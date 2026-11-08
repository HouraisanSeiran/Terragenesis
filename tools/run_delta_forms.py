"""Single-factor finite engineering delta forms, with resumable cold checkpoints."""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_delta_fv import FVDeltaConfig, initialize, advance, save, load
from tools.run_delta_distributary_trial import ORIGIN, WORLD_SEED, stage_report

CASES = {
    "slope": "Sloping marine bed",
    "wide_mouth": "150 m river mouth",
    "tide": "0.3 m engineering tide",
    "wave": "0.3 m incident Airy waves",
}


def initial_product(case, max_wall_s=240.):
    if case not in CASES:
        raise ValueError("unknown delta form: " + case)
    bed = np.full((32, 48), -.5)
    if case == "slope":
        bed[:, :36] = np.linspace(-1.5, -.5, 36)
    bed[:, 36:] = .8
    undug = bed.copy()
    mouth = slice(14, 19) if case == "wide_mouth" else slice(15, 18)
    bed[mouth, 36:] = -1.
    ocean = np.indices(bed.shape)[1] < 36
    floor = bed.copy()
    floor[ocean] -= .6
    config = FVDeltaConfig(coupling_interval_s=10., max_hydro_dt_s=3., max_wall_s=max_wall_s)
    if case == "tide":
        config = replace(config, tide_amplitude_m=.3, tide_period_s=43200.,
                         tide_phase_rad=-2.*math.pi*300./43200.)
    if case == "wave":
        config = replace(config, bedload=replace(config.bedload, wave_height_m=.3,
                         wave_period_s=5., wave_direction_xz=(1, 0)))
    product = initialize(bed, ocean, [16*48+46], origin_m_xz=ORIGIN,
        source_world_identity="seed20261020", source_identity="declared-finite-delta-form-v1:"+case,
        floor_m=floor, config=config)
    return product, float((undug-bed).sum()*900.)


def sea_stage(metadata):
    config = metadata["config"]
    return config["sea_mean_m"] + config["tide_amplitude_m"]*math.sin(
        2.*math.pi*metadata["physical_time_s"]/config["tide_period_s"]+config["tide_phase_rad"])


def form_report(product):
    report = stage_report(product, 100.)
    for key in ("bars", "local_material_distributary_passed", "local_bar_bypass_passed"):
        report.pop(key)
    report["distributary_classification"] = "not_evaluated"
    a, m = product["arrays"], product["metadata"]
    delta = a["bed_m"]-a["initial_bed_m"]
    ocean = a["ocean_mask"]
    land = ~ocean & (a["initial_bed_m"] > 0.)
    floor_eligible = a["initial_bed_m"]-a["floor_m"] > 1.e-9
    area = m["spacing_m"]**2
    # Areas use an explicit 1 mm threshold, separately from signed bulk volumes.
    report.update(sea_stage_m=sea_stage(m), growth_time_s=max(0., m["physical_time_s"]-300.),
        net_bed_bulk_change_m3=float(delta.sum()*area),
        deposition_bulk_m3=float(np.maximum(delta, 0.).sum()*area),
        erosion_bulk_m3=float(np.maximum(-delta, 0.).sum()*area),
        ocean_deposition_bulk_m3=float(np.maximum(delta[ocean], 0.).sum()*area),
        ocean_erosion_bulk_m3=float(np.maximum(-delta[ocean], 0.).sum()*area),
        deposition_area_m2=float(np.count_nonzero(delta > .001)*area),
        erosion_area_m2=float(np.count_nonzero(delta < -.001)*area),
        morphology_area_threshold_m=.001,
        substrate_floor_hit_cells=int(np.count_nonzero(floor_eligible & (a["bed_m"]-a["floor_m"] <= 1.e-8))),
        land_flooded_cells=int(np.count_nonzero(land & (a["depth_m"] > m["config"]["bedload"]["dry_depth_m"]))),
        maximum_land_water_depth_m=float(a["depth_m"][land].max()),
        completed_coupling_steps=m["completed_coupling_steps"], rejected_coupling_steps=m["rejected_coupling_steps"])
    dt = m["last_coupling_interval_s"]
    boundary = a["boundary_last_water_transfer_m3"][a["boundary_kind"] == 2]
    report["last_interval_sea_net_export_q_m3_s"] = float(boundary.sum()/dt) if dt else 0.
    report["last_interval_duration_s"] = dt
    report["interpretation"] = "Finite uncalibrated engineering morphology; no tidal distributary classification; Airy waves mobilize sediment without radiation-stress-driven coastal currents."
    return report


