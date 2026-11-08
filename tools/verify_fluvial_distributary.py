"""Saved-bed acceptance for finite source-cut distributary experiments."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scipy.ndimage import distance_transform_edt, map_coordinates

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary, FluvialDeltaInterval
from tools.verify_fluvial_channel_remobilization import (
    _check_flow_dag, _close, refine, refined_origin, resource_limits, source_input as td_input,
)

DEFAULT_OUTPUT = ROOT / "verification/fluvial-delta/distributary-20261015-01"
MARINE_PREPARATION = {"radius_m":300.,"slope_m_per_m":.03,"maximum_raise_m":16.,
                      "maximum_fill_bulk_m3":2000000.,"supplied_solid_m3":1300000.,"porosity":.35,
                      "minimum_submergence_m":.2}
ACCEPTANCE = {"minimum_branch_fraction": .05, "consecutive_intervals": 3,
              "minimum_separated_branch_length_m": 30., "minimum_bank_relief_m": .05,
              "maximum_uphill_step_m": 1e-6,
              "minimum_cross_section_coverage_fraction": .5,
              "interpretation": "actual derived source-cut bed; old task14 cover-only gate remains false"}


def synthetic_input(interval_count=16):
    bed = np.tile(.2-np.arange(81)*.01,(41,1))
    ocean = bed < 0.
    export = np.zeros(bed.shape,bool)
    export[:,-1] = ocean[:,-1]
    terrain = TerrainGrid(bed,np.ones(bed.shape,bool),0.,0.,5.,5.,"diagnostic_dem_proxy","SYNTHETIC-distributary","a"*64)
    boundary = FluvialDeltaBoundary(ocean,export,0.,2.,"SYNTHETIC-shallow-coast")
    forcing = tuple(FluvialDeltaInterval((20,5),200000.,1200. if i < interval_count//2 else 0.) for i in range(interval_count))
    provenance = {"kind":"SYNTHETIC","path":"SYNTHETIC controlled slope","sha256":"a"*64,
                  "sediment_origin":"explicit external delivery and separately accounted geometric source excavation"}
    return terrain,boundary,forcing,provenance,bed.copy()


def save_archive(path, terrain, boundary, forcing, result, source, raw, coordination=None):
    offsets, cells, volumes = [0], [], []
    records = result["intervals"]
    for record in records:
        for edge in record["flow_edges"]:
            cells.append((*edge["from_cell"], *edge["to_cell"]))
            volumes.append((edge["water_volume_m3"], edge["sediment_solid_m3"]))
        offsets.append(len(cells))
    meta = {"core": result["metadata"], "source": source,
            "boundary": {"sea_level_m":boundary.sea_level_m,"river_head_m":boundary.river_head_m},
            "terrain": {key: value for key, value in asdict(terrain).items() if key not in ("elevation_m", "valid_mask")},
            "forcing": [asdict(item) for item in forcing], "acceptance": ACCEPTANCE,
            "water_ledger": result["water_ledger"], "solid_ledger": result["solid_ledger"],
            "interval_ledgers": [{"water": record["water_ledger"], "solid": record["solid_ledger"]} for record in records],
            "channel_paths": [record["channel_paths"] for record in records]}
    meta["channel_width_m"] = [record["channel_width_m"] for record in records]
    arrays = {key: result[key] for key in ("initial_bed_m", "final_bed_m", "height_delta_m", "derived_base_bed_m",
              "deposited_solid_m3", "reentrained_solid_m3", "stored_solid_m3", "source_eroded_bulk_m3", "source_eroded_solid_m3",
              "original_source_bed_m", "initial_cover_solid_m3", "unresolved_solid_m3")}
    for saved, key in (("water", "water_throughput_m3"), ("sediment", "sediment_throughput_solid_m3"),
                       ("deposits", "deposited_solid_m3"), ("reentrainment", "reentrained_solid_m3"),
                       ("storage", "stored_solid_m3"), ("source_bulk", "source_eroded_bulk_m3"),
                       ("source_solid", "source_eroded_solid_m3"), ("beds_m", "bed_m")):
        arrays[saved] = np.stack([record[key] for record in records])
    arrays["escrow"] = np.stack([record["unresolved_solid_m3"] for record in records])
    arrays.update(raw_td_m=raw, valid_mask=terrain.valid_mask, ocean_mask=boundary.initial_ocean_mask,
                  export_mask=boundary.ocean_export_mask, edge_offsets=np.asarray(offsets, np.int64),
                  edge_cells=np.asarray(cells, np.int32).reshape(-1,4), edge_volumes=np.asarray(volumes,float).reshape(-1,2))
    if coordination is not None:
        meta["coordination"] = coordination["metadata"]
        meta["preparation_ledger"] = coordination["preparation_ledger"]
        arrays.update({key:coordination[key] for key in ("coordinated_bed_m","fill_bulk_m3")})
    arrays["metadata_json"] = np.array(json.dumps(meta, sort_keys=True))
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream, **arrays)


def _path_cells(paths):
    if isinstance(paths, dict):
        return paths["trunk"], paths["branches"]
    raise ValueError("named trunk and branches required")


def _profile(path, bed, water, spacing, acceptance, width, shared_port=None):
    cells = np.asarray(path, int)
    if cells.ndim != 2 or cells.shape[1] != 2 or len(cells) < 2:
        raise ValueError("invalid channel path")
    if np.any(cells < 0) or np.any(cells[:,0] >= bed.shape[0]) or np.any(cells[:,1] >= bed.shape[1]):
        raise ValueError("unbounded channel path")
    delta = np.diff(cells, axis=0)
    if np.any(np.abs(delta).sum(axis=1) != 1) or len(set(map(tuple,cells))) != len(cells):
        raise ValueError("channel path must be simple cardinal cells")
    values = bed[cells[:,0],cells[:,1]]
    steps = np.diff(values)
    bank_relief = []
    sections = []
    radius = width/(2*spacing)+1.
    for index,(r,c) in enumerate(cells):
        if shared_port is not None and np.linalg.norm(np.array((r,c))-shared_port)*spacing <= width:
            continue
        before,after = cells[max(0,index-2)],cells[min(len(cells)-1,index+2)]
        tangent = after-before
        length = np.linalg.norm(tangent)
        normal = np.array((-tangent[1],tangent[0]))/length
        sides = np.array((r,c))[None,:]+np.array((-1.,1.))[:,None]*radius*normal
        if np.any(sides < 0.) or np.any(sides[:,0] > bed.shape[0]-1) or np.any(sides[:,1] > bed.shape[1]-1):
            continue
        elevations = map_coordinates(bed,sides.T,order=1,mode="nearest")
        relief = float(elevations.min()-bed[r,c])
        bank_relief.append(relief)
        sections.append({"center_cell":[int(r),int(c)],"bank_sample_row_columns":sides.tolist(),"bank_elevations_m":elevations.tolist(),"bed_m":float(bed[r,c]),"minimum_relief_m":relief})
    minimum_relief = min(bank_relief,default=-1e30)
    coverage = min(1.,len(sections)/(len(cells)-1))
    return {"passed": bool(steps.max(initial=0.) <= acceptance["maximum_uphill_step_m"] and minimum_relief >= acceptance["minimum_bank_relief_m"]
                           and coverage >= acceptance["minimum_cross_section_coverage_fraction"]),
            "length_m": float((len(cells)-1)*spacing), "maximum_uphill_step_m": float(steps.max(initial=0.)),
            "maximum_absolute_slope": float(np.abs(steps).max(initial=0.)/spacing),
            "minimum_bank_relief_m": minimum_relief, "minimum_water_passage_m3": float(water[cells[:,0],cells[:,1]].min()),
            "actual_cross_sections":sections,"profile_bed_m":values.tolist(),"section_count":len(sections),"cross_section_coverage_fraction":coverage}


def geometry_evidence(arrays, meta):
    acceptance = meta["acceptance"]
    spacing = meta["terrain"]["dx_m"]
    count = acceptance["consecutive_intervals"]
    stages = []
    for index in range(max(0,len(meta["forcing"])-count),len(meta["forcing"])):
        trunk, branches = _path_cells(meta["channel_paths"][index])
        if not trunk and meta["forcing"][index]["water_volume_m3"] == 0.:
            stages.append({"interval":index,"passed":False,"reason":"no water and no worked channel"})
            continue
        if len(branches) != 2:
            raise ValueError("exactly two declared branches required")
        junction = tuple(trunk[-1])
        if any(tuple(branch[0]) != junction for branch in branches):
            raise ValueError("branches do not share actual trunk endpoint")
        if tuple(trunk[0]) != tuple(meta["forcing"][index]["inlet_cell"]):
            raise ValueError("trunk does not start at actual inlet")
        beds, water = arrays["beds_m"][index], arrays["water"][index]
        profiles = [_profile(path,beds,water,spacing,acceptance,meta["channel_width_m"][index],junction) for path in (trunk,*branches)]
        branch_sets = [set(map(tuple,branch[1:])) for branch in branches]
        separated = not (branch_sets[0] & branch_sets[1])
        separation_runs = []
        for branch,other in ((branches[0],branches[1]),(branches[1],branches[0])):
            other_mask = np.zeros(beds.shape,bool)
            for cell in other:
                other_mask[tuple(cell)] = True
            distances = distance_transform_edt(~other_mask,sampling=(spacing,spacing))
            run,longest = 0.,0.
            for a,b in zip(branch[:-1],branch[1:]):
                if min(distances[tuple(a)],distances[tuple(b)]) >= acceptance["minimum_separated_branch_length_m"]-1e-9:
                    run += spacing
                    longest = max(longest,run)
                else:
                    run = 0.
            separation_runs.append(longest)
        start, stop = arrays["edge_offsets"][index:index+2]
        cells, volumes = arrays["edge_cells"][start:stop], arrays["edge_volumes"][start:stop]
        edge_water = {tuple(cell): float(volume[0]) for cell,volume in zip(cells,volumes)}
        supplied = meta["forcing"][index]["water_volume_m3"]
        fractions = []
        path_edges_supported = True
        for branch in branches:
            values = []
            for a,b in zip(branch[:-1],branch[1:]):
                value = edge_water.get((*a,*b),0.)
                values.append(value)
            fractions.append(min(values,default=0.)/supplied if supplied else 0.)
        for a,b in zip(trunk[:-1],trunk[1:]):
            path_edges_supported &= edge_water.get((*a,*b),0.) > 0.
        endpoints_are_ocean = all(arrays["export_mask"][tuple(branch[-1])] for branch in branches)
        junction_outflow = sum(edge_water.get((*junction,*branch[1]),0.) for branch in branches)
        junction_inflow = float(water[junction])
        shared_port = (abs(junction_outflow-junction_inflow) <= 1e-7
                       and all(float(beds[tuple(branch[1])]-beds[junction]) <= acceptance["maximum_uphill_step_m"] for branch in branches)
                       and float(arrays["initial_bed_m"][junction]-beds[junction]) >= acceptance["minimum_bank_relief_m"])
        stage_passed = (all(item["passed"] for item in profiles) and separated and path_edges_supported and endpoints_are_ocean
                        and shared_port
                        and all(length >= acceptance["minimum_separated_branch_length_m"] for length in separation_runs)
                        and all(item["length_m"] >= acceptance["minimum_separated_branch_length_m"] for item in profiles[1:])
                        and all(fraction >= acceptance["minimum_branch_fraction"] for fraction in fractions))
        stages.append({"interval": index, "passed": bool(stage_passed), "junction_cell": list(junction), "profiles": profiles,
                       "branch_fractions": fractions, "spatially_disjoint_branches": separated, "declared_ocean_endpoints": bool(endpoints_are_ocean)})
        stages[-1]["continuous_length_at_minimum_branch_separation_m"] = separation_runs
        stages[-1]["shared_port"] = {"passed":bool(shared_port),"bed_m":float(beds[junction]),"water_in_m3":junction_inflow,"water_out_m3":junction_outflow}
    return {"sourcecut_continuous_distributary_bed": len(stages)==count and all(item["passed"] for item in stages),
            "old_task14_cover_only_gate": False, "stages": stages, "hydraulic_certification": False}


def audit_archive(path, expected_sha256=None):
    if expected_sha256 and file_sha256(path) != expected_sha256:
        raise ValueError("archive hash mismatch")
    with np.load(path,allow_pickle=False) as archive:
        a = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
        meta = json.loads(str(archive["metadata_json"].item()))
    for key,value in a.items():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite saved evidence: "+key)
    initial = a["initial_bed_m"]
    if meta["acceptance"] != ACCEPTANCE:
        raise ValueError("saved acceptance thresholds differ from the declared contract")
    config = meta["core"]["config"]
    area = meta["terrain"]["dx_m"]*meta["terrain"]["dz_m"]
    solid_area = area*(1-config["porosity"])
    rows,columns = initial.shape
    perimeter = np.ones(initial.shape,bool)
    perimeter[1:-1,1:-1] = False
    export = a["export_mask"]
    if not export.any() or np.any(export & ~(perimeter & a["ocean_mask"] & a["valid_mask"])):
        raise ValueError("unsupported ocean export")
    original = a["original_source_bed_m"]
    source = meta["source"]
    if source["kind"] == "saved_TD":
        if file_sha256(source["path"]) != source["sha256"]:
            raise ValueError("immutable TD source identity mismatch")
        r0,r1,c0,c1 = source["crop_rows_columns"]
        factor = source["refinement_factor"]
        with np.load(source["path"],allow_pickle=False) as parent:
            ocean = parent["ocean_mask"][r0:r1,c0:c1]
            for name,key in (("original_source_bed_m","derived_height_m"),("raw_td_m","original_td_m")):
                refined,labels = refine(parent[key][r0:r1,c0:c1],ocean,factor)
                np.testing.assert_array_equal(a[name],refined)
                np.testing.assert_array_equal(a["ocean_mask"],labels)
            parent_meta = json.loads(str(parent["metadata_json"].item()))
            _close([meta["terrain"]["x0_m"],meta["terrain"]["z0_m"]],refined_origin(parent_meta["origin_xz_m"],source["crop_rows_columns"],factor))
        _close([meta["terrain"]["dx_m"],meta["terrain"]["dz_m"]],[30/factor]*2)
    elif source["kind"] != "SYNTHETIC":
        raise ValueError("unknown source category")
    inventory, source_bulk = a["initial_cover_solid_m3"].copy(), np.zeros(initial.shape)
    if np.any(inventory < 0.):
        raise ValueError("negative prepared inventory")
    _close(initial,original+inventory/solid_area)
    if "coordination" in meta:
        preparation = meta["coordination"]
        parameters = preparation["config"]
        pr,pc = preparation["inlet_cell"]
        rr,cc = np.indices(initial.shape)
        radial = np.hypot((rr-pr)*meta["terrain"]["dz_m"],(cc-pc)*meta["terrain"]["dx_m"])
        taper = np.clip(2*(1-radial/parameters["radius_m"]),0,1)
        taper[0,:] = taper[-1,:] = taper[:,0] = taper[:,-1] = 0.
        ocean = a["ocean_mask"] & a["valid_mask"]
        offshore = distance_transform_edt(ocean,sampling=(meta["terrain"]["dz_m"],meta["terrain"]["dx_m"]))
        target = meta["boundary"]["sea_level_m"]-parameters["minimum_submergence_m"]-parameters["slope_m_per_m"]*offshore
        raising = np.where(ocean,np.maximum(0.,target-original)*taper,0.)
        bulk = raising*area
        prepared_solid = bulk*(1-parameters["porosity"])
        _close(bulk,a["fill_bulk_m3"])
        _close(prepared_solid,a["initial_cover_solid_m3"])
        _close(a["coordinated_bed_m"],original+raising)
        _close(initial,a["coordinated_bed_m"])
        ledger = meta["preparation_ledger"]
        if raising.max() > parameters["maximum_raise_m"]+1e-8 or bulk.sum() > parameters["maximum_fill_bulk_m3"]+1e-7 or prepared_solid.sum() > parameters["supplied_solid_m3"]+1e-7:
            raise ValueError("marine preparation budget exceeded")
        for key,value in (("supplied_solid_m3",parameters["supplied_solid_m3"]),("placed_solid_m3",prepared_solid.sum()),
                           ("unplaced_solid_m3",parameters["supplied_solid_m3"]-prepared_solid.sum()),("placed_bulk_m3",bulk.sum()),("residual_solid_m3",0.)):
            _close(ledger[key],value)
    elif np.any(inventory > 0.):
        raise ValueError("initial prepared material lacks independent preparation provenance")
    total_exports, total_unresolved, total_water_out, total_retained = 0.,0.,0.,0.
    for i,forcing in enumerate(meta["forcing"]):
        expected_width = min(config["max_channel_width_m"],config["width_at_reference_water_m"]*np.sqrt(forcing["water_volume_m3"]/config["reference_interval_water_m3"])) if forcing["water_volume_m3"] else 0.
        _close(meta["channel_width_m"][i],expected_width)
        start,stop = a["edge_offsets"][i:i+2]
        cells,volumes = a["edge_cells"][start:stop],a["edge_volumes"][start:stop]
        if np.any(volumes < 0.) or np.any(cells < 0) or np.any(cells[:,(0,2)] >= rows) or np.any(cells[:,(1,3)] >= columns):
            raise ValueError("invalid flow edge")
        if np.any(np.abs(cells[:,:2]-cells[:,2:]).sum(axis=1) != 1):
            raise ValueError("noncardinal flow edge")
        inlet = tuple(forcing["inlet_cell"])
        _check_flow_dag(cells,inlet,forcing["water_volume_m3"],columns,initial.size)
        starting_bed = initial if i == 0 else a["beds_m"][i-1]
        active = a["valid_mask"] & (starting_bed <= meta["boundary"]["river_head_m"])
        if cells.size and (np.any(~active[cells[:,0],cells[:,1]]) or np.any(~active[cells[:,2],cells[:,3]]) or np.any(export[cells[:,0],cells[:,1]])):
            raise ValueError("flow crosses unsupported starting bed or departs ocean export")
        incoming,outgoing = [],[]
        for channel in range(2):
            incoming.append(np.bincount(cells[:,2]*columns+cells[:,3],weights=volumes[:,channel],minlength=initial.size).reshape(initial.shape))
            outgoing.append(np.bincount(cells[:,0]*columns+cells[:,1],weights=volumes[:,channel],minlength=initial.size).reshape(initial.shape))
        incoming[0][inlet] += forcing["water_volume_m3"]
        incoming[1][inlet] += forcing["sediment_solid_m3"]
        _close(incoming[0],a["water"][i])
        _close(incoming[1],a["sediment"][i])
        if cells.size:
            origin = cells[:,0],cells[:,1]
            _close(volumes[:,1]*outgoing[0][origin],volumes[:,0]*outgoing[1][origin])
        deposit,eroded,cut,cut_solid = a["deposits"][i],a["reentrainment"][i],a["source_bulk"][i],a["source_solid"][i]
        if any(np.any(value < 0.) for value in (deposit,eroded,cut,cut_solid)) or np.any(eroded > inventory+1e-7):
            raise ValueError("invalid material inventory")
        if np.any(deposit[(incoming[0] <= 0.) | ~active | export] > 0.) or np.any(deposit > config["max_deposit_depth_per_interval_m"]*solid_area+1e-8):
            raise ValueError("deposition lacks water or exceeds depth budget")
        _close(cut_solid,cut*config["source_solid_fraction"])
        center = np.zeros(initial.shape,bool)
        if forcing["water_volume_m3"] > 0.:
            trunk,branches = _path_cells(meta["channel_paths"][i])
            for path_cells in (trunk,*branches):
                for cell in path_cells:
                    center[tuple(cell)] = True
            supported = distance_transform_edt(~center,sampling=(meta["terrain"]["dz_m"],meta["terrain"]["dx_m"])) < meta["channel_width_m"][i]/2
        else:
            supported = np.zeros(initial.shape,bool)
        if np.any(cut[~supported] > 0.) or np.any(eroded[~supported] > 0.):
            raise ValueError("source/cover work outside actual flowing section support")
        if np.any(cut > area*config["max_source_cut_depth_per_interval_m"]+1e-8):
            raise ValueError("interval source excavation limit exceeded")
        starting_inventory = float(inventory.sum())
        inventory += deposit-eroded
        source_bulk += cut
        _close(inventory,a["storage"][i])
        _close(original-source_bulk/area+inventory/solid_area,a["beds_m"][i])
        if np.any(source_bulk > area*config["max_source_cut_depth_m"]+1e-8) or source_bulk.sum() > config["max_source_eroded_bulk_m3"]+1e-7:
            raise ValueError("cumulative source excavation budget exceeded")
        rests = [incoming[0]-outgoing[0],incoming[1]+cut_solid+eroded-deposit-outgoing[1]]
        if np.any(rests[0] < -1e-7) or np.max(np.abs(rests[0][~export]),initial=0.) > 1e-7:
            raise ValueError("per-cell water conservation failed")
        escrow = a["escrow"][i]
        if np.any(escrow < 0.):
            raise ValueError("negative terminal material escrow")
        material_rest = rests[1]-escrow
        if np.any(material_rest < -1e-7) or np.max(np.abs(material_rest[~export]),initial=0.) > 1e-7:
            raise ValueError("per-cell source/material conservation failed")
        water_out,retained = float(rests[0][export].sum()),float(rests[0][~export].sum())
        solid_out,unresolved = float(material_rest[export].sum()),float(escrow.sum())
        ledgers = meta["interval_ledgers"][i]
        for key,value in (("input_m3",forcing["water_volume_m3"]),("ocean_export_m3",water_out),("retained_m3",retained)):
            _close(ledgers["water"][key],value)
        for key,value in (("input_solid_m3",forcing["sediment_solid_m3"]),("ocean_export_solid_m3",solid_out),
                           ("unresolved_solid_m3",unresolved),("stored_solid_m3",inventory.sum()),
                           ("deposited_solid_m3",deposit.sum()),("reentrained_solid_m3",eroded.sum()),
                           ("source_eroded_bulk_m3",cut.sum()),("source_eroded_solid_m3",cut_solid.sum())):
            _close(ledgers["solid"][key],value)
        _close(ledgers["solid"]["initial_stored_solid_m3"],starting_inventory)
        _close(ledgers["solid"]["residual_solid_m3"],starting_inventory+forcing["sediment_solid_m3"]+cut_solid.sum()-inventory.sum()-solid_out-unresolved)
        _close(ledgers["water"]["residual_m3"],forcing["water_volume_m3"]-water_out-retained)
        total_exports += solid_out
        total_unresolved += unresolved
        total_water_out += water_out
        total_retained += retained
    _close(source_bulk,a["source_eroded_bulk_m3"])
    _close(source_bulk*config["source_solid_fraction"],a["source_eroded_solid_m3"])
    _close(original-source_bulk/area,a["derived_base_bed_m"])
    _close(inventory,a["stored_solid_m3"])
    _close(a["beds_m"][-1],a["final_bed_m"])
    _close(a["final_bed_m"]-initial,a["height_delta_m"])
    _close(a["deposits"].sum(axis=0),a["deposited_solid_m3"])
    _close(a["reentrainment"].sum(axis=0),a["reentrained_solid_m3"])
    _close(a["escrow"].sum(axis=0),a["unresolved_solid_m3"])
    _close(a["initial_cover_solid_m3"].sum()+sum(item["sediment_solid_m3"] for item in meta["forcing"])+a["source_eroded_solid_m3"].sum(),inventory.sum()+total_exports+total_unresolved)
    _close(sum(item["water_volume_m3"] for item in meta["forcing"]),total_water_out+total_retained)
    ledger = meta["solid_ledger"]
    for key,value in (("source_eroded_bulk_m3",source_bulk.sum()),("source_eroded_solid_m3",source_bulk.sum()*config["source_solid_fraction"]),
                       ("stored_solid_m3",inventory.sum()),("ocean_export_solid_m3",total_exports),("unresolved_solid_m3",total_unresolved),
                       ("deposited_solid_m3",a["deposits"].sum()),("reentrained_solid_m3",a["reentrainment"].sum())):
        _close(ledger[key],value)
    _close(ledger["initial_stored_solid_m3"],a["initial_cover_solid_m3"].sum())
    _close(ledger["residual_solid_m3"],0.)
    unplaced = meta.get("preparation_ledger",{}).get("unplaced_solid_m3",0.)
    supplied = meta.get("preparation_ledger",{}).get("supplied_solid_m3",0.)
    external = sum(item["sediment_solid_m3"] for item in meta["forcing"])
    joint_residual = supplied+external+a["source_eroded_solid_m3"].sum()-inventory.sum()-total_exports-total_unresolved-unplaced
    _close(joint_residual,0.)
    return {"passed": True,"geometry":geometry_evidence(a,meta),"source_eroded_bulk_m3":float(source_bulk.sum()),
            "minimum_source_bed_change_m":float((-source_bulk/area).min()),
            "marine_growth":{"gross_river_deposition_solid_m3":float(a["deposits"][:,a["ocean_mask"]].sum()),
                             "final_minus_prepared_cover_solid_m3":float((inventory-a["initial_cover_solid_m3"])[a["ocean_mask"]].sum()),
                             "positive_net_growth_solid_m3":float(np.maximum(0.,inventory-a["initial_cover_solid_m3"])[a["ocean_mask"]].sum()),
                             "positive_net_growth_cell_count":int(np.count_nonzero((inventory-a["initial_cover_solid_m3"])[a["ocean_mask"]] > 1e-7))},
            "joint_material_balance":{"prepared_solid_m3":float(a["initial_cover_solid_m3"].sum()),
                                      "supplied_preparation_solid_m3":supplied,"unplaced_preparation_solid_m3":unplaced,
                                      "external_river_solid_m3":external,"residual_solid_m3":float(joint_residual),
                                      "source_cut_solid_m3":float(a["source_eroded_solid_m3"].sum()),
                                      "end_cover_solid_m3":float(inventory.sum()),"ocean_export_solid_m3":total_exports,"terminal_escrow_solid_m3":total_unresolved}}


def run_trial(output):
    from terrain_pipeline.surface_rivers.metric_fluvial_distributary import FluvialDistributaryConfig, simulate_fluvial_distributary
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    reports = {}
    terrain,boundary,forcing,source,raw = synthetic_input()
    td,td_boundary,_,_,td_source,td_raw = td_input()
    td_source["sediment_origin"] = "explicit external delivery plus separately accounted geometric original-source excavation"
    inlet = (75,51)
    td_forcing = tuple(FluvialDeltaInterval(inlet,200000.,1200. if i<8 else 0.) for i in range(16))
    for name,inputs in (("SYNTHETIC",(terrain,boundary,forcing,source,raw)),("TD",(td,td_boundary,td_forcing,td_source,td_raw))):
        directory = output/name
        directory.mkdir()
        t,b,f,s,r = inputs
        config = FluvialDistributaryConfig()
        declaration = {"source":s,"config":asdict(config),"forcing":[asdict(item) for item in f],"acceptance":ACCEPTANCE,
                       "scope":"finite structure diagnostic; final 96-stage declaration separate"}
        (directory/"declaration.json").write_text(json.dumps(declaration,indent=2),encoding="utf-8")
        try:
            result = simulate_fluvial_distributary(t,b,f,config)
            path = directory/"delta.npz"
            save_archive(path,t,b,f,result,s,r)
            report = {"cold_audit":audit_archive(path),"solid_ledger":result["solid_ledger"],"water_ledger":result["water_ledger"]}
        except ValueError as error:
            report = {"passed":False,"reason":str(error)}
        (directory/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        reports[name] = report
    return reports


def render(path,directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with np.load(path,allow_pickle=False) as archive:
        a = {key:archive[key].copy() for key in archive.files if key != "metadata_json"}
        meta = json.loads(str(archive["metadata_json"].item()))
    spacing = meta["terrain"]["dx_m"]
    fig,axes = plt.subplots(2,3,figsize=(15,9),constrained_layout=True)
    panels = ((a["original_source_bed_m"],"Immutable source bed (m)","terrain"),
              (a["initial_bed_m"],"Declared prepared bed (m)","terrain"),
              (a["final_bed_m"],"Actual final distributary bed (m)","terrain"),
              (a["source_eroded_bulk_m3"]/(spacing**2),"Actual original-source cut depth (m)","magma"),
              ((a["stored_solid_m3"]-a["initial_cover_solid_m3"])/((1-meta["core"]["config"]["porosity"])*spacing**2),"Net cover change after preparation (m)","coolwarm"),
              (np.log10(1+a["water"][-1]),"Actual last-stage water passage log10(1+m3)","viridis"))
    extent = (0,a["final_bed_m"].shape[1]*spacing,a["final_bed_m"].shape[0]*spacing,0)
    for axis,(data,title,cmap) in zip(axes.flat,panels):
        im = axis.imshow(data,extent=extent,cmap=cmap)
        axis.set(title=title,xlabel="local x (m)",ylabel="local z (m)")
        fig.colorbar(im,ax=axis,shrink=.8)
    fig.savefig(directory/"actual-bed-material.png",dpi=140)
    plt.close(fig)
    trunk,branches = _path_cells(meta["channel_paths"][-1])
    centers = np.array(trunk+branches[0]+branches[1])
    r0,r1 = max(0,centers[:,0].min()-8),min(a["final_bed_m"].shape[0],centers[:,0].max()+9)
    c0,c1 = max(0,centers[:,1].min()-4),min(a["final_bed_m"].shape[1],centers[:,1].max()+5)
    fig,axes = plt.subplots(2,1,figsize=(14,7),constrained_layout=True)
    for axis,key,title in ((axes[0],"final_bed_m","Actual final bed; no centerline overlay"),(axes[1],"source_eroded_bulk_m3","Actual source excavation (bulk m3/cell)")):
        im = axis.imshow(a[key][r0:r1,c0:c1],extent=(c0*spacing,c1*spacing,r1*spacing,r0*spacing),cmap="terrain" if key=="final_bed_m" else "magma",aspect="equal")
        axis.set(title=title,xlabel="local x (m)",ylabel="local z (m)")
        fig.colorbar(im,ax=axis,shrink=.8)
    fig.savefig(directory/"mouth-zoom.png",dpi=150)
    plt.close(fig)
    evidence = geometry_evidence(a,meta)["stages"][-1]
    fig,axes = plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
    for column,(name,profile) in enumerate(zip(("Main stem","Branch A","Branch B"),evidence["profiles"])):
        values = profile["profile_bed_m"]
        axes[0,column].plot(np.arange(len(values))*spacing,values)
        axes[0,column].set(title=name+": actual longitudinal profile",xlabel="path distance (m)",ylabel="bed elevation (m)")
        sections = profile["actual_cross_sections"]
        for section in sections[::max(1,len(sections)//5)]:
            axes[1,column].plot([-1,0,1],[section["bank_elevations_m"][0],section["bed_m"],section["bank_elevations_m"][1]],alpha=.7)
        axes[1,column].set(title=name+": actual bed and two banks",xlabel="left bank / bed / right bank",ylabel="elevation (m)")
    fig.savefig(directory/"longitudinal-cross-sections.png",dpi=140)
    plt.close(fig)
    fig,axes = plt.subplots(1,2,figsize=(13,4),constrained_layout=True)
    for key,label in (("source_bulk","original-source excavation"),("deposits","gross deposition"),("reentrainment","cover remobilization"),("escrow","terminal material escrow")):
        axes[0].plot(np.cumsum(a[key].sum(axis=(1,2))),label=label)
    axes[0].set(title="Cumulative material history",xlabel="generation interval (not years)",ylabel="bulk m3 for excavation; solid m3 otherwise")
    axes[0].legend(fontsize=8)
    axes[1].plot(a["storage"].sum(axis=(1,2))-a["initial_cover_solid_m3"].sum(),label="total cover change")
    axes[1].plot(np.cumsum([record["solid"]["ocean_export_solid_m3"] for record in meta["interval_ledgers"]]),label="solid export")
    axes[1].axhline(0,color="gray",linewidth=.7)
    axes[1].set(title="Net cover and delivered sediment",xlabel="generation interval",ylabel="solid m3")
    axes[1].legend(fontsize=8)
    fig.savefig(directory/"material-history.png",dpi=140)
    plt.close(fig)


def compact_evidence(report):
    result = json.loads(json.dumps(report))
    audit = result.get("cold_audit",result)
    for stage in audit.get("geometry",{}).get("stages",[]):
        for profile in stage.get("profiles",[]):
            profile.pop("actual_cross_sections",None)
            profile.pop("profile_bed_m",None)
    return result


def publish(output,reports):
    (output/"report.json").write_text(json.dumps(reports,indent=2),encoding="utf-8")
    html = "<!doctype html><meta charset='utf-8'><title>Distributary actual bed</title><style>body{font:16px sans-serif;margin:24px;color:#222}img{width:100%;max-width:1600px}pre{white-space:pre-wrap}</style><h1>Actual distributary bed</h1><p>Explicit geometric excavation and imported marine preparation. Naturalness and hydraulic certification remain unverified. The previous cover-only gate remains false.</p>"
    for name,report in reports.items():
        html += "<h2>"+name+"</h2>"
        for picture in ("actual-bed-material.png","mouth-zoom.png","longitudinal-cross-sections.png","material-history.png"):
            if (output/name/picture).exists():
                html += "<a href='"+name+"/"+picture+"'><img src='"+name+"/"+picture+"'></a>"
        html += "<pre>"+json.dumps(compact_evidence(report),indent=2)+"</pre>"
    (output/"index.html").write_text(html,encoding="utf-8")


def refresh(output):
    output = Path(output)
    reports = {}
    for directory in sorted(output.iterdir()):
        if not directory.is_dir() or not (directory/"delta.npz").exists():
            continue
        artifact = directory/"delta.npz"
        digest = file_sha256(artifact)
        completed = subprocess.run([sys.executable,str(Path(__file__).resolve()),"--audit",str(artifact),"--expected-sha256",digest],check=True,capture_output=True,text=True)
        report = json.loads((directory/"report.json").read_text(encoding="utf-8"))
        report.update(cold_audit=json.loads(completed.stdout),cold_audit_in_new_process=True,
                      verification_tool_sha256=file_sha256(Path(__file__)))
        audit = report["cold_audit"]
        report["separate_outcomes"] = {"material_and_water_audit_passed":audit["passed"],
            "actual_distributary_bed_passed":audit["geometry"]["sourcecut_continuous_distributary_bed"],
            "local_positive_marine_growth":audit["marine_growth"]["positive_net_growth_solid_m3"] > 0.,
            "whole_marine_cover_net_growth_positive":audit["marine_growth"]["final_minus_prepared_cover_solid_m3"] > 0.,
            "old_cover_only_gate":False,"naturalness_verified":False,"hydraulics_verified":False}
        render(artifact,directory)
        (directory/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        reports[directory.name] = report
    publish(output,reports)
    return {name:compact_evidence(report) for name,report in reports.items()}


def run(output=DEFAULT_OUTPUT):
    from terrain_pipeline.surface_rivers.metric_fluvial_distributary import FluvialDistributaryConfig, prepare_marine_transition, simulate_fluvial_distributary
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    config = FluvialDistributaryConfig(branch_landward_distance_m=15.)
    reports = {}
    for name in ("SYNTHETIC","TD-prepared"):
        directory = output/name
        directory.mkdir()
        if name == "SYNTHETIC":
            terrain,boundary,_,source,raw = synthetic_input()
            inlet = (20,5)
            preparation = None
            sediment = 3000.
        else:
            terrain,boundary,_,_,source,raw = td_input()
            source["sediment_origin"] = "declared external river sediment, separately imported marine preparation cover, and explicit original-source geometric excavation"
            inlet,sediment = (75,51),1200.
            preparation = prepare_marine_transition(terrain,boundary,inlet,**MARINE_PREPARATION)
        forcing = tuple(FluvialDeltaInterval(inlet,200000.,sediment if i<64 else 0.) for i in range(96))
        declaration = {"source":source,"config":asdict(config),"forcing":[asdict(item) for item in forcing],"acceptance":ACCEPTANCE,
                       "marine_preparation":MARINE_PREPARATION if preparation is not None else None,
                       "resource_policy":"2 CPU cores; BelowNormal; one numerical thread"}
        (directory/"declaration.json").write_text(json.dumps(declaration,indent=2),encoding="utf-8")
        try:
            result = simulate_fluvial_distributary(terrain,boundary,forcing,config,
                      initial_cover_solid_m3=preparation["initial_cover_solid_m3"] if preparation is not None else None)
            artifact = directory/"delta.npz"
            save_archive(artifact,terrain,boundary,forcing,result,source,raw,preparation)
            digest = file_sha256(artifact)
            completed = subprocess.run([sys.executable,str(Path(__file__).resolve()),"--audit",str(artifact),"--expected-sha256",digest],check=True,capture_output=True,text=True)
            audit = json.loads(completed.stdout)
            report = {"artifact_sha256":digest,"cold_audit_in_new_process":True,"cold_audit":audit,
                      "source":source,"solid_ledger":result["solid_ledger"],"water_ledger":result["water_ledger"],
                      "preparation_ledger":preparation["preparation_ledger"] if preparation is not None else None,
                      "naturalness_verified":False,"hydraulics_verified":False,"old_task14_cover_only_gate":False}
            render(artifact,directory)
        except ValueError as error:
            report = {"passed":False,"reason":str(error),"source":source}
        (directory/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        reports[name] = report
    publish(output,reports)
    return reports


if __name__ == "__main__":
    resource_limits()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit",type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--trial",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--refresh",type=Path)
    args = parser.parse_args()
    if args.audit:
        print(json.dumps(audit_archive(args.audit,args.expected_sha256),indent=2))
    elif args.trial:
        print(json.dumps(run_trial(args.trial),indent=2))
    elif args.output:
        print(json.dumps({name:compact_evidence(report) for name,report in run(args.output).items()},indent=2))
    elif args.refresh:
        print(json.dumps(refresh(args.refresh),indent=2))
    else:
        parser.error("--audit required")
