"""Independent, scenario geometry for a surveyed river-to-coast connection.

Coordinates are absolute x,z metres; arrays are indexed z,x.  The surface is
an imposed geometric stage, not a hydraulic solution or observed water level.
"""
import numpy as np
import heapq
from dataclasses import replace
from scipy.ndimage import map_coordinates, distance_transform_edt, minimum_filter
from scipy.spatial import cKDTree
from terrain_pipeline.channel_geometry import formative_section
from terrain_pipeline.channel_geometry import channel_section_cut
from .surface_rivers.metric_dynamic_feedback import normal_depth
from .surface_rivers.metric_coastal_transport import flowing_reach_stage
from .coastal_marine_sediment import RiverPacket, MarineConfig, advance


def refine_valley(terrain_m, origin_xz_m, spacing_m, coarse_path_xz_m, corridor_m=450.):
    """Bounded 8-neighbour valley search near the surveyed mainstem.

    Cost penalises length, local relief above a neighbourhood minimum and
    uphill elevation gains, following the existing bounded reroute idea.
    """
    bed = np.asarray(terrain_m, float); path = np.asarray(coarse_path_xz_m, float)
    if bed.ndim != 2 or not np.isfinite(bed).all() or path.ndim != 2 or path.shape[1] != 2 or len(path)<2 or spacing_m<=0 or corridor_m<=0:
        raise ValueError('invalid valley search inputs')
    origin=np.asarray(origin_xz_m,float)
    length=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
    samples=np.linspace(0,length[-1],int(length[-1]/(spacing_m/2))+2)
    x=np.interp(samples,length,path[:,0]); z=np.interp(samples,length,path[:,1])
    col=np.rint((x-origin[0])/spacing_m).astype(int); row=np.rint((z-origin[1])/spacing_m).astype(int)
    if (row.min()<0 or col.min()<0 or row.max()>=bed.shape[0] or col.max()>=bed.shape[1]):
        raise ValueError('survey path outside valley grid')
    seed=np.zeros(bed.shape,bool); seed[row,col]=True
    distance=distance_transform_edt(~seed)*spacing_m
    allowed=distance<=corridor_m
    relief=bed-minimum_filter(bed,size=31,mode='nearest')
    start=(int(row[0]),int(col[0])); end=(int(row[-1]),int(col[-1]))
    costs=np.full(bed.shape,np.inf); costs[start]=0.; previous=np.full(bed.shape,-1,np.int64)
    queue=[(0.,start[0],start[1])]; ny,nx=bed.shape
    while queue:
        cost,r,c=heapq.heappop(queue)
        if cost!=costs[r,c]: continue
        if (r,c)==end: break
        for dr,dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            rr=r+dr; cc=c+dc
            if not (0<=rr<ny and 0<=cc<nx and allowed[rr,cc]): continue
            step=spacing_m*np.hypot(dr,dc)
            rise=max(0.,bed[rr,cc]-bed[r,c])
            candidate=cost+step*(1.+max(0.,relief[rr,cc])/40.)+rise*12.
            if candidate<costs[rr,cc]:
                costs[rr,cc]=candidate; previous[rr,cc]=r*nx+c
                heapq.heappush(queue,(candidate,rr,cc))
    if not np.isfinite(costs[end]): raise ValueError('no path inside corridor')
    nodes=[]; cell=end
    while cell!=start:
        nodes.append(cell); cell=divmod(int(previous[cell]),nx)
    nodes.append(start); nodes.reverse()
    result=origin+np.column_stack(([c for r,c in nodes],[r for r,c in nodes]))*spacing_m
    result[0]=path[0]; result[-1]=path[-1]
    return result, float(np.max(distance[tuple(np.asarray(nodes).T)]))


def deliver_packets(state, packets, *, duration_s, travel_time_s, config=None):
    """Register finite upstream packets with a fixed delay and advance the sea.

    MarineState stores packet schedules and delivery progress; save_state/load_state
    therefore resume transit without replay. Unknown packet quantities stay None.
    Input intervals must start at or after the current state time.
    """
    if not np.isfinite([duration_s, travel_time_s]).all() or duration_s <= 0 or travel_time_s < 0:
        raise ValueError('invalid duration or travel time')
    shifted = []
    for packet in packets:
        if packet.start_s < state.time_s:
            raise ValueError('upstream packet starts before current state')
        shifted.append(replace(packet, start_s=packet.start_s + travel_time_s,
                               end_s=packet.end_s + travel_time_s))
    if config is None:
        config = MarineConfig(sea_level_m=0., step_s=9000., settling_rate_s=1e-5,
                              transverse_diffusivity_m2_s=0.)
    return advance(state, shifted, duration_s, config)


