import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_material_field import (
    _bundle, _save_bundle, load_material_field, make_material_field, save_material_field,
)


def malicious_archive(path):
    stream = io.BytesIO()
    np.lib.format.write_array_header_1_0(stream, {"descr": "<f8", "fortran_order": False, "shape": (2 ** 40,)})
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("erodibility.npy", stream.getvalue())


class MaterialFieldTests(unittest.TestCase):
    def make(self, shape=(12, 17), **kwargs):
        options = {"origin_m_xz": (-300, 600), "spacing_m": 30, **kwargs}
        return make_material_field(shape, **options)

    def test_seed_replay_variation_ranges_and_readonly(self):
        first = self.make()
        self.assertEqual(first["identity_sha256"], self.make()["identity_sha256"])
        other = self.make(seed=20261003)
        self.assertFalse(np.array_equal(first["arrays"]["erodibility"], other["arrays"]["erodibility"]))
        for name, low, high in (("erodibility", 0.25, 1), ("erodible_thickness_m", 0.25, 4), ("weak_path_preference", 0.8, 1.2)):
            values = first["arrays"][name]
            self.assertTrue(np.all((values >= low) & (values <= high)))
            with self.assertRaises(ValueError):
                values.setflags(write=True)

    def test_windows_tiles_and_reversed_order_exact(self):
        full = self.make((24, 30))
        for row, col in reversed([(0, 0), (0, 10), (12, 0), (12, 10), (5, 7)]):
            window = self.make((8, 9), origin_m_xz=(-300 + col * 30, 600 + row * 30))
            for name in full["arrays"]:
                np.testing.assert_array_equal(window["arrays"][name], full["arrays"][name][row:row + 8, col:col + 9])

    def test_fractional_spacing_windows_exact(self):
        full = self.make((8, 10), origin_m_xz=(-0.7, 0.3), spacing_m=0.1)
        window = self.make((4, 4), origin_m_xz=(-0.4, 0.5), spacing_m=0.1)
        np.testing.assert_array_equal(window["arrays"]["erodibility"], full["arrays"]["erodibility"][2:6, 3:7])

    def test_continuity_small_step_and_lattice_seam(self):
        field = self.make((1, 200), origin_m_xz=(899.0, 0.0), spacing_m=0.01)
        self.assertLess(float(np.max(np.abs(np.diff(field["arrays"]["erodibility"])))), 1e-4)

    def test_reject_invalid_parameters(self):
        for parameters in ({"solid_density_kg_m3": 0}, {"solid_density_kg_m3": np.nan},
                           {"source_porosity": -0.1}, {"source_porosity": 1},
                           {"deposit_porosity": np.inf}, {"correlation_length_m": 0},
                           {"erodibility_range": [0.1, 2]}, {"erodible_thickness_range_m": [4, 1]},
                           {"unknown": 2}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                self.make(parameters=parameters)

    def test_reject_invalid_grid_and_mask(self):
        for options in ({"shape": (1025, 1025)}, {"shape": (0, 2)}, {"seed": -1},
                        {"seed": True}, {"origin_m_xz": (1, 0)}, {"spacing_m": np.inf},
                        {"protected_mask": np.ones((12, 17), int)}):
            shape = options.pop("shape", (12, 17))
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.make(shape, **options)

    def test_cold_load_externally_pinned_without_generation(self):
        field = self.make()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "material.npz"
            save_material_field(field, path)
            digest = file_sha256(path)
            with patch("terrain_pipeline.td_material_field.make_material_field", side_effect=AssertionError("generation forbidden")):
                loaded = load_material_field(path, expected_sha256=digest, expected_identity=field["identity_sha256"])
                self.assertEqual(loaded["identity_sha256"], field["identity_sha256"])
            with self.assertRaises(ValueError):
                load_material_field(path)
            with self.assertRaises(FileExistsError):
                save_material_field(field, path)
            self.assertEqual(file_sha256(path), digest)

    def test_rehashed_forgery_rejected_by_external_pin(self):
        original = self.make()
        altered = {name: values.copy() for name, values in original["arrays"].items()}
        altered["erodibility"][:] = 0.5
        forged = _bundle(altered, original["metadata"])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "forged.npz"
            _save_bundle(forged, path)
            with self.assertRaises(ValueError):
                load_material_field(path, expected_identity=original["identity_sha256"])
            with self.assertRaises(ValueError):
                load_material_field(path, expected_sha256="0" * 64)

    def test_malicious_header_rejected_before_allocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "malicious.npz"
            malicious_archive(path)
            with patch("numpy.load", side_effect=AssertionError("allocation forbidden")):
                with self.assertRaises(ValueError):
                    load_material_field(path, expected_sha256=file_sha256(path))


if __name__ == "__main__":
    unittest.main()
