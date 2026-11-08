"""Render saved, cold-audited planning water accounts without simulation."""

import argparse
import html
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
from terrain_pipeline.runoff import load_seasonal_water_balance as load_seasonal_water_balance
from terrain_pipeline.runoff import validate_seasonal_water_balance as validate_seasonal_water_balance


def render(plan_path, seasonal_path, output):
    plan = load_plan(plan_path)
    result = load_seasonal_water_balance(plan, seasonal_path)
    audit = validate_seasonal_water_balance(plan, result)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    filenames = ["lake-footprint.png", "lake-season.png", "monthly-water-account.png", "review.json", "index.html"]
    if any((output / name).exists() for name in filenames):
        raise FileExistsError("review outputs are immutable; use a new directory")
    height = plan["height_m"]
    owner = plan["owner_domain_id"]
    spacing = plan["spacing_m"]
    origin = plan["origin_xz_m"]
    extent = [(origin[0] - spacing / 2) / 1000, (origin[0] + (height.shape[1] - .5) * spacing) / 1000,
              (origin[1] - spacing / 2) / 1000, (origin[1] + (height.shape[0] - .5) * spacing) / 1000]
    column = next(i for i, domain in enumerate(plan["domains"]) if domain["kind"] == "inland")
    domain = plan["domains"][column]
    lake = LakeGeometry(height, owner, domain, spacing**2)
    volumes = np.r_[result["lake_volume_m3"][0, column], result["lake_volume_m3"][0, column]
                    + np.cumsum(result["steps"]["lake_change_m3"][:, column])]
    minimum_level = lake.level(float(volumes.min()))
    maximum_level = lake.level(float(volumes.max()))
    minimum_wet = lake.mask & (height < minimum_level)
    maximum_wet = lake.mask & (height < maximum_level)
    monthly_levels = result["lake_level_m"][:-1, column]
    monthly_area = np.array([(lake.mask & (height < level)).sum() * spacing**2 for level in monthly_levels])
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    for axis in axes:
        terrain = axis.imshow(height, origin="lower", extent=extent, cmap="terrain")
        axis.contour(owner == domain["domain_id"], levels=[.5], origin="lower", extent=extent,
                     colors=["#b52d46"], linewidths=.8)
        rgba = np.zeros(height.shape + (4,))
        rgba[maximum_wet] = [0.10, 0.67, 0.76, .7]
        rgba[minimum_wet] = [0.06, 0.31, 0.79, .85]
        axis.imshow(rgba, origin="lower", extent=extent)
        axis.set_xlabel("World X (km)")
        axis.set_ylabel("World Z (km)")
    axes[0].set_title("Frozen terrain and actual lake footprint")
    axes[1].set_title("Lake vicinity: minimum / maximum wet area")
    rr, cc = np.where(maximum_wet)
    margin = 3 * spacing / 1000
    axes[1].set_xlim((origin[0] + cc.min() * spacing) / 1000 - margin,
                     (origin[0] + cc.max() * spacing) / 1000 + margin)
    axes[1].set_ylim((origin[1] + rr.min() * spacing) / 1000 - margin,
                     (origin[1] + rr.max() * spacing) / 1000 + margin)
    from matplotlib.patches import Patch
    axes[0].legend(handles=[Patch(color="#1050c9", label="Minimum actual wet footprint"),
                            Patch(color="#1aabc2", label="Additional maximum wet footprint"),
                            Patch(facecolor="none", edgecolor="#b52d46", label="Inland catchment boundary")],
                   loc="lower left", fontsize=8)
    fig.colorbar(terrain, ax=axes, label="Frozen bed elevation (m)", shrink=.65)
    fig.suptitle("Coarse D8 raster columns; diagonal connectivity is not fine water connectivity", fontsize=11)
    fig.savefig(output / filenames[0], dpi=150)
    plt.close(fig)
    months = np.arange(1, 13)
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
    axes[0].plot(months, monthly_levels, "o-", color="#2563a6")
    axes[0].set_ylabel("Lake level at month start (m)")
    axes[0].set_title(f"Full-year step range {minimum_level:.6f} to {maximum_level:.6f} m; spill {lake.spill_m:.3f} m")
    axes[1].step(months, monthly_area / 1e6, where="mid", color="#13897c")
    axes[1].set_ylabel("Actual wet area (km2)")
    axes[1].set_xlabel("Repeating calendar month")
    for axis in axes:
        axis.grid(alpha=.25)
        axis.set_xticks(months)
    fig.savefig(output / filenames[1], dpi=150)
    plt.close(fig)
    monthly = result["monthly"]
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    for col, axis in enumerate(axes):
        axis.plot(months, (monthly["land_rain_m3"][:, col] + monthly["lake_rain_m3"][:, col]) / 1e9,
                  "o-", label="Total precipitation", color="#2563a6")
        axis.plot(months, (monthly["land_et_m3"][:, col] + monthly["lake_evaporation_m3"][:, col]) / 1e9,
                  "s-", label="Actual land ET + lake evaporation", color="#b84f30")
        axis.plot(months, monthly["runoff_to_terminal_m3"][:, col] / 1e9,
                  "^-", label="Land runoff to terminal", color="#258958")
        axis.plot(months, monthly["coastal_outflow_m3"][:, col] / 1e9,
                  "d--", label="Certified coastal outflow", color="#823d86")
        axis.plot(months, (monthly["soil_change_m3"][:, col] + monthly["lake_change_m3"][:, col]) / 1e9,
                  ".:", label="Soil + lake storage change", color="#555555")
        axis.set_title(f"{plan['domains'][col]['kind'].title()} domain {plan['domains'][col]['domain_id']}")
        axis.set_ylabel("Monthly volume (billion m3)")
        axis.grid(alpha=.25)
        axis.legend(fontsize=8, ncol=2)
        axis.set_xticks(months)
    axes[-1].set_xlabel("Repeating calendar month")
    fig.suptitle("Runoff is an internal transfer; total rain excludes double-counted lake rain", fontsize=11)
    fig.savefig(output / filenames[2], dpi=150)
    plt.close(fig)
    report = {"source_plan_identity_sha256": plan["identity_sha256"], "plan_path": str(Path(plan_path).resolve()),
              "seasonal_path": str(Path(seasonal_path).resolve()), "audit": audit,
              "minimum_step_lake_level_m": minimum_level, "maximum_step_lake_level_m": maximum_level,
              "minimum_wet_area_m2": float(minimum_wet.sum() * spacing**2),
              "maximum_wet_area_m2": float(maximum_wet.sum() * spacing**2),
              "monthly_start_lake_level_m": monthly_levels.tolist(), "monthly_start_wet_area_m2": monthly_area.tolist(),
              "scope": "Planning-only coarse D8 raster columns. No Terrain Diffusion detail or fine face connectivity is certified.",
              "pet": "Uncalibrated illustrative temperature-index planning PET. No groundwater leak or terrain erosion."}
    with (output / "review.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    content = "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Saved seasonal water review</title><style>body{font:16px system-ui;margin:24px auto;max-width:1250px;padding:0 16px;color:#242424}img{width:100%;height:auto}code{overflow-wrap:anywhere}figure{margin:24px 0}p{line-height:1.5}</style><h1>Saved Seasonal Water Review</h1>"
    content += f"<p>Parent plan <code>{html.escape(plan['identity_sha256'])}</code>. Cold audit: {audit['status']}.</p>"
    content += "<p>Planning-only coarse D8 raster columns. The blue and cyan footprints are actual lake wet cells, not the entire inland catchment. Diagonal coarse connectivity does not certify fine lake shores or Minecraft water connectivity. PET is illustrative and uncalibrated; terrain stays fixed.</p>"
    for name, caption in zip(filenames[:3], ["Actual wet lake footprint at the yearly minimum and maximum.",
                                            "Month-start lake level and wet area; extrema include every saved step.",
                                            "Monthly rainfall, actual evaporation, runoff, legal outflow and storage change."]):
        content += f"<figure><img src='{name}' alt='{caption}'><figcaption>{caption}</figcaption></figure>"
    content += "<p><a href='review.json'>Cold audit and source identities</a></p></html>"
    with (output / "index.html").open("x", encoding="utf-8") as stream:
        stream.write(content)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--seasonal", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    print(json.dumps(render(arguments.plan, arguments.seasonal, arguments.output), indent=2))
