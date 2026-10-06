import unittest

import numpy as np

from terrain_pipeline.td_channel_vdm import channel_protection, reject_protected_sweep
from terrain_pipeline.td_native_channel_geometry import build_channel_geometry
from terrain_pipeline.td_native_channel_tiles import build_channel_tile, split_window_2x2
from terrain_pipeline.td_native_channel_surface import build_channel_surface
from tests.test_td_native_channel_geometry import fixture


class ChannelVdmTests(unittest.TestCase):
    def test_swept_face_cannot_jump_across_protected_river(self):
        rows, columns = np.mgrid[:7, :7]
        reference = np.stack((columns, np.zeros_like(rows), rows), axis=-1).astype(float)
        displaced = reference.reshape(-1, 3).copy()
        protected = np.zeros((7, 7), bool)
        protected[:, 3] = True
        triangles = np.array([[8, 15, 16]])
        displaced[triangles.ravel(), 0] += 4
        with self.assertRaisesRegex(ValueError, "protected"):
            reject_protected_sweep(reference, displaced, triangles, protected)
        displaced = reference.reshape(-1, 3).copy()
        displaced[triangles.ravel(), 1] += 1
        reject_protected_sweep(reference, displaced, triangles, protected)

    def test_mask_keeps_cut_and_source_link(self):
        hierarchy, page = fixture()
        geometry = build_channel_geometry(hierarchy, page)
        tiles = [build_channel_tile(geometry, window=window)
                 for window in split_window_2x2((0, 60, 0, 60))]
        surface = build_channel_surface(tiles, geometry=geometry)
        mask = channel_protection(surface, hierarchy)
        self.assertTrue(mask[surface["arrays"]["candidate_cut_m"].reshape(mask.shape) > 0].all())
        self.assertFalse(mask.flags.writeable)
        surface["metadata"]["hierarchy_identity"] = "0" * 64
        with self.assertRaises(ValueError):
            channel_protection(surface, hierarchy)


if __name__ == "__main__":
    unittest.main()
