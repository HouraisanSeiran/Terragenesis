"""Independent saved identity-trace and surface-composition v3 cold audit."""

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
from tools.audit_hybrid_surface_composition import exact_fan_cut, saved_patch_affine_depth, source_patch_height, volume_difference
from tools.audit_hybrid_surface_composition_v2 import NUMERICAL_POLICY as SOURCE_SLICE_POLICY, POLICY as SOURCE_POLICY
from tools.audit_hybrid_river_faces import check_plane, saved_slice_geometry
from tools.hybrid_cave_saved_audit import manifold_library
from tools.hybrid_exact_solid_saved_audit import ExactSolid, SOLID_POLICY, SOLID_POLICY_SHA256
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_identity, check_memory, compare, digest, file_sha256,
    load_native, read, read_audit, require)

Solid = ExactSolid
AUDIT_SCHEMA = "td-hybrid-surface-composition-independent-audit-v3"
SLICE_SCHEMA = "td-hybrid-exact-mesh-plane-slice-v2"
NUMERICAL_POLICY = {
    "version": "rational_topology_mesh_plane-v2",
    "authority": "saved_binary64_mesh_rational_XYZ_UV_nodes_and_exact_orientation",
    "identity": "original_vertex_and_unoriented_edge_ids_never_merged_or_snapped",
    "display": "consecutive_zero_length_display_edges_only_omitted_with_full_rational_witness",
    "topology": "exact_directed_loops_and_exact_containment_parents_equal_display_hierarchy_or_refused",
    "certificate": "original_1e-8m_distance_and_1e-8m2_area_limits_no_collapsed_positive_area_loop",
    "projection_bound": "exact_rational_L1_distance_and_display_perimeter_with_upward_binary64_ceiling",
    "coplanar": "original_oriented_facets_closed_trace_and_separate_incident_halfspaces",
    "occupancy": "original_Mesh64_two_ray_inside_and_hole_void_checks",
    "geometry": "saved_mesh_unchanged_no_CrossSection_grid"}
NUMERICAL_POLICY_SHA256 = digest(NUMERICAL_POLICY)
POLICY = {**previous.POLICY, "version": "saved-stage-rational-surface-composition-v3",
    "numerical_slice": NUMERICAL_POLICY_SHA256,
    "main_boolean": "immutable_composition02_checkpoint_mesh_pins_material_and_extra_removed_not_recomputed",
    "portal_boolean": "bounded_collars_only_reuse_saved_collars_when_available",
    "failure": "saved_stage_lineage_material_and_partial_port_reports_preserved"}
FROZEN_COMPOSITION_CODE = {
    "terrain_pipeline/hybrid_mesh_plane_v2.py": "c08f36980976193961c6869b6c07d2e3d44d313be1ecc7ef9e5fcdbed5ae788c",
    "terrain_pipeline/hybrid_surface_composition_v3.py": "4be72eb2607d47c9d6260a826d3c04d3624c7e31679bc2aa73c086a83c8828ea",
    "tools/prepare_hybrid_surface_composition_v3.py": "6aa37cf6341d078753421caeaee95480a9c335a7b0bb1e3412fd93937dd2cb38",
    "tests/test_hybrid_surface_composition_v3.py": "2a6d40e57c115a74c758010d4c19a70c57d766dec1e8561908e3105e6ecd5a1a"}
FROZEN_HELPERS = {
    "tools/audit_hybrid_surface_composition.py": "bb655a3a06ae410b22c72810d18a73a5c7b576b809a4ce9d0ef853255337b585",
    "tools/audit_hybrid_surface_composition_v2.py": "814c87591f8a6adecc82fab4c170424fa14fc0624d885c28802a09fd091cdf75"}
SOURCE_INDEX_SHA256 = "54f1fe63f8f8ff2b79e5bb7332c97fa76ec77b780abf772ad9245081b45af105"
SOURCE_COMPOSITION_SHA256 = "4ef1ed45bf4bd9b819e267273e622ca6475c4271e6d89672be31396e485f1f1d"
SOURCE_CHECKPOINT_SHA256 = "f84621ff8cecc5e7ef5e33f156c1d7329e998727a21d74d0823cb02207422394"
SOURCE_V2_CODE = {
    "terrain_pipeline/hybrid_mesh_plane.py": "ebe155432189c443e8bba0e0ef873873eeb7d4e65d46eaa7756c6877977e23f9",
    "terrain_pipeline/hybrid_surface_composition_v2.py": "9ca048b281f6cbf3fa358d84bed4f9a9df97ebfe9e9b2ec2f66129311e0042bd",
    "tools/prepare_hybrid_surface_composition_v2.py": "c7d47d03afbd4c361d95a58c06468e8546a65ebfd7b2a96e19728907bb81509a",
    "tests/test_hybrid_surface_composition_v2.py": "2e41c913fa454d64598664947dc0e9cc40cb3e95763ac30c7bc011f4bdd7c18c"}
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
                       "point_local_xyz_m": list(map(float, point)), "point_uv_m": uv,
                       "rational_xyz_m": list(map(str, point)),
                       "rational_uv_m": [str(dot([value - base for value, base in zip(point, anchor)], lateral)), str(point[1])]}
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
                "normal_dot_plane": float(orientation), "normal_dot_plane_rational": str(orientation),
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
            "points_uv_m": [nodes[name]["point_uv_m"] for name in ids],
            "orientation_rational": str(abs(orientation)), "exact_orientation_sign": 1,
            "orientation_before_reversal_rational": str(orientation),
            "rational_points_xyz_m": [nodes[name]["rational_xyz_m"] for name in ids],
            "rational_points_uv_m": [nodes[name]["rational_uv_m"] for name in ids]}
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


