"""Independent saved-only audit of source-relative banks and atomic replacements."""

import argparse
from collections import Counter, defaultdict
import gc
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from tools.audit_td_fine_bed_raster import _source
from tools.audit_td_fine_bed_shards import check_memory, cut_volume, digest, read
from tools.td_source_conforming_saved_audit import native_edge_polynomial


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assert_close(actual, expected, name, atol=1e-8):
    actual, expected = np.asarray(actual), np.asarray(expected)
    require(actual.shape == expected.shape and np.isfinite(actual).all() and np.isfinite(expected).all()
            and np.allclose(actual, expected, atol=atol, rtol=0.), "saved bank mismatch: "+name)


def area(polygon):
    points = np.asarray(polygon, float)
    local = points-points[0]
    return abs(float(np.sum(local[:, 0]*np.roll(local[:, 1], -1)-local[:, 1]*np.roll(local[:, 0], -1))))/2


def clip_patch(vertices, corner, spacing):
    polygon = np.asarray(vertices, float).tolist()
    for axis, boundary, sign in ((0, corner[0], 1), (0, corner[0]+spacing, -1),
                                  (1, corner[1], 1), (1, corner[1]+spacing, -1)):
        clipped = []
        for first, second in zip(polygon, polygon[1:]+polygon[:1]):
            first_distance = sign*(first[axis]-boundary)
            second_distance = sign*(second[axis]-boundary)
            if first_distance >= 0:
                clipped.append(first)
            if (first_distance >= 0) != (second_distance >= 0):
                ratio = first_distance/(first_distance-second_distance)
                clipped.append((np.array(first)+ratio*(np.array(second)-first)).tolist())
        polygon = clipped
    return polygon


def barycentric(vertices, point):
    points = np.asarray(vertices, float)
    return np.linalg.solve(np.vstack(((points-point).T, np.ones(3))), [0., 0., 1.])


def source_sample(hierarchy, selected, point, saved=None):
    height, reasons, provenance = _source(hierarchy["arrays"], hierarchy["metadata"], selected, np.asarray(point))
    if saved is not None:
        require(saved["rejection_reasons"] == reasons, "native source rejection mismatch")
        if height is None:
            require(saved["height_m"] is None, "unknown native height incorrectly filled")
        else:
            assert_close(saved["height_m"], height, "native saved sample", atol=1e-10)
        for name, value in provenance.items():
            assert_close(saved[name], value, "native saved provenance "+name, atol=1e-12)
    return height, reasons


def wet_at(hierarchy, protection, point, height):
    metadata, arrays = hierarchy["metadata"], hierarchy["arrays"]
    position = (np.asarray(point)-metadata["origin_m_xz"])/metadata["spacing_m"]
    column, row = np.floor(position+.5).astype(int)
    require(0 <= row < arrays["height_m"].shape[0] and 0 <= column < arrays["height_m"].shape[1], "wet vertex outside native source")
    native_cell = row*arrays["height_m"].shape[1]+column
    stages = {item["leaf_id"]: item["stage_m"] for item in protection["stage_by_leaf"]}
    return native_cell in protection["covered_native_cell_ids"] or height < stages.get(int(arrays["contribution_owner"][row, column]), -math.inf)


def edge_key(points):
    first, second = np.asarray(points, float)
    direction = second-first
    direction /= np.linalg.norm(direction)
    if direction[0] < -1e-12 or (abs(direction[0]) <= 1e-12 and direction[1] < 0):
        direction *= -1
    return (round(float(direction[0]), 10), round(float(direction[1]), 10),
            round(float(np.array([-direction[1], direction[0]])@first), 7))


def intervals_complete(intervals, label):
    cursor = 0.
    for lower, upper in sorted(intervals):
        require(abs(lower-cursor) <= 1e-8 and upper > lower, label+" gap/duplicate")
        cursor = upper
    require(abs(cursor-1) <= 1e-8, label+" incomplete")


