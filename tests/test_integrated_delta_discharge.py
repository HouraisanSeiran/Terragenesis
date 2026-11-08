"""Discharge scenarios rebuild hydraulics while preserving finite materials."""
import numpy as np
import pytest

from tests.test_dynamic_feedback import COORDS, source
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import route_feedback_daily
from terrain_pipeline.surface_rivers.metric_upstream_sediment import load_daily_sediment, save_daily_sediment, validate_daily_sediment
from tools.run_integrated_delta import positive_discharge_scale, scale_source_discharge, source_inventory, run


@pytest.mark.parametrize("value", [0., -1., float("nan"), float("inf"), -float("inf")])
def test_scale_requires_positive_finite(value):
    with pytest.raises(ValueError, match="positive and finite"):
        positive_discharge_scale(value)


def test_unit_scale_preserves_accepted_prefix_identity():
    baseline = source()
    assert scale_source_discharge(baseline, COORDS, 1.) is baseline


def test_scaled_hydraulics_keep_finite_material_and_seasonal_shape():
    baseline = source()
    original_q = baseline["arrays"]["water_q_m3_s"].copy()
    scaled = scale_source_discharge(baseline, COORDS, 5.)
    validate_daily_sediment(scaled)
    np.testing.assert_array_equal(scaled["arrays"]["water_q_m3_s"], original_q*5.)
    np.testing.assert_array_equal(baseline["arrays"]["water_q_m3_s"], original_q)
    for key in ("receiver", "length_m", "width_m", "bed_elevation_m", "rock_floor_m", "hardness_source",
                "initial_alluvium_bulk_m3", "initial_mobile_solid_m3", "external_solid_m3_s", "retention_fraction"):
        np.testing.assert_array_equal(scaled["arrays"][key], baseline["arrays"][key])
    assert scaled["metadata"]["material"] == baseline["metadata"]["material"]
    assert scaled["metadata"]["hydraulic_identity_sha256"] != baseline["metadata"]["hydraulic_identity_sha256"]
    lower = scale_source_discharge(baseline, COORDS, 2.)
    assert np.all(scaled["arrays"]["water_depth_m"] > lower["arrays"]["water_depth_m"])


def test_supply_is_recomputed_and_bounded_not_multiplied():
    baseline = source()
    one = route_feedback_daily(baseline, COORDS)
    five = route_feedback_daily(scale_source_discharge(baseline, COORDS, 5.), COORDS)
    supply_one = float(one["arrays"]["exported_solid_m3"].sum())
    supply_five = float(five["arrays"]["exported_solid_m3"].sum())
    assert supply_one > 0.
    assert supply_five == pytest.approx(supply_one)
    assert supply_five != pytest.approx(supply_one*5.)
    inventory = source_inventory(baseline, five)
    assert inventory["initial_rock_solid_m3"] == pytest.approx(1.2)
    assert inventory["remaining_rock_solid_m3"] <= 1.e-10
    assert inventory["rock_depleted"]


def test_parameter_rebuild_and_saved_prefix_replay_match(tmp_path):
    baseline = source()
    scaled = scale_source_discharge(baseline, COORDS, 2.)
    path = tmp_path/"prefix.npz"
    save_daily_sediment(path, scaled)
    loaded = load_daily_sediment(path, file_sha256(path))
    rebuilt = scale_source_discharge(baseline, COORDS, 2.)
    assert rebuilt["identity_sha256"] == loaded["identity_sha256"]
    assert route_feedback_daily(rebuilt, COORDS)["identity_sha256"] == route_feedback_daily(loaded, COORDS)["identity_sha256"]
    assert scale_source_discharge(baseline, COORDS, 3.)["identity_sha256"] != loaded["identity_sha256"]


def test_existing_result_directory_is_preserved(tmp_path):
    marker = tmp_path/"summary.json"
    marker.write_text("accepted", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already contains"):
        run(tmp_path, 2.)
    assert marker.read_text(encoding="utf-8") == "accepted"
