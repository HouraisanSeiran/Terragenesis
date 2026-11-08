import numpy as np

from tests.test_dynamic_feedback import source, COORDS
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import route_feedback_daily
from tools.run_finite_multiyear_source import run_bundle


def test_new_layer_added_once_with_carried_stores_and_lifetime_rock_debit(tmp_path):
    parent = route_feedback_daily(source(days=2, loose=.02, rock=.03), COORDS)
    summary = run_bundle(parent, tmp_path / "source", years=2, added_rock_thickness_m=.1)
    with np.load(tmp_path / "source/result.npz") as a:
        original = parent["arrays"]
        for target, source_key in (("trace_bed_m", "trace_bed_m"), ("trace_loose_solid_m3", "trace_loose_solid_m3"),
                ("trace_mobile_solid_m3", "trace_mobile_solid_m3"), ("trace_lifetime_rock_removed_solid_m3", "trace_rock_removed_m3")):
            np.testing.assert_array_equal(a[target][0], original[source_key][-1])
        np.testing.assert_allclose(a["rock_floor_m"], original["rock_floor_m"] - .1)
        assert a["trace_lifetime_rock_removed_solid_m3"][-1].sum() <= .13 * original["area_m2"].sum() + 1.e-9
        np.testing.assert_allclose(np.diff(a["trace_added_scenario_rock_removed_solid_m3"], axis=0), a["eroded_rock_m3"])
        np.testing.assert_allclose(a["trace_lifetime_rock_removed_solid_m3"],
            a["trace_added_scenario_rock_removed_solid_m3"] + original["trace_rock_removed_m3"][-1])
        assert a["exported_solid_m3"].sum() <= .1 * original["area_m2"].sum() + 1.e-9
    assert summary["status"] == "completed"
    assert summary["accepted_intervals"] == 4
    assert abs(summary["global_residual_solid_m3"]) < 1.e-9
    assert summary["old_exports_reissued_solid_m3"] == 0.


def test_zero_added_material_cannot_repeat_exhausted_parent_export(tmp_path):
    parent = route_feedback_daily(source(days=2, loose=.02, rock=.03), COORDS)
    summary = run_bundle(parent, tmp_path / "source", years=2, added_rock_thickness_m=0.)
    assert summary["new_deliverable_export_solid_m3"] < 1.e-10


def test_adverse_initial_slope_fails_without_raising_or_repairing_bed(tmp_path):
    parent = route_feedback_daily(source(days=2), COORDS)
    parent["arrays"]["trace_bed_m"][-1] = [1., 2.]
    summary = run_bundle(parent, tmp_path / "source", years=1)
    assert summary["status"] == "failed-normal-flow-closure"
    assert "reversed or flat" in summary["failure"]["reason"]
    assert summary["accepted_intervals"] == 0
    with np.load(tmp_path / "source/result.npz") as a:
        np.testing.assert_array_equal(a["trace_bed_m"][0], [1., 2.])
