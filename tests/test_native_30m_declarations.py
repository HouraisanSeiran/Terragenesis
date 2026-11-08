"""Synthetic declaration binding: no historical candidate required."""
import copy
import unittest
import numpy as np
from tools.native_30m_declarations import release_declarations
from tests.test_native_30m_bundle_validation import supply_fixture


def fixture():
    env = supply_fixture()
    ev = env['arrays']['event.npz']
    ev.update(routed_terminal_q_m3_s=np.array([1., 2.]), instantaneous_terminal_q_m3_s=np.array([3., 2.]))
    env['json_records']['event.json'].update(design_q_m3_s=2., design_q_interval_index=1,
                                             runoff_parameters={'infiltration_capacity_mm_h': 2.})
    env['manifest']['parameters']['dt_s'] = 10.
    env['arrays']['reach_context.npz']['initial_alluvium_bulk_m3'] = np.array([.04, .08])
    env['json_records']['section.json'] = {'actual_stride': 1, 'sampled_stem_length_m': 90.,
                                          'full_stem_length_m': 100., 'actual_parameters': {'manning_n': .035}}
    meta = env['dynamics']['metadata']
    meta['material'] = {'porosity': .35, 'provenance': 'declared uncalibrated'}
    for key in ('water_0', 'sediment_0'):
        meta[key]['metadata']['config'] = {'max_dt_seconds': 30.}
    return env


class DeclarationTests(unittest.TestCase):
    def test_actual_supply_units_and_event_identity(self):
        result = release_declarations(fixture())
        self.assertEqual(result['nodal_local_supply']['q_m3_s'], [[1., 2.], [2., 4.]])
        self.assertEqual(result['nodal_local_supply']['volumes_m3'], [[10., 20.], [20., 40.]])
        self.assertIs(result['design_q']['used_for_dynamic_injection'], False)
        self.assertIs(result['design_q']['is_bankfull'], False)

    def test_time_windows_and_actual_soil_defaults(self):
        env = fixture()
        result = release_declarations(env)
        self.assertIs(result['time_binding']['all_stages_share_one_window'], False)
        self.assertEqual(result['declared_defaults']['runoff'], {'infiltration_capacity_mm_h': 2.})
        self.assertEqual(result['declared_defaults']['initial_alluvium_depth_m_by_node'], [.02, .02])
        self.assertEqual(result['geometry']['normal_depth_slope_state'], 'source_bed')

    def test_certification_and_unimplemented_scopes(self):
        result = release_declarations(fixture())
        for record in result['certification'].values():
            self.assertIs(record['value'], False)
        self.assertEqual(len({record['reason'] for record in result['certification'].values()}), 3)
        for key in ('lake', 'backwater', 'floodplain_2d', 'natural_outlet', 'infinite_world'):
            self.assertEqual(result['capability_scopes'][key]['status'], 'not_implemented')
        self.assertIs(result['geometry']['dynamic_PL_mesh_updated'], False)
        self.assertIs(result['bed_change_magnitude_validated'], False)

    def test_declarations_are_bound_to_saved_supply_not_template(self):
        env = fixture()
        before = release_declarations(env)
        env['arrays']['event.npz']['local_q_m3_s'] *= 2
        self.assertNotEqual(before['nodal_local_supply'], release_declarations(env)['nodal_local_supply'])


if __name__ == '__main__':
    unittest.main()
