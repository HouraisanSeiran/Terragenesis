import unittest
import tempfile
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_storage_v7 import simulate_basin_storage, save_storage, load_storage
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.td_basin_storage_v7_io import validate_saved_storage
from terrain_pipeline.td_basin_storage_v4 import exchange, parameters
from terrain_pipeline.rainfall_runoff import RunoffParameters
from tools.audit_td_basin_generation import audit_storage


class SymmetricForcingTests(unittest.TestCase):
    def test_cold_cfl_metadata_cannot_be_forged(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.zeros((2, 2)), spacing_m=30))
        result = simulate_basin_storage(hierarchy, np.zeros(1), dt_s=10)
        metadata = {**result["metadata"], "positivity_cfl": .99}
        forged = {**result, "metadata": metadata, "identity_sha256": identity(result["arrays"], metadata)}
        with self.assertRaisesRegex(ValueError, "CFL"):
            validate_saved_storage(forged)

    def test_full_solver_water_accounts_and_activity(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.array([[0., 2., 1.], [3., 4., 0.]]), spacing_m=1))
        for rain in (np.array([30., 0.]), np.zeros(2)):
            result = simulate_basin_storage(hierarchy, rain, dt_s=60,
                initial_depth_m=np.array([[1., 0., .5], [0., 0., 1.]]), parameters={"substep_s": .25})
            audit = audit_storage(result["arrays"], result["metadata"])
            self.assertLess(audit["max_step_global_residual_m3"], 1e-8)
            self.assertTrue(np.all(result["arrays"]["depth_m"] >= 0))
            self.assertFalse(result["metadata"]["hydraulic_ready"])

    def test_dry_and_actual_reverse_face_accounts(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.array([[2., 0.]]), spacing_m=1))
        dry_runoff = RunoffParameters(initial_soil_mm=0)
        dry = simulate_basin_storage(hierarchy, np.zeros(2), dt_s=10, runoff_parameters=dry_runoff, parameters={"substep_s": .25})
        self.assertEqual(dry["arrays"]["depth_m"].sum(), 0)
        self.assertEqual(dry["arrays"]["face_forward_m3"].sum(), 0)
        reverse = simulate_basin_storage(hierarchy, np.zeros(2), dt_s=10,
            initial_depth_m=np.array([[0., 4.]]), runoff_parameters=dry_runoff,
            parameters={"surface_evaporation_mm_h": 0, "substep_s": .25})
        self.assertGreater(reverse["arrays"]["face_reverse_m3"][0], 0)
        self.assertEqual(reverse["arrays"]["routed_volume_m3"][0], 0)
        self.assertLessEqual(reverse["arrays"]["active_reverse_s"][0], 20)
        self.assertLess(audit_storage(reverse["arrays"], reverse["metadata"])["max_step_global_residual_m3"], 1e-9)

    def test_saved_storage_cold_read_no_compiled_exchange(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.array([[2., 0.]]), spacing_m=1))
        result = simulate_basin_storage(hierarchy, np.array([30., 0.]), dt_s=60, parameters={"substep_s": .25})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "storage.npz"
            save_storage(path, result)
            with patch("terrain_pipeline.td_basin_storage_v4._compiled_exchange", side_effect=AssertionError("no advance")):
                loaded = load_storage(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            code = """import sys
from terrain_pipeline.td_basin_storage_v7_io import load_storage
load_storage(sys.argv[1], expected_sha256=sys.argv[2], expected_identity=sys.argv[3])
assert 'terrain_pipeline.td_basin_storage_v4' not in sys.modules
assert 'terrain_pipeline.td_basin_storage_v7' not in sys.modules
assert 'terrain_pipeline.td_basin_transport_v6' not in sys.modules
assert 'numba' not in sys.modules
"""
            completed = subprocess.run([sys.executable, "-c", code, str(path), file_sha256(path), result["identity_sha256"]],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_constant_source_full_solver_second_order(self):
        bed = np.array([[0., 0.]])
        hierarchy = build_basin_hierarchy(make_td_source(bed, spacing_m=30))
        initial = np.array([[1., .2]])
        source = np.array([.03 / 3600, .01 / 3600])
        rain = np.array([[[30., 10.]]])
        runoff = RunoffParameters(initial_soil_mm=0, potential_et_mm_h=0, percolation_mm_h=0,
                                   infiltration_capacity_mm_h=0)

        def ode(time, depth):
            flow = .6 / 30 * (depth[0] - depth[1])
            return source + np.array([-flow, flow])

        reference = solve_ivp(ode, (0, 300), initial.ravel(), method="DOP853", rtol=1e-12, atol=1e-13).y[:, -1]
        errors = []
        for step in (5., 2.5, 1.25, .625):
            result = simulate_basin_storage(hierarchy, rain, dt_s=300, initial_depth_m=initial,
                runoff_parameters=runoff, parameters={"substep_s": step, "surface_evaporation_mm_h": 0})
            errors.append(float(abs(result["arrays"]["depth_m"][-1] - reference).max()))
        self.assertTrue(all(errors[index] > 3.8 * errors[index + 1] for index in range(3)))
        self.assertLess(errors[-1], 1e-6)


if __name__ == "__main__":
    unittest.main()
