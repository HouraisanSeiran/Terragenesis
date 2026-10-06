import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_overflow import OverflowParameters, build_overflow_topology
from terrain_pipeline.td_basin_overflow_implicit import (load_stable_overflow, save_stable_overflow,
                                                        simulate_stable_overflow, validate_stable_overflow)
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from tools.audit_td_original_bed_overflow import audit_saved_arrays


class StableOverflowTests(unittest.TestCase):
    def fixture(self, height=None, opened=None):
        height = np.array([[0., 1., 0.]]) if height is None else height
        return build_overflow_topology(build_basin_hierarchy(make_td_source(
            height, spacing_m=1., open_boundary_mask=opened)))

    def test_closed_reservoirs_equilibrate_without_directional_ping_pong(self):
        topology = self.fixture()
        event = simulate_stable_overflow(topology, np.zeros(12),
            parameters=OverflowParameters(timestep_s=300., duration_s=3600.), initial_volume_m3=[10., 0.])
        self.assertLess(float(np.ptp(event["arrays"]["stage_m"][-1])), .001)
        self.assertLess(float(event["arrays"]["face_reverse_m3"].sum()), 1e-8)
        self.assertLess(float(event["arrays"]["face_volume_m3"].sum()), 4.)

    def test_reverse_flow_is_preserved_not_clipped_as_a_fix(self):
        topology = self.fixture()
        event = simulate_stable_overflow(topology, np.zeros(12),
            parameters=OverflowParameters(timestep_s=300., duration_s=3600.), initial_volume_m3=[0., 10.])
        self.assertGreater(float(event["arrays"]["face_reverse_m3"].sum()), 6.)
        self.assertLess(float(event["arrays"]["face_forward_m3"].sum()), 1e-8)
        self.assertLess(float(np.ptp(event["arrays"]["stage_m"][-1])), .001)

    def test_subsill_storage_does_not_cross_saddle(self):
        topology = self.fixture()
        event = simulate_stable_overflow(topology, np.zeros(2),
            parameters=OverflowParameters(timestep_s=300., duration_s=600.), initial_volume_m3=[.1, 0.])
        self.assertEqual(float(event["arrays"]["face_volume_m3"].sum()), 0.)
        self.assertTrue(np.all(event["arrays"]["spill_onset_step"] == -1))
        self.assertTrue(np.all(event["arrays"]["spill_last_active_step"] == -1))

    def test_reference_two_basin_linear_relaxation_at_first_step(self):
        topology = self.fixture()
        config = OverflowParameters(timestep_s=300., duration_s=300.)
        event = simulate_stable_overflow(topology, np.zeros(1), parameters=config, initial_volume_m3=[10., 5.])
        supplied = 3. * config.baseflow_mm_per_day * 300. / 86_400_000.
        total = 15. + supplied
        expected_gap = .5 / (1. + 300. * .6 * (1. / 2. + 1.))
        expected_second = (total + 1. - 2. * expected_gap) / 3.
        self.assertAlmostEqual(float(event["arrays"]["stage_m"][-1, 1]), expected_second, places=9)
        self.assertAlmostEqual(float(np.diff(event["arrays"]["stage_m"][-1])[0]), -expected_gap, places=9)

    def test_boundary_drainage_is_positive_and_accounted(self):
        topology = self.fixture(np.array([[0., 1., 0.]]), np.array([[True, False, True]]))
        event = simulate_stable_overflow(topology, np.full(4, 600.),
            parameters=OverflowParameters(timestep_s=300., duration_s=1200.), substep_s=150.)
        self.assertTrue(np.all(event["arrays"]["volume_m3"] >= 0.))
        self.assertGreater(float(event["arrays"]["engineering_boundary_outflow_m3"].sum()), 0.)
        report = audit_saved_arrays(topology, event)
        self.assertLess(report["max_abs_basin_residual_m3"], 1e-7)
        self.assertFalse(event["metadata"]["natural_outlet_verified"])

    def test_timestep_refinement_does_not_change_equilibrium(self):
        topology = self.fixture()
        config = OverflowParameters(timestep_s=300., duration_s=3600.)
        first = simulate_stable_overflow(topology, np.zeros(12), parameters=config, substep_s=300., initial_volume_m3=[10., 0.])
        second = simulate_stable_overflow(topology, np.zeros(12), parameters=config, substep_s=150., initial_volume_m3=[10., 0.])
        np.testing.assert_allclose(first["arrays"]["volume_m3"][-1], second["arrays"]["volume_m3"][-1], atol=1e-8)
        self.assertLess(audit_saved_arrays(topology, second)["max_stage_inversion_error_m"], 1e-8)

    def test_actual_time_varying_supply_can_reverse_flow(self):
        topology = self.fixture(np.array([[0., 1., 0.]]), np.array([[False, False, True]]))
        event = simulate_stable_overflow(topology, np.concatenate((np.zeros(4), np.full(8, 100000.))),
            parameters=OverflowParameters(timestep_s=300., duration_s=3600., boundary_conductance_m_s=.00001), initial_volume_m3=[0., 10.])
        self.assertGreater(float(event["arrays"]["face_reverse_m3"].sum()), 1.)
        self.assertGreater(float(event["arrays"]["face_forward_m3"].sum()), .001)
        audit_saved_arrays(topology, event)

    def test_multiple_dry_and_sill_crossing_cells_remain_feasible(self):
        generator = np.random.default_rng(42)
        for sample in range(12):
            topology = self.fixture(generator.integers(0, 15, size=(5, 5)).astype(float))
            rain = generator.choice([0., 20000., 200000.], size=8)
            event = simulate_stable_overflow(topology, rain,
                parameters=OverflowParameters(timestep_s=300., duration_s=2400.))
            self.assertGreaterEqual(float(event["arrays"]["volume_m3"].min()), 0.)
            self.assertLess(audit_saved_arrays(topology, event)["max_abs_basin_residual_m3"], 1e-7)

    def test_pin_and_read_only_saved_consumption_without_solver(self):
        topology = self.fixture()
        event = simulate_stable_overflow(topology, np.full(4, 600.),
            parameters=OverflowParameters(timestep_s=300., duration_s=1200.), substep_s=150.)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.npz"
            save_stable_overflow(event, path, topology)
            with patch("terrain_pipeline.td_basin_overflow_implicit.simulate_stable_overflow", side_effect=AssertionError("solver forbidden")):
                loaded = load_stable_overflow(path, expected_sha256=file_sha256(path), expected_identity=event["identity_sha256"], topology=topology)
            self.assertEqual(loaded["identity_sha256"], event["identity_sha256"])
            self.assertFalse(loaded["arrays"]["volume_m3"].flags.writeable)
            with self.assertRaises(ValueError):
                load_stable_overflow(path, expected_sha256="0" * 64, expected_identity=event["identity_sha256"], topology=topology)

    def test_rejects_bad_substeps_topology_and_forged_activity(self):
        topology = self.fixture()
        config = OverflowParameters(timestep_s=300., duration_s=600.)
        for substep in (-1., 0., 70., np.nan):
            with self.assertRaises(ValueError):
                simulate_stable_overflow(topology, np.zeros(2), parameters=config, substep_s=substep)
        event = simulate_stable_overflow(topology, np.full(2, 12000.), parameters=config)
        changed = {"arrays": {key: value.copy() for key, value in event["arrays"].items()}, "metadata": event["metadata"]}
        changed["arrays"]["face_forward_active_s"].fill(1000.)
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_stable_overflow(changed, topology)


if __name__ == "__main__":
    unittest.main()
