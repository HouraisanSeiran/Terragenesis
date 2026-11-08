"""Consolidated test_hybrid_geometry implementations; numeric expressions preserved."""
from __future__ import annotations
import json as _i0_json
import unittest as _i0_unittest
import numpy as _i0_np
from terrain_pipeline.hybrid_geometry import Parameters as _i0_Parameters
from terrain_pipeline.hybrid_geometry import build_charts as _i0_build_charts
from terrain_pipeline.hybrid_geometry import build_rock as _i0_build_rock
from terrain_pipeline.hybrid_geometry import manifold_from_record as _i0_manifold_from_record
from terrain_pipeline.hybrid_geometry import mesh_record as _i0_mesh_record
from terrain_pipeline.hybrid_geometry import cell_record as _i0_cell_record
from terrain_pipeline.hybrid_geometry import closed_rock_section as _i0_closed_rock_section
from terrain_pipeline.hybrid_geometry import portal_knots as _i0_portal_knots
from terrain_pipeline.hybrid_geometry import seal as _i0_seal
from terrain_pipeline.hybrid_geometry import signed_volume as _i0_signed_volume
from terrain_pipeline.hybrid_geometry import void_witnesses as _i0_void_witnesses
from terrain_pipeline.hybrid_hydraulics import Model as _i0_Model
from fractions import Fraction as _i1_Fraction
import hashlib as _i1_hashlib
import json as _i1_json
from pathlib import Path as _i1_Path
import unittest as _i1_unittest
from shapely.geometry import Polygon as _i1_Polygon
from tools.hybrid_geometry_audit_base import saved_slice_geometry as _i1_saved_slice_geometry
from tools.hybrid_saved_slice_geometry_adapter import consume_saved_slice as _i1_consume_saved_slice
import json as _i2_json
import unittest as _i2_unittest
import numpy as _i2_np
from shapely.geometry import Polygon as _i2_Polygon
from terrain_pipeline.hybrid_geometry import classify_aperture as _i2_classify_aperture
from terrain_pipeline.hybrid_geometry import plane_frame as _i2_plane_frame
from terrain_pipeline.hybrid_geometry import project as _i2_project
from terrain_pipeline.hybrid_geometry import hybrid_river_faces_slice_solid as _i2_slice_solid
from terrain_pipeline.hybrid_geometry import unproject as _i2_unproject
import unittest as _i3_unittest
import numpy as _i3_np
from shapely.geometry import LineString as _i3_LineString
from shapely.geometry import Polygon as _i3_Polygon
from terrain_pipeline.hybrid_geometry import sweep_triangles as _i3_sweep_triangles
from terrain_pipeline.hybrid_geometry import lower_floor as _i3_lower_floor
from terrain_pipeline.hybrid_geometry import hybrid_river_faces_slice_solid as _i3_legacy_slice_solid
from terrain_pipeline.hybrid_geometry import hybrid_river_faces_mechanism_2_classify_aperture as _i3_classify_aperture
from terrain_pipeline.hybrid_geometry import plane_frame as _i3_plane_frame
from terrain_pipeline.hybrid_geometry import role_slice as _i3_role_slice
from terrain_pipeline.hybrid_geometry import seal as _i3_seal
from terrain_pipeline.hybrid_geometry import hybrid_mesh_plane_mechanism_2_slice_solid as _i3_slice_solid
from terrain_pipeline.hybrid_geometry import surface_role_sources as _i3_surface_role_sources
from terrain_pipeline.hybrid_geometry import vdm_role_source as _i3_vdm_role_source
import json as _i4_json
import unittest as _i4_unittest
from dataclasses import FrozenInstanceError as _i4_FrozenInstanceError
from terrain_pipeline.hybrid_geometry import build_graph as _i4_build_graph
from terrain_pipeline.hybrid_geometry import load_graph as _i4_load_graph
from terrain_pipeline.hybrid_geometry import native_bed_pieces as _i4_native_bed_pieces
from terrain_pipeline.hybrid_geometry import port_floor_xyz as _i4_port_floor_xyz
import math as _i5_math
import unittest as _i5_unittest
import numpy as _i5_np
from terrain_pipeline import hybrid_geometry as _i5_conduit
from terrain_pipeline.hybrid_geometry import ALGORITHM as _i5_ALGORITHM
from terrain_pipeline.hybrid_geometry import CONDUIT_POLICY_SHA256 as _i5_CONDUIT_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import FLAGS as _i5_FLAGS
from terrain_pipeline.hybrid_geometry import HYBRID_ROCK_BOOLEAN_POLICY as _i5_POLICY
from terrain_pipeline.hybrid_geometry import HYBRID_ROCK_BOOLEAN_POLICY_SHA256 as _i5_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import RESULT_SCHEMA as _i5_RESULT_SCHEMA
from terrain_pipeline.hybrid_geometry import HYBRID_ROCK_BOOLEAN_SCHEMA as _i5_SCHEMA
from terrain_pipeline.hybrid_geometry import BooleanParameters as _i5_BooleanParameters
from terrain_pipeline.hybrid_geometry import combine as _i5_combine
from terrain_pipeline.hybrid_geometry import census as _i5_census
from terrain_pipeline.hybrid_geometry import excavate as _i5_excavate
from terrain_pipeline.hybrid_geometry import frustum_record as _i5_frustum_record
from terrain_pipeline.hybrid_geometry import octagon_ring as _i5_octagon_ring
from terrain_pipeline.hybrid_geometry import polygon_prism_record as _i5_polygon_prism_record
from terrain_pipeline.hybrid_geometry import solid_from_record as _i5_solid_from_record
from terrain_pipeline.hybrid_geometry import sphere_record as _i5_sphere_record
from terrain_pipeline.hybrid_geometry import identity as _i5_identity
import json as _i6_json
import unittest as _i6_unittest
from terrain_pipeline.hybrid_geometry import hybrid_surface_prisms_canonical_boundary_witness as _i6_canonical_boundary_witness
from terrain_pipeline.hybrid_geometry import hybrid_surface_prisms_exact_depth as _i6_exact_depth
from terrain_pipeline.hybrid_geometry import hybrid_surface_prisms_saved_patch_depth as _i6_saved_patch_depth
from terrain_pipeline.hybrid_geometry import hybrid_surface_prisms_triangular_prism as _i6_triangular_prism
from terrain_pipeline.hybrid_geometry import hybrid_surface_material_volume_ledger as _i6_volume_ledger
from terrain_pipeline.hybrid_geometry import manifold_from_record as _i6_manifold_from_record
import json as _i7_json
from pathlib import Path as _i7_Path
import tempfile as _i7_tempfile
import unittest as _i7_unittest
import numpy as _i7_np
from shapely.geometry import GeometryCollection as _i7_GeometryCollection
from shapely.geometry import LineString as _i7_LineString
from shapely.geometry import Point as _i7_Point
from shapely.geometry import Polygon as _i7_Polygon
from terrain_pipeline.hybrid_geometry import manifold_from_record as _i7_manifold_from_record
from terrain_pipeline.hybrid_geometry import mesh_record as _i7_mesh_record
from terrain_pipeline.hybrid_geometry import slice_solid as _i7_slice_solid
from terrain_pipeline.hybrid_geometry import triangle_supports as _i7_triangle_supports
from terrain_pipeline.hybrid_geometry import plane_frame as _i7_plane_frame
from terrain_pipeline.hybrid_geometry import seal as _i7_seal
from terrain_pipeline.hybrid_geometry import _domain as _i7__domain
from tools.prepare_hybrid_geometry import refused_from_stage as _i7_refused_from_stage
from tools.prepare_hybrid_geometry import prepare_hybrid_surface_composition_save as _i7_save
from fractions import Fraction as _i8_Fraction
import json as _i8_json
import unittest as _i8_unittest
import numpy as _i8_np
from terrain_pipeline.hybrid_geometry import _side as _i8__side
from terrain_pipeline.hybrid_geometry import _trace as _i8__trace
from terrain_pipeline.hybrid_geometry import ceil_fraction as _i8_ceil_fraction
from terrain_pipeline.hybrid_geometry import hybrid_mesh_plane_mechanism_2_slice_solid as _i8_slice_solid
from terrain_pipeline.hybrid_geometry import plane_frame as _i8_plane_frame
CATEGORY = 'C'

