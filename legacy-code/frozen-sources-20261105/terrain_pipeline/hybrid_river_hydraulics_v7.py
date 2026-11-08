"""Frozen v5 physics with analytic native-section Jacobian and strict endpoint rejection."""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from bisect import bisect_right
import math
import time
from typing import Callable

import numpy as np
from scipy.integrate import BDF

from terrain_pipeline.hybrid_river_hydraulics import (
    Experiment, Model, OLD_FACE_BUDGET_REMAINING, conveyance, signed_flow)

SCHEMA = "td-hybrid-river-hydraulics-v7"
NUMERICAL_VERSION = "three_origin_analytic_native_chain_BDF_precision-v7"
MODEL_VERSION = "explicit_roof_friction_contact_transition-v5"
INTEGRATION = "BDF"
JACOBIAN_HEAD_FRACTION = 0.01
JACOBIAN_MAX_HEAD_STEP_M = 1e-6
DIRECT_VOLUME_RELATIVE_STEP = 1e-6


def jacobian_policy(model, width_m):
    return {"method": "native_piecewise_section_and_signed_Manning_full_chain_analytic",
            "inventory_columns": "all_three_origins_share_dV_dM_equal_one_plus_exact_donor_composition",
            "ledger_feedback_columns": "exact_zero", "jacobian_rhs_evaluations_per_call": 0,
            "jacobian_link_evaluations_per_call": 2 * (len(model.links) + 1),
            "jacobian_flow_evaluations_per_call": len(model.links) + 1,
            "jacobian_link_derivative_evaluations_per_call": len(model.links) + 1,
            "section_breakpoint_branch": "right_height_band",
            "min_capacity_tie_branch": "left_or_cell_at_boundary",
            "zero_signed_flow_donor_branch": "left_or_cell_outlet",
            "fallback_scope": "native_quadratic_section_without_cached_bands_local_geometry_difference_only",
            "fallback_max_head_step_m": 1e-6,
            "fallback_head_step_rule": "min(1e-6,width_m*0.01_if_positive)",
            "fallback_head_step_float_margin": "16_ulp_of_base_head",
            "nonsmooth_scope": "active_branch_derivative_at_storage_slot_donor_min_and_horizontal_perimeter_jumps_not_whole_RHS_C1",
            "scipy_adaptive_difference_factor_used": False}


@dataclass(frozen=True)
class StorageSystem:
    count: int
    initial_state: np.ndarray
    initial_volumes: np.ndarray
    work: dict
    started: float
    physical: Callable
    rhs_for: Callable
    jacobian_for: Callable
    peak_rss: Callable


class NonpositiveWaterTrial(ValueError):
    pass


def section_slopes(cell, head_m, width_m, roof_length, work=None):
    section = cell.section
    details = friction_state(cell, head_m, width_m, roof_length)
    if section.bands:
        ordinal = bisect_right(section.levels_m, head_m) - 1
        band = section.bands[ordinal]
        area_slope = band.width_at_lower_m + band.width_slope * (head_m - band.lower_m)
        perimeter_slope = band.perimeter_slope
        if width_m > 0 and section.kind == "closed_polygon" and section.crown_m <= head_m < section.crown_m + width_m:
            fraction = (head_m - section.crown_m) / width_m
            perimeter_slope += roof_length * 6 * fraction * (1 - fraction) / width_m
        if work is not None:
            work["jacobian_native_section_derivatives"] += 1
    else:
        step = min(1e-6, width_m * 0.01) if width_m > 0 else 1e-6
        raised = friction_state(cell, head_m + step, width_m, roof_length)
        actual_step = (head_m + step) - head_m
        if actual_step <= 0:
            raise ValueError("fallback section derivative head step unrepresentable")
        if actual_step > step + 16 * math.ulp(float(head_m)):
            raise ValueError("fallback section derivative exceeds declared head cap")
        area_slope = (raised["area_m2"] - details["area_m2"]) / actual_step
        perimeter_slope = (raised["effective_friction_perimeter_m"] - details["effective_friction_perimeter_m"]) / actual_step
        if work is not None:
            work["jacobian_section_fallback_evaluations"] += 2
            work["jacobian_max_observed_head_step_m"] = max(work.get("jacobian_max_observed_head_step_m", 0.0), actual_step)
    if not math.isfinite(area_slope) or area_slope <= 0 or not math.isfinite(perimeter_slope):
        raise ValueError("native section derivative invalid; no derivative clamp")
    head_per_volume = 1 / (cell.length_m * area_slope)
    capacity = details["effective_manning_conveyance"]
    capacity_per_head = capacity * ((5 / 3) * area_slope / details["area_m2"]
                                   - (2 / 3) * perimeter_slope / details["effective_friction_perimeter_m"])
    return capacity, head_per_volume, capacity_per_head * head_per_volume


