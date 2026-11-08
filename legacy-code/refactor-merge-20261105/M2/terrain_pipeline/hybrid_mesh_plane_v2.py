"""Rational intersection topology with certified binary64 display projection."""

from collections import defaultdict
from fractions import Fraction
import math

import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from terrain_pipeline.hybrid_mesh_occupancy import _occupancy, _polygons
from terrain_pipeline.hybrid_geometry_common import guard, seal
from terrain_pipeline.hybrid_river_graph import identity

NUMERICAL_POLICY = {"version": "rational_topology_mesh_plane-v2",
    "authority": "saved_binary64_mesh_rational_XYZ_UV_nodes_and_exact_orientation",
    "identity": "original_vertex_and_unoriented_edge_ids_never_merged_or_snapped",
    "display": "consecutive_zero_length_display_edges_only_omitted_with_full_rational_witness",
    "topology": "exact_directed_loops_and_exact_containment_parents_equal_display_hierarchy_or_refused",
    "certificate": "original_1e-8m_distance_and_1e-8m2_area_limits_no_collapsed_positive_area_loop",
    "projection_bound": "exact_rational_L1_distance_and_display_perimeter_with_upward_binary64_ceiling",
    "coplanar": "original_oriented_facets_closed_trace_and_separate_incident_halfspaces",
    "occupancy": "original_Mesh64_two_ray_inside_and_hole_void_checks",
    "geometry": "saved_mesh_unchanged_no_CrossSection_grid"}
NUMERICAL_POLICY_SHA256 = identity(NUMERICAL_POLICY)


def _sub(first, second):
    return [left - right for left, right in zip(first, second)]


def _cross(first, second):
    return [first[1] * second[2] - first[2] * second[1], first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0]]


def _dot(first, second):
    return sum(left * right for left, right in zip(first, second))


def _trace(points, triangles, frame):
    points, triangles = np.asarray(points, float), np.asarray(triangles, int)
    if (points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all()
            or triangles.ndim != 2 or triangles.shape[1] != 3 or len(triangles) > 200000
            or (len(triangles) and (triangles.min() < 0 or triangles.max() >= len(points)))):
        raise ValueError("invalid_rational_slice_mesh")
    rational_points = [list(map(Fraction, point)) for point in points]
    origin, normal, transverse = [list(map(Fraction, frame[name])) for name in
        ("origin_local_xyz_m", "normal_local_xyz", "transverse_unit_xyz")]
    distances = [_dot(normal, _sub(point, origin)) for point in rational_points]
    signs = [int(value > 0) - int(value < 0) for value in distances]
    nodes, segments, caps, collapses = {}, [], [], []

    def node(vertex=None, edge=None):
        node_id = "v:" + str(vertex) if vertex is not None else "e:" + ":".join(map(str, edge))
        if node_id not in nodes:
            if vertex is not None:
                rational = rational_points[vertex]
                references = [vertex]
            else:
                first, second = edge
                fraction = distances[first] / (distances[first] - distances[second])
                rational = [left + fraction * (right - left) for left, right in
                    zip(rational_points[first], rational_points[second])]
                references = list(edge)
            uv = [_dot(transverse, _sub(rational, origin)), rational[1]]
            nodes[node_id] = {"node_id": node_id, "vertex_indices": references,
                "point_local_xyz_m": list(map(float, rational)), "point_uv_m": list(map(float, uv)),
                "rational_xyz_m": list(map(str, rational)), "rational_uv_m": list(map(str, uv))}
        return node_id

    for ordinal, triangle in enumerate(triangles):
        values = [signs[index] for index in triangle]
        if min(values) > 0 or max(values) < 0:
            continue
        vertices = [rational_points[index] for index in triangle]
        outward = _cross(_sub(vertices[1], vertices[0]), _sub(vertices[2], vertices[0]))
        if not any(outward):
            raise ValueError("exact_zero_source_triangle")
        if not any(values):
            ids = [node(vertex=int(index)) for index in triangle]
            orientation = _dot(outward, normal)
            if not orientation:
                raise ValueError("exact_zero_coplanar_orientation")
            caps.append({"triangle_index": ordinal, "vertex_indices": triangle.tolist(), "intersection_node_ids": ids,
                "polygon_uv_m": [nodes[index]["point_uv_m"] for index in ids],
                "normal_dot_plane": float(orientation), "normal_dot_plane_rational": str(orientation),
                "occupied_incident_side": "negative" if orientation > 0 else "positive"})
            continue
        ids = []
        for first, second in zip(triangle, np.roll(triangle, -1)):
            if signs[first] == 0:
                ids.append(node(vertex=int(first)))
            if signs[first] * signs[second] < 0:
                ids.append(node(edge=tuple(sorted((int(first), int(second))))))
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2:
            continue
        if len(ids) != 2:
            raise ValueError("ambiguous_rational_triangle_plane_intersection")
        first, second = [list(map(Fraction, nodes[index]["rational_xyz_m"])) for index in ids]
        orientation = _dot(_sub(second, first), _cross(normal, outward))
        if not orientation:
            raise ValueError("exact_zero_projected_segment")
        if orientation < 0:
            ids.reverse()
        incident = "both" if min(values) < 0 < max(values) else "positive" if max(values) > 0 else "negative"
        segment = {"triangle_index": ordinal, "vertex_indices": triangle.tolist(), "intersection_node_ids": ids,
            "incident_halfspace": incident, "points_local_xyz_m": [nodes[index]["point_local_xyz_m"] for index in ids],
            "points_uv_m": [nodes[index]["point_uv_m"] for index in ids], "orientation_rational": str(orientation),
            "exact_orientation_sign": int(orientation > 0) - int(orientation < 0),
            "orientation_before_reversal_rational": str(orientation),
            "rational_points_xyz_m": [nodes[index]["rational_xyz_m"] for index in ids],
            "rational_points_uv_m": [nodes[index]["rational_uv_m"] for index in ids]}
        segment["orientation_rational"] = str(abs(orientation))
        segment["exact_orientation_sign"] = 1
        segments.append(segment)
        if segment["points_uv_m"][0] == segment["points_uv_m"][1]:
            rational_uv = [list(map(Fraction, nodes[index]["rational_uv_m"])) for index in ids]
            collapses.append({"triangle_index": ordinal, "intersection_node_ids": ids,
                "rational_delta_uv_m": list(map(str, _sub(rational_uv[1], rational_uv[0]))),
                "display_point_uv_m": segment["points_uv_m"][0], "display_omitted_zero_length_only": True,
                "original_segment_and_node_identities_preserved": True})
    return nodes, segments, caps, signs, collapses


