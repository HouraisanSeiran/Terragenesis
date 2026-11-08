"""Cold, independent topology/source audit of one saved ported junction."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from tools.audit_td_fine_bed_shards import digest, read, check_memory
from tools.audit_td_source_conforming_banks_v3 import assert_close, require, intervals_complete, source_sample, wet_at
from tools.td_ported_junction_saved_audit_v2 import audit_mesh, audit_saved_edges, old_port_witnesses, positive_overlap, projected_points, verify_reverse_ports, boundary_coverage
POLICY = {'schema': 'td-ported-junction-v1', 'arms': 'all_actual_three_land_channel_incident_arcs', 'outer': 'unchanged_four_point_profile_reverse_kept_06_seam_or_explicit_bound_section_open_stub', 'inner': 'independent_flow_normal_profile_preserve_each_outer_transverse_offsets_and_depths', 'ring': 'complete_four_point_ports_in_radial_order_star_center_triangulation', 'source': 'native_bilinear_minus_shared_nonnegative_affine_depth_fans', 'outer_native_knots': 'actual_native_source_minus_unchanged_legacy_line_whole_coefficients', 'wet': 'original_source_gates_and_conservative_native_patch_wet_guard', 'max_cut_m': 4.0, 'replacement': 'whole_component_all_or_none_no_fine_cells_or_material_effects'}
POLICY_SHA256 = digest(POLICY)
PATHS_SHA256 = '4db1e25e6b0d1f7ed5443e10a6eaabb467ac95e4669ea57f88d8e7f1bac2fd1b'
SECTIONS_SHA256 = '0d867183f2dc404c56959912bb4edacc559215d50c2075ac6769277e54ba8935'
HIERARCHY_SHA256 = '36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422'
SOURCE_FUNCTION_POLICY_SHA256 = '586f5ec92dc2320073b3f7dbd3ced1225759f6888d573aad750e19c4fc7f0d09'
FIXED_JSON_PINS = {'06_index': 'fec57d5c9df599ba3c419d2283910d27afe172c236743b3536769bf579af662b', '06_paths': PATHS_SHA256, '06_sections': SECTIONS_SHA256, 'source_bank_parent_index': 'aac571e0a6f0b730e0ebd5c67db9ac9182f2f1398409754d33d9d66273fc277e', 'source_bank_parent_audit': 'c410f1871d8b17cee5b48cb2ba141f3cce41b447daa042ddb8637abdc42041d9', 'wet_protection_manifest': 'b1e901474ecefc3674ffcdc3fc949d03662910cb4bf7e3b4949c35ea341b3651'}

def content_identity(record):
    require(record['identity_sha256'] == digest({name: value for name, value in record.items() if name != 'identity_sha256'}), 'ported record content identity differs')

def audit_parent_evidence(record, paths, sections):
    nodes = {node['node_id']: node for node in paths['nodes']}
    node_sections = {section['node_id']: (number, section) for number, section in enumerate(sections['node_sections'])}
    hub_id = record['hub_node_id']
    require(hub_id in nodes and hub_id in node_sections, 'junction hub absent from original parents')
    hub_index, hub = node_sections[hub_id]
    require(record['hub_section_index'] == hub_index and record['hub_parent_section'] == hub, 'junction changed original hub section')
    arcs = [(number, arc) for number, arc in enumerate(paths['arcs']) if arc['kind'] == 'land_channel' and len(arc['node_ids']) == 2 and (hub_id in arc['node_ids'])]
    arc_ids = sorted((arc['arc_id'] for number, arc in arcs))
    require(record['requested_replacement_arc_ids'] == arc_ids, 'junction omitted/fabricated actual incident arc')
    arms = {arm['arc_id']: arm for arm in record['arms']}
    require(len(arms) == len(record['arms']) and set(arms) == set(arc_ids), 'junction duplicate/missing actual arm')
    failures = []
    if len(arcs) != 3:
        failures.append('hub_requires_exactly_three_actual_land_arms')
    if hub.get('anchor'):
        failures.append('hub_anchor_refused')
    failures.extend(('hub_parent:' + reason for reason in hub.get('rejection_reasons', []) if reason != 'needs_junction_patch'))
    diagnostics = {item['arc_id']: item for item in sections['reach_diagnostics']}
    attachments = 0
    for arc_index, arc in arcs:
        arm = arms[arc['arc_id']]
        outer_id = next((identifier for identifier in arc['node_ids'] if identifier != hub_id))
        require(outer_id in node_sections, 'outer arm missing original section')
        outer_index, outer = node_sections[outer_id]
        profile = outer.get('cross_section_xyz_m', [])
        require(arm['path_arc_index'] == arc_index and arm['node_ids'] == arc['node_ids'] and (arm['outer_node_id'] == outer_id) and (arm['outer_section_index'] == outer_index), 'junction fabricated original directed arm provenance')
        require(arm['outer_profile_xyz_m'] == profile and arm['outer_parent_rejection_reasons'] == outer.get('rejection_reasons', []) and (arm['outer_anchor'] == bool(outer.get('anchor'))), 'junction changed original outer profile/rejection')
        witnesses = old_port_witnesses(sections, profile)
        require(arm['outer_old_mesh_edge_witnesses'] == witnesses, 'old mesh port witness census/provenance differs')
        complete = sorted((witness['profile_segment_index'] for witness in witnesses)) == [0, 1, 2]
        expected_attachment = 'actual_old_mesh' if complete else 'bound_original_section_no_accepted_external_strip'
        require(arm['attachment_status'] == expected_attachment, 'arm promoted profile declaration to old mesh attachment')
        attachments += complete
        arm_failures = list(outer.get('rejection_reasons', []))
        if outer.get('anchor'):
            arm_failures.append('outer_anchor_refused')
        points = np.asarray(profile, float)
        flow = np.asarray(nodes[arc['node_ids'][1]]['xyz_m'])[[0, 2]] - np.asarray(nodes[arc['node_ids'][0]]['xyz_m'])[[0, 2]]
        length = float(np.linalg.norm(flow))
        require(length > 1e-08, 'degenerate actual original arm')
        flow /= length
        assert_close(arm['flow_unit_xz'], flow, 'original directed arm unit vector', atol=1e-10)
        assert_close(arm['arm_length_m'], length, 'original arm length', atol=1e-10)
        if points.shape != (4, 3) or not np.isfinite(points).all():
            arm_failures.append('missing_or_invalid_outer_four_point_profile')
        else:
            relative = points[:, [0, 2]] - np.asarray(nodes[outer_id]['xyz_m'])[[0, 2]]
            offsets = relative @ np.array([-flow[1], flow[0]])
            if np.max(np.abs(relative @ flow)) > 1e-08 or not offsets[0] < offsets[1] < 0 < offsets[2] < offsets[3] or np.min(np.diff(offsets)) <= 1e-08:
                arm_failures.append('outer_profile_not_ordered_transverse_to_actual_arc')
        if witnesses and (not complete):
            arm_failures.append('outer_profile_partially_attached_kept_mesh')
        diagnostic = diagnostics.get(arc['arc_id'])
        require(arm['parent_incident_diagnostic'] == diagnostic, 'junction changed original incident diagnostic')
        if diagnostic is None:
            arm_failures.append('incident_arc_missing_parent_diagnostic')
        else:
            arm_failures.extend(('incident_parent:' + reason for reason in diagnostic['rejection_reasons'] if reason != 'needs_junction_patch'))
        require(set(arm_failures) == set(arm['rejection_reasons']), 'arm parent refusal reasons differ')
        failures.extend((arc['arc_id'] + ':' + reason for reason in arm_failures))
    if any((section['arc_id'] in arc_ids and section['triangle_indices'] for section in sections['edge_sections'])):
        failures.append('requested_incident_arc_already_has_accepted_06_mesh')
    return (failures, attachments, nodes)

def audit_ports(record, edges):
    mesh = record['geometry']
    roles = mesh['triangle_roles']
    ports = {(proof['arc_id'], proof['kind']): proof for proof in record['port_proofs']}
    require(len(ports) == len(record['port_proofs']) == 6, 'missing/duplicate complete three-arm port proofs')
    for arm in record['arms']:
        for kind in ('outer', 'inner'):
            proof = ports[arm['arc_id'], kind + '_port_proof']
            require(proof['node_ids'] == arm['node_ids'] and proof['profile_vertex_ids'] == arm[kind + '_profile_vertex_ids'], 'port original arm/profile identity binding differs')
            require(proof['status'] == 'candidate' and (not proof['rejection_reasons']), 'incomplete/refused internal junction port')
            require(len(proof['profile_segments']) == 3, 'port did not preserve all four profile points')
            for number, segment in enumerate(proof['profile_segments']):
                require(segment['profile_segment_index'] == number, 'port segment order/identity differs')
                profile_ids = proof['profile_vertex_ids']
                points = [mesh['vertices_xyz_m'][index] for index in profile_ids[number:number + 2]]
                require(segment['points_xyz_m'] == points, 'port segment not actual mesh profile')
                start, end = np.asarray(points)[:, [0, 2]]
                vector = end - start
                expected = []
                for edge in edges.values():
                    offsets = np.asarray([edge['start_xz_m'], edge['end_xz_m']]) - start
                    distances = np.abs(offsets[:, 0] * vector[1] - offsets[:, 1] * vector[0]) / np.linalg.norm(vector)
                    fractions = offsets @ vector / (vector @ vector)
                    if distances.max() > 1e-08 or fractions.min() < -1e-08 or fractions.max() > 1 + 1e-08:
                        continue
                    new = [side for side in edge['sides'] if side['triangle_id'].startswith('junction:')]
                    regions = [roles[int(side['triangle_id'].split(':')[1])] for side in new]
                    if kind == 'inner':
                        require(len(new) == len(edge['sides']) == 2 and {item['region'] for item in regions} == {'hub', 'arm'}, 'inner profile not shared actual hub/arm triangle boundary')
                        require(dict(region='arm', arc_id=arm['arc_id']) in regions, 'inner port joined a different actual arm')
                    else:
                        require(len(new) == 1 and regions[0] == dict(region='arm', arc_id=arm['arc_id']), 'outer profile not actual requested arm triangle boundary')
                        if arm['attachment_status'] == 'actual_old_mesh':
                            require(len(edge['sides']) == 2 and edge['bound_original_section'] is None, 'outer old mesh not truly attached')
                        else:
                            require(len(edge['sides']) == 1 and edge['bound_original_section'] is not None, 'open stub fabricated second side')
                    directions = [np.asarray(side['points_xyz_m'])[1, [0, 2]] - np.asarray(side['points_xyz_m'])[0, [0, 2]] for side in edge['sides']]
                    reverse = len(directions) == 2 and float(directions[0] @ directions[1]) < 0
                    require(reverse or (kind == 'outer' and arm['attachment_status'] != 'actual_old_mesh'), 'port seam lacks reverse winding')
                    expected.append(dict(segment_id=edge['segment_id'], interval_t01=sorted(fractions.tolist()), side_refs=[dict(triangle_id=side['triangle_id'], edge_index=side['edge_index']) for side in edge['sides']], reverse_seam=reverse))
                actual = segment['native_pieces']
                require(len(actual) == len(expected), 'port native piece census differs')
                for saved, observed in zip(actual, expected):
                    require(saved['segment_id'] == observed['segment_id'] and saved['side_refs'] == observed['side_refs'] and (saved['reverse_seam'] == observed['reverse_seam']), 'saved port native identity/provenance differs')
                    assert_close(saved['interval_t01'], observed['interval_t01'], 'complete native port intervals', atol=1e-09)
                intervals_complete([item['interval_t01'] for item in expected], 'entire four-point port native coverage')
            expected_attachment = arm['attachment_status'] if kind == 'outer' else 'internal_arm_hub_shared_profile'
            require(proof['attachment_status'] == expected_attachment, 'port misstated actual external attachment')

def audit_geometry(record, sections, hierarchy, nodes):
    mesh = record['geometry']
    require(0 < len(mesh['triangles']) <= 256 and len(mesh['triangle_roles']) == len(mesh['triangles']), 'missing/oversized junction face geometry')
    audit_mesh(mesh['vertices_xyz_m'], mesh['triangles'])
    points = projected_points(mesh['vertices_xyz_m'])
    require(len(mesh['vertex_depths_m']) == len(points), 'missing junction vertex cut depths')
    selected = set(record['selected_leaf_ids'])
    for vertex, saved_depth in zip(mesh['vertices_xyz_m'], mesh['vertex_depths_m']):
        height, reasons = source_sample(hierarchy, selected, np.asarray(vertex)[[0, 2]])
        require(not reasons and np.isfinite(saved_depth) and (0 <= saved_depth <= 4.0), 'junction vertex invalid source/no-fill/maxcut')
        assert_close(height - vertex[1], saved_depth, 'saved source-relative display vertex', atol=1e-09)
        require(not wet_at(hierarchy, record['wet_protection'], np.asarray(vertex)[[0, 2]], height) or saved_depth == 0.0, 'junction vertex cuts old wet support')
    require(len(mesh['ring_vertex_indices']) == len(set(mesh['ring_vertex_indices'])) == 12, 'junction ring missing actual four-point ports')
    expected_ring = {index for arm in record['arms'] for index in arm['inner_profile_vertex_ids']}
    require(set(mesh['ring_vertex_indices']) == expected_ring, 'hub ring substituted bank-only/profile declarations')
    center = np.asarray(nodes[record['hub_node_id']]['xyz_m'])[[0, 2]]
    assert_close(points[mesh['hub_center_vertex_id']], center, 'hub center original node', atol=1e-09)
    hub_triangles = [indices for indices, role in zip(mesh['triangles'], mesh['triangle_roles']) if role['region'] == 'hub']
    require(len(hub_triangles) == 12, 'hub ring incomplete triangle coverage')
    for indices, role in zip(mesh['triangles'], mesh['triangle_roles']):
        require(role['region'] in {'hub', 'arm'}, 'unknown junction face role')
        if role['region'] == 'hub':
            require(role == dict(region='hub', hub_node_id=record['hub_node_id']) and mesh['hub_center_vertex_id'] in indices, 'hub face wrong provenance/center')
    for arm in record['arms']:
        outer_ids, inner_ids = (arm['outer_profile_vertex_ids'], arm['inner_profile_vertex_ids'])
        require(len(outer_ids) == len(inner_ids) == 4 and len(set(outer_ids + inner_ids)) == 8, 'arm port vertex identities missing/duplicated')
        outer = np.asarray(arm['outer_profile_xyz_m'])
        assert_close(np.asarray(mesh['vertices_xyz_m'])[outer_ids], outer, 'unchanged original four-point outer mesh profile', atol=1e-10)
        flow = np.asarray(arm['flow_unit_xz'])
        normal = np.array([-flow[1], flow[0]])
        offsets = (outer[:, [0, 2]] - np.asarray(nodes[arm['outer_node_id']]['xyz_m'])[[0, 2]]) @ normal
        radial = np.asarray(nodes[arm['outer_node_id']]['xyz_m'])[[0, 2]] - center
        radial /= np.linalg.norm(radial)
        require(0 < arm['inset_m'] < 0.5 * arm['arm_length_m'], 'inner port inset not finite positive actual arm')
        expected_points = center + radial * arm['inset_m'] + offsets[:, None] * normal
        assert_close(points[inner_ids], expected_points, 'actual independently directed inner profile', atol=1e-09)
        assert_close(arm['outer_transverse_offsets_m'], offsets, 'each arm preserved original transverse offsets', atol=1e-09)
        assert_close(arm['preserved_outer_channel_width_m'], offsets[2] - offsets[1], 'arm original channel width', atol=1e-09)
        assert_close(np.asarray(mesh['vertex_depths_m'])[inner_ids], np.asarray(mesh['vertex_depths_m'])[outer_ids], 'preserved arm profile cut depths', atol=1e-09)
        assert_close(arm['inner_profile_xyz_m'], np.asarray(mesh['vertices_xyz_m'])[inner_ids], 'saved inner actual profile vertices', atol=1e-10)
        arm_triangles = [indices for indices, role in zip(mesh['triangles'], mesh['triangle_roles']) if role == dict(region='arm', arc_id=arm['arc_id'])]
        require(len(arm_triangles) == 6, 'arm strip is not a complete three-quad replacement')
        verify_reverse_ports(mesh['vertices_xyz_m'], arm_triangles, mesh['vertices_xyz_m'], hub_triangles, arm['inner_profile_xyz_m'])
        boundary_coverage(mesh['vertices_xyz_m'], arm_triangles, arm['outer_profile_xyz_m'])
    require(len(mesh['triangles']) == 30, 'extraneous/omitted three-arm junction face')
    old = np.asarray(sections['mesh']['vertices_xyz_m'])[np.asarray(sections['mesh']['triangles'])]
    old_projected = old[:, :, [0, 2]]
    for indices in mesh['triangles']:
        triangle = points[indices]
        nearby = np.flatnonzero(np.all(old_projected.max(axis=1) > triangle.min(axis=0) + 1e-09, axis=1) & np.all(old_projected.min(axis=1) < triangle.max(axis=0) - 1e-09, axis=1))
        for number in nearby:
            require(not positive_overlap(triangle, old_projected[number]), 'new strip/hub overlaps unchanged old mesh')
    edges, faces = audit_saved_edges(record, sections, hierarchy)
    audit_ports(record, edges)
    return dict(triangles=len(faces), native_segments=len(edges), full_four_point_ports=6)

def audit(record, paths, sections, hierarchy):
    content_identity(record)
    require(record['schema'] == 'td-ported-junction-v1' and record['policy'] == POLICY and (record['policy_identity_sha256'] == POLICY_SHA256), 'ported junction schema/policy differs')
    require(record['source_function_policy_identity_sha256'] == SOURCE_FUNCTION_POLICY_SHA256, 'source function policy lineage differs')
    require(record['parents'] == dict(hierarchy=hierarchy['identity_sha256'], paths=paths['identity_sha256'], sections=sections['identity_sha256'], source=hierarchy['metadata']['source_identity_sha256']), 'junction original parent identities differ')
    require(paths['hierarchy_identity_sha256'] == sections['hierarchy_identity_sha256'] == hierarchy['identity_sha256'] and paths['source_identity_sha256'] == sections['source_identity_sha256'] == hierarchy['metadata']['source_identity_sha256'] and (paths['ordinary_identity_sha256'] == sections['ordinary_identity_sha256']), 'original parent source/ordinary linkage differs')
    require(record['selected_leaf_ids'] == sections['selected_leaf_ids'], 'junction changed selected original source domain')
    require(record['parameters'] == dict(max_cut_m=4.0, conflict_tolerance_m=1e-09), 'junction enlarged original no-fill/maxcut gates')
    require(record['budgets']['max_bytes'] <= 64 * 1024 ** 2 and record['budgets']['max_rss_bytes'] <= 1024 ** 3 and (record['budgets']['max_triangles'] <= 256), 'junction resource budgets enlarged')
    transaction = record['transaction']
    kept = list(range(len(sections['mesh']['triangles'])))
    require(record['old_kept_mesh_triangle_ids'] == transaction['old_kept_triangle_indices'] == kept and transaction['replaced_original_triangle_indices'] == [], 'junction silently replaced/truncated original incident mesh')
    require(transaction['atomic'] is True and transaction['original_06_kept_unchanged'] is True and (transaction['parent_rejection_reasons_unchanged'] is True) and (transaction['fine_cells_replaced'] == 0) and (transaction['material_effects_generated'] is False), 'junction violates atomic saved-only replacement scope')
    for group in (record['edge_proofs'], record['source_functions'], record['port_proofs']):
        identities = set()
        for item in group:
            content_identity(item)
            require(item['status'] in {'candidate', 'refused'}, 'unknown junction child status')
            require(item['identity_sha256'] not in identities, 'duplicate junction proof/function content identity')
            identities.add(item['identity_sha256'])
    for edge in record['edge_proofs']:
        require(edge['policy_identity_sha256'] == edge['v3proof']['policy_identity_sha256'] == POLICY_SHA256, 'junction edge policy differs')
        expected = None if edge['status'] != 'candidate' else digest(dict(start_xz_m=edge['start_xz_m'], end_xz_m=edge['end_xz_m'], source=edge['source'], depth_coefficients_m_t01=edge['depth_coefficients_m_t01'], policy_identity_sha256=POLICY_SHA256))
        require(edge['common_function_identity_sha256'] == expected, 'junction common complete source/depth identity differs')
    require(all((function['policy_identity_sha256'] == POLICY_SHA256 for function in record['source_functions'])), 'junction face policy differs')
    failures, attachments, nodes = audit_parent_evidence(record, paths, sections)
    require(record['status'] in {'candidate', 'refused'}, 'unknown junction status')
    geometry_result, geometry_error = ({}, None)
    if record['geometry']['triangles']:
        try:
            geometry_result = audit_geometry(record, sections, hierarchy, nodes)
        except ValueError as error:
            geometry_error = str(error)
    else:
        require(not record['edge_proofs'] and (not record['source_functions']) and (not record['port_proofs']), 'empty mesh has unsupported junction proofs')
    accepted = record['status'] == 'candidate'
    if accepted:
        require(not failures and (not record['rejection_reasons']) and geometry_result and (geometry_error is None), 'junction candidate lacks independent full geometry proof: ' + str(geometry_error or failures))
    else:
        require(record['rejection_reasons'] and (failures or geometry_error), 'unsubstantiated whole junction refusal')
        require(set(failures) <= set(record['rejection_reasons']), 'junction omitted real original-parent refusal')
    require(transaction['candidate_replacement_arc_ids'] == (record['requested_replacement_arc_ids'] if accepted else []), 'partial/refused requested arc replacement')
    require(record['geometry_through_connection'] is accepted and record['internal_three_arm_geometry_candidate'] is accepted, 'junction misstated internal three-port geometry readiness')
    require(record['actual_external_attachment_count'] == (attachments if accepted else 0) and record['external_closure_verified'] is (accepted and attachments == 3), 'junction promoted open stub to external closure')
    for flag in ('bed_changed', 'fine_generated', 'hydraulic_solved', 'hydraulic_ready', 'full_river_verified', 'natural_outlet_certified', 'material_budget_verified', 'full_network_verified'):
        require(record[flag] is False, 'junction promoted local geometry to unrelated certification')
    return dict(schema='td-ported-junction-independent-audit-v2', status='passed', junction_status=record['status'], hub_node_id=record['hub_node_id'], internal_three_arm_geometry_verified=accepted, source_native_whole_face_functions_verified=accepted, actual_external_attachment_count=attachments if accepted else 0, parent_complete_mesh_port_evidence_count=attachments, external_closure_verified=accepted and attachments == 3, refusal_evidence_verified=not accepted, parent_refusal_witnesses=failures, independent_geometry_refusal=geometry_error, geometry=geometry_result if accepted else {}, full_network_verified=False, hydraulic_solved=False, fine_generated=False, source_bed_unchanged=True, actual_peak_audit_rss_bytes=check_memory(), scope='one atomic internal three-arm candidate or evidenced refusal; open stub is not external mesh closure or hydraulics')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / 'verification/natural-river-network'), 'new bounded junction audit output required')
    index = read(dict(path=str(args.input.resolve()), sha256=args.sha256))
    require(index['schema'] == 'td-ported-junction-preparation-v1' and index['policy_identity_sha256'] == POLICY_SHA256, 'junction preparation schema/policy differs')
    pins = index['inputs']
    require(set(pins) == set(FIXED_JSON_PINS) | {'hierarchy'}, 'junction immutable input pin census differs')
    loaded = {}
    for name, expected_sha in FIXED_JSON_PINS.items():
        require(pins[name]['sha256'] == expected_sha, 'fixed original JSON pin differs: ' + name)
        loaded[name] = read(pins[name])
    for name, sha in index['code_sha256'].items():
        require(file_sha256(ROOT / name) == sha, 'junction generator/code pin changed')
    paths_pin, sections_pin, hierarchy_pin = (pins['06_paths'], pins['06_sections'], pins['hierarchy'])
    require(paths_pin['sha256'] == PATHS_SHA256 and sections_pin['sha256'] == SECTIONS_SHA256 and (hierarchy_pin['sha256'] == HIERARCHY_SHA256), 'fixed 06/native source pins differ')
    paths, sections = (loaded['06_paths'], loaded['06_sections'])
    parent_index = loaded['06_index']
    require(parent_index['paths']['sha256'] == PATHS_SHA256 and parent_index['sections']['sha256'] == SECTIONS_SHA256 and (parent_index['inputs']['hierarchy']['sha256'] == HIERARCHY_SHA256), '06 original index path/section/native source binding differs')
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin['path']), expected_sha256=hierarchy_pin['sha256'], expected_identity=hierarchy_pin['identity_sha256'])
    record = read(index['junction'])
    require(record['inputs'] == pins, 'junction/index original input pins differ')
    wet_parent = loaded['wet_protection_manifest']
    source_index, source_audit = (loaded['source_bank_parent_index'], loaded['source_bank_parent_audit'])
    require(source_audit['status'] == 'passed' and source_audit['index_sha256'] == pins['source_bank_parent_index']['sha256'] and (source_audit['manifest_sha256'] == source_index['manifest']['sha256'] == pins['wet_protection_manifest']['sha256']), 'frozen source-bank wet audit linkage differs')
    require(wet_parent['sections_identity_sha256'] == sections['identity_sha256'] and wet_parent['paths_identity_sha256'] == paths['identity_sha256'] and (wet_parent['hierarchy_identity_sha256'] == hierarchy['identity_sha256']), 'original wet protection source domain binding differs')
    require(record['wet_protection'] == wet_parent['wet_protection'], 'junction changed original wet protection')
    for name in ('status', 'hub_node_id', 'requested_replacement_arc_ids', 'rejection_reasons', 'internal_three_arm_geometry_candidate', 'actual_external_attachment_count', 'external_closure_verified', 'full_network_verified'):
        require(index[name] == record[name], 'index/junction readiness metadata differs: ' + name)
    require(index['independent_audit_passed'] is False and index['resource']['actual_peak_rss_bytes'] <= 1024 ** 3 and (index['resource']['max_rss_bytes'] <= 1024 ** 3) and (index['resource']['max_json_bytes'] <= 64 * 1024 ** 2) and (index['resource']['solver_calls'] == index['resource']['fine_cells_generated'] == 0) and (index['resource']['old_packages_modified'] is False), 'junction preparation certification/resource scope differs')
    result = audit(record, paths, sections, hierarchy)
    result.update(index_sha256=args.sha256, junction_sha256=index['junction']['sha256'], junction_identity_sha256=record['identity_sha256'], inputs=record['inputs'], policy_identity_sha256=POLICY_SHA256, audit_code_sha256={name: file_sha256(ROOT / name) for name in ('tools/audit_td_ported_junction_v2.py', 'tools/td_ported_junction_saved_audit_v2.py', 'tools/audit_td_source_conforming_banks_v3.py', 'tools/audit_saved_source_conforming_banks.py', 'tools/audit_saved_source_conforming_banks.py', 'tools/audit_td_fine_bed_raster.py', 'tools/audit_td_fine_bed_shards.py')})
    publish_bytes(output, (json.dumps(result, sort_keys=True, allow_nan=False, indent=2) + '\n').encode())
    print(json.dumps(result, allow_nan=False))
if __name__ == '__main__':
    main()
