"""Saved assembly source gates, without full terrain simulation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from tools.native_30m_saved_source import load_saved_assembly
from tools.native_30m_sources import source_request_from_candidate, validate_request
from tools import publish_native_30m_bundle as publisher


class SavedAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root/'assembly.npz'
        self.params = {'shape_zx': [9, 9], 'origin_native_xz': [-9, 10], 'coupled_intervals': 1, 'resample_stride': 1}
        field = (np.indices((9, 9))[0]+np.indices((9, 9))[1]).astype(np.float64)
        mask = np.ones((9, 9), bool)
        self.meta = {'schema': 'native-30m-saved-assembly-v1', 'world_seed': 20261020,
                     'spacing_m': 30., 'provenance': 'pure synthetic test'}
        self.data = {'elevation_m': field, 'covered_mask': mask,
                     'receiver': build_strict_topology(field, mask, origin_native_xz=(-9, 10))['receiver'],
                     'origin_native_cells': np.array([-9, 10], np.int64)}

    def write(self, *, meta=None, omit=()):
        arrays = {k: v for k, v in self.data.items() if k not in omit}
        if 'metadata_json' not in omit:
            arrays['metadata_json'] = np.array(json.dumps(self.meta if meta is None else meta))
        with self.path.open('wb') as stream:
            np.savez(stream, **arrays)
        return {'path': str(self.path), 'sha256': file_sha256(self.path)}

    def test_valid_source_has_distinct_identity_and_kind(self):
        record = self.write()
        result = load_saved_assembly(record, self.params)
        np.testing.assert_array_equal(result['field'], self.data['elevation_m'])
        self.assertEqual(result['source_records'][0]['schema'], 'native-30m-saved-assembly-v1')
        self.assertIs(result['policy']['raw_td_page_authenticity_certified'], False)
        self.assertIs(result['policy']['routed_q_reused'], False)

    def test_q_only_or_missing_provenance_refused(self):
        for omit in (('receiver',), ('metadata_json',)):
            with self.subTest(omit=omit), self.assertRaisesRegex(ValueError, 'not_recomputable'):
                load_saved_assembly(self.write(omit=omit), self.params)

    def test_seed_spacing_origin_and_receiver_refused(self):
        for key, value in (('world_seed', 123), ('spacing_m', 10000.)):
            meta = dict(self.meta)
            meta[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_saved_assembly(self.write(meta=meta), self.params)
        self.data['origin_native_cells'][0] += 1
        with self.assertRaisesRegex(ValueError, 'origin_mismatch'):
            load_saved_assembly(self.write(), self.params)
        self.data['origin_native_cells'][0] -= 1
        self.data['receiver'][4, 4] = -1
        with self.assertRaisesRegex(ValueError, 'not_strict_native_topology'):
            load_saved_assembly(self.write(), self.params)

    def test_old_routed_q_is_not_used(self):
        record = self.write()
        original = load_saved_assembly(record, self.params)
        self.data['routed_q_m3_s'] = np.full((9, 9), 1e99)
        result = load_saved_assembly(self.write(), self.params)
        np.testing.assert_array_equal(original['field'], result['field'])
        self.assertNotEqual(original['assembly_digest'], result['assembly_digest'])
        self.assertNotIn('routed_q_m3_s', result)

    def test_file_pin_is_not_optional(self):
        record = self.write()
        record['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            load_saved_assembly(record, self.params)

    def test_shared_pipeline_used_after_source_loading(self):
        with patch('tools.native_30m_saved_source.load_saved_assembly', return_value={'test': 'source'}), \
             patch.object(publisher, '_compute_from_source', return_value={'test': 'result'}) as compute:
            self.assertEqual(publisher.compute_saved_assembly({'path': 'x'}, self.params), {'test': 'result'})
        self.assertEqual(compute.call_args.args[0], {'test': 'source'})
        self.assertEqual(compute.call_args.kwargs['shape'], [9, 9])


if __name__ == '__main__':
    unittest.main()
