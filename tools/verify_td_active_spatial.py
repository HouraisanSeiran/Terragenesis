"""Original Stage 4 TD domain, unchanged active material/runoff and zero stocks."""

import argparse
from dataclasses import asdict
import json
import time
import ctypes
from pathlib import Path
from unittest.mock import patch
import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_channel_product import (
    load_channel_product,
    make_channel_product,
    save_channel_product,
)
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters,
    SedimentConfig,
    load_sediment,
    save_sediment,
)
from terrain_pipeline.surface_rivers.metric_resolution_exchange import (
    refine_channel,
    _sediment,
    restrict_inventory,
)
from tools.verify_td_spatial_consistency import observe, discrepancy

ROOT = Path(__file__).resolve().parents[1]
PARENT = (
    ROOT
    / "verification/td-natural-river-stages/stage4-20261011-05/morphology/resolution/comparison.json"
)
POLICY = dict(
    levels=[1, 2, 4, 8, 16, 32, 64],
    local_levels=[4, 16, 32],
    dt_seconds=0.5,
    temporal_dt_seconds=0.25,
    reference_level=64,
    max_nodes=256,
    max_steps=10000,
    max_trace_bytes=128 * 1024 * 1024,
    inventory_relative_tolerance=0.03,
    export_relative_tolerance=0.03,
    half_export_time_tolerance_seconds=0.5,
    temporal_relative_tolerance=0.002,
    bed_absolute_tolerance_m=0.001,
    budget_absolute_tolerance=1e-8,
    sample_times_seconds=[300.0, 600.0, 900.0],
)


def peak_rss_bytes():
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    if not psapi.GetProcessMemoryInfo(
        ctypes.c_void_p(kernel.GetCurrentProcess()), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.PeakWorkingSetSize)


def source():
    old = json.loads(PARENT.read_text(encoding="utf-8"))
    pin = old["cases"]["native"]["channel_trace"]
    water = load_channel_product(
        PARENT.parent / pin["path"],
        expected_sha256=pin["sha256"],
        expected_identity=pin["identity_sha256"],
    )
    a, m = water["arrays"], water["metadata"]
    if len(a["network_receiver"]) != 4:
        raise AssertionError("expected original four-node Stage 4 domain")
    ids = np.arange(4)
    receiver = a["network_receiver"][ids].copy()
    if not np.array_equal(receiver, np.r_[ids[1:], -1]):
        raise AssertionError("expected serial original tail")
    receiver = np.array([1, 2, 3, -1], np.int64)
    fields = [
        a["network_" + f][ids].copy()
        for f in (
            "length_m",
            "width_m",
            "bed_elevation_m",
            "bed_slope",
            "roughness",
            "max_depth_m",
            "terminal_kind",
        )
    ]
    distance = a.get(
        "network_receiver_distance_m",
        np.where(a["network_receiver"] >= 0, a["network_length_m"], 0.0),
    )
    net = ChannelNetwork(
        receiver,
        *fields,
        m["network_source_identity_sha256"],
        m["section_source"],
        m["roughness_source"],
        receiver_distance_m=distance[ids].copy(),
    )
    forcing = ChannelForcing(
        a["forcing_time_seconds"].copy(),
        a["forcing_local_q_m3_s"][:, ids].copy(),
        m["forcing_source_identity_sha256"],
    )
    return (
        net,
        forcing,
        old,
        dict(
            parent_path=str(PARENT),
            parent_sha256=file_sha256(PARENT),
            water_pin=pin,
            native_indices=ids.tolist(),
            boundary="entire original four-node Stage 4 domain; same local runoff and zero initial water/mobile",
        ),
    )


