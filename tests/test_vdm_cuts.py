"""Consolidated test_vdm_cuts implementations; numeric expressions preserved."""
from __future__ import annotations
import tempfile as _i39_tempfile
import unittest as _i39_unittest
from pathlib import Path as _i39_Path
import numpy as _i39_np
from terrain_pipeline.vdm_cuts import CliffRecipe as _i39_CliffRecipe
from terrain_pipeline.vdm_cuts import build_vdm as _i39_build_vdm
from terrain_pipeline.vdm_cuts import load_vdm as _i39_load_vdm
from terrain_pipeline.vdm_cuts import save_vdm as _i39_save_vdm
from terrain_pipeline.vdm_cuts import validate_vdm as _i39_validate_vdm
from terrain_pipeline.common_infra import file_sha256 as _i39_file_sha256
import tempfile as _i40_tempfile
import unittest as _i40_unittest
from pathlib import Path as _i40_Path
import numpy as _i40_np
from terrain_pipeline.vdm_cuts import apply_fault as _i40_apply_fault
from terrain_pipeline.vdm_cuts import load_fault as _i40_load_fault
from terrain_pipeline.vdm_cuts import save_fault as _i40_save_fault
from terrain_pipeline.vdm_cuts import validate_fault as _i40_validate_fault
from terrain_pipeline.common_infra import file_sha256 as _i40_file_sha256
from terrain_pipeline.common_infra import identity as _i40_identity
from tests.metric_vdm_fault_fixtures import source as _i40_source
from tests.metric_vdm_fault_fixtures import selection as _i40_selection
from tests.metric_vdm_fault_fixtures import recipe as _i40_recipe
import json as _i41_json
import tempfile as _i41_tempfile
import unittest as _i41_unittest
from dataclasses import asdict as _i41_asdict
from pathlib import Path as _i41_Path
import numpy as _i41_np
from terrain_pipeline.vdm_cuts import CliffRecipe as _i41_CliffRecipe
from terrain_pipeline.vdm_cuts import build_vdm as _i41_build_vdm
from terrain_pipeline.vdm_cuts import KINDS as _i41_KINDS
from terrain_pipeline.vdm_cuts import FormRecipe as _i41_FormRecipe
from terrain_pipeline.vdm_cuts import build_formed_vdm as _i41_build_formed_vdm
from terrain_pipeline.vdm_cuts import load_formed_vdm as _i41_load_formed_vdm
from terrain_pipeline.vdm_cuts import save_formed_vdm as _i41_save_formed_vdm
from terrain_pipeline.vdm_cuts import validate_formed_vdm as _i41_validate_formed_vdm
from terrain_pipeline.common_infra import file_sha256 as _i41_file_sha256
import unittest as _i42_unittest
import numpy as _i42_np
from terrain_pipeline.vdm_cuts import channel_protection as _i42_channel_protection
from terrain_pipeline.vdm_cuts import reject_protected_sweep as _i42_reject_protected_sweep
from terrain_pipeline.td_native_channel_geometry import build_channel_geometry as _i42_build_channel_geometry
from terrain_pipeline.td_native_channel_tiles import build_channel_tile as _i42_build_channel_tile
from terrain_pipeline.td_native_channel_tiles import split_window_2x2 as _i42_split_window_2x2
from terrain_pipeline.td_native_channel_surface import build_channel_surface as _i42_build_channel_surface
from tests.test_td_native_channel_geometry import fixture as _i42_fixture
CATEGORY = 'C'

def chart(*, elevation=0, center=(0, 0), outward=(1, 0)):
    rows, cols = (21, 25)
    row, col = _i39_np.indices((rows, cols))
    normal = _i39_np.array(outward, dtype=float)
    normal /= _i39_np.linalg.norm(normal)
    along = _i39_np.array((normal[1], -normal[0]))
    u = col - cols // 2
    v = row - rows // 2
    reference = _i39_np.empty((rows, cols, 3), dtype=float)
    reference[:, :, 0] = center[0] + u * along[0] + v * normal[0]
    reference[:, :, 1] = elevation
    reference[:, :, 2] = center[1] + u * along[1] + v * normal[1]
    return reference

