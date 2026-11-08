from pathlib import Path
import json
from terrain_pipeline.coastal_delta_product import load_checkpoint,save_checkpoint
from terrain_pipeline.coastal_delta_plain import advance_years
from terrain_pipeline.coastal_marine_longterm import LongtermConfig
p=Path('.scratch/coast-marine-reorganization-20261102')
s,pr=load_checkpoint(p/'multi-branch-v3-repaired-event'); cfg=LongtermConfig(**pr['forcing'])
for i in range(9):
 s,pr=advance_years(s,pr,1.,cfg,step_years=1.)
 print(json.dumps({'year':pr['years'],'active':pr['active']}),flush=True)
 if i in (0,3,8): save_checkpoint(p/('tidal-plain-v1-year'+str(i+2)),s,pr)
