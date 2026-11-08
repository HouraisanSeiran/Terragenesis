"""Opt-in physical event for multi-cell deltas with hydraulic transport capacity (issue 24).

Mirrors ``coastal_delta_multicell.advance_event`` (which stays unchanged and
remains the default) but the channel exchange uses
``coastal_delta_hydraulic_capacity``: capacity from actual Q, depth, width and
Manning friction slope, erosion only for under-loaded nodes, finite settling
for over-loaded nodes, and transport substeps dt <= L/v inside every marine step.
"""
from dataclasses import replace
import copy
import math

import numpy as np

from .coastal_delta_routes import node_control_length, route_metrics
from .coastal_marine_sediment import RiverPacket, advance as marine_advance
from . import coastal_delta_hydraulic_capacity as hc

BED = hc.BED
MOBILE = hc.MOBILE


def advance_event_hydraulic(state, progress, duration_s, marine_config, *, input_id, hydraulic_config,
                            inlet_solid_rate_m3_s, capacity_rule, active_layer_m=.1, max_velocity_m_s=2.,
                            fixed_topology=False, floodplain_config=None):
    from .coastal_delta_node_inventory import ChannelInventory
    from .coastal_delta_branching import _record, _update_activity, _mouth_forcing, _clean_roundoff
    from .coastal_delta_multicell import _prepare, _budgets, _after_grid, _edges, _width_feedback
    if not isinstance(capacity_rule, hc.HydraulicCapacityRule):
        raise ValueError('capacity_rule must be a HydraulicCapacityRule')
    if (not input_id or input_id in progress['integrated']['consumed_year_inputs']
            or any(r['input_id'] == input_id or r['input_id'].startswith(input_id + ':stage:')
                   for r in state.consumed_packets)
            or hydraulic_config is None or not np.isfinite([duration_s, inlet_solid_rate_m3_s,
                active_layer_m, max_velocity_m_s, marine_config.step_s]).all()
            or duration_s <= 0 or inlet_solid_rate_m3_s < 0
            or active_layer_m < 0 or max_velocity_m_s <= 0 or marine_config.step_s <= 0):
        raise ValueError('invalid or duplicate multi-cell event')
    identity = capacity_rule.identity()
    saved = progress.get('hydraulic_capacity_rule')
    if saved is not None and saved != identity:
        raise ValueError('hydraulic capacity rule differs from the saved case identity')
    if progress.get('floodplain_coupling') and floodplain_config is None:
        raise ValueError('saved floodplain process requires its configuration')
    if floodplain_config is not None and not fixed_topology:
        raise ValueError('floodplain coupling currently requires fixed topology')
    state, p = _prepare(state, progress)
    flood = None
    layout = None
    if floodplain_config is not None:
        from . import coastal_delta_floodplain_coupling as flood
        state, p = flood.initialize_water(state, p, floodplain_config)
        layout = flood.bank_layout(state, p, marine_config.sea_level_m, floodplain_config)
    from .coastal_delta_multicell_avulsion import initialize_baseline
    initialize_baseline(p)
    p['hydraulic_capacity_rule'] = identity
    inlet = tuple(p['routes'][0][0])
    pool = ChannelInventory(state, p)
    budgets = _budgets(pool)
    caps = {tuple(row[:2]): min(pool.amount(tuple(row[:2]), BED), active_layer_m * state.spacing_m ** 2 *
            sum(part[2] * (1 - state.porosity[part[0], part[1]]) for part in row[2]))
            for row in p['node_footprints']}
    start = state.time_s
    delivered_water = delivered_solid = moved = eroded_total = 0.
    deliveries = {}
    outlet_water = {}
    diag = {}
    flood_totals = dict(bank_out_water_m3=0., bank_return_water_m3=0.,
        bank_out_solid_m3=0., bank_return_solid_m3=0., deposited_solid_m3=0., receiving_water_m3=0.)
    while state.time_s < start + duration_s - 1e-9:
        dt = min(marine_config.step_s, start + duration_s - state.time_s)
        phase = 2 * math.pi * (state.time_s + dt / 2) / marine_config.tide_period_s
        level = marine_config.sea_level_m + marine_config.tide_amplitude_m * math.sin(phase)
        if flood is not None:
            p.pop('river_lateral_exchange', None)
        _update_activity(state, p, level, input_id, hydraulic_config)
        plan = None
        if flood is not None:
            plan = flood.plan_exchange(state, p, layout, dt, floodplain_config)
            p['river_lateral_exchange'] = plan['river']
            _update_activity(state, p, level, input_id + ':lateral', hydraulic_config)
        hydraulic = p['river_hydraulics']
        interval_hydraulic = copy.deepcopy(hydraulic)
        accepted = hydraulic['accepted_q_m3_s']
        for z, x, q in hydraulic.get('mouth_q_m3_s', []):
            mouth = (int(z), int(x))
            outlet_water[mouth] = outlet_water.get(mouth, 0.) + q * dt
        water = accepted * dt
        solid = capacity_rule.inlet_solid(inlet_solid_rate_m3_s * dt * accepted / p['discharge_m3_s'], accepted, dt)
        delivered_water += water
        delivered_solid += solid
        pool = ChannelInventory(state, p)
        returned_solid = 0.
        if flood is not None:
            state, p, returned_solid = flood.apply_returns(state, p, pool, plan)
        outgoing = _edges(state, p, level)
        spill_volumes = {}
        if flood is not None:
            spill_edges, spill_volumes = flood.sink_edges(p, plan, dt)
            for node, edges in spill_edges.items():
                outgoing.setdefault(node, []).extend(edges)
        widths = {tuple(n[:2]): n[3] for n in p['hydraulic_sections']['nodes']}
        roughness = {tuple(n[:2]): (n[5] if len(n) == 6 else hydraulic_config.roughness)
                     for n in p['hydraulic_sections']['nodes']}
        stages = {tuple(n[:2]): n[2] for n in hydraulic['nodes']}
        metrics = route_metrics(p, state.spacing_m)
        ocean_delivery, step_moved, step_eroded = hc.river_transport(
            capacity_rule, pool, state, level, dt, outgoing, widths, stages, roughness,
            lambda node: node_control_length(p, node, state.spacing_m, metrics),
            caps, budgets, diag, max_velocity_m_s, inlet=inlet, inlet_solid_m3=solid)
        moved += step_moved
        eroded_total += step_eroded
        state, p = pool.commit(state, p)
        if flood is not None:
            state, p, ocean_delivery, flood_solid, flood_report, deposition = flood.spread_and_settle(
                state, p, pool, plan, spill_volumes, ocean_delivery, layout, dt, floodplain_config)
            spilled = math.fsum(spill_volumes.values())
            returned = math.fsum(row[2] for row in plan['sources'])
            receiving_water = water - spilled + returned
            if receiving_water < -1e-6:
                raise ValueError('lateral water budget exceeds accepted river input')
            receiving_water = max(0., receiving_water)
            increments = dict(bank_out_water_m3=spilled, bank_return_water_m3=returned,
                bank_out_solid_m3=flood_solid, bank_return_solid_m3=returned_solid,
                deposited_solid_m3=deposition, receiving_water_m3=receiving_water)
            ledger = p['floodplain_coupling']
            ledger['accepted_river_water_m3'] += water
            ledger['completed_steps'] += 1
            ledger['last_spreading_report'] = flood_report
            for name, value in increments.items():
                ledger[name] += value
                flood_totals[name] += value
        else:
            receiving_water = water
        held = {}
        for node in pool.node_keys:
            held[node] = (pool.take(node, MOBILE, pool.amount(node, MOBILE)),
                          pool.take(node, 'stranded_solid_m3', pool.amount(node, 'stranded_solid_m3')))
        state, p = pool.commit(state, p)
        held_floodplain = None
        if flood is not None:
            mask = layout['allowed']
            held_floodplain = (np.where(mask, state.mobile_solid_m3, 0.),
                               np.where(mask, state.stranded_solid_m3, 0.))
            after = replace(state, mobile_solid_m3=state.mobile_solid_m3 - held_floodplain[0],
                stranded_solid_m3=state.stranded_solid_m3 - held_floodplain[1])
            state, p = _after_grid(pool, state, after, p)
        before = state
        if ocean_delivery:
            mobile = state.mobile_solid_m3.copy()
            for mouth, destination, amount in ocean_delivery:
                mobile[destination] += amount
                key = (mouth, destination)
                deliveries[key] = deliveries.get(key, 0.) + amount
            state = replace(state, mobile_solid_m3=mobile)
        packet = []
        internal_id = f'{input_id}:stage:{state.time_s - start:.9f}'
        if receiving_water > 0:
            direction = np.asarray(p['routes'][0][1][::-1]) - np.asarray(p['routes'][0][0][::-1])
            packet = [RiverPacket(internal_id, 'multi-cell-inlet', state.time_s, state.time_s + dt,
                inlet[0], inlet[1], receiving_water, 0., True, tuple(direction), widths[inlet],
                max(stages[inlet] - pool.section_bed(inlet), .001))]
        state = marine_advance(state, packet, dt, marine_config, mouth_forcing=_mouth_forcing(p))
        state = _clean_roundoff(state)
        state, p = _after_grid(pool, before, state, p)
        if held_floodplain is not None:
            after = replace(state, mobile_solid_m3=state.mobile_solid_m3 + held_floodplain[0],
                stranded_solid_m3=state.stranded_solid_m3 + held_floodplain[1])
            state, p = _after_grid(pool, state, after, p)
        for node, (mobile, stranded) in held.items():
            pool.add(node, MOBILE, mobile)
            pool.add(node, 'stranded_solid_m3', stranded)
        state, p = pool.commit(state, p)
        state = replace(state, consumed_packets=tuple(r for r in state.consumed_packets if r['input_id'] != internal_id))
    _update_activity(state, p, marine_config.sea_level_m + marine_config.tide_amplitude_m *
                     math.sin(2 * math.pi * state.time_s / marine_config.tide_period_s), input_id, hydraulic_config)
    total_water = p['discharge_m3_s'] * duration_s
    total_solid = inlet_solid_rate_m3_s * duration_s
    items = [{'mouth_zx': list(a), 'exterior_face_zx': list(b), 'gross_solid_m3': v}
             for (a, b), v in sorted(deliveries.items())]
    water_items = [{'mouth_zx': list(mouth), 'water_m3': volume}
                   for mouth, volume in sorted(outlet_water.items())]
    record = {'input_id': input_id, 'source_id': 'branch-event-inlet', 'start_s': start, 'end_s': state.time_s,
              'known': True, 'row': inlet[0], 'col': inlet[1], 'direction_xz': [1., 0.],
              'water_m3': total_water, 'solid_m3': total_solid, 'delivered_water_m3': delivered_water,
              'delivered_solid_m3': delivered_solid, 'pending_solid_m3': 0.,
              'undelivered_water_m3': total_water - delivered_water, 'undelivered_solid_m3': total_solid - delivered_solid,
              'record_kind': 'branch_event', 'outlet_delivery': items, 'outlet_water': water_items}
    if flood is not None:
        record['floodplain'] = flood_totals
    state = replace(state, consumed_packets=state.consumed_packets + (record,))
    state = _record(state, p)
    if fixed_topology:
        mouth_update = {'extended': False, 'trigger': 'explicit_fixed_topology'}
        avulsion = {'activated': False, 'trigger': 'explicit_fixed_topology'}
    else:
        from .coastal_delta_avulsion import extend_mouths, activate_candidate
        state, p, mouth_update = extend_mouths(state, p, hydraulic_config=hydraulic_config,
                                               sea_level_m=marine_config.sea_level_m)
        state, p, avulsion = activate_candidate(_record(state, p), p, hydraulic_config=hydraulic_config,
                                                sea_level_m=marine_config.sea_level_m)
        _update_activity(state, p, marine_config.sea_level_m, input_id + ':shoreline', hydraulic_config)
        state, p = _width_feedback(state, p, budgets, input_id)
    if 'last_feedback' in p['fixed_channel_footprint']:
        p['fixed_channel_footprint']['last_feedback']['interval_used'] = {
            'last_substep_hydraulics': interval_hydraulic,
            'note': 'last physical substep; tide may vary during the interval'}
    if not fixed_topology:
        _update_activity(state, p, marine_config.sea_level_m, input_id + ':next-width', hydraulic_config)
    state = _record(state, p)
    return state, {**{k: record[k] for k in ('input_id', 'water_m3', 'solid_m3', 'delivered_water_m3',
        'delivered_solid_m3', 'undelivered_water_m3', 'undelivered_solid_m3')},
        'internal_transfer_solid_m3': moved, 'entrained_solid_m3': eroded_total,
        'river_deposited_solid_m3': math.fsum(r['deposited_m3'] for r in diag.values()),
        'node_exchange': hc.summarize(diag), 'hydraulic_capacity_rule': identity,
        'outlet_delivery': items, 'outlet_water': water_items, 'mouth_update': mouth_update, 'avulsion': avulsion,
        **({'floodplain': flood_totals} if flood is not None else {}), 'updated_progress': p}
