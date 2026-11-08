"""Bounded original-bed channel incision on one canonical metric heightfield."""

from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.spatial import cKDTree

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_contracts import TerrainGrid


SCHEMA = "terragenesis-metric-channel-geometry-v1"
ALGORITHM = "original-bed-canonical-fan4-max-cut-v2"
MAX_BYTES = 128 * 1024 * 1024
BANK_SLOPE = 2.
LIMITATIONS = ["fixed original-bed heightfield; no overhangs or below-grid detail",
               "cut volume exact only for represented piecewise-linear mesh",
               "one-hop neighboring reaches may share max-cut support; distant shortcuts refused",
               "no hydraulic, material, natural-mouth, or lake-merger certification"]
ARRAYS = ("source_node_cell_ids", "receiver", "original_node_xz_m", "node_xz_m",
          "node_source_elevation_m", "width_m", "depth_m", "anchor_mask",
          "vertices_xz_m", "source_elevation_m", "cut_depth_m", "bed_elevation_m",
          "triangles", "source_cell_ids", "source_height_m", "source_valid_mask",
          "owner_grid", "corridor_mask", "lake_mask", "canonical_port_edge_node_indices",
          "canonical_port_xz_m", "canonical_port_profile_xz_m",
          "canonical_port_triangle_ids", "canonical_port_barycentric",
          "canonical_port_cut_depth_m")


