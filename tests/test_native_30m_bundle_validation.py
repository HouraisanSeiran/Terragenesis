"""Small synthetic cross-stage gates, independent of installed TD data."""
import copy
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from tools.native_30m_bundle_validation import validate_graph_bindings, validate_nodal_supply


def graph_fixture():
    field = np.full((9, 9), -10., np.float64)
    field[2:7, 2:7] = 10.
    rr, cc = np.indices((3, 3))
    field[3:6, 3:6] = np.abs(rr-1) + np.abs(cc-1)
    valid = np.ones(field.shape, bool)
    top = build_strict_topology(field, valid, origin_native_xz=(100, 200))
    catch = np.zeros(field.shape, bool)
    catch[3:6, 3:6] = True
    flow = np.zeros_like(catch)
    flow.ravel()[[30, 31, 40]] = True
    return {'arrays': {
        'source.npz': {'field': field, 'resolved_mask': valid, 'origin_native_xz': np.array([100, 200])},
        'topology.npz': {k: top[k] for k in ('receiver', 'valid_mask', 'terminal_kind', 'upstream_unknown_mask')},
        'selection.npz': {'catchment_mask': catch, 'flowline_mask': flow,
                          'stem_flat_cells': np.array([30, 31, 40], np.int64)},
        'section.npz': {'node_cell_ids': np.array([30, 40], np.int64)},
        'reach_context.npz': {'lateral_cell_counts': np.array([1, 8], np.int64)}},
        'manifest': {'source_records': []}, 'json_records': {
            'source.json': {'source_records': []},
            'selection.json': {'chosen': {'terminal_flat_cell': 40, 'terminal_native_xz': [104, 204],
                                          'catchment_cells': 9}}}}


def pack(arrays, metadata, name, values):
    layout = []
    chunks = []
    offset = 0
    for key, value in sorted(values.items()):
        chunk = np.ascontiguousarray(value).tobytes()
        layout.append({'name': key, 'dtype': value.dtype.str, 'shape': list(value.shape),
                       'start': offset, 'stop': offset + len(chunk)})
        chunks.append(chunk)
        offset += len(chunk)
    child_meta = {'status': 'complete'}
    metadata[name] = {'layout': layout, 'payload_bytes': offset, 'metadata': child_meta,
                      'identity_sha256': identity(values, child_meta)}
    arrays[name + '__payload'] = np.frombuffer(b''.join(chunks), np.uint8).copy().reshape(1, -1)


def supply_fixture():
    event = {'local_q_m3_s': np.array([[1., 1., 1.], [2., 2., 2.]]),
             'time_edges_s': np.array([0., 10., 20.])}
    dyn_arrays = {'material_area_m2': np.array([2., 4.])}
    metadata = {'intervals': [{'start_seconds': 0., 'end_seconds': 10.},
                              {'start_seconds': 10., 'end_seconds': 20.}]}
    for i in range(2):
        times = np.array([i*10., i*10.+4., (i+1)*10.])
        water = {'trace_time_seconds': times, 'trace_local_q_m3_s':
                 np.tile(np.array([1., 2.]) * (i+1), (2, 1))}
        pack(dyn_arrays, metadata, 'water_%d' % i, water)
        pack(dyn_arrays, metadata, 'sediment_%d' % i, {'trace_time_seconds': times.copy()})
    env = {'arrays': {'event.npz': event,
                     'section.npz': {'node_cell_ids': np.array([0, 1]), 'width_m': np.array([1., 2.])},
                     'reach_context.npz': {'lateral_cell_counts': np.array([1, 2]), 'node_length_m': np.array([2., 2.])}},
           'dynamics': {'arrays': dyn_arrays, 'metadata': metadata},
           'manifest': {'parameters': {'coupled_intervals': 2}},
           'json_records': {'event.json': {'event_identity': 'a'*64},
                            'reach_context.json': {'reach_metadata': {
                                'forcing_event_identity_sha256': 'a'*64,
                                'forcing_time_edges_s': [0., 10., 20.],
                                'simulation_time_edges_s': [0., 10., 20.]}}}}
    return env


