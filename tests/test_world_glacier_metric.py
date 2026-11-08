"""Finite mechanism evidence; these grids are not TD acceptance artifacts."""

from copy import deepcopy

import numpy as np
import pytest

from terrain_pipeline.world_glacier import advance_flowline


def geometry(spacing=30.0, thickness=80.0):
    n = 48
    return {
        "bed_m": 3000.0 - np.arange(n) * spacing * 0.12,
        "spacing_m": spacing,
        "width_m": 2 * spacing,
        "cell_area_m2": np.full(n, 2 * spacing**2),
        "xz_m": np.column_stack((np.arange(n) * spacing, np.zeros(n))),
        "ice_thickness_m": np.full(n, thickness),
        "bedrock_erodible_m3": np.full(n, 500.0),
        "source_identity": "source",
        "terrain_identity": "terrain",
        "support_id": "glacier-0",
        "parent_terrain_revision": "r0",
    }


@pytest.mark.parametrize("spacing", [30.0, 90.0, 150.0])
def test_metric_area_live_bed_and_finite_budgets(spacing):
    g = geometry(spacing)
    original = deepcopy(g)
    result = advance_flowline(
        g,
        None,
        {"ablation_mm": np.full((2, 48), 2.0)},
        time_edges_s=[0.0, 3600.0, 7200.0],
    )
    assert np.array_equal(g["bed_m"], original["bed_m"])
    assert np.array_equal(result["arrays"]["cell_area_m2"], g["cell_area_m2"])
    assert np.any(result["arrays"]["face_ice_transfer_m3"])
    assert np.any(result["arrays"]["bed_change_m"] < 0)
    assert np.all(result["state"]["remaining_bedrock_m3"] >= 0)
    assert abs(result["ledger"]["water_residual_m3"]) < 1e-5
    assert abs(result["ledger"]["solid_residual_m3"]) < 1e-6
    assert result["ledger"]["ice_max_cell_residual_m3"] < 1e-5


def test_cold_split_is_identical_and_negative_balance_is_limited(tmp_path):
    g = geometry()
    whole = advance_flowline(g, None, {}, time_edges_s=[0.0, 7200.0])
    first = advance_flowline(g, None, {}, time_edges_s=[0.0, 3600.0])
    np.savez(tmp_path / "state.npz", **first["state"])
    with np.load(tmp_path / "state.npz") as bundle:
        state = {
            name: value.item() if value.ndim == 0 else value.copy()
            for name, value in bundle.items()
        }
    second = advance_flowline(g, state, {}, time_edges_s=[3600.0, 7200.0])
    for key in (
        "bed_m",
        "ice_thickness_m",
        "remaining_bedrock_m3",
        "pending_sediment_solid_m3",
    ):
        np.testing.assert_array_equal(whole["state"][key], second["state"][key])
    empty = advance_flowline(
        geometry(thickness=0.1),
        None,
        {
            "ablation_mm": np.full((1, 48), 10000.0),
            "sublimation_mm": np.full((1, 48), 10000.0),
        },
        time_edges_s=[0.0, 3600.0],
    )
    assert not np.any(empty["state"]["ice_thickness_m"])
    assert empty["ledger"]["melt_water_m3"] == pytest.approx(0.1 * 48 * 1800 * 0.917)
    assert empty["ledger"]["sublimation_water_m3"] == 0


def test_real_geometry_and_work_limits_reject_without_mutation():
    g = geometry()
    bad = deepcopy(g)
    bad["cell_area_m2"][:] = 900.0
    with pytest.raises(ValueError, match="actual spacing"):
        advance_flowline(bad, None, {}, time_edges_s=[0.0, 3600.0])
    before = deepcopy(g)
    with pytest.raises(ValueError, match="work budget"):
        advance_flowline(
            g, None, {}, time_edges_s=[0.0, 7200.0], config={"max_substeps": 1}
        )
    np.testing.assert_array_equal(g["bed_m"], before["bed_m"])
