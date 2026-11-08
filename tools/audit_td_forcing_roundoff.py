"""Isolate forcing roundoff without transport against extended precision."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import importlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters


def reference_half(state, rainfall_rate, duration, runoff, config):
    depth, soil, fast, slow = state
    hours = Decimal.from_float(float(duration)) / 3600
    rain = Decimal.from_float(float(rainfall_rate)) * hours
    land = Decimal(0) if depth > config["wet_threshold_m"] else rain
    lake = rain - land
    infiltration = min(land, Decimal.from_float(runoff.infiltration_capacity_mm_h) * hours,
                       max(Decimal(0), Decimal.from_float(runoff.soil_capacity_mm) - soil))
    soil += infiltration
    soil_et = min(soil, Decimal.from_float(runoff.potential_et_mm_h) * hours)
    soil -= soil_et
    percolation = min(soil, Decimal.from_float(runoff.percolation_mm_h) * hours)
    soil -= percolation
    releases = []
    stores = []
    for storage, incoming, tau in ((fast, land - infiltration, runoff.fast_tau_s),
                                   (slow, percolation, runoff.slow_tau_s)):
        ratio = Decimal.from_float(float(duration)) / Decimal.from_float(tau)
        fraction = 1 - (-ratio).exp()
        inflow_fraction = (ratio / 2 - ratio ** 2 / 6 + ratio ** 3 / 24
                          if ratio < 1e-4 else 1 - fraction / ratio)
        released = storage * fraction + incoming * inflow_fraction
        releases.append(released)
        stores.append(storage + incoming - released)
    depth += (lake + sum(releases)) / 1000
    surface_et = min(depth, Decimal.from_float(config["surface_evaporation_mm_h"]) * hours / 1000)
    depth -= surface_et
    return (depth, soil, *stores), rain / 1000, soil_et / 1000 + surface_et


def audit(version, substep):
    if version not in ("v5", "v6", "compensated") or substep not in (5., 2.5):
        raise ValueError("explicit frozen forcing version and step required")
    module_name = 'terrain_pipeline.basin_storage' if version == "compensated" else "terrain_pipeline.td_basin_storage_" + version
    solver = importlib.import_module(module_name)
    runoff = RunoffParameters()
    config = {"wet_threshold_m": 1e-9, "surface_evaporation_mm_h": .15}
    area = 900
    keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3",
            "local_release_m3", "surface_et_m3")
    cases = []
    for scenario in ("dry", "ordinary", "strong"):
        state = [np.array([value], dtype=np.float64) for value in
                 (0., runoff.initial_soil_mm, runoff.initial_fast_mm, runoff.initial_slow_mm)]
        reference = tuple(Decimal.from_float(float(values[0])) for values in state)
        ledgers = {key: np.zeros((24, 1)) for key in keys}
        errors = {key: np.zeros(1) for key in ("depth", "soil", "fast", "slow") + keys}
        frames = []
        for frame in range(24):
            for key in keys:
                errors[key][:] = 0
            rain_rate = 0. if frame >= 6 or scenario == "dry" else (10. if scenario == "ordinary" else 30.)
            before = float(state[0][0] + sum(values[0] for values in state[1:]) / 1000) * area
            reference_before = (reference[0] + sum(reference[1:]) / 1000) * area
            reference_rain = Decimal(0)
            reference_loss = Decimal(0)
            for half in range(round(7200 / substep)):
                arguments = (*state, np.array([rain_rate]), substep / 2, runoff, config, area, ledgers, frame)
                state = list(solver.forcing(*arguments, errors) if version == "compensated" else solver._forcing(*arguments))
                if any(np.any(values < 0) or not np.isfinite(values).all() for values in state):
                    raise ValueError("isolated forcing produced negative/nonfinite inventory")
                reference, rain, loss = reference_half(reference, rain_rate, substep / 2, runoff, config)
                reference_rain += rain * area
                reference_loss += loss * area
            after = float(state[0][0] + sum(values[0] for values in state[1:]) / 1000) * area
            actual_rain = ledgers["rain_volume_m3"][frame, 0]
            actual_loss = ledgers["soil_et_m3"][frame, 0] + ledgers["surface_et_m3"][frame, 0]
            residual = actual_rain - actual_loss - (after - before)
            reference_after = (reference[0] + sum(reference[1:]) / 1000) * area
            reference_residual = reference_rain - reference_loss - (reference_after - reference_before)
            frames.append({"frame": frame, "isolated_cell_residual_m3": residual,
                           "identical_65536_cells_residual_m3": residual * 65536,
                           "extended_precision_residual_m3": float(reference_residual),
                           "state_difference": [float(Decimal.from_float(float(actual[0])) - expected) for actual, expected in zip(state, reference)]})
        cases.append({"scenario": scenario, "frames": frames,
                      "max_scaled_residual_m3": max(abs(frame["identical_65536_cells_residual_m3"]) for frame in frames)})
    return {"schema": "td-forcing-roundoff-isolation-v1", "version": version, "substep_s": substep,
            "reference": "Decimal 40 significant digits; unchanged ordered forcing equations",
            "cases": cases, "forcing_parameters": config,
            "solver_sha256": file_sha256(ROOT / (module_name.replace(".", "/") + ".py")),
            "auditor_sha256": file_sha256(__file__), "threshold_changed": False,
            "full_domain_certification": False, "hydraulic_ready": False,
            "limitations": "One isolated cell, unchanged forcing equations, no transport. Scaling is an identical-cell diagnostic, not a TD rerun or a continuous soil ODE certification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("v5", "v6", "compensated"), required=True)
    parser.add_argument("--substep", type=float, choices=(5., 2.5), default=2.5)
    args = parser.parse_args()
    with localcontext() as context:
        context.prec = 40
        report = audit(args.version, args.substep)
    output = ROOT / "verification/td-basin-generation" / ("independent-forcing-roundoff-" +
             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"output": str(output), "reference": report["reference"],
                      "max_scaled_residuals_m3": {case["scenario"]: case["max_scaled_residual_m3"] for case in report["cases"]}}))


if __name__ == "__main__":
    main()
