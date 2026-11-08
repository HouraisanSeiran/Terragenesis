import json
from pathlib import Path
import numpy as np
from terrain_pipeline.coastal_marine_sediment import load_state
from terrain_pipeline.coastal_marine_product import file_hash
from terrain_pipeline.coastal_delta_routes import load_routes
from terrain_pipeline.coastal_delta_evolution import initialize, advance_years
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_delta_product import save_checkpoint
p=Path('.scratch/coast-marine-reorganization-20261102'); w=p/'window100-v2'
m=json.loads((w/'manifest.json').read_text(encoding='utf-8-sig'))
assert m['source_identity']=='778970b3c367bc5896e86e69b6eb17b30998482da96cd05d9d5ed7be796beb19'
assert file_hash(w/'source.npz')==m['source_sha256'] and file_hash(w/'state.npz')==m['state_sha256']
s=load_state(w/'state.npz'); assert s.source_identity==m['source_identity']
r,meta=load_routes(p/'full-routes-initial'); assert meta['source_identity']==s.source_identity
from terrain_pipeline.coastal_delta_evolution import advance_event, TidalConfig
from terrain_pipeline.coastal_delta_product import load_checkpoint
from terrain_pipeline.coastal_marine_longterm import LongtermConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig
cfg=HydraulicConfig(meta['extension_port_stage_m'])
s0,p0=load_checkpoint(p/'full-final-short-initial')
save_checkpoint(p/'full-final-initial',s0,p0)
s,progress=load_checkpoint(p/'full-final-short-formed')
s,progress=advance_years(s,progress,4.5,input_id='formation-continuation',hydraulic_config=cfg,marine_config=LongtermConfig(settling_velocity_m_s=1e-5),river_deposition_fraction=.0001,tidal_config=TidalConfig(amplitude_m=.3,phase_count=4),step_years=.25)
save_checkpoint(p/'full-final-formed',s,progress)
s,progress=load_checkpoint(p/'full-final-formed')
print('formed',progress['years'],len(progress['routes']),flush=True)
for i in (1,2):
    forcing=MarineConfig(step_s=3600.,tide_amplitude_m=.3,wave_height_m=.5,transport_rate_s=1e-6,entrainment_rate_s=1e-7,settling_rate_s=1e-6)
    s,report=advance_event(s,progress,25*3600,forcing,input_id=f'final-event{i}',hydraulic_config=cfg,inlet_solid_rate_m3_s=.08)
    progress=report['updated_progress']
    save_checkpoint(p/f'full-final-event{i}',s,progress)
    print('event',i,report['delivered_water_m3'],report['delivered_solid_m3'],flush=True)
