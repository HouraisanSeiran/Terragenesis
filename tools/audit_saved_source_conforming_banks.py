"""Consolidated audit_saved_source_conforming_banks implementations; numeric expressions preserved."""
from __future__ import annotations
import numpy as _i16_np
from tools.td_entry_saved_audit import assert_close as _i16_assert_close
import numpy as _i17_np
from collections import defaultdict as _i17_defaultdict
from tools.td_entry_saved_audit import assert_close as _i17_assert_close
from tools.audit_td_fine_bed_raster import _source as _i17__source
CATEGORY = 'B'

def native_edge_polynomial(hierarchy, selected_leaves, first_xz, second_xz):
    arrays, metadata = (hierarchy['arrays'], hierarchy['metadata'])
    bed = arrays['height_m']
    origin = _i16_np.asarray(metadata['origin_m_xz'], float)
    spacing = float(metadata['spacing_m'])
    first = (_i16_np.asarray(first_xz, float) - origin) / spacing
    second = (_i16_np.asarray(second_xz, float) - origin) / spacing
    if first.shape != (2,) or second.shape != (2,) or (not _i16_np.isfinite([first, second]).all()) or (_i16_np.linalg.norm(first - second) <= 1e-14):
        raise ValueError('invalid or degenerate saved native segment')
    shape = _i16_np.array(bed.shape[::-1])
    if _i16_np.any(_i16_np.minimum(first, second) < -1e-10) or _i16_np.any(_i16_np.maximum(first, second) > shape - 1 + 1e-10):
        raise ValueError('saved native edge outside source')
    patch = _i16_np.minimum(_i16_np.floor((first + second) / 2).astype(int), shape - 2)
    if _i16_np.any(_i16_np.minimum(first, second) < patch - 1e-09) or _i16_np.any(_i16_np.maximum(first, second) > patch + 1 + 1e-09):
        raise ValueError('saved native segment omitted a grid crossing')
    offset, delta = (first - patch, second - first)
    coefficients = _i16_np.zeros(3)
    provenance = []
    for delta_z, delta_x in ((0, 0), (0, 1), (1, 0), (1, 1)):
        x_value = offset[0] if delta_x else 1 - offset[0]
        z_value = offset[1] if delta_z else 1 - offset[1]
        x_delta = delta[0] if delta_x else -delta[0]
        z_delta = delta[1] if delta_z else -delta[1]
        weight = _i16_np.array([x_value * z_value, x_value * z_delta + x_delta * z_value, x_delta * z_delta])
        if _i16_np.all(weight == 0):
            continue
        row, column = (int(patch[1] + delta_z), int(patch[0] + delta_x))
        owner = int(arrays['cell_owner'][row, column])
        leaf = int(arrays['contribution_owner'][row, column])
        unknown = arrays['node_unknown_contact']
        if not arrays['valid_mask'][row, column] or arrays['protected_mask'][row, column] or arrays['open_boundary_mask'][row, column] or (leaf not in selected_leaves) or (owner < 0) or (owner >= len(unknown)) or (leaf < 0) or (leaf >= len(unknown)) or unknown[owner] or unknown[leaf] or (not _i16_np.isfinite(bed[row, column])):
            raise ValueError('native edge touches invalid/protected/unknown source')
        coefficients += weight * bed[row, column]
        provenance.append(dict(native_cell_id=row * bed.shape[1] + column, weight_polynomial=weight.tolist(), owner=owner, leaf=leaf))
    return dict(native_patch_row_column=[int(patch[1]), int(patch[0])], source_height_polynomial_m=coefficients.tolist(), provenance=provenance, parameter='t in [0,1], first + t*(second-first)')

def bed_edge_polynomial(source_coefficients, cut_first_m, cut_second_m):
    if not _i16_np.isfinite([cut_first_m, cut_second_m]).all() or min(cut_first_m, cut_second_m) < 0:
        raise ValueError('source-conforming edge has negative cut depth')
    result = _i16_np.asarray(source_coefficients, float).copy()
    if result.shape != (3,) or not _i16_np.isfinite(result).all():
        raise ValueError('invalid native edge polynomial')
    result[:2] -= [cut_first_m, cut_second_m - cut_first_m]
    return result

def reverse_polynomial(coefficients):
    constant, linear, quadratic = _i16_np.asarray(coefficients, float)
    return _i16_np.array([constant + linear + quadratic, -linear - 2 * quadratic, quadratic])

