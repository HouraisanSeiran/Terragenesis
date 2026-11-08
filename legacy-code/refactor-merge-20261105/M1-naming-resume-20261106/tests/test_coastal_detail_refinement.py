from dataclasses import replace
import numpy as np
import pytest
from terrain_pipeline.coastal_terrain import classify
from terrain_pipeline.coastal_terrain import DetailParameters, detail_support, refine


def terrain():
    z, x = np.indices((120, 160))
    bed = ((x - 78) * .45 + .7 * np.sin(z / 9)).astype(np.float32)
    raw = (bed + 24 * np.sin(x / 2.7) * np.cos(z / 3.5)).astype(np.float32)
    valid = np.ones(bed.shape, bool)
    codes, shore = classify(bed, valid, [(60, 0)])
    return raw, bed, valid, codes, shore


def test_bounded_support_and_sign_changes_deterministic():
    raw, bed, valid, codes, shore = terrain()
    support = detail_support(bed, valid, codes, shore)
    before = bed.copy(), raw.copy()
    result, delta = refine(raw, bed, support=support)
    assert np.any(delta != 0)
    assert np.max(np.abs(delta)) <= 6.00001
    protected = (support["distance_m"] >= 240) | (np.abs(bed) >= 40) | ~valid
    np.testing.assert_array_equal(result[protected], bed[protected])
    changed_sign = (result < 0) != (bed < 0)
    assert changed_sign.any()
    assert np.max(support["distance_m"][changed_sign]) < 90
    np.testing.assert_array_equal(refine(raw, bed, support=support)[0], result)
    np.testing.assert_array_equal(result - bed, delta)
    np.testing.assert_array_equal(bed, before[0])
    np.testing.assert_array_equal(raw, before[1])


def test_shared_support_offset_halos_are_bitwise_identical():
    raw, bed, valid, codes, shore = terrain()
    support = detail_support(bed, valid, codes, shore)
    full, _ = refine(raw, bed, support=support)
    for z0, z1, x0, x1 in [(3, 105, 21, 137), (12, 118, 38, 150)]:
        window = np.s_[z0:z1, x0:x1]
        cropped, _ = refine(raw[window], bed[window], support={k: a[window] for k, a in support.items()})
        np.testing.assert_array_equal(cropped[24:-24, 24:-24], full[z0 + 24:z1 - 24, x0 + 24:x1 - 24])


def test_zero_equal_and_flat_inputs_do_not_invent_detail():
    raw, bed, valid, codes, shore = terrain()
    support = detail_support(bed, valid, codes, shore)
    np.testing.assert_array_equal(refine(raw, bed, support=support, params=replace(DetailParameters(), strength=0))[0], bed)
    np.testing.assert_array_equal(refine(bed, bed, support=support)[0], bed)
    flat = np.full_like(bed, 2)
    fake_support = {"weight": np.ones_like(bed), "distance_m": np.zeros_like(bed)}
    np.testing.assert_array_equal(refine(flat + 10, flat, support=fake_support)[0], flat)
    no_coast = detail_support(flat, valid, np.ones_like(codes), np.zeros_like(shore))
    assert not no_coast["weight"].any()


def test_unknown_enclosed_and_invalid_are_protected():
    raw, bed, valid, _, _ = terrain()
    bed[:, 80:83] = 1
    bed[0:15, 83:85] = -1  # unknown boundary component near the real ocean
    bed[60, 84] = -1  # enclosed water
    valid[45:50, 84] = False
    codes, shore = classify(bed, valid, [(60, 0)])
    support = detail_support(bed, valid, codes, shore)
    result, _ = refine(raw, bed, support=support)
    protected = ~valid | ((bed < 0) & (codes != 2))
    np.testing.assert_array_equal(result[protected], bed[protected])
    final_codes, _ = classify(result, valid, [(60, 0)])
    np.testing.assert_array_equal(final_codes[protected], codes[protected])


@pytest.mark.parametrize("changes", [{"strength": -1}, {"strength": float("nan")}, {"cap_m": 6.1}, {"radius_m": 750}, {"coast_band_m": 241}, {"elevation_band_m": 41}, {"sign_band_m": 91}, {"sigma_short_m": 190}, {"spacing_m": 31}])
def test_parameter_rejection(changes):
    with pytest.raises(ValueError):
        replace(DetailParameters(), **changes).validate()


def test_bad_arrays_and_support_rejected():
    raw, bed, valid, codes, shore = terrain()
    support = detail_support(bed, valid, codes, shore)
    with pytest.raises(ValueError):
        refine(raw[:40, :40], bed[:40, :40], support={k: a[:40, :40] for k, a in support.items()})
    raw[60, 75] = np.nan
    with pytest.raises(ValueError):
        refine(raw, bed, support=support)
    with pytest.raises(ValueError):
        refine(bed, bed, support={"weight": support["weight"]})
