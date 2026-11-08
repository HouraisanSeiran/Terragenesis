"""Bounded TD spatial refinement with analytical steady and transient controls."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.channel_geometry import load_channel_geometry
from terrain_pipeline.surface_rivers.metric_channel_product import (
    load_channel_product,
    make_channel_product,
    save_channel_product,
)
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_resolution_exchange import (
    _sediment,
    refine_channel,
    restrict_inventory,
)
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters,
    SedimentConfig,
    load_sediment,
    save_sediment,
)
from tools.verify_td_morphology_extension import GEOMETRY, GEOMETRY_MANIFEST_SHA
from tools.verify_td_river_sediment import sample_saved_mesh

POLICY = dict(
    levels=[1, 2, 4, 8, 16, 32],
    reference_level=32,
    dt_seconds=0.1,
    temporal_dt_seconds=0.05,
    duration_seconds=60.0,
    initial_discharge_m3_s=0.01,
    concentration=0.0001,
    max_steps=5000,
    max_nodes=128,
    max_trace_bytes=64 * 1024 * 1024,
    inventory_relative_tolerance=0.03,
    export_relative_tolerance=0.03,
    half_export_time_tolerance_seconds=0.5,
    temporal_relative_tolerance=0.002,
    analytical_absolute_tolerance=1e-9,
    budget_absolute_tolerance=1e-9,
)


def native_network():
    if file_sha256(GEOMETRY / "acceptance.json") != GEOMETRY_MANIFEST_SHA:
        raise AssertionError("TD geometry manifest changed")
    manifest = json.loads((GEOMETRY / "acceptance.json").read_text(encoding="utf-8"))
    pin = manifest["artifacts"]["td_fine"]
    geometry = load_channel_geometry(
        GEOMETRY / pin["path"],
        expected_sha256=pin["sha256"],
        expected_identity=pin["identity_sha256"],
    )
    a = geometry["arrays"]
    bed = sample_saved_mesh(geometry, a["node_xz_m"])
    n = len(bed)
    length, distance, slope = np.zeros(n), np.zeros(n), np.zeros(n)
    for i, j in enumerate(a["receiver"]):
        if j >= 0:
            distance[i] = np.linalg.norm(a["node_xz_m"][j] - a["node_xz_m"][i])
            length[i] += distance[i] / 2.0
            length[j] += distance[i] / 2.0
            slope[i] = (bed[i] - bed[j]) / distance[i]
    for i, j in enumerate(a["receiver"]):
        if j < 0:
            slope[i] = slope[np.flatnonzero(a["receiver"] == i)[0]]
    net = ChannelNetwork(
        a["receiver"].copy(),
        length,
        a["width_m"].copy(),
        bed,
        slope,
        np.full(n, 0.035),
        np.full(n, 2.0),
        np.where(a["receiver"] >= 0, "interior", "open_outflow"),
        geometry["identity_sha256"],
        "TD canonical fine sections; half incident storage lengths",
        "declared Manning n=.035",
        receiver_distance_m=distance,
    )
    return net, dict(
        path=str(GEOMETRY / pin["path"]),
        **{k: v for k, v in pin.items() if k != "path"},
    )


def equilibrium_volume(network, discharge):
    low, high = np.zeros(len(network.receiver)), network.max_depth_m.copy()
    for _ in range(100):
        depth = (low + high) / 2.0
        area = network.width_m * depth
        radius = area / (network.width_m + 2.0 * depth)
        q = (
            area
            * radius ** (2.0 / 3.0)
            * np.sqrt(network.bed_slope)
            / network.roughness
        )
        low = np.where(q < discharge, depth, low)
        high = np.where(q >= discharge, depth, high)
    return (low + high) / 2.0 * network.width_m * network.length_m


def inlet_case(network, level, scenario, policy):
    n = len(network.receiver)
    donor_count = np.bincount(network.receiver[network.receiver >= 0], minlength=n)
    head = np.flatnonzero(donor_count == 0)
    if len(head) != 1 or np.any(donor_count > 1):
        raise ValueError("verification requires one serial TD reach")
    times = np.array([0.0, 10.0, policy["duration_seconds"]], np.float64)
    local = np.zeros((2, n), np.float64)
    local[:, head[0]] = policy["initial_discharge_m3_s"]
    if scenario == "drain":
        local[1] = 0.0
    forcing = ChannelForcing(times, local, network.source_identity_sha256)
    case = refine_channel(scenario, network, forcing, np.full(n, level, np.int64))
    # This is an upstream boundary inlet, not the lateral source of the legacy comparison.
    refined_local = np.zeros((2, len(case.parent_index)), np.float64)
    refined_local[:, np.flatnonzero(case.parent_index == head[0])[0]] = local[
        :, head[0]
    ]
    object.__setattr__(
        case,
        "forcing",
        ChannelForcing(times, refined_local, forcing.source_identity_sha256),
    )
    return case


def observe(water, sediment, parent, n, sample_times=(10.0, 30.0, 60.0), end_time=None):
    a, s = water["arrays"], sediment["arrays"]
    times = a["trace_time_seconds"]
    cumulative = np.r_[
        0.0, np.cumsum(a["trace_boundary_outflow_volume_m3"].sum(axis=1))
    ]
    solid_cumulative = np.r_[0.0, np.cumsum(s["step_exported_solid_m3"].sum(axis=1))]
    st = s["trace_time_seconds"]
    if end_time is not None:
        if end_time > min(times[-1], st[-1]):
            raise AssertionError("comparison horizon exceeds committed trace")
        cumulative = np.r_[
            cumulative[times < end_time], np.interp(end_time, times, cumulative)
        ]
        times = np.r_[times[times < end_time], end_time]
        solid_cumulative = np.r_[
            solid_cumulative[st < end_time], np.interp(end_time, st, solid_cumulative)
        ]
        st = np.r_[st[st < end_time], end_time]
    fields = {}
    for field, bundle in (
        ("volume_m3", a),
        ("mobile_solid_m3", s),
        ("bed_alluvium_solid_m3", s),
        ("rock_removed_m3", s),
    ):
        trajectory = restrict_inventory(bundle["trace_" + field], parent, n)
        clock = (
            a["trace_time_seconds"] if field == "volume_m3" else s["trace_time_seconds"]
        )
        fields[field] = np.array(
            [
                np.interp(t, clock, trajectory[:, i])
                for t in sample_times
                for i in range(n)
            ]
        ).tolist()
    fields.update(
        export_m3=float(cumulative[-1]),
        solid_export_m3=float(solid_cumulative[-1]),
        half_export_seconds=float(np.interp(cumulative[-1] / 2.0, cumulative, times)),
        half_solid_export_seconds=float(
            np.interp(solid_cumulative[-1] / 2.0, solid_cumulative, st)
        ),
    )
    return fields


def discrepancy(value, reference):
    relative = {}
    for key in (
        "volume_m3",
        "mobile_solid_m3",
        "bed_alluvium_solid_m3",
        "rock_removed_m3",
        "export_m3",
        "solid_export_m3",
    ):
        v, r = np.asarray(value[key]), np.asarray(reference[key])
        relative[key] = float(
            np.max(np.abs(v - r), initial=0.0)
            / max(float(np.max(np.abs(r), initial=0.0)), 1e-12)
        )
    relative["half_export_seconds"] = abs(
        value["half_export_seconds"] - reference["half_export_seconds"]
    )
    relative["half_solid_export_seconds"] = abs(
        value["half_solid_export_seconds"] - reference["half_solid_export_seconds"]
    )
    return relative


def cold_audit(path):
    path = Path(path)
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["policy"] != POLICY:
        raise AssertionError("frozen acceptance policy changed")
    native, source = native_network()
    if source != report["source"]:
        raise AssertionError("TD source changed")
    observations, errors = {}, {}
    initial = equilibrium_volume(native, POLICY["initial_discharge_m3_s"])
    for name, pin in report["products"].items():
        case = inlet_case(native, pin["level"], pin["scenario"], POLICY)
        water = load_channel_product(
            path.parent / pin["water_path"],
            expected_sha256=pin["water_sha256"],
            expected_identity=pin["water_identity"],
        )
        solid = load_sediment(
            path.parent / pin["solid_path"], expected_sha256=pin["solid_sha256"]
        )
        a, s = water["arrays"], solid["arrays"]
        if solid["identity_sha256"] != pin["solid_identity"]:
            raise AssertionError("sediment identity changed")
        expected_water_config = asdict(
            ChannelConfig(max_dt_seconds=pin["dt_seconds"], max_steps=pin["max_steps"])
        )
        expected_solid_config = asdict(
            SedimentConfig(
                max_dt_seconds=pin["dt_seconds"], max_steps=POLICY["max_steps"]
            )
        )
        if (
            water["metadata"]["config"] != expected_water_config
            or solid["metadata"]["config"] != expected_solid_config
        ):
            raise AssertionError("time controls changed")
        if solid["metadata"]["material"] != report["material"]:
            raise AssertionError("material changed")
        resource = dict(
            nodes=len(case.parent_index),
            water_steps=len(a["trace_time_seconds"]) - 1,
            solid_steps=len(s["step_dt_seconds"]),
            trace_bytes=sum(x.nbytes for x in a.values())
            + sum(x.nbytes for x in s.values()),
        )
        if (
            resource["nodes"] > POLICY["max_nodes"]
            or max(resource["water_steps"], resource["solid_steps"])
            > POLICY["max_steps"]
            or resource["trace_bytes"] > POLICY["max_trace_bytes"]
        ):
            raise AssertionError("frozen resource budget exceeded")
        if (
            water["metadata"]["status"] != pin["status"]
            or solid["metadata"]["status"] != pin["solid_status"]
        ):
            raise AssertionError("status changed")
        np.testing.assert_array_equal(a["network_receiver"], case.network.receiver)
        for field in (
            "length_m",
            "width_m",
            "bed_elevation_m",
            "bed_slope",
            "receiver_distance_m",
        ):
            np.testing.assert_array_equal(
                a["network_" + field], getattr(case.network, field)
            )
        np.testing.assert_array_equal(
            a["forcing_local_q_m3_s"], case.forcing.local_q_m3_s
        )
        expected = initial[case.parent_index] * case.fraction
        np.testing.assert_allclose(
            a["trace_volume_m3"][0], expected, rtol=0.0, atol=1e-12
        )
        np.testing.assert_allclose(
            s["trace_mobile_solid_m3"][0],
            expected * POLICY["concentration"],
            rtol=0.0,
            atol=1e-12,
        )
        np.testing.assert_allclose(
            s["trace_bed_alluvium_solid_m3"][0],
            case.network.width_m
            * case.network.length_m
            * 0.01
            * (1 - report["material"]["porosity"]),
            rtol=0.0,
            atol=1e-12,
        )
        np.testing.assert_array_equal(
            s["trace_rock_removed_m3"][0], np.zeros(len(case.parent_index))
        )
        np.testing.assert_array_equal(
            s["forcing_water_volume_m3"], a["trace_volume_m3"][:-1]
        )
        np.testing.assert_array_equal(
            s["forcing_water_outflow_m3_s"], a["trace_outflow_q_m3_s"]
        )
        dt = np.diff(a["trace_time_seconds"])
        incoming = np.zeros_like(a["trace_outflow_q_m3_s"])
        for i, j in enumerate(case.network.receiver):
            if j >= 0:
                incoming[:, j] += a["trace_outflow_q_m3_s"][:, i]
        residual = np.diff(a["trace_volume_m3"], axis=0) - dt[:, None] * (
            a["trace_local_q_m3_s"] + incoming - a["trace_outflow_q_m3_s"]
        )
        water_error = float(np.max(np.abs(residual), initial=0.0))
        solid_total = (
            s["trace_mobile_solid_m3"].sum(axis=1)
            + s["trace_bed_alluvium_solid_m3"].sum(axis=1)
            - s["trace_rock_removed_m3"].sum(axis=1)
        )
        solid_error = float(
            np.max(
                np.abs(
                    np.diff(solid_total)
                    - s["step_external_solid_m3"].sum(axis=1)
                    + s["step_exported_solid_m3"].sum(axis=1)
                ),
                initial=0.0,
            )
        )
        if max(water_error, solid_error) > POLICY["budget_absolute_tolerance"]:
            raise AssertionError("independent inventory budget failed")
        errors[name] = dict(
            water_residual_m3=water_error,
            solid_residual_m3=solid_error,
            resource=resource,
        )
        if pin["status"] == "complete" and pin["solid_status"] == "complete":
            observations[name] = observe(
                water, solid, case.parent_index, len(native.receiver)
            )
            if pin["scenario"] == "steady":
                analytical = max(
                    float(np.max(np.abs(a["trace_volume_m3"] - expected))),
                    abs(
                        float(a["trace_boundary_outflow_volume_m3"].sum()) - 0.01 * 60.0
                    ),
                    float(
                        np.max(
                            np.abs(
                                s["trace_mobile_solid_m3"]
                                - expected * POLICY["concentration"]
                            )
                        )
                    ),
                )
                if analytical > POLICY["analytical_absolute_tolerance"]:
                    raise AssertionError("analytical steady mismatch")
                errors[name]["analytical_absolute_error"] = analytical
    reference = observations["drain-32-dt005"]
    spatial = {
        str(level): discrepancy(observations[f"drain-{level}-dt01"], reference)
        for level in POLICY["levels"]
    }
    temporal = {
        str(level): discrepancy(
            observations[f"drain-{level}-dt01"], observations[f"drain-{level}-dt005"]
        )
        for level in (8, 16, 32)
    }
    accepted = []
    reference_time_ok = (
        max(
            temporal["32"][k]
            for k in ("volume_m3", "mobile_solid_m3", "export_m3", "solid_export_m3")
        )
        <= POLICY["temporal_relative_tolerance"]
    )
    reference_time_ok &= (
        max(
            temporal["32"]["half_export_seconds"],
            temporal["32"]["half_solid_export_seconds"],
        )
        <= POLICY["half_export_time_tolerance_seconds"]
    )
    for level in (8, 16):
        e, t = spatial[str(level)], temporal[str(level)]
        stock_ok = all(
            e[k] <= POLICY["inventory_relative_tolerance"]
            for k in (
                "volume_m3",
                "mobile_solid_m3",
                "bed_alluvium_solid_m3",
                "rock_removed_m3",
            )
        )
        export_ok = (
            max(e["export_m3"], e["solid_export_m3"])
            <= POLICY["export_relative_tolerance"]
        )
        timing_ok = (
            max(e["half_export_seconds"], e["half_solid_export_seconds"])
            <= POLICY["half_export_time_tolerance_seconds"]
        )
        time_ok = (
            max(
                t[k]
                for k in (
                    "volume_m3",
                    "mobile_solid_m3",
                    "export_m3",
                    "solid_export_m3",
                )
            )
            <= POLICY["temporal_relative_tolerance"]
        )
        time_ok &= (
            max(t["half_export_seconds"], t["half_solid_export_seconds"])
            <= POLICY["half_export_time_tolerance_seconds"]
        )
        if stock_ok and export_ok and timing_ok and time_ok and reference_time_ok:
            accepted.append(level)
    return dict(
        independent_budgets=errors,
        observations=observations,
        spatial_error=spatial,
        temporal_error=temporal,
        accepted_levels=accepted,
        minimum_accepted_level=min(accepted) if accepted else None,
        reference_temporal_control_passed=reference_time_ok,
        active_morphology_and_legacy_local_amr_status="unresolved; not covered by this passive serial inlet verification",
        status=(
            "accepted_bounded_serial_reach"
            if len(accepted) == 2
            else "spatial_consistency_unresolved"
        ),
    )


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    native, source = native_network()
    initial = equilibrium_volume(native, POLICY["initial_discharge_m3_s"])
    material = MaterialParameters(
        sediment_critical_shear_pa=0.0,
        rock_critical_shear_pa=0.0,
        sediment_erodibility_m_s_pa=0.0,
        rock_erodibility_m_s_pa=0.0,
        transport_coefficient=1.0,
        settling_velocity_m_s=0.0,
        provenance="declared passive sediment steady/draining inlet; no morphology feedback",
    )
    report = dict(
        schema="terragenesis-spatial-consistency-v1",
        policy=POLICY,
        source=source,
        scope="one real TD 90m serial reach; engineered inlet and passive sediment; no morphology/2D/global acceptance",
        reference="100-iteration Manning equilibrium bisection; transient level32 dt.05 numerical reference",
        forcing_policy="upstream inlet on first child only; all native initial extensive stocks split by length fraction",
        material=asdict(material),
        products={},
    )
    (output / "frozen-policy.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    specs = [("steady", level, 0.1, 5000) for level in (1, 8, 16, 32)]
    specs += [("drain", level, 0.1, 5000) for level in POLICY["levels"]]
    specs += [("drain", level, 0.05, 5000) for level in (8, 16, 32)]
    specs += [("drain", 8, 0.1, 1)]
    for scenario, level, dt, budget in specs:
        name = f"{scenario}-{level}-dt{'01' if dt==.1 else '005'}" + (
            "-failure" if budget == 1 else ""
        )
        case = inlet_case(native, level, scenario, POLICY)
        water = make_channel_product(
            case.network,
            case.forcing,
            solve_channel(
                case.network,
                case.forcing,
                initial_volume_m3=initial[case.parent_index] * case.fraction,
                config=ChannelConfig(max_dt_seconds=dt, max_steps=budget),
            ),
        )
        solid = _sediment(
            case,
            water,
            material,
            SedimentConfig(max_dt_seconds=dt, max_steps=5000),
            0.01,
            1.0,
            POLICY["concentration"],
            initial_mobile_solid_m3=initial[case.parent_index]
            * case.fraction
            * POLICY["concentration"],
        )
        if (
            sum(x.nbytes for x in water["arrays"].values())
            + sum(x.nbytes for x in solid["arrays"].values())
            > POLICY["max_trace_bytes"]
        ):
            raise AssertionError("frozen trace budget exceeded")
        wp, sp = output / (name + "-water.npz"), output / (name + "-solid.npz")
        save_channel_product(wp, water)
        save_sediment(sp, solid)
        report["products"][name] = dict(
            level=level,
            scenario=scenario,
            dt_seconds=dt,
            max_steps=budget,
            water_path=wp.name,
            water_sha256=file_sha256(wp),
            solid_path=sp.name,
            solid_sha256=file_sha256(sp),
            water_identity=water["identity_sha256"],
            solid_identity=solid["identity_sha256"],
            status=water["metadata"]["status"],
            solid_status=solid["metadata"]["status"],
        )
        print(
            name, water["metadata"]["status"], solid["metadata"]["status"], flush=True
        )
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with patch(
        __name__ + ".solve_channel", side_effect=AssertionError("cold water")
    ), patch(__name__ + "._sediment", side_effect=AssertionError("cold sediment")):
        report["audit"] = cold_audit(path)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    result = cold_audit(args.output) if args.audit else verify(args.output)
    if args.audit:
        destination = Path(args.output).parent / "cold-audit.json"
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result.get("audit", result), indent=2), flush=True)
