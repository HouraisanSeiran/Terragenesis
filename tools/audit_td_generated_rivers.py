"""Cold-read generated TD river artifacts; measure saved graphs and mesh beds."""

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle
from terrain_pipeline.channel_geometry import _mesh_volume, _metric_channel_geometry_sample as _sample
from terrain_pipeline.channel_geometry import _barycentric, _line_constraints
from terrain_pipeline.surface_rivers.metric_naturalness_audit import sample_summary
from terrain_pipeline.surface_rivers.metric_td_generated_source import load_generated_td_source


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _pinned_json(path, sha):
    _require(file_sha256(path) == sha, "saved JSON SHA differs")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bundle_identity(bundle):
    _require(bundle["identity_sha256"] == identity(bundle["arrays"], bundle["metadata"]),
             "saved geometry identity differs")


def _load_saved_geometry(path, pin):
    _require(file_sha256(path) == pin["sha256"], "saved geometry SHA differs")
    with np.load(path, allow_pickle=False) as archive:
        if "manifest" in archive.files:
            return load_bundle(path, expected_sha256=pin["sha256"], validator=_bundle_identity,
                               max_bytes=128 * 1024 * 1024)
        bundle = {"arrays": {key: archive[key] for key in archive.files if key not in ("metadata", "identity_sha256")},
                  "metadata": json.loads(str(archive["metadata"].item())),
                  "identity_sha256": str(archive["identity_sha256"].item())}
    _bundle_identity(bundle)
    return bundle


