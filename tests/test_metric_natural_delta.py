import numpy as np
import pytest
from pathlib import Path

from terrain_pipeline.surface_rivers.metric_natural_delta import NaturalDeltaConfig, finite_schedule, initial_basin


def test_finite_schedule_never_resets_source_and_separates_model_from_calendar_time():
    schedule = finite_schedule([100., 200.], [450., 0.], [86400., 86400.])
    assert len(schedule) == 3
    assert schedule[:, 3].sum() == 450.
    assert np.all(schedule[:, 3] <= 200.)
    assert np.sum(schedule[:, 4]) == pytest.approx(450./(.65*100.*.001))
    assert np.sum(schedule[:, 4]) != np.sum(schedule[:, 5])
    annual = finite_schedule([100., 200.], [450., 0.], [86400., 86400.], mode="annual")
    assert np.sum(annual[:, 4]) == 172800.
    assert np.sum(annual[:, 3]) == 450.


def test_initial_basin_has_no_downstream_bar_island_or_branches():
    config = NaturalDeltaConfig()
    bed = initial_basin(config)
    land = int(config.land_length_m/config.dx_m)
    np.testing.assert_array_equal(bed[land:], -config.basin_depth_m)
    assert np.count_nonzero(bed[0] < 0.) == int(config.inlet_width_m/config.dx_m)
    assert np.unique(bed[land:]).size == 1


def test_negative_or_nonfinite_supply_rejected():
    with pytest.raises(ValueError):
        finite_schedule([100.], [-1.], [86400.])


def test_saved_actual_backend_initial_inlet_and_water_are_consistent():
    """Exercise the real backend artifact, not a duplicate initialization formula."""
    root = Path(__file__).resolve().parents[1]
    path = root/"verification/fluvial-delta/natural-deposition-local-20261018-02/result.npz"
    if not path.exists():
        pytest.skip("complete fixed new-start backend run first")
    with np.load(path) as a:
        bed = a["bed_m"][0]
        stage = a["stage_m"][0]
        depth = a["depth_m"][0]
        cell_type = a["cell_type"]
        floor = a["source_floor_m"]
    initial = initial_basin()
    np.testing.assert_array_equal(bed, initial)
    np.testing.assert_array_equal(depth, np.maximum(stage-bed, 0.))
    expected = np.zeros_like(cell_type, bool)
    expected[:12, 52:68] = True
    np.testing.assert_array_equal(cell_type == 1, expected)
    assert np.all(bed[expected] == -1.5)
    assert np.all(depth[expected] == 1.5)
    assert np.all(bed[expected]-floor[expected] == pytest.approx(.3))
    assert np.all(depth[(cell_type == -2)] == 0.)
