import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools import prepare_world_terrain_water, query_world_terrain_water
from terrain_pipeline.common_infra import file_sha256


class WorldTerrainWaterCliTests(unittest.TestCase):
    def test_prepare_composes_full_page_before_cropping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "page.npz"
            np.savez(page, metadata_json=json.dumps({"native_origin": [10, 20], "size": 40}))
            digest = file_sha256(page)
            source = np.arange(1600, dtype=float).reshape(40, 40)
            seen = {}

            def compose(spec, elevation, origin, **kwargs):
                seen["source_shape"] = elevation.shape
                return {"metadata": {"filter_radius_cells": 2, "identity": "composition"}}

            def crop(product, origin, shape):
                seen["crop"] = (origin, shape)
                field = np.ones(shape)
                return {"metadata": product["metadata"], "td_elevation_m": field,
                        "macro_elevation_m": field, "composed_elevation_m": field,
                        "ocean_mask": None}

            def form(height, ocean, origin, seed, source_record, **kwargs):
                seen["ocean"] = ocean.copy()
                empty = np.zeros(height.shape, bool)
                return {"arrays": {"final_bed_m": height, "bed_before_m": height,
                        "water_surface_m": height, "ocean_mask": empty, "lake_mask": empty,
                        "pending_basin_mask": empty, "channel_mask": empty},
                        "metadata": {}, "identity_sha256": "water"}

            with patch.object(prepare_world_terrain_water, "_read_page", return_value=(source,
                    {"size": 40, "native_origin": [10, 20]}, [10, 20])), \
                 patch.object(prepare_world_terrain_water, "BORDER_BAND_CELLS", 0), \
                 patch.object(prepare_world_terrain_water, "compose_source", side_effect=compose), \
                 patch.object(prepare_world_terrain_water, "crop_composition", side_effect=crop), \
                 patch.object(prepare_world_terrain_water, "form_water_and_rivers", side_effect=form), \
                 patch.object(prepare_world_terrain_water, "render"):
                prepare_world_terrain_water.main(["--page", str(page), "--page-sha256", digest,
                    "--origin", "14", "24", "--shape", "5", "6", "--runoff-m-per-year", "1",
                    "--duration-seconds", "100", "--channel-threshold-m3-s", "0.1",
                    "--output", str(root / "product")])
            self.assertEqual(seen["source_shape"], (40, 40))
            self.assertEqual(seen["crop"], ([14, 24], [5, 6]))
            self.assertFalse(seen["ocean"].any())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                query_world_terrain_water.main([str(root / "product"), "--native-xz", "14", "24"])
            self.assertEqual(json.loads(output.getvalue())["values"]["final_bed_m"], 1.)
            with self.assertRaises(ValueError):
                query_world_terrain_water.main([str(root / "product"), "--native-xz", "13", "24"])

    def test_real_prepare_and_cold_query_for_lakes_and_ocean(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "source.npz"
            rows, cols = np.indices((40, 40))
            elevation = (100. + np.sin(rows / 3.) * 10. + np.cos(cols / 4.) * 8.).astype(np.float64)
            page_metadata = {"schema": "td-native-page-v1", "native_origin": [1000, 1000],
                             "size": 40, "spacing_m": 30., "world_seed": 20261020}
            np.savez(page, elevation_native=elevation, metadata_json=json.dumps(page_metadata))
            digest = file_sha256(page)
            with self.assertRaisesRegex(ValueError, "pin_mismatch"):
                prepare_world_terrain_water.main(["--page", str(page), "--page-sha256", "0" * 64,
                    "--runoff-m-per-year", "0.5", "--duration-seconds", "86400",
                    "--channel-threshold-m3-s", "0.000001", "--output", str(root / "bad")])
            for preset in ("lakes", "archipelago"):
                output_path = root / preset
                with contextlib.redirect_stdout(io.StringIO()):
                    prepare_world_terrain_water.main(["--page", str(page), "--page-sha256", digest,
                        "--preset", preset, "--sigma-cells", "1", "--runoff-m-per-year", "0.5",
                        "--duration-seconds", "86400", "--channel-threshold-m3-s", "0.000001",
                        "--output", str(output_path)])
                self.assertTrue((output_path / "stages.png").is_file())
                metadata = json.loads((output_path / "metadata.json").read_text(encoding="utf-8"))
                source_record = metadata["composition"]["source_record"]
                border = source_record["source_border_cells"]
                halo = metadata["composition"]["filter_radius_cells"]
                self.assertGreater(border, 0)
                self.assertEqual(metadata["origin_native_xz"], [1000 + border + halo] * 2)
                self.assertEqual(metadata["shape_zx"], [40 - 2 * (border + halo)] * 2)
                coordinate = [str(value) for value in metadata["origin_native_xz"]]
                result = io.StringIO()
                with contextlib.redirect_stdout(result):
                    query_world_terrain_water.main([str(output_path), "--native-xz", *coordinate])
                self.assertIn("final_bed_m", json.loads(result.getvalue())["values"])
                with np.load(output_path / "arrays.npz", allow_pickle=False) as archive:
                    arrays = {name: archive[name] for name in archive.files}
                arrays["final_bed_m"][0, 0] += 1.
                np.savez_compressed(output_path / "arrays.npz", **arrays)
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    query_world_terrain_water.main([str(output_path), "--native-xz", *coordinate])


if __name__ == "__main__":
    unittest.main()
