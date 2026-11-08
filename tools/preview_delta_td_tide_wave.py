"""Create a derived Terrain Diffusion delta/tide/wave preview."""
import argparse, json, hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
from terrain_pipeline.surface_rivers.metric_tide_wave_morphology import TideWaveConfig, apply_tide_wave_morphology

def run(scene_path, output):
    scene_path, output = Path(scene_path).resolve(), Path(output).resolve()
    z = np.load(scene_path, allow_pickle=True)
    required = {"bed_m", "raw_td_sample_m", "open_marine_mask", "channel_mask"}
    missing = required - set(z.files)
    if missing: raise ValueError(f"scene missing arrays: {sorted(missing)}")
    bed = np.asarray(z["bed_m"], float)
    td = np.asarray(z["raw_td_sample_m"], float)
    marine = np.asarray(z["open_marine_mask"], bool)
    channels = np.asarray(z["channel_mask"], bool)
    metadata = json.loads(str(z["metadata_json"]))
    spacing = float(metadata.get("spacing_m", 20.0))
    # Preserve delta geometry while using the TD sample as the unmodified base.
    delta_offset = bed - np.asarray(z["base_bed_m"], float)
    td_delta = np.where(np.isfinite(delta_offset), delta_offset, 0.)
    base = td + td_delta
    result = apply_tide_wave_morphology(base, marine, channels, spacing_m=spacing,
        config=TideWaveConfig(tide_range_m=.8, wave_height_m=.6, wave_length_m=900.,
                              active_width_m=3000., max_change_m=.35))
    output.mkdir(parents=True, exist_ok=False)
    arrays = {"base_td_delta_bed_m": base, "tide_wave_height_m": result["height_m"],
              "tide_wave_height_delta_m": result["height_delta_m"],
              "marine_mask": marine, "channel_mask": channels}
    np.savez_compressed(output / "preview.npz", **arrays)
    digest = hashlib.sha256((output / "preview.npz").read_bytes()).hexdigest()
    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
        for ax, data, title in zip(axes, (base, result["height_m"], result["height_delta_m"]),
                                   ("TD + delta", "TD + delta + tide/wave", "tide/wave delta")):
            if title == "tide/wave delta":
                # The morphology delta is defined only on active marine cells.
                # Mask protected cells so zero values do not form a rectangle.
                data = np.where(result["active_mask"], data, np.nan)
                cmap = plt.get_cmap("RdBu_r").copy()
                cmap.set_bad(alpha=0.0)
                ax.set_facecolor("#eeeeee")
            else:
                data = np.where(np.isfinite(data), data, np.nan)
                cmap = "terrain"
            im = ax.imshow(data, cmap=cmap)
            if title == "tide/wave delta":
                ax.contour(marine.astype(float), levels=[0.5], colors="#333333",
                           linewidths=0.45, alpha=0.8)
            ax.set_title(title); fig.colorbar(im, ax=ax, shrink=.75)
        fig.savefig(output / "preview.png", dpi=160); plt.close(fig)
    except Exception as exc:
        (output / "render-error.txt").write_text(str(exc), encoding="utf-8")
    summary = {"schema": "delta-td-tide-wave-preview-v1", "status": "derived_preview",
               "source_scene": str(scene_path), "source_scene_sha256": hashlib.sha256(scene_path.read_bytes()).hexdigest(),
               "source_scene_algorithm": metadata.get("algorithm"), "source_td_role": "raw_td_sample_m",
               "arrays": {k: list(v.shape) for k, v in arrays.items()}, "preview_sha256": digest,
               "spacing_m": spacing, "morphology": result["metadata"],
               "net_volume_m3": result["net_volume_m3"], "limitations": ["derived preview only", "marine bounded; no first-marine channel extension", "no 2-D plume or long-term shoreline"]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return summary

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--scene", required=True); ap.add_argument("--output", required=True)
    print(json.dumps(run(ap.parse_args().scene, ap.parse_args().output), ensure_ascii=False))