def audit_prisms(saved, attachments, vdm, native, origin, meshes):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    require(saved["schema"] == "td-hybrid-surface-prisms-v1" and saved["native_exact"] is False
            and saved["bottom_semantics"] == POLICY["floor"] and set(saved["half_arms"]) == {"sink", "spring"},
            "changed prism source/approximation contract")
    compare(saved["common_local_origin_xyz_m"], origin, "prism shared local origin", atol=0.)
    expected_cap = max(float(meshes[role].vertices[:, 1].max() + origin[1]) for role in ("rock_before", "original_cutter")) + 10.
    require(saved["cap_y_world_m"] == expected_cap and saved["cap_above_saved_rock_and_gallery_margin_m"] == 10.,
            "surface cutter cap not fixed above actual original solids")
    library = manifold_library()
    records, all_prisms, reports = {}, [], {}
    expected_faces = {tuple(sorted(face)) for face in ((0, 2, 1), (3, 4, 5), (0, 1, 4), (0, 4, 3),
                      (1, 2, 5), (1, 5, 4), (2, 0, 3), (2, 3, 5))}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        half = saved["half_arms"][kind]
        attachment = attachments["attachments"][kind]
        node = read(attachment["surface_node_pin"])
        wanted = {"shared:" + node["node_id"] + ":" + str(index) for index in attachment["half_arm_triangle_indices"]}
        functions = {item["triangle_id"]: item for item in node["source_functions"] if item["triangle_id"] in wanted}
        require(set(functions) == wanted and node["status"] == "candidate" and not node["rejection_reasons"]
                and half["node_id"] == node["node_id"] and half["node_pin"] == attachment["surface_node_pin"]
                and half["half_arm_triangle_indices"] == attachment["half_arm_triangle_indices"]
                and half["immutable_gallery_station_index"] == ordinal
                and half["immutable_gallery_ring_xyz_m"] == vdm["stations"][ordinal]["derived_ring_xyz_m"],
                "original whole half-arm/immutable gallery sources differ")
        expected = {}
        for function in functions.values():
            check_identity(function)
            require(function["status"] == "candidate" and not function["rejection_reasons"], "refused original source function")
            for fan in function["fans"]:
                require(fan["fan_id"] not in expected, "duplicate original fan")
                compact = next((item for item in attachment["compact_native_fans"] if item["fan_key"] == fan["fan_id"]), None)
                require(compact is not None and all(compact[key] == fan[key] for key in
                        ("vertices_xz_m", "depth_at_vertices_m", "depth_coefficients_m_1xz", "depth_origin_xz_m")),
                        "original native/compact affine fan mismatch")
                domains = [Polygon(patch["polygon_xz_m"]) for patch in fan["native_patches"]]
                require(all(domain.is_valid and domain.area > 0 for domain in domains)
                        and Polygon(fan["vertices_xz_m"]).symmetric_difference(unary_union(domains)).area <= 1e-8,
                        "original native patch coverage differs from fan domain")
                expected[fan["fan_id"]] = (function, fan)
        coverage = {}
        own = []
        bottoms = half["bottom_triangles"]
        require(bottoms and [item["bottom_triangle_id"] for item in bottoms] == list(range(len(bottoms)))
                and len(bottoms) * 8 <= 200000, "invalid bounded prism triangle census")
        maximum_approximation = 0.
        maximum_bilinear_bound = 0.
        outside_vertex_count = 0
        for item in bottoms:
            require(item["fan_key"] in expected, "surface cutter uses non-half-arm source")
            function, fan = expected[item["fan_key"]]
            require(item["triangle_id"] == function["triangle_id"]
                    and item["source_function_identity_sha256"] == function["identity_sha256"]
                    and item["saved_affine_fan"] == fan and item["saved_native_patch"] in fan["native_patches"]
                    and item["bilinear_interior_is_planar_approximation"] is True,
                    "prism native/fan function substituted or approximation concealed")
            patch = item["saved_native_patch"]
            patch_index = fan["native_patches"].index(patch)
            bottom = np.asarray(item["bottom_vertices_xyz_m"], float)
            require(bottom.shape == (3, 3) and np.isfinite(bottom).all(), "invalid bottom triangle")
            polygon = Polygon(bottom[:, [0, 2]])
            domain = Polygon(patch["polygon_xz_m"])
            require(polygon.is_valid and polygon.area > 0 and polygon.difference(domain).area <= 1e-10,
                    "bottom triangle outside original native patch")
            coverage.setdefault((item["fan_key"], patch_index), []).append(polygon)
            expected_depths = []
            domain_witnesses = []
            for point in bottom:
                horizontal = point[[0, 2]]
                require(any(np.array_equal(horizontal, vertex) for vertex in patch["polygon_xz_m"]),
                        "prism introduced or snapped a saved patch vertex")
                inside = exact_fan_cut(fan, horizontal) is not None
                outside_vertex_count += int(not inside)
                domain_witnesses.append({"point_xz_m": horizontal.tolist(), "inside_original_fan_exact_domain": inside,
                                         "entity_domain_authority": "original_saved_native_patch_polygon",
                                         "clip_point_not_snapped": True})
                depth = saved_patch_affine_depth(fan, horizontal)
                expected_depths.append(depth)
                compare(point[1], source_patch_height(patch, point[[0, 2]], native) - depth,
                        "prism bottom original native minus cut", atol=1e-9)
            compare(item["depth_at_vertices_m"], expected_depths, "strict original affine depths", atol=1e-12)
            require(item["saved_patch_vertex_domain_witnesses"] == domain_witnesses,
                    "exact original fan domain/patch authority witnesses concealed")
            centroid = bottom.mean(axis=0)
            depth = saved_patch_affine_depth(fan, centroid[[0, 2]])
            deviation = source_patch_height(patch, centroid[[0, 2]], native) - depth - centroid[1]
            maximum_approximation = max(maximum_approximation, abs(deviation))
            bilinear_bound = abs(patch["bilinear_coefficients_m"][3]) * np.ptp(bottom[:, 0]) * np.ptp(bottom[:, 2]) / native.spacing**2
            compare(item["conservative_interior_height_error_bound_m"], bilinear_bound,
                    "saved bilinear planar approximation bound", atol=1e-12)
            maximum_bilinear_bound = max(maximum_bilinear_bound, float(bilinear_bound))
            prism = item["prism"]
            check_identity(prism)
            require(prism["schema"] == "td-hybrid-local-solid-mesh-v1"
                    and prism["role"] == "surface_half_arm_closed_triangular_prism"
                    and item["prism_triangle_roles"] == ["floor", "artificial_top_cap"] + ["lateral"] * 6
                    and {tuple(sorted(face)) for face in prism["triangles"]} == expected_faces,
                    "prism closure/source roles differ")
            top = bottom.copy()
            top[:, 1] = expected_cap
            compare(prism["local_origin_xyz_m"], origin, "prism origin", atol=0.)
            compare(prism["vertices_local_xyz_m"], np.vstack((bottom, top)) - origin, "prism actual vertices", atol=1e-9)
            solid = Solid(prism["vertices_local_xyz_m"], prism["triangles"], "source prism")
            compare(prism["signed_volume_m3"], solid.signed_volume, "saved source prism volume", atol=1e-7)
            own.append(solid)
            all_prisms.append(solid.manifold(library))
        for fan_key, (_, fan) in expected.items():
            for patch_index, patch in enumerate(fan["native_patches"]):
                parts = coverage.get((fan_key, patch_index), [])
                domain = Polygon(patch["polygon_xz_m"])
                require(parts and domain.symmetric_difference(unary_union(parts)).area <= 1e-8
                        and abs(sum(part.area for part in parts) - domain.area) <= 1e-8,
                        "missing/overlapping whole native patch prism coverage")
        records[kind] = own
        reports[kind] = {"bottom_triangles": len(bottoms), "original_half_arm_triangles": len(wanted),
                         "native_source_and_saved_patch_affine_function_verified": True,
                         "exact_original_fan_outside_vertex_occurrences": outside_vertex_count,
                         "entity_domain_authority": "original_saved_native_patch_polygon",
                         "max_sampled_centroid_planar_native_difference_m": maximum_approximation,
                         "max_saved_bilinear_component_error_bound_m": maximum_bilinear_bound,
                         "centroid_probe_is_not_global_approximation_bound": True}
        check_memory()
    expected_surface = library.Manifold.batch_boolean(all_prisms, library.OpType.Add)
    tolerance = max(1e-7, expected_surface.volume() * 1e-10)
    require(volume_difference(expected_surface, meshes["surface_cutter"].manifold(library)) <= tolerance,
            "saved surface cutter not union of source-bound closed prisms")
    extra = meshes["extra_removed"].manifold(library)
    require((extra - expected_surface).volume() <= tolerance, "extra removed escapes source-supported prism volume")
    return records, reports


