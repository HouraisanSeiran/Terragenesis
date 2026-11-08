"""Run an explicit two-region trunk/tributary using existing geometry/water/sediment."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import GeometryConfig, build_channel_geometry, save_channel_geometry
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig, receiver_distances
from terrain_pipeline.surface_rivers.metric_morphology_coupling import (
    MorphologyConfig, couple_morphology, save_morphology_coupling, _basis, _sample_nodes, _unpack)
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.world_channel_graph import (
    WorldNode, node_id, assemble_world_graph, assemble_local_forcing, regional_exchange)


def make_scene():
    seed = 20261022
    # Two 200m regions, shared trunk crosses x=200m; branch joins downstream at x=240m.
    points = [(40., 80.), (80., 80.), (120., 80.), (160., 80.), (200., 80.),
              (240., 80.), (280., 80.), (320., 80.), (360., 80.),
              (120., 160.), (160., 160.), (200., 120.)]
    downstream = [1, 2, 3, 4, 5, 6, 7, 8, -1, 10, 11, 5]
    records = [WorldNode(seed, *p, None if j < 0 else node_id(seed, *points[j]))
               for p, j in zip(points, downstream)]
    # Simulate overlapping source pages deliberately: copies never create extra nodes.
    graph = assemble_world_graph(records + records[3:6], 200.)
    rows, cols = np.mgrid[:11, :21]
    height = 100. - .01 * cols * 20. + .001 * rows * 20.
    terrain = TerrainGrid(height.astype(np.float64), np.ones(height.shape, bool),
                          0., 0., 20., 20., "generated_terrain",
                          "explicit_analytical_trunk_tributary_plane", "a" * 64)
    xy = graph["node_xz_m"]
    ids = ((xy[:, 1] / 20).astype(np.int64) * height.shape[1] + (xy[:, 0] / 20).astype(np.int64))
    widths = np.full(len(ids), 12.)
    # Explicit narrower junction section avoids overlapping half-incident
    # hydraulic controls exceeding the disjoint PL material footprint.
    widths[np.all(xy == [240., 80.], axis=1)] = 8.
    geometry = build_channel_geometry(terrain, ids, graph["receiver"].copy(),
        widths, np.full(len(ids), .4),
        owner_grid=np.ones(height.shape, np.int64), corridor_mask=np.ones(height.shape, bool),
        lake_mask=np.zeros(height.shape, bool), anchor_mask=np.ones(len(ids), bool),
        config=GeometryConfig(fine_spacing_m=2., smoothing_iterations=0))
    a = geometry["arrays"]
    receiver = graph["receiver"]
    lengths = np.zeros(len(ids))
    distances = receiver_distances(a["node_xz_m"], receiver)
    for i, j in enumerate(receiver):
        if j >= 0:
            lengths[i] += distances[i] / 2.
            lengths[j] += distances[i] / 2.
    bed = _sample_nodes(geometry, a["bed_elevation_m"])
    slope = np.full(len(ids), .01)
    edges = receiver >= 0
    slope[edges] = (bed[edges] - bed[receiver[edges]]) / distances[edges]
    network = ChannelNetwork(receiver.copy(), lengths, a["width_m"].copy(), bed, slope,
        np.full(len(ids), .035), np.full(len(ids), 3.),
        np.where(edges, "interior", "open_outflow"), geometry["identity_sha256"],
        "existing canonical carved mesh; half-incident control lengths", "explicit n=.035", distances)
    times = np.arange(0., 1801., 150.)
    pulse = np.array([.3, .6, 1., 1., .8, .5, .3, .2, .15, .1, .05, .02])
    sources = [("main-head", node_id(seed, 40., 80.), pulse * .7),
               ("tributary-head", node_id(seed, 120., 160.), pulse * .4)]
    sources += [("tributary-head", node_id(seed, 120., 160.), pulse * .4)]
    for key in graph["node_ids"]:
        sources.append(("local:" + key, key, np.full(len(pulse), .002)))
    local = assemble_local_forcing(graph, times, sources)
    forcing = ChannelForcing(times, local, graph["identity_sha256"])
    return graph, geometry, network, forcing


def run(output, scene_builder=make_scene, *, material=None, channel_config=None,
        sediment_config=None, dynamics=couple_morphology, saver=save_morphology_coupling,
        reach_config=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    graph, geometry, network, forcing = scene_builder(output) if scene_builder is not make_scene else make_scene()
    scene = graph.get("scene", "explicit_analytical_engineering_scene_not_real_TD")
    save_channel_geometry(output / "generated-geometry.npz", geometry)
    (output / "world-graph.json").write_text(json.dumps(dict(
        **graph["declaration"], graph_identity_sha256=graph["identity_sha256"],
        node_xz_m=graph["node_xz_m"].tolist(), region_ids=graph["region_ids"],
        edge_ids=graph["edge_ids"], mode="global_synchronous_existing_solver",
        scene=scene), indent=2), encoding="utf-8")
    area = graph["material_area_m2"] if "material_area_m2" in graph else _basis(geometry)[1]
    n = len(network.receiver)
    material = material or MaterialParameters(sediment_erodibility_m_s_pa=2e-8,
        rock_erodibility_m_s_pa=1e-10, transport_coefficient=2e-5,
        settling_velocity_m_s=.0001,
        provenance="explicit uncalibrated ordinary tributary engineering material")
    initial_water = network.width_m * network.length_m * .02
    initial_mobile = np.full(n, .0001)
    result = dynamics(geometry, network, forcing, material,
        initial_water_volume_m3=initial_water, initial_mobile_solid_m3=initial_mobile,
        initial_alluvium_bulk_m3=area * .02, rock_floor_m=network.bed_elevation_m - .3,
        config=reach_config or MorphologyConfig(max_intervals=16),
        channel_config=channel_config or ChannelConfig(max_dt_seconds=2.),
        sediment_config=sediment_config or SedimentConfig(max_dt_seconds=1., max_bed_change_m=.01))
    saver(output / "dynamic-water-sediment-bed.npz", result)
    if result["metadata"]["status"] != "complete":
        raise RuntimeError(result["metadata"]["failure_reason"])
    a, m = result["arrays"], result["metadata"]
    water_times, depth, q, water_out = [], [], [], []
    solid_times, solid_out = [], []
    region_ids = sorted(set(graph["region_ids"]))
    regional_water_residual, regional_solid_residual = [], []
    water_export = solid_export = external_water = external_solid = 0.
    region_masks = [np.array(graph["region_ids"]) == r for r in region_ids]
    for interval in range(len(m["intervals"])):
        water = _unpack(a, m, "water_" + str(interval))["arrays"]
        sediment = _unpack(a, m, "sediment_" + str(interval))["arrays"]
        dt = np.diff(water["trace_time_seconds"])
        wout = water["trace_outflow_q_m3_s"] * dt[:, None]
        local = water["trace_local_q_m3_s"] * dt[:, None]
        wx = regional_exchange(graph, wout)
        sx = regional_exchange(graph, sediment["step_outgoing_solid_m3"])
        for r, mask in enumerate(region_masks):
            wdelta = a["water_volume_m3"][interval+1, mask].sum() - a["water_volume_m3"][interval, mask].sum()
            extout = water["trace_boundary_outflow_volume_m3"][:, mask].sum()
            regional_water_residual.append(float(wdelta - local[:, mask].sum() - wx["incoming_m3"][:, r].sum() + wx["outgoing_m3"][:, r].sum() + extout))
            before = (a["mobile_solid_m3"][interval, mask] + a["loose_solid_m3"][interval, mask]).sum()
            after = (a["mobile_solid_m3"][interval+1, mask] + a["loose_solid_m3"][interval+1, mask]).sum()
            rock = (a["rock_removed_m3"][interval+1, mask] - a["rock_removed_m3"][interval, mask]).sum()
            source = sediment["step_external_solid_m3"][:, mask].sum()
            exp = sediment["step_exported_solid_m3"][:, mask].sum()
            regional_solid_residual.append(float(after-before-rock-source-sx["incoming_m3"][:,r].sum()+sx["outgoing_m3"][:,r].sum()+exp))
        water_export += float(water["trace_boundary_outflow_volume_m3"].sum())
        solid_export += float(sediment["step_exported_solid_m3"].sum())
        external_water += float(local.sum())
        external_solid += float(sediment["step_external_solid_m3"].sum())
        water_times.extend(water["trace_time_seconds"][:-1])
        depth.extend(water["trace_depth_m"][:-1])
        q.extend(water["trace_outflow_q_m3_s"])
        water_out.extend(wout)
        solid_times.extend(sediment["trace_time_seconds"][:-1])
        solid_out.extend(sediment["step_outgoing_solid_m3"])
    water_out, solid_out = np.array(water_out), np.array(solid_out)
    wx, sx = regional_exchange(graph, water_out), regional_exchange(graph, solid_out)
    np.savez_compressed(output / "regional-exchanges.npz",
        water_step_start_seconds=water_times, water_outgoing_volume_m3=water_out,
        water_regional_incoming_m3=wx["incoming_m3"], water_regional_outgoing_m3=wx["outgoing_m3"],
        sediment_step_start_seconds=solid_times, sediment_outgoing_volume_m3=solid_out,
        sediment_regional_incoming_m3=sx["incoming_m3"], sediment_regional_outgoing_m3=sx["outgoing_m3"],
        region_ids=np.array(region_ids))
    final_water = float(a["water_volume_m3"][-1].sum())
    rock = float(a["rock_removed_m3"][-1].sum())
    final_solid = float((a["mobile_solid_m3"][-1]+a["loose_solid_m3"][-1]).sum())
    initial_solid = float((a["mobile_solid_m3"][0]+a["loose_solid_m3"][0]).sum())
    report = dict(scene=scene, status="complete",
        execution="global_synchronous_existing_water_sediment_not_partitioned_scheduler",
        seed_policy=graph.get("seed_policy", {"world_seed": graph["declaration"]["seed"], "forcing_mode": "fixed_explicit_scenario"}),
        forcing_components=graph.get("forcing_components", {"combined_local_and_boundary_input_m3": external_water}),
        physical_seconds=float(a["time_seconds"][-1]), nodes=n, regions=region_ids,
        cross_region_edges=len(graph["cross_region_donors"]),
        confluence_nodes=np.flatnonzero(np.bincount(network.receiver[network.receiver>=0], minlength=n)>=2).tolist(),
        water=dict(initial_m3=float(initial_water.sum()), local_input_m3=external_water,
            outlet_export_m3=water_export, final_storage_m3=final_water,
            residual_m3=float(initial_water.sum()+external_water-water_export-final_water),
            cross_region_transfers=wx["edge_transfers"],
            max_regional_residual_m3=float(np.max(np.abs(regional_water_residual)))),
        solid=dict(initial_mobile_plus_bed_m3=initial_solid, external_input_m3=external_solid,
            rock_eroded_m3=rock, outlet_export_m3=solid_export, final_mobile_plus_bed_m3=final_solid,
            residual_m3=initial_solid+external_solid+rock-solid_export-final_solid,
            cross_region_transfers=sx["edge_transfers"],
            max_regional_residual_m3=float(np.max(np.abs(regional_solid_residual)))),
        bed=dict(min_change_m=float((a["node_bed_m"][-1]-a["node_bed_m"][0]).min()),
                 max_change_m=float((a["node_bed_m"][-1]-a["node_bed_m"][0]).max()),
                 cut_volume_m3=geometry["metadata"]["cut_volume_m3"]),
        limitations=graph.get("limitations", ["engineering_scene_not_natural_world_selection", "not_independent_region_scheduling",
                     "no_lake_backwater_or_2D_floodplain", "explicit_uncalibrated_material_and_inflow"]),
        dynamic_geometry_mode="canonical_PL_mesh" if "mesh_bed_m" in a else "nodal_bed_only_initial_PL_mesh_not_updated",
        existing_algorithms=graph.get("existing_algorithms", ["build_channel_geometry", "solve_channel", "solve_sediment", "couple_morphology"]))
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    plot(output, graph, geometry, result, np.array(water_times), np.array(depth), np.array(q), wx, sx)
    (output / "report.md").write_text("# 跨区域普通干支流运行结果\n\n场景: " + scene + "。使用切后床，复用原Manning/输沙与库存床变，全图共同步推进。动态几何模式见dynamic_geometry_mode字段，nodal模式不更新完整PL网格。跨区是原图真实内部边输运，尚非独立分区调度。\n\n```json\n" + json.dumps(report, indent=2, ensure_ascii=False) + "\n```\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return report


def plot(output, graph, geometry, result, times, depth, q, wx, sx):
    a = geometry["arrays"]
    state = result["arrays"]
    xy = a["node_xz_m"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ax = axes[0,0]
    span = graph["declaration"]["region_size_m"]
    boundary = (np.floor(xy[:,0].min()/span)+1)*span
    padding = max(10.,np.ptp(xy[:,0])*.1)
    xmin,xmax = xy[:,0].min()-padding,xy[:,0].max()+padding
    ax.axvspan(xmin,boundary,color="#d8e8f8",alpha=.7)
    ax.axvspan(boundary,xmax,color="#f8e8d8",alpha=.7)
    for i,j in enumerate(graph["receiver"]):
        if j>=0:
            ax.annotate("",xy[j],xy[i],arrowprops=dict(arrowstyle="->",color="#17689a",lw=2))
    ax.scatter(*xy.T,c="k",s=20)
    for i,p in enumerate(xy): ax.text(*p,str(i),fontsize=9)
    ax.axvline(boundary,color="gray",ls="--")
    ax.set(xlabel="World X (m)",ylabel="World Z (m)",
           title="Trunk + tributary / actual ownership boundary",xlim=(xmin,xmax),
           ylim=(xy[:,1].min()-padding,xy[:,1].max()+padding))
    ax.ticklabel_format(useOffset=False,style="plain")
    heads = np.flatnonzero(np.bincount(graph["receiver"][graph["receiver"] >= 0], minlength=len(xy)) == 0)
    outlet = int(np.flatnonzero(graph["receiver"] < 0)[0])
    for i in list(heads) + [outlet]:
        axes[0,1].plot(times,q[:,i],label=f"node {i}" + (" (outlet)" if i == outlet else " (head)"))
    axes[0,1].set(xlabel="Physical seconds",ylabel="Outflow (m3/s)",title="Actual routed hydrograph");axes[0,1].legend()
    # Internal solver steps are nonuniform: use their actual physical-time edges.
    time_edges = np.r_[times, state["time_seconds"][-1]]
    image=axes[1,0].pcolormesh(time_edges, np.arange(len(xy)+1)-.5, depth.T,
                              shading="flat",cmap="Blues")
    fig.colorbar(image,ax=axes[1,0],label="Water depth (m)")
    axes[1,0].set(xlabel="Physical seconds",ylabel="World node index",title="Water moving through the joined graph")
    for i in range(len(xy)):
        axes[1,1].plot(state["time_seconds"],1000*(state["node_bed_m"][:,i]-state["node_bed_m"][0,i]),label=str(i))
    axes[1,1].set(xlabel="Physical seconds",ylabel="Bed change (mm)",title="Existing sediment + Exner feedback")
    fig.tight_layout();fig.savefig(output/"tributary-overview.png",dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    if "mesh_bed_m" in state:
        mesh=ax.tripcolor(a["vertices_xz_m"][:,0],a["vertices_xz_m"][:,1],a["triangles"],state["mesh_bed_m"][-1]-state["mesh_bed_m"][0],cmap="RdBu_r",shading="gouraud")
        title="Actual canonical carved mesh: dynamic bed change (m)"
    else:
        mesh=ax.scatter(xy[:,0],xy[:,1],c=state["node_bed_m"][-1]-state["node_bed_m"][0],s=160,cmap="RdBu_r")
        for i,j in enumerate(graph["receiver"]):
            if j>=0:
                ax.plot(xy[[i,j],0],xy[[i,j],1],color="gray",zorder=0)
        title="Dynamic nodal bed change (m); initial PL mesh not remapped"
    ax.axvline(boundary,color="gray",ls="--")
    ax.set(xlabel="World X (m)",ylabel="World Z (m)",title=title)
    ax.ticklabel_format(useOffset=False,style="plain")
    fig.colorbar(mesh,ax=ax);fig.tight_layout();fig.savefig(output/"carved-bed-change.png",dpi=150);plt.close(fig)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    run(parser.parse_args().output)
