import unittest
from dataclasses import replace

import numpy as np

from terrain_pipeline.channel_geometry import DischargeGeometryConfig, build_discharge_geometry, channel_section_cut


class DischargeGeometryTests(unittest.TestCase):
    def fixture(self):
        source = np.full((9, 9), 100.)
        channel = np.zeros(source.shape, bool)
        channel[4, :] = True
        monthly = np.ones((12, *source.shape))
        return source, monthly, channel

    def test_confluence_discharge_increases_both_dimensions(self):
        source, monthly, channel = self.fixture()
        monthly[:, 4, 4:] = 3.
        original = source.copy()
        arrays = build_discharge_geometry(source, monthly, channel, 1.)["arrays"]
        self.assertGreater(arrays["channel_width_m"][4, 4], arrays["channel_width_m"][4, 3])
        self.assertGreater(arrays["channel_depth_m"][4, 4], arrays["channel_depth_m"][4, 3])
        np.testing.assert_array_equal(source, original)

    def test_hard_bed_soft_bank_widens_soft_bed_incises(self):
        source, monthly, channel = self.fixture()
        hard = build_discharge_geometry(source, monthly, channel, 1., bed_hardness=1., bank_hardness=0.)["arrays"]
        soft = build_discharge_geometry(source, monthly, channel, 1., bed_hardness=0., bank_hardness=0.)["arrays"]
        self.assertGreater(hard["channel_width_m"][4, 4], soft["channel_width_m"][4, 4])
        self.assertLess(hard["channel_depth_m"][4, 4], soft["channel_depth_m"][4, 4])
        bank = build_discharge_geometry(source, monthly, channel, 1., bed_hardness=1., bank_hardness=1.)["arrays"]
        self.assertLess(bank["channel_width_m"][4, 4], hard["channel_width_m"][4, 4])
        self.assertGreater(bank["channel_depth_m"][4, 4], hard["channel_depth_m"][4, 4])

    def test_profile_and_actual_raster_excavation_budget(self):
        np.testing.assert_allclose(channel_section_cut([-5., -3., 0., 3., 4., 5.], 10., 2.), [0., 2., 2., 2., 1., 0.])
        source, monthly, channel = self.fixture()
        protected = np.zeros(source.shape, bool)
        protected[:, 0] = True
        result = build_discharge_geometry(source, monthly, channel, 1., protected_mask=protected)
        cut = result["arrays"]["cut_depth_m"]
        self.assertTrue((cut[:, 0] == 0.).all())
        unprotected = build_discharge_geometry(source, monthly, channel, 1.)["arrays"]
        for key in ("channel_width_m", "bottom_width_m", "channel_depth_m"):
            np.testing.assert_array_equal(result["arrays"][key], unprotected[key])
            self.assertGreater(result["arrays"][key][4, 0], 0.)
        entirely_protected = build_discharge_geometry(
            source, monthly, channel, 1., protected_mask=np.ones(source.shape, bool))["arrays"]
        self.assertFalse(entirely_protected["cut_depth_m"].any())
        np.testing.assert_array_equal(entirely_protected["channel_width_m"], unprotected["channel_width_m"])
        np.testing.assert_allclose(result["arrays"]["bed_elevation_m"], source - cut)
        ledger = result["metadata"]["material_budget"]
        self.assertAlmostEqual(ledger["removed_terrain_bulk_m3"], cut.sum())
        self.assertEqual(ledger["unplaced_excavated_bulk_m3"], ledger["removed_terrain_bulk_m3"])

    def test_zero_flow_exposure_and_four_metre_cap(self):
        source, monthly, channel = self.fixture()
        for q, exposure in ((0., 3.), (1., 0.)):
            monthly[:] = q
            arrays = build_discharge_geometry(source, monthly, channel, 1., config=replace(DischargeGeometryConfig(), generation_exposure=exposure))["arrays"]
            self.assertFalse(arrays["cut_depth_m"].any())
            self.assertFalse(arrays["channel_width_m"].any())
        monthly[:] = 1e6
        arrays = build_discharge_geometry(source, monthly, channel, 1.)["arrays"]
        self.assertLessEqual(arrays["cut_depth_m"].max(), 4.)
        with self.assertRaises(ValueError):
            DischargeGeometryConfig(max_incise_m=4.1)

    def test_duration_mean_determinism_and_input_rejection(self):
        source, monthly, channel = self.fixture()
        monthly[0] = 2.
        a = build_discharge_geometry(source, monthly, channel, 1.)
        b = build_discharge_geometry(source, monthly, channel, 1.)
        self.assertGreater(a["arrays"]["representative_q_m3_s"][0, 0], 1.)
        for key in a["arrays"]:
            np.testing.assert_array_equal(a["arrays"][key], b["arrays"][key])
        saved_mean = a["arrays"]["representative_q_m3_s"]
        direct = build_discharge_geometry(source, saved_mean, channel, 1.)
        for key in a["arrays"]:
            np.testing.assert_array_equal(a["arrays"][key], direct["arrays"][key])
        with self.assertRaises(ValueError):
            build_discharge_geometry(source, monthly[:1], channel, 1.)
        with self.assertRaises(ValueError):
            build_discharge_geometry(source, monthly, channel, 1., bed_hardness=1.1)
        monthly[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            build_discharge_geometry(source, monthly, channel, 1.)


if __name__ == "__main__":
    unittest.main()
