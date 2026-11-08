"""Checkpointed finite delta sediment and geographic tide operator splitting."""
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.large_delta_evolution import evolve
from terrain_pipeline.large_delta_state import (classify_ocean,evolve_all_mouths,map_to_hydro_nodes,
    project_hydro_to_native,unpack_hydro_state,feedback_from_continuation,ownership_snapshot,transfer_owned_nodes,coast_grid_to_nodes)
from terrain_pipeline.large_delta_suite_tidal import prepare,bind_continuation,advance_prepared
from terrain_pipeline.large_delta_tidal_dynamics import State


def cycle(model, manifest, *, sediment_seconds=3600., hydro_seconds=60., dt_s=5., solid_m3_s=.002):
    """Advance reach sediment, every mouth, then geographic tide without stock resets."""
    n=model['network'];valid=model['valid'];source_ocean=model['source_ocean'];source=manifest['source'];reach=model.get('reach_state')
    kwargs={}
    if model.get('feedback') is not None:
        kwargs=dict(hydraulic_depth_m=model['feedback']['depth_m'],hydraulic_slope=model['feedback']['friction_slope'])
    sed=evolve(n,intervals=1,interval_seconds=sediment_seconds,inlet_solid_m3_s=solid_m3_s,state=reach,project_to_raster=False,**kwargs)
    n=sed['network'];state=sed['state'];sea,unknown=classify_ocean(n['bed_m'],valid,source_ocean)
    coast=model['coast_active'].copy();coast_mobile=model['coast_mobile'].copy()
    mouth=evolve_all_mouths(n,sed,valid,sea,source['origin_xz_m'],source['spacing_m'],source['source_identity'],initial_cover_solid_m3=coast)
    z,x=mouth['origin_zx'];h,w=mouth['result']['final_bed_m'].shape;sl=np.s_[z:z+h,x:x+w]
    n['bed_m'][sl]=mouth['result']['final_bed_m'];coast[sl]=mouth['result']['stored_solid_m3']
    sea,unknown=classify_ocean(n['bed_m'],valid,source_ocean)
    case={'final_bed_m':n['bed_m'],'valid':valid,'ocean':sea,'sections':n['sections'],'parent':n['parent']}
    raw=prepare(case,manifest,hydro_spacing_m=max(600.,source['spacing_m']),reach_length_m=600.)
    new_support=ownership_snapshot(raw)
    ncoast=int(raw['n']); branches=new_support['branches']; count=len(n['parent'])
    if model.get('owned') is None:
        mapped=map_to_hydro_nodes(raw,state,np.zeros_like(coast))
        active=mapped['active_solid_m3'];mobile=mapped['mobile_solid_m3']
        water=raw['state'].water_m3.copy()
    else:
        prior=model['owned'];support=model['support']
        active=transfer_owned_nodes(support,new_support,prior['active'])
        mobile=transfer_owned_nodes(support,new_support,prior['mobile'])
        water=transfer_owned_nodes(support,new_support,prior['water'])
        # Reach sediment exchange acts on its own branch nodes; preserve the
        # prior distribution within the branch when applying its new total.
        for i in range(count):
            nodes=ncoast+np.flatnonzero(branches==i)
            for array,target in ((active,state['loose_solid_m3'][i]),(mobile,state['mobile_solid_m3'][i])):
                total=array[nodes].sum()
                if total>0: array[nodes]*=target/total
                elif target>0:
                    areas=np.array([raw['node_rows'][j-ncoast]['width']*raw['node_rows'][j-ncoast]['length'] for j in nodes])
                    array[nodes]=target*areas/areas.sum()
    # Fluvial coastal cover is already coastal stock, never repartition it to river.
    active[:ncoast]=coast_grid_to_nodes(raw,coast)
    geom=bind_continuation(raw,active,source_identity=source['source_identity'])
    hydro_state=State(state['time_seconds'],water,active,mobile)
    q=float(n['sections'][n['sections'][:,0]==0][0,8])
    hydro=advance_prepared(geom,hydro_state,source_identity=source['source_identity'],geometry_id=geom['geometry_id'],duration_s=hydro_seconds,dt_s=dt_s,source_water_m3_s=q,source_solid_m3_s=solid_m3_s)
    transferred=unpack_hydro_state(geom,hydro,len(n['parent']),n['bed_m'].shape);feedback=feedback_from_continuation(geom,hydro,len(n['parent']))
    projected,water=project_hydro_to_native(geom,hydro,n['bed_m'].shape);lo=geom['lo'];hi=geom['hi'];region=np.s_[lo[0]:hi[0],lo[1]:hi[1]];n['bed_m'][region]=projected[region]
    # Keep subpixel analytic beds distinct from the area-weighted native DEM.
    branches=np.array([row['branch'] for row in geom['node_rows']]);weights=np.array([row['length'] for row in geom['node_rows']]);cn=geom['n']
    for i in range(len(n['parent'])):
        ix=n['sections'][:,0]==i;nodes=branches==i
        previous=float(np.mean(n['sections'][ix,9]));n['sections'][ix,9]+=transferred['reach_bed_m'][i]-previous
        n['sections'][ix,5]=np.average(hydro['node_stage_m'][cn:][nodes],weights=weights[nodes])
    final_reach={k:transferred[k] for k in ('loose_solid_m3','mobile_solid_m3','reach_bed_m','time_seconds')};final_reach['width_m']=state['width_m']
    barledger=mouth['result']['solid_ledger'];escrow=model['escrow']+barledger['unresolved_solid_m3'];
    initial=(sed['initial_solid_m3']+model['coast_active'].sum()+model['coast_mobile'].sum()+model['escrow'])
    input_solid=sed['external_solid_m3']+hydro['ledger']['source_solid_m3'];export=barledger['ocean_export_solid_m3']+hydro['ledger']['sea_solid_out_m3']
    final=(final_reach['loose_solid_m3'].sum()+final_reach['mobile_solid_m3'].sum()+transferred['coastal_active_solid_m3'].sum()+transferred['coastal_mobile_solid_m3'].sum()+escrow)
    residual=float(initial+input_solid-export-final)
    if abs(residual)>1e-7*max(1.,initial+input_solid): raise ValueError('coupled solid ledger mismatch')
    return {'network':n,'valid':valid,'source_ocean':source_ocean,'reach_state':final_reach,
      'coast_active':transferred['coastal_active_solid_m3'],'coast_mobile':transferred['coastal_mobile_solid_m3'],
      'water':water,'feedback':feedback,'escrow':escrow,'ocean':sea,'unknown_wet':unknown,
      'source_identity':model['source_identity'],'input_sha256':model['input_sha256'],
      'owned':{'water':hydro['state'].water_m3.copy(),'active':hydro['state'].bed_solid_m3.copy(),'mobile':hydro['state'].mobile_solid_m3.copy()},'support':new_support,
      'ledger':{'initial_solid_m3':float(initial),'source_solid_m3':float(input_solid),'sea_export_solid_m3':float(export),'final_solid_m3':float(final),'residual_solid_m3':residual,'hydro_water_residual_m3':hydro['ledger']['water_residual_m3'], 'water_initial_m3':hydro['ledger']['initial_water_m3'], 'water_final_m3':float(hydro['state'].water_m3.sum()), 'hydro_source_water_m3':hydro['ledger']['source_water_m3'], 'sea_water_in_m3':hydro['ledger']['sea_water_in_m3'], 'sea_water_out_m3':hydro['ledger']['sea_water_out_m3'], 'sediment_phase_assumed_water_in_m3':q*sediment_seconds, 'sediment_phase_assumed_water_out_m3':q*sediment_seconds, 'sediment_phase_water_storage_change_m3':0.,'mouth_unresolved_solid_m3':barledger['unresolved_solid_m3'],'hydro_geometry_id':geom['geometry_id'], 'first_water_is_declared_initial_state':model['water'] is None}}


