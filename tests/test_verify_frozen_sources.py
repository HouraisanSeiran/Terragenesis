"""Positive and negative cases for tools/verify_frozen_sources.py (temp dirs only)."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import verify_frozen_sources as verifier


class VerifyFrozenSourcesTests(unittest.TestCase):
    def build(self, root, payload=b'alpha\n', recorded_sha=None, evidence_hash=None,
              pin_kind='hard', evidence_path='pin/report.json'):
        root = Path(root)
        snapshot = root / 'legacy-code' / 'frozen-sources-20261105'
        copy = snapshot / 'terrain_pipeline' / 'demo.py'
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()

        evidence = root / 'verification' / evidence_path
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({'sha256': evidence_hash or digest}), encoding='utf-8')

        manifest = {
            'schema': 'frozen-sources-snapshot-v1',
            'counts': {'total': 1},
            'files': [{
                'source_path': 'terrain_pipeline/demo.py',
                'sha256': recorded_sha or digest,
                'bytes': len(payload),
                'pin_kind': pin_kind,
                'evidence_refs': [evidence_path],
            }],
        }
        manifest_path = snapshot / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        return root, manifest_path, digest

    def test_clean_snapshot_passes_with_and_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest_path, _ = self.build(directory)
            plain = verifier.verify(root, manifest_path)
            self.assertTrue(plain['ok'], plain)
            self.assertEqual(plain['checked'], 1)
            with_evidence = verifier.verify(root, manifest_path, check_evidence=True)
            self.assertTrue(with_evidence['ok'], with_evidence)
            self.assertEqual(with_evidence['evidence_checked'], 1)

    def test_flipped_byte_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest_path, digest = self.build(directory)
            copy = manifest_path.parent / 'terrain_pipeline' / 'demo.py'
            copy.write_bytes(b'beta\n')
            report = verifier.verify(root, manifest_path)
            self.assertFalse(report['ok'])
            self.assertEqual(len(report['corrupt']), 1)
            self.assertEqual(report['corrupt'][0]['expected'], digest)

    def test_manifest_hash_not_present_in_evidence_fails_only_with_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest_path, _ = self.build(directory, evidence_hash='0' * 64)
            self.assertTrue(verifier.verify(root, manifest_path)['ok'])
            report = verifier.verify(root, manifest_path, check_evidence=True)
            self.assertFalse(report['ok'])
            self.assertEqual([item['source_path'] for item in report['evidence_absent']],
                             ['terrain_pipeline/demo.py'])

    def test_implicit_only_entries_are_not_evidence_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest_path, _ = self.build(directory, evidence_hash='1' * 64, pin_kind='implicit')
            report = verifier.verify(root, manifest_path, check_evidence=True)
            self.assertTrue(report['ok'], report)
            self.assertEqual(report['evidence_checked'], 0)

    def test_both_entries_are_evidence_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest_path, _ = self.build(directory, pin_kind='both')
            report = verifier.verify(root, manifest_path, check_evidence=True)
            self.assertTrue(report['ok'], report)
            self.assertEqual(report['evidence_checked'], 1)

    def test_missing_copy_and_size_mismatch_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest_path, _ = self.build(directory)
            (manifest_path.parent / 'terrain_pipeline' / 'demo.py').unlink()
            report = verifier.verify(root, manifest_path)
            self.assertFalse(report['ok'])
            self.assertEqual(report['missing'], ['terrain_pipeline/demo.py'])

            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['files'][0]['bytes'] = 4096
            copy = manifest_path.parent / 'terrain_pipeline' / 'demo.py'
            copy.write_bytes(b'alpha\n')
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            report = verifier.verify(root, manifest_path)
            self.assertFalse(report['ok'])
            self.assertEqual(report['size_mismatch'], ['terrain_pipeline/demo.py'])

    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest_path, _ = self.build(directory)
            self.assertEqual(verifier.main(['--root', str(root), '--manifest', str(manifest_path)]), 0)
            self.assertEqual(
                verifier.main(['--root', str(root), '--manifest', str(manifest_path), '--evidence']), 0)
            copy = manifest_path.parent / 'terrain_pipeline' / 'demo.py'
            copy.write_bytes(b'gamma\n')
            self.assertEqual(verifier.main(['--root', str(root), '--manifest', str(manifest_path)]), 1)


if __name__ == '__main__':
    unittest.main()
