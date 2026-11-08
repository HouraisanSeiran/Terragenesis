import numpy as np
import pytest

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import (
    FluvialDeltaBoundary,
    FluvialDeltaConfig,
    FluvialDeltaInterval,
    simulate_fluvial_delta,
)
from terrain_pipeline.surface_rivers.metric_river_dominant_delta import (
    RiverDominantComparisonConfig,
    simulate_river_dominant_budget,
    simulate_river_dominant_grid,
)


def _budget_config(**overrides):
    base = dict(branch_count=3, bar_resistance_per_m3=1e-3, capacity_solid_per_water=0.1)
    base.update(overrides)
    return RiverDominantComparisonConfig(**base)


def test_nonspatial_zero_water_escores_solid_and_exports_nothing():
    config = _budget_config()
    result = simulate_river_dominant_budget(
        [FluvialDeltaInterval((0, 0), 0.0, 5.0)], config
    )
    record = result["records"][0]
    assert record["ocean_export_water_m3"] == 0.0
    assert record["retained_water_m3"] == 0.0
    assert record["unresolved_solid_m3"] == 5.0
    assert all(value == 0.0 for value in record["deposited_solid_m3"])
    assert all(value == 0.0 for value in record["ocean_export_solid_m3"])
    assert record["solid_residual_m3"] == 0.0
    assert record["water_residual_m3"] == 0.0


def test_nonspatial_zero_solid_has_no_deposition_and_exports_water():
    config = _budget_config()
    result = simulate_river_dominant_budget(
        [FluvialDeltaInterval((0, 0), 100.0, 0.0)], config
    )
    record = result["records"][0]
    assert record["deposited_solid_m3"] == [0.0, 0.0, 0.0]
    assert record["ocean_export_solid_m3"] == [0.0, 0.0, 0.0]
    assert record["unresolved_solid_m3"] == 0.0
    assert record["ocean_export_water_m3"] == pytest.approx(100.0)
    assert record["retained_water_m3"] == 0.0


def test_nonspatial_under_capacity_load_is_transported_not_deposited():
    config = _budget_config(capacity_solid_per_water=1.0)
    result = simulate_river_dominant_budget(
        [FluvialDeltaInterval((0, 0), 100.0, 1.0)], config
    )
    record = result["records"][0]
    assert sum(record["deposited_solid_m3"]) == pytest.approx(0.0, abs=1e-12)
    assert sum(record["ocean_export_solid_m3"]) == pytest.approx(1.0)
    assert record["unresolved_solid_m3"] == 0.0


def test_nonspatial_excess_above_target_deposits():
    config = _budget_config(capacity_solid_per_water=0.01)
    result = simulate_river_dominant_budget(
        [FluvialDeltaInterval((0, 0), 100.0, 10.0)], config
    )
    record = result["records"][0]
    assert sum(record["deposited_solid_m3"]) == pytest.approx(9.0)
    assert sum(record["ocean_export_solid_m3"]) == pytest.approx(1.0)
    assert sum(record["deposited_solid_m3"]) + sum(
        record["ocean_export_solid_m3"]
    ) == pytest.approx(10.0)


def test_nonspatial_typed_config_and_immutable_forcing():
    config = _budget_config()
    forcing = [FluvialDeltaInterval((1, 2), 10.0, 1.0)]
    before = forcing.copy()
    simulate_river_dominant_budget(forcing, config)
    assert forcing == before
    with pytest.raises(ValueError):
        RiverDominantComparisonConfig(branch_count=1)
    with pytest.raises(ValueError):
        RiverDominantComparisonConfig(initial_branch_resistance=(0.0,))
    with pytest.raises(ValueError):
        simulate_river_dominant_budget(forcing, object())


