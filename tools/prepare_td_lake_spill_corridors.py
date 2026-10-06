"""Prepare pinned original-bed diagnostics, not a new or continuous channel."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.td_lake_spill_corridor import build_lake_spill_corridors, save_lake_spill_corridors


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def record_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_pin(path, sha256):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 32 * 1024**2 or file_hash(path) != sha256:
        raise ValueError('input_pin_mismatch')
    return json.loads(path.read_text(encoding='utf-8'))


def read_parent(index_path, index_sha256, audit_path, audit_sha256, case_id='baseline'):
    index = read_pin(index_path, index_sha256)
    audit = read_pin(audit_path, audit_sha256)
    if audit.get('status') != 'passed' or audit.get('index_sha256') != index_sha256:
        raise ValueError('parent_audit_not_bound_or_passed')
    case = next(item for item in index['cases'] if item['case_id'] == case_id)
    graph_pin = dict(case['graph'])
    graph_pin['path'] = str((Path(index_path).resolve().parent / graph_pin['path']).resolve())
    graph = read_pin(graph_pin['path'], graph_pin['sha256'])
    if (graph.get('identity_sha256') != graph_pin['identity_sha256'] or
            record_hash({key: value for key, value in graph.items() if key != 'identity_sha256'}) != graph_pin['identity_sha256']):
        raise ValueError('parent_graph_identity_mismatch')
    provenance = {'parent_index': {'path': str(Path(index_path).resolve()), 'sha256': index_sha256},
                  'parent_audit': {'path': str(Path(audit_path).resolve()), 'sha256': audit_sha256},
                  'graph': graph_pin, 'case_id': case_id}
    return graph, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-index', type=Path, required=True)
    parser.add_argument('--parent-index-sha256', required=True)
    parser.add_argument('--parent-audit', type=Path, required=True)
    parser.add_argument('--parent-audit-sha256', required=True)
    parser.add_argument('--case-id', default='baseline')
    parser.add_argument('--paths', type=Path)
    parser.add_argument('--paths-sha256')
    parser.add_argument('--paths-identity')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    graph, provenance = read_parent(args.parent_index, args.parent_index_sha256,
                                    args.parent_audit, args.parent_audit_sha256, args.case_id)
    paths = None
    if args.paths:
        paths = read_pin(args.paths, args.paths_sha256)
        if (paths.get('identity_sha256') != args.paths_identity or
                record_hash({key: value for key, value in paths.items() if key != 'identity_sha256'}) != args.paths_identity):
            raise ValueError('paths_identity_mismatch')
        provenance['paths'] = {'path': str(args.paths.resolve()), 'sha256': args.paths_sha256,
                               'identity_sha256': args.paths_identity}
    result = build_lake_spill_corridors(graph, paths, provenance=provenance)
    path = save_lake_spill_corridors(result, args.output / 'corridors.json')
    print(json.dumps({'output': str(path.resolve()), 'scope': result['scope'],
                      'domain_count': result['domain_routing_eligible_count'], 'summary': result['summary']}))


if __name__ == '__main__':
    main()
