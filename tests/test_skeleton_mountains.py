from dataclasses import replace
import importlib
import math

import numpy as np
import pytest

from terrain_pipeline import mountain_forms as advanced
from terrain_pipeline.skeleton_mountains import (
    HALO_M, MAX_COORDINATE_M, SkeletonMountainConfig, describe_skeleton,
    sample_skeleton_mountains,
)


def test_same_world_points_across_batches_order_tiles_and_resolution():
    config = SkeletonMountainConfig(batch_size=11)
    # Include cell borders and far/negative coordinates, without translating the
    # noise phase back to the origin.
    x = np.array([-500000000., -24000.001, -24000., -1., 0., 9000., 24000., 500000000.])
    z = np.array([500000000., 12000., -1., -24000., 0., 13000., 12000., -500000000.])
    whole = sample_skeleton_mountains(x, z, config)
    perm = np.array([4, 7, 1, 0, 6, 3, 5, 2])
    reordered = sample_skeleton_mountains(x[perm], z[perm], replace(config, batch_size=2))
    for key in whole:
        np.testing.assert_array_equal(whole[key][perm], reordered[key])
    for i in range(len(x)):
        single = sample_skeleton_mountains(x[i], z[i], config)
        for key in whole:
            np.testing.assert_array_equal(single[key], whole[key][i])
    a = np.arange(-4, 5) * 3000.
    xx, zz = np.meshgrid(a, a)
    fine = sample_skeleton_mountains(xx, zz, config)
    coarse = sample_skeleton_mountains(xx[::2, ::2], zz[::2, ::2], config)
    left = sample_skeleton_mountains(xx[:, :5], zz[:, :5], config)
    right = sample_skeleton_mountains(xx[:, 4:], zz[:, 4:], config)
    for key in fine:
        np.testing.assert_array_equal(fine[key][::2, ::2], coarse[key])
        np.testing.assert_array_equal(left[key][:, -1], right[key][:, 0])
        np.testing.assert_array_equal(fine[key], np.concatenate((left[key], right[key][:, 1:]), axis=1))


def test_profiles_share_curves_but_change_sections_and_keep_peak():
    results = []
    reference = describe_skeleton(0, 0)
    for profile in ("granite", "alpine", "asymmetric"):
        config = SkeletonMountainConfig(profile=profile, detail_amplitude_m=0, advanced_enabled=False)
        source = describe_skeleton(0, 0, config)
        assert source["curves"] == reference["curves"]
        assert source["peak_x_m"] == reference["peak_x_m"]
        assert source["peak_uplift_m"] == reference["peak_uplift_m"]
        px, pz = source["peak_x_m"], source["peak_z_m"]
        x, z = np.meshgrid(px + np.arange(-6, 7) * 400, pz + np.arange(-6, 7) * 400)
        f = sample_skeleton_mountains(x, z, config)
        np.testing.assert_array_equal(f["height_m"], f["skeleton_height_m"])
        assert np.all(f["detail_delta_m"] == 0)
        assert np.all(f["final_delta_m"] == 0)
        assert abs(f["height_m"][6, 6] - (f["base_height_m"][6, 6] + source["peak_uplift_m"])) < 1.
        results.append(f["height_m"])
    assert np.max(np.abs(results[0] - results[1])) > 500
    assert np.max(np.abs(results[0] - results[2])) > 200
    alternate = describe_skeleton(0, 0, SkeletonMountainConfig(world_seed=20260904))
    assert alternate["curves"] != reference["curves"]


def test_secondary_ridges_share_parent_nodes():
    source = describe_skeleton(-1, 0)
    assert len(source["curves"]) == 6
    by_id = {curve["id"]: curve for curve in source["curves"]}
    for child in source["curves"]:
        if child["level"] == 1:
            assert child["start_x_m"] == source["peak_x_m"]
            continue
        parent = by_id[child["parent_id"]]
        t = child["attach_t"]
        u, v = parent["length_m"] * t, parent["bend_m"] * math.sin(math.pi * t) ** 2
        co, si = math.cos(parent["angle_rad"]), math.sin(parent["angle_rad"])
        np.testing.assert_allclose([child["start_x_m"], child["start_z_m"]],
                                   [parent["start_x_m"] + co*u - si*v, parent["start_z_m"] + si*u + co*v], atol=1e-9, rtol=0)