def recipe(*, angle=60, lean=1, center=(0, 0), outward=(1, 0)):
    return _i39_CliffRecipe(center_xz_m=center, outward_xz=outward, height_m=12, half_length_m=8, half_depth_m=7, wall_half_width_m=2, end_fade_m=2, angle_degrees=angle, lean=lean)

def build(reference=None, settings=None, mask=None):
    reference = chart() if reference is None else reference
    settings = recipe() if settings is None else settings
    mask = _i39_np.zeros(reference.shape[:2], dtype=bool) if mask is None else mask
    return _i39_build_vdm(reference, recipe=settings, protected_mask=mask, source_identity='source-1', protection_identity='mask-1')

class MetricVdmTests(_i39_unittest.TestCase):

    def test_java_skeleton_center_and_wall_edges(self):
        for angle in (60, 90):
            for lean in (-1, 1):
                with self.subTest(angle=angle, lean=lean):
                    result = build(settings=recipe(angle=angle, lean=lean))
                    delta = result['arrays']['displacement_xyz_m']
                    _i39_np.testing.assert_allclose(delta[10, 12], [0, 0, 0], atol=1e-12)
                    offset = lean * 12 / _i39_np.tan(_i39_np.deg2rad(angle))
                    _i39_np.testing.assert_allclose(delta[8, 12], [offset / 2 + 2, 6, 0], atol=1e-12)
                    _i39_np.testing.assert_allclose(delta[12, 12], [-offset / 2 - 2, -6, 0], atol=1e-12)
                    self.assertFalse(delta[0].any())
                    self.assertFalse(delta[-1].any())

    def test_overhang_keeps_full_xyz_and_downward_faces(self):
        result = build(settings=recipe(angle=60, lean=1))
        arrays = result['arrays']
        self.assertTrue(_i39_np.any(arrays['displacement_xyz_m'][:, :, 0] != 0))
        self.assertTrue(_i39_np.any(arrays['displacement_xyz_m'][:, :, 1] != 0))
        vertices = arrays['vertices_xyz_m']
        points = vertices[arrays['triangles']]
        normals = _i39_np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        self.assertTrue(_i39_np.any(normals[:, 1] < 0))
        self.assertTrue(_i39_validate_vdm(result))

    def test_translation_rotation_and_protection(self):
        center = (103, -57)
        outward = (0, 1)
        baseline = build()
        rotated = build(chart(elevation=213, center=center, outward=outward), recipe(center=center, outward=outward))
        initial = baseline['arrays']['displacement_xyz_m']
        transformed = rotated['arrays']['displacement_xyz_m']
        _i39_np.testing.assert_allclose(transformed[:, :, 1], initial[:, :, 1])
        _i39_np.testing.assert_allclose(transformed[:, :, 2], initial[:, :, 0])
        self.assertTrue(_i39_np.all(transformed[:, :, 0] == 0))
        mask = _i39_np.zeros((21, 25), dtype=bool)
        mask[8, 12] = True
        protected = build(mask=mask)
        _i39_np.testing.assert_array_equal(protected['arrays']['displacement_xyz_m'][8, 12], [0, 0, 0])
        _i39_np.testing.assert_array_equal(protected['arrays']['vertices_xyz_m'][8 * 25 + 12], chart()[8, 12])

    def test_readonly_roundtrip_and_tampering(self):
        result = build()
        for value in result['arrays'].values():
            self.assertFalse(value.flags.writeable)
            with self.assertRaises(ValueError):
                value.flat[0] = 3
        with _i39_tempfile.TemporaryDirectory() as folder:
            path = _i39_Path(folder) / 'cliff.npz'
            _i39_save_vdm(path, result)
            restored = _i39_load_vdm(path, expected_sha256=_i39_file_sha256(path), expected_identity=result['identity_sha256'])
            for key in result['arrays']:
                _i39_np.testing.assert_array_equal(restored['arrays'][key], result['arrays'][key])
                self.assertFalse(restored['arrays'][key].flags.writeable)
            with self.assertRaises(ValueError):
                _i39_load_vdm(path, expected_sha256='0' * 64, expected_identity=result['identity_sha256'])
            with self.assertRaises(ValueError):
                _i39_load_vdm(path, expected_sha256=_i39_file_sha256(path), expected_identity='0' * 64)
        changed = {**result, 'arrays': {**result['arrays'], 'vertices_xyz_m': result['arrays']['vertices_xyz_m'].copy()}}
        changed['arrays']['vertices_xyz_m'][0, 1] += 1
        with self.assertRaises(ValueError):
            _i39_validate_vdm(changed)

    def test_rejects_bad_inputs_and_boundary_collision(self):
        with self.assertRaises(ValueError):
            build(chart()[:, :, :2])
        with self.assertRaises(ValueError):
            build(mask=_i39_np.zeros((21, 25), dtype=_i39_np.uint8))
        with self.assertRaises(ValueError):
            build(mask=_i39_np.zeros((20, 25), dtype=bool))
        nonfinite = chart()
        nonfinite[10, 12, 1] = _i39_np.nan
        with self.assertRaises(ValueError):
            build(nonfinite)
        narrow = chart()[:, 5:20]
        with self.assertRaisesRegex(ValueError, 'perimeter'):
            build(narrow)
        flat_cell = chart()
        flat_cell[10, 12] = flat_cell[10, 13]
        with self.assertRaisesRegex(ValueError, 'degenerate'):
            build(flat_cell)
        with self.assertRaises(ValueError):
            recipe(outward=(0, 0))

