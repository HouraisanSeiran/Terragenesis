"""Read-only potential basin connections with unique native-face evidence."""

from collections import Counter
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_surface_reaches import (
    _plain, _freeze, _hash, _storage_match, _checked_surface_reaches,
)

SCHEMA = "td-basin-spill-network-v1"
MAX_JSON_BYTES = 128 * 1024 * 1024


def _read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON")

    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)


def _finite(value):
    return float(value) if math.isfinite(value) else None


def _checked_network(hierarchy, reach_networks, storage, hierarchy_pin, storage_pin, face_sink=None):
    if hierarchy["identity_sha256"] != hierarchy_pin:
        raise ValueError("external hierarchy identity mismatch")
    validate_basin_hierarchy(hierarchy)
    if storage is not None:
        if storage_pin is None or storage["identity_sha256"] != storage_pin:
            raise ValueError("external storage identity mismatch")
        _storage_match(hierarchy, storage)
    elif storage_pin is not None:
        raise ValueError("storage pin without storage")
    arrays = hierarchy["arrays"]
    parent = arrays["node_parent"]
    chains = []
    for node in range(len(parent)):
        chain = []
        cursor = node
        while cursor >= 0:
            if cursor in chain:
                raise ValueError("parent cycle")
            chain.append(cursor)
            cursor = int(parent[cursor])
        chains.append(chain)
    ancestor_sets = [set(chain) for chain in chains]
    bed = arrays["height_m"].ravel()
    owners = arrays["cell_owner"].ravel()
    protected = arrays["protected_mask"].ravel()
    unknown = arrays["node_unknown_contact"]
    columns = arrays["height_m"].shape[1]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]

    def point(cell):
        row, column = divmod(cell, columns)
        return [origin[0] + column * spacing, float(bed[cell]), origin[1] + row * spacing]

    spills, incident, rejected = [], {}, Counter()
    pair_minimum = {}
    for pair in arrays["face_cells"]:
        first, second = map(int, pair)
        first_owner, second_owner = int(owners[first]), int(owners[second])
        if first_owner == second_owner or protected[first] or protected[second] or unknown[first_owner] or unknown[second_owner]:
            continue
        key = tuple(sorted((first_owner, second_owner)))
        pair_minimum[key] = min(pair_minimum.get(key, math.inf), float(max(bed[first], bed[second])))
    counts = Counter()
    for face, pair in enumerate(arrays["face_cells"]):
        first, second = map(int, pair)
        first_owner, second_owner = int(owners[first]), int(owners[second])
        second_ancestors = ancestor_sets[second_owner]
        merge = next((node for node in chains[first_owner] if node in second_ancestors), -1)
        if merge != int(arrays["face_merge_node"][face]):
            raise ValueError("saved face merge is not owner LCA")
        if first_owner == second_owner:
            continue
        reasons = []
        if protected[first] or protected[second]:
            reasons.append("protected_endpoint")
        if unknown[first_owner] or unknown[second_owner]:
            reasons.append("unknown_owner_subtree")
        if merge < 0:
            reasons.append("no_common_merge")
        sill = float(max(bed[first], bed[second]))
        if sill != arrays["face_level_m"][face]:
            raise ValueError("face sill mismatch")
        endpoints = sorted([[float(value).hex() for value in point(cell)] for cell in (first, second)])
        face_id = "face:" + _hash([hierarchy["metadata"]["source_identity_sha256"], endpoints])
        stages = []
        for owner in (first_owner, second_owner):
            chain = chains[owner]
            branch = chain[chain.index(merge) - 1] if merge in chain and owner != merge else None
            stages.append(branch)
        flux = None
        if storage is not None:
            water = storage["arrays"]
            forward = float(water["face_forward_m3"][face])
            reverse = float(water["face_reverse_m3"][face])
            flux = {"forward_m3": forward, "reverse_m3": reverse,
                    "gross_m3": forward + reverse, "net_first_to_second_m3": forward - reverse,
                    "positive_transfer_recorded": forward + reverse > 0}
        record = {"face_id": face_id, "face_index": face, "face_cell_ids": [first, second],
                  "owner_ids": [first_owner, second_owner], "xyz_m": [point(first), point(second)],
                  "merge_node_id": merge, "merge_birth_m": None if merge < 0 else float(arrays["node_birth_m"][merge]),
                  "face_sill_m": sill, "physical_face_sill_m": sill, "merge_child_ids": stages,
                  "potential_connection_allowed": not reasons, "rejection_reasons": reasons,
                  "potential_only": flux is None or not flux["positive_transfer_recorded"],
                  "stored_whole_run_flux": flux}
        key = tuple(sorted(record["owner_ids"]))
        record["lowest_allowed_owner_pair_face"] = not reasons and sill == pair_minimum.get(key)
        record["classification"] = "rejected_adjacency" if reasons else "lowest_owner_pair_face" if record["lowest_allowed_owner_pair_face"] else "higher_owner_pair_adjacency"
        counts["cross_owner_faces"] += 1
        counts["allowed_potential_faces"] += not reasons
        counts["lowest_owner_pair_faces"] += record["lowest_allowed_owner_pair_face"]
        counts["recorded_transfer_faces"] += flux is not None and flux["positive_transfer_recorded"]
        if face_sink is None:
            spills.append(record)
        else:
            face_sink(record)
        rejected.update(reasons)
        for owner in (first_owner, second_owner):
            incident.setdefault(owner, []).append(face_id)
    cases = []
    thresholds = set()
    for network in reach_networks:
        expected = _checked_surface_reaches(hierarchy, threshold_area_m2=network["threshold_area_m2"],
            expected_hierarchy_identity=hierarchy_pin, storage=storage, expected_storage_identity=storage_pin)
        if _plain(network) != _plain(expected):
            raise ValueError("reach semantic mismatch")
        if network["threshold_area_m2"] in thresholds:
            raise ValueError("duplicate reach threshold")
        thresholds.add(network["threshold_area_m2"])
        joins = []
        for node in network["nodes"]:
            if node["kind"] != "terminal":
                continue
            owner = int(owners[node["cell_id"]])
            joins.append({"reach_node_id": node["node_id"], "cell_id": node["cell_id"],
                          "terminal_kind": node["terminal_kind"], "owner_id": owner,
                          "contribution_leaf_id": int(arrays["contribution_owner"].ravel()[node["cell_id"]]),
                          "incident_face_ids": incident.get(owner, [])})
        cases.append({"threshold_area_m2": network["threshold_area_m2"],
                      "reach_identity_sha256": network["identity_sha256"], "terminal_owner_joins": joins})
    nodes = [{"node_id": node, "parent_id": int(parent[node]),
              "birth_m": float(arrays["node_birth_m"][node]),
              "upper_m": _finite(arrays["node_upper_m"][node]),
              "stage_capacity_m3": _finite(arrays["stage_capacity_m3"][node]),
              "unknown_contact": bool(unknown[node]), "open_boundary": bool(arrays["node_open_boundary"][node])}
             for node in range(len(parent))]
    result = {"schema": SCHEMA, "algorithm": "unique-D4-cross-owner-face-LCA-v1",
              "hierarchy_identity_sha256": hierarchy_pin,
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "storage_identity_sha256": storage_pin,
              "grid": {"shape_zx": list(arrays["height_m"].shape), "spacing_m": spacing,
                       "origin_m_xz": origin, "axes": "X east, Z south; XYZ metres"},
              "basin_nodes": nodes, "spills": spills, "reach_cases": cases,
              "summary": {**{name: counts[name] for name in ("cross_owner_faces", "lowest_owner_pair_faces", "allowed_potential_faces", "recorded_transfer_faces")}, "rejection_counts": dict(rejected)},
              "flux_scope": {"elapsed_s": None if storage is None else (storage["arrays"]["depth_m"].shape[0] - 1) * storage["metadata"]["dt_s"],
                             "time_series_available": False, "spill_onset_known": False,
                             "semantics": "Unique physical face, ordered first-to-second. Whole-run directional integrals; never summed over nested basin ancestors or reported as outlet Q."},
              "flags": {"readonly": True, "bed_unchanged": True, "receiver_unchanged": True,
                        "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False,
                        "water_generated": False, "publishable": False},
              "limitations": "All cross-owner faces are potential adjacency, not actual spill outlets or routed channels. Lowest allowed owner-pair faces include ties and are not certified global basin escape saddles. LCA merge birth and physical face sill are distinct. Subtree capacity thresholds are not measured storage and cannot be added across ancestors. Rejected faces retain evidence but are not allowed graph links. No dynamic onset, discharge, channel geometry or new water."}
    result["identity_sha256"] = _hash(result)
    return _freeze(result)


