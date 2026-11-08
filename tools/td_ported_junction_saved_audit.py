"""Independent projected topology and full-function checks for saved junctions."""
from collections import defaultdict
import math
import numpy as np
from tools.audit_td_source_conforming_banks_v3 import assert_close, intervals_complete, require, source_sample, wet_at, edge_key, audit_function
from tools.audit_td_fine_bed_shards import digest, check_memory
from tools.audit_saved_source_conforming_banks import native_edge_polynomial
from tools.audit_saved_source_conforming_banks import legacy_line_polynomial, legacy_endpoint_depths, verify_incident_fans, nearby, knot_key

def old_port_witnesses(sections, profile):
    mesh = sections['mesh']
    owners = {}
    for number, section in enumerate(sections['edge_sections']):
        for triangle in section['triangle_indices']:
            require(triangle not in owners, 'old mesh face has multiple section owners')
            owners[triangle] = (number, section)
    incidence = defaultdict(list)
    for number, indices in enumerate(mesh['triangles']):
        for edge_index in range(3):
            pair = [mesh['vertices_xyz_m'][indices[edge_index]], mesh['vertices_xyz_m'][indices[(edge_index + 1) % 3]]]
            incidence[tuple(sorted((tuple(point) for point in pair)))].append((number, edge_index, pair))
    witnesses = []
    if len(profile) != 4:
        return witnesses
    for segment, pair in enumerate(zip(profile, profile[1:])):
        sides = incidence.get(tuple(sorted((tuple(point) for point in pair))), [])
        if len(sides) != 1:
            continue
        triangle_index, edge_index, points = sides[0]
        if triangle_index not in owners:
            continue
        section_index, section = owners[triangle_index]
        for profile_index, saved_profile in enumerate(section['cross_section_xyz_m']):
            if saved_profile == profile:
                witnesses.append(dict(profile_segment_index=segment, section_index=section_index, arc_id=section['arc_id'], profile_index=profile_index, triangle_index=triangle_index, edge_index=edge_index, points_xyz_m=points, original_triangle_vertex_indices=mesh['triangles'][triangle_index]))
    return witnesses

def projected_points(vertices_xyz_m):
    points = np.asarray(vertices_xyz_m, float)
    require(points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all(), 'invalid junction vertices')
    return points[:, [0, 2]]

def point_key(point):
    return tuple((round(float(value), 8) for value in point))

def positive_overlap(first, second):
    first, second = (np.asarray(first, float), np.asarray(second, float))
    for polygon in (first, second):
        for start, end in zip(polygon, np.roll(polygon, -1, axis=0)):
            direction = end - start
            length = float(np.linalg.norm(direction))
            require(length > 1e-10, 'degenerate overlap edge')
            axis = np.array([-direction[1], direction[0]]) / length
            first_projection, second_projection = (first @ axis, second @ axis)
            overlap = min(first_projection.max(), second_projection.max()) - max(first_projection.min(), second_projection.min())
            if overlap <= 1e-09:
                return False
    return True

def audit_mesh(vertices_xyz_m, triangles, *, require_positive=True, check_overlap=True):
    points = projected_points(vertices_xyz_m)
    incidence = defaultdict(list)
    shapes = []
    identities = set()
    for number, indices in enumerate(triangles):
        require(len(indices) == 3 and all((type(index) is int and 0 <= index < len(points) for index in indices)) and (len(set(indices)) == 3), 'invalid junction triangle indices')
        identity = tuple(sorted((point_key(points[index]) for index in indices)))
        require(identity not in identities, 'duplicate projected junction face')
        identities.add(identity)
        shape = points[indices]
        first, second = (shape[1] - shape[0], shape[2] - shape[0])
        signed_area = float(first[0] * second[1] - first[1] * second[0]) / 2
        require(signed_area > 1e-09 if require_positive else abs(signed_area) > 1e-09, 'nonpositive junction face area')
        shapes.append(shape)
        for edge_index in range(3):
            start, end = (point_key(points[indices[edge_index]]), point_key(points[indices[(edge_index + 1) % 3]]))
            key = tuple(sorted((start, end)))
            require(start != end, 'degenerate junction edge')
            incidence[key].append(dict(triangle_index=number, edge_index=edge_index, start=start, end=end))
            require(len(incidence[key]) <= 2, 'nonmanifold junction edge')
            if len(incidence[key]) == 2:
                first_side, second_side = incidence[key]
                require(first_side['start'] == second_side['end'] and first_side['end'] == second_side['start'], 'shared junction edge winding mismatch')
    if check_overlap:
        for number, shape in enumerate(shapes):
            for other in shapes[:number]:
                if np.any(shape.max(axis=0) <= other.min(axis=0) + 1e-09) or np.any(other.max(axis=0) <= shape.min(axis=0) + 1e-09):
                    continue
                require(not positive_overlap(shape, other), 'overlapping projected junction faces')
    return incidence

