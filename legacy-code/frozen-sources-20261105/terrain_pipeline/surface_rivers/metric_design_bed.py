"""Minimum-volume shared beds with continuous design width and profile bounds."""

import numpy as np
import warnings
from dataclasses import asdict
from scipy.optimize import linprog, OptimizeWarning
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree
from types import SimpleNamespace

from .metric_monotone_union import _barycentric, _line_constraints
from .metric_channel_geometry import _sample
from terrain_pipeline.mountain_source_adapter import identity
from .metric_valley_union import (
    _cell_at_point,
    _mesh_directional_weights,
    _sparse_cells,
    _sparse_mesh,
)


DESIGN_BED_CONSTRAINT_MODEL = "fan4-physical-gradient-profile-actual-transverse-exterior-node-cone-v1"


def shared_section_constraints(sections, cells, vertices, triangles, source, terrain, spacing):
    """Fix the complete affine trace, including every represented triangle crossing."""
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    rows = []
    for section in sections:
        position = np.asarray(section["position_xz_m"], float)
        normal = np.asarray(section["normal_xz"], float)
        offsets = np.asarray(section["offsets_m"], float)
        bed = np.asarray(section["bed_elevation_m"], float)
        if (position.shape != (2,) or normal.shape != (2,) or offsets.ndim != 1
                or len(offsets) < 2 or bed.shape != offsets.shape or np.any(np.diff(offsets) <= 0)
                or not all(np.isfinite(value).all() for value in (position, normal, offsets, bed))
                or not np.isclose(np.linalg.norm(normal), 1., atol=1e-10, rtol=0)):
            raise ValueError("finite ordered shared fan4 cross-section required")
        ends = position + offsets[[0, -1], None] * normal
        segments = _line_constraints(ends, np.array([1, -1]), cells, vertices, triangles, terrain, spacing)
        samples = list(position + offsets[:, None] * normal)
        for start, end, _, _, _ in segments:
            samples.extend((start[1] @ vertices[start[0]], end[1] @ vertices[end[0]]))
        for point in samples:
            offset = float((point - position) @ normal)
            target = float(np.interp(offset, offsets, bed))
            key = _cell_at_point(point, lookup, origin, spacing)
            ids, weights = _barycentric(point, lookup[key], vertices, triangles)
            cut = float(weights @ source[ids] - target)
            rows.extend(((ids, weights, cut, "shared_section"),
                         (ids, -weights, -cut, "shared_section")))
    return rows


def interior_support_boundary_vertices(cells, vertices, terrain, spacing):
    """Return exposed mesh corners inside the known domain that must reconnect."""
    origin = np.array([terrain.x0_m, terrain.z0_m])
    vertex_keys = np.rint((vertices - origin) * 2.0 / spacing).astype(np.int64)
    minimum = cells.min(axis=0) - 1
    stride = int(cells[:, 0].max() - minimum[0]) + 3
    cell_keys = (cells[:, 1] - minimum[1]) * stride + cells[:, 0] - minimum[0]
    sorted_cells = np.sort(cell_keys)
    vertex_stride = 2 * stride
    encoded_vertices = (vertex_keys[:, 1] - 2 * minimum[1]) * vertex_stride + vertex_keys[:, 0] - 2 * minimum[0]
    vertex_order = np.argsort(encoded_vertices)
    sorted_vertices = encoded_vertices[vertex_order]
    maximum = np.rint(
        np.array(
            [
                (terrain.elevation_m.shape[1] - 1) * terrain.dx_m,
                (terrain.elevation_m.shape[0] - 1) * terrain.dz_m,
            ]
        )
        / spacing
    ).astype(int)
    boundary = np.zeros(len(vertices), bool)
    for start in range(0, len(cells), 200_000):
        block = cells[start:start + 200_000]
        keys = cell_keys[start:start + len(block)]
        faces = (
            (-1, ((0, 0), (0, 1)), block[:, 0] > 0),
            (1, ((1, 0), (1, 1)), block[:, 0] + 1 < maximum[0]),
            (-stride, ((0, 0), (1, 0)), block[:, 1] > 0),
            (stride, ((0, 1), (1, 1)), block[:, 1] + 1 < maximum[1]),
        )
        for offset, corners, interior in faces:
            neighbors = keys + offset
            positions = np.searchsorted(sorted_cells, neighbors)
            present = sorted_cells[np.minimum(positions, len(sorted_cells) - 1)] == neighbors
            exposed = block[interior & ~present]
            for corner in corners:
                xy = 2 * (exposed + corner - minimum)
                encoded = xy[:, 1] * vertex_stride + xy[:, 0]
                boundary[vertex_order[np.searchsorted(sorted_vertices, encoded)]] = True
    return np.flatnonzero(boundary)


