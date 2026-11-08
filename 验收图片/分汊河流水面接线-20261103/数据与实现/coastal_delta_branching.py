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
    references = [_control_reference(state, route) for route in routes]
    return {'control_references': references, 'input_id': input_id, 'discharge_m3_s': discharge_m3_s,
            'solid_rate_m3_s': solid_rate_m3_s, 'supply_solid_m3': 0.,
            'source_state_fingerprint': _source_fingerprint(state),
            'routes': [[list(c) for c in route] for route in routes],
            'shares': [.36, .34, .30], 'history': [], 'years': 0.,
            'assumptions': 'prescribed ocean velocity; route shares proxy water and solid flux; raster corridors are not resolved river widths'}



def _control_reference(state, route, radius_cells=6):
    """Save only the mouth control and its local bar neighbourhood."""
    end = route[-1]
    bed = state.bed_m
    cells = []
    for r in range(max(0, end[0]-radius_cells), min(state.bed_m.shape[0], end[0]+radius_cells+1)):
        for c in range(max(0, end[1]-radius_cells), min(state.bed_m.shape[1], end[1]+radius_cells+1)):
            if (r-end[0])**2 + (c-end[1])**2 <= radius_cells**2 and state.valid_mask[r, c]:
                cells.append([r, c, float(bed[r, c])])
    mouth = [list(c) for c in route[-6:]]
    return {'mouth': mouth, 'bed_m': [float(bed[tuple(c)]) for c in mouth],
            'bar_bed_m': cells, 'radius_cells': radius_cells}


def _validate(state, progress):
    records = [r for r in state.consumed_packets if r['input_id'] == progress['input_id']]
    if len(records) > 1:
        raise ValueError('duplicate formation record')
    if records:
        if records[0].get('formation_progress') != progress:
            raise ValueError('formation progress does not match state')
    elif progress['years'] != 0 or _source_fingerprint(state) != progress['source_state_fingerprint']:
        raise ValueError('formation source state mismatch')


def _clean_roundoff(state):
    """Remove only floating-point negative stock left by coupled solvers."""
    changes = {}
    for name in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        values = getattr(state, name)
        if values is not None and np.min(values) < 0:
            if np.min(values) < -1e-9:
                raise ValueError('negative sediment stock')
            changes[name] = np.maximum(values, 0.)
    return replace(state, **changes) if changes else state


def _record(state, progress):
    inlet = progress['routes'][0][0]
    equivalent_water = progress['discharge_m3_s'] * progress['years'] * 365.25 * 86400
    record = {'input_id': progress['input_id'], 'source_id': 'branch-formation',
              'start_s': state.time_s-1., 'end_s': state.time_s, 'known': True,
              'row': inlet[0], 'col': inlet[1], 'direction_xz': [1., 0.],
              'water_m3': 0., 'solid_m3': progress['supply_solid_m3'],
              'pending_solid_m3': 0., 'undelivered_solid_m3': progress.get('formation_undelivered_solid_m3', 0.),
              'undelivered_water_m3': progress.get('formation_undelivered_water_m3', 0.),
              'delivered_water_m3': 0.,
              'delivered_solid_m3': progress['supply_solid_m3'] - progress.get('formation_undelivered_solid_m3', 0.),
              'record_kind': 'equivalent_geological_formation',
              'equivalent_water_m3': equivalent_water,
              'equivalent_delivered_water_m3': equivalent_water - progress.get('formation_undelivered_water_m3', 0.),
              'formation_progress': progress}
    records = tuple(r for r in state.consumed_packets if r['input_id'] != progress['input_id']) + (record,)
    return replace(state, consumed_packets=records)


def segment_fluxes(progress):
    """Aggregate all outlet shares on shared directed D4 segments."""
    edges = {}
    for route, share in zip(progress['routes'], progress.get('actual_shares', progress['shares'])):
        for a, b in zip(route, route[1:]):
            key = (tuple(a), tuple(b))
            edges[key] = edges.get(key, 0.) + share
    return [{'from_zx': list(a), 'to_zx': list(b), 'share': share,
             'discharge_m3_s': progress['discharge_m3_s']*share,
             'solid_rate_m3_s': progress['solid_rate_m3_s']*share,
             'width_m': _width(progress['discharge_m3_s']*share, 0., 0.) if share else 0.,
             'active': share > 0}
            for (a,b), share in edges.items()]

