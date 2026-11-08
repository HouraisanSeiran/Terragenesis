"""Full seed-world reach: one real dendritic basin across four owning cores, ending in
an endorheic lake, run on the existing canonical geometry / Manning / sediment chain.

Nothing here is a new solver. The reach is selected from `domain_topology` (the same
window-independent raw D8 field the previous stage used), cut with the existing
`build_channel_geometry`, driven through the existing `solve_channel` +
`solve_sediment` nodal recoupling (`world_channel_dynamics.couple_nodal_reach`), and
the terminal open-outflow volume feeds the existing `metric_lake_storage` level-pool
store (`world_reach_lake`).

Geometry feasibility is a real constraint of the old canonical carver: it rejects a
centreline edge whose bilinear source profile is not strictly monotone
(`metric_channel_geometry._route_slope`, "candidate has uphill original-bed
 derivative"). The same guard is reused here, edge by edge, instead of being
re-implemented. A refused edge truncates the reach there; its upstream subtree
enters through an explicit, fully specified boundary hydrograph produced by the same
soil bucket over the omitted cells, so reach plus declared scenarios still carry the
whole basin volume.

Run:  D:/anaconda/python.exe -B tools/run_real_world_full_reach.py \
          --output .scratch/cross-region-tributary/full-reach-run-01
"""
import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff
from terrain_pipeline.channel_geometry import GeometryConfig, _route_slope, build_channel_geometry
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork, receiver_distances
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_domain_closure import domain_topology
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _sample_nodes, _unpack
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.world_channel_dynamics import couple_nodal_reach, save_nodal_reach
from terrain_pipeline.surface_rivers.world_channel_graph import (
    WorldNode, assemble_local_forcing, assemble_world_graph, derive_noise_seed, node_id)
from terrain_pipeline.lake import WIDTH_EXPONENT as WIDTH_EXPONENT
from terrain_pipeline.lake import build_sill_lake as build_sill_lake
from terrain_pipeline.lake import channel_width_from_lithology_m as channel_width_from_lithology_m
from terrain_pipeline.lake import integrate_sill_lake as integrate_sill_lake
from terrain_pipeline.geology import sample_lithology_points
from tools.run_cross_region_tributary import run

SEED = 20261020
# The basin straddling the core corner (1280 km, 1280 km): its nodes fall in four
# different owning cores. Anchored on the tile that owns the terminal cell.
TERMINAL_XZ_M = (1300000., 1290000.)

FINE_SPACING_M = 30.
WIDTH_RESOLUTION = 2.
# Width bounds. These used to be 800 / 3200 m, which were *geometry* limits of the
# 10 km carrier: 800 m was "the narrowest channel a 10 km cell can resolve". On a
# 30 m base that constraint is gone, and the old bounds made every reach an order
# of magnitude too wide. Measured against Leopold & Maddock (1953, W = 8.6 Q^0.5
# for bankfull width in metres and Q in m3/s), the old 800 m floor put a 27.8 m3/s
# reach at 2 071 m where the data say ~45 m, i.e. up to 50x too wide.
#
# The bounds below are the field-data envelope, not a carrier limit: 30 m is the
# narrowest channel the 30 m base can carry without sub-grid sections, and 3000 m
# is a large lowland river (Amazon-scale bankfull). They still clamp, because the
# discretisation cannot represent less than one cell, and the clamp count is
# reported in `width_clamp` rather than being left implicit.
MIN_WIDTH_M = 30.
MAX_WIDTH_M = 3000.
REFERENCE_WIDTH_M = 45.
# Anchored so the law reproduces Leopold & Maddock at the reference point:
# Q_ref = 27.8 m3/s (one 10 km basin cell at the 1 mm/h design runoff) and
# W_ref = 45 m is the field-data width for that discharge.
REFERENCE_DISCHARGE_M3_S = 100e6 / 1000. / 3600.
SECTION_DEPTH_M = .4
MANNING_N = .035
MAX_DEPTH_M = 3.

# Fixed explicit 72-hour scenario (mm/h): 24 hours of storm then 48 hours of recession.
STORM_RAIN_MM_H = np.array([1., 2., 3., 4., 5., 6., 7., 8., 8., 7., 6., 6.,
                            5., 5., 4., 4., 3., 3., 2., 2., 2., 1., 1., 1.]
                           + [0.] * 48)
INITIAL_STAGE_BELOW_SILL_M = .05
WEIR_DISCHARGE_COEFFICIENT = .4
WEIR_HEAD_ALLOWANCE_M = 1.5


@dataclass(frozen=True)
class FullReachConfig:
    """Dynamics bounds for a reach wider than the original 16-node guard."""

    max_nodes: int = 64
    max_intervals: int = 168
    max_cumulative_bed_change_m: float = .05
    max_depth_change_m: float = .05


def world_xz(topology, cell):
    shape = topology["shape"]
    row, col = divmod(int(cell), shape[1])
    return (topology["origin_x_m"] + col * topology["spacing_m"],
            topology["origin_z_m"] + row * topology["spacing_m"])


def cell_at(topology, point):
    shape = topology["shape"]
    col = int(round((point[0] - topology["origin_x_m"]) / topology["spacing_m"]))
    row = int(round((point[1] - topology["origin_z_m"]) / topology["spacing_m"]))
    if not (0 <= row < shape[0] and 0 <= col < shape[1]):
        raise ValueError("selected point outside source snapshot")
    return row * shape[1] + col


def _terrain_window(topology, cells):
    shape = topology["shape"]
    spacing = topology["spacing_m"]
    rows, cols = cells // shape[1], cells % shape[1]
    r0, c0 = int(rows.min() - 1), int(cols.min() - 1)
    r1, c1 = int(rows.max() + 2), int(cols.max() + 2)
    source = topology["height_m"][r0:r1, c0:c1].astype(np.float64).copy()
    x0 = topology["origin_x_m"] + c0 * spacing
    z0 = topology["origin_z_m"] + r0 * spacing
    source_id = hashlib.sha256(source.tobytes() + json.dumps([x0, z0, spacing]).encode()).hexdigest()
    terrain = TerrainGrid(source, np.ones(source.shape, bool), x0, z0, spacing, spacing,
                          "generated_terrain",
                          "seed20261020_actual_coarse_condition_field_bilinear_interpolation_not_TD_detail",
                          source_id)
    return terrain, dict(r0=r0, c0=c0)


