import numpy as np
import pytest
from terrain_pipeline.large_delta_forward import forward_fields, forward_network
from terrain_pipeline.channel_geometry import formative_section


def test_forward_tree_uses_shared_width_and_conserves_fork_flow():
    bed=np.zeros((31,31)); valid=np.ones_like(bed,bool)
    ocean=np.zeros_like(valid); ocean[:,24:]=True
    plain=~ocean
    result=forward_network(bed,bed,plain,valid,ocean,(0,0),100.,(15,2),(1,0),20.,outlet_count=4)
    sections=result['sections']; parents=result['parent']
    assert all(r >= .55 for r in result['path_forward_ratio'])
    assert len(result['outlet_zx']) >= 2
    for i,p in enumerate(parents):
        reach=sections[sections[:,0]==i]; q=reach[0,8]
        assert np.allclose(reach[:,6],formative_section(q,.35,.35,0,.25,max_width_m=2000).width_m)
        assert np.allclose(reach[:,9],result['bed_m'][reach[:,3].astype(int),reach[:,4].astype(int)])
        children=np.flatnonzero(parents==i)
        if len(children):
            assert np.isclose(q,sum(sections[sections[:,0]==j][0,8] for j in children))
    roots=np.flatnonzero(parents==-1)
    assert np.isclose(sum(sections[sections[:,0]==j][0,8] for j in roots),20.)
    assert np.all(result['bed_m'] <= bed)


def test_invalid_direction_rejected():
    with pytest.raises(ValueError):
        forward_fields((2,2),(0,0),1,(0,0),(0,0))


def test_source_reach_is_joined_and_uses_same_width():
    from terrain_pipeline.large_delta_forward import attach_source_reach
    bed=np.zeros((31,31)); valid=np.ones_like(bed,bool)
    ocean=np.zeros_like(valid); ocean[:,24:]=True
    network=forward_network(bed,bed,~ocean,valid,ocean,(0,0),100.,(15,2),(1,0),20.)
    result=attach_source_reach(network,[(15,0),(15,1),(15,2)],bed,(0,0),100.,20.)
    assert result['parent'][0]==-1
    assert np.all(result['parent'][1:][network['parent']==-1]==0)
    assert np.isclose(result['sections'][0,6],formative_section(20.,.35,.35,0,.25,max_width_m=2000).width_m)
    assert np.all(result['river'][15,:3])
