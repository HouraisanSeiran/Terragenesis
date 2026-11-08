"""Geometry-only refinement of a frozen delta graph in local (u, v) metres.

This is a bounded, offline construction experiment. Nodes, flow and topology
are frozen. Unavoidable conflicts in the input are reported rather than
resolved by changing a junction or cutting through a protected source hill.
"""
from __future__ import annotations

import copy

import numpy as np
from scipy import ndimage as ndi
from scipy.interpolate import CubicSpline
from scipy.spatial import cKDTree
from skimage.graph import MCP_Geometric

from terrain_pipeline.channel_geometry import turn_penalty
from terrain_pipeline.delta_network_site import derive_seed
from terrain_pipeline.delta_network_skeleton import edge_points, validate_graph


ALGORITHM_VERSION = 'frozen-delta-path-refinement-v2'


def _resample(points, step_m):
    """Subdivide each segment, retaining every original vertex exactly."""
    pieces = []
    for start, end in zip(points[:-1], points[1:]):
        count = max(1, int(np.ceil(np.linalg.norm(end - start) / step_m)))
        pieces.append(start + np.arange(count)[:, None] / count * (end - start))
    return np.vstack([*pieces, points[-1:]])


def _sample(array, points, spec, *, order=1):
    coordinates = (points - [spec.u0_m, spec.v0_m]) / spec.spacing_m - 0.5
    return ndi.map_coordinates(array, coordinates.T, order=order, mode='nearest')


def _turn_cost(points):
    directions = np.diff(points, axis=0)
    lengths = np.linalg.norm(directions, axis=1)
    if np.any(lengths < 1e-8):
        return float('inf')
    cosine = np.sum(directions[:-1] * directions[1:], axis=1) / (lengths[:-1] * lengths[1:])
    # The shared policy is free through 45 degrees; only larger turns need
    # its scalar evaluation. It also excludes 90 degrees exactly.
    return sum(turn_penalty(a, b) for a, b, c in zip(directions[:-1], directions[1:], cosine)
               if c < np.sqrt(0.5))


def _intersects(first, second, *, same=False):
    """Detect crossings, touches and overlaps, except a shared graph endpoint."""
    starts, ends = second[:-1], second[1:]
    lower, upper = np.minimum(starts, ends), np.maximum(starts, ends)
    for index, (start, end) in enumerate(zip(first[:-1], first[1:])):
        candidates = np.flatnonzero(np.all(upper >= np.minimum(start, end) - 1e-8, axis=1)
                                   & np.all(lower <= np.maximum(start, end) + 1e-8, axis=1))
        if same:
            candidates = candidates[candidates > index + 1]
        if not len(candidates):
            continue
        a, b = starts[candidates], ends[candidates]
        direction, other = end - start, b - a
        cross = lambda x, y: x[..., 0] * y[..., 1] - x[..., 1] * y[..., 0]
        c1, c2 = cross(direction, a - start), cross(direction, b - start)
        c3, c4 = cross(other, start - a), cross(other, end - a)
        hits = candidates[(c1 * c2 <= 1e-8) & (c3 * c4 <= 1e-8)]
        for other_index in hits:
            if not same:
                allowed = False
                for point, first_at_end in ((first[0], index == 0),
                                            (first[-1], index == len(first) - 2)):
                    for other_point, second_at_end in ((second[0], other_index == 0),
                                                       (second[-1], other_index == len(second) - 2)):
                        if first_at_end and second_at_end and np.linalg.norm(point - other_point) < 1e-7:
                            # Opposite rays touch only at the common endpoint;
                            # collinear rays in the same direction overlap.
                            ray_a = end - point if index == 0 else start - point
                            ray_b = ends[other_index] - point if other_index == 0 else starts[other_index] - point
                            allowed = abs(cross(ray_a, ray_b)) > 1e-8 or ray_a @ ray_b < 0
                if allowed:
                    continue
            return True
    return False


def _crossing_pairs(paths):
    pairs = []
    for index, path in enumerate(paths):
        if _intersects(path, path, same=True):
            pairs.append([index, index])
        for other in range(index):
            if _intersects(path, paths[other]):
                pairs.append([other, index])
    return pairs