def test_nonspatial_rejects_unbounded_forcing_and_numeric_overflow():
    interval = FluvialDeltaInterval((0, 0), 1., 1.)
    with pytest.raises(ValueError, match="bounded"):
        simulate_river_dominant_budget([interval] * 1025)
    with pytest.raises(ValueError, match="forcing totals overflow"):
        simulate_river_dominant_budget([FluvialDeltaInterval((0, 0), 1e308, 0.)] * 2)
    with pytest.raises(ValueError, match="capacity overflow"):
        simulate_river_dominant_budget(
            [FluvialDeltaInterval((0, 0), 1e308, 0.)],
            RiverDominantComparisonConfig(capacity_solid_per_water=10.))
    with pytest.raises(ValueError, match="resistance overflow"):
        simulate_river_dominant_budget(
            [FluvialDeltaInterval((0, 0), 1., 100.)],
            RiverDominantComparisonConfig(bar_resistance_per_m3=1e308))


def _asymmetric_comparison_config():
    return RiverDominantComparisonConfig(
        branch_count=3,
        bar_resistance_per_m3=5e-3,
        capacity_solid_per_water=0.01,
        initial_branch_resistance=(0.0, 0.0, 1.0),
    )


def test_nonspatial_bed_feedback_reallocates_shares_in_asymmetric_fixture():
    config = _asymmetric_comparison_config()
    forcing = [
        FluvialDeltaInterval((0, 0), 1000.0, 200.0),
        FluvialDeltaInterval((0, 0), 1000.0, 200.0),
        FluvialDeltaInterval((0, 0), 1000.0, 0.0),
    ]
    result = simulate_river_dominant_budget(forcing, config)
    first = np.asarray(result["records"][0]["branch_share"])
    last = np.asarray(result["records"][2]["branch_share"])
    assert not np.allclose(first, last)
    assert result["totals"]["solid_residual_m3"] == pytest.approx(0.0, abs=1e-9)
    assert abs(result["totals"]["water_residual_m3"]) < 1e-9


def _river_terrain():
    bed = np.full((9, 15), 0.2, np.float64)
    bed[:, 10:] = -0.5
    terrain = TerrainGrid(
        bed,
        np.ones(bed.shape, bool),
        0.0,
        0.0,
        10.0,
        10.0,
        "diagnostic_dem_proxy",
        "river-dominant-adapter",
        "d" * 64,
    )
    ocean = bed < 0.0
    exports = np.zeros(bed.shape, bool)
    for row in (2, 4, 6):
        exports[row, -1] = True
    boundary = FluvialDeltaBoundary(ocean, exports, 0.0, 2.0, "river-dominant-boundary")
    return terrain, boundary


def _river_config(**overrides):
    base = dict(porosity=0.35, capacity_solid_per_water=0.02)
    base.update(overrides)
    return FluvialDeltaConfig(**base)


def _spatial_asymmetric_terrain():
    """Shallow asymmetric bed with two distinct outlet rows."""
    bed = np.full((5, 9), 0.6, np.float64)
    bed[:, 6:] = -0.4
    bed[1, 2] = 0.80
    bed[1, 3] = 0.90
    bed[3, 2] = 0.10
    bed[3, 3] = 0.05
    terrain = TerrainGrid(
        bed,
        np.ones(bed.shape, bool),
        0.0,
        0.0,
        10.0,
        10.0,
        "diagnostic_dem_proxy",
        "asymmetric-spatial-bed",
        "e" * 64,
    )
    ocean = bed < 0.0
    exports = np.zeros(bed.shape, bool)
    exports[1, -1] = True
    exports[3, -1] = True
    boundary = FluvialDeltaBoundary(ocean, exports, 0.0, 2.0, "asymmetric-sea")
    return terrain, boundary


