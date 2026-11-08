"""Prepare unchanged TD macro/residual coast and one imported river boundary."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_td_delta_initialization import prepare_td_initialization

SCENE = ROOT/".scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-15/scene.npz"


def run(output):
    with np.load(SCENE) as saved:
        meta = json.loads(str(saved["metadata_json"]))
        arrays, report = prepare_td_initialization(saved["base_bed_m"], saved["macro_bed_m"],
            saved["raw_td_sample_m"], saved["td_residual_m"], source_origin_xz=meta["origin_xz_m"],
            source_spacing_m=meta["spacing_m"], mouth_xz=meta["mouth_xz_m"], direction_xz=meta["river_direction_xz"])
    report["source_scene"] = str(SCENE)
    report["source_sha256"] = file_sha256(SCENE)
    report["implementation_hashes"] = {str(path.relative_to(ROOT)): file_sha256(path) for path in
        (Path(__file__), ROOT/"terrain_pipeline/surface_rivers/metric_td_delta_initialization.py")}
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output/"initialization.npz", **arrays)
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15, 7))
    for ax, field, title, cmap in zip(axes, (arrays["initial_bed_m"], arrays["initial_depth_m"], arrays["cell_type"]),
        ("Original TD coast + single upstream stub", "Initial hydrostatic stage-depth", "Boundary labels; interior land mobile"),
        ("terrain", "Blues", "tab10")):
        image = ax.imshow(field, extent=[-300, 300, 740, -60], cmap=cmap)
        ax.contour(arrays["initial_bed_m"], [0.], extent=[-300, 300, 740, -60], origin="upper", colors="black", linewidths=.6)
        ax.set_title(title); ax.set_xlabel("Cross-stream (m)"); ax.set_ylabel("From actual mouth (m)")
        fig.colorbar(image, ax=ax, shrink=.65)
    fig.tight_layout(); fig.savefig(output/"initialization.png", dpi=170); plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT/"verification/fluvial-delta/natural-td-initialization-20261018-01")
    run(parser.parse_args().output)