def port_at(z_m):
    profile = [[2.0, 0.0, z_m], [1.0, 0.0, z_m], [-1.0, 0.0, z_m], [-2.0, 0.0, z_m]]
    segments = []
    for ordinal, (first, second) in enumerate(zip(profile, profile[1:])):
        segments.append({'profile_segment_index': ordinal, 'points_xyz_m': [first, second], 'native_pieces': [{'interval_t01': [0.0, 1.0], 'start_xz_m': [first[0], z_m], 'end_xz_m': [second[0], z_m], 'depth_coefficients_m_t01': [0.0, 0.0], 'source': {'source_coefficients_m_t012': [0.0, 0.0, 0.0]}}]})
    return {'status': 'candidate', 'rejection_reasons': [], 'flow_unit_xz': [0.0, 1.0], 'profile': {'profile_xyz_m': profile, 'profile_segments': segments}}

def flat_sampler(point):
    return {'derived_bed_m': 0.0, 'cut_depth_m': 0.0, 'fan_keys': [], 'source_sample': {'height_m': 0.0, 'wet_source_support': False, 'rejection_reasons': []}}

class CaveGeometryTests(_i0_unittest.TestCase):

    def test_boolean_two_real_openings_closed_rock_and_immutable_charts(self):
        parameters = _i0_Parameters(stations=9, crop_margin_m=4.0)
        vdm = _i0_build_charts(port_at(0.0), port_at(60.0), [0.0, 0.0, 0.0], [0.0, 0.0, 60.0], parameters)
        origin = _i0_np.array([0.0, 0.0, 0.0])
        rock_record, sampling = _i0_build_rock(vdm, flat_sampler, parameters, origin)
        before = _i0_manifold_from_record(rock_record)
        vertices = _i0_np.array([station['derived_ring_xyz_m'] for station in vdm['stations']]).reshape(-1, 3)
        cutter = _i0_manifold_from_record(_i0_mesh_record(vertices, vdm['triangles'], origin, 'cutter'))
        after, removed = (before - cutter, before ^ cutter)
        path, segments, openings = _i0_void_witnesses(before, after, removed, vdm, origin, flat_sampler)
        self.assertEqual(set(openings), {'sink', 'spring'})
        self.assertEqual(len(path), 9)
        self.assertTrue(all((not segment['rock_after_hits'] for segment in segments)))
        self.assertAlmostEqual(before.volume() - after.volume(), removed.volume(), places=8)
        self.assertGreater(removed.volume(), 0)
        self.assertGreater(_i0_signed_volume(vertices, vdm['triangles']), 0)
        for station in vdm['stations']:
            _i0_np.testing.assert_array_equal(_i0_np.array(station['reference_ring_xyz_m']) + _i0_np.array(station['displacement_ring_xyz_m']), station['derived_ring_xyz_m'])
        for station in (vdm['stations'][0], vdm['stations'][-1]):
            self.assertFalse(_i0_np.any(station['displacement_ring_xyz_m']))
        self.assertLess(sampling['top_vertex_count'], 300000)
        cells = [_i0_cell_record(station, 'underground', 'engineered:underground', 7.5, parameters, {'vdm_station_index': ordinal}, closed_rock=2 <= ordinal <= 6) for ordinal, station in enumerate(vdm['stations'])]
        links = []
        for ordinal, (first, second) in enumerate(zip(cells, cells[1:])):
            kind = {('surface', 'surface'): 'surface_half_arm', ('surface', 'underground'): 'sink_exchange', ('underground', 'underground'): 'conduit', ('underground', 'surface'): 'spring_exchange'}[first['kind'], second['kind']]
            links.append({'link_id': str(ordinal), 'from_cell_id': first['cell_id'], 'to_cell_id': second['cell_id'], 'kind': kind, 'length_m': 7.5})
        model = _i0_Model.from_geometry({'hydraulic_cells': cells, 'hydraulic_links': links})
        self.assertEqual(model.cells[0].section.kind, 'open_polyline')
        self.assertEqual(model.cells[2].section.kind, 'closed_polygon')
        self.assertEqual(cells[0]['route_region'], 'underground')
        classifications = [_i0_closed_rock_section([{'actual_sampled_top_cover_m': -point[1]} for point in _i0_np.array(station['derived_ring_xyz_m'])]) for station in vdm['stations']]
        self.assertTrue(all((type(value) is bool for value in classifications)))
        self.assertTrue(any(classifications))
        self.assertFalse(all(classifications))
        saved = _i0_seal({'station_source_cover_witnesses': [{'physical_closed_rock_section': value} for value in classifications], 'hydraulic_cells': cells, 'hydraulic_links': links})
        self.assertEqual(_i0_json.loads(_i0_json.dumps(saved, allow_nan=False)), saved)
        self.assertTrue(_i0_closed_rock_section([{'actual_sampled_top_cover_m': _i0_np.float64(0.5)}] * 4))
        self.assertFalse(_i0_closed_rock_section([{'actual_sampled_top_cover_m': _i0_np.nextafter(0.5, 0.0)}] * 4))
        with self.assertRaises(TypeError):
            _i0_seal({'unsupported_numpy_bool': _i0_np.bool_(True)})

    def test_refused_negative_quadratic_profile_and_bounded_parameters(self):
        port = port_at(0.0)
        port['profile']['profile_segments'][0]['native_pieces'][0]['depth_coefficients_m_t01'] = [-1e-16, 0.0]
        with self.assertRaises(ValueError):
            _i0_portal_knots(port)
        port = port_at(0.0)
        port['profile']['profile_segments'][1]['native_pieces'][0]['source']['source_coefficients_m_t012'][2] = 0.01
        with self.assertRaises(ValueError):
            _i0_portal_knots(port)
        port = port_at(0.0)
        port['rejection_reasons'] = ['protected_source']
        with self.assertRaises(ValueError):
            _i0_portal_knots(port)
        with self.assertRaises(ValueError):
            _i0_Parameters(rock_spacing_m=0.01)
ROOT = _i1_Path(__file__).resolve().parents[1]
CURRENT = ROOT / '.scratch/module-version-consolidation-20261022/current-geometry-run04'
ORIGINAL = ROOT / 'verification/natural-river-network/hybrid-surface-composition-20261006-03/composition.json'
CURRENT_SHA256 = '3bb73b2843316ebe89766c07684b7a31f96099498eb028b5e4f5431498c2efc4'
ORIGINAL_SHA256 = '88ed045a0589d130a2622cba3b4ace4a139b6513ebca2616a1bae67bdda0e4b6'
COLLAPSED_RING = [[0.0, 0.0], [1.0000000000003293, 0.1359761555989476], [1.876967859454453, 0.25522287371131824]]
POSITIVE_SLIVER = [[1.876967859454453, 0.25522287371131824], [2.6482670089858793, 0.7457507416435617], [2.6494438944122187, 0.7464992127125799]]

def exact_binary64_area(ring):
    values = [(_i1_Fraction(float(x)), _i1_Fraction(float(y))) for x, y in ring]
    return sum((start[0] * end[1] - end[0] * start[1] for start, end in zip(values, values[1:] + values[:1])), _i1_Fraction(0)) / 2

def read_pinned(path, expected):
    raw = path.read_bytes()
    if _i1_hashlib.sha256(raw).hexdigest() != expected:
        raise AssertionError('recovery evidence SHA256 changed: ' + str(path))
    return _i1_json.loads(raw)

class HybridGeometryPrecisionBlockerTests(_i1_unittest.TestCase):

    def test_exact_nonzero_triangle_with_zero_display_area_stays_rejected(self):
        self.assertEqual(exact_binary64_area(COLLAPSED_RING), _i1_Fraction(-16176346637, 1237940039285380274899124224))
        polygon = _i1_Polygon(COLLAPSED_RING)
        self.assertTrue(polygon.is_valid)
        self.assertEqual(polygon.area, 0.0)
        record = {'polygons_uv_m': [COLLAPSED_RING], 'holes_uv_m': [[]], 'area_m2': 0.0}
        with self.assertRaisesRegex(ValueError, 'invalid saved slice with holes'):
            _i1_saved_slice_geometry(record)
        with self.assertRaisesRegex(ValueError, 'exact nonzero exterior has zero display area'):
            _i1_consume_saved_slice(record)

    def test_positive_display_sliver_is_preserved_without_area_threshold(self):
        expected = _i1_Polygon(POSITIVE_SLIVER)
        self.assertGreater(expected.area, 0.0)
        self.assertLess(expected.area, 1e-08)
        record = {'polygons_uv_m': [POSITIVE_SLIVER], 'holes_uv_m': [[]], 'area_m2': expected.area}
        for reader in (_i1_saved_slice_geometry, _i1_consume_saved_slice):
            with self.subTest(reader=reader.__name__):
                actual = reader(record)
                self.assertTrue(actual.equals(expected))
                self.assertEqual(set(actual.exterior.coords), set(expected.exterior.coords))
                self.assertEqual(abs(exact_binary64_area(list(actual.exterior.coords)[:-1])), abs(exact_binary64_area(POSITIVE_SLIVER)))
                self.assertGreater(actual.area, 0.0)
                self.assertLess(actual.area, 1e-08)

    def test_mixed_domain_is_not_repaired_by_dropping_collapsed_component(self):
        record = {'polygons_uv_m': [POSITIVE_SLIVER, COLLAPSED_RING], 'holes_uv_m': [[], []], 'area_m2': _i1_Polygon(POSITIVE_SLIVER).area}
        for reader in (_i1_saved_slice_geometry, _i1_consume_saved_slice):
            with self.subTest(reader=reader.__name__), self.assertRaises(ValueError):
                reader(record)
        self.assertEqual(record['polygons_uv_m'], [POSITIVE_SLIVER, COLLAPSED_RING])

