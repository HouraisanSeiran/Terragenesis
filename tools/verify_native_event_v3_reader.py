import json
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_native_event import read_product
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval
root=Path('.scratch/river-upgrade-20261101'); e=root/'native-event-v3'; d=root/'native-final-routing-v1/derived'; routing=root/'native-final-routing-v1/routing'
load=lambda p:np.load(p,mmap_mode='r',allow_pickle=False)
product=read_product(e,lowland=root/'native-lowland-v1',network=root/'native-network-v4')
nodes=product.arrays['mouth_source']; volumes=product.arrays['mouth_water_m3'][1]; index=int(np.argmax(volumes)); node=int(nodes[index]); z,x=divmod(node,4096); mq=product.query(z,x,1)
assert mq['known_local_volume_m3']==float(volumes[index])
storage=product.arrays['pool_storage_m3'][2]; pool=int(np.argmax(storage)); labels=product.labels; anchor=int(load(d/'pool_anchor.npy')[pool]); z,x=divmod(anchor,4096); lq=product.query(z,x,1)
assert lq['pool']['storage_m3']==float(storage[pool]) and lq['pool']['level_m']==float(product.arrays['pool_level_m'][2,pool])
state=np.array(product.arrays['pool_storage_m3'][1]);flow,retained=route_pool_interval(product.arrays['local_contribution_m3'],load(routing/'order.npy'),load(routing/'receiver.npy'),labels,load(d/'pool_anchor.npy'),product.arrays['pool_capacity_m3'],state)
saved=product.arrays['node_water_m3'][1]; maximum=0.
for a in range(0,len(flow),262144):maximum=max(maximum,float(np.max(np.abs(flow[a:a+262144]-saved[a:a+262144]))))
store_diff=float(np.max(np.abs(state-storage)))
if maximum!=0 or store_diff!=0:raise ValueError('restart mismatch')
result=dict(resume_max_node_difference_m3=maximum,resume_max_storage_difference_m3=store_diff,mouth=dict(index=index,node=node,id=int(product.arrays['mouth_id'][index]),query=mq),lake=dict(pool_index=pool,anchor=anchor,query=lq),reader_metadata=product.metadata)
(e/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2),flush=True)
