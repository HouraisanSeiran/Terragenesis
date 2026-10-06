"""Summarize saved height-budget results without loading the model."""

import json
from pathlib import Path
import sys


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def _normalize(sample):
    for suffix in ("raw_full", "processed_interior"):
        old = f"exportable_{suffix}"
        new = f"height_eligible_{suffix}"
        if old in sample:
            sample[new] = sample.pop(old)


def main(run_dir: Path):
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["eligibility_note"] = ("Height bounds only; no Minecraft snapshot export or "
                                   "other adapter checks.")
    for sample in summary["baseline"] + summary["paired"]:
        _normalize(sample)
        stem = sample["archive"].removesuffix(".npz")
        sample_path = run_dir / f"{stem}.json"
        stored = json.loads(sample_path.read_text(encoding="utf-8"))
        _normalize(stored)
        stored["eligibility_note"] = summary["eligibility_note"]
        _write_json(sample_path, stored)
    baseline = summary["baseline"]
    paired = summary["paired"]
    complete = [sample for sample in baseline if sample["status"] == "complete"]
    upper = [sample for sample in complete if sample["raw_full"]["above_y800_percent"] > 0 or
             sample["processed_interior"]["above_y800_percent"] > 0]
    lower = [sample for sample in complete if sample["raw_full"]["below_y_minus64_percent"] > 0 or
             sample["processed_interior"]["below_y_minus64_percent"] > 0]
    summary["counts"] = {
        "baseline_total": len(baseline), "baseline_complete": len(complete),
        "baseline_failed": len(baseline) - len(complete),
        "baseline_upper_rejected": len(upper), "baseline_bottom_rejected": len(lower),
        "paired_total": len(paired),
        "paired_failed": sum(sample["status"] != "complete" for sample in paired),
    }
    _write_json(summary_path, summary)

    lines = ["# 高度预算真实模型抽样简报", "",
             "这是预先固定的 3 个种子、4 个目的性窗口，并非全球随机抽样；不能据此估计全球通过率。",
             "原始模型输出以海面为零米；加工时转换到核心海面 126 米，Minecraft 海面保持 Y62。",
             "统计坡度使用真实 30 米水平间距。加工前后只比较去掉每侧 13 个样本 halo 的同一内域；",
             "原始全幅峰值另列。这里只检查高度，不代表实际完成 Minecraft 导出。", "",
             f"基线完成 {len(complete)}/{len(baseline)}，失败 {len(baseline)-len(complete)}；"
             f"上限拒绝 {len(upper)}，底部拒绝 {len(lower)}。两种拒绝可重叠，失败样本不剔除。",
             "超出 Y800 或低于 Y-64 均不可发布。", "",
             "| 种子 | 原点 | 原始全幅最高Y | 原始同域最高Y | 加工同域最高Y | 原始全幅高度合格 | 加工同域高度合格 |",
             "| --- | --- | ---: | ---: | ---: | --- | --- |"]
    for sample in baseline:
        x, z = sample["native_origin"]
        if sample["status"] == "complete":
            lines.append(f"| {sample['seed']} | ({x},{z}) | {sample['raw_full_peak_y']:.2f} | "
                         f"{sample['raw_interior']['game_y_max']:.2f} | "
                         f"{sample['processed_interior']['game_y_max']:.2f} | "
                         f"{sample['height_eligible_raw_full']} | "
                         f"{sample['height_eligible_processed_interior']} |")
        else:
            lines.append(f"| {sample['seed']} | ({x},{z}) | 失败 | 失败 | 失败 | 失败 | 失败 |")
    lines += ["", "按基线原始全幅最高 Y 预先选出前三个已完成窗口，再分别运行 SNR 0.05 和 0.2。",
              "配对值按实测列示，不能假设较低 SNR 一定降低峰值。", "",
              "| 种子 | 原点 | SNR | 原始全幅最高Y | 原始同域起伏 p95-p5 (m) | 原始同域坡度 p95 (m/m) | 状态 |",
              "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for seed, x, z in summary["paired_jobs"]:
        for snr in (0.05, 0.1, 0.2):
            group = baseline if snr == 0.1 else paired
            sample = next((item for item in group if item["seed"] == seed and
                           item["native_origin"] == [x, z] and item["elevation_snr"] == snr), None)
            if sample and sample["status"] == "complete":
                lines.append(f"| {seed} | ({x},{z}) | {snr:g} | "
                             f"{sample['raw_full_peak_y']:.2f} | "
                             f"{sample['raw_interior']['relief_p95_minus_p5_m']:.2f} | "
                             f"{sample['raw_interior']['slope_m_per_m_p95']:.3f} | 完成 |")
            else:
                lines.append(f"| {seed} | ({x},{z}) | {snr:g} | 失败 | 失败 | 失败 | 失败 |")
    lines += ["", "完整分布、坡度、耗时、身份、源文件 SHA256 与失败信息见各样本 JSON 及 summary.json。", ""]
    (run_dir / "brief-zh.md").write_text("\n".join(lines), encoding="utf-8")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = [f"{seed}\n{x},{z}" for seed, x, z in summary["paired_jobs"]]
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
        for snr, color in ((0.05, "#3075a3"), (0.1, "#529d62"), (0.2, "#ce8150")):
            group = baseline if snr == 0.1 else paired
            values = [next((sample for sample in group if sample["seed"] == seed and
                            sample["native_origin"] == [x, z] and sample["elevation_snr"] == snr), None)
                      for seed, x, z in summary["paired_jobs"]]
            axes[0].plot(labels, [sample["raw_full_peak_y"] if sample and sample["status"] == "complete"
                                  else float("nan") for sample in values], "o-", color=color, label=f"SNR {snr:g}")
            axes[1].plot(labels, [sample["raw_interior"]["relief_p95_minus_p5_m"]
                                  if sample and sample["status"] == "complete" else float("nan")
                                  for sample in values], "o-", color=color, label=f"SNR {snr:g}")
        axes[0].axhline(800, color="black", linestyle="--", linewidth=1)
        axes[0].set_title("Raw full-grid peak (Minecraft Y)")
        axes[1].set_title("Raw interior relief p95-p5 (m)")
        for axis in axes:
            axis.grid(alpha=.25)
            axis.legend()
        fig.savefig(run_dir / "paired-peaks-relief.png", dpi=150)
        plt.close(fig)
    except ImportError:
        pass


if __name__ == "__main__":
    main(Path(sys.argv[1]))