@_i1_unittest.skipUnless((CURRENT / 'composition.json').is_file() and ORIGINAL.is_file(), 'fixed VC-03 recovery artifacts are unavailable')
class HybridGeometrySavedRecoveryTests(_i1_unittest.TestCase):

    def test_fixed_saved_blocker_is_unchanged_from_original(self):
        current = read_pinned(CURRENT / 'composition.json', CURRENT_SHA256)
        original = read_pinned(ORIGINAL, ORIGINAL_SHA256)
        domain = current['portal_connections']['sink']['blocked_domain']
        self.assertEqual(domain, original['portal_connections']['sink']['blocked_domain'])
        self.assertEqual(domain['polygons_uv_m'], [POSITIVE_SLIVER, COLLAPSED_RING])
        with self.assertRaisesRegex(ValueError, 'invalid saved slice with holes'):
            _i1_saved_slice_geometry(domain)
        with self.assertRaisesRegex(ValueError, 'exact nonzero exterior has zero display area'):
            _i1_consume_saved_slice(domain)

    def test_failed_integration_is_refused_with_checkpoint_not_successful_faces(self):
        index = _i1_json.loads((CURRENT / 'index.json').read_bytes())
        from tools.td_shared_channel_fine_saved_audit import check_identity
        check_identity(index)
        self.assertEqual(index['status'], 'refused')
        self.assertEqual(index['errors'], ['ValueError: invalid saved slice with holes'])
        self.assertEqual(index['stages_completed'], ['fresh-main-Boolean-saved', 'rational-port-stage-saved'])
        self.assertFalse(index['hydraulic_ready'])
        self.assertFalse(index['publishable'])
        for name in ('boolean_checkpoint', 'boolean_index', 'composition'):
            path = _i1_Path(index[name]['path'])
            self.assertTrue(path.is_file())
            self.assertEqual(_i1_hashlib.sha256(path.read_bytes()).hexdigest(), index[name]['sha256'])
        for name in ('composition_audit', 'faces', 'faces_audit'):
            self.assertNotIn(name, index)
        for name in ('composition-audit.json', 'faces.json', 'faces-audit.json'):
            self.assertFalse((CURRENT / name).exists())

class RiverFaceTests(_i2_unittest.TestCase):

    def test_library_oblique_plane_common_vertical_frame_and_actual_closed_void(self):
        import manifold3d as manifold
        normal = _i2_np.array([0.6, 0.0, 0.8])
        frame = _i2_plane_frame([-178440.0, 1366.0, 68355.0], normal[[0, 2]], [-178443.0, 1360.0, 68350.0])
        basis = _i2_np.array([frame['transverse_unit_xyz'], frame['vertical_unit_xyz'], frame['normal_local_xyz']])
        self.assertAlmostEqual(float(_i2_np.linalg.det(basis)), 1.0)
        origin = _i2_np.array(frame['origin_local_xyz_m'])
        before = manifold.Manifold.cube([12.0, 12.0, 12.0], center=True).translate(origin.tolist())
        cutter = manifold.Manifold.cube([2.0, 4.0, 16.0], center=True)
        rotation = _i2_np.column_stack((basis.T, origin))
        cutter = cutter.transform(rotation.tolist())
        after, removed = (before - cutter, before ^ cutter)
        records, shapes = ({}, {})
        for name, solid in {'cutter': cutter, 'removed': removed, 'rock_before': before, 'rock_after': after}.items():
            mesh = solid.to_mesh64()
            data = (solid, _i2_np.array(mesh.vert_properties[:, :3], copy=True), _i2_np.array(mesh.tri_verts, dtype=int, copy=True))
            records[name], shapes[name] = _i2_slice_solid(data, frame, {'path': name, 'sha256': '0' * 64})
            self.assertTrue(records[name]['triangle_segments'])
        result = _i2_classify_aperture(records, shapes, frame)
        self.assertEqual(result['kind'], 'closed_polygon')
        self.assertAlmostEqual(result['bounded_display_aperture_area_m2'], 8.0, places=7)
        self.assertFalse(result['pressure_slot_enlarges_face'])
        self.assertTrue(all((piece['category'] == 'actual_rock_wet_wall' for piece in result['boundary_pieces'])))
        uv = [[-1.0, 3.0], [1.0, 7.0]]
        local = _i2_unproject(uv, frame)
        _i2_np.testing.assert_allclose(_i2_project(local, frame), uv, atol=1e-12)
        _i2_np.testing.assert_array_equal(local[:, 1], [3.0, 7.0])
        self.assertTrue(all((piece['source_triangle_indices']['rock_after'] for piece in result['boundary_pieces'])))
        open_frame = _i2_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0])
        before = manifold.Manifold.cube([8.0, 8.0, 12.0], center=True).translate([0.0, -4.0, 0.0])
        cutter = manifold.Manifold.cube([2.0, 3.0, 16.0], center=True).translate([0.0, 0.5, 0.0])
        records, shapes = ({}, {})
        for name, solid in {'cutter': cutter, 'removed': before ^ cutter, 'rock_before': before, 'rock_after': before - cutter}.items():
            mesh = solid.to_mesh64()
            records[name], shapes[name] = _i2_slice_solid((solid, _i2_np.array(mesh.vert_properties[:, :3], copy=True), _i2_np.array(mesh.tri_verts, dtype=int, copy=True)), open_frame, {'path': name, 'sha256': '0' * 64})
        open_result = _i2_classify_aperture(records, shapes, open_frame)
        self.assertEqual(open_result['kind'], 'open_cut_floor')
        self.assertFalse(open_result['open_extension']['unbounded_above_cut_floor'])
        self.assertTrue(open_result['terrain_opening_free_edges'])
        self.assertTrue(open_result['open_extension']['unbounded_only_over_supported_free_top_intervals'])
        self.assertTrue(any((piece['category'] == 'artificial_cutter_top_cap_not_wetted_wall' for piece in open_result['boundary_pieces'])))
        self.assertEqual(_i2_json.loads(_i2_json.dumps(open_result, allow_nan=False)), open_result)

    def test_unknown_aperture_multiple_components_and_missing_support_refused(self):
        frame = _i2_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0])
        square = _i2_Polygon([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])
        records = {name: {'triangle_segments': [], 'coplanar_triangle_supports': []} for name in ('cutter', 'removed', 'rock_before', 'rock_after')}
        shapes = {'cutter': _i2_Polygon(), 'removed': square, 'rock_before': square, 'rock_after': _i2_Polygon()}
        with self.assertRaisesRegex(ValueError, 'unknown'):
            _i2_classify_aperture(records, shapes, frame)
        shapes['cutter'] = square.union(_i2_Polygon([[3.0, -1.0], [5.0, -1.0], [5.0, 1.0], [3.0, 1.0]]))
        with self.assertRaisesRegex(ValueError, 'multiple'):
            _i2_classify_aperture(records, shapes, frame)
        shapes['cutter'] = square
        with self.assertRaisesRegex(ValueError, 'support'):
            _i2_classify_aperture(records, shapes, frame)
        with self.assertRaisesRegex(ValueError, 'plane'):
            _i2_plane_frame([0.0, 0.0, 0.0], [0.0, 0.0], [0.0, 0.0, 0.0])

