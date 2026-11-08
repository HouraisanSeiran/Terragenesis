"""Static volcanic morphology, continuous protection and old product replay."""

from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline.island_volcanoes import VOLCANO_STAGES
from terrain_pipeline.ocean_islands import (
    ALGORITHM, METRIC_ALGORITHM, VOLCANIC_ALGORITHM, FrozenOceanIslands, OceanIslandConfig,
    _identity, _config_record, _manifest, load_product, prepare_ocean_islands,
    save_product,
)
from test_ocean_islands import source_fixture


@pytest.fixture(scope="module")
def volcanic():
    return prepare_ocean_islands(source_fixture(), OceanIslandConfig(
        hotspot_count=8, density="high", arcs=False, ridge=False, volcanic_fraction=1.))


def _isolated(product, stage):
    feature = next(f for f in product.features if f.stage == 0)
    feature = replace(feature, volcano_stage=stage)
    return FrozenOceanIslands(product.source, product.config, (feature,),
                              _manifest(product.source, product.config, (feature,), {}))


@pytest.mark.parametrize("value", [-.01, 1.01, True, None, "0.2", float("nan"), float("inf")])
def test_fraction_rejects_invalid(value):
    with pytest.raises(ValueError, match="volcanic_fraction"):
        OceanIslandConfig(volcanic_fraction=value)


@pytest.mark.parametrize("value", [-.01, 2.01, True, None, "0.2", float("nan"), float("inf")])
def test_lava_strength_rejects_invalid(value):
    with pytest.raises(ValueError, match="volcanic_lava_strength"):
        OceanIslandConfig(volcanic_lava_strength=value)


def test_voronoi_lava_changes_actual_surface_and_preserves_seabed(volcanic):
    off_config = replace(volcanic.config, volcanic_lava_strength=0., detail_strength=0.)
    on_config = replace(off_config, volcanic_lava_strength=1.)
    feature = replace(next(f for f in volcanic.features if f.stage == 0), volcano_stage="young")
    def product(config):
        local = replace(feature, parameter_identity=_identity(_config_record(config, ALGORITHM)))
        return FrozenOceanIslands(volcanic.source, config, (local,),
            _manifest(volcanic.source, config, (local,), {}))
    off, on = product(off_config), product(on_config)
    axis = np.linspace(-.35, .35, 181)*feature.support_radius_m
    x, z = feature.center_x_m+axis[None, :], feature.center_z_m+axis[:, None]
    original, changed = off.query(x, z), on.query(x, z)
    delta = changed["elevation_m"]-original["elevation_m"]
    assert np.max(np.abs(delta)) > 60.
    assert np.std(delta[original["elevation_m"] > 300.]) > 15.
    # Coarse accumulation extends an uneven shoreline but never cuts into the
    # existing submarine base; the fine signed texture fades before sea level.
    assert np.all(delta[original["elevation_m"] <= 0.] >= -1e-9)
    assert np.any(original["land"] != changed["land"])
    for key in ("base_elevation_m", "lagoon"):
        np.testing.assert_array_equal(original[key], changed[key])


def test_default_and_exposed_hotspot_stage_mapping(volcanic):
    assert OceanIslandConfig().volcanic_fraction == .2
    for feature in volcanic.features:
        if feature.kind == "hotspot" and feature.peak_elevation_m > 0:
            assert feature.volcano_stage == VOLCANO_STAGES[min(3, feature.stage)]
        else:
            assert feature.volcano_stage == "none"
    assert set(VOLCANO_STAGES) <= {f.volcano_stage for f in volcanic.features}


def test_upper_cone_is_steeper_than_low_lava_apron(volcanic):
    product = _isolated(volcanic, "young")
    feature = product.features[0]
    angles = np.arange(64)*2*np.pi/64
    radii = np.array([.04, .075, .16, .26])[:, None]
    x = feature.center_x_m + feature.support_radius_m*radii*np.cos(angles)
    z = feature.center_z_m + feature.support_radius_m*radii*np.sin(angles)
    heights = product.query(x, z)["elevation_m"].mean(axis=1)
    upper_slope = (heights[0]-heights[1])/.035
    apron_slope = (heights[2]-heights[3])/.10
    assert upper_slope > 3*apron_slope