def select_reach(seed=SEED, terminal_xz=TERMINAL_XZ_M):
    """Full real basin of one inland terminal, truncated where the old carver refuses."""
    topology = domain_topology(seed, *terminal_xz)
    spacing = topology["spacing_m"]
    core_span = topology["core_cells"] * spacing
    receiver = topology["receiver"].ravel()
    terminal = topology["terminal"].ravel()
    accepted = topology["accepted"].ravel()
    ocean_terminal = topology["ocean_terminal"].ravel()
    height = topology["height_m"].ravel()
    outlet = cell_at(topology, terminal_xz)
    if not accepted[outlet] or ocean_terminal[outlet] or receiver[outlet] >= 0:
        raise ValueError("selected terminal must be an accepted inland D8 minimum")
    basin = np.flatnonzero(accepted & (terminal == outlet))
    if not 20 <= len(basin) <= 400:
        raise ValueError("selected basin outside the reviewable size band")
    local = {int(cell): index for index, cell in enumerate(basin)}
    donors = {}
    for cell in basin:
        downstream = receiver[cell]
        if downstream >= 0:
            if int(downstream) not in local:
                raise ValueError("selected basin drains outside its own terminal")
            donors.setdefault(int(downstream), []).append(int(cell))
    accumulation = np.zeros(len(basin), np.int64)
    for index in np.argsort(-height[basin], kind="stable"):
        accumulation[index] = 1 + sum(int(accumulation[local[donor]])
                                      for donor in donors.get(int(basin[index]), ()))
    terrain, window = _terrain_window(topology, basin)
    points = np.array([world_xz(topology, cell) for cell in basin], np.float64)
    refused = []
    for index, cell in enumerate(basin):
        downstream = receiver[cell]
        if downstream < 0:
            continue
        target = local[int(downstream)]
        try:
            _route_slope(points[[index, target]], np.array([1, -1], np.int64), terrain)
        except ValueError:
            refused.append(index)
    drop = np.zeros(len(basin), bool)
    stack = list(refused)
    while stack:
        index = stack.pop()
        if drop[index]:
            continue
        drop[index] = True
        stack.extend(local[donor] for donor in donors.get(int(basin[index]), ()))
    kept = np.flatnonzero(~drop)
    if not 20 <= kept.size <= 60:
        raise ValueError("truncated reach outside the requested node band: %d" % kept.size)
    cut = [(index, local[int(receiver[basin[index]])]) for index in np.flatnonzero(drop)
           if receiver[basin[index]] >= 0 and not drop[local[int(receiver[basin[index]])]]]
    subtree = {}
    for index, _ in cut:
        members, stack = [], [index]
        while stack:
            current = stack.pop()
            members.append(current)
            stack.extend(local[donor] for donor in donors.get(int(basin[current]), ()))
        subtree[index] = sorted(members)
    kept_points = points[kept]
    records = [WorldNode(seed, float(kept_points[i, 0]), float(kept_points[i, 1]),
                         None if receiver[basin[kept[i]]] < 0 else
                         node_id(seed, *world_xz(topology, int(receiver[basin[kept[i]]]))))
               for i in range(kept.size)]
    graph = assemble_world_graph(records, core_span)
    by_identity = {node_id(seed, *world_xz(topology, int(basin[index]))): int(index) for index in kept}
    node_basin_index = np.array([by_identity[key] for key in graph["node_ids"]], np.int64)
    node_cells = basin[node_basin_index]
    node_accumulation = accumulation[node_basin_index]
    for index, basin_index in enumerate(node_basin_index):
        downstream = receiver[basin[basin_index]]
        expected = -1 if downstream < 0 else int(np.flatnonzero(node_cells == downstream)[0])
        if graph["receiver"][index] != expected:
            raise ValueError("world graph receiver disagrees with the raw D8 receiver")
    try:
        _route_slope(np.array([world_xz(topology, cell) for cell in node_cells], np.float64),
                     graph["receiver"].copy(), terrain)
    except ValueError as error:
        raise ValueError("truncated reach still refused by the canonical carver: " + str(error))
    cut_edges = []
    for index, _ in cut:
        members = subtree[index]
        cut_edges.append(dict(from_xz_m=list(world_xz(topology, int(basin[index]))),
                              to_xz_m=list(world_xz(topology, int(receiver[basin[index]]))),
                              omitted_cell_count=len(members),
                              omitted_cells=[int(basin[m]) for m in members],
                              source="declared_truncated_upstream_scenario_same_soil_bucket_over_omitted_cells"))
    return dict(topology=topology, terrain=terrain, window=window, basin=basin, kept=kept,
                graph=graph, node_cells=node_cells, node_accumulation=node_accumulation,
                accumulation=accumulation, cut_edges=cut_edges, refused=refused,
                outlet=outlet, core_span=core_span)


def boundary_scenarios(cut_edges, unit_q_m3_s):
    """Explicit hydrograph for every truncated upstream edge.

    Each omitted subtree is run through the same `simulate_rainfall_runoff` bucket as the
    kept cells; every coarse cell shares one area and one forcing, so the subtree series
    is the unit series times the number of omitted cells. It is a declared fixed
    scenario, not a fitted inflow, and it is what keeps the basin volume complete.
    """
    scenario = []
    for edge in cut_edges:
        rates = unit_q_m3_s * float(edge["omitted_cell_count"])
        edge["q_m3_s"] = rates.tolist()
        scenario.append(("boundary:" + node_id(SEED, *edge["from_xz_m"]) + "->" +
                         node_id(SEED, *edge["to_xz_m"]),
                         node_id(SEED, *edge["to_xz_m"]), rates))
    return scenario


def lake_geometry(topology, bed_at_outlet, terminal_cell):
    """Sill and secondary saddle of the endorheic terminal from the raw tile, no filling."""
    shape = topology["shape"]
    height = topology["height_m"]
    row, col = divmod(int(terminal_cell), shape[1])
    neighbours = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rr, cc = row + dr, col + dc
            if 0 <= rr < shape[0] and 0 <= cc < shape[1]:
                neighbours.append(((topology["origin_x_m"] + cc * topology["spacing_m"],
                                    topology["origin_z_m"] + rr * topology["spacing_m"]),
                                   float(height[rr, cc])))
    neighbours.sort(key=lambda item: item[1])
    if neighbours[0][1] <= bed_at_outlet + 1e-9:
        raise ValueError("terminal is not a strict local minimum of the raw tile")
    return dict(sill_stage_m=neighbours[0][1], primary_target_xz_m=list(neighbours[0][0]),
                secondary_target_xz_m=list(neighbours[1][0]),
                secondary_sill_stage_m=neighbours[1][1])


