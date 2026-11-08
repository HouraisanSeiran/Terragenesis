"""Behavioral tests for route_daily_sediment public API."""

from __future__ import annotations

import numpy as np
import pytest

from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_upstream_sediment import (
    load_daily_sediment,
    route_daily_sediment,
    save_daily_sediment,
    validate_daily_sediment,
)


GEOM = "a" * 64
HYD = "b" * 64
PROV = "explicit"


def _material(sed_k: float, rock_k: float, ws: float = 0.0) -> MaterialParameters:
    return MaterialParameters(
        settling_velocity_m_s=ws,
        sediment_erodibility_m_s_pa=sed_k,
        rock_erodibility_m_s_pa=rock_k,
        provenance=PROV,
        transport_coefficient=1.0,
    )


def _base_args(n: int = 2):
    length_m = np.full(n, 10.0, dtype=np.float64)
    width_m = np.full(n, 10.0, dtype=np.float64)
    bed = np.array([10.0, 5.0, 0.0], dtype=np.float64)[:n]
    rock = bed - 10.0
    alluvium = np.zeros(n, dtype=np.float64)
    hardness = np.zeros(n, dtype=np.float64)
    water_depth = np.full((1, n), 2.0, dtype=np.float64)
    water_q = np.full((1, n), 1.0, dtype=np.float64)
    friction_slope = np.full((1, n), 0.01, dtype=np.float64)
    time_seconds = np.array([0.0, 86400.0], dtype=np.float64)
    receiver = np.array([-1, -1, -1], dtype=np.int64)[:n]
    if n == 1:
        receiver = np.array([-1], dtype=np.int64)
    elif n == 2:
        receiver = np.array([1, -1], dtype=np.int64)
    else:
        receiver = np.array([2, 2, -1], dtype=np.int64)[:n]
    return dict(
        receiver=receiver,
        length_m=length_m,
        width_m=width_m,
        bed_elevation_m=bed,
        rock_floor_m=rock,
        initial_alluvium_bulk_m3=alluvium,
        hardness=hardness,
        water_depth_m=water_depth,
        water_q_m3_s=water_q,
        friction_slope=friction_slope,
        time_seconds=time_seconds,
        geometry_identity_sha256=GEOM,
        hydraulic_identity_sha256=HYD,
        material_provenance=PROV,
    )


def test_rock_hardness_controls_erosion_magnitude():
    args = _base_args(1)
    args["bed_elevation_m"] = np.array([100.0])
    args["rock_floor_m"] = np.array([90.0])
    args["hardness"] = np.array([0.0])
    soft = route_daily_sediment(**args, material=_material(0.0, 1e-7))
    args["hardness"] = np.array([0.75])
    hard = route_daily_sediment(**args, material=_material(0.0, 1e-7))
    soft_rock = float(soft["arrays"]["eroded_rock_m3"].sum())
    hard_rock = float(hard["arrays"]["eroded_rock_m3"].sum())
    assert soft_rock > 0.0
    assert hard_rock < soft_rock
    assert hard_rock >= 0.0


def test_rock_exhausts_finite_reserve_then_stops():
    args = _base_args(1)
    args["bed_elevation_m"] = np.array([0.0])
    args["rock_floor_m"] = np.array([-0.001])
    args["length_m"] = np.array([1.0])
    args["width_m"] = np.array([1.0])
    args["time_seconds"] = np.array([0.0, 86400.0, 172800.0])
    args["water_depth_m"] = np.full((2, 1), 2.0)
    args["water_q_m3_s"] = np.full((2, 1), 1.0)
    args["friction_slope"] = np.full((2, 1), 0.01)
    args["initial_alluvium_bulk_m3"] = np.array([0.0])
    result = route_daily_sediment(**args, material=_material(0.0, 1.0))
    arrays = result["arrays"]
    removed = float(arrays["eroded_rock_m3"].sum())
    assert removed == pytest.approx(0.001, rel=1e-6, abs=1e-9)
    assert float(arrays["eroded_rock_m3"][1, 0]) == 0.0


def test_loose_cover_blocks_rock_then_limits_removal():
    args = _base_args(1)
    args["bed_elevation_m"] = np.array([10.0])
    args["rock_floor_m"] = np.array([-100.0])
    args["initial_alluvium_bulk_m3"] = np.array([10.0])
    blocked = route_daily_sediment(**args, material=_material(0.0, 1e-6))
    assert float(blocked["arrays"]["eroded_rock_m3"].sum()) == 0.0

    args2 = _base_args(1)
    args2["bed_elevation_m"] = np.array([10.0])
    args2["rock_floor_m"] = np.array([-100.0])
    args2["initial_alluvium_bulk_m3"] = np.array([1.0])
    moved = route_daily_sediment(**args2, material=_material(1.0, 1e-6))
    arrays = moved["arrays"]
    loose_removed = float(arrays["eroded_loose_solid_m3"].sum())
    rock_removed = float(arrays["eroded_rock_m3"].sum())
    assert loose_removed > 0.0
    assert rock_removed > 0.0