def triangle_supports(points, triangles, frame):
    _, segments, caps, _, _ = _trace(points, triangles, frame)
    return segments, caps


def _area(uv):
    return sum(first[0] * second[1] - first[1] * second[0]
        for first, second in zip(uv, uv[1:] + uv[:1])) / 2


def ceil_fraction(value):
    rounded = float(value)
    return math.nextafter(rounded, math.inf) if Fraction(rounded) < value else rounded


def _projection_certificate(rational, displayed):
    displayed = [list(map(Fraction, point)) for point in displayed]
    error = max(sum(abs(left - right) for left, right in zip(exact, display))
        for exact, display in zip(rational, displayed))
    perimeter = sum(sum(abs(left - right) for left, right in zip(first, second))
        for first, second in zip(displayed, displayed[1:] + displayed[:1]))
    bound = 2 * error * perimeter + Fraction(math.nextafter(math.pi, math.inf)) * error**2
    return {"maximum_projection_distance_l1_rational": str(error),
        "display_perimeter_l1_rational": str(perimeter), "projection_area_bound_rational": str(bound),
        "maximum_projection_distance_m": ceil_fraction(error),
        "conservative_projection_area_bound_m2": ceil_fraction(bound),
        "area_error_m2": ceil_fraction(abs(_area(rational) - _area(displayed)))}


def _inside(query, ring):
    winding = 0
    for first, second in zip(ring, ring[1:] + ring[:1]):
        orientation = (second[0] - first[0]) * (query[1] - first[1]) - (second[1] - first[1]) * (query[0] - first[0])
        if not orientation and min(first[0], second[0]) <= query[0] <= max(first[0], second[0]) and min(first[1], second[1]) <= query[1] <= max(first[1], second[1]):
            raise ValueError("ambiguous_exact_hierarchy_boundary_query")
        if first[1] <= query[1] < second[1] and orientation > 0:
            winding += 1
        elif second[1] <= query[1] < first[1] and orientation < 0:
            winding -= 1
    return winding != 0


