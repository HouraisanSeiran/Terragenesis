"""Behavioural checks for bounded, frozen ocean landforms (CPU only)."""

from collections import Counter, defaultdict
from dataclasses import FrozenInstanceError, asdict, replace
import json
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline.common_infra import WORLD_SEED, array_sha256_raw, canonical_json
from terrain_pipeline.ocean_islands import (
    OceanIslandConfig, PlateOceanSource, prepare_ocean_islands, save_product, load_product,
)


def source_fixture(*, boundaries=False, continent=False):
    shape = (80, 80)
    plate = np.zeros(shape, dtype=np.int64)
    velocity = np.array([[1800., 500.]])
    if boundaries:
        plate[:, 30:50] = 1
        plate[:, 50:] = 2
        velocity = np.array([[1000., 0.], [-1000., 0.], [1000., 0.]])
    bed = np.full(shape, -4000.)
    fraction = np.full(shape, .01)
    if continent:
        fraction[:, 40:] = .8
        bed[:, 40:] = 600.
    arrays = dict(elevation_m=bed, continental_fraction=fraction, plate_id=plate,
                  ocean_connected=bed < 0, velocities_m_per_step=velocity)
    return PlateOceanSource(dict(origin_x_m=-800000., origin_z_m=-800000., spacing_m=20000., shape_zx=shape), arrays, "a" * 64, WORLD_SEED)


@pytest.fixture(scope="module")
def ocean():
    return source_fixture()


@pytest.fixture(scope="module")
def product(ocean):
    return prepare_ocean_islands(ocean, OceanIslandConfig(hotspot_count=8, density="high", arcs=False, ridge=False))


def test_prepare_is_deterministic_immutable_and_does_not_change_input(ocean, product):
    before = ocean.elevation_m.tobytes()
    again = prepare_ocean_islands(ocean, product.config)
    assert again.identity == product.identity
    assert again.features == product.features
    assert ocean.elevation_m.tobytes() == before
    assert product.config.world_seed == WORLD_SEED == 20260903
    with pytest.raises(ValueError):
        ocean.elevation_m.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        product.features = ()
    with pytest.raises(FrozenInstanceError):
        product.features[0].stage = 7
    with pytest.raises(TypeError):
        ocean.grid["spacing_m"] = 1
    copy = product.manifest
    copy["features"].clear()
    assert product.manifest["features"]


def test_absolute_slots_age_direction_and_submerged_tail(product):
    groups = defaultdict(list)
    for feature in product.features:
        groups[feature.chain_id].append(feature)
        assert feature.center_x_m == pytest.approx(feature.hotspot_x_m + feature.velocity_x_m_per_step * feature.age_steps)
        assert feature.center_z_m == pytest.approx(feature.hotspot_z_m + feature.velocity_z_m_per_step * feature.age_steps)
    full = [sorted(chain, key=lambda f: f.stage) for chain in groups.values() if len(chain) == product.config.stages]
    assert full
    for chain in full:
        peaks = [feature.peak_elevation_m for feature in chain]
        assert peaks[0] > 1000 and peaks[-1] < -1000
        assert chain[0].support_radius_m > chain[-1].support_radius_m
        assert all(a.age_steps < b.age_steps for a, b in zip(chain, chain[1:]))
        assert product.query(chain[-1].center_x_m, chain[-1].center_z_m)["relief_m"] > 0
    assert any(f.kind == "seamount" for f in product.features)


def test_overlapping_tiles_order_negative_coordinates_spacing_and_no_cache(product):
    axis = np.linspace(-700000, 700000, 81)
    x, z = np.meshgrid(axis, axis)
    whole = product.query(x, z)
    coarse = product.query(x[::4, ::4], z[::4, ::4])
    left = product.query(x[:, :42], z[:, :42])
    right = product.query(x[:, 40:], z[:, 40:])
    rng = np.random.default_rng(57)
    order = rng.permutation(x.size)
    mixed = product.query(x.ravel()[order], z.ravel()[order])
    for key, value in whole.items():
        np.testing.assert_array_equal(value[::4, ::4], coarse[key])
        np.testing.assert_array_equal(left[key][:, 40:], right[key][:, :2])
        np.testing.assert_array_equal(value.ravel()[order], mixed[key])
    # Four-window corner and exact negative cell border.
    for x0, z0 in ((0., 0.), (-160000., -160000.), (-1., -1.)):
        scalar = product.query(x0, z0)
        broadcast = product.query(np.array([[x0], [x0]]), np.array([[z0, z0]]))
        for key in scalar:
            np.testing.assert_array_equal(np.full((2, 2), scalar[key]), broadcast[key])
    assert product.manifest["preparation"]["query_cache_entries"] == 0
    assert not hasattr(product, "__dict__")


def test_continuous_bottom_island_and_slope_not_vertical_pedestal(product):
    feature = next(f for f in product.features if f.stage == 0 and abs(f.center_x_m) < 600000 and abs(f.center_z_m) < 600000)
    r = feature.support_radius_m
    # A cross-section from deep bottom through the sub-grid island.
    x = feature.center_x_m + np.linspace(-r * 1.05, r * 1.05, 3001)
    z = np.full(x.shape, feature.center_z_m)
    fields = product.query(x, z)
    assert fields["elevation_m"].max() > 800
    assert fields["elevation_m"].min() < -3500
    assert np.max(np.abs(np.diff(fields["elevation_m"]) / np.diff(x))) < 1.5
    assert np.any((fields["elevation_m"] < -200) & (fields["relief_m"] > 100))
    assert np.all(fields["protected"][fields["relief_m"] > 0])
    # The feature catalog survives a raster whose cell centres miss the island.
    inventory = product.features
    product.query(feature.center_x_m + r * .4, feature.center_z_m + r * .4)
    assert product.features is inventory
    assert r < 4 * product.source.grid["spacing_m"]
    # Compact support meets the unchanged floor continuously.
    points = feature.center_x_m + np.array([r - .001, r, r + .001])
    line = product.query(points, feature.center_z_m)["elevation_m"]
    assert np.max(np.abs(np.diff(line))) < .01


