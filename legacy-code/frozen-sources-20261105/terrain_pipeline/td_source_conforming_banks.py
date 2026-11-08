"""Independent source-relative bank functions; never repair the absolute parent mesh."""

from collections import Counter, OrderedDict, defaultdict, deque
from bisect import bisect_right
from copy import deepcopy
import gc
import hashlib
import json
import math
from pathlib import Path
import tempfile

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_fine_bed_raster import (
    LEDGER_KEYS, MAX_BYTES, MAX_CELLS, _context, _digest, _sample, _weights)
from terrain_pipeline.td_fine_bed_shards import _cut, _evaluate, _ledger, iter_merged_cells

SCHEMA = "td-source-conforming-banks-v2"
ALGORITHM = "native-bilinear-minus-shared-knot-affine-depth-fan-v2"
FLAGS = ("hydraulic_ready", "hydraulic_solved", "natural_outlet_certified",
         "publish_ready", "full_river_verified", "cross_domain_verified", "vdm_verified",
         "bed_changed", "water_generated", "full_watershed_fine_verified",
         "cross_shard_hydraulics_verified")
MAX_RSS = 1024**3
MAX_FILES = 4096
MAX_SAMPLE_CACHE = 65536
MAX_PATCH_CACHE = 8192
GEOMETRY_TOLERANCE_M = 1e-8
FUNCTION_TOLERANCE_M = 1e-9


def _json_fragments(record):
    encoder = json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(",", ":"))
    for fragment in encoder.iterencode(record):
        yield fragment.encode("utf-8")


def _record_identity(record):
    digest = hashlib.sha256()
    for fragment in _json_fragments(record):
        digest.update(fragment)
    return digest.hexdigest()


def _record_bytes(record):
    return sum(len(fragment) for fragment in _json_fragments(record))


def _write_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        for fragment in _json_fragments(record):
            handle.write(fragment)


def _seal(record):
    record["identity_sha256"] = _record_identity(record)
    return record


def _check_identity(record):
    if record.get("identity_sha256") != _record_identity(
            {key: value for key, value in record.items() if key != "identity_sha256"}):
        raise ValueError("source-conforming content identity mismatch")


def _rss_guard(callback=None, *, phase=None, counters=None):
    if callback is not None:
        if phase is not None and hasattr(callback, "__dict__"):
            callback.phase = phase
            callback.counters = counters or {}
        callback()
    memory = psutil.Process().memory_info()
    if max(memory.rss, getattr(memory, "peak_wset", 0)) > MAX_RSS:
        raise MemoryError("source-conforming hard 1GiB peak RSS exceeded")


def _source_sample(context, x_m, z_m):
    cache = context.setdefault("bank_sample_cache", OrderedDict())
    key = (x_m, z_m)
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    value = _sample(context, x_m, z_m)
    cache[key] = value
    if len(cache) > MAX_SAMPLE_CACHE:
        cache.popitem(last=False)
    return value


def _line_key(points):
    first, second = np.asarray(points[0], float), np.asarray(points[1], float)
    direction = second - first
    length = float(np.linalg.norm(direction))
    if length <= GEOMETRY_TOLERANCE_M:
        raise ValueError("degenerate projected edge")
    direction /= length
    if direction[0] < -1e-12 or (abs(direction[0]) <= 1e-12 and direction[1] < 0):
        direction *= -1
    normal = np.array([-direction[1], direction[0]])
    offset = float(normal @ first)
    return (round(float(direction[0]), 10), round(float(direction[1]), 10), round(offset, 7))


def _edge_record(triangle, edge_index):
    points = np.asarray(triangle["vertices_xyz_m"], float)
    first, second = points[edge_index], points[(edge_index + 1) % 3]
    return {"triangle_id": triangle["triangle_id"], "edge_index": edge_index,
            "points_xyz_m": [first.tolist(), second.tolist()]}


def _interval(edge, anchor, direction):
    points = np.asarray(edge["points_xyz_m"], float)[:, [0, 2]]
    delta = points - anchor
    distance = np.abs(delta[:, 0] * direction[1] - delta[:, 1] * direction[0])
    if np.max(distance) > GEOMETRY_TOLERANCE_M:
        raise ValueError("rounded edge key is not a verified common line")
    coordinates = delta @ direction
    return float(min(coordinates)), float(max(coordinates))


def _edge_y(edge, point):
    vertices = np.asarray(edge["points_xyz_m"], float)
    vector = vertices[1, [0, 2]] - vertices[0, [0, 2]]
    fraction = float((point - vertices[0, [0, 2]]) @ vector / (vector @ vector))
    return float(vertices[0, 1] + fraction * (vertices[1, 1] - vertices[0, 1]))


def _native_patch(context, point):
    position = (np.asarray(point) - context["origin"]) / context["spacing"]
    rows, columns = context["height"].shape
    if not (0 <= position[0] <= columns - 1 and 0 <= position[1] <= rows - 1):
        raise ValueError("outside_native_dem")
    column = min(int(math.floor(position[0])), columns - 2)
    row = min(int(math.floor(position[1])), rows - 2)
    cache = context.setdefault("bank_patch_cache", OrderedDict())
    key = (row, column)
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    values = [float(context["height"][row + vertical, column + horizontal])
              for vertical, horizontal in ((0, 0), (0, 1), (1, 0), (1, 1))]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite_native_height")
    coefficients = [values[0], values[1] - values[0], values[2] - values[0],
                    values[3] - values[2] - values[1] + values[0]]
    patch = {"patch_row_column": [row, column],
            "native_cell_ids": [row * columns + column, row * columns + column + 1,
                                (row + 1) * columns + column, (row + 1) * columns + column + 1],
            "native_height_m": values, "bilinear_coefficients_m": coefficients,
            "patch_origin_m_xz": (context["origin"] + np.array([column, row]) * context["spacing"]).tolist(),
             "native_spacing_m": context["spacing"]}
    cache[key] = patch
    if len(cache) > MAX_PATCH_CACHE:
        cache.popitem(last=False)
    return patch


def source_segment_polynomial(context, start_xz, end_xz):
    """Coefficients in normalized t in [0,1]; a diagonal can be quadratic."""
    start, end = np.asarray(start_xz, float), np.asarray(end_xz, float)
    patch = _native_patch(context, (start + end) / 2)
    native_origin, spacing = np.asarray(patch["patch_origin_m_xz"]), patch["native_spacing_m"]
    horizontal, vertical = (start - native_origin) / spacing
    delta_horizontal, delta_vertical = (end - start) / spacing
    constant, horizontal_term, vertical_term, mixed = patch["bilinear_coefficients_m"]
    coefficients = [constant + horizontal_term * horizontal + vertical_term * vertical + mixed * horizontal * vertical,
                    horizontal_term * delta_horizontal + vertical_term * delta_vertical
                    + mixed * (horizontal * delta_vertical + vertical * delta_horizontal),
                    mixed * delta_horizontal * delta_vertical]
    return {**patch, "source_coefficients_m_t012": [float(value) for value in coefficients]}


