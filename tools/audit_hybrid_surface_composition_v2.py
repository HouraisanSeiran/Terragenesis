"""Independent saved identity-trace and surface-composition v2 cold audit."""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import audit_hybrid_surface_composition as previous
from tools.audit_hybrid_river_faces import check_plane, saved_slice_geometry
from tools.hybrid_cave_saved_audit import Solid, manifold_library
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_identity, check_memory, compare, digest, file_sha256,
    load_native, read, read_audit, require)

AUDIT_SCHEMA = "td-hybrid-surface-composition-independent-audit-v2"
SLICE_SCHEMA = "td-hybrid-exact-mesh-plane-slice-v1"
NUMERICAL_POLICY = {
    "version": "identity_cached_mesh_plane-v1",
    "plane": "exact_rational_sign_of_saved_binary64_coordinates_and_plane",
    "intersection": "one_exact_rational_intersection_per_original_unoriented_edge_then_binary64",
    "identity": "original_vertex_or_sorted_original_edge_ids_no_round_bucket_no_snap",
    "regions": "directed_identity_loops_polygonize_winding_holes_and_3D_occupancy_check",
    "coplanar": "oriented_original_facets_closed_trace_and_separate_positive_negative_interior_traces",
    "geometry": "unchanged_saved_Mesh64_no_CrossSection_grid",
    "thresholds": "no_area_or_distance_acceptance_threshold_relaxation"}
NUMERICAL_POLICY_SHA256 = digest(NUMERICAL_POLICY)
POLICY = {**previous.POLICY, "version": "saved-native-halfarm-prism-composition-v2",
    "numerical_slice": NUMERICAL_POLICY_SHA256,
    "failure": "saved_boolean_stage_and_material_before_port_checks_port_failure_preserves_artifacts"}
FROZEN_COMPOSITION_CODE = {
    "terrain_pipeline/hybrid_mesh_plane.py": "ebe155432189c443e8bba0e0ef873873eeb7d4e65d46eaa7756c6877977e23f9",
    "terrain_pipeline/hybrid_surface_composition_v2.py": "9ca048b281f6cbf3fa358d84bed4f9a9df97ebfe9e9b2ec2f66129311e0042bd",
    "tools/prepare_hybrid_surface_composition_v2.py": "c7d47d03afbd4c361d95a58c06468e8546a65ebfd7b2a96e19728907bb81509a",
    "tests/test_hybrid_surface_composition_v2.py": "2e41c913fa454d64598664947dc0e9cc40cb3e95763ac30c7bc011f4bdd7c18c"}
FROZEN_HELPERS = {
    "tools/audit_hybrid_surface_composition.py": "bb655a3a06ae410b22c72810d18a73a5c7b576b809a4ce9d0ef853255337b585"}
ERRORS = (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError)


def rational_vector(values):
    return [Fraction.from_float(float(value)) for value in values]


def dot(first, second):
    return sum(value * other for value, other in zip(first, second))


def cross(first, second):
    return [first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0]]


def independent_triangle_trace(solid, frame):
    origin, normal, transverse = [np.asarray(frame[key], float) for key in
        ("origin_local_xyz_m", "normal_local_xyz", "transverse_unit_xyz")]
    require(all(value.shape == (3,) and np.isfinite(value).all() for value in (origin, normal, transverse)),
            "invalid exact plane frame")
    compare([np.linalg.norm(normal), np.linalg.norm(transverse), normal @ transverse],
            [1., 1., 0.], "exact plane orthonormal frame", atol=1e-12)
    require(normal[1] == transverse[1] == 0., "exact plane must use horizontal normal/transverse")
    anchor, direction, lateral = map(rational_vector, (origin, normal, transverse))
    vertices = [rational_vector(point) for point in solid.vertices]
    distances = [dot([value - base for value, base in zip(point, anchor)], direction) for point in vertices]
    signs = [int(value > 0) - int(value < 0) for value in distances]
    nodes, segments, caps = {}, {}, {}

    def vertex_node(index):
        return save_node("v:" + str(index), [index], vertices[index])

    def save_node(name, indices, point):
        uv = [float(dot([value - base for value, base in zip(point, anchor)], lateral)), float(point[1])]
        nodes[name] = {"node_id": name, "vertex_indices": indices,
                       "point_local_xyz_m": list(map(float, point)), "point_uv_m": uv}
        return name

    for ordinal, indices in enumerate(solid.triangles.tolist()):
        own_signs = [signs[index] for index in indices]
        if min(own_signs) > 0 or max(own_signs) < 0:
            continue
        points = [vertices[index] for index in indices]
        outward = cross([value - base for value, base in zip(points[1], points[0])],
                        [value - base for value, base in zip(points[2], points[0])])
        if own_signs == [0, 0, 0]:
            ids = [vertex_node(index) for index in indices]
            orientation = dot(outward, direction)
            require(orientation != 0, "degenerate coplanar original triangle")
            caps[ordinal] = {"triangle_index": ordinal, "vertex_indices": indices,
                "intersection_node_ids": ids, "polygon_uv_m": [nodes[name]["point_uv_m"] for name in ids],
                "normal_dot_plane": float(orientation),
                "occupied_incident_side": "negative" if orientation > 0 else "positive"}
            continue
        ids = []
        exact_points = {}
        for first, second in zip(indices, indices[1:] + indices[:1]):
            if signs[first] == 0:
                name = vertex_node(first)
                ids.append(name)
                exact_points[name] = vertices[first]
            if signs[first] * signs[second] < 0:
                low, high = sorted((first, second))
                fraction = distances[low] / (distances[low] - distances[high])
                point = [base + fraction * (end - base) for base, end in zip(vertices[low], vertices[high])]
                name = save_node("e:" + str(low) + ":" + str(high), [low, high], point)
                ids.append(name)
                exact_points[name] = point
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2:
            continue
        require(len(ids) == 2, "ambiguous original triangle intersection")
        orientation = dot([end - start for start, end in zip(exact_points[ids[0]], exact_points[ids[1]])],
                          cross(direction, outward))
        require(orientation != 0, "degenerate original slice segment")
        if orientation < 0:
            ids.reverse()
        incident = "both" if min(own_signs) < 0 < max(own_signs) else "positive" if max(own_signs) > 0 else "negative"
        segments[ordinal] = {"triangle_index": ordinal, "vertex_indices": indices,
            "intersection_node_ids": ids, "incident_halfspace": incident,
            "points_local_xyz_m": [nodes[name]["point_local_xyz_m"] for name in ids],
            "points_uv_m": [nodes[name]["point_uv_m"] for name in ids]}
    return nodes, segments, caps, signs