def boundary_coverage(vertices_xyz_m, triangles, profile_xyz_m):
    profile = projected_points(profile_xyz_m)
    require(profile.shape == (4, 2), 'port requires four actual profile points')
    points = projected_points(vertices_xyz_m)
    incidence = audit_mesh(vertices_xyz_m, triangles, require_positive=False, check_overlap=False)
    boundary = [sides[0] for sides in incidence.values() if len(sides) == 1]
    coverage = []
    for profile_index, (start, end) in enumerate(zip(profile, profile[1:])):
        vector = end - start
        length = float(np.linalg.norm(vector))
        require(length > 1e-08, 'degenerate four-point port interval')
        matches = []
        intervals = []
        for side in boundary:
            indices = triangles[side['triangle_index']]
            edge = points[[indices[side['edge_index']], indices[(side['edge_index'] + 1) % 3]]]
            offsets = edge - start
            distances = np.abs(offsets[:, 0] * vector[1] - offsets[:, 1] * vector[0]) / length
            fractions = offsets @ vector / (vector @ vector)
            if distances.max() > 1e-08 or fractions.min() < -1e-08 or fractions.max() > 1 + 1e-08:
                continue
            lower, upper = sorted(fractions.tolist())
            require(upper - lower > 1e-10, 'zero port coverage interval')
            intervals.append((lower, upper))
            matches.append(dict(triangle_index=side['triangle_index'], edge_index=side['edge_index'], direction=1 if fractions[1] > fractions[0] else -1, interval_t01=[lower, upper], profile_segment_index=profile_index))
        intervals_complete(intervals, 'actual three-piece triangle boundary port')
        coverage.append(matches)
    return coverage

def verify_reverse_ports(first_vertices, first_triangles, second_vertices, second_triangles, profile):
    first = boundary_coverage(first_vertices, first_triangles, profile)
    second = boundary_coverage(second_vertices, second_triangles, profile)
    for first_segment, second_segment in zip(first, second):
        for first_piece in first_segment:
            for second_piece in second_segment:
                lower = max(first_piece['interval_t01'][0], second_piece['interval_t01'][0])
                upper = min(first_piece['interval_t01'][1], second_piece['interval_t01'][1])
                if upper - lower > 1e-10:
                    require(first_piece['direction'] == -second_piece['direction'], 'ported junction requires reverse boundary winding')
    return (first, second)

def native_knots(hierarchy, start, end):
    metadata = hierarchy['metadata']
    origin, spacing = (np.asarray(metadata['origin_m_xz']), float(metadata['spacing_m']))
    first, second = (np.asarray(point, float) for point in (start, end))
    native_first, native_second = ((point - origin) / spacing for point in (first, second))
    fractions = [0.0, 1.0]
    for axis in range(2):
        delta = native_second[axis] - native_first[axis]
        if abs(delta) <= 1e-14:
            continue
        for index in range(math.floor(min(native_first[axis], native_second[axis])) + 1, math.ceil(max(native_first[axis], native_second[axis]))):
            fraction = (index - native_first[axis]) / delta
            if 1e-10 < fraction < 1 - 1e-10:
                fractions.append(float(fraction))
    fractions = sorted(set(fractions))
    return [first + fraction * (second - first) for fraction in fractions]

def fan_depth(fan, point):
    coefficients = np.asarray(fan['depth_coefficients_m_1xz'], float)
    origin = np.asarray(fan['depth_origin_xz_m'], float)
    require(coefficients.shape == (3,) and origin.shape == (2,) and np.isfinite(coefficients).all(), 'invalid saved affine face cut')
    return float(coefficients[0] + (np.asarray(point) - origin) @ coefficients[1:])