def save_model(path, model):
    n=model['network'];s=model['reach_state'];f=model['feedback'];path=Path(path)
    if path.exists(): raise FileExistsError(path)
    with path.open('xb') as stream:
        np.savez_compressed(stream,**{'net_'+k:v for k,v in n.items()},valid=model['valid'],source_ocean=model['source_ocean'],
          **{'state_'+k:v for k,v in s.items()},coast_active=model['coast_active'],coast_mobile=model['coast_mobile'],
          water=model['water'],**{'owned_'+k:v for k,v in model['owned'].items()},**{'support_'+k:v for k,v in model['support'].items()},feedback_depth=f['depth_m'],feedback_slope=f['friction_slope'],escrow=model['escrow'],source_identity=np.array(model['source_identity']),input_sha256=np.array(model['input_sha256']))


def load_model(path):
    with np.load(path,allow_pickle=False) as a:
        n={k[4:]:a[k].copy() for k in a.files if k.startswith('net_')};s={k[6:]:(float(a[k]) if a[k].ndim==0 else a[k].copy()) for k in a.files if k.startswith('state_')}
        return {'network':n,'valid':a['valid'].copy(),'source_ocean':a['source_ocean'].copy(),'reach_state':s,
         'coast_active':a['coast_active'].copy(),'coast_mobile':a['coast_mobile'].copy(),'water':a['water'].copy(),
         'owned':{k[6:]:a[k].copy() for k in a.files if k.startswith('owned_')},'support':{k[8:]:a[k].copy() for k in a.files if k.startswith('support_')},
         'feedback':{'depth_m':a['feedback_depth'].copy(),'friction_slope':a['feedback_slope'].copy()},'escrow':float(a['escrow']),'source_identity':str(a['source_identity']),'input_sha256':str(a['input_sha256'])}


