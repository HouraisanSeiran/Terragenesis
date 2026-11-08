"""Plot pinned native-grid refinement differences and actual saved water series."""

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


def plot(report_path, expected_sha256):
    if file_sha256(report_path) != expected_sha256:
        raise ValueError("external comparison report pin mismatch")
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    coarse, metadata = read_record(report["coarse"])
    fine, fine_metadata = read_record(report["fine"])
    for field in ("height_m", "valid_mask", "rain_mm_h", "face_cells"):
        np.testing.assert_array_equal(coarse[field], fine[field])
    if metadata["algorithm"] != fine_metadata["algorithm"]:
        raise ValueError("refinement plot cannot compare different algorithms")
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    if abs(float(difference.max()) - report["max_saved_depth_difference_m"]) > 1e-12:
        raise ValueError("comparison report does not match saved arrays")
    shape = coarse["height_m"].shape
    valid = coarse["valid_mask"]
    spacing = metadata["spacing_m"]
    extent = [0, shape[1] * spacing / 1000, shape[0] * spacing / 1000, 0]
    first_cell = int(np.argmax(difference[1]))
    late_cell = int(np.argmax(difference[-1]))
    time_h = np.arange(len(difference)) * metadata["dt_s"] / 3600
    figure, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    layers = ((coarse["height_m"], "Original TD bed (m)", "terrain", None),
              (difference[1].reshape(shape) * 1000, "First saved hour |coarse-fine| (mm)", "magma", 5),
              (difference.max(axis=0).reshape(shape) * 1000, "Maximum over saved frames (mm)", "magma", 5))
    for axis, (values, title, cmap, maximum) in zip(axes[0], layers):
        drawn = axis.imshow(np.ma.masked_where(~valid, values), extent=extent, cmap=cmap,
                            interpolation="nearest", vmin=None if maximum is None else 0, vmax=maximum)
        axis.set(title=title, xlabel="local X (km)", ylabel="local Z (km)")
        figure.colorbar(drawn, ax=axis, shrink=.8)
        for cell, marker in ((first_cell, "o"), (late_cell, "s")):
            row, column = divmod(cell, shape[1])
            axis.scatter((column + .5) * spacing / 1000, (row + .5) * spacing / 1000,
                         facecolors="none", edgecolors="cyan", marker=marker, s=60)
    for axis, cell, label in ((axes[1, 0], first_cell, "first-hour hotspot"),
                              (axes[1, 1], late_cell, "final-frame hotspot")):
        axis.plot(time_h, coarse["depth_m"][:, cell], label=f"{metadata['substep_s']:g}s")
        axis.plot(time_h, fine["depth_m"][:, cell], "--", label=f"{fine_metadata['substep_s']:g}s")
        axis.set(title=f"Actual depth: cell {cell}, {label}", xlabel="physical hours", ylabel="depth (m)")
        axis.legend()
    axes[1, 2].plot(time_h, difference.max(axis=1) * 1000, marker=".", label="domain saved-frame maximum")
    axes[1, 2].axhline(1, color="red", linestyle="--", label="unchanged 1mm gate")
    axes[1, 2].set(title="Time refinement acceptance", xlabel="physical hours", ylabel="difference (mm)")
    axes[1, 2].legend()
    figure.suptitle(f"{metadata['algorithm']} | Native {shape[1]}x{shape[0]}, {spacing:g}m | Engineering boundaries")
    output = ROOT / "verification/td-basin-generation" / ("independent-refinement-figure-" +
             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    path = output / "td-refinement-review.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    record = {"schema": "td-refinement-native-figure-v1", "comparison_path": str(Path(report_path).resolve()),
              "comparison_sha256": expected_sha256, "coarse": report["coarse"], "fine": report["fine"],
              "image_sha256": file_sha256(path), "native_grid": list(shape), "spacing_m": spacing,
              "algorithm": metadata["algorithm"], "first_hour_cell": first_cell, "final_frame_cell": late_cell,
              "water_interpolation": False, "solver_advanced": False, "hydraulic_ready": False,
              "limitations": "Hourly saved native samples and timestep differences, not observed river channels or instantaneous discharge."}
    publish_bytes(output / "report.json", json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args()
    print(plot(arguments.comparison, arguments.expected_sha256))
