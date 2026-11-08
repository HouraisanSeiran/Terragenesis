"""Adaptive stiff integration of reservoir inventories and actual directional flux quadrature."""

from dataclasses import asdict
import math
from pathlib import Path

import numpy as np
from numba import njit
from scipy.integrate import Radau
from scipy.sparse import coo_matrix

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.td_basin_overflow import MAX_STEPS, OverflowParameters, validate_overflow_event
from terrain_pipeline.td_basin_overflow_implicit import MAX_ARRAY_BYTES, _ReservoirSystem


ALGORITHM = "radau-conservative-original-bed-basin-face-exchange-v5"
RADAU_WEIGHTS = np.array([(16. - math.sqrt(6.)) / 36., (16. + math.sqrt(6.)) / 36., 1. / 9.])


@njit(cache=True)
def _invert_curves(volumes, offsets, relative_levels, capacities, cumulative_area):
    depth = np.empty(len(volumes), np.float64)
    area = np.empty(len(volumes), np.float64)
    for leaf in range(len(volumes)):
        start, end = offsets[leaf], offsets[leaf + 1]
        lower, upper = start, end
        while lower < upper:
            middle = (lower + upper) // 2
            if capacities[middle] <= volumes[leaf]:
                lower = middle + 1
            else:
                upper = middle
        interval = max(start, lower - 1)
        depth[leaf] = relative_levels[interval] + (volumes[leaf] - capacities[interval]) / cumulative_area[interval]
        area[leaf] = cumulative_area[interval]
    return depth, area


class _IntegratedExchange:
    def __init__(self, topology, config):
        self.system = _ReservoirSystem(topology, config)
        system = self.system
        self.count, self.faces, self.boundaries = system.count, len(system.first), len(system.boundary_leaf)
        self.size = self.count + 2 * self.faces + self.boundaries
        self.capacities = np.zeros_like(system.areas)
        self.cumulative_area = np.zeros_like(system.areas)
        for start, end in zip(system.offsets[:-1], system.offsets[1:]):
            self.cumulative_area[start:end] = np.cumsum(system.areas[start:end])
            self.capacities[start:end] = (system.relative_levels[start:end] * self.cumulative_area[start:end]
                                          - np.cumsum(system.relative_levels[start:end] * system.areas[start:end]))
        self.supply_rate = np.zeros(self.count)

    def fields(self, values):
        system = self.system
        depth, area = _invert_curves(values[:self.count], system.offsets, system.relative_levels,
                                     self.capacities, self.cumulative_area)
        first_head = depth[system.first] - system.first_sill
        second_head = depth[system.second] - system.second_sill
        boundary_head = depth[system.boundary_leaf] - system.boundary_sill
        signed = system.conductance * (np.maximum(first_head, 0.) - np.maximum(second_head, 0.))
        boundary = system.boundary_conductance * np.maximum(boundary_head, 0.)
        return depth, area, first_head, second_head, boundary_head, signed, boundary

    def rhs(self, time_s, values):
        system = self.system
        _, _, _, _, _, signed, boundary = self.fields(values)
        inventory_rate = (self.supply_rate - np.bincount(system.first, weights=signed, minlength=self.count)
                          + np.bincount(system.second, weights=signed, minlength=self.count)
                          - np.bincount(system.boundary_leaf, weights=boundary, minlength=self.count))
        return np.concatenate((inventory_rate, np.maximum(signed, 0.), np.maximum(-signed, 0.), boundary))

    def jacobian(self, time_s, values):
        system = self.system
        _, area, first_head, second_head, boundary_head, signed, _ = self.fields(values)
        first = system.conductance * (first_head > 0.) / area[system.first]
        second = system.conductance * (second_head > 0.) / area[system.second]
        boundary = system.boundary_conductance * (boundary_head > 0.) / area[system.boundary_leaf]
        forward_rows = self.count + np.arange(self.faces)
        reverse_rows = self.count + self.faces + np.arange(self.faces)
        boundary_rows = self.count + 2 * self.faces + np.arange(self.boundaries)
        rows = np.concatenate((system.first, system.first, system.second, system.second, system.boundary_leaf,
                               forward_rows, forward_rows, reverse_rows, reverse_rows, boundary_rows))
        columns = np.concatenate((system.first, system.second, system.first, system.second, system.boundary_leaf,
                                  system.first, system.second, system.first, system.second, system.boundary_leaf))
        derivatives = np.concatenate((-first, second, first, -second, -boundary,
                                       first * (signed > 0.), -second * (signed > 0.),
                                       -first * (signed < 0.), second * (signed < 0.), boundary))
        return coo_matrix((derivatives, (rows, columns)), shape=(self.size, self.size)).tocsc()

    def conservative_step(self, solver, previous, dt_s, atol, rtol):
        increments = np.zeros(2 * self.faces + self.boundaries)
        for weight, stage in zip(RADAU_WEIGHTS, solver.Z):
            *_, signed, boundary = self.fields(previous + stage)
            increments += dt_s * weight * np.concatenate((np.maximum(signed, 0.), np.maximum(-signed, 0.), boundary))
        signed_volume = increments[:self.faces] - increments[self.faces:2 * self.faces]
        system = self.system
        inventory = (previous[:self.count] + dt_s * self.supply_rate
                     - np.bincount(system.first, weights=signed_volume, minlength=self.count)
                     + np.bincount(system.second, weights=signed_volume, minlength=self.count)
                     - np.bincount(system.boundary_leaf, weights=increments[2 * self.faces:], minlength=self.count))
        updated = np.concatenate((inventory, previous[self.count:] + increments))
        defect = np.abs(updated - solver.y)
        scale = atol + rtol * np.maximum(np.abs(previous), np.abs(updated))
        normalized_defect = float(np.max(defect / scale))
        if not np.isfinite(updated).all() or np.any(inventory < 0.) or normalized_defect > .05:
            raise ValueError(f"Radau collocation balance defect or negative inventory: scaled_defect={normalized_defect}")
        solver.y = updated
        solver.f = self.rhs(solver.t, updated)
        return normalized_defect, float(defect[:self.count].max())


