"""Optional, conservative distributary experiment over the shared marine stock.

Routes are D4-connected raster corridors, not resolved hydraulics. Depositional
obstruction and conveyance are game-scale proxies; velocities are prescribed.
"""
from dataclasses import asdict, replace
import json
import numpy as np
from scipy import ndimage
from .coastal_delta_product import _route, _width, _source_fingerprint
from .coastal_marine_sediment import classify_ocean
from .coastal_marine_longterm import advance, LongtermConfig


def start(state, network, *, input_id, discharge_m3_s, solid_rate_m3_s):
    if not input_id or min(discharge_m3_s, solid_rate_m3_s) <= 0:
        raise ValueError('invalid input')
    if any(r['input_id'] == input_id for r in state.consumed_packets):
        raise ValueError('input already consumed')
    trunk = [tuple(c) for c in network['trunk']]
    forks = network['fork_indices']
    routes = [trunk] + [trunk[:i+1] + [tuple(c) for c in p[1:]]
                        for i, p in zip(forks, network['branches'])]
    return {'input_id': input_id, 'discharge_m3_s': discharge_m3_s,
            'solid_rate_m3_s': solid_rate_m3_s, 'supply_solid_m3': 0.,
            'source_state_fingerprint': _source_fingerprint(state),
            'routes': [[list(c) for c in route] for route in routes],
            'shares': [.36, .34, .30], 'history': [], 'years': 0.,
            'assumptions': 'prescribed ocean velocity; route shares proxy water and solid flux; raster corridors are not resolved river widths'}



def _validate(state, progress):
    records = [r for r in state.consumed_packets if r['input_id'] == progress['input_id']]
    if len(records) > 1:
        raise ValueError('duplicate formation record')
    if records:
        if records[0].get('formation_progress') != progress:
            raise ValueError('formation progress does not match state')
    elif progress['years'] != 0 or _source_fingerprint(state) != progress['source_state_fingerprint']:
        raise ValueError('formation source state mismatch')


def _record(state, progress):
    inlet = progress['routes'][0][0]
    equivalent_water = progress['discharge_m3_s'] * progress['years'] * 365.25 * 86400
    record = {'input_id': progress['input_id'], 'source_id': 'branch-formation',
              'start_s': state.time_s-1., 'end_s': state.time_s, 'known': True,
              'row': inlet[0], 'col': inlet[1], 'direction_xz': [1., 0.],
              'water_m3': 0., 'solid_m3': progress['supply_solid_m3'],
              'pending_solid_m3': 0., 'delivered_water_m3': 0.,
              'delivered_solid_m3': progress['supply_solid_m3'],
              'record_kind': 'equivalent_geological_formation',
              'equivalent_water_m3': equivalent_water, 'formation_progress': progress}
    records = tuple(r for r in state.consumed_packets if r['input_id'] != progress['input_id']) + (record,)
    return replace(state, consumed_packets=records)


def segment_fluxes(progress):
    """Aggregate all outlet shares on shared directed D4 segments."""
    edges = {}
    for route, share in zip(progress['routes'], progress['shares']):
        for a, b in zip(route, route[1:]):
            key = (tuple(a), tuple(b))
            edges[key] = edges.get(key, 0.) + share
    return [{'from_zx': list(a), 'to_zx': list(b), 'share': share,
             'discharge_m3_s': progress['discharge_m3_s']*share,
             'solid_rate_m3_s': progress['solid_rate_m3_s']*share,
             'width_m': _width(progress['discharge_m3_s']*share, 0., 0.)}
            for (a,b), share in edges.items()]

