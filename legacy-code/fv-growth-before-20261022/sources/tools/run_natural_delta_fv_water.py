"""Fixed saved natural-delta bed: physical-time FV drainage, no sediment.

Reuses the existing flat-cell hydrostatic HLL solver without changing its
equations. The river is a cell-volume source with zero injected momentum;
saved native momentum is not imported into this independent relaxation.
"""
import argparse
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget, prepare_surface_geometry
from terrain_pipeline.single_domain_shallow_water import advance_shallow_water
from tools.verify_fluvial_channel_remobilization import resource_limits

IMPLEMENTATIONS = ("tools/run_natural_delta_fv_water.py", "terrain_pipeline/single_domain_shallow_water.py",
    "terrain_pipeline/single_domain_shallow_water_support.py", "terrain_pipeline/regional_surface_hydraulics.py")
ACCELERATED_IMPLEMENTATIONS = ("terrain_pipeline/single_domain_shallow_water_accelerated_v7.py",
    "terrain_pipeline/single_domain_shallow_water_execution_v7.py",
    "terrain_pipeline/single_domain_shallow_water_support_v7.py")


def make_geometry(bed, cell_type, spacing):
    """Keep native marine boundary cells open and all other outer faces closed."""
    edge_types = np.r_[cell_type[:, 0], cell_type[:, -1], cell_type[0], cell_type[-1]]
    kinds = np.where(edge_types == -1, 2, 0).astype(np.int64)
    return prepare_surface_geometry(bed, spacing_m=spacing, origin_m_xz=[0., 0.],
        source_identity="saved-natural-delta-final-bed", boundary_kind=kinds)


def add_flat_cell_support(geometry):
    """One subcell and one crest segment per existing face; no coarsening."""
    arrays = geometry["arrays"]
    datum = float(arrays["H2_m"].min())
    relative_bed = (arrays["H2_m"] - datum).reshape(-1, 1)
    arrays["subcell_bed_relative_m"] = relative_bed.copy()
    arrays["subcell_prefix_relative_m"] = relative_bed.copy()
    arrays["face_segment_crest_relative_m"] = (arrays["face_crest_m"] - datum)[:, None]
    arrays["boundary_segment_crest_relative_m"] = (arrays["boundary_crest_m"] - datum)[:, None]
    geometry["metadata"]["hydraulic_datum_m"] = datum


