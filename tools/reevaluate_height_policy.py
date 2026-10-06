"""Read existing v5 raw results under the current Minecraft build-height policy."""

import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.minecraft_export import (MIN_BUILD_SURFACE_Y,
                                                MAX_BUILD_SURFACE_Y,
                                                SOFT_TARGET_SURFACE_Y)
from tools.prepare_height_budget_v4 import sha256, write_json


SOURCE = ROOT / "verification/height-budget-v5/run-20260929T103819083596Z"
OUTPUT_ROOT = ROOT / "verification/height-policy-review"


def _metric(values):
    minimum, maximum = values["min_y"], values["max_y"]
    return {"min_y": minimum, "max_y": maximum,
            "hard_pass": minimum >= MIN_BUILD_SURFACE_Y and maximum <= MAX_BUILD_SURFACE_Y,
            "above_y800_percent": values["above_y800_percent"],
            "below_y_minus64_percent": values["below_y_minus64_percent"]}


def reevaluate():
    source_summary = json.loads((SOURCE / "summary.json").read_text(encoding="utf-8"))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir()
    result = {"policy": "Minecraft build-safe surface Y=-64..1022; Y800 soft diagnostic target",
              "source_run": str(SOURCE.relative_to(ROOT)), "output_is_reassessment_only": True,
              "hard_bounds_y": [MIN_BUILD_SURFACE_Y, MAX_BUILD_SURFACE_Y],
              "soft_target_y": SOFT_TARGET_SURFACE_Y,
              "screen": [], "holdout": [], "selected_headroom_m": source_summary["selected_headroom_m"]}
    for phase, entries in (("screen", source_summary["screen"]),
                           ("holdout", [source_summary["holdout"]])):
        for entry in entries:
            report_path = SOURCE / entry["report"]
            old = json.loads(report_path.read_text(encoding="utf-8"))
            evaluated = {"headroom_m": old["base_headroom_m"],
                         "source_report": str(report_path.relative_to(ROOT)),
                         "generation_identity": old["generation_identity"],
                         "samples": []}
            for sample in old["samples"]:
                raw_path = report_path.parent / sample["raw_npz"]
                if sha256(raw_path) != sample["raw_sha256"]:
                    raise ValueError(f"source hash changed: {raw_path}")
                with np.load(raw_path, allow_pickle=False) as archive:
                    elevation = archive["elevation"]
                if elevation.shape != (513, 513) or not np.isfinite(elevation).all():
                    raise ValueError(f"invalid source grid: {raw_path}")
                raw_y = elevation.astype(np.float64) + 62
                raw = _metric(sample["raw_full"])
                if (not np.isclose(raw["min_y"], raw_y.min(), atol=0, rtol=0) or
                        not np.isclose(raw["max_y"], raw_y.max(), atol=0, rtol=0) or
                        not np.isclose(raw["above_y800_percent"],
                                       float(np.mean(raw_y > SOFT_TARGET_SURFACE_Y) * 100),
                                       atol=1e-12, rtol=0)):
                    raise ValueError("source statistics differ from saved raw elevation")
                processed = _metric(sample["processed_interior"])
                evaluated["samples"].append({
                    "seed": sample["seed"], "native_origin": sample["native_origin"],
                    "raw_npz": str(raw_path.relative_to(ROOT)),
                    "raw_sha256": sample["raw_sha256"],
                    "raw_full": raw, "processed_interior": processed,
                    "hard_pass": raw["hard_pass"] and processed["hard_pass"]})
            evaluated["all_hard_pass"] = all(s["hard_pass"] for s in evaluated["samples"])
            result[phase].append(evaluated)
    selected = next(e for e in result["screen"] if e["headroom_m"] == result["selected_headroom_m"])
    result["selected_screen_hard_pass"] = selected["all_hard_pass"]
    result["selected_holdout_hard_pass"] = result["holdout"][0]["all_hard_pass"]
    result["selected_seven_window_height_pass"] = (result["selected_screen_hard_pass"] and
                                                    result["selected_holdout_hard_pass"])
    result["rivers_ready"] = False
    result["rivers_ready_note"] = "Height safety alone does not establish terrain morphology or river acceptance."
    write_json(destination / "summary.json", result)
    lines = ["# Minecraft 高度政策重评", "",
             "本报告只读复评旧 v5 原始数据；算法、参数和原始文件未改变。硬边界为 Y-64..1022，",
             "Y800 是软目标。高于 Y800 的百分比表示网格像素面积占比，不是高峰数量。", "",
             "| 阶段 | h (m) | 种子 | 原点 | 原始峰 Y | 原始 >800 面积 % | 加工内域峰 Y | 高度安全 |",
             "| --- | ---: | --- | --- | ---: | ---: | ---: | --- |"]
    for phase in ("screen", "holdout"):
        for group in result[phase]:
            for sample in group["samples"]:
                x, z = sample["native_origin"]
                lines.append(f"| {phase} | {group['headroom_m']:.0f} | {sample['seed']} | ({x},{z}) | "
                             f"{sample['raw_full']['max_y']:.2f} | "
                             f"{sample['raw_full']['above_y800_percent']:.4f} | "
                             f"{sample['processed_interior']['max_y']:.2f} | {sample['hard_pass']} |")
    selected_peaks = [s["raw_full"]["max_y"] for s in selected["samples"]]
    selected_peaks += [s["raw_full"]["max_y"] for s in result["holdout"][0]["samples"]]
    lines += ["", "选定 h=120 的七个窗口逐窗原始峰 Y：" + ", ".join(f"{v:.2f}" for v in selected_peaks) + "。",
              "这些窗口包括海洋、普通山地和高山，不能把七窗峰值均值当作山峰分布。",
              f"选定候选七窗高度安全：{result['selected_seven_window_height_pass']}；河网准备：False。",
              "旧报告中的 Y800 失败仍表示旧政策判断；本重评通过来自政策放宽，不是算法改善。", ""]
    (destination / "brief-zh.md").write_text("\n".join(lines), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    reevaluate()
