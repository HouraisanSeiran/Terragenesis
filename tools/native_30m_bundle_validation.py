"""Cross-stage validation of saved native river products, without repairing them."""
import numpy as np


def validate_graph_bindings(env):
    from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
    from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge

    arrays = env['arrays']
    source = arrays['source.npz']
    topology = arrays['topology.npz']
    selection = arrays['selection.npz']
    section = arrays['section.npz']
    context = arrays['reach_context.npz']
    chosen = env['json_records']['selection.json']['chosen']
    if env['json_records']['source.json']['source_records'] != env['manifest']['source_records']:
        raise ValueError('source_records_binding')
    derived = build_strict_topology(source['field'], source['resolved_mask'],
        origin_native_xz=tuple(int(v) for v in source.get('origin_native_xz', (0, 0))))
    for name in ('receiver', 'valid_mask', 'terminal_kind', 'upstream_unknown_mask'):
        if not np.array_equal(topology[name], derived[name]):
            raise ValueError('topology_recompute_mismatch:' + name)
    acc = accumulate_network_discharge(
        topology['receiver'], topology['valid_mask'].astype(np.float64), topology['valid_mask'],
        terminal_kind=topology['terminal_kind'], upstream_unknown_mask=topology['upstream_unknown_mask'])
    receiver = topology['receiver'].ravel()
    catch = selection['catchment_mask'].ravel()
    stem = selection['stem_flat_cells']
    nodes = section['node_cell_ids']
    terminal = chosen['terminal_flat_cell']
    if type(terminal) is not int or not 0 <= terminal < receiver.size:
        raise ValueError('chosen_terminal_range')
    if (not catch[terminal] or receiver[terminal] != -1 or stem[-1] != terminal or
            nodes[-1] != terminal or topology['terminal_kind'].ravel()[terminal] != 'retained'):
        raise ValueError('chosen_terminal_binding')
    native_xz = source['origin_native_xz'] + [terminal % source['field'].shape[1],
                                             terminal // source['field'].shape[1]]
    if not np.array_equal(native_xz, chosen['terminal_native_xz']):
        raise ValueError('chosen_terminal_coordinates')
    live = np.flatnonzero(catch)
    targets = receiver[live]
    if np.any((targets < 0) & (live != terminal)):
        raise ValueError('catchment_has_another_terminal')
    moving = targets >= 0
    if np.any(~catch[targets[moving]]):
        raise ValueError('catchment_receiver_leaves_scope')
    if not acc['complete_mask'].ravel()[live].all():
        raise ValueError('catchment_upstream_unknown')
    full_counts = acc['known_routed_q_m3_s'].ravel()
    if full_counts[terminal] != live.size or chosen['catchment_cells'] != live.size:
        raise ValueError('catchment_not_full_upstream_tree')
    if (np.unique(stem).size != stem.size or
            not np.array_equal(receiver[stem[:-1]], stem[1:]) or
            not np.array_equal(np.sort(stem), np.flatnonzero(selection['flowline_mask']))):
        raise ValueError('stem_topology_binding')
    positions = {int(cell): i for i, cell in enumerate(stem)}
    order = np.array([positions[int(cell)] for cell in nodes])
    if np.any(np.diff(order) <= 0):
        raise ValueError('section_node_stem_order')
    counts = full_counts[nodes]
    if not np.array_equal(counts, np.rint(counts)):
        raise ValueError('nonintegral_node_catchment_counts')
    lateral = np.r_[counts[0], np.diff(counts)].astype(np.int64)
    if not np.array_equal(context['lateral_cell_counts'], lateral):
        raise ValueError('lateral_topology_binding')
    return {'topology_recomputed': True, 'catchment_cells': int(live.size),
            'node_lateral_counts_recomputed': True}


def validate_nodal_supply(env):
    from tools.audit_native_30m_bundle import unpack_pin

    arrays = env['arrays']
    event = arrays['event.npz']
    context = arrays['reach_context.npz']
    section = arrays['section.npz']
    dyn = env['dynamics']
    metadata = dyn['metadata']
    event_meta = env['json_records']['event.json']
    reach_meta = env['json_records']['reach_context.json']['reach_metadata']
    count = env['manifest']['parameters']['coupled_intervals']
    n = section['node_cell_ids'].size
    edges = event['time_edges_s'][:count + 1]
    if (reach_meta['forcing_event_identity_sha256'] != event_meta['event_identity'] or
            not np.array_equal(reach_meta['forcing_time_edges_s'], event['time_edges_s']) or
            not np.array_equal(reach_meta['simulation_time_edges_s'], edges)):
        raise ValueError('reach_event_time_binding')
    local = event['local_q_m3_s']
    scale = max(1.0, float(np.max(np.abs(local))))
    if np.any(np.ptp(local, axis=1) > 1e-14 * scale):
        raise ValueError('nonuniform_catchment_requires_explicit_node_attribution')
    supply = local[:count, :1] * context['lateral_cell_counts'][None, :]
    if not np.allclose(supply.sum(axis=1), local[:count].sum(axis=1), rtol=1e-12, atol=1e-12):
        raise ValueError('nodal_supply_total_binding')
    expected_area = section['width_m'] * context['node_length_m']
    if not np.array_equal(expected_area, dyn['arrays']['material_area_m2']):
        raise ValueError('material_control_area_binding')
    if len(metadata['intervals']) != count:
        raise ValueError('coupled_interval_count_binding')
    delivered = []
    for i in range(count):
        interval = metadata['intervals'][i]
        if interval['start_seconds'] != edges[i] or interval['end_seconds'] != edges[i+1]:
            raise ValueError('coupled_interval_time_binding')
        water, wm = unpack_pin(dyn['arrays'], metadata, 'water_%d' % i)
        sediment, sm = unpack_pin(dyn['arrays'], metadata, 'sediment_%d' % i)
        if wm.get('status') != 'complete' or sm.get('status') != 'complete':
            raise ValueError('incomplete_child_solver')
        for trace in (water, sediment):
            t = trace['trace_time_seconds']
            if (t.ndim != 1 or t.size < 2 or t[0] != edges[i] or t[-1] != edges[i+1] or
                    not np.isfinite(t).all() or np.any(np.diff(t) <= 0)):
                raise ValueError('child_trace_time_binding')
        q = water['trace_local_q_m3_s']
        t = water['trace_time_seconds']
        if q.shape != (t.size-1, n) or not np.array_equal(q, np.broadcast_to(supply[i], q.shape)):
            raise ValueError('substep_local_supply_binding')
        volume = np.sum(q * np.diff(t)[:, None], axis=0)
        expected = supply[i] * (edges[i+1]-edges[i])
        if not np.allclose(volume, expected, rtol=1e-12, atol=1e-9):
            raise ValueError('substep_supply_volume_binding')
        delivered.append(float(volume.sum()))
    return {'forcing_source': 'original_soil_bucket_local_q',
            'routed_terminal_used_for_dynamic_injection': False,
            'per_interval_input_m3': delivered, 'substep_supply_verified': True}


def validate_solver_links(env, index, water, sediment):
    """Verify stored child inputs/endpoints against their declared parent state."""
    a = env['arrays']
    rc = a['reach_context.npz']
    section = a['section.npz']
    dyn = env['dynamics']['arrays']
    metadata = env['dynamics']['metadata']
    receiver = section['receiver']
    edges = a['event.npz']['time_edges_s'][index:index+2]
    bed = dyn['node_bed_m'][index]
    slopes = rc['node_slope_per_m'].copy()
    slopes[:-1] = np.diff(-bed) / rc['node_distance_m'][:-1]
    counts = rc['lateral_cell_counts']
    supply = a['event.npz']['local_q_m3_s'][index, 0] * counts

    def equal(actual, expected, name):
        if not np.array_equal(actual, expected):
            raise ValueError('solver_parent_binding:' + name)

    for key, expected in (
            ('network_receiver', receiver), ('network_width_m', section['width_m']),
            ('network_length_m', rc['node_length_m']), ('network_receiver_distance_m', rc['node_distance_m']),
            ('network_bed_elevation_m', bed), ('network_bed_slope', slopes),
            ('forcing_time_seconds', edges), ('forcing_local_q_m3_s', supply[None, :])):
        equal(water[key], expected, key)
    equal(water['network_terminal_kind'], np.where(receiver >= 0, 'interior', 'open_outflow'),
          'network_terminal_kind')
    equal(water['trace_volume_m3'][0], dyn['water_volume_m3'][index], 'water_initial')
    equal(water['trace_volume_m3'][-1], dyn['water_volume_m3'][index+1], 'water_final')
    for key, expected in (
            ('domain_receiver', receiver), ('domain_bed_area_m2', dyn['material_area_m2']),
            ('domain_width_m', section['width_m']), ('domain_bed_elevation_m', bed),
            ('domain_rock_floor_m', rc['rock_floor_m']),
            ('domain_open_boundary', receiver < 0), ('domain_is_lake', np.zeros(receiver.size, bool)),
            ('forcing_time_seconds', water['trace_time_seconds']),
            ('forcing_water_volume_m3', water['trace_volume_m3'][:-1]),
            ('forcing_water_depth_m', water['trace_depth_m'][:-1]),
            ('forcing_water_outflow_m3_s', water['trace_outflow_q_m3_s']),
            ('forcing_friction_slope', np.broadcast_to(slopes, water['trace_outflow_q_m3_s'].shape)),
            ('initial_mobile_solid_m3', dyn['mobile_solid_m3'][index])):
        equal(sediment[key], expected, key)
    for key, parent in (('trace_bed_elevation_m', 'node_bed_m'),
                         ('trace_mobile_solid_m3', 'mobile_solid_m3'),
                         ('trace_bed_alluvium_solid_m3', 'loose_solid_m3')):
        if not np.allclose(sediment[key][0], dyn[parent][index], rtol=1e-12, atol=1e-12):
            raise ValueError('solver_parent_binding:' + key + '_initial')
        equal(sediment[key][-1], dyn[parent][index+1], key + '_final')
    equal(sediment['trace_rock_removed_m3'][-1] + dyn['rock_removed_m3'][index],
          dyn['rock_removed_m3'][index+1], 'rock_removed_interval')
    porosity = metadata['sediment_%d' % index]['metadata']['material']['porosity']
    if not np.allclose(sediment['domain_initial_alluvium_bulk_m3'] * (1-porosity),
                       dyn['loose_solid_m3'][index], rtol=1e-12, atol=1e-12):
        raise ValueError('solver_parent_binding:initial_alluvium')


def validate_solver_states(env):
    from tools.audit_native_30m_bundle import unpack_pin
    dynamics = env['dynamics']
    count = env['manifest']['parameters']['coupled_intervals']
    for i in range(count):
        water, _ = unpack_pin(dynamics['arrays'], dynamics['metadata'], 'water_%d' % i)
        sediment, _ = unpack_pin(dynamics['arrays'], dynamics['metadata'], 'sediment_%d' % i)
        validate_solver_links(env, i, water, sediment)
    return {'child_parent_states_verified': True, 'intervals': count}


def validate_diagnostic_binding(env):
    """Tie the diagnostic product's declared interval and raw inputs to the event."""
    arrays = env['arrays']
    event = arrays['event.npz']
    event_meta = env['json_records']['event.json']
    r0, r1, c0, c1 = env['json_records']['selection.json']['chosen']['subwindow_rc']
    width = arrays['source.npz']['field'].shape[1]
    raw = arrays['topology.npz']['receiver'][r0:r1, c0:c1]
    rr, cc = raw // width, raw % width
    inside = (raw >= 0) & (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
    receiver = np.where(inside, (rr-r0)*(c1-c0)+cc-c0, -1).astype(np.int64)
    step = event_meta['design_q_interval_index']
    local = np.zeros(receiver.shape, np.float64)
    local.ravel()[event['active_cells']] = event['local_q_m3_s'][step]
    valid = np.ones(receiver.shape, bool)
    unknown = np.zeros(receiver.shape, bool)
    unknown[[0, -1], :] = True
    unknown[:, [0, -1]] = True
    kinds = np.where(receiver >= 0, 'interior', 'retained')
    product = env['diagnostic']
    for name, expected in (('receiver', receiver), ('local_q_m3_s', local),
                           ('valid_mask', valid), ('upstream_unknown_mask', unknown), ('terminal_kind', kinds)):
        if not np.array_equal(product['arrays'][name], expected):
            raise ValueError('diagnostic_event_binding:' + name)
    meta = product['metadata']
    if (meta['origin_native_cells'] != event_meta['source']['origin_native_xz'] or
            meta['world_seed'] != env['manifest']['parameters']['world_seed'] or meta['spacing_m'] != 30.0 or
            not np.array_equal(meta['interval_seconds'], event['time_edges_s'][step:step+2]) or
            meta['source_sha256'] != env['manifest']['stage_identities']['source_assembly']):
        raise ValueError('diagnostic_event_metadata_binding')
