"""Finite branched sediment/section continuation for forward TD deltas.

One frozen-water routing interval is solved per reach. Downstream allocations
follow water fractions; each committed stock is carried into the next interval.
"""
import hashlib
import numpy as np
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment
from terrain_pipeline.channel_geometry import section_from_routed_budget


def evolve(network, *, intervals, interval_seconds, inlet_solid_m3_s,
           initial_alluvium_depth_m=.1, friction_slope=.0001,
           material_indices=(.35,.35,0.,.25), state=None, hydraulic_depth_m=None, hydraulic_slope=None, project_to_raster=True):
    """Return persistent reach stock, committed beds and lagged shared widths.

    Initial alluvium is an explicit finite active-layer scenario, not added on
    top of the geological inventory. Rock erosion is disabled. Inlet sediment
    is an explicit boundary rate, and each fork splits its upstream output by Q.
    """
    if (type(intervals) is not int or intervals < 1 or intervals > 128 or
        not np.isfinite([interval_seconds,inlet_solid_m3_s,initial_alluvium_depth_m,friction_slope]).all() or
        interval_seconds <= 0 or inlet_solid_m3_s < 0 or initial_alluvium_depth_m < 0 or friction_slope <= 0):
        raise ValueError('invalid continuation scenario')
    sec=np.asarray(network['sections'],float).copy(); parent=np.asarray(network['parent'],int)
    length=np.asarray(network['length_m'],float); count=len(parent)
    if count<1 or length.shape!=(count,) or np.any(length<=0) or parent[0]!=-1 or np.any(parent[1:]>=np.arange(1,count)) or np.any(parent[1:]<0):
        raise ValueError('one rooted parent-ordered reach tree required')
    ix=[np.flatnonzero(sec[:,0]==i) for i in range(count)]
    if any(len(a)<2 for a in ix): raise ValueError('each reach needs two sections')
    q=np.array([sec[a[0],8] for a in ix]); width=np.array([sec[a[0],6] for a in ix]); depth=np.array([sec[a[0],7] for a in ix])
    if np.any(q<=0) or np.any(width<=0) or np.any(depth<=0): raise ValueError('positive hydraulic geometry required')
    for i in range(count):
        child=np.flatnonzero(parent==i)
        if len(child) and not np.isclose(q[i],sum(q[child]),rtol=1e-9,atol=1e-9): raise ValueError('fork flow not conserved')
    mat=MaterialParameters(porosity=.4,sediment_critical_shear_pa=.05,sediment_erodibility_m_s_pa=1e-8,rock_erodibility_m_s_pa=0.,
                           transport_coefficient=1e-5,settling_velocity_m_s=.001,
                           provenance='declared finite channel active layer, no rock erosion')
    if state is None:
        stock=width*length*initial_alluvium_depth_m*(1-mat.porosity)
        mobile=np.zeros(count); reach_bed=np.array([np.mean(sec[a,9]) for a in ix]); start_time=0.
    else:
        stock=np.asarray(state['loose_solid_m3'],float).copy()
        mobile=np.asarray(state['mobile_solid_m3'],float).copy()
        reach_bed=np.asarray(state['reach_bed_m'],float).copy()
        width=np.asarray(state['width_m'],float).copy()
        start_time=float(state['time_seconds'])
        if any(v.shape != (count,) or not np.isfinite(v).all() for v in (stock,mobile,reach_bed,width)) or np.any(stock<0) or np.any(mobile<0) or np.any(width<=0) or not np.isfinite(start_time) or start_time<0:
            raise ValueError('invalid persistent reach state')
    if hydraulic_depth_m is not None:
        depth=np.asarray(hydraulic_depth_m,float)
        if depth.shape != (count,) or not np.isfinite(depth).all() or np.any(depth<0): raise ValueError('invalid hydraulic depths')
    slope=np.full(count,friction_slope) if hydraulic_slope is None else np.asarray(hydraulic_slope,float)
    if slope.shape != (count,) or not np.isfinite(slope).all() or np.any(slope<0): raise ValueError('invalid hydraulic slopes')
    initial=stock.copy(); initial_mobile=mobile.copy(); incoming_total=0.; exported_total=0.
    width_history=[width.copy()]; bed_history=[reach_bed.copy()]; stock_history=[stock.copy()]
    deposit_history=[]; erode_history=[]; out_history=[]; capacity_history=[]; incoming_history=[]
    token=hashlib.sha256(b'forward-delta-committed-reach-interval-v1').hexdigest()
    for step in range(intervals):
        pending=np.zeros(count); pending[0]=inlet_solid_m3_s*interval_seconds
        deposited=np.zeros(count); eroded=np.zeros(count); outgoing=np.zeros(count); capacity=np.zeros(count); newwidth=np.zeros(count); newbed=np.zeros(count)
        for i in range(count):
            area=width[i]*length[i]
            arr=route_daily_sediment(receiver=np.array([-1],dtype=np.int64),length_m=np.array([length[i]]),width_m=np.array([width[i]]),
                bed_elevation_m=np.array([reach_bed[i]]),water_depth_m=np.array([[depth[i]]]),water_q_m3_s=np.array([[q[i]]]),
                friction_slope=np.array([[slope[i]]]),time_seconds=np.array([start_time+step*interval_seconds,start_time+(step+1)*interval_seconds]),
                rock_floor_m=np.array([reach_bed[i]-stock[i]/((1-mat.porosity)*area)]),
                initial_alluvium_bulk_m3=np.array([stock[i]/(1-mat.porosity)]),initial_mobile_solid_m3=np.array([mobile[i]]),hardness=np.array([material_indices[0]]),material=mat,
                external_solid_m3_s=np.array([[pending[i]/interval_seconds]]),geometry_identity_sha256=token,hydraulic_identity_sha256=token,
                material_provenance=mat.provenance)['arrays']
            deposited[i]=arr['deposited_solid_m3'][0,0]; eroded[i]=arr['eroded_loose_solid_m3'][0,0]
            outgoing[i]=arr['outgoing_solid_m3'][0,0]; capacity[i]=arr['capacity_solid_m3'][0,0]
            stock[i]=arr['trace_loose_solid_m3'][-1,0]; mobile_before=mobile[i]; mobile[i]=arr['trace_mobile_solid_m3'][-1,0]; newbed[i]=arr['trace_bed_m'][-1,0]
            changed=section_from_routed_budget(q[i],*material_indices,incoming_solid_m3=pending[i] if i else 0.,
                external_solid_m3=pending[i] if i==0 else 0.,capacity_solid_m3=capacity[i],
                eroded_loose_solid_m3=eroded[i],eroded_rock_m3=0.,deposited_solid_m3=deposited[i],initial_mobile_solid_m3=mobile_before,max_width_m=2000.)
            newwidth[i]=float(changed.width_m)
            children=np.flatnonzero(parent==i)
            if len(children): pending[children]+=outgoing[i]*q[children]/q[i]
            else: exported_total+=outgoing[i]
        incoming_total+=inlet_solid_m3_s*interval_seconds
        deposit_history.append(deposited); erode_history.append(eroded); out_history.append(outgoing); capacity_history.append(capacity); incoming_history.append(pending)
        reach_bed=newbed; width=newwidth
        width_history.append(width.copy());bed_history.append(reach_bed.copy());stock_history.append(stock.copy())
    residual=float(initial.sum()+initial_mobile.sum()+incoming_total-stock.sum()-mobile.sum()-exported_total)
    if abs(residual)>1e-8*max(1.,initial.sum()+incoming_total): raise ValueError('branched solid ledger failed')
    # Update analytic sections and centre samples. Per-reach bed shift describes
    # physical section volume, never the full area of a coarse raster pixel.
    raster=network['bed_m'].copy()
    # A reach contributes at most once per pixel, even when repeated section
    # samples or a junction share the same raster location.
    shifts={}
    for i,indices in enumerate(ix):
        change=reach_bed[i]-bed_history[0][i]
        sec[indices,6]=width[i]
        sec[indices,9]+=change
        cells=np.unique(sec[indices,3:5].astype(int),axis=0)
        for z,x in cells:
            shifts.setdefault((int(z),int(x)),[]).append(change)
    if project_to_raster:
        for cell,changes in shifts.items():
            raster[cell]+=float(np.mean(changes))
    final_state={'time_seconds':start_time+intervals*interval_seconds,'loose_solid_m3':stock.copy(),
                 'mobile_solid_m3':mobile.copy(),'reach_bed_m':reach_bed.copy(),'width_m':width.copy()}
    return {'network':{**network,'sections':sec,'bed_m':raster},'width_history_m':np.array(width_history),
            'bed_history_m':np.array(bed_history),'stock_history_solid_m3':np.array(stock_history),
            'deposited_solid_m3':np.array(deposit_history),'eroded_solid_m3':np.array(erode_history),
            'outgoing_solid_m3':np.array(out_history),'incoming_solid_m3':np.array(incoming_history),
            'capacity_solid_m3':np.array(capacity_history),'state':final_state,'initial_solid_m3':float(initial.sum()+initial_mobile.sum()),
            'external_solid_m3':incoming_total,'exported_solid_m3':float(exported_total),'solid_residual_m3':residual,
            'porosity':mat.porosity,'interval_seconds':interval_seconds}




