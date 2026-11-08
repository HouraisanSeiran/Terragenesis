import unittest
import numpy as np
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from terrain_pipeline.surface_rivers.native_30m_reach_selection import select_from_topology

class TestSelection(unittest.TestCase):
    def test_select_success(self):
        e = np.zeros((9, 9), np.float64)
        e[4, 4] = -1
        top = build_strict_topology(e, np.ones(e.shape, bool), origin_native_xz=(-10, 7))
        result = select_from_topology(e, top, origin_native_xz=(-10, 7), min_stem_m=1., min_catchment_cells=2, contact_margin_cells=1)
        c = result['chosen']
        self.assertEqual(c['terminal_flat_cell'], 40)
        self.assertEqual(tuple(c['terminal_native_xz']), (-6, 11))
        donors = np.flatnonzero(top['receiver'].ravel() == 40)
        self.assertEqual(c['catchment_cells'], donors.size + 1)
        self.assertTrue(np.array_equal(c['stem_flat_cells'], [int(donors.min()), 40]))
        mesh = top['mesh']
        first = int(donors.min())
        self.assertAlmostEqual(c['stem_length_m'], np.hypot(
            mesh.node_x_m[first] - mesh.node_x_m[40],
            mesh.node_z_m[first] - mesh.node_z_m[40]))

    def test_select_raises(self):
        e = np.zeros((9, 9), np.float64)
        e[4, 4] = -1
        top = build_strict_topology(e, np.ones(e.shape, bool), origin_native_xz=(-10, 7))
        with self.assertRaises(ValueError):
            select_from_topology(e, top, origin_native_xz=(-10, 7), min_stem_m=1., min_catchment_cells=100, contact_margin_cells=1)

if __name__ == '__main__':
    unittest.main()