@dataclass(frozen=True)
class GeometryConfig:
    fine_spacing_m: float = 1.
    width_resolution: float = 4.
    max_cut_m: float = 4.
    max_offset_m: float = 6.
    smoothing_iterations: int = 12
    curvature_weight: float = .25
    valley_weight: float = 1.
    max_vertices: int = 262144

    def __post_init__(self):
        for name in ("fine_spacing_m", "width_resolution", "max_cut_m", "max_offset_m",
                     "curvature_weight", "valley_weight"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(value) or value < 0.:
                raise ValueError(name + " must be finite nonnegative")
            object.__setattr__(self, name, float(value))
        if self.fine_spacing_m <= 0. or self.width_resolution < 2. or self.max_cut_m <= 0. or self.valley_weight <= 0.:
            raise ValueError("geometry spacing/resolution/cut/valley weight outside bounds")
        if any(getattr(self, name) > 1e6 for name in ("fine_spacing_m", "width_resolution",
                                                     "max_cut_m", "max_offset_m",
                                                     "curvature_weight", "valley_weight")):
            raise ValueError("geometry numeric parameter resource bound exceeded")
        if type(self.smoothing_iterations) is not int or not 0 <= self.smoothing_iterations <= 100:
            raise ValueError("bounded smoothing_iterations required")
        if type(self.max_vertices) is not int or not 1 <= self.max_vertices <= 262144:
            raise ValueError("bounded max_vertices required")


def _sample(height, xz, terrain, *, require_valid=True):
    points = np.asarray(xz, np.float64).reshape(-1, 2)
    gx = (points[:, 0] - terrain.x0_m) / terrain.dx_m
    gz = (points[:, 1] - terrain.z0_m) / terrain.dz_m
    rows, cols = height.shape
    if rows < 2 or cols < 2 or not np.isfinite(points).all() or np.any(gx < -1e-10) or np.any(gz < -1e-10) or np.any(gx > cols - 1 + 1e-10) or np.any(gz > rows - 1 + 1e-10):
        raise ValueError("geometry leaves finite source grid")
    gx, gz = np.clip(gx, 0., cols - 1), np.clip(gz, 0., rows - 1)
    x0 = np.minimum(np.floor(gx).astype(np.int64), cols - 2)
    z0 = np.minimum(np.floor(gz).astype(np.int64), rows - 2)
    u, v = gx - x0, gz - z0
    if require_valid:
        mask = terrain.valid_mask
        if not np.all(mask[z0, x0] & mask[z0, x0 + 1] & mask[z0 + 1, x0] & mask[z0 + 1, x0 + 1]):
            raise ValueError("unknown original-bed interpolation stencil")
    value = ((1. - u) * (1. - v) * height[z0, x0] + u * (1. - v) * height[z0, x0 + 1]
             + (1. - u) * v * height[z0 + 1, x0] + u * v * height[z0 + 1, x0 + 1])
    return value, z0 * cols + x0


def _segment_points(a, b, terrain):
    cuts = [0., 1.]
    for axis, origin, spacing in ((0, terrain.x0_m, terrain.dx_m), (1, terrain.z0_m, terrain.dz_m)):
        delta = b[axis] - a[axis]
        if delta == 0.:
            continue
        lo = math.floor((min(a[axis], b[axis]) - origin) / spacing)
        hi = math.ceil((max(a[axis], b[axis]) - origin) / spacing)
        for index in range(lo, hi + 1):
            t = (origin + index * spacing - a[axis]) / delta
            if 1e-12 < t < 1. - 1e-12:
                cuts.append(t)
    cuts = np.unique(np.asarray(cuts))
    return a + cuts[:, None] * (b - a), cuts


def _route_slope(points, receiver, terrain):
    for start, target in enumerate(receiver):
        if target < 0:
            continue
        samples, parameter = _segment_points(points[start], points[target], terrain)
        height, _ = _sample(terrain.elevation_m, samples, terrain)
        if np.any(np.diff(height) >= -1e-10):
            raise ValueError("candidate crosses original-bed flat or uphill segment")
        # A bilinear source restricted to a segment is quadratic within a native cell.
        for k in range(len(parameter) - 1):
            t0, t1 = parameter[k:k + 2]
            middle = points[start] + ((t0 + t1) / 2.) * (points[target] - points[start])
            hm = _sample(terrain.elevation_m, middle, terrain)[0][0]
            left = (4. * hm - 3. * height[k] - height[k + 1]) / (t1 - t0)
            right = (height[k] + 3. * height[k + 1] - 4. * hm) / (t1 - t0)
            if left >= -1e-10 or right >= -1e-10:
                raise ValueError("candidate has uphill original-bed derivative")


def _minimum_source_slope(points, receiver, terrain):
    minimum = math.inf
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        samples, parameter = _segment_points(a, b, terrain)
        height = _sample(terrain.elevation_m, samples, terrain)[0]
        length = float(np.linalg.norm(b - a))
        for k in range(len(parameter) - 1):
            t0, t1 = parameter[k:k + 2]
            middle = a + (t0 + t1) / 2. * (b - a)
            hm = _sample(terrain.elevation_m, middle, terrain)[0][0]
            left = (4. * hm - 3. * height[k] - height[k + 1]) / ((t1 - t0) * length)
            right = (height[k] + 3. * height[k + 1] - 4. * hm) / ((t1 - t0) * length)
            minimum = min(minimum, -left, -right)
    return minimum


def _orientation(a, b, c):
    ab, ac = b - a, c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _segments_intersect(a, b, c, d):
    p = np.array([_orientation(a, b, c), _orientation(a, b, d),
                  _orientation(c, d, a), _orientation(c, d, b)])
    if p[0] * p[1] < 0. and p[2] * p[3] < 0.:
        return True
    for point, start, end, cross in ((c, a, b, p[0]), (d, a, b, p[1]),
                                     (a, c, d, p[2]), (b, c, d, p[3])):
        if abs(cross) <= 1e-10 and np.all(point >= np.minimum(start, end) - 1e-10) and np.all(point <= np.maximum(start, end) + 1e-10):
            return True
    return False


def _route_crossings(points, receiver):
    edges = [(i, int(j)) for i, j in enumerate(receiver) if j >= 0]
    for index, (i, j) in enumerate(edges):
        for k, l in edges[index + 1:]:
            shared = {i, j} & {k, l}
            if shared:
                common = points[next(iter(shared))]
                other1 = points[j if i in shared else i] - common
                other2 = points[l if k in shared else k] - common
                if abs(_orientation(np.zeros(2), other1, other2)) <= 1e-10 and np.dot(other1, other2) > 0.:
                    raise ValueError("adjacent centerline backtracking")
            elif _segments_intersect(points[i], points[j], points[k], points[l]):
                raise ValueError("nonadjacent centerline crossing")


def _segment_box_distance(a, b, low, high):
    delta = b - a
    if np.all(a >= low) and np.all(a <= high) or np.all(b >= low) and np.all(b <= high):
        return 0.
    for axis in (0, 1):
        if delta[axis] == 0.:
            continue
        for boundary in (low[axis], high[axis]):
            t = (boundary - a[axis]) / delta[axis]
            if 0. <= t <= 1. and low[1 - axis] <= a[1 - axis] + t * delta[1 - axis] <= high[1 - axis]:
                return 0.
    endpoint = min(np.linalg.norm(np.maximum(low - p, np.maximum(p - high, 0.))) for p in (a, b))
    corners = (np.array([x, z]) for x in (low[0], high[0]) for z in (low[1], high[1]))
    return min(endpoint, *(np.linalg.norm(c - (a + np.clip(np.dot(c - a, delta) / np.dot(delta, delta), 0., 1.) * delta)) for c in corners))


def _footprint(points, receiver, width, depth, terrain, owner, corridor, lake,
               original_owner, fine_spacing):
    rows, cols = terrain.elevation_m.shape
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        radius = max(width[i] / 2. + BANK_SLOPE * depth[i],
                     width[j] / 2. + BANK_SLOPE * depth[j])
        if (np.any(np.minimum(a, b) - radius < [terrain.x0_m, terrain.z0_m])
                or np.any(np.maximum(a, b) + radius >
                          [terrain.x0_m + (cols - 1) * terrain.dx_m,
                           terrain.z0_m + (rows - 1) * terrain.dz_m])):
            raise ValueError("complete bank footprint leaves source terrain")
        x0 = max(0, math.floor((min(a[0], b[0]) - radius - terrain.x0_m) / terrain.dx_m))
        x1 = min(cols - 2, math.floor((max(a[0], b[0]) + radius - terrain.x0_m) / terrain.dx_m))
        z0 = max(0, math.floor((min(a[1], b[1]) - radius - terrain.z0_m) / terrain.dz_m))
        z1 = min(rows - 2, math.floor((max(a[1], b[1]) + radius - terrain.z0_m) / terrain.dz_m))
        source_owner = original_owner[i]
        if source_owner < 0:
            raise ValueError("unknown source owner")
        for z in range(z0, z1 + 1):
            for x in range(x0, x1 + 1):
                low = np.array([terrain.x0_m + x * terrain.dx_m,
                                terrain.z0_m + z * terrain.dz_m])
                high = low + [terrain.dx_m, terrain.dz_m]
                if _segment_box_distance(a, b, low, high) > radius + 1e-10:
                    continue
                stencil = np.s_[z:z + 2, x:x + 2]
                if (not terrain.valid_mask[stencil].all() or not corridor[stencil].all()
                        or np.any(owner[stencil] != source_owner)):
                    raise ValueError("bank footprint crosses unknown, divide, corridor, or lake")


def _wet_guard(samples, lake, terrain):
    """Protect every native source cell touching known wet support, including mixed cells."""
    wet_cells = lake[:-1, :-1] | lake[:-1, 1:] | lake[1:, :-1] | lake[1:, 1:]
    gx = (samples[:, 0] - terrain.x0_m) / terrain.dx_m
    gz = (samples[:, 1] - terrain.z0_m) / terrain.dz_m
    ix = np.floor(gx + 1e-10).astype(np.int64)
    iz = np.floor(gz + 1e-10).astype(np.int64)
    on_x = np.abs(gx - np.round(gx)) <= 1e-10
    on_z = np.abs(gz - np.round(gz)) <= 1e-10
    protected = np.zeros(len(samples), bool)
    for x in (ix, ix - 1):
        for z in (iz, iz - 1):
            valid = (x >= 0) & (x < wet_cells.shape[1]) & (z >= 0) & (z < wet_cells.shape[0])
            valid &= (x == ix) | on_x
            valid &= (z == iz) | on_z
            protected[valid] |= wet_cells[z[valid], x[valid]]
    return protected


def _cut(points, receiver, width, depth, samples, *, lake=None, terrain=None):
    cut = np.zeros(len(samples), np.float64)
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        delta = b - a
        fraction = np.clip((samples - a) @ delta / np.dot(delta, delta), 0., 1.)
        distance = np.linalg.norm(samples - (a + fraction[:, None] * delta), axis=1)
        half_width = ((1. - fraction) * width[i] + fraction * width[j]) / 2.
        local_depth = (1. - fraction) * depth[i] + fraction * depth[j]
        bank = BANK_SLOPE * local_depth
        envelope = np.where(distance <= half_width, local_depth,
                            np.maximum(0., (half_width + bank - distance) / BANK_SLOPE))
        cut = np.maximum(cut, envelope)
    if lake is not None and lake.any():
        wet_cells = lake[:-1, :-1] | lake[:-1, 1:] | lake[1:, :-1] | lake[1:, 1:]
        rows, cols = np.nonzero(wet_cells)
        centers = np.column_stack((terrain.x0_m + (cols + .5) * terrain.dx_m,
                                   terrain.z0_m + (rows + .5) * terrain.dz_m))
        distance = cKDTree(centers).query(samples)[0]
        lower_bound = np.maximum(0., distance - math.hypot(terrain.dx_m, terrain.dz_m) / 2.)
        taper_rate = _minimum_source_slope(points, receiver, terrain) * .25
        cut = np.minimum(cut, lower_bound * taper_rate)
        cut[_wet_guard(samples, lake, terrain)] = 0.
    return cut


def _point_segment_distance(point, start, end):
    delta = end - start
    fraction = np.clip(np.dot(point - start, delta) / np.dot(delta, delta), 0., 1.)
    return float(np.linalg.norm(point - start - fraction * delta))


def _cut_overlap(points, receiver, width, depth):
    edges = [(i, int(j)) for i, j in enumerate(receiver) if j >= 0]
    adjacent = {frozenset((i, j)) for i, j in edges}
    for index, (i, j) in enumerate(edges):
        for other, (k, l) in enumerate(edges[index + 1:], start=index + 1):
            nearby = bool({i, j} & {k, l}) or any(
                frozenset((a, b)) in adjacent for a in (i, j) for b in (k, l))
            if nearby:
                continue
            radius1 = max(width[i] / 2. + BANK_SLOPE * depth[i],
                          width[j] / 2. + BANK_SLOPE * depth[j])
            radius2 = max(width[k] / 2. + BANK_SLOPE * depth[k],
                          width[l] / 2. + BANK_SLOPE * depth[l])
            distance = min(_point_segment_distance(p, points[k], points[l])
                           for p in (points[i], points[j]))
            distance = min(distance, *(_point_segment_distance(p, points[i], points[j])
                                           for p in (points[k], points[l])))
            if distance <= radius1 + radius2 + 1e-10:
                raise ValueError("nonadjacent cut supports overlap")


def _modified_bed_slope(points, receiver, vertices, triangles, bed, spacing):
    origin = vertices[0]
    nx = int(triangles[2, 1])
    nz = int(triangles[0, 2]) // nx
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        delta = b - a
        parameters = [0., 1.]
        for axis in (0, 1):
            if abs(delta[axis]) <= 1e-15:
                continue
            for index in range(int(math.floor((min(a[axis], b[axis]) - origin[axis]) / spacing)),
                               int(math.ceil((max(a[axis], b[axis]) - origin[axis]) / spacing)) + 1):
                t = (origin[axis] + index * spacing - a[axis]) / delta[axis]
                if 1e-12 < t < 1. - 1e-12:
                    parameters.append(t)
        grid_breaks = np.unique(parameters)
        for t0, t1 in zip(grid_breaks[:-1], grid_breaks[1:]):
            middle = a + (t0 + t1) / 2. * delta
            col = min(max(int(math.floor((middle[0] - origin[0]) / spacing)), 0), nx - 2)
            row = min(max(int(math.floor((middle[1] - origin[1]) / spacing)), 0), nz - 2)
            low = origin + np.array([col, row]) * spacing
            for normal, constant in ((np.array([1., -1.]), 0.),
                                     (np.array([1., 1.]), spacing)):
                divisor = float(np.dot(normal, delta))
                if abs(divisor) <= 1e-15:
                    continue
                t = (constant - np.dot(normal, a - low)) / divisor
                if t0 + 1e-12 < t < t1 - 1e-12:
                    parameters.append(t)
        parameters = np.unique(parameters)
        for t0, t1 in zip(parameters[:-1], parameters[1:]):
            middle = a + (t0 + t1) / 2. * delta
            col = min(max(int(math.floor((middle[0] - origin[0]) / spacing)), 0), nx - 2)
            row = min(max(int(math.floor((middle[1] - origin[1]) / spacing)), 0), nz - 2)
            cell = row * (nx - 1) + col
            for tri_id in range(4 * cell, 4 * cell + 4):
                ids = triangles[tri_id]
                triangle = vertices[ids]
                matrix = np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0]))
                uv = np.linalg.solve(matrix, middle - triangle[0])
                if min(1. - uv.sum(), uv[0], uv[1]) < -1e-9:
                    continue
                h = []
                for t in (t0, t1):
                    uv = np.linalg.solve(matrix, a + t * delta - triangle[0])
                    h.append(bed[ids[0]] + uv @ (bed[ids[1:]] - bed[ids[0]]))
                if h[1] - h[0] >= -1e-10 * (t1 - t0):
                    raise ValueError("canonical cut bed is flat or uphill")
                break
            else:
                raise ValueError("centerline leaves canonical mesh")


