"""Consolidated test_underground_rivers implementations; numeric expressions preserved."""
from __future__ import annotations
import copy as _i43_copy
import unittest as _i43_unittest
from unittest.mock import patch as _i43_patch
import numpy as _i43_np
from terrain_pipeline.artifacts.contracts import array_hash as _i43_array_hash
from terrain_pipeline.drainage import resolve_dem_flats as _i43_resolve_dem_flats
from terrain_pipeline.underground_rivers import _seal as _i43__seal
from terrain_pipeline.underground_rivers import build_river_geometry as _i43_build_river_geometry
from terrain_pipeline.underground_rivers import validate_river_geometry as _i43_validate_river_geometry
import json as _i44_json
import numpy as _i44_np
import pytest as _i44_pytest
from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i44_ArtifactIdentity
from terrain_pipeline.artifacts.contracts import array_hash as _i44_array_hash
from terrain_pipeline.underground_rivers import UndergroundRecipe as _i44_UndergroundRecipe
from terrain_pipeline.underground_rivers import load_underground as _i44_load_underground
from terrain_pipeline.underground_rivers import plan_underground as _i44_plan_underground
from terrain_pipeline.underground_rivers import save_underground as _i44_save_underground
from copy import deepcopy as _i46_deepcopy
from pathlib import Path as _i46_Path
import sys as _i46_sys
import time as _i46_time
import unittest as _i46_unittest
import numpy as _i46_np
from terrain_pipeline.hybrid_geometry import Parameters as _i46_CaveParameters
from terrain_pipeline.hybrid_geometry import build_charts as _i46_build_charts
from terrain_pipeline.hybrid_geometry import build_rock as _i46_build_rock
from terrain_pipeline.hybrid_geometry import identity as _i46_identity
from terrain_pipeline.underground_rivers import Parameters as _i46_Parameters
from terrain_pipeline.underground_rivers import build_preview as _i46_build_preview
from terrain_pipeline.underground_rivers import deform_charts as _i46_deform_charts
from tools.prepare_underground_rivers import prepare as _i46_prepare
from copy import deepcopy as _i45_deepcopy
from pathlib import Path as _i45_Path
import tempfile as _i45_tempfile
import unittest as _i45_unittest
from terrain_pipeline.underground_rivers import build_preview as _i45_build_preview
from tools.audit_underground_rivers import ROOT as _i45_ROOT
from tools.audit_underground_rivers import audit as _i45_audit
from tools.audit_underground_rivers import check_saved_geometry as _i45_check_saved_geometry
from tools.td_shared_channel_fine_saved_audit import digest as _i45_digest
CATEGORY = 'C'

def fixture(height):
    values = _i43_np.asarray(height, _i43_np.float64)
    candidate = {'arrays': {'height_m': values, 'valid_mask': _i43_np.isfinite(values), 'unknown_mask': ~_i43_np.isfinite(values)}, 'grid': {'origin_x_m': 400000.0, 'origin_z_m': -3200000.0, 'spacing_x_m': 90.0, 'spacing_z_m': 90.0, 'crs': 'EPSG:32651', 'units': 'metres'}}
    return (candidate, _i43_resolve_dem_flats(candidate))

