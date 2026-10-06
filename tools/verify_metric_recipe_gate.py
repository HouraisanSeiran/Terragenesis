"""Recompute three real samples and compare physical-scale recipe candidates."""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, RegionRecipe, process_region
from tools.verify_metric_region import SOURCES, make_base

RECIPES = {
    "literal_metre": RegionRecipe(),
    "moderate_30m": RegionRecipe(trend_sigma_m=90, trend_radius_m=270,
                                  local_sigma_m=45, local_radius_m=135,
                                  coast_sigma_m=60, coast_radius_m=180),
    "metric_30m_v1": METRIC_30M_RECIPE_V1,
}
OUTPUT = ROOT / "verification/metric-region-v1/final-recipe-gate.json"


def roughness(values: np.ndarray) -> float:
    return float(np.mean(np.abs(values[1:, :] - values[:-1, :])) +
                 np.mean(np.abs(values[:, 1:] - values[:, :-1])))


def main() -> None:
    result = {"decision": "metric_30m_v1", "criteria": {
        "sample_spacing_m": 30, "max_displacement_m": 16,
        "plains_roughness_reduction_fraction": [0.001, 0.05],
        "plateau_highland_mean_change_m_max": 0.1,
        "coast_within_1m_unchanged": True,
        "source_extrema_change_m_max": 16}, "samples": {}}
    halo = max(recipe.required_halo_samples(30, 30)[0] for recipe in RECIPES.values())
    for name, path in SOURCES.items():
        original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        with np.load(path, allow_pickle=False) as archive:
            elevation = archive["elevation"]
            metadata = json.loads(str(archive["metadata"].item()))
            config = json.loads(str(archive["generation_config"].item()))
        base = make_base(elevation, metadata, config, original_hash)
        before = base.reference_elevation_m[halo:-halo, halo:-halo]
        sample = {"source_sha256": original_hash, "candidates": {}}
        result["samples"][name] = sample
        for candidate_name, recipe in RECIPES.items():
            processed = process_region(base.reference_elevation_m, 126, 30, 30, recipe=recipe)
            after = processed.elevation_m[halo:-halo, halo:-halo]
            change = after - before
            coast = np.abs(before - 126) <= 1
            metrics = {"mean_abs_change_m": float(np.mean(np.abs(change))),
                       "max_abs_change_m": float(np.max(np.abs(change))),
                       "roughness_reduction_fraction": 1 - roughness(after) / roughness(before),
                       "min_change_m": float(after.min() - before.min()),
                       "max_change_m": float(after.max() - before.max()),
                       "coast_cell_count": int(coast.sum()),
                       "coast_max_change_m": (float(np.max(np.abs(change[coast])))
                                              if np.any(coast) else None)}
            sample["candidates"][candidate_name] = metrics
        if hashlib.sha256(path.read_bytes()).hexdigest() != original_hash:
            raise AssertionError(f"{name}: source changed")
        chosen = sample["candidates"]["metric_30m_v1"]
        if (chosen["max_abs_change_m"] > 16
                or (chosen["coast_cell_count"] and chosen["coast_max_change_m"] != 0)
                or max(abs(chosen["min_change_m"]), abs(chosen["max_change_m"])) > 16):
            raise AssertionError(f"{name}: protection or displacement budget failed")
        if name == "plains" and not 0.001 <= chosen["roughness_reduction_fraction"] <= 0.05:
            raise AssertionError("plains roughness gate failed")
        if name != "plains" and chosen["mean_abs_change_m"] > 0.1:
            raise AssertionError(f"{name}: disturbance budget failed")
        print(name, json.dumps(sample["candidates"], separators=(",", ":")))
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
