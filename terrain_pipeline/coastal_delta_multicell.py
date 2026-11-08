"""Fixed-footprint annual and physical exchange for multi-cell channels."""
from dataclasses import asdict, replace
import copy
import math
import numpy as np
import networkx as nx

from .coastal_delta_routes import node_control_length, route_metrics
from .coastal_marine_sediment import RiverPacket, advance as marine_advance
from .coastal_delta_deposition_scaling import deposition_fraction_for_length

BED = 'bed_solid_m3'
MOBILE = 'mobile_solid_m3'
SECONDS_PER_YEAR = 365.25 * 86400.


def _prepare(state, progress):
    from .coastal_delta_node_inventory import ChannelInventory
    from .coastal_delta_branching import _validate
    _validate(state, progress)
    p = copy.deepcopy(progress)
    pool = ChannelInventory(state, p)
    metrics = route_metrics(p, state.spacing_m)
    design = p.get('fixed_channel_footprint', {}).get('design_width_m', {})
    for node in p['hydraulic_sections']['nodes']:
        key = tuple(node[:2])
        design.setdefault(str(key), node[3])
        node[3] = min(design[str(key)], pool.area(key) / node_control_length(p, key, state.spacing_m, metrics))
        if node[3] <= 0:
            raise ValueError('node has no channel footprint')
    nmain = len(p['integrated']['sections']['section_width_m'])
    p['integrated']['sections']['section_width_m'] = [n[3] for n in p['hydraulic_sections']['nodes'][:nmain]]
    footprint = p.setdefault('fixed_channel_footprint', {})
    footprint.update({'design_width_m': design, 'effective_width_m': {str(tuple(n[:2])): n[3] for n in p['hydraulic_sections']['nodes']},
                      'width_rule': 'min(design, footprint area/control length)',
                      'lateral_change': 'fixed footprint; active bank expansion not implemented'})
    state, p = pool.commit(state, p)
    return state, p



def _width_feedback(state, p, budgets, interval_id):
    """Use committed channel exchanges once; grid-process gross exchange is unavailable."""
    from terrain_pipeline.channel_geometry import section_from_routed_budget
    params = p.get('geological_network', {}).get('width_parameters')
    if not params:
        p['fixed_channel_footprint']['feedback_unavailable'] = 'missing geological width parameters'
        return state, p
    known_q = {tuple(row[:2]): row[2] for row in p['geological_network'].get('node_design_q_m3_s', [])}
    # Attachments may postdate the construction metadata. Their design shares are
    # the only formative discharge available, independent of instantaneous tide.
    fallback_q = {}
    for route, share in zip(p['routes'], p['shares']):
        for key in {tuple(cell) for cell in route}:
            fallback_q[key] = fallback_q.get(key, 0.) + p['discharge_m3_s'] * share
    for key, q in fallback_q.items():
        known_q.setdefault(key, q)
    actual_formative = p.get('formative_discharge') if p.get('hydraulics_backend') == 'physical_edge_graph' else None
    if p.get('hydraulics_backend') == 'physical_edge_graph':
        known_q = {tuple(row[:2]): row[2] for row in (actual_formative or {}).get('nodes', [])}
    design = p['fixed_channel_footprint']['design_width_m']
    for node, budget in budgets.items():
        q = known_q.get(node)
        if q is None or q <= 0:
            budget['feedback_unavailable'] = 'formative discharge unavailable'
            continue
        result = section_from_routed_budget(q, params.get('bed_resistance', .5),
            params.get('bank_resistance', .5), params.get('fracture', 0.),
            params.get('bank_cohesion', .5), incoming_solid_m3=budget['incoming_solid_m3'],
            external_solid_m3=budget['external_solid_m3'], capacity_solid_m3=budget['capacity_solid_m3'],
            eroded_loose_solid_m3=budget['eroded_solid_m3'], eroded_rock_m3=0.,
            deposited_solid_m3=budget['deposited_solid_m3'],
            initial_mobile_solid_m3=budget['initial_mobile_solid_m3'],
            reference_discharge_m3_s=params.get('reference_q_m3_s', p['discharge_m3_s']),
            reference_width_m=params['reference_width_m'], max_width_m=params['max_width_m'])
        design[str(node)] = float(result.width_m)
        budget['formative_q_m3_s'] = q
        budget['baseline_width_m'] = float(result.baseline_width_m)
        budget['feedback_width_delta_m'] = float(result.width_m - result.baseline_width_m)
    p['fixed_channel_footprint']['last_feedback'] = {
        'input_id': interval_id, 'nodes': {str(k): v for k, v in budgets.items()},
        'scope': 'committed channel routing only; grid marine and floodplain gross erosion/deposition unavailable',
        'formative_q_source': (actual_formative or {}).get('source',
            'actual formative discharge unavailable' if p.get('hydraulics_backend') == 'physical_edge_graph'
            else 'existing node design Q, or accumulated design route shares for missing nodes'),
        'boundary': 'one update per event or annual interval; splitting changes feedback boundaries'}
    return _prepare(state, p)


