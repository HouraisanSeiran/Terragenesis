import unittest

import numpy as np

from tools.verify_td_valley_global_tiled import _unique_ledger


def _bundle(x, cut):
    vertices = np.asarray([[x, 0.0], [x + 1.0, 0.0], [x + 1.0, 1.0],
                           [x, 1.0], [x + .5, .5]], dtype=np.float64)
    triangles = np.asarray([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], dtype=np.int64)
    cuts = np.full(5, cut, dtype=np.float64)
    return {"arrays": {"global_cell_xy": np.asarray([[int(x), 0]], dtype=np.int64),
                        "global_triangles": triangles,
                        "global_vertex_xz_m": vertices,
                        "global_cut_depth_m": cuts},
            "metadata": {"cut_volume_m3": float(cut),
                         "config": {"max_cut_m": 4.0}}}


class GlobalTiledAuditTests(unittest.TestCase):
    def test_unique_ledger_accepts_zero_support_duplicate(self):
        result = _unique_ledger([_bundle(0, 0.0), _bundle(0, 0.0)])
        self.assertEqual(result["duplicate_zero_support_cells"], 1)
        self.assertTrue(result["cross_component_positive_support_disjoint"])

    def test_unique_ledger_rejects_positive_overlap(self):
        with self.assertRaisesRegex(ValueError, "positive cut overlap"):
            _unique_ledger([_bundle(0, .1), _bundle(0, .1)])

    def test_distinct_cells_have_unique_material_volume(self):
        result = _unique_ledger([_bundle(0, .1), _bundle(2, .2)])
        self.assertEqual(result["unique_cells"], 2)
        self.assertAlmostEqual(result["global_unique_cut_volume_m3"], .3)


if __name__ == "__main__":
    unittest.main()
