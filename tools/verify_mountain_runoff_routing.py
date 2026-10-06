"""Fixed task36 sources, six conservative reach-routing cases, independent review."""

import base64
from datetime import datetime, timezone
import hashlib
import html
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

from terrain_pipeline import mountain_runoff_routing as routing
from terrain_pipeline.rainfall_runoff import load_rainfall_runoff_npz
from tools.verify_mountain_rainfall import load_source, response_units


SOURCE = ROOT / "verification/mountain-rainfall/run-20261001T044308831149Z"
REPORT_SHA = "802083fc4604568635571baa71bc8a22ad3109483353ac30753942080179a9b4"
REVIEW_SHA = "89a983cf05c36637491a597935660b72d8af33059d939da7ec8b5bc6b8518f2c"
CONSTRAINTS = (
    "实验性守恒河段传播；示意速度1m/s，非校准洪水预报。人工开放边界仍为人工；"
    "原TD山地、历史限高conditioning、13格halo及海面平移全部保留。"
    "正驻留时间的库路由可经过原规划中的逆坡/人工填洼路径，不代表床面已修复。"
    "旧失败河床未认证；无水位、回水、Manning、漫滩或Minecraft水体验收。"
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, payload):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(payload)


def pinned_reports():
    if sha256(SOURCE / "report.json") != REPORT_SHA or sha256(SOURCE / "independent-review.json") != REVIEW_SHA:
        raise ValueError("accepted task36 report/review changed")
    report = json.loads((SOURCE / "report.json").read_text(encoding="utf-8"))
    review = json.loads((SOURCE / "independent-review.json").read_text(encoding="utf-8"))
    if review["report_sha256"] != REPORT_SHA or review["status"] != "accepted_bounded_rainfall_runoff":
        raise ValueError("task36 not accepted")
    return report, review


def accepted_case(name, scenario, report, review):
    case = report["samples"][name]["scenarios"][scenario]
    files = {case["npz"]: case["npz_sha256"], case["native_runoff_npz"]: case["native_runoff_npz_sha256"]}
    for filename, digest in files.items():
        if review["artifact_sha256"][filename] != digest or sha256(SOURCE / filename) != digest:
            raise ValueError("accepted scenario artifact changed")
    with np.load(SOURCE / case["npz"], allow_pickle=False) as archive:
        saved = {key: archive[key].copy() for key in archive.files}
    with patch("terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff", side_effect=AssertionError("no runoff")), \
         patch("terrain_pipeline.rainfall_runoff._release", side_effect=AssertionError("no advancement")):
        native = load_rainfall_runoff_npz(SOURCE / case["native_runoff_npz"])
    source = load_source(name)
    owner, area, mean, lower, upper = response_units(source["height_m"], source["spacing_m"])
    expected = {"height_m": source["height_m"], "receiver": source["receiver"].reshape(owner.shape),
                "legacy_flowline_mask": source["flowline_mask"], "outlet_mask": source["outlet_mask"],
                "cell_owner": owner, "area_m2": area, "hru_mean_height_m": mean,
                "hru_lower_m": lower, "hru_upper_m": upper,
                "origin_m_xz": np.asarray(source["origin_m_xz"]), "spacing_m": source["spacing_m"],
                "dt_s": 900., "interval_start_s": np.arange(1344) * 900.}
    for key, value in expected.items():
        if not np.array_equal(saved[key], value):
            raise ValueError(f"independent source grid mismatch: {key}")
    for key in ("local_q_m3_s", "rain_mm_h", "area_m2", "soil_mm", "fast_mm", "slow_mm"):
        if not np.array_equal(saved[key], native[key]):
            raise ValueError(f"scenario/native mismatch: {key}")
    if not np.array_equal(saved["actual_et_m3"], native["et_volume_m3"]):
        raise ValueError("ET mismatch")
    meta = json.loads(str(saved["metadata"].item()))
    if (meta["source_identity"] != report["samples"][name]["source_identity"]
            or native["metadata"] != meta["runoff_metadata"] or meta["parameters"] != case["parameters"]):
        raise ValueError("source/parameter metadata mismatch")
    inputs = {key: saved[key].copy() for key in routing.INPUT_KEYS if key != "flowline_mask"}
    inputs["flowline_mask"] = saved["legacy_flowline_mask"].copy()
    inputs["cell_owner"] = inputs["cell_owner"].astype(np.int64)
    binding = {"task36_directory": SOURCE.name, "report_sha256": REPORT_SHA,
               "independent_review_sha256": REVIEW_SHA, "artifacts": files,
               "mountain": name, "scenario": scenario, "source_identity": meta["source_identity"]}
    return inputs, binding, saved, source