def fixture():
    import manifold3d as manifold
    ring = [[1.0, 0.0], [0.0, -0.2], [-1.0, 0.0], [-1.0, 0.0023], [-1.0023, 0.0023], [-1.0023, 2.0], [1.0, 2.0]]
    stations = [{'station_id': 'station:' + str(ordinal), 'floor_vertex_count': 5, 'origin_xyz_m': [0.0, 0.0, depth], 'transverse_unit_xz': [1.0, 0.0], 'derived_ring_xyz_m': [[point[0], point[1], depth] for point in ring]} for ordinal, depth in enumerate((-2.0, 2.0))]
    vdm = {'stations': stations, 'triangles': _i3_sweep_triangles(stations)}
    points = _i3_np.array([station['derived_ring_xyz_m'] for station in stations]).reshape(-1, 3)
    triangles = _i3_np.array(vdm['triangles'], dtype=_i3_np.uint64)
    solid = manifold.Manifold(manifold.Mesh64(_i3_np.array(points, order='C'), _i3_np.array(triangles, order='C')))
    if solid.volume() < 0:
        triangles = triangles[:, ::-1].copy()
        vdm['triangles'] = triangles.tolist()
        solid = manifold.Manifold(manifold.Mesh64(_i3_np.array(points, order='C'), _i3_np.array(triangles, order='C')))
    if solid.is_empty() or solid.volume() <= 0:
        raise ValueError('invalid self-contained swept fixture')
    mesh = _i3_seal({'vertices_local_xyz_m': points.tolist(), 'triangles': triangles.tolist(), 'local_origin_xyz_m': [0.0, 0.0, 0.0]})
    frame = _i3_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0])
    source = _i3_vdm_role_source(vdm, mesh, [0.0, 0.0, 0.0], {'path': 'source-fixture', 'sha256': '0' * 64})
    return (solid, frame, _i3_role_slice(source, frame), mesh, vdm)

def slices_for(cutter, before, frame):
    records, shapes = ({}, {})
    for name, solid in {'cutter': cutter, 'rock_before': before, 'rock_after': before - cutter, 'removed': before ^ cutter}.items():
        mesh = solid.to_mesh64()
        records[name], shapes[name] = _i3_slice_solid((solid, _i3_np.array(mesh.vert_properties[:, :3], copy=True), _i3_np.array(mesh.tri_verts, copy=True)), frame, {'path': name + '-fixture', 'sha256': '0' * 64})
    return (records, shapes)

class ActualPolygonFaceTests(_i3_unittest.TestCase):

    def test_exact_mesh64_top_precision_cached_roles_and_actual_polygon(self):
        import manifold3d as manifold
        top = 3.0432591911956024
        initial = manifold.Manifold.cube([6.23213, 4.0, 2.0], center=True).to_mesh64()
        points = _i3_np.array(initial.vert_properties[:, :3], copy=True)
        points[:, 1] = _i3_np.where(points[:, 1] > 0, top, -1.0)
        triangles = _i3_np.array(initial.tri_verts, dtype=_i3_np.uint64, copy=True)
        solid = manifold.Manifold(manifold.Mesh64(_i3_np.array(points, order='C'), _i3_np.array(triangles, order='C')))
        frame = _i3_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0])
        data = (solid, points, triangles)
        pin = {'path': 'precision-fixture', 'sha256': '0' * 64}
        record, actual = _i3_slice_solid(data, frame, pin)
        legacy, quantized = _i3_legacy_slice_solid(data, frame, pin)
        self.assertEqual(actual.bounds[3], top)
        self.assertGreater(actual.difference(quantized).area, 1e-08)
        self.assertEqual(record['schema'], 'td-hybrid-exact-mesh-plane-slice-v2')
        self.assertTrue(record['display_projection_certified'])
        self.assertLessEqual(record['projection_area_error_bound_m2'], 1e-08)
        self.assertTrue(all(('rational_xyz_m' in node and 'rational_uv_m' in node for node in record['intersection_nodes'])))
        role_source = {'mesh_pin': pin, 'points_local_xyz_m': points, 'triangles': triangles, 'role_rule': 'precision_fixture', 'triangle_roles': [{'triangle_index': ordinal, 'source_role': 'lateral'} for ordinal in range(len(triangles))]}
        roles = _i3_role_slice(role_source, frame)
        for saved, role in zip(record['triangle_segments'], roles['triangle_segments']):
            self.assertEqual(saved['intersection_node_ids'], role['intersection_node_ids'])
            self.assertEqual(saved['points_uv_m'], role['points_uv_m'])
        self.assertEqual(roles['numerical_policy_identity_sha256'], record['numerical_policy_identity_sha256'])
        next_coordinate = _i3_np.nextafter(1.0, _i3_np.inf)
        collapsed_source = {'mesh_pin': pin, 'role_rule': 'synthetic_distinct_rational_same_display', 'points_local_xyz_m': _i3_np.array([[1.0, 1.0, 1.0], [next_coordinate, 1.0, -1.0], [1.0, next_coordinate, -1.0]]), 'triangles': _i3_np.array([[0, 1, 2]]), 'triangle_roles': [{'triangle_index': 0, 'source_role': 'lateral'}]}
        collapsed = _i3_role_slice(collapsed_source, frame)['triangle_segments'][0]
        self.assertNotEqual(*collapsed['intersection_node_ids'])
        self.assertEqual(*collapsed['points_uv_m'])
        self.assertNotEqual(*collapsed['rational_points_uv_m'])
        self.assertNotEqual(collapsed['orientation_rational'], '0')
        self.assertIn(collapsed['exact_orientation_sign'], (-1, 1))
        local_origin = [-179000.0, 1350.0, 68000.0]
        local_points = [[0.25, 0.0, 0.0], [1.0, 0.0, 0.0], [0.25, 0.0, 1.0], [0.25, 2.0, 0.0], [1.0, 2.0, 0.0], [0.25, 2.0, 1.0]]
        prism = _i3_seal({'vertices_local_xyz_m': local_points, 'triangles': [[0, 1, 2]] * 8, 'local_origin_xyz_m': local_origin})
        bottom = {'prism': prism, 'prism_triangle_roles': ['floor', 'artificial_top_cap'] + ['lateral'] * 6, 'bottom_vertices_xyz_m': (_i3_np.asarray(local_points[:3]) + local_origin).tolist(), 'bottom_triangle_id': 'fixture:0', 'fan_key': 'fixture', 'source_function_identity_sha256': '0' * 64}
        prisms = {'half_arms': {kind: {'bottom_triangles': [bottom]} for kind in ('sink', 'spring')}}
        for saved_source in _i3_surface_role_sources(prisms, local_origin, pin):
            self.assertTrue(_i3_np.array_equal(saved_source['points_local_xyz_m'], _i3_np.asarray(local_points)))
        cutter, frame, source, mesh, vdm = fixture()
        before = manifold.Manifold.cube([6.0, 5.0, 6.0], center=True).translate([0.0, -2.0, 0.0])
        records, shapes = slices_for(cutter, before, frame)
        with self.assertRaisesRegex(ValueError, 'cut_floor_not_actual'):
            _i3_lower_floor(shapes['cutter'])
        result = _i3_classify_aperture(records, shapes, [source], frame)
        self.assertEqual(result['kind'], 'open_actual_polygon')
        self.assertTrue(result['polygon_authoritative'])
        self.assertFalse(result['floor_height_function_required'])
        floor = [piece for piece in result['boundary_pieces'] if piece['source_role'] == 'floor']
        vertical_length = sum((_i3_LineString(piece['points_uv_m']).length for piece in floor if abs(piece['points_uv_m'][0][0] - piece['points_uv_m'][-1][0]) < 1e-12))
        self.assertAlmostEqual(vertical_length, 0.0023, delta=1e-08)
        roof = [piece for piece in result['boundary_pieces'] if piece['source_role'] == 'roof']
        self.assertTrue(all((piece['category'] == 'artificial_cutter_top_cap_not_wetted_wall' for piece in roof)))
        self.assertFalse(result['pressure_slot_enlarges_face'])
        first = manifold.Manifold.cube([0.5, 5.0, 6.0], center=True).translate([-0.65, -2.0, 0.0])
        second = manifold.Manifold.cube([0.5, 5.0, 6.0], center=True).translate([0.65, -2.0, 0.0])
        records, shapes = slices_for(cutter, first + second, frame)
        self.assertEqual(shapes['removed'].geom_type, 'MultiPolygon')
        result = _i3_classify_aperture(records, shapes, [source], frame)
        self.assertEqual(result['material_component_count'], 2)
        self.assertTrue(result['material_components_do_not_certify_fluid_connectivity'])
        self.assertEqual(_i3_Polygon(result['polygon_uv_m']).geom_type, 'Polygon')

    def test_blocking_cap_missing_two_sided_role_support_and_multiple_fluid_refused(self):
        import manifold3d as manifold
        cutter, frame, source, mesh, vdm = fixture()
        before = manifold.Manifold.cube([6.0, 5.0, 6.0], center=True).translate([0.0, -2.0, 0.0])
        records, shapes = slices_for(cutter, before, frame)
        profile = [point['points_uv_m'] for point in source['triangle_segments'] if point['source_role'] == 'floor'][0]
        with self.assertRaisesRegex(ValueError, 'two_sided'):
            _i3_classify_aperture(records, shapes, [source], frame, profile, {'two_sided_complete_port_verified': False})
        blocked = dict(shapes)
        blocked['rock_after'] = shapes['rock_after'].union(shapes['cutter'])
        with self.assertRaisesRegex(ValueError, 'no_cap_deletion'):
            _i3_classify_aperture(records, blocked, [source], frame, profile, {'two_sided_complete_port_verified': True})
        uncertain = {name: {**record, 'projection_area_error_bound_m2': 0.0} for name, record in records.items()}
        uncertain['cutter']['projection_area_error_bound_m2'] = 6e-09
        uncertain['rock_after']['projection_area_error_bound_m2'] = 6e-09
        with self.assertRaisesRegex(ValueError, 'no_cap_deletion'):
            _i3_classify_aperture(uncertain, shapes, [source], frame)
        with self.assertRaisesRegex(ValueError, 'source_role'):
            _i3_classify_aperture(records, shapes, [], frame)
        multiple = dict(shapes)
        multiple['cutter'] = shapes['cutter'].union(_i3_Polygon([[3.0, 0.0], [4.0, 0.0], [4.0, 1.0], [3.0, 1.0]]))
        with self.assertRaisesRegex(ValueError, 'multiple'):
            _i3_classify_aperture(records, multiple, [source], frame)
        changed = {**mesh, 'vertices_local_xyz_m': [[point[0] + 0.01, point[1], point[2]] for point in mesh['vertices_local_xyz_m']]}
        with self.assertRaisesRegex(ValueError, 'immutable_station'):
            _i3_vdm_role_source(vdm, changed, [0.0, 0.0, 0.0], {})

