"""Bounded fixed-XZ incision through original-bed bilinear local reversals."""

from dataclasses import asdict
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.common_infra import TerrainGrid
from .metric_channel_geometry import (
    GeometryConfig, BANK_SLOPE, _cut_overlap, _footprint, _mesh, _mesh_volume,
    _modified_bed_slope, _port_observations, _route_crossings, _sample,
    _segment_points, _topology, _validate_fan_mesh, _wet_guard,
    _point_segment_distance,
)


SCHEMA = "terragenesis-metric-valley-incision-v1"
ALGORITHM = "fixed-xz-running-min-original-bilinear-incision-v3"
MAX_BYTES = 128 * 1024 * 1024
EPSILON_SLOPE_M_PER_M = 1e-5
ARRAYS = ("source_node_cell_ids", "receiver", "node_xz_m", "width_m",
          "base_depth_m", "source_height_m", "source_valid_mask", "owner_grid",
          "corridor_mask", "lake_mask", "profile_offsets", "profile_t",
          "profile_source_m", "profile_center_bed_m", "vertices_xz_m",
          "source_elevation_m", "cut_depth_m", "bed_elevation_m", "triangles",
          "source_cell_ids", "canonical_port_edge_node_indices",
          "canonical_port_xz_m", "canonical_port_profile_xz_m",
          "canonical_port_triangle_ids", "canonical_port_barycentric",
          "canonical_port_cut_depth_m")


def _metadata_terrain(terrain):
    return {key: getattr(terrain, key) for key in terrain.__dataclass_fields__
            if key not in ("elevation_m", "valid_mask")}


def _profile(points, receiver, depth, terrain, max_cut_m):
    offsets = [0]
    parameters = []
    sources = []
    beds = []
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        samples, knots = _segment_points(a, b, terrain)
        values = _sample(terrain.elevation_m, samples, terrain)[0]
        length = float(np.linalg.norm(b - a))
        extra = []
        for k in range(len(knots) - 1):
            t0, t1 = knots[k:k + 2]
            tm = (t0 + t1) / 2.
            vm = _sample(terrain.elevation_m, a + tm * (b - a), terrain)[0][0]
            curvature = 2. * (values[k] + values[k + 1] - 2. * vm) / (t1 - t0) ** 2
            left_derivative = (values[k + 1] - values[k]) / (t1 - t0) - curvature * (t1 - t0)
            tilted_derivative = left_derivative - (depth[j] - depth[i]) + EPSILON_SLOPE_M_PER_M * length
            stationary = t0 - tilted_derivative / (2. * curvature) if abs(curvature) > 1e-14 else -1.
            if t0 + 1e-12 < stationary < t1 - 1e-12:
                extra.append(stationary)
        knots = np.unique(np.r_[knots, extra])
        # A rising quadratic can cross its previous minimum inside the next span.
        # Preserve that crossing so the monotone envelope is exact at every branch.
        crossings = []
        current_min = math.inf
        for k in range(len(knots) - 1):
            t0, t1 = knots[k:k + 2]
            ts = np.array([t0, (t0 + t1) / 2., t1])
            values3 = _sample(terrain.elevation_m, a + ts[:, None] * (b - a), terrain)[0]
            tilted3 = values3 - ((1. - ts) * depth[i] + ts * depth[j]) + EPSILON_SLOPE_M_PER_M * length * ts
            current_min = min(current_min, float(tilted3[0]))
            du = t1 - t0
            curvature = 2. * (tilted3[0] + tilted3[2] - 2. * tilted3[1]) / du ** 2
            linear = (tilted3[2] - tilted3[0]) / du - curvature * du
            constant = tilted3[0] - current_min
            roots = np.roots([curvature, linear, constant]) if abs(curvature) > 1e-14 else (
                np.array([-constant / linear]) if abs(linear) > 1e-14 else np.empty(0))
            for root in roots:
                if abs(np.imag(root)) <= 1e-10 and 1e-12 < np.real(root) < du - 1e-12:
                    crossings.append(t0 + float(np.real(root)))
            current_min = min(current_min, float(tilted3[2]))
        knots = np.unique(np.r_[knots, crossings])
        samples = a + knots[:, None] * (b - a)
        values = _sample(terrain.elevation_m, samples, terrain)[0]
        baseline = values - ((1. - knots) * depth[i] + knots * depth[j])
        tilted = baseline + EPSILON_SLOPE_M_PER_M * length * knots
        center_bed = np.minimum.accumulate(tilted) - EPSILON_SLOPE_M_PER_M * length * knots
        if (center_bed[0] != baseline[0]
                or center_bed[-1] < baseline[-1] - 1e-9):
            raise ValueError("fixed endpoint needs additional shared-node incision")
        maximum_cut = float(np.max(values - center_bed))
        for k in range(len(knots) - 1):
            t0, t1 = knots[k:k + 2]
            middle = (t0 + t1) / 2.
            source_middle = _sample(terrain.elevation_m, a + middle * (b - a), terrain)[0][0]
            curvature = 2. * (values[k] + values[k + 1] - 2. * source_middle) / (t1 - t0) ** 2
            source_left_derivative = (values[k + 1] - values[k]) / (t1 - t0) - curvature * (t1 - t0)
            bed_derivative = (center_bed[k + 1] - center_bed[k]) / (t1 - t0)
            stationary = t0 - (source_left_derivative - bed_derivative) / (2. * curvature) if abs(curvature) > 1e-14 else -1.
            if t0 < stationary < t1:
                height = _sample(terrain.elevation_m, a + stationary * (b - a), terrain)[0][0]
                target = np.interp(stationary, knots[k:k + 2], center_bed[k:k + 2])
                maximum_cut = max(maximum_cut, float(height - target))
        if maximum_cut > max_cut_m + 1e-9:
            raise ValueError("continuous centerline incision exceeds configured maximum")
        parameters.extend(knots)
        sources.extend(values)
        beds.extend(center_bed)
        offsets.append(len(parameters))
    return (np.asarray(offsets, np.int64), np.asarray(parameters, np.float64),
            np.asarray(sources, np.float64), np.asarray(beds, np.float64))