def _simple_rings(rings):
    edges, bounds = [], []
    for ring_index, ring in enumerate(rings):
        for ordinal, (first, second) in enumerate(zip(ring, ring[1:] + ring[:1])):
            low = [np.nextafter(float(min(first[axis], second[axis])), -np.inf) for axis in range(2)]
            high = [np.nextafter(float(max(first[axis], second[axis])), np.inf) for axis in range(2)]
            edges.append((ring_index, ordinal, first, second))
            bounds.append(box(low[0], low[1], high[0], high[1]))
    if not bounds:
        return
    tree = STRtree(bounds)
    comparisons = 0
    for index, (ring_index, ordinal, first, second) in enumerate(edges):
        for candidate in tree.query(bounds[index]):
            candidate = int(candidate)
            if candidate <= index:
                continue
            other_ring, other_ordinal, third, fourth = edges[candidate]
            if any(max(min(first[axis], second[axis]), min(third[axis], fourth[axis])) >
                    min(max(first[axis], second[axis]), max(third[axis], fourth[axis])) for axis in range(2)):
                continue
            comparisons += 1
            if comparisons > 2000000:
                raise ValueError("whole_rational_intersection_budget_exceeded")
            adjacent = ring_index == other_ring and (ordinal - other_ordinal) % len(rings[ring_index]) in (1, len(rings[ring_index]) - 1)
            if adjacent:
                shared = next((point for point in (first, second) if point in (third, fourth)), None)
                if shared is None:
                    raise ValueError("adjacent_rational_edges_not_shared")
                left = second if first == shared else first
                right = fourth if third == shared else third
                vector_first, vector_second = _sub(left, shared), _sub(right, shared)
                cross = vector_first[0] * vector_second[1] - vector_first[1] * vector_second[0]
                if not cross and _dot(vector_first, vector_second) > 0:
                    raise ValueError("overlapping_adjacent_rational_edges")
                continue
            def orientation(start, end, query):
                return (end[0] - start[0]) * (query[1] - start[1]) - (end[1] - start[1]) * (query[0] - start[0])
            if orientation(first, second, third) * orientation(first, second, fourth) <= 0 and orientation(third, fourth, first) * orientation(third, fourth, second) <= 0:
                raise ValueError("self_crossing_or_touching_rational_loops")


def _side(nodes, segments, side):
    edges, supports = defaultdict(int), defaultdict(list)
    for segment in segments:
        if segment["incident_halfspace"] not in (side, "both"):
            continue
        first, second = segment["intersection_node_ids"]
        key = tuple(sorted((first, second)))
        edges[key] += 1 if key == (first, second) else -1
        supports[key].append(segment["triangle_index"])
    active = []
    for key, count in edges.items():
        if abs(count) > 1:
            raise ValueError("nonmanifold_rational_slice_edge")
        if count:
            active.append(key if count > 0 else key[::-1])
    outgoing, incoming = {}, defaultdict(int)
    for first, second in active:
        if first in outgoing:
            raise ValueError("branched_rational_identity_loop")
        outgoing[first] = second
        incoming[second] += 1
    if set(outgoing) != set(incoming) or any(count != 1 for count in incoming.values()):
        raise ValueError("open_rational_identity_loop")
    pending, loops, rings, displays = set(outgoing), [], [], []
    while pending:
        start, ids = min(pending), []
        current = start
        while current in pending:
            pending.remove(current)
            ids.append(current)
            current = outgoing[current]
        if current != start or len(ids) < 3:
            raise ValueError("invalid_rational_identity_loop")
        rational = [list(map(Fraction, nodes[index]["rational_uv_m"])) for index in ids]
        area = _area(rational)
        if not area:
            raise ValueError("exact_zero_loop_area")
        display_ids = []
        for index in ids:
            if not display_ids or nodes[index]["point_uv_m"] != nodes[display_ids[-1]]["point_uv_m"]:
                display_ids.append(index)
        if len(display_ids) > 1 and nodes[display_ids[-1]]["point_uv_m"] == nodes[display_ids[0]]["point_uv_m"]:
            display_ids.pop()
        display = Polygon([nodes[index]["point_uv_m"] for index in display_ids]) if len(display_ids) >= 3 else Polygon()
        displayed = [list(map(Fraction, nodes[index]["point_uv_m"])) for index in display_ids]
        display_area = _area(displayed) if displayed else Fraction(0)
        certificate = _projection_certificate(rational, [nodes[index]["point_uv_m"] for index in ids])
        error = certificate["maximum_projection_distance_m"]
        area_bound = certificate["conservative_projection_area_bound_m2"]
        if (not display.is_valid or display.is_empty or display.area == 0 or area * display_area <= 0
                or error > 1e-8 or certificate["area_error_m2"] > 1e-8 or area_bound > 1e-8):
            raise ValueError("display_loop_projection_not_certified")
        rings.append(rational)
        displays.append(display)
        loops.append({"side": side, "node_ids": ids, "display_loop_node_ids": display_ids,
            "signed_area_m2": float(area), "signed_area_m2_rational": str(area),
            "display_signed_area_m2_rational": str(display_area), **certificate,
            "triangle_supports": [supports[tuple(sorted((first, second)))] for first, second in zip(ids, ids[1:] + ids[:1])]})
    _simple_rings(rings)
    parents = []
    for ordinal, (ring, display) in enumerate(zip(rings, displays)):
        point = display.representative_point()
        query = [Fraction(point.x), Fraction(point.y)]
        if not _inside(query, ring):
            raise ValueError("display_representative_outside_exact_loop")
        containers = []
        for other, (other_ring, other_display) in enumerate(zip(rings, displays)):
            if other == ordinal:
                continue
            if display.boundary.intersects(other_display.boundary):
                raise ValueError("touching_display_loop_hierarchy_not_certified")
            if abs(_area(other_ring)) <= abs(_area(ring)):
                continue
            exact_inside = _inside(query, other_ring)
            if exact_inside != other_display.contains(point):
                raise ValueError("display_exact_loop_hierarchy_mismatch")
            if exact_inside:
                containers.append(other)
        parent = min(containers, key=lambda index: abs(_area(rings[index]))) if containers else None
        parents.append(parent)
        loops[ordinal].update(containment_query_uv_rational=list(map(str, query)), exact_parent_loop_index=parent,
            display_parent_loop_index=parent, hierarchy_certified=True)
    polygons = []
    for ordinal, loop in enumerate(loops):
        positive = Fraction(loop["signed_area_m2_rational"]) > 0
        parent = parents[ordinal]
        if (parent is None and not positive) or (parent is not None and positive == (Fraction(loops[parent]["signed_area_m2_rational"]) > 0)):
            raise ValueError("invalid_exact_loop_winding_hierarchy")
        if positive:
            holes = [list(displays[index].exterior.coords) for index, value in enumerate(parents)
                if value == ordinal and Fraction(loops[index]["signed_area_m2_rational"]) < 0]
            polygon = Polygon(displays[ordinal].exterior.coords, holes)
            if not polygon.is_valid:
                raise ValueError("invalid_certified_display_polygon")
            polygons.append(polygon)
    return unary_union(polygons), loops


