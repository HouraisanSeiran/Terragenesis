"""Static independent review figure from externally pinned, already solved TD arrays."""

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

from tools.audit_td_basin_generation import file_record, read_saved
from terrain_pipeline.mountain_source_adapter import publish_bytes
from terrain_pipeline.mountain_source_adapter import file_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--storage-report-sha256", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if file_sha256(args.storage_dir / "report.json") != args.storage_report_sha256:
        raise ValueError("external storage report pin mismatch")
    storage_report = json.loads((args.storage_dir / "report.json").read_text(encoding="utf-8"))
    base = ROOT / "verification/td-basin-generation"
    hierarchy_path = base / "A-20261001T184113155960Z/hierarchy.npz"
    topology, metadata = read_saved(hierarchy_path, "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422")
    material_path = base / "B-20261001T184152639830Z/material/material.npz"
    material, unused = read_saved(material_path, "598d50701e02c9419ebc8ec47e1cc46a881e869e58d8837ac38a3eac45cf7b3a")
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "inputs": [file_record(hierarchy_path), file_record(material_path)],
              "renderer": file_record(__file__), "hydraulic_ready": False, "natural_outlet_verified": False,
              "storage_report_sha256": args.storage_report_sha256,
              "limitations": "Saved baseline only; whole-domain numerical sensitivity and physical calibration require separate evidence. No derived terrain is shown."}
    shape = topology["height_m"].shape
    extent = (0, shape[1] * metadata["spacing_m"] / 1000, shape[0] * metadata["spacing_m"] / 1000, 0)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False})
    figure, axes = plt.subplots(2, 3, figsize=(15, 10), constrained_layout=True)
    layers = [("TD 原床高程（m）", topology["height_m"], "terrain"),
              ("原床贡献盆地：1085 叶", topology["contribution_owner"], "turbo"),
              ("连续合成可侵蚀层厚度（m）", material["erodible_thickness_m"], "viridis")]
    for axis, (title, values, palette) in zip(axes[0], layers):
        plotted = axis.imshow(values, extent=extent, cmap=palette)
        axis.set_title(title)
        axis.set_xlabel("局部 X（km，东）")
        axis.set_ylabel("局部 Z（km，南）")
        if palette != "turbo":
            figure.colorbar(plotted, ax=axis, shrink=.8)
    for column, name in enumerate(("ordinary", "strong")):
        info = storage_report["scenarios"][name]
        path = args.storage_dir / (name + ".npz")
        arrays, hydro_metadata = read_saved(path, info["archive_sha256"])
        report["inputs"].append(file_record(path))
        depth = arrays["depth_m"][-1].reshape(shape)
        axis = axes[1, column]
        axis.imshow(topology["height_m"], extent=extent, cmap="Greys", alpha=.5)
        plotted = axis.imshow(np.ma.masked_less_equal(depth, 1e-4), extent=extent, cmap="Blues", vmin=0,
                              vmax=max(.001, float(depth.max())))
        axis.set_title(("普通雨" if name == "ordinary" else "强雨") + " 24h 求解水深（m）")
        axis.set_xlabel("局部 X（km，东）")
        axis.set_ylabel("局部 Z（km，南）")
        figure.colorbar(plotted, ax=axis, shrink=.8)
        volume = arrays["depth_m"].sum(axis=1) * metadata["spacing_m"] ** 2
        axes[1, 2].plot(np.arange(len(volume)) * hydro_metadata["dt_s"] / 3600, volume / 1e6,
                        label="普通雨" if name == "ordinary" else "强雨")
        report[name] = {"algorithm": hydro_metadata["algorithm"], "substep_s": hydro_metadata["substep_s"],
                        "final_surface_m3": float(volume[-1]), "max_final_depth_m": float(depth.max()),
                        "rain_volume_m3": float(arrays["rain_volume_m3"].sum())}
        del arrays
    axes[1, 2].set_title("地表库存过程（不含土壤/快慢库）")
    axes[1, 2].set_xlabel("物理时间（h）")
    axes[1, 2].set_ylabel("库存（百万 m³）")
    axes[1, 2].legend()
    figure.suptitle("真实尺度 TD 盆地与冻结水文审查\n原床未改；全域时间步收敛与物理标定按独立证据验收", fontsize=15)
    args.output.mkdir(parents=True)
    figure.savefig(args.output / "td-basin-baseline-review.png", dpi=140)
    plt.close(figure)
    report["figure"] = file_record(args.output / "td-basin-baseline-review.png")
    publish_bytes(args.output / "report.json", (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(report["figure"], ensure_ascii=True))


if __name__ == "__main__":
    main()
