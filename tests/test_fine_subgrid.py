"""Consolidated test_fine_subgrid implementations; numeric expressions preserved."""
from __future__ import annotations
import copy as _i66_copy
import unittest as _i66_unittest
from unittest.mock import patch as _i66_patch
import numpy as _i66_np
from tools.audit_single_domain_fine_stage import canonical_reference as _i66_canonical_reference
from tools.audit_single_domain_fine_stage import audit_initial_contract as _i66_audit_initial_contract
from tools.audit_single_domain_fine_stage import audit_bed as _i66_audit_bed
import copy as _i67_copy
from pathlib import Path as _i67_Path
import tempfile as _i67_tempfile
import unittest as _i67_unittest
from unittest.mock import patch as _i67_patch
import numpy as _i67_np
import copy as _i68_copy
import json as _i68_json
import os as _i68_os
from pathlib import Path as _i68_Path
import subprocess as _i68_subprocess
import tempfile as _i68_tempfile
import unittest as _i68_unittest
from unittest.mock import patch as _i68_patch
import numpy as _i68_np
CATEGORY = 'B'

def sample():
    source = dict(height_m=_i66_np.ones((2, 2)), receiver=_i66_np.array([-1, -1, -1, -1]), valid_mask=_i66_np.ones((2, 2), bool), protected_mask=_i66_np.zeros((2, 2), bool))
    arrays = {'native_' + key: value.copy() for key, value in source.items()}
    arrays.update(selected_edge_cell_ids=_i66_np.empty((0, 2), _i66_np.int64), native_bilinear_corner_m=_i66_np.ones((2, 2)), cut_corner_m=_i66_np.zeros((2, 2)), bed_corner_m=_i66_np.ones((2, 2)), bed_center_m=_i66_np.ones((1, 1)), canonical_bed_center_m=_i66_np.ones((30, 30)), bed_vertices_xyz_m=_i66_np.array([[0.0, 1.0, 0.0], [0.0, 1.0, 30.0], [30.0, 1.0, 30.0], [30.0, 1.0, 0.0], [15.0, 1.0, 15.0]]), bed_triangles=_i66_np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], _i66_np.int64))
    metadata = dict(native_window=[0, 1, 0, 1], spacing_m=30.0)
    return (source, arrays, metadata)

