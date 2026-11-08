"""Versioned compiled exact threshold ODE, preserving the independently verified v2 pair law."""

import numpy as np
import math
from numba import njit

from terrain_pipeline import td_basin_storage
from terrain_pipeline import td_basin_storage_implicit as analytic

PROFILE = "v4-threshold-pair-compiled-6e9-v1"
MAX_WORK_FACE_STEPS = 6_000_000_000


@njit(cache=True)
def _compiled_exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, conductance, ordered, offsets):
    depth = depth.copy()
    forward = np.zeros(len(faces))
    reverse = np.zeros(len(faces))
    forward_s = np.zeros(len(faces))
    reverse_s = np.zeros(len(faces))
    exported = np.zeros(len(boundary))
    area = spacing * spacing
    rate = conductance / spacing
    half = dt_s / 2
    for index in range(len(boundary)):
        cell = boundary[index]
        amount = depth[cell] * (-math.expm1(-conductance * boundary_width[index] / area * half))
        depth[cell] -= amount
        exported[index] += amount * area
    for sweep in range(8):
        group = sweep if sweep < 4 else 7 - sweep
        for cursor in range(offsets[group], offsets[group + 1]):
            index = ordered[cursor]
            first, second = faces[index, 0], faces[index, 1]
            head_first, head_second = bed[first] + depth[first], bed[second] + depth[second]
            positive = head_first >= head_second
            donor = first if positive else second
            recipient = second if positive else first
            sill = max(bed[donor], bed[recipient])
            excess = max(0.0, bed[donor] + depth[donor] - max(sill, bed[recipient] + depth[recipient]))
            if excess == 0 or rate == 0:
                continue
            below = max(0.0, sill - bed[recipient] - depth[recipient])
            if below > 0:
                first_phase = excess * (-math.expm1(-rate * half))
                amount = min(first_phase, below)
                if first_phase > below:
                    crossing_time = -math.log1p(-below / excess) / rate
                    amount = below + (excess - below) / 2 * (-math.expm1(-2 * rate * (half - crossing_time)))
            else:
                amount = excess / 2 * (-math.expm1(-2 * rate * half))
            amount = min(amount, depth[donor])
            depth[donor] -= amount
            depth[recipient] += amount
            if positive:
                forward[index] += amount * area
                if amount > 0:
                    forward_s[index] += half
            else:
                reverse[index] += amount * area
                if amount > 0:
                    reverse_s[index] += half
    for index in range(len(boundary)):
        cell = boundary[index]
        amount = depth[cell] * (-math.expm1(-conductance * boundary_width[index] / area * half))
        depth[cell] -= amount
        exported[index] += amount * area
    return depth, forward, reverse, exported, forward_s, reverse_s


def parameters(supplied):
    supplied = {} if supplied is None else dict(supplied)
    requested_budget = supplied.pop("max_work_face_steps", MAX_WORK_FACE_STEPS)
    if type(requested_budget) is not int or not 1 <= requested_budget <= MAX_WORK_FACE_STEPS:
        raise ValueError("refinement work budget exceeded")
    supplied["max_work_face_steps"] = min(requested_budget, analytic.DEFAULT_PARAMETERS["max_work_face_steps"])
    result = analytic.parameters(supplied)
    result["max_work_face_steps"] = requested_budget
    return result


def simulate_basin_storage(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None, runoff_parameters=None, parameters=None):
    faces = hierarchy["arrays"]["face_cells"]
    columns = hierarchy["arrays"]["height_m"].shape[1]
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(np.flatnonzero(groups == group) for group in range(4))
    ordered = np.concatenate(prepared)
    offsets = np.concatenate(([0], np.cumsum([len(values) for values in prepared])))

    class RefinementSolver:
        parameters = staticmethod(globals()["parameters"])

        @staticmethod
        def metadata(config):
            return {**analytic.metadata(config), "algorithm": "D4-threshold-exact-Strang-v4", "work_profile": PROFILE,
                    "execution": "numba scalar matching sweeps; float64 no fastmath; same analytic pair law"}

        @staticmethod
        def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
            return _compiled_exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s,
                                      config["face_conductance_m_s"], ordered, offsets)

    return td_basin_storage.simulate_basin_storage(hierarchy, rain_mm_h, dt_s=dt_s, initial_depth_m=initial_depth_m,
        runoff_parameters=runoff_parameters, parameters=parameters, _face_solver=RefinementSolver)

def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(np.flatnonzero(groups == group) for group in range(4))
    ordered = np.concatenate(prepared)
    offsets = np.concatenate(([0], np.cumsum([len(values) for values in prepared])))
    return _compiled_exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s,
                              config["face_conductance_m_s"], ordered, offsets)