def main():
    import argparse
    import hashlib
    from terrain_pipeline.large_delta_suite import load_source
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--resume',type=Path);parser.add_argument('--cycles',type=int,default=2);parser.add_argument('--sediment-seconds',type=float,default=3600.);parser.add_argument('--hydro-seconds',type=float,default=60.);parser.add_argument('--solid-rate',type=float,default=.002);parser.add_argument('--hydro-dt',type=float,default=5.)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    m=json.loads((args.input/'manifest.json').read_text(encoding='utf-8-sig'));source,_=load_source(m['source']);manifest={'source':source,'scenario':m['scenario']};d=np.load(args.input/'product.npz')
    input_sha=hashlib.sha256((args.input/'product.npz').read_bytes()).hexdigest()
    if args.resume:
        model=load_model(args.resume)
        if model['source_identity']!=source['source_identity'] or model['input_sha256']!=input_sha: raise ValueError('restart source or input identity mismatch')
    else:
        n={'sections':d['sections'].copy(),'parent':d['parent'].copy(),'length_m':d['reach_length_m'].copy(),'bed_m':d['geological_bed_m'].copy(),'river':d['river'].copy()};n['sections'][:,5]=n['sections'][:,9]+n['sections'][:,7];model={'network':n,'valid':d['valid'].copy(),'source_ocean':d['source_ocean'].copy(),'reach_state':None,'coast_active':np.zeros(n['bed_m'].shape),'coast_mobile':np.zeros(n['bed_m'].shape),'water':None,'feedback':None,'owned':None,'support':None,'escrow':0.,'source_identity':source['source_identity'],'input_sha256':input_sha}
    args.output.mkdir(parents=True);ledgers=[]
    for i in range(args.cycles):
        model=cycle(model,manifest,sediment_seconds=args.sediment_seconds,hydro_seconds=args.hydro_seconds,dt_s=args.hydro_dt,solid_m3_s=args.solid_rate);ledgers.append(model['ledger']);save_model(args.output/('cycle-%03d.npz'%(i+1)),model)
    (args.output/'manifest.json').write_text(json.dumps({'source_identity':source['source_identity'],'cycles':ledgers,'time_seconds':model['reach_state']['time_seconds'],'scenario':{'sediment_seconds_per_cycle':args.sediment_seconds,'hydro_seconds_per_cycle':args.hydro_seconds,'solid_m3_s':args.solid_rate,'hydro_dt_s':args.hydro_dt,'initial_river_stage':'analytic bed plus declared design depth; initial condition, not solved native stage','semantics':'Frozen-water reach and mouth sediment passage, then explicit tide; tidal dynamics are not simulated during sediment passage. Width reinitialization is geometric and does not debit lateral erosion.'}},indent=2),encoding='utf8')
    print(json.dumps(ledgers,indent=2))


if __name__=='__main__': main()



