"""Consolidated test_hybrid_geometry_saved_audit implementations; numeric expressions preserved."""
from __future__ import annotations
import unittest as _i9_unittest
from io import BytesIO as _i9_BytesIO
from types import SimpleNamespace as _i9_SimpleNamespace
import numpy as _i9_np
from tools.hybrid_cave_saved_audit import Solid as _i9_Solid
from tools.hybrid_cave_saved_audit import air_path_evidence as _i9_air_path_evidence
from tools.hybrid_cave_saved_audit import boolean_evidence as _i9_boolean_evidence
from tools.hybrid_cave_saved_audit import manifold_library as _i9_manifold_library
from tools.hybrid_cave_saved_audit import vdm_mapping as _i9_vdm_mapping
from tools.hybrid_cave_saved_audit import sampled_top_height as _i9_sampled_top_height
import copy as _i10_copy
import unittest as _i10_unittest
import numpy as _i10_np
from shapely.geometry import LineString as _i10_LineString
from shapely.geometry import Polygon as _i10_Polygon
from shapely.geometry import box as _i10_box
from tools.audit_hybrid_geometry import _i18_Solid as _i10_Solid
from tools.audit_hybrid_geometry import audit_aperture as _i10_audit_aperture
from tools.audit_hybrid_geometry import audit_slice as _i10_audit_slice
from tools.audit_hybrid_geometry import check_plane as _i10_check_plane
from tools.audit_hybrid_geometry import triangle_plane_segments as _i10_triangle_plane_segments
import copy as _i11_copy
import unittest as _i11_unittest
import numpy as _i11_np
from terrain_pipeline.hybrid_geometry import mesh_record as _i11_mesh_record
from terrain_pipeline.hybrid_geometry import plane_frame as _i11_plane_frame
from terrain_pipeline.hybrid_geometry import role_slice as _i11_role_slice
from terrain_pipeline.hybrid_geometry import surface_role_sources as _i11_surface_role_sources
from tools.audit_hybrid_geometry import audit_role_slice as _i11_audit_role_slice
from tools.audit_hybrid_geometry import topology_roles as _i11_topology_roles
import unittest as _i12_unittest
from tools.hybrid_saved_slice_geometry_adapter import consume_saved_slice as _i12_consume_saved_slice
from tools.hybrid_saved_slice_geometry_adapter import describe_saved_slice as _i12_describe_saved_slice
import unittest as _i13_unittest
import numpy as _i13_np
from tools.audit_hybrid_geometry import _i20_Solid as _i13_Solid
from tools.audit_hybrid_geometry import audit_material_solids as _i13_audit_material_solids
from tools.audit_hybrid_geometry import exact_fan_cut as _i13_exact_fan_cut
from tools.audit_hybrid_geometry import _i20_manifold_library as _i13_manifold_library
from tools.audit_hybrid_geometry import saved_patch_affine_depth as _i13_saved_patch_affine_depth
import copy as _i14_copy
import unittest as _i14_unittest
import numpy as _i14_np
from tools.audit_hybrid_geometry import NUMERICAL_POLICY as _i14_NUMERICAL_POLICY
from tools.audit_hybrid_geometry import NUMERICAL_POLICY_SHA256 as _i14_NUMERICAL_POLICY_SHA256
from tools.audit_hybrid_geometry import SLICE_SCHEMA as _i14_SLICE_SCHEMA
from tools.audit_hybrid_geometry import _i21_Solid as _i14_Solid
from tools.audit_hybrid_geometry import audit_exact_slice as _i14_audit_exact_slice
from tools.audit_hybrid_geometry import check_shape as _i14_check_shape
from tools.audit_hybrid_geometry import _i21_digest as _i14_digest
import copy as _i15_copy
from fractions import Fraction as _i15_Fraction
import math as _i15_math
from types import SimpleNamespace as _i15_SimpleNamespace
import unittest as _i15_unittest
from unittest.mock import patch as _i15_patch
import numpy as _i15_np
from tools import audit_hybrid_geometry as _i15_audit
from tools.hybrid_exact_solid_saved_audit import ExactSolid as _i15_ExactSolid
import copy as _i16_copy
import json as _i16_json
from pathlib import Path as _i16_Path
import tempfile as _i16_tempfile
import unittest as _i16_unittest
from unittest.mock import patch as _i16_patch
import numpy as _i16_np
from tools import audit_hybrid_geometry as _i16_audit
from tools.hybrid_exact_solid_saved_audit import ExactSolid as _i16_ExactSolid
from tools.hybrid_surface_resume_saved_audit import ValidatedSolid as _i16_ValidatedSolid
from tools.hybrid_surface_resume_saved_audit import load_native_bound as _i16_load_native_bound
from tools.td_shared_channel_fine_saved_audit import digest as _i16_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i16_file_sha256
from fractions import Fraction as _i17_Fraction
import unittest as _i17_unittest
import mpmath as _i17_mpmath
from mpmath.ctx_iv import MPIntervalContext as _i17_MPIntervalContext
from tools.hybrid_exact_solid_saved_audit import ExactSolid as _i17_ExactSolid
from tools.hybrid_interval_winding_saved_audit import IntervalSolid as _i17_IntervalSolid
from tools.hybrid_interval_winding_saved_audit import POLICY_SHA256 as _i17_POLICY_SHA256
from tools.hybrid_interval_winding_saved_audit import TOLERANCE as _i17_TOLERANCE
from tools.hybrid_interval_winding_saved_audit import exact_bounds as _i17_exact_bounds
import unittest as _i18_unittest
from tools.audit_hybrid_geometry import iter_input_pins as _i18_iter_input_pins
CATEGORY = 'C'

def saved_solid(manifold, label):
    mesh = manifold.to_mesh64()
    return _i9_Solid(_i9_np.asarray(mesh.vert_properties)[:, :3], _i9_np.asarray(mesh.tri_verts), label)

