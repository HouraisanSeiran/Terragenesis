"""Whole-domain original TD routing, forcing and auditable river generation."""
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import time
import numpy as np
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.channel_geometry import GeometryConfig, _footprint
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.channel_geometry import NetworkGeometryConfig, build_network_geometry_plan, save_network_geometry_plan
from terrain_pipeline.climate_forcing import grid_rainfall
from terrain_pipeline.channel_geometry import _profile
from terrain_pipeline.channel_geometry import EPSILON_SLOPE_M_PER_M, _profile_cut, _profile_max_cut_per_edge
from terrain_pipeline.channel_geometry import _metric_channel_geometry_sample as _sample, _route_crossings, _mesh_volume, _segment_points
from terrain_pipeline.channel_geometry import _sparse_cells, _sparse_mesh, _sparse_slope, _sparse_ports
from terrain_pipeline.channel_geometry import _close_bed
from terrain_pipeline.channel_geometry import _anchors, _turn_energy
from terrain_pipeline.channel_geometry import enforce_turn_ceiling, shape_centerline, turn_summary
from terrain_pipeline.channel_geometry import repair_budget_centerline
from terrain_pipeline.channel_geometry import repair_local_conflicts
from terrain_pipeline.channel_geometry import assess_local_bed
from terrain_pipeline.channel_geometry import evaluate_necessary_budget, controlling_upstream_nodes, budget_hotspot_targets
from types import SimpleNamespace
from scipy.spatial import cKDTree
from terrain_pipeline.common_infra import BoundaryGrid, RoutingGraph
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import route_graph as route_graph
from terrain_pipeline.common_infra import identity

@dataclass(frozen=True)
class GeneratedRiverConfig:
    min_contributing_area_m2: float = 1000000.0
    runoff_coefficient: float = 0.5
    fine_spacing_m: float = 1.0
    max_cut_m: float = 4.0
    centerline_iterations: int = 24
    centerline_corridor_m: float = 30.0
    transverse_bottom_slope_m_per_m: float = 0.02

    def __post_init__(self):
        if not 0.0 < self.runoff_coefficient <= 1.0:
            raise ValueError('runoff coefficient must be in (0,1]')
        NetworkGeometryConfig(min_contributing_area_m2=self.min_contributing_area_m2)
        GeometryConfig(fine_spacing_m=self.fine_spacing_m, max_cut_m=self.max_cut_m)
        if type(self.centerline_iterations) is not int or not 0 <= self.centerline_iterations <= 100:
            raise ValueError('bounded centerline iteration count required')
        if not np.isfinite(self.centerline_corridor_m) or not 0.0 <= self.centerline_corridor_m <= 60.0:
            raise ValueError('centerline corridor must be finite and within 60m')
        if not np.isfinite(self.transverse_bottom_slope_m_per_m) or not 0.0 <= self.transverse_bottom_slope_m_per_m < 0.5:
            raise ValueError('transverse bottom slope must be finite and below 0.5m/m')

def selected_components(source_ids, target_ids):
    """Partition all selected edges by shared nodes, retaining each edge once."""
    incident = {}
    for index, (source, target) in enumerate(zip(source_ids, target_ids)):
        incident.setdefault(int(source), []).append(index)
        incident.setdefault(int(target), []).append(index)
    remaining = set(range(len(source_ids)))
    result = []
    while remaining:
        pending = [min(remaining)]
        members = []
        while pending:
            edge = pending.pop()
            if edge not in remaining:
                continue
            remaining.remove(edge)
            members.append(edge)
            for node in (source_ids[edge], target_ids[edge]):
                pending.extend(incident[int(node)])
        result.append(np.asarray(sorted(members), np.int64))
    return result

def spill_candidate(terrain, boundary, max_depth):
    """Bounded working-surface fill on the shared irregular graph."""
    if not terrain.valid_mask.all() or terrain.dx_m != terrain.dz_m:
        raise ValueError('spill candidate adapter requires a complete square-cell source')
    if not np.isfinite(max_depth) or max_depth <= 0.0:
        raise ValueError('positive finite max_depth required')
    mesh = grid_mesh(terrain.elevation_m.shape, x0_m=terrain.x0_m, z0_m=terrain.z0_m, dx_m=terrain.dx_m, dz_m=terrain.dz_m, world_seed=terrain.generation_seed if terrain.generation_seed is not None else 20261020)
    outlets = np.zeros(terrain.valid_mask.shape, bool)
    outlets[[0, -1], :] = True
    outlets[:, [0, -1]] = True
    while True:
        routed = route_graph(terrain.elevation_m, outlets, mesh)
        deep = routed.filled - terrain.elevation_m >= max_depth
        added = deep & ~outlets
        if not added.any():
            break
        outlets |= added
    work = routed.filled
    rec, order = (routed.receiver, routed.order)
    kinds = np.full(rec.size, 'interior', dtype='U24')
    terminal = rec < 0
    kinds[terminal] = 'lake_preserved'
    kinds[terminal & (boundary.kind.ravel() == 'unknown_boundary')] = 'unknown_boundary'
    sources = np.flatnonzero(rec >= 0)
    length, slope = (np.zeros(rec.size), np.zeros(rec.size))
    targets = rec[sources]
    length[sources] = np.hypot(mesh.node_x_m[targets] - mesh.node_x_m[sources], mesh.node_z_m[targets] - mesh.node_z_m[sources])
    slope[sources] = np.maximum(0.0, (work.ravel()[sources] - work.ravel()[targets]) / length[sources])
    lake_id = np.full(rec.size, -1, np.int64)
    for cell in order:
        lake_id[cell] = (cell if kinds[cell] == 'lake_preserved' else -1) if rec[cell] < 0 else lake_id[rec[cell]]
    graph = RoutingGraph(rec, order, terrain.valid_mask, length, slope, kinds, lake_id, terrain.identity_sha256, boundary.identity_sha256, policy='irregular_graph_bounded_fill_unresolved_perimeter_v1')
    metadata = dict(backend='irregular_graph', version='1', max_depth_m=max_depth, deep_pit_policy='cells at or above fill cap become explicit unresolved terminals; reroute until all fills are bounded', work_surface_only=True, queue_elevation_dtype='float64', original_boundary_identity_sha256=boundary.identity_sha256, unknown_perimeter_policy='working spill candidate only; discharge remains unknown_pending', maximum_fill_m=float((work - terrain.elevation_m).max()), filled_volume_m3=float(np.sum(work - terrain.elevation_m) * terrain.cell_area_m2))
    return (graph, work, metadata)

