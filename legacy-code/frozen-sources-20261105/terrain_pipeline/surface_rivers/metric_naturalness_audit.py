"""Read-only geometry measurements; neither routes nor certifies natural channels."""

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity


QUANTILE_PROBS = (.05, .25, .5, .75, .95)


def channel_graph_observations(terrain, graph, upstream_area_m2, *, minimum_area_m2, curvature_method="legacy_acos"):
    """Measure only channel-support nodes above a frozen contributing-area cutoff."""
    area = np.asarray(upstream_area_m2, np.float64).ravel()
    if (area.shape != graph.receiver.shape or not np.isfinite(area).all()
            or not np.isfinite(minimum_area_m2) or minimum_area_m2 <= 0.):
        raise ValueError("finite grid areas and positive channel threshold required")
    selected = graph.valid_mask.ravel() & (area >= minimum_area_m2)
    ids = np.flatnonzero(selected)
    if ids.size < 2:
        return {"status": "insufficient_channel_support", "channel_node_count": int(ids.size)}
    index = np.full(area.size, -1, np.int64)
    index[ids] = np.arange(ids.size)
    receiver = graph.receiver[ids]
    if np.any((receiver >= 0) & ~selected[np.maximum(receiver, 0)]):
        raise ValueError("contributing area threshold unexpectedly disconnects downstream channel")
    targets = np.where(receiver >= 0, index[np.maximum(receiver, 0)], -1)
    points = np.array([terrain.world_xz(int(cell)) for cell in ids])
    result = geometry_metrics(points, terrain.elevation_m.ravel()[ids], targets,
        allowed_terminal=graph.outlet_kind[ids] != "interior", curvature_method=curvature_method)
    result["channel_support"] = {"minimum_upstream_area_m2": float(minimum_area_m2),
        "selected_node_count": int(ids.size), "selected_edge_count": int((targets >= 0).sum()),
        "area_m2": area[ids].tolist(), "source_cell_ids": ids.tolist(),
        "headwater_semantics": "threshold crossing; not observed perennial channel head",
        "terminal_semantics": "original declared unknown/open/lake terminal retained"}
    return result


def sample_summary(values):
    values = np.asarray(values, np.float64)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("finite one dimensional metric samples required")
    return {"count": int(values.size), "quantile_probs": list(QUANTILE_PROBS),
            "quantiles": np.quantile(values, QUANTILE_PROBS).tolist() if values.size else [],
            "samples": values.tolist()}


