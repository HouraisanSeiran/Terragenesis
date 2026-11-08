"""Real seed-world tributary reach across an actual owning-core boundary.

Uses existing coarse world terrain and its actual D8 receiver, not a drawn graph.
The canonical bed is bilinear interpolation of that coarse terrain, not TD detail.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff
from terrain_pipeline.surface_rivers.metric_domain_closure import domain_topology
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import GeometryConfig, build_channel_geometry
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig, receiver_distances
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _sample_nodes
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.world_channel_graph import WorldNode, node_id, assemble_world_graph, assemble_local_forcing, derive_noise_seed
from terrain_pipeline.surface_rivers.world_channel_dynamics import couple_nodal_reach, save_nodal_reach
from tools.run_cross_region_tributary import run


def world_xz(topology, cell):
    row, col = divmod(int(cell), topology["shape"][1])
    return (topology["origin_x_m"] + col * topology["spacing_m"],
            topology["origin_z_m"] + row * topology["spacing_m"])


def cell_at(topology, point):
    col = int(round((point[0] - topology["origin_x_m"]) / topology["spacing_m"]))
    row = int(round((point[1] - topology["origin_z_m"]) / topology["spacing_m"]))
    if not (0 <= row < topology["shape"][0] and 0 <= col < topology["shape"][1]):
        raise ValueError("selected point outside source snapshot")
    return row * topology["shape"][1] + col


def select_real_reach(seed=20261020):
    left = domain_topology(seed, 1270000., 230000.)
    right = domain_topology(seed, 1280000., 230000.)
    span = left["core_cells"] * left["spacing_m"]
    boundary = right["core_origin_x_m"]
    if boundary != left["core_origin_x_m"] + span or right["core_origin_z_m"] != left["core_origin_z_m"]:
        raise ValueError("snapshots must own adjacent cores")
    # Retain a fixed natural receiver junction picked from a source-topology scan.
    junction = cell_at(left, (boundary, 230000.))
    receiver = left["receiver"].ravel()
    donors = np.flatnonzero((receiver == junction) & left["accepted"].ravel())
    if len(donors) != 2 or receiver[junction] < 0:
        raise ValueError("selected actual junction must have two land donors and downstream")
    selected = list(donors) + [junction, int(receiver[junction])]
    points = [world_xz(left, cell) for cell in selected]
    answers = []
    for cell, point in zip(selected, points):
        other = cell_at(right, point)
        downstream = int(receiver[cell])
        other_downstream = int(right["receiver"].ravel()[other])
        a = None if downstream < 0 else world_xz(left, downstream)
        b = None if other_downstream < 0 else world_xz(right, other_downstream)
        term_a = world_xz(left, left["terminal"].ravel()[cell])
        term_b = world_xz(right, right["terminal"].ravel()[other])
        same = a == b and term_a == term_b and left["height_m"].ravel()[cell] == right["height_m"].ravel()[other]
        answers.append(dict(point_m=point, left_receiver_m=a, right_receiver_m=b,
                            left_terminal_m=term_a, right_terminal_m=term_b,
                            identical=bool(same)))
    if not all(item["identical"] for item in answers):
        raise ValueError("adjacent owner snapshots disagree: " + json.dumps(answers))
    records = [WorldNode(seed, *p, node_id(seed, *world_xz(left, receiver[cell]))
                         if receiver[cell] in selected else None)
               for cell, p in zip(selected, points)]
    graph = assemble_world_graph(records, span)
    boundary_edges = []
    for cell in selected:
        for donor in np.flatnonzero(receiver == cell):
            if donor not in selected:
                boundary_edges.append(dict(from_xz_m=world_xz(left, donor),
                    to_xz_m=world_xz(left, cell), source="declared_upstream_boundary_scenario_not_zero_or_full_basin"))
    return graph, left, right, selected, answers, boundary_edges


def make_real_scene(output):
    output = Path(output)
    graph, left, right, selected, answers, upstream = select_real_reach()
    points = graph["node_xz_m"]
    shape = left["shape"]
    ids = np.array([cell_at(left, p) for p in points], np.int64)
    rows, cols = ids // shape[1], ids % shape[1]
    r0, r1 = int(rows.min()-1), int(rows.max()+2)
    c0, c1 = int(cols.min()-1), int(cols.max()+2)
    source = left["height_m"][r0:r1, c0:c1].copy()
    x0 = left["origin_x_m"] + c0 * left["spacing_m"]
    z0 = left["origin_z_m"] + r0 * left["spacing_m"]
    source_id = hashlib.sha256(source.tobytes() + json.dumps([x0,z0,left["spacing_m"]]).encode()).hexdigest()
    terrain = TerrainGrid(source, np.ones(source.shape, bool), x0, z0,
        left["spacing_m"], left["spacing_m"], "generated_terrain",
        "seed20261020_actual_coarse_condition_field_bilinear_interpolation_not_TD_detail", source_id)
    local_ids = np.array([(r-r0)*source.shape[1]+c-c0 for r,c in zip(rows,cols)], np.int64)
    n = len(local_ids)
    widths = np.full(n, 800.)
    confluence = np.bincount(graph["receiver"][graph["receiver"]>=0], minlength=n)>=2
    widths[confluence] = 400.
    for name, topo in (("left",left),("right",right)):
        np.savez_compressed(output/("source-owner-"+name+".npz"),
            **{k: v for k,v in topo.items() if isinstance(v,np.ndarray)},
            origin_xz_m=[topo["origin_x_m"],topo["origin_z_m"]],
            core_origin_xz_m=[topo["core_origin_x_m"],topo["core_origin_z_m"]],
            spacing_m=topo["spacing_m"], core_cells=topo["core_cells"], margin=topo["margin"])
    geometry = build_channel_geometry(terrain, local_ids, graph["receiver"].copy(), widths,
        np.full(n, .4), owner_grid=np.ones(source.shape,np.int64),
        corridor_mask=np.ones(source.shape,bool), lake_mask=np.zeros(source.shape,bool),
        anchor_mask=np.ones(n,bool), config=GeometryConfig(fine_spacing_m=100.,smoothing_iterations=0))
    a = geometry["arrays"]
    np.testing.assert_array_equal(a["node_source_elevation_m"], left["height_m"].ravel()[ids])
    bed = _sample_nodes(geometry, a["bed_elevation_m"])
    distance = receiver_distances(a["node_xz_m"],graph["receiver"])
    lengths = np.zeros(n)
    for i,j in enumerate(graph["receiver"]):
        if j>=0:
            lengths[i] += distance[i]/2
            lengths[j] += distance[i]/2
    slope = np.zeros(n)
    for i,j in enumerate(graph["receiver"]):
        if j>=0:
            slope[i] = (bed[i]-bed[j])/distance[i]
    outlet = int(np.flatnonzero(graph["receiver"]<0)[0])
    slope[outlet] = slope[np.flatnonzero(graph["receiver"]==outlet)[0]]
    network = ChannelNetwork(graph["receiver"].copy(),lengths,widths,bed,slope,
        np.full(n,.035),np.full(n,3.), np.where(graph["receiver"]>=0,"interior","open_outflow"),
        geometry["identity_sha256"],"actual world receiver, bilinear coarse bed cut, half-incident lengths",
        "explicit uncalibrated n=.035",distance)
    times = np.arange(0.,43201.,3600.)
    rainfall = np.array([4.,6.,8.,8.,6.,4.,2.,1.,0.,0.,0.,0.])
    runoff_parameters = RunoffParameters(infiltration_capacity_mm_h=2.)
    runoff = simulate_rainfall_runoff(np.broadcast_to(rainfall[:,None],(12,n)).copy(),
        np.full(n,left["spacing_m"]**2),dt_s=3600.,source_id=source_id,parameters=runoff_parameters)
    sources = [("local-cell:"+key,key,runoff["local_q_m3_s"][:,i]) for i,key in enumerate(graph["node_ids"])]
    # Explicit upstream boundary hydrograph per omitted donor edge; these catchments
    # are outside selected cell footprints. No claim of complete upstream generation.
    pulse = rainfall/8.
    for edge in upstream:
        edge["q_m3_s"] = (pulse*10.).tolist()
        edge_id = node_id(20261020,*edge["from_xz_m"])+"->"+node_id(20261020,*edge["to_xz_m"])
        sources.append(("boundary:"+edge_id,node_id(20261020,*edge["to_xz_m"]),pulse*10.))
    local = assemble_local_forcing(graph,times,sources)
    forcing = ChannelForcing(times,local,graph["identity_sha256"])
    graph["scene"] = "actual_seed20261020_coarse_world_reach_bilinear_bed_not_TD_detail"
    graph["material_area_m2"] = network.width_m * network.length_m
    graph["existing_algorithms"] = ["build_channel_geometry", "solve_channel", "solve_sediment", "bed_from_inventory"]
    graph["forcing_components"] = dict(local_bucket_input_m3=float(runoff["outflow_volume_m3"].sum()),
        prescribed_clipped_upstream_boundary_input_m3=float((local-runoff["local_q_m3_s"]).sum()*3600.),
        interpretation="water.local_input_m3 is combined solver source, not local rainfall alone")
    graph["limitations"] = ["finite_selected_reach_not_complete_upstream_basin",
        "explicit_nonzero_upstream_boundary_scenario", "coarse_10km_field_interpolated_not_TD_detail",
        "explicit_uncalibrated_width_roughness_material", "global_synchronous_not_partitioned_scheduler",
        "no_lake_backwater_or_2D_floodplain"]
    seed_policy = dict(world_seed=20261020, derivation="sha256 JSON[terragenesis-world-noise-v1,world_seed,purpose] first32bits bigendian",
        reserved_noise_seeds={purpose:derive_noise_seed(20261020,purpose) for purpose in ("climate","rainfall","light")},
        active_noise_generators=[],rainfall_mode="fixed_explicit_12_hour_scenario_not_noise_generated",
        boundary_mode="fixed_explicit_upstream_hydrograph_not_noise_generated",
        future_noise_coordinates="absolute world x/z and explicit simulation time index, never loading order")
    graph["seed_policy"] = seed_policy
    source_report = dict(seed=20261020,seed_policy=seed_policy,source_module="metric_domain_closure.domain_topology / coarse_condition_field",
        source_terrain_sha256=source_id,config=asdict(PlanningConfig()),
        left_core_origin_m=[left["core_origin_x_m"],left["core_origin_z_m"]],
        right_core_origin_m=[right["core_origin_x_m"],right["core_origin_z_m"]],
        core_span_m=left["core_cells"]*left["spacing_m"],actual_boundary_x_m=right["core_origin_x_m"],
        node_xz_m=points.tolist(),original_receiver_flat_ids=left["receiver"].ravel()[ids].tolist(),
        original_node_height_m=left["height_m"].ravel()[ids].tolist(),
        adjacent_owner_answers=answers,clipped_upstream_boundary_edges=upstream,
        local_cell_area_m2=float(left["spacing_m"]**2),local_cells=ids.tolist(),
        local_water_volume_m3=float(runoff["outflow_volume_m3"].sum()),
        upstream_boundary_water_volume_m3=float((local-runoff["local_q_m3_s"]).sum()*3600.),
        runoff_parameters=asdict(runoff_parameters),rainfall_mm_h=rainfall.tolist(),
        coarse_terrain_spacing_m=left["spacing_m"],canonical_PL_spacing_m=100.,
        original_receiver_of_cut_outlet_xz_m=world_xz(left,left["receiver"].ravel()[ids[outlet]]),
        cut_outlet_policy="finite_reach_open_outflow_not_a_natural_river_mouth",
        water_source_separation="selected cell buckets plus distinct omitted-upstream edge scenario; no repeated cell area")
    (output/"source-selection.json").write_text(json.dumps(source_report,indent=2),encoding="utf-8")
    np.savez_compressed(output/"source-terrain-and-forcing.npz",height_m=source,origin_xz_m=[x0,z0],
        node_cell_ids=local_ids,original_tile_cell_ids=ids,raw_node_height_m=left["height_m"].ravel()[ids],
        raw_receiver=left["receiver"].ravel()[ids],time_seconds=times,
        local_bucket_q_m3_s=runoff["local_q_m3_s"],boundary_q_m3_s=local-runoff["local_q_m3_s"],
        **{"runoff_"+k:v for k,v in runoff.items() if isinstance(v,np.ndarray)})
    return graph, geometry, network, forcing


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True)
    args=parser.parse_args()
    run(args.output,scene_builder=make_real_scene,
        material=MaterialParameters(sediment_erodibility_m_s_pa=1e-10,
            rock_erodibility_m_s_pa=1e-12,transport_coefficient=1e-5,
            settling_velocity_m_s=.0001,provenance="explicit real coarse reach illustrative material"),
        channel_config=ChannelConfig(max_dt_seconds=30.),
        sediment_config=SedimentConfig(max_dt_seconds=30.,max_bed_change_m=.01),
        dynamics=couple_nodal_reach, saver=save_nodal_reach)
