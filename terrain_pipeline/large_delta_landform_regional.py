"""Provisional finite-stock, terrain-routed regional delta formation experiment."""
import heapq
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt, binary_propagation, label
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import conservative_diffusion_step


def _routes(bed, allowed, start, spacing):
    """Dijkstra on current coastal bed; shallow water favours transport corridors."""
    shape = bed.shape
    dist = np.full(shape, np.inf)
    previous = np.full(shape, -1, np.int32)
    dist[start] = 0.
    queue = [(0., start[0], start[1])]
    while queue:
        cost, r, c = heapq.heappop(queue)
        if cost != dist[r,c]:
            continue
        for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
            y, x = r+dr, c+dc
            if y < 0 or x < 0 or y >= shape[0] or x >= shape[1] or not allowed[y,x]:
                continue
            # Provisional depth and emergent-bed resistance, not hydraulic heads.
            resistance = 1. + .055*max(-bed[y,x], 0.) + 2.*max(bed[y,x]+.3, 0.)
            candidate = cost + spacing*np.hypot(dr,dc)*resistance
            if candidate < dist[y,x]:
                dist[y,x] = candidate
                previous[y,x] = r*shape[1]+c
                heapq.heappush(queue,(candidate,y,x))
    return dist, previous


def form(bed, ocean, valid, inlet, spacing, solid_m3, *, steps=30, porosity=.4):
    """Form a speculative coastal body with a finite imported solid budget.

    Morphological batches have no physical time; this is not a water solver.
    """
    bed = np.asarray(bed, float)
    ocean = np.asarray(ocean, bool)
    valid = np.asarray(valid, bool)
    if bed.shape != ocean.shape or bed.shape != valid.shape or not np.isfinite(bed).all():
        raise ValueError('matching finite terrain required')
    if solid_m3 <= 0 or spacing <= 0 or not 0 <= porosity < 1 or steps < 1:
        raise ValueError('invalid supply or iteration parameters')
    shape = bed.shape
    rr,cc = np.indices(shape)
    radius = np.hypot(rr-inlet[0],cc-inlet[1])*spacing
    # Shallow shelf only, fixed edge, no alteration to original land or deep ocean.
    sea_seed = np.zeros(shape, bool)
    sea_seed[0, :] = ocean[0, :]
    sea_seed[-1, :] = ocean[-1, :]
    sea_seed[:, 0] = ocean[:, 0]
    sea_seed[:, -1] = ocean[:, -1]
    connected_sea = binary_propagation(sea_seed, mask=ocean & valid & (bed < -.25))
    allowed = connected_sea & (bed > -18.) & (radius < 25000.)
    allowed[[0,-1],:] = False
    allowed[:,[0,-1]] = False
    candidates = np.argwhere(allowed)
    if not len(candidates):
        raise ValueError('no shallow shelf')
    start = tuple(candidates[np.argmin(np.sum((candidates-inlet)**2,axis=1))])
    shore_dist = distance_transform_edt(ocean)*spacing
    target_mask = allowed & (shore_dist < 1800.) & (radius > 3000.)
    # Edge attenuation controls deposition and therefore joins unchanged TD smoothly.
    taper = np.clip(distance_transform_edt(allowed)*spacing/1200.,0.,1.)
    taper *= np.clip((25000.-radius)/3000.,0.,1.)
    result = bed.copy()
    route_history = np.zeros(shape, np.int32)
    paths = []
    outlet_history = np.zeros(shape, float)
    delivered = solid_m3/(1.-porosity)/spacing**2
    remaining = delivered
    kinds = np.where(allowed,0,-2)
    for step in range(steps):
        distance, previous = _routes(result,allowed,start,spacing)
        viable = target_mask & np.isfinite(distance) & (taper > .05)
        # Prefer underused shoreline accommodation; penalty makes later lobes avulse.
        history = gaussian_filter(route_history.astype(float), sigma=8.)
        score = np.where(viable, distance/60000. + 10.*history + 250.*gaussian_filter(outlet_history, sigma=6.) - .6*np.clip(-result,0.,10.)/10., np.inf)
        if not np.isfinite(score).any():
            break
        target = np.unravel_index(np.argmin(score),shape)
        outlet_history[target] += 1.
        path=[]; cell=target
        while cell != start:
            path.append(cell)
            parent = int(previous[cell])
            if parent < 0 or len(path) > bed.size:
                raise RuntimeError('unreachable route')
            cell = divmod(parent,shape[1])
        path.append(start); path.reverse(); paths.append(path)
        path_grid=np.zeros(shape,float)
        for cell in path: path_grid[cell]+=1.
        route_history += path_grid.astype(np.int32)
        # Capacity loss near shoreline and overbank spreading follow current route.
        weights = gaussian_filter(path_grid,sigma=4.) * taper * allowed
        accommodation = np.maximum(0., .7-result)*taper
        weight = weights * np.sqrt(accommodation)
        batch = min(delivered/steps,remaining)
        for _ in range(8):
            total=weight.sum()
            if total <= 0 or batch <= 1e-10: break
            add=np.minimum(batch*weight/total,accommodation)
            result += add
            spent=float(add.sum()); batch-=spent; remaining-=spent
            accommodation-=add
            weight=weights*np.sqrt(np.maximum(accommodation,0.))
        # Existing donor-limited operator moves only cover, respecting original floor.
        result=conservative_diffusion_step(result, np.where(allowed, .1, 0.), kinds, bed, .01, spacing)
    return dict(bed=result, allowed=allowed, taper=taper, paths=paths, route_history=route_history,
                solid_input_m3=solid_m3, solid_retained_m3=(delivered-remaining)*spacing**2*(1.-porosity),
                solid_unplaced_m3=remaining*spacing**2*(1.-porosity), porosity=porosity, inlet=start)


