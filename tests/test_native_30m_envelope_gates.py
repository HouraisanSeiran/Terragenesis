"""Small envelope archives for re-sealed capability and header attacks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from terrain_pipeline.artifacts.contracts import digest
from terrain_pipeline.common_infra import file_sha256
from tools import native_30m_bundle_reader as reader
from tools.native_30m_sources import compute_source_request


class EnvelopeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'discharge-diagnostic').mkdir()
        names = (set(reader._NAMES) | {'discharge-diagnostic/manifest.json', 'discharge-diagnostic/arrays.npz'}) - {'bundle.json'}
        for name in names:
            path = self.root/name
            if name.endswith('.npz'):
                with path.open('wb') as stream:
                    np.savez(stream, harmless=np.array([1], np.int64))
            else:
                path.write_text('{}', encoding='utf-8')
        params = compute_source_request([{'path': 'x.npz', 'sha256': 'a'*64}],
                    {'shape_zx': [9, 9], 'coupled_intervals': 1})['parameters']
        self.body = {'schema': 'native-30m-river-bundle-v1', 'parameters': params, 'source_records': [],
            'stage_identities': dict.fromkeys(('source_assembly', 'event', 'geometry', 'dynamics', 'diagnostic'), 'a'*64),
            'files': {name: file_sha256(self.root/name) for name in names},
            'capabilities': {'hydraulic_ready': False, 'natural_outlet_certified': False,
                             'publishable': False, 'finite_graph_only': True}}
        self.seal()

    def seal(self):
        record = dict(self.body, identity_sha256=digest(self.body), checks={}, runtime={})
        (self.root/'bundle.json').write_text(json.dumps(record), encoding='utf-8')

    def test_positive_envelope_only_not_full_numerical_bundle(self):
        # This fixture is valid only for the envelope gate; stage data is deliberately tiny.
        self.assertEqual(len(reader.load_candidate_envelope(self.root)['arrays']), 6)

    def test_resealed_certification_upgrade_refused(self):
        original = copy.deepcopy(self.body)
        for key, value in (('hydraulic_ready', True), ('natural_outlet_certified', True),
                           ('publishable', True), ('finite_graph_only', False), ('publishable', 0)):
            with self.subTest(key=key, value=value):
                self.body = copy.deepcopy(original)
                self.body['capabilities'][key] = value
                self.seal()
                with self.assertRaisesRegex(ValueError, 'cap|finite_graph_only'):
                    reader.load_candidate_envelope(self.root)

    def test_unknown_true_capability_cannot_be_smuggled(self):
        self.body['capabilities']['infinite_world'] = True
        self.seal()
        with self.assertRaisesRegex(ValueError, 'whitelist'):
            reader.load_candidate_envelope(self.root)

    def test_resealed_object_and_structured_headers_refused(self):
        for value in (np.array([{'not': 'loaded'}], dtype=object), np.array([(1,)], dtype=[('x', 'i4')])):
            with self.subTest(dtype=str(value.dtype)):
                with (self.root/'source.npz').open('wb') as stream:
                    np.savez(stream, unsafe=value)
                self.body['files']['source.npz'] = file_sha256(self.root/'source.npz')
                self.seal()
                with self.assertRaises(ValueError):
                    reader.load_candidate_envelope(self.root)

    def test_resealed_path_escape_refused(self):
        self.body['files']['../outside.npz'] = self.body['files'].pop('source.npz')
        self.seal()
        with self.assertRaisesRegex(ValueError, 'files keys'):
            reader.load_candidate_envelope(self.root)


if __name__ == '__main__':
    unittest.main()
