"""Independent BDF precision experiment: unchanged forcing/physics, four new cases, no reuse."""

from dataclasses import asdict, replace
import argparse
import json
import math
import numpy as np
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_river_graph import MAX_FILE_BYTES, canonical_json, identity, read_pinned
from terrain_pipeline.hybrid_river_hydraulics import Experiment, compare_refinement
from terrain_pipeline.hybrid_river_hydraulics_v7 import (
    INTEGRATION, MODEL_VERSION, NUMERICAL_VERSION, HydraulicDiagnosticStop, HydraulicExecutionFailure, inventory_policy, jacobian_policy, run_experiment)
from terrain_pipeline.hybrid_river_sections_v2 import SCHEMA as SECTION_SCHEMA, accelerate_model
from tools.prepare_hybrid_river_hydraulics import file_sha, pin, validate_geometry

SCHEMA = "td-hybrid-river-hydraulics-preparation-v7"
FROZEN_CODE = {
    "terrain_pipeline/hybrid_river_graph.py": "063b2a3d037f366647aeb585161834a44a5eb18301dee919bb76b2b24052f8f6",
    "terrain_pipeline/hybrid_river_hydraulics.py": "896abd3ef8ec79bbbbdfe3638076361b83f2c2b61a1b0405378711366e372649",
    "tools/prepare_hybrid_river_hydraulics.py": "90a77f2813a33836787de400e45ce968b9f1a50369079bb6f7669b38a0e9f810",
    "tests/test_hybrid_river_graph.py": "a59b7ee534c3b74da2d9e513772bb0e703486f705d00f577ab2e64099aa28010",
    "tests/test_hybrid_river_hydraulics.py": "05de70386884fcb6e74a82c445ebf1a940c3048b17dd3eea362fa5103c2f96cf",
    "terrain_pipeline/hybrid_river_sections_v2.py": "a2dc77c77eee42620c8dd43822b48a40a30ba6dec8a957b8c25caed4ba4fe4ac",
    "tools/prepare_hybrid_river_hydraulics_v2.py": "bae884207976be09c341e3dfdf148cc4bd53ea63681b7492e5bbd9ea031b2829",
    "tests/test_hybrid_river_sections_v2.py": "b148f8c26c16721f4c187a714f8184452b6ba640ace21eca589f00515573ab8b",
    "terrain_pipeline/hybrid_river_hydraulics_v3.py": "472f3114a235d8c68fe449b4a514beceb8069853722abeb1664c822473a7311d",
    "tools/prepare_hybrid_river_hydraulics_v3.py": "a5a39e40b89eee6de525f50b3475f34e2036f4737f3f39dd061ccb389f0c9301",
    "tests/test_hybrid_river_hydraulics_v3.py": "d1e6dd64db328de47c21d586363781ccfa2a7b50f850131e02280e0a81f81b2a",
    "terrain_pipeline/hybrid_river_hydraulics_v4.py": "18b34e7e505b786e3a8f0469ff9ce44fd337090eb9e71c7064167078e9c7cdcd",
    "tools/prepare_hybrid_river_hydraulics_v4.py": "b04920036fcc17ce7a3a681df1e1beb96efc5faf2aa5c2ca810e507e18d2465e",
    "tests/test_hybrid_river_hydraulics_v4.py": "afd1c59e756dfd7f9fa91b61adabc8fc5088ed346be7462b33e6aa7c5b74fb64",
    "terrain_pipeline/hybrid_river_hydraulics_v5.py": "b170ddc31f62cf0c2b369be1ac5cec2633cc33ffa636aefdc6295536e1153443",
    "tools/prepare_hybrid_river_hydraulics_v5.py": "7c9430b42d43f31a3f249ef4dd956aa2365e5bcd82ce30f60b91666e1b8100d1",
    "tests/test_hybrid_river_hydraulics_v5.py": "2bb9c3f1962e461eb4d8fb74cef2b49136d16dce334e1d5b44d2b8679a2d99eb",
    "terrain_pipeline/hybrid_river_hydraulics_v6.py": "851f387c19287db1eac37033c2f54c34a03528779be02bf0d66107874c0fbd44",
    "tools/prepare_hybrid_river_hydraulics_v6.py": "ca8db593c8163f2c0b354827fae4023d36589563cac2e1479252d34355be4f20",
    "tests/test_hybrid_river_hydraulics_v6.py": "57b3e9b1ff004af1acd3e148d42fc7c1a6517f64617df88ebadd44aa67254099",
}
NEW_CODE = ("terrain_pipeline/hybrid_river_hydraulics_v7.py", "tools/prepare_hybrid_river_hydraulics_v7.py", "tests/test_hybrid_river_hydraulics_v7.py")


