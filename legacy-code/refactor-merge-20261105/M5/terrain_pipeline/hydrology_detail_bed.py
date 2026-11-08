"""Reuse the established continuous design bed on a finite genuine TD component."""

import hashlib

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_design_bed import (build_design_geometry, _mesh_volume_chunked,
    continuous_center_floor_constraints, interior_support_boundary_vertices)
from terrain_pipeline.surface_rivers.metric_channel_geometry import _sample
from terrain_pipeline.surface_rivers.metric_valley_union import _mesh_height


def frozen_shared_sections(detail, specification, *, piece_indices=None, complete_adjacent_pieces=False):
    """Return identical section records to every piece sharing a subdivision node."""
    pieces = split_frozen_window_component(specification)
    sections = [[] for _ in pieces]
    occurrences = {}
    for index, piece in enumerate(pieces):
        for local, parent in enumerate(piece["parent_node_ids"]):
            occurrences.setdefault(parent, []).append((index, local))
    for parent in sorted(occurrences):
        shared = occurrences[parent]
        if len(shared) < 2:
            continue
        if piece_indices is not None and not any(index in piece_indices for index, _ in shared):
            continue
        index, local = shared[0]
        piece = pieces[index]
        point = np.asarray(piece["points_xz_m"][local])
        receiver = np.asarray(piece["receiver"])
        neighbors = np.flatnonzero(receiver == local).tolist()
        if receiver[local] >= 0:
            neighbors.append(int(receiver[local]))
        vector = np.asarray(piece["points_xz_m"][neighbors[0]]) - point
        normal = np.array([-vector[1], vector[0]]) / np.linalg.norm(vector)
        if normal[0] < 0 or (normal[0] == 0 and normal[1] < 0):
            normal = -normal
        section = solved_shared_section(detail, specification, parent, normal,
            complete_adjacent_pieces=complete_adjacent_pieces)
        section["parent_node_id"] = int(parent)
        for index, _ in shared:
            sections[index].append(section)
    return sections


def solved_shared_section(detail, specification, node, normal, *, complete_adjacent_pieces=False):
    """Freeze a feasible trace from a deterministic bounded two-sided seam solve."""
    from terrain_pipeline.surface_rivers.metric_monotone_union import _line_constraints
    meta = detail["metadata"]
    height = detail["arrays"]["derived_height_m"]
    terrain = TerrainGrid(height, np.ones(height.shape, bool), *meta["origin_xz_m"],
                          meta["spacing_m"], meta["spacing_m"], "conditioned_terrain", "seam-local", meta["identity"])
    points = np.asarray(specification["points_xz_m"], float)
    receivers = np.asarray(specification["receiver"], int)
    upstream = np.flatnonzero(receivers == node)
    if len(upstream) != 1 or receivers[node] < 0:
        raise ValueError("bounded shared section requires one upstream and downstream edge")
    first, last = int(upstream[0]), int(receivers[node])
    edge_indices = {int(parent): index for index, parent in enumerate(np.flatnonzero(receivers >= 0))}
    frozen = specification["centerline_profile"]
    local_points, local_width, local_bed = [], [], []
    profile = [ [0], [], [], [] ]
    extents = []
    for ordinal, (a, b) in enumerate(((first, node), (node, last))):
        length = np.linalg.norm(points[b] - points[a])
        if complete_adjacent_pieces and (length <= 0 or length > 500. + 1e-8):
            raise ValueError("complete adjacent shared section requires each parent piece within 500m")
        extent = length if complete_adjacent_pieces else min(30., length)
        lo, hi = ((1. - extent / length, 1.) if ordinal == 0 else (0., extent / length))
        start, end = frozen["offsets"][edge_indices[a]:edge_indices[a] + 2]
        times = np.asarray(frozen["t"][start:end])
        samples = np.r_[lo, times[(times > lo) & (times < hi)], hi]
        coords = points[a] + samples[:, None] * (points[b] - points[a])
        beds = np.interp(samples, times, frozen["bed_m"][start:end])
        source, _ = _sample(height, coords, terrain)
        profile[1].extend(((samples-lo)/(hi-lo)).tolist())
        profile[2].extend(source.tolist())
        profile[3].extend(beds.tolist())
        profile[0].append(len(profile[1]))
        widths = np.interp([lo, hi], [0., 1.], np.asarray(specification["width_m"])[[a, b]])
        if ordinal == 0:
            local_points.append(coords[0])
            local_width.append(widths[0])
            local_bed.append(beds[0])
        local_points.append(coords[-1])
        local_width.append(widths[-1])
        local_bed.append(beds[-1])
        extents.append(float(extent))
    local_points = np.asarray(local_points)
    local_bed = np.asarray(local_bed)
    parent_source, _ = _sample(height, points[[first, node, last]], terrain)
    parent_bed = np.asarray(specification["bed_target_m"])[[first, node, last]]
    # Full pieces use the maximum endpoint depth for every bottom triangle.
    # The bounded witness must not weaken that bound at the frozen trace.
    inherited_depth = float(np.max(np.minimum(.5, parent_source-parent_bed)))
    mesh = build_design_geometry(local_points, np.array([1, 2, -1]), np.asarray(local_width),
        np.full(3, inherited_depth), tuple(np.asarray(value) for value in profile), terrain, 1., 4., 1e-5,
        center_lowest=True, continuous_center_lowest=True)
    cells, vertices, triangles, original, _, cut = mesh[:6]
    audit = _audit_mesh(cells, vertices, triangles, original, cut, local_points, np.array([1, 2, -1]),
                        np.asarray(local_width), terrain, 1., center_lowest=True, continuous_center_lowest=True)
    if not audit["accepted"]:
        raise ValueError("bounded shared-section source mesh failed independent geometry audit")
    half = specification["width_m"][node] / 2.
    radius = half + np.sqrt(2.) + 1. + 8.
    ends = points[node] + np.array([-radius, radius])[:, None] * normal
    segments = _line_constraints(ends, np.array([1, -1]), cells, vertices, triangles, terrain, 1.)
    values = []
    for start, end, _, _, _ in segments:
        for ids, weights in (start, end):
            values.append((float((weights @ vertices[ids]-points[node]) @ normal),
                           float(weights @ original[ids]), float(weights @ (original-cut)[ids])))
    values.sort()
    unique = []
    for value in values:
        if not unique or value[0]-unique[-1][0] > 1e-8:
            unique.append(value)
    offsets, original_trace, bed = np.asarray(unique).T
    design_cap = float(specification["bed_target_m"][node])
    center = float(np.interp(0., offsets, bed))
    if center > design_cap + 1e-8:
        raise ValueError("bounded shared section exceeds frozen design ceiling")
    algorithm = ("bounded-complete-adjacent-feasible-fan4-section-v3" if complete_adjacent_pieces
                 else "bounded-two-sided-30m-feasible-fan4-section-v2")
    return {"algorithm": algorithm, "parent_detail_identity": meta["identity"],
        "fine_spacing_m": 1., "position_xz_m": points[node].tolist(), "normal_xz": np.asarray(normal).tolist(),
        "half_width_m": float(half), "center_bed_m": center, "design_center_ceiling_m": design_cap,
        "realized_center_below_design_ceiling_m": design_cap-center, "radius_m": float(radius),
        "offsets_m": offsets.tolist(), "source_elevation_m": original_trace.tolist(), "bed_elevation_m": bed.tolist(),
        "maximum_cut_m": float(np.max(original_trace-bed)), "longitudinal_support_m": extents,
        "longitudinal_support_scope": ("two complete adjacent parent pieces, each at most 500m"
                                       if complete_adjacent_pieces else "two independently clipped 30m parent portions"),
        "inherited_parent_bottom_design_depth_m": inherited_depth,
        "minimum_cut_provenance": "maximum endpoint design depth from both adjacent complete parent pieces, capped at 0.5m; original-source interpolation padding retained",
        "source_mesh_geometry_audit": audit, "local_solve_closure": mesh[6],
        "local_mesh_witness": {"cells": cells.tolist(), "vertices_xz_m": vertices.tolist(),
            "triangles": triangles.tolist(), "original_macro_bed_m": original.tolist(), "local_cut_m": cut.tolist(),
            "node_xz_m": local_points.tolist(), "receiver": [1, 2, -1], "width_m": list(map(float, local_width))},
        "trace_contract": "actual independently audited local LP bed at every global fan4 triangle crossing"}


