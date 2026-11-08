"""Sampled macro bed-envelope requirements on the actual fan4 source model."""

import numpy as np


ALGORITHM = "sampled-fan4-channel-interval-elimination-v1"


def fan4_source_weights(point_xz_m, shape, origin_xz_m, spacing_m, fine_spacing_m):
    """Represent actual aligned fan4 source height by four native coefficients."""
    origin = np.asarray(origin_xz_m, float)
    point = np.asarray(point_xz_m, float)
    ratio = spacing_m / fine_spacing_m
    if not np.isfinite(ratio) or ratio < 1 or abs(ratio-round(ratio)) > 1e-9:
        raise ValueError("fan4 fine grid must divide the native spacing")
    maximum = origin + (np.array(shape)[::-1]-1)*spacing_m
    if point.shape != (2,) or not np.isfinite(point).all() or np.any(point < origin) or np.any(point > maximum):
        raise ValueError("fan4 point leaves native support")
    native = np.minimum(np.floor((point-origin)/spacing_m).astype(int), np.array(shape)[::-1]-2)
    fine = np.minimum(np.floor((point-origin)/fine_spacing_m).astype(int),
                      (np.array(shape)[::-1]-1)*int(round(ratio))-1)
    base = origin + fine*fine_spacing_m
    vertices = base + fine_spacing_m*np.array([[0.,0.],[1.,0.],[1.,1.],[0.,1.],[.5,.5]])
    bary = None
    for face in ((0,1,4),(1,2,4),(2,3,4),(3,0,4)):
        triangle = vertices[list(face)]
        uv = np.linalg.solve(np.column_stack((triangle[1]-triangle[0], triangle[2]-triangle[0])), point-triangle[0])
        candidate = np.array([1.-uv.sum(), uv[0], uv[1]])
        if candidate.min() >= -1e-9:
            local = (triangle-origin-native*spacing_m)/spacing_m
            x, z = local.T
            bary = candidate @ np.column_stack(((1-x)*(1-z), x*(1-z), (1-x)*z, x*z))
            break
    if bary is None:
        raise ValueError("fan4 point is outside its aligned fine cell")
    cx, cz = native
    ids = np.array([cz*shape[1]+cx, cz*shape[1]+cx+1, (cz+1)*shape[1]+cx, (cz+1)*shape[1]+cx+1])
    return ids.tolist(), bary.tolist()


def channel_section_intervals(height_m, offsets_m, *, bottom_width_m=8., fine_spacing_m=1.,
                              maximum_cut_m=4., design_depth_m=0., padding_m=0.):
    """Return center-bed intervals using the fine design's tapered cut envelope.

    Zero depth and padding relax cut bounds. Interval elimination is necessary
    and sufficient for this scalar section model, not for the full fine LP.
    A positive depth must be a known lower bound on the
    maximum endpoint design depth; positive padding needs its own proven bound.
    """
    height = np.asarray(height_m, float)
    distance = np.abs(np.asarray(offsets_m, float))
    padding = np.broadcast_to(np.asarray(padding_m, float), height.shape)
    if (height.shape != distance.shape or not np.isfinite(height).all()
            or not np.isfinite(distance).all() or not np.isfinite(padding).all()
            or np.any(padding < 0)
            or not np.isfinite([bottom_width_m, fine_spacing_m, maximum_cut_m, design_depth_m]).all()
            or not 0 <= design_depth_m <= .5
            or bottom_width_m <= 0 or fine_spacing_m <= 0 or maximum_cut_m <= 0):
        raise ValueError("finite aligned section heights and valid fine cut parameters required")
    half = bottom_width_m / 2 + np.sqrt(2.) * fine_spacing_m
    minimum = np.minimum(design_depth_m, np.maximum(0., (half + 2 * design_depth_m - distance) / 2))
    minimum += np.where(minimum > 0, padding, 0.)
    maximum = maximum_cut_m - padding
    rise = .02 * np.minimum(distance, half) + .5 * np.maximum(0., distance - half)
    return height - maximum - rise, height - minimum


