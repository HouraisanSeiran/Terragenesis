from dataclasses import replace
import numpy as np
import pytest

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import bed_slopes, deposit_landward_plain, normal_depth, route_feedback_daily
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import load_daily_sediment, route_daily_sediment, save_daily_sediment, validate_daily_sediment
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval, simulate_fluvial_delta


def source(*, hardness=0., days=4, loose=.02, rock=.03, material=None, q=5.):
    material = material or MaterialParameters(settling_velocity_m_s=0.)
    bed = np.array([2., 1.])
    area = np.array([20., 20.])
    return route_daily_sediment(
        receiver=np.array([1, -1], np.int64), length_m=np.array([10., 10.]), width_m=np.array([2., 2.]),
        bed_elevation_m=bed, water_depth_m=np.full((days, 2), 1. if q else 0.),
        water_q_m3_s=np.full((days, 2), q), friction_slope=np.full((days, 2), .05),
        time_seconds=np.arange(days+1, dtype=np.float64)*86400., rock_floor_m=bed-loose-rock,
        initial_alluvium_bulk_m3=area*loose, hardness=np.full(2, hardness), material=material,
        initial_mobile_solid_m3=np.array([.5, 0.]),
        geometry_identity_sha256="a"*64, hydraulic_identity_sha256="b"*64, material_provenance="test finite inventory")


COORDS = np.array([[0., 0.], [20., 0.]])


def test_sequential_finite_inventory_and_real_slope():
    b = source()
    result = route_feedback_daily(b, COORDS)
    a = result["arrays"]
    validate_daily_sediment(result)
    assert a["friction_slope"][0, 0] == .05
    np.testing.assert_allclose(a["friction_slope"][:, 0],
                               (a["trace_bed_m"][:-1, 0]-a["trace_bed_m"][:-1, 1])/20.)
    assert a["trace_rock_removed_m3"][-1].sum() <= 1.2+1e-10
    assert a["eroded_loose_solid_m3"][1:].sum() == 0.
    assert a["eroded_rock_m3"][1:].sum() == 0.
    assert a["exported_solid_m3"].sum() == pytest.approx(.52+1.2+.5)
    np.testing.assert_array_equal(a["rock_floor_m"], b["arrays"]["rock_floor_m"])


def test_hardness_and_material_are_preserved():
    material = MaterialParameters(transport_coefficient=2e-6, settling_velocity_m_s=0., provenance="custom")
    soft = route_feedback_daily(source(loose=0., hardness=0., material=material), COORDS)
    hard = route_feedback_daily(source(loose=0., hardness=1., material=material), COORDS)
    assert soft["arrays"]["eroded_rock_m3"].sum() > 0.
    assert hard["arrays"]["eroded_rock_m3"].sum() == 0.
    assert soft["metadata"]["material"]["transport_coefficient"] == 2e-6
    assert soft["metadata"]["material"]["provenance"] == "custom"


def test_zero_flow_carries_mobile_without_reset():
    b = source(q=0.)
    a = route_feedback_daily(b, COORDS)["arrays"]
    np.testing.assert_array_equal(a["trace_mobile_solid_m3"], np.tile([.5, 0.], (5, 1)))
    np.testing.assert_array_equal(a["trace_bed_m"], np.tile([2., 1.], (5, 1)))
    assert a["exported_solid_m3"].sum() == 0.


def test_zero_material_zero_supply_does_not_create_sediment():
    b = source(loose=0., rock=0.)
    b["arrays"]["initial_mobile_solid_m3"][:] = 0.
    # Build a fresh declared source, rather than mutating an output ledger.
    a = b["arrays"]
    b = route_daily_sediment(**{k: a[k] for k in ("receiver", "length_m", "width_m", "bed_elevation_m", "water_depth_m", "water_q_m3_s", "friction_slope", "time_seconds", "rock_floor_m", "initial_alluvium_bulk_m3", "initial_mobile_solid_m3")},
                            hardness=a["hardness_source"], material=MaterialParameters(settling_velocity_m_s=0.),
                            geometry_identity_sha256="a"*64, hydraulic_identity_sha256="b"*64, material_provenance="zero")
    result = route_feedback_daily(b, COORDS)
    assert result["arrays"]["exported_solid_m3"].sum() == 0.
    np.testing.assert_array_equal(result["arrays"]["trace_bed_m"], np.tile([2., 1.], (5, 1)))


def test_feedback_changes_next_interval_hydraulics():
    material = MaterialParameters(rock_erodibility_m_s_pa=0., settling_velocity_m_s=0.)
    b = source(loose=.1, rock=0., material=material)
    # Different finite cover thicknesses change the geometric grade when scoured.
    a = b["arrays"]
    a["initial_alluvium_bulk_m3"][1] = 0.
    a["rock_floor_m"][1] = 1.
    args = {k: a[k] for k in ("receiver", "length_m", "width_m", "bed_elevation_m", "water_depth_m", "water_q_m3_s", "friction_slope", "time_seconds", "rock_floor_m", "initial_alluvium_bulk_m3")}
    fresh = route_daily_sediment(**args, hardness=a["hardness_source"], material=material,
                               geometry_identity_sha256="a"*64, hydraulic_identity_sha256="b"*64, material_provenance="grade change")
    result = route_feedback_daily(fresh, COORDS)["arrays"]
    assert result["friction_slope"][1, 0] < result["friction_slope"][0, 0]
    assert result["water_depth_m"][1, 0] > result["water_depth_m"][0, 0]


