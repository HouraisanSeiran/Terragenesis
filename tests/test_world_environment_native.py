"""Small finite mechanism tests, separate from real source acceptance."""

from copy import deepcopy

import numpy as np
import pytest
from test_world_glacier_metric import geometry

from terrain_pipeline import environment_processes as kernels
from terrain_pipeline import world_environment_native as native
from terrain_pipeline.common_infra import json_sha256


def source():
    bed = np.full((8, 8), -20.0)
    bed[3:5, 3:5] = 10.0
    return {
        "elevation_m": bed,
        "ocean_mask": bed < 0,
        "first_xz_m": [0.0, 0.0],
        "spacing_m": 2000.0,
        "world_seed": 20260903,
        "source_identity": "world",
        "plate_identity": "plate",
        "parent_terrain_revision": "r0",
    }


def packet(prepared, region, process, quantities, weights=None, begin=0.0, end=1800.0):
    nodes = np.asarray(region["coarse_nodes"]).ravel()
    row = {
        "schema": native.PACKET_SCHEMA,
        "process": process,
        "source_identity": "world",
        "parent_state_identity": "parent-state",
        "parent_terrain_revision": "r0",
        "support_global_ids": nodes.tolist(),
        "mapping_weights": (
            np.full(nodes.size, 1 / nodes.size) if weights is None else weights
        ).tolist(),
        "owner_from": "parent",
        "owner_to": region["id"],
        "interval_start_s": begin,
        "interval_end_s": end,
        "quantities": quantities,
        "source_debit": {"status": "debited", "account_id": "finite-stock"},
        "status": "in-flight",
        "consumed_by": None,
    }
    row["id"] = json_sha256(row)
    return row


def test_basin_diagonal_heat_and_water_conservation_cold_continuation():
    prepared = native.prepare(source(), config={"max_glaciers": 0, "max_coasts": 0})
    region = prepared["plans"][0]
    initial = deepcopy(prepared["state"])
    # Nonuniform actual heat proves advection rather than a diagnostic-only field.
    initial["basin-0"]["sensible_heat_j"][0, 0] *= 2
    forcing = {
        "regions": {"basin-0": {"wind_xz_m_s": [7.0, -3.0], "surface_heat_w_m2": 12.0}}
    }
    whole = native.advance(prepared, initial, forcing, time_edges_s=[0.0, 1800.0])
    first = native.advance(prepared, initial, forcing, time_edges_s=[0.0, 900.0])
    second = native.advance(
        prepared, deepcopy(first["state"]), forcing, time_edges_s=[900.0, 1800.0]
    )
    for key in ("volume_m3", "sensible_heat_j"):
        np.testing.assert_array_equal(
            whole["state"]["basin-0"][key], second["state"]["basin-0"][key]
        )
    ledger = whole["ledger"]["basin-0"]
    assert abs(ledger["water_residual_m3"]) < 1e-5
    assert abs(ledger["sensible_heat_residual_j"]) < 1000.0
    assert ledger["internal_water_transfer_m3"] > 0
    assert whole["statuses"]["basin-0"]["consumer_status"] == "pending-task03"
    assert np.array_equal(region["wet_mask"], prepared["plans"][0]["wet_mask"])
    np.testing.assert_array_equal(
        initial["basin-0"]["volume_m3"], prepared["state"]["basin-0"]["volume_m3"]
    )


def test_packet_debit_identity_replay_and_refusal_persist():
    prepared = native.prepare(source(), config={"max_glaciers": 0, "max_coasts": 0})
    region = prepared["plans"][0]
    weights = region["wet_mask"].ravel().astype(float)
    weights /= weights.sum()
    good = packet(
        prepared,
        region,
        "river_to_basin",
        {"water_m3": 50.0, "sensible_heat_j": 2e9},
        weights,
    )
    bad = deepcopy(good)
    bad["id"] = "bad"
    result = native.advance(
        prepared, None, {"packets": [good, bad]}, time_edges_s=[0.0, 1800.0]
    )
    assert result["accepted_packet_ids"] == [good["id"]]
    assert result["state"]["_exchange"]["refused_packets"][0]["id"] == "bad"
    assert result["ledger"]["basin-0"]["water_input_m3"] == 50.0
    with pytest.raises(ValueError, match="duplicate"):
        native.advance(
            prepared, None, {"packets": [good, good]}, time_edges_s=[0.0, 1800.0]
        )
    stale = native.advance(
        prepared, result["state"], {"packets": [good]}, time_edges_s=[1800.0, 3600.0]
    )
    assert not stale["accepted_packet_ids"]
    assert stale["refused_packets"][0]["reason"] == "exchange packet already consumed"


