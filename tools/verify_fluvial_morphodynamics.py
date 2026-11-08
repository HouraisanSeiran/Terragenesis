"""Independent saved-array evidence for bounded two-dimensional delta evolution."""

import argparse
import html
import json
import os
from pathlib import Path
import sys
import subprocess

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.ndimage import distance_transform_edt, label

from terrain_pipeline.common_infra import file_sha256
from tools.verify_fluvial_channel_remobilization import _close, refine, resource_limits

TASK15 = ROOT / "verification/fluvial-delta/distributary-20261015-01/TD-prepared/delta.npz"
HISTORY_FIELDS = ("times_s","beds_m","depths_m","stages_m","qx_m2_s","qz_m2_s")
PHASE_FIELDS = ("start_bed_m","end_bed_m","delta_bulk_m3")
NATIVE_FIELDS = ("injected_bulk_m3","exported_bulk_m3","lost_bulk_m3","inlet_correction_bulk_m3")
GRAVITY_VERSION="pydeltarcm-metric-adapter-v3-mobile-gravity"
DRY_DEPTH_VERSION="pydeltarcm-metric-adapter-v4-dry-depth-sensitivity"
QUANTIZED_EXCHANGE_VERSION="pydeltarcm-metric-adapter-v5-quantized-native-exchange"
WATER_ROUTING_REPAIR_VERSION="pydeltarcm-metric-adapter-v6-water-routing-repair"
WATER_REPAIR_MECHANISMS={"loop_relocation":"irregular-graph-wet-connection-native-flux-v2",
                         "inlet_weights":"row0-inlet-upstream-weight-mask-v1"}
QUANTIZED_VERSIONS=(QUANTIZED_EXCHANGE_VERSION,WATER_ROUTING_REPAIR_VERSION)
GRAVITY_VERSIONS=(GRAVITY_VERSION,DRY_DEPTH_VERSION,*QUANTIZED_VERSIONS)
GRAVITY_ARRAY_FIELDS=("start_sand_fraction","end_sand_fraction","start_active_layer","end_active_layer")


def phase_order(core):
    return ("sand","diffusion","mud","finalize","gravity") if core.get("algorithm_version") in GRAVITY_VERSIONS else ("sand","diffusion","mud","finalize")


def _components(mask, cell_area_m2):
    labels,count = label(mask)
    sizes = np.bincount(labels.ravel())[1:]
    largest = int(sizes.max(initial=0))
    total = int(mask.sum())
    return {"cell_count":total,"component_count":int(count),"largest_component_cells":largest,
            "largest_component_area_m2":largest*cell_area_m2,
            "largest_component_fraction":largest/total if total else 0.,
            "component_cells_descending":sorted(map(int,sizes),reverse=True)}


def surface_exposure_diagnostics(initial_bed_m, final_bed_m, depths_m, initial_ocean_mask,
                                 valid_mask, spacing_m, sea_level_m=0., dry_depth_tolerance_m=2e-6):
    """Separate the frozen sea-reference geometry from actual local water exposure."""
    initial,bed,depth=np.asarray(initial_bed_m),np.asarray(final_bed_m),np.asarray(depths_m)
    above=valid_mask & initial_ocean_mask & (initial<=sea_level_m) & (bed>sea_level_m)
    surviving=valid_mask & ~initial_ocean_mask & (initial>=sea_level_m) & (bed>=sea_level_m)
    labels,_=label(surviving | above)
    roots=np.unique(labels[surviving])
    connected=above & np.isin(labels,roots[roots!=0])
    dry=depth<=dry_depth_tolerance_m
    dry_land=surviving & dry
    dry_labels,_=label(dry_land | (above & dry))
    dry_roots=np.unique(dry_labels[dry_land])
    connected_dry=above & dry & np.isin(dry_labels,dry_roots[dry_roots!=0])
    result={"sea_level_reference_m":sea_level_m,"dry_depth_tolerance_m":dry_depth_tolerance_m,
            "semantics":"bed above fixed sea level and geometric land connectivity do not imply local dry exposure; actual native depth is inspected separately"}
    for name,mask in (("bed_above_fixed_sea_level",above),("geometrically_connected_above_sea_bed",connected),
                      ("actual_dry_connected_to_original_land",connected_dry)):
        result[name]={"cell_count":int(mask.sum()),"area_m2":float(mask.sum()*spacing_m**2),
                      "actual_depth_range_m":[float(depth[mask].min()),float(depth[mask].max())] if mask.any() else None,
                      "actual_dry_cell_count":int(np.count_nonzero(mask & (depth<=dry_depth_tolerance_m))),
                      "actual_dry_area_m2":float(np.count_nonzero(mask & (depth<=dry_depth_tolerance_m))*spacing_m**2)}
    return result


def spatial_repetition(mask, maximum_lag_cells=8):
    """Describe translated overlap without treating irregularity as naturalness."""
    result = {}
    for axis,name in ((0,"rows"),(1,"columns")):
        overlap = []
        for lag in range(1,min(maximum_lag_cells,mask.shape[axis]-1)+1):
            a = np.take(mask,np.arange(mask.shape[axis]-lag),axis=axis)
            b = np.take(mask,np.arange(lag,mask.shape[axis]),axis=axis)
            union = np.count_nonzero(a|b)
            overlap.append(float(np.count_nonzero(a&b)/union) if union else 0.)
        result[name] = {"lag_cells":list(range(1,len(overlap)+1)),"jaccard_overlap":overlap}
    return result


def morphology_evidence(initial_bed_m, final_bed_m, initial_ocean_mask, valid_mask, spacing_m,
                        sea_level_m=0., positive_volume_tolerance_m3=1e-7):
    initial,final = np.asarray(initial_bed_m),np.asarray(final_bed_m)
    if initial.shape != final.shape or initial.shape != initial_ocean_mask.shape or initial.shape != valid_mask.shape:
        raise ValueError("morphology arrays must share the actual raster")
    if not np.isfinite(initial[valid_mask]).all() or not np.isfinite(final[valid_mask]).all() or spacing_m <= 0.:
        raise ValueError("finite real beds and positive physical spacing required")
    area = spacing_m**2
    ocean = initial_ocean_mask & valid_mask
    change = (final-initial)*area
    positive = ocean & (change > positive_volume_tolerance_m3)
    new_land = ocean & (initial <= sea_level_m) & (final > sea_level_m)
    initial_land = valid_mask & ~initial_ocean_mask & (initial >= sea_level_m)
    surviving_original_land = initial_land & (final >= sea_level_m)
    final_land = surviving_original_land | new_land
    land_labels,_ = label(final_land)
    rooted_labels = np.unique(land_labels[surviving_original_land])
    rooted_labels = rooted_labels[rooted_labels != 0]
    connected_new = new_land & np.isin(land_labels,rooted_labels)
    coast_distance = distance_transform_edt(~initial_land,sampling=spacing_m) if initial_land.any() else np.zeros(initial.shape)
    advances = coast_distance[connected_new]
    return {"volume_semantics":"native bulk bed volume; no porosity conversion inferred",
            "whole_ocean_net_bed_volume_m3":float(change[ocean].sum()),
            "positive_ocean_bed_volume_m3":float(np.maximum(0.,change[ocean]).sum()),
            "negative_ocean_bed_volume_m3":float(np.minimum(0.,change[ocean]).sum()),
            "positive_growth":_components(positive,area),"new_emergent_land":_components(new_land,area),
            "substantive_growth_at_least_005m":_components(ocean & (final-initial >= .05),area),
            "land_connected_new_emergence":_components(connected_new,area),
            "maximum_connected_shoreline_advance_m":float(advances.max(initial=0.)),
            "median_connected_shoreline_advance_m":float(np.median(advances)) if advances.size else 0.,
            "positive_growth_repetition":spatial_repetition(positive),
            "bulk_growth_and_land_connected_emergence":bool(change[ocean].sum() > positive_volume_tolerance_m3 and connected_new.any()),
            "naturalness_certified":False}


def distributary_evidence(bed,depth,stage,downstream_flux,ocean_mask,export_mask,inlet_mask,spacing_m,
                         section_rows,minimum_depth_m,minimum_bank_relief_m,minimum_branch_fraction,
                         minimum_branch_separation_m,maximum_bank_halfwidth_cells,valid_mask=None):
    """Detect wet low-bed branches from native fields, without supplied paths.

    Downstream-face flux is an approximate steady quantity in m2/s. Connected
    river support and subsequent wet-ocean export support are distinct checks.
    """
    bed,depth,stage,flux = map(np.asarray,(bed,depth,stage,downstream_flux))
    valid=np.ones(bed.shape,bool) if valid_mask is None else np.asarray(valid_mask,bool)
    wet = depth >= minimum_depth_m
    hydraulic = wet & (stage > bed) & valid
    low = np.zeros(bed.shape,bool)
    for offset in range(1,maximum_bank_halfwidth_cells+1):
        if bed.shape[1] <= 2*offset:
            continue
        middle=bed[:,offset:-offset]
        low[:,offset:-offset] |= (bed[:,:-2*offset]-middle >= minimum_bank_relief_m) & (bed[:,2*offset:]-middle >= minimum_bank_relief_m)
    supported = low & hydraulic & (flux>0.)
    def lateral_closure(row_support,seeds):
        groups,_=label(row_support)
        active=np.unique(groups[seeds & row_support])
        return row_support & np.isin(groups,active[active!=0])
    shared_upstream=np.zeros(bed.shape,bool)
    previous=np.zeros(bed.shape[1],bool)
    for row in range(bed.shape[0]):
        seeds=previous | np.roll(previous,1) | np.roll(previous,-1) | inlet_mask[row]
        seeds[0]=seeds[-1]=False
        previous=lateral_closure(supported[row],seeds)
        shared_upstream[row]=previous
    # Wet ocean reachability does not require an incised deep-sea channel.
    wet_ocean=(ocean_mask & hydraulic & (flux>0.))
    def neighboring_columns(row_mask):
        expanded=row_mask.copy()
        expanded[1:] |= row_mask[:-1]
        expanded[:-1] |= row_mask[1:]
        return expanded
    connected_sea=np.zeros(bed.shape,bool)
    following=np.zeros(bed.shape[1],bool)
    # Every ocean path may move laterally or downstream, never back upstream.
    for row in range(bed.shape[0]-1,-1,-1):
        seeds=export_mask[row] | neighboring_columns(following)
        following=lateral_closure(wet_ocean[row],seeds)
        connected_sea[row]=following
    sea_contact=np.zeros(bed.shape,bool)
    for row in range(bed.shape[0]):
        sea_contact[row]=neighboring_columns(connected_sea[row])
        if row+1 < bed.shape[0]:
            sea_contact[row] |= neighboring_columns(connected_sea[row+1])
    def downstream_contact(row,columns):
        reached=np.zeros(bed.shape[1],bool)
        reached[columns]=True
        last=row
        for next_row in range(row,bed.shape[0]):
            if next_row>row:
                reached=(reached | np.roll(reached,1) | np.roll(reached,-1))
                reached[0]=reached[-1]=False
            reached=lateral_closure(shared_upstream[next_row],reached)
            if not reached.any():
                break
            last=next_row
            if np.any(reached & sea_contact[next_row]):
                return True,last
        return False,last
    observations=[]
    for row in section_rows:
        if not 0 <= row < bed.shape[0]:
            raise ValueError("declared section lies outside the saved native domain")
        groups,count=label(shared_upstream[row])
        total_flux=float(np.maximum(0.,flux[row,valid[row]]).sum()*spacing_m)
        branches=[]
        for component in range(1,count+1):
            columns=np.flatnonzero(groups==component)
            positive=np.maximum(0.,flux[row,columns])
            discharge=float(positive.sum()*spacing_m)
            fraction=discharge/total_flux if total_flux>0. else 0.
            if fraction < minimum_branch_fraction:
                continue
            center=float(np.average(columns,weights=positive)) if positive.sum()>0. else float(columns.mean())
            contact,last_row=downstream_contact(row,columns)
            branches.append({"column_first":int(columns[0]),"column_last":int(columns[-1]),"flux_center_column":center,
                             "native_steady_discharge_m3_s":discharge,"fraction_of_section_positive_flux":fraction,
                             "minimum_water_depth_m":float(depth[row,columns].min()),
                             "wet_ocean_contact":contact,"downstream_supported_length_m":(last_row-row)*spacing_m,
                             "ocean_contact_semantics":"row-monotone native wet low-bed support and wet-ocean path to export; contact only same row or downstream; cannot return through shared upstream"})
        separated_pairs=[]
        for first in range(len(branches)):
            for second in range(first+1,len(branches)):
                distance=abs(branches[second]["flux_center_column"]-branches[first]["flux_center_column"])*spacing_m
                if distance >= minimum_branch_separation_m:
                    separated_pairs.append({"branch_indices":[first,second],"separation_m":distance})
        observations.append({"row":int(row),"distance_downstream_m":row*spacing_m,
                             "total_positive_native_discharge_m3_s":total_flux,
                             "signed_native_discharge_m3_s":float(flux[row,valid[row]].sum()*spacing_m),
                             "negative_native_discharge_m3_s":float(np.minimum(0.,flux[row,valid[row]]).sum()*spacing_m),
                             "branches":branches,"separated_pairs":separated_pairs})
    return {"section_observations":observations,"actual_low_bed_wet_support_cells":int(shared_upstream.sum()),
            "two_low_bed_flow_branches_observed":any(bool(section["separated_pairs"]) for section in observations),
            "downstream_ocean_connectivity_reported_separately":True,
            "semantics":"field-derived diagnostic; declared lengths, sustained steps and final thresholds require separate acceptance"}


def sustained_distributary_evidence(arrays, *, minimum_length_m=100., minimum_separation_m=20.,
                                   minimum_branch_fraction=.1, minimum_depth_m=.15,
                                   minimum_bank_relief_m=.15, final_snapshots=3,
                                   maximum_bank_halfwidth_cells=12, spacing_m=5.):
    """Track two distinct bed-bank intervals downstream and across saved times."""
    a=arrays
    valid=a.get("backend_valid_mask",np.ones(a["beds_m"].shape[1:],bool)).astype(bool)
    if "cell_type" in a:
        valid &= a["cell_type"]!=-2
    count=len(a["times_s"])
    snapshots=[]
    for index in range(max(0,count-final_snapshots),count):
        bed=a["beds_m"][index]
        evidence=distributary_evidence(bed,a["depths_m"][index],a["stages_m"][index],a["qx_m2_s"][index],
            a["backend_ocean_mask"],a["backend_export_mask"],a["backend_inlet_mask"],spacing_m,
            range(bed.shape[0]),minimum_depth_m,minimum_bank_relief_m,minimum_branch_fraction,
            minimum_separation_m,maximum_bank_halfwidth_cells,valid_mask=valid)
        sections=evidence["section_observations"]
        tracks=[]
        for row,section in enumerate(sections):
            for pair in section["separated_pairs"]:
                seeds=[section["branches"][j] for j in pair["branch_indices"]]
                frontier=[(seeds,[(row,[b["flux_center_column"] for b in seeds])])]
                for downstream in range(row+1,len(sections)):
                    following={}
                    for previous,path in frontier:
                        for next_pair in sections[downstream]["separated_pairs"]:
                            branches=[sections[downstream]["branches"][j] for j in next_pair["branch_indices"]]
                            if all(b["column_first"] <= p["column_last"]+1 and b["column_last"] >= p["column_first"]-1
                                   for p,b in zip(previous,branches)):
                                key=tuple((b["column_first"],b["column_last"]) for b in branches)
                                following.setdefault(key,(branches,path+[(downstream,[b["flux_center_column"] for b in branches])]))
                    if not following:
                        break
                    frontier=list(following.values())
                    # A valid prefix remains evidence when a later tail loses contact.
                    for branches,path in frontier:
                        length=(path[-1][0]-row)*spacing_m
                        if length>=minimum_length_m and all(b["wet_ocean_contact"] for b in branches):
                            tracks.append({"first_row":row,"last_row":path[-1][0],"length_m":length,
                                           "branch_centers_by_row":[{"row":r,"columns":c} for r,c in path]})
        snapshots.append({"snapshot_index":index,"physical_time_s":float(a["times_s"][index]),
                          "qualifying_tracks":tracks,"two_sustained_branches":bool(tracks)})
    matched=[]
    if len(snapshots)==final_snapshots:
        for track in snapshots[-1]["qualifying_tracks"]:
            reference={p["row"]:p["columns"] for p in track["branch_centers_by_row"]}
            matches=[]
            for snapshot in snapshots[:-1]:
                candidates=[]
                for earlier in snapshot["qualifying_tracks"]:
                    points={p["row"]:p["columns"] for p in earlier["branch_centers_by_row"]}
                    common=sorted(reference.keys() & points.keys())
                    if len(common)>1 and (common[-1]-common[0])*spacing_m>=minimum_length_m:
                        displacement=max(abs(reference[r][j]-points[r][j])*spacing_m for r in common for j in (0,1))
                        if displacement<=minimum_separation_m/2:
                            candidates.append({"snapshot_index":snapshot["snapshot_index"],"maximum_center_displacement_m":displacement})
                if not candidates:
                    break
                matches.append(candidates[0])
            if len(matches)==final_snapshots-1:
                matched.append({"final_track":track,"earlier_snapshot_matches":matches})
    return {"parameters":{"minimum_length_m":minimum_length_m,"minimum_separation_m":minimum_separation_m,
            "minimum_branch_fraction":minimum_branch_fraction,"minimum_depth_m":minimum_depth_m,
            "minimum_bank_relief_m":minimum_bank_relief_m,"final_snapshots":final_snapshots,
            "maximum_bank_halfwidth_cells":maximum_bank_halfwidth_cells,
            "maximum_bank_halfwidth_m":maximum_bank_halfwidth_cells*spacing_m,
            "maximum_cross_snapshot_center_displacement_m":minimum_separation_m/2},
            "snapshots":snapshots,"matched_sustained_pairs":matched,
            "sustained_distributary_gate":bool(matched),
            "semantics":"every qualifying prefix of consecutive row-overlapping distinct banked intervals; row-monotone wet-ocean export contact; native positive cross-section flux; final saved physical snapshots"}


