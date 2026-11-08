"""Independent original-grid priority flood for catchment potential escape planning."""

import argparse
from datetime import datetime, timezone
import heapq
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_surface_reaches import read_json


def audit(index_path, index_sha256, plan_record=None):
    index = read_json(index_path, index_sha256)
    hierarchy, metadata = read_record(index["inputs"]["hierarchy"])
    bundle = read_json(index["spills"]["path"], index["spills"]["expected_sha256"])
    graph = bundle["contribution_leaf_graph"]
    leaves = hierarchy["contribution_owner"].ravel()
    valid = hierarchy["valid_mask"].ravel()
    bed = hierarchy["height_m"].ravel()
    protected = hierarchy["protected_mask"].ravel()
    nodes = graph["leaf_nodes"]
    allowed = valid & ~protected
    allowed[valid] &= ~hierarchy["node_unknown_contact"][leaves[valid]]
    blocked_leaves = np.unique(leaves[protected & valid])
    allowed &= ~np.isin(leaves, blocked_leaves)
    roots = [node["terminal_cell_id"] for node in nodes if node["terminal_kind"] == "engineered_open" and allowed[node["terminal_cell_id"]]]
    levels = np.full(len(bed), np.inf)
    settled = np.zeros(len(bed), bool)
    queue = []
    for cell in roots:
        levels[cell] = bed[cell]
        heapq.heappush(queue, (float(bed[cell]), int(cell)))
    rows, columns = hierarchy["height_m"].shape
    while queue:
        level, cell = heapq.heappop(queue)
        if settled[cell] or level != levels[cell]:
            continue
        settled[cell] = True
        row, column = divmod(cell, columns)
        for next_row, next_column in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
            if not 0 <= next_row < rows or not 0 <= next_column < columns:
                continue
            target = next_row * columns + next_column
            if not allowed[target] or settled[target]:
                continue
            candidate = max(level, float(bed[target]))
            if candidate < levels[target]:
                levels[target] = candidate
                heapq.heappush(queue, (candidate, target))
    results = []
    area = metadata["spacing_m"] ** 2
    for node in nodes:
        leaf = node["leaf_id"]
        terminal = node["terminal_cell_id"]
        level = levels[terminal]
        cells = valid & (leaves == leaf)
        volume = float(np.maximum(level - bed[cells], 0).sum() * area) if np.isfinite(level) else None
        results.append({"leaf_id": leaf, "stable_leaf_id": node["stable_leaf_id"], "terminal_cell_id": terminal,
                        "terminal_kind": node["terminal_kind"], "reachable": bool(np.isfinite(level)),
                        "escape_stage_m": float(level) if np.isfinite(level) else None,
                        "exclusive_volume_at_escape_m3": volume, "area_m2": float(cells.sum() * area)})
    plan_checks = None
    if plan_record is not None:
        plan = read_json(plan_record["path"], plan_record["expected_sha256"])
        from tools.audit_td_surface_reaches import identity
        if plan["identity_sha256"] != plan_record["expected_identity"] or identity(plan) != plan_record["expected_identity"]:
            raise ValueError("escape plan identity mismatch")
        actual = {record["leaf_id"]: record for record in plan["leaves"]}
        if set(actual) != {record["leaf_id"] for record in results}:
            raise ValueError("plan leaf coverage mismatch")
        if sorted(seed["boundary_cell_id"] for seed in plan["engineering_seeds"]) != sorted(roots):
            raise ValueError("engineering root coverage mismatch")
        parent_faces = 0
        for reference in results:
            record = actual[reference["leaf_id"]]
            if record["reachable"] != reference["reachable"] or record["minimum_escape_stage_m"] != reference["escape_stage_m"]:
                raise ValueError("grid-versus-quotient minimum escape stage mismatch")
            expected_volume = reference["exclusive_volume_at_escape_m3"]
            if expected_volume is None:
                if record["raise_to_stage_volume_m3"] is not None or record["parent_leaf_id"] is not None:
                    raise ValueError("unreachable plan invented storage/parent")
                continue
            np.testing.assert_allclose(record["raise_to_stage_volume_m3"], expected_volume, rtol=1e-13, atol=1e-8)
            parent = record["parent_leaf_id"]
            if parent is None:
                if record["root_boundary_cell_id"] not in roots:
                    raise ValueError("forest root lacks explicit boundary seed")
            else:
                evidence = record["minimum_face"]
                face = evidence["face_index"]
                pair = hierarchy["face_cells"][face]
                if set(map(int, leaves[pair])) != {parent, reference["leaf_id"]} or evidence["face_cell_ids"] != pair.tolist():
                    raise ValueError("parent face does not connect exclusive catchments")
                if actual[parent]["settlement_rank"] >= record["settlement_rank"]:
                    raise ValueError("parent settlement cycle")
                if max(actual[parent]["minimum_escape_stage_m"], float(bed[pair].max())) != record["minimum_escape_stage_m"]:
                    raise ValueError("parent path minimax recurrence mismatch")
                if actual[parent]["root_boundary_cell_id"] != record["root_boundary_cell_id"]:
                    raise ValueError("forest root propagation mismatch")
                parent_faces += 1
        plan_checks = {"pin": plan_record, "passed": True, "parent_faces": parent_faces, "leaf_stages_and_volumes_checked": len(actual)}
    return {"schema": "td-independent-grid-escape-reference-v1", "utc": datetime.now(timezone.utc).isoformat(),
            "index": {"path": str(index_path), "expected_sha256": index_sha256}, "leaves": results,
            "reference": "priority flood on original D4 cell graph, seeded only at explicitly engineered-open receiver terminals",
            "root_count": len(roots), "settled_cells": int(settled.sum()),
            "reachable_leaves": sum(node["reachable"] for node in results),
            "exclusive_volume_at_escape_m3": sum(node["exclusive_volume_at_escape_m3"] or 0 for node in results),
            "bed_unchanged": True, "solver_advanced": False, "hydraulic_ready": False, "natural_outlet_verified": False,
            "auditor_sha256": file_sha256(__file__),
            "plan_comparison": plan_checks,
            "limitations": "Static minimum possible escape stage with source unknown/protection policy. Volume to stage is exclusive hypothetical fill, not observed storage, actual fill modification or required rain. No generated water, channel path or dynamic onset."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-report", type=Path)
    parser.add_argument("--plan-report-sha256")
    arguments = parser.parse_args()
    if bool(arguments.plan_report) != bool(arguments.plan_report_sha256):
        raise ValueError("plan report and external SHA must be supplied together")
    plan_record = None if arguments.plan_report is None else read_json(arguments.plan_report, arguments.plan_report_sha256)["plan"]
    report = audit(arguments.index, arguments.index_sha256, plan_record)
    publish_bytes(arguments.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode())
    print(json.dumps({key: report[key] for key in ("root_count", "settled_cells", "reachable_leaves", "exclusive_volume_at_escape_m3")}))