def _terrain_metrics(points, width_m, terrain, clearance, protected, spec):
    step_m = spec.spacing_m * 0.4
    dense = _resample(points, step_m)
    directions = np.gradient(dense, axis=0)
    normals = np.column_stack([-directions[:, 1], directions[:, 0]])
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    bank = normals * (0.5 * width_m + 0.25 * spec.spacing_m)
    heights = np.maximum.reduce([_sample(terrain, dense + offset, spec)
                                 for offset in (np.zeros_like(bank), bank, -bank)])
    cost = float(np.mean(np.maximum(heights - 8.0, 0.0) ** 2))
    # EDT is distance to protected cell centres. Include their half diagonal
    # and half the segment sample interval for a conservative width envelope.
    required = width_m * 0.5 + spec.spacing_m / np.sqrt(2) + step_m * 0.5
    intrusion = np.maximum(required - _sample(clearance, dense, spec), 0.0) if protected else np.zeros(len(dense))
    segment_m = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    conflict_m = float(np.sum(segment_m * ((intrusion[:-1] > 0) | (intrusion[1:] > 0))))
    return dict(high_bed_cost=cost, protected_conflict_length_m=conflict_m,
                protected_max_intrusion_m=float(intrusion.max()))


def _repair_lowland(path, width_m, surface, clearance, lowland_clearance, spec, others):
    """Find a bounded terrain route, keeping only half a native cell tangent."""
    spacing = spec.spacing_m
    origin = np.array([spec.u0_m, spec.v0_m])
    length_m = np.linalg.norm(np.diff(path, axis=0), axis=1).sum()
    corridor_m = min(2500.0, max(800.0, length_m * 0.4, width_m * 2.0))
    lower = np.maximum(np.floor((path.min(axis=0) - corridor_m - origin) / spacing).astype(int), 0)
    upper = np.minimum(np.ceil((path.max(axis=0) + corridor_m - origin) / spacing).astype(int), surface.shape)
    region = tuple(slice(a, b) for a, b in zip(lower, upper))
    shape = tuple(upper - lower)
    sampled = _resample(path, spacing * 0.4)
    cells = np.floor((sampled - origin) / spacing).astype(int) - lower
    near = np.ones(shape, bool)
    near[cells[:, 0], cells[:, 1]] = False
    deviation = ndi.distance_transform_edt(near) * spacing
    # A 100 m lowland margin also protects the identical geometry when saved
    # into 100 m cells. It does not enlarge the physical river section.
    safe = (lowland_clearance[region] >= 100.0) & (deviation <= corridor_m)
    safe &= clearance[region] >= width_m * 0.5 + spacing / np.sqrt(2)
    costs = 1.0 + (deviation / max(width_m, 200.0)) ** 2 * 0.1
    costs += np.maximum(surface[region] - 4.0, 0.0) ** 2 * 0.02
    costs[~safe] = np.inf
    tangent_m = min(spacing * 0.5, length_m * 0.05)
    first_direction = path[1] - path[0]
    last_direction = path[-1] - path[-2]
    start = path[0] + first_direction / np.linalg.norm(first_direction) * tangent_m
    end = path[-1] - last_direction / np.linalg.norm(last_direction) * tangent_m
    first = np.floor((start - origin) / spacing).astype(int) - lower
    last = np.floor((end - origin) / spacing).astype(int) - lower
    if not np.isfinite(costs[tuple(first)]) or not np.isfinite(costs[tuple(last)]):
        return None
    solver = MCP_Geometric(costs, fully_connected=True)
    cumulative, _ = solver.find_costs([tuple(first)], [tuple(last)])
    if not np.isfinite(cumulative[tuple(last)]):
        return None
    route = np.asarray(solver.traceback(tuple(last)))
    points = origin + (route + lower + 0.5) * spacing
    # End cell centres are replaced by exact tangent anchors before fairing.
    points = np.vstack([path[0], start, points[1:-1], end, path[-1]])
    candidates = []
    for sigma in (3.0, 2.0, 1.0, 0.5):
        inner = ndi.gaussian_filter1d(points[1:-1], sigma, axis=0, mode='nearest')
        inner[0], inner[-1] = start, end
        distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(inner, axis=0), axis=1))]
        if np.any(np.diff(distance) < 1e-6):
            continue
        spline = CubicSpline(distance, inner, bc_type=(
            (1, first_direction / np.linalg.norm(first_direction)),
            (1, last_direction / np.linalg.norm(last_direction))))
        stations = np.linspace(0., distance[-1], int(np.ceil(distance[-1] / (spacing * 0.3))) + 1)
        candidate = np.vstack([path[0], spline(stations), path[-1]])
        cost = _turn_cost(candidate)
        if not np.isfinite(cost) or _intersects(candidate, candidate, same=True):
            continue
        if any(_intersects(candidate, other) for other in others):
            continue
        probes = _resample(candidate, spacing * 0.25)
        if (_sample(surface, probes, spec, order=0).max() > 10.0
                or _sample(lowland_clearance, probes, spec).min() < 85.0
                or _sample(clearance, probes, spec).min()
                < width_m * 0.5 + spacing / np.sqrt(2) + spacing * 0.2):
            continue
        candidates.append((cost, np.linalg.norm(np.diff(candidate, axis=0), axis=1).sum(), candidate))
    return min(candidates, key=lambda item: item[:2])[2] if candidates else None


