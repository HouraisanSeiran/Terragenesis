"""Four new local-frame Radau precision cases, checkpointed under the original event budgets."""

from dataclasses import asdict
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT

from terrain_pipeline.hybrid_geometry import MAX_FILE_BYTES, identity, read_pinned
from terrain_pipeline.hybrid_hydraulics import common_Experiment as Experiment, common_compare_refinement as compare_refinement
from terrain_pipeline.hybrid_hydraulics import LOCAL_FRAME_INTEGRATION as INTEGRATION, MODEL_VERSION, LOCAL_FRAME_NUMERICAL_VERSION as NUMERICAL_VERSION, inventory_policy, jacobian_policy, local_model, numerical_frame, local_frame_run_experiment as run_experiment
from builtins import ValueError as HydraulicDiagnosticStop, ValueError as HydraulicExecutionFailure
from terrain_pipeline.hybrid_hydraulics import HYBRID_RIVER_SECTIONS_MECHANISM_2_SCHEMA as SECTION_SCHEMA
from tools.hybrid_hydraulics_preparation_common import (
    file_sha, pin, validate_geometry, atomic_save, meaningful_evidence, paired_refinement,
    physical_model_identity, precision_experiments, accuracy_policy as previous_accuracy_policy)
from tools.hybrid_hydraulics_legacy import HydraulicsLegacyReplay, SOURCE_ROOT

SCHEMA = "td-hybrid-river-hydraulics-preparation-v8"
NEW_CODE = (
    "terrain_pipeline/hybrid_geometry.py", "terrain_pipeline/hybrid_hydraulics.py",
    "tools/hybrid_hydraulics_preparation_common.py",
    "tools/hybrid_hydraulics_legacy.py", "tools/prepare_hybrid_river_hydraulics_v8.py",
    "tests/test_hybrid_river_hydraulics_v8.py")


def source_identity():
    """Current executed sources and historical reference pins are different identities."""
    replay = HydraulicsLegacyReplay()
    historical = {name: record["sha256"] for name, record in replay.manifest["files"].items()}
    current = {name: file_sha(DATA_ROOT / name) for name in NEW_CODE}
    return current, historical


def accuracy_policy():
    return {**previous_accuracy_policy(), "schema": "td-hybrid-river-accuracy-policy-v8", "integration": INTEGRATION}