def schedule(smoke=False):
    if smoke:
        return [("warmup", 300.)]
    times = {0., *np.arange(5400., 86401., 5400.), 21.*3600., 22.*3600., 23.*3600.}
    stages = [("warmup", 300.)]
    for seconds in sorted(times-{0.}):
        hour = seconds/3600.
        label = str(int(hour)) if hour.is_integer() else str(hour).replace(".", "p")
        stages.append(("growth_"+label+"h", float(300.+seconds)))
    return stages


def write_json(path, value):
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


def forcing_record(case, name, start, end):
    duration = end-start
    return {"id": case+"_"+name,
        "source": "Declared engineering upstream supply; no sea sediment input",
        "time_start_s": start, "time_end_s": end,
        "water_m3": 100.*duration, "solid_m3": 0. if name == "warmup" else duration}


def save_stage(directory, name, product, previous=None, runtime=0.):
    path = directory/(name+".npz")
    save(path, product)
    sha = file_sha256(path)
    cold = load(path, expected_sha256=sha)
    report = form_report(cold)
    report.update(runtime_s=runtime, sha256=sha, cold_identity_sha256=cold["identity_sha256"],
                  state_path=str(path.resolve()))
    a, m = cold["arrays"], cold["metadata"]
    record = {"time_s": m["physical_time_s"], "growth_time_s": max(0., m["physical_time_s"]-300.),
              "sea_stage_m": sea_stage(m), **m["ledger"]}
    if previous is not None:
        old_a, old_m = previous["arrays"], previous["metadata"]
        duration = m["physical_time_s"]-old_m["physical_time_s"]
        record.update(interval_duration_s=duration,
            interval_sea_import_m3=m["ledger"]["sea_import_m3"]-old_m["ledger"]["sea_import_m3"],
            interval_water_export_m3=m["ledger"]["water_export_m3"]-old_m["ledger"]["water_export_m3"])
        record["interval_net_internal_q_m3_s"] = ((a["internal_water_transfer_m3"]-old_a["internal_water_transfer_m3"])/duration).tolist()
        report["interval_mean_sea_gross_import_q_m3_s"] = record["interval_sea_import_m3"]/duration
        report["interval_mean_sea_gross_export_q_m3_s"] = record["interval_water_export_m3"]/duration
        report["interval_duration_s"] = duration
        report["interval_net_internal_q_m3_s"] = record["interval_net_internal_q_m3_s"]
    write_json(directory/(name+".json"), report)
    entry = {"path": str(path.resolve()), "sha256": sha,
             "report_path": str((directory/(name+".json")).resolve()),
             "physical_time_s": m["physical_time_s"], "growth_time_s": report["growth_time_s"]}
    return cold, entry, report, record


def baseline_entry(parent, report_path):
    old = json.loads(report_path.read_text(encoding="utf-8"))["cases"]["flat"]
    result = {"label_zh": "Flat bed baseline (reused)", "stages": {}, "reports": {},
              "source_ledger": {k: v for k, v in old.items() if k != "stages"},
              "evidence_origin": str(parent.resolve()), "authoritative_report": str(report_path.resolve()),
              "reused_without_advancing": True}
    for name in ("initial", "warmup", "growth_6h", "growth_12h", "growth_24h"):
        path = parent/"flat"/(name+".npz")
        sha = old["stages"][name]["sha256"]
        product = load(path, expected_sha256=sha)
        result["stages"][name] = {"path": str(path.resolve()), "sha256": sha,
            "physical_time_s": product["metadata"]["physical_time_s"],
            "growth_time_s": max(0., product["metadata"]["physical_time_s"]-300.)}
        result["reports"][name] = form_report(product)
    return result