def make_full_reach_scene(output, *, hours=72):
    """Build the real reach, its carved geometry, fixed forcing and the lake definition."""
    output = Path(output)
    started = time.perf_counter()
    selection = select_reach()
    topology, terrain = selection["topology"], selection["terrain"]
    graph, node_cells = selection["graph"], selection["node_cells"]
    n = len(node_cells)
    spacing = topology["spacing_m"]
    cell_area = spacing * spacing
    shape = topology["shape"]
    rows, cols = node_cells // shape[1], node_cells % shape[1]
    r0, c0 = selection["window"]["r0"], selection["window"]["c0"]
    local_ids = np.array([(row - r0) * terrain.elevation_m.shape[1] + col - c0
                          for row, col in zip(rows, cols)], np.int64)
    contributing_area = selection["node_accumulation"] * cell_area
    # Width comes from discharge **and** rock hardness, which is the project's own
    # stated erosion rule (`metric_discharge_geometry.build_discharge_geometry`).
    # The hardness is sampled at each node's absolute world coordinate from the
    # 18-rock / three-class geology table, so a granite reach and a shale reach
    # with the same discharge are no longer forced to the same width.
    node_xz = np.array([[terrain.x0_m + col * spacing,
                         terrain.z0_m + row * spacing]
                        for row, col in zip(rows, cols)], np.float64)
    lithology = sample_lithology_points(node_xz[:, 0], node_xz[:, 1], world_seed=SEED)
    bed_hardness = np.asarray(lithology["bed_hardness"], np.float64)
    bank_hardness = np.asarray(lithology["bank_hardness"], np.float64)
    widths, design_q = channel_width_from_lithology_m(
        contributing_area, bed_hardness, bank_hardness,
        reference_discharge_m3_s=REFERENCE_DISCHARGE_M3_S,
        reference_width_m=REFERENCE_WIDTH_M,
        min_width_m=MIN_WIDTH_M, max_width_m=MAX_WIDTH_M)
    # A clamp that binds on a large fraction of the reach hides the rock effect it
    # is supposed to carry, so the count is measured and reported instead of being
    # left implicit. `MAX_WIDTH_M` itself is a geometry limit of the 10 km carrier,
    # not a hydraulic conclusion.
    unbounded_widths = np.clip(
        REFERENCE_WIDTH_M * (design_q / REFERENCE_DISCHARGE_M3_S) ** WIDTH_EXPONENT
        * (1. + 1.5 * bed_hardness) * (.5 + 1.5 * (1. - bank_hardness)),
        MIN_WIDTH_M, np.inf)
    width_clamp = dict(
        at_upper_bound=int(np.count_nonzero(widths >= MAX_WIDTH_M - 1e-9)),
        at_lower_bound=int(np.count_nonzero(widths <= MIN_WIDTH_M + 1e-9)),
        nodes=int(n), upper_bound_m=MAX_WIDTH_M, lower_bound_m=MIN_WIDTH_M,
        interpretation=("the bound is a carrier geometry limit, not a hydraulic result; "
                        "a large count means rock differences are being truncated"))
    geometry = build_channel_geometry(terrain, local_ids, graph["receiver"].copy(), widths,
        np.full(n, SECTION_DEPTH_M), owner_grid=np.ones(terrain.elevation_m.shape, np.int64),
        corridor_mask=np.ones(terrain.elevation_m.shape, bool),
        lake_mask=np.zeros(terrain.elevation_m.shape, bool), anchor_mask=np.ones(n, bool),
        config=GeometryConfig(fine_spacing_m=FINE_SPACING_M, width_resolution=WIDTH_RESOLUTION,
                              smoothing_iterations=0))
    a = geometry["arrays"]
    np.testing.assert_array_equal(a["node_source_elevation_m"],
                                  topology["height_m"].ravel()[node_cells])
    bed = _sample_nodes(geometry, a["bed_elevation_m"])
    distance = receiver_distances(a["node_xz_m"], graph["receiver"])
    lengths = np.zeros(n)
    slope = np.zeros(n)
    for index, downstream in enumerate(graph["receiver"]):
        if downstream >= 0:
            lengths[index] += distance[index] / 2.
            lengths[downstream] += distance[index] / 2.
            slope[index] = (bed[index] - bed[downstream]) / distance[index]
    outlet = int(np.flatnonzero(graph["receiver"] < 0)[0])
    slope[outlet] = slope[np.flatnonzero(graph["receiver"] == outlet)[0]]
    network = ChannelNetwork(graph["receiver"].copy(), lengths, widths, bed, slope,
        np.full(n, MANNING_N), np.full(n, MAX_DEPTH_M),
        np.where(graph["receiver"] >= 0, "interior", "open_outflow"),
        geometry["identity_sha256"],
        "actual world receiver, bilinear coarse bed cut, half-incident lengths; "
        "width from discharge and sampled rock hardness", "explicit uncalibrated n=.035", distance)
    rainfall = np.asarray(STORM_RAIN_MM_H[:hours], np.float64)
    times = np.arange(0., 3600. * len(rainfall) + 3600., 3600.)
    parameters = RunoffParameters(infiltration_capacity_mm_h=2.)
    unit = simulate_rainfall_runoff(np.broadcast_to(rainfall[:, None], (len(rainfall), 1)).copy(),
        np.full(1, cell_area), dt_s=3600., source_id=terrain.identity_sha256, parameters=parameters)
    unit_q = unit["local_q_m3_s"][:, 0]
    runoff = simulate_rainfall_runoff(np.broadcast_to(rainfall[:, None], (len(rainfall), n)).copy(),
        np.full(n, cell_area), dt_s=3600., source_id=terrain.identity_sha256, parameters=parameters)
    np.testing.assert_allclose(runoff["local_q_m3_s"],
                               np.broadcast_to(unit_q[:, None], (len(rainfall), n)))
    sources = [("local-cell:" + key, key, runoff["local_q_m3_s"][:, index])
               for index, key in enumerate(graph["node_ids"])]
    scandir_scenarios = boundary_scenarios(selection["cut_edges"], unit_q)
    sources += scandir_scenarios
    local = assemble_local_forcing(graph, times, sources)
    forcing = ChannelForcing(times, local, graph["identity_sha256"])
    bed_at_outlet = float(bed[outlet])
    lake_shape = lake_geometry(topology, bed_at_outlet, int(node_cells[outlet]))
    lake_inputs = dict(
        cell_ids=[int(node_cells[outlet])], bed_elevation_m=[bed_at_outlet],
        cell_area_m2=[cell_area], seed_cell_id=int(node_cells[outlet]),
        sill_stage_m=lake_shape["sill_stage_m"], head_allowance_m=WEIR_HEAD_ALLOWANCE_M,
        sill_width_m=spacing, source_identity_sha256=terrain.identity_sha256,
        primary_target_xz_m=lake_shape["primary_target_xz_m"],
        secondary_sill=dict(stage_m=lake_shape["secondary_sill_stage_m"], width_m=spacing * .5,
                            target_xz_m=lake_shape["secondary_target_xz_m"]),
        discharge_coefficient=WEIR_DISCHARGE_COEFFICIENT,
        provenance=dict(module='terrain_pipeline.lake',
                        support_policy="single native coarse cell at the inland D8 minimum",
                        sill_policy="lowest of the eight raw neighbours of the terminal cell",
                        weir_law="LakeOutlet Q=C*(stage-crest)^1.5 with C=Cd*sqrt(2g)*sill width",
                        sill_width_source="native tile spacing (one cell edge)",
                        secondary_sill_policy="second lowest raw neighbour, half sill width, higher than the primary sill"))
    lake = build_sill_lake(**lake_inputs)
    initial_stage = lake.sill_stage_m - INITIAL_STAGE_BELOW_SILL_M
    initial_lake_volume = lake.storage.volume_at_stage(initial_stage)
    region_counts = {region: int(sum(1 for r in graph["region_ids"] if r == region))
                     for region in sorted(set(graph["region_ids"]))}
    cross_core = []
    for donor in graph["cross_region_donors"]:
        target = int(graph["receiver"][donor])
        cross_core.append(dict(donor=int(donor), receiver=target,
                               from_region=graph["region_ids"][donor],
                               to_region=graph["region_ids"][target],
                               donor_xz_m=graph["node_xz_m"][donor].tolist(),
                               receiver_xz_m=graph["node_xz_m"][target].tolist()))
    graph["scene"] = ("actual_seed20261020_coarse_world_basin_across_four_owning_cores_truncated_at_"
                      "canonical_geometry_refused_edges_with_endorheic_lake_terminal")
    graph["material_area_m2"] = network.width_m * network.length_m
    graph["existing_algorithms"] = ["build_channel_geometry", "solve_channel", "solve_sediment",
                                    "bed_from_inventory", "LakeStorage.volume_at_stage",
                                    "LakeStorage.stage_at_volume", "LakeOutlet.discharge_at_stage"]
    graph["forcing_components"] = dict(
        kept_cell_bucket_input_m3=float(runoff["outflow_volume_m3"].sum()),
        prescribed_truncated_upstream_input_m3=float(sum(
            edge["omitted_cell_count"] * unit["outflow_volume_m3"].sum()
            for edge in selection["cut_edges"])),
        interpretation="kept cells release their own bucket runoff; every truncated upstream edge carries the same "
                       "bucket over its omitted cells, so declared scenarios plus reach cover the whole basin")
    graph["limitations"] = ["real_basin_truncated_where_the_canonical_carver_refuses_a_non_monotone_source_profile",
        "coarse_10km_field_interpolated_not_TD_detail",
        "explicit_uncalibrated_width_roughness_material",
        "rock_hardness_from_simplified_noise_distribution_not_tectonic",
        "global_synchronous_not_partitioned_scheduler",
        "single_cell_coarse_level_pool_lake_no_two_way_backwater",
        "lake_sediment_delivery_not_inventoried_in_lake_bed",
        "fixed_explicit_storm_not_noise_generated_climate"]
    graph["seed_policy"] = dict(world_seed=SEED,
        derivation="sha256 JSON[terragenesis-world-noise-v1,world_seed,purpose] first32bits bigendian",
        reserved_noise_seeds={purpose: derive_noise_seed(SEED, purpose)
                              for purpose in ("climate", "rainfall", "light")},
        active_noise_generators=[],
        rainfall_mode="fixed_explicit_%d_hour_storm_not_noise_generated" % len(rainfall),
        boundary_mode="fixed_explicit_bucket_hydrograph_per_declared_truncated_upstream_edge",
        future_noise_coordinates="absolute world x/z and explicit simulation time index, never loading order")
    selection_report = dict(seed=SEED, seed_policy=graph["seed_policy"],
        source_module="metric_domain_closure.domain_topology",
        source_terrain_sha256=terrain.identity_sha256, config=asdict(PlanningConfig()),
        anchor_xz_m=list(TERMINAL_XZ_M),
        tile_origin_xz_m=[topology["origin_x_m"], topology["origin_z_m"]],
        core_origin_xz_m=[topology["core_origin_x_m"], topology["core_origin_z_m"]],
        core_span_m=selection["core_span"], owning_cores=region_counts,
        terminal_xz_m=list(TERMINAL_XZ_M), terminal_cell=int(node_cells[outlet]),
        full_basin_cell_count=int(selection["basin"].size), node_count=n,
        refused_d8_edges=int(len(selection["refused"])),
        confluence_nodes=np.flatnonzero(
            np.bincount(graph["receiver"][graph["receiver"] >= 0], minlength=n) >= 2).tolist(),
        cross_core_edges=len(graph["cross_region_donors"]), cross_core_edge_detail=cross_core,
        node_xz_m=graph["node_xz_m"].tolist(), node_cell_ids=node_cells.tolist(),
        node_contributing_area_m2=contributing_area.tolist(),
        node_design_q_m3_s=design_q.tolist(), node_width_m=widths.tolist(),
        node_bed_m=bed.tolist(), node_bed_slope=slope.tolist(),
        node_region_ids=list(graph["region_ids"]),
        original_receiver_flat_ids=topology["receiver"].ravel()[node_cells].tolist(),
        original_node_height_m=topology["height_m"].ravel()[node_cells].tolist(),
        truncated_upstream_edges=selection["cut_edges"],
        width_law=("W = clip(800*(Q/Q_cell)^0.5*(1+1.5*h_bed)*(0.5+1.5*(1-h_bank)), 800, 3200) m, "
                   "Q = A*1 mm/h/1000/3600 (metric_network_geometry design-runoff convention); "
                   "exponent .5 from metric_channel_plan.ChannelRecipe / Leopold & Maddock 1953 USGS PP252; "
                   "hardness factors copied verbatim from metric_discharge_geometry.build_discharge_geometry"),
        width_clamp=width_clamp,
        node_width_unclamped_m=unbounded_widths.tolist(),
        node_rock_index=np.asarray(lithology["rock_index"], np.int64).tolist(),
        node_rock_class_index=np.asarray(lithology["class_index"], np.int64).tolist(),
        node_bed_hardness=bed_hardness.tolist(),
        node_bank_hardness=bank_hardness.tolist(),
        node_erodibility_index=np.asarray(lithology["erodibility_index"], np.float64).tolist(),
        width_reference_discharge_m3_s=cell_area / 1000. / 3600.,
        rainfall_mm_h=rainfall.tolist(), physical_seconds=float(times[-1]),
        runoff_parameters=asdict(parameters),
        coarse_terrain_spacing_m=spacing, canonical_PL_spacing_m=FINE_SPACING_M,
        geometry_config=asdict(GeometryConfig(fine_spacing_m=FINE_SPACING_M,
                                             width_resolution=WIDTH_RESOLUTION,
                                             smoothing_iterations=0)),
        lake=lake_inputs, lake_initial_stage_below_sill_m=INITIAL_STAGE_BELOW_SILL_M,
        lake_initial_stage_m=float(initial_stage),
        lake_initial_volume_m3=float(initial_lake_volume),
        lake_capacity_m3=lake.capacity_m3(), lake_volume_at_sill_m3=lake.volume_at_sill_m3(),
        terminal_node_index=outlet,
        terrain_window=dict(r0=r0, c0=c0, shape=list(terrain.elevation_m.shape)))
    (output / "source-selection.json").write_text(json.dumps(selection_report, indent=2),
                                                 encoding="utf-8")
    (output / "lake-definition.json").write_text(json.dumps(
        dict(lake=lake_inputs, initial_volume_m3=float(initial_lake_volume),
             initial_stage_m=float(initial_stage),
             initial_stage_below_sill_m=INITIAL_STAGE_BELOW_SILL_M,
             capacity_m3=lake.capacity_m3(), volume_at_sill_m3=lake.volume_at_sill_m3(),
             sill_depth_m=lake.sill_depth_m, secondary_sill=lake.secondary_sill,
             terminal_node_index=outlet, terminal_cell=int(node_cells[outlet]),
             outlets=[dict(crest_stage_m=o.crest_stage_m,
                           coefficient_m3_s_m15=o.coefficient_m3_s_m15,
                           receiver=o.receiver, provenance=o.provenance) for o in lake.outlets]),
        indent=2), encoding="utf-8")
    np.savez_compressed(output / "source-terrain-and-forcing.npz", height_m=terrain.elevation_m,
        origin_xz_m=[terrain.x0_m, terrain.z0_m], node_cell_ids=local_ids,
        original_tile_cell_ids=node_cells, raw_node_height_m=topology["height_m"].ravel()[node_cells],
        raw_receiver=topology["receiver"].ravel()[node_cells], time_seconds=times,
        local_bucket_q_m3_s=runoff["local_q_m3_s"],
        boundary_q_m3_s=local - runoff["local_q_m3_s"],
        node_contributing_area_m2=contributing_area, node_width_m=widths,
        node_design_q_m3_s=design_q, unit_cell_local_q_m3_s=unit_q,
        **{"runoff_" + key: value for key, value in runoff.items()
           if isinstance(value, np.ndarray)})
    print(json.dumps(dict(nodes=n, full_basin_cells=int(selection["basin"].size),
        refused_edges=int(len(selection["refused"])),
        declared_edges=len(selection["cut_edges"]), owning_cores=region_counts,
        cross_core_edges=len(graph["cross_region_donors"]),
        confluences=len(selection_report["confluence_nodes"]),
        widths_m=[float(widths.min()), float(widths.max())],
        physical_seconds=float(times[-1]), lake_sill_depth_m=lake.sill_depth_m,
        lake_initial_volume_m3=float(initial_lake_volume), lake_capacity_m3=lake.capacity_m3(),
        mesh_vertices=int(a["vertices_xz_m"].shape[0]),
        cut_volume_m3=geometry["metadata"]["cut_volume_m3"],
        scene_seconds=time.perf_counter() - started), indent=2), flush=True)
    return graph, geometry, network, forcing


