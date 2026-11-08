import numpy as np

from terrain_pipeline.large_delta_tidal_reconstruction import reconstruct_coastal_water


def test_planar_coast_reduces_block_edges_and_conserves_water():
    y, x = np.indices((60, 60))
    bed = .012 * x + .007 * y
    stage = .46 + .035 * ((x // 10 + y // 10) % 3 - 1)
    original = np.maximum(stage - bed, 0.)
    area = np.full(bed.shape, 900.)
    result = reconstruct_coastal_water(bed, area, original)
    assert np.isclose(np.sum(result * area), np.sum(original * area), atol=1.e-8)
    def grid_edges(depth):
        wet = depth > 1.e-5
        horizontal = wet[1:] != wet[:-1]
        vertical = wet[:, 1:] != wet[:, :-1]
        return horizontal[9::10].sum() + vertical[:, 9::10].sum()
    assert grid_edges(result) < grid_edges(original)


def test_dry_barrier_and_invalid_area_block_water():
    bed = np.zeros((5, 11))
    bed[:, 5] = 2.
    area = np.ones_like(bed) * 900.
    area[0, :] = 0.
    depth = np.zeros_like(bed)
    depth[1:, :5] = 1.
    result = reconstruct_coastal_water(bed, area, depth)
    assert np.all(result[:, 5:] == 0)
    assert np.all(result[0] == 0)
    assert np.isclose(result.sum(), depth.sum())


def test_fractional_coast_and_separate_river_conserve_combined_water():
    y, x = np.indices((30, 30))
    bed = .01 * x + .005 * y
    coastal_area = np.where(x == 14, 450., 900.)
    river_area = 900. - coastal_area
    coast = np.maximum(.3 + .05 * (x // 10) - bed, 0.)
    river = np.where(river_area > 0, .5, 0.)
    before = (coast * coastal_area + river * river_area).sum()
    after_coast = reconstruct_coastal_water(bed, coastal_area, coast)
    after = (after_coast * coastal_area + river * river_area).sum()
    assert np.isclose(before, after, atol=1.e-8)
    assert np.array_equal(river, np.where(river_area > 0, .5, 0.))

def test_donor_can_drain_into_downstream_pool():
    bed = np.array([[1., 0.]])
    area = np.ones_like(bed)
    depth = np.array([[0.5, 0.]])
    result = reconstruct_coastal_water(bed, area, depth)
    assert result[0, 0] == 0
    assert result[0, 1] == 0.5
    assert np.all(result >= 0)