def propose(state, reference, progress, *, sea_level_m=0., min_bar_rise_m=.1,
            min_share=.08, max_cut_m=1., radius_cells=6):
    """Find a new wet path when measured nearby deposition reduces conveyance.

    Compare the same cells against the reference and seek accessible actual
    shoreline cells. No target shape or predetermined pair of mouths is used.
    """
    ocean, shore = classify_ocean(state, sea_level_m)
    depth = np.maximum(sea_level_m-state.bed_m, 0.)
    rise = np.maximum(state.bed_m-reference.bed_m, 0.)
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    occupied = set(c for route in routes for c in route)
    rows, cols = np.indices(depth.shape)
    best = None
    for index, route in enumerate(routes):
        if progress['shares'][index] < 2*min_share or len(route) < 7:
            continue
        end = route[-1]
        near = (rows-end[0])**2+(cols-end[1])**2 <= radius_cells**2
        bar = float(np.max(np.where(near & state.valid_mask, rise, 0.)))
        mouth_cells = np.array(route[max(0, len(route)-6):])
        mouth_index = tuple(mouth_cells.T)
        reference_depth = np.maximum(sea_level_m-reference.bed_m[mouth_index], 0.)
        current_depth = depth[mouth_index]
        loss = float(np.percentile(reference_depth, 10) - np.percentile(current_depth, 10))
        # A nearby bar alone is not evidence that the old route has lost
        # conveyance. Require an actual decline on its control section.
        if bar < min_bar_rise_m or loss < min_bar_rise_m:
            continue
        for fork_index in range(max(2, len(route)-12), len(route)-3):
            fork = route[fork_index]
            dist = np.hypot(rows-fork[0], cols-fork[1])
            separation = np.hypot(rows-end[0], cols-end[1])
            # Candidate wet shoreline neighbors with a real shallow-water outlet.
            coast = ocean & ndimage.binary_dilation(shore)
            candidates = coast & (depth <= 4.) & (dist >= 4) & (dist <= radius_cells*2) & (separation >= 4)
            cut = np.maximum(state.bed_m-(sea_level_m-.35), 0.)
            near_land = ndimage.binary_dilation(state.valid_mask & (state.bed_m >= sea_level_m), iterations=2)
            allowed = state.valid_mask & near_land & (state.base_bed_m < sea_level_m-.35) & (cut <= max_cut_m) & ((ocean & (depth <= 4.)) | (cut > 0))
            for cell in occupied:
                allowed[cell] = False
                candidates[cell] = False
            allowed[fork] = True
            labels, _ = ndimage.label(allowed)
            candidates &= labels == labels[fork]
            # Both existing continuation and new route must have positive capacity.
            old_depth = depth[tuple(np.array(route[fork_index+1:]).T)]
            old_capacity = float(np.percentile(old_depth, 10))
            if old_capacity <= 0:
                continue
            cost = np.where(allowed, 1 + .5*cut + .3/(.3+depth), np.inf)
            rank = np.argsort(np.where(candidates, depth-.08*dist, -np.inf).ravel())[::-1]
            for flat in rank[:12]:
                end2 = tuple(map(int, np.unravel_index(flat, depth.shape)))
                if not candidates[end2]:
                    break
                try:
                    path = _route(cost, fork, end2)
                except ValueError:
                    continue
                if len(path) < 5 or sum(cut[c] > .01 for c in path) < 2:
                    continue
                excavation = {c: float(cut[c]) for c in path if cut[c] > 0}
                penalty = sum(excavation.values())/len(path)
                new_capacity = float(np.percentile([max(depth[c], .35) for c in path[1:]], 10))
                # Bar rise is an explicit prerequisite and contributes to the
                # advantage; length and excavation oppose new corridors.
                old_length = len(route)-fork_index
                score = loss + .25*(min(new_capacity, 2.)-min(old_capacity, 2.)) - .035*(len(path)-old_length) - penalty
                if score > 0 and (best is None or score > best[0]):
                    best = (score, index, fork_index, path, excavation, bar, old_capacity, new_capacity, loss)
    if best is None:
        return None
    score, index, fork_index, path, excavation, bar, old_capacity, new_capacity, loss = best
    return {'parent': index, 'fork_index': fork_index, 'path': [list(c) for c in path],
            'excavation': [[*c, v] for c, v in excavation.items()], 'bar_rise_m': bar,
            'old_capacity_depth_m': old_capacity, 'new_capacity_depth_m': new_capacity,
            'control_depth_loss_m': loss,
            'score': score, 'min_bar_rise_m': min_bar_rise_m}


