"""Continue a saved FV interval with live water/finite-bed coastal transport."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_hydraulics import SurfaceBudget
from terrain_pipeline.shallow_water import shallow_water_rhs_accelerated as shallow_water_rhs
from terrain_pipeline.surface_rivers.metric_fv_coastal_coupling import advance_coupled
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig
from tools.run_natural_delta_fv_water import make_geometry, add_flat_cell_support
from tools.verify_fluvial_channel_remobilization import resource_limits


def run(parent, water_run, water_interval, output, *, duration_s=120., interval_s=10.,
        sea_mean_m=0., tide_amplitude_m=.3, tide_period_s=44714., tide_phase_deg=180.,
        wave_height_m=.3, wave_period_s=5., wave_direction_xz=(0, -1), grain_diameter_m=.0003,
        max_bed_change_m=.01, max_wall_s=7200., max_bytes_mib=1024):
    steps = round(duration_s / interval_s)
    if steps < 1 or not np.isclose(steps * interval_s, duration_s):
        raise ValueError("duration divisible by positive coupling interval required")
    native_report = json.loads((parent / "summary.json").read_text(encoding="utf-8"))
    with np.load(parent / "result.npz") as saved:
        bed = saved["bed_m"][-1].astype(float)
        floor = saved["source_floor_m"].astype(float)
        cell_type = saved["cell_type"].copy()
        initial_native = saved["initial_bed_m"].copy()
        coordinates = {key: saved[key].copy() for key in ("local_world_xz_m",) if key in saved}
        fixed = saved["fixed_boundary_mask"].copy() if "fixed_boundary_mask" in saved else np.isin(cell_type, [-1, -2])
    geometry = make_geometry(bed.copy(), cell_type, float(native_report["config"]["dx_m"]))
    geometry["arrays"]["fixed_bed_cell"] = fixed.ravel()
    add_flat_cell_support(geometry)
    packet_path = water_run / "intervals" / f"{water_interval:05d}.npz"
    witness_path = water_run / "intervals" / f"{water_interval:05d}-first-substep.npz"
    with np.load(packet_path) as saved:
        packet = {name: saved[name].copy() for name in saved.files}
    with np.load(witness_path) as saved:
        witness = {name: saved[name].copy() for name in saved.files}
    # In-progress fixed-bed water runs have no final summary yet. Verify the
    # full archived RK1 hydraulic witness against this exact parent geometry.
    a = geometry["arrays"]
    datum = geometry["metadata"]["hydraulic_datum_m"]
    support = {name: a[name] for name in ("subcell_bed_relative_m", "subcell_prefix_relative_m",
        "face_segment_crest_relative_m", "boundary_segment_crest_relative_m")}
    _, recomputed = shallow_water_rhs(witness["state_before"], bed - datum, support=support,
        spacing=geometry["metadata"]["spacing_m"], gravity=9.81, boundary_kind=a["boundary_kind"],
        tailwater=witness["tailwater_m"] - datum, roughness=.035, dt=float(witness["dt_s"]),
        boundary_crest=a["boundary_crest_m"] - datum)
    for archived, current in (("rk1_internal_flux", "internal_flux"), ("rk1_boundary_flux", "boundary_flux"), ("rk1_bed_source", "bed_source")):
        np.testing.assert_allclose(witness[archived], recomputed[current], atol=2.e-11, rtol=2.e-12)
    start_time = float(packet["time_end_s"])
    depth = packet["depth_after_m"].reshape(bed.shape).astype(float)
    momentum = packet["momentum_after"].astype(float)
    source = (packet["forcing_volume_m3"] / (packet["time_end_s"] - packet["time_start_s"])).reshape(bed.shape)
    config = BedloadConfig(wave_height_m=wave_height_m, wave_period_s=wave_period_s,
        wave_direction_xz=tuple(wave_direction_xz), grain_diameter_m=grain_diameter_m, max_bed_change_m=max_bed_change_m)
    config.validate()
    output.mkdir(parents=True, exist_ok=False)
    (output / "intervals").mkdir()
    implementations = ("terrain_pipeline/surface_rivers/metric_fv_coastal_sediment.py",
        "terrain_pipeline/surface_rivers/metric_fv_coastal_coupling.py", "tools/run_natural_delta_fv_coastal.py",
        "terrain_pipeline/shallow_water.py", "terrain_pipeline/shallow_water.py")
    hashes = {name: file_sha256(ROOT / name) for name in implementations}
    sea_stages = []

    def sea(index):
        absolute_time = start_time + index * interval_s
        level = sea_mean_m + tide_amplitude_m * np.sin(2. * np.pi * absolute_time / tide_period_s + np.deg2rad(tide_phase_deg))
        sea_stages.append(float(level))
        return np.full(len(a["boundary_cell"]), level)

    def save_interval(water, sediment):
        number = water["interval"]
        np.savez_compressed(output / "intervals" / f"{number:05d}-water.npz", **water)
        np.savez_compressed(output / "intervals" / f"{number:05d}-sediment.npz",
            **{name: value for name, value in sediment.items() if name != "ledger"})

    def save_failure(water, unchanged_bed, reason):
        np.savez_compressed(output / "rejected-water.npz", **water)
        np.savez_compressed(output / "rejected-bed.npz", bed_m=unchanged_bed, source_floor_m=floor)
        (output / "failure.json").write_text(json.dumps({"status": "rejected-morphodynamic-step",
            "reason": reason, "interval": int(water["interval"]), "sediment_config": asdict(config),
            "parent_result": str(parent / "result.npz"), "physical_parent_packet_time_s": start_time,
            "implementation_hashes": hashes, "rejected_sediment_delivered": False}, indent=2), encoding="utf-8")

    result = advance_coupled(geometry, floor_m=floor, initial_depth_m=depth, initial_momentum_m2_s=momentum,
        source_m3_s=source, sea_stage_provider=sea, intervals=steps, interval_s=interval_s,
        budget=SurfaceBudget(max_dt_s=1., max_snapshots=steps + 2, max_duration_s=duration_s,
            max_wall_s=max_wall_s, max_bytes=max_bytes_mib * 1024 * 1024), config=config, interval_observer=save_interval,
        failure_observer=save_failure,
        momentum_observer=lambda p: np.savez_compressed(output / "intervals" / f"{p['interval']:05d}-first-substep.npz", **p))
    arrays = result["arrays"]
    arrays.update(absolute_time_s=arrays["time_s"] + start_time, cell_type=cell_type,
        initial_native_bed_m=initial_native, applied_sea_stage_m=np.asarray(sea_stages),
        fixed_boundary_mask=fixed, **coordinates,
        **{key: a[key] for key in ("face_left", "face_right", "boundary_cell", "boundary_kind")})
    np.savez_compressed(output / "result.npz", **arrays)
    ledgers = result["sediment_ledgers"]
    summary = {"schema": "natural-FV-coupled-MPM-Airy-coastal-diagnostic-v1", "diagnostic_only": True,
        "parent_result": str(parent / "result.npz"), "parent_sha256": file_sha256(parent / "result.npz"),
        "water_packet": str(packet_path), "water_packet_sha256": file_sha256(packet_path),
        "water_witness": str(witness_path), "water_witness_sha256": file_sha256(witness_path),
        "parent_bed_full_RK1_flux_and_pressure_witness_match": True,
        "initial_momentum": "exact saved FV momentum_after, injected into live state before first CFL/RK evaluation",
        "physical_start_time_s": start_time, "physical_end_time_s": start_time + duration_s,
        "forcing": {"river_q_m3_s": float(source.sum()), "sea_mean_m": sea_mean_m,
            "tide_amplitude_m": tide_amplitude_m, "tide_period_s": tide_period_s, "tide_phase_deg": tide_phase_deg,
            "stage_sampling": "absolute-time interval-start hold", "external_sediment_solid_m3": 0.},
        "sediment_config": asdict(config), "sediment_intervals": ledgers,
        "sediment_exported_solid_m3": sum(row["exported_solid_m3"] for row in ledgers),
        "bed_change_limiter_activations": sum(row["bed_change_limiter_activations"] for row in ledgers),
        "minimum_transport_time_fraction": min(row["transport_time_fraction"] for row in ledgers),
        "inventory_limited_donor_events": sum(row["inventory_limited_donors"] for row in ledgers),
        "minimum_inventory_donor_factor": min(row["minimum_inventory_donor_factor"] for row in ledgers),
        "bed_change_stability_semantics": "full physical time evaluated without rate scaling; step exceeding max bed change raises MorphodynamicStepTooLarge and requires complete retry with shorter coupling interval",
        "coordinate_semantics": "FV x is cross-stream/column, z downstream/row; local_world_xz_m copied when parent supplies it; exact parent archive referenced otherwise",
        "maximum_abs_sediment_residual_solid_m3": max(abs(row["residual_solid_m3"]) for row in ledgers),
        "maximum_abs_water_residual_m3": float(abs(arrays["ledger"][:, -1]).max()),
        "metadata": result["metadata"], "diagnostics": result["diagnostics"],
        "implementation_hashes": hashes,
        "implementation_unchanged": all(file_sha256(ROOT / name) == value for name, value in hashes.items()),
        "scope": "two-way water/bed operator splitting; no fresh river sediment; original finite floor unchanged; MPM noncohesive bedload and symmetric Airy orbital stirring, straight rays without refraction/radiation stress; not calibrated shoreline evolution"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--water-run", type=Path, required=True)
    parser.add_argument("--water-interval", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=120.)
    parser.add_argument("--interval-s", type=float, default=10.)
    parser.add_argument("--sea-mean", type=float, default=0.)
    parser.add_argument("--tide-amplitude", type=float, default=.3)
    parser.add_argument("--tide-period-s", type=float, default=44714.)
    parser.add_argument("--tide-phase-deg", type=float, default=180.)
    parser.add_argument("--wave-height", type=float, default=.3)
    parser.add_argument("--wave-period-s", type=float, default=5.)
    parser.add_argument("--wave-direction-xz", type=int, nargs=2, default=(0, -1))
    parser.add_argument("--grain-diameter-m", type=float, default=.0003)
    parser.add_argument("--max-bed-change", type=float, default=.01)
    parser.add_argument("--max-bytes-mib", type=int, default=1024)
    args = parser.parse_args()
    resource_limits()
    print(json.dumps(run(args.parent, args.water_run, args.water_interval, args.output,
        duration_s=args.duration_s, interval_s=args.interval_s, sea_mean_m=args.sea_mean,
        tide_amplitude_m=args.tide_amplitude, tide_period_s=args.tide_period_s, tide_phase_deg=args.tide_phase_deg,
        wave_height_m=args.wave_height, wave_period_s=args.wave_period_s, wave_direction_xz=args.wave_direction_xz,
        grain_diameter_m=args.grain_diameter_m, max_bed_change_m=args.max_bed_change,
        max_bytes_mib=args.max_bytes_mib), indent=2))
