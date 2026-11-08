import json, time
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_game_hydrology import read_product, lifecycle_inputs
from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
root=Path('.scratch/river-upgrade-20261101')
out=root/'hydro-lifecycle-v1'
p=read_product(root/'game-hydro-v1')
product, local, state=lifecycle_inputs(p,root/'game-grade-90m',root/'terrain-v3')
rows=[]
for n in (1,2,4):
    t=time.monotonic()
    r=PartitionRouter(out/f'partition-{n}.sqlite',product,local,1296000,interval=0,source=p.identity,partitions=n,state=state,trace=True,reverse_preparation=n==4)
    r.run()
    result=r.result()
    mouth={x['index']:x['known_local_volume_m3'] for x in result['outlets'] if x['kind']=='marine'}
    indices=p.arrays['derived/mouth_source']
    expected=p.arrays['mouth_water_m3'][0]
    missing=sum(int(i) not in mouth for i in indices)
    error=max((abs(mouth[int(i)]-float(expected[j])) for j,i in enumerate(indices) if int(i) in mouth),default=0.)
    storage=np.array(result['state']['storage_m3'])
    row=dict(partitions=n,seconds=time.monotonic()-t,packets=r.db.execute('SELECT COUNT(*) FROM packets').fetchone()[0],mouth_missing=missing,mouth_max_error_m3=error,pool_max_error_m3=float(np.max(np.abs(storage-p.arrays['pool_storage_m3'][1]))),budget=result['budget'])
    if missing or error != 0 or row['pool_max_error_m3'] != 0:
        raise ValueError('saved reference mismatch')
    rows.append(row)
    r.close()
    (out/'completion-progress.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    print(json.dumps(row),flush=True)