def coast_prepared():
    bed = np.tile(np.linspace(-2.0, 1.0, 8), (8, 1))
    ocean = bed < 0
    mouth = np.zeros_like(ocean)
    mouth[4, 5] = True
    context = {
        "height_m": bed,
        "spacing_m": 30.0,
        "origin_native_xz": [0, 0],
        "world_seed": 20260903,
        "valid_mask": np.ones_like(ocean),
        "protected_mask": np.zeros_like(ocean),
        "ocean_mask": ocean,
        "river_mask": mouth,
        "receiver": np.full(bed.shape, -1, np.int64),
    }
    region = {
        "id": "coast-0",
        "kind": "coast",
        "context": context,
        "coarse_nodes": np.zeros(bed.size, np.int64),
        "mapping_weights": np.full(bed.size, 900.0 / 4e6),
    }
    prepared = native.prepare(source(), config={"max_glaciers": 0, "max_coasts": 0})
    prepared["plans"] = [region]
    prepared["state"] = {
        "coast-0": {
            "core": kernels.initialize_coastal_exchange(
                context, mobile_thickness_m=0.0
            ),
            "physical_time_s": 0.0,
            "consumed_packet_ids": [],
            "accepted_packet_ids": [],
            "refused_packets": [],
            "pending_packets": [],
        }
    }
    return prepared, region


def test_prism_actual_tide_wave_finite_sand_and_cold_phase():
    prepared, region = coast_prepared()
    weights = np.ones(64) / 64
    sand = packet(
        prepared,
        region,
        "coast_initial_solid",
        {"solid_m3": 640.0},
        weights,
        end=45000.0,
    )
    drivers = {
        "wave_height_m": 1.0,
        "wave_direction_xz": [0.0, 1.0],
        "tide_phase_rad": 0.3,
    }
    whole = native.advance(
        prepared,
        None,
        {"packets": [sand], "regions": {"coast-0": drivers}},
        time_edges_s=[0.0, 45000.0],
    )
    no_wave = native.advance(
        prepared,
        None,
        {"packets": [sand], "regions": {"coast-0": dict(drivers, wave_height_m=0.0)}},
        time_edges_s=[0.0, 45000.0],
    )
    ledger = whole["ledger"]["coast-0"]
    assert abs(ledger["water_residual_m3"]) < 1e-6
    assert abs(ledger["salt_residual_kg"]) < 1e-4
    assert abs(ledger["solid_residual_m3"]) < 1e-6
    assert not np.array_equal(
        whole["state"]["coast-0"]["core"]["bed_solid_m3"],
        no_wave["state"]["coast-0"]["core"]["bed_solid_m3"],
    )
    short = packet(
        prepared,
        region,
        "coast_initial_solid",
        {"solid_m3": 640.0},
        weights,
        end=22500.0,
    )
    first = native.advance(
        prepared,
        None,
        {"packets": [short], "regions": {"coast-0": drivers}},
        time_edges_s=[0.0, 22500.0],
    )
    second = native.advance(
        prepared,
        deepcopy(first["state"]),
        {"regions": {"coast-0": drivers}},
        time_edges_s=[22500.0, 45000.0],
    )
    for key in ("water_m3", "salt_kg", "bed_solid_m3", "bed_m"):
        np.testing.assert_array_equal(
            whole["state"]["coast-0"]["core"][key],
            second["state"]["coast-0"]["core"][key],
        )