def run(args):
    args.output.mkdir(parents=True, exist_ok=args.resume)
    manifest_path = args.output/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if args.resume and manifest_path.exists() else {
        "schema": "finite-delta-forms-v1", "world_seed": WORLD_SEED, "spacing_m": 30., "shape_zx": [32,48],
        "origin_m_xz": ORIGIN, "cpu_only": True, "noise": None,
        "forcing": {"warmup_s": 300., "growth_s": 86400., "water_q_m3_s": 100., "growth_solid_m3_s": 1.},
        "cases": {}}
    if args.baseline and "flat" not in manifest["cases"]:
        manifest["cases"]["flat"] = baseline_entry(args.baseline, args.baseline_report or args.baseline/"summary.json")
    for case in args.cases:
        directory = args.output/case
        directory.mkdir(exist_ok=args.resume)
        entry = manifest["cases"].get(case)
        if entry:
            last_name = list(entry["stages"])[-1]
            latest = entry["stages"][last_name]
            product = load(Path(latest["path"]), expected_sha256=latest["sha256"])
            records = json.loads((directory/"boundary_timeseries.json").read_text(encoding="utf-8"))
        else:
            product, excavation = initial_product(case, args.max_wall_s)
            entry = {"label_zh": CASES[case], "stages": {}, "reports": {}, "status": "running",
                "config": product["metadata"]["config"], "source_ledger": {
                    "initial_substrate_solid_m3": product["metadata"]["initial_bed_solid_m3"],
                    "initial_suspended_solid_m3": 0., "initial_water_m3": product["metadata"]["initial_water_m3"],
                    "excavated_bulk_m3": excavation, "excavated_solid_equivalent_m3": excavation*.65,
                    "excavation_semantics": "Initial feeder excavation removed before simulation; not supplied sediment.",
                    "substrate_semantics": "Declared 0.6 m finite marine sand cover; marine edge fixed and excluded from erodible stock."}}
            product, checkpoint, report, record = save_stage(directory, "initial", product)
            entry["stages"]["initial"], entry["reports"]["initial"] = checkpoint, report
            records = [record]
            manifest["cases"][case] = entry
        def persist():
            series = directory/"boundary_timeseries.json"
            write_json(series, records)
            entry["boundary_timeseries"] = {"path": str(series.resolve()), "sha256": file_sha256(series)}
            write_json(manifest_path, manifest)
            write_json(args.output/"summary.json", manifest)
        persist()
        for name, end in schedule(args.smoke):
            if end <= product["metadata"]["physical_time_s"]:
                continue
            previous = product
            start = product["metadata"]["physical_time_s"]
            duration = end-start
            started = time.monotonic()
            try:
                product = advance(product, [forcing_record(case, name, start, end)])
                product, checkpoint, report, record = save_stage(directory, name, product, previous, time.monotonic()-started)
            except Exception as error:
                entry.update(status="failed", failure={"stage": name, "error_type": type(error).__name__,
                    "message": str(error), "last_complete_time_s": previous["metadata"]["physical_time_s"],
                    "elapsed_s": time.monotonic()-started})
                persist()
                raise
            entry["stages"][name], entry["reports"][name] = checkpoint, report
            records.append(record)
            entry.pop("failure", None)
            entry["status"] = "running"
            persist()
            print(json.dumps({"case": case, "stage": name, "runtime_s": report["runtime_s"],
                "ocean_dry_cells": report["ocean_dry_cells"], "solid_residual_m3": report["solid_budget_residual_m3"]}), flush=True)
        entry["status"] = "smoke_complete" if args.smoke else "complete"
        persist()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    parser.add_argument("--max-wall-s", type=float, default=240.)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