def geometry_metrics(node_xz_m, bed_m, receiver, *, width_m=None, depth_m=None,
                     allowed_terminal=None, tile_ids=None, curvature_method="legacy_acos"):
    """Measure represented edges and three-node turns in a saved receiver network."""
    points = np.asarray(node_xz_m, np.float64)
    if curvature_method not in ("legacy_acos", "atan2"):
        raise ValueError("unknown curvature method")
    bed = np.asarray(bed_m, np.float64)
    downstream = np.asarray(receiver)
    size = len(bed)
    if (points.shape != (size, 2) or bed.ndim != 1 or size == 0
            or downstream.shape != (size,) or downstream.dtype.kind not in "iu"
            or not np.isfinite(points).all() or not np.isfinite(bed).all()
            or np.any(downstream < -1) or np.any(downstream >= size)):
        raise ValueError("finite metric geometry and in-range integer receivers required")
    edges = np.flatnonzero(downstream >= 0)
    targets = downstream[edges]
    lengths = np.linalg.norm(points[targets] - points[edges], axis=1)
    if np.any(lengths <= 0.):
        raise ValueError("positive geometric receiver distance required")
    slopes = (bed[edges] - bed[targets]) / lengths
    donors = np.bincount(targets, minlength=size)
    # Kahn traversal audits topology; it does not compute or change routing.
    indegree = donors.copy()
    queue = list(np.flatnonzero(indegree == 0))
    processed = 0
    while queue:
        node = queue.pop()
        processed += 1
        target = downstream[node]
        if target >= 0:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))
    cycle_nodes = size - processed
    terminals = downstream < 0
    permitted = np.ones(size, bool) if allowed_terminal is None else np.asarray(allowed_terminal)
    if permitted.shape != (size,) or permitted.dtype != bool:
        raise ValueError("matching allowed-terminal boolean mask required")
    hanging = terminals & ~permitted
    curvature, slope_jumps = [], []
    edge_slope = np.zeros(size)
    edge_slope[edges] = slopes
    for node in edges:
        middle = downstream[node]
        last = downstream[middle]
        if last < 0:
            continue
        first_vector = points[middle] - points[node]
        second_vector = points[last] - points[middle]
        first_length = np.linalg.norm(first_vector)
        second_length = np.linalg.norm(second_vector)
        dot = np.dot(first_vector, second_vector)
        if curvature_method == "atan2":
            cross = first_vector[0] * second_vector[1] - first_vector[1] * second_vector[0]
            angle = np.arctan2(abs(cross), dot)
        else:
            angle = np.arccos(np.clip(dot / (first_length * second_length), -1., 1.))
        curvature.append(float(angle / (.5 * (first_length + second_length))))
        slope_jumps.append(float(edge_slope[node] - edge_slope[middle]))
    cross_tile = 0
    cross_tile_joins = 0
    if tile_ids is not None:
        tiles = np.asarray(tile_ids)
        if tiles.shape != (size,):
            raise ValueError("matching tile identity array required")
        crossing = edges[tiles[edges] != tiles[targets]]
        cross_tile = len(crossing)
        cross_tile_joins = int(np.count_nonzero(donors[downstream[crossing]] >= 2))
    metrics = {"longitudinal_slope": sample_summary(slopes),
               "curvature_rad_per_m": sample_summary(curvature),
               "signed_slope_jump_knickpoint_candidate": sample_summary(slope_jumps),
               "topology": {"node_count": size, "edge_count": int(edges.size),
                            "terminal_count": int(terminals.sum()), "source_count": int((donors == 0).sum()),
                            "confluence_count": int((donors >= 2).sum()),
                            "cycle_or_cycle_dependent_node_count": cycle_nodes,
                            "unexplained_hanging_terminal_count": int(hanging.sum()),
                            "uphill_edge_count": int((slopes < -1e-12).sum()),
                            "cross_tile_edge_count": cross_tile,
                            "cross_tile_confluence_edge_count": cross_tile_joins},
               "knickpoint_semantics": "signed adjacent slope changes; candidates without lithology or history attribution",
               "curvature_method": curvature_method,
               "status": "diagnostic_geometry_observation"}
    if (width_m is None) != (depth_m is None):
        raise ValueError("width and depth must be supplied together")
    if width_m is not None:
        width, depth = np.asarray(width_m, np.float64), np.asarray(depth_m, np.float64)
        if (width.shape != (size,) or depth.shape != (size,) or not np.isfinite(width).all()
                or not np.isfinite(depth).all() or np.any(width <= 0.) or np.any(depth <= 0.)):
            raise ValueError("positive finite node width and depth required")
        metrics["width_depth_ratio"] = sample_summary(width / depth)
    else:
        metrics["width_depth_ratio"] = {"status": "unavailable_no_channel_cross_section"}
    metrics["checks"] = {"acyclic": cycle_nodes == 0, "no_unexplained_hanging_end": not hanging.any(),
                         "downhill_or_flat": not np.any(slopes < -1e-12)}
    return metrics


def compare_frozen_samples(observed, reference, *, conditions_match):
    """Report frozen empirical intervals, including explicit outliers and mismatch."""
    if reference.get("schema") != "metric-naturalness-frozen-reference-v1":
        raise ValueError("frozen reference schema required")
    outputs = {}
    for name, frozen in reference["metrics"].items():
        interval = np.asarray(frozen["review_interval"], np.float64)
        tolerance = frozen["absolute_tolerance"]
        if (interval.shape != (2,) or not np.isfinite(interval).all() or interval[0] > interval[1]
                or not isinstance(tolerance, (int, float)) or not np.isfinite(tolerance) or tolerance < 0.):
            raise ValueError("finite ordered reference interval and nonnegative tolerance required")
        if name not in observed or "samples" not in observed[name]:
            outputs[name] = {"status": "unavailable_observation"}
            continue
        samples = np.asarray(observed[name]["samples"], np.float64)
        if samples.ndim != 1 or not np.isfinite(samples).all():
            raise ValueError("finite one dimensional observed samples required")
        lower, upper = interval
        outside = (samples < lower - tolerance) | (samples > upper + tolerance)
        outputs[name] = {"status": "comparable" if conditions_match else "condition_mismatch_context_only",
                         "review_interval": [lower, upper], "absolute_tolerance": tolerance,
                         "sample_count": int(samples.size), "outside_count": int(outside.sum()),
                         "outside_fraction": float(outside.mean()) if samples.size else None,
                         "outside_samples": samples[outside].tolist(),
                         "all_samples_inside": bool(samples.size and not outside.any())}
    return {"reference_identity_sha256": identity({}, reference), "comparisons": outputs,
            "natural_certification": False}