def verify_shared_segment(hierarchy, selected_leaves, first_xz, second_xz, first_side_cut, second_side_cut, *, second_reversed=False):
    source = native_edge_polynomial(hierarchy, selected_leaves, first_xz, second_xz)
    expected_first = bed_edge_polynomial(source['source_height_polynomial_m'], *first_side_cut)
    if second_reversed:
        second_side_cut = list(reversed(second_side_cut))
    expected_second = bed_edge_polynomial(source['source_height_polynomial_m'], *second_side_cut)
    _i16_assert_close(expected_first, expected_second, 'whole shared-edge polynomial', atol=1e-09)
    return dict(**source, derived_bed_polynomial_m=expected_first.tolist(), whole_segment_verified=True, proof='equal source quadratic and equal linear cut coefficients on complete native segment')
POLICY = {'algorithm': 'native-bilinear-minus-legacy-matched-shared-knot-affine-depth-fan-v3', 'legacy_depth': 'native_segment_source_minus_unchanged_legacy_line_whole_coefficients', 'legacy_quadratic': 'refuse_nonzero_source_quadratic_no_joint_neighbor_version', 'incident_knots': 'legacy_constraint_propagates_to_all_incident_edges_before_fan_build', 'interior_depth': 'original_shared_T_vertex_interpolation_unless_legacy_constrained', 'uncovered_nonzero': 'classify_from_original_sections_paths_but_refuse_without_bound_BC', 'nonnegative': 'strict_no_clamp', 'gates': 'unchanged_v2_maxcut_wet_source_coverage_atomic_signed_material'}

def knot_key(point):
    return tuple((int(_i17_np.floor(float(value) / 1e-08)) for value in point))

def nearby(registry, point):
    bucket = knot_key(point)
    return [record for horizontal in (-1, 0, 1) for vertical in (-1, 0, 1) for record in registry.get((bucket[0] + horizontal, bucket[1] + vertical), []) if _i17_np.max(_i17_np.abs(_i17_np.asarray(point) - record[0])) <= 1e-08]

def legacy_line_polynomial(points_xyz_m, start_xz_m, end_xz_m):
    points = _i17_np.asarray(points_xyz_m, float)
    endpoints = _i17_np.asarray([start_xz_m, end_xz_m], float)
    if points.shape != (2, 3) or endpoints.shape != (2, 2) or (not _i17_np.isfinite(points).all()) or (not _i17_np.isfinite(endpoints).all()):
        raise ValueError('invalid saved legacy line')
    vector = points[1, [0, 2]] - points[0, [0, 2]]
    squared_length = float(vector @ vector)
    if squared_length <= 1e-16:
        raise ValueError('degenerate saved legacy line')
    offsets = endpoints - points[0, [0, 2]]
    fractions = offsets @ vector / squared_length
    distance = _i17_np.abs(offsets[:, 0] * vector[1] - offsets[:, 1] * vector[0]) / _i17_np.sqrt(squared_length)
    if distance.max() > 1e-08 or fractions.min() < -1e-08 or fractions.max() > 1 + 1e-08:
        raise ValueError('native segment outside saved legacy line')
    heights = points[0, 1] + fractions * (points[1, 1] - points[0, 1])
    return _i17_np.array([heights[0], heights[1] - heights[0], 0.0])

def legacy_endpoint_depths(points_xyz_m, start, end, hierarchy, selected):
    legacy_line_polynomial(points_xyz_m, start, end)
    vertices = _i17_np.asarray(points_xyz_m, float)
    vector = vertices[1, [0, 2]] - vertices[0, [0, 2]]
    depths = []
    for point in (start, end):
        point = _i17_np.asarray(point, float)
        height, reasons, provenance = _i17__source(hierarchy['arrays'], hierarchy['metadata'], selected, point)
        if height is None:
            raise ValueError('unknown native legacy endpoint source')
        fraction = float((point - vertices[0, [0, 2]]) @ vector / (vector @ vector))
        old_height = float(vertices[0, 1] + fraction * (vertices[1, 1] - vertices[0, 1]))
        depths.append(height - old_height)
    return _i17_np.asarray(depths)

def incident_constraints(proofs, hierarchy, selected):
    registry = {}
    conflicts = set()
    for proof in proofs.values():
        legacy = [side for side in proof['sides'] if side['triangle_id'].startswith('legacy06:')]
        if not legacy:
            continue
        start, end = (proof['start_xz_m'], proof['end_xz_m'])
        for side in legacy:
            try:
                depths = legacy_endpoint_depths(side['points_xyz_m'], start, end, hierarchy, selected)
            except ValueError:
                continue
            for point, value in zip((start, end), depths):
                key = knot_key(point)
                existing = nearby(registry, point)
                if existing:
                    if abs(existing[0][1] - value) > 1e-09:
                        conflicts.add(knot_key(existing[0][0]))
                else:
                    registry.setdefault(key, []).append((_i17_np.asarray(point), float(value)))
    return (registry, conflicts)

