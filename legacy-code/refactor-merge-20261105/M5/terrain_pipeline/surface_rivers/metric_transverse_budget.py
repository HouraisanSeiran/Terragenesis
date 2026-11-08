"""Necessary original-source cut bounds at local fan4 vertex locations."""

import numpy as np

from .metric_channel_geometry import _sample


def evaluate_necessary_budget(points, receiver, widths, profile, terrain, ids,
                              spacing, max_cut, bottom_slope, focus=None):
    hotspots = []
    bounds = necessary_bounds(points, receiver, widths, profile, terrain, ids,
                              spacing, max_cut, bottom_slope,
                              focus_nodes=focus, hotspot_records=hotspots)
    maxima, counts = [], []
    for category in ("physical_half_bottom", "bottom_guard_shell", "bank"):
        buckets = [bounds[kind][category] for kind in ("edge_strip", "node_cap")]
        maxima.append(max(bucket["maximum_required_cut_m"] for bucket in buckets))
        counts.append(sum(bucket["violations"] for bucket in buckets))
    return dict(maxima=maxima, counts=counts, hotspots=hotspots, bounds=bounds)


def budget_hotspot_targets(evaluation):
    targets = []
    for category in ("physical_half_bottom", "bottom_guard_shell", "bank"):
        hotspots = [hotspot for hotspot in evaluation["hotspots"] if hotspot["category"] == category]
        if not hotspots:
            continue
        worst = max(hotspots, key=lambda hotspot: hotspot["maximum_required_cut_m"])
        nodes = [worst["node_index"]] if "node_index" in worst else [
            worst["source_node_index"], worst["target_node_index"]]
        for node in nodes:
            if node not in targets:
                targets.append(node)
    return targets


def controlling_upstream_nodes(points, receiver, depths, profile, target_nodes, minimum_slope):
    """Find edge endpoints controlling the highest bed at the supplied nodes."""
    donors = [[] for _ in points]
    for source, target in enumerate(receiver):
        if target >= 0:
            donors[target].append(source)
    edge_order = {int(source): edge for edge, source in enumerate(np.flatnonzero(receiver >= 0))}
    result = []
    for node in target_nodes:
        distance = {node: 0.}
        pending = [node]
        for downstream in pending:
            for upstream in donors[downstream]:
                distance[upstream] = distance[downstream] + float(np.linalg.norm(points[upstream] - points[downstream]))
                pending.append(upstream)
        best = None
        for source in pending:
            if source not in edge_order:
                continue
            target = int(receiver[source])
            if target not in distance:
                continue
            edge = edge_order[source]
            start, end = profile[0][edge:edge + 2]
            knot_t = profile[1][start:end]
            source_height = profile[2][start:end]
            design_depth = (1. - knot_t) * depths[source] + knot_t * depths[target]
            remaining = distance[target] + (1. - knot_t) * np.linalg.norm(points[target] - points[source])
            upper = source_height - design_depth - minimum_slope * remaining
            knot = int(np.argmin(upper))
            if best is None or upper[knot] < best[0]:
                best = (float(upper[knot]), source, target, float(knot_t[knot]))
        if best is not None:
            _, source, target, knot_t = best
            for endpoint in ([source, target] if knot_t <= .5 else [target, source]):
                if endpoint not in result:
                    result.append(endpoint)
    return result


def local_vertices(low, high, terrain, spacing):
    origin = np.array([terrain.x0_m, terrain.z0_m])
    domain_high = origin + np.array([(terrain.elevation_m.shape[1] - 1) * terrain.dx_m,
                                     (terrain.elevation_m.shape[0] - 1) * terrain.dz_m])
    first = np.floor((np.maximum(low, origin) - origin) / spacing).astype(int)
    last = np.ceil((np.minimum(high, domain_high) - origin) / spacing).astype(int)
    batches = []
    for offset in (0., .5):
        x = np.arange(first[0], last[0] + 1) + offset
        z = np.arange(first[1], last[1] + 1) + offset
        xx, zz = np.meshgrid(x, z)
        points = origin + np.column_stack((xx.ravel(), zz.ravel())) * spacing
        inside = np.all((points >= origin) & (points <= domain_high), axis=1)
        batches.append(points[inside])
    return np.concatenate(batches)