def signed_flow_slopes(capacity, difference_m, length_m, regularization_m):
    squared = difference_m * difference_m + regularization_m * regularization_m
    root_length = math.sqrt(length_m)
    signed_factor = difference_m / (squared**0.25 * root_length)
    head_factor_derivative = (0.5 * difference_m * difference_m + regularization_m * regularization_m) / (squared**1.25 * root_length)
    return signed_factor, capacity * head_factor_derivative


def build_system(model: Model, experiment: Experiment, crown_transition_width_m=0.0, rhs_observer=None):
    validate_transition(crown_transition_width_m)
    model.validate()
    experiment.validate(model)
    count, link_count = len(model.cells), len(model.links)
    initial_volumes = np.array([cell.section.area_perimeter(head)[0] * cell.length_m
                                for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if np.any(initial_volumes <= 0):
        raise ValueError("initial storage must be strictly positive")
    ledger_start = 3 * count
    state = np.zeros(ledger_start + 7 + 4 * link_count)
    state[:count] = initial_volumes
    work = {"rhs_evaluations": 0, "link_evaluations": 0, "old_hll_face_work": 0,
            "jacobian_evaluations": 0, "jacobian_rhs_evaluations": 0,
            "jacobian_link_evaluations": 0, "jacobian_native_section_derivatives": 0,
            "jacobian_flow_evaluations": 0, "jacobian_link_derivative_evaluations": 0,
            "jacobian_section_fallback_evaluations": 0,
            "positivity_rejected_steps": 0, "nonpositive_total_trial_retries": 0,
            "solver_reinitializations": 0, "constructor_nonpositive_retries": 0,
            "accepted_endpoint_inventory_checks": 0, "observation_segment_initializations": 0,
            "bdf_constructor_attempts": 0}
    started = time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    roof_lengths = [roof_contact_length(cell.section) for cell in model.cells]

    def capacity_for(ordinal, head):
        return friction_state(model.cells[ordinal], head, crown_transition_width_m, roof_lengths[ordinal])["effective_manning_conveyance"]

    def physical(inventories):
        if np.shape(inventories) != (3 * count,) or not np.isfinite(inventories).all():
            raise NonpositiveWaterTrial("physical inventory requires finite three-origin state")
        volumes = inventories.reshape(3, count).sum(axis=0)
        if np.any(volumes <= 0):
            raise NonpositiveWaterTrial("trial total water is nonpositive; no floor clamp")
        heads = np.array([cell.section.head_for_area(volume / cell.length_m)
                          for cell, volume in zip(model.cells, volumes)])
        if any(head <= cell.section.floor_m for cell, head in zip(model.cells, heads)):
            raise NonpositiveWaterTrial("trial positive inventory below representable depth; no floor clamp")
        capacities = np.array([capacity_for(ordinal, head) for ordinal, head in enumerate(heads)])
        return volumes, heads, capacities

    def guard():
        nonlocal peak_rss
        if work["rhs_evaluations"] > experiment.max_rhs_evaluations or work["link_evaluations"] > experiment.max_link_evaluations or time.monotonic() - started > experiment.max_wall_seconds:
            raise ValueError("independent 1D work/time bound exceeded")
        peak_rss = max(peak_rss, process.memory_info().rss)
        if peak_rss > 1024**3:
            raise ValueError("1GiB hydraulic RSS limit exceeded")

    def flows(current):
        volumes, heads, capacities = physical(current[:3 * count])
        amounts = []
        for ordinal, link in enumerate(model.links):
            flow = signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1],
                               link.length_m, model.head_regularization_m)
            donor = ordinal if flow >= 0 else ordinal + 1
            flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
            amounts.append((float(flow), donor))
        boundary_capacity = min(capacities[-1], capacity_for(count - 1, experiment.tailwater_head_m))
        outlet = signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m,
                             model.cells[-1].length_m / 2, model.head_regularization_m)
        if outlet >= 0:
            outlet *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        return volumes, heads, amounts, float(outlet)

    def concentration_matrix(amounts, outlet):
        matrix = np.zeros((len(state), 3 * count))
        for ordinal, (flow, donor) in enumerate(amounts):
            for origin in range(3):
                column = origin * count + donor
                matrix[origin * count + ordinal, column] -= flow
                matrix[origin * count + ordinal + 1, column] += flow
                row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                matrix[row, column] += flow
        if outlet >= 0:
            for origin in range(3):
                column = origin * count + count - 1
                matrix[column, column] -= outlet
                row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                matrix[row, column] += outlet
        return matrix

    def rhs_for(source_q):
        def rhs(seconds, current, evaluation_context="BDF_rhs_trial"):
            if rhs_observer is not None:
                rhs_observer(seconds, current, evaluation_context)
            work["rhs_evaluations"] += 1
            work["link_evaluations"] += link_count + 1
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivative = np.zeros_like(current)
            rates = derivative[:3 * count].reshape(3, count)
            for ordinal, (flow, donor) in enumerate(amounts):
                transport = flow * concentrations[:, donor]
                rates[:, ordinal] -= transport
                rates[:, ordinal + 1] += transport
                derivative[ledger_start + 6 + link_count + ordinal] = transport[1]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = transport[2]
                derivative[ledger_start + 6 + 3 * link_count + ordinal] = transport[0]
            derivative[count] += source_q
            derivative[ledger_start] = source_q
            for ordinal, (flow, donor) in enumerate(amounts):
                derivative[ledger_start + 6 + ordinal] = flow
            if outlet >= 0:
                transport = outlet * concentrations[:, -1]
                rates[:, -1] -= transport
                derivative[ledger_start + 1] = outlet
                derivative[ledger_start + 3] = transport[1]
                derivative[ledger_start + 5] = transport[2]
                derivative[ledger_start + 6 + 4 * link_count] = transport[0]
            else:
                derivative[3 * count - 1] -= outlet
                derivative[ledger_start + 2] = -outlet
                derivative[ledger_start + 4] = -outlet
            return derivative
        return rhs

    def jacobian_for(source_q):
        def jacobian(seconds, current):
            if np.shape(current) != (len(state),) or not np.isfinite(current).all():
                raise ValueError("Jacobian requires finite complete three-origin state")
            if rhs_observer is not None:
                rhs_observer(seconds, current, "Jacobian_analytic_state")
            work["jacobian_evaluations"] += 1
            work["jacobian_link_evaluations"] += 2 * (link_count + 1)
            work["jacobian_flow_evaluations"] += link_count + 1
            work["jacobian_link_derivative_evaluations"] += link_count + 1
            work["link_evaluations"] += 2 * (link_count + 1)
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivatives = [section_slopes(cell, heads[ordinal], crown_transition_width_m,
                                          roof_lengths[ordinal], work)
                           for ordinal, cell in enumerate(model.cells)]
            matrix = np.zeros((len(state), len(state)))
            for ordinal, (flow, donor) in enumerate(amounts):
                link = model.links[ordinal]
                left_capacity, left_head_slope, left_capacity_slope = derivatives[ordinal]
                right_capacity, right_head_slope, right_capacity_slope = derivatives[ordinal + 1]
                limiting_left = left_capacity <= right_capacity
                minimum_capacity = min(left_capacity, right_capacity)
                factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[ordinal] - heads[ordinal + 1],
                                                                  link.length_m, model.head_regularization_m)
                donor_factor = volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[donor] + model.donor_regularization_m3)**2
                left_flow_slope = donor_factor * (difference_derivative * left_head_slope
                                                  + factor * left_capacity_slope * limiting_left)
                right_flow_slope = donor_factor * (-difference_derivative * right_head_slope
                                                   + factor * right_capacity_slope * (not limiting_left))
                if donor == ordinal:
                    left_flow_slope += minimum_capacity * factor * donor_derivative
                else:
                    right_flow_slope += minimum_capacity * factor * donor_derivative
                for cell_ordinal, flow_slope in ((ordinal, left_flow_slope), (ordinal + 1, right_flow_slope)):
                    for origin_column in range(3):
                        column = origin_column * count + cell_ordinal
                        matrix[ledger_start + 6 + ordinal, column] += flow_slope
                        for origin in range(3):
                            transport_slope = concentrations[origin, donor] * flow_slope
                            if cell_ordinal == donor:
                                transport_slope += flow * ((origin == origin_column) - concentrations[origin, donor]) / volumes[donor]
                            matrix[origin * count + ordinal, column] -= transport_slope
                            matrix[origin * count + ordinal + 1, column] += transport_slope
                            row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                            matrix[row, column] += transport_slope
            capacity, head_slope, capacity_slope = derivatives[-1]
            tailwater_capacity = capacity_for(count - 1, experiment.tailwater_head_m)
            limiting_cell = capacity <= tailwater_capacity
            minimum_capacity = min(capacity, tailwater_capacity)
            factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[-1] - experiment.tailwater_head_m,
                                                              model.cells[-1].length_m / 2, model.head_regularization_m)
            flow_slope = difference_derivative * head_slope + factor * capacity_slope * limiting_cell
            if outlet >= 0:
                donor_factor = volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[-1] + model.donor_regularization_m3)**2
                flow_slope = flow_slope * donor_factor + minimum_capacity * factor * donor_derivative
            for origin_column in range(3):
                column = origin_column * count + count - 1
                if outlet >= 0:
                    matrix[ledger_start + 1, column] += flow_slope
                    for origin in range(3):
                        transport_slope = concentrations[origin, -1] * flow_slope + outlet * ((origin == origin_column) - concentrations[origin, -1]) / volumes[-1]
                        matrix[origin * count + count - 1, column] -= transport_slope
                        row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                        matrix[row, column] += transport_slope
                else:
                    matrix[3 * count - 1, column] -= flow_slope
                    matrix[ledger_start + 2, column] -= flow_slope
                    matrix[ledger_start + 4, column] -= flow_slope
            if not np.isfinite(matrix).all():
                raise ValueError("analytic three-origin Jacobian nonfinite")
            return matrix
        return jacobian

    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for,
                         lambda: max(peak_rss, process.memory_info().rss))


