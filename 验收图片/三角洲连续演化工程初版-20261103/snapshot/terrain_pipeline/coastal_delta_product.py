"""Finite experimental geological delta, with restartable scenario metadata.

One raster cell is the minimum channel corridor; formative widths are subgrid
hydraulic parameters, never claimed as measured raster widths.
"""
from dataclasses import dataclass, asdict, replace
from collections import deque
import hashlib
import heapq
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
from .coastal_marine_sediment import classify_ocean, save_state, load_state, _park_and_release
from .coastal_marine_product import load_product as load_base_product
from .surface_rivers.formative_section import section_from_routed_budget


@dataclass(frozen=True)
class DeltaConfig:
    formation_id: str = 'rank1-v3'
    inlet_zx: tuple = (151, 439)
    direction_xz: tuple = (0.9238795325, 0.3826834324)
    discharge_m3_s: float = 150.0
    solid_rate_m3_s: float = 0.075
    total_years: float = 500.0
    interval_years: float = 10.0
    extent_m: float = 12000.0
    sea_level_m: float = 0.0
    clearance_m: float = 2.0
    max_rise_m: float = 2.5
    world_seed: int = 20261020
    marine_transit_speed_m_s: float = 0.02
    formation_highwater_m: float = 1.0
    overbank_settling_fraction: float = 0.03
    longterm_transport: dict | None = None


def _targets(state, ocean, cfg):
    rows, cols = np.indices(ocean.shape)
    dx = (cols - cfg.inlet_zx[1]) * state.spacing_m
    dz = (rows - cfg.inlet_zx[0]) * state.spacing_m
    d = np.asarray(cfg.direction_xz, float); d /= np.linalg.norm(d)
    along = dx*d[0] + dz*d[1]
    cross = -dx*d[1] + dz*d[0]
    # Select real connected marine cells with offshore clearance, not crop edges.
    full_ocean, _ = classify_ocean(state, cfg.sea_level_m)
    offshore = full_ocean & (state.bed_m < cfg.sea_level_m - 10.)
    candidates = ocean & ndimage.binary_dilation(offshore)
    if not candidates.any():
        candidates = ocean
    targets = []
    for lateral in (0., -0.42, 0.48):
        score = ((along-cfg.extent_m)/state.spacing_m)**2 + ((cross-lateral*cfg.extent_m)/state.spacing_m)**2
        score += (np.maximum(cfg.sea_level_m-state.bed_m-5., 0.)*2.0)**2
        score = np.where(candidates, score, np.inf)
        if not np.isfinite(score).any():
            raise ValueError('no sourced distal marine target')
        targets.append(tuple(map(int,np.unravel_index(np.argmin(score), score.shape))))
    return targets


def _route(cost, start, end):
    """Geometric D8 search with a safe, explicitly rasterized D4 bridge."""
    shape = cost.shape
    # Prefer gradual progress toward the destination when many geometric
    # shortest paths have equal length; barriers remain absolute constraints.
    rows, cols = np.indices(shape)
    dr, dc = end[0]-start[0], end[1]-start[1]
    length = np.hypot(dr, dc)
    if length:
        lateral = np.abs((rows-start[0])*dc-(cols-start[1])*dr)/length
        cost = cost + .04*lateral
    distance = {start: 0.}
    previous = {}
    queue = [(0., 0., start)]
    minimum = float(np.min(cost[np.isfinite(cost)]))
    while queue:
        _, value, cell = heapq.heappop(queue)
        if value != distance.get(cell):
            continue
        if cell == end:
            break
        r, c = cell
        for dr, dc in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            nxt = (r+dr, c+dc)
            if not (0 <= nxt[0] < shape[0] and 0 <= nxt[1] < shape[1]) or not np.isfinite(cost[nxt]):
                continue
            bridge = None
            if dr and dc:
                options = [(r+dr,c), (r,c+dc)]
                options = [p for p in options if np.isfinite(cost[p])]
                if not options:
                    continue
                bridge = min(options, key=lambda p: cost[p])
            step = (2**.5 if bridge else 1.) * (cost[cell]+cost[nxt])*.5
            candidate = value + step
            if candidate < distance.get(nxt, float('inf')):
                distance[nxt] = candidate
                previous[nxt] = (cell, bridge)
                heuristic = minimum * np.hypot(end[0]-nxt[0], end[1]-nxt[1])
                heapq.heappush(queue, (candidate+heuristic, candidate, nxt))
    if end not in distance:
        raise ValueError('no connected ocean route')
    edges = []
    cell = end
    while cell != start:
        parent, bridge = previous[cell]
        edges.append((cell, bridge))
        cell = parent
    path = [start]
    for cell, bridge in reversed(edges):
        if bridge is not None:
            path.append(bridge)
        path.append(cell)
    # Remove any loops introduced by bridge cells, preserving D4 adjacency.
    simple = []
    positions = {}
    for cell in path:
        if cell in positions:
            index = positions[cell]
            for removed in simple[index+1:]:
                del positions[removed]
            simple = simple[:index+1]
        else:
            positions[cell] = len(simple)
            simple.append(cell)
    return simple