def test_four_stages_change_real_height_crater_width_and_eroded_asymmetry(volcanic):
    profiles = {}
    for stage in VOLCANO_STAGES:
        product = _isolated(volcanic, stage)
        feature = product.features[0]
        axis = np.linspace(-.25, .25, 1001)*feature.support_radius_m
        fields = product.query(feature.center_x_m+axis, np.full_like(axis, feature.center_z_m))
        profiles[stage] = fields["elevation_m"]
        assert np.isfinite(profiles[stage]).all()
        assert fields["volcano_weight"][500] > .99
        assert np.all((fields["volcano_weight"] >= 0) & (fields["volcano_weight"] <= 1))
        assert np.all(fields["volcano_weight"][~fields["land"]] == 0)
    assert np.argmax(profiles["young"][500:]) < np.argmax(profiles["caldera"][500:])
    assert profiles["caldera"][500] + 300 < profiles["caldera"].max()
    assert profiles["mature"].max() > profiles["young"].max() > profiles["eroded"].max()
    assert np.max(np.abs(profiles["eroded"] - profiles["eroded"][::-1])) > 100
    assert len({p.tobytes() for p in profiles.values()}) == 4


def test_eroded_collapse_does_not_cut_outer_apron_or_submarine_base(volcanic):
    young, eroded = (_isolated(volcanic, stage) for stage in ("young", "eroded"))
    feature = young.features[0]
    angles = np.arange(256)*2*np.pi/256
    radii = np.linspace(.20, .70, 51)[:, None]
    x = feature.center_x_m + feature.support_radius_m*radii*np.cos(angles)
    z = feature.center_z_m + feature.support_radius_m*radii*np.sin(angles)
    original = young.query(x, z)
    aged = eroded.query(x, z)
    assert np.any(original["elevation_m"] < 0)
    assert np.any(original["elevation_m"] > 0)
    np.testing.assert_allclose(aged["elevation_m"], original["elevation_m"], atol=1e-9, rtol=0)


@pytest.mark.parametrize("stage", ["young", "mature", "caldera"])
def test_summit_contains_a_bounded_visible_depression(volcanic, stage):
    product = _isolated(volcanic, stage)
    feature = product.features[0]
    axis = np.linspace(-.08, .08, 321)*feature.support_radius_m
    heights = product.query(feature.center_x_m+axis[None, :],
                            feature.center_z_m+axis[:, None])["elevation_m"]
    # A summit depression must have higher terrain in every direction, not
    # merely be the low side of a smooth cone. Sample a 600..1200m-scale ring.
    from scipy.ndimage import minimum_filter
    minima = (heights == minimum_filter(heights, size=3)) & (heights > .25*feature.peak_elevation_m)
    candidates = np.argwhere(minima[65:-65, 65:-65])+65
    angles = np.arange(32)*2*np.pi/32
    candidates = candidates[np.argsort(heights[candidates[:, 0], candidates[:, 1]])[:64]]
    ring_radii = np.r_[.010, .016, .023, np.linspace(.030, .090, 13)][None, :, None]*feature.support_radius_m
    rings = product.query(feature.center_x_m+axis[candidates[:, 1]][:, None, None]+ring_radii*np.cos(angles),
                          feature.center_z_m+axis[candidates[:, 0]][:, None, None]+ring_radii*np.sin(angles))["elevation_m"]
    # Irregular rims need not lie at one radius in every direction. Each ray
    # must cross a higher wall within this bounded summit neighbourhood.
    best_depth = np.max(rings.max(axis=1).min(axis=1)-heights[candidates[:, 0], candidates[:, 1]])
    assert best_depth > 80.


