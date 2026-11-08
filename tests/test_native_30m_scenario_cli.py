"""Explicit scenario parameters must be used or refused, never silently ignored."""
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from tools import publish_native_30m_bundle as publisher


class ScenarioCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = ['--mode', 'publish', '--td-page', 'source-page.npz', '--page-sha256',
                     'source-page.npz='+'a'*64, '--output-dir', str(Path(self.tmp.name)/'out')]
        self.worker_report = {'manifest': {'identity_sha256': 'a'*64}, 'compute_wall_seconds': 1.,
                              'process_peak_rss_bytes': 1, 'rss_scope': 'test stub', 'resources': {}}

    def dispatch(self, flags):
        with patch.object(publisher, '_compute_candidate_in_worker', return_value=self.worker_report) as worker, \
             patch.object(publisher, 'publish_release', return_value={'test_stub': True}), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = publisher.main(self.base + flags)
        return result, worker

    def test_mode_defaults_to_publish(self):
        flags = self.base[2:]
        with patch.object(publisher, '_compute_candidate_in_worker', return_value=self.worker_report) as worker, \
             patch.object(publisher, 'publish_release', return_value={'test_stub': True}), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(flags), 0)
        worker.assert_called_once()

    def test_default_window_is_1337_not_implicit_smaller_window(self):
        result, worker = self.dispatch([])
        self.assertEqual(result, 0)
        self.assertEqual(worker.call_args.args[1]['shape_zx'], [1337, 1337])
        self.assertEqual(worker.call_args.args[1]['coupled_intervals'], 12)

    def test_declared_origin_shape_intervals_and_stride_are_used(self):
        result, worker = self.dispatch(['--origin-native-xz', '-10', '20', '--window-shape', '33', '49',
                                         '--coupled-intervals', '2', '--resample-stride', '4'])
        self.assertEqual(result, 0)
        self.assertEqual(worker.call_args.args[1], {'origin_native_xz': [-10, 20], 'shape_zx': [33, 49],
                                                   'coupled_intervals': 2, 'resample_stride': 4})

    def test_explicit_square_window(self):
        result, worker = self.dispatch(['--window-nodes', '65'])
        self.assertEqual(result, 0)
        self.assertEqual(worker.call_args.args[1]['shape_zx'], [65, 65])

    def test_unsupported_scenario_rejected_before_worker(self):
        for flags in (['--world-seed', '12345'], ['--spacing-m', '10000'], ['--dt-s', '60'],
                      ['--window-nodes', '2049'], ['--coupled-intervals', '13'], ['--resample-stride', '0']):
            with self.subTest(flags=flags):
                result, worker = self.dispatch(flags)
                self.assertEqual(result, 2)
                worker.assert_not_called()

    def test_compute_budget_does_not_silently_shrink_window(self):
        result, worker = self.dispatch(['--max-window-cells', '1000'])
        self.assertEqual(result, 2)
        worker.assert_not_called()
        self.assertFalse((Path(self.tmp.name)/'out').exists())

    def test_inspect_cannot_silently_ignore_scenario_override(self):
        with patch.object(publisher, 'inspect_release') as inspect, redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(['--mode', 'inspect', '--bundle', 'x', '--window-nodes', '65']), 2)
            inspect.assert_not_called()

    def test_help_contains_no_coarse_scale_or_skip_cold_read_knob(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            publisher.main(['--help'])
        self.assertEqual(caught.exception.code, 0)
        for flag in ('--macro-span-m', '--samples-per-span', '--planning-config', '--no-cold-read',
                     '--use-diagnostic-as-design'):
            self.assertNotIn(flag, out.getvalue())


if __name__ == '__main__':
    unittest.main()