def _mesh(points, receiver, width, depth, terrain, config):
    radius = float(np.max(width / 2. + BANK_SLOPE * depth))
    spacing = config.fine_spacing_m
    first = np.floor((np.min(points, axis=0) - radius - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int)
    last = np.ceil((np.max(points, axis=0) + radius - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int)
    first = np.maximum(first, 0)
    last = np.minimum(last, np.array([(terrain.elevation_m.shape[1] - 1) * int(round(terrain.dx_m / spacing)),
                                      (terrain.elevation_m.shape[0] - 1) * int(round(terrain.dz_m / spacing))]))
    nx, nz = int(last[0] - first[0] + 1), int(last[1] - first[1] + 1)
    if nx < 2 or nz < 2 or nx * nz + (nx - 1) * (nz - 1) > config.max_vertices:
        raise ValueError("geometry vertex budget exceeded")
    x = terrain.x0_m + np.arange(first[0], last[0] + 1) * spacing
    z = terrain.z0_m + np.arange(first[1], last[1] + 1) * spacing
    xx, zz = np.meshgrid(x, z)
    corners = np.column_stack((xx.ravel(), zz.ravel()))
    centers = np.column_stack(((xx[:-1, :-1] + spacing / 2.).ravel(),
                               (zz[:-1, :-1] + spacing / 2.).ravel()))
    vertices = np.vstack((corners, centers))
    triangles = np.empty((4 * (nx - 1) * (nz - 1), 3), np.int64)
    cell = 0
    for row in range(nz - 1):
        for col in range(nx - 1):
            sw = row * nx + col
            se, nw, ne = sw + 1, sw + nx, sw + nx + 1
            center = nx * nz + cell
            triangles[4 * cell:4 * cell + 4] = ((sw, se, center), (se, ne, center),
                                                (ne, nw, center), (nw, sw, center))
            cell += 1
    return vertices, triangles


def _validate_fan_mesh(vertices, triangles, points, width, depth, terrain, config):
    if (vertices.dtype != np.float64 or vertices.ndim != 2 or vertices.shape[1] != 2
            or not np.isfinite(vertices).all() or vertices.shape[0] > config.max_vertices
            or triangles.dtype != np.int64 or triangles.ndim != 2 or triangles.shape[1] != 3
            or len(triangles) < 4 or len(triangles) % 4):
        raise ValueError("invalid canonical fan4 arrays")
    corner_count = int(triangles[0, 2])
    nx = int(triangles[2, 1])
    if nx < 2 or corner_count % nx:
        raise ValueError("invalid canonical fan4 dimensions")
    nz = corner_count // nx
    if nz < 2 or corner_count + (nx - 1) * (nz - 1) != len(vertices) or len(triangles) != 4 * (nx - 1) * (nz - 1):
        raise ValueError("invalid canonical fan4 dimensions")
    spacing = config.fine_spacing_m
    first = vertices[0]
    radius = float(np.max(width / 2. + BANK_SLOPE * depth))
    lower = np.maximum(np.floor((np.min(points, axis=0) - radius
                                 - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int), 0)
    upper = np.minimum(np.ceil((np.max(points, axis=0) + radius
                                - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int),
                       [(terrain.elevation_m.shape[1] - 1) * int(round(terrain.dx_m / spacing)),
                        (terrain.elevation_m.shape[0] - 1) * int(round(terrain.dz_m / spacing))])
    if (nx != upper[0] - lower[0] + 1 or nz != upper[1] - lower[1] + 1
            or not np.allclose(first, [terrain.x0_m + lower[0] * spacing,
                                      terrain.z0_m + lower[1] * spacing], rtol=0., atol=1e-10)):
        raise ValueError("canonical mesh does not cover declared channel support")
    for row in range(nz):
        for col in range(nx):
            expected = first + [col * spacing, row * spacing]
            if not np.allclose(vertices[row * nx + col], expected, rtol=0., atol=1e-10):
                raise ValueError("canonical fan4 corner coordinate mismatch")
    for row in range(nz - 1):
        for col in range(nx - 1):
            cell = row * (nx - 1) + col
            sw = row * nx + col
            se, nw, ne = sw + 1, sw + nx, sw + nx + 1
            center = corner_count + cell
            if not np.allclose(vertices[center], vertices[sw] + spacing / 2., rtol=0., atol=1e-10):
                raise ValueError("canonical fan4 center coordinate mismatch")
            expected = ((sw, se, center), (se, ne, center),
                        (ne, nw, center), (nw, sw, center))
            if not np.array_equal(triangles[4 * cell:4 * cell + 4], expected):
                raise ValueError("canonical fan4 triangle incidence mismatch")


def _mesh_volume(vertices, triangles, heights, *, datum=0.):
    xy = vertices[triangles]
    area = np.abs((xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1])
                  - (xy[:, 2, 0] - xy[:, 0, 0]) * (xy[:, 1, 1] - xy[:, 0, 1])) / 2.
    return float(np.sum(area * np.mean(heights[triangles] - datum, axis=1)))


def _port_observations(points, receiver, width, depth, vertices, triangles, cut):
    edges = np.array([(i, int(j)) for i, j in enumerate(receiver) if j >= 0], np.int64).reshape(-1, 2)
    profile = np.empty((len(edges), 4, 2), np.float64)
    midpoint = np.empty((len(edges), 2), np.float64)
    triangle_ids = np.empty((len(edges), 4), np.int64)
    barycentric = np.empty((len(edges), 4, 3), np.float64)
    cuts = np.empty((len(edges), 4), np.float64)
    # Regular fan cells can be queried locally by their lower-left grid corner.
    x0, z0 = np.min(vertices, axis=0)
    xs = np.unique(vertices[:, 0])
    zs = np.unique(vertices[:, 1])
    spacing = 2. * (xs[1] - xs[0])
    nx = int(round((xs[-1] - xs[0]) / spacing)) + 1
    nz = int(round((zs[-1] - zs[0]) / spacing)) + 1
    for edge_index, (i, j) in enumerate(edges):
        a, b = points[i], points[j]
        center = (a + b) / 2.
        flow = (b - a) / np.linalg.norm(b - a)
        normal = np.array([-flow[1], flow[0]])
        half = (width[i] + width[j]) / 4.
        bank = BANK_SLOPE * (depth[i] + depth[j]) / 2.
        offsets = (-half - bank, -half, half, half + bank)
        midpoint[edge_index] = center
        for k, offset in enumerate(offsets):
            p = center + offset * normal
            profile[edge_index, k] = p
            cx = min(max(math.floor((p[0] - x0) / spacing), 0), nx - 2)
            cz = min(max(math.floor((p[1] - z0) / spacing), 0), nz - 2)
            square = cz * (nx - 1) + cx
            found = False
            for tri_id in range(4 * square, 4 * square + 4):
                triangle = vertices[triangles[tri_id]]
                matrix = np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0]))
                uv = np.linalg.solve(matrix, p - triangle[0])
                weights = np.array([1. - uv.sum(), uv[0], uv[1]])
                if np.min(weights) >= -1e-9:
                    triangle_ids[edge_index, k] = tri_id
                    barycentric[edge_index, k] = weights
                    cuts[edge_index, k] = weights @ cut[triangles[tri_id]]
                    found = True
                    break
            if not found:
                raise ValueError("canonical port leaves represented mesh")
    return edges, midpoint, profile, triangle_ids, barycentric, cuts