def test_grid_reuses_kernel_and_closure_holds():
    terrain, boundary = _river_terrain()
    outlets = [(2, 14), (4, 14), (6, 14)]
    forcing = [FluvialDeltaInterval((4, 2), 500.0, 80.0) for _ in range(4)]
    config = _river_config()
    physical = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), outlets, forcing, config
    )
    kernel = simulate_fluvial_delta(terrain, boundary, forcing, config)

    # Direct comparison demonstrates the adapter is a thin reuse of the kernel.
    np.testing.assert_array_equal(
        physical["final_bed_m"], kernel["final_bed_m"]
    )
    np.testing.assert_array_equal(
        physical["deposited_solid_m3"], kernel["deposited_solid_m3"]
    )
    for record, kernel_record in zip(
        physical["intervals"], kernel["intervals"]
    ):
        np.testing.assert_array_equal(
            record["water_throughput_m3"], kernel_record["water_throughput_m3"]
        )
        np.testing.assert_array_equal(
            record["deposited_solid_m3"], kernel_record["deposited_solid_m3"]
        )
    assert physical["sediment_budget"]["solid_residual_m3"] == pytest.approx(
        0.0, abs=1e-9
    )
    assert physical["sediment_budget"]["deposited_solid_m3"] == pytest.approx(
        kernel["solid_ledger"]["deposited_solid_m3"]
    )


def test_grid_repeated_output_is_exact():
    terrain, boundary = _river_terrain()
    outlets = [(2, 14), (4, 14), (6, 14)]
    forcing = [FluvialDeltaInterval((4, 2), 500.0, 80.0) for _ in range(3)]
    config = _river_config()
    first = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), outlets, forcing, config
    )
    second = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), outlets, forcing, config
    )
    np.testing.assert_array_equal(first["final_bed_m"], second["final_bed_m"])
    assert first["sediment_budget"] == second["sediment_budget"]
    assert first["water_budget"] == second["water_budget"]
    for a, b in zip(first["branch_history"], second["branch_history"]):
        assert a["branch_share"] == b["branch_share"]
        assert a["outlet_water_m3"] == b["outlet_water_m3"]
        np.testing.assert_array_equal(a["bed_after_m"], b["bed_after_m"])


def test_grid_shares_match_kernel_outlet_water_over_exported_water():
    terrain, boundary = _river_terrain()
    outlets = [(2, 14), (4, 14), (6, 14)]
    forcing = [FluvialDeltaInterval((4, 2), 500.0, 80.0) for _ in range(4)]
    result = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), outlets, forcing, _river_config()
    )
    rows = [cell[0] for cell in outlets]
    columns = [cell[1] for cell in outlets]
    for record, kernel_record in zip(
        result["branch_history"], result["intervals"]
    ):
        water = np.asarray(kernel_record["water_throughput_m3"], dtype=float)
        outlet_water = water[rows, columns]
        np.testing.assert_allclose(record["outlet_water_m3"], outlet_water)
        exported = float(kernel_record["water_ledger"]["ocean_export_m3"])
        if exported > 0.0:
            np.testing.assert_allclose(record["branch_share"], outlet_water / exported)
            assert sum(record["branch_share"]) == pytest.approx(1.0)
        else:
            assert record["branch_share"] == [0.0, 0.0, 0.0]


def test_grid_zero_water_and_zero_solid_behaviour():
    terrain, boundary = _river_terrain()
    outlets = [(2, 14), (4, 14), (6, 14)]
    config = _river_config()
    no_water = simulate_river_dominant_grid(
        terrain,
        boundary,
        (4, 2),
        outlets,
        [FluvialDeltaInterval((4, 2), 0.0, 100.0)],
        config,
    )
    record = no_water["branch_history"][0]
    np.testing.assert_array_equal(no_water["final_bed_m"], terrain.elevation_m)
    assert record["ocean_export_water_m3"] == 0.0
    assert record["branch_share"] == [0.0, 0.0, 0.0]
    assert record["unresolved_solid_m3"] == 100.0
    assert no_water["water_budget"]["retained_water_m3"] == 0.0

    no_solid = simulate_river_dominant_grid(
        terrain,
        boundary,
        (4, 2),
        outlets,
        [FluvialDeltaInterval((4, 2), 1000.0, 0.0)],
        config,
    )
    np.testing.assert_array_equal(no_solid["final_bed_m"], terrain.elevation_m)
    assert no_solid["sediment_budget"]["deposited_solid_m3"] == pytest.approx(0.0)
    assert no_solid["water_budget"]["retained_water_m3"] == pytest.approx(0.0)
    assert no_solid["water_budget"]["ocean_export_water_m3"] == pytest.approx(1000.0)


