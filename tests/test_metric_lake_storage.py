import unittest

import numpy as np

from terrain_pipeline.lake import LakeOutlet as LakeOutlet
from terrain_pipeline.lake import LakeStorage as LakeStorage


def bowl():
    return LakeStorage(
        cell_ids=np.array([3, 8], np.int64),
        bed_elevation_m=np.array([10., 11.]),
        cell_area_m2=np.array([2., 3.]),
        seed_cell_id=3, max_stage_m=12.,
        source_identity_sha256="a" * 64,
        footprint_policy="explicit isolated two-cell pool",
    )


class LakeStorageTests(unittest.TestCase):
    def test_piecewise_linear_bowl_volume_and_inverse(self):
        lake = bowl()
        self.assertEqual(lake.volume_at_stage(10.), 0.)
        self.assertEqual(lake.volume_at_stage(11.), 2.)
        self.assertEqual(lake.volume_at_stage(12.), 7.)
        self.assertEqual(lake.capacity_m3, 7.)
        self.assertEqual(lake.stage_at_volume(2.), 11.)
        self.assertEqual(lake.stage_at_volume(4.5), 11.5)
        np.testing.assert_array_equal(lake.wet_mask_at_stage(11.), [True, False])
        np.testing.assert_array_equal(lake.depth_at_stage(11.5), [1.5, .5])
        self.assertEqual(lake.surface_area_at_stage(11.), 2.)
        self.assertEqual(lake.surface_area_at_stage(11.5), 5.)

    def test_mixed_levels_large_datum_and_immutable_source(self):
        base = 1_000_000_000.
        ids = np.array([2, 3, 5], np.int64)
        bed = np.array([base, base, base + .25])
        area = np.array([1., 2., 4.])
        lake = LakeStorage(ids, bed, area, 2, base + .75,
                           "a" * 64, "explicit three-cell support")
        ids[0], bed[0], area[0] = 99, 0., 99.
        np.testing.assert_array_equal(lake.cell_ids, [2, 3, 5])
        self.assertEqual(lake.volume_at_stage(base + .25), .75)
        self.assertEqual(lake.capacity_m3, 4.25)
        self.assertEqual(lake.stage_at_volume(2.5), base + .5)
        for values in (lake.cell_ids, lake.bed_elevation_m, lake.cell_area_m2,
                       lake.wet_mask_at_stage(base + .5), lake.depth_at_stage(base + .5)):
            with self.assertRaises(ValueError):
                values[0] = 0

    def test_outlet_rating_and_input_rejection(self):
        outlet = LakeOutlet(0, -1, 11., 2., "bench broad crest")
        self.assertEqual(outlet.discharge_at_stage(10.), 0.)
        self.assertEqual(outlet.discharge_at_stage(12.), 2.)
        self.assertAlmostEqual(outlet.discharge_at_stage(15.), 16.)
        with self.assertRaisesRegex(ValueError, "positive"):
            LakeOutlet(0, -1, 11., 0., "invalid coefficient")
        with self.assertRaises(ValueError):
            outlet.discharge_at_stage(float("nan"))
        with self.assertRaisesRegex(ValueError, "finite lake"):
            bowl().volume_at_stage(12.1)
        with self.assertRaisesRegex(ValueError, "capacity"):
            bowl().stage_at_volume(7.1)

    def test_bad_footprints_and_resource_limits_reject(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            LakeStorage(np.array([3, 3], np.int64), np.array([10., 11.]),
                        np.array([1., 1.]), 3, 12., "a" * 64, "duplicate")
        with self.assertRaisesRegex(ValueError, "minimum"):
            LakeStorage(np.array([3, 8], np.int64), np.array([10., 11.]),
                        np.array([1., 1.]), 8, 12., "a" * 64, "wrong seed")
        with self.assertRaisesRegex(ValueError, "positive"):
            LakeStorage(np.array([3], np.int64), np.array([10.]),
                        np.array([0.]), 3, 12., "a" * 64, "zero area")
        with self.assertRaisesRegex(ValueError, "bounded"):
            LakeStorage(np.arange(65537, dtype=np.int64), np.zeros(65537),
                        np.ones(65537), 0, 1., "a" * 64, "too many")


if __name__ == "__main__":
    unittest.main()
