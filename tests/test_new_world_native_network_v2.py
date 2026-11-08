import numpy as np
from terrain_pipeline.new_world_native_network_v2 import wet_path


def test_pool_path_reaches_actual_wet_cell():
    bed=np.array([[4.,3.,2.],[4.,3.,1.],[8.,8.,8.]])
    labels=np.array([[0,0,0],[0,0,0],[-1,-1,-1]]).ravel()
    path=wet_path(0,0,2.5,labels,bed,bed.shape)
    assert path[0]==0 and bed.ravel()[path[-1]] < 2.45
    assert all(labels[i]==0 for i in path)


def test_pool_path_does_not_cross_other_pool_or_4m_barrier():
    bed=np.array([[0.,10.,0.],[10.,10.,0.],[0.,0.,0.]])
    labels=np.array([[0,0,1],[0,0,1],[1,1,1]]).ravel()
    assert wet_path(0,0,-1.,labels,bed,bed.shape) is None