def test_native_glacier_requires_actual_snow_and_commits_finite_bed_once():
    prepared = native.prepare(source(), config={"max_glaciers": 0, "max_coasts": 0})
    g = geometry(thickness=0.0)
    region = {
        "id": "glacier-0",
        "kind": "glacier",
        "geometry": g,
        "coarse_nodes": np.zeros(48, np.int64),
        "mapping_weights": np.full(48, 1800.0 / 4e6),
    }
    prepared["plans"] = [region]
    prepared["state"] = {
        "glacier-0": {
            "core": None,
            "physical_time_s": 0.0,
            "consumed_packet_ids": [],
            "accepted_packet_ids": [],
            "refused_packets": [],
            "pending_packets": [],
        }
    }
    empty = native.advance(prepared, None, {}, time_edges_s=[0.0, 1800.0])
    assert empty["statuses"]["glacier-0"]["status"] == "pending-input"
    snow = packet(
        prepared, region, "snow_to_glacier", {"water_m3": 48 * 1800.0 * 80.0 * 0.917}
    )
    result = native.advance(
        prepared, None, {"packets": [snow]}, time_edges_s=[0.0, 1800.0]
    )
    assert result["accepted_packet_ids"] == [snow["id"]]
    assert result["bed_commit"]
    assert result["state"]["_exchange"]["pending_bed_commits"] == result["bed_commit"]
    assert any(
        row["process"] == "glacier_sediment_to_route" for row in result["packets_out"]
    )


def test_candidates_require_ten_year_evidence_and_native_real_descent():
    s = source()
    s["ocean_mask"][:] = False
    s["snow_history"] = {
        "years": 10,
        "years_with_perennial_snow": np.full((8, 8), 10),
        "min_perennial_swe_mm": np.full((8, 8), 20.0),
        "snow_swe_mm": np.full((8, 8), 40.0),
    }
    assert not native.plan(s, {"max_glaciers": 0, "max_coasts": 0})["candidates"]
    selected = native.plan(s, {"max_coasts": 0})
    assert len(selected["candidates"]) == 2
    s["rock_reserve_m"] = 2.0
    terrain = {
        "elevation_m": np.tile(3000.0 - np.arange(64) * 4.0, (64, 1)),
        "identity": "mechanism-only",
        "grid": {"first_sample_xz_m": [0.0, 0.0], "spacing_m": 30.0},
    }
    candidate = {
        "id": "glacier-mechanism",
        "kind": "glacier",
        "node": 0,
        "location_xz_m": [150.0, 150.0],
    }
    region = native._native_region(s, candidate, terrain, native._config(None))
    assert len(region["geometry"]["bed_m"]) >= 32
    assert np.all(np.diff(region["geometry"]["bed_m"]) < 0)
    terrain["elevation_m"][:] = 10.0
    with pytest.raises(ValueError, match="shorter than 32"):
        native._native_region(s, candidate, terrain, native._config(None))
    s["snow_history"]["years"] = 1
    assert native.plan(s)["statuses"]["glacier"]["status"] == "pending-snow-history"


def test_uncapped_climate_demand_repeats_without_historical_snowfall():
    region = {
        "geometry": geometry(),
        "snow_history": {
            "time_edges_s": np.arange(121) * 900.0,
            "potential_ablation_mm": np.full((120, 48), 4.0),
            "potential_sublimation_mm": np.full((120, 48), 0.2),
            "snow_melt_mm": np.zeros((120, 48)),
            "snowfall_mm": np.full((120, 48), 1000.0),
        },
    }
    result = native._snow_demand(
        region, np.array([0.0, 1800.0, 11700.0]), "potential_ablation_mm"
    )
    np.testing.assert_array_equal(result[0], np.full(48, 8.0))
    np.testing.assert_array_equal(result[1], np.full(48, 44.0))


def test_landlocked_native_negative_depression_is_not_external_ocean():
    s = source()
    s["ocean_mask"][:] = False
    terrain = {
        "elevation_m": np.full((64, 64), -2.0),
        "identity": "mechanism-only",
        "grid": {"first_sample_xz_m": [0.0, 0.0], "spacing_m": 30.0},
    }
    candidate = {
        "id": "coast-test",
        "kind": "coast",
        "node": 0,
        "location_xz_m": [900.0, 900.0],
    }
    with pytest.raises(ValueError, match="no known external sea"):
        native._native_region(s, candidate, terrain, native._config(None))


def test_existing_ice_can_be_selected_without_inventing_snow_history():
    s = source()
    s["initial_ice_water_m3"] = np.zeros((8, 8))
    s["initial_ice_water_m3"][3, 3] = 100.0
    result = native.plan(s, {"max_coasts": 0})
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["node"] == 27
    assert result["candidates"][0]["evidence"]["years"] == 0