def make_basin_spill_network(hierarchy, *, expected_hierarchy_identity, reach_networks=(),
                            storage=None, expected_storage_identity=None):
    return _checked_network(hierarchy, reach_networks, storage, expected_hierarchy_identity, expected_storage_identity)


def save_basin_spill_network(result, path):
    plain = _plain(result)
    digest = plain.pop("identity_sha256", None)
    if plain.get("schema") != SCHEMA or _hash(plain) != digest:
        raise ValueError("spill identity/schema mismatch")
    plain["identity_sha256"] = digest
    payload = json.dumps(plain, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("spill JSON budget exceeded")
    publish_bytes(path, payload)


def load_basin_spill_network(path, *, expected_sha256, expected_identity, hierarchy,
                            reach_networks=(), storage=None):
    path = Path(path)
    if path.stat().st_size > MAX_JSON_BYTES or file_sha256(path) != expected_sha256:
        raise ValueError("external spill hash/budget mismatch")
    checked = _checked_network(hierarchy, reach_networks, storage, hierarchy["identity_sha256"],
        None if storage is None else storage["identity_sha256"])
    semantic_identity = checked["identity_sha256"]
    del checked
    if semantic_identity != expected_identity:
        raise ValueError("saved spill semantics mismatch")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON")

    result = json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)
    digest = result.pop("identity_sha256")
    if digest != expected_identity or _hash(result) != digest:
        raise ValueError("external spill identity mismatch")
    result["identity_sha256"] = digest
    return _freeze(result)