def _refresh_route_fields(state, progress, *, sea_level_m=None):
    """Synchronize saved route summaries with the current bed and topology."""
    if sea_level_m is None:
        sea_level_m = progress.get('forcing', {}).get('sea_level_m', 0.)
    ocean, _ = classify_ocean(state, sea_level_m)
    progress['segments'] = segment_fluxes(progress)
    progress['widths_m'] = [(_width(progress['discharge_m3_s']*share, 0., 0.) if share else 0.)
                            for share in progress.get('actual_shares', progress['shares'])]
    progress['active'] = [all(ocean[tuple(cell)] for cell in route) and bool(face)
                          for route, face in zip(progress['routes'], mouth_exterior_faces(state, progress, sea_level_m=sea_level_m))]


def propose(state, reference, progress, *, sea_level_m=0., min_bar_rise_m=.1,
            min_share=.08, max_cut_m=1., radius_cells=6):
    """Find a new wet path when measured nearby deposition reduces conveyance.

    Compare the same cells against the reference and seek accessible actual
    shoreline cells. No target shape or predetermined pair of mouths is used.
    """
    ocean, shore = classify_ocean(state, sea_level_m)
    bed = state.bed_m
    depth = np.maximum(sea_level_m-bed, 0.)
    rise = None if reference is None else np.maximum(state.bed_m-reference.bed_m, 0.)
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    occupied = set(c for route in routes for c in route)
    rows, cols = np.indices(depth.shape)
    best = None
    for index, route in enumerate(routes):
        if progress['shares'][index] < 2*min_share or len(route) < 7:
            continue
        end = route[-1]
        near = (rows-end[0])**2+(cols-end[1])**2 <= radius_cells**2
        saved = progress.get('control_references')
        if saved is not None:
            ref = saved[index]
            if ref['radius_cells'] != radius_cells:
                raise ValueError('control reference radius mismatch')
            bar = max((float(bed[r,c]-old_bed) for r,c,old_bed in ref['bar_bed_m']), default=0.)
        else:
            if rise is None:
                raise ValueError('missing reference')
            bar = float(np.max(np.where(near & state.valid_mask, rise, 0.)))
        mouth_cells = np.array(route[max(0, len(route)-6):])
        mouth_index = tuple(mouth_cells.T)
        if saved is not None:
            if ref['mouth'] != mouth_cells.tolist():
                raise ValueError('control reference route mismatch')
            reference_depth = np.maximum(sea_level_m-np.asarray(ref['bed_m']), 0.)
        else:
            reference_depth = np.maximum(sea_level_m-reference.bed_m[mouth_index], 0.)
        current_depth = depth[mouth_index]
        loss = float(np.percentile(reference_depth, 10) - np.percentile(current_depth, 10))
        # A nearby bar alone is not evidence that the old route has lost
        # conveyance. Require an actual decline on its control section.
        if bar < min_bar_rise_m or loss < min_bar_rise_m:
            continue
        for fork_index in range(max(2, len(route)-12), len(route)-3):
            fork = route[fork_index]
            if any(tuple(item['proposal']['path'][0]) == fork for item in progress['history'] if item.get('event') == 'split'):
                continue
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
    if 'control_references' in p:
        updated = replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile)
        p['control_references'][idx] = _control_reference(updated, p['routes'][idx])
        p['control_references'].append(_control_reference(updated, p['routes'][-1]))
    p['history'].append({'event': 'split', 'year': p['years'], 'proposal': proposal,
                         'excavated_solid_m3': removed, 'shares': list(p['shares'])})
    updated = replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile)
    _update_activity(updated, p, p.get('forcing', {}).get('sea_level_m', 0.), 'split')
    return _record(updated, p), p


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
        active = _update_activity(state, p, forcing.sea_level_m, 'formation')
        source = np.zeros(state.bed_m.shape)
        for route, share in zip(p['routes'], p['actual_shares']):
            if share:
                source[tuple(route[-1])] += p['solid_rate_m3_s']*share
        if not any(active):
            p['formation_undelivered_solid_m3'] = p.get('formation_undelivered_solid_m3', 0.) + p['solid_rate_m3_s']*seconds
            p['formation_undelivered_water_m3'] = p.get('formation_undelivered_water_m3', 0.) + p['discharge_m3_s']*seconds
        ceiling = np.full(state.bed_m.shape, forcing.sea_level_m)
        for route, wet in zip(p['routes'], active):
            if wet:
                for cell in route:
                    cell = tuple(cell)
                    ceiling[cell] = max(forcing.sea_level_m-channel_min_depth_m, state.bed_m[cell])
        state, _ = advance(state, seconds, forcing, source_rate_m3_s=source, bed_ceiling_m=ceiling)
        state = _clean_roundoff(replace(state, time_s=physical_time))
        p['supply_solid_m3'] += p['solid_rate_m3_s']*seconds
        p['years'] += step; elapsed += step
    p['max_formative_step_years'] = max_formative_step_years
    p['forcing'] = asdict(forcing)
    p['channel_min_depth_m'] = channel_min_depth_m
    _update_activity(state, p, forcing.sea_level_m, 'formation')
    return _record(state, p), p



