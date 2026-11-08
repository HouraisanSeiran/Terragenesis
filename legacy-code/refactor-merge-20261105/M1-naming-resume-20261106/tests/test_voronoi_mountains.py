import numpy as np
import pytest
import json

from diffusion.geographic_noise import _hash
from terrain_pipeline.mountain_forms import VoronoiConfig, _sample_batch, _structure, rasterize_voronoi as rasterize, sample_voronoi_stages as sample_stages
from terrain_pipeline.common_infra import seed_mountains_v1, derive_subseed


@pytest.fixture(scope="module")
def sampled():
    return rasterize((0, 0), (48, 48), 24000 / 47)


def test_protection_and_actual_stages(sampled):
    mask = sampled["protection_mask"]
    core = mask == 1
    assert core.any() and np.any(mask == 0) and np.any((mask > 0) & (mask < 1))
    np.testing.assert_array_equal(sampled["height_m"][core], sampled["advanced_base_m"][core])
    np.testing.assert_allclose(sampled["unprotected_height_m"], sampled["advanced_base_m"] + sampled["structure_delta_m"])
    assert np.max(np.abs(sampled["height_m"][mask == 0] - sampled["advanced_base_m"][mask == 0])) > 10


def test_chunk_order_and_common_points():
    x = np.array([-1e8, -6000.00001, -6000, -5999.99999, 0, 9000, 1e8])
    z = np.array([1e8, 0, 0, 0, 0, -9000, -1e8])
    full = sample_stages(x, z)
    order = np.array([6, 0, 4, 2, 5, 1, 3])
    shuffled = sample_stages(x[order], z[order])
    for key in ("advanced_base_m", "structure_delta_m", "protection_mask", "height_m"):
        np.testing.assert_array_equal(full[key][order], shuffled[key])
        np.testing.assert_array_equal(full[key][:3], sample_stages(x[:3], z[:3])[key])
        assert abs(full[key][1] - full[key][2]) < 0.1
    coarse = rasterize((-1000, -1000), (3, 3), 1000)
    fine = rasterize((-1000, -1000), (5, 5), 500)
    np.testing.assert_array_equal(coarse["height_m"], fine["height_m"][::2, ::2])


def test_families_and_seed():
    x = np.arange(8) * 1500
    z = np.arange(8)[:, None] * 1500
    fields = [sample_stages(x, z, VoronoiConfig(family=f))["structure_delta_m"] for f in ("mixed", "cellular_massif", "ridge_network")]
    assert not np.allclose(fields[0], fields[1])
    assert not np.allclose(fields[1], fields[2])
    changed = sample_stages(x, z, VoronoiConfig(world_seed=20260904))["height_m"]
    assert not np.allclose(changed, sample_stages(x, z)["height_m"])


@pytest.mark.parametrize("kwargs", [{"family": "invalid"}, {"world_seed": -1}, {"cell_size_m": 0}, {"warp_m": float("nan")}, {"anisotropy": 4}, {"protection_threshold_m": 0}, {"detail_strength": True}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        VoronoiConfig(**kwargs)


def test_invalid_coordinates():
    with pytest.raises(ValueError):
        sample_stages([float("nan")], [0])
    with pytest.raises(ValueError):
        rasterize((0, 0), (2, 2), 0)
    with pytest.raises(ValueError):
        sample_stages([0, 1e9 - 599], [0, 0])


def test_batching_matches_unbatched():
    x = np.linspace(-24000, 24000, 16400)
    z = np.sin(x / 1000) * 10000
    batched = sample_stages(x, z)
    unbatched = _sample_batch(x, z)
    for key in ("advanced_base_m", "structure_delta_m", "unprotected_height_m", "protection_mask", "height_m"):
        np.testing.assert_array_equal(batched[key], unbatched[key])


@pytest.mark.parametrize("world_seed", [20260903, 20260904])
@pytest.mark.parametrize("family", ["cellular_massif", "ridge_network"])
def test_transformed_lattice_boundary_against_larger_search(world_seed, family):
    config = VoronoiConfig(world_seed=world_seed, family=family, warp_m=0, anisotropy=3)
    seed = derive_subseed(world_seed, "voronoi-sites")
    warp_seed = derive_subseed(world_seed, "voronoi-warp")
    angle = 2 * np.pi * ((seed % 1000003) / 1000003)
    gx = np.array([-2 - 1e-8, -2, -2 + 1e-8, 0.2, 0.8, 1.0])
    gz = np.array([0.3, 0.3, 0.3, -1 - 1e-8, -1 + 1e-8, 1.0])
    a = gx * config.cell_size_m * config.anisotropy
    b = gz * config.cell_size_m
    x = np.cos(angle) * a - np.sin(angle) * b
    z = np.sin(angle) * a + np.cos(angle) * b
    distances, attrs = [], []
    ix, iz = np.floor(gx).astype(int), np.floor(gz).astype(int)
    for dz in range(-3, 4):
        for dx in range(-3, 4):
            cx, cz = ix + dx, iz + dz
            sx = cx + 0.5 + 0.25 * _hash(cx, cz, seed, 1)
            sz = cz + 0.5 + 0.25 * _hash(cx, cz, seed, 2)
            distances.append(np.hypot(gx - sx, gz - sz))
            attrs.append(_hash(cx, cz, seed, 3))
    distances, attrs = np.array(distances), np.array(attrs)
    order = np.argsort(distances, axis=0)
    first = np.take_along_axis(distances, order[:1], axis=0)[0]
    second = np.take_along_axis(distances, order[1:2], axis=0)[0]
    attr = np.take_along_axis(attrs, order[:1], axis=0)[0]
    t = np.clip((second - first) / 0.7, 0, 1)
    interior = t * t * (3 - 2 * t)
    if family == "cellular_massif":
        expected = 1.3 * np.exp(-2.2 * first * first) * (0.8 + 0.2 * attr * interior) - 0.55
    else:
        expected = 1.35 * np.exp(-5 * (second - first)) - 0.42
    actual = _structure(x, z, config, seed, warp_seed)
    np.testing.assert_allclose(actual, config.amplitude_m * expected, atol=1e-9)
    assert abs(actual[0] - actual[2]) < 0.001


def test_metadata_json_with_numpy_shape():
    result = rasterize((0, 0), (np.int64(2), np.int64(2)), np.float64(30))
    json.dumps(result["metadata"])
    assert result["metadata"]["subseeds"]["advanced-phacelle"] == 10860721302913963045


def test_transition_width_preserves_core():
    wide = rasterize((0, 0), (32, 32), 24000 / 31)
    narrow = rasterize((0, 0), (32, 32), 24000 / 31,
                       VoronoiConfig(protection_transition_m=17.5))
    np.testing.assert_array_equal(wide["protection_mask"] == 1, narrow["protection_mask"] == 1)
    assert np.mean((wide["protection_mask"] > 0) & (wide["protection_mask"] < 1)) > np.mean(
        (narrow["protection_mask"] > 0) & (narrow["protection_mask"] < 1))
