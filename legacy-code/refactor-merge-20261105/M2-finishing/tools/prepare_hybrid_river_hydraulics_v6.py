"""Pinned v6 analytic Jacobian; reuse complete v5 pulse-base unchanged, generate missing three cases."""

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

from terrain_pipeline.hybrid_geometry import MAX_FILE_BYTES, canonical_json, identity, read_pinned
from terrain_pipeline.hybrid_hydraulics import common_Experiment as Experiment, common_compare_refinement as compare_refinement
from terrain_pipeline.hybrid_hydraulics import MODEL_VERSION, NUMERICAL_VERSION, inventory_policy, jacobian_policy, analytic_radau_run_experiment as run_experiment
from builtins import ValueError as HydraulicDiagnosticStop, ValueError as HydraulicExecutionFailure
from terrain_pipeline.hybrid_hydraulics import DIRECT_INVENTORY_NUMERICAL_VERSION as SOURCE_NUMERICAL_VERSION, direct_inventory_jacobian_policy as source_jacobian_policy
from terrain_pipeline.hybrid_hydraulics import HYBRID_RIVER_SECTIONS_MECHANISM_2_SCHEMA as SECTION_SCHEMA, accelerate_model
from tools.prepare_hybrid_river_hydraulics import file_sha, pin, validate_geometry

SCHEMA = "td-hybrid-river-hydraulics-preparation-v6"
FROZEN_CODE = {
    "terrain_pipeline/hybrid_river_graph.py": "063b2a3d037f366647aeb585161834a44a5eb18301dee919bb76b2b24052f8f6",
    "terrain_pipeline/hybrid_river_hydraulics.py": "896abd3ef8ec79bbbbdfe3638076361b83f2c2b61a1b0405378711366e372649",
    "tools/prepare_hybrid_river_hydraulics.py": "90a77f2813a33836787de400e45ce968b9f1a50369079bb6f7669b38a0e9f810",
    "tests/test_hybrid_river_graph.py": "a59b7ee534c3b74da2d9e513772bb0e703486f705d00f577ab2e64099aa28010",
    "tests/test_hybrid_river_hydraulics.py": "05de70386884fcb6e74a82c445ebf1a940c3048b17dd3eea362fa5103c2f96cf",
    "terrain_pipeline/hybrid_river_sections_v2.py": "a2dc77c77eee42620c8dd43822b48a40a30ba6dec8a957b8c25caed4ba4fe4ac",
    "tools/prepare_hybrid_river_hydraulics_v2.py": "bae884207976be09c341e3dfdf148cc4bd53ea63681b7492e5bbd9ea031b2829",
    "tests/test_hybrid_river_sections_v2.py": "b148f8c26c16721f4c187a714f8184452b6ba640ace21eca589f00515573ab8b",
    "terrain_pipeline/hybrid_river_hydraulics_v3.py": "8ef6cf10d292accc0df83fd3a6f5dd1c1fce7a6d2afba4463813fd5a917fa296",
    "tools/prepare_hybrid_river_hydraulics_v3.py": "c7f92d6dbfd40538f4b820731b1d9998810f8c307988caa2bc279c41bb73a048",
    "tests/test_hybrid_river_hydraulics_v3.py": "d1e6dd64db328de47c21d586363781ccfa2a7b50f850131e02280e0a81f81b2a",
    "terrain_pipeline/hybrid_river_hydraulics_v4.py": "18b34e7e505b786e3a8f0469ff9ce44fd337090eb9e71c7064167078e9c7cdcd",
    "tools/prepare_hybrid_river_hydraulics_v4.py": "c5052f94a3562f2f31648ffed9febc15a84d674f5981f7b368a23de3697d1a22",
    "tests/test_hybrid_river_hydraulics_v4.py": "afd1c59e756dfd7f9fa91b61adabc8fc5088ed346be7462b33e6aa7c5b74fb64",
    "terrain_pipeline/hybrid_river_hydraulics_v5.py": "b170ddc31f62cf0c2b369be1ac5cec2633cc33ffa636aefdc6295536e1153443",
    "tools/prepare_hybrid_river_hydraulics_v5.py": "e39f5f6cbde34580bd0c948b3869f23131292ecea27267cf1c3b68521fd70260",
    "tests/test_hybrid_river_hydraulics_v5.py": "2bb9c3f1962e461eb4d8fb74cef2b49136d16dce334e1d5b44d2b8679a2d99eb",
}
NEW_CODE = ("terrain_pipeline/hybrid_river_hydraulics_v6.py", "tools/prepare_hybrid_river_hydraulics_v6.py", "tests/test_hybrid_river_hydraulics_v6.py")


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