def split(state, progress, proposal, *, min_share=.08):
    _validate(state, progress)
    p = json.loads(json.dumps(progress)); idx = proposal['parent']; fork = proposal['fork_index']
    old_share = p['shares'][idx]
    a, b = proposal['old_capacity_depth_m'], proposal['new_capacity_depth_m']
    if old_share < 2*min_share:
        raise ValueError('insufficient child discharge')
    new_share = float(np.clip(old_share*b/(a+b), min_share, old_share-min_share))
    stock = state.bed_solid_m3.copy(); mobile = state.mobile_solid_m3.copy()
    removed = 0.
    for r, c, depth in proposal['excavation']:
        amount = depth * state.spacing_m**2 * (1-state.porosity[r,c])
        if amount > stock[r,c] + 1e-7:
            raise ValueError('cut exceeds deposited stock')
        stock[r,c] -= amount; mobile[r,c] += amount; removed += amount
    p['routes'].append(p['routes'][idx][:fork+1] + proposal['path'][1:])
    p['shares'][idx] -= new_share; p['shares'].append(new_share)
    p['history'].append({'event': 'split', 'year': p['years'], 'proposal': proposal,
                         'excavated_solid_m3': removed, 'shares': list(p['shares'])})
    return _record(replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile), p), p


def advance_years(state, progress, years, forcing=LongtermConfig(), *, channel_min_depth_m=.35, max_formative_step_years=1.):
    if not np.isfinite(max_formative_step_years) or max_formative_step_years <= 0:
        raise ValueError('invalid formative step')
    if years <= 0:
        raise ValueError('invalid duration')
    _validate(state, progress)
    if not np.isfinite(channel_min_depth_m) or channel_min_depth_m <= 0:
        raise ValueError('invalid minimum depth')
    if 'forcing' in progress and progress['forcing'] != asdict(forcing):
        raise ValueError('formation forcing mismatch')
    if 'channel_min_depth_m' in progress and progress['channel_min_depth_m'] != channel_min_depth_m:
        raise ValueError('formation channel depth mismatch')
    if 'max_formative_step_years' in progress and progress['max_formative_step_years'] != max_formative_step_years:
        raise ValueError('formation step mismatch')
    p = json.loads(json.dumps(progress)); elapsed = 0.
    physical_time = state.time_s
    # Re-evaluate connectivity every at most one year: never relocate a future
    # dry source arbitrarily across cells. Inactive routes retain their share.
    while elapsed < years:
        step = min(max_formative_step_years, years-elapsed); seconds = step*365.25*86400
        ocean, _ = classify_ocean(state, forcing.sea_level_m)
        source = np.zeros(state.bed_m.shape); active = []
        for route, share in zip(p['routes'], p['shares']):
            cells = [tuple(c) for c in route]
            wet = all(ocean[c] for c in cells)
            active.append(wet)
            if wet:
                source[cells[-1]] += p['solid_rate_m3_s']*share
        # Closed outlets accumulate at the inlet only when it is itself wet.
        inactive = sum(s for s, wet in zip(p['shares'], active) if not wet)
        inlet = tuple(p['routes'][0][0])
        if inactive and not ocean[inlet]:
            raise ValueError('no wet inlet for inactive-route supply')
        source[inlet] += p['solid_rate_m3_s']*inactive
        if not all(active):
            raise ValueError('active route lacks wet connection')
        ceiling = np.full(state.bed_m.shape, forcing.sea_level_m)
        for route in p['routes']:
            for cell in route:
                cell = tuple(cell)
                ceiling[cell] = max(forcing.sea_level_m-channel_min_depth_m, state.bed_m[cell])
        state, _ = advance(state, seconds, forcing, source_rate_m3_s=source, bed_ceiling_m=ceiling)
        state = replace(state, time_s=physical_time)
        p['supply_solid_m3'] += p['solid_rate_m3_s']*seconds
        p['years'] += step; elapsed += step
    p['max_formative_step_years'] = max_formative_step_years
    p['forcing'] = asdict(forcing)
    p['widths_m'] = [_width(p['discharge_m3_s']*s, 0., 0.) for s in p['shares']]
    p['active'] = active
    p['channel_min_depth_m'] = channel_min_depth_m
    p['segments'] = segment_fluxes(p)
    return _record(state, p), p

