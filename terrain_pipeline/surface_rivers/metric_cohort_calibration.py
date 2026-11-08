"""Finite empirical calibration of two-window, relief-conditioned geometry cohorts."""

import math

import numpy as np

from terrain_pipeline.common_infra import identity
from .metric_distribution_calibration import evaluate_distribution


def pair_key(first, second):
    return ":".join(sorted((first, second)))


def _spatial_pairs(blocks, first, second):
    eligible = [block for block in blocks if block.get("condition") in {first, second} and block["status"] == "measured"]
    candidates = []
    for index, block in enumerate(eligible):
        for other in eligible[index + 1:]:
            if block.get("crs") != other.get("crs"):
                continue
            if sorted((block["condition"], other["condition"])) != sorted((first, second)):
                continue
            a, b = block["world_extent_xz_m"], other["world_extent_xz_m"]
            dx, dz = abs(a[0] - b[0]), abs(a[1] - b[1])
            mismatch = math.hypot(dx - 5760., dz - 5760.)
            candidates.append((mismatch, block["id"], other["id"], dx, dz, block, other))
    used = set()
    pairs = []
    for mismatch, first_id, second_id, dx, dz, first_block, second_block in sorted(candidates, key=lambda item: item[:3]):
        if first_id in used or second_id in used:
            continue
        used.update((first_id, second_id))
        pairs.append({"ids": [first_id, second_id], "separation_abs_xz_m": [dx, dz],
                      "crs": first_block.get("crs"),
                      "TD_separation_abs_xz_m": [5760., 5760.], "separation_mismatch_m": mismatch,
                      "blocks": [first_block, second_block]})
    return pairs


def _score_pair(pair, calibrations):
    scores = [evaluate_distribution(block["metrics"], calibrations[block["condition"]], conditions_match=True)["joint_score"]
              for block in pair["blocks"]]
    return {key: value for key, value in pair.items() if key != "blocks"} | {
        "block_joint_cdf_scores": scores, "cohort_score": float(np.mean(scores))}


def calibrate_cohorts(blocks, calibrations, *, alpha=.2, minimum_pairs=4):
    """Each pair type has separate calibration and genuine real heldout validation.

    Closest physical pairs are deterministic and do not reuse a block within a
    pair type. Alternative condition-census libraries are not independent trials.
    """
    if not 0. < alpha < 1. or type(minimum_pairs) is not int or minimum_pairs < 4:
        raise ValueError("alpha in (0,1) and at least four pairs required")
    classes = sorted(calibrations)
    outputs = {}
    shifted_scores = {}
    for condition, frozen in calibrations.items():
        shifted = {name: (np.asarray(values) + max(1., float(np.ptp(values))) + float(np.max(values)) - float(np.min(values))).tolist()
                   for name, values in frozen["reference_samples"].items()}
        shifted_scores[condition] = evaluate_distribution(shifted, frozen, conditions_match=True)["joint_score"]
    for index, first in enumerate(classes):
        for second in classes[index:]:
            key = pair_key(first, second)
            calibration = [_score_pair(pair, calibrations) for pair in _spatial_pairs(
                [block for block in blocks if block["role"] == "calibration"], first, second)]
            validation = [_score_pair(pair, calibrations) for pair in _spatial_pairs(
                [block for block in blocks if block["role"] == "real_holdout"], first, second)]
            rank = math.ceil((len(calibration) + 1) * (1. - alpha))
            supported = min(len(calibration), len(validation)) >= minimum_pairs and rank <= len(calibration)
            cutoff = float(np.sort([pair["cohort_score"] for pair in calibration])[rank - 1]) if supported else None
            for pair in validation:
                pair["status"] = "pass" if cutoff is not None and pair["cohort_score"] <= cutoff else "fail" if cutoff is not None else "not_assessed"
            negative_score = float(np.mean([shifted_scores[first], shifted_scores[second]]))
            outputs[key] = {"calibration_pairs": calibration, "real_validation_pairs": validation,
                "calibration_count": len(calibration), "real_validation_count": len(validation),
                "rank": rank, "cutoff": cutoff, "cutoff_status": "frozen_real_pair_calibration" if supported else "insufficient_real_pairs",
                "actual_shifted_negative_cohort_score": negative_score,
                "negative_control_status": "fail" if cutoff is not None and negative_score > cutoff else "not_assessed" if cutoff is None else "pass",
                "real_validation_counts": {status: sum(pair["status"] == status for pair in validation) for status in ("pass", "fail", "not_assessed")}}
    result = {"schema": "metric-two-window-cohort-calibration-v1", "alpha": alpha, "minimum_pairs": minimum_pairs,
        "score": "mean_of_two_relief_conditioned_joint_CDF_distances", "pair_types": outputs,
        "pair_rule": "greedy_minimum_deviation_from_abs_5760m_x_5760m_target_separation_stable_ID_ties_no_block_reuse_within_pair_type",
        "independence": "spatially_related_same_real_product;alternative_pair_type_libraries_not_independent;empirical_only",
        "natural_certification": False}
    result["identity_sha256"] = identity({}, result)
    return result


def evaluate_cohort(cases, frozen):
    if frozen.get("identity_sha256") != identity({}, {key: value for key, value in frozen.items() if key != "identity_sha256"}):
        raise ValueError("cohort reference identity differs")
    if len(cases) != 2:
        raise ValueError("exactly two predeclared windows per spatial cohort required")
    key = pair_key(*(case["relief_class"] for case in cases))
    reference = frozen["pair_types"].get(key)
    scores = [case["distribution_evaluation_relief_grid_only"].get("joint_score") for case in cases]
    if not reference or reference["cutoff"] is None or any(score is None for score in scores):
        return {"condition_pair": key, "status": "not_assessed", "reason": "insufficient_real_pair_support_or_channel_samples"}
    score = float(np.mean(scores))
    return {"condition_pair": key, "score": score, "cutoff": reference["cutoff"],
        "status": "pass" if score <= reference["cutoff"] else "fail",
        "individual_rejections_retained": [case["distribution_evaluation_relief_grid_only"]["status"] for case in cases],
        "interpretation": "finite_empirical_two_window_product_test_not_universal_naturalness", "natural_certification": False}