def task15_comparison(mapping=None):
    with np.load(TASK15,allow_pickle=False) as archive:
        initial,final,ocean,valid = (archive[key] for key in ("initial_bed_m","final_bed_m","ocean_mask","valid_mask"))
        if mapping is not None:
            initial,final,ocean,valid = (_mapped(value,mapping) for value in (initial,final,ocean,valid))
        return {"archive_path":str(TASK15),"archive_sha256":file_sha256(TASK15),
                "mapped_to_candidate_support":mapping is not None,
                "evidence":morphology_evidence(initial,final,ocean,valid,5.)}


def save_archive(path,result,provenance,source_arrays,mapping):
    """Publish native measurements; source_arrays retains all input identities."""
    arrays = {key:np.asarray(result[key]) for key in ("initial_bed_m","final_bed_m",*HISTORY_FIELDS)}
    arrays.update({key:np.asarray(value) for key,value in source_arrays.items()})
    phases = result["phases"]
    for field in PHASE_FIELDS:
        arrays["phase_"+field] = np.stack([phase[field] for phase in phases])
    if result["metadata"].get("algorithm_version") in GRAVITY_VERSIONS:
        for field in ("initial_mobile_base_m","final_mobile_base_m","ux_m_s","uz_m_s","speed_m_s"):
            arrays[field]=np.asarray(result[field])
        for field in GRAVITY_ARRAY_FIELDS:
            arrays["gravity_"+field]=np.stack([phase[field] for phase in phases if phase["phase"]=="gravity"])
    metadata = {"schema":"saved-pydeltarcm-morphodynamics-v1","core":result["metadata"],"source":provenance,"mapping":mapping,
                "phases":[{key:value for key,value in phase.items() if key not in (*PHASE_FIELDS,*GRAVITY_ARRAY_FIELDS)} for phase in phases]}
    arrays["metadata_json"] = np.array(json.dumps(metadata,sort_keys=True))
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream,**arrays)


def archive_result(path,result,provenance=None,raw_td_m=None,preparation=None):
    """Normalize the adapter's native result without re-running the backend."""
    result=dict(result)
    result["metadata"]=dict(result["metadata"])
    if "source_arrays" in result:
        arrays=dict(result["source_arrays"])
        arrays["source_raw_td_m"]=np.asarray(raw_td_m)
        source=dict(provenance)
        source["sediment_origin"]="declared preparation supply and native river sediment; original source incision separately measured"
        source["candidate_identity"]="task16 experimental pyDeltaRCM two-dimensional morphodynamics"
        mapping=result["mapping"]
    else:
        original=result["backend_source_bed_m"]
        source={"kind":"SYNTHETIC","interpretation":"official native pyDeltaRCM control; no TD source"}
        mapping={"source_rows_columns":[0,original.shape[0],0,original.shape[1]],"transpose":False}
        arrays={"source_original_bed_m":original,"source_prepared_bed_m":result["backend_prepared_bed_m"],
                "source_raw_td_m":original,"source_ocean_mask":(original < result["metadata"]["sea_level_m"]) & (result["cell_type"] != 1)}
        arrays["backend_ocean_mask"]=arrays["source_ocean_mask"]
        arrays["backend_valid_mask"]=result["cell_type"] != -2
        arrays["backend_export_mask"]=result["cell_type"] == -1
    for key in ("backend_source_bed_m","backend_prepared_bed_m","backend_initialization_delta_m","cell_type"):
        arrays[key]=result[key]
    for key in ("backend_physical_initialization_delta_m","backend_initial_representation_delta_m"):
        if key in result:
            arrays[key]=result[key]
    arrays["backend_inlet_mask"]=result["cell_type"]==1
    if preparation is not None:
        result["metadata"]["preparation_ledger"]=preparation["preparation_ledger"]
        result["metadata"]["preparation_metadata"]=preparation["metadata"]
        arrays["source_preparation_fill_bulk_m3"]=preparation["fill_bulk_m3"]
    else:
        result["metadata"]["preparation_ledger"]={"supplied_solid_m3":0.,"placed_solid_m3":0.,"unplaced_solid_m3":0.,"placed_bulk_m3":0.,"residual_solid_m3":0.}
    delta=np.asarray(result["backend_initialization_delta_m"])
    physical_initial=np.asarray(result["backend_prepared_bed_m"],dtype=np.float64).copy()
    if source["kind"]=="saved_TD":
        physical_initial[arrays["backend_inlet_mask"]]=result["metadata"]["sea_level_m"]-result["metadata"]["config"]["inlet_depth_m"]
        work_delta=physical_initial-np.asarray(result["backend_prepared_bed_m"])
        quantization=np.asarray(result["backend_prepared_bed_m"])+delta-physical_initial
    else:
        work_delta=delta
        quantization=np.zeros(delta.shape)
    area=result["metadata"]["dx_m"]**2
    initialization_cut=float(-np.minimum(0.,work_delta).sum()*area)
    initialization_fill=float(np.maximum(0.,work_delta).sum()*area)
    result["metadata"]["initialization_quantization_bulk_m3"]=float(quantization.sum()*area)
    result["metadata"]["initialization_work_semantics"]="physical stub before float32 representation; quantization separate"
    result["metadata"]["initialization_work_ledger"]={"source_cut_bulk_m3":initialization_cut,"supplied_fill_bulk_m3":initialization_fill,
        "cut_solid_m3":initialization_cut*result["metadata"]["solid_fraction"],
        "fill_solid_m3":initialization_fill*result["metadata"]["solid_fraction"],
        "cut_destination":"explicit initialization work escrow outside native transport; not model ocean export",
        "fill_source":"explicit initialization boundary work supply; not natural river deposition"}
    save_archive(path,result,source,arrays,mapping)


def _mapped(array,mapping):
    r0,r1,c0,c1 = mapping["source_rows_columns"]
    if not 0 <= r0 < r1 <= array.shape[0] or not 0 <= c0 < c1 <= array.shape[1]:
        raise ValueError("backend mapping leaves immutable source support")
    result = array[r0:r1,c0:c1]
    if mapping["transpose"]:
        result = result.T
    if mapping.get("reverse_rows",False):
        result = result[::-1,:]
    if mapping.get("reverse_columns",False):
        result = result[:,::-1]
    return result


def native_counter_sign_diagnostics(phase,core):
    """Classify signed counters at their mechanism's phase-throughput precision."""
    if not all(np.isfinite(phase[key]) for key in NATIVE_FIELDS):
        raise ValueError("nonfinite native parcel counter")
    resolution=0.
    quantized=core.get("algorithm_version") in QUANTIZED_VERSIONS
    scalar_type=np.float64 if quantized else np.float32
    if phase["phase"] in ("sand","mud") and "native_parcel_bulk_m3" in core:
        fraction=core["config"]["sand_fraction"] if phase["phase"]=="sand" else 1-core["config"]["sand_fraction"]
        expected=int(core["config"]["sediment_parcels"]*fraction)*core["native_parcel_bulk_m3"]
        resolution=float(np.spacing(scalar_type(expected))) if expected>0. else 0.
    if phase["injected_bulk_m3"]<0. or any(phase[key]<-resolution for key in ("exported_bulk_m3","lost_bulk_m3")):
        raise ValueError("negative native parcel boundary counter")
    precision="float64" if quantized else "float32"
    return {precision+"_phase_throughput_resolution_bulk_m3":resolution,
            "negative_raw_counters":{key:phase[key] for key in ("exported_bulk_m3","lost_bulk_m3") if phase[key]<0.},
            "semantics":f"one {precision} ULP at declared phase injection; sign classification only, not a bound on cumulative exchange error or a mass correction; raw signed values and material residuals remain unchanged"}


def native_material_acceptance(phases,residuals):
    """Apply fixed bulk-volume tolerances to raw independently measured phases."""
    observations=[]
    for phase,residual in zip(phases,residuals):
        magnitude=sum(phase[key] for key in ("injected_bulk_m3","exported_bulk_m3","lost_bulk_m3"))+abs(phase["inlet_correction_bulk_m3"])
        limit=.01+1e-5*magnitude
        value=residual["residual_bulk_m3"]
        observations.append({"step":residual["step"],"phase":residual["phase"],"raw_residual_bulk_m3":value,
                             "tolerance_bulk_m3":limit,"within_tolerance":abs(value)<=limit})
    total_injected=sum(p["injected_bulk_m3"] for p in phases)
    total_lost=sum(p["lost_bulk_m3"] for p in phases)
    signed_residual=sum(r["residual_bulk_m3"] for r in residuals)
    cumulative_limit=.01+1e-5*total_injected
    return {"phase_absolute_tolerance_bulk_m3":.01,"relative_tolerance":1e-5,
            "phases":observations,"cumulative_signed_raw_residual_bulk_m3":signed_residual,
            "sum_absolute_phase_residual_bulk_m3":sum(abs(r["residual_bulk_m3"]) for r in residuals),
            "cumulative_tolerance_bulk_m3":cumulative_limit,
            "native_lost_bulk_m3":total_lost,"native_lost_fraction_of_injected":total_lost/total_injected if total_injected else 0.,
            "lost_semantics":"native unresolved parcel bucket, separately accounted; not a registered ocean export",
            "cumulative_within_tolerance":abs(signed_residual)<=cumulative_limit,
            "native_material_gate":all(p["within_tolerance"] for p in observations) and abs(signed_residual)<=cumulative_limit,
            "semantics":"residuals retained as numerical discrepancy; never relabeled export, erosion, or sediment supply"}


def steady_flux_diagnostics(flux,valid,spacing_m,inlet_discharge_m3_s):
    rows=sorted({min(int(distance/spacing_m),flux.shape[0]-1) for distance in (50.,100.,150.,500.)} | {flux.shape[0]-1})
    sections=[]
    for row in rows:
        values=flux[row,valid[row]]*spacing_m
        sections.append({"row":row,"distance_downstream_m":row*spacing_m,
                         "signed_native_discharge_m3_s":float(values.sum()),
                         "positive_native_discharge_m3_s":float(np.maximum(0.,values).sum()),
                         "negative_native_discharge_m3_s":float(np.minimum(0.,values).sum())})
    return {"declared_inlet_discharge_m3_s":inlet_discharge_m3_s,"sections":sections,
            "semantics":"native iterative approximately steady q; positive cross-section flux can exceed inlet because of recirculation; branch fractions use positive section flux, not inlet discharge; not exact transient water mass balance"}


def stored_mobile_slope_diagnostics(bed,base,valid,spacing):
    """Read actual stored cells; never re-run the relaxation solver."""
    stored=np.asarray(bed)
    z=stored.astype(np.float64)
    mobile=z-base
    ulp=np.abs(np.spacing(stored.astype(np.float32))).astype(np.float64)
    eligible=valid.copy()
    eligible[0]=False
    raw_max,bounded_max,inherited_max=0.,0.,0.
    for dr,dc in ((0,1),(1,0),(1,1),(1,-1)):
        r,c=np.indices(z.shape)
        rr,cc=r+dr,c+dc
        take=(rr<z.shape[0]) & (cc>=0) & (cc<z.shape[1])
        r,c,rr,cc=r[take],c[take],rr[take],cc[take]
        take=eligible[r,c] & eligible[rr,cc]
        r,c,rr,cc=r[take],c[take],rr[take],cc[take]
        left_high=z[r,c]>=z[rr,cc]
        high_mobile=np.where(left_high,mobile[r,c],mobile[rr,cc])
        high_ulp=np.where(left_high,ulp[r,c],ulp[rr,cc])
        resolvable=high_mobile>high_ulp
        excess=np.abs(z[r,c]-z[rr,cc])-np.tan(np.radians(30.))*spacing*np.hypot(dr,dc)
        raw_max=max(raw_max,float(excess[resolvable].max(initial=0.)))
        bounded_max=max(bounded_max,float((excess-.5*(ulp[r,c]+ulp[rr,cc]))[resolvable].max(initial=0.)))
        inherited_max=max(inherited_max,float(excess[~resolvable].max(initial=0.)))
    unresolved=valid & (mobile>0.) & (mobile<=ulp)
    return {"maximum_resolvable_mobile_excess_m":raw_max,"maximum_excess_after_two_endpoint_half_ulp_bound_m":bounded_max,
            "maximum_unresolvable_or_immobile_excess_m":inherited_max,
            "unresolvable_positive_mobile_cell_count":int(unresolved.sum()),
            "unresolvable_positive_mobile_bulk_m3":float(mobile[unresolved].sum()*spacing**2),
            "negative_mobile_bulk_m3":float(np.minimum(mobile[valid],0.).sum()*spacing**2),
            "minimum_bed_minus_mobile_base_m":float(mobile[valid].min()),
            "mobile_base_within_rounding_bound":bool(np.all(mobile[valid]>=-.5*ulp[valid])),
            "actual_stored_slope_gate":bool(bounded_max<=1e-6),
            "semantics":"resolvable mobile donor thickness > its float32 ULP; actual excess may deduct half-ULP at each endpoint; sub-ULP inventory retained and reported, not called immobile rock or discarded"}


def audit_gravity_phases(arrays,meta,valid):
    core=meta["core"]
    required={"repose_angle_deg":30.,"tolerance_m":1e-6,"max_sweeps":512,"substrate_sand_fraction":.5}
    if core.get("gravity_parameters")!=required:
        raise ValueError("gravity parameters differ from the frozen mechanism")
    import hashlib
    parameters={"algorithm_version":core["algorithm_version"],"gravity_parameters":required}
    if core["algorithm_version"] in (DRY_DEPTH_VERSION,*QUANTIZED_VERSIONS):
        if core.get("routing_dry_depth_m")!=.01 or not core.get("material_state_start_path"):
            raise ValueError("routing-depth sensitivity requires its declared .01m threshold and inherited mobile material checkpoint")
        parameters["routing_dry_depth_m"]=.01
        if core.get("native_water_dry_depth_m")!=.01 or any(core.get("native_"+grain+"_router_dry_depth_m")!=float(np.float32(.01)) for grain in ("sand","mud")):
            raise ValueError("actual water and sediment routing-depth thresholds differ from the sensitivity mechanism")
    elif core.get("routing_dry_depth_m") is not None:
        raise ValueError("routing-depth sensitivity assigned to the original gravity mechanism")
    if core["algorithm_version"] in QUANTIZED_VERSIONS:
        if core.get("quantized_native_exchange") is not True:
            raise ValueError("quantized exchange mechanism requires its explicit precision declaration")
        parameters["quantized_native_exchange"]=True
        expected_precision={"bed_dtype":"float32","sand_deposition_dtype":"float64","mud_deposition_dtype":"float64",
            "routers":{grain:{**{key:"float64" for key in ("Vp_sed","Vp_res","Vp_exported","Vp_lost")},
                **{key:"array(float64, 2d, A)" for key in ("Vp_dep_sand","Vp_dep_mud")}} for grain in ("sand","mud")}}
        if core.get("native_exchange_precision")!=expected_precision:
            raise ValueError("actual native exchange scalar/deposition precision differs from the v5 mechanism")
        if any(arrays[key].dtype!=np.float32 for key in ("beds_m","depths_m","stages_m")):
            raise ValueError("v5 requires unchanged actual float32 bed and water storage")
    elif core.get("quantized_native_exchange"):
        raise ValueError("quantized exchange assigned to an earlier mechanism")
    validate_water_repair_declaration(meta)
    if core["algorithm_version"]==WATER_ROUTING_REPAIR_VERSION:
        parameters.update(water_routing_repair=True,water_repair_mechanisms=WATER_REPAIR_MECHANISMS)
    identity=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode("ascii")).hexdigest()
    if core.get("mechanism_identity")!=identity:
        raise ValueError("gravity mechanism identity mismatch")
    base=arrays["initial_mobile_base_m"].copy()
    if base.shape!=arrays["initial_bed_m"].shape or not np.isfinite(base).all():
        raise ValueError("invalid initial mobile material base")
    for position in ("start","end"):
        path=core.get("material_state_"+position+"_path")
        digest=core.get("material_state_"+position+"_sha256")
        if path:
            if file_sha256(path)!=digest:
                raise ValueError("mobile material checkpoint hash mismatch")
            with np.load(path,allow_pickle=False) as state:
                np.testing.assert_array_equal(state["mobile_base_m"],arrays["initial_mobile_base_m" if position=="start" else "final_mobile_base_m"])
        elif position=="end":
            raise ValueError("gravity material ending checkpoint required")
    if not core.get("material_state_start_path"):
        np.testing.assert_array_equal(base,np.minimum(arrays["backend_source_bed_m"],arrays["initial_bed_m"]))
    observations=[]
    gravity_index=0
    for index,phase in enumerate(meta["phases"]):
        end=arrays["phase_end_bed_m"][index]
        if phase["phase"]!="gravity":
            base=np.minimum(base,end.astype(np.float64))
            continue
        start=arrays["phase_start_bed_m"][index]
        if any(phase[key]!=0. for key in NATIVE_FIELDS):
            raise ValueError("gravity has an external material counter")
        composition={key:arrays["gravity_"+key][gravity_index] for key in GRAVITY_ARRAY_FIELDS}
        for value in composition.values():
            if value.shape!=base.shape or value.dtype!=np.float32 or not np.isfinite(value).all() or np.any((value<0.)|(value>1.)):
                raise ValueError("gravity requires actual float32 bounded composition arrays")
        before=(start.astype(np.float64)-base)*core["dx_m"]**2
        after=(end.astype(np.float64)-base)*core["dx_m"]**2
        f0=composition["start_sand_fraction"].astype(np.float64)
        f1=composition["end_sand_fraction"].astype(np.float64)
        residuals={"bulk":float(((end.astype(np.float64)-start)*core["dx_m"]**2).sum()),
                   "sand":float((after*f1-before*f0).sum()),"mud":float((after*(1.-f1)-before*(1.-f0)).sum())}
        ledger=phase["gravity_ledger"]
        for grain,value in residuals.items():
            key="actual_raw_residual_"+("" if grain=="bulk" else grain+"_")+"bulk_m3"
            _close(value,ledger[key])
            if abs(value)>.01:
                raise ValueError("gravity actual material residual exceeds fixed absolute phase tolerance")
        if ledger["maximum_mobile_excess_after_m"]>1e-6 or ledger["sweeps"]>512:
            raise ValueError("float64 gravity solver did not meet frozen convergence condition")
        diagnostic=stored_mobile_slope_diagnostics(end,base,valid,core["dx_m"])
        if not diagnostic["actual_stored_slope_gate"] or not diagnostic["mobile_base_within_rounding_bound"]:
            raise ValueError("actual float32 gravity state fails mobile slope/base validation")
        changed=end!=start
        excluded=~valid
        excluded[0]=True
        for value in (end-start,composition["end_sand_fraction"]-composition["start_sand_fraction"],composition["end_active_layer"]-composition["start_active_layer"]):
            if np.any(value[excluded]!=0.):
                raise ValueError("gravity changed a wall, invalid cell or fixed inlet row")
        np.testing.assert_array_equal(composition["end_active_layer"][changed],composition["end_sand_fraction"][changed])
        observations.append({"step_index":phase["step_index"],"actual_residuals_bulk_m3":residuals,"stored_slope":diagnostic,
                             "float64_solver_ledger":ledger})
        gravity_index+=1
    np.testing.assert_array_equal(base,arrays["final_mobile_base_m"])
    return {"gravity_evidence_reconstructed":True,"phases":observations,
            "algorithm_version":core["algorithm_version"],"mechanism_identity":identity,
            "routing_dry_depth_m":core.get("routing_dry_depth_m"),
            "quantized_native_exchange":core.get("quantized_native_exchange",False),
            "semantics":"independent actual stored-state gravity-only homogeneous-column bulk/sand/mud inventories; no native full-chain grain-class conservation claim"}


