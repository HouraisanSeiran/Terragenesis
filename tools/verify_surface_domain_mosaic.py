"""Verify the fixed saved two-domain dry extension and retain new UTC evidence."""
from terrain_pipeline.surface_identity import _plain as _merged_fine__plain
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import surface_domain as mosaic
from terrain_pipeline import surface_domain as fine
from terrain_pipeline.surface_domain import load_surface_domains
from tests.test_surface_domain import SurfaceDomainMosaicTests, SOURCE

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(directory, report):
    evaluation = load_surface_domains(SOURCE)
    report['old_source'] = {'path': str(SOURCE.resolve()), 'file_sha256': sha(SOURCE), 'evaluation_identity_sha256': evaluation['identity_sha256'], 'candidate_identity_sha256': evaluation['candidate']['identity_sha256']}
    if sha(SOURCE) != 'dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af':
        raise AssertionError('old prepared source changed')
    old_gap = ROOT / 'verification/surface-fine-mosaic/run-20260930T123659.258177Z/old-two-domain-gap.npz'
    diagnostic = fine.load_fine_mosaic(old_gap, allow_unprepared=True)
    report['old_gap'] = {'path': str(old_gap.resolve()), 'file_sha256': sha(old_gap), 'missing_cell_count': diagnostic['missing_cell_count']}
    if diagnostic['missing_cell_count'] != 600:
        raise AssertionError('old gap count changed')
    result = mosaic.prepare_domain_mosaic(evaluation)
    path = directory / 'two-domain-dry-extension.npz'
    mosaic.save_domain_mosaic(result, path)
    with ExitStack() as stack:
        for module, name in ((mosaic, 'prepare_domain_mosaic'), (mosaic, '_assemble'), (fine, '_mesh'), (fine, '_h0_support'), (fine, 'prepare_fine_mosaic')):
            stack.enter_context(patch.object(module, name, side_effect=AssertionError('load generated ' + name)))
        loaded = mosaic.load_domain_mosaic(path)
    if loaded['identity_sha256'] != result['identity_sha256']:
        raise AssertionError('static reload identity changed')
    extension = loaded['cell_owner'] == 2
    report['new_mosaic'] = {'path': str(path.resolve()), 'file_sha256': sha(path), 'identity_sha256': loaded['identity_sha256'], 'declared_node_envelope_complete': True, 'physical_footprint_complete': False, 'natural_outlets_certified': False, 'full_domain_mosaic_prepared': False, 'static_no_generation_reload': True, 'node_count': len(loaded['nodes']['x_m']), 'cell_count': len(loaded['cells']), 'triangle_count': len(loaded['triangles']), 'extension_cell_count': int(extension.sum()), 'extension_domain_cell_counts': {str(domain): int(np.sum(extension & (loaded['hydrologic_domain_owner'] == domain))) for domain in (1, 2)}, 'summary': _merged_fine__plain(loaded['summary']), 'domain_summaries': [_merged_fine__plain(mesh['summary']) for mesh in loaded['domain_meshes']]}
    if (len(loaded['nodes']['x_m']), len(loaded['cells']), len(loaded['triangles']), int(extension.sum())) != (7991, 7800, 15600, 600):
        raise AssertionError('fixed geometry changed')
    with (directory / 'focused-tests.txt').open('x', encoding='utf8') as stream:
        tests = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceDomainMosaicTests)
        outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    report['focused_tests'] = {'run': outcome.testsRun, 'failures': len(outcome.failures), 'errors': len(outcome.errors)}
    if not outcome.wasSuccessful():
        raise AssertionError('focused tests failed')

def main():
    started = datetime.now(timezone.utc)
    directory = ROOT / 'verification/surface-domain-mosaic' / ('run-' + started.strftime('%Y%m%dT%H%M%S.%fZ'))
    directory.mkdir(parents=True, exist_ok=False)
    files = ('terrain_pipeline/surface_domain.py', 'tests/test_surface_domain.py', 'tools/verify_surface_domain_mosaic.py', 'docs/surface-domain-mosaic-v1.md')
    report = {'executed_utc': started.isoformat(), 'algorithm_version': mosaic.SURFACE_DOMAIN_MOSAIC_VERSION, 'status': 'running', 'output_directory': str(directory.resolve()), 'implementation_files': {name: sha(ROOT / name) for name in files}}
    try:
        run(directory, report)
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
        (directory / 'traceback.txt').write_text(report['traceback'], encoding='utf8')
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with (directory / 'report.json').open('x', encoding='utf8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        print(json.dumps(report, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