class RealDemRiver3DAdapterTests(_i43_unittest.TestCase):

    def build(self, candidate, flat, **options):
        return _i43_build_river_geometry(candidate, flat, min_contributing_cells=1, **options)

    def test_y_junction_two_tributaries_shared_nodes_banks_and_profiles(self):
        candidate, flat = fixture([[9, 8, 9], [7, 5, 7], [6, 1, 6]])
        result = self.build(candidate, flat)
        receiver = flat['network'].receiver.ravel()
        sources = _i43_np.flatnonzero(receiver >= 0)
        _i43_np.testing.assert_array_equal(result['edges'], _i43_np.column_stack((sources, receiver[sources])))
        _i43_np.testing.assert_array_equal(result['edge_ids'], sources)
        donors = _i43_np.bincount(receiver[sources], minlength=9)
        _i43_np.testing.assert_array_equal(result['donor_count'], donors)
        _i43_np.testing.assert_array_equal(result['junctions'], donors > 1)
        _i43_np.testing.assert_array_equal(result['heads'], donors == 0)
        _i43_np.testing.assert_array_equal(result['terminals'], receiver < 0)
        self.assertGreaterEqual(donors[7], 2)
        self.assertEqual(result['vertices'].shape, (18, 3))
        for edge, faces in zip(result['edges'], result['faces'].reshape(-1, 2, 3)):
            self.assertEqual(set(faces.ravel()), {2 * edge[0], 2 * edge[0] + 1, 2 * edge[1], 2 * edge[1] + 1})
        _i43_np.testing.assert_array_equal(result['cross_sections'], _i43_np.tile([20.0, 1.0, 20.0], (9, 1)))
        _i43_np.testing.assert_array_equal(result['node_xyz'][:, 1], candidate['arrays']['height_m'].ravel())
        _i43_np.testing.assert_array_equal(result['vertices'][::2, 1], result['node_xyz'][:, 1] - 1.0)
        self.assertTrue(_i43_validate_river_geometry(candidate, flat, result)['verified'])
        self.assertFalse(result['metadata']['hydraulic_ready'])
        self.assertFalse(result['metadata']['continuous_water_body_verified'])

    def test_threshold_downstream_closure_and_empty_selection(self):
        candidate, flat = fixture([[4, 3, 2, 1]])
        result = _i43_build_river_geometry(candidate, flat, min_contributing_cells=3)
        self.assertEqual(result['node_ids'].tolist(), [2, 3])
        self.assertEqual(result['edges'].tolist(), [[2, 3]])
        self.assertTrue(_i43_validate_river_geometry(candidate, flat, result)['verified'])
        empty = _i43_build_river_geometry(candidate, flat, min_contributing_cells=100)
        self.assertEqual(empty['node_xyz'].shape, (0, 3))
        self.assertEqual(empty['faces'].shape, (0, 3))
        self.assertTrue(_i43_validate_river_geometry(candidate, flat, empty)['verified'])

    def test_tile_sizes_and_flat_loading_orders_exact_hashes(self):
        candidate, flat = fixture([[4, 4, 3, 2], [4, _i43_np.nan, 3, 1]])
        expected = self.build(candidate, flat, tile_size=1)
        for size in (2, 256, 512):
            flat = _i43_resolve_dem_flats(candidate, tile_size=size, tile_order='reversed')
            result = self.build(candidate, flat, tile_size=size)
            self.assertEqual(result['content_sha256'], expected['content_sha256'])
            self.assertEqual(result['array_hashes'], expected['array_hashes'])
            self.assertTrue(_i43_validate_river_geometry(candidate, flat, result)['verified'])

    def test_coordinates_explicit_grid_and_source_unchanged(self):
        candidate, flat = fixture([[3, 2], [_i43_np.nan, 1]])
        before = _i43_array_hash(candidate['arrays']['height_m'])
        result = self.build(candidate, flat, width_m=12.0, depth_m=2.0)
        _i43_np.testing.assert_array_equal(result['node_xyz'][:, 0], [400000.0, 400090.0, 400090.0])
        _i43_np.testing.assert_array_equal(result['node_xyz'][:, 2], [-3200000.0, -3200000.0, -3199910.0])
        self.assertEqual(_i43_array_hash(candidate['arrays']['height_m']), before)
        records = {item['component_id']: item for item in flat['components']}
        _i43_np.testing.assert_array_equal(result['touches_unknown'], [records[int(component)]['touches_unknown'] for component in result['component_id']])
        self.assertTrue(result['touches_unknown'].any())
        candidate['grid']['units'] = 'degrees'
        with self.assertRaises(ValueError):
            self.build(candidate, flat)

    def test_rehashed_array_class_edges_profile_mesh_and_claim_tampering_rejected(self):
        candidate, flat = fixture([[3, 2, 1]])
        original = self.build(candidate, flat)
        mutations = [lambda value: value['node_ids'].__setitem__(0, 1), lambda value: value['node_xyz'].__setitem__((0, 1), 100.0), lambda value: value['edges'].__setitem__((0, 1), 2), lambda value: value['junctions'].__setitem__(0, True), lambda value: value['touches_unknown'].__setitem__(0, True), lambda value: value['cross_sections'].__setitem__((0, 2), 99.0), lambda value: value['vertices'].__setitem__((0, 0), 99.0), lambda value: value['faces'].__setitem__((0, 0), 999), lambda value: value['faces'].__setitem__((0, 0), 1), lambda value: value['metadata'].update(hydraulic_ready=True), lambda value: value['metadata'].update(natural_outlet_verified=True)]
        for mutation in mutations:
            result = _i43_copy.deepcopy(original)
            mutation(result)
            _i43__seal(result)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _i43_validate_river_geometry(candidate, flat, result)
        altered = _i43_copy.deepcopy(flat)
        altered['network'].order[:] = altered['network'].order[::-1]
        with self.assertRaises(ValueError):
            _i43_validate_river_geometry(candidate, altered, original)

    def test_invalid_parameters_nonfinite_unknown_and_resource_budget(self):
        candidate, flat = fixture([[3, 2, 1]])
        for options in ({'width_m': True}, {'width_m': 0}, {'width_m': _i43_np.inf}, {'depth_m': -1}, {'depth_m': _i43_np.nan}, {'tile_size': True}, {'tile_size': 1025}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.build(candidate, flat, **options)
        for threshold in (True, 0, -1, _i43_np.inf, 500001):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                _i43_build_river_geometry(candidate, flat, min_contributing_cells=threshold)
        with self.assertRaises(ValueError):
            fixture([[_i43_np.nan]])
        huge = {'arrays': {'height_m': _i43_np.zeros((501, 1000)), 'valid_mask': _i43_np.ones((501, 1000), bool)}}
        with self.assertRaises(ValueError):
            self.build(huge, {})
        candidate['grid']['origin_x_m'] = _i43_np.inf
        with self.assertRaises(ValueError):
            self.build(candidate, flat)

    def test_validator_does_not_replay_builder(self):
        candidate, flat = fixture([[3, 2, 1]])
        result = self.build(candidate, flat)
        with _i43_patch('terrain_pipeline.underground_rivers.build_river_geometry', side_effect=AssertionError('no replay')):
            self.assertTrue(_i43_validate_river_geometry(candidate, flat, result)['verified'])

def _plan(shape=(5, 5)):
    h = _i44_np.full(shape, 20.0, dtype=_i44_np.float64)
    ident = _i44_ArtifactIdentity('Terragenesis', 'metric-channel-plan', 'metric-channel-plan-v1', 0, {'source_height_sha256': _i44_array_hash(h)})
    return {'status': 'diagnostic_not_publishable', 'identity': ident.record(), 'identity_sha256': ident.sha256, 'arrays': {'source_height_m': h}}

def test_paths_filters_and_explicit_exits(tmp_path):
    shape = (5, 5)
    domain = _i44_np.ones(shape, bool)
    protected = _i44_np.zeros(shape, bool)
    protected[1, 1] = True
    result = _i44_plan_underground(_plan(), _i44_np.zeros(shape), _i44_np.ones(shape), domain, protected, [[2, 1], [1, 1], [0, 0]], [{'grid_zx': [2, 3], 'type': 'surface_low'}, {'grid_zx': [2, 4], 'type': 'subsea'}], _i44_UndergroundRecipe(min_entry_score=0), _i44_np.full(shape, 10.0))
    assert result['summary']['accepted_entries'] == 2
    assert result['exits'][1]['type'] == 'subsea'
    assert result['edges'] and result['edges'][0]['path_grid_zx']
    assert result['preview_modes'] == ['surface_only', 'underground_only', 'overlay']
    path = tmp_path / 'u.npz'
    _i44_save_underground(result, path)
    loaded = _i44_load_underground(path)
    assert loaded['identity_sha256'] == result['identity_sha256']
    with _i44_np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files if k != 'manifest'}
        manifest = str(z['manifest'].item())
    arrays['score_m'] = arrays['score_m'].copy()
    arrays['score_m'][0, 0] += 1
    _i44_np.savez_compressed(path, manifest=manifest, **arrays)
    with _i44_pytest.raises(ValueError):
        _i44_load_underground(path)

