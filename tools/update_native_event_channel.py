from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_native_event import classify
root=Path('.scratch/river-upgrade-20261101')
e=root/'native-event-v1'; d=root/'native-final-routing-v1/derived'; r=root/'native-final-routing-v1/routing'; t=root/'terrain-v3'
load=lambda p:np.load(p,mmap_mode='r')
channel=np.load(e/'channel_mask.npy',mmap_mode='r+'); capture=np.load(e/'capture_index.npy',mmap_mode='r+')
classify(load(r/'order.npy'),load(r/'receiver.npy'),load(d/'pool_index.npy'),load(d/'pool_anchor.npy'),load(e/'node_water_m3.npy')[1],load(t/'ocean_mask.npy').ravel(),load(t/'unknown_mask.npy').ravel(),load(t/'valid_mask.npy').ravel(),channel,capture,.015*1296000)
channel.flush();capture.flush()
a=channel.reshape(4096,4096)
x0=int(np.ceil((-26170+61440)/30));x1=int(np.floor((23830+61440)/30))+1
z0=int(np.ceil((-19990+61440)/30));z1=int(np.floor((30010+61440)/30))+1
print('window indices',z0,z1,x0,x1,'channels',int(a[z0:z1,x0:x1].sum()),'whole',int(channel.sum()))