class FineAuditTests(_i66_unittest.TestCase):

    def test_canonical_manning_uniform_velocity_contract(self):
        from tools.audit_shallow_water import canonical_manning
        for depths in ([0.5, 0.5], [0.1, 0.9], [0.0, 1.0], [0.0, 0.1], [0.0, 0.0]):
            h = _i66_np.asarray(depths)
            stage = float(h.max())
            subbed = _i66_np.sort((stage - h)[None, :], axis=1)
            mean = float(h.mean())
            state = _i66_np.array([[mean, 0.5 * mean, 0.0]])
            damping, factor = canonical_manning(state, subbed, 0.1, 9.81, 0.035)
            expected_i = sum((value ** (-1 / 3) for value in h if value > 0)) / len(h)
            expected = mean / (mean + 0.1 * 9.81 * 0.035 ** 2 * 0.5 * expected_i) if mean > 0 else 0
            self.assertAlmostEqual(factor[0], expected_i, places=12)
            self.assertAlmostEqual(damping[0], expected, places=12)

    def test_v3_independent_subgrid_pressure_storage_and_flat_invariants(self):
        from tests.test_shallow_water import ShallowWaterSubgridSegmentedTests as ShallowWaterV3Tests
        from tools.audit_shallow_water import physical_witness
        from tools.audit_shallow_water import MODEL_V3
        from terrain_pipeline.shallow_water import subgrid_segmented_hll_rhs as shallow_water_rhs
        canonical = 1350.0 + _i66_np.tile(_i66_np.arange(16) * 0.1, (12, 1)) + 0.05 * _i66_np.arange(12)[:, None]
        for factor in (1, 2, 4):
            geometry, support, datum = ShallowWaterV3Tests().geometry(canonical, factor)
            g = dict(geometry['arrays'], hydraulic_datum_m=datum)
            h = _i66_np.maximum(1350.8 - canonical, 0).reshape(12 // factor, factor, 16 // factor, factor).mean(axis=(1, 3))
            state = _i66_np.column_stack((h.ravel(), _i66_np.zeros((h.size, 2))))
            args = dict(spacing=float(factor), gravity=9.81, boundary_kind=g['boundary_kind'], tailwater=_i66_np.zeros(2 * sum(h.shape)), roughness=0.035, dt=0.01)
            expected, witness = shallow_water_rhs(state, g['H2_m'] - datum, support=support, **args)
            actual = physical_witness(state, g, float(factor), 9.81, args['tailwater'] + datum, 0.01, model=MODEL_V3)
            for a, b in zip(actual, (expected, witness['internal_flux'], witness['boundary_flux'], witness['bed_source'])):
                _i66_np.testing.assert_allclose(a, b, atol=2e-12, rtol=0)
            _i66_np.testing.assert_allclose(actual[0], 0, atol=2e-12, rtol=0)
        geometry, _, datum = ShallowWaterV3Tests().geometry(_i66_np.zeros((12, 16)), 2)
        g = dict(geometry['arrays'], hydraulic_datum_m=datum)
        h = _i66_np.linspace(0.1, 1.0, g['H2_m'].size)
        state = _i66_np.column_stack((h, _i66_np.zeros((len(h), 2))))
        rhs, _, _, source = physical_witness(state, g, 2.0, 9.81, _i66_np.zeros(len(g['boundary_cell'])), 0.01, model=MODEL_V3)
        _i66_np.testing.assert_allclose(source, 0, atol=1e-14, rtol=0)
        self.assertGreater(_i66_np.linalg.norm(rhs[:, 1:]), 0)

    def test_flat_bed_source_zero_and_dam_break_pressure_accelerates(self):
        run_fixture = run_fixture
        from tools.audit_shallow_water import physical_witness
        from tools.audit_shallow_water import MODEL
        from tools.audit_shallow_water import MODEL_V2
        result = run_fixture(backend='shallow_water')
        geometry = _i66_copy.deepcopy(result['geometry']['arrays'])
        geometry['H2_m'][:] = 0
        geometry['boundary_crest_m'][:] = 0
        state = _i66_np.column_stack((_i66_np.array([1.0, 0.4, 0.1, 1.0, 0.4, 0.1]), _i66_np.zeros((6, 2))))
        for model in (MODEL, MODEL_V2):
            rhs, _, _, source = physical_witness(state, geometry, 1.0, 9.81, _i66_np.zeros(10), 0.01, model=model)
            _i66_np.testing.assert_array_equal(source, _i66_np.zeros((6, 3)))
            self.assertGreater(_i66_np.linalg.norm(rhs[:, 1:]), 0)
            self.assertGreater(_i66_np.max(abs(rhs[:, 0])), 0)

    def test_v2_independent_reconstruction_flux_and_pressure_match_saved_witness(self):
        run_fixture = run_fixture
        from tools.audit_shallow_water import physical_witness
        from tools.audit_shallow_water import MODEL_V2
        from terrain_pipeline.shallow_water import muscl_coarse_bed_rhs as shallow_water_rhs
        result = run_fixture(backend='shallow_water')
        geometry = result['geometry']['arrays']
        state = _i66_np.column_stack((_i66_np.array([0.2, 0.1, 0, 0.1, 0.05, 0.2]), _i66_np.array([0.02, -0.01, 0, 0.01, 0, -0.02]), _i66_np.array([0.01, 0, 0, -0.01, 0.01, 0])))
        kinds = geometry['boundary_kind'].copy()
        kinds[2:4] = 2
        geometry['boundary_kind'] = kinds
        tail = _i66_np.full(10, 0.25)
        actual = physical_witness(state, geometry, 1.0, 9.81, tail, 0.01, model=MODEL_V2)
        expected, witness = shallow_water_rhs(state, geometry['H2_m'], spacing=1.0, gravity=9.81, boundary_kind=kinds, tailwater=tail, roughness=0.03, dt=0.01, boundary_crest=geometry['boundary_crest_m'])
        for first, second in zip(actual, (expected, witness['internal_flux'], witness['boundary_flux'], witness['bed_source'])):
            _i66_np.testing.assert_allclose(first, second, atol=1e-12, rtol=1e-12)

    def test_physical_hll_rejects_coordinated_algebra_consistent_witness(self):
        run_fixture = run_fixture
        from tools.audit_shallow_water import audit_momentum
        from terrain_pipeline.fine_subgrid import validate_fine_momentum
        from terrain_pipeline.fine_subgrid import _saved_flux_divergence
        from terrain_pipeline.common_infra import identity
        result = run_fixture(backend='shallow_water', initial_depth_m=_i66_np.full((2, 3), 0.1))
        witness = _i66_copy.deepcopy(result['momenta'][0])
        geometry = result['geometry']
        forcing = result['forcing']['arrays']
        budget = result['states']['metadata']['solver_metadata']['budget']
        with _i66_patch('terrain_pipeline.shallow_water.hydrostatic_hll', side_effect=RuntimeError('forbidden')), _i66_patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_shallow_water_rhs', side_effect=RuntimeError('forbidden')):
            audit_momentum(witness['arrays'], witness['metadata'], geometry['arrays'], 1.0, budget, forcing['local_q_m3_s'][0], forcing['boundary_stage_m'][0])
            a = witness['arrays']
            a['rk2_internal_flux'][0] += _i66_np.array([0.001, 0.002, 0.003])
            rhs = _saved_flux_divergence(geometry, a['rk2_internal_flux'], a['rk2_boundary_flux']) + a['rk2_bed_source']
            rhs[:, 0] += a['forcing_m3_s']
            undamped = 0.5 * a['state_before'] + 0.5 * (a['state_predictor'] + witness['metadata']['dt_s'] * rhs)
            a['state_after'] = undamped.copy()
            wet = undamped[:, 0] > 0
            drag = budget['gravity_m_s2'] * budget['roughness_s_m_third'] ** 2 * _i66_np.linalg.norm(undamped[wet, 1:], axis=1) / undamped[wet, 0] ** (7 / 3)
            a['state_after'][wet, 1:] /= (1 + witness['metadata']['dt_s'] * drag)[:, None]
            a['manning_momentum_change'] = a['state_after'][:, 1:] - undamped[:, 1:]
            witness['identity_sha256'] = identity(a, witness['metadata'])
            validate_fine_momentum(witness, bed=result['bed'], geometry=geometry, forcing=result['forcing'], states=result['states'], interval=0, interval_packet=result['intervals'][0])
            with self.assertRaisesRegex(ValueError, 'physical RK2 internal_flux'):
                audit_momentum(a, witness['metadata'], geometry['arrays'], 1.0, budget, forcing['local_q_m3_s'][0], forcing['boundary_stage_m'][0])

    def test_true_triangle_mean_detects_center_equal_wrong_h2(self):
        from terrain_pipeline.fine_subgrid import validate_canonical_bed as _i66_validate_canonical_bed
        source, arrays, metadata = sample()
        self.assertTrue(_i66_audit_bed(arrays, metadata, source)['triangle_fv_bed_mean_verified'])
        arrays['bed_vertices_xyz_m'][-1, 1] = 2.0
        diagnostics = _i66_audit_bed(arrays, metadata, source)
        self.assertFalse(diagnostics['triangle_fv_bed_mean_verified'])
        self.assertAlmostEqual(diagnostics['maximum_triangle_fv_bed_mean_difference_m'], 1 / 3)
        with self.assertRaisesRegex(ValueError, 'triangle area-mean'):
            _i66_validate_canonical_bed(dict(arrays=arrays, metadata=metadata))

    def test_canonical_protection_is_checked_without_builders(self):
        from terrain_pipeline.fine_subgrid import canonical_bed_fields as _i66_canonical_bed_fields
        source, arrays, metadata = sample()
        source['protected_mask'][:] = True
        source['receiver'][0] = 1
        arrays['native_protected_mask'][:] = True
        arrays['native_receiver'][0] = 1
        arrays['selected_edge_cell_ids'] = _i66_np.array([[0, 1]], _i66_np.int64)
        with _i66_patch('terrain_pipeline.fine_subgrid._geometry_arrays', side_effect=RuntimeError('builder forbidden')):
            expected, protected, suppressed = _i66_canonical_reference(arrays, metadata, source)
            actual, mask = _i66_canonical_bed_fields(dict(arrays=arrays, metadata=metadata))
        self.assertTrue(protected.all())
        self.assertTrue(mask.all())
        self.assertGreater(suppressed.max(), 0.0)
        _i66_np.testing.assert_array_equal(expected, _i66_np.ones((30, 30)))
        _i66_np.testing.assert_array_equal(actual, expected)

    def test_coarse_initial_depth_restricts_wetted_inventory(self):
        bed = _i66_np.array([[0.0, 2.0], [2.0, 2.0]])
        coarse = _i66_np.array([[0.25]])
        correct = _i66_audit_initial_contract(coarse, bed, lake_stage_m=1.0, spacing_m=2.0, initial_kind='lake')
        self.assertTrue(correct['passed'])
        wrong = _i66_np.maximum(1.0 - bed.mean(), 0).reshape(1, 1)
        self.assertFalse(_i66_audit_initial_contract(wrong, bed, lake_stage_m=1.0, spacing_m=2.0, initial_kind='lake')['passed'])

    def test_subgrid_cold_equation_witness_never_calls_production_flux(self):
        from terrain_pipeline.fine_subgrid import _segment_momentum_witness
        from terrain_pipeline.surface_hydraulics import SurfaceBudget
        arrays = dict(face_left=_i66_np.array([0]), face_right=_i66_np.array([1]), boundary_cell=_i66_np.array([0, 1]), boundary_kind=_i66_np.array([0, 0]), face_segment_crest_relative_m=_i66_np.zeros((1, 2)), boundary_segment_crest_relative_m=_i66_np.zeros((2, 2)))
        geometry = dict(arrays=arrays, metadata=dict(spacing_m=2.0, hydraulic_datum_m=100.0))
        with _i66_patch('terrain_pipeline.fine_subgrid.segmented_flux', side_effect=RuntimeError('solver forbidden')):
            internal, boundary, limiter = _segment_momentum_witness(geometry, _i66_np.array([0.1, 0.1]), _i66_np.zeros((1, 2)), _i66_np.zeros((2, 2)), _i66_np.array([100.0, 100.0]), _i66_np.zeros(2), 0.01, SurfaceBudget(), _i66_np.array([0.1, 0.1]))
        _i66_np.testing.assert_array_equal(internal, _i66_np.zeros((1, 2)))
        _i66_np.testing.assert_array_equal(boundary, _i66_np.zeros((2, 2)))
        self.assertEqual(limiter['limited_donors'], 0)

def fixture(protected=None):
    from terrain_pipeline.fine_subgrid import build_fine_geometry as _i67_build_fine_geometry
    from terrain_pipeline.basin_topology import build_basin_hierarchy as _i67_build_basin_hierarchy
    from terrain_pipeline.basin_storage import make_td_source as _i67_make_td_source
    height = _i67_np.array([[4.0, 3.0, 4.0], [3.0, 0.0, 3.0], [4.0, 2.0, 4.0]])
    hierarchy = _i67_build_basin_hierarchy(_i67_make_td_source(height, spacing_m=30.0, origin_m_xz=(120.0, -60.0), protected_mask=protected))
    geometry = _i67_build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256='a' * 64)
    return (hierarchy, geometry)

