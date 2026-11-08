from pathlib import Path
import json
import numpy as np
from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint
from terrain_pipeline.coastal_delta_branching import advance_river_event
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig
p=Path('.scratch/coast-marine-reorganization-20261102')
s,pr=load_checkpoint(p/'tidal-plain-v1-year10')
config=MarineConfig(tide_amplitude_m=1.,wave_height_m=1.5,wave_direction_xz=(-1,0),transport_rate_s=2e-5,entrainment_rate_s=1e-6,settling_rate_s=1e-5,export_rate_s=1e-6,step_s=1800.,transverse_diffusivity_m2_s=30.,active_sediment_layer_m=.1)
out,report=advance_river_event(s,pr,90000.,config,input_id='river-stage-v1-event',inlet_solid_rate_m3_s=1.6,capacity_concentration=.01,active_layer_m=.5,max_velocity_m_s=2.,hydraulic_config=HydraulicConfig(upstream_stage_limit_m=3.))
save_checkpoint(p/'river-stage-v1-event',out,report['updated_progress'])
(p/'river-stage-v1-event-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
total=lambda x:sum(float(getattr(x,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+x.exported_solid_m3+x.unresolved_solid_m3
r=report['updated_progress']['river_hydraulics']
summary={k:v for k,v in report.items() if k!='updated_progress'}
summary.update(physical_time_start_s=s.time_s,physical_time_end_s=out.time_s,years=pr['years'],residual_solid_m3=total(out)-total(s)+report['undelivered_solid_m3']-report['solid_m3'],actual_q_m3_s=r['route_q_m3_s'],sea_level_m=r['sea_level_m'],active=r['active'],exterior_faces=r['exterior_faces'],parameters=r['parameters'],stock_bed_m3=float(out.bed_solid_m3.sum()),stock_mobile_m3=float(out.mobile_solid_m3.sum()),stock_stranded_m3=float(out.stranded_solid_m3.sum()),exported_solid_m3=out.exported_solid_m3,finite=all(np.isfinite(getattr(out,k)).all() for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3')))
(p/'river-stage-v1-stats.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print(json.dumps(summary),flush=True)