def read_sealed(file_pin):
    record = read_pinned(pin(file_pin["path"], file_pin["sha256"]))
    unsigned = dict(record)
    expected = unsigned.pop("identity_sha256", None)
    if expected != identity(unsigned) or file_pin.get("identity_sha256", expected) != expected:
        raise ValueError("reused sealed file identity mismatch")
    return record


def physical_model_identity(record):
    return identity({key: record[key] for key in PHYSICAL_MODEL_FIELDS})


def bind_reused_pulse_base(source_index_pin, expected_inputs, expected_parameters, expected_model, hydraulic_model):
    source_index = read_sealed(source_index_pin)
    if source_index["schema"] != "td-hybrid-river-hydraulics-preparation-v5" or source_index["status"] not in (
            "failed_partial", "diagnostic_accepted", "refused_diagnostic_evidence"):
        raise ValueError("reuse requires a sealed v5 index with a completed saved pulse-base")
    if "pulse-base" not in source_index["completed_cases"]:
        raise ValueError("pulse-base was not completed in source index")
    if source_index["inputs"] != expected_inputs or source_index["code_sha256"] != FROZEN_CODE:
        raise ValueError("reuse source index inputs/frozen17 code mismatch")
    source_result_pin = source_index["artifacts"]["pulse-base.json"]
    source = read_sealed(source_result_pin)
    source_model_pin = source_index["hydraulic_model_parameters"]
    source_model = read_sealed(source_model_pin)
    if source_model["schema"] != "td-hybrid-river-hydraulic-model-parameters-v5":
        raise ValueError("reuse source model schema mismatch")
    for key in ("model_version", "friction_policy", "jacobian_policy", "numerical_version"):
        if source_index[key] != source_model[key]:
            raise ValueError("reuse source index/model metadata mismatch: " + key)
    if (source["schema"] != "td-hybrid-river-hydraulics-v5" or source["status"] != "diagnostic_completed"
            or source["code_sha256"] != source_index["code_sha256"] or source_model["code_sha256"] != source["code_sha256"]
            or source["inputs"] != expected_inputs
            or source["hydraulic_model_parameters"] != source_model_pin
            or source["hydraulic_model_parameters_identity_sha256"] != source_model["identity_sha256"]):
        raise ValueError("reuse result/model/index exact provenance mismatch")
    if (identity(source["parameters"]) != identity(asdict(expected_parameters))
            or source["parameters_identity_sha256"] != identity(source["parameters"])
            or physical_model_identity(source_model) != physical_model_identity(expected_model)):
        raise ValueError("reuse physical model or pulse forcing mismatch")
    for key in ("model_version", "model_parameters", "friction_policy", "inventory_policy",
                "graph_identity_sha256", "geometry_identity_sha256"):
        if source[key] != source_model[key] or source[key] != expected_model[key]:
            raise ValueError("reuse result physical metadata mismatch: " + key)
    static_jacobian = {key: value for key, value in source["jacobian_policy"].items()
                       if key != "observed_max_head_step_m"}
    if (static_jacobian != source_model["jacobian_policy"]
            or static_jacobian != source_jacobian_policy(hydraulic_model, expected_model["friction_policy"]["width_m"])
            or source["numerical_version"] != source_model["numerical_version"]
            or source["numerical_version"] != SOURCE_NUMERICAL_VERSION):
        raise ValueError("reuse source numerical model mismatch")
    if (source["times_s"] != list(expected_parameters.saved_times_s)
            or source["execution_progress"]["last_accepted_physical_time_s"] != expected_parameters.duration_s
            or not source["execution_progress"]["physical_event_complete"]
            or source["execution_progress"]["diagnostic_stop_s"] is not None
            or source["execution_progress"]["triggered_guard"] is not None):
        raise ValueError("reuse pulse-base physical event incomplete")
    actual_initial = np.array([cell.section.area_perimeter(head)[0] * cell.length_m
                               for cell, head in zip(hydraulic_model.cells, expected_parameters.initial_heads_m)])
    if (source["cell_ids"] != [cell.cell_id for cell in hydraulic_model.cells]
            or source["link_ids"] != [link.link_id for link in hydraulic_model.links]
            or not np.array_equal(source["initial_untraced_water_m3"], actual_initial)):
        raise ValueError("reuse actual geometry initial water/topology mismatch")
    origins = np.array([source["untraced_water_volume_m3"], source["source_tracer_mass_m3"],
                        source["tailwater_tracer_mass_m3"]], dtype=float)
    volumes = np.asarray(source["water_volume_m3"], dtype=float)
    if (origins.shape != (3, len(source["times_s"]), len(source["cell_ids"]))
            or volumes.shape != origins.shape[1:] or not np.isfinite(origins).all()
            or np.any(origins < 0) or np.any(volumes <= 0) or not np.array_equal(volumes, origins.sum(axis=0))):
        raise ValueError("reuse actual three-origin positivity/composition invalid")
    if (not np.array_equal(origins[0, 0], source["initial_untraced_water_m3"])
            or np.any(origins[1:, 0] != 0)):
        raise ValueError("reuse initial origins changed")
    for key in ("max_water_residual_m3", "max_source_residual_m3", "max_tailwater_residual_m3", "max_untraced_residual_m3"):
        if not math.isfinite(source[key]) or source[key] > source["conservation_gate_m3"]:
            raise ValueError("reuse conservation gate failed")
    work = source["work"]
    if (work["rhs_evaluations"] > expected_parameters.max_rhs_evaluations
            or work["link_evaluations"] > expected_parameters.max_link_evaluations
            or work["wall_seconds"] > expected_parameters.max_wall_seconds
            or work["actual_peak_rss_bytes"] > 1024**3):
        raise ValueError("reuse completed case exceeded unchanged guard")
    provenance = {"source_index_pin": {**source_index_pin, "identity_sha256": source_index["identity_sha256"]}, "source_result_pin": source_result_pin,
                  "source_model_pin": source_model_pin, "code_sha256": source["code_sha256"],
                  "physical_model_identity_sha256": physical_model_identity(source_model),
                  "numerical_version": source["numerical_version"], "result_unmodified": True,
                  "independent_audit_passed": False}
    return source_result_pin, source, provenance



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
    for parameters in scenarios:
        experiment = Experiment(**{**parameters, "initial_heads_m": tuple(parameters["initial_heads_m"]), "saved_times_s": tuple(parameters["saved_times_s"])})
        experiment.validate(model)
        refined = replace(experiment, max_step_s=experiment.max_step_s / 2,
                          relative_tolerance=experiment.relative_tolerance / 4, absolute_tolerance=experiment.absolute_tolerance / 4)
        refined.validate(model)
        experiments.append((experiment, refined))
    if args.diagnostic_stop_s is None and args.crown_friction_transition_m == 0:
        raise ValueError("use a short diagnostic stop for legacy-law replay, or explicitly declare the new roof-friction transition")
    from terrain_pipeline.hybrid_hydraulics import validate_transition
    validate_transition(args.crown_friction_transition_m)
    if args.diagnostic_stop_s is not None and any(not 0 < args.diagnostic_stop_s <= experiment.duration_s for pair in experiments for experiment in pair):
        raise ValueError("short diagnostic must be inside the unchanged event")
    output = args.output.resolve()
    allowed = (ROOT / "verification" / "natural-river-network", ROOT / "verification" / "hybrid-river-network")
    if output.exists() or output.parent not in allowed:
        raise ValueError("new top-level verification package required; no overwrite/resume/repeated baseline")
    started = time.monotonic()
    model_parameters = {"schema": "td-hybrid-river-hydraulic-model-parameters-v6",
                        "model_version": MODEL_VERSION, "numerical_version": NUMERICAL_VERSION, "inventory_policy": inventory_policy(),
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
    source_index_pin = asdict(pin(args.reuse_index, args.reuse_index_sha256))
    source_result_pin, source_result, source_provenance = bind_reused_pulse_base(
        source_index_pin, inputs, next(base for base, refined in experiments if base.scenario == "pulse"), model_parameters, model)
    if source_result["cell_ids"] != [cell.cell_id for cell in model.cells] or source_result["link_ids"] != [link.link_id for link in model.links]:
        raise ValueError("reused actual hydraulic topology differs")
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
                  "artifacts": {"pulse-base.json": source_result_pin}, "summary": [], "completed_cases": ["pulse-base"],
                  "reused_cases": {"pulse-base": source_provenance}, "generated_cases": [],
                  "case_provenance": {"pulse-base": source_provenance},
                  "physical_model_identity_sha256": physical_model_identity(model_parameters),
                  "reuse_contract": {"physics": "exact_physical_model_fields_and_forcing",
                                     "allowed_numerical_differences": ["schema", "numerical_version", "jacobian_policy", "code_sha256"],
                                     "reused_result_rewritten": False, "reused_work_not_counted_as_new": True},
                  "reused_case_work": source_result["work"],
                  "independent_audit_passed": False, "natural_outlet_certified": False,
                  "full_network_verified": False, "three_dimensional_flow_solved": False,
                  "work": {"new_1d_rhs_evaluations": 0, "new_1d_link_evaluations": 0, "old_hll_face_work": 0, "old_hll_face_budget_remaining_unchanged": 2_949_448_968},
                  "resource": {"max_json_bytes": MAX_FILE_BYTES, "max_rss_bytes": 1024**3,
                               "wall_guard_seconds_per_case_unchanged": 600,
                               "whole_event_not_split_or_restarted": False,
                               "one_complete_forcing_event_budget_no_work_or_wall_reset": True,
                               "observation_times_reinitialize_Radau": True,
                               "negative_inventory_rollback_reinitializes_Radau_with_same_event_budget": True},
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
                if active_case == "pulse-base":
                    completed.append(source_result)
                    print(json.dumps({"case": active_case, "status": "reused_complete", "pin": source_result_pin}), flush=True)
                    continue
                print(json.dumps({"case": active_case, "status": "started", "physical_duration_s": parameters.duration_s}), flush=True)
                result = run_experiment(model, parameters, crown_transition_width_m=args.crown_friction_transition_m, diagnostic_stop_s=args.diagnostic_stop_s)
                result.update(graph_identity_sha256=graph["identity_sha256"], geometry_identity_sha256=geometry["identity_sha256"],
                              inputs=inputs, parameters=asdict(parameters), parameters_identity_sha256=identity(asdict(parameters)),
                              section_adapter_schema=SECTION_SCHEMA, code_sha256=code, meaningful_evidence=meaningful_evidence(result),
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
        record = {"schema": "td-hybrid-river-hydraulics-diagnostic-v6", "status": "diagnostic_stopped",
                  "case": active_case, "progress": stopped.progress, "parameters": asdict(parameters),
                  "inputs": inputs, "code_sha256": code, "hydraulic_model_parameters": model_pin,
                  "hydraulic_model_parameters_identity_sha256": model_pin["identity_sha256"],
                  "model_parameters": model_parameters["model_parameters"], "friction_policy": model_parameters["friction_policy"],
                  "jacobian_policy": model_parameters["jacobian_policy"], "inventory_policy": inventory_policy(), "model_version": MODEL_VERSION,
                  "numerical_version": NUMERICAL_VERSION, "physical_case_completed": False}
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
    parser.add_argument("--reuse-index", required=True, type=Path)
    parser.add_argument("--reuse-index-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diagnostic-stop-s", type=float, help="short accepted-time stop only; never a completed case")
    parser.add_argument("--crown-friction-transition-m", type=float, default=0.0, help="explicit new effective roof-friction law width; 0 replays legacy law for diagnosis")
    args = parser.parse_args()
    result = prepare(args)
    print(json.dumps({"status": result["status"], "completed_cases": result["completed_cases"], "summary": result["summary"]}))


if __name__ == "__main__":
    main()
