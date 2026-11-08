import numpy as np

from terrain_pipeline.coastal_delta_routes import irregular_valley_path


def test_direction_cost_yields_to_head_obstacle():
    bed = np.zeros((25, 25))
    valid = np.ones_like(bed, dtype=bool)
    valid[11:15, :] = False
    valid[11:15, 3:7] = True
    cells, _ = irregular_valley_path(
        bed, valid, (7, 12), (19, 12), 1., 100., world_seed=20260903,
        initial_direction_xz=(1., 0.), direction_weight=5., direction_decay_m=1000.)
    assert np.all(valid[cells[:, 0], cells[:, 1]])
    assert tuple(cells[-1]) == (19, 12)
    assert np.any((cells[:, 0] >= 11) & (cells[:, 0] <= 14) & (cells[:, 1] < 7))


def test_direction_default_preserves_path():
    bed = np.zeros((20, 20))
    valid = np.ones_like(bed, dtype=bool)
    args = (bed, valid, (2, 3), (17, 15), 1., 100.)
    baseline = irregular_valley_path(*args, world_seed=20260903)
    explicit = irregular_valley_path(*args, world_seed=20260903, direction_weight=0.)
    assert all(np.array_equal(a, b) for a, b in zip(baseline, explicit))