class CaveSavedAuditTests(_i9_unittest.TestCase):

    def test_actual_boolean_openings_volume_and_air_route(self):
        library = _i9_manifold_library()
        rock = library.Manifold.cube([4.0, 4.0, 4.0], center=True)
        cutter = library.Manifold.cube([6.0, 1.0, 1.0], center=True)
        actual = rock - cutter
        source, void, saved = (saved_solid(value, label) for value, label in ((rock, 'source'), (cutter, 'cutter'), (actual, 'actual')))
        evidence = _i9_boolean_evidence(source, void, saved)
        self.assertAlmostEqual(evidence['excavated_volume_m3'], 4.0)
        self.assertAlmostEqual(evidence['actual_rock_volume_m3'], 60.0)
        route = _i9_air_path_evidence(source, void, saved, [[-1.5, 0.0, 0.0], [0.0, 0.0, 0.0], [1.5, 0.0, 0.0]], [[-3.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
        self.assertTrue(route['actual_air_polyline_verified'])
        self.assertEqual(len(route['portal_original_exterior_face_hits']), 2)
        mapping = _i9_vdm_mapping(void.vertices, _i9_np.zeros_like(void.vertices), void.vertices, void.triangles, [0, 1])
        self.assertTrue(mapping['immutable_portals_verified'])
        sampled = _i9_SimpleNamespace(vertices=_i9_np.array([[0.0, 10.0, 0.0], [1.0, 12.0, 0.0], [0.0, 13.0, 1.0], [1.0, 17.0, 1.0]]))
        height = _i9_sampled_top_height(sampled, {'rows': 2, 'columns': 2, 'origin_xz_m': [0.0, 0.0], 'spacing_m': 1.0}, _i9_np.zeros(3), [0.25, 0.75])
        self.assertEqual(height, 13.25)
        from tools.export_hybrid_geometry_review import caseartifact
        from tools.export_hybrid_geometry_review import render_figures
        from PIL import Image
        records = {name: {'vertices_local_xyz_m': solid.vertices.tolist(), 'triangles': solid.triangles.tolist(), 'local_origin_xyz_m': [0.0, 0.0, 0.0]} for name, solid in (('rock_before', source), ('cutter', void), ('rock_after', saved), ('removed', saved_solid(rock ^ cutter, 'removed')))}
        review = {'geometry_identity_sha256': 'tiny', 'meshes': records, 'coordinates': {'plot_origin_xyz_m': [0.0, 0.0, 0.0], 'native_origin_m_xz': [-2.0, -2.0], 'native_spacing_m': 4.0}, 'native_terrain': {'height_m': [[2.0, 2.0], [2.0, 2.0]], 'valid_mask': [[True, True], [True, True]]}, 'portals': {'sink': {'xyz_m': [-2.0, 0.0, 0.0]}, 'spring': {'xyz_m': [2.0, 0.0, 0.0]}}, 'stations': [{'origin_xyz_m': [coordinate, 0.0, 0.0], 'derived_ring_xyz_m': [[coordinate, -0.5, -0.5], [coordinate, -0.5, 0.5], [coordinate, 0.5, 0.5], [coordinate, 0.5, -0.5]]} for coordinate in (-2.0, 2.0)], 'actual_closed_core_station_indices': [0, 1], 'surface_attachments': {}, 'pins': {}, 'independent_audit_reference': {'binding_status': 'not_supplied'}, 'limitations': ['tiny fixture']}
        artifact = caseartifact(review)
        self.assertIsNone(artifact['mesh']['water'])
        self.assertEqual(artifact['mesh']['triangles'], saved.triangles.tolist())
        figures = render_figures(review)
        self.assertEqual(set(figures), {'overview.png', 'profile.png', 'oblique-3d.png'})
        for payload in figures.values():
            picture = Image.open(_i9_BytesIO(payload)).convert('RGB')
            self.assertTrue(any((low != high for low, high in picture.getextrema())))

    def test_unopened_rock_and_invalid_mesh_are_not_accepted(self):
        library = _i9_manifold_library()
        source = saved_solid(library.Manifold.cube([4.0, 4.0, 4.0], center=True), 'source')
        void = saved_solid(library.Manifold.cube([6.0, 1.0, 1.0], center=True), 'void')
        with self.assertRaises(ValueError):
            _i9_boolean_evidence(source, void, source)
        with self.assertRaises(ValueError):
            _i9_air_path_evidence(source, void, source, [[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], [[-3.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
        with self.assertRaises(ValueError):
            _i9_Solid(source.vertices, source.triangles[:-1], 'open fake solid')
        forged = source.triangles.copy()
        forged[0, 0] = len(source.vertices)
        with self.assertRaises(ValueError):
            _i9_Solid(source.vertices, forged, 'bad geometry reference')
        displacement = _i9_np.zeros_like(void.vertices)
        displacement[0, 1] = 0.01
        with self.assertRaises(ValueError):
            _i9_vdm_mapping(void.vertices, displacement, void.vertices + displacement, void.triangles, [0, 1])

def frame():
    return {'origin_world_xyz_m': [100.0, 1350.0, 200.5], 'origin_local_xyz_m': [0.0, 0.0, 0.5], 'common_local_origin_xyz_m': [100.0, 1350.0, 200.0], 'normal_local_xyz': [0.0, 0.0, 1.0], 'transverse_unit_xyz': [1.0, 0.0, 0.0], 'transverse_unit_xz': [1.0, 0.0], 'vertical_unit_xyz': [0.0, 1.0, 0.0], 'coordinate_convention': 'u_metres_Ylocal_metres_not_floor_relative', 'positive_normal': 'from_cell_to_cell_actual_horizontal_route'}

def boundary_record(shape):
    segments = []
    rings = [] if shape.is_empty else [shape.exterior, *shape.interiors]
    for ring in rings:
        for first, second in zip(list(ring.coords), list(ring.coords)[1:]):
            segments.append({'triangle_index': len(segments), 'points_uv_m': [list(first), list(second)]})
    return {'triangle_segments': segments, 'coplanar_triangle_supports': []}

def open_fixture():
    cutter, before = (_i10_box(0, 0, 2, 3), _i10_box(-1, -1, 3, 1))
    shapes = {'cutter': cutter, 'rock_before': before, 'rock_after': before.difference(cutter), 'removed': before.intersection(cutter)}
    slices = {role: boundary_record(shape) for role, shape in shapes.items()}
    parts = [([[0, 0], [2, 0]], 'actual_rock_wet_wall'), ([[2, 0], [2, 1]], 'actual_rock_wet_wall'), ([[2, 1], [2, 3]], 'engineering_lateral_wall_above_terrain'), ([[2, 3], [0, 3]], 'artificial_cutter_top_cap_not_wetted_wall'), ([[0, 3], [0, 1]], 'engineering_lateral_wall_above_terrain'), ([[0, 1], [0, 0]], 'actual_rock_wet_wall')]
    pieces = []
    for points, category in parts:
        line = _i10_LineString(points)
        sources = {role: [item['triangle_index'] for item in slices[role]['triangle_segments'] if _i10_LineString(item['points_uv_m']).intersection(line.buffer(1e-08)).length > 1e-08] for role in ('cutter', 'rock_after')}
        pieces.append({'points_uv_m': points, 'points_local_xyz_m': [[point[0], point[1], 0.5] for point in points], 'category': category, 'potential_wetted_length_m': line.length if category == 'actual_rock_wet_wall' else None, 'source_triangle_indices': sources})
    top_refs = [item['triangle_index'] for item in slices['rock_before']['triangle_segments'] if _i10_LineString(item['points_uv_m']).intersection(_i10_LineString([[0, 1], [2, 1]])).length > 0]
    record = {'kind': 'open_cut_floor', 'polygon_uv_m': [[0, 0], [2, 0], [2, 3], [0, 3]], 'polygon_local_xyz_m': [[0, 0, 0.5], [2, 0, 0.5], [2, 3, 0.5], [0, 3, 0.5]], 'cut_floor_uv_m': [[0, 0], [2, 0]], 'boundary_pieces': pieces, 'terrain_opening_free_edges': [{'points_uv_m': [[0, 1], [2, 1]], 'category': 'original_rock_top_opening_free_boundary_not_wall', 'rock_before_triangle_indices': top_refs}], 'blocked_area_m2': 0.0, 'removed_replay_difference_area_m2': 0.0, 'actual_excavated_aperture_area_m2': 2.0, 'cutter_outside_original_rock_area_m2': 4.0, 'bounded_display_aperture_area_m2': 6.0, 'pressure_slot_enlarges_face': False, 'closed_boundary_certified': False, 'open_extension': {'kind': 'explicit_engineering_vertical', 'lateral_u_m': [0, 2], 'unbounded_above_cut_floor': False, 'unbounded_only_over_supported_free_top_intervals': [{'u_interval_m': [0, 2], 'lower_boundary_uv_m': [[2, 3], [0, 3]], 'kind': 'above_saved_artificial_cap_only_not_above_actual_rock_roof'}], 'actual_rock_roof_segments_remain_bounded': True, 'artificial_cutter_roof_is_not_flow_ceiling': True, 'extension_is_engineering_not_whole_physical_path_certification': True, 'not_actual_terrain_floodplain': True}}
    return (record, slices, shapes)

class SavedFaceAuditTests(_i10_unittest.TestCase):

    def test_source_cube_slice_and_plane_reject_fabricated_support(self):
        vertices = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
        triangles = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]]
        solid = _i10_Solid(vertices, triangles, 'tiny saved cube')
        plane = frame()
        _i10_check_plane(plane, [100, 1350, 200.5], [0, 1], [100, 1350, 200])
        segments, coplanar = _i10_triangle_plane_segments(vertices, triangles, [0, 0, 0.5], [0, 0, 1], [1, 0, 0])
        self.assertEqual(len(segments), 8)
        self.assertEqual(coplanar, [])
        pin = {'path': 'synthetic', 'sha256': 'synthetic'}
        record = {'mesh_pin': pin, 'coordinate_convention': plane['coordinate_convention'], 'method': 'Mesh64_transform_slice_exact_plane', 'polygons_uv_m': [[[0, 0], [1, 0], [1, 1], [0, 1]]], 'holes_uv_m': [[]], 'area_m2': 1.0, 'coplanar_triangle_supports': [], 'triangle_segments': []}
        for ordinal, points in segments.items():
            record['triangle_segments'].append({'triangle_index': ordinal, 'vertex_indices': triangles[ordinal], 'points_uv_m': points.tolist(), 'points_local_xyz_m': [[point[0], point[1], 0.5] for point in points]})
        shape, report = _i10_audit_slice(record, solid, plane, pin)
        self.assertAlmostEqual(shape.area, 1.0)
        self.assertAlmostEqual(report['symmetric_difference_m2'], 0.0)
        wrong = _i10_copy.deepcopy(record)
        wrong['triangle_segments'].pop()
        with self.assertRaisesRegex(ValueError, 'triangle-plane support'):
            _i10_audit_slice(wrong, solid, plane, pin)
        wrong = _i10_copy.deepcopy(record)
        wrong['triangle_segments'][0]['points_uv_m'][0][1] += 0.1
        with self.assertRaisesRegex(ValueError, 'fabricated triangle-plane'):
            _i10_audit_slice(wrong, solid, plane, pin)
        wrong_frame = _i10_copy.deepcopy(plane)
        wrong_frame['origin_local_xyz_m'][2] = 0.25
        with self.assertRaisesRegex(ValueError, 'actual plane'):
            _i10_check_plane(wrong_frame, [100, 1350, 200.5], [0, 1], [100, 1350, 200])

    def test_open_cap_extension_wall_census_and_unknown_rejection(self):
        record, slices, shapes = open_fixture()
        report = _i10_audit_aperture(record, slices, shapes, frame())
        self.assertEqual(report['actual_rock_wall_length_m'], 4.0)
        self.assertEqual(report['bounded_area_m2'], 6.0)
        wrong = _i10_copy.deepcopy(record)
        wrong['boundary_pieces'][3]['category'] = 'actual_rock_wet_wall'
        wrong['boundary_pieces'][3]['potential_wetted_length_m'] = 2.0
        with self.assertRaisesRegex(ValueError, 'artificial edge'):
            _i10_audit_aperture(wrong, slices, shapes, frame())
        wrong = _i10_copy.deepcopy(record)
        wrong['open_extension']['unbounded_above_cut_floor'] = True
        with self.assertRaisesRegex(ValueError, 'engineering open extension'):
            _i10_audit_aperture(wrong, slices, shapes, frame())
        wrong_shapes = {**shapes, 'removed': _i10_Polygon()}
        with self.assertRaisesRegex(ValueError, 'empty excavation'):
            _i10_audit_aperture(record, slices, wrong_shapes, frame())
        wrong = _i10_copy.deepcopy(record)
        wrong['pressure_slot_enlarges_face'] = True
        with self.assertRaisesRegex(ValueError, 'storage slot'):
            _i10_audit_aperture(wrong, slices, shapes, frame())
        wrong = _i10_copy.deepcopy(record)
        wrong['boundary_pieces'].pop()
        with self.assertRaisesRegex(ValueError, 'boundary pieces'):
            _i10_audit_aperture(wrong, slices, shapes, frame())

class FaceRoleAuditTests(_i11_unittest.TestCase):

    def test_topological_roles_do_not_depend_on_slanted_side_slope(self):
        ring = [[-3, 1, 0], [-2, 0, 0], [0, -0.1, 0], [2, 0, 0], [3, 1, 0], [3.02, 3, 0], [-3.02, 3, 0]]
        stations = [{'derived_ring_xyz_m': [[point[0], point[1], station] for point in ring], 'floor_vertex_count': 5} for station in range(17)]
        triangles = [[0, 1, 8], [4, 5, 12], [5, 6, 13], [6, 0, 7], [0, 2, 1]]
        vdm = {'stations': stations, 'triangles': triangles}
        mesh = {'local_origin_xyz_m': [0, 0, 0], 'triangles': triangles, 'vertices_local_xyz_m': [point for station in stations for point in station['derived_ring_xyz_m']]}
        roles = _i11_topology_roles(vdm, mesh)
        self.assertEqual([item['source_role'] for item in roles], ['floor', 'lateral', 'roof', 'lateral', 'endcap'])
        wrong = _i11_copy.deepcopy(mesh)
        wrong['vertices_local_xyz_m'][5][0] += 0.1
        with self.assertRaises(ValueError):
            _i11_topology_roles(vdm, wrong)

    def test_nonadjacent_sweep_and_interior_cap_are_refused(self):
        stations = [{'derived_ring_xyz_m': [[offset, offset % 2, station] for offset in range(4)], 'floor_vertex_count': 2} for station in range(17)]
        for triangle in ([0, 1, 9], [4, 5, 6]):
            vdm = {'stations': stations, 'triangles': [triangle]}
            mesh = {'local_origin_xyz_m': [0, 0, 0], 'triangles': [triangle], 'vertices_local_xyz_m': [point for station in stations for point in station['derived_ring_xyz_m']]}
            with self.assertRaises(ValueError):
                _i11_topology_roles(vdm, mesh)

    def test_exact_role_identities_and_incident_sides_cannot_be_forged(self):
        vertices = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, 2.0], [0.0, 2.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 2.0]]
        triangles = [[0, 1, 2], [3, 5, 4], [0, 3, 1], [1, 3, 4], [1, 4, 2], [2, 4, 5], [2, 5, 0], [0, 5, 3]]
        mesh = _i11_mesh_record(vertices, triangles, [0.0, 0.0, 0.0], 'fixture')
        bottom = {'prism': mesh, 'prism_triangle_roles': ['floor', 'artificial_top_cap'] + ['lateral'] * 6, 'bottom_triangle_id': 0, 'fan_key': 'fixture', 'source_function_identity_sha256': '0' * 64, 'bottom_vertices_xyz_m': vertices[:3]}
        prisms = {'half_arms': {'sink': {'bottom_triangles': [bottom]}, 'spring': {'bottom_triangles': []}}}
        pin = {'path': 'fixture', 'sha256': '0' * 64}
        source = _i11_surface_role_sources(prisms, _i11_np.zeros(3), pin)[0]
        for depth in (1.0, 0.0):
            frame = _i11_plane_frame([0.0, 0.0, depth], [0.0, 1.0], [0.0, 0.0, 0.0])
            record = _i11_role_slice(source, frame)
            _i11_audit_role_slice(record, frame, None, None, None, prisms, pin)
            for field, value in (('intersection_node_ids', ['forged', 'forged']), ('incident_halfspace', 'forged'), ('points_local_xyz_m', [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]), ('points_uv_m', [[0.0, 0.0], [0.0, 0.0]])):
                changed = _i11_copy.deepcopy(record)
                changed['triangle_segments'][0][field] = value
                with self.assertRaises(ValueError):
                    _i11_audit_role_slice(changed, frame, None, None, None, prisms, pin)
            if record['coplanar_triangle_supports']:
                for field, value in (('intersection_node_ids', ['forged'] * 3), ('normal_dot_plane', 0.0), ('occupied_incident_side', 'forged')):
                    changed = _i11_copy.deepcopy(record)
                    changed['coplanar_triangle_supports'][0][field] = value
                    with self.assertRaises(ValueError):
                        _i11_audit_role_slice(changed, frame, None, None, None, prisms, pin)

class SavedSliceGeometryAdapterTests(_i12_unittest.TestCase):

    def test_consumes_declared_empty_slice_without_fabricating_area(self):
        domain = _i12_consume_saved_slice({'polygons_uv_m': [], 'holes_uv_m': [], 'area_m2': 0.0})
        self.assertTrue(domain.is_empty)
        self.assertEqual(domain.area, 0.0)

    def test_keeps_positive_numeric_sliver_and_hole_owner(self):
        record = {'polygons_uv_m': [[[0, 0], [1e-05, 0], [0, 1e-05]], [[2, 0], [4, 0], [4, 2], [2, 2]]], 'holes_uv_m': [[], [[[2.25, 0.25], [2.5, 0.25], [2.5, 0.5], [2.25, 0.5]]]]}
        domain = _i12_consume_saved_slice(record)
        self.assertGreater(domain.area, 0.0)
        self.assertEqual(len(domain.geoms), 2)
        description = _i12_describe_saved_slice(record)
        self.assertEqual(description['positive_area_sliver_polygon_count'], 1)
        self.assertEqual(description['hole_ownership'], [0, 1])

    def test_consumes_owned_hole_without_filling_it(self):
        record = {'polygons_uv_m': [[[0, 0], [4, 0], [4, 4], [0, 4]]], 'holes_uv_m': [[[[1, 1], [3, 1], [3, 3], [1, 3]]]], 'area_m2': 12.0}
        domain = _i12_consume_saved_slice(record)
        self.assertEqual(domain.area, 12.0)
        self.assertEqual(len(domain.interiors), 1)

    def test_rejects_hole_outside_owner_without_repair(self):
        record = {'polygons_uv_m': [[[0, 0], [1, 0], [1, 1], [0, 1]]], 'holes_uv_m': [[[[2, 2], [3, 2], [3, 3], [2, 3]]]], 'area_m2': 1.0}
        with self.assertRaisesRegex(ValueError, 'hole'):
            _i12_consume_saved_slice(record)

    def test_rejects_non_adjacent_polygon_overlap(self):
        square = [[0, 0], [2, 0], [2, 2], [0, 2]]
        record = {'polygons_uv_m': [square, [[1, 1], [3, 1], [3, 3], [1, 3]], [[10, 10], [11, 10], [11, 11], [10, 11]]], 'holes_uv_m': [[], [], []]}
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            _i12_consume_saved_slice(record)

    def test_rejects_nan_boundary_coordinate(self):
        record = {'polygons_uv_m': [[[0, 0], [1, 0], [float('nan'), 1]]], 'holes_uv_m': [[]]}
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            _i12_consume_saved_slice(record)

def box_solid(low, high, label):
    vertices = [[low[0], low[1], low[2]], [high[0], low[1], low[2]], [high[0], high[1], low[2]], [low[0], high[1], low[2]], [low[0], low[1], high[2]], [high[0], low[1], high[2]], [high[0], high[1], high[2]], [low[0], high[1], high[2]]]
    triangles = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]]
    return _i13_Solid(vertices, triangles, label)

def _test_hybrid_surface_composition_saved_audit_saved_solid(manifold, label):
    mesh = manifold.to_mesh64()
    return _i13_Solid(_i13_np.asarray(mesh.vert_properties)[:, :3], _i13_np.asarray(mesh.tri_verts, dtype=_i13_np.int64), label)

class SurfaceCompositionSavedAuditTests(_i13_unittest.TestCase):

    def test_exact_edge_membership_without_negative_depth_or_outside_clamp(self):
        fan = {'vertices_xz_m': [[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]], 'depth_at_vertices_m': [0.0, 1.0, 2.0]}
        self.assertLess(1 - 8 / 10 - 2 / 10, 0.0)
        self.assertEqual(_i13_exact_fan_cut(fan, [8.0, 2.0]), 1.2)
        self.assertIsNone(_i13_exact_fan_cut(fan, [8.0, _i13_np.nextafter(2.0, _i13_np.inf)]))
        self.assertEqual(_i13_exact_fan_cut(fan, [0.0, 0.0]), 0.0)
        patch_function = {**fan, 'depth_coefficients_m_1xz': [0.0, 0.1, 0.2], 'depth_origin_xz_m': [0.0, 0.0]}
        self.assertAlmostEqual(_i13_saved_patch_affine_depth(patch_function, [8.0, _i13_np.nextafter(2.0, _i13_np.inf)]), 1.2)
        self.assertEqual(_i13_saved_patch_affine_depth(patch_function, [10.0, 0.0]), 1.0)
        with self.assertRaisesRegex(ValueError, 'strict original patch'):
            _i13_saved_patch_affine_depth(patch_function, [-1.0, -1.0])
        with self.assertRaisesRegex(ValueError, 'invalid saved fan'):
            _i13_exact_fan_cut({**fan, 'depth_at_vertices_m': [0.0, -0.01, 2.0]}, [8.0, 2.0])

    def test_saved_boolean_increment_uses_only_remaining_rock_and_rejects_double_cut(self):
        library = _i13_manifold_library()
        original = box_solid([0, 0, 0], [4, 3, 4], 'original rock')
        gallery = box_solid([1, 0, 1], [2, 2, 3], 'original gallery')
        surface = box_solid([1, 1, 1], [3, 4, 3], 'surface cutter')
        rock, cave, carve = [solid.manifold(library) for solid in (original, gallery, surface)]
        old_after = _test_hybrid_surface_composition_saved_audit_saved_solid(rock - cave, 'old after')
        old_removed = _test_hybrid_surface_composition_saved_audit_saved_solid(rock ^ cave, 'old removed')
        combined = _test_hybrid_surface_composition_saved_audit_saved_solid(cave + carve, 'combined cutter')
        actual = _test_hybrid_surface_composition_saved_audit_saved_solid(rock - (cave + carve), 'actual after')
        extra = _test_hybrid_surface_composition_saved_audit_saved_solid(rock - cave ^ carve, 'extra removed')
        total = _test_hybrid_surface_composition_saved_audit_saved_solid(rock ^ cave + carve, 'total removed')
        report = _i13_audit_material_solids(original, old_after, old_removed, surface, combined, actual, extra, total, gallery)
        self.assertAlmostEqual(report['original_removed_m3'], 4.0)
        self.assertAlmostEqual(report['extra_removed_m3'], 6.0)
        self.assertAlmostEqual(report['total_removed_m3'], 10.0)
        self.assertAlmostEqual(report['actual_added_rock_difference_m3'], 0.0)
        with self.assertRaisesRegex(ValueError, 'extra removed'):
            _i13_audit_material_solids(original, old_after, old_removed, surface, combined, actual, total, total, gallery)
TRIANGLES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]]
FRAME = {'origin_local_xyz_m': [0.0, 0.0, 0.0], 'normal_local_xyz': [0.0, 0.0, 1.0], 'transverse_unit_xyz': [1.0, 0.0, 0.0], 'coordinate_convention': 'local_XYZ_metres_Y_vertical'}
PIN = {'artifact': 'tiny_saved_solid'}

