"""Conservative serial channel refinement, with pinned water and solid traces.

This is one-dimensional reach refinement, not two-dimensional AMR. Sediment
uses the existing frozen-water contract and cannot certify bed feedback.
"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from .metric_channel_product import (
    NETWORK_FIELDS, SCHEMA as CHANNEL_SCHEMA, load_channel_product, make_channel_product, save_channel_product,
)
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork
from .metric_sediment import (
    MAX_SEDIMENT_NODES, MaterialParameters, SedimentConfig, SedimentDomain, SedimentForcing,
    load_sediment, save_sediment, solve_sediment,
)

SCHEMA = "terragenesis-resolution-comparison-v1"


@dataclass(frozen=True)
class ResolutionCase:
    name: str
    network: ChannelNetwork
    forcing: ChannelForcing
    parent_index: np.ndarray
    counts: np.ndarray
    fraction: np.ndarray


def restrict_inventory(values, parent_index, native_count):
    """Sum extensive inventories; never average water or solid volumes."""
    values = np.asarray(values)
    result = np.zeros(values.shape[:-1] + (native_count,), np.float64)
    for child, parent in enumerate(parent_index):
        result[..., parent] += values[..., child]
    return result


def refine_channel(name, network, forcing, counts):
    counts = np.asarray(counts)
    n = network.receiver.size
    if counts.shape != (n,) or counts.dtype.kind not in "iu" or np.any(counts < 1):
        raise ValueError("one positive integer subdivision count per native reach required")
    counts = counts.copy()
    counts[(network.receiver == -1) & (network.bed_slope == 0.)] = 1
    if np.sum(counts) > MAX_SEDIMENT_NODES:
        raise ValueError("refinement exceeds existing sediment domain limit")
    start = np.r_[0, np.cumsum(counts)[:-1]]
    parent = np.repeat(np.arange(n), counts)
    fraction = 1. / counts[parent]
    receiver = np.arange(1, parent.size + 1, dtype=np.int64)
    kind = np.full(parent.size, "interior", dtype="U24")
    bed = np.empty(parent.size, np.float64)
    distance = np.zeros(parent.size, np.float64)
    for i, count in enumerate(counts):
        last = start[i] + count - 1
        target = network.receiver[i]
        receiver[last] = start[target] if target >= 0 else -1
        kind[last] = network.terminal_kind[i]
        # Native upstream bed datum and Manning slope define a linear reach.
        # Native geometry is unchanged; the final terminal reach is extrapolated.
        reach_distance = network.receiver_distance_m[i] if target >= 0 else network.length_m[i]
        bed[start[i]:last + 1] = (network.bed_elevation_m[i]
            - np.arange(count) * reach_distance / count * network.bed_slope[i])
        distance[start[i]:last + 1] = reach_distance / count
        if target < 0:
            distance[last] = 0.
    refined = ChannelNetwork(receiver, network.length_m[parent] * fraction,
        network.width_m[parent].copy(), bed, network.bed_slope[parent].copy(),
        network.roughness[parent].copy(), network.max_depth_m[parent].copy(), kind,
        network.source_identity_sha256, network.section_source, network.roughness_source,
        receiver_distance_m=distance)
    local = forcing.local_q_m3_s[:, parent] * fraction
    refined_forcing = ChannelForcing(forcing.time_seconds.copy(), local,
                                     forcing.source_identity_sha256)
    return ResolutionCase(name, refined, refined_forcing, parent, counts.copy(), fraction)


def _pin(path, bundle):
    return {"path": path.name, "sha256": file_sha256(path),
            "identity_sha256": bundle["identity_sha256"]}


def _sediment(case, water, material, config, initial_alluvium_depth_m,
              rock_reserve_depth_m, external_concentration, initial_mobile_solid_m3=None):
    net = case.network
    a = water["arrays"]
    area = net.length_m * net.width_m
    domain = SedimentDomain(net.receiver.copy(), area, net.width_m.copy(),
        net.bed_elevation_m.copy(), net.bed_elevation_m - initial_alluvium_depth_m
        - rock_reserve_depth_m, area * initial_alluvium_depth_m,
        np.zeros(area.size, np.bool_), net.terminal_kind == "open_outflow",
        water["identity_sha256"], "same homogeneous native material split by reach area")
    forcing = SedimentForcing(a["trace_time_seconds"].copy(),
        a["trace_volume_m3"][:-1].copy(), a["trace_depth_m"][:-1].copy(),
        a["trace_outflow_q_m3_s"].copy(),
        np.broadcast_to(net.bed_slope, a["trace_local_q_m3_s"].shape).copy(),
        a["trace_local_q_m3_s"] * external_concentration,
        water["identity_sha256"], water["identity_sha256"],
        "committed hydraulic intervals; external solid equals local water times declared concentration")
    return solve_sediment(domain, forcing, material,
        initial_mobile_solid_m3=initial_mobile_solid_m3, config=config)


def _metrics(water, solid, case, native):
    a = water["arrays"]
    s = solid["arrays"] if solid is not None else None
    n = native.receiver.size
    volume = restrict_inventory(a["trace_volume_m3"], case.parent_index, n)
    stage = native.bed_elevation_m + volume / (native.length_m * native.width_m)
    last = np.cumsum(case.counts) - 1
    q = a["trace_outflow_end_q_m3_s"][:, last]
    arrival = []
    for column in q.T:
        active = np.flatnonzero(column > 1e-12)
        arrival.append(float(a["trace_time_seconds"][active[0]]) if active.size else None)
    native_bed_change = np.zeros(n)
    if s is not None:
        bed_change = s["trace_bed_elevation_m"][-1] - s["domain_bed_elevation_m"]
        native_bed_change = restrict_inventory(bed_change * s["domain_bed_area_m2"], case.parent_index, n) / (native.length_m * native.width_m)
    result = {"status": water["metadata"]["status"],
        "failure_reason": water["metadata"]["failure_reason"],
        "last_time_seconds": float(a["trace_time_seconds"][-1]),
        "sediment_status": solid["metadata"]["status"] if solid else "not_run",
        "sediment_failure_reason": solid["metadata"]["failure_reason"] if solid else "no committed hydraulic interval",
        "sediment_last_time_seconds": float(s["trace_time_seconds"][-1]) if solid else None,
        "node_count": int(case.parent_index.size),
        "final_volume_m3": float(volume[-1].sum()),
        "restricted_volume_m3": volume[-1].tolist(),
        "boundary_outflow_volume_m3": float(a["trace_boundary_outflow_volume_m3"].sum()),
        "peak_discharge_m3_s": float(q.max(initial=0.)),
        "section_peak_discharge_m3_s": q.max(axis=0).tolist(),
        "arrival_time_seconds": arrival, "cross_section_stage_m": stage[-1].tolist(),
        "final_bed_elevation_m": (native.bed_elevation_m + native_bed_change).tolist() if s else None,
        "native_bed_change_m": native_bed_change.tolist() if s else None,
        "exported_solid_m3": float(s["step_exported_solid_m3"].sum()) if s else None,
        "resource": {"steps": int(len(a["trace_time_seconds"]) - 1),
            "sediment_steps": int(len(s["step_dt_seconds"])) if s else 0,
            "min_dt_seconds": float(np.min(np.diff(a["trace_time_seconds"]), initial=np.inf)) if len(a["trace_time_seconds"]) > 1 else None,
            "max_dt_seconds": float(np.max(np.diff(a["trace_time_seconds"]), initial=0.)),
            "trace_array_bytes": int(sum(v.nbytes for v in a.values()) + (sum(v.nbytes for v in s.values()) if s else 0))}}
    for field in ("mobile_solid_m3", "bed_alluvium_solid_m3", "rock_removed_m3"):
        result["restricted_" + field] = restrict_inventory(s["trace_" + field][-1], case.parent_index, n).tolist() if s else None
    return result


def run_resolution_comparison(network, forcing, *, local_counts, output_path,
        source_manifest, config=ChannelConfig(), sediment_config=SedimentConfig(),
        material=MaterialParameters(), initial_alluvium_depth_m=.01,
        rock_reserve_depth_m=1., external_concentration=1e-5):
    """Run three subdivisions of one physical network with identical limits."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = network.receiver.size
    cases = {name: refine_channel(name, network, forcing, counts) for name, counts in (
        ("native", np.ones(n, np.int64)), ("uniform", np.full(n, 2, np.int64)),
        ("local_amr", local_counts))}
    reports = {}
    for name, case in cases.items():
        started = time.perf_counter()
        water = make_channel_product(case.network, case.forcing,
            solve_channel(case.network, case.forcing, config=config))
        water_path = path.parent / (name + "-channel.npz")
        save_channel_product(water_path, water)
        solid = None
        solid_path = path.parent / (name + "-sediment.npz")
        if len(water["arrays"]["trace_time_seconds"]) >= 2:
            solid = _sediment(case, water, material, sediment_config, initial_alluvium_depth_m, rock_reserve_depth_m, external_concentration)
            save_sediment(solid_path, solid)
        report = _metrics(water, solid, case, network)
        report.update(channel_trace=_pin(water_path, water), sediment_trace=_pin(solid_path, solid) if solid else None,
            parent_index=case.parent_index.tolist(), counts=case.counts.tolist(),
            fraction=case.fraction.tolist())
        report["resource"]["elapsed_seconds"] = time.perf_counter() - started
        reports[name] = report
    payload = {"schema": SCHEMA, "algorithm": "serial-reach-refinement-shared-flux-v1",
        "scope": "1D serial channel refinement; no 2D AMR, global coverage or bed feedback acceptance",
        "source_manifest": source_manifest, "cases": reports,
        "common_limits": {"channel": asdict(config), "sediment": asdict(sediment_config)},
        "material": asdict(material), "material_inputs": {
            "initial_alluvium_depth_m": initial_alluvium_depth_m,
            "rock_reserve_depth_m": rock_reserve_depth_m,
            "external_solid_concentration_m3_per_m3": external_concentration},
        "geometry_policy": "native upstream datum; child bed = native bed - slope * child upstream distance; terminal extrapolated; Manning slopes retained",
        "zero_slope_terminal_policy": "closed/unknown zero-slope controls remain native; uniform refines active transport reaches",
        "stage_policy": "native bed datum + restricted water volume / native bed area",
        "exchange": {"time_stepping": "one shared CFL step per case; no asynchronous subcycling",
            "interface": "actual donor outflow is receiver incoming contribution in the same solver step",
            "source": "native local water/solid inputs split once by child length fraction",
            "restriction": "sum extensive inventories; area-weight bed change; native datum stage"},
        "acceptance": {"conservative_exchange": "pending_cold_audit",
            "resolution_agreement": "measured_unresolved", "publishable": False}}
    payload["comparison"] = comparison_metrics(reports)
    save_comparison(path, payload)
    return payload