def obstacles(inputs):
    receiver = inputs["receiver"].ravel()
    height = inputs["height_m"].ravel()
    cells = np.flatnonzero(inputs["flowline_mask"].ravel() & (receiver >= 0))
    rise = height[receiver[cells]] - height[cells]
    uphill = rise > 1e-9
    return {"legacy_channel_edges": int(cells.size), "uphill_edges": int(uphill.sum()),
            "maxrise_m": float(max(0., rise.max(initial=0.))),
            "total_positive_rise_m": float(rise[uphill].sum()),
            "uphill_threshold_m": 1e-9, "reference": "original saved height_m, not filled working surface",
            "physical_bed_fixed": False}


def independent_review(result, saved):
    """Separate path-walk, direct count allocation and constitutive-volume audit."""
    height = result["height_m"]
    receiver = result["receiver"].ravel()
    river = result["flowline_mask"].ravel() | result["outlet_mask"].ravel()
    river_owner = result["river_reach"].ravel()
    owners = result["cell_owner"].ravel()
    reaches = len(result["reach_downstream"])
    hrus = len(result["area_m2"])
    first = np.full(height.size, -1, dtype=np.int64)
    first[river] = river_owner[river]
    for start in range(height.size):
        current = start
        path = []
        while first[current] < 0:
            path.append(current)
            current = int(receiver[current])
            if current < 0 or len(path) > height.size:
                raise ValueError("independent first downstream river unreachable")
        first[path] = first[current]
    np.testing.assert_array_equal(first.reshape(height.shape), result["cell_reach"])
    land = height.ravel() > 0
    counts = np.zeros((reaches, hrus), dtype=np.int64)
    np.add.at(counts, (first[land], owners[land]), 1)
    np.testing.assert_array_equal(counts, result["allocation_counts"])
    np.testing.assert_array_equal(counts.sum(axis=0) * 900., result["area_m2"])
    donors = np.bincount(receiver[river & (receiver >= 0)], minlength=height.size)
    starts = river & ((donors != 1) | (receiver < 0))
    if starts.sum() != reaches:
        raise ValueError("independent maximal reach count")
    lengths = np.zeros(reaches)
    targets = np.full(reaches, -1, dtype=np.int64)
    transitions = np.zeros(reaches, dtype=np.int64)
    width = height.shape[1]
    for current in np.flatnonzero(river):
        reach = river_owner[current]
        target = receiver[current]
        if reach < 0 or reach >= reaches:
            raise ValueError("river owner invalid")
        if target >= 0:
            lengths[reach] += 30. * np.hypot(current // width - target // width,
                                          current % width - target % width)
            if river_owner[target] != reach:
                targets[reach] = river_owner[target]
                transitions[reach] += 1
    if (transitions > 1).any() or not np.array_equal(targets, result["reach_downstream"]):
        raise ValueError("reach has multiple downstream connections")
    position = np.argsort(result["reach_order"])
    for reach, target in enumerate(targets):
        if target >= 0 and position[reach] >= position[target]:
            raise ValueError("non-topological routing")
    np.testing.assert_allclose(lengths, result["reach_length_m"], rtol=1e-12)
    np.testing.assert_allclose(result["tau_s"], np.maximum(lengths, 30.))
    terminal_cells = np.flatnonzero(receiver < 0)
    for current in terminal_cells:
        reach = river_owner[current]
        if (np.count_nonzero(river_owner == reach) != 1 or lengths[reach] != 0
                or result["tau_s"][reach] != 30.):
            raise ValueError("terminal must have dedicated minimum-length reach")
    dt = result["metadata"]["dt_s"]
    lateral = np.zeros_like(result["lateral_volume_m3"])
    for hru in range(hrus):
        lateral += (result["local_q_m3_s"][:, hru, None] * dt
                    * counts[None, :, hru] / counts[:, hru].sum())
    upstream = np.zeros_like(lateral)
    outflow = result["outflow_volume_m3"]
    for reach, target in enumerate(targets):
        if target >= 0:
            upstream[:, target] += outflow[:, reach]
    storage = result["storage_m3"]
    np.testing.assert_array_equal(storage[0], 0.)
    np.testing.assert_allclose(result["lateral_volume_m3"], lateral, rtol=1e-12, atol=1e-8)
    np.testing.assert_allclose(result["upstream_volume_m3"], upstream, rtol=1e-12, atol=1e-8)
    np.testing.assert_allclose(outflow, dt / result["tau_s"] * storage[1:], rtol=1e-12, atol=1e-8)
    reach_residual = lateral + upstream - outflow - np.diff(storage, axis=0)
    np.testing.assert_allclose(reach_residual, 0., atol=1e-8)
    outlet_volume = outflow[:, targets < 0].sum(axis=1)
    np.testing.assert_allclose(result["outlet_q_m3_s"], outlet_volume / dt, rtol=1e-12)
    rain = saved["rain_mm_h"].sum(axis=0) * 900. / 3600. * .001 * saved["area_m2"]
    soil_fast_slow = sum(saved[key + "_mm"] * .001 * saved["area_m2"] for key in ("soil", "fast", "slow"))
    for key in ("soil", "fast", "slow"):
        np.testing.assert_array_equal(saved[key + "_m3"], saved[key + "_mm"] * .001 * saved["area_m2"])
    rainfall_interval = (saved["rain_mm_h"] * 900. / 3600. * .001 * saved["area_m2"]).sum(axis=1)
    et_interval = saved["actual_et_m3"].sum(axis=1)
    local = saved["local_q_m3_s"].sum(axis=1)
    native_interval_residual = rainfall_interval - et_interval - local * 900. - np.diff(soil_fast_slow.sum(axis=1))
    global_interval_residual = (result["local_q_m3_s"].sum(axis=1) * dt
                                - outlet_volume - np.diff(storage.sum(axis=1)))
    np.testing.assert_allclose(native_interval_residual, 0., atol=1e-7)
    np.testing.assert_allclose(global_interval_residual, 0., atol=1e-7)
    aggregate = float(rain.sum() - saved["actual_et_m3"].sum()
                      - (soil_fast_slow[-1].sum() - soil_fast_slow[0].sum())
                      - storage[-1].sum() - outlet_volume.sum())
    if abs(aggregate) > 1e-5:
        raise ValueError("independent rain+ET+soil+reach+outlet aggregate mass")
    return {"first_downstream_cell_mapping_equal": True, "allocated_land_cells": int(land.sum()),
            "confluence_cells": int((river & (donors > 1)).sum()), "terminal_cells": int(terminal_cells.size),
            "max_reach_interval_residual_m3": float(np.abs(reach_residual).max()),
            "max_global_routing_interval_residual_m3": float(np.abs(global_interval_residual).max()),
            "max_native_interval_residual_m3": float(np.abs(native_interval_residual).max()),
            "rainfall_m3": float(rain.sum()), "ET_m3": float(saved["actual_et_m3"].sum()),
            "initial_soil_fast_slow_m3": float(soil_fast_slow[0].sum()),
            "final_soil_fast_slow_m3": float(soil_fast_slow[-1].sum()),
            "final_reach_storage_m3": float(storage[-1].sum()), "outlet_m3": float(outlet_volume.sum()),
            "aggregate_mass_residual_m3": aggregate}