def port(key, nodes, x):
    pieces = []
    for ordinal in range(3):
        pieces.append({'native_pieces': [{'interval_t01': [0, 1], 'start_xz_m': [x, ordinal], 'end_xz_m': [x, ordinal + 1], 'source': {'source_coefficients_m_t012': [10, 0, 0.4 if ordinal == 1 else 0]}, 'depth_coefficients_m_t01': [0.2, 0]}]})
    return {'arc_id': key, 'identity_sha256': key, 'midpoint_xz_m': [x, 1.5], 'node_ids': nodes, 'profile': {'profile_segments': pieces}, 'upstream_parent_section': {'anchor': False}, 'rejection_reasons': []}

class HybridGraphTests(_i4_unittest.TestCase):

    def fixtures(self):
        nodes = [{'node_id': str(ordinal), 'xyz_m': [ordinal, 10, 0], 'source_note': 'unchanged'} for ordinal in range(4)]
        arcs = [{'arc_id': str(ordinal), 'node_ids': [str(ordinal), str(ordinal + 1)], 'q_prior_not_new_supply': 0.1} for ordinal in range(3)]
        graph = {'nodes': nodes, 'arcs': arcs}
        manifest = {'selected_node_ids': [node['node_id'] for node in nodes]}
        topology = {'joined_arc_ids': [arc['arc_id'] for arc in arcs]}
        ports = {arc['arc_id']: port(arc['arc_id'], arc['node_ids'], int(arc['arc_id'])) for arc in arcs}
        audit = {'status': 'passed', 'complete_actual_reverse_midpoint_functions_verified': True, 'selected_node_ids': manifest['selected_node_ids'], 'ports': {key: {'identity_sha256': key} for key in ports}, 'nodes': {node['node_id']: {'identity_sha256': 'node:' + node['node_id']} for node in nodes}}
        saved_nodes = {}
        for node in nodes:
            key = node['node_id']
            incident = [arc for arc in arcs if key in arc['node_ids']]
            saved_nodes[key] = {'identity_sha256': 'node:' + key, 'status': 'candidate', 'source_xyz_m': node['xyz_m'], 'center_depth_m': 0.2, 'arms': [{'arc_id': arc['arc_id'], 'midpoint_port_identity_sha256': arc['arc_id']} for arc in incident], 'port_proofs': [{'arc_id': arc['arc_id'], 'midpoint_port_identity_sha256': arc['arc_id'], 'segments': [{'profile_segment_index': ordinal, 'pieces': [{'side': {'triangle_index': index}}]} for ordinal in range(3)]} for index, arc in enumerate(incident)], 'geometry': {'triangle_roles': [{'region': 'half_arm', 'arc_id': arc['arc_id']} for arc in incident] + [{'region': 'node_ring'}]}}
        self.saved_nodes = saved_nodes
        return (graph, manifest, topology, audit, ports)

    def test_preserves_surface_and_immutable_native_midpoint(self):
        arguments = self.fixtures()
        graph = _i4_build_graph(*arguments, {}, '0', '2', self.saved_nodes)
        record = graph.to_record()
        self.assertEqual(record, _i4_load_graph(record).to_record())
        self.assertEqual(graph.bypass_arc_ids, ('0', '1', '2'))
        self.assertEqual([_i4_json.loads(node.source_record_json) for node in graph.nodes if node.kind == 'surface'], arguments[0]['nodes'])
        self.assertTrue(all((arc.hydraulic_role == 'context_only' for arc in graph.arcs if arc.kind == 'surface')))
        active = {arc.node_ids[0]: arc.node_ids[1] for arc in graph.arcs if arc.hydraulic_role == 'sample_route'}
        self.assertEqual(active[active[active['0']]], '3')
        self.assertEqual(graph.nodes[0].source_xyz_m[1], 10)
        self.assertEqual(graph.nodes[0].bed_xyz_m[1], 9.8)
        with self.assertRaises(_i4_FrozenInstanceError):
            graph.nodes[0].kind = 'spring'
        self.assertAlmostEqual(_i4_port_floor_xyz(arguments[4]['0'])[1], 9.9)
        self.assertEqual(_i4_native_bed_pieces(arguments[4]['0'])[1]['bed_coefficients_m_t012'], [9.8, 0, 0.4])

    def test_rejects_fake_attachment_anchor_reverse_and_tampering(self):
        arguments = self.fixtures()
        with self.assertRaises(ValueError):
            _i4_build_graph(*arguments, {}, '2', '0', self.saved_nodes)
        arguments[4]['0']['upstream_parent_section']['anchor'] = True
        with self.assertRaises(ValueError):
            _i4_build_graph(*arguments, {}, '0', '2', self.saved_nodes)
        arguments = self.fixtures()
        arguments[2]['joined_arc_ids'].remove('0')
        with self.assertRaises(ValueError):
            _i4_build_graph(*arguments, {}, '0', '2', self.saved_nodes)
        arguments = self.fixtures()
        record = _i4_build_graph(*arguments, {}, '0', '2', self.saved_nodes).to_record()
        record['nodes'][0]['xyz_m'][1] = -1
        with self.assertRaises(ValueError):
            _i4_load_graph(record)
ORIGIN = _i5_np.array([4.0, -3.0, 7.0])

def square_ring(half_x, half_z, centre=(0.0, 0.0)):
    return _i5_np.array([[centre[0] - half_x, centre[1] - half_z], [centre[0] + half_x, centre[1] - half_z], [centre[0] + half_x, centre[1] + half_z], [centre[0] - half_x, centre[1] + half_z]], float)

