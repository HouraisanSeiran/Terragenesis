import unittest

import numpy as np

from terrain_pipeline.surface_moment_hydraulics import (
    limit_realizable_moments, moments_from_profile, nine_moment_rhs,
)
from terrain_pipeline.surface_moment_execution import advance_nine_moments


class NineMomentTests(unittest.TestCase):
    def profiles(self, bed, stages):
        count = bed.shape[0]*bed.shape[1]
        eta = np.zeros((count, 3))
        eta[:, 0] = np.asarray(stages).ravel()
        velocity = np.zeros((count, 3, 2))
        flat_bed = bed.reshape(count, *bed.shape[2:])
        state = np.asarray([moments_from_profile(eta[cell], velocity[cell], flat_bed[cell]) for cell in range(count)])
        return state, eta, velocity

    def test_full_and_half_wet_lake_balances_every_moment(self):
        rng = np.random.default_rng(92)
        for factor in (1, 2):
            bed = rng.uniform(0., 1., (2, 3, factor, factor))
            for stage in (.4, 2.):
                state, eta, velocity = self.profiles(bed, np.full((2, 3), stage))
                rhs, _ = nine_moment_rhs(state, eta, velocity, bed, spacing=float(factor))
                np.testing.assert_allclose(rhs, 0., rtol=0., atol=2e-14)

    def test_flat_uniform_state_has_no_geometric_source_and_interior_fv_rhs_zero(self):
        bed = np.zeros((3, 4, 1, 1))
        state, eta, velocity = self.profiles(bed, np.full((3, 4), 2.))
        velocity[:, 0] = [1., .2]
        state = np.asarray([moments_from_profile(eta[cell], velocity[cell], bed.reshape(-1, 1, 1)[cell]) for cell in range(12)])
        rhs, witness = nine_moment_rhs(state, eta, velocity, bed, spacing=1.)
        np.testing.assert_allclose(witness["geometric_source"], 0., rtol=0., atol=0.)
        np.testing.assert_allclose(rhs.reshape(3, 4, 3, 3)[1, 1:3], 0., rtol=0., atol=2e-14)
        self.assertAlmostEqual(float(rhs[:, 0, 0].sum()), 0., places=13)

    def test_limiter_preserves_means_and_refuses_negative_water(self):
        bed = np.zeros((1, 1))
        target = moments_from_profile([1., 0., 0.], np.zeros((3, 2)), bed)
        target[0, 1] = .8
        target[1, 0] = .2
        limited, eta, velocity, factor = limit_realizable_moments(target, bed, [1., 0., 0.])
        self.assertLess(factor, 1.)
        np.testing.assert_array_equal(limited[:, 0], target[:, 0])
        np.testing.assert_allclose(moments_from_profile(eta, velocity, bed), limited, rtol=0., atol=1e-11)
        target[0, 0] = -1.
        with self.assertRaises(ValueError):
            limit_realizable_moments(target, bed, [1., 0., 0.])

    def test_dam_evolution_develops_independent_moments_conserves_water(self):
        bed = np.zeros((2, 6, 1, 1))
        stages = np.ones((2, 6))
        stages[:, :3] = 2.
        _, eta, velocity = self.profiles(bed, stages)
        result = advance_nine_moments(bed, eta, velocity, spacing=1., duration_s=.02, max_dt_s=.01)
        initial, final = result["arrays"]["initial_moments"], result["arrays"]["final_moments"]
        self.assertGreater(float(abs(final[:, 0, 1]-initial[:, 0, 1]).max()), .001)
        self.assertGreater(float(final[:, 1, 0].max()), .01)
        self.assertTrue(np.all(final[:, 0, 0] >= 0))
        self.assertLess(abs(result["metadata"]["volume_residual_m3"]), 1e-12)
        for packet in result["packets"]:
            np.testing.assert_array_equal(packet["predictor_moment_limiter_change"][:, :, 0], 0.)
            np.testing.assert_array_equal(packet["final_moment_limiter_change"][:, :, 0], 0.)

    def test_half_wet_static_lake_execution(self):
        bed = np.array([[[[0., .6], [.1, .7]], [[.2, .8], [.3, .9]]]])
        _, eta, velocity = self.profiles(bed, np.full((1, 2), .4))
        result = advance_nine_moments(bed, eta, velocity, spacing=2., duration_s=.01)
        np.testing.assert_allclose(result["arrays"]["final_moments"], result["arrays"]["initial_moments"], rtol=0., atol=1e-13)

    def test_dry_bed_front_evolves_positive_realizable_moments(self):
        bed = np.zeros((1, 6, 1, 1))
        stages = np.zeros((1, 6))
        stages[:, :3] = 1.
        _, eta, velocity = self.profiles(bed, stages)
        result = advance_nine_moments(bed, eta, velocity, spacing=1., duration_s=.02, max_dt_s=.01)
        final = result["arrays"]["final_moments"]
        self.assertGreater(final[3, 0, 0], 0.)
        self.assertTrue(np.all(final[:, 0, 0] >= 0))
        self.assertLess(abs(result["metadata"]["volume_residual_m3"]), 1e-12)
        self.assertGreater(result["metadata"]["limited_profile_count"], 0)
        for cell in range(len(final)):
            eta = result["arrays"]["final_stage_coefficients"][cell]
            velocity = result["arrays"]["final_velocity_coefficients"][cell]
            np.testing.assert_allclose(moments_from_profile(eta, velocity, np.zeros((1, 1))), final[cell], rtol=0., atol=1e-10)


if __name__ == "__main__":
    unittest.main()
