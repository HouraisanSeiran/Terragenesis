"""Fixed offline verification for the independent metric channel plan."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.metric_channel_plan import ChannelRecipe, load_plan, plan_channel, save_plan
from terrain_pipeline.surface_rivers import accumulate, route


SOURCE = ROOT / "verification/metric-rivers/run-20260929T110135621570Z"
OUTPUT = ROOT / "verification/metric-channel-plan"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(name, plan, source_path, destination):
    arrays = plan["arrays"]
    saved = save_plan(plan, destination / f"{name}-plan.npz")
    loaded = load_plan(saved)
    if loaded["identity_sha256"] != plan["identity_sha256"]:
        raise AssertionError("plan identity changed on reload")
    for key in arrays:
        np.testing.assert_array_equal(arrays[key], loaded["arrays"][key])
    return {"source": str(source_path.relative_to(ROOT)) if source_path else "synthetic-confluence",
            "source_file_sha256": file_hash(source_path) if source_path else None,
            "plan_npz": saved.name, "plan_file_sha256": file_hash(saved),
            "identity_sha256": plan["identity_sha256"],
            "channel_cells": int(np.count_nonzero(arrays["channel_mask"])),
            "max_required_cut_m": float(arrays["required_cut_m"].max()),
            "over_budget_cells": int(np.count_nonzero(arrays["over_budget_mask"])),
            "failed_slope_edges": int(np.count_nonzero(arrays["failed_slope_edge_donor_mask"])),
            "needs_refinement_cells": int(np.count_nonzero(arrays["needs_refinement_mask"])),
            "status": plan["status"]}


def main():
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir()
    recipe = ChannelRecipe()
    report = {"purpose": "separate metric fixed-D8 channel-bed planning diagnostics",
              "recipe": recipe.__dict__,
              "recipe_note": "configurable engineering trial, not empirical width/depth calibration",
              "samples": {}}
    height = np.full((9, 9), 10., dtype=float)
    height[:, 4] = np.linspace(9., 1., 9)
    height[1:5, 1:4] = 8.
    height[1:5, 5:8] = 8.
    outlet = np.zeros(height.shape, dtype=bool)
    outlet[-1, 4] = True
    routing = route(height, outlet, 2.)
    runoff = np.full(height.shape, .002)
    accumulation = accumulate(routing, runoff, 2.)
    synthetic = plan_channel(height, routing.receiver, routing.order, outlet,
                             accumulation.discharge, 2., 2., 0., 0., 0.,
                             "synthetic-confluence-v1", recipe)
    report["samples"]["synthetic_confluence"] = describe(
        "synthetic-confluence", synthetic, None, destination)
    for name in ("pressure_mountain", "normal_mountain"):
        source = SOURCE / f"{name}.npz"
        before_hash = file_hash(source)
        with np.load(source, allow_pickle=False) as archive:
            height = archive["input_height"].copy()
            q = archive["discharge"].copy()
            outlet = archive["outlet_mask"].copy()
            old_receiver = archive["receiver"].copy()
            metadata = json.loads(str(archive["metadata"].item()))
        if file_hash(source) != before_hash:
            raise RuntimeError("source changed during read")
        routing = route(height, outlet, 30.)
        np.testing.assert_array_equal(routing.receiver, old_receiver.ravel())
        plan = plan_channel(height, routing.receiver, routing.order, outlet, q,
                            30., 30., *metadata["origin_world_xz"], 126., before_hash, recipe)
        report["samples"][name] = describe(name, plan, source, destination)
        report["samples"][name]["source_origin_core_m_xz"] = metadata["origin_world_xz"]
        report["samples"][name]["outlet_note"] = "artificial lowest boundary outlet, not legal sea mouth"
        report["samples"][name]["runoff_note"] = "saved discharge uses constant diagnostic 1e-8 m/s runoff"
        if file_hash(source) != before_hash:
            raise RuntimeError("source changed during verification")
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
