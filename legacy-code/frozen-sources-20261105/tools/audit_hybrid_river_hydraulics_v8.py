"""Independent local-frame reconstruction plus frozen per-cell hydraulic checks."""

import argparse
import copy
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

from tools.audit_hybrid_river_hydraulics import (
    AUDIT_SCHEMA, accuracy_parameters, check_case_binding, check_result,
    check_same_physics, compare_saved, physical_identity)
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, checked_path, check_memory, digest, file_sha256, read, read_audit, require)

NUMERICAL_VERSION = "three_origin_local_vertical_frame_analytic_Radau_precision-v8"


def local_geometry(geometry, datum):
    local = copy.deepcopy(geometry)
    for cell in local["hydraulic_cells"]:
        section = cell["section"]
        key = "polygon_transverse_elevation_m" if section["kind"] == "closed_polygon" else "polyline_transverse_elevation_m"
        require(section["kind"] in ("open_polyline", "closed_polygon"), "local frame requires actual polygon/polyline sections")
        section[key] = [[point[0], point[1] - datum] for point in section[key]]
    return local


def expected_frame(geometry):
    floors = []
    for cell in geometry["hydraulic_cells"]:
        section = cell["section"]
        points = section.get("polygon_transverse_elevation_m", section.get("polyline_transverse_elevation_m"))
        require(points is not None, "actual section floor not supplied")
        floors.append(min(point[1] for point in points))
    return {"schema": "td-hybrid-river-local-vertical-frame-v8", "datum_m": math.floor(min(floors)),
            "datum_policy": "floor_minimum_actual_section_floor_m",
            "computation": "one_common_local_frame_before_inverse_friction_flux_and_Jacobian",
            "output": "global_head_equals_datum_plus_local_head", "source_geometry_unchanged": True,
            "tiny_flux_deadband": False}


def check_frame(record, geometry, parameters):
    expected = expected_frame(geometry)
    require(record["numerical_frame"] == expected, "wrong/non-common local vertical datum policy")
    local_heads = np.asarray(record["local_hydraulic_head_m"], dtype=float)
    global_heads = np.asarray(record["hydraulic_head_m"], dtype=float)
    require(local_heads.shape == global_heads.shape == (len(record["times_s"]), len(geometry["hydraulic_cells"]))
            and np.isfinite(local_heads).all() and np.isfinite(global_heads).all()
            and np.array_equal(global_heads, local_heads + expected["datum_m"]),
            "global/local head output mismatch")
    require(record["local_tailwater_head_m"] == parameters["tailwater_head_m"] - expected["datum_m"]
            and record["execution_progress"]["numerical_frame"] == expected,
            "local tailwater/progress not bound to common frame")
    return expected, local_heads


def projected_result(record, geometry, parameters):
    frame, heads = check_frame(record, geometry, parameters)
    datum = frame["datum_m"]
    projected = copy.deepcopy(record)
    projected["schema"] = "td-hybrid-river-hydraulics-v6"
    projected["numerical_version"] = "three_origin_analytic_native_chain_Radau-v6"
    projected["hydraulic_head_m"] = heads.tolist()
    for key in ("open_channel_stage_m", "pressurized_head_m"):
        projected[key] = [[float(head) if original is not None else None for original, head in zip(row, local_row)]
                          for row, local_row in zip(record[key], heads)]
        for global_row, local_row in zip(record[key], projected[key]):
            require(all(global_value is None or global_value == local_value + datum
                        for global_value, local_value in zip(global_row, local_row)),
                    "global stage/pressure output not bound to local head")
    for ordinal, snapshot in enumerate(projected["saved_section_diagnostics"]):
        for column, cell in enumerate(snapshot["cells"]):
            require(cell["head_m"] == record["hydraulic_head_m"][ordinal][column]
                    and cell["local_head_m"] == float(heads[ordinal, column]),
                    "section probe has unbound global/local head")
            section = geometry["hydraulic_cells"][column]["section"]
            if section["kind"] == "closed_polygon":
                require(cell["crown_m"] == max(point[1] for point in section["polygon_transverse_elevation_m"]),
                        "section probe crown not in source global frame")
            else:
                points = section["polyline_transverse_elevation_m"]
                require(cell["low_bank_m"] == min(points[0][1], points[-1][1]),
                        "section probe bank not in source global frame")
            cell["head_m"] = float(heads[ordinal, column])
    local_parameters = {**parameters, "initial_heads_m": [value - datum for value in parameters["initial_heads_m"]],
                        "tailwater_head_m": parameters["tailwater_head_m"] - datum}
    require(record["local_solver_parameters"] == local_parameters
            and record["local_solver_parameters_identity_sha256"] == digest(local_parameters),
            "local solver parameters changed forcing/precision or mixed datum")
    projected["parameters"] = local_parameters
    projected["parameters_identity_sha256"] = digest(local_parameters)
    projected.pop("identity_sha256", None)
    projected["identity_sha256"] = digest(projected)
    return projected, local_geometry(geometry, datum), local_parameters


