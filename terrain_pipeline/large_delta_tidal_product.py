"""Prepare, run and publish the reduced tidal storage-graph experiment."""
from __future__ import annotations
import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
import numpy as np
from scipy.ndimage import binary_propagation
from terrain_pipeline.large_delta_tidal_source import load_source
from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, bed_elevation, step, tide_stage, save_checkpoint, load_checkpoint


@dataclass(frozen=True)
class Config:
    block: int = 10
    dt_s: int = 300
    tide: bool = True
    coastal_conductance_m2_s: float = 40.
    river_conductance_m2_s: float = 45.
    sea_conductance_m2_s: float = 100.


def prepare(source, config=Config()):
    """Aggregate the coastal window and retain separate analytic river storage."""
    bounds = source['manifest']['patches']['coastal_band_z0_z1_x0_x1']
    b = config.block
    z0, z1, x0, x1 = bounds
    z0 = max(0, (z0//b)*b-b*2); x0 = max(0, (x0//b)*b-b*2)
    z1 = min(2000, ((z1+b-1)//b)*b+b*2); x1 = min(2000, ((x1+b-1)//b)*b+b*2)
    nz, nx = (z1-z0)//b, (x1-x0)//b
    def blocks(array):
        return array[z0:z1,x0:x1].reshape(nz,b,nx,b)
    valid = blocks(source['valid']).all(axis=(1,3))
    bed = blocks(source['initial_bed_m']).mean(axis=(1,3))
    floor = blocks(source['active_layer']['floor_m']).mean(axis=(1,3))
    ocean = blocks(source['source_ocean']).any(axis=(1,3)) & valid
    n = nz*nx
    area = np.full(n, (30*b)**2, float)
    parent = source['parent']; leaves = source['leaf_indices']
    segments = source['reach_segments']; widths = source['network']['branch_width_m']; lengths = source['network']['branch_length_m']
    # The analytic channel area is width * length, independent of coarse cells.
    river_area = widths*lengths
    river_bed = np.array([np.mean(s[:,4]) for s in segments])
    river_floor = river_bed.copy()  # No duplicate stock: native channel cover is in coastal inventory.
    area = np.r_[area, river_area]
    floor_all = np.r_[floor.ravel(), river_floor]
    bed_all = np.r_[bed.ravel(), river_bed]
    left=[]; right=[]; conductance=[]
    for z in range(nz):
        for x in range(nx):
            if not valid[z,x]: continue
            for dz,dx in ((0,1),(1,0)):
                zz,xx=z+dz,x+dx
                if zz<nz and xx<nx and valid[zz,xx]:
                    left.append(z*nx+x); right.append(zz*nx+xx); conductance.append(config.coastal_conductance_m2_s)
    for i,p in enumerate(parent):
        if p>=0:
            left.append(n+int(p)); right.append(n+i); conductance.append(config.river_conductance_m2_s)
    outlet_faces=[]
    for i in leaves:
        row=segments[i][-1]
        x=int(round((row[2]-source['x_m'][0])/30)); z=int(round((row[3]-source['z_m'][0])/30))
        iz=(z-z0)//b; ix=(x-x0)//b
        if not (0<=iz<nz and 0<=ix<nx and valid[iz,ix]): raise ValueError('outlet outside valid coastal domain')
        outlet_faces.append(len(left)); left.append(n+int(i)); right.append(iz*nx+ix); conductance.append(config.river_conductance_m2_s)
    boundary = np.zeros((nz,nx), bool)
    boundary[0,:]=boundary[-1,:]=True; boundary[:,0]=boundary[:,-1]=True
    boundary = np.flatnonzero(((boundary | (bed < -3.)) & ocean).ravel())
    # The three saved sea anchors are open-water boundary cells as well.
    # They are classified ocean by the source and do not flood isolated land.
    anchors = np.array([right[j] for j in outlet_faces], dtype=int)
    if not ocean.ravel()[anchors].all(): raise ValueError('outlet anchor is not ocean-class')
    boundary = np.unique(np.r_[boundary, anchors])
    if not len(boundary): raise ValueError('no ocean-class open boundary')
    geometry=Geometry(area, floor_all, np.array(left,int),np.array(right,int),np.array(conductance),boundary,np.full(len(boundary),config.sea_conductance_m2_s))
    solid=(bed_all-floor_all)*area*.6
    # Initial sea prism and pre-event river stages; disconnected terrestrial cells start dry.
    water=np.zeros(len(area)); water[:n]=np.where(ocean.ravel(),np.maximum(-bed.ravel(),0)*area[:n],0)
    river_stage=np.array([np.mean(s[:,5]) for s in segments])
    water[n:]=np.maximum(river_stage-river_bed,0)*river_area
    state=State(0.,water,solid,np.zeros(len(area)))
    return dict(geometry=geometry,state=state,bounds=(z0,z1,x0,x1),shape=(nz,nx),ncoast=n,leaves=leaves,outlet_faces=np.array(outlet_faces),valid=valid,ocean=ocean,initial_bed=bed_all,initial_stock=solid.copy(),initial_water=float(water.sum()),initial_solid=float(solid.sum()),config=config)


def run(prepared, source, end_s, state=None, sample_s=3600):
    g=prepared['geometry']; config=prepared['config']; s=prepared['state'] if state is None else state
    times=source['forcing']['time_seconds']; water=source['forcing']['interval_water_q_m3_s']; solid=source['forcing']['interval_delivered_solid_m3_s']
    if end_s>times[-1] or end_s<s.time_s: raise ValueError('run must remain within the supplied event')
    records=[]; low=None; high=None; start=time.perf_counter(); next_sample=s.time_s
    initial_water=prepared['initial_water']; initial_solid=prepared['initial_solid']
    while s.time_s < end_s-1e-8:
        day=min(np.searchsorted(times,s.time_s,side='right')-1,len(water)-1)
        dt=min(config.dt_s,end_s-s.time_s,times[day+1]-s.time_s)
        sea=tide_stage(s.time_s+dt/2) if config.tide else 0.
        packet=step(g,s,dt,sea,prepared['ncoast'],water[day],solid[day])
        if s.time_s >= next_sample-1e-8:
            stage=bed_elevation(g,s)+s.water_m3/g.area_m2
            faces=prepared['outlet_faces']
            records.append(np.r_[s.time_s,sea,packet['internal_water_m3'][faces]/dt,packet['internal_solid_m3'][faces]/dt,stage[prepared['ncoast']:]])
            next_sample += sample_s
            if s.time_s >= end_s-86400:
                snap=(sea,s.time_s,s.water_m3.copy(),s.bed_solid_m3.copy())
                if low is None or sea<low[0]: low=snap
                if high is None or sea>high[0]: high=snap
    return dict(state=s,records=np.array(records),low=low,high=high,elapsed_s=time.perf_counter()-start,initial_water=initial_water,initial_solid=initial_solid)


def native_fields(source, prepared, water, stock):
    """Map coarse changes conservatively to native active inventory, not invented detail."""
    g=prepared['geometry']; n=prepared['ncoast']; nz,nx=prepared['shape']; b=prepared['config'].block
    z0,z1,x0,x1=prepared['bounds']; initial=source['initial_bed_m']
    result=initial.copy(); valid=source['valid']; stage=np.full(initial.shape,np.nan,np.float32)
    local=initial[z0:z1,x0:x1]; layer=local-source['active_layer']['floor_m'][z0:z1,x0:x1]
    difference=(stock[:n]-prepared['initial_stock'][:n]).reshape(nz,nx)
    # Erosion is apportioned by the native finite inventory; deposition by area.
    initial_stock=prepared['initial_stock'][:n].reshape(nz,nx)
    ratio=np.divide(np.minimum(difference,0),initial_stock,out=np.zeros_like(difference),where=initial_stock>0)
    delta=layer*np.repeat(np.repeat(ratio,b,axis=0),b,axis=1)
    delta+=np.repeat(np.repeat(np.maximum(difference,0)/((30*b)**2*.6),b,axis=0),b,axis=1)
    result[z0:z1,x0:x1]+=delta
    coarse_bed=bed_elevation(g,State(0,water,stock,np.zeros_like(stock)))[:n].reshape(nz,nx)
    coarse_depth=(water[:n]/g.area_m2[:n]).reshape(nz,nx)
    level=np.repeat(np.repeat(coarse_bed+coarse_depth,b,0),b,1)
    wet=np.repeat(np.repeat(coarse_depth>1e-5,b,0),b,1) & (level>result[z0:z1,x0:x1]) & valid[z0:z1,x0:x1]
    stage_local=stage[z0:z1,x0:x1]; stage_local[wet]=level[wet]
    # Channel node changes and stages are sampled only at saved centreline cells;
    # hydraulic storage itself uses the analytic width, not this display raster.
    rs=bed_elevation(g,State(0,water,stock,np.zeros_like(stock)))
    for i,section in enumerate(source['reach_segments']):
        col=np.rint((section[:,2]-source['x_m'][0])/30).astype(int); row=np.rint((section[:,3]-source['z_m'][0])/30).astype(int)
        result[row,col]=initial[row,col]+rs[n+i]-prepared['initial_bed'][n+i]
        surface=rs[n+i]+water[n+i]/g.area_m2[n+i]
        stage[row,col]=np.maximum(surface,result[row,col])
    return result,stage


def save_product(path, source, prepared, result):
    path=Path(path); path.mkdir(parents=True,exist_ok=False)
    s=result['state']; bed,stage=native_fields(source,prepared,s.water_m3,s.bed_solid_m3)
    extras={}
    for name in ('low','high'):
        snap=result[name]
        if snap is not None:
            _, surface=native_fields(source,prepared,snap[2],snap[3]); extras[name+'_stage_m']=surface; extras[name+'_time_s']=snap[1]
    wet=np.isfinite(stage) & (stage > bed)
    sea_connected=binary_propagation(wet & source['source_ocean'],mask=wet)
    water_class=np.where(sea_connected,1,np.where(wet,2,0)).astype('uint8')
    np.savez_compressed(path/'native.npz',bed_m=bed,water_stage_m=stage,water_depth_m=np.where(wet,np.maximum(stage-bed,0),0).astype('float32'),water_class=water_class,sea_connected=sea_connected,valid=source['valid'],original_ocean=source['source_ocean'],origin_xz_m=[source['x_m'][0],source['z_m'][0]],spacing_m=30.,**extras)
    np.savez_compressed(path/'series.npz',records=result['records'],outlet_branch=prepared['leaves'])
    np.savez_compressed(path/'stocks.npz',initial_solid_m3=prepared['initial_stock'],final_solid_m3=s.bed_solid_m3,mobile_solid_m3=s.mobile_solid_m3,area_m2=prepared['geometry'].area_m2,floor_m=prepared['geometry'].floor_m)
    save_checkpoint(path/'checkpoint.npz',s)
    ledger=dict(initial_water_m3=result['initial_water'],initial_solid_m3=result['initial_solid'],final_water_m3=float(s.water_m3.sum()),final_bed_solid_m3=float(s.bed_solid_m3.sum()),final_mobile_solid_m3=float(s.mobile_solid_m3.sum()),source_water_m3=s.source_water_m3,source_solid_m3=s.source_solid_m3,sea_water_in_m3=s.sea_water_in_m3,sea_water_out_m3=s.sea_water_out_m3,sea_solid_out_m3=s.sea_solid_out_m3)
    ledger['water_residual_m3']=ledger['initial_water_m3']+s.source_water_m3+s.sea_water_in_m3-s.sea_water_out_m3-ledger['final_water_m3']
    ledger['solid_residual_m3']=ledger['initial_solid_m3']+s.source_solid_m3-s.sea_solid_out_m3-ledger['final_bed_solid_m3']-ledger['final_mobile_solid_m3']
    manifest=dict(schema='tidal-storage-experiment-v1',source_identity=source['manifest']['source_identity'],source_manifest='../source-v1/source-manifest.json',config=asdict(prepared['config']),bounds_z0_z1_x0_x1=prepared['bounds'],coastal_shape=prepared['shape'],elapsed_s=result['elapsed_s'],time_s=s.time_s,ledger=ledger,records_columns=['time_s','sea_stage_m','outlet_q_0','outlet_q_1','outlet_q_2','outlet_solid_q_0','outlet_solid_q_1','outlet_solid_q_2','branch_stages_0_to_4'],limitations='300 m mean-bed coastal storage; analytic reach storage width times length; linear instantaneous head closure; no momentum or waves; clear-water sea; uncalibrated; native water is disaggregated stage, not 30 m hydraulic solution; unknown external rivers excluded; sea class is native wet connectivity seeded by original ocean, not independently solved')
    (path/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return manifest


def read_product(path):
    """Read existing product only; never invokes prepare or run."""
    path=Path(path)
    with np.load(path/'native.npz') as a, np.load(path/'series.npz') as b, np.load(path/'stocks.npz') as c:
        return dict(manifest=json.loads((path/'manifest.json').read_text(encoding='utf8')),native=dict(a),series=dict(b),stocks=dict(c),checkpoint=load_checkpoint(path/'checkpoint.npz'))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('source'); parser.add_argument('output'); parser.add_argument('--days',type=float,default=30); parser.add_argument('--dt',type=int,default=300); parser.add_argument('--calm',action='store_true'); args=parser.parse_args()
    source=load_source(args.source); prepared=prepare(source,Config(dt_s=args.dt,tide=not args.calm)); result=run(prepared,source,args.days*86400); print(json.dumps(save_product(args.output,source,prepared,result),indent=2))

if __name__=='__main__': main()


