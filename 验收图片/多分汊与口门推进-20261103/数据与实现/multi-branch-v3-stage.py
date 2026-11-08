from pathlib import Path
import json
import numpy as np
from terrain_pipeline.coastal_delta_product import load_checkpoint,save_checkpoint
from terrain_pipeline.coastal_delta_branching import update_shoreline_mouths,mouth_exterior_faces
p=Path('.scratch/coast-marine-reorganization-20261102'); state,progress=load_checkpoint(p/'multi-branch-v2-stage')
print('before',json.dumps(mouth_exterior_faces(state,progress)),flush=True)
state,progress,changes=update_shoreline_mouths(state,progress)
print('changes',json.dumps(changes),'after',json.dumps(mouth_exterior_faces(state,progress)),flush=True)
save_checkpoint(p/'multi-branch-v3-stage',state,progress)