def test_coast_protection_and_clamp_do_not_wrap():
    source = source_fixture(continent=True)
    xmin, zmin, xmax, zmax = source.bounds_m
    assert source.sample(xmin, zmin)["elevation_m"] == -4000
    assert source.sample(xmax - .001, zmax - .001)["elevation_m"] == 600
    # The old nearest ocean flag flips at x=0, continuous composition does not.
    confidence = source.sample(np.array([-.001, 0., .001]), 0.)["ocean_confidence"]
    assert np.max(np.abs(np.diff(confidence))) < 1e-6
    product = prepare_ocean_islands(source, OceanIslandConfig(density="high", hotspot_count=30, arcs=False, ridge=False))
    x, z = np.meshgrid(np.linspace(0, 700000, 31), np.linspace(-700000, 700000, 31))
    fields = product.query(x, z)
    assert np.all(fields["relief_m"][fields["base_elevation_m"] >= 0] == 0)
    for bad_x, bad_z in ((xmax, 0), (xmin - 1, 0), (0, zmax), (np.nan, 0), (np.inf, 0)):
        with pytest.raises(ValueError):
            product.query(bad_x, bad_z)


def test_ocean_ocean_convergence_upper_side_and_divergent_islands():
    source = source_fixture(boundaries=True)
    product = prepare_ocean_islands(source, OceanIslandConfig(density="high", hotspot_count=0))
    arcs = [f for f in product.features if f.kind == "arc"]
    ridges = [f for f in product.features if f.kind == "ridge"]
    assert len(arcs) >= 5 and len(ridges) >= 5
    for feature in arcs:
        assert feature.boundary_kind == "convergent"
        assert feature.center_x_m == -245000
        assert feature.plate_id == 0
        assert "polarity proxy" in feature.basis
        assert "-2000" in feature.basis
    for feature in ridges:
        assert feature.boundary_kind == "divergent"
        assert feature.center_x_m == 200000
        assert "2000" in feature.basis
    # The whole divergence line is not raised into a land bridge.
    assert sum(f.peak_elevation_m >= 0 for f in ridges) < len(ridges) / 2
    assert any(f.peak_elevation_m < 0 for f in ridges)
    assert len({f.boundary_id for f in product.features}) == len(product.features)
    # Continental convergence is not counted as an ocean island arc.
    arrays = {name: getattr(source, name) for name in ("elevation_m", "continental_fraction", "plate_id", "ocean_connected", "velocities_m_per_step")}
    fraction = np.array(source.continental_fraction)
    fraction[:, :30] = .8
    arrays["continental_fraction"] = fraction
    continental = PlateOceanSource(dict(source.grid), arrays, "b" * 64, WORLD_SEED)
    result = prepare_ocean_islands(continental, product.config)
    assert not any(f.kind == "arc" for f in result.features)


def test_cross_plate_older_tail_stops():
    source = source_fixture(boundaries=True)
    product = prepare_ocean_islands(source, OceanIslandConfig(density="high", hotspot_count=40, arcs=False, ridge=False))
    for feature in product.features:
        t = np.linspace(0, feature.age_steps, 100)
        fields = source.sample(feature.hotspot_x_m + feature.velocity_x_m_per_step * t,
                               feature.hotspot_z_m + feature.velocity_z_m_per_step * t)
        assert np.all(fields["plate_id"] == feature.plate_id)


def test_exact_cell_crossing_detects_tiny_foreign_plate_interval():
    from terrain_pipeline.ocean_islands import _same_plate_segment

    plate = np.zeros((4, 4), dtype=np.int64)
    plate[1, 0] = 1
    arrays = dict(elevation_m=np.full((4, 4), -4000.), plate_id=plate, continental_fraction=np.zeros((4, 4)),
                  ocean_connected=np.ones((4, 4), dtype=bool), velocities_m_per_step=np.array([[1000., 1 / 9000], [0., 0.]]))
    source = PlateOceanSource(dict(origin_x_m=0., origin_z_m=0., spacing_m=10000., shape_zx=(4, 4)), arrays, "a" * 64, WORLD_SEED)
    hx, hz, vx, vz = 1000., 9999.99900001, 1000., 1 / 9000
    # Uniform 4km probes miss the very short foreign-cell diagonal corner.
    time = np.linspace(0, 20, 6)
    assert np.all(source.sample(hx + vx * time, hz + vz * time)["plate_id"] == 0)
    assert not _same_plate_segment(source, hx, hz, vx, vz, 20., 0)


def test_valley_cut_is_not_fourfold_and_does_not_score_submarine_base(product):
    from terrain_pipeline.ocean_islands import _shape

    feature = next(f for f in product.features if f.stage == 0)
    # The real shape seam; a completely submarine field has no subaerial
    # drainage incision. v1 instead cuts its deep-bottom uplift in four rays.
    submarine = replace(feature, peak_elevation_m=-1000.)
    angles = np.arange(720) * 2 * np.pi / 720
    x = feature.center_x_m + .25 * feature.support_radius_m * np.cos(angles)
    z = feature.center_z_m + .25 * feature.support_radius_m * np.sin(angles)
    base = np.full(x.shape, feature.base_elevation_m)
    cut = _shape(submarine, x, z, base, valley_strength=1.)[0] - _shape(submarine, x, z, base, valley_strength=0.)[0]
    np.testing.assert_array_equal(cut, 0.)


