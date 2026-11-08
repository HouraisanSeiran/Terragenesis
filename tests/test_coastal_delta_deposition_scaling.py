import math

import pytest

from terrain_pipeline.coastal_delta_deposition_scaling import deposition_fraction_for_length


def remaining(lengths):
    sediment = 1.0
    for length in lengths:
        sediment *= 1 - deposition_fraction_for_length(0.01, 600, length)
    return sediment


def test_sixty_kilometres_is_independent_of_partition():
    coarse = remaining([600] * 100)
    fine = remaining([100] * 600)
    mixed = remaining([100, 400, 2500, 57000])
    assert coarse == pytest.approx(0.99 ** 100, rel=1e-13)
    assert fine == pytest.approx(coarse, rel=1e-13)
    assert mixed == pytest.approx(coarse, rel=1e-13)
    assert remaining([57000, 2500, 400, 100]) == pytest.approx(mixed, rel=1e-14)


def test_endpoints_and_small_fraction():
    f = deposition_fraction_for_length
    assert f(0, 600, 100) == 0
    assert f(1, 600, 0) == 0
    assert f(1, 600, 100) == 1
    assert f(0.01, 600, 600) == pytest.approx(0.01)
    assert f(1e-20, 600, 100) == pytest.approx(1e-20 / 6)
    assert f(1e-300, 1e-300, 1e100) == pytest.approx(-math.expm1(-1e100))
    assert f(1e-300, 1e-300, 1) == pytest.approx(-math.expm1(-1))


@pytest.mark.parametrize('fraction, reference, length', [
    (-0.01, 600, 100), (1.01, 600, 100), (0.01, 0, 100),
    (0.01, -1, 100), (0.01, 600, -1), (math.nan, 600, 100),
    (0.01, math.inf, 100), (0.01, 600, math.inf),
])
def test_invalid_inputs_rejected(fraction, reference, length):
    with pytest.raises(ValueError):
        deposition_fraction_for_length(fraction, reference, length)