def audit_edges(proofs, triangles, sections, transitions, hierarchy, selected, selected_triangles):
    groups = defaultdict(list)
    all_triangles = dict(triangles)
    mesh = sections["mesh"]
    for number, indices in enumerate(mesh["triangles"]):
        if "06:"+str(number) not in triangles:
            all_triangles["legacy06:"+str(number)] = dict(vertices_xyz_m=[mesh["vertices_xyz_m"][index] for index in indices])
    for identifier, triangle in all_triangles.items():
        vertices = np.asarray(triangle["vertices_xyz_m"])
        for edge_index in range(3):
            points = vertices[[edge_index, (edge_index+1)%3]]
            groups[edge_key(points[:, [0, 2]])].append((identifier, edge_index, points))
    coverage = defaultdict(list)
    accepted = {}
    for proof in proofs.values():
        start, end = np.asarray(proof["start_xz_m"]), np.asarray(proof["end_xz_m"])
        direction = end-start
        length = np.linalg.norm(direction)
        require(length > 1e-8, "degenerate source-relative segment")
        actual_sides = {}
        midpoint = (start+end)/2
        for identifier, edge_index, points in groups[edge_key([start, end])]:
            edge = points[1, [0, 2]]-points[0, [0, 2]]
            offsets = np.array([start, end])-points[0, [0, 2]]
            distance = np.abs(offsets[:, 0]*edge[1]-offsets[:, 1]*edge[0])/np.linalg.norm(edge)
            if np.max(distance) > 1e-8:
                continue
            fractions = offsets@edge/(edge@edge)
            middle_fraction = float((midpoint-points[0, [0, 2]])@edge/(edge@edge))
            if 1e-10 < middle_fraction < 1-1e-10:
                require(fractions.min() >= -1e-8 and fractions.max() <= 1+1e-8, "segment omitted original T-junction")
                actual_sides[(identifier, edge_index)] = points
                if identifier in selected_triangles:
                    coverage[(identifier, edge_index)].append(sorted(fractions.tolist()))
        saved_sides = {(side["triangle_id"], side["edge_index"]): side for side in proof["sides"]}
        require(len(saved_sides) == len(proof["sides"]) and set(saved_sides) == set(actual_sides), "shared edge omitted/duplicated an original neighbor")
        for key, points in actual_sides.items():
            assert_close(saved_sides[key]["points_xyz_m"], points, "original shared-edge provenance", atol=1e-10)
        if proof["status"] != "candidate":
            require(bool(proof["rejection_reasons"]), "refused edge lacks explanation")
            continue
        require(not proof["rejection_reasons"], "candidate edge has refusals")
        source = native_edge_polynomial(hierarchy, selected, start, end)
        coefficients = np.array(source["source_height_polynomial_m"])
        assert_close(proof["source"]["source_coefficients_m_t012"], coefficients, "whole native edge polynomial", atol=1e-9)
        require(proof["source"]["patch_row_column"] == source["native_patch_row_column"], "edge native patch differs")
        cuts = []
        for side in proof["side_depth_knots"]:
            require((side["triangle_id"], side["edge_index"]) in saved_sides, "depth side not a mesh side")
            values = np.asarray(side["depth_knots_m"], float)
            require(values.shape == (2,) and np.isfinite(values).all() and values.min() >= 0, "negative/nonfinite edge cut")
            cuts.append(values)
        require(len(cuts) == len(actual_sides), "missing depth side")
        for values in cuts:
            assert_close(values, cuts[0], "whole shared linear-depth function", atol=1e-9)
        assert_close(proof["depth_coefficients_m_t01"], [cuts[0][0], cuts[0][1]-cuts[0][0]], "edge cut polynomial", atol=1e-9)
        if proof["boundary_condition"] == "explicit_source_bank_zero_depth_v2":
            require(len(actual_sides) == 1 and next(iter(saved_sides.values())).get("zero_depth_boundary_eligible"), "zero-depth BC not an eligible outer bank")
            identifier, edge_index = next(iter(actual_sides))
            original_triangle = triangles[identifier]
            if original_triangle["source_package"] == "06":
                bank_points = {tuple(point) for section in sections["edge_sections"]
                               for profile in section["cross_section_xyz_m"] for point in (profile[0], profile[-1])}
                eligible = all(tuple(point) in bank_points for point in next(iter(actual_sides.values())))
            else:
                indices = original_triangle["source_vertex_indices"]
                first_index, second_index = indices[edge_index], indices[(edge_index+1)%3]
                entry = transitions["entries"][original_triangle["source_entry_index"]]
                eligible = (first_index%5 == second_index%5 and first_index%5 in (0, 4)
                            or min(first_index, second_index) >= len(entry["vertices_xyz_m"])-5)
            require(eligible, "zero-depth boundary has no original outer-bank/anchor witness")
            for vertex in next(iter(actual_sides.values())):
                height, reasons = source_sample(hierarchy, selected, vertex[[0, 2]])
                require(not reasons and height-vertex[1] == 0., "zero-depth boundary original endpoint not source-conforming")
            assert_close(cuts[0], [0., 0.], "new zero-depth source bank")
        else:
            support_points = np.asarray([knot["xz_m"] for knot in proof["depth_support_knots"]])
            require(support_points.shape == (2, 2), "edge requires two original support knots")
            support_vector = support_points[1]-support_points[0]
            require(np.linalg.norm(support_vector) > 1e-8, "degenerate original support interval")
            support_fractions = (np.array([start, end])-support_points[0])@support_vector/(support_vector@support_vector)
            require(support_fractions.min() >= -1e-8 and support_fractions.max() <= 1+1e-8, "segment outside original support interval")
            group = groups[edge_key([start, end])]
            for group_identifier, group_edge_index, group_points in group:
                for vertex in group_points:
                    fraction = float((vertex[[0, 2]]-support_points[0])@support_vector/(support_vector@support_vector))
                    require(not 1e-8 < fraction < 1-1e-8, "original support omitted a T-junction knot")
            support_depths = []
            for knot in proof["depth_support_knots"]:
                values = []
                expected_references = set()
                for group_identifier, group_edge_index, group_points in group:
                    for vertex in group_points:
                        if np.linalg.norm(vertex[[0, 2]]-knot["xz_m"]) <= 1e-8:
                            expected_references.add((group_identifier, group_edge_index, tuple(vertex)))
                actual_references = {(reference["triangle_id"], reference["edge_index"], tuple(reference["xyz_m"])) for reference in knot["original_vertex_refs"]}
                require(actual_references == expected_references, "original shared-knot reference census differs")
                for reference in knot["original_vertex_refs"]:
                    vertex = np.asarray(reference["xyz_m"])
                    original = np.asarray(all_triangles[reference["triangle_id"]]["vertices_xyz_m"])
                    edge_index = reference["edge_index"]
                    require(vertex.tolist() in original[[edge_index, (edge_index+1)%3]].tolist()
                            and np.linalg.norm(vertex[[0, 2]]-knot["xz_m"]) <= 1e-8, "fabricated shared source knot")
                    for points in actual_sides.values():
                        edge_vector = points[1, [0, 2]]-points[0, [0, 2]]
                        fraction = float((np.asarray(knot["xz_m"])-points[0, [0, 2]])@edge_vector/(edge_vector@edge_vector))
                        old_height = points[0, 1]+fraction*(points[1, 1]-points[0, 1])
                        require(abs(vertex[1]-old_height) <= 1e-9, "original T-junction height seam mismatch")
                    height, reasons = source_sample(hierarchy, selected, vertex[[0, 2]])
                    require(not reasons and height-vertex[1] >= 0, "shared source knot negative or unknown")
                    values.append(height-vertex[1])
                require(bool(values), "shared support knot lacks originals")
                assert_close(values, np.full(len(values), values[0]), "original shared-knot depths", atol=1e-9)
                support_depths.append(values[0])
            vector = support_points[1]-support_points[0]
            fraction = (np.array([start, end])-support_points[0])@vector/(vector@vector)
            assert_close(cuts[0], support_depths[0]+fraction*(support_depths[1]-support_depths[0]), "canonical source-depth knots", atol=1e-9)
        bed = coefficients.copy()
        bed[:2] -= proof["depth_coefficients_m_t01"]
        for (identifier, edge_index), points in actual_sides.items():
            if identifier.startswith("legacy06:"):
                vector = points[1, [0, 2]]-points[0, [0, 2]]
                fraction = (np.array([start, end])-points[0, [0, 2]])@vector/(vector@vector)
                heights = points[0, 1]+fraction*(points[1, 1]-points[0, 1])
                assert_close(bed, [heights[0], heights[1]-heights[0], 0.], "whole unchanged neighbor polynomial", atol=1e-9)
        if len(actual_sides) == 1:
            require(cuts[0].max() <= 1e-9, "nonzero uncovered channel edge")
        require(sum(not key[0].startswith("legacy06:") for key in actual_sides) <= 2, "nonmanifold source-relative edge")
        accepted[proof["segment_id"]] = (start, end, cuts[0], bed)
    for identifier in selected_triangles:
        for edge_index in range(3):
            intervals_complete(coverage[(identifier, edge_index)], "triangle boundary "+identifier)
    return accepted


