"""Pin short independent fine-grid hydraulic experiments without stage acceptance."""

import argparse
import gc
import json
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(name, "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import (
    build_fine_geometry, coarsen_cell_field, save_fine_geometry,
)
from terrain_pipeline.single_domain_fine_hydraulics import run_fine_hydraulics
from terrain_pipeline.single_domain_fine_io import save_fine_run
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
from tools.run_single_domain_fine_stage import (SOURCE, WINDOW, GATES, BUDGETS,
    THREADS, backend_code_files, freeze_execution_code, comparison, json_record, record, resources)
from terrain_pipeline.mountain_source_adapter import file_sha256


def diagnose(output, *, backend, duration_s=30., max_dt_s=.025):
    if any(os.environ.get(name) != "1" for name in THREADS):
        raise ValueError("all numerical thread environment settings must equal 1")
    if not 0 < duration_s <= 120 or not 0 < max_dt_s <= .025:
        raise ValueError("short diagnostic duration/dt outside declared bounds")
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    files = backend_code_files(backend) + ["tools/diagnose_single_domain_fine.py"]
    code = {name: file_sha256(ROOT / name) for name in files}
    code_records = freeze_execution_code(output, code)
    predeclared = json_record(output / "predeclared.json", dict(
        schema="single-domain-fine-short-diagnostic-v1", source=SOURCE, native_window=WINDOW,
        execution_backend=backend, duration_s=duration_s, max_dt_s=max_dt_s,
        forcing_interval_s=duration_s / 3, tailwater_rise_m=.5, spacing_m=[1., 2., 4.],
        initial_water_contract="canonical 1m lake inventory restricted by area mean",
        code_sha256=code, code_records=code_records, gates=GATES, budgets=BUDGETS, stage_accepted=False))
    try:
        hierarchy = load_basin_hierarchy(**SOURCE)
        canonical = build_fine_geometry(hierarchy, native_window=WINDOW,
            source_hierarchy_sha256=SOURCE["expected_sha256"], spacing_m=1.)
        lake_stage = float(np.quantile(canonical["arrays"]["bed_center_m"], .65))
        canonical_initial = np.maximum(lake_stage-canonical["arrays"]["bed_center_m"], 0.)
        cases, depths = {}, {}
        for spacing in (1., 2., 4.):
            bed = canonical if spacing == 1. else build_fine_geometry(hierarchy,
                native_window=WINDOW, source_hierarchy_sha256=SOURCE["expected_sha256"], spacing_m=spacing)
            bed_path = output / f"bed-{int(spacing)}m.npz"
            save_fine_geometry(bed_path, bed)
            bed_record = record(bed_path, bed)
            rows, columns = bed["arrays"]["bed_center_m"].shape
            boundary_kind = np.zeros(2*(rows+columns), np.int64)
            boundary_kind[rows:2*rows] = 2
            stages = np.full((3, len(boundary_kind)), lake_stage, np.float64)
            stages[1:, rows:2*rows] += .5
            initial = canonical_initial.copy() if spacing == 1. else coarsen_cell_field(canonical_initial, factor=int(spacing))
            budget = SurfaceBudget(max_dt_s=max_dt_s, max_cells=65536, max_snapshots=5,
                max_duration_s=duration_s, max_wall_s=1800., max_depth_m=10.)
            print(f"diagnostic {backend} {spacing:g}m: {rows}x{columns}", flush=True)
            result = run_fine_hydraulics(bed, rain_mm_h=np.zeros((3, rows, columns), np.float64),
                boundary_stage_m=stages, forcing_interval_s=duration_s/3,
                boundary_kind=boundary_kind, initial_depth_m=initial, budget=budget, backend=backend)
            run_record = save_fine_run(output/f"run-{int(spacing)}m", result,
                bed_record=bed_record, code_sha256=code, code_records=code_records)
            depths[spacing] = result["states"]["arrays"]["depth_m"].copy()
            cases[str(spacing)] = dict(bed=bed_record, run=run_record,
                solver=result["states"]["metadata"]["solver_metadata"],
                diagnostics=result["states"]["metadata"]["diagnostics"])
            resources(started, output)
            del result
            gc.collect()
        comparisons = [comparison(depths[2.], depths[1.], 2, "diagnostic 2/1m"),
                       comparison(depths[4.], depths[2.], 2, "diagnostic 4/2m")]
        observed = resources(started, output)
        if any(file_sha256(ROOT/name) != digest for name, digest in code.items()):
            raise ValueError("diagnostic implementation changed during execution")
        pin = json_record(output/"index.json", dict(schema="single-domain-fine-short-index-v1",
            source=SOURCE, predeclared=predeclared, code_sha256=code, code_records=code_records, cases=cases,
            comparisons=comparisons, resources=observed, initial_lake_stage_m=lake_stage,
            stage_accepted=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
            limitations=["Short diagnostic has no temporal refinement or full-day acceptance.",
                         ("Canonical storage preserves a uniform partial-wet lake; dynamic coarse subcell velocity is unresolved."
                          if backend in ("subgrid", "shallow_water_subgrid", "shallow_water_subgrid_manning", "shallow_water_subgrid_manning_accelerated") else
                          "Canonical mean inventory on a flat coarse bed need not preserve coarse lake equilibrium.")]))
        print(json.dumps(dict(index=pin, comparisons=comparisons, resources=observed)), flush=True)
    except Exception as error:
        json_record(output/"failure.json", dict(error_type=type(error).__name__, reason=str(error),
            predeclared=predeclared, code_sha256=code, index_published=False))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--backend", required=True, choices=("subgrid", "shallow_water", "shallow_water_subgrid", "shallow_water_subgrid_manning", "shallow_water_subgrid_manning_accelerated", "accelerated", "reference"))
    parser.add_argument("--duration-s", type=float, default=30.)
    parser.add_argument("--max-dt-s", type=float, default=.025)
    args = parser.parse_args()
    diagnose(args.output, backend=args.backend, duration_s=args.duration_s, max_dt_s=args.max_dt_s)
