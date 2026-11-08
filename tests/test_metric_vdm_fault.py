"""Explicit replay tests for the archived first metric VDM fault API.

The original test bytes and implementation are hash-pinned in legacy-code.
Current generation and current fixture types live independently in v2.
"""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from terrain_pipeline.vdm_cuts import CliffRecipe, build_vdm
from tools.frozen_vdm_fault import load_legacy_api
_legacy = load_legacy_api()
FaultRecipe = _legacy.FaultRecipe
apply_fault = _legacy.apply_fault
load_fault = _legacy.load_fault
save_fault = _legacy.save_fault
validate_fault = _legacy.validate_fault
from terrain_pipeline.common_infra import file_sha256

def chart(angle_degrees=0.0):
    row, col = np.indices((25, 25))
    x = col.astype(float) - 12.0
    z = row.astype(float) - 12.0
    angle = np.deg2rad(angle_degrees)
    reference = np.zeros((25, 25, 3), dtype=float)
    reference[:, :, 0] = x * np.cos(angle) - z * np.sin(angle)
    reference[:, :, 2] = x * np.sin(angle) + z * np.cos(angle)
    reference[:, :, 1] = 30.0 + 0.04 * x + 0.02 * z
    return reference

def source(angle_degrees=0.0, protected=None):
    reference = chart(angle_degrees)
    if protected is None:
        protected = np.zeros(reference.shape[:2], dtype=bool)
    recipe = CliffRecipe(center_xz_m=(0.0, 0.0), outward_xz=(1.0, 0.0), height_m=6.0, half_length_m=7.0, half_depth_m=8.0, wall_half_width_m=3.0, end_fade_m=2.0, angle_degrees=75.0, lean=1)
    return build_vdm(reference, recipe=recipe, protected_mask=protected, source_identity='source-vdm-test', protection_identity='protection-test')

def selection():
    mask = np.zeros((25, 25), dtype=bool)
    mask[5:20, 5:20] = True
    return mask

def recipe(slip=2.0, strike=0.0, moving_side='positive', transition=3.0):
    return FaultRecipe(plane_origin_xz_m=(0.0, 0.0), strike_degrees=strike, slip_m=slip, moving_side=moving_side, transition_width_m=transition)

