"""Render independently audited hourly native water and wet connectivity."""

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

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def plot(audit_path, audit_sha256, activity_path, activity_sha256, *, step_s=2.5):
    for path, digest in ((audit_path, audit_sha256), (activity_path, activity_sha256)):
        if file_sha256(path) != digest:
            raise ValueError("independent plot evidence external pin mismatch")
    report = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    activity_report = json.loads(Path(activity_path).read_text(encoding="utf-8"))
    if (report.get("checkpoint_chain_checked") is not True or report.get("saved_frames") != 25 or
            activity_report.get("audit_sha256") != audit_sha256 or
            activity_report.get("native_pool_count_independently_verified") is not True or
            activity_report.get("native_leaf_flux_divergence_verified") is not True):
        raise ValueError("complete independently checked native series required")
    selection_path = Path(report["comparison_path"])
    if file_sha256(selection_path) != report["comparison_sha256"]:
        raise ValueError("audited original page selection changed")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    pages = selection["pages"][str(step_s)]
    if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
        raise ValueError("complete hourly page coverage required")
    figure, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    frame_records = []
    geometry = None
    for position, hour in enumerate((0, 5, 23)):
        arrays, metadata = read_record(pages[hour]["storage"])
        current_geometry = {name: metadata[name] for name in ("origin_m_xz", "spacing_m", "hierarchy_identity_sha256")}
        if geometry is None:
            geometry = current_geometry
        elif geometry != current_geometry:
            raise ValueError("saved plot geometry changed")
        bed = arrays["height_m"]
        valid = arrays["valid_mask"]
        depth = arrays["depth_m"][-1].reshape(bed.shape)
        extent = [0, bed.shape[1] * metadata["spacing_m"] / 1000,
                  bed.shape[0] * metadata["spacing_m"] / 1000, 0]
        axes[0, position].imshow(np.ma.masked_where(~valid, bed), cmap="terrain", extent=extent, interpolation="nearest")
        water = np.ma.masked_where((depth < .01) | ~valid, depth)
        overlay = axes[0, position].imshow(water, cmap="Blues", vmin=0, vmax=16,
                                          extent=extent, interpolation="nearest", alpha=.9)
        axes[0, position].set(title=f"Hour {hour + 1}: actual depth >= 1cm", xlabel="local X (km)", ylabel="local Z (km)")
        figure.colorbar(overlay, ax=axes[0, position], shrink=.75, label="Actual water depth (m)")
        frame_records.append({"hour": hour + 1, "visible_cells_depth_at_least_1cm": int(np.count_nonzero(valid & (depth >= .01))),
                              "native_wet_cells": int(np.count_nonzero(valid & (depth > metadata["parameters"]["wet_threshold_m"]))),
                              "actual_surface_volume_m3": float(depth[valid].sum() * metadata["spacing_m"] ** 2)})
        del arrays
    budget = report["page_budget_audits"][str(step_s)]
    if budget["whole_period_passed"] is not True or len(budget["hours"]) != 24:
        raise ValueError("complete independent water budget required")
    hours = np.arange(25)
    totals = [budget["hours"][0]["initial_water_m3"]] + [hour["final_water_m3"] for hour in budget["hours"]]
    axes[1, 0].plot(hours, np.asarray(totals) / 1e6)
    axes[1, 0].set(title="Actual four-store domain inventory", xlabel="physical hours", ylabel="million cubic metres")
    activity = activity_report["series"][str(step_s)]
    axes[1, 1].plot(hours, [frame["open_cross_catchment_faces"] for frame in activity["frames"]])
    axes[1, 1].set(title="Wet faces joining static catchments", xlabel="physical hours", ylabel="D4 faces at saved frame")
    for field, label in (("forward_cross_catchment_m3", "forward"), ("reverse_cross_catchment_m3", "reverse")):
        volume = np.r_[0, np.cumsum([interval[field] for interval in activity["intervals"]])]
        axes[1, 2].plot(hours, volume / 1e6, label=label)
    axes[1, 2].set(title="Integrated internal face transport", xlabel="physical hours", ylabel="million cubic metres; repeated transport")
    axes[1, 2].legend()
    figure.suptitle(f"Original TD / {metadata['spacing_m']:g}m | {report['scenario']}, {step_s:g}s | Budget passed; engineering boundaries")
    output = ROOT / "verification/td-basin-generation" / ("independent-native-state-figure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    image_path = output / "actual-native-water.png"
    figure.savefig(image_path, dpi=145)
    plt.close(figure)
    result = {"schema": "td-independent-native-state-figure-v1", "audit_path": str(Path(audit_path).resolve()),
              "audit_sha256": audit_sha256, "activity_path": str(Path(activity_path).resolve()),
              "activity_sha256": activity_sha256, "image_sha256": file_sha256(image_path),
              "frames": frame_records, "geometry": geometry, "display_depth_threshold_m": .01,
              "display_filter_changes_solver": False, "water_interpolation": False, "hydraulic_ready": False,
              "limitations": "Display hides sheet water below 1cm; native inventory stays unchanged. Internal face totals include repeated transport and are not basin export or instantaneous Q."}
    publish_bytes(output / "report.json", json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return image_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--activity", type=Path, required=True)
    parser.add_argument("--activity-sha256", required=True)
    parser.add_argument("--step-s", type=float, default=2.5)
    arguments = parser.parse_args()
    print(plot(arguments.audit, arguments.audit_sha256, arguments.activity, arguments.activity_sha256, step_s=arguments.step_s))
