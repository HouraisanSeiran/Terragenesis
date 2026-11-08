"""Finite overbank exchange on a shared marine sediment state.

This optional building block treats channel stage and throughflow as boundary
conditions. It does not manufacture flood water, new sediment or terrain.
"""
from dataclasses import dataclass, asdict, replace
import math
import numpy as np


@dataclass(frozen=True)
class TidalConfig:
    amplitude_m: float = .5
    phase_count: int = 4


@dataclass(frozen=True)
class FloodplainConfig:
    exchange_fraction: float = .05
    settling_velocity_m_s: float = .0001
    residence_s: float = 3600.
    max_lateral_distance_m: float = 400.
    max_solid_fraction: float = .01


def overbank_exchange(state, channel_cells, stages_m, water_m3, *, config=FloodplainConfig(), excluded_cells=()):
    """Divert bounded water and mobile sediment to flooded neighbouring cells.

    Channel stage is prescribed at each cell; flood water is returned after
    residence. Sediment that does not settle remains in the receiving cell's
    stranded inventory until an explicitly wet process releases it.
    """
    values = [water_m3, config.exchange_fraction, config.settling_velocity_m_s,
              config.residence_s, config.max_lateral_distance_m, config.max_solid_fraction]
    if (not np.isfinite(values).all() or water_m3 < 0 or not 0 <= config.exchange_fraction <= 1
            or min(config.settling_velocity_m_s, config.residence_s, config.max_lateral_distance_m) < 0
            or not 0 <= config.max_solid_fraction <= 1):
        raise ValueError('invalid overbank parameters')
    if len(channel_cells) != len(stages_m) or not np.isfinite(stages_m).all():
        raise ValueError('invalid channel stages')
    cells = [tuple(map(int, c)) for c in channel_cells]
    if len(set(cells)) != len(cells) or any(not (0 <= r < state.bed_m.shape[0] and 0 <= c < state.bed_m.shape[1]) or not state.valid_mask[r,c] for r,c in cells):
        raise ValueError('invalid channel cell')
    stock = state.bed_solid_m3.copy()
    mobile = state.mobile_solid_m3.copy()
    stranded = state.stranded_solid_m3.copy()
    bed = state.bed_m
    occupied = set(cells) | {tuple(c) for c in excluded_cells}
    # Each flood search has its own stage and finite spatial neighbourhood.
    # A second donor cannot provide a route across the first donor's bank.
    from collections import deque
    radius = int(math.ceil(config.max_lateral_distance_m / state.spacing_m))
    donor_targets = {}
    for donor, stage in zip(cells, stages_m):
        if stage <= bed[donor]:
            continue
        queue = deque([donor])
        seen = {donor}
        targets = []
        while queue:
            r, c = queue.popleft()
            for dr, dc in ((-1, 0), (0, -1), (0, 1), (1, 0)):
                target = (r + dr, c + dc)
                if target in seen:
                    continue
                seen.add(target)
                tr, tc = target
                if not (0 <= tr < bed.shape[0] and 0 <= tc < bed.shape[1]):
                    continue
                if (abs(tr-donor[0]) > radius or abs(tc-donor[1]) > radius
                        or math.hypot(tr-donor[0], tc-donor[1]) * state.spacing_m > config.max_lateral_distance_m
                        or not state.valid_mask[target] or bed[target] >= stage
                        or target in occupied):
                    continue
                queue.append(target)
                targets.append(target)
        if targets:
            donor_targets[donor] = (float(stage), targets)
    if not donor_targets or not water_m3:
        return state, {'diverted_water_m3': 0., 'returned_water_m3': 0.,
                       'deposited_solid_m3': 0., 'stranded_solid_m3': 0., 'rewetted_solid_m3': 0.}
    # Split the single throughflow budget once, not once per river node.
    remaining_water = water_m3 * config.exchange_fraction
    deposited = parked = rewetted = used_water = new_solid = 0.
    wet_fraction = np.zeros(bed.shape)
    donors_left = len(donor_targets)
    for donor, (stage, targets) in donor_targets.items():
        donor_water = remaining_water / donors_left
        donors_left -= 1
        remaining_water -= donor_water
        capacity_left = donor_water * config.max_solid_fraction
        available = min(mobile[donor] * config.exchange_fraction, capacity_left)
        initial_water = donor_water
        for target in targets:
            depth = max(stage - bed[target], 0.)
            volume = depth * state.spacing_m**2 * (1. - wet_fraction[target])
            water = min(donor_water, volume)
            if water <= 0:
                continue
            fraction = water / (depth * state.spacing_m**2)
            wet_fraction[target] += fraction
            portion = min(available, capacity_left, available * water / max(donor_water, water))
            available -= portion
            new_solid += portion
            capacity_left -= portion
            mobile[donor] -= portion
            # Only the fraction actually rewetted can release historical stock.
            old = min(stranded[target] * min(1., fraction), max(water * config.max_solid_fraction - portion, 0.))
            stranded[target] -= old
            rewetted += old
            amount = portion + old
            settled = amount * (-math.expm1(-config.settling_velocity_m_s * config.residence_s / max(depth, .01)))
            room = max(stage - (state.base_bed_m[target] + stock[target] / (state.spacing_m**2 * (1-state.porosity[target]))), 0.) * state.spacing_m**2 * (1-state.porosity[target])
            placed = min(settled, room)
            stock[target] += placed
            stranded[target] += amount - placed
            deposited += placed
            parked += portion - min(portion, placed)
            donor_water -= water
            used_water += water
            if donor_water <= 0:
                break
        remaining_water += donor_water
    return replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile, stranded_solid_m3=stranded), {
        'diverted_water_m3': used_water, 'returned_water_m3': used_water,
        'deposited_solid_m3': deposited, 'stranded_solid_m3': parked,
        'rewetted_solid_m3': rewetted, 'new_solid_m3': new_solid, 'wet_area_m2': float(wet_fraction.sum() * state.spacing_m**2),
        'parameters': asdict(config)}



