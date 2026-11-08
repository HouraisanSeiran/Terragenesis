"""Distinct coherent metric cliff forms and artifact contract tests."""

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

import numpy as np

from terrain_pipeline.vdm_cuts import CliffRecipe, build_vdm
from terrain_pipeline.vdm_cuts import KINDS, FormRecipe, build_formed_vdm, load_formed_vdm, save_formed_vdm, validate_formed_vdm
from terrain_pipeline.common_infra import file_sha256


def chart(center=(0, 0), outward=(1, 0)):
    row, col = np.indices((33, 33))
    direction = np.asarray(outward, dtype=float)
    direction /= np.linalg.norm(direction)
    along = np.array((direction[1], -direction[0]))
    horizontal = ((row - 16)[..., None] * direction +
                  (col - 16)[..., None] * along)
    reference = np.zeros((33, 33, 3), dtype=float)
    reference[:, :, 0] = center[0] + horizontal[:, :, 0]
    reference[:, :, 2] = center[1] + horizontal[:, :, 1]
    return reference


def cliff(center=(0, 0), outward=(1, 0)):
    return CliffRecipe(center_xz_m=center, outward_xz=outward, height_m=8,
                       half_length_m=8, half_depth_m=10, wall_half_width_m=3,
                       end_fade_m=2, angle_degrees=75, lean=1)


def build(kind="fluted_wall", *, seed=20261003, reference=None, recipe=None, mask=None,
          curvature=0, end_difference=0, direction=None):
    reference = chart() if reference is None else reference
    recipe = cliff() if recipe is None else recipe
    mask = np.zeros(reference.shape[:2], dtype=bool) if mask is None else mask
    return build_formed_vdm(reference, recipe=recipe,
                            form=FormRecipe(kind, 1.5, 6, seed, curvature, end_difference, direction),
                            protected_mask=mask,
                            source_identity="source-1", protection_identity="mask-1")