def slice_solid(solid_data, frame, pin):
    solid, points, triangles = solid_data
    nodes, segments, caps, signs, collapses = _trace(points, triangles, frame)
    positive, positive_loops = _side(nodes, segments, "positive")
    negative, negative_loops = _side(nodes, segments, "negative")
    cap_polygons = []
    cap_bound = Fraction(0)
    for cap in caps:
        rational = [list(map(Fraction, nodes[index]["rational_uv_m"])) for index in cap["intersection_node_ids"]]
        display = Polygon(cap["polygon_uv_m"])
        certificate = _projection_certificate(rational, cap["polygon_uv_m"])
        if (not display.is_valid or display.area == 0 or certificate["maximum_projection_distance_m"] > 1e-8
                or certificate["conservative_projection_area_bound_m2"] > 1e-8 or certificate["area_error_m2"] > 1e-8):
            raise ValueError("coplanar_projection_not_certified")
        cap["projection_certificate"] = {"signed_area_m2_rational": str(_area(rational)), **certificate}
        cap_bound += Fraction(certificate["projection_area_bound_rational"])
        cap_polygons.append(display)
    cap_shape = unary_union(cap_polygons)
    shape = unary_union([positive, negative, cap_shape])
    if not shape.is_valid:
        raise ValueError("invalid_rational_closed_trace_display")
    loops = positive_loops + negative_loops
    rational_bound = sum(Fraction(loop["projection_area_bound_rational"]) for loop in loops) + cap_bound
    bound = ceil_fraction(rational_bound)
    if bound > 1e-8:
        raise ValueError("whole_slice_projection_error_bound_exceeded")
    polygons = _polygons(shape)
    record = seal({"schema": "td-hybrid-exact-mesh-plane-slice-v2", "mesh_pin": pin,
        "method": "rational_identity_topology_certified_binary64_display",
        "numerical_policy": NUMERICAL_POLICY, "numerical_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "polygons_uv_m": [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons],
        "holes_uv_m": [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in polygons],
        "area_m2": float(shape.area), "triangle_segments": segments, "coplanar_triangle_supports": caps,
        "intersection_nodes": list(nodes.values()), "identity_loops": loops, "projection_collapse_witnesses": collapses,
        "projection_area_error_bound_m2": bound, "projection_area_error_bound_rational": str(rational_bound),
        "display_projection_certified": True,
        "vertex_plane_classifications": [{"vertex_index": ordinal, "sign": sign, "classification_method": "exact_rational"}
            for ordinal, sign in enumerate(signs)],
        "one_sided_interior_traces": {side: {"polygons_uv_m": [list(map(list, polygon.exterior.coords))[:-1]
            for polygon in _polygons(domain)], "holes_uv_m": [[list(map(list, hole.coords))[:-1]
            for hole in polygon.interiors] for polygon in _polygons(domain)], "area_m2": float(domain.area)}
            for side, domain in (("positive", positive), ("negative", negative))},
        "occupancy_witnesses": _occupancy(solid, shape, cap_shape, frame, np.asarray(points), caps),
        "coplanar_semantics": "closed_trace_retains_original_oriented_facets_no_cap_deletion",
        "coordinate_convention": frame["coordinate_convention"]})
    guard()
    return record, shape