def seal(record):
    record.pop('identity_sha256', None)
    record['identity_sha256'] = _i14_digest(record)
    return record

def box_vertices(left, bottom, right, top, depth=1.0):
    return [[left, bottom, -depth], [right, bottom, -depth], [right, top, -depth], [left, top, -depth], [left, bottom, depth], [right, bottom, depth], [right, top, depth], [left, top, depth]]

def midpoint_fixture(left, bottom, right, top, offset=0, inward=False):
    middle_x, middle_y = ((left + right) / 2, (bottom + top) / 2)
    edges = [(0, 4), (0, 5), (1, 5), (1, 6), (2, 6), (3, 6), (3, 7), (0, 7)]
    points = [[left, bottom], [middle_x, bottom], [right, bottom], [right, middle_y], [right, top], [middle_x, top], [left, top], [left, middle_y]]
    names = ['e:' + str(first + offset) + ':' + str(second + offset) for first, second in edges]
    nodes = [{'node_id': name, 'vertex_indices': [first + offset, second + offset], 'point_local_xyz_m': [point[0], point[1], 0.0], 'point_uv_m': point} for name, (first, second), point in zip(names, edges, points)]
    segments = []
    support_indices = [5, 4, 11, 10, 7, 6, 9, 8]
    for index, ordinal in enumerate(support_indices):
        pair = [index, (index + 1) % 8]
        triangle = [value + offset for value in TRIANGLES[ordinal]]
        if inward:
            pair.reverse()
            triangle.reverse()
        segments.append({'triangle_index': ordinal + offset // 8 * 12, 'vertex_indices': triangle, 'intersection_node_ids': [names[value] for value in pair], 'incident_halfspace': 'both', 'points_local_xyz_m': [nodes[value]['point_local_xyz_m'] for value in pair], 'points_uv_m': [points[value] for value in pair]})
    loops = []
    loop_ids = names[::-1] if inward else names
    references = {tuple(sorted(segment['intersection_node_ids'])): [segment['triangle_index']] for segment in segments}
    for side in ('positive', 'negative'):
        loops.append({'side': side, 'node_ids': loop_ids, 'signed_area_m2': (right - left) * (top - bottom) * (-1 if inward else 1), 'triangle_supports': [references[tuple(sorted(pair))] for pair in zip(loop_ids, loop_ids[1:] + loop_ids[:1])]})
    return (nodes, segments, loops)

def record_base():
    return {'schema': _i14_SLICE_SCHEMA, 'mesh_pin': PIN, 'method': 'original_identity_cached_rational_mesh_plane_no_CrossSection', 'numerical_policy': _i14_copy.deepcopy(_i14_NUMERICAL_POLICY), 'numerical_policy_identity_sha256': _i14_NUMERICAL_POLICY_SHA256, 'coordinate_convention': FRAME['coordinate_convention'], 'coplanar_semantics': 'closed_trace_contains_actual_original_facets_side_occupation_recorded'}

class SurfaceCompositionV2SavedAuditTests(_i14_unittest.TestCase):

    def test_shared_edges_holes_and_unsnapped_original_top(self):
        top = 3.0432591911956024
        vertices = box_vertices(-1.0, -1.0, 1.0, top) + box_vertices(-0.25, -0.25, 0.25, 0.25, 0.5)
        triangles = TRIANGLES + [[index + 8 for index in triangle[::-1]] for triangle in TRIANGLES]
        solid = _i14_Solid(vertices, triangles, 'tiny saved cavity')
        nodes, segments, loops = midpoint_fixture(-1.0, -1.0, 1.0, top)
        inner_nodes, inner_segments, inner_loops = midpoint_fixture(-0.25, -0.25, 0.25, 0.25, 8, True)
        outer = [[-1.0, -1.0], [1.0, -1.0], [1.0, top], [-1.0, top]]
        hole = [[-0.25, -0.25], [-0.25, 0.25], [0.25, 0.25], [0.25, -0.25]]
        domain = {'polygons_uv_m': [outer], 'holes_uv_m': [[hole]], 'area_m2': 2 * (top + 1) - 0.25}
        record = record_base()
        record.update(**domain, intersection_nodes=nodes + inner_nodes, triangle_segments=segments + inner_segments, coplanar_triangle_supports=[], identity_loops=loops + inner_loops, vertex_plane_classifications=[{'vertex_index': index, 'sign': -1 if index % 8 < 4 else 1, 'classification_method': 'exact_rational'} for index in range(16)], one_sided_interior_traces={side: _i14_copy.deepcopy(domain) for side in ('positive', 'negative')}, occupancy_witnesses=[{'point_uv_m': [0.75, 0.75], 'point_local_xyz_m': [0.75, 0.75, 0.0], 'classification': 'original_Mesh64_interior_two_ray_parities', 'region': 'retained_polygon', 'ray_parities': [1, 1]}, {'point_uv_m': [0.0, 0.0], 'point_local_xyz_m': [0.0, 0.0, 0.0], 'classification': 'original_Mesh64_void_two_ray_parities', 'region': 'excluded_hole', 'ray_parities': [0, 0]}])
        shape, report = _i14_audit_exact_slice(seal(record), solid, FRAME, PIN)
        self.assertEqual(shape.bounds[3], top)
        self.assertEqual(len(shape.interiors), 1)
        self.assertEqual(report['independent_hole_occupancy_probes'], 1)
        self.assertFalse(report['builder_or_slicer_called'])
        changed = _i14_copy.deepcopy(record)
        changed['intersection_nodes'][4]['point_uv_m'][1] = float(_i14_np.nextafter(top, -_i14_np.inf))
        with self.assertRaisesRegex(ValueError, 'shared-edge intersection'):
            _i14_audit_exact_slice(seal(changed), solid, FRAME, PIN)
        changed = _i14_copy.deepcopy(record)
        changed['identity_loops'].pop()
        with self.assertRaisesRegex(ValueError, 'exhaust'):
            _i14_audit_exact_slice(seal(changed), solid, FRAME, PIN)
        changed = _i14_copy.deepcopy(record)
        changed['holes_uv_m'] = [[]]
        with self.assertRaisesRegex(ValueError, 'holes differ'):
            _i14_audit_exact_slice(seal(changed), solid, FRAME, PIN)

    def test_coplanar_closed_boundary_retains_actual_occupied_side_and_policy(self):
        from shapely.geometry import GeometryCollection
        from shapely.geometry import LineString
        from shapely.geometry import Point
        from shapely.geometry import Polygon
        contact = {'polygons_uv_m': [], 'holes_uv_m': [], 'area_m2': 0.0, 'contact_lines_uv_m': [[[0.0, 0.0], [1.0, 0.0]]], 'contact_points_uv_m': [[2.0, 0.0]]}
        touching = GeometryCollection([LineString([[0.0, 0.0], [1.0, 0.0]]), Point(2.0, 0.0)])
        self.assertEqual(_i14_check_shape(contact, touching, 'tiny contact', require_contacts=True), 0.0)
        with self.assertRaisesRegex(ValueError, 'components/holes'):
            _i14_check_shape(contact, GeometryCollection([touching, Polygon([[0.0, 1.0], [1.0, 1.0], [1.0, 2.0]])]), 'tiny contact', require_contacts=True)
        changed_contact = {**contact, 'contact_lines_uv_m': []}
        with self.assertRaisesRegex(ValueError, 'contact lines'):
            _i14_check_shape(changed_contact, touching, 'tiny contact', require_contacts=True)
        vertices = box_vertices(-1.0, -1.0, 1.0, 1.0)
        solid = _i14_Solid(vertices, TRIANGLES, 'tiny capped solid')
        frame = {**FRAME, 'origin_local_xyz_m': [0.0, 0.0, 1.0]}
        names = ['v:' + str(index) for index in range(4, 8)]
        nodes = [{'node_id': name, 'vertex_indices': [index], 'point_local_xyz_m': vertices[index], 'point_uv_m': vertices[index][:2]} for name, index in zip(names, range(4, 8))]
        segments = []
        for ordinal, first, second in ((5, 4, 5), (11, 5, 6), (6, 6, 7), (8, 7, 4)):
            segments.append({'triangle_index': ordinal, 'vertex_indices': TRIANGLES[ordinal], 'intersection_node_ids': ['v:' + str(first), 'v:' + str(second)], 'incident_halfspace': 'negative', 'points_local_xyz_m': [vertices[first], vertices[second]], 'points_uv_m': [vertices[first][:2], vertices[second][:2]]})
        caps = [{'triangle_index': ordinal, 'vertex_indices': TRIANGLES[ordinal], 'intersection_node_ids': ['v:' + str(index) for index in TRIANGLES[ordinal]], 'polygon_uv_m': [vertices[index][:2] for index in TRIANGLES[ordinal]], 'normal_dot_plane': 4.0, 'occupied_incident_side': 'negative'} for ordinal in (2, 3)]
        domain = {'polygons_uv_m': [[vertices[index][:2] for index in range(4, 8)]], 'holes_uv_m': [[]], 'area_m2': 4.0}
        record = record_base()
        record.update(**domain, intersection_nodes=nodes, triangle_segments=segments, coplanar_triangle_supports=caps, identity_loops=[{'side': 'negative', 'node_ids': names, 'signed_area_m2': 4.0, 'triangle_supports': [[5], [11], [6], [8]]}], vertex_plane_classifications=[{'vertex_index': index, 'sign': -1 if index < 4 else 0, 'classification_method': 'exact_rational'} for index in range(8)], one_sided_interior_traces={'negative': domain, 'positive': {'polygons_uv_m': [], 'holes_uv_m': [], 'area_m2': 0.0}}, occupancy_witnesses=[{'point_uv_m': [0.0, 0.0], 'point_local_xyz_m': [0.0, 0.0, 1.0], 'classification': 'original_oriented_coplanar_boundary_facet', 'region': 'retained_polygon', 'coplanar_triangle_indices': [2, 3]}])
        shape, report = _i14_audit_exact_slice(seal(record), solid, frame, PIN)
        self.assertEqual(shape.area, 4.0)
        self.assertEqual(report['coplanar_triangles'], 2)
        changed = _i14_copy.deepcopy(record)
        changed['coplanar_triangle_supports'][0]['occupied_incident_side'] = 'positive'
        with self.assertRaisesRegex(ValueError, 'coplanar facet'):
            _i14_audit_exact_slice(seal(changed), solid, frame, PIN)
        changed = _i14_copy.deepcopy(record)
        changed['numerical_policy']['identity'] = 'rounded_bucket'
        changed['numerical_policy_identity_sha256'] = _i14_digest(changed['numerical_policy'])
        with self.assertRaisesRegex(ValueError, 'policy binding'):
            _i14_audit_exact_slice(seal(changed), solid, frame, PIN)
        with self.assertRaisesRegex(ValueError, 'source/numerical'):
            _i14_audit_exact_slice(record, solid, frame, {'artifact': 'other'})

class SurfaceCompositionV3SavedAuditTests(_i15_unittest.TestCase):

    def test_exact_positive_facets_retained_with_area_volume_and_true_zero_refused(self):
        vertices = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1e-20, 0.0], [0.0, 0.0, 1.0]]
        triangles = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        solid = _i15_ExactSolid(vertices, triangles, 'tiny positive original facets')
        evidence = solid.validation_evidence
        self.assertEqual(evidence['retained_triangle_count'], 4)
        self.assertEqual(evidence['deleted_triangle_count'], 0)
        self.assertEqual(evidence['exact_zero_triangle_count'], 0)
        self.assertEqual(len(evidence['triangle_area_le_1e_minus14_m2_ids']), 2)
        self.assertEqual(evidence['minimum_positive_area_m2_approx'], 5e-21)
        self.assertEqual(solid.exact_signed_volume, _i15_Fraction.from_float(1e-20) / 6)
        self.assertTrue(evidence['all_original_faces_retained'])
        self.assertEqual(solid.triangles.tolist(), triangles)
        changed = _i15_copy.deepcopy(vertices)
        changed[2] = [0.0, 0.0, 0.0]
        with self.assertRaisesRegex(ValueError, 'exact-zero'):
            _i15_ExactSolid(changed, triangles)
        with self.assertRaisesRegex(ValueError, 'nonpositive exact'):
            _i15_ExactSolid(vertices, [triangle[::-1] for triangle in triangles])
        changed_faces = _i15_copy.deepcopy(triangles)
        changed_faces[0].reverse()
        with self.assertRaisesRegex(ValueError, 'orientation'):
            _i15_ExactSolid(vertices, changed_faces)

    def test_rational_identity_collapse_certificate_hierarchy_and_partial_refusal(self):
        frame = {'origin_local_xyz_m': [0.0, 0.0, 0.0], 'normal_local_xyz': [0.0, 0.0, 1.0], 'transverse_unit_xyz': [1.0, 0.0, 0.0]}
        source = _i15_SimpleNamespace(vertices=_i15_np.asarray([[1.0, 1.0, 1.0], [1.0, _i15_np.nextafter(1.0, _i15_np.inf), 1.0], [1.0, 1.0, -2.0 ** (-60)]]), triangles=_i15_np.asarray([[0, 1, 2]]))
        nodes, segments, _, _ = _i15_audit.audit_hybrid_surface_composition_mechanism_3_independent_triangle_trace(source, frame)
        segment = segments[0]
        self.assertEqual(segment['points_uv_m'][0], segment['points_uv_m'][1])
        self.assertNotEqual(segment['rational_points_uv_m'][0], segment['rational_points_uv_m'][1])
        self.assertGreater(_i15_Fraction(segment['orientation_rational']), 0)
        self.assertEqual(segment['exact_orientation_sign'], 1)
        self.assertIn('orientation_before_reversal_rational', segment)
        self.assertEqual(len(nodes), 2)
        exact = [[_i15_Fraction(-1), _i15_Fraction(-1)], [_i15_Fraction(1), _i15_Fraction(-1)], [_i15_Fraction(1), _i15_Fraction(1)], [_i15_Fraction(1) - _i15_Fraction(1, 2 ** 56), _i15_Fraction(1)], [_i15_Fraction(-1), _i15_Fraction(1)]]
        names = ['v:' + str(index) for index in range(5)]
        loop_nodes = {name: {'rational_uv_m': list(map(str, point)), 'point_uv_m': list(map(float, point))} for name, point in zip(names, exact)}
        loop_segments = {index: {'intersection_node_ids': [name, names[(index + 1) % 5]], 'incident_halfspace': 'both'} for index, name in enumerate(names)}
        display_ids = [names[index] for index in (0, 1, 2, 4)]
        area = _i15_audit.rational_area(exact)
        error = 2.0 ** (-56)
        exact_bound = 16 * _i15_Fraction.from_float(error) + _i15_Fraction.from_float(_i15_math.nextafter(_i15_math.pi, _i15_math.inf)) * _i15_Fraction.from_float(error) ** 2
        rounded_bound = float(exact_bound)
        if _i15_Fraction.from_float(rounded_bound) < exact_bound:
            rounded_bound = _i15_math.nextafter(rounded_bound, _i15_math.inf)
        loop = {'side': 'positive', 'node_ids': names, 'display_loop_node_ids': display_ids, 'triangle_supports': [[index] for index in range(5)], 'signed_area_m2_rational': str(area), 'signed_area_m2': float(area), 'display_signed_area_m2_rational': '4', 'area_error_m2': 0.0, 'maximum_projection_distance_m': error, 'conservative_projection_area_bound_m2': rounded_bound, 'maximum_projection_distance_l1_rational': str(_i15_Fraction.from_float(error)), 'display_perimeter_l1_rational': '8', 'projection_area_bound_rational': str(exact_bound), 'containment_query_uv_rational': ['0', '0'], 'exact_parent_loop_index': None, 'display_parent_loop_index': None, 'hierarchy_certified': True}
        shape, bound = _i15_audit.certified_side([loop], 'positive', loop_nodes, loop_segments)
        self.assertEqual(shape.area, 4.0)
        self.assertLess(bound, 1e-08)
        self.assertEqual(bound, exact_bound)
        self.assertGreaterEqual(_i15_Fraction.from_float(loop['conservative_projection_area_bound_m2']), bound)
        self.assertEqual(_i15_audit.area_upper(0.0, 0.0), _i15_math.nextafter(0.0, _i15_math.inf))
        changed = _i15_copy.deepcopy(loop)
        changed['projection_area_bound_rational'] = '0'
        with self.assertRaisesRegex(ValueError, 'certificate'):
            _i15_audit.certified_side([changed], 'positive', loop_nodes, loop_segments)
        changed = _i15_copy.deepcopy(loop)
        changed['node_ids'].remove(names[3])
        with self.assertRaises(ValueError):
            _i15_audit.certified_side([changed], 'positive', loop_nodes, loop_segments)
        changed = _i15_copy.deepcopy(loop)
        changed['display_parent_loop_index'] = 0
        with self.assertRaisesRegex(ValueError, 'hierarchy'):
            _i15_audit.certified_side([changed], 'positive', loop_nodes, loop_segments)
        with self.assertRaisesRegex(ValueError, 'self-intersecting'):
            _i15_audit.check_rational_boundaries([[[_i15_Fraction(0), _i15_Fraction(0)], [_i15_Fraction(2), _i15_Fraction(2)], [_i15_Fraction(0), _i15_Fraction(2)], [_i15_Fraction(2), _i15_Fraction(0)]]])

        def failed_after_material(pin, progress):
            progress.update(native_half_arm_sources_verified=True, materials_verified=True, material={'independent_boolean_verified': True})
            raise ValueError('saved whole port refused')
        with _i15_patch.object(_i15_audit, 'audit_complete', side_effect=failed_after_material):
            report = _i15_audit.audit_hybrid_surface_composition_mechanism_3_audit({'path': 'unused-tiny', 'sha256': 'unused-tiny'})
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(report['native_half_arm_sources_verified'])
        self.assertTrue(report['materials_verified'])
        self.assertFalse(report['two_sided_complete_port_verified'])
        self.assertFalse(report['hydraulic_constitutive_law_accepted'])