def _iter_segments(groups, context):
    segment_number = 0
    for group_key in sorted(groups):
        edges = groups[group_key]
        anchor = np.asarray(edges[0]["points_xyz_m"][0], float)[[0, 2]]
        direction = np.asarray(edges[0]["points_xyz_m"][1], float)[[0, 2]] - anchor
        direction /= np.linalg.norm(direction)
        if direction[0] < -1e-12 or (abs(direction[0]) <= 1e-12 and direction[1] < 0):
            direction *= -1
        intervals = [_interval(edge, anchor, direction) for edge in edges]
        minimum, maximum = min(pair[0] for pair in intervals), max(pair[1] for pair in intervals)
        knots = [value for pair in intervals for value in pair]
        endpoint_records = []
        for edge in edges:
            for vertex in edge["points_xyz_m"]:
                coordinate = float((np.asarray(vertex)[[0, 2]] - anchor) @ direction)
                endpoint_records.append((coordinate, {"triangle_id": edge["triangle_id"],
                    "edge_index": edge["edge_index"], "xyz_m": vertex}))
        mesh_knots = []
        for coordinate, reference in sorted(endpoint_records, key=lambda pair: pair[0]):
            if not mesh_knots or coordinate - mesh_knots[-1]["coordinate_m"] > GEOMETRY_TOLERANCE_M:
                mesh_knots.append({"coordinate_m": coordinate, "xz_m": (anchor + coordinate * direction).tolist(),
                                   "original_vertex_refs": []})
            mesh_knots[-1]["original_vertex_refs"].append(reference)
        mesh_coordinates = [knot["coordinate_m"] for knot in mesh_knots]
        for axis in range(2):
            if abs(direction[axis]) < 1e-12:
                continue
            ends = [float((anchor + value * direction)[axis]) for value in (minimum, maximum)]
            lower = math.ceil((min(ends) - context["origin"][axis]) / context["spacing"])
            upper = math.floor((max(ends) - context["origin"][axis]) / context["spacing"])
            if upper - lower > 1024:
                raise MemoryError("edge native-grid knot budget exceeded")
            for native_index in range(lower, upper + 1):
                knots.append(float((context["origin"][axis] + native_index * context["spacing"]
                                    - anchor[axis]) / direction[axis]))
        ordered = []
        for value in sorted(knots):
            if not ordered or value - ordered[-1] > GEOMETRY_TOLERANCE_M:
                ordered.append(value)
        starts = sorted((pair[0], number) for number, pair in enumerate(intervals))
        ends = sorted((pair[1], number) for number, pair in enumerate(intervals))
        start_index = end_index = 0
        active = set()
        for first, second in zip(ordered, ordered[1:]):
            midpoint = (first + second) / 2
            while start_index < len(starts) and starts[start_index][0] < midpoint:
                active.add(starts[start_index][1])
                start_index += 1
            while end_index < len(ends) and ends[end_index][0] < midpoint:
                active.discard(ends[end_index][1])
                end_index += 1
            if not active:
                continue
            start, end = anchor + first * direction, anchor + second * direction
            support_index = min(max(0, bisect_right(mesh_coordinates, midpoint) - 1), len(mesh_knots) - 2)
            record = {"segment_id": "segment:" + str(segment_number), "start_xz_m": start.tolist(),
                      "end_xz_m": end.tolist(), "sides": [edges[index] for index in sorted(active)],
                      "depth_support_knots": mesh_knots[support_index:support_index + 2]}
            segment_number += 1
            yield record


def _segments(groups, context):
    return list(_iter_segments(groups, context))


def _components(triangles, segments, seeds):
    parent = {identifier: identifier for identifier in triangles}

    def root(identifier):
        while parent[identifier] != identifier:
            parent[identifier] = parent[parent[identifier]]
            identifier = parent[identifier]
        return identifier

    for segment in segments:
        identifiers = [side["triangle_id"] for side in segment["sides"] if side["triangle_id"] in parent]
        for identifier in identifiers[1:]:
            parent[root(identifier)] = root(identifiers[0])
    selected_roots = {root(identifier) for identifier in seeds}
    members = defaultdict(list)
    for identifier in sorted(triangles):
        if root(identifier) in selected_roots:
            members[root(identifier)].append(identifier)
    return {"component:" + str(number): identifiers
            for number, identifiers in enumerate(sorted(members.values()))}


def _clip_polygon(polygon, axis, bound, keep_above):
    result = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        first_inside = first[axis] >= bound if keep_above else first[axis] <= bound
        second_inside = second[axis] >= bound if keep_above else second[axis] <= bound
        if first_inside:
            result.append(first)
        if first_inside != second_inside:
            fraction = (bound - first[axis]) / (second[axis] - first[axis])
            result.append([first[index] + fraction * (second[index] - first[index]) for index in range(2)])
    return result


def _patch_polygons(context, vertices_xz):
    points = np.asarray(vertices_xz, float)
    native = (points - context["origin"]) / context["spacing"]
    rows, columns = context["height"].shape
    if (native < 0).any() or (native[:, 0] > columns - 1).any() or (native[:, 1] > rows - 1).any():
        raise ValueError("outside_native_dem")
    low = np.floor(native.min(axis=0)).astype(int)
    high = np.minimum(np.floor(native.max(axis=0)).astype(int), [columns - 2, rows - 2])
    if math.prod((high - low + 1).tolist()) > 4096:
        raise MemoryError("fan native patch budget exceeded")
    result = []
    for row in range(low[1], high[1] + 1):
        for column in range(low[0], high[0] + 1):
            corner = context["origin"] + np.array([column, row]) * context["spacing"]
            polygon = points.tolist()
            for axis in range(2):
                polygon = _clip_polygon(polygon, axis, float(corner[axis]), True) if polygon else []
                polygon = _clip_polygon(polygon, axis, float(corner[axis] + context["spacing"]), False) if polygon else []
            if len(polygon) < 3:
                continue
            area = abs(math.fsum(first[0] * second[1] - second[0] * first[1]
                                 for first, second in zip(np.asarray(polygon) - corner,
                                                          np.roll(np.asarray(polygon) - corner, -1, axis=0)))) / 2
            if area <= 1e-14:
                continue
            patch = _native_patch(context, np.mean(polygon, axis=0))
            source_gate = _source_sample(context, float(corner[0] + context["spacing"] / 2),
                                        float(corner[1] + context["spacing"] / 2))
            if source_gate["rejection_reasons"]:
                raise ValueError("native_patch_gate:" + ",".join(source_gate["rejection_reasons"]))
            result.append({**patch, "polygon_xz_m": polygon, "projected_area_m2": area})
    return result


