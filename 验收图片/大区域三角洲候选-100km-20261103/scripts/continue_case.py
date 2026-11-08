"""Continue regional case from initial, preserving short diagnostic checkpoints."""
import json
import time
from pathlib import Path
import numpy as np
from terrain_pipeline.coastal_delta_evolution import load, save, advance_years, advance_event, TidalConfig
from terrain_pipeline.coastal_delta_routes import valley_path, connected_ocean
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_marine_longterm import LongtermConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig

P=Path('.scratch/delta-large-acceptance-20261103')
def main():
    start=time.perf_counter()
    state, progress=load(P/'initial')
    cfg=HydraulicConfig(progress['integrated']['route_metadata']['extension_port_stage_m'])
    with np.load(P/'case-source/source.npz') as src:
        ocean=connected_ocean(state.bed_m,state.valid_mask,state.ocean_seed_mask) & src['source_ocean']
    h=solve(state,progress,0.,cfg)
    stages={tuple(map(int,n[:2])):float(n[2]) for n in h['nodes']}
    trunk=[tuple(c) for c in progress['routes'][0]]
    blocked=np.zeros(state.bed_m.shape,bool)
    for cell in trunk: blocked[cell]=True
    rows,cols=np.indices(state.bed_m.shape)
    mouths=[trunk[-1]]; candidates=[]
    for index in sorted(set(max(1,min(len(trunk)-2,int(len(trunk)*f))) for f in (.2,.4,.6,.8))):
        fork=trunk[index]; target=ocean.copy()
        for mouth in mouths:
            target &= (rows-mouth[0])**2+(cols-mouth[1])**2 >= (2000/state.spacing_m)**2
        target &= ~blocked
        try:
            path=valley_path(state.bed_m,state.valid_mask,fork,target,stages[fork],state.spacing_m,blocked)
        except ValueError:
            continue
        candidates.append(path.tolist()); mouths.append(tuple(path[-1]))
        for cell in path[1:]: blocked[tuple(cell)]=True
    progress['integrated']['candidate_routes']=candidates
    save(P/'final-initial',state,progress)
    (P/'candidate-survey.json').write_text(json.dumps({'method':'D4 minimax bed below actual fork stage; candidate corridors mutually forbidden; ocean targets at least 2 km apart','candidates':candidates,'fork_stages_m':[stages[tuple(c[0])] for c in candidates]},indent=2),encoding='utf-8')
    print('candidates',[(len(c),c[0],c[-1]) for c in candidates],flush=True)
    for i in range(4):
        # Annual stage uses river/floodplain transport only. The full-grid
        # implicit marine solver did not complete its first half-year step in
        # several minutes; physical tide and waves are applied in the event.
        state,progress=advance_years(state,progress,.5,input_id=f'regional-final-{i}',hydraulic_config=cfg,river_deposition_fraction=.0001,step_years=.5)
        save(P/f'final-step{i+1}',state,progress)
        h=solve(state,progress,0.,cfg)
        print('step',i+1,'seconds',time.perf_counter()-start,'q',h['route_q_m3_s'],'routes',len(progress['routes']),flush=True)
    save(P/'final-formed',state,progress)
    forcing=MarineConfig(step_s=3600.,tide_amplitude_m=.3,wave_height_m=.5,transport_rate_s=1e-6,entrainment_rate_s=1e-7,settling_rate_s=1e-6)
    state,report=advance_event(state,progress,25*3600.,forcing,input_id='regional-final-event',hydraulic_config=cfg,inlet_solid_rate_m3_s=.08)
    save(P/'final-event',state,report['updated_progress'])
    (P/'final-event-report.json').write_text(json.dumps({k:v for k,v in report.items() if k!='updated_progress'},indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else x),encoding='utf-8')
    print('event complete seconds',time.perf_counter()-start,flush=True)
if __name__=='__main__': main()
