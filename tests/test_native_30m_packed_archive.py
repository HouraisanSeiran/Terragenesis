import unittest
import numpy as np

from tools.audit_native_30m_bundle import unpack_pin
from terrain_pipeline.common_infra import identity


def make_fixture(raw=None):
    if raw is None:
        raw = np.array([1.0, 2.0], dtype=np.float64)
    padded = np.pad(np.frombuffer(raw.tobytes(), dtype=np.uint8), (0, 4)).reshape(2, 10)
    arrays = {'water_0__payload': padded}
    pin = {'metadata': {'schema': 'unit-test'},
           'identity_sha256': identity({'x': raw}, {'schema': 'unit-test'}),
           'payload_bytes': 16,
           'layout': [{'name': 'x', 'dtype': '<f8', 'shape': [2], 'start': 0, 'stop': 16}]}
    return raw, arrays, {'water_0': pin}, pin


class TestNative30mPackedArchive(unittest.TestCase):
    def test_positive_zero_padding_accepted(self):
        raw, arrays, metadata, pin = make_fixture()
        out, pin_meta = unpack_pin(arrays, metadata, 'water_0')
        np.testing.assert_array_equal(out['x'], raw)
        self.assertEqual(out['x'].dtype, np.float64)
        self.assertEqual(pin_meta, pin['metadata'])

    def test_bad_payload_bytes_too_large(self):
        raw, arrays, metadata, pin = make_fixture()
        pin['payload_bytes'] = 21
        with self.assertRaises((ValueError, TypeError)):
            unpack_pin(arrays, metadata, 'water_0')

    def test_bad_dtype_object(self):
        raw, arrays, metadata, pin = make_fixture()
        pin['layout'][0]['dtype'] = 'O'
        with self.assertRaises((ValueError, TypeError)):
            unpack_pin(arrays, metadata, 'water_0')

    def test_bad_stop_out_of_range(self):
        raw, arrays, metadata, pin = make_fixture()
        pin['layout'][0]['stop'] = 17
        with self.assertRaises((ValueError, TypeError)):
            unpack_pin(arrays, metadata, 'water_0')

    def test_bad_start_gap(self):
        raw, arrays, metadata, pin = make_fixture()
        pin['layout'][0]['start'] = 1
        with self.assertRaises((ValueError, TypeError)):
            unpack_pin(arrays, metadata, 'water_0')

    def test_bad_duplicate_layout_field(self):
        raw, arrays, metadata, pin = make_fixture()
        pin['layout'].append(dict(pin['layout'][0]))
        with self.assertRaises((ValueError, TypeError)):
            unpack_pin(arrays, metadata, 'water_0')

    def test_bad_identity_all_zero(self):
        raw, arrays, metadata, pin = make_fixture()
        pin['identity_sha256'] = '0' * 64
        with self.assertRaises((ValueError, TypeError)):
            unpack_pin(arrays, metadata, 'water_0')

    def test_bad_nonfinite_raw(self):
        raw, arrays, metadata, pin = make_fixture(np.array([np.nan, 2.0], dtype=np.float64))
        with self.assertRaises((ValueError, TypeError)):
            unpack_pin(arrays, metadata, 'water_0')


if __name__ == '__main__':
    unittest.main()
