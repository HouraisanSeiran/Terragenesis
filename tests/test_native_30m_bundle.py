"""Engineering gates; real-candidate tests are explicitly skipped if data is absent."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import publish_native_30m_bundle as publisher
from tools.native_30m_bundle_reader import (
    _jread, load_candidate, validate_candidate_shapes, validate_candidate_event,
)

CANDIDATE = publisher.ROOT / '.scratch/river-stage1-completion/m1-candidate-20261025'


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_nonfinite_and_oversized(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', ' ' * 1048577):
            with self.subTest(raw=raw[:40]), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'record.json'
                path.write_text(raw, encoding='utf-8')
                with self.assertRaises(ValueError):
                    _jread(path)


class AtomicPublicationTests(unittest.TestCase):
    def test_existing_target_is_never_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out'
            target.mkdir()
            marker = target / 'keep'
            marker.write_bytes(b'original')
            with self.assertRaises(FileExistsError):
                publisher.publish_release('missing', target)
            self.assertEqual(marker.read_bytes(), b'original')

    def test_audit_failure_never_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'src'
            src.mkdir()
            (src / 'bundle.json').write_text('{}', encoding='utf-8')
            env = {'directory': src, 'manifest': {'identity_sha256': 'a'*64}}
            target = Path(tmp) / 'out'
            with patch('tools.native_30m_bundle_reader.load_candidate', return_value=env), patch.object(
                    publisher, '_independent_audit', side_effect=RuntimeError('injected audit failure')):
                with self.assertRaisesRegex(RuntimeError, 'injected audit failure'):
                    publisher.publish_release(src, target)
            self.assertFalse(target.exists())
            failures = list(Path(tmp).glob('.out-*/failure.json'))
            self.assertEqual(len(failures), 1)
            self.assertFalse(json.loads(failures[0].read_text())['success'])
            self.assertEqual((src / 'bundle.json').read_text(), '{}')

    def test_bad_cli_combinations(self):
        self.assertEqual(publisher.main(['--mode', 'publish', '--output-dir', 'unused-test-output']), 2)
        self.assertEqual(publisher.main(['--mode', 'rerun', '--candidate', 'x', '--output-dir', 'unused-test-output']), 2)


@unittest.skipUnless(CANDIDATE.is_dir(), 'saved real TD candidate not installed')
class RealCandidateBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load_candidate(CANDIDATE)

    def setUp(self):
        self.env = dict(self.base)
        self.env['arrays'] = {key: dict(value) for key, value in self.base['arrays'].items()}
        self.env['manifest'] = copy.deepcopy(self.base['manifest'])
        self.env['json_records'] = copy.deepcopy(self.base['json_records'])
        self.env['dynamics'] = dict(self.base['dynamics'], arrays=dict(self.base['dynamics']['arrays']))

    def test_valid(self):
        validate_candidate_shapes(self.env)
        validate_candidate_event(self.env)

    def test_wrong_origin(self):
        self.env['arrays']['source.npz']['origin_native_xz'] = np.array([0, 0], np.int64)
        with self.assertRaisesRegex(ValueError, 'origin'):
            validate_candidate_shapes(self.env)

    def test_receiver_range(self):
        rec = self.env['arrays']['topology.npz']['receiver'].copy()
        rec.flat[0] = rec.size
        self.env['arrays']['topology.npz']['receiver'] = rec
        with self.assertRaises(ValueError):
            validate_candidate_shapes(self.env)

    def test_edge_distance_is_not_cumulative(self):
        rc = self.env['arrays']['reach_context.npz']
        rc['node_distance_m'] = np.cumsum(rc['node_distance_m'])
        with self.assertRaisesRegex(ValueError, 'edge distance'):
            validate_candidate_shapes(self.env)

    def test_section_coordinates(self):
        sec = self.env['arrays']['section.npz']
        sec['node_xz_m'] = sec['node_xz_m'] + 30
        with self.assertRaisesRegex(ValueError, 'coordinates'):
            validate_candidate_shapes(self.env)

    def test_negative_dynamic_stock(self):
        arr = self.env['dynamics']['arrays']['water_volume_m3'].copy()
        arr[0, 0] = -1
        self.env['dynamics']['arrays']['water_volume_m3'] = arr
        with self.assertRaisesRegex(ValueError, 'negative inventory'):
            validate_candidate_shapes(self.env)

    def test_changed_event_q_even_with_same_manifest(self):
        event = self.env['arrays']['event.npz']
        event['local_q_m3_s'] = event['local_q_m3_s'] * 2
        with self.assertRaisesRegex(ValueError, 'event array identity'):
            validate_candidate_event(self.env)

    def test_diagnostic_peak_cannot_replace_design_q(self):
        ej = self.env['json_records']['event.json']
        ej['design_q_m3_s'] = float(self.env['arrays']['event.npz']['instantaneous_terminal_q_m3_s'].max())
        with self.assertRaisesRegex(ValueError, 'routed event peak'):
            validate_candidate_event(self.env)

    def test_active_cell_order(self):
        self.env['arrays']['event.npz']['active_cells'] = self.env['arrays']['event.npz']['active_cells'][::-1]
        with self.assertRaisesRegex(ValueError, 'active catchment'):
            validate_candidate_event(self.env)

    def test_bucket_imbalance(self):
        event = self.env['arrays']['event.npz']
        event['bucket_outflow_volume_m3'] = event['bucket_outflow_volume_m3'] + 1
        with self.assertRaisesRegex(ValueError, 'bucket independent balance'):
            validate_candidate_event(self.env)

    def test_nested_time_mismatch(self):
        event = self.env['arrays']['event.npz']
        event['time_edges_s'] = event['time_edges_s'] + 3600
        with self.assertRaisesRegex(ValueError, 'time binding'):
            validate_candidate_event(self.env)


if __name__ == '__main__':
    unittest.main()
