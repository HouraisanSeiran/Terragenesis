import numpy as np
import pytest

from terrain_pipeline.surface_rivers.metric_stylized_wetland import (
    apply_designed_section,
    connected_design_water,
    generate_stylized_wetland,
)


def test_apply_designed_section_non_square():
    rows, cols = 7, 11
    spacing = 20.0
    origin_xz = np.array([100.0, 200.0])

    path_xz = np.array([[100.0, 260.0], [120.0, 260.0], [140.0, 260.0],
                        [160.0, 260.0], [180.0, 260.0], [200.0, 260.0],
                        [220.0, 260.0], [240.0, 260.0], [260.0, 260.0],
                        [280.0, 260.0], [300.0, 260.0]])
    profile_bed = np.linspace(-2.0, -4.0, len(path_xz))
    profile_stage = np.zeros_like(profile_bed)

    bed_m = np.full((rows, cols), 10.0)

    res = apply_designed_section(
        bed_m,
        origin_xz,
        spacing,
        path_xz,
        profile_bed,
        profile_stage,
        100.0,
        allow_fill=True,
    )

    out_bed = res["bed_m"]
    assert out_bed.shape == (rows, cols)

    np.testing.assert_allclose(out_bed[3, :], profile_bed)
    np.testing.assert_allclose(out_bed[0, :], 10.0)


def test_connected_design_water_basic():
    rows, cols = 7, 9
    bed = np.full((rows, cols), 2.0)
    bed[3, :] = -1.0
    bed[1, 4] = -2.0

    stage = np.zeros_like(bed)
    channel_mask = np.zeros_like(bed, dtype=bool)
    source_cell = (3, 4)

    res = connected_design_water(
        bed,
        stage,
        channel_mask,
        source_cell,
    )

    depth = res["water_depth_m"]
    water_surface = res["water_surface_m"]
    wet_mask = res["wet_mask"]

    assert np.all(wet_mask[3, :])
    np.testing.assert_allclose(depth[3, :], 1.0)

    assert not wet_mask[1, 4]
    assert depth[1, 4] == 0.0

    dry_cells = ~wet_mask
    np.testing.assert_allclose(water_surface[dry_cells], bed[dry_cells])

    wet_cells = wet_mask
    np.testing.assert_allclose(
        water_surface[wet_cells] - bed[wet_cells],
        depth[wet_cells],
        atol=1e-10,
    )