def _exterior_ocean(state, routes, sea_level_m):
    """Ocean connected to a real seed after excluding every route cell."""
    wet = state.valid_mask & (state.bed_m < sea_level_m)
    for route in routes:
        for cell in route:
            wet[tuple(cell)] = False
    labels, _ = ndimage.label(wet)
    ids = np.unique(labels[state.ocean_seed_mask & wet])
    return np.isin(labels, ids[ids != 0]) & wet


def mouth_exterior_faces(state, progress, *, sea_level_m=0.):
    exterior = _exterior_ocean(state, progress['routes'], sea_level_m)
    result = []
    for route in progress['routes']:
        r, c = route[-1]
        faces = [[r+dr,c+dc] for dr,dc in ((0,1),(1,0),(0,-1),(-1,0))
                 if 0 <= r+dr < exterior.shape[0] and 0 <= c+dc < exterior.shape[1]
                 and exterior[r+dr,c+dc]]
        result.append(faces)
    return result


def update_shoreline_mouths(state, progress, *, sea_level_m=0., radius_cells=8,
                            max_cut_m=2., channel_depth_m=.35):
    """Extend isolated mouths to independently boundary-connected exterior water.

    Existing route cells are impassable except the current endpoint. A failed
    update raises without returning a partially modified state or progress.
    """
    _validate(state, progress)
    if (not np.isfinite([sea_level_m, max_cut_m, channel_depth_m]).all() or
            max_cut_m <= 0 or channel_depth_m <= 0 or not isinstance(radius_cells, int) or radius_cells < 2):
        raise ValueError('invalid mouth update settings')
    p = json.loads(json.dumps(progress))
    current = state
    changes = []
    for idx in range(len(p['routes'])):
        if mouth_exterior_faces(current, p, sea_level_m=sea_level_m)[idx]:
            continue
        route = p['routes'][idx]; start_cell = tuple(route[-1])
        bed = current.bed_m
        exterior = _exterior_ocean(current, p['routes'], sea_level_m)
        rr, cc = np.indices(bed.shape)
        local = (rr-start_cell[0])**2+(cc-start_cell[1])**2 <= radius_cells**2
        cut = np.maximum(bed-(sea_level_m-channel_depth_m), 0.)
        allowed = (current.valid_mask & local & (current.base_bed_m <= sea_level_m-channel_depth_m)
                   & (cut <= max_cut_m))
        for occupied_route in p['routes']:
            for cell in occupied_route:
                allowed[tuple(cell)] = False
        allowed[start_cell] = True
        # A new endpoint itself becomes occupied: retain a separate exterior face.
        candidates = exterior & local & ndimage.convolve(exterior.astype(np.int8),
            np.array([[0,1,0],[1,0,1],[0,1,0]], dtype=np.int8), mode='constant').astype(bool)
        candidates &= allowed
        coordinates = np.argwhere(candidates)
        coordinates = sorted((tuple(map(int, c)) for c in coordinates),
                             key=lambda c: (abs(c[0]-start_cell[0])+abs(c[1]-start_cell[1]), c))
        cost = np.where(allowed, 1.+cut, np.inf)
        best = None
        for end in coordinates[:80]:
            try:
                path = _route(cost, start_cell, end)
            except ValueError:
                continue
            if len(path) < 2:
                continue
            score = sum(1.+cut[cell] for cell in path[1:])
            if best is None or score < best[0]:
                best = score, path
        if best is None:
            raise ValueError('no finite deposited-sediment mouth route to exterior ocean')
        path = best[1]
        stock = current.bed_solid_m3.copy(); mobile = current.mobile_solid_m3.copy()
        removed = 0.
        for cell in path[1:]:
            amount = float(cut[cell]*current.spacing_m**2*(1-current.porosity[cell]))
            if amount > stock[cell]+1e-7:
                raise ValueError('mouth cut exceeds sediment inventory')
            stock[cell] -= amount; mobile[cell] += amount; removed += amount
        current = replace(current, bed_solid_m3=stock, mobile_solid_m3=mobile)
        p['routes'][idx].extend([list(c) for c in path[1:]])
        if 'control_references' in p:
            p['control_references'][idx] = _control_reference(current, p['routes'][idx])
        change = {'event': 'mouth_extension', 'year': p['years'], 'route': idx,
                  'reason': 'mouth lacked independently boundary-connected exterior face',
                  'path': [list(c) for c in path], 'excavated_solid_m3': removed,
                  'max_cut_m': float(max(cut[c] for c in path))}
        p['history'].append(change); changes.append(change)
        if not mouth_exterior_faces(current, p, sea_level_m=sea_level_m)[idx]:
            raise ValueError('mouth update did not reach exterior ocean')
    if not all(mouth_exterior_faces(current, p, sea_level_m=sea_level_m)):
        raise ValueError('mouth updates obstruct another exterior face')
    if changes:
        _update_activity(current, p, sea_level_m, 'mouth_extension')
    return _record(current, p), p, changes


