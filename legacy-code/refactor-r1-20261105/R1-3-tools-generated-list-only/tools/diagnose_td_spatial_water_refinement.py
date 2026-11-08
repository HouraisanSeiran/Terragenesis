"""Attribute spatial-weather refinement failure using pinned saved states and accounts."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def diagnose(audit_path, expected_sha256):
    audit_path = Path(audit_path).resolve(strict=True)
    if file_sha256(audit_path) != expected_sha256:
        raise ValueError("independent spatial audit external pin mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (audit["schema"] != "td-independent-spatial-weather-continuation-v1" or
            audit["full_spatial_rain_checked"] is not True or audit["checkpoint_chain_checked"] is not True or
            audit["solver_advanced"] is not False):
        raise ValueError("complete independent spatial chain audit required")
    comparison_path = Path(audit["comparison_path"])
    if file_sha256(comparison_path) != audit["comparison_sha256"]:
        raise ValueError("audited spatial comparison changed")
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    coarse, fine = sorted(audit["substeps_s"], reverse=True)
    topology, geometry = read_record(audit["hierarchy_record"])
    weather, weather_metadata = read_record(audit["weather_record"])
    cells = topology["height_m"].size
    accumulated = {step: {name: np.zeros(cells) for name in
        ("lake_rain_m3", "land_rain_m3", "local_release_m3", "soil_et_m3", "surface_et_m3",
         "boundary_outflow_m3", "internal_net_m3")} for step in (coarse, fine)}
    timeline = []
    hotspot_history = []
    hotspot = audit["max_cell"]
    for hour in range(24):
        pages = {}
        for step in (coarse, fine):
            arrays, metadata = read_record(comparison["pages"][str(step)][hour]["storage"])
            pages[step] = arrays
            for name in accumulated[step]:
                accumulated[step][name] += arrays[name][0]
        difference = pages[coarse]["depth_m"][-1] - pages[fine]["depth_m"][-1]
        maximum_cell = int(np.argmax(abs(difference)))
        timeline.append({"hour": hour + 1, "max_depth_difference_m": float(abs(difference).max()),
            "max_cell": maximum_cell, "cells_over_1mm": int(np.count_nonzero(abs(difference) > .001)),
            "surface_storage_difference_m3": math.fsum(difference.tolist()) * geometry["spacing_m"] ** 2,
            "max_soil_difference_mm": float(abs(pages[coarse]["soil_mm"][-1] - pages[fine]["soil_mm"][-1]).max()),
            "max_fast_difference_mm": float(abs(pages[coarse]["fast_mm"][-1] - pages[fine]["fast_mm"][-1]).max()),
            "max_slow_difference_mm": float(abs(pages[coarse]["slow_mm"][-1] - pages[fine]["slow_mm"][-1]).max()),
            "cumulative_lake_rain_l1_m3": float(abs(accumulated[coarse]["lake_rain_m3"] - accumulated[fine]["lake_rain_m3"]).sum()),
            "cumulative_internal_net_l1_m3": float(abs(accumulated[coarse]["internal_net_m3"] - accumulated[fine]["internal_net_m3"]).sum())})
        hotspot_history.append({"hour": hour + 1, "rain_mm_h": float(weather["rain_mm_h"][hour].ravel()[hotspot]),
            "by_step": {str(step): {**{name: float(pages[step][name][-1, hotspot]) for name in
                ("depth_m", "soil_mm", "fast_mm", "slow_mm")},
                **{name: float(accumulated[step][name][hotspot]) for name in accumulated[step]}}
                for step in (coarse, fine)}})
    maximum = max(item["max_depth_difference_m"] for item in timeline)
    if abs(maximum - audit["max_saved_depth_difference_m"]) > 1e-12:
        raise ValueError("diagnostic does not reproduce independent maximum")
    ranked = np.argsort(abs(difference))[-20:][::-1]
    hotspots = [{"cell": int(cell), "row": int(cell // topology["height_m"].shape[1]),
                 "column": int(cell % topology["height_m"].shape[1]),
                 "height_m": float(topology["height_m"].ravel()[cell]),
                 "final_depth_difference_m": float(difference[cell]),
                 "cumulative_lake_rain_difference_m3": float(accumulated[coarse]["lake_rain_m3"][cell] - accumulated[fine]["lake_rain_m3"][cell]),
                 "cumulative_internal_net_difference_m3": float(accumulated[coarse]["internal_net_m3"][cell] - accumulated[fine]["internal_net_m3"][cell])}
                for cell in ranked]
    if file_sha256(comparison_path) != audit["comparison_sha256"] or file_sha256(audit_path) != expected_sha256:
        raise ValueError("diagnostic pinned inputs changed")
    return {"schema": "td-spatial-water-refinement-diagnostic-v1", "audit_path": str(audit_path),
            "audit_sha256": expected_sha256, "gate_passed": audit["gate_passed"], "timeline": timeline,
            "original_hotspot": hotspot, "hotspot_history": hotspot_history, "final_hotspots": hotspots,
            "solver_advanced": False, "root_cause_confirmed": False, "hydraulic_ready": False,
            "interpretation": "Saved hourly differences attribute cumulative rain partition and transport accounts; internal substep events and causal isolation are not available from these files."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args()
    report = diagnose(arguments.audit, arguments.expected_sha256)
    output = ROOT / "verification/td-basin-generation" / ("spatial-weather-diagnostic-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"path": str(output), "sha256": file_sha256(output), "gate_passed": report["gate_passed"]}))