def open_deposited_path(state, path, target_bed_m):
    """Lower a D4 path only through existing solid deposits; retain all cuts locally."""
    cells=[tuple(map(int,c)) for c in path]
    if not cells or len(set(cells)) != len(cells) or not np.isfinite(target_bed_m):
        raise ValueError('invalid channel path')
    if any(abs(a[0]-b[0])+abs(a[1]-b[1]) != 1 for a,b in zip(cells,cells[1:])):
        raise ValueError('path must be D4 connected')
    stock=state.bed_solid_m3.copy(); mobile=state.mobile_solid_m3.copy(); cut=0.
    for cell in cells:
        if not (0 <= cell[0] < stock.shape[0] and 0 <= cell[1] < stock.shape[1]) or not state.valid_mask[cell]:
            raise ValueError('invalid path cell')
        if state.base_bed_m[cell] > target_bed_m:
            raise ValueError('path requires cutting geological base')
        area=state.spacing_m**2*(1-state.porosity[cell])
        amount=min(stock[cell], max(state.bed_m[cell]-target_bed_m,0.)*area)
        stock[cell]-=amount; mobile[cell]+=amount; cut+=amount
    return replace(state,bed_solid_m3=stock,mobile_solid_m3=mobile), {'excavated_solid_m3':float(cut), 'path':[list(c) for c in cells], 'target_bed_m':float(target_bed_m)}


def advance_event(state, progress, duration_s, marine_config, *, input_id, hydraulic_config,
                  inlet_solid_rate_m3_s, floodplain_config=FloodplainConfig(),
                  capacity_concentration=.01, active_layer_m=.5, max_velocity_m_s=2.):
    """Advance a physical event and one finite end-stage overbank exchange.

    The overbank calculation is an end-stage approximation, not a resolved
    hydrograph. Both steps use the same solid inventory and physical clock.
    """
    from .coastal_delta_branching import advance_river_event, _update_activity, _record
    result, report = advance_river_event(state, progress, duration_s, replace(marine_config, same_cell_wet_dry=True),
        input_id=input_id, hydraulic_config=hydraulic_config,
        inlet_solid_rate_m3_s=inlet_solid_rate_m3_s,
        capacity_concentration=capacity_concentration, active_layer_m=active_layer_m,
        max_velocity_m_s=max_velocity_m_s)
    p=report['updated_progress']; hydraulic=p['river_hydraulics']
    before_flood = result
    cells=[node[:2] for node in hydraulic['nodes']]
    stages=[node[2] for node in hydraulic['nodes']]
    result, flood=overbank_exchange(result,cells,stages,report['delivered_water_m3'],config=floodplain_config)
    if 'integrated' in p:
        _refresh_geometry(before_flood, result, p)
    _update_activity(result,p,hydraulic['sea_level_m'],input_id+':floodplain',hydraulic_config)
    p['history'].append({'event':'floodplain_exchange','input_id':input_id,**flood})
    p['history'].append({'event':'physical_forcing','input_id':input_id,'marine':asdict(marine_config),'hydraulic':asdict(hydraulic_config),'solid_rate_m3_s':inlet_solid_rate_m3_s})
    result=_record(result,p)
    report['updated_progress']=p; report['floodplain']=flood
    return result, report


