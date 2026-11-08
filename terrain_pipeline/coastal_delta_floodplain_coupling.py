"""Finite bank exchange between node-owned rivers and persistent floodplain water.

The river is a steady DAG, the floodplain a no-momentum D4 storage grid. Bank
fluxes use the beginning-of-substep head and are then imposed as river sinks
and sources. This is an explicit reduced coupling, not full shallow water.
"""
from collections import Counter
from dataclasses import asdict, dataclass, replace
import math

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class FloodplainCouplingConfig:
    max_exchange_fraction: float = .08
    bank_discharge_coefficient: float = 1.5
    max_solid_fraction: float = .01
    max_lateral_distance_m: float = 2500.
    protected_elevation_m: float = 45.
    roughness: float = .06
    settling_velocity_m_s: float = .0001
    max_step_s: float = 60.

    def __post_init__(self):
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in asdict(self).values()):
            raise ValueError('floodplain parameters must be finite numbers')
        if (not 0 < self.max_exchange_fraction <= .2 or not 0 < self.max_solid_fraction <= 1
                or min(self.bank_discharge_coefficient, self.max_lateral_distance_m,
                       self.roughness, self.max_step_s) <= 0 or self.settling_velocity_m_s < 0):
            raise ValueError('invalid floodplain coupling parameters')

    def identity(self):
        return dict(algorithm='finite-bank-d4-storage-settling-v1', **asdict(self))


def initialize_water(state, progress, config):
    if not isinstance(config, FloodplainCouplingConfig):
        raise ValueError('invalid floodplain configuration')
    if progress.get('hydraulics_backend') != 'physical_edge_graph':
        raise ValueError('floodplain exchange requires physical-edge river hydraulics')
    identity = config.identity()
    saved = progress.get('floodplain_coupling')
    if saved is not None and saved['identity'] != identity:
        raise ValueError('floodplain identity differs from saved case')
    water = state.floodplain_water_m3
    if water is None:
        water = np.zeros(state.base_bed_m.shape)
        state = replace(state, floodplain_water_m3=water)
    if (water.shape != state.base_bed_m.shape or not np.isfinite(water).all()
            or (water < 0).any() or (water[~state.valid_mask] != 0).any()):
        raise ValueError('invalid persistent floodplain water')
    if saved is None:
        progress['floodplain_coupling'] = dict(identity=identity,
            initial_water_m3=float(water.sum()), initial_marine_water_input_m3=state.water_input_m3,
            accepted_river_water_m3=0., bank_out_water_m3=0., bank_return_water_m3=0.,
            bank_out_solid_m3=0., bank_return_solid_m3=0., deposited_solid_m3=0.,
            receiving_water_m3=0., completed_steps=0,
            approximation='explicit bank heads; steady river with actual lateral continuity; no-momentum D4 floodplain')
    return state, progress