def test_cover_is_required_and_grayscale_only_changes_ranking():
    shape = (3, 3)
    masks = (_i44_np.ones(shape, bool), _i44_np.zeros(shape, bool))
    with _i44_pytest.raises(ValueError):
        _i44_plan_underground(_plan(shape), _i44_np.zeros(shape), _i44_np.ones(shape), *masks, [[1, 1]], [{'grid_zx': [1, 2], 'type': 'surface_low'}])
    kwargs = dict(surface_plan=_plan(shape), lithology_reference=_i44_np.ones(shape), domain_mask=masks[0], protected_mask=masks[1], entries=[[1, 0]], exits=[{'grid_zx': [1, 2], 'type': 'surface_low'}], recipe=_i44_UndergroundRecipe(min_entry_score=0), cover_reference=_i44_np.full(shape, 10.0))
    a = _i44_plan_underground(grayscale_reference=_i44_np.zeros(shape), **kwargs)
    b = _i44_plan_underground(grayscale_reference=_i44_np.full(shape, 9.0), **kwargs)
    assert _i44_np.array_equal(a['arrays']['accepted_entry_mask'], b['arrays']['accepted_entry_mask'])
    assert not _i44_np.array_equal(a['arrays']['score_m'], b['arrays']['score_m'])
ROOT = _i46_Path(__file__).resolve().parents[1]
_i46_sys.path.insert(0, str(ROOT / '.scratch/hybrid-river-network/python-deps'))