def test_grid_spatial_asymmetric_bed_reallocates_outlet_fractions():
    terrain, boundary = _spatial_asymmetric_terrain()
    outlets = [(1, 8), (3, 8)]
    config = _river_config(
        porosity=0.4,
        capacity_solid_per_water=0.02,
        max_deposit_depth_per_interval_m=0.05,
        marine_capacity_decay_per_m=0.0,
    )
    control_forcing = [
        FluvialDeltaInterval((2, 0), 500.0, 0.0),
        FluvialDeltaInterval((2, 0), 500.0, 0.0),
        FluvialDeltaInterval((2, 0), 500.0, 0.0),
    ]
    supplied_forcing = [
        FluvialDeltaInterval((2, 0), 500.0, 2.0),
        FluvialDeltaInterval((2, 0), 500.0, 2.0),
        FluvialDeltaInterval((2, 0), 500.0, 2.0),
    ]
    control = simulate_river_dominant_grid(
        terrain, boundary, (2, 0), outlets, control_forcing, config
    )
    supplied = simulate_river_dominant_grid(
        terrain, boundary, (2, 0), outlets, supplied_forcing, config
    )

    control_first = np.asarray(control["branch_history"][0]["branch_share"])
    control_last = np.asarray(control["branch_history"][-1]["branch_share"])
    np.testing.assert_allclose(control_first, control_last, atol=1e-12)

    supplied_first = np.asarray(supplied["branch_history"][0]["branch_share"])
    supplied_last = np.asarray(supplied["branch_history"][-1]["branch_share"])
    assert np.sum(np.abs(supplied_first - supplied_last)) > 1e-6

    for record in supplied["branch_history"]:
        assert np.count_nonzero(np.asarray(record["outlet_water_m3"]) > 0.0) >= 2
    # Measurable deposition occurred and stayed finite in the supplied case.
    assert supplied["sediment_budget"]["deposited_solid_m3"] > 0.0
    assert np.isfinite(supplied["final_bed_m"]).all()


def test_grid_duplicate_outlets_rejected():
    terrain, boundary = _river_terrain()
    forcing = [FluvialDeltaInterval((4, 2), 100.0, 1.0)]
    with pytest.raises(ValueError):
        simulate_river_dominant_grid(
            terrain,
            boundary,
            (4, 2),
            [(2, 14), (2, 14), (4, 14)],
            forcing,
            _river_config(),
        )


def test_grid_reentrainment_budget_separates_gross_deposit_from_net_storage():
    terrain, boundary = _river_terrain()
    before = terrain.elevation_m.copy()
    config = _river_config(max_reentrainment_depth_per_interval_m=.1)
    result = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), [(2, 14), (4, 14), (6, 14)],
        [FluvialDeltaInterval((4, 2), 500., 80.),
         FluvialDeltaInterval((4, 2), 500., 0.)], config)
    budget = result["sediment_budget"]
    assert budget["reentrained_solid_m3"] > 0.
    assert budget["deposited_solid_m3"] > budget["stored_solid_m3"]
    assert budget["stored_solid_m3"] == pytest.approx(
        budget["deposited_solid_m3"] - budget["reentrained_solid_m3"])
    bed_solid = float(np.sum(result["final_bed_m"] - before)
                      * terrain.cell_area_m2 * (1. - config.porosity))
    assert bed_solid == pytest.approx(budget["stored_solid_m3"], abs=1e-9)
    assert budget["input_solid_m3"] == pytest.approx(
        budget["stored_solid_m3"] + budget["ocean_export_solid_m3"]
        + budget["unresolved_solid_m3"], abs=1e-9)
    np.testing.assert_array_equal(terrain.elevation_m, before)


