"""Build the bounded saved-river sediment and mouth coupling case."""
from __future__ import annotations
import argparse, json, math, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import (
    route_daily_sediment, save_daily_sediment, load_daily_sediment,
)
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import (
    FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval,
    simulate_fluvial_delta,
)

CENTER = ROOT / ".scratch/hydrological-planning-domain/saved-bed-mouth-20261016-01/centerline.npz"
SUPPLY = ROOT / ".scratch/hydrological-planning-domain/saved-river-seasonal-supply-20261016-01/supply.npz"
DETAIL = ROOT / "verification/hydrological-planning-domain/full-edges-v5-20261014-03/edge-8470-8600-v7-shared-sections-owned-halo2/detail.npz"

def _depth(q, width, slope, rough=.035):
    if q <= 0: return 0.0
    lo, hi = 1e-9, 200.0
    for _ in range(70):
        h=(lo+hi)/2; a=width*h; rh=a/(width+2*h)
        pred=a*rh**(2/3)*math.sqrt(max(slope,1e-12))/rough
        if pred < q: lo=h
        else: hi=h
    return (lo+hi)/2

def _hardness(x,z):
    return float(np.clip(.5+.5*(.6*np.sin(x/6000)*np.cos(z/6000)+.3*np.sin(x/1800)*np.cos(z/1800)+.1*np.sin(x/600)*np.cos(z/600)),0,1))

def build(output):
    c=np.load(CENTER,allow_pickle=False); s=np.load(SUPPLY,allow_pickle=False); d=np.load(DETAIL,allow_pickle=False)
    meta=json.loads(c['metadata_json'].item()); end=int(meta['first_land_to_connected_ocean_bracket']['after']['index'])
    xz=np.asarray(c['node_xz_m'][:end+1],float); bed=np.asarray(c['bed_m'][:end+1],float)
    seg=np.hypot(np.diff(xz[:,0]),np.diff(xz[:,1])); dist=np.r_[0,np.cumsum(seg)]; total=float(dist[-1])
    ix=np.searchsorted(dist,np.linspace(0,total,85)); ix[-1]=end; xz=xz[ix]; bed=bed[ix]
    seg=np.hypot(np.diff(xz[:,0]),np.diff(xz[:,1])); n=85
    length=np.empty(n); length[0]=seg[0]/2; length[-1]=seg[-1]/2; length[1:-1]=(seg[:-1]+seg[1:])/2
    receiver=np.r_[np.arange(1,n),-1].astype(np.int64)
    slope=np.r_[((bed[:-1]-bed[1:])/seg),0.0]; slope[-1]=slope[-2]
    q=np.asarray(s['selected_q_m3_s'],float); starts=np.asarray(s['step_start_s'],float); ends=np.asarray(s['step_end_s'],float); times=np.r_[starts,ends[-1]]; dt=np.diff(times)
    qmat=np.repeat(q[:,None],n,axis=1); smat=np.repeat(slope[None,:],len(q),axis=0); width=np.full(n,8.0); hardness=np.array([_hardness(*p) for p in xz]); depth=np.array([[_depth(v,8,float(sl)) for sl in slope] for v in q])
    floor=bed-1.05; alluv=width*length*.05
    bundle=route_daily_sediment(receiver=receiver,length_m=length,width_m=width,bed_elevation_m=bed,water_depth_m=depth,water_q_m3_s=qmat,friction_slope=smat,time_seconds=times,rock_floor_m=floor,initial_alluvium_bulk_m3=alluv,hardness=hardness,material=MaterialParameters(),external_solid_m3_s=np.zeros_like(qmat),geometry_identity_sha256=file_sha256(CENTER),hydraulic_identity_sha256=file_sha256(SUPPLY),material_provenance='MaterialParameters defaults')
    output.mkdir(parents=True,exist_ok=False); save_daily_sediment(output/'upstream_bundle.npz',bundle); load_daily_sediment(output/'upstream_bundle.npz',expected_sha256=file_sha256(output/'upstream_bundle.npz'))
    terminal=bundle['arrays']['exported_solid_m3'][:,-1]; ms=np.asarray(s['monthly_start_s'],float); me=np.asarray(s['monthly_end_s'],float); monthly=[]
    for a,b in zip(ms,me):
        mask=(starts>=a-1e-6)&(ends<=b+1e-6); monthly.append(float(terminal[mask].sum()))
    assert np.isclose(sum(monthly),float(terminal.sum()),rtol=1e-9,atol=1e-8)
    dm=json.loads(d['metadata_json'].item()); spacing=float(dm['spacing_m']); ox,oz=dm['origin_xz_m']; r,c0=198,198; crop=np.asarray(d['derived_height_m'][r-32:r+32,c0-32:c0+32],float); ocean=np.asarray(d['ocean_mask'][r-32:r+32,c0-32:c0+32],bool); valid=np.ones_like(crop,bool)
    terrain=TerrainGrid(crop,valid,float(ox+(c0-32)*spacing),float(oz+(r-32)*spacing),spacing,spacing,'diagnostic_dem_proxy','saved-mouth-detail',file_sha256(DETAIL),source_path=str(DETAIL))
    export=np.zeros_like(ocean); export[0]=ocean[0]; export[-1]=ocean[-1]; export[:,0]|=ocean[:,0]; export[:,-1]|=ocean[:,-1]; boundary=FluvialDeltaBoundary(ocean,export,0.,max(1.,float(crop[32,32]+1)),'saved-mouth-detail')
    forcing=[FluvialDeltaInterval((32,32),float((q*dt)[(starts>=a-1e-6)&(ends<=b+1e-6)].sum()),float(v)) for (a,b),v in zip(zip(ms,me),monthly)]
    result=simulate_fluvial_delta(terrain,boundary,forcing,FluvialDeltaConfig(capacity_solid_per_water=.0001)); zero=simulate_fluvial_delta(terrain,boundary,[FluvialDeltaInterval((32,32),0.,0.) for _ in forcing],FluvialDeltaConfig(capacity_solid_per_water=.0001)); assert np.array_equal(zero['final_bed_m'],zero['initial_bed_m'])
    np.savez(output/'geometry.npz',node_xz_m=xz,bed_m=bed,length_m=length,receiver=receiver,width_m=width,slope=slope,hardness=hardness,depth_m=depth)
    np.savez(output/'upstream.npz',time_seconds=times,q_m3_s=q,terminal_export_m3=terminal,monthly_export_m3=np.asarray(monthly))
    np.savez(output/'mouth.npz',initial_bed_m=result['initial_bed_m'],final_bed_m=result['final_bed_m'],height_delta_m=result['height_delta_m'],deposited_solid_m3=result['deposited_solid_m3'])
    report={'schema':'upstream-sediment-prep-v1','path_m':total,'length_sum_m':float(length.sum()),'nodes':n,'days':len(q),'monthly_export_m3':monthly,'interface_bed_difference_m':float(abs(bed[-1]-crop[32,32])),'terminal_export_m3':float(terminal.sum()),'mouth_solid_input_m3':float(sum(monthly)),'mouth_budget':result['solid_ledger'],'source_hashes':{'center':file_sha256(CENTER),'supply':file_sha256(SUPPLY),'detail':file_sha256(DETAIL)},'frozen_water':True,'hydraulic_ready':False,'mainstem_only':True}
    (output/'summary.json').write_text(json.dumps(report,indent=2,default=float),encoding='utf-8'); return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,default=ROOT/'verification/upstream-sediment/same-source-20261016-01'); args=ap.parse_args(); print(json.dumps(build(args.output),indent=2,default=float))
