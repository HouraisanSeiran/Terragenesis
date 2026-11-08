"""Independent nested-branch regression, using the documented small fixture."""
from pathlib import Path
from dataclasses import replace
import json
import runpy
from terrain_pipeline.coastal_delta_hydraulics import solve, HydraulicConfig

root = Path(__file__).resolve().parents[2]
state, progress = runpy.run_path(str(root/'tests/test_coastal_delta_hydraulics.py'))['fixture']()
bed = state.base_bed_m.copy()
bed[5,9] = 10.
result = solve(replace(state,base_bed_m=bed),progress,0.,HydraulicConfig(4.))
expected = [19.8,10.2,0.]
report = {'actual_q_m3_s':result['route_q_m3_s'],'expected_q_m3_s':expected,
          'pass':all(abs(a-b)<1e-6 for a,b in zip(result['route_q_m3_s'],expected))}
(Path(__file__).parent/'main-stage-nested-probe.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(report)