def _allocate_route_shares(routes, planned, active):
    """Redistribute blocked paths at each shared-prefix fork."""
    actual = [0.] * len(routes)

    def allocate(indices, depth, fraction):
        eligible = [i for i in indices if active[i]]
        if not eligible:
            return
        groups = {}
        for i in indices:
            key = tuple(routes[i][depth]) if depth < len(routes[i]) else None
            groups.setdefault(key, []).append(i)
        if len(groups) == 1:
            if next(iter(groups)) is None:
                total = sum(planned[i] for i in eligible)
                for i in eligible:
                    actual[i] += fraction * planned[i] / total
            else:
                allocate(indices, depth + 1, fraction)
            return
        live = [g for g in groups.values() if any(active[i] for i in g)]
        total = sum(sum(planned[i] for i in g) for g in live)
        for group in live:
            allocate(group, depth + 1, fraction * sum(planned[i] for i in group) / total)

    allocate(list(range(len(routes))), 0, 1.)
    return actual


def _update_activity(state, progress, sea_level_m, event_id, hydraulic_config=None):
    """Redistribute at each shared prefix, retaining the planned fork ratios."""
    if hydraulic_config is not None:
        from .coastal_delta_hydraulics import solve
        result = solve(state, progress, sea_level_m, hydraulic_config)
        previous = progress.get('river_hydraulics')
        if previous and previous['parameters'] != result['parameters']:
            raise ValueError('river hydraulic parameters mismatch')
        old = progress.get('active'), progress.get('actual_shares')
        progress['river_hydraulics'] = result
        progress['active'] = result['active']
        progress['actual_shares'] = result['actual_shares']
        progress['segments'] = segment_fluxes(progress)
        progress['widths_m'] = [(_width(q, 0., 0.) if q > 0 else 0.) for q in result['route_q_m3_s']]
        if old != (progress['active'], progress['actual_shares']):
            progress['history'].append({'event': 'river_stage_activity', 'input_id': event_id,
                'time_s': state.time_s, 'active': result['active'], 'route_q_m3_s': result['route_q_m3_s']})
        return result['active']
    ocean, _ = classify_ocean(state, sea_level_m)
    faces = mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)
    routes = progress['routes']
    active = [all(ocean[tuple(c)] for c in route) and bool(face)
              for route, face in zip(routes, faces)]
    actual = _allocate_route_shares(routes, progress['shares'], active)
    old_active = progress.get('active')
    old_shares = progress.get('actual_shares')
    progress['actual_shares'] = actual
    _refresh_route_fields(state, progress, sea_level_m=sea_level_m)
    if old_active != active or old_shares != actual:
        progress['history'].append({'event': 'route_activity', 'input_id': event_id,
            'time_s': state.time_s, 'active': active, 'actual_shares': actual})
    return active


