from copy import deepcopy
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.common_infra import BoundaryGrid, RainfallForcing
from terrain_pipeline.surface_rivers.metric_product import (
    build_diagnostic_product, load_diagnostic_product, save_diagnostic_product, validate_diagnostic_product,
    decode_diagnostic_product,
)
from tests.test_metric_river_contracts import terrain


class DiagnosticProductTests(unittest.TestCase):
    def test_product_exceeds_legacy_cell_limit_without_changing_solver(self):
        shape = (320, 320)
        grid = terrain(np.broadcast_to(np.arange(320., 0., -1), shape).copy(), dx_m=30., dz_m=30.)
        outlets = np.zeros(shape, bool)
        outlets[:, -1] = True
        boundary = BoundaryGrid.from_outlet_mask(grid, outlets,
                                                 source_id="explicit", source_sha256="b" * 64)
        forcing = RainfallForcing(np.array([0., 300.]), np.full((1,) + shape, 30.),
                                  source_id="large-pulse", source_sha256="c" * 64)
        result = build_diagnostic_product(grid, boundary, forcing)
        self.assertEqual(result["metadata"]["water_budget_m3"]["rain_input"], 230400.)
        self.assertEqual(result["metadata"]["runoff_metadata"]["algorithm"], "rainfall-runoff-v1")
        with tempfile.TemporaryDirectory() as folder:
            path = folder + "/product.npz"
            save_diagnostic_product(path, result)
            loaded = load_diagnostic_product(path, expected_sha256=file_sha256(path),
                                             expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])

    def test_full_native_grid_budget_survives_save_and_cold_validation(self):
        shape = (256, 256)
        height = np.broadcast_to(np.arange(256, 0, -1, dtype=np.float64), shape).copy()
        grid = terrain(height, dx_m=30., dz_m=30.)
        outlets = np.zeros(shape, bool)
        outlets[:, -1] = True
        boundary = BoundaryGrid.from_outlet_mask(grid, outlets,
                                                 source_id="explicit", source_sha256="b" * 64)
        rain = np.zeros((3,) + shape)
        rain[0] = 30.
        forcing = RainfallForcing(np.array([0., 300., 600., 900.]), rain,
                                  source_id="pulse", source_sha256="c" * 64)
        result = build_diagnostic_product(grid, boundary, forcing)
        self.assertEqual(result["metadata"]["water_budget_m3"]["rain_input"], 147456.)
        with tempfile.TemporaryDirectory() as folder:
            path = folder + "/product.npz"
            save_diagnostic_product(path, result)
            load_diagnostic_product(path, expected_sha256=file_sha256(path),
                                    expected_identity=result["identity_sha256"])

    def test_resealed_provenance_cannot_claim_certification(self):
        grid = terrain(np.array([[1., 0.]]))
        boundary = BoundaryGrid.from_outlet_mask(grid, np.array([[False, True]]),
                                                 source_id="explicit", source_sha256="b" * 64)
        forcing = RainfallForcing(np.array([0., 300.]), np.zeros((1, 1, 2)),
                                  source_id="dry", source_sha256="c" * 64)
        result = build_diagnostic_product(grid, boundary, forcing)
        result["metadata"]["terrain"]["hydraulic_certification_allowed"] = True
        result["identity_sha256"] = identity(result["arrays"], result["metadata"])
        with self.assertRaisesRegex(ValueError, "terrain metadata"):
            validate_diagnostic_product(result)

    def test_resealed_graph_cannot_fake_edge_length_with_zero_balanced_flow(self):
        grid = terrain(np.array([[2., 1., 0.]]))
        boundary = BoundaryGrid.from_outlet_mask(grid, np.array([[False, False, True]]),
                                                 source_id="explicit", source_sha256="b" * 64)
        forcing = RainfallForcing(np.array([0., 300.]), np.zeros((1, 1, 3)),
                                  source_id="dry", source_sha256="c" * 64)
        result = build_diagnostic_product(grid, boundary, forcing,
                                          parameters=RunoffParameters(initial_soil_mm=0.))
        for key, value in (("graph_edge_length_m", 6.),
                           ("graph_edge_slope", 1. / 3.)):
            result["arrays"][key] = result["arrays"][key].copy()
            result["arrays"][key][0] = value
        graph = decode_diagnostic_product(result)[3]
        result["metadata"]["routing_identity_sha256"] = graph.identity_sha256
        result["identity_sha256"] = identity(result["arrays"], result["metadata"])
        with self.assertRaisesRegex(ValueError, "metric edge length"):
            validate_diagnostic_product(result)

    def test_resealed_time_semantics_cannot_promote_topology_to_hydraulics(self):
        grid = terrain(np.array([[2., 1., 0.]]))
        boundary = BoundaryGrid.from_outlet_mask(grid, np.array([[False, False, True]]),
                                                 source_id="explicit", source_sha256="b" * 64)
        forcing = RainfallForcing(np.array([0., 300.]), np.ones((1, 1, 3)),
                                  source_id="rain", source_sha256="c" * 64)
        result = build_diagnostic_product(grid, boundary, forcing)
        result["metadata"]["time_semantics"]["routed_q_m3_s"] = "instantaneous_channel_discharge"
        result["identity_sha256"] = identity(result["arrays"], result["metadata"])
        with self.assertRaisesRegex(ValueError, "time semantics"):
            validate_diagnostic_product(result)

    def test_native_ledger_routes_release_and_cold_reads_without_simulation(self):
        grid = terrain(np.array([[2., 1., 0.]]))
        boundary = BoundaryGrid.from_outlet_mask(grid, np.array([[False, False, True]]),
                                                 source_id="explicit", source_sha256="b" * 64)
        forcing = RainfallForcing(np.array([0., 3600., 7200.]), np.array([[[20., 20., 20.]], [[0., 0., 0.]]]),
                                  source_id="pulse", source_sha256="c" * 64)
        params = RunoffParameters(infiltration_capacity_mm_h=0., soil_capacity_mm=0.,
                                  initial_soil_mm=0., potential_et_mm_h=0., percolation_mm_h=0.)
        result = build_diagnostic_product(grid, boundary, forcing, parameters=params)
        budget = result["metadata"]["water_budget_m3"]
        self.assertAlmostEqual(budget["rain_input"], .72)
        self.assertAlmostEqual(budget["rain_input"], budget["hydrology_storage_change"] + budget["open_outflow"])
        self.assertLess(abs(budget["combined_residual"]), 1e-12)
        self.assertEqual(result["metadata"]["status"], "diagnostic_runoff")
        self.assertFalse(result["metadata"]["publishable"])
        with tempfile.TemporaryDirectory() as folder:
            path = folder + "/product.npz"
            save_diagnostic_product(path, result)
            from unittest.mock import patch
            with patch("terrain_pipeline.surface_rivers.metric_product.runoff_from_forcing", side_effect=AssertionError("regenerated")):
                loaded = load_diagnostic_product(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            for name in loaded["arrays"]:
                np.testing.assert_array_equal(loaded["arrays"][name], result["arrays"][name])
        altered = deepcopy(result)
        altered["arrays"]["routed_q_m3_s"] = result["arrays"]["routed_q_m3_s"].copy()
        altered["arrays"]["routed_q_m3_s"][0, 0, 2] += 1.
        altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            validate_diagnostic_product(altered)


if __name__ == "__main__":
    unittest.main()
