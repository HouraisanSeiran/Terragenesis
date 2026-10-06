"""Explicit frozen regional regression plus pinned static artifact integrity."""

import argparse
import ast
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.rainfall_runoff import _strict_json
from tools.verify_mountain_source_adapter import write_json
from tools.verify_mountain_round_acceptance import RecordedResult

MODULES = (
    'tests.test_regional_source', 'tests.test_regional_forcing', 'tests.test_regional_source_network',
    'tests.test_rainfall_runoff', 'tests.test_mountain_source_adapter',
    'tests.test_mountain_depression_geometry', 'tests.test_regional_hydraulics', 'tests.test_regional_review',
    'tests.test_regional_hydraulics_archive',
    'tests.test_regional_hydraulics_compare',
    'tests.test_regional_hydraulics_accelerated',
    'tests.test_regional_review_diagnostics',
    'tests.test_regional_review_landing',
    'tests.test_surface_network_consumer',
)


def local_dependency_files():
    pending = [ROOT / (module.replace('.', '/') + '.py') for module in MODULES]
    pending.extend(ROOT.glob('tools/verify_regional*.py'))
    pending.extend(ROOT.glob('terrain_pipeline/regional*.py'))
    pending.append(ROOT / 'tools/verify_mountain_round_acceptance.py')
    seen = set()
    while pending:
        path = pending.pop().resolve()
        if path in seen or not path.is_file() or not path.is_relative_to(ROOT):
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
                names.extend(node.module + '.' + alias.name for alias in node.names)
            for name in names:
                candidate = ROOT / (name.replace('.', '/') + '.py')
                if candidate.is_file():
                    pending.append(candidate)
    return {str(path.relative_to(ROOT)).replace('\\', '/') for path in seen}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def verify(args):
    if not args.run_after_B_freeze:
        raise ValueError('formal run requires explicit B freeze state declaration')
    artifact_path = args.artifact_index.resolve()
    if file_sha256(artifact_path) != args.artifact_index_sha256:
        raise ValueError('external static artifact index SHA required')
    if artifact_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('bounded acceptance artifact index required')
    record = _strict_json(artifact_path.read_text(encoding='utf-8'))
    if set(record) != {'files_sha256', 'source_sha256', 'B_freeze_evidence'} or not record['B_freeze_evidence']:
        raise ValueError('explicit static files/source hashes and B freeze evidence required')
    required_sources = local_dependency_files()
    if not required_sources.issubset(record['source_sha256']):
        raise ValueError('missing recursive local source/test/tool hashes: ' +
            ', '.join(sorted(required_sources - set(record['source_sha256']))))
    required_fixtures = {
        'verification/regional-source/run-20261001T095258008789Z/source.npz',
        'verification/regional-source/run-20261001T095258008789Z/manifest.json',
        'verification/regional-source-network/run-20261001T095553240102Z/network.json',
        'verification/regional-hydraulics/full-20261001T101153406000Z/dry/states.json',
        'verification/regional-hydraulics/mesh-dry-20261001T101953058448Z/saved-mesh-index.json',
        'verification/regional-hydraulics/failure-20261001T102852005353Z/work_two_commit/states.json',
        'verification/regional-hydraulics/mesh-work_two_commit-20261001T103232437820Z/consumer-cases-index.json',
        'verification/regional-hydraulics/full-20261001T101153406000Z/dry-summary.json',
        'verification/regional-hydraulics/full-20261001T101153406000Z/wet_no_rain-summary.json',
        'verification/regional-hydraulics/failure-20261001T102852005353Z/work_two_commit-summary.json',
    }
    for case in ('dry', 'wet_no_rain', 'uniform_heavy'):
        required_fixtures.update(str(path.relative_to(ROOT)).replace('\\', '/')
            for path in (ROOT / 'verification/regional-forcing/run-20261001T095608600719Z' / case).glob('*')
            if path.is_file())
    for folder in ('verification/regional-hydraulics/mesh-dry-20261001T101953058448Z',
            'verification/regional-hydraulics/mesh-work_two_commit-20261001T103232437820Z'):
        required_fixtures.update(str(path.relative_to(ROOT)).replace('\\', '/')
            for path in (ROOT / folder).glob('*water*.json'))
    if not required_fixtures.issubset(record['files_sha256']):
        raise ValueError('missing original cold review fixture hashes: ' +
            ', '.join(sorted(required_fixtures - set(record['files_sha256']))))
    for name in set(record['source_sha256']) | set(record['files_sha256']):
        if not (ROOT / name).resolve().is_relative_to(ROOT):
            raise ValueError('artifact index path escapes workspace')
    destination = ROOT / 'verification/regional-round-acceptance' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    before = {name: file_sha256(ROOT / name) for name in record['source_sha256']}
    if before != record['source_sha256']:
        raise ValueError('frozen regression source hashes changed')
    artifacts = {name: file_sha256(ROOT / name) for name in record['files_sha256']}
    if artifacts != record['files_sha256']:
        raise ValueError('static evidence hashes changed')
    source_files = {'tools/verify_regional_round_acceptance.py': file_sha256(Path(__file__)),
                    'tools/verify_mountain_round_acceptance.py': file_sha256(ROOT / 'tools/verify_mountain_round_acceptance.py')}
    loader = unittest.TestLoader()
    tests = []
    counts = {}
    for module in MODULES:
        if importlib.util.find_spec(module) is None:
            raise ValueError('declared module absent: ' + module)
        declared = [test for test in flatten(loader.loadTestsFromName(module)) if type(test).__module__ == module]
        if not declared:
            raise ValueError('zero declared tests: ' + module)
        counts[module] = len(declared)
        tests.extend(declared)
    identities = [test.id() for test in tests]
    if loader.errors or len(set(identities)) != len(identities):
        raise ValueError('test discovery error or duplicate identity')
    write_json(destination / 'predeclared.json', {'modules': list(MODULES), 'unique_test_ids': identities,
        'module_counts': counts, 'source_hashes': before, 'static_artifacts': artifacts,
        'verifier_hashes': source_files, 'artifact_index_sha256': args.artifact_index_sha256,
        'B_freeze_evidence': record['B_freeze_evidence'], 'mode': 'serial CPU tests; no production surface scenarios/GPU/browser'})
    started = time.perf_counter()
    with (destination / 'tests.log').open('x', encoding='utf-8') as output:
        runner = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=RecordedResult)
        result = runner.run(unittest.TestSuite(tests))
    after = {name: file_sha256(ROOT / name) for name in before}
    after_artifacts = {name: file_sha256(ROOT / name) for name in artifacts}
    stable = before == after and artifacts == after_artifacts and all(file_sha256(ROOT / name) == digest for name, digest in source_files.items())
    report = {'success': result.wasSuccessful() and stable, 'tests_run_unique': result.testsRun,
        'records': result.records, 'skips': [{'id': test.id(), 'reason': reason} for test, reason in result.skipped],
        'failures': len(result.failures), 'errors': len(result.errors), 'elapsed_s': time.perf_counter() - started,
        'source_and_static_hashes_unchanged': stable, 'modules': list(MODULES), 'module_counts': counts}
    write_json(destination / 'report.json', report)
    write_json(destination / 'freeze-manifest.json', {'files_sha256': {item.name: file_sha256(item) for item in destination.iterdir() if item.is_file()}})
    print(json.dumps({'directory': str(destination), **report}, ensure_ascii=False))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-after-B-freeze', action='store_true')
    parser.add_argument('--artifact-index', required=True, type=Path)
    parser.add_argument('--artifact-index-sha256', required=True)
    sys.exit(verify(parser.parse_args()))
