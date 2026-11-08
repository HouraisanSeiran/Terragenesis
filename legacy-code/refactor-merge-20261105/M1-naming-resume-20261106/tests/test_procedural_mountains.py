import json
import subprocess
import sys

import numpy as np
import pytest

from terrain_pipeline.mountain_forms import MountainConfig, rasterize_procedural as rasterize, sample_procedural_height as sample_height, sample_procedural_stages as sample_stages
from terrain_pipeline.common_infra import WORLD_SEED, seed_mountains_v1, derive_subseed


def test_seed_and_point_order_are_stable():
    assert WORLD_SEED == 20260903
    assert derive_subseed(WORLD_SEED, "sites") != derive_subseed(WORLD_SEED, "erosion")
    config = MountainConfig(detail_strength=0)
    x = np.linspace(-50000, 50000, 101)
    z = np.sin(x / 10000) * 20000
    expected = sample_height(x, z, config)
    order = np.random.default_rng(42).permutation(x.size)
    actual = np.concatenate([sample_height(x[part], z[part], config) for part in np.array_split(order, 7)])
    assert np.array_equal(actual, expected[order])
    assert not np.array_equal(expected, sample_height(x, z, MountainConfig(world_seed=20260904, detail_strength=0)))


def test_nested_spacing_and_metadata():
    config = MountainConfig(family="granite_dome", detail_strength=0)
    fine = rasterize((-1200, -1800), (17, 17), 30, config)
    for spacing, stride in [(60, 2), (120, 4)]:
        coarse = rasterize((-1200, -1800), ((16 // stride) + 1,) * 2, spacing, config)
        assert np.array_equal(fine["height_m"][::stride, ::stride], coarse["height_m"])
    assert fine["metadata"]["world_seed"] == WORLD_SEED
    json.dumps(fine["metadata"], allow_nan=False)


def test_families_have_distinct_base_shapes_and_site_edges_are_continuous():
    coords = np.linspace(-16000, 16000, 129)
    xx, zz = np.meshgrid(coords, coords)
    fields = [sample_height(xx, zz, MountainConfig(family=f, detail_strength=0)) for f in
              ("granite_dome", "layered_massif", "glacial_horn")]
    for field in fields:
        assert np.ptp(field) > 500
    for i in range(3):
        for j in range(i):
            assert np.sqrt(np.mean((fields[i] - fields[j]) ** 2)) > 100
    x = np.array([24000.0 - 0.001, 24000.0 + 0.001])
    assert abs(np.diff(sample_height(x, [10000, 10000], MountainConfig(detail_strength=0)))[0]) < 0.1


def test_stages_share_macro_field_and_reconstruct_result():
    x, z = np.meshgrid(np.linspace(-30000, 30000, 49), np.linspace(-30000, 30000, 49))
    stages = [sample_stages(x, z, MountainConfig(family=f, detail_strength=0)) for f in
              ("granite_dome", "layered_massif", "glacial_horn")]
    assert all(np.array_equal(stages[0]["base_noise_m"], item["base_noise_m"]) for item in stages)
    for item in stages:
        assert np.array_equal(item["height_m"], item["advanced_base_m"] + item["regional_noise_delta_m"])
    for i in range(3):
        for j in range(i):
            assert np.sqrt(np.mean((stages[i]["regional_noise_delta_m"] - stages[j]["regional_noise_delta_m"]) ** 2)) > 50


def test_advanced_is_in_base_and_pointwise():
    x = np.linspace(-12000, 12000, 21)
    z = np.linspace(5000, -5000, 21)
    full = sample_stages(x, z)
    chunks = [sample_stages(x[:9], z[:9]), sample_stages(x[9:], z[9:])]
    for key in full:
        assert np.array_equal(full[key], np.concatenate([part[key] for part in chunks]))
    assert np.any(full["advanced_base_m"] != full["base_noise_m"])
    disabled = sample_stages(x, z, MountainConfig(detail_strength=0))
    assert np.array_equal(disabled["base_noise_m"], disabled["advanced_base_m"])
    fine = rasterize((-300, -300), (9, 9), 30)
    coarse = rasterize((-300, -300), (5, 5), 60)
    for key in full:
        assert np.array_equal(fine[key][::2, ::2], coarse[key])


@pytest.mark.parametrize("x,z", [([float('nan')], [0]), ([1e11], [0]), ([], []), ([0, 1], [0, 1, 2])])
def test_invalid_coordinates(x, z):
    with pytest.raises(ValueError):
        sample_height(x, z, MountainConfig(detail_strength=0))


@pytest.mark.parametrize("kwargs", [{"world_seed": -1}, {"world_seed": True}, {"family": "missing"}, {"detail_strength": float('nan')}, {"detail_strength": 1.1}, {"detail_strength": 1e-7}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        MountainConfig(**kwargs)


@pytest.mark.parametrize("shape,spacing", [((0, 1), 30), ((2.5, 2), 30), ((1025, 1024), 30), ((2, 2), float('inf')), ((2, 2), 0)])
def test_invalid_raster(shape, spacing):
    with pytest.raises(ValueError):
        rasterize((0, 0), shape, spacing, MountainConfig(detail_strength=0))


def test_module_import_does_not_load_model_dependencies():
    code = "import sys; import terrain_pipeline.procedural_mountains; assert 'torch' not in sys.modules; assert 'diffusion.geography_physical' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)