def check_accuracy(index, model):
    expected = {"schema": "td-hybrid-river-accuracy-policy-v8", "integration": "Radau",
                "forcing_configuration_pin_unchanged": True,
                "parameter_transform": {
                    "base": {"relative_tolerance_divisor": 64, "absolute_tolerance_divisor": 64, "max_step_divisor": 4},
                    "refined": {"relative_tolerance_divisor": 256, "absolute_tolerance_divisor": 256, "max_step_divisor": 8}},
                "unchanged_scope": "all_other_pinned_Experiment_parameters_initial_geometry_slot_forcing_and_guards",
                "comparison_gates_unchanged": {"volume_absolute_tolerance_m3": 1e-4,
                                              "head_absolute_tolerance_m": 1e-3, "volume_relative_tolerance": .01,
                                              "paired_and_origin_absolute_tolerance_m3": 1e-4},
                "reused_cases_allowed": False, "precision_change_not_physical_change": True}
    require(index["integration"] == model["integration"] == "Radau"
            and index["accuracy_policy"] == model["accuracy_policy"] == expected
            and index["reused_cases"] == {}, "unbound local-frame accuracy policy")


def audit(index_pin):
    index = read(index_pin)
    require(index["schema"] == "td-hybrid-river-hydraulics-preparation-v8"
            and index["status"] == "diagnostic_accepted", "unfinished/refused local-frame batch cannot be accepted")
    cases = {scenario + "-" + level for scenario in ("pulse", "reverse_tailwater") for level in ("base", "refined")}
    require(set(index["completed_cases"]) == set(index["generated_cases"]) == cases
            and len(index["completed_cases"]) == 4 and set(index["artifacts"]) == {name + ".json" for name in cases},
            "local-frame batch missing complete cases")
    inputs = index["inputs"]
    graph, geometry, configuration = [read(inputs[key]) for key in ("graph", "geometry", "experiments")]
    geometry_audit = read_audit(inputs["geometry_audit"])
    model = read(index["hydraulic_model_parameters"])
    require(geometry_audit["status"] == "passed" and not geometry_audit["errors"]
            and geometry_audit["geometry_sha256"] == inputs["geometry"]["sha256"]
            and geometry_audit["actual_hydraulic_sections_verified"] is True
            and geometry_audit["actual_portal_connections_verified"] is True, "unbound/unverified actual geometry")
    from tools.prepare_hybrid_river_hydraulics_v8 import source_identity
    current_code, historical_code = source_identity()
    require(model.get("source_layout") == index.get("source_layout") == "explicit_common_radau_v8_20261023"
            and model.get("frozen_reference_code_sha256") == index.get("frozen_reference_code_sha256") == historical_code
            and index["code_sha256"] == current_code,
            "current source identity mismatch; historical batches require explicit legacy replay")
    require(model["schema"] == "td-hybrid-river-hydraulic-model-parameters-v8"
            and model["model_version"] == index["model_version"] == "explicit_roof_friction_contact_transition-v5"
            and model["numerical_version"] == index["numerical_version"] == NUMERICAL_VERSION
            and model["code_sha256"] == index["code_sha256"] == current_code
            and model["forcing_configuration_pin"] == inputs["experiments"]
            and model["graph_identity_sha256"] == index["graph_identity_sha256"] == graph["identity_sha256"]
            and model["geometry_identity_sha256"] == index["geometry_identity_sha256"] == geometry["identity_sha256"]
            and model["physical_model_identity_sha256"] == index["physical_model_identity_sha256"] == physical_identity(model)
            and model["numerical_frame"] == index["numerical_frame"] == expected_frame(geometry)
            and model["friction_policy"] == index["friction_policy"]
            and model["jacobian_policy"] == index["jacobian_policy"]
            and model["model_parameters"] == {"head_regularization_m": 1e-4, "donor_regularization_m3": 1e-6}
            and index["diagnostic_stop_s"] is None and not index["diagnostic_artifacts"],
            "unbound local-frame physical/numerical model")
    for parent in (index, geometry, geometry_audit):
        for field in ("code_sha256", "audit_code_sha256", "readonly_dependency_code_sha256"):
            for name, sha in parent.get(field, {}).items():
                require(file_sha256(ROOT / name) == sha, "frozen dependency changed: " + name)
    for parent in (graph, geometry):
        for pin in parent["inputs"].values():
            checked_path(pin)
    require(configuration["graph_identity_sha256"] == graph["identity_sha256"]
            and configuration["geometry_identity_sha256"] == geometry["identity_sha256"], "wrong actual forcing parents")
    check_same_physics()
    check_accuracy(index, model)
    resource = index["resource"]
    require(resource["whole_event_not_split_or_restarted"] is False
            and resource["one_complete_forcing_event_budget_no_work_or_wall_reset"] is True
            and resource["observation_times_reinitialize_Radau"] is True
            and resource["negative_inventory_rollback_reinitializes_Radau_with_same_event_budget"] is True,
            "hidden local-frame observation reset or changed budget")
    parameters_by_scenario = {row["scenario"]: row for row in configuration["scenarios"]}
    require(set(parameters_by_scenario) == {"pulse", "reverse_tailwater"}, "wrong engineering scenarios")
    reports = {}
    new_rhs, new_links = 0, 0
    for scenario, original in parameters_by_scenario.items():
        require(index["input_parameter_identities"][scenario] == digest(original), "original forcing identity changed")
        pair, pair_reports = [], []
        for level in ("base", "refined"):
            name = scenario + "-" + level
            record = read(index["artifacts"][name + ".json"])
            parameters = accuracy_parameters(original, level)
            check_case_binding(record, index, model, name)
            require(record["schema"] == "td-hybrid-river-hydraulics-v8"
                    and record["parameters"] == parameters and record["parameters_identity_sha256"] == digest(parameters)
                    and record["input_parameters_identity_sha256"] == digest(original)
                    and record["inputs"] == inputs and record["accuracy_level"] == level
                    and record["accuracy_policy"] == index["accuracy_policy"]
                    and record["integration"] == "Radau" and record["inventory_policy"] == model["inventory_policy"]
                    and record["graph_identity_sha256"] == graph["identity_sha256"]
                    and record["geometry_identity_sha256"] == geometry["identity_sha256"]
                    and record["physical_model_identity_sha256"] == physical_identity(model)
                    and record["section_adapter_schema"] == index["section_adapter_schema"] == "td-hybrid-river-fast-sections-v2",
                    "unbound local-frame saved case/accuracy/source")
            projected, local, local_parameters = projected_result(record, geometry, parameters)
            report = check_result(projected, local, local_parameters)
            report["local_frame_flux_independently_verified"] = True
            report["datum_m"] = index["numerical_frame"]["datum_m"]
            times = record["times_s"]
            late_start = times[-1] - 100
            require(late_start in times, "missing exact late-window observation")
            report["late_100s_source_export_m3"] = record["boundary_ledger_m3"][-1][3] - record["boundary_ledger_m3"][times.index(late_start)][3]
            if scenario == "pulse":
                require(report["source_reached_engineered_outlet"] and report["source_outlet_m3"] >= 2.7
                        and report["late_100s_source_export_m3"] >= .5, "insufficient real source transport")
            else:
                require(report["reverse_reached_sink"] and report["tailwater_arrived_first_surface_m3"] >= 1,
                        "insufficient actual return flow")
            pair.append(projected)
            pair_reports.append(report)
            new_rhs += record["work"]["rhs_evaluations"]
            new_links += record["work"]["link_evaluations"]
        reports[scenario] = {"base": pair_reports[0], "refined": pair_reports[1], "refinement": compare_saved(*pair)}
        check_memory()
    require(index["work"]["new_1d_rhs_evaluations"] == new_rhs
            and index["work"]["new_1d_link_evaluations"] == new_links
            and index["work"]["old_hll_face_work"] == 0, "wrong complete event work ledger")
    return {"schema": AUDIT_SCHEMA, "status": "passed", "errors": [], "index_sha256": index_pin["sha256"],
            "inputs": inputs, "reports": reports, "actual_section_storage_verified": True,
            "paired_per_cell_water_and_tracers_verified": True, "time_refinement_verified": True,
            "numerical_frame": index["numerical_frame"], "accuracy_policy": index["accuracy_policy"],
            "numerical_version": NUMERICAL_VERSION, "local_frame_flux_independently_verified": True,
            "scope": "saved_finite_1d_diffusive_storage_two_engineering_events_in_common_local_vertical_frame",
            "projection_semantics": "in_memory_local_geometry_and_inventory_projection_into_frozen_v6_checks_original_cases_unmodified",
            "continuous_between_steps_positivity_certified": False, "natural_outlet_certified": False,
            "full_network_verified": False, "three_dimensional_flow_solved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification audit output required")
    started = time.monotonic()
    index_pin = {"path": str(args.input.resolve()), "sha256": args.sha256}
    try:
        report = audit(index_pin)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {"schema": AUDIT_SCHEMA, "status": "refused", "index_sha256": args.sha256,
                  "errors": [str(error)], "natural_outlet_certified": False}
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory()}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_river_hydraulics_v8.py", "tools/audit_hybrid_river_hydraulics.py",
        "tools/td_shared_channel_fine_saved_audit.py", "tests/test_hybrid_river_hydraulics_saved_audit.py",
        "tests/test_hybrid_river_hydraulics_v8_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "independent audit file budget exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    summary = {scenario: values["refinement"] for scenario, values in report.get("reports", {}).items()}
    print(json.dumps({"status": report["status"], "errors": report["errors"], "output": str(output),
                      "sha256": file_sha256(output), "refinement": summary}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
