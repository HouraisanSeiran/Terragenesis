"""Run fixed real-model height-budget samples without changing generation defaults."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from diffusion.backend import TerrainDiffusionBackend
from diffusion.config import GenerationConfig
from diffusion.paths import configure
from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, process_region


OUTPUT_ROOT = ROOT / "verification" / "height-budget-benchmark"
SEEDS = (20260930, 20260931, 20260932)
ORIGINS = ((-16000, -13952), (384, 15488), (0, 0), (11520, 15360))
SIZE = 513
SPACING_M = 30
SEA_Y = 62
MAX_Y = 800
MIN_Y = -64
RECIPE = METRIC_30M_RECIPE_V1
HALO_X, HALO_Z = RECIPE.required_halo_samples(SPACING_M, SPACING_M)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stats(height_m: np.ndarray) -> dict:
    game_y = height_m.astype(np.float64) + SEA_Y
    slope_z, slope_x = np.gradient(height_m.astype(np.float64), SPACING_M, SPACING_M)
    slope = np.hypot(slope_x, slope_z)
    return {
        "game_y_min": float(game_y.min()), "game_y_max": float(game_y.max()),
        "game_y_p50": float(np.percentile(game_y, 50)),
        "game_y_p95": float(np.percentile(game_y, 95)),
        "game_y_p99": float(np.percentile(game_y, 99)),
        "above_y800_percent": float(np.mean(game_y > MAX_Y) * 100),
        "below_y_minus64_percent": float(np.mean(game_y < MIN_Y) * 100),
        "slope_m_per_m_p95": float(np.percentile(slope, 95)),
        "relief_p95_minus_p5_m": float(np.percentile(height_m, 95) - np.percentile(height_m, 5)),
    }


def _sample(run_dir: Path, backend: TerrainDiffusionBackend, seed: int,
            x: int, z: int, snr: float, phase: str) -> dict:
    stem = f"{phase}-snr{snr:g}-seed{seed}-x{x}-z{z}"
    archive_path = run_dir / f"{stem}.npz"
    report_path = run_dir / f"{stem}.json"
    record = {"phase": phase, "seed": seed, "native_origin": [x, z],
              "size": SIZE, "elevation_snr": snr, "status": "failed",
              "generation_identity": backend.identity,
              "generation_config": asdict(backend.config),
              "source_metadata": backend.metadata,
              "archive": archive_path.name}
    started = time.perf_counter()
    try:
        elevation, climate, metadata = backend.generate(seed, x, z, SIZE)
        record["generation_seconds"] = float(metadata["seconds"])
        record["native_resolution_m"] = metadata["native_resolution_m"]
        record["backend_metadata"] = metadata
        if (elevation.shape != (SIZE, SIZE) or not np.isfinite(elevation).all() or
                metadata["native_resolution_m"] != SPACING_M):
            raise ValueError("unexpected model elevation shape, resolution or finite state")
        np.savez_compressed(archive_path, elevation=elevation, climate=climate,
                            metadata=json.dumps(metadata),
                            generation_config=json.dumps(asdict(backend.config)))
        record["archive_sha256"] = _sha256(archive_path)
        record["raw_full"] = _stats(elevation)
        raw_game_y = elevation.astype(np.float64) + SEA_Y
        record["raw_full_peak_y"] = float(raw_game_y.max())
        # The model stores sea-relative metres; the processor uses the core datum at 126 m.
        core_elevation = elevation.astype(np.float64) + 126
        processed_core = process_region(core_elevation, 126, SPACING_M, SPACING_M,
                                        recipe=RECIPE).elevation_m
        processed = processed_core - 126
        interior = np.s_[HALO_Z:SIZE - HALO_Z, HALO_X:SIZE - HALO_X]
        record["interior_shape"] = list(elevation[interior].shape)
        record["raw_interior"] = _stats(elevation[interior])
        record["processed_interior"] = _stats(processed[interior])
        record["height_eligible_raw_full"] = bool(raw_game_y.min() >= MIN_Y and raw_game_y.max() <= MAX_Y)
        processed_y = processed[interior] + SEA_Y
        record["height_eligible_processed_interior"] = bool(processed_y.min() >= MIN_Y and processed_y.max() <= MAX_Y)
        record["status"] = "complete"
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        record["traceback"] = traceback.format_exc()
    record["elapsed_seconds"] = time.perf_counter() - started
    _write_json(report_path, record)
    print(f"{stem}: {record['status']} ({record['elapsed_seconds']:.1f}s)", flush=True)
    return record


def _brief(summary: dict) -> str:
    baseline = summary["baseline"]
    complete = [sample for sample in baseline if sample["status"] == "complete"]
    failed = [sample for sample in baseline if sample["status"] != "complete"]
    above = [sample for sample in complete if sample["raw_full"]["above_y800_percent"] > 0 or
             sample["processed_interior"]["above_y800_percent"] > 0]
    below = [sample for sample in complete if sample["raw_full"]["below_y_minus64_percent"] > 0 or
             sample["processed_interior"]["below_y_minus64_percent"] > 0]
    lines = ["# 高度预算真实模型抽样简报", "",
             "这是预先固定的 3 个种子、4 个目的性窗口，并非全球随机抽样；不能据此估计全球通过率。",
             f"基线完成 {len(complete)}/12，失败 {len(failed)}；超出 Y800 或低于 Y-64 均不可导出。",
             f"基线上限拒绝 {len(above)} 个，底部拒绝 {len(below)} 个（可能重叠）。失败样本仍计入总数。", "",
             "这里只检查高度是否合格，并未实际导出，也未检查其他导出约束。", "",
             "| 种子 | 原点 | 原始全幅最高Y | 加工同域最高Y | 原始全幅高度合格 | 加工同域高度合格 |",
             "| --- | --- | ---: | ---: | --- | --- |"]
    for sample in baseline:
        x, z = sample["native_origin"]
        if sample["status"] == "complete":
            lines.append(f"| {sample['seed']} | ({x},{z}) | {sample['raw_full_peak_y']:.2f} | "
                         f"{sample['processed_interior']['game_y_max']:.2f} | "
                         f"{sample['height_eligible_raw_full']} | {sample['height_eligible_processed_interior']} |")
        else:
            lines.append(f"| {sample['seed']} | ({x},{z}) | 失败 | 失败 | 失败 | 失败 |")
    lines += ["", "配对实验仅对基线原始全幅最高 Y 的三个已完成窗口运行 SNR 0.05 和 0.2；",
              "完整分布、坡度、起伏、耗时、身份与哈希见各样本 JSON 及 summary.json。", ""]
    return "\n".join(lines)


def main() -> None:
    configure()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir()
    jobs = [(seed, x, z) for seed in SEEDS for x, z in ORIGINS]
    summary = {"purpose": "fixed geographic_v3 height budget benchmark, not global random sampling",
               "run_dir": str(run_dir.relative_to(ROOT)), "size": SIZE,
               "native_resolution_m": SPACING_M, "recipe": RECIPE.record(),
               "halo_samples": [HALO_X, HALO_Z], "sea_y": SEA_Y,
               "publication_bounds_y": [MIN_Y, MAX_Y],
               "eligibility_note": "Height bounds only; no Minecraft snapshot export or other adapter checks.",
               "baseline_jobs": jobs,
               "baseline": [], "paired_jobs": [], "paired": []}
    _write_json(run_dir / "summary.json", summary)
    baseline_config = GenerationConfig.for_profile("geographic_v3")
    baseline_backend = TerrainDiffusionBackend(baseline_config)
    try:
        for seed, x, z in jobs:
            summary["baseline"].append(_sample(run_dir, baseline_backend, seed, x, z, 0.1,
                                               "baseline"))
            _write_json(run_dir / "summary.json", summary)
    finally:
        baseline_backend.close()
    ranked = sorted((sample for sample in summary["baseline"] if sample["status"] == "complete"),
                    key=lambda sample: (-sample["raw_full_peak_y"], sample["seed"],
                                       sample["native_origin"]))[:3]
    summary["paired_jobs"] = [[sample["seed"], *sample["native_origin"]] for sample in ranked]
    _write_json(run_dir / "summary.json", summary)
    for snr in (0.05, 0.2):
        config = GenerationConfig.for_profile("geographic_v3",
                                              cond_snr=(snr, 0.1, 1.0, 0.1, 1.0))
        backend = TerrainDiffusionBackend(config)
        try:
            for sample in ranked:
                seed, (x, z) = sample["seed"], sample["native_origin"]
                summary["paired"].append(_sample(run_dir, backend, seed, x, z, snr, "paired"))
                _write_json(run_dir / "summary.json", summary)
        finally:
            backend.close()
    (run_dir / "brief-zh.md").write_text(_brief(summary), encoding="utf-8")
    print(run_dir, flush=True)


if __name__ == "__main__":
    main()
