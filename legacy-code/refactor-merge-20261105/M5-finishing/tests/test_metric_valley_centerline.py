import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.channel_geometry import GeometryConfig
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import build_valley_centerline, load_valley_centerline, save_valley_centerline, validate_valley_centerline


def fixture():
    rows, cols = np.indices((13, 13))
    height = (50. - .3 * cols - .2 * rows).astype(np.float64)
    terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 4., 4.,
                          "observed_dem", "linear valley", "a" * 64)
    ids = np.array([3 * 13 + 3, 4 * 13 + 4, 4 * 13 + 5, 5 * 13 + 6], np.int64)
    receiver = np.array([1, 2, 3, -1], np.int64)
    options = dict(owner_grid=np.zeros(height.shape, np.int64),
                   corridor_mask=np.ones(height.shape, bool),
                   lake_mask=np.zeros(height.shape, bool),
                   source_plan_identity_sha256="b" * 64,
                   config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))
    return terrain, ids, receiver, options


class ValleyCenterlineTests(unittest.TestCase):
    def test_anchored_shape_decreases_turn_and_roundtrips(self):
        terrain, ids, receiver, options = fixture()
        result = build_valley_centerline(terrain, ids, receiver, np.full(4, 2.),
                                         np.full(4, .25), **options)
        self.assertTrue(validate_valley_centerline(result))
        self.assertGreater(result["metadata"]["moved_nodes"], 0)
        self.assertLess(result["metadata"]["final_turn_energy"],
                        result["metadata"]["initial_turn_energy"])
        a = result["arrays"]
        np.testing.assert_array_equal(a["node_xz_m"][a["anchor_mask"]],
                                      a["original_node_xz_m"][a["anchor_mask"]])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "centerline.npz"
            save_valley_centerline(path, result)
            loaded = load_valley_centerline(path, expected_sha256=file_sha256(path),
                                            expected_identity=result["identity_sha256"])
        self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