def check_census(saved, expected, key, label):
    require(isinstance(saved, list) and len(saved) == len(expected), label + " census differs")
    actual = {}
    for item in saved:
        name = item[key]
        require(name not in actual and name in expected, label + " duplicate/unknown reference")
        actual[name] = item
        require(item == expected[name], label + " source value/reference differs")


def signed_area(points):
    offsets = np.asarray(points, float) - np.asarray(points[0], float)
    return math.fsum(float(first[0] * second[1] - first[1] * second[0])
                     for first, second in zip(offsets, np.roll(offsets, -1, axis=0))) / 2.


def audit_side_loops(loops, side, nodes, segments):
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize_full, unary_union
    coefficients, supports = Counter(), defaultdict(list)
    for ordinal, segment in segments.items():
        if segment["incident_halfspace"] in (side, "both"):
            first, second = segment["intersection_node_ids"]
            key = tuple(sorted((first, second)))
            coefficients[key] += 1 if key == (first, second) else -1
            supports[key].append(ordinal)
    expected = Counter()
    for key, count in coefficients.items():
        require(abs(count) <= 1, "duplicate/nonmanifold exact identity edge")
        if count:
            expected[key if count > 0 else key[::-1]] += 1
    observed, loop_polygons = Counter(), []
    for loop in loops:
        if loop["side"] != side:
            continue
        ids = loop["node_ids"]
        require(len(ids) >= 3 and len(set(ids)) == len(ids) and all(name in nodes for name in ids),
                "open/repeated/unknown exact loop node")
        edges = list(zip(ids, ids[1:] + ids[:1]))
        observed.update(edges)
        require(loop["triangle_supports"] == [supports[tuple(sorted(edge))] for edge in edges],
                "loop original triangle support differs")
        points = [nodes[name]["point_uv_m"] for name in ids]
        area = signed_area(points)
        compare(loop["signed_area_m2"], area, "loop signed area", atol=max(1e-14, abs(area) * 2e-15))
        polygon = Polygon(points)
        require(polygon.is_valid and polygon.area > 0 and area != 0, "invalid exact loop geometry")
        loop_polygons.append((polygon, 1 if area > 0 else -1))
    require(observed == expected, "loop edges do not exhaust original oriented side trace")
    outgoing, incoming = Counter(edge[0] for edge in expected), Counter(edge[1] for edge in expected)
    require(outgoing == incoming and all(count == 1 for count in outgoing.values()),
            "branched/unclosed exact side trace")
    lines = [LineString([nodes[first]["point_uv_m"], nodes[second]["point_uv_m"]]) for first, second in expected]
    if not lines:
        return Polygon()
    cells, cuts, dangles, invalid = polygonize_full(lines)
    require(cuts.is_empty and dangles.is_empty and invalid.is_empty, "incomplete planar identity arrangement")
    retained = []
    for cell in cells.geoms:
        query = cell.representative_point()
        winding = sum(sign for polygon, sign in loop_polygons if polygon.covers(query))
        require(winding in (0, 1), "invalid oriented hole/component winding")
        if winding:
            retained.append(cell)
    return unary_union(retained)