def _terrain_metadata(terrain):
    return {key: getattr(terrain, key) for key in terrain.__dataclass_fields__
            if key not in ("elevation_m", "valid_mask")}


def _constraints_identity(arrays, terrain_identity):
    return identity({key: arrays[key] for key in ("owner_grid", "corridor_mask",
                                                  "lake_mask", "anchor_mask")},
                    {"terrain_identity_sha256": terrain_identity,
                     "provenance": "explicit_caller_supplied_unverified_source_masks"})


def _topology(ids, receiver, terrain):
    n = len(ids)
    if (ids.dtype != np.int64 or ids.shape != (n,) or not 2 <= n <= 128
            or np.unique(ids).size != n or np.any(ids < 0) or np.any(ids >= terrain.elevation_m.size)
            or not terrain.valid_mask.ravel()[ids].all()
            or receiver.dtype != np.int64 or receiver.shape != (n,)
            or np.any((receiver < -1) | (receiver >= n) | (receiver == np.arange(n)))):
        raise ValueError("invalid bounded selected source graph")
    for start in range(n):
        seen = set()
        current = start
        while current >= 0:
            if current in seen:
                raise ValueError("selected channel graph cycle")
            seen.add(current)
            current = int(receiver[current])


def _inputs(terrain, ids, receiver, width, depth, owner, corridor, lake, anchors, config, lake_stage):
    if not isinstance(terrain, TerrainGrid) or not isinstance(config, GeometryConfig):
        raise ValueError("TerrainGrid and GeometryConfig required")
    _topology(ids, receiver, terrain)
    n = len(ids)
    for name, value in (("width_m", width), ("depth_m", depth)):
        if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != (n,) or not np.isfinite(value).all() or np.any(value <= 0.):
            raise ValueError("finite positive physical " + name + " required")
    if np.any(depth > config.max_cut_m):
        raise ValueError("requested channel cut exceeds max_cut_m")
    if not np.isfinite(width / 2. + BANK_SLOPE * depth).all():
        raise ValueError("nonfinite bank support radius")
    shape = terrain.elevation_m.shape
    if (not isinstance(owner, np.ndarray) or owner.dtype != np.int64 or owner.shape != shape
            or not isinstance(corridor, np.ndarray) or corridor.dtype != bool or corridor.shape != shape
            or not isinstance(lake, np.ndarray) or lake.dtype != bool or lake.shape != shape
            or not isinstance(anchors, np.ndarray) or anchors.dtype != bool or anchors.shape != (n,)):
        raise ValueError("source owner/corridor/lake/anchor arrays required")
    if lake_stage is not None and (isinstance(lake_stage, bool) or not isinstance(lake_stage, (int, float)) or not math.isfinite(lake_stage)):
        raise ValueError("finite explicit lake_stage_m required")
    if lake.ravel()[ids].any() and lake_stage is None:
        raise ValueError("lake endpoint requires explicit lake stage")
    if np.any(lake.ravel()[ids] & (receiver >= 0)):
        raise ValueError("interior centerline cannot enter lake support")
    if not np.any(receiver >= 0):
        raise ValueError("selected channel requires at least one original-bed edge")
    selected_owner = owner.ravel()[ids]
    if np.any(selected_owner < 0) or np.any(~corridor.ravel()[ids]) or np.any(
            (receiver >= 0) & (selected_owner != selected_owner[np.maximum(receiver, 0)])):
        raise ValueError("selected source nodes cross owner or corridor")
    if lake.ravel()[ids].any() and lake_stage < np.max(terrain.elevation_m.ravel()[ids[lake.ravel()[ids]]]):
        raise ValueError("lake stage does not cover original wet terminal bed")
    if not math.isclose(terrain.dx_m / config.fine_spacing_m, round(terrain.dx_m / config.fine_spacing_m), abs_tol=1e-10) or not math.isclose(terrain.dz_m / config.fine_spacing_m, round(terrain.dz_m / config.fine_spacing_m), abs_tol=1e-10):
        raise ValueError("fine spacing must divide both native grid spacings")
    if config.fine_spacing_m > np.min(width) / config.width_resolution:
        raise ValueError("channel width underresolved by fine lattice")