def rational_area(points):
    return sum(first[0] * second[1] - first[1] * second[0]
               for first, second in zip(points, points[1:] + points[:1])) / 2


def ceil_fraction(value):
    rounded = float(value)
    require(math.isfinite(rounded), "nonfinite rational certificate conversion")
    return math.nextafter(rounded, math.inf) if Fraction.from_float(rounded) < value else rounded


def projection_certificate(rational, display_points):
    displayed = [rational_vector(point) for point in display_points]
    require(len(rational) == len(displayed) and len(rational) >= 3, "projection certificate vertex census differs")
    error = max(sum(abs(exact - shown) for exact, shown in zip(point, rounded))
                for point, rounded in zip(rational, displayed))
    perimeter = sum(sum(abs(end - start) for start, end in zip(first, second))
                    for first, second in zip(displayed, displayed[1:] + displayed[:1]))
    bound = 2 * error * perimeter + Fraction.from_float(math.nextafter(math.pi, math.inf)) * error**2
    return {"maximum_projection_distance_l1_rational": str(error), "display_perimeter_l1_rational": str(perimeter),
        "projection_area_bound_rational": str(bound), "maximum_projection_distance_m": ceil_fraction(error),
        "conservative_projection_area_bound_m2": ceil_fraction(bound),
        "area_error_m2": ceil_fraction(abs(rational_area(rational) - rational_area(displayed)))}