def run(parent, output, *, duration_s=150., interval_s=30., river_q_m3_s=155., sea_stage_m=0., backend="reference",
        tide_amplitude_m=0., tide_period_s=44714., tide_phase_deg=0., max_wall_s=3600., max_bytes_mib=512):
    if (not np.isfinite([duration_s, interval_s, river_q_m3_s, sea_stage_m,
            tide_amplitude_m, tide_period_s, tide_phase_deg]).all()
            or duration_s <= 0 or interval_s <= 0 or river_q_m3_s < 0
            or tide_amplitude_m < 0 or tide_period_s <= 0
            or not np.isclose(duration_s / interval_s, round(duration_s / interval_s))):
        raise ValueError("finite duration divisible by interval and nonnegative river Q required")
    if backend not in ("reference", "accelerated-v7"):
        raise ValueError("unknown FV backend")
    report = json.loads((parent / "summary.json").read_text(encoding="utf-8"))
    spacing = float(report["config"]["dx_m"])
    with np.load(parent / "result.npz") as saved:
        bed = saved["bed_m"][-1].astype(np.float64)
        depth = saved["depth_m"][-1].astype(np.float64)
        cell_type = saved["cell_type"].copy()
        original_bed = saved["initial_bed_m"].astype(np.float64)
    geometry = make_geometry(bed, cell_type, spacing)
    advance = advance_shallow_water
    implementations = IMPLEMENTATIONS
    if backend == "accelerated-v7":
        from terrain_pipeline.single_domain_shallow_water_accelerated_v7 import advance_shallow_water as accelerated_advance
        add_flat_cell_support(geometry)
        advance = accelerated_advance
        implementations += ACCELERATED_IMPLEMENTATIONS
    inlet = np.flatnonzero(cell_type[0] == 1)
    if not len(inlet):
        raise ValueError("saved upstream inlet required")
    source = np.zeros_like(bed)
    source[0, inlet] = river_q_m3_s / len(inlet)
    intervals = round(duration_s / interval_s)
    forcing_time = np.arange(intervals + 1, dtype=np.float64) * interval_s
    sea_stages = sea_stage_m + tide_amplitude_m * np.sin(
        2. * np.pi * forcing_time / tide_period_s + np.deg2rad(tide_phase_deg))
    applied_stages = []
    boundary_net_transfers = []

    def boundary_stage(index):
        applied_stages.append(float(sea_stages[index]))
        return np.full(len(geometry["arrays"]["boundary_cell"]), sea_stages[index])

    budget = SurfaceBudget(max_dt_s=1., max_duration_s=duration_s, max_snapshots=intervals + 2,
        max_wall_s=max_wall_s, max_bytes=max_bytes_mib * 1024 * 1024)
    hashes = {name: file_sha256(ROOT / name) for name in implementations}
    output.mkdir(parents=True, exist_ok=False)
    (output / "intervals").mkdir()

    def save_interval(packet):
        packet["applied_sea_stage_m"] = sea_stages[packet["interval"]]
        boundary_net_transfers.append(float(packet["boundary_transfer_m3"].sum()))
        np.savez_compressed(output / "intervals" / (f"{packet['interval']:05d}.npz"), **packet)

    result = advance(geometry, initial_depth_m=depth, forcing_interval_s=interval_s,
        intervals=intervals, forcing_provider=lambda index: source,
        boundary_stage_provider=boundary_stage, source_identity="saved-natural-delta-final-bed",
        forcing_identity="constant-river-cell-volume-source-and-interval-sampled-sinusoidal-sea-stage", budget=budget,
        snapshot_interval_s=interval_s, interval_observer=save_interval,
        momentum_observer=lambda packet: np.savez_compressed(
            output / "intervals" / (f"{packet['interval']:05d}-first-substep.npz"), **packet))
    arrays = result["arrays"]
    arrays.update(bed_m=bed, initial_bed_m=original_bed, cell_type=cell_type,
        stage_m=arrays["depth_m"] + bed, forcing_time_s=forcing_time,
        sea_stage_at_forcing_times_m=sea_stages, applied_sea_stage_m=np.asarray(applied_stages),
        interval_sea_imported_m3=np.diff(arrays["ledger"][:, 1]),
        interval_sea_exported_m3=np.diff(arrays["ledger"][:, 2]),
        interval_boundary_net_outward_m3=np.asarray(boundary_net_transfers), **geometry["arrays"])
    exchange_residual = (arrays["interval_boundary_net_outward_m3"]
        - arrays["interval_sea_exported_m3"] + arrays["interval_sea_imported_m3"])
    np.savez_compressed(output / "result.npz", **arrays)
    area = spacing ** 2
    bar = (original_bed < 0) & (cell_type == 0) & (bed >= 0)
    dry_area = ((arrays["depth_m"] <= 2.e-6) & bar).sum(axis=(1, 2)) * area
    summary = {"schema": "natural-delta-fixed-bed-physical-time-FV-water-v1", "diagnostic_only": True,
        "backend": backend, "subcells_per_cell": 1, "crest_segments_per_face": 1,
        "parent_result": str(parent / "result.npz"), "parent_sha256": file_sha256(parent / "result.npz"),
        "implementation_hashes": hashes,
        "implementation_unchanged": all(file_sha256(ROOT / name) == digest for name, digest in hashes.items()),
        "initialization": "saved native final depth; FV initial momentum zero; fixed unchanged final bed",
        "forcing": {"river_q_m3_s": river_q_m3_s, "sea_stage_m": sea_stage_m,
            "tide_amplitude_m": tide_amplitude_m, "tide_period_s": tide_period_s,
            "tide_phase_deg": tide_phase_deg, "forcing_interval_s": interval_s,
            "sea_stage_formula": "mean + amplitude*sin(2*pi*t/period + phase)",
            "sea_stage_time_semantics": "interval-start samples held constant throughout each interval; final endpoint sample saved but not applied",
            "river_cells_row_column": [[0, int(column)] for column in inlet],
            "river_injected_momentum": "zero", "boundary_face_order": "W/E/N/S",
            "prescribed_sea_faces": int((geometry["arrays"]["boundary_kind"] == 2).sum())},
        "ledger_columns": ["supplied_m3", "sea_imported_m3", "sea_exported_m3", "stored_m3", "residual_m3"],
        "ledger_final_m3": arrays["ledger"][-1].tolist(),
        "maximum_abs_water_residual_m3": float(abs(arrays["ledger"][:, -1]).max()),
        "maximum_abs_boundary_exchange_residual_m3": float(abs(exchange_residual).max()),
        "sea_exchange_audit": "gross sea input/output integrate signed RK face flux at every substep; interval differences of cumulative ledger; net checked against all boundary face transfers",
        "above_datum_bar_area_m2": float(bar.sum() * area),
        "true_dry_bar_area_m2_by_frame": dry_area.tolist(),
        "metadata": result["metadata"], "diagnostics": result["diagnostics"],
        "projected_44714s_wall_s_linear": result["metadata"]["wall_s"] * 44714. / duration_s,
        "limitations": "physical-time fixed-bed water diagnostic, no sediment or waves; first-order FV and uncalibrated friction; initial zero momentum requires relaxation; linear runtime projection may change with wetting/velocity"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=150.)
    parser.add_argument("--interval-s", type=float, default=30.)
    parser.add_argument("--river-q", type=float, default=155.)
    parser.add_argument("--sea-stage", type=float, default=0.)
    parser.add_argument("--backend", choices=("reference", "accelerated-v7"), default="reference")
    parser.add_argument("--tide-amplitude", type=float, default=0., help="metres; zero keeps fixed sea stage")
    parser.add_argument("--tide-period-s", type=float, default=44714.)
    parser.add_argument("--tide-phase-deg", type=float, default=0.)
    parser.add_argument("--max-wall-s", type=float, default=3600.)
    parser.add_argument("--max-bytes-mib", type=int, default=512)
    args = parser.parse_args()
    resource_limits()
    print(json.dumps(run(args.parent, args.output, duration_s=args.duration_s, interval_s=args.interval_s,
        river_q_m3_s=args.river_q, sea_stage_m=args.sea_stage, backend=args.backend,
        tide_amplitude_m=args.tide_amplitude, tide_period_s=args.tide_period_s,
        tide_phase_deg=args.tide_phase_deg, max_wall_s=args.max_wall_s,
        max_bytes_mib=args.max_bytes_mib), indent=2))
