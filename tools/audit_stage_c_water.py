"""Independent volume reductions and sampled delayed-edge propagation checks."""

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.dem_domain import load_dem_candidate
from tools import verify_real_dem_rainfall_routing as exporter
from tools.verify_real_dem_outlet_classification import DEFAULT_CANDIDATE, canonical_bytes, check_unchanged, read_json, source_record


def audit_scenario(candidate, flat, result, sample_count=32):
    ids = result["valid_cell_ids"]
    grid = candidate["manifest"]["identity"]["grid"]
    area = grid["spacing_x_m"] * grid["spacing_z_m"]
    dt_s = result["metadata"]["dt_s"]
    receiver = flat["receiver"].ravel()[ids]
    targets = np.searchsorted(ids, np.maximum(receiver, 0))
    routed = receiver >= 0
    targets[~routed] = -1
    rows, cols = np.divmod(ids, candidate["arrays"]["height_m"].shape[1])
    target_rows, target_cols = np.divmod(np.maximum(receiver, 0), candidate["arrays"]["height_m"].shape[1])
    lengths = np.hypot((target_rows - rows) * grid["spacing_z_m"], (target_cols - cols) * grid["spacing_x_m"])
    lengths[~routed] = grid["spacing_x_m"]
    fraction = -np.expm1(-dt_s * result["metadata"]["speed_m_s"] / lengths)
    external = np.isin(ids, result["metadata"]["engineering_terminal_ids"])
    fraction[~routed & ~external] = 0
    chosen = np.unique(np.concatenate((np.linspace(0, len(ids) - 1, sample_count).astype(int),
                                      np.flatnonzero(external)[:8])))
    donors = {int(cell): np.flatnonzero(targets == cell) for cell in chosen}
    max_equation_error = 0.
    steps = len(result["rain_mm_h"])
    errors = []
    initial = result["metadata"]["parameters"]
    initial_stores = len(ids) * area / 1000 * sum(initial["initial_" + name + "_mm"] for name in ("soil", "fast", "slow"))
    final_stores = math.fsum(math.fsum(result["final_" + name + "_mm"]) for name in ("soil", "fast", "slow")) * area / 1000
    for step in range(steps):
        storage = result["channel_storage"][step]
        after = result["channel_storage"][step + 1]
        local = result["local_volume"][step]
        for cell in chosen:
            inflow = math.fsum(float(storage[donor] * fraction[donor]) for donor in donors[int(cell)])
            expected = float(storage[cell]) * (1 - float(fraction[cell])) + inflow + float(local[cell])
            max_equation_error = max(max_equation_error, abs(float(after[cell]) - expected))
        rain_volume = float(result["rain_mm_h"][step]) * dt_s / 3600 * len(ids) * area / 1000
        local_sum = math.fsum(local)
        change = math.fsum(after) - math.fsum(storage)
        discharge = math.fsum(float(storage[cell] * fraction[cell]) for cell in np.flatnonzero(external))
        errors.append(local_sum - change - discharge)
        np.testing.assert_allclose(rain_volume, result["ledger"]["rain_volume_m3"][step], rtol=1e-12, atol=1e-7)
        np.testing.assert_allclose(discharge, result["ledger"]["engineering_discharge_m3"][step], rtol=1e-12, atol=1e-7)
    rainfall = math.fsum(result["ledger"]["rain_volume_m3"])
    et = math.fsum(result["ledger"]["et_volume_m3"])
    external_volume = math.fsum(result["ledger"]["engineering_discharge_m3"])
    final_channel = math.fsum(result["channel_storage"][-1])
    residual = initial_stores + rainfall - final_stores - et - external_volume - final_channel
    if abs(residual) > 1e-6 + rainfall * 1e-12 or max(abs(value) for value in errors) > 1e-6 + rainfall * 1e-12:
        raise ValueError("independent whole-system/one-step conservation failed")
    if max_equation_error > 1e-7:
        raise ValueError("sampled scalar delayed propagation failed")
    return {"initial_soil_fast_slow_m3": initial_stores, "rainfall_m3": rainfall,
            "final_soil_fast_slow_m3": final_stores, "et_m3": et, "engineering_discharge_m3": external_volume,
            "final_channel_storage_m3": final_channel, "whole_period_residual_m3": residual,
            "max_step_channel_residual_m3": max(abs(value) for value in errors),
            "scalar_sample_cells": len(chosen), "scalar_equation_checks": len(chosen) * steps,
            "max_sampled_equation_error_m3": max_equation_error,
            "verified_external_m3": 0., "natural_outlet_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rainfall-package", type=Path, required=True)
    args = parser.parse_args()
    report = exporter.verify_package(args.rainfall_package)
    candidate = load_dem_candidate(DEFAULT_CANDIDATE, verify_source=True)
    with np.load(exporter.DEFAULT_FLAT / "network.npz", allow_pickle=False) as archive:
        flat = {name: archive[name] for name in archive.files}
    records = [source_record(args.rainfall_package / "manifest.json"), source_record(DEFAULT_CANDIDATE), source_record(__file__)]
    audits = {}
    curves = {}
    for name in exporter.SCENARIOS:
        records.append(source_record(args.rainfall_package / (name + ".npz")))
        result = exporter.load_saved(args.rainfall_package / (name + ".npz"), report["scenarios"][name], len(np.flatnonzero(candidate["arrays"]["valid_mask"])))
        audits[name] = audit_scenario(candidate, flat, result)
        curves[name] = {key: value.copy() for key, value in result["ledger"].items()}
        del result
    check_unchanged(records)
    output = ROOT / "verification/real-dem-rainfall-independent-review" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    for axis, name in zip(axes, exporter.SCENARIOS):
        ledger = curves[name]
        axis.plot(np.arange(exporter.STEPS), ledger["rain_volume_m3"] / exporter.DT_S, label="rain input (m3/s)")
        axis.plot(np.arange(exporter.STEPS), ledger["local_runoff_m3"] / exporter.DT_S, label="local runoff (m3/s)")
        axis.plot(np.arange(exporter.STEPS), ledger["engineering_discharge_m3"] / exporter.DT_S, label="engineering boundary discharge (m3/s)")
        axis.set_title(name + "; no calibrated flood or solved river stage")
        axis.set_xlabel("interval start (hours)")
        axis.legend()
    figure.savefig(output / "rainfall-propagation.png", dpi=140)
    plt.close(figure)
    result = {"inputs": records, "method": "math.fsum_global_reductions_and_scalar_donor_equations",
              "scenarios": audits, "source_unchanged": True, "natural_outlet_verified": False}
    (output / "independent-review.json").write_bytes(canonical_bytes(result))
    print(str(output))


if __name__ == "__main__":
    main()