class DeformedFaultTests(_i40_unittest.TestCase):

    def test_zero_slip_keeps_deformed_source_not_original_chart(self):
        original = _i40_source()
        result = _i40_apply_fault(original, recipe=_i40_recipe(slip=0.0), selection_mask=_i40_selection())
        arrays = result['arrays']
        exact = arrays['vertex_source_index'] >= 0
        source_index = arrays['vertex_source_index'][exact]
        _i40_np.testing.assert_allclose(arrays['vertices_xyz_m'][exact], original['arrays']['vertices_xyz_m'][source_index])
        self.assertGreater(_i40_np.max(_i40_np.abs(original['arrays']['vertices_xyz_m'] - original['arrays']['reference_xyz_m'].reshape(-1, 3))), 1.0)
        _i40_np.testing.assert_array_equal(arrays['source_vertices_xyz_m'], original['arrays']['vertices_xyz_m'])

    def test_edge_interpolation_is_independent_of_triangle_vertex_order(self):
        original = _i40_source()
        result = _i40_apply_fault(original, recipe=_i40_recipe(strike=18.0), selection_mask=_i40_selection())
        arrays = result['arrays']
        edges = arrays['vertex_source_edge']
        fraction = arrays['vertex_source_fraction'][:, None]
        before = original['arrays']['vertices_xyz_m'][edges[:, 0]] * (1.0 - fraction) + original['arrays']['vertices_xyz_m'][edges[:, 1]] * fraction
        _i40_np.testing.assert_allclose(arrays['vertices_xyz_m'] - arrays['applied_displacement_xyz_m'], before, atol=1e-10)
        self.assertGreater(_i40_np.count_nonzero(arrays['vertex_source_index'] < 0), 0)
        self.assertLess(result['metadata']['cut_source_triangle_count'], len(original['arrays']['triangles']))

    def test_negative_slip_and_saved_cold_read(self):
        original = _i40_source()
        result = _i40_apply_fault(original, recipe=_i40_recipe(slip=-2.0, strike=18.0), selection_mask=_i40_selection())
        with _i40_tempfile.TemporaryDirectory() as folder:
            path = _i40_Path(folder) / 'fault.npz'
            _i40_save_fault(path, result)
            loaded = _i40_load_fault(path, expected_sha256=_i40_file_sha256(path), expected_identity=result['identity_sha256'])
            self.assertTrue(_i40_validate_fault(loaded))
            self.assertTrue(all((not value.flags.writeable for value in loaded['arrays'].values())))

    def test_geometry_erasure_rejected_even_with_updated_identity(self):
        result = _i40_apply_fault(_i40_source(), recipe=_i40_recipe(), selection_mask=_i40_selection())
        arrays = {key: value.copy() for key, value in result['arrays'].items()}
        arrays['vertices_xyz_m'][0, 1] += 1.0
        corrupted = {'arrays': arrays, 'metadata': result['metadata'], 'identity_sha256': _i40_identity(arrays, result['metadata'])}
        with self.assertRaisesRegex(ValueError, 'erased source'):
            _i40_validate_fault(corrupted)

    def test_swept_patch_protection_is_not_just_selection_protection(self):
        protected = _i40_np.zeros((25, 25), bool)
        protected[15, 22] = True
        original = _i40_source(protected=protected)
        self.assertFalse(_i40_np.any(_i40_selection() & protected))
        with self.assertRaisesRegex(ValueError, 'swept'):
            _i40_apply_fault(original, recipe=_i40_recipe(slip=12.0), selection_mask=_i40_selection())

