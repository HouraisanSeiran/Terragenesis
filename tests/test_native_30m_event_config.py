"""Declared event overrides must reach the original bucket and remain reproducible."""
from dataclasses import asdict
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import numpy as np
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import run_catchment_event as run_catchment_event
from tools.native_30m_event_config import event_configuration
from tools.native_30m_sources import compute_source_request, validate_request, STORM
from tools import publish_native_30m_bundle as publisher


class EventConfigurationTests(unittest.TestCase):
    def test_default_is_original_declared_event(self):
        rain, rp = event_configuration()
        np.testing.assert_array_equal(rain, STORM)
        self.assertEqual(rp.infiltration_capacity_mm_h, 2.)

    def test_partial_parameters_merged_and_not_mutated(self):
        values = {'infiltration_capacity_mm_h': 15., 'initial_soil_mm': 40.}
        rain = [4.]*72
        actual, rp = event_configuration(rain, values)
        self.assertEqual(rp.initial_soil_mm, 40.)
        self.assertEqual(rp.fast_tau_s, 3600.)
        self.assertEqual(values, {'infiltration_capacity_mm_h': 15., 'initial_soil_mm': 40.})
        np.testing.assert_array_equal(actual, rain)

    def test_bad_storm_fields_and_initial_state_refused(self):
        for rain, rp in (([8.]*71, None), ([float('nan')]*72, None), ([-1.]*72, None),
                         ([True]*72, None), (None, {'unknown_parameter': 1}),
                         (None, {'initial_soil_mm': 200.}), (None, {'infiltration_capacity_mm_h': -1.})):
            with self.subTest(rp=rp), self.assertRaises(ValueError):
                event_configuration(rain, rp)

    def test_custom_inputs_have_versioned_source_request(self):
        parameters = {'runoff_parameters': asdict(RunoffParameters(infiltration_capacity_mm_h=15.)),
                      'infiltration_capacity_mm_h': 15., 'storm_rain_mm_h': [4.]*72}
        request = compute_source_request([{'path': 'x.npz', 'sha256': 'a'*64}], parameters)
        self.assertEqual(request['schema'], 'native-30m-source-request-v3')
        validate_request(request)
        self.assertEqual(request['parameters']['runoff_parameters']['infiltration_capacity_mm_h'], 15.)

    def test_bucket_is_distinguishable_from_declared_rain_conversion(self):
        elevation = np.array([[4., 3., 2., 1.]])
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        mask = np.ones((1, 4), bool)
        rain = np.array([8., 8., 0.])
        outputs = []
        diagnostic_inputs = []
        for infiltration in (2., 15.):
            outputs.append(run_catchment_event(elevation, receiver, mask, mask,
                origin_native_xz=[0, 0], source_identity_sha256='a'*64, world_seed=20261020,
                rain_mm_h=rain, dt_s=3600.,
                runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=infiltration)))
            diagnostic_inputs.append(rain/1000./3600.*900.)
        self.assertFalse(np.array_equal(outputs[0]['local_q_m3_s'], outputs[1]['local_q_m3_s']))
        self.assertNotEqual(outputs[0]['event_identity_sha256'], outputs[1]['event_identity_sha256'])
        np.testing.assert_array_equal(diagnostic_inputs[0], diagnostic_inputs[1])

    def test_public_compute_checks_bad_event_before_page_io(self):
        with patch.object(publisher, 'load_native_window') as source:
            with self.assertRaises(ValueError):
                publisher.compute_native_river([], runoff_parameters={'initial_soil_mm': 200.})
            source.assert_not_called()

    def test_cli_values_reach_worker_request_and_bad_initial_soil_is_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storm, rpfile = root/'rain.json', root/'runoff.json'
            storm.write_text(json.dumps([4.]*72), encoding='utf-8')
            rpfile.write_text(json.dumps({'infiltration_capacity_mm_h': 15.}), encoding='utf-8')
            flags = ['--mode', 'publish', '--td-page', 'page.npz', '--page-sha256', 'page.npz='+'a'*64,
                     '--storm-table', str(storm), '--runoff-parameters', str(rpfile), '--output-dir', str(root/'out')]
            report = {'manifest': {'identity_sha256': 'a'*64}, 'compute_wall_seconds': 0.,
                      'process_peak_rss_bytes': 1, 'rss_scope': 'synthetic stub', 'resources': {}}
            with patch.object(publisher, '_compute_candidate_in_worker', return_value=report) as worker, \
                 patch.object(publisher, 'publish_release', return_value={}), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(publisher.main(flags), 0)
            actual = worker.call_args.args[1]
            self.assertEqual(actual['storm_rain_mm_h'], [4.]*72)
            self.assertEqual(actual['runoff_parameters']['infiltration_capacity_mm_h'], 15.)
            rpfile.write_text(json.dumps({'initial_soil_mm': 200.}), encoding='utf-8')
            with patch.object(publisher, '_compute_candidate_in_worker') as worker, redirect_stderr(io.StringIO()):
                self.assertEqual(publisher.main(flags), 2)
                worker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