def build_design_geometry(
    points,
    receiver,
    width,
    design_depth,
    profile,
    terrain,
    spacing,
    max_cut,
    minimum_slope,
    *,
    transverse_bottom_slope=0.02,
    center_lowest=False,
    continuous_center_lowest=False,
    shared_sections=None,
):
    """Build known-domain support for the conservative bottom and zero bank edge."""
    support_guard = (np.sqrt(2.0) + 1.0) * spacing
    edge_nodes = np.flatnonzero(receiver >= 0)
    support_radius = np.maximum(width[edge_nodes], width[receiver[edge_nodes]]) / 2.0 + support_guard + 2.0 * max_cut
    options = SimpleNamespace(
        fine_spacing_m=spacing, max_cut_m=max_cut, max_vertices=8_000_000
    )
    cells = _sparse_cells(
        points, receiver, width, profile, options, terrain,
        support_radius_m=support_radius,
    )
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, options.max_vertices)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    lower, upper, padding = design_cut_bounds(
        points,
        receiver,
        width,
        design_depth,
        cells,
        vertices,
        triangles,
        terrain,
        spacing,
        max_cut,
    )
    boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
    if np.any(lower[boundary] > 1e-10):
        raise ValueError(
            "continuous design bank does not reconnect within known support"
        )
    upper[boundary] = 0.0
    cut, closure = solve_design_bed(
        points,
        receiver,
        cells,
        vertices,
        triangles,
        source,
        lower,
        upper,
        terrain,
        spacing,
        profile,
        minimum_slope,
        width=width,
        transverse_bottom_slope=transverse_bottom_slope,
        center_lowest=center_lowest,
        continuous_center_lowest=continuous_center_lowest,
        shared_sections=shared_sections,
    )
    if np.any(np.abs(cut[boundary]) > 1e-10):
        raise ValueError("actual design bed has nonzero interior support boundary cut")
    closure.update(
        interior_support_boundary_vertices=len(boundary),
        maximum_interior_support_boundary_cut_m=float(
            np.max(np.abs(cut[boundary]), initial=0.0)
        ),
    )
    return (
        cells,
        vertices,
        triangles,
        source,
        source_cells,
        cut,
        closure,
        lower,
        upper,
        padding,
        boundary,
    )


def merge_design_bundles(terrain, bundles, config, network_design_depth):
    """Preserve legacy cuts while recomputing necessary new design incision once."""
    spacing = config.fine_spacing_m
    cells = np.unique(
        np.concatenate([b["arrays"]["sparse_cell_xy"] for b in bundles]), axis=0
    )
    cells = cells[np.lexsort((cells[:, 0], cells[:, 1]))]
    # The union cannot contain more vertices than its already budgeted inputs.
    vertex_budget = sum(len(b["arrays"]["vertices_xz_m"]) for b in bundles)
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, vertex_budget)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    origin = np.array([terrain.x0_m, terrain.z0_m])
    keys = np.rint((vertices - origin) * 2.0 / spacing).astype(np.int64)
    minimum = cells.min(axis=0)
    stride = int(cells[:, 0].max() - minimum[0]) + 2
    vertex_keys = (keys[:, 1] - 2 * minimum[1]) * (2 * stride) + keys[:, 0] - 2 * minimum[0]
    vertex_order = np.argsort(vertex_keys)
    sorted_vertex_keys = vertex_keys[vertex_order]
    cell_keys = (cells[:, 1] - minimum[1]) * stride + cells[:, 0] - minimum[0]
    del keys, vertex_keys
    lower = np.zeros(len(vertices))
    legacy_lower = np.zeros(len(vertices))
    reference_cut = np.zeros(len(vertices))
    padding = np.zeros(len(vertices))
    vertex_mask = np.zeros(len(vertices), bool)
    triangle_mask = np.zeros(len(triangles), bool)
    node_masks, receivers, ids, points, widths, depths = [], [], [], [], [], []
    component_supports = []
    all_new = all("design_minimum_cut_m" in b["arrays"] for b in bundles)
    offsets, parameters, profile_source, profile_bed = [0], [], [], []
    node_offset = 0
    for bundle in bundles:
        a = bundle["arrays"]
        local_keys = np.rint((a["vertices_xz_m"] - origin) * 2.0 / spacing).astype(np.int64)
        encoded = (local_keys[:, 1] - 2 * minimum[1]) * (2 * stride) + local_keys[:, 0] - 2 * minimum[0]
        mapping = vertex_order[np.searchsorted(sorted_vertex_keys, encoded)]
        local_cells = a["sparse_cell_xy"]
        cell_ids = np.searchsorted(cell_keys, (local_cells[:, 1] - minimum[1]) * stride + local_cells[:, 0] - minimum[0])
        del local_keys, encoded
        new = "design_minimum_cut_m" in a
        if all_new:
            face_ids = (4 * cell_ids[:, None] + np.arange(4)).ravel()
            same_mesh = (np.array_equal(triangles[face_ids], mapping[a["triangles"]])
                         and bundle.get("metadata", {}).get("config") == asdict(config)
                         and bundle.get("metadata", {}).get("source_identity_sha256") == terrain.identity_sha256)
            component_supports.append((bundle, mapping, same_mesh))
        necessary = a["design_minimum_cut_m"] if new else a["cut_depth_m"]
        np.maximum.at(lower, mapping, necessary)
        np.maximum.at(reference_cut, mapping, a["cut_depth_m"])
        if new:
            vertex_mask[mapping] = True
            np.maximum.at(padding, mapping, a["source_interpolation_padding_m"])
            triangle_mask.reshape(-1, 4)[cell_ids] = True
        else:
            np.maximum.at(legacy_lower, mapping, necessary)
        node_masks.append(np.full(len(a["receiver"]), new, bool))
        receivers.append(np.where(a["receiver"] >= 0, a["receiver"] + node_offset, -1))
        ids.append(a["source_node_cell_ids"])
        points.append(a["node_xz_m"])
        widths.append(a["width_m"])
        depths.append(a["base_depth_m"])
        offsets.extend(a["profile_offsets"][1:] + offsets[-1])
        parameters.extend(a["profile_t"])
        profile_source.extend(a["profile_source_m"])
        profile_bed.extend(a["profile_center_bed_m"])
        node_offset += len(a["receiver"])
    receiver = np.concatenate(receivers)
    points = np.concatenate(points)
    ids = np.concatenate(ids)
    node_mask = np.concatenate(node_masks)
    profile = (
        np.asarray(offsets, np.int64),
        np.asarray(parameters),
        np.asarray(profile_source),
        np.asarray(profile_bed),
    )
    del vertex_order, sorted_vertex_keys, cell_keys, mapping
    upper = np.full(len(vertices), config.max_cut_m)
    upper[vertex_mask] -= padding[vertex_mask]
    boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
    zero_mask = np.zeros(len(vertices), bool)
    zero_mask[boundary] = vertex_mask[boundary] & (legacy_lower[boundary] == 0.0)
    upper[zero_mask] = 0.0
    cut, closure = solve_design_bed(
        points,
        receiver,
        cells,
        vertices,
        triangles,
        source,
        lower,
        upper,
        terrain,
        spacing,
        profile,
        1e-5,
        node_mask,
        width=np.concatenate(widths),
        transverse_bottom_slope=getattr(config, "transverse_bottom_slope_m_per_m", 0.02),
        component_supports=component_supports if all_new else None,
    )
    arrays = dict(
        source_height_m=terrain.elevation_m,
        source_valid_mask=terrain.valid_mask,
        source_node_cell_ids=ids,
        receiver=receiver,
        node_xz_m=points,
        width_m=np.concatenate(widths),
        base_depth_m=np.concatenate(depths),
        design_base_depth_m=network_design_depth[ids],
        design_constraint_node_mask=node_mask,
        design_constraint_vertex_mask=vertex_mask,
        design_constraint_triangle_mask=triangle_mask,
        design_zero_boundary_vertex_mask=zero_mask,
        design_minimum_cut_m=lower,
        design_maximum_cut_m=upper,
        source_interpolation_padding_m=padding,
        sparse_cell_xy=cells,
        vertices_xz_m=vertices,
        triangles=triangles,
        source_elevation_m=source,
        source_cell_ids=source_cells,
        cut_depth_m=cut,
        bed_elevation_m=source - cut,
        profile_offsets=profile[0],
        profile_t=profile[1],
        profile_source_m=profile[2],
        profile_center_bed_m=profile[3],
    )
    metadata = dict(
        schema="td-generated-component-bed-v1",
        algorithm="unique-mixed-legacy-and-transverse-coupled-design-bed-v2",
        terrain_metadata=terrain.metadata(),
        source_identity_sha256=terrain.identity_sha256,
        config=asdict(config),
        cut_volume_m3=_mesh_volume_chunked(vertices, triangles, cut),
        preclosure_cut_volume_m3=_mesh_volume_chunked(vertices, triangles, lower),
        component_max_cut_reference_volume_m3=_mesh_volume_chunked(
            vertices, triangles, reference_cut
        ),
        maximum_cut_m=float(cut.max()),
        closure=closure,
        minimum_bed_slope_m_per_m=1e-5,
        design_bed_policy=dict(
            certificate_scope="masked new component support only; legacy actual cut locked",
            bottom_triangle_guard_m=np.sqrt(2.0) * spacing,
            bank_slope=2.0,
            design_depth_policy="edge endpoint maximum",
            source_padding="maximum incident new fan4 triangle bilinear error",
            profile_constraint_policy="mesh triangle boundaries union profile knots",
            necessary_lower_policy="maximum legacy actual cut and new design minimum; new solved cut is not locked",
            known_domain_boundary_cut_policy="zero new exposed interior bank vertices with zero legacy necessary cut",
            transverse_bed_policy="actual solved center bed coupled across full bottom; bounded transverse bottom slope and bank ceiling relative to projected center",
            transverse_bottom_slope_m_per_m=getattr(config, "transverse_bottom_slope_m_per_m", 0.02),
            transverse_bank_horizontal_per_vertical=2.0,
            transverse_bottom_guard_m=np.sqrt(2.0) * spacing,
            transverse_node_cap_policy="all incident unit-direction dot distances <= 1e-10m; actual node bed coupled",
            transverse_node_cap_dot_tolerance_m=1e-10,
        ),
        natural_outlet_verified=False,
        hydraulic_ready=False,
        publishable=False,
    )
    return dict(
        arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata)
    )


