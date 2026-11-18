"""Explicit bounded local tributary declarations on an immutable coarse receiver.

These declarations are geometry requests, not additions to the registered river
mask, changed river-source thresholds, or accepted fine-water geometry.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np


ALGORITHM = "frozen-local-tributary-confluence-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _array_digest(value):
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode())
    digest.update(array.dtype.str.encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


def freeze_local_tributary_confluence(plan, *, junction_id, incoming_ids, highest_lake_level_m, lake_mask):
    """Freeze one explicit natural two-in/one-out coastal receiver junction."""
    if not isinstance(plan.get("identity_sha256"), str) or not plan["identity_sha256"]:
        raise ValueError("immutable parent plan identity required")
    height = np.asarray(plan["height_m"])
    owner = np.asarray(plan["owner_domain_id"])
    receiver = np.asarray(plan["receiver"])
    registered = np.asarray(plan["river_mask"])
    accumulation = np.asarray(plan["accumulation_area_m2"])
    mask = np.asarray(lake_mask)
    if (height.ndim != 2 or any(a.shape != height.shape for a in (owner, receiver, registered, accumulation, mask))
            or registered.dtype != bool or mask.dtype != bool or receiver.dtype.kind not in "iu"
            or not np.isfinite(height).all() or not np.isfinite(accumulation).all() or np.any(accumulation < 0)):
        raise ValueError("aligned finite frozen receiver/owner/area/river/lake arrays required")
    if not np.isfinite(highest_lake_level_m):
        raise ValueError("explicit verified finite highest lake level required")
    if isinstance(junction_id, bool) or not isinstance(junction_id, (int, np.integer)):
        raise ValueError("explicit integer coarse junction required")
    incoming = np.asarray(incoming_ids)
    if incoming.shape != (2,) or incoming.dtype.kind not in "iu" or len(set(incoming.tolist())) != 2:
        raise ValueError("exactly two distinct explicit coarse incoming ids required")
    junction = int(junction_id)
    upstream = sorted(int(value) for value in incoming)
    flat_height, flat_owner, flat_receiver = height.ravel(), owner.ravel(), receiver.ravel()
    flat_registered, flat_area = registered.ravel(), accumulation.ravel()
    cells = height.size
    if any(index < 0 or index >= cells for index in upstream + [junction]):
        raise ValueError("coarse tributary index out of range")
    downstream = int(flat_receiver[junction])
    if downstream < 0 or downstream >= cells:
        raise ValueError("junction requires a real outgoing receiver")
    domain_id = int(flat_owner[junction])
    domains = [domain for domain in plan["domains"] if domain["domain_id"] == domain_id]
    if len(domains) != 1 or domains[0]["kind"] != "coastal":
        raise ValueError("first local tributary declaration requires a registered coastal catchment")
    domain = domains[0]
    actual_incoming = np.flatnonzero((flat_receiver == junction) & (flat_owner == domain_id)).tolist()
    if actual_incoming != upstream:
        raise ValueError("explicit incoming edges are not the true two-in receiver junction")
    edges = [[upstream[0], junction], [upstream[1], junction], [junction, downstream]]
    wet = mask.ravel() & (flat_height < highest_lake_level_m)
    for first, second in edges:
        if flat_receiver[first] != second or flat_owner[first] != domain_id or flat_owner[second] != domain_id:
            raise ValueError("tributary edge crosses owner or is not an actual frozen receiver")
        if flat_height[first] <= flat_height[second]:
            raise ValueError("tributary receiver edge is not strictly descending")
        if wet[first] or wet[second]:
            raise ValueError("tributary confluence is submerged in the verified highest wet lake")
    # Every downstream step is bounded, owner-consistent and reaches the already
    # registered marine terminal. A window edge is never treated as an outlet.
    chain, seen = [], set()
    index = junction
    ocean = np.asarray(plan["ocean_mask"])
    if ocean.shape != height.shape or ocean.dtype != bool:
        raise ValueError("frozen marine identity mask required")
    for unused_step in range(cells):
        if index < 0 or index >= cells or index in seen:
            raise ValueError("cyclic or out-of-range tributary terminal trace")
        seen.add(index)
        chain.append(index)
        if wet[index]:
            raise ValueError("tributary downstream trace enters verified wet lake")
        if flat_owner[index] == -1:
            if not ocean.ravel()[index] or flat_height[index] >= 0 or index not in domain["terminal_indices"]:
                raise ValueError("tributary trace lacks an already registered marine terminal")
            if flat_receiver[index] != -1:
                raise ValueError("registered marine terminal must terminate the frozen receiver")
            break
        if flat_owner[index] != domain_id:
            raise ValueError("tributary trace enters another or unknown owner")
        other = int(flat_receiver[index])
        if other < 0 or other >= cells or flat_height[index] <= flat_height[other]:
            raise ValueError("tributary downstream trace lacks a descending registered terminal path")
        index = other
    else:
        raise ValueError("tributary terminal trace exceeds receiver-size bound")
    spacing = float(plan["spacing_m"])
    threshold = float(plan["river_threshold_area_m2"])
    origin = np.asarray(plan["origin_xz_m"], dtype=float)
    if spacing <= 0 or threshold <= 0 or not np.isfinite([spacing, threshold]).all() or origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("finite physical grid and unchanged river threshold required")
    columns = height.shape[1]
    records = []
    for first, second in edges:
        is_registered = bool(flat_registered[first])
        if is_registered != bool(flat_area[first] >= threshold):
            raise ValueError("frozen river mask disagrees with the frozen accumulation threshold")
        records.append({"source_edge": [first, second], "owner_domain_id": domain_id,
                        "start_world_xz_m": (origin + [first % columns * spacing, first // columns * spacing]).tolist(),
                        "end_world_xz_m": (origin + [second % columns * spacing, second // columns * spacing]).tolist(),
                        "start_height_m": float(flat_height[first]), "end_height_m": float(flat_height[second]),
                        "start_accumulation_area_m2": float(flat_area[first]),
                        "end_accumulation_area_m2": float(flat_area[second]),
                        "category": "registered_river_edge" if is_registered else "subthreshold_local_tributary_edge"})
    if not any(record["category"] == "subthreshold_local_tributary_edge" for record in records[:2]):
        raise ValueError("local tributary sidecar requires an explicit unregistered incoming tributary")
    declaration = {"algorithm": ALGORITHM, "status": "frozen_geometry_unverified",
                   "parent_plan_identity_sha256": plan["identity_sha256"], "junction_id": junction,
                   "incoming_ids": upstream, "owner_domain_id": domain_id,
                   "river_threshold_area_m2": threshold, "edges": records,
                   "registered_terminal_id": chain[-1], "downstream_receiver_chain": chain,
                   "receiver_sha256": _array_digest(receiver), "river_mask_sha256": _array_digest(registered),
                   "highest_lake_level_m": float(highest_lake_level_m), "lake_mask_sha256": _array_digest(mask),
                   "scope": "bounded three-edge local tributary geometry; parent river mask and threshold unchanged",
                   "freeze_order": "declaration must be saved before any new TD source inference or geometry solve",
                   "fine_geometry_certified": False, "global_hydrology_certified": False}
    declaration["identity_sha256"] = _digest(declaration)
    return declaration


def validate_local_tributary_sidecar(plan, declaration, *, highest_lake_level_m, lake_mask):
    """Cold-check the frozen declaration against its real receiver and wet stage."""
    expected = freeze_local_tributary_confluence(plan, junction_id=declaration["junction_id"],
        incoming_ids=declaration["incoming_ids"], highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    if declaration != expected:
        raise ValueError("local tributary declaration or immutable parent provenance mismatch")
    return {"status": "verified_declared_receiver_graph", "fine_geometry_certified": False,
            "sidecar_identity_sha256": declaration["identity_sha256"]}


def validate_local_tributary_source_edges(plan, declaration, node_source_edges, *, highest_lake_level_m, lake_mask):
    """Opt-in fine nodes may use only one of the three declared real edges."""
    validate_local_tributary_sidecar(plan, declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    edges = np.asarray(node_source_edges)
    if edges.ndim != 2 or edges.shape[1] != 2 or edges.dtype.kind not in "iu" or not len(edges):
        raise ValueError("integer clipped-node source edges required")
    allowed = {tuple(record["source_edge"]) for record in declaration["edges"]}
    if any(tuple(int(value) for value in edge) not in allowed for edge in edges):
        raise ValueError("fine tributary source edge is outside the explicit three-edge declaration")
    return {"status": "verified_declared_receiver_edges", "sidecar_identity_sha256": declaration["identity_sha256"],
            "fine_geometry_certified": False}


def save_local_tributary_sidecar(declaration, path):
    """Publish a new declaration using the existing immutable JSON-file pattern."""
    unsigned = {key: value for key, value in declaration.items() if key != "identity_sha256"}
    if declaration.get("identity_sha256") != _digest(unsigned) or declaration.get("status") != "frozen_geometry_unverified":
        raise ValueError("invalid frozen local tributary declaration identity")
    payload = json.dumps(declaration, indent=2, allow_nan=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)


def load_local_tributary_sidecar(plan, path, *, highest_lake_level_m, lake_mask):
    declaration = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_local_tributary_sidecar(plan, declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    return declaration


def build_local_tributary_window(plan, declaration, *, highest_lake_level_m, lake_mask):
    """Select one frozen native97 window at the explicit junction, no search."""
    validate_local_tributary_sidecar(plan, declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    junction = declaration["junction_id"]
    columns = plan["height_m"].shape[1]
    center = np.asarray(plan["origin_xz_m"], float) + np.array([junction % columns, junction // columns]) * plan["spacing_m"]
    native_origin = np.floor(center / 30.0).astype(np.int64) - 48
    return {"kind": "confluence", "status": "planned", "coarse_cell": junction,
            "native_origin_xz": native_origin.tolist(), "shape": [97, 97],
            "origin_xz_m": (native_origin * 30.0).tolist(), "spacing_m": 30.0,
            "selection_edge_cell_ids": declaration["edges"][2]["source_edge"],
            "declared_source_edge_cell_ids": [record["source_edge"] for record in declaration["edges"]],
            "selection_algorithm": "explicit-local-tributary-junction-native-floor-v1",
            "local_tributary_sidecar_identity_sha256": declaration["identity_sha256"],
            "river_selection_semantics": "local subthreshold tributary geometry request; not two previously registered river branches",
            "fine_geometry_certified": False, "global_hydrology_certified": False}


def _save_matching_json(path, record):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("immutable local tributary preparation declaration differs")
        return
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)


def prepare_local_tributary_source_declaration(plan, declaration, output, *, budget, highest_lake_level_m,
                                             lake_mask, maximum_source_tiles=15):
    """CPU-only frozen collection/detail declarations plus existing dependency API.

    This never generates TD or projects terrain. After reviewing the written
    dependencies, the caller may invoke existing prepare_projection_source with
    generate=True. Original97 assembly must honor this custom frozen selection.
    """
    raise NotImplementedError("This adapter requires the private development tools.")


def prepare_local_tributary_original(plan, declaration, output, *, budget, highest_lake_level_m, lake_mask,
                                    resource_tier="light", canonical_cache_root=None):
    """Assemble only already cached genuine TD and derive the new native97 crop.

    Every declared tile and pin must exist before constructing the backend. The
    backend inference method is explicitly disabled, including a later cache
    race. This does not perform a macro projection or continuous bed solve.
    """
    raise NotImplementedError("This adapter requires the private development tools.")
