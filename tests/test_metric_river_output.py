import tempfile
import unittest
from copy import deepcopy

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.surface_rivers.metric_contracts import BoundaryGrid, RainfallForcing
from terrain_pipeline.surface_rivers.metric_product import build_diagnostic_product
from terrain_pipeline.surface_rivers.metric_output import (
    load_diagnostic_output, sample_diagnostic_output, save_diagnostic_output,
    validate_diagnostic_output,
)
from tests.test_metric_river_contracts import terrain


def product():
    grid = terrain(np.array([[2., 1., 0.]]))
    boundary = BoundaryGrid.from_outlet_mask(grid, np.array([[False, False, True]]),
                                             source_id="edge", source_sha256="b" * 64)
    forcing = RainfallForcing(np.array([10., 310., 610.]),
                              np.array([[[30., 30., 30.]], [[0., 0., 0.]]]),
                              source_id="pulse", source_sha256="c" * 64)
    params = RunoffParameters(infiltration_capacity_mm_h=0., soil_capacity_mm=0.,
                              initial_soil_mm=0., potential_et_mm_h=0., percolation_mm_h=0.)
    return build_diagnostic_product(grid, boundary, forcing, parameters=params)


class DiagnosticOutputTests(unittest.TestCase):
    def test_sparse_output_integrates_intervals_and_cold_reads(self):
        source = product()
        dense = sample_diagnostic_output(source, [0, 1, 2], product_sha256="d" * 64)
        sparse = sample_diagnostic_output(source, [0, 2], product_sha256="d" * 64)
        self.assertEqual(sparse["arrays"]["state_time_seconds"].tolist(), [10., 610.])
        self.assertEqual(sparse["arrays"]["interval_seconds"].tolist(), [600.])
        np.testing.assert_array_equal(sparse["arrays"]["fast_mm"][-1], dense["arrays"]["fast_mm"][-1])
        np.testing.assert_allclose(sparse["arrays"]["local_q_m3_s"][0] * 600.,
                                   (dense["arrays"]["local_q_m3_s"] * 300.).sum(axis=0), atol=1e-12)
        for name in ("local_release_volume_m3", "open_outflow_volume_m3", "rain_volume_m3",
                     "et_volume_m3", "storage_change_m3"):
            self.assertAlmostEqual(sparse["arrays"][name][0], dense["arrays"][name].sum())
        self.assertAlmostEqual(sparse["arrays"]["cumulative_local_release_m3"][-1],
                               dense["arrays"]["cumulative_local_release_m3"][-1])
        self.assertEqual(sparse["metadata"]["source_product_identity_sha256"], source["identity_sha256"])
        with tempfile.TemporaryDirectory() as folder:
            path = folder + "/sample.npz"
            save_diagnostic_output(path, sparse)
            cold = load_diagnostic_output(path, expected_sha256=file_sha256(path),
                                          expected_identity=sparse["identity_sha256"],
                                          expected_product_identity=source["identity_sha256"],
                                          expected_product_sha256="d" * 64)
            np.testing.assert_array_equal(cold["arrays"]["local_q_m3_s"], sparse["arrays"]["local_q_m3_s"])

    def test_bad_state_indices_and_bad_external_pin_are_rejected(self):
        source = product()
        for values in ([1, 2], [0, 1], [0, 2, 1], [0, 1, 1, 2], [0., 2.], [False, True]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                sample_diagnostic_output(source, values)
        sampled = sample_diagnostic_output(source, [0, 2], product_sha256="d" * 64)
        with tempfile.TemporaryDirectory() as folder:
            path = folder + "/sample.npz"
            save_diagnostic_output(path, sampled)
            with self.assertRaises(ValueError):
                load_diagnostic_output(path, expected_sha256=file_sha256(path),
                                       expected_identity=sampled["identity_sha256"],
                                       expected_product_identity=source["identity_sha256"],
                                       expected_product_sha256="e" * 64)

    def test_rehashed_semantics_times_and_negative_ledger_are_rejected(self):
        sampled = sample_diagnostic_output(product(), [0, 2], product_sha256="d" * 64)
        changes = (("metadata", "q_semantics", "instantaneous"),
                   ("metadata", "source_interval_semantics", "sampled_only"),
                   ("arrays", "state_time_seconds", np.array([10., 700.])),
                   ("arrays", "rain_volume_m3", np.array([-1.])))
        for section, key, value in changes:
            altered = deepcopy(sampled)
            altered[section][key] = value
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_diagnostic_output(altered)
        for key, value in (("combined_residual", 1.), ("rain_input", -1.)):
            altered = deepcopy(sampled)
            altered["metadata"]["source_water_budget_m3"][key] = value
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_diagnostic_output(altered)
        for key, value in (("grid_shape_zx", [-1, -3]),
                           ("source_solver_dt_seconds", 1e100)):
            altered = deepcopy(sampled)
            altered["metadata"][key] = value
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_diagnostic_output(altered)


if __name__ == "__main__":
    unittest.main()
