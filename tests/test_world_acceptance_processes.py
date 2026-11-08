import json

import numpy as np
import pytest

from terrain_pipeline.basin_storage import PoolStorage as PoolStorage
from terrain_pipeline.soil_water import constant_month_soil
from terrain_pipeline.environment_product import prepare_world_acceptance_processes
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval
from terrain_pipeline.climate_forcing import native_climate_sampler
from terrain_pipeline.climate_forcing import boundary_influence_mask
from terrain_pipeline.climate_forcing import couple_td_climate
from terrain_pipeline.drainage import accumulate_graph as accumulate_graph


def test_pool_retains_then_overflows_into_downstream_pool():
    # Node 3 drains to a lake at 2, whose spill drains into lake 1 then ocean 0.
    order = np.arange(4, dtype=np.int64)
    receiver = np.array([-1, 0, 1, 2], np.int64)
    labels = np.array([-1, 0, 1, -1], np.int64)
    anchors = np.array([1, 2], np.int64)
    capacity = np.array([5., 10.])
    storage = np.zeros(2)
    first, retained = route_pool_interval(np.array([0., 0., 0., 12.]),
        order, receiver, labels, anchors, capacity, storage)
    np.testing.assert_allclose(storage, [2., 10.])
    assert first[0] == 0
    assert retained == 12
    second, retained = route_pool_interval(np.array([0., 0., 0., 8.]),
        order, receiver, labels, anchors, capacity, storage)
    assert second[0] == 5.
    assert retained == 3.
    assert storage.sum() + second[0] == 20.


def test_actual_90m_prism_stage_volume_is_monotone():
    bed = np.array([0., 1., 2.])
    pool = PoolStorage(np.arange(3), bed, 3., 8100.)
    assert pool.capacity_m3 == 48600.
    volumes = np.linspace(0., pool.capacity_m3, 19)
    stages = [pool.stage_at_volume(volume) for volume in volumes]
    assert np.all(np.diff(stages) > 0)
    np.testing.assert_allclose([pool.volume_at_stage(stage) for stage in stages], volumes,
        atol=1e-8)


def test_streamed_soil_closes_and_responds_to_rain_and_temperature():
    initial = np.zeros((3, 3), np.float64)
    states = initial.copy()
    liquid = np.array([0., 100., 100.])
    runoff, et = constant_month_soil(liquid, states, np.array([10., 0., 30.]), 31)
    np.testing.assert_allclose(liquid, runoff + et + (states - initial).sum(axis=0), atol=1e-9)
    assert runoff[0] == 0.
    assert runoff[1] > runoff[2]
    assert et[2] > et[1]


def test_same_source_small_pipeline_and_cropped_boundary(tmp_path):
    rows, cols = np.mgrid[:8, :9]
    elevation = 15. + cols * 2. + rows * .2
    elevation[3:5, 3:5] -= 8.
    ocean = np.zeros(elevation.shape, bool)
    ocean[:, 0] = True
    elevation[:, 0] = -2.
    terrain = tmp_path / "terrain.npz"
    native_path = tmp_path / "composed30.npy"
    np.save(native_path, np.full((1602, 1602), 25., np.float32))
    np.savez(terrain, elevation_m=elevation, ocean_mask=ocean,
        raw_td_m=elevation, climate_base=np.stack([np.full(elevation.shape, v)
            for v in (16., 900., 1100., 40., -.006)]),
        metadata_json=json.dumps(dict(spacing_m=90., origin_xz_m=[123.5, -90.],
            native_source_origin_xz_m=[123.5 - 24000., -90. - 24000.],
            native_source_paths=dict(composed_30m=dict(path=str(native_path))),
            world_seed=20261020, terrain_identity="test-TD-source")))
    output = tmp_path / "result"
    report = prepare_world_acceptance_processes(terrain, output, spinup_years=0,
        river_display_q_m3_s=.0001)
    assert report["cell_area_m2"] == 8100.
    assert report["boundaries"]["cropped_land_outlet_cells"] > 0
    assert report["boundaries"]["external_inflow_m3"] is None
    assert report["origin_xz_m"] == [123.5, -90.]
    assert abs(report["succession"]["nutrient_residual_kg"]) < 1e-7
    resumed = prepare_world_acceptance_processes(terrain, output, spinup_years=0,
        river_display_q_m3_s=.0001, resume=True)
    assert resumed["seasonal_water_ledger"] == report["seasonal_water_ledger"]
    assert resumed["seasonal_storage_end_m3"] == report["seasonal_storage_end_m3"]
    assert resumed["routing_water_ledger"] == report["routing_water_ledger"]
    assert abs(report["seasonal_balance_residual_m3"]) < 1e-6
    assert max(abs(row["residual_m3"]) for row in report["routing_water_ledger"]) < 1e-6
    with np.load(output / "product.npz") as product:
        assert np.array_equal(product["elevation_m"], elevation)
        assert np.all(product["bed_m"] <= elevation)
        assert np.max(elevation - product["bed_m"]) <= 4.
        assert product["node_x_m"].shape == (elevation.size,)
        assert np.all(product["node_x_m"].reshape(elevation.shape)[:, 0] > 123.5 - 32.)
        assert product["monthly_precipitation_mm"].shape == (12, *elevation.shape)
        np.testing.assert_allclose(product["annual_precipitation_mm"],
            product["monthly_precipitation_mm"].sum(axis=0))
        np.testing.assert_allclose(product["annual_temperature_c"], 16., atol=1e-12)
        np.testing.assert_allclose(product["monthly_temperature_c"].std(axis=0), 9., atol=1e-12)
        assert not np.any(product["lake_mask"] & ocean)
        for name in ("snow_swe_mm", "soil_water_mm", "soil_depth_m",
                     "cover_suitability_fraction", "land_cover_index"):
            assert np.all(product[name][ocean] == 0.)
        assert np.all(product["monthly_snow_swe_mm"][:, ocean] == 0.)
        assert np.all(product["monthly_soil_water_mm"][:, ocean] == 0.)
        np.testing.assert_allclose(product["vegetation_fraction"],
            product["biomass_carbon_kg_m2"] / 8.)
        assert np.all(product["vegetation_fraction"][ocean] == 0.)