def _event_edges(state, progress, sea_level_m):
    """Append a single wet seaward exchange face to each distinct outlet."""
    edges = [e for e in segment_fluxes(progress) if e['share'] > 0]
    ocean = _exterior_ocean(state, progress['routes'], sea_level_m)
    occupied = {tuple(c) for route in progress['routes'] for c in route}
    bed = state.bed_m
    for route, share in zip(progress['routes'], progress.get('actual_shares', progress['shares'])):
        if share <= 0:
            continue
        end = tuple(route[-1]); prev = tuple(route[-2])
        direction = (end[0]-prev[0], end[1]-prev[1])
        options = []
        for dr, dc in ((0,1), (1,0), (0,-1), (-1,0)):
            r, c = end[0]+dr, end[1]+dc
            if 0 <= r < bed.shape[0] and 0 <= c < bed.shape[1] and ocean[r,c] and (r,c) not in occupied:
                options.append((dr*direction[0]+dc*direction[1], -bed[r,c], r, c))
        if options:
            _, _, r, c = max(options)
            q = progress['discharge_m3_s']*share
            edges.append({'from_zx': list(end), 'to_zx': [r,c], 'discharge_m3_s': q,
                          'width_m': _width(q, 0., 0.)})
    return edges


def _river_exchange(state, progress, duration_s, *, sea_level_m=0.,
                    capacity_concentration=.01, active_layer_m=.1, max_velocity_m_s=2.,
                    erosion_remaining=None, river_stages=None):
    """Move finite stocks along directed edges; Q-weighted branches share one donor.

    A grid cell represents a wider area than its river. Only the channel-width
    fraction of mobile stock participates. Bed entrainment is limited by the
    exposed channel area, deposited inventory and remaining carrying capacity.
    """
    edges = _event_edges(state, progress, sea_level_m)
    outgoing = {}
    for edge in edges:
        outgoing.setdefault(tuple(edge['from_zx']), []).append(edge)
    mobile = state.mobile_solid_m3.copy()
    bed = state.bed_solid_m3.copy()
    terminal_q = {tuple(route[-1]): progress['discharge_m3_s']*share
                  for route, share in zip(progress['routes'], progress.get('actual_shares', progress['shares']))
                  if share > 0 and tuple(route[-1]) not in outgoing}
    if erosion_remaining is None:
        erosion_remaining = {}
        for cell, branches in outgoing.items():
            q = sum(e['discharge_m3_s'] for e in branches)
            width = min(state.spacing_m, _width(q, 0., 0.))
            erosion_remaining[cell] = min(bed[cell], active_layer_m*width*state.spacing_m*(1-state.porosity[cell]))
        for cell, q in terminal_q.items():
            width = min(state.spacing_m, _width(q, 0., 0.))
            erosion_remaining[cell] = min(bed[cell], active_layer_m*width*state.spacing_m*(1-state.porosity[cell]))
    moved_total = entrained_total = 0.
    elapsed = 0.
    while elapsed < duration_s:
        dt = min(duration_s-elapsed, state.spacing_m/max_velocity_m_s)
        bed_height = state.base_bed_m + bed/(state.spacing_m**2*(1-state.porosity))
        delta = np.zeros_like(mobile)
        for cell, branches in outgoing.items():
            depth = (river_stages.get(cell, sea_level_m) if river_stages is not None else sea_level_m)-bed_height[cell]
            if depth <= 0:
                continue
            usable = [e for e in branches if (river_stages.get(tuple(e['to_zx']), sea_level_m) if river_stages is not None else sea_level_m)-bed_height[tuple(e['to_zx'])] > 0]
            if not usable:
                continue
            q = sum(e['discharge_m3_s'] for e in usable)
            width = _width(q, 0., 0.)
            velocity = min(max_velocity_m_s, q/(width*depth))
            fraction = min(1., width/state.spacing_m)
            capacity = q*capacity_concentration*dt
            carried = min(mobile[cell]*fraction*min(1., velocity*dt/state.spacing_m), capacity)
            available_bed = min(bed[cell], erosion_remaining.get(cell, 0.))
            eroded = min(available_bed, max(0., capacity-carried))
            bed[cell] -= eroded
            erosion_remaining[cell] = erosion_remaining.get(cell, 0.)-eroded
            delta[cell] -= carried
            for edge in usable:
                amount = (carried+eroded)*edge['discharge_m3_s']/q
                delta[tuple(edge['to_zx'])] += amount
            moved_total += carried+eroded
            entrained_total += eroded
        for cell, q in terminal_q.items():
            if (river_stages.get(cell, sea_level_m) if river_stages is not None else sea_level_m)-bed_height[cell] <= 0:
                continue
            width = min(state.spacing_m, _width(q, 0., 0.))
            carried = mobile[cell]*width/state.spacing_m
            eroded = min(bed[cell], erosion_remaining.get(cell, 0.),
                         max(0., q*capacity_concentration*dt-carried))
            bed[cell] -= eroded
            erosion_remaining[cell] = erosion_remaining.get(cell, 0.)-eroded
            delta[cell] += eroded
            entrained_total += eroded
        mobile += delta
        elapsed += dt
    return replace(state, bed_solid_m3=bed, mobile_solid_m3=mobile), {
        'internal_transfer_solid_m3': moved_total, 'entrained_solid_m3': entrained_total}