def constrained_depths(start, end, default_depths, registry, conflicts):
    values = _i17_np.asarray(default_depths, float).copy()
    for index, point in enumerate((start, end)):
        found = nearby(registry, point)
        if any((knot_key(record[0]) in conflicts for record in found)):
            raise ValueError('conflicting incident native legacy knot')
        if found:
            _i17_assert_close([record[1] for record in found], _i17_np.full(len(found), found[0][1]), 'incident legacy knot constraints', atol=1e-09)
            values[index] = found[0][1]
    return values

def verify_v3proof(proof, source_coefficients, policy_identity, *, require_match=True):
    saved = proof['v3proof']
    if saved['policy_identity_sha256'] != policy_identity:
        raise ValueError('v3 edge policy identity differs')
    neighbors = [side for side in proof['sides'] if side['triangle_id'].startswith('legacy06:')]
    expected_rule = 'native_source_minus_legacy_line_v3' if neighbors else 'shared_incident_native_knot_depth_v3'
    if saved['depth_rule'] != expected_rule:
        raise ValueError('v3 edge depth rule differs')
    records = saved['unchanged_neighbor_polynomials']
    if len(records) != len(neighbors):
        raise ValueError('missing unchanged neighbor coefficient proof')
    differences = []
    bed = _i17_np.asarray(source_coefficients, float).copy()
    proposed = saved['proposed_depth_coefficients_m_t01']
    if proposed is None:
        if require_match or neighbors:
            raise ValueError('missing proposed native depth coefficients')
        return
    bed[:2] -= proposed
    for side, record in zip(neighbors, records):
        if (record['triangle_id'], record['edge_index']) != (side['triangle_id'], side['edge_index']):
            raise ValueError('unchanged neighbor proof binding differs')
        old_line = legacy_line_polynomial(side['points_xyz_m'], proof['start_xz_m'], proof['end_xz_m'])
        _i17_assert_close(record['bed_coefficients_m_t012'], old_line, 'saved unchanged native-segment coefficients', atol=1e-09)
        differences.append(dict(triangle_id=side['triangle_id'], edge_index=side['edge_index'], difference_coefficients_m_t012=(bed - old_line).tolist()))
        if require_match:
            _i17_assert_close(bed, old_line, 'whole unchanged neighbor coefficients', atol=1e-09)
    if len(saved['whole_coefficient_differences_m_t012']) != len(differences):
        raise ValueError('missing complete coefficient differences')
    for actual, expected in zip(saved['whole_coefficient_differences_m_t012'], differences):
        if actual['triangle_id'] != expected['triangle_id'] or actual['edge_index'] != expected['edge_index']:
            raise ValueError('coefficient difference neighbor binding differs')
        _i17_assert_close(actual['difference_coefficients_m_t012'], expected['difference_coefficients_m_t012'], 'saved complete coefficient differences', atol=1e-09)
    if require_match:
        _i17_assert_close(proposed, proof['depth_coefficients_m_t01'], 'proposed accepted depth coefficients', atol=1e-09)