def polygon_parts(shape):
    require(shape.is_empty or shape.geom_type in ("Polygon", "MultiPolygon"), "nonpolygon slice region")
    return [] if shape.is_empty else [shape] if shape.geom_type == "Polygon" else list(shape.geoms)


def domain_parts(shape):
    from shapely.geometry import GeometryCollection
    from shapely.ops import unary_union
    polygons, lines, points = [], [], []
    pending = [shape]
    while pending:
        item = pending.pop()
        if item.is_empty:
            continue
        if item.geom_type == "Polygon":
            polygons.append(item)
        elif item.geom_type in ("LineString", "LinearRing"):
            lines.append(item)
        elif item.geom_type == "Point":
            points.append(tuple(item.coords[0]))
        elif item.geom_type in ("MultiPolygon", "MultiLineString", "MultiPoint", "GeometryCollection"):
            pending.extend(item.geoms)
        else:
            raise ValueError("unknown saved contact domain dimension")
    return unary_union(polygons), unary_union(lines) if lines else GeometryCollection(), set(points)


def check_shape(record, expected, label, require_contacts=False):
    from shapely.geometry import GeometryCollection, LineString
    from shapely.ops import unary_union
    expected_area, expected_lines, expected_points = domain_parts(expected)
    supplied = saved_slice_geometry(record)
    difference = supplied.symmetric_difference(expected_area).area
    require(difference <= 1e-8, label + " saved components/holes differ from identity trace")
    compare(record["area_m2"], expected_area.area, label + " area", atol=1e-8)
    if require_contacts or "contact_lines_uv_m" in record or "contact_points_uv_m" in record:
        saved_lines = []
        for points in record["contact_lines_uv_m"]:
            values = np.asarray(points, float)
            require(values.ndim == 2 and values.shape[1] == 2 and len(values) >= 2 and np.isfinite(values).all(),
                    label + " invalid contact line")
            line = LineString(values)
            require(line.is_valid and line.length > 0, label + " degenerate contact line")
            saved_lines.append(line)
        lines = unary_union(saved_lines) if saved_lines else GeometryCollection()
        require(lines.equals(expected_lines), label + " contact lines differ from actual zero-area trace")
        saved_points = record["contact_points_uv_m"]
        require(all(len(point) == 2 and all(math.isfinite(value) for value in point) for point in saved_points)
                and len(set(map(tuple, saved_points))) == len(saved_points)
                and set(map(tuple, saved_points)) == expected_points,
                label + " contact points differ from actual zero-area trace")
    else:
        require(expected_lines.is_empty and not expected_points, label + " missing explicit contact domain fields")
    return difference