def flush_pending(state, progress, *, input_id, water_m3=None, solid_m3=None, sea_level_m=0.):
    """Deliver selected upstream stock at the wet inlet without replaying its source.

    None selects the entire pending quantity. Physical water updates the marine
    ledger; formation water remains an equivalent geological quantity. This is
    an instantaneous bookkeeping transfer, not a timed hydraulic simulation.
    """
    _validate(state, progress)
    records = [dict(record) for record in state.consumed_packets]
    matches = [r for r in records if r['input_id'] == input_id]
    if len(matches) != 1 or matches[0].get('record_kind') not in ('branch_event', 'equivalent_geological_formation'):
        raise ValueError('unknown pending branch source')
    record = matches[0]
    available_water = record.get('undelivered_water_m3', 0.)
    available_solid = record.get('undelivered_solid_m3', 0.)
    water = available_water if water_m3 is None else water_m3
    solid = available_solid if solid_m3 is None else solid_m3
    if (not np.isfinite([water, solid, sea_level_m]).all() or min(water, solid) < 0
            or water > available_water or solid > available_solid or water + solid <= 0):
        raise ValueError('invalid pending delivery')
    p = json.loads(json.dumps(progress))
    active = _update_activity(state, p, sea_level_m, input_id + ':flush')
    if not any(active):
        raise ValueError('no active path for pending delivery')
    inlet = tuple(p['routes'][0][0])
    mobile = state.mobile_solid_m3.copy()
    mobile[inlet] += solid
    formation = record['record_kind'] == 'equivalent_geological_formation'
    if formation:
        p['formation_undelivered_water_m3'] = available_water - water
        p['formation_undelivered_solid_m3'] = available_solid - solid
    else:
        record['undelivered_water_m3'] = available_water - water
        record['undelivered_solid_m3'] = available_solid - solid
        record['delivered_water_m3'] += water
        record['delivered_solid_m3'] += solid
    p['history'].append({'event': 'pending_delivery', 'input_id': input_id,
        'time_s': state.time_s, 'water_m3': water, 'solid_m3': solid})
    state = replace(state, mobile_solid_m3=mobile, consumed_packets=tuple(records),
        water_input_m3=state.water_input_m3 + (0. if formation else water))
    return _record(state, p), p, {'input_id': input_id, 'water_m3': water, 'solid_m3': solid,
        'undelivered_water_m3': available_water-water, 'undelivered_solid_m3': available_solid-solid}


