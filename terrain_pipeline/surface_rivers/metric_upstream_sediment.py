"""Daily quasi-steady DAG sediment routing adapter. Schema: daily-upstream-sediment-v1."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict

import numpy as np

from terrain_pipeline.channel_geometry import validate_receiver_acyclic
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_bed_update import bed_from_inventory
from terrain_pipeline.common_infra import identity, save_bundle, load_bundle

SCHEMA = "daily-upstream-sediment-v1"
G = 9.81
RHO = 1000.0

def _finite(name, arr, shape):
    if arr.shape != shape:
        raise ValueError(f"{name} shape {arr.shape} != {shape}")
    if arr.dtype != np.float64:
        raise ValueError(f"{name} must be float64")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be finite")

def route_daily_sediment(
    *,
    receiver,
    length_m,
    width_m,
    bed_elevation_m,
    water_depth_m,
    water_q_m3_s,
    friction_slope,
    time_seconds,
    rock_floor_m,
    initial_alluvium_bulk_m3,
    hardness,
    material: MaterialParameters,
    external_solid_m3_s=None,
    initial_mobile_solid_m3=None,
    geometry_identity_sha256: str,
    hydraulic_identity_sha256: str,
    material_provenance: str,
    retention_fraction=None,
) -> Dict[str, Any]:
    if not isinstance(material, MaterialParameters):
        raise TypeError("material must be MaterialParameters")
    sedcrit = float(material.sediment_critical_shear_pa)
    sedK = float(material.sediment_erodibility_m_s_pa)
    rockcrit = float(material.rock_critical_shear_pa)
    rockK = float(material.rock_erodibility_m_s_pa)
    transport_coefficient = float(material.transport_coefficient)
    settling_velocity = float(material.settling_velocity_m_s)
    p = float(material.porosity)
    if not isinstance(material_provenance, str) or material_provenance == "":
        raise ValueError("material_provenance must be nonempty str")

    if not isinstance(receiver, np.ndarray) or receiver.ndim != 1:
        raise ValueError("receiver must be 1-D ndarray")
    if receiver.dtype != np.int64:
        raise ValueError("receiver must be int64")
    n = receiver.shape[0]
    if n < 1:
        raise ValueError("n must be >= 1")
    if n > 2048:
        raise ValueError("n must be <= 2048")
    if np.any((receiver < -1) | (receiver >= n)):
        raise ValueError("receiver range invalid")
    receiver = np.ascontiguousarray(receiver, dtype=np.int64)
    length_m = np.ascontiguousarray(length_m, dtype=np.float64)
    width_m = np.ascontiguousarray(width_m, dtype=np.float64)
    bed_elevation_m = np.ascontiguousarray(bed_elevation_m, dtype=np.float64)
    water_depth_m = np.ascontiguousarray(water_depth_m, dtype=np.float64)
    water_q_m3_s = np.ascontiguousarray(water_q_m3_s, dtype=np.float64)
    friction_slope = np.ascontiguousarray(friction_slope, dtype=np.float64)
    time_seconds = np.ascontiguousarray(time_seconds, dtype=np.float64)
    rock_floor_m = np.ascontiguousarray(rock_floor_m, dtype=np.float64)
    initial_alluvium_bulk_m3 = np.ascontiguousarray(initial_alluvium_bulk_m3, dtype=np.float64)
    hardness = np.ascontiguousarray(hardness, dtype=np.float64)

    k = time_seconds.shape[0] - 1
    if k < 1 or k > 366:
        raise ValueError("k must be in [1,366]")

    validate_receiver_acyclic(receiver)

    _finite("length_m", length_m, (n,))
    _finite("width_m", width_m, (n,))
    _finite("bed_elevation_m", bed_elevation_m, (n,))
    _finite("rock_floor_m", rock_floor_m, (n,))
    _finite("initial_alluvium_bulk_m3", initial_alluvium_bulk_m3, (n,))
    _finite("hardness", hardness, (n,))
    _finite("water_depth_m", water_depth_m, (k, n))
    _finite("water_q_m3_s", water_q_m3_s, (k, n))
    _finite("friction_slope", friction_slope, (k, n))
    _finite("time_seconds", time_seconds, (k + 1,))

    if np.any(length_m <= 0.0) or np.any(width_m <= 0.0):
        raise ValueError("length_m/width_m must be positive")
    if np.any(np.diff(time_seconds) <= 0.0):
        raise ValueError("time_seconds must strictly increase")
    if np.any(hardness < 0.0) or np.any(hardness > 1.0):
        raise ValueError("hardness in [0,1]")
    if np.any(initial_alluvium_bulk_m3 < 0.0):
        raise ValueError("initial_alluvium must be nonnegative")
    if np.any(water_depth_m < 0.0) or np.any(water_q_m3_s < 0.0) or np.any(friction_slope < 0.0):
        raise ValueError("hydraulic fields must be nonnegative")

    area = width_m * length_m

    rock_floor_m = rock_floor_m.copy()
    bed_elevation_m = bed_elevation_m.copy()

    initial_loose_solid = initial_alluvium_bulk_m3 * (1.0 - p)

    rock_reserve = (bed_elevation_m - initial_alluvium_bulk_m3 / area - rock_floor_m) * area
    if np.any(rock_reserve < -1e-9 * area):
        raise ValueError("rock reserve negative")
    # Reconstruction of an exhausted reserve can round a few ulps below zero.
    rock_reserve = np.maximum(rock_reserve, 0.)

    if external_solid_m3_s is None:
        external_solid_m3_s = np.zeros((k, n), dtype=np.float64)
    else:
        external_solid_m3_s = np.ascontiguousarray(external_solid_m3_s, dtype=np.float64)
        _finite("external_solid_m3_s", external_solid_m3_s, (k, n))
        if np.any(external_solid_m3_s < 0.0):
            raise ValueError("external_solid_m3_s nonnegative")

    if retention_fraction is None:
        retention_fraction = np.zeros(n, dtype=np.float64)
    else:
        retention_fraction = np.ascontiguousarray(retention_fraction, dtype=np.float64)
        _finite("retention_fraction", retention_fraction, (n,))
        if np.any(retention_fraction < 0.0) or np.any(retention_fraction > 1.0):
            raise ValueError("retention_fraction in [0,1]")

    if initial_mobile_solid_m3 is None:
        mobile0 = np.zeros(n, dtype=np.float64)
    else:
        mobile0 = np.ascontiguousarray(initial_mobile_solid_m3, dtype=np.float64)
        _finite("initial_mobile_solid_m3", mobile0, (n,))
        if np.any(mobile0 < 0.0):
            raise ValueError("initial_mobile_solid_m3 nonnegative")

    rock_tau = rockcrit * (1.0 + 4.0 * hardness)
    rock_K = rockK * (1.0 - hardness) ** 2
    rho_g = RHO * G

    topo = []
    indeg = np.zeros(n, dtype=np.int64)
    for i in range(n):
        r = int(receiver[i])
        if r >= 0:
            indeg[r] += 1
    stack = [i for i in range(n) if indeg[i] == 0]
    while stack:
        i = stack.pop()
        topo.append(i)
        r = int(receiver[i])
        if r >= 0:
            indeg[r] -= 1
            if indeg[r] == 0:
                stack.append(r)
    if len(topo) != n:
        raise ValueError("receiver DAG contains a cycle")

    loose = initial_loose_solid.copy()
    loose0 = initial_loose_solid.copy()
    mobile_trace_copy = mobile0.copy()
    rock_removed_cum = np.zeros(n, dtype=np.float64)

    incoming_rec = np.zeros((k, n), dtype=np.float64)
    external_rec = np.zeros((k, n), dtype=np.float64)
    eroded_loose_rec = np.zeros((k, n), dtype=np.float64)
    eroded_rock_rec = np.zeros((k, n), dtype=np.float64)
    deposited_rec = np.zeros((k, n), dtype=np.float64)
    outgoing_rec = np.zeros((k, n), dtype=np.float64)
    exported_rec = np.zeros((k, n), dtype=np.float64)
    shear_rec = np.zeros((k, n), dtype=np.float64)
    capacity_rec = np.zeros((k, n), dtype=np.float64)

    mobile_trace = np.zeros((k + 1, n), dtype=np.float64)
    loose_trace = np.zeros((k + 1, n), dtype=np.float64)
    rockremoved_trace = np.zeros((k + 1, n), dtype=np.float64)
    bed_trace = np.zeros((k + 1, n), dtype=np.float64)
    mobile_trace[0] = mobile0
    loose_trace[0] = loose
    bed_trace[0] = bed_elevation_m.copy()

    total_external = 0.0
    total_exported = 0.0
    total_rock_eroded = 0.0

    mobile = mobile0.copy()

    for j in range(k):
        dt = float(time_seconds[j + 1] - time_seconds[j])
        incoming = np.zeros(n, dtype=np.float64)
        eroded_loose_step = np.zeros(n, dtype=np.float64)
        eroded_rock_step = np.zeros(n, dtype=np.float64)
        deposited_step = np.zeros(n, dtype=np.float64)
        outgoing_step = np.zeros(n, dtype=np.float64)
        exported_step = np.zeros(n, dtype=np.float64)

        for i in topo:
            h = float(water_depth_m[j, i])
            q = float(water_q_m3_s[j, i])
            sf = float(friction_slope[j, i])
            area_i = float(area[i])
            w = float(width_m[i])
            L = float(length_m[i])
            ext_rate = float(external_solid_m3_s[j, i])

            avail = mobile[i] + incoming[i] + ext_rate * dt
            total_external += ext_rate * dt
            if avail < 0.0:
                raise ValueError("negative available inventory")

            if h <= 0.0 or q <= 0.0:
                # dry: keep mobile, no erosion, no movement
                mobile[i] = avail
                continue

            R = w * h / (w + 2.0 * h)
            tau = rho_g * R * sf
            shear_rec[j, i] = tau

            excess = tau - sedcrit
            if excess < 0.0:
                excess = 0.0
            cap_rate = transport_coefficient * w * excess ** 1.5
            cap_vol = cap_rate * dt
            capacity_rec[j, i] = cap_vol

            deficit = cap_vol - avail
            if deficit < 0.0:
                deficit = 0.0

            # loose priority
            ero_loose = 0.0
            if deficit > 0.0 and loose[i] > 0.0:
                rate_vol = area_i * sedK * excess * (1.0 - p) * dt
                ero_loose = min(loose[i], deficit, rate_vol)
                if ero_loose < 0.0:
                    ero_loose = 0.0
                loose[i] -= ero_loose
                if loose[i] <= 0.0:
                    loose[i] = 0.0

            # rock only when loose fully exhausted
            ero_rock = 0.0
            if deficit > 0.0 and loose[i] <= 0.0:
                remaining = deficit - ero_loose
                if remaining > 0.0:
                    rt = tau - rock_tau[i]
                    if rt > 0.0:
                        rrate = area_i * rock_K[i] * rt * dt
                        ero_rock = min(remaining, rrate)
                        if ero_rock < 0.0:
                            ero_rock = 0.0
                        remaining_reserve = rock_reserve[i] - rock_removed_cum[i]
                        if ero_rock > remaining_reserve:
                            ero_rock = remaining_reserve
                        rock_removed_cum[i] += ero_rock

            eroded_loose_step[i] = ero_loose
            eroded_rock_step[i] = ero_rock
            avail += ero_loose + ero_rock

            potential = min(avail, cap_vol)
            if potential < 0.0:
                potential = 0.0

            velocity = q / (w * h) if (w * h) > 0.0 else 0.0
            if velocity > 0.0:
                arg = -settling_velocity * L / (velocity * h)
                if arg < -700.0:
                    arg = -700.0
                survive = float(np.exp(arg))
            else:
                survive = 0.0
            survive *= (1.0 - float(retention_fraction[i]))

            outgoing = potential * survive
            if outgoing < 0.0:
                outgoing = 0.0
            deposited = avail - outgoing
            if deposited < 0.0:
                deposited = 0.0

            loose[i] += deposited
            deposited_step[i] = deposited
            outgoing_step[i] = outgoing

            r = int(receiver[i])
            if r >= 0:
                incoming[r] += outgoing
            else:
                exported_step[i] = outgoing
                total_exported += outgoing

            mobile[i] = 0.0

        incoming_rec[j] = incoming
        external_rec[j] = external_solid_m3_s[j] * dt
        eroded_loose_rec[j] = eroded_loose_step
        eroded_rock_rec[j] = eroded_rock_step
        deposited_rec[j] = deposited_step
        outgoing_rec[j] = outgoing_step
        exported_rec[j] = exported_step

        mobile_trace[j + 1] = mobile
        loose_trace[j + 1] = loose
        rockremoved_trace[j + 1] = rock_removed_cum
        bed_trace[j + 1] = bed_from_inventory(
            bed_elevation_m, loose0, loose, rock_removed_cum, area, p
        )

        total_rock_eroded += float(np.sum(eroded_rock_step))

    # global ledger
    init_total = float(np.sum(loose0) + np.sum(mobile0) + total_external)
    final_total = float(np.sum(loose) + np.sum(mobile) + total_exported)
    scale = max(1.0, abs(init_total), abs(final_total))
    residual = init_total + total_rock_eroded - final_total
    if abs(residual) > 1e-9 * scale:
        raise ValueError(f"global sediment ledger residual {residual}")

    dt_arr = np.diff(time_seconds)[:, None]
    daily_Qs = outgoing_rec / dt_arr
    with np.errstate(divide="ignore", invalid="ignore"):
        Qs_over_Q = np.divide(
            daily_Qs, water_q_m3_s, out=np.zeros_like(daily_Qs), where=water_q_m3_s > 0.0
        )

    arrays: Dict[str, Any] = {
        "receiver": receiver.copy(),
        "length_m": length_m.copy(),
        "width_m": width_m.copy(),
        "area_m2": area.copy(),
        "bed_elevation_m": bed_elevation_m.copy(),
        "rock_floor_m": rock_floor_m.copy(),
        "water_depth_m": water_depth_m.copy(),
        "water_q_m3_s": water_q_m3_s.copy(),
        "friction_slope": friction_slope.copy(),
        "time_seconds": time_seconds.copy(),
        "hardness_source": hardness.copy(),
        "initial_alluvium_bulk_m3": initial_alluvium_bulk_m3.copy(),
        "initial_mobile_solid_m3": mobile_trace_copy,
        "retention_fraction": retention_fraction.copy(),
        "external_solid_m3_s": external_solid_m3_s.copy(),
        "incoming_solid_m3": incoming_rec,
        "external_solid_m3": external_rec,
        "eroded_loose_solid_m3": eroded_loose_rec,
        "eroded_rock_m3": eroded_rock_rec,
        "deposited_solid_m3": deposited_rec,
        "outgoing_solid_m3": outgoing_rec,
        "exported_solid_m3": exported_rec,
        "shear_stress_pa": shear_rec,
        "capacity_solid_m3_s": capacity_rec / dt_arr,
        "capacity_solid_m3": capacity_rec,
        "trace_mobile_solid_m3": mobile_trace,
        "trace_loose_solid_m3": loose_trace,
        "trace_rock_removed_m3": rockremoved_trace,
        "trace_bed_m": bed_trace,
        "qs_solid_m3_s": daily_Qs,
        "concentration_solid_m3_per_water_m3": Qs_over_Q,
    }

    material_dict = (
        dataclasses.asdict(material) if dataclasses.is_dataclass(material) else dict(material.__dict__)
    )

    metadata: Dict[str, Any] = {
        "schema": SCHEMA,
        "units": {
            "length": "m", "time": "s", "volume": "m3", "rate": "m3/s",
            "shear": "Pa", "solid_volume": "m3",
        },
        "scenario": {
            "n": int(n), "k": int(k), "terminal_policy": "open_export",
        },
        "global_residual": float(residual),
        "frozen_water": True,
        "hydraulic_ready": False,
        "publishable": False,
        "needs_revalidation": bool(np.any(bed_trace != bed_elevation_m)),
        "geometry_identity_sha256": geometry_identity_sha256,
        "hydraulic_identity_sha256": hydraulic_identity_sha256,
        "material_provenance": material_provenance,
        "material": material_dict,
        "terminals_open": True,
    }

    bundle: Dict[str, Any] = {
        "arrays": arrays,
        "metadata": metadata,
        "identity_sha256": identity(arrays, metadata),
    }

    validate_daily_sediment(bundle)

    return bundle

def validate_daily_sediment(bundle: Dict[str, Any]) -> None:
    if not isinstance(bundle, dict):
        raise ValueError("bundle must be dict")
    if "arrays" not in bundle or "metadata" not in bundle:
        raise ValueError("bundle missing arrays/metadata")
    arrays = bundle["arrays"]
    metadata = bundle["metadata"]
    if "identity_sha256" not in bundle:
        raise ValueError("missing identity_sha256")
    if bundle["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("identity mismatch")

    m = metadata
    if m.get("schema") != SCHEMA:
        raise ValueError("schema mismatch")
    for key in ("frozen_water", "hydraulic_ready", "publishable", "needs_revalidation"):
        if not isinstance(m.get(key), bool):
            raise ValueError(f"{key} must be bool")
    if not isinstance(m.get("geometry_identity_sha256"), str) or not m["geometry_identity_sha256"]:
        raise ValueError("geometry_identity_sha256 invalid")
    source_hash64 = m.get("hydraulic_identity_sha256")
    if not isinstance(source_hash64, str) or len(source_hash64) != 64:
        raise ValueError("source hash64 invalid")
    if not isinstance(m.get("material_provenance"), str) or m["material_provenance"] == "":
        raise ValueError("material_provenance must be nonempty str")
    if not isinstance(m.get("global_residual"), float) and not isinstance(m.get("global_residual"), int):
        raise ValueError("global_residual missing")

    n = int(m["scenario"]["n"])
    k = int(m["scenario"]["k"])

    receiver = arrays["receiver"]
    if receiver.shape != (n,) or receiver.dtype != np.int64:
        raise ValueError("receiver schema")
    if np.any(receiver < -1) or np.any(receiver >= n):
        raise ValueError("receiver range")
    validate_receiver_acyclic(receiver)

    time_seconds = arrays["time_seconds"]
    if (time_seconds.shape != (k + 1,) or time_seconds.dtype != np.float64
            or not np.isfinite(time_seconds).all() or np.any(np.diff(time_seconds) <= 0.)):
        raise ValueError("time_seconds shape")

    vec_names = (
        "length_m", "width_m", "area_m2", "bed_elevation_m", "rock_floor_m",
        "hardness_source", "initial_alluvium_bulk_m3", "initial_mobile_solid_m3",
        "retention_fraction",
    )
    for name in vec_names:
        a = arrays[name]
        if a.shape != (n,) or a.dtype != np.float64 or not np.all(np.isfinite(a)):
            raise ValueError(f"{name} schema")

    mat_names = (
        "water_depth_m", "water_q_m3_s", "friction_slope", "external_solid_m3_s",
        "incoming_solid_m3", "external_solid_m3", "eroded_loose_solid_m3",
        "eroded_rock_m3", "deposited_solid_m3", "outgoing_solid_m3",
        "exported_solid_m3", "shear_stress_pa", "capacity_solid_m3",
        "capacity_solid_m3_s", "qs_solid_m3_s", "concentration_solid_m3_per_water_m3",
    )
    for name in mat_names:
        a = arrays[name]
        if a.shape != (k, n) or a.dtype != np.float64 or not np.all(np.isfinite(a)):
            raise ValueError(f"{name} shape/dtype")

    for name in ("trace_mobile_solid_m3", "trace_loose_solid_m3",
                 "trace_rock_removed_m3", "trace_bed_m"):
        a = arrays[name]
        if a.shape != (k + 1, n) or a.dtype != np.float64 or not np.all(np.isfinite(a)):
            raise ValueError(f"{name} shape")

    for name in mat_names:
        if np.any(arrays[name] < -1e-9):
            raise ValueError(f"{name} negative")

    for name in ("trace_mobile_solid_m3", "trace_loose_solid_m3", "trace_rock_removed_m3"):
        if np.any(arrays[name] < -1e-9):
            raise ValueError(f"{name} negative")

    p = float(metadata["material"]["porosity"])
    if (not np.allclose(arrays["trace_loose_solid_m3"][0], arrays["initial_alluvium_bulk_m3"] * (1. - p), rtol=1e-12, atol=1e-10)
            or not np.allclose(arrays["trace_mobile_solid_m3"][0], arrays["initial_mobile_solid_m3"], rtol=1e-12, atol=1e-10)
            or np.any(arrays["trace_rock_removed_m3"][0] != 0.)):
        raise ValueError("initial inventory trace mismatch")
    if not np.allclose(np.diff(arrays["trace_rock_removed_m3"], axis=0), arrays["eroded_rock_m3"], rtol=1e-9, atol=1e-9):
        raise ValueError("per-step cumulative rock mismatch")
    expected_export = np.where(receiver[None, :] == -1, arrays["outgoing_solid_m3"], 0.)
    if not np.allclose(arrays["exported_solid_m3"], expected_export, rtol=1e-9, atol=1e-9):
        raise ValueError("terminal export relation mismatch")
    if not np.allclose(arrays["external_solid_m3"], arrays["external_solid_m3_s"] * np.diff(time_seconds)[:, None], rtol=1e-9, atol=1e-9):
        raise ValueError("external rate/time volume mismatch")

    if np.any(arrays["water_q_m3_s"] > 0.0) and not np.all(arrays["water_depth_m"][arrays["water_q_m3_s"] > 0.0] > 0.0):
        raise ValueError("hydraulic q > 0 requires depth > 0")

    # capacity bound
    cap = arrays["capacity_solid_m3"]
    out = arrays["outgoing_solid_m3"]
    if np.any(out > cap + 1e-9 * np.maximum(1.0, cap)):
        raise ValueError("outgoing exceeds capacity")

    # receiver incoming relation
    for j in range(k):
        inc_check = np.zeros(n, dtype=np.float64)
        for i in range(n):
            r = int(receiver[i])
            if r >= 0:
                inc_check[r] += out[j, i]
        if not np.allclose(inc_check, arrays["incoming_solid_m3"][j], rtol=1e-9, atol=1e-9):
            raise ValueError("incoming/outgoing relation mismatch")

    # local ledger per step
    loose_prev = arrays["trace_loose_solid_m3"][: k]
    loose_next = arrays["trace_loose_solid_m3"][1:]
    ero_l = arrays["eroded_loose_solid_m3"]
    dep = arrays["deposited_solid_m3"]
    dloose = (loose_next - loose_prev) - (dep - ero_l)
    if np.any(np.abs(dloose) > 1e-6 * np.maximum(1.0, np.abs(loose_prev)) + 1e-9):
        raise ValueError("loose trace ledger mismatch")

    # per-node mobile ledger per step
    mob_prev = arrays["trace_mobile_solid_m3"][: k]
    mob_next = arrays["trace_mobile_solid_m3"][1:]
    inc_s = arrays["incoming_solid_m3"]
    ext_s = arrays["external_solid_m3"]
    ero_r = arrays["eroded_rock_m3"]
    dmob = (mob_next - mob_prev) - (inc_s + ext_s + ero_l + ero_r - out - dep)
    if not np.allclose(dmob, 0.0, rtol=1e-9, atol=1e-8):
        raise ValueError("mobile trace ledger mismatch")

    # global ledger
    loose0_bulk = arrays["initial_alluvium_bulk_m3"]
    mob0 = arrays["initial_mobile_solid_m3"]
    m = metadata["material"]
    p = float(m["porosity"])
    ext_total = float(np.sum(arrays["external_solid_m3"]))
    exported_total = float(np.sum(arrays["exported_solid_m3"]))
    rock_removed_total = float(np.sum(arrays["eroded_rock_m3"]))
    loose_f = arrays["trace_loose_solid_m3"][k]
    mob_f = arrays["trace_mobile_solid_m3"][k]
    init_total = float(np.sum(loose0_bulk) * (1.0 - p) + np.sum(mob0) + ext_total)
    final_total = float(np.sum(loose_f) + np.sum(mob_f) + exported_total)
    scale = max(1.0, abs(init_total), abs(final_total))
    if abs(init_total + rock_removed_total - final_total) > 1e-9 * scale:
        raise ValueError("global ledger mismatch")

    cum_rock = arrays["trace_rock_removed_m3"][k]
    if not np.allclose(cum_rock, np.cumsum(arrays["eroded_rock_m3"], axis=0)[-1], rtol=1e-9, atol=1e-9):
        raise ValueError("rock removed cumulative mismatch")

    bed_check = arrays["trace_bed_m"]
    if bed_check.shape[0] < 1:
        raise ValueError("trace_bed_m empty")
    if not np.allclose(bed_check[0], arrays["bed_elevation_m"], rtol=1e-9, atol=1e-9):
        raise ValueError("bed trace initial mismatch")

    # reserve bound
    bed = arrays["bed_elevation_m"]
    floor = arrays["rock_floor_m"]
    area = arrays["area_m2"]
    reserve = (bed - arrays["initial_alluvium_bulk_m3"] / area - floor) * area
    if np.any(reserve < -1e-9 * area):
        raise ValueError("rock reserve negative")
    reserve = np.maximum(reserve, 0.)
    if np.any(arrays["trace_rock_removed_m3"][k] > reserve + 1e-9):
        raise ValueError("rock removed exceeds reserve")

    if np.any(arrays["trace_rock_removed_m3"] > reserve[None, :] + 1e-9):
        raise ValueError("cumulative rock removed exceeds reserve")
    if np.any(arrays["trace_bed_m"] < floor[None, :] - 1e-9):
        raise ValueError("trace_bed below rock floor")

    loose_tr = arrays["trace_loose_solid_m3"]
    rock_tr = arrays["trace_rock_removed_m3"]
    bed_recon = bed_from_inventory(
        bed[None, :],
        (arrays["initial_alluvium_bulk_m3"] * (1.0 - p))[None, :],
        loose_tr,
        rock_tr,
        area[None, :],
        p,
    )
    if not np.allclose(bed_recon, arrays["trace_bed_m"], rtol=1e-9, atol=1e-9):
        raise ValueError("trace_bed recompute mismatch")

    dt = np.diff(time_seconds)[:, None]
    if not np.allclose(arrays["qs_solid_m3_s"], out / dt, rtol=1e-9, atol=1e-12):
        raise ValueError("qs mismatch")
    if not np.allclose(arrays["capacity_solid_m3_s"], arrays["capacity_solid_m3"] / dt,
                       rtol=1e-9, atol=1e-12):
        raise ValueError("capacity rate mismatch")
    with np.errstate(divide="ignore", invalid="ignore"):
        conc_check = np.divide(arrays["qs_solid_m3_s"], arrays["water_q_m3_s"],
                              out=np.zeros_like(arrays["qs_solid_m3_s"]),
                              where=arrays["water_q_m3_s"] > 0.0)
    if not np.allclose(conc_check, arrays["concentration_solid_m3_per_water_m3"],
                       rtol=1e-9, atol=1e-12):
        raise ValueError("concentration mismatch")

def save_daily_sediment(path: str, bundle: Dict[str, Any]) -> None:
    save_bundle(path, bundle, validator=validate_daily_sediment)

def load_daily_sediment(path: str, expected_sha256: str) -> Dict[str, Any]:
    return load_bundle(
        path,
        expected_sha256=expected_sha256,
        validator=validate_daily_sediment,
        max_bytes=128 * 1024 * 1024,
    )
