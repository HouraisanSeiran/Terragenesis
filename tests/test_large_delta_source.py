import numpy as np
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval


def test_full_pool_boundary_preserves_initial_water_and_routes_local_input():
    # Upstream cell 2 drains through the pool anchor 1 to mouth 0.
    order = np.array([0, 1, 2], dtype=np.int64)
    receiver = np.array([-1, 0, 1], dtype=np.int64)
    labels = np.array([-1, 0, 0], dtype=np.int32)
    anchors = np.array([1], dtype=np.int64)
    capacity = np.array([100.0])
    local = np.array([1.0, 2.0, 3.0])
    full = capacity.copy()
    flow, retained = route_pool_interval(local, order, receiver, labels, anchors, capacity, full)
    assert flow[0] == 6.0
    assert retained == 0.0
    assert full[0] == 100.0
    dry = np.zeros(1)
    transient, retained = route_pool_interval(local, order, receiver, labels, anchors, capacity, dry)
    assert transient[0] == 1.0
    assert retained == 5.0
    assert dry[0] == 5.0
