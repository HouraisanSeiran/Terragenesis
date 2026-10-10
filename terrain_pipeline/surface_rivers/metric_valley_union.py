"""One sparse canonical fan4 field for a bounded connected valley graph."""

from dataclasses import asdict
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_channel_geometry import (
    GeometryConfig, BANK_SLOPE, _mesh_volume, _footprint,
    _route_crossings, _sample, _segment_box_distance,
)
from .metric_contracts import TerrainGrid
from .metric_valley_incision import (
    _check_inputs, _metadata_terrain, _profile, _profile_cut,
    _profile_overlap, _profile_max_cut_per_edge,
)


SCHEMA = "terragenesis-sparse-valley-union-v1"
ALGORITHM = "aligned-sparse-fan4-global-max-incision-v2"
MAX_BYTES = 128 * 1024 * 1024


def _sparse_cells(points, receiver, width, profile, config, terrain):
    spacing = config.fine_spacing_m
    origin = np.array([terrain.x0_m, terrain.z0_m])
    maximum = np.array([(terrain.elevation_m.shape[1] - 1) * round(terrain.dx_m / spacing),
                        (terrain.elevation_m.shape[0] - 1) * round(terrain.dz_m / spacing)], np.int64)
    cells = set()
    maximum_cut = _profile_max_cut_per_edge(points, receiver, profile, terrain)
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        radius = max(width[i], width[j]) / 2. + BANK_SLOPE * maximum_cut[edge]
        edge += 1
        a, b = points[i], points[j]
        first = np.maximum(np.floor((np.minimum(a, b) - radius - origin) / spacing).astype(int), 0)
        last = np.minimum(np.ceil((np.maximum(a, b) + radius - origin) / spacing).astype(int), maximum)
        if np.prod(np.maximum(last - first, 0)) > config.max_vertices:
            raise ValueError("sparse footprint preflight vertex budget exceeded")
        for z in range(first[1], last[1]):
            for x in range(first[0], last[0]):
                low = origin + spacing * np.array([x, z])
                if _segment_box_distance(a, b, low, low + spacing) <= radius + 1e-10:
                    cells.add((x, z))
        if len(cells) > config.max_vertices:
            raise ValueError("sparse union cell budget exceeded before meshing")
    if not cells:
        raise ValueError("no sparse channel support cells")
    return np.asarray(sorted(cells, key=lambda item: (item[1], item[0])), np.int64)


def _sparse_mesh(cells, terrain, spacing, max_vertices):
    corners = sorted({(x + ox, z + oz) for x, z in cells
                      for ox, oz in ((0, 0), (1, 0), (1, 1), (0, 1))},
                     key=lambda item: (item[1], item[0]))
    count = len(corners) + len(cells)
    if count > max_vertices:
        raise ValueError("sparse canonical mesh vertex budget exceeded")
    corner_id = {key: index for index, key in enumerate(corners)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    vertices = np.asarray([origin + spacing * np.asarray(key) for key in corners]
                          + [origin + spacing * (cell + .5) for cell in cells], np.float64)
    triangles = np.empty((4 * len(cells), 3), np.int64)
    for index, (x, z) in enumerate(cells):
        sw = corner_id[(x, z)]
        se = corner_id[(x + 1, z)]
        ne = corner_id[(x + 1, z + 1)]
        nw = corner_id[(x, z + 1)]
        center = len(corners) + index
        triangles[4 * index:4 * index + 4] = ((sw, se, center), (se, ne, center),
                                               (ne, nw, center), (nw, sw, center))
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
        grid_breaks = np.unique(breaks)
        for t0, t1 in zip(grid_breaks[:-1], grid_breaks[1:]):
            midpoint = a + (t0 + t1) / 2. * delta
            key = tuple(np.floor((midpoint - origin) / spacing).astype(int))
            if key not in lookup:
                raise ValueError("centerline leaves sparse mesh support")
            low = origin + spacing * np.asarray(key)
            for normal, constant in ((np.array([1., -1.]), 0.),
                                     (np.array([1., 1.]), spacing)):
                denominator = float(normal @ delta)
                if abs(denominator) <= 1e-15:
                    continue
                t = (constant - normal @ (a - low)) / denominator
                if t0 + 1e-12 < t < t1 - 1e-12:
                    breaks.append(t)
        breaks = np.unique(breaks)
        for t0, t1 in zip(breaks[:-1], breaks[1:]):
            midpoint = a + (t0 + t1) / 2. * delta
            key = tuple(np.floor((midpoint - origin) / spacing).astype(int))
            if key not in lookup:
                raise ValueError("centerline leaves sparse mesh support")
            cell = lookup[key]
            h0 = _mesh_height(a + t0 * delta, cell, vertices, triangles, bed)
            h1 = _mesh_height(a + t1 * delta, cell, vertices, triangles, bed)
            if h1 - h0 >= -1e-10 * (t1 - t0):
                raise ValueError("sparse canonical bed is flat or uphill")


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
