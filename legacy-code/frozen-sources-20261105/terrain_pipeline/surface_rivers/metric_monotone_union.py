"""Monotone closure of a shared sparse valley bed after edge envelopes overlap."""

from dataclasses import asdict
import math

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_channel_geometry import GeometryConfig, _footprint, _mesh_volume, _route_crossings, _sample
from .metric_contracts import TerrainGrid
from .metric_valley_incision import _check_inputs, _metadata_terrain, _profile, _profile_cut, _profile_overlap
from .metric_valley_union import (
    _cut_source_constraints, _sparse_cells, _sparse_mesh, _sparse_ports, _sparse_slope, _cell_at_point, _coalesce_line_breaks, _mesh_directional_weights,
)


SCHEMA = "terragenesis-monotone-sparse-valley-union-v1"
ALGORITHM = "aligned-sparse-fan4-global-max-lp-monotone-closure-v1"
SHAPED_ALGORITHM = "anchored-original-valley-sparse-monotone-closure-v1"
MAX_BYTES = 128 * 1024 * 1024


def _barycentric(point, cell, vertices, triangles):
    scale = max(1., float(np.abs(point).max()))
    span = np.linalg.norm(vertices[triangles[4 * cell, 1]] - vertices[triangles[4 * cell, 0]])
    tolerance = max(1e-9, 8. * np.spacing(scale) / span)
    for face in range(4 * cell, 4 * cell + 4):
        ids = triangles[face]
        tri = vertices[ids]
        matrix = np.column_stack((tri[1] - tri[0], tri[2] - tri[0]))
        uv = np.linalg.solve(matrix, point - tri[0])
        weights = np.array([1. - uv.sum(), uv[0], uv[1]])
        if np.min(weights) >= -tolerance:
            return ids, weights
    raise ValueError("centerline point outside sparse triangles")


def _line_constraints(points, receiver, cells, vertices, triangles, terrain, spacing):
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    segments = []
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        delta = b - a
        breaks = [0., 1.]
        for axis in range(2):
            if abs(delta[axis]) <= 1e-15:
                continue
            first = int(math.floor((min(a[axis], b[axis]) - origin[axis]) / spacing))
            last = int(math.ceil((max(a[axis], b[axis]) - origin[axis]) / spacing))
            for grid in range(first, last + 1):
                t = (origin[axis] + grid * spacing - a[axis]) / delta[axis]
                if 1e-12 < t < 1. - 1e-12:
                    breaks.append(t)
        grid_breaks = _coalesce_line_breaks(breaks,a,b,spacing)
        for t0, t1 in zip(grid_breaks[:-1], grid_breaks[1:]):
            midpoint = a + (t0 + t1) / 2. * delta
            key = _cell_at_point(midpoint,lookup,origin,spacing)
            low = origin + spacing * np.asarray(key)
            for normal, constant in ((np.array([1., -1.]), 0.),
                                     (np.array([1., 1.]), spacing)):
                denominator = float(normal @ delta)
                if abs(denominator) <= 1e-15:
                    continue
                t = (constant - normal @ (a - low)) / denominator
                if t0 + 1e-12 < t < t1 - 1e-12:
                    breaks.append(t)
        all_breaks=_coalesce_line_breaks(breaks,a,b,spacing)
        for t0, t1 in zip(all_breaks[:-1], all_breaks[1:]):
            midpoint = a + (t0 + t1) / 2. * delta
            key = _cell_at_point(midpoint,lookup,origin,spacing)
            cell = lookup.get(key)
            if cell is None:
                raise ValueError("centerline leaves sparse mesh support")
            start = _barycentric(a + t0 * delta, cell, vertices, triangles)
            end = _barycentric(a + t1 * delta, cell, vertices, triangles)
            segments.append((start, end, float(t1 - t0), i, int(j)))
    return segments