def audit_function(function, triangle, edges, hierarchy, selected, parameters, protection):
    require(function["original_triangle"] == triangle, "source-relative function changed parent triangle")
    vertices = np.asarray(triangle["vertices_xyz_m"], float)
    require(len(function["original_vertex_source_samples"]) == 3, "missing original vertex sample")
    depths = []
    for vertex, sample in zip(vertices, function["original_vertex_source_samples"]):
        height, reasons = source_sample(hierarchy, selected, vertex[[0, 2]], sample)
        depths.append(None if height is None else height-vertex[1])
    center = vertices[:, [0, 2]].mean(axis=0)
    source_sample(hierarchy, selected, center, function["center_source_sample"])
    if function["status"] != "candidate":
        require(bool(function["rejection_reasons"]), "refused function lacks explanation")
        return None
    require(all(value is not None and value >= 0 for value in depths), "candidate original vertex cut negative")
    require(max(depths) <= parameters["max_cut_m"]+parameters["conflict_tolerance_m"], "candidate original vertex cut too deep")
    for vertex, depth, sample in zip(vertices, depths, function["original_vertex_source_samples"]):
        wet = wet_at(hierarchy, protection, vertex[[0, 2]], sample["height_m"])
        require(sample["wet_source_support"] == wet and not (wet and depth > parameters["conflict_tolerance_m"]), "candidate cut protected wet vertex")
    assert_close(function["original_vertex_cut_depth_m"], depths, "source-relative original depths", atol=1e-9)
    center_depth = math.fsum(depths)/3
    assert_close(function["center_cut_depth_m"], center_depth, "source-relative center rule", atol=1e-9)
    expected_edges = {identifier for identifier, proof in edges.items() if any(side["triangle_id"] == triangle["triangle_id"] for side in proof["sides"])}
    require({fan["boundary_segment_id"] for fan in function["fans"]} == expected_edges and len(function["fans"]) == len(expected_edges), "fan boundary coverage missing/duplicate")
    total_area = 0.
    compact = []
    origin = np.asarray(hierarchy["metadata"]["origin_m_xz"])
    spacing = hierarchy["metadata"]["spacing_m"]
    height = hierarchy["arrays"]["height_m"]
    for fan in function["fans"]:
        proof = edges[fan["boundary_segment_id"]]
        require(proof["status"] == "candidate", "candidate fan touches refused edge")
        points = np.asarray(fan["vertices_xz_m"], float)
        assert_close(points, [center, proof["start_xz_m"], proof["end_xz_m"]], "fan geometry", atol=1e-10)
        coefficients = np.asarray(fan["depth_coefficients_m_1xz"])
        assert_close(fan["depth_origin_xz_m"], center, "fan cut origin")
        predicted = coefficients[0]+(points-center)@coefficients[1:]
        edge_depth = proof["depth_coefficients_m_t01"]
        assert_close(predicted, [center_depth, edge_depth[0], sum(edge_depth)], "fan entire affine function", atol=1e-9)
        assert_close(fan["depth_at_vertices_m"], predicted, "fan depth vertices", atol=1e-9)
        require(np.min(fan["depth_at_vertices_m"]) >= 0, "fan violates continuum no-fill")
        require(np.max(fan["depth_at_vertices_m"]) <= parameters["max_cut_m"]+parameters["conflict_tolerance_m"], "fan exceeds continuum cut-depth cap")
        patch_ids = set()
        patch_area = 0.
        for patch in fan["native_patches"]:
            row, column = patch["patch_row_column"]
            require((row, column) not in patch_ids, "duplicate native fan patch")
            patch_ids.add((row, column))
            corner = origin+np.array([column, row])*spacing
            polygon = clip_patch(points, corner, spacing)
            require(len(polygon) >= 3, "native fan patch outside triangle")
            assert_close(patch["polygon_xz_m"], polygon, "complete fan/native intersection", atol=1e-9)
            sample, reasons = source_sample(hierarchy, selected, corner+spacing/2)
            require(not reasons, "fan native patch contains invalid source")
            native_values = [height[row, column], height[row, column+1], height[row+1, column], height[row+1, column+1]]
            assert_close(patch["native_height_m"], native_values, "actual native patch heights")
            assert_close(patch["bilinear_coefficients_m"], [native_values[0], native_values[1]-native_values[0], native_values[2]-native_values[0], native_values[3]-native_values[2]-native_values[1]+native_values[0]], "native bilinear coefficients", atol=1e-10)
            assert_close(patch["patch_origin_m_xz"], corner, "native fan patch origin")
            require(patch["native_spacing_m"] == spacing, "native patch resolution changed")
            require(patch["native_cell_ids"] == [row*height.shape[1]+column, row*height.shape[1]+column+1, (row+1)*height.shape[1]+column, (row+1)*height.shape[1]+column+1], "native patch cell references changed")
            measure = area(polygon)
            assert_close(patch["projected_area_m2"], measure, "native intersection area", atol=1e-10)
            patch_area += measure
        assert_close(patch_area, area(points), "complete native fan coverage", atol=1e-9)
        total_area += patch_area
        compact.append((points, center, coefficients, fan["fan_id"]))
    assert_close(total_area, area(vertices[:, [0, 2]]), "complete source-relative triangle coverage", atol=1e-9)
    assert_close(function["fan_projected_area_m2"], total_area, "saved total fan area", atol=1e-9)
    return dict(identity=function["identity_sha256"], fans=compact)


