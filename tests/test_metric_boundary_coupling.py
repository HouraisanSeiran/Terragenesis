import unittest

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.surface_rivers.metric_channel_state import ChannelConfig, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_lake_storage import LakeOutlet, LakeStorage
from terrain_pipeline.surface_rivers.metric_boundary_coupling import (
    BoundarySeries, CoupledForcing, solve_coupled,
)
from terrain_pipeline.surface_rivers.metric_coupled_product import make_coupled_product


def channel(kind="closed_wall", slope=0.):
    return ChannelNetwork(np.array([-1], np.int64), np.array([10.]), np.array([2.]),
                          np.array([0.]), np.array([slope]), np.array([.05]),
                          np.array([10.]), np.array([kind]), "a" * 64,
                          "rectangular-test", "manning-test")


def lake(max_stage=10.):
    return LakeStorage(np.array([0], np.int64), np.array([0.]), np.array([10.]),
                       0, max_stage, "b" * 64, "finite-one-cell-test")


def boundary(times=(0., 4.), *, kind=None, discharge=0., stage=0., conductance=0., allow=False):
    times = np.asarray(times, np.float64)
    if kind is None:
        return BoundarySeries(np.empty(0, np.int64), np.empty(0, dtype="U24"),
                              np.empty(0, bool), times, np.empty((times.size - 1, 0)),
                              np.empty((times.size - 1, 0)), np.empty(0), "c" * 64)
    return BoundarySeries(np.array([0], np.int64), np.array([kind]), np.array([allow]),
                          times, np.full((times.size - 1, 1), stage),
                          np.full((times.size - 1, 1), discharge),
                          np.array([conductance]), "c" * 64)


def forcing(times=(0., 4.), *, channel_q=0., lake_q=0., lakes=1):
    times = np.asarray(times, np.float64)
    return CoupledForcing(times, np.full((times.size - 1, 1), channel_q),
                          np.full((times.size - 1, lakes), lake_q), "d" * 64)