class RockBooleanTests(_i5_unittest.TestCase):

    def test_prism_volume_and_closed_record_reproducible(self):
        first = _i5_polygon_prism_record(square_ring(10.0, 10.0), -5.0, 5.0, ORIGIN, 'rock')
        second = _i5_polygon_prism_record(square_ring(10.0, 10.0), -5.0, 5.0, ORIGIN, 'rock')
        self.assertEqual(first['schema'], 'td-hybrid-local-solid-mesh-v1')
        self.assertEqual(first['role'], 'rock')
        self.assertTrue(first['sampled_not_native_exact'])
        self.assertEqual(first, second)
        self.assertAlmostEqual(first['signed_volume_m3'], 4000.0, places=6)
        self.assertEqual(_i5_census(_i5_solid_from_record(first, 'rock')), 1)

    def test_frustum_and_sphere_records_are_closed_positive_solids(self):
        frustum = _i5_frustum_record([0.0, 0.0], [0.0, 0.0], 0.0, 10.0, 6.0, 2.0, ORIGIN, 'cutter', segments=32)
        self.assertGreater(frustum['signed_volume_m3'], 0.0)
        expected = _i5_math.pi * 10.0 * (6.0 ** 2 + 6.0 * 2.0 + 2.0 ** 2) / 3.0
        self.assertLess(abs(frustum['signed_volume_m3'] - expected) / expected, 0.02)
        ball = _i5_sphere_record([1.0, 2.0, 3.0], 2.5, ORIGIN, 'egg', circular_segments=64)
        ideal_ball = 4.0 / 3.0 * _i5_math.pi * 2.5 ** 3
        self.assertLess(abs(ball['signed_volume_m3'] - ideal_ball) / ideal_ball, 0.01)
        with self.assertRaises(ValueError):
            _i5_polygon_prism_record(square_ring(1.0, 1.0), 5.0, 5.0, ORIGIN, 'rock')
        with self.assertRaises(ValueError):
            _i5_polygon_prism_record([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]], 0.0, 1.0, ORIGIN, 'rock')
        with self.assertRaises(ValueError):
            _i5_octagon_ring([0.0, 0.0], 1.0, 1.0, 2)
        with self.assertRaises(ValueError):
            _i5_frustum_record([0.0, 0.0], [0.0, 0.0], 0.0, 10.0, 6.0, float('nan'), ORIGIN, 'cutter')

    def test_excavation_matches_actual_volume_and_refuses_shortfalls(self):
        parameters = _i5_BooleanParameters(solids_spacing_m=1.0, component_limit=8)
        rock = _i5_polygon_prism_record(square_ring(10.0, 10.0), -5.0, 5.0, ORIGIN, 'rock')
        tunnel = _i5_polygon_prism_record(square_ring(5.0, 5.0), -20.0, 20.0, ORIGIN, 'cutter')
        result, meshes = _i5_excavate(rock, [tunnel], parameters, ORIGIN)
        self.assertEqual(result['schema'], _i5_RESULT_SCHEMA)
        self.assertEqual(result['algorithm'], _i5_ALGORITHM)
        self.assertEqual(result['status'], 'candidate')
        self.assertEqual(result['rejection_reasons'], [])
        material = result['material']
        self.assertAlmostEqual(material['rock_before_m3'], 4000.0, places=6)
        self.assertAlmostEqual(material['excavated_rock_m3'], 1000.0, places=6)
        self.assertAlmostEqual(material['rock_after_m3'], 3000.0, places=6)
        self.assertAlmostEqual(material['fill_rock_m3'], 0.0)
        self.assertLess(abs(material['signed_residual_m3']), material['balance_budget_m3'])
        self.assertEqual(set(meshes), {'rock_after', 'removed', 'cutter_union'})
        self.assertAlmostEqual(meshes['removed']['signed_volume_m3'], 1000.0, places=6)
        self.assertEqual(_i5_census(_i5_solid_from_record(meshes['removed'], 'removed')), 1)
        self.assertEqual(result['census']['removed_components'], 1)
        self.assertEqual(result['census']['rock_after_components'], 1)
        for flag in _i5_FLAGS:
            self.assertIs(result[flag], False)
        self.assertEqual(result['identity_sha256'], _i5_identity({key: value for key, value in result.items() if key != 'identity_sha256'}))
        repeat, _ = _i5_excavate(rock, [tunnel], parameters, ORIGIN)
        self.assertEqual(repeat['identity_sha256'], result['identity_sha256'])

    def test_two_disjoint_cutters_are_one_union_and_two_cavities(self):
        parameters = _i5_BooleanParameters(solids_spacing_m=1.0, component_limit=8)
        rock = _i5_polygon_prism_record(square_ring(20.0, 10.0), -10.0, 10.0, ORIGIN, 'rock')
        first = _i5_polygon_prism_record(square_ring(2.0, 2.0, (-12.0, 0.0)), -30.0, 30.0, ORIGIN, 'cutter')
        second = _i5_polygon_prism_record(square_ring(2.0, 2.0, (12.0, 0.0)), -30.0, 30.0, ORIGIN, 'cutter')
        self.assertEqual(_i5_census(_i5_solid_from_record(first, 'cutter')), 1)
        result, meshes = _i5_excavate(rock, [first, second], parameters, ORIGIN, minimum_removed_components=2)
        self.assertEqual(result['census']['cutter_union_components'], 2)
        self.assertEqual(result['census']['removed_components'], 2)
        self.assertAlmostEqual(meshes['cutter_union']['signed_volume_m3'], 2 * 960.0, places=6)
        self.assertAlmostEqual(meshes['removed']['signed_volume_m3'], 2 * 320.0, places=6)
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [first, second], parameters, ORIGIN, minimum_removed_components=3)

    def test_cutter_union_merges_into_one_cavity_when_overlapping(self):
        parameters = _i5_BooleanParameters(solids_spacing_m=1.0, component_limit=8)
        rock = _i5_polygon_prism_record(square_ring(20.0, 10.0), -10.0, 10.0, ORIGIN, 'rock')
        first = _i5_polygon_prism_record(square_ring(3.0, 2.0, (-2.0, 0.0)), -30.0, 30.0, ORIGIN, 'cutter')
        second = _i5_polygon_prism_record(square_ring(3.0, 2.0, (2.0, 0.0)), -30.0, 30.0, ORIGIN, 'cutter')
        result, meshes = _i5_excavate(rock, [first, second], parameters, ORIGIN)
        self.assertEqual(result['census']['cutter_union_components'], 1)
        self.assertEqual(result['census']['removed_components'], 1)
        self.assertAlmostEqual(meshes['cutter_union']['signed_volume_m3'], 2400.0, places=6)
        self.assertAlmostEqual(meshes['removed']['signed_volume_m3'], 800.0, places=6)
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [first, second], parameters, ORIGIN, minimum_removed_components=2)

    def test_combine_union_preserves_gaps_and_refuses_claimed_components(self):
        parameters = _i5_BooleanParameters(solids_spacing_m=1.0, component_limit=8)
        eggs = [_i5_sphere_record([0.0, 0.0, 0.0], 1.5, ORIGIN, 'egg', circular_segments=32), _i5_sphere_record([0.0, 5.0, 0.0], 1.5, ORIGIN, 'egg', circular_segments=32), _i5_sphere_record([0.0, 10.0, 0.0], 1.5, ORIGIN, 'egg', circular_segments=32)]
        result, meshes = _i5_combine(eggs, ORIGIN, 'egg_pile', parameters, minimum_components=3)
        self.assertEqual(result['operation'], 'closed_solid_union_no_cutter')
        self.assertEqual(result['census']['assembled_components'], 3)
        self.assertEqual(result['material']['excavated_rock_m3'], 0.0)
        self.assertEqual(result['material']['signed_residual_m3'], 0.0)
        self.assertEqual(set(meshes), {'egg_pile'})
        self.assertAlmostEqual(meshes['egg_pile']['signed_volume_m3'], sum((egg['signed_volume_m3'] for egg in eggs)), places=6)
        for flag in _i5_FLAGS:
            self.assertIs(result[flag], False)
        with self.assertRaises(ValueError):
            _i5_combine(eggs, ORIGIN, 'egg_pile', parameters, minimum_components=4)
        with self.assertRaises(ValueError):
            _i5_combine([eggs[0], _i5_sphere_record([0.0, 0.5, 0.0], 1.5, ORIGIN, 'egg', circular_segments=32)], ORIGIN, 'egg_pile', parameters, minimum_components=2)
        with self.assertRaises(ValueError):
            _i5_combine([], ORIGIN, 'egg_pile', parameters)

    def test_open_or_mismatched_records_and_parameters_are_refused(self):
        parameters = _i5_BooleanParameters(solids_spacing_m=1.0, component_limit=8)
        rock = _i5_polygon_prism_record(square_ring(10.0, 10.0), -5.0, 5.0, ORIGIN, 'rock')
        tunnel = _i5_polygon_prism_record(square_ring(5.0, 5.0), -20.0, 20.0, ORIGIN, 'cutter')
        broken = {'schema': 'td-hybrid-local-solid-mesh-v1', 'role': 'cutter', 'local_origin_xyz_m': ORIGIN.tolist(), 'sampled_not_native_exact': True, 'vertices_local_xyz_m': [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], 'triangles': [[0, 1, 2]], 'signed_volume_m3': 1.0}
        with self.assertRaises(ValueError):
            _i5_excavate(broken, [tunnel], parameters, ORIGIN)
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [broken], parameters, ORIGIN)
        wrong_schema = dict(tunnel, schema='td-hybrid-multichart-vdm-v1')
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [wrong_schema], parameters, ORIGIN)
        tampered = dict(tunnel, signed_volume_m3=tunnel['signed_volume_m3'] + 1.0)
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [tampered], parameters, ORIGIN)
        missing_volume = {key: value for key, value in tunnel.items() if key != 'signed_volume_m3'}
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [missing_volume], parameters, ORIGIN)
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [], parameters, ORIGIN)
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [tunnel], parameters, [1.0, 2.0])
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [tunnel], dict(solids_spacing_m=1.0), ORIGIN)
        with self.assertRaises(ValueError):
            _i5_BooleanParameters(solids_spacing_m=1)
        with self.assertRaises(ValueError):
            _i5_BooleanParameters(solids_spacing_m=0.01)
        with self.assertRaises(ValueError):
            _i5_BooleanParameters(component_limit=0)
        with self.assertRaises(ValueError):
            _i5_BooleanParameters(component_limit=True)
        with self.assertRaises(ValueError):
            _i5_BooleanParameters(balance_relative_tolerance=0.001)
        unused = _i5_polygon_prism_record(square_ring(0.5, 0.5, (100.0, 100.0)), -30.0, 30.0, ORIGIN, 'cutter')
        with self.assertRaises(ValueError):
            _i5_excavate(rock, [unused], parameters, ORIGIN)

    def test_module_identity_is_independent_of_the_pinned_conduit_identity(self):
        self.assertEqual(_i5_SCHEMA, 'td-hybrid-rock-boolean-v1')
        self.assertNotEqual(_i5_POLICY_SHA256, _i5_CONDUIT_POLICY_SHA256)
        self.assertEqual(_i5_conduit.POLICY_SHA256, _i5_CONDUIT_POLICY_SHA256)
        self.assertEqual(_i5_conduit.POLICY['version'], 'local-rock-boolean-multichart-v1')
        self.assertNotEqual(_i5_POLICY, _i5_conduit.POLICY)