def necessary_bounds(points, receiver, widths, profile, terrain, ids, spacing=1., max_cut=4., bottom_slope=.02,
                     *, focus_nodes=None, hotspot_records=None):
    names = ("physical_half_bottom", "bottom_guard_shell", "bank")
    result = {kind: {name: dict(constraint_vertex_tests=0, violations=0, maximum_required_cut_m=0., worst=None)
                     for name in names} for kind in ("edge_strip", "node_cap")}
    edges = np.flatnonzero(receiver >= 0)
    incident = [[] for _ in points]
    incident_width = widths.copy()
    node_upper = np.full(len(points), np.inf)
    for edge, source in enumerate(edges):
        target = receiver[source]
        direction = points[target] - points[source]
        direction /= np.linalg.norm(direction)
        incident[source].append(direction)
        incident[target].append(-direction)
        width = max(widths[source], widths[target])
        incident_width[source] = max(incident_width[source], width)
        incident_width[target] = max(incident_width[target], width)
        start, end = profile[0][edge:edge + 2]
        node_upper[source] = min(node_upper[source], profile[3][start])
        node_upper[target] = min(node_upper[target], profile[3][end - 1])

    def record(kind, vertices, distances, upper, real_half, descriptor):
        heights = _sample(terrain.elevation_m, vertices, terrain)[0]
        guarded_half = real_half + np.sqrt(2.) * spacing
        rise = np.minimum(distances, guarded_half) * bottom_slope + np.maximum(0., distances - guarded_half) / 2.
        required = heights - upper - rise
        masks = (distances <= real_half,
                 (distances > real_half) & (distances <= guarded_half),
                 distances > guarded_half)
        for name, mask in zip(names, masks):
            values = required[mask]
            if not len(values):
                continue
            bucket = result[kind][name]
            bucket["constraint_vertex_tests"] += int(mask.sum())
            bucket["violations"] += int(np.count_nonzero(values > max_cut + 1e-8))
            worst_index = np.flatnonzero(mask)[np.argmax(values)]
            if hotspot_records is not None and values.max() > max_cut + 1e-8:
                hotspot_records.append(dict(descriptor, kind=kind, category=name,
                                            maximum_required_cut_m=float(values.max()),
                                            violating_tests=int(np.count_nonzero(values > max_cut + 1e-8))))
            if values.max() > bucket["maximum_required_cut_m"]:
                bucket["maximum_required_cut_m"] = float(values.max())
                bucket["worst"] = dict(descriptor, vertex_xz_m=vertices[worst_index].tolist(),
                                       lateral_distance_m=float(distances[worst_index]),
                                       physical_half_bottom_m=float(real_half),
                                       source_height_m=float(heights[worst_index]),
                                       highest_center_bed_m=float(np.broadcast_to(upper, heights.shape)[worst_index]),
                                       transverse_rise_m=float(rise[worst_index]),
                                       necessary_cut_m=float(required[worst_index]),
                                       excess_over_four_m=float(required[worst_index] - max_cut))

    for edge, source in enumerate(edges):
        target = receiver[source]
        if focus_nodes is not None and source not in focus_nodes and target not in focus_nodes:
            continue
        a, b = points[source], points[target]
        delta = b - a
        real_half = max(widths[source], widths[target]) / 2.
        radius = real_half + np.sqrt(2.) * spacing + 2. * max_cut
        vertices = local_vertices(np.minimum(a, b) - radius, np.maximum(a, b) + radius, terrain, spacing)
        t = (vertices - a) @ delta / (delta @ delta)
        distance = np.linalg.norm(vertices - (a + t[:, None] * delta), axis=1)
        selected = (t >= 0.) & (t <= 1.) & (distance > 1e-10) & (distance <= radius)
        vertices, t, distance = vertices[selected], t[selected], distance[selected]
        start, end = profile[0][edge:edge + 2]
        upper = np.interp(t, profile[1][start:end], profile[3][start:end])
        record("edge_strip", vertices, distance, upper, real_half,
               dict(edge_index=int(edge), source_node_index=int(source), target_node_index=int(target), source_node_cell_id=int(ids[source]),
                    target_node_cell_id=int(ids[target]), source_xz_m=a.tolist(), target_xz_m=b.tolist()))
    for node, directions in enumerate(incident):
        if not directions:
            continue
        if focus_nodes is not None and node not in focus_nodes:
            continue
        real_half = incident_width[node] / 2.
        radius = real_half + np.sqrt(2.) * spacing + 2. * max_cut
        vertices = local_vertices(points[node] - radius, points[node] + radius, terrain, spacing)
        displacement = vertices - points[node]
        distance = np.linalg.norm(displacement, axis=1)
        selected = (distance > 1e-10) & (distance <= radius)
        selected &= np.all(displacement @ np.asarray(directions).T <= 1e-10, axis=1)
        record("node_cap", vertices[selected], distance[selected], node_upper[node], real_half,
               dict(node_index=node, node_cell_id=int(ids[node]), node_xz_m=points[node].tolist(),
                    incident_edge_count=len(directions)))
    return result