def segment_bed(hierarchy, selected, fan, start, end):
    source = native_edge_polynomial(hierarchy, selected, start, end)['source_height_polynomial_m']
    depths = [fan_depth(fan, point) for point in (start, end)]
    require(min(depths) >= 0 and max(depths) <= 4.0 + 1e-09, 'native face edge violates no-fill/maxcut')
    bed = np.asarray(source).copy()
    bed[:2] -= [depths[0], depths[1] - depths[0]]
    return bed

def verify_outer_function(hierarchy, selected, fan, start, end, old_points_xyz_m):
    knots = native_knots(hierarchy, start, end)
    for first, second in zip(knots, knots[1:]):
        actual = segment_bed(hierarchy, selected, fan, first, second)
        expected = legacy_line_polynomial(old_points_xyz_m, first, second)
        assert_close(actual, expected, 'complete source-native outer unchanged port function', atol=1e-09)

def verify_shared_function(hierarchy, selected, first_fan, second_fan, start, end):
    knots = native_knots(hierarchy, start, end)
    for first, second in zip(knots, knots[1:]):
        assert_close(segment_bed(hierarchy, selected, first_fan, first, second), segment_bed(hierarchy, selected, second_fan, first, second), 'whole shared junction native face function', atol=1e-09)

def verify_fan_wet_vertices(fan, hierarchy, selected, protection):
    for point in fan['vertices_xz_m']:
        height, reasons = source_sample(hierarchy, selected, point)
        require(not reasons, 'junction fan invalid original source')
        depth = fan_depth(fan, point)
        require(depth >= 0 and depth <= 4.0 + 1e-09, 'junction fan negative/excessive cut')
        require(not wet_at(hierarchy, protection, point, height) or depth <= 1e-09, 'junction fan cut old protected wet source')

def native_constraint_registry(record, all_faces, hierarchy):
    selected, registry = (set(record['selected_leaf_ids']), {})

    def register(point, depth):
        require(np.isfinite(depth), 'nonfinite independently rebuilt native knot depth')
        for previous in nearby(registry, point):
            assert_close(depth, previous[1], 'conflicting independently rebuilt legacy/stub native knot', atol=1e-09)
        registry.setdefault(knot_key(point), []).append((np.asarray(point), float(depth)))
    for arm in record['arms']:
        for first, second in zip(arm['outer_profile_xyz_m'], arm['outer_profile_xyz_m'][1:]):
            knots = native_knots(hierarchy, np.asarray(first)[[0, 2]], np.asarray(second)[[0, 2]])
            for start, end in zip(knots, knots[1:]):
                depths = legacy_endpoint_depths([first, second], start, end, hierarchy, selected)
                for point, depth in zip((start, end), depths):
                    register(point, depth)
    for proof in record['edge_proofs']:
        for side in proof['sides']:
            identifier = side['triangle_id']
            if not identifier.startswith('legacy06:'):
                continue
            require(identifier in all_faces and side['edge_index'] in (0, 1, 2), 'fabricated legacy native constraint reference')
            vertices = np.asarray(all_faces[identifier]['vertices_xyz_m'])
            edge = vertices[[side['edge_index'], (side['edge_index'] + 1) % 3]]
            assert_close(side['points_xyz_m'], edge, 'legacy native constraint original mesh reference', atol=1e-10)
            depths = legacy_endpoint_depths(edge, proof['start_xz_m'], proof['end_xz_m'], hierarchy, selected)
            for point, depth in zip((proof['start_xz_m'], proof['end_xz_m']), depths):
                register(point, depth)
    return registry

