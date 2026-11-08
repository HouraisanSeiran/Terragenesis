import unittest

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import FanFloodplainConfig, build_alluvial_fan_candidate, build_floodplain_candidate


class FanFloodplainTests(unittest.TestCase):
    def terrain(self, unknown=False):
        height = np.tile(np.arange(10., 0., -1.), (10, 1))
        valid = np.ones_like(height, dtype=bool)
        if unknown:
            valid[4, 5] = False
        return TerrainGrid(height, valid, 0., 0., 1., 1., "generated_terrain", "fixture", "a" * 64)

    def test_fan_solid_conservation_with_unresolved_capacity(self):
        result = build_alluvial_fan_candidate(self.terrain(), (5., 1.), (0., 1.), 100., "b" * 64, "c" * 64,
                                              FanFloodplainConfig(max_fan_radius_m=4., max_deposit_depth_m=.1))
        ledger = result["material_ledger"]
        self.assertAlmostEqual(ledger["deposited_solid_m3"] + ledger["unresolved_solid_m3"], 100.)
        self.assertTrue(np.all(result["height_delta_m"][~result["deposit_mask"]] == 0.))
        self.assertFalse(result["capabilities"]["hydraulic"])

    def test_floodplain_stays_out_of_unknown(self):
        result = build_floodplain_candidate(self.terrain(True), ((2., 2.), (8., 2.)), 1., "b" * 64, "c" * 64)
        self.assertFalse(np.any(result["inundation_mask"] & ~self.terrain(True).valid_mask))
        self.assertEqual(result["event"].event_type, "floodplain_inundation")
        self.assertEqual(result["event"].water_transfer_m3, 0.)

    def test_invalid_inputs_and_event_identity(self):
        terrain = self.terrain()
        with self.assertRaises(ValueError):
            build_alluvial_fan_candidate(terrain, (5., 1.), (0., 0.), 1., "b" * 64, "c" * 64)
        with self.assertRaises(ValueError):
            build_floodplain_candidate(terrain, ((2., 2.), (2., 2.)), 1., "b" * 64, "c" * 64)
        first = build_alluvial_fan_candidate(terrain, (5., 1.), (0., 1.), 1., "b" * 64, "c" * 64)
        second = build_alluvial_fan_candidate(terrain, (5., 1.), (0., 1.), 1., "b" * 64, "c" * 64)
        self.assertEqual(first["event"].identity_sha256, second["event"].identity_sha256)
        self.assertEqual(first["event"].parent_graph_identity_sha256, "b" * 64)


if __name__ == "__main__":
    unittest.main()
