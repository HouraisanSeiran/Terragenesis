"""Resume finite FV sediment growth with explicit source cursor and acceleration."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
from terrain_pipeline.surface_rivers.metric_natural_delta import finite_schedule
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig
from terrain_pipeline.surface_rivers.metric_fv_suspended_supply import SuspendedConfig, integrate_schedule
from terrain_pipeline.surface_rivers.metric_fv_growth_coupling_v3 import advance_growth
from terrain_pipeline.surface_rivers.metric_fv_exchange_v3 import ExchangeConfig
from tools.run_natural_delta_fv_water import make_geometry
from tools.verify_fluvial_channel_remobilization import resource_limits

IMPLEMENTATIONS = ("tools/run_natural_fv_growth.py", "terrain_pipeline/surface_rivers/metric_fv_growth_coupling.py",
    "terrain_pipeline/surface_rivers/metric_fv_suspended_supply.py", "terrain_pipeline/surface_rivers/metric_fv_coastal_sediment.py",
    "terrain_pipeline/surface_rivers/metric_natural_delta.py", "tools/run_natural_delta_fv_water.py",
    "terrain_pipeline/single_domain_shallow_water_accelerated_v7.py", "terrain_pipeline/single_domain_shallow_water_execution_v7.py",
    "terrain_pipeline/single_domain_shallow_water_support_v7.py", "terrain_pipeline/regional_surface_hydraulics.py",
    "tools/run_natural_fv_growth_v2.py", "terrain_pipeline/surface_rivers/metric_fv_exchange_v3.py",
    "terrain_pipeline/surface_rivers/metric_fv_growth_coupling_v3.py", "tools/run_natural_fv_growth_interval_v3.py",
    "tools/run_natural_fv_growth_v3.py")


def bootstrap(parent, water_run):
    report = json.loads((parent / "summary.json").read_text(encoding="utf-8"))
    water_report = json.loads((water_run / "summary.json").read_text(encoding="utf-8"))
    if water_report["parent_sha256"] != file_sha256(parent / "result.npz"):
        raise ValueError("water state belongs to another bed")
    with np.load(parent / "result.npz") as a:
        schedule = a["schedule"].copy()
        consumed = int(report["steps"])
        np.testing.assert_allclose(a["cumulative_input_solid_m3"][-1], schedule[:consumed, 3].sum(), atol=1.e-8)
        data = {key: a[key].copy() for key in ("source_floor_m", "cell_type", "local_world_xz_m", "fixed_boundary_mask")}
        data.update(bed_m=a["bed_m"][-1].astype(float), initial_bed_m=a["initial_bed_m"].astype(float),
            source_schedule=schedule[consumed:].copy())
    with np.load(water_run / "result.npz") as a:
        np.testing.assert_array_equal(a["bed_m"], data["bed_m"])
        data.update(depth_m=a["depth_m"][-1].copy(), momentum_m2_s=np.column_stack(
            (a["momentum_x_m2_s"][-1].ravel(), a["momentum_z_m2_s"][-1].ravel())),
            suspended_solid_m3=np.zeros_like(data["bed_m"]))
        physical = float(a["time_s"][-1])
    meta = {"schema": "finite-FV-growth-checkpoint-v3", "source_cursor_s": 0., "physical_time_s": physical,
        "cumulative_injected_solid_m3": 0., "cumulative_exported_solid_m3": 0.,
        "source_identities": [report["forcing"]["source_sha256"]],
        "source_total_solid_m3": float(data["source_schedule"][:, 3].sum()),
        "already_consumed_native_solid_m3": float(schedule[:consumed, 3].sum()),
        "already_consumed_native_packets": consumed,
        "parent_result": str(parent / "result.npz"), "parent_sha256": file_sha256(parent / "result.npz"),
        "water_result": str(water_run / "result.npz"), "water_sha256": file_sha256(water_run / "result.npz"),
        "scope": "independent wide river chain; never inherits sediment consumption from unrelated old TD02 continuation scenarios"}
    return data, meta


def append_source(data, meta, directory):
    digest = file_sha256(directory / "result.npz")
    if digest in meta["source_identities"]:
        raise ValueError("source already appended in this chain")
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    if report.get("status") != "completed" or report.get("old_exports_reissued_solid_m3") != 0.:
        raise ValueError("completed finite new-source export without recycled material required")
    with np.load(directory / "result.npz") as a:
        schedule = finite_schedule(a["water_q_m3_s"][:, -1], a["exported_solid_m3"].sum(axis=1), np.diff(a["time_seconds"]))
    np.testing.assert_allclose(schedule[:, 3].sum(), report["new_deliverable_export_solid_m3"], atol=1.e-7)
    data["source_schedule"] = np.concatenate([data["source_schedule"], schedule])
    meta["source_total_solid_m3"] += float(schedule[:, 3].sum())
    meta["source_identities"].append(digest)
    meta.setdefault("appended_sources", []).append({"path": str(directory), "sha256": digest, "solid_m3": float(schedule[:, 3].sum())})


def forcing_step(schedule, cursor, dt, acceleration, maximum_concentration, river_q=None, supply_off=False):
    if supply_off:
        _, q = integrate_schedule(schedule, cursor, dt)
        return 0., float(q if river_q is None else river_q), cursor
    desired = dt * acceleration
    def values(span):
        solid, q = integrate_schedule(schedule, cursor, span)
        q = q if river_q is None else river_q
        return solid, q
    solid, q = values(desired)
    if solid > maximum_concentration * q * dt:
        low, high = 0., desired
        for _ in range(40):
            middle = .5 * (low + high)
            load, flow = values(middle)
            if load <= maximum_concentration * flow * dt:
                low = middle
            else:
                high = middle
        desired = low
        solid, q = values(desired)
    return float(solid), float(q), cursor + desired


def run(args):
    if (args.intervals < 1 or args.chunk_intervals < 1 or args.interval_s <= 0. or args.source_time_scale <= 0.
            or not 0. < args.max_input_concentration <= .02 or args.packet_stride < 1):
        raise ValueError("positive execution budget and dilute input concentration <=0.02 required")
    hashes = {name: file_sha256(ROOT / name) for name in IMPLEMENTATIONS}
    if args.resume:
        with np.load(args.resume) as a:
            meta = json.loads(str(a["metadata_json"]))
            data = {key: a[key].copy() for key in a.files if key != "metadata_json"}
        if meta["schema"] != "finite-FV-growth-checkpoint-v3":
            raise ValueError("complete FV growth checkpoint required")
        if meta["implementation_hashes"] != hashes:
            raise ValueError("checkpoint implementation identity changed")
        meta["resumed_checkpoint"] = str(args.resume)
        meta["resumed_checkpoint_sha256"] = file_sha256(args.resume)
    else:
        data, meta = bootstrap(args.parent, args.water_run)
    if args.append_source:
        append_source(data, meta, args.append_source)
    meta["implementation_hashes"] = hashes
    exchange = ExchangeConfig(enabled=not args.disable_exchange, erosion_velocity_m_s=args.erosion_velocity,
        maximum_concentration=args.exchange_max_concentration, slope_enabled=not args.disable_slope,
        critical_slope_m_m=args.critical_slope, slope_mobility_m2_s=args.slope_mobility)
    exchange.validate()
    meta["exchange_config"] = asdict(exchange)
    bedload = BedloadConfig(wave_height_m=args.wave_height, wave_period_s=args.wave_period,
        max_bed_change_m=args.max_bed_change)
    suspended = SuspendedConfig(settling_velocity_m_s=args.settling_velocity, max_bed_change_m=args.max_bed_change)
    bedload.validate()
    suspended.validate()
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    (output / "packets").mkdir()
    started = time.monotonic()
    snapshots = {key: [data[key].copy()] for key in ("bed_m", "depth_m", "momentum_m2_s", "suspended_solid_m3")}
    times = [meta["physical_time_s"]]
    all_ledgers = []
    start_meta = json.loads(json.dumps(meta))
    initial_inventory = float(((data["bed_m"] - data["source_floor_m"]) * 25. * .65).sum() + data["suspended_solid_m3"].sum())
    done = 0
    water_totals = np.zeros(3)
    while done < args.intervals:
        count = min(args.chunk_intervals, args.intervals - done)
        cursor = meta["source_cursor_s"]
        loads, flows = [], []
        for _ in range(count):
            load, flow, cursor = forcing_step(data["source_schedule"], cursor, args.interval_s,
                args.source_time_scale, args.max_input_concentration, args.river_q, args.supply_off)
            loads.append(load)
            flows.append(flow)
        absolute_start = meta["physical_time_s"]
        phases = 2. * np.pi * (absolute_start + np.arange(count) * args.interval_s) / args.tide_period + np.deg2rad(args.tide_phase)
        seas = args.sea_mean + args.tide_amplitude * np.sin(phases)
        geometry = make_geometry(data["bed_m"].copy(), data["cell_type"], 5.)
        geometry["arrays"]["fixed_bed_cell"] = data["fixed_boundary_mask"].ravel()
        inlet = np.flatnonzero(data["cell_type"][0] == 1)
        base_number = done
        before_chunk = {key: data[key].copy() for key in ("bed_m", "depth_m", "momentum_m2_s", "suspended_solid_m3")}
        aggregate = {}
        aggregate_count = 0
        def accumulate(name, value):
            if name not in aggregate:
                aggregate[name] = np.zeros_like(value, dtype=float)
            aggregate[name] += value
        def save(packet, b, s, ledger):
            nonlocal aggregate_count
            aggregate_count += 1
            number = base_number + packet["interval"]
            ledger["global_interval"] = number
            ledger["physical_time_start_s"] = absolute_start + packet["time_start_s"]
            ledger["physical_time_end_s"] = absolute_start + packet["time_end_s"]
            for name in ("internal_transfer_m3", "boundary_transfer_m3", "forcing_volume_m3", "internal_momentum_transfer",
                    "boundary_momentum_transfer", "bed_momentum_change", "manning_momentum_change"):
                accumulate("water_" + name, packet[name])
            for name in ("internal_transfer_solid_m3", "boundary_export_solid_m3", "deposited_solid_m3", "entrained_solid_m3"):
                accumulate("suspended_" + name, s[name])
            for name in ("internal_transfer_solid_m3", "boundary_export_solid_m3", "fixed_marine_edge_export_solid_m3"):
                accumulate("bedload_" + name, b[name])
            accumulate("slope_internal_transfer_solid_m3", b["slope_internal_transfer_solid_m3"])
            injection = np.zeros(data["bed_m"].size)
            injection[inlet] = ledger["injected_solid_m3"] / len(inlet)
            accumulate("injected_cell_solid_m3", injection)
            if number % args.packet_stride == 0:
                np.savez_compressed(output / "packets" / f"{number:07d}-water.npz", **packet)
                np.savez_compressed(output / "packets" / f"{number:07d}-sediment.npz",
                    **{name: value for name, value in s.items() if name != "ledger"},
                    slope_internal_transfer_solid_m3=b["slope_internal_transfer_solid_m3"],
                    bedload_bed_m=b["bed_m"], bedload_internal_transfer_solid_m3=b["internal_transfer_solid_m3"],
                    bedload_boundary_export_solid_m3=b["boundary_export_solid_m3"],
                    bedload_fixed_marine_edge_export_solid_m3=b["fixed_marine_edge_export_solid_m3"])
        def witness(packet):
            number = base_number + packet["interval"]
            if number % args.packet_stride == 0:
                np.savez_compressed(output / "packets" / f"{number:07d}-first-substep.npz", **packet)
        result = advance_growth(geometry, floor_m=data["source_floor_m"], depth_m=data["depth_m"],
            momentum_m2_s=data["momentum_m2_s"], suspended_solid_m3=data["suspended_solid_m3"],
            river_q_m3_s=flows, input_solid_m3=loads, sea_stages_m=seas, inlet_cells=inlet,
            interval_s=args.interval_s, budget=SurfaceBudget(max_dt_s=1., max_snapshots=max(3, count + 2),
                max_duration_s=count * args.interval_s, max_wall_s=args.max_wall_s, max_bytes=args.max_bytes_mib * 1024 * 1024),
            exchange_config=exchange, bedload_config=bedload, suspended_config=suspended, interval_observer=save, momentum_observer=witness)
        a = result["arrays"]
        data.update(bed_m=a["bed_m"][-1], depth_m=a["depth_m"][-1], suspended_solid_m3=a["suspended_solid_m3"][-1],
            momentum_m2_s=np.column_stack([a["momentum_x_m2_s"][-1].ravel(), a["momentum_z_m2_s"][-1].ravel()]))
        meta["source_cursor_s"] = cursor
        meta["physical_time_s"] += count * args.interval_s
        meta["cumulative_injected_solid_m3"] += sum(loads)
        meta["cumulative_exported_solid_m3"] += sum(row["exported_solid_m3"] for row in result["sediment_ledgers"])
        all_ledgers.extend(result["sediment_ledgers"])
        water_totals += a["ledger"][-1, :3]
        done += count
        np.savez_compressed(output / f"chunk-audit-{done:07d}.npz", **aggregate,
            **{"before_" + key: value for key, value in before_chunk.items()},
            **{"after_" + key: data[key] for key in before_chunk}, source_floor_m=data["source_floor_m"],
            face_left=geometry["arrays"]["face_left"], face_right=geometry["arrays"]["face_right"],
            boundary_cell=geometry["arrays"]["boundary_cell"],
            aggregated_interval_count=aggregate_count, expected_interval_count=count,
            absolute_time_start_s=absolute_start, absolute_time_end_s=meta["physical_time_s"])
        checkpoint = output / f"checkpoint-{done:07d}.npz"
        np.savez_compressed(checkpoint, **data, metadata_json=json.dumps(meta))
        for key in snapshots:
            snapshots[key].append(data[key].copy())
        times.append(meta["physical_time_s"])
        (output / "interval-ledgers.json").write_text(json.dumps(all_ledgers, indent=2), encoding="utf-8")
        print("PROGRESS", done, "physical_s", meta["physical_time_s"], "new_solid_m3", meta["cumulative_injected_solid_m3"] - start_meta["cumulative_injected_solid_m3"],
            "wall_s", time.monotonic() - started, flush=True)
        if time.monotonic() - started > args.max_wall_s:
            raise RuntimeError("growth wall budget reached; resume last complete checkpoint")
    final_inventory = float(((data["bed_m"] - data["source_floor_m"]) * 25. * .65).sum() + data["suspended_solid_m3"].sum())
    injected = meta["cumulative_injected_solid_m3"] - start_meta["cumulative_injected_solid_m3"]
    exported = meta["cumulative_exported_solid_m3"] - start_meta["cumulative_exported_solid_m3"]
    arrays = {key: np.asarray(value) for key, value in snapshots.items()}
    arrays.update(time_s=np.asarray(times), source_floor_m=data["source_floor_m"], cell_type=data["cell_type"],
        initial_bed_m=data["initial_bed_m"], local_world_xz_m=data["local_world_xz_m"], fixed_boundary_mask=data["fixed_boundary_mask"])
    arrays["stage_m"] = arrays["bed_m"] + arrays["depth_m"]
    np.savez_compressed(output / "result.npz", **arrays)
    report = {"schema": "finite-FV-suspended-growth-v1", "status": "completed", "checkpoint": str(checkpoint),
        "checkpoint_sha256": file_sha256(checkpoint), "start": start_meta, "end": meta,
        "parameters": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "exchange_config": asdict(exchange), "bedload_config": asdict(bedload), "suspended_config": asdict(suspended),
        "initial_bed_plus_suspended_solid_m3": initial_inventory, "final_bed_plus_suspended_solid_m3": final_inventory,
        "injected_solid_m3": injected, "exported_solid_m3": exported,
        "combined_residual_solid_m3": final_inventory + exported - initial_inventory - injected,
        "maximum_phase_residual_solid_m3": max(abs(row["combined_residual_solid_m3"]) for row in all_ledgers),
        "remaining_finite_source_solid_m3": meta["source_total_solid_m3"] - meta["cumulative_injected_solid_m3"],
        "water_supplied_imported_exported_m3": water_totals.tolist(),
        "water_volume_residual_m3": float((arrays["depth_m"][-1] - arrays["depth_m"][0]).sum() * 25.
            - water_totals[0] - water_totals[1] + water_totals[2]),
        "runtime_s": time.monotonic() - started, "implementation_hashes": hashes,
        "limitations": "v3 finite shear-dependent bed/suspended exchange and wet-bank excess-slope transport; empirical equilibrium/erosion/mobility parameters; interval-net advection; unchanged finite floor; no cohesive bank calibration or wave radiation stress; mechanism source-time compression"}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", type=Path)
    p.add_argument("--water-run", type=Path)
    p.add_argument("--resume", type=Path)
    p.add_argument("--append-source", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--intervals", type=int, default=32)
    p.add_argument("--chunk-intervals", type=int, default=16)
    p.add_argument("--interval-s", type=float, default=.25)
    p.add_argument("--source-time-scale", type=float, default=1.)
    p.add_argument("--max-input-concentration", type=float, default=.01)
    p.add_argument("--supply-off", action="store_true")
    p.add_argument("--river-q", type=float)
    p.add_argument("--sea-mean", type=float, default=0.)
    p.add_argument("--tide-amplitude", type=float, default=0.)
    p.add_argument("--tide-period", type=float, default=44714.)
    p.add_argument("--tide-phase", type=float, default=0.)
    p.add_argument("--wave-height", type=float, default=0.)
    p.add_argument("--wave-period", type=float, default=5.)
    p.add_argument("--settling-velocity", type=float, default=.005)
    p.add_argument("--max-bed-change", type=float, default=.01)
    p.add_argument("--packet-stride", type=int, default=1)
    p.add_argument("--max-wall-s", type=float, default=7200.)
    p.add_argument("--max-bytes-mib", type=int, default=768)
    p.add_argument("--disable-exchange", action="store_true")
    p.add_argument("--erosion-velocity", type=float, default=1.e-5)
    p.add_argument("--exchange-max-concentration", type=float, default=.03)
    p.add_argument("--disable-slope", action="store_true")
    p.add_argument("--critical-slope", type=float, default=.35)
    p.add_argument("--slope-mobility", type=float, default=.02)
    return p


if __name__ == "__main__":
    resource_limits()
    args = parser().parse_args()
    print(json.dumps(run(args), indent=2))
