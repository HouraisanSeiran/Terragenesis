"""Simultaneous conservative D4 SSP-RK2 threshold transport, without donor caps."""

import numpy as np
from numba import njit

PROFILE = "v6-simultaneous-SSPRK2-6e9-v1"


@njit(cache=True)
def _stage(depth, bed, faces, boundary, widths, spacing, conductance):
    derivative = np.zeros(len(depth))
    flux = np.zeros(len(faces))
    exported = np.zeros(len(boundary))
    for index in range(len(faces)):
        first, second = faces[index, 0], faces[index, 1]
        first_head = bed[first] + depth[first]
        second_head = bed[second] + depth[second]
        sill = max(bed[first], bed[second])
        if first_head >= second_head:
            rate = conductance / spacing * max(first_head - max(sill, second_head), 0.0)
        else:
            rate = -conductance / spacing * max(second_head - max(sill, first_head), 0.0)
        flux[index] = rate
        derivative[first] -= rate
        derivative[second] += rate
    for index in range(len(boundary)):
        cell = boundary[index]
        rate = conductance * widths[index] / (spacing * spacing) * depth[cell]
        exported[index] = rate
        derivative[cell] -= rate
    return derivative, flux, exported


@njit(cache=True)
def _compiled_exchange(depth, bed, faces, boundary, widths, spacing, dt_s, conductance, ordered, offsets):
    derivative0, flux0, boundary0 = _stage(depth, bed, faces, boundary, widths, spacing, conductance)
    stage1 = depth + dt_s * derivative0
    if np.any(stage1 < 0):
        raise ValueError("SSP-RK2 negative Euler stage; no clamp permitted")
    derivative1, flux1, boundary1 = _stage(stage1, bed, faces, boundary, widths, spacing, conductance)
    stage2 = stage1 + dt_s * derivative1
    if np.any(stage2 < 0):
        raise ValueError("SSP-RK2 negative second Euler stage; no clamp permitted")
    final = 0.5 * depth + 0.5 * stage2
    area = spacing * spacing
    half = dt_s / 2
    forward = half * area * (np.maximum(flux0, 0) + np.maximum(flux1, 0))
    reverse = half * area * (np.maximum(-flux0, 0) + np.maximum(-flux1, 0))
    forward_s = half * ((flux0 > 0).astype(np.float64) + (flux1 > 0).astype(np.float64))
    reverse_s = half * ((flux0 < 0).astype(np.float64) + (flux1 < 0).astype(np.float64))
    exported = half * area * (boundary0 + boundary1)
    return final, forward, reverse, exported, forward_s, reverse_s


def validate_cfl(faces, boundary, widths, spacing, dt_s, conductance, cells):
    degree = np.bincount(faces.reshape(-1), minlength=cells).astype(float)
    np.add.at(degree, boundary, widths / spacing)
    maximum = float(degree.max(initial=0)) * conductance * dt_s / spacing
    if not np.isfinite(maximum) or maximum > 1:
        raise ValueError("SSP-RK2 positivity CFL exceeded")
    return maximum
