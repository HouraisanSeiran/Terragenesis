"""Run fixed real-TD same-bed fine scenarios and predeclared refinement gates."""

import argparse
from dataclasses import asdict
import gc
import json
import os
from pathlib import Path
import sys
import time

THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")
for name in THREADS:
    os.environ.setdefault(name, "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.single_domain_fine_geometry import (build_fine_geometry, build_fine_water_frame,
    coarsen_cell_field, save_fine_geometry, save_fine_water_frame)
from terrain_pipeline.single_domain_fine_hydraulics import run_fine_hydraulics
from terrain_pipeline.single_domain_fine_io import save_fine_run
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget

SOURCE = dict(path=str(ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"),
              expected_sha256="36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
              expected_identity="cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998")
WINDOW = [150, 158, 241, 249]
CODE_FILES = ("terrain_pipeline/single_domain_fine_geometry.py", "terrain_pipeline/single_domain_fine_hydraulics.py",
              "terrain_pipeline/single_domain_fine_io.py", "terrain_pipeline/regional_surface_hydraulics.py",
              "terrain_pipeline/regional_surface_hydraulics_accelerated.py", "terrain_pipeline/rainfall_runoff.py",
              "tools/run_single_domain_fine_stage.py")
FLAGS = dict(hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
GATES = dict(max_saved_depth_difference_m=.01, max_relative_surface_volume_difference=.01,
             max_lake_depth_change_m=1e-9, minimum_tailwater_import_m3=1e-8,
             minimum_tailwater_response_m=1e-6)
BUDGETS = dict(max_memory_bytes=1024**3, max_artifact_bytes=256*1024**2,
               max_output_bytes=2*1024**3, max_wall_s=1800)


def json_record(path, value):
    publish_bytes(path, (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return dict(path=str(path.resolve()), expected_sha256=file_sha256(path))


def record(path, bundle):
    return dict(path=str(path.resolve()), expected_sha256=file_sha256(path), expected_identity=bundle["identity_sha256"])


def freeze_execution_code(output, code):
    records = {}
    for name, digest in code.items():
        original = ROOT / name
        target = output / "execution-code" / name
        publish_bytes(target, original.read_bytes())
        if file_sha256(target) != digest or file_sha256(original) != digest:
            raise ValueError("execution code changed while freezing provenance")
        records[name] = dict(path=str(target.resolve()), expected_sha256=digest)
    return records


def backend_code_files(backend):
    files = list(CODE_FILES)
    if backend in ("shallow_water", "shallow_water_subgrid", "shallow_water_subgrid_manning", "shallow_water_subgrid_manning_accelerated"):
        files.extend(("terrain_pipeline/single_domain_shallow_water.py",
                      "terrain_pipeline/single_domain_shallow_water_support.py"))
    if backend in ("shallow_water_subgrid", "shallow_water_subgrid_manning", "shallow_water_subgrid_manning_accelerated"):
        files.extend(("terrain_pipeline/single_domain_shallow_water_v3.py",
                      "terrain_pipeline/single_domain_shallow_water_support_v3.py",
                      "terrain_pipeline/single_domain_shallow_water_execution.py"))
    if backend in ("shallow_water_subgrid_manning", "shallow_water_subgrid_manning_accelerated"):
        files.extend(("terrain_pipeline/single_domain_shallow_water_v7.py",
                      "terrain_pipeline/single_domain_shallow_water_support_v7.py",
                      "terrain_pipeline/single_domain_shallow_water_execution_v7.py"))
    if backend == "shallow_water_subgrid_manning_accelerated":
        files.append("terrain_pipeline/single_domain_shallow_water_accelerated_v7.py")
    return files


def resources(started, output):
    memory = psutil.Process().memory_info()
    files = [path for path in output.rglob("*") if path.is_file()]
    observation = dict(peak_rss_bytes=int(getattr(memory, "peak_wset", memory.rss)),
                       peak_private_bytes=int(getattr(memory, "peak_pagefile", memory.vms)),
                       elapsed_s=time.monotonic()-started, output_bytes=sum(path.stat().st_size for path in files),
                       largest_artifact_bytes=max((path.stat().st_size for path in files), default=0))
    if (max(observation["peak_rss_bytes"], observation["peak_private_bytes"]) > BUDGETS["max_memory_bytes"]
            or observation["elapsed_s"] > BUDGETS["max_wall_s"]
            or observation["output_bytes"] > BUDGETS["max_output_bytes"]
            or observation["largest_artifact_bytes"] > BUDGETS["max_artifact_bytes"]):
        raise RuntimeError("fine stage predeclared resource budget exceeded")
    return observation


def comparison(coarse_depth, fine_depth, factor, label):
    steps, rows, columns = coarse_depth.shape
    averaged = fine_depth.reshape(steps, rows, factor, columns, factor).mean(axis=(2, 4))
    differences = np.abs(coarse_depth - averaged)
    fine_volumes = fine_depth.sum(axis=(1, 2))
    coarse_volumes = coarse_depth.sum(axis=(1, 2))*factor**2
    relative = np.abs(coarse_volumes-fine_volumes)/np.maximum(fine_volumes, 1e-12)
    depth_error = float(differences.max(initial=0))
    volume_error = float(relative.max(initial=0))
    return dict(label=label, maximum_saved_depth_difference_m=depth_error,
                maximum_relative_surface_volume_difference=volume_error,
                passed=depth_error <= GATES["max_saved_depth_difference_m"]
                       and volume_error <= GATES["max_relative_surface_volume_difference"])


def run(output, *, backend="subgrid"):
    if any(os.environ.get(name) != "1" for name in THREADS):
        raise ValueError("all numerical thread environment settings must equal 1")
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    code_files = backend_code_files(backend)
    code = {name:file_sha256(ROOT / name) for name in code_files}
    code_records = freeze_execution_code(output, code)
    predeclared = dict(schema="single-domain-fine-predeclared-v1", source=SOURCE, native_window=WINDOW,
                       duration_s=120., forcing_interval_s=30., rain_pulse_mm_h=[40.,40.,0.,0.],
                       spacing_m=[1.,2.,4.], temporal_max_dt_s=[.025,.0125], gates=GATES, budgets=BUDGETS,
                       tailwater_rise_m=.5, code_sha256=code, code_records=code_records,
                       execution_backend=backend, python_version=sys.version, numpy_version=np.__version__,
                       cross_resolution_contract="coarse FV bed and initial water depth are area means of canonical 1m fields",
                       scope="full selected 240m window; not full 7.68km original domain or natural basin", **FLAGS)
    declaration = json_record(output / "predeclared.json", predeclared)
    try:
        hierarchy = load_basin_hierarchy(**SOURCE)
        beds = {}
        bed_records = {}
        for spacing in (1., 2., 4.):
            bed = build_fine_geometry(hierarchy, native_window=WINDOW, source_hierarchy_sha256=SOURCE["expected_sha256"], spacing_m=spacing)
            path = output / f"bed-{int(spacing)}m.npz"
            save_fine_geometry(path, bed)
            beds[spacing], bed_records[spacing] = bed, record(path, bed)
        lake_stage = float(np.quantile(beds[1.]["arrays"]["bed_center_m"], .65))
        canonical_initial_depth = np.maximum(lake_stage - beds[1.]["arrays"]["bed_center_m"], 0.)
        predeclared["initial_lake_stage_m"] = lake_stage
        boundary_declaration = json_record(output / "boundary-declaration.json", dict(initial_lake_stage_m=lake_stage,
            tailwater_schedule_m=[lake_stage, lake_stage+.5, lake_stage+.5, lake_stage+.5],
            boundary="prescribed stage on entire east face; all other faces closed", source_bed=bed_records[1.]))
        cases = {}
        depths = {}
        definitions = (("dry-rain-1m",1.,.1,"rain"), ("lake-at-rest-1m",1.,.1,"lake"),
                       ("tailwater-baseline-1m",1.,.0125,"baseline"), ("tailwater-rise-1m",1.,.025,"rise"),
                       ("tailwater-rise-1m-half-dt",1.,.0125,"rise"),
                       ("tailwater-rise-2m",2.,.025,"rise"), ("tailwater-rise-4m",4.,.025,"rise"))
        for name, spacing, dt, kind in definitions:
            bed = beds[spacing]
            height = bed["arrays"]["bed_center_m"]
            rows, columns = height.shape
            boundary_kinds = np.zeros(2*(rows+columns), np.int64)
            if kind in ("baseline", "rise"):
                boundary_kinds[rows:2*rows] = 2
            rain = np.zeros((4, rows, columns), np.float64)
            if kind == "rain":
                rain[:2] = 40.
            if kind == "rain":
                initial = np.zeros(height.shape, dtype=np.float64)
            elif spacing == 1.:
                initial = canonical_initial_depth.copy()
            else:
                initial = coarsen_cell_field(canonical_initial_depth, factor=int(spacing))
            stages = np.full((4, len(boundary_kinds)), lake_stage, np.float64)
            if kind == "rise":
                stages[1:, rows:2*rows] += .5
            budget = SurfaceBudget(max_dt_s=dt, max_cells=65536, max_snapshots=6, max_duration_s=120., max_wall_s=1800., max_depth_m=10.)
            print(f"running {name}: {rows}x{columns}, max_dt={dt}s", flush=True)
            result = run_fine_hydraulics(bed, rain_mm_h=rain, boundary_stage_m=stages,
                forcing_interval_s=30., boundary_kind=boundary_kinds, initial_depth_m=initial,
                budget=budget, backend=backend)
            run_record = save_fine_run(output/name, result, bed_record=bed_records[spacing],
                code_sha256=code, code_records=code_records)
            frames = []
            frame_directory = output / name / "frames"
            frame_directory.mkdir()
            for state_index in range(5):
                frame = build_fine_water_frame(bed, result["states"], state_index=state_index)
                path = frame_directory/f"frame-{state_index:02d}.npz"
                save_fine_water_frame(path, frame)
                frames.append(dict(state_index=state_index, time_s=float(result["states"]["arrays"]["time_s"][state_index]),
                                   frame=record(path, frame)))
                del frame
            states = result["states"]
            depths[name] = states["arrays"]["depth_m"].copy()
            cases[name] = dict(bed=bed_records[spacing], run=run_record, frames=frames,
                spacing_m=spacing, max_dt_s=dt, initial_kind=kind, solver=states["metadata"]["solver_metadata"],
                diagnostics=states["metadata"]["diagnostics"], runoff_parameters=result["runoff_parameters"])
            resources(started, output)
            del result
            gc.collect()
            print(f"saved {name}", flush=True)
        comparisons = [comparison(depths["tailwater-rise-1m"], depths["tailwater-rise-1m-half-dt"], 1, "temporal .025/.0125s"),
                       comparison(depths["tailwater-rise-2m"], depths["tailwater-rise-1m-half-dt"], 2, "spatial 2/1m"),
                       comparison(depths["tailwater-rise-4m"], depths["tailwater-rise-2m"], 2, "spatial 4/2m")]
        coarse_time = cases["tailwater-rise-1m"]["solver"]
        fine_time = cases["tailwater-rise-1m-half-dt"]["solver"]
        temporal_resolution_changed = fine_time["substeps"] > coarse_time["substeps"]
        comparisons[0]["actual_temporal_resolution_changed"] = temporal_resolution_changed
        comparisons[0]["passed"] &= temporal_resolution_changed
        lake_error = float(np.abs(depths["lake-at-rest-1m"]-depths["lake-at-rest-1m"][0]).max())
        response = depths["tailwater-rise-1m-half-dt"][-1]-depths["tailwater-baseline-1m"][-1]
        import_volume = cases["tailwater-rise-1m-half-dt"]["solver"]["boundary_input_m3"]
        scenario_gates = dict(lake_at_rest=dict(max_depth_change_m=lake_error, passed=lake_error<=GATES["max_lake_depth_change_m"]),
                              controlled_tailwater=dict(max_depth_increase_m=float(response.max()),
                                  positive_response_cells=int(np.count_nonzero(response>GATES["minimum_tailwater_response_m"])),
                                  imported_volume_m3=import_volume,
                                  passed=float(response.max())>GATES["minimum_tailwater_response_m"] and import_volume>GATES["minimum_tailwater_import_m3"]))
        report = dict(schema="single-domain-fine-stage-report-v1", predeclared=declaration, boundary_declaration=boundary_declaration,
                      source=SOURCE, cases=cases, comparisons=comparisons, scenario_gates=scenario_gates,
                      all_predeclared_gates_passed=all(item["passed"] for item in comparisons) and all(item["passed"] for item in scenario_gates.values()),
                      official_frontend_integrated=False, full_native_domain_fine_verified=False,
                      limitations=["Selected 240m engineering window inside the original 7.68km TD domain.",
                                   "Fine interpolation and artificial channels are not naturally verified banks or outlets.",
                                   "Continuous water is conservative visualization of FV means, not subcell hydraulic state.",
                                   "Controlled finite scenarios do not replace full-day fine-domain validation.",
                                   "Official frontend integration belongs to the separately assigned frontend implementer."], **FLAGS)
        report_record = json_record(output / "report.json", report)
        observation = resources(started, output)
        artifacts = [dict(path=str(path.resolve()), expected_sha256=file_sha256(path), bytes=path.stat().st_size)
                     for path in sorted(output.rglob("*")) if path.is_file()]
        resource_record = json_record(output / "resource.json", dict(schema="single-domain-fine-stage-resource-v1",
            budgets=BUDGETS, observed=observation, artifacts=artifacts, thread_environment={name:os.environ[name] for name in THREADS},
            python_executable=sys.executable, complete=True))
        if file_sha256(SOURCE["path"]) != SOURCE["expected_sha256"] or any(file_sha256(ROOT/name)!=digest for name,digest in code.items()):
            raise ValueError("fixed source or code changed during run")
        index = dict(schema="single-domain-fine-stage-index-v1", source=SOURCE, predeclared=declaration,
                     boundary_declaration=boundary_declaration, report=report_record, resource=resource_record,
                     code_sha256=code, code_records=code_records, cases=cases,
                     all_predeclared_gates_passed=report["all_predeclared_gates_passed"], **FLAGS)
        pin = json_record(output / "index.json", index)
        print(json.dumps(dict(index=pin, observations=observation, comparisons=comparisons, scenario_gates=scenario_gates)), flush=True)
        return index
    except Exception as error:
        json_record(output / "failure.json", dict(error_type=type(error).__name__, reason=str(error),
            elapsed_s=time.monotonic()-started, source=SOURCE, code_sha256=code, index_published=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--backend", choices=("subgrid", "shallow_water", "shallow_water_subgrid", "shallow_water_subgrid_manning", "shallow_water_subgrid_manning_accelerated", "accelerated", "reference"), default="subgrid")
    args = parser.parse_args()
    run(args.output, backend=args.backend)


if __name__ == "__main__":
    main()