def inventory_policy():
    return {"origins": ["untraced", "source", "tailwater"], "water_definition": "sum_three_origin_inventories",
            "state_units": "m3", "negative_inventory_action": "reject_entire_BDF_step_and_halve_retry",
            "dense_inventory_check": "no_interpolated_inventory_output_saved_times_are_BDF_endpoints",
            "output_clamp": False, "posthoc_normalization": False, "positivity_tolerance_m3": 0.0,
            "initial_origin": "untraced", "pulse_origin": "source", "reverse_boundary_origin": "tailwater",
            "trial_scope": "finite_signed_origin_Newton_trials_allowed_only_with_positive_total_water",
            "retry_budget": "one_original_event_work_wall_RSS_budget_never_reset"}


def positivity_violation(state, count, seconds):
    inventories = state[:3 * count].reshape(3, count)
    if not np.isfinite(state).all() or np.any(inventories < 0) or np.any(inventories.sum(axis=0) <= 0):
        ordinal = np.unravel_index(np.argmin(inventories), inventories.shape)
        value = float(inventories[ordinal])
        total = float(inventories[:, ordinal[1]].sum())
        return {"time_s": float(seconds), "minimum_origin_inventory_m3": value if math.isfinite(value) else None,
                "origin": ("untraced", "source", "tailwater")[ordinal[0]], "cell_ordinal": int(ordinal[1]),
                "total_water_m3": total if math.isfinite(total) else None, "all_finite": bool(np.isfinite(state).all())}
    return None


