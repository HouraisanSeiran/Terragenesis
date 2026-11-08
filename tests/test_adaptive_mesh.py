"""Consolidated test_adaptive_mesh implementations; numeric expressions preserved."""
from __future__ import annotations
import unittest as _i79_unittest
import tempfile as _i79_tempfile
import hashlib as _i79_hashlib
from pathlib import Path as _i79_Path
from unittest.mock import patch as _i79_patch
import numpy as _i79_np
import copy as _i80_copy
from pathlib import Path as _i80_Path
import tempfile as _i80_tempfile
import subprocess as _i80_subprocess
import sys as _i80_sys
import unittest as _i80_unittest
from unittest.mock import patch as _i80_patch
import numpy as _i80_np
from tools.audit_adaptive_mesh import audit_step as _i80_audit_step
import tempfile as _i81_tempfile
from pathlib import Path as _i81_Path
import unittest as _i81_unittest
import numpy as _i81_np
import copy as _i82_copy
from pathlib import Path as _i82_Path
import shutil as _i82_shutil
import tempfile as _i82_tempfile
import unittest as _i82_unittest
import numpy as _i82_np
from tests.test_fine_subgrid import fixture as _x5_fixture
from tests.test_shallow_water import ShallowWaterSubgridSegmentedTests as _x6_ShallowWaterSubgridSegmentedTests
CATEGORY = 'B'