def reconstructed_depths(proof, registry, all_faces, record, hierarchy):
    selected = set(record['selected_leaf_ids'])
    support_points, support_depths = ([], [])
    for knot in proof['depth_support_knots']:
        point = np.asarray(knot['xz_m'])
        support_points.append(point)
        depths = []
        for reference in knot['original_vertex_refs']:
            identifier, edge_index = (reference['triangle_id'], reference['edge_index'])
            require(identifier in all_faces and edge_index in (0, 1, 2), 'fabricated original support vertex reference')
            vertices = np.asarray(all_faces[identifier]['vertices_xyz_m'])
            vertex = np.asarray(reference['xyz_m'])
            require(vertex.tolist() in vertices[[edge_index, (edge_index + 1) % 3]].tolist(), 'support reference is not actual original edge vertex')
            assert_close(vertex[[0, 2]], point, 'source support original vertex coordinates', atol=1e-08)
            height, reasons = source_sample(hierarchy, selected, point)
            require(not reasons and height - vertex[1] >= 0, 'original support source invalid/negative')
            depths.append(height - vertex[1])
        require(depths, 'missing actual support source vertex')
        assert_close(depths, np.full(len(depths), depths[0]), 'all original shared support depth values', atol=1e-09)
        support_depths.append(depths[0])
    require(len(support_points) == 2, 'native edge omitted original support interval')
    vector = support_points[1] - support_points[0]
    require(vector @ vector > 1e-16, 'degenerate original source-depth support')
    points = np.asarray([proof['start_xz_m'], proof['end_xz_m']])
    fractions = (points - support_points[0]) @ vector / (vector @ vector)
    require(fractions.min() >= -1e-08 and fractions.max() <= 1 + 1e-08, 'native segment outside original support interval')
    values = support_depths[0] + fractions * (support_depths[1] - support_depths[0])
    if proof['boundary_condition'] == 'explicit_source_bank_zero_depth_v3':
        values = np.zeros(2)
    constraints = proof['v3proof']['knot_constraints']
    require(len(constraints) == 2, 'native incident constraint endpoint census differs')
    for index, (point, saved) in enumerate(zip(points, constraints)):
        found = nearby(registry, point)
        require(bool(found) == (saved is not None), 'native incident constraint omitted/fabricated')
        if not found:
            continue
        assert_close([item[1] for item in found], np.full(len(found), found[0][1]), 'whole incident legacy/stub registry depth', atol=1e-09)
        values[index] = found[0][1]
        assert_close(saved['xz_m'], point, 'saved native constraint endpoint', atol=1e-08)
        assert_close(saved['cut_depth_m'], values[index], 'independently rebuilt source-oldline constraint', atol=1e-09)
        require(saved['conflicting_legacy_depth'] is False, 'candidate retained conflicting native constraint')
        if saved['legacy_triangle_id'] is not None:
            identifier, edge_index = (saved['legacy_triangle_id'], saved['legacy_edge_index'])
            require(identifier.startswith('legacy06:') and identifier in all_faces and (edge_index in (0, 1, 2)), 'false legacy incident constraint identity')
            vertices = np.asarray(all_faces[identifier]['vertices_xyz_m'])
            pair = vertices[[edge_index, (edge_index + 1) % 3]]
        else:
            require(saved['legacy_edge_index'] is None and saved['binding_kind'] == 'bound_original_section_open_stub', 'fabricated open stub legacy triangle identity')
            binding = saved['bound_original_section']
            arm = next((arm for arm in record['arms'] if arm['arc_id'] == binding['arc_id']), None)
            require(arm is not None and arm['attachment_status'] != 'actual_old_mesh', 'stub constraint falsely claims actual external mesh')
            segment_index = binding['profile_segment_index']
            require(segment_index in (0, 1, 2), 'invalid constraint bound profile segment')
            pair = arm['outer_profile_xyz_m'][segment_index:segment_index + 2]
            require(binding['original_points_xyz_m'] == pair and binding['external_mesh_attachment_claimed'] is False, 'constraint fabricated original bound profile')
        expected = legacy_endpoint_depths(pair, point, point, hierarchy, selected)
        assert_close(saved['cut_depth_m'], expected[0], 'actual legacy/stub constraint reference depth', atol=1e-09)
    require(np.isfinite(values).all() and values.min() >= 0 and (values.max() <= 4.0), 'rebuilt native edge strict nonnegative/maxcut failed')
    return values