class GraphBindingsTests(unittest.TestCase):
    def test_wrong_declared_origin_cannot_reuse_saved_topology(self):
        env = graph_fixture()
        env['arrays']['source.npz']['origin_native_xz'] = np.array([0, 0], np.int64)
        with self.assertRaisesRegex(ValueError, 'topology_recompute_mismatch'):
            validate_graph_bindings(env)

    def test_valid_graph_and_full_catchment(self):
        result = validate_graph_bindings(graph_fixture())
        self.assertEqual(result['catchment_cells'], 9)

    def test_resealed_wrong_receiver(self):
        env = graph_fixture()
        env['arrays']['topology.npz']['receiver'].ravel()[30] = -1
        with self.assertRaisesRegex(ValueError, 'topology_recompute_mismatch'):
            validate_graph_bindings(env)

    def test_counts_redistributed_but_sum_preserved(self):
        env = graph_fixture()
        env['arrays']['reach_context.npz']['lateral_cell_counts'] = np.array([2, 7])
        with self.assertRaisesRegex(ValueError, 'lateral_topology_binding'):
            validate_graph_bindings(env)

    def test_catchment_hole_not_hidden_by_count(self):
        env = graph_fixture()
        env['arrays']['selection.npz']['catchment_mask'][3, 5] = False
        with self.assertRaises(ValueError):
            validate_graph_bindings(env)

    def test_unknown_seed_cannot_be_removed(self):
        env = graph_fixture()
        env['arrays']['topology.npz']['upstream_unknown_mask'][0, 0] = False
        with self.assertRaisesRegex(ValueError, 'topology_recompute_mismatch'):
            validate_graph_bindings(env)


class NodalSupplyTests(unittest.TestCase):
    def test_valid_substeps(self):
        result = validate_nodal_supply(supply_fixture())
        self.assertEqual(result['per_interval_input_m3'], [30., 60.])
        self.assertIs(result['routed_terminal_used_for_dynamic_injection'], False)

    def test_resealed_equal_total_wrong_node_forcing(self):
        env = supply_fixture()
        meta, arrays = env['dynamics']['metadata'], env['dynamics']['arrays']
        pack(arrays, meta, 'water_0', {'trace_time_seconds': np.array([0., 4., 10.]),
             'trace_local_q_m3_s': np.array([[2., 1.], [2., 1.]])})
        with self.assertRaisesRegex(ValueError, 'substep_local_supply_binding'):
            validate_nodal_supply(env)

    def test_resealed_time_averaging(self):
        env = supply_fixture()
        pack(env['dynamics']['arrays'], env['dynamics']['metadata'], 'water_0', {
            'trace_time_seconds': np.array([0., 5., 10.]),
            'trace_local_q_m3_s': np.array([[0., 0.], [2., 4.]])})
        with self.assertRaisesRegex(ValueError, 'substep_local_supply_binding'):
            validate_nodal_supply(env)

    def test_resealed_truncated_trace(self):
        env = supply_fixture()
        pack(env['dynamics']['arrays'], env['dynamics']['metadata'], 'water_0', {
            'trace_time_seconds': np.array([0., 9.]), 'trace_local_q_m3_s': np.array([[1., 2.]])})
        with self.assertRaisesRegex(ValueError, 'child_trace_time_binding'):
            validate_nodal_supply(env)

    def test_nonuniform_runoff_not_smeared(self):
        env = supply_fixture()
        env['arrays']['event.npz']['local_q_m3_s'][0, 0] = 2.
        with self.assertRaisesRegex(ValueError, 'nonuniform_catchment'):
            validate_nodal_supply(env)

    def test_control_area_mismatch(self):
        env = supply_fixture()
        env['dynamics']['arrays']['material_area_m2'] *= 2
        with self.assertRaisesRegex(ValueError, 'material_control_area_binding'):
            validate_nodal_supply(env)