class MetricVdmFaultTests(unittest.TestCase):

    def build(self, *, slip=2.0, strike=0.0, moving_side='positive', transition=3.0, protected=None, angle_degrees=0.0):
        return apply_fault(source(angle_degrees, protected), recipe=recipe(slip, strike, moving_side, transition), selection_mask=selection())

    def test_zero_slip_preserves_surface_and_still_has_explicit_fault_contract(self):
        original = source()
        result = self.build(slip=0.0)
        self.assertTrue(validate_fault(result))
        self.assertEqual(result['metadata']['slip_m'], 0.0)
        self.assertEqual(result['metadata']['moving_side'], 'positive')
        self.assertGreaterEqual(result['arrays']['seam_edges'].shape[0], 1)
        self.assertTrue(np.isfinite(result['arrays']['vertices_xyz_m']).all())
        self.assertEqual(result['metadata']['source_identity'], original['identity_sha256'])

    def test_positive_and_negative_slip_move_only_the_selected_side(self):
        positive = self.build(slip=2.0)
        negative = self.build(slip=-2.0)
        self.assertNotEqual(positive['identity_sha256'], negative['identity_sha256'])
        for result in (positive, negative):
            displacement = result['arrays']['applied_displacement_xyz_m']
            self.assertTrue(np.isfinite(displacement).all())
            self.assertGreater(np.max(np.linalg.norm(displacement, axis=1)), 0.0)
            self.assertTrue(np.allclose(displacement[:, 1], 0.0, atol=1e-12))
            self.assertEqual(result['metadata']['slip_axis'], 'horizontal_strike')
        self.assertTrue(np.any(positive['arrays']['applied_displacement_xyz_m'] == -negative['arrays']['applied_displacement_xyz_m']))

    def test_strike_rotation_is_covariant(self):
        first = self.build(slip=1.75, strike=0.0, angle_degrees=0.0)
        turned = self.build(slip=1.75, strike=90.0, angle_degrees=90.0)
        a = first['arrays']['applied_displacement_xyz_m']
        b = turned['arrays']['applied_displacement_xyz_m']
        np.testing.assert_allclose(b[:, 1], a[:, 1])
        np.testing.assert_allclose(b[:, 0], -a[:, 2], atol=1e-10)
        np.testing.assert_allclose(b[:, 2], a[:, 0], atol=1e-10)

    def test_cut_mesh_has_no_triangle_crossing_the_open_seam(self):
        result = self.build(strike=0.0)
        vertices = result['arrays']['vertices_xyz_m']
        triangles = result['arrays']['triangles']
        sides = result['arrays']['vertex_side']
        triangle_sides = sides[triangles]
        self.assertFalse(np.any((triangle_sides.min(axis=1) < 0) & (triangle_sides.max(axis=1) > 0)))
        self.assertEqual(result['arrays']['triangle_source_index'].shape[0], triangles.shape[0])
        self.assertEqual(result['arrays']['vertex_source_index'].shape[0], vertices.shape[0])
        self.assertGreater(result['arrays']['seam_edges'].shape[0], 0)
        self.assertTrue(np.isfinite(vertices).all())
        self.assertLessEqual(np.max(np.linalg.norm(vertices, axis=1)), 100.0)

    def test_fixed_side_is_unchanged_and_transition_reaches_zero(self):
        result = self.build(slip=3.0)
        displacement = result['arrays']['applied_displacement_xyz_m']
        sides = result['arrays']['vertex_side']
        weights = result['arrays']['transition_weight']
        self.assertTrue(np.allclose(displacement[sides < 0], 0.0, atol=1e-12))
        self.assertTrue(np.all((weights >= 0.0) & (weights <= 1.0)))
        self.assertTrue(np.any(np.isclose(weights, 0.0)))
        self.assertTrue(np.any(np.isclose(weights, 1.0)))
        moving = displacement[sides > 0]
        self.assertGreater(np.max(np.linalg.norm(moving, axis=1)), 0.0)

    def test_invalid_plane_and_empty_selection_are_rejected(self):
        with self.assertRaises(ValueError):
            FaultRecipe((0.0, 0.0), float('nan'), 1.0, 'positive', 2.0)
        with self.assertRaises(ValueError):
            FaultRecipe((0.0, 0.0), 0.0, 1.0, 'positive', 0.0)
        with self.assertRaises(ValueError):
            apply_fault(source(), recipe=recipe(), selection_mask=np.zeros((25, 25), bool))
        with self.assertRaises(ValueError):
            apply_fault(source(), recipe=recipe(), selection_mask=np.ones((24, 25), bool))

    def test_protected_influence_is_rejected(self):
        protected = np.zeros((25, 25), dtype=bool)
        protected[12, 12] = True
        with self.assertRaises(ValueError):
            self.build(protected=protected, slip=4.0)

    def test_npz_roundtrip_is_readonly_and_tampering_is_rejected(self):
        result = self.build()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fault.npz'
            save_fault(path, result)
            loaded = load_fault(path, expected_sha256=file_sha256(path), expected_identity=result['identity_sha256'])
            self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])
            for key, value in result['arrays'].items():
                np.testing.assert_array_equal(loaded['arrays'][key], value)
                self.assertFalse(loaded['arrays'][key].flags.writeable)
            with self.assertRaises(ValueError):
                load_fault(path, expected_sha256='0' * 64, expected_identity=result['identity_sha256'])
            with self.assertRaises(ValueError):
                load_fault(path, expected_sha256=file_sha256(path), expected_identity='0' * 64)
            with self.assertRaises(ValueError):
                loaded['arrays']['vertices_xyz_m'].flat[0] = 9.0
if __name__ == '__main__':
    unittest.main()
