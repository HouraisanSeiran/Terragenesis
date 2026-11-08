import numpy as np
import pytest
from copy import deepcopy
from terrain_pipeline.surface_rivers.metric_saved_river_supply import partition_saved_supply, replay_saved_supply
from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from terrain_pipeline.runoff import _year as _year


def make_case(substeps=1, unrelated_rain_scale=1.0):
    parent_plan = {
        "receiver": np.full((3, 4), -1, dtype=np.int64),
        "owner_domain_id": np.full((3, 4), -1, dtype=np.int64),
        "ocean_mask": np.zeros((3, 4), dtype=bool),
        "domains": [{"domain_id": 0, "kind": "coastal", "terminal_indices": [5, 9]}],
        "spacing_m": 10,
    }
    parent_plan["receiver"].flat[0] = 1
    parent_plan["receiver"].flat[1] = 5
    parent_plan["receiver"].flat[4] = 5
    parent_plan["receiver"].flat[8] = 9
    for idx in (0, 1, 4, 8):
        parent_plan["owner_domain_id"].flat[idx] = 0
    parent_plan["ocean_mask"].flat[5] = True
    parent_plan["ocean_mask"].flat[9] = True

    columns = {
        "owner_domain_id": np.zeros((1, 5), dtype=np.int64),
        "seasonal_parent_cell_id": np.array([[0, 1, 1, 4, 8]], dtype=np.int64),
        "seasonal_column_area_m2": np.array([[100.0, 40.0, 60.0, 100.0, 100.0]]),
    }

    climate = {
        "precipitation_mm": np.full((12, 1, 5), 60.0),
        "potential_et_mm": np.full((12, 1, 5), 10.0),
    }
    climate["precipitation_mm"][:, :, 4] *= unrelated_rain_scale

    config = SeasonalConfig(substeps_per_day=substeps)

    result = _year(
        np.zeros((1, 5)),
        np.zeros((1, 5), np.int64),
        parent_plan["domains"],
        {},
        columns["seasonal_column_area_m2"],
        climate,
        config,
        np.full((1, 5), 30.0),
        np.zeros(1),
        retain=True,
    )

    four_keys = [
        "coastal_outflow_m3",
        "runoff_to_terminal_m3",
        "land_rain_m3",
        "lake_rain_m3",
    ]
    saved = {
        "soil_mm": np.stack(result[3]),
        "domain_ids": [0],
        "steps": {key: np.stack([step[key] for step in result[5]]) for key in four_keys},
        "monthly": {key: result[2][key] for key in four_keys},
    }

    partition = partition_saved_supply(
        parent_plan, columns, source_node=1, receiver_node=5
    )
    return (parent_plan, columns, climate, saved, config, partition)


def test_partition():
    parent_plan, columns, climate, saved, config, partition = make_case()

    receiver_before = parent_plan["receiver"].copy()

    terminal_ids = partition["terminal_ids"]
    np.testing.assert_array_equal(terminal_ids, [5, 9])

    terminal_column_masks = partition["terminal_column_masks"]
    np.testing.assert_array_equal(terminal_column_masks, [
        [True, True, True, True, False],
        [False, False, False, False, True],
    ])

    selected_column_mask = partition["selected_column_mask"]
    np.testing.assert_array_equal(selected_column_mask, [True, True, True, False, False])

    other_receiver_column_mask = partition["other_receiver_column_mask"]
    np.testing.assert_array_equal(other_receiver_column_mask, [False, False, False, True, False])

    selected_parent_mask = partition["selected_parent_mask"]
    assert np.flatnonzero(selected_parent_mask).tolist() == [0, 1]

    assert parent_plan["receiver"].flat[1] == 5
    assert np.array_equal(parent_plan["receiver"], receiver_before)


@pytest.mark.parametrize("substeps", [1, 2])
def test_replay_units_and_saved_state(substeps):
    parent, columns, climate, saved, config, partition = make_case(substeps=substeps)
    result = replay_saved_supply(partition, columns, climate, saved, config)
    dt = 86400.0 / substeps
    assert np.allclose(result['selected_volume_m3'], result['selected_q_m3_s'] * dt)
    assert np.allclose(result['terminal_volume_m3'], result['terminal_q_m3_s'] * dt)
    assert np.allclose(result['step_end_s'][-1], 31536000.0)
    expected_selected = result['terminal_volume_m3'][:, 0] * (2.0 / 3.0)
    np.testing.assert_allclose(result['selected_volume_m3'], expected_selected)
    np.testing.assert_allclose(result['other_receiver_volume_m3'], expected_selected * 0.5)
    np.testing.assert_allclose(result['coastal_soil_month_mm'], saved['soil_mm'].reshape(13, -1))
    np.testing.assert_allclose(result['annual_selected_volume_m3'], result['monthly_selected_volume_m3'].sum())
    nsteps = len(result['step_start_s'])
    np.testing.assert_allclose(result['annual_selected_volume_m3'], result['selected_volume_m3'][:nsteps].sum())


def test_unrelated_branch():
    parent0, columns0, climate0, saved0, config0, partition0 = make_case()
    parent1, columns1, climate1, saved1, config1, partition1 = make_case(unrelated_rain_scale=2.0)
    result0 = replay_saved_supply(partition0, columns0, climate0, saved0, config0)
    result1 = replay_saved_supply(partition1, columns1, climate1, saved1, config1)
    np.testing.assert_allclose(result0['selected_volume_m3'], result1['selected_volume_m3'])
    np.testing.assert_allclose(result0['terminal_volume_m3'][:, 0], result1['terminal_volume_m3'][:, 0])
    assert not np.allclose(result0['terminal_volume_m3'][:, 1], result1['terminal_volume_m3'][:, 1])


@pytest.mark.parametrize("bad", ["area", "parent"])
def test_reject_incompatible_mapping(bad):
    parent, columns, climate, saved, config, partition = make_case()
    bad_columns = deepcopy(columns)
    if bad == "area":
        bad_columns["seasonal_column_area_m2"][0, 1] += 1.0
    else:
        bad_columns["seasonal_parent_cell_id"][0, 1] = 5
    with pytest.raises(ValueError):
        partition_saved_supply(parent, bad_columns, source_node=1, receiver_node=5)


def test_reject_month_soil_mismatch():
    parent, columns, climate, saved, config, partition = make_case()
    bad_saved = deepcopy(saved)
    bad_saved["soil_mm"][5, 0, 0] += 0.1
    with pytest.raises(ValueError, match="soil mismatch"):
        replay_saved_supply(partition, columns, climate, bad_saved, config)


@pytest.mark.parametrize("period", ["steps", "monthly"])
def test_reject_saved_ledger_mismatch(period):
    parent, columns, climate, saved, config, partition = make_case()
    bad_saved = deepcopy(saved)
    key = "coastal_outflow_m3" if period == "steps" else "coastal_outflow_m3"
    ledger = bad_saved[period][key]
    ledger[2, 0] += 1.0
    with pytest.raises(ValueError, match="mismatch"):
        replay_saved_supply(partition, columns, climate, bad_saved, config)


