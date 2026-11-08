"""Explicit MUSCL hydrostatic shallow-water execution with momentum witnesses."""

import math
import time

import numpy as np

from terrain_pipeline.regional_surface_hydraulics import validate_budget


def advance_shallow_water(geometry, *, rhs, model, scope, physical_limitation, initial_depth_m, forcing_interval_s, intervals, forcing_provider,
                         boundary_stage_provider, source_identity, forcing_identity, budget,
                         snapshot_interval_s, interval_observer, momentum_observer, hydraulic_datum_m=None,
                         wave_speed=None, stage_provider=None, face_evaluation_multiplier=1):
    validate_budget(budget)
    a, meta = geometry["arrays"],geometry["metadata"]
    bed = a["H2_m"]
    initial = np.asarray(initial_depth_m)
    if (initial.dtype != np.float64 or initial.shape != bed.shape or not np.isfinite(initial).all() or
            np.any(initial < 0) or np.any(initial > budget.max_depth_m)):
        raise ValueError("shallow-water initial depth invalid")
    if (bed.size > budget.max_cells or intervals+1 > budget.max_snapshots or
            intervals*forcing_interval_s > budget.max_duration_s or snapshot_interval_s != forcing_interval_s):
        raise ValueError("shallow-water domain/time/snapshot budget invalid")
    support_bytes=sum(a[name].nbytes for name in a if "subcell_" in name or "segment_" in name)
    segment_work_bytes=8*20*face_evaluation_multiplier*(len(a["face_left"])+len(a["boundary_cell"]))
    estimate = bed.size*8*(40+10*(intervals+1))+support_bytes+segment_work_bytes
    if estimate > budget.max_bytes:
        raise ValueError("shallow-water saved momentum memory budget exceeded")
    datum = float(bed.min()) if hydraulic_datum_m is None else hydraulic_datum_m
    relative_bed = bed-datum
    state = np.column_stack((initial.ravel(),np.zeros((bed.size,2))))
    spacing, area = meta["spacing_m"],meta["spacing_m"]**2
    stages = [state.copy()]
    times = [0.]
    initial_volume = float(initial.sum()*area)
    supplied=imported=exported=0.
    ledgers = [[0.,0.,0.,initial_volume,0.]]
    steps=evaluations=limited=0
    minimum_dt=math.inf
    maximum_dt=maximum_speed=0.
    started=time.monotonic()
    last_i=np.zeros(len(a["face_left"]))
    last_b=np.zeros(len(a["boundary_cell"]))
    for interval in range(intervals):
        source=np.asarray(forcing_provider(interval))
        tailwater=np.asarray(boundary_stage_provider(interval))
        if (source.dtype != np.float64 or source.shape != bed.shape or not np.isfinite(source).all() or np.any(source < 0) or
                tailwater.dtype != np.float64 or tailwater.shape != (len(last_b),) or not np.isfinite(tailwater).all()):
            raise ValueError("shallow-water complete finite forcing/tailwater required")
        source=source.ravel()/area
        tail=tailwater-datum
        start_state=state.copy()
        transfer_i=np.zeros_like(last_i)
        transfer_b=np.zeros_like(last_b)
        momentum_transfer_i=np.zeros((len(last_i),2))
        momentum_transfer_b=np.zeros((len(last_b),2))
        before_i,before_b=last_i.copy(),last_b.copy()
        bed_impulse=np.zeros((bed.size,2))
        drag_impulse=np.zeros((bed.size,2))
        supplied_cell=np.zeros(bed.size)
        current=interval*forcing_interval_s
        end=(interval+1)*forcing_interval_s
        first=True
        while current < end-1e-12:
            if steps >= budget.max_substeps or time.monotonic()-started > budget.max_wall_s:
                raise RuntimeError("shallow-water execution resource budget exceeded")
            velocity=np.divide(state[:,1:],state[:,0,None],out=np.zeros_like(state[:,1:]),where=state[:,0,None] > 0)
            speed=float((np.sum(abs(velocity),axis=1)+2*np.sqrt(budget.gravity_m_s2*state[:,0])).max(initial=0))
            if wave_speed is not None:
                speed=max(speed,wave_speed(state,budget.gravity_m_s2))
            external_bed=(a["boundary_segment_crest_relative_m"].min(axis=1) if stage_provider is not None
                else relative_bed.ravel()[a["boundary_cell"]])
            external_bed=np.maximum(external_bed,a["boundary_crest_m"]-datum)
            exterior_stage=np.where(a["boundary_kind"] == 1,external_bed,tail)
            external_depth=np.maximum(exterior_stage-external_bed,0.)
            speed=max(speed,float(2*np.sqrt(budget.gravity_m_s2*external_depth[a["boundary_kind"] != 0]).max(initial=0)))
            dt=min(budget.max_dt_s,budget.inertial_cfl*spacing/max(speed,1e-12),end-current)
            rhs1,witness1=rhs(state,relative_bed,spacing=spacing,gravity=budget.gravity_m_s2,
                boundary_kind=a["boundary_kind"],tailwater=tail,roughness=budget.roughness_s_m_third,dt=dt,boundary_crest=a["boundary_crest_m"]-datum)
            rhs1[:,0]+=source
            trial=state+dt*rhs1
            if np.any(trial[:,0] < 0):
                raise RuntimeError("shallow-water first RK positivity refusal")
            rhs2,witness2=rhs(trial,relative_bed,spacing=spacing,gravity=budget.gravity_m_s2,
                boundary_kind=a["boundary_kind"],tailwater=tail,roughness=budget.roughness_s_m_third,dt=dt,boundary_crest=a["boundary_crest_m"]-datum)
            rhs2[:,0]+=source
            updated=.5*state+.5*(trial+dt*rhs2)
            before_drag=updated[:,1:].copy()
            wet=updated[:,0] > 0
            magnitude=np.linalg.norm(updated[wet,1:],axis=1)
            depth_power=updated[wet,0]**(7/3)
            drag_denominator=depth_power+dt*budget.gravity_m_s2*budget.roughness_s_m_third**2*magnitude
            damping=np.divide(depth_power,drag_denominator,out=np.zeros_like(depth_power),where=drag_denominator > 0)
            updated[wet,1:]*=damping[:,None]
            if (not np.isfinite(updated).all() or np.any(updated[:,0] < 0) or np.any(updated[:,0] > budget.max_depth_m)):
                raise RuntimeError("shallow-water final RK depth refusal; no clipping")
            qi=.5*(witness1["internal_flux"][:,0]+witness2["internal_flux"][:,0])*spacing
            qb=.5*(witness1["boundary_flux"][:,0]+witness2["boundary_flux"][:,0])*spacing
            bed_step=.5*dt*(witness1["bed_source"][:,1:]+witness2["bed_source"][:,1:])
            if first:
                momentum_observer(dict(interval=interval,time_start_s=current,dt_s=dt,
                    state_before=state.copy(),state_predictor=trial.copy(),state_after=updated.copy(),forcing_m3_s=source*area,
                    tailwater_m=tailwater.copy(),rk1_internal_flux=witness1["internal_flux"],rk2_internal_flux=witness2["internal_flux"],
                    rk1_boundary_flux=witness1["boundary_flux"],rk2_boundary_flux=witness2["boundary_flux"],
                    rk1_bed_source=witness1["bed_source"],rk2_bed_source=witness2["bed_source"],manning_momentum_change=updated[:,1:]-before_drag))
                first=False
            transfer_i+=dt*qi
            transfer_b+=dt*qb
            momentum_transfer_i+=.5*dt*spacing*(witness1["internal_flux"][:,1:]+witness2["internal_flux"][:,1:])
            momentum_transfer_b+=.5*dt*spacing*(witness1["boundary_flux"][:,1:]+witness2["boundary_flux"][:,1:])
            bed_impulse+=bed_step
            drag_impulse+=updated[:,1:]-before_drag
            supplied_cell+=dt*source*area
            supplied+=float(dt*source.sum()*area)
            imported+=float(dt*np.maximum(-qb,0).sum())
            exported+=float(dt*np.maximum(qb,0).sum())
            limited+=witness1["limited_donors"]+witness2["limited_donors"]
            state=updated
            current+=dt
            steps+=1
            evaluations+=2*face_evaluation_multiplier*(len(qi)+len(qb))
            if evaluations > budget.max_face_evaluations:
                raise RuntimeError("shallow-water face work budget exceeded")
            minimum_dt=min(minimum_dt,dt)
            maximum_dt=max(maximum_dt,dt)
            maximum_speed=max(maximum_speed,speed)
        _,endpoint=rhs(state,relative_bed,spacing=spacing,gravity=budget.gravity_m_s2,
            boundary_kind=a["boundary_kind"],tailwater=tail,roughness=budget.roughness_s_m_third,dt=0.,boundary_crest=a["boundary_crest_m"]-datum)
        evaluations+=face_evaluation_multiplier*(len(last_i)+len(last_b))
        if evaluations > budget.max_face_evaluations:
            raise RuntimeError("shallow-water endpoint face work budget exceeded")
        last_i=endpoint["internal_flux"][:,0]*spacing
        last_b=endpoint["boundary_flux"][:,0]*spacing
        interval_observer(dict(interval=interval,time_start_s=interval*forcing_interval_s,time_end_s=end,
            depth_before_m=start_state[:,0],depth_after_m=state[:,0].copy(),momentum_before=start_state[:,1:],momentum_after=state[:,1:].copy(),
            internal_transfer_m3=transfer_i,boundary_transfer_m3=transfer_b,forcing_volume_m3=supplied_cell,
            internal_momentum_transfer=momentum_transfer_i,boundary_momentum_transfer=momentum_transfer_b,
            bed_momentum_change=bed_impulse,manning_momentum_change=drag_impulse,
            internal_q_before_m3_s=before_i,internal_q_after_m3_s=last_i.copy(),
            boundary_q_before_m3_s=before_b,boundary_q_after_m3_s=last_b.copy()))
        stages.append(state.copy())
        times.append(end)
        volume=float(state[:,0].sum()*area)
        ledgers.append([supplied,imported,exported,volume,volume-initial_volume-supplied-imported+exported])
    saved=np.asarray(stages)
    result = dict(arrays=dict(time_s=np.asarray(times),depth_m=saved[:,:,0].reshape(-1,*bed.shape),
        momentum_x_m2_s=saved[:,:,1].reshape(-1,*bed.shape),momentum_z_m2_s=saved[:,:,2].reshape(-1,*bed.shape),
        initial_depth_m=initial.copy(),ledger=np.asarray(ledgers),final_internal_q_m3_s=last_i,final_boundary_q_m3_s=last_b),
        metadata=dict(schema=model,hydraulic_model=model,status="completed",failure=None,budget=vars(budget),
            source_identity=source_identity,forcing_identity=forcing_identity,requested_time_s=intervals*forcing_interval_s,
            committed_time_s=intervals*forcing_interval_s,substeps=steps,face_evaluations=evaluations,wall_s=time.monotonic()-started,
            initial_volume_m3=initial_volume,final_volume_m3=float(state[:,0].sum()*area),supplied_m3=supplied,
            boundary_input_m3=imported,boundary_output_m3=exported,estimated_peak_bytes=estimate,
            scope=scope),
        diagnostics=dict(minimum_dt_s=minimum_dt,maximum_dt_s=maximum_dt,maximum_wave_speed_m_s=maximum_speed,
            limited_donor_count=limited,negative_water_clip_count=0,physical_limitation=physical_limitation))
    if stage_provider is not None:
        result["arrays"]["stage_relative_m"] = np.asarray([stage_provider(item[:,0]) for item in saved]).reshape(-1,*bed.shape)
    return result
