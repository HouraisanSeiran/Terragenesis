import unittest
from pathlib import Path
from unittest.mock import patch
from terrain_pipeline.regional_surface_source import headers, load_source, validate_source
from terrain_pipeline.mountain_source_adapter import identity
import numpy as np

class RegionalSourceTests(unittest.TestCase):

    def test_extra_members_rejected(self):
        with self.assertRaises(ValueError):
            headers({'junk': ((100000000,), np.dtype(np.float64))})

    def test_actual_full_source_coldload_and_omission_rejected(self):
        directory = Path(__file__).resolve().parents[1] / 'verification/regional-source/run-20261001T095258008789Z'
        with patch('terrain_pipeline.regional_surface_source.build_source', side_effect=AssertionError('cold source prepare')):
            source = load_source(directory / 'source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        self.assertEqual(source['arrays']['hydrology_mask'].sum(), 65536)
        source['arrays'] = {key: value.copy() for key, value in source['arrays'].items()}
        source['arrays']['hydrology_mask'][128, 128] = False
        source['identity_sha256'] = identity(source['arrays'], source['metadata'])
        with self.assertRaisesRegex(ValueError, 'full finite'):
            validate_source(source)

    def test_receiver_and_owner_resigned_tampering_rejected(self):
        directory = Path(__file__).resolve().parents[1] / 'verification/regional-source/run-20261001T095258008789Z'
        trusted = load_source(directory / 'source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        for key in ('receiver', 'outlet_owner'):
            source = dict(trusted, arrays={name: value.copy() for name, value in trusted['arrays'].items()})
            source['arrays'][key][128, 128] = -1
            source['identity_sha256'] = identity(source['arrays'], source['metadata'])
            with self.assertRaises(ValueError):
                validate_source(source)
if __name__ == '__main__':
    unittest.main()