def test_advanced_uses_macro_and_negative_gain_only():
    x, z = np.meshgrid(np.arange(9)*1500 + 5000., np.arange(9)*1500 + 5000.)
    config = SkeletonMountainConfig()
    f = sample_skeleton_mountains(x, z, config)
    control = sample_skeleton_mountains(x, z, replace(config, depth_gain=1))
    raw = advanced.filter_height(x, z, f["macro_height_m"], f["slope_x"], f["slope_z"], f["fade_target"],
                                 world_seed=config.world_seed, config=advanced.AdvancedFilterConfig(amplitude_m=150., wavelength_m=1800., octaves=3))
    np.testing.assert_array_equal(f["raw_advanced_delta_m"], raw["delta_m"])
    np.testing.assert_array_equal(f["height_m"], f["macro_height_m"] + f["final_delta_m"])
    negative = f["raw_advanced_delta_m"] < 0
    assert negative.any() and (~negative).any()
    np.testing.assert_allclose(f["final_delta_m"][negative], control["final_delta_m"][negative] * 2.4, atol=1e-12)
    np.testing.assert_array_equal(f["final_delta_m"][~negative], control["final_delta_m"][~negative])
    flat = f["skeleton_height_m"] == f["base_height_m"]
    assert np.all(f["final_delta_m"][flat] == 0)


@pytest.mark.parametrize("profile", ["granite", "alpine", "asymmetric", "mixed"])
def test_macro_small_step_cell_boundaries_and_curve_junctions(profile):
    config = SkeletonMountainConfig(profile=profile, advanced_enabled=False, detail_amplitude_m=0)
    source = describe_skeleton(0, 0, config)
    positions = [(24000., 12000.), (-24000., -13000.), (source["peak_x_m"], source["peak_z_m"])]
    positions += [(q["start_x_m"], q["start_z_m"]) for q in source["curves"] if q["level"] == 2]
    positions += [(q["start_x_m"] + math.cos(q["angle_rad"])*q["length_m"],
                   q["start_z_m"] + math.sin(q["angle_rad"])*q["length_m"]) for q in source["curves"]]
    positions += [(source["peak_x_m"] + source["support_radius_m"], source["peak_z_m"])]
    for x, z in positions:
        errors = []
        for step in (1., .1, .01):
            f = sample_skeleton_mountains([x-step, x+step], z, config)["height_m"]
            errors.append(abs(f[1]-f[0]))
        assert errors[-1] < .5  # At most 25 m/m across this test's junctions.
        assert errors[-1] <= errors[0] * .025 + 1e-8


def test_source_support_bound_covers_unmasked_ribbons():
    # Check the geometry before the production circular culling; this catches
    # a future width/length change that would otherwise introduce a hard seam.
    module = importlib.import_module("terrain_pipeline.skeleton_mountains")
    angle = np.linspace(0, 2*np.pi, 257)
    for profile in ("granite", "alpine", "asymmetric"):
        config = SkeletonMountainConfig(profile=profile)
        for cell in ((0, 0), (-1, -1), (20833, -20834)):
            source = describe_skeleton(*cell, config)
            radius = source["support_radius_m"]
            x = source["peak_x_m"] + radius*np.cos(angle)
            z = source["peak_z_m"] + radius*np.sin(angle)
            raw = module._source_uplift(x, z, source, config.cell_size_m)
            np.testing.assert_array_equal(raw, np.zeros_like(raw))


@pytest.mark.parametrize("kwargs", [{"profile": "missing"}, {"cell_size_m": 0}, {"cell_size_m": True},
    {"depth_gain": float("nan")}, {"detail_amplitude_m": -1}, {"batch_size": True},
    {"world_seed": -1}, {"advanced_enabled": 1}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        SkeletonMountainConfig(**kwargs)


def test_invalid_coordinates_and_halo():
    for x in ([], [float("nan")], [float("inf")], [MAX_COORDINATE_M - HALO_M + .1]):
        with pytest.raises(ValueError):
            sample_skeleton_mountains(x, 0)
    with pytest.raises(ValueError):
        sample_skeleton_mountains([1, 2], [1, 2, 3])
    for sign in (-1, 1):
        f = sample_skeleton_mountains(sign*(MAX_COORDINATE_M-HALO_M), 0)
        assert all(np.isfinite(value).all() for value in f.values())