def test_reversed_bed_is_rejected_explicitly():
    with pytest.raises(ValueError, match="reversed or flat"):
        bed_slopes(np.array([1, -1]), np.array([1., 2.]), COORDS)


@pytest.mark.parametrize("arguments", [(float("nan"), 2., .1), (1., float("inf"), .1), (1., 2., float("nan")), (-1., 2., .1)])
def test_normal_depth_rejects_nonfinite_or_invalid_parameters(arguments):
    with pytest.raises(ValueError):
        normal_depth(*arguments)


@pytest.mark.parametrize("field,index,value,reason", [
    ("time_seconds", 1, 0., "time_seconds"),
    ("time_seconds", 1, float("nan"), "time_seconds"),
    ("trace_mobile_solid_m3", (0, 0), 3., "initial inventory"),
    ("trace_loose_solid_m3", (0, 0), 3., "initial inventory"),
    ("trace_rock_removed_m3", (2, 0), .1, "per-step cumulative"),
    ("exported_solid_m3", (0, 0), .1, "terminal export"),
    ("external_solid_m3_s", (0, 0), .1, "external rate"),
])
def test_rehashed_cold_ledger_tampering_is_rejected(field, index, value, reason):
    result = route_feedback_daily(source(), COORDS)
    result["arrays"][field][index] = value
    result["identity_sha256"] = identity(result["arrays"], result["metadata"])
    with pytest.raises(ValueError, match=reason):
        validate_daily_sediment(result)


def test_cold_load_replay_identity_and_tampering(tmp_path):
    b = source()
    result = route_feedback_daily(b, COORDS)
    path = tmp_path/"feedback.npz"
    save_daily_sediment(path, result)
    loaded = load_daily_sediment(path, file_sha256(path))
    assert loaded["identity_sha256"] == route_feedback_daily(b, COORDS)["identity_sha256"]
    assert loaded["metadata"]["hydraulic_identity_sha256"] != b["metadata"]["hydraulic_identity_sha256"]
    loaded["metadata"]["manning_roughness"] = .1
    with pytest.raises(ValueError, match="identity"):
        validate_daily_sediment(loaded)


def test_landward_nonunit_cell_area_and_no_wetland_inference():
    out = deposit_landward_plain(np.zeros((2, 2)), np.array([[1, 0], [0, 1]], bool), np.ones((2, 2)), cell_area_m2=900.)
    assert out["deposited_solid_m3"].sum() == 2.
    assert out["final_bed_m"].sum()*900.*.65 == pytest.approx(2.)
    assert "wetland_cells" not in out


def test_combined_exact_handoff_land_deposition_and_zero_control():
    upstream = route_feedback_daily(source(), COORDS)["arrays"]
    handoff = float(upstream["exported_solid_m3"].sum())
    bed = np.tile(np.array([.2, .1, -.1, -.2]), (4, 1))
    ocean = bed <= 0.
    exports = np.zeros((4, 4), bool)
    exports[:, -1] = True
    terrain = TerrainGrid(bed, np.ones((4, 4), bool), 0., 0., 30., 30., "diagnostic_dem_proxy", "test", "a"*64)
    boundary = FluvialDeltaBoundary(ocean, exports, 0., .5, "test")
    config = FluvialDeltaConfig(capacity_solid_per_water=0.)
    result = simulate_fluvial_delta(terrain, boundary, [FluvialDeltaInterval((1, 0), 100., handoff)], config)
    zero = simulate_fluvial_delta(terrain, boundary, [FluvialDeltaInterval((1, 0), 100., 0.)], config)
    assert result["deposited_solid_m3"][bed > 0.].sum() > 0.
    assert result["solid_ledger"]["input_solid_m3"] == handoff
    assert result["solid_ledger"]["residual_solid_m3"] == pytest.approx(0.)
    np.testing.assert_array_equal(zero["final_bed_m"], bed)


def test_cut_control_volumes_stop_at_handoff_and_preserve_cover_thickness():
    from tools.run_feedback_landward_case import cut_source, monthly_sum
    b = source()
    coordinates = np.array([[0., 0.], [30., 0.]])
    cut = cut_source(b, coordinates, 2)["arrays"]
    assert cut["length_m"].sum() == 30.
    np.testing.assert_array_equal(cut["length_m"], [15., 15.])
    np.testing.assert_allclose(cut["initial_alluvium_bulk_m3"]/cut["area_m2"], .02)
    assert monthly_sum(np.array([1., 2., 3., 4.]), np.array([0., 1., 2., 3.]), np.array([1., 2., 3., 4.]),
                       np.array([0., 2.]), np.array([2., 4.])).tolist() == [3., 7.]
    with pytest.raises(ValueError, match="partition"):
        monthly_sum(np.ones(2), np.array([0., 1.]), np.array([1., 2.]), np.array([0.]), np.array([1.5]))
