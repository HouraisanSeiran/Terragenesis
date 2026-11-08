"""Cold audit of atomic saved hubs and full-boundary composition evidence."""
import argparse
import gc
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from tools.audit_td_fine_bed_shards import read, digest, check_memory
from tools.audit_td_source_conforming_banks_v3 import require
from tools.audit_td_ported_junction_v3 import audit as audit_junction, FIXED_JSON_PINS, HIERARCHY_SHA256, content_identity
from tools.td_ported_network_saved_audit import SelectionAudit, census_hubs, compare, topology
AUDIT_SCHEMA = 'td-ported-network-independent-audit-v3'
POLICY = {'schema': 'td-ported-network-composition-v1', 'census': 'all_actual_three_land_channel_arms_q_descending', 'selection': 'whole_hub_atomic_missing_unique_arcs_original_06_unchanged', 'ports': 'actual_three_boundary_segments_reverse_whole_native_function_union_partition', 'conflicts': 'positive_projected_overlap_partial_edge_contact_nonmanifold_or_unbound_seam_refuse_whole_hub', 'source': 'unchanged_frozen_ported_junction_native_source_nonnegative_cut_wet_guards', 'topology': 'full_section_geometry_connections_not_node_id_adjacency_candidate_until_independent_audit', 'max_hubs': 256, 'max_json_bytes': 64 * 1024 ** 2, 'max_rss_bytes': 1024 ** 3}
POLICY_SHA256 = digest(POLICY)
FROZEN_CODE = {'terrain_pipeline/td_ported_network_composition.py': 'b4db872c525aa65a186afb25857fc7edd7cf725a8a37f4f90c48c643227c9165', 'tools/prepare_td_ported_network_composition.py': 'a6182f7f1e15e5b9ef866c5def5b11f3ea2940706900347f81cf77f553bd1df3', 'tests/test_td_ported_network_composition.py': '08ecf11221ccbee91c33d54d7ca9240f7f43a73008782f3d0d47213f0646083e', 'tools/audit_td_ported_junction_v3.py': '06e85216a416bec7f465cbe7dcf72f6073cd7cb4208bf7a09e1dc9b1c93713a9', 'tools/td_ported_junction_saved_audit_v3.py': '902a218d17a46dcbc45df1c28d7dca8662bc3d6277d6980e33df0df103981221'}
FALSE_FLAGS = ('independent_audit_passed', 'full_network_verified', 'fine_generated', 'hydraulic_ready', 'material_budget_verified')

def parent_inputs(pins):
    require(set(pins) == set(FIXED_JSON_PINS) | {'hierarchy'}, 'immutable input pin census differs')
    loaded = {}
    for name, expected in FIXED_JSON_PINS.items():
        require(pins[name]['sha256'] == expected, 'fixed original input SHA differs: ' + name)
        loaded[name] = read(pins[name])
    hierarchy_pin = pins['hierarchy']
    require(hierarchy_pin['sha256'] == HIERARCHY_SHA256, 'fixed hierarchy SHA differs')
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin['path']), expected_sha256=HIERARCHY_SHA256, expected_identity=hierarchy_pin['identity_sha256'])
    paths, sections = (loaded['06_paths'], loaded['06_sections'])
    old_index, source_index = (loaded['06_index'], loaded['source_bank_parent_index'])
    wet, source_audit = (loaded['wet_protection_manifest'], loaded['source_bank_parent_audit'])
    require(old_index['paths']['sha256'] == pins['06_paths']['sha256'] and old_index['sections']['sha256'] == pins['06_sections']['sha256'] and (old_index['inputs']['hierarchy']['sha256'] == HIERARCHY_SHA256), '06 original pin linkage differs')
    require(source_audit['status'] == 'passed' and source_audit['index_sha256'] == pins['source_bank_parent_index']['sha256'] and (source_audit['manifest_sha256'] == source_index['manifest']['sha256'] == pins['wet_protection_manifest']['sha256']), 'original source-bank/wet audit binding differs')
    require(wet['paths_identity_sha256'] == paths['identity_sha256'] and wet['sections_identity_sha256'] == sections['identity_sha256'] and (wet['hierarchy_identity_sha256'] == hierarchy['identity_sha256']), 'original wet protection domain differs')
    return (paths, sections, hierarchy, wet['wet_protection'])

