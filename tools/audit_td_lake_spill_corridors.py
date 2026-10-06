"""Independent cold comparison against pinned parent graph; no generation."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prepare_td_lake_spill_corridors import read_parent, read_pin, record_hash


def _classify(edge):
    geometry = edge.get('geometry') or {}
    if geometry.get('status') != 'accepted':
        return ['spill_geometry_not_accepted'], None
    try:
        cross = geometry['cross_face']
        downhill = geometry['downhill_terrain_approach']
        for part in (cross, downhill):
            if (not part['xyz_m'] or len(part['xyz_m']) != len(part['cell_ids']) or
                    any(len(point) != 3 or not all(math.isfinite(value) for value in point) for point in part['xyz_m'])):
                return ['invalid_station_cells'], None
        if len(cross['cell_ids']) != 2:
            return ['invalid_station_cells'], None
        if cross['cell_ids'][-1] != downhill['cell_ids'][0]:
            return ['join_cell_mismatch'], None
        if cross['xyz_m'][-1] != downhill['xyz_m'][0]:
            return ['join_xyz_mismatch'], None
        points = cross['xyz_m'] + downhill['xyz_m'][1:]
        heights = [point[1] for point in points]
        sill = max(heights[:2])
        crest = heights.index(max(heights))
        reasons = []
        if not math.isfinite(edge['sill_m']) or abs(sill - edge['sill_m']) > 1e-8:
            reasons.append('physical_sill_mismatch')
        if any(height > sill + 1e-8 for height in heights[2:]):
            reasons.append('crest_not_at_shared_sill')
        if any(after > before + 1e-8 for before, after in zip(heights[crest:], heights[crest+1:])):
            reasons.append('downstream_profile_rises')
        if geometry.get('sill_m') != edge['sill_m']:
            reasons.append('geometry_sill_mismatch')
        profile = {'crest_station': crest, 'crest_m': heights[crest], 'downstream_min_m': heights[-1],
                   'downstream_drop_m': heights[crest] - heights[-1], 'rejection_reasons': reasons,
                   'single_crest_downhill': not reasons}
        return reasons, (points, profile)
    except (KeyError, TypeError, ValueError) as error:
        return [str(error)], None


def audit(path, *, expected_sha256):
    record = read_pin(path, expected_sha256)
    provenance = record['provenance']
    graph, checked = read_parent(provenance['parent_index']['path'], provenance['parent_index']['sha256'],
                                 provenance['parent_audit']['path'], provenance['parent_audit']['sha256'],
                                 provenance['case_id'])
    errors = []
    if provenance['graph'] != checked['graph'] or record['source_graph_identity_sha256'] != graph['identity_sha256']:
        errors.append('graph_provenance')
    domain = [edge for edge in graph['edges'] if edge['routing_eligible']]
    selected = {edge['face_id'] for edge in domain}
    if 'paths' in provenance:
        pin = provenance['paths']
        paths = read_pin(pin['path'], pin['sha256'])
        if (paths['identity_sha256'] != pin['identity_sha256'] or paths['graph_identity_sha256'] != graph['identity_sha256'] or
                record_hash({key: value for key, value in paths.items() if key != 'identity_sha256'}) != pin['identity_sha256']):
            errors.append('paths_provenance')
        selected = {arc['face_id'] for arc in paths['arcs'] if arc.get('face_id')}
        if record['source_paths_identity_sha256'] != pin['identity_sha256'] or record['scope'] != 'paths_main_watershed':
            errors.append('paths_scope')
    elif record['scope'] != 'all_domain' or record['source_paths_identity_sha256'] is not None:
        errors.append('domain_scope')
    edges = [edge for edge in domain if edge['face_id'] in selected]
    if (len(edges) != len(selected) or record['selected_face_ids'] != [edge['face_id'] for edge in edges] or
            record['domain_routing_eligible_count'] != len(domain) or
            [item['corridor_id'] for item in record['corridors']] != [edge['face_id'] for edge in edges]):
        errors.append('coverage_census')
    counts = Counter()
    stations = 0
    for edge, item in zip(edges, record['corridors']):
        for name, value in {'source_geometry': edge.get('geometry'), 'sill_m': edge.get('sill_m'),
                            'source_leaf_id': edge.get('source_leaf_id'),
                            'receiver_leaf_id': edge.get('receiver_leaf_id')}.items():
            if item.get(name) != value:
                errors.append(edge['face_id'] + ':' + name)
        reasons, diagnostic = _classify(edge)
        expected = 'rejected' if reasons else 'candidate'
        counts[expected] += 1
        if item['status'] != expected or (expected == 'rejected' and item['rejection_reasons'] != reasons):
            errors.append(edge['face_id'] + ':classification')
        if diagnostic and item.get('profile') != diagnostic[1]:
            errors.append(edge['face_id'] + ':profile')
        if expected == 'candidate':
            points, _ = diagnostic
            stations += len(points)
            geometry = edge['geometry']
            fields = {'source_geometry': geometry, 'sill_m': edge['sill_m'], 'centerline_bed_xyz_m': points,
                      'centerline_cell_ids': geometry['cross_face']['cell_ids'] + geometry['downhill_terrain_approach']['cell_ids'][1:],
                      'source_lake_approach_xyz_m': geometry['source_lake_approach']['xyz_m'],
                      'spill_cross_face_xyz_m': geometry['cross_face']['xyz_m'],
                      'downstream_support_xyz_m': geometry['downhill_terrain_approach']['xyz_m'],
                      'source_leaf_id': edge['source_leaf_id'], 'receiver_leaf_id': edge['receiver_leaf_id'],
                      'source_bed_unchanged': True, 'channel_verified': False, 'hydraulic_solved': False,
                      'natural_outlet_verified': False, 'publishable': False,
                      'open_lake_port': True, 'open_downstream_port': True}
            for name, value in fields.items():
                if item.get(name) != value:
                    errors.append(edge['face_id'] + ':' + name)
        elif diagnostic and any(item.get(name) != edge[name] for name in ('source_leaf_id', 'receiver_leaf_id')):
            errors.append(edge['face_id'] + ':leaf')
    summary = {'requested': len(edges), 'candidate': counts['candidate'], 'rejected': counts['rejected'],
               'candidate_station_count': stations}
    if record['summary'] != summary:
        errors.append('summary')
    if record['status'] != ('candidate' if counts['candidate'] else 'pending'):
        errors.append('status')
    for name in ('continuous_bed_ready', 'integrated_with_watershed_mesh', 'bed_changed', 'hydraulic_solved',
                 'natural_outlet_certified', 'publishable'):
        if record.get(name) is not False:
            errors.append(name)
    unsigned = {key: value for key, value in record.items() if key != 'identity_sha256'}
    digest = hashlib.sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if digest != record['identity_sha256'] or record.get('solver_calls') != 0:
        errors.append('identity_or_solver')
    return {'schema': 'td-lake-spill-original-bed-independent-audit-v2', 'status': 'failed' if errors else 'passed',
            'errors': errors, 'scope': record['scope'], 'summary': summary, 'domain_count': len(domain),
            'corridors_sha256': expected_sha256, 'parent_graph_identity_sha256': graph['identity_sha256'],
            'solver_calls': 0, 'bed_changed': False, 'continuous_bed_ready': False, 'natural_outlet_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = audit(args.path, expected_sha256=args.sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result))
    if result['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
