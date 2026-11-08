"""One sparse canonical fan4 field for a bounded connected valley graph."""

from dataclasses import asdict
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from .metric_channel_geometry import (
    GeometryConfig, BANK_SLOPE, _mesh_volume, _footprint,
    _route_crossings, _sample, _segment_box_distance,
)
from terrain_pipeline.common_infra import TerrainGrid
from .metric_valley_incision import (
    _check_inputs, _metadata_terrain, _profile, _profile_cut,
    _profile_overlap, _profile_max_cut_per_edge,
)


SCHEMA = "terragenesis-sparse-valley-union-v1"
ALGORITHM = "aligned-sparse-fan4-global-max-incision-v2"
MAX_BYTES = 128 * 1024 * 1024


def _sparse_cells(points, receiver, width, profile, config, terrain, *, support_radius_m=None):
    spacing = config.fine_spacing_m
    origin = np.array([terrain.x0_m, terrain.z0_m])
    maximum = np.array([(terrain.elevation_m.shape[1] - 1) * round(terrain.dx_m / spacing),
                        (terrain.elevation_m.shape[0] - 1) * round(terrain.dz_m / spacing)], np.int64)
    cells = set()
    if support_radius_m is None:
        maximum_cut = _profile_max_cut_per_edge(points, receiver, profile, terrain)
    else:
        support_radius_m = np.asarray(support_radius_m, dtype=np.float64)
        if (support_radius_m.shape != (np.count_nonzero(receiver >= 0),)
                or not np.all(np.isfinite(support_radius_m))
                or np.any(support_radius_m <= 0.0)):
            raise ValueError("positive finite support radius required for every represented edge")
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        radius = (max(width[i], width[j]) / 2. + BANK_SLOPE * maximum_cut[edge]
                  if support_radius_m is None else support_radius_m[edge])
        edge += 1
        a, b = points[i], points[j]
        first = np.maximum(np.floor((np.minimum(a, b) - radius - origin) / spacing).astype(int), 0)
        last = np.minimum(np.ceil((np.maximum(a, b) + radius - origin) / spacing).astype(int), maximum)
        candidate_count = int(np.prod(np.maximum(last - first, 0)))
        if candidate_count > config.max_vertices:
            raise ValueError("sparse footprint preflight vertex budget exceeded")
        columns = int(last[0] - first[0])
        for start in range(0, candidate_count, 65_536):
            flat = np.arange(start, min(start + 65_536, candidate_count))
            candidates = np.column_stack((first[0] + flat % columns, first[1] + flat // columns))
            low = origin + spacing * candidates
            selected = _segment_boxes_distance(a, b, low, low + spacing) <= radius + 1e-10
            cells.update(map(tuple, candidates[selected]))
        if len(cells) > config.max_vertices:
            raise ValueError("sparse union cell budget exceeded before meshing")
    if not cells:
        raise ValueError("no sparse channel support cells")
    return np.asarray(sorted(cells, key=lambda item: (item[1], item[0])), np.int64)


def _segment_boxes_distance(a, b, low, high):
    """Batch the scalar endpoint, four-corner and edge-intersection predicate."""
    delta = b - a
    intersects = np.zeros(len(low), bool)
    for endpoint in (a, b):
        intersects |= np.all(endpoint >= low, axis=1) & np.all(endpoint <= high, axis=1)
    for axis in (0, 1):
        if delta[axis] == 0.0:
            continue
        other = 1 - axis
        for boundary in (low[:, axis], high[:, axis]):
            t = (boundary - a[axis]) / delta[axis]
            cross = a[other] + t * delta[other]
            intersects |= (t >= 0.0) & (t <= 1.0) & (cross >= low[:, other]) & (cross <= high[:, other])
    distances = np.full(len(low), np.inf)
    for endpoint in (a, b):
        separation = np.maximum(low - endpoint, np.maximum(endpoint - high, 0.0))
        distances = np.minimum(distances, np.linalg.norm(separation, axis=1))
    denominator = float(delta @ delta)
    if denominator == 0.0:
        return distances
    for x in (low[:, 0], high[:, 0]):
        for z in (low[:, 1], high[:, 1]):
            corner = np.column_stack((x, z))
            t = np.clip(np.sum((corner - a) * delta, axis=1) / denominator, 0.0, 1.0)
            separation = corner - (a + t[:, None] * delta)
            distances = np.minimum(distances, np.linalg.norm(separation, axis=1))
    distances[intersects] = 0.0
    return distances


def _sparse_mesh(cells, terrain, spacing, max_vertices):
    if not len(cells):
        if max_vertices < 0:
            raise ValueError("sparse canonical mesh vertex budget exceeded")
        return np.empty(0, np.float64), np.empty((0, 3), np.int64)
    cells = np.asarray(cells, np.int64)
    minimum = cells.min(axis=0)
    stride = int(cells[:, 0].max() - minimum[0]) + 2
    cell_keys = (cells[:, 1] - minimum[1]) * stride + cells[:, 0] - minimum[0]
    corners = np.unique(np.concatenate([
        cell_keys, cell_keys + 1, cell_keys + stride + 1, cell_keys + stride,
    ]))
    count = len(corners) + len(cells)
    if count > max_vertices:
        raise ValueError("sparse canonical mesh vertex budget exceeded")
    origin = np.array([terrain.x0_m, terrain.z0_m])
    vertices = np.empty((count, 2), np.float64)
    vertices[:len(corners), 0] = origin[0] + spacing * (corners % stride + minimum[0])
    vertices[:len(corners), 1] = origin[1] + spacing * (corners // stride + minimum[1])
    vertices[len(corners):] = origin + spacing * (cells + .5)
    triangles = np.empty((4 * len(cells), 3), np.int64)
    for start in range(0, len(cells), 200_000):
        keys = cell_keys[start:start + 200_000]
        corner_ids = np.searchsorted(corners, keys[:, None] + [0, 1, stride + 1, stride])
        faces = triangles[4 * start:4 * (start + len(keys))].reshape(-1, 4, 3)
        faces[:, :, 0] = corner_ids
        faces[:, :, 1] = corner_ids[:, [1, 2, 3, 0]]
        faces[:, :, 2] = (len(corners) + np.arange(start, start + len(keys)))[:, None]
    return vertices, triangles


def _mesh_height(point, cell, vertices, triangles, bed):
    for face in range(4 * cell, 4 * cell + 4):
        ids = triangles[face]
        tri = vertices[ids]
        matrix = np.column_stack((tri[1] - tri[0], tri[2] - tri[0]))
        uv = np.linalg.solve(matrix, point - tri[0])
        if min(1. - uv.sum(), uv[0], uv[1]) >= -1e-9:
            return float(bed[ids[0]] + uv @ (bed[ids[1:]] - bed[ids[0]]))
    raise ValueError("line point outside sparse canonical triangle")


def _sparse_ports(points, receiver, width, profile_data, cells, vertices, triangles,
                  cut, spacing, terrain):
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    edges = np.array([(i, int(j)) for i, j in enumerate(receiver) if j >= 0], np.int64)
    middle = np.empty((len(edges), 2), np.float64)
    profile = np.empty((len(edges), 4, 2), np.float64)
    face_ids = np.empty((len(edges), 4), np.int64)
    bary = np.empty((len(edges), 4, 3), np.float64)
    cut_values = np.empty((len(edges), 4), np.float64)
    for index, (i, j) in enumerate(edges):
        a, b = points[i], points[j]
        center = (a + b) / 2.
        flow = (b - a) / np.linalg.norm(b - a)
        normal = np.array([-flow[1], flow[0]])
        half = (width[i] + width[j]) / 4.
        lo, hi = profile_data[0][index:index + 2]
        center_cut = float(np.interp(.5, profile_data[1][lo:hi],
                                     profile_data[2][lo:hi] - profile_data[3][lo:hi]))
        bank = BANK_SLOPE * center_cut
        middle[index] = center
        for k, offset in enumerate((-half - bank, -half, half, half + bank)):
            p = center + offset * normal
            profile[index, k] = p
            cell_xy = np.floor((p - origin) / spacing).astype(int)
            found = False
            for x in (cell_xy[0], cell_xy[0] - 1):
                for z in (cell_xy[1], cell_xy[1] - 1):
                    cell = lookup.get((x, z))
                    if cell is None:
                        continue
                    for face in range(4 * cell, 4 * cell + 4):
                        ids = triangles[face]
                        tri = vertices[ids]
                        matrix = np.column_stack((tri[1] - tri[0], tri[2] - tri[0]))
                        uv = np.linalg.solve(matrix, p - tri[0])
                        weights = np.array([1. - uv.sum(), uv[0], uv[1]])
                        if np.min(weights) >= -1e-9:
                            face_ids[index, k] = face
                            bary[index, k] = weights
                            cut_values[index, k] = weights @ cut[ids]
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
            if not found:
                raise ValueError("shared sparse port outside canonical mesh")
    return edges, middle, profile, face_ids, bary, cut_values


def _cut_source_constraints(vertices, source_cells, cut, terrain, owner_grid,
                            corridor_mask, lake_mask, source_owner):
    cols = terrain.elevation_m.shape[1]
    for cell, amount in zip(source_cells, cut):
        if amount <= 1e-10:
            continue
        gz, gx = divmod(int(cell), cols)
        stencil = np.s_[gz:gz + 2, gx:gx + 2]
        if (not terrain.valid_mask[stencil].all() or not corridor_mask[stencil].all()
                or np.any(owner_grid[stencil] != source_owner)
                or lake_mask[stencil].any()):
            raise ValueError("sparse cut crosses unknown, owner, corridor or known wet support")


def _cell_at_point(point,lookup,origin,spacing):
    coordinate=(point-origin)/spacing
    first=np.floor(coordinate).astype(np.int64)
    key=tuple(first)
    if key in lookup:
        return key
    # A point on a grid line belongs to either touching cell, including the
    # upper exterior grid line whose floor index has no represented cell.
    touching=[]
    for axis in range(2):
        candidates=[first[axis],first[axis]-1]
        nearest=int(np.rint(coordinate[axis]))
        if abs(coordinate[axis]-nearest)<=1e-9 and nearest not in candidates:
            candidates.append(nearest)
        touching.append(candidates)
    for x in touching[0]:
        for z in touching[1]:
            candidate=(int(x),int(z))
            if candidate in lookup and np.all(coordinate>=[x-1e-9,z-1e-9]) and np.all(coordinate<=[x+1.+1e-9,z+1.+1e-9]):
                return candidate
    raise ValueError("centerline leaves sparse mesh support")


def _coalesce_line_breaks(values,a,b,spacing):
    values=np.unique(values)
    # Distinct analytic intersections can round to the same metric point at
    # large world origins. Treat those as one break at coordinate precision.
    resolution=max(spacing*1e-10,8.*np.spacing(max(1.,float(np.abs(np.r_[a,b]).max()))))
    tolerance=resolution/np.linalg.norm(b-a)
    result=[]
    group=[float(values[0])]
    for value in values[1:]:
        if value-group[-1]<=tolerance:
            group.append(float(value))
        else:
            result.append(0. if group[0]==0. else float(np.mean(group)))
            group=[float(value)]
    result.append(1. if group[-1]==1. else float(np.mean(group)))
    return np.asarray(result)


def _mesh_directional_weights(point,cell,vertices,triangles,direction):
    candidates=[]
    for face in range(4*cell,4*cell+4):
        ids=triangles[face]
        tri=vertices[ids]
        matrix=np.column_stack((tri[1]-tri[0],tri[2]-tri[0]))
        uv=np.linalg.solve(matrix,point-tri[0])
        weights=np.r_[1.-uv.sum(),uv]
        candidates.append((float(weights.min()),ids,matrix))
    margin,ids,matrix=max(candidates,key=lambda item:item[0])
    if margin< -1e-8:
        raise ValueError("line midpoint outside sparse canonical triangle")
    uv_direction=np.linalg.solve(matrix,direction)
    return ids,np.r_[-uv_direction.sum(),uv_direction]


def _sparse_slope(points, receiver, cells, vertices, triangles, bed, spacing, terrain):
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        delta = b - a
        breaks = [0., 1.]
        for axis in (0, 1):
            if abs(delta[axis]) <= 1e-15:
                continue
            for grid in range(int(math.floor((min(a[axis], b[axis]) - origin[axis]) / spacing)),
                              int(math.ceil((max(a[axis], b[axis]) - origin[axis]) / spacing)) + 1):
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
        breaks = _coalesce_line_breaks(breaks,a,b,spacing)
        for t0, t1 in zip(breaks[:-1], breaks[1:]):
            midpoint = a + (t0 + t1) / 2. * delta
            key = _cell_at_point(midpoint,lookup,origin,spacing)
            cell = lookup[key]
            ids,direction_weights=_mesh_directional_weights(midpoint,cell,vertices,triangles,delta/np.linalg.norm(delta))
            gradient=float(direction_weights[1:]@(bed[ids[1:]]-bed[ids[0]]))
            if gradient>=0.:
                raise ValueError(f"sparse canonical bed is flat or uphill: edge={i}->{j}, dt={t1-t0:.17g}, length={np.linalg.norm(delta)*(t1-t0):.17g}m, directional_gradient={gradient:.17g}m/m")


def build_valley_union(terrain, node_cell_ids, receiver, width_m, base_depth_m, *,
                       owner_grid, corridor_mask, lake_mask,
                       source_plan_identity_sha256, config=None):
    config = config or GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0)
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m,
                  owner_grid, corridor_mask, lake_mask, config)
    if (not isinstance(source_plan_identity_sha256, str)
            or len(source_plan_identity_sha256) != 64
            or any(c not in "0123456789abcdef" for c in source_plan_identity_sha256)):
        raise ValueError("source network plan SHA256 identity required")
    if np.unique(owner_grid.ravel()[node_cell_ids]).size != 1:
        raise ValueError("sparse union component must have one source owner")
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m,
                              terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, base_depth_m, terrain, config.max_cut_m)
    maxdepth = np.full(len(points), config.max_cut_m)
    _footprint(points, receiver, width_m, maxdepth, terrain,
               owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids],
               config.fine_spacing_m)
    _profile_overlap(points, receiver, width_m, profile, terrain)
    cells = _sparse_cells(points, receiver, width_m, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m, config.max_vertices)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width_m, profile, vertices, terrain, lake_mask)
    if not np.isfinite(cut).all() or np.any(cut < 0.) or np.any(cut > config.max_cut_m + 1e-10):
        raise ValueError("sparse union cut exceeds maximum")
    bed = source - cut
    _sparse_slope(points, receiver, cells, vertices, triangles, bed,
                  config.fine_spacing_m, terrain)
    # All source-cell corner stencils touched by a represented cut stay in one owner/corridor.
    _cut_source_constraints(vertices, source_cells, cut, terrain, owner_grid,
                            corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids[0]])
    ports = _sparse_ports(points, receiver, width_m, profile, cells,
                          vertices, triangles, cut, config.fine_spacing_m, terrain)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(),
                  node_xz_m=points, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(),
                  source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(),
                  owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(),
                  lake_mask=lake_mask.copy(), profile_offsets=profile[0], profile_t=profile[1],
                  profile_source_m=profile[2], profile_center_bed_m=profile[3],
                  sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles,
                  source_elevation_m=source, source_cell_ids=source_cells,
                  cut_depth_m=cut, bed_elevation_m=bed,
                  port_edge_node_indices=ports[0], port_xz_m=ports[1],
                  port_profile_xz_m=ports[2], port_triangle_ids=ports[3],
                  port_barycentric=ports[4], port_cut_depth_m=ports[5])
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, terrain_metadata=_metadata_terrain(terrain),
                    source_identity_sha256=terrain.identity_sha256, config=asdict(config),
                    source_plan_identity_sha256=source_plan_identity_sha256,
                    cut_volume_m3=_mesh_volume(vertices, triangles, cut),
                    mesh_measure="unique_sparse_aligned_fan4_piecewise_linear",
                    global_component_only=True, cross_component_verified=False,
                    hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    arrays = {key: readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_valley_union(bundle)
    return bundle


def validate_valley_union(bundle):
    if (not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}
            or bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"])
            or sum(value.nbytes for value in bundle["arrays"].values()) > MAX_BYTES):
        raise ValueError("sparse union identity or byte budget mismatch")
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
                     "config", "source_plan_identity_sha256", "cut_volume_m3", "mesh_measure",
                     "global_component_only", "cross_component_verified", "hydraulic_ready",
                     "natural_outlet_verified", "publishable"}
    if (set(a) != expected_arrays or set(m) != expected_meta
            or m.get("schema") != SCHEMA or m.get("algorithm") != ALGORITHM
            or m.get("mesh_measure") != "unique_sparse_aligned_fan4_piecewise_linear"
            or m.get("global_component_only") is not True
            or any(m.get(key) is not False for key in ("cross_component_verified", "hydraulic_ready",
                                                       "natural_outlet_verified", "publishable"))):
        raise ValueError("sparse union schema or scope mismatch")
    float_fields = ("node_xz_m", "width_m", "base_depth_m", "source_height_m",
                    "profile_t", "profile_source_m", "profile_center_bed_m",
                    "vertices_xz_m", "source_elevation_m", "cut_depth_m",
                    "bed_elevation_m", "port_xz_m", "port_profile_xz_m",
                    "port_barycentric", "port_cut_depth_m")
    int_fields = ("source_node_cell_ids", "receiver", "owner_grid", "profile_offsets",
                  "sparse_cell_xy", "triangles", "source_cell_ids",
                  "port_edge_node_indices", "port_triangle_ids")
    bool_fields = ("source_valid_mask", "corridor_mask", "lake_mask")
    if (any(not isinstance(a[key], np.ndarray) or a[key].dtype != np.float64
            for key in float_fields)
            or any(not isinstance(a[key], np.ndarray) or a[key].dtype != np.int64
                   for key in int_fields)
            or any(not isinstance(a[key], np.ndarray) or a[key].dtype != bool
                   for key in bool_fields)):
        raise ValueError("sparse union array dtype mismatch")
    pin = m.get("source_plan_identity_sha256")
    if (not isinstance(pin, str) or len(pin) != 64
            or any(c not in "0123456789abcdef" for c in pin)):
        raise ValueError("source network plan identity missing")
    terrain = TerrainGrid(a["source_height_m"], a["source_valid_mask"], **m["terrain_metadata"])
    if terrain.identity_sha256 != m["source_identity_sha256"]:
        raise ValueError("sparse union source identity mismatch")
    config = GeometryConfig(**m["config"])
    ids, receiver, width, depth = (a[key] for key in ("source_node_cell_ids", "receiver",
                                                   "width_m", "base_depth_m"))
    _check_inputs(terrain, ids, receiver, width, depth, a["owner_grid"],
                  a["corridor_mask"], a["lake_mask"], config)
    if np.unique(a["owner_grid"].ravel()[ids]).size != 1:
        raise ValueError("sparse union component spans owners")
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m,
                              terrain.z0_m + ids // cols * terrain.dz_m))
    if not np.array_equal(a["node_xz_m"], points):
        raise ValueError("sparse union fixed node position mismatch")
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    maxdepth = np.full(len(points), config.max_cut_m)
    _footprint(points, receiver, width, maxdepth, terrain,
               a["owner_grid"], a["corridor_mask"], a["lake_mask"],
               a["owner_grid"].ravel()[ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    for key, expected in zip(("profile_offsets", "profile_t", "profile_source_m",
                              "profile_center_bed_m"), profile):
        if not np.allclose(a[key], expected, rtol=0., atol=1e-9):
            raise ValueError("sparse union profile mismatch")
    cells = _sparse_cells(points, receiver, width, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m,
                                       config.max_vertices)
    if (a["sparse_cell_xy"].shape != cells.shape
            or a["vertices_xz_m"].shape != vertices.shape
            or a["triangles"].shape != triangles.shape):
        raise ValueError("sparse union mesh shape mismatch")
    if (not np.array_equal(a["sparse_cell_xy"], cells)
            or not np.array_equal(a["vertices_xz_m"], vertices)
            or not np.array_equal(a["triangles"], triangles)):
        raise ValueError("unique sparse fan4 incidence mismatch")
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width, profile, vertices, terrain, a["lake_mask"])
    if (np.any(cut > config.max_cut_m + 1e-10)
            or not np.array_equal(a["source_cell_ids"], source_cells)
            or not np.allclose(a["source_elevation_m"], source, rtol=0., atol=1e-9)
            or not np.allclose(a["cut_depth_m"], cut, rtol=0., atol=1e-9)
            or not np.allclose(a["bed_elevation_m"], source - cut, rtol=0., atol=1e-9)):
        raise ValueError("sparse union source/cut field mismatch")
    _cut_source_constraints(vertices, source_cells, cut, terrain, a["owner_grid"],
                            a["corridor_mask"], a["lake_mask"],
                            a["owner_grid"].ravel()[ids[0]])
    _sparse_slope(points, receiver, cells, vertices, triangles, source - cut,
                  config.fine_spacing_m, terrain)
    ports = _sparse_ports(points, receiver, width, profile, cells, vertices, triangles,
                          cut, config.fine_spacing_m, terrain)
    port_keys = ("port_edge_node_indices", "port_xz_m", "port_profile_xz_m",
                 "port_triangle_ids", "port_barycentric", "port_cut_depth_m")
    if (any(not np.allclose(a[key], value, rtol=0., atol=1e-9)
            for key, value in zip(port_keys, ports))
            or not math.isclose(m["cut_volume_m3"], _mesh_volume(vertices, triangles, cut),
                                rel_tol=1e-10, abs_tol=1e-8)):
        raise ValueError("sparse shared port or material ledger mismatch")
    return True


def save_valley_union(path, bundle):
    save_bundle(path, bundle, validator=validate_valley_union)


def load_valley_union(path, *, expected_sha256, expected_identity):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_valley_union, max_bytes=MAX_BYTES)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external sparse union identity mismatch")
    return bundle