def _profile_cut(points, receiver, width, profile, samples, terrain, lake):
    offsets, knots, _, center_bed = profile
    cut = np.zeros(len(samples), np.float64)
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        delta = b - a
        t = np.clip((samples - a) @ delta / np.dot(delta, delta), 0., 1.)
        position = a + t[:, None] * delta
        distance = np.linalg.norm(samples - position, axis=1)
        source_at_center = _sample(terrain.elevation_m, position, terrain)[0]
        lo, hi = offsets[edge:edge + 2]
        target = np.interp(t, knots[lo:hi], center_bed[lo:hi])
        depth = np.maximum(source_at_center - target, 0.)
        half = ((1. - t) * width[i] + t * width[j]) / 2.
        envelope = np.where(distance <= half, depth,
                            np.maximum(0., (half + BANK_SLOPE * depth - distance) / BANK_SLOPE))
        cut = np.maximum(cut, envelope)
        edge += 1
    if lake.any():
        guarded = _wet_guard(samples, lake, terrain)
        if np.any(cut[guarded] > 1e-10):
            raise ValueError("incision enters protected known-wet source cells")
    return cut


def _profile_max_cut_per_edge(points, receiver, profile, terrain):
    """Maximum original bilinear source minus linear profile bed on each edge."""
    offsets, knots, source, bed = profile
    maximum = []
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        lo, hi = offsets[edge:edge + 2]
        amount = float(np.max(source[lo:hi] - bed[lo:hi]))
        a, b = points[i], points[j]
        for k in range(lo, hi - 1):
            t0, t1 = knots[k:k + 2]
            middle = (t0 + t1) / 2.
            source_middle = float(_sample(
                terrain.elevation_m, a + middle * (b - a), terrain)[0][0])
            span = t1 - t0
            curvature = 2. * (source[k] + source[k + 1] - 2. * source_middle) / span ** 2
            if curvature >= -1e-14:
                continue
            derivative = ((source[k + 1] - source[k]) / span - curvature * span
                          - (bed[k + 1] - bed[k]) / span)
            local_t = -derivative / (2. * curvature)
            if 0. < local_t < span:
                candidate = source[k] - bed[k] + derivative * local_t + curvature * local_t ** 2
                amount = max(amount, float(candidate))
        maximum.append(max(0., amount))
        edge += 1
    return np.asarray(maximum, np.float64)


def _profile_overlap(points, receiver, width, profile, terrain):
    edges = [(i, int(j)) for i, j in enumerate(receiver) if j >= 0]
    adjacency = {frozenset((i, j)) for i, j in edges}
    maximum_cut = _profile_max_cut_per_edge(points, receiver, profile, terrain)
    radii = []
    for edge, (i, j) in enumerate(edges):
        radii.append(max(width[i], width[j]) / 2.
                     + BANK_SLOPE * maximum_cut[edge])
    for index, (i, j) in enumerate(edges):
        for other in range(index + 1, len(edges)):
            k, l = edges[other]
            near = bool({i, j} & {k, l}) or any(
                frozenset((a, b)) in adjacency for a in (i, j) for b in (k, l))
            if near:
                continue
            distance = min(_point_segment_distance(p, points[k], points[l])
                           for p in (points[i], points[j]))
            distance = min(distance, *(_point_segment_distance(p, points[i], points[j])
                                           for p in (points[k], points[l])))
            if distance <= radii[index] + radii[other] + 1e-10:
                raise ValueError("nonlocal actual incision envelopes may overlap")


