import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.minecraft_export import export_metric_minecraft


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "verification/metric-region-v1/run-20260929T080003051803Z"
V3_SAMPLES = ROOT / "verification/height-budget-v3/run-20260929T091944094519Z"


class MinecraftExportTests(unittest.TestCase):
    def export_grid(self, directory, relative_height, sea=126):
        elevation = np.array(relative_height, dtype=np.float64) + sea
        original = elevation.copy()
        base = SimpleNamespace(water=None, origin_x_m=0, origin_z_m=0,
                               spacing_x_m=64, spacing_z_m=64,
                               sea_level_elevation_m=sea,
                               identity=SimpleNamespace(seed=7))
        derived = SimpleNamespace(water=None, displacement_type="vertical",
                                  content_id="a" * 64)
        region = SimpleNamespace(base=base, derived=derived,
                                 reconstructed_elevation_m=lambda: elevation,
                                 dominant_type=np.zeros(elevation.shape, dtype=np.uint8))
        destination = Path(directory) / "surface.tgmc"
        with patch("terrain_pipeline.minecraft_export.load_metric_region", return_value=region):
            try:
                export_metric_minecraft("synthetic-region", destination)
                return destination, original, elevation, None
            except ValueError as error:
                return destination, original, elevation, error

    def test_publication_boundary_sea_datum_and_source_immutability(self):
        for sea in (0, 126, 426):
            for peak in (699, 800, 851, 1022, 1022.001):
                with self.subTest(sea=sea, peak=peak), tempfile.TemporaryDirectory() as directory:
                    relative = np.full((3, 3), 100.0)
                    relative[1, 1] = peak - 62
                    destination, original, elevation, error = self.export_grid(directory, relative, sea)
                    np.testing.assert_array_equal(elevation, original)
                    if peak <= 1022:
                        self.assertIsNone(error)
                        self.assertTrue(destination.is_file())
                    else:
                        self.assertRegex(str(error), "build height")
                        self.assertEqual(list(Path(directory).iterdir()), [])

    def test_build_bounds_and_nonfinite_heights_still_rejected(self):
        for height, message in ((-64.001, "build height"), (1022.001, "build height"),
                                (float("nan"), "finite"), (float("inf"), "finite")):
            with self.subTest(height=height), tempfile.TemporaryDirectory() as directory:
                relative = np.full((3, 3), 0.0)
                relative[2, 2] = height - 62
                destination, _, _, error = self.export_grid(directory, relative)
                self.assertRegex(str(error), message)
                self.assertFalse(destination.exists())
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_checked_v3_and_old_plains_snapshots_rejects_overbuild_samples(self):
        if not SAMPLES.is_dir() or not V3_SAMPLES.is_dir():
            self.fail("real metric samples required for consumer acceptance")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "plateau.tgmc"
            export_metric_minecraft(V3_SAMPLES / "plateau-region", destination)
            self.assertGreater(destination.stat().st_size, 100)
            with self.assertRaises(FileExistsError):
                export_metric_minecraft(V3_SAMPLES / "plateau-region", destination)
            highland = Path(temporary) / "highland.tgmc"
            export_metric_minecraft(V3_SAMPLES / "highland-region", highland)
            self.assertGreater(highland.stat().st_size, 100)
            plains = Path(temporary) / "old-plains.tgmc"
            export_metric_minecraft(SAMPLES / "plains/resolvable_30m_candidate", plains)
            self.assertGreater(plains.stat().st_size, 100)
            for sample in ("plateau", "highland"):
                rejected = Path(temporary) / f"{sample}-old.tgmc"
                with self.assertRaisesRegex(ValueError, "build height"):
                    export_metric_minecraft(SAMPLES / sample / "resolvable_30m_candidate",
                                            rejected)
                self.assertFalse(rejected.exists())

    def test_failed_publish_removes_partial_file(self):
        if not V3_SAMPLES.is_dir():
            self.fail("real metric samples required for consumer acceptance")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "failed.tgmc"
            with patch("terrain_pipeline.minecraft_export.os.rename", side_effect=OSError("publish failed")):
                with self.assertRaisesRegex(OSError, "publish failed"):
                    export_metric_minecraft(V3_SAMPLES / "plateau-region", destination)
            self.assertEqual(list(Path(temporary).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