def frozen_window_profiles(plan, height_m, origin_xz_m, spacing_m, *, sample_spacing_m=1.0,
                           clip_origin_xz_m=None, clip_shape=None, source_edges=None, frozen_paths=None):
    """Exact frozen-edge/window intersections and one shared terrain-following bed.

    Window boundaries are computational clips, never hydrological outlets.
    A profile is defined over this immutable source before any mesh subdivision.
    """
    if frozen_paths is not None:
        from terrain_pipeline.frozen_terrain_centerline import frozen_path_profiles
        if source_edges is not None and {tuple(path["metadata"]["source_edge"]) for path in frozen_paths} != set(map(tuple, source_edges)):
            raise ValueError("frozen path set differs from requested source edges")
        return frozen_path_profiles(plan, frozen_paths, height_m, origin_xz_m, spacing_m,
            sample_spacing_m=sample_spacing_m, clip_origin_xz_m=clip_origin_xz_m, clip_shape=clip_shape)
    height = np.asarray(height_m, dtype=float)
    origin = np.asarray(origin_xz_m, dtype=float)
    maximum = origin + (np.array(height.shape)[::-1] - 1) * spacing_m
    terrain = TerrainGrid(height, np.ones(height.shape, bool), *origin, spacing_m, spacing_m,
                          "conditioned_terrain", "frozen-window-profile", hashlib.sha256(height.tobytes()).hexdigest())
    if clip_origin_xz_m is not None:
        clip_origin = np.asarray(clip_origin_xz_m, dtype=float)
        clip_maximum = clip_origin + (np.array(clip_shape)[::-1] - 1) * spacing_m
        if np.any(clip_origin < origin) or np.any(clip_maximum > maximum):
            raise ValueError("declared frozen profile window leaves genuine source support")
        origin, maximum = clip_origin, clip_maximum
    columns = np.asarray(plan["height_m"]).shape[1]
    receivers = np.asarray(plan["receiver"]).ravel()
    river = np.asarray(plan.get("river_mask", np.zeros_like(plan["height_m"], bool))).ravel()
    profiles = []
    edges = ([(int(first), int(receivers[first])) for first in np.flatnonzero(river & (receivers >= 0))]
             if source_edges is None else source_edges)
    for first, second in edges:
        if not 0 <= first < receivers.size or not 0 <= second < receivers.size or receivers[first] != second:
            raise ValueError("profile line is not an actual frozen receiver edge")
        start = np.asarray(plan["origin_xz_m"]) + np.array([first % columns, first // columns]) * plan["spacing_m"]
        finish = np.asarray(plan["origin_xz_m"]) + np.array([second % columns, second // columns]) * plan["spacing_m"]
        vector = finish - start
        lo, hi = 0.0, 1.0
        for axis in range(2):
            if vector[axis] == 0:
                if not origin[axis] <= start[axis] <= maximum[axis]:
                    hi = -1.0
                    break
            else:
                limits = sorted(((origin[axis] - start[axis]) / vector[axis], (maximum[axis] - start[axis]) / vector[axis]))
                lo, hi = max(lo, limits[0]), min(hi, limits[1])
        if hi <= lo:
            continue
        length = np.linalg.norm(vector) * (hi - lo)
        fractions = np.linspace(lo, hi, int(np.ceil(length / sample_spacing_m)) + 1)
        points = np.clip(start + fractions[:, None] * vector, origin, maximum)
        source, _ = _sample(height, points, terrain)
        distance = (fractions - lo) * np.linalg.norm(vector)
        bed = np.minimum.accumulate(source + 0.001 * distance) - 0.001 * distance - 0.5
        profiles.append({"source_edge": [int(first), second], "fractions": fractions,
                         "points_xz_m": points, "source_m": source, "bed_m": bed,
                         "length_m": float(length), "full_coarse_edge_length_m": float(np.linalg.norm(vector))})
    node_beds = {}
    for profile in profiles:
        for endpoint, fraction in ((0, 0), (-1, 1)):
            if profile["fractions"][endpoint] == fraction:
                node = profile["source_edge"][fraction]
                node_beds[node] = min(node_beds.get(node, np.inf), profile["bed_m"][endpoint])
    for profile in profiles:
        for endpoint, fraction in ((0, 0), (-1, 1)):
            if profile["fractions"][endpoint] == fraction:
                profile["bed_m"][endpoint] = node_beds[profile["source_edge"][fraction]]
    # Match real shared frozen nodes before splitting meshes. Upstream edge
    # constraints propagate through the finite DAG; no segment resets its bed.
    pending = list(range(len(profiles)))
    while pending:
        ready = [index for index in pending if not any(
            profiles[upstream]["source_edge"][1] == profiles[index]["source_edge"][0]
            and profiles[upstream]["fractions"][-1] == 1 and profiles[index]["fractions"][0] == 0
            for upstream in pending)]
        if not ready:
            raise ValueError("frozen window river profile contains a cycle")
        for index in ready:
            profile = profiles[index]
            upstream_profiles = [other for other in profiles
                if other["source_edge"][1] == profile["source_edge"][0]
                and other["fractions"][-1] == 1 and profile["fractions"][0] == 0]
            if upstream_profiles:
                shared_bed = min([profile["bed_m"][0]] + [other["bed_m"][-1] for other in upstream_profiles])
                for other in upstream_profiles:
                    other["bed_m"][-1] = shared_bed
                distance = (profile["fractions"] - profile["fractions"][0]) * profile["full_coarse_edge_length_m"]
                profile["bed_m"] = np.minimum(profile["bed_m"], shared_bed - 0.001 * distance)
            pending.remove(index)
    return profiles


def select_frozen_window_component(plan, detail, window, *, width_m=8.0, maximum_segment_length_m=500.0,
                                   tributary_declaration=None, highest_lake_level_m=None, lake_mask=None,
                                   junction_length_m=120.0):
    """Request the entire represented window intersection of a selected edge.

    The profile is computed once before subdivisions, whose shared endpoints
    therefore have identical beds. Full coarse-edge coverage is reported.
    """
    if window["kind"] not in ("river", "mouth", "confluence") or not 4 <= width_m <= 64:
        raise ValueError("full-window selection requires a frozen river component, width 4..64m")
    if not 30 <= maximum_segment_length_m <= 1000:
        raise ValueError("bounded full-window segment length 30..1000m required")
    if window["kind"] == "confluence":
        return _select_frozen_window_confluence(plan, detail, window, width_m=width_m,
            maximum_segment_length_m=maximum_segment_length_m, junction_length_m=junction_length_m,
            tributary_declaration=tributary_declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    meta = detail["metadata"]
    profiles = frozen_window_profiles(plan, detail["arrays"]["derived_height_m"], meta["origin_xz_m"], meta["spacing_m"],
        clip_origin_xz_m=window.get("origin_xz_m"), clip_shape=window.get("shape"))
    edge = list(window["selection_edge_cell_ids"])
    profile = next((profile for profile in profiles if profile["source_edge"] == edge), None)
    if profile is None:
        raise ValueError("selected frozen edge does not intersect represented window")
    segment_count = int(np.ceil(profile["length_m"] / maximum_segment_length_m))
    if segment_count + 1 > 16:
        raise ValueError("full-window request exceeds bounded 16-node component")
    fractions = np.linspace(profile["fractions"][0], profile["fractions"][-1], segment_count + 1)
    points = np.column_stack([np.interp(fractions, profile["fractions"], profile["points_xz_m"][:, axis]) for axis in range(2)])
    target = np.interp(fractions, profile["fractions"], profile["bed_m"])
    offsets, parameters, sources, beds = [0], [], [], []
    height = detail["arrays"]["derived_height_m"]
    terrain = TerrainGrid(height, np.ones(height.shape, bool), *meta["origin_xz_m"], meta["spacing_m"], meta["spacing_m"],
                          "conditioned_terrain", "full-window-component", meta["identity"])
    for lo, hi in zip(fractions[:-1], fractions[1:]):
        knots = np.r_[lo, profile["fractions"][(profile["fractions"] > lo) & (profile["fractions"] < hi)], hi]
        parameters.extend((knots - lo) / (hi - lo))
        sample_points = np.column_stack([np.interp(knots, profile["fractions"], profile["points_xz_m"][:, axis]) for axis in range(2)])
        sampled_source, _ = _sample(height, sample_points, terrain)
        sources.extend(sampled_source)
        beds.extend(np.interp(knots, profile["fractions"], profile["bed_m"]))
        offsets.append(len(parameters))
    return {"points_xz_m": points.tolist(), "receiver": list(range(1, segment_count + 1)) + [-1],
            "width_m": [width_m] * len(points), "bed_target_m": target.tolist(), "fine_spacing_m": 1.0,
            "node_source_edges": [edge] * len(points), "node_edge_fractions": fractions.tolist(),
            "centerline_profile": {"offsets": offsets, "t": list(parameters), "source_m": list(sources), "bed_m": list(beds),
                                   "parent_detail_identity": meta["identity"]},
            "selection_semantics": "exact complete frozen-edge/window intersection; shared terrain-following profile before mesh subdivision",
            "coverage": {"scope": "entire represented window intersection, not entire frozen coarse edge",
                         "profile_semantics": "local_clipped_component; shared frozen profile within this declared window only",
                         "represented_length_m": profile["length_m"], "full_coarse_edge_length_m": profile["full_coarse_edge_length_m"],
                         "edge_fraction_interval": fractions[[0, -1]].tolist(),
                         "entire_coarse_edge_covered": bool(fractions[0] == 0 and fractions[-1] == 1),
                         "boundary_policy": "computational clip; finite-width mesh may require genuine source halo"}}


def _select_frozen_window_confluence(plan, detail, window, *, width_m, maximum_segment_length_m,
                                     junction_length_m, tributary_declaration, highest_lake_level_m, lake_mask):
    if tributary_declaration is None or not 30 <= junction_length_m <= min(500, maximum_segment_length_m):
        raise ValueError("full-window confluence needs an explicit sidecar and bounded shared junction arms")
    from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
    source_edges = [record["source_edge"] for record in tributary_declaration["edges"]]
    validation = validate_local_tributary_source_edges(plan, tributary_declaration, source_edges,
        highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    junction = tributary_declaration["junction_id"]
    if window["coarse_cell"] != junction or window.get("declared_source_edge_cell_ids") != source_edges:
        raise ValueError("full-window confluence differs from its frozen three-edge declaration")
    meta, height = detail["metadata"], detail["arrays"]["derived_height_m"]
    profiles = frozen_window_profiles(plan, height, meta["origin_xz_m"], meta["spacing_m"],
        clip_origin_xz_m=window.get("origin_xz_m"), clip_shape=window.get("shape"), source_edges=source_edges)
    by_edge = {tuple(profile["source_edge"]): profile for profile in profiles}
    if len(by_edge) != 3:
        raise ValueError("full-window source does not represent all three declared confluence edges")
    outgoing = by_edge[tuple(source_edges[2])]
    if outgoing["fractions"][0] != 0:
        raise ValueError("declared confluence junction is outside its full-window source")
    points = [outgoing["points_xz_m"][0]]
    targets = [outgoing["bed_m"][0]]
    edges, fractions, receivers = [source_edges[2]], [0.0], [-1]
    segment_profiles = {}
    coverage = []
    for edge in source_edges:
        profile = by_edge[tuple(edge)]
        incoming = edge[1] == junction
        lo, hi = profile["fractions"][[0, -1]]
        if incoming and hi != 1:
            raise ValueError("incoming sidecar branch does not reach the shared junction")
        count = int(np.ceil(profile["length_m"] / maximum_segment_length_m))
        cut = (1 - junction_length_m / profile["full_coarse_edge_length_m"] if incoming
               else junction_length_m / profile["full_coarse_edge_length_m"])
        knots = np.unique(np.r_[np.linspace(lo, hi, count + 1), np.clip(cut, lo, hi)])
        ids = []
        for fraction in knots:
            if (incoming and fraction == 1) or (not incoming and fraction == 0):
                ids.append(0)
                continue
            ids.append(len(points))
            points.append(np.array([np.interp(fraction, profile["fractions"], profile["points_xz_m"][:, axis]) for axis in range(2)]))
            targets.append(float(np.interp(fraction, profile["fractions"], profile["bed_m"])))
            edges.append(edge)
            fractions.append(float(fraction))
            receivers.append(-1)
        for index, (first, second) in enumerate(zip(ids[:-1], ids[1:])):
            receivers[first] = second
            segment_profiles[first] = (profile, knots[index], knots[index + 1])
        coverage.append({"source_edge": edge, "edge_fraction_interval": [float(lo), float(hi)],
                         "represented_length_m": profile["length_m"], "full_coarse_edge_length_m": profile["full_coarse_edge_length_m"],
                         "entire_coarse_edge_covered": bool(lo == 0 and hi == 1)})
    if len(points) > 16:
        raise ValueError("full-window confluence exceeds bounded 16-node component")
    terrain = TerrainGrid(height, np.ones(height.shape, bool), *meta["origin_xz_m"], meta["spacing_m"], meta["spacing_m"],
                          "conditioned_terrain", "full-window-confluence", meta["identity"])
    offsets, parameters, sources, beds = [0], [], [], []
    for node in np.flatnonzero(np.asarray(receivers) >= 0):
        profile, lo, hi = segment_profiles[int(node)]
        knots = np.r_[lo, profile["fractions"][(profile["fractions"] > lo) & (profile["fractions"] < hi)], hi]
        parameters.extend((knots - lo) / (hi - lo))
        sample_points = np.column_stack([np.interp(knots, profile["fractions"], profile["points_xz_m"][:, axis]) for axis in range(2)])
        source, _ = _sample(height, sample_points, terrain)
        sources.extend(source)
        beds.extend(np.interp(knots, profile["fractions"], profile["bed_m"]))
        offsets.append(len(parameters))
    return {"points_xz_m": np.asarray(points).tolist(), "receiver": receivers, "width_m": [width_m] * len(points),
            "bed_target_m": targets, "node_source_edges": edges, "node_edge_fractions": fractions, "fine_spacing_m": 1.0,
            "centerline_profile": {"offsets": offsets, "t": list(parameters), "source_m": list(sources), "bed_m": list(beds),
                                   "parent_detail_identity": meta["identity"]},
            "junction_node_index": 0, "junction_length_m": junction_length_m,
            "local_tributary_sidecar_validation": validation,
            "selection_semantics": "complete declared two-in/one-out receiver graph/window intersections; one shared junction bed before subdivision",
            "coverage": {"scope": "all three local tributary edge/window intersections; not entire coarse edges",
                         "profile_semantics": "local_clipped_component; shared three-edge DAG profile within declared source",
                         "source_edges": coverage, "represented_length_m": sum(record["represented_length_m"] for record in coverage),
                         "entire_coarse_edge_covered": all(record["entire_coarse_edge_covered"] for record in coverage),
                         "boundary_policy": "computational clips; genuine source halo required for finite-width support"}}


def select_frozen_component(plan, detail, window, *, length_m=120.0, width_m=8.0,
                            tributary_declaration=None, highest_lake_level_m=None, lake_mask=None):
    """Prepare an inspectable finite piece of actual frozen river edges.

    This selects coordinates and fixed bed targets only. The continuous solver
    and independent represented-bed audit still decide success or refusal.
    """
    if window["kind"] not in ("river", "confluence", "mouth"):
        raise ValueError("fine component selection supports ordinary, confluence and mouth reaches")
    if not 30 <= length_m <= 500 or not 4 <= width_m <= 64:
        raise ValueError("finite selection length 30..500m and width 4..64m required")
    columns = plan["height_m"].shape[1]
    frozen_receiver = plan["receiver"].ravel()
    river = plan["river_mask"].ravel()
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
        sidecar_edges = [record["source_edge"] for record in tributary_declaration["edges"]]
        validate_local_tributary_source_edges(plan, tributary_declaration, sidecar_edges,
            highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
        river = river.copy()
        river[np.asarray(sidecar_edges)[:, 0]] = True
    owner = plan["owner_domain_id"].ravel()
    coarse_origin = np.asarray(plan["origin_xz_m"])
    coarse_spacing = plan["spacing_m"]

    def point(edge, fraction):
        first, second = edge
        start = coarse_origin + np.array([first % columns, first // columns]) * coarse_spacing
        finish = coarse_origin + np.array([second % columns, second // columns]) * coarse_spacing
        return start + fraction * (finish - start)

    points, edges, fractions, receivers = [], [], [], []
    if window["kind"] == "confluence":
        junction = window["coarse_cell"]
        downstream = int(frozen_receiver[junction])
        incoming = np.flatnonzero(river & (frozen_receiver == junction) & (owner == owner[junction]))
        if len(incoming) < 2 or downstream < 0:
            raise ValueError("selected confluence lacks two genuine incoming and one outgoing frozen edges")
        out_edge = [junction, downstream]
        points.append(point(out_edge, 0.0))
        edges.append(out_edge)
        fractions.append(0.0)
        receivers.append(1)
        fraction = min(1.0, length_m / np.linalg.norm(point(out_edge, 1) - point(out_edge, 0)))
        points.append(point(out_edge, fraction))
        edges.append(out_edge)
        fractions.append(fraction)
        receivers.append(-1)
        for upstream in incoming[:3]:
            edge = [int(upstream), junction]
            fraction = max(0.0, 1 - length_m / np.linalg.norm(point(edge, 1) - point(edge, 0)))
            points.append(point(edge, fraction))
            edges.append(edge)
            fractions.append(fraction)
            receivers.append(0)
    else:
        edge = window["selection_edge_cell_ids"]
        vector_length = np.linalg.norm(point(edge, 1) - point(edge, 0))
        if window["kind"] == "mouth":
            heights = plan["height_m"].ravel()[edge]
            middle = float(-heights[0] / (heights[1] - heights[0]))
        else:
            middle = 0.5
        half = length_m / (2 * vector_length)
        for fraction in (max(0.0, middle - half), min(1.0, middle + half)):
            points.append(point(edge, fraction))
            edges.append(edge)
            fractions.append(fraction)
        receivers = [1, -1]
    points = np.asarray(points)
    metadata = detail["metadata"]
    terrain = TerrainGrid(detail["arrays"]["derived_height_m"], np.ones(detail["arrays"]["derived_height_m"].shape, bool),
        *metadata["origin_xz_m"], metadata["spacing_m"], metadata["spacing_m"], "conditioned_terrain", "component-request", metadata["identity"])
    source, _ = _sample(terrain.elevation_m, points, terrain)
    target = source - 0.5
    # Propagate the declared finite gravity grade through the clipped DAG.
    # The independent solver still rejects any resulting cut beyond 4m.
    pending = set(range(len(points)))
    while pending:
        ready = [node for node in pending if not any(receivers[upstream] == node for upstream in pending)]
        if not ready:
            raise ValueError("selected finite river component contains a cycle")
        for node in ready:
            downstream = receivers[node]
            if downstream >= 0:
                length = np.linalg.norm(points[downstream] - points[node])
                target[downstream] = min(target[downstream], target[node] - 0.001 * length)
            pending.remove(node)
    return {"points_xz_m": points.tolist(), "receiver": receivers, "width_m": [width_m] * len(points),
            "bed_target_m": target.tolist(), "fine_spacing_m": 1.0,
            "node_source_edges": edges, "node_edge_fractions": fractions,
            "selection_semantics": "exact frozen graph clipping; 0.5m initial depth and globally declared 0.001 downhill grade; no hydraulic certification"}


def split_frozen_window_component(specification):
    """Bound solver memory by reusing, rather than resetting, the full profile."""
    profile = specification["centerline_profile"]
    receivers = np.asarray(specification["receiver"])
    edge_nodes = np.flatnonzero(receivers >= 0).tolist()
    edge_index = {node: index for index, node in enumerate(edge_nodes)}
    groups = []
    junction = specification.get("junction_node_index")
    if junction is not None:
        central = [node for node in edge_nodes if node == junction or receivers[node] == junction]
        if len(central) != 3:
            raise ValueError("shared confluence component needs the complete two-in/one-out junction")
        groups.append(central)
    groups.extend([[node] for node in edge_nodes if not groups or node not in groups[0]])
    if specification.get("joint_component_solve", False):
        indegree = np.bincount(receivers[receivers >= 0], minlength=len(receivers))
        retained = [node for node in range(len(receivers)) if indegree[node] != 1 or receivers[node] < 0]
        remap = {node: index for index, node in enumerate(retained)}
        piece = {key: [specification[key][node] for node in retained] for key in
                 ("points_xz_m", "width_m", "bed_target_m", "node_source_edges", "node_edge_fractions")}
        joint_profile = {"offsets": [0], "parent_detail_identity": profile["parent_detail_identity"], "t": [], "source_m": [], "bed_m": []}
        joint_receiver = []
        positions = np.asarray(specification["points_xz_m"])
        for node in retained:
            if receivers[node] < 0:
                joint_receiver.append(-1)
                continue
            chain, current = [], node
            while True:
                chain.append(current)
                current = int(receivers[current])
                if current in remap:
                    break
            vector = positions[current] - positions[node]
            length = np.linalg.norm(vector)
            for ordinal, first in enumerate(chain):
                second = int(receivers[first])
                lo, hi = profile["offsets"][edge_index[first]:edge_index[first] + 2]
                local_t = np.asarray(profile["t"][lo:hi])
                coords = positions[first] + local_t[:, None] * (positions[second] - positions[first])
                offsets = coords - positions[node]
                transverse = (vector[0] * offsets[:, 1] - vector[1] * offsets[:, 0]) / length
                if np.max(np.abs(transverse)) > 1e-7:
                    raise ValueError("joint bounded component requires collinear subdivisions per arm")
                use = slice(1, None) if ordinal else slice(None)
                mapped = np.clip(((coords - positions[node]) @ vector) / length ** 2, 0., 1.)
                if ordinal == 0:
                    mapped[0] = 0.
                if ordinal == len(chain) - 1:
                    mapped[-1] = 1.
                joint_profile["t"].extend(mapped[use].tolist())
                for key in ("source_m", "bed_m"):
                    joint_profile[key].extend(profile[key][lo:hi][use])
            joint_profile["offsets"].append(len(joint_profile["t"]))
            joint_receiver.append(remap[current])
        filtered = {"offsets": [0], "parent_detail_identity": profile["parent_detail_identity"], "t": [], "source_m": [], "bed_m": []}
        for lo, hi in zip(joint_profile["offsets"][:-1], joint_profile["offsets"][1:]):
            values = np.asarray(joint_profile["t"][lo:hi])
            keep = np.r_[True, np.diff(values) > 1e-12]
            for key in ("t", "source_m", "bed_m"):
                filtered[key].extend(np.asarray(joint_profile[key][lo:hi])[keep].tolist())
            filtered["offsets"].append(len(filtered["t"]))
        joint_profile = filtered
        piece.update(receiver=joint_receiver, parent_node_ids=retained, junction_piece=True,
            joint_component=True,
            fine_spacing_m=specification["fine_spacing_m"], centerline_profile=joint_profile,
            coverage={**specification["coverage"], "scope": "joint solve of complete declared clipped three-arm component"})
        return [piece]
    pieces = []
    for group in groups:
        nodes = sorted(set(group + [int(receivers[node]) for node in group]))
        node_index = {node: index for index, node in enumerate(nodes)}
        piece = {key: [specification[key][node] for node in nodes] for key in
                 ("points_xz_m", "width_m", "bed_target_m", "node_source_edges", "node_edge_fractions")}
        clipped_profile = {"offsets": [0], "parent_detail_identity": profile["parent_detail_identity"],
                           "t": [], "source_m": [], "bed_m": []}
        for node in nodes:
            if node not in group:
                continue
            lo, hi = profile["offsets"][edge_index[node]:edge_index[node] + 2]
            for key in ("t", "source_m", "bed_m"):
                clipped_profile[key].extend(profile[key][lo:hi])
            clipped_profile["offsets"].append(len(clipped_profile["t"]))
        piece.update({"receiver": [node_index[int(receivers[node])] if node in group else -1 for node in nodes],
                      "parent_node_ids": nodes, "junction_piece": junction is not None and junction in group,
                      "fine_spacing_m": specification["fine_spacing_m"], "centerline_profile": clipped_profile,
                      "coverage": {**specification["coverage"], "piece_index": len(pieces),
                                   "scope": "one subdivision of shared declared full-window component"}})
        pieces.append(piece)
    return pieces


def represented_section_offsets(result, position, normal, radius):
    """All affine trace breakpoints of one saved mesh on a physical section."""
    from types import SimpleNamespace
    from terrain_pipeline.surface_rivers.metric_monotone_union import _line_constraints
    arrays = result["arrays"]
    terrain = SimpleNamespace(x0_m=result["mesh_origin_xz_m"][0], z0_m=result["mesh_origin_xz_m"][1])
    ends = position + np.array([-radius, radius])[:, None]*normal
    records = _line_constraints(ends, np.array([1, -1]), arrays["cells"], arrays["vertices_xz_m"],
                                arrays["triangles"], terrain, result["fine_spacing_m"])
    return [float((weights @ arrays["vertices_xz_m"][ids]-position) @ normal)
            for start, end, _, _, _ in records for ids, weights in (start, end)]


def audit_frozen_window_seams(results, specification, *, center_lowest=False):
    """Cold-check both represented finite beds at every shared full-width seam."""
    pieces = split_frozen_window_component(specification)
    if len(results) != len(pieces) or any(not result.get("arrays") for result in results):
        return {"accepted": False, "reason": "full_window_mesh_coverage_incomplete"}
    maximum = 0.0
    transverse_residual = 0.0
    center_minimum_residual = 0.0
    center_lowest = bool(center_lowest or any(result.get("center_lowest", False) for result in results))
    count = 0
    lookups = [{tuple(cell): index for index, cell in enumerate(result["arrays"]["cells"])} for result in results]

    def sample(result_index, point):
        result = results[result_index]
        arrays = result["arrays"]
        cells, vertices, triangles = arrays["cells"], arrays["vertices_xz_m"], arrays["triangles"]
        # Mesh cells are indexed relative to the parent terrain's physical origin.
        origin = np.asarray(result["mesh_origin_xz_m"])
        key = tuple(np.floor((point - origin) / result["fine_spacing_m"]).astype(int))
        lookup = lookups[result_index]
        if key not in lookup:
            raise ValueError("full-width seam leaves represented finite mesh")
        return _mesh_height(point, lookup[key], vertices, triangles, arrays["bed_elevation_m"])

    try:
        occurrences = {}
        for index, (result, piece) in enumerate(zip(results, pieces)):
            if (not np.allclose(result["arrays"]["node_xz_m"], piece["points_xz_m"], atol=1e-8, rtol=0)
                    or not np.allclose(result["arrays"]["node_bed_target_m"], piece["bed_target_m"], atol=1e-8, rtol=0)
                    or not np.array_equal(result["arrays"]["receiver"], piece["receiver"])):
                return {"accepted": False, "reason": "full_window_piece_does_not_match_shared_profile"}
            for local_node, parent_node in enumerate(piece["parent_node_ids"]):
                occurrences.setdefault(parent_node, []).append((index, local_node))
        for shared in occurrences.values():
            if len(shared) < 2:
                continue
            first_piece, local_node = shared[0]
            piece = pieces[first_piece]
            position = np.asarray(piece["points_xz_m"][local_node])
            local_receivers = np.asarray(piece["receiver"])
            neighbors = np.flatnonzero(local_receivers == local_node).tolist()
            if local_receivers[local_node] >= 0:
                neighbors.append(int(local_receivers[local_node]))
            direction = np.asarray(piece["points_xz_m"][neighbors[0]]) - position
            normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
            for other_piece, _ in shared[1:]:
                center_heights = [sample(first_piece, position), sample(other_piece, position)]
                half = piece["width_m"][local_node] / 2
                first_sections = results[first_piece].get("shared_sections") or []
                other_sections = results[other_piece].get("shared_sections") or []
                section = next((item for item in first_sections if np.allclose(item["position_xz_m"], position, atol=1e-8, rtol=0)), None)
                radius = half + (np.sqrt(2.)+1.)*max(results[first_piece]["fine_spacing_m"], results[other_piece]["fine_spacing_m"]) + 8.
                offsets = [0., -half, half, -radius, radius]
                if section is not None:
                    other = next((item for item in other_sections if item.get("parent_node_id") == section.get("parent_node_id")), None)
                    if other != section:
                        return {"accepted": False, "reason": "shared_cross_section_contracts_differ"}
                    normal = np.asarray(section["normal_xz"])
                    radius = section["radius_m"]
                    offsets.extend(section["offsets_m"])
                offsets = np.unique(np.r_[offsets,
                    represented_section_offsets(results[first_piece], position, normal, radius),
                    represented_section_offsets(results[other_piece], position, normal, radius)])
                for offset in offsets:
                    point = position + offset * normal
                    heights = [sample(first_piece, point), sample(other_piece, point)]
                    maximum = max(maximum, abs(heights[0] - heights[1]))
                    if section is not None:
                        target = np.interp(offset, section["offsets_m"], section["bed_elevation_m"])
                        maximum = max(maximum, max(abs(height - target) for height in heights))
                    if abs(offset) <= half + 1e-8:
                        transverse_residual = max(transverse_residual, max(height - center - abs(offset) * 0.02
                            for height, center in zip(heights, center_heights)))
                    center_minimum_residual = max(center_minimum_residual, max(center - height
                        for height, center in zip(heights, center_heights)))
                    count += 1
    except ValueError as error:
        return {"accepted": False, "reason": str(error)}
    return {"accepted": bool(maximum <= 1e-6 and transverse_residual <= 1e-6
                              and (not center_lowest or center_minimum_residual <= 1e-6)),
            "maximum_shared_full_width_bed_difference_m": float(maximum),
            "maximum_full_width_seam_transverse_residual_m": float(transverse_residual),
            "center_lowest_required": center_lowest, "center_minimum_max_residual_m": float(center_minimum_residual),
            "junction_component_count": sum(piece["junction_piece"] for piece in pieces),
            "full_width_seam_samples": count, "piece_count": len(pieces),
            "continuous_affine_trace_verified": bool(maximum <= 1e-6),
            "trace_breakpoints": "union of all triangle crossings in both represented meshes, complete bottom and bank support",
            "scope": "complete declared clipped component; both finite represented beds at every seam"}


def _audit_mesh(cells, vertices, triangles, source, cut, points, receiver, widths, terrain, spacing, *, center_lowest=False,
                continuous_center_lowest=False):
    """Independently sample represented bed, not just solver feasibility flags."""
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    bed = source - cut
    from terrain_pipeline.surface_rivers.metric_design_bed import bed_constraints
    gradient_rows = bed_constraints(points, receiver, cells, vertices, triangles, source, terrain, spacing,
        (np.zeros(np.count_nonzero(receiver >= 0) + 1, int), [], [], []), 1e-5,
        profile_node_mask=np.zeros(len(receiver), bool))
    gradient_residual = max((float(weights @ cut[ids] - limit)
                             for ids, weights, limit, _ in gradient_rows), default=0.)
    longitudinal_residual = 0.0
    transverse_residual = 0.0
    samples = 0
    center_minimum_residual = 0.0
    unreconnected_banks = 0
    internal_junction_sections = 0
    bank_sections = 0
    minimum_reconnected_bank_rise = np.inf

    def sample(point, values=bed):
        key = tuple(np.floor((point - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int))
        if key not in lookup:
            raise ValueError("independent represented bed sample outside finite mesh support")
        return _mesh_height(point, lookup[key], vertices, triangles, values)

    def belongs_to_strip(point, distance):
        for first in np.flatnonzero(receiver >= 0):
            vector = points[receiver[first]] - points[first]
            t = np.clip((point - points[first]) @ vector / (vector @ vector), 0, 1)
            if np.linalg.norm(point - points[first] - t * vector) < distance - 1e-8:
                return False
        return True

    for node in np.flatnonzero(receiver >= 0):
        other = receiver[node]
        vector = points[other] - points[node]
        length = np.linalg.norm(vector)
        direction = vector / length
        normal = np.array([-direction[1], direction[0]])
        parameters = np.linspace(0.0, 1.0, max(3, int(np.ceil(length / spacing)) + 1))
        center = np.array([sample(points[node] + value * vector) for value in parameters])
        slope_residual = np.diff(center) + np.diff(parameters) * length * 1e-5
        longitudinal_residual = max(longitudinal_residual, float(slope_residual.max(initial=0.0)))
        # Skip graph nodes: intersections use the established shared-node cone,
        # while ordinary sections must expose the actual full transverse bottom.
        for value, center_height in zip(parameters[1:-1], center[1:-1]):
            width = widths[node] * (1 - value) + widths[other] * value
            position = points[node] + value * vector
            for offset in np.linspace(-width / 2, width / 2, 9):
                actual = sample(position + offset * normal)
                transverse_residual = max(transverse_residual, actual - center_height - abs(offset) * 0.02)
                if center_lowest and belongs_to_strip(position + offset * normal, abs(offset)):
                    center_minimum_residual = max(center_minimum_residual, center_height - actual)
                samples += 1
            if center_lowest:
                radius = width / 2 + (np.sqrt(2) + 1.) * spacing + 8.0
                for side in (-1, 1):
                    distances = np.linspace(width / 2, radius, int(np.ceil((radius - width / 2) / spacing)) + 1)
                    cuts, rises = [], []
                    crossed_other_arm = False
                    for distance in distances:
                        point = position + side * distance * normal
                        if not belongs_to_strip(point, distance):
                            crossed_other_arm = True
                            continue
                        actual = sample(point)
                        source_height = sample(point, source)
                        center_minimum_residual = max(center_minimum_residual, center_height - actual)
                        cuts.append(source_height - actual)
                        rises.append(actual - center_height)
                    if not cuts:
                        continue
                    if continuous_center_lowest and np.count_nonzero(receiver >= 0) > 1 and crossed_other_arm:
                        internal_junction_sections += 1
                        continue
                    bank_sections += 1
                    returned = np.asarray(cuts) <= 1e-8
                    if not returned.any():
                        unreconnected_banks += 1
                    else:
                        minimum_reconnected_bank_rise = min(minimum_reconnected_bank_rise, float(np.asarray(rises)[returned].max()))
    exact_floor_residual = None
    exact_floor_count = 0
    union_boundary_count = 0
    union_boundary_cut = None
    unknown_union_boundary = False
    if continuous_center_lowest:
        ids, coefficients, _ = continuous_center_floor_constraints(points, receiver, widths, cells, vertices,
            triangles, source, terrain, spacing, np.full(len(source), 4.))
        exact_floor_residual = float(np.max(-np.sum(coefficients * bed[ids], axis=1), initial=0.))
        exact_floor_count = len(ids)
        if np.count_nonzero(receiver >= 0) > 1:
            boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
            union_boundary_count = len(boundary)
            union_boundary_cut = float(np.max(np.abs(cut[boundary]), initial=0.))
            origin = np.array([terrain.x0_m, terrain.z0_m])
            maximum = origin + np.array([terrain.elevation_m.shape[1] - 1, terrain.elevation_m.shape[0] - 1]) * np.array([terrain.dx_m, terrain.dz_m])
            unknown_union_boundary = bool(np.any(vertices <= origin + 1e-8) or np.any(vertices >= maximum - 1e-8))
    accepted = (np.isfinite(bed).all() and cut.min(initial=0.0) >= -1e-8
                and cut.max(initial=0.0) <= 4.0 + 1e-8
                and longitudinal_residual <= 1e-6 and gradient_residual <= 1e-8 and transverse_residual <= 1e-6
                and (not center_lowest or (center_minimum_residual <= 1e-6 and not unreconnected_banks
                    and minimum_reconnected_bank_rise >= -1e-6))
                and (exact_floor_residual is None or exact_floor_residual <= 1e-6)
                and not unknown_union_boundary and (union_boundary_cut is None or union_boundary_cut <= 1e-8))
    return {"accepted": bool(accepted), "longitudinal_max_residual_m": longitudinal_residual,
            "physical_triangle_gradient_max_residual_m_per_m": float(gradient_residual),
            "physical_triangle_gradient_constraint_count": len(gradient_rows),
            "continuous_longitudinal_gradient_verified": bool(gradient_residual <= 1e-8),
            "continuous_longitudinal_gradient_scope": "all triangle planes crossed by the represented centerline paths; downstream directional slope on those crossings, not all mesh faces or arbitrary off-centerline points",
            "transverse_max_residual_m": float(transverse_residual), "transverse_sample_count": samples,
            "maximum_cut_m": float(cut.max(initial=0.0)), "minimum_cut_m": float(cut.min(initial=0.0)),
            "center_lowest_required": bool(center_lowest),
            "bank_support_radius_policy": "half width plus (sqrt(2)+1) fine spacing plus 8m; same represented support as design builder",
            "continuous_center_floor_max_residual_m": exact_floor_residual,
            "continuous_center_floor_polygon_vertex_count": exact_floor_count,
            "continuous_center_floor_scope": "all represented triangle/projection partition vertices; shared-junction nearest-ray polygons include conservative distant-end supersets" if continuous_center_lowest else None,
            "internal_junction_bank_sections": internal_junction_sections,
            "union_exterior_boundary_vertex_count": union_boundary_count,
            "union_exterior_boundary_maximum_cut_m": union_boundary_cut,
            "union_exterior_touches_unknown_source_boundary": unknown_union_boundary,
            "center_minimum_max_residual_m": float(center_minimum_residual),
            "unreconnected_bank_sections": unreconnected_banks, "bank_section_count": bank_sections,
            "minimum_reconnected_bank_rise_m": None if not np.isfinite(minimum_reconnected_bank_rise) else float(minimum_reconnected_bank_rise),
            "scope": "represented finite fan4 mesh; samples every fine spacing and nine bottom offsets"}


def audit_saved_continuous_bed(result, detail, *, center_lowest=True, continuous_center_lowest=None,
                               centerline_profile=None, frozen_path=None, frozen_plan=None):
    """Reassess saved geometry against the explicit actual-channel contract."""
    arrays, meta = result["arrays"], detail["metadata"]
    if result["parent_detail_identity"] != meta["identity"]:
        raise ValueError("saved continuous bed source parent identity mismatch")
    height = detail["arrays"]["derived_height_m"]
    terrain = TerrainGrid(height, np.ones(height.shape, bool), *meta["origin_xz_m"], meta["spacing_m"], meta["spacing_m"],
                          "conditioned_terrain", "saved-bed-assessment", meta["identity"])
    try:
        if result.get("frozen_path_identity") is not None:
            from terrain_pipeline.frozen_terrain_centerline import validate_frozen_path_nodes
            if frozen_path is None or frozen_plan is None or result["frozen_path_identity"] != frozen_path["identity"]:
                raise ValueError("saved path bed requires its complete frozen path and plan")
            validate_frozen_path_nodes(frozen_path, frozen_plan, arrays["node_xz_m"], arrays["node_source_edges"],
                                      arrays["node_edge_fractions"], arrays["receiver"])
        sampled_source, _ = _sample(height, arrays["vertices_xz_m"], terrain)
        if not np.allclose(sampled_source, arrays["original_macro_bed_m"], rtol=0, atol=1e-8):
            raise ValueError("saved original macro bed differs from immutable detail at mesh vertices")
        for section in result.get("shared_sections") or []:
            if section["algorithm"] in ("bounded-two-sided-30m-feasible-fan4-section-v1",
                                        "bounded-two-sided-30m-feasible-fan4-section-v2",
                                        "bounded-complete-adjacent-feasible-fan4-section-v3"):
                witness = {key: np.asarray(value) for key, value in section["local_mesh_witness"].items()}
                sampled, _ = _sample(height, witness["vertices_xz_m"], terrain)
                if not np.allclose(sampled, witness["original_macro_bed_m"], atol=1e-8, rtol=0):
                    raise ValueError("shared-section local witness differs from immutable source")
                witness_audit = _audit_mesh(witness["cells"], witness["vertices_xz_m"], witness["triangles"],
                    witness["original_macro_bed_m"], witness["local_cut_m"], witness["node_xz_m"],
                    witness["receiver"], witness["width_m"], terrain, result["fine_spacing_m"],
                    center_lowest=True, continuous_center_lowest=True)
                from terrain_pipeline.surface_rivers.metric_design_bed import shared_section_constraints
                rows = shared_section_constraints([section], witness["cells"], witness["vertices_xz_m"],
                    witness["triangles"], sampled, terrain, result["fine_spacing_m"])
                if not witness_audit["accepted"] or max(float(weights @ witness["local_cut_m"][ids]-limit)
                                                        for ids, weights, limit, _ in rows) > 1e-8:
                    raise ValueError("shared-section local source mesh witness rejected")
                if abs(np.interp(0., section["offsets_m"], section["bed_elevation_m"])-section["center_bed_m"]) > 1e-8:
                    raise ValueError("shared-section center differs from explicit frozen target")
                continue
            raise ValueError("unsupported shared-section algorithm; source mesh witness required")
        audit = _audit_mesh(arrays["cells"], arrays["vertices_xz_m"], arrays["triangles"], arrays["original_macro_bed_m"],
            arrays["local_cut_m"], arrays["node_xz_m"], arrays["receiver"], arrays["width_m"], terrain,
            result["fine_spacing_m"], center_lowest=center_lowest,
            continuous_center_lowest=(result.get("continuous_center_lowest", False)
                                     if continuous_center_lowest is None else continuous_center_lowest))
        audit["immutable_source_at_vertices_verified"] = True
        profile_keys = ("offsets", "t", "source_m", "bed_m")
        if centerline_profile is not None:
            profile = tuple(np.asarray(centerline_profile[key]) for key in profile_keys)
        elif all("centerline_profile_" + key in arrays for key in profile_keys):
            profile = tuple(arrays["centerline_profile_" + key] for key in profile_keys)
        else:
            profile = None
        if profile is not None:
            from terrain_pipeline.surface_rivers.metric_design_bed import bed_constraints
            rows = bed_constraints(arrays["node_xz_m"], arrays["receiver"], arrays["cells"], arrays["vertices_xz_m"],
                arrays["triangles"], arrays["original_macro_bed_m"], terrain, result["fine_spacing_m"], profile, 1e-5)
            residual = max((float(weights @ arrays["local_cut_m"][ids]-limit)
                            for ids, weights, limit, kind in rows if kind == "profile"), default=0.)
            audit.update(frozen_profile_ceiling_max_residual_m=residual, frozen_profile_ceiling_verified=residual <= 1e-8,
                         frozen_profile_constraint_count=sum(kind == "profile" for _, _, _, kind in rows))
            audit["accepted"] = bool(audit["accepted"] and residual <= 1e-8)
        else:
            audit.update(frozen_profile_ceiling_verified=False, frozen_profile_ceiling_scope="source profile not supplied or archived")
        if result.get("shared_sections"):
            from terrain_pipeline.surface_rivers.metric_design_bed import shared_section_constraints
            rows = shared_section_constraints(result["shared_sections"], arrays["cells"], arrays["vertices_xz_m"],
                arrays["triangles"], arrays["original_macro_bed_m"], terrain, result["fine_spacing_m"])
            residual = max((float(weights @ arrays["local_cut_m"][ids] - limit)
                            for ids, weights, limit, _ in rows), default=0.)
            audit.update(shared_section_affine_max_residual_m=residual, shared_section_constraint_count=len(rows),
                         shared_section_continuous_trace_verified=residual <= 1e-8)
            audit["accepted"] = bool(audit["accepted"] and residual <= 1e-8)
        return audit
    except ValueError as error:
        return {"accepted": False, "reason": str(error), "center_lowest_required": bool(center_lowest)}


def derive_continuous_bed(detail, points_xz_m, receiver, width_m, bed_target_m, *, fine_spacing_m=1.0,
                          frozen_plan=None, node_source_edges=None, node_edge_fractions=None, centerline_profile=None,
                          tributary_declaration=None, highest_lake_level_m=None, lake_mask=None, center_lowest=False,
                          continuous_center_lowest=False, joint_component=False, shared_sections=None, frozen_path=None):
    """Explicit component only: no local rerouting, invented ports, or widening budget.

    A successful mesh remains locally geometric, not a hydraulic certificate.
    Macro-grid D8 evidence and fine triangle bed evidence remain distinct.
    """
    arrays, meta = detail["arrays"], detail["metadata"]
    height = arrays["derived_height_m"]
    origin = meta["origin_xz_m"]
    terrain = TerrainGrid(height, np.ones(height.shape, dtype=bool), origin[0], origin[1],
        meta["spacing_m"], meta["spacing_m"], "conditioned_terrain", "hydrology-detail", meta["identity"])
    points = np.asarray(points_xz_m, dtype=np.float64)
    receiver = np.asarray(receiver, dtype=np.int64)
    width = np.asarray(width_m, dtype=np.float64)
    target = np.asarray(bed_target_m, dtype=np.float64)
    if (points.ndim != 2 or points.shape[1] != 2 or not 2 <= len(points) <= 16
            or receiver.shape != (len(points),) or width.shape != receiver.shape or target.shape != receiver.shape
            or not np.isfinite(points).all() or not np.isfinite(width).all() or not np.isfinite(target).all()
            or np.any(width < 4) or np.any(width > 64) or np.any(receiver < -1) or np.any(receiver >= len(points))):
        raise ValueError("bounded 2..16 node frozen component with widths 4..64m required")
    if not 0.5 <= fine_spacing_m <= 2.0:
        raise ValueError("finite fine spacing must be 0.5..2m")
    if frozen_plan is None or node_source_edges is None or node_edge_fractions is None:
        return {"status": "rejected", "reason": "component_missing_frozen_drainage_graph_provenance", "arrays": {}}
    if frozen_plan.get("identity_sha256") != meta["plan_identity"]:
        raise ValueError("fine component frozen-plan identity mismatch")
    if shared_sections and any(section.get("parent_detail_identity") != meta["identity"]
                               or section.get("fine_spacing_m") != fine_spacing_m for section in shared_sections):
        raise ValueError("shared-section source parent or fine spacing mismatch")
    source_edges = np.asarray(node_source_edges, dtype=np.int64)
    fractions = np.asarray(node_edge_fractions, dtype=np.float64)
    if source_edges.shape != (len(points), 2) or fractions.shape != (len(points),) or not np.isfinite(fractions).all() or np.any(fractions < 0) or np.any(fractions > 1):
        raise ValueError("each clipped node needs an actual frozen edge and fraction 0..1")
    frozen_receivers = np.asarray(frozen_plan["receiver"]).ravel()
    frozen_rivers = np.asarray(frozen_plan["river_mask"]).ravel()
    if np.any(source_edges < 0) or np.any(source_edges >= frozen_receivers.size):
        raise ValueError("invalid frozen source-edge cell ids")
    tributary_validation = None
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
        tributary_validation = validate_local_tributary_source_edges(frozen_plan, tributary_declaration, source_edges,
            highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    if not np.all(frozen_receivers[source_edges[:, 0]] == source_edges[:, 1]) or (tributary_validation is None and not np.all(frozen_rivers[source_edges[:, 0]])):
        raise ValueError("component edges are not genuine frozen river graph edges")
    frozen_owners = np.asarray(frozen_plan["owner_domain_id"]).ravel()
    coastal_domains = {domain["domain_id"] for domain in frozen_plan["domains"] if domain.get("kind") == "coastal"}
    mouth_component = bool(np.any((frozen_owners[source_edges[:, 1]] == -1)
        & np.isin(frozen_owners[source_edges[:, 0]], list(coastal_domains))))
    columns = np.asarray(frozen_plan["height_m"]).shape[1]
    source_xz = np.stack((source_edges % columns, source_edges // columns), axis=-1).astype(float)
    expected_points = np.asarray(frozen_plan["origin_xz_m"]) + frozen_plan["spacing_m"] * (
        source_xz[:, 0, :] * (1 - fractions[:, None]) + source_xz[:, 1, :] * fractions[:, None])
    if frozen_path is None:
        if not np.allclose(points, expected_points, atol=1e-7, rtol=0):
            raise ValueError("component node coordinates differ from frozen graph clipping")
    else:
        from terrain_pipeline.frozen_terrain_centerline import validate_frozen_path_nodes
        validate_frozen_path_nodes(frozen_path, frozen_plan, points, source_edges, fractions, receiver)
    maximum = np.asarray(origin) + (np.array(height.shape)[::-1] - 1) * meta["spacing_m"]
    if np.any(points < origin) or np.any(points > maximum):
        raise ValueError("component leaves finite genuine TD source")
    edges = np.flatnonzero(receiver >= 0)
    if not len(edges):
        raise ValueError("component needs a frozen directed edge")
    for node in edges:
        other = receiver[node]
        same_edge = np.array_equal(source_edges[node], source_edges[other]) and fractions[node] < fractions[other]
        shared_node = source_edges[node, 1] == source_edges[other, 0] and fractions[other] == 0
        if not same_edge and not shared_node:
            raise ValueError("fine component joins unrelated frozen river edges")
    for node in range(len(points)):
        seen = set()
        while node >= 0:
            if node in seen:
                raise ValueError("frozen component cycle")
            seen.add(node)
            node = int(receiver[node])
    source, _ = _sample(height, points, terrain)
    if np.any(source - target > 4) or np.any(source - target < 0):
        return {"status": "rejected", "reason": "continuous_bed_target_exceeds_original_4m_cut", "arrays": {}}
    length = np.linalg.norm(points[edges] - points[receiver[edges]], axis=1)
    maximum_length = 3000 if joint_component and tributary_validation is not None and len(points) == 4 else 1000
    if np.any(length <= 0) or np.any(length > maximum_length) or np.any(target[edges] - target[receiver[edges]] < length * 1e-5):
        return {"status": "rejected", "reason": "non_descending_or_unbounded_frozen_component", "arrays": {}}
    gx = np.rint((points[:, 0] - origin[0]) / meta["spacing_m"]).astype(int)
    gz = np.rint((points[:, 1] - origin[1]) / meta["spacing_m"]).astype(int)
    owner = arrays["owner_domain_id"][gz, gx]
    if np.any((owner[edges] != owner[receiver[edges]]) & (owner[receiver[edges]] >= 0)):
        return {"status": "rejected", "reason": "frozen_component_crosses_shared_divide", "arrays": {}}
    for node in edges:
        other = receiver[node]
        count = max(2, int(np.ceil(length[list(edges).index(node)] / min(meta["spacing_m"], fine_spacing_m))) + 1)
        samples = points[node] + np.linspace(0, 1, count)[:, None] * (points[other] - points[node])
        sx = np.rint((samples[:, 0] - origin[0]) / meta["spacing_m"]).astype(int)
        sz = np.rint((samples[:, 1] - origin[1]) / meta["spacing_m"]).astype(int)
        actual_owners = arrays["owner_domain_id"][sz, sx]
        same_domain = actual_owners == frozen_owners[source_edges[node, 0]]
        certified_ocean = ((actual_owners == -1) & arrays["ocean_mask"][sz, sx]
                           & (height[sz, sx] < 0) & mouth_component)
        if not np.all(same_domain | certified_ocean):
            return {"status": "rejected", "reason": "frozen_segment_interior_leaves_owner", "arrays": {}}
    profile = (np.arange(0, 2 * len(edges) + 1, 2), np.tile([0.0, 1.0], len(edges)),
               np.column_stack((source[edges], source[receiver[edges]])).ravel(),
               np.column_stack((target[edges], target[receiver[edges]])).ravel())
    if centerline_profile is not None:
        if centerline_profile.get("parent_detail_identity") != meta["identity"]:
            raise ValueError("full-window profile parent identity mismatch")
        profile = tuple(np.asarray(centerline_profile[key], dtype=(int if key == "offsets" else float))
                        for key in ("offsets", "t", "source_m", "bed_m"))
        if (profile[0].shape != (len(edges) + 1,) or profile[0][0] != 0 or profile[0][-1] != len(profile[1])
                or np.any(np.diff(profile[0]) < 2) or profile[2].shape != profile[1].shape
                or profile[3].shape != profile[1].shape or not all(np.isfinite(value).all() for value in profile)):
            raise ValueError("finite complete full-window profile required")
        for edge_index, node in enumerate(edges):
            lo, hi = profile[0][edge_index:edge_index + 2]
            t = profile[1][lo:hi]
            bed = profile[3][lo:hi]
            other = receiver[node]
            if (t[0] != 0 or t[-1] != 1 or np.any(np.diff(t) <= 0)
                    or np.max(np.diff(t)) * length[edge_index] > fine_spacing_m * 1.01
                    or not np.allclose(bed[[0, -1]], target[[node, other]], atol=1e-8, rtol=0)
                    or np.any(np.diff(bed) > -np.diff(t) * length[edge_index] * 1e-5 + 1e-8)):
                raise ValueError("full-window profile must cover every segment with shared descending node beds")
            actual, _ = _sample(height, points[node] + t[:, None] * (points[other] - points[node]), terrain)
            if not np.allclose(actual, profile[2][lo:hi], atol=1e-4, rtol=0):
                raise ValueError("full-window profile source differs from parent terrain")
            if np.any(actual - bed > 4 + 1e-8) or np.any(actual - bed < -1e-8):
                return {"status": "rejected", "reason": "full_window_profile_exceeds_original_4m_cut", "arrays": {}}
    try:
        mesh = build_design_geometry(points, receiver, width, np.minimum(0.5, source - target),
            profile, terrain, fine_spacing_m, 4.0, 1e-5, transverse_bottom_slope=0.02, center_lowest=center_lowest,
            continuous_center_lowest=continuous_center_lowest, shared_sections=shared_sections)
    except ValueError as error:
        return {"status": "rejected", "reason": str(error), "arrays": {}}
    cells, vertices, triangles, original, _, cut, closure = mesh[:7]
    if np.any(vertices < origin) or np.any(vertices > maximum):
        return {"status": "rejected", "reason": "continuous_mesh_leaves_genuine_td_support", "arrays": {}}
    vx = np.rint((vertices[:, 0] - origin[0]) / meta["spacing_m"]).astype(int)
    vz = np.rint((vertices[:, 1] - origin[1]) / meta["spacing_m"]).astype(int)
    vertex_owners = arrays["owner_domain_id"][vz, vx]
    same_domain = vertex_owners == frozen_owners[source_edges[edges[0], 0]]
    certified_ocean = ((vertex_owners == -1) & arrays["ocean_mask"][vz, vx]
                       & (height[vz, vx] < 0) & mouth_component)
    if not np.all(same_domain | certified_ocean):
        return {"status": "rejected", "reason": "continuous_mesh_enters_unknown_or_other_domain", "arrays": {}}
    if np.any(arrays["shared_boundary_protected"][vz, vx] & (cut > 1e-10)):
        return {"status": "rejected", "reason": "continuous_bed_support_touches_shared_divide", "arrays": {}}
    try:
        audit = _audit_mesh(cells, vertices, triangles, original, cut, points, receiver, width, terrain, fine_spacing_m,
            center_lowest=center_lowest, continuous_center_lowest=continuous_center_lowest)
    except ValueError as error:
        return {"status": "rejected", "reason": str(error), "arrays": {}}
    if not audit["accepted"]:
        return {"status": "rejected", "reason": "independent_continuous_bed_audit_failed", "audit": audit, "arrays": {}}
    original_td, _ = _sample(arrays["original_td_m"], vertices, terrain)
    macro_delta = original - original_td
    total_delta = original - cut - original_td
    ledger = {"local_max_cut_m": float(cut.max(initial=0.0)),
              "local_cut_volume_m3": _mesh_volume_chunked(vertices, triangles, cut),
              "macro_max_abs_m": float(np.abs(macro_delta).max(initial=0.0)),
              "total_max_abs_m": float(np.abs(total_delta).max(initial=0.0)),
              "total_absolute_volume_upper_bound_m3": _mesh_volume_chunked(vertices, triangles, np.abs(total_delta)),
              "volume_semantics": "exact linear cut integration; absolute total integration upper bound when sign crosses a triangle"}
    if ledger["total_max_abs_m"] > meta["budget"]["total_max_abs_m"] or ledger["total_absolute_volume_upper_bound_m3"] > meta["budget"]["total_absolute_volume_m3"]:
        return {"status": "rejected", "reason": "continuous_mesh_total_change_budget_exceeded", "ledger": ledger, "arrays": {}}
    return {"status": "local_continuous_geometry_global_unverified", "closure": closure,
            "algorithm": ("frozen-continuous-bed-v9-whole-path-arclength" if frozen_path is not None else "frozen-continuous-bed-v8-complete-adjacent-shared-sections" if shared_sections
                          and all(section["algorithm"] == "bounded-complete-adjacent-feasible-fan4-section-v3" for section in shared_sections)
                          else "frozen-continuous-bed-v7-bounded-feasible-shared-sections" if shared_sections
                          else "frozen-continuous-bed-v5-continuous-center-floor" if continuous_center_lowest
                          else "frozen-continuous-bed-v4-center-lowest" if center_lowest else "frozen-continuous-bed-v3-ceiling-only"),
            "center_lowest": bool(center_lowest),
            "continuous_center_lowest": bool(continuous_center_lowest),
            "shared_sections": shared_sections,
            "independent_geometry_audit": audit,
            "ledger": ledger,
            "global_hydrology_certified": False, "publishable": False,
            "parent_detail_identity": meta["identity"], "fine_spacing_m": fine_spacing_m,
            "mesh_origin_xz_m": list(origin),
            "frozen_plan_identity": frozen_plan["identity_sha256"],
            **({"frozen_path_identity": frozen_path["identity"], "frozen_path_source_identity": frozen_path["metadata"]["source_identity"]} if frozen_path is not None else {}),
            "local_tributary_sidecar_validation": tributary_validation,
            "component_boundary_policy": "clipped frozen graph; outside component hydraulics unknown",
            "certified_coastal_ocean_support": mouth_component,
            "arrays": {"cells": cells, "vertices_xz_m": vertices, "triangles": triangles,
                       "original_macro_bed_m": original, "local_cut_m": cut, "bed_elevation_m": original - cut,
                       "original_td_m": original_td, "macro_delta_m": macro_delta,
                       "local_channel_delta_m": -cut, "total_delta_m": total_delta,
                       "node_xz_m": points, "node_bed_target_m": target, "receiver": receiver, "width_m": width,
                       "node_source_edges": source_edges, "node_edge_fractions": fractions,
                       **{"centerline_profile_"+key: value for key, value in zip(("offsets", "t", "source_m", "bed_m"), profile)}}}
