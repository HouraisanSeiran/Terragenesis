"""Potential minimax escape forest on exclusive saved catchment partitions."""

import heapq
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_spill_network import _leaf_graph, _read_json
from terrain_pipeline.td_surface_reaches import _plain, _freeze, _hash

SCHEMA = "td-basin-escape-plan-v1"
MAX_BYTES = 16 * 1024 * 1024


def _face_id(hierarchy, face):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    columns = arrays["height_m"].shape[1]
    spacing = metadata["spacing_m"]
    origin = metadata["origin_m_xz"]
    endpoints = []
    for cell in arrays["face_cells"][face]:
        row, column = divmod(int(cell), columns)
        xyz = [float(origin[0] + column * spacing), float(arrays["height_m"].ravel()[cell]),
               float(origin[1] + row * spacing)]
        endpoints.append([value.hex() for value in xyz])
    return "face:" + _hash([metadata["source_identity_sha256"], sorted(endpoints)])


def _checked_plan(hierarchy, graph, seeds, hierarchy_pin):
    if hierarchy["identity_sha256"] != hierarchy_pin:
        raise ValueError("external hierarchy identity mismatch")
    validate_basin_hierarchy(hierarchy)
    expected_graph = _leaf_graph(hierarchy, None)
    graph_plain = _plain(graph)
    if graph_plain["leaf_nodes"] != expected_graph["leaf_nodes"]:
        raise ValueError("catchment node semantics mismatch")
    geometry_fields = ("leaf_ids", "stable_leaf_ids", "pair_id", "all_face_indices", "minimum_physical_sill_m",
                       "minimum_face_indices", "rejected_face_indices", "potential_connection_allowed")
    if len(graph_plain["pairs"]) != len(expected_graph["pairs"]):
        raise ValueError("catchment pair coverage mismatch")
    for actual, expected in zip(graph_plain["pairs"], expected_graph["pairs"]):
        if any(actual[name] != expected[name] for name in geometry_fields):
            raise ValueError("catchment pair geometry mismatch")
    arrays = hierarchy["arrays"]
    leaf = arrays["contribution_owner"].ravel()
    bed = arrays["height_m"].ravel()
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    nodes = {node["leaf_id"]: node for node in expected_graph["leaf_nodes"]}
    blocked = {}
    for node in nodes:
        reasons = []
        if arrays["node_unknown_contact"][node]:
            reasons.append("unknown_contact")
        if np.any(protected & (leaf == node)):
            reasons.append("protected_catchment")
        blocked[node] = reasons
    seeds = _plain(seeds)
    if not isinstance(seeds, list):
        raise ValueError("explicit seed list required")
    seed_cells = set()
    seed_records = []
    for seed in seeds:
        if set(seed) != {"leaf_id", "boundary_cell_id"}:
            raise ValueError("seed requires leaf and exact engineering boundary cell")
        node, cell = seed["leaf_id"], seed["boundary_cell_id"]
        if type(node) is not int or type(cell) is not int or node not in nodes or not 0 <= cell < len(bed):
            raise ValueError("invalid seed cell/leaf")
        if not arrays["open_boundary_mask"].ravel()[cell] or int(leaf[cell]) != node or blocked[node]:
            raise ValueError("seed is not an allowed engineering boundary")
        if cell in seed_cells:
            raise ValueError("duplicate engineering boundary seed")
        seed_cells.add(cell)
        seed_records.append({**seed, "boundary_level_m": float(bed[cell]), "stable_leaf_id": nodes[node]["stable_leaf_id"]})
    seed_records.sort(key=lambda item: (item["stable_leaf_id"], item["boundary_level_m"], item["boundary_cell_id"]))
    adjacency = {node: [] for node in nodes}
    for pair in expected_graph["pairs"]:
        first, second = pair["leaf_ids"]
        if not pair["potential_connection_allowed"] or blocked[first] or blocked[second]:
            continue
        face = min(pair["minimum_face_indices"], key=lambda index: _face_id(hierarchy, index))
        evidence = {"pair_id": pair["pair_id"], "face_index": face, "face_id": _face_id(hierarchy, face),
                    "face_cell_ids": arrays["face_cells"][face].tolist(), "physical_sill_m": pair["minimum_physical_sill_m"]}
        adjacency[first].append((second, evidence))
        adjacency[second].append((first, evidence))
    distances = {node: math.inf for node in nodes}
    candidate_keys, parents, chosen_faces, roots = {}, {}, {}, {}
    heap = []
    for seed in seed_records:
        node, cell, stage = seed["leaf_id"], seed["boundary_cell_id"], seed["boundary_level_m"]
        key = (stage, "seed", nodes[node]["stable_leaf_id"], cell)
        if node not in candidate_keys or key < candidate_keys[node]:
            candidate_keys[node] = key
            distances[node] = stage
            parents[node], chosen_faces[node], roots[node] = None, None, cell
            heapq.heappush(heap, (stage, nodes[node]["stable_leaf_id"], node, key))
    settled = {}
    while heap:
        stage, stable_id, node, key = heapq.heappop(heap)
        if node in settled or candidate_keys[node] != key:
            continue
        settled[node] = len(settled)
        for target, evidence in adjacency[node]:
            if target in settled:
                continue
            target_stage = max(stage, evidence["physical_sill_m"])
            target_key = (target_stage, "face", evidence["face_id"], stable_id)
            if target not in candidate_keys or target_key < candidate_keys[target]:
                candidate_keys[target] = target_key
                distances[target] = target_stage
                parents[target], chosen_faces[target], roots[target] = node, evidence, roots[node]
                heapq.heappush(heap, (target_stage, nodes[target]["stable_leaf_id"], target, target_key))
    records = []
    area = hierarchy["metadata"]["spacing_m"] ** 2
    for node in sorted(nodes, key=lambda value: nodes[value]["stable_leaf_id"]):
        reachable = node in settled
        stage = distances[node] if reachable else None
        volume = None if not reachable else float(np.maximum(stage - bed[valid & (leaf == node)], 0).sum() * area)
        records.append({"leaf_id": node, "stable_leaf_id": nodes[node]["stable_leaf_id"],
                        "reachable": reachable, "minimum_escape_stage_m": stage,
                        "parent_leaf_id": parents.get(node), "minimum_face": chosen_faces.get(node),
                        "root_boundary_cell_id": roots.get(node), "settlement_rank": settled.get(node),
                        "raise_to_stage_volume_m3": volume,
                        "unreachable_reasons": [] if reachable else blocked[node] or ["no_allowed_path_to_explicit_seed"]})
    result = {"schema": SCHEMA, "algorithm": "multi-source-minimax-settled-parent-forest-v1",
              "hierarchy_identity_sha256": hierarchy_pin,
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "catchment_geometry_identity_sha256": _hash(expected_graph), "engineering_seeds": seed_records,
              "leaves": records, "summary": {"leaf_count": len(records), "reachable_leaves": len(settled),
                "unreachable_leaves": len(records) - len(settled),
                "exclusive_raise_to_stage_volume_m3": sum(item["raise_to_stage_volume_m3"] or 0. for item in records)},
              "flags": {"potential_only": True, "bed_unchanged": True, "receiver_unchanged": True,
                        "hydraulic_verified": False, "hydraulic_ready": False, "transient_converged": False,
                        "publishable": False, "natural_outlet_verified": False, "water_generated": False},
              "semantics": "Engineering seed stage equals its unchanged boundary bed. Minimum maximum face sill to any explicit seed. Parent always settled earlier, including equal levels; physical IDs resolve ties. Raise-to-stage volume sums positive(stage-bed) over exclusive catchment cells, not existing water, incremental fill demand or nested hierarchy capacities. Unknown or any protected catchment is conservatively blocked. No imposed receiver link, bed filling/cutting, hydro solve, spill onset, Q or coupled cross-domain advancement."}
    result["identity_sha256"] = _hash(result)
    return _freeze(result)


