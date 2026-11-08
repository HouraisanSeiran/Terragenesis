"""Real-reference-only calibration of empirical distribution distances."""

import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity


def _samples(values):
    result = np.asarray(values, np.float64)
    if result.ndim != 1 or result.size < 2 or not np.isfinite(result).all():
        raise ValueError("at least two finite samples required")
    return np.sort(result)


def cdf_distance(observed, reference):
    """Two empirical CDF sup-distance, including both sides of tied values."""
    observed, reference = _samples(observed), _samples(reference)
    support = np.unique(np.r_[observed, reference])
    maximum = 0.
    for side in ("left", "right"):
        difference = (np.searchsorted(observed, support, side=side) / observed.size
                      - np.searchsorted(reference, support, side=side) / reference.size)
        maximum = max(maximum, float(np.max(np.abs(difference))))
    return maximum


def calibrate_distribution(training, calibration, *, alpha=.2, conditions=None):
    """Freeze a finite-sample rank cutoff using only real calibration blocks.

    Rank calibration needs exchangeable blocks for coverage guarantees. Spatial
    DEM blocks are correlated, so callers must report observed holdout coverage
    and cannot infer a universal statistical or naturalness certification.
    """
    if not isinstance(alpha, (int, float)) or not 0. < alpha < 1.:
        raise ValueError("alpha must lie strictly between zero and one")
    if not training or not calibration:
        raise ValueError("separate nonempty training and calibration blocks required")
    training_ids = [block["id"] for block in training]
    calibration_ids = [block["id"] for block in calibration]
    if len(set(training_ids + calibration_ids)) != len(training_ids + calibration_ids):
        raise ValueError("training and calibration block ids must be disjoint and unique")
    names = sorted(training[0]["metrics"])
    if any(set(block["metrics"]) != set(names) for block in training + calibration):
        raise ValueError("all calibration blocks must have identical metric census")
    pooled = {name: np.concatenate([_samples(block["metrics"][name]) for block in training])
              for name in names}
    scores = []
    records = []
    for block in calibration:
        values = {name: cdf_distance(block["metrics"][name], pooled[name]) for name in names}
        score = max(values.values())
        scores.append(score)
        records.append({"id": block["id"], "metric_scores": values, "joint_score": score})
    rank = math.ceil((len(scores) + 1) * (1. - alpha))
    cutoff = float(np.sort(scores)[rank - 1]) if rank <= len(scores) else None
    result = {"schema": "real-block-distribution-calibration-v1", "alpha": alpha,
              "conditions": conditions or {}, "training_ids": [block["id"] for block in training],
              "calibration_ids": [block["id"] for block in calibration],
              "reference_samples": {name: values.tolist() for name, values in pooled.items()},
              "calibration_scores": records, "joint_cdf_cutoff": cutoff,
              "rank": rank, "calibration_count": len(scores),
              "cutoff_status": "frozen_real_calibration" if cutoff is not None else "insufficient_calibration",
              "coverage_claim": "empirical_spatial_holdout_only_no_exchangeability_assumption",
              "natural_certification": False}
    result["identity_sha256"] = identity({}, result)
    return result


def evaluate_distribution(metrics, frozen, *, conditions_match):
    """Evaluate one frozen joint test, keeping unmatched conditions unassessed."""
    payload = {key: value for key, value in frozen.items() if key != "identity_sha256"}
    if (frozen.get("schema") != "real-block-distribution-calibration-v1"
            or frozen.get("identity_sha256") != identity({}, payload)):
        raise ValueError("frozen calibration identity mismatch")
    names = frozen["reference_samples"]
    if set(metrics) != set(names):
        raise ValueError("evaluation metric census differs")
    scores = {name: cdf_distance(metrics[name], names[name]) for name in names}
    score = max(scores.values())
    cutoff = frozen["joint_cdf_cutoff"]
    evaluated = conditions_match and cutoff is not None
    return {"metric_scores": scores, "joint_score": score, "cutoff": cutoff,
            "status": "pass" if evaluated and score <= cutoff else "fail" if evaluated else "not_assessed",
            "conditions_match": conditions_match,
            "reference_identity_sha256": frozen["identity_sha256"], "natural_certification": False}
