import copy
import unittest

import numpy as np

from terrain_pipeline.surface_hydraulics import prepare_surface_geometry
from terrain_pipeline.td_entry_shallow_water import finish
from terrain_pipeline.td_entry_pulse_propagation import (
    ORDINARY_Q_M3_S, build_dry_drain_geometry, build_pulse_forcing,
    propagation_diagnostics, run_pulse_level, validate_experiment)


def fixture():
    bed = np.zeros((3, 8), np.float64)
    mask = np.zeros(bed.shape, bool)
    mask[1, 0] = True
    distance = np.broadcast_to(np.arange(8)*.175, bed.shape).copy()
    carrier = finish(dict(derived_bed_m=bed, forcing_mask=mask, overlay_mask=mask.copy(),
                          wet_protected_mask=np.zeros_like(mask), longitudinal_from_upstream_m=distance,
                          centerline_offset_m=np.broadcast_to(abs(np.arange(3)-1)[:, None]*.175, bed.shape).copy()),
                     dict(injection_node_id='cell:61625', ordinary_q_m3_s=ORDINARY_Q_M3_S))
    geometry = prepare_surface_geometry(bed, spacing_m=.175, origin_m_xz=[0., 0.], source_identity=carrier['identity_sha256'])
    geometry['arrays']['boundary_kind'][3:6] = 2
    geometry['metadata']['bed_identity_sha256'] = carrier['identity_sha256']
    return carrier, finish(geometry['arrays'], geometry['metadata'])


class EntryPulseTests(unittest.TestCase):
    def test_only_boundary_kind_changes_and_exact_dry_Q_schedule(self):
        carrier, parent = fixture()
        geometry = build_dry_drain_geometry(carrier, parent)
        for key in parent['arrays']:
            expected = np.where(parent['arrays'][key] == 2, 1, parent['arrays'][key]) if key == 'boundary_kind' else parent['arrays'][key]
            np.testing.assert_array_equal(geometry['arrays'][key], expected)
        forcing = build_pulse_forcing(carrier, geometry)
        validate_experiment(carrier, geometry, forcing)
        np.testing.assert_allclose(forcing['arrays']['forcing_m3_s'][0, :12].sum(axis=1), ORDINARY_Q_M3_S)
        self.assertEqual(float(forcing['arrays']['forcing_m3_s'][0, 12:].sum()), 0.)
        self.assertEqual(float(forcing['arrays']['initial_depth_m'].sum()), 0.)
        changed = copy.deepcopy(carrier)
        changed['metadata']['injection_node_id'] = 'cell:61624'
        with self.assertRaisesRegex(ValueError, 'binding'):
            build_pulse_forcing(changed, geometry)
        changed_parent = copy.deepcopy(parent)
        changed_parent['arrays']['boundary_crest_m'][0] = .1
        with self.assertRaisesRegex(ValueError, 'crest'):
            build_dry_drain_geometry(carrier, changed_parent)

    def test_short_existing_HLL_preserves_zero_boundary_input_gate(self):
        carrier, parent = fixture()
        geometry = build_dry_drain_geometry(carrier, parent)
        forcing = build_pulse_forcing(carrier, geometry, duration_s=.2, pulse_s=.1, interval_s=.1)
        state, intervals, first_rk = run_pulse_level(carrier, geometry, forcing, max_dt_s=.01, work_limit=1000000)
        self.assertEqual(state['metadata']['status'], 'completed')
        self.assertEqual(state['metadata']['boundary_input_m3'], 0.)
        self.assertEqual(len(intervals['arrays']['interval']), 2)
        self.assertEqual(len(first_rk['arrays']['interval']), 2)
        self.assertLess(abs(state['arrays']['ledger'][-1, -1]), 1e-12)
        self.assertTrue(propagation_diagnostics(carrier, geometry, state, intervals)['source_isolation_diagnostic_passed'])
        altered = copy.deepcopy(state)
        altered['metadata']['boundary_input_m3'] = 1e-20
        self.assertFalse(propagation_diagnostics(carrier, geometry, altered, intervals)['source_isolation_diagnostic_passed'])
        self.assertFalse(propagation_diagnostics(carrier, geometry, altered, intervals)['upstream_pulse_to_lake_verified'])


if __name__ == '__main__':
    unittest.main()
