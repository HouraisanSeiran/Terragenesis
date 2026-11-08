import unittest

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_hydraulics import solve_channel


def network(receiver=(-1,), kind=("open_outflow",), slope=(.01,)):
    n = len(receiver)
    bed = np.zeros(n)
    for _ in range(n):
        for node, target in enumerate(receiver):
            if target >= 0:
                bed[node] = bed[target] + slope[node] * 10.
    return ChannelNetwork(
        receiver=np.array(receiver, np.int64),
        length_m=np.full(n, 10.), width_m=np.full(n, 2.),
        bed_elevation_m=bed, bed_slope=np.array(slope, np.float64),
        roughness=np.full(n, .05), max_depth_m=np.full(n, 3.),
        terminal_kind=np.array(kind), source_identity_sha256="a" * 64,
        section_source="test rectangular", roughness_source="test Manning",
    )


class ChannelSolverTests(unittest.TestCase):
    def test_inconsistent_physical_edges_reject_before_solve(self):
        from dataclasses import replace
        channel = network((1, -1), ("interior", "open_outflow"), (.1, .1))
        for bed, slope in (([0., 0.], [.1, .1]), ([0., 1.], [.1, .1]),
                           ([1., .999], [1., 1.]), ([1e-20, 0.], [1e-13, .1])):
            with self.subTest(bed=bed), self.assertRaisesRegex(ValueError, "downhill|inconsistent"):
                replace(channel, bed_elevation_m=np.array(bed), bed_slope=np.array(slope))
        with self.assertRaisesRegex(ValueError, "downhill"):
            replace(channel, receiver=np.array([-1, 0], np.int64),
                    terminal_kind=np.array(["open_outflow", "interior"]),
                    receiver_distance_m=np.array([0., 10.]))
        object.__setattr__(channel, "bed_slope", np.array([1., .1]))
        forcing = ChannelForcing(np.array([0., 1.]), np.zeros((1, 2)), "b" * 64)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            solve_channel(channel, forcing)

    def test_receiver_distance_is_independent_of_storage_length(self):
        from dataclasses import replace
        channel = network((1, -1), ("interior", "open_outflow"), (.1, .1))
        channel = replace(channel, length_m=np.array([5., 5.]),
                          receiver_distance_m=np.array([10., 0.]))
        forcing = ChannelForcing(np.array([0., .1]), np.zeros((1, 2)), "b" * 64)
        result = solve_channel(channel, forcing, np.array([5., 5.]))
        np.testing.assert_array_equal(result["arrays"]["area_m2"][0], [1., 1.])
        np.testing.assert_array_equal(channel.receiver_distance_m, [10., 0.])
        with self.assertRaisesRegex(ValueError, "zero at terminals"):
            replace(channel, receiver_distance_m=np.array([10., 10.]))

    def test_single_channel_initial_manning_flux_and_continuity(self):
        channel = network()
        forcing = ChannelForcing(np.array([0., .1]), np.zeros((1, 1)), "b" * 64)
        result = solve_channel(channel, forcing, initial_volume_m3=np.array([10.]),
                               config=ChannelConfig(max_dt_seconds=.1))
        arrays = result["arrays"]
        expected_q = 0.9614997135382722  # A=1 m2, wetted perimeter=3 m.
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertAlmostEqual(arrays["outflow_end_q_m3_s"][0, 0], expected_q)
        self.assertAlmostEqual(arrays["volume_m3"][-1, 0],
                               10. - np.sum(arrays["boundary_outflow_volume_m3"]), places=12)
        np.testing.assert_allclose(arrays["balance_residual_m3"], 0., atol=1e-12)

    def test_dry_pulse_reaches_downstream_after_storage_delay(self):
        channel = network(receiver=(1, -1), kind=("interior", "open_outflow"),
                          slope=(.01, .01))
        forcing = ChannelForcing(np.array([0., 1., 2., 3.]),
                                 np.array([[1., 0.], [0., 0.], [0., 0.]]), "b" * 64)
        arrays = solve_channel(channel, forcing, config=ChannelConfig(max_dt_seconds=1.))["arrays"]
        self.assertEqual(arrays["volume_m3"][1, 1], 0.)
        self.assertEqual(arrays["outflow_q_m3_s"][0, 0], 0.)
        self.assertGreater(arrays["volume_m3"][-1, 1], 0.)
        self.assertEqual(arrays["boundary_outflow_volume_m3"][0, 1], 0.)

    def test_single_volume_converges_to_independent_ode(self):
        channel = network()
        forcing = ChannelForcing(np.array([0., 5.]), np.zeros((1, 1)), "b" * 64)

        def ode(_, state):
            area = state[0] / 10.
            depth = area / 2.
            return [-area * (area / (2. + 2. * depth)) ** (2. / 3.) * .1 / .05]

        reference = solve_ivp(ode, (0., 5.), [10.], rtol=1e-12, atol=1e-12).y[0, -1]
        coarse = solve_channel(channel, forcing, np.array([10.]),
                               ChannelConfig(max_dt_seconds=.5))["arrays"]["volume_m3"][-1, 0]
        fine = solve_channel(channel, forcing, np.array([10.]),
                             ChannelConfig(max_dt_seconds=.02))["arrays"]["volume_m3"][-1, 0]
        self.assertLess(abs(fine - reference) / reference, .005)
        self.assertLess(abs(fine - reference), abs(coarse - reference))

    def test_y_junction_conserves_water_and_respects_cfl(self):
        channel = network(receiver=(2, 2, -1),
                          kind=("interior", "interior", "open_outflow"),
                          slope=(.01, .01, .01))
        forcing = ChannelForcing(np.array([0., 1., 2.]),
                                 np.array([[1., 2., 0.], [0., 0., 0.]]), "b" * 64)
        result = solve_channel(channel, forcing,
                               config=ChannelConfig(max_dt_seconds=.3, cfl=.4))
        arrays = result["arrays"]
        input_volume = np.sum(np.diff(arrays["time_seconds"])[:, None]
                              * arrays["local_q_m3_s"])
        self.assertAlmostEqual(input_volume, 3.)
        self.assertAlmostEqual(np.sum(arrays["volume_m3"][-1])
                               + np.sum(arrays["boundary_outflow_volume_m3"]), 3., places=12)
        self.assertLessEqual(np.max(arrays["cfl_number"]), .4 + 1e-12)
        np.testing.assert_allclose(arrays["inflow_q_m3_s"][:, 2],
                                   arrays["outflow_q_m3_s"][:, 0]
                                   + arrays["outflow_q_m3_s"][:, 1])

    def test_depth_failure_returns_only_committed_prefix(self):
        channel = network(kind=("closed_wall",), slope=(0.,))
        forcing = ChannelForcing(np.array([0., 1., 2.]),
                                 np.array([[0.], [2.]]), "b" * 64)
        result = solve_channel(channel, forcing, initial_volume_m3=np.array([59.]),
                               config=ChannelConfig(max_dt_seconds=1.))
        arrays = result["arrays"]
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertIn("depth", result["metadata"]["failure_reason"])
        self.assertEqual(result["metadata"]["last_time_seconds"], 1.)
        np.testing.assert_array_equal(arrays["time_seconds"], [0., 1.])
        np.testing.assert_array_equal(arrays["volume_m3"][:, 0], [59., 59.])
        self.assertEqual(arrays["local_q_m3_s"].shape, (1, 1))

    def test_closed_and_unknown_terminals_retain_all_input(self):
        channel = network(receiver=(-1, -1),
                          kind=("closed_wall", "unknown_boundary"), slope=(0., 0.))
        forcing = ChannelForcing(np.array([0., 1., 2.]),
                                 np.array([[1., 2.], [0., 0.]]), "b" * 64)
        arrays = solve_channel(channel, forcing)["arrays"]
        np.testing.assert_array_equal(arrays["volume_m3"][-1], [1., 2.])
        np.testing.assert_array_equal(arrays["outflow_end_q_m3_s"], 0.)
        np.testing.assert_array_equal(arrays["boundary_outflow_volume_m3"], 0.)

    def test_inputs_are_copied_and_zero_step_limit_is_a_prefix(self):
        channel = network()
        q = np.array([[1.]])
        forcing = ChannelForcing(np.array([0., 2.]), q, "b" * 64)
        q[0, 0] = 100.
        with self.assertRaises(ValueError):
            channel.width_m[0] = 7.
        with self.assertRaises(ValueError):
            forcing.local_q_m3_s[0, 0] = 100.
        self.assertEqual(forcing.local_q_m3_s[0, 0], 1.)
        result = solve_channel(channel, forcing,
                               config=ChannelConfig(max_dt_seconds=.5, max_steps=1))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertEqual(result["metadata"]["last_time_seconds"], .5)
        self.assertEqual(result["arrays"]["volume_m3"].shape, (2, 1))
        self.assertEqual(result["arrays"]["inflow_q_m3_s"].shape, (1, 1))

    def test_invalid_topology_and_initial_depth_reject_before_solve(self):
        with self.assertRaisesRegex(ValueError, "acyclic"):
            network(receiver=(1, 0), kind=("interior", "interior"), slope=(.01, .01))
        channel = network()
        forcing = ChannelForcing(np.array([0., 1.]), np.zeros((1, 1)), "b" * 64)
        with self.assertRaisesRegex(ValueError, "initial volume"):
            solve_channel(channel, forcing, np.array([61.]))

    def test_wave_speed_limits_internal_step_and_zero_step_failure_is_valid(self):
        channel = network()
        forcing = ChannelForcing(np.array([0., 10.]), np.zeros((1, 1)), "b" * 64)
        result = solve_channel(channel, forcing, np.array([10.]),
                               ChannelConfig(max_dt_seconds=10., cfl=.1))
        arrays = result["arrays"]
        self.assertGreater(len(arrays["cfl_number"]), 1)
        self.assertAlmostEqual(arrays["cfl_number"][0], .1, places=12)
        self.assertLessEqual(np.max(arrays["cfl_number"]), .1 + 1e-12)

        closed = network(kind=("closed_wall",), slope=(0.,))
        full = ChannelForcing(np.array([0., 1.]), np.array([[2.]]), "b" * 64)
        prefix = solve_channel(closed, full, np.array([59.]),
                               ChannelConfig(max_dt_seconds=1.))
        self.assertEqual(prefix["metadata"]["status"], "failed_prefix")
        self.assertEqual(prefix["metadata"]["last_time_seconds"], 0.)
        self.assertEqual(prefix["arrays"]["volume_m3"].shape, (1, 1))
        self.assertEqual(prefix["arrays"]["local_q_m3_s"].shape, (0, 1))


if __name__ == "__main__":
    unittest.main()
