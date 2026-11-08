import unittest

import numpy as np

from terrain_pipeline.shallow_water import single_domain_shallow_water_support_mechanism_7_manning_damping as manning_damping
from terrain_pipeline.shallow_water import single_domain_shallow_water_mechanism_7_advance_shallow_water as advance_shallow_water
from terrain_pipeline.surface_hydraulics import SurfaceBudget
from tests import test_single_domain_shallow_water_v3 as v3_tests


class ShallowWaterV7Tests(unittest.TestCase):
    def test_flat_fully_wet_drag_reduces_to_standard_manning(self):
        subbed = np.zeros((3, 4))
        support = dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=np.cumsum(subbed, axis=1))
        state = np.array([[.2, .4, .3], [1., 2., 1.], [2., -1., 3.]])
        dt, gravity, roughness = .025, 9.81, .035
        damping, factor = manning_damping(state, dt, gravity, roughness, support=support)
        expected = 1/(1+dt*gravity*roughness**2*np.hypot(state[:, 1], state[:, 2])/state[:, 0]**(7/3))
        np.testing.assert_allclose(damping, expected, rtol=0., atol=2e-15)
        np.testing.assert_allclose(factor, state[:, 0]**(-1/3), rtol=0., atol=2e-15)

    def test_half_wet_drag_integral_includes_dry_zero_area(self):
        subbed = np.array([[0., 0., 2., 2.]])
        support = dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=np.cumsum(subbed, axis=1))
        state = np.array([[.5, 1., 0.]])
        damping, factor = manning_damping(state, .1, 9.81, .035, support=support)
        np.testing.assert_allclose(factor, [.5], rtol=0., atol=1e-15)
        np.testing.assert_allclose(damping, [.25/(.25+.1*9.81*.035**2*.5)], rtol=0., atol=1e-15)
        old_damping = 1/(1+.1*9.81*.035**2/.5**(7/3))
        self.assertGreater(damping[0], old_damping)

    def test_extremely_thin_and_dry_drag_is_finite(self):
        subbed = np.zeros((2, 1))
        support = dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=subbed.copy())
        state = np.array([[1e-300, 0., 0.], [0., 0., 0.]])
        damping, factor = manning_damping(state, .1, 9.81, .035, support=support)
        self.assertTrue(np.isfinite(damping).all())
        self.assertTrue(np.isfinite(factor).all())

    def test_saved_first_rk_friction_witness_is_bound_to_depth(self):
        geometry, support, _ = v3_tests.ShallowWaterV3Tests().geometry(np.zeros((8, 16)), 2)
        bed = geometry["arrays"]["H2_m"]
        depth = np.ones_like(bed)
        depth[:, :4] = 2.
        packets = []
        result = advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=.1, intervals=1,
            forcing_provider=lambda i: np.zeros_like(bed), boundary_stage_provider=lambda i: np.zeros(2*sum(bed.shape)),
            source_identity="synthetic", forcing_identity="dam-break", budget=SurfaceBudget(max_dt_s=.025, max_snapshots=3),
            snapshot_interval_s=.1, interval_observer=lambda packet: None, momentum_observer=packets.append)
        packet = packets[0]
        _, factor = manning_damping(packet["state_after"], packet["dt_s"], 9.81, .035, support=support)
        np.testing.assert_allclose(packet["manning_inverse_depth_third_mean"], factor, rtol=0., atol=1e-15)
        self.assertLess(abs(result["arrays"]["ledger"][-1, -1]), 1e-10)


if __name__ == "__main__":
    unittest.main()
