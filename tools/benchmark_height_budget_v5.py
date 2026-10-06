"""Fixed v5 input-compression screen and one held-out seed, without publication."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from diffusion.backend import TerrainDiffusionBackend
from diffusion.config import GenerationConfig
from diffusion.geography_v5 import make_geographic_map_factory
from diffusion.paths import configure
from tools.prepare_height_budget_v4 import ORIGINS, SIZE, SPACING_M, HALO_X, HALO_Z
from tools.prepare_height_budget_v4 import height_result, sha256, write_json
from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, process_region


OUTPUT_ROOT = ROOT / "verification/height-budget-v5"
HEADROOMS = (40.0, 80.0, 120.0)
KNEE_M = 120.0
SCREEN = ((20260931, 0, 0), (20260931, 11520, 15360), (20260930, 0, 0))
HOLDOUT_SEED = 20261004
PRIOR_V3 = ROOT / "verification/height-budget-benchmark/run-20260929T093611798760Z/summary.json"


def _range(values):
    return {"min_m": float(np.min(values)), "max_m": float(np.max(values))}


def _condition_probe(seed, x, z, headroom, compression):
    # Upstream maps native pixels to coarse cells by 32 * latent_compression.
    scale = 32 * compression
    cx0, cz0 = x // scale, z // scale
    cx1 = -(-(x + SIZE) // scale)
    cz1 = -(-(z + SIZE) // scale)
    factory = make_geographic_map_factory(seed=seed, base_knee_m=KNEE_M,
                                          base_headroom_m=headroom)
    fields = factory.sample_components(cx0, cz0, cx1, cz1)
    return {"kind": "covering coarse-coordinate condition probe; model may use additional tile halo",
            "coarse_bounds_xz": [cx0, cz0, cx1, cz1], "coarse_scale_native_samples": scale,
            "base": _range(fields["base_m"]),
            "compressed_base": _range(fields["compressed_base_m"]),
            "relief": _range(fields["relief_m"]),
            "ocean": _range(fields["ocean_m"]),
            "final_elevation": _range(fields["condition_elevation_m"])}


def evaluate(directory, headroom, jobs, label):
    config = GenerationConfig.for_profile("geographic_v5", v5_base_knee_m=KNEE_M,
                                          v5_base_headroom_m=headroom)
    backend = TerrainDiffusionBackend(config)
    directory.mkdir()
    report = {"label": label, "profile": "geographic_v5", "base_knee_m": KNEE_M,
              "base_headroom_m": headroom, "generation_identity": backend.identity,
              "generation_config": config.record(), "jobs": [list(job) for job in jobs],
              "samples": [], "status": "running"}
    write_json(directory / "report.json", report)
    try:
        for seed, x, z in jobs:
            stem = f"seed{seed}-x{x}-z{z}"
            elevation, climate, metadata = backend.generate(seed, x, z, SIZE)
            if elevation.shape != (SIZE, SIZE) or metadata["native_resolution_m"] != SPACING_M:
                raise ValueError("unexpected model grid or spacing")
            raw_path = directory / f"{stem}.npz"
            np.savez_compressed(raw_path, elevation=elevation, climate=climate,
                                metadata=json.dumps(metadata),
                                generation_config=json.dumps(config.record()))
            sample = {"seed": seed, "native_origin": [x, z],
                      "raw_npz": raw_path.name, "raw_sha256": sha256(raw_path),
                      "generation_seconds": metadata["seconds"],
                      "raw_full": height_result(elevation)}
            report["samples"].append(sample)
            write_json(directory / "report.json", report)
            processed = process_region(elevation.astype(np.float64) + 126, 126,
                                       SPACING_M, SPACING_M,
                                       recipe=METRIC_30M_RECIPE_V1).elevation_m
            interior = np.s_[HALO_Z:SIZE-HALO_Z, HALO_X:SIZE-HALO_X]
            sample["raw_interior"] = height_result(elevation[interior])
            sample["processed_interior"] = height_result(processed[interior] - 126)
            sample["height_pass"] = (sample["raw_full"]["height_pass"] and
                                     sample["processed_interior"]["height_pass"])
            sample["condition_probe"] = _condition_probe(
                seed, x, z, headroom, backend.pipeline.latent_compression)
            write_json(directory / "report.json", report)
            print(f"{label} {stem}: raw Y {sample['raw_full']['min_y']:.1f}.."
                  f"{sample['raw_full']['max_y']:.1f}, processed peak Y "
                  f"{sample['processed_interior']['max_y']:.1f}, pass={sample['height_pass']}",
                  flush=True)
        report["status"] = "height_pass" if all(s["height_pass"] for s in report["samples"]) else "height_fail"
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        write_json(directory / "report.json", report)
        raise
    finally:
        backend.close()
        write_json(directory / "report.json", report)
    return report


def _get(samples, seed, x, z):
    return next(s for s in samples if s["seed"] == seed and s["native_origin"] == [x, z])


def _score(report, prior_v3):
    def hard_pass(sample):
        return all(sample[field]["min_y"] >= -64 and sample[field]["max_y"] <= 1022
                   for field in ("raw_full", "processed_interior"))
    failures = sum(not hard_pass(s) for s in report["samples"])
    exceedance = sum(max(0, s[field]["max_y"] - 1022) +
                     max(0, -64 - s[field]["min_y"])
                     for s in report["samples"] for field in ("raw_full", "processed_interior"))
    mountain = _get(report["samples"], 20260931, 11520, 15360)
    reference = _get(prior_v3["baseline"], 20260931, 11520, 15360)
    relief_gap = abs(mountain["processed_interior"]["relief_p95_minus_p5_m"] -
                     reference["processed_interior"]["relief_p95_minus_p5_m"])
    return failures, relief_gap, exceedance


def main():
    configure()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    directory = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    directory.mkdir()
    prior_v3 = json.loads(PRIOR_V3.read_text(encoding="utf-8"))
    summary = {"purpose": "fixed v5 soft-knee input screen and held-out seed under current height policy; no publication",
               "run_dir": str(directory.relative_to(ROOT)), "base_knee_m": KNEE_M,
               "headrooms_m": list(HEADROOMS), "sea_y": 62,
               "hard_height_bounds_y": [-64, 1022], "soft_target_y": 800,
               "screen_jobs": [list(job) for job in SCREEN],
               "holdout_jobs": [[HOLDOUT_SEED, x, z] for x, z in ORIGINS],
               "raw_grid_shape": [SIZE, SIZE], "halo_samples": [HALO_X, HALO_Z],
               "screen": [], "holdout": None, "publication": "none"}
    write_json(directory / "summary.json", summary)
    reports = []
    for index, headroom in enumerate(HEADROOMS, 1):
        name = f"screen-{index}"
        report = evaluate(directory / name, headroom, SCREEN, name)
        score = _score(report, prior_v3)
        reports.append(report)
        summary["screen"].append({"headroom_m": headroom, "report": f"{name}/report.json",
                                  "status": report["status"], "score": list(score)})
        write_json(directory / "summary.json", summary)
    selected = min(range(3), key=lambda i: (*_score(reports[i], prior_v3), i))
    summary["selected_headroom_m"] = HEADROOMS[selected]
    summary["screen_all_height_pass"] = _score(reports[selected], prior_v3)[0] == 0
    summary["selection_note"] = ("Rank by failed-window count, then processed-interior normal-mountain "
                                 "relief distance to v3, then total exceedance. Relief ranking is not naturalness acceptance. "
                                 "If every candidate fails height, holdout is research only.")
    write_json(directory / "summary.json", summary)
    jobs = tuple((HOLDOUT_SEED, x, z) for x, z in ORIGINS)
    holdout = evaluate(directory / "holdout", HEADROOMS[selected], jobs, "holdout")
    summary["holdout"] = {"report": "holdout/report.json", "status": holdout["status"]}
    summary["height_gate"] = (summary["screen_all_height_pass"] and
                              _score(holdout, prior_v3)[0] == 0)
    summary["rivers_ready"] = False
    summary["rivers_ready_note"] = "Height screening and morphology review are separate; no river work in this task."
    write_json(directory / "summary.json", summary)
    lines = ["# v5 软膝输入条件实验", "",
             "三个候选只改变高正基底的饱和余量 40/80/120 米；膝点 120 米、起伏系数 0.18、"
             "平滑有界海深 40 米与 SNR 0.1 固定。模型输出未缩放或裁切。"
             "当前硬边界 Y-64..1022；Y800 仅作软目标诊断。", "",
             "| 阶段 | 余量 m | 种子 | 原点 | 原始全幅最高 Y | 加工同域起伏 m | 高度合格 |",
             "| --- | ---: | --- | --- | ---: | ---: | --- |"]
    for headroom, report in zip(HEADROOMS, reports):
        for sample in report["samples"]:
            x, z = sample["native_origin"]
            lines.append(f"| 筛选 | {headroom:.0f} | {sample['seed']} | ({x},{z}) | "
                         f"{sample['raw_full']['max_y']:.2f} | "
                         f"{sample['processed_interior']['relief_p95_minus_p5_m']:.2f} | "
                         f"{sample['height_pass']} |")
    for sample in holdout["samples"]:
        x, z = sample["native_origin"]
        lines.append(f"| 留出 | {HEADROOMS[selected]:.0f} | {sample['seed']} | ({x},{z}) | "
                     f"{sample['raw_full']['max_y']:.2f} | "
                     f"{sample['processed_interior']['relief_p95_minus_p5_m']:.2f} | "
                     f"{sample['height_pass']} |")
    lines += ["", f"高度门槛：{'通过' if summary['height_gate'] else '未通过'}；河网准备：未通过（形态仍需审查）。",
              "输入条件范围只是模型 coarse 坐标覆盖窗的诊断，模型可能额外读取 tile halo。",
              "本轮仅固定窗口抽样，不保证任意种子或全球区域合格。", ""]
    (directory / "brief-zh.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{directory} height_gate={summary['height_gate']}", flush=True)


if __name__ == "__main__":
    main()
