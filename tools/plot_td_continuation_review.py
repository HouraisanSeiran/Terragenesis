"""Plot audited original-grid hourly water states without interpolation or simulation."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def plot(report_path, expected_sha256, output=None):
    report_path = Path(report_path).resolve(strict=True)
    if file_sha256(report_path) != expected_sha256:
        raise ValueError("independent audit report external SHA mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    version10 = report["schema"] == "td-independent-spatial-weather-v10-v1"
    spatial = report["schema"] in ("td-independent-spatial-weather-continuation-v1", "td-independent-spatial-weather-v10-v1")
    if (report["schema"] not in ("td-independent-streaming-continuation-v1", "td-independent-spatial-weather-continuation-v1", "td-independent-spatial-weather-v10-v1") or
            report["saved_frames"] != 25 or report["checkpoint_chain_checked"] is not True or
            report["solver_advanced"] is not False):
        raise ValueError("complete independent continuation audit required")
    if spatial and report.get("full_spatial_rain_checked") is not True:
        raise ValueError("independently checked complete spatial rainfall required")
    if version10 and report.get("compartment_ledgers_checked") is not True:
        raise ValueError("independently checked v10 compartment accounts required")
    scenario = report.get("scenario", Path(report["comparison_path"]).name.removesuffix("-comparison.json"))
    comparison_path = Path(report["comparison_path"]).resolve(strict=True)
    if file_sha256(comparison_path) != report["comparison_sha256"]:
        raise ValueError("audited comparison external SHA mismatch")
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    steps = sorted(report["substeps_s"], reverse=True)
    if len(steps) != 2:
        raise ValueError("audited two-step comparison required")
    maxima = []
    maximum_difference = None
    fine_maximum_depth = None
    inventories = {str(step): {"surface_m3": [], "total_m3": []} for step in steps}
    bed = None
    valid = None
    geometry = None
    for hour in range(24):
        saved = []
        for step in steps:
            pages = comparison["pages"][str(step)]
            if len(pages) != 24 or pages[hour]["hour"] != hour:
                raise ValueError("audited hourly coverage changed")
            arrays, metadata = read_record(pages[hour]["storage"])
            fields = ("spacing_m", "origin_m_xz", "hierarchy_identity", "profile") if version10 else (
                "spacing_m", "origin_m_xz", "hierarchy_identity_sha256", "algorithm")
            current_geometry = {name: metadata[name] for name in fields}
            if bed is None:
                bed = arrays["height_m"].copy()
                valid = arrays["valid_mask"].copy()
                geometry = current_geometry
                maximum_difference = np.zeros(bed.size)
                fine_maximum_depth = np.zeros(bed.size)
            if current_geometry != geometry or not np.array_equal(arrays["height_m"], bed) or not np.array_equal(arrays["valid_mask"], valid):
                raise ValueError("hourly plot input original geometry changed")
            area = metadata["spacing_m"] ** 2
            frames = (0, 1) if hour == 0 else (1,)
            for frame in frames:
                surface = arrays["depth_m"][frame]
                stores = surface + sum(arrays[name][frame] for name in ("soil_mm", "fast_mm", "slow_mm")) / 1000
                inventories[str(step)]["surface_m3"].append(float(surface.sum() * area))
                inventories[str(step)]["total_m3"].append(float(stores.sum() * area))
            saved.append(arrays["depth_m"].copy())
            del arrays
        difference = abs(saved[0] - saved[1])
        maxima.extend(float(difference[frame].max()) for frame in ((0, 1) if hour == 0 else (1,)))
        maximum_difference = np.maximum(maximum_difference, difference.max(axis=0))
        fine_maximum_depth = np.maximum(fine_maximum_depth, saved[1].max(axis=0))
    maximum = max(maxima)
    if abs(maximum - report["max_saved_depth_difference_m"]) > 1e-12:
        raise ValueError("plot depth reductions differ from independent audit")
    figure, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    spacing = geometry["spacing_m"]
    extent = [0, bed.shape[1] * spacing / 1000, bed.shape[0] * spacing / 1000, 0]
    layers = ((bed, "Original TD bed (m)", "terrain"),
              (fine_maximum_depth.reshape(bed.shape), "Maximum fine depth over hourly frames (m)", "Blues"),
              (maximum_difference.reshape(bed.shape) * 1000, "Maximum saved-frame timestep difference (mm)", "magma"))
    for axis, (values, title, cmap) in zip(axes[0], layers):
        rendered = axis.imshow(np.ma.masked_where(~valid, values), extent=extent,
                               interpolation="nearest", cmap=cmap)
        axis.set(title=title, xlabel="local X (km)", ylabel="local Z (km)")
        figure.colorbar(rendered, ax=axis, shrink=.8)
    hours = np.arange(25)
    for step in steps:
        axis_data = inventories[str(step)]
        axes[1, 0].plot(hours, np.asarray(axis_data["surface_m3"]) / 1e6, label=f"surface {step:g}s")
        axes[1, 0].plot(hours, np.asarray(axis_data["total_m3"]) / 1e6, "--", label=f"four stores {step:g}s")
    axes[1, 0].set(title="Actual domain inventory", xlabel="physical hours", ylabel="million cubic metres")
    axes[1, 0].legend()
    axes[1, 1].plot(hours, np.asarray(maxima) * 1000, marker=".")
    axes[1, 1].axhline(1, color="red", linestyle="--", label="unchanged 1mm gate")
    axes[1, 1].set(title="Original-grid timestep refinement", xlabel="physical hours", ylabel="difference (mm)")
    axes[1, 1].legend()
    for step in steps:
        budget = report["page_budget_audits"][str(step)]
        if budget["whole_period_passed"] is not True or len(budget["hours"]) != 24:
            raise ValueError("whole-period independently passed water budget required")
        exported = [hour["external_m3"] if version10 else sum(item["external_m3"] for item in hour["budgets"])
                    for hour in budget["hours"]]
        axes[1, 2].plot(hours, np.r_[0, np.cumsum(exported)] / 1e6, label=f"{step:g}s")
    axes[1, 2].set(title="Cumulative engineering boundary export", xlabel="physical hours", ylabel="million cubic metres")
    axes[1, 2].legend()
    figure.suptitle(f"{scenario} | {bed.shape[1]}x{bed.shape[0]}, {spacing:g}m | Saved-frame gate passed: {report['gate_passed']}")
    if output is None:
        output = ROOT / "verification/td-basin-generation" / ("independent-continuation-figure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    image_path = output / "td-continuation-review.png"
    figure.savefig(image_path, dpi=160)
    plt.close(figure)
    record = {"schema": "td-continuation-native-figure-v1", "audit_path": str(report_path),
              "audit_sha256": expected_sha256, "comparison_sha256": report["comparison_sha256"],
              "image_sha256": file_sha256(image_path), "geometry": geometry,
              "saved_frames": 25, "depth_difference_m": maximum,
              "numerical_saved_frame_gate_passed": report["gate_passed"],
              "water_interpolation": False, "solver_advanced": False, "hydraulic_ready": False,
              "limitations": "Native hourly water samples; maximum map is not one simultaneous water surface; no observed channels or natural outlet certification."}
    publish_bytes(output / "report.json", json.dumps(record, indent=2, allow_nan=False).encode("utf-8"))
    return image_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args()
    print(plot(arguments.audit, arguments.expected_sha256))
