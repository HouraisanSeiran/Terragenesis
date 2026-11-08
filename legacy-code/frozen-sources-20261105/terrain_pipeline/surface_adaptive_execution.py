"""Adaptive single-domain SSPRK2; all active leaves share one physical step."""

import math
import time

import numpy as np

from terrain_pipeline.regional_surface_hydraulics import validate_budget
from terrain_pipeline.surface_adaptive_geometry import MODEL, initial_leaf_state
from terrain_pipeline.surface_adaptive_hydraulics import adaptive_rhs, adaptive_drag, canonical_inventory, leaf_stages
from terrain_pipeline.surface_adaptive_refinement import anticipated_spacing_map, refine_adaptive_state
from terrain_pipeline.surface_adaptive_records import CompressedRecordList, CompressedGeometryHistory


def advance_adaptive_surface(geometry, *, initial_depth_m, forcing_interval_s, intervals,
                             forcing_provider, boundary_stage_provider, budget, dynamic_refinement=True,
                             halo_m=8, activity_depth_m=1e-8, step_observer=None, refinement_observer=None,
                             geometry_observer=None, history_directory=None, resource_observer=None):
    validate_budget(budget)
    if (type(intervals) is not int or intervals < 1 or not math.isfinite(forcing_interval_s) or forcing_interval_s <= 0 or
            intervals+1 > budget.max_snapshots or intervals*forcing_interval_s > budget.max_duration_s):
        raise ValueError("adaptive interval/time/snapshot budget invalid")
    canonical_shape = geometry["arrays"]["canonical_owner"].shape
    estimate = np.prod(canonical_shape)*8*(100+10*(intervals+1))
    if estimate > budget.max_bytes:
        raise ValueError("adaptive predeclared memory budget exceeded")
    state = initial_leaf_state(geometry, initial_depth_m)
    if np.any(state[:, 0] > budget.max_depth_m):
        raise ValueError("adaptive initial depth budget exceeded")
    started = time.monotonic()
    initial_volume = float(np.sum(state[:, 0]*geometry["arrays"]["leaf_area_m2"]))
    supplied = imported = exported = 0.
    steps = evaluations = limited = refinements = 0
    minimum_dt, maximum_dt, maximum_speed = math.inf, 0., 0.
    snapshots, transactions, interval_ledgers = CompressedRecordList(history_directory,append_observer=resource_observer), CompressedRecordList(history_directory,append_observer=resource_observer), []
    geometries = CompressedGeometryHistory(history_directory,append_observer=resource_observer)
    geometries.register(geometry)
    if geometry_observer is not None:
        geometry_observer(geometry)
    first_packets = CompressedRecordList(history_directory,append_observer=resource_observer)
    epoch_packets = CompressedRecordList(history_directory,append_observer=resource_observer)
    max_leaf_count = len(state)

    def retained_bytes(value):
        if hasattr(value, "storage_nbytes"):
            return value.storage_nbytes
        if isinstance(value, np.ndarray):
            return value.nbytes
        if isinstance(value, dict):
            return sum(retained_bytes(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return sum(retained_bytes(item) for item in value)
        return 0

    observed_peak_bytes = 0
    peak_work_disk_bytes = 0

    def check_memory():
        nonlocal observed_peak_bytes, peak_work_disk_bytes
        retained = retained_bytes(geometry)+retained_bytes(geometries)+retained_bytes(snapshots)+retained_bytes(transactions)+retained_bytes(first_packets)+retained_bytes(epoch_packets)
        scratch = state.nbytes*18+len(geometry["arrays"]["face_left"])*8*20
        observed_peak_bytes = max(observed_peak_bytes, retained+scratch)
        peak_work_disk_bytes = max(peak_work_disk_bytes, sum(item.temporary_storage_nbytes for item in (geometries,snapshots,transactions,first_packets,epoch_packets)))
        if peak_work_disk_bytes > 2*1024**3:
            raise RuntimeError("adaptive temporary history disk budget exceeded")
        if observed_peak_bytes > budget.max_bytes:
            raise RuntimeError("adaptive geometry/history/ledger memory budget exceeded")

    def begin_epoch(physical_time):
        a = geometry["arrays"]
        return dict(interval=interval, time_start_s=physical_time, geometry_identity=geometry["identity_sha256"],
            state_before=state.copy(), internal_transfer=np.zeros((len(a["face_left"]), 3)),
            boundary_transfer=np.zeros((len(a["boundary_cell"]), 3)),
            bed_impulse=np.zeros((len(state), 2)), manning_impulse=np.zeros((len(state), 2)),
            forcing_volume_m3=np.zeros(len(state)))

    def finish_epoch(physical_time):
        nonlocal evaluations
        if physical_time <= epoch["time_start_s"]:
            return
        epoch.update(time_end_s=physical_time, state_after=state.copy())
        _, endpoint = adaptive_rhs(geometry, state, tailwater_m=tailwater, gravity=budget.gravity_m_s2, dt=0.)
        epoch["internal_q_after_m3_s"] = endpoint["internal_flux_m2_s"][:, 0]
        epoch["boundary_q_after_m3_s"] = endpoint["boundary_flux_m2_s"][:, 0]
        evaluations += len(geometry["arrays"]["face_left"])+len(geometry["arrays"]["boundary_cell"])
        if evaluations > budget.max_face_evaluations:
            raise RuntimeError("adaptive endpoint face-work budget exceeded")
        epoch_packets.append(epoch)
        check_memory()

    def save_snapshot(physical_time):
        h, momentum = canonical_inventory(geometry, state)
        a = geometry["arrays"]
        stage = leaf_stages(state[:, 0], a["subcell_count"], a["sorted_subcell_bed_relative_m"], a["prefix_subcell_bed_relative_m"])
        snapshots.append(dict(time_s=physical_time, geometry_identity=geometry["identity_sha256"], state=state.copy(),
            leaf_row=a["leaf_row"].copy(), leaf_column=a["leaf_column"].copy(), leaf_spacing_m=a["leaf_spacing_m"].copy(),
            canonical_owner=a["canonical_owner"].copy(), leaf_stage_relative_m=stage,
            canonical_depth_m=h, canonical_momentum_m2_s=momentum,
            leaf_counts=geometry["metadata"]["leaf_counts"].copy(), leaf_area_m2=geometry["metadata"]["leaf_area_m2"].copy()))

    save_snapshot(0.)
    ledger = [[0., 0., 0., initial_volume, 0.]]
    for interval in range(intervals):
        forcing = np.asarray(forcing_provider(interval))
        tailwater = np.asarray(boundary_stage_provider(interval))
        if (forcing.dtype != np.float64 or forcing.shape != canonical_shape or not np.isfinite(forcing).all() or np.any(forcing < 0) or
                tailwater.dtype != np.float64 or tailwater.shape != geometry["arrays"]["boundary_cell"].shape or not np.isfinite(tailwater).all()):
            raise ValueError("complete finite canonical forcing and prescribed boundary stage required")
        current, end = interval*forcing_interval_s, (interval+1)*forcing_interval_s
        imported_interval, exported_interval, supplied_interval = 0., 0., 0.
        first = True
        epoch = begin_epoch(current)
        while current < end-1e-12:
            if steps >= budget.max_substeps or time.monotonic()-started > budget.max_wall_s:
                raise RuntimeError("adaptive physical execution resource budget exceeded")
            if dynamic_refinement and geometry["arrays"]["leaf_spacing_m"].max() > 1:
                h, _ = canonical_inventory(geometry, state)
                a = geometry["arrays"]
                desired = anticipated_spacing_map(h, max_leaf_spacing_m=int(a["leaf_spacing_m"].max()),
                    halo_m=halo_m, activity_depth_m=activity_depth_m, canonical_forcing_m3_s=forcing,
                    forcing_prediction_dt_s=budget.max_dt_s,
                    boundary_kind=a["boundary_kind"], tailwater_m=tailwater, canonical_bed_m=a["canonical_bed_m"])
                next_geometry, next_state, transaction = refine_adaptive_state(geometry, state, desired)
                if transaction is not None:
                    finish_epoch(current)
                    transaction.update(time_s=current, interval=interval)
                    transactions.append(transaction)
                    if refinement_observer is not None:
                        refinement_observer(transaction)
                    geometry, state = next_geometry, next_state
                    geometries.register(geometry)
                    if geometry_observer is not None:
                        geometry_observer(geometry)
                    refinements += transaction["refined_parent_count"]
                    epoch = begin_epoch(current)
                    check_memory()
            a, meta = geometry["arrays"], geometry["metadata"]
            max_leaf_count = max(max_leaf_count, len(state))
            if len(state) > budget.max_cells:
                raise RuntimeError("adaptive active-leaf budget exceeded")
            stage = leaf_stages(state[:, 0], a["subcell_count"], a["sorted_subcell_bed_relative_m"], a["prefix_subcell_bed_relative_m"])
            velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            maximum_h = np.maximum(stage-a["sorted_subcell_bed_relative_m"][a["subcell_offset"]], 0.)
            local_speed = abs(velocity).sum(axis=1)+2*np.sqrt(budget.gravity_m_s2*maximum_h)
            exterior_bed = np.maximum(a["boundary_bed_relative_m"], a["boundary_crest_m"]-meta["hydraulic_datum_m"])
            exterior_stage = np.where(a["boundary_kind"] == 1, exterior_bed, tailwater-meta["hydraulic_datum_m"])
            exterior_h = np.maximum(exterior_stage-exterior_bed, 0.)
            speed = max(float(local_speed.max(initial=0)), float(2*np.sqrt(budget.gravity_m_s2*exterior_h[a["boundary_kind"] != 0]).max(initial=0)))
            dt = min(budget.max_dt_s, budget.inertial_cfl*float(a["leaf_spacing_m"].min())/max(speed, 1e-12), end-current)
            source = np.bincount(a["canonical_owner"].ravel(), weights=forcing.ravel(), minlength=len(state))/a["leaf_area_m2"]
            before = state.copy()
            rhs1, witness1 = adaptive_rhs(geometry, state, tailwater_m=tailwater, gravity=budget.gravity_m_s2, dt=dt)
            rhs1[:, 0] += source
            trial = state+dt*rhs1
            if np.any(trial[:, 0] < 0):
                raise RuntimeError("adaptive first RK positivity refusal")
            rhs2, witness2 = adaptive_rhs(geometry, trial, tailwater_m=tailwater, gravity=budget.gravity_m_s2, dt=dt)
            rhs2[:, 0] += source
            updated = .5*state+.5*(trial+dt*rhs2)
            before_drag = updated[:, 1:].copy()
            damping, drag_factor = adaptive_drag(geometry, updated, dt=dt, gravity=budget.gravity_m_s2, roughness=budget.roughness_s_m_third)
            updated[:, 1:] *= damping[:, None]
            if (not np.isfinite(updated).all() or np.any(updated[:, 0] < 0) or np.any(updated[:, 0] > budget.max_depth_m)):
                raise RuntimeError("adaptive final RK depth refusal; no clipping")
            boundary_q = .5*(witness1["boundary_flux_m2_s"][:, 0]+witness2["boundary_flux_m2_s"][:, 0])
            step_imported, step_exported = float(dt*np.maximum(-boundary_q, 0.).sum()), float(dt*np.maximum(boundary_q, 0.).sum())
            step_supplied = float(dt*forcing.sum())
            imported += step_imported
            exported += step_exported
            supplied += step_supplied
            imported_interval += step_imported
            exported_interval += step_exported
            supplied_interval += step_supplied
            limited += witness1["limited_donors"]+witness2["limited_donors"]
            epoch["internal_transfer"] += .5*dt*(witness1["internal_flux_m2_s"]+witness2["internal_flux_m2_s"])
            epoch["boundary_transfer"] += .5*dt*(witness1["boundary_flux_m2_s"]+witness2["boundary_flux_m2_s"])
            epoch["bed_impulse"] += .5*dt*(witness1["bed_source"][:, 1:]+witness2["bed_source"][:, 1:])*a["leaf_area_m2"][:, None]
            epoch["manning_impulse"] += (updated[:, 1:]-before_drag)*a["leaf_area_m2"][:, None]
            epoch["forcing_volume_m3"] += dt*source*a["leaf_area_m2"]
            if first or step_observer is not None:
                packet = dict(interval=interval, time_start_s=current, dt_s=dt, geometry_identity=geometry["identity_sha256"],
                    state_before=before, state_predictor=trial, state_after=updated.copy(),
                    rk1_internal_flux=witness1["internal_flux_m2_s"], rk2_internal_flux=witness2["internal_flux_m2_s"],
                    rk1_boundary_flux=witness1["boundary_flux_m2_s"], rk2_boundary_flux=witness2["boundary_flux_m2_s"],
                    rk1_bed_source=witness1["bed_source"], rk2_bed_source=witness2["bed_source"],
                    manning_momentum_change=updated[:, 1:]-before_drag, manning_inverse_depth_third_mean=drag_factor,
                    leaf_area_m2=a["leaf_area_m2"].copy(), face_left=a["face_left"].copy(), face_right=a["face_right"].copy(),
                    face_axis=a["face_axis"].copy(), face_crest_relative_m=a["face_crest_relative_m"].copy(),
                    boundary_cell=a["boundary_cell"].copy(), forcing_m3_s=source*a["leaf_area_m2"], tailwater_m=tailwater.copy())
                if first:
                    first_packets.append(packet)
                if step_observer is not None:
                    step_observer(packet)
                first = False
            state = updated
            current += dt
            steps += 1
            evaluations += 2*(len(a["face_left"])+len(a["boundary_cell"]))
            if evaluations > budget.max_face_evaluations:
                raise RuntimeError("adaptive face-work budget exceeded")
            minimum_dt, maximum_dt = min(minimum_dt, dt), max(maximum_dt, dt)
            maximum_speed = max(maximum_speed, speed)
        finish_epoch(end)
        volume = float(np.sum(state[:, 0]*geometry["arrays"]["leaf_area_m2"]))
        ledger.append([supplied, imported, exported, volume, volume-initial_volume-supplied-imported+exported])
        interval_ledgers.append(dict(interval=interval, supplied_m3=supplied_interval, boundary_input_m3=imported_interval,
            boundary_output_m3=exported_interval, final_volume_m3=volume))
        save_snapshot(end)
        check_memory()
    return dict(geometry=geometry, geometries=geometries, snapshots=snapshots, refinement_transactions=transactions,
        first_rk_packets=first_packets, epoch_packets=epoch_packets, ledger=np.asarray(ledger), interval_ledgers=interval_ledgers,
        metadata=dict(model=MODEL, execution_backend="numba_scalar_components_fastmath_false_lossless_npz_level1_workspace_segmented_spool", status="completed", wall_s=time.monotonic()-started, substeps=steps, face_evaluations=evaluations,
            initial_volume_m3=initial_volume, final_volume_m3=float(ledger[-1][3]), boundary_input_m3=imported,
            boundary_output_m3=exported, supplied_m3=supplied, maximum_active_leaf_count=max_leaf_count,
            finest_spacing_m=int(geometry["arrays"]["leaf_spacing_m"].min()), minimum_dt_s=minimum_dt, maximum_dt_s=maximum_dt,
            maximum_wave_speed_m_s=maximum_speed, limited_donors=limited, refined_parent_count=refinements,
            dynamic_refinement=dynamic_refinement, halo_m=halo_m, activity_depth_m=activity_depth_m,
            estimated_peak_bytes=int(estimate), observed_peak_bytes_estimate=int(observed_peak_bytes), uniform_coarse_convergence_claim=False,
            peak_work_disk_bytes=int(peak_work_disk_bytes), history_serialized_bytes=int(sum(item.serialized_nbytes for item in (geometries,snapshots,transactions,first_packets,epoch_packets))),
            scope="single-domain adaptive independent leaf evolution; canonical inventory reconstruction is not a hidden 1m solve",
            limitation="refinement only; active depth threshold predeclared; coarse represented stage/velocity uniform; engineering boundaries uncalibrated"))