def verify_knot_constraints(proof, registry, conflicts, hierarchy, selected, all_triangles):
    constraints = proof['v3proof']['knot_constraints']
    if len(constraints) != 2:
        raise ValueError('v3 native endpoint constraint census differs')
    for point, record in zip((proof['start_xz_m'], proof['end_xz_m']), constraints):
        found = nearby(registry, point)
        if record is None:
            if found:
                raise ValueError('omitted incident legacy native knot constraint')
            continue
        _i17_assert_close(record['xz_m'], point, 'constraint native endpoint binding', atol=1e-08)
        identifier = record['legacy_triangle_id']
        if not identifier.startswith('legacy06:') or identifier not in all_triangles:
            raise ValueError('fabricated unchanged legacy knot reference')
        edge_index = record['legacy_edge_index']
        if edge_index not in (0, 1, 2):
            raise ValueError('invalid unchanged legacy knot edge')
        vertices = _i17_np.asarray(all_triangles[identifier]['vertices_xyz_m'])
        edge = vertices[[edge_index, (edge_index + 1) % 3]]
        vector = edge[1, [0, 2]] - edge[0, [0, 2]]
        fraction = float((_i17_np.asarray(point) - edge[0, [0, 2]]) @ vector / (vector @ vector))
        _i17_assert_close(edge[0, [0, 2]] + fraction * vector, point, 'constraint lies on legacy edge', atol=1e-08)
        if fraction < -1e-08 or fraction > 1 + 1e-08:
            raise ValueError('constraint outside legacy edge')
        height, reasons, provenance = _i17__source(hierarchy['arrays'], hierarchy['metadata'], selected, _i17_np.asarray(point))
        if height is None:
            raise ValueError('unknown native constraint source')
        depth = height - (edge[0, 1] + fraction * (edge[1, 1] - edge[0, 1]))
        _i17_assert_close(record['cut_depth_m'], depth, 'independent incident constraint source-oldline', atol=1e-09)
        expected_conflict = any((knot_key(item[0]) in conflicts for item in found))
        if record['conflicting_legacy_depth'] and (not expected_conflict):
            for other_id, triangle in all_triangles.items():
                if not other_id.startswith('legacy06:'):
                    continue
                other_vertices = _i17_np.asarray(triangle['vertices_xyz_m'])
                for other_index in range(3):
                    endpoints = other_vertices[[other_index, (other_index + 1) % 3]]
                    direction = endpoints[1, [0, 2]] - endpoints[0, [0, 2]]
                    fraction = float((_i17_np.asarray(point) - endpoints[0, [0, 2]]) @ direction / (direction @ direction))
                    if fraction < -1e-08 or fraction > 1 + 1e-08:
                        continue
                    if _i17_np.max(_i17_np.abs(endpoints[0, [0, 2]] + fraction * direction - point)) > 1e-08:
                        continue
                    other_depth = height - (endpoints[0, 1] + fraction * (endpoints[1, 1] - endpoints[0, 1]))
                    expected_conflict |= abs(other_depth - depth) > 1e-09
            if not expected_conflict:
                raise ValueError('unsubstantiated legacy constraint conflict')
            conflicts.add(knot_key(point))

def boundary_evidence(sections, paths):
    incoming = _i17_defaultdict(list)
    arcs = {arc['arc_id']: arc for arc in paths['arcs']}
    nodes = {node['node_id']: node for node in sections['node_sections']}
    for arc in arcs.values():
        for first, second in zip(arc['node_ids'], arc['node_ids'][1:]):
            incoming[second].append(dict(arc_id=arc['arc_id'], from_node_id=first))
    result = {}
    mesh = sections['mesh']
    for number, section in enumerate(sections['edge_sections']):
        profiles = section.get('cross_section_xyz_m', [])
        if not profiles or not section.get('node_ids'):
            continue
        node_id = section['node_ids'][0]
        node, arc = (nodes.get(node_id), arcs.get(section['arc_id']))
        bound = arc is not None and arc['node_ids'][:2] == section['node_ids'][:2] and (node is not None) and (node.get('cross_section_xyz_m') == profiles[0]) and (not node.get('rejection_reasons', [])) and _i17_np.isfinite(node.get('representative_q_m3_s', _i17_np.nan)) and (node.get('representative_q_m3_s', 0.0) > 0.0)
        for triangle_index in section['triangle_indices']:
            indices = mesh['triangles'][triangle_index]
            for edge_index in range(3):
                points = [mesh['vertices_xyz_m'][indices[edge_index]], mesh['vertices_xyz_m'][indices[(edge_index + 1) % 3]]]
                if not any((points == [first, second] or points == [second, first] for first, second in zip(profiles[0], profiles[0][1:]))):
                    continue
                result[f'06:{triangle_index}:{edge_index}'] = dict(classification='upstream_profile_without_bound_BC' if bound and (not incoming[node_id]) else 'truncated_bank', sections_identity_sha256=sections['identity_sha256'], paths_identity_sha256=paths['identity_sha256'], section_index=number, arc_id=section['arc_id'], node_id=node_id, profile_index=0, original_edge_xyz_m=points, original_profile_xyz_m=profiles[0], ordinary_identity_sha256=sections.get('ordinary_identity_sha256'), representative_q_m3_s=None if node is None else node.get('representative_q_m3_s'), incoming_path_steps=incoming[node_id], section_path_profile_bound=bool(bound), boundary_condition_bound=False, hydraulic_inflow_claimed=False)
    return result

def verify_incident_fans(fans):
    registry = {}
    for points, origin, coefficients, fan_id in fans:
        points = _i17_np.asarray(points, float)
        values = coefficients[0] + (points - origin) @ coefficients[1:]
        for point, value in zip(points, values):
            found = nearby(registry, point)
            for record in found:
                _i17_assert_close(value, record[1], 'incident fan knot crack ' + fan_id, atol=1e-09)
            registry.setdefault(knot_key(point), []).append((point, float(value)))