def test_valley_network_has_unequal_curved_trunks_and_exact_forks(product):
    from terrain_pipeline.ocean_islands import valley_paths

    feature = next(f for f in product.features if f.stage == 0)
    paths = valley_paths(feature)
    mains = [p for p in paths if p.parent_path_id is None]
    branches = [p for p in paths if p.parent_path_id is not None]
    assert 3 <= len(mains) <= 5 and len(branches) == 2 * len(mains) and len(paths) <= 15
    by_id = {p.path_id: p for p in paths}
    directions = []
    for path in paths:
        points = np.array(path.points_local)
        assert points.shape == (7, 2)
        assert np.all(np.diff(path.half_widths_local) > 0)
        # Every actual polyline bends relative to its endpoint chord.
        chord = points[-1] - points[0]
        perpendicular = np.array([-chord[1], chord[0]])
        deviation = np.max(np.abs((points - points[0]) @ perpendicular)) / np.linalg.norm(chord)
        assert deviation > .002
        if path.parent_path_id is None:
            directions.append(np.arctan2(points[-1, 1], points[-1, 0]))
        else:
            parent = by_id[path.parent_path_id]
            np.testing.assert_array_equal(points[-1], parent.points_local[path.join_parent_node])
            assert np.linalg.norm(points[0]) < np.linalg.norm(points[-1])
    directions = np.sort(np.mod(directions, 2 * np.pi))
    gaps = np.diff(np.r_[directions, directions[0] + 2 * np.pi])
    assert np.ptp(gaps) > .2
    # Not four quarter-turn copies after rotating coordinates.
    assert not (len(gaps) == 4 and np.allclose(gaps, np.pi / 2, atol=.1))


def test_valley_strength_changes_only_incisions_not_layout_network_or_base(ocean, product):
    from dataclasses import asdict
    from terrain_pipeline.ocean_islands import _shape, valley_paths

    off = prepare_ocean_islands(ocean, replace(product.config, valley_strength=0.))
    assert off.identity != product.identity
    assert len(off.features) == len(product.features)
    for a, b in zip(product.features, off.features):
        ar, br = asdict(a), asdict(b)
        ar.pop("parameter_identity")
        br.pop("parameter_identity")
        assert ar == br
        assert valley_paths(a) == valley_paths(b)
    feature = next(f for f in product.features if f.stage == 0)
    axis = np.linspace(-.3, .3, 201) * feature.support_radius_m
    x, z = np.meshgrid(feature.center_x_m + axis, feature.center_z_m + axis)
    base = np.full(x.shape, feature.base_elevation_m)
    uncut = base + _shape(feature, x, z, base, valley_strength=0.)[0]
    cut = base + _shape(feature, x, z, base, valley_strength=1.)[0]
    depth = uncut - cut
    assert depth.max() > 1
    assert np.all(depth >= -1e-10)
    np.testing.assert_array_equal(depth[uncut <= 0], 0.)
    assert np.max(depth) <= min(240., .16 * feature.peak_elevation_m, .004 * feature.support_radius_m) + 1e-8
    # Each branch really meets a terrestrial parent, not just an underwater
    # extension of unrelated radial scratches.
    forks_above_sea = 0
    for path in valley_paths(feature):
        if path.parent_path_id is None:
            continue
        px, pz = path.points_local[-1]
        c, s = np.cos(feature.orientation_rad), np.sin(feature.orientation_rad)
        qx = feature.center_x_m + feature.support_radius_m * (c*px - s*pz)
        qz = feature.center_z_m + feature.support_radius_m * (s*px + c*pz)
        if base.flat[0] + _shape(feature, np.array(qx), np.array(qz), np.array(base.flat[0]), valley_strength=0.)[0] > 0:
            forks_above_sea += 1
    assert forks_above_sea >= 2


def test_v2_incisions_have_no_quarter_turn_template_and_c0_segment_edges(product):
    from terrain_pipeline.ocean_islands import _shape, valley_paths

    feature = next(f for f in product.features if f.stage == 0)
    angle = np.arange(1440) * 2 * np.pi / 1440
    c, s = np.cos(feature.orientation_rad), np.sin(feature.orientation_rad)
    x = feature.center_x_m + .085 * feature.support_radius_m * np.cos(angle)
    z = feature.center_z_m + .085 * feature.support_radius_m * np.sin(angle)
    base = np.full(x.shape, feature.base_elevation_m)
    depth = _shape(feature, x, z, base, valley_strength=0.)[0] - _shape(feature, x, z, base, valley_strength=1.)[0]
    assert depth.max() > .1
    assert np.max(np.abs(depth - np.roll(depth, 360))) > .5
    for path in valley_paths(feature):
        point = np.array(path.points_local[2])
        samples = point + np.array([[-1e-8, 0.], [1e-8, 0.]])
        xx = feature.center_x_m + feature.support_radius_m * (c*samples[:, 0] - s*samples[:, 1])
        zz = feature.center_z_m + feature.support_radius_m * (s*samples[:, 0] + c*samples[:, 1])
        values = _shape(feature, xx, zz, np.full(2, feature.base_elevation_m))[0]
        assert abs(values[1] - values[0]) < .01