def prepare_network(registration, config=None, *, bounded_spills=False):
    config = config or GeneratedRiverConfig()
    terrain, boundary = (registration['terrain'], registration['boundary'])
    original_graph = route_diagnostic(terrain, boundary, flat_distance_strategy='metric_distance')
    graph = original_graph
    work = terrain.elevation_m
    spill_metadata = None
    if bounded_spills:
        graph, work, spill_metadata = spill_candidate(terrain, boundary, config.max_cut_m)
    plan = build_network_geometry_plan(terrain, graph, NetworkGeometryConfig(min_contributing_area_m2=config.min_contributing_area_m2))
    forcing, forcing_metadata = grid_rainfall(terrain.generation_seed, origin_xz_m=(terrain.x0_m, terrain.z0_m), shape_zx=terrain.elevation_m.shape, spacing_m=float(terrain.dx_m), time_edges_s=[0.0, 900.0])
    rainfall = forcing.rain_mm_h[0]
    local_q = rainfall * terrain.cell_area_m2 * config.runoff_coefficient / 1000.0 / 3600.0
    accumulated = accumulate_local_discharge(graph, local_q)
    q = accumulated['routed_q_m3_s'].ravel()
    arrays = dict(source_height_m=terrain.elevation_m, valid_mask=terrain.valid_mask, original_receiver=original_graph.receiver, original_outlet_kind=original_graph.outlet_kind, working_elevation_m=work, working_fill_depth_m=work - terrain.elevation_m, receiver=graph.receiver, order_downstream_first=graph.order_downstream_first, outlet_kind=graph.outlet_kind, edge_length_m=graph.edge_length_m, edge_slope=graph.edge_slope, terminal_owner=plan['arrays']['terminal_owner'], contributing_area_m2=plan['arrays']['contributing_area_m2'], rainfall_mm_h=rainfall, local_q_m3_s=local_q, routed_q_m3_s=accumulated['routed_q_m3_s'], selected_edge_source_ids=plan['arrays']['selected_edge_source_ids'], selected_edge_target_ids=plan['arrays']['selected_edge_target_ids'], width_m=np.maximum(6.0, 4.0 * np.sqrt(q)), base_depth_m=np.maximum(0.25, 0.2 * np.cbrt(q)))
    original_plan = build_network_geometry_plan(terrain, original_graph, NetworkGeometryConfig(min_contributing_area_m2=config.min_contributing_area_m2))
    arrays['baseline_selected_edge_source_ids'] = original_plan['arrays']['selected_edge_source_ids']
    arrays['baseline_selected_edge_target_ids'] = original_plan['arrays']['selected_edge_target_ids']
    components = selected_components(arrays['selected_edge_source_ids'], arrays['selected_edge_target_ids'])
    component_id = np.empty(len(arrays['selected_edge_source_ids']), np.int64)
    for index, edges in enumerate(components):
        component_id[edges] = index
    arrays['selected_component_id'] = component_id
    owner = arrays['terminal_owner'].reshape(terrain.elevation_m.shape)
    corridor = terrain.valid_mask
    lake = np.zeros(owner.shape, bool)
    failures = []
    for source, target in zip(arrays['selected_edge_source_ids'], arrays['selected_edge_target_ids']):
        ids = np.array([source, target], np.int64)
        receiver = np.array([1, -1], np.int64)
        points = np.column_stack((terrain.x0_m + ids % owner.shape[1] * terrain.dx_m, terrain.z0_m + ids // owner.shape[1] * terrain.dz_m))
        checks = {}
        for name, action in (('footprint', lambda: _footprint(points, receiver, arrays['width_m'][ids], np.full(2, config.max_cut_m), terrain, owner, corridor, lake, arrays['terminal_owner'][ids], config.fine_spacing_m)), ('profile', lambda: _profile(points, receiver, arrays['base_depth_m'][ids], terrain, config.max_cut_m))):
            try:
                action()
                checks[name] = 'pass'
            except ValueError as error:
                checks[name] = str(error)
        failures.append(checks)
    terminals = np.flatnonzero(terrain.valid_mask.ravel() & (graph.receiver < 0))
    selected_terminal = np.unique(arrays['terminal_owner'][arrays['selected_edge_source_ids']])
    selected_mask = np.zeros(graph.receiver.size, bool)
    selected_mask[arrays['selected_edge_source_ids']] = True
    downstream_length = np.zeros(graph.receiver.size)
    for cell in graph.order_downstream_first:
        if selected_mask[cell]:
            downstream_length[cell] = graph.edge_length_m[cell] + downstream_length[graph.receiver[cell]]
    metadata = dict(schema='td-generated-river-network-v1', config=asdict(config), original_bed_baseline=dict(selected_edges=len(original_plan['arrays']['selected_edge_source_ids']), terminal_count=int(np.sum(original_graph.receiver < 0)), terminal_kinds=dict(Counter(original_graph.outlet_kind[original_graph.receiver < 0].tolist())), maximum_terminal_catchment_m2=float(original_plan['arrays']['contributing_area_m2'][original_graph.receiver < 0].max()), closed_catchment_area_fraction=float(np.mean(original_graph.outlet_kind[original_plan['arrays']['terminal_owner']] == 'lake_preserved'))), terrain_metadata=terrain.metadata(), source_registration=registration['metadata'], source_plan_identity_sha256=plan['identity_sha256'], graph_identity_sha256=graph.identity_sha256, forcing=forcing_metadata, discharge_policy='instantaneous diagnostic mean 0-900s rainfall; no travel time or storage', spill_candidate=spill_metadata, section_policy='noise-derived discharge; width/depth coefficients uncalibrated engineering assumptions', terminal_policy='lake_preserved denotes original-bed internal sink; no lake surface extent inferred', water_budget={key: value for key, value in accumulated.items() if not isinstance(value, np.ndarray)}, selected_edges=len(arrays['selected_edge_source_ids']), component_count=len(components), component_edge_counts=[len(edges) for edges in components], terminal_count=len(terminals), terminal_kinds=dict(Counter(graph.outlet_kind[terminals].tolist())), selected_terminal_count=len(selected_terminal), maximum_terminal_catchment_m2=float(arrays['contributing_area_m2'][terminals].max()), closed_catchment_area_fraction=float(np.mean(graph.outlet_kind[arrays['terminal_owner']] == 'lake_preserved')), maximum_selected_path_length_m=float(downstream_length.max()), preflight_counts={name: dict(Counter((row[name] for row in failures))) for name in ('footprint', 'profile')}, preflight_edge_records=failures, natural_outlet_verified=False, hydraulic_ready=False, publishable=False)
    return (arrays, metadata, plan, components)

def write_preflight(output, registration, config=None, *, bounded_spills=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    arrays, metadata, plan, components = prepare_network(registration, config, bounded_spills=bounded_spills)
    arrays['selected_edge_status'] = np.full(len(arrays['selected_edge_source_ids']), 'geometry_pending', dtype='U32')
    np.savez_compressed(output / 'network.npz', **arrays)
    save_network_geometry_plan(output / 'network-plan.npz', plan)
    metadata['network'] = dict(path='network.npz', sha256=file_sha256(output / 'network.npz'))
    publish_bytes(output / 'report.json', json.dumps(metadata, indent=2, allow_nan=False).encode())
    return metadata

def shared_node_depths(terrain, ids, receiver, depth, max_cut):
    """Shared endpoint depths of the continuous whole-component bed envelope."""
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    _, result = _continuous_profile(points, receiver, depth, terrain, max_cut, 1.0)
    return (points, result)

def _continuous_profile(points, receiver, design_depth, terrain, max_cut, spacing):
    """Highest feasible running-min bed, with one height at each confluence.

    Quadratic extrema are included exactly. Dense knots bound the represented
    piecewise-linear profile, whose continuous maximum cut is checked below.
    """
    node_source = _sample(terrain.elevation_m, points, terrain)[0]
    node_bed = node_source - design_depth
    donors = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    pending = [int(i) for i in np.flatnonzero(donors == 0)]
    profiles = {}
    for i in pending:
        j = int(receiver[i])
        if j < 0:
            continue
        a, b = (points[i], points[j])
        length = float(np.linalg.norm(b - a))
        samples, native = _segment_points(a, b, terrain)
        extra = []
        for t0, t1 in zip(native[:-1], native[1:]):
            ts = np.array([t0, (t0 + t1) / 2.0, t1])
            h = _sample(terrain.elevation_m, a + ts[:, None] * (b - a), terrain)[0]
            span = t1 - t0
            quadratic = 2.0 * (h[0] + h[2] - 2.0 * h[1]) / span ** 2
            linear = (h[2] - h[0]) / span - quadratic * span - (design_depth[j] - design_depth[i]) + EPSILON_SLOPE_M_PER_M * length
            stationary = t0 - linear / (2.0 * quadratic) if abs(quadratic) > 1e-14 else -1.0
            if t0 < stationary < t1:
                extra.append(stationary)
        knots = np.unique(np.r_[native, extra, np.linspace(0.0, 1.0, max(2, int(np.ceil(length / spacing)) + 1))])
        source = _sample(terrain.elevation_m, a + knots[:, None] * (b - a), terrain)[0]
        upper = source - ((1.0 - knots) * design_depth[i] + knots * design_depth[j]) + EPSILON_SLOPE_M_PER_M * length * knots
        bed = np.minimum.accumulate(np.minimum(upper, node_bed[i])) - EPSILON_SLOPE_M_PER_M * length * knots
        node_bed[j] = min(node_bed[j], bed[-1])
        profiles[i] = [knots, source, bed]
        donors[j] -= 1
        if donors[j] == 0:
            pending.append(j)
    offsets = [0]
    parameters = []
    sources = []
    beds = []
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        knots, source, bed = profiles[i]
        bed[-1] = node_bed[j]
        parameters.extend(knots)
        sources.extend(source)
        beds.extend(bed)
        offsets.append(len(parameters))
    profile = (np.asarray(offsets, np.int64), np.asarray(parameters, np.float64), np.asarray(sources, np.float64), np.asarray(beds, np.float64))
    maximum = _maximum_profile_cut(points, receiver, profile, terrain)
    if maximum.size and maximum.max() > max_cut + 1e-09:
        raise ValueError(f'continuous shared-bed envelope incision {maximum.max():.9g}m exceeds {max_cut:g}m budget')
    return (profile, node_source - node_bed)

def _maximum_profile_cut(points, receiver, profile, terrain):
    """Vectorized exact quadratic-source minus linear-bed maximum per edge."""
    maximum = []
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        lo, hi = profile[0][edge:edge + 2]
        t, source, bed = [field[lo:hi] for field in profile[1:]]
        span = np.diff(t)
        middle = _sample(terrain.elevation_m, points[i] + ((t[:-1] + t[1:]) / 2.0)[:, None] * (points[j] - points[i]), terrain)[0]
        quadratic = 2.0 * (source[:-1] + source[1:] - 2.0 * middle) / span ** 2
        derivative = np.diff(source) / span - quadratic * span - np.diff(bed) / span
        position = np.divide(-derivative, 2.0 * quadratic, out=np.zeros_like(span), where=np.abs(quadratic) > 1e-14)
        valid = (quadratic < -1e-14) & (position > 0.0) & (position < span)
        amount = float(np.max(source - bed))
        if np.any(valid):
            amount = max(amount, float(np.max((source[:-1] - bed[:-1] + derivative * position + quadratic * position ** 2)[valid])))
        maximum.append(max(0.0, amount))
        edge += 1
    return np.asarray(maximum, np.float64)

def _local_route_crossings(points, receiver):
    from terrain_pipeline.channel_geometry import _segments_intersect, _metric_channel_geometry_orientation as _orientation
    edges = np.asarray([(i, int(j)) for i, j in enumerate(receiver) if j >= 0], np.int64)
    if not len(edges):
        return
    midpoint = (points[edges[:, 0]] + points[edges[:, 1]]) / 2.0
    length = np.linalg.norm(points[edges[:, 1]] - points[edges[:, 0]], axis=1)
    pairs = cKDTree(midpoint).query_pairs(float(length.max()))
    for first, second in pairs:
        i, j = edges[first]
        k, l = edges[second]
        shared = {i, j} & {k, l}
        if shared:
            common = points[next(iter(shared))]
            a = points[j if i in shared else i] - common
            b = points[l if k in shared else k] - common
            if abs(_orientation(np.zeros(2), a, b)) <= 1e-10 and np.dot(a, b) > 0.0:
                raise ValueError('adjacent centerline backtracking')
        elif _segments_intersect(points[i], points[j], points[k], points[l]):
            raise ValueError('nonadjacent centerline crossing')

def _clipped_ports(points, receiver, width, profile, cells, vertices, triangles, cut, spacing, terrain):
    from terrain_pipeline.channel_geometry import _barycentric
    from terrain_pipeline.channel_geometry import _cell_at_point
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    high = origin + np.array([(terrain.elevation_m.shape[1] - 1) * terrain.dx_m, (terrain.elevation_m.shape[0] - 1) * terrain.dz_m])
    edges = np.asarray([(i, int(j)) for i, j in enumerate(receiver) if j >= 0], np.int64)
    middle = np.empty((len(edges), 2))
    positions = np.empty((len(edges), 4, 2))
    faces = np.empty((len(edges), 4), np.int64)
    weights = np.empty((len(edges), 4, 3))
    values = np.empty((len(edges), 4))
    requested_positions = np.empty((len(edges), 4, 2))
    support = np.full((len(edges), 4), 'represented', dtype='U32')
    for edge, (i, j) in enumerate(edges):
        center = (points[i] + points[j]) / 2.0
        delta = points[j] - points[i]
        normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
        half = (width[i] + width[j]) / 4.0
        lo, hi = profile[0][edge:edge + 2]
        bank = 2.0 * np.interp(0.5, profile[1][lo:hi], profile[2][lo:hi] - profile[3][lo:hi])
        middle[edge] = center
        for k, distance in enumerate((-half - bank, -half, half, half + bank)):
            requested = center + distance * normal
            allowed_low, allowed_high = (-np.inf, np.inf)
            for axis in (0, 1):
                if abs(normal[axis]) > 1e-15:
                    limits = sorted(((origin[axis] - center[axis]) / normal[axis], (high[axis] - center[axis]) / normal[axis]))
                    allowed_low = max(allowed_low, limits[0])
                    allowed_high = min(allowed_high, limits[1])
            position = center + np.clip(distance, allowed_low, allowed_high) * normal
            requested_positions[edge, k] = requested
            if np.any(np.abs(requested - position) > 1e-09):
                support[edge, k] = 'clipped_unknown_exterior'
            positions[edge, k] = position
            key = _cell_at_point(position, lookup, origin, spacing)
            cell = lookup[key]
            ids, bary = _barycentric(position, cell, vertices, triangles)
            face = next((face for face in range(4 * cell, 4 * cell + 4) if np.array_equal(triangles[face], ids)))
            faces[edge, k] = face
            weights[edge, k] = bary
            values[edge, k] = bary @ cut[ids]
    return ((edges, middle, positions, faces, weights, values), support, requested_positions)

def component_centerline(terrain, ids, receiver, width, depth, config, *, reference_points=None, progress=None):
    cols = terrain.elevation_m.shape[1]
    original = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    certify = lambda candidate: _continuous_profile(candidate, receiver, depth, terrain, config.max_cut_m, config.fine_spacing_m)[0]
    if progress is not None:
        progress('centerline_search_and_profile_certificate')
    points, policy = shape_centerline(original, receiver, terrain, iterations=config.centerline_iterations, corridor_m=config.centerline_corridor_m, validate=lambda candidate: _local_route_crossings(candidate, receiver), certify=certify, reference_points=reference_points)
    policy.pop('path_search_seconds')
    policy.pop('total_path_seconds')
    anchors = _anchors(receiver)
    source_height = _sample(terrain.elevation_m, original, terrain)[0]

    def validate(candidate):
        if np.any(np.linalg.norm(candidate - original, axis=1) > config.centerline_corridor_m + 1e-08):
            raise ValueError('original centerline corridor exceeded')
        if not np.array_equal(candidate[anchors], original[anchors]):
            raise ValueError('fixed centerline anchor moved')
        sampled, _ = _sample(terrain.elevation_m, candidate, terrain)
        if np.any(sampled > source_height + 0.5 + 1e-09):
            raise ValueError('original centerline source rise exceeded')
        enforce_turn_ceiling(candidate, receiver, policy['effective_turn_ceiling_degrees'])
        _local_route_crossings(candidate, receiver)
    if progress is not None:
        progress('transverse_budget_hotspots_and_controlling_upstream')
    points, profile, budget_policy = repair_budget_centerline(points, receiver, certify(points), max_cut_m=config.max_cut_m, evaluate=lambda candidate, profile, focus: evaluate_necessary_budget(candidate, receiver, width, profile, terrain, ids, config.fine_spacing_m, config.max_cut_m, config.transverse_bottom_slope_m_per_m, focus), validate=validate, certify=certify, causal_nodes=lambda candidate, profile, evaluation: controlling_upstream_nodes(candidate, receiver, depth, profile, budget_hotspot_targets(evaluation), EPSILON_SLOPE_M_PER_M), source_height=lambda point: _sample(terrain.elevation_m, np.array([point]), terrain)[0][0])
    if budget_policy['status'] != 'necessary_bounds_clear':
        raise ValueError('transverse necessary budget conflicts remain before bed solve: ' + json.dumps(dict(maxima=budget_policy['final_maxima'], counts=budget_policy['final_counts'])))
    if progress is not None:
        progress('original_row_local_bed_conflicts_and_route_repair')
    points, profile, local_policy = repair_local_conflicts(terrain, points, receiver, width, depth, profile, ids, validate=validate, certify=certify, assess=assess_local_bed, spacing=config.fine_spacing_m, max_cut=config.max_cut_m, bottom_slope=config.transverse_bottom_slope_m_per_m, minimum_slope=EPSILON_SLOPE_M_PER_M)
    if local_policy['status'] in ('local_conflicts_remain', 'local_conflict_without_dual_route_witness'):
        raise ValueError('original-row local bed conflicts remain before full bed solve: ' + json.dumps(dict(status=local_policy['status'], attempted_candidates=local_policy['attempted_candidates'])))
    final_budget = evaluate_necessary_budget(points, receiver, width, profile, terrain, ids, config.fine_spacing_m, config.max_cut_m, config.transverse_bottom_slope_m_per_m)
    budget_policy['necessary_repair_stage_final_maxima'] = budget_policy['final_maxima']
    budget_policy['necessary_repair_stage_final_counts'] = budget_policy['final_counts']
    budget_policy['final_maxima'] = final_budget['maxima']
    budget_policy['final_counts'] = final_budget['counts']
    if sum(final_budget['counts']):
        raise ValueError('final route has transverse necessary budget conflicts')
    policy['budget_hotspot_repair'] = budget_policy
    policy['local_original_row_bed_repair'] = local_policy
    policy['final_turns'] = turn_summary(points, receiver)
    policy['final_mean_source_height_m'] = float(_sample(terrain.elevation_m, points, terrain)[0].mean())
    return (points, profile, policy)

def component_geometry(terrain, ids, receiver, width, depth, config, *, reference_points=None, progress=None):
    """Use existing fan4 geometry and LP with explicit same-source support.

    The source's terminal labels describe drainage, not impermeable stencil walls.
    The mesh is clipped to the known domain; no exterior bank is represented.
    """
    design_depth = depth.copy()
    cols = terrain.elevation_m.shape[1]
    original_points = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    anchors = _anchors(receiver)
    points, profile, centerline_policy = component_centerline(terrain, ids, receiver, width, design_depth, config, reference_points=reference_points, progress=progress)
    _local_route_crossings(points, receiver)
    profile, depth = _continuous_profile(points, receiver, design_depth, terrain, config.max_cut_m, config.fine_spacing_m)
    options = SimpleNamespace(fine_spacing_m=config.fine_spacing_m, max_vertices=8000000, max_cut_m=config.max_cut_m)
    from terrain_pipeline.channel_geometry import build_design_geometry
    if progress is not None:
        progress('sparse_mesh_and_physical_bed_solve')
    cells, vertices, triangles, source, source_cells, cut, closure, design_lower, design_upper, source_padding, zero_boundary = build_design_geometry(points, receiver, width, design_depth, profile, terrain, config.fine_spacing_m, config.max_cut_m, EPSILON_SLOPE_M_PER_M, transverse_bottom_slope=config.transverse_bottom_slope_m_per_m)
    if progress is not None:
        progress('saved_mesh_slope_certificate')
    _sparse_slope(points, receiver, cells, vertices, triangles, source - cut, config.fine_spacing_m, terrain)
    if progress is not None:
        progress('physical_cross_section_ports')
    ports, port_support, requested_ports = _clipped_ports(points, receiver, width, profile, cells, vertices, triangles, cut, config.fine_spacing_m, terrain)
    arrays = dict(source_node_cell_ids=ids, receiver=receiver, node_xz_m=points, original_node_xz_m=original_points, anchor_mask=anchors, source_height_m=terrain.elevation_m, source_valid_mask=terrain.valid_mask, width_m=width, base_depth_m=depth, design_base_depth_m=design_depth, design_minimum_cut_m=design_lower, design_maximum_cut_m=design_upper, source_interpolation_padding_m=source_padding, sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, source_elevation_m=source, source_cell_ids=source_cells, cut_depth_m=cut, bed_elevation_m=source - cut, profile_offsets=profile[0], profile_t=profile[1], profile_source_m=profile[2], profile_center_bed_m=profile[3], port_edge_node_indices=ports[0], port_xz_m=ports[1], port_profile_xz_m=ports[2], port_triangle_ids=ports[3], port_barycentric=ports[4], port_cut_depth_m=ports[5])
    arrays['port_support_status'] = port_support
    arrays['port_requested_profile_xz_m'] = requested_ports
    arrays['port_design_width_m'] = np.linalg.norm(requested_ports[:, 2] - requested_ports[:, 1], axis=1)
    arrays['port_actual_width_m'] = np.linalg.norm(ports[2][:, 2] - ports[2][:, 1], axis=1)
    arrays['port_complete_cross_section'] = np.all(port_support == 'represented', axis=1)
    metadata = dict(schema='td-generated-component-bed-v1', algorithm='terrain-local-original-row-budget-continuous-source-design-profile-fan4-v6', terrain_metadata=terrain.metadata(), source_identity_sha256=terrain.identity_sha256, config=asdict(config), cut_volume_m3=_mesh_volume(vertices, triangles, cut), maximum_cut_m=float(cut.max()), design_bed_policy=dict(bottom_triangle_guard_m=np.sqrt(2.0) * config.fine_spacing_m, support_guard_m=(np.sqrt(2.0) + 1.0) * config.fine_spacing_m, design_depth_policy='original network edge endpoint maximum', bank_slope=2.0, source_padding='aligned fan4 abs native mixed difference*h^2/(16 dx dz)', profile_constraint_policy='mesh triangle boundaries union all profile knots', cut_contract='original bilinear source upper cut bound; represented source lower bound outside design bottom', known_domain_boundary_cut_policy='clipped unresolved exterior; zero interior support boundary', transverse_bed_policy='actual solved center bed coupled across full bottom; bounded transverse bottom slope and bank ceiling relative to projected center', transverse_bottom_slope_m_per_m=config.transverse_bottom_slope_m_per_m, transverse_bank_horizontal_per_vertical=2.0, transverse_bottom_guard_m=np.sqrt(2.0) * config.fine_spacing_m, transverse_node_cap_policy='all incident unit-direction dot distances <= 1e-10m; actual node bed coupled', transverse_node_cap_dot_tolerance_m=1e-10), closure=closure, centerline_moved_nodes=int(np.count_nonzero(np.linalg.norm(points - original_points, axis=1) > 1e-09)), centerline_max_offset_m=float(np.linalg.norm(points - original_points, axis=1).max()), initial_turn_energy=_turn_energy(original_points, receiver), final_turn_energy=_turn_energy(points, receiver), centerline_policy=centerline_policy, minimum_bed_slope_m_per_m=EPSILON_SLOPE_M_PER_M, monotone_closure_policy='actual triangle-plane directional gradient in m/m; no short-span elevation subtraction', ownership_policy='known original terrain domain; routing terminal_owner retained separately', finite_domain_policy='mesh support clipped to known domain; exterior unresolved; no exterior volume charged', clipped_port_points=int(np.sum(port_support == 'clipped_unknown_exterior')), port_policy='original straight cross-section clipped along its normal to known rectangle; exterior requested points unsupported', divide_preservation_verified=False, natural_outlet_verified=False, hydraulic_ready=False, publishable=False)
    return dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))

def save_component_geometry(path, bundle):
    validate_component_geometry(bundle)
    np.savez_compressed(path, **bundle['arrays'], metadata=np.array(json.dumps(bundle['metadata'], sort_keys=True)), identity_sha256=np.array(bundle['identity_sha256']))

def validate_component_geometry(bundle):
    from terrain_pipeline.common_infra import TerrainGrid
    a, m = (bundle['arrays'], bundle['metadata'])
    if identity(a, m) != bundle['identity_sha256']:
        raise ValueError('component identity differs')
    terrain = TerrainGrid(a['source_height_m'], a['source_valid_mask'], **{key: value for key, value in m['terrain_metadata'].items() if key in TerrainGrid.__dataclass_fields__})
    if terrain.identity_sha256 != m['source_identity_sha256']:
        raise ValueError('component source differs')
    sampled = _sample(terrain.elevation_m, a['vertices_xz_m'], terrain)[0]
    if not np.array_equal(sampled, a['source_elevation_m']):
        raise ValueError('represented original source differs')
    if not np.allclose(a['source_elevation_m'] - a['bed_elevation_m'], a['cut_depth_m'], rtol=0.0, atol=1e-10):
        raise ValueError('source-bed-cut differs')
    if np.min(a['cut_depth_m']) < -1e-10 or np.max(a['cut_depth_m']) > m['config']['max_cut_m'] + 1e-08:
        raise ValueError('component cut outside budget')
    if not np.isclose(_mesh_volume(a['vertices_xz_m'], a['triangles'], a['cut_depth_m']), m['cut_volume_m3'], rtol=1e-10):
        raise ValueError('material ledger differs')
    _sparse_slope(a['node_xz_m'], a['receiver'], a['sparse_cell_xy'], a['vertices_xz_m'], a['triangles'], a['bed_elevation_m'], m['config']['fine_spacing_m'], terrain)
    if 'anchor_mask' in a:
        if not np.array_equal(a['node_xz_m'][a['anchor_mask']], a['original_node_xz_m'][a['anchor_mask']]):
            raise ValueError('source, confluence or terminal anchor moved')
        corridor = m['config'].get('centerline_corridor_m', 6.0)
        if np.any(np.linalg.norm(a['node_xz_m'] - a['original_node_xz_m'], axis=1) > corridor + 1e-08):
            raise ValueError('centerline outside declared original corridor')
        _local_route_crossings(a['node_xz_m'], a['receiver'])
    from terrain_pipeline.channel_geometry import _line_constraints
    from terrain_pipeline.channel_geometry import _mesh_directional_weights, _cell_at_point
    lookup = {tuple(cell): index for index, cell in enumerate(a['sparse_cell_xy'])}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    minimum = m.get('minimum_bed_slope_m_per_m', 0.0)
    for start, end, dt, i, j in _line_constraints(a['node_xz_m'], a['receiver'], a['sparse_cell_xy'], a['vertices_xz_m'], a['triangles'], terrain, m['config']['fine_spacing_m']):
        midpoint = (start[1] @ a['vertices_xz_m'][start[0]] + end[1] @ a['vertices_xz_m'][end[0]]) / 2.0
        cell = lookup[_cell_at_point(midpoint, lookup, origin, m['config']['fine_spacing_m'])]
        delta = a['node_xz_m'][j] - a['node_xz_m'][i]
        ids, weights = _mesh_directional_weights(midpoint, cell, a['vertices_xz_m'], a['triangles'], delta / np.linalg.norm(delta))
        gradient = float(weights[1:] @ (a['bed_elevation_m'][ids[1:]] - a['bed_elevation_m'][ids[0]]))
        if -gradient < minimum - 1e-08:
            raise ValueError('physical minimum bed slope violated')
    return True

def load_component_geometry(path, *, expected_sha256, expected_identity=None):
    if file_sha256(path) != expected_sha256:
        raise ValueError('component bytes differ')
    with np.load(path, allow_pickle=False) as archive:
        bundle = dict(arrays={key: archive[key] for key in archive.files if key not in ('metadata', 'identity_sha256')}, metadata=json.loads(str(archive['metadata'].item())), identity_sha256=str(archive['identity_sha256'].item()))
    if expected_identity is not None and bundle['identity_sha256'] != expected_identity:
        raise ValueError('component expected identity differs')
    validate_component_geometry(bundle)
    return bundle

def _resume_component(path, terrain, ids, receiver, width, depth, config):
    bundle = load_component_geometry(path, expected_sha256=file_sha256(path))
    if bundle['metadata']['source_identity_sha256'] != terrain.identity_sha256 or bundle['metadata']['config'] != asdict(config):
        raise ValueError('resume component source or config differs')
    for name, expected in (('source_node_cell_ids', ids), ('receiver', receiver), ('width_m', width), ('design_base_depth_m', depth)):
        if name not in bundle['arrays'] or not np.array_equal(bundle['arrays'][name], expected):
            raise ValueError('resume component ' + name + ' differs')
    return bundle

def generate_sample(output, registration, config=None, *, resume_from=None):
    config = config or GeneratedRiverConfig()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    arrays, metadata, plan, components = prepare_network(registration, config, bounded_spills=True)
    terrain = registration['terrain']
    records, artifacts, accepted = ([], [], [])
    statuses = np.full(len(arrays['selected_edge_source_ids']), 'rejected', dtype='U32')
    for index, edges in enumerate(components):
        sources = arrays['selected_edge_source_ids'][edges]
        targets = arrays['selected_edge_target_ids'][edges]
        ids = np.unique(np.r_[sources, targets])
        mapping = {int(cell): i for i, cell in enumerate(ids)}
        receiver = np.full(len(ids), -1, np.int64)
        for source, target in zip(sources, targets):
            receiver[mapping[int(source)]] = mapping[int(target)]
        record = dict(component_id=index, selected_edge_indices=edges.tolist(), edge_count=len(edges))
        resume_path = Path(resume_from) / f'geometry-c{index}.npz' if resume_from else None
        reused = resume_path is not None and resume_path.is_file()
        if reused:
            bundle = _resume_component(resume_path, terrain, ids, receiver, arrays['width_m'][ids], arrays['base_depth_m'][ids], config)
            record['reused_from'] = dict(path=str(resume_path.resolve()), sha256=file_sha256(resume_path), identity_sha256=bundle['identity_sha256'])
            import shutil
            shutil.copy2(resume_path, output / resume_path.name)
            if file_sha256(output / resume_path.name) != record['reused_from']['sha256']:
                raise ValueError('copied resume component bytes differ')
        try:

            def progress(phase):
                print(json.dumps(dict(sample=registration['metadata']['source_metadata']['sample_index'], component=index, phase=phase)), flush=True)
            if not reused:
                bundle = component_geometry(terrain, ids, receiver, arrays['width_m'][ids], arrays['base_depth_m'][ids], config, progress=progress)
            path = output / f'geometry-c{index}.npz'
            if not reused:
                save_component_geometry(path, bundle)
            pin = dict(path=path.name, sha256=file_sha256(path), identity_sha256=bundle['identity_sha256'])
            if not reused:
                load_component_geometry(path, expected_sha256=pin['sha256'], expected_identity=pin['identity_sha256'])
            record.update(status='accepted', geometry=pin, cut_volume_m3=bundle['metadata']['cut_volume_m3'], maximum_cut_m=bundle['metadata']['maximum_cut_m'])
            statuses[edges] = 'accepted'
            artifacts.append(pin)
            accepted.append(bundle)
        except ValueError as error:
            record.update(status='rejected', reason=str(error))
        records.append(record)
        print(json.dumps(dict(sample=registration['metadata']['source_metadata']['sample_index'], component=index, status=record['status'], reason=record.get('reason'))), flush=True)
    global_pin = None
    material = dict(unique_cut_volume_m3=0.0, component_sum_cut_volume_m3=0.0, overlap_double_count_m3=0.0)
    if accepted:
        sample_index = registration['metadata']['source_metadata']['sample_index']
        merge_started = time.perf_counter()
        print(json.dumps(dict(sample=sample_index, phase='global_merge_started', phase_elapsed_seconds=0.0)), flush=True)
        global_bundle = merge_component_beds(terrain, accepted, config, network_design_depth=arrays['base_depth_m'])
        print(json.dumps(dict(sample=sample_index, phase='global_merge_completed', phase_elapsed_seconds=time.perf_counter() - merge_started)), flush=True)
        path = output / 'global-bed.npz'
        save_started = time.perf_counter()
        save_component_geometry(path, global_bundle)
        print(json.dumps(dict(sample=sample_index, phase='global_bed_save_completed', phase_elapsed_seconds=time.perf_counter() - save_started)), flush=True)
        global_pin = dict(path=path.name, sha256=file_sha256(path), identity_sha256=global_bundle['identity_sha256'])
        load_component_geometry(path, expected_sha256=global_pin['sha256'], expected_identity=global_pin['identity_sha256'])
        summed = sum((bundle['metadata']['cut_volume_m3'] for bundle in accepted))
        unique = global_bundle['metadata']['cut_volume_m3']
        material = dict(unique_cut_volume_m3=unique, component_sum_cut_volume_m3=summed, overlap_double_count_m3=summed - global_bundle['metadata']['component_max_cut_reference_volume_m3'], component_max_envelope_cut_volume_m3=global_bundle['metadata']['component_max_cut_reference_volume_m3'], necessary_lower_cut_volume_m3=global_bundle['metadata']['preclosure_cut_volume_m3'], reclosure_net_change_m3=unique - global_bundle['metadata']['component_max_cut_reference_volume_m3'], closure_additional_cut_semantics='relative to necessary design minimum lower bound; net change is relative to component solved max envelope', union_monotone_additional_cut_volume_m3=unique - global_bundle['metadata']['preclosure_cut_volume_m3'], material_policy='single native source cut volume; exported sediment candidate, no deposition simulated')
    arrays['selected_edge_status'] = statuses
    np.savez_compressed(output / 'network.npz', **arrays)
    save_network_geometry_plan(output / 'network-plan.npz', plan)
    metadata.update(component_records=records, geometry_artifacts=artifacts, accepted_edges=int(np.sum(statuses == 'accepted')), rejected_edges=int(np.sum(statuses != 'accepted')), network=dict(path='network.npz', sha256=file_sha256(output / 'network.npz')), global_bed=global_pin, material_ledger=material, status='completed_all_selected_edges_classified', centerline_reference_policy='deterministic original-TD legacy initializer; no historical bed dependency', geometry_policy='complete connected components; no manual edge paths, wet mask or component selection', algorithm_source_sha256={name: file_sha256(Path(__file__).parents[2] / name) for name in ('terrain_pipeline/surface_rivers/metric_td_generated_rivers.py', 'terrain_pipeline/drainage.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/climate_forcing.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/channel_geometry.py', 'terrain_pipeline/channel_geometry.py')})
    publish_bytes(output / 'report.json', json.dumps(metadata, indent=2, allow_nan=False).encode())
    return (metadata, accepted)

def merge_component_beds(terrain, bundles, config, *, network_design_depth=None):
    """Own each fan4 cell once and close the actual global max envelope."""
    if any(('design_minimum_cut_m' in bundle['arrays'] for bundle in bundles)):
        if network_design_depth is None:
            raise ValueError('original network design depths required for design global bed')
        from terrain_pipeline.channel_geometry import merge_design_bundles
        return merge_design_bundles(terrain, bundles, config, network_design_depth)
    cells = np.unique(np.concatenate([bundle['arrays']['sparse_cell_xy'] for bundle in bundles]), axis=0)
    cells = cells[np.lexsort((cells[:, 0], cells[:, 1]))]
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m, 8000000)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    origin = np.array([terrain.x0_m, terrain.z0_m])
    keys = np.rint((vertices - origin) * 2.0 / config.fine_spacing_m).astype(np.int64)
    lookup = {tuple(key): index for index, key in enumerate(keys)}
    cut = np.zeros(len(vertices))
    all_ids = np.concatenate([bundle['arrays']['source_node_cell_ids'] for bundle in bundles])
    all_receiver = []
    offset = 0
    for bundle in bundles:
        a = bundle['arrays']
        mapping = np.array([lookup[tuple(key)] for key in np.rint((a['vertices_xz_m'] - origin) * 2.0 / config.fine_spacing_m).astype(np.int64)])
        np.maximum.at(cut, mapping, a['cut_depth_m'])
        all_receiver.extend(np.where(a['receiver'] >= 0, a['receiver'] + offset, -1))
        offset += len(a['receiver'])
    rec = np.asarray(all_receiver, np.int64)
    points = np.concatenate([bundle['arrays']['node_xz_m'] for bundle in bundles])
    before = _mesh_volume(vertices, triangles, cut)
    cut, closure = _close_bed(points, rec, cells, vertices, triangles, source, cut, terrain, config.fine_spacing_m, config.max_cut_m, minimum_slope_m_per_m=EPSILON_SLOPE_M_PER_M)
    _sparse_slope(points, rec, cells, vertices, triangles, source - cut, config.fine_spacing_m, terrain)
    arrays = dict(source_height_m=terrain.elevation_m, source_valid_mask=terrain.valid_mask, source_node_cell_ids=all_ids, receiver=rec, node_xz_m=points, width_m=np.concatenate([bundle['arrays']['width_m'] for bundle in bundles]), base_depth_m=np.concatenate([bundle['arrays']['base_depth_m'] for bundle in bundles]), sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, source_elevation_m=source, source_cell_ids=source_cells, cut_depth_m=cut, bed_elevation_m=source - cut)
    metadata = dict(schema='td-generated-component-bed-v1', algorithm='unique-whole-domain-max-cut-global-monotone-closure-v1', terrain_metadata=terrain.metadata(), source_identity_sha256=terrain.identity_sha256, config=asdict(config), cut_volume_m3=_mesh_volume(vertices, triangles, cut), preclosure_cut_volume_m3=before, maximum_cut_m=float(cut.max()), closure=closure, minimum_bed_slope_m_per_m=EPSILON_SLOPE_M_PER_M, monotone_closure_policy='actual triangle-plane directional gradient in m/m; no short-span elevation subtraction', unique_triangle_count=len(triangles), unique_cell_count=len(cells), divide_preservation_verified=False, natural_outlet_verified=False, hydraulic_ready=False, publishable=False)
    return dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