def test_fraction_zero_exact_v3_and_layout_preserved(volcanic):
    off = prepare_ocean_islands(volcanic.source, replace(volcanic.config, volcanic_fraction=0))
    lava_off = prepare_ocean_islands(volcanic.source, replace(off.config, volcanic_lava_strength=0.))
    config = off.config
    old_features = tuple(replace(f, algorithm=METRIC_ALGORITHM,
        parameter_identity=_identity(_config_record(config, METRIC_ALGORITHM))) for f in off.features)
    old = FrozenOceanIslands(off.source, config, old_features,
        _manifest(off.source, config, old_features, {}, algorithm=METRIC_ALGORITHM))
    rng = np.random.default_rng(20260903)
    x, z = rng.uniform(-799999, 799999, (2, 5001))
    for key, value in old.query(x, z).items():
        np.testing.assert_array_equal(off.query(x, z)[key], value)
        np.testing.assert_array_equal(lava_off.query(x, z)[key], value)
    assert not off.query(x, z)["volcano_weight"].any()
    for original, disabled in zip(volcanic.features, off.features):
        a, b = asdict(original), asdict(disabled)
        for key in ("volcano_stage", "parameter_identity"):
            a.pop(key); b.pop(key)
        assert a == b
    assert "volcanic_fraction" not in old.manifest["config"]
    assert all("volcano_stage" not in f for f in old.manifest["features"])


def test_caldera_survives_ordinary_overlapping_platform_and_cold_read(volcanic, tmp_path):
    caldera = _isolated(volcanic, "caldera")
    feature = caldera.features[0]
    ordinary = replace(feature, feature_id=feature.feature_id+":ordinary", volcano_stage="none",
                       peak_elevation_m=feature.peak_elevation_m*1.5)
    features = tuple(sorted((feature, ordinary), key=lambda f:f.feature_id))
    combined = FrozenOceanIslands(caldera.source, caldera.config, features,
        _manifest(caldera.source, caldera.config, features, {}))
    centre = (feature.center_x_m, feature.center_z_m)
    assert combined.query(*centre)["elevation_m"] == caldera.query(*centre)["elevation_m"]
    restored = save_product(combined, tmp_path/"volcanic.npz")
    assert restored.identity == combined.identity
    for key, value in combined.query(*centre).items():
        np.testing.assert_array_equal(restored.query(*centre)[key], value)


def test_actual_v3_world_replays_every_query_field():
    directory = Path(__file__).resolve().parents[1]/".scratch/ocean-islands-20261106/run-metric-v3-2km"
    if not (directory/"islands.npz").exists():
        pytest.skip("historical v3 product absent")
    product = load_product(directory/"islands.npz")
    assert product.manifest["algorithm"] == METRIC_ALGORITHM != ALGORITHM
    assert product.config.volcanic_fraction == 0
    assert all(f.volcano_stage == "none" for f in product.features)
    with np.load(directory/"world.npz", allow_pickle=False) as archive:
        x, z = archive["x_m"], archive["z_m"]
        if x.ndim == 1 and z.ndim == 1:
            x, z = np.meshgrid(x, z)
        fields = product.query(x[::29, ::31], z[::29, ::31])
        assert "volcano_weight" not in fields
        for key, value in fields.items():
            np.testing.assert_array_equal(value, archive[key][::29, ::31])


def test_actual_v4_world_replays_every_query_field_and_is_read_only(tmp_path):
    directory = Path(__file__).resolve().parents[1]/".scratch/volcanic-islands-20261107/actual-final-v4"
    if not (directory/"islands.npz").exists():
        pytest.skip("historical v4 product absent")
    product = load_product(directory/"islands.npz")
    assert product.manifest["algorithm"] == VOLCANIC_ALGORITHM != ALGORITHM
    assert "volcanic_fraction" in product.manifest["config"]
    assert any(f.volcano_stage != "none" for f in product.features)
    with np.load(directory/"world.npz", allow_pickle=False) as archive:
        fields = product.query(archive["x_m"][None, :], archive["z_m"][:, None])
        for key, value in fields.items():
            np.testing.assert_array_equal(value, archive[key])
    with pytest.raises(ValueError, match="read-only"):
        save_product(product, tmp_path/"forbidden-v4.npz")