def test_query_valleys_respect_final_coastal_height_and_transition(ocean, product):
    from terrain_pipeline.ocean_islands import FrozenOceanIslands, _manifest

    feature = next(f for f in product.features if f.stage == 0 and abs(f.center_x_m) < 500000 and abs(f.center_z_m) < 500000)
    feature = replace(feature, support_radius_m=90000., peak_elevation_m=4000.)
    # Reuse one exact feature on a continuously fading continental field.
    # Its raw volcanic face is exposed, but coastal weighting drowns its fringe.
    arrays = {name: getattr(ocean, name) for name in ("elevation_m", "plate_id", "continental_fraction", "ocean_connected", "velocities_m_per_step")}
    gx = ocean.grid["origin_x_m"] + (np.arange(80) + .5) * ocean.grid["spacing_m"]
    gradient = np.clip(.13 + (gx - feature.center_x_m) / (feature.support_radius_m * .4) * .3, .01, .4)
    arrays["continental_fraction"] = np.broadcast_to(gradient, (80, 80))
    partial = PlateOceanSource(dict(ocean.grid), arrays, "b" * 64, WORLD_SEED)
    products = []
    for strength in (0., 1.):
        config = replace(product.config, valley_strength=strength)
        from terrain_pipeline.ocean_islands import _identity
        f = replace(feature, source_identity=partial.identity, parameter_identity=_identity(asdict(config)))
        products.append(FrozenOceanIslands(partial, config, (f,), _manifest(partial, config, (f,), {})))
    axis = np.linspace(-.23, .23, 401) * feature.support_radius_m
    x, z = np.meshgrid(feature.center_x_m + axis, feature.center_z_m + axis)
    off, on = (p.query(x, z) for p in products)
    delta = off["elevation_m"] - on["elevation_m"]
    assert delta.max() > .1
    assert np.any((off["elevation_m"] <= 0) & (off["relief_m"] > 2000))
    np.testing.assert_array_equal(delta[off["elevation_m"] <= 0], 0.)
    assert np.all(on["elevation_m"][off["elevation_m"] > 0] > 0)
    # Changing continuous coast weight through the drowned shore never creates
    # a binary incision step; the complete height signal remains C0.
    row, column = np.unravel_index(np.argmax(np.abs(np.diff(delta, axis=1))), (401, 400))
    px, pz = x[row, column], z[row, column]
    close_x = px + np.array([-.001, .001])
    near_off, near_on = (p.query(close_x, pz)["elevation_m"] for p in products)
    assert abs(np.diff(near_off - near_on)[0]) < .05


def test_small_and_low_islands_disable_valleys_but_large_fixture_activates(ocean, product):
    from terrain_pipeline.ocean_islands import FrozenOceanIslands, _manifest

    feature = next(f for f in product.features if f.stage == 0)
    source = source_fixture()
    candidates = [replace(feature, feature_id="small-high-island", support_radius_m=40000., peak_elevation_m=1600.),
                  replace(feature, feature_id="wide-low-island", support_radius_m=90000., peak_elevation_m=500.),
                  replace(feature, feature_id="declared-large-volcanic-fixture", support_radius_m=90000., peak_elevation_m=4000.)]
    records = []
    for f in candidates:
        features = (f,)
        prepared = FrozenOceanIslands(source, product.config, features, _manifest(source, product.config, features, {}))
        records.append(prepared)
    small, low, large = records
    assert small.valley_domains[candidates[0].feature_id].equivalent_emerged_diameter_m <= 20000
    assert small.valley_domains[candidates[0].feature_id].activation == 0
    assert low.valley_domains[candidates[1].feature_id].estimated_exposed_relief_m <= 600
    assert low.valley_domains[candidates[1].feature_id].activation == 0
    domain = large.valley_domains[candidates[2].feature_id]
    assert domain.equivalent_emerged_diameter_m > 40000
    assert domain.estimated_exposed_relief_m > 1500
    assert domain.activation == 1
    with pytest.raises(TypeError):
        large.valley_domains[domain.feature_id] = domain
    axis = np.linspace(-.3, .3, 151) * candidates[2].support_radius_m
    x, z = np.meshgrid(candidates[2].center_x_m + axis, candidates[2].center_z_m + axis)
    config = replace(product.config, valley_strength=0.)
    off_feature = replace(candidates[2], parameter_identity=__import__("terrain_pipeline.ocean_islands", fromlist=["_identity"])._identity(asdict(config)))
    off = FrozenOceanIslands(source, config, (off_feature,), _manifest(source, config, (off_feature,), {}))
    assert np.max(off.query(x, z)["elevation_m"] - large.query(x, z)["elevation_m"]) > 1
    assert large.valley_domains[domain.feature_id] == off.valley_domains[domain.feature_id]


def test_user_diagnosed_real_small_island_defaults_to_no_valley_incision():
    root = Path(__file__).resolve().parents[1]
    path = root / ".scratch/ocean-islands-20261106/run-main-2km/islands.npz"
    if not path.exists():
        pytest.skip("saved diagnosed-world fixture absent")
    old = load_product(path)
    on = prepare_ocean_islands(old.source, old.config)
    off = prepare_ocean_islands(old.source, replace(old.config, valley_strength=0.))
    key = "hotspot:20260903:-1:-3:stage:0"
    f = next(f for f in on.features if f.feature_id == key)
    assert on.valley_domains[key].equivalent_emerged_diameter_m <= 20000
    assert on.valley_domains[key].activation == 0
    axis = np.linspace(-.45, .45, 201) * f.support_radius_m
    x, z = np.meshgrid(f.center_x_m + axis, f.center_z_m + axis)
    np.testing.assert_array_equal(on.query(x, z)["elevation_m"], off.query(x, z)["elevation_m"])


def test_v1_read_replays_saved_fields_exactly_and_cannot_publish(tmp_path):
    root = Path(__file__).resolve().parents[1]
    directory = root / ".scratch/ocean-islands-20261106/arc-reference"
    if not (directory / "islands.npz").exists():
        pytest.skip("historical real-source fixture absent")
    from terrain_pipeline.ocean_islands import ALGORITHM, LEGACY_ALGORITHM

    historical = load_product(directory / "islands.npz")
    assert historical.manifest["algorithm"] == LEGACY_ALGORITHM != ALGORITHM
    assert "valley_strength" not in historical.manifest["config"]
    with np.load(directory / "strait_section_01.npz", allow_pickle=False) as saved:
        query = historical.query(saved["x_m"], saved["z_m"])
        for key, value in query.items():
            np.testing.assert_array_equal(value, saved[key])
    # This separate saved new-seed world is also v1: compare an absolute set
    # spanning its finite domain, including negatives, without changing files.
    main = root / ".scratch/ocean-islands-20261106/run-main-2km"
    if (main / "world.npz").exists():
        old_world = load_product(main / "islands.npz")
        with np.load(main / "world.npz", allow_pickle=False) as saved:
            x, z = saved["x_m"][::31], saved["z_m"][::29]
            sampled = old_world.query(x[None, :], z[:, None])
            for key, value in sampled.items():
                np.testing.assert_array_equal(value, saved[key][::29, ::31])
    with pytest.raises(ValueError, match="read-only"):
        save_product(historical, tmp_path / "should-not-publish-v1.npz")
    assert not (tmp_path / "should-not-publish-v1.npz").exists()
    # Version migration retains physical layout and underlying shape randomness.
    upgraded = prepare_ocean_islands(historical.source, historical.config)
    for old, new in zip(historical.features, upgraded.features):
        a, b = asdict(old), asdict(new)
        for key in ("algorithm", "parameter_identity"):
            a.pop(key)
            b.pop(key)
        assert a == b


