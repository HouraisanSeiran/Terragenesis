"""Physical checks and descriptive real-context comparisons for noise climate."""

import numpy as np

from .metric_noise_forcing import sample_climate


def physical_bio_context(values, real_reference):
    values = np.asarray(values, np.float64)
    if values.shape[0] != 4 or not np.isfinite(values).all():
        raise ValueError("four finite BIO physical channels required")
    reference = real_reference["physical_reference"]
    observations = values.reshape(4, -1)
    names = ("BIO1", "BIO4", "BIO12", "BIO15")
    context = {}
    for index, name in enumerate(names):
        lower, upper = reference["quantiles"][name][0], reference["quantiles"][name][-1]
        sample = observations[index]
        context[name] = {"observed_range": [float(sample.min()), float(sample.max())],
            "real_product_range": [lower, upper], "outside_real_product_range_count": int(((sample < lower) | (sample > upper)).sum())}
    bins = np.searchsorted([0., 10., 20., 30.], observations[0], side="right")
    conditioned = []
    for envelope in reference["temperature_conditioned_joint_envelopes"]:
        selected = bins == envelope["BIO1_bin"]
        if not selected.any():
            continue
        departures = {}
        for index, name in enumerate(names[1:], 1):
            lower, upper = envelope["quantiles"][name][0], envelope["quantiles"][name][-1]
            sample = observations[index, selected]
            departures[name] = int(((sample < lower) | (sample > upper)).sum())
        conditioned.append({"temperature_class": envelope["BIO1_bin"], "sample_count": int(selected.sum()),
                            "outside_temperature_conditioned_real_range": departures})
    return {"univariate": context, "temperature_conditioned_joint_context": conditioned,
            "role": "observed_product_descriptive_context_not_universal_physical_impossibility_or_geographic_match",
            "real_product_weighting": reference["statistical_weighting"]}


def audit_noise_climate(seed, x_m, z_m, elevation_m, real_reference, *, parameters=None):
    climate = sample_climate(seed, x_m, z_m, elevation_m, parameters=parameters)
    temperature, precipitation = climate["monthly_temperature_c"], climate["monthly_precipitation_mm"]
    expected = np.stack((temperature.mean(axis=0), temperature.std(axis=0) * 100., precipitation.sum(axis=0),
                         precipitation.std(axis=0) / precipitation.mean(axis=0) * 100.))
    checks = {"monthly_finite": bool(np.isfinite(temperature).all() and np.isfinite(precipitation).all()),
              "monthly_precipitation_nonnegative": bool((precipitation >= 0.).all()),
              "BIO_from_same_months": bool(np.array_equal(expected, climate["BIO1_4_12_15"]))}
    return {"schema": "metric-noise-climate-physical-audit-v1", "seed": seed,
        "parameter_identity_sha256": climate["parameter_identity_sha256"], "checks": checks,
        "physical_model_status": "pass" if all(checks.values()) else "fail",
        "real_context": physical_bio_context(climate["BIO1_4_12_15"], real_reference),
        "forcing_semantics": "synthetic_weather;monthly_targets_are_not_realized_annual_rainfall_or_observations",
        "natural_certification": False}