def make_basin_escape_plan(hierarchy, *, contribution_leaf_graph, engineering_seeds, expected_hierarchy_identity):
    return _checked_plan(hierarchy, contribution_leaf_graph, engineering_seeds, expected_hierarchy_identity)


def save_basin_escape_plan(result, path):
    plain = _plain(result)
    digest = plain.pop("identity_sha256")
    if plain.get("schema") != SCHEMA or _hash(plain) != digest:
        raise ValueError("escape plan identity/schema mismatch")
    plain["identity_sha256"] = digest
    payload = json.dumps(plain, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > MAX_BYTES:
        raise ValueError("escape plan JSON budget exceeded")
    publish_bytes(path, payload)


def load_basin_escape_plan(path, *, expected_sha256, expected_identity, hierarchy, contribution_leaf_graph):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES or file_sha256(path) != expected_sha256:
        raise ValueError("external escape plan pin/budget mismatch")
    result = _read_json(path)
    digest = result.pop("identity_sha256")
    if digest != expected_identity or _hash(result) != digest:
        raise ValueError("external escape plan identity mismatch")
    seeds = [{"leaf_id": seed["leaf_id"], "boundary_cell_id": seed["boundary_cell_id"]} for seed in result["engineering_seeds"]]
    expected = _checked_plan(hierarchy, contribution_leaf_graph, seeds, result["hierarchy_identity_sha256"])
    if expected["identity_sha256"] != digest:
        raise ValueError("escape plan semantic mismatch")
    result["identity_sha256"] = digest
    return _freeze(result)