def prepare(args):
    code, historical_code = source_identity()
    pins = {name: pin(getattr(args, name), getattr(args, name + "_sha256"))
            for name in ("graph", "geometry", "geometry_audit", "experiments")}
    inputs = {name: asdict(value) for name, value in pins.items()}
    graph = read_pinned(pins["graph"])
    model, geometry = validate_geometry(graph, pins["geometry"], pins["geometry_audit"])
    configuration = read_pinned(pins["experiments"])
    unsigned = dict(configuration)
    expected = unsigned.pop("identity_sha256")
    if configuration["schema"] != "td-hybrid-river-engineering-experiments-v1" or identity(unsigned) != expected:
        raise ValueError("engineering configuration identity/schema mismatch")
    if (configuration["graph_identity_sha256"] != graph["identity_sha256"]
            or configuration["geometry_identity_sha256"] != geometry["identity_sha256"]
            or configuration["inputs"] != {name: inputs[name] for name in ("graph", "geometry", "geometry_audit")}):
        raise ValueError("engineering configuration geometry/graph binding mismatch")
    scenarios = configuration["scenarios"]
    if len(scenarios) != 2 or {item["scenario"] for item in scenarios} != {"pulse", "reverse_tailwater"}:
        raise ValueError("exactly the original two events required")
    tolerances = configuration.get("refinement_tolerances", {})
    limits = {"volume_absolute_tolerance_m3": 1e-4, "head_absolute_tolerance_m": 1e-3,
              "volume_relative_tolerance": 0.01}
    if any(tolerances.get(key, maximum) > maximum for key, maximum in limits.items()):
        raise ValueError("refinement gates cannot be relaxed")
    experiments, parameter_ids = [], {}
    for item in scenarios:
        original = Experiment(**{**item, "initial_heads_m": tuple(item["initial_heads_m"]),
                                 "saved_times_s": tuple(item["saved_times_s"])})
        original.validate(model)
        pair = precision_experiments(original)
        for experiment in pair:
            experiment.validate(model)
        experiments.append(pair)
        parameter_ids[original.scenario] = identity(asdict(original))
    from terrain_pipeline.hybrid_hydraulics import validate_transition
    validate_transition(args.crown_friction_transition_m)
    if args.crown_friction_transition_m <= 0:
        raise ValueError("v8 requires the explicitly pinned roof-friction model")
    frame = numerical_frame(model)
    model_record = {"schema": "td-hybrid-river-hydraulic-model-parameters-v8",
                    "model_version": MODEL_VERSION, "numerical_version": NUMERICAL_VERSION,
                    "integration": INTEGRATION, "inventory_policy": inventory_policy(),
                    "accuracy_policy": accuracy_policy(), "numerical_frame": frame,
                    "model_parameters": {"head_regularization_m": model.head_regularization_m,
                                         "donor_regularization_m3": model.donor_regularization_m3},
                    "friction_policy": {"width_m": args.crown_friction_transition_m, "transition_start": "crown",
                                        "transition_end": "crown+width_m", "actual_perimeter_unchanged": True,
                                        "storage_area_unchanged": True, "pressure_slot_width_unchanged": True,
                                        "roof_length_source": "sum_actual_polygon_edges_with_both_endpoints_at_crown",
                                        "constitutive_kind": "C1_effective_roof_contact_friction",
                                        "contact_polynomial": "u*u*(3-2*u)_for_0<=u<=1"},
                    "jacobian_policy": jacobian_policy(local_model(model, frame), args.crown_friction_transition_m),
                    "forcing_configuration_pin": inputs["experiments"], "code_sha256": code,
                    "graph_identity_sha256": graph["identity_sha256"], "geometry_identity_sha256": geometry["identity_sha256"]}
    model_record["source_layout"] = "explicit_common_radau_v8_20261023"
    model_record["frozen_reference_code_sha256"] = historical_code
    model_record["physical_model_identity_sha256"] = physical_model_identity(model_record)
    output = args.output.resolve()
    if output.exists() or output.parent not in (ROOT / "verification/natural-river-network", ROOT / "verification/hybrid-river-network"):
        raise ValueError("new verification directory required; no resume/reuse")
    output.mkdir(parents=True)
    model_pin = atomic_save(output, "hydraulic-model.json", model_record)
    started = time.monotonic()
    checkpoint = {"schema": SCHEMA, "status": "running_partial", "inputs": inputs,
                  "code_sha256": code, "model_version": MODEL_VERSION, "numerical_version": NUMERICAL_VERSION,
                  "integration": INTEGRATION, "numerical_frame": frame, "accuracy_policy": accuracy_policy(),
                  "section_adapter_schema": SECTION_SCHEMA, "hydraulic_model_parameters": model_pin,
                  "physical_model_identity_sha256": physical_model_identity(model_record),
                  "graph_identity_sha256": graph["identity_sha256"], "geometry_identity_sha256": geometry["identity_sha256"],
                  "friction_policy": model_record["friction_policy"], "jacobian_policy": model_record["jacobian_policy"],
                  "input_parameter_identities": parameter_ids, "completed_cases": [], "generated_cases": [],
                  "artifacts": {}, "summary": [], "reused_cases": {}, "case_provenance": {},
                  "diagnostic_stop_s": args.diagnostic_stop_s, "diagnostic_artifacts": {},
                  "independent_audit_passed": False, "natural_outlet_certified": False,
                  "full_network_verified": False, "three_dimensional_flow_solved": False,
                  "work": {"new_1d_rhs_evaluations": 0, "new_1d_link_evaluations": 0,
                           "old_hll_face_work": 0, "old_hll_face_budget_remaining_unchanged": 2_949_448_968},
                  "resource": {"max_json_bytes": MAX_FILE_BYTES, "max_rss_bytes": 1024**3,
                               "wall_guard_seconds_per_case_unchanged": 600, "whole_event_not_split_or_restarted": False,
                               "one_complete_forcing_event_budget_no_work_or_wall_reset": True,
                               "observation_times_reinitialize_Radau": True,
                               "negative_inventory_rollback_reinitializes_Radau_with_same_event_budget": True},
                  "checkpoint_semantics": "each complete case atomic; failure never accepted; no automatic resume"}

    def save_checkpoint():
        checkpoint["resource"]["elapsed_wall_seconds"] = time.monotonic() - started
        atomic_save(output, "checkpoint.json", checkpoint)
        atomic_save(output, "index.json", checkpoint)

    checkpoint["source_layout"] = model_record["source_layout"]
    checkpoint["frozen_reference_code_sha256"] = historical_code
    active_case = None
    save_checkpoint()
    try:
        for pair in experiments:
            completed = []
            for label, parameters in zip(("base", "refined"), pair):
                active_case = parameters.scenario + "-" + label
                print(json.dumps({"case": active_case, "status": "started"}), flush=True)
                result = run_experiment(model, parameters, args.crown_friction_transition_m, args.diagnostic_stop_s)
                result.update(inputs=inputs, parameters=asdict(parameters), parameters_identity_sha256=identity(asdict(parameters)),
                              local_solver_parameters_identity_sha256=identity(result["local_solver_parameters"]),
                              graph_identity_sha256=graph["identity_sha256"], geometry_identity_sha256=geometry["identity_sha256"],
                              code_sha256=code, section_adapter_schema=SECTION_SCHEMA, meaningful_evidence=meaningful_evidence(result),
                              accuracy_policy=accuracy_policy(), accuracy_level=label,
                              input_parameters_identity_sha256=parameter_ids[parameters.scenario],
                              physical_model_identity_sha256=physical_model_identity(model_record),
                              hydraulic_model_parameters=model_pin, hydraulic_model_parameters_identity_sha256=model_pin["identity_sha256"])
                name = active_case + ".json"
                result_pin = atomic_save(output, name, result)
                checkpoint["artifacts"][name] = result_pin
                checkpoint["completed_cases"].append(active_case)
                checkpoint["generated_cases"].append(active_case)
                checkpoint["case_provenance"][active_case] = {"source_result_pin": result_pin, "source_model_pin": model_pin,
                                                           "code_sha256": code, "numerical_version": NUMERICAL_VERSION,
                                                           "physical_model_identity_sha256": physical_model_identity(model_record), "reused": False}
                for key, source in (("new_1d_rhs_evaluations", "rhs_evaluations"), ("new_1d_link_evaluations", "link_evaluations")):
                    checkpoint["work"][key] += result["work"][source]
                save_checkpoint()
                print(json.dumps({"case": active_case, "status": "checkpoint_saved", "pin": result_pin}), flush=True)
                completed.append(result)
            comparison = compare_refinement(*completed, **tolerances)
            comparison["scope"] = "Radau_solver_parameter_refinement_of_full_saved_inventory_and_flux_history_not_wave_speed"
            paired = paired_refinement(*completed)
            evidence = completed[1]["meaningful_evidence"]
            status = "diagnostic_accepted" if comparison["status"] == paired["status"] == "passed" and evidence["passed"] else "refused_diagnostic_evidence"
            checkpoint["summary"].append({"scenario": pair[0].scenario, "status": status, "refinement": comparison,
                                          "paired_link_refinement": paired, "meaningful_evidence": evidence})
            save_checkpoint()
        checkpoint["status"] = "diagnostic_accepted" if all(item["status"] == "diagnostic_accepted" for item in checkpoint["summary"]) else "refused_diagnostic_evidence"
        save_checkpoint()
    except Exception as error:
        stopped = isinstance(error, HydraulicDiagnosticStop)
        checkpoint["status"] = "diagnostic_stopped" if stopped else "failed_partial"
        checkpoint["failure"] = {"case": active_case, "exception_type": type(error).__name__, "message": str(error),
                                 "failed_case_not_saved": True}
        if isinstance(error, HydraulicExecutionFailure):
            checkpoint["failure"]["progress"] = error.progress
            for key, source in (("new_1d_rhs_evaluations", "rhs_evaluations"), ("new_1d_link_evaluations", "link_evaluations")):
                checkpoint["work"][key] += error.progress["work"][source]
            checkpoint["resource"]["actual_peak_rss_bytes"] = error.progress["actual_peak_rss_bytes"]
        save_checkpoint()
        if not stopped:
            raise
    return checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "geometry", "geometry-audit", "experiments"):
        parser.add_argument("--" + name, required=True, type=Path)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diagnostic-stop-s", type=float)
    parser.add_argument("--crown-friction-transition-m", type=float, default=0.02)
    result = prepare(parser.parse_args())
    print(json.dumps({"status": result["status"], "completed_cases": result["completed_cases"], "summary": result["summary"]}))


if __name__ == "__main__":
    main()
