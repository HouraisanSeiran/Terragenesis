"""Independent rectangular Manning checks and discriminating saved-bed control."""
import copy
import unittest
import numpy as np

from tools.native_30m_hydraulic_reference import manning_trace_reference
from tools.audit_native_30m_bundle import recheck_hydraulic_trace


def hydraulic_fixture():
    arrays = {'node_bed_m': np.array([[2., 1.], [2.1, 1.], [2.1, 1.]]),
              'time_seconds': np.array([0., 10., 20.])}
    water = {'network_receiver': np.array([1, -1], np.int64),
             'network_receiver_distance_m': np.array([1., 0.]),
             'network_bed_elevation_m': arrays['node_bed_m'][1].copy(),
             'network_bed_slope': np.array([1.1, 1.]), 'network_length_m': np.ones(2),
             'network_width_m': np.ones(2), 'network_roughness': np.ones(2),
             'trace_volume_m3': np.ones((2, 2))}
    ref = manning_trace_reference(water['trace_volume_m3'], np.ones(2), np.ones(2), np.ones(2),
                                  water['network_bed_slope'], water['network_bed_elevation_m'])
    for field, saved in (('area_m2', 'trace_area_m2'), ('depth_m', 'trace_depth_m'),
                         ('stage_m', 'trace_stage_m'), ('outflow_q_m3_s', 'trace_outflow_end_q_m3_s')):
        water[saved] = ref[field].copy()
    return arrays, water


class ReferenceTests(unittest.TestCase):
    def test_analytic_rectangle_and_dry_cell(self):
        volume = np.array([[1., 0.]])
        result = manning_trace_reference(volume, np.ones(2), np.ones(2), np.ones(2),
                                         np.ones(2), np.array([2., -1.]))
        self.assertAlmostEqual(result['outflow_q_m3_s'][0, 0], 3. ** (-2./3.), places=14)
        self.assertEqual(result['outflow_q_m3_s'][0, 1], 0.)
        np.testing.assert_array_equal(result['stage_m'], [[3., -1.]])
        np.testing.assert_array_equal(volume, [[1., 0.]])

    def test_invalid_shapes_and_physical_values(self):
        base = [np.ones((2, 2))] + [np.ones(2) for _ in range(5)]
        for index, bad in ((0, -np.ones((2, 2))), (1, np.zeros(2)), (2, np.ones((2, 1))),
                           (3, np.array([np.nan, 1.])), (4, np.zeros(2))):
            with self.subTest(index=index):
                values = copy.deepcopy(base)
                values[index] = bad
                with self.assertRaises(ValueError):
                    manning_trace_reference(*values)

    def test_updated_bed_has_discriminating_initial_control(self):
        arrays, water = hydraulic_fixture()
        report = recheck_hydraulic_trace(arrays, 1, water)
        self.assertIs(report['initial_bed_control_discriminating'], True)
        self.assertGreater(report['initial_bed_control_max_q_difference_m3_s'], .01)
        self.assertLess(report['residuals']['outflow_q_m3_s']['max_error_over_tolerance'], 1.)

    def test_uniform_bed_shift_does_not_fake_q_control(self):
        arrays, water = hydraulic_fixture()
        arrays['node_bed_m'][0] = arrays['node_bed_m'][1] - 1.
        report = recheck_hydraulic_trace(arrays, 1, water)
        self.assertIs(report['bed_differs_from_initial'], True)
        self.assertIs(report['initial_bed_control_discriminating'], False)

    def test_no_change_is_not_falsely_discriminating(self):
        arrays, water = hydraulic_fixture()
        arrays['node_bed_m'][0] = arrays['node_bed_m'][1]
        self.assertIs(recheck_hydraulic_trace(arrays, 1, water)['initial_bed_control_discriminating'], False)

    def test_corrupted_saved_hydraulics_refused(self):
        for key in ('trace_area_m2', 'trace_depth_m', 'trace_stage_m', 'trace_outflow_end_q_m3_s'):
            with self.subTest(key=key):
                arrays, water = hydraulic_fixture()
                water[key][0, 0] += .1
                with self.assertRaisesRegex(ValueError, 'independent Manning mismatch'):
                    recheck_hydraulic_trace(arrays, 1, water)

    def test_wrong_updated_bed_slope_refused(self):
        arrays, water = hydraulic_fixture()
        water['network_bed_slope'][0] = 1.
        with self.assertRaisesRegex(ValueError, 'slope binding'):
            recheck_hydraulic_trace(arrays, 1, water)


if __name__ == '__main__':
    unittest.main()