def _check_inputs(terrain, ids, receiver, width, depth, owner, corridor, lake, config):
    if not isinstance(terrain, TerrainGrid) or not isinstance(config, GeometryConfig):
        raise ValueError("TerrainGrid and GeometryConfig required")
    _topology(ids, receiver, terrain)
    n = len(ids)
    for name, value in (("width_m", width), ("base_depth_m", depth)):
        if (value.dtype != np.float64 or value.shape != (n,) or not np.isfinite(value).all()
                or np.any(value <= 0.)):
            raise ValueError("positive physical " + name + " required")
    if np.any(depth > config.max_cut_m) or config.max_cut_m > 4.:
        raise ValueError("fixed 4m maximum incision exceeded")
    shape = terrain.elevation_m.shape
    if (owner.dtype != np.int64 or owner.shape != shape or corridor.dtype != bool
            or corridor.shape != shape or lake.dtype != bool or lake.shape != shape):
        raise ValueError("original owner, corridor and known-wet masks required")
    if np.any(lake.ravel()[ids]):
        raise ValueError("known wet lake terminal cannot be incised")
    if np.any(owner.ravel()[ids] < 0) or np.any(~corridor.ravel()[ids]):
        raise ValueError("source nodes outside owner corridor")
    for i, j in enumerate(receiver):
        if j >= 0 and owner.ravel()[ids[i]] != owner.ravel()[ids[j]]:
            raise ValueError("source edge crosses owner divide")
    if config.fine_spacing_m > np.min(width) / config.width_resolution:
        raise ValueError("channel width underresolved")
    if (not math.isclose(terrain.dx_m / config.fine_spacing_m,
                         round(terrain.dx_m / config.fine_spacing_m), abs_tol=1e-10)
            or not math.isclose(terrain.dz_m / config.fine_spacing_m,
                                round(terrain.dz_m / config.fine_spacing_m), abs_tol=1e-10)):
        raise ValueError("fine spacing must divide native source spacing")