def area_upper(area, bound):
    return math.nextafter(math.fsum((float(area), bound)), math.inf)


def planar_turn(first, second, third):
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])


def on_segment(point, first, second):
    return planar_turn(first, second, point) == 0 and all(
        min(start, end) <= value <= max(start, end) for value, start, end in zip(point, first, second))


def segments_meet(first, second, other_first, other_second):
    if any(max(first[axis], second[axis]) < min(other_first[axis], other_second[axis])
           or max(other_first[axis], other_second[axis]) < min(first[axis], second[axis]) for axis in (0, 1)):
        return False
    turns = [planar_turn(first, second, other_first), planar_turn(first, second, other_second),
             planar_turn(other_first, other_second, first), planar_turn(other_first, other_second, second)]
    return (turns[0] * turns[1] < 0 and turns[2] * turns[3] < 0) or any((
        turns[0] == 0 and on_segment(other_first, first, second),
        turns[1] == 0 and on_segment(other_second, first, second),
        turns[2] == 0 and on_segment(first, other_first, other_second),
        turns[3] == 0 and on_segment(second, other_first, other_second)))


def rational_contains(point, ring):
    winding = 0
    for first, second in zip(ring, ring[1:] + ring[:1]):
        require(not on_segment(point, first, second), "exact hierarchy query on original boundary")
        turn = planar_turn(first, second, point)
        if first[1] <= point[1] < second[1] and turn > 0:
            winding += 1
        elif second[1] <= point[1] < first[1] and turn < 0:
            winding -= 1
    require(winding in (-1, 0, 1), "non-simple rational hierarchy winding")
    return winding != 0


def check_rational_boundaries(rings):
    for ordinal, ring in enumerate(rings):
        require(len(set(map(tuple, ring))) == len(ring), "repeated rational loop coordinate")
        edges = list(zip(ring, ring[1:] + ring[:1]))
        for index, (first, second) in enumerate(edges):
            previous = ring[index - 1]
            if planar_turn(previous, first, second) == 0:
                require(dot([value - center for value, center in zip(previous, first)],
                            [value - center for value, center in zip(second, first)]) < 0,
                        "backtracking rational loop boundary")
            for other_index in range(index + 1, len(edges)):
                if other_index == index + 1 or index == 0 and other_index == len(edges) - 1:
                    continue
                require(not segments_meet(first, second, *edges[other_index]), "self-intersecting exact rational loop")
        for other in rings[:ordinal]:
            require(not any(segments_meet(first, second, other_first, other_second)
                            for first, second in edges for other_first, other_second in zip(other, other[1:] + other[:1])),
                    "intersecting/touching exact rational loop hierarchy")