def initialize(state, routes, metadata, *, input_id="integrated-formation",
               discharge_m3_s=150., solid_rate_m3_s=.08):
    """Bind a source state and its prepared subgrid route geometry.

    Candidate branches are stored as candidates, not active distributaries.
    The source identity and route metadata must agree. Historical excavation
    is geometry only and never a sediment input.
    """
    import json
    from . import coastal_delta_branching as branching
    if metadata.get('source_identity') != state.source_identity:
        raise ValueError('route and source identity mismatch')
    if not input_id or not np.isfinite([discharge_m3_s, solid_rate_m3_s]).all() or discharge_m3_s <= 0 or solid_rate_m3_s < 0:
        raise ValueError('invalid scenario')
    main = np.asarray(routes['main_cells_zx'], dtype=int)
    if main.ndim != 2 or main.shape[1] != 2 or len(main) < 2:
        raise ValueError('invalid route')
    if np.any(np.abs(np.diff(main, axis=0)).sum(axis=1) != 1):
        raise ValueError('route must be D4 connected')
    if np.any(main < 0) or np.any(main[:, 0] >= state.bed_m.shape[0]) or np.any(main[:, 1] >= state.bed_m.shape[1]):
        raise ValueError('route outside source')
    sections = {}
    for name in ('section_bed_m', 'section_bank_m', 'section_width_m', 'section_stage_m'):
        values = np.asarray(routes[name], float)
        if values.shape != (len(main),) or not np.isfinite(values).all():
            raise ValueError('invalid section geometry')
        sections[name] = values.tolist()
    if np.any(np.asarray(sections['section_width_m']) <= 0):
        raise ValueError('invalid section width')
    offsets = np.asarray(routes['branch_offsets'], int)
    packed = np.asarray(routes['branch_cells_zx'], int)
    if offsets.ndim != 1 or not len(offsets) or offsets[0] != 0 or offsets[-1] != len(packed) or np.any(np.diff(offsets) < 0):
        raise ValueError('invalid candidate offsets')
    candidates = [packed[offsets[i]:offsets[i+1]].tolist() for i in range(len(offsets)-1)]
    p = branching.start(state, {'trunk': main.tolist(), 'fork_indices': [], 'branches': []},
                        input_id=input_id, discharge_m3_s=discharge_m3_s,
                        solid_rate_m3_s=max(solid_rate_m3_s, 1e-300))
    p['solid_rate_m3_s'] = solid_rate_m3_s
    p['shares'] = [1.]
    p['hydraulic_sections'] = {'nodes': [[int(c[0]), int(c[1]), float(b), float(w), max(float(bank), float(b))] for c, b, w, bank in zip(main, sections['section_bed_m'], sections['section_width_m'], sections['section_bank_m'])]}
    p['integrated'] = {'algorithm': 'integrated-steady-v1', 'source_identity': state.source_identity,
        'route_data_sha256': metadata.get('data_sha256'), 'control': metadata.get('control'),
        'route_metadata': json.loads(json.dumps(metadata)), 'sections': sections,
        'reference_width_m': list(sections['section_width_m']),
        'candidate_routes': candidates, 'equivalent_water_m3': 0.,
        'accepted_water_m3': 0., 'pending_water_m3': 0., 'pending_solid_m3': 0.,
        'river_deposited_solid_m3': 0., 'mouth_delivered_solid_m3': 0.,
        'marine_deposited_solid_m3': 0., 'consumed_year_inputs': [],
        'assumption': 'steady interval transport; no transient floodplain storage'}
    if 'owner_fine_area_fraction' in routes:
        fraction = np.asarray(routes['owner_fine_area_fraction'], float)
        if fraction.shape != state.bed_m.shape or np.any((fraction < 0) | (fraction > 1)):
            raise ValueError('invalid owner fractions')
        owner = []
        for r, c in np.argwhere(fraction > 0):
            stocks = []
            for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
                fine = float(routes['owner_fine_' + field][r,c])
                outer = float(routes['owner_outer_' + field][r,c])
                if not np.isclose(fine + outer, getattr(state, field)[r,c], rtol=1e-10, atol=1e-7):
                    raise ValueError('owner stocks do not partition source')
                stocks.append(fine)
            owner.append([int(r), int(c), float(fraction[r,c]), *stocks,
                float(routes['owner_fine_base_bed_m'][r,c]),
                float(routes['owner_outer_base_bed_m'][r,c]),
                float(routes['owner_geometry_difference_bulk_m3'][r,c])])
        p['integrated']['owner_cells'] = owner
        p['integrated']['owner_assumption'] = 'area-mixed changes; fine plus outer always equals common stock'
    return state, p


