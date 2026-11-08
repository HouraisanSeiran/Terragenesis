from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.mountain_forms import HALO_M, MAX_COORDINATE_M, LocalVolumeConfig, sample_local_volume_mountains
from terrain_pipeline.mountain_forms import ProductMountainConfig, sample_product_mountains


def test_stages_and_negative_only_gain():
    x, z = np.meshgrid(np.linspace(0, 24000, 19), np.linspace(0, 24000, 19))
    config = LocalVolumeConfig()
    result = sample_local_volume_mountains(x, z, config)
    control = sample_local_volume_mountains(x, z, replace(config, depth_gain=1))
    raw = result["raw_advanced_delta_m"]
    np.testing.assert_array_equal(result["raw_advanced_delta_m"], control["raw_advanced_delta_m"])
    np.testing.assert_allclose(result["final_delta_m"], result["slope_fade"] * np.where(raw < 0, raw * 2.4, raw))
    np.testing.assert_array_equal(result["final_delta_m"][raw >= 0], control["final_delta_m"][raw >= 0])
    assert np.any(raw < 0) and np.any(raw > 0)
    assert np.any(result["p"] == 0) and np.any(result["p"] > 0)
    np.testing.assert_array_equal(result["macro_height_m"][result["p"] == 0], result["h0_m"][result["p"] == 0])
    assert np.all((result["slope_fade"] >= 0) & (result["slope_fade"] <= 1))
    slope = np.hypot(result["slope_x"], result["slope_z"])
    assert np.all(result["slope_fade"][slope <= config.slope_fade_low] == 0)


def test_disabled_matches_product_macro_and_deterministic_sampling():
    x = np.array([-987654321.0, -24000, 0, 1234, 24000])
    z = np.array([123456789.0, -500, 0, 6789, 12000])
    config = LocalVolumeConfig(k=0, advanced_enabled=False, batch_size=2)
    whole = sample_local_volume_mountains(x, z, config)
    product = sample_product_mountains(x, z, ProductMountainConfig(advanced_enabled=False))
    np.testing.assert_array_equal(whole["height_m"], product["macro_height_m"])
    np.testing.assert_array_equal(whole["final_delta_m"], np.zeros(x.size))
    for i in range(x.size):
        part = sample_local_volume_mountains(x[i], z[i], replace(config, batch_size=1))
        for key in whole:
            np.testing.assert_array_equal(whole[key][i], part[key])


def test_shared_points_and_order():
    coords = np.arange(-3, 4) * 600.0
    fine = sample_local_volume_mountains(coords, 900, LocalVolumeConfig(batch_size=3))
    coarse = sample_local_volume_mountains(coords[::2][::-1], 900)
    for key in fine:
        np.testing.assert_array_equal(fine[key][::2][::-1], coarse[key])


@pytest.mark.parametrize("kwargs", [
    {"k": -1}, {"depth_gain": 0}, {"cell_size_m": 0},
    {"cell_threshold_low": 0.8, "cell_threshold_high": 0.8},
    {"slope_fade_low": float("nan")}, {"batch_size": True},
    {"world_seed": -1}, {"advanced_enabled": 1},
])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        LocalVolumeConfig(**kwargs)


def test_invalid_coordinates_and_halo():
    for x in ([], [float("nan")], [MAX_COORDINATE_M - HALO_M + 1]):
        with pytest.raises(ValueError):
            sample_local_volume_mountains(x, 0)
    sample_local_volume_mountains(MAX_COORDINATE_M - HALO_M, 0)