def evolve_mouth_bar(network, continuation, valid, ocean, origin, spacing, source_id):
    """Route one represented mouth's committed output through a persistent TD patch."""
    from terrain_pipeline.common_infra import TerrainGrid
    from terrain_pipeline.surface_rivers.metric_fluvial_delta import (
        FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval, simulate_fluvial_delta)
    parent=network['parent']; leaves=[i for i in range(len(parent)) if i not in set(parent)]
    leaf=max(leaves,key=lambda i:float(continuation['outgoing_solid_m3'][:,i].sum()))
    sec=network['sections']; reach=sec[sec[:,0]==leaf]; z,x=reach[-1,3:5].astype(int)
    bed=network['bed_m']; radius=min(80,max(15,int(12000/spacing)))
    lo=np.maximum([0,0],[z-radius,x-radius]);hi=np.minimum(bed.shape,[z+radius+1,x+radius+1]); sl=np.s_[lo[0]:hi[0],lo[1]:hi[1]]
    local_bed=np.asarray(bed[sl],dtype=float); local_valid=np.asarray(valid[sl],bool); local_ocean=np.asarray(ocean[sl],bool)&local_valid&(local_bed<=0.)
    perimeter=np.zeros(local_bed.shape,bool);perimeter[0,:]=perimeter[-1,:]=True;perimeter[:,0]=perimeter[:,-1]=True
    exports=local_ocean&perimeter
    if not exports.any(): raise ValueError('mouth patch lacks explicit ocean export boundary')
    terrain=TerrainGrid(local_bed,local_valid,origin[0]+lo[1]*spacing,origin[1]+lo[0]*spacing,
                        spacing,spacing,'diagnostic_dem_proxy','forward-delta-mouth',source_id)
    boundary=FluvialDeltaBoundary(local_ocean,exports,0.,max(.5,float(reach[-1,5])),'source-connected mouth scenario')
    dt=continuation['interval_seconds'];q=float(reach[0,8]);forcing=[]
    mouth=(int(z-lo[0]),int(x-lo[1]))
    candidates=[(mouth[0]+dz,mouth[1]+dx) for dz in (-1,0,1) for dx in (-1,0,1) if (dz or dx) and 0<=mouth[0]+dz<local_bed.shape[0] and 0<=mouth[1]+dx<local_bed.shape[1] and local_ocean[mouth[0]+dz,mouth[1]+dx] and not exports[mouth[0]+dz,mouth[1]+dx]]
    if not candidates: raise ValueError('mouth has no adjacent submerged ocean cell')
    mouth=min(candidates,key=lambda cell: abs(local_bed[cell]))
    for solid in continuation['outgoing_solid_m3'][:,leaf]:
        forcing.append(FluvialDeltaInterval(mouth,q*dt,float(solid)))
    config=FluvialDeltaConfig(porosity=.4,capacity_solid_per_water=1e-8,
                              max_deposit_depth_per_interval_m=.25,max_reentrainment_depth_per_interval_m=.01)
    result=simulate_fluvial_delta(terrain,boundary,forcing,config)
    return result,tuple(int(v) for v in lo),leaf


