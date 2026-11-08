"""Identity-cached rational mesh/plane intersections without CrossSection quantization."""

from collections import defaultdict
from fractions import Fraction
import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize_full, unary_union

from terrain_pipeline.hybrid_river_faces import guard, seal
from terrain_pipeline.hybrid_river_graph import identity

NUMERICAL_POLICY = {"version": "identity_cached_mesh_plane-v1",
    "plane": "exact_rational_sign_of_saved_binary64_coordinates_and_plane",
    "intersection": "one_exact_rational_intersection_per_original_unoriented_edge_then_binary64",
    "identity": "original_vertex_or_sorted_original_edge_ids_no_round_bucket_no_snap",
    "regions": "directed_identity_loops_polygonize_winding_holes_and_3D_occupancy_check",
    "coplanar": "oriented_original_facets_closed_trace_and_separate_positive_negative_interior_traces",
    "geometry": "unchanged_saved_Mesh64_no_CrossSection_grid",
    "thresholds": "no_area_or_distance_acceptance_threshold_relaxation"}
NUMERICAL_POLICY_SHA256 = identity(NUMERICAL_POLICY)


def _fraction(value):
    return Fraction(float(value))


def _intersection_data(points, triangles, frame):
    points, triangles = np.asarray(points, float), np.asarray(triangles, int)
    if (points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all()
            or triangles.ndim != 2 or triangles.shape[1] != 3 or len(triangles) > 200000
            or (len(triangles) and (triangles.min() < 0 or triangles.max() >= len(points)))):
        raise ValueError("invalid_exact_slice_mesh")
    origin = list(map(_fraction, frame["origin_local_xyz_m"]))
    normal = list(map(_fraction, frame["normal_local_xyz"]))
    transverse = list(map(_fraction, frame["transverse_unit_xyz"]))
    active_axes = [axis for axis, value in enumerate(normal) if value]
    distances = [sum(normal[axis] * (_fraction(point[axis]) - origin[axis]) for axis in active_axes) for point in points]
    signs = [int(value > 0) - int(value < 0) for value in distances]
    nodes, segments, coplanar = {}, [], []

    def node(vertex=None, edge=None):
        node_id = "v:" + str(vertex) if vertex is not None else "e:" + ":".join(map(str, edge))
        if node_id not in nodes:
            if vertex is not None:
                rational = list(map(_fraction, points[vertex]))
                references = [vertex]
            else:
                first, second = edge
                fraction = distances[first] / (distances[first] - distances[second])
                rational = [_fraction(points[first, axis]) + fraction *
                    (_fraction(points[second, axis]) - _fraction(points[first, axis])) for axis in range(3)]
                references = list(edge)
            uv = [float(sum(transverse[axis] * (rational[axis] - origin[axis]) for axis in range(3))), float(rational[1])]
            nodes[node_id] = {"node_id": node_id, "vertex_indices": references,
                "point_local_xyz_m": list(map(float, rational)), "point_uv_m": uv}
        return node_id

    for ordinal, triangle in enumerate(triangles):
        values = [signs[index] for index in triangle]
        if min(values) > 0 or max(values) < 0:
            continue
        vertices = points[triangle]
        outward = np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
        if np.linalg.norm(outward) == 0:
            raise ValueError("degenerate_exact_slice_triangle")
        if not any(values):
            ids = [node(vertex=int(index)) for index in triangle]
            uv = [nodes[index]["point_uv_m"] for index in ids]
            rational_edges = [[_fraction(vertices[index, axis]) - _fraction(vertices[0, axis]) for axis in range(3)]
                for index in (1, 2)]
            first, second = rational_edges
            rational_outward = [first[1] * second[2] - first[2] * second[1],
                first[2] * second[0] - first[0] * second[2], first[0] * second[1] - first[1] * second[0]]
            dot = sum(value * direction for value, direction in zip(rational_outward, normal))
            if dot == 0:
                raise ValueError("degenerate_coplanar_facet_orientation")
            coplanar.append({"triangle_index": ordinal, "vertex_indices": triangle.tolist(),
                "intersection_node_ids": ids, "polygon_uv_m": uv, "normal_dot_plane": float(dot),
                "occupied_incident_side": "negative" if dot > 0 else "positive"})
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
            raise ValueError("ambiguous_exact_triangle_plane_intersection")
        tangent = np.cross(np.asarray(frame["normal_local_xyz"]), outward)
        delta = np.asarray(nodes[ids[1]]["point_local_xyz_m"]) - nodes[ids[0]]["point_local_xyz_m"]
        orientation = float(delta @ tangent)
        if orientation == 0:
            raise ValueError("degenerate_projected_exact_segment")
        if orientation < 0:
            ids.reverse()
        incident = "both" if min(values) < 0 < max(values) else "positive" if max(values) > 0 else "negative"
        segments.append({"triangle_index": ordinal, "vertex_indices": triangle.tolist(),
            "intersection_node_ids": ids, "incident_halfspace": incident,
            "points_local_xyz_m": [nodes[index]["point_local_xyz_m"] for index in ids],
            "points_uv_m": [nodes[index]["point_uv_m"] for index in ids]})
    return nodes, segments, coplanar, signs


