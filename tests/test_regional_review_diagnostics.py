from copy import deepcopy
import unittest
import json
from pathlib import Path

from tools.verify_regional_review_diagnostics import diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_real_dry_and_failure_summaries(self):
        from terrain_pipeline.regional_surface_review import read_bounded_json
        root = Path(__file__).resolve().parents[1]
        cases = (
            ('full-20261001T101153406000Z/dry-summary.json', '7b4c08160378f69d5bddaee5dbd8a5f800c013666bc9daa383de7094a5c03b1b',
                'dry', '0ef7e6afacf02aa41696e3103baff6b5fa59f9366c7fba4d8748fa0190e6a1c3', 259200.),
            ('failure-20261001T102852005353Z/work_two_commit-summary.json', '40a4dfbd23cab7eb3819622df12863a3728ec17af113f407e889d75d0a606262',
                'uniform_heavy', '699a34ee51a68d98aa99a1c63a0cc9435845a2fb315a9e51b0f9343b3a839bbc', 60.),
            ('full-20261001T101153406000Z/wet_no_rain-summary.json', 'cd9754c1308302bb164b0d155e3f4fe16d71945d27a1755f6a4728403424bb04',
                'wet_no_rain', 'f34e963d4cb3b3b0afc3a7e884aa97aa486b8f8f240aee251becc9297efc45ca', 259200.),
        )
        for path, sha, forcing_case, forcing_sha, committed in cases:
            summary = read_bounded_json(root / 'verification/regional-hydraulics' / path, expected_sha256=sha)
            forcing = read_bounded_json(root / 'verification/regional-forcing/run-20261001T095608600719Z' / forcing_case / 'manifest.json',
                expected_sha256=forcing_sha)
            data = diagnostics(summary, forcing)
            self.assertEqual(data['committed_time_s'], committed)
            self.assertTrue(all(rate['end_s'] <= committed for rate in data['forcing_rates']))
            if forcing_case == 'wet_no_rain':
                self.assertGreater(data['frames'][-1]['total_volume_m3'], data['frames'][-2]['total_volume_m3'])
                self.assertEqual(sum(rate['rain_mean_mm_h'] for rate in data['forcing_rates']), 0.)

    def fixture(self):
        summary = {'source_identity': 'test', 'frames': [{'time_s': t, 'total_volume_m3': t,
            'preceding_saved_interval_external_outflow_mean_m3_s': 0. if t else None,
            'preceding_saved_interval_external_inflow_mean_m3_s': 0. if t else None,
            'partitions': {'potential_lake': {'volume_m3': t * .25}, 'non_lake': {'volume_m3': t * .75}}}
            for t in (0., 450.)], 'rain_soil_surface': {}, 'non_DAG': {}}
        forcing = {'source_identity': 'test', 'steps': 1, 'dt_s': 900.,
            'ledger': {'rain_m3': [900.], 'runoff_m3': [450.], 'et_m3': [0.]}}
        return summary, forcing

    def test_partial_commit_rates_keep_physical_time(self):
        summary, forcing = self.fixture()
        data = diagnostics(summary, forcing)
        self.assertEqual(data['forcing_rates'][0]['end_s'], 450.)
        self.assertEqual(data['forcing_rates'][0]['runoff_mean_m3_s'], .5)
        self.assertIn('not instantaneous', data['scope'])

    def test_bad_partition_time_and_source_rejected(self):
        summary, forcing = self.fixture()
        for key, value in [('time_s', float('nan')), ('total_volume_m3', -1.), ('total_volume_m3', 451.)]:
            forged = deepcopy(summary)
            forged['frames'][-1][key] = value
            with self.assertRaises(ValueError):
                diagnostics(forged, forcing)
        with self.assertRaises(ValueError):
            diagnostics(summary, dict(forcing, source_identity='different'))

    def test_saved_failure_prefix_and_incoming_curve(self):
        summary, forcing = self.fixture()
        metadata = {'source_identity': 'test', 'status': 'refused',
            'requested_time_s': 259200., 'committed_time_s': 450.,
            'failure': {'reason': 'budget', 'time_s': 450.}}
        data = diagnostics(summary, forcing, case_metadata=metadata)
        self.assertEqual(data['case_status']['status'], 'refused')
        self.assertEqual(data['incoming_intervals'][0]['end_s'], 450.)
        with self.assertRaises(ValueError):
            diagnostics(summary, forcing, case_metadata=dict(metadata, status='completed'))


if __name__ == '__main__':
    unittest.main()
