from pathlib import Path
import json
import numpy as np
from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint
from terrain_pipeline.coastal_delta_branching import flush_pending,advance_river_event
from terrain_pipeline.coastal_marine_sediment import MarineConfig
p=Path('.scratch/coast-marine-reorganization-20261102')
s,pr=load_checkpoint(p/'active-routes-v1-event')
inlet=tuple(pr['routes'][0][0]); before=float(s.mobile_solid_m3[inlet]); w=s.water_input_m3
out,updated,report=flush_pending(s,pr,input_id='active-routes-v1-inlet')
save_checkpoint(p/'active-routes-v1-flush',out,updated)
r,rp=load_checkpoint(p/'active-routes-v1-flush')
rec=next(x for x in r.consumed_packets if x['input_id']=='active-routes-v1-inlet')
try: flush_pending(r,rp,input_id='active-routes-v1-inlet'); duplicate=False
except ValueError: duplicate=True
try: advance_river_event(r,rp,1.,MarineConfig(),input_id='active-routes-v1-inlet'); replay=False
except ValueError: replay=True
report.update(inlet_mobile_delta_m3=float(r.mobile_solid_m3[inlet]-before),water_delta_m3=r.water_input_m3-w,delivered_solid_m3=rec['delivered_solid_m3'],delivered_water_m3=rec['delivered_water_m3'],record_count=sum(x['input_id']=='active-routes-v1-inlet' for x in r.consumed_packets),active=rp['active'],no_duplicate_flush=duplicate,no_replay=replay,reload_matches=rp==updated and np.array_equal(r.mobile_solid_m3,out.mobile_solid_m3),formation_consistent=next(x for x in r.consumed_packets if x['input_id']==rp['input_id'])['formation_progress']==rp)
(p/'active-routes-v1-flush-stats.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report),flush=True)
