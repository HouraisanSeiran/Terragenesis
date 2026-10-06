"""Fixed comparison of unsmoothed and constrained shared centerline geometry."""

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

from terrain_pipeline.channel_centerline import (SmoothingRecipe, build_centerline,
                                                  load_centerline, save_centerline)
from terrain_pipeline.local_channel_sections import SectionRecipe, evaluate_sections
from terrain_pipeline.metric_channel_plan import load_plan
from tests.test_channel_centerline import corner_plan


OUTPUT = ROOT / "verification/channel-centerline"
SAVED_PLAN = ROOT / "verification/metric-channel-plan/run-20260929T140629572001Z/normal_mountain-plan.npz"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draw(path, plan, geometry, origin, shape):
    protected = np.zeros(shape, dtype=bool)
    recipe = SectionRecipe()
    old = evaluate_sections(plan, origin[0], origin[1], 1., 1., shape, protected, recipe)
    new = evaluate_sections(plan, origin[0], origin[1], 1., 1., shape, protected, recipe, geometry)
    arrays = geometry["arrays"]
    index = {int(cell): i for i, cell in enumerate(arrays["node_flat_index"])}
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    old_cut = old["arrays"]["required_cut_m"]
    new_cut = new["arrays"]["required_cut_m"]
    scale = max(float(old_cut.max()), float(new_cut.max()))
    extent = [origin[0], origin[0] + shape[1] - 1,
              origin[1], origin[1] + shape[0] - 1]
    axes[0].imshow(old_cut, origin="lower", extent=extent, vmin=0, vmax=scale)
    axes[0].set_title("Original required cut (m)")
    im = axes[1].imshow(new_cut, origin="lower", extent=extent, vmin=0, vmax=scale)
    axes[1].set_title("Smoothed required cut (m)")
    fig.colorbar(im, ax=axes[:2], label="Required cut (m)")
    old_xy = arrays["original_world_xz_m"]
    new_xy = arrays["node_world_xz_m"]
    for cell, target in zip(arrays["edge_donor_flat_index"], arrays["edge_target_flat_index"]):
        i, j = index[int(cell)], index[int(target)]
        if max(old_xy[i, 0], old_xy[j, 0], new_xy[i, 0], new_xy[j, 0]) < origin[0] or min(old_xy[i, 0], old_xy[j, 0], new_xy[i, 0], new_xy[j, 0]) > extent[1]:
            continue
        if max(old_xy[i, 1], old_xy[j, 1], new_xy[i, 1], new_xy[j, 1]) < origin[1] or min(old_xy[i, 1], old_xy[j, 1], new_xy[i, 1], new_xy[j, 1]) > extent[3]:
            continue
        axes[2].plot(old_xy[[i, j], 0], old_xy[[i, j], 1], color="gray", linewidth=.8)
        axes[2].plot(new_xy[[i, j], 0], new_xy[[i, j], 1], color="blue", linewidth=.8)
    axes[2].set(xlim=(extent[0], extent[1]), ylim=(extent[2], extent[3]),
                title="Gray original / blue smoothed", xlabel="World x (m)", ylabel="World z (m)")
    for ax in axes[:2]:
        ax.set(xlabel="World x (m)", ylabel="World z (m)")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return {"old_required_cut_max_m": float(old_cut.max()),
            "new_required_cut_max_m": float(new_cut.max()),
            "new_local_budget_conflict_nodes": new["summary"]["local_budget_conflict_nodes"],
            "new_clipped_boundary_nodes": new["summary"]["clipped_boundary_nodes"]}


def main():
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir()
    report = {"purpose": "shared constrained centerline diagnostic, not river product",
              "samples": {}}
    synthetic = corner_plan()
    real_hash = file_hash(SAVED_PLAN)
    real = load_plan(SAVED_PLAN)
    if file_hash(SAVED_PLAN) != real_hash:
        raise RuntimeError("saved plan changed during load")
    for name, plan, recipe, origin, shape in (
            ("synthetic_corner", synthetic, SmoothingRecipe(max_offset_m=10.), (0., 0.), (31, 31)),
            ("normal_mountain_local", real, SmoothingRecipe(max_offset_m=10.),
             (354240., 468420.), (61, 61))):
        geometry = build_centerline(plan, recipe)
        path = destination / f"{name}-centerline.npz"
        save_centerline(geometry, path)
        loaded = load_centerline(path)
        if loaded["identity_sha256"] != geometry["identity_sha256"]:
            raise AssertionError("centerline reload identity mismatch")
        plot = draw(destination / f"{name}-comparison.png", plan, loaded, origin, shape)
        report["samples"][name] = {"recipe": recipe.__dict__, "summary": geometry["summary"],
                                   "geometry_identity_sha256": geometry["identity_sha256"],
                                   "geometry_npz": path.name, "geometry_sha256": file_hash(path),
                                   "figure": f"{name}-comparison.png", **plot}
    report["samples"]["normal_mountain_local"]["source_plan_npz"] = str(SAVED_PLAN.relative_to(ROOT))
    report["samples"]["normal_mountain_local"]["source_plan_sha256"] = real_hash
    report["limitations"] = ("Original artificial outlet and diagnostic runoff persist. "
                             "Moved geometry is checked for centerline slope and local cut budget, "
                             "but section geometry does not guarantee a continuous bed or water-surface slope. "
                             "No lake, valley or hydraulic solution is included.")
    if file_hash(SAVED_PLAN) != real_hash:
        raise RuntimeError("saved plan changed during verification")
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
