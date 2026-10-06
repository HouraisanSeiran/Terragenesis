"""Fixed synthetic verification; no real terrain, services or publication."""

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.lake_routing import (
    LakeRoutingRecipe, evaluate_lake_routing, load_lake_routing, save_lake_routing,
)


def fixture():
    terrain = np.full((7, 7), 6.)
    terrain[2:5, 2:5] = 1.
    terrain[3, 5] = 3.
    terrain[3, 6] = 2.
    basin = np.zeros(terrain.shape, bool)
    basin[2:5, 2:5] = True
    legal = np.zeros(terrain.shape, bool)
    legal[3, 6] = True
    return dict(height_m=terrain, basin_mask=basin, legal_spill_grid_zx=(3, 5),
                spacing_x_m=1., spacing_z_m=1., origin_x_m=100., origin_z_m=-50.,
                vertical_datum="synthetic-local-m", source_identity="synthetic-nine-cell-v1",
                downstream_path_grid_zx=[(3, 5), (3, 6)], domain_mask=np.ones(terrain.shape, bool),
                protected_mask=np.zeros(terrain.shape, bool), legal_outlet_mask=legal)


def independent_checks(result):
    arrays = result["arrays"]
    recipe = result["input"]["recipe"]
    area = result["input"]["spacing_x_m"] * result["input"]["spacing_z_m"]
    recomputed_storage = np.asarray([
        np.maximum(stage - arrays["height_m"][arrays["basin_mask"]], 0.).sum() * area
        for stage in arrays["stage_m"]])
    recomputed_discharge = np.asarray([
        0. if stage <= recipe["rating_stage_m"][0] else
        np.interp(stage, recipe["rating_stage_m"], recipe["rating_outflow_m3_s"])
        for stage in arrays["stage_m"][1:]])
    np.testing.assert_allclose(recomputed_storage, arrays["storage_m3"], rtol=0, atol=1e-12)
    np.testing.assert_allclose(recomputed_discharge, arrays["step_outflow_m3_s"], rtol=0, atol=1e-12)
    residuals = (np.diff(recomputed_storage) - arrays["step_inflow_volume_m3"] +
                 arrays["step_loss_volume_m3"] + recipe["dt_s"] * recomputed_discharge)
    np.testing.assert_allclose(residuals, arrays["step_residual_m3"], rtol=0, atol=1e-13)
    total = float(recomputed_storage[-1] - recomputed_storage[0] -
                  arrays["step_inflow_volume_m3"].sum() + arrays["step_loss_volume_m3"].sum() +
                  arrays["step_outflow_volume_m3"].sum())
    geometry = float(arrays["water_depth_m"].sum() * area)
    assert abs(geometry - recomputed_storage[-1]) <= 1e-12
    assert np.array_equal(arrays["wet_mask"], arrays["water_depth_m"] > 0)
    assert np.isnan(arrays["water_surface_m"][~arrays["wet_mask"]]).all()
    assert not arrays["wet_mask"][3, 5] and not arrays["wet_mask"][3, 6]
    if result["scenario_feasible"]:
        assert abs(total) <= result["summary"]["cumulative_volume_tolerance_m3"] + 1e-13
    return dict(recomputed_storage_m3=recomputed_storage.tolist(),
                independently_recomputed_step_residual_m3=residuals.tolist(),
                independently_recomputed_total_residual_m3=total,
                geometry_volume_m3=geometry,
                downstream_water_geometry_published=False)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / "verification" / "lake-routing" / f"run-{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    base = LakeRoutingRecipe(3., 1., (2.,) * 10, (0.,) * 10,
                             (3., 4., 5.), (0., 1., 2.), 5.)
    cases = []

    def add(name, recipe=base, expected="scenario_feasible", inputs=None):
        cases.append((name, inputs or fixture(), recipe, expected))

    add("analytic-one-step", replace(base, inflow_m3_s=(2.,), loss_m3_s=(0.,)))
    add("analytic-ten-steps")
    add("below-spill-storage", replace(base, initial_stage_m=1., inflow_m3_s=(9.,), loss_m3_s=(0.,)))
    add("variable-inflow-loss", replace(base, inflow_m3_s=(2., 4., 0., 3.), loss_m3_s=(0., .5, 1., 0.)))
    add("empty-below-bed", replace(base, initial_stage_m=0., inflow_m3_s=(0.,), loss_m3_s=(0.,)))
    add("insufficient-spill-capacity", replace(base, inflow_m3_s=(100.,), loss_m3_s=(0.,)),
        "spill_capacity_exceeded")
    add("curve-exhausted", replace(base, inflow_m3_s=(100.,), loss_m3_s=(0.,),
                                  rating_stage_m=(3., 4.), rating_outflow_m3_s=(0., 1.)),
        "rating_range_exceeded")
    add("dry-loss-prefix", replace(base, initial_stage_m=1., inflow_m3_s=(9., 0.), loss_m3_s=(0., 20.)),
        "dry_loss_exceeds_available_water")
    add("solver-resource", replace(base, max_solver_iterations=1), "solver_resource_limit")
    inputs = fixture()
    inputs["legal_outlet_mask"][:] = False
    add("missing-outlet", expected="missing_legal_outlet", inputs=inputs)
    inputs = fixture()
    inputs["height_m"][2, 5] = 4.
    add("unmodeled-low-shore", expected="unmodeled_low_saddle", inputs=inputs)
    inputs = fixture()
    inputs["protected_mask"][2, 2] = True
    add("protected-basin", expected="basin_domain_or_protection", inputs=inputs)
    inputs = fixture()
    inputs["domain_mask"][3, 6] = False
    add("domain-conflict", expected="path_domain_or_protection", inputs=inputs)
    inputs = fixture()
    inputs["basin_mask"][3, 2:5] = False
    add("disconnected-basin", expected="basin_disconnected", inputs=inputs)
    inputs = fixture()
    inputs["height_m"][3, 2:5] = 4.
    add("split-initial-wet", expected="wet_pool_disconnected", inputs=inputs)
    inputs = fixture()
    inputs["height_m"][3, 2:5] = 2.5
    add("split-final-wet", replace(base, inflow_m3_s=(0., 0.), loss_m3_s=(0., 8.)),
        "wet_pool_disconnected", inputs)
    inputs = fixture()
    inputs["height_m"][3, 6] = 3.
    add("flat-outlet", expected="outlet_not_below_spill", inputs=inputs)
    report = dict(status="diagnostic_not_publishable", verification_passed=False,
                  scope="fixed synthetic finite single-pool engineering scenarios only",
                  generated_utc=stamp, cases={}, invalid_inputs={})
    for name, inputs, recipe, expected in cases:
        original_height = inputs["height_m"].copy()
        result = evaluate_lake_routing(**inputs, recipe=recipe)
        assert result["diagnostic"]["code"] == expected
        assert result["scenario_feasible"] == (expected == "scenario_feasible")
        assert result["status"] == "diagnostic_not_publishable"
        np.testing.assert_array_equal(inputs["height_m"], original_height)
        checks = independent_checks(result)
        if name.startswith("analytic-"):
            count = result["summary"]["completed_steps"]
            expected_stages = 3. + 2. * (1. - .9 ** np.arange(count + 1))
            expected_storage = 9. * (expected_stages - 1.)
            expected_outflow = 2. * count - (expected_storage[-1] - 18.)
            np.testing.assert_allclose(result["arrays"]["stage_m"], expected_stages, rtol=0, atol=2e-9)
            assert abs(result["summary"]["total_outflow_volume_m3"] - expected_outflow) < 2e-8
            checks["analytic"] = dict(stage_recurrence="x_next = 0.9*x_previous + 0.2; x=stage-3",
                                      expected_stage_m=expected_stages.tolist(),
                                      expected_final_storage_m3=float(expected_storage[-1]),
                                      expected_total_outflow_m3=float(expected_outflow))
        path = save_lake_routing(result, destination / f"{name}.npz")
        reloaded = load_lake_routing(path)
        assert reloaded["identity_sha256"] == result["identity_sha256"]
        assert all(not array.flags.writeable for array in reloaded["arrays"].values())
        report["cases"][name] = dict(expected_diagnostic=expected, diagnostic=result["diagnostic"],
                                     scenario_feasible=result["scenario_feasible"], summary=result["summary"],
                                     independent_checks=checks, bundle=path.name,
                                     file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                     identity_sha256=result["identity_sha256"], replay_verified=True)
    invalid = (
        ("grid-resource", fixture(), replace(base, max_grid_cells=48)),
        ("step-resource", fixture(), replace(base, max_steps=9)),
        ("fractional-spill", dict(fixture(), legal_spill_grid_zx=(3.2, 5)), base),
        ("boolean-path", dict(fixture(), downstream_path_grid_zx=[(True, 5), (3, 6)]), base),
    )
    for name, inputs, recipe in invalid:
        try:
            evaluate_lake_routing(**inputs, recipe=recipe)
        except ValueError as error:
            report["invalid_inputs"][name] = dict(rejected_before_copy_or_solve=True,
                                                  reason=str(error), bundle=None)
        else:
            raise AssertionError(f"invalid case accepted: {name}")
    report["verification_passed"] = True
    report["scenario_bundles"] = len(cases)
    with (destination / "report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(dict(report=str(destination / "report.json"),
                          scenario_bundles=len(cases), rejected_invalid_inputs=len(invalid),
                          verification_passed=True), ensure_ascii=False))


if __name__ == "__main__":
    main()
