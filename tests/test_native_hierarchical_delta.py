import numpy as np
import pytest
from terrain_pipeline.native_hierarchical_delta import route_tree


def test_multilevel_tree_preserves_water_and_solid():
    parents=np.array([-1,0,0,2,2]); masks=np.ones((5,2,2),bool)
    r=route_tree([100.,200.],[1.,2.],[10.,10.],parents,np.ones(5)*20,np.ones(5)*2,np.ones(5),masks,25.)
    assert np.allclose(r['edge_water_m3'][:,r['leaf_indices']].sum(axis=1),[100.,200.])
    assert np.isclose(r['stored_solid_m3'].sum()+r['edge_solid_out_m3'][:,r['leaf_indices']].sum(),3.)
    with pytest.raises(ValueError):route_tree([1.],[1.],[1.],[-1,2,1],[1.]*3,[1.]*3,[1.]*3,np.ones((3,1,1),bool),1.)