def audit_ports(ports, edges, transitions, sections, component_by_triangle, components):
    owners = {item["arc_id"]: item for item in sections["edge_sections"]}
    expected_entries = {number for number, entry in enumerate(transitions["entries"]) if entry["status"] == "candidate" and any(identifier.startswith(f"09:{number}:") for identifier in component_by_triangle)}
    require({port["source_entry_index"] for port in ports} == expected_entries and len(ports) == len(expected_entries), "missing/duplicate changed port proof")
    for port in ports:
        entry = transitions["entries"][port["source_entry_index"]]
        expected_components = sorted({component_id for identifier, component_id in component_by_triangle.items()
                                      if identifier.startswith(f"09:{port['source_entry_index']}:")})
        require(port["component_ids"] == expected_components, "port component binding differs")
        require(port["entry_id"] == entry["entry_id"] and port["original_four_point_port_xyz_m"] == entry["accepted_port_xyz_m"], "changed port lost original binding")
        owner = owners[entry["accepted_port_arc_id"]]
        require(entry["accepted_port_xyz_m"] in owner["cross_section_xyz_m"], "port not bound to accepted section")
        if port["status"] != "candidate":
            require(bool(port["rejection_reasons"]), "refused port lacks explanation")
            require(all(components[identifier]["status"] == "refused" for identifier in expected_components), "refused port associated with accepted component")
            continue
        matched = set()
        for first, second in zip(entry["accepted_port_xyz_m"], entry["accepted_port_xyz_m"][1:]):
            start, end = np.asarray(first)[[0, 2]], np.asarray(second)[[0, 2]]
            vector = end-start
            intervals = []
            for identifier in port["segment_ids"]:
                proof = edges[identifier]
                points = np.array([proof["start_xz_m"], proof["end_xz_m"]])
                offsets = points-start
                distances = np.abs(offsets[:, 0]*vector[1]-offsets[:, 1]*vector[0])/np.linalg.norm(vector)
                fractions = offsets@vector/(vector@vector)
                if distances.max() <= 1e-8 and fractions.min() >= -1e-8 and fractions.max() <= 1+1e-8:
                    identifiers = {side["triangle_id"] for side in proof["sides"]}
                    require(proof["status"] == "candidate" and identifiers.intersection({"06:"+str(number) for number in owner["triangle_indices"]}) and any(identifier.startswith(f"09:{port['source_entry_index']}:") for identifier in identifiers), "port lacks complete two-sided function")
                    intervals.append(sorted(fractions.tolist()))
                    matched.add(identifier)
            intervals_complete(intervals, "complete four-point shared port")
        require(matched == set(port["segment_ids"]), "extraneous shared port segment")