def advance_years(state, progress, years, *, input_id, hydraulic_result=None, hydraulic_config=None,
                  marine_config=None, river_deposition_fraction=.01, floodplain_config=FloodplainConfig(),
                  tidal_config=None, step_years=1., _parameter_sea_level=None):
    """Route a finite equivalent interval through a supplied hydraulic solution.

    `hydraulic_result` follows the existing solve result (accepted Q, route Q,
    nodes and active). The solution is evaluated by the caller for this step;
    no historic packet or physical seconds are replayed. A separate call is
    required after geometry or tide changes.
    """
    import json
    import networkx as nx
    from . import coastal_delta_branching as branching
    from .coastal_delta_plain import _park_same_cell
    from .coastal_marine_longterm import advance as marine_advance, LongtermConfig
    from .surface_rivers.formative_section import section_from_routed_budget
    branching._validate(state, progress)
    if (not input_id or not np.isfinite([years, step_years, river_deposition_fraction]).all()
            or years <= 0 or not 0 < step_years <= 1 or not 0 <= river_deposition_fraction <= 1
            or input_id in progress['integrated']['consumed_year_inputs']
            or any(record['input_id'] == input_id for record in state.consumed_packets)):
        raise ValueError('invalid or duplicate annual input')
    if tidal_config is not None:
        if (not isinstance(tidal_config, TidalConfig) or not np.isfinite(tidal_config.amplitude_m)
                or tidal_config.amplitude_m < 0 or not isinstance(tidal_config.phase_count, int)
                or not 4 <= tidal_config.phase_count <= 8 or hydraulic_config is None
                or hydraulic_result is not None or marine_config is None):
            raise ValueError('invalid tidal forcing')
        count = int(math.ceil(years / step_years - 1e-12))
        existing = set(progress['integrated']['consumed_year_inputs']) | {record['input_id'] for record in state.consumed_packets}
        if any(f'{input_id}:step:{step}:phase:{phase}' in existing
               for step in range(count) for phase in range(tidal_config.phase_count)):
            raise ValueError('annual phase input ID conflicts with checkpoint')
        tidal_identity = asdict(tidal_config) | {'step_years': step_years}
        old = progress['integrated'].get('tidal_config')
        if old is not None and old != tidal_identity:
            raise ValueError('tidal parameters do not match checkpoint')
        current, cp = state, json.loads(json.dumps(progress))
        cp['integrated']['tidal_config'] = tidal_identity
        remaining = years
        step = 0
        while remaining > 1e-12:
            interval = min(step_years, remaining)
            for phase in range(tidal_config.phase_count):
                level = marine_config.sea_level_m + tidal_config.amplitude_m * math.sin(2*math.pi*(phase+.5)/tidal_config.phase_count)
                current, cp = advance_years(current, cp, interval/tidal_config.phase_count,
                    input_id=f'{input_id}:step:{step}:phase:{phase}', hydraulic_config=hydraulic_config,
                    marine_config=replace(marine_config, sea_level_m=level),
                    river_deposition_fraction=river_deposition_fraction, floodplain_config=floodplain_config,
                    _parameter_sea_level=marine_config.sea_level_m)
            from .coastal_delta_avulsion import extend_mouths, activate_candidate
            current, cp, mean_mouth = extend_mouths(current, cp, hydraulic_config=hydraulic_config,
                sea_level_m=marine_config.sea_level_m)
            cp['history'].append({'event': 'shoreline_extension', **mean_mouth})
            current = branching._record(current, cp)
            current, cp, _ = activate_candidate(current, cp, hydraulic_config=hydraulic_config,
                sea_level_m=marine_config.sea_level_m)
            current = branching._record(current, cp)
            remaining -= interval
            step += 1
        from .coastal_delta_branching import _update_activity
        _update_activity(current, cp, marine_config.sea_level_m, input_id+':mean', hydraulic_config)
        cp['integrated']['consumed_year_inputs'].append(input_id)
        return branching._record(current, cp), cp
    if years > 1:
        if hydraulic_config is None or hydraulic_result is not None:
            raise ValueError('multi-year advancement requires fresh hydraulic solves')
        if input_id in progress['integrated']['consumed_year_inputs']:
            raise ValueError('duplicate annual input')
        remaining = years
        current, current_progress = state, progress
        step = 0
        while remaining > 1e-12:
            interval = min(1., remaining)
            current, current_progress = advance_years(current, current_progress, interval,
                input_id=f'{input_id}:step:{step}', hydraulic_config=hydraulic_config,
                marine_config=marine_config, river_deposition_fraction=river_deposition_fraction,
                floodplain_config=floodplain_config)
            remaining -= interval
            step += 1
        current_progress['integrated']['consumed_year_inputs'].append(input_id)
        return branching._record(current, current_progress), current_progress
    if (not input_id or any(record['input_id'] == input_id for record in state.consumed_packets) or input_id in progress['integrated']['consumed_year_inputs']
            or not np.isfinite([years, river_deposition_fraction]).all()
            or years <= 0 or not 0 <= river_deposition_fraction <= 1):
        raise ValueError('invalid or duplicate annual input')
    p = json.loads(json.dumps(progress))
    info = p['integrated']
    marine_parameters = None if marine_config is None else asdict(marine_config)
    if marine_parameters is not None and _parameter_sea_level is not None:
        marine_parameters['sea_level_m'] = _parameter_sea_level
    parameters = {'river_deposition_fraction': river_deposition_fraction, 'floodplain': asdict(floodplain_config), 'marine': marine_parameters, 'hydraulic': None if hydraulic_config is None else asdict(hydraulic_config)}
    if 'parameters' in info and info['parameters'] != parameters:
        raise ValueError('annual parameters do not match checkpoint')
    info['parameters'] = parameters
    if hydraulic_config is not None and 'avulsion_baseline_sections' not in p:
        from .coastal_delta_avulsion import activate_candidate
        state, p, _ = activate_candidate(state, p, hydraulic_config=hydraulic_config,
            sea_level_m=0. if marine_config is None else marine_config.sea_level_m)
        info = p['integrated']
    if hydraulic_result is None:
        if hydraulic_config is None:
            raise ValueError('hydraulic solution or configuration required')
        from .coastal_delta_hydraulics import solve
        hydraulic_result = solve(state, p, 0. if marine_config is None else marine_config.sea_level_m, hydraulic_config)
    q = float(p['discharge_m3_s'])
    accepted = float(hydraulic_result['accepted_q_m3_s'])
    route_q = np.asarray(hydraulic_result['route_q_m3_s'], float)
    if (not np.isfinite(accepted) or not 0 <= accepted <= q or route_q.shape != (len(p['routes']),)
            or not np.isfinite(route_q).all() or (route_q < 0).any()
            or not np.isclose(route_q.sum(), accepted)):
        raise ValueError('invalid hydraulic allocation')
    duration = years * 365.25 * 86400.
    supply = p['solid_rate_m3_s'] * duration
    delivered = supply * accepted / q
    pending = supply - delivered
    stock = state.bed_solid_m3.copy()
    mobile = state.mobile_solid_m3.copy()
    graph = nx.DiGraph()
    edge_q = {}
    mouth_q = {}
    for route, flow in zip(p['routes'], route_q):
        if flow <= 0:
            continue
        cells = [tuple(c) for c in route]
        nx.add_path(graph, cells)
        for a, b in zip(cells, cells[1:]):
            edge_q[a, b] = edge_q.get((a, b), 0.) + float(flow)
        mouth_q[cells[-1]] = mouth_q.get(cells[-1], 0.) + float(flow)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError('route graph contains a cycle')
    flux = {cell: 0. for cell in graph}
    inlet = tuple(p['routes'][0][0])
    if accepted:
        flux[inlet] += delivered
    deposition = 0.
    mouth_delivered = 0.
    stranded = state.stranded_solid_m3.copy()
    flood = {'deposited_solid_m3': 0., 'diverted_water_m3': 0., 'rewetted_solid_m3': 0., 'new_solid_m3': 0.}
    main_index = {tuple(n[:2]): i for i, n in enumerate(p['hydraulic_sections']['nodes'][:len(info['sections']['section_bed_m'])])}
    section = info['sections']
    section_nodes = {tuple(node[:2]): node for node in p['hydraulic_sections']['nodes']}
    stage_by_cell = {tuple(n[:2]): float(n[2]) for n in hydraulic_result.get('nodes', [])}
    for cell in nx.topological_sort(graph):
        incoming = flux[cell]
        if incoming > 0 and cell in stage_by_cell:
            temporary_mobile = mobile.copy()
            temporary_mobile[cell] = incoming
            temporary = replace(state, bed_solid_m3=stock, mobile_solid_m3=temporary_mobile, stranded_solid_m3=stranded)
            temporary, exchange = overbank_exchange(temporary, [cell], [stage_by_cell[cell]],
                accepted * duration / max(len(graph), 1), config=floodplain_config, excluded_cells=graph)
            taken = temporary_mobile[cell] - temporary.mobile_solid_m3[cell]
            incoming -= taken
            stock, stranded = temporary.bed_solid_m3, temporary.stranded_solid_m3
            mobile = temporary.mobile_solid_m3.copy()
            mobile[cell] = state.mobile_solid_m3[cell]
            for key in flood:
                flood[key] += exchange.get(key, 0.)
        settled = incoming * river_deposition_fraction
        if cell in main_index:
            i = main_index[cell]
            ceiling = stage_by_cell.get(cell, section['section_stage_m'][i])
            accommodation = max(ceiling - section['section_bed_m'][i], 0.) * section['section_width_m'][i] * state.spacing_m * (1-state.porosity[cell])
            settled = min(settled, accommodation)
        elif cell in section_nodes:
            node = section_nodes[cell]
            ceiling = stage_by_cell.get(cell, node[2])
            accommodation = max(ceiling-node[2], 0.) * node[3] * state.spacing_m * (1-state.porosity[cell])
            settled = min(settled, accommodation)
        stock[cell] += settled
        deposition += settled
        outgoing = incoming - settled
        successors = list(graph.successors(cell))
        outgoing_q = sum(edge_q[cell, dst] for dst in successors) + mouth_q.get(cell, 0.)
        if outgoing_q <= 0:
            mobile[cell] += outgoing
        else:
            for dst in successors:
                flux[dst] += outgoing * edge_q[cell, dst] / outgoing_q
            mouth = outgoing * mouth_q.get(cell, 0.) / outgoing_q
            mobile[cell] += mouth
            mouth_delivered += mouth
        if cell in main_index and incoming > 0:
            i = main_index[cell]
            updated = section_from_routed_budget(outgoing_q, .5, .5, 0., .5,
                incoming_solid_m3=incoming, external_solid_m3=0., capacity_solid_m3=incoming,
                eroded_loose_solid_m3=0., eroded_rock_m3=0., deposited_solid_m3=settled,
                reference_discharge_m3_s=max(outgoing_q, 1e-9),
                reference_width_m=info['reference_width_m'][i], max_width_m=state.spacing_m)
            old_width = section['section_width_m'][i]
            section['section_width_m'][i] = info['reference_width_m'][i] * float(updated.width_m / updated.baseline_width_m)
            section_nodes[cell][3] = section['section_width_m'][i]
    current = replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile, stranded_solid_m3=stranded)
    marine_report = {'deposited_solid_m3': 0., 'exported_solid_m3': 0.}
    if marine_config is not None:
        if not isinstance(marine_config, LongtermConfig):
            raise ValueError('invalid marine forcing')
        # Channel stocks remain in their own cells while the ocean operates.
        held = np.zeros_like(mobile)
        for cell in graph:
            if cell not in mouth_q:
                held[cell] = current.mobile_solid_m3[cell]
        current = replace(current, mobile_solid_m3=current.mobile_solid_m3-held)
        current, marine_report = marine_advance(current, duration, marine_config, park_and_release=_park_same_cell)
        current = replace(current, mobile_solid_m3=current.mobile_solid_m3+held, time_s=state.time_s)
    _refresh_geometry(state, current, p)
    info['equivalent_water_m3'] += q*duration
    info['accepted_water_m3'] += accepted*duration
    info['pending_water_m3'] += (q-accepted)*duration
    info['pending_solid_m3'] += pending
    info['river_deposited_solid_m3'] += deposition
    info['mouth_delivered_solid_m3'] += mouth_delivered
    info['marine_deposited_solid_m3'] += marine_report['deposited_solid_m3']
    info['floodplain_deposited_solid_m3'] = info.get('floodplain_deposited_solid_m3', 0.) + flood['deposited_solid_m3']
    info['consumed_year_inputs'].append(input_id)
    p['formation_undelivered_water_m3'] = info['pending_water_m3']
    p['formation_undelivered_solid_m3'] = info['pending_solid_m3']
    p['supply_solid_m3'] += supply
    p['years'] += years
    p['history'].append({'event': 'integrated_years', 'input_id': input_id, 'years': years,
        'accepted_q_m3_s': accepted, 'route_q_m3_s': route_q.tolist(),
        'river_deposited_solid_m3': deposition, 'mouth_delivered_solid_m3': mouth_delivered,
        'marine_deposited_solid_m3': marine_report['deposited_solid_m3'], 'floodplain': flood})
    current = branching._record(current, p)
    if hydraulic_config is not None:
        from .coastal_delta_avulsion import activate_candidate, extend_mouths
        level = 0. if marine_config is None else marine_config.sea_level_m
        current, p, mouth_report = extend_mouths(current, p, hydraulic_config=hydraulic_config, sea_level_m=level)
        p['history'].append({'event': 'shoreline_extension', **mouth_report})
        current = branching._record(current, p)
        current, p, _ = activate_candidate(current, p, hydraulic_config=hydraulic_config, sea_level_m=level)
        current = branching._record(current, p)
    return current, p


