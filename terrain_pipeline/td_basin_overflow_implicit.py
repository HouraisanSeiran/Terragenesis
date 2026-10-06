"""Versioned stable basin exchange, independent of the frozen explicit diagnostic."""

from dataclasses import asdict
import math
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.td_basin_overflow import (MAX_STEPS, OverflowParameters, _stage_at,
                                               _topology_identity, validate_overflow_event)


ALGORITHM = "implicit-original-bed-basin-face-exchange-v3"
MAX_ARRAY_BYTES = 128 * 1024 * 1024


class _ReservoirSystem:
    def __init__(self, topology, config):
        if topology["identity_sha256"] != _topology_identity(topology):
            raise ValueError("implicit reservoir topology identity mismatch")
        arrays = topology["arrays"]
        self.count = len(arrays["leaf_ids"])
        self.offsets = arrays["curve_offsets"]
        self.levels = arrays["curve_level_m"]
        self.areas = arrays["curve_area_m2"]
        self.bottom = self.levels[self.offsets[:-1]]
        self.curve_owner = np.repeat(np.arange(self.count), np.diff(self.offsets))
        self.relative_levels = self.levels - self.bottom[self.curve_owner]
        lookup = {int(leaf): index for index, leaf in enumerate(arrays["leaf_ids"])}
        self.first = np.array([lookup[face["leaf_ids"][0]] for face in topology["faces"]], np.int64)
        self.second = np.array([lookup[face["leaf_ids"][1]] for face in topology["faces"]], np.int64)
        sill = np.array([face["sill_m"] for face in topology["faces"]])
        self.first_sill = sill - self.bottom[self.first]
        self.second_sill = sill - self.bottom[self.second]
        self.conductance = config.face_conductance_m_s * float(topology["metadata"]["spacing_m"])
        self.boundary_leaf = np.array([lookup[face["leaf_id"]] for face in topology["engineering_boundaries"]], np.int64)
        self.boundary_sill = np.array([face["sill_m"] for face in topology["engineering_boundaries"]]) - self.bottom[self.boundary_leaf]
        self.boundary_conductance = config.boundary_conductance_m_s * np.array([face["width_m"] for face in topology["engineering_boundaries"]])
        self.diagonal = np.arange(self.count)
        self.rows = np.concatenate((self.diagonal, self.first, self.second, self.first, self.second, self.boundary_leaf))
        self.columns = np.concatenate((self.diagonal, self.first, self.second, self.second, self.first, self.boundary_leaf))

    def depth_at(self, volumes):
        return np.array([_stage_at(volumes[index], self.levels[self.offsets[index]:self.offsets[index + 1]],
                                   self.areas[self.offsets[index]:self.offsets[index + 1]]) - self.bottom[index]
                         for index in range(self.count)])

    def evaluate(self, depth):
        excess = depth[self.curve_owner] - self.relative_levels
        volumes = np.bincount(self.curve_owner, weights=self.areas * np.maximum(excess, 0.), minlength=self.count)
        wet_area = np.bincount(self.curve_owner, weights=self.areas * (excess >= 0.), minlength=self.count)
        first_head = depth[self.first] - self.first_sill
        second_head = depth[self.second] - self.second_sill
        flux = self.conductance * (np.maximum(first_head, 0.) - np.maximum(second_head, 0.))
        boundary_head = depth[self.boundary_leaf] - self.boundary_sill
        boundary_flux = self.boundary_conductance * np.maximum(boundary_head, 0.)
        outflow = (np.bincount(self.first, weights=flux, minlength=self.count)
                   - np.bincount(self.second, weights=flux, minlength=self.count)
                   + np.bincount(self.boundary_leaf, weights=boundary_flux, minlength=self.count))
        return volumes, wet_area, flux, boundary_flux, outflow, first_head, second_head, boundary_head

    def advance(self, previous, supplied, previous_depth, dt_s):
        depth = previous_depth.copy()
        for iteration in range(80):
            volume, wet_area, flux, boundary_flux, outflow, first_head, second_head, boundary_head = self.evaluate(depth)
            residual = volume - previous - supplied + dt_s * outflow
            norm = float(np.max(np.abs(residual)))
            merit = float(np.sum(np.abs(residual)))
            if norm <= 2e-9 and abs(float(residual.sum())) <= 2e-8:
                conservative = previous + supplied - dt_s * outflow
                if np.any(conservative < -1e-8):
                    raise ValueError("implicit reservoir negative inventory")
                return np.maximum(conservative, 0.), depth, dt_s * flux, dt_s * boundary_flux, iteration + 1, norm
            first_derivative = dt_s * self.conductance * (first_head >= 0.)
            second_derivative = dt_s * self.conductance * (second_head >= 0.)
            values = np.concatenate((wet_area, first_derivative, second_derivative,
                                     -second_derivative, -first_derivative,
                                     dt_s * self.boundary_conductance * (boundary_head >= 0.)))
            jacobian = coo_matrix((values, (self.rows, self.columns)), shape=(self.count, self.count)).tocsc()
            update = spsolve(jacobian, -residual)
            if not np.isfinite(update).all():
                raise ValueError("implicit reservoir nonfinite Newton update")
            scale = 1.0
            for attempt in range(32):
                candidate = np.maximum(depth + scale * update, 0.)
                candidate_volume, _, _, _, candidate_outflow, *_ = self.evaluate(candidate)
                candidate_residual = candidate_volume - previous - supplied + dt_s * candidate_outflow
                if np.sum(np.abs(candidate_residual)) <= merit * (1. - 1e-4 * scale) + 2e-10:
                    depth = candidate
                    break
                scale *= .5
            else:
                raise ValueError("implicit reservoir line search failed")
        raise ValueError(f"implicit reservoir Newton budget exceeded: max_residual={norm}, total_abs={merit}, last_scale={scale}")


