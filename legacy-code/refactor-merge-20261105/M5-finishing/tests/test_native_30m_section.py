import unittest
import numpy as np
from terrain_pipeline.channel_geometry import build_section


def make(q=1., params=None):
    h = np.array([[4., 3., 2., 1.]], np.float64)
    selection = {'chosen': {'stem_flat_cells': np.array([0, 1, 2, 3], np.int64)}}
    return build_section(
        h, selection, q,
        origin_native_xz=(-3, 7),
        section_parameters={} if params is None else params,
    )


class TestNative30mSection(unittest.TestCase):
    def test_default_section(self):
        out = make()
        a = out['arrays']
        np.testing.assert_array_equal(a['node_xz_m'], [[-90., 210.], [0., 210.]])
        self.assertTrue(np.all(a['width_m'] > 0))
        self.assertTrue(np.all(a['normal_depth_m'] > 0))
        W = a['width_m']
        d = a['normal_depth_m']
        R = W * d / (W + 2.0 * d)
        src = a['source_slope_per_m']
        Q = W * d * R ** (2.0 / 3.0) * np.sqrt(src) / 0.035
        np.testing.assert_allclose(a['design_q_m3_s'], Q, rtol=1e-8)
        m = out['metadata']
        self.assertEqual(m['full_stem_length_m'], 90)
        self.assertEqual(m['sampled_stem_length_m'], 90)
        self.assertTrue(m['normal_depth_not_bankfull'])

    def test_invalid_q(self):
        with self.assertRaises((TypeError, ValueError)):
            make(q=True)
        with self.assertRaises((TypeError, ValueError)):
            make(q='1')

    def test_depth_budget_exceeded(self):
        with self.assertRaises(ValueError) as ctx:
            make(params={'max_depth_m': 1e-12})
        self.assertIn('depth_budget_exceeded', str(ctx.exception))

    def test_resample_stride(self):
        out = make(params={'resample_stride': 1})
        a = out['arrays']
        self.assertEqual(len(a['node_xz_m']), 4)
        self.assertEqual(out['metadata']['actual_stride'], 1)
        h = np.array([[4., 3., 2., 1.]], np.float64)
        h_before = h.copy()
        selection = {'chosen': {'stem_flat_cells': np.array([0, 1, 2, 3], np.int64)}}
        build_section(h, selection, 1., origin_native_xz=(-3, 7),
                      section_parameters={'resample_stride': 1})
        np.testing.assert_array_equal(h, h_before)


if __name__ == '__main__':
    unittest.main()
