"""Frozen TD potential escape forest with independent native D4 flood check."""

from datetime import datetime, timezone
import heapq
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_topology import make_basin_escape_plan as make_basin_escape_plan
from terrain_pipeline.basin_topology import save_basin_escape_plan as save_basin_escape_plan
from terrain_pipeline.basin_topology import load_basin_escape_plan as load_basin_escape_plan
from terrain_pipeline.td_surface_reaches import _plain
from tools.verify_td_basin_spill_network import peak_process_memory


def independent_audit(hierarchy, graph, plan):
    arrays = hierarchy["arrays"]
    bed = arrays["height_m"].ravel()
    leaf = arrays["contribution_owner"].ravel()
    rows, columns = arrays["height_m"].shape
    blocked_leaves = {node["leaf_id"] for node in graph["leaf_nodes"] if arrays["node_unknown_contact"][node["leaf_id"]]
                      or np.any(arrays["protected_mask"].ravel() & (leaf == node["leaf_id"]))}
    usable = arrays["valid_mask"].ravel() & ~np.isin(leaf, list(blocked_leaves))
    levels = np.full(len(bed), np.inf)
    heap = []
    for seed in plan["engineering_seeds"]:
        cell = seed["boundary_cell_id"]
        levels[cell] = bed[cell]
        heapq.heappush(heap, (float(bed[cell]), cell))
    while heap:
        level, cell = heapq.heappop(heap)
        if level != levels[cell]:
            continue
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
        for target in neighbors:
            next_level = max(level, float(bed[target]))
            if usable[target] and next_level < levels[target]:
                levels[target] = next_level
                heapq.heappush(heap, (next_level, target))
    nodes = {node["leaf_id"]: node for node in graph["leaf_nodes"]}
    records = {record["leaf_id"]: record for record in plan["leaves"]}
    stage_by_cell = np.zeros(len(bed))
    for node, record in records.items():
        expected = levels[nodes[node]["terminal_cell_id"]]
        if record["reachable"] != np.isfinite(expected) or record["reachable"] and record["minimum_escape_stage_m"] != expected:
            raise ValueError("native D4 flood terminal escape stage mismatch")
        if record["reachable"]:
            stage_by_cell[leaf == node] = record["minimum_escape_stage_m"]
        parent = record["parent_leaf_id"]
        if parent is not None:
            if records[parent]["settlement_rank"] >= record["settlement_rank"]:
                raise ValueError("escape parent cycle/order mismatch")
            face = record["minimum_face"]["face_index"]
            pair = arrays["face_cells"][face]
            if set(map(int, leaf[pair])) != {node, parent}:
                raise ValueError("escape face does not join parent catchment")
            if record["minimum_escape_stage_m"] != max(records[parent]["minimum_escape_stage_m"], float(max(bed[pair]))):
                raise ValueError("parent minimax recurrence mismatch")
    volumes = np.bincount(leaf[arrays["valid_mask"].ravel()],
        weights=np.maximum(stage_by_cell[arrays["valid_mask"].ravel()] - bed[arrays["valid_mask"].ravel()], 0) * hierarchy["metadata"]["spacing_m"] ** 2,
        minlength=len(arrays["node_parent"]))
    for node, record in records.items():
        if record["reachable"] and not np.isclose(record["raise_to_stage_volume_m3"], volumes[node], rtol=1e-12, atol=1e-6):
            raise ValueError("exclusive volume bincount mismatch")
    return {"passed": True, "method": "independent original D4 priority flood from explicit boundary cells with identical whole-leaf barriers; terminal stages, parent face recurrence and exclusive volume bincount", "checked_leaves": len(records)}


