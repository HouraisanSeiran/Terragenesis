import numpy as np
from tools.verify_native_ownership import replay, stable_id


def test_owner_replay_moves_pool_and_receiver_water_across_boundaries():
    # 2x4 grid: cell 0 drains into a pool anchored at 2, then to cell 3.
    order = np.array([3, 2, 0], dtype=np.int64)
    receiver = np.full(8, -1, dtype=np.int64)
    receiver[2] = 3
    labels = np.full(8, -1, dtype=np.int64)
    labels[[0, 2]] = 0
    flow = np.zeros(8)
    flow[0], flow[2] = 5, 4
    incoming, storage = np.zeros(1), np.zeros(1)
    counts, volumes = np.zeros(2, dtype=np.int64), np.zeros(2)
    replay(order, receiver, labels, np.array([2]), np.array([6.]), flow, incoming, storage, 0, 1, 2, 2, 4, counts, volumes)
    replay(order, receiver, labels, np.array([2]), np.array([6.]), flow, incoming, storage, 1, 3, 2, 2, 4, counts, volumes)
    assert storage[0] == 6
    assert flow[3] == 3
    assert counts.tolist() == [1, 0]
    assert volumes.tolist() == [5, 0]


def test_ids_bind_absolute_coordinates_source_and_kind():
    value = stable_id('pool', 6, 4, (-2, -1))
    assert value == stable_id('pool', 0, 4, (0, 0))
    assert value != stable_id('mouth', 6, 4, (-2, -1))
    assert value != stable_id('pool', 6, 4, (-2, -1), identity='another source')