def _budgets(pool):
    return {node: {'incoming_solid_m3': 0., 'external_solid_m3': 0.,
        'capacity_solid_m3': 0., 'eroded_solid_m3': 0., 'deposited_solid_m3': 0.,
        'initial_mobile_solid_m3': pool.amount(node, MOBILE)} for node in pool.node_keys}


def _after_grid(pool, before, after, p):
    pool.apply_grid_changes(before, after)
    return pool.commit(after, p)


def _edges(state, p, sea_level):
    from .coastal_delta_branching import _event_edges
    outgoing = {}
    for edge in _event_edges(state, p, sea_level):
        outgoing.setdefault(tuple(edge['from_zx']), []).append(edge)
    return outgoing


def advance_event(state, progress, duration_s, marine_config, *, input_id, hydraulic_config,
                  inlet_solid_rate_m3_s, capacity_concentration, active_layer_m, max_velocity_m_s):
    from .coastal_delta_node_inventory import ChannelInventory
    from .coastal_delta_branching import _record, _update_activity, _mouth_forcing
    if (not input_id or input_id in progress['integrated']['consumed_year_inputs']
            or any(r['input_id'] == input_id or r['input_id'].startswith(input_id+':stage:')
                   for r in state.consumed_packets)
            or hydraulic_config is None or not np.isfinite([duration_s, inlet_solid_rate_m3_s,
                capacity_concentration, active_layer_m, max_velocity_m_s, marine_config.step_s]).all()
            or duration_s <= 0 or inlet_solid_rate_m3_s < 0 or not 0 < capacity_concentration <= 1
            or active_layer_m < 0 or max_velocity_m_s <= 0 or marine_config.step_s <= 0):
        raise ValueError('invalid or duplicate multi-cell event')
    state, p = _prepare(state, progress)
    from .coastal_delta_multicell_avulsion import initialize_baseline
    initialize_baseline(p)
    inlet = tuple(p['routes'][0][0])
    pool = ChannelInventory(state, p)
    budgets = _budgets(pool)
    caps = {tuple(row[:2]): min(pool.amount(tuple(row[:2]), BED), active_layer_m * state.spacing_m**2 *
            sum(part[2]*(1-state.porosity[part[0], part[1]]) for part in row[2]))
            for row in p['node_footprints']}
    start = state.time_s
    delivered_water = delivered_solid = moved = eroded_total = 0.
    deliveries = {}
    while state.time_s < start + duration_s - 1e-9:
        dt = min(marine_config.step_s, start + duration_s - state.time_s)
        phase = 2*math.pi*(state.time_s+dt/2)/marine_config.tide_period_s
        level = marine_config.sea_level_m + marine_config.tide_amplitude_m*math.sin(phase)
        _update_activity(state, p, level, input_id, hydraulic_config)
        hydraulic = p['river_hydraulics']
        interval_hydraulic = copy.deepcopy(hydraulic)
        accepted = hydraulic['accepted_q_m3_s']
        water = accepted*dt
        solid = min(inlet_solid_rate_m3_s*dt*accepted/p['discharge_m3_s'], accepted*capacity_concentration*dt)
        delivered_water += water
        delivered_solid += solid
        pool = ChannelInventory(state, p)
        if solid:
            pool.add(inlet, MOBILE, solid)
            budgets[inlet]['external_solid_m3'] += solid
        outgoing = _edges(state, p, level)
        widths = {tuple(n[:2]): n[3] for n in p['hydraulic_sections']['nodes']}
        stages = {tuple(n[:2]): n[2] for n in hydraulic['nodes']}
        metrics = route_metrics(p, state.spacing_m)
        incoming = {}
        ocean_delivery = []
        for node, edges in outgoing.items():
            depth = stages.get(node, level)-pool.section_bed(node)
            if depth <= 0:
                continue
            usable = [e for e in edges if tuple(e['to_zx']) not in widths or
                      stages.get(tuple(e['to_zx']), level) > pool.section_bed(tuple(e['to_zx']))]
            q = sum(e['discharge_m3_s'] for e in usable)
            if q <= 0:
                continue
            speed = min(max_velocity_m_s, q/(widths[node]*depth))
            fraction = min(1., speed*dt/node_control_length(p, node, state.spacing_m, metrics))
            capacity = q*capacity_concentration*dt
            budgets[node]['capacity_solid_m3'] += capacity
            carried = pool.take(node, MOBILE, min(pool.amount(node, MOBILE)*fraction, capacity))
            eroded = pool.take(node, BED, min(caps[node], max(0., capacity-carried)))
            caps[node] -= eroded
            moved += carried + eroded
            eroded_total += eroded
            budgets[node]['eroded_solid_m3'] += eroded
            for edge in usable:
                destination = tuple(edge['to_zx'])
                amount = (carried+eroded)*edge['discharge_m3_s']/q
                if destination in widths:
                    incoming[destination] = incoming.get(destination, 0.) + amount
                else:
                    ocean_delivery.append((node, destination, amount))
        for node, amount in incoming.items():
            pool.add(node, MOBILE, amount)
            budgets[node]['incoming_solid_m3'] += amount
        state, p = pool.commit(state, p)
        held = {}
        for node in pool.node_keys:
            held[node] = (pool.take(node, MOBILE, pool.amount(node, MOBILE)),
                          pool.take(node, 'stranded_solid_m3', pool.amount(node, 'stranded_solid_m3')))
        state, p = pool.commit(state, p)
        before = state
        if ocean_delivery:
            mobile = state.mobile_solid_m3.copy()
            for mouth, destination, amount in ocean_delivery:
                mobile[destination] += amount
                key = (mouth, destination)
                deliveries[key] = deliveries.get(key, 0.) + amount
            state = replace(state, mobile_solid_m3=mobile)
        packet = []
        internal_id = f'{input_id}:stage:{state.time_s-start:.9f}'
        if water > 0:
            direction = np.asarray(p['routes'][0][1][::-1])-np.asarray(p['routes'][0][0][::-1])
            packet = [RiverPacket(internal_id, 'multi-cell-inlet', state.time_s, state.time_s+dt,
                inlet[0], inlet[1], water, 0., True, tuple(direction), widths[inlet],
                max(stages[inlet]-pool.section_bed(inlet), .001))]
        state = marine_advance(state, packet, dt, marine_config, mouth_forcing=_mouth_forcing(p))
        state, p = _after_grid(pool, before, state, p)
        for node, (mobile, stranded) in held.items():
            pool.add(node, MOBILE, mobile)
            pool.add(node, 'stranded_solid_m3', stranded)
        state, p = pool.commit(state, p)
        state = replace(state, consumed_packets=tuple(r for r in state.consumed_packets if r['input_id'] != internal_id))
    _update_activity(state, p, marine_config.sea_level_m + marine_config.tide_amplitude_m *
                     math.sin(2*math.pi*state.time_s/marine_config.tide_period_s), input_id, hydraulic_config)
    total_water = p['discharge_m3_s']*duration_s
    total_solid = inlet_solid_rate_m3_s*duration_s
    items = [{'mouth_zx': list(a), 'exterior_face_zx': list(b), 'gross_solid_m3': v}
             for (a, b), v in sorted(deliveries.items())]
    record = {'input_id': input_id, 'source_id': 'branch-event-inlet', 'start_s': start, 'end_s': state.time_s,
              'known': True, 'row': inlet[0], 'col': inlet[1], 'direction_xz': [1., 0.],
              'water_m3': total_water, 'solid_m3': total_solid, 'delivered_water_m3': delivered_water,
              'delivered_solid_m3': delivered_solid, 'pending_solid_m3': 0.,
              'undelivered_water_m3': total_water-delivered_water, 'undelivered_solid_m3': total_solid-delivered_solid,
              'record_kind': 'branch_event', 'outlet_delivery': items}
    state = replace(state, consumed_packets=state.consumed_packets+(record,))
    state = _record(state, p)
    from .coastal_delta_avulsion import extend_mouths
    state, p, mouth_update = extend_mouths(state, p, hydraulic_config=hydraulic_config,
                                            sea_level_m=marine_config.sea_level_m)
    from .coastal_delta_avulsion import activate_candidate
    state, p, avulsion = activate_candidate(_record(state, p), p, hydraulic_config=hydraulic_config,
                                            sea_level_m=marine_config.sea_level_m)
    _update_activity(state, p, marine_config.sea_level_m, input_id+':shoreline', hydraulic_config)
    state, p = _width_feedback(state, p, budgets, input_id)
    if 'last_feedback' in p['fixed_channel_footprint']:
        p['fixed_channel_footprint']['last_feedback']['interval_used'] = {
            'last_substep_hydraulics': interval_hydraulic,
            'note': 'last physical substep; tide may vary during the interval'}
    _update_activity(state, p, marine_config.sea_level_m, input_id+':next-width', hydraulic_config)
    state = _record(state, p)
    return state, {**{k: record[k] for k in ('input_id', 'water_m3', 'solid_m3', 'delivered_water_m3',
        'delivered_solid_m3', 'undelivered_water_m3', 'undelivered_solid_m3')},
        'internal_transfer_solid_m3': moved, 'entrained_solid_m3': eroded_total,
        'outlet_delivery': items, 'mouth_update': mouth_update, 'avulsion': avulsion, 'updated_progress': p}