def test_provisional_untextured_v5_cold_replay_is_exact():
    directory = Path(__file__).resolve().parents[1]/".scratch/volcanic-islands-refinement-20261108/preview-attempt-1"
    if not (directory/"young-island.npz").exists():
        pytest.skip("provisional untextured v5 replay fixture absent")
    for stage in VOLCANO_STAGES:
        product = load_product(directory/f"{stage}-island.npz")
        assert product.config.volcanic_lava_strength == 0
        assert "volcanic_lava_strength" not in product.manifest["config"]
        assert "lava_geometry" not in product.manifest["volcano_model"]
        with np.load(directory/f"{stage}-samples.npz", allow_pickle=False) as archive:
            fields = product.query(archive["x_m"][None, :], archive["z_m"][:, None])
            for key, value in fields.items():
                np.testing.assert_array_equal(value, archive[key])


def test_compact_voronoi_stencil_is_continuous_at_warped_negative_boundaries():
    from scipy.optimize import brentq
    from terrain_pipeline.island_volcanoes import _lava_cells, _lattice_value
    seed, spacing = 20260903, 720.
    differences = []
    for z in (-3.25, -.30, .65):
        for boundary in range(-3, 3):
            def warped_coordinate(x):
                return x+.48*_lattice_value(np.asarray(x/1.7), np.asarray(z/1.7), seed, "warp-x")-boundary
            root = brentq(warped_coordinate, boundary-.5, boundary+.5)
            samples = _lava_cells(np.array([root-1e-7, root, root+1e-7])*spacing, z*spacing, spacing, seed)
            differences.append(abs(samples[2]-samples[0]))
            # Matching one-sided first derivatives additionally catches a
            # compact weight that merely reaches zero with a kink.
            assert abs(samples[2]-2*samples[1]+samples[0]) < 1e-9
    assert max(differences) < 1e-5


@pytest.mark.parametrize("strength", [0., .4, 1.5])
def test_lava_strength_roundtrips_geometry_domain_stats_and_manifest(volcanic, tmp_path, strength):
    config = replace(volcanic.config, volcanic_lava_strength=strength)
    feature = replace(next(f for f in volcanic.features if f.stage == 0), volcano_stage="caldera",
                      parameter_identity=_identity(_config_record(config, ALGORITHM)))
    product = FrozenOceanIslands(volcanic.source, config, (feature,),
        _manifest(volcanic.source, config, (feature,), {}))
    restored = save_product(product, tmp_path/f"strength-{strength}.npz")
    assert restored.config.volcanic_lava_strength == strength
    assert restored.manifest == product.manifest
    assert restored.valley_domains == product.valley_domains
    assert ("lava_geometry" in product.manifest["volcano_model"]) == (strength > 0)
    axis = np.linspace(-.4, .4, 81)*feature.support_radius_m
    x, z = feature.center_x_m+axis[None, :], feature.center_z_m+axis[:, None]
    for key, value in product.query(x, z).items():
        np.testing.assert_array_equal(restored.query(x, z)[key], value)


def test_special_surface_has_no_ordinary_valley_injection_and_is_query_order_independent(volcanic):
    product = _isolated(volcanic, "eroded")
    feature = product.features[0]
    config = replace(product.config, valley_strength=0.)
    uncut_feature = replace(feature, parameter_identity=_identity(asdict(config)))
    uncut = FrozenOceanIslands(product.source, config, (uncut_feature,),
        _manifest(product.source, config, (uncut_feature,), {}))
    axis = np.linspace(-.62, .62, 121)*feature.support_radius_m
    x, z = np.broadcast_arrays(feature.center_x_m+axis[None, :], feature.center_z_m+axis[:, None])
    fields = product.query(x, z)
    uncut_fields = uncut.query(x, z)
    reversed_fields = product.query(x[::-1, ::-1], z[::-1, ::-1])
    first_tile, second_tile = product.query(x[:59], z[:59]), product.query(x[59:], z[59:])
    for key, value in fields.items():
        np.testing.assert_array_equal(value, uncut_fields[key])
        np.testing.assert_array_equal(value[::-1, ::-1], reversed_fields[key])
        np.testing.assert_array_equal(value, np.concatenate([first_tile[key], second_tile[key]]))