def audit_queue(queue, readiness, transitions, paths, sections, components):
    original = {item["entry_id"]: item for item in readiness["requests"] if item["status"] in {"pending", "parent_refused"}}
    rows = {item["entry_id"]: item for item in queue["requests"]}
    require(set(rows) == set(original) and len(rows) == len(queue["requests"]), "connection queue omitted/duplicated old refusal")
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
    node_sections = {item["node_id"]: (number, item) for number, item in enumerate(sections["node_sections"])}
    for identifier, row in rows.items():
        entry = transitions["entries"][row["source_entry_index"]]
        require(entry["entry_id"] == identifier and row["parent_status"] == original[identifier]["status"], "queue changed old status")
        arc = arcs.get(identifier)
        require(row["source_arc_reference"] == arc and row["actual_node_ids"] == (arc["node_ids"] if arc else []), "queue fabricated original arc")
        require(row["actual_entry_arc_id"] == (arc["arc_id"] if arc else None), "queue original arc identity differs")
        affected_components = sorted(component_id for component_id, component in components.items()
                                     if any(triangle.startswith(f"09:{row['source_entry_index']}:") for triangle in component["triangle_ids"]))
        require(row["component_ids"] == affected_components, "queue changed component references")
        classification = ("missing_geometry_parent" if entry["status"] != "candidate" else
                          "source_conforming_candidate" if affected_components and all(components[item]["status"] == "candidate" for item in affected_components)
                          else "shared_function_or_source_gate_pending")
        require(row["classification"] == classification, "queue overstated candidate readiness")
        parent_reasons = (list(entry["rejection_reasons"]) if entry["status"] != "candidate"
                          else list(original[identifier].get("cell_refusals", {})))
        require(row["parent_reasons"] == parent_reasons, "queue changed original rejection reasons")
        reason_class = ("ambiguous_or_missing_port" if "missing_or_ambiguous_accepted_port" in parent_reasons else
                        "ambiguous_or_missing_land_predecessor" if "missing_or_ambiguous_land_predecessor" in parent_reasons else
                        "engineering_boundary" if "engineering_boundary_contact" in parent_reasons else "saved_cell_gate")
        require(row["parent_reason_class"] == reason_class, "queue parent reason classification differs")
        source_nodes = sorted(set(row["actual_node_ids"]).union(entry[name] for name in ("upstream_node_id", "anchor_node_id", "wet_node_id") if name in entry))
        require(row["source_node_references"] == [nodes[node] for node in source_nodes if node in nodes], "queue fabricated nodes")
        require(row["accepted_port_arc_reference"] == arcs.get(entry.get("accepted_port_arc_id"))
                and row["land_arc_reference"] == arcs.get(entry.get("land_arc_id")), "queue fabricated port/predecessor arc")
        require(row["directed_hydraulic_connection_proved"] is False and row["fabricated_arc_count"] == 0, "queue promotes support path to hydraulic proof")
        arc_walk = row["actual_support_path_to_engineering_arc_ids"]
        node_walk = row["actual_support_path_to_engineering_node_ids"]
        if node_walk:
            require(len(node_walk) == len(arc_walk)+1 and node_walk[0] in row["actual_node_ids"], "queue node walk does not start at original entry")
        else:
            require(not arc_walk, "queue arc walk omitted node witnesses")
        for offset, arc_id in enumerate(arc_walk):
            require(arc_id in arcs, "queue fabricated support arc")
            segments = {(first, second) for first, second in zip(arcs[arc_id]["node_ids"], arcs[arc_id]["node_ids"][1:])}
            pair = tuple(node_walk[offset:offset+2])
            require(pair in segments or pair[::-1] in segments, "queue support hop is not an original adjacent arc segment")
        reached = bool(node_walk and node_walk[-1] in nodes and "engineering" in nodes[node_walk[-1]]["kinds"])
        require(reached == row["undirected_support_reaches_engineering"], "queue support reachability differs")
        expected_flow = []
        for node in source_nodes:
            if node in node_sections:
                number, section = node_sections[node]
                expected_flow.append(dict(node_id=node, source_node_section_index=number,
                    representative_q_m3_s=section.get("representative_q_m3_s"),
                    local_runoff_q_m3_s=section.get("local_runoff_q_m3_s"),
                    incoming_exchange_q_m3_s=section.get("incoming_exchange_q_m3_s"),
                    ordinary_identity_sha256=sections.get("ordinary_identity_sha256"),
                    semantics="unchanged ordinary-event mean proxy, not instantaneous Q"))
        require(row["ordinary_flow_references"] == expected_flow, "queue changed original Q references")
    return dict(requests=len(rows), parent_status_counts=dict(Counter(row["parent_status"] for row in rows.values())),
                classification_counts=dict(Counter(row["classification"] for row in rows.values())),
                parent_reason_counts=dict(Counter(row["parent_reason_class"] for row in rows.values())),
                original_graph_and_Q_references_verified=True, directed_hydraulic_connection_proved=False)