def _refresh_geometry(before, after, progress):
    """Reflect net physical-event sediment changes in section and owner geometry."""
    info = progress['integrated']
    section = info['sections']
    original_count = len(section['section_bed_m'])
    for i, node in enumerate(progress['hydraulic_sections']['nodes']):
        cell = tuple(node[:2])
        delta = float(after.bed_solid_m3[cell] - before.bed_solid_m3[cell])
        # Stock changes are area-mixed, as in the owner partition: dividing the
        # fine share by its fine area gives the full-cell equivalent rise.
        area = before.spacing_m**2 * (1-before.porosity[cell])
        node[2] += delta / area
        node[4] = max(node[4], node[2])
        if i < original_count:
            section['section_bed_m'][i] = node[2]
            section['section_width_m'][i] = node[3]
            section['section_bank_m'][i] = node[4]
    for row in info.get('owner_cells', []):
        r, c, fraction = row[:3]
        for index, field in enumerate(('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')):
            old = float(getattr(before, field)[r, c])
            new = float(getattr(after, field)[r, c])
            row[3+index] = min(new, max(0., row[3+index] + (new-old)*fraction))


def save(prefix, state, progress):
    """Save a hash-bound state and JSON progress for continuation."""
    from .coastal_delta_product import save_checkpoint
    from .coastal_delta_branching import _validate
    _validate(state, progress)
    save_checkpoint(prefix, state, progress)


def load(prefix):
    """Load and validate a saved integrated state and progress."""
    from .coastal_delta_product import load_checkpoint
    from .coastal_delta_branching import _validate
    state, progress = load_checkpoint(prefix)
    _validate(state, progress)
    if progress.get('integrated', {}).get('source_identity') != state.source_identity:
        raise ValueError('checkpoint source identity mismatch')
    return state, progress
