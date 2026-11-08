"""Pin completed stage reports for the existing read-only morphology API."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import publish_bytes
from terrain_pipeline.channel_geometry import load_cutoff_material_candidate


def supplemental_summary(report):
    keys = ("schema", "status", "scope", "summary", "acceptance", "completion", "failure", "failure_reason",
            "uncovered", "natural_credible", "natural_certification", "publishable", "source", "source_sha256",
            "reference_sha256", "generation_report_sha256", "plan_sha256", "evaluation_plan_sha256",
            "eligible_counts", "source_product", "relief_grid_real_holdout_summary", "real_holdout_summary",
            "conditional_real_holdout_summary", "cohort_evaluation", "elapsed_s", "gpu_peak_allocated_bytes",
            "forcing_provenance", "rainfall_forcing_identity_sha256", "artifact", "input_inventories", "comparison_scope",
            "evaluation_role", "individual_window_counts", "two_window_cohort_counts", "noise_climate_physical_counts",
            "cohort_results", "products", "generation_plan_sha256", "real_block_validation", "real_pair_calibration_validation",
            "sampling_limit", "real_reference_limit", "climate_limit", "default_world_publication",
            "quantiles", "temperature_conditioned_joint_envelopes", "statistical_weighting", "source_report_sha256",
            "physical_reference", "valid_global_pixels", "target_conditions",
            "elapsed_seconds", "peak_rss_bytes", "horizon_seconds", "level", "dt_seconds", "segments",
            "implementation_sha256", "performance_passed", "old_180s_passed", "new_offline_600s_passed",
            "retained_segments_solve_save_seconds", "prefix_cold_audit_seconds", "retained_segments_600s_passed",
            "suffix_worker_seconds", "prefix_original_worker_seconds")
    summary = {key: report[key] for key in keys if key in report}
    if report.get("schema") is None and "elapsed_seconds" in report and "implementation_sha256" in report:
        summary["scope"] = "saved_worker_resource_measurement_including_solve_save_and_completion"
        summary["prefix_reuse_present"] = "prefix_original_worker_seconds" in report or "suffix_worker_seconds" in report
        summary["resource_policy_context"] = {"old_seconds": 180, "offline_seconds": 600, "rss_bytes": 1073741824}
    if report.get("schema") == "river-reference-geographic-inventory-v1":
        blocks = [block for dataset in report.get("datasets", []) for block in dataset.get("blocks", [])]
        summary["dataset_count"] = len(report.get("datasets", []))
        summary["block_count"] = len(blocks)
        summary["eligible_block_count"] = sum(block.get("eligible_for_evaluation") is True for block in blocks)
        summary["eligible_role_counts"] = {role: sum(block.get("eligible_for_evaluation") is True and block.get("role") == role for block in blocks)
                                           for role in ("fit", "calibration", "real_holdout")}
    if report.get("schema") == "TD-noise-independent-evaluation-summary-v1":
        rejected = any(report.get(key, {}).get("fail", 0) for key in ("individual_window_counts", "two_window_cohort_counts", "noise_climate_physical_counts"))
        summary["status"] = "completed_independent_evaluation_with_retained_rejections" if rejected else "completed_independent_evaluation"
        summary["status_source"] = "derived_from_saved_outcome_counts"
        summary["scope"] = "finite_independent_noise_holdout;individual_window_rejections_retained"
    if report.get("schema") in ("terragenesis-active-spatial-series-verification-v1", "terragenesis-active-spatial-series-verification-v2"):
        audit = report.get("audit", {})
        summary.update({"status": audit.get("status"), "status_source": "audit.status",
                        "scope": audit.get("scope"), "policy": report.get("policy")})
        for key in ("accepted_uniform_levels", "minimum_accepted_level", "spatial_error", "temporal_error", "resources",
                    "physical_status", "engineering_status", "normal_resource_measurement", "resource_extension", "coverage_policy"):
            if key in audit:
                summary[key] = audit[key]
        for key in ("coverage_policy_sha256", "engineering_budget_supplement_path", "engineering_budget_supplement_sha256",
                    "resource_extension_path", "save_policy_disclosure"):
            if key in report:
                summary[key] = report[key]
    if "cases" in report:
        cases = report["cases"]
        case_keys = ("id", "name", "seed", "source_sha256", "status", "reason", "failure_reason", "condition",
                     "full_condition", "naturalness_status", "evaluation", "full_condition_evaluation",
                     "cohort_evaluation", "level", "dt_seconds", "path", "sha256", "source_origin", "window_zx",
                     "distribution_evaluation_relief_grid_only", "conditional_geometry_evaluation", "relief_class", "window_origin_zx",
                     "noise_climate_physical_evaluation", "upstream_auxiliary_BIO_real_context", "climate_semantics")
        if isinstance(cases, list):
            summary["case_count"] = len(cases)
            summary["case_outcomes"] = [{key: case[key] for key in case_keys if key in case}
                                        for case in cases if isinstance(case, dict)]
        elif isinstance(cases, dict):
            summary["case_count"] = len(cases)
            summary["case_outcomes"] = {name: {key: case[key] for key in case_keys if key in case}
                                         for name, case in cases.items() if isinstance(case, dict)}
    if report.get("schema") == "TD-noise-climate-generation-v1":
        samples = report.get("samples", [])
        sample_keys = ("seed", "native_origin", "raw_sha256", "generation_identity", "condition_sha256",
                       "height_range_m", "output_BIO_medians", "elapsed_s")
        summary["sample_count"] = len(samples)
        summary["sample_sources"] = [{key: sample[key] for key in sample_keys if key in sample} for sample in samples]
        summary["actual_source_checks"] = report.get("actual_source_checks", [])
    if report.get("schema") == "real-channel-distribution-reference-v1":
        summary["spatial_dependence"] = report.get("spatial_dependence")
        summary["condition_coverage"] = report.get("condition_coverage")
        summary["calibration_conditions"] = {
            name: {key: item[key] for key in ("joint_cdf_cutoff", "cutoff_status", "alpha", "conditions", "calibration_count") if key in item}
            for name, item in report.get("calibrations", {}).items()}
        summary["negative_control_outcomes"] = {
            name: {key: item[key] for key in ("status", "reason", "joint_score", "cutoff") if key in item}
            for name, item in report.get("negative_controls", {}).items()}
        cohort = report.get("cohort_calibration", {})
        summary["cohort_calibration"] = {
            key: cohort[key] for key in ("schema", "alpha", "minimum_pairs", "score", "pair_rule", "independence", "identity_sha256") if key in cohort}
        summary["cohort_calibration"]["pair_types"] = {
            name: {key: item[key] for key in ("calibration_count", "real_validation_count", "rank", "cutoff", "cutoff_status",
                                             "actual_shifted_negative_cohort_score", "negative_control_status", "real_validation_counts") if key in item}
            for name, item in cohort.get("pair_types", {}).items()}
    return summary


def file_pin(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError("stage review requires saved workspace evidence")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest}


def prepare(stage3, cutoff, stage4, output, *, supplemental_reports=None):
    pins = {"stage3": file_pin(stage3), "cutoff": file_pin(cutoff), "stage4": file_pin(stage4)}
    product = load_cutoff_material_candidate(ROOT / pins["cutoff"]["path"], expected_sha256=pins["cutoff"]["sha256"])
    reports = {}
    for name in ["stage3", "stage4"]:
        report = json.loads((ROOT / pins[name]["path"]).read_text(encoding="utf-8"))
        reports[name] = report
        if report.get("publishable") is True:
            raise ValueError("candidate review cannot assert publishable capability")
    if reports["stage3"].get("schema") != "td-stage3-native-morphology-evidence-v1" or reports["stage3"].get("status") != "accepted_candidate_contracts":
        raise ValueError("completed native stage3 report required")
    if reports["stage4"].get("schema") != "td-stage4-falsification-v1" or not reports["stage4"].get("status", "").startswith("completed_bounded"):
        raise ValueError("completed bounded stage4 report required")
    bound = reports["stage3"]["artifacts"]["cutoff_material"]
    if (Path(stage3).parent / bound["path"]).resolve() != Path(cutoff).resolve() or bound["sha256"] != pins["cutoff"]["sha256"] or bound["identity_sha256"] != product["identity_sha256"]:
        raise ValueError("stage3 report does not bind supplied cutoff")
    pins["cutoff"]["identity_sha256"] = product["identity_sha256"]
    result = {"schema": "td-natural-stage-review-pin-v1", "artifacts": pins,
              "publishable": False, "hydraulic_ready": False, "natural_outlet_verified": False}
    if supplemental_reports:
        supplements = {}
        for name, path in sorted(supplemental_reports.items()):
            if not isinstance(name, str) or not name:
                raise ValueError("supplemental report name required")
            pin = file_pin(path)
            report = json.loads((ROOT / pin["path"]).read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ValueError("saved supplemental report object required")
            supplements[name] = {**pin, "schema": report.get("schema"), "status": report.get("status"),
                                "summary": supplemental_summary(report)}
        result["supplemental_reports"] = supplements
    publish_bytes(Path(output), (json.dumps(result, indent=2) + "\n").encode("utf-8"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage3", type=Path, required=True)
    parser.add_argument("--cutoff", type=Path, required=True)
    parser.add_argument("--stage4", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "web-preview/data/natural-stage-review-v1/manifest.json")
    parser.add_argument("--supplemental-report", action="append", default=[], metavar="NAME=PATH")
    arguments = parser.parse_args()
    supplemental = {}
    for item in arguments.supplemental_report:
        name, separator, path = item.partition("=")
        if not separator or not name or not path or name in supplemental:
            parser.error("supplemental report requires unique NAME=PATH")
        supplemental[name] = Path(path)
    print(json.dumps(prepare(arguments.stage3, arguments.cutoff, arguments.stage4, arguments.output,
                             supplemental_reports=supplemental)))
