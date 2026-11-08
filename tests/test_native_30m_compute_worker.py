"""Worker isolation and failure atomicity; no real TD compute in these tests."""
from dataclasses import asdict
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import numpy as np

from tools import publish_native_30m_bundle as publisher
from tools.native_30m_compute_worker import run_worker
from tools.native_30m_resources import ComputeBudget
from tools.native_30m_sources import compute_source_request, save_source_request
from terrain_pipeline.common_infra import file_sha256


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.page = self.root / 'source.npz'
        self.page.write_bytes(b'codec fixture only, not real TD')
        self.records = [{'path': str(self.page), 'sha256': file_sha256(self.page)}]
        self.params = {'shape_zx': [9, 9], 'origin_native_xz': [0, 0],
                       'coupled_intervals': 1, 'resample_stride': 1}
        self.source = compute_source_request(self.records, self.params)
        self.request = {'schema': 'native-30m-compute-worker-v1', 'source_request': self.source,
                        'budget': asdict(ComputeBudget())}

    def test_candidate_only_with_stage_measurement(self):
        with patch.object(publisher, 'compute_native_river', return_value={}) as compute, \
             patch.object(publisher, '_write_candidate', return_value={'identity_sha256': 'a'*64}):
            report = run_worker(self.request, self.root / 'candidate')
        self.assertIs(report['candidate_only'], True)
        self.assertIsNone(report['resources']['failure'])
        self.assertGreater(report['resources']['stages']['candidate_serialization']['max_sampled_current_rss_bytes'], 0)
        self.assertEqual(compute.call_args.kwargs['shape_zx'], [9, 9])

    def test_budget_window_rejects_before_page_loading(self):
        with patch.object(publisher, 'load_native_window') as source:
            with self.assertRaisesRegex(ValueError, 'budget_window_dimension'):
                publisher.compute_native_river(self.records, shape_zx=(1338, 1338))
            source.assert_not_called()

    def test_bucket_budget_before_event_kernel(self):
        src = {'field': np.ones((9, 9)), 'resolved_mask': np.ones((9, 9), bool), 'assembly_digest': 'a'*64}
        with patch.object(publisher, 'load_native_window', return_value=src), \
             patch.object(publisher, 'build_strict_topology', return_value={}), \
             patch.object(publisher, 'select_from_topology', return_value={'chosen': {'catchment_cells': 100001}}), \
             patch.object(publisher, 'run_catchment_event') as event:
            with self.assertRaisesRegex(ValueError, 'budget_rainfall_entries'):
                publisher.compute_native_river(self.records, shape_zx=(9, 9))
            event.assert_not_called()

    def test_parent_timeout_is_refusal_not_product(self):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 1)):
            with self.assertRaisesRegex(ValueError, 'budget_seconds'):
                publisher._compute_candidate_in_worker(self.records, self.params, self.root/'candidate', ComputeBudget())
        self.assertFalse((self.root/'candidate').exists())

    def test_actual_worker_rss_limit_never_publishes(self):
        source_path = self.root / 'source-request.json'
        source_pin = save_source_request(source_path, self.source)
        target = self.root / 'out'
        with redirect_stderr(io.StringIO()):
            result = publisher.main(['--mode', 'source-rebuild', '--source-request', str(source_path),
                '--source-request-sha256', source_pin, '--output-dir', str(target), '--max-rss-bytes', '1'])
        self.assertEqual(result, 2)
        self.assertFalse(target.exists())
        evidence = list(self.root.glob('.out-failed-*/failure.json'))
        self.assertEqual(len(evidence), 1)
        self.assertIn('budget_rss', json.loads(evidence[0].read_text())['error'])
        self.assertEqual(self.page.read_bytes(), b'codec fixture only, not real TD')

    def test_source_code_drift_during_compute_refuses_candidate(self):
        with patch.object(publisher, '_code_pins', side_effect=[{'unit.py': 'a'*64}, {'unit.py': 'b'*64}]), \
             patch.object(publisher, 'compute_native_river', return_value={}), \
             patch.object(publisher, '_write_candidate', return_value={'identity_sha256': 'a'*64}):
            with self.assertRaisesRegex(ValueError, 'compute_source_code_drift_during_run'):
                run_worker(self.request, self.root/'candidate')

    def test_wrong_requested_code_pin_refused_before_compute(self):
        self.request['source_code_identity'] = {'unit.py': 'wrong'}
        with patch.object(publisher, '_code_pins', return_value={'unit.py': 'a'*64}), \
             patch.object(publisher, 'compute_native_river') as compute:
            with self.assertRaisesRegex(ValueError, 'drift_before_start'):
                run_worker(self.request, self.root/'candidate')
            compute.assert_not_called()

    def test_changed_code_between_compute_and_publish_refused(self):
        with patch.object(publisher, '_code_pins', return_value={'unit.py': 'a'*64}), \
             patch('tools.native_30m_bundle_reader.load_candidate', side_effect=AssertionError('must refuse first')):
            with self.assertRaisesRegex(ValueError, 'drift_before_publication'):
                publisher.publish_release('unused', self.root/'final',
                    provenance={'source_code_identity_at_compute': {'unit.py': 'b'*64}})
        self.assertFalse((self.root/'final').exists())

    def test_static_cli_budget_before_worker_or_output(self):
        source_path = self.root / 'source-request.json'
        source_pin = save_source_request(source_path, self.source)
        with patch.object(publisher, '_compute_candidate_in_worker') as worker, redirect_stderr(io.StringIO()):
            result = publisher.main(['--mode', 'source-rebuild', '--source-request', str(source_path),
                '--source-request-sha256', source_pin, '--output-dir', str(self.root/'out'),
                '--max-window-cells', '1'])
        self.assertEqual(result, 2)
        worker.assert_not_called()
        self.assertFalse((self.root/'out').exists())


if __name__ == '__main__':
    unittest.main()