def simulate_stable_overflow(topology, rain_mm_h, *, parameters, substep_s=300.0, initial_volume_m3=None):
    if not isinstance(parameters, OverflowParameters):
        raise ValueError("OverflowParameters required")
    if (type(substep_s) not in (int, float) or not math.isfinite(substep_s) or substep_s <= 0
            or parameters.timestep_s / substep_s != int(parameters.timestep_s / substep_s)):
        raise ValueError("output interval must contain integer positive implicit substeps")
    steps = int(parameters.duration_s / parameters.timestep_s)
    substeps = int(parameters.timestep_s / substep_s)
    if steps * substeps > MAX_STEPS:
        raise ValueError("implicit reservoir step budget exceeded")
    rain = np.asarray(rain_mm_h, np.float64)
    if rain.shape != (steps,) or not np.isfinite(rain).all() or np.any(rain < 0.):
        raise ValueError("invalid implicit reservoir rain vector")
    system = _ReservoirSystem(topology, parameters)
    count = system.count
    volumes = np.zeros(count) if initial_volume_m3 is None else np.asarray(initial_volume_m3, np.float64).copy()
    if volumes.shape != (count,) or not np.isfinite(volumes).all() or np.any(volumes < 0.):
        raise ValueError("invalid implicit initial inventory")
    faces, boundaries = len(system.first), len(system.boundary_leaf)
    shapes = {"rain_mm_h": (steps,), "stage_m": (steps + 1, count), "volume_m3": (steps + 1, count),
              "input_volume_m3": (steps, count), "face_forward_m3": (steps, faces), "face_reverse_m3": (steps, faces),
              "face_volume_m3": (steps, faces), "face_net_m3": (steps, faces),
              "basin_net_internal_m3": (steps, count), "basin_gross_internal_m3": (steps, count),
              "basin_boundary_outflow_m3": (steps, count), "basin_balance_residual_m3": (steps, count),
              "engineering_boundary_outflow_m3": (steps, boundaries), "balance_residual_m3": (steps,),
              "face_forward_active_s": (steps, faces), "face_reverse_active_s": (steps, faces),
              "newton_max_residual_m3": (steps,), "newton_iterations": (steps,)}
    if sum(math.prod(shape) * 8 for shape in shapes.values()) > MAX_ARRAY_BYTES:
        raise ValueError("implicit saved array byte budget exceeded")
    arrays = {name: np.zeros(shape, np.float64) for name, shape in shapes.items()}
    arrays["rain_mm_h"] = rain.copy()
    depth = system.depth_at(volumes)
    arrays["stage_m"][0] = system.bottom + depth
    arrays["volume_m3"][0] = volumes
    for step in range(steps):
        rate = rain[step] * parameters.runoff_coefficient / 3_600_000.0 + parameters.baseflow_mm_per_day / 86_400_000.0
        supplied = topology["arrays"]["leaf_area_m2"] * rate * substep_s
        arrays["input_volume_m3"][step] = supplied * substeps
        for substep in range(substeps):
            try:
                volumes, depth, signed, exported, iterations, residual = system.advance(volumes, supplied, depth, substep_s)
            except ValueError as error:
                raise ValueError(f"implicit interval={step}, substep={substep}: {error}") from error
            arrays["face_forward_m3"][step] += np.maximum(signed, 0.)
            arrays["face_reverse_m3"][step] += np.maximum(-signed, 0.)
            arrays["face_forward_active_s"][step] += (signed > 0.) * substep_s
            arrays["face_reverse_active_s"][step] += (signed < 0.) * substep_s
            arrays["engineering_boundary_outflow_m3"][step] += exported
            arrays["newton_max_residual_m3"][step] = max(arrays["newton_max_residual_m3"][step], residual)
            arrays["newton_iterations"][step] += iterations
        arrays["volume_m3"][step + 1] = volumes
        arrays["stage_m"][step + 1] = system.bottom + depth
    arrays["face_net_m3"] = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    arrays["face_volume_m3"] = arrays["face_forward_m3"] + arrays["face_reverse_m3"]
    for face_index, (first, second) in enumerate(zip(system.first, system.second)):
        arrays["basin_net_internal_m3"][:, first] -= arrays["face_net_m3"][:, face_index]
        arrays["basin_net_internal_m3"][:, second] += arrays["face_net_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, first] += arrays["face_volume_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, second] += arrays["face_volume_m3"][:, face_index]
    for boundary_index, leaf in enumerate(system.boundary_leaf):
        arrays["basin_boundary_outflow_m3"][:, leaf] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    arrays["basin_balance_residual_m3"] = arrays["input_volume_m3"] + arrays["basin_net_internal_m3"] - arrays["basin_boundary_outflow_m3"] - np.diff(arrays["volume_m3"], axis=0)
    arrays["balance_residual_m3"] = arrays["input_volume_m3"].sum(axis=1) - arrays["engineering_boundary_outflow_m3"].sum(axis=1) - np.diff(arrays["volume_m3"].sum(axis=1))
    active = arrays["face_volume_m3"] > 0.
    arrays["spill_onset_step"] = np.where(active.any(axis=0), active.argmax(axis=0), -1).astype(np.int64) if faces else np.empty(0, np.int64)
    arrays["spill_last_active_step"] = np.where(active.any(axis=0), steps - 1 - active[::-1].argmax(axis=0), -1).astype(np.int64) if faces else np.empty(0, np.int64)
    metadata = {"schema": "td-original-bed-overflow-event-v2", "algorithm": ALGORITHM,
                "topology_identity_sha256": topology["identity_sha256"],
                "hierarchy_identity_sha256": topology["metadata"]["hierarchy_identity_sha256"],
                "source_identity_sha256": topology["metadata"]["source_identity_sha256"],
                "parameters": asdict(parameters), "steps": steps, "timestep_s": parameters.timestep_s,
                "duration_s": parameters.duration_s, "implicit_substep_s": substep_s,
                "integration": "backward Euler; coupled semismooth Newton with SciPy sparse linear solve; no explicit donor-emptying limiter",
                "flux_law": "same original law: conductance*(positive first head above sill - positive second head above sill)",
                "rain_semantics": "fixed runoff coefficient plus uniform baseflow, not four-store hydrology",
                "activity_semantics": "end-of-substep flux quadrature support; output-resolution first/last active steps are not exact threshold crossing times",
                "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False, "publishable": False}
    result = {"arrays": {name: readonly(value) for name, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = identity(result["arrays"], metadata)
    validate_stable_overflow(result, topology)
    return result


def validate_stable_overflow(event, topology):
    validate_overflow_event(event, topology)
    arrays, metadata = event["arrays"], event["metadata"]
    if metadata.get("algorithm") != ALGORITHM:
        raise ValueError("stable overflow algorithm mismatch")
    config = OverflowParameters(**metadata["parameters"])
    if (metadata["steps"] * metadata["timestep_s"] != config.duration_s
            or metadata["timestep_s"] != config.timestep_s
            or metadata["implicit_substep_s"] <= 0
            or config.timestep_s / metadata["implicit_substep_s"] != int(config.timestep_s / metadata["implicit_substep_s"])):
        raise ValueError("stable overflow time contract mismatch")
    for name, volume_name in (("face_forward_active_s", "face_forward_m3"), ("face_reverse_active_s", "face_reverse_m3")):
        if (arrays[name].shape != arrays[volume_name].shape or np.any(arrays[name] < 0.)
                or np.any(arrays[name] > config.timestep_s) or not np.array_equal(arrays[name] > 0., arrays[volume_name] > 0.)):
            raise ValueError("stable overflow activity mismatch")
    if np.any(arrays["face_forward_active_s"] + arrays["face_reverse_active_s"] > config.timestep_s):
        raise ValueError("stable overflow bidirectional activity exceeds interval")
    active = arrays["face_volume_m3"] > 0.
    expected_last = np.where(active.any(axis=0), metadata["steps"] - 1 - active[::-1].argmax(axis=0), -1) if active.shape[1] else np.empty(0, np.int64)
    if not np.array_equal(arrays["spill_last_active_step"], expected_last):
        raise ValueError("stable overflow last active index mismatch")
    if np.any(arrays["newton_max_residual_m3"] > 2e-9):
        raise ValueError("stable overflow nonlinear closure failed")
    return True


def save_stable_overflow(event, path, topology):
    save_bundle(path, event, validator=lambda result: validate_stable_overflow(result, topology))


def load_stable_overflow(path, *, expected_sha256, expected_identity, topology):
    event = load_bundle(Path(path), expected_sha256=expected_sha256,
                        validator=lambda result: validate_stable_overflow(result, topology), max_bytes=MAX_ARRAY_BYTES)
    if event["identity_sha256"] != expected_identity:
        raise ValueError("stable overflow external identity mismatch")
    return event
