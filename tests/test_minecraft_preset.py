import unittest

import numpy as np

from terrain_pipeline.minecraft_preset import MinecraftExportPreset


class MinecraftPresetTests(unittest.TestCase):
    def test_explicit_metres_mapping_and_reserved_headroom(self):
        preset = MinecraftExportPreset(metres_per_block=10)
        physical = np.array([-1280., -1., 0., 1024., 9580.])
        original = physical.copy()
        np.testing.assert_array_equal(preset.transform(physical), [-64, 63, 64, 166, 1022])
        np.testing.assert_array_equal(physical, original)
        self.assertTrue(preset.dry_run(physical)["accepted"])
        self.assertEqual(preset.ceiling_exclusive_y, 1024)

    def test_dryrun_reports_clipping_and_transform_rejects(self):
        preset = MinecraftExportPreset(metres_per_block=1)
        report = preset.dry_run([-129, 0, 959])
        self.assertEqual(report["below_min_count"], 1)
        self.assertEqual(report["above_safe_top_count"], 1)
        self.assertFalse(report["accepted"])
        for values in ([-129], [959], [958.01]):
            with self.assertRaises(ValueError):
                preset.transform(values)

    def test_invalid_scale_data_and_preset_identity(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                MinecraftExportPreset(value)
        for data in ([], [float("nan")], [float("inf")]):
            with self.assertRaises(ValueError):
                MinecraftExportPreset(10).dry_run(data)
        with self.assertRaises(ValueError):
            MinecraftExportPreset(10, sea_level_y=72)
        self.assertNotEqual(MinecraftExportPreset(10).identity(), MinecraftExportPreset(30).identity())


if __name__ == "__main__":
    unittest.main()