def validate_water_repair_declaration(meta):
    core=meta["core"]
    if meta.get("diagnostic_only") or core.get("diagnostic_only"):
        raise ValueError("terminal diagnostic cannot enter formal morphodynamics evidence")
    if core.get("algorithm_version")==WATER_ROUTING_REPAIR_VERSION:
        if core.get("water_routing_repair") is not True or core.get("water_repair_mechanisms")!=WATER_REPAIR_MECHANISMS:
            raise ValueError("v6 requires the exact declared water routing repair mechanisms")
    elif core.get("water_routing_repair") or core.get("water_repair_mechanisms"):
        raise ValueError("water routing repair assigned to an earlier mechanism")


def audit_water_repair_statistics(core):
    if core.get("algorithm_version")!=WATER_ROUTING_REPAIR_VERSION:
        return None
    records=core.get("water_routing_repair_statistics")
    start,end=core["native_start_step_index"],core["native_end_step_index"]
    expected=[(step,iteration) for step in range(start,end) for iteration in range(3)]
    if not isinstance(records,list) or [(r.get("step_index"),r.get("iteration")) for r in records]!=expected:
        raise ValueError("v6 requires three ordered compact water repair records per native step")
    totals={key:0 for key in ("native_relocations","accepted_connections","accepted_graph_steps","out_of_domain_transitions")}
    for record in records:
        counts=[record.get(key) for key in (*totals,"steps","boundary_parcels","active_at_end")]
        rejected=record.get("rejected_connections")
        inlet=record.get("inlet_weight_mask",{})
        if (any(type(value) is not int or value<0 for value in counts) or not isinstance(rejected,dict)
                or any(type(value) is not int or value<0 for value in rejected.values())):
            raise ValueError("invalid v6 compact water repair counters")
        if (record["native_relocations"]!=record["accepted_connections"]+sum(rejected.values())
                or record["accepted_graph_steps"]<record["accepted_connections"]
                or record["steps"]>570 or record["out_of_domain_transitions"]!=0
                or record["boundary_parcels"]>core["config"]["water_parcels"]
                or record["active_at_end"]>core["config"]["water_parcels"]):
            raise ValueError("v6 repair counts violate declared native routing boundaries")
        if (any(type(inlet.get(key)) is not int or inlet[key]<0 for key in ("inlet_cells","changed_cells"))
                or inlet["changed_cells"]>inlet["inlet_cells"] or not inlet["inlet_cells"]
                or not np.isfinite(inlet.get("removed_upstream_weight_sum",np.nan))
                or inlet["removed_upstream_weight_sum"]<0):
            raise ValueError("invalid v6 inlet mask evidence")
        for key in totals:
            totals[key]+=record[key]
    return {"record_count":len(records),"totals":totals,
            "semantics":"compact native runtime counters; independent bed/material/gravity reconstruction remains separate"}


