"""Static contribution-area candidates on frozen TD receiver topology."""

from collections import deque
from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_storage_dispatch_io import validate_saved_storage as validate_basin_storage


SCHEMA = "td-surface-reaches-v1"
MAX_JSON_BYTES = 128 * 1024 * 1024


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _point_id(x, z):
    return "point:" + _hash([float(x).hex(), float(z).hex()])


def _derive(hierarchy, threshold_m2, storage):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    bed = arrays["height_m"].ravel()
    rows, columns = arrays["height_m"].shape
    usable = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    receiver = arrays["receiver"].copy()
    receiver[~usable] = -1
    for cell in np.flatnonzero(usable & (receiver >= 0)):
        if not usable[receiver[cell]]:
            receiver[cell] = -1
    donors = np.zeros(bed.size, np.int64)
    active_edges = np.flatnonzero(usable & (receiver >= 0))
    np.add.at(donors, receiver[active_edges], 1)
    queue = deque(int(cell) for cell in np.flatnonzero(usable & (donors == 0)))
    spacing = float(metadata["spacing_m"])
    area = np.where(usable, spacing ** 2, 0.0)
    order = []
    pending = donors.copy()
    while queue:
        cell = queue.popleft()
        order.append(cell)
        target = int(receiver[cell])
        if target >= 0:
            area[target] += area[cell]
            pending[target] -= 1
            if pending[target] == 0:
                queue.append(target)
    if len(order) != int(usable.sum()):
        raise ValueError("receiver cycle")
    selected = usable & (area >= threshold_m2)
    selected_donors = np.zeros(bed.size, np.int64)
    chosen_edges = np.flatnonzero(selected & (receiver >= 0))
    if np.any(~selected[receiver[chosen_edges]]):
        raise ValueError("threshold network lacks downstream closure")
    np.add.at(selected_donors, receiver[chosen_edges], 1)
    faces = {tuple(sorted(map(int, pair))): index for index, pair in enumerate(arrays["face_cells"])}
    origin_x, origin_z = metadata["origin_m_xz"]

    def point(cell):
        row, column = divmod(cell, columns)
        return [float(origin_x + column * spacing), float(bed[cell]), float(origin_z + row * spacing)]

    def node_id(cell):
        xyz = point(cell)
        return _point_id(xyz[0], xyz[2])

    def unknown_contact(cell):
        row, column = divmod(cell, columns)
        neighbors = []
        if row:
            neighbors.append(cell - columns)
        if row + 1 < rows:
            neighbors.append(cell + columns)
        if column:
            neighbors.append(cell - 1)
        if column + 1 < columns:
            neighbors.append(cell + 1)
        return any(not arrays["valid_mask"].ravel()[neighbor] for neighbor in neighbors)

    def terminal_kind(cell):
        original_target = int(arrays["receiver"][cell])
        if original_target >= 0 and arrays["protected_mask"].ravel()[original_target]:
            return "protected_barrier"
        if unknown_contact(cell):
            return "unknown_contact"
        if arrays["open_boundary_mask"].ravel()[cell]:
            return "engineered_open"
        return "internal_basin"

    anchors = [int(cell) for cell in np.flatnonzero(selected & ((selected_donors != 1) | (receiver < 0)))]
    reaches = []
    covered_edges = set()
    for start in anchors:
        if receiver[start] < 0:
            continue
        cells = [start]
        target = int(receiver[start])
        while True:
            cells.append(target)
            if selected_donors[target] != 1 or receiver[target] < 0:
                break
            target = int(receiver[target])
        edge_records = []
        for donor, target in zip(cells, cells[1:]):
            if bed[target] > bed[donor]:
                raise ValueError("uphill receiver edge")
            face = faces[tuple(sorted((donor, target)))]
            covered_edges.add(donor)
            record = {"edge_id": "edge:" + _hash([node_id(donor), node_id(target)]),
                      "donor_cell_id": donor, "target_cell_id": target, "face_index": face,
                      "hierarchy_identity_sha256": hierarchy["identity_sha256"], "stored_flux": None}
            if storage is not None:
                water = storage["arrays"]
                pair = arrays["face_cells"][face]
                forward = float(water["face_forward_m3"][face])
                reverse = float(water["face_reverse_m3"][face])
                along, against = (forward, reverse) if int(pair[0]) == donor else (reverse, forward)
                record["stored_flux"] = {"storage_identity_sha256": storage["identity_sha256"],
                    "face_cell_ids": list(map(int, pair)), "forward_m3": forward, "reverse_m3": reverse,
                    "net_face_m3": forward - reverse, "gross_m3": forward + reverse,
                    "along_receiver_m3": along, "against_receiver_m3": against,
                    "net_receiver_m3": along - against,
                    "forward_active_s": float(water["active_forward_s"][face]),
                    "reverse_active_s": float(water["active_reverse_s"][face])}
            edge_records.append(record)
        reaches.append({"reach_id": "reach:" + _hash([node_id(cell) for cell in cells]),
                        "start_node_id": node_id(start), "end_node_id": node_id(cells[-1]),
                        "cell_ids": cells, "xyz_m": [point(cell) for cell in cells],
                        "contributing_area_m2": [float(area[cell]) for cell in cells],
                        "basin_owner_ids": [int(arrays["cell_owner"].ravel()[cell]) for cell in cells],
                        "contribution_leaf_ids": [int(arrays["contribution_owner"].ravel()[cell]) for cell in cells],
                        "edges": edge_records})
    if covered_edges != set(map(int, chosen_edges)):
        raise ValueError("reach compression lost or duplicated receiver edges")
    nodes = [{"node_id": node_id(cell), "cell_id": cell, "xyz_m": point(cell),
              "contributing_area_m2": float(area[cell]), "selected_donor_count": int(selected_donors[cell]),
              "kind": "terminal" if receiver[cell] < 0 else "junction" if selected_donors[cell] > 1 else "head",
              "terminal_kind": terminal_kind(cell) if receiver[cell] < 0 else None,
              "boundary_kind": "engineered" if receiver[cell] < 0 and arrays["open_boundary_mask"].ravel()[cell] else None,
              "open_boundary": bool(arrays["open_boundary_mask"].ravel()[cell]),
              "unknown_contact": unknown_contact(cell), "basin_owner_id": int(arrays["cell_owner"].ravel()[cell])}
             for cell in anchors]
    terminal_area = sum(float(area[cell]) for cell in np.flatnonzero(usable & (receiver < 0)))
    if terminal_area != int(usable.sum()) * spacing ** 2:
        raise ValueError("contribution area ledger mismatch")
    return {"nodes": nodes, "reaches": reaches,
            "summary": {"usable_cells": int(usable.sum()), "protected_cells": int(arrays["protected_mask"].sum()),
                        "unknown_cells": int((~arrays["valid_mask"]).sum()),
                        "selected_cells": int(selected.sum()), "selected_edges": len(chosen_edges),
                        "reach_count": len(reaches), "node_count": len(nodes),
                        "terminal_contribution_area_m2": terminal_area,
                        "terminal_classes": dict(sorted(Counter(node["terminal_kind"] for node in nodes if node["kind"] == "terminal").items()))}}