def test_confluence_no_double_count_and_held_mobile_export():
    args = _base_args(3)
    args["receiver"] = np.array([2, 2, -1], dtype=np.int64)
    args["time_seconds"] = np.array([0.0, 10.0])
    args["water_depth_m"] = np.full((1, 3), 2.0)
    args["water_q_m3_s"] = np.full((1, 3), 1.0)
    args["friction_slope"] = np.full((1, 3), 0.01)
    external = np.array([[1.0, 2.0, 0.0]])
    result = route_daily_sediment(
        **args, material=_material(0.0, 0.0), external_solid_m3_s=external
    )
    arrays = result["arrays"]
    exported = float(arrays["exported_solid_m3"].sum())
    incoming = arrays["incoming_solid_m3"]
    assert exported == pytest.approx(30.0, rel=1e-6)
    assert float(incoming[0, 2]) == pytest.approx(30.0, rel=1e-6)

    args2 = _base_args(1)
    args2["bed_elevation_m"] = np.array([10.0])
    args2["rock_floor_m"] = np.array([0.0])
    args2["water_q_m3_s"] = np.array([[0.0]])
    args2["time_seconds"] = np.array([0.0, 10.0])
    external2 = np.array([[1.0]])
    held = route_daily_sediment(
        **args2, material=_material(0.0, 0.0, ws=0.0), external_solid_m3_s=external2
    )
    held_arrays = held["arrays"]
    assert float(held_arrays["exported_solid_m3"].sum()) == 0.0
    assert float(held_arrays["trace_mobile_solid_m3"][-1, 0]) == pytest.approx(10.0, rel=1e-6)


def test_retention_fraction_reduces_delivery_and_deposits():
    args = _base_args(2)
    args["receiver"] = np.array([1, -1], dtype=np.int64)
    args["time_seconds"] = np.array([0.0, 10.0])
    args["water_depth_m"] = np.full((1, 2), 2.0)
    args["water_q_m3_s"] = np.full((1, 2), 1.0)
    args["friction_slope"] = np.full((1, 2), 0.01)
    external = np.array([[10.0, 0.0]])

    result = route_daily_sediment(
        **args,
        material=_material(0.0, 0.0),
        external_solid_m3_s=external,
        retention_fraction=np.array([0.5, 0.0]),
    )
    arrays = result["arrays"]
    assert float(arrays["exported_solid_m3"].sum()) == pytest.approx(50.0, rel=1e-6)
    deposit = float(arrays["deposited_solid_m3"].sum())
    assert deposit > 0.0

    area = float(args["length_m"][0] * args["width_m"][0])
    bed_gain = float(
        arrays["trace_bed_m"][-1, 0] - arrays["trace_bed_m"][0, 0]
    )
    porosity = 0.35
    expected = bed_gain * area * (1.0 - porosity)
    assert deposit == pytest.approx(expected, rel=1e-6)


def test_dry_holds_mobile_solid():
    args = _base_args(1)
    args["bed_elevation_m"] = np.array([10.0])
    args["rock_floor_m"] = np.array([0.0])
    args["water_q_m3_s"] = np.array([[0.0]])
    args["time_seconds"] = np.array([0.0, 10.0])
    external = np.array([[1.0]])
    result = route_daily_sediment(
        **args, material=_material(0.0, 0.0, ws=0.0), external_solid_m3_s=external
    )
    arrays = result["arrays"]
    assert float(arrays["exported_solid_m3"].sum()) == 0.0
    assert float(arrays["trace_mobile_solid_m3"][-1, 0]) == pytest.approx(10.0, rel=1e-6)


def test_deterministic_save_load_and_tamper_validation(tmp_path):
    args = _base_args(2)
    args["time_seconds"] = np.array([0.0, 10.0])
    args["water_depth_m"] = np.full((1, 2), 2.0)
    args["water_q_m3_s"] = np.full((1, 2), 1.0)
    args["friction_slope"] = np.full((1, 2), 0.01)
    material = _material(0.0, 0.0)

    first = route_daily_sediment(**args, material=material)
    second = route_daily_sediment(**args, material=material)
    assert first["identity_sha256"] == second["identity_sha256"]

    path = tmp_path / "s.npz"
    save_daily_sediment(path, first)
    reloaded = load_daily_sediment(path, expected_sha256=file_sha256(path))
    assert reloaded["identity_sha256"] == first["identity_sha256"]

    tampered = {
        "arrays": {k: v.copy() for k, v in first["arrays"].items()},
        "metadata": dict(first["metadata"]),
    }
    tampered["arrays"]["outgoing_solid_m3"] = (
        tampered["arrays"]["outgoing_solid_m3"] + 1.0
    )
    tampered["identity_sha256"] = identity(tampered["arrays"], tampered["metadata"])
    with pytest.raises(ValueError):
        validate_daily_sediment(tampered)