def build_valley_incision(terrain, node_cell_ids, receiver, width_m, base_depth_m, *,
                          owner_grid, corridor_mask, lake_mask, config=None):
    config = config or GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0)
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m,
                  owner_grid, corridor_mask, lake_mask, config)
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m,
                              terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, base_depth_m, terrain, config.max_cut_m)
    # The full possible 4m bank is checked, including source interpolation stencils.
    _footprint(points, receiver, width_m, np.full(len(points), config.max_cut_m), terrain,
               owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids],
               config.fine_spacing_m)
    _profile_overlap(points, receiver, width_m, profile, terrain)
    vertices, triangles = _mesh(points, receiver, width_m,
                                np.full(len(points), config.max_cut_m), terrain, config)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width_m, profile, vertices, terrain, lake_mask)
    if not np.isfinite(cut).all() or np.any(cut < 0.) or np.any(cut > config.max_cut_m + 1e-10):
        raise ValueError("represented incision exceeds declared depth")
    if np.any(cut[_wet_guard(vertices, lake_mask, terrain)] > 0.):
        raise ValueError("known wet support would be incised")
    bed = source - cut
    _modified_bed_slope(points, receiver, vertices, triangles, bed, config.fine_spacing_m)
    ports = _port_observations(points, receiver, width_m, base_depth_m,
                               vertices, triangles, cut)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(),
                  node_xz_m=points, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(),
                  source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(),
                  owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(),
                  lake_mask=lake_mask.copy(), profile_offsets=profile[0], profile_t=profile[1],
                  profile_source_m=profile[2], profile_center_bed_m=profile[3],
                  vertices_xz_m=vertices, source_elevation_m=source, cut_depth_m=cut,
                  bed_elevation_m=bed, triangles=triangles, source_cell_ids=source_cells,
                  canonical_port_edge_node_indices=ports[0], canonical_port_xz_m=ports[1],
                  canonical_port_profile_xz_m=ports[2], canonical_port_triangle_ids=ports[3],
                  canonical_port_barycentric=ports[4], canonical_port_cut_depth_m=ports[5])
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, terrain_metadata=_metadata_terrain(terrain),
                    source_identity_sha256=terrain.identity_sha256, config=asdict(config),
                    epsilon_slope_m_per_m=EPSILON_SLOPE_M_PER_M,
                    cut_volume_m3=_mesh_volume(vertices, triangles, cut),
                    geometry_measure="canonical_piecewise_linear_heightfield",
                    fixed_xz=True, original_bed_may_rise_within_edge=True,
                    geometry_verified=True, hydraulic_ready=False,
                    natural_outlet_verified=False, publishable=False)
    arrays = {key: readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_valley_incision(bundle)
    return bundle


def validate_valley_incision(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid valley incision bundle")
    a, m = bundle["arrays"], bundle["metadata"]
    expected_meta = {"schema", "algorithm", "terrain_metadata", "source_identity_sha256",
                     "config", "epsilon_slope_m_per_m", "cut_volume_m3", "geometry_measure",
                     "fixed_xz", "original_bed_may_rise_within_edge", "geometry_verified",
                     "hydraulic_ready", "natural_outlet_verified", "publishable"}
    if (set(a) != set(ARRAYS) or set(m) != expected_meta or m["schema"] != SCHEMA
            or m["algorithm"] != ALGORITHM or m["epsilon_slope_m_per_m"] != EPSILON_SLOPE_M_PER_M
            or m["geometry_measure"] != "canonical_piecewise_linear_heightfield"
            or any(m[k] is not True for k in ("fixed_xz", "original_bed_may_rise_within_edge", "geometry_verified"))
            or any(m[k] is not False for k in ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or sum(value.nbytes for value in a.values()) > MAX_BYTES
            or bundle["identity_sha256"] != identity(a, m)):
        raise ValueError("valley incision schema/identity/scope mismatch")
    terrain = TerrainGrid(a["source_height_m"], a["source_valid_mask"], **m["terrain_metadata"])
    if terrain.identity_sha256 != m["source_identity_sha256"]:
        raise ValueError("source identity mismatch")
    config = GeometryConfig(**m["config"])
    ids, receiver, width, depth = (a[key] for key in
                                   ("source_node_cell_ids", "receiver", "width_m", "base_depth_m"))
    _check_inputs(terrain, ids, receiver, width, depth, a["owner_grid"],
                  a["corridor_mask"], a["lake_mask"], config)
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m,
                              terrain.z0_m + ids // cols * terrain.dz_m))
    if not np.array_equal(points, a["node_xz_m"]):
        raise ValueError("fixed source node coordinates mismatch")
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    if any(not np.allclose(a[key], expected, atol=1e-10, rtol=0.) for key, expected in zip(
            ("profile_offsets", "profile_t", "profile_source_m", "profile_center_bed_m"), profile)):
        raise ValueError("original-bilinear incision profile mismatch")
    maxdepth = np.full(len(points), config.max_cut_m)
    _footprint(points, receiver, width, maxdepth, terrain, a["owner_grid"],
               a["corridor_mask"], a["lake_mask"], a["owner_grid"].ravel()[ids],
               config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    vertices, triangles = a["vertices_xz_m"], a["triangles"]
    _validate_fan_mesh(vertices, triangles, points, width, maxdepth, terrain, config)
    source, cells = _sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width, profile, vertices, terrain, a["lake_mask"])
    if (np.any(cut > config.max_cut_m + 1e-10)
            or not np.array_equal(a["source_cell_ids"], cells)
            or not np.allclose(a["source_elevation_m"], source, rtol=0., atol=1e-9)
            or not np.allclose(a["cut_depth_m"], cut, rtol=0., atol=1e-9)
            or not np.allclose(a["bed_elevation_m"], source - cut, rtol=0., atol=1e-9)):
        raise ValueError("represented original-source incision mismatch")
    if np.any(cut[_wet_guard(vertices, a["lake_mask"], terrain)] > 0.):
        raise ValueError("known wet source support cut")
    _modified_bed_slope(points, receiver, vertices, triangles, source - cut,
                        config.fine_spacing_m)
    ports = _port_observations(points, receiver, width, depth, vertices, triangles, cut)
    port_names = ("canonical_port_edge_node_indices", "canonical_port_xz_m",
                  "canonical_port_profile_xz_m", "canonical_port_triangle_ids",
                  "canonical_port_barycentric", "canonical_port_cut_depth_m")
    if any(not np.allclose(a[key], value, rtol=0., atol=1e-9)
           for key, value in zip(port_names, ports)):
        raise ValueError("shared canonical port mismatch")
    if not math.isclose(m["cut_volume_m3"], _mesh_volume(vertices, triangles, cut),
                        rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("represented cut volume mismatch")
    return True


def save_valley_incision(path, bundle):
    save_bundle(path, bundle, validator=validate_valley_incision)


def load_valley_incision(path, *, expected_sha256, expected_identity):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_valley_incision, max_bytes=MAX_BYTES)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external valley incision identity mismatch")
    return bundle