def test_generate_stylized_wetland_deterministic_and_consistent():
    rows, cols = 320, 320
    spacing = 20.0
    origin = np.array([-2500.0, -2500.0])
    mouth = np.array([0.0, 0.0])

    xgrid, zgrid = np.meshgrid(origin[0] + np.arange(cols) * spacing,
                               origin[1] + np.arange(rows) * spacing)
    u = (xgrid + zgrid) / np.sqrt(2.0)
    base = 2.0 - 0.002 * u

    e = np.array([1.0, 1.0]) / np.sqrt(2.0)
    u_in = np.arange(-2000.0, 0.0 + 1e-9, 5.0)
    path_xz = np.outer(u_in, e)
    incoming_bed = np.linspace(4.0, -5.8, len(u_in))

    seed = 84708600
    incoming_q_m3_s = np.array([31.0, 62.0, 110.0])

    res1 = generate_stylized_wetland(
        base,
        origin,
        spacing,
        path_xz,
        incoming_bed,
        mouth,
        incoming_q_m3_s,
        seed=seed,
    )

    res2 = generate_stylized_wetland(
        base,
        origin,
        spacing,
        path_xz,
        incoming_bed,
        mouth,
        incoming_q_m3_s,
        seed=seed,
    )

    arr1 = res1["arrays"]
    arr2 = res2["arrays"]

    np.testing.assert_array_equal(arr1["bed_m"], arr2["bed_m"])
    np.testing.assert_array_equal(arr1["water_depth_m"], arr2["water_depth_m"])

    assert np.all(np.isfinite(arr1["bed_m"]))
    assert np.all(np.isfinite(arr1["water_depth_m"]))

    wet = arr1["wet_mask"]
    dry = ~wet
    depth = arr1["water_depth_m"]
    water_surface = arr1["water_surface_m"]
    bed = arr1["bed_m"]

    assert np.all(depth[wet] > 0.0)
    assert np.all(depth[dry] == 0.0)
    np.testing.assert_allclose(
        water_surface[wet] - bed[wet],
        depth[wet],
        atol=1e-8,
    )

    branch_q = arr1["branch_q_m3_s"]
    assert branch_q.shape == (3, 3)
    np.testing.assert_allclose(branch_q.sum(axis=1), incoming_q_m3_s)

    audit = res1["audit"]
    assert all(v >= 20 for v in audit["branch_cut_wet_cell_counts"])
    assert len(audit["branch_transects"]) == 2

    cell_area = spacing * spacing
    delta = bed - base
    expected_cut = float(np.sum(np.maximum(-delta, 0.0)) * cell_area)
    expected_fill = float(np.sum(np.maximum(delta, 0.0)) * cell_area)
    expected_net = float(np.sum(delta) * cell_area)

    np.testing.assert_allclose(audit["cut_bulk_m3"], expected_cut, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(audit["fill_bulk_m3"], expected_fill, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(audit["net_bulk_m3"], expected_net, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(
        audit["material_account_residual_m3"],
        expected_fill - expected_cut - expected_net,
        rtol=1e-6,
        atol=1e-6,
    )


def test_landward_plain_changes_original_land_preserves_upstream_and_closes_construction_budget():
    rows, cols, spacing = 560, 560, 20.
    origin, mouth = np.array([-5000., -5000.]), np.array([0., 0.])
    x, z = np.meshgrid(origin[0]+np.arange(cols)*spacing, origin[1]+np.arange(rows)*spacing)
    u = (x+z)/np.sqrt(2.)
    base = -.012*u
    profile_u = np.arange(-5000., .1, 5.)
    path = profile_u[:, None]*np.array([1., 1.])/np.sqrt(2.)
    old_bed = -2.-.05*profile_u
    q = np.array([30., 60., 100.])
    first = generate_stylized_wetland(base, origin, spacing, path, old_bed, mouth, q, landward_plain=True)
    second = generate_stylized_wetland(base, origin, spacing, path, old_bed, mouth, q, landward_plain=True)
    a = first["arrays"]
    np.testing.assert_array_equal(a["bed_m"], second["arrays"]["bed_m"])
    np.testing.assert_array_equal(a["old_incoming_bed_m"], old_bed)
    keep = profile_u <= -4500.
    np.testing.assert_array_equal(a["designed_incoming_bed_m"][:np.count_nonzero(keep)], old_bed[keep])
    assert np.all(np.diff(a["designed_incoming_bed_m"]) <= 1e-10)
    np.testing.assert_array_equal(a["bed_m"][~a["construction_footprint_mask"]], base[~a["construction_footprint_mask"]])
    old_section = apply_designed_section(base, origin, spacing, path, old_bed, np.maximum(old_bed+3., 0.), 100., allow_fill=True)
    retained_pixels = a["retained_upstream_raster_mask"]
    np.testing.assert_array_equal(a["bed_m"][retained_pixels], old_section["bed_m"][retained_pixels])
    assert retained_pixels.any()
    assert max(first["audit"]["main_wet_depth_max_by_reach_m"].values()) <= 3.1
    assert first["audit"]["bank_support_gross_fill_before_channel_cut_m3"] > 0.
    audit = first["audit"]
    assert audit["original_land_off_old_strip_changed_area_m2"] > 3e5
    assert audit["original_land_off_old_strip_wet_area_m2"] > 1e4
    assert audit["original_land_off_old_strip_dry_area_m2"] > 2e5
    assert [t["u_m"] for t in audit["branch_transects"]] == [-700., 800., 2000.]
    assert all(count > 0 for count in audit['branch_transects'][0]['original_land_wet_counts'])
    np.testing.assert_array_equal(a['trunk_path_xz_m'][0], a['designed_incoming_path_xz_m'][-1])
    assert np.all(a['channel_mask'][a['trunk_section_mask']])
    trunk_cells = np.rint((a['trunk_path_xz_m']-origin)/spacing).astype(int)
    assert np.all(a['wet_mask'][trunk_cells[:, 1], trunk_cells[:, 0]])
    assert np.all(a['water_depth_m'][trunk_cells[:, 1], trunk_cells[:, 0]] > .1)
    for i, station in enumerate(a['branch_junction_station_m']):
        parent = np.array([np.interp(station, a['trunk_station_m'], a['trunk_path_xz_m'][:, axis]) for axis in range(2)])
        np.testing.assert_allclose(a['branch_paths_xz_m'][i, 0], parent, atol=1e-7)
        for field in ('bed', 'stage'):
            parent_profile = a['trunk_profile_'+field+'_m']
            child_profile = a['branch_profile_'+field+'_m'][i]
            np.testing.assert_allclose(child_profile[0], np.interp(station, a['trunk_station_m'], parent_profile), atol=1e-7)
        cell = np.rint((parent-origin)/spacing).astype(int)
        assert base[cell[1], cell[0]] > 0.
    np.testing.assert_allclose(a['trunk_profile_bed_m'][0], a['designed_incoming_bed_m'][-1])
    np.testing.assert_allclose(a['trunk_profile_stage_m'][0], a['designed_incoming_stage_m'][-1])
    assert a["branch_paths_xz_m"].shape[0] == 3
    assert len(set(np.round(a["branch_width_m"], 6))) == 3
    path_lengths = np.linalg.norm(np.diff(a["branch_paths_xz_m"], axis=1), axis=2).sum(axis=1)
    assert len(set(np.round(path_lengths, 3))) == 3
    np.testing.assert_allclose(a["branch_q_m3_s"].sum(axis=1), q)
    np.testing.assert_allclose(a['trunk_reach_q_m3_s'][:, 0], q)
    np.testing.assert_allclose(a['trunk_reach_q_m3_s'][:, 0], a['branch_q_m3_s'][:, 0]+a['trunk_reach_q_m3_s'][:, 1])
    np.testing.assert_allclose(a['trunk_reach_q_m3_s'][:, 1], a['branch_q_m3_s'][:, 1:].sum(axis=1))
    assert max(audit['branch_terminal_open_sea_distance_m']) <= 100.
    np.testing.assert_allclose(a["water_surface_m"][a["wet_mask"]]-a["bed_m"][a["wet_mask"]], a["water_depth_m"][a["wet_mask"]])
    assert abs(audit["material_account_residual_m3"]) < 1e-5
    delta = a["bed_m"]-base
    np.testing.assert_allclose(audit["cut_bulk_m3"], np.maximum(-delta, 0.).sum()*spacing**2)
    land = base>0.
    np.testing.assert_allclose(audit["original_land_construction"]["fill_bulk_m3"], np.maximum(delta[land], 0.).sum()*spacing**2)


def test_radial_fan_widens_and_rotates_with_actual_incoming_direction():
    from terrain_pipeline.surface_rivers.metric_stylized_wetland import _river_fan_fields
    u, v = np.meshgrid(np.arange(-2500., 4500., 20.), np.arange(-4500., 4500., 20.))
    path_distance = np.arange(-6000., 1., 5.)
    path = np.column_stack((path_distance, np.zeros_like(path_distance)))
    base = -.01*u
    first = _river_fan_fields(base, u, v, path, np.zeros(2), seed=41)
    widths = []
    for station in (-1300., -300., 1000.):
        mask = (np.abs(u-station) < 11.) & (first['weight'] > .5)
        widths.append(float(np.ptp(v[mask])))
    assert widths[0] < widths[1] < widths[2]
    assert widths[2] > widths[0]*4.
    np.testing.assert_allclose(first['direction_xz'], [1., 0.], atol=1e-12)
    rotation = np.deg2rad(23.)
    c, s = np.cos(rotation), np.sin(rotation)
    matrix = np.array([[c, -s], [s, c]])
    rotated_path = path @ matrix.T
    rotated = _river_fan_fields(base, c*u-s*v, s*u+c*v, rotated_path, np.zeros(2), seed=41)
    np.testing.assert_allclose(rotated['direction_xz'], [c, s], atol=1e-12)
    np.testing.assert_allclose(rotated['weight'], first['weight'], atol=1e-12)
    np.testing.assert_allclose(rotated['target_bed_m'], first['target_bed_m'], atol=1e-12)
    np.testing.assert_allclose(rotated['bed_m'], first['bed_m'], atol=1e-11)


def test_fan_returns_to_reentered_far_coastal_headland_without_excavating_pocket():
    from terrain_pipeline.surface_rivers.metric_stylized_wetland import _river_fan_fields

    u, v = np.meshgrid(np.arange(-2500., 6500., 20.), np.arange(-4500., 4500., 20.))
    distance = np.arange(-6000., 1., 5.)
    path = np.column_stack((distance, np.zeros_like(distance)))
    # Original river land, open sea, then the elevated neighboring headland.
    base = np.where(u > 4000., .04*(u-4000.), -.01*u)
    result = _river_fan_fields(base, u, v, path, np.zeros(2), seed=84708600)
    shoulder = (u >= 4600.) & (u <= 5500.) & (np.abs(v-1800.) <= 200.)
    assert np.all(result['bed_m'][shoulder] > 0.)
    highland = shoulder & (base >= 36.)
    assert highland.any()
    np.testing.assert_array_equal(result['bed_m'][highland], base[highland])
    assert np.any(result['weight'][(u < 0.) & (base > 0.)] > .5)