class MetricVdmFormsTests(unittest.TestCase):
    def test_six_distinct_shapes_and_seed(self):
        results = {kind: build(kind) for kind in KINDS}
        forms = [result["arrays"]["displacement_xyz_m"] for result in results.values()]
        self.assertEqual(len({value.tobytes() for value in forms}), 6)
        for result in results.values():
            self.assertTrue(validate_formed_vdm(result))
            self.assertFalse(result["arrays"]["vertices_xyz_m"].flags.writeable)
        self.assertEqual(build()["identity_sha256"], build()["identity_sha256"])
        self.assertNotEqual(build(seed=1)["identity_sha256"], build(seed=2)["identity_sha256"])
        self.assertFalse(np.array_equal(build(seed=1)["arrays"]["displacement_xyz_m"],
                                        build(seed=2)["arrays"]["displacement_xyz_m"]))
        base = build_vdm(chart(), recipe=cliff(), protected_mask=np.zeros((33, 33), bool),
                         source_identity="source-1", protection_identity="mask-1")
        self.assertEqual(results["fluted_wall"]["metadata"]["base_identity_sha256"],
                         base["identity_sha256"])
        self.assertFalse(np.array_equal(results["curved_escarpment"]["arrays"]["displacement_xyz_m"][10, 11],
                                        results["curved_escarpment"]["arrays"]["displacement_xyz_m"][10, 15]))

    def test_rotation_translation_edges_and_protection(self):
        baseline = build()
        center = (110, -230)
        rotated = build(reference=chart(center, (0, 1)), recipe=cliff(center, (0, 1)))
        first = baseline["arrays"]["displacement_xyz_m"]
        second = rotated["arrays"]["displacement_xyz_m"]
        np.testing.assert_allclose(first[:, :, 1], second[:, :, 1])
        np.testing.assert_allclose(first[:, :, 0], second[:, :, 2])
        np.testing.assert_allclose(second[:, :, 0], 0, atol=1e-12)
        mask = np.zeros((33, 33), dtype=bool)
        mask[13, 13] = True
        protected = build(mask=mask)["arrays"]
        self.assertFalse(np.any(protected["displacement_xyz_m"][mask]))
        for edge in (protected["displacement_xyz_m"][0], protected["displacement_xyz_m"][-1],
                     protected["displacement_xyz_m"][:, 0], protected["displacement_xyz_m"][:, -1]):
            self.assertFalse(np.any(edge))
        np.testing.assert_array_equal(protected["triangles"], baseline["arrays"]["triangles"])

    def test_curvature_sign_and_bounded_profile(self):
        base = build()["arrays"]["displacement_xyz_m"]
        convex = build(curvature=1)["arrays"]["displacement_xyz_m"]
        concave = build(curvature=-1)["arrays"]["displacement_xyz_m"]
        np.testing.assert_allclose(convex[:, :, 0] - base[:, :, 0],
                                   -(concave[:, :, 0] - base[:, :, 0]))
        self.assertAlmostEqual(convex[16, 16, 0] - base[16, 16, 0], 1)
        self.assertAlmostEqual(concave[16, 16, 0] - base[16, 16, 0], -1)
        self.assertAlmostEqual(convex[19, 16, 0] - base[19, 16, 0], 0)
        self.assertFalse(np.any(convex[0] - base[0]))

    def test_inner_end_difference_and_outer_collar(self):
        baseline = build()["arrays"]["displacement_xyz_m"]
        raised = build(end_difference=2)["arrays"]["displacement_xyz_m"]
        added = raised - baseline
        self.assertAlmostEqual(added[16, 22, 1] - added[16, 10, 1], 2)
        self.assertAlmostEqual(added[16, 22, 1], 1)
        self.assertAlmostEqual(added[16, 10, 1], -1)
        self.assertFalse(np.any(added[:, 8]))
        self.assertFalse(np.any(added[:, 24]))
        self.assertFalse(np.any(added[:, :, (0, 2)]))

    def test_explicit_direction_rotates_skeleton_and_controls(self):
        first = build(reference=chart(outward=(0, 1)), curvature=1,
                      end_difference=2, direction=0)
        center = (100, -60)
        second = build(reference=chart(center, (-1, 0)), recipe=cliff(center),
                       curvature=1, end_difference=2, direction=90)
        original = first["arrays"]["displacement_xyz_m"]
        turned = second["arrays"]["displacement_xyz_m"]
        np.testing.assert_allclose(turned[:, :, 0], -original[:, :, 2], atol=1e-12)
        np.testing.assert_allclose(turned[:, :, 2], original[:, :, 0], atol=1e-12)
        np.testing.assert_allclose(turned[:, :, 1], original[:, :, 1], atol=1e-12)
        normalized = build(curvature=1, end_difference=2, direction=450)
        self.assertEqual(normalized["metadata"]["recipe"]["outward_xz"],
                         second["metadata"]["recipe"]["outward_xz"])
        mask = np.zeros((33, 33), dtype=bool)
        mask[16, 16] = True
        self.assertFalse(np.any(build(curvature=1, end_difference=2, direction=90,
                                      reference=chart(outward=(-1, 0)), mask=mask)
                                ["arrays"]["displacement_xyz_m"][mask]))

    def test_rejects_curvature_beyond_wavelength(self):
        with self.assertRaises(ValueError):
            FormRecipe("fluted_wall", 1.0, 6, 1, surface_curvature_m=3.1)

    def test_roundtrip_and_tampering(self):
        result = build()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "form.npz"
            save_formed_vdm(path, result)
            loaded = load_formed_vdm(path, expected_sha256=file_sha256(path),
                                     expected_identity=result["identity_sha256"])
            for key in result["arrays"]:
                np.testing.assert_array_equal(loaded["arrays"][key], result["arrays"][key])
            with self.assertRaises(ValueError):
                load_formed_vdm(path, expected_sha256="0" * 64,
                                expected_identity=result["identity_sha256"])
            with self.assertRaises(ValueError):
                load_formed_vdm(path, expected_sha256=file_sha256(path), expected_identity="0" * 64)
        changed = {**result, "arrays": {**result["arrays"],
                                       "vertices_xyz_m": result["arrays"]["vertices_xyz_m"].copy()}}
        changed["arrays"]["vertices_xyz_m"][0, 1] += 1
        with self.assertRaises(ValueError):
            validate_formed_vdm(changed)

    def test_v1_identity_and_v2_roundtrip(self):
        legacy = build()
        self.assertEqual(legacy["metadata"]["schema"], "metric-vdm-forms-v1")
        self.assertEqual(set(legacy["metadata"]["form"]),
                         {"kind", "amplitude_m", "wavelength_m", "seed"})
        self.assertEqual(legacy["identity_sha256"], build()["identity_sha256"])
        modern = build(curvature=1, end_difference=2, direction=0)
        self.assertEqual(modern["metadata"]["schema"], "metric-vdm-forms-v2")
        self.assertEqual(modern["metadata"]["form"],
                         asdict(FormRecipe("fluted_wall", 1.5, 6, 20261003, 1, 2, 0)))
        with tempfile.TemporaryDirectory() as folder:
            for name, result in (("v1", legacy), ("v2", modern)):
                with self.subTest(version=name):
                    path = Path(folder) / (name + ".npz")
                    save_formed_vdm(path, result)
                    loaded = load_formed_vdm(path, expected_sha256=file_sha256(path),
                                             expected_identity=result["identity_sha256"])
                    self.assertEqual(loaded["metadata"], json.loads(json.dumps(result["metadata"])))
                    self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
        forged = {**modern, "metadata": {**modern["metadata"], "form":
                  {**modern["metadata"]["form"], "extension_direction_degrees": 90}}}
        with self.assertRaises(ValueError):
            validate_formed_vdm(forged)
        wrong_version = {**modern, "metadata": {**modern["metadata"],
                                                "schema": "metric-vdm-forms-v1",
                                                "algorithm": "coherent-cliff-forms-v1"}}
        with self.assertRaises(ValueError):
            validate_formed_vdm(wrong_version)

    def test_rejects_invalid_parameters_and_sampling(self):
        for kind, amplitude, wavelength, seed in (("unknown", 1, 6, 1),
                                                   ("fluted_wall", float("nan"), 6, 1),
                                                   ("fluted_wall", 1, 0, 1),
                                                   ("fluted_wall", 1, 6, -1)):
            with self.assertRaises(ValueError):
                FormRecipe(kind, amplitude, wavelength, seed)
        for amplitude, wavelength in ((2.1, 6), (1.5, 3.9)):
            with self.assertRaises(ValueError):
                build_formed_vdm(chart(), recipe=cliff(),
                                 form=FormRecipe("fluted_wall", amplitude, wavelength, 1),
                                 protected_mask=np.zeros((33, 33), dtype=bool),
                                 source_identity="s", protection_identity="p")
        bad = chart()
        bad[13, 13, 1] = np.inf
        with self.assertRaises(ValueError):
            build(reference=bad)
        for controls in ({"curvature": float("inf")}, {"direction": float("nan")},
                         {"end_difference": 9}, {"curvature": 3.1}):
            with self.assertRaises(ValueError):
                build(**controls)
        narrow_fade = CliffRecipe(center_xz_m=(0, 0), outward_xz=(1, 0),
                                  height_m=8, half_length_m=8, half_depth_m=10,
                                  wall_half_width_m=3, end_fade_m=8,
                                  angle_degrees=75, lean=1)
        with self.assertRaises(ValueError):
            build(recipe=narrow_fade, end_difference=1)


if __name__ == "__main__":
    unittest.main()
