from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import io
import json

import numpy as np

from terrain_pipeline import surface_domain_mosaic as mosaic
from terrain_pipeline import surface_fine_mosaic as fine
from terrain_pipeline.surface_domain_prepare import load_surface_domains


SOURCE = (Path(__file__).resolve().parents[1] / "verification/surface-domain-prepare"
          / "run-20260930T103111870204Z/two-domain-prepared.npz")


def mutable(value):
    return deepcopy(fine._plain(value))


def rehash(value):
    value.pop("identity_sha256", None)
    value["identity_sha256"] = fine._identity(value)
    return value


class SurfaceDomainMosaicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluation = load_surface_domains(SOURCE)
        cls.result = mosaic.prepare_domain_mosaic(cls.evaluation)

    def test_fixed_coverage_seam_and_q(self):
        result = self.result
        self.assertEqual(result["extension_cell_count"], 600)
        self.assertEqual(result["cells"].shape, (7800, 4))
        self.assertEqual(result["triangles"].shape, (15600, 3))
        self.assertEqual(len(result["nodes"]["x_m"]), 7991)
        self.assertEqual([int(np.sum(result["hydrologic_domain_owner"] == domain)) for domain in (1, 2)], [3900, 3900])
        self.assertEqual([int(np.sum((result["cell_owner"] == 2) & (result["hydrologic_domain_owner"] == domain))) for domain in (1, 2)], [300, 300])
        self.assertTrue(np.all(result["nodes"]["h0_m"][result["nodes"]["x_m"] == 75] == 10.))
        self.assertAlmostEqual(result["summary"]["q_outgoing_m3_s"], .400098)
        self.assertAlmostEqual(result["summary"]["unique_cut_volume_m3"], 576.8710544290026)
        self.assertAlmostEqual(result["summary"]["actual_wet_water_volume_m3"], 236.01507098278892)
        self.assertTrue(mosaic.validate_domain_mosaic(result))

    def test_static_reload_readonly_and_no_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mosaic.npz"
            mosaic.save_domain_mosaic(self.result, path)
            with patch.object(mosaic, "prepare_domain_mosaic", side_effect=AssertionError("prepared")), \
                 patch.object(mosaic, "_assemble", side_effect=AssertionError("assembled")), \
                 patch.object(fine, "_mesh", side_effect=AssertionError("mesh generated")), \
                 patch.object(fine, "_h0_support", side_effect=AssertionError("support generated")):
                loaded = mosaic.load_domain_mosaic(path)
            self.assertEqual(loaded["identity_sha256"], self.result["identity_sha256"])
            with self.assertRaises(ValueError):
                loaded["nodes"]["h0_m"][0] = 1.
            with self.assertRaises(FileExistsError):
                mosaic.save_domain_mosaic(self.result, path)

    def test_saved_mosaic_full_static_guard_and_coherent_proof_rejection(self):
        from tests.test_surface_variable_storage import static_disabled
        frozen = SOURCE.parents[2] / "surface-domain-mosaic/run-20260930T170535.835312Z/two-domain-dry-extension.npz"
        with ExitStack() as stack:
            static_disabled(stack)
            stack.enter_context(patch.object(mosaic, "_assemble", side_effect=AssertionError("assembly")))
            loaded = mosaic.load_domain_mosaic(frozen)
            self.assertTrue(mosaic.validate_domain_mosaic(loaded))
            changed = mutable(loaded)
            domain_mesh = changed["domain_meshes"][0]
            proof_id = next(iter(domain_mesh["proofs"]))
            domain_mesh["proof_h0_support"][proof_id]["weights"][0, 0] += .2
            rehash(domain_mesh)
            with self.assertRaises(ValueError):
                mosaic.validate_domain_mosaic(rehash(changed))

    def test_coherent_rehash_attacks(self):
        for change in (
            lambda value: value["nodes"]["h2_m"].__setitem__(75, 9.),
            lambda value: value["contributors"]["weights"].__setitem__((3600, 0, 0), .5),
            lambda value: value["cell_owner"].__setitem__((0, 0), 2),
            lambda value: value["hydrologic_domain_owner"].__setitem__((0, 0), 2),
            lambda value: value["grid"]["bbox_xz_m"].__setitem__(1, 130.),
            lambda value: value["domain_meshes"][0]["sources"][0]["window_zx"].__setitem__(3, 60),
        ):
            with self.subTest(change=change):
                value = mutable(self.result)
                change(value)
                with self.assertRaises(ValueError):
                    mosaic.validate_domain_mosaic(rehash(value))

        value = mutable(self.result)
        value["domain_meshes"][0]["sources"][0]["window_zx"][3] = 60
        rehash(value["domain_meshes"][0])
        with self.assertRaises(ValueError):
            mosaic.validate_domain_mosaic(rehash(value))

        value = mutable(self.result)
        extension_cell = int(np.flatnonzero(value["cell_owner"].ravel() == 2)[0])
        value["contributors"]["weights"][extension_cell, 1, 0] += .1
        value["contributors"]["weights"][extension_cell, 1, 1] -= .1
        with self.assertRaises(ValueError):
            mosaic.validate_domain_mosaic(rehash(value))

        value = mutable(self.result)
        extension_node = int(value["cells"][extension_cell, 1])
        value["nodes"]["h0_m"][extension_node] += 1.
        value["nodes"]["h2_m"][extension_node] += 1.
        with self.assertRaises(ValueError):
            mosaic.validate_domain_mosaic(rehash(value))

    def test_resource_cancel_and_original_support(self):
        with self.assertRaises(ValueError):
            mosaic.prepare_domain_mosaic(self.evaluation, resources=fine.MosaicResources(max_cells=7799))
        with self.assertRaises(InterruptedError):
            mosaic.prepare_domain_mosaic(self.evaluation, cancel=lambda: True)
        value = mutable(self.result)
        candidate = value["evaluation"]["candidate"]
        candidate["inputs"]["land_mask"][1, 7] = False
        column = 60
        row = 0
        cell_id = row * 130 + column
        with self.assertRaises(ValueError):
            mosaic._extension_value(candidate, 71., 10.,
                value["contributors"]["indices"][cell_id, 1],
                value["contributors"]["weights"][cell_id, 1])

        for mask in ("valid_mask", "land_mask"):
            candidate = mutable(self.evaluation["candidate"])
            candidate["inputs"][mask][1, 7] = False
            with self.assertRaises(ValueError):
                mosaic._extension_value(candidate, 71., 10.,
                    value["contributors"]["indices"][cell_id, 1],
                    value["contributors"]["weights"][cell_id, 1])

    def test_protection_and_wet_seam_rejection(self):
        value = mutable(self.result)
        extension_cell = int(np.flatnonzero(value["cell_owner"].ravel() == 2)[0])
        indices = value["contributors"]["indices"][extension_cell, 1]
        weights = value["contributors"]["weights"][extension_cell, 1]
        candidate = value["evaluation"]["candidate"]
        candidate["inputs"]["protected_mask"][1, 7] = True
        height, protected = mosaic._extension_value(candidate, 71., 10., indices, weights)
        self.assertEqual(height, 10.)
        self.assertTrue(protected)
        with self.assertRaises(ValueError):
            mosaic.validate_domain_mosaic(rehash(value))

        value = mutable(self.result)
        shared = int(np.flatnonzero((value["nodes"]["x_m"] == 70.) & (value["nodes"]["z_m"] == 10.))[0])
        value["domain_meshes"][0]["nodes"]["wet_mask"][-1] = True
        value["domain_meshes"][0]["nodes"]["water_surface_m"][-1] = 11.
        rehash(value["domain_meshes"][0])
        with self.assertRaises(ValueError):
            mosaic.validate_domain_mosaic(rehash(value))

    def test_archive_gate_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.npz"
            mosaic.save_domain_mosaic(self.result, path)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                mosaic.save_domain_mosaic(self.result, path)
            self.assertEqual(path.read_bytes(), original)
            for name, payload in (("extra.npy", b"not an NPY"), ("array_object.npy", self._object_npy())):
                attack = Path(directory) / name.replace(".npy", ".npz")
                with zipfile.ZipFile(path) as source, zipfile.ZipFile(attack, "w") as output:
                    for member in source.namelist():
                        output.writestr(member, source.read(member))
                    output.writestr(name, payload)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    mosaic.load_domain_mosaic(attack)

    @staticmethod
    def _object_npy():
        stream = io.BytesIO()
        np.save(stream, np.array(["bad"], dtype=object), allow_pickle=True)
        return stream.getvalue()


if __name__ == "__main__":
    unittest.main()
