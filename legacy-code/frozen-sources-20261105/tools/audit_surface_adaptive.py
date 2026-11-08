"""Independent adaptive canonical segment equations; no adaptive solver imports."""

import argparse
import json
import hashlib
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ.setdefault(name,"1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np
import psutil

from terrain_pipeline.surface_adaptive_io import near,storage_stage,load_adaptive_run
from terrain_pipeline.mountain_source_adapter import file_sha256,publish_bytes
from tools.audit_single_domain_fine_stage import read_json,read_bundle,audit_fan
from tools.single_domain_shallow_water_audit import face_flux


def physical_rhs(geometry,state,tailwater,gravity,dt):
    a,m = geometry["arrays"],geometry["metadata"]
    stage = storage_stage(state[:,0],geometry)
    velocity = np.divide(state[:,1:],state[:,0,None],out=np.zeros_like(state[:,1:]),where=state[:,0,None]>0)
    left,right,axis = a["face_left"],a["face_right"],a["face_axis"]
    cells,area = a["boundary_cell"],a["leaf_area_m2"]
    internal,boundary = np.zeros((len(left),3)),np.zeros((len(cells),3))
    pressure = np.zeros_like(state)
    for direction in (0,1):
        mask = axis==direction
        crest = a["face_crest_relative_m"][mask]
        hl,hr = np.maximum(stage[left[mask]]-crest,0),np.maximum(stage[right[mask]]-crest,0)
        first,second = np.column_stack((hl,hl[:,None]*velocity[left[mask]])),np.column_stack((hr,hr[:,None]*velocity[right[mask]]))
        flux,_,_ = face_flux(first,second,crest,crest,gravity,direction)
        internal[mask] = flux
        np.add.at(pressure[:,direction+1],left[mask],.5*gravity*hl**2/area[left[mask]])
        np.add.at(pressure[:,direction+1],right[mask],-.5*gravity*hr**2/area[right[mask]])
        mask = a["boundary_axis"]==direction
        ids,kind,sign = cells[mask],a["boundary_kind"][mask],a["boundary_sign"][mask]
        crest = a["boundary_bed_relative_m"][mask].copy()
        opened = kind!=0
        crest[opened] = np.maximum(crest[opened],a["boundary_crest_m"][mask][opened]-m["hydraulic_datum_m"])
        h = np.maximum(stage[ids]-crest,0)
        first = np.column_stack((h,h[:,None]*velocity[ids]))
        ghost = first.copy()
        ghost[:,direction+1] *= -1
        outside = np.where(kind==1,crest,tailwater[mask]-m["hydraulic_datum_m"])
        ghost[opened,0] = np.maximum(outside[opened]-crest[opened],0)
        ghost[opened,1:] = 0
        first[:,direction+1] *= sign
        ghost[:,direction+1] *= sign
        flux,_,_ = face_flux(first,ghost,crest,crest,gravity,direction)
        flux[:,direction+1] *= sign
        boundary[mask] = flux
        np.add.at(pressure[:,direction+1],ids,sign*.5*gravity*h**2/area[ids])
    outgoing = np.bincount(left,weights=np.maximum(internal[:,0],0),minlength=len(state))
    outgoing += np.bincount(right,weights=np.maximum(-internal[:,0],0),minlength=len(state))
    outgoing += np.bincount(cells,weights=np.maximum(boundary[:,0],0),minlength=len(state))
    scale = np.ones(len(state))
    limited = outgoing*dt>state[:,0]*area
    scale[limited] = state[limited,0]*area[limited]/(dt*outgoing[limited])*(1-1e-12)
    internal *= np.where(internal[:,0]>=0,scale[left],scale[right])[:,None]
    boundary *= np.where(boundary[:,0]>=0,scale[cells],1.)[:,None]
    rhs = pressure.copy()
    np.add.at(rhs,left,-internal/area[left,None])
    np.add.at(rhs,right,internal/area[right,None])
    np.add.at(rhs,cells,-boundary/area[cells,None])
    return rhs,internal,boundary,pressure


def audit_step(packet,geometry,budget):
    a = geometry["arrays"]
    before,predictor,after = (packet[name] for name in ("state_before","state_predictor","state_after"))
    dt,g = packet["dt_s"],budget["gravity_m_s2"]
    area = a["leaf_area_m2"]
    if not 0<dt<=budget["max_dt_s"] or any(np.any(state[:,0]<0) for state in (before,predictor,after)):
        raise ValueError("adaptive independent sampled time/depth mismatch")
    stage = storage_stage(before[:,0],geometry)
    minimum_bed = a["sorted_subcell_bed_relative_m"][a["subcell_offset"]]
    velocity = np.divide(before[:,1:],before[:,0,None],out=np.zeros_like(before[:,1:]),where=before[:,0,None]>0)
    speed = float((abs(velocity).sum(axis=1)+2*np.sqrt(g*np.maximum(stage-minimum_bed,0))).max(initial=0))
    outside_bed = np.maximum(a["boundary_bed_relative_m"],a["boundary_crest_m"]-geometry["metadata"]["hydraulic_datum_m"])
    outside = np.where(a["boundary_kind"]==1,outside_bed,packet["tailwater_m"]-geometry["metadata"]["hydraulic_datum_m"])
    speed = max(speed,float((2*np.sqrt(g*np.maximum(outside-outside_bed,0)[a["boundary_kind"]!=0])).max(initial=0)))
    if dt>budget["inertial_cfl"]*a["leaf_spacing_m"].min()/max(speed,1e-12)+1e-12:
        raise ValueError("adaptive independent CFL mismatch")
    equations = []
    for number,state in ((1,before),(2,predictor)):
        rhs,internal,boundary,pressure = physical_rhs(geometry,state,packet["tailwater_m"],g,dt)
        for name,expected in (("internal_flux",internal),("boundary_flux",boundary),("bed_source",pressure)):
            near(packet[f"rk{number}_"+name],expected,"independent physical RK "+name)
        rhs[:,0] += packet["forcing_m3_s"]/area
        equations.append(rhs)
    near(predictor,before+dt*equations[0],"independent predictor")
    updated = .5*before+.5*(predictor+dt*equations[1])
    stage = storage_stage(updated[:,0],geometry)
    factor = np.zeros(len(state))
    for cell,count in enumerate(a["subcell_count"]):
        offset = a["subcell_offset"][cell]
        h = np.maximum(stage[cell]-a["sorted_subcell_bed_relative_m"][offset:offset+count],0)
        factor[cell] = np.sum(h[h>0]**(-1/3))/count
    near(packet["manning_inverse_depth_third_mean"],factor,"independent canonical Manning integral")
    squared = updated[:,0]**2
    denominator = squared+dt*g*budget["roughness_s_m_third"]**2*np.hypot(updated[:,1],updated[:,2])*factor
    damping = np.divide(squared,denominator,out=np.zeros_like(squared),where=denominator>0)
    before_drag = updated[:,1:].copy()
    updated[:,1:] *= damping[:,None]
    near(after,updated,"independent SSPRK2 and canonical drag")
    near(packet["manning_momentum_change"],updated[:,1:]-before_drag,"independent Manning impulse")
    return dict(equations_sampled=True,physical_HLL_verified=True,canonical_Manning_verified=True,CFL_verified=True)


def audit_frame(frame_record,bed_record,snapshot_record,geometry,number):
    frame,metadata,_ = read_bundle(frame_record)
    bed,bed_metadata,bed_id = read_bundle(bed_record)
    snapshot,snapshot_metadata,snapshot_id = read_bundle(snapshot_record)
    if (metadata.get("schema")!="surface-adaptive-canonical-water-fan-v1" or metadata["bed_identity"]!=bed_id
            or metadata["adaptive_snapshot_identity"]!=snapshot_id or metadata["adaptive_geometry_identity"]!=geometry["identity_sha256"]
            or metadata["state_index"]!=number or metadata["time_s"]!=snapshot_metadata["time_s"]
            or not np.array_equal(bed["H2_m"],geometry["arrays"]["canonical_bed_m"])
            or bed_metadata["origin_m_xz"]!=geometry["metadata"]["origin_m_xz"]
            or not np.array_equal(frame["cell_depth_m"],snapshot["canonical_depth_m"])):
        raise ValueError("adaptive independent frame original bed/snapshot/geometry/time binding mismatch")
    return audit_fan(bed,frame,1.)


def audit_saved(index_record,output,*,physical=True):
    started = time.monotonic()
    index = read_json(index_record)
    run_records = {"run":index_record} if index.get("schema")=="surface-adaptive-run-index-v1" else {name:case["run"] for name,case in index["cases"].items()}
    cases,depths = {},{}
    for name,pin in run_records.items():
        print("independent adaptive "+name,flush=True)
        loaded = load_adaptive_run(pin["path"],expected_sha256=pin["expected_sha256"])
        samples = []
        if physical:
            for packet in loaded["first_steps"]:
                samples.append(audit_step(packet,loaded["geometries"][packet["geometry_identity"]],loaded["index"]["budget"]))
            for epoch in loaded["epochs"]:
                geometry = loaded["geometries"][epoch["geometry_identity"]]
                interval = epoch["interval"]
                _,internal,boundary,_ = physical_rhs(geometry,epoch["state_after"],loaded["forcing"]["tailwater_m"][interval],loaded["index"]["budget"]["gravity_m_s2"],0.)
                near(epoch["internal_q_after_m3_s"],internal[:,0],"independent epoch endpoint internal Q")
                near(epoch["boundary_q_after_m3_s"],boundary[:,0],"independent epoch endpoint boundary Q")
        snapshots = loaded["snapshots"]
        initial = snapshots[0]["canonical_depth_m"]
        depths[name] = np.asarray([snapshot["canonical_depth_m"] for snapshot in snapshots])
        drift = max(float(abs(snapshot["canonical_depth_m"]-initial).max()) for snapshot in snapshots)
        source_free = bool(np.all(loaded["forcing"]["forcing_m3_s"]==0))
        cases[name] = dict(geometries_verified=len(loaded["geometries"]),snapshots_verified=len(snapshots),epochs_verified=len(loaded["epochs"]),
            refinements_verified=len(loaded["refinements"]),first_steps_verified=len(loaded["first_steps"]),physical_samples=samples,
            complete_leaf_mass_momentum_chain_verified=True,original_snapshot_inventory_verified=True,
            source_free=source_free,maximum_canonical_depth_change_m=drift,
            source_semantics=loaded["source_semantics"],
            independent_import_lower_bound_m3=sum(float(np.maximum(-epoch["boundary_transfer"][:,0],0).sum()) for epoch in loaded["epochs"]),
            gross_boundary_import_m3=float(loaded["states"]["ledger"][-1,1]),
            actual_substeps=loaded["states"]["solver_metadata"]["substeps"],
            maximum_dt_s=loaded["index"]["budget"]["max_dt_s"],
            forcing_interval_s=loaded["forcing"]["dt_s"],
            local_forcing_sha256=hashlib.sha256(loaded["forcing"]["forcing_m3_s"].tobytes()).hexdigest(),
            canonical_initial_inventory_sha256=hashlib.sha256(initial.tobytes()).hexdigest(),
            initial_depth=initial.copy(),
            source_record=loaded["index"]["source_record"],
            snapshot_times_s=[snapshot["time_s"] for snapshot in snapshots],
            source_free_lake_gate_passed=(drift<=1e-9) if "lake" in name and source_free else None,
            uniform_coarse_convergence_claim=False,solver_advanced=False)
        memory = psutil.Process().memory_info()
        if max(getattr(memory,"peak_wset",memory.rss),getattr(memory,"peak_pagefile",memory.vms))>1073741824 or time.monotonic()-started>1800:
            raise RuntimeError("adaptive independent audit resource exceeded")
    if file_sha256(index_record["path"])!=index_record["expected_sha256"]:
        raise ValueError("adaptive observed index changed")
    memory = psutil.Process().memory_info()
    result = dict(schema="surface-adaptive-independent-audit-v1",index_record=index_record,cases=cases,
        pure_saved_chain_read=True,equations_sampled=physical,physical_equations_independently_verified=physical,
        production_adaptive_helpers_called=False,solver_advanced=False,stage_accepted=False,
        hydraulic_ready=False,natural_outlet_verified=False,publishable=False,
        resource=dict(elapsed_s=time.monotonic()-started,peak_rss_bytes=int(getattr(memory,"peak_wset",memory.rss)),peak_private_bytes=int(getattr(memory,"peak_pagefile",memory.vms))),
        code_sha256=file_sha256(Path(__file__)),limitations=["First-step physical equations are sampled; all geometry epochs and refinement inventory transactions are checked.",
            "Adaptive agreement is not a uniform coarse-grid convergence claim; reference comparisons and original strict stage gates require explicit independent evaluation."])
    if index.get("schema")=="single-domain-adaptive-stage-index-v1":
        result.update(audit_stage_gates(index,cases,depths))
    for case in cases.values():
        case.pop("initial_depth")
    root = Path(output).resolve()
    root.relative_to(ROOT)
    root.mkdir(parents=True,exist_ok=False)
    target = root/"report.json"
    publish_bytes(target,(json.dumps(result,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    print(json.dumps(dict(path=str(target),expected_sha256=file_sha256(target))),flush=True)
    return result


def audit_stage_gates(index,cases,depths):
    declaration = read_json(index["predeclared"])
    source = read_json(index["source_v7_index"])
    source_report = read_json(index["source_v7_report"])
    if (source["report"]!=index["source_v7_report"] or declaration["source_v7_index"]!=index["source_v7_index"]
            or source_report["all_predeclared_gates_passed"] is not False or index.get("uniform_coarse_convergence_claim") is not False):
        raise ValueError("adaptive independent original uniform evidence/claim mismatch")
    gates = declaration["gates"]
    required_cases = {"dry-rain-root4","zero-source-lake-root4","tailwater-baseline-root4",
        "tailwater-rise-root1","tailwater-rise-root1-half-dt","tailwater-rise-root2","tailwater-rise-root4"}
    if set(cases)!=required_cases or len(index["comparisons"])!=4:
        raise ValueError("adaptive independent complete seven-case stage/four comparisons required")
    if gates["max_saved_depth_difference_m"]!=.01 or gates["max_relative_surface_volume_difference"]!=.01 or gates["max_lake_depth_change_m"]!=1e-9:
        raise ValueError("adaptive independent strict original gates changed")
    for name,case in cases.items():
        source_name = index["cases"][name]["source_v7_case"]
        if (case["source_record"]!=source["cases"][source_name]["run"]
                or case["snapshot_times_s"]!=[0.,30.,60.,90.,120.]):
            raise ValueError("adaptive independent original case source or physical timeline mismatch")
        semantics = case["source_semantics"]
        if name=="zero-source-lake-root4":
            if semantics!="explicit zero-source closed lake correction of prior soil-release case":
                raise ValueError("adaptive independent only static lake may override original forcing")
        elif semantics!="original saved canonical source/time schedule":
            raise ValueError("adaptive independent nonstatic forcing differs from original four-store source")
    baseline,rise = cases["tailwater-baseline-root4"],cases["tailwater-rise-root4"]
    if (baseline["maximum_dt_s"]!=rise["maximum_dt_s"] or baseline["forcing_interval_s"]!=rise["forcing_interval_s"]
            or baseline["local_forcing_sha256"]!=rise["local_forcing_sha256"]):
        raise ValueError("adaptive controlled tailwater baseline/run forcing or cadence changed")
    near(baseline["initial_depth"],rise["initial_depth"],"controlled tailwater common original initial inventory")
    reference_case = source["cases"]["tailwater-rise-1m-half-dt"]
    reference_run = read_json(reference_case["run"])
    reference,_,_ = read_bundle(reference_run["states"])
    times = reference["time_s"]
    if not np.array_equal(times,np.arange(5)*30.):
        raise ValueError("adaptive independent all saved reference times mismatch")
    reference_depth = reference["depth_m"]
    def compare(first,second,label):
        if first.shape!=second.shape:
            raise ValueError("adaptive independent fullwindow comparison shape mismatch")
        error = float(abs(first-second).max())
        volume = float((abs(first.sum(axis=(1,2))-second.sum(axis=(1,2)))/np.maximum(second.sum(axis=(1,2)),1e-12)).max())
        return dict(label=label,maximum_saved_depth_difference_m=error,maximum_relative_surface_volume_difference=volume,passed=error<=.01 and volume<=.01)
    comparisons = [compare(depths["tailwater-rise-root1"],depths["tailwater-rise-root1-half-dt"],"independent root1 temporal")]
    changed = cases["tailwater-rise-root1-half-dt"]["actual_substeps"]>cases["tailwater-rise-root1"]["actual_substeps"]
    comparisons[0].update(actual_temporal_resolution_changed=changed,passed=comparisons[0]["passed"] and changed)
    comparisons += [compare(depths[f"tailwater-rise-root{size}"],reference_depth,f"independent adaptive root{size} vs uniform1m") for size in (1,2,4)]
    for calculated,reported in zip(comparisons,index["comparisons"]):
        near(np.asarray(calculated["maximum_saved_depth_difference_m"]),np.asarray(reported["maximum_saved_depth_difference_m"]),"reported fullwindow depth comparison")
        near(np.asarray(calculated["maximum_relative_surface_volume_difference"]),np.asarray(reported["maximum_relative_surface_volume_difference"]),"reported fullwindow volume comparison")
    lake = cases["zero-source-lake-root4"]
    if not lake["source_free"]:
        raise ValueError("adaptive independent static lake has real saved source")
    response = depths["tailwater-rise-root4"][-1]-depths["tailwater-baseline-root4"][-1]
    imported = cases["tailwater-rise-root4"]["independent_import_lower_bound_m3"]
    scenarios = dict(zero_source_lake=dict(max_depth_change_m=lake["maximum_canonical_depth_change_m"],passed=lake["maximum_canonical_depth_change_m"]<=1e-9),
        controlled_tailwater=dict(max_depth_increase_m=float(response.max()),positive_response_cells=int(np.sum(response>gates["minimum_tailwater_response_m"])),
            imported_volume_lower_bound_m3=imported,passed=float(response.max())>gates["minimum_tailwater_response_m"] and imported>gates["minimum_tailwater_import_m3"]))
    western = response[:,:max(1,response.shape[1]//2)]
    positions = np.argwhere(response>gates["minimum_tailwater_response_m"])
    scenarios["controlled_tailwater"].update(maximum_west_half_depth_increase_m=float(western.max()),
        positive_west_half_response_cells=int(np.sum(western>gates["minimum_tailwater_response_m"])),
        farthest_response_from_prescribed_east_boundary_m=float((response.shape[1]-.5-positions[:,1]).max(initial=0)),
        original_common_forcing_and_initial_inventory_verified=True)
    near(np.asarray(scenarios["zero_source_lake"]["max_depth_change_m"]),np.asarray(index["scenario_gates"]["zero_source_lake"]["max_depth_change_m"]),"reported actual zero-source lake drift")
    near(np.asarray(scenarios["controlled_tailwater"]["max_depth_increase_m"]),np.asarray(index["scenario_gates"]["controlled_tailwater"]["max_depth_increase_m"]),"reported controlled tailwater response")
    return dict(comparisons=comparisons,scenario_gates=scenarios,all_predeclared_gates_passed=all(item["passed"] for item in comparisons) and all(item["passed"] for item in scenarios.values()),
        reference_comparisons_independently_verified=True,controlled_tailwater_independently_verified=True,
        original_forcing_and_initial_contracts_verified=True,
        uniform_coarse_convergence_claim=False,source_uniform_coarse_gates_passed=False,reference_is_independent_saved_uniform_1m=True)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",required=True,type=Path)
    parser.add_argument("--index-sha256",required=True)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    audit_saved(dict(path=str(args.index.resolve()),expected_sha256=args.index_sha256),args.output)
