"""Aggregate all frozen noise-generation samples without selecting successes."""

import argparse
import json
from pathlib import Path

import numpy as np

from tools.verify_td_channel_distribution import evaluate, file_sha256


def summarize(reference_path, generation_path, output, *, development=False):
    reference_path, generation_path, output = map(Path, (reference_path, generation_path, output))
    output.mkdir(parents=True, exist_ok=False)
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if generation["status"] != "completed" or len(generation["samples"]) != 6:
        raise ValueError("all six planned generation samples must complete")
    results = []
    products = []
    for sample in generation["samples"]:
        source = generation_path.parent / sample["raw_npz"]
        destination = output / (source.stem + ".json")
        result = evaluate(reference_path, source, sample["raw_sha256"], destination,
                          generation_path if development else None)
        results.append(result)
        products.append({"path": str(destination.resolve()), "sha256": file_sha256(destination),
                         "source_sha256": sample["raw_sha256"], "seed": sample["seed"],
                         "native_origin": sample["native_origin"]})
    cases = [case for result in results for case in result["cases"]]
    status_counts = lambda values: {status: values.count(status) for status in ("pass", "fail", "not_assessed")}
    pairs = reference["cohort_calibration"]["pair_types"]
    pair_summary = {}
    for key, pair in pairs.items():
        separations = [item["separation_abs_xz_m"] for item in pair["calibration_pairs"] + pair["real_validation_pairs"]]
        pair_summary[key] = {name: pair[name] for name in (
            "calibration_count", "real_validation_count", "cutoff", "real_validation_counts", "negative_control_status")}
        pair_summary[key]["actual_abs_xz_separation_range_m"] = [np.min(separations, axis=0).tolist(), np.max(separations, axis=0).tolist()]
    report = {"schema": "TD-noise-independent-evaluation-summary-v1", "products": products,
              "reference_path": str(reference_path.resolve()), "reference_sha256": file_sha256(reference_path),
              "generation_report_path": str(generation_path.resolve()), "generation_report_sha256": file_sha256(generation_path),
              "generation_plan_sha256": generation["plan_sha256"],
              "evaluation_role": "development_only" if development else "independent_holdout",
              "individual_window_counts": status_counts([case["distribution_evaluation_relief_grid_only"]["status"] for case in cases]),
              "two_window_cohort_counts": status_counts([result["cohort_evaluation"]["status"] for result in results]),
              "noise_climate_physical_counts": status_counts([case["noise_climate_physical_evaluation"]["physical_model_status"] for case in cases]),
              "cohort_results": [result["cohort_evaluation"] | {"seed": result["source_metadata"]["seed"],
                  "native_origin": result["source_metadata"]["native_origin"]} for result in results],
              "real_block_validation": reference["relief_grid_real_holdout_summary"],
              "real_pair_calibration_validation": pair_summary,
              "sampling_limit": "two_seeds_three_source_condition_selected_domains_each;windows_within_domains_and_same_seed_related",
              "real_reference_limit": "same_SRTM_product_spatial_dependence;target_grid_nonoverlap_not_source_pixel_independence",
              "climate_limit": "canonical_deterministic_monthly_noise_climate;upstream_auxiliary_BIO_separate;real_WorldClim_context_descriptive",
              "natural_certification": False, "default_world_publication": False}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--generation-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    report = summarize(args.reference, args.generation_report, args.output, development=args.development)
    print(json.dumps({name: report[name] for name in ("individual_window_counts", "two_window_cohort_counts", "noise_climate_physical_counts")}))
