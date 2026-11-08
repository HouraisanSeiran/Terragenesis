"""Render native saved distributary trials without inventing terrain or paths."""
import argparse
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.environment_delta_fv import load

STAGES = {
    "initial": "初态", "growth_6h": "生长 6 小时", "growth_12h": "生长 12 小时",
    "growth_24h": "生长 24 小时", "clearwater_36h": "清水维持 36 小时",
    "flood_39h": "高流量 39 小时", "recession_42h": "低流量 42 小时",
    "recovered_48h": "恢复 48 小时",
}
CASES = {"flat": "平床", "microrelief": "微扰床面"}
WATER = colors.LinearSegmentedColormap.from_list("trial_water", ["#d8f2ed", "#45a9bc", "#12617d", "#13394c"])
LAND = colors.LinearSegmentedColormap.from_list("trial_land", ["#eff2c3", "#8fba75", "#506847"])
THIN_WATER_NOTE = "恢复48小时岸上浅色为洪水后毫米级薄水，不表示海岸退缩"


def configure_font():
    for path in (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf")):
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(path)).get_name()
            break
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 10, "axes.titlesize": 12})


def read_trial(directory, diagnostics_directory=None):
    reports = diagnostics_directory or directory
    summary = json.loads((reports / "summary.json").read_text(encoding="utf-8"))
    products = {}
    for case, item in summary["cases"].items():
        products[case] = {}
        for stage, report in item["stages"].items():
            if stage in STAGES:
                products[case][stage] = load(directory / case / (stage + ".npz"), expected_sha256=report["sha256"])
    return summary, products


def coordinates(product):
    rows, cols = product["arrays"]["bed_m"].shape
    spacing = product["metadata"]["spacing_m"]
    return np.arange(cols) * spacing, np.arange(rows) * spacing, [-spacing / 2, (cols - .5) * spacing,
                                                                  -spacing / 2, (rows - .5) * spacing]


def wet_mask(product):
    return product["arrays"]["depth_m"] > product["metadata"]["config"]["bedload"]["dry_depth_m"]


def frame(ax, product):
    _, _, extent = coordinates(product)
    ax.set(xlim=extent[:2], ylim=extent[2:], aspect="equal", xlabel="局部 x（米）", ylabel="局部 z（米）")
    ax.tick_params(labelsize=8)


def wet_boundary(ax, product):
    wet = wet_mask(product)
    if wet.any() and not wet.all():
        x, z, _ = coordinates(product)
        half = product["metadata"]["spacing_m"] / 2
        segments = []
        for row, col in zip(*np.nonzero(wet[:, 1:] != wet[:, :-1])):
            edge_x = x[col] + half
            segments.append([(edge_x, z[row] - half), (edge_x, z[row] + half)])
        for row, col in zip(*np.nonzero(wet[1:] != wet[:-1])):
            edge_z = z[row] + half
            segments.append([(x[col] - half, edge_z), (x[col] + half, edge_z)])
        ax.add_collection(LineCollection(segments, colors="#233837", linewidths=.45))


def draw_map(ax, product, depth_norm, land_norm):
    arrays = product["arrays"]
    _, _, extent = coordinates(product)
    wet = wet_mask(product)
    ax.imshow(np.ma.masked_where(wet, arrays["bed_m"]), origin="lower", extent=extent,
              cmap=LAND, norm=land_norm, interpolation="nearest")
    ax.imshow(np.ma.masked_where(~wet, arrays["depth_m"]), origin="lower", extent=extent,
              cmap=WATER, norm=depth_norm, interpolation="nearest")
    wet_boundary(ax, product)
    frame(ax, product)


def save_figure(fig, output):
    fig.savefig(output, dpi=180, facecolor="white")
    plt.close(fig)


