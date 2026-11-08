"""Pure scoped-consumption tests on a tiny finite catchment."""
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import numpy as np

from terrain_pipeline.surface_rivers.metric_network_discharge_product import build_discharge_product
from tools.native_30m_query import ScopeRefusal, require_available, query_point, census
from tools import publish_native_30m_bundle as publisher
from tests.test_native_30m_bundle_validation import graph_fixture


def fixture():
    env = graph_fixture()
    env['manifest'].update(identity_sha256='a'*64, source_records=[{
        'native_origin_xz': [100, 200], 'shape_zx': [9, 9]}])
    a = env['arrays']
    env['json_records']['selection.json']['chosen']['subwindow_rc'] = [0, 9, 0, 9]
    a['event.npz'] = {'active_cells': np.flatnonzero(a['selection.npz']['catchment_mask']),
                      'local_q_m3_s': np.ones((2, 9)), 'time_edges_s': np.array([0., 3600., 7200.])}
    a['section.npz'].update(width_m=np.array([30., 30.]), normal_depth_m=np.array([.1, .2]),
                           source_slope_per_m=np.array([.2, .1]), design_q_m3_s=np.array([3., 3.]))
    a['reach_context.npz']['node_slope_per_m'] = np.array([.19, .09])
    env['dynamics'] = {'arrays': {
        'time_seconds': np.array([0., 3600.]),
        'water_volume_m3': np.array([[0., 0.], [3., 5.]]),
        'node_bed_m': np.array([[2., 0.], [1.99, -.01]]),
        'mobile_solid_m3': np.zeros((2, 2)), 'loose_solid_m3': np.ones((2, 2)),
        'rock_removed_m3': np.zeros((2, 2))}}
    top = a['topology.npz']
    local = a['selection.npz']['catchment_mask'].astype(np.float64)
    env['diagnostic'] = build_discharge_product(top['receiver'], local, top['valid_mask'],
        top['terminal_kind'], top['upstream_unknown_mask'], origin_native_cells=[100, 200],
        world_seed=20261020, interval_seconds=[0., 3600.], source_sha256='a'*64,
        forcing_semantics='unit test diagnostic')
    return env