@pytest.mark.parametrize("strength", [-.1, 2.1, True, float("inf"), float("nan")])
def test_invalid_valley_strength_rejected(strength):
    with pytest.raises(ValueError, match="valley_strength"):
        OceanIslandConfig(valley_strength=strength)


def test_continuous_protection_envelope_and_declared_dependencies(product):
    feature = next(f for f in product.features if f.stage == 0)
    r = feature.support_radius_m
    fields = product.query(feature.center_x_m + np.array([0., .65, .825, 1.]) * r, feature.center_z_m)
    assert fields["protection_weight"][0] == 1
    assert 0 <= fields["protection_weight"][2] <= 1
    # Other supports may overlap: find an isolated outward edge or check each
    # field's protection remains a finite continuous union on a dense section.
    x = feature.center_x_m + np.linspace(-r * 1.05, r * 1.05, 2001)
    line = product.query(x, feature.center_z_m)["protection_weight"]
    assert np.max(np.abs(np.diff(line))) < .02
    dependencies = product.manifest["preparation"]["dependencies"]
    assert dependencies["finite_count_global_dependency"] is True
    assert "entire finite source" in dependencies["hotspot_selection_scope"]
    expected = product.config.max_chain_length_m + r + product.config.min_hotspot_spacing_m
    assert product.manifest["preparation"]["dependency_radius_m"] >= expected
    assert dependencies["boundary_pca_and_thinning_m"] >= product.config.boundary_spacing_m


def test_boundary_budget_rejects_during_face_collection():
    with pytest.raises(ValueError, match="boundary face budget"):
        prepare_ocean_islands(source_fixture(boundaries=True), OceanIslandConfig(hotspot_count=0, max_boundary_segments=1))


def test_explicit_warm_atoll_has_real_ring_and_submerged_protected_lagoon(ocean):
    with pytest.raises(ValueError, match="warm"):
        OceanIslandConfig(atolls=True)
    cold = prepare_ocean_islands(ocean, OceanIslandConfig(hotspot_count=15, density="high", arcs=False, ridge=False))
    assert not any(f.kind == "atoll" for f in cold.features)
    warm = prepare_ocean_islands(ocean, replace(cold.config, atolls=True, warm_water_scenario=True))
    atolls = [f for f in warm.features if f.kind == "atoll"]
    assert atolls
    for feature in atolls[:3]:
        center = warm.query(feature.center_x_m, feature.center_z_m)
        assert center["elevation_m"] < -5
        assert center["lagoon"] and center["protected"]
        # Resolve the narrow irregular annulus without enlarging it to a cell.
        r = feature.support_radius_m
        axis = np.linspace(-.32, .32, 129) * r
        x, z = np.meshgrid(feature.center_x_m + axis, feature.center_z_m + axis)
        fields = warm.query(x, z)
        assert np.any(fields["land"])
        assert np.all(fields["elevation_m"][fields["lagoon"]] < 0)
        assert np.all(fields["protected"][fields["lagoon"]])
        assert np.max(np.abs(np.diff(fields["elevation_m"], axis=0))) < 300


def test_atoll_authority_is_continuous_with_overlapping_volcano(ocean):
    from terrain_pipeline.ocean_islands import FrozenOceanIslands, _manifest

    config = OceanIslandConfig(hotspot_count=15, density="high", atolls=True, warm_water_scenario=True, arcs=False, ridge=False)
    prepared = prepare_ocean_islands(ocean, config)
    atoll = next(f for f in prepared.features if f.kind == "atoll")
    # An independently overlapping taller field would max-fill the lagoon.
    volcano = replace(atoll, feature_id="overlapping-volcano", chain_id="overlapping-volcano", kind="hotspot", peak_elevation_m=4000.,
                      support_radius_m=min(config.max_support_radius_m, atoll.support_radius_m * 1.8))
    features = tuple(sorted((atoll, volcano), key=lambda f: f.feature_id))
    product = FrozenOceanIslands(ocean, config, features, _manifest(ocean, config, features, {}))
    angle = -atoll.orientation_rad
    ring_radius = .235 * (1 + .09 * np.sin(3 * angle + atoll.orientation_rad) + .035 * np.sin(7 * angle))
    # Two millimetres across the former hard cap and both blend endpoints.
    for edge in (ring_radius - .047, .3, .6):
        points = atoll.center_x_m + edge * atoll.support_radius_m + np.array([-.001, .001])
        elevations = product.query(points, atoll.center_z_m)["elevation_m"]
        assert abs(elevations[1] - elevations[0]) < .05
    assert product.query(atoll.center_x_m, atoll.center_z_m)["elevation_m"] == pytest.approx(-35.)


