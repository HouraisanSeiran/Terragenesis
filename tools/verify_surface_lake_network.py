"""Fixed synthetic joint scenarios, real downstream gates, no publication."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_surface_lake_network import high_tailwater_case, joint_case
from terrain_pipeline.surface_domain import SurfaceNetworkBudget
from terrain_pipeline.lake import evaluate_surface_lake_network as evaluate_surface_lake_network
from terrain_pipeline.lake import load_surface_lake_network as load_surface_lake_network
from terrain_pipeline.lake import save_surface_lake_network as save_surface_lake_network
from terrain_pipeline.lake import surface_lake_network_hash as surface_lake_network_hash
from terrain_pipeline.lake import validate_surface_lake_network as validate_surface_lake_network


def independent_checks(result):
    lake = result["inputs"]["lake_inputs"]
    params = result["inputs"]["plan"]["identity"]["parameters"]
    arrays = result["committed_lake_arrays"]
    area = lake["spacing_x_m"] * lake["spacing_z_m"]
    volumes = np.asarray([np.maximum(stage - lake["height_m"][lake["basin_mask"]], 0.).sum() * area
                          for stage in arrays["stage_m"]])
    np.testing.assert_allclose(volumes, arrays["storage_m3"], rtol=0, atol=1e-12)
    original = result["inputs"]["plan"]["arrays"]
    local = original["discharge_m3_s"].ravel().copy()
    for donor, target in enumerate(original["receiver"]):
        if target >= 0:
            local[target] -= original["discharge_m3_s"].flat[donor]
    assert np.all(local >= 0)
    base_local_total = float(local.sum())
    dt = lake["recipe"]["dt_s"]
    checks = []
    for index, row in enumerate(result["ledger"]):
        flow = result["trace"][index]["lake_outflow_m3_s"]
        expected_local = local.copy()
        seam = result["inputs"]["seam"]
        source_column = int((seam["world_x_m"] - params["origin_x_m"]) / params["spacing_x_m"])
        source_row = int((seam["world_z_m"] - params["origin_z_m"]) / params["spacing_z_m"])
        expected_local[source_row * original["source_height_m"].shape[1] + source_column] += flow
        expected_discharge = expected_local.copy()
        for donor in original["order"][::-1]:
            target = original["receiver"][donor]
            if target >= 0:
                expected_discharge[target] += expected_discharge[donor]
        step = result["trace"][index]
        actual = step["recomputed_plan"]["arrays"]["discharge_m3_s"]
        np.testing.assert_allclose(actual.ravel(), expected_discharge, rtol=0, atol=1e-12)
        river_outlet = float(expected_discharge[original["outlet_mask"].ravel()].sum())
        if step["recovery"] is not None:
            final = step["recovery"]["final_plan"]["arrays"]
            assert abs(float(final["discharge_m3_s"][final["outlet_mask"]].sum()) - river_outlet) < 1e-12
        lake_in = lake["recipe"]["inflow_m3_s"][index]
        loss = lake["recipe"]["loss_m3_s"][index]
        delta_volume = volumes[index + 1] - volumes[index]
        lake_error = delta_volume - dt * (lake_in - loss - flow)
        river_error = river_outlet - base_local_total - flow
        combined = delta_volume + dt * river_outlet - dt * (lake_in - loss + base_local_total)
        assert abs(combined) <= row["combined_tolerance_m3"] + 1e-13
        checks.append(dict(step=index, lake_residual_m3=float(lake_error),
                           river_residual_m3_s=float(river_error), combined_residual_m3=float(combined),
                           independently_accumulated_outlet_m3_s=river_outlet,
                           original_local_total_m3_s=base_local_total))
    summary = result["summary"]
    aggregate = (volumes[-1] - volumes[0] + summary["total_downstream_outlet_m3"] -
                 summary["total_lake_inflow_m3"] + summary["total_lake_loss_m3"] - summary["total_downstream_local_m3"])
    assert abs(aggregate) <= summary["total_combined_tolerance_m3"] + 1e-12
    assert abs(float(arrays["water_depth_m"].sum()) * area - volumes[-1]) < 1e-12
    assert np.isnan(arrays["water_surface_m"][~arrays["wet_mask"]]).all()
    return dict(committed_storage_recomputed_m3=volumes.tolist(), steps=checks,
                independently_recomputed_aggregate_residual_m3=float(aggregate),
                connector_geometry_generated=False, river_storage_and_propagation_omitted=True)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / "verification" / "surface-lake-network" / f"run-{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    cases = [("two-step-positive", joint_case(), "transfer_feasible"),
             ("zero-no-flow", joint_case((0., 0.), 8., 0.), "transfer_feasible"),
             ("lake-capacity-failed", joint_case((100.,)), "lake_scenario_failed"),
             ("positive-below-threshold", joint_case((.01,), original_local=0.), "positive_outflow_without_active_path"),
             ("high-tailwater-positive", high_tailwater_case(False), "spill_submerged_one_way_invalid"),
             ("high-tailwater-zero", high_tailwater_case(True), "spill_submerged_one_way_invalid")]

    def add(name, case, expected):
        cases.append((name, case, expected))

    case = joint_case()
    case["recipe"] = replace(case["recipe"], max_total_attempts=1)
    add("attempt-prefix", case, "joint_recovery_resource_exhausted")
    case = joint_case()
    case["recipe"] = replace(case["recipe"], max_total_fine_work=3721)
    add("fine-work-prefix", case, "joint_recovery_resource_exhausted")
    case = joint_case()
    case["recipe"] = replace(case["recipe"], max_total_lake_work=150)
    add("lake-work-prefix", case, "joint_lake_work_exhausted")
    case = joint_case()
    case["recipe"] = replace(case["recipe"], max_retained_bytes=500000)
    add("retained-bytes", case, "joint_retained_memory_exhausted")
    case = joint_case()
    case["coarse_protected"][1, 3] = True
    add("protected-seam", case, "seam_domain_or_protection")
    case = joint_case()
    case["coarse_domain"][1, 3] = False
    add("domain-seam", case, "seam_domain_or_protection")
    case = joint_case()
    case["coarse_protected"][3, 3] = True
    protected = case["fine"].protected_mask.copy()
    protected[30, 30] = True
    case["fine"] = replace(case["fine"], protected_mask=protected)
    add("downstream-protected", case, "downstream_recovery_failed")
    case = joint_case()
    case["budget"] = SurfaceNetworkBudget(2., 0., 0.)
    add("downstream-budget", case, "downstream_recovery_failed")
    case = joint_case()
    case["lake_inputs"]["basin_mask"][4, 5] = True
    case["lake_inputs"]["height_m"][4, 5] = 8.
    add("wet-overlap-prefix", case, "lake_river_wet_overlap")
    report = dict(verification_passed=False, status="diagnostic_not_publishable",
                  generated_utc=stamp, scope="synthetic finite one-way scenario sequence, not evolving erosion",
                  cases={}, invalid_inputs={}, semantic_tampering={})
    positive = None
    for name, case, expected in cases:
        result = evaluate_surface_lake_network(**case)
        assert result["diagnostic"]["code"] == expected
        assert result["transfer_feasible"] == (expected == "transfer_feasible")
        checks = independent_checks(result)
        if name == "two-step-positive":
            positive = result
            first, second = result["trace"]
            evidence = {}
            for field in ("bed_cut_m", "wet_mask", "final_surface_m"):
                arrays = [step["recovery"]["surface"]["arrays"][field] for step in (first, second)]
                changed = int(np.count_nonzero(arrays[0] != arrays[1]))
                assert changed > 0
                evidence[field + "_changed_cells"] = changed
            assert first["lake_outflow_m3_s"] != second["lake_outflow_m3_s"]
            checks["recalculation_evidence"] = evidence
        path = save_surface_lake_network(result, destination / f"{name}.npz")
        loaded = load_surface_lake_network(path)
        assert loaded["identity_sha256"] == result["identity_sha256"]
        independent_checks(loaded)
        report["cases"][name] = dict(bundle=path.name, diagnostic=result["diagnostic"],
            transfer_feasible=result["transfer_feasible"], summary=result["summary"],
            independent_checks=checks, semantic_replay_verified=True,
            actual_recovery_used=True, controlled_mock_used=False,
            outlet_evidence="caller_supplied_engineering_boundary_not_natural_mouth_certification",
            identity_sha256=result["identity_sha256"], file_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    case = joint_case()
    case["seam"] = replace(case["seam"], world_x_m=.01)
    invalid = [("coordinate-unaligned", case)]
    case = joint_case()
    case["plan"] = deepcopy(case["plan"])
    case["plan"]["arrays"]["discharge_m3_s"][2, 3] += 1.
    invalid.append(("original-q-tampered", case))
    for name, case in invalid:
        try:
            evaluate_surface_lake_network(**case)
        except ValueError as error:
            report["invalid_inputs"][name] = dict(rejected=True, reason=str(error), bundle=None)
        else:
            raise AssertionError(name)
    for name in ("forged-transfer", "forged-step-q"):
        forged = deepcopy(positive)
        if name == "forged-transfer":
            forged["transfer_feasible"] = False
        else:
            forged["trace"][0]["recomputed_plan"]["arrays"]["discharge_m3_s"][3, 3] += 1.
        forged["identity_sha256"] = surface_lake_network_hash(forged)
        try:
            validate_surface_lake_network(forged)
        except ValueError as error:
            report["semantic_tampering"][name] = dict(rejected_after_rehash=True, reason=str(error))
        else:
            raise AssertionError(name)
    report["verification_passed"] = True
    report["scenario_bundles"] = len(cases)
    with (destination / "report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(dict(report=str(destination / "report.json"), scenario_bundles=len(cases),
                          rejected_invalid_inputs=len(invalid), rejected_rehashed_tampering=2,
                          verification_passed=True), ensure_ascii=False))


if __name__ == "__main__":
    main()