def _proof(segment, context):
    start, end = np.asarray(segment["start_xz_m"]), np.asarray(segment["end_xz_m"])
    samples = [_source_sample(context, float(point[0]), float(point[1])) for point in (start, end)]
    reasons = set(reason for sample in samples for reason in sample["rejection_reasons"])
    support_depths, support_provenance = [], []
    for knot in segment["depth_support_knots"]:
        values, records = [], []
        for reference in knot["original_vertex_refs"]:
            vertex = reference["xyz_m"]
            source_sample = _source_sample(context, vertex[0], vertex[2])
            reasons.update(source_sample["rejection_reasons"])
            value = None if source_sample["height_m"] is None else source_sample["height_m"] - vertex[1]
            values.append(value)
            records.append({**reference, "source_sample": source_sample, "cut_depth_m": value})
        if any(value is None or value < 0 for value in values):
            reasons.add("original_shared_knot_fill_or_unknown")
            support_depths.append(None)
        else:
            if max(values) - min(values) > FUNCTION_TOLERANCE_M:
                reasons.add("shared_original_vertex_depth_mismatch")
            support_depths.append(values[0])
        support_provenance.append(records)
    canonical_depths = [None, None]
    if all(value is not None for value in support_depths):
        first_support, second_support = [np.asarray(knot["xz_m"]) for knot in segment["depth_support_knots"]]
        vector = second_support - first_support
        canonical_depths = [float((1 - fraction) * support_depths[0] + fraction * support_depths[1])
                            for fraction in [float((point - first_support) @ vector / (vector @ vector)) for point in (start, end)]]
    zero_boundary = False
    original_endpoint_depths = []
    if len(segment["sides"]) == 1 and segment["sides"][0].get("zero_depth_boundary_eligible"):
        for vertex in segment["sides"][0]["points_xyz_m"]:
            sample = _source_sample(context, vertex[0], vertex[2])
            original_endpoint_depths.append(None if sample["height_m"] is None else sample["height_m"] - vertex[1])
            reasons.update(sample["rejection_reasons"])
        zero_boundary = original_endpoint_depths == [0., 0.]
    side_depths = []
    for side in segment["sides"]:
        values = [0., 0.] if zero_boundary else canonical_depths
        side_endpoint_depths = []
        for vertex in side["points_xyz_m"]:
            sample = _source_sample(context, vertex[0], vertex[2])
            value = None if sample["height_m"] is None else sample["height_m"] - vertex[1]
            side_endpoint_depths.append(value)
            reasons.update(sample["rejection_reasons"])
        if any(value is None or value < 0 for value in side_endpoint_depths):
            reasons.add("original_edge_vertex_fill_or_unknown")
        for knot in segment["depth_support_knots"]:
            if any(abs(reference["xyz_m"][1] - _edge_y(side, np.asarray(knot["xz_m"]))) > FUNCTION_TOLERANCE_M
                   for reference in knot["original_vertex_refs"]):
                reasons.add("T_junction_original_profile_mismatch")
        if any(value is None or value < 0 for value in values):
            reasons.add("boundary_knot_fill_or_unknown")
        side_depths.append({"triangle_id": side["triangle_id"], "edge_index": side["edge_index"],
                            "depth_knots_m": values, "original_endpoint_cut_depth_m": side_endpoint_depths,
                            "new_common_knot_function_adopted": True})
    if not reasons:
        if any(max(values["depth_knots_m"][index] for values in side_depths)
               - min(values["depth_knots_m"][index] for values in side_depths) > FUNCTION_TOLERANCE_M
               for index in range(2)):
            reasons.add("shared_depth_knot_mismatch")
    source = None
    try:
        source = source_segment_polynomial(context, start, end)
    except ValueError as error:
        reasons.add(str(error))
    depth = None if reasons else side_depths[0]["depth_knots_m"]
    coefficients = None if depth is None else [depth[0], depth[1] - depth[0]]
    if not reasons:
        if any(side["triangle_id"].startswith("legacy06:") for side in segment["sides"]):
            for side in segment["sides"]:
                if not side["triangle_id"].startswith("legacy06:"):
                    continue
                legacy_start = _edge_y(side, start)
                legacy_end = _edge_y(side, end)
                difference = [source["source_coefficients_m_t012"][0] - coefficients[0] - legacy_start,
                              source["source_coefficients_m_t012"][1] - coefficients[1] - (legacy_end - legacy_start),
                              source["source_coefficients_m_t012"][2]]
                if max(abs(value) for value in difference) > FUNCTION_TOLERANCE_M:
                    reasons.add("unchanged_neighbor_quadratic_function_mismatch")
        elif len(segment["sides"]) == 1 and max(depth) > FUNCTION_TOLERANCE_M:
            reasons.add("uncovered_boundary_has_nonzero_depth")
        if len([side for side in segment["sides"] if not side["triangle_id"].startswith("legacy06:")]) > 2:
            reasons.add("nonmanifold_shared_segment")
    if reasons:
        depth = coefficients = None
    return _seal({"kind": "edge_function_proof", **segment, "source": source,
                  "source_samples": samples, "side_depth_knots": side_depths,
                  "depth_support_knot_source_provenance": support_provenance,
                  "support_cut_depth_m": support_depths,
                  "depth_coefficients_m_t01": coefficients,
                  "common_function_identity_sha256": None if depth is None else _digest({
                      "start_xz_m": start.tolist(), "end_xz_m": end.tolist(), "source": source,
                      "depth_coefficients_m_t01": coefficients}),
                  "boundary_condition": "explicit_source_bank_zero_depth_v2" if zero_boundary else "unified_original_vertex_depth_knots_v2",
                  "original_edge_endpoint_cut_depth_m": original_endpoint_depths,
                  "old_absolute_edge_changed": bool(zero_boundary), "status": "refused" if reasons else "candidate",
                  "rejection_reasons": sorted(reasons), "proof_method": "same_native_patch_quadratic_source_and_linear_depth"})