def triangle_supports(points, triangles, frame):
    _, segments, coplanar, _ = _intersection_data(points, triangles, frame)
    return segments, coplanar


def _side_region(nodes, segments, side):
    edges, supports = {}, defaultdict(list)
    for segment in segments:
        if segment["incident_halfspace"] not in (side, "both"):
            continue
        first, second = segment["intersection_node_ids"]
        key = tuple(sorted((first, second)))
        direction = 1 if key == (first, second) else -1
        edges[key] = edges.get(key, 0) + direction
        supports[key].append(segment["triangle_index"])
    active = []
    for key, count in edges.items():
        if abs(count) > 1:
            raise ValueError("nonmanifold_duplicate_exact_slice_edge")
        if count:
            active.append(key if count > 0 else key[::-1])
    outgoing, incoming = {}, defaultdict(int)
    for first, second in active:
        if first in outgoing:
            raise ValueError("branched_exact_slice_identity_graph")
        outgoing[first] = second
        incoming[second] += 1
    if set(outgoing) != set(incoming) or any(count != 1 for count in incoming.values()):
        raise ValueError("open_or_nonmanifold_exact_slice_identity_graph")
    pending, loops = set(outgoing), []
    while pending:
        start = min(pending)
        current, ids = start, []
        while current in pending:
            pending.remove(current)
            ids.append(current)
            current = outgoing[current]
        if current != start or len(ids) < 3:
            raise ValueError("invalid_exact_identity_loop")
        uv = [nodes[index]["point_uv_m"] for index in ids]
        anchor = np.asarray(uv[0])
        local = np.asarray(uv) - anchor
        area = float(sum(first[0] * second[1] - first[1] * second[0]
            for first, second in zip(local, np.roll(local, -1, axis=0))) / 2.)
        if area == 0 or not Polygon(uv).is_valid:
            raise ValueError("degenerate_or_self_crossing_exact_identity_loop")
        loops.append({"side": side, "node_ids": ids, "signed_area_m2": area,
            "triangle_supports": [supports[tuple(sorted((first, second)))]
                for first, second in zip(ids, ids[1:] + ids[:1])]})
    lines = [LineString([nodes[first]["point_uv_m"], nodes[second]["point_uv_m"]]) for first, second in active]
    if not lines:
        return Polygon(), loops
    cells, cuts, dangles, invalid = polygonize_full(lines)
    if not cuts.is_empty or not dangles.is_empty or not invalid.is_empty:
        raise ValueError("exact_polygonize_incomplete_identity_graph")
    retained = []
    for cell in cells.geoms:
        representative = cell.representative_point()
        winding = sum((1 if loop["signed_area_m2"] > 0 else -1)
            for loop in loops if Polygon([nodes[index]["point_uv_m"] for index in loop["node_ids"]]).covers(representative))
        if winding not in (0, 1):
            raise ValueError("ambiguous_exact_slice_winding")
        if winding:
            retained.append(cell)
    return unary_union(retained), loops


