"""Render hash-pinned native delta form comparisons without generated paths."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
from matplotlib.collections import LineCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.environment_delta_fv import load

STAGES = ("initial", "growth_6h", "growth_12h", "growth_24h")
CASES_ZH = {"flat": "90 米口门 · 平床", "slope": "向海坡降 1 米", "wide_mouth": "150 米宽河口",
            "tide": "0.3 米潮汐", "wave": "0.3 米入射波"}
WATER = colors.LinearSegmentedColormap.from_list(
    "forms_water", ["#edf8f8", "#77c8cb", "#248ba8", "#164360"])
BED = colors.LinearSegmentedColormap.from_list(
    "forms_bed", ["#253e61", "#73a8b1", "#e7e3cd", "#9cab77", "#455b40"])
NOTE = "理想化工程试验，非现实地点复现；波浪仅参与泥沙动员。"
GRID_NOTE = "原生 30 米网格；黑线为实际干湿边界；灰色为干格。供沙时长不计 5 分钟预热。"


def configure_font():
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font_manager.fontManager.addfont(str(font_path))
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=str(font_path)).get_name(),
                         "axes.unicode_minus": False, "font.size": 10,
                         "axes.titlesize": 12, "savefig.facecolor": "white"})


def pinned_path(directory, entry):
    path = Path(entry["path"])
    if not path.is_absolute():
        path = directory / path
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != entry["sha256"]:
        raise ValueError(f"SHA256 mismatch: {path}")
    return path


def read_products(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    products = {}
    for case, item in manifest["cases"].items():
        products[case] = {}
        for stage in STAGES:
            entry = item["stages"][stage]
            products[case][stage] = load(pinned_path(directory, entry), expected_sha256=entry["sha256"])
    return manifest, products


def geometry(product):
    rows, cols = product["arrays"]["bed_m"].shape
    spacing = product["metadata"]["spacing_m"]
    return rows, cols, spacing, [-spacing / 2, (cols - .5) * spacing,
                                -spacing / 2, (rows - .5) * spacing]


def wet_mask(product):
    threshold = product["metadata"]["config"]["bedload"]["dry_depth_m"]
    return product["arrays"]["depth_m"] > threshold


def wet_boundary(ax, product):
    wet = wet_mask(product)
    _, _, spacing, _ = geometry(product)
    segments = []
    for row, col in zip(*np.nonzero(wet[:, 1:] != wet[:, :-1])):
        x, z = (col + .5) * spacing, row * spacing
        segments.append([(x, z - spacing / 2), (x, z + spacing / 2)])
    for row, col in zip(*np.nonzero(wet[1:] != wet[:-1])):
        x, z = col * spacing, (row + .5) * spacing
        segments.append([(x - spacing / 2, z), (x + spacing / 2, z)])
    ax.add_collection(LineCollection(segments, colors="#283e3d", linewidths=.45))


def draw_field(ax, product, field, norm, cmap, *, depth=False, xlabel=False, ylabel=False):
    _, _, _, extent = geometry(product)
    if depth:
        field = np.ma.masked_where(~wet_mask(product), field)
    ax.set_facecolor("#dedfdb")
    ax.imshow(field, origin="lower", extent=extent, interpolation="nearest", norm=norm, cmap=cmap)
    wet_boundary(ax, product)
    ax.set(xlim=extent[:2], ylim=extent[2:], aspect="equal")
    ax.set_xticks([0, 600, 1200])
    ax.set_yticks([0, 450, 900])
    ax.tick_params(labelsize=8, labelbottom=xlabel, labelleft=ylabel, length=2)
    if xlabel:
        ax.set_xlabel("局部 x（米）", fontsize=9)
    if ylabel:
        ax.set_ylabel("局部 z（米）", fontsize=9)


def finish(fig, output, title, note=GRID_NOTE):
    fig.suptitle(title, fontsize=17)
    fig.supxlabel(note + "\n" + NOTE, fontsize=10)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def add_colorbar(fig, axes, norm, cmap, label):
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes,
                 fraction=.022, pad=.012, shrink=.88, label=label)


def labels(manifest):
    return {case: CASES_ZH.get(case, item["label_zh"]) for case, item in manifest["cases"].items()}


def overview(manifest, products, output, bed_norm, depth_norm):
    fig, axes = plt.subplots(2, len(products), figsize=(22, 8), layout="constrained", squeeze=False)
    for col, (case, stages) in enumerate(products.items()):
        product = stages["growth_24h"]
        for row, (field, norm, cmap) in enumerate((("bed_m", bed_norm, BED), ("depth_m", depth_norm, WATER))):
            draw_field(axes[row, col], product, product["arrays"][field], norm, cmap,
                       depth=row == 1, xlabel=row == 1, ylabel=col == 0)
        axes[0, col].set_title(labels(manifest)[case])
    add_colorbar(fig, axes[0], bed_norm, BED, "床面高程（米）")
    add_colorbar(fig, axes[1], depth_norm, WATER, "实际水深（米）")
    finish(fig, output / "delta-forms-final.png", "不同河口条件 · 供沙 24 小时实测")


def initial(manifest, products, output, bed_norm):
    fig, axes = plt.subplots(1, len(products), figsize=(22, 4.4), layout="constrained", squeeze=False)
    for col, (case, stages) in enumerate(products.items()):
        product = stages["initial"]
        draw_field(axes[0, col], product, product["arrays"]["bed_m"], bed_norm, BED,
                   xlabel=True, ylabel=col == 0)
        axes[0, col].set_title(labels(manifest)[case])
    add_colorbar(fig, axes, bed_norm, BED, "床面高程（米）")
    finish(fig, output / "delta-forms-initial.png", "初始床面")


def changes(manifest, products, output, change_norm, evolution):
    stages_to_plot = STAGES[1:] if evolution else STAGES[-1:]
    fig, axes = plt.subplots(len(stages_to_plot), len(products),
                             figsize=(22, 3.1 * len(stages_to_plot) + 1.3),
                             layout="constrained", squeeze=False)
    for col, (case, stages) in enumerate(products.items()):
        base = stages["initial"]["arrays"]["bed_m"]
        for row, stage in enumerate(stages_to_plot):
            product = stages[stage]
            difference = product["arrays"]["bed_m"] - base
            draw_field(axes[row, col], product, difference, change_norm, "RdBu_r",
                       xlabel=row == len(stages_to_plot) - 1, ylabel=col == 0)
            hour = stage.split("_")[1][:-1]
            axes[row, col].set_title(labels(manifest)[case] + (f" · {hour} 小时" if evolution else ""))
    add_colorbar(fig, axes, change_norm, "RdBu_r", "床面变化（米）；正值沉积，负值侵蚀")
    filename = "delta-forms-evolution.png" if evolution else "delta-forms-change-annotated.png"
    title = "供沙 6 / 12 / 24 小时 · 床面变化" if evolution else "供沙 24 小时 · 床面变化"
    note = "相对各自初始床面；原生 30 米网格；黑线为实际干湿边界。"
    if not evolution:
        note += "右端为输入馈槽，形态比较看左侧海域。"
    finish(fig, output / filename, title, note)


def tide_timeseries(directory, manifest, output):
    for case, item in manifest["cases"].items():
        if case != "tide" or "boundary_timeseries" not in item:
            continue
        records = json.loads(pinned_path(directory, item["boundary_timeseries"]).read_text(encoding="utf-8"))
        records = [record for record in records if record["time_s"] >= 300]
        time = np.array([record["growth_time_s"] for record in records])
        stage = np.array([record["sea_stage_m"] for record in records])
        imported = np.array([record["sea_import_m3"] for record in records])
        exported = np.array([record["water_export_m3"] for record in records])
        intervals = np.diff(time)
        midpoint = (time[1:] + time[:-1]) / 7200
        fig, axes = plt.subplots(2, 1, figsize=(13, 6.5), sharex=True, layout="constrained")
        axes[0].plot(time / 3600, stage, color="#236888", lw=1.5)
        axes[0].axhline(0, color="#9a9a9a", lw=.7)
        axes[0].set_ylabel("海位（米）")
        axes[1].plot(midpoint, np.diff(imported) / intervals, color="#8c3975",
                     label=f"海水入域（累计 {imported[-1] - imported[0]:,.0f} 立方米）", lw=1.3)
        axes[1].plot(midpoint, np.diff(exported) / intervals, color="#277c61",
                     label=f"向海出域（累计 {exported[-1] - exported[0]:,.0f} 立方米）", lw=1.3)
        axes[1].set(xlabel="供沙时间（小时）", ylabel="边界流量（立方米／秒）", xlim=(0, 24))
        axes[1].legend(loc="lower right", frameon=False)
        for ax in axes:
            ax.grid(alpha=.18)
        finish(fig, output / f"delta-forms-{case}-tide.png", labels(manifest)[case] + " · 潮汐与海边界交换",
               "仅统计供沙期，已扣预热；净向海输出占主导。流量为保存区间水量增量／物理时长。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    configure_font()
    manifest, products = read_products(args.trial)
    all_products = [product for stages in products.values() for product in stages.values()]
    bed_norm = colors.Normalize(min(float(p["arrays"]["bed_m"].min()) for p in all_products),
                                max(float(p["arrays"]["bed_m"].max()) for p in all_products))
    depth_norm = colors.Normalize(0, max(float(p["arrays"]["depth_m"].max()) for p in all_products))
    change_max = max(float(np.abs(product["arrays"]["bed_m"] - stages["initial"]["arrays"]["bed_m"]).max())
                     for stages in products.values() for product in stages.values())
    change_norm = colors.Normalize(-max(change_max, .01), max(change_max, .01))
    output = args.output or args.trial / "images"
    output.mkdir(parents=True, exist_ok=False)
    overview(manifest, products, output, bed_norm, depth_norm)
    initial(manifest, products, output, bed_norm)
    changes(manifest, products, output, change_norm, False)
    changes(manifest, products, output, change_norm, True)
    tide_timeseries(args.trial, manifest, output)
    print(str(output.resolve()))


if __name__ == "__main__":
    main()