def sealed(record):
    record = dict(record)
    record.pop('identity_sha256', None)
    record['identity_sha256'] = _i16_digest(record)
    return record

class SurfaceCompositionV4SavedAuditTests(_i16_unittest.TestCase):

    def test_native_identity_explicitly_from_sections_preserves_original_sha_only_pin(self):
        identity = 'a' * 64
        manifest = {'identity_sha256': identity, 'metadata': {'origin_m_xz': [0.0, 0.0], 'spacing_m': 1.0}}
        with _i16_tempfile.TemporaryDirectory(dir=_i16_audit.ROOT / '.scratch') as temporary:
            path = _i16_Path(temporary) / 'tiny-native.npz'
            _i16_np.savez_compressed(path, manifest=_i16_np.frombuffer(_i16_json.dumps(manifest).encode('utf-8'), dtype=_i16_np.uint8), height_m=_i16_np.asarray([[1.0, 2.0], [3.0, 4.0]]), valid_mask=_i16_np.ones((2, 2), dtype=bool), protected_mask=_i16_np.zeros((2, 2), dtype=bool), open_boundary_mask=_i16_np.zeros((2, 2), dtype=bool), cell_owner=_i16_np.zeros((2, 2), dtype=_i16_np.int64), contribution_owner=_i16_np.zeros((2, 2), dtype=_i16_np.int64), node_unknown_contact=_i16_np.asarray([False]))
            pin = {'path': str(path.resolve()), 'sha256': _i16_file_sha256(path)}
            before = _i16_copy.deepcopy(pin)
            native, binding = _i16_load_native_bound(pin, identity, [0], {'covered_native_cell_ids': [], 'stage_by_leaf': []})
            self.assertEqual(native.sample([0.5, 0.5])['height_m'], 2.5)
            self.assertEqual(pin, before)
            self.assertNotIn('identity_sha256', pin)
            self.assertEqual(binding['expected_hierarchy_identity_sha256'], binding['manifest_hierarchy_identity_sha256'])
            self.assertFalse(binding['original_inputs_or_pin_modified'])
            with self.assertRaisesRegex(ValueError, 'manifest/sections'):
                _i16_load_native_bound(pin, 'b' * 64, [0], {'covered_native_cell_ids': [], 'stage_by_leaf': []})
            with self.assertRaisesRegex(ValueError, 'optional hierarchy pin'):
                _i16_load_native_bound({**pin, 'identity_sha256': 'b' * 64}, identity, [0], {'covered_native_cell_ids': [], 'stage_by_leaf': []})

    def test_validated_view_binds_all_original_arrays_flags_volume_and_failure_stage(self):
        vertices = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1e-20, 0.0], [0.0, 0.0, 1.0]]
        triangles = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        validated = _i16_ExactSolid(vertices, triangles, 'tiny existing evidence')
        evidence = validated.validation_evidence
        mesh = sealed({'schema': 'td-hybrid-local-solid-mesh-v1', 'role': 'tiny', 'local_origin_xyz_m': [0.0, 0.0, 0.0], 'vertices_local_xyz_m': vertices, 'triangles': triangles, 'signed_volume_m3': validated.signed_volume})
        view = _i16_ValidatedSolid(mesh, evidence, 'tiny byte-bound view')
        self.assertEqual(view.vertices.tolist(), vertices)
        self.assertEqual(view.triangles.tolist(), triangles)
        self.assertEqual(view.exact_signed_volume, validated.exact_signed_volume)
        self.assertIs(view.validation_evidence, evidence)
        changed = _i16_copy.deepcopy(mesh)
        changed['vertices_local_xyz_m'][1][0] = 2.0
        with self.assertRaisesRegex(ValueError, 'digest'):
            _i16_ValidatedSolid(sealed(changed), evidence, 'changed arrays')
        changed_evidence = _i16_copy.deepcopy(evidence)
        changed_evidence['all_original_faces_retained'] = False
        with self.assertRaisesRegex(ValueError, 'closed/oriented/retained'):
            _i16_ValidatedSolid(mesh, changed_evidence, 'incomplete retained proof')
        changed_evidence = _i16_copy.deepcopy(evidence)
        changed_evidence['exact_signed_volume_m3'] = ['1', '1']
        with self.assertRaisesRegex(ValueError, 'exact volume'):
            _i16_ValidatedSolid(mesh, changed_evidence, 'changed volume proof')

        def fail_native(pin, parent_pin, report):
            report['current_stage'] = 'native_manifest_binding'
            report['inherited_evidence'] = {'mesh_validation_inherited': True}
            raise KeyError('manifest-test-field')
        with _i16_patch.object(_i16_audit, 'resume', side_effect=fail_native):
            report = _i16_audit.audit_hybrid_surface_composition_mechanism_4_audit({'sha256': 'tiny'}, {'sha256': 'tiny'})
        self.assertEqual(report['status'], 'refused')
        self.assertEqual(report['failure_stage'], 'native_manifest_binding')
        self.assertEqual(report['failures'][0]['error_type'], 'KeyError')
        self.assertIn('manifest-test-field', report['errors'][0])
        self.assertTrue(report['inherited_evidence']['mesh_validation_inherited'])
        self.assertFalse(report['native_half_arm_sources_verified'])
        self.assertFalse(report['two_sided_complete_port_verified'])