def _storage_match(hierarchy, storage):
    validate_basin_storage(storage)
    if storage["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("storage hierarchy identity mismatch")
    for name in ("spacing_m", "origin_m_xz"):
        if storage["metadata"][name] != hierarchy["metadata"][name]:
            raise ValueError("storage coordinate mismatch")
    for name in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells"):
        if not np.array_equal(storage["arrays"][name], hierarchy["arrays"][name], equal_nan=True):
            raise ValueError("storage geometry/topology/boundary mismatch")
    boundary = np.flatnonzero(hierarchy["arrays"]["open_boundary_mask"].ravel())
    if not np.array_equal(boundary, storage["arrays"]["boundary_cells"]):
        raise ValueError("storage open boundary mismatch")


def _checked_surface_reaches(hierarchy, *, threshold_area_m2, expected_hierarchy_identity,
                         storage=None, expected_storage_identity=None):
    if isinstance(threshold_area_m2, bool) or not isinstance(threshold_area_m2, (int, float)) or not math.isfinite(threshold_area_m2) or threshold_area_m2 <= 0:
        raise ValueError("finite positive area threshold required")
    if hierarchy["identity_sha256"] != expected_hierarchy_identity:
        raise ValueError("external hierarchy identity mismatch")
    validate_basin_hierarchy(hierarchy)
    if storage is not None:
        if expected_storage_identity is None or storage["identity_sha256"] != expected_storage_identity:
            raise ValueError("external storage identity mismatch")
        _storage_match(hierarchy, storage)
    network = _derive(hierarchy, float(threshold_area_m2), storage)
    result = {"schema": SCHEMA, "algorithm": "static-D4-area-degree2-compression-v1",
              "threshold_area_m2": float(threshold_area_m2), "hierarchy_identity_sha256": expected_hierarchy_identity,
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "storage_identity_sha256": expected_storage_identity if storage is not None else None,
              "grid": {"shape_zx": list(hierarchy["arrays"]["height_m"].shape), "spacing_m": hierarchy["metadata"]["spacing_m"],
                       "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "axes": "X east, Z south; XYZ metres"},
              "hierarchy": {"node_parent": hierarchy["arrays"]["node_parent"].tolist(),
                            "node_unknown_contact": hierarchy["arrays"]["node_unknown_contact"].tolist()},
              **network, "flags": {"readonly": True, "bed_unchanged": True, "static_contribution_candidates": True,
                                     "water_generated": False, "geometry_generated": False,
                                     "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False},
              "flux_scope": {"stored_flux_available": storage is not None,
                             "elapsed_s": None if storage is None else (storage["arrays"]["depth_m"].shape[0] - 1) * storage["metadata"]["dt_s"],
                             "edge_time_series_available": False,
                             "semantics": "Each edge retains its own whole-run directional volume/activity. No edge-flux sum is an outlet Q; area is not rainfall discharge."},
              "limitations": "Thresholds are caller-declared, never automatically chosen. D4 static area paths are candidate drainage, not observed channels. Protection excludes local area and stops transfers. No width, depth, water surface or rain-Q inference. Engineering open boundaries are not natural outlets."}
    result["identity_sha256"] = _hash(result)
    return _freeze(result)


def make_surface_reaches(hierarchy, *, threshold_area_m2, expected_hierarchy_identity,
                         storage=None, expected_storage_identity=None):
    return _checked_surface_reaches(hierarchy, threshold_area_m2=threshold_area_m2,
        expected_hierarchy_identity=expected_hierarchy_identity, storage=storage,
        expected_storage_identity=expected_storage_identity)


def save_surface_reaches(result, path):
    plain = _plain(result)
    digest = plain.pop("identity_sha256", None)
    if plain.get("schema") != SCHEMA or _hash(plain) != digest:
        raise ValueError("reach identity/schema mismatch")
    plain["identity_sha256"] = digest
    payload = json.dumps(plain, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("reach JSON budget exceeded")
    publish_bytes(path, payload)


def load_surface_reaches(path, *, expected_sha256, expected_identity, hierarchy, storage=None):
    path = Path(path)
    if path.stat().st_size > MAX_JSON_BYTES or file_sha256(path) != expected_sha256:
        raise ValueError("external reach archive pin/budget mismatch")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite JSON value")
    result = json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)
    digest = result.pop("identity_sha256")
    if digest != expected_identity or _hash(result) != digest or result.get("schema") != SCHEMA:
        raise ValueError("external reach identity mismatch")
    if result["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("reach hierarchy mismatch")
    validate_basin_hierarchy(hierarchy)
    threshold = result["threshold_area_m2"]
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("invalid saved area threshold")
    if result["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]:
        raise ValueError("saved reach source identity mismatch")
    if storage is not None:
        _storage_match(hierarchy, storage)
        if storage["identity_sha256"] != result["storage_identity_sha256"] or storage["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
            raise ValueError("reach storage mismatch")
        for name in ("height_m", "valid_mask", "receiver", "face_cells"):
            if not np.array_equal(storage["arrays"][name], hierarchy["arrays"][name], equal_nan=True):
                raise ValueError("saved reach storage geometry mismatch")
    elif result["storage_identity_sha256"] is not None:
        raise ValueError("pinned reach flux requires storage")
    expected = _derive(hierarchy, result["threshold_area_m2"], storage)
    for name, value in expected.items():
        if value != result[name]:
            raise ValueError("saved reach topology/area/flux mismatch")
    if any(result["flags"][name] for name in ("hydraulic_ready", "natural_outlet_verified", "publishable", "water_generated", "geometry_generated")):
        raise ValueError("unverified reach claims")
    expected_full = _plain(_checked_surface_reaches(hierarchy, threshold_area_m2=threshold,
        expected_hierarchy_identity=hierarchy["identity_sha256"], storage=storage,
        expected_storage_identity=None if storage is None else storage["identity_sha256"]))
    expected_full.pop("identity_sha256")
    if result != expected_full:
        raise ValueError("saved reach metadata/identity/grid/hierarchy/flux semantics mismatch")
    result["identity_sha256"] = digest
    return _freeze(result)