def test_subseed_changes_actual_eccentric_edifice_geometry(volcanic):
    product = _isolated(volcanic, "young")
    feature = product.features[0]
    another = replace(feature, subseed=feature.subseed+1)
    changed = FrozenOceanIslands(product.source, product.config, (another,),
        _manifest(product.source, product.config, (another,), {}))
    axis = np.linspace(-.4, .4, 161)*feature.support_radius_m
    x, z = feature.center_x_m+axis[None, :], feature.center_z_m+axis[:, None]
    first, second = product.query(x, z), changed.query(x, z)
    assert np.max(np.abs(first["elevation_m"]-second["elevation_m"])) > 100.
    assert np.any(first["land"] != second["land"])
    assert np.unravel_index(first["elevation_m"].argmax(), (161, 161)) != np.unravel_index(second["elevation_m"].argmax(), (161, 161))


@pytest.mark.parametrize("stage", VOLCANO_STAGES)
def test_shifted_edifice_apron_protection_and_local_joins_are_continuous(volcanic, stage):
    product = _isolated(volcanic, stage)
    feature = product.features[0]
    angles = np.arange(96)*2*np.pi/96
    # These boundaries include full replacement, the fade, and support end.
    radii = np.array([.13, .30, .36, .55, 1.])[:, None]
    samples = []
    for delta in (-1e-6, 1e-6):
        x = feature.center_x_m+feature.support_radius_m*(radii+delta)*np.cos(angles)
        z = feature.center_z_m+feature.support_radius_m*(radii+delta)*np.sin(angles)
        samples.append(product.query(x, z))
    assert np.max(np.abs(samples[0]["elevation_m"]-samples[1]["elevation_m"])) < 2.
    exposed_apron = (samples[0]["elevation_m"][:2] > 80.)
    assert exposed_apron.any()
    assert np.all(samples[0]["volcano_weight"][:2][exposed_apron] > .99)


def test_arc_stages_are_seeded_and_query_independent():
    source = source_fixture(boundaries=True)
    config = OceanIslandConfig(hotspot_count=0, ridge=False, density="high", volcanic_fraction=1)
    first = prepare_ocean_islands(source, config)
    arcs = [f for f in first.features if f.kind == "arc"]
    assert arcs and all(f.volcano_stage in VOLCANO_STAGES for f in arcs)
    again = prepare_ocean_islands(source, config)
    assert first.features == again.features
    for feature in arcs:
        x = feature.center_x_m + np.array([0., 1., 500.])
        z = np.full_like(x, feature.center_z_m)
        whole = first.query(x, z)
        for key, value in whole.items():
            np.testing.assert_array_equal(first.query(x[::-1], z[::-1])[key], value[::-1])


def test_reef_lagoon_retains_priority_and_original_land_has_no_volcano_weight(volcanic):
    config = replace(volcanic.config, atolls=True, warm_water_scenario=True)
    prepared = prepare_ocean_islands(volcanic.source, config)
    atoll = next(f for f in prepared.features if f.kind == "atoll")
    special = replace(next(f for f in prepared.features if f.kind == "hotspot" and f.stage == 0),
        center_x_m=atoll.center_x_m, center_z_m=atoll.center_z_m,
        support_radius_m=atoll.support_radius_m, volcano_stage="mature")
    features = tuple(sorted((atoll, special), key=lambda f:f.feature_id))
    combined = FrozenOceanIslands(prepared.source, config, features,
        _manifest(prepared.source, config, features, {}))
    result = combined.query(atoll.center_x_m, atoll.center_z_m)
    assert result["lagoon"] and result["elevation_m"] < 0
    assert result["volcano_weight"] == 0
    continental = prepare_ocean_islands(source_fixture(continent=True), volcanic.config)
    result = continental.query(np.array([200000., 400000.]), np.array([0., 0.]))
    assert result["land"].all() and not result["volcano_weight"].any()