class SurfaceCompositionV5SavedAuditTests(_i17_unittest.TestCase):

    def test_thin_saved_solid_has_certified_interior_and_void_without_global_mutation(self):
        vertices = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1e-12, 0.0], [0.0, 0.0, 1.0]]
        triangles = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        original = _i17_ExactSolid(vertices, triangles, 'tiny thin original')
        queries = []
        wrapper = _i17_IntervalSolid(original, {'path': 'tiny immutable mesh', 'sha256': 'a' * 64}, queries)
        before = _i17_mpmath.iv.dps
        self.assertEqual(wrapper.winding([0.2, 2e-13, 0.2]), 1.0)
        self.assertEqual(wrapper.winding([2.0, 2e-13, 2.0]), 0.0)
        self.assertEqual(_i17_mpmath.iv.dps, before)
        self.assertEqual(wrapper.vertices.tolist(), vertices)
        self.assertEqual(wrapper.triangles.tolist(), triangles)
        self.assertEqual(wrapper.signed_volume, original.signed_volume)
        for query in queries:
            lower, upper = (_i17_Fraction(query['lower_rational']), _i17_Fraction(query['upper_rational']))
            target = query['certified_target']
            self.assertTrue(query['verified'])
            self.assertLess(target - _i17_TOLERANCE, lower)
            self.assertLess(upper, target + _i17_TOLERANCE)
            self.assertEqual(query['policy_identity_sha256'], _i17_POLICY_SHA256)

    def test_exact_boundary_and_vertex_refused_and_library_bounds_are_not_rounded_float_proof(self):
        solid = _i17_ExactSolid([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], 'tiny')
        queries = []
        wrapper = _i17_IntervalSolid(solid, {'sha256': 'b' * 64}, queries)
        with self.assertRaisesRegex(ValueError, 'exact triangle boundary'):
            wrapper.winding([0.25, 0.25, 0.0])
        with self.assertRaisesRegex(ValueError, 'touches saved vertex'):
            wrapper.winding([0.0, 0.0, 0.0])
        self.assertTrue(all((not query['verified'] and 'error' in query for query in queries)))
        budget_queries = [{} for _ in range(512)]
        budget_limited = _i17_IntervalSolid(solid, {'sha256': 'c' * 64}, budget_queries)
        with self.assertRaisesRegex(ValueError, 'query budget'):
            budget_limited.winding([0.2, 0.2, 0.2])
        self.assertFalse(budget_queries[-1]['verified'])
        context = _i17_MPIntervalContext()
        context.dps = 50
        lower, upper = _i17_exact_bounds(context.mpf(1) / context.mpf(3))
        self.assertLess(lower, _i17_Fraction(1, 3))
        self.assertLess(_i17_Fraction(1, 3), upper)
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            _i17_exact_bounds(context.mpf(['-inf', 'inf']))

