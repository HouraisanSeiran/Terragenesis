"""Same pinned engineering events and frozen solver, with fast sections/checkpoints."""

from dataclasses import asdict, replace
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_geometry import MAX_FILE_BYTES, canonical_json, identity, read_pinned
from terrain_pipeline.hybrid_hydraulics import common_Experiment as Experiment, common_compare_refinement as compare_refinement, run_experiment
from terrain_pipeline.hybrid_hydraulics import HYBRID_RIVER_SECTIONS_MECHANISM_2_SCHEMA as SECTION_SCHEMA, accelerate_model
from tools.prepare_hybrid_river_hydraulics import file_sha, pin, validate_geometry

SCHEMA = "td-hybrid-river-hydraulics-preparation-v2"
FROZEN_CODE = {
    "terrain_pipeline/hybrid_river_graph.py": "063b2a3d037f366647aeb585161834a44a5eb18301dee919bb76b2b24052f8f6",
    "terrain_pipeline/hybrid_river_hydraulics.py": "896abd3ef8ec79bbbbdfe3638076361b83f2c2b61a1b0405378711366e372649",
    "tools/prepare_hybrid_river_hydraulics.py": "90a77f2813a33836787de400e45ce968b9f1a50369079bb6f7669b38a0e9f810",
    "tests/test_hybrid_river_graph.py": "a59b7ee534c3b74da2d9e513772bb0e703486f705d00f577ab2e64099aa28010",
    "tests/test_hybrid_river_hydraulics.py": "05de70386884fcb6e74a82c445ebf1a940c3048b17dd3eea362fa5103c2f96cf",
}
NEW_CODE = ("terrain_pipeline/hybrid_river_sections_v2.py", "tools/prepare_hybrid_river_hydraulics_v2.py", "tests/test_hybrid_river_sections_v2.py")


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
    fields = ("paired_link_water_integral_m3", "paired_link_source_integral_m3", "paired_link_tailwater_integral_m3")
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
    return {"status": "passed" if max(differences.values()) <= 1e-4 else "refused",
            "absolute_tolerance_m3": 1e-4, "max_absolute_differences_m3": differences}


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
    output = args.output.resolve()
    allowed = (ROOT / "verification" / "natural-river-network", ROOT / "verification" / "hybrid-river-network")
    if output.exists() or output.parent not in allowed:
        raise ValueError("new top-level verification package required; no overwrite/resume/repeated baseline")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    started = time.monotonic()
    checkpoint = {"schema": SCHEMA, "status": "running_partial", "inputs": inputs,
                  "graph_identity_sha256": graph["identity_sha256"], "geometry_identity_sha256": geometry["identity_sha256"],
                  "section_adapter_schema": SECTION_SCHEMA, "code_sha256": code,
                  "artifacts": {}, "summary": [], "completed_cases": [],
                  "independent_audit_passed": False, "natural_outlet_certified": False,
                  "full_network_verified": False, "three_dimensional_flow_solved": False,
                  "work": {"new_1d_rhs_evaluations": 0, "new_1d_link_evaluations": 0, "old_hll_face_work": 0, "old_hll_face_budget_remaining_unchanged": 2_949_448_968},
                  "resource": {"max_json_bytes": MAX_FILE_BYTES, "max_rss_bytes": 1024**3,
                               "wall_guard_seconds_per_case_unchanged": 600, "whole_event_not_split_or_restarted": True},
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
                result = run_experiment(model, parameters)
                result.update(graph_identity_sha256=graph["identity_sha256"], geometry_identity_sha256=geometry["identity_sha256"],
                              inputs=inputs, parameters=asdict(parameters), parameters_identity_sha256=identity(asdict(parameters)),
                              section_adapter_schema=SECTION_SCHEMA, code_sha256=code, meaningful_evidence=meaningful_evidence(result))
                name = active_case + ".json"
                checkpoint["artifacts"][name] = atomic_save(output, name, result)
                checkpoint["completed_cases"].append(active_case)
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
    except Exception as error:
        checkpoint["status"] = "failed_partial"
        checkpoint["failure"] = {"case": active_case, "exception_type": type(error).__name__, "message": str(error), "failed_case_not_saved": active_case not in checkpoint["completed_cases"]}
        save_checkpoint()
        raise
    return checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "geometry", "geometry-audit", "experiments"):
        parser.add_argument("--" + name, required=True, type=Path)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args)
    print(json.dumps({"status": result["status"], "completed_cases": result["completed_cases"], "summary": result["summary"]}))


if __name__ == "__main__":
    main()