class AdaptiveSurfaceTests(_i79_unittest.TestCase):

    def test_archived_prefix_releases_only_owned_segments_and_keeps_random_access(self):
        from terrain_pipeline.adaptive_mesh import CompressedRecordList as _i79_CompressedRecordList
        from terrain_pipeline.adaptive_mesh import _encode as _i79__encode
        from terrain_pipeline.adaptive_mesh import _decode as _i79__decode
        with _i79_tempfile.TemporaryDirectory(dir=_i79_Path(__file__).resolve().parents[1] / '.scratch') as directory:
            work, saved = (_i79_Path(directory) / 'work', _i79_Path(directory) / 'saved')
            saved.mkdir()
            records = _i79_CompressedRecordList(work, memory_limit_bytes=1024, segment_limit_bytes=8192)
            sentinel = work / 'sentinel'
            sentinel.write_bytes(b'preserved')
            values = _i79_np.random.default_rng(61).normal(size=2048)
            for index in range(12):
                records.append(dict(index=index, values=values + index))
            for index in (-13, 12):
                with self.assertRaises(IndexError):
                    records[index]
            previous = records.temporary_storage_nbytes

            def loader(pin):
                payload = _i79_Path(pin['path']).read_bytes()
                if _i79_hashlib.sha256(payload).hexdigest() != pin['expected_sha256']:
                    raise ValueError('saved record immutable hash mismatch')
                return _i79__decode(payload)
            for index in range(12):
                item = records[index]
                payload = _i79__encode(item)
                path = saved / f'record-{index}.npz'
                path.write_bytes(payload)
                records.bind_saved_record(index, dict(path=str(path), expected_sha256=_i79_hashlib.sha256(payload).hexdigest()), loader)
                self.assertLessEqual(records.temporary_storage_nbytes, previous)
                previous = records.temporary_storage_nbytes
                _i79_np.testing.assert_array_equal(records[0]['values'], values)
                _i79_np.testing.assert_array_equal(records[-1]['values'], values + 11)
            self.assertEqual(records.temporary_storage_nbytes, 0)
            for index in (-13, 12):
                with self.assertRaises(IndexError):
                    records[index]
            with self.assertRaises(RuntimeError):
                records.append(dict(index=12, values=values + 12))
            self.assertEqual([item['index'] for item in records[::-3]], [11, 8, 5, 2])
            self.assertEqual(list(work.iterdir()), [sentinel])
            for index in reversed(range(12)):
                _i79_np.testing.assert_array_equal(records[index]['values'], values + index)
            records.close()
            self.assertEqual(sentinel.read_bytes(), b'preserved')
            (saved / 'record-0.npz').write_bytes(b'altered')
            with self.assertRaises(ValueError):
                records[0]

    def test_history_spills_and_keeps_all_records_without_resident_growth(self):
        from terrain_pipeline.adaptive_mesh import CompressedRecordList as _i79_CompressedRecordList
        with _i79_tempfile.TemporaryDirectory(dir=_i79_Path(__file__).resolve().parents[1] / '.scratch') as directory:
            records = _i79_CompressedRecordList(directory, memory_limit_bytes=1024)
            values = _i79_np.random.default_rng(13).normal(size=2048)
            for index in range(12):
                records.append(dict(index=index, values=values + index))
            self.assertEqual(len(records), 12)
            self.assertGreater(records.temporary_storage_nbytes, 1024)
            self.assertLess(records.storage_nbytes, records.serialized_nbytes / 4)
            for index, record in enumerate(records):
                self.assertEqual(record['index'], index)
                _i79_np.testing.assert_array_equal(record['values'], values + index)
            self.assertGreater(sum((path.stat().st_size for path in _i79_Path(directory).iterdir())), 0)
            records.close()
            self.assertEqual(list(_i79_Path(directory).iterdir()), [])

    def geometry(self, bed):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i79_build_adaptive_geometry
        request = _i79_np.full(bed.shape, 4, _i79_np.int64)
        request[:, :4] = 1
        request[:, 4:8] = 2
        return _i79_build_adaptive_geometry(bed, request)

    def run_surface(self, geometry, depth, duration=0.1, dynamic=False, forcing=None, tail=None):
        from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i79_SurfaceBudget
        from terrain_pipeline.adaptive_mesh import advance_adaptive_surface as _i79_advance_adaptive_surface
        rows, columns = depth.shape
        return _i79_advance_adaptive_surface(geometry, initial_depth_m=depth, forcing_interval_s=duration, intervals=1, forcing_provider=lambda i: _i79_np.zeros_like(depth) if forcing is None else forcing, boundary_stage_provider=lambda i: _i79_np.zeros(2 * (rows + columns)) if tail is None else tail, budget=_i79_SurfaceBudget(max_dt_s=0.025, max_snapshots=3, max_duration_s=duration, max_wall_s=120.0), dynamic_refinement=dynamic, halo_m=2)

    def test_partition_coverage_and_face_segments_are_unique_and_once(self):
        from terrain_pipeline.adaptive_mesh import validate_adaptive_geometry as _i79_validate_adaptive_geometry
        geometry = self.geometry(_i79_np.zeros((8, 16)))
        self.assertTrue(_i79_validate_adaptive_geometry(geometry))
        self.assertEqual(geometry['metadata']['leaf_counts'], {'1': 32, '2': 8, '4': 4})
        self.assertEqual(geometry['arrays']['leaf_area_m2'].sum(), 128)
        a = geometry['arrays']
        self.assertEqual(len(_i79_np.unique(_i79_np.column_stack((a['face_axis'], a['face_canonical_row'], a['face_canonical_column'])), axis=0)), len(a['face_left']))

    def test_mixed_full_half_wet_lakes_are_stationary(self):
        from terrain_pipeline.adaptive_mesh import initial_leaf_state as _i79_initial_leaf_state
        from terrain_pipeline.adaptive_mesh import adaptive_rhs as _i79_adaptive_rhs
        bed = _i79_np.random.default_rng(120).uniform(0.0, 1.0, (8, 16))
        geometry = self.geometry(bed)
        for stage in (0.4, 2.0):
            depth = _i79_np.maximum(stage - bed, 0.0)
            state = _i79_initial_leaf_state(geometry, depth)
            rhs, witness = _i79_adaptive_rhs(geometry, state, tailwater_m=_i79_np.zeros(48), dt=0.01)
            _i79_np.testing.assert_allclose(rhs, 0.0, rtol=0.0, atol=2e-13)
            result = self.run_surface(geometry, depth, duration=0.05)
            _i79_np.testing.assert_allclose(result['snapshots'][-1]['canonical_depth_m'], depth, rtol=0.0, atol=1e-12)
            self.assertLess(abs(result['ledger'][-1, -1]), 1e-10)

    def test_uniform_1m_rhs_and_drag_match_frozen_v7(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i79_build_adaptive_geometry
        from terrain_pipeline.adaptive_mesh import initial_leaf_state as _i79_initial_leaf_state
        from terrain_pipeline.adaptive_mesh import adaptive_rhs as _i79_adaptive_rhs
        from terrain_pipeline.adaptive_mesh import adaptive_drag as _i79_adaptive_drag
        from terrain_pipeline.shallow_water import shallow_water_rhs_accelerated as _i79_uniform_rhs
        from terrain_pipeline.shallow_water import manning_damping_accelerated as _i79_uniform_drag
        rng = _i79_np.random.default_rng(121)
        bed = rng.uniform(0.0, 0.3, (8, 16))
        geometry = _i79_build_adaptive_geometry(bed, _i79_np.ones(bed.shape, _i79_np.int64))
        uniform, support, datum = _x6_ShallowWaterSubgridSegmentedTests().geometry(bed, 1)
        depth = rng.uniform(0.01, 0.6, bed.shape)
        momentum = depth[:, :, None] * rng.uniform(-1.0, 1.0, (*bed.shape, 2))
        state = _i79_initial_leaf_state(geometry, depth, momentum)
        geometry['arrays']['boundary_kind'][:] = _i79_np.arange(48) % 3
        tail = _i79_np.full(48, 0.7)
        actual, witness = _i79_adaptive_rhs(geometry, state, tailwater_m=tail, dt=0.01)
        uniform_state = _i79_np.column_stack((depth.ravel(), momentum.reshape(-1, 2)))
        expected, uniform_witness = _i79_uniform_rhs(uniform_state, bed - datum, support=support, spacing=1.0, gravity=9.81, boundary_kind=geometry['arrays']['boundary_kind'], tailwater=tail - datum, roughness=0.035, dt=0.01)
        owner = geometry['arrays']['canonical_owner'].ravel()
        _i79_np.testing.assert_allclose(actual[owner], expected, rtol=0.0, atol=1e-12)
        _i79_np.testing.assert_allclose(witness['internal_flux_m2_s'], uniform_witness['internal_flux'], rtol=0.0, atol=1e-12)
        damping, factor = _i79_adaptive_drag(geometry, state, dt=0.01, gravity=9.81, roughness=0.035)
        expected_damping, expected_factor = _i79_uniform_drag(uniform_state, 0.01, 9.81, 0.035, support=support)
        _i79_np.testing.assert_allclose(damping[owner], expected_damping, rtol=0.0, atol=1e-14)
        _i79_np.testing.assert_allclose(factor[owner], expected_factor, rtol=0.0, atol=1e-14)

    def test_refinement_transfer_preserves_each_parent_water_and_momentum(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i79_build_adaptive_geometry
        from terrain_pipeline.adaptive_mesh import initial_leaf_state as _i79_initial_leaf_state
        from terrain_pipeline.adaptive_mesh import canonical_inventory as _i79_canonical_inventory
        from terrain_pipeline.adaptive_mesh import refine_adaptive_state as _i79_refine_adaptive_state
        bed = _i79_np.random.default_rng(122).uniform(0.0, 0.3, (8, 16))
        geometry = _i79_build_adaptive_geometry(bed, _i79_np.full(bed.shape, 4, _i79_np.int64))
        depth = _i79_np.maximum(0.25 - bed, 0.0)
        momentum = depth[:, :, None] * _i79_np.array([0.3, -0.2])
        state = _i79_initial_leaf_state(geometry, depth, momentum)
        requested = _i79_np.full(bed.shape, 4, _i79_np.int64)
        requested[:, :8] = 1
        refined, after, witness = _i79_refine_adaptive_state(geometry, state, requested)
        self.assertGreater(witness['added_leaf_count'], 0)
        _i79_np.testing.assert_allclose(witness['parent_grouped_residual'], 0.0, rtol=0.0, atol=1e-13)
        before_depth, before_momentum = _i79_canonical_inventory(geometry, state)
        after_depth, after_momentum = _i79_canonical_inventory(refined, after)
        _i79_np.testing.assert_allclose(after_depth, before_depth, rtol=0.0, atol=1e-14)
        _i79_np.testing.assert_allclose(after_momentum, before_momentum, rtol=0.0, atol=1e-14)

    def test_dry_front_is_pre_tagged_and_dynamic_run_matches_uniform_1m(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i79_build_adaptive_geometry
        from terrain_pipeline.adaptive_mesh import anticipated_spacing_map as _i79_anticipated_spacing_map
        bed = _i79_np.zeros((8, 32))
        depth = _i79_np.zeros_like(bed)
        depth[:, :8] = 1.0
        requested = _i79_anticipated_spacing_map(depth, halo_m=4)
        self.assertTrue(_i79_np.all(requested[:, 8:12] == 1))
        self.assertTrue(_i79_np.all(requested[:, 16:] == 4))
        adaptive = _i79_build_adaptive_geometry(bed, requested)
        uniform = _i79_build_adaptive_geometry(bed, _i79_np.ones(bed.shape, _i79_np.int64))
        actual = self.run_surface(adaptive, depth, duration=0.2, dynamic=True)
        reference = self.run_surface(uniform, depth, duration=0.2)
        _i79_np.testing.assert_allclose(actual['snapshots'][-1]['canonical_depth_m'], reference['snapshots'][-1]['canonical_depth_m'], rtol=0.0, atol=1e-10)
        self.assertLess(abs(actual['ledger'][-1, -1]), 1e-10)
        self.assertLess(actual['metadata']['maximum_active_leaf_count'], bed.size)
        for epoch in actual['epoch_packets']:
            a = actual['geometries'][epoch['geometry_identity']]['arrays']
            net = _i79_np.zeros_like(epoch['state_before'])
            _i79_np.add.at(net, a['face_left'], -epoch['internal_transfer'])
            _i79_np.add.at(net, a['face_right'], epoch['internal_transfer'])
            _i79_np.add.at(net, a['boundary_cell'], -epoch['boundary_transfer'])
            net[:, 0] += epoch['forcing_volume_m3']
            net[:, 1:] += epoch['bed_impulse'] + epoch['manning_impulse']
            _i79_np.testing.assert_allclose((epoch['state_after'] - epoch['state_before']) * a['leaf_area_m2'][:, None], net, rtol=0.0, atol=1e-12)

    def test_tiny_uniform_forcing_is_retained_without_forcing_all_refinement(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i79_build_adaptive_geometry
        bed = _i79_np.zeros((8, 16))
        geometry = _i79_build_adaptive_geometry(bed, _i79_np.full(bed.shape, 4, _i79_np.int64))
        source = _i79_np.full_like(bed, 1e-12)
        result = self.run_surface(geometry, _i79_np.zeros_like(bed), duration=0.05, dynamic=True, forcing=source)
        self.assertEqual(result['snapshots'][-1]['leaf_counts'], {'1': 0, '2': 0, '4': 8})
        _i79_np.testing.assert_allclose(result['snapshots'][-1]['canonical_depth_m'], source * 0.05, rtol=0.0, atol=1e-26)
        self.assertEqual(result['metadata']['supplied_m3'], float(source.sum() * 0.05))

    def test_compressed_geometry_history_is_immutable_and_decodes_without_building(self):
        from terrain_pipeline.adaptive_mesh import CompressedGeometryHistory as _i79_CompressedGeometryHistory
        geometry = self.geometry(_i79_np.zeros((8, 16)))
        history = _i79_CompressedGeometryHistory()
        history.register(geometry)
        identity = geometry['identity_sha256']
        geometry['arrays']['canonical_bed_m'][0, 0] = 99.0
        with _i79_patch('terrain_pipeline.adaptive_mesh.build_adaptive_geometry', side_effect=AssertionError('generation forbidden')):
            decoded = history[identity]
        self.assertEqual(decoded['arrays']['canonical_bed_m'][0, 0], 0.0)
        self.assertEqual(decoded['identity_sha256'], identity)

    def test_forcing_pre_tag_refines_all_and_reports_zero_savings(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i79_build_adaptive_geometry
        bed = _i79_np.zeros((8, 16))
        geometry = _i79_build_adaptive_geometry(bed, _i79_np.full(bed.shape, 4, _i79_np.int64))
        result = self.run_surface(geometry, _i79_np.zeros_like(bed), duration=0.05, dynamic=True, forcing=_i79_np.full_like(bed, 0.001))
        self.assertEqual(result['snapshots'][-1]['leaf_counts'], {'1': bed.size, '2': 0, '4': 0})
        self.assertEqual(result['metadata']['maximum_active_leaf_count'], bed.size)
        self.assertFalse(result['metadata']['uniform_coarse_convergence_claim'])
        self.assertLess(abs(result['ledger'][-1, -1]), 1e-12)

    def test_interval_rk_packet_mass_and_momentum_close(self):
        bed = _i79_np.zeros((8, 16))
        geometry = self.geometry(bed)
        depth = _i79_np.ones_like(bed)
        depth[:, :4] = 2.0
        result = self.run_surface(geometry, depth, duration=0.05)
        packet = result['first_rk_packets'][0]
        area, dt = (packet['leaf_area_m2'], packet['dt_s'])
        net = _i79_np.zeros_like(packet['state_before'])
        internal = 0.5 * dt * (packet['rk1_internal_flux'] + packet['rk2_internal_flux'])
        boundary = 0.5 * dt * (packet['rk1_boundary_flux'] + packet['rk2_boundary_flux'])
        _i79_np.add.at(net, packet['face_left'], -internal)
        _i79_np.add.at(net, packet['face_right'], internal)
        _i79_np.add.at(net, packet['boundary_cell'], -boundary)
        net /= area[:, None]
        net += 0.5 * dt * (packet['rk1_bed_source'] + packet['rk2_bed_source'])
        net[:, 1:] += packet['manning_momentum_change']
        _i79_np.testing.assert_allclose(packet['state_after'] - packet['state_before'], net, rtol=0.0, atol=2e-14)

    def test_small_pulse_crosses_coarse_fine_interface_without_large_reflection(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i79_build_adaptive_geometry
        bed = _i79_np.zeros((4, 64))
        x = _i79_np.arange(64) + 0.5
        depth = _i79_np.tile(1.0 + 0.001 * _i79_np.exp(-((x - 20) / 4) ** 2), (4, 1))
        requested = _i79_np.full(bed.shape, 2, _i79_np.int64)
        requested[:, :32] = 1
        adaptive = _i79_build_adaptive_geometry(bed, requested)
        uniform = _i79_build_adaptive_geometry(bed, _i79_np.ones(bed.shape, _i79_np.int64))
        actual = self.run_surface(adaptive, depth, duration=5.0, dynamic=False)
        reference = self.run_surface(uniform, depth, duration=5.0)
        difference = actual['snapshots'][-1]['canonical_depth_m'] - reference['snapshots'][-1]['canonical_depth_m']
        self.assertLess(float(abs(difference[:, :28]).max()), 0.0002)
        self.assertLess(float(abs(difference).max()), 0.0003)
        self.assertLess(abs(actual['ledger'][-1, -1]), 1e-10)

def run_fixture():
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i80_SurfaceBudget
    from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i80_build_adaptive_geometry
    from terrain_pipeline.adaptive_mesh import advance_adaptive_surface as _i80_advance_adaptive_surface
    bed = _i80_np.tile(_i80_np.arange(16) * 0.015, (12, 1)) + 0.003 * _i80_np.arange(12)[:, None]
    geometry = _i80_build_adaptive_geometry(bed, _i80_np.full(bed.shape, 4, _i80_np.int64))
    depth = _i80_np.maximum(0.08 - bed, 0)
    forcing = _i80_np.zeros((2, *bed.shape))
    forcing[:, 10, 14] = 1e-14
    tailwater = _i80_np.zeros((2, 2 * sum(bed.shape)))
    budget = _i80_SurfaceBudget(max_dt_s=0.01, max_snapshots=4, max_duration_s=1.0, max_cells=65536, max_bytes=268435456, max_wall_s=1800.0)
    result = _i80_advance_adaptive_surface(geometry, initial_depth_m=depth, forcing_interval_s=0.02, intervals=2, forcing_provider=lambda i: forcing[i], boundary_stage_provider=lambda i: tailwater[i], budget=budget, halo_m=2)
    return (result, forcing, tailwater, budget)

class AdaptiveIOTests(_i80_unittest.TestCase):

    def test_archive_binding_releases_segments_preserves_random_reads_and_rejects_tampering(self):
        from terrain_pipeline.common_infra import save_bundle as _i80_save_bundle
        from terrain_pipeline.common_infra import file_sha256 as _i80_file_sha256
        from terrain_pipeline.common_infra import identity as _i80_identity
        from terrain_pipeline.adaptive_mesh import save_adaptive_run as _i80_save_adaptive_run
        from terrain_pipeline.adaptive_mesh import load_adaptive_run as _i80_load_adaptive_run
        from terrain_pipeline.adaptive_mesh import CompressedRecordList
        from terrain_pipeline.adaptive_mesh import CompressedGeometryHistory
        result, forcing, tailwater, budget = run_fixture()
        with _i80_tempfile.TemporaryDirectory() as temporary:
            root = _i80_Path(temporary)
            histories = []
            for name in ('snapshots', 'epoch_packets', 'refinement_transactions', 'first_rk_packets'):
                original = result[name]
                collection = CompressedRecordList(root / 'scratch', memory_limit_bytes=128)
                collection._file._segment_limit = 512
                for record in original:
                    collection.append(record)
                result[name] = collection
                histories.append(collection)
            original_geometries = result['geometries']
            geometries = CompressedGeometryHistory(root / 'scratch', memory_limit_bytes=128)
            geometries._records._file._segment_limit = 512
            for geometry in original_geometries.values():
                geometries.register(geometry)
            result['geometries'] = geometries
            histories.append(geometries)
            expected_snapshots = [_i80_copy.deepcopy(item) for item in result['snapshots']]
            source = root / 'source.npz'
            arrays = dict(canonical_bed_m=result['geometry']['arrays']['canonical_bed_m'])
            metadata = dict(schema='test-source')
            _i80_save_bundle(source, dict(arrays=arrays, metadata=metadata, identity_sha256=_i80_identity(arrays, metadata)), validator=lambda item: True)
            observations = []
            repo = _i80_Path(__file__).resolve().parents[1]
            name = 'terrain_pipeline/adaptive_mesh.py'
            pin = _i80_save_adaptive_run(root / 'run', result, forcing_m3_s=forcing, tailwater_m=tailwater, forcing_interval_s=0.02, budget=budget, source_record=dict(path=str(source), expected_sha256=_i80_file_sha256(source)), code_sha256={name: _i80_file_sha256(repo / name)}, resource_observer=lambda: observations.append(sum((item.temporary_storage_nbytes for item in histories))))
            self.assertGreater(max(observations), 0)
            self.assertEqual(observations[-1], 0)
            self.assertEqual(list((root / 'scratch').iterdir()), [])
            for number in (2, 0, 1):
                actual = result['snapshots'][number]
                self.assertEqual(set(actual), set(expected_snapshots[number]))
                for field in ('state', 'canonical_depth_m', 'canonical_momentum_m2_s'):
                    _i80_np.testing.assert_array_equal(actual[field], expected_snapshots[number][field])
            for key in reversed(list(result['geometries'])):
                self.assertEqual(result['geometries'][key]['identity_sha256'], key)
            for field in ('epoch_packets', 'refinement_transactions', 'first_rk_packets'):
                for number in reversed(range(len(result[field]))):
                    self.assertNotIn('schema', result[field][number])
            loaded = _i80_load_adaptive_run(pin['path'], expected_sha256=pin['expected_sha256'])
            snapshot_path = _i80_Path(loaded['index']['snapshots'][0]['path'])
            snapshot_path.write_bytes(b'tampered immutable snapshot')
            with self.assertRaises(ValueError):
                result['snapshots'][0]
            first_geometry = next(iter(result['geometries']))
            geometry_path = _i80_Path(loaded['index']['geometries'][first_geometry]['path'])
            geometry_path.write_bytes(b'tampered immutable geometry')
            with self.assertRaises(ValueError):
                result['geometries'][first_geometry]
            for item in histories:
                if hasattr(item, 'close'):
                    item.close()
                else:
                    item._records.close()

    def test_grouped_storage_inverse_is_bitwise_equivalent_at_wetting_thresholds(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i80_build_adaptive_geometry
        from terrain_pipeline.adaptive_mesh import storage_stage as _i80_storage_stage
        bed = _i80_np.random.default_rng(42).uniform(-2, 3, (12, 16))
        requested = _i80_np.full(bed.shape, 4, _i80_np.int64)
        requested[:4, :4] = 1
        requested[4:8, :4] = 2
        geometry = _i80_build_adaptive_geometry(bed, requested)
        a = geometry['arrays']
        self.assertEqual(set(a['subcell_count']), {1, 4, 16})
        depths = [_i80_np.zeros(len(a['leaf_row'])), _i80_np.random.default_rng(43).uniform(0, 3, len(a['leaf_row']))]
        for wet_count in range(1, 17):
            wet = _i80_np.minimum(wet_count, a['subcell_count'])
            indices = a['subcell_offset'] + wet - 1
            depths.append((wet * a['sorted_subcell_bed_relative_m'][indices] - a['prefix_subcell_bed_relative_m'][indices]) / a['subcell_count'])
        for depth in depths:
            expected = _i80_np.empty(len(depth))
            for cell, count in enumerate(a['subcell_count']):
                offset = a['subcell_offset'][cell]
                sorted_bed = a['sorted_subcell_bed_relative_m'][offset:offset + count]
                prefix = a['prefix_subcell_bed_relative_m'][offset:offset + count]
                volume = depth[cell] * count
                wet = max(int(_i80_np.sum(volume >= _i80_np.arange(1, count + 1) * sorted_bed - prefix)), 1)
                expected[cell] = (volume + prefix[wet - 1]) / wet
            _i80_np.testing.assert_array_equal(_i80_storage_stage(depth, geometry).view(_i80_np.uint64), expected.view(_i80_np.uint64))

    def test_archive_cold_roundtrip_and_independent_physical_samples(self):
        from terrain_pipeline.common_infra import save_bundle as _i80_save_bundle
        from terrain_pipeline.common_infra import file_sha256 as _i80_file_sha256
        from terrain_pipeline.common_infra import identity as _i80_identity
        from terrain_pipeline.adaptive_mesh import save_adaptive_run as _i80_save_adaptive_run
        from terrain_pipeline.adaptive_mesh import load_adaptive_run as _i80_load_adaptive_run
        result, forcing, tailwater, budget = run_fixture()
        with _i80_tempfile.TemporaryDirectory() as temporary:
            root = _i80_Path(temporary)
            source = root / 'source.npz'
            arrays = dict(canonical_bed_m=result['geometry']['arrays']['canonical_bed_m'])
            metadata = dict(schema='test-source')
            _i80_save_bundle(source, dict(arrays=arrays, metadata=metadata, identity_sha256=_i80_identity(arrays, metadata)), validator=lambda item: True)
            repo = _i80_Path(__file__).resolve().parents[1]
            name = 'terrain_pipeline/adaptive_mesh.py'
            pin = _i80_save_adaptive_run(root / 'run', result, forcing_m3_s=forcing, tailwater_m=tailwater, forcing_interval_s=0.02, budget=budget, source_record=dict(path=str(source), expected_sha256=_i80_file_sha256(source)), code_sha256={name: _i80_file_sha256(repo / name)})
            with _i80_patch('terrain_pipeline.adaptive_mesh.build_adaptive_geometry', side_effect=RuntimeError('forbidden')), _i80_patch('terrain_pipeline.adaptive_mesh.advance_adaptive_surface', side_effect=RuntimeError('forbidden')), _i80_patch('terrain_pipeline.adaptive_mesh.adaptive_rhs', side_effect=RuntimeError('forbidden')), _i80_patch('terrain_pipeline.adaptive_mesh.refine_adaptive_state', side_effect=RuntimeError('forbidden')):
                loaded = _i80_load_adaptive_run(pin['path'], expected_sha256=pin['expected_sha256'])
                for step in loaded['first_steps']:
                    _i80_audit_step(step, loaded['geometries'][step['geometry_identity']], vars(budget))
            self.assertEqual(len(loaded['snapshots']), 3)
            self.assertFalse(loaded['solver_advanced'])
            self.assertGreater(len(loaded['refinements']), 0)
            script = "from contextlib import ExitStack\nfrom unittest.mock import patch\nimport terrain_pipeline.adaptive_mesh as adaptive\ndef forbidden(*args, **kwargs): raise AssertionError('execution during cold read')\nwith ExitStack() as guards:\n    for name in ('build_adaptive_geometry', 'advance_adaptive_surface', 'adaptive_rhs', 'refine_adaptive_state'):\n        guards.enter_context(patch.object(adaptive, name, forbidden))\n    r=adaptive.load_adaptive_run(" + repr(pin['path']) + ',expected_sha256=' + repr(pin['expected_sha256']) + ")\n    assert not r['solver_advanced']\n    assert len(r['snapshots'])==3\n"
            cold = _i80_subprocess.run([_i80_sys.executable, '-B', '-c', script], cwd=repo, capture_output=True, text=True, check=False)
            self.assertEqual(cold.returncode, 0, cold.stderr)

    def test_coordinated_algebra_valid_false_physical_flux_rejected(self):
        from terrain_pipeline.adaptive_mesh import _validate_step_algebra as _i80__validate_step_algebra
        result, _, _, budget = run_fixture()
        packet = _i80_copy.deepcopy(result['first_rk_packets'][0])
        geometry = result['geometries'][packet['geometry_identity']]
        a = geometry['arrays']
        packet['rk2_internal_flux'][0] += _i80_np.array([0.0001, 0.0002, 0.0003])
        rhs = packet['rk2_bed_source'].copy()
        _i80_np.add.at(rhs, a['face_left'], -packet['rk2_internal_flux'] / a['leaf_area_m2'][a['face_left'], None])
        _i80_np.add.at(rhs, a['face_right'], packet['rk2_internal_flux'] / a['leaf_area_m2'][a['face_right'], None])
        _i80_np.add.at(rhs, a['boundary_cell'], -packet['rk2_boundary_flux'] / a['leaf_area_m2'][a['boundary_cell'], None])
        rhs[:, 0] += packet['forcing_m3_s'] / a['leaf_area_m2']
        undamped = 0.5 * packet['state_before'] + 0.5 * (packet['state_predictor'] + packet['dt_s'] * rhs)
        from terrain_pipeline.adaptive_mesh import adaptive_drag
        damping, factor = adaptive_drag(geometry, undamped, dt=packet['dt_s'], gravity=budget.gravity_m_s2, roughness=budget.roughness_s_m_third)
        packet['state_after'] = undamped.copy()
        packet['state_after'][:, 1:] *= damping[:, None]
        packet['manning_momentum_change'] = packet['state_after'][:, 1:] - undamped[:, 1:]
        packet['manning_inverse_depth_third_mean'] = factor
        _i80__validate_step_algebra(packet, geometry, vars(budget))
        with self.assertRaisesRegex(ValueError, 'physical RK'):
            _i80_audit_step(packet, geometry, vars(budget))

    def test_resigned_geometry_epoch_and_refinement_corruption_rejected(self):
        from terrain_pipeline.adaptive_mesh import validate_geometry as _i80_validate_geometry
        from terrain_pipeline.adaptive_mesh import validate_epoch as _i80_validate_epoch
        from terrain_pipeline.adaptive_mesh import apply_transaction as _i80_apply_transaction
        result, _, _, _ = run_fixture()
        geometry = _i80_copy.deepcopy(result['geometry'])
        geometry['arrays']['face_crest_relative_m'][0] += 0.1
        from terrain_pipeline.surface_identity import geometry_identity
        geometry['identity_sha256'] = geometry_identity(geometry['arrays'], geometry['metadata'])
        with self.assertRaises(ValueError):
            _i80_validate_geometry(geometry)
        epoch = _i80_copy.deepcopy(result['epoch_packets'][0])
        epoch['bed_impulse'][0, 0] += 0.1
        with self.assertRaises(ValueError):
            _i80_validate_epoch(epoch, result['geometries'][epoch['geometry_identity']])
        transaction = _i80_copy.deepcopy(result['refinement_transactions'][0])
        before = result['geometries'][transaction['before_geometry_identity']]
        after = result['geometries'][transaction['after_geometry_identity']]
        transaction['child_inventory_m3_m4_s'][0, 0] += 0.1
        with self.assertRaises(ValueError):
            _i80_apply_transaction(transaction, before, after, result['snapshots'][0]['state'])

class SegmentedSpoolTests(_i81_unittest.TestCase):

    def test_cross_segment_random_reads_preserve_every_byte_and_bounds(self):
        from terrain_pipeline.adaptive_mesh import SegmentedWorkspaceSpool as _i81_SegmentedWorkspaceSpool
        directory = _i81_Path(__file__).resolve().parents[1] / '.scratch'
        with _i81_tempfile.TemporaryDirectory(dir=directory) as folder:
            spool = _i81_SegmentedWorkspaceSpool(folder, memory_limit_bytes=1024, segment_limit_bytes=8192)
            first = _i81_np.random.default_rng(18).bytes(20000)
            second = _i81_np.random.default_rng(19).bytes(31000)
            spool.write(first)
            spool.write(second)
            spool.flush()
            self.assertLessEqual(max((path.stat().st_size for path in _i81_Path(folder).iterdir())), 8192)
            self.assertGreater(spool.temporary_storage_nbytes, 40000)
            self.assertLessEqual(spool.resident_nbytes, 1024)
            spool.seek(0)
            self.assertEqual(spool.read(), first + second)
            for offset, length in ((8000, 22000), (19000, 15000), (49000, 2000)):
                spool.seek(offset)
                self.assertEqual(spool.read(length), (first + second)[offset:offset + length])
            spool.seek(0)
            with self.assertRaises(ValueError):
                spool.write(b'immutable')
            spool.seek(0, 2)
            spool.write(b'endpoint')
            spool.seek(len(first) + len(second))
            self.assertEqual(spool.read(), b'endpoint')
            spool.close()
            self.assertEqual(list(_i81_Path(folder).iterdir()), [])

    def test_rejects_unbounded_file_and_ram_configuration(self):
        from terrain_pipeline.adaptive_mesh import SegmentedWorkspaceSpool as _i81_SegmentedWorkspaceSpool
        for memory, segment in ((0, 1024), (2048, 1024), (1024, 257 * 1024 ** 2)):
            with self.assertRaises(ValueError):
                _i81_SegmentedWorkspaceSpool('unused', memory_limit_bytes=memory, segment_limit_bytes=segment)

class AdaptiveWaterTests(_i82_unittest.TestCase):

    def setUp(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_geometry as _i82_build_adaptive_geometry
        from terrain_pipeline.adaptive_mesh import _bundle as _i82__bundle
        _, self.bed = _x5_fixture()
        canonical = self.bed['arrays']['H2_m']
        requested = _i82_np.full(canonical.shape, 4, _i82_np.int64)
        requested[:4, :4] = 1
        self.geometry = _i82_build_adaptive_geometry(canonical, requested, origin_m_xz=self.bed['metadata']['origin_m_xz'])
        a = self.geometry['arrays']
        stage = canonical.max() + 0.25 - self.geometry['metadata']['hydraulic_datum_m']
        depth = stage - (canonical - self.geometry['metadata']['hydraulic_datum_m'])
        mean = _i82_np.bincount(a['canonical_owner'].ravel(), weights=depth.ravel()) / a['leaf_area_m2']
        record = dict(state=_i82_np.column_stack((mean, _i82_np.zeros((len(mean), 2)))), geometry_identity=self.geometry['identity_sha256'], time_s=30.0, leaf_counts=self.geometry['metadata']['leaf_counts'], leaf_area_m2=self.geometry['metadata']['leaf_area_m2'], leaf_stage_relative_m=_i82_np.full(len(mean), stage), canonical_depth_m=depth, canonical_momentum_m2_s=_i82_np.zeros((*depth.shape, 2)), **{name: a[name].copy() for name in ('leaf_row', 'leaf_column', 'leaf_spacing_m', 'canonical_owner')})
        self.snapshot = _i82__bundle(record, 'surface-adaptive-canonical-snapshot-v1')

    def test_mixed_leaf_inventory_fan_preserves_each_canonical_volume(self):
        from terrain_pipeline.adaptive_mesh import build_adaptive_water_frame as _i82_build_adaptive_water_frame
        frame = _i82_build_adaptive_water_frame(self.bed, self.snapshot, self.geometry, state_index=1)
        _i82_np.testing.assert_allclose(frame['arrays']['cell_volume_m3'], self.snapshot['arrays']['canonical_depth_m'], atol=1e-10)
        self.assertEqual(frame['metadata']['adaptive_snapshot_identity'], self.snapshot['identity_sha256'])
        self.assertEqual(frame['metadata']['leaf_count'], 240)
        self.assertEqual(frame['metadata']['omitted_wet_cell_count'], 0)

    def test_resigned_snapshot_and_frame_source_substitution_rejected(self):
        from terrain_pipeline.common_infra import identity as _i82_identity
        from terrain_pipeline.adaptive_mesh import build_adaptive_water_frame as _i82_build_adaptive_water_frame
        from terrain_pipeline.adaptive_mesh import validate_bound_adaptive_water_frame as _i82_validate_bound_adaptive_water_frame
        frame = _i82_build_adaptive_water_frame(self.bed, self.snapshot, self.geometry, state_index=1)
        changed = _i82_copy.deepcopy(self.snapshot)
        changed['arrays']['canonical_depth_m'][0, 0] += 0.1
        changed['identity_sha256'] = _i82_identity(changed['arrays'], changed['metadata'])
        with self.assertRaises(ValueError):
            _i82_validate_bound_adaptive_water_frame(frame, self.bed, changed, self.geometry)
        changed_frame = _i82_copy.deepcopy(frame)
        changed_frame['metadata']['adaptive_snapshot_identity'] = 'a' * 64
        changed_frame['identity_sha256'] = _i82_identity(changed_frame['arrays'], changed_frame['metadata'])
        with self.assertRaises(ValueError):
            _i82_validate_bound_adaptive_water_frame(changed_frame, self.bed, self.snapshot, self.geometry)

    def test_public_consumer_loads_relocated_sources_and_rejects_frame_order(self):
        from terrain_pipeline.common_infra import file_sha256 as _i82_file_sha256
        from terrain_pipeline.common_infra import save_bundle as _i82_save_bundle
        from terrain_pipeline.adaptive_mesh import _bundle as _i82__bundle
        from terrain_pipeline.adaptive_mesh import build_adaptive_water_frame as _i82_build_adaptive_water_frame
        from terrain_pipeline.adaptive_mesh import load_consumer_adaptive_frame as _i82_load_consumer_adaptive_frame
        frame = _i82_build_adaptive_water_frame(self.bed, self.snapshot, self.geometry, state_index=0)
        geometry = _i82__bundle(dict(self.geometry['arrays'], raw_geometry_metadata=self.geometry['metadata'], raw_geometry_identity=self.geometry['identity_sha256']), 'surface-adaptive-geometry-v1')
        with _i82_tempfile.TemporaryDirectory() as temporary:
            source = _i82_Path(temporary) / 'source'
            source.mkdir()
            artifacts = []
            for name, bundle in (('bed.npz', self.bed), ('snapshot.npz', self.snapshot), ('geometry.npz', geometry), ('frame.npz', frame)):
                target = source / name
                _i82_save_bundle(target, bundle, validator=lambda value: True)
                artifacts.append(dict(path=name, sha256=_i82_file_sha256(target), identity_sha256=bundle['identity_sha256']))
            moved = _i82_Path(temporary) / 'moved'
            _i82_shutil.move(str(source), str(moved))
            context = dict(manifest=dict(backend='adaptive-saved-canonical-fan', artifacts=artifacts, scenarios=dict(test=dict(geometry='bed.npz', frames=[dict(frame=0, time_s=30.0, artifact='frame.npz', snapshot='snapshot.npz', adaptive_geometry='geometry.npz')]))), allowlist={item['path']: moved / item['path'] for item in artifacts})
            loaded = _i82_load_consumer_adaptive_frame(context, scenario='test', frame_index=0)
            self.assertFalse(loaded['solver_advanced'])
            self.assertEqual(loaded['frame']['identity_sha256'], frame['identity_sha256'])
            context['manifest']['scenarios']['test']['frames'][0]['time_s'] = 60.0
            with self.assertRaises(ValueError):
                _i82_load_consumer_adaptive_frame(context, scenario='test', frame_index=0)