def _test_metric_vdm_forms_chart(center=(0, 0), outward=(1, 0)):
    row, col = _i41_np.indices((33, 33))
    direction = _i41_np.asarray(outward, dtype=float)
    direction /= _i41_np.linalg.norm(direction)
    along = _i41_np.array((direction[1], -direction[0]))
    horizontal = (row - 16)[..., None] * direction + (col - 16)[..., None] * along
    reference = _i41_np.zeros((33, 33, 3), dtype=float)
    reference[:, :, 0] = center[0] + horizontal[:, :, 0]
    reference[:, :, 2] = center[1] + horizontal[:, :, 1]
    return reference

def cliff(center=(0, 0), outward=(1, 0)):
    return _i41_CliffRecipe(center_xz_m=center, outward_xz=outward, height_m=8, half_length_m=8, half_depth_m=10, wall_half_width_m=3, end_fade_m=2, angle_degrees=75, lean=1)

def _test_metric_vdm_forms_build(kind='fluted_wall', *, seed=20261003, reference=None, recipe=None, mask=None, curvature=0, end_difference=0, direction=None):
    reference = _test_metric_vdm_forms_chart() if reference is None else reference
    recipe = cliff() if recipe is None else recipe
    mask = _i41_np.zeros(reference.shape[:2], dtype=bool) if mask is None else mask
    return _i41_build_formed_vdm(reference, recipe=recipe, form=_i41_FormRecipe(kind, 1.5, 6, seed, curvature, end_difference, direction), protected_mask=mask, source_identity='source-1', protection_identity='mask-1')