def _mesh_volume_chunked(vertices, triangles, heights, *, datum=0.0):
    """Integrate the same piecewise-linear field without expanding the full mesh."""
    volume = 0.0
    for start in range(0, len(triangles), 200_000):
        faces = triangles[start:start + 200_000]
        xy = vertices[faces]
        area = np.abs(
            (xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1])
            - (xy[:, 2, 0] - xy[:, 0, 0]) * (xy[:, 1, 1] - xy[:, 0, 1])
        ) / 2.0
        volume += float(np.sum(area * np.mean(heights[faces] - datum, axis=1)))
    return volume


def source_interpolation_padding(cells, vertices, triangles, terrain, spacing):
    """Exact fan4 error bound for a fine cell within one bilinear source cell."""
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("positive finite fine spacing required")
    ratios = np.array([terrain.dx_m, terrain.dz_m]) / spacing
    if (
        not np.all(np.isfinite(ratios))
        or np.any(ratios < 1.0)
        or not np.allclose(ratios, np.rint(ratios), rtol=0.0, atol=1e-10)
    ):
        raise ValueError("continuous design requires aligned native and fine grids")
    middle = (cells + 0.5) * spacing
    x = np.floor(middle[:, 0] / terrain.dx_m).astype(np.int64)
    z = np.floor(middle[:, 1] / terrain.dz_m).astype(np.int64)
    height = terrain.elevation_m
    cross = height[z + 1, x + 1] - height[z + 1, x] - height[z, x + 1] + height[z, x]
    cell_padding = np.abs(cross) * spacing**2 / (16.0 * terrain.dx_m * terrain.dz_m)
    padding = np.zeros(len(vertices))
    np.maximum.at(padding, triangles.ravel(), np.repeat(cell_padding, 12))
    return padding


