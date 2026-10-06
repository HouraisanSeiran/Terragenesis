"""Frozen 60m HRU paired hydrology and saved-data-only playback review."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.mountain_depression_geometry import load_mountain_geometry
from terrain_pipeline.mountain_lake_coupling import (
    build_group_topology, couple_rainfall, group_lake_specs, load_coupling, save_coupling, validate_coupling,
)
from terrain_pipeline.mountain_source_adapter import checked_archive, file_sha256, load_legacy_source
from terrain_pipeline.mountain_storm_forcing import load_forcing
from terrain_pipeline.rainfall_runoff import RunoffParameters
from tools.verify_mountain_source_adapter import snapshot, assert_unchanged, write_json
from tools.verify_mountain_storm_forcing import check_frozen_compatibility, FROZEN
from tools.verify_mountain_storm_hru_scale import SOURCE, partition_bins

SCALES = ROOT / "verification/mountain-storm-hru-scale/run-20261001T072822219893Z"
SPATIAL = ROOT / "verification/mountain-storm-review/run-20261001T072059959238Z"


def read_arrays(path, digest):
    arrays = checked_archive(path, expected_sha256=digest, max_bytes=768*1024*1024)
    arrays.pop("manifest")
    return arrays


def summarize(arrays, lake_nodes):
    flow = arrays["total_boundary_volume_m3"]/900.
    soil = ((arrays["runoff_soil_mm"]+arrays["runoff_fast_mm"]+arrays["runoff_slow_mm"])
            * arrays["runoff_area_m2"]/1000.).sum(axis=1)
    storage = soil+arrays["storage_m3"].sum(axis=1)
    rain = arrays["runoff_rain_volume_m3"].sum(axis=1)+arrays["surface_rain_volume_m3"].sum(axis=1)
    losses = arrays["runoff_et_volume_m3"].sum(axis=1)+arrays["lake_loss_volume_m3"].sum(axis=1)
    residual = rain-losses-arrays["total_boundary_volume_m3"]-np.diff(storage)
    return {"peak_q_m3_s": float(flow.max()), "peak_interval_start_h": float(flow.argmax()*.25),
        "total_boundary_volume_m3": float(arrays["total_boundary_volume_m3"].sum()),
        "lake_max_stage_m": {str(node): float(arrays["lake_stage_m"][:, node].max()) for node in lake_nodes},
        "water_account": {"rain_m3": float(rain.sum()), "et_and_lake_losses_m3": float(losses.sum()),
            "initial_storage_m3": float(storage[0]), "final_storage_m3": float(storage[-1]),
            "boundary_out_m3": float(arrays["total_boundary_volume_m3"].sum()),
            "whole_duration_residual_m3": float(rain.sum()-losses.sum()-arrays["total_boundary_volume_m3"].sum()-storage[-1]+storage[0]),
            "max_step_residual_m3": float(np.abs(residual).max()), "sum_abs_step_residual_m3": float(np.abs(residual).sum())}}


def compare(new, old):
    return {"peak_q_difference_m3_s": new["peak_q_m3_s"]-old["peak_q_m3_s"],
        "peak_q_difference_percent": 100*(new["peak_q_m3_s"]/old["peak_q_m3_s"]-1),
        "peak_time_difference_h": new["peak_interval_start_h"]-old["peak_interval_start_h"],
        "boundary_volume_difference_m3": new["total_boundary_volume_m3"]-old["total_boundary_volume_m3"],
        "boundary_volume_difference_percent": 100*(new["total_boundary_volume_m3"]/old["total_boundary_volume_m3"]-1),
        "lake_max_stage_difference_m": {node: level-old["lake_max_stage_m"][node] for node, level in new["lake_max_stage_m"].items()},
        "water_account_difference": {key: value-old["water_account"][key] for key, value in new["water_account"].items()}}


def export_playback(destination):
    import tools.verify_mountain_storm_review as review

    original_source, original_page = review.SOURCE, review.PAGE
    page = original_page.replace("300m", "60m").replace("15 HRU", "208 HRU").replace(
        "5.16334110", "0.98489290")
    page = page.replace('<input id="time"', '<button id="play" type="button">播放</button><input id="time"')
    page = page.replace("document.getElementById('case').onchange=render;", """
