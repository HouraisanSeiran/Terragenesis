"""Small, uncalibrated finite-inventory dynamic erosion comparison."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.surface_rivers.metric_dynamic_feedback import route_feedback_daily
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment


def scenario(q: float, hardness: float) -> dict:
    bed = np.array([2., 1.])
    material = MaterialParameters(settling_velocity_m_s=0., provenance="uncalibrated comparison")
    source = route_daily_sediment(
        receiver=np.array([1, -1], dtype=np.int64), length_m=np.array([10., 10.]),
        width_m=np.array([2., 2.]), bed_elevation_m=bed,
        rock_floor_m=bed - 10., initial_alluvium_bulk_m3=np.zeros(2),
        hardness=np.array([hardness, 1.]), material=material,
        water_depth_m=np.ones((2, 2)), water_q_m3_s=np.full((2, 2), q),
        friction_slope=np.full((2, 2), .05), time_seconds=np.array([0., 3600., 7200.]),
        geometry_identity_sha256="a" * 64, hydraulic_identity_sha256="b" * 64,
        material_provenance="uncalibrated comparison")
    result = route_feedback_daily(source, np.array([[0., 0.], [20., 0.]]))
    a = result["arrays"]
    return {
        "q_m3_s": q, "upstream_hardness": hardness,
        "rock_reserve_m3": 200.,
        "eroded_rock_m3": float(a["eroded_rock_m3"].sum()),
        "exported_solid_m3": float(a["exported_solid_m3"].sum()),
        "remaining_mobile_solid_m3": float(a["trace_mobile_solid_m3"][-1].sum()),
        "remaining_loose_solid_m3": float(a["trace_loose_solid_m3"][-1].sum()),
        "solid_residual_m3": result["metadata"]["global_residual"],
        "bed_m": a["trace_bed_m"].tolist(),
        "slope": a["friction_slope"].tolist(),
        "water_depth_m": a["water_depth_m"].tolist(),
    }


def run() -> dict:
    return {
        "scope": "uncalibrated two-node comparison; independent of large-world geometry",
        "interval_seconds": 3600,
        "cases": {"low_q_soft": scenario(1., 0.), "high_q_soft": scenario(5., 0.),
                  "high_q_hard": scenario(5., .75)},
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, allow_nan=False))
