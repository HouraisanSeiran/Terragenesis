"""Cold-read actual-section storage and paired water/tracer ledgers; no solver."""

import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from shapely.geometry import Polygon, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, checked_path, check_identity, check_memory, digest, file_sha256,
    read, read_audit, require)

AUDIT_SCHEMA = "td-hybrid-river-hydraulics-independent-audit-v1"
LEDGER_COLUMNS = ["source_in_m3", "outlet_water_out_m3", "tailwater_water_in_m3",
                  "source_tracer_out_m3", "tailwater_tracer_in_m3", "tailwater_tracer_out_m3"]
ARRAY_KEYS = ("water_volume_m3", "source_tracer_mass_m3", "tailwater_tracer_mass_m3")
LINK_KEYS = ("paired_link_water_integral_m3", "paired_link_source_integral_m3",
             "paired_link_tailwater_integral_m3")


def section_area(section, head):
    if section["kind"] == "open_polyline":
        area = 0.0
        points = section["polyline_transverse_elevation_m"]
        for first, second in zip(points[:-1], points[1:]):
            width = second[0] - first[0]
            require(width > 0, "unordered actual surface section")
            first_depth, second_depth = head - first[1], head - second[1]
            if min(first_depth, second_depth) >= 0:
                area += width * (first_depth + second_depth) / 2
            elif max(first_depth, second_depth) > 0:
                positive_depth = max(first_depth, second_depth)
                area += width * positive_depth**2 / (2 * abs(first_depth - second_depth))
        return area
    require(section["kind"] == "closed_polygon", "unexpected actual section kind")
    points = np.asarray(section["polygon_transverse_elevation_m"], dtype=float)
    origin = points[0]
    polygon = Polygon(points - origin)
    require(polygon.is_valid and polygon.area > 0, "invalid final VDM polygon")
    floor, crown = points[:, 1].min(), points[:, 1].max()
    if head <= floor:
        return 0.0
    if head >= crown:
        return polygon.area + section["pressure_slot_width_m"] * (head - crown)
    lower_x, lower_y, upper_x, upper_y = polygon.bounds
    return polygon.intersection(box(lower_x - 1, lower_y - 1, upper_x + 1, head - origin[1])).area


def array(record, key, shape):
    result = np.asarray(record[key], dtype=float)
    require(result.shape == shape and np.isfinite(result).all(), "invalid saved array: " + key)
    return result


