import numpy as np
from terrain_pipeline.new_world_native_network_v4 import corridor, reconcile


def test_shared_junction_and_corrected_lake_stage():
    raw=np.array([12.,11.,10.,9.]);q=np.ones(4);kind=np.array([0,0,1,2]);pools=np.array([-1,-1,0,-1]);levels=np.array([10.5]);targets=np.array([2,2,3,-1]);rank=np.array([3,2,1,0])
    stage,bed,width,bad=reconcile(raw,q,kind,pools,levels,targets,rank,np.array([2]),np.array([10.5]))
    assert stage[2]==10.5 and stage[0]>=stage[2] and stage[1]>=stage[2]
    assert stage[3]==0 and np.all(raw-bed<=4) and not bad[:3].any()


def test_corridor_crosses_bounded_dry_saddle():
    bed=np.array([[0.,2.,0.]])
    labels=np.array([0,0,0]);path=corridor(0,2,0,1.,labels,bed,max_cut=2.)
    assert path==[0,1,2]
    assert corridor(0,2,0,1.,labels,bed,max_cut=.5) is None
