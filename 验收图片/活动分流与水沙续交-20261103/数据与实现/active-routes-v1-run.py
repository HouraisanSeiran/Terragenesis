from pathlib import Path
import json
import numpy as np
from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint
from terrain_pipeline.coastal_delta_branching import advance_river_event, mouth_exterior_faces
from terrain_pipeline.coastal_marine_sediment import MarineConfig
p=Path('.scratch/coast-marine-reorganization-20261102')
s,progress=load_checkpoint(p/'multi-branch-v3-repaired-long')
cfg=MarineConfig(tide_amplitude_m=1,wave_height_m=1.5,wave_direction_xz=(-1,0),transport_rate_s=2e-5,entrainment_rate_s=1e-6,settling_rate_s=1e-5,export_rate_s=1e-6,step_s=1800,transverse_diffusivity_m2_s=30)
t=lambda x: sum(float(getattr(x,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+x.exported_solid_m3+x.unresolved_solid_m3
out, report=advance_river_event(s,progress,90000,cfg,input_id='active-routes-v1-inlet',inlet_solid_rate_m3_s=1.6,capacity_concentration=.01,active_layer_m=.5)
progress=report.pop('updated_progress')
save_checkpoint(p/'active-routes-v1-event',out,progress)
r,rp=load_checkpoint(p/'active-routes-v1-event')
report.update(active=rp['active'],actual_shares=rp['actual_shares'],actual_q_m3_s=[rp['discharge_m3_s']*v for v in rp['actual_shares']],exterior_faces=mouth_exterior_faces(r,rp),activity_history=[x for x in rp['history'] if x.get('input_id')=='active-routes-v1-inlet'],solid_residual_m3=t(r)-t(s)-report['delivered_solid_m3'],water_delta_m3=r.water_input_m3-s.water_input_m3,reload_matches=rp==progress and np.array_equal(r.bed_solid_m3,out.bed_solid_m3),record_count=sum(a['input_id']=='active-routes-v1-inlet' for a in r.consumed_packets))
(p/'active-routes-v1-stats.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report),flush=True)