def mask(*cells):
    result = np.zeros((9, 9), bool)
    result.ravel()[list(cells)] = True
    return result


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.env = fixture()

    def refuse(self, scope, requested, reason, **kwargs):
        with self.assertRaises(ScopeRefusal) as caught:
            require_available(self.env, scope, requested, **kwargs)
        self.assertEqual(caught.exception.reason_code, reason)

    def test_private_writable_copies(self):
        for scope in ('terrain_surface', 'd8_topology', 'local_runoff', 'diagnostic_discharge',
                      'design_discharge', 'channel_section', 'hydraulics', 'bed_change', 'solid_inventory'):
            with self.subTest(scope=scope):
                one = require_available(self.env, scope, mask(30, 40))
                before = one.copy()
                one[...] = -999
                np.testing.assert_array_equal(require_available(self.env, scope, mask(30, 40)), before)

    def test_mixed_request_wholly_refused(self):
        self.refuse('hydraulics', mask(30, 31), 'stage_absent')

    def test_upstream_unknown_not_zero(self):
        self.env['arrays']['topology.npz']['upstream_unknown_mask'].ravel()[30] = True
        self.refuse('d8_topology', mask(40), 'upstream_unknown')
        self.assertEqual(require_available(self.env, 'terrain_surface', mask(40)).tolist(), [0.])

    def test_retained_is_not_natural_outlet(self):
        self.refuse('d8_topology', mask(40), 'gate_refuses_retained_as_outlet', as_natural_outlet=True)

    def test_design_cannot_accept_diagnostic_semantics(self):
        self.refuse('design_discharge', mask(40), 'semantics_mismatch', semantics='instantaneous_diagnostic')

    def test_unimplemented_and_unknown_scope(self):
        for scope in ('lake', 'backwater', 'floodplain_2d', 'natural_outlet', 'infinite_world'):
            self.refuse(scope, mask(40), 'stage_not_implemented')
        self.refuse('not-a-stage', mask(40), 'stage_absent')
        self.refuse('water_ledger', mask(40), 'scope_not_spatial_use_audit')

    def test_unresolved_and_outside(self):
        self.env['arrays']['source.npz']['resolved_mask'].ravel()[30] = False
        self.refuse('terrain_surface', mask(30, 40), 'unresolved_border')
        self.refuse('terrain_surface', np.ones((10, 10), bool), 'outside_window')

    def test_no_source_coverage_is_not_border_only(self):
        self.env['arrays']['source.npz']['resolved_mask'].ravel()[30] = False
        self.env['manifest']['source_records'] = []
        self.refuse('terrain_surface', mask(30), 'out_of_tile')

    def test_native_and_world_coordinate_mapping(self):
        a = query_point(self.env, 104, 204, native=True)
        b = query_point(self.env, 104*30+1, 204*30+1)
        self.assertEqual(a['sampled_native_xz'], b['sampled_native_xz'])
        self.assertEqual(b['sampling'], 'floor_to_native_30m_node')
        with self.assertRaises(ScopeRefusal):
            query_point(self.env, 104.5, 204, native=True)
        with self.assertRaises(ScopeRefusal):
            query_point(self.env, 99, 204, native=True)

    def test_time_windows_are_explicit_and_distinct(self):
        local = query_point(self.env, 104, 204, native=True, scope='local_runoff')
        water = query_point(self.env, 104, 204, native=True, scope='hydraulics')
        design = query_point(self.env, 104, 204, native=True, scope='design_discharge')
        self.assertEqual(local['time_edges_seconds'], [0., 3600., 7200.])
        self.assertEqual(water['time_edges_seconds'], [0., 3600.])
        self.assertEqual(design['design_event_window_seconds'], [0., 7200.])
        self.assertIs(design['design_q_is_bankfull'], False)

    def test_census_is_full_window(self):
        result = census(self.env)
        self.assertEqual(result['shape_zx'], [9, 9])
        self.assertEqual(sum(result['terminal_kind'].values()), 81)
        self.assertEqual(result['catchment_cells'], 9)

    def test_point_scope_without_point_cli_refused(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
             patch.object(publisher, 'inspect_release') as inspect:
            self.assertEqual(publisher.main(['--mode', 'inspect', '--bundle', 'x', '--scope', 'hydraulics']), 2)
            inspect.assert_not_called()


def diagnostic_fixture(*, q_scale=1., origin=None, interval=None):
    env = fixture()
    env['manifest'].update(parameters={'world_seed': 20261020}, stage_identities={'source_assembly': 'a'*64})
    env['arrays']['event.npz']['time_edges_s'] = np.array([0., 3600., 7200.])
    env['json_records']['event.json'] = {'design_q_interval_index': 1,
                                       'source': {'origin_native_xz': [100, 200]}}
    top = env['arrays']['topology.npz']
    local = env['arrays']['selection.npz']['catchment_mask'].astype(np.float64) * q_scale
    dirty = np.zeros((9, 9), bool)
    dirty[[0, -1], :] = True
    dirty[:, [0, -1]] = True
    env['diagnostic'] = build_discharge_product(top['receiver'], local, np.ones((9, 9), bool),
        np.where(top['receiver'] >= 0, 'interior', 'retained'), dirty,
        origin_native_cells=origin or [100, 200], world_seed=20261020,
        interval_seconds=interval or [3600., 7200.], source_sha256='a'*64,
        forcing_semantics='declared event diagnostic at design interval')
    return env


class DiagnosticEventTests(unittest.TestCase):
    def test_valid(self):
        from tools.native_30m_bundle_validation import validate_diagnostic_binding
        validate_diagnostic_binding(diagnostic_fixture())

    def test_self_consistent_wrong_forcing_refused(self):
        from tools.native_30m_bundle_validation import validate_diagnostic_binding
        with self.assertRaisesRegex(ValueError, 'diagnostic_event_binding:local_q'):
            validate_diagnostic_binding(diagnostic_fixture(q_scale=2.))

    def test_self_consistent_wrong_origin_and_time_refused(self):
        from tools.native_30m_bundle_validation import validate_diagnostic_binding
        for kwargs in ({'origin': [101, 200]}, {'interval': [0., 3600.]}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'metadata_binding'):
                validate_diagnostic_binding(diagnostic_fixture(**kwargs))


if __name__ == '__main__':
    unittest.main()
