"""Empirical conversion of a reference reach deposition fraction by length."""
import math


def deposition_fraction_for_length(reference_fraction, reference_length_m, length_m):
    """Return the fraction retained over length_m for a uniform reach.

    The reference fraction applies over reference_length_m metres. This is an
    empirical exponential length-decay approximation, not a grain-size or
    bed-load capacity model. Fractions are in [0, 1], reference length is
    positive, and actual length is nonnegative; all inputs must be finite.
    """
    if (not all(math.isfinite(value) for value in
                (reference_fraction, reference_length_m, length_m))
            or not 0 <= reference_fraction <= 1
            or reference_length_m <= 0 or length_m < 0):
        raise ValueError('invalid deposition fraction or reach length')
    if length_m == 0 or reference_fraction == 0:
        return 0.0
    if reference_fraction == 1:
        return 1.0
    decay = -math.log1p(-reference_fraction)
    ratio = length_m / reference_length_m
    exponent = decay * ratio
    if not math.isfinite(exponent) or exponent == 0:
        log_exponent = math.log(decay) + math.log(length_m) - math.log(reference_length_m)
        if log_exponent > math.log(745.0):
            return 1.0
        exponent = math.exp(log_exponent)
    return -math.expm1(-exponent)
