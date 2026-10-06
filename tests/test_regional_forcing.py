import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from terrain_pipeline.regional_surface_forcing import advance_soil, preflight, load_forcing
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.rainfall_runoff import RunoffParameters, simulate_rainfall_runoff
from terrain_pipeline.regional_surface_review import read_bounded_json

CANONICAL_FORCING = Path(__file__).resolve().parents[1] / 'verification/regional-forcing/run-20261001T095608600719Z'
SOURCE_IDENTITY = '81d12179658ed02fefc94883cea1ce32888ff36199952d2bd88f68eb576f8cb2'
DRY_MANIFEST_SHA = '0ef7e6afacf02aa41696e3103baff6b5fa59f9366c7fba4d8748fa0190e6a1c3'


def canonical_manifest():
    return read_bounded_json(CANONICAL_FORCING / 'dry/manifest.json', expected_sha256=DRY_MANIFEST_SHA)

class RegionalForcingTests(unittest.TestCase):

    def test_streamed_formula_matches_frozen_reference(self):
        rain = np.array([[0.0, 24.0, 4.0], [24.0, 0.0, 8.0], [0.0, 0.0, 0.0]])
        parameters = RunoffParameters(initial_soil_mm=135.0)
        reference = simulate_rainfall_runoff(rain, np.full(3, 900.0), dt_s=900.0, source_id='synthetic', parameters=parameters)
        states = np.tile(np.array([135.0, 0.0, 0.0])[:, None], (1, 3))
        for step in range(3):
            states, release, et, change = advance_soil(rain[step], states, dt_s=900.0, parameters=parameters)
            np.testing.assert_array_equal(states[0], reference['soil_mm'][step + 1])
            np.testing.assert_array_equal(states[1], reference['fast_mm'][step + 1])
            np.testing.assert_array_equal(states[2], reference['slow_mm'][step + 1])
            np.testing.assert_allclose(release * 0.9, reference['outflow_volume_m3'][step], atol=1e-14, rtol=0)
            np.testing.assert_allclose(et * 0.9, reference['et_volume_m3'][step], atol=1e-14, rtol=0)
            np.testing.assert_allclose(change * 0.9, reference['storage_change_m3'][step], atol=1e-14, rtol=0)

    def test_dry_no_input_exact_zero(self):
        state, release, et, change = advance_soil(np.zeros(4), np.zeros((3, 4)), dt_s=900.0, parameters=RunoffParameters(initial_soil_mm=0.0))
        self.assertEqual(state.sum() + release.sum() + et.sum() + change.sum(), 0.0)

    def test_independent_budget(self):
        budget = preflight(65536, 288, 4096, 900.0)
        self.assertLess(budget['estimated_memory_bytes'], 128 * 1024 * 1024)
        self.assertLess(budget['estimated_uncompressed_output_bytes'], 512 * 1024 * 1024)
        with self.assertRaises(ValueError):
            preflight(65536, 289, 4096, 900.0)

    def test_invalid_forcing_rejected(self):
        with self.assertRaises(ValueError):
            advance_soil(np.array([float('nan')]), np.zeros((3, 1)), dt_s=900.0, parameters=RunoffParameters())

    def test_real_cold_read_is_readonly_and_never_advances(self):
        root = Path(__file__).resolve().parents[1]
        directory = CANONICAL_FORCING / 'dry'
        meta = canonical_manifest()
        with patch('terrain_pipeline.regional_surface_forcing.advance_soil', side_effect=AssertionError('cold read advanced')), patch('terrain_pipeline.regional_surface_forcing.generate_forcing', side_effect=AssertionError('cold generated')), patch('terrain_pipeline.regional_surface_forcing.interval_mean_mm_h', side_effect=AssertionError('cold weather')):
            loaded = load_forcing(directory, expected_manifest_sha256=DRY_MANIFEST_SHA, source_identity=SOURCE_IDENTITY)
        try:
            self.assertEqual(loaded['runoff_volume_m3'].shape, (288, 256, 256))
            self.assertEqual(loaded['seconds_edges'][-1], 259200.)
            with self.assertRaises(ValueError):
                loaded['runoff_volume_m3'][0, 0, 0] = 1.
        finally:
            loaded['runoff_volume_m3']._mmap.close()

    def test_canonical_wet_and_storm_full_grid_accounts(self):
        cases = (
            ('wet_no_rain', 'f34e963d4cb3b3b0afc3a7e884aa97aa486b8f8f240aee251becc9297efc45ca', 0.),
            ('uniform_heavy', '699a34ee51a68d98aa99a1c63a0cc9435845a2fb315a9e51b0f9343b3a839bbc', 16986931.2),
        )
        for name, digest, rain in cases:
            with self.subTest(case=name), patch('terrain_pipeline.regional_surface_forcing.advance_soil', side_effect=AssertionError('cold advanced')):
                loaded = load_forcing(CANONICAL_FORCING / name, expected_manifest_sha256=digest,
                    source_identity=SOURCE_IDENTITY)
                try:
                    self.assertEqual(loaded['runoff_volume_m3'].shape, (288, 256, 256))
                    self.assertEqual(loaded['seconds_edges'].shape, (289,))
                    self.assertAlmostEqual(loaded['metadata']['total_rain_m3'], rain, places=6)
                    self.assertLess(abs(loaded['metadata']['whole_account_residual_m3']), 1e-6)
                    np.testing.assert_array_equal(loaded['initial_states_mm'][0], np.full((256, 256), 135.))
                finally:
                    loaded['runoff_volume_m3']._mmap.close()

    def test_resigned_negative_dt_rejected_before_array_load(self):
        root = Path(__file__).resolve().parents[1]
        meta = canonical_manifest()
        meta['dt_s'] = -900.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'manifest.json'
            path.write_text(json.dumps(meta), encoding='utf-8')
            with patch('numpy.load', side_effect=AssertionError('allocated before reject')):
                with self.assertRaises(ValueError):
                    load_forcing(path.parent, expected_manifest_sha256=file_sha256(path), source_identity=meta['source_identity'])

    def test_resigned_escaping_path_rejected(self):
        root = Path(__file__).resolve().parents[1]
        meta = canonical_manifest()
        meta['runoff_path'] = '../escape.npy'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'manifest.json'
            path.write_text(json.dumps(meta), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'basenames'):
                load_forcing(path.parent, expected_manifest_sha256=file_sha256(path), source_identity=meta['source_identity'])

    def test_boolean_dt_and_excess_soil_rejected(self):
        with self.assertRaises(ValueError):
            advance_soil(np.zeros(1), np.zeros((3, 1)), dt_s=True, parameters=RunoffParameters())
        with self.assertRaises(ValueError):
            advance_soil(np.zeros(1), np.array([[151.], [0.], [0.]]), dt_s=900., parameters=RunoffParameters())

    def test_payload_hash_and_typed_header_rejected_before_np_load(self):
        root = Path(__file__).resolve().parents[1]
        original = canonical_manifest()
        for resign in (False, True):
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                np.save(directory / 'runoff_volume_m3.npy', np.zeros((1, 100), np.float64), allow_pickle=False)
                meta = dict(original)
                if resign:
                    meta['runoff_sha256'] = file_sha256(directory / 'runoff_volume_m3.npy')
                path = directory / 'manifest.json'
                path.write_text(json.dumps(meta), encoding='utf-8')
                with patch('numpy.load', side_effect=AssertionError('allocated before typed rejection')):
                    with self.assertRaises(ValueError):
                        load_forcing(directory, expected_manifest_sha256=file_sha256(path), source_identity=meta['source_identity'])
if __name__ == '__main__':
    unittest.main()
