import json
from pathlib import Path
import numpy as np
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval
root = Path('.scratch/river-upgrade-20261101')
event = root / 'native-event-v1'
d = root / 'native-final-routing-v1/derived'
r = root / 'native-final-routing-v1/routing'
load = lambda p: np.load(p, mmap_mode='r', allow_pickle=False)
local = load(event/'local_contribution_m3.npy')
state = np.array(load(event/'pool_storage_m3.npy')[1])
flow, retained = route_pool_interval(local, load(r/'order.npy'), load(r/'receiver.npy'), load(d/'pool_index.npy'), load(d/'pool_anchor.npy'), load(d/'pool_capacity_m3.npy'), state)
saved = load(event/'node_water_m3.npy')[1]
max_diff = 0.
for a in range(0, len(flow), 262144): max_diff = max(max_diff, float(np.max(np.abs(flow[a:a+262144]-saved[a:a+262144]))))
store_diff = float(np.max(np.abs(state-load(event/'pool_storage_m3.npy')[2])))
if max_diff != 0 or store_diff != 0: raise ValueError('persisted restart mismatch')
q = load(event/'mouth_water_m3.npy')[1] / 1296000
ids = load(d/'mouth_id.npy'); nodes = load(d/'mouth_source.npy'); targets = load(d/'mouth_ocean_receiver.npy'); coords = load(event/'mouth_world_xz_m.npy'); targetcoords = load(event/'mouth_ocean_world_xz_m.npy'); unknown = load(event/'mouth_unknown.npy')
selected = np.argsort(q)[-12:][::-1]
table = [dict(id=int(ids[i]), source_node=int(nodes[i]), ocean_node=int(targets[i]), source_xz_m=coords[i].tolist(), ocean_xz_m=targetcoords[i].tolist(), q_m3_s=float(q[i]), unknown=bool(unknown[i])) for i in selected]
result = dict(resume_max_node_difference_m3=max_diff, resume_max_storage_difference_m3=store_diff, prominent_mouths=table)
(event/'verification.json').write_text(json.dumps(result, indent=2), encoding='utf8')
print(json.dumps(result, indent=2))
