import unittest

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from tools.prepare_td_delta_sediment_candidate import _terminal_inlet


class PrepareDeltaInletTests(unittest.TestCase):
    def test_actual_southward_donor_and_deterministic_multiple_donor_selection(self):
        terrain = TerrainGrid(np.zeros((7, 8)), np.ones((7, 8), bool), 900., -300., 30., 30.,
                              "diagnostic_dem_proxy", "fixture", "a" * 64, generation_seed=20261020)
        # Both candidate donors are real edges; the smaller source cell id wins.
        geometry = {"arrays": {"receiver": np.array([2, 2, -1], np.int64),
                               "source_node_cell_ids": np.array([35, 11, 43], np.int64),
                               "node_xz_m": np.array([[990., -180.], [990., -270.], [990., -150.]])}}
        land, water, path, evidence = _terminal_inlet(geometry, terrain, 2)
        self.assertEqual(path, ((1, 3), (5, 3)))
        self.assertEqual(evidence["upstream_node"], 1)
        self.assertTrue(land[path[0]])
        self.assertTrue(water[path[1]])
        self.assertTrue(land[2].all())
        self.assertTrue(water[4].all())
        np.testing.assert_allclose(evidence["imposed_downstream_unit_direction_xz"], [0., 1.])

    def test_terminal_without_real_donor_rejected(self):
        terrain = TerrainGrid(np.zeros((2, 2)), np.ones((2, 2), bool), 0., 0., 30., 30.,
                              "diagnostic_dem_proxy", "fixture", "a" * 64)
        with self.assertRaisesRegex(ValueError, "real upstream receiver edge"):
            _terminal_inlet({"arrays": {"receiver": np.array([-1], np.int64)}}, terrain, 0)


if __name__ == "__main__":
    unittest.main()
