import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import load_basin_storage as load_basin_storage
from terrain_pipeline.basin_storage import save_basin_storage as save_basin_storage
from terrain_pipeline.basin_storage import simulate_threshold_storage as simulate_basin_storage
from terrain_pipeline.basin_storage import validate_basin_storage as validate_basin_storage

DRY_SOIL = RunoffParameters(initial_soil_mm=0, infiltration_capacity_mm_h=0,
    potential_et_mm_h=0, percolation_mm_h=0, fast_tau_s=1, slow_tau_s=1)
NO_LOSS = {"surface_evaporation_mm_h": 0, "substep_s": 10}


class BasinStorageTests(unittest.TestCase):
    def topology(self, height, **kwargs):
        return build_basin_hierarchy(make_td_source(np.array(height, float), spacing_m=1, **kwargs))

    def simulate(self, height, depth, rain=None, **kwargs):
        topology = self.topology(height)
        return simulate_basin_storage(topology, np.zeros(1) if rain is None else rain,
            initial_depth_m=np.array(depth, float), runoff_parameters=DRY_SOIL,
            parameters=NO_LOSS, **kwargs)

    def test_dry_no_rain_no_invented_water(self):
        result = self.simulate([[0, 2, 1, 4, 0]], [[0, 0, 0, 0, 0]])
        self.assertFalse(result["arrays"]["depth_m"].any())
        self.assertFalse(result["arrays"]["routed_volume_m3"].any())
        self.assertTrue(validate_basin_storage(result))

    def test_asymmetric_fill_spill_before_dual_full_merge(self):
        result = self.simulate([[0, 2, 1, 4, 0]], [[2.5, 0, 0, 0, 0]])
        arrays = result["arrays"]
        np.testing.assert_allclose(arrays["depth_m"][-1], [2, 0, 0.5, 0, 0], atol=1e-9)
        self.assertEqual(arrays["wet_pool_count"][-1], 2)
        self.assertAlmostEqual(arrays["face_forward_m3"][1], 0.5, places=9)
        self.assertEqual(arrays["face_forward_m3"][-1], 0)
        self.assertEqual(arrays["routed_volume_m3"][0], 0)
        self.assertEqual(arrays["routed_volume_m3"][1], 0)
        self.assertGreater(arrays["active_forward_s"][1], 0)
        self.assertTrue(validate_basin_storage(result))

    def test_saddle_full_threshold_and_parent_marginal(self):
        full = self.simulate([[0, 2, 1, 4, 0]], [[3, 0, 0, 0, 0]])
        np.testing.assert_allclose(full["arrays"]["depth_m"][-1], [2, 0, 1, 0, 0], atol=1e-9)
        merged = self.simulate([[0, 2, 1, 4, 0]], [[4, 0, 0, 0, 0]])
        np.testing.assert_allclose(merged["arrays"]["depth_m"][-1], [7 / 3, 1 / 3, 4 / 3, 0, 0], atol=1e-9)
        self.assertEqual(merged["arrays"]["wet_pool_count"][-1], 1)
        self.assertAlmostEqual(merged["arrays"]["depth_m"][-1].sum(), 4, places=12)

    def test_outer_geolink_spills_only_after_left_component_full(self):
        result = self.simulate([[0, 2, 1, 4, 0]], [[9.5, 0, 0, 0, 0]], dt_s=7200)
        np.testing.assert_allclose(result["arrays"]["depth_m"][-1], [4, 2, 3, 0, 0.5], atol=1e-9)
        self.assertEqual(result["arrays"]["wet_pool_count"][-1], 2)
        self.assertAlmostEqual(result["arrays"]["face_forward_m3"][-1], 0.5, places=9)

    def test_finite_time_does_not_teleport_along_receiver(self):
        result = self.simulate([[3, 2, 1, 0]], [[1, 0, 0, 0]], dt_s=1)
        self.assertEqual(result["arrays"]["depth_m"][-1, -1], 0)
        self.assertGreater(result["arrays"]["depth_m"][-1, 0], 0)
        self.assertGreater(result["arrays"]["depth_m"][-1, 1], 0)

    def test_wet_recession_splits_and_is_conservative(self):
        topology = self.topology([[0, 2, 1, 4, 0]])
        result = simulate_basin_storage(topology, np.zeros(4), initial_depth_m=[[7 / 3, 1 / 3, 4 / 3, 0, 0]],
            runoff_parameters=DRY_SOIL, parameters={"surface_evaporation_mm_h": 200, "substep_s": 10})
        arrays = result["arrays"]
        self.assertEqual(arrays["wet_pool_count"][0], 1)
        self.assertEqual(arrays["wet_pool_count"][-1], 2)
        self.assertEqual(arrays["depth_m"][-1, 3], 0)
        self.assertAlmostEqual(arrays["depth_m"][-1].sum() + arrays["surface_et_m3"].sum(), 4, places=10)
        self.assertTrue(validate_basin_storage(result))

    def test_low_boundary_exports_before_root_height(self):
        topology = self.topology([[0, 2, 1, 100, 0]], open_boundary_mask=np.array([[True, False, False, False, False]]))
        result = simulate_basin_storage(topology, np.zeros(1), initial_depth_m=[[1, 0, 0, 0, 0]],
            runoff_parameters=DRY_SOIL, parameters=NO_LOSS)
        self.assertAlmostEqual(result["arrays"]["boundary_outflow_m3"].sum(), 1, places=9)
        self.assertEqual(result["arrays"]["routed_volume_m3"].sum(), 0)

    def test_unknown_never_crossed_and_protected_bed_unchanged(self):
        topology = self.topology([[0, 0, 0]], valid_mask=np.array([[True, False, True]]),
                                 protected_mask=np.array([[True, False, False]]))
        result = simulate_basin_storage(topology, np.zeros(1), initial_depth_m=[[3, 0, 0]],
            runoff_parameters=DRY_SOIL, parameters=NO_LOSS)
        np.testing.assert_array_equal(result["arrays"]["depth_m"][-1], [3, 0, 0])
        np.testing.assert_array_equal(result["arrays"]["height_m"], topology["arrays"]["height_m"])

    def test_multiple_saddles_and_forward_reverse_waterbook(self):
        result = self.simulate([[0, 2, 0], [2, 3, 2], [0, 2, 0]], [[12, 0, 0], [0, 0, 0], [0, 0, 0]])
        arrays = result["arrays"]
        self.assertAlmostEqual(arrays["depth_m"][-1].sum(), 12, places=10)
        self.assertTrue(validate_basin_storage(result))
        self.assertGreater(int((arrays["face_forward_m3"] > 0).sum()), 2)

    def test_half_step_sensitivity_and_symmetric_saddles(self):
        topology = self.topology([[0, 2, 1, 4, 0]])
        outputs = []
        for substep in (10, 5, 2.5):
            outputs.append(simulate_basin_storage(topology, np.zeros(1), dt_s=3600,
                initial_depth_m=[[4, 0, 0, 0, 0]], runoff_parameters=DRY_SOIL,
                parameters={"surface_evaporation_mm_h": 0, "substep_s": substep})["arrays"]["depth_m"][-1])
        np.testing.assert_allclose(outputs[0], outputs[1], atol=1e-9)
        np.testing.assert_allclose(outputs[1], outputs[2], atol=1e-9)
        short_outputs = []
        for substep in (0.02, 0.01, 0.005):
            short_outputs.append(simulate_basin_storage(topology, np.zeros(1), dt_s=1,
                initial_depth_m=[[4, 0, 0, 0, 0]], runoff_parameters=DRY_SOIL,
                parameters={"surface_evaporation_mm_h": 0, "substep_s": substep})["arrays"]["depth_m"][-1])
        coarse = np.linalg.norm(short_outputs[0] - short_outputs[1])
        fine = np.linalg.norm(short_outputs[1] - short_outputs[2])
        self.assertLess(fine, coarse)
        self.assertLess(coarse, 0.01)
        symmetric = self.simulate([[0, 2, 0], [2, 3, 2], [0, 2, 0]], [[12, 0, 0], [0, 0, 0], [0, 0, 0]])
        np.testing.assert_allclose(symmetric["arrays"]["depth_m"][-1].reshape(3, 3),
                                   symmetric["arrays"]["depth_m"][-1].reshape(3, 3).T, atol=1e-10)

    def test_fixed_ordinary_strong_24_step_forcing(self):
        topology = self.topology([[0, 2, 1]])
        for rate, total in ((10, 0.18), (30, 0.54)):
            rain = np.zeros(24)
            rain[:6] = rate
            result = simulate_basin_storage(topology, rain, runoff_parameters=DRY_SOIL, parameters=NO_LOSS)
            arrays = result["arrays"]
            self.assertAlmostEqual(arrays["rain_volume_m3"].sum(), total, places=10)
            self.assertAlmostEqual(arrays["depth_m"][-1].sum() + arrays["fast_mm"][-1].sum() / 1000, total, places=10)
            self.assertTrue(validate_basin_storage(result))

    def test_land_lake_partition_and_soil_fast_slow_balance(self):
        topology = self.topology([[0, 2, 1]])
        result = simulate_basin_storage(topology, np.array([10., 30., 0., 0.]), initial_depth_m=[[0.1, 0, 0]])
        arrays = result["arrays"]
        np.testing.assert_allclose(arrays["lake_rain_m3"] + arrays["land_rain_m3"], arrays["rain_volume_m3"], atol=1e-12)
        self.assertGreater(arrays["lake_rain_m3"].sum(), 0)
        self.assertGreater(arrays["land_rain_m3"].sum(), 0)
        self.assertGreater(arrays["slow_mm"][-1].sum(), 0)
        self.assertTrue(validate_basin_storage(result))

    def test_budget_invalid_inputs_and_cold_no_simulation(self):
        topology = self.topology([[0, 2, 1]])
        with self.assertRaises(ValueError):
            simulate_basin_storage(topology, np.ones(24), parameters={"max_substeps": 1})
        for depth in ([[float("nan"), 0, 0]], [[-1, 0, 0]]):
            with self.assertRaises(ValueError):
                simulate_basin_storage(topology, np.zeros(1), initial_depth_m=depth)
        result = simulate_basin_storage(topology, np.array([10., 0.]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "storage.npz"
            save_basin_storage(path, result)
            with patch('terrain_pipeline.basin_storage.simulate_threshold_storage', side_effect=AssertionError("cold advance forbidden")):
                loaded = load_basin_storage(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertEqual(result["identity_sha256"], loaded["identity_sha256"])
            with self.assertRaises(ValueError):
                load_basin_storage(path, expected_sha256="0" * 64, expected_identity=result["identity_sha256"])
            corrupted = dict(result, arrays=dict(result["arrays"]))
            corrupted["arrays"]["routed_volume_m3"] = result["arrays"]["routed_volume_m3"] + 1
            with self.assertRaises(ValueError):
                save_basin_storage(Path(directory) / "bad.npz", corrupted)
            self.assertFalse((Path(directory) / "bad.npz").exists())


if __name__ == "__main__":
    unittest.main()
