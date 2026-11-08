"""Run six fixed v4 confirmation windows without publication or retuning."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from diffusion.paths import configure
from tools.prepare_height_budget_v4 import CANDIDATES, ORIGINS, evaluate_candidate, sha256, write_json


OUTPUT_ROOT = ROOT / "verification/height-budget-confirmation"
PRIOR_V4 = ROOT / "verification/height-budget-v4/run-20260929T095325080740Z/screen-candidate-3/report.json"
PRIOR_V3 = ROOT / "verification/height-budget-benchmark/run-20260929T093611798760Z/summary.json"
PRESSURE = ((20260931, 0, 0), (20260931, 11520, 15360))
NEW_SEED = 20261003
JOBS = PRESSURE + tuple((NEW_SEED, x, z) for x, z in ORIGINS)


def _find(samples, seed, origin):
    return next(sample for sample in samples if sample["seed"] == seed and
                sample["native_origin"] == list(origin))


def summarize(record, directory):
    prior_v4 = json.loads(PRIOR_V4.read_text(encoding="utf-8"))
    prior_v3 = json.loads(PRIOR_V3.read_text(encoding="utf-8"))
    previous_identity = prior_v4["generation_identity"]
    if record["generation_identity"] != previous_identity:
        raise ValueError("confirmation generation identity differs from prior v4")
    if record["jobs"] != [list(job) for job in JOBS] or len(record["samples"]) != len(JOBS):
        raise ValueError("confirmation did not complete all fixed windows")
    if any(sample["raw_sha256"] != sha256(directory / "samples" / sample["raw_npz"])
           for sample in record["samples"]):
        raise ValueError("confirmation source hash mismatch")
    for sample in record["samples"]:
        with np.load(directory / "samples" / sample["raw_npz"], allow_pickle=False) as archive:
            elevation = archive["elevation"]
            metadata = json.loads(str(archive["metadata"].item()))
            saved_config = json.loads(str(archive["generation_config"].item()))
        if (elevation.shape != (513, 513) or not np.isfinite(elevation).all() or
                metadata["identity"] != previous_identity or
                metadata["native_resolution_m"] != 30 or
                saved_config != json.loads(json.dumps(record["generation_config"]))):
            raise ValueError("confirmation source grid or identity mismatch")

    comparisons = []
    for seed, x, z in PRESSURE:
        current = _find(record["samples"], seed, (x, z))
        old_v4 = _find(prior_v4["samples"], seed, (x, z))
        old_v3 = _find(prior_v3["baseline"], seed, (x, z))
        prior_raw = PRIOR_V4.parent / old_v4["raw_npz"]
        current_raw = directory / "samples" / current["raw_npz"]
        with np.load(prior_raw, allow_pickle=False) as prior_archive, \
             np.load(current_raw, allow_pickle=False) as current_archive:
            max_abs_elevation_difference_m = float(np.max(np.abs(
                prior_archive["elevation"].astype(np.float64) -
                current_archive["elevation"].astype(np.float64))))
        current_processed = current["processed_interior"]
        old_v4_processed = old_v4["processed_interior"]
        old_v3_processed = old_v3["processed_interior"]
        comparisons.append({
            "seed": seed, "native_origin": [x, z],
            "v4_previous_raw_peak_y": old_v4["raw_full"]["max_y"],
            "v4_confirmed_raw_peak_y": current["raw_full"]["max_y"],
            "v4_raw_peak_delta_y": current["raw_full"]["max_y"] - old_v4["raw_full"]["max_y"],
            "v4_raw_max_abs_elevation_difference_m": max_abs_elevation_difference_m,
            "v4_previous_processed_interior": old_v4_processed,
            "v4_confirmed_processed_interior": current_processed,
            "v3_baseline_processed_interior_relief_p95_minus_p5_m":
                old_v3_processed["relief_p95_minus_p5_m"],
            "v3_baseline_processed_interior_slope_m_per_m_p95":
                old_v3_processed["slope_m_per_m_p95"],
        })
    new_samples = [_find(record["samples"], NEW_SEED, origin) for origin in ORIGINS]
    def hard_pass(sample):
        return all(sample[field]["min_y"] >= -64 and sample[field]["max_y"] <= 1022
                   for field in ("raw_full", "processed_interior"))
    pressure_pass = all(hard_pass(_find(record["samples"], seed, (x, z)))
                        for seed, x, z in PRESSURE)
    height_gate = pressure_pass and all(hard_pass(sample) for sample in new_samples)
    summary = {"purpose": "fixed v4 confirmation under current height policy, no retuning or publication",
               "profile": "geographic_v4", "candidate": list(CANDIDATES[2]),
               "elevation_snr": 0.1, "jobs": [list(job) for job in JOBS],
               "generation_identity": previous_identity,
               "report": "samples/report.json", "pressure_comparisons": comparisons,
               "new_seed_samples": [{"native_origin": sample["native_origin"],
                                     "raw_full": sample["raw_full"],
                                     "processed_interior": sample["processed_interior"],
                                     "height_pass": sample["height_pass"]}
                                    for sample in new_samples],
               "all_raw_finite": True, "raw_hashes_verified": True,
               "pressure_pass": pressure_pass, "height_gate": height_gate,
               "rivers_ready": False,
               "rivers_ready_note": "Morphology requires review; height alone does not authorize river work.",
               "gate_rule": "All fixed windows must fit raw-full and processed-interior Y=-64..1022; Y800 is a soft diagnostic target.",
               "publication": "none"}
    write_json(directory / "summary.json", summary)
    lines = ["# v4 高度复验", "",
             "当前硬边界 Y-64..1022；Y800 仅作软目标诊断。旧归档保留当时的 Y800 判定。", "",
             "固定 v4 参数 (.04, .18, 40 米) 与高程 SNR 0.1，复跑两处既有压力窗，",
             "并检查新种子 20261003 的四个固定窗口。每窗 513 x 513、30 米间距。",
             "仅保留原始模型样本与诊断；没有加工包或 Minecraft 快照发布。", "",
             "| 种子 | 原点 | 原始全幅最高 Y | 加工内域最高 Y | 高度合格 |",
             "| --- | --- | ---: | ---: | --- |"]
    for sample in record["samples"]:
        x, z = sample["native_origin"]
        lines.append(f"| {sample['seed']} | ({x},{z}) | {sample['raw_full']['max_y']:.2f} | "
                     f"{sample['processed_interior']['max_y']:.2f} | {sample['height_pass']} |")
    lines += ["", "压力窗同配置复现及与 v3 基线对照（起伏、坡度均为加工后同域）：", "",
              "| 原点 | 旧 v4 峰 Y | 本轮 v4 峰 Y | 本轮 v4 起伏 m | v3 起伏 m | 本轮 v4 坡度 p95 | v3 坡度 p95 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in comparisons:
        x, z = item["native_origin"]
        processed = item["v4_confirmed_processed_interior"]
        lines.append(f"| ({x},{z}) | {item['v4_previous_raw_peak_y']:.2f} | "
                     f"{item['v4_confirmed_raw_peak_y']:.2f} | "
                     f"{processed['relief_p95_minus_p5_m']:.2f} | "
                     f"{item['v3_baseline_processed_interior_relief_p95_minus_p5_m']:.2f} | "
                     f"{processed['slope_m_per_m_p95']:.3f} | "
                     f"{item['v3_baseline_processed_interior_slope_m_per_m_p95']:.3f} |")
    lines += ["", f"高度门槛：{'通过' if height_gate else '未通过'}；河网准备：未通过（形态仍需审查）。",
              "本次是固定地点验证，不能外推成任意种子的高度保证。", ""]
    (directory / "brief-zh.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    configure()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    directory = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    directory.mkdir()
    record = evaluate_candidate(directory / "samples", CANDIDATES[2], JOBS, "confirmation")
    summary = summarize(record, directory)
    print(f"{directory} height_gate={summary['height_gate']}", flush=True)


if __name__ == "__main__":
    main()