def port_at(z_m):
    profile = [[2.0, 0.0, z_m], [1.0, 0.0, z_m], [-1.0, 0.0, z_m], [-2.0, 0.0, z_m]]
    return {'status': 'candidate', 'rejection_reasons': [], 'flow_unit_xz': [0.0, 1.0], 'profile': {'profile_xyz_m': profile, 'profile_segments': [{'profile_segment_index': ordinal, 'points_xyz_m': [first, second], 'native_pieces': [{'interval_t01': [0.0, 1.0], 'start_xz_m': [first[0], z_m], 'end_xz_m': [second[0], z_m], 'depth_coefficients_m_t01': [0.0, 0.0], 'source': {'source_coefficients_m_t012': [0.0, 0.0, 0.0]}}]} for ordinal, (first, second) in enumerate(zip(profile, profile[1:]))]}}

def flat_sampler(point):
    return {'derived_bed_m': 0.0, 'source_sample': {'height_m': 0.0}, 'cut_depth_m': 0.0, 'fan_keys': []}

class UndergroundRiverTests(_i46_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        parameters = _i46_CaveParameters(stations=9, crop_margin_m=4.0)
        cls.vdm = _i46_build_charts(port_at(0.0), port_at(60.0), [0.0, 0.0, 0.0], [0.0, 0.0, 60.0], parameters)
        cls.rock, _ = _i46_build_rock(cls.vdm, flat_sampler, parameters, _i46_np.zeros(3))

    def test_seed_fixed_endpoints_reference_and_source_immutability(self):
        original = _i46_deepcopy(self.vdm)
        first = _i46_deform_charts(self.vdm, _i46_Parameters())
        self.assertEqual(first, _i46_deform_charts(self.vdm, _i46_Parameters()))
        self.assertNotEqual(first, _i46_deform_charts(self.vdm, _i46_Parameters(seed=18)))
        self.assertEqual(self.vdm, original)
        for ordinal in (0, -1):
            self.assertEqual(first['stations'][ordinal], original['stations'][ordinal])
        for station in first['stations']:
            _i46_np.testing.assert_array_equal(_i46_np.asarray(station['reference_ring_xyz_m']) + _i46_np.asarray(station['displacement_ring_xyz_m']), station['derived_ring_xyz_m'])

    def test_real_boolean_air_route_and_preview_contract(self):
        preview = _i46_build_preview(self.rock, self.vdm, flat_sampler, {}, _i46_Parameters())
        self.assertEqual(preview['status'], 'geometry_checked')
        self.assertEqual(preview['schema'], 'td-underground-river-preview-v1')
        self.assertEqual(set(preview['meshes']), {'rock_before', 'cutter', 'rock_after', 'removed'})
        self.assertEqual(preview['geometry_checks']['air_segment_count'], 8)
        self.assertEqual(preview['geometry_checks']['terrain_opening_kinds'], ['sink', 'spring'])
        checks = preview['geometry_checks']
        self.assertFalse(checks['independent_audit_passed'])
        self.assertFalse(checks['complete_portal_certified'])
        self.assertEqual(len(checks['station_source_cover_witnesses']), 9)
        for station in checks['station_source_cover_witnesses']:
            for witness in station['actual_ring_containment']:
                self.assertIn('rock_before_vertical_hits', witness)
                self.assertEqual(witness['source_bed_witness']['derived_bed_m'], 0.0)
        self.assertEqual(len(checks['air_path_segments']), 8)
        for segment in checks['air_path_segments']:
            self.assertEqual(segment['rock_after_hits'], [])
            self.assertIn('rock_before_hits', segment)
            self.assertIn('removed_hits', segment)
        for opening in checks['portal_opening_witnesses'].values():
            self.assertTrue(opening['rock_before_hits'])
            self.assertEqual(opening['rock_after_hits'], [])
            self.assertIn('source_bed_witness', opening)
        self.assertGreater(preview['metrics']['excavated_rock_m3'], 0.0)
        self.assertLess(abs(preview['metrics']['material_residual_m3']), 1e-07)
        self.assertFalse(any(preview['capabilities'].values()))
        self.assertIsNone(preview['water'])
        expected = preview.pop('identity_sha256')
        self.assertEqual(_i46_identity(preview), expected)

    def test_parameter_bounds_cover_crop_and_deadline_refused(self):
        _i46_Parameters(seed=2 ** 32 - 1, lateral_amplitude_m=3.0, roof_variation_m=0.5)
        for kwargs in ({'seed': True}, {'seed': -1}, {'seed': 2 ** 32}, {'lateral_amplitude_m': 3.001}, {'roof_variation_m': 0.501}, {'width_scale': float('nan')}, {'width_scale': 0.79}):
            with self.assertRaises(ValueError):
                _i46_Parameters(**kwargs)
        broken = _i46_deepcopy(self.vdm)
        broken['stations'][4]['derived_ring_xyz_m'][0][0] = 100.0
        broken['stations'][4]['displacement_ring_xyz_m'][0][0] = 98.0
        with self.assertRaisesRegex(ValueError, 'crop'):
            _i46_build_preview(self.rock, broken, flat_sampler, {})
        exposed = _i46_deepcopy(self.vdm)
        exposed['stations'][4]['derived_ring_xyz_m'] = (_i46_np.asarray(exposed['stations'][4]['derived_ring_xyz_m']) + [0.0, 20.0, 0.0]).tolist()
        exposed['stations'][4]['displacement_ring_xyz_m'] = (_i46_np.asarray(exposed['stations'][4]['displacement_ring_xyz_m']) + [0.0, 20.0, 0.0]).tolist()
        with self.assertRaisesRegex(ValueError, 'cover'):
            _i46_build_preview(self.rock, exposed, flat_sampler, {})
        with self.assertRaisesRegex(ValueError, 'budget'):
            _i46_build_preview(self.rock, self.vdm, flat_sampler, {}, started=_i46_time.perf_counter() - 61.0)

    def test_numeric_types_rejected_as_value_error(self):
        for name in ('lateral_amplitude_m', 'width_scale', 'roof_variation_m'):
            for value in (None, '1.0', True, [], {}, complex(1.0, 0.0), float('inf'), 10 ** 1000):
                with self.subTest(name=name, value_type=type(value).__name__):
                    with self.assertRaises(ValueError):
                        _i46_Parameters(**{name: value})

    def test_connected_removed_does_not_accept_blocked_air_polyline(self):
        blocked = _i46_deepcopy(self.vdm)
        blocked['stations'][4]['origin_xyz_m'][0] = 5.0
        with self.assertRaisesRegex(ValueError, 'actual_rock_blocks_continuous_air_path'):
            _i46_build_preview(self.rock, blocked, flat_sampler, {}, _i46_Parameters(lateral_amplitude_m=0.0, width_scale=1.0, roof_variation_m=0.0))

    def test_no_overwrite_existing_source_directory(self):
        with self.assertRaisesRegex(ValueError, 'never overwrite'):
            _i46_prepare(ROOT / 'verification/natural-river-network/hybrid-cave-geometry-20261006-03')

def reseal(record):
    record.pop('identity_sha256', None)
    record['identity_sha256'] = _i45_digest(record)
    return record

class SavedGalleryAuditTests(_i45_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        UndergroundRiverTests.setUpClass()
        cls.rock = UndergroundRiverTests.rock
        cls.vdm = UndergroundRiverTests.vdm
        cls.preview = _i45_build_preview(cls.rock, cls.vdm, flat_sampler, {})

    def check(self, preview):
        return _i45_check_saved_geometry(reseal(preview), self.rock, self.vdm)

    def test_original_saved_geometry_passes_without_producer_calls(self):
        from unittest.mock import patch
        with patch('terrain_pipeline.underground_rivers.build_preview', side_effect=AssertionError('producer called')):
            result = self.check(_i45_deepcopy(self.preview))
        self.assertTrue(result['actual_boolean']['independent_boolean_verified'])
        self.assertTrue(result['actual_air_route']['actual_air_polyline_verified'])

    def test_resealed_material_lie_is_rejected(self):
        altered = _i45_deepcopy(self.preview)
        altered['metrics']['excavated_rock_m3'] += 1.0
        with self.assertRaisesRegex(ValueError, 'excavated material'):
            self.check(altered)

    def test_consistently_resealed_endpoint_movement_is_rejected(self):
        altered = _i45_deepcopy(self.preview)
        altered['stations'][0]['ring_local_xyz_m'][0][0] += 0.1
        altered['vdm']['derived_local_xyz_m'][0][0] += 0.1
        altered['vdm']['displacement_xyz_m'][0][0] += 0.1
        altered['meshes']['cutter']['vertices_local_xyz_m'][0][0] += 0.1
        with self.assertRaisesRegex(ValueError, 'immutable portal ring'):
            self.check(altered)

    def test_resealed_air_path_and_capability_are_rejected(self):
        altered = _i45_deepcopy(self.preview)
        altered['geometry_checks']['air_path_local_xyz_m'][3][1] -= 30.0
        altered['geometry_checks']['air_path_xyz_m'][3][1] -= 30.0
        with self.assertRaisesRegex(ValueError, 'waypoint outside'):
            self.check(altered)
        altered = _i45_deepcopy(self.preview)
        altered['capabilities']['hydraulic_solved'] = True
        with self.assertRaisesRegex(ValueError, 'capability promoted'):
            self.check(altered)

    def test_resealed_remaining_rock_substitution_is_rejected(self):
        altered = _i45_deepcopy(self.preview)
        altered['meshes']['rock_after'] = _i45_deepcopy(altered['meshes']['rock_before'])
        with self.assertRaisesRegex(ValueError, 'differs from independent Boolean'):
            self.check(altered)

    def test_wrong_external_sha_is_rejected_before_parsing(self):
        with _i45_tempfile.TemporaryDirectory(dir=_i45_ROOT / 'verification') as directory:
            path = _i45_Path(directory) / 'index.json'
            path.write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                _i45_audit({'path': str(path), 'sha256': '0' * 64})


def test_grayscale_ranks_entries_without_changing_physical_acceptance():
    shape = (3, 3)
    domain = _i44_np.ones(shape, bool)
    protected = _i44_np.zeros(shape, bool)
    protected[0, 0] = True
    domain[2, 0] = False
    cover = _i44_np.full(shape, 10.0)
    cover[2, 2] = 7.0
    gray = _i44_np.zeros(shape)
    gray[1, 0] = 1.0
    kwargs = dict(
        surface_plan=_plan(shape), lithology_reference=_i44_np.ones(shape),
        domain_mask=domain, protected_mask=protected,
        entries=[[1, 0], [1, 1], [0, 1], [0, 0], [2, 0], [2, 2]],
        exits=[{'grid_zx': [1, 2], 'type': 'surface_low'}],
        recipe=_i44_UndergroundRecipe(min_entry_score=100), cover_reference=cover)
    first = _i44_plan_underground(grayscale_reference=gray, **kwargs)
    second = _i44_plan_underground(grayscale_reference=1 - gray, **kwargs)
    expected = _i44_np.zeros(shape, bool)
    expected[1, :2] = True
    expected[0, 1] = True
    _i44_np.testing.assert_array_equal(first['arrays']['accepted_entry_mask'], expected)
    _i44_np.testing.assert_array_equal(second['arrays']['accepted_entry_mask'], expected)
    assert [item['grid_zx'] for item in first['entries'] if item['accepted']] == [[1, 1], [0, 1], [1, 0]]
    assert [item['grid_zx'] for item in second['entries'] if item['accepted']] == [[1, 0], [1, 1], [0, 1]]
    reasons = {tuple(item['grid_zx']): item['reasons'] for item in first['entries']}
    assert reasons[(0, 0)] == ['protected']
    assert reasons[(2, 0)] == ['outside_hydrologic_domain']
    assert reasons[(2, 2)] == ['insufficient_cover']
    assert first['edges'] and second['edges']
    assert first['identity']['algorithm_version'] == 'underground-channel-v2'
    assert first['identity']['parameters']['min_entry_score'] == 100


@_i44_pytest.mark.parametrize('gray,expected_score', [(-2, 0.65), (0, 0.65), (0.25, 0.5375), (1, 0.2), (9, 0.2)])
def test_constant_grayscale_keeps_absolute_clipped_intensity(gray, expected_score):
    shape = (2, 3)
    result = _i44_plan_underground(
        _plan(shape), _i44_np.full(shape, gray), _i44_np.ones(shape),
        _i44_np.ones(shape, bool), _i44_np.zeros(shape, bool), [[0, 0]],
        [{'grid_zx': [0, 2], 'type': 'surface_low'}],
        _i44_UndergroundRecipe(), _i44_np.full(shape, 10.0))
    _i44_np.testing.assert_allclose(result['arrays']['score_m'], expected_score)
    assert result['arrays']['accepted_entry_mask'][0, 0]


def test_loader_preserves_real_v1_fixture_and_rejects_unknown_version(tmp_path):
    import base64
    import hashlib
    # Frozen with the unchanged v1 implementation, before the v2 bugfix.
    raw = base64.b64decode('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')
    assert hashlib.sha256(raw).hexdigest() == 'c1461c57b10d4b42e98b74c6e2d768084d73026bad89e092021a203f599435e7'
    path = tmp_path / 'real-v1.npz'
    path.write_bytes(raw)
    with _i44_np.load(path, allow_pickle=False) as saved:
        manifest = _i44_json.loads(str(saved['manifest'].item()))
        original_arrays = {key: saved[key].copy() for key in saved.files if key != 'manifest'}
    loaded = _i44_load_underground(path)
    assert loaded['identity'] == manifest['identity']
    assert loaded['identity']['algorithm_version'] == 'underground-channel-v1'
    assert loaded['identity_sha256'] == manifest['identity_sha256'] == 'cf3e28e506c039330183cd4704ad16eab5b52caa367624946dfd789e7dc0a249'
    assert loaded['entries'] == manifest['entries']
    assert all(item['reasons'] == ['score_below_threshold'] for item in loaded['entries'])
    assert not loaded['arrays']['accepted_entry_mask'].any()
    _i44_np.testing.assert_array_equal(loaded['arrays']['score_m'], _i44_np.full((2, 3), 0.65))
    for name, value in loaded['arrays'].items():
        _i44_np.testing.assert_array_equal(value, original_arrays[name])
        assert _i44_array_hash(value) == manifest['array_sha256'][name]
        assert not value.flags.writeable
    assert path.read_bytes() == raw
    # Use a valid replacement identity and matching pin: rejection must be version policy.
    manifest['identity']['algorithm_version'] = 'underground-channel-v999'
    manifest['identity_sha256'] = _i44_ArtifactIdentity(**manifest['identity']).sha256
    unknown = tmp_path / 'unknown-version.npz'
    _i44_np.savez_compressed(unknown, manifest=_i44_json.dumps(manifest, sort_keys=True), **original_arrays)
    with _i44_pytest.raises(ValueError, match='identity or arrays differ'):
        _i44_load_underground(unknown)