def atomic_save(output, name, record):
    sealed = dict(record)
    sealed.pop("identity_sha256", None)
    sealed["identity_sha256"] = identity(sealed)
    payload = canonical_json(sealed).encode("utf-8")
    if len(payload) > MAX_FILE_BYTES:
        raise ValueError("bounded checkpoint JSON exceeded")
    descriptor, temporary = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=output)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output / name)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    return {"path": str(output / name), "sha256": file_sha(output / name), "identity_sha256": sealed["identity_sha256"]}


def meaningful_evidence(result):
    if result["scenario"] == "pulse":
        ordinal = result["ledger_columns"].index("source_tracer_out_m3")
        source_out = result["boundary_ledger_m3"][-1][ordinal]
        start = result["times_s"][-1] - 100.0
        observed = start in result["times_s"]
        recent = source_out - result["boundary_ledger_m3"][result["times_s"].index(start)][ordinal] if observed else None
        return {"passed": bool(source_out >= 2.7 and observed and recent >= 0.5),
                "source_tracer_out_m3": source_out, "source_tracer_out_last_100s_m3": recent,
                "last_100s_start_observed": observed, "minimum_source_out_m3": 2.7, "minimum_recent_source_out_m3": 0.5}
    returned = result["tailwater_tracer_mass_m3"][-1][0]
    return {"passed": bool(returned >= 1.0 and result["reverse_reached_sink"]),
            "tailwater_tracer_in_first_surface_cell_m3": returned, "minimum_returned_tailwater_m3": 1.0}


def paired_refinement(base, refined):
    fields = ("paired_link_water_integral_m3", "paired_link_source_integral_m3", "paired_link_tailwater_integral_m3",
              "paired_link_untraced_integral_m3", "untraced_water_volume_m3")
    if base["times_s"] != refined["times_s"] or base["link_ids"] != refined["link_ids"]:
        raise ValueError("paired-link refinement identities/times differ")
    differences = {}
    for key in fields:
        if len(base[key]) != len(refined[key]):
            raise ValueError("paired-link refinement shape differs")
        difference = 0.0
        for first, second in zip(base[key], refined[key]):
            if len(first) != len(second):
                raise ValueError("paired-link refinement shape differs")
            difference = max(difference, max(abs(left - right) for left, right in zip(first, second)))
        differences[key] = difference
    if len(base["outlet_untraced_out_m3"]) != len(refined["outlet_untraced_out_m3"]):
        raise ValueError("untraced outlet refinement shape differs")
    differences["outlet_untraced_out_m3"] = max(abs(first - second) for first, second in
                                               zip(base["outlet_untraced_out_m3"], refined["outlet_untraced_out_m3"]))
    return {"status": "passed" if max(differences.values()) <= 1e-4 else "refused",
            "absolute_tolerance_m3": 1e-4, "max_absolute_differences_m3": differences}


PHYSICAL_MODEL_FIELDS = ("model_version", "model_parameters", "friction_policy", "inventory_policy",
                         "forcing_configuration_pin", "graph_identity_sha256", "geometry_identity_sha256")


def physical_model_identity(record):
    return identity({key: record[key] for key in PHYSICAL_MODEL_FIELDS})


def accuracy_policy():
    return {"schema": "td-hybrid-river-accuracy-policy-v7", "integration": "BDF",
            "forcing_configuration_pin_unchanged": True,
            "parameter_transform": {
                "base": {"relative_tolerance_divisor": 64, "absolute_tolerance_divisor": 64, "max_step_divisor": 4},
                "refined": {"relative_tolerance_divisor": 256, "absolute_tolerance_divisor": 256, "max_step_divisor": 8}},
            "unchanged_scope": "all_other_pinned_Experiment_parameters_initial_geometry_slot_forcing_and_guards",
            "comparison_gates_unchanged": {"volume_absolute_tolerance_m3": 1e-4,
                                          "head_absolute_tolerance_m": 1e-3,
                                          "volume_relative_tolerance": 0.01,
                                          "paired_and_origin_absolute_tolerance_m3": 1e-4},
            "reused_cases_allowed": False, "precision_change_not_physical_change": True}


