"""Bounded fixed-hotspot replay to separate saved forcing from face splitting."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.mountain_source_adapter import publish_bytes, file_sha256
from terrain_pipeline.td_basin_storage import load_basin_storage
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_storage_v4 import exchange, parameters
from tools.verify_td_basin_storage import HIERARCHY, HIERARCHY_SHA256, HIERARCHY_IDENTITY


def verify(package):
    package = Path(package)
    comparison_path = package / "strong-comparison.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    coarse = load_basin_storage(**comparison["coarse"])
    fine = load_basin_storage(**comparison["fine"])
    hierarchy = load_basin_hierarchy(HIERARCHY, expected_sha256=HIERARCHY_SHA256, expected_identity=HIERARCHY_IDENTITY)
    arrays = hierarchy["arrays"]
    cell = comparison["max_difference_cell"]
    rows, columns = arrays["height_m"].shape
    row, column = divmod(cell, columns)
    selected = np.zeros((rows, columns), bool)
    selected[max(0, row - 8):min(rows, row + 9), max(0, column - 8):min(columns, column + 9)] = True
    selected = selected.ravel()
    selected_cells = np.flatnonzero(selected)
    local_ids = np.full(selected.size, -1, np.int64)
    local_ids[selected_cells] = np.arange(len(selected_cells))
    faces = arrays["face_cells"]
    faces = local_ids[faces[selected[faces].all(axis=1)]]
    local_columns = min(columns, column + 9) - max(0, column - 8)
    bed = arrays["height_m"].ravel()[selected]
    boundary = np.array([], np.int64)
    width = np.array([])
    area = hierarchy["metadata"]["spacing_m"] ** 2
    start_frame = max(0, comparison["max_difference_step"] - 1)
    duration_s = 3600.
    results = {}
    initial = coarse["arrays"]["depth_m"][start_frame, selected].copy()
    for forcing_name, saved in (("coarse", coarse), ("fine", fine)):
        source = (saved["arrays"]["lake_rain_m3"][start_frame, selected] + saved["arrays"]["local_release_m3"][start_frame, selected] -
                  saved["arrays"]["surface_et_m3"][start_frame, selected]) / area
        for step in (5., 2.5, 1.25, .625):
            depth = initial.copy()
            for substep in range(int(duration_s / step)):
                updated = depth + source * step / duration_s
                if updated.min() < -1e-12:
                    raise ValueError("frozen forcing replay requires unavailable local water")
                depth, *_ = exchange(np.maximum(updated, 0), bed, faces, boundary, width,
                                     hierarchy["metadata"]["spacing_m"], step, parameters(None), local_columns)
            results[(forcing_name, step)] = depth
    first, second = faces[:, 0], faces[:, 1]
    sill = np.maximum(bed[first], bed[second])
    source = (coarse["arrays"]["lake_rain_m3"][start_frame, selected] + coarse["arrays"]["local_release_m3"][start_frame, selected] -
              coarse["arrays"]["surface_et_m3"][start_frame, selected]) / area / duration_s

    def derivative(time, depth):
        head = bed + depth
        signed = .6 / hierarchy["metadata"]["spacing_m"] * (np.maximum(0, head[first] - np.maximum(sill, head[second])) -
                  np.maximum(0, head[second] - np.maximum(sill, head[first])))
        return source + np.bincount(second, weights=signed, minlength=len(bed)) - np.bincount(first, weights=signed, minlength=len(bed))

    reference = solve_ivp(derivative, (0., duration_s), initial, method="DOP853", rtol=1e-10, atol=1e-11, max_step=1.25)
    if not reference.success:
        raise ValueError("hotspot continuous ODE failed")
    ode_errors = {f"{step:g}": float(abs(results[("coarse", step)] - reference.y[:, -1]).max()) for step in (5., 2.5, 1.25, .625)}
    records = {}
    for forcing_name in ("coarse", "fine"):
        records[forcing_name] = {f"{first:g}/{second:g}": float(abs(results[(forcing_name, first)] -
            results[(forcing_name, second)]).max()) for first, second in ((5., 2.5), (2.5, 1.25), (1.25, .625))}
    forcing_error = float(abs(results[("coarse", .625)] - results[("fine", .625)]).max())
    saved_diffs = {name: float(abs(coarse["arrays"][name][start_frame, selected] -
        fine["arrays"][name][start_frame, selected]).sum()) for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "surface_et_m3")}
    report = {"schema": "td-v4-fixed-hotspot-forcing-face-replay-v1", "comparison_pin": {
        "path": str(comparison_path), "sha256": file_sha256(comparison_path)}, "coarse": comparison["coarse"],
        "fine": comparison["fine"], "cell": cell, "cells": int(selected.sum()), "faces": len(faces),
        "start_frame": start_frame, "replay_duration_s": duration_s, "face_step_errors_m": records,
        "forcing_change_same0_625s_error_m": forcing_error, "saved_forcing_cell_l1_m3": saved_diffs,
        "continuous_ode_errors_m": ode_errors, "ode": {"method": "DOP853", "rtol": 1e-10, "atol": 1e-11, "max_step_s": 1.25},
        "hydraulic_ready": False, "publishable": False, "transient_converged": False,
        "limitations": "Closed17x17 hotspot window with fixed coarse initial surface, hourly saved source replay. Excludes external exchange and dynamic wet partition; controlled local attribution, not full catchment certification.",
        "next_verified_repair": "If face splitting dominates, resolve hotspot with finer conservative face splitting and saved boundary flux replay; if forcing dominates, split rainfall/runoff midpoint integration with frozen wet classification and test same forcing/gates.",
        "code_sha256": {name: file_sha256(ROOT / name) for name in ("terrain_pipeline/td_basin_storage_v4.py", "tools/diagnose_td_v4_hotspot.py")}}
    destination = ROOT / "verification/td-basin-generation" / ("A-v4-hotspot-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    publish_bytes(destination / "report.json", payload)
    print(json.dumps({"output": str(destination), "face_errors": records, "forcing_error_m": forcing_error}), flush=True)


if __name__ == "__main__":
    verify(sys.argv[1])
