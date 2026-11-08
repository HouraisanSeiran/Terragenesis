import numpy as np
from terrain_pipeline.lake import minimax_cost as minimax_cost
from terrain_pipeline.lake import invert_connected_storage as invert_connected_storage


def test_lake_storage_and_spill_balance():
    bed = np.array([[0., 1., 3.]])
    cost, _ = minimax_cost(bed, np.ones_like(bed, dtype=bool), (0, 0))
    stage, retained, excess, capacity, wet = invert_connected_storage(bed, cost, 3., 5000., 'a'*64)
    assert abs(capacity - 4500.) < 1e-8
    assert retained == capacity and excess == 500.
    assert stage == 3. and wet.tolist() == [[True, True, False]]
    assert retained + excess == 5000.