def frozen_river_channel_feasibility_constraints(
        plan, shape, origin_xz_m, spacing_m, terminal_mask, *, source_edges,
        owner_domain_id=None, ocean_mask=None, pinned_mask=None, bottom_width_m=8.,
        fine_spacing_m=1., maximum_cut_m=4., design_depth_m=0., section_spacing_m=15.,
        maximum_sections=200000, maximum_constraints=2000000):
    """Build bounded sampled planning-envelope rows; report unsupported sections.

    Source edges are complete frozen receiver edges. Terminal/pinned heights stay
    in the rows; the projection retains their exact registered bounds. No LP is
    run here. This adds a planning envelope at arbitrary sampled points: the
    fine LP applies its rise ceilings only at mesh vertices and their projected
    centers, so these rows are not logical consequences of every fine LP.
    This does not certify continuous fan4 or longitudinal feasibility.
    """
    shape = tuple(shape)
    origin = np.asarray(origin_xz_m, float)
    terminal = np.asarray(terminal_mask, bool)
    if (len(shape) != 2 or min(shape) < 2 or origin.shape != (2,)
            or not np.isfinite(origin).all() or not np.isfinite(spacing_m) or spacing_m <= 0
            or terminal.shape != shape or not np.isfinite(section_spacing_m) or section_spacing_m <= 0):
        raise ValueError("finite aligned channel constraint support required")
    if (not isinstance(maximum_sections, (int, np.integer)) or maximum_sections < 1
            or not isinstance(maximum_constraints, (int, np.integer)) or maximum_constraints < 1):
        raise ValueError("positive integer channel budgets required")
    # Validate the physical parameters through the same interval implementation.
    channel_section_intervals(np.zeros(1), np.zeros(1), bottom_width_m=bottom_width_m,
                              fine_spacing_m=fine_spacing_m, maximum_cut_m=maximum_cut_m,
                              design_depth_m=design_depth_m)
    fan4_source_weights(origin, shape, origin, spacing_m, fine_spacing_m)
    masks = {}
    for name, value, dtype in (("owner", owner_domain_id, int), ("ocean", ocean_mask, bool),
                               ("pinned", pinned_mask, bool)):
        if value is not None:
            masks[name] = np.asarray(value, dtype)
            if masks[name].shape != shape:
                raise ValueError("aligned channel ownership and fixed masks required")
    if "owner" in masks and "ocean" not in masks:
        raise ValueError("owner validation requires registered ocean mask")
    maximum = origin + (np.array(shape)[::-1] - 1) * spacing_m
    coarse_shape = np.asarray(plan["height_m"]).shape
    receiver = np.asarray(plan["receiver"]).ravel()
    owners = np.asarray(plan["owner_domain_id"]).ravel()
    coarse_ocean = np.asarray(plan.get("ocean_mask", np.zeros(coarse_shape, bool)), bool).ravel()
    coarse_origin = np.asarray(plan["origin_xz_m"], float)
    coarse_spacing = float(plan["spacing_m"])
    edges = sorted(set((int(a), int(b)) for a, b in source_edges))
    geometry = []
    for first, second in edges:
        if (not 0 <= first < receiver.size or not 0 <= second < receiver.size
                or receiver[first] != second):
            raise ValueError("channel line is not an actual frozen receiver edge")
        if owners[first] != owners[second] and owners[second] != -1:
            raise ValueError("channel edge crosses registered domain ownership")
        if owners[first] != owners[second] and not coarse_ocean[second]:
            raise ValueError("channel -1 outlet is not registered coarse ocean")
        start = coarse_origin + np.array([first % coarse_shape[1], first // coarse_shape[1]]) * coarse_spacing
        finish = coarse_origin + np.array([second % coarse_shape[1], second // coarse_shape[1]]) * coarse_spacing
        vector = finish - start
        length = float(np.linalg.norm(vector))
        if not np.isfinite(length) or length <= 0:
            raise ValueError("channel edge needs positive finite length")
        geometry.append((start, vector, length))
    expected_sections = sum(int(np.ceil(length / section_spacing_m)) + 1 for _, _, length in geometry)
    if expected_sections > maximum_sections:
        raise ValueError("channel section budget exceeded before row assembly")
    half = bottom_width_m / 2 + np.sqrt(2.) * fine_spacing_m
    radius = half + 2 * maximum_cut_m
    floor_radius = radius + fine_spacing_m
    indices, coefficients, rhs, centers, pairs = [], [], [], [], []
    coverage, unsupported_examples = [], []
    row_count = 0

    for edge, (start, vector, length) in zip(edges, geometry):
        normal = np.array([-vector[1], vector[0]]) / length
        represented, missing = 0, 0
        for fraction in np.linspace(0., 1., int(np.ceil(length / section_spacing_m)) + 1):
            center = start + fraction * vector
            offsets = [-floor_radius, -radius, -half, -bottom_width_m/2, 0.,
                       bottom_width_m/2, half, radius, floor_radius]
            # Native crossings supplement physical bottom/rise/support
            # breakpoints. Outer support points supply only floor upper bounds.
            for grid_spacing in (spacing_m,):
                for axis in range(2):
                    if abs(normal[axis]) < 1e-12:
                        continue
                    lower, upper = sorted((center[axis] - floor_radius * normal[axis], center[axis] + floor_radius * normal[axis]))
                    grid = np.arange(np.ceil((lower-origin[axis])/grid_spacing),
                                     np.floor((upper-origin[axis])/grid_spacing)+1) * grid_spacing + origin[axis]
                    offsets.extend(((grid-center[axis])/normal[axis]).tolist())
            offsets = np.unique(np.round(offsets, 10))
            points = center + offsets[:, None] * normal
            if np.any(points < origin - 1e-8) or np.any(points > maximum + 1e-8):
                missing += 1
                if len(unsupported_examples) < 16:
                    unsupported_examples.append({"source_edge": list(edge), "center_xz_m": center.tolist(),
                                                 "reason": "complete_transverse_strip_leaves_support"})
                continue
            points = np.maximum(origin, np.minimum(points, maximum))
            if "owner" in masks:
                native = np.rint((points-origin)/spacing_m).astype(int)
                actual = masks["owner"][native[:, 1], native[:, 0]]
                ocean = masks["ocean"][native[:, 1], native[:, 0]]
                legal_ocean = (actual == -1) & ocean & (owners[edge[1]] == -1)
                if np.any((actual != owners[edge[0]]) & ~legal_ocean):
                    raise ValueError("channel transverse strip enters another registered owner")
            # Reverse floor rows belong only to the nearest frozen ray. Rise
            # ceilings remain valid for every represented point of this edge.
            closest = np.abs(offsets)
            for other_start, other_vector, _ in geometry:
                t = np.clip((points-other_start) @ other_vector / (other_vector @ other_vector), 0., 1.)
                closest = np.minimum(closest, np.linalg.norm(points-other_start-t[:, None]*other_vector, axis=1))
            floor_owned = np.abs(offsets) <= closest + 1e-8
            rise_represented = np.abs(offsets) <= radius + 1e-8
            lower, upper = channel_section_intervals(np.zeros(len(points)), offsets,
                bottom_width_m=bottom_width_m, fine_spacing_m=fine_spacing_m,
                maximum_cut_m=maximum_cut_m, design_depth_m=design_depth_m)
            sample_weights = [fan4_source_weights(point, shape, origin, spacing_m, fine_spacing_m) for point in points]
            count = int(rise_represented.sum()) * int(floor_owned.sum()) - int(np.sum(rise_represented & floor_owned))
            if row_count + count > maximum_constraints:
                raise ValueError("channel constraint budget exceeded before row assembly")
            row_count += count
            for p in np.flatnonzero(rise_represented):
                for q in np.flatnonzero(floor_owned):
                    if p == q:
                        continue
                    pi, pw = sample_weights[p]
                    qi, qw = sample_weights[q]
                    indices.append(pi+qi)
                    coefficients.append(pw+[-w for w in qw])
                    rhs.append(float(upper[q]-lower[p]))
                    centers.append(center.tolist())
                    pairs.append([points[p].tolist(), points[q].tolist()])
            represented += 1
        coverage.append({"source_edge": list(edge), "represented_sections": represented,
                         "unsupported_sections": missing, "edge_length_m": length})
    return {"columns": np.asarray(indices, np.int64).reshape(-1, 8),
            "coefficients": np.asarray(coefficients, float).reshape(-1, 8),
            "rhs": np.asarray(rhs, float), "world_xz_m": np.asarray(centers, float).reshape(-1, 2),
            "sample_pairs_xz_m": np.asarray(pairs, float).reshape(-1, 2, 2),
            "metadata": {"algorithm": ALGORITHM, "section_spacing_m": float(section_spacing_m),
                "bottom_width_m": float(bottom_width_m), "fine_spacing_m": float(fine_spacing_m),
                "maximum_cut_m": float(maximum_cut_m), "design_depth_lower_bound_m": float(design_depth_m),
                "padding_lower_bound_m": 0., "padding_provenance": "nonnegative fan4 padding relaxed to zero; actual fan4 source weights retained",
                "bottom_slope_m_per_m": .02, "bank_horizontal_per_vertical": 2.,
                "rise_radius_m": float(radius), "floor_sample_radius_m": float(floor_radius),
                "scope": "additional sampled macro planning envelope; interval equivalence only; final fine LP and cold audit required",
                "fine_lp_necessary_condition": False,
                "extra_planning_requirement": "rise envelope at arbitrary section samples is stronger than vertex-only fine LP rise rows",
                "terminal_policy": "retain registered terminal and pinned coefficients without waiver",
                "ownership_policy": "reject other domains; nearest-ray reverse floor within domain",
                "sample_policy": "center, physical bottom, guard, rise strip edges, expanded floor-support edges and native crossings; fine crossings, fan diagonals and between-section points not certified",
                "floor_support_limit": "sampled strip reaches fine mesh support radius; rounded mesh corner extent not completely represented",
                "constraints": row_count, "coefficient_slots": 8*row_count,
                "coverage": coverage, "unsupported_examples": unsupported_examples,
                "unsupported_sections": sum(item["unsupported_sections"] for item in coverage)}}