def advance_river_event(state, progress, duration_s, marine_config, *, input_id,
                        inlet_solid_rate_m3_s=0., capacity_concentration=.01,
                        active_layer_m=.1, max_velocity_m_s=2., hydraulic_config=None):
    """Couple a single physical inlet packet, finite river transfer and marine event.

    River velocity and carrying concentration are explicit engineering assumptions;
    the model does not solve water levels or claim resolved river hydraulics.
    """
    from .coastal_marine_sediment import RiverPacket, advance as marine_advance
    _validate(state, progress)
    if 'river_hydraulics' in progress and hydraulic_config is None:
        raise ValueError('river hydraulic configuration required for continuation')
    values = [duration_s, inlet_solid_rate_m3_s, capacity_concentration, active_layer_m, max_velocity_m_s]
    if (not np.isfinite(values).all() or duration_s <= 0 or inlet_solid_rate_m3_s < 0
            or capacity_concentration <= 0 or capacity_concentration > 1
            or active_layer_m < 0 or max_velocity_m_s <= 0 or not input_id
            or any(r['input_id'] == input_id for r in state.consumed_packets)):
        raise ValueError('invalid or duplicate river event')
    if not np.isfinite(marine_config.step_s) or marine_config.step_s <= 0:
        raise ValueError('invalid marine step')
    # Reserve every possible internal ID before any state is processed.
    existing_ids = {r['input_id'] for r in state.consumed_packets}
    elapsed_check = 0.
    while elapsed_check < duration_s:
        stage_id = input_id + ':stage:' + str(elapsed_check)
        if stage_id in existing_ids:
            raise ValueError('river event stage ID conflicts with existing record')
        elapsed_check += min(marine_config.step_s, duration_s-elapsed_check)
    p = json.loads(json.dumps(progress))
    first = p['routes'][0]
    inlet = first[0]
    dr = first[1][0]-inlet[0]; dc = first[1][1]-inlet[1]
    start_time = state.time_s
    total_water = p['discharge_m3_s'] * duration_s
    total_solid = inlet_solid_rate_m3_s * duration_s
    pending_water = pending_solid = delivered_water = delivered_solid = 0.
    erosion_remaining = {}
    # Establish the original event-wide cap from planned segment discharges.
    planned = dict(p)
    planned.pop('actual_shares', None)
    q_by_cell = {}
    for edge in _event_edges(state, planned, marine_config.sea_level_m):
        cell = tuple(edge['from_zx'])
        q_by_cell[cell] = q_by_cell.get(cell, 0.) + edge['discharge_m3_s']
    for route, share in zip(p['routes'], p['shares']):
        q_by_cell.setdefault(tuple(route[-1]), p['discharge_m3_s'] * share)
    for cell, q in q_by_cell.items():
        width = min(state.spacing_m, _width(q, 0., 0.))
        erosion_remaining[cell] = min(state.bed_solid_m3[cell],
            active_layer_m * width * state.spacing_m * (1-state.porosity[cell]))
    elapsed = moved = entrained = 0.
    while elapsed < duration_s:
        dt = min(marine_config.step_s, duration_s-elapsed)
        level = marine_config.sea_level_m
        if hydraulic_config is not None:
            level += marine_config.tide_amplitude_m*np.sin(2*np.pi*(state.time_s+dt/2)/marine_config.tide_period_s)
        active = _update_activity(state, p, level, input_id, hydraulic_config)
        fraction = (p['river_hydraulics']['accepted_q_m3_s']/p['discharge_m3_s']
                    if hydraulic_config is not None else (1. if any(active) else 0.))
        water = p['discharge_m3_s'] * dt * fraction
        solid = inlet_solid_rate_m3_s * dt * fraction
        pending_water += p['discharge_m3_s']*dt-water
        pending_solid += inlet_solid_rate_m3_s*dt-solid
        packets = []
        if any(active):
            stages = ({(n[0], n[1]): n[2] for n in p['river_hydraulics']['nodes']}
                      if hydraulic_config is not None else None)
            depth = (stages[tuple(inlet)] if stages is not None else marine_config.sea_level_m)-state.bed_m[tuple(inlet)]
            if hydraulic_config is not None:
                mobile = state.mobile_solid_m3.copy()
                mobile[tuple(inlet)] += solid
                state = replace(state, mobile_solid_m3=mobile)
            packet = RiverPacket(input_id=input_id + ':stage:' + str(elapsed),
                source_id='branch-event-inlet', start_s=state.time_s, end_s=state.time_s+dt,
                row=inlet[0], col=inlet[1], water_m3=water, solid_m3=(0. if hydraulic_config is not None else solid), known=True,
                direction_xz=(dc, dr), width_m=_width(p['discharge_m3_s']*fraction, 0., 0.), depth_m=depth)
            packets = [packet]
            delivered_water += water; delivered_solid += solid
            state, transfer = _river_exchange(state, p, dt, sea_level_m=level,
                capacity_concentration=capacity_concentration, active_layer_m=active_layer_m,
                max_velocity_m_s=max_velocity_m_s, erosion_remaining=erosion_remaining, river_stages=stages)
            moved += transfer['internal_transfer_solid_m3']; entrained += transfer['entrained_solid_m3']
        if hydraulic_config is not None:
            # Keep the channel's shared stock at its own cells while the marine
            # solver operates on the ocean; restore it after the marine step.
            mask = np.zeros(state.bed_m.shape, bool)
            for route, wet in zip(p['routes'], active):
                if wet:
                    for cell in route:
                        mask[tuple(cell)] = True
            mobile = state.mobile_solid_m3.copy(); stranded = state.stranded_solid_m3.copy()
            held_mobile = np.where(mask, mobile + stranded, 0.); held_stranded = np.zeros_like(stranded)
            mobile[mask] = 0.; stranded[mask] = 0.
            state = replace(state, mobile_solid_m3=mobile, stranded_solid_m3=stranded)
        state = _clean_roundoff(marine_advance(state, packets, dt, marine_config))
        if hydraulic_config is not None:
            state = replace(state, mobile_solid_m3=state.mobile_solid_m3+held_mobile,
                            stranded_solid_m3=state.stranded_solid_m3+held_stranded)
        if packets:
            stage_id = packet.input_id
            stage_record = next(r for r in state.consumed_packets if r['input_id'] == stage_id)
            withheld = stage_record['pending_solid_m3']
            pending_solid += withheld
            delivered_solid -= withheld
            state = replace(state, consumed_packets=tuple(r for r in state.consumed_packets if r['input_id'] != stage_id))
        elapsed += dt
    final_level = marine_config.sea_level_m
    if hydraulic_config is not None:
        final_level += marine_config.tide_amplitude_m*np.sin(2*np.pi*state.time_s/marine_config.tide_period_s)
    _update_activity(state, p, final_level, input_id, hydraulic_config)
    record = {'input_id': input_id, 'source_id': 'branch-event-inlet', 'start_s': start_time,
        'end_s': state.time_s, 'known': True, 'row': inlet[0], 'col': inlet[1],
        'direction_xz': [dc, dr], 'water_m3': total_water, 'solid_m3': total_solid,
        'delivered_water_m3': delivered_water, 'delivered_solid_m3': delivered_solid,
        'pending_solid_m3': 0., 'undelivered_solid_m3': pending_solid,
        'undelivered_water_m3': pending_water, 'record_kind': 'branch_event'}
    state = replace(state, consumed_packets=state.consumed_packets + (record,))
    state = _record(state, p)
    return state, {'input_id': input_id, 'water_m3': total_water, 'solid_m3': total_solid,
        'delivered_water_m3': delivered_water, 'delivered_solid_m3': delivered_solid,
        'undelivered_water_m3': pending_water, 'undelivered_solid_m3': pending_solid,
        'internal_transfer_solid_m3': moved, 'entrained_solid_m3': entrained,
        'capacity_concentration': capacity_concentration, 'active_layer_m': active_layer_m,
        'max_velocity_m_s': max_velocity_m_s, 'updated_progress': p}