def comparison_metrics(reports):
    base = reports["native"]
    deltas = {}
    for name, report in reports.items():
        if name == "native":
            continue
        common_water = report["last_time_seconds"] == base["last_time_seconds"]
        common_solid = (report["sediment_last_time_seconds"] is not None
            and report["sediment_last_time_seconds"] == base["sediment_last_time_seconds"])
        deltas[name] = {field: report[field] - base[field] if common_water else None for field in (
            "final_volume_m3", "boundary_outflow_volume_m3", "peak_discharge_m3_s")}
        deltas[name]["exported_solid_m3"] = report["exported_solid_m3"] - base["exported_solid_m3"] if common_solid else None
        for field in ("cross_section_stage_m", "native_bed_change_m", "section_peak_discharge_m3_s"):
            if (field == "native_bed_change_m" and not common_solid) or (field != "native_bed_change_m" and not common_water):
                deltas[name][field + "_delta"] = None
                deltas[name][field + "_max_abs_delta"] = None
                continue
            diff = np.asarray(report[field]) - np.asarray(base[field])
            deltas[name][field + "_delta"] = diff.tolist()
            deltas[name][field + "_max_abs_delta"] = float(np.abs(diff).max(initial=0.))
        deltas[name]["arrival_time_delta_seconds"] = [
            None if a is None or b is None else a - b
            for a, b in zip(report["arrival_time_seconds"], base["arrival_time_seconds"])] if common_water else None
        deltas[name]["common_end_time"] = report["last_time_seconds"] == base["last_time_seconds"]
        deltas[name]["common_sediment_end_time"] = common_solid
    return {"native_volume_m3": base["final_volume_m3"], "deltas": deltas,
        "threshold_context": {"M3_temporal_stage_m": .001, "M3_temporal_outlet_relative": .01,
            "applicability": "temporal-refinement thresholds do not certify spatial refinement convergence"}}


