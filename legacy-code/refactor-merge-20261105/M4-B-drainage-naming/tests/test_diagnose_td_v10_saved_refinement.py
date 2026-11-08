import unittest

import numpy as np

from tools.diagnose_td_v10_saved_refinement import attribute


class AttributionTests(unittest.TestCase):
    def fixture(self):
        source = dict(height_m=np.zeros((1, 2)), valid_mask=np.ones((1, 2), bool),
                      face_cells=np.array([[0, 1]], np.int64), receiver=np.array([1, -1]),
                      rain_mm_h=np.zeros((1, 2)), depth_m=np.array([[1., 1.], [1., 1.]]),
                      face_forward_m3=np.array([0.]), face_reverse_m3=np.array([0.]),
                      soil_mm=np.zeros((2, 2)))
        for name in ("local_release_m3", "surface_infiltration_m3", "surface_et_m3", "internal_net_m3",
                     "boundary_outflow_m3", "rain_infiltration_m3"):
            source[name] = np.zeros((1, 2))
        return source

    def test_incident_exchange_localizes_difference(self):
        first, second = self.fixture(), self.fixture()
        first["depth_m"][-1] += [-.002, .002]
        first["internal_net_m3"][0] = [-1.8, 1.8]
        first["face_forward_m3"][0] = 1.8
        result = attribute(first, second, spacing_m=30., hour=5, top_cells=2)
        self.assertFalse(result["numerical_depth_gate_passed"])
        self.assertAlmostEqual(result["max_saved_depth_difference_mm"], 2.)
        self.assertAlmostEqual(result["hotspot_rows"][0]["signed_account_contributions_mm"]["internal_net_m3"], 2.)
        self.assertAlmostEqual(result["hotspot_rows"][0]["incident_faces"][0]["signed_contribution_mm"], 2.)

    def test_inherited_error_without_new_flux(self):
        first, second = self.fixture(), self.fixture()
        first["depth_m"][:, 0] += .0012
        result = attribute(first, second, spacing_m=30., hour=6, top_cells=1)
        self.assertAlmostEqual(result["hotspot_rows"][0]["inherited_signed_difference_mm"], 1.2)
        self.assertAlmostEqual(result["maximum_account_explanation_residual_mm"], 0.)

    def test_unexplained_difference_and_rain_change_rejected(self):
        first, second = self.fixture(), self.fixture()
        first["depth_m"][-1, 0] += .001
        with self.assertRaisesRegex(ValueError, "attribution"):
            attribute(first, second, spacing_m=30., hour=1)
        first = self.fixture()
        first["rain_mm_h"][0, 0] = 1.
        with self.assertRaises(AssertionError):
            attribute(first, second, spacing_m=30., hour=1)


if __name__ == "__main__":
    unittest.main()