def _network(state, cfg):
    ocean, _ = classify_ocean(state,cfg.sea_level_m)
    start=tuple(cfg.inlet_zx)
    if not ocean[start]:
        raise ValueError('inlet no longer connected to ocean')
    bed=state.bed_m
    # Existing shallow cells are traversable without excavation. Their bed
    # remains unchanged until a wet connected channel can be maintained.
    deep = ocean & (bed >= cfg.sea_level_m - 10.)
    labels, _ = ndimage.label(deep)
    label = labels[start]
    if label == 0:
        raise ValueError('inlet lacks declared channel clearance')
    ocean = deep & (labels == label)
    targets=_targets(state,ocean,cfg)
    # Absolute-coordinate deterministic variation breaks ties without a local-grid seed.
    z,x=np.indices(bed.shape)
    wx=state.origin_xz_m[0]+x*state.spacing_m
    wz=state.origin_xz_m[1]+z*state.spacing_m
    # Smooth world-coordinate resistance varies bank preference over kilometres.
    ripple=.01*(1+np.sin(wx*.0013+1.3*np.sin(wz*.0011)+cfg.world_seed*.001)
                  *np.cos(wz*.0015+wx*.00035))
    cost=1.+np.maximum(cfg.sea_level_m-bed-2.,0.)**2*.001+ripple
    cost=np.where(ocean,cost,np.inf)
    # Choose a nearby deep-water terminus before routing: an intermediate
    # shallow target would force an artificial right-angle change of course.
    full_ocean,_=classify_ocean(state,cfg.sea_level_m)
    deep_sea=full_ocean & (bed <= cfg.sea_level_m-20.)
    if deep_sea.any():
        rows,cols=np.indices(bed.shape)
        dist=(rows-targets[0][0])**2+(cols-targets[0][1])**2
        sea_target=tuple(map(int,np.unravel_index(np.argmin(np.where(deep_sea,dist,np.inf)),dist.shape)))
        trunk_cost=np.where(full_ocean,1.+np.maximum(cfg.sea_level_m-bed-2.,0.)**2*.001+ripple,np.inf)
        trunk=_route(trunk_cost,start,sea_target)
    else:
        trunk=_route(cost,start,targets[0])
    if len(trunk)<8:
        raise ValueError('distal route too short')
    forks=[max(3,len(trunk)//3), max(6,2*len(trunk)//3)]
    branches=[]
    selected_forks=[]
    for nominal,target in zip(forks,targets[1:]):
        best=None
        # A coastal corridor can pinch shut. Find a reachable staggered fork
        # rather than forcing an overlap or manufacturing an opening.
        minimum=selected_forks[-1]+2 if selected_forks else 2
        for index in sorted(range(minimum,len(trunk)-2), key=lambda i: abs(i-nominal)):
            allowed=ocean.copy()
            for cell in trunk:
                allowed[cell]=False
            for prior in branches:
                for cell in prior:
                    allowed[cell]=False
            junction=trunk[index]
            allowed[junction]=True
            labels, _ = ndimage.label(allowed)
            reachable=labels == labels[junction]
            rows,cols=np.indices(bed.shape)
            distance=np.hypot(rows-junction[0],cols-junction[1])*state.spacing_m
            score=((rows-target[0])**2+(cols-target[1])**2
                   + np.maximum(cfg.sea_level_m-bed-5.,0.)**2*4.)
            score=np.where(reachable & (distance>=state.spacing_m*4),score,np.inf)
            if np.isfinite(score).any():
                outlet=tuple(map(int,np.unravel_index(np.argmin(score),score.shape)))
                best=(index,junction,outlet,allowed)
                break
        if best is None:
            raise ValueError('no distinct reachable branch outlet')
        index,junction,outlet,allowed=best
        selected_forks.append(index)
        branches.append(_route(np.where(allowed,cost,np.inf),junction,outlet))
    forks=selected_forks
    targets=[trunk[-1],*(path[-1] for path in branches)]
    return trunk,branches,forks,targets


def _width(q, incoming, deposited):
    return float(section_from_routed_budget(q,.35,.35,0.,.25,
        incoming_solid_m3=incoming, external_solid_m3=0., capacity_solid_m3=incoming,
        eroded_loose_solid_m3=0.,eroded_rock_m3=0.,deposited_solid_m3=deposited,
        max_width_m=2000.).width_m)


def _spread(mobile, stranded, wet, channel, channel_ceiling, bed, stock, area, cfg, state, source_ocean):
    """Conservative face mixing and settling; no geometric support mask."""
    for _ in range(40):
        available=mobile*.20*np.where(bed >= cfg.sea_level_m, .25, 1.)
        out=np.zeros_like(mobile)
        incoming=np.zeros_like(mobile)
        for dr,dc in ((0,1),(0,-1),(1,0),(-1,0)):
            src=(slice(max(0,-dr),min(mobile.shape[0],mobile.shape[0]-dr)),slice(max(0,-dc),min(mobile.shape[1],mobile.shape[1]-dc)))
            dst=(slice(max(0,dr),min(mobile.shape[0],mobile.shape[0]+dr)),slice(max(0,dc),min(mobile.shape[1],mobile.shape[1]+dc)))
            transfer=available[src]*wet[src]*wet[dst]
            out[src]+=transfer
            incoming[dst]+=transfer
        mobile += incoming-out
        # Distributed settling respects local accommodation and iteration rise.
        highwater=cfg.sea_level_m+cfg.formation_highwater_m
        capacity=np.maximum(0., np.minimum(cfg.max_rise_m/40, np.where(channel, channel_ceiling, highwater)-bed))*area
        # Reduced coastal settling applies on the shallow shelf and channel;
        # deeper water retains mobile sediment for the marine event solver.
        depth=np.maximum(cfg.sea_level_m-bed,0.)
        settling_factor=1. / (1. + np.exp(np.clip((depth-15.)/3.,-60.,60.)))
        settling_factor=np.where(channel,1.,settling_factor)
        overbank=cfg.overbank_settling_fraction*np.clip((highwater-bed)/cfg.formation_highwater_m,0.,1.)
        settling_factor=np.where((bed>=cfg.sea_level_m) & ~channel,overbank,settling_factor)
        settle=np.minimum(mobile*.075*settling_factor,capacity)*wet
        mobile-=settle; stock+=settle; bed+=settle/area
        if np.any(wet & (bed >= highwater)):
            wet,_=classify_ocean(replace(state,bed_solid_m3=stock),highwater)
            wet &= source_ocean
            _park_and_release(mobile,stranded,wet)
    return mobile


def _ocean_transit_graph(wet, seeds):
    """Shortest D4 paths to actual wet parent-domain boundary seed cells."""
    rows, cols = wet.shape
    downstream = np.full(wet.size, -1, dtype=np.int32)
    distance = np.full(wet.size, -1, dtype=np.int32)
    boundary = np.flatnonzero((wet & seeds).ravel())
    queue = deque(map(int, boundary))
    distance[boundary] = 0
    downstream[boundary] = -2
    flat_wet = wet.ravel()
    while queue:
        cell = queue.popleft()
        r, c = divmod(cell, cols)
        for neighbor in ((cell-cols if r else -1), (cell+cols if r+1 < rows else -1),
                         (cell-1 if c else -1), (cell+1 if c+1 < cols else -1)):
            if neighbor >= 0 and flat_wet[neighbor] and distance[neighbor] < 0:
                distance[neighbor] = distance[cell] + 1
                downstream[neighbor] = cell
                queue.append(neighbor)
    if np.any(flat_wet & (distance < 0)):
        raise ValueError('ocean transit lacks a boundary path')
    return downstream, distance


def _transit(mobile, downstream, seconds, cell_seconds, *, uniform):
    """Move stock along the boundary DAG; uniform stock arrives during interval.

    Each face takes cell_seconds. The final boundary cell also takes that time
    before export. Uniform arrivals occupy every traversed cell for its actual
    remaining residence time; a pre-existing pulse uses its full elapsed time.
    """
    shape = mobile.shape
    wave = mobile.ravel().copy()
    residual = np.zeros_like(wave)
    exported = np.zeros_like(wave)
    step = 0
    while np.any(wave):
        active = np.flatnonzero(wave)
        if np.any(downstream[active] == -1):
            raise ValueError('mobile sediment outside connected transit ocean')
        elapsed = step*cell_seconds
        if uniform:
            residence = max(0., min(cell_seconds, seconds-elapsed))/seconds
            residual[active] += wave[active]*residence
            exited = max(0., seconds-(elapsed+cell_seconds))/seconds
        else:
            if elapsed+cell_seconds > seconds:
                residual[active] += wave[active]
                break
            exited = 1.
        boundary = downstream[active] == -2
        if boundary.any():
            exported[active[boundary]] += wave[active[boundary]]*exited
        if uniform and elapsed+cell_seconds >= seconds:
            break
        parents = downstream[active[~boundary]]
        wave = np.bincount(parents, weights=wave[active[~boundary]], minlength=wave.size)
        step += 1
    return residual.reshape(shape), exported.reshape(shape)


def _source_fingerprint(state):
    digest=hashlib.sha256()
    for name in ('base_bed_m','bed_solid_m3','mobile_solid_m3','stranded_solid_m3',
                 'porosity','valid_mask','ocean_seed_mask'):
        array=np.ascontiguousarray(getattr(state,name))
        digest.update(name.encode('ascii'))
        digest.update(str(array.dtype).encode('ascii'))
        digest.update(json.dumps(array.shape).encode('ascii'))
        digest.update(array.tobytes())
    metadata={'source_identity':state.source_identity,'origin_xz_m':state.origin_xz_m,
              'spacing_m':state.spacing_m,'time_s':state.time_s,
              'exported_solid_m3':state.exported_solid_m3,'unresolved_solid_m3':state.unresolved_solid_m3,
              'water_input_m3':state.water_input_m3,'consumed_packets':state.consumed_packets}
    digest.update(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode('utf8'))
    return digest.hexdigest()


def start(state, cfg):
    if not cfg.formation_id or cfg.world_seed != 20261020 or not np.isfinite([cfg.total_years,cfg.interval_years,cfg.discharge_m3_s,cfg.solid_rate_m3_s,cfg.extent_m,cfg.clearance_m,cfg.max_rise_m,cfg.marine_transit_speed_m_s,cfg.formation_highwater_m,cfg.overbank_settling_fraction]).all() or min(cfg.total_years,cfg.interval_years,cfg.discharge_m3_s,cfg.solid_rate_m3_s,cfg.extent_m,cfg.clearance_m,cfg.max_rise_m,cfg.marine_transit_speed_m_s,cfg.formation_highwater_m)<=0 or not 0 <= cfg.overbank_settling_fraction <= 1:
        raise ValueError('invalid formation configuration')
    if any(r['input_id'] == 'formation:' + cfg.formation_id for r in state.consumed_packets):
        raise ValueError('formation already registered')
    serialized_config = asdict(cfg)
    if cfg.longterm_transport is None:
        serialized_config.pop('longterm_transport')
    progress = {'formation_id':cfg.formation_id,'config':json.loads(json.dumps(serialized_config)),'source_state_fingerprint':_source_fingerprint(state),'years_delivered':0.,'supply_solid_m3':0.,'pending_solid_m3':0.,'deposited_solid_m3':0.,'intervals':0}
    if cfg.longterm_transport is not None:
        from .coastal_marine_longterm import LongtermConfig
        progress['longterm_forcing'] = asdict(LongtermConfig(**cfg.longterm_transport))
        progress['longterm_algorithm'] = 'implicit-upwind-diffusion-settling-v1'
    return progress


def advance_formation(state, progress, cfg, intervals=1, *, network_proposal=None,
                      channel_excavation=None, delivery_leak_multiplier=1., split_fractions=None):
    """Transfer incremental external solid to the single marine stock owner."""
    saved_config = dict(progress['config'])
    saved_config.setdefault('longterm_transport', None)
    if progress['formation_id'] != cfg.formation_id or saved_config != json.loads(json.dumps(asdict(cfg))):
        raise ValueError('formation identity/config mismatch')
    if cfg.longterm_transport is not None and 'longterm_forcing' in progress:
        from .coastal_marine_longterm import LongtermConfig
        if progress['longterm_forcing'] != asdict(LongtermConfig(**cfg.longterm_transport)):
            raise ValueError('longterm forcing mismatch')
    if intervals < 1 or progress['years_delivered'] >= cfg.total_years:
        raise ValueError('formation already completed or invalid interval count')
    records=[dict(r) for r in state.consumed_packets]
    record_id='formation:' + cfg.formation_id
    prior=next((r for r in records if r['input_id']==record_id), None)
    if prior is not None and prior.get('formation_progress') != progress:
        raise ValueError('formation progress does not match state')
    if prior is None and progress['intervals'] != 0:
        raise ValueError('formation progress missing from state')
    if prior is None and progress.get('source_state_fingerprint') != _source_fingerprint(state):
        raise ValueError('formation source state mismatch')
    if network_proposal is not None and intervals != 1:
        raise ValueError('a network proposal applies to exactly one interval')
    if (not np.isfinite(delivery_leak_multiplier) or not 0 <= delivery_leak_multiplier <= 1
            or (channel_excavation and (network_proposal is None or intervals != 1))):
        raise ValueError('invalid proposed channel treatment')
    if prior is not None and progress.get('delivery_leak_multiplier', 1.) != delivery_leak_multiplier:
        raise ValueError('formation delivery multiplier mismatch')
    if split_fractions is not None and (len(split_fractions) != 2 or not np.isfinite(split_fractions).all() or any(x < 0 or x > 1 for x in split_fractions)):
        raise ValueError('invalid split fractions')
    p=json.loads(json.dumps(progress)); stock=state.bed_solid_m3.copy()
    if delivery_leak_multiplier != 1.:
        p['delivery_leak_multiplier'] = delivery_leak_multiplier
    mobile=state.mobile_solid_m3.copy()
    stranded=state.stranded_solid_m3.copy()
    area=state.spacing_m**2*(1-state.porosity)
    last=None
    exported=state.exported_solid_m3
    source_ocean,_=classify_ocean(replace(state,bed_solid_m3=np.zeros_like(stock)),cfg.sea_level_m)
    for _ in range(intervals):
        years=min(cfg.interval_years,cfg.total_years-p['years_delivered'])
        if years<=0: break
        current=replace(state,bed_solid_m3=stock.copy())
        if network_proposal is not None:
            trunk, branches, forks, targets = network_proposal
            proposal_cells = {tuple(cell) for path in [trunk, *branches] for cell in path}
            removed = []
            for cell, target_bed in (channel_excavation or {}).items():
                cell = tuple(cell)
                if (cell not in proposal_cells or not np.isfinite(target_bed)
                        or target_bed < current.base_bed_m[cell]
                        or target_bed > current.bed_m[cell]):
                    raise ValueError('channel excavation exceeds finite deposit')
                amount = (current.bed_m[cell]-target_bed)*area[cell]
                stock[cell] -= amount
                mobile[cell] += amount
                removed.append({'cell_zx':list(cell), 'target_bed_m':float(target_bed),
                                'solid_m3':float(amount)})
            current = replace(state, bed_solid_m3=stock.copy())
            ocean, _ = classify_ocean(current, cfg.sea_level_m)
            paths = [trunk, *branches]
            if (len(branches) != 2 or len(forks) != 2 or len(targets) != 3
                    or not trunk or tuple(trunk[0]) != tuple(cfg.inlet_zx)
                    or any(not path for path in paths)):
                raise ValueError('invalid proposed network')
            for index, path in enumerate(paths):
                cells = [tuple(cell) for cell in path]
                if (any(len(cell) != 2 or not (0 <= cell[0] < ocean.shape[0] and 0 <= cell[1] < ocean.shape[1]) or not ocean[cell] for cell in cells)
                        or any(abs(a[0]-b[0])+abs(a[1]-b[1]) != 1 for a, b in zip(cells, cells[1:]))
                        or tuple(targets[index]) != cells[-1]):
                    raise ValueError('proposed path must be a connected wet D4 route')
            if any(not 0 <= fork < len(trunk) or tuple(branch[0]) != tuple(trunk[fork]) for fork, branch in zip(forks, branches)) or forks[0] >= forks[1]:
                raise ValueError('invalid proposed forks')
            sets = [set(map(tuple, path)) for path in paths]
            if (any(len(cells) != len(path) for cells, path in zip(sets, paths))
                    or sets[0] & sets[1] != {tuple(branches[0][0])}
                    or sets[0] & sets[2] != {tuple(branches[1][0])}
                    or sets[1] & sets[2]):
                raise ValueError('proposed paths overlap outside their forks')
            ceilings = [[float(min(current.bed_m[cell], cfg.sea_level_m-cfg.clearance_m-max(0., cfg.sea_level_m-current.bed_m[cell]-8.)*.75)) for cell in map(tuple, path)] for path in paths]
            p['network'] = json.loads(json.dumps({'trunk': trunk, 'branches': branches,
                'fork_indices': forks, 'targets': targets, 'channel_ceilings_m': ceilings}))
            p.setdefault('channel_treatment', []).append({'year_start':p['years_delivered'],
                'excavation':removed})
        if 'network' not in p:
            trunk,branches,forks,targets=_network(current,cfg)
            paths=[trunk,*branches]
            # Retain a graded connection into the original deep marine bed.
            ceilings=[[float(cfg.sea_level_m-cfg.clearance_m-max(0., cfg.sea_level_m-current.bed_m[cell]-8.)*.75) for cell in path] for path in paths]
            p['network']={'trunk':trunk,'branches':branches,'fork_indices':forks,'targets':targets,'channel_ceilings_m':ceilings}
            p['network']=json.loads(json.dumps(p['network']))
        saved=p['network']
        trunk=[tuple(cell) for cell in saved['trunk']]
        branches=[[tuple(cell) for cell in path] for path in saved['branches']]
        forks=saved['fork_indices']; targets=saved['targets']
        ocean,_=classify_ocean(current,cfg.sea_level_m)
        if any(not ocean[cell] for path in [trunk,*branches] for cell in path):
            raise ValueError('formation channel lost ocean connectivity')
        paths=[trunk,*branches]
        protected=np.zeros(stock.shape,bool)
        channel_ceiling=np.full(stock.shape,cfg.sea_level_m-cfg.clearance_m)
        for path, ceilings in zip(paths,saved['channel_ceilings_m']):
            for cell, ceiling in zip(path,ceilings):
                protected[cell]=True
                channel_ceiling[cell]=ceiling
        wet,_=classify_ocean(current,cfg.sea_level_m)
        _park_and_release(mobile,stranded,wet)
        duration_s=years*365.25*86400
        cell_seconds=state.spacing_m/cfg.marine_transit_speed_m_s
        if cfg.longterm_transport is None:
            downstream, distances = _ocean_transit_graph(wet, state.ocean_seed_mask)
            mobile, previous_export = _transit(mobile,downstream,duration_s,cell_seconds,uniform=False)
        bed=current.bed_m.copy()
        source=cfg.solid_rate_m3_s*years*365.25*86400
        available=source+p['pending_solid_m3']
        lateral=np.zeros_like(stock)
        previous=p.get('reach_exchange', {})
        exchange={}
        # Route inlet supply in order through the trunk and its two fork stations.
        branch_in=[0.,0.]; carried=available; reach=[]
        splits=(.28,.30) if split_fractions is None else tuple(split_fractions)
        p.setdefault('split_history', []).append({'year_start':p['years_delivered'], 'sequential_fractions':list(splits), 'discharge_m3_s':[cfg.discharge_m3_s*(1-splits[0])*(1-splits[1]), cfg.discharge_m3_s*splits[0], cfg.discharge_m3_s*(1-splits[0])*splits[1]]}) if split_fractions is not None else None
        def traverse(path, initial, q, r0_path, split_indices=None):
            nonlocal carried
            amount=initial
            for i,cell in enumerate(path):
                if split_indices and i in split_indices:
                    j=split_indices.index(i); share=amount*splits[j]
                    branch_in[j]+=share; amount-=share; q*=1-splits[j]
                key=f'{state.origin_xz_m[0]+cell[1]*state.spacing_m:.6f}:{state.origin_xz_m[1]+cell[0]*state.spacing_m:.6f}'
                prev=previous.get(key, [0.,0.])
                width=_width(q,max(prev[0],1e-12),prev[1])
                r,c=cell
                depth=max(cfg.sea_level_m-bed[cell],0.)
                leak=min(.14, .025 + width/state.spacing_m*.12 + depth*.001)*delivery_leak_multiplier
                incoming=amount
                released=amount*leak
                exchange[key]=[incoming,0.,r,c]
                amount-=released
                # The channel itself receives finite aggradation before bank settling.
                channel_capacity=max(0., min(cfg.max_rise_m, channel_ceiling[cell]-bed[cell]))*area[cell]
                channel_fill=min(released*.6,channel_capacity)
                stock[cell]+=channel_fill
                bed[cell]+=channel_fill/area[cell]
                lateral[cell]+=released-channel_fill
                reach.append((r,c,q,width,bed[cell]))
            return amount
        residual=traverse(trunk,available,cfg.discharge_m3_s,'trunk',forks)
        lateral[trunk[-1]]+=residual
        trunk_outlet_solid = residual
        for i,path in enumerate(branches):
            q=cfg.discharge_m3_s*(splits[0] if i==0 else (1-splits[0])*splits[1])
            residual=traverse(path,branch_in[i],q,str(i))
            lateral[path[-1]]+=residual
        if split_fractions is not None:
            p['split_history'][-1]['branch_solid_m3'] = list(branch_in)
            p['split_history'][-1]['trunk_outlet_solid_m3'] = trunk_outlet_solid
            p['split_history'][-1]['inlet_solid_m3'] = available
            p['split_history'][-1]['sections'] = [list(item) for item in reach]
        # Lateral release is an interval-integrated flux, not an instantaneous
        # century-long pulse waiting for the following physical tide event.
        highwater_wet,_=classify_ocean(current,cfg.sea_level_m+cfg.formation_highwater_m)
        highwater_wet &= source_ocean
        newly_mobile=_spread(lateral,stranded,highwater_wet,protected,channel_ceiling,bed,stock,area,cfg,current,source_ocean)
        highwater_wet,_=classify_ocean(replace(current,bed_solid_m3=stock),cfg.sea_level_m+cfg.formation_highwater_m)
        highwater_wet &= source_ocean
        _park_and_release(newly_mobile,stranded,highwater_wet)
        if cfg.longterm_transport is not None:
            from .coastal_marine_longterm import LongtermConfig, advance as advance_longterm
            forcing = LongtermConfig(**cfg.longterm_transport)
            if forcing.sea_level_m != cfg.sea_level_m + cfg.formation_highwater_m:
                raise ValueError('longterm level must match formation high water')
            marine = replace(current, bed_solid_m3=stock, mobile_solid_m3=mobile,
                             stranded_solid_m3=stranded, exported_solid_m3=exported)
            ceiling = np.where(protected, channel_ceiling, forcing.sea_level_m)
            marine, summary = advance_longterm(marine, duration_s, forcing,
                source_rate_m3_s=newly_mobile/duration_s, bed_ceiling_m=ceiling,
                allowed_mask=source_ocean)
            stock = marine.bed_solid_m3.copy()
            mobile = marine.mobile_solid_m3.copy()
            stranded = marine.stranded_solid_m3.copy()
            exported = marine.exported_solid_m3
            p.setdefault('longterm_transport', []).append(summary)
            newly_mobile = np.zeros_like(mobile)
        else:
            downstream, distances = _ocean_transit_graph(highwater_wet,state.ocean_seed_mask)
            newly_mobile, new_export = _transit(newly_mobile,downstream,duration_s,cell_seconds,uniform=True)
        wet,_=classify_ocean(replace(current,bed_solid_m3=stock),cfg.sea_level_m)
        _park_and_release(newly_mobile,stranded,wet)
        _park_and_release(mobile,stranded,wet)
        # Parked material has left connected water. Over the geological
        # interval it settles locally into the bed instead of becoming a
        # century-scale cache released by the next high tide.
        if cfg.longterm_transport is None:
            stock += stranded
            stranded.fill(0.)
        mobile += newly_mobile
        if cfg.longterm_transport is None:
            boundary_export=previous_export+new_export
            exported+=float(boundary_export.sum())
            transit=p.setdefault('marine_transit',{'speed_m_s':cfg.marine_transit_speed_m_s,
                'cell_travel_s':cell_seconds,'exported_solid_m3':0.,'boundary_export_m3':{},'max_path_cells':0})
            transit['exported_solid_m3']+=float(boundary_export.sum())
            transit['max_path_cells']=max(transit['max_path_cells'],int(distances.max())+1)
            for row,col in np.argwhere(boundary_export>0):
                key=f'{row}:{col}'
                transit['boundary_export_m3'][key]=transit['boundary_export_m3'].get(key,0.)+float(boundary_export[row,col])
            transit['end_mobile_solid_m3']=float(mobile.sum())
        saved_bed=replace(current,bed_solid_m3=stock).bed_m
        reach=[(r,c,q,w,float(saved_bed[r,c])) for r,c,q,w,_ in reach]
        placed=float((stock-current.bed_solid_m3).sum())
        p['years_delivered']+=years; p['supply_solid_m3']+=source
        p['pending_solid_m3']=0.
        for key, (incoming, _, row, col) in exchange.items():
            exchange[key]=[incoming, float(stock[row,col]-current.bed_solid_m3[row,col])]
        p['reach_exchange']=exchange
        p['deposited_solid_m3']+=placed; p['intervals']+=1
        last={'trunk':trunk,'branches':branches,'fork_indices':forks,'targets':targets,'sections':reach}
    # A completed synthetic packet records the geological delivery exactly once.
    # Its elapsed physical interval is already past, so event advance cannot
    # re-deliver it; formation_progress carries equivalent years and exchanges.
    record={'input_id':record_id,'source_id':'geological-formation','start_s':state.time_s-1.,
            'end_s':state.time_s,'known':True,'row':cfg.inlet_zx[0],'col':cfg.inlet_zx[1],
            'direction_xz':cfg.direction_xz,'water_m3':0.,'solid_m3':p['supply_solid_m3'], 'record_kind':'geological_formation',
            'pending_solid_m3':0.,'delivered_water_m3':0.,'delivered_solid_m3':p['supply_solid_m3'],
            'formation_progress':p}
    records=[r for r in records if r['input_id'] != record_id]+[record]
    result=replace(state,bed_solid_m3=stock,mobile_solid_m3=mobile,stranded_solid_m3=stranded,exported_solid_m3=exported,consumed_packets=tuple(records))
    return result,p,last


def save_checkpoint(prefix,state,progress):
    prefix=Path(prefix)
    state_path=prefix.with_suffix('.npz'); meta_path=prefix.with_suffix('.json')
    save_state(state_path,state)
    record=dict(progress); record['state_sha256']=hashlib.sha256(state_path.read_bytes()).hexdigest()
    meta_path.write_text(json.dumps(record,indent=2),encoding='utf8')


def load_checkpoint(prefix):
    prefix=Path(prefix); path=prefix.with_suffix('.npz')
    p=json.loads(prefix.with_suffix('.json').read_text(encoding='utf8'))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=p.pop('state_sha256'):
        raise ValueError('formation checkpoint state mismatch')
    return load_state(path),p


def read_product(prefix, source_state, base_product_path):
    """Read a completed checkpoint with source/final beds and explicit unknowns."""
    state, progress = load_checkpoint(prefix)
    manifest, base = load_base_product(base_product_path)
    if (state.source_identity != source_state.source_identity
            or progress.get('source_state_fingerprint') != _source_fingerprint(source_state)
            or manifest['identity'] != source_state.source_identity
            or tuple(manifest['origin_xz_m']) != source_state.origin_xz_m
            or manifest['spacing_m'] != source_state.spacing_m
            or not np.array_equal(base['final_bed'],source_state.base_bed_m)
            or not np.array_equal(base['valid'],source_state.valid_mask)
            or state.origin_xz_m != source_state.origin_xz_m
            or state.spacing_m != source_state.spacing_m
            or not np.array_equal(state.base_bed_m, source_state.base_bed_m)
            or not np.array_equal(state.valid_mask, source_state.valid_mask)):
        raise ValueError('source and product do not match')
    ocean, _ = classify_ocean(state, progress['config']['sea_level_m'])
    source_classification=base['classification'].copy()
    # Preserve unknowns and distinguish enclosed negative cells from land.
    classification = np.where(source_classification == 0, 0,
        np.where(ocean, 2, np.where(state.bed_m < progress['config']['sea_level_m'],3,1))).astype(np.uint8)
    arrays = {'source_bed_m': source_state.bed_m, 'final_bed_m': state.bed_m,
              'source_classification':source_classification, 'classification': classification}
    for array in arrays.values():
        array.setflags(write=False)
    return arrays, state, progress




