"""Predeclared finite-window adaptive leaf acceptance against frozen v7 evidence."""

import argparse
import ast
import gc
import json
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
from terrain_pipeline.single_domain_fine_geometry import load_fine_geometry
from terrain_pipeline.single_domain_fine_io import load_fine_run
from terrain_pipeline.surface_adaptive_geometry import build_adaptive_geometry
from terrain_pipeline.surface_adaptive_refinement import anticipated_spacing_map
from terrain_pipeline.surface_adaptive_execution import advance_adaptive_surface
from terrain_pipeline.surface_adaptive_io import save_adaptive_run
from tools.run_single_domain_fine_stage import GATES, BUDGETS, FLAGS, json_record, freeze_execution_code, resources

SOURCE_INDEX = ROOT / "verification/single-domain-fine/stage-v7-20261004-01/index.json"
SOURCE_SHA = "ab7b5f64c1ce6bb8460070e4639062e6ce8b73ce32546184afd25e4eaefc35ca"
DEFINITIONS = (("dry-rain-root4",4,.1,"rain","dry-rain-1m"),
    ("zero-source-lake-root4",4,.1,"zero_source_lake","lake-at-rest-1m"),
    ("tailwater-baseline-root4",4,.025,"baseline","tailwater-baseline-1m"),
    ("tailwater-rise-root1",1,.025,"rise","tailwater-rise-1m"),
    ("tailwater-rise-root1-half-dt",1,.0125,"rise","tailwater-rise-1m-half-dt"),
    ("tailwater-rise-root2",2,.025,"rise","tailwater-rise-1m"),
    ("tailwater-rise-root4",4,.025,"rise","tailwater-rise-1m"))


def dependency_files():
    """Pin the complete repository-local import closure, including dormant imports."""
    pending = [Path(__file__).relative_to(ROOT)]
    found = set()
    while pending:
        name = pending.pop().as_posix()
        if name in found:
            continue
        found.add(name)
        tree = ast.parse((ROOT/name).read_text(encoding="utf-8-sig"))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        for module in modules:
            target = Path(*module.split(".")).with_suffix(".py")
            if (ROOT/target).is_file():
                pending.append(target)
    return sorted(found)


def compare(first, second, label):
    depth = float(np.max(np.abs(first-second)))
    v1,v2 = first.sum(axis=(1,2)),second.sum(axis=(1,2))
    volume = float(np.max(np.abs(v1-v2)/np.maximum(v2,1e-12)))
    return dict(label=label,maximum_saved_depth_difference_m=depth,
        maximum_relative_surface_volume_difference=volume,
        passed=depth<=GATES["max_saved_depth_difference_m"] and volume<=GATES["max_relative_surface_volume_difference"])