def validate_transition(width_m):
    if not math.isfinite(width_m) or not 0 <= width_m <= 0.05:
        raise ValueError("declared roof friction transition must be between 0 and 0.05m")


def roof_contact_length(section):
    if section.kind != "closed_polygon":
        return 0.0
    crown = section.crown_m
    return math.fsum(math.dist(start, end) for start, end in zip(section.polygon, section.polygon[1:] + section.polygon[:1])
                     if start[1] == crown and end[1] == crown)


def friction_state(cell, head_m, width_m, roof_length=None):
    area, actual_perimeter = cell.section.area_perimeter(head_m)
    effective_perimeter = actual_perimeter
    if roof_length is None:
        roof_length = roof_contact_length(cell.section)
    if width_m > 0 and cell.section.kind == "closed_polygon" and head_m >= cell.section.crown_m:
        fraction = (head_m - cell.section.crown_m) / width_m
        contact = 1.0 if fraction >= 1 else fraction * fraction * (3 - 2 * fraction)
        effective_perimeter = actual_perimeter - roof_length + roof_length * contact
    if area > 0 and (actual_perimeter <= 0 or effective_perimeter <= 0):
        raise ValueError("wet section has nonpositive actual/effective friction perimeter")
    actual_capacity = area * (area / actual_perimeter)**(2 / 3) / cell.roughness_manning if area > 0 and actual_perimeter > 0 else 0.0
    capacity = area * (area / effective_perimeter)**(2 / 3) / cell.roughness_manning if area > 0 and effective_perimeter > 0 else 0.0
    return {"area_m2": area, "actual_wetted_perimeter_m": actual_perimeter,
            "effective_friction_perimeter_m": effective_perimeter, "actual_geometry_manning_conveyance": actual_capacity,
            "effective_manning_conveyance": capacity, "actual_horizontal_roof_length_m": roof_length}


def effective_conveyance(cell, head_m, width_m):
    return friction_state(cell, head_m, width_m)["effective_manning_conveyance"]


class HydraulicExecutionFailure(ValueError):
    def __init__(self, message, progress):
        super().__init__(message)
        self.progress = progress


class HydraulicDiagnosticStop(HydraulicExecutionFailure):
    pass


def inventory_snapshot(model, system, state, width_m):
    volumes, heads, capacities = system.physical(state[:3 * system.count])
    cells = []
    for ordinal, (cell, volume, head) in enumerate(zip(model.cells, volumes, heads)):
        section = cell.section
        details = friction_state(cell, float(head), width_m)
        details.update(untraced_water_volume_m3=float(state[ordinal]), cell_id=cell.cell_id, kind=cell.kind, head_m=float(head), volume_m3=float(volume),
                       source_tracer_mass_m3=float(state[system.count + ordinal]),
                       tailwater_tracer_mass_m3=float(state[2 * system.count + ordinal]))
        if cell.kind == "underground":
            details.update(crown_m=section.crown_m, head_minus_crown_m=float(head - section.crown_m),
                           actual_closed_capacity_m3=cell.length_m * section.area_perimeter(section.crown_m)[0],
                           engineered_pressure_slot_volume_m3=cell.length_m * section.pressure_slot_width_m * max(0.0, head - section.crown_m))
        else:
            bank = min(section.pieces[0][1][0], sum(section.pieces[-1][1]))
            details.update(low_bank_m=bank, head_minus_low_bank_m=float(head - bank),
                           engineering_overbank_wall_storage_m3=cell.length_m * (section.area_perimeter(head)[0] - section.area_perimeter(bank)[0]) if head > bank else 0.0)
        cells.append(details)
    return {"cells": cells, "total_water_m3": float(volumes.sum()),
            "boundary_and_paired_ledgers_m3": state[3 * system.count:].tolist()}


