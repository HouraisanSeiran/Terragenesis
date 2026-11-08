import numpy as np

from terrain_pipeline.large_delta_terrain_product import make_product


def test_budget_and_protected_terrain():
    bed = np.full((80, 80), -4.0)
    bed[0, :] = 12
    bed[1, :] = -30
    ocean = np.ones_like(bed, dtype=bool)
    ocean[:, 0] = False
    valid = np.ones_like(ocean)
    valid[:, 1] = False
    footprint = np.ones((8, 8), dtype=bool)
    derived, deposit, _ = make_product(bed, ocean, valid, footprint,
        fine_origin_xz=(0, 0), coarse_origin_xz=(135, 135), solid_budget_m3=100000)
    assert np.isfinite(derived).all()
    assert deposit.sum() * 900 * .6 <= 100000.00001
    assert np.all(deposit[(bed >= 0) | (bed <= -24) | ~ocean | ~valid] == 0)
    np.testing.assert_allclose(derived, bed + deposit)


def test_coarse_centers_interpolate_smoothly_without_block_steps():
    bed = np.full((100, 100), -2.0)
    mask = np.ones_like(bed, dtype=bool)
    footprint = np.zeros((10, 10), dtype=bool)
    footprint[2:8, 2:8] = True
    _, deposit, _ = make_product(bed, mask, mask, footprint,
        fine_origin_xz=(0, 0), coarse_origin_xz=(135, 135))
    # A transect across a footprint edge changes continuously at 30 m,
    # including at the old 300 m block boundary.
    transect = deposit[50]
    assert np.max(np.abs(np.diff(transect))) < .25
    assert 0 < transect[20] < transect[50]


def test_expansion_and_deeper_toe_remain_budgeted_and_protect_deep_sea():
    bed = np.full((100, 100), -16.0)
    bed[:5] = -40
    valid = np.ones_like(bed, dtype=bool)
    footprint = np.zeros((10, 10), dtype=bool)
    footprint[2:8, 2:8] = True
    kwargs = dict(fine_origin_xz=(0, 0), coarse_origin_xz=(135, 135))
    _, baseline, _ = make_product(bed, valid, valid, footprint, **kwargs)
    _, expanded, _ = make_product(bed, valid, valid, footprint, **kwargs,
        footprint_expansion_m=550, full_depth_m=18, toe_depth_m=36)
    assert expanded.sum() > baseline.sum()
    assert np.all(expanded[:5] == 0)
    _, capped, _ = make_product(bed, valid, valid, footprint, **kwargs,
        footprint_expansion_m=550, full_depth_m=18, toe_depth_m=36,
        solid_budget_m3=10_000_000)
    assert capped.sum() * 900 * .6 <= 10_000_000.00001
