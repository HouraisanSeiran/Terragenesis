"""Unconditionally positive exact pair exchange; bounded Strang splitting v2."""

import math

import numpy as np

from terrain_pipeline import td_basin_storage

DEFAULT_PARAMETERS = {"substep_s": 60.0, "face_conductance_m_s": 0.6, "surface_evaporation_mm_h": 0.15,
    "wet_threshold_m": 1e-9, "max_substeps": 100000, "max_work_face_steps": 3_000_000_000}


def parameters(supplied):
    supplied = {} if supplied is None else dict(supplied)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown v2 storage parameters")
    result = {**DEFAULT_PARAMETERS, **supplied}
    for key in ("substep_s", "face_conductance_m_s", "surface_evaporation_mm_h", "wet_threshold_m"):
        if type(result[key]) not in (int, float) or not math.isfinite(result[key]) or result[key] < 0:
            raise ValueError("invalid v2 coefficient")
    if result["substep_s"] <= 0 or result["wet_threshold_m"] <= 0:
        raise ValueError("positive v2 step/threshold required")
    for key in ("max_substeps", "max_work_face_steps"):
        if type(result[key]) is not int or not 1 <= result[key] <= DEFAULT_PARAMETERS[key]:
            raise ValueError("v2 work budget rejected")
    return result


def metadata(config):
    return {"algorithm": "D4-analytic-face-Strang-splitting-v2", "limiter_semantics": "no quarter cap; each pair solves exact threshold linear ODE",
        "solver_semantics": "four disjoint D4 matching groups, symmetric forward/reverse half sweeps; exact boundary exponential half steps",
        "work_bound": "at most two analytic face visits per substep, finite declared work budget; no nonlinear iterations",
        "transient_converged": False, "morphology_flux_ready": False}


def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns, prepared=None):
    depth = depth.copy()
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = np.where(horizontal, first % columns % 2, 2 + first // columns % 2) if prepared is None else None
    forward = np.zeros(len(faces))
    reverse = np.zeros(len(faces))
    forward_s = np.zeros(len(faces))
    reverse_s = np.zeros(len(faces))
    conductance = config["face_conductance_m_s"]
    area = spacing ** 2
    boundary_factor = -np.expm1(-conductance * boundary_width / area * dt_s / 2)
    exported = depth[boundary] * boundary_factor * area
    depth[boundary] *= 1 - boundary_factor
    rate = conductance / spacing
    half = dt_s / 2
    for group in (0, 1, 2, 3, 3, 2, 1, 0):
        indices = np.flatnonzero(groups == group) if prepared is None else prepared[group]
        first_selected, second_selected = first[indices], second[indices]
        head_first = bed[first_selected] + depth[first_selected]
        head_second = bed[second_selected] + depth[second_selected]
        positive = head_first >= head_second
        donor = np.where(positive, first_selected, second_selected)
        recipient = np.where(positive, second_selected, first_selected)
        sill = np.maximum(bed[donor], bed[recipient])
        donor_head = bed[donor] + depth[donor]
        recipient_head = bed[recipient] + depth[recipient]
        excess = np.maximum(0, donor_head - np.maximum(sill, recipient_head))
        below = np.maximum(0, sill - recipient_head)
        first_phase = excess * (-np.expm1(-rate * half))
        crosses = (below > 0) & (first_phase > below)
        transfer = np.where(below > 0, np.minimum(first_phase, below), excess / 2 * (-np.expm1(-2 * rate * half)))
        if crosses.any() and rate > 0:
            crossing_time = -np.log1p(-below[crosses] / excess[crosses]) / rate
            remaining = half - crossing_time
            transfer[crosses] = below[crosses] + (excess[crosses] - below[crosses]) / 2 * (-np.expm1(-2 * rate * remaining))
        transfer = np.minimum(transfer, depth[donor])
        depth[donor] -= transfer
        depth[recipient] += transfer
        forward[indices] += np.where(positive, transfer * area, 0)
        reverse[indices] += np.where(positive, 0, transfer * area)
        forward_s[indices] += (positive & (transfer > 0)) * half
        reverse_s[indices] += (~positive & (transfer > 0)) * half
    final_export = depth[boundary] * boundary_factor * area
    depth[boundary] *= 1 - boundary_factor
    exported += final_export
    return depth, forward, reverse, exported, forward_s, reverse_s


def simulate_basin_storage(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None, runoff_parameters=None, parameters=None):
    faces = hierarchy["arrays"]["face_cells"]
    columns = hierarchy["arrays"]["height_m"].shape[1]
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(np.flatnonzero(groups == group) for group in range(4))
    class PreparedSolver:
        parameters = staticmethod(globals()["parameters"])
        metadata = staticmethod(globals()["metadata"])

        @staticmethod
        def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
            return exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns, prepared)

    return td_basin_storage.simulate_basin_storage(hierarchy, rain_mm_h, dt_s=dt_s, initial_depth_m=initial_depth_m,
        runoff_parameters=runoff_parameters, parameters=parameters, _face_solver=PreparedSolver)
