"""First-coast termination and frozen marine boundary behavior."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from terrain_pipeline.surface_rivers.metric_coast_bounded_delta import (
    carve_section, coastal_lowland_relief, connected_water, construct_coast_bounded_scene, delayed_distributary_geometry, open_marine_mask, secondary_from_parent_land_prefix, truncate_at_first_marine,
)
from tools.run_integrated_delta import load_scene, protect_scene_geometry


def test_multiscale_relief_is_deterministic_and_leaves_upstream_and_high_ground_exact():
    v, u = np.meshgrid(np.linspace(-4000., 4000., 161), np.linspace(-4500., 7000., 231), indexing="ij")
    bed = np.full_like(u, .7)
    bed[:, -5:] = 12.
    fan = {"u_m": u-1800., "v_m": v, "weight": np.ones_like(u), "parameters": {"apex_u_m": -1800.}}
    first = coastal_lowland_relief(bed, fan)
    np.testing.assert_array_equal(first, coastal_lowland_relief(bed, fan))
    np.testing.assert_array_equal(first[u <= 650.], 0.)
    np.testing.assert_array_equal(first[:, -5:], 0.)
    assert first.min() < -2.
    assert first.max() > 1.5
    assert np.count_nonzero(np.abs(first) > .5) > 5000


def test_delayed_distributaries_extend_common_plain_and_are_unequal():
    trunk = np.column_stack([np.linspace(0., 500., 121), np.zeros(121)])
    branches = np.array([np.column_stack([np.linspace(250., 5000., 121), np.full(121, y)])
                         for y in (-700., 100., 800.)])
    new_trunk, new_branches, junctions = delayed_distributary_geometry(trunk, branches, np.zeros(2))
    assert junctions[0] > 500.
    assert junctions[1] == pytest.approx(junctions[2])
    assert np.linalg.norm(new_trunk[-1]-new_trunk[0]) > 1200.
    assert np.linalg.norm(new_branches[0][-1]-new_branches[0][0]) != pytest.approx(np.linalg.norm(new_branches[1][-1]-new_branches[1][0]))
    assert not np.allclose(new_branches[0][-1]-new_branches[0][0], new_branches[1][-1]-new_branches[1][0])


def test_distributary_selection_count_changes_with_forcing_and_plain_width():
    from terrain_pipeline.surface_rivers.metric_coast_bounded_delta import select_distributary_candidates
    candidates = [{"score": float(i)} for i in range(5)]
    sparse = select_distributary_candidates(0., 0., 100., candidates, limits=(1, 5))
    rich = select_distributary_candidates(5000., 50000., 6000., candidates, limits=(1, 5))
    assert sparse["count"] < rich["count"]
    assert rich["selected_indices"] == [4, 3, 2, 1, 0]


def test_secondary_starts_on_land_before_parent_first_marine():
    marine = np.zeros((30, 60), bool); marine[:, 40:] = True
    parent = np.column_stack([np.linspace(5., 55., 101), np.full(101, 15.)])
    secondary, reason = secondary_from_parent_land_prefix(parent, marine, np.zeros(2), 1.)
    assert secondary is not None and reason["reason"] == "selected"
    cells = np.floor(secondary+.5).astype(int)
    assert not marine[cells[0, 1], cells[0, 0]]


def test_terminal_only_solver_supports_two_and_four_outlets_and_closes_load():
    from terrain_pipeline.surface_rivers.metric_integrated_delta import _solve_terminal_hydraulics, route_terminal_load
    profiles = [np.linspace(1.5, -.2, 31) for _ in range(4)]
    stations = [np.linspace(0., 1200.+200.*i, 31) for i in range(4)]
    for widths in (np.array([160., 110.]), np.array([180., 145., 120., 95.])):
        n = len(widths)
        q, heads = _solve_terminal_hydraulics(profiles[:n], stations[:n], widths, 240., .035)
        exports = route_terminal_load(1234., q, 86400.)
        assert q.shape == (n,) and heads.shape == (n,)
        assert q.sum() == pytest.approx(240.)
        assert exports.sum() == pytest.approx(1234.)


def test_channel_tree_accepts_two_and_four_terminal_paths():
    from terrain_pipeline.surface_rivers.metric_integrated_delta import build_channel_tree, run_integrated_delta
    trunk = np.column_stack([np.linspace(0., 900., 19), np.zeros(19)])
    for count in (2, 4):
        branches = [np.column_stack([np.linspace(900., 1800.+i*80., 19), np.linspace(0., (i+1)*120., 19)])
                    for i in range(count)]
        geometry = build_channel_tree(np.zeros((80, 220)), np.zeros(2), 10.,
            np.array([1800., 0.]), np.array([0., 0.]), trunk, branches,
            [140., *([100.]*count)], trunk_split_station=8, branch_split_station=17)
        assert len([name for name in geometry.paths if name.startswith("terminal")]) == count
        result = run_integrated_delta(np.zeros((80, 220)), geometry, np.array([0.]), np.array([0.]), np.array([86400.]))
        assert result["final_bed_m"].shape == (80, 220)
        assert result["monthly_terminal_export_solid_m3"][0].sum() == pytest.approx(0.)


def test_open_sea_excludes_closed_pool_and_diagonal_connections():
    bed = np.ones((9, 13))
    bed[:, 9:] = -1.
    bed[4, 3:5] = -2.
    bed[4, 8] = -1.
    bed[3, 7] = -1.
    marine = open_marine_mask(bed)
    assert marine[4, 8]
    assert not marine[4, 3]
    assert not marine[3, 7]


def test_branch_stops_at_first_sea_before_reentry_and_has_own_length():
    marine = np.zeros((9, 30), bool)
    marine[:, 9:14] = True
    marine[:, 21:] = True
    path = np.array([[2., 4.], [27., 4.]])
    result, station = truncate_at_first_marine(path, marine, np.zeros(2), 1., sample_count=101)
    assert result.shape == (101, 2)
    assert station[-1] == pytest.approx(6.5, abs=1.e-10)
    cells = np.floor(result+.5).astype(int)
    assert not np.any(marine[cells[:-1, 1], cells[:-1, 0]])
    assert marine[cells[-1, 1], cells[-1, 0]]
    assert result[-1, 0] < 14.


def test_section_has_no_terminal_caps_and_no_marine_cut():
    bed = np.full((13, 21), 2.)
    path = np.column_stack([np.linspace(3., 12., 101), np.full(101, 6.)])
    marine = np.zeros_like(bed, bool)
    marine[:, 12:] = True
    section = carve_section(bed, np.zeros(2), 1., path, np.full(101, -2.),
                            np.zeros(101), 6., marine)
    assert np.any(section["bed_m"] < bed)
    np.testing.assert_array_equal(section["bed_m"][:, :3], bed[:, :3])
    np.testing.assert_array_equal(section["bed_m"][marine], bed[marine])
    assert not section["section_mask"][:, 13:].any()


def test_closed_pool_stays_dry_until_channel_connects_it():
    bed = np.ones((9, 13))
    bed[:, 10:] = -2.
    bed[4, 2:4] = -1.
    marine = open_marine_mask(bed)
    stage = np.zeros_like(bed)
    channel = np.zeros_like(bed, bool)
    water = connected_water(bed, stage, channel, marine, (0, 0))
    assert not water["wet_mask"][4, 2]
    bed[4, 3:11] = -1.
    channel[4, 2:11] = True
    water = connected_water(bed, stage, channel, marine, (0, 0))
    assert water["wet_mask"][4, 2]
    np.testing.assert_array_equal(water["water_surface_m"][marine], 0.)


def test_marine_cells_cannot_receive_river_sediment():
    marine = np.zeros((7, 9), bool)
    marine[:, 6:] = True
    retained = np.zeros_like(marine)
    retained[2, 1] = True
    geometry = SimpleNamespace(eligible_mask=np.ones_like(marine), protected_mask=np.zeros_like(marine))
    protect_scene_geometry(geometry, {"open_marine_mask": marine, "retained_upstream_raster_mask": retained})
    assert not geometry.eligible_mask[marine | retained].any()
    assert geometry.protected_mask[marine | retained].all()


def test_solver_keeps_marine_at_sea_head_and_exports_without_marine_store():
    from tests.test_metric_integrated_delta import synthetic_scene, build_geometry
    from terrain_pipeline.surface_rivers.metric_integrated_delta import run_integrated_delta
    scene = synthetic_scene()
    geometry = build_geometry(scene)
    protect_scene_geometry(geometry, {"open_marine_mask": scene["ocean"],
                           "retained_upstream_raster_mask": np.zeros_like(scene["ocean"])})
    result = run_integrated_delta(scene["bed"], geometry, np.array([1.e7]),
                                  np.array([1.e4]), np.array([30.*86400.]))
    np.testing.assert_array_equal(result["stage_m"][scene["ocean"]], 0.)
    np.testing.assert_array_equal(result["stored_solid_m3"][scene["ocean"]], 0.)
    np.testing.assert_array_equal(result["final_bed_m"][scene["ocean"]], scene["bed"][scene["ocean"]])


def test_construction_replaces_old_grooves_preserves_retained_and_closes_ledger(monkeypatch):
    import terrain_pipeline.surface_rivers.metric_coast_bounded_delta as module
    base = np.ones((31, 71))
    base[:, 40:50] = -1.
    base[:, 60:] = -1.
    origin, spacing = np.zeros(2), 1.
    incoming = np.array([[1., 15.], [10., 15.]])
    trunk = np.column_stack([np.linspace(10., 15., 21), np.full(21, 15.)])
    branches = np.array([np.column_stack([np.linspace(12.5 if i == 0 else 15., 65., 21),
                          np.linspace(15., 8.+7.*i, 21)]) for i in range(3)])
    old = base.copy()
    old[8, 53:58] = -3.
    retained = np.zeros_like(base, bool)
    retained[15, 1:4] = True
    old[retained] = -2.
    old_cuts = np.zeros((3, *base.shape))
    old_cuts[0, 8, 53:58] = 4.
    zz, xx = np.indices(base.shape)
    monkeypatch.setattr(module, "_river_fan_fields", lambda *args, **kwargs: {
        "bed_m": base.copy(), "u_m": xx-20., "v_m": zz-15., "weight": np.ones_like(base),
        "radius_m": np.hypot(xx, zz), "angle_rad": np.arctan2(zz, xx),
        "outer_radius_m": np.full_like(base, 7600.), "target_bed_m": base.copy(),
        "parameters": {"apex_u_m": -10.}})
    monkeypatch.setattr(module, "coastal_lowland_relief", lambda bed, fan: np.zeros_like(bed))
    monkeypatch.setattr(module, "delayed_distributary_geometry",
                        lambda trunk, branches, apex: (trunk, branches, np.array([2.5, 5., 5.])))
    def synthetic_truncate(path, marine, origin, spacing, sample_count=1201):
        value = np.asarray(path).copy()
        value[:, 0] = np.linspace(10., 39., len(value))
        value[-1, 0] = 40.
        return value, np.linspace(0., 1., len(value))
    monkeypatch.setattr(module, "truncate_at_first_marine", synthetic_truncate)
    arrays = {"base_bed_m": base, "bed_m": old, "old_incoming_path_xz_m": incoming,
              "bank_support_added_height_before_channel_cut_m": np.zeros_like(base),
              "retained_upstream_raster_mask": retained, "designed_incoming_path_xz_m": incoming,
              "designed_incoming_bed_m": np.array([-2., -2.]), "designed_incoming_stage_m": np.array([1., 1.]),
              "branch_paths_xz_m": branches, "trunk_path_xz_m": trunk,
              "incoming_q_m3_s": np.array([120.]),
              "trunk_reach_q_m3_s": np.array([[120., 60.]]),
              "trunk_reach_station_bounds_m": np.array([[0., 2.5], [2.5, 5.]]),
              "trunk_reach_discharge_fraction": np.array([1., .5]),
              "secondary_candidate_rejection_json": np.asarray(json.dumps({"reason": "stale_rejection"})),
              "branch_junction_station_m": np.array([2.5, 5., 5.]),
              "construction_footprint_mask": old != base, "branch_cut_depth_m": old_cuts}
    metadata = {"origin_xz_m": origin.tolist(), "spacing_m": spacing, "mouth_xz_m": [20., 15.],
                "seed": 1, "retained_profile_before_u_m": -17., "river_direction_xz": [1., 0.],
                "branching_model": {"curvature_amplitude_m": [145., 182., 219.]}}
    result = construct_coast_bounded_scene(arrays, metadata, finite_solid_supply_m3=1000.)
    final = result["arrays"]
    assert np.any(final["terminal_level"] == 1)
    assert "secondary_candidate_rejection_json" not in final
    assert not any(key.startswith("trunk_reach_") for key in final)
    assert "curvature_amplitude_m" not in result["metadata"]["branching_model"]
    candidates = json.loads(final["candidate_selection_json"].item())
    selected = [item for item in candidates if item["selected"]]
    assert len(selected) == len(final["branch_paths_xz_m"])
    for candidate in selected:
        index = candidate["selected_terminal_index"]
        assert candidate["parent_selected_index"] == final["terminal_parent_index"][index]
    assert all("score" in candidate and "reason" in candidate for candidate in candidates)
    low_budget = construct_coast_bounded_scene({**arrays, "incoming_q_m3_s": np.array([1.])}, metadata,
                                             finite_solid_supply_m3=0.)
    assert not np.any(low_budget["arrays"]["terminal_level"] == 1)
    np.testing.assert_array_equal(final["bed_m"][retained], old[retained])
    np.testing.assert_array_equal(final["pre_channel_bed_m"], base)
    marine = final["open_marine_mask"]
    np.testing.assert_array_equal(final["bed_m"][marine], base[marine])
    assert np.all(final["branch_paths_xz_m"][:, -1, 0] < 50.)
    for i, branch in enumerate(final["branch_paths_xz_m"]):
        parent = int(final["terminal_parent_index"][i])
        points = final["trunk_path_xz_m"] if parent < 0 else final["branch_paths_xz_m"][parent]
        profile = final["trunk_profile_bed_m"] if parent < 0 else final["branch_profile_bed_m"][parent]
        split = module.station_on_path(points, branch[0])
        expected = np.interp(split, module.path_station(points), profile)
        assert final["branch_profile_bed_m"][i, 0] == pytest.approx(expected)
    audit = result["audit"]
    assert audit["fill_bulk_m3"]-audit["cut_bulk_m3"] == pytest.approx(audit["net_bulk_m3"])
    assert audit["outside_footprint_exact"]


def test_explicit_scene_load_preserves_nominal_and_incoming_widths(tmp_path):
    path = tmp_path/"independent.npz"
    metadata = {"origin_xz_m": [0., 0.], "spacing_m": 1., "mouth_xz_m": [5., 5.], "fan_apex_xz_m": [2., 2.]}
    grid = np.zeros((7, 7))
    incoming = np.array([[0., 2.], [2., 2.]])
    np.savez(path, metadata_json=json.dumps(metadata), bed_m=grid, base_bed_m=grid,
             trunk_path_xz_m=incoming, branch_paths_xz_m=np.tile(incoming, (3, 1, 1)),
             branch_width_m=np.array([170., 145., 120.]), trunk_width_m=200.,
             incoming_width_profile_m=np.array([100., 200.]), open_marine_mask=grid.astype(bool),
             original_land_mask=grid.astype(bool), retained_upstream_raster_mask=grid.astype(bool),
             designed_incoming_path_xz_m=incoming, designed_incoming_bed_m=np.zeros(2),
             main_section_mask=grid.astype(bool), connected_ocean_mask=grid.astype(bool))
    scene = load_scene(path)
    np.testing.assert_array_equal(scene["widths_m"], [200., 170., 145., 120.])
    np.testing.assert_array_equal(scene["incoming_width_profile_m"], [100., 200.])
    assert "open_marine_mask" in scene
