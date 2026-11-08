"""Pure continuous wet-polygon moment prototype; no hydraulic execution.

Local coordinates cover [-.5,.5]^2. Exact affine-product triangle integrals
retain full moment rank even when a wet sliver contains no canonical midpoint.
"""

from itertools import product
from math import factorial

import numpy as np


def clip_tile(coefficients, bounds):
    xmin, xmax, zmin, zmax = bounds
    polygon = np.array([[xmin, zmin], [xmax, zmin], [xmax, zmax], [xmin, zmax]])
    result = []
    previous = polygon[-1]
    previous_value = coefficients[0]+previous@coefficients[1:]
    for current in polygon:
        value = coefficients[0]+current@coefficients[1:]
        if (value > 0) != (previous_value > 0):
            result.append(previous+previous_value/(previous_value-value)*(current-previous))
        if value > 0:
            result.append(current)
        previous, previous_value = current, value
    return np.asarray(result)


def affine_product_integral(vertex_values, area):
    """Exact simplex integral of a product of zero to three affine fields."""
    degree = len(vertex_values)
    value = 0.
    for indices in product(range(3), repeat=degree):
        counts = np.bincount(indices, minlength=3)
        coefficient = 2*area*np.prod([factorial(int(count)) for count in counts])/factorial(degree+2)
        for field, index in zip(vertex_values, indices):
            coefficient *= field[index]
        value += coefficient
    return value


def profile_moments(stage_coefficients, positional_bed):
    """Return water moments, wet-domain Jacobian and h-weighted velocity Gram."""
    stage_coefficients = np.asarray(stage_coefficients, np.float64)
    positional_bed = np.asarray(positional_bed, np.float64)
    if (stage_coefficients.shape != (3,) or positional_bed.ndim != 2 or
            positional_bed.shape[0] != positional_bed.shape[1] or not positional_bed.size or
            not np.isfinite(stage_coefficients).all() or not np.isfinite(positional_bed).all()):
        raise ValueError("finite affine stage and nonempty square positional bed required")
    factor = len(positional_bed)
    edges = np.linspace(-.5, .5, factor+1)
    moments = np.zeros(3)
    jacobian = np.zeros((3, 3))
    gram = np.zeros((3, 3))
    for row in range(factor):
        for column in range(factor):
            depth = stage_coefficients.copy()
            depth[0] -= positional_bed[row, column]
            polygon = clip_tile(depth, (edges[column], edges[column+1], edges[row], edges[row+1]))
            for index in range(1, len(polygon)-1):
                triangle = polygon[[0, index, index+1]]
                first, second = triangle[1]-triangle[0], triangle[2]-triangle[0]
                area = abs(first[0]*second[1]-first[1]*second[0])/2
                phi = np.column_stack((np.ones(3), triangle)).T
                h = depth@phi
                for i in range(3):
                    moments[i] += affine_product_integral([h, phi[i]], area)
                    for j in range(3):
                        jacobian[i, j] += affine_product_integral([phi[i], phi[j]], area)
                        gram[i, j] += affine_product_integral([h, phi[i], phi[j]], area)
    return moments, jacobian, gram


def invert_water_moments(target, positional_bed, *, initial_coefficients, tolerance=1e-12, max_iterations=60):
    target = np.asarray(target, np.float64)
    if target.shape != (3,) or target[0] <= 0 or not np.isfinite(target).all():
        raise ValueError("positive finite water moment target required")
    if np.any(abs(target[1:]) >= .5*target[0]):
        raise ValueError("water moments outside the cell realizability bounds")
    coefficients = np.asarray(initial_coefficients, np.float64).copy()
    if coefficients.shape != (3,) or not np.isfinite(coefficients).all():
        raise ValueError("finite initial affine stage required")
    scale = max(float(target[0]), 1e-12)
    for iteration in range(max_iterations):
        moments, jacobian, gram = profile_moments(coefficients, positional_bed)
        residual = moments-target
        error = float(np.linalg.norm(residual)/scale)
        if error <= tolerance:
            return coefficients, dict(iterations=iteration, relative_residual=error,
                wet_jacobian_condition=float(np.linalg.cond(jacobian)), velocity_gram_condition=float(np.linalg.cond(gram)))
        if not np.isfinite(jacobian).all() or np.linalg.cond(jacobian) > 1e14:
            raise ValueError("wet moment inverse is singular or too poorly conditioned")
        step = np.linalg.solve(jacobian, residual)
        length = 1.
        for _ in range(30):
            proposed = coefficients-length*step
            proposed_moments, _, _ = profile_moments(proposed, positional_bed)
            if np.linalg.norm(proposed_moments-target) < np.linalg.norm(residual):
                coefficients = proposed
                break
            length *= .5
        else:
            raise ValueError("water moment inverse line search refused")
    raise ValueError("water moment inverse iteration budget exceeded")


def invert_velocity_moments(momentum_moments, gram, *, max_condition=1e14):
    momentum_moments, gram = np.asarray(momentum_moments, np.float64), np.asarray(gram, np.float64)
    if (gram.shape != (3, 3) or momentum_moments.shape not in ((3,), (3, 2)) or
            not np.isfinite(gram).all() or not np.isfinite(momentum_moments).all()):
        raise ValueError("finite velocity Gram and three momentum moments required")
    if np.linalg.cond(gram) > max_condition:
        raise ValueError("wet velocity moment map is poorly conditioned")
    return np.linalg.solve(gram, momentum_moments)

