"""Consolidated tests.test_td_source_regions implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json as _i5_json
import contextlib as _i5_contextlib
import io as _i5_io
import tempfile as _i5_tempfile
import unittest as _i5_unittest
from pathlib import Path as _i5_Path
from types import SimpleNamespace as _i5_SimpleNamespace
from unittest.mock import patch as _i5_patch
import numpy as _i5_np
from terrain_pipeline.td_source import make_spec as _i5_make_spec
from terrain_pipeline.td_source import open_region_registry as _i5_open_registry
from terrain_pipeline.td_source import plan_region_store as _i5_plan
from terrain_pipeline.td_source import prepare_region_store as _i5_prepare
from terrain_pipeline.td_source import read_region_component as _i5_read_component
from terrain_pipeline.common_infra import file_sha256 as _i5_file_sha256
from tools import prepare_world_terrain_region as _i5_prepare_world_terrain_region
from tools import query_world_terrain_region as _i5_query_world_terrain_region
import tempfile as _i6_tempfile
import unittest as _i6_unittest
import contextlib as _i6_contextlib
import io as _i6_io
import json as _i6_json
from pathlib import Path as _i6_Path
import numpy as _i6_np
from terrain_pipeline.td_source import open_disk_registry as _i6_open_registry
from terrain_pipeline.td_source import plan_disk_region as _i6_plan
from terrain_pipeline.td_source import prepare_disk_region as _i6_prepare
from terrain_pipeline.td_source import read_disk_manifest as _i6_read_manifest
from terrain_pipeline.td_source import make_spec as _i6_make_spec
from tools.query_world_terrain_region import main as _i6_query
import hashlib as _i7_hashlib
import json as _i7_json
import tempfile as _i7_tempfile
import unittest as _i7_unittest
from pathlib import Path as _i7_Path
import numpy as _i7_np
from terrain_pipeline.td_source import compose_source as _i7_compose_source
from terrain_pipeline.td_source import crop_composition as _i7_crop_composition
from terrain_pipeline.td_source import compose_window as _i7_compose_window
from terrain_pipeline.td_source import inspect_window_support as _i7_inspect_window_support
from terrain_pipeline.world_water_layout import LayoutSpec as _i7_LayoutSpec
import unittest as _i8_unittest
from unittest.mock import patch as _i8_patch
import numpy as _i8_np
from terrain_pipeline.td_source import compose_source as _i8_compose_source
from terrain_pipeline.td_source import crop_composition as _i8_crop_composition
from terrain_pipeline.td_source import make_ocean_plan as _i8_make_ocean_plan
from terrain_pipeline.td_source import sample_ocean_mask as _i8_sample_ocean_mask
from terrain_pipeline.world_water_layout import LayoutSpec as _i8_LayoutSpec
from terrain_pipeline.world_water_layout import layout_field as _i8_layout_field

CATEGORY = 'B'

# Source: tests.test_world_terrain_store
class StoreTests(_i5_unittest.TestCase):

    def test_old_preparation_revision_requires_new_store(self):
        with _i5_tempfile.TemporaryDirectory() as directory:
            root = _i5_Path(directory)
            spec = _i5_make_spec('lakes')
            forcing = {'runoff_m_per_year': 0.5, 'duration_seconds': 100.0, 'channel_threshold_m3_s': 0.1}
            registry = _i5_open_registry(root, spec, 'physical', forcing)
            registry['world'].pop('preparation_revision')
            (root / 'registry.json').write_text(_i5_json.dumps(registry), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'use a new store'):
                _i5_open_registry(root, spec, 'physical', forcing)
            registry['world']['preparation_revision'] = 'older'
            (root / 'registry.json').write_text(_i5_json.dumps(registry), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'use a new store'):
                _i5_open_registry(root, spec, 'physical', forcing)

    def test_generation_does_not_duplicate_halo_pages(self):
        request = {'origin_native_xz': [464, 464], 'shape_zx': [1, 1]}
        support = {'support_origin_native_xz': [446, 446], 'missing_mask': _i5_np.ones((37, 37), bool)}
        args = _i5_SimpleNamespace(source_family='physical-default-v1', model_dir='model', store='store')
        with _i5_patch('diffusion.world_demand_backend.run_source_page', return_value={'path': 'page', 'sha256': 'a' * 64}) as run:
            records = _i5_prepare_world_terrain_region.generate_page(request, support, args)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [440, 440])
        self.assertEqual(records, [{'path': 'page', 'sha256': 'a' * 64}])

    def test_real_cli_adjacent_regions_and_query(self):
        with _i5_tempfile.TemporaryDirectory() as directory:
            root = _i5_Path(directory)
            page = root / 'page.npz'
            z, x = _i5_np.indices((64, 64))
            elevation = (200.0 + 0.3 * x + 0.1 * z + _i5_np.sin(x / 4.0)).astype(_i5_np.float64)
            metadata = {'schema': 'td-native-page-v1', 'native_origin': [100, 100], 'size': 64, 'spacing_m': 30.0, 'world_seed': 20261020}
            _i5_np.savez(page, elevation_native=elevation, metadata_json=_i5_json.dumps(metadata))
            pages = root / 'pages.json'
            pages.write_text(_i5_json.dumps([{'path': str(page), 'sha256': _i5_file_sha256(page)}]), encoding='utf-8')
            store = root / 'store'
            common = ['--store', str(store), '--source-family', 'physical-default-v1', '--sigma-cells', '1', '--runoff-m-per-year', '.5', '--duration-seconds', '86400', '--channel-threshold-m3-s', '.000001']
            with _i5_contextlib.redirect_stdout(_i5_io.StringIO()):
                _i5_prepare_world_terrain_region.main(common + ['--pages-json', str(pages), '--origin', '116', '128', '--shape', '12', '12'])
                _i5_prepare_world_terrain_region.main(common + ['--origin', '128', '128', '--shape', '12', '12'])
            registry = _i5_json.loads((store / 'registry.json').read_text(encoding='utf-8'))
            self.assertEqual(len(registry['components']), 1)
            self.assertEqual(registry['prepared_cells'], 288)
            arrays, meta = _i5_read_component(store, registry['components'][0], registry['world_identity'])
            cols = _i5_np.arange(116, 140)[None, :]
            crosses = (arrays['receiver'] >= 0) & ((cols < 128) & (arrays['receiver_native_x'] >= 128) | (cols >= 128) & (arrays['receiver_native_x'] < 128))
            self.assertTrue(crosses.any())
            output = _i5_io.StringIO()
            with _i5_contextlib.redirect_stdout(output):
                _i5_query_world_terrain_region.main([str(store), '--native-xz', '128', '130'])
            result = _i5_json.loads(output.getvalue())
            self.assertIn('receiver_native_x', result['values'])
            self.assertIn('spill_receiver_native_x', result['values'])
            self.assertIn('basin_transfer_links', result)

    def test_merge_resume_failure_and_identity(self):
        with _i5_tempfile.TemporaryDirectory() as directory:
            root = _i5_Path(directory)
            spec = _i5_make_spec('lakes')
            forcing = {'runoff_m_per_year': 0.5, 'duration_seconds': 100.0, 'channel_threshold_m3_s': 0.1}
            registry = _i5_open_registry(root, spec, 'physical', forcing)
            calls = []

            def coverage(origin, shape, pages):
                return {'missing_cells': 0}

            def compose(spec, pages, origin, shape, **kwargs):
                calls.append((origin, shape))
                return {'composed_elevation_m': _i5_np.ones(shape), 'metadata': {}}

            def form(composition, origin, **kwargs):
                return {'arrays': {'final_bed_m': composition['composed_elevation_m']}, 'metadata': {}, 'identity_sha256': 'water'}

            def render(arrays, origin, path):
                path.write_bytes(b'image')
            first_plan = _i5_plan(registry, [10, 20], [3, 4], [], coverage)
            first = _i5_prepare(root, registry, first_plan, [], spec, compose=compose, form=form, render=render)
            hit = _i5_plan(registry, [11, 21], [1, 1], [], coverage)
            self.assertEqual(_i5_prepare(root, registry, hit, [], spec, compose=compose, form=form, render=render), first)
            self.assertEqual(len(calls), 1)
            joined = _i5_plan(registry, [14, 20], [3, 2], [], coverage)
            second = _i5_prepare(root, registry, joined, [], spec, compose=compose, form=form, render=render)
            self.assertEqual(calls[-1], ([10, 20], [3, 6]))
            self.assertTrue((root / 'versions' / first['version']).is_dir())
            self.assertEqual(registry['prepared_cells'], 18)
            arrays, _ = _i5_read_component(root, second, registry['world_identity'])
            self.assertEqual(arrays['final_bed_m'].shape, (3, 6))
            with self.assertRaises(ValueError):
                _i5_open_registry(root, spec, 'other', forcing)
            before = (root / 'registry.json').read_bytes()
            pending = _i5_plan(registry, [16, 20], [3, 2], [], coverage)

            def fail(*args, **kwargs):
                raise RuntimeError('failed')
            with self.assertRaises(RuntimeError):
                _i5_prepare(root, registry, pending, [], spec, compose=compose, form=fail, render=render)
            self.assertEqual((root / 'registry.json').read_bytes(), before)
            metadata_path = root / 'versions' / second['version'] / 'metadata.json'
            metadata = _i5_json.loads(metadata_path.read_text(encoding='utf-8'))
            metadata['world_identity'] = 'wrong'
            metadata_path.write_text(_i5_json.dumps(metadata), encoding='utf-8')
            with self.assertRaises(ValueError):
                _i5_read_component(root, second, registry['world_identity'])

# Source: tests.test_world_terrain_disk_store
class DiskStoreTests(_i6_unittest.TestCase):

    def test_real_solver_expansion_order_matches(self):
        from terrain_pipeline.drainage import solve_disk_region as solve_disk_region
        with _i6_tempfile.TemporaryDirectory() as directory:
            spec = _i6_make_spec('lakes')
            forcing = {'runoff_m_per_year': 0.5, 'duration_seconds': 86400.0, 'channel_threshold_m3_s': 1e-05, 'min_lake_area_m2': 10000.0}

            def compose(spec, pages, origin, shape, **kwargs):
                z, x = _i6_np.indices(shape)
                bed = 100.0 + (x + origin[0]) * 0.1 + (z + origin[1]) * 0.02
                return {'composed_elevation_m': bed, 'ocean_mask': None, 'metadata': {}}
            results = []
            for index, origins in enumerate((([100, 100], [112, 100]), ([112, 100], [100, 100]))):
                root = _i6_Path(directory) / str(index)
                registry = _i6_open_registry(root, spec, 'physical', forcing, 1.0)
                for origin in origins:
                    request = _i6_plan(registry, origin, [24, 12])
                    component = _i6_prepare(root, registry, request, [], spec, compose=compose, solve=solve_disk_region)
                path, manifest = _i6_read_manifest(root, component, registry['world_identity'])
                tile = manifest['water_tiles'][0]
                with _i6_np.load(path / tile['file'], allow_pickle=False) as archive:
                    results.append({name: archive[name] for name in archive.files})
            self.assertEqual(results[0].keys(), results[1].keys())
            for name in results[0]:
                _i6_np.testing.assert_array_equal(results[0][name], results[1][name])

    def test_tiled_inputs_and_failed_solve_preserves_registry(self):
        with _i6_tempfile.TemporaryDirectory() as directory:
            root = _i6_Path(directory)
            spec = _i6_make_spec('lakes')
            forcing = {'runoff_m_per_year': 1.0, 'duration_seconds': 100.0, 'channel_threshold_m3_s': 0.1}
            registry = _i6_open_registry(root, spec, 'physical', forcing, 6.0)
            request = _i6_plan(registry, [100, 100], [520, 520])
            calls = []

            def compose(spec, pages, origin, shape, **kwargs):
                calls.append((origin, shape))
                return {'composed_elevation_m': _i6_np.ones(shape), 'ocean_mask': None, 'metadata': {}}

            def solve(height, ocean, work, **kwargs):
                self.assertEqual(_i6_np.load(height, mmap_mode='r').shape, (520, 520))
                self.assertFalse(_i6_np.load(ocean, mmap_mode='r').any())
                work.mkdir()
                field = work / 'receiver_native_x.npy'
                _i6_np.save(field, _i6_np.zeros((520, 520), dtype=_i6_np.int64))
                return {'fields': {'receiver_native_x': field.name}, 'metadata': {'algorithm': 'test'}}
            component = _i6_prepare(root, registry, request, [], spec, compose=compose, solve=solve)
            self.assertEqual(len(calls), 4)
            _, manifest = _i6_read_manifest(root, component, registry['world_identity'])
            self.assertEqual(len(manifest['composition_tiles']), 4)
            for coordinate in ([611, 611], [612, 612]):
                output = _i6_io.StringIO()
                with _i6_contextlib.redirect_stdout(output):
                    _i6_query([str(root), '--native-xz', *map(str, coordinate)])
                self.assertEqual(_i6_json.loads(output.getvalue())['values']['receiver_native_x'], 0)
            hit = _i6_plan(registry, [100, 100], [1, 1])
            self.assertEqual(_i6_prepare(root, registry, hit, [], spec, compose=compose, solve=solve), component)
            before = (root / 'registry.json').read_bytes()
            extension = _i6_plan(registry, [620, 100], [2, 2])
            count = 0

            def fail_compose(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 2:
                    raise RuntimeError('second tile failed')
                return compose(*args, **kwargs)
            with self.assertRaisesRegex(RuntimeError, 'second tile failed'):
                _i6_prepare(root, registry, extension, [], spec, compose=fail_compose, solve=solve)
            self.assertEqual((root / 'registry.json').read_bytes(), before)

            def fail(*args, **kwargs):
                raise RuntimeError('solver failure')
            with self.assertRaises(RuntimeError):
                _i6_prepare(root, registry, extension, [], spec, compose=compose, solve=fail)
            self.assertEqual(before, (root / 'registry.json').read_bytes())

# Source: tests.test_world_terrain_mosaic
class MosaicTests(_i7_unittest.TestCase):

    def setUp(self):
        self.temp = _i7_tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.spec = _i7_LayoutSpec('lakes', 0.12, mode='finite', frame_origin_m=(0, 0), frame_side_m=12288000)
        self.family = 'test-conditioning'

    def page(self, name, x0, z0, *, change=None, family='test-conditioning'):
        z, x = _i7_np.indices((128, 128))
        height = (x + x0) * 0.3 + (z + z0) * 0.2 + _i7_np.sin((x + x0) / 4)
        if change is not None:
            height[change] += 100
        metadata = {'schema': 'td-native-page-v1', 'native_origin': [x0, z0], 'size': 128, 'spacing_m': 30, 'world_seed': 20261020, 'conditioning_identity': family}
        path = _i7_Path(self.temp.name) / name
        _i7_np.savez(path, elevation_native=height.astype(_i7_np.float64), metadata_json=_i7_np.array(_i7_json.dumps(metadata)))
        return {'path': str(path), 'sha256': _i7_hashlib.sha256(path.read_bytes()).hexdigest()}

    def compose(self, records, origin, shape=(20, 20)):
        return _i7_compose_window(self.spec, records, origin, shape, sigma_cells=2, source_family=self.family)

    def test_page_join_order_and_overlapping_windows(self):
        first = self.page('first.npz', 0, 0)
        second = self.page('second.npz', 65, 0)
        whole = self.compose([first, second], (100, 30), (25, 30))
        reverse = self.compose([second, first], (100, 30), (25, 30))
        overlapping = self.compose([second, first], (105, 35), (15, 20))
        _i7_np.testing.assert_array_equal(whole['composed_elevation_m'], reverse['composed_elevation_m'])
        _i7_np.testing.assert_array_equal(whole['composed_elevation_m'][5:20, 5:25], overlapping['composed_elevation_m'])
        self.assertEqual(whole['metadata']['identity'], reverse['metadata']['identity'])
        self.assertTrue(whole['valid_mask'].all())

    def test_same_as_single_fixed_source_interior(self):
        record = self.page('one.npz', 0, 0)
        with _i7_np.load(record['path'], allow_pickle=False) as saved:
            source = saved['elevation_native'].copy()
        fixed = _i7_compose_source(self.spec, source, (0, 0), source_record={**record, 'world_seed': 20261020}, sigma_cells=2)
        expected = _i7_crop_composition(fixed, (30, 30), (20, 20))
        actual = self.compose([record], (30, 30))
        _i7_np.testing.assert_array_equal(actual['td_residual_m'], expected['td_residual_m'])
        _i7_np.testing.assert_array_equal(actual['composed_elevation_m'], expected['composed_elevation_m'])

    def test_missing_and_inconsistent_support_are_rejected(self):
        first = self.page('first.npz', 0, 0)
        inspection = _i7_inspect_window_support(self.spec, [first], (110, 30), (20, 20), sigma_cells=2, source_family=self.family)
        self.assertGreater(inspection['missing_cells'], 0)
        self.assertEqual(inspection['missing_cells'], int(inspection['missing_mask'].sum()))
        empty = _i7_inspect_window_support(self.spec, [], (110, 30), (20, 20), sigma_cells=2, source_family=self.family)
        self.assertTrue(empty['missing_mask'].all())
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.compose([first], (110, 30))
        second = self.page('second.npz', 65, 0, change=(35, 40))
        with self.assertRaisesRegex(ValueError, 'overlap disagrees'):
            self.compose([first, second], (100, 30), (20, 20))

    def test_world_edge_may_use_td_support_outside_frame(self):
        first = self.page('edge.npz', -20, -20)
        result = self.compose([first], (0, 0))
        self.assertTrue(result['valid_mask'].all())
        last = 409599
        far = self.page('far-edge.npz', last - 107, last - 107)
        result = self.compose([far], (last - 19, last - 19))
        self.assertTrue(result['valid_mask'].all())

    def test_wrong_family_is_rejected(self):
        wrong = self.page('wrong.npz', 0, 0, family='other')
        with self.assertRaisesRegex(ValueError, 'source family'):
            self.compose([wrong], (30, 30))

    def test_legacy_and_declared_page_can_overlap(self):
        legacy = self.page('legacy.npz', 0, 0, family=None)
        current = self.page('current.npz', 65, 0)
        result = self.compose([legacy, current], (100, 30), (20, 20))
        self.assertEqual(result['metadata']['source_family_verification'], 'mixed_embedded_and_caller_declared')

    def test_support_inspection_rejects_outside_world(self):
        with self.assertRaisesRegex(ValueError, 'outside finite world'):
            _i7_inspect_window_support(self.spec, [], (-1, 0), (20, 20), sigma_cells=2, source_family=self.family)

# Source: tests.test_world_terrain_composition
class WorldTerrainCompositionTests(_i8_unittest.TestCase):

    def setUp(self):
        self.spec = _i8_LayoutSpec('lakes', 0.12, mode='finite', frame_origin_m=(0, 0), frame_side_m=12288000)
        z, x = _i8_np.indices((80, 90), dtype=_i8_np.float64)
        self.source = x * 0.5 + z * 0.3 + 12 * _i8_np.sin(x / 3)
        self.record = {'sha256': 'a' * 64, 'world_seed': 20261020}

    def test_crops_share_fixed_source_residual_and_preserve_td(self):
        original = self.source.copy()
        product = _i8_compose_source(self.spec, self.source, (2000, 3000), source_record=self.record, sigma_cells=3)
        first = _i8_crop_composition(product, (2015, 3014), (30, 35))
        second = _i8_crop_composition(product, (2020, 3018), (20, 25))
        _i8_np.testing.assert_array_equal(first['composed_elevation_m'][4:24, 5:30], second['composed_elevation_m'])
        _i8_np.testing.assert_array_equal(product['td_elevation_m'], original)
        _i8_np.testing.assert_array_equal(self.source, original)
        self.assertIsNone(product['ocean_mask'])
        self.assertIsNone(product['metadata']['sea_level_m'])
        self.assertEqual(product['metadata']['lake_status'], 'not_modelled')
        with self.assertRaises(ValueError):
            _i8_crop_composition(product, (2000, 3000), (10, 10))

    def test_seed_and_lake_mask_are_rejected(self):
        with self.assertRaises(ValueError):
            _i8_compose_source(self.spec, self.source, (0, 0), source_record={**self.record, 'world_seed': 1})
        with self.assertRaises(ValueError):
            _i8_compose_source(self.spec, self.source, (0, 0), source_record=self.record, ocean_mask=_i8_np.zeros(self.source.shape, dtype=bool))

    def test_ocean_mask_is_explicit_and_sea_side_stays_below_datum(self):
        spec = _i8_LayoutSpec('archipelago', 0.8, mode='finite', frame_origin_m=(0, 0), frame_side_m=12288000)
        z, x = _i8_np.indices(self.source.shape)
        x = (x + 2000) * 30.0
        z = (z + 3000) * 30.0
        mask = _i8_layout_field(spec, x, z) < 0
        product = _i8_compose_source(spec, self.source, (2000, 3000), source_record=self.record, ocean_mask=mask, sigma_cells=3)
        self.assertTrue(_i8_np.all(product['composed_elevation_m'][mask] <= 0))
        with self.assertRaises(ValueError):
            _i8_compose_source(spec, self.source, (2000, 3000), source_record=self.record)
        self.assertEqual(product['metadata']['ocean_classification'], 'externally_supplied')

    def test_source_content_and_mask_are_part_of_identity(self):
        first = _i8_compose_source(self.spec, self.source, (0, 0), source_record=self.record)
        changed = self.source.copy()
        changed[40, 40] += 1
        second = _i8_compose_source(self.spec, changed, (0, 0), source_record=self.record)
        self.assertNotEqual(first['metadata']['identity'], second['metadata']['identity'])

# Source: tests.test_world_terrain_composition
class OceanPlanTests(_i8_unittest.TestCase):

    def test_off_grid_shore_uses_exact_field_not_coarse_cell_edge(self):
        spec = _i8_LayoutSpec('earth', 0.62, mode='finite', frame_origin_m=(0, 0), frame_side_m=800000)

        def field(_spec, x, z):
            x, z = _i8_np.broadcast_arrays(x, z)
            return x - 150000.0
        with _i8_patch('terrain_pipeline.td_source.layout_field', side_effect=field):
            plan = _i8_make_ocean_plan(spec, pixels=8)
            result = _i8_sample_ocean_mask(plan, spec, _i8_np.array([99999.0, 100001.0, 125000.0, 149999.0, 150001.0]), _i8_np.full(5, 350000.0))
        _i8_np.testing.assert_array_equal(result, [True, True, True, True, False])
        self.assertIn('nearest classified water', plan['metadata']['ownership'])

    def test_global_components_and_crop_consistency(self):
        spec = _i8_LayoutSpec('earth', 0.62, mode='finite', frame_origin_m=(0, 0), frame_side_m=800000)

        def field(_spec, x, z):
            x, z = _i8_np.broadcast_arrays(x, z)
            large = (x < 300000) & (z < 500000)
            small = (x >= 600000) & (z >= 600000)
            return _i8_np.where(large | small, -1.0, 1.0)
        with _i8_patch('terrain_pipeline.td_source.layout_field', side_effect=field):
            plan = _i8_make_ocean_plan(spec, pixels=8, min_ocean_area_fraction=0.1)
            x, z = _i8_np.meshgrid((_i8_np.arange(8) + 0.5) * 100000, (_i8_np.arange(8) + 0.5) * 100000)
            whole = _i8_sample_ocean_mask(plan, spec, x, z)
            part = _i8_sample_ocean_mask(plan, spec, x[3:, 2:], z[3:, 2:])
        _i8_np.testing.assert_array_equal(whole[3:, 2:], part)
        self.assertTrue(whole[0, 0])
        self.assertFalse(whole[7, 7])
        self.assertEqual(plan['metadata']['water_components'], 2)
        self.assertEqual(plan['metadata']['ocean_components'], 1)

    def test_lakes_reject_ocean_plan(self):
        spec = _i8_LayoutSpec('lakes', 0.12, mode='finite', frame_origin_m=(0, 0), frame_side_m=12288000)
        with self.assertRaises(ValueError):
            _i8_make_ocean_plan(spec)
