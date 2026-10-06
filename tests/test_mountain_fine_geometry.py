"""Real TD bilinear transverse profiles and continuous shared fine sections."""

import unittest

import numpy as np

from terrain_pipeline import mountain_depression_geometry as geometry
from terrain_pipeline import mountain_fine_geometry as fine
from tools.verify_mountain_rainfall import load_source


class MountainFineGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_source("normal_mountain")
        cls.geometry = geometry.prepare_mountain_geometry(source["height_m"], spacing_m=30.,
            origin_m_xz=source["origin_m_xz"], source_binding={"mountain": "normal_mountain"},
            boundary_mask=geometry.window_boundary(source["height_m"].shape),
            protected_mask=np.zeros(source["height_m"].shape, dtype=bool))

    def test_real_continuous_chain_shared_sections_and_positive_cut(self):
        evidence = fine.select_continuous_fine_geometry(self.geometry)
        accepted = evidence["accepted"]
        self.assertIsNotNone(accepted)
        self.assertGreaterEqual(accepted["segments"], 3)
        arrays = accepted["arrays"]
        self.assertEqual(accepted["length_m"], accepted["segments"] * 30.)
        self.assertTrue((np.diff(arrays["H2_m"][:, 5]) <= 1e-9).all())
        self.assertTrue((arrays["H2_m"] >= arrays["H2_m"][:, 5:6] - 1e-9).all())
        self.assertLessEqual(arrays["cut_depth_m"].max(), 2.)
        self.assertAlmostEqual(accepted["cut_volume_m3"], (arrays["cut_depth_m"] * arrays["quadrature_area_m2"]).sum())
        self.assertEqual(arrays["shared_node_section_rows"].size, accepted["segments"] - 1)
        self.assertGreater(np.ptp(arrays["H0_m"][0]), 0.)
        self.assertIn("alternative", accepted["scope"])

    def test_fine_resolution_and_width_are_fixed(self):
        evidence = fine.select_continuous_fine_geometry(self.geometry)
        donor = int(evidence["accepted"]["arrays"]["chain_cells"][0])
        with self.assertRaises(ValueError):
            fine.prepare_fine_segment(self.geometry, donor, width_m=20.)
        with self.assertRaises(ValueError):
            fine.prepare_fine_segment(self.geometry, donor, fine_spacing_m=.5)

    def test_bilinear_source_is_not_repeated_center_column(self):
        height = np.array([[0., 2.], [4., 6.]])
        sampled = fine._sample(height, np.array([0., .5, 1.]), np.array([.5, .5, .5]))
        np.testing.assert_array_equal(sampled, [2., 3., 4.])


if __name__ == "__main__":
    unittest.main()