def solver_fixture():
    from tools.native_30m_bundle_validation import validate_solver_links
    env = supply_fixture()
    section = env['arrays']['section.npz']
    section['receiver'] = np.array([1, -1], np.int64)
    context = env['arrays']['reach_context.npz']
    context.update(node_distance_m=np.array([1., 0.]), node_slope_per_m=np.array([1., 1.]),
                   rock_floor_m=np.array([0., -1.]))
    state = env['dynamics']['arrays']
    state.update(node_bed_m=np.tile([2., 1.], (3, 1)),
                 water_volume_m3=np.array([[0., 0.], [10., 20.], [30., 60.]]),
                 mobile_solid_m3=np.zeros((3, 2)), loose_solid_m3=np.zeros((3, 2)),
                 rock_removed_m3=np.zeros((3, 2)))
    env['dynamics']['metadata']['sediment_0']['metadata']['material'] = {'porosity': .35}
    volumes = np.array([[0., 0.], [4., 8.], [10., 20.]])
    water = {
        'network_receiver': section['receiver'].copy(), 'network_width_m': section['width_m'].copy(),
        'network_length_m': context['node_length_m'].copy(),
        'network_receiver_distance_m': context['node_distance_m'].copy(),
        'network_bed_elevation_m': np.array([2., 1.]), 'network_bed_slope': np.array([1., 1.]),
        'network_terminal_kind': np.array(['interior', 'open_outflow']),
        'forcing_time_seconds': np.array([0., 10.]), 'forcing_local_q_m3_s': np.array([[1., 2.]]),
        'trace_time_seconds': np.array([0., 4., 10.]), 'trace_volume_m3': volumes,
        'trace_depth_m': volumes / np.array([2., 4.]), 'trace_outflow_q_m3_s': np.zeros((2, 2)),
    }
    sediment = {
        'domain_receiver': section['receiver'].copy(), 'domain_bed_area_m2': np.array([2., 4.]),
        'domain_width_m': section['width_m'].copy(), 'domain_bed_elevation_m': np.array([2., 1.]),
        'domain_rock_floor_m': context['rock_floor_m'].copy(),
        'domain_open_boundary': np.array([False, True]), 'domain_is_lake': np.zeros(2, bool),
        'forcing_time_seconds': water['trace_time_seconds'].copy(),
        'forcing_water_volume_m3': water['trace_volume_m3'][:-1].copy(),
        'forcing_water_depth_m': water['trace_depth_m'][:-1].copy(),
        'forcing_water_outflow_m3_s': water['trace_outflow_q_m3_s'].copy(),
        'forcing_friction_slope': np.ones((2, 2)), 'initial_mobile_solid_m3': np.zeros(2),
        'trace_bed_elevation_m': np.tile([2., 1.], (3, 1)),
        'trace_mobile_solid_m3': np.zeros((3, 2)), 'trace_bed_alluvium_solid_m3': np.zeros((3, 2)),
        'trace_rock_removed_m3': np.zeros((3, 2)), 'domain_initial_alluvium_bulk_m3': np.zeros(2),
    }
    return env, water, sediment, validate_solver_links


class SolverParentTests(unittest.TestCase):
    def test_valid_links(self):
        env, water, sediment, validate = solver_fixture()
        validate(env, 0, water, sediment)

    def test_water_parent_fields(self):
        for key in ('network_receiver', 'network_bed_slope', 'network_bed_elevation_m',
                    'forcing_local_q_m3_s', 'forcing_time_seconds', 'trace_volume_m3'):
            with self.subTest(key=key):
                env, water, sediment, validate = solver_fixture()
                water[key].flat[-1] += 1
                with self.assertRaisesRegex(ValueError, 'solver_parent_binding'):
                    validate(env, 0, water, sediment)

    def test_sediment_cannot_use_another_water_trace(self):
        for key in ('forcing_water_volume_m3', 'forcing_water_depth_m', 'forcing_water_outflow_m3_s',
                    'forcing_friction_slope', 'domain_bed_area_m2', 'trace_bed_elevation_m',
                    'trace_mobile_solid_m3', 'trace_bed_alluvium_solid_m3', 'trace_rock_removed_m3'):
            with self.subTest(key=key):
                env, water, sediment, validate = solver_fixture()
                sediment[key].flat[-1] += 1
                with self.assertRaisesRegex(ValueError, 'solver_parent_binding'):
                    validate(env, 0, water, sediment)


if __name__ == '__main__':
    unittest.main()