def simulate_radau_overflow(topology, rain_mm_h, *, parameters, max_step_s=300.,
                            rtol=1e-7, atol_stage_m=1e-7, flux_atol_m3=1e-6, initial_volume_m3=None):
    if not isinstance(parameters, OverflowParameters):
        raise ValueError("OverflowParameters required")
    if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0.
           for value in (max_step_s, rtol, atol_stage_m, flux_atol_m3)):
        raise ValueError("positive finite Radau step and tolerances required")
    steps = int(parameters.duration_s / parameters.timestep_s)
    rain = np.asarray(rain_mm_h, np.float64)
    if steps > MAX_STEPS or rain.shape != (steps,) or not np.isfinite(rain).all() or np.any(rain < 0.):
        raise ValueError("invalid Radau rain/output budget")
    exchange = _IntegratedExchange(topology, parameters)
    count, faces, boundaries = exchange.count, exchange.faces, exchange.boundaries
    initial = np.zeros(count) if initial_volume_m3 is None else np.asarray(initial_volume_m3, np.float64).copy()
    if initial.shape != (count,) or not np.isfinite(initial).all() or np.any(initial < 0.):
        raise ValueError("invalid Radau initial inventory")
    shapes = {"rain_mm_h": (steps,), "stage_m": (steps + 1, count), "volume_m3": (steps + 1, count),
              "input_volume_m3": (steps, count), "face_forward_m3": (steps, faces), "face_reverse_m3": (steps, faces),
              "face_volume_m3": (steps, faces), "face_net_m3": (steps, faces),
              "basin_net_internal_m3": (steps, count), "basin_gross_internal_m3": (steps, count),
              "basin_boundary_outflow_m3": (steps, count), "basin_balance_residual_m3": (steps, count),
              "engineering_boundary_outflow_m3": (steps, boundaries), "balance_residual_m3": (steps,)}
    if sum(math.prod(shape) * 8 for shape in shapes.values()) > MAX_ARRAY_BYTES:
        raise ValueError("Radau saved array byte budget exceeded")
    arrays = {name: np.zeros(shape) for name, shape in shapes.items()}
    arrays["rain_mm_h"] = rain.copy()
    arrays["volume_m3"][0] = initial
    values = np.concatenate((initial, np.zeros(2 * faces + boundaries)))
    depth, *_ = exchange.fields(values)
    arrays["stage_m"][0] = exchange.system.bottom + depth
    minimum_area = exchange.system.areas[exchange.system.offsets[:-1]]
    atol = np.concatenate((minimum_area * atol_stage_m, np.full(2 * faces + boundaries, flux_atol_m3)))
    accepted_steps = 0
    total_rhs, total_jacobian, total_lu = 0, 0, 0
    minimum_inventory = 0.
    maximum_scaled_defect = 0.
    maximum_inventory_correction = 0.
    solver = None
    previous_rain = None
    for step in range(steps):
        rate = rain[step] * parameters.runoff_coefficient / 3_600_000.0 + parameters.baseflow_mm_per_day / 86_400_000.0
        exchange.supply_rate = topology["arrays"]["leaf_area_m2"] * rate
        arrays["input_volume_m3"][step] = exchange.supply_rate * parameters.timestep_s
        start, end = step * parameters.timestep_s, (step + 1) * parameters.timestep_s
        before = values.copy()
        if solver is None or rain[step] != previous_rain:
            solver = Radau(exchange.rhs, start, values, parameters.duration_s, jac=exchange.jacobian,
                           max_step=min(max_step_s, parameters.timestep_s), rtol=rtol, atol=atol)
            solver.newton_tol = min(solver.newton_tol, 1e-8)
        before_rhs, before_jacobian, before_lu = solver.nfev, solver.njev, solver.nlu
        while solver.t < end:
            solver.max_step = min(max_step_s, end - solver.t)
            previous_step = solver.y.copy()
            previous_time = solver.t
            solver.step()
            accepted_steps += 1
            if solver.status == "failed" or accepted_steps > MAX_STEPS:
                raise ValueError("Radau integration failed or exceeded step budget")
            scaled_defect, correction = exchange.conservative_step(solver, previous_step, solver.t - previous_time, atol, rtol)
            maximum_scaled_defect = max(maximum_scaled_defect, scaled_defect)
            maximum_inventory_correction = max(maximum_inventory_correction, correction)
            minimum_inventory = min(minimum_inventory, float(solver.y[:count].min()))
            if minimum_inventory < -1e-8:
                raise ValueError("Radau integration produced negative basin inventory")
        values = solver.y.copy()
        previous_rain = rain[step]
        total_rhs += solver.nfev - before_rhs
        total_jacobian += solver.njev - before_jacobian
        total_lu += solver.nlu - before_lu
        arrays["volume_m3"][step + 1] = values[:count]
        depth, *_ = exchange.fields(values)
        arrays["stage_m"][step + 1] = exchange.system.bottom + depth
        arrays["face_forward_m3"][step] = values[count:count + faces] - before[count:count + faces]
        arrays["face_reverse_m3"][step] = values[count + faces:count + 2 * faces] - before[count + faces:count + 2 * faces]
        arrays["engineering_boundary_outflow_m3"][step] = values[count + 2 * faces:] - before[count + 2 * faces:]
        for name in ("face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3"):
            if arrays[name][step].size and arrays[name][step].min() < -1e-8:
                raise ValueError(f"negative directional quadrature in interval={step}, field={name}, min={arrays[name][step].min()}")
    arrays["face_net_m3"] = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    arrays["face_volume_m3"] = arrays["face_forward_m3"] + arrays["face_reverse_m3"]
    for face_index, (first, second) in enumerate(zip(exchange.system.first, exchange.system.second)):
        arrays["basin_net_internal_m3"][:, first] -= arrays["face_net_m3"][:, face_index]
        arrays["basin_net_internal_m3"][:, second] += arrays["face_net_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, first] += arrays["face_volume_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, second] += arrays["face_volume_m3"][:, face_index]
    for boundary_index, leaf in enumerate(exchange.system.boundary_leaf):
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
                "duration_s": parameters.duration_s, "max_step_s": max_step_s, "rtol": rtol, "atol_stage_m": atol_stage_m,
                "flux_atol_m3": flux_atol_m3,
                "integration": "SciPy adaptive Radau IIA; positive collocation weights integrate actual stage fluxes; the same face volumes update both inventories and directional quadrature",
                "activity_semantics": "first/last active saved interval from actual quadrature; exact threshold crossing time is unresolved inside 300s",
                "rain_semantics": "fixed runoff coefficient plus baseflow, not four-store hydrology",
                "work": {"accepted_steps": accepted_steps, "rhs_evaluations": total_rhs,
                         "jacobian_evaluations": total_jacobian, "lu_factorizations": total_lu,
                         "minimum_inventory_m3": minimum_inventory,
                         "maximum_scaled_collocation_defect": maximum_scaled_defect,
                         "maximum_inventory_correction_m3": maximum_inventory_correction},
                "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False, "publishable": False}
    result = {"arrays": {name: readonly(value) for name, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = identity(result["arrays"], metadata)
    validate_radau_overflow(result, topology)
    return result


def validate_radau_overflow(event, topology):
    validate_overflow_event(event, topology)
    if event["metadata"].get("algorithm") != ALGORITHM:
        raise ValueError("Radau event algorithm mismatch")
    if event["metadata"]["work"]["minimum_inventory_m3"] < -1e-8:
        raise ValueError("Radau event negative internal inventory")
    return True


def save_radau_overflow(event, path, topology):
    save_bundle(path, event, validator=lambda result: validate_radau_overflow(result, topology))


def load_radau_overflow(path, *, expected_sha256, expected_identity, topology):
    event = load_bundle(Path(path), expected_sha256=expected_sha256,
                        validator=lambda result: validate_radau_overflow(result, topology), max_bytes=MAX_ARRAY_BYTES)
    if event["identity_sha256"] != expected_identity:
        raise ValueError("Radau event external identity mismatch")
    return event
