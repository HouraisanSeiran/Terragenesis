"""Real-source geometry/coupling eligibility evidence, never fake lake acceptance."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.lake import prepare_mountain_geometry as prepare_mountain_geometry
from terrain_pipeline.lake import save_mountain_geometry as save_mountain_geometry
from terrain_pipeline.lake import screen_single_pool_lakes as screen_single_pool_lakes
from terrain_pipeline.lake import window_boundary as window_boundary
from terrain_pipeline.lake import build_group_topology as build_group_topology
from terrain_pipeline.lake import contribution_mask as contribution_mask
from terrain_pipeline.lake import couple_rainfall as couple_rainfall
from terrain_pipeline.lake import group_lake_specs as group_lake_specs
from terrain_pipeline.lake import load_coupling as load_coupling
from terrain_pipeline.lake import save_coupling as save_coupling
from terrain_pipeline.lake import single_pool_proof as single_pool_proof
from terrain_pipeline.lake import terminal_ownership as terminal_ownership
from terrain_pipeline.lake import validate_coupling as validate_coupling
from terrain_pipeline.common_infra import file_sha256, identity, load_legacy_source, save_source
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from tools.verify_mountain_source_adapter import assert_unchanged, snapshot, write_json


DELIVERY_FILES = ("terrain_pipeline/mountain_source_adapter.py", 'terrain_pipeline/lake.py',
    'terrain_pipeline/lake.py', "tools/verify_mountain_lake_coupling.py",
    "tools/verify_mountain_source_adapter.py", "tests/test_mountain_source_adapter.py",
    "tests/test_mountain_lake_coupling.py", "docs/mountain-source-and-coupling-v1.md")


def delivery_snapshot():
    return {name: file_sha256(ROOT / name) for name in DELIVERY_FILES}


def inspect_geometry(source, geometry):
    arrays = geometry["arrays"]
    height = source["arrays"]["height_m"]
    receiver = arrays["receiver"].reshape(height.shape)
    domain = np.ones(height.shape, bool)
    partition = terminal_ownership(receiver, domain)
    screening = screen_single_pool_lakes(geometry)
    candidates = []
    for decision in screening["decisions"]:
        if decision["status"] != "single_pool_static_candidate":
            continue
        lake = decision["lake_id"]
        basin = arrays["lake_id"] == lake
        path_flat = np.array(decision["downstream_path"], np.int64)
        path = np.column_stack(np.unravel_index(path_flat, height.shape)).astype(np.int64)
        legal = np.zeros(height.shape, bool)
        legal[tuple(path[-1])] = True
        spill = path[0]
        shore = np.zeros(height.shape, bool)
        for row, column in np.argwhere(basin):
            for delta_row, delta_column in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbor = (row + delta_row, column + delta_column)
                if not basin[neighbor]:
                    shore[neighbor] = True
        shore[tuple(spill)] = False
        max_stage = min(float(height[shore].min()), float(height[tuple(spill)]) + 0.1)
        record = dict(decision, max_stage_m=max_stage,
            positive_rating_stage_margin_m=max_stage-float(height[tuple(spill)]))
        try:
            record["single_pool_proof"] = single_pool_proof(height, basin, spill, path, domain,
                arrays["protected_mask"], legal, max_stage_m=max_stage)
            record["single_pool_geometry_valid"] = True
        except ValueError as error:
            record.update(single_pool_geometry_valid=False, rejection=str(error))
        terminal = int(path_flat[-1])
        mask, proof = contribution_mask(receiver, domain, terminal)
        group = int(arrays["outlet_owner"].flat[terminal])
        lakes = np.unique(arrays["lake_id"][mask])
        lakes = lakes[lakes > 0]
        record.update(contribution_proof=proof, contributing_area_m2=float(mask.sum() * source["metadata"]["spacing_m"]**2),
            complete_group_lake_ids=lakes.tolist(), static_geometry_accepted=bool(arrays["accepted_outlets"][group]),
            all_group_lakes_single_pool=all(any(item["lake_id"] == int(label) and
                item["status"] == "single_pool_static_candidate" for item in screening["decisions"]) for label in lakes),
            dynamic_water_solved=False)
        candidates.append(record)
    return {"screening": screening, "candidates": candidates,
        "partition": {"terminal_flat": partition["terminal_flat"].tolist(),
            "contributing_counts": partition["contributing_counts"].tolist(),
            "contributing_area_m2": (partition["contributing_counts"] * source["metadata"]["spacing_m"]**2).tolist()},
        "geometry_identity": identity(arrays, geometry["metadata"]),
        "accepted_area_m2": float(arrays["accepted_mask"].sum() * source["metadata"]["spacing_m"]**2),
        "potential_full_spill_capacity_m3": float(arrays["lake_capacity_m3"].sum()),
        "capacity_is_actual_storage": False, "hydrological_closure_certified": False}


def verify(destination):
    if destination.exists():
        raise FileExistsError(destination)
    before = snapshot()
    write_json(destination / "frozen-before.json", before)
    delivery_before = delivery_snapshot()
    write_json(destination / "delivery-before.json", delivery_before)
    report = {"status": "real_source_partial_complete_group_coupling", "gpu_inference_run": False,
        "boundary_condition_changed": True, "same_boundary_algorithm_comparison": False,
        "samples": {}, "dynamic_water_solved": "selected_complete_groups_only",
        "whole_window_dynamic_water_solved": False}
    try:
        for name in ("normal_mountain", "pressure_mountain"):
            source = load_legacy_source(name, boundary_policy="all_edges_open")
            save_source(destination / f"{name}-source.npz", source)
            geometry = prepare_mountain_geometry(source["arrays"]["height_m"],
                spacing_m=source["metadata"]["spacing_m"], origin_m_xz=source["metadata"]["origin_m_xz"],
                source_binding={"source_identity": source["identity_sha256"]},
                boundary_mask=window_boundary(source["arrays"]["height_m"].shape),
                protected_mask=np.zeros(source["arrays"]["height_m"].shape, bool))
            geometry_path = destination / f"{name}-geometry.npz"
            save_mountain_geometry(geometry_path, geometry, trusted_height=source["arrays"]["height_m"],
                source_binding={"source_identity": source["identity_sha256"]})
            report["samples"][name] = dict(inspect_geometry(source, geometry),
                geometry_archive_sha256=file_sha256(geometry_path), source_identity=source["identity_sha256"])
            group = 154 if name == "normal_mountain" else 1639
            report["samples"][name]["complete_group_dynamics"] = run_complete_group(
                destination, name, source, geometry, group)
            cascade_group = 1208 if name == "normal_mountain" else 1623
            report["samples"][name]["cascade_group_dynamics"] = run_complete_group(
                destination, name + "_cascade", source, geometry, cascade_group)
            if name == "pressure_mountain":
                report["samples"][name]["cascade_positive_group_dynamics"] = run_complete_group(
                    destination, name + "_cascade_positive", source, geometry, 1378)
        report["frozen_after"] = assert_unchanged(before)
        report["delivery_source_sha256"] = delivery_before
        report["delivery_unchanged_during_run"] = delivery_before == delivery_snapshot()
        if not report["delivery_unchanged_during_run"]:
            report["status"] = "draft_delivery_sources_changed_during_run_not_frozen"
        write_review(destination, report)
        write_json(destination / "report.json", report)
        return report
    except BaseException as error:
        write_json(destination / "failure.json", {"exception": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(), "dynamic_water_solved": False})
        raise


def run_complete_group(destination, name, source, geometry, group):
    topology, selection, lake_nodes = build_group_topology(source, geometry, group)
    mask = selection["arrays"]["mask"]
    owner = np.full(mask.shape, -1, np.int64)
    height = source["arrays"]["height_m"]
    edges = np.linspace(height[mask].min(), height[mask].max(), 17)
    bands = np.minimum(np.searchsorted(edges, height[mask], side="right") - 1, 15)
    _, labels = np.unique(bands, return_inverse=True)
    owner[mask] = labels
    hrus = int(labels.max()) + 1
    steps = 1344
    dt = 900.
    hours = np.arange(steps) * dt / 3600.
    specs = group_lake_specs(source, geometry, topology, lake_nodes, steps=steps)
    record = {"group": group, "selection_identity": selection["identity_sha256"],
        "selection_metadata": selection["metadata"], "area_m2": float(mask.sum() * 900),
        "nodes": len(topology["node_kind"]), "lake_nodes": lake_nodes,
        "grid_resolution_m": 30., "lake_semantics": "full_30m_cell_discrete_storage_not_resolved_natural_lake",
        "geometry_scope": "independent_no_cut_certificate_not_construction_acceptance",
        "weir_coefficient_m_half_per_s": 1.7, "weir_width_m": 30., "scenarios": {}}
    first_lake = geometry["arrays"]["lake_id"].ravel().copy()
    for cell in geometry["arrays"]["order"]:
        target = int(geometry["arrays"]["receiver"][cell])
        if first_lake[cell] == 0 and target >= 0:
            first_lake[cell] = first_lake[target]
    record["lake_contribution"] = {}
    for lake, node in lake_nodes.items():
        contributing = mask.ravel() & (first_lake == lake)
        count = int(contributing.sum())
        record["lake_contribution"][str(lake)] = {
            "contributing_cells": count, "contributing_area_m2": float(count * 900),
            "fraction_of_group": float(count / mask.sum()),
            "bypass_fraction_of_group": float(1-count/mask.sum()),
            "storage_footprint_cells": int((geometry["arrays"]["lake_id"] == lake).sum()),
            "note": "first-lake area fraction; upstream cascaded contributions additionally transfer through DAG"}
    for scenario in ("steady", "dry_storm", "wet_storm", "wet_storm_surface"):
        if scenario == "steady":
            intensity = np.where(hours < 24, 3., 0.)
        else:
            intensity = np.select([(hours >= 6) & (hours < 9), (hours >= 9) & (hours < 12),
                (hours >= 12) & (hours < 18)], [4., 24., 8.], default=0.)
        rain = np.repeat(intensity[:, None], hrus, axis=1)
        parameters = RunoffParameters(initial_soil_mm=135. if scenario.startswith("wet_storm") else 30.)
        result = couple_rainfall(source, topology, owner, rain, dt_s=dt, geometry=geometry,
            selection=selection, parameters=parameters, lakes=specs,
            surface_rain=scenario.endswith("_surface"))
        if "arrays" not in result:
            failure = dict(result)
            lake = failure.pop("lake_failure", None)
            if lake is not None:
                from terrain_pipeline.lake import save_lake_routing as save_lake_routing

                path = destination / f"{name}-{scenario}-failed-lake.npz"
                save_lake_routing(lake, path)
                failure["lake_failure"] = {key: value for key, value in lake.items() if key != "arrays"}
                failure["lake_archive_sha256"] = file_sha256(path)
                export_failed_case(destination, name, scenario, source, topology, selection, lake, failure)
            else:
                write_json(destination / f"{name}-{scenario}-consumer.json", {
                    "schema": "mountain-coupling-failed-no-prefix-review-v1",
                    "source_identity": source["identity_sha256"], "geometry_identity": topology["geometry_identity"],
                    "selection_identity": selection["identity_sha256"], "scenario": scenario,
                    "case_id": f"{name}-{scenario}",
                    "status": failure["status"], "failure": failure, "state_time_hours": [0.],
                    "lake_storage_m3": [None], "lake_stage_by_node_m": {}, "outlet_q_m3_s": [],
                    "group_outlet_solved": False, "joint_residual_m3": [], "rain_support": "not_committed",
                    "boundary": "external_open_boundary", "image": None})
            write_json(destination / f"{name}-{scenario}-failure.json", failure)
            record["scenarios"][scenario] = failure
            continue
        path = destination / f"{name}-{scenario}-coupling.npz"
        save_coupling(path, result)
        loaded = load_coupling(path, expected_sha256=file_sha256(path), source=source,
            topology=topology, geometry=geometry, selection=selection)
        stats = validate_coupling(loaded, source=source, topology=topology, geometry=geometry, selection=selection)
        stats.update(archive_sha256=file_sha256(path), identity_sha256=result["identity_sha256"],
            dynamic_water_solved=True, outlet_peak_m3_s=float(result["arrays"]["total_boundary_volume_m3"].max()/dt),
            final_lake_storage_m3=float(result["arrays"]["storage_m3"][-1, list(lake_nodes.values())].sum()),
            final_river_storage_m3=float(result["arrays"]["storage_m3"][-1, len(lake_nodes):].sum()))
        record["scenarios"][scenario] = stats
        export_review_case(destination, name, scenario, source, geometry, topology, selection, result)
    return record


def export_failed_case(destination, name, scenario, source, topology, selection, lake, failure):
    arrays = lake["arrays"]
    dt = lake["input"]["recipe"]["dt_s"]
    count = arrays["storage_m3"].size
    write_json(destination / f"{name}-{scenario}-consumer.json", {
        "schema": "mountain-coupling-failed-prefix-review-v1", "source_identity": source["identity_sha256"],
        "geometry_identity": topology["geometry_identity"], "selection_identity": selection["identity_sha256"],
        "scenario": scenario, "status": "failed_single_pool_prefix_not_whole_group_solution",
        "case_id": f"{name}-{scenario}",
        "failure": lake["diagnostic"], "failed_node": failure["failed_node"],
        "state_time_hours": (np.arange(count)*dt/3600.).tolist(),
        "lake_storage_m3": arrays["storage_m3"].tolist(),
        "lake_stage_by_node_m": {str(failure["failed_node"]): arrays["stage_m"].tolist()},
        "outlet_q_m3_s": arrays["step_outflow_m3_s"].tolist(), "group_outlet_solved": False,
        "plot_flux_semantics": "failed_pool_spill_only_not_group_outlet",
        "lake_inflow_m3_s": (arrays["step_inflow_volume_m3"]/dt).tolist(),
        "lake_spill_m3_s": arrays["step_outflow_m3_s"].tolist(),
        "joint_residual_m3": arrays["step_residual_m3"].tolist(),
        "rain_support": "see failure input; no whole-group ledger committed",
        "river_stage_solved": False, "hydrological_closure_certified": False,
        "boundary": "external_open_boundary", "image": None})


def export_review_case(destination, name, scenario, source, geometry, topology, selection, result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arrays = result["arrays"]
    mask = selection["arrays"]["mask"]
    cells = np.argwhere(mask)
    lower = cells.min(axis=0)
    upper = cells.max(axis=0) + 1
    crop = tuple(slice(int(first), int(last)) for first, last in zip(lower, upper))
    origin = source["metadata"]["origin_m_xz"]
    spacing = source["metadata"]["spacing_m"]
    extent = [(origin[0]+(lower[1]-.5)*spacing)/1000., (origin[0]+(upper[1]-.5)*spacing)/1000.,
              (origin[1]+(upper[0]-.5)*spacing)/1000., (origin[1]+(lower[0]-.5)*spacing)/1000.]
    figure, axes = plt.subplots(1, 3, figsize=(15, 5))
    image = axes[0].imshow(source["arrays"]["height_m"][crop], cmap="terrain", extent=extent)
    figure.colorbar(image, ax=axes[0], label="Elevation m, sea datum 0")
    grid_east = (origin[0]+np.arange(lower[1],upper[1])*spacing)/1000.
    grid_south = (origin[1]+np.arange(lower[0],upper[0])*spacing)/1000.
    axes[0].contour(grid_east, grid_south, mask[crop], levels=[.5], colors="white", linewidths=.7)
    axes[0].set_title("H0 / complete window contribution")
    lake_mask = geometry["arrays"]["lake_mask"][crop] & mask[crop]
    display = np.where(mask[crop], geometry["arrays"]["H2_m"][crop], np.nan)
    axes[1].imshow(display, cmap="terrain", extent=extent)
    lake_rows, lake_cols = np.nonzero(lake_mask)
    axes[1].scatter(grid_east[lake_cols], grid_south[lake_rows], marker="s", color="cyan", s=18, label="30m storage cell")
    river = topology["receiver"]
    dry = mask & (geometry["arrays"]["lake_id"] == 0)
    from matplotlib.collections import LineCollection

    segments = []
    channels = []
    for cell in np.flatnonzero(dry):
        target = int(river.flat[cell])
        if target >= 0:
            row, col = divmod(int(cell), mask.shape[1])
            next_row, next_col = divmod(target, mask.shape[1])
            segment = [((origin[0]+col*spacing)/1000., (origin[1]+row*spacing)/1000.),
                       ((origin[0]+next_col*spacing)/1000., (origin[1]+next_row*spacing)/1000.)]
            if geometry["arrays"]["flowline_mask"].flat[cell]:
                channels.append(segment)
            else:
                segments.append(segment)
    axes[1].add_collection(LineCollection(segments, colors="#999999", linewidths=.25, alpha=.4, label="hillslope receiver routes"))
    axes[1].add_collection(LineCollection(channels, colors="#165bc7", linewidths=1., label="channel >=1 km2 upstream"))
    axes[1].set_title("Receiver drainage, not all visible rivers")
    for axis in axes[:2]:
        axis.set_xlabel("East coordinate km")
        axis.set_ylabel("South coordinate km")
    axes[1].legend(fontsize=8)
    dt = result["metadata"]["runoff_metadata"]["dt_s"]
    hours = np.arange(arrays["total_boundary_volume_m3"].size) * dt / 3600.
    axes[2].plot(hours, arrays["total_boundary_volume_m3"] / dt, label="external boundary")
    lake_nodes = [node for node, kind in enumerate(topology["node_kind"]) if kind == "lake"]
    axes[2].plot(hours, arrays["outflow_volume_m3"][:, lake_nodes].sum(axis=1)/dt, label="lake spill only")
    axes[2].plot(hours, arrays["lateral_volume_m3"].sum(axis=1)/dt, label="local total")
    axes[2].set_xlabel("physical hour")
    axes[2].set_ylabel("m3/s")
    axes[2].legend(fontsize=8)
    axes[2].set_title(name + " / " + scenario)
    figure.tight_layout()
    figure.savefig(destination / f"{name}-{scenario}-review.png", dpi=130)
    plt.close(figure)
    times = [1., 12., 48., 336.]
    frames = []
    for hour in times:
        index = min(int(hour*3600/dt), hours.size-1)
        frames.append({"physical_hour": float(hours[index]),
            "node_storage_m3": arrays["storage_m3"][index+1].tolist(),
            "node_q_m3_s": (arrays["outflow_volume_m3"][index]/dt).tolist(),
            "lake_stage_m": {str(node): float(arrays["lake_stage_m"][index+1,node]) for node in lake_nodes}})
    write_json(destination / f"{name}-{scenario}-consumer.json", {
        "schema": "mountain-coupling-readonly-review-v1", "source_identity": source["identity_sha256"],
        "geometry_identity": topology["geometry_identity"], "selection_identity": selection["identity_sha256"],
        "scenario": scenario, "node_kind": topology["node_kind"],
        "case_id": f"{name}-{scenario}",
        "node_downstream": topology["node_downstream"].tolist(), "frames": frames,
        "time_hours": hours.tolist(), "outlet_q_m3_s": (arrays["total_boundary_volume_m3"]/dt).tolist(),
        "state_time_hours": (np.arange(hours.size+1)*dt/3600.).tolist(),
        "state_flux_alignment": "state k at k*dt; preceding interval k-1 when k>0; initial state has no flux interval",
        "archive_sha256": file_sha256(destination / f"{name}-{scenario}-coupling.npz"),
        "dt_s": dt,
        "lake_storage_m3": arrays["storage_m3"][:, lake_nodes].sum(axis=1).tolist(),
        "lake_stage_by_node_m": {str(node): arrays["lake_stage_m"][:, node].tolist() for node in lake_nodes},
        "river_storage_m3": arrays["storage_m3"][:, [node for node in range(len(topology["node_kind"])) if node not in lake_nodes]].sum(axis=1).tolist(),
        "soil_fast_slow_storage_m3": ((arrays["runoff_soil_mm"]+arrays["runoff_fast_mm"]+arrays["runoff_slow_mm"])*arrays["runoff_area_m2"]/1000.).sum(axis=1).tolist(),
        "total_rain_volume_m3": (arrays["runoff_rain_volume_m3"].sum(axis=1)+arrays["surface_rain_volume_m3"].sum(axis=1)).tolist(),
        "joint_residual_m3": (arrays["runoff_rain_volume_m3"].sum(axis=1)+arrays["surface_rain_volume_m3"].sum(axis=1)-arrays["runoff_et_volume_m3"].sum(axis=1)-arrays["lake_loss_volume_m3"].sum(axis=1)-arrays["total_boundary_volume_m3"]-arrays["runoff_storage_change_m3"].sum(axis=1)-np.diff(arrays["storage_m3"],axis=0).sum(axis=1)).tolist(),
        "rain_support": result["metadata"]["rain_support"], "river_stage_solved": False,
        "hydrological_closure_certified": False, "boundary": "external_open_boundary",
        "image": f"{name}-{scenario}-review.png"})


def write_review(destination, report):
    from terrain_pipeline.common_infra import publish_bytes

    options = []
    for name, sample in report["samples"].items():
        for key, suffix in (("complete_group_dynamics", ""), ("cascade_group_dynamics", "_cascade")):
            for scenario, result in sample[key]["scenarios"].items():
                state = "通过" if result.get("dynamic_water_solved") else "失败前缀"
                options.append(f'<option value="{name}{suffix}-{scenario}">{name}{suffix} / {scenario} / {state}</option>')
        if "cascade_positive_group_dynamics" in sample:
            for scenario, result in sample["cascade_positive_group_dynamics"]["scenarios"].items():
                state = "通过" if result.get("dynamic_water_solved") else "失败前缀"
                options.append(f'<option value="{name}_cascade_positive-{scenario}">{name} positive cascade / {scenario} / {state}</option>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>有限窗口湖河水账审查</title><style>body{font:16px sans-serif;background:#16202b;color:#eee;margin:25px}img{max-width:100%}pre{white-space:pre-wrap}canvas{background:#fff;width:95%;height:240px}</style>
<h1>真实旧 TD：有限窗口完整贡献组湖河耦合</h1>
<p>边界条件由旧单出口改为全窗口开放，不能作同边界算法改进。不是完整水文规划域认证；非海岸终端均为 external_open_boundary。</p>
<p>30m 单格/两格湖是离散蓄水单元，不是精细自然湖。原地形未切；几何采用独立 no-cut 证据，不等同施工 accepted。河道为线性库，没有水深或回水。</p>
<p>固定全陆地概念产流与 fixed footprint 直降雨对照分别标明。后者固定湖 footprint 即使初始干燥；尚非动态湿面积模型。无 GPU 推理，无 Minecraft 部署。</p>
<select id="case">OPTIONS</select><input id="time" type="range" min="0" max="1344" step="1" value="48"><span id="clock"></span>
<img id="image" alt="H0、湖河路径和过程线"><canvas id="plot" width="1200" height="240"></canvas><pre id="detail"></pre>
<script>let data,requestId=0;const choose=document.getElementById('case'),slider=document.getElementById('time');
async function load(){const ticket=++requestId,name=choose.value;const incoming=await(await fetch(name+'-consumer.json')).json();if(ticket!==requestId||choose.value!==name)return;data=incoming;slider.max=data.state_time_hours.length-1;slider.value=Math.min(+slider.value,+slider.max);const img=document.getElementById('image');img.hidden=!data.image;if(data.image)img.src=data.image;render()}
function render(){if(!data)return;const k=Math.min(+slider.value,data.state_time_hours.length-1),interval=k? k-1:null;const frame={state_index:k,physical_hour:data.state_time_hours[k],preceding_interval_index:interval,lake_storage_m3:data.lake_storage_m3[k],lake_stage_m:Object.fromEntries(Object.entries(data.lake_stage_by_node_m).map(([node,values])=>[node,values[k]])),river_storage_m3:data.river_storage_m3?.[k],soil_fast_slow_storage_m3:data.soil_fast_slow_storage_m3?.[k],rain_volume_m3:interval===null?null:data.total_rain_volume_m3?.[interval],outlet_q_m3_s:interval===null||data.group_outlet_solved===false?null:data.outlet_q_m3_s[interval],joint_residual_m3:interval===null?null:data.joint_residual_m3[interval],failure:data.failure||null,status:data.status||'selected_group_solved'};document.getElementById('clock').textContent=frame.physical_hour+' h; T+1 state / preceding T interval';
document.getElementById('detail').textContent=JSON.stringify({source:data.source_identity,geometry:data.geometry_identity,selection:data.selection_identity,rain_support:data.rain_support,boundary:data.boundary,river_stage_solved:false,hydrological_closure_certified:false,frame},null,2);
const canvas=document.getElementById('plot'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,1200,240);const duration=data.state_time_hours.at(-1),failed=data.group_outlet_solved===false,flux=data.outlet_q_m3_s,max=Math.max(...flux,1e-9);ctx.strokeStyle='#1250ad';ctx.beginPath();flux.forEach((value,index)=>{let hour=data.state_time_hours[index+1],x=40+hour/Math.max(duration,1e-9)*1120,y=210-value/max*180;index?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.fillStyle='#222';ctx.fillText((failed?'FAILED POOL SPILL ONLY; group outlet not solved':'External boundary m3/s')+'; physical hours 0-'+duration,40,20);let x=40+frame.physical_hour/Math.max(duration,1e-9)*1120;ctx.strokeStyle='red';ctx.beginPath();ctx.moveTo(x,25);ctx.lineTo(x,220);ctx.stroke()}
choose.onchange=load;slider.oninput=render;load();</script></html>'''.replace("OPTIONS", "".join(options))
    publish_bytes(destination / "review.html", page.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument("--browser-review", type=Path)
    parser.add_argument("--freeze-from", type=Path)
    args = parser.parse_args()
    destination = args.output or ROOT / "verification/mountain-lake-coupling" / (
        "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    if args.freeze_from:
        report = freeze_saved_run(args.freeze_from, destination)
        print({"output": str(destination), "status": report["status"]})
    elif args.browser_review:
        audit_browser(args.browser_review)
    elif args.sensitivity:
        report = verify_sensitivity(destination)
        print({"output": str(destination), "status": report["status"]})
    else:
        report = verify(destination)
        print({"output": str(destination), "candidate_counts": {
            name: len(sample["candidates"]) for name, sample in report["samples"].items()}})


def freeze_saved_run(source_directory, destination):
    """Revalidate saved equations, then export current read-only consumers without advancing."""
    import json
    import shutil
    from terrain_pipeline.lake import load_mountain_geometry as load_mountain_geometry
    from terrain_pipeline.common_infra import checked_archive
    from terrain_pipeline.lake import lake_routing_hash as lake_routing_hash
    from terrain_pipeline.runoff import _strict_json as _strict_json

    source_directory = source_directory.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    before = snapshot()
    delivery_before = delivery_snapshot()
    write_json(destination / "frozen-before.json", before)
    write_json(destination / "delivery-before.json", delivery_before)
    report = json.loads((source_directory / "report.json").read_text(encoding="utf-8"))
    report["origin_draft_directory"] = str(source_directory)
    report["origin_draft_report_sha256"] = file_sha256(source_directory / "report.json")
    try:
        for name, sample in report["samples"].items():
            source = load_legacy_source(name, boundary_policy="all_edges_open")
            geometry_path = source_directory / f"{name}-geometry.npz"
            if file_sha256(geometry_path) != sample["geometry_archive_sha256"]:
                raise ValueError("draft geometry external hash mismatch")
            geometry = load_mountain_geometry(geometry_path, trusted_height=source["arrays"]["height_m"],
                source_binding={"source_identity": source["identity_sha256"]})
            for filename in (f"{name}-geometry.npz", f"{name}-source.npz"):
                shutil.copyfile(source_directory / filename, destination / filename)
            for key, suffix in (("complete_group_dynamics", ""), ("cascade_group_dynamics", "_cascade"),
                    ("cascade_positive_group_dynamics", "_cascade_positive")):
                if key not in sample:
                    continue
                group_record = sample[key]
                topology, selection, lake_nodes = build_group_topology(source, geometry, group_record["group"])
                for scenario, stats in group_record["scenarios"].items():
                    case_name = name + suffix
                    if stats.get("dynamic_water_solved"):
                        filename = f"{case_name}-{scenario}-coupling.npz"
                        path = source_directory / filename
                        result = load_coupling(path, expected_sha256=stats["archive_sha256"], source=source,
                            topology=topology, geometry=geometry, selection=selection)
                        stats["frozen_static_validation"] = validate_coupling(result, source=source,
                            topology=topology, geometry=geometry, selection=selection)
                        shutil.copyfile(path, destination / filename)
                        export_review_case(destination, case_name, scenario, source, geometry, topology, selection, result)
                    else:
                        failure_path = source_directory / f"{case_name}-{scenario}-failure.json"
                        shutil.copyfile(failure_path, destination / failure_path.name)
                        if "lake_failure" in stats:
                            filename = f"{case_name}-{scenario}-failed-lake.npz"
                            path = source_directory / filename
                            if file_sha256(path) != stats["lake_archive_sha256"]:
                                raise ValueError("failed pool external hash mismatch")
                            payload = checked_archive(path, expected_sha256=stats["lake_archive_sha256"])
                            metadata = payload.pop("metadata")
                            lake = _strict_json(str(metadata.item()))
                            lake["arrays"] = payload
                            if lake["identity_sha256"] != lake_routing_hash(lake) or lake["scenario_feasible"] is not False:
                                raise ValueError("failed pool static identity/status mismatch")
                            saved = lake["arrays"]
                            recipe = lake["input"]["recipe"]
                            floors = saved["height_m"][saved["basin_mask"]]
                            area = lake["input"]["spacing_x_m"] * lake["input"]["spacing_z_m"]
                            volume = np.array([np.maximum(stage-floors,0).sum()*area for stage in saved["stage_m"]])
                            if not np.allclose(volume, saved["storage_m3"], rtol=1e-12, atol=1e-8):
                                raise ValueError("failed prefix V(h) mismatch")
                            residual = saved["step_inflow_volume_m3"]-saved["step_loss_volume_m3"]-saved["step_outflow_volume_m3"]-np.diff(saved["storage_m3"])
                            if (np.abs(residual) > 1e-8+np.maximum(volume[:-1],volume[1:])*1e-12).any():
                                raise ValueError("failed prefix ledger mismatch")
                            single_pool_proof(saved["height_m"],saved["basin_mask"],saved["legal_spill_grid_zx"],
                                saved["downstream_path_grid_zx"],saved["domain_mask"],saved["protected_mask"],
                                saved["legal_outlet_mask"],max_stage_m=recipe["max_stage_m"])
                            shutil.copyfile(path, destination / filename)
                            export_failed_case(destination, case_name, scenario, source, topology, selection, lake, stats)
                        else:
                            shutil.copyfile(source_directory / f"{case_name}-{scenario}-consumer.json",
                                destination / f"{case_name}-{scenario}-consumer.json")
        report["frozen_after"] = assert_unchanged(before)
        report["delivery_source_sha256"] = delivery_before
        report["delivery_unchanged_during_run"] = delivery_before == delivery_snapshot()
        if not report["delivery_unchanged_during_run"]:
            raise RuntimeError("delivery changed during static freezing")
        report["status"] = "frozen_static_validated_partial_complete_groups"
        write_review(destination, report)
        write_json(destination / "report.json", report)
        return report
    except BaseException as error:
        write_json(destination / "failure.json", {"exception": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(), "frozen_publication_complete": False})
        raise


def verify_sensitivity(destination):
    from terrain_pipeline.lake import load_mountain_geometry as load_mountain_geometry

    if destination.exists():
        raise FileExistsError(destination)
    before = snapshot()
    write_json(destination / "frozen-before.json", before)
    base = ROOT / "verification/mountain-lake-coupling/run-20261001T062620750889Z"
    report = {"status": "72h_dt_sensitivity_not_peak_accuracy_certification", "cases": {},
        "limitation": "single-cell tau30s; backward Euler dt/tau 30 vs 15; not a convergence proof or calibrated hydrograph"}
    try:
        for name, group in (("normal_mountain", 154), ("pressure_mountain", 1639)):
            source = load_legacy_source(name, boundary_policy="all_edges_open")
            geometry = load_mountain_geometry(base / f"{name}-geometry.npz",
                trusted_height=source["arrays"]["height_m"], source_binding={"source_identity": source["identity_sha256"]})
            topology, selection, lake_nodes = build_group_topology(source, geometry, group)
            owner = np.full(selection["arrays"]["mask"].shape, -1, np.int64)
            owner[selection["arrays"]["mask"]] = 0
            comparison = {}
            for dt in (900., 450.):
                steps = int(72*3600/dt)
                hours = np.arange(steps)*dt/3600.
                rain = np.select([(hours >= 6) & (hours < 9), (hours >= 9) & (hours < 12),
                    (hours >= 12) & (hours < 18)], [4., 24., 8.], default=0.)[:, None]
                specs = group_lake_specs(source, geometry, topology, lake_nodes, steps=steps)
                result = couple_rainfall(source, topology, owner, rain, dt_s=dt, geometry=geometry,
                    selection=selection, lakes=specs, parameters=RunoffParameters(initial_soil_mm=135.), surface_rain=True)
                if "arrays" not in result:
                    raise ValueError("sensitivity scenario failed; preserve the explicit failure separately")
                path = destination / f"{name}-dt{int(dt)}.npz"
                save_coupling(path, result)
                arrays = result["arrays"]
                flow = arrays["total_boundary_volume_m3"]/dt
                comparison[str(int(dt))] = {"peak_q_m3_s": float(flow.max()),
                    "peak_interval_start_h": float(hours[flow.argmax()]),
                    "max_lake_stage_m": float(arrays["lake_stage_m"][:, list(lake_nodes.values())].max()),
                    "total_outflow_m3": float(arrays["total_boundary_volume_m3"].sum()),
                    "total_rain_m3": float(arrays["runoff_rain_volume_m3"].sum()+arrays["surface_rain_volume_m3"].sum()),
                    "archive_sha256": file_sha256(path),
                    "ledger": validate_coupling(result, source=source, topology=topology, geometry=geometry, selection=selection)}
            first, second = comparison["900"], comparison["450"]
            comparison["difference_450_minus_900"] = {key: second[key]-first[key] for key in (
                "peak_q_m3_s", "peak_interval_start_h", "max_lake_stage_m", "total_outflow_m3", "total_rain_m3")}
            comparison["relative_difference"] = {key: (second[key]-first[key])/max(abs(first[key]),1e-12)
                for key in ("peak_q_m3_s", "total_outflow_m3")}
            report["cases"][name] = comparison
        report["frozen_after"] = assert_unchanged(before)
        write_json(destination / "report.json", report)
        return report
    except BaseException as error:
        write_json(destination / "failure.json", {"exception": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc()})
        raise


def audit_browser(directory):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from playwright.sync_api import sync_playwright

    directory = directory.resolve()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {"pageerrors": [], "cases": {}, "html_sha256": file_sha256(directory / "review.html")}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True, args=["--disable-gpu"])
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/review.html", wait_until="networkidle")
            options = page.locator("#case option").evaluate_all("items=>items.map(item=>item.value)")
            for option in options:
                page.select_option("#case", option)
                page.wait_for_function("name=>data?.case_id===name", arg=option)
                page.wait_for_load_state("networkidle")
                count = page.evaluate("data.state_time_hours.length")
                points = sorted(set((0, min(48,count-1), count-1)))
                for point in points:
                    page.locator("#time").evaluate("(slider,value)=>{slider.value=value;slider.dispatchEvent(new Event('input'))}", point)
                    frame = page.locator("#detail").inner_text()
                    if f'"state_index": {point}' not in frame:
                        raise ValueError("browser state index mismatch")
                image_ok = page.locator("#image").evaluate("img=>img.hidden||(img.complete&&img.naturalWidth>0)")
                if not image_ok:
                    raise ValueError("browser image not loaded")
                report["cases"][option] = {"state_count": count, "indices_checked": points, "image_ok": image_ok}
            if report["pageerrors"]:
                raise ValueError("browser pageerrors")
            page.screenshot(path=str(directory / "browser-review.png"), full_page=True)
            browser.close()
        write_json(directory / "browser-review.json", report)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
