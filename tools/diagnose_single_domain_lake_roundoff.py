"""Read a pinned lake and measure datum/storage/RHS roundoff without rewriting it."""

import argparse
import json
import os
from pathlib import Path
import sys

for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ.setdefault(name,"1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256,publish_bytes
from tools.audit_single_domain_fine_stage import read_json,read_bundle
from tools.single_domain_shallow_water_audit import storage_stage
from terrain_pipeline.single_domain_shallow_water_accelerated_v7 import shallow_water_rhs


def diagnose(index_record,output):
    index = read_json(index_record)
    boundary = read_json(index["boundary_declaration"])
    case = index["cases"]["lake-at-rest-1m"]
    run = read_json(case["run"])
    bed,_,_ = read_bundle(case["bed"])
    geometry,metadata,_ = read_bundle(run["geometry"])
    states,_,_ = read_bundle(run["states"])
    forcing,forcing_metadata,_ = read_bundle(run["forcing"])
    witness,witness_meta,_ = read_bundle(run["momenta"][0])
    stage = boundary["initial_lake_stage_m"]
    datum = metadata["hydraulic_datum_m"]
    subbed = geometry["subcell_bed_relative_m"]
    prefix = geometry["subcell_prefix_relative_m"]
    initial = states["depth_m"][0].ravel()
    relative_initial = np.maximum((stage-datum)-subbed,0).mean(axis=1)
    initial_stage = storage_stage(initial,subbed)
    wet = initial>0
    support = {name:geometry[name] for name in ("subcell_bed_relative_m","subcell_prefix_relative_m","face_segment_crest_relative_m","boundary_segment_crest_relative_m")}
    args = dict(support=support,spacing=metadata["spacing_m"],gravity=9.81,boundary_kind=geometry["boundary_kind"],
        tailwater=witness["tailwater_m"]-datum,roughness=.035,dt=witness_meta["dt_s"],boundary_crest=geometry["boundary_crest_m"]-datum)
    variants = {}
    for name,depth in (("saved_absolute_initial",initial),("relative_consistent_initial",relative_initial)):
        state = np.column_stack((depth,np.zeros((len(depth),2))))
        rhs,_ = shallow_water_rhs(state,geometry["H2_m"]-datum,**args)
        variants[name] = dict(maximum_depth_rhs_m_s=float(abs(rhs[:,0]).max()),maximum_momentum_rhs_m2_s2=float(abs(rhs[:,1:]).max()),
            maximum_wet_stage_range_m=float(np.ptp(storage_stage(depth,subbed)[depth>0])))
    # A translated absolute bed changes no intended physical difference, but
    # changes the conditioning of reconstructing h+crest-crest in HLL.
    shifted = {key:value.copy() for key,value in support.items()}
    shift = -float(np.median(subbed))
    for key in shifted:
        shifted[key] += shift if "prefix" not in key else shift*np.arange(1,subbed.shape[1]+1)[None,:]
    shifted_args = dict(args,support=shifted,tailwater=args["tailwater"]+shift,boundary_crest=args["boundary_crest"]+shift)
    state = np.column_stack((relative_initial,np.zeros((len(initial),2))))
    rhs,_ = shallow_water_rhs(state,geometry["H2_m"]-datum+shift,**shifted_args)
    variants["translated_relative_support"] = dict(maximum_depth_rhs_m_s=float(abs(rhs[:,0]).max()),maximum_momentum_rhs_m2_s2=float(abs(rhs[:,1:]).max()))
    change = abs(states["depth_m"]-states["depth_m"][0])
    flat = int(np.argmax(change[-1]))
    local_supply = forcing["outflow_volume_m3"][:,flat].sum()/metadata["spacing_m"]**2
    result = dict(schema="single-domain-lake-roundoff-diagnostic-v1",index_record=index_record,
        initial_absolute_stage_m=stage,hydraulic_datum_m=datum,initial_relative_stage_m=stage-datum,
        maximum_initial_absolute_vs_relative_depth_m=float(abs(initial-relative_initial).max()),
        maximum_initial_wet_relative_stage_error_m=float(abs(initial_stage[wet]-(stage-datum)).max()),
        wet_relative_stage_spread_m=float(np.ptp(initial_stage[wet])),rhs_variants=variants,
        saved_times_s=states["time_s"].tolist(),maximum_saved_depth_drift_m=change.max(axis=(1,2)).tolist(),
        maximum_final_drift_cell=dict(row=flat//states["depth_m"].shape[2],column=flat%states["depth_m"].shape[2],
            initial_depth_m=float(initial[flat]),final_depth_m=float(states["depth_m"][-1].ravel()[flat]),
            maximum_final_momentum_m2_s=float(max(abs(states["momentum_x_m2_s"][-1].ravel()[flat]),abs(states["momentum_z_m2_s"][-1].ravel()[flat])))),
        forcing_diagnosis=dict(source_free_lake=bool(np.all(forcing["outflow_volume_m3"]==0)),
            total_local_runoff_supply_m3=float(forcing["outflow_volume_m3"].sum()),
            supplied_per_interval_m3=forcing["outflow_volume_m3"].sum(axis=1).tolist(),
            maximum_drift_cell_local_supply_depth_m=float(local_supply),
            maximum_drift_minus_local_supply_m=float(states["depth_m"][-1].ravel()[flat]-initial[flat]-local_supply),
            runoff_parameters=forcing_metadata["runoff_metadata"]["parameters"],
            interpretation="Default initial soil and percolation feed slow reservoir release despite zero rain; observed drift is dominated by real saved forcing, not an initial datum mismatch."),
        all_fixed_artifacts_unchanged=True,solver_advanced=False,stage_accepted=False,hydraulic_ready=False,natural_outlet_verified=False,publishable=False,
        limitations=["RHS diagnostic executes isolated equations at saved initial state; no time evolution or package mutation.",
            "The fixed case is not source-free, so its failed static drift gate cannot establish solver lake-at-rest failure or justify a relaxed tolerance.",
            "Remaining drift minus local supply includes neighboring water exchange; no new time evolution has been performed."])
    if file_sha256(index_record["path"])!=index_record["expected_sha256"]:
        raise ValueError("pinned index changed")
    root = Path(output).resolve()
    root.relative_to(ROOT)
    root.mkdir(parents=True,exist_ok=False)
    target = root/"report.json"
    publish_bytes(target,(json.dumps(result,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    print(json.dumps(dict(report=dict(path=str(target),expected_sha256=file_sha256(target)),diagnostic=result)),flush=True)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",required=True,type=Path)
    parser.add_argument("--index-sha256",required=True)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    diagnose(dict(path=str(args.index.resolve()),expected_sha256=args.index_sha256),args.output)