def deliver_scenario(state, *, input_id, duration_s, travel_time_s, q_m3_s,
                     solid_rate_m3_s, width_m, depth_m, inlet_zx=(214, 401)):
    """Delay finite constant input once, then hand its arrival to MarineState.

    Delayed packet progress is stored in the returned MarineState. Excavation
    remains a separate unknown-destination stock. This is not routing
    of a solved hydrograph or an equilibrium suspended-sediment model.
    """
    values=[duration_s,travel_time_s,q_m3_s,solid_rate_m3_s,width_m,depth_m]
    if not input_id or not np.isfinite(values).all() or duration_s<=0 or travel_time_s<0 or q_m3_s<=0 or solid_rate_m3_s<0 or width_m<=0 or depth_m<=0:
        raise ValueError('invalid finite river input')
    if any(p['input_id']==input_id for p in state.consumed_packets):
        raise ValueError('duplicate input id')
    packet=RiverPacket(input_id,'rank4-constant-scenario',state.time_s,
        state.time_s+duration_s,int(inlet_zx[0]),int(inlet_zx[1]),q_m3_s*duration_s,
        solid_rate_m3_s*duration_s,True,(10200.,1200.),width_m,depth_m)
    config=MarineConfig(sea_level_m=0.,step_s=9000.,settling_rate_s=1e-5,
                        transverse_diffusivity_m2_s=0.)
    result=deliver_packets(state,[packet],duration_s=duration_s,travel_time_s=travel_time_s,config=config)
    arrival=max(0.,duration_s-travel_time_s)
    record=next(p for p in result.consumed_packets if p['input_id']==input_id)
    ledger=dict(input_id=input_id,start_s=state.time_s,end_s=result.time_s,
        travel_time_s=travel_time_s,upstream_water_m3=q_m3_s*duration_s,
        upstream_solid_m3=solid_rate_m3_s*duration_s,
        in_transit_water_m3=q_m3_s*(duration_s-arrival),
        in_transit_solid_m3=solid_rate_m3_s*(duration_s-arrival),
        marine_delivered_water_m3=record['delivered_water_m3'],
        marine_delivered_solid_m3=record['delivered_solid_m3'],
        marine_pending_solid_m3=record['pending_solid_m3'],config=vars(config))
    return result,ledger


def reconcile_sections(result, origin_xz_m, spacing_m, q_m3_s=150., roughness=.035):
    """Raise stage for Manning capacity of sampled actual transverse sections.

    Uses one reach-mean friction slope and an upstream envelope, not a
    gradually-varied-flow solution. The port stage is fixed and must pass Q.
    """
    path=result['path_xz_m']; distance=result['distance_m']; bed=result['bed_m']
    tangent=np.gradient(path,axis=0); tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    half_width = float(result['width_m']) / 2
    # Include the channel shoulders and terrain beyond both banks.
    extent = half_width + max(spacing_m, half_width * .25)
    offsets = np.linspace(-extent, extent, int(np.ceil(2 * extent / 2.)) + 1)
    x=path[:,0,None]-tangent[:,1,None]*offsets
    z=path[:,1,None]+tangent[:,0,None]*offsets
    sections=map_coordinates(bed,[(z-origin_xz_m[1])/spacing_m,(x-origin_xz_m[0])/spacing_m],order=1)
    grade=(result['target_bed_m'][0]-result['target_bed_m'][-1])/distance[-1]
    if grade<=0: raise ValueError('positive mean bed slope required')
    def capacities(level):
        depth=np.maximum(level[:,None]-sections,0.)
        area=np.trapezoid(depth,offsets,axis=1)
        wet=(depth[:,:-1]>0)|(depth[:,1:]>0)
        perimeter=np.sum(np.hypot(np.diff(offsets)[None,:],np.diff(sections,axis=1))*wet,axis=1)
        radius=np.divide(area,perimeter,out=np.zeros_like(area),where=perimeter>0)
        return area*radius**(2/3)*np.sqrt(grade)/roughness
    low=np.min(sections,axis=1); high=np.maximum(result['stage_m']+20,low+20)
    if np.any(capacities(high)<q_m3_s): raise ValueError('section capacity unresolved within 20 m')
    for _ in range(32):
        middle=(low+high)/2; enough=capacities(middle)>=q_m3_s
        high=np.where(enough,middle,high); low=np.where(enough,low,middle)
    if capacities(result['stage_m'])[-1]<q_m3_s:
        raise ValueError('fixed sea boundary cannot pass scenario discharge')
    # Margin covers interpolation between discrete cross-section stations.
    levels=np.maximum(result['stage_m'],high+.25); levels[-1]=result['stage_m'][-1]
    levels=np.maximum.accumulate(levels[::-1])[::-1]
    zz,xx=np.indices(bed.shape)
    xy=np.column_stack((origin_xz_m[0]+xx.ravel()*spacing_m,origin_xz_m[1]+zz.ravel()*spacing_m))
    dist,index=cKDTree(path).query(xy,workers=1)
    surface=np.full(bed.size,np.nan); inside=dist<=extent
    surface[inside]=levels[index[inside]]
    surface=surface.reshape(bed.shape); wet=np.isfinite(surface)&(surface>bed)
    surface[~wet]=np.nan
    out=dict(result); out.update(stage_m=levels,water_surface_m=surface,wet=wet,
                                 friction_slope=grade,section_node_capacity_m3_s=capacities(levels))
    return out