def audit_exact_slice(record, solid, frame, pin):
    """Return independently verified closed-trace shape and compact source evidence."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    check_identity(record)
    require(record["schema"] == SLICE_SCHEMA and record["mesh_pin"] == pin
            and record["coordinate_convention"] == frame["coordinate_convention"]
            and record["method"] == "original_identity_cached_rational_mesh_plane_no_CrossSection"
            and record["numerical_policy"] == NUMERICAL_POLICY
            and record["numerical_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256,
            "exact slice schema/source/numerical policy binding differs")
    nodes, segments, caps, signs = independent_triangle_trace(solid, frame)
    require(record["vertex_plane_classifications"] == [
        {"vertex_index": index, "sign": sign, "classification_method": "exact_rational"}
        for index, sign in enumerate(signs)], "saved exact vertex signs differ")
    check_census(record["intersection_nodes"], nodes, "node_id", "shared-edge intersection")
    check_census(record["triangle_segments"], segments, "triangle_index", "original segment")
    check_census(record["coplanar_triangle_supports"], caps, "triangle_index", "oriented coplanar facet")
    loops = record["identity_loops"]
    require(all(loop["side"] in ("positive", "negative") for loop in loops), "unknown loop incident side")
    sides = {side: audit_side_loops(loops, side, nodes, segments) for side in ("positive", "negative")}
    require(set(record["one_sided_interior_traces"]) == set(sides), "one-sided slice census differs")
    for side, shape in sides.items():
        check_shape(record["one_sided_interior_traces"][side], shape, side + " trace")
    cap_shape = unary_union([Polygon(item["polygon_uv_m"]) for item in caps.values()])
    actual = unary_union([*sides.values(), cap_shape])
    require(actual.is_valid and record["coplanar_semantics"] ==
            "closed_trace_contains_actual_original_facets_side_occupation_recorded", "invalid coplanar occupancy semantics")
    difference = check_shape(record, actual, "closed exact slice")
    witnesses = record["occupancy_witnesses"]
    parts = polygon_parts(actual)
    holes = [Polygon(hole).difference(actual) for polygon in parts for hole in polygon.interiors]
    holes = [hole for hole in holes if not hole.is_empty]
    require(len(witnesses) == len(parts) + len(holes), "component/hole occupancy witness census differs")
    covered, covered_holes = set(), set()
    for witness in witnesses:
        query = Point(witness["point_uv_m"])
        inside = witness["region"] == "retained_polygon"
        require(inside or witness["region"] == "excluded_hole", "unknown occupancy witness region")
        candidates = [index for index, polygon in enumerate(parts if inside else holes) if polygon.contains(query)]
        visited = covered if inside else covered_holes
        require(len(candidates) == 1 and candidates[0] not in visited, "duplicate/outside occupancy witness")
        visited.add(candidates[0])
        point = np.asarray(frame["origin_local_xyz_m"]) + query.x * np.asarray(frame["transverse_unit_xyz"])
        point[1] = query.y
        compare(witness["point_local_xyz_m"], point, "occupancy witness frame", atol=1e-12)
        if cap_shape.covers(query):
            require(inside and witness["classification"] == "original_oriented_coplanar_boundary_facet"
                    and witness["coplanar_triangle_indices"] == [ordinal for ordinal, cap in caps.items()
                        if Polygon(cap["polygon_uv_m"]).covers(query)],
                    "coplanar occupancy classified as free interior")
        else:
            classification = "original_Mesh64_interior_two_ray_parities" if inside else "original_Mesh64_void_two_ray_parities"
            expected = 1 if inside else 0
            require(witness["classification"] == classification
                    and witness["ray_parities"] == [expected, expected], "missing saved interior/void occupancy evidence")
            require(abs(solid.winding(point) - expected) <= 1e-7, "independent original solid occupancy failed")
    hole_probes = 0
    for polygon in parts:
        for hole in polygon.interiors:
            region = Polygon(hole).difference(actual)
            for empty in polygon_parts(region):
                query = empty.representative_point()
                point = np.asarray(frame["origin_local_xyz_m"]) + query.x * np.asarray(frame["transverse_unit_xyz"])
                point[1] = query.y
                require(not cap_shape.covers(query) and abs(solid.winding(point)) <= 1e-7,
                        "saved hole conceals occupied original solid")
                hole_probes += 1
    check_memory()
    return actual, {"schema": "td-hybrid-exact-slice-independent-evidence-v1", "verified": True,
        "mesh_pin": pin, "slice_identity_sha256": record["identity_sha256"],
        "numerical_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "area_m2": float(actual.area), "symmetric_difference_m2": float(difference),
        "triangle_segments": len(segments), "coplanar_triangles": len(caps),
        "shared_intersection_nodes": len(nodes), "identity_loops": len(loops),
        "component_occupancy_witnesses": len(witnesses), "independent_hole_occupancy_probes": hole_probes,
        "builder_or_slicer_called": False, "coplanar_facets_removed": False}


def audit_port(kind, composition, prisms, geometry, attachments, vdm, meshes, origin, evidence):
    from shapely.geometry import Polygon
    library = manifold_library()
    ordinal = 0 if kind == "sink" else len(vdm["stations"]) - 1
    connection = composition["portal_connections"][kind]
    attachment = attachments["attachments"][kind]
    port = read(attachment["canonical_port_pin"])
    station = vdm["stations"][ordinal]
    require(port["identity_sha256"] == geometry["portal_bindings"][kind]["port_identity_sha256"]
            and connection["original_complete_port_proof"] == attachment["actual_complete_port_proof"]
            and connection["immutable_gallery_station_index"] == ordinal
            and connection["offset_traces_are_diagnostic_only"] is True
            and connection["hydraulic_boundary_certified"] is False
            and connection["full_shared_interface_supported"] is True
            and connection["canonical_whole_piece_witnesses"] == prisms["half_arms"][kind]["canonical_whole_piece_witnesses"],
            "canonical original source/whole-port claim differs")
    distance = previous.audit_canonical_pieces(connection["canonical_whole_piece_witnesses"],
        attachment["actual_complete_port_proof"], prisms["half_arms"][kind]["bottom_triangles"],
        port["flow_unit_xz"], kind, station)
    frame = connection["plane"]
    check_plane(frame, station["origin_xyz_m"], port["flow_unit_xz"], origin)
    ring = np.asarray(station["derived_ring_xyz_m"])
    uv = np.column_stack(((ring[:, [0, 2]] - np.asarray(station["origin_xyz_m"])[[0, 2]])
                         @ np.asarray(frame["transverse_unit_xz"]), ring[:, 1] - origin[1]))
    aperture = Polygon(uv)
    require(aperture.is_valid and aperture.area > 0 and not aperture.interiors, "invalid immutable port")
    compare(connection["gallery_aperture_uv_m"], uv, "immutable whole port", atol=1e-8)

    def checked_slice(record, role, plane, label):
        shape, report = audit_exact_slice(record, meshes[role], plane, {"artifact": role})
        report["source_mesh_pin"] = composition["mesh_pins"][role]
        evidence[label] = report
        return shape

    require(set(connection["exact_solid_slices"]) == {"coupled_cutter", "rock_after", "removed"},
            "whole-port solid slice census differs")
    shapes = {role: checked_slice(record, role, frame, "canonical:" + role)
              for role, record in connection["exact_solid_slices"].items()}
    blocked = aperture.intersection(shapes["rock_after"])
    missing = aperture.difference(shapes["coupled_cutter"])
    compare(connection["exact_blocked_area_m2"], blocked.area, "actual whole-port blockage", atol=1e-8)
    compare(connection["exact_missing_cutter_area_m2"], missing.area, "actual whole-port missing", atol=1e-8)
    check_shape(connection["blocked_domain"], blocked, "blocked port", require_contacts=True)
    check_shape(connection["missing_domain"], missing, "missing port", require_contacts=True)
    evidence["whole_port_metrics"] = {"exact_blocked_area_m2": float(blocked.area),
                                     "exact_missing_cutter_area_m2": float(missing.area)}
    require(blocked.area <= 1e-8 and missing.area <= 1e-8, "actual full port blocked or missing")
    epsilon = min(.001, distance / 16)
    require(connection["epsilon_rule"] == "min_1mm_and_minimum_actual_exterior_support_distance_div16",
            "collar depth policy changed")
    bounds = aperture.bounds
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    basis = np.asarray([frame["transverse_unit_xyz"], frame["vertical_unit_xyz"], frame["normal_local_xyz"]]).T
    center = np.asarray(frame["origin_local_xyz_m"]) + np.asarray(frame["transverse_unit_xyz"]) * ((bounds[0] + bounds[2]) / 2)
    center[1] = (bounds[1] + bounds[3]) / 2
    proof = connection["positive_volume_connection"]
    require(set(proof["sides"]) == {"surface", "gallery"}
            and proof["constructed_by_intersecting_actual_cutters_not_new_excavation"] is True,
            "missing two-sided actual source-volume proof")
    surface_sign = -1. if kind == "sink" else 1.
    side_solids, side_reports = [], {}
    for side, sign, source in (("surface", surface_sign, "surface_cutter"), ("gallery", -surface_sign, "original_cutter")):
        saved = proof["sides"][side]
        role = kind + "_" + side + "_collar"
        require(saved["artifact"] == role and saved["source_solid"] == source and saved["normal_side_sign"] == sign,
                "collar source/orientation differs")
        transform = np.column_stack((basis, center + sign * epsilon / 2 * np.asarray(frame["normal_local_xyz"])))
        compare(saved["slab_width_height_depth_m"], [width, height, epsilon], "collar dimensions", atol=1e-12)
        compare(saved["slab_transform_3x4"], transform, "collar side frame", atol=1e-9)
        slab = library.Manifold.cube([width, height, epsilon], center=True).transform(transform)
        expected = meshes[source].manifold(library) ^ slab
        actual = meshes[role].manifold(library)
        require(actual.volume() > 0 and len(actual.decompose()) == saved["component_count"] == 1
                and previous.volume_difference(expected, actual) <= 1e-7, "collar not actual connected source/slab intersection")
        compare(saved["positive_volume_m3"], actual.volume(), "collar volume", atol=1e-7)
        domain = checked_slice(saved["interface_solid_slice"], role, frame, "collar:" + side)
        gap = aperture.difference(domain)
        compare(saved["whole_aperture_uncovered_area_m2"], gap.area, "whole collar gap", atol=1e-8)
        check_shape(saved["uncovered_domain"], gap, "collar uncovered domain", require_contacts=True)
        require(gap.area <= 1e-8, "whole port not covered by both actual volume collars")
        side_solids.append(actual)
        side_reports[side] = {"mesh_pin": composition["mesh_pins"][role], "volume_m3": float(actual.volume()),
                              "whole_port_gap_m2": float(gap.area), "actual_source_solid": source}
    role = kind + "_connected_collar"
    connected = meshes[role].manifold(library)
    require(proof["connected_collar_artifact"] == role and len(connected.decompose()) == proof["component_count"] == 1
            and previous.volume_difference(connected, side_solids[0] + side_solids[1]) <= 1e-7,
            "source collars not one saved connected volume")
    overlap = float((connected ^ meshes["rock_after"].manifold(library)).volume())
    require(overlap <= 1e-7 and (connected - meshes["coupled_cutter"].manifold(library)).volume() <= 1e-7,
            "collar blocked or outside actual cutter")
    compare(proof["actual_rock_overlap_volume_m3"], overlap, "actual collar rock overlap", atol=1e-7)
    traces = connection["one_sided_diagnostic_traces"]
    require([trace["offset_m"] for trace in traces] == [-epsilon, -epsilon / 2, epsilon / 2, epsilon],
            "offset diagnostics not source-depth-bound")
    for index, trace in enumerate(traces):
        shifted = np.asarray(station["origin_xyz_m"]) + trace["offset_m"] * np.asarray(frame["normal_local_xyz"])
        check_plane(trace["plane"], shifted, port["flow_unit_xz"], origin)
        require(set(trace["solid_slices"]) == set(shapes), "diagnostic solid slice census differs")
        for source, record in trace["solid_slices"].items():
            checked_slice(record, source, trace["plane"], "offset:" + str(index) + ":" + source)
    require(connection["status"] == "verified_geometry_unverified_audit"
            and connection["two_sided_complete_port_verified"] is True and not connection["rejection_reasons"],
            "producer whole-port status disagrees with evidence")
    return {"verified": True, "port_identity_sha256": port["identity_sha256"],
        "canonical_port_pin": attachment["canonical_port_pin"], "two_sided_complete_port_verified": True,
        "exact_blocked_area_m2": float(blocked.area), "exact_missing_cutter_area_m2": float(missing.area),
        "positive_volume_sides": side_reports, "connected_collar_pin": composition["mesh_pins"][role],
        "actual_rock_overlap_volume_m3": overlap, "offset_slices_not_acceptance_basis": True,
        "scope": "local_source_supported_full_port_volume_join_not_whole_link_or_hydraulics"}


def check_code_pins(record):
    require(FROZEN_COMPOSITION_CODE and record["code_sha256"] == FROZEN_COMPOSITION_CODE,
            "composition v2 frozen implementation identity differs")
    for name, sha in {**FROZEN_HELPERS, **previous.FROZEN_COMPOSITION_CODE}.items():
        require(file_sha256(ROOT / name) == sha, "frozen v1 dependency changed: " + name)
    for group in ("code_sha256", "readonly_dependency_code_sha256", "audit_code_sha256"):
        for name, sha in record.get(group, {}).items():
            require(file_sha256(ROOT / name) == sha, "pinned implementation changed: " + name)


def audit(composition_pin):
    record = read(composition_pin)
    require(record["schema"] == "td-hybrid-surface-composition-v2"
            and record["status"] in ("candidate_unverified", "refused")
            and record["boolean_stage_preserved"] is True, "unknown/incomplete composition v2 stage")
    check_code_pins(record)
    inputs = record["inputs"]
    require(set(inputs) == {"geometry", "geometry_audit", "graph", "mesh_pins", "vdm", "surface_attachments",
                           "surface_nodes", "original_source_sampling"}
            and inputs["geometry"]["sha256"] == previous.GEOMETRY_SHA256
            and inputs["geometry_audit"]["sha256"] == previous.GEOMETRY_AUDIT_SHA256, "fixed geometry03 pins differ")
    geometry, old_audit, graph = read(inputs["geometry"]), read_audit(inputs["geometry_audit"]), read(inputs["graph"])
    for parent in (geometry, old_audit):
        for group in ("code_sha256", "readonly_dependency_code_sha256", "audit_code_sha256"):
            for name, sha in parent.get(group, {}).items():
                require(file_sha256(ROOT / name) == sha, "geometry03 implementation changed: " + name)
    require(old_audit["status"] == "passed" and not old_audit["errors"]
            and old_audit["geometry_sha256"] == previous.GEOMETRY_SHA256
            and old_audit["geometry_identity_sha256"] == geometry["identity_sha256"]
            and old_audit["mesh_pins"] == geometry["mesh_pins"] and old_audit["inputs"] == geometry["inputs"]
            and old_audit["actual_portal_connections_verified"] is True
            and old_audit["actual_hydraulic_sections_verified"] is True
            and graph["identity_sha256"] == geometry["graph_identity_sha256"] == record["graph_identity_sha256"]
            and record["geometry_identity_sha256"] == geometry["identity_sha256"], "original accepted geometry chain differs")
    require(inputs["graph"] == geometry["inputs"]["graph"] and inputs["mesh_pins"] == geometry["mesh_pins"]
            and inputs["vdm"] == geometry["vdm_pin"] and inputs["surface_attachments"] == geometry["surface_attachments_pin"]
            and inputs["original_source_sampling"] == geometry["source_sampling_pin"], "immutable sources changed")
    require(record["policy"] == POLICY and record["policy_identity_sha256"] == digest(POLICY)
            and record["numerical_slice_policy"] == NUMERICAL_POLICY
            and record["numerical_slice_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256, "unknown composition/slice policy")
    for flag in ("vdm_moved", "ports_moved", "fill_generated", "native_exact", "fine15_replaced",
                 "independent_audit_passed", "hydraulic_ready", "hydraulic_solved", "full_network_verified"):
        require(record[flag] is False, "prematurely promoted source composition: " + flag)
    require(record["original_sampled_rock_retained_cut_only_not_source_resampling"] is True,
            "original sampled-source repair semantics concealed")
    library = manifold_library()
    require(record["runtime"]["manifold3d"] == "3.5.4"
            and record["runtime"]["manifold3d_binary_sha256"] == file_sha256(library.__file__), "Boolean runtime differs")
    attachments, vdm = read(inputs["surface_attachments"]), read(inputs["vdm"])
    require(inputs["surface_nodes"] == {kind: attachment["surface_node_pin"]
            for kind, attachment in attachments["attachments"].items()}
            and set(inputs["surface_nodes"]) == {"sink", "spring"}, "original half-arm node bindings differ")
    sampling_mismatches = previous.audit_sampling_mismatches(record["original_source_sampling_cut_lookup_mismatches"],
                                                            read(inputs["original_source_sampling"]), attachments)
    originals = {"rock_before": geometry["mesh_pins"]["rock_before"],
                 **{"original_" + role: geometry["mesh_pins"][role] for role in ("cutter", "rock_after", "removed")}}
    base_roles = set(originals) | {"surface_cutter", "coupled_cutter", "rock_after", "removed", "extra_removed"}
    collar_roles = {kind + "_" + side + "_collar" for kind in ("sink", "spring") for side in ("surface", "gallery", "connected")}
    require(base_roles <= set(record["mesh_pins"]) <= base_roles | collar_roles
            and all(record["mesh_pins"][role] == pin for role, pin in originals.items()), "mesh census/source bindings differ")
    checkpoint = read(record["checkpoint_boolean_pin"])
    require(checkpoint["schema"] == "td-hybrid-surface-composition-boolean-checkpoint-v2"
            and checkpoint["status"] == "boolean_stage_unverified" and checkpoint["portal_checks_started"] is False
            and checkpoint["inputs"] == inputs and checkpoint["code_sha256"] == record["code_sha256"]
            and checkpoint["readonly_dependency_code_sha256"] == record["readonly_dependency_code_sha256"]
            and checkpoint["runtime"] == record["runtime"] and checkpoint["material"] == record["material"]
            and checkpoint["numerical_slice_policy"] == NUMERICAL_POLICY
            and checkpoint["numerical_slice_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256,
            "Boolean checkpoint source/material/policy binding differs")
    stage = checkpoint["composition_stage"]
    check_identity(stage)
    require(stage["schema"] == record["schema"] and stage["status"] == "boolean_stage_unverified"
            and not stage["rejection_reasons"], "unknown Boolean composition stage")
    for field in ("policy", "policy_identity_sha256", "numerical_slice_policy", "numerical_slice_policy_identity_sha256",
                  "geometry_identity_sha256", "graph_identity_sha256", "material", "coupled_cutter_component_count",
                  "original_source_sampling_cut_lookup_mismatches"):
        require(stage[field] == record[field], "Boolean/final composition field differs: " + field)
    artifacts = checkpoint["artifacts"]
    require(set(artifacts) == (base_roles - set(originals)) | {"surface_prisms"}
            and artifacts["surface_prisms"] == record["surface_prisms_pin"]
            and all(artifacts[role] == record["mesh_pins"][role] for role in base_roles - set(originals)),
            "Boolean checkpoint artifact pins differ")
    meshes, origin = {}, None
    for role, pin in record["mesh_pins"].items():
        mesh = read(pin)
        current = np.asarray(mesh["local_origin_xyz_m"], float)
        require(current.shape == (3,) and np.isfinite(current).all(), "invalid local solid origin")
        if origin is None:
            origin = current
        require(np.array_equal(current, origin), "solids do not share original local origin")
        expected_role = role.removeprefix("original_")
        require(mesh["role"] == expected_role, "saved solid role differs")
        if mesh["schema"] == "td-hybrid-empty-solid-v1":
            require(role == "extra_removed" and mesh["vertices_local_xyz_m"] == []
                    and mesh["triangles"] == [] and mesh["signed_volume_m3"] == 0., "invalid empty solid")
            meshes[role] = previous.EmptySolid()
        else:
            require(mesh["schema"] == "td-hybrid-local-solid-mesh-v1", "unknown solid schema")
            meshes[role] = Solid(mesh["vertices_local_xyz_m"], mesh["triangles"], role)
            compare(mesh["signed_volume_m3"], meshes[role].signed_volume, "saved actual solid volume", atol=1e-7, rtol=1e-9)
    sections = read(geometry["inputs"]["original_06_sections"])
    protection = read(geometry["inputs"]["original_wet_protection_manifest"])["wet_protection"]
    native = load_native(geometry["inputs"]["original_hierarchy"], sections["selected_leaf_ids"], protection)
    prisms = read(record["surface_prisms_pin"])
    _, source_reports = previous.audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    material = previous.audit_material_solids(*(meshes[key] for key in ("rock_before", "original_rock_after", "original_removed",
        "surface_cutter", "coupled_cutter", "rock_after", "extra_removed", "removed", "original_cutter")))
    saved = record["material"]
    for key, expected in (("original_rock_before_m3", meshes["rock_before"].signed_volume),
            ("original_rock_after_m3", meshes["original_rock_after"].signed_volume),
            ("new_rock_after_m3", meshes["rock_after"].signed_volume),
            *((key, material[key]) for key in ("original_removed_m3", "extra_removed_m3", "total_removed_m3"))):
        compare(saved[key], expected, "saved material " + key, atol=1e-7, rtol=1e-9)
    residuals = [saved["original_rock_before_m3"] - saved["original_rock_after_m3"] - saved["original_removed_m3"],
                 saved["original_rock_before_m3"] - saved["new_rock_after_m3"] - saved["total_removed_m3"],
                 saved["total_removed_m3"] - saved["original_removed_m3"] - saved["extra_removed_m3"]]
    compare(saved["signed_residuals_m3"], residuals, "signed material residuals", atol=1e-7)
    require(saved["fill_m3"] == 0. and saved["fine15_material_replaced"] is False
            and saved["sampled_solid_material_not_native_exact"] is True
            and abs(saved["residual_tolerance_m3"] - material["comparison_tolerance_m3"]) <= 1e-12,
            "material semantics or tolerance changed")
    errors, portal_reports, evidence = [], {}, {}
    if len(meshes["coupled_cutter"].manifold(library).decompose()) != record["coupled_cutter_component_count"] or record["coupled_cutter_component_count"] != 1:
        errors.append("actual coupled cutter not one component")
    require(set(record["portal_connections"]) == {"sink", "spring"}, "missing canonical ports")
    for kind in ("sink", "spring"):
        evidence[kind] = {}
        try:
            portal_reports[kind] = audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, evidence[kind])
        except ERRORS as error:
            errors.append(kind + ": " + str(error))
            portal_reports[kind] = {"verified": False, "two_sided_complete_port_verified": False, "errors": [str(error)]}
    if record["status"] != "candidate_unverified" or record["rejection_reasons"]:
        errors.append("producer refused composition: " + "; ".join(record["rejection_reasons"]))
    verified = not errors
    return {"schema": AUDIT_SCHEMA, "status": "passed" if verified else "refused", "errors": errors,
        "composition_pin": composition_pin, "composition_identity_sha256": record["identity_sha256"], "inputs": inputs,
        "mesh_pins": record["mesh_pins"], "surface_prisms_pin": record["surface_prisms_pin"],
        "checkpoint_boolean_pin": record["checkpoint_boolean_pin"], "geometry_sha256": previous.GEOMETRY_SHA256,
        "policy_identity_sha256": digest(POLICY), "numerical_slice_policy": NUMERICAL_POLICY,
        "numerical_slice_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "native_half_arm_sources_verified": True, "source_reports": source_reports,
        "original_source_sampling_cut_lookup_mismatches": sampling_mismatches,
        "materials_verified": True, "material": material, "portal_reports": portal_reports,
        "exact_slice_reports": evidence, "two_sided_complete_port_verified": verified,
        "hydraulic_constitutive_law_accepted": False, "hydraulic_solved": False, "native_exact": False,
        "fine15_replaced": False, "original_sampling_defects_revalidated_as_correct": False,
        "whole_link_control_sill_verified": False, "builder_or_slicer_called": False,
        "scope": "source_bound_piecewise_planar_carve_material_and_local_full_port_connections_only",
        "tolerances": {"canonical_boundary_m": 1e-8, "whole_port_gap_area_m2": 1e-8, "collar_boolean_difference_m3": 1e-7}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--composition-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification audit file required")
    pin = {"path": str(args.composition.resolve()), "sha256": args.composition_sha256}
    started = time.monotonic()
    try:
        report = audit(pin)
    except ERRORS as error:
        report = {"schema": AUDIT_SCHEMA, "status": "refused", "errors": [str(error)], "composition_pin": pin,
            "materials_verified": False, "native_half_arm_sources_verified": False, "two_sided_complete_port_verified": False,
            "hydraulic_constitutive_law_accepted": False, "hydraulic_solved": False}
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory(),
        "solver_calls": 0, "source_artifacts_modified": False}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_surface_composition_v2.py", "tests/test_hybrid_surface_composition_v2_saved_audit.py",
        "tools/audit_hybrid_surface_composition.py", "tools/audit_hybrid_river_faces.py",
        "tools/hybrid_cave_saved_audit.py", "tools/td_shared_channel_fine_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "audit report exceeds 64MiB")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"status": report["status"], "errors": report["errors"], "output": str(output),
        "sha256": file_sha256(output), "two_sided_complete_port_verified": report["two_sided_complete_port_verified"]}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