def advance_years(state, progress, years, *, input_id, hydraulic_config, hydraulic_result,
                  marine_config, river_deposition_fraction, floodplain_config, tidal_config, step_years,
                  river_deposition_reference_length_m=None, annual_channel_exchange=None,
                  annual_erosion_depth_m_per_year=None):
    from .coastal_delta_node_inventory import ChannelInventory
    from .coastal_delta_branching import _record, _update_activity, _mouth_forcing
    from .coastal_delta_evolution import overbank_exchange
    from .coastal_marine_longterm import advance as longterm_advance, LongtermConfig, normalize_forcing_parameters
    from .coastal_delta_plain import _park_same_cell
    if (not input_id or input_id in progress['integrated']['consumed_year_inputs']
            or any(r['input_id'] == input_id for r in state.consumed_packets)
            or not np.isfinite([years, river_deposition_fraction]).all()
            or not 0 < years <= 1 or not 0 <= river_deposition_fraction <= 1
            or hydraulic_config is None or hydraulic_result is not None or tidal_config is not None):
        raise ValueError('invalid, duplicate or unsupported multi-cell annual forcing')
    if marine_config is not None and not isinstance(marine_config, LongtermConfig):
        raise ValueError('invalid marine forcing')
    if river_deposition_reference_length_m is not None:
        deposition_fraction_for_length(river_deposition_fraction, river_deposition_reference_length_m, 0.)
    old = progress['integrated'].get('multicell_parameters')
    if old is not None:
        old = copy.deepcopy(old)
        old['marine'] = normalize_forcing_parameters(old.get('marine'))
    exchange = (annual_channel_exchange if annual_channel_exchange is not None
                else (old or {}).get('annual_channel_exchange', 'legacy'))
    erosion_rate = (annual_erosion_depth_m_per_year if annual_erosion_depth_m_per_year is not None
                    else (old or {}).get('annual_erosion_depth_m_per_year', .1))
    if exchange not in ('legacy', 'capacity_balance'):
        raise ValueError('invalid annual channel exchange mode')
    if exchange == 'capacity_balance':
        if progress.get('hydraulics_backend') != 'physical_edge_graph':
            raise ValueError('capacity_balance requires physical_edge_graph')
        if not np.isfinite(erosion_rate) or erosion_rate < 0:
            raise ValueError('invalid annual erosion depth per year')
    elif annual_erosion_depth_m_per_year is not None:
        raise ValueError('annual erosion depth requires capacity_balance')
    state, p = _prepare(state, progress)
    from .coastal_delta_multicell_avulsion import initialize_baseline
    initialize_baseline(p)
    parameters = {'marine': None if marine_config is None else asdict(marine_config),
                  'hydraulic': asdict(hydraulic_config), 'floodplain': asdict(floodplain_config),
                  'river_deposition_fraction': river_deposition_fraction,
                  'capacity_concentration': .01, 'lateral_geometry': 'fixed footprint'}
    if river_deposition_reference_length_m is not None:
        parameters['river_deposition_mode'] = 'reference_length'
        parameters['river_deposition_reference_length_m'] = river_deposition_reference_length_m
    if exchange == 'capacity_balance':
        parameters.update(annual_channel_exchange=exchange,
            annual_erosion_depth_m_per_year=float(erosion_rate),
            annual_channel_algorithm='finite-capacity-balance-v1')
    if old is not None and old != parameters:
        # Only an explicit legacy -> capacity-balance switch may migrate the
        # saved exchange identity. Other forcing changes remain mismatches.
        exchange_keys = {'annual_channel_exchange', 'annual_erosion_depth_m_per_year', 'annual_channel_algorithm'}
        core = {k: v for k, v in parameters.items() if k not in exchange_keys}
        if (annual_channel_exchange == 'capacity_balance'
                and old.get('annual_channel_exchange', 'legacy') == 'legacy' and old == core):
            p['integrated'].setdefault('multicell_parameter_transitions', []).append({
                'input_id': input_id, 'previous': copy.deepcopy(old), 'current': copy.deepcopy(parameters),
                'reason': 'explicit legacy to capacity_balance annual channel exchange'})
        else:
            raise ValueError('multi-cell annual parameters do not match checkpoint')
    p['integrated']['multicell_parameters'] = parameters
    level = 0. if marine_config is None else marine_config.sea_level_m
    _update_activity(state, p, level, input_id, hydraulic_config)
    solution = p['river_hydraulics']
    accepted = solution['accepted_q_m3_s']
    duration = years*SECONDS_PER_YEAR
    supply = p['solid_rate_m3_s']*duration
    delivered = min(supply*accepted/p['discharge_m3_s'], accepted*.01*duration)
    pending = supply-delivered
    pool = ChannelInventory(state, p)
    budgets = _budgets(pool)
    outgoing = _edges(state, p, level)
    graph = nx.DiGraph()
    graph.add_nodes_from(pool.node_keys)
    for node, edges in outgoing.items():
        graph.add_node(node)
        for edge in edges:
            dst = tuple(edge['to_zx'])
            if dst in pool.node_keys:
                graph.add_edge(node, dst)
    flux = {node: 0. for node in graph}
    inlet = tuple(p['routes'][0][0])
    if accepted and inlet in flux:
        flux[inlet] = delivered
        budgets[inlet]['external_solid_m3'] = delivered
    deposited = mouth = 0.
    deliveries = []
    sea_add = []
    stages = {tuple(n[:2]): n[2] for n in solution['nodes']}
    metrics = route_metrics(p, state.spacing_m)
    for node in nx.topological_sort(graph):
        amount = flux[node] + pool.take(node, MOBILE, pool.amount(node, MOBILE))
        edges = outgoing.get(node, [])
        q = sum(e['discharge_m3_s'] for e in edges)
        capacity = q * parameters['capacity_concentration'] * duration
        budgets[node]['capacity_solid_m3'] = capacity
        room = max(0., stages.get(node, pool.section_bed(node))-pool.section_bed(node)) * pool.area(node) * (1-state.porosity[node])
        fraction = river_deposition_fraction
        if river_deposition_reference_length_m is not None:
            fraction = deposition_fraction_for_length(fraction, river_deposition_reference_length_m,
                node_control_length(p, node, state.spacing_m, metrics))
        sediment_to_settle = max(0., amount-capacity) if exchange == 'capacity_balance' else amount
        settled = min(sediment_to_settle*fraction, room)
        if settled:
            pool.add(node, BED, settled)
        deposited += settled
        budgets[node]['deposited_solid_m3'] += settled
        amount -= settled
        transported = min(amount, capacity)
        pool.add(node, MOBILE, amount - transported)
        if exchange == 'capacity_balance':
            # Match finite-event bed entrainment, with a rate integrated over
            # equivalent years so smaller annual calls do not multiply erosion.
            exposed_solid_area = state.spacing_m**2 * math.fsum(
                part[2]*(1-state.porosity[part[0], part[1]]) for part in pool._parts[node])
            erosion_cap = float(erosion_rate)*years*exposed_solid_area
            eroded = pool.take(node, BED, min(erosion_cap, max(0., capacity-transported)))
            transported += eroded
            budgets[node]['eroded_solid_m3'] += eroded
            budgets[node]['erosion_depth_limit_m'] = float(erosion_rate)*years
            budgets[node]['excess_before_settling_solid_m3'] = sediment_to_settle
        budgets[node]['transported_solid_m3'] = transported
        for edge in edges:
            dst = tuple(edge['to_zx'])
            part = transported*edge['discharge_m3_s']/q
            if dst in flux:
                flux[dst] += part
                budgets[dst]['incoming_solid_m3'] += part
            else:
                sea_add.append((node, dst, part))
                mouth += part
                deliveries.append({'mouth_zx': list(node), 'exterior_zx': list(dst), 'gross_solid_m3': part})
    state, p = pool.commit(state, p)
    if sea_add:
        before = state
        mobile = state.mobile_solid_m3.copy()
        for _, dst, amount in sea_add:
            mobile[dst] += amount
        state = replace(state, mobile_solid_m3=mobile)
        state, p = _after_grid(pool, before, state, p)
    if accepted:
        before = state
        cells = [n[:2] for n in solution['nodes']]
        stages_list = [n[2] for n in solution['nodes']]
        state, flood = overbank_exchange(state, cells, stages_list, accepted*duration,
                                         config=floodplain_config)
        state, p = _after_grid(pool, before, state, p)
    else:
        flood = {'deposited_solid_m3': 0.}
    marine_report = {'deposited_solid_m3': 0.}
    if marine_config is not None:
        before = state
        state, marine_report = longterm_advance(state, duration, marine_config,
            park_and_release=_park_same_cell, mouth_forcing=_mouth_forcing(p))
        state = replace(state, time_s=before.time_s)
        state, p = _after_grid(pool, before, state, p)
    info = p['integrated']
    info['equivalent_water_m3'] += p['discharge_m3_s']*duration
    info['accepted_water_m3'] += accepted*duration
    info['pending_water_m3'] += (p['discharge_m3_s']-accepted)*duration
    info['pending_solid_m3'] += pending
    info['river_deposited_solid_m3'] += deposited
    if exchange == 'capacity_balance':
        info['river_eroded_solid_m3'] = info.get('river_eroded_solid_m3', 0.) + math.fsum(
            budget['eroded_solid_m3'] for budget in budgets.values())
    info['mouth_delivered_solid_m3'] += mouth
    info['marine_deposited_solid_m3'] += marine_report['deposited_solid_m3']
    info['floodplain_deposited_solid_m3'] = info.get('floodplain_deposited_solid_m3', 0.) + flood.get('deposited_solid_m3', 0.)
    info['consumed_year_inputs'].append(input_id)
    p['formation_undelivered_water_m3'] = info['pending_water_m3']
    p['formation_undelivered_solid_m3'] = info['pending_solid_m3']
    p['supply_solid_m3'] += supply
    p['years'] += years
    p['history'].append({'event': 'integrated_years', 'input_id': input_id, 'years': years,
        'accepted_q_m3_s': accepted, 'route_q_m3_s': solution['route_q_m3_s'],
        'mouth_handoffs': deliveries, 'river_deposited_solid_m3': deposited,
        'mouth_delivered_solid_m3': mouth, 'marine_deposited_solid_m3': marine_report['deposited_solid_m3'],
        'floodplain': flood, 'lateral_geometry': 'fixed footprint'})
    if exchange == 'capacity_balance':
        p['history'][-1].update(annual_channel_exchange=exchange,
            annual_erosion_depth_m_per_year=float(erosion_rate),
            river_eroded_solid_m3=math.fsum(b['eroded_solid_m3'] for b in budgets.values()))
    state = _record(state, p)
    from .coastal_delta_avulsion import extend_mouths
    state, p, mouth_update = extend_mouths(state, p, hydraulic_config=hydraulic_config, sea_level_m=level)
    p['history'].append({'event': 'shoreline_extension', **mouth_update})
    from .coastal_delta_avulsion import activate_candidate
    state, p, avulsion = activate_candidate(_record(state, p), p, hydraulic_config=hydraulic_config, sea_level_m=level)
    p['history'].append({'event': 'avulsion_check', **avulsion})
    _update_activity(state, p, level, input_id+':final', hydraulic_config)
    state, p = _width_feedback(state, p, budgets, input_id)
    if 'last_feedback' in p['fixed_channel_footprint']:
        p['fixed_channel_footprint']['last_feedback']['interval_used'] = {
            'hydraulics': solution, 'capacity_concentration': parameters['capacity_concentration'],
            'duration_s': duration}
    _update_activity(state, p, level, input_id+':next-width', hydraulic_config)
    return _record(state, p), p
