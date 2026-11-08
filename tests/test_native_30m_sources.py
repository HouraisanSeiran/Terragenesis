"""Source-only codec and CLI isolation tests; no TD pages or numerical kernels needed."""
import copy
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from terrain_pipeline.common_infra import file_sha256
from tools import native_30m_sources as sources
from tools import publish_native_30m_bundle as publisher


def request_for(page):
    return {'schema': sources.SCHEMA, 'source_records': [{'path': str(page), 'sha256': file_sha256(page)}],
            'expected_numerical_identity_sha256': 'a'*64,
            'parameters': {'world_seed': 20261020, 'origin_native_xz': [0, 0], 'shape_zx': [9, 9],
                           'coupled_intervals': 1, 'resample_stride': 1, 'storm_rain_mm_h': list(sources.STORM),
                           'dt_s': 3600., 'infiltration_capacity_mm_h': 2.}}


class SourceRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.page = self.root / 'source.npz'
        self.page.write_bytes(b'pinned input for codec testing only')
        self.request = request_for(self.page)
        self.path = self.root / 'source-request.json'
        self.pin = sources.save_source_request(self.path, self.request)

    def test_external_pin_and_page_verification(self):
        self.assertEqual(sources.load_source_request(self.path, expected_sha256=self.pin), self.request)
        with self.assertRaisesRegex(ValueError, 'external_pin_required'):
            sources.load_source_request(self.path, expected_sha256=None)
        with self.assertRaisesRegex(ValueError, 'pin_mismatch'):
            sources.load_source_request(self.path, expected_sha256='0'*64)

    def test_source_changes_are_rejected(self):
        self.page.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'pin_mismatch'):
            sources.load_source_request(self.path, expected_sha256=self.pin)

    def test_derived_fields_and_unsupported_defaults_refused(self):
        mutations = [('world_seed', True), ('world_seed', 1), ('dt_s', 60.),
                     ('infiltration_capacity_mm_h', 15.), ('shape_zx', [2049, 2049]),
                     ('coupled_intervals', 13), ('storm_rain_mm_h', [0]*72)]
        for key, value in mutations:
            with self.subTest(key=key, value=str(value)[:50]):
                request = copy.deepcopy(self.request)
                request['parameters'][key] = value
                with self.assertRaises(ValueError):
                    sources.validate_request(request)
        request = copy.deepcopy(self.request)
        request['receiver'] = [0]
        with self.assertRaisesRegex(ValueError, 'source_request_fields'):
            sources.validate_request(request)

    def test_saving_never_overwrites(self):
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            sources.save_source_request(self.path, self.request)
        self.assertEqual(self.path.read_bytes(), before)

    def command(self):
        return ['--mode', 'source-rebuild', '--source-request', str(self.path),
                '--source-request-sha256', self.pin, '--output-dir', str(self.root/'out')]

    def test_rebuild_uses_no_old_release_or_candidate_reader(self):
        with patch('tools.native_30m_bundle_reader.load_candidate', side_effect=AssertionError('old cache read')), \
             patch.object(publisher, 'inspect_release', side_effect=AssertionError('old release read')), \
             patch.object(publisher, '_compute_candidate_in_worker', return_value={
                 'manifest': {'identity_sha256': 'a'*64}, 'compute_wall_seconds': 0.,
                 'process_peak_rss_bytes': 1, 'rss_scope': 'synthetic worker stub', 'resources': {}}) as compute, \
             patch.object(publisher, 'publish_release', return_value={'mock_publication': True}) as publish, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(self.command()), 0)
        self.assertEqual(compute.call_args.args[0], self.request['source_records'])
        self.assertEqual(compute.call_args.args[1]['shape_zx'], [9, 9])
        publish.assert_called_once()

    def test_bad_page_pin_never_enters_compute(self):
        self.page.write_bytes(b'changed')
        with patch.object(publisher, '_compute_candidate_in_worker') as compute, redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(self.command()), 2)
            compute.assert_not_called()
        self.assertFalse((self.root/'out').exists())

    def test_rebuild_checks_expected_numerical_identity(self):
        with patch.object(publisher, '_compute_candidate_in_worker', return_value={'manifest': {'identity_sha256': 'b'*64}}), \
             patch.object(publisher, 'publish_release') as publish, redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(self.command()), 1)
            publish.assert_not_called()

    def test_rerun_still_rejects_invalid_release(self):
        release = self.root / 'corrupt-release'
        release.mkdir()
        (release/'release.json').write_text('{}', encoding='utf-8')
        (release/'audit.json').write_text('{}', encoding='utf-8')
        (release/'data').mkdir()
        with patch.object(publisher, '_compute_candidate_in_worker') as compute, redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(['--mode', 'rerun', '--bundle', str(release),
                                            '--output-dir', str(self.root/'out')]), 2)
            compute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
