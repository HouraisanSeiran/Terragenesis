"""Small analytic checks; no terrain run or saved hydraulic package."""

import unittest

import numpy as np

from terrain_pipeline.surface_moment_storage import profile_moments, invert_water_moments, invert_velocity_moments


class SurfaceMomentTests(unittest.TestCase):
    def test_dry_and_rotated_half_wet_analytic_integrals(self):
        moments, jacobian, gram = profile_moments([-1., .1, .1], np.zeros((1, 1)))
        np.testing.assert_array_equal(moments, 0.)
        np.testing.assert_array_equal(jacobian, 0.)
        np.testing.assert_array_equal(gram, 0.)
        moments, _, gram = profile_moments([0., 1., 1.], np.zeros((1, 1)))
        np.testing.assert_allclose(moments, [1/6, 1/24, 1/24], rtol=0., atol=1e-15)
        np.testing.assert_allclose(gram[:, 0], moments, rtol=0., atol=1e-15)
        side = .05
        moments, jacobian, gram = profile_moments([-.95, 1., 1.], np.zeros((1, 1)))
        np.testing.assert_allclose(moments[0], side**3/6, rtol=0., atol=1e-17)
        self.assertTrue(np.all(np.linalg.eigvalsh(jacobian) > 0))
        self.assertTrue(np.all(np.linalg.eigvalsh(gram) > 0))

    def test_jacobian_matches_independent_finite_difference(self):
        bed = np.array([[0., .4], [.2, .8]])
        coefficients = np.array([.3, .6, -.25])
        _, jacobian, _ = profile_moments(coefficients, bed)
        epsilon = 1e-6
        for column in range(3):
            offset = np.zeros(3)
            offset[column] = epsilon
            high, _, _ = profile_moments(coefficients+offset, bed)
            low, _, _ = profile_moments(coefficients-offset, bed)
            np.testing.assert_allclose((high-low)/(2*epsilon), jacobian[:, column], rtol=0., atol=1e-9)

    def test_independent_audit_volume_momentum_integral(self):
        from tools.single_domain_linear_storage_audit import continuous_profile_moments
        rng = np.random.default_rng(58)
        for factor in (1, 2, 4):
            bed = rng.uniform(0., 1., (factor, factor))
            coefficients = np.array([.4, .6, -.2])
            moments, _, gram = profile_moments(coefficients, bed)
            velocity = np.array([[.4, -.2], [.1, .3], [-.15, .05]])
            center = np.column_stack(([coefficients[0]], velocity[0][None]))
            sx = np.column_stack(([coefficients[1]], velocity[1][None]))
            sz = np.column_stack(([coefficients[2]], velocity[2][None]))
            volume, momentum = continuous_profile_moments(center, sx, sz, bed[None])
            np.testing.assert_allclose(moments[0], volume[0], rtol=0., atol=1e-15)
            np.testing.assert_allclose((gram@velocity)[0], momentum[0], rtol=0., atol=1e-15)

    def test_flat_full_wet_analytic_moments(self):
        moments, jacobian, gram = profile_moments([2., .4, -.2], np.zeros((1, 1)))
        np.testing.assert_allclose(moments, [2., .4/12, -.2/12], rtol=0., atol=1e-15)
        np.testing.assert_allclose(jacobian, np.diag([1., 1/12, 1/12]), rtol=0., atol=1e-15)
        np.testing.assert_allclose(gram[:, 0], moments, rtol=0., atol=1e-15)

    def test_sliver_has_no_wet_midpoint_but_full_rank(self):
        coefficients = np.array([-.45, 1., 0.])
        moments, jacobian, gram = profile_moments(coefficients, np.zeros((1, 1)))
        self.assertLess(coefficients[0], 0.)
        np.testing.assert_allclose(moments[0], .05**2/2, rtol=0., atol=1e-17)
        self.assertTrue(np.all(np.linalg.eigvalsh(jacobian) > 0))
        self.assertTrue(np.all(np.linalg.eigvalsh(gram) > 0))
        recovered, witness = invert_water_moments(moments, np.zeros((1, 1)), initial_coefficients=[-.44, 1., .01])
        np.testing.assert_allclose(recovered, coefficients, rtol=0., atol=2e-9)
        self.assertLess(witness["relative_residual"], 1e-12)

    def test_piecewise_bed_water_and_velocity_inverse(self):
        bed = np.array([[0., .4], [.2, .8]])
        coefficients = np.array([.3, .6, -.25])
        moments, _, gram = profile_moments(coefficients, bed)
        recovered, _ = invert_water_moments(moments, bed, initial_coefficients=[.5, .2, 0.])
        np.testing.assert_allclose(recovered, coefficients, rtol=0., atol=1e-10)
        velocity = np.array([[.4, -.2], [.1, .3], [-.15, .05]])
        momentum_moments = gram@velocity
        np.testing.assert_allclose(invert_velocity_moments(momentum_moments, gram), velocity, rtol=0., atol=1e-12)

    def test_unrealizable_target_refused(self):
        with self.assertRaises(ValueError):
            invert_water_moments([1., .6, 0.], np.zeros((1, 1)), initial_coefficients=[1., 0., 0.])

    def test_rotated_sliver_inverse_recovers_independent_water_moments(self):
        coefficients = np.array([-.95, 1., 1.])
        bed = np.zeros((1, 1))
        moments, _, _ = profile_moments(coefficients, bed)
        recovered, witness = invert_water_moments(moments, bed, initial_coefficients=[-.9, 1., 1.])
        np.testing.assert_allclose(recovered, coefficients, rtol=0., atol=1e-8)
        self.assertLess(witness["relative_residual"], 1e-12)

    def test_invalid_nonfinite_inputs_refused(self):
        with self.assertRaises(ValueError):
            profile_moments([np.nan, 0., 0.], np.zeros((1, 1)))
        with self.assertRaises(ValueError):
            profile_moments([1., 0., 0.], np.zeros((1, 2)))
        with self.assertRaises(ValueError):
            invert_velocity_moments([np.nan, 0., 0.], np.eye(3))


if __name__ == "__main__":
    unittest.main()