def _polygons(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    if shape.geom_type == "MultiPolygon":
        return list(shape.geoms)
    raise ValueError("unknown_nonpolygon_exact_slice_domain")


def _occupancy(solid, shape, cap_shape, frame, points, coplanar):
    witnesses = []
    extent = float(np.linalg.norm(np.ptp(points, axis=0))) * 4. + 1.
    queries = [(polygon.representative_point(), 1, "retained_polygon") for polygon in _polygons(shape)]
    for polygon in _polygons(shape):
        for hole in polygon.interiors:
            void = Polygon(hole).difference(shape)
            if not void.is_empty:
                queries.append((void.representative_point(), 0, "excluded_hole"))
    for query, expected, region in queries:
        uv = [query.x, query.y]
        local = np.asarray(frame["origin_local_xyz_m"]) + query.x * np.asarray(frame["transverse_unit_xyz"])
        local[1] = query.y
        if cap_shape.covers(query):
            if not expected:
                raise ValueError("coplanar_facet_in_declared_slice_hole")
            witnesses.append({"point_uv_m": uv, "point_local_xyz_m": local.tolist(),
                "classification": "original_oriented_coplanar_boundary_facet", "region": region,
                "coplanar_triangle_indices": [item["triangle_index"] for item in coplanar
                    if Polygon(item["polygon_uv_m"]).covers(query)]})
            continue
        parities = []
        for direction in ([1., .3713906763541037, .5291502622129182], [.239, 1., .617]):
            vector = np.asarray(direction)
            vector /= np.linalg.norm(vector)
            hits = solid.ray_cast(local.tolist(), (local + extent * vector).tolist())
            distances = sorted(set(float(hit.distance) for hit in hits if hit.distance > 0.))
            parities.append(len(distances) % 2)
        if parities != [expected, expected]:
            raise ValueError("exact_slice_3D_occupancy_not_certified")
        witnesses.append({"point_uv_m": uv, "point_local_xyz_m": local.tolist(),
            "classification": "original_Mesh64_interior_two_ray_parities" if expected else "original_Mesh64_void_two_ray_parities",
            "region": region, "ray_parities": parities})
    return witnesses


def slice_solid(solid_data, frame, pin):
    solid, points, triangles = solid_data
    points = np.asarray(points, float)
    nodes, segments, coplanar, signs = _intersection_data(points, triangles, frame)
    positive, positive_loops = _side_region(nodes, segments, "positive")
    negative, negative_loops = _side_region(nodes, segments, "negative")
    cap_shape = unary_union([Polygon(item["polygon_uv_m"]) for item in coplanar])
    shape = unary_union([positive, negative, cap_shape])
    if not shape.is_valid:
        raise ValueError("invalid_exact_mesh_plane_region")
    polygons = _polygons(shape)
    occupancy = _occupancy(solid, shape, cap_shape, frame, points, coplanar)
    record = seal({"schema": "td-hybrid-exact-mesh-plane-slice-v1", "mesh_pin": pin,
        "method": "original_identity_cached_rational_mesh_plane_no_CrossSection",
        "numerical_policy": NUMERICAL_POLICY, "numerical_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "polygons_uv_m": [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons],
        "holes_uv_m": [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in polygons],
        "area_m2": float(shape.area), "triangle_segments": segments, "coplanar_triangle_supports": coplanar,
        "intersection_nodes": list(nodes.values()), "identity_loops": positive_loops + negative_loops,
        "vertex_plane_classifications": [{"vertex_index": ordinal, "sign": sign, "classification_method": "exact_rational"}
            for ordinal, sign in enumerate(signs)],
        "one_sided_interior_traces": {side: {"polygons_uv_m": [list(map(list, polygon.exterior.coords))[:-1]
            for polygon in _polygons(domain)], "holes_uv_m": [[list(map(list, hole.coords))[:-1]
            for hole in polygon.interiors] for polygon in _polygons(domain)], "area_m2": float(domain.area)}
            for side, domain in (("positive", positive), ("negative", negative))},
        "occupancy_witnesses": occupancy, "coplanar_semantics": "closed_trace_contains_actual_original_facets_side_occupation_recorded",
        "coordinate_convention": frame["coordinate_convention"]})
    guard()
    return record, shape
