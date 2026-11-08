"""Declared query fixtures exercise volcano protection without TD or core edits."""
from types import SimpleNamespace

import numpy as np
import pytest

from terrain_pipeline.island_mountains import (
    IslandMountainConfig,
    analyze_island_mountains,
    load_mountain_plan,
    sample_mountain_components,
    sample_mountain_weights,
    save_mountain_plan,
)


def declared_islands(volcano_weight=None):
    def query(x, z):
        x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
        left = (abs(x + 6000.) < 3000.) & (abs(z) < 3000.)
        right = (abs(x - 6000.) < 3000.) & (abs(z) < 3000.)
        land = left | right
        result = dict(elevation_m=np.where(land, 500., -4000.),
            base_elevation_m=np.full(x.shape, -4000.),
            protected=land, lagoon=np.zeros(x.shape, bool))
        if volcano_weight is not None:
            result['volcano_weight'] = volcano_weight(x, z)
        return result

    return SimpleNamespace(identity='a'*64,
        source=SimpleNamespace(identity='b'*64, bounds_m=(-15000., -8000., 15000., 8000.)),
        config=SimpleNamespace(world_seed=20260903), query=query)


def test_special_connected_island_excluded_and_ordinary_area_peak_unchanged(tmp_path):
    ordinary = declared_islands()
    original = analyze_island_mountains(ordinary)
    assert len(original.manifest['selected_components']) == 2
    product = declared_islands(lambda x, z: np.where((x < 0) & (abs(z) < 1000), .25, 0.))
    plan = analyze_island_mountains(product)
    rows = plan.manifest['components']
    special = next(row for row in rows if row['bounds_m'][0] < 0)
    normal = next(row for row in rows if row['bounds_m'][0] > 0)
    assert special['exposed_area_km2'] == 36.
    assert not special['accepted']
    assert special['exclusion_reasons'] == ['special-volcanic-morphology']
    assert normal == next(row for row in original.manifest['components'] if row['bounds_m'][0] > 0)
    assert plan.manifest['selected_components'] == [normal['component_id']]
    path = tmp_path/'volcano-plan.npz'
    save_mountain_plan(plan, path)
    restored = load_mountain_plan(path, plan.identity, product)
    assert restored.manifest == plan.manifest
    np.testing.assert_array_equal(sample_mountain_weights(restored, product, [-6000., 6000.], 0.), [0., 1.])


def test_missing_and_zero_volcano_field_have_identical_plan_and_sampling():
    legacy = declared_islands()
    zero = declared_islands(lambda x, z: np.zeros(x.shape))
    plan = analyze_island_mountains(legacy)
    same = analyze_island_mountains(zero)
    assert same.identity == plan.identity
    assert same.manifest == plan.manifest
    x = np.linspace(-15000., 15000., 401)
    np.testing.assert_array_equal(sample_mountain_weights(plan, legacy, x, 0.),
        sample_mountain_weights(same, zero, x, 0.))


@pytest.mark.parametrize('protection', [1e-12, .25, 1.])
def test_actual_sampling_protects_subgrid_volcano_and_keeps_order(protection):
    # This protected patch falls between analysis centres, so sampling must
    # enforce the query field even though both complete islands were selected.
    product = declared_islands(lambda x, z: np.where(
        (abs(x + 6000.) < 10.) & (abs(z) < 10.), protection, 0.))
    plan = analyze_island_mountains(product)
    assert len(plan.manifest['selected_components']) == 2
    x = np.array([-6000., -6100., 6000., 0.])
    weights = sample_mountain_weights(plan, product, x, 0.)
    components = sample_mountain_components(plan, product, x, 0.)
    assert weights[0] == 0. and components[0] == 0
    assert weights[1] > 0. and weights[2] > 0.
    assert components[1] > 0 and components[2] > 0
    assert weights[3] == 0. and components[3] == 0
    np.testing.assert_array_equal(weights[::-1], sample_mountain_weights(plan, product, x[::-1], 0.))
    np.testing.assert_array_equal(weights, np.concatenate([
        sample_mountain_weights(plan, product, x[:2], 0.),
        sample_mountain_weights(plan, product, x[2:], 0.)]))


def test_public_v5_product_and_cold_plan_protect_all_volcano_stages(tmp_path):
    from terrain_pipeline.ocean_islands import (
        OceanIslandConfig, PlateOceanSource, load_product, prepare_ocean_islands, save_product,
    )

    # A finite, entirely oceanic plate fixture; this is a CPU consumer test,
    # not a claim that production TD or the real plate source was exercised.
    shape = (40, 40)
    source = PlateOceanSource(
        dict(origin_x_m=-400000., origin_z_m=-400000., spacing_m=20000., shape_zx=shape),
        dict(elevation_m=np.full(shape, -4000.), plate_id=np.zeros(shape, dtype=np.int64),
            continental_fraction=np.zeros(shape), ocean_connected=np.ones(shape, bool),
            velocities_m_per_step=np.array([[1800., 500.]])), 'a'*64, 20260903)
    product = prepare_ocean_islands(source, OceanIslandConfig(hotspot_count=4, density='high',
        arcs=False, ridge=False, max_support_radius_m=30000., volcanic_fraction=.5))
    assert {feature.volcano_stage for feature in product.features} == {
        'none', 'young', 'mature', 'caldera', 'eroded'}
    plan = analyze_island_mountains(product, IslandMountainConfig(analysis_spacing_m=2000.))
    ordinary = [row for row in plan.manifest['components'] if row['accepted']]
    special = [row for row in plan.manifest['components']
        if 'special-volcanic-morphology' in row['exclusion_reasons']]
    assert ordinary and special
    assert all(row['exposed_area_km2'] > 25. for row in ordinary)
    assert all(not row['accepted'] for row in special)
    product_path = tmp_path/'v5-product.json'
    plan_path = tmp_path/'v5-mountains.npz'
    save_product(product, product_path)
    restored_product = load_product(product_path, product.identity)
    save_mountain_plan(plan, plan_path)
    restored_plan = load_mountain_plan(plan_path, plan.identity, restored_product)
    assert restored_plan.manifest == plan.manifest
    x = np.arange(-399000., 400000., 2000.)[None, :]
    z = np.arange(-399000., 400000., 2000.)[:, None]
    query = restored_product.query(x, z)
    weights = sample_mountain_weights(restored_plan, restored_product, x, z)
    protected = (query['volcano_weight'] > 0) & (query['elevation_m'] >= 0)
    assert protected.any() and (weights > 0).any()
    assert not weights[protected].any()
    np.testing.assert_array_equal(weights, sample_mountain_weights(plan, product, x, z))