def test_qualified_atoll_platform_stays_absolute_under_partial_coastal_weight(ocean):
    arrays = {name: getattr(ocean, name) for name in ("elevation_m", "plate_id", "continental_fraction", "ocean_connected", "velocities_m_per_step")}
    # Still admits a hotspot (>=.98 suitability), but the old multiplication
    # would subtract ~58m from a rim only 5..11m above sea level.
    arrays["continental_fraction"] = np.full(ocean.elevation_m.shape, .125)
    partial = PlateOceanSource(dict(ocean.grid), arrays, "b" * 64, WORLD_SEED)
    product = prepare_ocean_islands(partial, OceanIslandConfig(density="high", hotspot_count=15, atolls=True, warm_water_scenario=True, arcs=False, ridge=False))
    atoll = next(f for f in product.features if f.kind == "atoll")
    center = product.query(atoll.center_x_m, atoll.center_z_m)
    assert center["elevation_m"] == pytest.approx(-35.)
    assert center["protection_weight"] == 1
    radius = np.linspace(.17, .30, 81) * atoll.support_radius_m
    angle = np.linspace(0, 2 * np.pi, 129)
    x = atoll.center_x_m + radius[:, None] * np.cos(angle)
    z = atoll.center_z_m + radius[:, None] * np.sin(angle)
    assert np.max(product.query(x, z)["elevation_m"]) > 1


@pytest.mark.parametrize("world_type", ["multi-continent", "pangaea", "two-continents", "inland-sea"])
def test_dream_world_types_have_explicit_presets(ocean, world_type):
    assert prepare_ocean_islands(ocean, OceanIslandConfig(world_type=world_type, density="none")).config.world_type == world_type


@pytest.mark.parametrize("changes", [dict(density="bad"), dict(world_seed=True), dict(stages=2), dict(stages=100), dict(max_candidates=0), dict(max_support_radius_m=float("nan")), dict(candidate_cell_m=0), dict(max_features=999999), dict(hotspot_count=-1), dict(max_chain_length_m=1e10), dict(atolls=1)])
def test_bad_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        OceanIslandConfig(**changes)


def test_preparation_query_and_overlap_budgets_reject_before_publish(ocean, product):
    for config in (replace(product.config, max_source_cells=100), replace(product.config, max_candidates=1),
                   replace(product.config, max_features=1), replace(product.config, max_working_bytes=100),
                   replace(product.config, max_speed_m_per_step=1), replace(product.config, max_local_features=1)):
        with pytest.raises(ValueError):
            prepare_ocean_islands(ocean, config)
    limited = prepare_ocean_islands(ocean, OceanIslandConfig(density="none", max_query_points=10))
    with pytest.raises(ValueError, match="budget"):
        limited.query(np.zeros(11), 0)


def test_none_is_exact_control_and_catalog_does_not_depend_on_queries(ocean):
    product = prepare_ocean_islands(ocean, OceanIslandConfig(density="none", hotspot_count=10, atolls=True, warm_water_scenario=True))
    assert product.features == ()
    fields = product.query(np.array([-300000., -1., 0., 400000.]), 0)
    np.testing.assert_array_equal(fields["elevation_m"], fields["base_elevation_m"])
    assert not fields["protected"].any() and not fields["lagoon"].any()


def test_save_cold_read_no_external_dependency_no_overwrite_and_tamper_rejection(product, tmp_path):
    path = tmp_path / "islands.npz"
    returned = save_product(product, path)
    loaded = load_product(path, expected_identity=product.identity)
    assert loaded.identity == returned.identity == product.identity
    assert loaded.features == product.features
    for feature in product.features[:10]:
        before = product.query(feature.center_x_m, feature.center_z_m)
        after = loaded.query(feature.center_x_m, feature.center_z_m)
        for key in before:
            np.testing.assert_array_equal(before[key], after[key])
    with pytest.raises(FileExistsError):
        save_product(product, path)
    with pytest.raises(ValueError):
        load_product(path, expected_identity="b" * 64)
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    arrays["elevation_m"] = arrays["elevation_m"] + 1
    broken = tmp_path / "broken.npz"
    np.savez(broken, **arrays)
    with pytest.raises(ValueError, match="integrity"):
        load_product(broken)
    arrays["elevation_m"] -= 1
    manifest = json.loads(str(arrays["manifest_json"]))
    manifest["features"][0]["peak_elevation_m"] += 10
    arrays["manifest_json"] = np.array(canonical_json(manifest))
    np.savez(broken, **arrays)
    with pytest.raises(ValueError, match="identity"):
        load_product(broken)