def audit_archive(path,expected_sha256=None):
    if expected_sha256 and file_sha256(path) != expected_sha256:
        raise ValueError("saved native archive hash mismatch")
    with np.load(path,allow_pickle=False) as archive:
        a = {key:archive[key].copy() for key in archive.files if key != "metadata_json"}
        meta = json.loads(str(archive["metadata_json"].item()))
    if meta["schema"] != "saved-pydeltarcm-morphodynamics-v1":
        raise ValueError("unknown morphodynamics evidence schema")
    validate_water_repair_declaration(meta)
    for key,value in a.items():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite actual model evidence: "+key)
    source,mapping,core = meta["source"],meta["mapping"],meta["core"]
    water_repair_audit=audit_water_repair_statistics(core)
    start_step=core.get("native_start_step_index",0)
    if source["kind"] == "saved_TD":
        if file_sha256(source["path"]) != source["sha256"]:
            raise ValueError("immutable source identity mismatch")
        r0,r1,c0,c1 = source["crop_rows_columns"]
        with np.load(source["path"],allow_pickle=False) as original:
            for key,parent_key in (("source_original_bed_m","derived_height_m"),("source_raw_td_m","original_td_m")):
                bed,ocean = refine(original[parent_key][r0:r1,c0:c1],original["ocean_mask"][r0:r1,c0:c1],source["refinement_factor"])
                np.testing.assert_array_equal(a[key],bed)
                np.testing.assert_array_equal(a["source_ocean_mask"],ocean)
    elif source["kind"] != "SYNTHETIC":
        raise ValueError("unknown original terrain origin")
    native_source = _mapped(a["source_original_bed_m"],mapping)
    native_prepared = _mapped(a["source_prepared_bed_m"],mapping)
    ocean = _mapped(a["source_ocean_mask"],mapping)
    _close(a["backend_source_bed_m"],native_source)
    _close(a["backend_prepared_bed_m"],native_prepared)
    if "backend_ocean_mask" in a:
        np.testing.assert_array_equal(a["backend_ocean_mask"],ocean)
    if start_step==0:
        _close(a["initial_bed_m"],native_prepared+a["backend_initialization_delta_m"])
    floor_tolerance=core.get("source_floor_tolerance_m",2e-6)
    if floor_tolerance!=2e-6:
        raise ValueError("original-source floor tolerance differs from fixed float32 criterion")
    if np.min(a["initial_bed_m"]-native_source) < -core["maximum_original_source_cut_m"]-floor_tolerance:
        raise ValueError("native initialization crosses the original-source floor")
    if np.any(a["source_prepared_bed_m"] < a["source_original_bed_m"]-1e-8):
        raise ValueError("unaccounted source incision during marine preparation")
    spacing = core["dx_m"]
    area = spacing**2
    preparation_bulk = float(((a["source_prepared_bed_m"]-a["source_original_bed_m"])*area).sum())
    _close(core["preparation_ledger"]["placed_bulk_m3"],preparation_bulk)
    if "preparation_metadata" in core:
        preparation=core["preparation_metadata"]
        parameters=preparation["config"]
        rr,cc=np.indices(a["source_original_bed_m"].shape)
        pr,pc=preparation["inlet_cell"]
        radial=np.hypot((rr-pr)*spacing,(cc-pc)*spacing)
        taper=np.clip(2*(1-radial/parameters["radius_m"]),0,1)
        taper[0,:]=taper[-1,:]=taper[:,0]=taper[:,-1]=0.
        offshore=distance_transform_edt(a["source_ocean_mask"],sampling=spacing)
        target=core["sea_level_m"]-parameters["minimum_submergence_m"]-parameters["slope_m_per_m"]*offshore
        raising=np.maximum(0.,target-a["source_original_bed_m"])*taper
        raising[~a["source_ocean_mask"]]=0.
        _close(a["source_prepared_bed_m"],a["source_original_bed_m"]+raising)
        _close(a["source_preparation_fill_bulk_m3"],raising*area)
        used=preparation_bulk*(1-parameters["porosity"])
        ledger=core["preparation_ledger"]
        _close(ledger["supplied_solid_m3"],parameters["supplied_solid_m3"])
        _close(ledger["placed_solid_m3"],used)
        _close(ledger["unplaced_solid_m3"],parameters["supplied_solid_m3"]-used)
        if raising.max() > parameters["maximum_raise_m"]+1e-7 or preparation_bulk > parameters["maximum_fill_bulk_m3"]+1e-7 or used > parameters["supplied_solid_m3"]+1e-7:
            raise ValueError("declared marine preparation exceeds material budget")
    elif abs(preparation_bulk)>1e-7:
        raise ValueError("prepared input lacks independently declared material event")
    physical_delta=a["backend_initialization_delta_m"]
    initialization_quantization=0.
    if core.get("backend")=="pyDeltaRCM":
        config=core["config"]
        expected_export=a["cell_type"]==-1
        if source["kind"]=="saved_TD":
            registered_export=np.zeros(native_source.shape,bool)
            registered_export[-1,:]=ocean[-1,:]
            np.testing.assert_array_equal(a["backend_export_mask"],registered_export)
            np.testing.assert_array_equal(expected_export,registered_export)
            declared_inlet=core["preparation_metadata"]["inlet_cell"]
            if mapping["source_rows_columns"] != [0,a["source_original_bed_m"].shape[0],declared_inlet[1],a["source_original_bed_m"].shape[1]] or not mapping["transpose"]:
                raise ValueError("TD downstream mapping disagrees with declared preparation inlet")
            length=max(1,min(int(round(config["inlet_length_m"]/spacing)),native_source.shape[0]//4))
            width=max(3,min(int(round(config["inlet_width_m"]/spacing)),native_source.shape[1]//4))
            first=declared_inlet[0]-width//2
            expected_inlet=np.zeros(native_source.shape,bool)
            expected_inlet[:length,first:first+width]=True
            np.testing.assert_array_equal(a["backend_inlet_mask"],expected_inlet)
            np.testing.assert_array_equal(a["backend_valid_mask"],np.ones(native_source.shape,bool))
            expected_types=np.zeros(native_source.shape,int)
            expected_types[0,:]=expected_types[-1,:]=-2
            expected_types[:,0]=expected_types[:,-1]=-2
            expected_types[registered_export]=-1
            expected_types[expected_inlet]=1
            np.testing.assert_array_equal(a["cell_type"],expected_types)
            inlet=a["backend_inlet_mask"]
            cells=np.argwhere(inlet)
            if cells.size==0:
                raise ValueError("mapped native inlet is empty")
            r0,c0=cells.min(axis=0)
            r1,c1=cells.max(axis=0)+1
            if r0!=0 or not np.all(inlet[r0:r1,c0:c1]) or inlet.sum()!=(r1-r0)*(c1-c0):
                raise ValueError("native initialization inlet is not the declared rectangular boundary stub")
            expected=native_prepared.copy()
            expected[inlet]=core["sea_level_m"]-config["inlet_depth_m"]
            physical_initial=expected.copy()
            if start_step==0:
                _close(a["initial_bed_m"],expected.astype(np.float32).astype(np.float64))
            _close(native_prepared+a["backend_initialization_delta_m"],expected.astype(np.float32).astype(np.float64))
        initialization=a["backend_initialization_delta_m"]
        if source["kind"]=="saved_TD":
            physical_delta=physical_initial-native_prepared
            initialization_quantization=float((native_prepared+a["backend_initialization_delta_m"]-physical_initial).sum()*area)
        else:
            physical_delta=initialization
            initialization_quantization=0.
        if "backend_physical_initialization_delta_m" in a:
            _close(a["backend_physical_initialization_delta_m"],physical_delta)
            _close(a["backend_initial_representation_delta_m"],a["backend_initialization_delta_m"]-physical_delta)
            _close(core["physical_initialization_bulk_m3"],float(physical_delta.sum()*area))
            _close(core["initial_float32_representation_bulk_m3"],initialization_quantization)
        work=core["initialization_work_ledger"]
        if "initialization_work_semantics" in core:
            initialization=physical_delta
            _close(core["initialization_quantization_bulk_m3"],initialization_quantization)
        cut=float(-np.minimum(0.,initialization).sum()*area)
        fill=float(np.maximum(0.,initialization).sum()*area)
        for key,value in (("source_cut_bulk_m3",cut),("supplied_fill_bulk_m3",fill),("cut_solid_m3",cut*core["solid_fraction"]),("fill_solid_m3",fill*core["solid_fraction"])):
            _close(work[key],value)
    times = a["times_s"]
    if times.ndim != 1 or len(times)<2 or np.any(np.diff(times) <= 0.):
        raise ValueError("physical times must strictly increase")
    if "native_dt_s" in core:
        _close(np.diff(times),core["native_dt_s"])
        _close(core["water_input_m3"],core["native_water_discharge_m3_s"]*(times[-1]-times[0]))
        _close(core["native_parcel_bulk_m3"]*core["config"]["sediment_parcels"],core["native_sediment_bulk_discharge_m3_s"]*core["native_dt_s"])
    count,shape = len(times),a["initial_bed_m"].shape
    if "native_end_step_index" in core and core["native_end_step_index"]!=start_step+count-1:
        raise ValueError("native end step disagrees with saved physical history")
    if "start_time_s" in core:
        _close(core["start_time_s"],times[0])
        _close(core["end_time_s"],times[-1])
    for field in HISTORY_FIELDS[1:]:
        if a[field].shape != (count,*shape):
            raise ValueError("actual history shape mismatch: "+field)
    _close(a["beds_m"][0],a["initial_bed_m"])
    _close(a["beds_m"][-1],a["final_bed_m"])
    if core.get("backend")=="pyDeltaRCM":
        if start_step>0 and not core.get("checkpoint_start_path"):
            raise ValueError("resumed batch lacks its native starting checkpoint")
        for position,index,native_step in (("start",0,start_step),("end",-1,start_step+count-1)):
            checkpoint=core.get("checkpoint_"+position+"_path")
            if checkpoint:
                if file_sha256(checkpoint)!=core.get("checkpoint_"+position+"_sha256"):
                    raise ValueError("native checkpoint identity mismatch")
                with np.load(checkpoint,allow_pickle=False) as checkpoint_archive:
                    for key,native in (("beds_m","eta"),("depths_m","depth"),("stages_m","stage"),("qx_m2_s","qx"),("qz_m2_s","qy")):
                        np.testing.assert_array_equal(a[key][index],checkpoint_archive[native])
                    if core.get("algorithm_version") in GRAVITY_VERSIONS:
                        for key,native in (("ux_m_s","ux"),("uz_m_s","uy"),("speed_m_s","uw")):
                            np.testing.assert_array_equal(a[key][index],checkpoint_archive[native])
                        if position=="end":
                            np.testing.assert_array_equal(a["gravity_end_sand_fraction"][-1],checkpoint_archive["sand_frac"])
                            np.testing.assert_array_equal(a["gravity_end_active_layer"][-1],checkpoint_archive["active_layer"])
                    _close(checkpoint_archive["time"],times[index])
                    if int(checkpoint_archive["time_iter"])!=native_step:
                        raise ValueError("native checkpoint step differs from archive history")
    if np.any(a["depths_m"] < 0.):
        raise ValueError("negative native water depth")
    np.testing.assert_allclose(np.maximum(0.,a["stages_m"]-a["beds_m"]),a["depths_m"],atol=2e-6,rtol=1e-6)
    phases = meta["phases"]
    order=phase_order(core)
    phase_count=len(order)
    if len(phases) != (count-1)*phase_count:
        raise ValueError("declared native/gravity phases required per physical step")
    minimum_floor = 0.
    residuals = []
    negative_counter_observations=[]
    gross_deposit,gross_erosion = 0.,0.
    phase_totals = {name:{key:0. for key in (*NATIVE_FIELDS,"bed_delta_bulk_m3")} for name in order}
    for index,phase in enumerate(phases):
        step=index//phase_count
        name=order[index%phase_count]
        if phase["step_index"] != start_step+step or phase["phase"] != name:
            raise ValueError("native phase order differs from physical step history")
        start,end,delta = (a["phase_"+field][index] for field in PHASE_FIELDS)
        expected_start = a["beds_m"][step] if index%phase_count == 0 else a["phase_end_bed_m"][index-1]
        _close(start,expected_start)
        _close(delta,(end-start)*area)
        if index%phase_count == phase_count-1:
            _close(end,a["beds_m"][step+1])
        floor_change = float(np.min(end-native_source))
        minimum_floor = min(minimum_floor,floor_change)
        if floor_change < -core["maximum_original_source_cut_m"]-floor_tolerance:
            raise ValueError("actual phase crosses original-source floor")
        counter_sign=native_counter_sign_diagnostics(phase,core)
        if counter_sign["negative_raw_counters"]:
            negative_counter_observations.append({"step_index":phase["step_index"],"phase":name,**counter_sign})
        if core.get("algorithm_version") in ("pydeltarcm-metric-adapter-v2-source-floor-exchange",*GRAVITY_VERSIONS) and name in ("sand","mud"):
            if not all(key in phase for key in ("source_floor_limited_bulk_m3","source_floor_limited_exchange_count")):
                raise ValueError("source-floor exchange mechanism lacks its declared native availability diagnostics")
        if "source_floor_limited_bulk_m3" in phase:
            if not np.isfinite(phase["source_floor_limited_bulk_m3"]) or phase["source_floor_limited_bulk_m3"]<0. or phase["source_floor_limited_exchange_count"]<0 or int(phase["source_floor_limited_exchange_count"])!=phase["source_floor_limited_exchange_count"]:
                raise ValueError("invalid native source-floor availability-limiting diagnostic")
        if name != "finalize" and phase["inlet_correction_bulk_m3"] != 0.:
            raise ValueError("inlet boundary correction assigned to wrong phase")
        if "native_parcel_bulk_m3" in core:
            fraction=core["config"]["sand_fraction"] if name=="sand" else 1-core["config"]["sand_fraction"]
            injected=int(core["config"]["sediment_parcels"]*fraction)*core["native_parcel_bulk_m3"] if name in ("sand","mud") else 0.
            _close(phase["injected_bulk_m3"],injected)
        measured = float(delta.sum())
        residual = measured-phase["injected_bulk_m3"]+phase["exported_bulk_m3"]+phase["lost_bulk_m3"]-phase["inlet_correction_bulk_m3"]
        _close(phase["raw_residual_bulk_m3"],residual)
        residuals.append({"step":start_step+step,"phase":name,"residual_bulk_m3":residual})
        if name in ("sand","mud"):
            gross_deposit += float(np.maximum(0.,delta).sum())
            gross_erosion += float(-np.minimum(0.,delta).sum())
        for key in NATIVE_FIELDS:
            phase_totals[name][key] += phase[key]
        phase_totals[name]["bed_delta_bulk_m3"] += measured
    valid=a.get("backend_valid_mask",np.ones(shape,bool)).astype(bool)
    if "cell_type" in a:
        valid &= a["cell_type"] != -2
    gravity_audit=audit_gravity_phases(a,meta,valid) if core.get("algorithm_version") in GRAVITY_VERSIONS else None
    morphology = morphology_evidence(a["initial_bed_m"],a["final_bed_m"],ocean,valid,spacing,core["sea_level_m"])
    return {"native_evidence_reconstructed":True,"physical_duration_s":float(times[-1]-times[0]),
            "initialization_quantization_bulk_m3":initialization_quantization,
            "physical_initialization_cut_bulk_m3":float(-np.minimum(0.,physical_delta).sum()*area),
            "physical_initialization_fill_bulk_m3":float(np.maximum(0.,physical_delta).sum()*area),
            "minimum_bed_minus_original_source_m":minimum_floor,"native_phase_totals":phase_totals,"native_phase_residuals":residuals,
            "initial_original_source_deficit_bulk_m3":float(np.maximum(0.,native_source-a["initial_bed_m"])[valid].sum()*area),
            "final_original_source_deficit_bulk_m3":float(np.maximum(0.,native_source-a["final_bed_m"])[valid].sum()*area),
            "source_deficit_semantics":"remaining geometric original-source deficit; not gross parcel erosion, and initial stub excavation is separate external work",
            "material_acceptance":native_material_acceptance(phases,residuals),"gravity_evidence":gravity_audit,
            "water_routing_repair_evidence":water_repair_audit,
            "negative_native_counter_observations":negative_counter_observations,
            "source_floor_availability_diagnostics":{"limited_attempt_bulk_m3":sum(phase.get("source_floor_limited_bulk_m3",0.) for phase in phases),
                "limited_exchange_count":sum(phase.get("source_floor_limited_exchange_count",0) for phase in phases),
                "semantics":"attempted native erosion excluded by available source material; diagnostic, never counted as actual erosion, sediment input, or export"},
            "steady_flux_diagnostics":steady_flux_diagnostics(a["qx_m2_s"][-1],valid,spacing,core.get("native_water_discharge_m3_s")),
            "declared_boundary_sediment_bulk_m3":core.get("native_sediment_bulk_discharge_m3_s",0.)*float(times[-1]-times[0]),
            "boundary_sampling_uninjected_bulk_m3":core.get("native_sediment_bulk_discharge_m3_s",0.)*float(times[-1]-times[0])-sum(p["injected_bulk_m3"] for p in phases) if "native_sediment_bulk_discharge_m3_s" in core else None,
            "phase_net_positive_sand_mud_bulk_m3":gross_deposit,"phase_net_negative_sand_mud_bulk_m3":gross_erosion,
            "phase_net_semantics":"positive and negative cell changes per phase are lower bounds on parcel gross deposition and erosion",
            "morphology":morphology,"water_semantics":"native approximately steady flux; no exact transient inventory claim",
            "naturalness_certified":False}


def validate_gravity_transition(transition,core,previous,inherited_batches):
    if transition.get("gravity_parameters")!=core.get("gravity_parameters") or transition.get("mechanism_identity")!=core.get("mechanism_identity"):
        raise ValueError("gravity transition parameters or mechanism identity differ from actual mechanism")
    version=core.get("algorithm_version")
    if version in (DRY_DEPTH_VERSION,*QUANTIZED_VERSIONS):
        quantized=version in QUANTIZED_VERSIONS
        water_repair=version==WATER_ROUTING_REPAIR_VERSION
        expected_parent=QUANTIZED_EXCHANGE_VERSION if water_repair else (DRY_DEPTH_VERSION if quantized else GRAVITY_VERSION)
        if (transition.get("from_algorithm_version")!=expected_parent or transition.get("to_algorithm_version")!=version
                or transition.get("from_routing_dry_depth_m")!=(.01 if quantized else .1) or transition.get("routing_dry_depth_m")!=.01
                or transition.get("material_state_start_sha256")!=previous.get("material_state_end_sha256")
                or transition.get("material_state_start_sha256")!=core.get("material_state_start_sha256")
                or not transition.get("material_state_start_path")
                or file_sha256(transition["material_state_start_path"])!=transition["material_state_start_sha256"]):
            raise ValueError("routing-depth sensitivity transition does not preserve its declared parameter change and inherited mobile material")
        if quantized and (transition.get("quantized_native_exchange") is not True or core.get("quantized_native_exchange") is not True):
            raise ValueError("v5 transition requires the explicit quantized exchange mechanism")
        if water_repair:
            validate_water_repair_declaration({"core":core})
            if (transition.get("after_step")!=4096 or previous.get("end_step")!=4096
                    or core.get("native_start_step_index")!=4096
                    or transition.get("water_routing_repair") is not True
                    or transition.get("water_repair_mechanisms")!=WATER_REPAIR_MECHANISMS):
                raise ValueError("v6 transition requires the frozen v5 step4096 parent and exact water repairs")
        evidence_key="water_routing_repair_evidence" if water_repair else ("numerical_precision_evidence" if quantized else "numerical_sensitivity_evidence")
        evidence_list=transition.get(evidence_key,[])
        if not evidence_list:
            raise ValueError("routing-depth sensitivity requires pinned numerical evidence")
    else:
        evidence_list=transition.get("morphology_failure_evidence",[])
    for evidence in evidence_list:
        if file_sha256(evidence["path"])!=evidence["sha256"]:
            raise ValueError("gravity morphology failure evidence identity mismatch")
    parent_path=Path(transition["parent_manifest_path"])
    if file_sha256(parent_path)!=transition["parent_manifest_sha256"]:
        raise ValueError("gravity inherited parent manifest identity mismatch")
    parent=json.loads(parent_path.read_text(encoding="utf-8"))
    if parent["batches"]!=inherited_batches:
        raise ValueError("gravity inherited chain differs from pinned parent")
    if transition["checkpoint_sha256"]!=previous["checkpoint_end_sha256"] or file_sha256(transition["checkpoint_path"])!=transition["checkpoint_sha256"]:
        raise ValueError("gravity inherited native checkpoint identity mismatch")


def validate_gravity_handoff(previous,core,arrays):
    if previous["material_state_end_sha256"]!=core.get("material_state_start_sha256"):
        raise ValueError("gravity mobile material checkpoint continuity broken")
    np.testing.assert_array_equal(previous["mobile_base_m"],arrays["initial_mobile_base_m"])
    for key in ("ux_m_s","uz_m_s","speed_m_s"):
        np.testing.assert_array_equal(previous["velocities"][key],arrays[key][0])


def audit_chain(manifest_path):
    """Cold-read batches sequentially, keeping only boundary states in memory."""
    manifest_path=Path(manifest_path)
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["schema"]!="saved-pydeltarcm-chain-v1" or not manifest["batches"]:
        raise ValueError("nonempty explicit morphodynamics batch manifest required")
    reports=[]
    all_phases=[]
    all_residuals=[]
    previous=None
    identity=None
    first_initial=None
    initial_time=None
    positive_bc=None
    state_fields=("beds_m","depths_m","stages_m","qx_m2_s","qz_m2_s")
    for batch_index,batch in enumerate(manifest["batches"]):
        path=Path(batch["path"])
        if not path.is_absolute():
            path=manifest_path.parent/path
        if not batch.get("sha256"):
            raise ValueError("each batch must have a pinned archive hash")
        report=audit_archive(path,batch["sha256"])
        with np.load(path,allow_pickle=False) as archive:
            meta=json.loads(str(archive["metadata_json"].item()))
            core=meta["core"]
            algorithm_version=core.get("algorithm_version","unspecified-synthetic-fixture")
            config={k:v for k,v in core["config"].items() if k!="steps"}
            current_identity={"source":meta["source"],"mapping":meta["mapping"],"config":config,
                              "backend":core["backend"],"backend_version":core["backend_version"],
                              "continuation_identity":core.get("continuation_identity")}
            times=archive["times_s"]
            start_step=core.get("native_start_step_index",0)
            states={key:archive[key][-1].copy() for key in state_fields}
            if previous is None:
                if algorithm_version in (DRY_DEPTH_VERSION,*QUANTIZED_VERSIONS):
                    raise ValueError("routing-depth sensitivity chain must retain its inherited gravity prefix")
                if start_step!=0:
                    raise ValueError("chain must begin with native step zero")
                identity=current_identity
                first_initial=archive["initial_bed_m"].copy()
                initial_time=float(times[0])
                original_ocean=archive["backend_ocean_mask"].copy()
                valid=archive["backend_valid_mask"] & (archive["cell_type"]!=-2)
                initialization=archive["backend_initialization_delta_m"].copy()
                positive_bc=np.zeros(first_initial.shape)
            else:
                if identity!=current_identity:
                    raise ValueError("batch source, backend, physical config, or mapping identity changed")
                if start_step!=previous["end_step"] or float(times[0])!=previous["end_time"]:
                    raise ValueError("batch physical time or native step continuity broken")
                for key in state_fields:
                    np.testing.assert_array_equal(previous["states"][key],archive[key][0],err_msg="batch boundary mismatch: "+key)
                np.testing.assert_array_equal(initialization,archive["backend_initialization_delta_m"])
                if previous["algorithm_version"]!=algorithm_version:
                    transitions=[item for item in manifest.get("mechanism_transitions",[]) if item["after_step"]==start_step
                                 and item["from_algorithm_version"]==previous["algorithm_version"] and item["to_algorithm_version"]==algorithm_version]
                    if len(transitions)!=1 or not transitions[0].get("reason"):
                        raise ValueError("algorithm mechanism changed without a unique explicit inherited-chain declaration")
                    transition=transitions[0]
                    if algorithm_version in GRAVITY_VERSIONS:
                        validate_gravity_transition(transition,core,previous,manifest["batches"][:batch_index])
                    else:
                        failed_path=Path(transition["failed_archive_path"])
                        if not failed_path.is_absolute():
                            failed_path=manifest_path.parent/failed_path
                        if file_sha256(failed_path)!=transition["failed_archive_sha256"]:
                            raise ValueError("mechanism transition failure evidence identity mismatch")
                        with np.load(failed_path,allow_pickle=False) as failed:
                            np.testing.assert_array_equal(failed["source_bed_m"],archive["backend_source_bed_m"])
                            np.testing.assert_array_equal(failed["successful_beds_m"][0],archive["initial_bed_m"])
                            if not np.any(failed["proposed_bed_m"]<failed["source_bed_m"]-core["maximum_original_source_cut_m"]-2e-6):
                                raise ValueError("declared source-floor repair has no actual rejected floor breach")
                if previous["algorithm_version"] in GRAVITY_VERSIONS and algorithm_version in GRAVITY_VERSIONS:
                    validate_gravity_handoff(previous,core,archive)
                if not previous["checkpoint_end_sha256"] or previous["checkpoint_end_sha256"]!=core.get("checkpoint_start_sha256"):
                    raise ValueError("batch native checkpoint/RNG continuity unproven")
            for position in ("start","end"):
                checkpoint=core.get("checkpoint_"+position+"_path")
                digest=core.get("checkpoint_"+position+"_sha256")
                if checkpoint and (not digest or file_sha256(checkpoint)!=digest):
                    raise ValueError("native checkpoint artifact identity mismatch")
            previous={"states":states,"end_time":float(times[-1]),"end_step":start_step+len(times)-1,
                      "algorithm_version":algorithm_version,
                      "material_state_end_sha256":core.get("material_state_end_sha256"),
                      "mobile_base_m":archive["final_mobile_base_m"].copy() if algorithm_version in GRAVITY_VERSIONS else None,
                      "velocities":{key:archive[key][-1].copy() for key in ("ux_m_s","uz_m_s","speed_m_s")} if algorithm_version in GRAVITY_VERSIONS else {},
                      "checkpoint_end_sha256":core.get("checkpoint_end_sha256")}
            final=archive["final_bed_m"].copy()
            last_arrays={key:archive[key][-3:].copy() for key in HISTORY_FIELDS}
            last_arrays.update({key:archive[key].copy() for key in ("backend_valid_mask","backend_ocean_mask","backend_inlet_mask","backend_export_mask","cell_type")})
            all_phases.extend(meta["phases"])
            phase_delta=archive["phase_delta_bulk_m3"]
            finalize=np.array([phase["phase"]=="finalize" for phase in meta["phases"]])
            positive_bc+=np.maximum(0.,phase_delta[finalize]).sum(axis=0)/(core["dx_m"]**2)
        all_residuals.extend(report["native_phase_residuals"])
        reports.append({"path":str(path.resolve()),"sha256":batch["sha256"],"start_step":start_step,
                        "end_step":previous["end_step"],"start_time_s":float(times[0]),"end_time_s":previous["end_time"],
                        "minimum_bed_minus_original_source_m":report["minimum_bed_minus_original_source_m"],
                        "algorithm_version":algorithm_version,
                        "gravity_evidence":report.get("gravity_evidence"),
                        "water_routing_repair_evidence":report.get("water_routing_repair_evidence"),
                        "negative_native_counter_observations":report["negative_native_counter_observations"],
                        "native_material_gate":report["material_acceptance"]["native_material_gate"]})
    corrected_final=final-positive_bc
    corrected_final[original_ocean]-=2e-6
    corrected_morphology=morphology_evidence(first_initial,corrected_final,original_ocean,valid,core["dx_m"],core["sea_level_m"])
    numerical_uncertainty=sum(abs(r["residual_bulk_m3"]) for r in all_residuals)
    positive_bc_bulk=float(positive_bc[valid].sum()*core["dx_m"]**2)
    raw_morphology=morphology_evidence(first_initial,final,original_ocean,valid,core["dx_m"],core["sea_level_m"])
    corrected_morphology["whole_ocean_net_bed_volume_m3"]=raw_morphology["whole_ocean_net_bed_volume_m3"]-positive_bc_bulk-numerical_uncertainty-2e-6*int((original_ocean & valid).sum())*core["dx_m"]**2
    return {"chain_evidence_reconstructed":True,"batch_reports":reports,"physical_duration_s":previous["end_time"]-initial_time,
            "mechanism_transitions":manifest.get("mechanism_transitions",[]),
            "minimum_bed_minus_original_source_m":min(batch["minimum_bed_minus_original_source_m"] for batch in reports),
            "material_acceptance":native_material_acceptance(all_phases,all_residuals),
            "source_floor_availability_diagnostics":{"limited_attempt_bulk_m3":sum(phase.get("source_floor_limited_bulk_m3",0.) for phase in all_phases),
                "limited_exchange_count":sum(phase.get("source_floor_limited_exchange_count",0) for phase in all_phases),
                "semantics":"attempted exchanges prevented by available material, not actual eroded or transported volume"},
            "morphology":raw_morphology,
            "actual_surface_exposure_diagnostics":surface_exposure_diagnostics(first_initial,final,last_arrays["depths_m"][-1],original_ocean,valid,core["dx_m"],core["sea_level_m"]),
            "physical_config":core["config"],"source_kind":meta["source"]["kind"],"source_sha256":meta["source"].get("sha256"),
            "source_provenance":meta["source"],"mapping":meta["mapping"],"preparation_metadata":core.get("preparation_metadata"),
            "spacing_m":core["dx_m"],
            "contribution_excluded_morphology":corrected_morphology,
            "positive_ocean_boundary_correction_bulk_m3":float((positive_bc*core["dx_m"]**2)[original_ocean & valid].sum()),
            "all_positive_boundary_correction_bulk_m3":positive_bc_bulk,
            "numerical_volume_uncertainty_bulk_m3":numerical_uncertainty,
            "contribution_exclusion_semantics":"first actual initialized bed excludes preparation and physical stub; spatial morphology subtracts positive finalize cell changes and 2e-6m ocean elevation guard; ocean net lower bound subtracts all-domain positive finalize volume (including potentially transported inlet work), ocean guard volume, and all absolute raw phase residuals; no parcel material-source attribution inferred",
            "sustained_distributary_evidence":sustained_distributary_evidence(last_arrays,spacing_m=core["dx_m"]),
            "steady_flux_diagnostics":steady_flux_diagnostics(last_arrays["qx_m2_s"][-1],valid,core["dx_m"],core.get("native_water_discharge_m3_s")),
            "naturalness_certified":False}


def formal_acceptance(manifest_path):
    report=audit_chain(manifest_path)
    morphology=report["contribution_excluded_morphology"]
    growth=morphology["substantive_growth_at_least_005m"]
    emergence=morphology["land_connected_new_emergence"]
    step=report["batch_reports"][-1]["end_step"]
    required={"dx_m":5.,"inlet_width_m":35.,"inlet_depth_m":2.,"inlet_length_m":45.,"inlet_velocity_m_s":1.,
              "sediment_concentration_percent":.1,"sand_fraction":.5,"porosity":.35,"water_parcels":1000,"sediment_parcels":1000,
              "water_iterations":3,"seed":42,"diffusion_enabled":True,"diffusion_mode":"conservative","maximum_original_source_cut_m":4.}
    parameters_match=all(report["physical_config"].get(key)==value for key,value in required.items()) and report["source_kind"]=="saved_TD" and report["source_sha256"]=="6ae9d436a073ecd64c5f554f27c62ba0248ead1c6ccdbf08c225762ae2387784"
    required_preparation={"maximum_fill_bulk_m3":2000000.,"maximum_raise_m":16.,"minimum_submergence_m":.2,"porosity":.35,
                          "radius_m":300.,"slope_m_per_m":.03,"supplied_solid_m3":1300000.}
    source=report["source_provenance"]
    preparation=report["preparation_metadata"] or {}
    support_match=(source.get("crop_rows_columns")==[116,140,230,262] and source.get("refinement_factor")==6
                   and source.get("native_spacing_m")==30. and source.get("fine_spacing_m")==5.
                   and report["mapping"].get("source_rows_columns")==[0,144,51,192] and report["mapping"].get("transpose") is True
                   and not report["mapping"].get("reverse_rows",False) and not report["mapping"].get("reverse_columns",False)
                   and preparation.get("inlet_cell")==[75,51] and preparation.get("config")==required_preparation)
    gates={"fixed_formal_scenario":{"required_config":required,"required_preparation":required_preparation,"passed":parameters_match and support_match},
           "source_floor_each_phase":{"value":-report["minimum_bed_minus_original_source_m"],"maximum":4.000002,"passed":-report["minimum_bed_minus_original_source_m"]<=4.000002},
           "minimum_512_native_steps":{"value":step,"minimum":512,"passed":step>=512},
           "ocean_net_bulk_growth_m3":{"value":morphology["whole_ocean_net_bed_volume_m3"],"minimum":10000.,"passed":morphology["whole_ocean_net_bed_volume_m3"]>=10000.},
           "substantive_largest_growth_area_m2":{"value":growth["largest_component_area_m2"],"minimum":10000.,"passed":growth["largest_component_area_m2"]>=10000.},
           "substantive_largest_growth_fraction":{"value":growth["largest_component_fraction"],"minimum":.5,"passed":growth["largest_component_fraction"]>=.5},
           "land_connected_new_emergence_area_m2":{"value":emergence["cell_count"]*report["spacing_m"]**2,"minimum":2500.,"passed":emergence["cell_count"]*report["spacing_m"]**2>=2500.},
           "connected_shoreline_advance_m":{"value":morphology["maximum_connected_shoreline_advance_m"],"minimum":50.,"passed":morphology["maximum_connected_shoreline_advance_m"]>=50.},
           "sustained_distributaries":{"value":report["sustained_distributary_evidence"]["sustained_distributary_gate"],"passed":report["sustained_distributary_evidence"]["sustained_distributary_gate"]},
           "native_material":{"value":report["material_acceptance"]["native_material_gate"],"passed":report["material_acceptance"]["native_material_gate"]}}
    report["formal_acceptance"]={"gates":gates,"all_formal_gates":all(gate["passed"] for gate in gates.values()),
        "visual_review_required":True,"naturalness_certified":False}
    return report


def audit_failed_proposal(path,manifest_path):
    """Reconstruct a rejected proposal without treating it as a successful state."""
    chain=audit_chain(manifest_path)
    last=chain["batch_reports"][-1]
    with np.load(last["path"],allow_pickle=False) as baseline:
        baseline_meta=json.loads(str(baseline["metadata_json"].item()))
        source=baseline["backend_source_bed_m"].copy()
        previous_final=baseline["final_bed_m"].copy()
        valid=baseline["backend_valid_mask"] & (baseline["cell_type"]!=-2)
    with np.load(path,allow_pickle=False) as archive:
        a={key:archive[key].copy() for key in archive.files if key!="metadata_json"}
        meta=json.loads(str(archive["metadata_json"].item()))
    for key,value in a.items():
        if np.issubdtype(value.dtype,np.number) and not np.isfinite(value).all():
            raise ValueError("nonfinite failed proposal evidence: "+key)
    np.testing.assert_array_equal(a["source_bed_m"],source)
    np.testing.assert_array_equal(a["successful_beds_m"][0],previous_final)
    if meta["mapping"]!=baseline_meta["mapping"] or {k:v for k,v in meta["config"].items() if k!="steps"}!={k:v for k,v in baseline_meta["core"]["config"].items() if k!="steps"}:
        raise ValueError("failed proposal changed physical scenario")
    core=baseline_meta["core"]
    spacing=core["dx_m"]
    area=spacing**2
    times=np.asarray(meta["successful_times_s"])
    _close(times[0],last["end_time_s"])
    _close(np.diff(times),core["native_dt_s"])
    if a["successful_beds_m"].shape!=(len(times),*source.shape):
        raise ValueError("failed archive successful-history shape mismatch")
    count=len(a["completed_phase_names"])
    if count//4!=len(times)-1:
        raise ValueError("failed proposal phase count disagrees with completed physical steps")
    phases=[]
    residuals=[]
    before=previous_final
    floor=source-core["maximum_original_source_cut_m"]
    for index in range(count):
        phase={key:a["completed_phase_"+key][index].item() for key in ("step_index",*NATIVE_FIELDS,"raw_residual_bulk_m3")}
        phase["phase"]=str(a["completed_phase_names"][index])
        expected_step=last["end_step"]+index//4
        expected_phase=("sand","diffusion","mud","finalize")[index%4]
        if phase["step_index"]!=expected_step or phase["phase"]!=expected_phase:
            raise ValueError("failed archive phase step/order is inconsistent")
        start,end,delta=(a["completed_phase_"+key][index] for key in PHASE_FIELDS)
        np.testing.assert_array_equal(start,before)
        _close(delta,(end-start)*area)
        if np.any(end<floor-2e-6):
            raise ValueError("an allegedly completed phase already crossed the source floor")
        if index%4==3:
            np.testing.assert_array_equal(end,a["successful_beds_m"][index//4+1])
        fraction=core["config"]["sand_fraction"] if expected_phase=="sand" else 1-core["config"]["sand_fraction"]
        injection=int(core["config"]["sediment_parcels"]*fraction)*core["native_parcel_bulk_m3"] if expected_phase in ("sand","mud") else 0.
        _close(phase["injected_bulk_m3"],injection)
        residual=float(delta.sum())-phase["injected_bulk_m3"]+phase["exported_bulk_m3"]+phase["lost_bulk_m3"]-phase["inlet_correction_bulk_m3"]
        _close(phase["raw_residual_bulk_m3"],residual)
        phases.append(phase)
        residuals.append({"step":expected_step,"phase":expected_phase,"residual_bulk_m3":residual})
        before=end
    np.testing.assert_array_equal(a["proposed_start_bed_m"],before)
    expected_phase=("sand","diffusion","mud","finalize")[count%4]
    if meta["proposed_phase"]!=expected_phase:
        raise ValueError("rejected proposal phase does not follow completed phase history")
    proposal=a["proposed_bed_m"].astype(float)
    violation=valid & (proposal<floor-2e-6)
    if not violation.any():
        raise ValueError("floor-rejection archive contains no actual source-floor breach")
    cut=source-proposal
    row,column=np.unravel_index(np.argmax(np.where(valid,cut,-np.inf)),cut.shape)
    return {"failed_proposal_evidence_reconstructed":True,"failed_archive_path":str(Path(path).resolve()),"failed_archive_sha256":file_sha256(path),
            "inherited_chain_end_step":last["end_step"],"inherited_chain_last_archive_sha256":last["sha256"],
            "last_completed_physical_step":last["end_step"]+len(times)-1,"last_completed_physical_time_s":float(times[-1]),
            "rejected_step_index":last["end_step"]+count//4,"rejected_human_step_number":last["end_step"]+count//4+1,
            "rejected_phase":expected_phase,"violating_cell_count":int(violation.sum()),
            "maximum_original_source_cut_m":float(cut[row,column]),"source_floor_m":float(floor[row,column]),
            "maximum_cut_cell_backend_row_column":[int(row),int(column)],"source_bed_at_maximum_cut_m":float(source[row,column]),
            "before_rejected_phase_bed_at_maximum_cut_m":float(before[row,column]),"proposed_bed_at_maximum_cut_m":float(proposal[row,column]),
            "proposed_floor_overshoot_bulk_m3":float(np.maximum(0.,floor-proposal)[violation].sum()*area),
            "completed_phase_material_acceptance":native_material_acceptance(phases,residuals),
            "rejected_phase_material_ledger_available":False,
            "semantics":"proposal was rejected before successful phase publication; no claim of material closure for the rejected phase because its native counters were not archived; completed partial phases are independently audited; successful 512-step chain remains unchanged"}


def publish_failed_proposal(path,manifest_path,directory):
    report=audit_failed_proposal(path,manifest_path)
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    (directory/"failure-cold-audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    with np.load(path,allow_pickle=False) as archive:
        source=archive["source_bed_m"].copy()
        before=archive["proposed_start_bed_m"].copy()
        proposed=archive["proposed_bed_m"].copy()
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["image.interpolation"]="nearest"
    import matplotlib.pyplot as plt
    row,column=report["maximum_cut_cell_backend_row_column"]
    r0,r1=max(0,row-8),min(source.shape[0],row+9)
    c0,c1=max(0,column-12),min(source.shape[1],column+13)
    crop=np.s_[r0:r1,c0:c1]
    floor=source-4.
    common_low=min(float(before[crop].min()),float(proposed[crop].min()))
    common_high=max(float(before[crop].max()),float(proposed[crop].max()))
    fig,axes=plt.subplots(2,2,figsize=(12,9),constrained_layout=True)
    for axis,data,title in zip(axes.flat,(before,floor,proposed,np.maximum(0.,floor-proposed)),
                               ("Actual bed before rejected mud proposal (m)","Original source minus 4 m floor (m)",
                                "Rejected proposed bed (m)","Proposed breach depth below floor (m)")):
        same_bed_scale=axis is axes[0,0] or axis is axes[1,0]
        image=axis.imshow(data[crop],extent=(c0*5.,c1*5.,r1*5.,r0*5.),cmap="Reds" if axis is axes[1,1] else "terrain",
                          vmin=common_low if same_bed_scale else None,vmax=common_high if same_bed_scale else None)
        axis.plot((column+.5)*5.,(row+.5)*5.,"+",color="black",markersize=10)
        axis.set(title=title,xlabel="cross-domain (m)",ylabel="downstream (m)")
        fig.colorbar(image,ax=axis,shrink=.75)
    fig.suptitle(f"Rejected step {report['rejected_human_step_number']} {report['rejected_phase']}: original-source cut {report['maximum_original_source_cut_m']:.6f} m")
    fig.savefig(directory/"rejected-source-floor-proposal.png",dpi=160)
    plt.close(fig)
    root=Path(manifest_path).parent
    index=root/"index.html"
    if index.exists():
        page=index.read_text(encoding="utf-8")
        original=root/"index-before-floor-failure-512.html"
        if not original.exists():
            original.write_text(page,encoding="utf-8")
        relative=Path(os.path.relpath(directory,root)).as_posix()
        banner=f'<aside style="border:2px solid #a82727;padding:16px;margin:18px 0"><strong>Continuation rejected at step {report["rejected_human_step_number"]}, {report["rejected_phase"]}.</strong> Proposed original-source cut {report["maximum_original_source_cut_m"]:.6f} m exceeds the 4 m floor. The figures below remain the successful 512-step chain. <a href="{relative}/failure-cold-audit.json">Independent rejected-proposal audit</a>; <a href="{relative}/rejected-source-floor-proposal.png">actual before and rejected proposal</a>.</aside>'
        marker="<h1>Delta morphodynamics batch chain</h1>"
        index.write_text(page.replace(marker,marker+banner,1),encoding="utf-8")
    return report


def render(path,directory):
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["image.interpolation"]="nearest"
    import matplotlib.pyplot as plt
    directory = Path(directory)
    with np.load(path,allow_pickle=False) as archive:
        a = {key:archive[key].copy() for key in archive.files if key != "metadata_json"}
        meta = json.loads(str(archive["metadata_json"].item()))
    spacing = meta["core"]["dx_m"]
    extent = (0,a["initial_bed_m"].shape[1]*spacing,a["initial_bed_m"].shape[0]*spacing,0)
    original,prepared = a["backend_source_bed_m"],a["backend_prepared_bed_m"]
    low = min(original.min(),prepared.min(),a["initial_bed_m"].min(),a["final_bed_m"].min())
    high = max(original.max(),prepared.max(),a["initial_bed_m"].max(),a["final_bed_m"].max())
    fig,axes = plt.subplots(2,3,figsize=(14,9),constrained_layout=True)
    panels = ((original,"Mapped immutable source bed (m)","terrain",low,high),
              (prepared,"Mapped declared preparation bed (m)","terrain",low,high),
              (a["initial_bed_m"],"Actual saved batch-start bed (m)","terrain",low,high),
              (a["final_bed_m"],"Actual final bed (m)","terrain",low,high),
              (a["final_bed_m"]-a["initial_bed_m"],"Actual evolution bed change (m)","coolwarm",None,None),
              (np.hypot(a["qx_m2_s"][-1],a["qz_m2_s"][-1]),"Native steady flux magnitude (m2/s)","viridis",0,None))
    for axis,(data,title,cmap,vmin,vmax) in zip(axes.flat,panels):
        image=axis.imshow(data,extent=extent,cmap=cmap,vmin=vmin,vmax=vmax)
        axis.set(title=title,xlabel="backend cross-domain coordinate (m)",ylabel="backend downstream coordinate (m)")
        fig.colorbar(image,ax=axis,shrink=.8)
    fig.suptitle("Three input identities and actual model evolution; native bulk bed volumes")
    fig.savefig(directory/"actual-input-evolution.png",dpi=140)
    plt.close(fig)
    indices=np.unique(np.linspace(0,len(a["times_s"])-1,4).astype(int))
    fig,axes=plt.subplots(1,len(indices),figsize=(4*len(indices),6),constrained_layout=True,squeeze=False)
    for axis,index in zip(axes.flat,indices):
        image=axis.imshow(a["beds_m"][index],extent=extent,cmap="terrain",vmin=low,vmax=high)
        axis.set(title="Physical t = "+format(a["times_s"][index],".3g")+" s",xlabel="cross-domain (m)",ylabel="downstream (m)")
        fig.colorbar(image,ax=axis,shrink=.7)
    fig.savefig(directory/"physical-time-evolution.png",dpi=140)
    plt.close(fig)
    phase_delta=a["phase_delta_bulk_m3"].sum(axis=(1,2))
    phases=meta["phases"]
    fig,axes=plt.subplots(1,2,figsize=(13,4),constrained_layout=True)
    for name in phase_order(meta["core"]):
        selected=np.array([phase["phase"]==name for phase in phases])
        axes[0].plot(np.cumsum(np.where(selected,phase_delta,0.)),label=name+" actual bulk change")
    for field,label_text in (("injected_bulk_m3","native injected"),("exported_bulk_m3","native exported"),("lost_bulk_m3","native lost"),("inlet_correction_bulk_m3","inlet BC correction")):
        axes[1].plot(np.cumsum([phase[field] for phase in phases]),label=label_text)
    for axis in axes:
        axis.set(xlabel="native phase index",ylabel="native bulk m3")
        axis.legend(fontsize=8)
    fig.savefig(directory/"native-phase-materials.png",dpi=140)
    plt.close(fig)
    inlet_columns=np.flatnonzero(a["backend_inlet_mask"].any(axis=0))
    center=int(np.median(inlet_columns))
    c0,c1=max(0,center-35),min(original.shape[1],center+36)
    r1=min(original.shape[0],80)
    zoom_extent=(c0*spacing,c1*spacing,r1*spacing,0)
    fig,axes=plt.subplots(1,3,figsize=(14,7),constrained_layout=True)
    for axis,data,title,cmap in zip(axes,(a["final_bed_m"],a["depths_m"][-1],a["qx_m2_s"][-1]),
                                  ("Final actual bed (m)","Final actual water depth (m)","Native downstream flux (m2/s)"),
                                  ("terrain","Blues","viridis")):
        image=axis.imshow(data[:r1,c0:c1],extent=zoom_extent,cmap=cmap)
        axis.set(title=title,xlabel="cross-domain (m)",ylabel="downstream (m)")
        fig.colorbar(image,ax=axis,shrink=.65)
        for distance in (50.,100.,150.,200.):
            if distance<r1*spacing:
                axis.axhline(distance,color="crimson",lw=.6,alpha=.8)
    fig.savefig(directory/"delta-depth-bed-flux.png",dpi=150)
    plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    columns=(np.arange(c0,c1)+.5)*spacing
    for axis,distance in zip(axes.flat,(50.,100.,150.,200.)):
        row=min(int(distance/spacing),original.shape[0]-1)
        axis.plot(columns,a["final_bed_m"][row,c0:c1],color="black",label="actual final bed")
        axis.plot(columns,a["stages_m"][-1,row,c0:c1],color="royalblue",label="actual stage")
        axis.fill_between(columns,a["final_bed_m"][row,c0:c1],a["stages_m"][-1,row,c0:c1],
                          where=a["depths_m"][-1,row,c0:c1]>.0,color="skyblue",alpha=.4)
        flux_axis=axis.twinx()
        flux_axis.plot(columns,a["qx_m2_s"][-1,row,c0:c1],color="seagreen",alpha=.8,label="native downstream flux")
        flux_axis.set_ylabel("native flux (m2/s)",color="seagreen")
        axis.set(title=f"Actual cross-section at downstream {row*spacing:g} m",xlabel="cross-domain (m)",ylabel="bed / stage (m)")
        axis.legend(fontsize=8,loc="upper left")
    fig.savefig(directory/"actual-bed-bank-sections.png",dpi=150)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5),constrained_layout=True)
    downstream=(np.arange(original.shape[0])+.5)*spacing
    for axis,limit in zip(axes,(downstream[-1],min(300.,downstream[-1]))):
        for data,title,color in ((original,"immutable source","gray"),(prepared,"declared prepared bed","#a06b42"),
                                 (a["initial_bed_m"],"actual batch-start bed","black"),(a["final_bed_m"],"actual final bed","#287f57"),
                                 (a["stages_m"][-1],"actual final stage","royalblue")):
            axis.plot(downstream,data[:,center],label=title,color=color,lw=1.2)
        axis.set(xlim=(0,limit),xlabel="downstream (m)",ylabel="bed / stage (m)",
                 title=f"Fixed inlet-aligned longitudinal transect at cross-domain {(center+.5)*spacing:g} m")
        axis.legend(fontsize=8)
    fig.savefig(directory/"actual-longitudinal-transect.png",dpi=150)
    plt.close(fig)


def publish_evidence(path,directory):
    """Render a portable saved-array inspection page with explicit gate results."""
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    report=audit_archive(path)
    with np.load(path,allow_pickle=False) as archive:
        a={key:archive[key] for key in archive.files if key!="metadata_json"}
        metadata=json.loads(str(archive["metadata_json"].item()))
        report["sustained_distributary_evidence"]=sustained_distributary_evidence(a,spacing_m=metadata["core"]["dx_m"])
        report["task15_same_support_comparison"]=task15_comparison(metadata["mapping"]) if metadata["source"]["kind"]=="saved_TD" else None
    report["archive_path"]=str(Path(path).resolve())
    report["archive_sha256"]=file_sha256(path)
    report["overall_morphology_accepted"]=False
    (directory/"cold-audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    render(path,directory)
    material=report["material_acceptance"]
    morphology=report["morphology"]
    figures=[("actual-input-evolution.png","Source, preparation, initialization, final state"),
             ("physical-time-evolution.png","Saved physical-time evolution"),
             ("delta-depth-bed-flux.png","Actual delta bed, depth and downstream flux"),
             ("actual-bed-bank-sections.png","Actual beds, banks, water stages and flux"),
             ("actual-longitudinal-transect.png","Actual longitudinal transect aligned with the fixed inlet, not a supplied downstream channel path"),
             ("native-phase-materials.png","Native phase changes and boundary counters")]
    body="".join(f'<figure><img src="{name}" alt="{html.escape(title)}"><figcaption>{html.escape(title)}</figcaption></figure>' for name,title in figures)
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Saved delta morphodynamics evidence</title><style>body{{font:16px system-ui;margin:24px auto;max-width:1500px;padding:0 20px;color:#252525}}img{{width:100%;height:auto}}figure{{margin:28px 0}}table{{border-collapse:collapse}}td,th{{padding:8px 14px;border:1px solid #bbb;text-align:left}}code{{overflow-wrap:anywhere}}</style>
<h1>Saved delta morphodynamics evidence</h1><table><tr><th>Independent check</th><th>Result</th></tr>
<tr><td>Native evidence reconstruction</td><td>{report["native_evidence_reconstructed"]}</td></tr>
<tr><td>Native material tolerance</td><td>{material["native_material_gate"]}</td></tr>
<tr><td>Ocean net bed growth, bulk m3</td><td>{morphology["whole_ocean_net_bed_volume_m3"]:.6f}</td></tr>
<tr><td>Bed above fixed sea level geometrically connected to surviving original land, cells</td><td>{morphology["land_connected_new_emergence"]["cell_count"]}</td></tr>
<tr><td>Fixed-sea-level geometric advance, m</td><td>{morphology["maximum_connected_shoreline_advance_m"]:.3f}</td></tr>
<tr><td>Provisional sustained distributary criteria</td><td>{report["sustained_distributary_evidence"]["sustained_distributary_gate"]}</td></tr>
<tr><td>Naturalness certified</td><td>False</td></tr></table>
<p>Physical duration: {report["physical_duration_s"]:g} seconds. Sediment quantities are native bulk bed volume. Water fields are approximately steady native solutions.</p>
<p>Archive SHA-256: <code>{report["archive_sha256"]}</code>. <a href="cold-audit.json">Complete independent numeric audit</a>.</p>{body}</html>'''
    (directory/"index.html").write_text(page,encoding="utf-8")
    return report


def publish_slope_structure(path,checkpoint_path,directory):
    """One isolated gravity phase; never advance native water or sediment time."""
    from terrain_pipeline.surface_rivers.metric_fluvial_slope_stability import relax_mobile_slopes
    with np.load(path,allow_pickle=False) as archive:
        bed=archive["final_bed_m"].copy()
        source=archive["backend_source_bed_m"].copy()
        prepared=archive["backend_prepared_bed_m"].copy()
        valid=archive["backend_valid_mask"] & (archive["cell_type"]!=-2)
        meta=json.loads(str(archive["metadata_json"].item()))
        spacing=meta["core"]["dx_m"]
    with np.load(checkpoint_path,allow_pickle=False) as checkpoint:
        np.testing.assert_array_equal(bed,checkpoint["eta"])
        fraction=checkpoint["sand_frac"].copy()
        active=checkpoint["active_layer"].copy()
    base=np.minimum(source,bed)
    result=relax_mobile_slopes(bed,base,fraction,active,valid,dx_m=spacing)
    stored_bed=result.bed_m.astype(np.float32)
    stored_fraction=result.sand_fraction.astype(np.float32)
    stored_active=result.active_layer.astype(np.float32)
    mobile_before=(bed.astype(np.float64)-base)*spacing**2
    mobile_after=(stored_bed.astype(np.float64)-base)*spacing**2
    residual={"bulk":float(((stored_bed.astype(np.float64)-bed)*spacing**2).sum()),
              "sand":float((mobile_after*stored_fraction-mobile_before*fraction).sum()),
              "mud":float((mobile_after*(1.-stored_fraction.astype(np.float64))-mobile_before*(1.-fraction.astype(np.float64))).sum())}
    report={"experiment":"isolated gravity-only structure check at unchanged native physical time, not a formal continuation",
            "source_archive_path":str(Path(path).resolve()),"source_archive_sha256":file_sha256(path),
            "native_checkpoint_sha256":file_sha256(checkpoint_path),"float64_solver_converged":bool(result.converged),
            "float64_solver_ledger":result.ledger,"actual_float32_residuals_bulk_m3":residual,
            "float32_minus_float64_bed_bulk_m3":float(((stored_bed-result.bed_m)*spacing**2).sum()),
            "actual_float32_slope_diagnostics":stored_mobile_slope_diagnostics(stored_bed,base,valid,spacing),
            "front_pair_native_rows_columns":[[59,82],[60,82]],
            "front_pair_before_m":[float(bed[59,82]),float(bed[60,82])],
            "front_pair_after_float64_m":[float(result.bed_m[59,82]),float(result.bed_m[60,82])],
            "front_pair_after_float32_m":[float(stored_bed[59,82]),float(stored_bed[60,82])],
            "semantics":"gross paired transferred volumes may count the same material over multiple edges/sweeps; they are not new supply or net deposition. Signed below-base quantization and sub-ULP inventories remain in the actual stored-state evidence. Surface fraction approximates a homogeneous mobile column; conservation here is gravity-only, not native full-chain grain conservation"}
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(directory/"structure-state.npz",actual_before_bed_m=bed,source_bed_m=source,prepared_bed_m=prepared,
                        mobile_base_m=base,valid_mask=valid,before_sand_fraction=fraction,before_active_layer=active,
                        solver_float64_bed_m=result.bed_m,solver_float64_sand_fraction=result.sand_fraction,solver_float64_active_layer=result.active_layer,
                        actual_float32_bed_m=stored_bed,actual_float32_sand_fraction=stored_fraction,actual_float32_active_layer=stored_active)
    report["saved_state_sha256"]=file_sha256(directory/"structure-state.npz")
    (directory/"structure-audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,5),constrained_layout=True)
    for axis,direction in zip(axes,(0,1)):
        indices=np.arange(49,71) if direction==0 else np.arange(72,94)
        for data,name,color in ((source,"immutable source","gray"),(prepared,"prepared bed","#a06b42"),(bed,"before actual gravity","black"),
                                (result.bed_m,"after float64 solve","#287f57"),(stored_bed,"after actual float32 storage","#ad3762")):
            values=data[indices,82] if direction==0 else data[59,indices]
            axis.plot((indices+.5)*spacing,values,label=name,color=color,marker="o",markersize=3,lw=1.)
        axis.set(xlabel=("downstream" if direction==0 else "cross-domain")+" cell-center distance (m)",ylabel="bed elevation (m)",
                 title="Isolated gravity phase: "+("cross-domain 412.5 m" if direction==0 else "downstream 297.5 m"))
        axis.legend(fontsize=8)
    fig.suptitle("1536 native checkpoint held fixed; exact before / float64 solve / actual float32 cells; no smoothing")
    fig.savefig(directory/"before-after-front-sections.png",dpi=150)
    plt.close(fig)
    return report


def publish_front_slope_evidence(path,initial_path,directory,append_html=True):
    """Inspect exact four-neighbor bed steps without assigning a new acceptance gate."""
    with np.load(path,allow_pickle=False) as archive:
        meta=json.loads(str(archive["metadata_json"].item()))
        bed=archive["final_bed_m"].copy()
        source=archive["backend_source_bed_m"].copy()
        prepared=archive["backend_prepared_bed_m"].copy()
        valid=archive["backend_valid_mask"] & (archive["cell_type"]!=-2)
        ocean=archive["backend_ocean_mask"] & valid
        spacing=meta["core"]["dx_m"]
        time=float(archive["times_s"][-1])
    with np.load(initial_path,allow_pickle=False) as first:
        initial=first["initial_bed_m"].copy()
    grown=ocean & (bed-initial>=.05)
    report={"archive_path":str(Path(path).resolve()),"archive_sha256":file_sha256(path),
            "initial_archive_sha256":file_sha256(initial_path),"physical_time_s":time,
            "spacing_m":spacing,"semantics":"exact four-neighbor cell-center elevation differences; absolute slope is rise/run, not a smoothed or reconstructed continuum slope; diagnostics do not change frozen gates",
            "all_original_ocean_neighbors":[],"substantive_growth_mask_boundary_neighbors":[]}
    for axis,direction in ((0,"downstream"),(1,"cross-domain")):
        left=(slice(None,-1),slice(None)) if axis==0 else (slice(None),slice(None,-1))
        right=(slice(1,None),slice(None)) if axis==0 else (slice(None),slice(1,None))
        difference=np.abs(bed[right]-bed[left])
        for key,mask in (("all_original_ocean_neighbors",ocean[left] & ocean[right]),
                         ("substantive_growth_mask_boundary_neighbors",valid[left] & valid[right] & (grown[left]!=grown[right]))):
            if not mask.any():
                continue
            start=tuple(map(int,np.unravel_index(np.argmax(np.where(mask,difference,-1.)),difference.shape)))
            end=(start[0]+(axis==0),start[1]+(axis==1))
            drop=float(difference[start])
            report[key].append({"direction":direction,"start_native_row_column":list(start),"end_native_row_column":list(end),
                                "start_cell_center_downstream_cross_m":[(start[0]+.5)*spacing,(start[1]+.5)*spacing],
                                "end_cell_center_downstream_cross_m":[(end[0]+.5)*spacing,(end[1]+.5)*spacing],
                                "actual_bed_pair_m":[float(bed[start]),float(bed[end])],"absolute_bed_difference_m":drop,
                                "absolute_slope_m_per_m":drop/spacing,"slope_angle_degrees":float(np.degrees(np.arctan(drop/spacing))),
                                "source_absolute_difference_m":float(abs(source[end]-source[start])),
                                "prepared_absolute_difference_m":float(abs(prepared[end]-prepared[start])),
                                "actual_minus_prepared_pair_m":[float(bed[start]-prepared[start]),float(bed[end]-prepared[end])]})
    report["substantive_boundary_definition"]="one neighbor has at least 0.05m actual bed growth since original initialized bed and the other does not; this threshold boundary need not coincide with the steepest foreset"
    directory=Path(directory)
    (directory/"actual-front-slope-audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
    for pair,row_axes in zip(report["all_original_ocean_neighbors"],axes):
        row,column=pair["start_native_row_column"]
        for axis,direction in zip(row_axes,(0,1)):
            center=row if direction==0 else column
            length=bed.shape[direction]
            indices=np.arange(max(0,center-10),min(length,center+12))
            distance=(indices+.5)*spacing
            for data,name,color in ((source,"immutable source","gray"),(prepared,"declared prepared bed","#a06b42"),
                                    (bed,"actual final bed","#287f57")):
                values=data[indices,column] if direction==0 else data[row,indices]
                axis.plot(distance,values,marker="o",markersize=3,label=name,color=color,lw=1.)
            axis.axvline((center+.5)*spacing,color="black",lw=.7,ls=":")
            axis.set(xlabel=("downstream" if direction==0 else "cross-domain")+" cell-center distance (m)",ylabel="actual elevation (m)",
                     title=f"{'Longitudinal' if direction==0 else 'Cross'} section through native ({row}, {column})\n"+
                           (f"Maximum {pair['direction']} neighbor step {pair['absolute_bed_difference_m']:.5f} m / {spacing:g} m\nSlope {pair['absolute_slope_m_per_m']:.5f} m/m ({pair['slope_angle_degrees']:.2f} deg)" if direction==(0 if pair['direction']=="downstream" else 1) else "Same maximum-step location, perpendicular section"))
            axis.legend(fontsize=8)
    fig.suptitle(f"Actual deposition-front steps at t = {time:g} s; saved cell centers, no smoothing; not an added acceptance gate")
    fig.savefig(directory/"actual-deposition-front-sections.png",dpi=150)
    plt.close(fig)
    if append_html:
        page_path=directory/"index.html"
        page=page_path.read_text(encoding="utf-8")
        marker='<section id="actual-front-slope-evidence">'
        if marker in page:
            before,_,tail=page.partition(marker)
            _,_,after=tail.partition("</section>")
            page=before+after
        section=marker+'<h2>Actual Deposition Front</h2><p>Exact original-ocean neighbor differences expose the steep foreset. The 0.05 m growth-mask boundary is separately reported and need not coincide with the steepest bed step. These diagnostics do not change the frozen gates.</p><p><a href="actual-front-slope-audit.json">Independent actual slope audit</a></p><figure><img src="actual-deposition-front-sections.png" alt="Actual local longitudinal and cross sections, immutable source and declared prepared bed"><figcaption>Exact saved cell centers with visible samples; no smoothing.</figcaption></figure></section>'
        page_path.write_text(page.replace("</html>",section+"</html>"),encoding="utf-8")
    return report


def publish_routing_depth_comparison(native_path,sensitivity_path,original_initial_path,directory):
    """Compare saved common-start endpoints after their separate chain cold audits."""
    paths=[Path(native_path),Path(sensitivity_path)]
    histories=(*HISTORY_FIELDS[1:],"ux_m_s","uz_m_s","speed_m_s")
    runs=[]
    for path in paths:
        with np.load(path,allow_pickle=False) as archive:
            meta=json.loads(str(archive["metadata_json"].item()))
            run={"core":meta["core"],"meta":meta,
                 "times":archive["times_s"][[0,-1]].copy(),
                 "initial_base":archive["initial_mobile_base_m"].copy()}
            run.update({key:archive[key][[0,-1]].copy() for key in histories})
            run.update({key:archive[key].copy() for key in ("backend_valid_mask","backend_ocean_mask","backend_inlet_mask","cell_type")})
        runs.append(run)
    native,sensitive=runs
    if native["core"]["algorithm_version"]!=GRAVITY_VERSION or sensitive["core"]["algorithm_version"]!=DRY_DEPTH_VERSION:
        raise ValueError("comparison requires the original gravity and explicit routing-depth sensitivity mechanisms")
    for key in histories:
        np.testing.assert_array_equal(native[key][0],sensitive[key][0],err_msg="comparison common-start mismatch: "+key)
    for key in ("initial_base","times","backend_valid_mask","backend_ocean_mask","backend_inlet_mask","cell_type"):
        np.testing.assert_array_equal(native[key],sensitive[key],err_msg="comparison shared identity mismatch: "+key)
    for key in ("checkpoint_start_sha256","material_state_start_sha256","continuation_identity","config","dx_m","sea_level_m"):
        if native["core"].get(key)!=sensitive["core"].get(key):
            raise ValueError("comparison common-start core identity mismatch: "+key)
    if native["meta"]["source"]!=sensitive["meta"]["source"] or native["meta"]["mapping"]!=sensitive["meta"]["mapping"]:
        raise ValueError("comparison source or mapping changed")
    with np.load(original_initial_path,allow_pickle=False) as archive:
        original_initial=archive["initial_bed_m"].copy()
        np.testing.assert_array_equal(native["backend_ocean_mask"],archive["backend_ocean_mask"])
    spacing=native["core"]["dx_m"]
    sea=native["core"]["sea_level_m"]
    valid=native["backend_valid_mask"] & (native["cell_type"]!=-2)
    ocean=valid & native["backend_ocean_mask"]
    initial=native["beds_m"][0]
    near=ocean & (np.abs(initial-sea)<=.25)
    initial_step=native["core"]["native_start_step_index"]
    end_step=native["core"]["native_end_step_index"]
    names=[f"Common step {initial_step}","Native routing 0.1 m","Sensitivity routing 0.01 m"]
    states=[{key:native[key][0] for key in histories},
            {key:native[key][-1] for key in histories},{key:sensitive[key][-1] for key in histories}]
    masks=[]
    original_land=valid & ~ocean & (original_initial>=sea)
    for state in states:
        above=ocean & (original_initial<=sea) & (state["beds_m"]>sea)
        surviving=original_land & (state["beds_m"]>=sea)
        components,_=label(surviving | above)
        roots=np.unique(components[surviving])
        connected=above & np.isin(components,roots[roots!=0])
        masks.append({"above":above,"connected":connected,"dry":ocean & (state["depths_m"]<=2e-6)})
    report={"common_start_step":initial_step,"end_step":end_step,"physical_times_s":native["times"].tolist(),
            "archive_paths":[str(path.resolve()) for path in paths],"archive_sha256":[file_sha256(path) for path in paths],
            "whole_chain_initial_archive_path":str(Path(original_initial_path).resolve()),
            "whole_chain_initial_archive_sha256":file_sha256(original_initial_path),
            "common_checkpoint_sha256":native["core"]["checkpoint_start_sha256"],
            "common_material_state_sha256":native["core"]["material_state_start_sha256"],
            "near_sea_level_cohort":{"reference":f"actual step {initial_step} bed, frozen for both endpoints; original-ocean valid cells within +/-0.25m of fixed sea level",
                                     "cell_count":int(near.sum()),"area_m2":float(near.sum()*spacing**2)},
            "surface_reference":"geometry uses the original whole-chain initialized bed/ocean and surviving original land; actual dry exposure uses native depth<=2e-6m, independently of routing dry_depth",
            "routing_depth_semantics":"coupled native water weights, velocity wet mask, flooding and both sediment routers; native shoreline criterion depth<0.1*h0 remains unchanged; final stage may evolve through routing, smoothing, underrelaxation and flooding",
            "runs":[],"semantics":"actual saved arrays only; delta and fixed-cohort deposition are measured since the common comparison start, not whole-chain growth or material-source attribution; no new acceptance thresholds"}
    for run,state,mask in zip(runs,states[1:],masks[1:]):
        change=state["beds_m"]-initial
        cohort={"net_bed_change_bulk_m3":float(change[near].sum()*spacing**2),
                "positive_bed_change_bulk_m3":float(np.maximum(0.,change[near]).sum()*spacing**2),
                "negative_bed_change_bulk_m3":float(np.minimum(0.,change[near]).sum()*spacing**2),
                "actual_dry_area_m2":float((near & mask["dry"]).sum()*spacing**2)}
        for key in ("beds_m","depths_m","stages_m"):
            values=state[key][near]
            cohort[key+"_min_mean_max"]=[float(values.min()),float(values.mean()),float(values.max())] if values.size else None
        report["runs"].append({"algorithm_version":run["core"]["algorithm_version"],"mechanism_identity":run["core"]["mechanism_identity"],
            "fixed_common_start_cohort":cohort,
            "whole_chain_surface_exposure":surface_exposure_diagnostics(original_initial,state["beds_m"],state["depths_m"],ocean,valid,spacing,sea),
            "actual_original_ocean_dry_area_m2":float(mask["dry"].sum()*spacing**2)})
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["image.interpolation"]="nearest"
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    extent=(0,initial.shape[1]*spacing,initial.shape[0]*spacing,0)
    def draw(axis,data,title,cmap,limits,mask=valid):
        im=axis.imshow(np.ma.masked_where(~mask,data),extent=extent,cmap=cmap,vmin=limits[0],vmax=limits[1])
        axis.set(title=title,xlabel="cross-domain (m)",ylabel="downstream (m)")
        return im
    fields=(("beds_m","Actual bed (m)","terrain"),("depths_m","Actual depth (m)","Blues"),
            ("stages_m","Actual water stage (m)","cividis"),("qx_m2_s","Positive downstream flux (m2/s)","viridis"))
    fig,axes=plt.subplots(4,3,figsize=(16,20),constrained_layout=True)
    for row,(key,title,cmap) in enumerate(fields):
        values=[np.maximum(0.,state[key]) if key=="qx_m2_s" else state[key] for state in states]
        limits=(min(float(value[valid].min()) for value in values),max(float(value[valid].max()) for value in values))
        for axis,value,name in zip(axes[row],values,names):
            im=draw(axis,value,name+"\n"+title,cmap,limits)
        fig.colorbar(im,ax=list(axes[row]),shrink=.7)
    fig.suptitle(f"Saved step {initial_step} common start and step {end_step} endpoints; shared axes and row color scale")
    fig.savefig(directory/"common-start-bed-depth-stage-positive-flux.png",dpi=140)
    plt.close(fig)
    fig,axes=plt.subplots(4,3,figsize=(16,20),constrained_layout=True)
    for row,(key,title,_) in enumerate(fields):
        values=[states[1][key]-states[0][key],states[2][key]-states[0][key],states[2][key]-states[1][key]]
        limit=max(max(float(np.abs(value[valid]).max()) for value in values),1e-12)
        for axis,value,name in zip(axes[row],values,("Native minus common start","Sensitivity minus common start","Sensitivity minus native")):
            im=draw(axis,value,name+"\n"+title.replace("Positive downstream","Signed downstream")+" difference","coolwarm",(-limit,limit))
        fig.colorbar(im,ax=list(axes[row]),shrink=.7)
    fig.suptitle("Actual endpoint differences; flux difference is signed native qx, not clipped positive flux")
    fig.savefig(directory/"actual-common-start-and-endpoint-differences.png",dpi=140)
    plt.close(fig)
    fig,axes=plt.subplots(4,3,figsize=(16,20),constrained_layout=True)
    for column,(name,state,mask) in enumerate(zip(names,states,masks)):
        im=draw(axes[0,column],state["beds_m"],name+"\nActual bed; fixed sea +/-0.25m","coolwarm",(sea-.25,sea+.25))
        for row,(key,title,color) in enumerate((("above","Bed above fixed sea","#d89841"),("connected","Geometric original-land connection","#287f57"),("dry","Actual ocean dry depth <=2e-6m","#995b9d")),1):
            draw(axes[row,column],mask[key].astype(float),f"{title}\n{mask[key].sum()*spacing**2:g} m2",ListedColormap(["#edf0f2",color]),(0,1))
    fig.colorbar(im,ax=list(axes[0]),shrink=.7)
    fig.suptitle("Full-chain sea-reference geometry and actual local exposure are separate; no routing-threshold dry mask")
    fig.savefig(directory/"geometry-and-actual-dry-exposure.png",dpi=140)
    plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,11),constrained_layout=True)
    bed_limit=max(max(float(np.abs((state["beds_m"]-initial)[near]).max(initial=0.)) for state in states[1:]),1e-12)
    depth_limit=max(float(state["depths_m"][near].max(initial=0.)) for state in states)
    for column,(state,name) in enumerate(zip(states[1:],names[1:])):
        im=draw(axes[0,column],state["beds_m"]-initial,name+"\nActual bed change since common start","coolwarm",(-bed_limit,bed_limit),near)
        im_depth=draw(axes[1,column],state["depths_m"],name+"\nActual final depth on same frozen cells","Blues",(0,max(depth_limit,1e-12)),near)
    fig.colorbar(im,ax=list(axes[0]),shrink=.7)
    fig.colorbar(im_depth,ax=list(axes[1]),shrink=.7)
    fig.suptitle(f"Fixed cohort: original-ocean actual step {initial_step} bed within +/-0.25m of sea; {near.sum()} cells")
    fig.savefig(directory/"fixed-common-start-near-sea-level-cohort.png",dpi=150)
    plt.close(fig)
    inlet_columns=np.flatnonzero(native["backend_inlet_mask"].any(axis=0))
    center=int(np.median(inlet_columns))
    # The baseline's steepest original-ocean downstream step anchors both front sections.
    neighbor=ocean[:-1] & ocean[1:]
    front=np.abs(states[1]["beds_m"][1:]-states[1]["beds_m"][:-1])
    front_row,front_column=map(int,np.unravel_index(np.argmax(np.where(neighbor,front,-1.)),front.shape))
    sections=[("cross",min(int(distance/spacing),initial.shape[0]-1)) for distance in (150.,200.,240.)]
    sections += [("long",center),("long",front_column),("cross",front_row)]
    fig,axes=plt.subplots(2,3,figsize=(17,10),constrained_layout=True)
    section_records=[]
    for position,(axis,(direction,index)) in enumerate(zip(axes.flat,sections)):
        coordinates=(np.arange(initial.shape[1] if direction=="cross" else initial.shape[0])+.5)*spacing
        inspection=slice(None)
        if position>=4:
            anchor=front_column if direction=="cross" else front_row
            inspection=slice(max(0,anchor-10),min(len(coordinates),anchor+12))
            coordinates=coordinates[inspection]
        selected=(index,inspection) if direction=="cross" else (inspection,index)
        for state,name,color in zip(states,names,("#666666","#247b55","#b75232")):
            axis.plot(coordinates,state["beds_m"][selected],color=color,label=name+" bed",lw=1.2)
            axis.plot(coordinates,state["stages_m"][selected],color=color,label=name+" stage",lw=1.,ls="--")
        axis.axhline(sea,color="black",lw=.6,ls=":")
        axis.set(title=f"{direction} section, fixed native {'row' if direction=='cross' else 'column'} {index}",
                 xlabel=("cross-domain" if direction=="cross" else "downstream")+" cell-center distance (m)",ylabel="actual bed / stage (m)")
        axis.legend(fontsize=7)
        section_records.append({"direction":direction,"native_index":index})
    fig.suptitle("Exact saved-cell sections; common initial bed/stage and both endpoints; no smoothing")
    fig.savefig(directory/"shared-bed-stage-and-deposition-front-sections.png",dpi=150)
    plt.close(fig)
    report["sections"]=section_records
    report["front_section_anchor"]={"reference":"native 0.1m endpoint maximum original-ocean downstream neighbor step; same location used for both endpoints",
                                      "native_row_column":[front_row,front_column],
                                      "actual_initial_native_sensitivity_bed_pairs_m":[[float(state["beds_m"][front_row,front_column]),float(state["beds_m"][front_row+1,front_column])] for state in states]}
    (directory/"routing-depth-comparison.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    figures=("common-start-bed-depth-stage-positive-flux.png","actual-common-start-and-endpoint-differences.png",
             "geometry-and-actual-dry-exposure.png","fixed-common-start-near-sea-level-cohort.png","shared-bed-stage-and-deposition-front-sections.png")
    body="".join(f'<figure><img src="{name}" alt="{html.escape(name)}"></figure>' for name in figures)
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Routing-depth actual comparison</title>
<style>body{{font:16px system-ui;max-width:1600px;margin:24px auto;padding:0 20px}}img{{width:100%;height:auto}}figure{{margin:24px 0}}</style>
<h1>Actual routing-depth comparison</h1><p>Common start: step {initial_step}; endpoints: step {end_step}. Native 0.1m and explicit sensitivity 0.01m share the same initial bed, water, velocity, mobile base, native checkpoint and RNG.</p>
<p>Changes and the frozen near-sea cohort use the actual common-start bed. Sea-reference emergence and original-land connection use the original whole-chain initial bed. Actual dry exposure uses depth &lt;=2e-6m independently of either routing threshold. No new acceptance gates or material-source attribution.</p>
<p>This is a coupled routing-threshold sensitivity affecting water weights, wet velocity masks, flooding and both sediment routers. The separate native shoreline criterion depth &lt; 0.1*h0 remains unchanged. Saved final stage may evolve through routing, smoothing, underrelaxation and flooding.</p>
<p><a href="routing-depth-comparison.json">Exact paired provenance and measurements</a></p>{body}</html>'''
    (directory/"index.html").write_text(page,encoding="utf-8")
    return report


def publish_water_repair_evolution(paths,directory):
    """Compare stored v6 states against their actual v5 handoff, without interpolation."""
    snapshots=[]
    with np.load(paths[0],allow_pickle=False) as first:
        original=first["initial_bed_m"].copy()
    for path in paths:
        with np.load(path,allow_pickle=False) as archive:
            core=json.loads(str(archive["metadata_json"].item()))["core"]
            if core.get("algorithm_version")!=WATER_ROUTING_REPAIR_VERSION:
                continue
            if not snapshots:
                positions=[0,-1]
                spacing=core["dx_m"]
                sea=core["sea_level_m"]
                valid=archive["backend_valid_mask"] & (archive["cell_type"]!=-2)
                ocean=archive["backend_ocean_mask"].copy()
            else:
                positions=[-1]
            for position in positions:
                snapshot={key:archive[key][position].copy() for key in HISTORY_FIELDS}
                snapshot["step"]=core["native_start_step_index"]+(position if position>=0 else len(archive["times_s"])+position)
                snapshot["archive_path"]=str(Path(path).resolve())
                arrays={key:archive[key][position:position+1] if position>=0 else archive[key][-1:] for key in HISTORY_FIELDS}
                arrays.update({key:archive[key] for key in ("backend_valid_mask","backend_ocean_mask","backend_inlet_mask","backend_export_mask","cell_type")})
                snapshot["branches"]=sustained_distributary_evidence(arrays,final_snapshots=1,spacing_m=spacing)["snapshots"][0]
                snapshots.append(snapshot)
    if not snapshots:
        return None
    selected=np.unique(np.linspace(0,len(snapshots)-1,min(5,len(snapshots))).astype(int))
    chosen=[snapshots[index] for index in selected]
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    fig,axes=plt.subplots(4,len(chosen),figsize=(5*len(chosen),17),squeeze=False,constrained_layout=True)
    extent=(0,original.shape[1]*spacing,original.shape[0]*spacing,0)
    ranges={key:(min(float(s[key][valid].min()) for s in chosen),max(float(s[key][valid].max()) for s in chosen))
            for key in ("beds_m","depths_m","qx_m2_s")}
    diagnostics=[]
    xx=(np.arange(original.shape[1])+.5)*spacing
    yy=(np.arange(original.shape[0])+.5)*spacing
    for column,snapshot in enumerate(chosen):
        bed,depth=snapshot["beds_m"],snapshot["depths_m"]
        dry=valid & (depth<=2e-6)
        exposure=surface_exposure_diagnostics(original,bed,depth,ocean,valid,spacing,sea)
        diagnostics.append({"native_step":snapshot["step"],"physical_time_s":float(snapshot["times_s"]),
                            "archive_path":snapshot["archive_path"],"surface_exposure":exposure,
                            "valid_actual_dry_area_m2":float(dry.sum()*spacing**2),
                            "single_snapshot_distributary_evidence":snapshot["branches"]})
        for row,key,title,cmap in ((0,"beds_m","Actual bed / fixed-sea shoreline","terrain"),
                                   (1,"depths_m","Actual water depth (m)","Blues"),
                                   (3,"qx_m2_s","Actual downstream flux (m2/s)","coolwarm")):
            axis=axes[row,column]
            image=axis.imshow(np.ma.masked_where(~valid,snapshot[key]),extent=extent,cmap=cmap,
                              vmin=ranges[key][0],vmax=ranges[key][1])
            fig.colorbar(image,ax=axis,shrink=.7)
            axis.set_title(f"Step {snapshot['step']}; t={float(snapshot['times_s']):g}s\n{title}")
        axes[2,column].imshow(np.ma.masked_where(~valid,dry.astype(float)),extent=extent,
                             cmap=ListedColormap(["#cde5f1","#ad864a"]),vmin=0,vmax=1)
        axes[2,column].set_title(f"Actual dry depth <= 2e-6 m\nValid dry area: {dry.sum()*spacing**2:g} m2")
        if (bed[valid]<sea).any() and (bed[valid]>sea).any():
            axes[0,column].contour(xx,yy,np.ma.masked_where(~valid,bed),levels=[sea],colors="black",linewidths=.7)
        for track in snapshot["branches"]["qualifying_tracks"]:
            points=track["branch_centers_by_row"]
            for branch in (0,1):
                axes[3,column].plot([(p["columns"][branch]+.5)*spacing for p in points],
                                    [(p["row"]+.5)*spacing for p in points],color="#dbb530",linewidth=.6)
        axes[3,column].set_title(axes[3,column].get_title()+f"\nQualifying banked pairs: {len(snapshot['branches']['qualifying_tracks'])}")
    for axis in axes.flat:
        axis.set(xlabel="cross-domain (m)",ylabel="downstream (m)")
    fig.suptitle("Actual saved water-repair evolution; shared color scales; black = bed at fixed sea level; gold = detected banked branch pairs")
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    fig.savefig(directory/"water-repair-actual-evolution.png",dpi=140)
    plt.close(fig)
    report={"semantics":"actual saved v5 handoff and v6 batch endpoints; no smoothing or imposed channels; single-frame branch paths do not establish sustained final-three-frame acceptance",
            "snapshots":diagnostics,"shared_display_ranges":ranges}
    (directory/"water-repair-actual-evolution.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


def publish_chain(manifest_path,directory):
    report=formal_acceptance(manifest_path)
    if report["source_kind"]=="saved_TD":
        report["task15_same_support_comparison"]=task15_comparison(report["mapping"])
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    (directory/"cold-chain-audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    manifest_path=Path(manifest_path)
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    paths=[Path(batch["path"]) if Path(batch["path"]).is_absolute() else manifest_path.parent/batch["path"] for batch in manifest["batches"]]
    water_evolution=publish_water_repair_evolution(paths,directory)
    render(paths[-1],directory)
    publish_front_slope_evidence(paths[-1],paths[0],directory,append_html=False)
    snapshots=[]
    cumulative_positive_bc=None
    phase_changes=[]
    counters={field:[] for field in NATIVE_FIELDS}
    for index,path in enumerate(paths):
        with np.load(path,allow_pickle=False) as archive:
            meta=json.loads(str(archive["metadata_json"].item()))
            if index==0:
                snapshots.append((float(archive["times_s"][0]),archive["initial_bed_m"].copy()))
                cumulative_positive_bc=np.zeros(archive["initial_bed_m"].shape)
                ocean=archive["backend_ocean_mask"].copy()
            finalize=np.array([phase["phase"]=="finalize" for phase in meta["phases"]])
            cumulative_positive_bc+=np.maximum(0.,archive["phase_delta_bulk_m3"][finalize]).sum(axis=0)/(meta["core"]["dx_m"]**2)
            snapshots.append((float(archive["times_s"][-1]),archive["final_bed_m"].copy()))
            for phase in meta["phases"]:
                phase_changes.append(phase["injected_bulk_m3"]-phase["exported_bulk_m3"]-phase["lost_bulk_m3"]+phase["inlet_correction_bulk_m3"]+phase["raw_residual_bulk_m3"])
                for field in NATIVE_FIELDS:
                    counters[field].append(phase[field])
    import matplotlib.pyplot as plt
    actual_final=snapshots[-1][1]
    corrected_final=actual_final-cumulative_positive_bc
    guarded_final=corrected_final.copy()
    guarded_final[ocean]-=2e-6
    np.savez_compressed(directory/"contribution-adjusted-bed.npz",actual_initial_bed_m=snapshots[0][1],actual_final_bed_m=actual_final,
                        positive_finalization_delta_m=cumulative_positive_bc,contribution_adjusted_final_bed_m=corrected_final,
                        numeric_guarded_contribution_adjusted_final_bed_m=guarded_final)
    fig,axes=plt.subplots(1,3,figsize=(15,6),constrained_layout=True)
    for axis,bed,title in zip(axes,(actual_final,corrected_final,corrected_final-snapshots[0][1]),
                              ("Actual final native bed (m)","Bed minus positive boundary work (m)","Growth excluding positive boundary work (m)")):
        image=axis.imshow(bed,cmap="terrain" if axis is not axes[-1] else "coolwarm")
        axis.set(title=title,xlabel="native column",ylabel="native row")
        fig.colorbar(image,ax=axis,shrink=.7)
    fig.savefig(directory/"actual-and-contribution-adjusted-bed.png",dpi=150)
    plt.close(fig)
    if report["source_kind"]=="saved_TD":
        with np.load(TASK15,allow_pickle=False) as previous:
            previous_initial=_mapped(previous["initial_bed_m"],report["mapping"])
            previous_final=_mapped(previous["final_bed_m"],report["mapping"])
        extent=(0,actual_final.shape[1]*report["spacing_m"],actual_final.shape[0]*report["spacing_m"],0)
        fig,axes=plt.subplots(2,2,figsize=(13,11),constrained_layout=True)
        for axis,bed,title in zip(axes[0],(previous_final,actual_final),("Task15 saved actual final bed (m)","Task16 saved actual final bed (m)")):
            image=axis.imshow(bed,extent=extent,cmap="terrain",vmin=-5.,vmax=2.)
            axis.set(title=title+"; display range -5 to 2",xlabel="cross-domain (m)",ylabel="downstream (m)")
            fig.colorbar(image,ax=axis,shrink=.7)
        for axis,delta,title in zip(axes[1],(previous_final-previous_initial,actual_final-snapshots[0][1]),
                                    ("Task15 actual bed change (m)","Task16 actual bed change (m)")):
            image=axis.imshow(delta,extent=extent,cmap="coolwarm",vmin=-4.,vmax=4.)
            axis.set(title=title+"; display range -4 to 4",xlabel="cross-domain (m)",ylabel="downstream (m)")
            fig.colorbar(image,ax=axis,shrink=.7)
        fig.savefig(directory/"task15-task16-actual-bed-comparison.png",dpi=150)
        plt.close(fig)
    with np.load(paths[-1],allow_pickle=False) as latest:
        valid=latest["backend_valid_mask"] & (latest["cell_type"]!=-2)
        sea_level=meta["core"]["sea_level_m"]
    initial_land=valid & ~ocean & (snapshots[0][1]>=sea_level)
    surviving_land=initial_land & (actual_final>=sea_level)
    new_land=valid & ocean & (snapshots[0][1]<=sea_level) & (actual_final>sea_level)
    land_labels,_=label(surviving_land | new_land)
    roots=np.unique(land_labels[surviving_land])
    connected_new=new_land & np.isin(land_labels,roots[roots!=0])
    changed=valid & (np.abs(actual_final-snapshots[0][1])>=.05)
    locations=np.argwhere(changed | new_land)
    if locations.size:
        first=locations.min(axis=0)
        last=locations.max(axis=0)+1
        r0,c0=np.maximum(first-10,0)
        r1,c1=np.minimum(last+10,actual_final.shape)
    else:
        r0,c0=0,0
        r1,c1=actual_final.shape
    crop=np.s_[r0:r1,c0:c1]
    spacing=report["spacing_m"]
    extent=(c0*spacing,c1*spacing,r1*spacing,r0*spacing)
    xx=(np.arange(c0,c1)+.5)*spacing
    yy=(np.arange(r0,r1)+.5)*spacing
    from matplotlib.colors import ListedColormap
    fig,axes=plt.subplots(2,2,figsize=(13,11),constrained_layout=True)
    image=axes[0,0].imshow(np.ma.masked_where(~valid[crop],actual_final[crop]),extent=extent,cmap="coolwarm",vmin=sea_level-.25,vmax=sea_level+.25)
    axes[0,0].set_title("Actual final bed (m)\nDisplay clipped: sea level +/- 0.25 m")
    fig.colorbar(image,ax=axes[0,0],shrink=.7)
    initial_classes=np.where(ocean,0.,1.)
    axes[0,1].imshow(np.ma.masked_where(~valid[crop],initial_classes[crop]),extent=extent,cmap=ListedColormap(["#cde5f1","#b6b6b6"]),vmin=0,vmax=1)
    axes[0,1].set_title("Initial ocean (blue)\nOriginal land (gray)")
    exposure=report["actual_surface_exposure_diagnostics"]
    for axis,mask,title,color,key in ((axes[1,0],new_land,"Bed above fixed sea level","#da843b","bed_above_fixed_sea_level"),
                                      (axes[1,1],connected_new,"Geometrically connected to surviving original land","#287f57","geometrically_connected_above_sea_bed")):
        axis.imshow(np.ma.masked_where(~valid[crop],mask[crop].astype(float)),extent=extent,cmap=ListedColormap(["#edf0f2",color]),vmin=0,vmax=1)
        diagnostic=exposure[key]
        depth_range=diagnostic["actual_depth_range_m"]
        depth_text=f"native depth {depth_range[0]:.5f} to {depth_range[1]:.5f} m" if depth_range else "no qualifying cells"
        axis.set_title(f"{title}\n{int(mask.sum())} cells / {mask.sum()*spacing**2:g} m2; {depth_text}\nActual dry area (depth <= 2e-6 m): {diagnostic['actual_dry_area_m2']:g} m2")
    for axis in axes.flat:
        if ocean[crop].any() and not ocean[crop].all():
            axis.contour(xx,yy,ocean[crop].astype(float),levels=[.5],colors="black",linewidths=.8)
        axis.set(xlabel="cross-domain (m)",ylabel="downstream (m)")
    fig.suptitle(f"Actual physical t = {snapshots[-1][0]:g} s; black line = initial land-ocean boundary; no smoothing")
    fig.savefig(directory/"near-sea-level-and-emergence-masks.png",dpi=160)
    plt.close(fig)
    selected=np.unique(np.linspace(0,len(snapshots)-1,min(5,len(snapshots))).astype(int))
    fig,axes=plt.subplots(1,len(selected),figsize=(4*len(selected),6),constrained_layout=True,squeeze=False)
    low=min(float(snapshots[i][1].min()) for i in selected)
    high=max(float(snapshots[i][1].max()) for i in selected)
    for axis,index in zip(axes.flat,selected):
        time,bed=snapshots[index]
        image=axis.imshow(bed,cmap="terrain",vmin=low,vmax=high)
        axis.set(title=f"Full-chain physical t = {time:g} s",xlabel="native column",ylabel="native row")
        fig.colorbar(image,ax=axis,shrink=.7)
    fig.savefig(directory/"full-chain-evolution.png",dpi=150)
    plt.close(fig)
    fig,axis=plt.subplots(figsize=(12,5),constrained_layout=True)
    axis.plot(np.cumsum(phase_changes),label="actual bed delta (cold reconstructed)")
    for field,values in counters.items():
        axis.plot(np.cumsum(values),label=field)
    axis.set(xlabel="native phase index across all batches",ylabel="native bulk m3")
    axis.legend(fontsize=8)
    fig.savefig(directory/"full-chain-materials.png",dpi=150)
    plt.close(fig)
    morphology=report["morphology"]
    adjusted=report["contribution_excluded_morphology"]
    gate_labels={"land_connected_new_emergence_area_m2":"Above-fixed-sea-level bed geometrically connected to surviving original land (m2)",
                 "connected_shoreline_advance_m":"Fixed-sea-level geometric advance (m)"}
    formal_rows="".join(f'<tr><td>{html.escape(gate_labels.get(name,name))}</td><td>{html.escape(str(gate.get("value","fixed declaration")))}</td><td>{html.escape(str("maximum " + str(gate["maximum"]) if "maximum" in gate else gate.get("minimum","required")))}</td><td>{gate["passed"]}</td></tr>' for name,gate in report["formal_acceptance"]["gates"].items())
    exposure_rows="".join(f'<tr><td>{html.escape(name)}</td><td>{item["area_m2"]:g}</td><td>{html.escape(str(item["actual_depth_range_m"]))}</td><td>{item["actual_dry_area_m2"]:g}</td></tr>' for name,item in exposure.items() if isinstance(item,dict))
    transitions="".join(f'<p>Mechanism transition after step {item["after_step"]}: {html.escape(item["from_algorithm_version"])} to {html.escape(item["to_algorithm_version"])}. {html.escape(item["reason"])}</p>' for item in report["mechanism_transitions"])
    for item in report["mechanism_transitions"]:
        if item.get("failed_archive_path"):
            failed_directory=Path(item["failed_archive_path"]).parent
            audit_link=Path(os.path.relpath(failed_directory/"failure-cold-audit.json",directory)).as_posix()
            figure_link=Path(os.path.relpath(failed_directory/"rejected-source-floor-proposal.png",directory)).as_posix()
            transitions+=f'<p><a href="{html.escape(audit_link)}">Preserved rejected native proposal audit</a> | <a href="{html.escape(figure_link)}">Actual rejected proposal and source floor</a>. Successful inherited batches remain unchanged; full transition and artifact hashes are in the chain audit.</p>'
    gravity_phases=[phase for batch in report["batch_reports"] if batch.get("gravity_evidence") for phase in batch["gravity_evidence"]["phases"]]
    gravity_summary=""
    if gravity_phases:
        maximum=max(phase["stored_slope"]["maximum_excess_after_two_endpoint_half_ulp_bound_m"] for phase in gravity_phases)
        totals={grain:sum(phase["actual_residuals_bulk_m3"][grain] for phase in gravity_phases) for grain in ("bulk","sand","mud")}
        gravity_summary=f'<p>Independent actual stored-state gravity audit: {len(gravity_phases)} phases. Maximum resolvable mobile slope excess after the two-endpoint half-ULP bound: {maximum:.9g} m (required &lt;= 1e-6 m). Signed cumulative gravity-only bulk / sand / mud residuals: {totals["bulk"]:.9g} / {totals["sand"]:.9g} / {totals["mud"]:.9g} bulk m3. Full actual quantization, sub-ULP inventory and float64 solver evidence are retained in the cold audit. This does not assert grain-class conservation in native routing.</p>'
    figures=[("full-chain-evolution.png","Evolution from the first initial bed across saved batch endpoints"),
             ("actual-and-contribution-adjusted-bed.png","Actual and boundary-work contribution adjusted beds; water fields remain actual native fields"),
             ("near-sea-level-and-emergence-masks.png","Actual near-sea-level bed, initial coast, bed above fixed sea level and geometric connection to surviving original land; local native water depth and actual dry area shown separately"),
             ("full-chain-materials.png","Cumulative materials across all independently audited native phases"),
             ("delta-depth-bed-flux.png","Actual final bed, depth and native downstream flux"),
             ("actual-bed-bank-sections.png","Actual final bed-bank cross-sections and native flux"),
             ("actual-deposition-front-sections.png","Exact saved-cell deposition-front longitudinal and cross sections against immutable source and declared preparation; see actual-front-slope-audit.json for slope diagnostics"),
             ("actual-longitudinal-transect.png","Actual longitudinal transect aligned with the fixed inlet; a fixed inspection section, not an imposed channel")]
    if water_evolution:
        figures.insert(0,("water-repair-actual-evolution.png","Actual v5 handoff and v6 saved endpoints: shared-scale bed, depth, actual dry exposure, fixed-sea shoreline and native downstream flux with independently detected banked pairs; diagnostics in water-repair-actual-evolution.json"))
    if report["source_kind"]=="saved_TD":
        figures.insert(1,("task15-task16-actual-bed-comparison.png","Task15 and Task16 actual final beds and changes on the same mapped support; color display ranges are explicitly capped"))
    body="".join(f'<figure><img src="{name}" alt="{html.escape(title)}"><figcaption>{html.escape(title)}</figcaption></figure>' for name,title in figures)
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Delta morphodynamics batch chain</title>
<style>body{{font:16px system-ui;max-width:1500px;margin:24px auto;padding:0 20px;color:#252525}}figure{{margin:28px 0}}img{{width:100%;height:auto}}table{{border-collapse:collapse}}td,th{{border:1px solid #bbb;padding:8px 12px;text-align:left}}</style>
<h1>Delta morphodynamics batch chain</h1><p>Physical duration: {report["physical_duration_s"]:g} seconds. Independently audited batches: {len(report["batch_reports"])}.</p>
{transitions}
{gravity_summary}
<p>Native material tolerance: {report["material_acceptance"]["native_material_gate"]}. Sustained distributary criteria: {report["sustained_distributary_evidence"]["sustained_distributary_gate"]}. Naturalness certified: False.</p>
<p>Ocean net growth: {morphology["whole_ocean_net_bed_volume_m3"]:.6f} bulk m3. Bed above fixed sea level geometrically connected to surviving original land: {morphology["land_connected_new_emergence"]["cell_count"]} cells. Maximum fixed-sea-level geometric advance: {morphology["maximum_connected_shoreline_advance_m"]:g} m.</p>
<p>Bed above fixed sea level does not imply dry land: local native water stage can remain higher. The frozen morphology gates retain their sea-reference geometry; actual dry exposure below is a separate diagnostic using native depth &lt;= 2e-6 m.</p>
<table><tr><th>Geometric set</th><th>Area (m2)</th><th>Actual native depth range (m)</th><th>Actual dry area (m2)</th></tr>{exposure_rows}</table>
<p>Ocean net growth after conservative contribution exclusion: {adjusted["whole_ocean_net_bed_volume_m3"]:.6f} bulk m3. Full formal numeric criteria: {report["formal_acceptance"]["all_formal_gates"]}. Visual review remains required.</p>
<table><tr><th>Formal criterion</th><th>Actual value</th><th>Threshold / requirement</th><th>Passed</th></tr>{formal_rows}</table>
<p><a href="cold-chain-audit.json">Complete cold chain audit</a> | <a href="actual-front-slope-audit.json">Exact actual deposition-front slope audit</a></p>{body}</html>'''
    (directory/"index.html").write_text(page,encoding="utf-8")
    return report


if __name__ == "__main__":
    resource_limits()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task15-comparison",action="store_true")
    parser.add_argument("--audit",type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--render",type=Path)
    parser.add_argument("--publish",type=Path)
    parser.add_argument("--audit-chain",type=Path)
    parser.add_argument("--publish-chain",type=Path)
    parser.add_argument("--compare-routing-depth",type=Path,nargs=3,metavar=("NATIVE_DETAIL","SENSITIVITY_DETAIL","ORIGINAL_INITIAL_DETAIL"))
    parser.add_argument("--formal-acceptance",type=Path)
    parser.add_argument("--failed-proposal",type=Path)
    parser.add_argument("--chain-manifest",type=Path)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    if args.task15_comparison:
        print(json.dumps(task15_comparison(),indent=2))
    elif args.audit:
        print(json.dumps(audit_archive(args.audit,args.expected_sha256),indent=2))
    elif args.audit_chain:
        print(json.dumps(audit_chain(args.audit_chain),indent=2))
    elif args.formal_acceptance:
        print(json.dumps(formal_acceptance(args.formal_acceptance),indent=2))
    elif args.failed_proposal and args.chain_manifest and args.output:
        print(json.dumps(publish_failed_proposal(args.failed_proposal,args.chain_manifest,args.output),indent=2))
    elif args.compare_routing_depth and args.output:
        report=publish_routing_depth_comparison(*args.compare_routing_depth,args.output)
        print(json.dumps({key:report[key] for key in ("common_start_step","end_step","near_sea_level_cohort")},indent=2))
    elif args.publish_chain and args.output:
        report=publish_chain(args.publish_chain,args.output)
        print(json.dumps({"batch_count":len(report["batch_reports"]),"native_material_gate":report["material_acceptance"]["native_material_gate"],
                          "sustained_distributary_gate":report["sustained_distributary_evidence"]["sustained_distributary_gate"]},indent=2))
    elif args.render and args.output:
        render(args.render,args.output)
    elif args.publish and args.output:
        report=publish_evidence(args.publish,args.output)
        print(json.dumps({"archive_sha256":report["archive_sha256"],"native_material_gate":report["material_acceptance"]["native_material_gate"],
                          "sustained_distributary_gate":report["sustained_distributary_evidence"]["sustained_distributary_gate"]},indent=2))
    else:
        parser.error("--task15-comparison required")
