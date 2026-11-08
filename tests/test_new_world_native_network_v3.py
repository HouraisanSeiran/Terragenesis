import numpy as np
from terrain_pipeline.new_world_native_event_correction import corrected_capacity
from terrain_pipeline.new_world_native_network_v3 import local_path, profile


def test_notch_capacity_conserves_explicit_added_water():
    capacity=np.array([10.,20.])
    total,extra=corrected_capacity(capacity,np.array([0,0,1]),np.array([1.,2.,.5]))
    np.testing.assert_array_equal(total,[13.,20.5])
    np.testing.assert_array_equal(extra,[3.,.5])
    state=np.array([6.5,10.25]); base=state*capacity/total
    np.testing.assert_allclose(base+base*extra/capacity,state)


def test_dry_shore_to_true_wet_support_with_descending_profile():
    bed=np.array([[12.,10.,8.,5.],[15.,15.,15.,15.]])
    labels=np.array([[0,0,0,0],[-1,-1,-1,-1]]).ravel()
    path=local_path(0,0,6.,labels,bed)
    assert path==[0,1,2,3]
    stages=profile(path,6.,bed,4)
    assert stages is not None and np.all(np.diff(stages)<=0)
    assert bed.ravel()[path[-1]]<6.


def test_wet_link_does_not_cross_dry_saddle():
    bed=np.array([[0.,2.,0.],[2.,2.,2.],[2.,2.,2.]])
    labels=np.zeros(9,dtype=int)
    assert local_path(0,0,1.,labels,bed,goal=2,wet_only=True) is None
