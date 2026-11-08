"""Isolated non-fastmath acceleration of the frozen implicit-drag face law."""

import math
import types

import numpy as np
from numba import njit

from terrain_pipeline import regional_surface_hydraulics as reference


@njit(fastmath=False, cache=True)
def face_kernel(stage_left, stage_right, crest, previous_q, dt, width, distance, gravity, roughness):
    result = np.zeros(previous_q.size)
    depths = np.zeros(previous_q.size)
    for index in range(previous_q.size):
        depth = max(max(stage_left[index], stage_right[index]) - crest[index], 0.)
        depths[index] = depth
        if depth > 0:
            old = previous_q[index] / width
            rhs = old - gravity * depth * dt * (stage_right[index] - stage_left[index]) / distance
            drag = gravity * dt * roughness**2 / depth**(7 / 3)
            result[index] = width * 2 * rhs / (1 + math.sqrt(1 + 4 * drag * abs(rhs)))
    return result, depths


def inertial_face_flux(stage_left, stage_right, crest, previous_q, dt_s, spacing_m, distance_m, budget):
    return face_kernel(stage_left, stage_right, crest, previous_q, dt_s, spacing_m, distance_m,
        budget.gravity_m_s2, budget.roughness_s_m_third)


@njit(fastmath=False, cache=True)
def limiter_kernel(depth, forcing, internal, boundary, left, right, cells, dt, area):
    outgoing_left = np.zeros(depth.size)
    outgoing_right = np.zeros(depth.size)
    outgoing_boundary = np.zeros(depth.size)
    for index in range(internal.size):
        outgoing_left[left[index]] += max(internal[index], 0.)
    for index in range(internal.size):
        outgoing_right[right[index]] += max(-internal[index], 0.)
    for index in range(boundary.size):
        outgoing_boundary[cells[index]] += max(boundary[index], 0.)
    factors = np.ones(depth.size)
    count = 0
    minimum = 1.
    for index in range(depth.size):
        outgoing = outgoing_left[index] + outgoing_right[index] + outgoing_boundary[index]
        available = depth[index] * area + dt * forcing[index]
        if outgoing * dt > available:
            factors[index] = available / (outgoing * dt) * (1 - 1e-12)
            count += 1
            minimum = min(minimum, factors[index])
    removed_internal = raw_internal = removed_boundary = raw_boundary = 0.
    for index in range(internal.size):
        raw = internal[index]
        factor = factors[left[index]] if raw >= 0 else factors[right[index]]
        internal[index] *= factor
        removed_internal += abs(raw - internal[index])
        raw_internal += abs(raw)
    for index in range(boundary.size):
        raw = boundary[index]
        if raw >= 0:
            boundary[index] *= factors[cells[index]]
        removed_boundary += abs(raw - boundary[index])
        raw_boundary += abs(raw)
    return count, (removed_internal + removed_boundary) * dt, (raw_internal + raw_boundary) * dt, minimum


def limited_inertial_fluxes(geometry, depth, previous_internal, previous_boundary, tailwater, forcing, dt_s, budget):
    arrays = geometry["arrays"]
    stage = arrays["H2_m"].ravel() + depth
    spacing = geometry["metadata"]["spacing_m"]
    left, right, cells = arrays["face_left"], arrays["face_right"], arrays["boundary_cell"]
    internal, _ = inertial_face_flux(stage[left], stage[right], arrays["face_crest_m"], previous_internal, dt_s, spacing, spacing, budget)
    exterior = np.where(arrays["boundary_kind"] == 1, arrays["boundary_crest_m"], tailwater)
    boundary, _ = inertial_face_flux(stage[cells], exterior, arrays["boundary_crest_m"], previous_boundary, dt_s, spacing, spacing / 2, budget)
    boundary[arrays["boundary_kind"] == 0] = 0.
    raw_internal, raw_boundary = internal.copy(), boundary.copy()
    count, removed, raw, minimum = limiter_kernel(depth, forcing, internal, boundary, left, right, cells, dt_s, spacing**2)
    removed = float((np.abs(raw_internal - internal).sum() + np.abs(raw_boundary - boundary).sum()) * dt_s)
    raw = float((np.abs(raw_internal).sum() + np.abs(raw_boundary).sum()) * dt_s)
    return internal, boundary, {"limited_donors": count, "removed_transfer_m3": removed,
        "raw_transfer_m3": raw, "minimum_factor": minimum,
        "trigger": "sum_outgoing_dt_exceeds_donor_volume_plus_local_input"}


def advance_accelerated_surface(*args, **kwargs):
    namespace = dict(reference.advance_inertial_surface.__globals__)
    namespace["limited_inertial_fluxes"] = limited_inertial_fluxes
    advance = types.FunctionType(reference.advance_inertial_surface.__code__, namespace,
        reference.advance_inertial_surface.__name__, reference.advance_inertial_surface.__defaults__)
    advance.__kwdefaults__ = reference.advance_inertial_surface.__kwdefaults__
    result = advance(*args, **kwargs)
    result["metadata"]["execution_backend"] = "numba_face_limiter_fastmath_false_v1_reference_control_flow"
    return result