def save_comparison(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_comparison(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError("invalid comparison schema")
    return payload


def _same_native_basis(original, current):
    if original["identity_sha256"] == current["identity_sha256"]:
        return True
    old_meta, new_meta = original["metadata"], current["metadata"]
    if (old_meta["schema"] != "terragenesis-channel-diagnostic-v1"
            or new_meta["schema"] != CHANNEL_SCHEMA):
        return False
    old_arrays, new_arrays = original["arrays"], current["arrays"]
    if set(new_arrays) != set(old_arrays) | {"network_receiver_distance_m"}:
        return False
    for name, old_value in old_arrays.items():
        new_value = new_arrays[name]
        if old_value.dtype != new_value.dtype or not np.array_equal(old_value, new_value):
            return False
    expected_distance = np.where(old_arrays["network_receiver"] >= 0,
                                 old_arrays["network_length_m"], 0.)
    if not np.array_equal(new_arrays["network_receiver_distance_m"], expected_distance):
        return False
    old_shared = {key: value for key, value in old_meta.items() if key not in ("schema", "semantics")}
    new_shared = {key: value for key, value in new_meta.items() if key not in ("schema", "semantics")}
    new_semantics = {key: value for key, value in new_meta["semantics"].items() if key != "geometry"}
    return old_shared == new_shared and old_meta["semantics"] == new_semantics


def audit_comparison(path):
    """Cold-load pinned products and reconstruct exchange and budgets."""
    path = Path(path)
    payload = load_comparison(path)
    waters, solids = {}, {}
    for name, report in payload["cases"].items():
        pin = report["channel_trace"]
        waters[name] = load_channel_product(path.parent / pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        pin = report["sediment_trace"]
        if pin is None:
            solids[name] = None
            continue
        solids[name] = load_sediment(path.parent / pin["path"], expected_sha256=pin["sha256"])
        if solids[name]["identity_sha256"] != pin["identity_sha256"]:
            raise ValueError("sediment identity mismatch")
    native_a = waters["native"]["arrays"]
    native_m = waters["native"]["metadata"]
    source = payload["source_manifest"]
    if "native_channel_product" in source:
        pin = source["native_channel_product"]
        original = load_channel_product(pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        if not _same_native_basis(original, waters["native"]):
            raise ValueError("native run changed the pinned M3 volume basis")
        if file_sha256(source["acceptance_path"]) != source["acceptance_sha256"]:
            raise ValueError("source acceptance changed")
    native = ChannelNetwork(**{k: native_a["network_" + k] for k in NETWORK_FIELDS if "network_" + k in native_a},
        source_identity_sha256=native_m["network_source_identity_sha256"],
        section_source=native_m["section_source"], roughness_source=native_m["roughness_source"])
    forcing = ChannelForcing(native_a["forcing_time_seconds"], native_a["forcing_local_q_m3_s"], native_m["forcing_source_identity_sha256"])
    results, metrics = {}, {}
    for name, report in payload["cases"].items():
        case = refine_channel(name, native, forcing, np.asarray(report["counts"], np.int64))
        a = waters[name]["arrays"]
        s = solids[name]["arrays"] if solids[name] else None
        if report["parent_index"] != case.parent_index.tolist() or report["fraction"] != case.fraction.tolist():
            raise ValueError("native refinement mapping mismatch")
        for field in NETWORK_FIELDS:
            observed = a.get("network_" + field)
            if observed is None and field == "receiver_distance_m":
                observed = np.where(a["network_receiver"] >= 0, a["network_length_m"], 0.)
            np.testing.assert_array_equal(observed, getattr(case.network, field))
        np.testing.assert_allclose(a["forcing_local_q_m3_s"], case.forcing.local_q_m3_s, rtol=0., atol=0.)
        np.testing.assert_array_equal(a["forcing_time_seconds"], forcing.time_seconds)
        if s is None:
            if len(a["trace_time_seconds"]) != 1 or report["status"] != "failed_prefix":
                raise ValueError("sediment omitted despite committed hydraulic intervals")
            metrics[name] = _metrics(waters[name], None, case, native)
            for field, value in metrics[name].items():
                if field != "resource" and value != report[field]:
                    raise ValueError("zero-interval metrics mismatch")
            results[name] = {"status": "failed_prefix", "sediment_status": "not_run", "mixed_interfaces": [], "water_residual_m3": 0., "solid_residual_m3": None}
            continue
        if waters[name]["metadata"]["config"] != payload["common_limits"]["channel"] or solids[name]["metadata"]["config"] != payload["common_limits"]["sediment"]:
            raise ValueError("case limits differ")
        if solids[name]["metadata"]["material"] != payload["material"]:
            raise ValueError("material differs between resolutions")
        inputs = payload["material_inputs"]
        for field in ("bed_elevation_m", "width_m"):
            np.testing.assert_array_equal(s["domain_" + field], getattr(case.network, field))
        np.testing.assert_array_equal(s["domain_rock_floor_m"], case.network.bed_elevation_m - inputs["initial_alluvium_depth_m"] - inputs["rock_reserve_depth_m"])
        np.testing.assert_array_equal(s["domain_is_lake"], np.zeros(case.parent_index.size, np.bool_))
        np.testing.assert_array_equal(s["forcing_friction_slope"], np.broadcast_to(case.network.bed_slope, a["trace_local_q_m3_s"].shape))
        for field in ("hydraulic_identity_sha256", "geometry_identity_sha256"):
            if solids[name]["metadata"][field] != waters[name]["identity_sha256"]:
                raise ValueError("sediment replay identity differs from water")
        np.testing.assert_array_equal(s["domain_receiver"], case.network.receiver)
        np.testing.assert_array_equal(s["domain_open_boundary"], case.network.terminal_kind == "open_outflow")
        np.testing.assert_allclose(s["domain_bed_area_m2"], case.network.length_m * case.network.width_m, rtol=0., atol=0.)
        np.testing.assert_allclose(s["domain_initial_alluvium_bulk_m3"], s["domain_bed_area_m2"] * inputs["initial_alluvium_depth_m"], rtol=0., atol=0.)
        np.testing.assert_array_equal(s["forcing_time_seconds"], a["trace_time_seconds"])
        for field, water_field in (("water_volume_m3", "volume_m3"), ("water_depth_m", "depth_m")):
            np.testing.assert_array_equal(s["forcing_" + field], a["trace_" + water_field][:-1])
        np.testing.assert_array_equal(s["forcing_water_outflow_m3_s"], a["trace_outflow_q_m3_s"])
        np.testing.assert_array_equal(s["forcing_external_solid_m3_s"], a["trace_local_q_m3_s"] * inputs["external_solid_concentration_m3_per_m3"])
        local = restrict_inventory(a["forcing_local_q_m3_s"], case.parent_index, native.receiver.size)
        np.testing.assert_allclose(local, forcing.local_q_m3_s, rtol=0., atol=1e-14)
        dt = np.diff(a["trace_time_seconds"])
        receiver = case.network.receiver
        incoming = np.zeros_like(a["trace_outflow_q_m3_s"])
        solid_incoming = np.zeros_like(s["step_outgoing_solid_m3"])
        interfaces = []
        for donor, target in enumerate(receiver):
            if target >= 0:
                incoming[:, target] += a["trace_outflow_q_m3_s"][:, donor]
                solid_incoming[:, target] += s["step_outgoing_solid_m3"][:, donor]
                if case.counts[case.parent_index[donor]] != case.counts[case.parent_index[target]]:
                    interfaces.append({"donor": donor, "receiver": int(target),
                        "water_transferred_m3": float(np.sum(dt * a["trace_outflow_q_m3_s"][:, donor])),
                        "solid_transferred_m3": float(s["step_outgoing_solid_m3"][:, donor].sum())})
        np.testing.assert_allclose(incoming, a["trace_inflow_q_m3_s"], rtol=0., atol=1e-12)
        np.testing.assert_allclose(solid_incoming, s["step_incoming_solid_m3"], rtol=0., atol=1e-12)
        residual = np.diff(a["trace_volume_m3"], axis=0) - dt[:, None] * (a["trace_local_q_m3_s"] + incoming - a["trace_outflow_q_m3_s"])
        water_balance = float(a["trace_volume_m3"][0].sum() + np.sum(dt[:, None] * a["trace_local_q_m3_s"]) - a["trace_boundary_outflow_volume_m3"].sum() - a["trace_volume_m3"][-1].sum())
        solid_balance = float((s["trace_mobile_solid_m3"][0] + s["trace_bed_alluvium_solid_m3"][0]).sum() + s["step_external_solid_m3"].sum() + s["step_eroded_rock_m3"].sum() - s["step_exported_solid_m3"].sum() - (s["trace_mobile_solid_m3"][-1] + s["trace_bed_alluvium_solid_m3"][-1]).sum())
        for quantity in ("volume_m3",):
            restricted = restrict_inventory(a["trace_" + quantity], case.parent_index, native.receiver.size)
            np.testing.assert_allclose(restricted.sum(axis=1), a["trace_" + quantity].sum(axis=1), rtol=1e-12, atol=1e-12)
        for quantity in ("mobile_solid_m3", "bed_alluvium_solid_m3", "rock_removed_m3"):
            restricted = restrict_inventory(s["trace_" + quantity], case.parent_index, native.receiver.size)
            np.testing.assert_allclose(restricted.sum(axis=1), s["trace_" + quantity].sum(axis=1), rtol=1e-12, atol=1e-12)
        metrics[name] = _metrics(waters[name], solids[name], case, native)
        for field, value in metrics[name]["resource"].items():
            if report["resource"][field] != value:
                raise ValueError("saved resource metric differs from trace: " + field)
        for field, value in metrics[name].items():
            if field != "resource" and value != report[field]:
                raise ValueError("saved comparison metric differs from traces: " + field)
        results[name] = {"water_residual_m3": water_balance, "solid_residual_m3": solid_balance,
            "max_cell_water_residual_m3": float(np.abs(residual).max(initial=0.)),
            "mixed_interfaces": interfaces, "source_restriction_max_error_m3_s": float(np.abs(local - forcing.local_q_m3_s).max()),
            "status": report["status"], "sediment_status": report["sediment_status"]}
    if comparison_metrics(metrics) != payload["comparison"]:
        raise ValueError("comparison differences mismatch")
    complete = all(report["status"] == "complete" and report["sediment_status"] == "complete" for report in payload["cases"].values())
    return {"schema": SCHEMA, "status": "accepted_conservative_1d_exchange" if complete else "accepted_committed_prefix_exchange",
        "resolution_agreement": "measured_unresolved", "solver_invoked": False, "cases": results}