def check_result(record, geometry, parameters):
    check_identity(record)
    require(record["parameters"] == parameters and record["parameters_identity_sha256"] == digest(parameters),
            "saved experiment differs from explicit configuration")
    cells, links = geometry["hydraulic_cells"], geometry["hydraulic_links"]
    count, times = len(cells), np.asarray(record["times_s"], dtype=float)
    require(3 <= count <= 64 and len(links) == count - 1, "invalid bounded physical chain")
    require(record["cell_ids"] == [cell["cell_id"] for cell in cells]
            and record["link_ids"] == [link["link_id"] for link in links], "actual geometry ownership mismatch")
    require(times.tolist() == parameters["saved_times_s"] and 2 <= len(times) <= 4096
            and np.isfinite(times).all() and times[0] == 0 and times[-1] == parameters["duration_s"]
            and np.all(np.diff(times) > 0), "physical saved-time mismatch")
    shape = (len(times), count)
    volumes, source, tailwater = [array(record, key, shape) for key in ARRAY_KEYS]
    heads = array(record, "hydraulic_head_m", shape)
    initial = array(record, "initial_untraced_water_m3", (count,))
    require(np.all(volumes > 0) and np.all(source >= 0) and np.all(tailwater >= 0)
            and np.all(source + tailwater <= volumes + 1e-7), "positivity/tracer composition mismatch")
    require(np.max(abs(volumes[0] - initial)) <= 1e-9 and np.max(abs(source[0])) == 0
            and np.max(abs(tailwater[0])) == 0, "initial storage/tracer origin mismatch")
    ledgers = array(record, "boundary_ledger_m3", (len(times), 6))
    require(record["ledger_columns"] == LEDGER_COLUMNS and np.max(abs(ledgers[0])) == 0
            and np.all(ledgers >= -1e-9) and np.all(np.diff(ledgers, axis=0) >= -1e-9),
            "invalid cumulative boundary ledger")
    link_integrals = [array(record, key, (len(times), count - 1)) for key in LINK_KEYS]
    require(all(np.max(abs(integral[0])) == 0 for integral in link_integrals), "nonzero initial internal exchange")
    require(np.max(abs(ledgers[:, 2] - ledgers[:, 4])) <= 1e-9, "tailwater inlet attribution mismatch")
    expected_source = np.minimum(times, parameters["pulse_duration_s"]) * parameters["pulse_q_m3_s"]
    require(np.max(abs(ledgers[:, 0] - expected_source)) <= 1e-6, "duplicate/missing prescribed pulse source")
    tolerance = 1e-4
    residuals = []
    for stored, initial_storage, integral, incoming, outgoing in (
            (volumes, initial, link_integrals[0], ledgers[:, 0], ledgers[:, 1] - ledgers[:, 2]),
            (source, np.zeros(count), link_integrals[1], ledgers[:, 0], ledgers[:, 3]),
            (tailwater, np.zeros(count), link_integrals[2], np.zeros(len(times)), ledgers[:, 5] - ledgers[:, 4])):
        expected = np.tile(initial_storage, (len(times), 1))
        expected[:, 0] += incoming
        expected[:, -1] -= outgoing
        expected[:, :-1] -= integral
        expected[:, 1:] += integral
        residuals.append(float(np.max(abs(stored - expected))))
    require(max(residuals) <= tolerance, "per-cell paired water/tracer conservation failed")
    area_error = 0.0
    pressure_count = 0
    compliance_volume = np.zeros(len(times))
    max_pressure_excess = 0.0
    max_engineered_bank_excess = 0.0
    overbank_count = 0
    for ordinal, cell in enumerate(cells):
        require(cell["length_m"] > 0, "invalid actual storage length")
        section = cell["section"]
        for row, head in enumerate(heads[:, ordinal]):
            area_error = max(area_error, abs(section_area(section, head) * cell["length_m"] - volumes[row, ordinal]))
            closed = section["kind"] == "closed_polygon"
            crown = max(point[1] for point in section["polygon_transverse_elevation_m"]) if closed else math.inf
            pressurized = closed and head > crown
            if closed:
                excess = max(0.0, head - crown)
                max_pressure_excess = max(max_pressure_excess, excess)
                compliance_volume[row] += section["pressure_slot_width_m"] * excess * cell["length_m"]
            else:
                bank = max(point[1] for point in section["polyline_transverse_elevation_m"])
                bank_excess = max(0.0, head - bank)
                max_engineered_bank_excess = max(max_engineered_bank_excess, bank_excess)
                overbank_count += int(bank_excess > 0)
            actual_stage = record["open_channel_stage_m"][row][ordinal]
            actual_pressure = record["pressurized_head_m"][row][ordinal]
            require((actual_stage is None) == pressurized and (actual_pressure is not None) == pressurized,
                    "pressure head mislabeled as open water surface")
            value = actual_pressure if pressurized else actual_stage
            require(abs(value - head) <= 1e-9, "stage/head value mismatch")
            pressure_count += int(pressurized)
    require(area_error <= 1e-7, "saved inventory does not match actual VDM/open-section geometry")
    threshold = parameters["source_arrival_threshold_m3"]
    arrival_indices = np.flatnonzero(source[:, -1] >= threshold)
    arrival_time = float(times[arrival_indices[0]]) if len(arrival_indices) else None
    sink_index = next(ordinal for ordinal, link in enumerate(links) if link["kind"] == "sink_exchange")
    reached_outlet = bool(ledgers[-1, 3] >= threshold)
    reverse_sink = bool(-link_integrals[0][-1, sink_index] > threshold and tailwater[-1, 0] >= threshold)
    require(record["source_arrival_time_s"] == arrival_time and record["source_reached_engineered_outlet"] == reached_outlet
            and record["reverse_reached_sink"] == reverse_sink, "source/return arrival claim mismatch")
    require(record["boundary_scope"] == "positively_wet_prescribed_tailwater_only_no_dry_free_outfall",
            "unsupported hydraulic boundary scope")
    for flag in ("natural_outlet_certified", "full_network_verified", "finite_speed_front_verified", "three_dimensional_flow_solved"):
        require(record[flag] is False, "unjustified promotion: " + flag)
    for segment in record["integration_segments"]:
        require(0 < segment["max_adaptive_step_s"] <= parameters["max_step_s"] + 1e-9
                and segment["accepted_steps"] > 0, "saved integrator step contract mismatch")
    work = record["work"]
    require(work["rhs_evaluations"] <= parameters["max_rhs_evaluations"]
            and work["link_evaluations"] == work["rhs_evaluations"] * count
            and work["link_evaluations"] <= parameters["max_link_evaluations"]
            and work["actual_peak_rss_bytes"] <= 1024**3
            and work["wall_seconds"] <= parameters["max_wall_seconds"]
            and work["old_hll_face_work"] == 0 and work["old_hll_face_budget_remaining_unchanged"] == 2_949_448_968,
            "saved resource/work contract failed")
    return {"max_per_cell_water_residual_m3": residuals[0], "max_per_cell_source_residual_m3": residuals[1],
            "max_per_cell_tailwater_residual_m3": residuals[2], "conservation_tolerance_m3": tolerance,
            "max_actual_section_volume_difference_m3": area_error, "pressurized_saved_cell_count": pressure_count,
            "max_pressure_above_actual_crown_m": max_pressure_excess,
            "max_engineered_stage_above_section_bank_m": max_engineered_bank_excess,
            "overbank_saved_cell_count": overbank_count,
            "pressure_slot_compliance_volume_m3": compliance_volume.tolist(),
            "max_pressure_slot_compliance_volume_m3": float(compliance_volume.max()),
            "initial_untraced_water_m3": float(initial.sum()), "source_in_m3": float(ledgers[-1, 0]),
            "source_arrival_time_s": arrival_time, "source_outlet_m3": float(ledgers[-1, 3]),
            "source_export_fraction": float(ledgers[-1, 3] / ledgers[-1, 0]) if ledgers[-1, 0] else None,
            "outlet_water_out_m3": float(ledgers[-1, 1]), "tailwater_water_in_m3": float(ledgers[-1, 2]),
            "tailwater_arrived_first_surface_m3": float(tailwater[-1, 0]),
            "source_reached_engineered_outlet": reached_outlet, "reverse_reached_sink": reverse_sink}


