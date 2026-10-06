"""Independently sum native leaf memberships and compare saved review pages."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def near(actual, expected, absolute=1e-6):
    if not math.isfinite(actual) or not math.isfinite(expected) or abs(actual - expected) > absolute + abs(expected) * 1e-10:
        raise ValueError("independent dynamic saved value mismatch")


def json_identity(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def audit(index_path, index_sha256, expected_identity):
    index_path = Path(index_path)
    if file_sha256(index_path) != index_sha256:
        raise ValueError("external dynamic index pin mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    digest = index.pop("identity_sha256")
    if digest != expected_identity or json_identity(index) != digest:
        raise ValueError("external dynamic index identity mismatch")
    hierarchy, hierarchy_metadata = read_record(index["inputs"]["hierarchy"])
    water, water_metadata = read_record(index["inputs"]["storage"])
    for field in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
        np.testing.assert_array_equal(hierarchy[field], water[field])
    if water_metadata["hierarchy_identity_sha256"] != index["inputs"]["hierarchy"]["expected_identity"]:
        raise ValueError("dynamic input chain mismatch")
    owners = hierarchy["contribution_owner"].ravel()
    valid = hierarchy["valid_mask"].ravel()
    leaf_ids = np.unique(owners[valid])
    memberships = {int(leaf): np.flatnonzero(valid & (owners == leaf)) for leaf in leaf_ids}
    covered = np.concatenate(list(memberships.values()))
    if len(covered) != int(valid.sum()) or len(np.unique(covered)) != len(covered):
        raise ValueError("independent native leaf partition overlap/omission")
    area = hierarchy_metadata["spacing_m"] ** 2
    bed = hierarchy["height_m"].ravel()
    threshold = water_metadata["parameters"]["wet_threshold_m"]
    pins = index["pages"]
    if len(pins) != len(water["depth_m"]):
        raise ValueError("dynamic saved frame count mismatch")
    ledgers = ("rain_volume_m3", "soil_et_m3", "surface_et_m3", "boundary_outflow_m3", "internal_net_m3",
               "storage_change_m3", "balance_residual_m3", "lake_rain_m3", "land_rain_m3", "local_release_m3")
    state_fields = {"surface_volume_m3": ("depth_m", area),
                    "soil_volume_m3": ("soil_mm", area / 1000),
                    "fast_volume_m3": ("fast_mm", area / 1000),
                    "slow_volume_m3": ("slow_mm", area / 1000)}
    comparisons = 0
    budgets = []
    for frame, pin in enumerate(pins):
        if pin["file"] != f"frame-{frame:04d}.json":
            raise ValueError("dynamic page name/order mismatch")
        path = index_path.parent / pin["file"]
        if path.is_symlink() or file_sha256(path) != pin["expected_sha256"] or path.stat().st_size != pin["bytes"]:
            raise ValueError("dynamic page external hash/bytes mismatch")
        page = json.loads(path.read_text(encoding="utf-8"))
        if json_identity(page) != pin["expected_identity"]:
            raise ValueError("dynamic page identity mismatch")
        if page["time_s"] != frame * water_metadata["dt_s"] or page["frame_index"] != frame:
            raise ValueError("dynamic saved time mismatch")
        expected_interval = None if frame == 0 else [(frame - 1) * water_metadata["dt_s"], frame * water_metadata["dt_s"]]
        if page["interval_s"] != expected_interval:
            raise ValueError("dynamic interval semantics mismatch")
        leaves = {record["leaf_id"]: record for record in page["leaves"]}
        if len(leaves) != len(page["leaves"]) or set(leaves) != set(memberships):
            raise ValueError("dynamic exclusive leaf coverage mismatch")
        for leaf, cells in memberships.items():
            record = leaves[leaf]
            total = 0.
            for output_name, (native_name, factor) in state_fields.items():
                expected = math.fsum((water[native_name][frame, cells] * factor).tolist())
                near(record[output_name], expected)
                total += expected
                comparisons += 1
            near(record["total_water_volume_m3"], total)
            wet_cells = cells[water["depth_m"][frame, cells] > threshold]
            if record["wet_count"] != len(wet_cells):
                raise ValueError("native wet count mismatch")
            if not len(wet_cells):
                if record["water_surface_min_m"] is not None or record["water_surface_max_m"] is not None:
                    raise ValueError("dry leaf must have null surface extent")
            else:
                heads = bed[wet_cells] + water["depth_m"][frame, wet_cells]
                near(record["water_surface_min_m"], float(heads.min()), 1e-10)
                near(record["water_surface_max_m"], float(heads.max()), 1e-10)
            if frame:
                for field in ledgers:
                    near(record["interval_ledger_m3"][field], math.fsum(water[field][frame - 1, cells].tolist()))
                    comparisons += 1
            elif record["interval_ledger_m3"] is not None:
                raise ValueError("initial leaf has no prior ledger interval")
        for field, (native_name, factor) in state_fields.items():
            near(page["domain_totals"][field], math.fsum((water[native_name][frame, valid] * factor).tolist()))
        if frame:
            for field in ledgers:
                near(page["domain_interval_ledger_m3"][field], math.fsum(water[field][frame - 1, valid].tolist()))
            soil_names = ("soil_mm", "fast_mm", "slow_mm")
            previous = water["depth_m"][frame - 1] + sum(water[name][frame - 1] for name in soil_names) / 1000
            current = water["depth_m"][frame] + sum(water[name][frame] for name in soil_names) / 1000
            change = math.fsum(((current - previous) * area).tolist())
            rain = math.fsum((water["rain_mm_h"][frame - 1] * (water_metadata["dt_s"] / 3600) * area / 1000).tolist())
            losses = math.fsum((water["soil_et_m3"][frame - 1] + water["surface_et_m3"][frame - 1]).tolist())
            export = math.fsum(water["boundary_outflow_m3"][frame - 1].tolist())
            residual = rain - losses - export - change
            allowed = 1e-6 + abs(losses + export + change) * 1e-10
            diagnostic = page["budget_diagnostic"]["whole_interval"]
            near(diagnostic["residual_m3"], residual, 1e-10)
            near(diagnostic["allowed_m3"], allowed, 1e-12)
            gate_difference = rain - (losses + export + change)
            near(diagnostic["gate_difference_m3"], gate_difference, 1e-10)
            if diagnostic["passed"] != (abs(gate_difference) <= allowed):
                raise ValueError("dynamic interval budget flag differs from original gate")
            budgets.append({"interval": frame - 1, "residual_m3": residual,
                            "gate_difference_m3": gate_difference,
                            "allowed_m3": allowed, "passed": abs(gate_difference) <= allowed})
        for reach in page.get("native_reach_vertices") or []:
            cells = np.asarray(reach["cell_ids"], dtype=np.int64)
            np.testing.assert_array_equal(reach["bed_plus_depth_m"], bed[cells] + water["depth_m"][frame, cells])
            np.testing.assert_array_equal(reach["wet"], water["depth_m"][frame, cells] > threshold)
    if {path.name for path in index_path.parent.glob("frame-*.json")} != {pin["file"] for pin in pins}:
        raise ValueError("dynamic directory has extra or missing frames")
    if not all(item["passed"] for item in budgets) and index["budget_acceptance"]["audit_budget_passed"] is not False:
        raise ValueError("dynamic budget acceptance hides interval rejection")
    return {"schema": "td-independent-catchment-dynamic-review-v1", "index_path": str(index_path.resolve()),
            "index_sha256": index_sha256, "index_identity": expected_identity, "inputs": index["inputs"],
            "algorithm": water_metadata["algorithm"], "valid_cells": int(valid.sum()), "exclusive_leaves": len(memberships),
            "saved_frames": len(pins), "independent_sum_comparisons": comparisons, "value_checks_passed": True,
            "whole_interval_budgets": budgets, "whole_interval_budgets_passed": all(item["passed"] for item in budgets),
            "auditor_sha256": file_sha256(__file__), "solver_advanced": False, "hydraulic_ready": False,
            "limitations": "Native membership and saved-value export audit. A numerical budget rejection remains a rejection; no dynamic refinement, common lake stage or observed channel certification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--expected-identity", required=True)
    args = parser.parse_args()
    report = audit(args.index, args.index_sha256, args.expected_identity)
    output = ROOT / "verification/td-catchment-dynamic-review" / ("independent-" +
             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    print(json.dumps({"output": str(output), "value_checks_passed": report["value_checks_passed"],
                      "whole_interval_budgets_passed": report["whole_interval_budgets_passed"]}))
