"""Finite world-reach orchestration of existing water and sediment solvers.

Uses explicit rectangular control areas for material inventories. The canonical
initial carved mesh is not remapped: dynamic geometry is the nodal bed/section.
"""
from dataclasses import asdict
import hashlib

import numpy as np

from terrain_pipeline.common_infra import identity, readonly, save_bundle
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product
from terrain_pipeline.surface_rivers.metric_sediment import SedimentDomain, SedimentForcing, solve_sediment
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _pack


def couple_nodal_reach(geometry, network, forcing, material, *, initial_water_volume_m3,
                       initial_mobile_solid_m3, initial_alluvium_bulk_m3, rock_floor_m,
                       config, channel_config, sediment_config):
    """Solve water, replay its actual trace through old sediment, advance nodal bed.

    No replacement transport equations are used. Material area is deliberately the
    disjoint rectangular water control area, not the old PL mesh's nearest basis.
    """
    limit = getattr(config, "max_nodes", 16)
    if len(network.receiver) > limit or len(forcing.time_seconds)-1 > config.max_intervals:
        raise ValueError("small finite reach required")
    if network.source_identity_sha256 != geometry["identity_sha256"]:
        raise ValueError("initial carved geometry and channel identity differ")
    if not np.array_equal(network.receiver, geometry["arrays"]["receiver"]):
        raise ValueError("initial carved geometry receiver differs")
    n = len(network.receiver)
    area = network.width_m * network.length_m
    bed = network.bed_elevation_m.copy()
    original = bed.copy()
    water = initial_water_volume_m3.copy()
    mobile = initial_mobile_solid_m3.copy()
    loose = initial_alluvium_bulk_m3 * (1-material.porosity)
    rock_removed = np.zeros(n)
    arrays = {}
    meta = dict(schema="world-nodal-water-sediment-bed-v1", algorithm="existing-manning-sediment-nodal-recoupling-v1",
        status="complete", intervals=[], material=asdict(material),
        geometry_identity_sha256=geometry["identity_sha256"],
        material_area_semantics="width_times_half_incident_storage_control_length",
        dynamic_PL_mesh_updated=False, initial_carved_mesh_only=True,
        hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    _pack(arrays,meta,"geometry",geometry)
    states = {"node_bed_m":[bed.copy()],"water_volume_m3":[water.copy()],
              "mobile_solid_m3":[mobile.copy()],"loose_solid_m3":[loose.copy()],
              "rock_removed_m3":[rock_removed.copy()]}
    times = [float(forcing.time_seconds[0])]
    for interval,(start,end) in enumerate(zip(forcing.time_seconds[:-1],forcing.time_seconds[1:])):
        slopes=network.bed_slope.copy()
        edges=network.receiver>=0
        slopes[edges]=(bed[edges]-bed[network.receiver[edges]])/network.receiver_distance_m[edges]
        gid=hashlib.sha256(geometry["identity_sha256"].encode()+bed.tobytes()).hexdigest()
        current=ChannelNetwork(network.receiver.copy(),network.length_m.copy(),network.width_m.copy(),
            bed.copy(),slopes,network.roughness.copy(),network.max_depth_m.copy(),network.terminal_kind.copy(),
            gid,"actual coarse-world carved nodal bed plus inventory updates",network.roughness_source,
            network.receiver_distance_m.copy())
        drive=ChannelForcing(np.array([start,end],np.float64),forcing.local_q_m3_s[interval:interval+1].copy(),
                             forcing.source_identity_sha256)
        wt=solve_channel(current,drive,water,channel_config)
        if wt["metadata"]["status"]!="complete":
            raise ValueError("existing water solver: "+str(wt["metadata"]["failure_reason"]))
        wp=make_channel_product(current,drive,wt)
        wa=wt["arrays"]
        sf=SedimentForcing(wa["time_seconds"].copy(),wa["volume_m3"][:-1].copy(),wa["depth_m"][:-1].copy(),
            wa["outflow_q_m3_s"].copy(),np.broadcast_to(slopes,wa["outflow_q_m3_s"].shape).copy(),
            np.zeros_like(wa["outflow_q_m3_s"]),wp["identity_sha256"],gid,"exact newly solved existing Manning trace")
        sd=SedimentDomain(network.receiver.copy(),area.copy(),network.width_m.copy(),bed.copy(),rock_floor_m.copy(),
            (loose/(1-material.porosity)).copy(),np.zeros(n,bool),network.terminal_kind=="open_outflow",gid,
            "explicit nodal rectangular material control volumes; initial PL mesh is not dynamically remapped")
        sp=solve_sediment(sd,sf,material,mobile,sediment_config)
        if sp["metadata"]["status"]!="complete":
            raise ValueError("existing sediment solver: "+str(sp["metadata"]["failure_reason"]))
        sa=sp["arrays"]
        next_bed=sa["trace_bed_elevation_m"][-1].copy()
        if np.max(np.abs(next_bed-original)) > config.max_cumulative_bed_change_m:
            raise ValueError("cumulative nodal bed limit exceeded")
        if np.max(np.abs(next_bed-bed)) > config.max_depth_change_m:
            raise ValueError("fixed-volume stage shift exceeds nodal coupling bound")
        if np.any(next_bed[edges] <= next_bed[network.receiver[edges]]):
            raise ValueError("updated nodal bed reverses original receiver")
        _pack(arrays,meta,"water_"+str(interval),wp)
        _pack(arrays,meta,"sediment_"+str(interval),sp)
        meta["intervals"].append(dict(start_seconds=float(start),end_seconds=float(end),geometry_identity_sha256=gid))
        water=wa["volume_m3"][-1].copy()
        mobile=sa["trace_mobile_solid_m3"][-1].copy()
        loose=sa["trace_bed_alluvium_solid_m3"][-1].copy()
        rock_removed+=sa["trace_rock_removed_m3"][-1]
        bed=next_bed
        for key,value in (("node_bed_m",bed),("water_volume_m3",water),("mobile_solid_m3",mobile),
                          ("loose_solid_m3",loose),("rock_removed_m3",rock_removed)):
            states[key].append(value.copy())
        times.append(float(end))
    arrays.update({key:readonly(np.array(values)) for key,values in states.items()})
    arrays["time_seconds"]=readonly(np.array(times,np.float64))
    arrays["material_area_m2"]=readonly(area)
    result=dict(arrays=arrays,metadata=meta,identity_sha256=identity(arrays,meta))
    return result


def save_nodal_reach(path,result):
    def check(record):
        if record["metadata"].get("schema")!="world-nodal-water-sediment-bed-v1":
            raise ValueError("nodal reach schema required")
        if identity(record["arrays"],record["metadata"])!=record["identity_sha256"]:
            raise ValueError("nodal reach identity mismatch")
    save_bundle(path,result,validator=check)
