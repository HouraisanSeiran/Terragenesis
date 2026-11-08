import unittest
import numpy as np
from scipy.integrate import solve_ivp
import terrain_pipeline.basin_storage as transport


class SimultaneousTransportTests(unittest.TestCase):
    def exchange(self, depth, bed, faces, dt, spacing=1., boundary=None, widths=None):
        boundary = np.array([], dtype=np.int64) if boundary is None else boundary
        widths = np.array([]) if widths is None else widths
        transport.validate_cfl(faces, boundary, widths, spacing, dt, .6, len(depth))
        return transport._compiled_exchange(depth, bed, faces, boundary, widths, spacing, dt, .6,
                                            np.array([], dtype=np.int64), np.array([], dtype=np.int64))

    def test_high_bed_regression_and_ode_refinement(self):
        faces = np.array([[0, 1]], dtype=np.int64)
        errors = []
        for dt in (.2, .1, .05):
            depth = np.array([1., 0.])
            for step in range(round(1 / dt)):
                depth = self.exchange(depth, np.array([2., 0.]), faces, dt)[0]
            errors.append(abs(depth[0] - np.exp(-.6)))
            self.assertAlmostEqual(depth.sum(), 1., places=14)
        self.assertGreater(errors[0] / errors[1], 3.8)
        self.assertGreater(errors[1] / errors[2], 3.8)

    def test_multiface_sill_front_ode_mass_divergence_activity(self):
        bed = np.array([2., 0., 1., 2., .5, 0.])
        initial = np.array([1., .2, .1, .1, 0., .3])
        faces = np.array([[0, 1], [1, 2], [3, 4], [4, 5], [0, 3], [1, 4], [2, 5]])
        boundary = np.array([5], dtype=np.int64)
        widths = np.array([1.])
        reference = solve_ivp(lambda time, depth: transport._stage(depth, bed, faces, boundary, widths, 1., .6)[0],
                              (0, 2), initial, method="DOP853", rtol=1e-12, atol=1e-13).y[:, -1]
        errors = []
        for dt in (.1, .05, .025):
            depth = initial.copy()
            net = np.zeros(len(faces))
            export = 0.
            for step in range(round(2 / dt)):
                depth, forward, reverse, exported, active_forward, active_reverse = self.exchange(depth, bed, faces, dt, boundary=boundary, widths=widths)
                self.assertTrue(np.all(depth >= 0))
                self.assertTrue(np.all(active_forward + active_reverse <= dt))
                net += forward - reverse
                export += exported.sum()
            divergence = np.bincount(faces[:, 1], weights=net, minlength=6) - np.bincount(faces[:, 0], weights=net, minlength=6)
            divergence[5] -= export
            np.testing.assert_allclose(depth - initial, divergence, atol=1e-14)
            self.assertAlmostEqual(depth.sum() + export, initial.sum(), places=13)
            errors.append(abs(depth-reference).max())
        self.assertGreater(errors[0] / errors[1], 3.5)
        self.assertGreater(errors[1] / errors[2], 3.5)

    def test_cfl_rejects_before_stage(self):
        faces = np.array([[0, 1], [0, 2], [0, 3], [0, 4]])
        with self.assertRaisesRegex(ValueError, "CFL"):
            self.exchange(np.ones(5), np.zeros(5), faces, .5)

    def test_direction_reversal_quadrature(self):
        result = self.exchange(np.array([1., 0.]), np.zeros(2), np.array([[0, 1]]), 1.)
        self.assertGreater(result[1][0], 0)
        self.assertGreater(result[2][0], 0)
        self.assertEqual(result[4][0], .5)
        self.assertEqual(result[5][0], .5)


if __name__ == "__main__":
    unittest.main()
