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

def _refresh_route_fields(state, progress, *, sea_level_m=None):
    """Synchronize saved route summaries with the current bed and topology."""
    if sea_level_m is None:
        sea_level_m = progress.get('forcing', {}).get('sea_level_m', 0.)
    ocean, _ = classify_ocean(state, sea_level_m)
    progress['segments'] = segment_fluxes(progress)
    progress['widths_m'] = [_width(progress['discharge_m3_s']*share, 0., 0.)
                            for share in progress['shares']]
    progress['active'] = [all(ocean[tuple(cell)] for cell in route)
                          for route in progress['routes']]


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
    _refresh_route_fields(updated, p)
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
        _refresh_route_fields(current, p, sea_level_m=sea_level_m)
    return _record(current, p), p, changes


def _event_edges(state, progress, sea_level_m):
    """Append a single wet seaward exchange face to each distinct outlet."""
    edges = segment_fluxes(progress)
    ocean = _exterior_ocean(state, progress['routes'], sea_level_m)
    occupied = {tuple(c) for route in progress['routes'] for c in route}
    bed = state.bed_m
    for route, share in zip(progress['routes'], progress['shares']):
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
                    erosion_remaining=None):
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
                  for route, share in zip(progress['routes'], progress['shares'])
                  if tuple(route[-1]) not in outgoing}
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
            depth = sea_level_m-bed_height[cell]
            if depth <= 0:
                continue
            usable = [e for e in branches if sea_level_m-bed_height[tuple(e['to_zx'])] > 0]
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
            if sea_level_m-bed_height[cell] <= 0:
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


def advance_river_event(state, progress, duration_s, marine_config, *, input_id,
                        inlet_solid_rate_m3_s=0., capacity_concentration=.01,
                        active_layer_m=.1, max_velocity_m_s=2.):
    """Couple a single physical inlet packet, finite river transfer and marine event.

    River velocity and carrying concentration are explicit engineering assumptions;
    the model does not solve water levels or claim resolved river hydraulics.
    """
    from .coastal_marine_sediment import RiverPacket, advance as marine_advance
    _validate(state, progress)
    values = [duration_s, inlet_solid_rate_m3_s, capacity_concentration, active_layer_m, max_velocity_m_s]
    if (not np.isfinite(values).all() or duration_s <= 0 or inlet_solid_rate_m3_s < 0
            or capacity_concentration <= 0 or capacity_concentration > 1
            or active_layer_m < 0 or max_velocity_m_s <= 0 or not input_id
            or any(r['input_id'] == input_id for r in state.consumed_packets)):
        raise ValueError('invalid or duplicate river event')
    first = progress['routes'][0]
    inlet = first[0]
    dr = first[1][0]-inlet[0]; dc = first[1][1]-inlet[1]
    depth = marine_config.sea_level_m-state.bed_m[tuple(inlet)]
    if depth <= 0:
        raise ValueError('dry river inlet')
    packet = RiverPacket(input_id=input_id, source_id='branch-event-inlet',
        start_s=state.time_s, end_s=state.time_s+duration_s, row=inlet[0], col=inlet[1],
        water_m3=progress['discharge_m3_s']*duration_s,
        solid_m3=inlet_solid_rate_m3_s*duration_s, known=True, direction_xz=(dc, dr),
        width_m=_width(progress['discharge_m3_s'], 0., 0.), depth_m=depth)
    outgoing = {}
    for edge in _event_edges(state, progress, marine_config.sea_level_m):
        cell = tuple(edge['from_zx'])
        outgoing[cell] = outgoing.get(cell, 0.) + edge['discharge_m3_s']
    for route, share in zip(progress['routes'], progress['shares']):
        cell = tuple(route[-1])
        if cell not in outgoing:
            outgoing[cell] = progress['discharge_m3_s']*share
    erosion_remaining = {}
    for cell, q in outgoing.items():
        width = min(state.spacing_m, _width(q, 0., 0.))
        erosion_remaining[cell] = min(state.bed_solid_m3[cell],
            active_layer_m*width*state.spacing_m*(1-state.porosity[cell]))
    elapsed = moved = entrained = 0.
    while elapsed < duration_s:
        dt = min(marine_config.step_s, duration_s-elapsed)
        state, transfer = _river_exchange(state, progress, dt, sea_level_m=marine_config.sea_level_m,
            capacity_concentration=capacity_concentration, active_layer_m=active_layer_m,
            max_velocity_m_s=max_velocity_m_s, erosion_remaining=erosion_remaining)
        moved += transfer['internal_transfer_solid_m3']; entrained += transfer['entrained_solid_m3']
        state = marine_advance(state, [packet] if elapsed == 0 else [], dt, marine_config)
        elapsed += dt
    return state, {'input_id': input_id, 'water_m3': packet.water_m3, 'solid_m3': packet.solid_m3,
                   'internal_transfer_solid_m3': moved, 'entrained_solid_m3': entrained,
                   'capacity_concentration': capacity_concentration, 'active_layer_m': active_layer_m,
                   'max_velocity_m_s': max_velocity_m_s}