def design_cut_bounds(
    points,
    receiver,
    width,
    design_depth,
    cells,
    vertices,
    triangles,
    terrain,
    spacing,
    max_cut,
):
    """Cover each design-bottom triangle with a conservative constant depth."""
    padding = source_interpolation_padding(cells, vertices, triangles, terrain, spacing)
    lower = np.zeros(len(vertices))
    tree = cKDTree(vertices)
    guard = np.sqrt(2.0) * spacing
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = points[i], points[j]
        delta = b - a
        depth = max(float(design_depth[i]), float(design_depth[j]))
        half = max(float(width[i]), float(width[j])) / 2.0 + guard
        near = np.asarray(
            tree.query_ball_point(
                (a + b) / 2.0, np.linalg.norm(delta) / 2.0 + half + 2.0 * depth
            ),
            np.int64,
        )
        t = np.clip((vertices[near] - a) @ delta / np.dot(delta, delta), 0.0, 1.0)
        distance = np.linalg.norm(vertices[near] - (a + t[:, None] * delta), axis=1)
        amount = np.minimum(
            depth, np.maximum(0.0, (half + 2.0 * depth - distance) / 2.0)
        )
        lower[near] = np.maximum(lower[near], amount)
    # Zero banks reconnect to the represented source without a padding seam.
    lower += np.where(lower > 0.0, padding, 0.0)
    upper = max_cut - padding
    if np.any(lower > upper + 1e-10):
        raise ValueError("continuous design depth exceeds original-source cut budget")
    return lower, upper, padding


def bed_constraints(
    points,
    receiver,
    cells,
    vertices,
    triangles,
    source,
    terrain,
    spacing,
    profile,
    minimum_slope,
    profile_node_mask=None,
):
    """Build physical gradients and the union of mesh and profile breakpoints."""
    segments = _line_constraints(
        points, receiver, cells, vertices, triangles, terrain, spacing
    )
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    edge_by_node = np.full(len(receiver), -1, np.int64)
    edge_by_node[receiver >= 0] = np.arange(np.count_nonzero(receiver >= 0))
    if profile_node_mask is None:
        profile_node_mask = np.ones(len(receiver), bool)
    rows = []
    for start, end, _, i, j in segments:
        midpoint = (start[1] @ vertices[start[0]] + end[1] @ vertices[end[0]]) / 2.0
        cell = lookup[_cell_at_point(midpoint, lookup, origin, spacing)]
        delta = points[j] - points[i]
        ids, weights = _mesh_directional_weights(
            midpoint, cell, vertices, triangles, delta / np.linalg.norm(delta)
        )
        source_gradient = float(weights[1:] @ (source[ids[1:]] - source[ids[0]]))
        rows.append((ids, -weights, -minimum_slope - source_gradient, "gradient"))
        if not profile_node_mask[i]:
            continue
        edge = edge_by_node[i]
        lo, hi = profile[0][edge : edge + 2]
        for ids, weights in (start, end):
            point = weights @ vertices[ids]
            t = float(
                np.clip((point - points[i]) @ delta / np.dot(delta, delta), 0.0, 1.0)
            )
            target = np.interp(t, profile[1][lo:hi], profile[3][lo:hi])
            rows.append(
                (ids, -weights, float(target - weights @ source[ids]), "profile")
            )
    for i, j in enumerate(receiver):
        if j < 0 or not profile_node_mask[i]:
            continue
        lo, hi = profile[0][edge_by_node[i] : edge_by_node[i] + 2]
        for t, target in zip(profile[1][lo:hi], profile[3][lo:hi]):
            point = points[i] + t * (points[j] - points[i])
            cell = lookup[_cell_at_point(point, lookup, origin, spacing)]
            ids, weights = _barycentric(point, cell, vertices, triangles)
            rows.append(
                (ids, -weights, float(target - weights @ source[ids]), "profile")
            )
    return rows