def _port_proofs(transitions, sections, proofs, triangle_components, reasons_by_component):
    edge_sections = {item["arc_id"]: item for item in sections["edge_sections"]}
    result = []
    for entry_index, entry in enumerate(transitions["entries"]):
        if entry["status"] != "candidate":
            continue
        entry_triangles = {side["triangle_id"] for proof in proofs for side in proof["sides"]
                           if side["triangle_id"].startswith(f"09:{entry_index}:")}
        components = {triangle_components[identifier] for identifier in entry_triangles if identifier in triangle_components}
        if not components:
            continue
        reasons, matched = set(), []
        port = entry.get("accepted_port_xyz_m", [])
        owner = edge_sections.get(entry.get("accepted_port_arc_id"))
        if len(port) != 4 or owner is None or port not in owner.get("cross_section_xyz_m", []):
            reasons.add("port_parent_profile_not_exactly_bound")
        else:
            for first, second in zip(port, port[1:]):
                first_xz, second_xz = np.asarray(first)[[0, 2]], np.asarray(second)[[0, 2]]
                vector = second_xz - first_xz
                length = float(np.linalg.norm(vector))
                intervals = []
                for proof in proofs:
                    if not any(side["triangle_id"] in entry_triangles for side in proof["sides"]):
                        continue
                    start, end = np.asarray(proof["start_xz_m"]), np.asarray(proof["end_xz_m"])
                    cross = [(point[0] - first_xz[0]) * vector[1] - (point[1] - first_xz[1]) * vector[0]
                             for point in (start, end)]
                    if max(abs(value) for value in cross) > GEOMETRY_TOLERANCE_M * length:
                        continue
                    values = sorted(float((point - first_xz) @ vector / (vector @ vector)) for point in (start, end))
                    if values[0] < -1e-8 or values[1] > 1 + 1e-8:
                        continue
                    sides = proof["sides"]
                    has_06 = any(side["triangle_id"] == "06:" + str(index)
                                 for side in sides for index in owner["triangle_indices"])
                    has_09 = any(side["triangle_id"] in entry_triangles for side in sides)
                    if not has_06 or not has_09 or proof["status"] != "candidate":
                        reasons.add("port_piece_missing_two_sided_function")
                    intervals.append(values)
                    matched.append(proof["segment_id"])
                cursor = 0.
                for lower, upper in sorted(intervals):
                    if lower > cursor + 1e-8 or lower < cursor - 1e-8:
                        reasons.add("port_piece_gap_or_duplicate")
                    cursor = max(cursor, upper)
                if abs(cursor - 1) > 1e-8:
                    reasons.add("port_piece_incomplete")
        for component in components:
            reasons_by_component[component].update(reasons)
        result.append(_seal({"kind": "port_function_proof", "entry_id": entry["entry_id"],
            "source_entry_index": entry_index, "accepted_port_arc_id": entry.get("accepted_port_arc_id"),
            "original_four_point_port_xyz_m": port, "segment_ids": sorted(set(matched)),
            "component_ids": sorted(components), "status": "refused" if reasons else "candidate",
            "rejection_reasons": sorted(reasons),
            "port_function_identity_sha256": None if reasons else _digest([
                proof["common_function_identity_sha256"] for proof in proofs if proof["segment_id"] in set(matched)]),
            "legacy_port_function_preserved": False,
            "old_absolute_expression_verified": False}))
    return result


def _function(triangle, edge_proofs, context, parameters):
    vertices = np.asarray(triangle["vertices_xyz_m"], float)
    samples = [_source_sample(context, float(point[0]), float(point[2])) for point in vertices]
    reasons = set(reason for sample in samples for reason in sample["rejection_reasons"])
    depths = [None if sample["height_m"] is None else sample["height_m"] - point[1]
              for sample, point in zip(samples, vertices)]
    if any(value is None or value < 0 for value in depths):
        reasons.add("original_vertex_fill_or_unknown")
    if any(value is not None and value > parameters["max_cut_m"] + parameters["conflict_tolerance_m"] for value in depths):
        reasons.add("original_vertex_cut_depth_exceeded")
    if any(value is not None and value > parameters["conflict_tolerance_m"] and sample["wet_source_support"]
           for sample, value in zip(samples, depths)):
        reasons.add("lake_wet_vertex_cut_refused")
    if any(proof["status"] != "candidate" for proof in edge_proofs):
        reasons.add("boundary_function_unproved")
    center = vertices[:, [0, 2]].mean(axis=0)
    center_sample = _source_sample(context, float(center[0]), float(center[1]))
    reasons.update(center_sample["rejection_reasons"])
    center_depth = None if any(value is None for value in depths) else math.fsum(depths) / 3
    fans = []
    if not reasons:
        for proof in edge_proofs:
            start, end = proof["start_xz_m"], proof["end_xz_m"]
            edge_depth = proof["depth_coefficients_m_t01"]
            fan_xz = [center.tolist(), start, end]
            fan_depth = [center_depth, edge_depth[0], edge_depth[0] + edge_depth[1]]
            if min(fan_depth) < 0:
                reasons.add("negative_fan_depth")
                break
            if max(fan_depth) > parameters["max_cut_m"] + parameters["conflict_tolerance_m"]:
                reasons.add("fan_cut_depth_exceeded")
                break
            local = np.asarray(fan_xz) - center
            matrix = np.column_stack((np.ones(3), local))
            try:
                coefficients = np.linalg.solve(matrix, np.asarray(fan_depth))
                patches = _patch_polygons(context, fan_xz)
            except (ValueError, np.linalg.LinAlgError) as error:
                reasons.add("fan_source_or_geometry_refused:" + str(error))
                break
            fans.append({"fan_id": triangle["triangle_id"] + ":fan:" + str(len(fans)),
                         "vertices_xz_m": fan_xz, "depth_at_vertices_m": fan_depth,
                         "depth_origin_xz_m": center.tolist(),
                         "depth_coefficients_m_1xz": coefficients.tolist(),
                         "boundary_segment_id": proof["segment_id"], "native_patches": patches})
    projected_area = abs(float(np.linalg.det(np.column_stack((vertices[1, [0, 2]] - vertices[0, [0, 2]],
                                                              vertices[2, [0, 2]] - vertices[0, [0, 2]]))))) / 2
    fan_area = math.fsum(patch["projected_area_m2"] for fan in fans for patch in fan["native_patches"])
    if not reasons and abs(fan_area - projected_area) > max(1e-10, projected_area * 1e-9):
        reasons.add("fan_area_coverage_incomplete")
    return _seal({"kind": "source_relative_triangle_function", "triangle_id": triangle["triangle_id"],
        "original_triangle": triangle, "original_vertex_source_samples": samples,
        "original_vertex_cut_depth_m": depths, "center_source_sample": center_sample,
        "center_cut_depth_m": center_depth, "center_rule": "arithmetic_mean_original_vertex_cut_depths",
        "fans": fans, "projected_area_m2": projected_area, "fan_projected_area_m2": fan_area,
        "expression": "native_bilinear_source_minus_piecewise_affine_nonnegative_cut_depth",
        "old_edge_function_may_change": True, "status": "refused" if reasons else "candidate",
        "rejection_reasons": sorted(reasons)})


def evaluate_bank_function(function, x_m, z_m, source_height_m):
    if function["status"] != "candidate":
        raise ValueError("refused function cannot be evaluated")
    values = []
    for fan in function["fans"]:
        points = np.array([[point[0], 0., point[1]] for point in fan["vertices_xz_m"]])
        weights = _weights(points, x_m, z_m)
        if weights is not None:
            depth = float(weights @ np.asarray(fan["depth_at_vertices_m"]))
            values.append((depth, fan["fan_id"]))
    if not values or max(value[0] for value in values) - min(value[0] for value in values) > FUNCTION_TOLERANCE_M:
        raise ValueError("fan coverage or internal depth continuity failed")
    depth, fan_id = values[0]
    if depth < 0:
        raise ValueError("negative evaluated cut depth")
    return {"bed_m": float(source_height_m - depth), "cut_depth_m": depth, "fan_id": fan_id,
            "function_identity_sha256": function["identity_sha256"]}