def cold(path):
    path = Path(path)
    report = json.loads(path.read_text(encoding="utf-8"))
    net, forcing, old, pin = source()
    if (
        report["policy"] != POLICY
        or report["source"] != pin
        or report["material"] != old["material"]
        or report["material_inputs"] != old["material_inputs"]
    ):
        raise AssertionError("frozen source/material/policy changed")
    observations, resources, budgets, beds = {}, {}, {}, {}
    for name, p in report["products"].items():
        case = refine_channel(name, net, forcing, np.asarray(p["counts"], np.int64))
        w = load_channel_product(
            path.parent / p["water_path"],
            expected_sha256=p["water_sha256"],
            expected_identity=p["water_identity"],
        )
        s = load_sediment(
            path.parent / p["solid_path"], expected_sha256=p["solid_sha256"]
        )
        a, b = w["arrays"], s["arrays"]
        if (
            s["identity_sha256"] != p["solid_identity"]
            or s["metadata"]["material"] != old["material"]
        ):
            raise AssertionError("solid material/identity changed")
        if w["metadata"]["config"] != asdict(
            ChannelConfig(max_dt_seconds=p["dt"], max_steps=10000)
        ) or s["metadata"]["config"] != asdict(
            SedimentConfig(max_dt_seconds=p["dt"], max_steps=10000)
        ):
            raise AssertionError("time controls changed")
        for f in (
            "receiver",
            "length_m",
            "width_m",
            "bed_elevation_m",
            "bed_slope",
            "receiver_distance_m",
            "roughness",
            "max_depth_m",
            "terminal_kind",
        ):
            np.testing.assert_array_equal(a["network_" + f], getattr(case.network, f))
        np.testing.assert_array_equal(
            a["forcing_local_q_m3_s"], case.forcing.local_q_m3_s
        )
        np.testing.assert_array_equal(
            a["forcing_time_seconds"], case.forcing.time_seconds
        )
        np.testing.assert_array_equal(
            a["trace_volume_m3"][0], np.zeros(len(case.parent_index))
        )
        np.testing.assert_array_equal(
            b["trace_mobile_solid_m3"][0], np.zeros(len(case.parent_index))
        )
        np.testing.assert_array_equal(
            b["forcing_water_volume_m3"], a["trace_volume_m3"][:-1]
        )
        np.testing.assert_array_equal(
            b["forcing_water_outflow_m3_s"], a["trace_outflow_q_m3_s"]
        )
        np.testing.assert_array_equal(
            b["forcing_external_solid_m3_s"],
            a["trace_local_q_m3_s"]
            * old["material_inputs"]["external_solid_concentration_m3_per_m3"],
        )
        area = case.network.width_m * case.network.length_m
        np.testing.assert_array_equal(b["domain_bed_area_m2"], area)
        np.testing.assert_allclose(
            b["domain_rock_floor_m"],
            case.network.bed_elevation_m
            - old["material_inputs"]["initial_alluvium_depth_m"]
            - old["material_inputs"]["rock_reserve_depth_m"],
            rtol=0,
            atol=1e-12,
        )
        np.testing.assert_allclose(
            b["trace_bed_alluvium_solid_m3"][0],
            case.network.width_m
            * case.network.length_m
            * old["material_inputs"]["initial_alluvium_depth_m"]
            * (1 - old["material"]["porosity"]),
            rtol=0,
            atol=1e-12,
        )
        dt = np.diff(a["trace_time_seconds"])
        incoming = np.zeros_like(a["trace_outflow_q_m3_s"])
        for i, j in enumerate(case.network.receiver):
            if j >= 0:
                incoming[:, j] += a["trace_outflow_q_m3_s"][:, i]
        wr = np.diff(a["trace_volume_m3"], axis=0) - dt[:, None] * (
            a["trace_local_q_m3_s"] + incoming - a["trace_outflow_q_m3_s"]
        )
        stocks = (
            b["trace_mobile_solid_m3"].sum(axis=1)
            + b["trace_bed_alluvium_solid_m3"].sum(axis=1)
            - b["trace_rock_removed_m3"].sum(axis=1)
        )
        sr = (
            np.diff(stocks)
            - b["step_external_solid_m3"].sum(axis=1)
            + b["step_exported_solid_m3"].sum(axis=1)
        )
        budgets[name] = dict(
            water=float(np.max(np.abs(wr), initial=0)),
            solid=float(np.max(np.abs(sr), initial=0)),
        )
        if max(budgets[name].values()) > POLICY["budget_absolute_tolerance"]:
            raise AssertionError("independent budget failed")
        resources[name] = dict(
            nodes=len(case.parent_index),
            water_steps=len(dt),
            solid_steps=len(b["step_dt_seconds"]),
            water_trace_bytes=sum(x.nbytes for x in a.values()),
            solid_trace_bytes=sum(x.nbytes for x in b.values()),
            water_status=w["metadata"]["status"],
            solid_status=s["metadata"]["status"],
            water_end_seconds=float(a["trace_time_seconds"][-1]),
            solid_end_seconds=float(b["trace_time_seconds"][-1]),
        )
        q = resources[name]
        if (
            q["nodes"] > POLICY["max_nodes"]
            or max(q["water_steps"], q["solid_steps"]) > POLICY["max_steps"]
            or max(q["water_trace_bytes"], q["solid_trace_bytes"])
            > POLICY["max_trace_bytes"]
        ):
            raise AssertionError("resource exceeded")
        observations[name] = observe(
            w, s, case.parent_index, 4, (300.0,), end_time=300.0
        )
        at_end = np.array(
            [
                np.interp(300.0, b["trace_time_seconds"], column)
                for column in b["trace_bed_elevation_m"].T
            ]
        )
        change = at_end - b["domain_bed_elevation_m"]
        beds[name] = (
            restrict_inventory(change * b["domain_bed_area_m2"], case.parent_index, 4)
            / (net.width_m * net.length_m)
        ).tolist()
    reference = observations["uniform-64-fine"]
    errors = {name: discrepancy(o, reference) for name, o in observations.items()}
    for name, e in errors.items():
        e["bed_max_abs_m"] = float(
            np.max(np.abs(np.asarray(beds[name]) - beds["uniform-64-fine"]))
        )
    temporal = {
        str(level): discrepancy(
            observations[f"uniform-{level}"], observations[f"uniform-{level}-fine"]
        )
        for level in (16, 32, 64)
    }

    def time_ok(e):
        return (
            max(
                e[k]
                for k in (
                    "volume_m3",
                    "mobile_solid_m3",
                    "export_m3",
                    "solid_export_m3",
                )
            )
            <= POLICY["temporal_relative_tolerance"]
            and max(e["half_export_seconds"], e["half_solid_export_seconds"])
            <= POLICY["half_export_time_tolerance_seconds"]
        )

    accepted = []
    for level in (16, 32):
        e = errors[f"uniform-{level}"]
        stock = (
            max(
                e[k]
                for k in (
                    "volume_m3",
                    "mobile_solid_m3",
                    "bed_alluvium_solid_m3",
                    "rock_removed_m3",
                )
            )
            <= POLICY["inventory_relative_tolerance"]
        )
        if (
            stock
            and max(e["export_m3"], e["solid_export_m3"])
            <= POLICY["export_relative_tolerance"]
            and max(e["half_export_seconds"], e["half_solid_export_seconds"])
            <= POLICY["half_export_time_tolerance_seconds"]
            and e["bed_max_abs_m"] <= POLICY["bed_absolute_tolerance_m"]
            and time_ok(temporal[str(level)])
            and time_ok(temporal["64"])
        ):
            accepted.append(level)
    return dict(
        errors=errors,
        temporal_errors=temporal,
        independent_budgets=budgets,
        resources=resources,
        observations=observations,
        comparison_horizon_seconds=300.0,
        horizon_reason="predeclared sample300 is last shared sample before level64 dt.25 water budget failure584.75s; sample600/900 cannot be evaluated",
        full_900_second_status="not_accepted; level64 traces exceed unchanged per-product128MiB budget",
        native_bed_change_m=beds,
        accepted_uniform_levels=accepted,
        minimum_accepted_level=min(accepted) if accepted else None,
        status=(
            "accepted_original_stage4_active_domain"
            if len(accepted) == 2
            else "unresolved_original_stage4_active_domain"
        ),
        dynamic_bed_feedback_spatial_status="not covered; original resolution comparison is frozen-water sediment replay",
    )


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    net, forcing, old, pin = source()
    material = MaterialParameters(**old["material"])
    mi = old["material_inputs"]
    report = dict(
        schema="terragenesis-active-spatial-consistency-v1",
        policy=POLICY,
        source=pin,
        material=old["material"],
        material_inputs=mi,
        scope="entire original Stage4 native geometry/local runoff/active material/zero stocks; frozen-water replay; not coupled bed feedback",
        products={},
    )
    (output / "frozen-policy.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    specs = (
        [(f"uniform-{k}", [k] * 4, 0.5) for k in POLICY["levels"]]
        + [(f"local-{k}", [1, k, k, 1], 0.5) for k in POLICY["local_levels"]]
        + [(f"uniform-{k}-fine", [k] * 4, 0.25) for k in (16, 32, 64)]
    )
    for name, counts, dt in specs:
        case = refine_channel(name, net, forcing, np.array(counts, np.int64))
        w = make_channel_product(
            case.network,
            case.forcing,
            solve_channel(
                case.network,
                case.forcing,
                config=ChannelConfig(max_dt_seconds=dt, max_steps=10000),
            ),
        )
        s = _sediment(
            case,
            w,
            material,
            SedimentConfig(max_dt_seconds=dt, max_steps=10000),
            mi["initial_alluvium_depth_m"],
            mi["rock_reserve_depth_m"],
            mi["external_solid_concentration_m3_per_m3"],
        )
        wp, sp = output / (name + "-water.npz"), output / (name + "-solid.npz")
        save_channel_product(wp, w)
        save_sediment(sp, s)
        report["products"][name] = dict(
            counts=counts,
            dt=dt,
            water_path=wp.name,
            solid_path=sp.name,
            water_sha256=file_sha256(wp),
            solid_sha256=file_sha256(sp),
            water_identity=w["identity_sha256"],
            solid_identity=s["identity_sha256"],
        )
        print(name, w["metadata"]["status"], s["metadata"]["status"], flush=True)
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with patch(
        __name__ + ".solve_channel", side_effect=AssertionError("cold water")
    ), patch(__name__ + "._sediment", side_effect=AssertionError("cold sediment")):
        report["audit"] = cold(path)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--audit", action="store_true")
    a = p.parse_args()
    started = time.perf_counter()
    r = cold(a.output) if a.audit else verify(a.output)
    if a.audit:
        r["cold_read_resource"] = dict(
            elapsed_seconds=time.perf_counter() - started,
            peak_rss_bytes=peak_rss_bytes(),
            solver_calls=0,
            solve_elapsed_seconds="not instrumented in initial saved run",
        )
        destination = Path(a.output).parent / "cold-audit-300s.json"
        destination.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: v
                for k, v in r.get("audit", r).items()
                if k not in ("observations", "native_bed_change_m")
            },
            indent=2,
        ),
        flush=True,
    )