def main():
    """Build a checkpoint; geographic seed-state continuation is pending."""
    import argparse
    import json
    from pathlib import Path
    from terrain_pipeline.large_delta_suite import load_source
    from terrain_pipeline.large_delta_suite_tidal import prepare
    from terrain_pipeline.large_delta_state import (save_state, classify_ocean, map_to_hydro_nodes,
        evolve_all_mouths, save_mouth_checkpoint)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--intervals',type=int,default=3);parser.add_argument('--interval-seconds',type=float,default=86400.)
    parser.add_argument('--inlet-solid-m3-s',type=float,default=.002)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    manifest=json.loads((args.input/'manifest.json').read_text(encoding='utf-8-sig'))
    d=np.load(args.input/'product.npz'); source_manifest,_=load_source(manifest['source'])
    network={'sections':d['sections'],'parent':d['parent'],'length_m':d['reach_length_m'],'bed_m':d['final_bed_m'],'river':d['river']}
    result=evolve(network,intervals=args.intervals,interval_seconds=args.interval_seconds,inlet_solid_m3_s=args.inlet_solid_m3_s)
    n=result['network'];sea,unknown=classify_ocean(n['bed_m'],d['valid'],d['source_ocean'])
    mouth=evolve_all_mouths(n,result,d['valid'],sea,source_manifest['origin_xz_m'],source_manifest['spacing_m'],source_manifest['source_identity'])
    z,x=mouth['origin_zx'];h,w=mouth['result']['final_bed_m'].shape
    bar=np.zeros(n['bed_m'].shape);bar[z:z+h,x:x+w]=mouth['result']['stored_solid_m3']
    n['bed_m'][z:z+h,x:x+w]=mouth['result']['final_bed_m']
    n['sections'][:,9]=n['bed_m'][n['sections'][:,3].astype(int),n['sections'][:,4].astype(int)]
    sea,unknown=classify_ocean(n['bed_m'],d['valid'],d['source_ocean'])
    case={'final_bed_m':n['bed_m'],'valid':d['valid'],'ocean':sea,'sections':n['sections'],'parent':n['parent']}
    geometry=prepare(case,{'source':source_manifest,'scenario':manifest['scenario']},hydro_spacing_m=max(source_manifest['spacing_m'],600),reach_length_m=600.)
    mapped=map_to_hydro_nodes(geometry,result['state'],bar)
    gid=hashlib.sha256((args.input/'product.npz').read_bytes()).hexdigest()
    args.output.mkdir(parents=True)
    save_state(args.output/'reach-state.npz',result['state'],source_identity=source_manifest['source_identity'],geometry_identity=gid)
    save_mouth_checkpoint(args.output/'mouth-history.npz',mouth)
    np.savez_compressed(args.output/'hydro-seed-map.npz',active_solid_m3=mapped['active_solid_m3'],mobile_solid_m3=mapped['mobile_solid_m3'],time_seconds=mapped['time_seconds'])
    arrays={k:d[k] for k in d.files};arrays.update(final_bed_m=n['bed_m'],sections=n['sections'],ocean=sea,unknown_wet=unknown,bar_solid_m3=bar)
    np.savez_compressed(args.output/'product.npz',**arrays)
    np.savez_compressed(args.output/'evolution.npz',**{k:v for k,v in result.items() if isinstance(v,np.ndarray)})
    solid=mouth['result']['solid_ledger'];state=result['state']
    residual=result['initial_solid_m3']+result['external_solid_m3']-state['loose_solid_m3'].sum()-state['mobile_solid_m3'].sum()-solid['stored_solid_m3']-solid['ocean_export_solid_m3']-solid['unresolved_solid_m3']
    report={'source':source_manifest,'scenario':manifest['scenario'],'input_geometry_sha256':gid,
      'mapping_geometry_sha256':mapped['mapping_geometry_sha256'],'time_seconds':state['time_seconds'],
      'inlet_solid_m3_s':args.inlet_solid_m3_s,'reach_initial_solid_m3':result['initial_solid_m3'],
      'inlet_solid_m3':result['external_solid_m3'],'mouth_ledger':solid,'combined_solid_residual_m3':float(residual),
      'limitations':'All mouths share one operator-split cover state; unresolved stock remains escrow. Width reinitialization is a geometric parameterization and has no lateral-erosion debit. Geographic seed-state API is pending; no hydraulic event was run.'}
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'output':str(args.output),'combined_solid_residual_m3':residual,'status':'hydro seed-state interface pending'}))


if __name__=='__main__':
    main()