class SurfaceCompositionTests(_i6_unittest.TestCase):

    def test_saved_exact_edge_and_cut_only_boolean_material(self):
        import manifold3d as manifold
        fan = {'vertices_xz_m': [[-178439.37434404684, 68351.55803256418], [-178440.0, 68355.0], [-178441.87696785945, 68355.0]], 'depth_at_vertices_m': [0.619548634445664, 0.619548634445697, 0.619548634445697]}
        self.assertAlmostEqual(_i6_exact_depth(fan, [-178441.0, 68355.0]), 0.619548634445697)
        record = _i6_triangular_prism([[0.0, 1.0, 0.0], [2.0, 1.0, 0.0], [0.0, 1.0, 2.0]], 5.0, [0.0, 0.0, 0.0])
        self.assertEqual(_i6_json.loads(_i6_json.dumps(record, allow_nan=False)), record)
        surface = _i6_manifold_from_record(record)
        attachment = {'half_arm_triangle_indices': [0], 'actual_complete_port_proof': {'original_profile_xyz_m': [[0.0, 1.0, 0.0], [0.5, 1.0, 0.0], [1.5, 1.0, 0.0], [2.0, 1.0, 0.0]], 'segments': [{'pieces': [{'start_xz_m': [0.0, 0.0], 'end_xz_m': [2.0, 0.0], 'bed_coefficients_m_t012': [1.0, 0.0, 0.0]}]}]}}
        bottoms = [{'bottom_triangle_id': 0, 'fan_key': 'actual', 'bottom_vertices_xyz_m': [[0.0, 1.0, 0.0], [2.0, 1.0, 0.0], [0.0, 1.0, -2.0]]}]
        support = _i6_canonical_boundary_witness(attachment, bottoms, attachment['actual_complete_port_proof']['original_profile_xyz_m'], [0.0, 1.0], 'sink')
        self.assertEqual(support[0]['supports'][0]['interval_t01'], [0.0, 1.0])
        self.assertEqual(support[0]['supports'][0]['maximum_whole_linear_error_m'], 0.0)
        before = manifold.Manifold.cube([4.0, 4.0, 4.0])
        gallery = manifold.Manifold.cube([1.0, 2.0, 4.0]).translate([0.25, 0.5, 0.0])
        old_after, old_removed = (before - gallery, before ^ gallery)
        coupled = gallery + surface
        after, removed, extra = (before - coupled, before ^ coupled, old_after ^ surface)
        ledger = _i6_volume_ledger(before, old_after, old_removed, after, removed, extra)
        self.assertGreater(ledger['extra_removed_m3'], 0.0)
        self.assertEqual(ledger['fill_m3'], 0.0)
        self.assertAlmostEqual(ledger['total_removed_m3'], ledger['original_removed_m3'] + ledger['extra_removed_m3'])
        self.assertEqual((after - before).volume(), 0.0)

    def test_illegal_source_depth_missing_domain_and_cap_refused(self):
        fan = {'vertices_xz_m': [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], 'depth_at_vertices_m': [-1e-16, 0.5, 0.5]}
        with self.assertRaisesRegex(ValueError, 'strict'):
            _i6_exact_depth(fan, [0.0, 0.0])
        fan = {**fan, 'depth_at_vertices_m': [0.0, 0.5, 0.5]}
        with self.assertRaisesRegex(ValueError, 'outside'):
            _i6_exact_depth(fan, [1.0, 1.0])
        with self.assertRaisesRegex(ValueError, 'cap'):
            _i6_triangular_prism([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 1.0]], 1.0, [0.0, 0.0, 0.0])
        patch_fan = {**fan, 'depth_origin_xz_m': [0.0, 0.0], 'depth_coefficients_m_1xz': [-1e-16, 0.0, 0.0]}
        with self.assertRaisesRegex(ValueError, 'strict'):
            _i6_saved_patch_depth(patch_fan, [0.25, 0.25])

def box():
    left, right = (-3.1160651283571497, 3.1160651283571497)
    bottom, top = (-0.06256177661430229, 3.0432591911956024)
    vertices = [[left, bottom, -1.0], [right, bottom, -1.0], [right, top, -1.0], [left, top, -1.0], [left, bottom, 1.0], [right, bottom, 1.0], [right, top, 1.0], [left, top, 1.0]]
    triangles = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    record = _i7_mesh_record(vertices, triangles, [0.0, 0.0, 0.0], 'tiny_original_box')
    return (record, _i7_Polygon([[left, bottom], [right, bottom], [right, top], [left, top]]))

