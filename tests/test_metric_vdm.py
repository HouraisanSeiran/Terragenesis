"""Metric cliff skeleton and bounded bundle contract tests."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.metric_vdm import CliffRecipe, build_vdm, load_vdm, save_vdm, validate_vdm
from terrain_pipeline.mountain_source_adapter import file_sha256


def chart(*, elevation=0, center=(0, 0), outward=(1, 0)):
    rows, cols = 21, 25
    row, col = np.indices((rows, cols))
    normal = np.array(outward, dtype=float)
    normal /= np.linalg.norm(normal)
    along = np.array((normal[1], -normal[0]))
    u = col - cols // 2
    v = row - rows // 2
    reference = np.empty((rows, cols, 3), dtype=float)
    reference[:, :, 0] = center[0] + u * along[0] + v * normal[0]
    reference[:, :, 1] = elevation
    reference[:, :, 2] = center[1] + u * along[1] + v * normal[1]
    return reference


def recipe(*, angle=60, lean=1, center=(0, 0), outward=(1, 0)):
    return CliffRecipe(center_xz_m=center, outward_xz=outward, height_m=12,
                       half_length_m=8, half_depth_m=7, wall_half_width_m=2,
                       end_fade_m=2, angle_degrees=angle, lean=lean)


def build(reference=None, settings=None, mask=None):
    reference = chart() if reference is None else reference
    settings = recipe() if settings is None else settings
    mask = np.zeros(reference.shape[:2], dtype=bool) if mask is None else mask
    return build_vdm(reference, recipe=settings, protected_mask=mask,
                     source_identity="source-1", protection_identity="mask-1")


class MetricVdmTests(unittest.TestCase):
    def test_java_skeleton_center_and_wall_edges(self):
        for angle in (60, 90):
            for lean in (-1, 1):
                with self.subTest(angle=angle, lean=lean):
                    result = build(settings=recipe(angle=angle, lean=lean))
                    delta = result["arrays"]["displacement_xyz_m"]
                    np.testing.assert_allclose(delta[10, 12], [0, 0, 0], atol=1e-12)
                    offset = lean * 12 / np.tan(np.deg2rad(angle))
                    np.testing.assert_allclose(delta[8, 12], [offset / 2 + 2, 6, 0], atol=1e-12)
                    np.testing.assert_allclose(delta[12, 12], [-offset / 2 - 2, -6, 0], atol=1e-12)
                    self.assertFalse(delta[0].any())
                    self.assertFalse(delta[-1].any())

    def test_overhang_keeps_full_xyz_and_downward_faces(self):
        result = build(settings=recipe(angle=60, lean=1))
        arrays = result["arrays"]
        self.assertTrue(np.any(arrays["displacement_xyz_m"][:, :, 0] != 0))
        self.assertTrue(np.any(arrays["displacement_xyz_m"][:, :, 1] != 0))
        vertices = arrays["vertices_xyz_m"]
        points = vertices[arrays["triangles"]]
        normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        self.assertTrue(np.any(normals[:, 1] < 0))
        self.assertTrue(validate_vdm(result))

    def test_translation_rotation_and_protection(self):
        center = (103, -57)
        outward = (0, 1)
        baseline = build()
        rotated = build(chart(elevation=213, center=center, outward=outward),
                        recipe(center=center, outward=outward))
        initial = baseline["arrays"]["displacement_xyz_m"]
        transformed = rotated["arrays"]["displacement_xyz_m"]
        np.testing.assert_allclose(transformed[:, :, 1], initial[:, :, 1])
        np.testing.assert_allclose(transformed[:, :, 2], initial[:, :, 0])
        self.assertTrue(np.all(transformed[:, :, 0] == 0))
        mask = np.zeros((21, 25), dtype=bool)
        mask[8, 12] = True
        protected = build(mask=mask)
        np.testing.assert_array_equal(protected["arrays"]["displacement_xyz_m"][8, 12], [0, 0, 0])
        np.testing.assert_array_equal(protected["arrays"]["vertices_xyz_m"][8 * 25 + 12], chart()[8, 12])

    def test_readonly_roundtrip_and_tampering(self):
        result = build()
        for value in result["arrays"].values():
            self.assertFalse(value.flags.writeable)
            with self.assertRaises(ValueError):
                value.flat[0] = 3
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cliff.npz"
            save_vdm(path, result)
            restored = load_vdm(path, expected_sha256=file_sha256(path),
                                expected_identity=result["identity_sha256"])
            for key in result["arrays"]:
                np.testing.assert_array_equal(restored["arrays"][key], result["arrays"][key])
                self.assertFalse(restored["arrays"][key].flags.writeable)
            with self.assertRaises(ValueError):
                load_vdm(path, expected_sha256="0" * 64, expected_identity=result["identity_sha256"])
            with self.assertRaises(ValueError):
                load_vdm(path, expected_sha256=file_sha256(path), expected_identity="0" * 64)
        changed = {**result, "arrays": {**result["arrays"], "vertices_xyz_m":
                                  result["arrays"]["vertices_xyz_m"].copy()}}
        changed["arrays"]["vertices_xyz_m"][0, 1] += 1
        with self.assertRaises(ValueError):
            validate_vdm(changed)

    def test_rejects_bad_inputs_and_boundary_collision(self):
        with self.assertRaises(ValueError):
            build(chart()[:, :, :2])
        with self.assertRaises(ValueError):
            build(mask=np.zeros((21, 25), dtype=np.uint8))
        with self.assertRaises(ValueError):
            build(mask=np.zeros((20, 25), dtype=bool))
        nonfinite = chart()
        nonfinite[10, 12, 1] = np.nan
        with self.assertRaises(ValueError):
            build(nonfinite)
        narrow = chart()[:, 5:20]
        with self.assertRaisesRegex(ValueError, "perimeter"):
            build(narrow)
        flat_cell = chart()
        flat_cell[10, 12] = flat_cell[10, 13]
        with self.assertRaisesRegex(ValueError, "degenerate"):
            build(flat_cell)
        with self.assertRaises(ValueError):
            recipe(outward=(0, 0))


if __name__ == "__main__":
    unittest.main()