def _close_bed(points, receiver, cells, vertices, triangles, source, original_cut,
               terrain, spacing, max_cut_m, *, minimum_slope_m_per_m=None):
    segments = _line_constraints(points, receiver, cells, vertices, triangles,
                                 terrain, spacing)
    if minimum_slope_m_per_m is not None:
        return _close_physical_bed(points,segments,cells,vertices,triangles,source,original_cut,
            terrain,spacing,max_cut_m,minimum_slope_m_per_m)
    active = np.unique(np.concatenate([np.r_[start[0], end[0]]
                                       for start, end, _, _, _ in segments]))
    if active.size == 0:
        raise ValueError("monotone closure has no centerline support")
    mapping = np.full(len(vertices), -1, np.int64)
    mapping[active] = np.arange(len(active))
    base_bed = source - original_cut
    rows, columns, coefficients, limits = [], [], [], []
    for row, (start, end, dt, edge_source, edge_target) in enumerate(segments):
        h0 = float(start[1] @ base_bed[start[0]])
        h1 = float(end[1] @ base_bed[end[0]])
        for vertex, weight in zip(start[0], start[1]):
            rows.append(row)
            columns.append(int(mapping[vertex]))
            coefficients.append(float(weight))
        for vertex, weight in zip(end[0], end[1]):
            rows.append(row)
            columns.append(int(mapping[vertex]))
            coefficients.append(float(-weight))
        minimum_drop = 1e-7 * dt if minimum_slope_m_per_m is None else (
            minimum_slope_m_per_m * np.linalg.norm(points[edge_target]-points[edge_source]) * dt)
        limits.append(-minimum_drop - (h1 - h0))
    matrix = coo_matrix((coefficients, (rows, columns)),
                        shape=(len(segments), len(active))).tocsr()
    bounds = [(0., float(max_cut_m - original_cut[vertex])) for vertex in active]
    result = linprog(np.ones(len(active)), A_ub=matrix, b_ub=np.asarray(limits),
                     bounds=bounds, method="highs",
                     options={} if minimum_slope_m_per_m is None else {"primal_feasibility_tolerance":1e-9})
    if not result.success:
        raise ValueError("shared monotone closure exceeds 4m cut or is infeasible: " + result.message)
    cut = original_cut.copy()
    cut[active] += result.x
    residual = matrix @ result.x - limits
    if np.max(residual) > 1e-7 or np.max(cut) > max_cut_m + 1e-8:
        raise ValueError("shared monotone closure residual or maximum cut exceeded")
    return cut, dict(extra_cut_vertices=int(np.count_nonzero(result.x > 1e-9)),
                     extra_cut_sum_m=float(np.sum(result.x)),
                     maximum_constraint_residual_m=float(np.max(residual)),
                     centerline_segments=len(segments))