class SurfaceCompositionV2Tests(_i7_unittest.TestCase):

    def test_quantized_top_band_exact_shared_edges_and_holes(self):
        import manifold3d as manifold
        record, expected = box()
        solid = _i7_manifold_from_record(record)
        mesh = solid.to_mesh64()
        points, triangles = (_i7_np.asarray(mesh.vert_properties[:, :3]), _i7_np.asarray(mesh.tri_verts))
        frame = _i7_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0])
        result, shape = _i7_slice_solid((solid, points, triangles), frame, {'fixture': 'box'})
        self.assertEqual(shape.bounds, expected.bounds)
        self.assertEqual(expected.difference(shape).area, 0.0)
        old_shape = _i7_Polygon(solid.slice(0.0).to_polygons()[0])
        self.assertGreater(expected.difference(old_shape).area, 1e-08)
        self.assertEqual(_i7_json.loads(_i7_json.dumps(result, allow_nan=False)), result)
        self.assertEqual(len({node['node_id'] for node in result['intersection_nodes']}), len(result['intersection_nodes']))
        self.assertTrue(all((item['ray_parities'] == [1, 1] for item in result['occupancy_witnesses'])))
        hollow = manifold.Manifold.cube([4.0, 4.0, 4.0], center=True) - manifold.Manifold.cube([1.0, 1.0, 6.0], center=True)
        mesh = hollow.to_mesh64()
        saved, domain = _i7_slice_solid((hollow, _i7_np.asarray(mesh.vert_properties[:, :3]), _i7_np.asarray(mesh.tri_verts)), frame, {'fixture': 'hole'})
        self.assertAlmostEqual(domain.area, 15.0)
        self.assertEqual(len(domain.interiors), 1)
        self.assertEqual(len(saved['holes_uv_m'][0]), 1)
        self.assertTrue(any((item.get('ray_parities') == [0, 0] for item in saved['occupancy_witnesses'])))

    def test_coplanar_closed_and_one_sided_semantics_and_unknown_refusal(self):
        record, expected = box()
        solid = _i7_manifold_from_record(record)
        points, triangles = (_i7_np.asarray(record['vertices_local_xyz_m']), _i7_np.asarray(record['triangles']))
        frame = _i7_plane_frame([0.0, 0.0, 1.0], [0.0, 1.0], [0.0, 0.0, 0.0])
        result, shape = _i7_slice_solid((solid, points, triangles), frame, {'fixture': 'exact_cap'})
        self.assertAlmostEqual(shape.area, expected.area)
        self.assertEqual(result['one_sided_interior_traces']['positive']['area_m2'], 0.0)
        self.assertAlmostEqual(result['one_sided_interior_traces']['negative']['area_m2'], expected.area)
        self.assertTrue(all((item['occupied_incident_side'] == 'negative' for item in result['coplanar_triangle_supports'])))
        with self.assertRaisesRegex(ValueError, 'identity_graph'):
            _i7_slice_solid((solid, points, triangles[:-1]), _i7_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0]), {'fixture': 'open'})
        segments, caps = _i7_triangle_supports(points, triangles, frame)
        self.assertEqual(caps, result['coplanar_triangle_supports'])
        self.assertEqual(segments, result['triangle_segments'])
        line, point = (_i7_LineString([[0.0, 0.0], [1.0, 0.0]]), _i7_Point(2.0, 0.0))
        contact = _i7__domain(_i7_GeometryCollection([line, point]))
        self.assertEqual(contact['area_m2'], 0.0)
        self.assertEqual(contact['contact_lines_uv_m'], [[[0.0, 0.0], [1.0, 0.0]]])
        self.assertEqual(contact['contact_points_uv_m'], [[2.0, 0.0]])
        mixed = _i7__domain(_i7_GeometryCollection([expected, _i7_GeometryCollection([line, point])]))
        self.assertEqual(mixed['area_m2'], expected.area)
        self.assertEqual(len(mixed['polygons_uv_m']), 1)
        self.assertEqual(_i7_json.loads(_i7_json.dumps(mixed, allow_nan=False)), mixed)
        with _i7_tempfile.TemporaryDirectory() as directory:
            staging = _i7_Path(directory)
            stage = {'schema': 'td-hybrid-surface-composition-v2', 'status': 'boolean_stage_unverified', 'material': {'extra_removed_m3': 1.25}, 'original_source_sampling_cut_lookup_mismatches': [{'saved_cut_depth_m': 0.0}]}
            checkpoint = _i7_seal({'composition_stage': stage, 'material': stage['material']})
            _i7_save(staging / 'checkpoint_boolean.json', checkpoint, staging / 'published/checkpoint_boolean.json')
            refused = _i7_refused_from_stage(staging, staging / 'published', AttributeError('exterior'))
            self.assertEqual(refused['status'], 'refused')
            self.assertEqual(refused['material'], stage['material'])
            self.assertEqual(refused['original_source_sampling_cut_lookup_mismatches'], stage['original_source_sampling_cut_lookup_mismatches'])
            self.assertTrue(refused['boolean_stage_preserved'])
            self.assertTrue((staging / 'checkpoint_boolean.json').exists())
            self.assertFalse(refused['portal_connections']['sink']['two_sided_complete_port_verified'])
            self.assertEqual(_i7_json.loads(_i7_json.dumps(refused, allow_nan=False)), refused)

def loop_data(points):
    nodes = {'v:' + str(index): {'node_id': 'v:' + str(index), 'point_uv_m': list(map(float, point)), 'rational_uv_m': list(map(str, point))} for index, point in enumerate(points)}
    ids = list(nodes)
    segments = [{'triangle_index': ordinal, 'intersection_node_ids': [first, second], 'incident_halfspace': 'both'} for ordinal, (first, second) in enumerate(zip(ids, ids[1:] + ids[:1]))]
    return (nodes, segments)

class SurfaceCompositionV3Tests(_i8_unittest.TestCase):

    def test_exact_orientation_identity_collapse_and_certified_full_loop(self):
        frame = _i8_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0])
        adjacent = _i8_np.nextafter(1.0, _i8_np.inf)
        points = [[1.0, 1.0, 1.0], [adjacent, 1.0, -1.0], [1.0, adjacent, -1.0]]
        nodes, segments, _, _, collapses = _i8__trace(points, [[0, 1, 2]], frame)
        self.assertEqual(len(segments), 1)
        self.assertEqual(len(collapses), 1)
        self.assertGreater(_i8_Fraction(segments[0]['orientation_rational']), 0)
        first, second = [nodes[index] for index in segments[0]['intersection_node_ids']]
        self.assertNotEqual(first['rational_uv_m'], second['rational_uv_m'])
        self.assertEqual(first['point_uv_m'], second['point_uv_m'])
        half = _i8_Fraction(1, 2)
        ring = [[_i8_Fraction(0), _i8_Fraction(0)], [_i8_Fraction(1), _i8_Fraction(0)], [_i8_Fraction(1), half], [_i8_Fraction(1), half + _i8_Fraction(1, 10 ** 30)], [_i8_Fraction(1), _i8_Fraction(1)], [_i8_Fraction(0), _i8_Fraction(1)]]
        loop_nodes, loop_segments = loop_data(ring)
        shape, loops = _i8__side(loop_nodes, loop_segments, 'positive')
        self.assertEqual(shape.area, 1.0)
        self.assertEqual(len(loops[0]['node_ids']), 6)
        self.assertEqual(len(loops[0]['display_loop_node_ids']), 5)
        self.assertTrue(loops[0]['hierarchy_certified'])
        certificate = loops[0]
        error = _i8_Fraction(certificate['maximum_projection_distance_l1_rational'])
        perimeter = _i8_Fraction(certificate['display_perimeter_l1_rational'])
        bound = _i8_Fraction(certificate['projection_area_bound_rational'])
        self.assertGreaterEqual(bound, 2 * error * perimeter)
        self.assertGreaterEqual(_i8_Fraction(certificate['conservative_projection_area_bound_m2']), bound)
        self.assertGreaterEqual(_i8_Fraction(_i8_ceil_fraction(_i8_Fraction(1, 10))), _i8_Fraction(1, 10))
        self.assertEqual(_i8_json.loads(_i8_json.dumps(loops, allow_nan=False)), loops)

    def test_positive_area_projection_loss_refused_and_holes_preserved(self):
        import manifold3d as manifold
        tiny = _i8_Fraction(1, 10 ** 30)
        nodes, segments = loop_data([[_i8_Fraction(1), _i8_Fraction(1)], [_i8_Fraction(1) + tiny, _i8_Fraction(1)], [_i8_Fraction(1), _i8_Fraction(1) + tiny]])
        with self.assertRaisesRegex(ValueError, 'projection_not_certified'):
            _i8__side(nodes, segments, 'positive')
        frame = _i8_plane_frame([0.0, 0.0, 0.0], [0.0, 1.0], [0.0, 0.0, 0.0])
        hollow = manifold.Manifold.cube([4.0, 4.0, 4.0], center=True) - manifold.Manifold.cube([1.0, 1.0, 6.0], center=True)
        mesh = hollow.to_mesh64()
        record, domain = _i8_slice_solid((hollow, _i8_np.asarray(mesh.vert_properties[:, :3]), _i8_np.asarray(mesh.tri_verts)), frame, {'fixture': 'hole'})
        self.assertEqual(domain.area, 15.0)
        self.assertEqual(len(domain.interiors), 1)
        exact_bound = sum((_i8_Fraction(loop['projection_area_bound_rational']) for loop in record['identity_loops']))
        exact_bound += sum((_i8_Fraction(cap['projection_certificate']['projection_area_bound_rational']) for cap in record['coplanar_triangle_supports']))
        self.assertEqual(_i8_Fraction(record['projection_area_error_bound_rational']), exact_bound)
        self.assertGreaterEqual(_i8_Fraction(record['projection_area_error_bound_m2']), exact_bound)
        self.assertTrue(any((item.get('ray_parities') == [0, 0] for item in record['occupancy_witnesses'])))
        self.assertEqual(_i8_json.loads(_i8_json.dumps(record, allow_nan=False)), record)