def channelize(formation, original_bed, spacing, discharge_m3_s):
    """Construct wet paths on the final routing tree, recycling excavated cover.

    Equal steady terminal partition is a documented kinematic scenario, not FV.
    """
    bed = formation['bed'].copy()
    original = np.asarray(original_bed, float)
    allowed = formation['allowed']
    start = formation['inlet']
    _, previous = _routes(bed, allowed, start, spacing)
    tree = {}
    paths=[]
    selected = []
    for candidate in formation['paths']:
        target = candidate[-1]
        if any(np.hypot(target[0]-other[0], target[1]-other[1])*spacing < 1500. for other in selected):
            continue
        if (len(selected)+1)*3. > discharge_m3_s:
            break
        selected.append(target)
        path=[]; cell=target
        while cell != start:
            path.append(cell)
            parent=int(previous[cell])
            if parent < 0 or len(path)>bed.size:
                path=[]; break
            cell=divmod(parent, bed.shape[1])
        if not path: continue
        path.append(start); path.reverse(); paths.append(path)
        for a,b in zip(path,path[1:]): tree.setdefault(a,set()).add(b)
    channel=np.zeros(bed.shape,bool)
    for path in paths:
        for cell in path: channel[cell]=True
    # Cut only previously deposited cover; never cut original TD.
    target=np.maximum(original, -.25)
    lowered=np.where(channel, np.minimum(bed,target),bed)
    removed=float((bed-lowered).sum())
    bed=lowered
    # Return channel excavation to eligible shallow cells, excluding channels.
    room=np.maximum(.7-bed,0.)*formation['taper']*allowed*(~channel)
    remaining=removed
    for _ in range(10):
        total=room.sum()
        if total <= 0 or remaining <= 1.e-10: break
        add=np.minimum(remaining*room/total, room)
        bed+=add; used=float(add.sum()); remaining-=used; room-=add
    junctions=[cell for cell,children in tree.items() if len(children)>=2]
    # Q is partitioned at the root and accumulated along shared edges.
    q=float(discharge_m3_s)/len(paths) if paths else 0.
    water_flux=np.zeros(bed.shape,float)
    for path in paths:
        for cell in path: water_flux[cell]+=q
    return dict(bed=bed, channel=channel, paths=paths, junctions=junctions,
                water_flux_m3_s=water_flux, channel_excavated_bulk_m3=removed*spacing**2,
                channel_unplaced_solid_m3=remaining*spacing**2*(1.-formation['porosity']))
