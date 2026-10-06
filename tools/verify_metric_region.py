"""Fixed CPU-only real-sample comparison for metric regional processing."""

import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.artifacts import ArtifactIdentity, TerrainArtifact
from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, RegionRecipe
from terrain_pipeline.metric_region_storage import load_metric_region, prepare_metric_region


SOURCES = {
    "plains": ROOT / "verification/tuned-model/plains-geographic_v2-seed20260927-x2176-z8832.npz",
    "plateau": ROOT / "verification/tuned-model/plateau-geographic_v2-seed20260927-x-16000-z-13952.npz",
    "highland": ROOT / "verification/tuned-model/second-seed-highland-geographic_v2-seed20260928-x384-z15488.npz",
}
OUTPUT = ROOT / "verification/metric-region-v1"



def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_base(elevation, metadata, config, source_hash):
    return TerrainArtifact(
        kind="base", identity=ArtifactIdentity(
            backend="TerrainDiffusion/WorldPipeline", algorithm="real_sample_metric_import",
            algorithm_version="1", seed=int(metadata["seed"]),
            parameters={"source_sha256": source_hash, "source_identity": metadata["identity"],
                        "source_metadata": metadata, "generation_config": config}),
        reference_elevation_m=elevation.astype(np.float64) + 126,
        origin_x_m=float(metadata["native_origin"][0]) * 30,
        origin_z_m=float(metadata["native_origin"][1]) * 30,
        spacing_x_m=30, spacing_z_m=30,
        vertical_datum="core bottom = 0 m", sea_level_elevation_m=126)


def stats(region):
    displacement = region.derived.displacement_m[1]
    return {"mean_abs_change_m": float(np.mean(np.abs(displacement))),
            "max_abs_change_m": float(np.max(np.abs(displacement))),
            "changed_fraction_over_0_01m": float(np.mean(np.abs(displacement) > 0.01)),
            "mean_landform_weights": [float(v) for v in region.weights.mean(axis=(0, 1))]}


def main():
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_metric_region")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    from datetime import datetime, timezone
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run = OUTPUT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    run.mkdir()
    recipes = {"literal_metre": RegionRecipe(),
               "moderate_30m": RegionRecipe(trend_sigma_m=90, trend_radius_m=270,
                                            local_sigma_m=45, local_radius_m=135,
                                            coast_sigma_m=60, coast_radius_m=180),
               "metric_30m_v1": METRIC_30M_RECIPE_V1}
    max_halo = tuple(max(recipe.required_halo_samples(30, 30)[axis]
                         for recipe in recipes.values()) for axis in (0, 1))
    report = {"tests_run": result.testsRun, "common_halo_samples_xz": list(max_halo), "samples": {}}
    for sample_name, source_path in SOURCES.items():
        original_hash = sha256(source_path)
        with np.load(source_path, allow_pickle=False) as archive:
            elevation = archive["elevation"]
            metadata = json.loads(str(archive["metadata"].item()))
            config = json.loads(str(archive["generation_config"].item()))
        if elevation.shape != (513, 513) or elevation.dtype != np.float32 or not np.isfinite(elevation).all():
            raise ValueError("unexpected real source grid")
        if metadata.get("native_resolution_m") != 30:
            raise ValueError("unexpected native sample spacing")
        base = make_base(elevation, metadata, config, original_hash)
        sample_report = {"source_sha256": original_hash, "source_spacing_m": 30,
                         "sea_level_m": 126, "candidates": {}}
        report["samples"][sample_name] = sample_report
        for name, recipe in recipes.items():
            destination = run / sample_name / name
            destination.parent.mkdir(exist_ok=True)
            loaded = prepare_metric_region(base, destination, recipe=recipe, halo_samples=max_halo)
            reloaded = load_metric_region(destination)
            if loaded.derived.content_id != reloaded.derived.content_id:
                raise ValueError("published identity changed on reload")
            sample_report["candidates"][name] = {"recipe": recipe.record(),
                                                    "derived_content_id": loaded.derived.content_id,
                                                    "shape_zx": list(loaded.base.reference_elevation_m.shape),
                                                    **stats(loaded)}
        if sha256(source_path) != original_hash:
            raise ValueError("real source changed")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    candidate = load_metric_region(run / "plains" / "metric_30m_v1")
    source_core = candidate.base.reference_elevation_m - 126
    change = candidate.derived.displacement_m[1]
    limits = (float(min(source_core.min(), (source_core + change).min())),
              float(max(source_core.max(), (source_core + change).max())))
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    axes[0].imshow(source_core, cmap="terrain", vmin=limits[0], vmax=limits[1])
    axes[0].set_title("Raw elevation relative to sea (m)")
    axes[1].imshow(source_core + change, cmap="terrain", vmin=limits[0], vmax=limits[1])
    axes[1].set_title("Candidate elevation relative to sea (m)")
    image = axes[2].imshow(change, cmap="coolwarm", vmin=-16, vmax=16)
    axes[2].set_title("Candidate displacement (m)")
    fig.colorbar(image, ax=axes[2], fraction=0.046)
    for axis in axes:
        axis.set_xlabel("30 m samples east")
        axis.set_ylabel("30 m samples south")
    fig.savefig(run / "plains-comparison.png", dpi=130)
    plt.close(fig)
    report["resolution_note"] = ("Literal 2-24 m filter scales are below the 30 m sampling interval; "
                                 "the second recipe is an explicit larger-scale candidate, not an upsampled source.")
    (run / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
