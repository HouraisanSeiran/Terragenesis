import numpy as np
from terrain_pipeline.new_world_native_network import solve_nodes


def test_shared_junction_downstream_stage_and_bounded_cut():
    # Two upstream branches share node 2; it has exactly one stage and bed.
    raw=np.array([12.,11.,10.,9.]); q=np.ones(4)
    target=np.array([2,2,3,-1]); rank=np.array([3,2,1,0]); kind=np.zeros(4,dtype='u1')
    stage,bed,width,status=solve_nodes(raw,q,target,rank,kind,np.full(4,np.nan))
    assert stage[0]>=stage[2] and stage[1]>=stage[2]>=stage[3]
    assert np.all(raw-bed<=4) and np.all(status==0) and np.all(width>0)


def test_lake_and_ocean_boundary_and_cut_failure():
    raw=np.array([4.,3.,-.000038,10.]); q=np.ones(4)
    target=np.array([1,2,-1,-1]); rank=np.array([2,1,0,3]); kind=np.array([0,1,2,1],dtype='u1')
    level=np.array([np.nan,3.5,np.nan,0.])
    stage,bed,_,status=solve_nodes(raw,q,target,rank,kind,level)
    assert stage[1]==3.5 and stage[2]==0 and stage[2]-bed[2]>.05
    assert status[3]==1 and raw[3]-bed[3]<=4


def test_dry_pool_is_not_resolved():
    raw=np.array([5.]); stage,_,_,status=solve_nodes(raw,np.ones(1),np.array([-1]),np.array([0]),np.array([1]),np.array([np.nan]))
    assert np.isnan(stage[0]) and status[0]!=0
