"""Scale-aware, terrain-routed distributaries on an initialized delta plain."""
import hashlib
import numpy as np
from scipy import ndimage
from skimage.graph import MCP_Geometric
from terrain_pipeline.large_delta_active_network import curve_edge


def _corridor_field(shape, origin, spacing, case_name):
    seed = int.from_bytes(hashlib.sha256(('20261020:delta-suite/corridor/' + case_name).encode('utf8')).digest()[:8], 'little')
    rng = np.random.default_rng(seed)
    x = origin[0] + np.arange(shape[1]) * spacing
    z = origin[1] + np.arange(shape[0]) * spacing
    result = np.zeros(shape)
    for _ in range(12):
        angle = rng.uniform(0, 2*np.pi)
        wavelength = rng.uniform(1200, 4000)
        phase = rng.uniform(0, 2*np.pi)
        result += np.cos(2*np.pi/wavelength * (np.sin(angle)*z[:,None]+np.cos(angle)*x[None,:]) + phase)
    return result / np.sqrt(6.), seed


def construct_network(bed_m, original_m, landform, valid, sea, origin_xz_m, spacing_m,
                      discharge_m3_s, *, outlet_count, inlet_zx=None, case_name="default",
                      water_slope_m_per_m=.00004, bank_allowance_m=.5):
    """Create a rooted set of wet native-bed cuts and metric analytic sections.

    Sea must already be connected to the regional boundary. The returned graph
    is kinematic initialization, with no simulated tidal or floodplain dynamics.
    """
    bed = np.asarray(bed_m, float); original = np.asarray(original_m, float)
    valid = np.asarray(valid, bool); sea = np.asarray(sea, bool)
    plain = np.asarray(landform, bool)
    if (bed.ndim != 2 or any(a.shape != bed.shape for a in (original, valid, sea, plain))
            or not np.isfinite(bed[valid]).all() or not np.isfinite(original[valid]).all()
            or not np.isfinite([spacing_m, discharge_m3_s, water_slope_m_per_m, bank_allowance_m]).all()
            or spacing_m <= 0 or discharge_m3_s <= 0 or water_slope_m_per_m < 0
            or bank_allowance_m < 0 or not 2 <= outlet_count <= 20):
        raise ValueError('invalid network inputs')
    bed = np.where(valid, bed, 0.)
    original = np.where(valid, original, 0.)
    boundary = np.zeros(bed.shape, bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    sea = ndimage.binary_propagation(sea & valid & boundary, mask=sea & valid, structure=np.ones((3, 3)))
    distance = ndimage.distance_transform_edt(~sea) * spacing_m
    # Route on low deposited ground only, avoiding original uplands.
    lowland_ceiling = max(4., float(np.percentile(bed[plain & valid], 99)) + 1.) if np.any(plain & valid) else 4.
    land = valid & ~sea & (bed >= 0) & (bed <= lowland_ceiling) & (original < 3) & (plain | (bed-original > .05))
    labels, n = ndimage.label(land, np.ones((3, 3)))
    if not n: raise ValueError('no connected low plain')
    if inlet_zx is None:
        sizes = np.bincount(labels.ravel()); sizes[0] = 0
        land &= labels == sizes.argmax()
        start = np.unravel_index(np.argmax(np.where(land, distance, -1)), bed.shape)
    else:
        start = tuple(map(int, inlet_zx))
        if len(start) != 2 or not (0 <= start[0] < bed.shape[0] and 0 <= start[1] < bed.shape[1]):
            raise ValueError('inlet outside grid')
        if not land[start]: raise ValueError('inlet outside low plain')
        land &= labels == labels[start]
    radius = float(distance[start])
    if radius < 5 * spacing_m: raise ValueError('plain too narrow for network')
    coastal = land & ndimage.binary_dilation(sea, structure=np.ones((3, 3)))
    noise, seed = _corridor_field(bed.shape, origin_xz_m, spacing_m, case_name)
    costs = np.full(bed.shape, np.inf)
    costs[land] = (1. + .12*np.maximum(bed[land], 0) + 3*np.exp(-distance[land]/max(radius*.08, spacing_m))
                   + .7*np.clip(noise[land]+2, 0, 4))
    mcp = MCP_Geometric(costs, fully_connected=True)
    distances, _ = mcp.find_costs([start])
    candidates = np.argwhere(coastal & np.isfinite(distances))
    candidates = candidates[np.linalg.norm(candidates-start, axis=1)*spacing_m > radius*.65]
    if len(candidates) > 500: candidates = candidates[::int(np.ceil(len(candidates)/500))]
    proposals = []
    for p in candidates:
        path = mcp.traceback(tuple(p))
        if len(path) < 3: continue
        near = np.mean([distance[q] < max(2*spacing_m, radius*.15) for q in path[:-max(1,int(radius*.05/spacing_m))]])
        if near > .3 or p[0] < 3 or p[1] < 3 or p[0] >= bed.shape[0]-3 or p[1] >= bed.shape[1]-3:
            continue
        proposals.append((tuple(p), path, near))
    chosen = []
    for _ in range(outlet_count):
        best = None
        for p, path, near in proposals:
            if any(p == item[0] for item in chosen): continue
            if chosen:
                shared = max(next((i for i,(a,b) in enumerate(zip(path,old)) if a != b), min(len(path),len(old))) for _,old,_ in chosen)
                unique = (len(path)-shared)*spacing_m
                sep = min(np.linalg.norm(np.subtract(p,q))*spacing_m for q,_,_ in chosen)
                if unique < max(radius*.06, 3*spacing_m) or sep < max(radius*.08, 4*spacing_m) or shared*spacing_m < radius*.08:
                    continue
                splits = [old[max(0,next((i for i,(a,b) in enumerate(zip(path,old)) if a != b),min(len(path),len(old)))-1)] for _,old,_ in chosen]
                # Require distinct bifurcation positions once the tree has forks.
                existing = set()
                for i,(_,a,_) in enumerate(chosen):
                    for _,b,_ in chosen[:i]:
                        k=next((j for j,(u,v) in enumerate(zip(a,b)) if u!=v),min(len(a),len(b)))
                        existing.add(a[max(0,k-1)])
                split = path[max(0,shared-1)]
                if any(np.linalg.norm(np.subtract(split,v))*spacing_m < max(radius*.025,2*spacing_m) for v in existing): continue
                score = min(unique,radius) + min(sep,radius) - near*radius*2
            else:
                score = len(path)*spacing_m - near*radius*2
            if best is None or score > best[0]: best = (score,p,path,near)
        if best is None: break
        _,p,path,near = best; chosen.append((p,path,near))
    # Add genuinely new branches where a single global shortest-path tree has
    # too few bifurcations. Existing channels are barriers except at eligible
    # interior attachment points, so a new branch cannot cross and rejoin.
    while len(chosen) < outlet_count and chosen:
        prefixes = {}
        tree_children = {}
        for _, path, _ in chosen:
            for k, cell in enumerate(path):
                prefixes.setdefault(tuple(cell), (path, k))
            for a, b in zip(path, path[1:]):
                tree_children.setdefault(tuple(a), set()).add(tuple(b))
        forks = [cell for cell, children in tree_children.items() if len(children) > 1]
        tree_mask = np.zeros(bed.shape, bool)
        for cell in prefixes: tree_mask[cell] = True
        attach = []
        for cell, (path, k) in prefixes.items():
            if (k+1)*spacing_m < radius*.12 or distance[cell] < radius*.15:
                continue
            if any(np.linalg.norm(np.subtract(cell, fork))*spacing_m < max(radius*.04,3*spacing_m) for fork in forks):
                continue
            if any(np.linalg.norm(np.subtract(cell, p))*spacing_m < max(radius*.08,4*spacing_m) for p,_,_ in chosen):
                continue
            attach.append(cell)
        if not attach: break
        extra_cost = costs.copy()
        extra_cost[tree_mask] = np.inf
        for cell in attach: extra_cost[cell] = costs[cell]
        branch_mcp = MCP_Geometric(extra_cost, fully_connected=True)
        branch_distance, _ = branch_mcp.find_costs(attach)
        best = None
        for candidate in candidates:
            p = tuple(candidate)
            if p[0] < 3 or p[1] < 3 or p[0] >= bed.shape[0]-3 or p[1] >= bed.shape[1]-3:
                continue
            separation = min(np.linalg.norm(np.subtract(p,q))*spacing_m for q,_,_ in chosen)
            if separation < max(radius*.08,4*spacing_m) or not np.isfinite(branch_distance[p]):
                continue
            branch = branch_mcp.traceback(p)
            if len(branch)*spacing_m < max(radius*.08,4*spacing_m): continue
            near = np.mean([distance[q] < max(2*spacing_m,radius*.10) for q in branch[:-max(1,int(radius*.05/spacing_m))]])
            if near > .4: continue
            score = min(separation,radius) + min(len(branch)*spacing_m,radius) - near*2*radius
            if best is None or score > best[0]: best = (score,p,branch,near)
        if best is None: break
        _, p, branch, near = best
        old_path, index = prefixes[tuple(branch[0])]
        chosen.append((p, old_path[:index+1] + branch[1:], near))
    if len(chosen) < 2: raise ValueError('fewer than two separated reachable outlets')
    paths=[]
    for p,path,_ in chosen:
        z,x=p
        neighbors=[(z+dz,x+dx) for dz in (-1,0,1) for dx in (-1,0,1)
                   if (dz or dx) and 0<=z+dz<bed.shape[0] and 0<=x+dx<bed.shape[1] and sea[z+dz,x+dx]]
        anchor=min(neighbors,key=lambda q: abs(bed[q]+1))
        paths.append(path+[anchor])
    children={}
    for path in paths:
        for a,b in zip(path,path[1:]): children.setdefault(tuple(a),set()).add(tuple(b))
    nodes={start}|{tuple(p[-1]) for p in paths}|{p for p,c in children.items() if len(c)>1}
    edges=[]
    def walk(node,parent):
        for child in sorted(children.get(node,())):
            pts=[node,child]
            while child not in nodes:
                child=next(iter(children[child])); pts.append(child)
            index=len(edges); edges.append({'parent':parent,'points':pts}); walk(child,index)
    walk(start,-1)
    original_cells=[set(e['points']) for e in edges]; occupied=set()
    for i,e in enumerate(edges):
        forbidden=set().union(*(c for j,c in enumerate(original_cells) if j!=i)) | occupied
        forbidden.discard(e['points'][0]); forbidden.discard(e['points'][-1])
        e['points'], e['smooth'], _ = curve_edge(e['points'],land,[p[-1] for p in paths],forbidden,spacing_m)
        # Smooth the metric centreline within each already-cut native cell;
        # fixed endpoints preserve exact junctions and the same raster path.
        positions=e['smooth']
        if len(positions)>3:
            filtered=ndimage.gaussian_filter1d(positions,1.2,axis=0,mode='nearest')
            cells=np.asarray(e['points'],float)
            filtered=np.clip(filtered,cells-.45,cells+.45)
            filtered[0]=positions[0]; filtered[-1]=positions[-1]
            e['smooth']=filtered
        occupied.update(e['points'][1:-1])
        e['length']=float(np.linalg.norm(np.diff(e['smooth'],axis=0),axis=1).sum()*spacing_m)
    conductance=np.zeros(len(edges))
    remaining=np.zeros(len(edges))
    for i in range(len(edges)-1,-1,-1):
        downstream=[j for j,e in enumerate(edges) if e['parent']==i]
        conductance[i]=1/(edges[i]['length']+(1/sum(conductance[j] for j in downstream) if downstream else radius*.2))
        remaining[i]=edges[i]['length']+(min(remaining[j] for j in downstream) if downstream else 0)
    inlet_stage=min(max(1.5,water_slope_m_per_m*max(remaining)),float(bed[start])+bank_allowance_m)
    carved=bed.copy(); river=np.zeros(bed.shape,bool); rows=[]
    for i,e in enumerate(edges):
        parent=e['parent']; siblings=[j for j,v in enumerate(edges) if v['parent']==parent]
        incoming=discharge_m3_s if parent==-1 else edges[parent]['q']
        e['q']=float(incoming*conductance[i]/sum(conductance[j] for j in siblings))
        width=float(8.314*e['q']**.45); depth=float(.598*e['q']**.28581553)
        start_stage=inlet_stage if parent==-1 else edges[parent]['end_stage']
        downstream=[j for j,v in enumerate(edges) if v['parent']==i]
        rem=min((remaining[j] for j in downstream),default=0.)
        e['end_stage']=start_stage*rem/(e['length']+rem)
        smooth=e['smooth']; d=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(smooth,axis=0),axis=1))]
        stages=start_stage+(e['end_stage']-start_stage)*d/d[-1]
        # Constrain initial surface to the local uncut land surface. Ocean
        # outlet anchors are excluded; junction stages remain parent-owned.
        local_caps=np.array([bed[z,x]+bank_allowance_m if not sea[z,x] else np.inf for z,x in e['points']])
        stages=np.minimum.accumulate(np.minimum(stages,local_caps))
        e['end_stage']=float(stages[-1])
        # Widen the analytic section when the declared original-material
        # incision limit does not accommodate the empirical depth.
        feasible = min(stage - (original[z,x]-3.) for (z,x),stage in zip(e['points'],stages))
        if feasible < .5: raise ValueError('insufficient incision for a wet channel')
        if feasible < depth:
            width *= depth/feasible
            depth = feasible
        for (z,x),pos,stage in zip(e['points'],smooth,stages):
            target=min(bed[z,x],stage-depth)
            if target < original[z,x]-3: raise ValueError('channel needs more than 3 m original incision')
            carved[z,x]=min(carved[z,x],target); river[z,x]=True
            rows.append((i,origin_xz_m[0]+pos[1]*spacing_m,origin_xz_m[1]+pos[0]*spacing_m,z,x,stage,width,depth,e['q']))
    sections=np.asarray(rows)
    sections=np.column_stack((sections,carved[sections[:,3].astype(int),sections[:,4].astype(int)]))
    deposit=np.maximum(bed-original,0); cut=bed-carved
    return {'bed_m':carved,'river':river,'sections':sections,'parent':np.array([e['parent'] for e in edges]),
            'length_m':np.array([e['length'] for e in edges]),'corridor_seed':seed,'inlet_zx':start,
            'outlet_zx':[p[-1] for p in paths], 'plain_radius_m':radius,
            'deposit_excavation_bulk_m3':float(np.minimum(cut,deposit).sum()*spacing_m**2),
            'original_excavation_bulk_m3':float(np.maximum(cut-deposit,0).sum()*spacing_m**2)}



