def overview(summary, products, output, stages, filename, title, depth_norm, land_norm, footnote=None):
    cases = list(products)
    fig, axes = plt.subplots(len(cases), len(stages), figsize=(4.4 * len(stages), 3.7 * len(cases)),
                             squeeze=False, layout="constrained")
    for row, case in enumerate(cases):
        for col, stage in enumerate(stages):
            ax = axes[row, col]
            product = products[case][stage]
            draw_map(ax, product, depth_norm, land_norm)
            report = summary["cases"][case]["stages"][stage]
            ax.set_title(f"{CASES[case]} · {STAGES[stage]}\n海床最大抬升 {report['maximum_offshore_rise_m']:.2f} 米")
    fig.colorbar(plt.cm.ScalarMappable(norm=depth_norm, cmap=WATER), ax=axes, shrink=.7,
                 label="有水格的实际水深（米）", pad=.015)
    fig.colorbar(plt.cm.ScalarMappable(norm=land_norm, cmap=LAND), ax=axes, shrink=.7,
                 label="干格床面高程（米）", pad=.015)
    fig.suptitle(title + "\n形成与维持待人工验收 · 原生 30 米网格 · 实际干湿 · 标称小时不计 5 分钟预热", fontsize=15)
    if footnote:
        fig.supxlabel(footnote, fontsize=10)
    save_figure(fig, output / filename)


