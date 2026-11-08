"""Verify the fixed, saved surface evidence without generating terrain."""
import json
import hashlib
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import surface_domain as readiness
EVIDENCE = ROOT / 'verification'
PATHS = {'dem': EVIDENCE / 'dem-domain/run-20260930T062026836139Z/dem-candidate.npz', 'domain': EVIDENCE / 'surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz', 'mosaic': EVIDENCE / 'surface-fine-mosaic/run-20260930T123659.258177Z/old-two-domain-gap.npz', 'drop': EVIDENCE / 'surface-coast-drop/run-20260930T125523.932019Z/actual-river-engineering-coast.npz', 'dynamic': EVIDENCE / 'surface-dynamic-prepare/run-20260930T130638.804119Z/saved-old-prepared-domain1.npz'}
IMPLEMENTATION_FILES = {'module': ROOT / 'terrain_pipeline/surface_domain.py', 'tests': ROOT / 'tests/test_surface_domain.py', 'verifier': ROOT / 'tools/verify_surface_development_readiness.py', 'documentation': ROOT / 'docs/surface-development-readiness-v1.md'}

def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def main():
    started = datetime.now(timezone.utc)
    output = EVIDENCE / 'surface-development-readiness' / ('run-' + started.strftime('%Y%m%dT%H%M%S.%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': started.isoformat(), 'verifier_passed': False}
    try:
        report['implementation_sha256'] = {name: file_sha256(path) for name, path in IMPLEMENTATION_FILES.items()}
        manifest = readiness.prepare_readiness(PATHS, dynamic_scope='lumped_storage_linear_conductance')
        readiness.save_readiness(manifest, output / 'manifest.json')
        reloaded = readiness.load_readiness(output / 'manifest.json')
        if reloaded != manifest or reloaded['diagnosis']['ready']:
            raise ValueError('unexpected readiness result')
        suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_surface_domain')
        with (output / 'focused-tests.txt').open('w', encoding='utf-8') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report.update(verifier_passed=result.wasSuccessful(), tests_run=result.testsRun, readiness=manifest['diagnosis'])
    except Exception as error:
        report['error'] = str(error)
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(output)
    print('verifier_passed=', report['verifier_passed'], 'readiness=', report.get('readiness', {}).get('ready'))
    return 0 if report['verifier_passed'] else 1
if __name__ == '__main__':
    sys.exit(main())