def precision_experiments(original):
    base = replace(original, relative_tolerance=original.relative_tolerance / 64,
                   absolute_tolerance=original.absolute_tolerance / 64, max_step_s=original.max_step_s / 4)
    refined = replace(original, relative_tolerance=original.relative_tolerance / 256,
                      absolute_tolerance=original.absolute_tolerance / 256, max_step_s=original.max_step_s / 8)
    return base, refined


def prepare(args):
    code = {name: file_sha(ROOT / name) for name in tuple(FROZEN_CODE) + NEW_CODE}
    if any(code[name] != expected for name, expected in FROZEN_CODE.items()):
        raise ValueError("frozen solver/graph/preparer/test code pin changed")
    pins = {name: pin(getattr(args, name), getattr(args, name + "_sha256")) for name in ("graph", "geometry", "geometry_audit", "experiments")}
    graph = read_pinned(pins["graph"])
    original_model, geometry = validate_geometry(graph, pins["geometry"], pins["geometry_audit"])
    model = accelerate_model(original_model)
    configuration = read_pinned(pins["experiments"])
    unsigned = dict(configuration)
    expected = unsigned.pop("identity_sha256")
    inputs = {name: asdict(value) for name, value in pins.items()}
    if configuration["schema"] != "td-hybrid-river-engineering-experiments-v1" or identity(unsigned) != expected:
        raise ValueError("pinned engineering configuration schema/identity mismatch")
    if (configuration["graph_identity_sha256"] != graph["identity_sha256"]
            or configuration["geometry_identity_sha256"] != geometry["identity_sha256"]
            or configuration["inputs"] != {name: inputs[name] for name in ("graph", "geometry", "geometry_audit")}):
        raise ValueError("pinned event differs from actual geometry/graph inputs")
    scenarios = configuration["scenarios"]
    if len(scenarios) != 2 or {parameters["scenario"] for parameters in scenarios} != {"pulse", "reverse_tailwater"}:
        raise ValueError("exactly the same pinned pulse/reverse events required")
    tolerances = configuration.get("refinement_tolerances", {})
    if tolerances.get("volume_absolute_tolerance_m3", 1e-4) > 1e-4:
        raise ValueError("per-cell absolute refinement cannot exceed 1e-4m3")
    experiments = []
    input_parameter_identities = {}
    for parameters in scenarios:
        original = Experiment(**{**parameters, "initial_heads_m": tuple(parameters["initial_heads_m"]), "saved_times_s": tuple(parameters["saved_times_s"])})
        original.validate(model)
        base, refined = precision_experiments(original)
        base.validate(model)
        refined.validate(model)
        experiments.append((base, refined))
        input_parameter_identities[original.scenario] = identity(asdict(original))
    if args.diagnostic_stop_s is None and args.crown_friction_transition_m == 0:
        raise ValueError("use a short diagnostic stop for legacy-law replay, or explicitly declare the new roof-friction transition")
    from terrain_pipeline.hybrid_river_hydraulics_v7 import validate_transition
    validate_transition(args.crown_friction_transition_m)
    if args.diagnostic_stop_s is not None and any(not 0 < args.diagnostic_stop_s <= experiment.duration_s for pair in experiments for experiment in pair):
        raise ValueError("short diagnostic must be inside the unchanged event")
    output = args.output.resolve()
    allowed = (ROOT / "verification" / "natural-river-network", ROOT / "verification" / "hybrid-river-network")
    if output.exists() or output.parent not in allowed:
        raise ValueError("new top-level verification package required; no overwrite/resume/repeated baseline")
    started = time.monotonic()
    model_parameters = {"schema": "td-hybrid-river-hydraulic-model-parameters-v7",
                        "model_version": MODEL_VERSION, "numerical_version": NUMERICAL_VERSION, "inventory_policy": inventory_policy(),
                        "integration": INTEGRATION, "accuracy_policy": accuracy_policy(),
                        "model_parameters": {"head_regularization_m": model.head_regularization_m, "donor_regularization_m3": model.donor_regularization_m3},
                        "friction_policy": {"width_m": args.crown_friction_transition_m, "transition_start": "crown", "transition_end": "crown+width_m",
                                            "actual_perimeter_unchanged": True, "storage_area_unchanged": True, "pressure_slot_width_unchanged": True,
                                            "roof_length_source": "sum_actual_polygon_edges_with_both_endpoints_at_crown",
                                            "constitutive_kind": "C1_effective_roof_contact_friction" if args.crown_friction_transition_m > 0 else "legacy_actual_perimeter",
                                            "contact_polynomial": "u*u*(3-2*u)_for_0<=u<=1"},
                        "forcing_configuration_pin": inputs["experiments"],
                        "graph_identity_sha256": graph["identity_sha256"], "geometry_identity_sha256": geometry["identity_sha256"],
                        "code_sha256": code,
                        "jacobian_policy": jacobian_policy(model, args.crown_friction_transition_m)}
    model_parameters["physical_model_identity_sha256"] = physical_model_identity(model_parameters)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    model_pin = atomic_save(output, "hydraulic-model.json", model_parameters)
    checkpoint = {"schema": SCHEMA, "status": "running_partial", "inputs": inputs,
                  "graph_identity_sha256": graph["identity_sha256"], "geometry_identity_sha256": geometry["identity_sha256"],
                  "section_adapter_schema": SECTION_SCHEMA, "numerical_version": NUMERICAL_VERSION, "code_sha256": code,
                  "model_version": MODEL_VERSION, "hydraulic_model_parameters": model_pin,
                  "friction_policy": model_parameters["friction_policy"], "jacobian_policy": model_parameters["jacobian_policy"],
                  "diagnostic_stop_s": args.diagnostic_stop_s, "diagnostic_artifacts": {},
                  "artifacts": {}, "summary": [], "completed_cases": [],
                  "reused_cases": {}, "generated_cases": [], "case_provenance": {},
                  "physical_model_identity_sha256": physical_model_identity(model_parameters),
                  "integration": INTEGRATION, "accuracy_policy": accuracy_policy(),
                  "input_parameter_identities": input_parameter_identities,
                  "independent_audit_passed": False, "natural_outlet_certified": False,
                  "full_network_verified": False, "three_dimensional_flow_solved": False,
                  "work": {"new_1d_rhs_evaluations": 0, "new_1d_link_evaluations": 0, "old_hll_face_work": 0, "old_hll_face_budget_remaining_unchanged": 2_949_448_968},
                  "resource": {"max_json_bytes": MAX_FILE_BYTES, "max_rss_bytes": 1024**3,
                               "wall_guard_seconds_per_case_unchanged": 600,
                               "whole_event_not_split_or_restarted": False,
                               "one_complete_forcing_event_budget_no_work_or_wall_reset": True,
                               "observation_times_reinitialize_BDF": True,
                               "negative_inventory_rollback_reinitializes_BDF_with_same_event_budget": True},
                  "checkpoint_semantics": "each complete case atomic; partial/failure never accepted; no automatic resume"}

    def save_checkpoint():
        checkpoint["resource"]["elapsed_wall_seconds"] = time.monotonic() - started
        atomic_save(output, "checkpoint.json", checkpoint)
        atomic_save(output, "index.json", checkpoint)

    save_checkpoint()
    active_case = None
    try:
        for base_parameters, refined_parameters in experiments:
            completed = []
            for label, parameters in (("base", base_parameters), ("refined", refined_parameters)):
                active_case = parameters.scenario + "-" + label
                print(json.dumps({"case": active_case, "status": "started", "physical_duration_s": parameters.duration_s}), flush=True)
                result = run_experiment(model, parameters, crown_transition_width_m=args.crown_friction_transition_m, diagnostic_stop_s=args.diagnostic_stop_s)
                result.update(graph_identity_sha256=graph["identity_sha256"], geometry_identity_sha256=geometry["identity_sha256"],
                              inputs=inputs, parameters=asdict(parameters), parameters_identity_sha256=identity(asdict(parameters)),
                              section_adapter_schema=SECTION_SCHEMA, code_sha256=code, meaningful_evidence=meaningful_evidence(result),
                              accuracy_policy=accuracy_policy(), accuracy_level=label,
                              input_parameters_identity_sha256=input_parameter_identities[parameters.scenario],
                              physical_model_identity_sha256=physical_model_identity(model_parameters),
                              hydraulic_model_parameters=model_pin, hydraulic_model_parameters_identity_sha256=model_pin["identity_sha256"])
                name = active_case + ".json"
                checkpoint["artifacts"][name] = atomic_save(output, name, result)
                checkpoint["completed_cases"].append(active_case)
                checkpoint["generated_cases"].append(active_case)
                checkpoint["case_provenance"][active_case] = {
                    "source_result_pin": checkpoint["artifacts"][name], "source_model_pin": model_pin,
                    "code_sha256": code, "numerical_version": NUMERICAL_VERSION,
                    "physical_model_identity_sha256": physical_model_identity(model_parameters),
                    "reused": False}
                checkpoint["work"]["new_1d_rhs_evaluations"] += result["work"]["rhs_evaluations"]
                checkpoint["work"]["new_1d_link_evaluations"] += result["work"]["link_evaluations"]
                save_checkpoint()
                print(json.dumps({"case": active_case, "status": "checkpoint_saved", "pin": checkpoint["artifacts"][name]}), flush=True)
                completed.append(result)
            comparison = compare_refinement(*completed, **tolerances)
            paired = paired_refinement(*completed)
            evidence = completed[1]["meaningful_evidence"]
            required = completed[1]["source_reached_engineered_outlet"] if base_parameters.scenario == "pulse" else completed[1]["reverse_reached_sink"]
            status = "diagnostic_accepted" if comparison["status"] == paired["status"] == "passed" and required and evidence["passed"] else "refused_diagnostic_evidence"
            checkpoint["summary"].append({"scenario": base_parameters.scenario, "status": status, "refinement": comparison,
                                          "paired_link_refinement": paired, "meaningful_evidence": evidence,
                                          "source_reached_engineered_outlet": completed[1]["source_reached_engineered_outlet"],
                                          "reverse_reached_sink": completed[1]["reverse_reached_sink"]})
            save_checkpoint()
        checkpoint["status"] = "diagnostic_accepted" if all(row["status"] == "diagnostic_accepted" for row in checkpoint["summary"]) else "refused_diagnostic_evidence"
        save_checkpoint()
    except HydraulicDiagnosticStop as stopped:
        checkpoint["status"] = "diagnostic_stopped"
        checkpoint["diagnostic_progress"] = stopped.progress
        checkpoint["work"]["new_1d_rhs_evaluations"] += stopped.progress["work"]["rhs_evaluations"]
        checkpoint["work"]["new_1d_link_evaluations"] += stopped.progress["work"]["link_evaluations"]
        checkpoint["resource"]["actual_peak_rss_bytes"] = stopped.progress["actual_peak_rss_bytes"]
        record = {"schema": "td-hybrid-river-hydraulics-diagnostic-v7", "status": "diagnostic_stopped",
                  "case": active_case, "progress": stopped.progress, "parameters": asdict(parameters),
                  "inputs": inputs, "code_sha256": code, "hydraulic_model_parameters": model_pin,
                  "hydraulic_model_parameters_identity_sha256": model_pin["identity_sha256"],
                  "model_parameters": model_parameters["model_parameters"], "friction_policy": model_parameters["friction_policy"],
                  "jacobian_policy": model_parameters["jacobian_policy"], "inventory_policy": inventory_policy(), "model_version": MODEL_VERSION,
                  "numerical_version": NUMERICAL_VERSION, "integration": INTEGRATION,
                  "accuracy_policy": accuracy_policy(), "accuracy_level": label,
                  "input_parameters_identity_sha256": input_parameter_identities[parameters.scenario], "physical_case_completed": False}
        name = active_case + "-diagnostic.json"
        checkpoint["diagnostic_artifacts"][name] = atomic_save(output, name, record)
        save_checkpoint()
        return checkpoint
    except Exception as error:
        checkpoint["status"] = "failed_partial"
        checkpoint["failure"] = {"case": active_case, "exception_type": type(error).__name__, "message": str(error), "failed_case_not_saved": active_case not in checkpoint["completed_cases"]}
        if isinstance(error, HydraulicExecutionFailure):
            checkpoint["failure"]["progress"] = error.progress
            checkpoint["work"]["new_1d_rhs_evaluations"] += error.progress["work"]["rhs_evaluations"]
            checkpoint["work"]["new_1d_link_evaluations"] += error.progress["work"]["link_evaluations"]
            checkpoint["resource"]["actual_peak_rss_bytes"] = error.progress["actual_peak_rss_bytes"]
        save_checkpoint()
        raise
    return checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "geometry", "geometry-audit", "experiments"):
        parser.add_argument("--" + name, required=True, type=Path)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diagnostic-stop-s", type=float, help="short accepted-time stop only; never a completed case")
    parser.add_argument("--crown-friction-transition-m", type=float, default=0.0, help="explicit new effective roof-friction law width; 0 replays legacy law for diagnosis")
    args = parser.parse_args()
    result = prepare(args)
    print(json.dumps({"status": result["status"], "completed_cases": result["completed_cases"], "summary": result["summary"]}))


if __name__ == "__main__":
    main()