def audit(index):
    content_identity(index)
    require(index['schema'] == 'td-ported-network-composition-preparation-v1' and index['status'] == index['metrics_status'] == 'candidate_unverified' and (index['policy_identity_sha256'] == POLICY_SHA256), 'composition preparation schema/policy differs')
    for flag in FALSE_FLAGS:
        require(index[flag] is False, 'preparation promoted certification: ' + flag)
    resource = index['resource']
    require(0 <= resource['actual_peak_rss_bytes'] <= resource['max_rss_bytes'] <= 1024 ** 3 and 0 < resource['max_json_bytes'] <= 64 * 1024 ** 2 and (resource['max_hubs'] == 256) and (resource['solver_calls'] == resource['fine_cells_generated'] == 0) and (resource['old_packages_modified'] is False), 'composition resource/scope differs')
    for name, expected in FROZEN_CODE.items():
        require(file_sha256(ROOT / name) == expected, 'frozen readonly code changed: ' + name)
        if name.startswith('terrain_pipeline/') or name.startswith('tools/prepare_') or name.startswith('tests/'):
            require(index['code_sha256'].get(name) == expected, 'index omits fixed generator code: ' + name)
    for name, sha in index['code_sha256'].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT) and file_sha256(path) == sha, 'saved code pin changed')
    pins = index['inputs']
    paths, sections, hierarchy, wet = parent_inputs(pins)
    records = {key: read(index[key]) for key in ('manifest', 'census', 'composed_mesh', 'topology')}
    manifest, census = (records['manifest'], records['census'])
    for record in records.values():
        content_identity(record)
    require(manifest['schema'] == 'td-ported-network-composition-v1' and manifest['policy'] == POLICY and (manifest['policy_identity_sha256'] == POLICY_SHA256) and (manifest['inputs'] == pins), 'manifest schema/policy/source pins differ')
    require(manifest['parents'] == dict(paths=paths['identity_sha256'], sections=sections['identity_sha256'], hierarchy=hierarchy['identity_sha256'], source=paths['source_identity_sha256']), 'manifest parent identities differ')
    require(census['schema'] == 'td-ported-network-census-v1' and census['inputs'] == pins and (census['policy_identity_sha256'] == POLICY_SHA256) and (census['all_actual_three_arm_hubs'] is True) and (census['max_hubs'] == 256), 'all-hub census policy differs')
    expected_census = census_hubs(paths, sections)
    compare(census['hubs'], expected_census, 'complete Q-ordered original census')
    require(census['hub_count'] == index['hub_count'] == len(expected_census) == len(manifest['hubs']), 'hub census count differs')
    require(manifest['original_06_kept_unchanged'] is True and manifest['original_06_triangle_count'] == len(sections['mesh']['triangles']) and (manifest['metrics_status'] == 'candidate_unverified'), 'manifest original geometry scope differs')
    for flag in FALSE_FLAGS + ('bed_changed', 'hydraulic_solved', 'full_river_verified', 'natural_outlet_certified'):
        require(manifest[flag] is False, 'manifest promoted certification: ' + flag)
    selection = SelectionAudit(sections)
    junction_pins, single_results = ({}, [])
    generation_count, peak = (0, check_memory())
    for ordinal, (row, expected_row) in enumerate(zip(manifest['hubs'], expected_census)):
        for key, value in expected_row.items():
            compare(row[key], value, 'manifest census ' + key)
        record = read(row['junction'])
        require(record['hub_node_id'] == row['hub_node_id'] and record['inputs'] == pins and (record['wet_protection'] == wet) and (row['generation_status'] == record['status']) and (row['generation_rejection_reasons'] == record['rejection_reasons']), 'junction/row original binding differs')
        if record['status'] == 'refused':
            require(not record['geometry']['triangles'], 'nonempty generation refusal requires a separate geometry refusal audit')
        result = audit_junction(record, paths, sections, hierarchy)
        single_results.append({key: result[key] for key in ('hub_node_id', 'junction_status', 'internal_three_arm_geometry_verified', 'source_native_whole_face_functions_verified', 'actual_external_attachment_count', 'external_closure_verified', 'refusal_evidence_verified')})
        junction_pins[str(row['hub_node_id'])] = {key: row['junction'][key] for key in ('path', 'sha256', 'identity_sha256')}
        if record['status'] == 'refused':
            require(result['parent_refusal_witnesses'], 'empty refusal lacks independently verified parent evidence')
            reasons, witnesses = (['junction_generation_refused'], [])
        else:
            generation_count += 1
            reasons, witnesses = selection.consider(record)
        selected = not reasons
        require(row['composition_status'] == ('selected' if selected else 'refused'), 'greedy atomic selection differs')
        compare(row['rejection_reasons'], reasons, 'independent selection refusal')
        compare(row['conflict_witnesses'], witnesses, 'actual conflict face witnesses')
        require(row['added_arc_ids'] == (record['requested_replacement_arc_ids'] if selected else []), 'partial/refused hub owns arcs')
        peak = max(peak, check_memory())
        print(json.dumps(dict(ordinal=ordinal, hub_node_id=row['hub_node_id'], independent_single_status=result['junction_status'], composition_selected=selected)), flush=True)
        del record, result
        gc.collect()
    require(index['generation_candidate_count'] == generation_count and index['composition_selected_count'] == len(selection.accepted), 'composition candidate/selected totals differ')
    compare(manifest['arc_owners'], selection.owners, 'unique atomic arc ownership')
    compare(manifest['connections'], selection.connections, 'whole actual reverse function seams')
    expected_mesh = dict(vertices_xyz_m=selection.vertices, triangles=selection.triangles, face_origins=selection.origins, parametric_only=True, fine_generated=False, original_06_prefix_unchanged=True)
    saved_mesh = {key: value for key, value in records['composed_mesh'].items() if key != 'identity_sha256'}
    require(saved_mesh == expected_mesh, 'composed mesh differs from exact original prefix and selected atomic patches')
    expected_topology = topology(paths, sections, selection)
    compare({key: value for key, value in records['topology'].items() if key != 'identity_sha256'}, expected_topology, 'geometry-evidenced connectivity metrics')
    return dict(schema=AUDIT_SCHEMA, status='passed', errors=[], policy_identity_sha256=POLICY_SHA256, accepted_hub_ids=selection.accepted, junctions=junction_pins, junction_audits=single_results, hub_count=len(expected_census), generation_candidate_count=generation_count, composition_selected_count=len(selection.accepted), arc_count=len(selection.owners), whole_hub_atomic_ownership_verified=True, original_06_mesh_exactly_preserved=True, selected_source_native_functions_verified=bool(selection.accepted), actual_whole_boundary_connections_verified=True, topology_metrics_verified=True, component_count=expected_topology['component_count'], components=expected_topology['components'], longest_directed_path=expected_topology['longest_directed_path'], directed_cycle_arc_ids=expected_topology['directed_cycle_arc_ids'], open_port_count=expected_topology['open_port_count'], open_ports=expected_topology['open_ports'], no_node_only_connections=True, full_network_verified=False, hydraulic_ready=False, hydraulic_solved=False, fine_generated=False, material_budget_verified=False, inputs=pins, manifest_identity_sha256=manifest['identity_sha256'], actual_peak_audit_rss_bytes=max(peak, check_memory()), scope='saved atomic composition and geometry-evidenced arc metrics; parent-evidenced empty refusals; not full-network hydraulics', **{key + '_sha256': index[key]['sha256'] for key in ('manifest', 'composed_mesh', 'census', 'topology')})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit-schema', choices=[AUDIT_SCHEMA], default=AUDIT_SCHEMA)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / 'verification/natural-river-network'), 'new verification audit output required')
    index = read(dict(path=str(args.input.resolve()), sha256=args.sha256))
    result = audit(index)
    result.update(index_sha256=args.sha256, audit_code_sha256={name: file_sha256(ROOT / name) for name in ('tools/audit_td_ported_network_composition_v3.py', 'tools/td_ported_network_saved_audit.py', 'tools/audit_td_ported_junction_v3.py', 'tools/td_ported_junction_saved_audit_v3.py', 'tools/audit_td_source_conforming_banks_v3.py', 'tools/audit_saved_source_conforming_banks.py', 'tools/audit_saved_source_conforming_banks.py', 'tools/audit_td_fine_bed_shards.py', 'tools/audit_td_fine_bed_raster.py')})
    publish_bytes(output, (json.dumps(result, sort_keys=True, allow_nan=False, indent=2) + '\n').encode())
    print(json.dumps({key: result[key] for key in ('schema', 'status', 'hub_count', 'composition_selected_count', 'component_count', 'open_port_count', 'full_network_verified', 'actual_peak_audit_rss_bytes')}))
if __name__ == '__main__':
    main()