def audit_network(arrays, terrain, minimum_area_m2):
    """Audit the saved full-domain receiver and local sums without rerouting."""
    size = terrain.elevation_m.size
    receiver = arrays["receiver"]
    _require(receiver.shape == (size,) and receiver.dtype.kind in "iu"
             and np.all((receiver >= -1) & (receiver < size)), "invalid saved receiver")
    _require(np.array_equal(arrays["source_height_m"], terrain.elevation_m), "saved source bed differs")
    edges = np.flatnonzero(receiver >= 0)
    target = receiver[edges]
    donors = np.bincount(target, minlength=size)
    indegree = donors.copy()
    queue = deque(np.flatnonzero(indegree == 0).tolist())
    area = np.full(size, terrain.cell_area_m2)
    local = arrays["local_q_m3_s"].ravel()
    _require(local.shape == (size,) and np.isfinite(local).all() and np.all(local >= 0), "invalid saved local Q")
    q = local.copy()
    order = np.ones(size, np.int64)
    maximum_order = np.zeros(size, np.int64)
    maximum_count = np.zeros(size, np.int64)
    processed = 0
    traversal = []
    while queue:
        cell = queue.popleft()
        processed += 1
        traversal.append(cell)
        order[cell] = maximum_order[cell] + (maximum_count[cell] >= 2) if maximum_order[cell] else 1
        downstream = receiver[cell]
        if downstream >= 0:
            area[downstream] += area[cell]
            q[downstream] += q[cell]
            if order[cell] > maximum_order[downstream]:
                maximum_order[downstream] = order[cell]
                maximum_count[downstream] = 1
            elif order[cell] == maximum_order[downstream]:
                maximum_count[downstream] += 1
            indegree[downstream] -= 1
            if indegree[downstream] == 0:
                queue.append(int(downstream))
    _require(processed == size, "saved receiver contains cycle")
    owner = np.full(size, -1, np.int64)
    for cell in reversed(traversal):
        owner[cell] = cell if receiver[cell] < 0 else owner[receiver[cell]]
    if "terminal_owner" in arrays:
        _require(np.array_equal(owner, arrays["terminal_owner"]), "saved terminal owner differs")
    _require(np.allclose(area, arrays["contributing_area_m2"].ravel(), rtol=0, atol=1e-6),
             "saved contributing area differs from receiver accumulation")
    _require(np.allclose(q, arrays["routed_q_m3_s"].ravel(), rtol=1e-11, atol=1e-10),
             "saved routed Q differs from local Q accumulation")
    terminals = receiver < 0
    source_ids = arrays["selected_edge_source_ids"]
    target_ids = arrays["selected_edge_target_ids"]
    expected = np.flatnonzero((area >= minimum_area_m2) & ~terminals)
    channel = area >= minimum_area_m2
    channel_order = np.zeros(size, np.int64)
    maximum_order.fill(0)
    maximum_count.fill(0)
    for cell in traversal:
        if not channel[cell]:
            continue
        channel_order[cell] = maximum_order[cell] + (maximum_count[cell] >= 2) if maximum_order[cell] else 1
        downstream = receiver[cell]
        if downstream >= 0 and channel[downstream]:
            if channel_order[cell] > maximum_order[downstream]:
                maximum_order[downstream] = channel_order[cell]
                maximum_count[downstream] = 1
            elif channel_order[cell] == maximum_order[downstream]:
                maximum_count[downstream] += 1
    _require(np.array_equal(source_ids, expected) and np.array_equal(target_ids, receiver[expected]),
             "selected edge inventory is not the complete area-threshold network")
    status = arrays["selected_edge_status"]
    _require(status.shape == source_ids.shape and np.all(status != ""), "selected edge status missing")
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((source_ids % cols * terrain.dx_m, source_ids // cols * terrain.dz_m))
    targets = np.column_stack((target_ids % cols * terrain.dx_m, target_ids // cols * terrain.dz_m))
    vectors = targets - points
    lengths = np.linalg.norm(vectors, axis=1)
    _require(np.all(lengths > 0), "zero-length selected edge")
    path_length = np.zeros(size)
    native_lengths = np.zeros(size)
    native_lengths[source_ids] = lengths
    for cell in reversed(traversal):
        if receiver[cell] >= 0 and channel[cell]:
            path_length[cell] = native_lengths[cell] + path_length[receiver[cell]]
    original_drop = terrain.elevation_m.ravel()[source_ids] - terrain.elevation_m.ravel()[target_ids]
    lookup = {int(cell): i for i, cell in enumerate(source_ids)}
    angles = []
    for i, cell in enumerate(target_ids):
        if int(cell) in lookup:
            second = vectors[lookup[int(cell)]]
            first = vectors[i]
            angles.append(float(np.arctan2(abs(first[0] * second[1] - first[1] * second[0]), first @ second)))
    bearing = np.arctan2(vectors[:, 1], vectors[:, 0])
    quantized = np.abs(bearing / (np.pi / 4) - np.rint(bearing / (np.pi / 4))) < 1e-10
    kinds, counts = np.unique(arrays["outlet_kind"][terminals], return_counts=True)
    return {
        "selected_edge_count": int(len(expected)), "status_counts": dict(zip(*[v.tolist() for v in np.unique(status, return_counts=True)])),
        "terminal_count": int(terminals.sum()), "terminal_kind_counts": dict(zip(kinds.tolist(), counts.tolist())),
        "terminal_area_residual_m2": float(area[terminals].sum() - size * terrain.cell_area_m2),
        "terminal_q_residual_m3_s": float(q[terminals].sum() - local.sum()),
        "selected_component_count": int(np.unique(owner[source_ids]).size),
        "maximum_selected_path_length_m": float(path_length.max()),
        "original_bed_uphill_selected_edge_count": int(np.count_nonzero(original_drop < -1e-8)),
        "original_bed_uphill_semantics": "routing candidate constraint, not a test of saved excavated bed",
        "length_m": sample_summary(lengths), "turn_angle_rad": sample_summary(angles),
        "d8_quantized_bearing_fraction": float(quantized.mean()) if len(quantized) else None,
        "drainage_density_km_per_km2": float(lengths.sum() * 1000 / (size * terrain.cell_area_m2)),
        "maximum_strahler_order": int(channel_order.max()),
        "maximum_full_grid_strahler_order": int(order.max()),
        "morphology_scope": "saved original-bed selected graph; grid directions retained; no naturalness certification",
    }


def mesh_flow_slopes(points, receiver, cells, vertices, triangles, bed, terrain, spacing):
    """Measure triangle-plane gradients; partitioning supplies intersections only."""
    partitions = _line_constraints(points, receiver, cells, vertices, triangles, terrain, spacing)
    first_center = len(vertices) - len(cells)
    _require(len(triangles) == 4 * len(cells)
             and np.array_equal(triangles[:, 2], np.repeat(np.arange(first_center, len(vertices)), 4)),
             "saved mesh is not canonical fan4 for independent triangle selection")
    gradients = {}
    slopes, lengths, selected_faces = [], [], []
    for start, end, fraction, node, target in partitions:
        flow = points[target] - points[node]
        full_length = np.linalg.norm(flow)
        anchor = vertices[start[0][0]]
        midpoint_local = (start[1] @ (vertices[start[0]] - anchor)
                          + end[1] @ (vertices[end[0]] - anchor)) / 2.
        cell = int(start[0][2]) - first_center
        best = None
        # At a crossing, endpoint barycentrics can name adjacent triangles.
        # Choose the triangle whose interior contains the segment midpoint.
        for face in range(4 * cell, 4 * cell + 4):
            ids = triangles[face]
            local = vertices[ids] - anchor
            uv = np.linalg.solve(np.column_stack((local[1] - local[0], local[2] - local[0])),
                                 midpoint_local - local[0])
            weights = np.r_[1. - uv.sum(), uv]
            score = float(weights.min())
            if best is None or score > best[0]:
                best = score, face
        _require(best[0] >= -1e-8, "intersection midpoint outside saved triangle support")
        face = best[1]
        if face not in gradients:
            ids = triangles[face]
            local = vertices[ids[1:]] - vertices[ids[0]]
            gradients[face] = np.linalg.solve(local, bed[ids[1:]] - bed[ids[0]])
        slopes.append(float(-gradients[face] @ (flow / full_length)))
        lengths.append(float(full_length * fraction))
        selected_faces.append(face)
    return np.asarray(slopes), np.asarray(lengths), np.asarray(selected_faces)


def audit_continuous_design(bundle, terrain, network=None, component_recipe_lower=None):
    """Certify a declared conservative design recipe on the saved actual mesh."""
    a, m = bundle["arrays"], bundle["metadata"]
    points, receiver = a["node_xz_m"], a["receiver"]
    vertices, triangles = a["vertices_xz_m"], a["triangles"]
    design = a["design_base_depth_m"]
    width = a["width_m"]
    mask = a.get("design_constraint_node_mask", np.ones(len(receiver), bool))
    _require(mask.shape == receiver.shape and mask.dtype.kind == "b", "invalid design constraint node mask")
    _require(np.any(mask), "declared continuous design has no constrained nodes")
    _require(design.shape == receiver.shape and np.isfinite(design).all() and np.all(design > 0.),
             "invalid original design depth evidence")
    if network is not None:
        ids = a["source_node_cell_ids"]
        _require(np.array_equal(design, network["base_depth_m"][ids])
                 and np.array_equal(width, network["width_m"][ids]), "saved design differs from original network forcing dimensions")
    h = m["config"]["fine_spacing_m"]
    _require(float(terrain.dx_m / h).is_integer() and float(terrain.dz_m / h).is_integer(),
             "analytic bilinear padding requires fine/native alignment")
    cells = a["sparse_cell_xy"]
    _require(len(triangles) == 4 * len(cells), "continuous certificate requires actual fan4 mesh")
    origin = np.array([terrain.x0_m, terrain.z0_m])
    for first in range(0, len(cells), 25_000):
        last = min(first + 25_000, len(cells))
        local = (vertices[triangles[4*first:4*last]] - origin) / h
        local -= np.repeat(cells[first:last], 4, axis=0)[:, None, :]
        center_vertices = np.all(np.isclose(local, .5, rtol=0., atol=1e-8), axis=2)
        corner_vertices = np.all(np.isclose(local, 0., rtol=0., atol=1e-8)
                                 | np.isclose(local, 1., rtol=0., atol=1e-8), axis=2)
        _require(np.all(center_vertices.sum(axis=1) == 1)
                 and np.all(corner_vertices.sum(axis=1) == 2), "saved triangles are not cell-corner/center fan4 geometry")
        codes = np.where(center_vertices, 4, np.rint(local[:, :, 0] + 2.*local[:, :, 1]).astype(int))
        codes.sort(axis=1)
        edge_codes = codes[:, 0] + 4*codes[:, 1]
        _require(np.all(np.sort(edge_codes.reshape(-1, 4), axis=1) == [4, 8, 13, 14]),
                 "saved fan4 cell has missing or duplicate canonical triangles")
    center = vertices[triangles].mean(axis=1)
    gx = np.floor((center[:, 0] - terrain.x0_m) / terrain.dx_m).astype(int)
    gz = np.floor((center[:, 1] - terrain.z0_m) / terrain.dz_m).astype(int)
    height = terrain.elevation_m
    cross = height[gz + 1, gx + 1] - height[gz + 1, gx] - height[gz, gx + 1] + height[gz, gx]
    triangle_padding = np.abs(cross) * h * h / (16. * terrain.cell_area_m2)
    mixed = "design_constraint_node_mask" in a and not np.all(mask)
    certified_triangles = a.get("design_constraint_triangle_mask", np.ones(len(triangles), bool))
    _require(certified_triangles.shape == (len(triangles),) and certified_triangles.dtype.kind == "b"
             and np.any(certified_triangles), "invalid continuous raw-cut triangle scope")
    _require(not mixed or "design_constraint_triangle_mask" in a, "mixed global lacks explicit raw-cut certificate scope")
    vertex_padding = np.zeros(len(vertices))
    np.maximum.at(vertex_padding, triangles[certified_triangles].ravel(),
                  np.repeat(triangle_padding[certified_triangles], 3))
    mesh_edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    unique_edges, edge_counts = np.unique(mesh_edges, axis=0, return_counts=True)
    exposed_edges = unique_edges[edge_counts == 1]
    origin = np.array([terrain.x0_m, terrain.z0_m])
    high = origin + [(terrain.elevation_m.shape[1] - 1) * terrain.dx_m,
                     (terrain.elevation_m.shape[0] - 1) * terrain.dz_m]
    edge_midpoints = vertices[exposed_edges].mean(axis=1)
    exterior_edges = np.any(np.isclose(edge_midpoints, origin, rtol=0., atol=1e-8)
                            | np.isclose(edge_midpoints, high, rtol=0., atol=1e-8), axis=1)
    interior_boundary = np.unique(exposed_edges[~exterior_edges])
    exterior_boundary = np.unique(exposed_edges[exterior_edges])
    lower = np.zeros(len(vertices))
    plateau_lower = np.zeros(len(vertices))
    tree = cKDTree(vertices)
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        _require(mask[i] == mask[j], "continuous design mask splits a represented edge")
        if not mask[i]:
            continue
        delta = points[j] - points[i]
        plateau_radius = max(width[i], width[j]) / 2. + np.sqrt(2.) * h
        near = np.asarray(tree.query_ball_point((points[i] + points[j]) / 2.,
                                               plateau_radius + 2. * max(design[i], design[j])
                                               + np.linalg.norm(delta) / 2.), np.int64)
        t = np.clip((vertices[near] - points[i]) @ delta / (delta @ delta), 0., 1.)
        distance = np.linalg.norm(vertices[near] - points[i] - t[:, None] * delta, axis=1)
        required = distance <= plateau_radius + 1e-8
        depth = max(design[i], design[j])
        plateau_lower[near[required]] = np.maximum(plateau_lower[near[required]], depth)
        bank_lower = np.minimum(depth, np.maximum(0., (plateau_radius + 2. * depth - distance) / 2.))
        lower[near] = np.maximum(lower[near], bank_lower)
    required_vertices = plateau_lower > 0.
    inherited_recipe = "design_constraint_node_mask" in a
    if inherited_recipe:
        _require(component_recipe_lower is not None, "global continuous certificate requires independently verified component recipe bounds")
        margins = a["cut_depth_m"][required_vertices] - component_recipe_lower[required_vertices]
        _require(np.all(margins >= -1e-8), "actual global bed loses verified continuous component bottom bounds")
    else:
        margins = a["cut_depth_m"][required_vertices] - vertex_padding[required_vertices] - plateau_lower[required_vertices]
        _require(np.all(margins >= -1e-8), "actual saved mesh fails continuous bottom width/design-depth lower bound")
    recipe_lower = lower + np.where(lower > 0., vertex_padding, 0.)
    saved_lower, saved_upper = a["design_minimum_cut_m"], a["design_maximum_cut_m"]
    _require(saved_lower.shape == lower.shape and saved_upper.shape == lower.shape
             and np.isfinite(saved_lower).all() and np.isfinite(saved_upper).all(), "invalid saved continuous design cut bounds")
    if "design_constraint_node_mask" not in a:
        _require(np.allclose(saved_lower, recipe_lower, rtol=0., atol=1e-8), "saved design lower differs from independent conservative recipe")
    else:
        _require(np.allclose(saved_lower, component_recipe_lower, rtol=0., atol=1e-8),
                 "global design lower differs from independently verified component bounds")
    _require(np.allclose(a["source_interpolation_padding_m"], vertex_padding, rtol=0., atol=1e-12),
             "saved source interpolation padding differs from raw bilinear certificate")
    if not mixed:
        expected_upper = m["config"]["max_cut_m"] - vertex_padding
        expected_upper[interior_boundary] = 0.
        _require(np.allclose(saved_upper, expected_upper, rtol=0., atol=1e-8),
                 "saved design upper differs from raw bilinear budget/interior seam certificate")
    _require(np.all(a["cut_depth_m"] >= saved_lower - 1e-8)
             and np.all(a["cut_depth_m"] <= saved_upper + 1e-8), "actual saved cut violates declared necessary design bounds")
    raw_upper = np.max(a["cut_depth_m"][triangles], axis=1) + triangle_padding
    _require(np.all(raw_upper[certified_triangles] <= m["config"]["max_cut_m"] + 1e-8), "continuous original bilinear cut exceeds budget")
    partitions = _line_constraints(points, receiver, a["sparse_cell_xy"], vertices, triangles, terrain, h)
    edge_lookup = {int(i): e for e, i in enumerate(np.flatnonzero(receiver >= 0))}
    residuals = []
    for start, end, _, i, j in partitions:
        if not mask[i]:
            continue
        edge = edge_lookup[i]
        lo, hi = a["profile_offsets"][edge:edge + 2]
        delta = points[j] - points[i]
        for ids, bary in (start, end):
            t = float(bary @ ((vertices[ids] - points[i]) @ delta) / (delta @ delta))
            desired = np.interp(t, a["profile_t"][lo:hi], a["profile_center_bed_m"][lo:hi])
            residuals.append(float(bary @ a["bed_elevation_m"][ids] - desired))
    cell_lookup = {tuple(cell): index for index, cell in enumerate(a["sparse_cell_xy"])}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    from terrain_pipeline.channel_geometry import _cell_at_point
    for edge, i in enumerate(np.flatnonzero(receiver >= 0)):
        if not mask[i]:
            continue
        j = receiver[i]
        lo, hi = a["profile_offsets"][edge:edge + 2]
        for t, desired in zip(a["profile_t"][lo:hi], a["profile_center_bed_m"][lo:hi]):
            point = points[i] + t * (points[j] - points[i])
            cell = cell_lookup[_cell_at_point(point, cell_lookup, origin, h)]
            ids, bary = _barycentric(point, cell, vertices, triangles)
            residuals.append(float(bary @ a["bed_elevation_m"][ids] - desired))
    _require(np.max(residuals) <= 1e-8, "actual saved mesh exceeds continuous center-profile bed ceiling")
    interior_seam_cut = a["cut_depth_m"][interior_boundary]
    if not mixed:
        _require(not np.any(interior_seam_cut > 1e-8), "new conservative mesh has nonzero incision at interior support seam")
    return {"passed": True, "status": "continuous_conservative_bottom_depth_profile_raw_cut_verified"
            if mixed else "continuous_conservative_bottom_depth_profile_raw_cut_and_interior_seam_verified",
            "applies_to": "this saved artifact only; does not certify legacy component design parameters",
            "bottom_bound_method": "independently verified component recipes preserved on identical final fan4 triangles"
            if inherited_recipe else "full touching triangles via diameter-expanded endpoint-max design lower bound",
            "minimum_continuous_design_depth_margin_m": None if inherited_recipe else float(margins.min()),
            "minimum_preserved_component_bottom_bound_margin_m": float(margins.min()) if inherited_recipe else None,
            "maximum_certified_raw_cut_m": float(raw_upper[certified_triangles].max()),
            "certified_raw_cut_triangle_count": int(certified_triangles.sum()),
            "maximum_source_interpolation_padding_m": float(triangle_padding[certified_triangles].max()),
            "maximum_continuous_profile_residual_m": float(np.max(residuals)),
            "interior_support_seam_status": "not_claimed_for_mixed_legacy_global" if mixed else "zero_cut_verified",
            "interior_support_boundary_vertex_count": int(len(interior_boundary)),
            "unknown_domain_boundary_vertex_count": int(len(exterior_boundary))}


def audit_transverse_bed(bundle, terrain):
    """Cold-read every declared edge/vertex pair, using actual saved triangles."""
    a, m = bundle["arrays"], bundle["metadata"]
    policy = m.get("design_bed_policy", {})
    if not policy.get("transverse_bed_policy"):
        return {"status": "not_declared_for_this_artifact"}
    spacing = m["config"]["fine_spacing_m"]
    slope = policy["transverse_bottom_slope_m_per_m"]
    bank = policy["transverse_bank_horizontal_per_vertical"]
    guard = policy["transverse_bottom_guard_m"]
    _require(np.isfinite(slope) and 0 <= slope < .5 and bank == 2.0
             and np.isclose(guard, np.sqrt(2.) * spacing), "invalid declared transverse bed policy")
    vertices, bed, triangles = a["vertices_xz_m"], a["bed_elevation_m"], a["triangles"]
    lookup = {tuple(cell): index for index, cell in enumerate(a["sparse_cell_xy"])}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    tree = cKDTree(vertices)

    def elevations(points):
        coordinate = (points - origin) / spacing
        grid = np.floor(coordinate).astype(np.int64)
        cell_ids = np.array([lookup.get(tuple(cell), -1) for cell in grid])
        for row in np.flatnonzero(cell_ids < 0):
            for dx, dz in ((-1, 0), (0, -1), (-1, -1)):
                candidate = grid[row] + [dx, dz]
                cell = lookup.get(tuple(candidate))
                if cell is not None and np.all(coordinate[row] >= candidate - 1e-8) and np.all(coordinate[row] <= candidate + 1 + 1e-8):
                    cell_ids[row] = cell
                    break
        _require(np.all(cell_ids >= 0), "transverse center projection outside saved support")
        result = np.full(len(points), np.nan)
        for face in range(4):
            ids = triangles[4 * cell_ids + face]
            v0, v1, v2 = vertices[ids[:, 0]], vertices[ids[:, 1]], vertices[ids[:, 2]]
            first, second, delta = v1 - v0, v2 - v0, points - v0
            determinant = first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]
            u = (delta[:, 0] * second[:, 1] - delta[:, 1] * second[:, 0]) / determinant
            v = (first[:, 0] * delta[:, 1] - first[:, 1] * delta[:, 0]) / determinant
            represented = (u >= -1e-7) & (v >= -1e-7) & (u + v <= 1 + 1e-7)
            result[represented] = ((1 - u - v) * bed[ids[:, 0]] + u * bed[ids[:, 1]] + v * bed[ids[:, 2]])[represented]
        _require(np.isfinite(result).all(), "transverse projection absent from actual saved triangles")
        return result

    mask = a.get("design_constraint_node_mask", np.ones(len(a["receiver"]), bool))
    count = skipped = 0
    maximum = -np.inf
    for first, second in enumerate(a["receiver"]):
        if second < 0:
            continue
        if not mask[first] or not mask[second]:
            skipped += 1
            continue
        start, end = a["node_xz_m"][[first, second]]
        delta = end - start
        length = np.linalg.norm(delta)
        half = max(a["width_m"][first], a["width_m"][second]) / 2 + guard
        radius = half + bank * m["config"]["max_cut_m"]
        ids = np.asarray(tree.query_ball_point((start + end) / 2, np.hypot(length / 2, radius) + 1e-7), dtype=np.int64)
        fraction = (vertices[ids] - start) @ delta / length ** 2
        projections = start + fraction[:, None] * delta
        distance = np.linalg.norm(vertices[ids] - projections, axis=1)
        valid = (fraction >= 0) & (fraction <= 1) & (distance > 1e-9) & (distance <= radius + 1e-9)
        ids, projections, distance = ids[valid], projections[valid], distance[valid]
        if not len(ids):
            continue
        actual = bed[ids] - elevations(projections)
        allowed = np.minimum(distance, half) * slope + np.maximum(distance - half, 0) / bank
        residual = actual - allowed
        maximum = max(maximum, float(residual.max()))
        count += len(ids)
    _require(maximum <= 1e-7, "actual saved transverse bed exceeds center-coupled ceiling")
    cap_audit = {"status": "not_declared_for_this_artifact", "scope": "edge strips only; node exterior cones not certified"}
    if policy.get("transverse_node_cap_policy"):
        dot_tolerance = policy["transverse_node_cap_dot_tolerance_m"]
        _require(np.isfinite(dot_tolerance) and dot_tolerance == 1e-10,
                 "invalid declared node cap dot tolerance")
        points, receiver, widths = a["node_xz_m"], a["receiver"], a["width_m"]
        neighbors = [[] for _ in receiver]
        enabled = np.zeros(len(receiver), bool)
        for first, second in enumerate(receiver):
            if second < 0:
                continue
            neighbors[first].append(int(second))
            neighbors[second].append(first)
            if mask[first] and mask[second]:
                enabled[[first, second]] = True
        cap_count = excluded_nodes = 0
        cap_maximum = -np.inf
        for node, adjacent in enumerate(neighbors):
            if not adjacent:
                continue
            if not mask[node] or not enabled[node]:
                excluded_nodes += 1
                continue
            half = max(widths[[node, *adjacent]]) / 2 + guard
            radius = half + bank * m["config"]["max_cut_m"]
            ids = np.asarray(tree.query_ball_point(points[node], radius + 1e-9), dtype=np.int64)
            relative = vertices[ids] - points[node]
            distance = np.linalg.norm(relative, axis=1)
            exterior = (distance > 1e-9) & (distance <= radius + 1e-9)
            for other in adjacent:
                direction = points[other] - points[node]
                length = np.linalg.norm(direction)
                _require(length > 0, "zero length incident edge in node cap")
                exterior &= relative @ (direction / length) <= dot_tolerance
            ids, distance = ids[exterior], distance[exterior]
            if not len(ids):
                continue
            node_bed = elevations(points[node:node + 1])[0]
            allowed = np.minimum(distance, half) * slope + np.maximum(distance - half, 0) / bank
            residual = bed[ids] - node_bed - allowed
            cap_maximum = max(cap_maximum, float(residual.max()))
            cap_count += len(ids)
        _require(cap_maximum <= 1e-7, "actual saved node exterior cap exceeds node-coupled ceiling")
        cap_audit = {"status": "verified", "checked_node_vertex_pairs": cap_count,
                     "legacy_excluded_node_count": excluded_nodes,
                     "maximum_node_cap_ceiling_residual_m": cap_maximum if cap_count else None,
                     "scope": "all represented incident directions; enabled nodes with at least one enabled incident edge"}
    return {"status": "verified", "checked_edge_vertex_pairs": count, "legacy_excluded_edge_count": skipped,
            "maximum_transverse_ceiling_residual_m": maximum if count else None,
            "node_exterior_cap_audit": cap_audit,
            "method": "independent actual triangle barycentric elevations; every declared overlapping edge"}


def audit_saved_centerline(bundle, terrain):
    """Check saved coordinates independently of the shaping implementation."""
    a, m = bundle["arrays"], bundle["metadata"]
    if "anchor_mask" not in a:
        return {"status": "not_declared_for_this_artifact"}
    receiver, points, ids = a["receiver"], a["node_xz_m"], a["source_node_cell_ids"]
    columns = terrain.elevation_m.shape[1]
    original = np.column_stack((terrain.x0_m + ids % columns * terrain.dx_m,
                                terrain.z0_m + ids // columns * terrain.dz_m))
    _require(np.array_equal(original, a["original_node_xz_m"]), "saved original centerline differs from source IDs")
    donors = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    anchors = (donors != 1) | (receiver < 0)
    _require(np.array_equal(anchors, a["anchor_mask"]), "saved anchor inventory differs from topology")
    _require(np.array_equal(points[anchors], original[anchors]), "source, confluence or terminal anchor moved")
    policy = m.get("centerline_policy")
    corridor = policy["corridor_m"] if policy else 6.0
    rise = policy["maximum_original_source_rise_m"] if policy else .5
    _require(np.isfinite(corridor) and 0 <= corridor <= 60 and np.isfinite(rise) and 0 <= rise <= .5,
             "invalid declared centerline bounds")
    if policy:
        _require(corridor == m["config"]["centerline_corridor_m"], "centerline policy and config corridor differ")
    offset = np.linalg.norm(points - original, axis=1)
    _require(np.all(offset <= corridor + 1e-8), "saved centerline exceeds declared original corridor")
    sampled, cells = _sample(terrain.elevation_m, points, terrain)
    original_height = terrain.elevation_m.ravel()[ids]
    _require(np.all(sampled - original_height <= rise + 1e-8), "saved centerline source rise exceeds policy")
    _require(np.all(terrain.valid_mask.ravel()[cells]), "saved centerline enters invalid source terrain")
    edges = np.flatnonzero(receiver >= 0)
    starts, ends = points[edges], points[receiver[edges]]
    lengths = np.linalg.norm(ends - starts, axis=1)
    _require(np.all(lengths > 0), "saved centerline has zero length edge")
    midpoints = (starts + ends) / 2
    pairs = cKDTree(midpoints).query_pairs(float(lengths.max()) + 1e-8)

    def cross(first, second):
        return first[0] * second[1] - first[1] * second[0]

    for first, second in pairs:
        first_ids = {int(edges[first]), int(receiver[edges[first]])}
        second_ids = {int(edges[second]), int(receiver[edges[second]])}
        shared = first_ids & second_ids
        if shared:
            node = next(iter(shared))
            other_first = next(iter(first_ids - shared))
            other_second = next(iter(second_ids - shared))
            left, right = points[other_first] - points[node], points[other_second] - points[node]
            _require(not (abs(cross(left, right)) <= 1e-8 and np.dot(left, right) > 0),
                     "saved adjacent centerline edges overlap")
            continue
        left, right = ends[first] - starts[first], ends[second] - starts[second]
        denominator = cross(left, right)
        delta = starts[second] - starts[first]
        if abs(denominator) > 1e-10:
            along_first, along_second = cross(delta, right) / denominator, cross(delta, left) / denominator
            _require(not (-1e-10 <= along_first <= 1 + 1e-10 and -1e-10 <= along_second <= 1 + 1e-10),
                     "saved nonadjacent centerline edges cross")
        elif abs(cross(delta, left)) <= 1e-8:
            projections = np.array([np.dot(starts[second] - starts[first], left),
                                    np.dot(ends[second] - starts[first], left)]) / np.dot(left, left)
            _require(projections.max() < 0 or projections.min() > 1,
                     "saved nonadjacent centerline edges overlap")
    return {"status": "verified", "policy": policy or "legacy6m-offset-0.5m-source-rise",
            "maximum_offset_m": float(offset.max()), "maximum_source_rise_m": float((sampled - original_height).max()),
            "fixed_anchor_count": int(anchors.sum()), "crossing_count": 0}


def audit_geometry(bundle, terrain, network=None):
    """Interpolate the saved mesh along saved lines, without rebuilding geometry."""
    _bundle_identity(bundle)
    a, m = bundle["arrays"], bundle["metadata"]
    ids, receiver = a["source_node_cell_ids"], a["receiver"]
    _require(ids.ndim == 1 and ids.dtype.kind in "iu" and np.unique(ids).size == ids.size
             and np.all((ids >= 0) & (ids < terrain.elevation_m.size)), "invalid or duplicate mesh source nodes")
    _require(receiver.shape == ids.shape and receiver.dtype.kind in "iu"
             and np.all((receiver >= -1) & (receiver < ids.size)), "invalid mesh receiver")
    _require(m["source_identity_sha256"] == terrain.identity_sha256, "geometry source identity differs")
    if "source_height_m" in a:
        _require(np.array_equal(a["source_height_m"], terrain.elevation_m), "geometry source bed differs")
    centerline_audit = audit_saved_centerline(bundle, terrain)
    transverse_audit = audit_transverse_bed(bundle, terrain)
    vertices, triangles = a["vertices_xz_m"], a["triangles"]
    source, _ = _sample(terrain.elevation_m, vertices, terrain)
    bed, cut = a["bed_elevation_m"], a["cut_depth_m"]
    _require(np.isfinite(bed).all() and np.isfinite(cut).all() and np.all(cut >= -1e-9), "invalid saved bed or cut")
    _require(float(cut.max()) <= m["config"]["max_cut_m"] + 1e-8, "actual cut exceeds declared bound")
    _require(np.allclose(source, a["source_elevation_m"], rtol=0, atol=1e-8)
             and np.allclose(source - cut, bed, rtol=0, atol=1e-8), "mesh source/bed/cut mismatch")
    slopes, segment_lengths, _ = mesh_flow_slopes(a["node_xz_m"], a["receiver"], a["sparse_cell_xy"],
                                                 vertices, triangles, bed, terrain, m["config"]["fine_spacing_m"])
    _require(len(slopes) > 0 and not np.any(slopes < -1e-8),
             "actual saved mesh bed has uphill or no centerline segments")
    minimum_slope = m.get("minimum_bed_slope_m_per_m")
    if minimum_slope is not None:
        _require(np.isfinite(minimum_slope) and minimum_slope > 0., "invalid declared minimum physical bed slope")
        _require(np.all(slopes >= minimum_slope - 1e-8),
                 "actual saved mesh slope falls below declared physical minimum")
    width, depth = a["width_m"], a["base_depth_m"]
    _require(np.isfinite(width).all() and np.isfinite(depth).all() and np.all(width > 0)
             and np.all(depth > 0), "invalid saved channel width/depth")
    design_depth = a.get("design_base_depth_m")
    if design_depth is not None:
        _require(design_depth.shape == depth.shape and np.isfinite(design_depth).all()
                 and np.all(design_depth > 0.), "invalid original design depth statistics")
    port_cut, port_bed, actual_width = np.array([]), np.array([]), np.array([])
    design_width, support = np.array([]), np.empty((0, 4), dtype="U32")
    if "port_cut_depth_m" in a:
        port_cut = a["port_cut_depth_m"]
        port_vertices = triangles[a["port_triangle_ids"]]
        bary = a["port_barycentric"]
        _require(np.isfinite(bary).all() and np.all(bary >= -1e-8)
                 and np.allclose(bary.sum(axis=-1), 1., rtol=0, atol=1e-8), "invalid cross-section barycentric coordinates")
        _require(np.allclose(np.sum(vertices[port_vertices] * bary[..., None], axis=-2),
                            a["port_profile_xz_m"], rtol=0, atol=1e-7)
                 and np.allclose(np.sum(cut[port_vertices] * bary, axis=-1), port_cut, rtol=0, atol=1e-8),
                 "saved cross-section ports differ from actual mesh")
        port_bed = np.sum(bed[port_vertices] * bary, axis=-1)
        actual_width = np.linalg.norm(a["port_profile_xz_m"][:, 2] - a["port_profile_xz_m"][:, 1], axis=1)
        port_edges = a["port_edge_node_indices"]
        design_width = width[port_edges].mean(axis=1)
        support = a.get("port_support_status", np.full((len(port_edges), 4), "represented", dtype="U32"))
        _require(support.shape == (len(port_edges), 4)
                 and np.all(np.isin(support, ["represented", "clipped_unknown_exterior"])),
                 "invalid saved port support classification")
        origin = np.array([terrain.x0_m, terrain.z0_m])
        high = origin + [(terrain.elevation_m.shape[1] - 1) * terrain.dx_m,
                         (terrain.elevation_m.shape[0] - 1) * terrain.dz_m]
        for edge, (i, j) in enumerate(port_edges):
            center = (a["node_xz_m"][i] + a["node_xz_m"][j]) / 2.
            delta = a["node_xz_m"][j] - a["node_xz_m"][i]
            normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
            half = design_width[edge] / 2.
            lo, hi = a["profile_offsets"][edge:edge + 2]
            bank = 2. * np.interp(.5, a["profile_t"][lo:hi],
                                   a["profile_source_m"][lo:hi] - a["profile_center_bed_m"][lo:hi])
            requested_offsets = np.array([-half - bank, -half, half, half + bank])
            if "port_requested_profile_xz_m" in a:
                _require(np.allclose(a["port_requested_profile_xz_m"][edge],
                                    center + requested_offsets[:, None] * normal, rtol=0, atol=1e-7),
                         "saved requested section differs from declared width/profile")
            lower, upper = -np.inf, np.inf
            for axis in range(2):
                if abs(normal[axis]) < 1e-14:
                    _require(origin[axis] - 1e-8 <= center[axis] <= high[axis] + 1e-8, "section center outside known domain")
                    continue
                limits = (np.array([origin[axis], high[axis]]) - center[axis]) / normal[axis]
                lower, upper = max(lower, limits.min()), min(upper, limits.max())
            actual_offsets = np.clip(requested_offsets, lower, upper)
            expected_positions = center + actual_offsets[:, None] * normal
            _require(np.allclose(expected_positions, a["port_profile_xz_m"][edge], rtol=0, atol=1e-7),
                     "cropped section is not the requested normal intersected with known domain")
            clipped = np.abs(requested_offsets - actual_offsets) > 1e-8
            _require(np.array_equal(clipped, support[edge] == "clipped_unknown_exterior"),
                     "partial section support label differs from actual clipping")
        _require(np.all(actual_width <= design_width + 1e-7), "represented section exceeds requested bottom width")
        for key, actual in (("port_design_width_m", design_width), ("port_actual_width_m", actual_width)):
            if key in a:
                _require(a[key].shape == actual.shape and np.allclose(a[key], actual, rtol=0, atol=1e-7),
                         "saved port width differs from measured section: " + key)
        if "port_complete_cross_section" in a:
            _require(np.array_equal(a["port_complete_cross_section"], np.all(support == "represented", axis=1)),
                     "saved complete-section flag differs from measured support")
    volume = float(_mesh_volume(vertices, triangles, cut))
    _require(np.isclose(volume, m["cut_volume_m3"], rtol=1e-9, atol=1e-6), "saved material volume differs")
    edges = {(int(ids[i]), int(ids[j])) for i, j in enumerate(receiver) if j >= 0}
    continuous = audit_continuous_design(bundle, terrain, network) if m.get("design_bed_policy") and "design_constraint_node_mask" not in a else None
    return {"node_count": len(ids), "edge_count": len(edges), "mesh_vertex_count": len(vertices),
            "mesh_triangle_count": len(triangles), "actual_bed_segment_slope": sample_summary(slopes),
            "actual_bed_slope_method": "independent_saved_triangle_plane_gradient_projected_along_flow",
            "slope_comparison_tolerance_m_per_m": 1e-8,
            "minimum_actual_bed_slope_m_per_m": float(slopes.min()),
            "minimum_slope_margin_m_per_m": float(slopes.min() - minimum_slope) if minimum_slope is not None else None,
            "centerline_triangle_segment_length_m": sample_summary(segment_lengths),
            "uphill_actual_bed_segment_count": int(np.count_nonzero(slopes < -1e-8)),
            "near_zero_actual_bed_slope_fraction": float(np.mean(np.asarray(slopes) <= 1e-6)),
            "minimum_bed_slope_m_per_m": minimum_slope,
            "minimum_slope_policy_status": "declared_physical_minimum_verified" if minimum_slope is not None else "legacy_unbounded_near_zero_slope",
            "width_m": sample_summary(width),
            "designed_base_depth_m": sample_summary(design_depth) if design_depth is not None else None,
            "saved_base_depth_parameter_m": sample_summary(depth),
            "legacy_propagated_profile_depth_m": sample_summary(depth) if design_depth is None else None,
            "depth_statistics_source": "original network design_base_depth_m" if design_depth is not None
            else "original design unavailable; legacy propagated profile depth reported separately",
            "actual_port_cut_depth_m": sample_summary(port_cut.ravel()),
            "actual_port_bed_elevation_m": sample_summary(port_bed.ravel()),
            "actual_port_bottom_width_m": sample_summary(actual_width),
            "requested_port_bottom_width_m": sample_summary(design_width),
            "actual_to_requested_bottom_width_ratio": sample_summary(actual_width / design_width),
            "partial_cross_section_count": int(np.count_nonzero(np.any(support != "represented", axis=1))),
            "fully_represented_cross_section_count": int(np.count_nonzero(np.all(support == "represented", axis=1))),
            "port_support_counts": dict(zip(*[v.tolist() for v in np.unique(support, return_counts=True)])),
            "width_depth_ratio": sample_summary(width / design_depth) if design_depth is not None else None,
            "width_depth_ratio_semantics": "width divided by original network design depth"
            if design_depth is not None else "not reported without original design depth evidence",
            "cut_volume_m3": volume,
            "maximum_cut_m": float(cut.max()), "continuous_design_certificate": continuous,
            "saved_centerline_policy_audit": centerline_audit,
            "saved_transverse_bed_audit": transverse_audit,
            "cross_section_semantics": "saved mesh port cuts; width is a design parameter; original design and legacy propagated profile depth are reported separately"
            if actual_width.size else "no ports in this artifact; final bed sections measured separately"}, edges


def saved_centerline_metrics(points, receiver):
    """Measure only saved represented centreline edges, including shaped positions."""
    size = len(points)
    source = np.flatnonzero(receiver >= 0)
    target = receiver[source]
    vectors = points[target] - points[source]
    lengths = np.linalg.norm(vectors, axis=1)
    _require(np.all(lengths > 0), "nonpositive saved centreline edge length")
    indegree = np.bincount(target, minlength=size)
    pending = deque(np.flatnonzero(indegree == 0).tolist())
    traversal = []
    while pending:
        node = pending.popleft()
        traversal.append(node)
        downstream = receiver[node]
        if downstream >= 0:
            indegree[downstream] -= 1
            if indegree[downstream] == 0:
                pending.append(int(downstream))
    _require(len(traversal) == size, "saved centreline cycle")
    native_length = np.zeros(size)
    native_length[source] = lengths
    path_length = np.zeros(size)
    for node in reversed(traversal):
        if receiver[node] >= 0:
            path_length[node] = native_length[node] + path_length[receiver[node]]
    edge_vectors = {int(node): vector for node, vector in zip(source, vectors)}
    turns = []
    for node, downstream in zip(source, target):
        if int(downstream) not in edge_vectors:
            continue
        first, second = edge_vectors[int(node)], edge_vectors[int(downstream)]
        turns.append(float(np.arctan2(abs(first[0] * second[1] - first[1] * second[0]), first @ second)))
    bearing = np.arctan2(vectors[:, 1], vectors[:, 0])
    quantized = np.abs(bearing / (np.pi / 4.) - np.rint(bearing / (np.pi / 4.))) < 1e-10
    return {"scope": "represented saved global mesh centreline, not all routing candidates",
            "edge_count": len(source), "actual_total_centerline_length_m": float(lengths.sum()),
            "actual_maximum_continuous_path_length_m": float(path_length.max()) if size else 0.,
            "actual_edge_length_m": sample_summary(lengths), "actual_turn_angle_rad": sample_summary(turns),
            "actual_d8_quantized_bearing_fraction": float(quantized.mean()) if len(quantized) else None,
            "bearing_quantization_tolerance_in_pi_over_4": 1e-10}


def audit_global_geometry(bundle, components, terrain, network=None, component_certificates=None):
    result, edges = audit_geometry(bundle, terrain, network)
    a, m = bundle["arrays"], bundle["metadata"]
    cells, vertices, triangles = a["sparse_cell_xy"], a["vertices_xz_m"], a["triangles"]
    _require(np.unique(cells, axis=0).shape == cells.shape
             and np.unique(vertices, axis=0).shape == vertices.shape
             and np.unique(np.sort(triangles, axis=1), axis=0).shape == triangles.shape,
             "global cells, vertices or triangles are duplicated")
    _require(len(triangles) == 4 * len(cells), "global fan4 cell/triangle count differs")
    tri = vertices[triangles]
    area = np.abs((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1])
                  - (tri[:, 1, 1] - tri[:, 0, 1]) * (tri[:, 2, 0] - tri[:, 0, 0])) / 2.
    spacing = m["config"]["fine_spacing_m"]
    _require(np.allclose(area, spacing * spacing / 4., rtol=0, atol=1e-8), "global mesh has noncanonical fan4 triangle areas")
    vertex_lookup = {tuple(point): index for index, point in enumerate(vertices)}
    envelope = np.zeros(len(vertices))
    necessary_lower = np.zeros(len(vertices))
    legacy_lower = np.zeros(len(vertices))
    new_vertex_mask = np.zeros(len(vertices), bool)
    new_cells = set()
    node_lookup = {int(node): index for index, node in enumerate(a["source_node_cell_ids"])}
    new_node_mask = np.zeros(len(a["receiver"]), bool)
    sum_component_volume = 0.
    component_cells = set()
    for component_index, component in enumerate(components):
        ca, cm = component["arrays"], component["metadata"]
        component_cells.update(map(tuple, ca["sparse_cell_xy"]))
        indices = np.array([vertex_lookup[tuple(point)] for point in ca["vertices_xz_m"]])
        np.maximum.at(envelope, indices, ca["cut_depth_m"])
        needed = ca["design_minimum_cut_m"] if cm.get("design_bed_policy") else ca["cut_depth_m"]
        np.maximum.at(necessary_lower, indices, needed)
        node_indices = np.array([node_lookup[int(node)] for node in ca["source_node_cell_ids"]])
        _require(np.array_equal(a["node_xz_m"][node_indices], ca["node_xz_m"])
                 and np.array_equal(a["width_m"][node_indices], ca["width_m"]),
                 "global represented line/dimensions differ from saved components")
        if cm.get("design_bed_policy"):
            certificate = component_certificates[component_index] if component_certificates is not None else audit_continuous_design(component, terrain, network)
            _require(certificate is not None and certificate.get("passed") is True,
                     "global design component has no independent continuous certificate")
            new_vertex_mask[indices] = True
            new_cells.update(map(tuple, ca["sparse_cell_xy"]))
            new_node_mask[node_indices] = True
        else:
            np.maximum.at(legacy_lower, indices, ca["cut_depth_m"])
        sum_component_volume += cm["cut_volume_m3"]
        if m.get("design_bed_policy"):
            global_edges = {int(node): edge for edge, node in enumerate(np.flatnonzero(a["receiver"] >= 0))}
            for component_edge, node in enumerate(np.flatnonzero(ca["receiver"] >= 0)):
                global_edge = global_edges[int(node_indices[node])]
                glo, ghi = a["profile_offsets"][global_edge:global_edge + 2]
                clo, chi = ca["profile_offsets"][component_edge:component_edge + 2]
                for key in ("profile_t", "profile_source_m", "profile_center_bed_m"):
                    _require(np.array_equal(a[key][glo:ghi], ca[key][clo:chi]),
                             "global saved profile differs from component evidence: " + key)
    _require(component_cells == set(map(tuple, cells)), "global cell support differs from component union")
    new_design = bool(m.get("design_bed_policy"))
    minimum = necessary_lower if new_design else envelope
    _require(np.all(a["cut_depth_m"] >= minimum - 1e-8), "global bed erases necessary component incision")
    if new_design:
        _require(np.allclose(a["design_minimum_cut_m"], necessary_lower, rtol=0., atol=1e-8),
                 "global necessary lower differs from old cut/new design component union")
        expected_triangles = np.repeat(np.array([tuple(cell) in new_cells for cell in cells]), 4)
        for key, expected in (("design_constraint_node_mask", new_node_mask),
                              ("design_constraint_vertex_mask", new_vertex_mask),
                              ("design_constraint_triangle_mask", expected_triangles)):
            _require(np.array_equal(a[key], expected), "global continuous design scope differs from saved component provenance: " + key)
        expected_upper = np.full(len(vertices), m["config"]["max_cut_m"])
        expected_upper[new_vertex_mask] -= a["source_interpolation_padding_m"][new_vertex_mask]
        mesh_edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
        unique_edges, counts = np.unique(mesh_edges, axis=0, return_counts=True)
        exposed = unique_edges[counts == 1]
        origin = np.array([terrain.x0_m, terrain.z0_m])
        high = origin + [(terrain.elevation_m.shape[1]-1)*terrain.dx_m,
                         (terrain.elevation_m.shape[0]-1)*terrain.dz_m]
        midpoint = vertices[exposed].mean(axis=1)
        domain_edges = np.any(np.isclose(midpoint, origin, atol=1e-8, rtol=0.)
                              | np.isclose(midpoint, high, atol=1e-8, rtol=0.), axis=1)
        interior_boundary = np.unique(exposed[~domain_edges])
        zero_boundary = interior_boundary[new_vertex_mask[interior_boundary] & (legacy_lower[interior_boundary] == 0.)]
        expected_upper[zero_boundary] = 0.
        _require(np.allclose(a["design_maximum_cut_m"], expected_upper, atol=1e-8, rtol=0.),
                 "global cut upper differs from independent scoped raw-budget/boundary reconstruction")
        result["continuous_design_certificate"] = audit_continuous_design(bundle, terrain, network, necessary_lower)
    preclosure = float(_mesh_volume(vertices, triangles, minimum))
    _require(np.isclose(preclosure, m["preclosure_cut_volume_m3"], rtol=1e-9, atol=1e-6),
             "global preclosure volume differs from independently reconstructed necessary lower")
    cell_lookup = {tuple(cell): i for i, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    section_cut, section_bed = [], []
    partial_sections = 0
    full_sections = 0
    for component in components:
        ca = component["arrays"]
        support = ca.get("port_support_status", np.full((len(ca["port_edge_node_indices"]), 4), "represented", dtype="U32"))
        partial_sections += int(np.count_nonzero(np.any(support != "represented", axis=1)))
        full_sections += int(np.count_nonzero(np.all(support == "represented", axis=1)))
        for point in component["arrays"]["port_profile_xz_m"].reshape(-1, 2):
            key = tuple(np.floor((point - origin) / spacing).astype(int))
            found = None
            for candidate in (key, (key[0] - 1, key[1]), (key[0], key[1] - 1), (key[0] - 1, key[1] - 1)):
                if candidate not in cell_lookup:
                    continue
                try:
                    found = _barycentric(point, cell_lookup[candidate], vertices, triangles)
                    break
                except ValueError:
                    continue
            _require(found is not None, "saved cross-section location absent from global mesh")
            ids, weights = found
            section_cut.append(float(weights @ a["cut_depth_m"][ids]))
            section_bed.append(float(weights @ a["bed_elevation_m"][ids]))
    component_envelope_volume = float(_mesh_volume(vertices, triangles, envelope))
    result.update(unique_cell_count=len(cells), unique_triangle_count=len(triangles),
                  represented_centerline=saved_centerline_metrics(a["node_xz_m"], a["receiver"]),
                  preclosure_cut_volume_m3=preclosure, component_sum_volume_m3=sum_component_volume,
                  component_max_envelope_cut_volume_m3=component_envelope_volume,
                  preclosure_semantics="old actual cut/new design minimum bounds" if new_design else "component actual cut maximum envelope",
                  overlap_double_count_m3=sum_component_volume - component_envelope_volume,
                  union_additional_cut_volume_m3=result["cut_volume_m3"] - preclosure,
                  reclosure_net_change_m3=result["cut_volume_m3"] - component_envelope_volume,
                  final_cross_section_cut_depth_m=sample_summary(section_cut),
                  final_cross_section_bed_elevation_m=sample_summary(section_bed),
                  partial_cross_section_count=partial_sections, fully_represented_cross_section_count=full_sections,
                  cross_section_semantics="component port locations resampled on final global mesh; not premerge component elevations")
    return result, edges


def reference_scale_gate(reference, terrain, cutoff):
    expected = {"spacing_m_xz": [terrain.dx_m, terrain.dz_m],
                "shape_zx": list(terrain.elevation_m.shape), "minimum_area_m2": cutoff}
    mismatches = [key for key, value in expected.items() if reference.get(key) != value]
    return {"status": "scale_matched_reference_only" if not mismatches else "not_comparable_scale_mismatch",
            "mismatched_fields": mismatches, "required_scale": expected, "natural_certification": False}


def audit_material_ledger(ledger, global_result, *, continuous_design=False):
    checks = [("unique_cut_volume_m3", "cut_volume_m3"),
              ("component_sum_cut_volume_m3", "component_sum_volume_m3"),
              ("overlap_double_count_m3", "overlap_double_count_m3"),
              ("union_monotone_additional_cut_volume_m3", "union_additional_cut_volume_m3")]
    if continuous_design:
        checks.extend([("component_max_envelope_cut_volume_m3", "component_max_envelope_cut_volume_m3"),
                       ("reclosure_net_change_m3", "reclosure_net_change_m3"),
                       ("necessary_lower_cut_volume_m3", "preclosure_cut_volume_m3")])
    for ledger_key, result_key in checks:
        _require(np.isclose(ledger[ledger_key], global_result[result_key], rtol=1e-9, atol=1e-6),
                 "final global material ledger differs: " + ledger_key)


def audit_sample(report_path, *, expected_sha256=None):
    report_path = Path(report_path)
    report_sha = expected_sha256 or file_sha256(report_path)
    report = _pinned_json(report_path, report_sha)
    source_metadata = report["source_registration"]["source_metadata"]
    registration = load_generated_td_source(source_metadata["generation_report_path"], source_metadata["sample_index"],
                                            expected_report_sha256=source_metadata["generation_report_sha256"])
    terrain = registration["terrain"]
    _require(registration["metadata"] == report["source_registration"], "source registration changed")
    model_metadata = source_metadata["model_metadata"]
    model_digest = hashlib.sha256(json.dumps(model_metadata, sort_keys=True).encode()).hexdigest()
    _require(model_digest == source_metadata["generation_identity"], "frozen model/config identity differs")
    _require(terrain.elevation_m.shape == (513, 513) and terrain.dx_m == 30. and terrain.dz_m == 30.,
             "full native 513-square 30m source required")
    network_record = report["network"]
    path = report_path.parent / network_record["path"]
    _require(file_sha256(path) == network_record["sha256"], "saved network SHA differs")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    cutoff = report["config"]["min_contributing_area_m2"]
    _require(cutoff == 1_000_000., "new full-domain evaluation requires frozen 1km2 cutoff")
    observation = audit_network(arrays, terrain, cutoff)
    local_expected = arrays["rainfall_mm_h"] * terrain.cell_area_m2 * report["config"]["runoff_coefficient"] / 1000. / 3600.
    _require(np.allclose(local_expected, arrays["local_q_m3_s"], rtol=1e-12, atol=1e-12),
             "saved local Q differs from declared synthetic rainfall")
    geometry_results, represented, component_bundles = [], set(), []
    accounted = np.zeros(len(arrays["selected_edge_source_ids"]), np.int64)
    for record in report.get("component_records", []):
        edge_indices = np.asarray(record["selected_edge_indices"], np.int64)
        _require(edge_indices.ndim == 1 and np.unique(edge_indices).size == len(edge_indices)
                 and np.all((edge_indices >= 0) & (edge_indices < len(accounted))), "invalid component edge inventory")
        accounted[edge_indices] += 1
        _require(np.all(arrays["selected_edge_status"][edge_indices] == record["status"]),
                 "component status differs from saved edge status")
        geometry = record.get("geometry")
        if geometry is None:
            _require(record["status"] == "rejected" and isinstance(record.get("reason"), str)
                     and bool(record["reason"]), "rejected component has no explicit reason")
            continue
        _require(record["status"] == "accepted", "mesh attached to unaccepted component")
        bundle = _load_saved_geometry(report_path.parent / geometry["path"], geometry)
        _require(bundle["identity_sha256"] == geometry["identity_sha256"], "external geometry pin differs")
        result, edges = audit_geometry(bundle, terrain, arrays)
        component_edges = set(zip(map(int, arrays["selected_edge_source_ids"][edge_indices]),
                                  map(int, arrays["selected_edge_target_ids"][edge_indices])))
        _require(edges == component_edges, "saved mesh edge set differs from its component inventory")
        _require(not represented.intersection(edges), "generated edge duplicated across meshes")
        represented.update(edges)
        result["component_id"] = record["component_id"]
        geometry_results.append(result)
        component_bundles.append(bundle)
    selected = set(zip(map(int, arrays["selected_edge_source_ids"]), map(int, arrays["selected_edge_target_ids"])))
    accepted = {edge for edge, status in zip(zip(map(int, arrays["selected_edge_source_ids"]),
                                               map(int, arrays["selected_edge_target_ids"])), arrays["selected_edge_status"])
                if status == "accepted"}
    _require(represented == accepted, "accepted edge inventory differs from actual saved meshes")
    pending = int(np.count_nonzero(arrays["selected_edge_status"] == "geometry_pending"))
    if not pending:
        _require(np.all(accounted == 1), "selected edges missing or duplicated in component records")
    global_result = {"status": "not_available_global_union_pending"}
    if report.get("global_bed") is not None:
        pin = report["global_bed"]
        global_bundle = _load_saved_geometry(report_path.parent / pin["path"], pin)
        _require(global_bundle["identity_sha256"] == pin["identity_sha256"], "global mesh identity pin differs")
        global_result, global_edges = audit_global_geometry(global_bundle, component_bundles, terrain, arrays,
            [result["continuous_design_certificate"] for result in geometry_results])
        _require(global_edges == accepted, "final global mesh edge inventory differs from all accepted edges")
        audit_material_ledger(report["material_ledger"], global_result,
            continuous_design=bool(global_bundle["metadata"].get("design_bed_policy")))
        global_result["status"] = "final_global_mesh_independently_audited"
    unresolved = ["unknown exterior and vertical datum", "uncalibrated channel width/depth coefficients",
                  "synthetic diagnostic rainfall Q without water surface or transport simulation",
                  "no scale-matched real morphology/cross-section reference supplied"]
    if "working_fill_depth_m" in arrays:
        fill = arrays["working_fill_depth_m"]
        _require(np.isfinite(fill).all() and np.all(fill >= -1e-8), "invalid working fill")
        _require(np.allclose(terrain.elevation_m + fill, arrays["working_elevation_m"], rtol=0, atol=1e-8),
                 "saved working surface differs from raw plus diagnostic fill")
        _require(float(fill.max()) <= report["config"]["max_cut_m"] + 1e-8,
                 "diagnostic spill work surface exceeds declared bounded depth")
        observation["working_fill_m"] = sample_summary(fill.ravel())
        observation["working_fill_semantics"] = "routing work surface only; not material fill or observed lake water"
    result = {"schema": "td-generated-river-saved-audit-v1", "sample_index": source_metadata["sample_index"],
              "report_sha256": report_sha, "source_sha256": terrain.source_sha256,
              "source_status": "verified_frozen_TD_raw_report_plan_bytes", "source_provenance_status": terrain.provenance_status,
              "frozen_model_revision": model_metadata["model"]["revision"],
              "frozen_upstream_revision": model_metadata["upstream"],
              "scale": {"shape_zx": [513, 513], "spacing_m_xz": [30., 30.], "minimum_area_m2": cutoff},
              "network": observation, "saved_meshes": geometry_results, "final_global_mesh": global_result,
              "coverage": {"selected": len(selected), "represented": len(represented),
                           "not_represented": len(selected - represented), "pending": pending},
              "status": ("incomplete_geometry_pending" if pending else "no_generated_geometry"
                         if not represented else "generated_components_global_union_pending"
                         if report.get("global_bed") is None
                         else "saved_artifacts_audited_not_realism_certified"),
              "real_reference": {"status": "not_assessed_no_scale_matched_reference"},
              "unresolved": unresolved, "natural_certification": False, "publishable": False}
    result["identity_sha256"] = identity({}, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sample-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _require(bool(args.manifest) != bool(args.sample_report), "one manifest or sample report required")
    if args.sample_report:
        result = audit_sample(args.sample_report)
    else:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        samples = manifest["samples"]
        _require(len(samples) == 6, "all six generated samples required")
        results = []
        for item in samples:
            print(json.dumps({"event": "sample_audit_started", "sample_index": item["sample_index"],
                              "coverage": {"represented": item.get("accepted_edges"),
                                           "not_represented": item.get("rejected_edges")},
                              "coverage_source": "manifest_declared"}), flush=True)
            sample_result = audit_sample(args.manifest.parent / item["report_path"], expected_sha256=item["report_sha256"])
            results.append(sample_result)
            print(json.dumps({"event": "sample_audit_completed", "sample_index": sample_result["sample_index"],
                              "coverage": sample_result["coverage"]}), flush=True)
        _require([item["sample_index"] for item in results] == list(range(6)), "six-sample order differs")
        result = {"schema": "td-generated-river-all-six-saved-audit-v1", "manifest_sha256": file_sha256(args.manifest),
                  "samples": results, "natural_certification": False, "publishable": False}
    _require(not args.output.exists(), "audit evidence output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "status": result.get("status", "all_six_audited")}))
