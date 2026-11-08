"""Current v4 FV interval execution, explicit state protocol and carrier evidence."""
from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np
from terrain_pipeline.surface_hydraulics import SurfaceBudget, prepare_surface_geometry
from terrain_pipeline.surface_rivers.metric_natural_delta import finite_schedule
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig
from terrain_pipeline.surface_rivers.metric_fv_suspended_supply import SuspendedConfig, integrate_schedule
from terrain_pipeline.surface_rivers.metric_fv_exchange_v3 import ExchangeConfig
from terrain_pipeline.surface_rivers.metric_fv_growth_coupling_v4 import advance_growth
from tools.natural_fv_growth_state_io import (CAPTURE_FIELDS, CONTRACT, bind_parameters, file_sha256,
    identities, load_checkpoint, read_arrays, save_checkpoint)


def make_geometry(bed, cell_type, spacing):
    edge_types = np.r_[cell_type[:, 0], cell_type[:, -1], cell_type[0], cell_type[-1]]
    kinds = np.where(edge_types == -1, 2, 0).astype(np.int64)
    return prepare_surface_geometry(bed, spacing_m=spacing, origin_m_xz=[0., 0.],
        source_identity="saved-natural-delta-final-bed", boundary_kind=kinds)


def append_source(data, meta, directory):
    digest = file_sha256(directory / "result.npz")
    if digest in meta["source_identities"]:
        raise ValueError("source already appended in this chain")
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    if report.get("status") != "completed" or report.get("old_exports_reissued_solid_m3") != 0.:
        raise ValueError("completed finite new-source export without recycled material required")
    with np.load(directory / "result.npz", allow_pickle=False) as a:
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
    if not args.resume:
        raise ValueError("current v4 interval requires an explicit complete current checkpoint")
    data, meta = load_checkpoint(args.resume)
    bind_parameters(meta, args)
    if args.append_source:
        append_source(data, meta, args.append_source)
    hashes = identities()
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
    carrier = {}
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
            for key in CAPTURE_FIELDS:
                value = b[key]
                if key not in carrier:
                    carrier[key] = np.zeros_like(value)
                carrier[key] += value
            actual = b["internal_transfer_solid_m3"]
            boundary_actual = b["boundary_export_solid_m3"]
            evidence = {
                "carrier_internal_accepted_abs_solid_m3": abs(actual),
                "carrier_internal_max_capacity_violation_solid_m3": np.asarray(np.maximum(abs(actual) - b["carrier_internal_capacity_solid_m3"], 0.).max(initial=0.)),
                "carrier_internal_max_direction_violation_solid_m3": np.asarray(np.where(actual * packet["internal_transfer_m3"] <= 0., abs(actual), 0.).max(initial=0.)),
                "carrier_boundary_accepted_actual_solid_m3": boundary_actual,
                "carrier_boundary_max_capacity_violation_solid_m3": np.asarray(np.maximum(boundary_actual - b["carrier_boundary_capacity_solid_m3"], 0.).max(initial=0.))}
            for key, value in evidence.items():
                if key not in carrier:
                    carrier[key] = np.zeros_like(value)
                if "_max_" in key:
                    carrier[key] = np.maximum(carrier[key], value)
                else:
                    carrier[key] += value
            if packet["interval"] % args.packet_stride == 0:
                np.savez_compressed(output / "packets" / f"{packet['interval']:07d}-carrier.npz",
                    **{key: b[key] for key in CAPTURE_FIELDS},
                    accepted_internal_transfer_solid_m3=b["internal_transfer_solid_m3"],
                    accepted_boundary_export_solid_m3=b["boundary_export_solid_m3"],
                    water_internal_transfer_m3=packet["internal_transfer_m3"],
                    water_boundary_transfer_m3=packet["boundary_transfer_m3"])
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
        save_checkpoint(checkpoint, data, meta)
        for key in snapshots:
            snapshots[key].append(data[key].copy())
        times.append(meta["physical_time_s"])
        (output / "interval-ledgers.json").write_text(json.dumps(all_ledgers, indent=2), encoding="utf-8")
        if time.monotonic() - started > args.max_wall_s:
            raise RuntimeError("growth wall budget reached; resume last complete checkpoint")
    for path in output.glob("chunk-audit-*.npz"):
        saved = read_arrays(path)
        saved.update({"bedload_" + key: value for key, value in carrier.items()})
        np.savez_compressed(path, **saved)
    final_inventory = float(((data["bed_m"] - data["source_floor_m"]) * 25. * .65).sum() + data["suspended_solid_m3"].sum())
    injected = meta["cumulative_injected_solid_m3"] - start_meta["cumulative_injected_solid_m3"]
    exported = meta["cumulative_exported_solid_m3"] - start_meta["cumulative_exported_solid_m3"]
    arrays = {key: np.asarray(value) for key, value in snapshots.items()}
    arrays.update(time_s=np.asarray(times), source_floor_m=data["source_floor_m"], cell_type=data["cell_type"],
        initial_bed_m=data["initial_bed_m"], local_world_xz_m=data["local_world_xz_m"], fixed_boundary_mask=data["fixed_boundary_mask"])
    arrays["stage_m"] = arrays["bed_m"] + arrays["depth_m"]
    np.savez_compressed(output / "result.npz", **arrays)
    report = {"schema": "finite-FV-suspended-growth-v4", "status": "completed", "checkpoint": str(checkpoint),
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
        "bedload_transport_contract": CONTRACT,
        "limitations": "v4 carrier-bound bedload, v3 finite exchange and slope; no adaptive time accuracy certification"}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