def certified_side(loops, side, nodes, segments):
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    coefficients, supports = Counter(), defaultdict(list)
    for ordinal, segment in segments.items():
        if segment["incident_halfspace"] in (side, "both"):
            first, second = segment["intersection_node_ids"]
            key = tuple(sorted((first, second)))
            coefficients[key] += 1 if key == (first, second) else -1
            supports[key].append(ordinal)
    expected = Counter()
    for key, count in coefficients.items():
        require(abs(count) <= 1, "nonmanifold rational edge census")
        if count:
            expected[key if count > 0 else key[::-1]] += 1
    own_loops = [loop for loop in loops if loop["side"] == side]
    observed, rings, displays, areas, bounds = Counter(), [], [], [], []
    for loop in own_loops:
        ids = loop["node_ids"]
        require(len(ids) >= 3 and len(set(ids)) == len(ids) and all(name in nodes for name in ids),
                "unknown/repeated rational loop identity")
        edges = list(zip(ids, ids[1:] + ids[:1]))
        observed.update(edges)
        require(loop["triangle_supports"] == [supports[tuple(sorted(edge))] for edge in edges],
                "rational loop triangle support differs")
        ring = [list(map(Fraction, nodes[name]["rational_uv_m"])) for name in ids]
        area = rational_area(ring)
        require(area != 0 and loop["signed_area_m2_rational"] == str(area)
                and loop["signed_area_m2"] == float(area), "rational loop area authority differs")
        display_ids = []
        for name in ids:
            if not display_ids or nodes[name]["point_uv_m"] != nodes[display_ids[-1]]["point_uv_m"]:
                display_ids.append(name)
        if len(display_ids) > 1 and nodes[display_ids[-1]]["point_uv_m"] == nodes[display_ids[0]]["point_uv_m"]:
            display_ids.pop()
        require(loop["display_loop_node_ids"] == display_ids and len(display_ids) >= 3,
                "display omission is not consecutive duplicate-only or collapses positive-area loop")
        displayed = [rational_vector(nodes[name]["point_uv_m"]) for name in display_ids]
        displayed_area = rational_area(displayed)
        polygon = Polygon([nodes[name]["point_uv_m"] for name in display_ids])
        require(polygon.is_valid and polygon.area > 0 and area * displayed_area > 0,
                "display loop changes orientation or validity")
        certificate = projection_certificate(ring, [nodes[name]["point_uv_m"] for name in ids])
        bound = Fraction(certificate["projection_area_bound_rational"])
        require(certificate["maximum_projection_distance_m"] <= 1e-8 and certificate["area_error_m2"] <= 1e-8
                and certificate["conservative_projection_area_bound_m2"] <= 1e-8,
                "original projection distance/area gate exceeded")
        require(loop["display_signed_area_m2_rational"] == str(displayed_area), "display rational area differs")
        require(all(loop[key] == value for key, value in certificate.items()), "exact L1/upward projection certificate differs")
        rings.append(ring)
        displays.append(polygon)
        areas.append(area)
        bounds.append(bound)
    require(observed == expected, "identity loops do not exhaust original rational directed edges")
    outgoing, incoming = Counter(edge[0] for edge in expected), Counter(edge[1] for edge in expected)
    require(outgoing == incoming and all(count == 1 for count in outgoing.values()), "open/branched original rational trace")
    check_rational_boundaries(rings)
    parents = []
    for ordinal, loop in enumerate(own_loops):
        query = list(map(Fraction, loop["containment_query_uv_rational"]))
        point = Point(list(map(float, query)))
        require(displays[ordinal].contains(point) and rational_contains(query, rings[ordinal]),
                "hierarchy query outside own rational/display loop")
        containers = []
        for other, polygon in enumerate(displays):
            if other == ordinal:
                continue
            require(not displays[ordinal].boundary.intersects(polygon.boundary), "display hierarchy touching/crossing")
            if abs(areas[other]) > abs(areas[ordinal]):
                inside = rational_contains(query, rings[other])
                require(inside == polygon.contains(point), "rational/display containment disagreement")
                if inside:
                    containers.append(other)
        parent = min(containers, key=lambda index: abs(areas[index])) if containers else None
        require(loop["exact_parent_loop_index"] == parent and loop["display_parent_loop_index"] == parent
                and loop["hierarchy_certified"] is True, "saved hierarchy certificate differs")
        require(parent is not None or areas[ordinal] > 0, "root hole without occupied shell")
        if parent is not None:
            require((areas[parent] > 0) != (areas[ordinal] > 0), "non-alternating exact hole hierarchy")
        parents.append(parent)
    polygons = []
    for ordinal, area in enumerate(areas):
        if area > 0:
            holes = [list(displays[index].exterior.coords) for index, parent in enumerate(parents)
                     if parent == ordinal and areas[index] < 0]
            polygon = Polygon(displays[ordinal].exterior.coords, holes)
            require(polygon.is_valid, "invalid certified occupied component/holes")
            polygons.append(polygon)
    return unary_union(polygons), sum(bounds, Fraction(0))