def connect(terrain_m, origin_xz_m, spacing_m, path_xz_m, *, mouth_stage_m=0.,
            q_m3_s=150., bed_resistance=.5, bank_resistance=.5,
            fracture=.25, bank_cohesion=.3, water_depth_m=2., hydraulic=False):
    """Carve a finite trapezoid into a copy and return the raster and ledger.

    The monotone scenario stage is raised upstream only as needed to limit
    incision; it is tied to the specified mouth stage. Segment projection is
    continuous; no 600 m cell is treated as a river width.
    """
    terrain = np.asarray(terrain_m, float)
    path = np.asarray(path_xz_m, float)
    if terrain.ndim != 2 or not np.isfinite(terrain).all() or path.ndim != 2 or path.shape[1] != 2 or len(path) < 2 or not np.isfinite(path).all() or spacing_m <= 0 or water_depth_m <= 0:
        raise ValueError('finite terrain, spacing, depth and path required')
    distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    if np.any(np.diff(distance) <= 0):
        raise ValueError('path segments must have positive length')
    indices = [(path[:, 1]-origin_xz_m[1])/spacing_m, (path[:, 0]-origin_xz_m[0])/spacing_m]
    if np.any(indices[0] < 0) or np.any(indices[1] < 0) or np.any(indices[0] > terrain.shape[0]-1) or np.any(indices[1] > terrain.shape[1]-1):
        raise ValueError('path outside terrain')
    ground = map_coordinates(terrain, indices, order=1)
    width = float(formative_section(q_m3_s, bed_resistance, bank_resistance, fracture, bank_cohesion).width_m)
    if hydraulic:
        grade=max((ground[0]-ground[-1])/distance[-1],1e-5)
        water_depth_m=max(normal_depth(q_m3_s,width,grade,roughness=.035),
                          (q_m3_s**2/(9.81*width**2))**(1/3))
    stage = np.empty(len(path)); stage[-1] = mouth_stage_m
    for i in range(len(path)-2, -1, -1):
        stage[i] = max(stage[i+1] + .0001*(distance[i+1]-distance[i]), ground[i]-water_depth_m)
    target = stage-water_depth_m
    # Terminate on the saved port bed if already wet; do not excavate the port.
    target[-1] = min(ground[-1], mouth_stage_m-0.01)
    if hydraulic:
        stage, control = flowing_reach_stage(target,distance,width,q_m3_s,mouth_stage_m)
    cut = np.zeros_like(terrain); surface = np.full_like(terrain, np.nan)
    nearest = np.full_like(terrain, np.inf)
    ox, oz = origin_xz_m
    for i, (a, b) in enumerate(zip(path[:-1], path[1:])):
        margin = width/2 + spacing_m
        x0 = max(0, int(np.floor((min(a[0], b[0])-margin-ox)/spacing_m)))
        x1 = min(terrain.shape[1], int(np.ceil((max(a[0], b[0])+margin-ox)/spacing_m))+1)
        z0 = max(0, int(np.floor((min(a[1], b[1])-margin-oz)/spacing_m)))
        z1 = min(terrain.shape[0], int(np.ceil((max(a[1], b[1])+margin-oz)/spacing_m))+1)
        x = ox + np.arange(x0,x1)*spacing_m; z = oz + np.arange(z0,z1)*spacing_m
        xx, zz = np.meshgrid(x,z); d = b-a
        t = np.clip(((xx-a[0])*d[0]+(zz-a[1])*d[1])/np.dot(d,d),0,1)
        offset = np.hypot(xx-a[0]-t*d[0],zz-a[1]-t*d[1])
        local_stage = stage[i]*(1-t)+stage[i+1]*t
        local_bed = target[i]*(1-t)+target[i+1]*t
        local_ground = terrain[z0:z1,x0:x1]
        depth = np.maximum(local_ground-local_bed,0.)
        proposed = channel_section_cut(offset,width,depth)
        old = cut[z0:z1,x0:x1]; take = proposed > old
        old[take] = proposed[take]
        section_surface = surface[z0:z1,x0:x1]
        nearest_local = nearest[z0:z1,x0:x1]
        closest = (offset <= width/2) & (offset < nearest_local)
        section_surface[closest] = local_stage[closest]
        nearest_local[closest] = offset[closest]
    bed = terrain-cut
    wet = np.isfinite(surface) & (bed < surface)
    surface[~wet] = np.nan
    return dict(bed_m=bed, cut_m=cut, water_surface_m=surface, wet=wet,
                path_xz_m=path, distance_m=distance, ground_m=ground,
                stage_m=stage, target_bed_m=target, width_m=width,
                control_depth_m=water_depth_m,
                removed_bulk_m3=float(cut.sum()*spacing_m**2))

