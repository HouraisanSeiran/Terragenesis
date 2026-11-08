import numpy as np
import pytest
from terrain_pipeline.new_world_native_geometry import native_lake_wet


def test_wet_lakes_use_actual_finite_pool_levels_and_masks():
    bed=np.array([[0.,0.,0.],[0.,2.,0.]])
    pools=np.array([[0,1,-1],[0,0,0]])
    ocean=np.array([[False,False,False],[True,False,False]])
    unknown=np.array([[False,False,False],[False,False,True]])
    wet=native_lake_wet(bed,pools,np.array([1.,np.nan]),ocean,unknown)
    assert np.array_equal(wet,[[True,False,False],[False,False,False]])
    with pytest.raises(ValueError):
        native_lake_wet(bed,np.full_like(pools,2),np.array([1.,np.nan]),ocean,unknown)