def compare_saved(base, refined):
    require(base["cell_ids"] == refined["cell_ids"] and base["times_s"] == refined["times_s"], "unaligned refinement")
    head_error = float(np.max(abs(np.asarray(base["hydraulic_head_m"]) - refined["hydraulic_head_m"])))
    volume_error = float(np.max(abs(np.asarray(base["water_volume_m3"]) - refined["water_volume_m3"])))
    relative_error = float(np.max(abs(np.asarray(base["water_volume_m3"]) - refined["water_volume_m3"]) / refined["water_volume_m3"]))
    tracer_error = max(float(np.max(abs(np.asarray(base[key]) - refined[key]))) for key in ARRAY_KEYS[1:] + ("boundary_ledger_m3",))
    link_l1 = {}
    for key in LINK_KEYS:
        first, second = np.asarray(base[key]), np.asarray(refined[key])
        absolute = float(np.sum(abs(first - second)))
        denominator = float(np.sum(abs(second)))
        require(absolute <= 1e-4 + .01 * denominator, "paired link refinement failed: " + key)
        link_l1[key] = absolute / denominator if denominator else None
    require(head_error <= .001 and volume_error <= 1e-4 and relative_error <= .01 and tracer_error <= 1e-4,
            "saved 1mm/1percent refinement failed")
    return {"max_head_difference_m": head_error, "max_volume_difference_m3": volume_error,
            "max_relative_volume_difference": relative_error, "max_tracer_ledger_difference_m3": tracer_error,
            "paired_link_relative_l1": link_l1}