def audit(index):
    for name, sha in index["code_sha256"].items():
        require(file_sha256(ROOT/name) == sha, "bank code pin changed")
    pins = index["inputs"]
    parent_audit = read(pins["shards_independent_audit"])
    require(parent_audit["status"] == "passed" and parent_audit["index_sha256"] == pins["shards_index"]["sha256"], "accepted parent audit binding missing")
    parent_index = read(pins["shards_index"])
    require(parent_index["manifest"] == pins["shards_manifest"] and parent_index["raw"] == pins["shards_raw"]
            and parent_index["shard0"] == pins["base_raster"]
            and parent_audit["manifest_sha256"] == parent_index["manifest"]["sha256"], "accepted parent index does not bind consumed raw/base/manifest")
    for name, pin in parent_index["inputs"].items():
        require(pins[name] == pin, "new bank replaced an accepted parent input")
    shard_names = sorted((name for name in pins if name.startswith("shard:")), key=lambda name: int(name.split(":")[1]))
    require(shard_names == ["shard:"+str(number) for number in range(len(parent_index["shards"]))]
            and [pins[name] for name in shard_names] == parent_index["shards"], "accepted parent shard order/count/pins differ")
    base, parent_raw, parent_manifest = (read(pins[name]) for name in ("base_raster", "shards_raw", "shards_manifest"))
    manifest = read(index["manifest"])
    require(parent_manifest["identity_sha256"] == manifest["parent_identity_sha256"] and base["identity_sha256"] == manifest["base_identity_sha256"], "new bank parent identity mismatch")
    require(manifest["grid"] == base["grid"] and manifest["parameters"] == base["parameters"] and manifest["wet_protection"] == base["wet_protection"], "new bank changed original lattice/gates/protection")
    cells = {}
    tile = base["grid"]["tile_cells"]
    for window in base["windows"]:
        row, column = window["global_origin_row_column"]
        for cell in window["cells"]:
            key = (row+cell["local_index"]//tile, column+cell["local_index"]%tile)
            require(key not in cells, "duplicate parent cell")
            cells[key] = (cell, "shard0")
    for name in sorted((name for name in pins if name.startswith("shard:")), key=lambda name: int(name.split(":")[1])):
        shard = read(pins[name])
        for transaction in shard["transactions"]:
            key = tuple(transaction["global_key_row_column"])
            if key in cells:
                require(digest(cells[key][0]) == transaction["before_sha256"], "saved parent before hash mismatch")
            cells[key] = (transaction["cell"], transaction["logical_owner"])
        del shard
        check_memory()
    triangles = {triangle["triangle_id"]: triangle for triangle in base["triangles"]}
    triangles.update({triangle["triangle_id"]: triangle for triangle in parent_raw["triangles"]})
    components = {component["component_id"]: component for component in manifest["components"]}
    component_by_triangle = {identifier: component["component_id"] for component in components.values() for identifier in component["triangle_ids"]}
    require(len(component_by_triangle) == sum(len(component["triangle_ids"]) for component in components.values()), "duplicate changed component triangle")
    seeds = {proposal["triangle_id"] for cell, owner in cells.values() if "fill_without_material" in cell["rejection_reasons"] for proposal in cell["triangle_sources"]}
    require(seeds <= set(component_by_triangle), "v2 omitted old fill-refused seeds")
    affected = {key for key, (cell, owner) in cells.items() if any(proposal["triangle_id"] in component_by_triangle for proposal in cell["triangle_sources"])}
    require(affected == {tuple(key) for key in manifest["affected_global_keys_row_column"]}, "incomplete affected cell union")
    hierarchy_pin = pins["hierarchy"]
    hierarchy = load_basin_hierarchy(hierarchy_pin["path"], expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    selected = set(base["selected_leaf_ids"])
    sections, transitions, paths = (read(pins[name]) for name in ("06_sections", "09_transitions", "06_paths"))
    edges, ports = {}, []
    def records(kind):
        require([pin["identity_sha256"] for pin in index["chunks"][kind]] == manifest["chunk_identities"][kind], "chunk identity census differs")
        for pin in index["chunks"][kind]:
            chunk = read(pin)
            require(chunk["parent_identity_sha256"] == manifest["parent_identity_sha256"], "chunk parent differs")
            for record in chunk["records"]:
                if "identity_sha256" in record:
                    require(digest({name: value for name, value in record.items() if name != "identity_sha256"}) == record["identity_sha256"], "chunk record content identity differs")
                yield record
            del chunk
            check_memory()
    for proof in records("proofs"):
        if proof["kind"] == "edge_function_proof":
            require(proof["segment_id"] not in edges, "duplicate shared edge")
            retained = {name: proof[name] for name in ("segment_id", "start_xz_m", "end_xz_m", "sides", "status",
                "rejection_reasons", "side_depth_knots", "depth_coefficients_m_t01", "boundary_condition", "depth_support_knots")}
            retained["source"] = ({name: proof["source"][name] for name in ("source_coefficients_m_t012", "patch_row_column")}
                                  if proof["source"] is not None else None)
            edges[proof["segment_id"]] = retained
        else:
            ports.append(proof)
    accepted_edges = audit_edges(edges, triangles, sections, transitions, hierarchy, selected, set(component_by_triangle))
    for proof in edges.values():
        adjacent = {side["triangle_id"] for side in proof["sides"] if not side["triangle_id"].startswith("legacy06:")}
        require(adjacent <= set(component_by_triangle), "changed component omitted shared neighbor")
        require(len({component_by_triangle[identifier] for identifier in adjacent}) <= 1, "shared neighbors divided between components")
    audit_ports(ports, edges, transitions, sections, component_by_triangle, components)
    functions, statuses = {}, {}
    edges_by_triangle = defaultdict(dict)
    for identifier, edge in edges.items():
        for side in edge["sides"]:
            if side["triangle_id"] in component_by_triangle:
                edges_by_triangle[side["triangle_id"]][identifier] = edge
    for function in records("raw"):
        identifier = function["triangle_id"]
        require(identifier in component_by_triangle and identifier not in statuses, "unselected/duplicate function")
        statuses[identifier] = function["status"]
        functions[identifier] = audit_function(function, triangles[identifier], edges_by_triangle[identifier], hierarchy, selected, base["parameters"], base["wet_protection"])
    require(set(statuses) == set(component_by_triangle), "missing source-relative function")
    for component in components.values():
        require(set(component["seed_triangle_ids"]) == seeds.intersection(component["triangle_ids"]), "component seed provenance differs")
        require(bool(component["seed_triangle_ids"]), "unrequested component lacks old fill-refused seed")
        if component["status"] == "candidate":
            require(not component["rejection_reasons"] and all(statuses[identifier] == "candidate" for identifier in component["triangle_ids"]), "accepted component includes refused function")
            require(all(triangles[identifier]["status"] in {"rasterized", "no_center_coverage"} for identifier in component["triangle_ids"]), "accepted component changed incomplete parent geometry")
        else:
            require(bool(component["rejection_reasons"]), "component refusal unexplained")
    expected_effects = {key for key in affected if all(components[component_by_triangle[proposal["triangle_id"]]]["status"] == "candidate" for proposal in cells[key][0]["triangle_sources"] if proposal["triangle_id"] in component_by_triangle)}
    effects, deltas = set(), []
    spacing = base["grid"]["spacing_m"]
    origin = np.asarray(base["grid"]["origin_m_xz"])
    recovered = 0
    for effect in records("effects"):
        key = tuple(effect["global_key_row_column"])
        require(key in expected_effects and key not in effects and effect["operation"] == "replace", "partial/refused/new/duplicate effect")
        effects.add(key)
        before, owner = cells[key]
        after = effect["cell"]
        require(effect["before_sha256"] == digest(before) and effect["logical_owner"] == owner, "effect beforehash/owner mismatch")
        require(after["source_sample"] == before["source_sample"] and effect["source_sample_reused"] is True, "effect changed saved source sample")
        point = origin+(np.array([key[1], key[0]])+base["grid"]["center_offset_cells"])*spacing
        proposals = {proposal["triangle_id"]: proposal for proposal in after["triangle_sources"]}
        require(len(proposals) == len(after["triangle_sources"]) and set(proposals) == {proposal["triangle_id"] for proposal in before["triangle_sources"]}, "effect lost/added triangle proposal")
        for old in before["triangle_sources"]:
            identifier = old["triangle_id"]
            new = proposals[identifier]
            if identifier not in component_by_triangle:
                require(new == old, "effect changed untouched neighbor")
                continue
            function = functions[identifier]
            values = []
            for points, center, coefficients, fan_id in function["fans"]:
                weights = barycentric(points, point)
                if weights.min() >= -1e-8:
                    values.append((float(coefficients[0]+(point-center)@coefficients[1:]), fan_id))
            require(bool(values), "effect outside actual fan coverage")
            assert_close([value[0] for value in values], np.full(len(values), values[0][0]), "internal fan seam at saved center", atol=1e-9)
            depth = values[0][0]
            require(depth >= 0 and new["function_identity_sha256"] == function["identity"], "effect uses wrong/negative source cut")
            require(new["fan_id"] in {value[1] for value in values}, "effect fan identity mismatch")
            assert_close(new["legacy_absolute_bed_m"], old["bed_m"], "retained old mesh bed")
            assert_close(new["cut_depth_m"], depth, "saved effect cut function", atol=1e-9)
            assert_close(new["bed_m"], after["source_sample"]["height_m"]-depth, "source-relative effect bed", atol=1e-9)
        targets = [proposal["bed_m"] for proposal in proposals.values()]
        source = after["source_sample"]["height_m"]
        tolerance = base["parameters"]["conflict_tolerance_m"]
        require(after["status"] == "candidate" and not after["rejection_reasons"] and not after["source_sample"]["rejection_reasons"], "refused source/after effect applied")
        require(max(targets)-min(targets) <= tolerance and source-min(targets) <= base["parameters"]["max_cut_m"]+tolerance and max(targets) <= source+tolerance, "new center exceeds original cut/conflict/no-fill gate")
        require(not after["source_sample"]["wet_source_support"] or source-min(targets) <= tolerance, "new center cut original wet support")
        assert_close(after["derived_bed_m"], min(source, math.fsum(targets)/len(targets)), "derived saved center")
        before_cut, after_cut = cut_volume(before, spacing), cut_volume(after, spacing)
        assert_close([effect["before_cut_m3"], effect["after_cut_m3"], effect["cut_delta_m3"]], [before_cut, after_cut, after_cut-before_cut], "signed material replacement", atol=1e-10)
        deltas.append(after_cut-before_cut)
        recovered += "fill_without_material" in before["rejection_reasons"]
    require(effects == expected_effects, "accepted component only partially replaced")
    total_delta = math.fsum(deltas)
    require(manifest["material_ledger_parent"] == parent_manifest["material_ledger_merged"], "changed accepted parent ledger")
    for name, before in manifest["material_ledger_parent"].items():
        delta = total_delta if name in {"cut_rock_m3", "exported_excavated_rock_m3"} else 0.
        assert_close(manifest["material_ledger_delta"][name], delta, "whole signed material delta", atol=1e-9)
        assert_close(manifest["material_ledger_candidate"][name], before+delta, "whole candidate material", atol=1e-9)
    queue = read(index["connection_queue"])
    require(queue["identity_sha256"] == manifest["queue_identity_sha256"], "connection queue identity binding differs")
    queue_report = audit_queue(queue, parent_audit["readiness"], transitions, paths, sections, components)
    summary = manifest["summary"]
    require(summary["replace_cells"] == len(effects) and summary["affected_cells"] == len(affected) and summary["parent_unique_cells"] == len(cells), "bank summary census mismatch")
    require(summary["center_source_resamples"] == summary["new_lattice_cells"] == summary["water_solves"] == 0, "bank scope changed")
    require(index["resource"]["actual_peak_rss_bytes"] <= 1024**3 and len(cells) <= 2_000_000, "bank preparation resource gate exceeded")
    for record in (index, manifest):
        require(record["old_mesh_passed"] is False and record["independent_audit_passed"] is False, "unverified bank promoted old mesh")
        for flag in ("hydraulic_ready", "hydraulic_solved", "natural_outlet_certified", "publish_ready", "full_river_verified", "cross_domain_verified", "vdm_verified"):
            require(record[flag] is False, "bank promoted unrelated certification")
    gc.collect()
    return dict(schema="td-source-conforming-banks-independent-audit-v2", status="passed", summary=summary,
                saved_candidate_functions_and_refusals_verified=True,
                whole_shared_edge_and_port_functions_verified=summary["candidate_components"] > 0,
                source_conforming_component_ready=summary["candidate_components"] > 0,
                native_source_and_nonnegative_affine_cut_verified=True,
                atomic_affected_component_replacements_verified=True, signed_material_delta_verified=True,
                accepted_edge_functions=len(accepted_edges), accepted_port_functions=sum(port["status"] == "candidate" for port in ports),
                recovered_original_fill_refused_cells=recovered, signed_cut_delta_m3=total_delta,
                remaining_original_fill_refused_cells=summary["original_fill_refused_cells"]-recovered,
                refused_component_reason_counts=dict(Counter(reason for component in components.values()
                    if component["status"] == "refused" for reason in component["rejection_reasons"])),
                queue=queue_report, actual_peak_audit_rss_bytes=check_memory(),
                old_mesh_passed=False, hydraulic_solved=False, natural_outlet_certified=False, full_river_verified=False,
                scope="new source-relative candidate or explicit whole-component refusal; no solver, resampling, natural mouth or VDM certification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT/"verification/natural-river-network"), "new bounded bank audit path required")
    index = read(dict(path=str(args.input.resolve()), sha256=args.sha256))
    result = audit(index)
    result.update(index_sha256=args.sha256, manifest_sha256=index["manifest"]["sha256"], audit_code_sha256={name: file_sha256(ROOT/name) for name in (
        "tools/audit_td_source_conforming_banks.py", "tools/td_source_conforming_saved_audit.py",
        "tools/audit_td_fine_bed_raster.py", "tools/audit_td_fine_bed_shards.py", "tools/td_entry_saved_audit.py")})
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode())
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
