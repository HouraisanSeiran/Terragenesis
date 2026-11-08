import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.tectonic import TectonicConfig, evolve
from terrain_pipeline.tectonic import connected_ocean, freeze, load_product, plan, prepare_frozen_product as prepare, save_product
from tools.prepare_tectonic_world import main


class TectonicProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = TectonicConfig(shape=(12, 16), plate_count=4, steps=3,
                                    origin_x_m=-80000., origin_z_m=30000.)
        cls.product = freeze(cls.config, evolve(cls.config))

    def test_deterministic_identity_and_cold_read(self):
        other = freeze(self.config, evolve(self.config))
        self.assertEqual(other.identity, self.product.identity)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "product.npz"
            save_product(self.product, path)
            loaded = load_product(path, expected_identity=self.product.identity)
            for key in self.product.arrays:
                np.testing.assert_array_equal(loaded.arrays[key], self.product.arrays[key])
                with self.assertRaises(ValueError):
                    loaded.arrays[key].setflags(write=True)
            with self.assertRaises(FileExistsError):
                save_product(self.product, path)
            with self.assertRaises(ValueError):
                load_product(path, expected_identity="wrong")

    def test_runtime_and_machine_paths_do_not_change_identity(self):
        result = evolve(self.config)
        result.metadata["runtime_seconds"] = 1234.
        result.metadata["machine_path"] = "D:/different-machine/output"
        self.assertEqual(freeze(self.config, result).identity, self.product.identity)

    def test_cli_generate_and_diagnostic_images(self):
        from PIL import Image
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".tectonic-test-", dir=root) as directory:
            output = Path(directory) / "published"
            with contextlib.redirect_stdout(io.StringIO()):
                report = main(["generate", "--shape", "12", "16", "--plates", "4", "--steps", "3",
                               "--output", str(output)])
            loaded = load_product(output / "product.npz", expected_identity=report["identity"])
            self.assertEqual(loaded.manifest["config"]["world_seed"], 20261020)
            for name in ("initial-macro.png", "final-macro.png", "process-budgets.png"):
                with Image.open(output / name) as image:
                    self.assertGreater(image.width, 1000)
            self.assertIsNone(json.loads((output / "diagnostics.json").read_text())["td_binding"])
            with self.assertRaises(FileExistsError):
                main(["generate", "--output", str(output)])

    def test_sampling_absolute_centres_reverse_overlap_and_seams(self):
        c = self.config
        x = c.origin_x_m + (np.arange(16) + .5) * c.cell_size_m
        z = c.origin_z_m + (np.arange(12) + .5) * c.cell_size_m
        all_samples = self.product.sample(x[None, :], z[:, None])
        for name, values in all_samples.items():
            np.testing.assert_array_equal(values, self.product.arrays["final/" + name])
            reverse = self.product.sample(x[::-1][None, :], z[::-1, None])[name]
            np.testing.assert_array_equal(reverse[::-1, ::-1], values)
            overlap = self.product.sample(x[4:10][None, :], z[3:8, None])[name]
            np.testing.assert_array_equal(overlap, values[3:8, 4:10])
        left = self.product.sample(c.origin_x_m, z)
        right = self.product.sample(c.origin_x_m + 16 * c.cell_size_m, z)
        for name in left:
            np.testing.assert_array_equal(left[name], right[name])
        for xbad in (c.origin_x_m - 1, c.origin_x_m + 16 * c.cell_size_m):
            with self.assertRaises(ValueError):
                self.product.sample(xbad, z, outside="reject")
        with self.assertRaises(ValueError):
            self.product.sample(np.nan, 0)

    def test_interpolation_and_read_only_queries(self):
        c = self.config
        x = c.origin_x_m + c.cell_size_m
        z = c.origin_z_m + c.cell_size_m
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "product.npz"
            save_product(self.product, path)
            before = path.read_bytes()
            with patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError("must not evolve")):
                loaded = load_product(path)
                values = loaded.sample(x, z)
            self.assertEqual(before, path.read_bytes())
            self.assertAlmostEqual(float(values["elevation_m"]),
                                   self.product.arrays["final/elevation_m"][:2, :2].mean())
            self.assertEqual(int(values["plate_id"]), int(self.product.arrays["final/plate_id"][1, 1]))

    def test_corrupt_field_schema_hash_and_missing_data_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.npz"
            for corruption in ("field", "schema", "identity", "missing", "dtype", "nan"):
                arrays = {k: v.copy() for k, v in self.product.arrays.items()}
                manifest = self.product.manifest
                if corruption == "field":
                    arrays["final/elevation_m"][0, 0] += 1
                elif corruption == "schema":
                    manifest["schema"] = "wrong"
                elif corruption == "identity":
                    manifest["identity"] = "wrong"
                elif corruption == "missing":
                    arrays.pop("final/plate_id")
                elif corruption == "dtype":
                    arrays["final/plate_id"] = arrays["final/plate_id"].astype(float)
                else:
                    arrays["final/elevation_m"][0, 0] = np.nan
                np.savez(path, manifest_json=np.array(json.dumps(manifest)), **arrays)
                with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                    load_product(path)

    def test_connected_ocean_excludes_enclosed_depression_and_wraps(self):
        elevation = np.ones((7, 7))
        elevation[0, 0] = -10
        elevation[0, -1] = -1
        elevation[3, 3] = -2
        ocean, seed = connected_ocean(elevation)
        self.assertEqual(seed, [0, 0])
        self.assertTrue(ocean[0, -1])
        self.assertFalse(ocean[3, 3])
        self.assertEqual(int(ocean.sum()), 2)
        self.assertIsNone(connected_ocean(np.ones((2, 2)))[1])

    def test_budget_precedes_evolution_and_cli_plan_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "never.npz"
            with patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError("must not evolve")):
                with self.assertRaisesRegex(ValueError, "budget"):
                    prepare(self.config, path, max_memory_bytes=1)
                self.assertFalse(path.exists())
                with contextlib.redirect_stdout(io.StringIO()):
                    report = main(["plan", "--shape", "12", "16", "--plates", "4", "--steps", "3",
                                   "--output", str(path)])
                self.assertTrue(report["allowed"])
                self.assertFalse(path.exists())
        self.assertFalse(plan(self.config, max_cell_plate_steps=1)["allowed"])
        with self.assertRaises(ValueError):
            plan(replace(self.config, world_seed=1))

    def test_failed_publication_leaves_no_product_or_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "product.npz"
            with patch('terrain_pipeline.tectonic.load_product', side_effect=ValueError("cold read failed")):
                with self.assertRaises(ValueError):
                    save_product(self.product, path)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cli_failed_render_leaves_no_completed_directory(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".tectonic-test-", dir=root) as directory:
            path = Path(directory) / "failed"
            with patch("tools.prepare_tectonic_world.render_diagnostics", side_effect=RuntimeError("render failed")):
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    main(["generate", "--shape", "12", "16", "--plates", "4", "--steps", "3",
                          "--output", str(path)])
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
