import unittest
import numpy as np
from terrain_pipeline.common_infra import TerrainGrid, GRID_MAX_CELLS as MAX_CELLS, MAX_FORCING_ENTRIES
from tools.render_hydrology_large_preview import frozen_domain_diagnostics


class LargePreviewTests(unittest.TestCase):
    def test_static_grid_crosses_old_capacity_but_new_limit_is_bounded(self):
        h = np.zeros((1025, 1024), np.float64)
        grid = TerrainGrid(h, np.ones(h.shape, bool), 0., 0., 30., 30., "generated_terrain", "source", "0" * 64)
        self.assertEqual(grid.elevation_m.shape, h.shape)
        self.assertEqual(MAX_CELLS, 1280**2)
        self.assertEqual(MAX_FORCING_ENTRIES, 3 * 1024**2)
        too_large = np.zeros((1, MAX_CELLS + 1), np.float64)
        with self.assertRaisesRegex(ValueError, "bounded"):
            TerrainGrid(too_large, np.ones(too_large.shape, bool), 0., 0., 30., 30., "generated_terrain", "source", "0" * 64)

    def test_owner_conflict_and_unclosed_edge_do_not_become_legal_ports(self):
        plan = {"height_m": np.zeros((2, 2)), "origin_xz_m": [0., 0.], "spacing_m": 30.,
                "owner_domain_id": np.array([[0, 1], [0, -1]]), "domains": [{"terminal_indices": [3]}]}
        receiver = np.array([1, -1, 3, -1])
        kinds = np.array(["interior", "unknown_boundary", "interior", "lake_preserved"])
        _, conflicts, unclosed, report = frozen_domain_diagnostics(plan, (2, 2), [0., 0.], 30., receiver, kinds, np.array([0, 2]))
        self.assertEqual(conflicts.tolist(), [0])
        self.assertEqual(unclosed.tolist(), [1])
        self.assertEqual(report["selected_owner_crossing_conflicts"], 1)
        self.assertEqual(report["unclosed_boundary_terminal_count"], 1)
        self.assertFalse(report["frozen_domain_routing_certified"])
        self.assertFalse(report["actual_bed_verified"])


if __name__ == "__main__":
    unittest.main()