def audit(index_pin):
    index = read(index_pin)
    inputs = index["inputs"]
    graph = read(inputs["graph"])
    geometry = read(inputs["geometry"])
    geometry_audit = read_audit(inputs["geometry_audit"])
    configuration = read(inputs["experiments"])
    require(index["schema"] == "td-hybrid-river-hydraulics-preparation-v1", "wrong saved hydraulics schema")
    require(geometry_audit["status"] == "passed" and not geometry_audit.get("errors")
            and geometry_audit["geometry_sha256"] == inputs["geometry"]["sha256"]
            and geometry_audit["actual_hydraulic_sections_verified"] and geometry_audit["actual_portal_connections_verified"],
            "unverified actual geometry input")
    for record in (index, geometry, configuration):
        require(record["graph_identity_sha256"] == graph["identity_sha256"], "parent graph mismatch")
    require(index["geometry_identity_sha256"] == geometry["identity_sha256"]
            and configuration["geometry_identity_sha256"] == geometry["identity_sha256"], "parent geometry mismatch")
    for pin in graph["inputs"].values():
        checked_path(pin)
    for pin in geometry["inputs"].values():
        checked_path(pin)
    for parent in (geometry, geometry_audit):
        for field in ("code_sha256", "audit_code_sha256", "readonly_dependency_code_sha256"):
            for name, sha in parent.get(field, {}).items():
                require(file_sha256(ROOT / name) == sha, "frozen geometry/audit dependency changed: " + name)
    for name, sha in index["code_sha256"].items():
        require(file_sha256(ROOT / name) == sha, "frozen solver code changed: " + name)
    scenarios = {row["scenario"]: row for row in configuration["scenarios"]}
    require(set(scenarios) == {"pulse", "reverse_tailwater"}, "wrong engineering scenarios")
    reports = {}
    for scenario, parameters in scenarios.items():
        base = read(index["artifacts"][scenario + "-base.json"])
        refined = read(index["artifacts"][scenario + "-refined.json"])
        for record in (base, refined):
            require(record["inputs"] == inputs and record["graph_identity_sha256"] == graph["identity_sha256"]
                    and record["geometry_identity_sha256"] == geometry["identity_sha256"], "result/input binding mismatch")
        refined_parameters = {**parameters, "max_step_s": parameters["max_step_s"] / 2,
                              "relative_tolerance": parameters["relative_tolerance"] / 4,
                              "absolute_tolerance": parameters["absolute_tolerance"] / 4}
        base_report = check_result(base, geometry, parameters)
        refined_report = check_result(refined, geometry, refined_parameters)
        refinement = compare_saved(base, refined)
        required = "source_reached_engineered_outlet" if scenario == "pulse" else "reverse_reached_sink"
        require(base_report[required] and refined_report[required], "missing actual arrival evidence: " + scenario)
        meaningful_key = "source_outlet_m3" if scenario == "pulse" else "tailwater_arrived_first_surface_m3"
        meaningful_minimum = max(1.0, base_report["source_in_m3"] * .001) if scenario == "pulse" else 1.0
        require(base_report[meaningful_key] >= meaningful_minimum and refined_report[meaningful_key] >= meaningful_minimum,
                "threshold arrival is insufficient meaningful transported volume: " + scenario)
        for record, report in ((base, base_report), (refined, refined_report)):
            times = np.asarray(record["times_s"])
            ledgers = np.asarray(record["boundary_ledger_m3"])
            late_index = int(np.searchsorted(times, times[-1] - 100, side="left"))
            report["late_100s_source_export_m3"] = float(ledgers[-1, 3] - ledgers[late_index, 3])
            if scenario == "pulse":
                require(report["late_100s_source_export_m3"] >= .5, "no meaningful late-window source transport")
        refined_report["meaningful_transport_minimum_m3"] = meaningful_minimum
        reports[scenario] = {"base": base_report, "refined": refined_report, "refinement": refinement}
        check_memory()
    return {"schema": AUDIT_SCHEMA, "status": "passed", "errors": [], "index_sha256": index_pin["sha256"],
            "inputs": inputs, "reports": reports, "actual_section_storage_verified": True,
            "paired_per_cell_water_and_tracers_verified": True, "time_refinement_verified": True,
            "scope": "saved_finite_1d_diffusive_storage_and_two_engineering_events_not_independent_momentum_solver",
            "natural_outlet_certified": False, "full_network_verified": False, "three_dimensional_flow_solved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "new independent audit output required")
    started = time.monotonic()
    index_pin = {"path": str(args.input.resolve()), "sha256": args.sha256}
    try:
        report = audit(index_pin)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {"schema": AUDIT_SCHEMA, "status": "refused", "index_sha256": args.sha256,
                  "errors": [str(error)], "natural_outlet_certified": False}
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory()}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_river_hydraulics.py", "tools/td_shared_channel_fine_saved_audit.py",
        "tests/test_hybrid_river_hydraulics_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "independent audit exceeds file limit")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(json.dumps(report, ensure_ascii=True))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