def marks(ax, product, report):
    spacing = product["metadata"]["spacing_m"]
    cols = product["arrays"]["bed_m"].shape[1]
    for index, bar in enumerate(report["bars"]):
        row, col = bar["anchor_rc"]
        ax.plot(col * spacing, row * spacing, marker="*", color="#fce461", mec="#343414", ms=10)
        ax.text(col * spacing + 15, row * spacing + 15, str(index + 1), fontsize=8,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": .8, "pad": .5})
        for side, color in (("north", "#a0155c"), ("south", "#d65418")):
            for section in bar["sections"]:
                gate_row, gate_col = section[side]["cell_rc"]
                ax.plot((gate_col + .5) * spacing, gate_row * spacing, marker="|", color=color, ms=9, mew=1.8)
            path = bar["sides"][side]["path"]
            if bar["passed"] and path:
                path = np.asarray(path, dtype=int)
                ax.plot((path % cols) * spacing, (path // cols) * spacing, color=color, lw=1.1, alpha=.8)


def face_flows(product):
    arrays, metadata = product["arrays"], product["metadata"]
    dt = metadata["last_coupling_interval_s"]
    return arrays["internal_last_water_transfer_m3"] / dt if dt else np.zeros(len(arrays["face_left"]))


def diagnostics(summary, products, output, depth_norm, stage):
    cases = list(products)
    finals = [products[case][stage] for case in cases]
    bed_norm = colors.Normalize(min(p["arrays"]["bed_m"].min() for p in finals),
                                max(p["arrays"]["bed_m"].max() for p in finals))
    max_q = max(float(np.abs(face_flows(p)).max()) for p in finals)
    flux_norm = colors.Normalize(0, max(max_q, .01))
    fig, axes = plt.subplots(len(cases), 3, figsize=(17, 4.8 * len(cases)), squeeze=False, layout="constrained")
    fig.get_layout_engine().set(h_pad=.1, hspace=.12)
    for row, case in enumerate(cases):
        product = products[case][stage]
        report = summary["cases"][case]["stages"][stage]
        arrays = product["arrays"]
        x, z, extent = coordinates(product)
        axes[row, 0].imshow(arrays["bed_m"], origin="lower", extent=extent, cmap="terrain",
                            norm=bed_norm, interpolation="nearest")
        axes[row, 1].imshow(np.ma.masked_where(~wet_mask(product), arrays["depth_m"]), origin="lower",
                            extent=extent, cmap=WATER, norm=depth_norm, interpolation="nearest")
        axes[row, 1].set_facecolor("#e3e5df")
        axes[row, 2].imshow(wet_mask(product), origin="lower", extent=extent,
                            cmap=colors.ListedColormap(["#e3e5df", "#edf5f5"]), interpolation="nearest", vmin=0, vmax=1)
        left, right = arrays["face_left"], arrays["face_right"]
        points = np.column_stack([np.tile(x, len(z)), np.repeat(z, len(x))])
        q = face_flows(product)
        active = np.abs(q) > .0001
        segments = np.stack([points[left[active]], points[right[active]]], axis=1)
        relative = np.sqrt(np.abs(q[active]) / max(max_q, .01))
        collection = LineCollection(segments, cmap="inferno", norm=flux_norm,
                                    linewidths=.08 + 1.6 * relative, alpha=.08 + .92 * relative)
        collection.set_array(np.abs(q[active]))
        axes[row, 2].add_collection(collection)
        arrows = np.abs(q) >= .5
        centers = (points[left[arrows]] + points[right[arrows]]) / 2
        directions = (points[right[arrows]] - points[left[arrows]]) * np.sign(q[arrows, None])
        axes[row, 2].quiver(centers[:, 0], centers[:, 1], directions[:, 0], directions[:, 1],
                            angles="xy", scale_units="xy", scale=2, color="#48404b", width=.0013)
        status = "通过" if report["local_material_distributary_passed"] else "未通过"
        for col, name in enumerate(("床面高程", "实际水深", "面通量（箭头≥0.5立方米／秒）")):
            ax = axes[row, col]
            wet_boundary(ax, product)
            marks(ax, product, report)
            frame(ax, product)
            ax.set_title(f"{CASES[case]} · {STAGES[stage]}\n{name}")
        axes[row, 0].set_xlabel(f"局部 x（米）\n候选 {len(report['bars'])} 个；局部绕洲输水指标：{status}")
        axes[row, 1].set_xlabel(f"局部 x（米）\n水预算余差 {report['water_budget_residual_m3']:.2e} 立方米")
        axes[row, 2].set_xlabel(f"局部 x（米）\n泥沙预算余差 {report['solid_budget_residual_m3']:.2e} 立方米")
    for col, norm, cmap, label in ((0, bed_norm, "terrain", "床面（米）"),
                                    (1, depth_norm, WATER, "水深（米）；灰色为干格"),
                                    (2, flux_norm, "inferno", "面流量绝对值（立方米／秒）")):
        fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes[:, col], shrink=.7, label=label)
    legend = [Line2D([], [], marker="*", ls="", color="#b49814", label="报告候选沙洲"),
              Line2D([], [], color="#a0155c", marker="|", label="北侧断面与实际有向路径"),
              Line2D([], [], color="#d65418", marker="|", label="南侧断面与实际有向路径")]
    fig.legend(handles=legend, loc="outside lower center", ncol=3)
    fig.suptitle(f"{STAGES[stage]}物理诊断 · 形成与维持待人工验收\n仅对指标通过的候选绘制实际有向路径；成槽形态另待验收", fontsize=16)
    save_figure(fig, output / ("delta-" + stage + "-diagnostics.png"))


def cross_sections(summary, products, output):
    cases = list(products)
    fig, axes = plt.subplots(len(cases), 3, figsize=(18, 4.1 * len(cases)), squeeze=False,
                             layout="constrained")
    for row, case in enumerate(cases):
        product = products[case]["growth_24h"]
        report = summary["cases"][case]["stages"]["growth_24h"]
        bars = report["bars"]
        if not bars:
            for ax in axes[row]:
                ax.text(.5, .5, CASES[case] + "：报告没有沙洲候选", transform=ax.transAxes, ha="center")
                ax.set_axis_off()
            continue
        bar = next((candidate for candidate in bars if candidate["passed"]), bars[0])
        candidate_number = bars.index(bar) + 1
        spacing = product["metadata"]["spacing_m"]
        for col, section in enumerate(bar["sections"]):
            ax = axes[row, col]
            bed = np.asarray(section["bed_m_by_row"])
            depth = np.asarray(section["depth_m_by_row"])
            initial = np.asarray(section["initial_bed_m_by_row"])
            q = np.asarray(section["westward_q_m3_s_by_row"])
            across = np.arange(len(bed)) * spacing
            wet = depth > product["metadata"]["config"]["bedload"]["dry_depth_m"]
            ax.plot(across, initial, "--", color="#777777", label="初始床面", lw=1.1)
            ax.plot(across, bed, color="#263926", label="当前床面", lw=1.6)
            ax.plot(across, np.where(wet, bed + depth, np.nan), color="#127b9d", label="实际水面", lw=1.1)
            ax.fill_between(across, bed, bed + depth, where=wet, color="#65c9df", alpha=.25,
                            step="mid", label="实际水深")
            flux_axis = ax.twinx()
            flux_axis.plot(across, q, color="#9d2c7c", ls=":", lw=1.5, label="西向面流量")
            flux_axis.axhline(0, color="#9d2c7c", lw=.5, alpha=.4)
            flux_axis.set_ylabel("西向面流量（立方米／秒）", color="#9d2c7c", fontsize=9)
            flux_axis.tick_params(axis="y", labelsize=8, colors="#9d2c7c")
            for side, color in (("north", "#a0155c"), ("south", "#d65418")):
                gate_row = section[side]["cell_rc"][0]
                ax.axvline(gate_row * spacing, color=color, lw=.7, alpha=.8)
                ax.plot(gate_row * spacing, bed[gate_row], marker="v", color=color, ms=6)
            ax.set(xlabel="横断面 z（米）", ylabel="床高／水面高程（米）")
            ax.set_title(f"{CASES[case]} · 候选 {candidate_number}\n床面 x = {section['col'] * spacing:.0f} 米；流量面 x = {(section['col'] + .5) * spacing:.0f} 米")
            ax.grid(axis="y", alpha=.15)
            if row == 0 and col == 0:
                handles, labels = ax.get_legend_handles_labels()
                extra_handles, extra_labels = flux_axis.get_legend_handles_labels()
                fig.legend(handles + extra_handles, labels + extra_labels, loc="outside lower center", ncol=5)
    fig.suptitle("生长 24 小时 · 候选沙洲的三个完整横断面\n每例优先展示绕洲输水指标通过的首个候选，否则展示首个候选；两侧竖线为报告门位置", fontsize=15)
    save_figure(fig, output / "delta-growth_24h-cross-sections.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path, help="directory containing summary.json and both saved cases")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diagnostics", type=Path, help="separate rechecked summary directory; NPZ files remain in trial")
    args = parser.parse_args()
    configure_font()
    summary, products = read_trial(args.trial, args.diagnostics)
    output = args.output or args.trial / "images"
    output.mkdir(parents=True, exist_ok=True)
    depth_norm = colors.Normalize(0, max(float(p["arrays"]["depth_m"].max())
                                        for case in products.values() for p in case.values()))
    land_norm = colors.Normalize(min(float(p["arrays"]["bed_m"].min())
                                     for case in products.values() for p in case.values()),
                                 max(float(p["arrays"]["bed_m"].max())
                                     for case in products.values() for p in case.values()))
    overview(summary, products, output, ["initial", "growth_6h", "growth_24h", "recovered_48h"],
             "delta-overview.png", "三角洲生长与涨落水后对照", depth_norm, land_norm, THIN_WATER_NOTE)
    overview(summary, products, output, ["growth_6h", "growth_12h", "growth_24h"],
             "delta-growth.png", "供沙生长阶段", depth_norm, land_norm)
    overview(summary, products, output, ["growth_24h", "clearwater_36h", "flood_39h", "recession_42h"],
             "delta-clearwater-flood-recession.png", "停沙清水与流量涨落", depth_norm, land_norm, THIN_WATER_NOTE)
    diagnostics(summary, products, output, depth_norm, "growth_24h")
    diagnostics(summary, products, output, depth_norm, "recovered_48h")
    cross_sections(summary, products, output)
    print(str(output.resolve()))


if __name__ == "__main__":
    main()