let playbackTimer=null;
function pausePlayback(){if(playbackTimer!==null){clearInterval(playbackTimer);playbackTimer=null}document.getElementById('play').textContent='播放'}
document.getElementById('play').onclick=()=>{if(playbackTimer!==null){pausePlayback();return}const slider=document.getElementById('time');if(+slider.value>=+slider.max)slider.value=0;document.getElementById('play').textContent='暂停';render();playbackTimer=setInterval(()=>{slider.value=Math.min(+slider.max,+slider.value+1);render();if(+slider.value>=+slider.max)pausePlayback()},150)};
document.addEventListener('visibilitychange',()=>{if(document.hidden)pausePlayback()});
document.getElementById('case').onchange=render;"""
    )
    review.SOURCE, review.PAGE = destination, page
    try:
        review.export_review(destination / "review")
        consumer_path = destination / "review/weather-water-consumer.json"
        data = json.loads(consumer_path.read_text(encoding="utf-8"))
        data["geometry"]["HRU_absolute_60m_bins"] = data["geometry"].pop("HRU_absolute_300m_bins")
        data["HRU_bin_m"] = 60.
        data["lake_rain_limitation"] = "60m mixed HRU mean applied to lake footprint; max error 0.98489290 mm/h"
        data["comparison_300m"] = {}
        for name in ("eastward", "westward", "no_rain"):
            old_report = json.loads((SOURCE / "report.json").read_text(encoding="utf-8"))
            digest = old_report["no_rain_baseline"]["archive_sha256"] if name == "no_rain" else old_report["cases"][name]["coupling_sha256"]
            arrays = read_arrays(SOURCE / f"pressure_mountain-{name}-coupling.npz", digest)
            data["comparison_300m"][name] = {"outlet_q_m3_s": (arrays["total_boundary_volume_m3"]/900).tolist(),
                "lake_storage_m3": arrays["storage_m3"][:, data["geometry"]["lake_nodes"]].sum(axis=1).tolist()}
        from terrain_pipeline.mountain_source_adapter import publish_bytes

        final_directory = destination / "play-review"
        write_json(final_directory / "weather-water-consumer.json", data)
        page = page.replace("HRU_absolute_300m_bins", "HRU_absolute_60m_bins").replace("bin[0]*300", "bin[0]*60").replace("bin[1]*300", "bin[1]*60").replace("300*scale", "60*scale")
        page = page.replace("同轴方向对照：", "同轴方向对照：实线60m，虚线原300m；")
        page = page.replace("ctx.stroke();ctx.fillStyle=colors[index];ctx.fillText(n,800+index*130,18)",
            "ctx.stroke();ctx.setLineDash([5,4]);ctx.beginPath();data.comparison_300m[n][key].forEach((v,j)=>{const hour=(states?j:j+1)*.25,x=50+hour/72*1150,y=220-v/maximum*185;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=colors[index];ctx.fillText(n,800+index*130,18)")
        page = page.replace("Math.max(...data.cases[n][key])", "Math.max(...data.cases[n][key],...data.comparison_300m[n][key])")
        publish_bytes(final_directory / "review.html", page.encode("utf-8"))
        review.browser_audit(final_directory)
        audit_playback(final_directory)
    finally:
        review.SOURCE, review.PAGE = original_source, original_page


def audit_playback(directory):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True, args=["--disable-gpu"])
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/review.html", wait_until="networkidle")
            page.wait_for_function("window.reviewReady===true")
            page.click("#play")
            page.wait_for_function("window.currentReviewFrame.state_index>48")
            page.click("#play")
            paused = page.evaluate("window.currentReviewFrame.state_index")
            page.wait_for_timeout(400)
            if page.evaluate("window.currentReviewFrame.state_index") != paused:
                raise ValueError("pause did not stop playback")
            page.locator("#time").evaluate("slider=>{slider.value=287;slider.dispatchEvent(new Event('input'))}")
            page.click("#play")
            page.wait_for_function("window.currentReviewFrame.state_index===288 && document.getElementById('play').textContent==='播放'")
            page.click("#play")
            page.wait_for_function("window.currentReviewFrame.state_index<288")
            page.click("#play")
            if errors:
                raise ValueError("playback page errors")
            write_json(directory / "browser-playback.json", {"play_advances": True, "pause_stops": True,
                "stops_at_72h": True, "restarts_from_initial": True, "pageerrors": errors})
            browser.close()
    finally:
        server.shutdown()


def verify(destination):
    if destination.exists():
        raise FileExistsError(destination)
    frozen = snapshot()
    directories = (SOURCE, SCALES, SPATIAL)
    old_hashes = {str(path): file_sha256(path) for directory in directories for path in directory.iterdir() if path.is_file()}
    a_report = json.loads((FROZEN / "report.json").read_text(encoding="utf-8"))
    compatibility = check_frozen_compatibility(a_report["delivery_source_sha256"])
    write_json(destination / "frozen-before.json", {"source_snapshot": frozen, "old_artifacts": old_hashes})
    try:
        old_report = json.loads((SOURCE / "report.json").read_text(encoding="utf-8"))
        scale_report = json.loads((SCALES / "report.json").read_text(encoding="utf-8"))
        source = load_legacy_source("pressure_mountain", boundary_policy="all_edges_open")
        geometry_path = FROZEN / "pressure_mountain-geometry.npz"
        if file_sha256(geometry_path) != a_report["samples"]["pressure_mountain"]["geometry_archive_sha256"]:
            raise ValueError("frozen geometry external SHA mismatch")
        geometry = load_mountain_geometry(geometry_path, trusted_height=source["arrays"]["height_m"],
            source_binding={"source_identity": source["identity_sha256"]})
        topology, selection, lake_nodes = build_group_topology(source, geometry, 1378)
        for key, actual in (("source_identity", source["identity_sha256"]),
                            ("selection_identity", selection["identity_sha256"]),
                            ("geometry_identity", topology["geometry_identity"])):
            if old_report[key] != actual or scale_report[key] != actual:
                raise ValueError("same source/selection/geometry required")
        mask = selection["arrays"]["mask"]
        lake_mask = mask & (geometry["arrays"]["lake_id"] > 0)
        owner, partition = partition_bins(mask, lake_mask, source["metadata"]["origin_m_xz"], 30., 60.)
        if partition["HRUs"] != 208 or partition["pure_lake_merges"]:
            raise ValueError("predeclared 208 mixed HRUs required")
        from terrain_pipeline.mountain_runoff_routing import preflight

        nodes = int(topology["node_downstream"].size)
        cells = int(source["arrays"]["height_m"].size)
        resource_request = {"steps": 288, "cells": cells, "HRUs": 208, "nodes": nodes,
            "work_units": 288*nodes*209+cells*8,
            "estimated_bytes": 8*(12*cells+288*208+8*289*nodes),
            "frozen_MAX_WORK": 30000000, "no_budget_override": True}
        write_json(destination / "resource-precheck.json", resource_request)
        preflight(288, cells, 208, nodes)
        result = {"status": "60m_HRU_real_paired_lake_river_coupling", "group": 1378,
            "source_identity": source["identity_sha256"], "selection_identity": selection["identity_sha256"],
            "geometry_identity": topology["geometry_identity"], "HRUs": 208, "HRU_bin_m": 60.,
            "area_m2": 674100., "duration_h": 72., "dt_s": 900., "cases": {}, "comparisons_300m": {},
            "geometry_compatibility_exception": compatibility, "gpu_inference_run": False,
            "only_changed_parameter": "absolute HRU bin 300m -> 60m; nonlinear soil aggregation also changes",
            "unchanged_parameters": {"initial_soil_mm": 135., "surface_rain": True, "lake_evaporation_mm_h": 0.,
                "storm_parameters": {name: old_report["cases"][name]["parameters"] for name in ("eastward", "westward")}},
            "resource_predeclaration": {"steps": 288, "HRUs": 208, "nodes": int(topology["node_downstream"].size),
                "runs": 3, "weather_generation": False, "coupling_archive_max_bytes": 768*1024*1024}}
        summaries, flows = {}, {}
        for name in ("no_rain", "eastward", "westward"):
            if name == "no_rain":
                rain = np.zeros((288, 208), np.float64)
                weather_digest = None
            else:
                weather_path = SCALES / f"60m-{name}-weather.npz"
                weather_digest = scale_report["scales"]["60"]["cases"][name]["weather_sha256"]
                weather = load_forcing(weather_path, expected_sha256=weather_digest, cell_owner=owner,
                    source_identity=source["identity_sha256"], selection_identity=selection["identity_sha256"])
                rain = weather["arrays"]["rain_mm_h"]
                from terrain_pipeline.mountain_source_adapter import publish_bytes

                publish_bytes(destination / f"{name}-weather.npz", weather_path.read_bytes())
            specs = group_lake_specs(source, geometry, topology, lake_nodes, steps=288)
            solved = couple_rainfall(source, topology, owner, rain, dt_s=900., geometry=geometry,
                selection=selection, lakes=specs, surface_rain=True, parameters=RunoffParameters(initial_soil_mm=135.))
            if "arrays" not in solved:
                if "lake_failure" in solved:
                    from terrain_pipeline.lake_routing import save_lake_routing

                    save_lake_routing(solved["lake_failure"], destination / f"{name}-failed-lake.npz")
                write_json(destination / f"{name}-failure.json", {key: value for key, value in solved.items() if key != "lake_failure"})
                raise ValueError("60m coupled case failed: "+name)
            path = destination / f"pressure_mountain-{name}-coupling.npz"
            save_coupling(path, solved)
            digest = file_sha256(path)
            cold = load_coupling(path, expected_sha256=digest, source=source, topology=topology,
                geometry=geometry, selection=selection)
            stats = validate_coupling(cold, source=source, topology=topology, geometry=geometry, selection=selection)
            summaries[name] = summarize(cold["arrays"], list(lake_nodes.values()))
            flows[name] = cold["arrays"]["total_boundary_volume_m3"]/900.
            old_digest = old_report["no_rain_baseline"]["archive_sha256"] if name == "no_rain" else old_report["cases"][name]["coupling_sha256"]
            old_summary = summarize(read_arrays(SOURCE / f"pressure_mountain-{name}-coupling.npz", old_digest), list(lake_nodes.values()))
            result["comparisons_300m"][name] = {"300m": old_summary, "60m": summaries[name],
                                               "difference_60m_minus_300m": compare(summaries[name], old_summary)}
            if name == "no_rain":
                result["no_rain_baseline"] = {"archive_sha256": digest, **summaries[name]}
            else:
                result["cases"][name] = {**stats, **summaries[name], "weather_sha256": weather_digest,
                    "coupling_sha256": digest, "dynamic_water_solved": True,
                    "parameters": old_report["cases"][name]["parameters"]}
        for name in ("eastward", "westward"):
            increment = flows[name]-flows["no_rain"]
            peak = int(np.argmax(increment[24:])+24)
            result["cases"][name]["storm_response"] = {"post_6h_increment_peak_m3_s": float(increment[peak]),
                "increment_peak_interval_start_h": peak*.25, "72h_increment_boundary_volume_m3": float(increment.sum()*900)}
        write_json(destination / "pressure_mountain-eastward-weather-consumer.json", {
            "HRU_bins_east_south": partition["representative_bins_east_south"], "HRU_bin_m": 60.})
        result["frozen_after"] = assert_unchanged(frozen)
        result["delivery_source_sha256"] = {name: file_sha256(ROOT / name) for name in (
            "terrain_pipeline/mountain_storm_forcing.py", "terrain_pipeline/mountain_lake_coupling.py",
            "tools/verify_mountain_storm_60m.py", "tools/verify_mountain_storm_hru_scale.py", "tools/verify_mountain_storm_review.py")}
        write_json(destination / "report.json", result)
        export_playback(destination)
        if any(file_sha256(Path(path)) != digest for path, digest in old_hashes.items()):
            raise RuntimeError("previous frozen artifacts changed")
        assert_unchanged(frozen)
        if compatibility != check_frozen_compatibility(a_report["delivery_source_sha256"]):
            raise RuntimeError("geometry compatibility changed")
        write_json(destination / "freeze-manifest.json", {"status": "frozen_60m_three_cases_and_playback",
            "old_artifacts_unchanged": True, "files_sha256": {str(path.relative_to(destination)): file_sha256(path)
                for path in destination.rglob("*") if path.is_file()}})
        return result
    except BaseException as error:
        write_json(destination / "failure.json", {"exception": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    destination = arguments.output or ROOT / "verification/mountain-storm-60m" / (
        "run-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    result = verify(destination)
    print(json.dumps({"directory": str(destination), "differences": {name: comparison["difference_60m_minus_300m"]
        for name, comparison in result["comparisons_300m"].items()}}, indent=2))
