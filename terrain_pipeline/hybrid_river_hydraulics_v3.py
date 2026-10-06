"""Versioned Radau kernel: fixed log-volume differences and analytic tracer Jacobian."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.hybrid_river_hydraulics import (
    Experiment, Model, OLD_FACE_BUDGET_REMAINING, conveyance, signed_flow)

SCHEMA = "td-hybrid-river-hydraulics-v3"
NUMERICAL_VERSION = "fixed_log_volume_difference_analytic_tracer_jacobian-v3"
LOG_VOLUME_DIFFERENCE_STEP = 1e-6


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


def build_system(model: Model, experiment: Experiment):
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

    def physical(log_volumes):
        if not np.isfinite(log_volumes).all() or np.any(abs(log_volumes) > 600):
            raise ValueError("storage transform exceeds physical range")
        volumes = np.exp(log_volumes)
        heads = np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any(head <= cell.section.floor_m for cell, head in zip(model.cells, heads)):
            raise ValueError("positive storage is below representable section depth; no floor clamp")
        capacities = np.array([conveyance(cell, head) for cell, head in zip(model.cells, heads)])
        return volumes, heads, capacities

    def rhs_for(source_q):
        def rhs(seconds, current):
            nonlocal peak_rss
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
            boundary_capacity = min(capacities[-1], conveyance(model.cells[-1], experiment.tailwater_head_m))
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
            base = rhs(seconds, current)
            work["jacobian_rhs_evaluations"] += 1
            matrix = np.zeros((len(state), len(state)))
            for column in range(count):
                displaced = current.copy()
                displaced[column] += LOG_VOLUME_DIFFERENCE_STEP
                actual_step = displaced[column] - current[column]
                if actual_step <= 0 or not math.isfinite(actual_step):
                    raise ValueError("fixed log-volume Jacobian step is not representable")
                shifted = rhs(seconds, displaced)
                work["jacobian_rhs_evaluations"] += 1
                matrix[:, column] = (shifted - base) / actual_step
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
            boundary_capacity = min(capacities[-1], conveyance(model.cells[-1], experiment.tailwater_head_m))
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


def run_experiment(model: Model, experiment: Experiment):
    system = build_system(model, experiment)
    count = system.count
    link_count = len(model.links)
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes = system.initial_volumes
    work = system.work
    started = system.started
    physical = system.physical
    rhs_for = system.rhs_for

    breaks = [0.0, experiment.duration_s]
    if experiment.scenario == "pulse":
        breaks.insert(1, experiment.pulse_duration_s)
    observations = []
    integration_segments = []
    saved_times = np.asarray(experiment.saved_times_s)
    for lower, upper in zip(breaks[:-1], breaks[1:]):
        source_q = experiment.pulse_q_m3_s if experiment.scenario == "pulse" and lower < experiment.pulse_duration_s else 0.0
        solution = solve_ivp(rhs_for(source_q), (lower, upper), state, method="Radau", dense_output=True,
                             max_step=experiment.max_step_s, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance,
                             jac=system.jacobian_for(source_q))
        if not solution.success:
            raise ValueError("Radau failed: " + solution.message)
        steps = np.diff(solution.t)
        integration_segments.append({"start_s": lower, "end_s": upper, "accepted_steps": len(steps),
                                     "min_adaptive_step_s": float(steps.min()), "max_adaptive_step_s": float(steps.max()),
                                     "nfev": solution.nfev, "njev": solution.njev, "nlu": solution.nlu})
        selected = saved_times[(saved_times >= lower) & (saved_times <= upper)]
        for seconds in selected:
            if observations and observations[-1][0] == seconds:
                continue
            observations.append((float(seconds), solution.sol(seconds)))
        state = solution.y[:, -1]
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
    return {"schema": SCHEMA, "numerical_version": NUMERICAL_VERSION,
            "jacobian_policy": {"log_volume_absolute_step": LOG_VOLUME_DIFFERENCE_STEP,
                                "step_units": "dimensionless_log_volume_fixed_forward_difference",
                                "tracer_columns": "analytic_donor_transport", "ledger_feedback_columns": "exact_zero",
                                "nonsmooth_scope": "fixed_forward_secant_at_donor_kinks_crowns_and_horizontal_ledges_no_smoothing",
                                "scipy_adaptive_difference_factor_used": False}, "status": "diagnostic_completed", "model": "finite_1d_diffusive_storage_signed_manning_Radau",
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
