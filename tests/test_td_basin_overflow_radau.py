import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import OverflowParameters as OverflowParameters
from terrain_pipeline.basin_storage import build_overflow_topology as build_overflow_topology
from terrain_pipeline.basin_storage import simulate_overflow as simulate_overflow
from terrain_pipeline.basin_storage import _IntegratedExchange as _IntegratedExchange
from terrain_pipeline.basin_storage import load_radau_overflow as load_radau_overflow
from terrain_pipeline.basin_storage import save_radau_overflow as save_radau_overflow
from terrain_pipeline.basin_storage import simulate_radau_overflow as simulate_radau_overflow
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from tools.audit_td_original_bed_overflow import audit_saved_arrays
from tools.verify_td_stable_overflow import compare_events


class RadauOverflowTests(unittest.TestCase):
    def fixture(self, opened=None):
        return build_overflow_topology(build_basin_hierarchy(make_td_source(
            np.array([[0., 1., 0.]]), spacing_m=1., open_boundary_mask=opened)))

    def test_closed_two_basins_have_no_macroscopic_ping_pong(self):
        topology = self.fixture()
        event = simulate_radau_overflow(topology, np.zeros(12),
            parameters=OverflowParameters(timestep_s=300., duration_s=3600.), initial_volume_m3=[10., 0.])
        self.assertLess(float(np.ptp(event["arrays"]["stage_m"][-1])), 1e-8)
        self.assertLess(float(event["arrays"]["face_reverse_m3"].sum()), 1e-8)
        self.assertLess(audit_saved_arrays(topology, event)["canceled_fraction_of_gross"], 1e-8)

    def test_legacy_large_step_reproduces_canceling_exchange_not_new_supply(self):
        topology = self.fixture()
        config = OverflowParameters(timestep_s=300., duration_s=3600.)
        rain = np.zeros(12)
        old = simulate_overflow(topology, rain, parameters=config, initial_volume_m3=[10., 0.])
        repaired = simulate_radau_overflow(topology, rain, parameters=config, initial_volume_m3=[10., 0.])
        self.assertGreater(audit_saved_arrays(topology, old)["canceled_fraction_of_gross"], .9)
        self.assertLess(audit_saved_arrays(topology, repaired)["canceled_fraction_of_gross"], 1e-8)
        np.testing.assert_allclose(old["arrays"]["input_volume_m3"], repaired["arrays"]["input_volume_m3"], rtol=0, atol=1e-20)
        self.assertAlmostEqual(float(old["arrays"]["volume_m3"][-1].sum()),
                               float(repaired["arrays"]["volume_m3"][-1].sum()), places=8)

    def test_matches_analytic_linear_relaxation_and_directional_integral(self):
        topology = self.fixture()
        config = OverflowParameters(timestep_s=1., duration_s=10.)
        event = simulate_radau_overflow(topology, np.zeros(10), parameters=config, initial_volume_m3=[10., 5.],
                                        max_step_s=1., rtol=1e-9, atol_stage_m=1e-10)
        times = np.arange(11)
        gap = .5 * np.exp(-.9 * times)
        total = 15. + 3. * config.baseflow_mm_per_day * times / 86_400_000.
        equilibrium = (total + 1.) / 3.
        expected = np.column_stack((equilibrium + gap / 3., equilibrium - 2. * gap / 3.))
        np.testing.assert_allclose(event["arrays"]["stage_m"], expected, rtol=0, atol=2e-8)
        self.assertAlmostEqual(float(event["arrays"]["face_forward_m3"].sum()), (1. - np.exp(-9.)) / 3., places=8)
        audit_saved_arrays(topology, event)

    def test_true_drainage_can_reverse_direction_without_suppression(self):
        topology = self.fixture(np.array([[False, False, True]]))
        event = simulate_radau_overflow(topology, np.concatenate((np.zeros(4), np.full(8, 100000.))),
            parameters=OverflowParameters(timestep_s=300., duration_s=3600., boundary_conductance_m_s=.00001), initial_volume_m3=[0., 10.])
        self.assertGreater(float(event["arrays"]["face_forward_m3"].sum()), .001)
        self.assertGreater(float(event["arrays"]["face_reverse_m3"].sum()), 1.)
        self.assertGreater(float(event["arrays"]["engineering_boundary_outflow_m3"].sum()), 0.)
        audit_saved_arrays(topology, event)

    def test_sparse_jacobian_matches_finite_difference(self):
        topology = self.fixture(np.array([[False, False, True]]))
        exchange = _IntegratedExchange(topology, OverflowParameters())
        values = np.array([10., 5., 0., 0., 0.])
        analytic = exchange.jacobian(0., values).toarray()
        for column in range(exchange.size):
            perturbation = np.zeros(exchange.size)
            perturbation[column] = 1e-6
            numerical = (exchange.rhs(0., values + perturbation) - exchange.rhs(0., values - perturbation)) / 2e-6
            np.testing.assert_allclose(analytic[:, column], numerical, atol=1e-8)

    def test_cold_pinned_read_is_solver_free(self):
        topology = self.fixture()
        event = simulate_radau_overflow(topology, np.full(2, 20000.),
            parameters=OverflowParameters(timestep_s=300., duration_s=600.))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.npz"
            save_radau_overflow(event, path, topology)
            with patch('terrain_pipeline.basin_storage.simulate_radau_overflow', side_effect=AssertionError("solver forbidden")):
                loaded = load_radau_overflow(path, expected_sha256=file_sha256(path), expected_identity=event["identity_sha256"], topology=topology)
            self.assertEqual(loaded["identity_sha256"], event["identity_sha256"])
            with self.assertRaises(ValueError):
                load_radau_overflow(path, expected_sha256=file_sha256(path), expected_identity="0" * 64, topology=topology)

    def test_tolerance_refinement_preserves_physics_and_same_saved_times(self):
        topology = self.fixture()
        parameters = OverflowParameters(timestep_s=300., duration_s=1800.)
        rain = np.array([0., 0., 20000., 20000., 0., 0.])
        coarse = simulate_radau_overflow(topology, rain, parameters=parameters, max_step_s=300.)
        fine = simulate_radau_overflow(topology, rain, parameters=parameters, max_step_s=150., rtol=5e-8, atol_stage_m=5e-8)
        self.assertTrue(compare_events(coarse, fine)["passed"])
        self.assertFalse(fine["metadata"]["publishable"])
        with self.assertRaises(ValueError):
            simulate_radau_overflow(topology, rain, parameters=parameters, rtol=-1.)

    def test_positive_stage_quadrature_replaces_small_auxiliary_newton_defect(self):
        exchange = _IntegratedExchange(self.fixture(), OverflowParameters())
        previous = np.array([10., 5., 0., 0.])
        expected = previous + .01 * exchange.rhs(0., previous)
        approximate = expected.copy()
        approximate[-1] = -2e-8
        solver = SimpleNamespace(y=approximate, Z=np.zeros((3, 4)), t=.01)
        exchange.conservative_step(solver, previous, .01, np.full(4, .001), 1e-7)
        np.testing.assert_allclose(solver.y, expected, rtol=0, atol=1e-14)
        self.assertGreaterEqual(float(solver.y[-1]), 0.)

    def test_closed_complex_wet_dry_relaxation_preserves_nonnegative_directional_ledger(self):
        generator = np.random.default_rng(724)
        topology = build_overflow_topology(build_basin_hierarchy(make_td_source(
            generator.uniform(0., 3., (7, 7)), spacing_m=1.)))
        initial = generator.uniform(0., 20., topology["metadata"]["leaf_count"])
        event = simulate_radau_overflow(topology, np.zeros(12),
            parameters=OverflowParameters(timestep_s=300., duration_s=3600.), initial_volume_m3=initial)
        arrays = event["arrays"]
        self.assertTrue(np.all(arrays["volume_m3"] >= 0.))
        self.assertTrue(np.all(arrays["face_forward_m3"] >= 0.))
        self.assertTrue(np.all(arrays["face_reverse_m3"] >= 0.))
        self.assertLess(float(np.max(np.abs(arrays["basin_balance_residual_m3"]))), 1e-7)
        audit_saved_arrays(topology, event)