def flux_snapshot(model, system, seconds, state, source_q, width_m, tailwater_head_m):
    volumes, heads, capacities = system.physical(state[:3 * system.count])
    concentrations = state[system.count:3 * system.count].reshape(2, system.count) / volumes
    links = []
    for ordinal, link in enumerate(model.links):
        flow = signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
        donor = ordinal if flow >= 0 else ordinal + 1
        flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
        links.append({"link_id": link.link_id, "water_q_m3_s": float(flow),
                      "source_tracer_q_m3_s": float(flow * concentrations[0, donor]),
                      "tailwater_tracer_q_m3_s": float(flow * concentrations[1, donor]), "donor_cell_id": model.cells[donor].cell_id})
    tailwater_capacity = effective_conveyance(model.cells[-1], tailwater_head_m, width_m)
    flow = signed_flow(min(capacities[-1], tailwater_capacity), heads[-1] - tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
    if flow >= 0:
        flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        source_flow, tailwater_flow = flow * concentrations[:, -1]
    else:
        source_flow, tailwater_flow = 0.0, flow
    system.work["link_evaluations"] += len(model.links) + 1
    system.work["diagnostic_flux_link_evaluations"] = system.work.get("diagnostic_flux_link_evaluations", 0) + len(model.links) + 1
    return {"time_s": float(seconds), "source_q_m3_s": source_q, "links": links,
            "outlet_signed_water_q_m3_s": float(flow), "outlet_signed_source_tracer_q_m3_s": float(source_flow),
            "outlet_signed_tailwater_tracer_q_m3_s": float(tailwater_flow)}


def run_experiment(model: Model, experiment: Experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    if diagnostic_stop_s is not None and (not math.isfinite(diagnostic_stop_s) or not 0 < diagnostic_stop_s <= experiment.duration_s):
        raise ValueError("diagnostic stop must be positive and within the unchanged physical event")
    last_evaluation = {"context": "not_started", "time_s": None}
    last_trial_state = None

    def observe_rhs(seconds, current, context):
        nonlocal last_trial_state
        last_evaluation.update(context=context, time_s=float(seconds))
        last_trial_state = current.copy()

    system = build_system(model, experiment, crown_transition_width_m, rhs_observer=observe_rhs)
    count, link_count = system.count, len(model.links)
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes, work, started = system.initial_volumes, system.work, system.started
    physical = system.physical
    accepted_state, accepted_time = state.copy(), 0.0
    accepted_steps, min_step, max_step = 0, None, None
    last_positivity_rejection = None
    saved_mass_extrema = None
    recent_steps = deque(maxlen=16)
    accepted_order_counts = {str(order): 0 for order in range(1, 6)}
    observations = [(0.0, state.copy())]
    integration_segments = []
    rejected_solver_statistics = {"nfev": 0, "njev": 0, "nlu": 0}
    saved_times = np.asarray(experiment.saved_times_s)
    saved_ordinal = 1

    def progress():
        observed_origins = np.array([current[:3 * count].reshape(3, count) for seconds, current in observations])
        observed_index = np.unravel_index(np.argmin(observed_origins), observed_origins.shape)
        observed_extrema = {"minimum_origin_inventory_m3": float(observed_origins[observed_index]),
                            "time_s": float(observations[observed_index[0]][0]),
                            "origin": ("untraced", "source", "tailwater")[observed_index[1]],
                            "cell_id": model.cells[observed_index[2]].cell_id,
                            "per_origin_minimum_m3": observed_origins.min(axis=(0, 2)).tolist()}
        elapsed = time.monotonic() - started
        guard = None
        if work["rhs_evaluations"] > experiment.max_rhs_evaluations:
            guard = "max_rhs_evaluations"
        elif work["link_evaluations"] > experiment.max_link_evaluations:
            guard = "max_link_evaluations"
        elif elapsed > experiment.max_wall_seconds:
            guard = "max_wall_seconds"
        elif system.peak_rss() > 1024**3:
            guard = "max_rss_bytes"
        trial = None
        if last_trial_state is not None:
            trial = {"state_all_finite": bool(np.isfinite(last_trial_state).all()),
                     "state": [float(value) if math.isfinite(value) else None for value in last_trial_state],
                     "is_accepted_state": False, "state_layout": "untracedMass/sourceMass/tailwaterMass/oldSixBoundary/threePaired/untracedPaired/untracedOutlet"}
        try:
            accepted_inventory = inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
        except Exception as snapshot_error:
            accepted_inventory = {"snapshot_error": str(snapshot_error), "state": [float(value) if math.isfinite(value) else None for value in accepted_state]}
        return {"last_accepted_physical_time_s": accepted_time, "configured_physical_duration_s": experiment.duration_s,
                "diagnostic_stop_s": diagnostic_stop_s, "physical_event_complete": accepted_time == experiment.duration_s,
                "work": dict(work), "last_positivity_rejection": last_positivity_rejection,
                "saved_mass_extrema": saved_mass_extrema if saved_mass_extrema is not None else observed_extrema,
                "elapsed_wall_seconds": elapsed, "triggered_guard": guard,
                "discarded_solver_statistics": dict(rejected_solver_statistics),
                "max_rhs_evaluations": experiment.max_rhs_evaluations, "max_link_evaluations": experiment.max_link_evaluations,
                "max_wall_seconds": experiment.max_wall_seconds, "accepted_steps": accepted_steps,
                "min_accepted_step_s": min_step, "max_accepted_step_s": max_step, "recent_accepted_steps": list(recent_steps),
                "accepted_BDF_order_after_step_counts": dict(accepted_order_counts),
                "last_evaluation": dict(last_evaluation), "last_trial": trial,
                "last_accepted_inventory": accepted_inventory,
                "actual_peak_rss_bytes": system.peak_rss(), "model_version": MODEL_VERSION, "integration": INTEGRATION,
                "crown_friction_transition_width_m": crown_transition_width_m,
                "inventory_scope": "actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume"}

    breaks = [0.0, experiment.duration_s, *experiment.saved_times_s]
    if experiment.scenario == "pulse":
        breaks.append(experiment.pulse_duration_s)
    breaks = sorted(set(breaks))
    try:
        for lower, full_upper in zip(breaks[:-1], breaks[1:]):
            upper = min(full_upper, diagnostic_stop_s) if diagnostic_stop_s is not None else full_upper
            if upper <= lower:
                break
            source_q = experiment.pulse_q_m3_s if experiment.scenario == "pulse" and lower < experiment.pulse_duration_s else 0.0
            raw_rhs, raw_jacobian = system.rhs_for(source_q), system.jacobian_for(source_q)

            def tracked_rhs(seconds, current):
                return raw_rhs(seconds, current)

            def tracked_jacobian(seconds, current):
                return raw_jacobian(seconds, current)

            def construct_solver(seconds, current, maximum_step, first_step=None):
                nonlocal last_positivity_rejection
                while True:
                    try:
                        work["bdf_constructor_attempts"] += 1
                        return BDF(tracked_rhs, seconds, current, upper, max_step=maximum_step,
                                     first_step=first_step, rtol=experiment.relative_tolerance,
                                     atol=experiment.absolute_tolerance, jac=tracked_jacobian)
                    except NonpositiveWaterTrial as error:
                        work["constructor_nonpositive_retries"] += 1
                        work["nonpositive_total_trial_retries"] += 1
                        last_positivity_rejection = {"time_s": seconds, "trial_error": str(error),
                                                     "context": "BDF_constructor", "accepted_state_unchanged": True}
                        bound = min(maximum_step, upper - seconds)
                        if first_step is not None:
                            bound = min(bound, first_step)
                        first_step = bound / 2
                        maximum_step = min(maximum_step, first_step)
                        if first_step <= 16 * math.ulp(seconds) or first_step <= 0:
                            raise ValueError("constructor positivity retry step unrepresentable; no clamp")
                        work["solver_reinitializations"] += 1

            work["observation_segment_initializations"] += 1
            solver = construct_solver(lower, state, experiment.max_step_s)
            segment_steps = []
            while solver.status == "running":
                previous_state = accepted_state.copy()
                attempted_step = min(solver.h_abs, upper - accepted_time)
                trial_error = None
                try:
                    message = solver.step()
                except NonpositiveWaterTrial as error:
                    trial_error = str(error)
                if trial_error is None and solver.status != "failed":
                    work["accepted_endpoint_inventory_checks"] += 1
                    violation = positivity_violation(solver.y, count, solver.t)
                    actual_candidate_step = solver.t - accepted_time
                else:
                    violation = {"time_s": accepted_time, "trial_error": trial_error} if trial_error else None
                    actual_candidate_step = attempted_step
                if violation is not None:
                    last_positivity_rejection = violation
                    if "cell_ordinal" in violation:
                        last_positivity_rejection["cell_id"] = model.cells[violation["cell_ordinal"]].cell_id
                    work["positivity_rejected_steps"] += 1
                    if trial_error:
                        work["nonpositive_total_trial_retries"] += 1
                    retry_step = min(attempted_step, actual_candidate_step) / 2
                    if retry_step <= 16 * math.ulp(accepted_time) or retry_step <= 0:
                        raise ValueError("strict positivity retry step unrepresentable; no clamp")
                    work["solver_reinitializations"] += 1
                    for name in rejected_solver_statistics:
                        rejected_solver_statistics[name] += getattr(solver, name)
                    solver = construct_solver(accepted_time, previous_state,
                                              min(experiment.max_step_s, retry_step), first_step=retry_step)
                    continue
                if solver.status == "failed":
                    raise ValueError("BDF failed: " + str(message))
                previous_time = accepted_time
                accepted_time = float(solver.t)
                accepted_state = solver.y.copy()
                solver.max_step = experiment.max_step_s
                step = accepted_time - previous_time
                accepted_steps += 1
                accepted_order_counts[str(solver.order)] += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                recent_steps.append({"start_s": previous_time, "end_s": accepted_time, "step_s": step,
                                     "solver_order_after_step": int(solver.order)})
                segment_steps.append(step)
                while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                    seconds = float(saved_times[saved_ordinal])
                    if seconds != accepted_time:
                        raise ValueError("saved physical observation must coincide with accepted BDF endpoint")
                    saved_state = accepted_state.copy()
                    violation = positivity_violation(saved_state, count, seconds)
                    if violation:
                        raise ValueError("saved inventory positivity violation: " + str(violation))
                    observations.append((seconds, saved_state))
                    saved_ordinal += 1
            state = accepted_state.copy()
            integration_segments.append({"start_s": lower, "end_s": upper, "accepted_steps": len(segment_steps),
                                         "min_adaptive_step_s": min(segment_steps), "max_adaptive_step_s": max(segment_steps),
                                         "final_solver_nfev": solver.nfev, "final_solver_njev": solver.njev, "final_solver_nlu": solver.nlu,
                                         "discarded_solver_statistics_cumulative": dict(rejected_solver_statistics)})
            if diagnostic_stop_s is not None and accepted_time >= diagnostic_stop_s:
                raise HydraulicDiagnosticStop("declared short diagnostic stop; not a completed hydraulic case", progress())
    except HydraulicDiagnosticStop:
        raise
    except Exception as error:
        raise HydraulicExecutionFailure(str(error), progress()) from error
    if accepted_time != experiment.duration_s or saved_ordinal != len(saved_times):
        raise HydraulicExecutionFailure("physical event/observations incomplete", progress())
    try:
        saved_section_diagnostics = [{"time_s": seconds, **inventory_snapshot(model, system, current, crown_transition_width_m)} for seconds, current in observations]
        flux_probes = []
        for seconds, current in observations:
            source_q = experiment.pulse_q_m3_s if experiment.scenario == "pulse" and seconds < experiment.pulse_duration_s else 0.0
            flux_probes.append(flux_snapshot(model, system, seconds, current, source_q, crown_transition_width_m, experiment.tailwater_head_m))
        if work["link_evaluations"] > experiment.max_link_evaluations:
            raise ValueError("independent 1D diagnostic flux work bound exceeded")
        rows = np.array([current for seconds, current in observations])
        all_origins = rows[:, :3 * count].reshape(-1, 3, count)
        volumes = all_origins.sum(axis=1)
        masses = rows[:, count:3 * count].reshape(-1, 2, count)
        minimum_index = np.unravel_index(np.argmin(all_origins), all_origins.shape)
        saved_mass_extrema = {"minimum_origin_inventory_m3": float(all_origins[minimum_index]),
                             "time_s": float(saved_times[minimum_index[0]]),
                             "origin": ("untraced", "source", "tailwater")[minimum_index[1]],
                             "cell_id": model.cells[minimum_index[2]].cell_id,
                             "per_origin_minimum_m3": all_origins.min(axis=(0, 2)).tolist(),
                             "max_water_minus_origin_sum_m3": float(np.max(abs(volumes - all_origins.sum(axis=1))))}
        if not np.isfinite(rows).all() or np.any(all_origins < 0) or np.any(volumes <= 0):
            raise ValueError("strict saved tracer positivity/composition failed; no output clamp")
        ledgers = rows[:, ledger_start:ledger_start + 6]
        residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
        residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
        residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
        untraced_out = rows[:, ledger_start + 6 + 4 * link_count]
        residual_untraced = all_origins[:, 0].sum(axis=1) - initial_volumes.sum() + untraced_out
        threshold = max(1e-7, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
        if max(np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater, residual_untraced)) > threshold:
            raise ValueError("water/tracer conservation gate failed")
        heads = np.array([physical(row[:3 * count])[1] for row in rows])
        stages, pressure = [], []
        for head_row in heads:
            stages.append([float(head) if cell.kind == "surface" or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            pressure.append([float(head) if cell.kind == "underground" and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
        sink_link_index = next(ordinal for ordinal, link in enumerate(model.links) if link.kind == "sink_exchange")
        reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
        if time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024**3:
            raise ValueError("final independent 1D wall/RSS bound exceeded")
        return {"schema": SCHEMA, "numerical_version": NUMERICAL_VERSION, "integration": INTEGRATION,
                "model_version": MODEL_VERSION,
                "friction_policy": {"width_m": crown_transition_width_m, "transition_start": "crown",
                                    "transition_end": "crown+width_m", "actual_perimeter_unchanged": True,
                                    "storage_area_unchanged": True, "pressure_slot_width_unchanged": True,
                                    "roof_length_source": "sum_actual_polygon_edges_with_both_endpoints_at_crown",
                                    "constitutive_kind": "C1_effective_roof_contact_friction" if crown_transition_width_m > 0 else "legacy_actual_perimeter",
                                    "contact_polynomial": "u*u*(3-2*u)_for_0<=u<=1"},
                "saved_section_diagnostics": saved_section_diagnostics, "instantaneous_flux_probes": flux_probes,
                "execution_progress": progress(),
                "jacobian_policy": {**jacobian_policy(model, crown_transition_width_m),
                                    "observed_max_head_step_m": work.get("jacobian_max_observed_head_step_m", 0.0),
                                    }, "status": "diagnostic_completed", "model": "finite_1d_diffusive_storage_signed_manning_BDF",
                "pressure_model": "explicit_engineered_Preissmann_slot_compliance_not_waterhammer",
                "scenario": experiment.scenario, "cell_ids": [cell.cell_id for cell in model.cells],
                "link_ids": [link.link_id for link in model.links], "times_s": [seconds for seconds, current in observations],
                "water_volume_m3": volumes.tolist(), "untraced_water_volume_m3": all_origins[:, 0].tolist(),
                "inventory_policy": inventory_policy(), "source_tracer_mass_m3": masses[:, 0].tolist(),
                "tailwater_tracer_mass_m3": masses[:, 1].tolist(), "open_channel_stage_m": stages,
                "pressurized_head_m": pressure, "hydraulic_head_m": heads.tolist(),
                "initial_untraced_water_m3": initial_volumes.tolist(),
                "ledger_columns": ["source_in_m3", "outlet_water_out_m3", "tailwater_water_in_m3", "source_tracer_out_m3", "tailwater_tracer_in_m3", "tailwater_tracer_out_m3"],
                "boundary_ledger_m3": ledgers.tolist(), "paired_link_water_integral_m3": rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(),
                "paired_link_source_integral_m3": rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(),
                "paired_link_tailwater_integral_m3": rows[:, ledger_start + 6 + 2 * link_count:ledger_start + 6 + 3 * link_count].tolist(),
                "paired_link_untraced_integral_m3": rows[:, ledger_start + 6 + 3 * link_count:ledger_start + 6 + 4 * link_count].tolist(),
                "outlet_untraced_out_m3": untraced_out.tolist(),
                "max_untraced_residual_m3": float(np.max(abs(residual_untraced))),
                "saved_mass_extrema": saved_mass_extrema,
                "dense_positivity_witness": {"policy": "no_dense_inventory_output_saved_times_are_BDF_endpoints",
                                           "interpolated_inventory_samples": 0,
                                           "continuous_between_steps_positivity_certified": False,
                                           "candidate_endpoint_checks": work["accepted_endpoint_inventory_checks"],
                                           "accepted_steps": accepted_steps, "last_rejected": last_positivity_rejection,
                                           "negative_inventory_tolerance_m3": 0.0},
                "max_water_residual_m3": float(np.max(abs(residual_water))), "max_source_residual_m3": float(np.max(abs(residual_source))),
                "max_tailwater_residual_m3": float(np.max(abs(residual_tailwater))), "conservation_gate_m3": threshold,
                "source_arrival_threshold_m3": experiment.source_arrival_threshold_m3, "source_arrival_time_s": arrival[0] if arrival else None,
                "arrival_semantics": "threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed",
                "source_reached_spring": bool(arrival), "source_reached_engineered_outlet": bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3),
                "reverse_reached_sink": bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3),
                "boundary_condition_kind": "engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet",
                "boundary_scope": "positively_wet_prescribed_tailwater_only_no_dry_free_outfall",
                "integration_segments": integration_segments,
                "model_parameters": {"head_regularization_m": model.head_regularization_m, "donor_regularization_m3": model.donor_regularization_m3},
                "no_duplicate_cumulative_Q": True, "natural_outlet_certified": False, "full_network_verified": False,
                "finite_speed_front_verified": False, "three_dimensional_flow_solved": False,
                "work": {**work, "old_hll_face_budget_remaining_unchanged": OLD_FACE_BUDGET_REMAINING,
                         "actual_peak_rss_bytes": system.peak_rss(), "max_rss_bytes": 1024**3,
                         "wall_seconds": time.monotonic() - started}}
    except Exception as error:
        raise HydraulicExecutionFailure(str(error), progress()) from error