class SurfaceCompositionV6SavedAuditTests(_i18_unittest.TestCase):

    def test_explicit_pin_walk_ignores_container_dicts_and_keeps_nested_pins(self):
        record = {'inputs': {'geometry': {'path': 'g', 'sha256': '1'}, 'geometry_audit': {'path': 'ga', 'sha256': '2'}, 'graph': {'path': 'gr', 'sha256': '3'}, 'original_source_sampling': {'path': 's', 'sha256': '4'}, 'surface_attachments': {'path': 'a', 'sha256': '5'}, 'vdm': {'path': 'v', 'sha256': '6'}, 'mesh_pins': {'rock_after': {'path': 'm', 'sha256': '7'}}, 'surface_nodes': {'sink': {'path': 'n', 'sha256': '8'}}, 'ordinary_metadata': {'units': 'm', 'origin': [0, 0, 0]}}}
        walked = list(_i18_iter_input_pins(record))
        self.assertEqual([label for label, _ in walked], ['inputs.geometry', 'inputs.geometry_audit', 'inputs.graph', 'inputs.original_source_sampling', 'inputs.surface_attachments', 'inputs.vdm', 'inputs.mesh_pins.rock_after', 'inputs.surface_nodes.sink'])
        self.assertNotIn('ordinary_metadata', [label for label, _ in walked])