def _load_dynamics(output):
    with np.load(output / "dynamic-water-sediment-bed.npz", allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    record = json.loads(arrays.pop("manifest").tobytes().decode("utf-8"))
    return arrays, record["metadata"], record["identity_sha256"]


def finish_full_reach(output):
    """Feed the saved terminal outflow into the lake, close the domain ledger, report, plot."""
    output = Path(output)
    selection = json.loads((output / "source-selection.json").read_text(encoding="utf-8"))
    definition = json.loads((output / "lake-definition.json").read_text(encoding="utf-8"))
    lake = build_sill_lake(**definition["lake"])
    arrays, metadata, bundle_identity = _load_dynamics(output)
    terminal = int(selection["terminal_node_index"])
    inflow, dts, steps = [], [], 0
    for index in range(len(metadata["intervals"])):
        water = _unpack(arrays, metadata, "water_%d" % index)["arrays"]
        boundary = np.asarray(water["trace_boundary_outflow_volume_m3"], np.float64)
        scale = max(1., float(np.max(boundary)))
        if np.max(np.abs(np.delete(boundary, terminal, axis=1))) > 1e-9 * scale:
            raise ValueError("open outflow appeared outside the terminal node")
        inflow.append(boundary[:, terminal].copy())
        dts.append(np.diff(np.asarray(water["trace_time_seconds"], np.float64)))
        steps += boundary.shape[0]
    inflow, dts = np.concatenate(inflow), np.concatenate(dts)
    lake_run = integrate_sill_lake(lake, inflow, dts,
                                   initial_volume_m3=definition["initial_volume_m3"])
    np.savez_compressed(output / "lake-storage.npz",
        time_edges_seconds=lake_run["time_edges_seconds"], stage_m=lake_run["stage_m"],
        volume_m3=lake_run["volume_m3"], surface_area_m2=lake_run["surface_area_m2"],
        inflow_volume_m3=lake_run["inflow_volume_m3"], spill_volume_m3=lake_run["spill_volume_m3"],
        dt_seconds=lake_run["dt_seconds"], sill_stage_m=np.array(lake.sill_stage_m),
        bed_elevation_m=np.array(lake.bed_elevation_m),
        outlet_crest_m=np.array([o.crest_stage_m for o in lake.outlets]),
        outlet_coefficient_m3_s_m15=np.array([o.coefficient_m3_s_m15 for o in lake.outlets]),
        **{"ledger_" + key: np.array(value) for key, value in lake_run["ledger"].items()})
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    channel_water, channel_solid = report["water"], report["solid"]
    ledger = lake_run["ledger"]
    if abs(channel_water["outlet_export_m3"] - ledger["inflow_m3"]) > 1e-6 * max(
            1., abs(ledger["inflow_m3"])):
        raise ValueError("channel terminal export and lake inflow disagree")
    domain_initial = channel_water["initial_m3"] + ledger["initial_m3"]
    domain_final = channel_water["final_storage_m3"] + ledger["final_m3"]
    domain_input = channel_water["local_input_m3"]
    domain_export = ledger["spill_m3"]
    spill_by_outlet = lake_run["outlet_spill_m3"]
    overflowing_steps = int(np.count_nonzero(lake_run["spill_volume_m3"].sum(axis=1) > 0.))
    report["lake"] = dict(
        module="terrain_pipeline.surface_rivers.metric_lake_storage + world_reach_lake wiring",
        support_cells=[int(definition["terminal_cell"])],
        support_area_m2=float(definition["lake"]["cell_area_m2"][0]),
        bed_elevation_m=float(lake.bed_elevation_m), sill_stage_m=float(lake.sill_stage_m),
        secondary_sill=definition["secondary_sill"],
        outlet_coefficients_m3_s_m15=[float(o.coefficient_m3_s_m15) for o in lake.outlets],
        outlet_crests_m=[float(o.crest_stage_m) for o in lake.outlets],
        capacity_m3=float(definition["capacity_m3"]),
        volume_at_sill_m3=float(definition["volume_at_sill_m3"]),
        initial_stage_m=float(definition["initial_stage_m"]),
        initial_volume_m3=float(ledger["initial_m3"]),
        final_stage_m=float(lake_run["stage_m"][-1]),
        final_volume_m3=float(ledger["final_m3"]),
        max_stage_m=float(np.max(lake_run["stage_m"])),
        min_stage_m=float(np.min(lake_run["stage_m"])),
        surface_area_m2=float(lake_run["surface_area_m2"][-1]),
        inflow_m3=float(ledger["inflow_m3"]), spill_m3=float(ledger["spill_m3"]),
        spill_by_outlet_m3=[float(value) for value in spill_by_outlet],
        storage_change_m3=float(ledger["final_m3"] - ledger["initial_m3"]),
        residual_m3=float(ledger["residual_m3"]),
        steps=int(steps), overflowing_steps=overflowing_steps,
        coupling="one_way_sequential_level_pool_at_existing_solver_substeps_no_lake_backwater",
        initial_condition="stage = sill - %.2f m (declared scenario initial state)" % INITIAL_STAGE_BELOW_SILL_M)
    report["water"]["domain_total"] = dict(
        initial_m3=domain_initial, input_m3=domain_input,
        export_m3=domain_export, final_m3=domain_final,
        residual_m3=domain_initial + domain_input - domain_export - domain_final,
        components=dict(channel_initial_m3=channel_water["initial_m3"],
                        lake_initial_m3=ledger["initial_m3"],
                        channel_local_export_to_lake_m3=channel_water["outlet_export_m3"],
                        lake_spill_export_m3=ledger["spill_m3"],
                        channel_final_m3=channel_water["final_storage_m3"],
                        lake_final_m3=ledger["final_m3"]),
        interpretation="reach open outflow is routed into the lake; only the lake spill leaves the modelled basin")
    report["solid"]["delivered_to_lake_m3"] = channel_solid["outlet_export_m3"]
    report["solid"]["lake_bed_deposition_modelled"] = False
    bed_state = np.asarray(arrays["node_bed_m"], np.float64)
    change = bed_state[-1] - bed_state[0]
    report["bed"].update(dict(per_node_change_m=change.tolist(),
                              start_of_record_m=bed_state[0].tolist(),
                              end_of_record_m=bed_state[-1].tolist(),
                              node_count=int(change.size)))
    report["reach"] = dict(node_count=int(len(selection["node_xz_m"])),
        full_basin_cell_count=int(selection["full_basin_cell_count"]),
        refused_d8_edges=int(selection["refused_d8_edges"]),
        declared_upstream_edges=len(selection["truncated_upstream_edges"]),
        owning_cores=selection["owning_cores"],
        cross_core_edges=selection["cross_core_edges"],
        cross_core_edge_detail=selection["cross_core_edge_detail"],
        confluences=selection["confluence_nodes"],
        width_m=[float(min(selection["node_width_m"])), float(max(selection["node_width_m"]))],
        width_law=selection["width_law"],
        truncated_upstream_edges=[dict(from_xz_m=e["from_xz_m"], to_xz_m=e["to_xz_m"],
                                      omitted_cell_count=e["omitted_cell_count"],
                                      peak_q_m3_s=float(max(e["q_m3_s"]))) for e in
                                 selection["truncated_upstream_edges"]],
        bundle_identity_sha256=bundle_identity)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    plot_planform(output, selection, definition, lake_run)
    plot_lake(output, lake_run, definition)
    write_markdown(output, report)
    summary = dict(nodes=report["reach"]["node_count"],
        owning_cores=report["reach"]["owning_cores"],
        cross_core_edges=report["reach"]["cross_core_edges"],
        water=report["water"]["domain_total"], lake=report["lake"])
    return summary


def plot_planform(output, selection, definition, lake_run):
    import matplotlib.pyplot as plt
    node_xz = np.array(selection["node_xz_m"], np.float64)
    receiver = np.array([-1] * len(node_xz), np.int64)
    widths = np.array(selection["node_width_m"], np.float64)
    area = np.array(selection["node_contributing_area_m2"], np.float64)
    cells = np.array(selection["node_cell_ids"], np.int64)
    flat_receiver = np.array(selection["original_receiver_flat_ids"], np.int64)
    by_cell = {int(cell): index for index, cell in enumerate(cells)}
    for index, target in enumerate(flat_receiver):
        receiver[index] = by_cell.get(int(target), -1)
    regions = selection["node_region_ids"]
    terrain = np.load(output / "source-terrain-and-forcing.npz", allow_pickle=False)
    height = np.asarray(terrain["height_m"], np.float64)
    x0, z0 = [float(value) for value in terrain["origin_xz_m"]]
    spacing = float(selection["coarse_terrain_spacing_m"])
    core = float(selection["core_span_m"])
    edge_x = x0 + spacing * np.arange(height.shape[1])
    edge_z = z0 + spacing * np.arange(height.shape[0])
    ex = np.r_[edge_x - spacing / 2., edge_x[-1] + spacing / 2.]
    ez = np.r_[edge_z - spacing / 2., edge_z[-1] + spacing / 2.]
    fig = plt.figure(figsize=(21, 12))
    grid = fig.add_gridspec(3, 2, width_ratios=[1.45, 1.])
    ax = fig.add_subplot(grid[:, 0])
    mesh = ax.pcolormesh(ex, ez, height, cmap="Greys", shading="flat", alpha=.55)
    fig.colorbar(mesh, ax=ax, shrink=.55, label="Coarse source elevation (m)")
    palette = {"0:0": "#1f77b4", "0:1": "#d62728", "1:0": "#2ca02c", "1:1": "#9467bd"}
    for index, (x, z) in enumerate(node_xz):
        ax.add_patch(plt.Rectangle((x - spacing / 2., z - spacing / 2.), spacing, spacing,
                                   facecolor=palette.get(regions[index], "#888888"),
                                   alpha=.10, edgecolor="none", zorder=1))
    lo = np.floor(min(node_xz[:, 0].min(), node_xz[:, 1].min()) / core)
    hi = np.ceil(max(node_xz[:, 0].max(), node_xz[:, 1].max()) / core)
    for line in range(int(lo), int(hi) + 1):
        ax.axvline(line * core, color="#444444", ls="--", lw=1.2, zorder=2)
        ax.axhline(line * core, color="#444444", ls="--", lw=1.2, zorder=2)
    for index, target in enumerate(receiver):
        if target < 0:
            continue
        colour = palette.get(regions[index], "#888888")
        ax.plot(node_xz[[index, target], 0], node_xz[[index, target], 1], color=colour,
                lw=max(1.2, 7.0 * widths[index] / widths.max()), solid_capstyle="round", zorder=3)
    donors = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    for index, (x, z) in enumerate(node_xz):
        if donors[index] >= 2:
            ax.scatter(x, z, s=110, facecolor="white", edgecolor="k", zorder=5)
    ax.scatter(node_xz[:, 0], node_xz[:, 1], c="k", s=22, zorder=6)
    for index, (x, z) in enumerate(node_xz):
        ax.annotate("%d\n%.1fx" % (index, area[index] / 1e8), (x, z), textcoords="offset points",
                    xytext=(6, 5), fontsize=7, zorder=7)
    terminal = int(selection["terminal_node_index"])
    ax.scatter(node_xz[terminal, 0], node_xz[terminal, 1], s=420, marker="s",
               facecolor="#1f6fb4", edgecolor="navy", alpha=.75, zorder=8,
               label="endorheic lake cell (level-pool store)")
    sill = definition["lake"]["primary_target_xz_m"]
    ax.annotate("", xy=sill, xytext=node_xz[terminal],
                arrowprops=dict(arrowstyle="-|>", color="navy", lw=2.4), zorder=9)
    ax.annotate("sill overflow\n%.1f m a.s.l." % definition["lake"]["sill_stage_m"], sill,
                textcoords="offset points", xytext=(10, -18), fontsize=9, color="navy", zorder=9)
    for edge in selection["truncated_upstream_edges"]:
        ax.scatter(*edge["from_xz_m"], marker="X", s=120, c="darkorange", zorder=9)
        ax.annotate("declared boundary\n%.0f cells" % edge["omitted_cell_count"],
                    edge["from_xz_m"], textcoords="offset points", xytext=(8, -6),
                    fontsize=8, color="darkorange", zorder=9)
    ax.set(xlabel="World X (m)", ylabel="World Z (m)",
           title="Full seed-20261020 reach: %d nodes, %d owning cores, %d cross-core edges\n"
                 "line width = bank width, cell tint = owning core, numbers = node / contributing area (10^8 m2)"
                 % (len(node_xz), len(set(regions)), selection["cross_core_edges"]))
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.legend(loc="lower right", fontsize=9)
    stem = [terminal]
    while True:
        upstream = np.flatnonzero(receiver == stem[-1])
        if upstream.size == 0:
            break
        stem.append(int(upstream[np.argmax(area[upstream])]))
    stem = np.array(stem[::-1])
    chainage = np.r_[0., np.cumsum(np.linalg.norm(np.diff(node_xz[stem], axis=0), axis=1))] / 1000.
    ax_b = fig.add_subplot(grid[0, 1])
    ax_b.loglog(area / 1e6, widths, "o", color="#1f77b4", label="nodes")
    ax_b.loglog(area / 1e6, widths, color="#1f77b4", alpha=.35)
    ax_b.set(xlabel="Contributing area (km2)", ylabel="Bank width (m)",
             title="Width law W = clip(800*(Q/Q_cell)^0.5, 800, 3200); b=.5")
    ax_b.grid(True, which="both", alpha=.3)
    ax_w = fig.add_subplot(grid[1, 1])
    ax_w.plot(chainage, widths[stem], "-o", color="#2ca02c")
    ax_w.set(xlabel="Stem chainage (km)", ylabel="Bank width (m)",
             title="Width along the main stem (heads left, lake outlet right)")
    ax_w.grid(alpha=.3)
    ax_p = fig.add_subplot(grid[2, 1])
    ax_p.plot(chainage, np.array(selection["node_bed_m"])[stem], "-o", color="#8c564b")
    ax_p.set(xlabel="Stem chainage (km)", ylabel="Carved bed (m)",
             title="Carved bed along the main stem")
    ax_p.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(output / "reach-planform.png", dpi=150)
    plt.close(fig)
    terrain.close()


def plot_lake(output, lake_run, definition):
    import matplotlib.pyplot as plt
    hours = lake_run["time_edges_seconds"] / 3600.
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    axes[0].plot(hours, lake_run["stage_m"], color="#1f6fb4", lw=2, label="lake stage")
    axes[0].axhline(definition["lake"]["sill_stage_m"], color="navy", ls="--",
                    label="primary sill %.2f m" % definition["lake"]["sill_stage_m"])
    if definition["secondary_sill"]:
        axes[0].axhline(definition["secondary_sill"]["stage_m"], color="gray", ls=":",
                        label="secondary saddle %.2f m" % definition["secondary_sill"]["stage_m"])
    axes[0].axhline(definition["lake"]["bed_elevation_m"][0], color="k", ls="-", lw=.8,
                    label="lake bed %.2f m" % definition["lake"]["bed_elevation_m"][0])
    axes[0].set(ylabel="Stage (m)", title="Endorheic lake: level-pool storage and sill overflow")
    axes[0].legend(fontsize=9); axes[0].grid(alpha=.3)
    mid_hours = 0.5 * (lake_run["time_edges_seconds"][:-1] + lake_run["time_edges_seconds"][1:]) / 3600.
    axes[1].plot(mid_hours, lake_run["inflow_volume_m3"] / lake_run["dt_seconds"], color="#d62728",
                 label="channel terminal delivered to lake (m3/s)")
    spill_q = lake_run["spill_volume_m3"].sum(axis=1) / lake_run["dt_seconds"]
    axes[1].plot(mid_hours, spill_q, color="navy", label="sill spill out of the basin (m3/s)")
    axes[1].set(xlabel="Physical hours (substeps of the existing solvent, <=30 s)",
                ylabel="Discharge (m3/s)")
    axes[1].legend(fontsize=9); axes[1].grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(output / "lake-overflow.png", dpi=150)
    plt.close(fig)


def write_markdown(output, report):
    water, solid, lake = report["water"], report["solid"], report["lake"]
    total = water["domain_total"]
    bed = report["bed"]
    reach = report["reach"]
    selection = json.loads((output / "source-selection.json").read_text(encoding="utf-8"))
    receiver = np.array([-1] * len(selection["node_xz_m"]), np.int64)
    cells = np.array(selection["node_cell_ids"], np.int64)
    by_cell = {int(cell): index for index, cell in enumerate(cells)}
    for index, target in enumerate(selection["original_receiver_flat_ids"]):
        receiver[index] = by_cell.get(int(target), -1)
    area = np.array(selection["node_contributing_area_m2"], np.float64)
    stem = [int(selection["terminal_node_index"])]
    while True:
        upstream = np.flatnonzero(receiver == stem[-1])
        if upstream.size == 0:
            break
        stem.append(int(upstream[np.argmax(area[upstream])]))
    stem = stem[::-1]
    lines = ["# 完整真实河段（多 owning core）与末端内流湖泊运行结果", "",
        "场景: `%s`" % report["scene"], "",
        "- 节点 **%d**，跨 **%d** 个真实 owning core %s，跨 core 单元边 **%d** 条，汇流点 %d 个"
        % (reach["node_count"], len(reach["owning_cores"]), reach["owning_cores"],
           reach["cross_core_edges"], len(reach["confluences"])),
        "- 流域完整粗格 **%d** 个；canonical 切槽拒绝 **%d** 条 D8 边，因此截断出 **%d** 条显式上游边界情景"
        % (reach["full_basin_cell_count"], reach["refused_d8_edges"],
           reach["declared_upstream_edges"]),
        "- 河宽 **%.0f–%.0f m**（%s）" % (reach["width_m"][0], reach["width_m"][1], reach["width_law"]),
        "- 物理秒 **%.0f s**（%.0f h）；水量/固体/湖泊账目见下"
        % (report["physical_seconds"], report["physical_seconds"] / 3600.), "",
        "## 水系结构（主槽自上游到头）", "",
        "```",
        "%-5s %-12s %-12s %8s %8s %9s %8s" % ("node", "x_m", "z_m", "A_km2", "Q_m3s", "bed_m", "width_m")]
    for index in stem:
        lines.append("%-5d %-12.0f %-12.0f %8.1f %8.3f %9.2f %8.1f" % (
            index, selection["node_xz_m"][index][0], selection["node_xz_m"][index][1],
            area[index] / 1e6, selection["node_design_q_m3_s"][index],
            selection["node_bed_m"][index], selection["node_width_m"][index]))
    lines += ["```", "",
        "汇流点节点序号: %s；跨 core 边: %s" % (reach["confluences"],
            [(item["donor"], item["receiver"], item["from_region"], item["to_region"])
             for item in reach["cross_core_edge_detail"]]), "",
        "被截断上游边（显式边界情景）:", ""]
    for edge in reach["truncated_upstream_edges"]:
        lines.append("- %s -> %s，省略 %d 个粗格，情景峰值 %.2f m3/s"
                     % (edge["from_xz_m"], edge["to_xz_m"], edge["omitted_cell_count"],
                        edge["peak_q_m3_s"]))
    lines += ["", "## 水量（全域合并）", "", "```json",
        json.dumps(dict(total=total, channel=water), indent=2), "```", "",
        "## 固体（终节点出口 = 送入湖泊，未在湖床记账）", "", "```json",
        json.dumps(solid, indent=2), "```", "",
        "## 湖泊", "",
        "- 水位 %.3f → %.3f m（鞍部 %.3f m，最高 %.3f m，湖底 %.3f m）"
        % (lake["initial_stage_m"], lake["final_stage_m"], lake["sill_stage_m"],
           lake["max_stage_m"], lake["bed_elevation_m"]),
        "- 蓄水 %.6e → %.6e m3（容量 %.6e m3）；入湖 %.6e m3，溢流出境 %.6e m3"
        % (lake["initial_volume_m3"], lake["final_volume_m3"], lake["capacity_m3"],
           lake["inflow_m3"], lake["spill_m3"]),
        "- 溢流子步 %d / %d；各溢流口 %.6e / %.6e m3；湖账残差 %.3e m3"
        % (lake["overflowing_steps"], lake["steps"], lake["spill_by_outlet_m3"][0],
           lake["spill_by_outlet_m3"][1], lake["residual_m3"]), "",
        "```json", json.dumps(lake, indent=2), "```", "",
        "## 节点床变", "",
        "- 范围 **%.4e – %.4e m**，切槽体积 %.4e m3" % (bed.get("min_change_m", float("nan")),
                                                bed.get("max_change_m", float("nan")),
                                                bed.get("cut_volume_m3", float("nan"))),
        "", "## 局限", ""]
    lines += ["- " + item for item in report["limitations"]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--hours", type=int, default=72)
    args = parser.parse_args()
    started = time.perf_counter()
    report = run(args.output,
        scene_builder=lambda path: make_full_reach_scene(path, hours=args.hours),
        material=MaterialParameters(sediment_erodibility_m_s_pa=1e-10,
            rock_erodibility_m_s_pa=1e-12, transport_coefficient=1e-5,
            settling_velocity_m_s=.0001,
            provenance="explicit real coarse reach illustrative material"),
        channel_config=ChannelConfig(max_dt_seconds=30.),
        sediment_config=SedimentConfig(max_dt_seconds=30., max_bed_change_m=.01),
        dynamics=couple_nodal_reach, saver=save_nodal_reach,
        reach_config=FullReachConfig())
    summary = finish_full_reach(args.output)
    summary["wall_seconds"] = time.perf_counter() - started
    print(json.dumps(summary, indent=2), flush=True)
