"""Plot independently audited native rainfall samples without interpolating weather."""

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


def plot(audit_path, expected_sha256):
    audit_path = Path(audit_path).resolve(strict=True)
    if file_sha256(audit_path) != expected_sha256:
        raise ValueError("external independent rainfall audit pin mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["all_native_weather_gates_passed"] is not True:
        raise ValueError("independently accepted native weather required")
    index_path = Path(audit["index"])
    if file_sha256(index_path) != audit["index_sha256"]:
        raise ValueError("audited weather index changed")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    source, grid = read_record(index["source"])
    figure, axes = plt.subplots(3, 4, figsize=(16, 11), constrained_layout=True)
    spacing = grid["spacing_m"]
    origin_x, origin_z = grid["origin_m_xz"]
    extent = [(origin_x - spacing / 2) / 1000,
              (origin_x + (source["height_m"].shape[1] - .5) * spacing) / 1000,
              (origin_z + (source["height_m"].shape[0] - .5) * spacing) / 1000,
              (origin_z - spacing / 2) / 1000]
    for row, direction in enumerate(("eastward", "westward")):
        arrays, metadata = read_record(index["cases"][direction]["record"])
        rain = arrays["rain_mm_h"]
        valid = arrays["valid_mask"]
        for column, step in enumerate((0, 2, 5)):
            rendered = axes[row, column].imshow(np.ma.masked_where(~valid, rain[step]),
                extent=extent, interpolation="nearest", cmap="Blues", vmin=0, vmax=30)
            axes[row, column].set(title=f"{direction}: hour {step}-{step + 1} mean (mm/h)",
                                  xlabel="source X (km)", ylabel="source Z (km)")
            figure.colorbar(rendered, ax=axes[row, column], shrink=.7)
        accumulated = rain.sum(axis=0) * metadata["plan"]["dt_s"] / 3600
        rendered = axes[row, 3].imshow(np.ma.masked_where(~valid, accumulated), extent=extent,
            interpolation="nearest", cmap="Blues", vmin=0, vmax=120)
        axes[row, 3].set(title=f"{direction}: total rain depth (mm)", xlabel="source X (km)", ylabel="source Z (km)")
        figure.colorbar(rendered, ax=axes[row, 3], shrink=.7)
        axes[2, 1].plot(np.arange(24) + .5, arrays["interval_rain_m3"] / 1e6, label=direction)
        weighted_x = (origin_x + np.arange(valid.shape[1]) * spacing)[None, :]
        centroids = np.divide((rain * weighted_x).sum(axis=(1, 2)), rain.sum(axis=(1, 2)),
                              out=np.full(24, np.nan), where=rain.sum(axis=(1, 2)) > 0)
        axes[2, 2].plot(np.arange(24) + .5, centroids / 1000, label=direction)
    rendered = axes[2, 0].imshow(np.ma.masked_where(~source["valid_mask"], source["height_m"]),
        extent=extent, interpolation="nearest", cmap="terrain")
    axes[2, 0].set(title="Original Terrain Diffusion bed (m)", xlabel="source X (km)", ylabel="source Z (km)")
    figure.colorbar(rendered, ax=axes[2, 0], shrink=.7)
    axes[2, 1].set(title="Actual domain rain volume", xlabel="physical hours", ylabel="million cubic metres per hour")
    axes[2, 2].set(title="Rain-weighted centroid", xlabel="physical hours", ylabel="source X (km)")
    axes[2, 1].legend()
    axes[2, 2].legend()
    axes[2, 3].axis("off")
    axes[2, 3].text(0, .9, "256 x 256 native cells, 30 m\n2 x 2 equal-area spatial samples\nIndependent full-grid time quadrature\n6 h active rain, 18 h dry\nParameterized scenario, not forecast\nRain forcing only: no water solved\nOriginal bed preserved", va="top", fontsize=11)
    figure.suptitle("Native moving rainfall on the fixed TD mountain source | No spatial interpolation")
    output = ROOT / "verification/td-native-storm-forcing" / ("figure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    path = output / "native-moving-rainfall.png"
    figure.savefig(path, dpi=150)
    plt.close(figure)
    record = dict(audit_path=str(audit_path), audit_sha256=expected_sha256,
        index_sha256=audit["index_sha256"], image_sha256=file_sha256(path),
        water_solved=False, interpolation=False, plotter_sha256=file_sha256(__file__))
    publish_bytes(output / "report.json", json.dumps(record, indent=2).encode("utf-8"))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    print(plot(args.audit, args.expected_sha256))