def verify():
    baseline = ROOT / "verification/td-basin-spill-network/run-20261002T095052584723Z"
    bundle_path = baseline / "bundle.json"
    if file_sha256(bundle_path) != "a76b27a55ced5386d0e285250f2a7135f09515a4f72608498ccd1bcd552f40d1":
        raise ValueError("external frozen catchment bundle pin mismatch")
    bundle = json.loads(bundle_path.read_bytes())
    hierarchy_path = ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
    hierarchy_pin = {"path": str(hierarchy_path), "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                     "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"}
    hierarchy = load_basin_hierarchy(**hierarchy_pin)
    graph = bundle["contribution_leaf_graph"]
    leaf = hierarchy["arrays"]["contribution_owner"].ravel()
    blocked = {node["leaf_id"] for node in graph["leaf_nodes"] if hierarchy["arrays"]["node_unknown_contact"][node["leaf_id"]]
               or np.any(hierarchy["arrays"]["protected_mask"].ravel() & (leaf == node["leaf_id"]))}
    seeds = [{"leaf_id": int(leaf[cell]), "boundary_cell_id": int(cell)}
             for cell in hierarchy["arrays"]["boundary_cells"] if int(leaf[cell]) not in blocked and hierarchy["arrays"]["receiver"][cell] < 0]
    result = make_basin_escape_plan(hierarchy, contribution_leaf_graph=graph, engineering_seeds=seeds,
        expected_hierarchy_identity=hierarchy_pin["expected_identity"])
    audit = independent_audit(hierarchy, graph, result)
    output = ROOT / "verification/td-basin-escape-plan" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    path = output / "escape-plan.json"
    save_basin_escape_plan(result, path)
    pin = {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": result["identity_sha256"]}
    load_basin_escape_plan(path, expected_sha256=pin["expected_sha256"], expected_identity=pin["expected_identity"], hierarchy=hierarchy, contribution_leaf_graph=graph)
    memory = peak_process_memory()
    report = {"schema": "td-basin-escape-verification-v1", "inputs": {"hierarchy": hierarchy_pin,
              "catchment_bundle": {"path": str(bundle_path), "expected_sha256": file_sha256(bundle_path), "expected_identity": bundle["identity_sha256"]}},
              "plan": pin, "seed_selection": "explicitly enumerate every saved allowed engineering boundary receiver terminal, at its original bed level; no natural outlet inference",
              "summary": _plain(result["summary"]), "audit": audit, "cold_read_passed": True,
              "resources": {"peak_process_memory": memory, "json_bytes": path.stat().st_size, "within_1GiB": max(memory.values()) <= 1024 ** 3},
              "implementation_sha256": {name: file_sha256(ROOT / name) for name in ('terrain_pipeline/basin_topology.py', "tests/test_td_basin_escape_plan.py", "tools/verify_td_basin_escape_plan.py")}}
    if not report["resources"]["within_1GiB"]:
        publish_bytes(output / "failed-resource.json", json.dumps(report, indent=2).encode())
        raise RuntimeError("resource budget exceeded")
    index = {"schema": "td-basin-escape-review-index-v1", "plan": pin, "inputs": report["inputs"],
             "consumer": {"forest": "leaves[].parent_leaf_id + minimum_face (exact source face, not an invented terminal-to-terminal line)",
                          "catchment_join": "leaves[].stable_leaf_id and leaf_id -> frozen contribution_leaf_graph.leaf_nodes[]",
                          "labels": "potential minimum_escape_stage_m and raise_to_stage_volume_m3; unreachable null preserved"},
             "flags": _plain(result["flags"]), "limitations": result["semantics"]}
    for name, value in (("report.json", report), ("index.json", index)):
        publish_bytes(output / name, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode())
    pins = {name: file_sha256(output / name) for name in ("escape-plan.json", "report.json", "index.json")}
    publish_bytes(output / "pins.json", json.dumps(pins, indent=2).encode())
    print(json.dumps({"output": str(output), "summary": report["summary"], "audit": audit, "resources": report["resources"], "pins": pins}, ensure_ascii=False))


if __name__ == "__main__":
    verify()