def states(geometry, depth):
    from terrain_pipeline.common_infra import identity as _i67_identity
    arrays = dict(depth_m=_i67_np.array([depth], dtype=_i67_np.float64), time_s=_i67_np.array([60.0], _i67_np.float64))
    metadata = dict(schema='single-domain-fine-states-v1', bed_identity=geometry['identity_sha256'])
    return dict(arrays=arrays, metadata=metadata, identity_sha256=_i67_identity(arrays, metadata))

def mutable(result):
    result = _i67_copy.deepcopy(result)
    result['arrays'] = {name: value.copy() for name, value in result['arrays'].items()}
    return result

class FineGeometryTests(_i67_unittest.TestCase):

    def test_complete_window_upward_shared_junction_fan(self):
        hierarchy, geometry = fixture()
        arrays = geometry['arrays']
        self.assertEqual(arrays['H2_m'].shape, (60, 60))
        self.assertEqual(len(arrays['bed_triangles']), 14400)
        corners = arrays['bed_vertices_xyz_m'][arrays['cell_corner_vertex_ids'], 1]
        self.assertTrue(_i67_np.isfinite(arrays['H2_m']).all())
        entering = arrays['edge_node_indices'][:, 1] == 4
        self.assertEqual(int(entering.sum()), 4)
        endpoints = arrays['node_xyz_m'][arrays['edge_node_indices']]
        _i67_np.testing.assert_array_equal(endpoints[entering, 1], _i67_np.tile([150.0, -1.0, -30.0], (4, 1)))
        vertices, triangles = (arrays['bed_vertices_xyz_m'], arrays['bed_triangles'])
        normals = _i67_np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
        self.assertTrue(_i67_np.all(normals[:, 1] > 0))
        self.assertTrue(arrays['internal_sink_mask'][4])
        _i67_np.testing.assert_array_equal(arrays['native_height_m'], hierarchy['arrays']['height_m'])
        self.assertFalse(arrays['bed_vertices_xyz_m'].flags.writeable)

    def test_protection_preserves_original_and_cut_is_max_not_sum(self):
        protected = _i67_np.zeros((3, 3), bool)
        protected[1, 1] = True
        _, geometry = fixture(protected)
        arrays = geometry['arrays']
        self.assertFalse(arrays['cut_corner_m'][arrays['protected_corner_mask']].any())
        _i67_np.testing.assert_array_equal(arrays['bed_corner_m'][arrays['protected_corner_mask']], arrays['native_bilinear_corner_m'][arrays['protected_corner_mask']])
        _, unprotected = fixture()
        self.assertEqual(unprotected['metadata']['maximum_cut_m'], 1.0)
        self.assertEqual(unprotected['arrays']['cut_corner_m'][30, 30], 1.0)

    def test_isolated_wet_cell_continuous_nonnegative_exact_local_volume(self):
        from terrain_pipeline.fine_subgrid import build_fine_water_frame as _i67_build_fine_water_frame
        _, geometry = fixture()
        depth = _i67_np.zeros((60, 60), _i67_np.float64)
        depth[30, 30] = 0.25
        frame = _i67_build_fine_water_frame(geometry, states(geometry, depth), state_index=0)
        arrays = frame['arrays']
        self.assertEqual(len(arrays['water_triangles']), 4)
        self.assertEqual(arrays['center_depth_m'][30, 30], 0.75)
        self.assertEqual(arrays['cell_volume_m3'][30, 30], 0.25)
        self.assertEqual(frame['metadata']['raster_volume_m3'], 0.25)
        expected_offset = geometry['arrays']['bed_fan_center_m'] + arrays['center_depth_m'] - (geometry['arrays']['H2_m'] + depth)
        self.assertEqual(frame['metadata']['max_center_stage_offset_m'], float(abs(expected_offset).max()))
        self.assertEqual(frame['metadata']['omitted_wet_cell_count'], 0)
        self.assertFalse(arrays['corner_depth_m'].any())
        _i67_np.testing.assert_array_equal(arrays['water_vertices_xyz_m'][:, [0, 2]], geometry['arrays']['bed_vertices_xyz_m'][:, [0, 2]])

    def test_random_wet_dry_depths_conserve_every_cell_and_share_edges(self):
        from terrain_pipeline.fine_subgrid import build_fine_water_frame as _i67_build_fine_water_frame
        _, geometry = fixture()
        depth = _i67_np.random.default_rng(31).random((60, 60))
        depth[depth < 0.4] = 0.0
        frame = _i67_build_fine_water_frame(geometry, states(geometry, depth), state_index=0)
        arrays = frame['arrays']
        _i67_np.testing.assert_allclose(arrays['cell_volume_m3'], depth, rtol=0.0, atol=1e-15)
        self.assertTrue(_i67_np.all(arrays['center_depth_m'] >= 0.0))
        corner_ids = geometry['arrays']['cell_corner_vertex_ids'].reshape(60, 60, 4)
        _i67_np.testing.assert_array_equal(corner_ids[:, :-1, [3, 2]], corner_ids[:, 1:, [0, 1]])
        corner_depths = arrays['corner_depth_m'].ravel()[corner_ids.reshape(-1, 4)]
        self.assertFalse(corner_depths[depth.ravel() == 0].any())
        self.assertEqual(len(arrays['water_triangles']), int(_i67_np.count_nonzero(depth)) * 4)

    def test_resolution_samples_same_original_and_all_window_cells(self):
        from terrain_pipeline.fine_subgrid import build_fine_geometry as _i67_build_fine_geometry
        from terrain_pipeline.fine_subgrid import build_fine_water_frame as _i67_build_fine_water_frame
        hierarchy, fine = fixture()
        for spacing in (2.0, 4.0):
            geometry = _i67_build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256='a' * 64, spacing_m=spacing)
            arrays = geometry['arrays']
            _i67_np.testing.assert_array_equal(arrays['native_bilinear_corner_m'], fine['arrays']['native_bilinear_corner_m'][::int(spacing), ::int(spacing)])
            self.assertEqual(arrays['H2_m'].shape, (int(60 / spacing),) * 2)
            frame = _i67_build_fine_water_frame(geometry, states(geometry, _i67_np.ones_like(arrays['H2_m'])), state_index=0)
            self.assertEqual(frame['metadata']['triangulated_volume_m3'], 3600.0)
            expected_offset = abs(arrays['bed_fan_center_m'] - arrays['H2_m'])
            self.assertAlmostEqual(frame['metadata']['max_center_stage_offset_m'], float(expected_offset.max()))

    def test_coarse_bed_is_canonical_one_metre_area_transfer(self):
        from terrain_pipeline.fine_subgrid import build_fine_geometry as _i67_build_fine_geometry
        hierarchy, one = fixture()
        two = _i67_build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256='a' * 64, spacing_m=2.0)
        four = _i67_build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256='a' * 64, spacing_m=4.0)
        expected_two = one['arrays']['H2_m'].reshape(30, 2, 30, 2).mean(axis=(1, 3))
        expected_four = one['arrays']['H2_m'].reshape(15, 4, 15, 4).mean(axis=(1, 3))
        _i67_np.testing.assert_allclose(two['arrays']['H2_m'], expected_two, rtol=0.0, atol=1e-12)
        _i67_np.testing.assert_allclose(four['arrays']['H2_m'], expected_four, rtol=0.0, atol=1e-12)
        for geometry in (one, two, four):
            corners = geometry['arrays']['bed_corner_m']
            centre = geometry['arrays']['bed_fan_center_m']
            integrated = (corners[:-1, :-1] + corners[1:, :-1] + corners[1:, 1:] + corners[:-1, 1:] + 2 * centre) / 6
            _i67_np.testing.assert_allclose(integrated, geometry['arrays']['H2_m'], rtol=0.0, atol=1e-12)

    def test_initial_depth_transfer_uses_area_mean_not_recomputed_clipping(self):
        from terrain_pipeline.fine_subgrid import coarsen_cell_field as _i67_coarsen_cell_field
        fine_depth = _i67_np.zeros((60, 60), _i67_np.float64)
        fine_depth[10:14, 10:14] = _i67_np.arange(16, dtype=_i67_np.float64).reshape(4, 4)
        coarse = _i67_coarsen_cell_field(fine_depth, factor=2)
        _i67_np.testing.assert_array_equal(coarse[5:7, 5:7], [[2.5, 4.5], [10.5, 12.5]])
        with self.assertRaises(ValueError):
            _i67_coarsen_cell_field(fine_depth, factor=3)

    def test_native_boundary_crossings_and_true_internal_sinks(self):
        from terrain_pipeline.fine_subgrid import build_fine_geometry as _i67_build_fine_geometry
        from terrain_pipeline.basin_topology import build_basin_hierarchy as _i67_build_basin_hierarchy
        from terrain_pipeline.basin_storage import make_td_source as _i67_make_td_source
        height = _i67_np.tile(_i67_np.arange(5.0, 0.0, -1), (5, 1))
        hierarchy = _i67_build_basin_hierarchy(_i67_make_td_source(height, spacing_m=30.0, origin_m_xz=(0.0, 0.0)))
        geometry = _i67_build_fine_geometry(hierarchy, native_window=[1, 3, 1, 3], source_hierarchy_sha256='a' * 64)
        arrays = geometry['arrays']
        self.assertEqual(len(arrays['incoming_boundary_edge_cell_ids']), 3)
        self.assertEqual(len(arrays['outgoing_boundary_edge_cell_ids']), 3)
        self.assertFalse(arrays['internal_sink_mask'].any())

    def test_rehashed_geometry_and_water_corruption_rejected(self):
        from terrain_pipeline.common_infra import identity as _i67_identity
        from terrain_pipeline.fine_subgrid import build_fine_water_frame as _i67_build_fine_water_frame
        from terrain_pipeline.fine_subgrid import validate_fine_geometry as _i67_validate_fine_geometry
        from terrain_pipeline.fine_subgrid import validate_fine_water_frame as _i67_validate_fine_water_frame
        _, geometry = fixture()
        frame = _i67_build_fine_water_frame(geometry, states(geometry, _i67_np.ones((60, 60))), state_index=0)
        for original, validator, field in ((geometry, _i67_validate_fine_geometry, 'bed_corner_m'), (geometry, _i67_validate_fine_geometry, 'H2_m'), (geometry, _i67_validate_fine_geometry, 'node_xyz_m'), (frame, _i67_validate_fine_water_frame, 'center_depth_m'), (frame, _i67_validate_fine_water_frame, 'water_vertices_xyz_m'), (frame, _i67_validate_fine_water_frame, 'cell_volume_m3')):
            result = mutable(original)
            result['arrays'][field].flat[0] += 1.0
            result['identity_sha256'] = _i67_identity(result['arrays'], result['metadata'])
            with self.subTest(field=field), self.assertRaises(ValueError):
                validator(result)

    def test_native_water_and_invalid_state_or_window_refused(self):
        from terrain_pipeline.common_infra import identity as _i67_identity
        from terrain_pipeline.fine_subgrid import build_fine_geometry as _i67_build_fine_geometry
        from terrain_pipeline.fine_subgrid import build_fine_water_frame as _i67_build_fine_water_frame
        hierarchy, geometry = fixture()
        saved = states(geometry, _i67_np.ones((60, 60)))
        for kind in ('native', 'identity', 'negative'):
            bad = mutable(saved)
            if kind == 'native':
                bad['metadata']['bed_identity'] = hierarchy['identity_sha256']
            elif kind == 'identity':
                bad['identity_sha256'] = 'b' * 64
            else:
                bad['arrays']['depth_m'][0, 0, 0] = -1.0
            if kind != 'identity':
                bad['identity_sha256'] = _i67_identity(bad['arrays'], bad['metadata'])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                _i67_build_fine_water_frame(geometry, bad, state_index=0)
        for kwargs in (dict(native_window=[0, 3, 0, 2]), dict(native_window=[0, 2, 0, 2], spacing_m=0.5), dict(native_window=[0, 2, 0, 2], width_m=9.0)):
            with self.assertRaises(ValueError):
                _i67_build_fine_geometry(hierarchy, source_hierarchy_sha256='a' * 64, **kwargs)

    def test_roundtrip_readonly_without_constructor_calls(self):
        from terrain_pipeline.common_infra import file_sha256 as _i67_file_sha256
        from terrain_pipeline.fine_subgrid import build_fine_water_frame as _i67_build_fine_water_frame
        from terrain_pipeline.fine_subgrid import load_fine_geometry as _i67_load_fine_geometry
        from terrain_pipeline.fine_subgrid import load_fine_water_frame as _i67_load_fine_water_frame
        from terrain_pipeline.fine_subgrid import save_fine_geometry as _i67_save_fine_geometry
        from terrain_pipeline.fine_subgrid import save_fine_water_frame as _i67_save_fine_water_frame
        _, geometry = fixture()
        frame = _i67_build_fine_water_frame(geometry, states(geometry, _i67_np.ones((60, 60))), state_index=0)
        with _i67_tempfile.TemporaryDirectory() as directory:
            for name, result, saver, loader in (('bed', geometry, _i67_save_fine_geometry, _i67_load_fine_geometry), ('water', frame, _i67_save_fine_water_frame, _i67_load_fine_water_frame)):
                path = _i67_Path(directory) / (name + '.npz')
                saver(path, result)
                with _i67_patch('terrain_pipeline.fine_subgrid.build_fine_geometry', side_effect=AssertionError), _i67_patch('terrain_pipeline.fine_subgrid.build_fine_water_frame', side_effect=AssertionError):
                    loaded = loader(path, expected_sha256=_i67_file_sha256(path), expected_identity=result['identity_sha256'])
                self.assertTrue(all((not value.flags.writeable for value in loaded['arrays'].values())))
                with self.assertRaises(ValueError):
                    loader(path, expected_sha256='0' * 64, expected_identity=result['identity_sha256'])

