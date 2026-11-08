"""Acceptance replay with the unchanged published marine event forcing."""
from pathlib import Path
import json
import hashlib
from terrain_pipeline.coastal_delta_product import load_checkpoint,save_checkpoint
from terrain_pipeline.coastal_delta_branching import advance_river_event
from terrain_pipeline.coastal_marine_sediment import MarineConfig

p=Path(__file__).parent
s,pr=load_checkpoint(p/'tidal-plain-v1-year10')
cfg=MarineConfig(tide_amplitude_m=1,wave_height_m=1.5,wave_direction_xz=(-1,0),
                 transport_rate_s=2e-5,entrainment_rate_s=1e-6,settling_rate_s=1e-5,
                 export_rate_s=1e-6,step_s=1800,transverse_diffusivity_m2_s=30,
                 active_sediment_layer_m=.1)
out,report=advance_river_event(s,pr,90000,cfg,input_id='tidal-plain-main-event',
    inlet_solid_rate_m3_s=1.6,capacity_concentration=.01,active_layer_m=.5,max_velocity_m_s=2.)
save_checkpoint(p/'tidal-plain-main-event',out,report['updated_progress'])
report['formed_checkpoint_sha256']=hashlib.sha256((p/'tidal-plain-v1-year10.npz').read_bytes()).hexdigest()
(p/'main-tidal-event-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('same forcing event saved')
