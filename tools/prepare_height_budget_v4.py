"""Finite v4 batch screening and all-or-nothing publication by seed."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from diffusion.backend import TerrainDiffusionBackend
from diffusion.config import GenerationConfig
from diffusion.paths import configure
from terrain_pipeline.artifacts import ArtifactIdentity, TerrainArtifact
from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, process_region
from terrain_pipeline.metric_region_storage import prepare_metric_region
from terrain_pipeline.minecraft_export import export_metric_minecraft
from terrain_pipeline.minecraft_export import (SOFT_TARGET_SURFACE_Y,
                                                MAX_BUILD_SURFACE_Y,
                                                MIN_BUILD_SURFACE_Y)


OUTPUT_ROOT = ROOT / "verification/height-budget-v4"
CANDIDATES = ((.12, .18, 80.0), (.08, .18, 60.0), (.04, .18, 40.0))
SCREEN = ((20260930, 0, 0), (20260930, 11520, 15360),
          (20260931, 0, 0), (20260931, 11520, 15360))
HOLDOUT_SEEDS = (20261001, 20261002)
ORIGINS = ((-16000, -13952), (384, 15488), (0, 0), (11520, 15360))
SIZE = 513
SPACING_M = 30
HALO_X, HALO_Z = METRIC_30M_RECIPE_V1.required_halo_samples(SPACING_M, SPACING_M)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def height_result(elevation):
    game_y = elevation.astype(np.float64) + 62
    if not np.isfinite(game_y).all():
        raise ValueError("nonfinite generated height")
    minimum, maximum = float(game_y.min()), float(game_y.max())
    slope_z, slope_x = np.gradient(elevation.astype(np.float64), SPACING_M, SPACING_M)
    return {"min_y": minimum, "max_y": maximum,
            "above_y800_percent": float(np.mean(game_y > SOFT_TARGET_SURFACE_Y) * 100),
            "below_y_minus64_percent": float(np.mean(game_y < MIN_BUILD_SURFACE_Y) * 100),
            "slope_m_per_m_p95": float(np.percentile(np.hypot(slope_x, slope_z), 95)),
            "relief_p95_minus_p5_m": float(np.percentile(elevation, 95) -
                                           np.percentile(elevation, 5)),
            "height_pass": minimum >= MIN_BUILD_SURFACE_Y and maximum <= MAX_BUILD_SURFACE_Y,
            "exceedance_y": max(0, maximum - MAX_BUILD_SURFACE_Y) +
                            max(0, MIN_BUILD_SURFACE_Y - minimum)}


def evaluate_candidate(directory, candidate, jobs, name):
    land, relief, depth = candidate
    config = GenerationConfig.for_profile("geographic_v4", v4_land_base_factor=land,
                                          v4_mountain_relief_factor=relief,
                                          v4_ocean_depth_m=depth)
    backend = TerrainDiffusionBackend(config)
    directory.mkdir()
    record = {"name": name, "candidate": {"land_base_factor": land,
              "mountain_relief_factor": relief, "ocean_depth_m": depth},
              "generation_identity": backend.identity, "generation_config": config.record(),
              "jobs": [list(job) for job in jobs], "samples": [], "status": "running"}
    write_json(directory / "report.json", record)
    try:
        for seed, x, z in jobs:
            stem = f"seed{seed}-x{x}-z{z}"
            elevation, climate, metadata = backend.generate(seed, x, z, SIZE)
            if elevation.shape != (SIZE, SIZE) or metadata["native_resolution_m"] != SPACING_M:
                raise ValueError("unexpected generation grid or metre spacing")
            raw_path = directory / f"{stem}.npz"
            np.savez_compressed(raw_path, elevation=elevation, climate=climate,
                                metadata=json.dumps(metadata),
                                generation_config=json.dumps(config.record()))
            sample = {"seed": seed, "native_origin": [x, z],
                      "raw_npz": raw_path.name, "raw_sha256": sha256(raw_path),
                      "generation_seconds": metadata["seconds"],
                      "raw_full": height_result(elevation)}
            record["samples"].append(sample)
            write_json(directory / "report.json", record)
            core_elevation = elevation.astype(np.float64) + 126
            processed = process_region(core_elevation, 126, SPACING_M, SPACING_M,
                                       recipe=METRIC_30M_RECIPE_V1).elevation_m
            interior = np.s_[HALO_Z:SIZE-HALO_Z, HALO_X:SIZE-HALO_X]
            sample["raw_interior"] = height_result(elevation[interior])
            sample["processed_interior"] = height_result(processed[interior] - 126)
            sample["height_pass"] = (sample["raw_full"]["height_pass"] and
                                     sample["processed_interior"]["height_pass"])
            write_json(directory / "report.json", record)
            print(f"{name} {stem}: raw Y {sample['raw_full']['min_y']:.1f}.."
                  f"{sample['raw_full']['max_y']:.1f}, processed Y "
                  f"{sample['processed_interior']['min_y']:.1f}.."
                  f"{sample['processed_interior']['max_y']:.1f}, pass={sample['height_pass']}", flush=True)
        record["status"] = "height_pass" if all(s["height_pass"] for s in record["samples"]) else "height_fail"
    except Exception as error:
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"
        write_json(directory / "report.json", record)
        raise
    finally:
        backend.close()
        write_json(directory / "report.json", record)
    return record


def publish_batch(directory, record):
    if record["status"] != "height_pass":
        raise ValueError("entire batch must pass height checks before publication")
    if (not record["jobs"] or len(record["jobs"]) != len(record["samples"]) or
            len({tuple(job) for job in record["jobs"]}) != len(record["jobs"]) or
            len({job[0] for job in record["jobs"]}) != 1 or
            {(sample["seed"], *sample["native_origin"]) for sample in record["samples"]}
            != {tuple(job) for job in record["jobs"]} or
            any(not sample["raw_full"]["height_pass"] or
                not sample["processed_interior"]["height_pass"] for sample in record["samples"])):
        raise ValueError("incomplete or mixed-seed batch cannot be published")
    staging = directory / "publication.staging"
    published = directory / "publication"
    if staging.exists() or published.exists():
        raise FileExistsError(published)
    staging.mkdir()
    snapshot_hashes = {}
    try:
        for sample in record["samples"]:
            with np.load(directory / sample["raw_npz"], allow_pickle=False) as archive:
                elevation = archive["elevation"].copy()
                metadata = json.loads(str(archive["metadata"].item()))
                stored_config = json.loads(str(archive["generation_config"].item()))
            if sha256(directory / sample["raw_npz"]) != sample["raw_sha256"]:
                raise ValueError("raw source changed before publication")
            seed, (x, z) = sample["seed"], sample["native_origin"]
            if (metadata["identity"] != record["generation_identity"] or
                    int(metadata["seed"]) != seed or metadata["native_origin"] != [x, z] or
                    metadata["native_resolution_m"] != SPACING_M or
                    elevation.shape != (SIZE, SIZE) or
                    stored_config != json.loads(json.dumps(record["generation_config"]))):
                raise ValueError("raw source identity or coordinates differ from batch")
            if not height_result(elevation)["height_pass"]:
                raise ValueError("raw full grid fails height check before publication")
            stem = f"seed{seed}-x{x}-z{z}"
            base = TerrainArtifact(kind="base", identity=ArtifactIdentity(
                backend="TerrainDiffusion/WorldPipeline", algorithm="geographic_v4_metric_import",
                algorithm_version="1", seed=seed,
                parameters={"generation_identity": record["generation_identity"],
                            "source_sha256": sample["raw_sha256"],
                            "generation_config": json.loads(json.dumps(record["generation_config"]))}),
                reference_elevation_m=elevation.astype(np.float64) + 126,
                origin_x_m=x * SPACING_M, origin_z_m=z * SPACING_M,
                spacing_x_m=SPACING_M, spacing_z_m=SPACING_M,
                vertical_datum="core bottom = 0 m", sea_level_elevation_m=126)
            region_path = staging / f"{stem}-region"
            snapshot_path = staging / f"{stem}.tgmc"
            prepare_metric_region(base, region_path)
            export_metric_minecraft(region_path, snapshot_path)
            snapshot_hashes[stem] = sha256(snapshot_path)
        write_json(staging / "manifest.json", {"generation_identity": record["generation_identity"],
                                             "jobs": record["jobs"],
                                             "snapshot_sha256": snapshot_hashes})
        staging.rename(published)
        record["status"] = "published"
        record["snapshot_sha256"] = snapshot_hashes
        write_json(directory / "report.json", record)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def prepare_batch_with_retry(directory, seed, origins, candidates=CANDIDATES):
    """Try at most three whole-batch configs; publish the first complete pass."""
    if len(candidates) == 0 or len(candidates) > 3:
        raise ValueError("batch requires one to three explicit candidates")
    if not origins or len(set(origins)) != len(origins):
        raise ValueError("batch requires distinct explicit windows")
    directory.mkdir()
    jobs = [(seed, x, z) for x, z in origins]
    result = {"seed": seed, "jobs": [list(job) for job in jobs],
              "candidates": [list(candidate) for candidate in candidates],
              "attempts": [], "status": "running"}
    write_json(directory / "batch.json", result)
    for index, candidate in enumerate(candidates, 1):
        attempt_dir = directory / f"candidate-{index}"
        attempt_entry = {"candidate_index": index, "status": "running",
                         "report": f"candidate-{index}/report.json"}
        result["attempts"].append(attempt_entry)
        write_json(directory / "batch.json", result)
        try:
            attempt = evaluate_candidate(attempt_dir, candidate, jobs, f"candidate-{index}")
            attempt_entry["status"] = attempt["status"]
            write_json(directory / "batch.json", result)
            if attempt["status"] == "height_pass":
                publish_batch(attempt_dir, attempt)
                result["status"] = "published"
                result["selected_candidate_index"] = index
                attempt_entry["status"] = "published"
                write_json(directory / "batch.json", result)
                return result
        except Exception as error:
            attempt_entry["status"] = "error"
            result["status"] = "error"
            result["error"] = f"{type(error).__name__}: {error}"
            write_json(directory / "batch.json", result)
            raise
    result["status"] = "height_fail"
    write_json(directory / "batch.json", result)
    return result


def main():
    configure()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir()
    summary = {"purpose": "fixed v4 joint-parameter candidate screening and holdout",
               "run_dir": str(run_dir.relative_to(ROOT)), "candidates": [list(c) for c in CANDIDATES],
               "hard_height_bounds_y": [MIN_BUILD_SURFACE_Y, MAX_BUILD_SURFACE_Y],
               "soft_target_y": SOFT_TARGET_SURFACE_Y,
               "screen_jobs": [list(job) for job in SCREEN],
               "holdout_seeds": list(HOLDOUT_SEEDS), "holdout_origins": [list(o) for o in ORIGINS],
               "size": SIZE, "native_resolution_m": SPACING_M,
               "halo_samples": [HALO_X, HALO_Z], "screen": [], "holdout": []}
    write_json(run_dir / "summary.json", summary)
    for index, candidate in enumerate(CANDIDATES, 1):
        result = evaluate_candidate(run_dir / f"screen-candidate-{index}", candidate, SCREEN,
                                    f"screen-{index}")
        summary["screen"].append({"candidate_index": index, "status": result["status"],
                                  "report": f"screen-candidate-{index}/report.json"})
        write_json(run_dir / "summary.json", summary)
    def rank(index):
        result = json.loads((run_dir / f"screen-candidate-{index}" / "report.json").read_text(encoding="utf-8"))
        failures = sum(not sample["height_pass"] for sample in result["samples"])
        exceedance = sum(sample["raw_full"]["exceedance_y"] +
                         sample["processed_interior"]["exceedance_y"] for sample in result["samples"])
        return failures, exceedance, index
    selected_index = min(range(1, len(CANDIDATES) + 1), key=rank)
    summary["selected_candidate_index"] = selected_index
    summary["screen_selected_all_pass"] = rank(selected_index)[0] == 0
    summary["selection_note"] = ("Selected by fewest failed windows then total height exceedance; "
                                 "a failed screen candidate is for holdout research only, not publication advice.")
    write_json(run_dir / "summary.json", summary)
    candidate = CANDIDATES[selected_index - 1]
    # The holdout is a research check of the screen selection, not a second tuning loop.
    for seed in HOLDOUT_SEEDS:
        name = f"holdout-seed{seed}"
        result = prepare_batch_with_retry(run_dir / name, seed, ORIGINS, (candidate,))
        summary["holdout"].append({"seed": seed, "status": result["status"],
                                   "report": f"{name}/batch.json"})
        write_json(run_dir / "summary.json", summary)
    print(run_dir, flush=True)


if __name__ == "__main__":
    main()
