from types import SimpleNamespace

import numpy as np
import pytest

from tools.prepare_natural_delta_wide_initial import prepare
from tools.run_natural_delta_wide import apply_inlet_stage, material_reference, execute, initial_discharge_guess
from tools.run_natural_delta import load_forcing


@pytest.fixture(scope="module")
def prepared():
    return prepare()


def test_wide_river_preserves_marine_bed_and_descends_to_mouth(prepared):
    arrays, report = prepared
    marine = arrays["station_m"] >= 0.
    np.testing.assert_array_equal(arrays["initial_bed_m"][marine], arrays["source_base_bed_m"][marine])
    assert arrays["construction_height_delta_m"].max() == 0.
    inlet = arrays["inlet_columns"]
    assert len(inlet) == 16
    assert np.diff(arrays["initial_bed_m"][:73, inlet], axis=0).max() <= 0.
    assert np.all(arrays["cell_type"][2:-1, 1:-1] == 0)
    assert not report["relative_piece_cuts_imported"]
    assert report["parent_checkpoint"] is None


def test_wet_section_matches_q_at_inlet_mouth_and_sea50m(prepared):
    arrays, report = prepared
    inlet = arrays["inlet_columns"]
    np.testing.assert_allclose(arrays["initial_depth_m"][0, inlet], 4.)
    for station in (-360., 0., 50.):
        section = next(row for row in report["sections"] if row["station_m"] == station)
        assert section["core_wet_area_m2"] > 240.
        assert 1. <= section["q_divided_by_core_area_m_s"] <= 2.
    assert report["initial_water"]["not_hydraulic_equilibrium_or_tide_solution"]


def test_stage_boundary_changes_only_row_zero_inlet():
    model = SimpleNamespace(stage=np.arange(100, dtype=float).reshape(10, 10),
        depth=np.ones((10, 10)), eta=np.zeros((10, 10)), inlet=np.arange(3, 7))
    old_stage, old_depth = model.stage.copy(), model.depth.copy()
    apply_inlet_stage(model, 4.)
    changed = np.zeros((10, 10), bool)
    changed[0, model.inlet] = True
    np.testing.assert_array_equal(model.stage[~changed], old_stage[~changed])
    np.testing.assert_array_equal(model.depth[~changed], old_depth[~changed])
    np.testing.assert_array_equal(model.stage[changed], 4.)


def test_absolute_material_thresholds_match_td02_reference():
    thresholds, report = material_reference()
    speed = report["reference_initial_u0_m_s"]
    assert speed == pytest.approx(4.029710425919349)
    assert thresholds["U_dep_mud"] == pytest.approx(1.2089131277758047)
    assert thresholds["U_ero_mud"] == pytest.approx(6.044565638879024)
    assert thresholds["U_ero_sand"] == pytest.approx(4.231195947215316)


def test_initial_flow_guess_reaches_flat_wet_sea_and_normalizes_each_section(prepared):
    arrays, geometry = prepared
    q = geometry["inlet"]["q_m3_s"]
    depth = arrays["initial_depth_m"]
    inlet = arrays["inlet_columns"]
    guessed = initial_discharge_guess(depth, inlet, q)
    wet = depth > .01
    assert np.all(guessed[1:][wet[1:]] > 0.)
    assert np.all(guessed[~wet] == 0.)
    np.testing.assert_allclose(guessed.astype(float).sum(axis=1) * 5., q, rtol=1.e-7)
    np.testing.assert_allclose(guessed[0, inlet], q / 80., rtol=1.e-7)
    assert np.count_nonzero(guessed[0]) == 16
    assert np.all(guessed[-2][wet[-2]] > 0.)


def test_initial_flow_guess_rejects_section_without_wet_route():
    depth = np.ones((3, 10))
    depth[1] = 0.
    with pytest.raises(ValueError, match="wet path"):
        initial_discharge_guess(depth, np.arange(3, 7), 100.)


def test_native_initialization_uses_matching_inlet_and_preserves_interior_water(prepared, tmp_path):
    arrays, geometry = prepared
    schedule, _ = load_forcing("mechanism")
    state, report = execute(arrays, geometry, schedule, tmp_path / "native", initialize_only=True)
    assert report["steps"] == 0
    assert report["N0"] == 16
    assert report["L0"] == 2
    assert report["initialized_inlet_q_m3_s"] == pytest.approx(geometry["inlet"]["q_m3_s"], rel=1.e-6)
    assert report["interior_stage_initialization_error_m"] < 5.e-7
    assert report["source_floor_minimum_margin_m"] >= 0.
    assert report["actual_material_thresholds_m_s"] == report["materials"]["absolute_thresholds_m_s"]
    assert report["initial_flow_guess"]["interior_wet_cells_without_downstream_guess"] == 0
    assert report["initial_flow_guess"]["dry_cells_with_nonzero_guess"] == 0
    assert not report["initial_flow_guess"]["applied_each_timestep"]
    np.testing.assert_allclose(state["qx_m2_s"].astype(float).sum(axis=1) * 5., geometry["inlet"]["q_m3_s"], rtol=1.e-7)
    np.testing.assert_allclose(state["bed_m"], arrays["initial_bed_m"], atol=1.e-6)