def test_grid_missing_or_extra_outlet_rejected():
    terrain, boundary = _river_terrain()
    forcing = [FluvialDeltaInterval((4, 2), 100.0, 1.0)]
    with pytest.raises(ValueError):
        simulate_river_dominant_grid(
            terrain, boundary, (4, 2), [(2, 14), (4, 14)], forcing, _river_config()
        )
    with pytest.raises(ValueError):
        simulate_river_dominant_grid(
            terrain,
            boundary,
            (4, 2),
            [(2, 14), (4, 14), (6, 14), (8, 14)],
            forcing,
            _river_config(),
        )
    with pytest.raises(ValueError):
        simulate_river_dominant_grid(
            terrain, boundary, (4, 2), [(2, 14), "bad", (6, 14)], forcing, _river_config()
        )


def test_grid_outlet_outside_export_mask_rejected():
    terrain, boundary = _river_terrain()
    forcing = [FluvialDeltaInterval((4, 2), 100.0, 1.0)]
    with pytest.raises(ValueError):
        simulate_river_dominant_grid(
            terrain, boundary, (4, 2), [(2, 13), (4, 14), (6, 14)], forcing, _river_config()
        )
    with pytest.raises(ValueError):
        simulate_river_dominant_grid(
            terrain, boundary, (4, 2), [(2, 14), (4, 14), (30, 14)], forcing, _river_config()
        )


def test_grid_forcing_inlet_mismatch_rejected():
    terrain, boundary = _river_terrain()
    forcing = [FluvialDeltaInterval((3, 2), 100.0, 1.0)]
    with pytest.raises(ValueError):
        simulate_river_dominant_grid(
            terrain, boundary, (4, 2), [(2, 14), (4, 14), (6, 14)], forcing, _river_config()
        )


def test_grid_above_head_stripe_is_not_crossed():
    bed = np.full((9, 15), 0.2, np.float64)
    bed[:, 10:] = -0.5
    bed[:, 7] = 3.0  # above river head of 2 m
    terrain = TerrainGrid(
        bed,
        np.ones(bed.shape, bool),
        0.0,
        0.0,
        10.0,
        10.0,
        "diagnostic_dem_proxy",
        "above-head",
        "d" * 64,
    )
    ocean = bed < 0.0
    exports = np.zeros(bed.shape, bool)
    for row in (2, 4, 6):
        exports[row, -1] = True
    boundary = FluvialDeltaBoundary(ocean, exports, 0.0, 2.0, "above-head-sea")
    forcing = [FluvialDeltaInterval((4, 2), 500.0, 80.0)]
    result = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), [(2, 14), (4, 14), (6, 14)], forcing, _river_config()
    )
    assert result["branch_history"][0]["ocean_export_water_m3"] == 0.0
    assert result["water_budget"]["retained_water_m3"] == pytest.approx(500.0)
    assert result["sediment_budget"]["unresolved_solid_m3"] == pytest.approx(80.0)
    blocked = np.zeros(bed.shape, bool)
    blocked[:, 7] = True
    for row in range(bed.shape[0]):
        assert bed[row, 7] == result["final_bed_m"][row, 7]
    for record in result["intervals"]:
        for edge in record["flow_edges"]:
            assert not blocked[edge["from_cell"]]
            assert not blocked[edge["to_cell"]]


def test_grid_all_no_export_no_sediment_stripe_is_not_crossed():
    bed = np.full((9, 15), 0.2, np.float64)
    bed[:, 10:] = -0.5
    valid = np.ones(bed.shape, bool)
    valid[:, 7] = False
    terrain = TerrainGrid(
        bed,
        valid,
        0.0,
        0.0,
        10.0,
        10.0,
        "diagnostic_dem_proxy",
        "full-height-block",
        "d" * 64,
    )
    ocean = bed < 0.0
    exports = np.zeros(bed.shape, bool)
    for row in (2, 4, 6):
        exports[row, -1] = True
    boundary = FluvialDeltaBoundary(ocean, exports, 0.0, 2.0, "full-height-sea")
    forcing = [FluvialDeltaInterval((4, 2), 500.0, 80.0)]
    result = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), [(2, 14), (4, 14), (6, 14)], forcing, _river_config()
    )
    blocked = np.zeros(bed.shape, bool)
    blocked[:, 7] = True
    assert result["branch_history"][0]["ocean_export_water_m3"] == 0.0
    assert result["water_budget"]["retained_water_m3"] == pytest.approx(500.0)
    assert result["sediment_budget"]["unresolved_solid_m3"] == pytest.approx(80.0)
    for record in result["intervals"]:
        for edge in record["flow_edges"]:
            assert not blocked[edge["from_cell"]]
            assert not blocked[edge["to_cell"]]