def _connection_queue(transitions, paths, sections, readiness, component_by_triangle, components):
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
    graph = defaultdict(list)
    engineering = {identifier for identifier, node in nodes.items() if "engineering" in node["kinds"]}
    for arc in arcs.values():
        for first, second in zip(arc["node_ids"], arc["node_ids"][1:]):
            if first in nodes and second in nodes:
                graph[first].append((second, arc["arc_id"]))
                graph[second].append((first, arc["arc_id"]))
    parents = {}
    pending = deque(sorted(engineering))
    for identifier in engineering:
        parents[identifier] = None
    while pending:
        identifier = pending.popleft()
        for neighbor, arc_id in sorted(graph[identifier]):
            if neighbor not in parents:
                parents[neighbor] = (identifier, arc_id)
                pending.append(neighbor)
    requests = {item["entry_id"]: item for item in readiness["requests"]}
    node_sections = {item["node_id"]: (index, item) for index, item in enumerate(sections.get("node_sections", []))}
    rows = []
    for entry_index, entry in enumerate(transitions["entries"]):
        previous = requests.get(entry["entry_id"], {"status": "unknown_parent_readiness"})
        if previous["status"] not in {"parent_refused", "pending"}:
            continue
        actual_arc = arcs.get(entry["entry_id"])
        node_ids = actual_arc["node_ids"] if actual_arc is not None else []
        chain = []
        reachable = next((identifier for identifier in node_ids if identifier in parents), None)
        node_walk = [] if reachable is None else [reachable]
        while reachable is not None and parents[reachable] is not None:
            reachable, arc_id = parents[reachable]
            chain.append(arc_id)
            node_walk.append(reachable)
        affected = sorted({component for identifier, component in component_by_triangle.items()
                           if identifier.startswith(f"09:{entry_index}:")})
        reasons = list(entry.get("rejection_reasons", [])) if entry["status"] != "candidate" else list(previous.get("cell_refusals", {}))
        component_reasons = sorted({reason for component in affected for reason in components[component]["rejection_reasons"]})
        classification = ("missing_geometry_parent" if entry["status"] != "candidate" else
                          "source_conforming_candidate" if affected and all(components[item]["status"] == "candidate" for item in affected)
                          else "shared_function_or_source_gate_pending")
        source_node_ids = sorted(set(node_ids).union(
            entry[name] for name in ("upstream_node_id", "anchor_node_id", "wet_node_id") if name in entry))
        flow_references = []
        for node_id in source_node_ids:
            if node_id in node_sections:
                section_index, section = node_sections[node_id]
                flow_references.append({"node_id": node_id, "source_node_section_index": section_index,
                    "representative_q_m3_s": section.get("representative_q_m3_s"),
                    "local_runoff_q_m3_s": section.get("local_runoff_q_m3_s"),
                    "incoming_exchange_q_m3_s": section.get("incoming_exchange_q_m3_s"),
                    "ordinary_identity_sha256": sections.get("ordinary_identity_sha256"),
                    "semantics": "unchanged ordinary-event mean proxy, not instantaneous Q"})
        rows.append({"entry_id": entry["entry_id"], "source_entry_index": entry_index,
                     "parent_status": previous["status"], "parent_reasons": reasons,
                     "parent_reason_class": ("ambiguous_or_missing_port" if "missing_or_ambiguous_accepted_port" in reasons else
                                             "ambiguous_or_missing_land_predecessor" if "missing_or_ambiguous_land_predecessor" in reasons else
                                             "engineering_boundary" if "engineering_boundary_contact" in reasons else "saved_cell_gate"),
                     "classification": classification, "component_ids": affected,
                     "v2_rejection_reasons": component_reasons, "actual_entry_arc_id": None if actual_arc is None else actual_arc["arc_id"],
                     "actual_node_ids": node_ids, "actual_support_path_to_engineering_arc_ids": chain,
                     "actual_support_path_to_engineering_node_ids": node_walk,
                     "source_node_references": [deepcopy(nodes[node_id]) for node_id in source_node_ids if node_id in nodes],
                     "source_arc_reference": deepcopy(actual_arc), "ordinary_flow_references": flow_references,
                     "accepted_port_arc_reference": deepcopy(arcs.get(entry.get("accepted_port_arc_id"))),
                     "land_arc_reference": deepcopy(arcs.get(entry.get("land_arc_id"))),
                     "flow_reference_missing": not flow_references,
                     "undirected_support_reaches_engineering": bool(node_walk),
                     "directed_hydraulic_connection_proved": False, "fabricated_arc_count": 0})
    rows.sort(key=lambda item: (not item["undirected_support_reaches_engineering"],
                                item["classification"] != "source_conforming_candidate", item["entry_id"]))
    return _seal({"schema": SCHEMA + "-connection-queue", "requests": rows,
                  "paths_identity_sha256": paths["identity_sha256"], "sections_identity_sha256": sections["identity_sha256"],
                  "transitions_identity_sha256": transitions["identity_sha256"],
                  "semantics": "priority uses actual undirected support graph, not a proved river or downstream flow",
                  "parent_status_counts": dict(Counter(item["parent_status"] for item in rows)),
                  **{flag: False for flag in FLAGS}})


def _chunks(kind, records, max_bytes, parent_identity):
    chunks, current, size = [], [], 1024
    for record in records:
        length = _record_bytes(record) + 1
        if length + 1024 > max_bytes:
            raise MemoryError("single " + kind + " record exceeds shard budget")
        if current and (size + length > max_bytes or len(current) >= 2048):
            chunks.append(_seal({"schema": SCHEMA + "-" + kind, "parent_identity_sha256": parent_identity,
                                 "chunk_id": kind + "-" + str(len(chunks)).zfill(4), "records": current}))
            current, size = [], 1024
        current.append(record)
        size += length
    if current:
        chunks.append(_seal({"schema": SCHEMA + "-" + kind, "parent_identity_sha256": parent_identity,
                             "chunk_id": kind + "-" + str(len(chunks)).zfill(4), "records": current}))
    return chunks


