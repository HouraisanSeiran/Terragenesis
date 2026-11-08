"""Read-only diagnosis of spatial-rain partition and wet-front exchange splits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _page(run: Path, direction: str, step: float, hour: int):
    report_path = run / f"{direction}-{step:g}s" / f"hour-{hour:02d}" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    storage = report["storage"]
    if file_sha256(storage["path"]) != storage["expected_sha256"]:
        raise ValueError(f"storage SHA changed: {storage['path']}")
    with np.load(storage["path"], allow_pickle=False) as saved:
        return report, {name: saved[name].copy() for name in saved.files}


def _cells_for_faces(faces: np.ndarray, cells: np.ndarray) -> np.ndarray:
    return np.flatnonzero(np.isin(faces[:, 0], cells) | np.isin(faces[:, 1], cells))


def diagnose(run: Path, weather_path: Path, *, direction="eastward", cell=60279,
             coarse_step=2.5, fine_step=1.25, radius=1, output=None):
    weather_sha = file_sha256(weather_path)
    with np.load(weather_path, allow_pickle=False) as weather:
        rain = weather["rain_mm_h"].copy()
    if rain.ndim != 3 or rain.shape[0] != 24:
        raise ValueError("weather record must be [24,z,x]")
    height, width = rain.shape[1:]
    row, column = divmod(cell, width)
    neighborhood = [
        r * width + c
        for r in range(max(0, row - radius), min(height, row + radius + 1))
        for c in range(max(0, column - radius), min(width, column + radius + 1))
    ]
    neighborhood = np.asarray(neighborhood, dtype=np.int64)
    coarse_rows, fine_rows = [], []
    first_global = None
    first_local = None
    for hour in range(24):
        coarse_report, coarse = _page(run, direction, coarse_step, hour)
        fine_report, fine = _page(run, direction, fine_step, hour)
        if not np.array_equal(coarse["face_cells"], fine["face_cells"]):
            raise ValueError("static face topology differs between refinements")
        faces = coarse["face_cells"]
        face_indices = _cells_for_faces(faces, neighborhood)
        rows = []
        for label, arrays, report in (("coarse", coarse, coarse_report), ("fine", fine, fine_report)):
            depth0 = arrays["depth_m"][0]
            depth1 = arrays["depth_m"][1]
            rain_cell = float(arrays["rain_mm_h"][0, cell])
            rain_volume = float(arrays["rain_volume_m3"][0, cell])
            lake_rain = float(arrays["lake_rain_m3"][0, cell])
            land_rain = float(arrays["land_rain_m3"][0, cell])
            rows.append({
                "step": label,
                "hour": hour,
                "report_elapsed_s": report["elapsed_s"],
                "rain_mm_h": rain_cell,
                "depth_start_m": float(depth0[cell]),
                "depth_end_m": float(depth1[cell]),
                "wet_start": bool(depth0[cell] > 1e-9),
                "wet_end": bool(depth1[cell] > 1e-9),
                "thin_start_1e-9_to_1e-6": bool(1e-9 < depth0[cell] <= 1e-6),
                "rain_volume_m3": rain_volume,
                "lake_rain_m3": lake_rain,
                "land_rain_m3": land_rain,
                "rain_partition_residual_m3": lake_rain + land_rain - rain_volume,
                "soil_start_mm": float(arrays["soil_mm"][0, cell]),
                "soil_end_mm": float(arrays["soil_mm"][1, cell]),
                "fast_start_mm": float(arrays["fast_mm"][0, cell]),
                "fast_end_mm": float(arrays["fast_mm"][1, cell]),
                "slow_start_mm": float(arrays["slow_mm"][0, cell]),
                "slow_end_mm": float(arrays["slow_mm"][1, cell]),
                "internal_net_m3": float(arrays["internal_net_m3"][0, cell]),
                "local_release_m3": float(arrays["local_release_m3"][0, cell]),
                "face_forward_m3_neighborhood": float(arrays["face_forward_m3"][face_indices].sum()),
                "face_reverse_m3_neighborhood": float(arrays["face_reverse_m3"][face_indices].sum()),
                "active_forward_s_neighborhood": float(arrays["active_forward_s"][face_indices].sum()),
                "active_reverse_s_neighborhood": float(arrays["active_reverse_s"][face_indices].sum()),
                "routed_volume_m3": float(arrays["routed_volume_m3"][cell]),
                "wet_duration_s": float(arrays["wet_duration_s"][cell]),
                "global_wet_cells_start": int(np.count_nonzero(depth0 > 1e-9)),
                "global_thin_cells_start": int(np.count_nonzero((depth0 > 1e-9) & (depth0 <= 1e-6))),
                "global_newly_wet_cells": int(np.count_nonzero((depth0 <= 1e-9) & (depth1 > 1e-9))),
                "global_wet_rain_m3": float(arrays["lake_rain_m3"][0].sum()),
                "global_dry_land_rain_m3": float(arrays["land_rain_m3"][0].sum()),
                "global_rain_partition_residual_m3": float(
                    arrays["lake_rain_m3"][0].sum() + arrays["land_rain_m3"][0].sum()
                    - arrays["rain_volume_m3"][0].sum()
                ),
            })
        coarse_row, fine_row = rows
        local_difference = abs(fine_row["depth_end_m"] - coarse_row["depth_end_m"])
        global_difference = float(np.max(np.abs(fine["depth_m"][1] - coarse["depth_m"][1])))
        if first_local is None and local_difference > 1e-12:
            first_local = hour
        if first_global is None and global_difference > 1e-6:
            first_global = hour
        coarse_rows.append(coarse_row)
        fine_rows.append(fine_row)
    result = {
        "schema": "td-native-weather-partition-diagnosis-v1",
        "scope": "read-only saved eastward spatial-weather pages; no solver advance",
        "run": str(run),
        "direction": direction,
        "weather_path": str(weather_path),
        "weather_sha256": weather_sha,
        "cell": cell,
        "cell_zx": [row, column],
        "neighborhood_radius": radius,
        "neighborhood_cells": neighborhood.tolist(),
        "steps_s": [coarse_step, fine_step],
        "wet_threshold_m": 1e-9,
        "thin_band_m": [1e-9, 1e-6],
        "first_local_depth_difference_hour": first_local,
        "first_global_depth_difference_hour": first_global,
        "global_first_difference_threshold_m": 1e-6,
        "coarse": coarse_rows,
        "fine": fine_rows,
        "interpretation": {
            "lake_rain_is_wet_bypass": "diagnostic classification only; it records saved ledger partition and does not infer causality",
            "internal_net_is_actual_face_divergence": True,
            "depth_difference_is_not_replaced_by_rain_difference": True,
            "hydraulic_ready": False,
            "transient_converged": False,
        },
    }
    output = Path(output) if output is not None else run / f"{direction}-partition-diagnosis-v2.json"
    publish_bytes(output, _json(result))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--weather", type=Path, required=True)
    parser.add_argument("--direction", default="eastward")
    parser.add_argument("--cell", type=int, default=60279)
    parser.add_argument("--coarse-step", type=float, default=2.5)
    parser.add_argument("--fine-step", type=float, default=1.25)
    parser.add_argument("--radius", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = diagnose(args.run, args.weather, direction=args.direction, cell=args.cell,
                    coarse_step=args.coarse_step, fine_step=args.fine_step, radius=args.radius,
                    output=args.output)
    print(json.dumps({"path": str(path), "sha256": file_sha256(path)}))
