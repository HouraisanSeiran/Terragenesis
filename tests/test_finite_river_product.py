"""Synthetic contracts for the finite-sample product reader, query and explicit recovery."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.surface_rivers import finite_river_product as product_module
from terrain_pipeline.surface_rivers.finite_river_product import (
    META_KEYS, PRODUCT_SCHEMA, load_product, write_product,
)
from tools import publish_domain_bundle as publisher

INTERVALS = 4
DT_S = 900.0
ROUTED = 10.0


def synthetic_arrays(intervals=INTERVALS):
    rows, columns = 1, 5
    edges = np.arange(intervals + 1) * DT_S
    local = np.zeros((intervals, 5), np.float64)
    routed = np.zeros((intervals, 5), np.float64)
    delivered = np.zeros(intervals, np.float64)
    lake_volume = np.zeros(intervals + 1, np.float64)
    lake_level = np.zeros(intervals + 1, np.float64)
    lake_wet = np.zeros(intervals + 1, np.int64)
    et = np.zeros((intervals, 3), np.float64)
    release = np.zeros((intervals, 3), np.float64)
    soil = np.zeros((intervals + 1, 3, 3), np.float64)
    lake_level[0] = 0.4
    for index in range(intervals):
        local[index] = 1.0 + index
        routed[index] = 10.0 * (np.arange(5) + 1) + index
        delivered[index] = 5.0 + index
        lake_volume[index + 1] = lake_volume[index] + delivered[index]
        lake_level[index + 1] = 0.4 + 0.01 * (index + 1)
        lake_wet[index + 1] = 1 if index >= 1 else 0
        et[index] = 0.1
        release[index] = 0.2
        soil[index + 1] = soil[index] + 0.3
    return {'seconds_edges': edges, 'rain_mm_h': np.linspace(2.0, 0.0, intervals),
            'local_q_m3_s': local, 'routed_q_m3_s': routed,
            'delivered_to_lake_m3': delivered, 'lake_volume_m3': lake_volume,
            'lake_level_m': lake_level, 'lake_wet_cells': lake_wet,
            'et_mm_land': et, 'release_mm_land': release, 'soil_states_mm': soil,
            'active_index': np.array([0, 1, 2, 3, 4], np.int64),
            'land_index': np.array([0, 1, 2], np.int64),
            'lake_bed_index': np.array([3, 4], np.int64),
            'head_path_index': np.array([0, 1, 2, 3, 4], np.int64),
            'elevation_m': np.array([[3.0, 2.0, 1.0, 0.6, 0.4]], np.float64),
            'resolved_mask': np.ones((1, 5), bool),
            'receiver': np.array([[1, 2, 3, 4, -1]], np.int64),
            'terminal_kind_code': np.array([[1, 1, 1, 1, 2]], np.int8),
            'member_mask': np.array([[False, False, False, True, True]]),
            'reach_mask': np.ones((1, 5), bool),
            'block_of': np.zeros(5, np.int64)}


def synthetic_meta(intervals=INTERVALS):
    edges = np.arange(intervals + 1) * DT_S
    return {
        'schema': PRODUCT_SCHEMA,
        'created_at': '2026-10-28T00:00:00',
        'role': 'finite_sample_default_consumption',
        'capabilities': {'finite_sample_complete': True, 'world_complete': False,
                         'hydraulic_ready': False, 'natural_outlet_verified': False,
                         'publishable': False},
        'source_code_identity': {'terrain_pipeline/x.py': 'a' * 64},
        'test_evidence': {'tests/test_x.py': 'b' * 64},
        'provenance': {'prepared_by': 'test'},
        'domain': {'origin_native_xz': [0, 0], 'origin_m_xz': [0.0, 0.0], 'spacing_m': 30.0,
                   'cell_area_m2': 900.0, 'grid_shape_zx': [1, 5], 'active_cells': 5,
                   'land_cells': 3, 'lake_bed_cells': 2, 'terminal_cell_flat': 4,
                   'head_path_cells': 5, 'safe_level_m': 0.85, 'safe_capacity_m3': 630.0,
                   'world_convention': 'cell reference point'},
        'time': {'dt_s': DT_S, 'intervals': intervals, 'start_s': 0.0,
                 'end_s': float(edges[-1]),
                 'seconds_edges': [float(value) for value in edges],
                 'interval_semantics': 'interval i owns [edges[i], edges[i+1])'},
        'model': {'routing': 'quasi_steady_d8_no_channel_storage', 'no_channel_storage': True,
                  'channel_storage_m3': 0.0, 'dt_s': DT_S, 'intervals': intervals,
                  'parameters': {'infiltration_capacity_mm_h': 15.0, 'soil_capacity_mm': 150.0,
                                 'potential_et_mm_h': 0.15, 'percolation_mm_h': 1.0,
                                 'fast_tau_s': 3600.0, 'slow_tau_s': 259200.0,
                                 'initial_soil_mm': 0.0, 'initial_fast_mm': 0.0,
                                 'initial_slow_mm': 0.0}},
        'forcing': {'kind': 'fixed', 'rain_mm_h_by_interval': list(np.linspace(2.0, 0.0,
                                                                             intervals)),
                    'total_rain_m3': 1.0},
        'layout': {'block_count': 1, 'cuts': None, 'dispatch_order': 'forward',
                   'block_of_path': product_module.LAYOUT_FILES['block_of'],
                   'block_of_sha256': 'c' * 64},
        'checkpoints': {},
        'features': {'head_world_m': [0.0, 0.0], 'mid_world_m': [60.0, 0.0],
                     'lake_world_m': [120.0, 0.0]},
        'files': {},
        'limitations': ['synthetic'],
        'gates': {},
    }


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='finite-product-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.directory = self.root / 'product'
        write_product(self.directory, meta=synthetic_meta(), arrays=synthetic_arrays())
        self.product = load_product(self.directory)

    def test_query_semantics_edges_intervals_and_end(self):
        at_zero = self.product.query(60.0, 0.0, 0.0)
        self.assertEqual(at_zero['interval_index'], 0)
        self.assertEqual(at_zero['time']['state_edge'], 0)
        self.assertEqual(at_zero['local_q_m3_s'], 1.0)
        self.assertEqual(at_zero['routed_q_m3_s'], 30.0 + 0.0)
        self.assertEqual(at_zero['cell']['cell_flat'], 2)
        edge = self.product.query(60.0, 0.0, 1800.0)
        self.assertEqual(edge['interval_index'], 2)
        self.assertEqual(edge['time']['state_edge'], 2)
        self.assertEqual(edge['lake']['edge_index'], 2)
        interior = self.product.query(60.0, 0.0, 2000.0)
        self.assertEqual(interior['interval_index'], 2)
        self.assertEqual(interior['time']['state_edge'], 3)
        self.assertEqual(interior['time']['asof'], 'interval_end')
        end = self.product.query(60.0, 0.0, INTERVALS * DT_S)
        self.assertEqual(end['interval_index'], INTERVALS - 1)
        self.assertEqual(end['time']['state_edge'], INTERVALS)
        self.assertEqual(end['time']['asof'], 't=end')
        self.assertEqual(end['lake']['volume_m3'], float(self.product.arrays['lake_volume_m3'][-1]))
        self.assertTrue(end['safety']['lake_within_safe'])
        self.assertEqual(end['capabilities']['world_complete'], False)

    def test_query_refuses_outside_unaliend_and_out_of_time(self):
        with self.assertRaises(ValueError):  # outside the window
            self.product.query(1000.0, 0.0, 0.0)
        with self.assertRaises(ValueError):  # not a 30 m reference point
            self.product.query(60.0 + 1.0, 0.0, 0.0)
        with self.assertRaises(ValueError):  # beyond the stored event
            self.product.query(60.0, 0.0, INTERVALS * DT_S + 900.0)
        window = product_module.load_product(self.directory)
        window.arrays['active_index'] = np.array([0, 1], np.int64)
        with self.assertRaises(ValueError):  # inside the window but outside the drainage set
            window.query(120.0, 0.0, 0.0)

    def test_native_coordinates_are_explicit(self):
        native = self.product.query(4.0, 0.0, 0.0, native=True)
        world = self.product.query(120.0, 0.0, 0.0)
        self.assertEqual(native['cell']['cell_flat'], world['cell']['cell_flat'])
        self.assertEqual(native['query']['coordinate_mode'], 'native_grid')
        self.assertEqual(world['query']['coordinate_mode'], 'world_metres')
        with self.assertRaises(ValueError):  # native indices do not accept fractional cells
            self.product.query(1.5, 0.0, 0.0, native=True)

    def test_loader_rejects_tampering_missing_and_shape_drift(self):
        damaged = self.root / 'damaged'
        shutil.copytree(self.directory, damaged)
        path = damaged / product_module.EVENT_FILE
        raw = bytearray(path.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        path.write_bytes(bytes(raw))
        with self.assertRaises(ValueError):
            load_product(damaged)
        missing = self.root / 'missing'
        shutil.copytree(self.directory, missing)
        (missing / 'event' / 'active_index.npy').unlink()
        with self.assertRaises(FileNotFoundError):
            load_product(missing)
        wrong_shape = self.root / 'wrong-shape'
        shutil.copytree(self.directory, wrong_shape)
        meta = json.loads((wrong_shape / 'product.json').read_text(encoding='utf-8'))
        meta['time']['intervals'] = INTERVALS + 1
        (wrong_shape / 'product.json').write_text(json.dumps(meta), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_product(wrong_shape, verify_files=False)
        unknown_key = self.root / 'unknown-key'
        shutil.copytree(self.directory, unknown_key)
        meta = json.loads((unknown_key / 'product.json').read_text(encoding='utf-8'))
        meta['extra'] = 1
        (unknown_key / 'product.json').write_text(json.dumps(meta), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_product(unknown_key)
        self.assertEqual(set(meta) - META_KEYS, {'extra'})

    def test_write_product_never_overwrites(self):
        with self.assertRaises(FileExistsError):
            write_product(self.directory, meta=synthetic_meta(), arrays=synthetic_arrays())

    def test_query_is_read_only(self):
        before = {path: product_module.sha256_file(path)
                  for path in sorted(self.directory.rglob('*')) if path.is_file()}
        self.product.query(60.0, 0.0, 900.0)
        after = {path: product_module.sha256_file(path)
                 for path in sorted(self.directory.rglob('*')) if path.is_file()}
        self.assertEqual(before, after)


class DefaultEntryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='finite-entry-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.directory = self.root / 'product'
        write_product(self.directory, meta=synthetic_meta(), arrays=synthetic_arrays())

    def test_default_entry_consumes_the_product_without_the_legacy_chain(self):
        with patch.object(publisher, '_run_legacy_coarse',
                          side_effect=AssertionError('legacy chain must not run by default')):
            code = publisher.run(['--product-dir', str(self.directory),
                                  '--point', '60', '0', '--time-s', '900', '2000'])
        self.assertEqual(code, 0)

    def test_default_entry_reports_real_values(self):
        report_path = self.root / 'report'
        code = publisher.run(['--product-dir', str(self.directory), '--point', '60', '0',
                              '--time-s', '900', '--output-dir', str(report_path)])
        self.assertEqual(code, 0)
        report = json.loads((report_path / 'query.json').read_text(encoding='utf-8'))
        self.assertEqual(report['role'], publisher.FINITE_ROLE)
        self.assertEqual(report['query_count'], 1)
        answer = report['queries'][0]
        self.assertEqual(answer['interval_index'], 1)
        self.assertGreater(answer['routed_q_m3_s'], 0.0)
        self.assertIn('product_sha256', report)
        again = publisher.run(['--product-dir', str(self.directory), '--point', '60', '0',
                               '--time-s', '900', '--output-dir', str(report_path)])
        self.assertEqual(again, 2)

    def test_default_entry_refuses_bad_requests(self):
        cases = [['--point', '1000', '0', '--time-s', '0'],
                 ['--point', '61', '0', '--time-s', '0'],
                 ['--point', '60', '0', '--time-s', '999999'],
                 ['--point', '60', '0', '--time-s', '-5']]
        for extra in cases:
            with self.subTest(case=extra):
                code = publisher.run(['--product-dir', str(self.directory)] + extra)
                self.assertEqual(code, 2)
        code = publisher.run(['--product-dir', str(self.root / 'absent'), '--point', '60', '0',
                              '--time-s', '0'])
        self.assertEqual(code, 2)
        code = publisher.run(['--product-dir', str(self.directory), '--point', '60', '0',
                              '--time-s', '0', '--resume-checkpoint', 'k8'])
        self.assertEqual(code, 2)

    def test_legacy_chain_requires_the_explicit_switch(self):
        with patch.object(publisher, '_run_legacy_coarse', return_value=7) as legacy:
            self.assertEqual(publisher.run(['--legacy-coarse', '--point', '1', '2']), 7)
            legacy.assert_called_once_with(['--point', '1', '2'])
        with patch.object(publisher, '_run_legacy_coarse', return_value=7) as legacy:
            code = publisher.run(['--product-dir', str(self.directory), '--point', '60', '0',
                                  '--time-s', '0'])
            self.assertEqual(code, 0)
            legacy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