def _barycentric_batch(points, cells, vertices, triangles):
    """Keep scalar fan4 tolerance and first-face selection with stacked solves."""
    indices = np.empty((len(points), 3), np.int64)
    weights = np.empty((len(points), 3))
    if not len(points):
        return indices, weights
    scale = np.maximum(1.0, np.max(np.abs(points), axis=1))
    first = triangles[4 * cells]
    span = np.linalg.norm(vertices[first[:, 1]] - vertices[first[:, 0]], axis=1)
    tolerance = np.maximum(1e-9, 8.0 * np.spacing(scale) / span)
    pending = np.ones(len(points), bool)
    for face in range(4):
        rows = np.flatnonzero(pending)
        if not len(rows):
            break
        ids = triangles[4 * cells[rows] + face]
        tri = vertices[ids]
        matrix = np.stack((tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=2)
        uv = np.linalg.solve(matrix, (points[rows] - tri[:, 0])[:, :, None])[:, :, 0]
        bary = np.column_stack((1.0 - uv.sum(axis=1), uv[:, 0], uv[:, 1]))
        accepted = np.min(bary, axis=1) >= -tolerance[rows]
        selected = rows[accepted]
        indices[selected], weights[selected] = ids[accepted], bary[accepted]
        pending[selected] = False
    if pending.any():
        raise ValueError("centerline point outside sparse triangles")
    return indices, weights


def transverse_bed_constraints(
    points, receiver, width, cells, vertices, triangles, source, terrain,
    spacing, maximum_cut, node_mask=None, transverse_bottom_slope=0.02, center_lowest=False,
    internal_port_mask=None,
):
    """Couple bottom and bank elevations to the actual variable center bed."""
    if width.shape != (len(points),) or np.any(width <= 0.0) or not np.isfinite(width).all():
        raise ValueError("positive finite bottom width required at every node")
    if not np.isfinite(transverse_bottom_slope) or not 0.0 <= transverse_bottom_slope < 0.5:
        raise ValueError("transverse bottom slope must be finite and in [0, 0.5)")
    if node_mask is None:
        node_mask = np.ones(len(points), bool)
    tree = cKDTree(vertices)
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    guard = np.sqrt(2.0) * spacing
    index_batches, weight_batches, limit_batches = [], [], []
    maximum_depth = float(np.max(maximum_cut))
    incident_directions = [[] for _ in points]
    incident_width = width.copy()
    enabled_incident = np.zeros(len(points), bool)
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        direction = points[j] - points[i]
        direction = direction / np.linalg.norm(direction)
        incident_directions[i].append(direction)
        incident_directions[j].append(-direction)
        edge_width = max(float(width[i]), float(width[j]))
        incident_width[i] = max(incident_width[i], edge_width)
        incident_width[j] = max(incident_width[j], edge_width)
        if node_mask[i]:
            enabled_incident[i] = enabled_incident[j] = True
    for i, j in enumerate(receiver):
        if j < 0 or not node_mask[i]:
            continue
        a, b = points[i], points[j]
        delta = b - a
        half = max(float(width[i]), float(width[j])) / 2.0 + guard
        radius = half + 2.0 * maximum_depth
        near = np.asarray(tree.query_ball_point((a + b) / 2.0,
                         np.linalg.norm(delta) / 2.0 + radius), np.int64)
        t = (vertices[near] - a) @ delta / (delta @ delta)
        projected = a + t[:, None] * delta
        distance = np.linalg.norm(vertices[near] - projected, axis=1)
        selected = (distance > 1e-10) & (distance <= radius) & (t >= 0.0) & (t <= 1.0)
        near, projected, distance = near[selected], projected[selected], distance[selected]
        indices = np.empty((len(near), 4), np.int64)
        weights = np.empty((len(near), 4))
        indices[:, 0], weights[:, 0] = near, -1.0
        cell_ids = np.asarray([lookup[_cell_at_point(center, lookup, origin, spacing)]
                               for center in projected], np.int64)
        indices[:, 1:], weights[:, 1:] = _barycentric_batch(
            projected, cell_ids, vertices, triangles
        )
        # B(vertex) <= B(projected center) + transverse rise; both are variables.
        rise = np.minimum(distance, half) * transverse_bottom_slope + np.maximum(0.0, distance - half) / 2.0
        limits = rise + np.sum(weights * source[indices], axis=1)
        index_batches.append(indices)
        weight_batches.append(weights)
        limit_batches.append(limits)
        if center_lowest:
            # The existing row is only an upper ceiling. Its reverse bounds
            # the actual center below the entire bottom and bank strip.
            closest = distance.copy()
            for first, second in enumerate(receiver):
                if second < 0:
                    continue
                vector = points[second] - points[first]
                fraction = np.clip((vertices[near] - points[first]) @ vector / (vector @ vector), 0, 1)
                closest = np.minimum(closest, np.linalg.norm(vertices[near] - points[first] - fraction[:, None] * vector, axis=1))
            owned = distance <= closest + 1e-8
            index_batches.append(indices[owned])
            weight_batches.append(-weights[owned])
            limit_batches.append(-np.sum(weights[owned] * source[indices[owned]], axis=1))
    cap_count = 0
    for node, directions in enumerate(incident_directions):
        if not directions or not node_mask[node] or not enabled_incident[node]:
            continue
        if internal_port_mask is not None and internal_port_mask[node]:
            continue
        half = incident_width[node] / 2.0 + guard
        radius = half + 2.0 * maximum_depth
        near = np.asarray(tree.query_ball_point(points[node], radius), np.int64)
        displacement = vertices[near] - points[node]
        distance = np.linalg.norm(displacement, axis=1)
        # Only the exterior cone is missing from edge strips; a full cap would
        # couple upstream center points to a lower downstream endpoint bed.
        selected = (distance > 1e-10) & np.all(
            displacement @ np.asarray(directions).T <= 1e-10, axis=1
        )
        near, distance = near[selected], distance[selected]
        cell = lookup[_cell_at_point(points[node], lookup, origin, spacing)]
        ids, bary = _barycentric(points[node], cell, vertices, triangles)
        indices = np.empty((len(near), 4), np.int64)
        weights = np.empty((len(near), 4))
        indices[:, 0], weights[:, 0] = near, -1.0
        indices[:, 1:], weights[:, 1:] = ids, bary
        rise = np.minimum(distance, half) * transverse_bottom_slope + np.maximum(0.0, distance - half) / 2.0
        limits = rise + np.sum(weights * source[indices], axis=1)
        index_batches.append(indices)
        weight_batches.append(weights)
        limit_batches.append(limits)
        cap_count += len(near)
    if not index_batches:
        return np.empty((0, 4), np.int64), np.empty((0, 4)), np.empty(0), 0
    return np.concatenate(index_batches), np.concatenate(weight_batches), np.concatenate(limit_batches), cap_count


def _clip_floor_polygon(polygon, normal, limit):
    """Clip an affine mesh region against one closed half-plane."""
    if len(polygon) == 0:
        return polygon
    output = []
    previous = polygon[-1]
    previous_value = float(previous @ normal - limit)
    for current in polygon:
        current_value = float(current @ normal - limit)
        if (current_value <= 1e-10) != (previous_value <= 1e-10):
            # Tolerance can classify two positive distances on opposite sides.
            # Their exact-plane intersection must never extrapolate the edge.
            fraction = np.clip(previous_value / (previous_value - current_value), 0., 1.)
            output.append(previous + fraction * (current - previous))
        if current_value <= 1e-10:
            output.append(current)
        previous, previous_value = current, current_value
    return np.asarray(output).reshape(-1, 2)


def _shared_junction_floor_regions(polygon, own_normal, junction, rays):
    """Cover nearest finite-segment regions; distant end caps are conservative."""
    regions = [polygon]
    for ray, length in rays:
        other_normal = np.array([-ray[1], ray[0]])
        following = []
        for region in regions:
            before = _clip_floor_polygon(region, ray, float(junction @ ray))
            beyond = _clip_floor_polygon(region, -ray, -float(junction @ ray) - length)
            if len(before) >= 3:
                following.append(before)
            if len(beyond) >= 3:
                # This superset avoids certifying a polygon approximation to
                # the parabolic nearest finite-endpoint boundary.
                following.append(beyond)
            interior = _clip_floor_polygon(region, -ray, -float(junction @ ray))
            interior = _clip_floor_polygon(interior, ray, float(junction @ ray) + length)
            for own_sign in (-1, 1):
                for other_sign in (-1, 1):
                    part = _clip_floor_polygon(interior, -own_sign * own_normal,
                                               -float(junction @ (own_sign * own_normal)))
                    part = _clip_floor_polygon(part, -other_sign * other_normal,
                                               -float(junction @ (other_sign * other_normal)))
                    difference = own_sign * own_normal - other_sign * other_normal
                    part = _clip_floor_polygon(part, difference, float(junction @ difference))
                    if len(part) >= 3:
                        following.append(part)
        regions = following
    return regions


def _edge_continuous_floor_constraints(node, points, receiver, width, cells, vertices, triangles,
                                       source, terrain, spacing, maximum_cut, junction=None):
    other = int(receiver[node])
    a, b = points[node], points[other]
    delta = b - a
    length = float(np.linalg.norm(delta))
    unit = delta / length
    normal = np.array([-unit[1], unit[0]])
    line = _line_constraints(points, receiver, cells, vertices, triangles, terrain, spacing)
    knots = [0., length]
    for start, end, _, first, _ in line:
        if first != node:
            continue
        knots.extend([float((weights @ vertices[ids] - a) @ unit) for ids, weights in (start, end)])
    knots = np.unique(np.clip(knots, 0., length))
    query_points = []
    # A side triangle and one projected center triangle define an affine
    # height difference; checking every clipped polygon vertex proves it.
    for face in triangles:
        polygon = vertices[face] - a
        along = polygon @ unit
        if along.max() < 0 or along.min() > length:
            continue
        if len(polygon) < 3:
            continue
        lo = max(0, int(np.searchsorted(knots, along.min(), side="right")) - 1)
        hi = min(len(knots) - 1, int(np.searchsorted(knots, along.max(), side="left")) + 1)
        for index in range(lo, hi):
            region = _clip_floor_polygon(polygon, -unit, -knots[index])
            region = _clip_floor_polygon(region, unit, knots[index + 1])
            regions = [region]
            if junction is not None:
                rays = []
                for first in np.flatnonzero(receiver >= 0):
                    if first == node:
                        continue
                    second = int(receiver[first])
                    endpoint = points[second] if first == junction else points[first]
                    vector = endpoint - points[junction]
                    other_length = float(np.linalg.norm(vector))
                    rays.append((vector / other_length, other_length))
                regions = _shared_junction_floor_regions(region, normal, points[junction] - a, rays)
            for part in regions:
                if len(part) >= 3:
                    query_points.extend(part + a)
        if len(query_points) > 2_500_000:
            raise ValueError("continuous center-floor polygon work budget exceeded")
    if not query_points:
        raise ValueError("continuous center-floor has no represented strip")
    side = np.unique(np.round(np.asarray(query_points) - a, decimals=10), axis=0) + a
    center = a + ((side - a) @ unit)[:, None] * unit
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    side_cells = np.asarray([lookup[_cell_at_point(point, lookup, origin, spacing)] for point in side], np.int64)
    center_cells = np.asarray([lookup[_cell_at_point(point, lookup, origin, spacing)] for point in center], np.int64)
    side_ids, side_weights = _barycentric_batch(side, side_cells, vertices, triangles)
    center_ids, center_weights = _barycentric_batch(center, center_cells, vertices, triangles)
    indices = np.column_stack((center_ids, side_ids))
    weights = np.column_stack((-center_weights, side_weights))
    limits = np.sum(weights * source[indices], axis=1)
    return indices, weights, limits


def continuous_center_floor_constraints(points, receiver, width, cells, vertices, triangles,
                                        source, terrain, spacing, maximum_cut):
    """Prove floor on each affine region, with conservative finite-end ownership."""
    edges = np.flatnonzero(receiver >= 0)
    junction = None
    if len(edges) > 1:
        common = set([int(edges[0]), int(receiver[edges[0]])])
        for first in edges[1:]:
            common &= {int(first), int(receiver[first])}
        if len(common) != 1 or len(edges) > 4:
            raise ValueError("continuous center-floor requires one edge or at most four arms at one shared junction")
        junction = common.pop()
    results = [_edge_continuous_floor_constraints(int(node), points, receiver, width, cells, vertices, triangles,
        source, terrain, spacing, maximum_cut, junction) for node in edges]
    if not results or sum(len(record[2]) for record in results) > 2_500_000:
        raise ValueError("continuous center-floor polygon work budget exceeded")
    return tuple(np.concatenate([record[index] for record in results]) for index in range(3))


def _vertex_volume_weights(vertices, triangles):
    weights = np.zeros(len(vertices))
    for start in range(0, len(triangles), 200_000):
        faces = triangles[start:start + 200_000]
        tri = vertices[faces]
        delta1, delta2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        area = np.abs(delta1[:, 0] * delta2[:, 1] - delta1[:, 1] * delta2[:, 0]) / 2.0
        np.add.at(weights, faces.ravel(), np.repeat(area / 3.0, 3))
    return weights


def _design_support_groups(component_supports, vertex_count, active, matrix):
    parent = np.arange(len(component_supports))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return int(index)

    def join(first, second):
        first, second = root(first), root(second)
        parent[max(first, second)] = min(first, second)

    owner = np.full(vertex_count, -1, np.int32)
    for index, (_, mapping, _) in enumerate(component_supports):
        for previous in np.unique(owner[mapping]):
            if previous >= 0:
                join(index, int(previous))
        owner[mapping] = index
    roots = np.asarray([root(i) for i in range(len(parent))])
    active_owner = roots[owner[active]]
    counts = np.diff(matrix.indptr)
    nonempty = counts > 0
    # A geometric transverse row can connect otherwise disjoint supports.
    # Keep those variables together rather than dropping a global constraint.
    row_min = np.full(matrix.shape[0], -1, np.int32)
    row_max = row_min.copy()
    starts = matrix.indptr[:-1][nonempty]
    row_min[nonempty] = np.minimum.reduceat(active_owner[matrix.indices], starts)
    row_max[nonempty] = np.maximum.reduceat(active_owner[matrix.indices], starts)
    for row in np.flatnonzero(row_min != row_max):
        groups = np.unique(active_owner[matrix.indices[matrix.indptr[row]:matrix.indptr[row+1]]])
        for group in groups[1:]:
            join(int(groups[0]), int(group))
    roots = np.asarray([root(i) for i in range(len(parent))])
    active_owner = roots[owner[active]]
    row_owner = np.full(matrix.shape[0], int(roots[0]), np.int32)
    row_owner[nonempty] = active_owner[matrix.indices[starts]]
    return roots, active_owner, row_owner


def _saved_design_optimum(bundle, mapping, same_mesh, source, minimum_cut,
                          maximum_cut, volume_weights, minimum_slope, bottom_slope):
    a, metadata = bundle["arrays"], bundle.get("metadata", {})
    closure = metadata.get("closure", {})
    if (not same_mesh or closure.get("constraint_model") != DESIGN_BED_CONSTRAINT_MODEL
            or metadata.get("minimum_bed_slope_m_per_m") != minimum_slope
            or closure.get("transverse_bottom_slope_m_per_m") != bottom_slope
            or not all(closure.get(key) is True for key in (
                "minimum_volume_objective", "physical_triangle_plane_gradient",
                "profile_mesh_breakpoint_union", "transverse_bed_coupling"))):
        return False
    for actual, name in ((source[mapping], "source_elevation_m"),
                         (minimum_cut[mapping], "design_minimum_cut_m"),
                         (maximum_cut[mapping], "design_maximum_cut_m")):
        if name not in a or not np.array_equal(actual, a[name]):
            return False
    old_weights = _vertex_volume_weights(a["vertices_xz_m"], a["triangles"])
    return np.array_equal(volume_weights[mapping], old_weights)


def solve_design_bed(
    points,
    receiver,
    cells,
    vertices,
    triangles,
    source,
    minimum_cut,
    maximum_cut,
    terrain,
    spacing,
    profile,
    minimum_slope,
    profile_node_mask=None,
    *,
    width=None,
    transverse_bottom_slope=0.02,
    center_lowest=False,
    continuous_center_lowest=False,
    component_supports=None,
    shared_sections=None,
):
    """Minimize unique cut volume without locking an unnecessary max envelope."""
    if (
        minimum_cut.shape != (len(vertices),)
        or maximum_cut.shape != (len(vertices),)
        or not np.all(np.isfinite(minimum_cut))
        or not np.all(np.isfinite(maximum_cut))
        or np.any(minimum_cut < 0.0)
        or np.any(minimum_cut > maximum_cut + 1e-10)
    ):
        raise ValueError(
            "finite ordered nonnegative cut bounds required for all vertices"
        )
    constraints = bed_constraints(
        points,
        receiver,
        cells,
        vertices,
        triangles,
        source,
        terrain,
        spacing,
        profile,
        minimum_slope,
        profile_node_mask,
    )
    if shared_sections:
        constraints.extend(shared_section_constraints(shared_sections, cells, vertices, triangles,
                                                       source, terrain, spacing))
    if continuous_center_lowest:
        if width is None or not center_lowest:
            raise ValueError("continuous center-floor requires center-lowest width contract")
        floor = continuous_center_floor_constraints(points, receiver, width, cells, vertices, triangles,
                                                    source, terrain, spacing, maximum_cut)
        constraints.extend((ids, weights, limit, "continuous_floor")
                           for ids, weights, limit in zip(*floor))
    transverse = (np.empty((0, 4), np.int64), np.empty((0, 4)), np.empty(0), 0)
    if width is not None:
        internal_ports = np.array([any(np.allclose(point, section["position_xz_m"], atol=1e-8, rtol=0)
                                       for section in shared_sections or []) for point in points])
        transverse = transverse_bed_constraints(
            points, receiver, width, cells, vertices, triangles, source, terrain,
            spacing, maximum_cut, profile_node_mask, transverse_bottom_slope,
            center_lowest,
            internal_port_mask=internal_ports,
        )
    active = np.unique(np.concatenate([np.concatenate([ids for ids, _, _, _ in constraints]), transverse[0].ravel()]))
    mapping = np.full(len(vertices), -1, np.int64)
    mapping[active] = np.arange(len(active))
    rr, cc, vv, limits = [], [], [], []
    for row, (ids, weights, limit, _) in enumerate(constraints):
        rr.extend([row] * len(ids))
        cc.extend(mapping[ids])
        vv.extend(weights)
        limits.append(limit)
    base_count, transverse_count = len(constraints), len(transverse[2])
    cap_count = transverse[3]
    rr = np.concatenate((np.asarray(rr, np.int64), np.repeat(np.arange(base_count, base_count + transverse_count), 4)))
    cc = np.concatenate((np.asarray(cc, np.int64), mapping[transverse[0]].ravel()))
    vv = np.concatenate((np.asarray(vv), transverse[1].ravel()))
    limits = np.concatenate((np.asarray(limits), transverse[2]))
    matrix = coo_matrix((vv, (rr, cc)), shape=(base_count + transverse_count, len(active))).tocsr()
    matrix.eliminate_zeros()
    del rr, cc, vv, transverse
    volume_weights = _vertex_volume_weights(vertices, triangles)
    bounds = np.column_stack((minimum_cut[active], maximum_cut[active]))
    if component_supports is None:
        roots = np.array([0])
        active_owner = np.zeros(len(active), np.int32)
        row_owner = np.zeros(len(limits), np.int32)
    else:
        roots, active_owner, row_owner = _design_support_groups(
            component_supports, len(vertices), active, matrix
        )
    solution = np.empty(len(active))
    reused_components, solved_groups = 0, 0
    for group in np.unique(roots):
        columns = np.flatnonzero(active_owner == group)
        rows = np.flatnonzero(row_owner == group)
        block = matrix if len(np.unique(roots)) == 1 else matrix[rows][:, columns]
        block_limits = limits[rows]
        members = np.flatnonzero(roots == group)
        candidate = None
        if component_supports is not None and len(members) == 1 and not center_lowest:
            bundle, mapping, same_mesh = component_supports[members[0]]
            if _saved_design_optimum(bundle, mapping, same_mesh, source, minimum_cut,
                                     maximum_cut, volume_weights, minimum_slope,
                                     transverse_bottom_slope):
                order = np.argsort(mapping)
                local_ids = order[np.searchsorted(mapping[order], active[columns])]
                trial = bundle["arrays"]["cut_depth_m"][local_ids]
                if (np.isfinite(trial).all()
                        and np.all(trial >= bounds[columns, 0] - 1e-10)
                        and np.all(trial <= bounds[columns, 1] + 1e-10)
                        and np.max(block @ trial - block_limits, initial=0.0) <= 1e-8):
                    candidate = trial
        if candidate is not None:
            solution[columns] = candidate
            reused_components += 1
            continue
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unrecognized options detected:.*threads.*parallel.*", category=OptimizeWarning)
            result = linprog(
                volume_weights[active[columns]], A_ub=block, b_ub=block_limits,
                bounds=bounds[columns], method="highs",
                options={"primal_feasibility_tolerance": 1e-8 if shared_sections else 1e-9,
                         "dual_feasibility_tolerance": 1e-9,
                         "threads": 1, "parallel": False},
            )
        solved_groups += 1
        if not result.success:
            raise ValueError(
                "continuous design/profile physical bed exceeds configured cut bounds or is infeasible: "
                + result.message
            )
        solution[columns] = result.x
    cut = minimum_cut.copy()
    cut[active] = solution
    residual = matrix @ solution - limits
    gradient_rows = np.concatenate((np.array([kind == "gradient" for _, _, _, kind in constraints]), np.zeros(transverse_count, bool)))
    transverse_rows = np.arange(base_count + transverse_count) >= base_count
    profile_rows = ~(gradient_rows | transverse_rows)
    if (
        np.max(residual[gradient_rows]) > 1e-8
        or np.max(residual[~gradient_rows]) > 1e-8
    ):
        raise ValueError("continuous design/profile closure residual exceeds tolerance")
    return cut, dict(
        constraint_model=("fan4-continuous-bed-v5-continuous-center-floor" if continuous_center_lowest
                          else "fan4-continuous-bed-v4-center-lowest" if center_lowest else DESIGN_BED_CONSTRAINT_MODEL),
        closure_policy="minimum unique volume with continuous design bottom, profile and actual transverse bed coupling",
        physical_triangle_plane_gradient=True,
        profile_mesh_breakpoint_union=True,
        minimum_volume_objective=True,
        support_group_count=int(len(np.unique(roots))),
        solved_support_groups=solved_groups,
        reused_optimal_components=reused_components,
        decomposition_policy="shared support vertices and complete global constraint rows; singleton optimum reused only with identical bounds and volume weights and feasible global rows",
        gradient_constraints=int(gradient_rows.sum()),
        profile_constraints=int(profile_rows.sum()),
        transverse_bed_coupling=width is not None,
        center_lowest=bool(center_lowest),
        continuous_center_lowest=bool(continuous_center_lowest),
        shared_section_constraints=sum(kind == "shared_section" for _, _, _, kind in constraints),
        internal_port_cap_policy="shared two-sided source-mesh sections omit physical endpoint cone; all strip and floor constraints retained",
        internal_port_node_indices=np.flatnonzero(internal_ports).tolist() if width is not None else [],
        continuous_center_floor_constraints=sum(kind == "continuous_floor" for _, _, _, kind in constraints),
        transverse_constraints=int(transverse_rows.sum()),
        transverse_node_cap_constraints=int(cap_count),
        transverse_bottom_slope_m_per_m=transverse_bottom_slope if width is not None else None,
        transverse_bank_ceiling_horizontal_per_vertical=2.0 if width is not None else None,
        active_solver_vertices=int(len(active)),
        solver_constraint_nonzeros=int(matrix.nnz),
        maximum_transverse_residual_m=float(np.max(residual[transverse_rows], initial=0.0)),
        maximum_gradient_residual_m_per_m=float(np.max(residual[gradient_rows])),
        maximum_profile_residual_m=float(np.max(residual[profile_rows], initial=0.0)),
        centerline_segments=int(gradient_rows.sum()),
    )