def save_basin_spill_bundle(directory, hierarchy, *, expected_hierarchy_identity,
                           reach_networks=(), storage=None, expected_storage_identity=None):
    directory = Path(directory)
    chunks, pending = [], []

    def flush():
        if not pending:
            return
        name = f"faces-{len(chunks):04d}.json"
        payload = json.dumps(pending, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        publish_bytes(directory / name, payload)
        chunks.append({"file": name, "expected_sha256": file_sha256(directory / name),
                       "identity_sha256": _hash(pending), "face_count": len(pending), "bytes": len(payload)})
        pending.clear()

    def sink(record):
        pending.append(record)
        if len(pending) == 2048:
            flush()

    metadata = _plain(_checked_network(hierarchy, reach_networks, storage, expected_hierarchy_identity,
        expected_storage_identity, face_sink=sink))
    flush()
    metadata.pop("identity_sha256")
    metadata.pop("spills")
    metadata["schema"] = "td-basin-spill-sharded-v2"
    metadata["face_chunks"] = chunks
    metadata["contribution_leaf_graph"] = _leaf_graph(hierarchy, storage)
    metadata["identity_sha256"] = _hash(metadata)
    publish_bytes(directory / "bundle.json", json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    return _freeze(metadata)


def load_basin_spill_bundle(path, *, expected_sha256, expected_identity, hierarchy,
                           reach_networks=(), storage=None):
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024 or file_sha256(path) != expected_sha256:
        raise ValueError("external spill bundle pin/budget mismatch")
    metadata = _read_json(path)
    digest = metadata.pop("identity_sha256")
    if digest != expected_identity or _hash(metadata) != digest or metadata["schema"] != "td-basin-spill-sharded-v2":
        raise ValueError("external spill bundle identity mismatch")
    chunks = metadata["face_chunks"]
    if not isinstance(chunks, list) or len(chunks) > 1000:
        raise ValueError("invalid chunk registry")
    registered = set()
    for index, pin in enumerate(chunks):
        if pin["file"] != f"faces-{index:04d}.json" or type(pin["face_count"]) is not int or not 1 <= pin["face_count"] <= 2048:
            raise ValueError("unsafe chunk path/order/count")
        chunk_path = path.parent / pin["file"]
        if not chunk_path.is_file() or chunk_path.is_symlink() or chunk_path.resolve().parent != path.parent.resolve():
            raise ValueError("missing or redirected face chunk")
        registered.add(pin["file"])
    if {entry.name for entry in path.parent.glob("faces-*.json")} != registered:
        raise ValueError("extra or missing face chunk files")
    cursor, pending = 0, []

    def check_chunk():
        nonlocal cursor
        if not pending:
            return
        if cursor >= len(chunks):
            raise ValueError("missing face chunk")
        pin = chunks[cursor]
        if pin["file"] != f"faces-{cursor:04d}.json" or pin["face_count"] != len(pending):
            raise ValueError("face chunk order/count mismatch")
        chunk_path = path.parent / pin["file"]
        if chunk_path.stat().st_size != pin["bytes"] or pin["bytes"] > 4 * 1024 * 1024 or file_sha256(chunk_path) != pin["expected_sha256"]:
            raise ValueError("external face chunk pin/budget mismatch")
        payload = _read_json(chunk_path)
        if _hash(payload) != pin["identity_sha256"] or payload != pending:
            raise ValueError("face chunk semantic mismatch")
        cursor += 1
        pending.clear()

    def sink(record):
        pending.append(record)
        if len(pending) == 2048:
            check_chunk()

    expected = _plain(_checked_network(hierarchy, reach_networks, storage,
        metadata["hierarchy_identity_sha256"], metadata["storage_identity_sha256"], face_sink=sink))
    check_chunk()
    if cursor != len(chunks):
        raise ValueError("extra face chunks")
    expected.pop("identity_sha256")
    expected.pop("spills")
    expected["schema"] = metadata["schema"]
    expected["face_chunks"] = chunks
    expected["contribution_leaf_graph"] = _leaf_graph(hierarchy, storage)
    if expected != metadata:
        raise ValueError("bundle metadata semantics mismatch")
    metadata["identity_sha256"] = digest
    return _freeze(metadata)


def _leaf_graph(hierarchy, storage):
    arrays = hierarchy["arrays"]
    leaf = arrays["contribution_owner"].ravel()
    protected = arrays["protected_mask"].ravel()
    bed = arrays["height_m"].ravel()
    leaf_nodes = []
    leaf_ids = {}
    columns = arrays["height_m"].shape[1]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    valid = arrays["valid_mask"].ravel()
    for node in np.unique(leaf[valid]):
        cells = np.flatnonzero(valid & (leaf == node))
        terminals = cells[arrays["receiver"][cells] < 0]
        if len(terminals) != 1:
            raise ValueError("catchment requires unique receiver terminal")
        terminal = int(terminals[0])
        row, column = divmod(terminal, columns)
        xyz = [float(origin[0] + column * spacing), float(bed[terminal]), float(origin[1] + row * spacing)]
        stable_id = "leaf:" + _hash([hierarchy["metadata"]["source_identity_sha256"], [value.hex() for value in xyz]])
        leaf_ids[int(node)] = stable_id
        kind = "protected_terminal" if protected[terminal] else "unknown_contact" if arrays["node_unknown_contact"][node] else "engineered_open" if arrays["open_boundary_mask"].ravel()[terminal] else "internal_basin"
        leaf_nodes.append({"leaf_id": int(node), "stable_leaf_id": stable_id,
                           "terminal_cell_id": terminal, "terminal_xyz_m": xyz, "terminal_kind": kind,
                           "cell_count": len(cells), "area_m2": len(cells) * spacing ** 2,
                           "cell_id_bounds": [int(cells.min()), int(cells.max())],
                           "bounds_semantics": "inclusive min/max bounds, not a contiguous membership range"})
    pairs = {}
    for face, cells in enumerate(arrays["face_cells"]):
        first, second = map(int, cells)
        first_leaf, second_leaf = int(leaf[first]), int(leaf[second])
        if first_leaf == second_leaf:
            continue
        key = tuple(sorted((first_leaf, second_leaf)))
        entry = pairs.setdefault(key, {"leaf_ids": list(key), "all_face_indices": [],
            "minimum_physical_sill_m": None, "minimum_face_indices": [],
            "forward_leaf0_to_leaf1_m3": 0., "reverse_leaf1_to_leaf0_m3": 0.,
            "rejected_face_indices": []})
        entry["all_face_indices"].append(face)
        rejected = protected[first] or protected[second] or arrays["node_unknown_contact"][first_leaf] or arrays["node_unknown_contact"][second_leaf]
        sill = float(max(bed[first], bed[second]))
        if rejected:
            entry["rejected_face_indices"].append(face)
        elif entry["minimum_physical_sill_m"] is None or sill < entry["minimum_physical_sill_m"]:
            entry["minimum_physical_sill_m"] = sill
            entry["minimum_face_indices"] = [face]
        elif sill == entry["minimum_physical_sill_m"]:
            entry["minimum_face_indices"].append(face)
        if storage is not None:
            forward = float(storage["arrays"]["face_forward_m3"][face])
            reverse = float(storage["arrays"]["face_reverse_m3"][face])
            along, against = (forward, reverse) if first_leaf == key[0] else (reverse, forward)
            entry["forward_leaf0_to_leaf1_m3"] += along
            entry["reverse_leaf1_to_leaf0_m3"] += against
    for entry in pairs.values():
        entry["stable_leaf_ids"] = [leaf_ids[node] for node in entry["leaf_ids"]]
        entry["pair_id"] = "leaf-pair:" + _hash(sorted(entry["stable_leaf_ids"]))
        entry["surface_flux_whole_run"] = storage is not None
        entry["gross_m3"] = entry["forward_leaf0_to_leaf1_m3"] + entry["reverse_leaf1_to_leaf0_m3"]
        entry["net_leaf0_to_leaf1_m3"] = entry["forward_leaf0_to_leaf1_m3"] - entry["reverse_leaf1_to_leaf0_m3"]
        entry["potential_connection_allowed"] = bool(entry["minimum_face_indices"])
    return {"partition": "exclusive contribution_owner catchments, not nested cell_owner activation nodes",
            "semantics": "Each cross-leaf physical face appears once. Pair directional volumes are whole-run surface_flux, never discharge Q or known spill onset. Minimum pair faces are not global natural escape outlets. Rejected faces remain in measured ledger but are not traversable links.",
            "leaf_nodes": leaf_nodes, "pairs": list(pairs.values()), "unique_cross_leaf_faces": sum(len(entry["all_face_indices"]) for entry in pairs.values())}
