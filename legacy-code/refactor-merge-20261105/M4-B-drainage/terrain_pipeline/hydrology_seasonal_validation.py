"""CPU-only bounded seasonal evidence for frozen planning candidates."""

from dataclasses import asdict, replace
import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.hydrology_seasonal import (
    LEDGER_KEYS, SeasonalBalanceError, SeasonalConfig, _inputs, _year,
    load_seasonal_water_balance, save_seasonal_water_balance,
    simulate_seasonal_water_balance, validate_seasonal_water_balance,
)


def _write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False))


def failure_evidence(plan, error, config, output):
    """Store one genuine nonperiodic year and cold-read every step water account."""
    report = dict(error.diagnostics)
    report["pet_calibration"] = "illustrative temperature-index PET; not calibrated or observed"
    lower = report.get("lower_level_m")
    if lower is None:
        _write_report(output.with_suffix(".json"), report)
        return report
    height, owner, domains, lakes, area, climate = _inputs(plan, config, None)
    column, lake = next(iter(lakes.items()))
    volumes = np.zeros(len(domains))
    diagnostic_level = max(float(lake.beds[0]), lower - 10.0)
    volumes[column] = lake.volume(diagnostic_level)
    report["diagnostic_initial_lake_level_m"] = diagnostic_level
    soil = np.zeros(height.shape)
    previous_x = previous_residual = None
    used = 0
    for unused in range(min(12, config.max_years - report["annual_map_evaluations"] - 1)):
        before = soil.copy()
        soil, _, *_ = _year(height, owner, domains, lakes, area, climate, config, soil, volumes.copy())
        used += 1
        residual = soil - before
        if np.max(np.abs(residual)) <= config.convergence_depth_mm:
            break
        if previous_residual is not None:
            denominator = residual - previous_residual
            usable = np.abs(denominator) > 1e-10
            proposal = np.zeros_like(soil)
            np.divide(residual * (before - previous_x), denominator, out=proposal, where=usable)
            proposal = before - proposal
            good = usable & (proposal >= 0) & (proposal <= config.soil_capacity_mm)
            soil = np.where(good, proposal, soil)
        previous_x, previous_residual = before, residual
    soil, end, monthly, soil_months, lake_months, steps, inventories = _year(
        height, owner, domains, lakes, area, climate, config, soil, volumes.copy(), retain=True)
    arrays = {key: np.array([step[key] for step in steps]) for key in LEDGER_KEYS}
    arrays["inventory_m3"] = np.array(inventories)
    arrays["soil_mm"] = np.array(soil_months)
    arrays["lake_volume_m3"] = np.array(lake_months)
    arrays["precipitation_mm"] = climate["precipitation_mm"]
    arrays["potential_et_mm"] = climate["potential_et_mm"]
    arrays["metadata_json"] = np.array(json.dumps({"status": "nonperiodic_diagnostic_only",
          "source_plan_identity_sha256": plan["identity_sha256"], "parameters": asdict(config)}, allow_nan=False))
    with output.with_suffix(".npz").open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    # This audit reads the written arrays; it does not rerun climate or time.
    with np.load(output.with_suffix(".npz"), allow_pickle=False) as saved:
        rain = saved["land_rain_m3"] + saved["lake_rain_m3"]
        loss = saved["land_et_m3"] + saved["lake_evaporation_m3"] + saved["coastal_outflow_m3"]
        delta = saved["soil_change_m3"] + saved["lake_change_m3"]
        residual = rain - loss - delta
        inventory_residual = np.diff(saved["inventory_m3"], axis=0) - delta
        rain_total = np.array([saved["precipitation_mm"][:, owner == d["domain_id"]].sum() * area / 1000 for d in domains])
        partition_residual = rain.sum(axis=0) - rain_total
        finite = all(np.isfinite(saved[key]).all() for key in saved.files if key != "metadata_json")
        annual_inventory = saved["inventory_m3"][-1] - saved["inventory_m3"][0]
    tolerance = max(1e-6, float(rain.max()) * 1e-9)
    cold_passed = finite and np.max(np.abs(residual)) <= tolerance and np.max(np.abs(inventory_residual)) <= tolerance and np.max(np.abs(partition_residual)) <= tolerance * len(steps)
    report["diagnostic_evaluations"] = used + 1
    report["cold_annual_account_audit"] = {"status": "passed" if cold_passed else "failed",
        "meaning": "nonperiodic annual arithmetic verified; seasonal acceptance remains failed",
        "max_step_residual_m3": float(np.max(np.abs(residual))),
        "max_step_inventory_residual_m3": float(np.max(np.abs(inventory_residual))),
        "rain_partition_residual_m3": partition_residual.tolist(),
        "annual_inventory_change_m3": annual_inventory.tolist(), "finite": finite}
    _write_report(output.with_suffix(".json"), report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    plan = load_plan(args.plan)
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    failures = []
    results = []
    for substeps in (1, 2):
        config = replace(SeasonalConfig(), substeps_per_day=substeps)
        try:
            result = simulate_seasonal_water_balance(plan, config)
            path = folder / f"seasonal-{substeps}step.npz"
            save_seasonal_water_balance(plan, result, path)
            cold = load_seasonal_water_balance(plan, path)
            report = validate_seasonal_water_balance(plan, cold)
            report["metadata"] = cold["metadata"]
            report["lake_level_m"] = cold["lake_level_m"][:, 1].tolist()
            _write_report(folder / f"seasonal-{substeps}step-audit.json", report)
            results.append(cold)
        except SeasonalBalanceError as error:
            failures.append(failure_evidence(plan, error, config, folder / f"seasonal-failure-{substeps}step"))
    if failures:
        _write_report(folder / "seasonal-step-comparison.json", {
            "status": "failed_at_least_one_step", "source_plan_identity_sha256": plan["identity_sha256"],
            "failures": [{"substeps_per_day": f["parameters"]["substeps_per_day"],
                          "annual_map_evaluations": f.get("annual_map_evaluations"), "reason": f["reason"],
                          "lower_level_m": f.get("lower_level_m")} for f in failures],
            "climate_and_pet_parameters_changed": False})
        print("actual failure and nonperiodic cold accounts retained")
        return
    daily, halfday = results
    _write_report(folder / "seasonal-step-comparison.json", {
        "status": "both_periodic_accounts_verified", "scope": "development candidate; planning visuals/catalog still need acceptance",
        "max_monthly_lake_level_difference_m": float(np.max(np.abs(daily["lake_level_m"][:, 1] - halfday["lake_level_m"][:, 1]))),
        "daily_monthly_lake_level_m": daily["lake_level_m"][:, 1].tolist(),
        "halfday_monthly_lake_level_m": halfday["lake_level_m"][:, 1].tolist(),
        "pet_calibration": "illustrative temperature-index PET; not calibrated or observed"})
    print("daily/halfday periodic accounts saved and cold-audited")


if __name__ == "__main__":
    main()