def build_source_conforming_banks(base, shard_package, hierarchy, sections, transitions, paths, readiness, *,
                                  input_pins=None, max_cells=MAX_CELLS, max_shard_bytes=MAX_BYTES,
                                  resource_check=None):
    """Reuse saved centers. Reject a whole changed component if any gate fails."""
    if (type(max_cells) is not int or not 1 <= max_cells <= MAX_CELLS
            or type(max_shard_bytes) is not int or not 4096 <= max_shard_bytes <= MAX_BYTES):
        raise ValueError("invalid source-conforming resource budget")
    _rss_guard(resource_check, phase="parent_linkage")
    for name, record in (("hierarchy", hierarchy), ("sections", sections), ("transitions", transitions)):
        if base[name + "_identity_sha256"] != record["identity_sha256"]:
            raise ValueError("immutable " + name + " linkage mismatch")
    if (paths["identity_sha256"] != transitions["paths_identity_sha256"]
            or shard_package["manifest"]["base_identity_sha256"] != base["identity_sha256"]
            or base["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("immutable source/paths/shards linkage mismatch")
    parent_identity = shard_package["manifest"]["identity_sha256"]
    context = _context(hierarchy, base["selected_leaf_ids"], base["wet_protection"])
    cells = {key: (cell, owner) for key, cell, owner in iter_merged_cells(base, shard_package["shards"])}
    if len(cells) > max_cells:
        raise MemoryError("merged parent exceeds unique-cell budget")
    _rss_guard(resource_check, phase="readonly_parent_cells", counters={"cells": len(cells)})
    triangles = {item["triangle_id"]: item for item in base["triangles"]}
    triangles.update({item["triangle_id"]: item for item in shard_package["raw"]["triangles"]})
    if len(triangles) != len(base["triangles"]):
        raise ValueError("parent triangle indices are duplicated or shard raw introduced new triangles")
    for triangle in triangles.values():
        mesh = sections["mesh"] if triangle["source_package"] == "06" else transitions["entries"][triangle["source_entry_index"]]
        original_indices = mesh["triangles"][triangle["source_triangle_index"]]
        if (original_indices != triangle["source_vertex_indices"]
                or [mesh["vertices_xyz_m"][index] for index in original_indices] != triangle["vertices_xyz_m"]):
            raise ValueError("original triangle indices/source XYZ chain mismatch")
    seeds = {proposal["triangle_id"] for cell, owner in cells.values()
             if "fill_without_material" in cell["rejection_reasons"] for proposal in cell["triangle_sources"]}
    if not seeds.issubset(triangles):
        raise ValueError("saved fill proposals missing original provenance")
    groups = defaultdict(list)
    bank_points = {tuple(point) for edge in sections["edge_sections"]
                   for profile in edge.get("cross_section_xyz_m", []) for point in (profile[0], profile[-1])}
    for triangle in triangles.values():
        for edge_index in range(3):
            edge = _edge_record(triangle, edge_index)
            if triangle["source_package"] == "06":
                edge["zero_depth_boundary_eligible"] = all(tuple(point) in bank_points for point in edge["points_xyz_m"])
            else:
                entry = transitions["entries"][triangle["source_entry_index"]]
                first_index = triangle["source_vertex_indices"][edge_index]
                second_index = triangle["source_vertex_indices"][(edge_index + 1) % 3]
                edge["zero_depth_boundary_eligible"] = (
                    first_index % 5 == second_index % 5 and first_index % 5 in (0, 4)
                    or min(first_index, second_index) >= len(entry["vertices_xyz_m"]) - 5)
            groups[_line_key(np.asarray(edge["points_xyz_m"])[:, [0, 2]])].append(edge)
    original_mesh = sections["mesh"]
    for index, indices in enumerate(original_mesh["triangles"]):
        if "06:" + str(index) in triangles:
            continue
        legacy = {"triangle_id": "legacy06:" + str(index),
                  "vertices_xyz_m": [original_mesh["vertices_xyz_m"][vertex] for vertex in indices]}
        for edge_index in range(3):
            edge = _edge_record(legacy, edge_index)
            key = _line_key(np.asarray(edge["points_xyz_m"])[:, [0, 2]])
            if key in groups:
                groups[key].append(edge)
    _rss_guard(resource_check, phase="edge_groups", counters={"groups": len(groups)})
    member_sets = _components(triangles, _iter_segments(groups, context), seeds)
    component_by_triangle = {identifier: component for component, members in member_sets.items() for identifier in members}
    reasons_by_component = defaultdict(set)
    _rss_guard(resource_check, phase="component_selection", counters={"triangles": len(component_by_triangle)})
    proofs = []
    by_triangle = defaultdict(list)
    for segment in _iter_segments(groups, context):
        if not any(side["triangle_id"] in component_by_triangle for side in segment["sides"]):
            continue
        if len(proofs) % 256 == 0:
            _rss_guard(resource_check, phase="selected_proofs", counters={"proofs": len(proofs)})
        proof = _proof(segment, context)
        proofs.append(proof)
        for side in segment["sides"]:
            identifier = side["triangle_id"]
            by_triangle[identifier].append(proof)
            if identifier in component_by_triangle:
                reasons_by_component[component_by_triangle[identifier]].update(proof["rejection_reasons"])
    del groups, bank_points
    gc.collect()
    _rss_guard(resource_check, phase="selected_proofs_complete", counters={"proofs": len(proofs)})
    port_proofs = _port_proofs(transitions, sections, proofs, component_by_triangle, reasons_by_component)
    functions = {}
    for number, identifier in enumerate(sorted(component_by_triangle)):
        if number % 128 == 0:
            _rss_guard(resource_check, phase="raw_functions", counters={"functions": number, "proofs": len(proofs)})
        function = _function(triangles[identifier], by_triangle[identifier], context, base["parameters"])
        functions[identifier] = function
        component = component_by_triangle[identifier]
        reasons_by_component[component].update(function["rejection_reasons"])
        if triangles[identifier]["status"] not in {"rasterized", "no_center_coverage"}:
            reasons_by_component[component].add("parent_triangle_coverage_incomplete")
    context.get("bank_sample_cache", {}).clear()
    context.get("bank_patch_cache", {}).clear()
    del by_triangle
    gc.collect()
    _rss_guard(resource_check, phase="raw_functions_complete", counters={"functions": len(functions)})
    census = Counter(proposal["triangle_id"] for cell, owner in cells.values() for proposal in cell["triangle_sources"])
    for identifier, component in component_by_triangle.items():
        if census[identifier] != triangles[identifier].get("covered_centers", 0):
            reasons_by_component[component].add("saved_triangle_center_census_mismatch")
    affected_cells = [(key, cell, owner) for key, (cell, owner) in cells.items()
                      if any(proposal["triangle_id"] in component_by_triangle for proposal in cell["triangle_sources"])]
    parent_cell_count = len(cells)
    original_fill_count = sum("fill_without_material" in cell["rejection_reasons"] for cell, owner in cells.values())
    del cells, census
    effects = []
    origin, spacing = np.asarray(base["grid"]["origin_m_xz"]), base["grid"]["spacing_m"]
    for number, (key, cell, owner) in enumerate(sorted(affected_cells)):
        if number % 4096 == 0:
            _rss_guard(resource_check, phase="effects", counters={"visited_cells": number, "effects": len(effects)})
        components = {component_by_triangle[proposal["triangle_id"]] for proposal in cell["triangle_sources"]
                      if proposal["triangle_id"] in component_by_triangle}
        if any(reasons_by_component[component] for component in components):
            continue
        point = origin + (np.array([key[1], key[0]]) + base["grid"]["center_offset_cells"]) * spacing
        source_height = cell["source_sample"]["height_m"]
        if source_height is None:
            for component in components:
                reasons_by_component[component].add("saved_source_unknown")
            continue
        proposals = []
        try:
            for original in cell["triangle_sources"]:
                proposal = dict(original)
                if original["triangle_id"] in functions:
                    value = evaluate_bank_function(functions[original["triangle_id"]], float(point[0]), float(point[1]), source_height)
                    proposal["legacy_absolute_bed_m"] = original["bed_m"]
                    proposal.update(value)
                proposals.append(proposal)
            after = _evaluate(cell["source_sample"], proposals, cell["local_index"], base["parameters"])
            if after["status"] != "candidate":
                for component in components:
                    reasons_by_component[component].update("v2_cell_gate:" + reason for reason in after["rejection_reasons"])
                continue
        except ValueError as error:
            for component in components:
                reasons_by_component[component].add("v2_cell_function:" + str(error))
            continue
        before_cut, after_cut = _cut(cell, spacing), _cut(after, spacing)
        effects.append({"global_key_row_column": list(key), "operation": "replace", "logical_owner": owner,
                        "component_ids": sorted(components), "before_sha256": _digest(cell), "cell": after,
                        "before_cut_m3": before_cut, "after_cut_m3": after_cut,
                        "cut_delta_m3": after_cut - before_cut, "source_sample_reused": True})
    changed = True
    while changed:
        changed = False
        for key, cell, owner in affected_cells:
            components = {component_by_triangle[item["triangle_id"]] for item in cell["triangle_sources"]
                          if item["triangle_id"] in component_by_triangle}
            if any(reasons_by_component[component] for component in components):
                for component in components:
                    if not reasons_by_component[component]:
                        reasons_by_component[component].add("overlapping_refused_component")
                        changed = True
    effects = [effect for effect in effects if not any(reasons_by_component[item] for item in effect["component_ids"])]
    components = {component: {"component_id": component, "triangle_ids": members,
        "status": "refused" if reasons_by_component[component] else "candidate",
        "rejection_reasons": sorted(reasons_by_component[component]),
        "seed_triangle_ids": sorted(set(members).intersection(seeds)),
        "union_method": "entire_parent_shared_edge_component_including_T_junction_overlaps"}
        for component, members in member_sets.items()}
    queue = _connection_queue(transitions, paths, sections, readiness, component_by_triangle, components)
    before_ledger = deepcopy(shard_package["manifest"]["material_ledger_merged"])
    delta = _ledger(math.fsum(effect["cut_delta_m3"] for effect in effects))
    after_ledger = {name: before_ledger[name] + delta[name] for name in LEDGER_KEYS}
    package = {"raw": _chunks("raw", list(functions.values()), max_shard_bytes, parent_identity),
               "proofs": _chunks("proofs", proofs + port_proofs, max_shard_bytes, parent_identity),
               "effects": _chunks("effects", effects, max_shard_bytes, parent_identity), "queue": queue}
    package["manifest"] = _seal({"schema": SCHEMA, "algorithm": ALGORITHM, "inputs": dict(input_pins or {}),
        "parent_identity_sha256": parent_identity, "base_identity_sha256": base["identity_sha256"],
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "source_identity_sha256": base["source_identity_sha256"],
        "sections_identity_sha256": sections["identity_sha256"], "transitions_identity_sha256": transitions["identity_sha256"],
        "paths_identity_sha256": paths["identity_sha256"], "grid": deepcopy(base["grid"]),
        "selected_leaf_ids": list(base["selected_leaf_ids"]), "wet_protection": deepcopy(base["wet_protection"]),
        "parameters": deepcopy(base["parameters"]),
        "budgets": {"max_cells": max_cells, "max_shard_bytes": max_shard_bytes, "max_rss_bytes": MAX_RSS},
        "proof_tolerances": {"geometry_m": GEOMETRY_TOLERANCE_M, "function_m": FUNCTION_TOLERANCE_M},
        "components": list(components.values()), "affected_global_keys_row_column": [list(item[0]) for item in sorted(affected_cells)],
        "summary": {"parent_unique_cells": parent_cell_count, "original_fill_refused_cells": original_fill_count,
            "seed_triangles": len(seeds), "affected_triangles": len(functions), "affected_cells": len(affected_cells),
            "replace_cells": len(effects), "unchanged_parent_cells": parent_cell_count - len(effects),
            "candidate_components": sum(item["status"] == "candidate" for item in components.values()),
            "refused_components": sum(item["status"] == "refused" for item in components.values()),
            "center_source_resamples": 0, "new_lattice_cells": 0, "water_solves": 0},
        "material_ledger_parent": before_ledger, "material_ledger_delta": delta, "material_ledger_candidate": after_ledger,
        "chunk_identities": {kind: [chunk["identity_sha256"] for chunk in package[kind]] for kind in ("raw", "proofs", "effects")},
        "queue_identity_sha256": queue["identity_sha256"], "old_mesh_passed": False,
        "old_port_preservation_claimed": False, "independent_audit_passed": False,
        **{flag: False for flag in FLAGS}})
    _rss_guard(resource_check, phase="candidate_chunks_complete")
    validate_source_conforming_banks(package)
    return package


def validate_source_conforming_banks(package, *, base=None, shard_package=None, hierarchy=None):
    """Cold identity/unique-effect/ledger check; independent function audit stays separate."""
    manifest = package["manifest"]
    _check_identity(manifest)
    _check_identity(package["queue"])
    budgets = manifest["budgets"]
    if (manifest["schema"] != SCHEMA or manifest["algorithm"] != ALGORITHM
            or not 1 <= budgets["max_cells"] <= MAX_CELLS
            or not 4096 <= budgets["max_shard_bytes"] <= MAX_BYTES
            or budgets["max_rss_bytes"] != MAX_RSS
            or any(manifest.get(flag) is not False for flag in FLAGS)
            or manifest["old_mesh_passed"] is not False or manifest["independent_audit_passed"] is not False):
        raise ValueError("source-conforming schema/budget/certification mismatch")
    if package["queue"]["identity_sha256"] != manifest["queue_identity_sha256"]:
        raise ValueError("connection queue pin mismatch")
    parents = None
    if base is not None and shard_package is not None:
        if (base["identity_sha256"] != manifest["base_identity_sha256"]
                or shard_package["manifest"]["identity_sha256"] != manifest["parent_identity_sha256"]
                or base["grid"] != manifest["grid"]
                or shard_package["manifest"]["material_ledger_merged"] != manifest["material_ledger_parent"]):
            raise ValueError("cold immutable parent linkage mismatch")
        parents = {key: (cell, owner) for key, cell, owner in iter_merged_cells(base, shard_package["shards"])}
    keys, deltas, functions, edge_proofs = set(), [], {}, {}
    component_by_triangle = {identifier: component for component in manifest["components"] for identifier in component["triangle_ids"]}
    for kind in ("raw", "proofs", "effects"):
        if len(package[kind]) > MAX_FILES or [item["identity_sha256"] for item in package[kind]] != manifest["chunk_identities"][kind]:
            raise ValueError("chunk identity census mismatch")
        for chunk in package[kind]:
            _check_identity(chunk)
            if chunk["parent_identity_sha256"] != manifest["parent_identity_sha256"] or _record_bytes(chunk) > budgets["max_shard_bytes"]:
                raise ValueError("chunk parent pin/byte limit mismatch")
            for record in chunk["records"]:
                if kind == "raw":
                    _check_identity(record)
                    identifier = record["triangle_id"]
                    if identifier in functions or identifier not in component_by_triangle:
                        raise ValueError("duplicate/unselected raw triangle")
                    functions[identifier] = record
                    if record["status"] == "candidate" and any(depth < 0 for fan in record["fans"] for depth in fan["depth_at_vertices_m"]):
                        raise ValueError("negative candidate depth")
                elif kind == "proofs":
                    _check_identity(record)
                    if record["kind"] == "edge_function_proof":
                        if record["segment_id"] in edge_proofs:
                            raise ValueError("duplicate edge proof")
                        edge_proofs[record["segment_id"]] = record
                else:
                    key = tuple(record["global_key_row_column"])
                    if key in keys or record["operation"] != "replace" or not record["source_sample_reused"]:
                        raise ValueError("duplicate/new center transaction")
                    keys.add(key)
                    cell = record["cell"]
                    if any(component_by_triangle[item["triangle_id"]]["status"] != "candidate"
                           for item in cell["triangle_sources"] if item["triangle_id"] in component_by_triangle):
                        raise ValueError("effect applied refused component")
                    if parents is not None:
                        before, owner = parents[key]
                        if (_digest(before) != record["before_sha256"] or owner != record["logical_owner"]
                                or before["source_sample"] != cell["source_sample"]
                                or abs(_cut(before, manifest["grid"]["spacing_m"]) - record["before_cut_m3"]) > 1e-10):
                            raise ValueError("effect parent/source/owner mismatch")
                    cut = _cut(cell, manifest["grid"]["spacing_m"])
                    if (abs(cut - record["after_cut_m3"]) > 1e-10
                            or abs(cut - record["before_cut_m3"] - record["cut_delta_m3"]) > 1e-10):
                        raise ValueError("signed effect material mismatch")
                    deltas.append(record["cut_delta_m3"])
    if set(functions) != set(component_by_triangle) or len(keys) != manifest["summary"]["replace_cells"]:
        raise ValueError("complete affected union/effect census mismatch")
    if len(manifest["affected_global_keys_row_column"]) != manifest["summary"]["affected_cells"]:
        raise ValueError("affected center census mismatch")
    if (manifest["summary"]["parent_unique_cells"] > budgets["max_cells"]
            or not keys.issubset({tuple(key) for key in manifest["affected_global_keys_row_column"]})):
        raise ValueError("effect outside bounded affected union")
    expected_delta = _ledger(math.fsum(deltas))
    for name in LEDGER_KEYS:
        if (abs(expected_delta[name] - manifest["material_ledger_delta"][name]) > 1e-9
                or abs(manifest["material_ledger_parent"][name] + expected_delta[name]
                       - manifest["material_ledger_candidate"][name]) > 1e-9):
            raise ValueError("signed material ledger double count")
    if hierarchy is not None:
        if hierarchy["identity_sha256"] != manifest["hierarchy_identity_sha256"]:
            raise ValueError("cold source identity mismatch")
        context = _context(hierarchy, manifest["selected_leaf_ids"], manifest["wet_protection"])
        for proof in edge_proofs.values():
            expected = _proof({name: proof[name] for name in ("segment_id", "start_xz_m", "end_xz_m", "sides", "depth_support_knots")}, context)
            if proof != expected:
                raise ValueError("cold full edge function proof mismatch")
        for identifier, function in functions.items():
            expected = _function(function["original_triangle"],
                [proof for proof in edge_proofs.values() if any(side["triangle_id"] == identifier for side in proof["sides"])],
                context, manifest["parameters"])
            if expected != function:
                raise ValueError("cold source-relative raw function mismatch")
    return package


def save_source_conforming_banks(package, directory, *, resource_check=None):
    validate_source_conforming_banks(package)
    target = Path(directory)
    if target.exists():
        raise FileExistsError(target)
    files = {"manifest.json": package["manifest"], "connection-queue.json": package["queue"]}
    for kind in ("raw", "proofs", "effects"):
        files.update({kind + "/" + chunk["chunk_id"] + ".json": chunk for chunk in package[kind]})
    if len(files) > MAX_FILES:
        raise MemoryError("source-conforming file count budget exceeded")
    for name, record in files.items():
        _rss_guard(resource_check)
        if _record_bytes(record) > package["manifest"]["budgets"]["max_shard_bytes"]:
            raise MemoryError("new candidate file exceeds bounded byte budget: " + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".source-conforming-", dir=target.parent) as staging:
        staging_path = Path(staging) / "package"
        for name, record in files.items():
            _rss_guard(resource_check)
            _write_record(staging_path / name, record)
        _rss_guard(resource_check)
        staging_path.rename(target)
    return target


def load_source_conforming_banks(directory, *, expected_manifest_sha256, expected_manifest_identity, **parents):
    target = Path(directory)

    def read(path):
        if path.stat().st_size > MAX_BYTES:
            raise MemoryError("saved source-conforming file exceeds 64MiB")
        return json.loads(path.read_bytes())

    if file_sha256(target / "manifest.json") != expected_manifest_sha256:
        raise ValueError("external manifest SHA mismatch")
    manifest = read(target / "manifest.json")
    if manifest["identity_sha256"] != expected_manifest_identity:
        raise ValueError("external manifest identity mismatch")
    package = {"manifest": manifest, "queue": read(target / "connection-queue.json")}
    for kind in ("raw", "proofs", "effects"):
        if len(manifest["chunk_identities"][kind]) > MAX_FILES:
            raise MemoryError("saved chunk count exceeded")
        package[kind] = [read(target / kind / (kind + "-" + str(index).zfill(4) + ".json"))
                         for index in range(len(manifest["chunk_identities"][kind]))]
    return validate_source_conforming_banks(package, **parents)