def build_channel_geometry(terrain, node_cell_ids, receiver, width_m, depth_m, *, owner_grid,
                           corridor_mask, lake_mask, anchor_mask, config=None, lake_stage_m=None):
    if config is None:
        config = GeometryConfig()
    _inputs(terrain, node_cell_ids, receiver, width_m, depth_m, owner_grid,
            corridor_mask, lake_mask, anchor_mask, config, lake_stage_m)
    cols = terrain.elevation_m.shape[1]
    original = np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m,
                                terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    effective_depth = depth_m.copy()
    effective_depth[lake_mask.ravel()[node_cell_ids]] = 0.
    original_owner = owner_grid.ravel()[node_cell_ids]
    points = original.copy()
    donors = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    lake_nodes = lake_mask.ravel()[node_cell_ids]
    fixed = anchor_mask | (donors != 1) | (receiver < 0) | lake_nodes
    fixed |= (receiver >= 0) & lake_nodes[np.maximum(receiver, 0)]
    _route_slope(points, receiver, terrain)
    _route_crossings(points, receiver)
    # Local coordinate descent can only accept a lower original-bed + curvature objective.
    for iteration in range(config.smoothing_iterations):
        changed = False
        step = config.max_offset_m / (2. ** (iteration // 4 + 1))
        if step <= 0.:
            break
        for i in np.flatnonzero(~fixed):
            donor = int(np.flatnonzero(receiver == i)[0])
            target = int(receiver[i])
            bend = (points[donor] + points[target]) / 2.
            scale = min(terrain.dx_m, terrain.dz_m)
            def objective(p):
                height = _sample(terrain.elevation_m, p, terrain)[0][0]
                return config.valley_weight * height + config.curvature_weight * np.linalg.norm(p - bend) ** 2 / scale
            best = points[i].copy()
            best_score = objective(best)
            for offset in ((step, 0.), (-step, 0.), (0., step), (0., -step)):
                candidate = points[i] + offset
                if np.linalg.norm(candidate - original[i]) > config.max_offset_m:
                    continue
                trial = points.copy()
                trial[i] = candidate
                try:
                    _sample(terrain.elevation_m, candidate, terrain)
                    _route_slope(trial, receiver, terrain)
                    _route_crossings(trial, receiver)
                    _footprint(trial, receiver, width_m, effective_depth, terrain, owner_grid, corridor_mask, lake_mask, original_owner, config.fine_spacing_m)
                except ValueError:
                    continue
                score = objective(candidate)
                if score < best_score - 1e-12:
                    best, best_score = candidate, score
            if not np.array_equal(best, points[i]):
                points[i] = best
                changed = True
        if not changed and iteration >= 4:
            break
    _route_slope(points, receiver, terrain)
    _route_crossings(points, receiver)
    _footprint(points, receiver, width_m, effective_depth, terrain, owner_grid, corridor_mask, lake_mask, original_owner, config.fine_spacing_m)
    vertices, triangles = _mesh(points, receiver, width_m, effective_depth, terrain, config)
    _cut_overlap(points, receiver, width_m, effective_depth)
    source, source_cell_ids = _sample(terrain.elevation_m, vertices, terrain)
    cut = _cut(points, receiver, width_m, effective_depth, vertices,
               lake=lake_mask, terrain=terrain)
    if not np.isfinite(cut).all() or np.any(cut < 0.) or np.any(cut > config.max_cut_m + 1e-12):
        raise ValueError("invalid represented cut depth")
    bed = source - cut
    _modified_bed_slope(points, receiver, vertices, triangles, bed, config.fine_spacing_m)
    edges, midpoint, profile, port_tri, bary, port_cut = _port_observations(
        points, receiver, width_m, effective_depth, vertices, triangles, cut)
    volume = _mesh_volume(vertices, triangles, cut)
    datum = float(source[0])
    source_volume = _mesh_volume(vertices, triangles, source, datum=datum)
    final_volume = _mesh_volume(vertices, triangles, bed, datum=datum)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(),
                  original_node_xz_m=original, node_xz_m=points,
                  node_source_elevation_m=_sample(terrain.elevation_m, points, terrain)[0],
                  width_m=width_m.copy(), depth_m=depth_m.copy(), anchor_mask=anchor_mask.copy(),
                  vertices_xz_m=vertices, source_elevation_m=source,
                  cut_depth_m=cut, bed_elevation_m=bed, triangles=triangles,
                  source_cell_ids=source_cell_ids,
                  source_height_m=terrain.elevation_m.copy(),
                  source_valid_mask=terrain.valid_mask.copy(), owner_grid=owner_grid.copy(),
                  corridor_mask=corridor_mask.copy(), lake_mask=lake_mask.copy(),
                  canonical_port_edge_node_indices=edges,
                  canonical_port_xz_m=midpoint, canonical_port_profile_xz_m=profile,
                  canonical_port_triangle_ids=port_tri, canonical_port_barycentric=bary,
                  canonical_port_cut_depth_m=port_cut)
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, terrain_metadata=_terrain_metadata(terrain),
                    source_identity_sha256=terrain.identity_sha256,
                    constraints_identity_sha256=_constraints_identity(arrays, terrain.identity_sha256),
                    constraints_provenance="explicit_caller_supplied_unverified_source_masks",
                    config=asdict(config), lake_stage_m=lake_stage_m,
                    lake_cut_policy="zero_on_native_cells_touching_known_wet_nodes",
                    bank_slope_h_per_v=BANK_SLOPE,
                    geometry_measure="canonical_piecewise_linear_heightfield",
                    cut_volume_m3=volume, deposition_bulk_m3=0.,
                    original_mesh_volume_m3=source_volume,
                    final_mesh_volume_m3=final_volume,
                    geometry_verified=True, hydraulic_ready=False,
                    natural_outlet_verified=False, publishable=False,
                    limitations=list(LIMITATIONS))
    arrays = {name: readonly(value) for name, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata,
              "identity_sha256": identity(arrays, metadata)}
    validate_channel_geometry(bundle)
    return bundle