def audit_saved_edges(record, sections, hierarchy):
    mesh, selected = (record['geometry'], set(record['selected_leaf_ids']))
    faces = {'junction:' + str(number): dict(triangle_id='junction:' + str(number), vertices_xyz_m=[mesh['vertices_xyz_m'][index] for index in indices], replacement_role=mesh['triangle_roles'][number], vertex_ids=indices) for number, indices in enumerate(mesh['triangles'])}
    groups = defaultdict(list)
    all_faces = dict(faces)
    for number in record['old_kept_mesh_triangle_ids']:
        all_faces['legacy06:' + str(number)] = dict(vertices_xyz_m=[sections['mesh']['vertices_xyz_m'][index] for index in sections['mesh']['triangles'][number]])
    for identifier, face in all_faces.items():
        vertices = np.asarray(face['vertices_xyz_m'])
        for edge_index in range(3):
            edge = vertices[[edge_index, (edge_index + 1) % 3]]
            groups[edge_key(edge[:, [0, 2]])].append((identifier, edge_index, edge))
    registry = native_constraint_registry(record, all_faces, hierarchy)
    edges, coverage = ({}, defaultdict(list))
    for proof in record['edge_proofs']:
        identifier = proof['segment_id']
        require(identifier not in edges, 'duplicate native junction segment identity')
        edges[identifier] = proof
        start, end = (np.asarray(proof['start_xz_m']), np.asarray(proof['end_xz_m']))
        actual = {}
        for face_id, edge_index, edge in groups[edge_key([start, end])]:
            vector = edge[1, [0, 2]] - edge[0, [0, 2]]
            offsets = np.array([start, end]) - edge[0, [0, 2]]
            distance = np.abs(offsets[:, 0] * vector[1] - offsets[:, 1] * vector[0]) / np.linalg.norm(vector)
            fractions = offsets @ vector / (vector @ vector)
            if distance.max() <= 1e-08 and 1e-10 < fractions.mean() < 1 - 1e-10:
                require(fractions.min() >= -1e-08 and fractions.max() <= 1 + 1e-08, 'junction segment omitted original T knot')
                actual[face_id, edge_index] = edge
                if face_id in faces:
                    coverage[face_id, edge_index].append(sorted(fractions.tolist()))
        saved = {(side['triangle_id'], side['edge_index']): side for side in proof['sides']}
        require(len(saved) == len(proof['sides']) and set(saved) == set(actual), 'junction omitted/duplicated actual kept neighbor side')
        require(1 <= len(actual) <= 2, 'nonmanifold junction native face')
        for key, edge in actual.items():
            assert_close(saved[key]['points_xyz_m'], edge, 'junction actual triangle edge provenance', atol=1e-10)
        require(proof['status'] == 'candidate' and (not proof['rejection_reasons']), 'refused native junction edge')
        native = native_edge_polynomial(hierarchy, selected, start, end)
        source = np.asarray(native['source_height_polynomial_m'])
        assert_close(proof['source']['source_coefficients_m_t012'], source, 'whole junction native source coefficients', atol=1e-09)
        require(proof['source']['patch_row_column'] == native['native_patch_row_column'], 'junction source patch binding differs')
        depths = {}
        for side in proof['side_depth_knots']:
            key = (side['triangle_id'], side['edge_index'])
            require(key in actual and key not in depths, 'duplicate/false junction cut side')
            values = np.asarray(side['depth_knots_m'])
            require(values.shape == (2,) and np.isfinite(values).all() and (values.min() >= 0) and (values.max() <= 4.0), 'junction edge violates strict nonnegative/maxcut')
            depths[key] = values
        require(set(depths) == set(actual), 'missing junction cut side')
        values = reconstructed_depths(proof, registry, all_faces, record, hierarchy)
        for other in depths.values():
            assert_close(values, other, 'saved final cut vs independently rebuilt native knot function', atol=1e-09)
        assert_close(proof['depth_coefficients_m_t01'], [values[0], values[1] - values[0]], 'junction cut coefficients', atol=1e-09)
        assert_close(proof['v3proof']['proposed_depth_coefficients_m_t01'], [values[0], values[1] - values[0]], 'independent proposed native cut coefficients', atol=1e-09)
        bed = source.copy()
        bed[:2] -= proof['depth_coefficients_m_t01']
        legacy = [key for key in actual if key[0].startswith('legacy06:')]
        neighbor_records = proof['v3proof']['unchanged_neighbor_polynomials']
        require(len(neighbor_records) == len(legacy), 'missing full kept neighbor polynomial witness')
        for key, witness in zip(legacy, neighbor_records):
            require((witness['triangle_id'], witness['edge_index']) == key, 'kept neighbor polynomial binding differs')
            expected = legacy_line_polynomial(actual[key], start, end)
            assert_close(witness['bed_coefficients_m_t012'], expected, 'kept neighbor complete saved polynomial', atol=1e-09)
            assert_close(bed, expected, 'whole unchanged 06 neighbor bed function', atol=1e-09)
        differences = proof['v3proof']['whole_coefficient_differences_m_t012']
        require(len(differences) == len(legacy), 'whole neighbor difference census differs')
        for key, witness in zip(legacy, differences):
            require((witness['triangle_id'], witness['edge_index']) == key, 'neighbor difference binding differs')
            assert_close(witness['difference_coefficients_m_t012'], bed - legacy_line_polynomial(actual[key], start, end), 'whole neighbor difference truth', atol=1e-09)
        if len(actual) == 2:
            directions = [edge[1, [0, 2]] - edge[0, [0, 2]] for edge in actual.values()]
            require(float(directions[0] @ directions[1]) < 0, 'native junction seam not reverse winding')
        binding = proof.get('bound_original_section')
        if binding is not None:
            require(len(actual) == 1 and (not legacy), 'old mesh port fabricated open stub')
            arm = next((item for item in record['arms'] if item['arc_id'] == binding['arc_id']), None)
            require(arm is not None and arm['attachment_status'] != 'actual_old_mesh', 'stub falsely claims old external attachment')
            index = binding['profile_segment_index']
            require(index in (0, 1, 2), 'invalid bound profile interval')
            pair = arm['outer_profile_xyz_m'][index:index + 2]
            for name in ('node_ids', 'outer_node_id', 'outer_section_index'):
                require(binding[name] == arm[name], 'open stub original section binding differs')
            require(binding['original_points_xyz_m'] == pair and binding['external_mesh_attachment_claimed'] is False, 'open stub fabricated original profile/attachment')
            expected = legacy_line_polynomial(pair, start, end)
            assert_close(binding['bed_coefficients_m_t012'], expected, 'bound original profile polynomial', atol=1e-09)
            assert_close(binding['difference_coefficients_m_t012'], bed - expected, 'bound original whole profile differences', atol=1e-09)
            assert_close(bed, expected, 'whole bound section open stub bed function', atol=1e-09)
        elif len(actual) == 1:
            require(values.max() <= 1e-09, 'unbound nonzero junction open edge')
        for point, depth in zip((start, end), values):
            height, reasons = source_sample(hierarchy, selected, point)
            require(not reasons, 'native port endpoint invalid original source')
            require(not wet_at(hierarchy, record['wet_protection'], point, height) or depth <= 1e-09, 'native port endpoint cut protected wet source')
    for face_id in faces:
        for edge_index in range(3):
            intervals_complete(coverage[face_id, edge_index], 'whole junction face boundary')
    functions = {}
    for function in record['source_functions']:
        face_id = function['triangle_id']
        require(face_id in faces and face_id not in functions, 'duplicate/false source junction face identity')
        face_edges = {identifier: edge for identifier, edge in edges.items() if any((side['triangle_id'] == face_id for side in edge['sides']))}
        require(function['status'] == 'candidate' and (not function['rejection_reasons']), 'refused whole junction face function')
        functions[face_id] = audit_function(function, faces[face_id], face_edges, hierarchy, selected, record['parameters'], record['wet_protection'])
        for fan in function['fans']:
            require(min(fan['depth_at_vertices_m']) >= 0 and max(fan['depth_at_vertices_m']) <= 4.0, 'strict fan nonnegative/maxcut violation')
            for patch in fan['native_patches']:
                heights = hierarchy['arrays']['height_m'].ravel()
                leaves = hierarchy['arrays']['contribution_owner'].ravel()
                stages = {item['leaf_id']: item['stage_m'] for item in record['wet_protection']['stage_by_leaf']}
                wet = set(patch['native_cell_ids']) & set(record['wet_protection']['covered_native_cell_ids'])
                wet |= {cell for cell in patch['native_cell_ids'] if heights[cell] < stages.get(int(leaves[cell]), -math.inf)}
                require(not wet or max(fan['depth_at_vertices_m']) == 0.0, 'native junction patch cut old wet support')
    require(set(functions) == set(faces), 'missing whole native junction face function')
    verify_incident_fans([fan for function in functions.values() for fan in function['fans']])
    check_memory()
    return (edges, faces)
