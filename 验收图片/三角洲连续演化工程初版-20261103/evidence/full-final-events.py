from pathlib import Path
from terrain_pipeline.coastal_delta_product import load_checkpoint,save_checkpoint
from terrain_pipeline.coastal_delta_avulsion import activate_candidate
from terrain_pipeline.coastal_delta_evolution import advance_event
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig
root=Path('.scratch/coast-marine-reorganization-20261102')
for name in ('formed','event1','event2'):
    state,progress=load_checkpoint(root/f'full-final-{name}')
    save_checkpoint(root/f'full-final-diagnostic-{name}',state,progress)
s,p=load_checkpoint(root/'full-final-diagnostic-formed')
cfg=HydraulicConfig(2.320855878)
s,p,info=activate_candidate(s,p,hydraulic_config=cfg,sea_level_m=0.)
print('avulsion',info['trigger'],info.get('actual_Q_m3_s'),info.get('solid_cut_m3'),flush=True)
if not info['activated']:
    raise RuntimeError('no physical candidate activated')
save_checkpoint(root/'full-final-formed',s,p)
s,p=load_checkpoint(root/'full-final-formed')
for i in (1,2):
    forcing=MarineConfig(step_s=3600.,tide_amplitude_m=.3,wave_height_m=.5,transport_rate_s=1e-6,entrainment_rate_s=1e-7,settling_rate_s=1e-6)
    s,report=advance_event(s,p,25*3600,forcing,input_id=f'final-event{i}',hydraulic_config=cfg,inlet_solid_rate_m3_s=.08)
    p=report['updated_progress']
    save_checkpoint(root/f'full-final-event{i}',s,p)
    print('event',i,report['delivered_water_m3'],report['delivered_solid_m3'],flush=True)