def validate_channel_geometry(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid channel geometry bundle")
    arrays, meta = bundle["arrays"], bundle["metadata"]
    if (set(arrays) != set(ARRAYS) or set(meta) != {"schema", "algorithm", "terrain_metadata",
            "source_identity_sha256", "constraints_identity_sha256", "constraints_provenance",
            "config", "lake_stage_m", "lake_cut_policy", "bank_slope_h_per_v",
            "geometry_measure", "cut_volume_m3", "deposition_bulk_m3", "original_mesh_volume_m3",
            "final_mesh_volume_m3", "geometry_verified", "hydraulic_ready",
            "natural_outlet_verified", "publishable", "limitations"}
            or meta["schema"] != SCHEMA or meta["algorithm"] != ALGORITHM
            or meta["bank_slope_h_per_v"] != BANK_SLOPE
            or meta["geometry_measure"] != "canonical_piecewise_linear_heightfield"
            or meta["lake_cut_policy"] != "zero_on_native_cells_touching_known_wet_nodes"
            or meta["limitations"] != LIMITATIONS or meta["geometry_verified"] is not True
            or meta["constraints_provenance"] != "explicit_caller_supplied_unverified_source_masks"
            or meta["constraints_identity_sha256"] != _constraints_identity(arrays, meta["source_identity_sha256"])
            or any(meta[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or bundle["identity_sha256"] != identity(arrays, meta)
            or sum(value.nbytes for value in arrays.values()) > MAX_BYTES):
        raise ValueError("geometry schema, scope, identity, or budget mismatch")
    config = GeometryConfig(**meta["config"])
    terrain = TerrainGrid(arrays["source_height_m"], arrays["source_valid_mask"],
                          **meta["terrain_metadata"])
    if terrain.identity_sha256 != meta["source_identity_sha256"]:
        raise ValueError("source identity mismatch")
    ids, receiver, width, depth = (arrays[key] for key in
                                   ("source_node_cell_ids", "receiver", "width_m", "depth_m"))
    _inputs(terrain, ids, receiver, width, depth, arrays["owner_grid"],
            arrays["corridor_mask"], arrays["lake_mask"], arrays["anchor_mask"],
            config, meta["lake_stage_m"])
    cols = terrain.elevation_m.shape[1]
    original = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m,
                                terrain.z0_m + ids // cols * terrain.dz_m))
    points = arrays["node_xz_m"]
    donors = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    lake_nodes = arrays["lake_mask"].ravel()[ids]
    fixed = arrays["anchor_mask"] | (donors != 1) | (receiver < 0) | lake_nodes
    fixed |= (receiver >= 0) & lake_nodes[np.maximum(receiver, 0)]
    if (points.dtype != np.float64 or points.shape != original.shape or not np.isfinite(points).all()
            or not np.array_equal(arrays["original_node_xz_m"], original)
            or not np.array_equal(points[fixed], original[fixed])
            or np.any(np.linalg.norm(points - original, axis=1) > config.max_offset_m + 1e-10)):
        raise ValueError("invalid candidate centerline anchors or offsets")
    source_node = _sample(terrain.elevation_m, points, terrain)[0]
    if not np.allclose(arrays["node_source_elevation_m"], source_node, rtol=0., atol=1e-9):
        raise ValueError("candidate centerline original-bed samples mismatch")
    _route_slope(points, receiver, terrain)
    _route_crossings(points, receiver)
    effective_depth = depth.copy()
    effective_depth[arrays["lake_mask"].ravel()[ids]] = 0.
    _footprint(points, receiver, width, effective_depth, terrain, arrays["owner_grid"],
               arrays["corridor_mask"], arrays["lake_mask"], arrays["owner_grid"].ravel()[ids],
               config.fine_spacing_m)
    vertices, triangles = arrays["vertices_xz_m"], arrays["triangles"]
    _validate_fan_mesh(vertices, triangles, points, width, effective_depth, terrain, config)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    _cut_overlap(points, receiver, width, effective_depth)
    cut = _cut(points, receiver, width, effective_depth, vertices,
               lake=arrays["lake_mask"], terrain=terrain)
    if (not np.array_equal(arrays["source_cell_ids"], source_cells)
            or not np.allclose(arrays["source_elevation_m"], source, rtol=0., atol=1e-9)
            or not np.allclose(arrays["cut_depth_m"], cut, rtol=0., atol=1e-9)
            or not np.allclose(arrays["bed_elevation_m"], source - cut, rtol=0., atol=1e-9)):
        raise ValueError("original-source interpolation or cut field mismatch")
    _modified_bed_slope(points, receiver, vertices, triangles, source - cut,
                        config.fine_spacing_m)
    port_fields = ("canonical_port_edge_node_indices", "canonical_port_xz_m",
                   "canonical_port_profile_xz_m", "canonical_port_triangle_ids",
                   "canonical_port_barycentric", "canonical_port_cut_depth_m")
    expected = _port_observations(points, receiver, width, effective_depth, vertices, triangles, cut)
    if any(not np.allclose(arrays[key], value, rtol=0., atol=1e-9)
           for key, value in zip(port_fields, expected)):
        raise ValueError("canonical shared mesh port mismatch")
    volume = _mesh_volume(vertices, triangles, cut)
    datum = float(source[0])
    source_volume = _mesh_volume(vertices, triangles, source, datum=datum)
    final_volume = _mesh_volume(vertices, triangles, source - cut, datum=datum)
    if (not np.isfinite([volume, source_volume]).all() or volume < 0.
            or not math.isclose(meta["cut_volume_m3"], volume, rel_tol=1e-10, abs_tol=1e-8)
            or meta["deposition_bulk_m3"] != 0.
            or not math.isclose(meta["original_mesh_volume_m3"], source_volume, rel_tol=1e-10, abs_tol=1e-8)
            or not math.isclose(meta["final_mesh_volume_m3"], final_volume,
                                rel_tol=1e-10, abs_tol=1e-8)):
        raise ValueError("canonical cut volume ledger mismatch")
    return True


def save_channel_geometry(path, bundle):
    save_bundle(path, bundle, validator=validate_channel_geometry)


def load_channel_geometry(path, *, expected_sha256, expected_identity):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_channel_geometry, max_bytes=MAX_BYTES)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external geometry identity mismatch")
    return bundle
