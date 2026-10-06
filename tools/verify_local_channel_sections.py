"""Offline local-section geometry verification on synthetic and saved plans."""

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

from terrain_pipeline.local_channel_sections import (SectionRecipe, evaluate_sections,
                                                     load_sections, save_sections)
from terrain_pipeline.metric_channel_plan import load_plan
from tests.test_local_channel_sections import synthetic_plan


OUTPUT = ROOT / "verification/local-channel-sections"
PLAN_ROOT = ROOT / "verification/metric-channel-plan/run-20260929T140629572001Z"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plot_geometry(destination, name, result):
    arrays = result["arrays"]
    source = arrays["source_surface_m"]
    bounded = arrays["bounded_surface_m"]
    required = arrays["required_cut_m"]
    row = source.shape[0] // 2
    params = result["identity"]["parameters"]
    x0, z0 = params["origin_x_m"], params["origin_z_m"]
    dx, dz = params["spacing_x_m"], params["spacing_z_m"]
    extent = [x0, x0 + (source.shape[1] - 1) * dx,
              z0, z0 + (source.shape[0] - 1) * dz]
    lower = float(min(source.min(), bounded.min()))
    upper = float(max(source.max(), bounded.max()))
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    source_image = axes[0, 0].imshow(source, origin="lower", extent=extent,
                                    vmin=lower, vmax=upper)
    axes[0, 0].set_title("Interpolated source surface (m)")
    fig.colorbar(source_image, ax=axes[0, 0], label="Elevation (m)")
    cut_image = axes[0, 1].imshow(required, origin="lower", extent=extent)
    axes[0, 1].set_title("Required channel cut (m)")
    fig.colorbar(cut_image, ax=axes[0, 1], label="Cut (m)")
    bounded_image = axes[1, 0].imshow(bounded, origin="lower", extent=extent,
                                      vmin=lower, vmax=upper)
    axes[1, 0].set_title("Bounded surface (m)")
    fig.colorbar(bounded_image, ax=axes[1, 0], label="Elevation (m)")
    distance = np.arange(source.shape[1]) * dx
    axes[1, 1].plot(distance, source[row], label="source")
    axes[1, 1].plot(distance, bounded[row], label="bounded")
    axes[1, 1].set_title(f"Cross-section at local row {row}")
    axes[1, 1].set(xlabel="Distance from west edge (m)", ylabel="Elevation (m)")
    for ax in (axes[0, 0], axes[0, 1], axes[1, 0]):
        ax.set(xlabel="World x (m)", ylabel="World z (m)")
    axes[1, 1].legend()
    fig.savefig(destination / f"{name}-geometry.png", dpi=140)
    plt.close(fig)


def record(name, plan, origin, spacing, shape, destination, recipe):
    protected = np.zeros(shape, dtype=bool)
    result = evaluate_sections(plan, origin[0], origin[1], spacing[0], spacing[1],
                               shape, protected, recipe)
    saved = save_sections(result, destination / f"{name}-sections.npz")
    loaded = load_sections(saved)
    for key in result["arrays"]:
        np.testing.assert_array_equal(result["arrays"][key], loaded["arrays"][key])
    plot_geometry(destination, name, result)
    return {"sections_npz": saved.name, "sections_sha256": file_hash(saved),
            "plan_identity_sha256": plan["identity_sha256"],
            "section_identity_sha256": result["identity_sha256"],
            "origin_xz_m": list(origin), "spacing_xz_m": list(spacing),
            "shape_zx": list(shape), "summary": result["summary"],
            "required_cut_max_m": float(np.max(result["arrays"]["required_cut_m"])),
            "status": result["status"], "figure": f"{name}-geometry.png"}


def main():
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir()
    recipe = SectionRecipe()
    synthetic = synthetic_plan(width=4.)
    real_path = PLAN_ROOT / "normal_mountain-plan.npz"
    before_hash = file_hash(real_path)
    real = load_plan(real_path)
    if file_hash(real_path) != before_hash:
        raise RuntimeError("saved plan changed during load")
    params = real["identity"]["parameters"]
    # A bounded 60 x 60 m patch around a saved active cell; source remains unchanged.
    active = np.argwhere(real["arrays"]["channel_mask"])
    z, x = map(int, active[len(active) // 2])
    start_x = min(max(0, x - 1), real["arrays"]["source_height_m"].shape[1] - 3)
    start_z = min(max(0, z - 1), real["arrays"]["source_height_m"].shape[0] - 3)
    real_origin = (params["origin_x_m"] + start_x * 30.,
                   params["origin_z_m"] + start_z * 30.)
    report = {"purpose": "local metric channel geometry diagnostics, not terrain or water product",
              "section_recipe": recipe.__dict__,
              "assumptions": "cosine taper of cut depth across full nominal width; interpolated source has no new fine terrain detail",
              "samples": {}}
    report["samples"]["synthetic_confluence"] = record(
        "synthetic-confluence", synthetic, (0., 0.), (1., 1.), (41, 41), destination, recipe)
    report["samples"]["normal_mountain_local"] = record(
        "normal-mountain-local", real, real_origin, (1., 1.), (61, 61), destination, recipe)
    report["samples"]["normal_mountain_local"]["source_plan_npz"] = str(real_path.relative_to(ROOT))
    report["samples"]["normal_mountain_local"]["source_plan_sha256"] = file_hash(real_path)
    report["samples"]["normal_mountain_local"]["source_note"] = (
        "inherits artificial lowest-boundary outlet and constant diagnostic 1e-8 m/s runoff; "
        "not a natural mouth or climate calibration")
    if file_hash(real_path) != before_hash:
        raise RuntimeError("saved plan changed during verification")
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
