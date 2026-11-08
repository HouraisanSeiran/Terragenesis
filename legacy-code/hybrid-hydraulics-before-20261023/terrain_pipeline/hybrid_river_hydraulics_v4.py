"""Versioned Radau kernel: fixed log-volume differences and analytic tracer Jacobian."""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import math
import time
from typing import Callable

import numpy as np
from scipy.integrate import Radau

from terrain_pipeline.hybrid_river_hydraulics import (
    Experiment, Model, OLD_FACE_BUDGET_REMAINING, conveyance, signed_flow)

SCHEMA = "td-hybrid-river-hydraulics-v4"
NUMERICAL_VERSION = "head_bounded_log_difference_Radau_step_diagnostics-v4"
MODEL_VERSION = "explicit_roof_friction_contact_transition-v4"
JACOBIAN_HEAD_FRACTION = 0.01
JACOBIAN_MAX_HEAD_STEP_M = 1e-6
LOG_VOLUME_DIFFERENCE_STEP = 1e-6


def jacobian_policy(model, width_m):
    cap = min(JACOBIAN_MAX_HEAD_STEP_M, model.head_regularization_m * JACOBIAN_HEAD_FRACTION)
    if width_m > 0:
        cap = min(cap, width_m * JACOBIAN_HEAD_FRACTION)
    return {"log_volume_nominal_absolute_step": LOG_VOLUME_DIFFERENCE_STEP,
            "max_head_step_m": cap, "nominal_head_ceiling_m": JACOBIAN_MAX_HEAD_STEP_M,
            "head_cap_rule": "min(nominal_head_ceiling_m,head_regularization_m*0.01,width_m*0.01_if_positive)",
            "head_step_target_fraction_of_cap": 0.5,
            "head_step_fraction_of_friction_transition": JACOBIAN_HEAD_FRACTION,
            "head_step_float_margin": "16_ulp_of_base_head",
            "step_units": "dimensionless_log_volume_forward_difference_bounded_by_physical_head",
            "tracer_columns": "analytic_donor_transport", "ledger_feedback_columns": "exact_zero",
            "nonsmooth_scope": "fixed_forward_secant_at_exact_storage_slot_derivative_and_donor_min_ledges;C1_roof_contact_only_not_whole_RHS",
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


def build_system(model: Model, experiment: Experiment, crown_transition_width_m=0.0, rhs_observer=None):
    validate_transition(crown_transition_width_m)
    model.validate()
    experiment.validate(model)
    count = len(model.cells)
    initial_volumes = np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if np.any(initial_volumes <= 0):
        raise ValueError("initial storage must be strictly positive")
    link_count = len(model.links)
    ledger_start = 3 * count
    state = np.zeros(ledger_start + 6 + 3 * link_count)
    state[:count] = np.log(initial_volumes)
    work = {"rhs_evaluations": 0, "link_evaluations": 0, "old_hll_face_work": 0,
            "jacobian_evaluations": 0, "jacobian_rhs_evaluations": 0}
    started = time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    roof_lengths = {cell.cell_id: roof_contact_length(cell.section) for cell in model.cells}

    def capacity_for(cell, head):
        return friction_state(cell, head, crown_transition_width_m, roof_lengths[cell.cell_id])["effective_manning_conveyance"]

    def physical(log_volumes):
        if not np.isfinite(log_volumes).all() or np.any(abs(log_volumes) > 600):
            raise ValueError("storage transform exceeds physical range")
        volumes = np.exp(log_volumes)
        heads = np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any(head <= cell.section.floor_m for cell, head in zip(model.cells, heads)):
            raise ValueError("positive storage is below representable section depth; no floor clamp")
        capacities = np.array([capacity_for(cell, head) for cell, head in zip(model.cells, heads)])
        return volumes, heads, capacities

    def rhs_for(source_q):
        def rhs(seconds, current, evaluation_context="Radau_rhs_trial"):
            nonlocal peak_rss
            if rhs_observer is not None:
                rhs_observer(seconds, current, evaluation_context)
            work["rhs_evaluations"] += 1
            work["link_evaluations"] += link_count + 1
            if work["rhs_evaluations"] > experiment.max_rhs_evaluations or work["link_evaluations"] > experiment.max_link_evaluations or time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError("independent 1D work/time bound exceeded")
            if work["rhs_evaluations"] % 32 == 1:
                peak_rss = max(peak_rss, process.memory_info().rss)
                if peak_rss > 1024**3:
                    raise ValueError("1GiB hydraulic RSS limit exceeded")
            volumes, heads, capacities = physical(current[:count])
            concentrations = current[count:3 * count].reshape(2, count) / volumes
            volume_rates = np.zeros(count)
            tracer_rates = np.zeros((2, count))
            derivative = np.zeros_like(current)
            for ordinal, link in enumerate(model.links):
                flow = signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor = ordinal if flow >= 0 else ordinal + 1
                flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                tracer_flow = flow * concentrations[:, donor]
                volume_rates[ordinal] -= flow
                volume_rates[ordinal + 1] += flow
                tracer_rates[:, ordinal] -= tracer_flow
                tracer_rates[:, ordinal + 1] += tracer_flow
                derivative[ledger_start + 6 + ordinal] = flow
                derivative[ledger_start + 6 + link_count + ordinal] = tracer_flow[0]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = tracer_flow[1]
            boundary_capacity = min(capacities[-1], capacity_for(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                boundary_tracer = outlet_flow * concentrations[:, -1]
                derivative[ledger_start + 1] = outlet_flow
                derivative[ledger_start + 3] = boundary_tracer[0]
                derivative[ledger_start + 5] = boundary_tracer[1]
            else:
                boundary_tracer = np.array([0.0, outlet_flow])
                derivative[ledger_start + 2] = -outlet_flow
                derivative[ledger_start + 4] = -outlet_flow
            volume_rates[-1] -= outlet_flow
            tracer_rates[:, -1] -= boundary_tracer
            volume_rates[0] += source_q
            tracer_rates[0, 0] += source_q
            derivative[ledger_start] = source_q
            derivative[:count] = volume_rates / volumes
            derivative[count:3 * count] = tracer_rates.ravel()
            return derivative
        return rhs


    def jacobian_for(source_q):
        rhs = rhs_for(source_q)

        def jacobian(seconds, current):
            if np.shape(current) != (len(state),) or not np.isfinite(current).all():
                raise ValueError("Jacobian requires a finite complete state vector")
            work["jacobian_evaluations"] += 1
            work["jacobian_rhs_evaluations"] += 1
            base = rhs(seconds, current, "Jacobian_baseline_rhs")
            matrix = np.zeros((len(state), len(state)))
            volumes, heads, capacities = physical(current[:count])
            for column in range(count):
                displaced = current.copy()
                head_cap = jacobian_policy(model, crown_transition_width_m)["max_head_step_m"]
                cell = model.cells[column]
                area = volumes[column] / cell.length_m
                raised_area = cell.section.area_perimeter(heads[column] + 0.5 * head_cap)[0]
                permitted_step = math.log1p((raised_area - area) / area)
                log_step = min(LOG_VOLUME_DIFFERENCE_STEP, permitted_step)
                if not math.isfinite(log_step) or log_step <= 0:
                    raise ValueError("head-bounded Jacobian step is not representable")
                displaced[column] += log_step
                actual_step = displaced[column] - current[column]
                if actual_step <= 0 or not math.isfinite(actual_step):
                    raise ValueError("fixed log-volume Jacobian step is not representable")
                work["jacobian_rhs_evaluations"] += 1
                shifted = rhs(seconds, displaced, "Jacobian_log_column_" + str(column))
                matrix[:, column] = (shifted - base) / actual_step
                work["jacobian_min_log_step"] = min(work.get("jacobian_min_log_step", actual_step), actual_step)
                work["jacobian_max_log_step"] = max(work.get("jacobian_max_log_step", actual_step), actual_step)
                trial_head = cell.section.head_for_area(math.exp(displaced[column]) / cell.length_m)
                observed_head_step = abs(trial_head - heads[column])
                work["jacobian_max_observed_head_step_m"] = max(work.get("jacobian_max_observed_head_step_m", 0.0), observed_head_step)
                if observed_head_step > head_cap + 16 * math.ulp(float(heads[column])):
                    raise ValueError("Jacobian perturbation exceeds declared physical head cap")
            volumes, heads, capacities = physical(current[:count])
            work["link_evaluations"] += link_count + 1
            if work["link_evaluations"] > experiment.max_link_evaluations or time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError("independent 1D Jacobian work/time bound exceeded")
            for ordinal, link in enumerate(model.links):
                flow = signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor = ordinal if flow >= 0 else ordinal + 1
                flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                coefficient = flow / volumes[donor]
                for tracer in range(2):
                    mass_start = count * (tracer + 1)
                    column = mass_start + donor
                    matrix[mass_start + ordinal, column] -= coefficient
                    matrix[mass_start + ordinal + 1, column] += coefficient
                    ledger_row = ledger_start + 6 + (tracer + 1) * link_count + ordinal
                    matrix[ledger_row, column] += coefficient
            boundary_capacity = min(capacities[-1], capacity_for(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                coefficient = outlet_flow / volumes[-1]
                for tracer, ledger_offset in ((0, 3), (1, 5)):
                    column = count * (tracer + 1) + count - 1
                    matrix[column, column] -= coefficient
                    matrix[ledger_start + ledger_offset, column] += coefficient
            if not np.isfinite(matrix).all():
                raise ValueError("explicit Jacobian contains nonfinite entries")
            return matrix
        return jacobian

    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for, lambda: max(peak_rss, process.memory_info().rss))



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
    volumes, heads, capacities = system.physical(state[:system.count])
    cells = []
    for ordinal, (cell, volume, head) in enumerate(zip(model.cells, volumes, heads)):
        section = cell.section
        details = friction_state(cell, float(head), width_m)
        details.update(cell_id=cell.cell_id, kind=cell.kind, head_m=float(head), volume_m3=float(volume),
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
    volumes, heads, capacities = system.physical(state[:system.count])
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
    recent_steps = deque(maxlen=16)
    observations = [(0.0, state.copy())]
    integration_segments = []
    saved_times = np.asarray(experiment.saved_times_s)
    saved_ordinal = 1

    def progress():
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
                     "is_accepted_state": False, "state_layout": "logV/sourceMass/tailwaterMass/boundaryAndPairedLedgers"}
        try:
            accepted_inventory = inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
        except Exception as snapshot_error:
            accepted_inventory = {"snapshot_error": str(snapshot_error), "state": [float(value) if math.isfinite(value) else None for value in accepted_state]}
        return {"last_accepted_physical_time_s": accepted_time, "configured_physical_duration_s": experiment.duration_s,
                "diagnostic_stop_s": diagnostic_stop_s, "physical_event_complete": accepted_time == experiment.duration_s,
                "work": dict(work), "elapsed_wall_seconds": elapsed, "triggered_guard": guard,
                "max_rhs_evaluations": experiment.max_rhs_evaluations, "max_link_evaluations": experiment.max_link_evaluations,
                "max_wall_seconds": experiment.max_wall_seconds, "accepted_steps": accepted_steps,
                "min_accepted_step_s": min_step, "max_accepted_step_s": max_step, "recent_accepted_steps": list(recent_steps),
                "last_evaluation": dict(last_evaluation), "last_trial": trial,
                "last_accepted_inventory": accepted_inventory,
                "actual_peak_rss_bytes": system.peak_rss(), "model_version": MODEL_VERSION,
                "crown_friction_transition_width_m": crown_transition_width_m,
                "inventory_scope": "actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume"}

    breaks = [0.0, experiment.duration_s]
    if experiment.scenario == "pulse":
        breaks.insert(1, experiment.pulse_duration_s)
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

            solver = Radau(tracked_rhs, lower, state, upper, max_step=experiment.max_step_s,
                           rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=tracked_jacobian)
            segment_steps = []
            while solver.status == "running":
                message = solver.step()
                if solver.status == "failed":
                    raise ValueError("Radau failed: " + str(message))
                previous_time = accepted_time
                accepted_time = float(solver.t)
                accepted_state = solver.y.copy()
                step = accepted_time - previous_time
                accepted_steps += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                recent_steps.append({"start_s": previous_time, "end_s": accepted_time, "step_s": step})
                segment_steps.append(step)
                dense = solver.dense_output()
                while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                    seconds = float(saved_times[saved_ordinal])
                    observations.append((seconds, dense(seconds)))
                    saved_ordinal += 1
            state = accepted_state.copy()
            integration_segments.append({"start_s": lower, "end_s": upper, "accepted_steps": len(segment_steps),
                                         "min_adaptive_step_s": min(segment_steps), "max_adaptive_step_s": max(segment_steps),
                                         "nfev": solver.nfev, "njev": solver.njev, "nlu": solver.nlu})
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
        volumes = np.exp(rows[:, :count])
        masses = rows[:, count:3 * count].reshape(-1, 2, count)
        if not np.isfinite(rows).all() or np.any(masses < 0) or np.any(masses.sum(axis=1) > volumes + experiment.absolute_tolerance * 100):
            raise ValueError("strict saved tracer positivity/composition failed; no output clamp")
        ledgers = rows[:, ledger_start:ledger_start + 6]
        residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
        residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
        residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
        threshold = max(1e-7, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
        if max(np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater)) > threshold:
            raise ValueError("water/tracer conservation gate failed")
        heads = np.array([physical(row[:count])[1] for row in rows])
        stages, pressure = [], []
        for head_row in heads:
            stages.append([float(head) if cell.kind == "surface" or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            pressure.append([float(head) if cell.kind == "underground" and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
        sink_link_index = next(ordinal for ordinal, link in enumerate(model.links) if link.kind == "sink_exchange")
        reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
        if time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024**3:
            raise ValueError("final independent 1D wall/RSS bound exceeded")
        return {"schema": SCHEMA, "numerical_version": NUMERICAL_VERSION,
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
                                    }, "status": "diagnostic_completed", "model": "finite_1d_diffusive_storage_signed_manning_Radau",
                "pressure_model": "explicit_engineered_Preissmann_slot_compliance_not_waterhammer",
                "scenario": experiment.scenario, "cell_ids": [cell.cell_id for cell in model.cells],
                "link_ids": [link.link_id for link in model.links], "times_s": [seconds for seconds, current in observations],
                "water_volume_m3": volumes.tolist(), "source_tracer_mass_m3": masses[:, 0].tolist(),
                "tailwater_tracer_mass_m3": masses[:, 1].tolist(), "open_channel_stage_m": stages,
                "pressurized_head_m": pressure, "hydraulic_head_m": heads.tolist(),
                "initial_untraced_water_m3": initial_volumes.tolist(),
                "ledger_columns": ["source_in_m3", "outlet_water_out_m3", "tailwater_water_in_m3", "source_tracer_out_m3", "tailwater_tracer_in_m3", "tailwater_tracer_out_m3"],
                "boundary_ledger_m3": ledgers.tolist(), "paired_link_water_integral_m3": rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(),
                "paired_link_source_integral_m3": rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(),
                "paired_link_tailwater_integral_m3": rows[:, ledger_start + 6 + 2 * link_count:].tolist(),
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
