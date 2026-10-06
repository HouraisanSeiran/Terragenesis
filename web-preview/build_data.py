"""Export saved Java-processed NPZ samples as small local preview JSON files."""
from pathlib import Path
import json
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "verification" / "region-processing"
OUTPUT = Path(__file__).resolve().parent / "data"
STRIDE = 4


def main() -> None:
    reports = json.loads((SAMPLES / "report.json").read_text(encoding="utf-8"))
    OUTPUT.mkdir(exist_ok=True)
    manifest = []
    for path in sorted(SAMPLES.glob("*-derived.npz")):
        name = path.name.removesuffix("-derived.npz")
        if name not in reports:
            raise ValueError(f"Missing report for {name}")
        with np.load(path, allow_pickle=False) as data:
            raw = data["raw_height"]
            processed = data["processed_height"]
            weights = data["weights"]
            types = data["dominant_type"]
            origin = data["origin_world"].tolist()
            spacing = int(data["spacing_blocks"])
            algorithm = str(data["algorithm_id"])
        if raw.shape != processed.shape or weights.shape != (*raw.shape, 4) or types.shape != raw.shape:
            raise ValueError(f"Invalid grid shape: {name}")
        if not np.isfinite(raw).all() or not np.isfinite(processed).all() or not np.isfinite(weights).all():
            raise ValueError(f"Non-finite grid: {name}")
        if np.any((weights < 0) | (weights > 1)) or not np.allclose(weights.sum(axis=2), 1, atol=.001):
            raise ValueError(f"Invalid weights: {name}")
        if not np.isin(types, [0, 1, 2, 3]).all() or spacing != 2 or origin != reports[name]["origin_world"]:
            raise ValueError(f"Invalid labels or coordinates: {name}")
        if algorithm != reports[name]["algorithm_id"]:
            raise ValueError(f"Algorithm identity mismatch: {name}")
        sampled = np.s_[::STRIDE, ::STRIDE]
        payload = {"name": name, "width": int(raw[sampled].shape[1]),
                   "height": int(raw[sampled].shape[0]), "origin": origin,
                   "spacing": spacing * STRIDE, "sourceSpacing": spacing,
                   "sourceShape": list(raw.shape), "seed": reports[name]["seed"],
                   "algorithm": algorithm, "seaLevel": 62,
                   "raw": raw[sampled].round(4).ravel().tolist(),
                   "processed": processed[sampled].round(4).ravel().tolist(),
                   "weights": weights[sampled].round(5).reshape(-1, 4).tolist(),
                   "types": types[sampled].ravel().tolist(),
                   "report": reports[name]}
        file_name = name + ".json"
        (OUTPUT / file_name).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        manifest.append({"name": name, "file": file_name, "seed": payload["seed"]})
    if not manifest:
        raise ValueError("No saved derived NPZ samples found")
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(manifest)} saved samples to {OUTPUT}")


if __name__ == "__main__":
    main()