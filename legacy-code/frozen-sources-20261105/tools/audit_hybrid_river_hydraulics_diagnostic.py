"""Cold-read completed cases from a refused batch; never authorize water consumption."""

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.audit_hybrid_river_hydraulics import (
    accuracy_parameters, check_accuracy_policy, check_case_binding, check_result,
    check_same_physics, compare_saved, physical_identity)
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_memory, digest, file_sha256, read, read_audit, require)


def diagnose(index_pin):
    index = read(index_pin)
    require(index["schema"] in ("td-hybrid-river-hydraulics-preparation-v6",
                                "td-hybrid-river-hydraulics-preparation-v7")
            and index["status"] in ("failed_partial", "refused_diagnostic_evidence"),
            "only refused v6/v7 saved batches are supported")
    inputs = index["inputs"]
    graph, geometry, configuration = [read(inputs[key]) for key in ("graph", "geometry", "experiments")]
    geometry_audit = read_audit(inputs["geometry_audit"])
    model = read(index["hydraulic_model_parameters"])
    require(geometry_audit["status"] == "passed" and not geometry_audit["errors"]
            and geometry_audit["geometry_sha256"] == inputs["geometry"]["sha256"]
            and geometry_audit["actual_hydraulic_sections_verified"] is True
            and geometry_audit["actual_portal_connections_verified"] is True,
            "actual geometry audit not passed or not bound")
    require(model["code_sha256"] == index["code_sha256"]
            and model["forcing_configuration_pin"] == inputs["experiments"]
            and index["physical_model_identity_sha256"] == physical_identity(model)
            and model["geometry_identity_sha256"] == index["geometry_identity_sha256"] == geometry["identity_sha256"]
            and model["graph_identity_sha256"] == index["graph_identity_sha256"] == graph["identity_sha256"]
            and configuration["geometry_identity_sha256"] == geometry["identity_sha256"]
            and configuration["graph_identity_sha256"] == graph["identity_sha256"],
            "unbound diagnostic model/forcing/graph/geometry")
    for parent in (index, geometry, geometry_audit):
        for key in ("code_sha256", "audit_code_sha256", "readonly_dependency_code_sha256"):
            for name, sha in parent.get(key, {}).items():
                require(file_sha256(ROOT / name) == sha, "frozen dependency changed: " + name)
    bdf = index["schema"].endswith("v7")
    check_same_physics(include_bdf=bdf)
    if bdf:
        check_accuracy_policy(index, model)
    parameters_by_scenario = {row["scenario"]: row for row in configuration["scenarios"]}
    reports, records = {}, {}
    for name in index["completed_cases"]:
        record = read(index["artifacts"][name + ".json"])
        check_case_binding(record, index, model, name)
        scenario, level = name.rsplit("-", 1)
        original = parameters_by_scenario[scenario]
        require(record["inputs"] == inputs, "diagnostic case input binding mismatch")
        if bdf:
            require(index["input_parameter_identities"][scenario] == digest(original), "original forcing identity changed")
            parameters = accuracy_parameters(original, level)
        else:
            parameters = original if level == "base" else {
                **original, "max_step_s": original["max_step_s"] / 2,
                "relative_tolerance": original["relative_tolerance"] / 4,
                "absolute_tolerance": original["absolute_tolerance"] / 4}
        reports[name] = check_result(record, geometry, parameters)
        records[name] = record
    comparisons = {}
    for scenario in parameters_by_scenario:
        if scenario + "-base" not in records or scenario + "-refined" not in records:
            comparisons[scenario] = {"status": "not_comparable_missing_case"}
            continue
        base, refined = records[scenario + "-base"], records[scenario + "-refined"]
        difference = abs(np.asarray(base["hydraulic_head_m"]) - refined["hydraulic_head_m"])
        row, column = np.unravel_index(difference.argmax(), difference.shape)
        evidence = {"max_head_difference_m": float(difference[row, column]),
                    "worst_head_time_s": base["times_s"][row], "worst_head_cell_id": base["cell_ids"][column],
                    "final_max_head_difference_m": float(difference[-1].max()),
                    "max_volume_difference_m3": float(np.max(abs(np.asarray(base["water_volume_m3"]) - refined["water_volume_m3"]))),
                    "paired_link_max_absolute_difference_m3": {
                        key: float(np.max(abs(np.asarray(base[key]) - refined[key]))) for key in (
                            "paired_link_water_integral_m3", "paired_link_source_integral_m3",
                            "paired_link_tailwater_integral_m3", "paired_link_untraced_integral_m3")}}
        try:
            evidence.update(compare_saved(base, refined), status="passed_individual_pair_only")
        except ValueError as error:
            evidence.update(status="refused", error=str(error))
        comparisons[scenario] = evidence
    return {"schema": "td-hybrid-river-hydraulics-saved-diagnostic-v1",
            "status": "saved_diagnostic_read_not_acceptance", "index_pin": index_pin,
            "parent_batch_status": index["status"], "inputs": inputs, "completed_case_reports": reports,
            "comparisons": comparisons, "failure": index.get("failure"), "recorded_batch_work": index["work"],
            "independent_acceptance_passed": False, "water_animation_authorized": False,
            "time_refinement_verified": False, "natural_outlet_certified": False,
            "full_network_verified": False, "three_dimensional_flow_solved": False,
            "scope": "independent_actual_section_and_completed_case_ledger_checks_from_refused_batch_only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification diagnostic output required")
    started = time.monotonic()
    report = diagnose({"path": str(args.input.resolve()), "sha256": args.sha256})
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory()}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_river_hydraulics_diagnostic.py", "tools/audit_hybrid_river_hydraulics.py",
        "tools/td_shared_channel_fine_saved_audit.py", "tests/test_hybrid_river_hydraulics_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "saved diagnostic exceeds file budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"status": report["status"], "output": str(output), "sha256": file_sha256(output),
                      "completed_cases": list(report["completed_case_reports"]), "comparisons": report["comparisons"]}))


if __name__ == "__main__":
    main()