class MetricVdmFormsTests(_i41_unittest.TestCase):

    def test_six_distinct_shapes_and_seed(self):
        results = {kind: _test_metric_vdm_forms_build(kind) for kind in _i41_KINDS}
        forms = [result['arrays']['displacement_xyz_m'] for result in results.values()]
        self.assertEqual(len({value.tobytes() for value in forms}), 6)
        for result in results.values():
            self.assertTrue(_i41_validate_formed_vdm(result))
            self.assertFalse(result['arrays']['vertices_xyz_m'].flags.writeable)
        self.assertEqual(_test_metric_vdm_forms_build()['identity_sha256'], _test_metric_vdm_forms_build()['identity_sha256'])
        self.assertNotEqual(_test_metric_vdm_forms_build(seed=1)['identity_sha256'], _test_metric_vdm_forms_build(seed=2)['identity_sha256'])
        self.assertFalse(_i41_np.array_equal(_test_metric_vdm_forms_build(seed=1)['arrays']['displacement_xyz_m'], _test_metric_vdm_forms_build(seed=2)['arrays']['displacement_xyz_m']))
        base = _i41_build_vdm(_test_metric_vdm_forms_chart(), recipe=cliff(), protected_mask=_i41_np.zeros((33, 33), bool), source_identity='source-1', protection_identity='mask-1')
        self.assertEqual(results['fluted_wall']['metadata']['base_identity_sha256'], base['identity_sha256'])
        self.assertFalse(_i41_np.array_equal(results['curved_escarpment']['arrays']['displacement_xyz_m'][10, 11], results['curved_escarpment']['arrays']['displacement_xyz_m'][10, 15]))

    def test_rotation_translation_edges_and_protection(self):
        baseline = _test_metric_vdm_forms_build()
        center = (110, -230)
        rotated = _test_metric_vdm_forms_build(reference=_test_metric_vdm_forms_chart(center, (0, 1)), recipe=cliff(center, (0, 1)))
        first = baseline['arrays']['displacement_xyz_m']
        second = rotated['arrays']['displacement_xyz_m']
        _i41_np.testing.assert_allclose(first[:, :, 1], second[:, :, 1])
        _i41_np.testing.assert_allclose(first[:, :, 0], second[:, :, 2])
        _i41_np.testing.assert_allclose(second[:, :, 0], 0, atol=1e-12)
        mask = _i41_np.zeros((33, 33), dtype=bool)
        mask[13, 13] = True
        protected = _test_metric_vdm_forms_build(mask=mask)['arrays']
        self.assertFalse(_i41_np.any(protected['displacement_xyz_m'][mask]))
        for edge in (protected['displacement_xyz_m'][0], protected['displacement_xyz_m'][-1], protected['displacement_xyz_m'][:, 0], protected['displacement_xyz_m'][:, -1]):
            self.assertFalse(_i41_np.any(edge))
        _i41_np.testing.assert_array_equal(protected['triangles'], baseline['arrays']['triangles'])

    def test_curvature_sign_and_bounded_profile(self):
        base = _test_metric_vdm_forms_build()['arrays']['displacement_xyz_m']
        convex = _test_metric_vdm_forms_build(curvature=1)['arrays']['displacement_xyz_m']
        concave = _test_metric_vdm_forms_build(curvature=-1)['arrays']['displacement_xyz_m']
        _i41_np.testing.assert_allclose(convex[:, :, 0] - base[:, :, 0], -(concave[:, :, 0] - base[:, :, 0]))
        self.assertAlmostEqual(convex[16, 16, 0] - base[16, 16, 0], 1)
        self.assertAlmostEqual(concave[16, 16, 0] - base[16, 16, 0], -1)
        self.assertAlmostEqual(convex[19, 16, 0] - base[19, 16, 0], 0)
        self.assertFalse(_i41_np.any(convex[0] - base[0]))

    def test_inner_end_difference_and_outer_collar(self):
        baseline = _test_metric_vdm_forms_build()['arrays']['displacement_xyz_m']
        raised = _test_metric_vdm_forms_build(end_difference=2)['arrays']['displacement_xyz_m']
        added = raised - baseline
        self.assertAlmostEqual(added[16, 22, 1] - added[16, 10, 1], 2)
        self.assertAlmostEqual(added[16, 22, 1], 1)
        self.assertAlmostEqual(added[16, 10, 1], -1)
        self.assertFalse(_i41_np.any(added[:, 8]))
        self.assertFalse(_i41_np.any(added[:, 24]))
        self.assertFalse(_i41_np.any(added[:, :, (0, 2)]))

    def test_explicit_direction_rotates_skeleton_and_controls(self):
        first = _test_metric_vdm_forms_build(reference=_test_metric_vdm_forms_chart(outward=(0, 1)), curvature=1, end_difference=2, direction=0)
        center = (100, -60)
        second = _test_metric_vdm_forms_build(reference=_test_metric_vdm_forms_chart(center, (-1, 0)), recipe=cliff(center), curvature=1, end_difference=2, direction=90)
        original = first['arrays']['displacement_xyz_m']
        turned = second['arrays']['displacement_xyz_m']
        _i41_np.testing.assert_allclose(turned[:, :, 0], -original[:, :, 2], atol=1e-12)
        _i41_np.testing.assert_allclose(turned[:, :, 2], original[:, :, 0], atol=1e-12)
        _i41_np.testing.assert_allclose(turned[:, :, 1], original[:, :, 1], atol=1e-12)
        normalized = _test_metric_vdm_forms_build(curvature=1, end_difference=2, direction=450)
        self.assertEqual(normalized['metadata']['recipe']['outward_xz'], second['metadata']['recipe']['outward_xz'])
        mask = _i41_np.zeros((33, 33), dtype=bool)
        mask[16, 16] = True
        self.assertFalse(_i41_np.any(_test_metric_vdm_forms_build(curvature=1, end_difference=2, direction=90, reference=_test_metric_vdm_forms_chart(outward=(-1, 0)), mask=mask)['arrays']['displacement_xyz_m'][mask]))

    def test_rejects_curvature_beyond_wavelength(self):
        with self.assertRaises(ValueError):
            _i41_FormRecipe('fluted_wall', 1.0, 6, 1, surface_curvature_m=3.1)

    def test_roundtrip_and_tampering(self):
        result = _test_metric_vdm_forms_build()
        with _i41_tempfile.TemporaryDirectory() as folder:
            path = _i41_Path(folder) / 'form.npz'
            _i41_save_formed_vdm(path, result)
            loaded = _i41_load_formed_vdm(path, expected_sha256=_i41_file_sha256(path), expected_identity=result['identity_sha256'])
            for key in result['arrays']:
                _i41_np.testing.assert_array_equal(loaded['arrays'][key], result['arrays'][key])
            with self.assertRaises(ValueError):
                _i41_load_formed_vdm(path, expected_sha256='0' * 64, expected_identity=result['identity_sha256'])
            with self.assertRaises(ValueError):
                _i41_load_formed_vdm(path, expected_sha256=_i41_file_sha256(path), expected_identity='0' * 64)
        changed = {**result, 'arrays': {**result['arrays'], 'vertices_xyz_m': result['arrays']['vertices_xyz_m'].copy()}}
        changed['arrays']['vertices_xyz_m'][0, 1] += 1
        with self.assertRaises(ValueError):
            _i41_validate_formed_vdm(changed)

    def test_v1_identity_and_v2_roundtrip(self):
        legacy = _test_metric_vdm_forms_build()
        self.assertEqual(legacy['metadata']['schema'], 'metric-vdm-forms-v1')
        self.assertEqual(set(legacy['metadata']['form']), {'kind', 'amplitude_m', 'wavelength_m', 'seed'})
        self.assertEqual(legacy['identity_sha256'], _test_metric_vdm_forms_build()['identity_sha256'])
        modern = _test_metric_vdm_forms_build(curvature=1, end_difference=2, direction=0)
        self.assertEqual(modern['metadata']['schema'], 'metric-vdm-forms-v2')
        self.assertEqual(modern['metadata']['form'], _i41_asdict(_i41_FormRecipe('fluted_wall', 1.5, 6, 20261003, 1, 2, 0)))
        with _i41_tempfile.TemporaryDirectory() as folder:
            for name, result in (('v1', legacy), ('v2', modern)):
                with self.subTest(version=name):
                    path = _i41_Path(folder) / (name + '.npz')
                    _i41_save_formed_vdm(path, result)
                    loaded = _i41_load_formed_vdm(path, expected_sha256=_i41_file_sha256(path), expected_identity=result['identity_sha256'])
                    self.assertEqual(loaded['metadata'], _i41_json.loads(_i41_json.dumps(result['metadata'])))
                    self.assertEqual(loaded['identity_sha256'], result['identity_sha256'])
        forged = {**modern, 'metadata': {**modern['metadata'], 'form': {**modern['metadata']['form'], 'extension_direction_degrees': 90}}}
        with self.assertRaises(ValueError):
            _i41_validate_formed_vdm(forged)
        wrong_version = {**modern, 'metadata': {**modern['metadata'], 'schema': 'metric-vdm-forms-v1', 'algorithm': 'coherent-cliff-forms-v1'}}
        with self.assertRaises(ValueError):
            _i41_validate_formed_vdm(wrong_version)

    def test_rejects_invalid_parameters_and_sampling(self):
        for kind, amplitude, wavelength, seed in (('unknown', 1, 6, 1), ('fluted_wall', float('nan'), 6, 1), ('fluted_wall', 1, 0, 1), ('fluted_wall', 1, 6, -1)):
            with self.assertRaises(ValueError):
                _i41_FormRecipe(kind, amplitude, wavelength, seed)
        for amplitude, wavelength in ((2.1, 6), (1.5, 3.9)):
            with self.assertRaises(ValueError):
                _i41_build_formed_vdm(_test_metric_vdm_forms_chart(), recipe=cliff(), form=_i41_FormRecipe('fluted_wall', amplitude, wavelength, 1), protected_mask=_i41_np.zeros((33, 33), dtype=bool), source_identity='s', protection_identity='p')
        bad = _test_metric_vdm_forms_chart()
        bad[13, 13, 1] = _i41_np.inf
        with self.assertRaises(ValueError):
            _test_metric_vdm_forms_build(reference=bad)
        for controls in ({'curvature': float('inf')}, {'direction': float('nan')}, {'end_difference': 9}, {'curvature': 3.1}):
            with self.assertRaises(ValueError):
                _test_metric_vdm_forms_build(**controls)
        narrow_fade = _i41_CliffRecipe(center_xz_m=(0, 0), outward_xz=(1, 0), height_m=8, half_length_m=8, half_depth_m=10, wall_half_width_m=3, end_fade_m=8, angle_degrees=75, lean=1)
        with self.assertRaises(ValueError):
            _test_metric_vdm_forms_build(recipe=narrow_fade, end_difference=1)