def hydro_metrics(local, outlet, dt):
    result = {"local_peak_m3_s": float(local.max()), "outlet_peak_m3_s": float(outlet.max()),
              "local_peak_interval_end_h": float((local.argmax() + 1) * dt / 3600),
              "outlet_peak_interval_end_h": float((outlet.argmax() + 1) * dt / 3600),
              "peak_attenuation_fraction": float(1 - outlet.max() / local.max()),
              "peak_delay_h": float((outlet.argmax() - local.argmax()) * dt / 3600)}
    for hours in (24, 48, 96, 168, 336):
        index = int(hours * 3600 / dt) - 1
        result[f"local_{hours}h_m3_s"] = float(local[index])
        result[f"outlet_{hours}h_m3_s"] = float(outlet[index])
    result["local_volume_centroid_h"] = float(np.dot(local, (np.arange(local.size) + .5) * dt / 3600) / local.sum())
    result["outlet_volume_centroid_h"] = float(np.dot(outlet, (np.arange(outlet.size) + .5) * dt / 3600) / outlet.sum())
    return result


def image_data(figure):
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=120, bbox_inches="tight")
    plt.close(figure)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def terrain_panel(result, source):
    height = result["height_m"]
    origin_x, origin_z = source["origin_m_xz"]
    rows, cols = height.shape
    extent = [(origin_x - 15) / 1000, (origin_x + (cols - .5) * 30) / 1000,
              (origin_z + (rows - .5) * 30) / 1000, (origin_z - 15) / 1000]
    figure, axes = plt.subplots(1, 2, figsize=(15, 7))
    image = axes[0].imshow(height, extent=extent, cmap="terrain")
    figure.colorbar(image, ax=axes[0], label="Original shifted TD height (m)")
    axes[1].imshow(np.ma.masked_less(result["cell_reach"], 0), extent=extent, cmap="tab20")
    receiver = result["receiver"].ravel()
    cells = np.flatnonzero(result["flowline_mask"].ravel() & (receiver >= 0))
    target = receiver[cells]
    rise = height.ravel()[target] - height.ravel()[cells]
    upstream_points = np.column_stack(((origin_x + cells % cols * 30) / 1000,
                                       (origin_z + cells // cols * 30) / 1000))
    downstream_points = np.column_stack(((origin_x + target % cols * 30) / 1000,
                                         (origin_z + target // cols * 30) / 1000))
    segments = np.stack((upstream_points, downstream_points), axis=1)
    for axis in axes:
        axis.add_collection(LineCollection(segments, colors="#1269dc", linewidths=.8, label="All original flowline edges"))
        axis.add_collection(LineCollection(segments[rise > 1e-9], colors="#ff1835", linewidths=1.8, label="Uphill on original terrain"))
        terminal = np.flatnonzero(receiver < 0)
        axis.scatter((origin_x + terminal % cols * 30) / 1000,
                     (origin_z + terminal // cols * 30) / 1000, marker="x", c="black", label="Artificial outlet")
        axis.set(xlabel="X (km), sample centers", ylabel="Z (km), sample centers")
        axis.legend(fontsize=7)
    axes[0].set_title("Immutable TD terrain / original planned route obstacles")
    axes[1].set_title("First downstream reach catchments (colors repeat)")
    return image_data(figure)


def hydro_panel(cases):
    figure, axes = plt.subplots(3, 2, figsize=(14, 11))
    for row, (scenario, result) in enumerate(cases.items()):
        time = (np.arange(1344) + 1) * .25
        local = result["local_q_m3_s"].sum(axis=1)
        outlet = result["outlet_q_m3_s"]
        for col in range(2):
            axis = axes[row, col]
            axis.plot(time, local, label="Local input total (not routed)")
            axis.plot(time, outlet, label="Artificial outlet, reach-routed")
            axis.set(xlabel="Physical time (h)", ylabel="Interval-average Q (m3/s)", title=scenario)
            if col == 0:
                axis.set_xlim(0, 48)
            else:
                axis.set_yscale("log")
                axis.set_xlim(24, 336)
            axis.legend(fontsize=8)
    figure.tight_layout()
    return image_data(figure)


def slider_data(result):
    receiver = result["receiver"].ravel()
    cells = np.flatnonzero(result["flowline_mask"].ravel() & (receiver >= 0))
    width = result["height_m"].shape[1]
    target = receiver[cells]
    river_reach = result["river_reach"].ravel()[cells]
    rise = result["height_m"].ravel()[target] - result["height_m"].ravel()[cells]
    segments = np.column_stack((cells % width, cells // width, target % width, target // width,
                                river_reach, rise > 1e-9)).tolist()
    reach_q = result["outflow_volume_m3"] / 900.
    outlet = result["outlet_q_m3_s"]
    local = result["local_q_m3_s"].sum(axis=1)
    return {"shape": list(result["height_m"].shape), "segments": segments,
            "reach_q": np.round(reach_q, 5).tolist(), "outlet": outlet.tolist(), "local": local.tolist()}


def write_html(output, report, panels, slider):
    sections = []
    for name, images in panels.items():
        geo = report["mountains"][name]
        sections.append(f'<h2>{html.escape(name)}</h2><p>河段 {geo["reach_count"]}；原河线逆坡边 '
                        f'{geo["obstacles"]["uphill_edges"]}；最大单边抬升 {geo["obstacles"]["maxrise_m"]:.3f} m。'
                        '红线为原地形逆坡；它们未被本次储水路由修复。</p>'
                        + ''.join(f'<img alt="TD地形/河段归属或局地与出口过程线" src="{image}">' for image in images))
    payload = json.dumps(slider, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>山地河段守恒传播独立审查</title><style>body{max-width:1450px;margin:auto;padding:24px;font-family:system-ui;background:#f4f6f8;color:#182537}img{width:100%}canvas{background:#dde8d7;border:1px solid #aab}p{line-height:1.6}pre{white-space:pre-wrap}</style>
<h1>山地河段守恒传播 · 实验 v1</h1><p>CONSTRAINTS</p>
<p>蓝线：全部原规划河线；红线：原TD地形上的逆坡边。本次只加入储水/释放传播，不修床、不认证自然海口。
每个陆地格唯一归属首次下游河段，64 HRU局地产流按格数分配，绝不复用瞬时累积量。
节点无储水；河段零初始储水。τ=max(原receiver边长之和,30m)/1m/s；终端独立河段无出边，采用30m有效长度。
地图线坐标位于原样本中心；imshow边界半格扩展只是正确显示像素足迹，不平移线坐标。</p>
SECTIONS
<h2>二维河段流量时间浏览（湿土暴雨）</h2>
<p>背景为离散网格，不表示水深或淹没。颜色强度表示区间平均河段输出；逆坡边始终红色。完整1344步、全部原河线。</p>
<select id="mountain"></select><input id="time" type="range" min="0" max="1343" value="48" style="width:60%"><p id="caption"></p><canvas id="map" width="780" height="780"></canvas>
<h2>审查与数值敏感性</h2><p>450s对照仅将同一保存900s区间的局地产流恒定拆成两半，不重新运行降雨/土壤模型。
记录峰值、峰时、168/336h尾流、区间均值差与最终储水差；这是路由离散化敏感性，不是完整模型收敛证明。</p><pre id="metrics"></pre>
<script>const data=SLIDER;const report=REPORT;
const select=document.getElementById('mountain'),time=document.getElementById('time');
for(const name of Object.keys(data)){const option=document.createElement('option');option.value=name;option.textContent=name;select.appendChild(option);}
function draw(){const item=data[select.value],step=Number(time.value),canvas=document.getElementById('map'),ctx=canvas.getContext('2d');
ctx.clearRect(0,0,780,780);const scale=760/Math.max(...item.shape),flux=item.reach_q[step],maximum=Math.max(1,...flux);
for(const segment of item.segments){const value=flux[segment[4]];ctx.strokeStyle=segment[5]?'#ff1835':`hsl(215 95% ${75-45*Math.sqrt(value/maximum)}%)`;ctx.lineWidth=segment[5]?2:1+2*Math.sqrt(value/maximum);ctx.beginPath();ctx.moveTo(10+segment[0]*scale,10+segment[1]*scale);ctx.lineTo(10+segment[2]*scale,10+segment[3]*scale);ctx.stroke();}
document.getElementById('caption').textContent=`区间终点 ${(step+1)*.25} h；局地总量 ${item.local[step].toFixed(3)} m³/s；人工出口 ${item.outlet[step].toFixed(3)} m³/s`;
}select.onchange=draw;time.oninput=draw;draw();document.getElementById('metrics').textContent=JSON.stringify(report,null,2);</script></html>'''
    document = document.replace("CONSTRAINTS", html.escape(CONSTRAINTS)).replace("SECTIONS", ''.join(sections))
    document = document.replace("SLIDER", payload).replace("REPORT", json.dumps(report, ensure_ascii=True))
    write_new(output / "review.html", document)


def main():
    report_source, review_source = pinned_reports()
    output = ROOT / "verification/mountain-runoff-routing" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "mountain-runoff-routing-verification-v1", "constraints": CONSTRAINTS,
              "source_directory": str(SOURCE.relative_to(ROOT)), "source_report_sha256": REPORT_SHA,
              "source_review_sha256": REVIEW_SHA, "duration_h": 336, "steps": 1344,
              "illustrative_speed_m_s": 1., "minimum_length_m": 30., "mountains": {}}
    panels, slider, independent = {}, {}, {}
    for name in ("normal_mountain", "pressure_mountain"):
        cases = {}
        mountain = {"cases": {}}
        for scenario in ("dry_storm", "wet_storm", "steady"):
            print(f"Routing {name}/{scenario}", flush=True)
            inputs, binding, saved, source = accepted_case(name, scenario, report_source, review_source)
            result = routing.route_local_discharge(inputs, dt_s=900., spacing_m=30., source_binding=binding)
            audit = independent_review(result, saved)
            artifact = output / f"{name}-{scenario}.npz"
            routing.save_routing_npz(artifact, result)
            with patch.object(routing, "build_reaches", side_effect=AssertionError("no assembly on load")), \
                 patch.object(routing, "route_local_discharge", side_effect=AssertionError("no routing on load")), \
                 patch("terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff", side_effect=AssertionError("no runoff on load")):
                loaded = routing.load_routing_npz(artifact, trusted_inputs=inputs, source_binding=binding)
            for key in routing.ARRAY_KEYS:
                np.testing.assert_array_equal(result[key], loaded[key])
            fine_inputs = dict(inputs, local_q_m3_s=np.repeat(inputs["local_q_m3_s"], 2, axis=0))
            fine_binding = dict(binding, interval_split="same constant local inputs; 900s -> 2 x 450s")
            fine = routing.route_local_discharge(fine_inputs, dt_s=450., spacing_m=30., source_binding=fine_binding)
            fine_audit = independent_review(fine, saved)
            local = inputs["local_q_m3_s"].sum(axis=1)
            metrics = hydro_metrics(local, result["outlet_q_m3_s"], 900.)
            fine_metrics = hydro_metrics(fine_inputs["local_q_m3_s"].sum(axis=1), fine["outlet_q_m3_s"], 450.)
            if metrics["peak_attenuation_fraction"] <= 0 or metrics["peak_delay_h"] <= 0:
                raise ValueError("saved scenarios must show delayed and attenuated outlet peaks")
            coarse_average_fine = fine["outlet_q_m3_s"].reshape(1344, 2).mean(axis=1)
            sensitivity = {"forcing": "identical interval-constant local HRU discharge; not rainfall resimulation",
                "fine_dt_s": 450., "fine_steps": 2688, "fine_metrics": fine_metrics,
                "max_interval_mean_difference_m3_s": float(np.abs(coarse_average_fine - result["outlet_q_m3_s"]).max()),
                "relative_L1_outlet_difference": float(np.abs(coarse_average_fine - result["outlet_q_m3_s"]).sum() / result["outlet_q_m3_s"].sum()),
                "peak_difference_m3_s": fine_metrics["outlet_peak_m3_s"] - metrics["outlet_peak_m3_s"],
                "peak_time_difference_h": fine_metrics["outlet_peak_interval_end_h"] - metrics["outlet_peak_interval_end_h"],
                "final_reach_storage_difference_m3": float(fine["storage_m3"][-1].sum() - result["storage_m3"][-1].sum()),
                "fine_independent_budget": fine_audit,
                "fine_preflight": routing.preflight(2688, inputs["height_m"].size, 64, len(fine["tau_s"]))}
            mountain["cases"][scenario] = {"artifact": artifact.name, "sha256": sha256(artifact),
                "source_binding": binding, "hydrograph": metrics, "independent_budget": audit,
                "discretization_sensitivity": sensitivity, "cold_static_reload_equal": True}
            independent[f"{name}/{scenario}"] = audit
            cases[scenario] = result
        wet = cases["wet_storm"]
        mountain.update({"reach_count": len(wet["tau_s"]), "land_cells": inputs["height_m"].size,
            "legacy_flowline_cells": int(inputs["flowline_mask"].sum()), "obstacles": obstacles(inputs),
            "minimum_tau_s": float(wet["tau_s"].min()), "maximum_tau_s": float(wet["tau_s"].max()),
            "total_original_edge_length_m": float(wet["reach_length_m"].sum()),
            "terminal_reach_original_length_m": wet["reach_length_m"][wet["reach_downstream"] < 0].tolist(),
            "preflight": routing.preflight(1344, inputs["height_m"].size, 64, len(wet["tau_s"]))})
        report["mountains"][name] = mountain
        panels[name] = (terrain_panel(wet, source), hydro_panel(cases))
        slider[name] = slider_data(wet)
    report["implementation_sha256"] = {path: sha256(ROOT / path) for path in (
        "terrain_pipeline/mountain_runoff_routing.py", "tests/test_mountain_runoff_routing.py",
        "tools/verify_mountain_runoff_routing.py", "docs/mountain-runoff-routing-v1.md")}
    write_new(output / "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    independent_report = {"status": "accepted_experimental_conservative_reach_propagation_not_physical_bed",
                          "report_sha256": sha256(output / "report.json"), "cases": independent,
                          "validation": "independent cell walks, edge topology/length, allocation counts, static reservoir equations, aggregate rain/ET/soil/reach/outlet",
                          "source_report_sha256": REPORT_SHA, "source_review_sha256": REVIEW_SHA}
    write_new(output / "independent-review.json", json.dumps(independent_report, ensure_ascii=False, indent=2))
    write_html(output, report, panels, slider)
    pinned_reports()
    for name in ("normal_mountain", "pressure_mountain"):
        for scenario in ("dry_storm", "wet_storm", "steady"):
            accepted_case(name, scenario, report_source, review_source)
    print(output, flush=True)


if __name__ == "__main__":
    main()