class CouplingTests(unittest.TestCase):
    def test_threshold_time_and_lake_ode_refinement(self):
        pool = lake()
        outlet = LakeOutlet(0, -1, .5, 1., "broad-crest-test")
        event = forcing(lake_q=2.)
        coarse = solve_coupled(channel(), (pool,), (outlet,), np.array([-1], np.int64),
                               event, boundary(), config=ChannelConfig(max_dt_seconds=.2))
        fine = solve_coupled(channel(), (pool,), (outlet,), np.array([-1], np.int64),
                             event, boundary(), config=ChannelConfig(max_dt_seconds=.02))
        def derivative(_, volume):
            stage = max(volume[0] / 10., 0.)
            return [2. - max(stage - .5, 0.) ** 1.5]
        reference = solve_ivp(derivative, (0., 4.), [0.], rtol=1e-11, atol=1e-12)
        expected = reference.y[0, -1]
        coarse_error = abs(coarse["arrays"]["lake_volume_m3"][-1, 0] - expected)
        fine_error = abs(fine["arrays"]["lake_volume_m3"][-1, 0] - expected)
        self.assertLess(fine_error, coarse_error)
        self.assertLess(fine_error / expected, .005)
        first_spill = np.flatnonzero(fine["arrays"]["lake_outlet_q_m3_s"][:, 0] > 0.)[0]
        self.assertAlmostEqual(fine["arrays"]["time_seconds"][first_spill], 2.5, delta=.02)

    def test_river_lake_river_transfer_is_counted_once(self):
        network = ChannelNetwork(np.array([-1, -1], np.int64), np.array([10., 10.]),
                                 np.array([2., 2.]), np.array([0., 0.]),
                                 np.array([.01, 0.]), np.array([.05, .05]),
                                 np.array([10., 10.]), np.array(["open_outflow", "closed_wall"]),
                                 "a" * 64, "rectangular-test", "manning-test")
        coupled = CoupledForcing(np.array([0., 2.]), np.zeros((1, 2)), np.zeros((1, 1)), "d" * 64)
        linked = np.array([0, -1], np.int64)
        result = solve_coupled(network, (lake(),), (LakeOutlet(0, 1, 0., 1., "spill-test"),),
                               linked, coupled, boundary((0., 2.)),
                               initial_channel_volume_m3=np.array([10., 0.]),
                               initial_lake_volume_m3=np.array([10.]),
                               config=ChannelConfig(max_dt_seconds=.05))
        arrays = result["arrays"]
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertGreater(arrays["lake_donor_q_m3_s"].sum(), 0.)
        self.assertGreater(arrays["channel_donor_q_m3_s"][:, 1].sum(), 0.)
        self.assertEqual(arrays["channel_boundary_volume_m3"].sum(), 0.)
        self.assertAlmostEqual(arrays["channel_volume_m3"][-1].sum()
                               + arrays["lake_volume_m3"][-1].sum(), 20., places=8)

    def test_unknown_retains_water_and_capacity_failure_keeps_prefix(self):
        unknown = solve_coupled(channel("unknown_boundary"), (), (), np.array([-1], np.int64),
                                forcing(lakes=0, channel_q=1.), boundary(),
                                config=ChannelConfig(max_dt_seconds=.5))
        self.assertAlmostEqual(unknown["arrays"]["channel_volume_m3"][-1, 0], 4.)
        self.assertEqual(unknown["arrays"]["channel_boundary_volume_m3"].sum(), 0.)
        limited = solve_coupled(channel(), (lake(max_stage=1.),), (), np.array([-1], np.int64),
                                forcing(lake_q=4.), boundary(),
                                config=ChannelConfig(max_dt_seconds=.5))
        self.assertEqual(limited["metadata"]["status"], "failed_prefix")
        self.assertEqual(limited["metadata"]["failure_reason"], "lake capacity exceeded")
        self.assertGreater(limited["arrays"]["time_seconds"].size, 1)
        self.assertLess(limited["metadata"]["last_time_seconds"], 4.)

    def test_boundary_only_targets_terminal_and_overflow_returns_prefix(self):
        internal = ChannelNetwork(np.array([1, -1], np.int64), np.array([10., 10.]),
                                  np.array([2., 2.]), np.array([0., 0.]),
                                  np.array([.01, 0.]), np.array([.05, .05]),
                                  np.array([10., 10.]), np.array(["interior", "closed_wall"]),
                                  "a" * 64, "rectangular-test", "manning-test")
        local = CoupledForcing(np.array([0., 4.]), np.zeros((1, 2)), np.empty((1, 0)), "d" * 64)
        with self.assertRaisesRegex(ValueError, "mapping"):
            solve_coupled(internal, (), (), np.array([-1, -1], np.int64), local,
                          boundary(kind="prescribed_discharge", discharge=1.))
        overflow = solve_coupled(channel(), (lake(),),
                                 (LakeOutlet(0, -1, 0., 1e308, "extreme-rating"),),
                                 np.array([-1], np.int64), forcing(), boundary(),
                                 initial_lake_volume_m3=np.array([50.]))
        self.assertEqual(overflow["metadata"]["status"], "failed_prefix")
        self.assertEqual(overflow["metadata"]["failure_reason"], "nonfinite hydraulic flux")
        self.assertEqual(overflow["arrays"]["time_seconds"].tolist(), [0.])

    def test_finite_cells_with_overflowing_global_storage_are_rejected(self):
        huge = ChannelNetwork(np.array([-1, -1], np.int64), np.ones(2), np.ones(2),
                              np.zeros(2), np.zeros(2), np.full(2, .05),
                              np.full(2, 1e308), np.array(["closed_wall", "closed_wall"]),
                              "a" * 64, "rectangular-test", "manning-test")
        local = CoupledForcing(np.array([0., 1.]), np.zeros((1, 2)), np.empty((1, 0)), "d" * 64)
        empty_boundary = boundary((0., 1.))
        with self.assertRaisesRegex(ValueError, "aggregate|total"):
            solve_coupled(huge, (), (), np.array([-1, -1], np.int64), local,
                          empty_boundary, initial_channel_volume_m3=np.full(2, 1e308))

    def test_stage_boundary_flux_overflow_is_a_zero_step_flux_failure(self):
        extreme = solve_coupled(channel("closed_wall"), (), (), np.array([-1], np.int64),
                                forcing(lakes=0), boundary(kind="prescribed_stage", stage=-2.,
                                                            conductance=1e308),
                                initial_channel_volume_m3=np.array([1.]))
        self.assertEqual(extreme["metadata"]["status"], "failed_prefix")
        self.assertEqual(extreme["metadata"]["failure_reason"], "nonfinite hydraulic flux")
        self.assertEqual(extreme["arrays"]["time_seconds"].tolist(), [0.])
        product = make_coupled_product(channel("closed_wall"), (), (), np.array([-1], np.int64),
                                       forcing(lakes=0), boundary(kind="prescribed_stage", stage=-2.,
                                                                   conductance=1e308), extreme)
        self.assertEqual(product["metadata"]["result"]["status"], "failed_prefix")

    def test_equilibrium_stage_boundary_still_limits_shared_step(self):
        event = CoupledForcing(np.array([0., 1.]), np.array([[1.]]), np.empty((1, 0)), "d" * 64)
        edge = BoundarySeries(np.array([0], np.int64), np.array(["prescribed_stage"]),
                              np.array([True]), np.array([0., 1.]), np.array([[.5]]),
                              np.array([[0.]]), np.array([100.]), "c" * 64)
        result = solve_coupled(channel("closed_wall"), (), (), np.array([-1], np.int64),
                               event, edge, initial_channel_volume_m3=np.array([10.]),
                               config=ChannelConfig(max_dt_seconds=1., cfl=.8))
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertLessEqual(result["arrays"]["time_seconds"][1], .16 + 1e-12)
        self.assertLessEqual(result["arrays"]["stability_number"].max(), .8 + 1e-12)

    def test_bowl_fills_linearly_to_crest_and_retains_without_outlet(self):
        result = solve_coupled(channel(), (lake(),), (), np.array([-1], np.int64),
                               forcing(lake_q=2.), boundary(), config=ChannelConfig(max_dt_seconds=.5))
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertAlmostEqual(result["arrays"]["lake_volume_m3"][-1, 0], 8.)
        self.assertAlmostEqual(result["arrays"]["lake_stage_m"][-1, 0], .8)
        self.assertAlmostEqual(result["arrays"]["lake_external_volume_m3"].sum(), 0.)
        self.assertLess(abs(result["arrays"]["lake_residual_m3"].sum()), 1e-12)

    def test_two_outlets_split_lake_volume_without_double_count(self):
        outlets = (LakeOutlet(0, -1, 0., 1., "test-one"),
                   LakeOutlet(0, -1, 0., 2., "test-two"))
        result = solve_coupled(channel(), (lake(),), outlets, np.array([-1], np.int64),
                               forcing(lake_q=0.), boundary(), initial_lake_volume_m3=np.array([10.]),
                               config=ChannelConfig(max_dt_seconds=.05))
        arrays = result["arrays"]
        self.assertEqual(result["metadata"]["status"], "complete")
        np.testing.assert_allclose(arrays["lake_outlet_q_m3_s"][:, 1],
                                   2. * arrays["lake_outlet_q_m3_s"][:, 0])
        self.assertAlmostEqual(10., arrays["lake_volume_m3"][-1, 0]
                               + arrays["lake_external_volume_m3"].sum(), places=8)

    def test_boundary_sign_and_permission(self):
        network = channel("open_outflow", slope=.01)
        dis = solve_coupled(network, (), (), np.array([-1], np.int64),
                            forcing(lakes=0), boundary(kind="prescribed_discharge", discharge=-1., allow=True),
                            config=ChannelConfig(max_dt_seconds=.25))
        self.assertEqual(dis["metadata"]["status"], "complete")
        self.assertAlmostEqual(dis["arrays"]["channel_volume_m3"][-1, 0], 4.)
        self.assertAlmostEqual(dis["arrays"]["channel_boundary_volume_m3"].sum(), -4.)
        with self.assertRaises(ValueError):
            boundary(kind="prescribed_discharge", discharge=-1., allow=False)
        stage = solve_coupled(network, (), (), np.array([-1], np.int64),
                              forcing(lakes=0), boundary(kind="prescribed_stage", stage=2., conductance=1., allow=False),
                              config=ChannelConfig(max_dt_seconds=.25))
        self.assertEqual(stage["arrays"]["boundary_q_m3_s"].sum(), 0.)
        dry = solve_coupled(channel("closed_wall"), (), (), np.array([-1], np.int64),
                            forcing(lakes=0), boundary(kind="prescribed_stage", stage=-1., conductance=1.),
                            config=ChannelConfig(max_dt_seconds=.25))
        self.assertEqual(dry["metadata"]["status"], "complete")
        self.assertEqual(dry["arrays"]["channel_volume_m3"].sum(), 0.)
        inbound = solve_coupled(channel("closed_wall"), (), (), np.array([-1], np.int64),
                                forcing(lakes=0), boundary(kind="prescribed_stage", stage=2.,
                                                            conductance=1., allow=True),
                                config=ChannelConfig(max_dt_seconds=.1))
        self.assertEqual(inbound["metadata"]["status"], "complete")
        self.assertLess(inbound["arrays"]["boundary_q_m3_s"][0, 0], 0.)
        self.assertGreater(inbound["arrays"]["channel_volume_m3"][-1, 0], 0.)


if __name__ == "__main__":
    unittest.main()
