"""CPU-only pinned dual-TD geometry, exact pool cascades and Chinese review."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage

from terrain_pipeline import mountain_depression_geometry as geometry
from terrain_pipeline import mountain_fine_geometry as fine
from terrain_pipeline import mountain_fine_storage as fine_storage
from terrain_pipeline import mountain_pool_network as pools
from terrain_pipeline.mountain_fine_mesh import export_fine_mesh
from terrain_pipeline.mountain_lake_experiment import first_lake_ownership
from terrain_pipeline.surface_rivers.drainage import route
from tools.verify_mountain_rainfall import SOURCE_NAMES, EXPECTED, load_source
from tools.verify_mountain_runoff_routing import pinned_reports, accepted_case


SCENARIOS = ("dry_storm", "wet_storm", "steady")
MAX_GROUP_ATTEMPTS = 10
FROZEN_FILES = (
    "terrain_pipeline/surface_rivers/drainage.py", "terrain_pipeline/mountain_runoff_routing.py",
    "terrain_pipeline/rainfall_runoff.py", "terrain_pipeline/lake_balance.py", "terrain_pipeline/lake_routing.py",
    "terrain_pipeline/lake_river_connector.py", "terrain_pipeline/surface_lake_network.py",
    "terrain_pipeline/surface_variable_storage.py", "terrain_pipeline/dynamic_surface_hydraulics.py",
    "terrain_pipeline/metric_channel_plan.py", "terrain_pipeline/local_channel_sections.py",
    "terrain_pipeline/channel_stage.py", "terrain_pipeline/channel_inundation.py",
    "terrain_pipeline/network_valley.py", "terrain_pipeline/valley_geometry.py",
    "terrain_pipeline/surface_network_prepare.py", "terrain_pipeline/surface_network_recovery.py",
    "terrain_pipeline/surface_fine_mosaic.py", "terrain_pipeline/surface_multidomain_dynamic.py",
    "tools/verify_mountain_rainfall.py", "tools/verify_mountain_runoff_routing.py",
    "tests/test_mountain_rainfall.py", "tests/test_mountain_runoff_routing.py",
    "diffusion/physical_config.py", "terrain_pipeline/minecraft_preset.py",
    "tests/test_physical_generation.py", "tests/test_minecraft_preset.py",
)


def frozen_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FROZEN_FILES}


def json_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def array_json(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: array_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [array_json(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def binding(name, source):
    return {"mountain": name, "pinned_river_npz_sha256": EXPECTED[name]["river"],
            "raw_td_sha256": EXPECTED[name]["raw"], "provenance_sha256": EXPECTED[name]["provenance"],
            "historical_conditioning": "geographic_v5_game_headroom_120m_legacy_13cell_halo_crop_sea_datum_shift_only",
            "height_source": "tools.verify_mountain_rainfall.load_source.height_m_not_filled"}


def diagnostic(height, escape, receiver, flowline, spacing):
    depressed = escape > height + 1e-9
    labels4, count4 = ndimage.label(depressed, ndimage.generate_binary_structure(2, 1))
    _, count8 = ndimage.label(depressed, ndimage.generate_binary_structure(2, 2))
    donors = np.flatnonzero(flowline.ravel() & (receiver >= 0))
    rises = height.ravel()[receiver[donors]] - height.ravel()[donors]
    uphill = donors[rises > 1e-9]
    boundary = geometry.window_boundary(height.shape).ravel()
    targets = receiver[donors]
    boundary_edges = boundary[donors] & boundary[targets]
    length = spacing * np.hypot(donors // height.shape[1] - targets // height.shape[1], donors % height.shape[1] - targets % height.shape[1])
    return {"positive_fill_cells": int(depressed.sum()), "max_escape_depth_m": float((escape - height).max()),
            "equilibrium_geometric_capacity_m3": float((escape - height).sum() * spacing ** 2),
            "four_connected_positive_components": int(count4), "eight_connected_positive_components": int(count8),
            "flowline_cells": int(flowline.sum()), "original_H0_channel_uphill_edges": int(uphill.size),
            "dry_original_uphill_edges": int(np.count_nonzero(~depressed.ravel()[uphill])),
            "boundary_channel_length_m": float(length[boundary_edges].sum()),
            "all_channel_edge_length_m": float(length.sum()), "capacity_not_actual_water": True}


def save_npz_new(path, arrays):
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = tempfile.mkstemp(prefix=".geometry-evidence-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def maps(output, name, source, result, d8_single, d8_open, no_cut):
    arrays = result["arrays"]
    extent = [0, source["height_m"].shape[1] * 30 / 1000, source["height_m"].shape[0] * 30 / 1000, 0]
    figure, axes = plt.subplots(2, 3, figsize=(17, 10))
    panels = ((source["height_m"], "H0 original saved TD (m)", "terrain"),
              (d8_single.routing_height - source["height_m"], "D8 old SINGLE artificial outlet: escape depth (m)", "magma"),
              (d8_open.routing_height - source["height_m"], "D8 ALL explicit truncated-open edges: depth (m)", "magma"),
              (np.where(arrays["lake_mask"], arrays["escape_level_m"] - arrays["H0_m"], np.nan), "D4 potential fill depth (m), NOT actual water", "Blues"),
              (arrays["accepted_mask"].astype(float), "Construction groups: accepted=1 / unselected=0", "RdYlGn"),
              (arrays["cut_depth_m"], "Actual H0-H2 cut (m); no fill", "inferno"))
    for axis, (values, title, cmap) in zip(axes.ravel(), panels):
        image = axis.imshow(values, extent=extent, cmap=cmap)
        figure.colorbar(image, ax=axis, shrink=.7)
        axis.set(title=title, xlabel="Window X (km)", ylabel="Window Z (km)")
    figure.tight_layout()
    figure.savefig(output / f"{name}-full-window.png", dpi=140)
    plt.close(figure)
    figure, axes = plt.subplots(1, 2, figsize=(13, 6))
    accumulation = np.ones(source["height_m"].size, dtype=np.float64) * 900
    for cell in d8_single.order[::-1]:
        if d8_single.receiver[cell] >= 0:
            accumulation[d8_single.receiver[cell]] += accumulation[cell]
    same_threshold = (accumulation >= 1e6).reshape(source["height_m"].shape)
    for axis, mask, title in ((axes[0], same_threshold, "D8 single artificial outlet: SAME 1 km2 threshold"),
                              (axes[1], arrays["flowline_mask"], "New D4 explicit edge-open + retained lakes")):
        axis.imshow(source["height_m"], extent=extent, cmap="terrain", alpha=.7)
        axis.imshow(np.where(mask, 1., np.nan), extent=extent, cmap="Reds", alpha=.9)
        axis.set(title=title, xlabel="Window X (km)", ylabel="Window Z (km)")
    figure.tight_layout()
    figure.savefig(output / f"{name}-routes.png", dpi=140)
    plt.close(figure)


def fine_panels(output, name, chain):
    if chain is None:
        return
    arrays = chain["arrays"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot(arrays["along_m"], arrays["H0_m"][:, 5], label="H0 source centre")
    axes[0].plot(arrays["along_m"], arrays["H2_m"][:, 5], label="H2 fine bed")
    axes[0].set(xlabel="Along continuous chain (m)", ylabel="Elevation (m)", title="3 shared-node segments; explicit local receiving seam")
    for row in [0] + arrays["shared_node_section_rows"].tolist() + [arrays["H0_m"].shape[0] - 1]:
        axes[1].plot(arrays["across_m"], arrays["H0_m"][row], linestyle="--", alpha=.7)
        axes[1].plot(arrays["across_m"], arrays["H2_m"][row], label=f"section at {row} m")
    axes[1].set(xlabel="Transverse offset (m)", ylabel="Elevation (m)", title="Original bilinear TD vs cosine-taper bed")
    for axis in axes:
        axis.legend()
        axis.grid(alpha=.3)
    figure.tight_layout()
    figure.savefig(output / f"{name}-fine-sections.png", dpi=140)
    plt.close(figure)


def hydro_panels(output, name, cases):
    figure, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    for scenario, case in cases.items():
        values = case["arrays"]
        time_h = np.arange(case["completed_steps"]) * case["dt_s"] / 3600
        axes[0].plot(time_h, values["lateral_volume_m3"].sum(axis=1) / case["dt_s"], label=scenario)
        axes[0].plot(time_h, values["external_outflow_volume_m3"] / case["dt_s"], linestyle="--")
        axes[1].plot(np.r_[time_h, case["completed_steps"] * case["dt_s"] / 3600], values["storage_m3"].sum(axis=1), label=scenario)
        axes[2].plot(time_h, values["joint_residual_m3"], label=scenario)
    axes[0].set(ylabel="Local / external Q (m3/s)", title="Complete no-cut contribution group: exact weir, no river travel time")
    axes[1].set(ylabel="Actual pool storage (m3)")
    axes[2].set(ylabel="Joint interval residual (m3)", xlabel="Physical time (h)")
    for axis in axes:
        axis.grid(alpha=.3)
        axis.legend()
    figure.tight_layout()
    figure.savefig(output / f"{name}-pool-hydrographs.png", dpi=140)
    plt.close(figure)


def fine_dynamic_cases(output, name, chain, result):
    support = fine_storage.fine_storage_support(chain)
    minimum = support["min_bed_m"]
    level = float(support["max_stage_m"].min() - .02)
    steps = 120
    nodes = minimum.size
    partial = np.maximum(minimum, level)
    zero = np.zeros((steps, nodes), dtype=np.float64)
    pulse = zero.copy()
    pulse[12:36, -1] = .003
    cases = {
        "partial_static": (partial, zero, np.full(steps + 1, level), np.full(steps + 1, level)),
        "dry_initial": (minimum.copy(), zero, np.full(steps + 1, minimum[0]), np.full(steps + 1, minimum[-1])),
        "tailwater_backflow": (minimum.copy(), zero, np.full(steps + 1, minimum[0]), np.full(steps + 1, minimum[-1] + .08)),
        "local_pulse": (minimum.copy(), pulse, np.full(steps + 1, minimum[0]), np.full(steps + 1, minimum[-1])),
        "bank_failure": (partial, np.full_like(zero, 1.), np.full(steps + 1, level), np.full(steps + 1, level)),
    }
    summaries = {}
    saved_cases = {}
    for scenario, (initial, local, upstream, tailwater) in cases.items():
        saved = fine_storage.prepare_fine_storage(chain, result, initial_stage_m=initial,
            local_q_m3_s=local, upstream_stage_m=upstream, tailwater_stage_m=tailwater, dt_s=10.)
        path = output / f"{name}-fine-{scenario}.npz"
        fine_storage.save_fine_storage(path, saved, chain, result)
        with patch.object(fine_storage, "fine_storage_support", side_effect=AssertionError("no support assembly")), \
             patch.object(fine_storage, "prepare_fine_storage", side_effect=AssertionError("no dynamics")), \
             patch.object(fine, "prepare_fine_segment", side_effect=AssertionError("no fine prepare")), \
             patch.object(fine, "select_continuous_fine_geometry", side_effect=AssertionError("no fine selection")):
            cold = fine_storage.load_fine_storage(path, chain, result)
        evidence = fine_storage.validate_fine_storage(cold, chain, result)
        summaries[scenario] = {"status": saved["status"], "committed_steps": saved["committed_steps"],
                               "failure": saved["failure"], "static_validation": evidence,
                               "boundary": "explicit_artificial_local_upstream_head_and_tailwater_not_rainfall_coupled"}
        saved_cases[scenario] = saved
        mesh = export_fine_mesh(chain, cold, result)
        save_npz_new(output / f"{name}-fine-{scenario}-mesh.npz", mesh["arrays"])
        json_new(output / f"{name}-fine-{scenario}-mesh-metadata.json", mesh["metadata"])
        review_data = dict(mesh["metadata"], arrays=array_json(mesh["arrays"]))
        json_new(output / f"{name}-fine-{scenario}-mesh.json", review_data)
    coarse = saved_cases["local_pulse"]
    initial, local, upstream, tailwater = cases["local_pulse"]
    refined = fine_storage.prepare_fine_storage(chain, result, initial_stage_m=initial,
        local_q_m3_s=np.repeat(local, 2, axis=0), upstream_stage_m=np.full(steps * 2 + 1, upstream[0]),
        tailwater_stage_m=np.full(steps * 2 + 1, tailwater[0]), dt_s=5.)
    fine_storage.save_fine_storage(output / f"{name}-fine-local_pulse-dt5.npz", refined, chain, result)
    final_coarse = coarse["arrays"]["storage_m3"][-1].sum()
    final_fine = refined["arrays"]["storage_m3"][-1].sum()
    summaries["dt_sensitivity"] = {"coarse_dt_s": 10., "fine_dt_s": 5.,
                                    "final_storage_relative_difference": float(abs(final_coarse - final_fine) / max(final_fine, 1e-12)),
                                    "coarse_status": coarse["status"], "fine_status": refined["status"]}
    figure, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for scenario, saved in saved_cases.items():
        state_time = np.arange(saved["committed_steps"] + 1) * saved["dt_s"]
        axes[0].plot(state_time, saved["arrays"]["storage_m3"].sum(axis=1), label=scenario)
        axes[1].plot(state_time[:-1], saved["arrays"]["qedges_m3_s"][:, -1], label=scenario)
    axes[0].set(ylabel="Fine actual V(h) storage (m3)", title="Artificial local boundaries; NOT whole-mountain rainfall coupling")
    axes[1].set(xlabel="Physical time (s)", ylabel="Signed downstream Q (m3/s); negative=backflow")
    for axis in axes:
        axis.legend()
        axis.grid(alpha=.3)
    figure.tight_layout()
    figure.savefig(output / f"{name}-fine-dynamics.png", dpi=140)
    plt.close(figure)
    return summaries, saved_cases


def write_mesh_review(output):
    names = SOURCE_NAMES
    datasets = {}
    for name in names:
        datasets[name] = {}
        for scenario in ("partial_static", "dry_initial", "tailwater_backflow", "local_pulse", "bank_failure"):
            datasets[name][scenario] = json.loads((output / f"{name}-fine-{scenario}-mesh.json").read_text(encoding="utf-8"))
    encoded = json.dumps(datasets, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>同源细河床三维只读回放</title>
<style>body{font:16px sans-serif;background:#eeeade;margin:20px}canvas{background:#fafaf5;width:100%;max-width:1400px;height:620px;border:1px solid #888}label{margin:10px}pre{white-space:pre-wrap}strong{color:#923c20}</style>
<h1>90m连续细河床 / 离散湿支持水柱</h1><p><strong>人工入口与尾水试验，非完整山地降雨联算。不是Saint-Venant，不是天然海口。</strong></p>
<p>床面固定对角线三角；水只显示湿支持点/小柱，权重体积与求解V(h)一致，不插值成假连续水面。鼠标拖动旋转，滚轮缩放。</p>
<label>山地<select id="mountain"><option value="normal_mountain">普通山地</option><option value="pressure_mountain">压力山地</option></select></label>
<label>场景<select id="scenario"><option value="partial_static">部分湿静水</option><option value="dry_initial">干初始</option><option value="tailwater_backflow">尾水抬升倒灌</option><option value="local_pulse">局地脉冲</option><option value="bank_failure">超岸拒绝，仅提交状态</option></select></label>
<label>床面<select id="surface"><option value="vertices_H2_local_xyz_m">H2实际细床</option><option value="vertices_H0_local_xyz_m">H0原同坐标地形</option></select></label>
<label>垂直夸张<select id="exaggeration"><option value="1">1x真实</option><option value="10" selected>10x 明示</option><option value="30">30x 明示</option></select></label>
<p><input id="state" type="range" min="0" value="0" step="1" style="width:80%"><button id="play">播放/暂停</button></p>
<canvas id="view" width="1400" height="620"></canvas><pre id="status"></pre>
<p>首尾为显式局部工程接收面。节点控制区水位可阶梯；无水顶点不画蓝色平面穿山。所有状态来自保存结果，失败不展示被拒绝水位。</p>
<script>const DATA=__DATA__;
const mountain=document.getElementById('mountain'),scenario=document.getElementById('scenario'),surface=document.getElementById('surface'),exaggeration=document.getElementById('exaggeration'),state=document.getElementById('state'),canvas=document.getElementById('view'),context=canvas.getContext('2d'),status=document.getElementById('status');
let yaw=.8,pitch=.55,scale=9,drag=null,playing=false;
function current(){return DATA[mountain.value][scenario.value]}
const BOUNDS={};for(const mountainKey of Object.keys(DATA)){const arrays=DATA[mountainKey].partial_static.arrays,vertices=[...arrays.vertices_H0_local_xyz_m,...arrays.vertices_H2_local_xyz_m],lower=[Infinity,Infinity,Infinity],upper=[-Infinity,-Infinity,-Infinity];for(const vertex of vertices)for(let axis=0;axis<3;axis++){lower[axis]=Math.min(lower[axis],vertex[axis]);upper[axis]=Math.max(upper[axis],vertex[axis])}BOUNDS[mountainKey]={center:lower.map((value,axis)=>(value+upper[axis])/2),span:upper.map((value,axis)=>value-lower[axis])};}
function project(point){const angle=yaw,tilt=pitch,bounds=BOUNDS[mountain.value],center=bounds.center;let relativeX=point[0]-center[0],relativeZ=point[2]-center[2],horizontal=relativeX*Math.cos(angle)-relativeZ*Math.sin(angle),depth=relativeX*Math.sin(angle)+relativeZ*Math.cos(angle),vertical=(point[1]-center[1])*Number(exaggeration.value);return [700+scale*horizontal,310+scale*(depth*Math.sin(tilt)-vertical*Math.cos(tilt))]}
function draw(){const saved=current(),arrays=saved.arrays,index=Math.min(Number(state.value),saved.state_count-1);state.max=saved.state_count-1;state.value=index;context.clearRect(0,0,1400,620);const vertices=arrays[surface.value],bed=arrays.vertices_H2_local_xyz_m,triangles=arrays.triangles;context.strokeStyle='#9a9075';context.lineWidth=.45;for(const triangle of triangles){context.beginPath();triangle.forEach((vertex,position)=>{const point=project(vertices[vertex]);position?context.lineTo(...point):context.moveTo(...point)});context.closePath();context.stroke()}
const depth=arrays.water_depth_m[index];let wet=0;for(let vertex=0;vertex<bed.length;vertex++){if(depth[vertex]<=0)continue;wet++;const bottom=project(bed[vertex]),top=project([bed[vertex][0],bed[vertex][1]+depth[vertex],bed[vertex][2]]);context.strokeStyle='#238aca';context.lineWidth=1.2;context.beginPath();context.moveTo(...bottom);context.lineTo(...top);context.stroke();context.fillStyle='#1474b0';context.fillRect(top[0]-1.2,top[1]-1.2,2.4,2.4)}
const edges=index>0?arrays.qedges_m3_s[index-1]:[];status.textContent=`物理时间 ${arrays.time_s[index]} s | 状态 ${index}/${saved.state_count-1} | 湿支持 ${wet}\n离散水量 ${arrays.water_volume_m3[index].toFixed(9)} m³ | 求解水量 ${arrays.solver_volume_m3[index].toFixed(9)} m³ | 差 ${arrays.display_volume_difference_m3[index]} m³\n前一时段有符号边流 ${JSON.stringify(edges)} m³/s\n失败 ${JSON.stringify(saved.failure)} | 来源H0 ${saved.fine_H0_sha256}\n局部米制原点 ${JSON.stringify(arrays.origin_world_xyz_m)} | 垂直夸张 ${exaggeration.value}x\n水表示 ${saved.water_representation}`;window.reviewState={mountain:mountain.value,scenario:scenario.value,state:index,wet,volume:arrays.water_volume_m3[index]};}
for(const control of [mountain,scenario])control.addEventListener('change',()=>{state.value=0;draw()});for(const control of [surface,exaggeration])control.addEventListener('change',draw);state.addEventListener('input',draw);canvas.addEventListener('pointerdown',event=>{drag=[event.clientX,event.clientY];canvas.setPointerCapture(event.pointerId)});canvas.addEventListener('pointermove',event=>{if(!drag)return;yaw+=(event.clientX-drag[0])*.01;pitch=Math.max(-1.3,Math.min(1.3,pitch+(event.clientY-drag[1])*.01));drag=[event.clientX,event.clientY];draw()});canvas.addEventListener('pointerup',()=>drag=null);canvas.addEventListener('wheel',event=>{event.preventDefault();scale=Math.max(2,Math.min(40,scale*Math.exp(-event.deltaY*.001)));draw()},{passive:false});document.getElementById('play').onclick=()=>playing=!playing;setInterval(()=>{if(playing){state.value=(Number(state.value)+1)%current().state_count;draw()}},120);draw();
</script></html>'''.replace("__DATA__", encoded)
    with (output / "fine-3d-review.html").open("x", encoding="utf-8") as stream:
        stream.write(page)


def analyze_pressure_group_fine_binding(output, geometry_result, pool_case, forcing, *, group=1378):
    """Explicit fixed group integration diagnosis; no hidden raw-Q substitution."""
    arrays = geometry_result["arrays"]
    receiver = arrays["receiver"]
    labels = arrays["lake_id"].ravel()
    owner = arrays["outlet_owner"].ravel()
    pool_ids = pool_case["arrays"]["lake_ids"]
    if pool_case["proposal"]["group"] != group or pool_case["status"] != "complete_pool_group_feasible":
        raise ValueError("verified complete pressure group required")
    first = first_lake_ownership(geometry_result).ravel()
    candidates = []
    for start in np.flatnonzero((owner == group) & (labels == 0) & (receiver >= 0)):
        cells = [int(start)]
        direction = int(receiver[start] - start)
        while len(cells) < 4:
            target = int(receiver[cells[-1]])
            if target < 0 or target - cells[-1] != direction or labels[target] > 0:
                break
            cells.append(target)
        if len(cells) != 4:
            continue
        row, column = divmod(cells[0], arrays["H0_m"].shape[1])
        delta_row = cells[1] // arrays["H0_m"].shape[1] - row
        delta_column = cells[1] % arrays["H0_m"].shape[1] - column
        along = np.arange(91., dtype=np.float64)
        across = np.arange(-5., 6., dtype=np.float64)
        rows = row + along[:, None] / 30 * delta_row + across[None, :] / 30 * delta_column
        columns = column + along[:, None] / 30 * delta_column - across[None, :] / 30 * delta_row
        if (rows < 0).any() or (rows > arrays["H0_m"].shape[0] - 1).any() or (columns < 0).any() or (columns > arrays["H0_m"].shape[1] - 1).any():
            continue
        original = fine._sample(arrays["H0_m"], columns, rows)
        cut = np.broadcast_to(.25 * (.5 * (1 + np.cos(np.pi * across / 5)))[None, :], original.shape).copy()
        bed = original - cut
        nearest_rows = np.floor(rows + .5).astype(np.int64)
        nearest_columns = np.floor(columns + .5).astype(np.int64)
        if ((arrays["outlet_owner"][nearest_rows, nearest_columns] != group) | arrays["lake_mask"][nearest_rows, nearest_columns] | arrays["protected_mask"][nearest_rows, nearest_columns]).any():
            continue
        if (np.diff(bed[:, 5]) > 1e-9).any() or (bed < bed[:, 5:6] - 1e-9).any():
            continue
        subtree = np.zeros(receiver.size, dtype=bool)
        subtree[cells[0]] = True
        for cell in arrays["order"]:
            if receiver[cell] >= 0 and subtree[receiver[cell]]:
                subtree[cell] = True
        lake_ids = np.unique(labels[subtree])
        lake_ids = lake_ids[lake_ids > 0]
        if not lake_ids.size or not np.isin(lake_ids, pool_ids).all():
            continue
        candidates.append({"cells": cells, "subtree": subtree, "lake_ids": lake_ids,
                           "H0_m": original, "H2_m": bed, "cut_depth_m": cut,
                           "world_x_m": geometry_result["metadata"]["origin_m_xz"][0] + columns * 30,
                           "world_z_m": geometry_result["metadata"]["origin_m_xz"][1] + rows * 30})
    candidates.sort(key=lambda item: (-item["lake_ids"].size, -item["subtree"].sum(), item["cells"][0]))
    if not candidates:
        evidence = {"status": "no_source_complete_fine_binding_candidate", "group": group}
        json_new(output / "pressure1378-fine-binding-preflight.json", evidence)
        return evidence
    selected = candidates[0]
    subtree = selected["subtree"]
    first_dry = subtree & (first == 0)
    dry_counts = np.bincount(forcing["cell_owner"].ravel()[first_dry], minlength=forcing["area_m2"].size)
    dry_local = forcing["local_q_m3_s"] @ (dry_counts * 900 / forcing["area_m2"])
    incoming_lakes = []
    for lake in selected["lake_ids"]:
        downstream_lake = arrays["lake_downstream_id"][lake - 1]
        if downstream_lake <= 0 or downstream_lake not in selected["lake_ids"]:
            incoming_lakes.append(int(lake))
    indices = [int(np.flatnonzero(pool_ids == lake)[0]) for lake in incoming_lakes]
    pool_q = pool_case["arrays"]["outflow_volume_m3"][:, indices].sum(axis=1) / pool_case["dt_s"]
    inlet_q = pool_q + dry_local
    weights = np.ones(selected["H0_m"].shape)
    weights[0] *= .5
    weights[-1] *= .5
    weights[:, 0] *= .5
    weights[:, -1] *= .5
    chain = {"segments": 3, "arrays": {"H2_m": selected["H2_m"], "quadrature_area_m2": weights}}
    support = fine_storage.fine_storage_support(chain)
    capacities = np.array([fine_storage.volume(support["max_stage_m"][node],
        support["beds_m"][support["offsets"][node]:support["offsets"][node + 1]],
        support["weights_m2"][support["offsets"][node]:support["offsets"][node + 1]]) for node in range(4)])
    max_exit_q = fine_storage.CONDUCTANCE_M2_S * max(support["max_stage_m"][-1] - support["interface_sill_m"][-1], 0.)
    dt = pool_case["dt_s"]
    cumulative_input = np.cumsum(inlet_q * dt)
    generous_output_bound = np.arange(1, inlet_q.size + 1) * dt * max_exit_q
    over = cumulative_input - generous_output_bound > capacities.sum() + 1e-6
    first_exceed = int(np.flatnonzero(over)[0]) if over.any() else None
    saved = {key: value for key, value in selected.items() if isinstance(value, np.ndarray)}
    saved.update({"chain_cells": np.asarray(selected["cells"], dtype=np.int64),
                  "dry_local_allocation_counts": dry_counts, "dry_local_q_m3_s": dry_local,
                  "actual_verified_pool_release_q_m3_s": pool_q, "actual_inlet_q_m3_s": inlet_q,
                  "incoming_lake_ids": np.asarray(incoming_lakes, dtype=np.int64),
                  "quadrature_area_m2": weights, "pool_capacity_upper_m3": capacities,
                  "cumulative_input_volume_m3": cumulative_input,
                  "generous_cumulative_outflow_bound_m3": generous_output_bound,
                  "capacity_upper_bound_exceeded": over})
    save_npz_new(output / "pressure1378-fine-binding-preflight.npz", saved)
    evidence = {"status": "fixed_fine_conductance_capacity_preflight_refused" if first_exceed is not None else "capacity_bound_not_exceeded_not_solver_acceptance",
                "group": group, "candidate_count": len(candidates), "chain_cells": selected["cells"],
                "selection": "max_verified_upstream_lake_count_then_complete_subtree_area_then_flat_id",
                "length_m": 90., "width_m": 10., "spacing_m": 1.,
                "upstream_lake_ids": selected["lake_ids"].tolist(), "incoming_release_lake_ids": incoming_lakes,
                "complete_subtree_area_m2": int(subtree.sum()) * 900,
                "dry_local_area_m2": int(first_dry.sum()) * 900,
                "independent_cut_volume_m3": float((selected["cut_depth_m"] * weights).sum()),
                "effective_bank_capacity_upper_m3": float(capacities.sum()),
                "max_fixed_K_exit_Q_m3_s": float(max_exit_q), "actual_peak_inlet_Q_m3_s": float(inlet_q.max()),
                "first_provably_exceeding_interval": first_exceed,
                "time_at_end_of_first_exceed_s": (first_exceed + 1) * dt if first_exceed is not None else None,
                "bound_assumption": "dry_initial_all_banks_capacity_and_max_exit_for_every_interval_generous_bound_zero_upstream_escape",
                "boundary": "directional_actual_pool_plus_dry_local_inflow_to_local_strip_explicit_dry_downstream_tailwater",
                "scope": "source_complete_integration_preflight_not_prepared_coarse_bed_or_accepted_hydraulics",
                "source_binding": geometry_result["metadata"]["source_binding"],
                "pool_storage_sha256": geometry._hash(pool_case["arrays"]["storage_m3"]),
                "pool_release_sha256": geometry._hash(pool_case["arrays"]["outflow_volume_m3"]),
                "forcing_sha256": geometry._hash(forcing["local_q_m3_s"]),
                "no_raw_accumulated_Q_substitution": True}
    json_new(output / "pressure1378-fine-binding-preflight.json", evidence)
    return evidence


def main():
    started = datetime.now(timezone.utc)
    output = ROOT / "verification/mountain-depression-geometry" / ("run-" + started.strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    report = {"algorithm": geometry.ALGORITHM, "started_utc": started.isoformat(),
              "frozen_source_hashes_before": frozen_hashes(),
              "fixed_budget": geometry.GeometryBudget().__dict__,
              "scope": "有限计算窗口/截断边界实验，非完整水文规划域，无天然海口认证",
              "pool_limits": {"max_group_attempts": MAX_GROUP_ATTEMPTS, "max_steps": pools.MAX_STEPS,
                              "max_pools": pools.MAX_POOLS, "max_work": pools.MAX_WORK,
                              "weir_C": 1.7, "weir_width": "one full grid edge, 30m",
                              "max_head": "min(1m, half gap to other original shoreline)"},
              "samples": {}}
    frozen_report, frozen_review = pinned_reports()
    for name in SOURCE_NAMES:
        source = load_source(name)
        height = source["height_m"]
        source_binding = binding(name, source)
        boundary = geometry.window_boundary(height.shape)
        result = geometry.prepare_mountain_geometry(height, spacing_m=30., origin_m_xz=source["origin_m_xz"],
            source_binding=source_binding, boundary_mask=boundary, protected_mask=np.zeros(height.shape, dtype=bool))
        arrays = result["arrays"]
        path = output / f"{name}-geometry.npz"
        geometry.save_mountain_geometry(path, result, trusted_height=height, source_binding=source_binding)
        with patch.object(geometry, "prepare_mountain_geometry", side_effect=AssertionError("no prepare")), \
             patch.object(geometry, "_flood", side_effect=AssertionError("no flood")), \
             patch.object(geometry, "_route_lakes", side_effect=AssertionError("no routing")), \
             patch.object(geometry, "_ownership", side_effect=AssertionError("no assembly")), \
             patch.object(geometry, "_bed_candidates", side_effect=AssertionError("no bed preparation")):
            loaded = geometry.load_mountain_geometry(path, trusted_height=height, source_binding=source_binding)
        summary = geometry.validate_mountain_geometry(loaded, trusted_height=height, source_binding=source_binding)
        no_cut = geometry.certify_no_cut_groups(result)
        save_npz_new(output / f"{name}-no-cut-certificate.npz", {key: value for key, value in no_cut.items() if isinstance(value, np.ndarray)})
        d8_single = route(height, source["outlet_mask"], 30.)
        d8_open = route(height, boundary, 30.)
        accumulation = np.ones(height.size, dtype=np.float64) * 900
        for cell in d8_open.order[::-1]:
            if d8_open.receiver[cell] >= 0:
                accumulation[d8_open.receiver[cell]] += accumulation[cell]
        old = diagnostic(height, d8_single.routing_height, source["receiver"], source["flowline_mask"], 30.)
        single_area = np.ones(height.size, dtype=np.float64) * 900
        for cell in d8_single.order[::-1]:
            if d8_single.receiver[cell] >= 0:
                single_area[d8_single.receiver[cell]] += single_area[cell]
        old_same_threshold = diagnostic(height, d8_single.routing_height, d8_single.receiver, (single_area >= 1e6).reshape(height.shape), 30.)
        old["threshold_label"] = "legacy_source_mask_Q0.05_at_runoff1e-8_equivalent_5km2"
        old_same_threshold["threshold_area_m2"] = 1000000.
        open_d8 = diagnostic(height, d8_open.routing_height, d8_open.receiver, (accumulation >= 1e6).reshape(height.shape), 30.)
        open_d4 = diagnostic(height, arrays["escape_level_m"], arrays["receiver"], arrays["flowline_mask"], 30.)
        open_d8["threshold_area_m2"] = open_d4["threshold_area_m2"] = 1000000.
        save_npz_new(output / f"{name}-boundary-comparison.npz", {
            "H0_m": height, "legacy_receiver": source["receiver"], "legacy_flowline_mask": source["flowline_mask"],
            "D8_single_escape_m": d8_single.routing_height, "D8_open_escape_m": d8_open.routing_height,
            "D8_open_receiver": d8_open.receiver, "D8_open_order": d8_open.order,
            "D8_open_contributing_area_m2": accumulation.reshape(height.shape)})
        screen4 = geometry.screen_single_pool_lakes(result, min_cells=4)
        screen1 = geometry.screen_single_pool_lakes(result, min_cells=1)
        json_new(output / f"{name}-all-event-screen-4cells.json", screen4)
        json_new(output / f"{name}-all-event-screen-1cell.json", screen1)
        proposals = pools.screen_complete_pool_groups(result, screen1)
        json_new(output / f"{name}-complete-group-screen.json", {key: value for key, value in proposals.items() if key != "first_lake_id"})
        candidates = [item for item in proposals["groups"] if item["status"] == "static_complete_pool_candidate"][:MAX_GROUP_ATTEMPTS]
        pool_attempts = []
        selected = None
        forcing, forcing_binding, _, _ = accepted_case(name, "wet_storm", frozen_report, frozen_review)
        for proposal in candidates:
            trial = pools.route_complete_pool_group(result, proposal, local_q_m3_s=forcing["local_q_m3_s"],
                cell_owner=forcing["cell_owner"], hru_area_m2=forcing["area_m2"])
            pool_attempts.append({key: value for key, value in trial.items() if key != "arrays"})
            if "arrays" in trial:
                pools.save_pool_group(output / f"{name}-pool-attempt-group{proposal['group']}.npz", trial, result,
                    local_q_m3_s=forcing["local_q_m3_s"], cell_owner=forcing["cell_owner"], hru_area_m2=forcing["area_m2"])
            if selected is None and trial["status"] == "complete_pool_group_feasible":
                selected = proposal
        json_new(output / f"{name}-pool-attempts.json", pool_attempts)
        cases = {}
        case_summary = {}
        if selected is not None:
            for scenario in SCENARIOS:
                inputs, forcing_binding, _, _ = accepted_case(name, scenario, frozen_report, frozen_review)
                case = pools.route_complete_pool_group(result, selected, local_q_m3_s=inputs["local_q_m3_s"],
                    cell_owner=inputs["cell_owner"], hru_area_m2=inputs["area_m2"])
                case_path = output / f"{name}-{scenario}-complete-pool-group.npz"
                pools.save_pool_group(case_path, case, result, local_q_m3_s=inputs["local_q_m3_s"],
                    cell_owner=inputs["cell_owner"], hru_area_m2=inputs["area_m2"])
                with patch.object(pools, "route_complete_pool_group", side_effect=AssertionError("no advance")), \
                     patch.object(pools, "screen_complete_pool_groups", side_effect=AssertionError("no screen")), \
                     patch.object(pools, "first_lake_ownership", side_effect=AssertionError("no assembly")):
                    cold = pools.load_pool_group(case_path, result, local_q_m3_s=inputs["local_q_m3_s"],
                        cell_owner=inputs["cell_owner"], hru_area_m2=inputs["area_m2"])
                budget = pools.validate_complete_pool_group(cold, result, local_q_m3_s=inputs["local_q_m3_s"],
                    cell_owner=inputs["cell_owner"], hru_area_m2=inputs["area_m2"])
                cases[scenario] = case
                case_summary[scenario] = {"status": case["status"], "group": selected["group"], "area_m2": selected["area_m2"],
                                          "lakes": selected["lake_ids"], "budget": budget, "forcing_binding": forcing_binding}
        fine_trial = fine.select_continuous_fine_geometry(result)
        chain = fine_trial["accepted"]
        fine_summary = {key: value for key, value in fine_trial.items() if key != "accepted"}
        if chain is not None:
            fine_summary["source_geometry_validation"] = fine.validate_fine_chain(chain, result)
            save_npz_new(output / f"{name}-continuous-fine-chain.npz", chain["arrays"])
            fine_summary["accepted"] = {key: value for key, value in chain.items() if key != "arrays"}
            support = fine_storage.fine_storage_support(chain)
            fine_summary["minimum_bank_margin_m"] = float(support["side_margin_m"].min())
            mapped = fine_storage.map_chain_upstream_runoff(result, chain, local_q_m3_s=forcing["local_q_m3_s"],
                cell_owner=forcing["cell_owner"], hru_area_m2=forcing["area_m2"])
            save_npz_new(output / f"{name}-fine-upstream-map.npz", {key: value for key, value in mapped.items() if isinstance(value, np.ndarray)})
            fine_summary["rainfall_binding"] = array_json({key: value for key, value in mapped.items() if key not in ("subtree_mask", "allocation_counts", "rainfall_only_instantaneous_local_q_m3_s")})
            fine_summary["dynamic_scenarios"], fine_cases = fine_dynamic_cases(output, name, chain, result)
        json_new(output / f"{name}-fine-evidence.json", fine_summary)
        maps(output, name, source, result, d8_single, d8_open, no_cut)
        fine_panels(output, name, chain)
        if cases:
            hydro_panels(output, name, cases)
        changed_d8 = source["receiver"] != d8_open.receiver
        changed_d4 = source["receiver"] != arrays["receiver"]
        sample = {"source_binding": source_binding, "shape": list(height.shape), "origin_m_xz": source["origin_m_xz"],
                  "geometry": summary, "no_cut": {key: value for key, value in no_cut.items() if not isinstance(value, np.ndarray)},
                  "D8_single_artificial_outlet": old, "D8_all_external_open": open_d8, "D4_all_external_open": open_d4,
                  "D8_single_same_1km2_threshold": old_same_threshold,
                  "receiver_changed_old_to_D8open_cells": int(changed_d8.sum()),
                  "receiver_changed_old_to_D4open_cells": int(changed_d4.sum()),
                  "construction_unaccepted_cells": int((~arrays["accepted_mask"]).sum()),
                  "construction_accepted_outlets": np.flatnonzero(arrays["accepted_outlets"]).tolist(),
                  "screen4_status_counts": dict(Counter(item["status"] for item in screen4["decisions"])),
                  "screen1_status_counts": dict(Counter(item["status"] for item in screen1["decisions"])),
                  "pool_cases": case_summary, "pool_attempt_count": len(pool_attempts), "fine": fine_summary,
                  "static_cold_load_passed": True}
        report["samples"][name] = array_json(sample)
        print(name, json.dumps({"geometry": summary, "pool_cases": case_summary, "fine": fine_summary}, ensure_ascii=False), flush=True)
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["frozen_source_hashes_after"] = frozen_hashes()
    if report["frozen_source_hashes_before"] != report["frozen_source_hashes_after"]:
        raise ValueError("frozen source modified during verifier")
    files = [ROOT / "terrain_pipeline" / name for name in ("mountain_depression_geometry.py", "mountain_fine_geometry.py",
        "mountain_fine_storage.py", "mountain_pool_network.py", "mountain_lake_experiment.py", "mountain_fine_mesh.py")]
    files += list((ROOT / "tests").glob("test_mountain_*geometry.py")) + [ROOT / "tests/test_mountain_pool_network.py", ROOT / "tests/test_mountain_fine_storage.py", ROOT / "tests/test_mountain_fine_mesh.py", Path(__file__).resolve(), ROOT / "docs/mountain-depression-geometry.md"]
    report["source_code_sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    json_new(output / "report.json", report)
    sections = []
    for name, sample in report["samples"].items():
        label = "普通山地" if name == "normal_mountain" else "压力山地"
        sections.append(f'<section><h2>{label}</h2><p>完整487²，面积213.4521km²。施工未接受{sample["construction_unaccepted_cells"]}格；'
            f'原床no-cut静态合法面积{sample["no_cut"]["valid_area_m2"]/1e6:.4f}km²，非动态全域认证。</p>'
            f'<img src="{name}-full-window.png" alt="全窗口H0边界条件湖盆施工与切深">'
            f'<img src="{name}-routes.png" alt="原新河线路线"><img src="{name}-fine-sections.png" alt="独立连续fine床面断面">'
            f'<img src="{name}-pool-hydrographs.png" alt="有限完整贡献组湖泊过程线">'
            f'<img src="{name}-fine-dynamics.png" alt="人工局部边界干湿静水倒流与失败">'
            '<details><summary>固定身份、预算与失败证据</summary><pre>' + html.escape(json.dumps(sample, ensure_ascii=False, indent=2)) + '</pre></details></section>')
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>山地洼地与合法几何独立图报告</title>' \
        '<style>body{font:16px sans-serif;max-width:1400px;margin:auto;padding:24px;background:#f5f3ed}img{width:100%;background:white}pre{white-space:pre-wrap}section{margin:36px 0}</style>' \
        '<h1>任务39：保湖、截断边界与有限床几何</h1><p><strong>实验，不是天然流域/海口认证。容量不是实际存水。</strong></p>' \
        '<p>旧D8单人工出口→D8全部边界开放→新D4全部边界开放分别报告。变化包括边界条件与邻接规则，不是同边界算法优越性。深度图各用独立色标范围，必须读取m数值，不能直接按颜色深浅比较比例。</p>' \
        '<p>湖组件是满溢平衡容量；多局部极小盆不当干初始单湖。30m单格湖仅离散蓄水单元。动态候选逐全部高程事件验证单池，真实堰C=1.7、宽30m，超岸或下游淹没spill拒绝。</p>' \
        '<p>连续fine为独立90m×10m条带，1m采样，共享节点。不是全forest，不与coarse重复加体积。边界为显式局部接收几何seam，不是自然出口。上游包含湖时直接雨量注入拒绝。</p>' \
        ''.join(sections) + '</html>'
    with (output / "review.html").open("x", encoding="utf-8") as stream:
        stream.write(page)
    write_mesh_review(output)
    print("OUTPUT", output, flush=True)


def verify_manning():
    from terrain_pipeline.mountain_source_adapter import file_sha256, load_legacy_source, identity
    from terrain_pipeline.mountain_lake_coupling import build_group_topology, load_coupling
    from terrain_pipeline.mountain_manning_geometry import prepare_tributary_geometry
    from terrain_pipeline.mountain_manning_binding import bind_saved_releases
    from terrain_pipeline import mountain_manning_storage as manning

    output = ROOT / "verification/mountain-manning-tributary" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    shared = ROOT / "terrain_pipeline/mountain_depression_geometry.py"
    if file_sha256(shared) != "6be2f275de2907183a214903f35fc7742d34a7f26141c1757b036cd42e477694":
        raise ValueError("shared geometry freeze mismatch")
    delivery = list((ROOT / "terrain_pipeline").glob("mountain_*.py"))
    delivery += list((ROOT / "tests").glob("test_mountain_*.py"))
    delivery += [Path(__file__).resolve(), ROOT / "docs/mountain-depression-geometry.md"]
    before = {str(path.relative_to(ROOT)): file_sha256(path) for path in delivery}
    frozen_before = frozen_hashes()
    json_new(output / "before.json", {"delivery": before, "frozen": frozen_before})
    base = ROOT / "verification/mountain-lake-coupling/frozen-20261001-A-v3"
    weather = ROOT / "verification/mountain-storm-forcing/run-20261001T071520828638Z"
    source = load_legacy_source("pressure_mountain", boundary_policy="all_edges_open")
    geometry_path = base / "pressure_mountain-geometry.npz"
    original_report = json.loads((base / "report.json").read_text(encoding="utf-8"))
    expected_geometry = original_report["samples"]["pressure_mountain"]["geometry_archive_sha256"]
    if file_sha256(geometry_path) != expected_geometry:
        raise ValueError("A frozen geometry archive mismatch")
    coarse = geometry.load_mountain_geometry(geometry_path, trusted_height=source["arrays"]["height_m"],
        source_binding={"source_identity": source["identity_sha256"]})
    topology, selection, _ = build_group_topology(source, coarse, 1378)
    record = prepare_tributary_geometry(coarse)
    save_npz_new(output / "tributary-geometry.npz", record["arrays"])
    json_new(output / "tributary-geometry.json", record["metadata"])
    report = {"schema": "mountain-manning-tributary-report-v1", "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_identity": source["identity_sha256"], "source_geometry_archive_sha256": expected_geometry,
        "study_identity": identity(record["arrays"], record["metadata"]), "budget": manning.preflight(5760, 15.),
        "roughness_s_m_third": .035, "cases": {}, "limitations": [
        "工程upwind断面conveyance、crest截断水头、BE四控制体扩散近似，无动量，非Saint-Venant",
        "1m双线性为30m源的采样，不增加地形分辨率；独立112.5m³切床不叠加coarse预算",
        "指定末端minbed水位边界，不是自然自由跌落；离线单向回放，未反馈A网络",
        "仅前24h统一时窗，不能声称整个72h或14天退水；旧湿暴雨和移动雨不按能力挑选"]}
    weather_report = json.loads((weather / "report.json").read_text(encoding="utf-8"))
    cases = {
        "old_wet_storm": base / "pressure_mountain_cascade_positive-wet_storm_surface-coupling.npz",
        "eastward": weather / "pressure_mountain-eastward-coupling.npz",
        "westward": weather / "pressure_mountain-westward-coupling.npz",
        "no_rain": weather / "pressure_mountain-no_rain-coupling.npz"}
    plotted = {}
    for name, path in cases.items():
        digest = file_sha256(path)
        if name == "no_rain":
            expected = weather_report["no_rain_baseline"]["archive_sha256"]
        elif name in ("eastward", "westward"):
            expected = weather_report["cases"][name]["coupling_sha256"]
        else:
            expected = original_report["samples"]["pressure_mountain"]["cascade_positive_group_dynamics"]["scenarios"]["wet_storm_surface"]["archive_sha256"]
        if digest != expected:
            raise ValueError("A forcing archive hash mismatch: " + name)
        coupled = load_coupling(path, expected_sha256=expected, source=source, topology=topology,
            geometry=coarse, selection=selection)
        report["cases"][name] = {"A_archive": str(path.relative_to(ROOT)), "A_archive_sha256": expected, "steps": {}}
        for dt in (30., 15.):
            bound = bind_saved_releases(coupled, source, topology, coarse, selection, record, dt_s=dt)
            forcing = bound["forcing"]
            json_new(output / f"{name}-dt{int(dt)}-binding.json", bound["metadata"])
            save_npz_new(output / f"{name}-dt{int(dt)}-binding.npz", bound["arrays"])
            limit = manning.capacity_bound(record, **{key: forcing[key] for key in
                ("inlet_q_m3_s", "lateral_q_m3_s", "tailwater_stage_m", "dt_s")})
            save_npz_new(output / f"{name}-dt{int(dt)}-capacity.npz", {key: value for key, value in limit.items() if isinstance(value, np.ndarray)})
            saved = manning.prepare_manning_storage(record, coarse, **forcing)
            target = output / f"{name}-dt{int(dt)}-storage.npz"
            manning.save_manning_storage(target, saved, record, coarse)
            with patch.object(manning, "prepare_manning_storage", side_effect=AssertionError("no advance")), \
                 patch.object(manning, "least_squares", side_effect=AssertionError("no solve")):
                cold = manning.load_manning_storage(target, record, coarse, expected_sha256=file_sha256(target), trusted_forcing=forcing)
            statistics = manning.validate_manning_storage(cold, record, coarse)
            detail = {"status": saved["metadata"]["status"], "failure": saved["metadata"]["failure"],
                "committed_steps": saved["metadata"]["committed_steps"], "requested_steps": saved["metadata"]["requested_steps"],
                "residual_evaluations": saved["metadata"]["residual_evaluations"], "statistics": statistics,
                "input_m3": float((forcing["inlet_q_m3_s"] + forcing["lateral_q_m3_s"].sum(axis=1)).sum() * dt),
                "inlet_peak_m3_s": float(forcing["inlet_q_m3_s"].max()),
                "capacity_m3": float(limit["capacity_m3"].sum()), "outlet_upper_q_m3_s": float(limit["max_outflow_q_m3_s"].max()),
                "necessary_capacity_first_exceed_step": limit["first_exceed_step"], "static_cold_load": True}
            report["cases"][name]["steps"][str(int(dt))] = detail
            json_new(output / f"{name}-dt{int(dt)}-result.json", detail)
            print(name, dt, json.dumps(detail, ensure_ascii=False), flush=True)
            plotted[(name, dt)] = saved
    figure, axes = plt.subplots(3, 1, figsize=(13, 11))
    for (name, dt), saved in plotted.items():
        state = saved["arrays"]
        count = saved["metadata"]["committed_steps"]
        axes[0].plot(np.arange(state["inlet_q_m3_s"].size) * dt / 3600, state["inlet_q_m3_s"], label=f"{name}/{dt:g}s")
        axes[1].plot(np.arange(1, count + 1) * dt / 3600, state["qedges_m3_s"][:, -1], label=f"{name}/{dt:g}s")
        axes[2].plot(np.arange(count + 1) * dt / 3600, state["storage_m3"].sum(axis=1), label=f"{name}/{dt:g}s")
    for axis, label in zip(axes, ("Saved A inlet (m3/s)", "Committed signed outlet (m3/s)", "Fine storage (m3)")):
        axis.set_ylabel(label)
        axis.set_xlabel("Time (h), same 24h physical input")
        axis.legend(fontsize=8)
        axis.grid(alpha=.3)
    figure.tight_layout()
    figure.savefig(output / "hydrographs.png", dpi=150)
    plt.close(figure)
    report["frozen_unchanged"] = frozen_hashes() == frozen_before
    report["delivery_unchanged"] = {str(path.relative_to(ROOT)): file_sha256(path) for path in delivery} == before
    if not report["frozen_unchanged"] or not report["delivery_unchanged"]:
        raise ValueError("source changed during Manning verifier")
    report["source_code_sha256"] = before
    report["artifacts_sha256"] = {path.name: file_sha256(path) for path in output.iterdir() if path.is_file()}
    json_new(output / "report.json", report)
    page = '<!doctype html><meta charset="utf-8"><title>Manning支流独立审查</title><h1>同源支流工程扩散试验</h1><p>' + '</p><p>'.join(report["limitations"]) + '</p><img style="max-width:100%" src="hydrographs.png"><pre>' + html.escape(json.dumps(report["cases"], ensure_ascii=False, indent=2)) + '</pre>'
    (output / "review.html").write_text(page, encoding="utf-8")
    print("OUTPUT", output, flush=True)


def freeze_manning(run_path):
    from terrain_pipeline.mountain_source_adapter import file_sha256, load_legacy_source, identity
    from terrain_pipeline.mountain_lake_coupling import build_group_topology, load_coupling
    from terrain_pipeline import mountain_manning_geometry as study
    from terrain_pipeline import mountain_manning_storage as manning
    from terrain_pipeline import mountain_manning_binding as binding_module
    from terrain_pipeline.mountain_manning_mesh import export_manning_mesh

    run = Path(run_path).resolve()
    old = json.loads((run / "report.json").read_text(encoding="utf-8"))
    for name, digest in old["artifacts_sha256"].items():
        if file_sha256(run / name) != digest:
            raise ValueError("old run artifact modified: " + name)
    output = ROOT / "verification/mountain-manning-tributary" / ("frozen-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    delivery = list((ROOT / "terrain_pipeline").glob("mountain_*.py")) + list((ROOT / "tests").glob("test_mountain_*.py"))
    delivery += [Path(__file__).resolve(), ROOT / "docs/mountain-depression-geometry.md"]
    before = {str(path.relative_to(ROOT)): file_sha256(path) for path in delivery}
    frozen_before = frozen_hashes()
    source = load_legacy_source("pressure_mountain", boundary_policy="all_edges_open")
    base = ROOT / "verification/mountain-lake-coupling/frozen-20261001-A-v3"
    coarse = geometry.load_mountain_geometry(base / "pressure_mountain-geometry.npz",
        trusted_height=source["arrays"]["height_m"], source_binding={"source_identity": source["identity_sha256"]})
    topology, selection, _ = build_group_topology(source, coarse, 1378)
    with np.load(run / "tributary-geometry.npz", allow_pickle=False) as archive:
        record = {"arrays": {key: archive[key] for key in archive.files},
                  "metadata": json.loads((run / "tributary-geometry.json").read_text(encoding="utf-8"))}
    study.validate_tributary_geometry(record, coarse)
    if identity(record["arrays"], record["metadata"]) != old["study_identity"]:
        raise ValueError("stored study identity differs")
    save_npz_new(output / "tributary-geometry.npz", record["arrays"])
    json_new(output / "tributary-geometry.json", record["metadata"])
    final = {"schema": "mountain-manning-static-freeze-v1", "numerical_run": str(run.relative_to(ROOT)),
        "numerical_report_sha256": file_sha256(run / "report.json"), "numerical_source_hashes": old["source_code_sha256"],
        "current_static_source_hashes": before, "study_identity": old["study_identity"], "limitations": old["limitations"],
        "static_only_no_prepare_bind_or_advance": True, "cases": {}, "mesh": {},
        "accepted_scope": {"cells": 716, "area_m2": 644400., "group_cells": 749,
            "partition_counts": [425, 1, 1, 289], "inlet_node": 293, "last_node": 296,
            "full_group_not_claimed": True}, "modified_paths": [
            "terrain_pipeline/mountain_manning_geometry.py", "terrain_pipeline/mountain_manning_storage.py",
            "terrain_pipeline/mountain_manning_binding.py", "terrain_pipeline/mountain_manning_mesh.py",
            "tests/test_mountain_manning_storage.py", "tools/verify_mountain_depression_geometry.py",
            "docs/mountain-depression-geometry.md"]}
    browser_data = {}
    for name, old_case in old["cases"].items():
        coupled = load_coupling(ROOT / old_case["A_archive"], expected_sha256=old_case["A_archive_sha256"],
            source=source, topology=topology, geometry=coarse, selection=selection)
        final["cases"][name] = {"A_archive": old_case["A_archive"], "A_archive_sha256": old_case["A_archive_sha256"], "steps": {}}
        series = {}
        for dt in (30., 15.):
            path = run / f"{name}-dt{int(dt)}-storage.npz"
            with np.load(path, allow_pickle=False) as archive:
                forcing = {key: archive[key] for key in ("initial_stage_m", "inlet_q_m3_s", "lateral_q_m3_s", "tailwater_stage_m")}
            forcing["dt_s"] = dt
            with np.load(run / f"{name}-dt{int(dt)}-binding.npz", allow_pickle=False) as archive:
                bound = {"arrays": {key: archive[key] for key in archive.files}, "forcing": forcing,
                    "metadata": json.loads((run / f"{name}-dt{int(dt)}-binding.json").read_text(encoding="utf-8"))}
            with patch.object(binding_module, "bind_saved_releases", side_effect=AssertionError("no rebind")), \
                 patch.object(study, "prepare_tributary_geometry", side_effect=AssertionError("no geometry prepare")), \
                 patch.object(manning, "prepare_manning_storage", side_effect=AssertionError("no advance")), \
                 patch.object(manning, "least_squares", side_effect=AssertionError("no solve")):
                provenance = binding_module.validate_saved_binding(bound, coupled, record)
                saved = manning.load_manning_storage(path, record, coarse, expected_sha256=old["artifacts_sha256"][path.name], trusted_forcing=forcing)
                stats = manning.validate_manning_storage(saved, record, coarse)
                limit = manning.capacity_bound(record, **{key: forcing[key] for key in ("inlet_q_m3_s", "lateral_q_m3_s", "tailwater_stage_m", "dt_s")})
                mesh = export_manning_mesh(record, saved, coarse)
            target = output / path.name
            from terrain_pipeline.mountain_source_adapter import publish_bytes
            publish_bytes(target, path.read_bytes())
            save_npz_new(output / f"{name}-dt{int(dt)}-binding.npz", bound["arrays"])
            json_new(output / f"{name}-dt{int(dt)}-binding.json", bound["metadata"])
            save_npz_new(output / f"{name}-dt{int(dt)}-capacity.npz", {key: value for key, value in limit.items() if isinstance(value, np.ndarray)})
            committed = saved["metadata"]["committed_steps"]
            input_rates = forcing["inlet_q_m3_s"] + forcing["lateral_q_m3_s"].sum(axis=1)
            submitted = float(input_rates[:committed].sum() * dt)
            outlet = float(saved["arrays"]["qedges_m3_s"][:, -1].sum() * dt)
            initial_storage = float(saved["arrays"]["storage_m3"][0].sum())
            last_storage = float(saved["arrays"]["storage_m3"][-1].sum())
            detail = {"status": saved["metadata"]["status"], "failure": saved["metadata"]["failure"],
                "requested_duration_s": forcing["inlet_q_m3_s"].size * dt, "committed_duration_s": committed * dt,
                "requested_input_m3": float(input_rates.sum() * dt), "committed_input_m3": submitted,
                "uncommitted_input_m3": float(input_rates[committed:].sum() * dt),
                "committed_external_outflow_m3": outlet, "initial_storage_m3": initial_storage, "final_storage_m3": last_storage,
                "cumulative_balance_error_m3": last_storage - initial_storage - submitted + outlet,
                "stats": stats, "binding_static_validation": provenance,
                "necessary_any_interval_first_exceed_end_s": None if limit["any_interval_first_exceed_step"] is None else (limit["any_interval_first_exceed_step"] + 1) * dt,
                "max_any_interval_drawup_m3": float(limit["any_interval_drawup_m3"].max()),
                "total_capacity_m3": float(limit["capacity_m3"].sum()), "bound_scope": limit["bound_scope"],
                "residual_evaluations": saved["metadata"]["residual_evaluations"]}
            final["cases"][name]["steps"][str(int(dt))] = detail
            json_new(output / f"{name}-dt{int(dt)}-result.json", detail)
            save_npz_new(output / f"{name}-dt{int(dt)}-mesh.npz", mesh["arrays"])
            json_new(output / f"{name}-dt{int(dt)}-mesh.json", array_json(mesh))
            final["mesh"][f"{name}/{dt:g}"] = mesh["metadata"]
            series[dt] = saved
            if dt == 30.:
                browser_data[name] = array_json(mesh)
        count = min(series[30.]["metadata"]["committed_steps"], series[15.]["metadata"]["committed_steps"] // 2)
        coarse_q = series[30.]["arrays"]["qedges_m3_s"][:count, -1]
        fine_q = series[15.]["arrays"]["qedges_m3_s"][:count * 2, -1].reshape(-1, 2).mean(axis=1)
        final["cases"][name]["dt_comparison"] = {"same_input_duration_s": 86400., "common_committed_duration_s": count * 30.,
            "relative_outlet_L1": float(np.abs(coarse_q - fine_q).sum() / max(np.abs(fine_q).sum(), 1e-30)),
            "max_common_node_storage_difference_m3": float(np.abs(series[30.]["arrays"]["storage_m3"][:count + 1] - series[15.]["arrays"]["storage_m3"][:count * 2 + 1:2]).max())}
    write_manning_mesh_review(output, browser_data)
    from terrain_pipeline.mountain_source_adapter import publish_bytes
    publish_bytes(output / "hydrographs.png", (run / "hydrographs.png").read_bytes())
    final["frozen_unchanged"] = frozen_before == frozen_hashes()
    final["delivery_unchanged"] = before == {str(path.relative_to(ROOT)): file_sha256(path) for path in delivery}
    if not final["frozen_unchanged"] or not final["delivery_unchanged"]:
        raise ValueError("source changed during static freeze")
    final["artifacts_sha256"] = {path.name: file_sha256(path) for path in output.iterdir() if path.is_file()}
    json_new(output / "report.json", final)
    print("STATIC_OUTPUT", output, flush=True)


def write_manning_mesh_review(output, datasets):
    encoded = json.dumps(datasets, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Manning同源支流三维审查</title>
<style>body{font:16px sans-serif;background:#eeeade;margin:20px}canvas{width:100%;max-width:1400px;height:620px;background:#fafaf5;border:1px solid #888}label{margin:10px}pre{white-space:pre-wrap}</style>
<h1>同源支流90m床面与保存真实水位</h1><p>工程Manning扩散近似：upwind断面＋crest截断水头＋BE四控制体，无动量；n=0.035，不是Saint-Venant或天然自由跌落。1m仅采样30m原TD。</p>
<p>A首节点下游释放离线接入，额外fine停留；尾水指定为末支撑最低床。716格完整子树644400m²，非全1378组。水为V(h)加权湿点，不插值假连续水面。</p>
<p>滑块最多98个原保存状态（含初态、末态、储量峰），不是全时间步滑块；未插值或重新推进。初态无前一时段，初态占位数组不是计算流量。</p>
<label>场景<select id="scenario"><option value="eastward">东向移动雨</option><option value="westward">西向移动雨</option><option value="no_rain">无雨（原土库仍退水）</option><option value="old_wet_storm">旧湿暴雨超岸，仅提交前缀</option></select></label>
<label>床面<select id="surface"><option value="vertices_H2_local_xyz_m">H2实际床</option><option value="vertices_H0_local_xyz_m">H0原床</option></select></label>
<label>夸张<select id="exaggeration"><option value="1">1x真实</option><option value="10" selected>10x明示</option></select></label>
<p><input id="state" type="range" min="0" value="0" style="width:70%"><button id="peak">储量峰态</button><button id="last">末态</button><button id="play">播放/暂停</button></p>
<canvas id="view" width="1400" height="620"></canvas><pre id="status"></pre><p><a href="report.json">固定身份、失败与requested/committed分账</a></p><img src="hydrographs.png" style="max-width:100%">
<script>const DATA=__DATA__;
const scenario=document.getElementById('scenario'),surface=document.getElementById('surface'),exaggeration=document.getElementById('exaggeration'),state=document.getElementById('state'),canvas=document.getElementById('view'),ctx=canvas.getContext('2d'),status=document.getElementById('status');
const base=DATA.eastward.arrays,vertices=[...base.vertices_H0_local_xyz_m,...base.vertices_H2_local_xyz_m],lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(const vertex of vertices)for(let axis=0;axis<3;axis++){lo[axis]=Math.min(lo[axis],vertex[axis]);hi[axis]=Math.max(hi[axis],vertex[axis])}const center=lo.map((v,i)=>(v+hi[i])/2);
let yaw=.8,pitch=.55,zoom=1,drag=null,playing=false;
function raw(point){const x=point[0]-center[0],z=point[2]-center[2],y=(point[1]-center[1])*Number(exaggeration.value);return [x*Math.cos(yaw)-z*Math.sin(yaw),(x*Math.sin(yaw)+z*Math.cos(yaw))*Math.sin(pitch)-y*Math.cos(pitch)]}
function draw(){const saved=DATA[scenario.value],a=saved.arrays;state.max=saved.metadata.state_count-1;const index=Math.min(Number(state.value),Number(state.max));state.value=index;const bounds=vertices.map(raw),xmin=Math.min(...bounds.map(v=>v[0])),xmax=Math.max(...bounds.map(v=>v[0])),ymin=Math.min(...bounds.map(v=>v[1])),ymax=Math.max(...bounds.map(v=>v[1]));const scale=zoom*Math.min(1200/(xmax-xmin),480/(ymax-ymin));function project(v){const p=raw(v);return [700+scale*p[0],310+scale*p[1]]}ctx.clearRect(0,0,1400,620);ctx.strokeStyle='#a7987d';ctx.lineWidth=.5;for(const tri of a.triangles){ctx.beginPath();tri.forEach((id,i)=>{const p=project(a[surface.value][id]);i?ctx.lineTo(...p):ctx.moveTo(...p)});ctx.closePath();ctx.stroke()}let wet=0;for(let id=0;id<a.vertices_H2_local_xyz_m.length;id++){const depth=a.water_depth_m[index][id];if(depth<=0)continue;wet++;const b=a.vertices_H2_local_xyz_m[id],p=project(b),q=project([b[0],b[1]+depth,b[2]]);ctx.strokeStyle='#168aca';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.stroke();ctx.fillStyle='#1474b0';ctx.fillRect(q[0]-1.2,q[1]-1.2,2.4,2.4)}status.textContent=`时间 ${a.time_s[index]}s | 原保存状态 ${a.saved_state_indices[index]} | 湿点 ${wet}\n水量 ${a.water_volume_m3[index]}m³ | V(h)差 ${a.display_volume_difference_m3[index]}m³\n前段有符号边流 ${JSON.stringify(a.qedges_m3_s[index])}m³/s\n失败 ${JSON.stringify(saved.metadata.failure)} | 垂直夸张 ${exaggeration.value}x\n几何身份 ${saved.metadata.geometry_identity}`;window.reviewState={scenario:scenario.value,index,wet,time:a.time_s[index],volume:a.water_volume_m3[index],yaw,pitch,zoom};}
const drawSavedState=draw;draw=function(){drawSavedState();if(DATA[scenario.value].arrays.saved_state_indices[Number(state.value)]===0)status.textContent=status.textContent.split(String.fromCharCode(10)).map(line=>line.startsWith('前段有符号边流')?'前段有符号边流：无前一时段（null）':line).join(String.fromCharCode(10));};
scenario.onchange=()=>{state.value=0;draw()};surface.onchange=draw;exaggeration.onchange=draw;state.oninput=draw;document.getElementById('peak').onclick=()=>{const a=DATA[scenario.value].arrays;state.value=a.water_volume_m3.indexOf(Math.max(...a.water_volume_m3));draw()};document.getElementById('last').onclick=()=>{state.value=DATA[scenario.value].metadata.state_count-1;draw()};document.getElementById('play').onclick=()=>playing=!playing;setInterval(()=>{if(playing){state.value=(Number(state.value)+1)%DATA[scenario.value].metadata.state_count;draw()}},150);canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.01;pitch=Math.max(-1.3,Math.min(1.3,pitch+(e.clientY-drag[1])*.01));drag=[e.clientX,e.clientY];draw()};canvas.onpointerup=()=>drag=null;canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.3,Math.min(3,zoom*Math.exp(-e.deltaY*.001)));draw()},{passive:false});draw();
</script></html>'''.replace("__DATA__", encoded)
    with (output / "manning-3d-review.html").open("x", encoding="utf-8") as stream:
        stream.write(page)


def verify_manning_100m():
    from terrain_pipeline.mountain_source_adapter import file_sha256, load_legacy_source, publish_bytes, identity
    from terrain_pipeline.mountain_lake_coupling import build_group_topology, load_coupling
    from terrain_pipeline.mountain_manning_geometry import validate_tributary_geometry
    from terrain_pipeline.mountain_manning_binding import bind_saved_releases, validate_saved_binding
    from terrain_pipeline import mountain_manning_storage as manning
    from terrain_pipeline.mountain_manning_mesh import export_manning_mesh

    fixed = ROOT / "verification/mountain-manning-tributary/frozen-20261001T075127883716Z"
    parent = json.loads((fixed / "final-handoff-manifest.json").read_text(encoding="utf-8"))
    parent_source_hashes = {name.replace("\\", "/"): digest for name, digest in parent["source_hashes"].items()}
    for name, digest in parent["artifacts_sha256"].items():
        if file_sha256(fixed / name) != digest:
            raise ValueError("canonical Manning artifact changed: " + name)
    for name, digest in parent_source_hashes.items():
        if name != "tools/verify_mountain_depression_geometry.py" and file_sha256(ROOT / name) != digest:
            raise ValueError("canonical Manning non-verifier source changed: " + name)
    source = load_legacy_source("pressure_mountain", boundary_policy="all_edges_open")
    base = ROOT / "verification/mountain-lake-coupling/frozen-20261001-A-v3"
    coarse = geometry.load_mountain_geometry(base / "pressure_mountain-geometry.npz",
        trusted_height=source["arrays"]["height_m"], source_binding={"source_identity": source["identity_sha256"]})
    topology, selection, _ = build_group_topology(source, coarse, 1378)
    with np.load(fixed / "tributary-geometry.npz", allow_pickle=False) as archive:
        record = {"arrays": {key: archive[key] for key in archive.files},
            "metadata": json.loads((fixed / "tributary-geometry.json").read_text(encoding="utf-8"))}
    validate_tributary_geometry(record, coarse)
    weather_dir = ROOT / "verification/mountain-storm-100m/run-20261001T074007800900Z"
    weather_report = json.loads((weather_dir / "report.json").read_text(encoding="utf-8"))
    old_weather = ROOT / "verification/mountain-storm-forcing/run-20261001T071520828638Z"
    old_weather_report = json.loads((old_weather / "report.json").read_text(encoding="utf-8"))
    if weather_report["cases"]["eastward"]["parameters"] != old_weather_report["cases"]["eastward"]["parameters"]:
        raise ValueError("100m must not retune weather")
    if (weather_report["source_identity"] != source["identity_sha256"] or weather_report["geometry_identity"] != topology["geometry_identity"]
            or weather_report["selection_identity"] != selection["identity_sha256"] or weather_report["HRU_bin_m"] != 100.):
        raise ValueError("100m same source/domain/geometry required")
    output = ROOT / "verification/mountain-manning-100m" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    files = list((ROOT / "terrain_pipeline").glob("mountain_*.py")) + [Path(__file__).resolve()]
    before = {str(path.relative_to(ROOT)): file_sha256(path) for path in files}
    frozen_before = frozen_hashes()
    json_new(output / "resource-precheck.json", {"budget": manning.preflight(2880, 30.), "source_code_sha256": before,
        "frozen_before": frozen_before, "roughness_s_m_third": .035, "study_identity": identity(record["arrays"], record["metadata"]),
        "only_changed_input": "saved_A_eastward_100m_HRU_vs_300m_HRU_including_nonlinear_soil_aggregation",
        "canonical_parent": str(fixed.relative_to(ROOT)), "parent_verifier_sha256": parent_source_hashes["tools/verify_mountain_depression_geometry.py"],
        "current_verifier_sha256": file_sha256(Path(__file__).resolve()), "canonical_parent_not_overwritten": True})
    path = weather_dir / "pressure_mountain-eastward-coupling.npz"
    expected = weather_report["cases"]["eastward"]["coupling_sha256"]
    coupled = load_coupling(path, expected_sha256=expected, source=source, topology=topology, geometry=coarse, selection=selection)
    bound = bind_saved_releases(coupled, source, topology, coarse, selection, record, dt_s=30.)
    old_case_report = json.loads((fixed / "report.json").read_text(encoding="utf-8"))["cases"]["eastward"]
    old_coupled = load_coupling(ROOT / old_case_report["A_archive"], expected_sha256=old_case_report["A_archive_sha256"],
        source=source, topology=topology, geometry=coarse, selection=selection)
    for key in ("receiver", "anchor_node", "node_downstream", "cell_node", "tau_s", "hydrology_mask"):
        if not np.array_equal(coupled["arrays"][key], old_coupled["arrays"][key]):
            raise ValueError("100m changed non-forcing topology: " + key)
    with np.load(fixed / "eastward-dt30-binding.npz", allow_pickle=False) as archive:
        for key in ("cell_partition", "node_partition", "partition_counts", "upstream_cell_mask"):
            if not np.array_equal(bound["arrays"][key], archive[key]):
                raise ValueError("100m contribution partition changed: " + key)
    forcing = bound["forcing"]
    save_npz_new(output / "eastward-dt30-binding.npz", bound["arrays"])
    json_new(output / "eastward-dt30-binding.json", bound["metadata"])
    save_npz_new(output / "tributary-geometry.npz", record["arrays"])
    json_new(output / "tributary-geometry.json", record["metadata"])
    limit = manning.capacity_bound(record, **{key: forcing[key] for key in ("inlet_q_m3_s", "lateral_q_m3_s", "tailwater_stage_m", "dt_s")})
    save_npz_new(output / "eastward-dt30-capacity.npz", {key: value for key, value in limit.items() if isinstance(value, np.ndarray)})
    saved = manning.prepare_manning_storage(record, coarse, **forcing)
    target = output / "eastward-dt30-storage.npz"
    manning.save_manning_storage(target, saved, record, coarse)
    with patch.object(manning, "prepare_manning_storage", side_effect=AssertionError("no re-advance")), \
         patch.object(manning, "least_squares", side_effect=AssertionError("no solve")):
        cold = manning.load_manning_storage(target, record, coarse, expected_sha256=file_sha256(target), trusted_forcing=forcing)
        provenance = validate_saved_binding(bound, coupled, record)
        mesh = export_manning_mesh(record, cold, coarse)
    save_npz_new(output / "eastward-dt30-mesh.npz", mesh["arrays"])
    json_new(output / "eastward-dt30-mesh.json", array_json(mesh))
    old_data = {}
    for name in ("eastward", "westward", "no_rain", "old_wet_storm"):
        old_data[name] = json.loads((fixed / f"{name}-dt30-mesh.json").read_text(encoding="utf-8"))
    old_data["eastward"] = array_json(mesh)
    write_manning_mesh_review(output, old_data)
    committed = cold["metadata"]["committed_steps"]
    rates = forcing["inlet_q_m3_s"] + forcing["lateral_q_m3_s"].sum(axis=1)
    report = {"schema": "mountain-manning-100m-single-input-comparison-v1", "status": cold["metadata"]["status"],
        "failure": cold["metadata"]["failure"], "A_archive": str(path.relative_to(ROOT)), "A_archive_sha256": expected,
        "A_report_sha256": file_sha256(weather_dir / "report.json"), "parent_package": str(fixed.relative_to(ROOT)),
        "same_source_geometry_topology_partition": True, "same_weather_parameters": True,
        "only_changed_input": "A_HRU_bin_300m_to_100m_including_nonlinear_soil_aggregation_not_terrain_resolution",
        "roughness_s_m_third": .035, "dt_s": 30., "requested_duration_s": 86400., "committed_duration_s": committed * 30.,
        "requested_input_m3": float(rates.sum() * 30.), "committed_input_m3": float(rates[:committed].sum() * 30.),
        "uncommitted_input_m3": float(rates[committed:].sum() * 30.),
        "inlet_peak_m3_s": float(forcing["inlet_q_m3_s"].max()), "binding_validation": provenance,
        "statistics": manning.validate_manning_storage(cold, record, coarse), "residual_evaluations": cold["metadata"]["residual_evaluations"],
        "necessary_any_interval_first_exceed_step": limit["any_interval_first_exceed_step"],
        "source_code_sha256": before, "mesh_metadata": mesh["metadata"], "old_eight_cases_not_advanced": True}
    with np.load(fixed / "eastward-dt30-storage.npz", allow_pickle=False) as archive:
        common = min(committed, archive["qedges_m3_s"].shape[0])
        old_q = archive["qedges_m3_s"][:common, -1]
        new_q = cold["arrays"]["qedges_m3_s"][:common, -1]
        report["100m_vs_300m"] = {"common_duration_s": common * 30.,
            "relative_outlet_L1": float(np.abs(new_q - old_q).sum() / np.abs(old_q).sum()),
            "new_minus_old_committed_outflow_m3": float((new_q - old_q).sum() * 30.),
            "new_minus_old_final_storage_m3": float(cold["arrays"]["storage_m3"][common].sum() - archive["storage_m3"][common].sum())}
        figure, axes = plt.subplots(2, 1, figsize=(13, 8))
        axes[0].plot(np.arange(common) * 30 / 3600, old_q, label="300m HRU saved")
        axes[0].plot(np.arange(common) * 30 / 3600, new_q, label="100m HRU saved")
        axes[1].plot(np.arange(common + 1) * 30 / 3600, archive["storage_m3"][:common + 1].sum(axis=1), label="300m HRU")
        axes[1].plot(np.arange(common + 1) * 30 / 3600, cold["arrays"]["storage_m3"][:common + 1].sum(axis=1), label="100m HRU")
        for axis in axes:
            axis.legend(); axis.grid(alpha=.3); axis.set_xlabel("Time (h), same 24h weather")
        axes[0].set_ylabel("Outlet (m3/s)"); axes[1].set_ylabel("Fine storage (m3)")
        figure.tight_layout(); figure.savefig(output / "hydrographs.png", dpi=150); plt.close(figure)
    if before != {str(path.relative_to(ROOT)): file_sha256(path) for path in files} or frozen_before != frozen_hashes():
        raise ValueError("source changed during 100m single trial")
    report["frozen_unchanged"] = True
    report["artifacts_sha256"] = {path.name: file_sha256(path) for path in output.iterdir() if path.is_file()}
    json_new(output / "report.json", report)
    print("100M_OUTPUT", output, json.dumps(report["statistics"]), flush=True)


if __name__ == "__main__":
    if "--manning-100m" in sys.argv:
        verify_manning_100m()
    elif "--manning-freeze" in sys.argv:
        freeze_manning(sys.argv[sys.argv.index("--manning-freeze") + 1])
    elif "--manning" in sys.argv:
        verify_manning()
    else:
        main()