def _test_single_domain_fine_hydraulics_fixture():
    from terrain_pipeline.common_infra import identity as _i68_identity
    bed = dict(arrays=dict(bed_center_m=_i68_np.array([[0.0, 0.01, 0.02], [0.0, 0.01, 0.02]])), metadata=dict(spacing_m=1.0, origin_m_xz=[2.0, 3.0], scope='synthetic_fixture'))
    bed['identity_sha256'] = _i68_identity(bed['arrays'], bed['metadata'])
    return bed

def run_fixture(**overrides):
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i68_SurfaceBudget
    from terrain_pipeline.fine_subgrid import run_fine_hydraulics as _i68_run_fine_hydraulics
    bed = _test_single_domain_fine_hydraulics_fixture()
    options = dict(rain_mm_h=_i68_np.full((4, 2, 3), 40.0), boundary_stage_m=_i68_np.zeros((4, 10)), forcing_interval_s=0.25, boundary_kind=_i68_np.zeros(10, _i68_np.int64), backend='reference', budget=_i68_SurfaceBudget(max_dt_s=0.05, max_snapshots=6, max_duration_s=2.0, max_wall_s=1800.0))
    options.update(overrides)
    return _i68_run_fine_hydraulics(bed, **options)

class FineHydraulicsTests(_i68_unittest.TestCase):

    def test_frozen_snapshot_link_cannot_escape_stage_root(self):
        from terrain_pipeline.common_infra import file_sha256 as _i68_file_sha256
        from terrain_pipeline.fine_subgrid import _validate_code_records
        from tools.audit_single_domain_fine_stage import audit_code_records
        with _i68_tempfile.TemporaryDirectory() as temporary:
            root = _i68_Path(temporary)
            stage, outside = (root / 'stage', root / 'outside-stage')
            stage.mkdir()
            outside.mkdir()
            name = 'module.py'
            source = outside / name
            source.write_bytes(b'# immutable external test source\n')
            link = stage / 'execution-code'
            try:
                _i68_os.symlink(outside, link, target_is_directory=True)
            except OSError:
                if _i68_os.name != 'nt':
                    self.skipTest('directory symlinks unavailable')
                created = _i68_subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True, check=False)
                if created.returncode:
                    self.skipTest('directory symlink and junction creation unavailable')
            digest = _i68_file_sha256(source)
            records = {name: dict(path=str(link / name), expected_sha256=digest)}
            with self.assertRaisesRegex(ValueError, 'root escaped stage'):
                _validate_code_records({name: digest}, records, stage)
            with self.assertRaisesRegex(ValueError, 'root escaped stage'):
                audit_code_records(dict(code_sha256={name: digest}, code_records=records), stage, [])

    def setUp(self):
        self.result = run_fixture()

    def validate(self, result=None):
        from terrain_pipeline.fine_subgrid import validate_fine_forcing as _i68_validate_fine_forcing
        from terrain_pipeline.fine_subgrid import validate_fine_states as _i68_validate_fine_states
        from terrain_pipeline.fine_subgrid import validate_fine_interval as _i68_validate_fine_interval
        from terrain_pipeline.fine_subgrid import validate_fine_momentum as _i68_validate_fine_momentum
        result = self.result if result is None else result
        _i68_validate_fine_forcing(result['forcing'], bed=result['bed'])
        _i68_validate_fine_states(result['states'], bed=result['bed'], geometry=result['geometry'], forcing=result['forcing'])
        previous = None
        for number, item in enumerate(result['intervals']):
            _i68_validate_fine_interval(item, bed=result['bed'], geometry=result['geometry'], forcing=result['forcing'], interval=number, previous=previous)
            _i68_validate_fine_momentum(result['momenta'][number], bed=result['bed'], geometry=result['geometry'], forcing=result['forcing'], states=result['states'], interval=number, interval_packet=item)
            previous = item

    def test_dry_rain_independent_four_compartments(self):
        self.validate()
        forcing = self.result['forcing']['arrays']
        self.assertGreater(forcing['fast_release_mm'].sum(), 0.0)
        self.assertGreater(forcing['slow_release_mm'].sum(), 0.0)
        self.assertGreater(self.result['states']['arrays']['depth_m'][-1].sum(), 0.0)
        self.assertEqual(self.result['geometry']['metadata']['origin_m_xz'], [2.5, 3.5])

    def bed(self):
        from terrain_pipeline.common_infra import identity as _i68_identity
        canonical = 1350.0 + _i68_np.tile(_i68_np.array([0.0, 0.03, 0.01, 0.04, 0.02, 0.05]), (4, 1))
        mean = canonical.reshape(2, 2, 3, 2).mean(axis=(1, 3))
        arrays = dict(canonical_bed_center_m=canonical, bed_center_m=mean, H2_m=mean.copy())
        metadata = dict(spacing_m=2.0, origin_m_xz=[0.0, 0.0])
        return dict(arrays=arrays, metadata=metadata, identity_sha256=_i68_identity(arrays, metadata))

    def run_case(self, initial, kinds=None, tailwater=1350.1):
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i68_SurfaceBudget
        from terrain_pipeline.runoff import RunoffParameters as _i68_RunoffParameters
        from terrain_pipeline.fine_subgrid import run_fine_hydraulics as _i68_run_fine_hydraulics
        bed = self.bed()
        return _i68_run_fine_hydraulics(bed, rain_mm_h=_i68_np.zeros((2, 2, 3)), boundary_stage_m=_i68_np.full((2, 10), tailwater), backend='subgrid', forcing_interval_s=0.1, boundary_kind=_i68_np.zeros(10, _i68_np.int64) if kinds is None else kinds, initial_depth_m=initial, runoff_parameters=_i68_RunoffParameters(initial_soil_mm=0.0, percolation_mm_h=0.0, potential_et_mm_h=0.0), budget=_i68_SurfaceBudget(max_dt_s=0.01, max_snapshots=4, max_duration_s=1.0, max_wall_s=1800.0))

    def test_exact_piecewise_wet_storage_inverse(self):
        from terrain_pipeline.fine_subgrid import storage_stages as _i68_storage_stages
        from terrain_pipeline.fine_subgrid import stage_depths as _i68_stage_depths
        bed = _i68_np.array([[0.0, 0.2, 0.8, 1.0]])
        stage = _i68_storage_stages(_i68_np.array([0.15]), bed, _i68_np.cumsum(bed, axis=1))
        _i68_np.testing.assert_allclose(stage, [0.4], rtol=0.0, atol=1e-15)
        _i68_np.testing.assert_allclose(_i68_stage_depths(stage, bed), [0.15], rtol=0.0, atol=1e-15)

    def test_closed_partially_wet_lake_at_1350m_uses_relative_datum(self):
        from terrain_pipeline.fine_subgrid import prepare_subgrid_support as _i68_prepare_subgrid_support
        from terrain_pipeline.fine_subgrid import stage_depths as _i68_stage_depths
        from terrain_pipeline.fine_subgrid import SUBGRID_MODEL as _i68_SUBGRID_MODEL
        support, _ = _i68_prepare_subgrid_support(self.bed())
        initial = _i68_stage_depths(_i68_np.full(6, 0.025), support['subcell_bed_relative_m']).reshape(2, 3)
        result = self.run_case(initial)
        _i68_np.testing.assert_allclose(result['states']['arrays']['depth_m'][-1], initial, rtol=0.0, atol=1e-13)
        self.assertEqual(result['geometry']['metadata']['coarse_independent_unknowns'], 6)
        self.assertEqual(result['states']['metadata']['hydraulic_model'], _i68_SUBGRID_MODEL)

    def test_segmented_coarse_boundary_witness_and_local_budget(self):
        kinds = _i68_np.zeros(10, _i68_np.int64)
        kinds[2:4] = 2
        result = self.run_case(_i68_np.zeros((2, 3)), kinds)
        self.assertGreater(result['states']['arrays']['ledger'][-1, 1], 0.0)
        for packet in result['intervals']:
            a = packet['arrays']
            _i68_np.testing.assert_array_equal(a['internal_transfer_m3'], a['internal_segment_transfer_m3'].sum(axis=1))
            _i68_np.testing.assert_array_equal(a['boundary_transfer_m3'], a['boundary_segment_transfer_m3'].sum(axis=1))
        self.assertEqual(result['states']['arrays']['final_internal_segment_q_m3_s'].shape, (7, 2))

    def test_lake_at_rest_and_tailwater_import(self):
        from terrain_pipeline.runoff import RunoffParameters as _i68_RunoffParameters
        initial = 0.1 - _test_single_domain_fine_hydraulics_fixture()['arrays']['bed_center_m']
        still = run_fixture(rain_mm_h=_i68_np.zeros((4, 2, 3)), initial_depth_m=initial, runoff_parameters=_i68_RunoffParameters(initial_soil_mm=0.0, percolation_mm_h=0.0, potential_et_mm_h=0.0))
        self.validate(still)
        _i68_np.testing.assert_allclose(still['states']['arrays']['depth_m'][-1], initial, atol=1e-14)
        kinds = _i68_np.zeros(10, _i68_np.int64)
        kinds[2:4] = 2
        backwater = run_fixture(initial_depth_m=initial, boundary_kind=kinds, boundary_stage_m=_i68_np.full((4, 10), 0.6))
        self.validate(backwater)
        self.assertGreater(backwater['states']['arrays']['ledger'][-1, 1], 0.0)
        self.assertLess(backwater['intervals'][0]['arrays']['boundary_transfer_m3'].sum(), 0.0)

    def test_resigned_state_source_release_momentum_and_closed_boundary_rejected(self):
        from terrain_pipeline.common_infra import identity as _i68_identity
        for kind in ('state', 'source', 'fast_release', 'momentum', 'closed'):
            with self.subTest(kind=kind):
                result = _i68_copy.deepcopy(self.result)
                if kind == 'state':
                    result['states']['arrays']['depth_m'][-1, 0, 0] += 0.1
                elif kind == 'source':
                    result['states']['metadata']['bed_identity'] = 'a' * 64
                elif kind == 'fast_release':
                    result['forcing']['arrays']['fast_release_mm'][0, 0] += 0.1
                elif kind == 'momentum':
                    result['momenta'][0]['arrays']['internal_q_after_m3_s'][0] += 1.0
                else:
                    result['intervals'][0]['arrays']['boundary_q_after_m3_s'][0] = 1.0
                for role in ('states', 'forcing'):
                    result[role]['identity_sha256'] = _i68_identity(result[role]['arrays'], result[role]['metadata'])
                for role in ('intervals', 'momenta'):
                    for item in result[role]:
                        item['identity_sha256'] = _i68_identity(item['arrays'], item['metadata'])
                with self.assertRaises(ValueError):
                    self.validate(result)

    def test_resource_and_forcing_preflight_rejected(self):
        from terrain_pipeline.common_infra import identity as _i68_identity
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i68_SurfaceBudget
        with self.assertRaises(ValueError):
            run_fixture(budget=_i68_SurfaceBudget(max_wall_s=1801.0, max_snapshots=6))
        with self.assertRaises(ValueError):
            run_fixture(rain_mm_h=_i68_np.full((4, 2, 3), _i68_np.nan))
        with self.assertRaises(ValueError):
            run_fixture(boundary_stage_m=_i68_np.zeros((3, 10)))
        forged = _i68_copy.deepcopy(self.result)
        forged['states']['metadata']['solver_metadata']['budget']['max_wall_s'] = 1801.0
        forged['states']['identity_sha256'] = _i68_identity(forged['states']['arrays'], forged['states']['metadata'])
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.validate(forged)

    def test_shallow_saved_momentum_closures_and_resigned_corruption(self):
        from terrain_pipeline.common_infra import identity as _i68_identity
        result = run_fixture(backend='shallow_water', initial_depth_m=_i68_np.full((2, 3), 0.1))
        self.validate(result)
        for role, name in (('momenta', 'state_predictor'), ('momenta', 'rk1_bed_source'), ('momenta', 'rk2_internal_flux'), ('momenta', 'manning_momentum_change'), ('intervals', 'momentum_after'), ('intervals', 'bed_momentum_change'), ('intervals', 'internal_momentum_transfer')):
            with self.subTest(role=role, field=name):
                forged = _i68_copy.deepcopy(result)
                packet = forged[role][0]
                packet['arrays'][name].flat[1] += 0.01
                packet['identity_sha256'] = _i68_identity(packet['arrays'], packet['metadata'])
                with self.assertRaises(ValueError):
                    self.validate(forged)

    def test_shallow_roundtrip_without_execution_helpers(self):
        from terrain_pipeline.common_infra import file_sha256 as _i68_file_sha256
        from terrain_pipeline.common_infra import save_bundle as _i68_save_bundle
        from terrain_pipeline.fine_subgrid import save_fine_run as _i68_save_fine_run
        from terrain_pipeline.fine_subgrid import load_fine_run as _i68_load_fine_run
        result = run_fixture(backend='shallow_water', initial_depth_m=_i68_np.full((2, 3), 0.1))
        with _i68_tempfile.TemporaryDirectory() as temporary:
            root = _i68_Path(temporary)
            bed_path = root / 'bed.npz'
            _i68_save_bundle(bed_path, result['bed'], validator=lambda item: True)
            bed_record = dict(path=str(bed_path), expected_sha256=_i68_file_sha256(bed_path), expected_identity=result['bed']['identity_sha256'])
            repo = _i68_Path(__file__).resolve().parents[1]
            codes = {'terrain_pipeline/fine_subgrid.py': _i68_file_sha256(repo / 'terrain_pipeline/fine_subgrid.py')}
            pin = _i68_save_fine_run(root / 'run', result, bed_record=bed_record, code_sha256=codes)
            with _i68_patch('terrain_pipeline.shallow_water.advance_shallow_water', side_effect=RuntimeError('forbidden')), _i68_patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_shallow_water_rhs', side_effect=RuntimeError('forbidden')), _i68_patch('terrain_pipeline.shallow_water.hydrostatic_hll', side_effect=RuntimeError('forbidden')):
                loaded = _i68_load_fine_run(pin['path'], expected_sha256=pin['expected_sha256'], bed=result['bed'])
            self.assertEqual(loaded['intervals_verified'], 4)

    def test_subgrid_shallow_stage_cold_package_and_forged_stage(self):
        from terrain_pipeline.common_infra import identity as _i68_identity
        from terrain_pipeline.common_infra import file_sha256 as _i68_file_sha256
        from terrain_pipeline.common_infra import save_bundle as _i68_save_bundle
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i68_SurfaceBudget
        from terrain_pipeline.runoff import RunoffParameters as _i68_RunoffParameters
        from terrain_pipeline.fine_subgrid import run_fine_hydraulics as _i68_run_fine_hydraulics
        from terrain_pipeline.fine_subgrid import save_fine_run as _i68_save_fine_run
        from terrain_pipeline.fine_subgrid import load_fine_run as _i68_load_fine_run
        geometry_fixture = fixture
        from terrain_pipeline.fine_subgrid import build_fine_geometry
        hierarchy, _ = geometry_fixture()
        bed = build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256='a' * 64, spacing_m=2.0)
        shape = bed['arrays']['bed_center_m'].shape
        canonical = bed['arrays']['canonical_bed_center_m']
        initial = _i68_np.maximum(2.0 - canonical, 0).reshape(shape[0], 2, shape[1], 2).mean(axis=(1, 3))
        result = _i68_run_fine_hydraulics(bed, rain_mm_h=_i68_np.zeros((2, *shape)), boundary_stage_m=_i68_np.zeros((2, 2 * sum(shape))), boundary_kind=_i68_np.zeros(2 * sum(shape), _i68_np.int64), forcing_interval_s=0.02, initial_depth_m=initial, backend='shallow_water_subgrid', budget=_i68_SurfaceBudget(max_dt_s=0.01, max_snapshots=4, max_wall_s=1800.0), runoff_parameters=_i68_RunoffParameters(initial_soil_mm=0.0, percolation_mm_h=0.0, potential_et_mm_h=0.0))
        self.validate(result)
        _i68_np.testing.assert_allclose(result['states']['arrays']['depth_m'][-1], initial, atol=1e-12, rtol=0)
        forged = _i68_copy.deepcopy(result)
        forged['states']['arrays']['stage_relative_m'][-1, 0, 0] += 0.1
        forged['states']['identity_sha256'] = _i68_identity(forged['states']['arrays'], forged['states']['metadata'])
        with self.assertRaises(ValueError):
            self.validate(forged)
        for role, name in (('momenta', 'rk1_internal_flux'), ('momenta', 'rk2_bed_source'), ('intervals', 'internal_momentum_transfer')):
            forged = _i68_copy.deepcopy(result)
            packet = forged[role][0]
            packet['arrays'][name].flat[1] += 0.1
            packet['identity_sha256'] = _i68_identity(packet['arrays'], packet['metadata'])
            with self.assertRaises(ValueError):
                self.validate(forged)
        with _i68_tempfile.TemporaryDirectory() as temporary:
            root = _i68_Path(temporary)
            bed_path = root / 'bed.npz'
            _i68_save_bundle(bed_path, bed, validator=lambda item: True)
            bed_record = dict(path=str(bed_path), expected_sha256=_i68_file_sha256(bed_path), expected_identity=bed['identity_sha256'])
            repo = _i68_Path(__file__).resolve().parents[1]
            name = 'terrain_pipeline/single_domain_fine_io.py'
            snapshot = root / 'execution-code' / name
            snapshot.parent.mkdir(parents=True)
            snapshot.write_bytes((repo / name).read_bytes())
            codes = {name: _i68_file_sha256(snapshot)}
            code_records = {name: dict(path=str(snapshot), expected_sha256=codes[name])}
            pin = _i68_save_fine_run(root / 'run', result, bed_record=bed_record, code_sha256=codes, code_records=code_records)
            with _i68_patch('terrain_pipeline.shallow_water.single_domain_shallow_water_mechanism_3_advance_shallow_water', side_effect=RuntimeError('forbidden')), _i68_patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_mechanism_3_shallow_water_rhs', side_effect=RuntimeError('forbidden')), _i68_patch('terrain_pipeline.fine_subgrid.storage_stages', side_effect=RuntimeError('forbidden')):
                loaded = _i68_load_fine_run(pin['path'], expected_sha256=pin['expected_sha256'], bed=bed)
            self.assertEqual(loaded['intervals_verified'], 2)
            index_path = _i68_Path(pin['path'])
            original = index_path.read_text(encoding='utf-8')
            wrong = _i68_json.loads(original)
            wrong['code_records'] = {'wrong-name.py': code_records[name]}
            index_path.write_text(_i68_json.dumps(wrong), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'record names'):
                _i68_load_fine_run(index_path, expected_sha256=_i68_file_sha256(index_path), bed=bed)
            index_path.write_text(original, encoding='utf-8')
            snapshot.write_bytes(snapshot.read_bytes() + b'\n# forged snapshot\n')
            with self.assertRaisesRegex(ValueError, 'snapshot pin'):
                _i68_load_fine_run(index_path, expected_sha256=_i68_file_sha256(index_path), bed=bed)

    def test_v7_canonical_manning_saved_witness_cold_and_forgery(self):
        from terrain_pipeline.common_infra import identity as _i68_identity
        from terrain_pipeline.common_infra import file_sha256 as _i68_file_sha256
        from terrain_pipeline.common_infra import save_bundle as _i68_save_bundle
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i68_SurfaceBudget
        from terrain_pipeline.fine_subgrid import run_fine_hydraulics as _i68_run_fine_hydraulics
        from terrain_pipeline.fine_subgrid import save_fine_run as _i68_save_fine_run
        from terrain_pipeline.fine_subgrid import load_fine_run as _i68_load_fine_run
        geometry_fixture = fixture
        from terrain_pipeline.fine_subgrid import build_fine_geometry
        from tools.audit_shallow_water import audit_momentum
        hierarchy, _ = geometry_fixture()
        bed = build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256='a' * 64, spacing_m=2.0)
        shape = bed['arrays']['bed_center_m'].shape
        result = _i68_run_fine_hydraulics(bed, rain_mm_h=_i68_np.zeros((2, *shape)), boundary_stage_m=_i68_np.full((2, 2 * sum(shape)), 2.0), boundary_kind=_i68_np.zeros(2 * sum(shape), _i68_np.int64), forcing_interval_s=0.02, initial_depth_m=_i68_np.full(shape, 0.1), backend='shallow_water_subgrid_manning', budget=_i68_SurfaceBudget(max_dt_s=0.01, max_snapshots=4, max_wall_s=1800.0))
        self.validate(result)
        geometry = dict(result['geometry']['arrays'], hydraulic_datum_m=result['geometry']['metadata']['hydraulic_datum_m'])
        packet = result['momenta'][0]
        with _i68_patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_mechanism_7_manning_damping', side_effect=RuntimeError('forbidden')):
            audited = audit_momentum(packet['arrays'], packet['metadata'], geometry, 2.0, result['states']['metadata']['solver_metadata']['budget'], result['forcing']['arrays']['local_q_m3_s'][0], result['forcing']['arrays']['boundary_stage_m'][0])
        self.assertTrue(audited['canonical_subgrid_manning_consistency_verified'])
        forged = _i68_copy.deepcopy(result)
        witness = forged['momenta'][0]
        witness['arrays']['manning_inverse_depth_third_mean'][0] += 0.1
        witness['identity_sha256'] = _i68_identity(witness['arrays'], witness['metadata'])
        with self.assertRaisesRegex(ValueError, 'Manning'):
            self.validate(forged)
        with self.assertRaisesRegex(ValueError, 'inverse-depth integral'):
            audit_momentum(witness['arrays'], witness['metadata'], geometry, 2.0, result['states']['metadata']['solver_metadata']['budget'], result['forcing']['arrays']['local_q_m3_s'][0], result['forcing']['arrays']['boundary_stage_m'][0])
        with _i68_tempfile.TemporaryDirectory() as temporary:
            root = _i68_Path(temporary)
            bed_path = root / 'bed.npz'
            _i68_save_bundle(bed_path, bed, validator=lambda item: True)
            bed_record = dict(path=str(bed_path), expected_sha256=_i68_file_sha256(bed_path), expected_identity=bed['identity_sha256'])
            repo = _i68_Path(__file__).resolve().parents[1]
            name = 'terrain_pipeline/single_domain_fine_io.py'
            pin = _i68_save_fine_run(root / 'run', result, bed_record=bed_record, code_sha256={name: _i68_file_sha256(repo / name)})
            with _i68_patch('terrain_pipeline.shallow_water.single_domain_shallow_water_mechanism_7_advance_shallow_water', side_effect=RuntimeError('forbidden')), _i68_patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_mechanism_7_manning_damping', side_effect=RuntimeError('forbidden')):
                loaded = _i68_load_fine_run(pin['path'], expected_sha256=pin['expected_sha256'], bed=bed)
            self.assertEqual(loaded['intervals_verified'], 2)

    def test_roundtrip_cold_without_advance_and_forged_code_pin(self):
        from terrain_pipeline.common_infra import file_sha256 as _i68_file_sha256
        from terrain_pipeline.common_infra import save_bundle as _i68_save_bundle
        from terrain_pipeline.fine_subgrid import save_fine_run as _i68_save_fine_run
        from terrain_pipeline.fine_subgrid import load_fine_run as _i68_load_fine_run
        with _i68_tempfile.TemporaryDirectory() as temporary:
            root = _i68_Path(temporary)
            bed_path = root / 'bed.npz'
            _i68_save_bundle(bed_path, self.result['bed'], validator=lambda item: True)
            bed_record = dict(path=str(bed_path), expected_sha256=_i68_file_sha256(bed_path), expected_identity=self.result['bed']['identity_sha256'])
            repo = _i68_Path(__file__).resolve().parents[1]
            codes = {'terrain_pipeline/fine_subgrid.py': _i68_file_sha256(repo / 'terrain_pipeline/fine_subgrid.py')}
            pin = _i68_save_fine_run(root / 'run', self.result, bed_record=bed_record, code_sha256=codes)
            with _i68_patch('terrain_pipeline.surface_hydraulics.advance_inertial_surface', side_effect=RuntimeError('advance forbidden')):
                loaded = _i68_load_fine_run(pin['path'], expected_sha256=pin['expected_sha256'], bed=self.result['bed'])
            self.assertEqual(loaded['intervals_verified'], 4)
            self.assertFalse(loaded['solver_advanced'])
            index = _i68_json.loads(_i68_Path(pin['path']).read_text(encoding='utf-8'))
            index['code_sha256']['terrain_pipeline/fine_subgrid.py'] = 'a' * 64
            _i68_Path(pin['path']).write_text(_i68_json.dumps(index), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'implementation pin'):
                _i68_load_fine_run(pin['path'], expected_sha256=_i68_file_sha256(pin['path']), bed=self.result['bed'])