def audit_exact_slice(record, solid, frame, pin):
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    check_identity(record)
    require(record["schema"] == SLICE_SCHEMA and record["mesh_pin"] == pin
            and record["coordinate_convention"] == frame["coordinate_convention"]
            and record["method"] == "rational_identity_topology_certified_binary64_display"
            and record["numerical_policy"] == NUMERICAL_POLICY
            and record["numerical_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256,
            "rational slice source/schema/policy differs")
    nodes, segments, caps, signs = independent_triangle_trace(solid, frame)
    require(record["vertex_plane_classifications"] == [{"vertex_index": index, "sign": sign,
            "classification_method": "exact_rational"} for index, sign in enumerate(signs)], "rational vertex classification differs")
    check_census(record["intersection_nodes"], nodes, "node_id", "rational intersection authority")
    check_census(record["triangle_segments"], segments, "triangle_index", "rational original triangle segment")
    for cap in caps.values():
        rational = [list(map(Fraction, nodes[name]["rational_uv_m"])) for name in cap["intersection_node_ids"]]
        cap["projection_certificate"] = {"signed_area_m2_rational": str(rational_area(rational)),
                                         **projection_certificate(rational, cap["polygon_uv_m"])}
    check_census(record["coplanar_triangle_supports"], caps, "triangle_index", "rational oriented original cap")
    collapses = {}
    for ordinal, segment in segments.items():
        if segment["points_uv_m"][0] == segment["points_uv_m"][1]:
            first, second = [list(map(Fraction, point)) for point in segment["rational_points_uv_m"]]
            require(first != second, "actual exact-zero segment cannot be display-omitted")
            collapses[ordinal] = {"triangle_index": ordinal, "intersection_node_ids": segment["intersection_node_ids"],
                "rational_delta_uv_m": [str(end - start) for start, end in zip(first, second)],
                "display_point_uv_m": segment["points_uv_m"][0], "display_omitted_zero_length_only": True,
                "original_segment_and_node_identities_preserved": True}
    check_census(record["projection_collapse_witnesses"], collapses, "triangle_index", "display collapse witness")
    loops = record["identity_loops"]
    require(all(loop["side"] in ("positive", "negative") for loop in loops), "unknown rational loop side")
    sides, bounds = {}, []
    for side in ("positive", "negative"):
        sides[side], bound = certified_side(loops, side, nodes, segments)
        bounds.append(bound)
        check_shape(record["one_sided_interior_traces"][side], sides[side], side + " certified trace")
    require(set(record["one_sided_interior_traces"]) == set(sides), "rational incident-side census differs")
    cap_polygons, cap_bounds = [], []
    for cap in caps.values():
        rational = [list(map(Fraction, nodes[name]["rational_uv_m"])) for name in cap["intersection_node_ids"]]
        display = Polygon(cap["polygon_uv_m"])
        shown = [rational_vector(point) for point in cap["polygon_uv_m"]]
        certificate = cap["projection_certificate"]
        require(display.is_valid and display.area > 0 and rational_area(rational) * rational_area(shown) > 0
                and certificate["area_error_m2"] <= 1e-8 and certificate["maximum_projection_distance_m"] <= 1e-8
                and certificate["conservative_projection_area_bound_m2"] <= 1e-8,
                "actual coplanar facet projection cannot be certified")
        cap_polygons.append(display)
        cap_bounds.append(Fraction(certificate["projection_area_bound_rational"]))
    rational_bound = sum([*bounds, *cap_bounds], Fraction(0))
    full_bound = ceil_fraction(rational_bound)
    require(record["display_projection_certified"] is True and full_bound <= 1e-8, "whole slice projection certificate exceeds original gate")
    require(record["projection_area_error_bound_m2"] == full_bound
            and record["projection_area_error_bound_rational"] == str(rational_bound), "whole rational L1/upward projection bound differs")
    cap_shape = unary_union(cap_polygons)
    actual = unary_union([*sides.values(), cap_shape])
    require(actual.is_valid and record["coplanar_semantics"] ==
            "closed_trace_retains_original_oriented_facets_no_cap_deletion", "unknown rational cap semantics")
    difference = check_shape(record, actual, "rational closed slice display")
    parts = polygon_parts(actual)
    holes = [Polygon(hole).difference(actual) for polygon in parts for hole in polygon.interiors]
    holes = [hole for hole in holes if not hole.is_empty]
    witnesses = record["occupancy_witnesses"]
    require(len(witnesses) == len(parts) + len(holes), "rational occupancy witness census differs")
    covered, covered_holes = set(), set()
    for witness in witnesses:
        query = Point(witness["point_uv_m"])
        inside = witness["region"] == "retained_polygon"
        require(inside or witness["region"] == "excluded_hole", "unknown rational occupancy region")
        candidates = [index for index, polygon in enumerate(parts if inside else holes) if polygon.contains(query)]
        visited = covered if inside else covered_holes
        require(len(candidates) == 1 and candidates[0] not in visited, "duplicate/outside rational occupancy witness")
        visited.add(candidates[0])
        point = np.asarray(frame["origin_local_xyz_m"]) + query.x * np.asarray(frame["transverse_unit_xyz"])
        point[1] = query.y
        compare(witness["point_local_xyz_m"], point, "rational occupancy frame", atol=1e-12)
        if cap_shape.covers(query):
            require(inside and witness["classification"] == "original_oriented_coplanar_boundary_facet"
                    and witness["coplanar_triangle_indices"] == [ordinal for ordinal, cap in caps.items()
                        if Polygon(cap["polygon_uv_m"]).covers(query)], "unbound coplanar occupancy witness")
        else:
            expected = int(inside)
            classification = "original_Mesh64_interior_two_ray_parities" if inside else "original_Mesh64_void_two_ray_parities"
            require(witness["classification"] == classification and witness["ray_parities"] == [expected, expected]
                    and abs(solid.winding(point) - expected) <= 1e-7, "independent rational original solid occupancy failed")
    check_memory()
    return actual, {"schema": "td-hybrid-rational-slice-independent-evidence-v1", "verified": True,
        "mesh_pin": pin, "slice_identity_sha256": record["identity_sha256"],
        "numerical_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "area_m2": float(actual.area), "symmetric_difference_m2": float(difference),
        "triangle_segments": len(segments), "coplanar_triangles": len(caps), "identity_loops": len(loops),
        "projection_collapse_witnesses": len(collapses), "projection_area_error_bound_m2": full_bound,
        "full_rational_source_identity_and_hierarchy_verified": True,
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
        source_record = read(composition["mesh_pins"][role])
        pin = {"artifact": role, "identity_sha256": source_record["identity_sha256"],
               "triangle_identity_authority": "immutable_saved_record_arrays"}
        shape, report = audit_exact_slice(record, meshes[role], plane, pin)
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
    blocked_upper = area_upper(blocked.area, evidence["canonical:rock_after"]["projection_area_error_bound_m2"])
    missing_upper = area_upper(missing.area, evidence["canonical:coupled_cutter"]["projection_area_error_bound_m2"])
    require(connection["blocked_area_upper_bound_m2"] == blocked_upper
            and connection["missing_area_upper_bound_m2"] == missing_upper, "saved port area upward bound differs")
    evidence["whole_port_metrics"].update(blocked_area_with_projection_bound_m2=blocked_upper,
                                         missing_area_with_projection_bound_m2=missing_upper)
    require(blocked_upper <= 1e-8 and missing_upper <= 1e-8, "actual full port blocked/missing or projection uncertainty exceeds original gate")
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
        source_index = read(composition["stage_lineage"]["source_index_pin"])
        inherited = role in source_index["artifacts"]
        require(saved["inherited_saved_collar"] is inherited and (not inherited
                or source_index["artifacts"][role] == composition["mesh_pins"][role]), "saved collar inheritance claim differs")
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
        gap_upper = area_upper(gap.area, evidence["collar:" + side]["projection_area_error_bound_m2"])
        require(saved["uncovered_area_upper_bound_m2"] == gap_upper, "saved collar upward coverage bound differs")
        check_shape(saved["uncovered_domain"], gap, "collar uncovered domain", require_contacts=True)
        require(gap_upper <= 1e-8,
                "whole port collar gap/projection uncertainty exceeds original gate")
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
    require(traces == [] and connection["offset_traces_not_recomputed"] is True,
            "v3 diagnostic-offset reuse contract differs")
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


def check_stage_lineage(record):
    lineage = record["stage_lineage"]
    require(set(lineage) == {"source_index_pin", "source_composition_pin", "checkpoint_pin", "boolean_artifact_pins",
            "source_code_sha256", "source_readonly_dependency_code_sha256", "source_status", "source_rejection_reasons",
            "main_boolean_recomputed"} and lineage["main_boolean_recomputed"] is False, "unknown stage replay lineage")
    require(lineage["source_index_pin"]["sha256"] == SOURCE_INDEX_SHA256
            and lineage["source_composition_pin"]["sha256"] == SOURCE_COMPOSITION_SHA256
            and lineage["checkpoint_pin"]["sha256"] == SOURCE_CHECKPOINT_SHA256,
            "only fixed composition02 saved Boolean stage authorized")
    index = read(lineage["source_index_pin"])
    source = read(lineage["source_composition_pin"])
    checkpoint = read(lineage["checkpoint_pin"])
    require(index["schema"] == "td-hybrid-surface-composition-preparation-v2"
            and source["schema"] == "td-hybrid-surface-composition-v2"
            and index["composition"] == lineage["source_composition_pin"]
            and source["checkpoint_boolean_pin"] == lineage["checkpoint_pin"] == record["checkpoint_boolean_pin"]
            and index["status"] == source["status"] == lineage["source_status"]
            and index["rejection_reasons"] == source["rejection_reasons"] == lineage["source_rejection_reasons"]
            and source["boolean_stage_preserved"] is True, "source stage identity/status binding differs")
    require(checkpoint["schema"] == "td-hybrid-surface-composition-boolean-checkpoint-v2"
            and checkpoint["status"] == "boolean_stage_unverified" and checkpoint["portal_checks_started"] is False
            and lineage["boolean_artifact_pins"] == checkpoint["artifacts"]
            and index["inputs"] == source["inputs"] == checkpoint["inputs"] == record["inputs"]
            and index["code_sha256"] == source["code_sha256"] == checkpoint["code_sha256"] == lineage["source_code_sha256"] == SOURCE_V2_CODE
            and index["readonly_dependency_code_sha256"] == source["readonly_dependency_code_sha256"]
            == checkpoint["readonly_dependency_code_sha256"] == lineage["source_readonly_dependency_code_sha256"],
            "source Boolean checkpoint input/code/artifact binding differs")
    for name, sha in {**SOURCE_V2_CODE, **lineage["source_readonly_dependency_code_sha256"]}.items():
        require(file_sha256(ROOT / name) == sha, "source stage frozen implementation changed: " + name)
    stage = checkpoint["composition_stage"]
    check_identity(stage)
    require(stage["schema"] == source["schema"] and stage["status"] == "boolean_stage_unverified"
            and not stage["rejection_reasons"] and checkpoint["runtime"] == source["runtime"] == record["runtime"],
            "source Boolean stage/runtime contract differs")
    require(source["policy"] == stage["policy"] == SOURCE_POLICY
            and source["policy_identity_sha256"] == stage["policy_identity_sha256"] == index["policy_identity_sha256"] == digest(SOURCE_POLICY)
            and source["numerical_slice_policy"] == checkpoint["numerical_slice_policy"] == index["numerical_slice_policy"]
            == stage["numerical_slice_policy"] == SOURCE_SLICE_POLICY
            and source["numerical_slice_policy_identity_sha256"] == checkpoint["numerical_slice_policy_identity_sha256"]
            == index["numerical_slice_policy_identity_sha256"] == stage["numerical_slice_policy_identity_sha256"] == digest(SOURCE_SLICE_POLICY),
            "source stage numerical/geometric identity differs")
    for field in ("geometry_identity_sha256", "graph_identity_sha256", "material", "coupled_cutter_component_count",
                  "original_source_sampling_cut_lookup_mismatches"):
        require(stage[field] == source[field] == record[field], "unchanged source Boolean field differs: " + field)
    require(checkpoint["material"] == record["material"] and checkpoint["artifacts"]["surface_prisms"] == record["surface_prisms_pin"],
            "replayed source prisms/material substituted")
    expected = {"surface_cutter", "coupled_cutter", "rock_after", "removed", "extra_removed", "surface_prisms"}
    require(set(checkpoint["artifacts"]) == expected, "source Boolean artifact census differs")
    for role, pin in checkpoint["artifacts"].items():
        require(index["artifacts"][role] == pin and (source["surface_prisms_pin"] == pin if role == "surface_prisms"
                else source["mesh_pins"][role] == record["mesh_pins"][role] == pin), "unchanged Boolean artifact byte pin differs")
    return checkpoint


def audit_complete(composition_pin, progress):
    record = read(composition_pin)
    require(record["schema"] == "td-hybrid-surface-composition-v3"
            and record["status"] in ("candidate_unverified", "refused")
            and record["boolean_stage_preserved"] is True, "unknown/incomplete composition v2 stage")
    check_code_pins(record)
    progress.update(composition_identity_sha256=record["identity_sha256"], inputs=record["inputs"],
                    mesh_pins=record["mesh_pins"], surface_prisms_pin=record["surface_prisms_pin"],
                    stage_lineage=record["stage_lineage"])
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
    require(record["main_boolean_recomputed"] is False and record["material_inherited_unchanged"] is True,
            "v3 replay changed original Boolean/material")
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
    checkpoint = check_stage_lineage(record)
    progress["stage_lineage_verified"] = True
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
            progress.setdefault("mesh_validation_reports", {})[role] = meshes[role].validation_evidence
    sections = read(geometry["inputs"]["original_06_sections"])
    protection = read(geometry["inputs"]["original_wet_protection_manifest"])["wet_protection"]
    native = load_native(geometry["inputs"]["original_hierarchy"], sections["selected_leaf_ids"], protection)
    prisms = read(record["surface_prisms_pin"])
    _, source_reports = audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    progress.update(native_half_arm_sources_verified=True, source_reports=source_reports,
                    original_source_sampling_cut_lookup_mismatches=sampling_mismatches)
    material = previous.audit_material_solids(*(meshes[key] for key in ("rock_before", "original_rock_after", "original_removed",
        "surface_cutter", "coupled_cutter", "rock_after", "extra_removed", "removed", "original_cutter")))
    progress["material_boolean_evidence"] = material
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
    progress.update(materials_verified=True, material=material)
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
        "stage_lineage": record["stage_lineage"], "stage_lineage_verified": True,
        "mesh_validation_reports": progress.get("mesh_validation_reports", {}),
        "solid_validation_policy": SOLID_POLICY, "solid_validation_policy_identity_sha256": SOLID_POLICY_SHA256,
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


def audit(composition_pin):
    progress = {"schema": AUDIT_SCHEMA, "status": "refused", "errors": [], "composition_pin": composition_pin,
        "native_half_arm_sources_verified": False, "materials_verified": False, "two_sided_complete_port_verified": False,
        "hydraulic_constitutive_law_accepted": False, "hydraulic_solved": False, "whole_link_control_sill_verified": False,
        "numerical_slice_policy": NUMERICAL_POLICY, "numerical_slice_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "solid_validation_policy": SOLID_POLICY, "solid_validation_policy_identity_sha256": SOLID_POLICY_SHA256}
    try:
        return audit_complete(composition_pin, progress)
    except ERRORS as error:
        progress["errors"].append(str(error))
        return progress


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
        "tools/audit_hybrid_surface_composition_v3.py", "tests/test_hybrid_surface_composition_v3_saved_audit.py",
        "tools/audit_hybrid_surface_composition.py", "tools/audit_hybrid_river_faces.py",
        "tools/hybrid_exact_solid_saved_audit.py", "tools/hybrid_cave_saved_audit.py", "tools/td_shared_channel_fine_saved_audit.py")}
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