def _close_physical_bed(points,segments,cells,vertices,triangles,source,original_cut,
                        terrain,spacing,max_cut_m,minimum_slope):
    lookup={tuple(cell):index for index,cell in enumerate(cells)}
    origin=np.array([terrain.x0_m,terrain.z0_m])
    base_bed=source-original_cut
    constraints=[]
    for start,end,dt,i,j in segments:
        midpoint=(start[1]@vertices[start[0]]+end[1]@vertices[end[0]])/2.
        key=_cell_at_point(midpoint,lookup,origin,spacing)
        delta=points[j]-points[i]
        ids,weights=_mesh_directional_weights(midpoint,lookup[key],vertices,triangles,delta/np.linalg.norm(delta))
        base_gradient=float(weights[1:]@(base_bed[ids[1:]]-base_bed[ids[0]]))
        constraints.append((ids,-weights,-minimum_slope-base_gradient))
    active=np.unique(np.concatenate([ids for ids,_,_ in constraints]))
    mapping=np.full(len(vertices),-1,np.int64);mapping[active]=np.arange(len(active))
    rows=[];columns=[];coefficients=[];limits=[]
    for row,(ids,weights,limit) in enumerate(constraints):
        rows.extend([row]*3);columns.extend(mapping[ids]);coefficients.extend(weights);limits.append(limit)
    matrix=coo_matrix((coefficients,(rows,columns)),shape=(len(constraints),len(active))).tocsr()
    bounds=[(0.,float(max_cut_m-original_cut[vertex])) for vertex in active]
    result=linprog(np.ones(len(active)),A_ub=matrix,b_ub=np.asarray(limits),bounds=bounds,method="highs",
        options={"primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9})
    if not result.success:
        raise ValueError("shared physical-slope closure exceeds 4m cut or is infeasible: "+result.message)
    residual=matrix@result.x-limits
    if np.max(residual)>1e-8:
        raise ValueError("shared physical-slope closure residual exceeds tolerance")
    cut=original_cut.copy();cut[active]+=result.x
    return cut,dict(extra_cut_vertices=int(np.count_nonzero(result.x>1e-9)),extra_cut_sum_m=float(np.sum(result.x)),
        maximum_constraint_residual_m_per_m=float(np.max(residual)),constraint_units="m/m",
        centerline_segments=len(segments),physical_triangle_plane_gradient=True)


def _geometry(terrain, ids, receiver, width, depth, points, owner, corridor, lake, config):
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    _footprint(points, receiver, width, np.full(len(points), config.max_cut_m),
               terrain, owner, corridor, lake, owner.ravel()[ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    cells = _sparse_cells(points, receiver, width, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m, config.max_vertices)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    base_cut = _profile_cut(points, receiver, width, profile, vertices, terrain, lake)
    cut, closure = _close_bed(points, receiver, cells, vertices, triangles, source,
                              base_cut, terrain, config.fine_spacing_m, config.max_cut_m)
    _sparse_slope(points, receiver, cells, vertices, triangles, source-cut,
                  config.fine_spacing_m, terrain)
    _cut_source_constraints(vertices, source_cells, cut, terrain, owner, corridor, lake,
                            owner.ravel()[ids[0]])
    ports = _sparse_ports(points, receiver, width, profile, cells, vertices, triangles,
                          cut, config.fine_spacing_m, terrain)
    return profile, cells, vertices, triangles, source, source_cells, cut, ports, closure


def build_monotone_union(terrain, node_cell_ids, receiver, width_m, base_depth_m, *,
                         owner_grid, corridor_mask, lake_mask,
                         source_plan_identity_sha256, config=None, centerline=None):
    config = config or GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0)
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m,
                  owner_grid, corridor_mask, lake_mask, config)
    if (not isinstance(source_plan_identity_sha256, str)
            or len(source_plan_identity_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in source_plan_identity_sha256)):
        raise ValueError("source network plan identity required")
    if np.unique(owner_grid.ravel()[node_cell_ids]).size != 1:
        raise ValueError("shared component spans original source owners")
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m,
                              terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    if centerline is not None:
        from .metric_valley_centerline import validate_valley_centerline
        validate_valley_centerline(centerline)
        ca, cm = centerline["arrays"], centerline["metadata"]
        if (cm["source_identity_sha256"] != terrain.identity_sha256
                or cm["source_plan_identity_sha256"] != source_plan_identity_sha256
                or any(not np.array_equal(ca[key], value) for key, value in (
                    ("source_node_cell_ids", node_cell_ids), ("receiver", receiver),
                    ("width_m", width_m), ("base_depth_m", base_depth_m),
                    ("owner_grid", owner_grid), ("corridor_mask", corridor_mask),
                    ("lake_mask", lake_mask)))):
            raise ValueError("shaped bed and centerline source graph mismatch")
        points = ca["node_xz_m"]
    profile, cells, vertices, triangles, source, source_cells, cut, ports, closure = _geometry(
        terrain, node_cell_ids, receiver, width_m, base_depth_m, points,
        owner_grid, corridor_mask, lake_mask, config)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(),
                  node_xz_m=points, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(),
                  source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(),
                  owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(),
                  lake_mask=lake_mask.copy(), profile_offsets=profile[0], profile_t=profile[1],
                  profile_source_m=profile[2], profile_center_bed_m=profile[3],
                  sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles,
                  source_elevation_m=source, source_cell_ids=source_cells,
                  cut_depth_m=cut, bed_elevation_m=source-cut,
                  port_edge_node_indices=ports[0], port_xz_m=ports[1],
                  port_profile_xz_m=ports[2], port_triangle_ids=ports[3],
                  port_barycentric=ports[4], port_cut_depth_m=ports[5])
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, terrain_metadata=_metadata_terrain(terrain),
                    source_identity_sha256=terrain.identity_sha256,
                    source_plan_identity_sha256=source_plan_identity_sha256,
                    config=asdict(config), closure=closure,
                    cut_volume_m3=_mesh_volume(vertices, triangles, cut),
                    global_component_only=True, cross_component_verified=False,
                    hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    if centerline is not None:
        arrays.update(original_node_xz_m=ca["original_node_xz_m"].copy(),
                      anchor_mask=ca["anchor_mask"].copy())
        metadata.update(algorithm=SHAPED_ALGORITHM, centerline_recipe=cm["recipe"])
    arrays = {key: readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_monotone_union(bundle)
    return bundle


def validate_monotone_union(bundle):
    if (not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}
            or bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"])
            or sum(value.nbytes for value in bundle["arrays"].values()) > MAX_BYTES):
        raise ValueError("monotone union identity or byte budget mismatch")
    a, m = bundle["arrays"], bundle["metadata"]
    expected_arrays = {"source_node_cell_ids", "receiver", "node_xz_m", "width_m",
                       "base_depth_m", "source_height_m", "source_valid_mask", "owner_grid",
                       "corridor_mask", "lake_mask", "profile_offsets", "profile_t",
                       "profile_source_m", "profile_center_bed_m", "sparse_cell_xy",
                       "vertices_xz_m", "triangles", "source_elevation_m", "source_cell_ids",
                       "cut_depth_m", "bed_elevation_m", "port_edge_node_indices", "port_xz_m",
                       "port_profile_xz_m", "port_triangle_ids", "port_barycentric",
                       "port_cut_depth_m"}
    expected_meta = {"schema", "algorithm", "terrain_metadata", "source_identity_sha256",
                     "source_plan_identity_sha256", "config", "closure", "cut_volume_m3",
                     "global_component_only", "cross_component_verified", "hydraulic_ready",
                     "natural_outlet_verified", "publishable"}
    float_fields = {"node_xz_m", "width_m", "base_depth_m", "source_height_m",
                    "profile_t", "profile_source_m", "profile_center_bed_m",
                    "vertices_xz_m", "source_elevation_m", "cut_depth_m", "bed_elevation_m",
                    "port_xz_m", "port_profile_xz_m", "port_barycentric", "port_cut_depth_m"}
    int_fields = {"source_node_cell_ids", "receiver", "owner_grid", "profile_offsets",
                  "sparse_cell_xy", "triangles", "source_cell_ids", "port_edge_node_indices",
                  "port_triangle_ids"}
    bool_fields = {"source_valid_mask", "corridor_mask", "lake_mask"}
    shaped = m.get("algorithm") == SHAPED_ALGORITHM
    if shaped:
        expected_arrays.update(("original_node_xz_m", "anchor_mask"))
        expected_meta.add("centerline_recipe")
        float_fields.add("original_node_xz_m")
        bool_fields.add("anchor_mask")
    pin = m.get("source_plan_identity_sha256")
    if (set(a) != expected_arrays or set(m) != expected_meta
            or any(not isinstance(a[key], np.ndarray) or a[key].dtype != np.float64
                   for key in float_fields)
            or any(not isinstance(a[key], np.ndarray) or a[key].dtype != np.int64
                   for key in int_fields)
            or any(not isinstance(a[key], np.ndarray) or a[key].dtype != bool
                   for key in bool_fields)
            or not isinstance(pin, str) or len(pin) != 64
            or any(ch not in "0123456789abcdef" for ch in pin)
            or m.get("schema") != SCHEMA or m.get("algorithm") not in (ALGORITHM, SHAPED_ALGORITHM)
            or m.get("global_component_only") is not True
            or any(m.get(key) is not False for key in (
                "cross_component_verified", "hydraulic_ready", "natural_outlet_verified", "publishable"))):
        raise ValueError("monotone union schema or scope mismatch")
    terrain = TerrainGrid(a["source_height_m"], a["source_valid_mask"], **m["terrain_metadata"])
    if terrain.identity_sha256 != m["source_identity_sha256"]:
        raise ValueError("monotone union source mismatch")
    config = GeometryConfig(**m["config"])
    ids, receiver, width, depth = (a[key] for key in (
        "source_node_cell_ids", "receiver", "width_m", "base_depth_m"))
    _check_inputs(terrain, ids, receiver, width, depth, a["owner_grid"],
                  a["corridor_mask"], a["lake_mask"], config)
    if np.unique(a["owner_grid"].ravel()[ids]).size != 1:
        raise ValueError("monotone union component spans owners")
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m,
                              terrain.z0_m + ids // cols * terrain.dz_m))
    if shaped:
        from .metric_valley_centerline import CenterlineRecipe, _anchors, _validate_shape
        anchors = _anchors(receiver)
        if (not np.array_equal(points, a["original_node_xz_m"])
                or not np.array_equal(anchors, a["anchor_mask"])):
            raise ValueError("shaped bed original graph or anchors mismatch")
        _validate_shape(a["node_xz_m"], points, anchors, receiver, width, depth,
                        terrain, a["owner_grid"], a["corridor_mask"], a["lake_mask"],
                        config, CenterlineRecipe(**m["centerline_recipe"]))
        points = a["node_xz_m"]
    elif not np.array_equal(points, a["node_xz_m"]):
        raise ValueError("monotone union fixed source node mismatch")
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    _footprint(points, receiver, width, np.full(len(points), config.max_cut_m),
               terrain, a["owner_grid"], a["corridor_mask"], a["lake_mask"],
               a["owner_grid"].ravel()[ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    cells = _sparse_cells(points, receiver, width, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m,
                                       config.max_vertices)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    base_cut = _profile_cut(points, receiver, width, profile, vertices, terrain,
                            a["lake_mask"])
    cut = a["cut_depth_m"]
    if (cut.shape != base_cut.shape or not np.isfinite(cut).all()
            or np.any(cut < base_cut - 1e-9)
            or np.any(cut > config.max_cut_m + 1e-8)):
        raise ValueError("monotone closure cut violates base envelope or maximum")
    _cut_source_constraints(vertices, source_cells, cut, terrain, a["owner_grid"],
                            a["corridor_mask"], a["lake_mask"],
                            a["owner_grid"].ravel()[ids[0]])
    _sparse_slope(points, receiver, cells, vertices, triangles, source-cut,
                  config.fine_spacing_m, terrain)
    ports = _sparse_ports(points, receiver, width, profile, cells, vertices, triangles,
                          cut, config.fine_spacing_m, terrain)
    expected = dict(profile_offsets=profile[0], profile_t=profile[1],
                    profile_source_m=profile[2], profile_center_bed_m=profile[3],
                    sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles,
                    source_elevation_m=source, source_cell_ids=source_cells,
                    cut_depth_m=cut, bed_elevation_m=source-cut,
                    port_edge_node_indices=ports[0], port_xz_m=ports[1],
                    port_profile_xz_m=ports[2], port_triangle_ids=ports[3],
                    port_barycentric=ports[4], port_cut_depth_m=ports[5])
    for key, value in expected.items():
        if a[key].shape != value.shape or not np.allclose(a[key], value, rtol=0., atol=1e-8):
            raise ValueError("monotone union field mismatch: " + key)
    extra = cut - base_cut
    closure = m["closure"]
    segments = _line_constraints(points, receiver, cells, vertices, triangles,
                                 terrain, config.fine_spacing_m)
    if (set(closure) != {"extra_cut_vertices", "extra_cut_sum_m",
                        "maximum_constraint_residual_m", "centerline_segments"}
            or closure["extra_cut_vertices"] != int(np.count_nonzero(extra > 1e-9))
            or not math.isclose(closure["extra_cut_sum_m"], float(np.sum(extra)), abs_tol=1e-8)
            or closure["centerline_segments"] != len(segments)
            or not math.isfinite(closure["maximum_constraint_residual_m"])
            or closure["maximum_constraint_residual_m"] > 1e-7
            or not math.isclose(m["cut_volume_m3"], _mesh_volume(vertices, triangles, cut),
                                rel_tol=1e-10, abs_tol=1e-7)):
        raise ValueError("monotone closure material ledger mismatch")
    return True


def save_monotone_union(path, bundle):
    save_bundle(path, bundle, validator=validate_monotone_union)


def load_monotone_union(path, *, expected_sha256, expected_identity):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_monotone_union, max_bytes=MAX_BYTES)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external monotone union identity mismatch")
    return bundle
