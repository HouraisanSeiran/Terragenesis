"""Persistent delta state and conservative mapping to geographic solver nodes."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy import ndimage


def save_state(path, state, *, source_identity, geometry_identity):
    """Write exact non-pickle checkpoint; input identities are required SHA-256."""
    for value in (source_identity,geometry_identity):
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value): raise ValueError('invalid identity')
    path=Path(path)
    if path.exists(): raise FileExistsError(path)
    names=('loose_solid_m3','mobile_solid_m3','reach_bed_m','width_m')
    arrays={k:np.asarray(state[k],dtype=np.float64) for k in names}
    if any(a.ndim!=1 or not np.isfinite(a).all() for a in arrays.values()) or len({len(a) for a in arrays.values()})!=1:
        raise ValueError('invalid state arrays')
    if np.any(arrays['loose_solid_m3']<0) or np.any(arrays['mobile_solid_m3']<0) or np.any(arrays['width_m']<=0): raise ValueError('invalid state stock or width')
    time=float(state['time_seconds'])
    if not np.isfinite(time) or time<0: raise ValueError('invalid time')
    metadata=json.dumps({'schema':'forward-delta-state-v1','source_identity':source_identity,'geometry_identity':geometry_identity,'time_seconds':time},sort_keys=True)
    with path.open('xb') as f: np.savez_compressed(f,metadata=np.array(metadata),**arrays)


def load_state(path, *, source_identity, geometry_identity):
    with np.load(path,allow_pickle=False) as data:
        meta=json.loads(str(data['metadata']))
        if meta['schema']!='forward-delta-state-v1' or meta['source_identity']!=source_identity or meta['geometry_identity']!=geometry_identity:
            raise ValueError('checkpoint identity mismatch')
        return {'time_seconds':float(meta['time_seconds']),**{k:data[k].copy() for k in ('loose_solid_m3','mobile_solid_m3','reach_bed_m','width_m')}}


def classify_ocean(bed, valid, source_ocean):
    """Reclassify source-known submerged cells; disconnected wet remains unknown."""
    bed=np.asarray(bed,float);valid=np.asarray(valid,bool);source_ocean=np.asarray(source_ocean,bool)
    if bed.ndim!=2 or valid.shape!=bed.shape or source_ocean.shape!=bed.shape or not np.isfinite(bed[valid]).all(): raise ValueError('invalid source')
    wet=valid & source_ocean & (bed<0)
    edge=np.zeros(bed.shape,bool);edge[0,:]=edge[-1,:]=True;edge[:,0]=edge[:,-1]=True
    sea=ndimage.binary_propagation(wet & edge,mask=wet,structure=np.ones((3,3)))
    return sea,valid & (bed<0) & ~sea


def map_to_hydro_nodes(prepared, state, bar_solid_m3):
    """Partition exact reach and pixel stocks into prepared coast/river nodes.

    Bar stock at a partial river pixel is partitioned by the adapter's actual
    area fractions. A stock outside prepared coverage is rejected, not dropped.
    This function maps only; it does not seed or execute hydro.
    """
    p=prepared;n=int(p['n']); rows=p['node_rows']; branches=np.array([r['branch'] for r in rows],int)
    widths=np.array([r['width'] for r in rows],float); lengths=np.array([r['length'] for r in rows],float)
    loose=np.asarray(state['loose_solid_m3'],float); mobile=np.asarray(state['mobile_solid_m3'],float)
    bar=np.asarray(bar_solid_m3,float)
    if loose.ndim!=1 or mobile.shape!=loose.shape or np.any(loose<0) or np.any(mobile<0) or not np.isfinite(loose).all() or not np.isfinite(mobile).all(): raise ValueError('invalid reach stock')
    if bar.ndim!=2 or not np.isfinite(bar).all() or np.any(bar<0): raise ValueError('invalid bar stock')
    if len(branches)==0 or np.any(branches<0) or np.any(branches>=len(loose)): raise ValueError('invalid branch mapping')
    active=np.zeros(n+len(rows)); suspended=np.zeros_like(active)
    for i in range(len(loose)):
        nodes=np.flatnonzero(branches==i)
        if not len(nodes): raise ValueError('reach missing in hydro geometry')
        weight=widths[nodes]*lengths[nodes];weight/=weight.sum()
        active[n+nodes]+=loose[i]*weight;suspended[n+nodes]+=mobile[i]*weight
    lo=np.asarray(p['lo'],int); hi=np.asarray(p['hi'],int); shape=p['local_valid'].shape
    if np.any(lo<0) or hi[0]>bar.shape[0] or hi[1]>bar.shape[1]: raise ValueError('bar extent mismatch')
    outside=bar.copy();outside[lo[0]:hi[0],lo[1]:hi[1]]=0
    if np.any(outside): raise ValueError('bar stock outside hydro coverage')
    local=np.zeros(shape); local[:hi[0]-lo[0],:hi[1]-lo[1]]=bar[lo[0]:hi[0],lo[1]:hi[1]]
    if np.any((local>0)&~p['local_valid']): raise ValueError('bar stock in unknown cell')
    fraction=np.asarray(p['fraction']);owner=np.asarray(p['owner']);river=local*fraction
    if np.any((river>0)&(owner<0)): raise ValueError('unowned river fraction')
    active[n:]+=np.bincount(owner[owner>=0],weights=river[owner>=0],minlength=len(rows))
    coast=local-river; block=int(p['block']); nz=int(p['nz']); nx=int(p['nx'])
    active[:n]+=coast.reshape(nz,block,nx,block).transpose(0,2,1,3).reshape(n,-1).sum(axis=1)
    if not np.isclose(active.sum(),loose.sum()+bar.sum(),rtol=1e-12,atol=1e-8) or not np.isclose(suspended.sum(),mobile.sum(),rtol=1e-12,atol=1e-8): raise ValueError('stock mapping residual')
    digest=hashlib.sha256()
    for value in (branches,widths,lengths,owner,fraction): digest.update(np.ascontiguousarray(value).tobytes())
    return {'active_solid_m3':active,'mobile_solid_m3':suspended,'mapping_geometry_sha256':digest.hexdigest(),
            'time_seconds':float(state['time_seconds'])}


def hydraulic_feedback(hydro_dir, parent, expected_width_m):
    """Extract final geographic reach depths and head gradients for next transport.

    Fluxes are not yet exported for all river faces; formative Q remains the
    declared scenario. The magnitude of head gradient is a quasi-steady shear
    proxy, including tidal reversals, not a reconstructed downstream discharge.
    """
    from pathlib import Path
    p=Path(hydro_dir)
    with np.load(p/'geometry.npz',allow_pickle=False) as g, np.load(p/'series.npz',allow_pickle=False) as series, np.load(p/'checkpoint.npz',allow_pickle=False) as state:
        branches=g['node_branch'].astype(int); width=g['node_width_m'];length=g['node_length_m']
        expected=np.asarray(expected_width_m,float)
        if np.any(branches<0) or np.any(branches>=len(expected)) or not np.allclose(width,expected[branches],rtol=1e-10,atol=1e-10):
            raise ValueError('hydraulic geometry width differs from expected state')
        n=len(g['area_m2'])-len(branches); bed=g['floor_m']+state['bed_solid_m3']/((1-.4)*g['area_m2'])
        river_stage=series['river_node_stage_m'][-1];node_depth=np.maximum(river_stage-bed[n:],0.)
        fullstage=bed+state['water_m3']/g['area_m2'];fullstage[n:]=river_stage
        faces=g['river_faces'].astype(int); left=g['left'][faces];right=g['right'][faces]
        gradients=np.abs(fullstage[left]-fullstage[right])/g['river_distance_m']
        branch_gradient=[[] for _ in range(len(parent))]
        for a,b,slope in zip(left,right,gradients):
            for node in (a,b):
                if node>=n: branch_gradient[branches[node-n]].append(float(slope))
        depth=np.empty(len(parent));slope=np.empty(len(parent))
        for i in range(len(parent)):
            ix=np.flatnonzero(branches==i)
            if not len(ix) or not branch_gradient[i]: raise ValueError('missing hydraulic reach coverage')
            depth[i]=np.average(node_depth[ix],weights=length[ix]);slope[i]=np.mean(branch_gradient[i])
        return {'depth_m':depth,'friction_slope':slope,'time_seconds':float(state['time_s']),
                'policy':'geographic final stage minus final node bed, length weighted; absolute river-face head gradient proxy; Q remains formative scenario'}


def evolve_all_mouths(network, continuation, valid, ocean, origin, spacing, source_id, *, initial_cover_solid_m3=None):
    """Route every reach outlet through a shared persistent mouth-deposit grid.

    Multiple mouths within each day are applied in stable reach order. This is
    an operator-split approximation; each input is charged once and the one
    common cover stock prevents independent overlapping inventories.
    """
    from terrain_pipeline.common_infra import TerrainGrid
    from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval, simulate_fluvial_delta
    sec=network['sections'];parent=network['parent'];leaves=np.array([i for i in range(len(parent)) if i not in set(parent)],int)
    reaches=[sec[sec[:,0]==i] for i in leaves]; mouths=np.array([r[-1,3:5].astype(int) for r in reaches])
    margin=max(10,int(5000/spacing));lo=np.maximum(0,mouths.min(axis=0)-margin);hi=np.minimum(network['bed_m'].shape,mouths.max(axis=0)+margin+1)
    if np.prod(hi-lo)>65536: raise ValueError('all-mouth patch exceeds finite routing budget')
    sl=np.s_[lo[0]:hi[0],lo[1]:hi[1]];bed=np.asarray(network['bed_m'][sl],float);v=np.asarray(valid[sl],bool);sea=np.asarray(ocean[sl],bool)&v&(bed<=0)
    boundary=np.zeros(bed.shape,bool);boundary[0,:]=boundary[-1,:]=True;boundary[:,0]=boundary[:,-1]=True;exports=sea&boundary
    if not exports.any(): raise ValueError('mouth patch has no explicit ocean export')
    terrain=TerrainGrid(bed,v,origin[0]+lo[1]*spacing,origin[1]+lo[0]*spacing,spacing,spacing,'diagnostic_dem_proxy','forward-delta-all-mouths',source_id)
    head=max(.5,max(float(r[-1,5]) for r in reaches))
    boundary_config=FluvialDeltaBoundary(sea,exports,0.,head,'all surveyed outlets, connected source ocean')
    points=[]
    for z,x in mouths:
        z-=lo[0];x-=lo[1]
        candidates=[(z+dz,x+dx) for dz in (-1,0,1) for dx in (-1,0,1) if (dz or dx) and 0<=z+dz<bed.shape[0] and 0<=x+dx<bed.shape[1] and sea[z+dz,x+dx] and not exports[z+dz,x+dx]]
        if not candidates: raise ValueError('outlet lacks adjacent ocean cell')
        points.append(min(candidates,key=lambda cell:abs(bed[cell])))
    dt=continuation['interval_seconds']; outgoing=continuation['outgoing_solid_m3'];forcing=[]
    for day in range(len(outgoing)):
        for i,reach,cell in zip(leaves,reaches,points):
            forcing.append(FluvialDeltaInterval(tuple(int(v) for v in cell),float(reach[0,8])*dt,float(outgoing[day,i])))
    cover=None
    if initial_cover_solid_m3 is not None:
        cover_global=np.asarray(initial_cover_solid_m3,float)
        if cover_global.shape!=network['bed_m'].shape: raise ValueError('cover shape differs from bed')

        cover=cover_global[sl]
    result=simulate_fluvial_delta(terrain,boundary_config,forcing,FluvialDeltaConfig(porosity=.4,capacity_solid_per_water=1e-8,max_deposit_depth_per_interval_m=.25,max_reentrainment_depth_per_interval_m=.01,max_intervals=max(128,len(forcing))),initial_cover_solid_m3=cover)
    return {'result':result,'origin_zx':lo,'leaves':leaves,'mouth_zx':np.asarray(points)+lo,
            'forcing_water_m3':np.array([v.water_volume_m3 for v in forcing]),
            'forcing_solid_m3':np.array([v.sediment_solid_m3 for v in forcing]),
            'operator_order':'interval then ascending reach; sequential mouth passage', 'terrain':terrain, 'boundary':boundary_config, 'forcing':forcing}


def save_mouth_checkpoint(path, mouth):
    """Persist source terrain and all forcing for exact cover replay on resume."""
    terrain=mouth['terrain'];boundary=mouth['boundary'];forcing=mouth['forcing'];path=Path(path)
    if path.exists(): raise FileExistsError(path)
    meta={'source_sha256':terrain.source_sha256,'x0_m':terrain.x0_m,'z0_m':terrain.z0_m,'spacing_m':terrain.dx_m,
          'sea_level_m':boundary.sea_level_m,'river_head_m':boundary.river_head_m,'source_id':boundary.source_id}
    with path.open('xb') as f:
        np.savez_compressed(f,metadata=np.array(json.dumps(meta)),bed_m=terrain.elevation_m,valid=terrain.valid_mask,
          ocean=boundary.initial_ocean_mask,exports=boundary.ocean_export_mask,
          cells=np.array([v.inlet_cell for v in forcing],int),water=np.array([v.water_volume_m3 for v in forcing]),
          solid=np.array([v.sediment_solid_m3 for v in forcing]))


def replay_mouth_checkpoint(path, *, append_cells=(), append_water=(), append_solid=()):
    """Recompute saved history once plus appended mouth passages from bare bed."""
    from terrain_pipeline.common_infra import TerrainGrid
    from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary,FluvialDeltaConfig,FluvialDeltaInterval,simulate_fluvial_delta
    with np.load(path,allow_pickle=False) as d:
        m=json.loads(str(d['metadata']));bed=d['bed_m'].copy();valid=d['valid'].copy();ocean=d['ocean'].copy();exports=d['exports'].copy()
        cells=d['cells'].tolist()+list(append_cells);water=d['water'].tolist()+list(append_water);solid=d['solid'].tolist()+list(append_solid)
    if len(cells)!=len(water) or len(cells)!=len(solid): raise ValueError('incompatible appended forcing')
    terrain=TerrainGrid(bed,valid,m['x0_m'],m['z0_m'],m['spacing_m'],m['spacing_m'],'diagnostic_dem_proxy','forward-delta-all-mouths',m['source_sha256'])
    boundary=FluvialDeltaBoundary(ocean,exports,m['sea_level_m'],m['river_head_m'],m['source_id'])
    forcing=[FluvialDeltaInterval(tuple(int(v) for v in cell),float(w),float(s)) for cell,w,s in zip(cells,water,solid)]
    config=FluvialDeltaConfig(porosity=.4,capacity_solid_per_water=1e-8,max_deposit_depth_per_interval_m=.25,max_reentrainment_depth_per_interval_m=.01,max_intervals=max(128,len(forcing)))
    return simulate_fluvial_delta(terrain,boundary,forcing,config)



def advance_seeded_hydro(case, manifest, reach_state, bar_solid_m3, *, duration_s, dt_s,
                         source_water_m3_s, source_solid_m3_s, water_m3=None):
    """Seed geographic continuation with exact stocks once hydro exposes its API.

    If water_m3 is omitted, prepared geometric water is an explicitly new
    hydraulic initial condition, not continuation of previous unknown water.
    """
    from terrain_pipeline.large_delta_suite_tidal import prepare,prepare_continuation,advance_prepared
    from terrain_pipeline.large_delta_tidal_dynamics import State
    source=manifest['source']['source_identity'];spacing=max(600.,manifest['source']['spacing_m'])
    preliminary=prepare(case,manifest,hydro_spacing_m=spacing,reach_length_m=600.)
    mapped=map_to_hydro_nodes(preliminary,reach_state,bar_solid_m3)
    prepared=prepare_continuation(case,manifest,mapped['active_solid_m3'],source_identity=source,
                                  hydro_spacing_m=spacing,reach_length_m=600.)
    water=preliminary['state'].water_m3.copy() if water_m3 is None else np.asarray(water_m3,float).copy()
    if water.shape!=mapped['active_solid_m3'].shape or not np.isfinite(water).all() or np.any(water<0):
        raise ValueError('invalid exact hydraulic water stock')
    initial=State(float(reach_state['time_seconds']),water,mapped['active_solid_m3'].copy(),mapped['mobile_solid_m3'].copy())
    result=advance_prepared(prepared,initial,source_identity=source,geometry_id=prepared['geometry_id'],
          duration_s=duration_s,dt_s=dt_s,source_water_m3_s=source_water_m3_s,source_solid_m3_s=source_solid_m3_s)
    return result,prepared,mapped



def unpack_hydro_state(prepared, result, reach_count, output_shape):
    """Conservatively partition final hydro state to reaches and coastal pixels.

    Stocks follow current node ownership; historical material identity is not
    reconstructed. Coastal mobile remains a separate persistent raster stock.
    """
    p=prepared;state=result['state'];n=int(p['n']);rows=p['node_rows'];branches=np.array([r['branch'] for r in rows],int)
    if np.any(branches<0) or np.any(branches>=reach_count): raise ValueError('invalid hydro branch')
    active=np.bincount(branches,weights=state.bed_solid_m3[n:],minlength=reach_count)
    mobile=np.bincount(branches,weights=state.mobile_solid_m3[n:],minlength=reach_count)
    weights=np.array([r['length'] for r in rows]);bed_sum=np.bincount(branches,weights=result['node_bed_m'][n:]*weights,minlength=reach_count);lengths=np.bincount(branches,weights=weights,minlength=reach_count)
    if np.any(lengths<=0): raise ValueError('empty hydro reach')
    reach_bed=bed_sum/lengths
    coast=np.asarray(p['coast_area'],float);block=int(p['block']);nz=int(p['nz']);nx=int(p['nx'])
    blocks=coast.reshape(nz,block,nx,block).transpose(0,2,1,3).reshape(n,-1)
    totals=blocks.sum(axis=1)
    if np.any((totals==0)&((state.bed_solid_m3[:n]>0)|(state.mobile_solid_m3[:n]>0))): raise ValueError('coastal stock without mapped area')
    fractions=np.divide(blocks,totals[:,None],out=np.zeros_like(blocks),where=totals[:,None]>0)
    def raster(values):
        local=(fractions*values[:,None]).reshape(nz,nx,block,block).transpose(0,2,1,3).reshape(coast.shape)
        out=np.zeros(output_shape);lo=p['lo'];hi=p['hi'];out[lo[0]:hi[0],lo[1]:hi[1]]=local[:hi[0]-lo[0],:hi[1]-lo[1]]
        return out
    coastal_active=raster(state.bed_solid_m3[:n]);coastal_mobile=raster(state.mobile_solid_m3[:n])
    if not np.isclose(active.sum()+coastal_active.sum(),state.bed_solid_m3.sum(),rtol=1e-12,atol=1e-8) or not np.isclose(mobile.sum()+coastal_mobile.sum(),state.mobile_solid_m3.sum(),rtol=1e-12,atol=1e-8): raise ValueError('inverse stock mapping residual')
    return {'loose_solid_m3':active,'mobile_solid_m3':mobile,'reach_bed_m':reach_bed,
            'coastal_active_solid_m3':coastal_active,'coastal_mobile_solid_m3':coastal_mobile,
            'time_seconds':state.time_s}


def feedback_from_continuation(prepared, result, reach_count):
    """Map actual seeded hydro depth and river-face head gradient to reaches."""
    p=prepared;g=p['geom'];n=int(p['n']);branches=np.array([r['branch'] for r in p['node_rows']],int)
    lengths=np.array([r['length'] for r in p['node_rows']],float);node_depth=np.maximum(result['node_stage_m'][n:]-result['node_bed_m'][n:],0.)
    faces=g.river_faces;left=g.left[faces];right=g.right[faces];stage=result['node_stage_m'];gradient=np.abs(stage[left]-stage[right])/g.river_distance_m
    depth=np.zeros(reach_count);slope=np.zeros(reach_count)
    for i in range(reach_count):
        indices=np.flatnonzero(branches==i);face_mask=((left>=n)&(branches[np.maximum(left-n,0)]==i))|((right>=n)&(branches[np.maximum(right-n,0)]==i))
        if not len(indices) or not face_mask.any(): raise ValueError('missing reach feedback')
        depth[i]=np.average(node_depth[indices],weights=lengths[indices]);slope[i]=np.mean(gradient[face_mask])
    return {'depth_m':depth,'friction_slope':slope,'time_seconds':result['state'].time_s}



def project_hydro_to_native(prepared, result, shape):
    """Project actual node bed changes and water volumes onto native ownership."""
    p=prepared;n=int(p['n']);block=int(p['block']);nz=int(p['nz']);nx=int(p['nx']);lo=p['lo'];hi=p['hi']
    coast=p['coast_area'];river=p['river_area'];owner=p['owner'];cellarea=p['cell_area']
    bed_delta=result['node_bed_m']-p['base'];coast_delta=np.repeat(np.repeat(bed_delta[:n].reshape(nz,nx),block,0),block,1)
    river_delta=np.zeros(coast.shape);mask=owner>=0;river_delta[mask]=bed_delta[n:][owner[mask]]
    local_bed=p['local_bed']+np.where(coast>0,coast_delta,0.)
    cblocks=coast.reshape(nz,block,nx,block).transpose(0,2,1,3).reshape(n,-1);carea=cblocks.sum(axis=1)
    cw=np.divide(cblocks,carea[:,None],out=np.zeros_like(cblocks),where=carea[:,None]>0)*result['state'].water_m3[:n,None]
    local_water=cw.reshape(nz,nx,block,block).transpose(0,2,1,3).reshape(coast.shape)
    river_total=np.bincount(owner[mask],weights=river[mask],minlength=len(p['node_rows']))
    local_water[mask]+=river[mask]/river_total[owner[mask]]*result['state'].water_m3[n:][owner[mask]]
    def place(local):
        out=np.zeros(shape);out[lo[0]:hi[0],lo[1]:hi[1]]=local[:hi[0]-lo[0],:hi[1]-lo[1]];return out
    if not np.isclose(local_water.sum(),result['state'].water_m3.sum(),rtol=1e-12,atol=1e-6): raise ValueError('native projection lost water')
    return place(local_bed),place(local_water)


def water_to_hydro_nodes(prepared, native_water_m3):
    """Partition native water once by new hydro pixel ownership fractions."""
    p=prepared;water=np.asarray(native_water_m3,float);lo=p['lo'];hi=p['hi'];local=np.zeros(p['local_valid'].shape)
    if np.any(water<0) or not np.isfinite(water).all(): raise ValueError('invalid native water')
    outside=water.copy();outside[lo[0]:hi[0],lo[1]:hi[1]]=0
    if np.any(outside): raise ValueError('water outside prepared crop')
    local[:hi[0]-lo[0],:hi[1]-lo[1]]=water[lo[0]:hi[0],lo[1]:hi[1]]
    if np.any((local>0)&~p['local_valid']): raise ValueError('water on invalid pixels')
    f=p['fraction'];owner=p['owner'];river=local*f;mask=owner>=0;n=p['n'];block=p['block'];nz=p['nz'];nx=p['nx']
    coast=(local-river).reshape(nz,block,nx,block).transpose(0,2,1,3).reshape(n,-1).sum(axis=1)
    rivers=np.bincount(owner[mask],weights=river[mask],minlength=len(p['node_rows']))
    result=np.r_[coast,rivers]
    if not np.isclose(result.sum(),water.sum(),rtol=1e-12,atol=1e-6): raise ValueError('water remapping residual')
    return result



def ownership_snapshot(prepared):
    """Minimal native support needed for component-preserving overlap transfer."""
    p=prepared
    return {k:np.asarray(p[k]).copy() for k in ('lo','hi','owner','river_area','coast_area','block','nz','nx','n')} | {
        'branches':np.array([r['branch'] for r in p['node_rows']],dtype=np.int64)}


def transfer_owned_nodes(old, new, values):
    """Move node stocks by native support overlap, never across river/coast.

    Each river branch is an independent ownership class. If a new width removes
    a branch's old support, its remainder is redistributed within that branch.
    Coast nodes use same-cell overlap; absent overlap raises rather than inventing
    transport. Node stocks are interpreted as uniform over their old support.
    """
    from scipy import sparse
    values=np.asarray(values,float);on=int(old['n']);nn=int(new['n']);ob=np.asarray(old['branches']);nb=np.asarray(new['branches'])
    if values.shape!=(on+len(ob),) or np.any(values<0) or not np.isfinite(values).all(): raise ValueError('invalid node stock')
    if not np.array_equal(old['lo'],new['lo']) or not np.array_equal(old['hi'],new['hi']) or np.asarray(old['owner']).shape!=np.asarray(new['owner']).shape or int(old['block'])!=int(new['block']):
        raise ValueError('geometry crop changed; conservative remap unavailable')
    shape=np.asarray(old['owner']).shape;block=int(old['block']);nx=int(old['nx']);zz,xx=np.indices(shape);coarse=(zz//block)*nx+xx//block
    rows=[];cols=[];weights=[]
    for kind in ('coast','river'):
        oa=np.asarray(old[kind+'_area']);na=np.asarray(new[kind+'_area']);both=(oa>0)&(na>0)
        if kind=='coast': src=coarse;dst=coarse
        else:
            src=on+np.asarray(old['owner']);dst=nn+np.asarray(new['owner'])
            valid=both & (src>=on)&(dst>=nn);eq=np.zeros(shape,bool);eq[valid]=ob[src[valid]-on]==nb[dst[valid]-nn];both &= eq
        rows.extend(src[both].tolist());cols.extend(dst[both].tolist());weights.extend(np.minimum(oa[both],na[both]).tolist())
    matrix=sparse.coo_matrix((weights,(rows,cols)),shape=(len(values),nn+len(nb))).tocsr();tot=np.asarray(matrix.sum(axis=1)).ravel();missing=np.flatnonzero((tot==0)&(values>0))
    out=np.asarray(matrix.T.dot(np.divide(values,tot,out=np.zeros_like(values),where=tot>0))).ravel()
    for i in missing:
        if i<on: raise ValueError('coast water or stock lost native overlap')
        branch=ob[i-on];targets=np.flatnonzero(nb==branch)
        if not len(targets): raise ValueError('river branch lost all support')
        area=np.bincount(np.maximum(np.asarray(new['owner']).ravel(),0),weights=np.asarray(new['river_area']).ravel(),minlength=len(nb))[targets]
        if area.sum()<=0: raise ValueError('river branch has no area')
        out[nn+targets]+=values[i]*area/area.sum()
    if not np.isclose(out.sum(),values.sum(),rtol=1e-12,atol=1e-8):raise ValueError('ownership transfer lost stock')
    return out


def coast_grid_to_nodes(prepared, grid):
    """Map an already coastal stock only to coastal nodes."""
    p=prepared;grid=np.asarray(grid,float);lo=p['lo'];hi=p['hi'];local=np.zeros(p['local_valid'].shape)
    outside=grid.copy();outside[lo[0]:hi[0],lo[1]:hi[1]]=0
    if np.any(outside):raise ValueError('coastal stock outside hydro crop')
    local[:hi[0]-lo[0],:hi[1]-lo[1]]=grid[lo[0]:hi[0],lo[1]:hi[1]]
    if np.any((local>0)&(p['coast_area']<=0)):raise ValueError('coastal stock without coastal support')
    block=p['block'];n=p['n'];return local.reshape(p['nz'],block,p['nx'],block).transpose(0,2,1,3).reshape(n,-1).sum(axis=1)

