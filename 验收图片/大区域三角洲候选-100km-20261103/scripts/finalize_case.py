"""Save explicitly constructed post-formation forks and run physical event."""
import json
from pathlib import Path
from terrain_pipeline.coastal_delta_evolution import load, save, advance_event
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig
P=Path('.scratch/delta-large-acceptance-20261103')
annual,progress=load(P/'final-formed'); save(P/'final-annual',annual,progress)
state,progress=load(P/'activation-probe'); save(P/'final-formed',state,progress)
cfg=HydraulicConfig(progress['integrated']['route_metadata']['extension_port_stage_m'])
forcing=MarineConfig(step_s=3600.,tide_amplitude_m=.3,wave_height_m=.5,transport_rate_s=1e-6,entrainment_rate_s=1e-7,settling_rate_s=1e-6)
state,report=advance_event(state,progress,25*3600.,forcing,input_id='constructed-forks-event',hydraulic_config=cfg,inlet_solid_rate_m3_s=.08)
save(P/'final-event',state,report['updated_progress'])
(P/'final-event-report.json').write_text(json.dumps({k:v for k,v in report.items() if k!='updated_progress'},indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else x),encoding='utf-8')
print('done',flush=True)
