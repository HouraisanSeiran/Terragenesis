import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_delta import DeltaConfig, build_delta_candidate


class DeltaCandidateTests(unittest.TestCase):
    def setUp(self):
        height = np.zeros((5, 7), dtype=np.float64)
        self.terrain = TerrainGrid(height, np.ones_like(height, dtype=bool), 0., 0., 2., 3.,
                                   "diagnostic_dem_proxy", "fixture", "a" * 64)
        self.land = np.zeros((5, 7), dtype=bool)
        self.land[:, :2] = True
        self.water = np.zeros((5, 7), dtype=bool)
        self.water[:, 2:6] = True
        self.water[0, 6] = True
        self.path = ((2, 0), (2, 1), (2, 2))

    def build(self, amount=100.):
        return build_delta_candidate(self.terrain, self.land, self.water, self.path, amount,
                                     "b" * 64, "c" * 64, DeltaConfig(max_radius_cells=3, max_deposit_depth_m=.2,
                                                                        porosity=.25, seed=7,
                                                                        max_distributary_candidates=3))

    def test_conservation_capacity_and_masks(self):
        result = self.build()
        ledger = result["material_ledger"]
        self.assertAlmostEqual(ledger["deposited_solid_m3"] + ledger["unresolved_solid_m3"], 100.)
        self.assertGreater(ledger["unresolved_solid_m3"], 0.)
        self.assertTrue(np.all(result["height_delta_m"][self.land] == 0.))
        self.assertFalse(result["deposit_mask"][0, 6])
        self.assertTrue(np.all(result["height_delta_m"][~result["water_component_mask"]] == 0.))

    def test_deterministic_and_event_identity(self):
        first = self.build(3.)
        second = self.build(3.)
        np.testing.assert_array_equal(first["height_delta_m"], second["height_delta_m"])
        self.assertEqual(first["event"].identity_sha256, second["event"].identity_sha256)
        self.assertEqual(first["event"].event_type, "delta_growth")
        self.assertEqual(first["event"].retired_edges, ())
        self.assertEqual(first["event"].parameters["candidate_count"], 3)

    def test_invalid_input_and_connected_water_gate(self):
        with self.assertRaises(ValueError):
            build_delta_candidate(self.terrain, self.land, self.land, self.path, 1., "b" * 64, "c" * 64)
        with self.assertRaises(ValueError):
            build_delta_candidate(self.terrain, self.land, self.water, ((2, 0), (0, 2)), 1., "b" * 64, "c" * 64)
        with self.assertRaises(ValueError):
            build_delta_candidate(self.terrain, self.land, self.water, ((2, 0), (2, 1)), 1., "b" * 64, "c" * 64)
        with self.assertRaises(ValueError):
            build_delta_candidate(self.terrain, self.land, self.water, self.path, -1., "b" * 64, "c" * 64)


if __name__ == "__main__":
    unittest.main()
