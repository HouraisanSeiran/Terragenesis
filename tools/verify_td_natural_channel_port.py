"""Pinned TD256 natural six-pool domain and disjoint M5 channel port replay."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.integrate import solve_ivp
from scipy.ndimage import label

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.channel_geometry import GeometryConfig, build_channel_geometry, save_channel_geometry
from terrain_pipeline.channel_geometry import ChannelNetwork
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.lake import LakeChannelConfig as LakeChannelConfig
from terrain_pipeline.lake import LakeChannelForcing as LakeChannelForcing
from terrain_pipeline.lake import LakeChannelPort as LakeChannelPort
from terrain_pipeline.lake import load_lake_channel as load_lake_channel
from terrain_pipeline.lake import save_lake_channel as save_lake_channel
from terrain_pipeline.lake import solve_lake_channel as solve_lake_channel
from terrain_pipeline.lake import build_natural_lakes as build_natural_lakes
from terrain_pipeline.lake import load_natural_lakes as load_natural_lakes
from terrain_pipeline.lake import save_natural_lakes as save_natural_lakes
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from tools.verify_td_natural_lake_extension import TD_PATH, TD_SHA, TD_ID
from tools.verify_td_river_geometry import mesh_evidence
from tools.verify_td_river_sediment import sample_saved_mesh


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "verification/td-natural-lake-extension/td256-20261008-04"


def volume_stage(sorted_bed, cell_area, volume):
    """Independent exact prism inverse via sorted threshold prefix sums."""
    cumulative = np.cumsum(sorted_bed)
    counts = np.arange(1, len(sorted_bed)+1)
    candidates = (volume/cell_area+cumulative)/counts
    next_bed = np.r_[sorted_bed[1:], np.inf]
    hit = np.flatnonzero(candidates <= next_bed)
    return float(candidates[hit[0]])


def rates(domain, network, port, drive, interval, volumes):
    d = domain["arrays"]
    owner, bed = d["owner_grid"].ravel(), d["source_height_m"].ravel()
    nc = len(network.receiver)
    channel, lake = np.maximum(volumes[:nc],0.), np.maximum(volumes[nc:],0.)
    cell_area = domain["metadata"]["terrain_metadata"]["dx_m"] * domain["metadata"]["terrain_metadata"]["dz_m"]
    stage = np.array([volume_stage(np.sort(bed[owner==i]),cell_area,v) for i,v in enumerate(lake)])
    depth = channel/(network.width_m*network.length_m)
    radius = network.width_m*depth/(network.width_m+2.*depth)
    q = network.width_m*depth*radius**(2./3.)*np.sqrt(network.bed_slope)/network.roughness
    q[port.channel_node_index] = 0.
    dc = drive.channel_local_q_m3_s[interval].copy()-q
    dl = drive.lake_local_q_m3_s[interval].copy()
    for i,j in enumerate(network.receiver):
        if j>=0: dc[j]+=q[i]
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    internal = []
    for first,second in d["internal_faces"]:
        i,j = owner[first],owner[second]
        high,low = max(stage[i],stage[j]),min(stage[i],stage[j])
        flux = coefficient*max(high-max(bed[first],bed[second],low),0.)**1.5*np.sign(stage[i]-stage[j])
        dl[i]-=flux
        dl[j]+=flux
        internal.append(flux)
    boundary = []
    for e,(first,second) in enumerate(d["boundary_faces"]):
        flux = 0.
        if e != port.boundary_face_index:
            i = owner[first]
            crest = bed[first] if second<0 else max(bed[first],bed[second])
            if d["boundary_kinds"][e] == "free_outflow":
                flux = coefficient*max(stage[i]-crest,0.)**1.5
            elif d["boundary_kinds"][e] == "tailwater":
                tail = drive.tailwater_stage_m[interval,e]
                flux = coefficient*max(max(stage[i],tail)-max(crest,min(stage[i],tail)),0.)**1.5*np.sign(stage[i]-tail)
            dl[i]-=flux
        boundary.append(flux)
    first,second = d["boundary_faces"][port.boundary_face_index]
    pool = owner[first]
    cstage = network.bed_elevation_m[port.channel_node_index]+depth[port.channel_node_index]
    flux = port.coefficient_m3_s_m15*max(max(cstage,stage[pool])-max(bed[first],bed[second],min(cstage,stage[pool])),0.)**1.5*np.sign(cstage-stage[pool])
    dc[port.channel_node_index]-=flux
    dl[pool]+=flux
    return np.r_[dc,dl],np.asarray(internal),np.asarray(boundary),flux


def cold_evidence(domain, network, port, drive, result):
    a,d = result["arrays"],domain["arrays"]
    owner,bed = d["owner_grid"].ravel(),d["source_height_m"].ravel()
    support = d["support_cell_ids"]
    nl = len(d["seed_cell_ids"])
    cell_area = domain["metadata"]["terrain_metadata"]["dx_m"]*domain["metadata"]["terrain_metadata"]["dz_m"]
    initial = np.r_[a["initial_channel_volume_m3"],a["initial_lake_volume_m3"]]
    volume = np.concatenate((a["trace_channel_volume_m3"],a["trace_lake_volume_m3"]),axis=1)
    max_residual = 0.
    for k,t in enumerate(a["trace_time_seconds"]):
        stage = a["trace_lake_stage_m"][k]
        actual_volume = np.array([cell_area*np.maximum(stage[i]-bed[owner==i],0.).sum() for i in range(nl)])
        np.testing.assert_allclose(actual_volume,a["trace_lake_volume_m3"][k],rtol=1e-9,atol=1e-7)
        wet = (owner>=0)&(bed<stage[np.maximum(owner,0)])
        np.testing.assert_array_equal(wet[support],a["trace_wet_support"][k])
        labels,_ = label(wet.reshape(d["owner_grid"].shape))
        at_seed = labels.ravel()[d["seed_cell_ids"]]
        for i in range(nl):
            for j in range(i+1,nl):
                connected = at_seed[i]>0 and at_seed[i]==at_seed[j]
                if connected != (a["trace_wet_component"][k,i]==a["trace_wet_component"][k,j]):
                    raise AssertionError("independent natural wet connectivity")
        if k<len(a["step_dt_seconds"]):
            interval = np.searchsorted(drive.time_seconds,t,side="right")-1
            derivative,internal,boundary,flux = rates(domain,network,port,drive,interval,volume[k])
            dt = a["step_dt_seconds"][k]
            np.testing.assert_allclose(a["step_lake_internal_q_m3_s"][k],internal,rtol=1e-10,atol=1e-9)
            np.testing.assert_allclose(a["step_boundary_q_m3_s"][k],boundary,rtol=1e-10,atol=1e-9)
            np.testing.assert_allclose(a["step_port_q_m3_s"][k,0],flux,rtol=1e-10,atol=1e-9)
            residual = float(np.max(np.abs(volume[k+1]-volume[k]-dt*derivative)))
            max_residual = max(max_residual,residual)
            np.testing.assert_allclose(volume[k+1],volume[k]+dt*derivative,rtol=1e-10,atol=1e-8)
    dt = a["step_dt_seconds"]
    local_input = 0.
    for start,end,cq,lq in zip(drive.time_seconds[:-1],drive.time_seconds[1:],drive.channel_local_q_m3_s,drive.lake_local_q_m3_s):
        local_input+=(end-start)*(cq.sum()+lq.sum())
    external = float(np.sum(dt[:,None]*a["step_boundary_q_m3_s"]))
    residual = float(initial.sum()+local_input-external-volume[-1].sum())
    np.testing.assert_allclose(residual,0.,rtol=0.,atol=1e-7)
    return dict(status=result["metadata"]["status"],steps=len(dt),max_node_residual_m3=max_residual,
        global_residual_m3=residual,local_input_m3=float(local_input),external_outflow_m3=external,
        net_channel_to_lake_m3=float(np.dot(dt,a["step_port_q_m3_s"][:,0])),
        final_stage_m=a["trace_lake_stage_m"][-1].tolist(),final_channel_volume_m3=a["trace_channel_volume_m3"][-1].tolist())


def verify(output):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    parent=json.loads((PARENT/"acceptance.json").read_text())
    pin=parent["artifacts"]["td-domain"]
    old=load_natural_lakes(PARENT/pin["path"],expected_sha256=pin["sha256"],expected_identity=pin["identity_sha256"])
    da=old["arrays"]
    terrain=TerrainGrid(da["source_height_m"],da["source_valid_mask"],**old["metadata"]["terrain_metadata"])
    faces=np.vstack((da["boundary_faces"],np.array([[62396,62140]],np.int64)))
    kinds=np.concatenate((da["boundary_kinds"],np.array(["tailwater"])))
    domain=build_natural_lakes(terrain,da["seed_cell_ids"].copy(),da["owner_grid"].copy(),
        max_stage_m=da["max_stage_m"].copy(),boundary_faces=faces,boundary_kinds=kinds,
        weir_coefficient_m3_s_m15=old["metadata"]["weir_coefficient_m3_s_m15"],
        source_provenance="pinned TD256 six frozen D4 owners; unchanged source",
        boundary_provenance="original D4 face 62396/62140 internal to explicit M5 channel port; other exterior unresolved")
    ids=np.array([61884,62140],np.int64)
    rec=np.array([1,-1],np.int64)
    products=[]
    for spacing in (.5,.25):
        products.append(build_channel_geometry(terrain,ids,rec,np.full(2,6.),np.full(2,.25),
            owner_grid=np.zeros(da["owner_grid"].shape,np.int64),corridor_mask=np.ones(da["owner_grid"].shape,bool),
            lake_mask=da["owner_grid"]>=0,anchor_mask=np.ones(2,bool),
            config=GeometryConfig(fine_spacing_m=spacing,smoothing_iterations=0)))
    volumes=[mesh_evidence(g)["represented_cut_volume_m3"] for g in products]
    spatial=abs(volumes[0]-volumes[1])/volumes[1]
    if spatial>.02: raise AssertionError(("port geometry refinement",spatial))
    geometry=products[-1]
    bed=sample_saved_mesh(geometry,geometry["arrays"]["node_xz_m"])
    lengths=np.full(2,15.)
    network=ChannelNetwork(rec,lengths,np.full(2,6.),bed,np.full(2,(bed[0]-bed[1])/30.),
        np.full(2,.035),np.full(2,2.),np.array(["interior","open_outflow"]),
        geometry["identity_sha256"],"M5 PL bed; disjoint half incident controls","explicit uncalibrated n=.035",
        receiver_distance_m=np.array([30., 0.]))
    port=LakeChannelPort(len(faces)-1,1,10.,"explicit uncalibrated finite conductance on native D4 crest")
    source=load_diagnostic_product(TD_PATH,expected_sha256=TD_SHA,expected_identity=TD_ID)
    sa=source["arrays"]
    times=sa["time_seconds"].copy()
    local=sa["local_q_m3_s"].reshape(len(times)-1,-1)
    lake_local=np.column_stack([local[:,da["owner_grid"].ravel()==i].sum(axis=1) for i in range(len(da["seed_cell_ids"]))])
    drive=LakeChannelForcing(times,local[:,ids].copy(),lake_local,np.zeros((len(times)-1,len(faces))),terrain.identity_sha256,
        "original local sources once; lake support and channel source cells disjoint; source product "+TD_ID)
    initial_channel=network.width_m*network.length_m*np.array([.02,1.5])
    cell_area=terrain.cell_area_m2
    initial_lake=np.array([cell_area*np.maximum(1347.-terrain.elevation_m[da["owner_grid"]==i],0.).sum() for i in range(len(da["seed_cell_ids"]))])
    artifacts,cases,runs={},{},[]
    for name,step in (("coarse",.5),("fine",.125)):
        result=solve_lake_channel(domain,geometry,network,(port,),drive,initial_channel,initial_lake,
            LakeChannelConfig(max_dt_seconds=step,max_steps=20000))
        path=output/(name+".npz")
        save_lake_channel(path,result)
        artifacts[name]=dict(path=path.name,sha256=file_sha256(path),identity_sha256=result["identity_sha256"])
        with patch('terrain_pipeline.lake.solve_lake_channel',side_effect=AssertionError("cold solve")), \
             patch('terrain_pipeline.lake.solve_natural_lakes',side_effect=AssertionError("cold lake")):
            cold=load_lake_channel(path,expected_sha256=artifacts[name]["sha256"])
            cases[name]=cold_evidence(domain,network,port,drive,cold)
        if result["metadata"]["status"]!="complete": raise AssertionError(result["metadata"]["failure_reason"])
        runs.append(result)
        print(json.dumps({"case":name,**cases[name]}),flush=True)
    stage_difference=float(np.max(np.abs(runs[0]["arrays"]["trace_lake_stage_m"][-1]-runs[1]["arrays"]["trace_lake_stage_m"][-1])))
    port_difference=abs(cases["coarse"]["net_channel_to_lake_m3"]-cases["fine"]["net_channel_to_lake_m3"])/max(abs(cases["fine"]["net_channel_to_lake_m3"]),1e-12)
    if stage_difference>.001 or port_difference>.01: raise AssertionError(("coupled time refinement",stage_difference,port_difference))
    state=np.r_[initial_channel,initial_lake]
    for interval,(start,end) in enumerate(zip(times[:-1],times[1:])):
        reference=solve_ivp(lambda t,y:rates(domain,network,port,drive,interval,y)[0],(start,end),state,method="Radau",
            rtol=2e-10,atol=1e-9,max_step=1.)
        if not reference.success:raise AssertionError(reference.message)
        state=reference.y[:,-1]
    observed=np.r_[runs[-1]["arrays"]["trace_channel_volume_m3"][-1],runs[-1]["arrays"]["trace_lake_volume_m3"][-1]]
    errors=np.abs(observed-state)
    scale=np.maximum(np.maximum(np.abs(state),np.r_[initial_channel,initial_lake]),1.)
    relative=float(np.max(errors/scale))
    if relative>.005: raise AssertionError(("independent Radau",relative))
    for name,product,save in (("domain",domain,save_natural_lakes),("geometry-coarse",products[0],save_channel_geometry),("geometry-fine",geometry,save_channel_geometry)):
        path=output/(name+".npz")
        save(path,product)
        artifacts[name]=dict(path=path.name,sha256=file_sha256(path),identity_sha256=product["identity_sha256"])
    report=dict(status="accepted_bounded_TD_natural_channel_port",cases=cases,artifacts=artifacts,
        original_source=dict(path=str(TD_PATH),sha256=TD_SHA,identity_sha256=TD_ID),
        parent_natural_domain=pin,port_original_cells=[62396,62140],channel_original_cells=ids.tolist(),
        source_assignments_disjoint=True,spatial_volume_refinement_relative=spatial,
        stage_refinement_m=stage_difference,port_transfer_refinement_relative=port_difference,independent_Radau_relative_error=relative,
        initial_inventory_policy="explicit near-saddle pools and 1.5m terminal-channel stock to exercise native crest; not generated rainfall stock",
        limitations=["finite_level_pool_signed_weir_not_Saint_Venant","TD256_6pools_30m_channel_not_TD1024_global_lakes", "unclassified_exterior_stops_at_native_crest"],
        hydraulic_ready=False,natural_outlet_verified=False,publishable=False)
    publish_bytes(output/"acceptance.json",json.dumps(report,indent=2,allow_nan=False).encode())
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    print(json.dumps(verify(parser.parse_args().output)["status"]))
