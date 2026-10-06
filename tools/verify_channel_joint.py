"""Fixed static stage, bank inundation, and joint diagnostic verification."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.channel_inundation import (InundationRecipe, evaluate_inundation,
                                                  load_inundation, save_inundation)
from terrain_pipeline.channel_joint import assess_joint
from terrain_pipeline.channel_stage import StageRecipe, load_stage, save_stage, solve_stage
from terrain_pipeline.channel_centerline import load_centerline
from terrain_pipeline.local_channel_sections import SectionRecipe, evaluate_sections
from terrain_pipeline.metric_channel_plan import load_plan
from tests.test_channel_stage_inundation import confluence_plan, full_sections


OUTPUT = ROOT / "verification/channel-joint"
REAL_PLAN = ROOT / "verification/metric-channel-plan/run-20260929T140629572001Z/normal_mountain-plan.npz"
REAL_CENTERLINE = ROOT / "verification/channel-centerline/run-20260929T144849174805Z/normal_mountain_local-centerline.npz"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plot(path, sections, stage, flood):
    surface = sections["arrays"]["bounded_surface_m"]
    wet = flood["arrays"]["wet_mask"]
    water = flood["arrays"]["water_surface_m"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    a = axes[0].imshow(surface, origin="lower")
    fig.colorbar(a, ax=axes[0], label="Elevation (m)")
    axes[0].set_title("Bounded terrain")
    b = axes[1].imshow(stage["arrays"]["stage_m"], origin="lower")
    fig.colorbar(b, ax=axes[1], label="Stage (m)")
    axes[1].set_title("Shared graph stage")
    c = axes[2].imshow(np.where(wet, water - surface, np.nan), origin="lower")
    fig.colorbar(c, ax=axes[2], label="Wet depth (m)")
    axes[2].set_title("Connected lowland inundation")
    for ax in axes:
        ax.set(xlabel="Grid x", ylabel="Grid z")
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir()
    report = {"purpose": "static shared-stage and connected-lowland joint diagnostic",
              "limits": "not conveyance, backwater, mature wetland, or terrain publication",
              "samples": {}}
    plan = confluence_plan()
    sections = full_sections(plan)
    stage = solve_stage(plan, np.array([5.2]), StageRecipe(max_depth_m=4.,
                                                            max_lift_above_nominal_m=3.))
    full = np.ones((61, 61), bool)
    empty = np.zeros((61, 61), bool)
    legal = empty.copy()
    legal[-1, 27:34] = True
    flood = evaluate_inundation(plan, sections, stage, full, empty, legal,
                                InundationRecipe(max_lateral_reach_m=15.))
    joint = assess_joint(plan, sections, stage, flood)
    save_stage(stage, destination / "synthetic-stage.npz")
    save_inundation(flood, destination / "synthetic-inundation.npz")
    load_stage(destination / "synthetic-stage.npz")
    load_inundation(destination / "synthetic-inundation.npz")
    plot(destination / "synthetic-joint.png", sections, stage, flood)
    report["samples"]["synthetic_pass"] = {"joint": joint,
        "stage": stage["summary"], "inundation": flood["summary"],
        "outlet_note": "explicit synthetic open-water receiving edge z=60, x=27..33; not a measured sea mouth"}
    high = solve_stage(plan, np.array([20.]), StageRecipe(max_depth_m=2.))
    report["samples"]["synthetic_depth_failure"] = {"stage": high["summary"],
        "fixed_outlet_stage_m": 20., "note": "fixed outlet exceeds maximum allowed depth; no silent bed or stage repair"}
    protected = empty.copy()
    protected[30, 30] = True
    blocked = evaluate_inundation(plan, sections, stage, full, protected, legal,
                                  InundationRecipe(max_lateral_reach_m=5.))
    report["samples"]["synthetic_protection_failure"] = {
        "joint": assess_joint(plan, sections, stage, blocked), "inundation": blocked["summary"]}
    before_hash = file_hash(REAL_PLAN)
    real_plan = load_plan(REAL_PLAN)
    real_centerline = load_centerline(REAL_CENTERLINE)
    if file_hash(REAL_PLAN) != before_hash:
        raise RuntimeError("real plan changed during load")
    params = real_plan["identity"]["parameters"]
    active = np.argwhere(real_plan["arrays"]["channel_mask"])
    z, x = map(int, active[len(active) // 2])
    x0 = min(max(0, x - 1), real_plan["arrays"]["source_height_m"].shape[1] - 3)
    z0 = min(max(0, z - 1), real_plan["arrays"]["source_height_m"].shape[0] - 3)
    origin = (params["origin_x_m"] + x0 * 30., params["origin_z_m"] + z0 * 30.)
    real_sections = evaluate_sections(real_plan, *origin, 1., 1., (61, 61), empty,
                                      SectionRecipe(), real_centerline)
    outlet = np.flatnonzero(real_plan["arrays"]["outlet_mask"] & real_plan["arrays"]["channel_mask"])
    real_bed = real_plan["arrays"]["bounded_bed_m"].ravel()[outlet]
    real_stage = solve_stage(real_plan, real_bed + .5, StageRecipe(), real_centerline)
    no_legal = np.zeros((61, 61), bool)
    real_flood = evaluate_inundation(real_plan, real_sections, real_stage, full, empty,
                                     no_legal, InundationRecipe(max_lateral_reach_m=5.), real_centerline)
    real_joint = assess_joint(real_plan, real_sections, real_stage, real_flood)
    save_stage(real_stage, destination / "real-stage.npz")
    save_inundation(real_flood, destination / "real-local-inundation.npz")
    plot(destination / "real-local-joint.png", real_sections, real_stage, real_flood)
    report["samples"]["real_local_failure"] = {
        "source_plan": str(REAL_PLAN.relative_to(ROOT)), "source_sha256": before_hash,
        "source_centerline": str(REAL_CENTERLINE.relative_to(ROOT)),
        "source_centerline_sha256": file_hash(REAL_CENTERLINE),
        "stage": real_stage["summary"], "inundation": real_flood["summary"],
        "joint": real_joint,
        "note": "local saved mountain window lacks a legal sea outlet and full-domain fine coverage; diagnostic runoff and artificial boundary outlet persist"}
    if file_hash(REAL_PLAN) != before_hash:
        raise RuntimeError("real plan changed during verification")
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
