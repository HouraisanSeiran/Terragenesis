import unittest
import numpy as np

from terrain_pipeline.runoff import run_catchment_event as run_catchment_event
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters


def run(r=None, mask=None, rain=None):
    h = np.array([[4., 3., 2., 1.]], dtype=np.float64)
    if r is None:
        r = np.array([[1, 2, 3, -1]], dtype=np.int64)
    if mask is None:
        mask = np.array([[True, True, True, True]], dtype=bool)
    if rain is None:
        rain = np.array([8., 0., 0.], dtype=np.float64)
    out = run_catchment_event(
        h, r, mask, mask,
        origin_native_xz=(0, 0),
        source_identity_sha256='0' * 64,
        world_seed=20261020,
        rain_mm_h=rain,
        dt_s=3600.,
        runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.),
    )
    return out, h, r, mask


class TestNative30mRunoff(unittest.TestCase):

    def test_design_terminal_q_and_not_bankfull(self):
        out, _, _, _ = run()
        q = out['routed_terminal_q_m3_s']
        design = out['design_q_m3_s']
        self.assertGreater(design, 0.0)
        self.assertEqual(design, np.max(q))
        self.assertTrue(out['event_design_q_not_bankfull'])

    def test_instantaneous_equals_local_sum(self):
        out, _, _, _ = run()
        inst = out['routed_terminal_q_m3_s'] - out['routed_terminal_q_m3_s'] + out[
            'instantaneous_terminal_q_m3_s'] if False else out[
            'instantaneous_terminal_q_m3_s']
        local = out['local_q_m3_s']
        np.testing.assert_allclose(inst, local.sum(axis=1),
                                   rtol=1e-12, atol=1e-12)

    def test_long_rain_finite_and_rising(self):
        rain = np.r_[8., np.zeros(71)]
        out, _, _, _ = run(rain=rain)
        inst = out['instantaneous_terminal_q_m3_s']
        routed = out['routed_terminal_q_m3_s']
        self.assertEqual(inst.shape, (72,))
        self.assertEqual(routed.shape, (72,))
        self.assertTrue(np.all(np.isfinite(inst)))
        self.assertTrue(np.all(np.isfinite(routed)))
        self.assertTrue(np.any(inst[1:] < routed[1:]))

    def test_self_loop_rejected(self):
        r = np.array([[0, 2, 3, -1]], dtype=np.int64)
        with self.assertRaises(ValueError):
            run(r=r)

    def test_source_outside_catchment_rejected(self):
        mask = np.array([[True, False, False, False]], dtype=bool)
        with self.assertRaises(ValueError):
            run(mask=mask)

    def test_determinism_and_inputs_unchanged(self):
        h0 = np.array([[4., 3., 2., 1.]], dtype=np.float64)
        r0 = np.array([[1, 2, 3, -1]], dtype=np.int64)
        m0 = np.array([[True, True, True, True]], dtype=bool)
        out1, h1, r1, m1 = run()
        out2, h2, r2, m2 = run()
        np.testing.assert_array_equal(out1['instantaneous_terminal_q_m3_s'],
                                      out2['instantaneous_terminal_q_m3_s'])
        np.testing.assert_array_equal(out1['routed_terminal_q_m3_s'],
                                      out2['routed_terminal_q_m3_s'])
        self.assertEqual(out1['design_q_m3_s'],
                         out2['design_q_m3_s'])
        np.testing.assert_array_equal(h1, h0)
        np.testing.assert_array_equal(r1, r0)
        np.testing.assert_array_equal(m1, m0)
        np.testing.assert_array_equal(h2, h0)
        np.testing.assert_array_equal(r2, r0)
        np.testing.assert_array_equal(m2, m0)


if __name__ == '__main__':
    unittest.main()