def run(output):
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True,exist_ok=False)
    started = time.monotonic()
    highwater = dict(combined_output_and_work_bytes=0,largest_file_bytes=0,peak_rss_bytes=0,
        peak_private_bytes=0,observation_count=0,combined_peak_elapsed_s=0.,largest_file_peak_elapsed_s=0.)

    def observe_resources():
        observation = resources(started,output)
        highwater["observation_count"] += 1
        for target,source in (("combined_output_and_work_bytes","output_bytes"),("largest_file_bytes","largest_artifact_bytes")):
            if observation[source]>highwater[target]:
                highwater[target] = observation[source]
                highwater["combined_peak_elapsed_s" if target=="combined_output_and_work_bytes" else "largest_file_peak_elapsed_s"] = observation["elapsed_s"]
        for name in ("peak_rss_bytes","peak_private_bytes"):
            highwater[name] = max(highwater[name],observation[name])
        return observation
    if file_sha256(SOURCE_INDEX)!=SOURCE_SHA:
        raise ValueError("fixed uniform v7 source index pin mismatch")
    source = json.loads(SOURCE_INDEX.read_text(encoding="utf-8"))
    source_pin = dict(path=str(SOURCE_INDEX),expected_sha256=SOURCE_SHA)
    source_report = source["report"]
    if file_sha256(source_report["path"])!=source_report["expected_sha256"]:
        raise ValueError("fixed uniform v7 report pin mismatch")
    code = {name:file_sha256(ROOT/name) for name in dependency_files()}
    code_records = freeze_execution_code(output,code)
    declaration = json_record(output/"predeclared.json",dict(schema="single-domain-adaptive-predeclared-v1",
        source_v7_index=source_pin,source_v7_report=source_report,duration_s=120.,forcing_interval_s=30.,
        cases=[dict(name=n,root_spacing_m=r,max_dt_s=dt,initial_kind=k,source_case=s) for n,r,dt,k,s in DEFINITIONS],
        gates=GATES,budgets=BUDGETS,halo_m=8,activity_depth_m=1e-8,
        zero_source_lake="Closed boundaries and explicitly zero hydraulic source; original default soil release remains in other cases.",
        history_storage="Complete lossless history; 8MiB RAM cap, 128MiB workspace segments, immutable saved bindings release only fully archived segment prefixes. Every append/write/transfer measures simultaneous temporary+published bytes.",
        canonical_spacing_m=1,adaptive_spacings_m=[1,2,4],uniform_coarse_convergence_claim=False,
        source_uniform_coarse_gates_passed=False,code_sha256=code,code_records=code_records,
        comparison_scope="All five saved times and all cells of selected 240m window; adaptive inventory vs independent saved uniform1m.",**FLAGS))
    cases,depths = {},{}
    bed_pin = source["cases"]["tailwater-rise-1m"]["bed"]
    bed = load_fine_geometry(**bed_pin)
    height = bed["arrays"]["canonical_bed_center_m"]
    rows,columns = height.shape
    reference = None
    observations = []
    try:
        for name,root_spacing,dt,kind,source_name in DEFINITIONS:
            before = time.monotonic()
            saved = load_fine_run(**source["cases"][source_name]["run"],bed=bed)
            forcing = saved["forcing"]["arrays"]["local_q_m3_s"].reshape(4,rows,columns).copy()
            tailwater = saved["forcing"]["arrays"]["boundary_stage_m"].copy()
            initial = saved["states"]["arrays"]["initial_depth_m"].reshape(rows,columns).copy()
            boundary_kind = saved["geometry"]["arrays"]["boundary_kind"].copy()
            if kind=="zero_source_lake":
                forcing.fill(0.)
                boundary_kind.fill(0)
            if source_name=="tailwater-rise-1m-half-dt":
                reference = saved["states"]["arrays"]["depth_m"].copy()
            del saved
            requested = anticipated_spacing_map(initial,max_leaf_spacing_m=root_spacing,halo_m=8,
                activity_depth_m=1e-8,canonical_forcing_m3_s=forcing[0],forcing_prediction_dt_s=dt,
                boundary_kind=boundary_kind,tailwater_m=tailwater[0],canonical_bed_m=height)
            geometry = build_adaptive_geometry(height,requested,origin_m_xz=bed["metadata"]["origin_m_xz"],boundary_kind=boundary_kind)
            budget = SurfaceBudget(max_dt_s=dt,max_cells=65536,max_snapshots=6,max_duration_s=120.,
                max_wall_s=BUDGETS["max_wall_s"]-(time.monotonic()-started),max_depth_m=10.,max_bytes=BUDGETS["max_artifact_bytes"])
            print(f"running {name}, leaves={geometry['metadata']['leaf_counts']}, dt={dt}",flush=True)
            result = advance_adaptive_surface(geometry,initial_depth_m=initial,forcing_interval_s=30.,intervals=4,
                forcing_provider=lambda i:forcing[i],boundary_stage_provider=lambda i:tailwater[i],budget=budget,
                dynamic_refinement=True,halo_m=8,activity_depth_m=1e-8,history_directory=output/"working-history"/name,resource_observer=observe_resources)
            run_pin = save_adaptive_run(output/name,result,forcing_m3_s=forcing,tailwater_m=tailwater,
                forcing_interval_s=30.,budget=budget,source_record=source["cases"][source_name]["run"],
                code_sha256=code,code_records=code_records,resource_observer=observe_resources)
            observe_resources()
            depths[name] = np.asarray([s["canonical_depth_m"] for s in result["snapshots"]])
            cases[name] = dict(bed=bed_pin,run=run_pin,initial_kind=kind,max_dt_s=dt,root_spacing_m=root_spacing,
                solver=result["metadata"],snapshot_leaf_counts=[s["leaf_counts"] for s in result["snapshots"]],
                snapshot_leaf_areas_m2=[s["leaf_area_m2"] for s in result["snapshots"]],
                source_v7_case=source_name,case_wall_s=time.monotonic()-before)
            del result,geometry
            gc.collect()
            observations.append(observe_resources())
            print(f"saved {name}, wall={cases[name]['case_wall_s']:.3f}s",flush=True)
        temporal = compare(depths["tailwater-rise-root1"],depths["tailwater-rise-root1-half-dt"],"same root1 temporal .025/.0125s")
        temporal["actual_temporal_resolution_changed"] = cases["tailwater-rise-root1-half-dt"]["solver"]["substeps"]>cases["tailwater-rise-root1"]["solver"]["substeps"]
        temporal["passed"] &= temporal["actual_temporal_resolution_changed"]
        comparisons = [temporal]+[compare(depths[f"tailwater-rise-root{r}"],reference,f"adaptive root{r} vs saved uniform1m halfdt") for r in (1,2,4)]
        lake = float(np.max(np.abs(depths["zero-source-lake-root4"]-depths["zero-source-lake-root4"][0])))
        response = depths["tailwater-rise-root4"][-1]-depths["tailwater-baseline-root4"][-1]
        imported = cases["tailwater-rise-root4"]["solver"]["boundary_input_m3"]
        scenarios = dict(zero_source_lake=dict(max_depth_change_m=lake,passed=lake<=GATES["max_lake_depth_change_m"]),
            controlled_tailwater=dict(max_depth_increase_m=float(response.max()),positive_response_cells=int(np.sum(response>GATES["minimum_tailwater_response_m"])),
                imported_volume_m3=imported,passed=bool(response.max()>GATES["minimum_tailwater_response_m"] and imported>GATES["minimum_tailwater_import_m3"])))
        report = dict(schema="single-domain-adaptive-stage-report-v1",predeclared=declaration,source_v7_index=source_pin,
            source_v7_report=source_report,cases=cases,comparisons=comparisons,scenario_gates=scenarios,
            resource_observations=observations,resources=observe_resources(),resource_highwater=highwater,uniform_coarse_convergence_claim=False,
            source_uniform_coarse_gates_passed=False,all_predeclared_gates_passed=all(c["passed"] for c in comparisons) and all(c["passed"] for c in scenarios.values()),**FLAGS)
        report_pin = json_record(output/"report.json",report)
        index = dict(report,report=report_pin,schema="single-domain-adaptive-stage-index-v1")
        pin = json_record(output/"index.json",index)
        print(json.dumps(dict(index=pin,comparisons=comparisons,scenario_gates=scenarios)),flush=True)
    except Exception as error:
        json_record(output/"failure.json",dict(error_type=type(error).__name__,error=str(error),elapsed_s=time.monotonic()-started,cases=cases,predeclared=declaration,resource_highwater=highwater))
        raise


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    run(parser.parse_args().output)
