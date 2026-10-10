"""Cold M1/M2 audit with generation and solver entry points explicitly disabled."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from unittest.mock import patch

import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.prepare_td_river_milestones import ROOT, audit_saved


GENERATION_ENTRIES = (
    "tools.prepare_td_river_milestones.build_spatial_forcing",
    "tools.prepare_td_river_milestones.build_diagnostic_product",
    "tools.prepare_td_river_milestones.compare_routing_policies",
    "tools.prepare_td_river_milestones.sample_diagnostic_output",
    "terrain_pipeline.surface_rivers.metric_forcing.field",
    "terrain_pipeline.surface_rivers.metric_drainage.route_diagnostic",
    "terrain_pipeline.surface_rivers.metric_routing_comparison.route_diagnostic",
    "terrain_pipeline.surface_rivers.metric_routing_comparison.route_priority_flood",
    "terrain_pipeline.surface_rivers.metric_routing_comparison._route_d4",
    "terrain_pipeline.surface_rivers.metric_product.route_diagnostic",
    "terrain_pipeline.surface_rivers.metric_product.runoff_from_forcing",
    "terrain_pipeline.surface_rivers.metric_product.runoff_from_forcing_large",
    "terrain_pipeline.surface_rivers.metric_runoff.simulate_rainfall_runoff",
    "terrain_pipeline.surface_rivers.metric_large_runoff.simulate_rainfall_runoff",
    "terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff",
    "terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy",
)
IMPLEMENTATION_PATHS = (
    "terrain_pipeline/surface_rivers/metric_source.py",
    "terrain_pipeline/surface_rivers/metric_routing_comparison.py",
    "terrain_pipeline/surface_rivers/metric_forcing.py",
    "terrain_pipeline/surface_rivers/metric_output.py",
    "terrain_pipeline/surface_rivers/metric_product.py",
    "terrain_pipeline/surface_rivers/metric_drainage.py",
    "terrain_pipeline/surface_rivers/metric_large_runoff.py",
    "tools/prepare_td_river_milestones.py",
    "tools/audit_td_river_milestones.py",
)


def audit(directory, output):
    started = time.perf_counter()
    directory = Path(directory).resolve()
    with ExitStack() as guards:
        for entry in GENERATION_ENTRIES:
            guards.enter_context(patch(entry, side_effect=AssertionError("cold audit generated: " + entry)))
        report = audit_saved(directory)
    memory = psutil.Process().memory_info()
    result = {"status": "cold_m1_m2_verified", "input_directory": str(directory),
              "manifest_sha256": file_sha256(directory / "manifest.json"),
              "acceptance_sha256": file_sha256(directory / "acceptance.json"),
              "grid_shape_zx": report["grid_shape_zx"], "sampling": report["sampling"],
              "mass_balance_m3": report["mass_balance_m3"],
              "generation_entry_points_disabled": list(GENERATION_ENTRIES),
              "implementation_sha256": {name: file_sha256(ROOT / name) for name in IMPLEMENTATION_PATHS},
              "elapsed_seconds": time.perf_counter() - started,
              "process_peak_working_set_bytes": int(getattr(memory, "peak_wset", memory.rss)),
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    publish_bytes(output, (json.dumps(result, ensure_ascii=False, sort_keys=True,
                                     indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("cold-%Y%m%dT%H%M%S%fZ")
    output = args.output or args.input / (stamp + ".json")
    result = audit(args.input, output)
    print(json.dumps({"status": result["status"], "output": str(output),
                      "elapsed_seconds": result["elapsed_seconds"],
                      "process_peak_working_set_bytes": result["process_peak_working_set_bytes"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