def refine_graph(graph, spec, surface, source_bed, source_ocean, *, seed=20260903):
    """Return an independent graph and JSON-compatible refinement diagnostics.

    Arrays have shape ``(spec.nu, spec.nv)`` and use cell-centre local metres.
    Protected terrain is source land at >=45 m. Irregular bends use a narrow
    corridor; blocked lowland centreline sections may use a bounded 2.5 km
    terrain detour. A short native-cell endpoint tangent keeps junction angles.
    """
    shape = (spec.nu, spec.nv)
    surface, source_bed, source_ocean = map(np.asarray, (surface, source_bed, source_ocean))
    if (surface.shape != shape or source_bed.shape != shape or source_ocean.shape != shape
            or source_ocean.dtype != bool or not np.isfinite(surface).all()
            or not np.isfinite(source_bed).all() or not np.isfinite(spec.spacing_m)
            or not np.isfinite([spec.u0_m, spec.v0_m]).all()
            or spec.spacing_m <= 0 or not isinstance(seed, (int, np.integer))):
        raise ValueError('finite surfaces and boolean source ocean must match the metric SiteSpec grid')
    initial_validation = validate_graph(graph)
    if not initial_validation['ok']:
        raise ValueError('refinement requires a legal frozen graph')
    paths = [edge_points(graph, index).copy() for index in range(len(graph.edge_from))]
    for path in paths:
        if not np.isfinite(path).all() or np.any(np.linalg.norm(np.diff(path, axis=0), axis=1) <= 1e-8):
            raise ValueError('frozen paths must contain finite, nonzero segments')
    original_crossings = _crossing_pairs(paths)
    protected_mask = (~source_ocean) & (source_bed >= 45.0)
    has_protection = bool(protected_mask.any())
    clearance = (ndi.distance_transform_edt(~protected_mask) * spec.spacing_m if has_protection
                 else np.full(shape, np.hypot(spec.nu, spec.nv) * spec.spacing_m))
    terrain = np.maximum(surface, np.where(source_ocean, surface, source_bed))
    lowland_clearance = (ndi.distance_transform_edt(surface <= 10.0) * spec.spacing_m
                         if np.any(surface > 10.0) else np.full(shape, np.hypot(*shape) * spec.spacing_m))
    results, subseeds = [], {}
    for index, original in enumerate(paths):
        width_m = float(graph.edge_w[index])
        step_m = min(spec.spacing_m * 0.75, max(30.0, width_m / 3.0))
        base = _resample(original, step_m)
        distance = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(base, axis=0), axis=1))]
        length_m = distance[-1]
        # One short native-cell tangent fixes the junction headings without
        # freezing an entire obsolete 240 m construction segment over a ridge.
        pin_start = pin_end = min(spec.spacing_m * 0.75, length_m * 0.1)
        free = (distance > pin_start + 1e-6) & (distance < length_m - pin_end - 1e-6)
        before = _terrain_metrics(original, width_m, terrain, clearance, has_protection, spec)
        item = dict(edge_id=index, accepted=False, before=before, after=before.copy(),
                    max_displacement_m=0.0, reason='no_legal_improvement')
        if np.count_nonzero(free) < 5 or length_m < 6 * step_m:
            item['reason'] = 'short_reach_or_frozen_tangent_portions'
            results.append(item)
            continue
        sub_seed = derive_seed('delta-path-refinement', index, world_seed=int(seed))
        subseeds[str(index)] = sub_seed
        rng = np.random.Generator(np.random.PCG64(sub_seed))
        typical_step = float(np.mean(np.diff(distance)))
        noise = np.zeros(len(base))
        for correlation_m, weight in ((max(4 * width_m, 450.0), 0.60),
                                       (max(9 * width_m, 1000.0), 0.28),
                                       (max(18 * width_m, 2000.0), 0.12)):
            component = ndi.gaussian_filter1d(rng.standard_normal(len(base)),
                                               max(1.0, correlation_m / typical_step / 3.0), mode='reflect')
            component -= component.mean()
            component /= max(float(np.std(component)), 1e-8)
            noise += weight * component
        amplitude_m = min(width_m * 1.2 + 25.0, 0.045 * length_m, 380.0)
        desired = noise * amplitude_m
        corridor_m = min(max(4 * width_m, 500.0), 0.12 * length_m, 1400.0)
        directions = np.gradient(base, axis=0)
        normals = np.column_stack([-directions[:, 1], directions[:, 0]])
        normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
        offsets = np.linspace(-corridor_m, corridor_m, 25)
        probes = base[:, None, :] + normals[:, None, :] * offsets[None, :, None]
        heights = _sample(terrain, probes.reshape(-1, 2), spec).reshape(len(base), -1)
        costs = np.maximum(heights - 8.0, 0.0) ** 2 / 16.0
        if has_protection:
            probe_clearance = _sample(clearance, probes.reshape(-1, 2), spec).reshape(len(base), -1)
            required = width_m * 0.5 + spec.spacing_m
            costs += np.maximum(required - probe_clearance, 0.0) ** 2 * 10.0
        costs += ((offsets[None, :] - desired[:, None]) / max(amplitude_m, 1.0)) ** 2
        terrain_target = offsets[np.argmin(costs, axis=1)]
        target = ndi.gaussian_filter1d(terrain_target, max(1.0, width_m / typical_step), mode='nearest')
        taper = np.minimum(np.clip((distance - pin_start) / max(2 * width_m, 3 * step_m), 0, 1),
                           np.clip((length_m - pin_end - distance) / max(2 * width_m, 3 * step_m), 0, 1))
        taper = taper * taper * (3 - 2 * taper)
        target *= taper
        proposals = [target]
        if before['protected_conflict_length_m'] > 0 or before['high_bed_cost'] > 0:
            # A coherent choice of valley side avoids pointwise lateral minima
            # switching sides inside an inherited hill conflict.
            proposals.extend([(desired * 0.4 - corridor_m * 0.75) * taper,
                              (desired * 0.4 + corridor_m * 0.75) * taper])
        for lateral in proposals:
            for scale in (1.0, 0.65, 0.35, 0.15):
                candidate = base + normals * (lateral * scale)[:, None]
                candidate[~free] = base[~free]
                # Fair the geometric result as well as its scalar displacement;
                # this removes corner artefacts from the changing normal frame.
                for _ in range(3):
                    averaged = 0.2 * candidate[:-2] + 0.6 * candidate[1:-1] + 0.2 * candidate[2:]
                    candidate[1:-1][free[1:-1]] = averaged[free[1:-1]]
                grid_min = np.array([spec.u0_m, spec.v0_m])
                grid_max = grid_min + np.array(shape) * spec.spacing_m
                if np.any(candidate < grid_min) or np.any(candidate > grid_max):
                    continue
                cost = _turn_cost(candidate)
                if not np.isfinite(cost) or cost > _turn_cost(original) + 1e-8:
                    continue
                if _intersects(candidate, candidate, same=True):
                    continue
                if any(_intersects(candidate, other) for other_index, other in enumerate(paths) if index != other_index):
                    continue
                after = _terrain_metrics(candidate, width_m, terrain, clearance, has_protection, spec)
                if (after['protected_conflict_length_m'] > before['protected_conflict_length_m'] + 1e-6
                        or after['protected_max_intrusion_m'] > before['protected_max_intrusion_m'] + 1e-6
                        or after['high_bed_cost'] > before['high_bed_cost'] + 0.05):
                    continue
                displacement_m = float(np.max(np.linalg.norm(candidate - base, axis=1)))
                if displacement_m < 1.0:
                    continue
                paths[index] = candidate
                item.update(accepted=True, after=after, max_displacement_m=displacement_m,
                            reason='legal_width_and_terrain_constrained_bend')
                break
            if item['accepted']:
                break
        results.append(item)
    for index, path in enumerate(paths):
        probes = _resample(path, spec.spacing_m * 0.25)
        before_max = float(_sample(surface, probes, spec, order=0).max())
        before_margin = float(_sample(lowland_clearance, probes, spec).min())
        item = results[index]
        item['lowland_repair'] = dict(needed=before_max > 10.0 or before_margin < 100.0,
                                      accepted=False, before_center_surface_max_m=before_max,
                                      before_lowland_margin_m=before_margin)
        if item['lowland_repair']['needed']:
            candidate = _repair_lowland(path, float(graph.edge_w[index]), surface, clearance,
                                        lowland_clearance, spec,
                                        [other for other_index, other in enumerate(paths) if index != other_index])
            if candidate is not None:
                paths[index] = candidate
                item['accepted'] = True
                item['reason'] = 'legal_reconstructable_lowland_detour'
                item['lowland_repair']['accepted'] = True
                item['lowland_repair']['path_length_before_m'] = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
                item['lowland_repair']['path_length_after_m'] = float(np.linalg.norm(np.diff(candidate, axis=0), axis=1).sum())
                deviation_m = float(cKDTree(_resample(path, spec.spacing_m * 0.25)).query(candidate)[0].max())
                item['lowland_repair']['maximum_detour_from_previous_path_m'] = deviation_m
                item['max_displacement_m'] = max(item['max_displacement_m'], deviation_m)
                item['after'] = _terrain_metrics(candidate, float(graph.edge_w[index]), terrain,
                                                  clearance, has_protection, spec)
        probes = _resample(paths[index], spec.spacing_m * 0.25)
        item['lowland_repair']['after_center_surface_max_m'] = float(_sample(surface, probes, spec, order=0).max())
        item['lowland_repair']['after_lowland_margin_m'] = float(_sample(lowland_clearance, probes, spec).min())
    refined = copy.deepcopy(graph)
    refined.pt_off = np.r_[0, np.cumsum([len(path) for path in paths])].astype(np.int64)
    refined.pts_uv = np.vstack(paths)
    refined.edge_len = np.array([np.linalg.norm(np.diff(path, axis=0), axis=1).sum() for path in paths])
    validation = validate_graph(refined)
    final_crossings = _crossing_pairs(paths)
    if not validation['ok'] or any(pair not in original_crossings for pair in final_crossings):
        raise RuntimeError('refined frozen graph failed final geometric validation')
    report = dict(algorithm_version=ALGORITHM_VERSION, world_seed=int(seed),
                  seed_derivation='SHA256 via delta_network_site.derive_seed', subseeds=subseeds,
                  coordinate_system='local u,v metres; SiteSpec cell centres',
                  accepted_reaches=sum(item['accepted'] for item in results), total_reaches=len(paths),
                  protected_source_height_m=45.0, topology_unchanged=True, endpoints_unchanged=True,
                  lowland_target_elevation_m=10.0, lowland_excavation_ceiling_m=12.0,
                  lowland_repairs=sum(item['lowland_repair']['accepted'] for item in results),
                  remaining_lowland_blockers=[item['edge_id'] for item in results
                                              if item['lowland_repair']['after_center_surface_max_m'] > 12.0],
                  initial_crossing_pairs=original_crossings, final_crossing_pairs=final_crossings,
                  validation=validation, reaches=results,
                  limitations=['Frozen junction tangent portions cannot be rerouted.',
                               'Bounded local bends may retain inherited terrain conflicts; source terrain is unchanged.',
                               'Construction geometry experiment; no physical migration calibration.'])
    return refined, report
