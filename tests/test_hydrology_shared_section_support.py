import unittest

import numpy as np

from terrain_pipeline.channel_geometry import solved_shared_section


class SharedSectionSupportTests(unittest.TestCase):
    def fixture(self):
        z, x = np.indices((21, 21))
        height = 101. - .001*x*10.
        # This low bank lies 40m upstream, outside the former 30m witness.
        height[11:13, 6] -= .8
        detail = {"metadata": {"identity": "a"*64, "origin_xz_m": [0.,0.], "spacing_m": 10.},
                  "arrays": {"derived_height_m": height}}
        times = np.linspace(0.,1.,61)
        specification = {"points_xz_m": [[40.,100.],[100.,100.],[160.,100.]],
            "receiver": [1,2,-1], "width_m": [8.]*3, "bed_target_m": [100.46,100.4,100.34],
            "centerline_profile": {"offsets": [0,61,122], "t": list(times)*2,
                "bed_m": np.r_[100.46-.06*times,100.4-.06*times].tolist()}}
        return detail, specification

    def test_shared_trace_obeys_upstream_floor_beyond_former_local_extent(self):
        detail, specification = self.fixture()
        section = solved_shared_section(detail, specification, 1, np.array([0.,1.]), complete_adjacent_pieces=True)
        # The actual zero-cut bank at (60,115) caps its projected center.
        # The 40m physical downstream gradient carries that cap to the seam.
        shore_height = (detail["arrays"]["derived_height_m"][11,6]
                        + detail["arrays"]["derived_height_m"][12,6])/2
        self.assertLessEqual(section["center_bed_m"], shore_height-40.*1e-5+1e-8)
        self.assertEqual(section["longitudinal_support_m"], [60.,60.])
        self.assertTrue(section["source_mesh_geometry_audit"]["accepted"])
        self.assertLessEqual(section["maximum_cut_m"], 4.+1e-8)
        np.testing.assert_allclose(np.asarray(section["bed_elevation_m"])[[0,-1]],
                                   np.asarray(section["source_elevation_m"])[[0,-1]], atol=1e-8)

    def test_neighbor_length_budget_is_preserved(self):
        detail, specification = self.fixture()
        specification["points_xz_m"][0] = [-501.,100.]
        with self.assertRaisesRegex(ValueError, "500m"):
            solved_shared_section(detail, specification, 1, np.array([0.,1.]), complete_adjacent_pieces=True)


if __name__ == "__main__":
    unittest.main()