def test_native_climate_sampler_rejects_missing_support_without_clamping(tmp_path):
    path = tmp_path / "source.npy"
    native = np.arange(25, dtype=np.float32).reshape(5, 5)
    np.save(path, native)
    sampler, _ = native_climate_sampler(dict(native_source_paths=dict(composed_30m=dict(path=str(path))),
        native_source_origin_xz_m=[100., 200.], composition=dict(filter_radius_native_cells=1)))
    assert sampler(np.array([145.]), np.array([245.]))[0] == 9.
    with pytest.raises(ValueError, match="lacks unfiltered climate query support"):
        sampler(np.array([100.]), np.array([200.]))


def test_boundary_influence_reaches_downstream_interior_not_only_outlets():
    shape = (24, 24)
    source = boundary_influence_mask(shape, np.zeros(shape, bool))
    receiver = np.arange(24 * 24, dtype=np.int64).reshape(shape) + 1
    receiver[:, -1] = -1
    order = np.arange(24 * 24 - 1, -1, -1, dtype=np.int64)
    affected = accumulate_graph(receiver.ravel(), order, source.astype(float)) > 0
    assert source[12, 7]
    assert not source[12, 10]
    assert affected[12, 10]


def test_td_climate_keeps_conditioned_means_lapse_variability_and_existing_phase():
    cycle = np.cos(np.arange(12) * 2. * np.pi / 12.)[:, None]
    refined = dict(monthly_temperature_c=np.broadcast_to(-17. + 3. * cycle, (12, 3)),
        monthly_precipitation_mm=np.broadcast_to(100. * (1. + .3 * cycle), (12, 3)),
        precipitation_multiplier=np.array([.5, 1., 2.]))
    base = np.tile(np.array([16., 900., 1100., 40., -.006])[:, None], (1, 3))
    coupled = couple_td_climate(base, np.array([100., 100., -100.]),
        np.array([100., 1100., -10.]), refined)
    temperature = coupled["monthly_temperature_c"]
    precipitation = coupled["monthly_precipitation_mm"]
    np.testing.assert_allclose(temperature.mean(axis=0), [16., 10., 16.], atol=1e-12)
    np.testing.assert_allclose(temperature.std(axis=0), 9., atol=1e-12)
    np.testing.assert_allclose(precipitation.sum(axis=0), [550., 1100., 2200.], atol=1e-10)
    np.testing.assert_allclose(precipitation.std(axis=0) / precipitation.mean(axis=0), .4, atol=1e-12)
    assert not coupled["precipitation_cv_fallback"].any()
    assert np.all(temperature.argmax(axis=0) == 0)
    assert np.all(precipitation.argmax(axis=0) == 0)


def test_td_precipitation_cv_fallback_preserves_positive_existing_seasonality():
    rain = (1. + .5 * np.cos(np.arange(12) * 2. * np.pi / 12.))[:, None]
    refined = dict(monthly_temperature_c=rain, monthly_precipitation_mm=rain,
        precipitation_multiplier=np.array([5.]))
    base = np.array([[16.], [900.], [1100.], [200.], [-.006]])
    coupled = couple_td_climate(base, np.array([0.]), np.array([0.]), refined)
    assert coupled["precipitation_cv_fallback"].item()
    assert np.all(coupled["monthly_precipitation_mm"] > 0.)
    np.testing.assert_allclose(coupled["monthly_precipitation_mm"].sum(), 3200.)
    np.testing.assert_allclose(coupled["monthly_precipitation_mm"] / 3200., rain / rain.sum())