def test_skeleton_source_checks_all_hashes_manifest_and_true_seed(tmp_path):
    source = source_fixture()
    arrays = {"final/" + name: getattr(source, name) for name in ("elevation_m", "plate_id", "continental_fraction", "ocean_connected", "velocities_m_per_step")}
    arrays["other/retained_provenance"] = np.arange(3)
    manifest = {"schema": "dream-world-skeleton-plate-v1", "config": {"shape": [80, 80], "cell_size_m": 20000., "origin_x_m": -800000., "origin_z_m": -800000., "world_seed": 20261020},
                "arrays": {key: {"shape": list(value.shape), "dtype": str(value.dtype), "sha256": array_sha256_raw(value)} for key, value in arrays.items()}}
    import hashlib
    manifest["identity"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    path = tmp_path / "source.npz"
    np.savez(path, manifest_json=np.array(canonical_json(manifest)), **arrays)
    checked = PlateOceanSource.from_npz(path, manifest["identity"])
    assert checked.world_seed == 20261020
    with pytest.raises(ValueError):
        PlateOceanSource.from_npz(path, "b" * 64)
    arrays["other/retained_provenance"][0] = 50
    np.savez(path, manifest_json=np.array(canonical_json(manifest)), **arrays)
    with pytest.raises(ValueError, match="SHA"):
        PlateOceanSource.from_npz(path)
    manifest["config"]["world_seed"] = 3
    np.savez(path, manifest_json=np.array(canonical_json(manifest)), **arrays)
    with pytest.raises(ValueError, match="identity"):
        PlateOceanSource.from_npz(path)


def test_cold_read_rejects_relabelled_embedded_source_seed(tmp_path):
    import hashlib

    source = source_fixture()
    arrays = {"final/" + name: getattr(source, name) for name in ("elevation_m", "plate_id", "continental_fraction", "ocean_connected", "velocities_m_per_step")}
    original = {"schema": "dream-world-skeleton-plate-v1", "config": {"shape": [80, 80], "cell_size_m": 20000., "origin_x_m": -800000., "origin_z_m": -800000., "world_seed": WORLD_SEED},
                "arrays": {key: {"shape": list(value.shape), "dtype": str(value.dtype), "sha256": array_sha256_raw(value)} for key, value in arrays.items()}}
    original["identity"] = hashlib.sha256(canonical_json(original).encode()).hexdigest()
    upstream = tmp_path / "upstream.npz"
    np.savez(upstream, manifest_json=np.array(canonical_json(original)), **arrays)
    checked = PlateOceanSource.from_npz(upstream)
    product = prepare_ocean_islands(checked, OceanIslandConfig(density="none"))
    frozen = tmp_path / "frozen.npz"
    save_product(product, frozen)
    with np.load(frozen, allow_pickle=False) as archive:
        payload = {key: archive[key] for key in archive.files}
    manifest = json.loads(str(payload["manifest_json"]))
    manifest["source"]["world_seed"] = 20261020
    del manifest["identity"]
    manifest["identity"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    payload["manifest_json"] = np.array(canonical_json(manifest))
    broken = tmp_path / "relabelled.npz"
    np.savez(broken, **payload)
    with pytest.raises(ValueError, match="seed/grid"):
        load_product(broken)


@pytest.mark.parametrize("relative,seed", [
    (".scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz", 20261020),
    ("../织梦/artifacts/worlds/world1600-archipelago-v4/skeleton.npz", 20260903),
])
def test_real_plate_source_prepares_visible_islands_and_cold_reads(relative, seed, tmp_path):
    path = Path(__file__).resolve().parents[1] / relative
    if not path.exists():
        pytest.skip("optional saved real-source fixture absent")
    source = PlateOceanSource.from_npz(path)
    assert source.world_seed == seed
    product = prepare_ocean_islands(source, OceanIslandConfig(density="high", hotspot_count=30, atolls=True, warm_water_scenario=True))
    counts = Counter(f.kind for f in product.features)
    assert counts["hotspot"] > 0 and counts["ridge"] > 0
    centers = [(f.center_x_m, f.center_z_m) for f in product.features if f.peak_elevation_m > 100]
    fields = product.query(*np.array(centers).T)
    assert np.any(fields["elevation_m"] > 100)
    atolls = [f for f in product.features if f.kind == "atoll"]
    assert atolls
    emerged_reefs = 0
    for atoll in atolls:
        angles = np.linspace(0, 2 * np.pi, 65)
        radius = np.linspace(.17, .30, 33) * atoll.support_radius_m
        x = atoll.center_x_m + radius[:, None] * np.cos(angles)
        z = atoll.center_z_m + radius[:, None] * np.sin(angles)
        # All real fixtures' reefs lie within the domain; this is local polar
        # rim sampling, not a new full-domain raster or a synthetic replacement.
        xmin, zmin, xmax, zmax = source.bounds_m
        valid = (x >= xmin) & (x < xmax) & (z >= zmin) & (z < zmax)
        if np.any(product.query(x[valid], z[valid])["land"]):
            emerged_reefs += 1
        assert product.query(atoll.center_x_m, atoll.center_z_m)["lagoon"]
    assert emerged_reefs > 0
    frozen = tmp_path / "real.npz"
    save_product(product, frozen)
    loaded = load_product(frozen)
    assert loaded.source.identity == source.identity and loaded.source.world_seed == seed
    assert loaded.identity == product.identity


def test_metric_detail_noise_is_bounded_absolute_seeded_and_continuous():
    from terrain_pipeline.ocean_islands import _metric_noise

    x = np.linspace(-14533., 17512., 17003)
    z = x * -.713 + 19.
    value = _metric_noise(x, z, 80., WORLD_SEED, "surface")
    assert np.max(np.abs(value)) <= 1
    np.testing.assert_array_equal(value, np.concatenate([
        _metric_noise(x[:731], z[:731], 80., WORLD_SEED, "surface"),
        _metric_noise(x[731:], z[731:], 80., WORLD_SEED, "surface")]))
    np.testing.assert_array_equal(value[::-1], _metric_noise(x[::-1], z[::-1], 80., WORLD_SEED, "surface"))
    assert not np.array_equal(value, _metric_noise(x, z, 80., WORLD_SEED+1, "surface"))
    assert not np.array_equal(value, _metric_noise(x, z, 80., WORLD_SEED, "contour"))
    for boundary in (-160., -80., 0., 80.):
        near = _metric_noise(boundary + np.array([-.01, 0., .01]), np.full(3, 39.), 80., WORLD_SEED, "surface")
        assert np.max(np.abs(np.diff(near))) < 1e-9


@pytest.mark.parametrize("count", [2, 3, 7, 64])
def test_global_simplex_join_handles_multiway_ties_without_pairwise_accumulation(count):
    from terrain_pipeline.ocean_islands import _smooth_seabed_envelope

    heights = np.full((count, 5), 2000.)
    joined = _smooth_seabed_envelope(heights, np.full(5, -20000.), 320.)
    np.testing.assert_allclose(joined, 2000.+160.*(1-1/count), rtol=0, atol=1e-11)
    np.testing.assert_array_equal(joined, _smooth_seabed_envelope(heights[::-1], np.full(5, -20000.), 320.))
    np.testing.assert_array_equal(_smooth_seabed_envelope(heights, np.full(5, -20000.), 320., np.ones(5)), 2000.)


def test_global_simplex_join_is_bounded_never_creates_land_and_fades_continuously():
    from terrain_pipeline.ocean_islands import _smooth_seabed_envelope

    rng = np.random.default_rng(WORLD_SEED)
    heights = rng.uniform(0., 12000., (64, 4001))
    maximum = heights.max(axis=0)
    base = -maximum - np.geomspace(.0001, 2000., len(maximum))
    for softness in (0., 80., 160., 320.):
        result = _smooth_seabed_envelope(heights, base, softness)
        assert np.all(result >= maximum - 1e-10)
        assert np.all(result <= maximum + softness/2 + 1e-10)
        assert np.all(base + result < 0)
        np.testing.assert_array_equal(result[base+maximum >= -30.], maximum[base+maximum >= -30.])
    with pytest.raises(ValueError, match="320"):
        OceanIslandConfig(seabed_join_softness_m=640.)
    isolated = np.zeros((64, 5)); isolated[17] = np.arange(5)*1000.
    np.testing.assert_array_equal(_smooth_seabed_envelope(isolated, np.full(5, -20000.), 320.), isolated[17])
    # Three-way active-set crossing has a continuous derivative as the finite
    # difference width shrinks, including exact equality of all contributors.
    jumps = []
    for step in (1., .1, .01):
        offset = np.array([-step, 0., step])
        h = np.array([4000.+offset, 4000.-offset, np.full(3, 4000.)])
        values = _smooth_seabed_envelope(h, np.full(3, -8000.), 320.)
        jumps.append(abs(values[2]-2*values[1]+values[0])/step)
    assert jumps[-1] < jumps[0]*.011
    # Both smooth depth-gate knots must approach zero correction slope.
    h = np.full((3, 3), 1000.)
    upper_uplift = 1000.*3**(1/16)
    for knot in (-30., -230.):
        offset = np.array([-.001, 0., .001])
        values = _smooth_seabed_envelope(h, knot-upper_uplift+offset, 320.)
        assert abs(values[2]-2*values[1]+values[0])/.001 < 1e-4


def test_dynamic_query_batches_budget_scattered_catalog_rows_and_replay(product, monkeypatch):
    import terrain_pipeline.ocean_islands as oi

    batch = oi._query_batch_size(50000, 10000, 10000000, 268435456)
    assert batch < 200
    assert 10000000 + 224*50000 + batch*(512+192*10000) <= 268435456
    with pytest.raises(ValueError, match="combined"):
        oi._query_batch_size(1000, 10000, 10000, 240000)
    count = 17011
    fixed = 4*sum(getattr(product.source, key).nbytes for key in oi.SOURCE_FIELDS) + oi._valley_storage_bound(product.features)
    per_point = 512+192*len(product.features)
    config = replace(product.config, max_working_bytes=fixed+224*count+per_point*37)
    limited = prepare_ocean_islands(product.source, config)
    rng = np.random.default_rng(WORLD_SEED)
    x, z = rng.uniform(-799999., 799999., (2, count))
    expected = product.query(x, z)
    sizes = []
    direct = oi.FrozenOceanIslands._query_direct
    def measured(self, xx, zz):
        sizes.append(xx.size)
        return direct(self, xx, zz)
    monkeypatch.setattr(oi.FrozenOceanIslands, "_query_direct", measured)
    actual = limited.query(x, z)
    assert max(sizes) <= 37 and len(sizes) > 1
    for key in actual:
        np.testing.assert_array_equal(actual[key], expected[key])


def test_v3_controls_preserve_feature_layout_and_reef_interior(product):
    from terrain_pipeline.ocean_islands import _shape

    controls = [prepare_ocean_islands(product.source, replace(product.config, detail_strength=0.)),
                prepare_ocean_islands(product.source, replace(product.config, seabed_join_softness_m=0.))]
    for control in controls:
        for original, changed in zip(product.features, control.features, strict=True):
            before, after = asdict(original), asdict(changed)
            before.pop("parameter_identity"); after.pop("parameter_identity")
            assert before == after
    reef_product = prepare_ocean_islands(product.source, replace(product.config, atolls=True, warm_water_scenario=True))
    reef = next(f for f in reef_product.features if f.kind == "atoll")
    axis = np.linspace(-.3, .3, 37)*reef.support_radius_m
    x, z = np.meshgrid(reef.center_x_m+axis, reef.center_z_m+axis)
    base = reef_product.source.sample(x, z)["elevation_m"]
    np.testing.assert_array_equal(_shape(reef,x,z,base,detail_strength=0.)[0], _shape(reef,x,z,base,detail_strength=2.)[0])
    off = prepare_ocean_islands(product.source, replace(reef_product.config, detail_strength=0., seabed_join_softness_m=0.))
    for key in ("elevation_m", "lagoon"):
        np.testing.assert_array_equal(reef_product.query(x,z)[key], off.query(x,z)[key])


def test_v2_read_replays_frozen_original_implementation_and_cannot_publish(tmp_path):
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[1]
    directory = root/".scratch/ocean-islands-20261106"
    path = directory/"run-curved-v2-2km/islands.npz"
    original_source = directory/"legacy-v2-source/ocean_islands.py"
    if not path.exists() or not original_source.exists():
        pytest.skip("historical v2 source/product absent")
    name = "terrain_pipeline._frozen_ocean_islands_v2_test"
    spec = importlib.util.spec_from_file_location(name, original_source)
    original = importlib.util.module_from_spec(spec)
    sys.modules[name] = original
    try:
        spec.loader.exec_module(original)
        before, replay = original.load_product(path), load_product(path)
        assert before.manifest == replay.manifest
        rng = np.random.default_rng(WORLD_SEED)
        x,z = rng.uniform(-799999., 799999., (2, 5001))
        for key,value in before.query(x,z).items():
            np.testing.assert_array_equal(replay.query(x,z)[key], value)
        with pytest.raises(ValueError, match="read-only"):
            save_product(replay, tmp_path/"must-not-exist.npz")
        assert not (tmp_path/"must-not-exist.npz").exists()
    finally:
        del sys.modules[name]
