"""Diagnostic conversion is cold-readable but cannot impersonate the full chain."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import numpy as np
from terrain_pipeline.artifacts.contracts import digest
from terrain_pipeline.common_infra import file_sha256
from tools import publish_native_30m_bundle as publisher
from tools.native_30m_diagnostic_only import build_diagnostic_candidate, load_diagnostic, publish_diagnostic
from tools.native_30m_query import query_point, ScopeRefusal
from tests.test_native_30m_bundle_validation import graph_fixture


class DiagnosticOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        graph = graph_fixture()['arrays']
        self.source = self.root/'assembly.npz'
        with self.source.open('xb') as stream:
            np.savez(stream, elevation_m=graph['source.npz']['field'],
                     covered_mask=graph['source.npz']['resolved_mask'], receiver=graph['topology.npz']['receiver'],
                     origin_native_cells=np.array([100, 200], np.int64), metadata_json=np.array(json.dumps({
                         'schema': 'native-30m-saved-assembly-v1', 'world_seed': 20261020, 'spacing_m': 30.})))
        self.records = [{'path': str(self.source), 'sha256': file_sha256(self.source)}]
        self.params = {'origin_native_xz': [100, 200], 'shape_zx': [9, 9], 'coupled_intervals': 1, 'resample_stride': 3}
        self.candidate = self.root/'candidate'

    def build(self):
        return build_diagnostic_candidate(self.records, self.params, self.candidate,
                                          source_kind='saved_assembly', rain_mm_h=4.)

    def reseal_metadata(self, mutate):
        path = self.candidate/'diagnostic.json'
        record = json.loads(path.read_text())
        mutate(record)
        body = {k: v for k, v in record.items() if k != 'identity_sha256'}
        record['identity_sha256'] = digest(body)
        path.write_text(json.dumps(record, allow_nan=False), encoding='utf-8')

    def test_build_does_not_run_bucket_or_reach_chain(self):
        with patch.object(publisher, 'run_catchment_event', side_effect=AssertionError('bucket called')), \
             patch.object(publisher, 'run_reach_dynamics', side_effect=AssertionError('dynamics called')):
            record = self.build()
        self.assertIs(record['is_product'], False)
        env = load_diagnostic(self.candidate)
        np.testing.assert_array_equal(env['diagnostic']['arrays']['local_q_m3_s'], np.full((9, 9), 4/1000/3600*900))
        self.assertIn('design_q', record['not_computed'])

    def test_cold_query_refuses_full_chain_scope(self):
        self.build()
        env = load_diagnostic(self.candidate)
        self.assertEqual(query_point(env, 104, 204, native=True)['elevation_m'], 0.)
        with self.assertRaisesRegex(ScopeRefusal, 'stage_absent'):
            query_point(env, 104, 204, native=True, scope='design_discharge')

    def test_resealed_full_product_claim_refused(self):
        self.build()
        self.reseal_metadata(lambda record: record.update(is_product=True))
        with self.assertRaisesRegex(ValueError, 'semantics'):
            load_diagnostic(self.candidate)

    def test_resealed_rain_metadata_cannot_change_saved_q(self):
        self.build()
        self.reseal_metadata(lambda record: record['parameters'].update(rain_mm_h=8.))
        with self.assertRaisesRegex(ValueError, 'conversion_binding'):
            load_diagnostic(self.candidate)

    def test_atomic_copy_and_inspect(self):
        self.build()
        target = self.root/'diagnostic-release'
        result = publish_diagnostic(self.candidate, target)
        self.assertIs(result['is_product'], False)
        summary = publisher.inspect_release(target, require_source_pins=True)
        self.assertIs(summary['is_product'], False)
        self.assertEqual(summary['source_code_drift'], [])
        with self.assertRaises(FileExistsError):
            publish_diagnostic(self.candidate, target)

    def test_profile_semantics_and_stage_conflicts_before_worker(self):
        for flags in (['--profile', 'full', '--rain-semantics', 'declared_conversion'],
                      ['--profile', 'diagnostic-only', '--rain-semantics', 'soil_bucket_catchment', '--rain-mm-h', '4'],
                      ['--profile', 'diagnostic-only', '--rain-mm-h', '4', '--stages', 'hydraulics'],
                      ['--profile', 'diagnostic-only', '--rain-mm-h', '4', '--coupled-intervals', '2']):
            with self.subTest(flags=flags), patch.object(publisher, '_compute_candidate_in_worker') as worker, \
                 redirect_stderr(io.StringIO()):
                self.assertEqual(publisher.main(['--mode', 'publish', '--assembly', str(self.source),
                    '--assembly-sha256', self.records[0]['sha256'], '--output-dir', str(self.root/'out')] + flags), 2)
                worker.assert_not_called()

    def test_real_worker_profile_isolation_and_cli_inspect(self):
        target = self.root/'worker-diagnostic'
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = publisher.main(['--mode', 'publish', '--assembly', str(self.source),
                '--assembly-sha256', self.records[0]['sha256'], '--window-nodes', '9',
                '--origin-native-xz', '100', '200', '--output-dir', str(target),
                '--profile', 'diagnostic-only', '--rain-mm-h', '4'])
        self.assertEqual(result, 0)
        self.assertFalse((target/'release.json').exists())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(['--mode', 'inspect', '--bundle', str(target), '--census']), 0)
            self.assertEqual(publisher.main(['--mode', 'inspect', '--bundle', str(target), '--point',
                                            '104', '204', '--native', '--scope', 'hydraulics']), 2)
            self.assertEqual(publisher.main(['--mode', 'audit', '--bundle', str(target)]), 2)


if __name__ == '__main__':
    unittest.main()
