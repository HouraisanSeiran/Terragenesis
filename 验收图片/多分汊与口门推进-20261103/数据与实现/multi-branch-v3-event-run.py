from pathlib import Path
import json
import os
import numpy as np
from terrain_pipeline.coastal_delta_product import load_checkpoint,save_checkpoint
from terrain_pipeline.coastal_delta_branching import advance_river_event, mouth_exterior_faces
from terrain_pipeline.coastal_marine_sediment import MarineConfig,classify_ocean
p=Path('.scratch/coast-marine-reorganization-20261102'); layer=float(os.environ.get('V3_LAYER', '0.5')); suffix='' if layer==0.5 else '-layer-'+str(layer);s,progress=load_checkpoint(p/'multi-branch-v3-stage')
cfg=MarineConfig(tide_amplitude_m=1,wave_height_m=1.5,wave_direction_xz=(-1,0),transport_rate_s=2e-5,entrainment_rate_s=1e-6,settling_rate_s=1e-5,export_rate_s=1e-6,step_s=1800,transverse_diffusivity_m2_s=30)
t=lambda x: sum(float(getattr(x,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+x.exported_solid_m3+x.unresolved_solid_m3
out,report=advance_river_event(s,progress,90000,cfg,input_id='multi-branch-v3-event-inlet',inlet_solid_rate_m3_s=1.6,capacity_concentration=.01,active_layer_m=layer,max_velocity_m_s=2.)
save_checkpoint(p/('multi-branch-v3-event'+suffix),out,progress)
r,rp=load_checkpoint(p/('multi-branch-v3-event'+suffix));wet,_=classify_ocean(r,0)
report.update({'wet_paths':[all(wet[tuple(c)] for c in route) for route in rp['routes']], 'max_bed_change_m':float(np.max(np.abs(r.bed_m-s.bed_m))), 'mass_residual_m3':t(r)-t(s)-report['solid_m3'],'clock_start_s':s.time_s,'clock_end_s':r.time_s,'water_delta_m3':r.water_input_m3-s.water_input_m3,'record_count':sum(a['input_id']=='multi-branch-v3-event-inlet' for a in r.consumed_packets),'event_reload_matches':rp==progress and np.array_equal(r.bed_solid_m3,out.bed_solid_m3),'mobile_before_m3':float(s.mobile_solid_m3.sum()),'mobile_after_m3':float(r.mobile_solid_m3.sum()),'outlets':[a[-1] for a in rp['routes']], 'exterior_faces':mouth_exterior_faces(r,rp)})
(p/('multi-branch-v3-event'+suffix+'-stats.json')).write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report),flush=True)