class ChannelVdmTests(_i42_unittest.TestCase):

    def test_swept_face_cannot_jump_across_protected_river(self):
        rows, columns = _i42_np.mgrid[:7, :7]
        reference = _i42_np.stack((columns, _i42_np.zeros_like(rows), rows), axis=-1).astype(float)
        displaced = reference.reshape(-1, 3).copy()
        protected = _i42_np.zeros((7, 7), bool)
        protected[:, 3] = True
        triangles = _i42_np.array([[8, 15, 16]])
        displaced[triangles.ravel(), 0] += 4
        with self.assertRaisesRegex(ValueError, 'protected'):
            _i42_reject_protected_sweep(reference, displaced, triangles, protected)
        displaced = reference.reshape(-1, 3).copy()
        displaced[triangles.ravel(), 1] += 1
        _i42_reject_protected_sweep(reference, displaced, triangles, protected)

    def test_mask_keeps_cut_and_source_link(self):
        hierarchy, page = _i42_fixture()
        geometry = _i42_build_channel_geometry(hierarchy, page)
        tiles = [_i42_build_channel_tile(geometry, window=window) for window in _i42_split_window_2x2((0, 60, 0, 60))]
        surface = _i42_build_channel_surface(tiles, geometry=geometry)
        mask = _i42_channel_protection(surface, hierarchy)
        self.assertTrue(mask[surface['arrays']['candidate_cut_m'].reshape(mask.shape) > 0].all())
        self.assertFalse(mask.flags.writeable)
        surface['metadata']['hierarchy_identity'] = '0' * 64
        with self.assertRaises(ValueError):
            _i42_channel_protection(surface, hierarchy)