def test_grid_nonunit_cell_area_and_nonzero_porosity_volume_closure():
    bed = np.full((9, 15), 0.2, np.float64)
    bed[:, 10:] = -0.5
    terrain = TerrainGrid(
        bed,
        np.ones(bed.shape, bool),
        0.0,
        0.0,
        3.0,
        5.0,
        "diagnostic_dem_proxy",
        "nonunit-cell",
        "d" * 64,
    )
    ocean = bed < 0.0
    exports = np.zeros(bed.shape, bool)
    for row in (2, 4, 6):
        exports[row, -1] = True
    boundary = FluvialDeltaBoundary(ocean, exports, 0.0, 2.0, "nonunit-sea")
    outlets = [(2, 14), (4, 14), (6, 14)]
    forcing = [
        FluvialDeltaInterval((4, 2), 1000.0, 40.0),
        FluvialDeltaInterval((4, 2), 1000.0, 40.0),
    ]
    config = _river_config(porosity=0.5, capacity_solid_per_water=0.02)
    result = simulate_river_dominant_grid(
        terrain, boundary, (4, 2), outlets, forcing, config
    )
    bed_initial = terrain.elevation_m.copy()
    stored = np.asarray(result["spatial_result"]["stored_solid_m3"], dtype=float)
    expected_delta = stored / ((1.0 - config.porosity) * terrain.cell_area_m2)
    np.testing.assert_allclose(
        result["final_bed_m"] - terrain.elevation_m, expected_delta, atol=1e-12
    )
    # Independent per-interval bed-volume closure using the kernel stored array.
    for record, kernel_record in zip(result["branch_history"], result["intervals"]):
        kernel_stored = np.asarray(kernel_record["stored_solid_m3"], dtype=float)
        expected_bed = terrain.elevation_m + kernel_stored / (
            (1.0 - config.porosity) * terrain.cell_area_m2
        )
        np.testing.assert_allclose(record["bed_after_m"], expected_bed, atol=1e-12)
        solid_closure = float(
            np.sum((record["bed_after_m"] - terrain.elevation_m) * terrain.cell_area_m2 * (1.0 - config.porosity))
        )
        assert solid_closure == pytest.approx(float(kernel_stored.sum()), abs=1e-9)
    np.testing.assert_array_equal(terrain.elevation_m, bed_initial)
    # Outlet water and solid sums must equal the kernel's own ledger.
    rows = [cell[0] for cell in outlets]
    columns = [cell[1] for cell in outlets]
    for record, kernel_record in zip(result["branch_history"], result["intervals"]):
        water = np.asarray(kernel_record["water_throughput_m3"], dtype=float)
        solid = np.asarray(kernel_record["sediment_throughput_solid_m3"], dtype=float)
        np.testing.assert_allclose(
            float(np.sum(record["outlet_water_m3"])),
            float(np.sum(water[rows, columns])),
        )
        np.testing.assert_allclose(
            float(np.sum(record["outlet_solid_m3"])),
            float(np.sum(solid[rows, columns])),
        )
        np.testing.assert_allclose(
            float(np.sum(record["outlet_water_m3"])),
            float(kernel_record["water_ledger"]["ocean_export_m3"]),
        )
        np.testing.assert_allclose(
            float(np.sum(record["outlet_solid_m3"])),
            float(kernel_record["solid_ledger"]["ocean_export_solid_m3"]),
        )
    assert result["sediment_budget"]["solid_residual_m3"] == pytest.approx(0.0, abs=1e-9)