def bank_layout(state, progress, sea_level_m, config):
    """Use actual footprint boundaries; no centerline-distance levee painting."""
    shape = state.base_bed_m.shape
    owned = np.zeros(shape, bool)
    owner = {}
    for r, c, parts in progress['node_footprints']:
        for pr, pc, fraction, *_ in parts:
            cell = (int(pr), int(pc))
            owned[cell] = True
            candidate = (float(fraction), (-int(r), -int(c)))
            previous = owner.get(cell)
            if previous is None or candidate > previous[0]:
                owner[cell] = (candidate, (int(r), int(c)))
    distance = ndimage.distance_transform_edt(~owned, sampling=state.spacing_m)
    bed = state.bed_m
    allowed = (state.valid_mask & ~owned & (bed >= sea_level_m)
               & (bed < config.protected_elevation_m) & (distance <= config.max_lateral_distance_m))
    if state.floodplain_water_m3 is not None:
        retained = state.floodplain_water_m3 > 0
        if np.any(retained & (owned | ~state.valid_mask)):
            raise ValueError('floodplain water overlaps a channel footprint or invalid cells')
        allowed |= retained
    faces = []
    for cell, (_, node) in sorted(owner.items()):
        r, c = cell
        for dr, dc in ((-1, 0), (0, -1), (0, 1), (1, 0)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < shape[0] and 0 <= cc < shape[1] and allowed[rr, cc]:
                faces.append((node, (rr, cc), max(float(bed[cell]), float(bed[rr, cc]))))
    return dict(allowed=allowed, faces=faces)


def plan_exchange(state, progress, layout, duration_s, config):
    """Plan once per physical step; shared source and receiver limits apply."""
    hydraulic = progress['river_hydraulics']
    accepted = float(hydraulic['accepted_q_m3_s'])
    nodes = {tuple(row[:2]): row for row in hydraulic['nodes']}
    water = state.floodplain_water_m3
    area = state.spacing_m ** 2
    bed = state.bed_m
    counts = Counter(cell for node, cell, _ in layout['faces'] if node in nodes)
    sinks, sources = [], []
    for node, cell, crest in layout['faces']:
        if node not in nodes:
            continue
        stage = float(nodes[node][2])
        flood_stage = float(bed[cell] + water[cell] / area)
        head = stage - max(crest, flood_stage)
        if head > 0 and accepted > 0:
            volume = min(config.bank_discharge_coefficient * state.spacing_m * head ** 1.5 * duration_s,
                         head * area / counts[cell])
            sinks.append([node, cell, volume])
        reverse = flood_stage - max(crest, stage)
        if reverse > 0 and water[cell] > 0:
            volume = min(config.bank_discharge_coefficient * state.spacing_m * reverse ** 1.5 * duration_s,
                         water[cell] / counts[cell], reverse * area / counts[cell])
            sources.append([node, cell, volume])
    node_totals = {}
    for node, _, volume in sinks:
        node_totals[node] = node_totals.get(node, 0.) + volume
    for row in sinks:
        node = row[0]
        cap = config.max_exchange_fraction * float(nodes[node][4]) * duration_s
        row[2] *= min(1., cap / node_totals[node])
    total = math.fsum(row[2] for row in sinks)
    scale = min(1., config.max_exchange_fraction * accepted * duration_s / total) if total else 0.
    for row in sinks:
        row[2] *= scale
    fractions, return_q = {}, {}
    for node, _, volume in sinks:
        fractions[node] = fractions.get(node, 0.) + volume / (accepted * duration_s)
    for node, _, volume in sources:
        return_q[node] = return_q.get(node, 0.) + volume / duration_s
    return dict(sinks=sinks, sources=sources, base_accepted_q_m3_s=accepted,
        river=dict(sink_fraction=[[*node, fraction] for node, fraction in sorted(fractions.items()) if fraction > 0],
                   source_q_m3_s=[[*node, value] for node, value in sorted(return_q.items()) if value > 0]))


def apply_returns(state, progress, pool, plan):
    """Debit actual stored water/mobile once and credit the chosen river node."""
    water = state.floodplain_water_m3.copy()
    mobile = state.mobile_solid_m3.copy()
    solid = 0.
    for node, cell, volume in plan['sources']:
        amount = min(float(mobile[cell]), float(mobile[cell]) * volume / water[cell]) if water[cell] > 0 else 0.
        water[cell] -= volume
        mobile[cell] -= amount
        pool.add(node, 'mobile_solid_m3', amount)
        solid += amount
    # Node edits and outer edits are committed in order, avoiding shared owners.
    with_nodes, progress = pool.commit(state, progress)
    after = replace(with_nodes, floodplain_water_m3=water, mobile_solid_m3=with_nodes.mobile_solid_m3 + mobile - state.mobile_solid_m3)
    pool.apply_grid_changes(with_nodes, after)
    state, progress = pool.commit(after, progress)
    return state, progress, solid


def sink_edges(progress, plan, duration_s):
    base = plan['base_accepted_q_m3_s']
    accepted = progress['river_hydraulics']['accepted_q_m3_s']
    ratio = accepted / base if base > 0 else 0.
    edges = {}
    volumes = {}
    for node, cell, planned in plan['sinks']:
        volume = planned * ratio
        if volume <= 0:
            continue
        edges.setdefault(node, []).append(dict(to_zx=list(cell), discharge_m3_s=volume / duration_s))
        key = (node, cell)
        volumes[key] = volumes.get(key, 0.) + volume
    return edges, volumes


def spread_and_settle(state, progress, pool, plan, volumes, deliveries, layout, duration_s, config):
    from .coastal_delta_floodplain import advance_floodplain
    water = state.floodplain_water_m3.copy()
    mobile = state.mobile_solid_m3.copy()
    bank_solid = 0.
    marine_deliveries = []
    used = {}
    for mouth, destination, amount in deliveries:
        key = (mouth, destination)
        if key not in volumes:
            marine_deliveries.append((mouth, destination, amount))
            continue
        room = max(0., volumes[key] * config.max_solid_fraction - used.get(key, 0.))
        transferred = min(amount, room)
        used[key] = used.get(key, 0.) + transferred
        mobile[destination] += transferred
        bank_solid += transferred
        pool.add(mouth, 'mobile_solid_m3', amount - transferred)
    with_nodes, progress = pool.commit(state, progress)
    for (_, cell), volume in volumes.items():
        water[cell] += volume
    after = replace(with_nodes, floodplain_water_m3=water,
                    mobile_solid_m3=with_nodes.mobile_solid_m3 + mobile - state.mobile_solid_m3)
    pool.apply_grid_changes(with_nodes, after)
    state, progress = pool.commit(after, progress)
    area = state.spacing_m ** 2
    result = advance_floodplain(state.bed_m, water, state.mobile_solid_m3, state.stranded_solid_m3,
        area_m2=area, solid_area_m2=area * (1 - state.porosity), allowed_mask=layout['allowed'],
        spacing_m=state.spacing_m, duration_s=duration_s, roughness=config.roughness,
        settling_velocity_m_s=config.settling_velocity_m_s, max_step_s=config.max_step_s)
    after = replace(state, floodplain_water_m3=result['water_m3'],
        mobile_solid_m3=result['mobile_solid_m3'], stranded_solid_m3=result['stranded_solid_m3'],
        bed_solid_m3=state.bed_solid_m3 + result['deposited_solid_m3'])
    pool.apply_grid_changes(state, after)
    state, progress = pool.commit(after, progress)
    return state, progress, marine_deliveries, bank_solid, result['report'], float(result['deposited_solid_m3'].sum())


def water_evidence(state, progress):
    saved = progress.get('floodplain_coupling')
    if saved is None:
        return None
    water = state.floodplain_water_m3
    current = float(water.sum())
    receiving = state.water_input_m3 - saved['initial_marine_water_input_m3']
    return {**saved, 'retained_water_m3': current,
        'wet_cell_count': int(np.count_nonzero(water > 1e-6)),
        'maximum_water_depth_m': float(water.max() / state.spacing_m ** 2),
        'marine_received_water_m3': receiving,
        'water_residual_m3': saved['initial_water_m3'] + saved['accepted_river_water_m3'] - current - receiving}
