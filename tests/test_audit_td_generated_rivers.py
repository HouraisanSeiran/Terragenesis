import copy
import unittest
from unittest.mock import patch
import numpy as np
from terrain_pipeline.common_infra import TerrainGrid
from tools.audit_td_generated_rivers import audit_continuous_design, audit_geometry, audit_global_geometry, audit_material_ledger, audit_network, mesh_flow_slopes, reference_scale_gate, saved_centerline_metrics
from terrain_pipeline.common_infra import identity
from terrain_pipeline.channel_geometry import _line_constraints, _mesh_volume, build_monotone_union
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import GeneratedRiverConfig, component_geometry
from tests.test_channel_geometry import _test_metric_valley_centerline_fixture as fixture
from terrain_pipeline.channel_geometry import _sparse_mesh
from terrain_pipeline.channel_geometry import build_design_geometry

class GeneratedRiverAuditTests(unittest.TestCase):

    def setUp(self):
        self.terrain = TerrainGrid(np.array([[4.0, 3.0], [2.0, 1.0]]), np.ones((2, 2), bool), 0.0, 0.0, 30.0, 30.0, 'generated_terrain', 'fixture', 'a' * 64)
        self.arrays = {'source_height_m': self.terrain.elevation_m, 'receiver': np.array([2, 2, 3, -1]), 'contributing_area_m2': np.array([900.0, 900.0, 2700.0, 3600.0]), 'local_q_m3_s': np.ones((2, 2)), 'routed_q_m3_s': np.array([[1.0, 1.0], [3.0, 4.0]]), 'outlet_kind': np.array(['interior', 'interior', 'interior', 'unknown_boundary']), 'selected_edge_source_ids': np.array([2]), 'selected_edge_target_ids': np.array([3]), 'selected_edge_status': np.array(['accepted'])}

    def test_saved_graph_balances_and_morphology(self):
        result = audit_network(self.arrays, self.terrain, 1800.0)
        self.assertEqual(result['terminal_area_residual_m2'], 0.0)
        self.assertEqual(result['terminal_q_residual_m3_s'], 0.0)
        self.assertEqual(result['maximum_strahler_order'], 1)
        self.assertEqual(result['maximum_full_grid_strahler_order'], 2)
        self.assertEqual(result['selected_edge_count'], 1)

    def test_missing_edge_and_forged_accumulation_rejected(self):
        changed = copy.deepcopy(self.arrays)
        changed['selected_edge_source_ids'] = np.array([], np.int64)
        changed['selected_edge_target_ids'] = np.array([], np.int64)
        with self.assertRaisesRegex(ValueError, 'complete area-threshold'):
            audit_network(changed, self.terrain, 1800.0)
        changed = copy.deepcopy(self.arrays)
        changed['contributing_area_m2'][-1] += 900.0
        with self.assertRaisesRegex(ValueError, 'area differs'):
            audit_network(changed, self.terrain, 1800.0)

    def test_cycle_and_flow_tampering_rejected(self):
        changed = copy.deepcopy(self.arrays)
        changed['receiver'][3] = 2
        with self.assertRaisesRegex(ValueError, 'cycle'):
            audit_network(changed, self.terrain, 1800.0)
        changed = copy.deepcopy(self.arrays)
        changed['routed_q_m3_s'][1, 1] += 1
        with self.assertRaisesRegex(ValueError, 'routed Q differs'):
            audit_network(changed, self.terrain, 1800.0)

    def test_old_real_reference_scale_is_not_comparable(self):
        result = reference_scale_gate({'spacing_m_xz': [90.0, 90.0], 'shape_zx': [48, 48], 'minimum_area_m2': 100000.0}, self.terrain, 1000000.0)
        self.assertEqual(result['status'], 'not_comparable_scale_mismatch')
        self.assertEqual(len(result['mismatched_fields']), 3)

    def test_actual_mesh_measured_without_rebuilding_and_bed_tamper_rejected(self):
        terrain, ids, receiver, options = fixture()
        bundle = build_monotone_union(terrain, ids, receiver, np.full(4, 2.0), np.full(4, 0.25), **options)
        with patch('terrain_pipeline.channel_geometry.build_monotone_union', side_effect=AssertionError('audit regenerated mesh')):
            result, edges = audit_geometry(bundle, terrain)
        self.assertEqual(result['uphill_actual_bed_segment_count'], 0)
        self.assertEqual(len(edges), 3)
        changed = copy.deepcopy(bundle)
        changed['arrays']['bed_elevation_m'] = changed['arrays']['bed_elevation_m'].copy()
        changed['arrays']['bed_elevation_m'][0] += 1.0
        changed['identity_sha256'] = identity(changed['arrays'], changed['metadata'])
        with self.assertRaisesRegex(ValueError, 'mesh source/bed/cut'):
            audit_geometry(changed, terrain)
        changed = copy.deepcopy(bundle)
        a = changed['arrays']
        segments = _line_constraints(a['node_xz_m'], a['receiver'], a['sparse_cell_xy'], a['vertices_xz_m'], a['triangles'], terrain, changed['metadata']['config']['fine_spacing_m'])
        start = segments[0][0]
        vertex = start[0][np.argmax(start[1])]
        a['cut_depth_m'] = a['cut_depth_m'].copy()
        a['cut_depth_m'][vertex] += 1.0
        a['bed_elevation_m'] = a['source_elevation_m'] - a['cut_depth_m']
        changed['identity_sha256'] = identity(a, changed['metadata'])
        with self.assertRaisesRegex(ValueError, 'uphill'):
            audit_geometry(changed, terrain)

    def test_boundary_section_reports_partial_actual_width(self):
        _, cols = np.indices((5, 5))
        terrain = TerrainGrid((10.0 - cols).astype(np.float64), np.ones((5, 5), bool), 0.0, 0.0, 30.0, 30.0, 'generated_terrain', 'boundary', 'b' * 64)
        bundle = component_geometry(terrain, np.array([1, 2, 3]), np.array([1, 2, -1]), np.full(3, 6.0), np.full(3, 0.25), GeneratedRiverConfig(centerline_iterations=0))
        result, _ = audit_geometry(bundle, terrain)
        self.assertEqual(result['partial_cross_section_count'], 2)
        self.assertEqual(result['fully_represented_cross_section_count'], 0)
        self.assertEqual(result['actual_port_bottom_width_m']['samples'], [3.0, 3.0])
        self.assertEqual(result['requested_port_bottom_width_m']['samples'], [6.0, 6.0])

    def test_depth_statistics_use_original_design_and_separate_legacy_profile_depth(self):
        terrain, ids, receiver, options = fixture()
        bundle = build_monotone_union(terrain, ids, receiver, np.full(4, 2.0), np.full(4, 0.25), **options)
        legacy, _ = audit_geometry(bundle, terrain)
        self.assertIsNone(legacy['designed_base_depth_m'])
        self.assertIsNone(legacy['width_depth_ratio'])
        self.assertEqual(legacy['legacy_propagated_profile_depth_m']['samples'], [0.25] * 4)
        changed = copy.deepcopy(bundle)
        changed['arrays']['design_base_depth_m'] = np.full(4, 0.125)
        changed['identity_sha256'] = identity(changed['arrays'], changed['metadata'])
        design, _ = audit_geometry(changed, terrain)
        self.assertEqual(design['designed_base_depth_m']['samples'], [0.125] * 4)
        self.assertEqual(design['width_depth_ratio']['samples'], [16.0] * 4)
        self.assertEqual(design['saved_base_depth_parameter_m']['samples'], [0.25] * 4)
        self.assertIsNone(design['legacy_propagated_profile_depth_m'])

    def test_short_triangle_intersection_large_datum_uses_plane_gradient(self):
        terrain = TerrainGrid(np.full((2, 2), 1000000.0), np.ones((2, 2), bool), 0.0, 0.0, 1.0, 1.0, 'generated_terrain', 'short', 'c' * 64)
        cells = np.array([[0, 0]])
        vertices, triangles = _sparse_mesh(cells, terrain, 1.0, 20)
        points = np.array([[0.1, 0.50000001], [0.9, 0.50000001]])
        receiver = np.array([1, -1])
        bed = 1000000.0 - 2e-05 * vertices[:, 0] + 1e-05 * vertices[:, 1]
        slopes, lengths, _ = mesh_flow_slopes(points, receiver, cells, vertices, triangles, bed, terrain, 1.0)
        self.assertLess(lengths.min(), 1e-07)
        np.testing.assert_allclose(slopes, 2e-05, atol=5e-10, rtol=0.0)
        bed = 1000000.0 - 4e-05 * vertices[:, 0]
        bed[vertices[:, 1] == 1.0] = 1000000.0
        bed[np.all(vertices == [0.5, 0.5], axis=1)] = 1000000.0 - 1e-05
        slopes, lengths, _ = mesh_flow_slopes(points, receiver, cells, vertices, triangles, bed, terrain, 1.0)
        tiny = lengths < 1e-07
        self.assertTrue(tiny.any())
        self.assertTrue(np.all(np.abs(slopes[tiny]) < 1e-10))
        self.assertTrue(np.all(slopes[~tiny] > 1e-05))

    def test_actual_saved_centerline_length_uses_shaped_positions(self):
        points = np.array([[0.0, 0.0], [3.0, 4.0], [6.0, 4.0], [10.0, 0.0], [10.0, 2.0]])
        result = saved_centerline_metrics(points, np.array([1, 2, -1, 4, -1]))
        self.assertEqual(result['actual_total_centerline_length_m'], 10.0)
        self.assertEqual(result['actual_maximum_continuous_path_length_m'], 8.0)
        self.assertAlmostEqual(result['actual_d8_quantized_bearing_fraction'], 2.0 / 3.0)
        self.assertAlmostEqual(result['actual_turn_angle_rad']['samples'][0], np.arctan2(4.0, 3.0))

    def continuous_design_fixture(self):
        terrain = TerrainGrid(np.full((2, 2), 10.0), np.ones((2, 2), bool), 0.0, 0.0, 40.0, 40.0, 'observed_dem', 'design', 'd' * 64)
        points, receiver = (np.array([[6.0, 10.0], [14.0, 10.0]]), np.array([1, -1]))
        profile = (np.array([0, 3]), np.array([0.0, 0.3, 1.0]), np.full(3, 10.0), np.array([9.5, 9.49995, 9.4999]))
        cells, vertices, triangles, source, _, cut, _, lower, upper, padding, _ = build_design_geometry(points, receiver, np.ones(2), np.full(2, 0.5), profile, terrain, 1.0, 4.0, 1e-05)
        arrays = dict(node_xz_m=points, receiver=receiver, width_m=np.ones(2), design_base_depth_m=np.full(2, 0.5), sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, source_elevation_m=source, cut_depth_m=cut, bed_elevation_m=source - cut, design_minimum_cut_m=lower, design_maximum_cut_m=upper, source_interpolation_padding_m=padding, profile_offsets=profile[0], profile_t=profile[1], profile_source_m=profile[2], profile_center_bed_m=profile[3])
        return (terrain, dict(arrays=arrays, metadata=dict(config=dict(fine_spacing_m=1.0, max_cut_m=4.0))))

    def test_continuous_saved_mesh_certificate_rejects_depth_and_profile_tampering(self):
        terrain, bundle = self.continuous_design_fixture()
        vertices, source, upper = (bundle['arrays'][key] for key in ('vertices_xz_m', 'source_elevation_m', 'design_maximum_cut_m'))
        result = audit_continuous_design(bundle, terrain)
        self.assertEqual(result['interior_support_seam_status'], 'zero_cut_verified')
        changed = copy.deepcopy(bundle)
        central = np.argmin(np.linalg.norm(vertices - [10.0, 10.0], axis=1))
        changed['arrays']['cut_depth_m'][central] = 0.1
        changed['arrays']['bed_elevation_m'][central] = source[central] - 0.1
        with self.assertRaisesRegex(ValueError, 'continuous bottom'):
            audit_continuous_design(changed, terrain)
        changed = copy.deepcopy(bundle)
        changed['arrays']['profile_center_bed_m'][1] -= 1.0
        with self.assertRaisesRegex(ValueError, 'continuous center-profile'):
            audit_continuous_design(changed, terrain)
        changed = copy.deepcopy(bundle)
        seam = np.flatnonzero(upper == 0.0)[0]
        changed['arrays']['cut_depth_m'][seam] = 0.1
        changed['arrays']['bed_elevation_m'][seam] = source[seam] - 0.1
        with self.assertRaisesRegex(ValueError, 'necessary design bounds'):
            audit_continuous_design(changed, terrain)

    def test_global_material_released_cut_is_not_counted_as_overlap(self):
        terrain, global_bundle = self.continuous_design_fixture()
        a, m = (global_bundle['arrays'], global_bundle['metadata'])
        a.update(source_node_cell_ids=np.array([0, 1]), base_depth_m=np.full(2, 0.5), port_edge_node_indices=np.empty((0, 2), np.int64), port_profile_xz_m=np.empty((0, 4, 2)))
        m.update(source_identity_sha256=terrain.identity_sha256, design_bed_policy={'test': True}, minimum_bed_slope_m_per_m=1e-05, cut_volume_m3=_mesh_volume(a['vertices_xz_m'], a['triangles'], a['cut_depth_m']), preclosure_cut_volume_m3=_mesh_volume(a['vertices_xz_m'], a['triangles'], a['design_minimum_cut_m']))
        component = copy.deepcopy(global_bundle)
        ca = component['arrays']
        distance = np.linalg.norm(ca['vertices_xz_m'] - [10.0, 10.0], axis=1)
        candidates = np.flatnonzero((distance > 3.0) & (ca['design_maximum_cut_m'] > 0.0) & (ca['vertices_xz_m'][:, 1] != 10.0))
        ca['cut_depth_m'][candidates[0]] += 0.1
        ca['bed_elevation_m'] = ca['source_elevation_m'] - ca['cut_depth_m']
        component['metadata']['cut_volume_m3'] = _mesh_volume(ca['vertices_xz_m'], ca['triangles'], ca['cut_depth_m'])
        component['identity_sha256'] = identity(ca, component['metadata'])
        a.update(design_constraint_node_mask=np.ones(2, bool), design_constraint_vertex_mask=np.ones(len(a['vertices_xz_m']), bool), design_constraint_triangle_mask=np.ones(len(a['triangles']), bool))
        global_bundle['identity_sha256'] = identity(a, m)
        result, _ = audit_global_geometry(global_bundle, [component], terrain)
        self.assertAlmostEqual(result['overlap_double_count_m3'], 0.0)
        self.assertLess(result['reclosure_net_change_m3'], 0.0)
        self.assertGreaterEqual(result['union_additional_cut_volume_m3'], 0.0)
        ledger = dict(unique_cut_volume_m3=result['cut_volume_m3'], component_sum_cut_volume_m3=result['component_sum_volume_m3'], overlap_double_count_m3=result['overlap_double_count_m3'], union_monotone_additional_cut_volume_m3=result['union_additional_cut_volume_m3'], component_max_envelope_cut_volume_m3=result['component_max_envelope_cut_volume_m3'], reclosure_net_change_m3=result['reclosure_net_change_m3'], necessary_lower_cut_volume_m3=result['preclosure_cut_volume_m3'])
        audit_material_ledger(ledger, result, continuous_design=True)
        ledger['necessary_lower_cut_volume_m3'] += 1.0
        with self.assertRaisesRegex(ValueError, 'necessary_lower_cut_volume_m3'):
            audit_material_ledger(ledger, result, continuous_design=True)
        changed = copy.deepcopy(global_bundle)
        changed['metadata']['preclosure_cut_volume_m3'] += 1.0
        changed['identity_sha256'] = identity(changed['arrays'], changed['metadata'])
        with self.assertRaisesRegex(ValueError, 'preclosure volume'):
            audit_global_geometry(changed, [component], terrain)
if __name__ == '__main__':
    unittest.main()
