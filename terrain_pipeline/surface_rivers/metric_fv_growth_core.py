"""Common FV growth step with explicitly supplied sediment operators."""
from dataclasses import dataclass, replace
from functools import partial
import numpy as np

from terrain_pipeline.shallow_water import shallow_water_rhs_accelerated as shallow_water_rhs, storage_kernel, manning_damping_accelerated as manning_damping
from terrain_pipeline.shallow_water import advance_with_drag as advance_shallow_water
from .metric_fv_coastal_sediment import MorphodynamicStepTooLarge
from .metric_fv_exchange_v3 import ExchangeConfig
from .metric_fv_suspended_supply import advance_suspended


@dataclass(frozen=True)
class GrowthOperators:
    transport_bedload: object
    calm_transport: object
    equilibrium_concentration: object
    entrain: object
    slope_transport: object


def zero_wave_field(depth, geometry, config):
    return {name: np.zeros_like(depth) for name in ("wave_height_m", "wave_orbital_velocity_m_s",
        "wave_number_m_inverse", "wave_group_speed_m_s")}


def advance_growth(geometry, *, floor_m, depth_m, momentum_m2_s, suspended_solid_m3,
                   river_q_m3_s, input_solid_m3, sea_stages_m, inlet_cells, interval_s, budget,
                   bedload_config, suspended_config, operators, interval_observer=None,
                   momentum_observer=None, exchange_config=ExchangeConfig()):
    """Keep the established split order and joint commit; inject only operators."""
    transport_bedload = operators.transport_bedload
    _calm_transport = operators.calm_transport
    equilibrium_concentration = operators.equilibrium_concentration
    entrain = operators.entrain
    slope_transport = operators.slope_transport
    exchange_config.validate()
    a = geometry["arrays"]
    bed = a["H2_m"]
    datum = float(bed.min())
    support = {"subcell_bed_relative_m": (bed - datum).reshape(-1, 1).copy(),
        "subcell_prefix_relative_m": (bed - datum).reshape(-1, 1).copy(),
        "face_segment_crest_relative_m": (a["face_crest_m"] - datum)[:, None].copy(),
        "boundary_segment_crest_relative_m": (a["boundary_crest_m"] - datum)[:, None].copy()}
    a.update(support)
    geometry["metadata"]["hydraulic_datum_m"] = datum
    momentum = np.asarray(momentum_m2_s, float).copy()
    suspended = np.asarray(suspended_solid_m3, float).copy()
    if (momentum.shape != (bed.size, 2) or suspended.shape != bed.shape
            or not np.isfinite(momentum).all() or not np.isfinite(suspended).all()
            or np.any(suspended < 0.) or np.any(momentum[np.asarray(depth_m).ravel() == 0.] != 0.)):
        raise ValueError("matching finite live water momentum and suspended state required")
    beds, suspensions = [bed.copy()], [suspended.copy()]
    ledgers = []
    initialized = False
    initial_momentum = momentum.copy()
    previous_depth = np.asarray(depth_m).ravel().copy()
    previous_momentum = initial_momentum.copy()

    def source(index):
        result = np.zeros(bed.size, float)
        result[inlet_cells] = river_q_m3_s[index] / len(inlet_cells)
        return result.reshape(bed.shape)

    def update(packet):
        nonlocal suspended, previous_depth, previous_momentum
        index = packet["interval"]
        packet["tailwater_m"] = np.full(len(a["boundary_cell"]), sea_stages_m[index])
        if index == 0:
            packet["momentum_before"] = initial_momentum.copy()
        incoming_depth_error = float(abs(packet["depth_before_m"] - previous_depth).max())
        incoming_momentum_error = float(abs(packet["momentum_before"] - previous_momentum).max())
        if incoming_depth_error > 1.e-12 or incoming_momentum_error > 1.e-12:
            raise RuntimeError("water state was not retained between sediment coupling intervals")
        previous_depth = packet["depth_after_m"].copy()
        previous_momentum = packet["momentum_after"].copy()
        before = bed.copy()
        water_depth_before_handoff = packet["depth_after_m"].copy()
        water_momentum_before_handoff = packet["momentum_after"].copy()
        old_suspended = float(suspended.sum())
        transport = _calm_transport if bedload_config.wave_height_m == 0. else transport_bedload
        bedload = transport(bed, floor_m, geometry, packet, bedload_config)
        bedload["bed_m"], slope_transfer, slope_ledger = slope_transport(bedload["bed_m"], floor_m,
            geometry, packet["time_end_s"] - packet["time_start_s"], bedload_config, exchange_config, packet["depth_after_m"])
        bedload["slope_internal_transfer_solid_m3"] = slope_transfer
        bedload["ledger"].update(slope_ledger)
        settling = advance_suspended(suspended, bedload["bed_m"], geometry, packet,
            float(input_solid_m3[index]), inlet_cells, replace(suspended_config, settling_velocity_m_s=0.))
        equilibrium, excess = equilibrium_concentration(bedload["bed_m"], geometry, packet, bedload_config, exchange_config)
        area = geometry["metadata"]["spacing_m"] ** 2
        water_volume = packet["depth_after_m"] * area
        mass = settling["suspended_solid_m3"].ravel()
        dt = packet["time_end_s"] - packet["time_start_s"]
        fraction = -np.expm1(-suspended_config.settling_velocity_m_s * dt / np.maximum(packet["depth_after_m"], 1.e-12))
        actual_deposited = (np.maximum(mass - equilibrium * water_volume, 0.) * fraction).reshape(bed.shape)
        actual_deposited[np.asarray(a["fixed_bed_cell"], bool).reshape(bed.shape)] = 0.
        settling["suspended_solid_m3"] -= actual_deposited
        settling["bed_m"] += actual_deposited / (area * (1. - bedload_config.porosity))
        settling["deposited_solid_m3"] = actual_deposited
        changed, exchanged_mass, eroded, exchange_ledger = entrain(settling["bed_m"],
            settling["suspended_solid_m3"], floor_m, geometry, packet, bedload_config, exchange_config,
            equilibrium_state=(equilibrium, excess))
        settling["bed_m"] = changed
        settling["suspended_solid_m3"] = exchanged_mass
        settling["entrained_solid_m3"] = eroded
        settling["ledger"].update(exchange_ledger)
        settling["ledger"]["deposited_solid_m3"] = float(actual_deposited.sum())
        settling["ledger"]["final_suspended_solid_m3"] = float(exchanged_mass.sum())
        settling["ledger"]["exchange_residual_solid_m3"] = float(exchanged_mass.sum()
            + actual_deposited.sum() - eroded.sum() - old_suspended - input_solid_m3[index]
            + settling["boundary_export_solid_m3"].sum())
        changed = settling["bed_m"]
        if abs(changed - before).max() > bedload_config.max_bed_change_m * (1. + 1.e-12):
            raise MorphodynamicStepTooLarge("combined bedload and settling bed jump too large; retry shorter full interval")
        suspended = settling["suspended_solid_m3"]
        bed[:] = changed
        flat = bed.ravel()
        a["face_crest_m"][:] = np.maximum(flat[a["face_left"]], flat[a["face_right"]])
        a["boundary_crest_m"][:] = flat[a["boundary_cell"]]
        support["subcell_bed_relative_m"][:, 0] = flat - datum
        support["subcell_prefix_relative_m"][:, 0] = flat - datum
        support["face_segment_crest_relative_m"][:, 0] = a["face_crest_m"] - datum
        support["boundary_segment_crest_relative_m"][:, 0] = a["boundary_crest_m"] - datum
        solid_per_m = geometry["metadata"]["spacing_m"] ** 2 * (1. - bedload_config.porosity)
        initial_bed_solid = float(((before - floor_m) * solid_per_m).sum())
        final_bed_solid = float(((bed - floor_m) * solid_per_m).sum())
        exported = bedload["ledger"]["exported_solid_m3"] + settling["ledger"]["exported_solid_m3"]
        ledger = {"interval": int(index), "bedload": bedload["ledger"], "suspended": settling["ledger"],
            "initial_bed_solid_m3": initial_bed_solid, "final_bed_solid_m3": final_bed_solid,
            "initial_suspended_solid_m3": old_suspended, "final_suspended_solid_m3": float(suspended.sum()),
            "injected_solid_m3": float(input_solid_m3[index]), "exported_solid_m3": exported,
            "combined_residual_solid_m3": final_bed_solid + suspended.sum() + exported
                - initial_bed_solid - old_suspended - input_solid_m3[index],
            "maximum_bed_change_m": float(abs(bed - before).max()),
            "incoming_water_depth_continuity_error_m": incoming_depth_error,
            "incoming_water_momentum_continuity_error_m2_s": incoming_momentum_error,
            "water_depth_handoff_error_m": float(abs(packet["depth_after_m"] - water_depth_before_handoff).max()),
            "water_momentum_handoff_error_m2_s": float(abs(packet["momentum_after"] - water_momentum_before_handoff).max())}
        ledgers.append(ledger)
        beds.append(bed.copy())
        suspensions.append(suspended.copy())
        if interval_observer is not None:
            interval_observer(packet, bedload, settling, ledger)

    def stage_provider(h):
        return storage_kernel(h, support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])

    def speed(state, gravity):
        nonlocal initialized
        if not initialized:
            state[:, 1:] = initial_momentum
            initialized = True
        h = np.maximum(stage_provider(state[:, 0]) - support["subcell_bed_relative_m"][:, 0], 0.)
        velocity = np.divide(state[:, 1:], state[:, :1], out=np.zeros_like(state[:, 1:]), where=state[:, :1] > 0.)
        return float((abs(velocity).sum(axis=1) + 2. * np.sqrt(gravity * h)).max(initial=0.))

    result = advance_shallow_water(geometry, rhs=partial(shallow_water_rhs, support=support),
        model="FV-finite-exchange-wetbank-growth-v3", scope="live FV water, finite shear-dependent bed/suspended exchange and wet-bank slope flux",
        physical_limitation="empirical equilibrium entrainment and excess-slope rates, interval-net advection, MPM/Airy; no wave radiation stress or cohesive banks",
        initial_depth_m=np.asarray(depth_m, np.float64), forcing_interval_s=interval_s, intervals=len(input_solid_m3),
        forcing_provider=source, boundary_stage_provider=lambda i: np.full(len(a["boundary_cell"]), sea_stages_m[i]),
        source_identity=geometry["metadata"]["source_identity"], forcing_identity="finite-source-cursor-river-sea-wave",
        budget=budget, snapshot_interval_s=interval_s, interval_observer=update,
        momentum_observer=momentum_observer or (lambda p: None), hydraulic_datum_m=datum,
        wave_speed=speed, stage_provider=stage_provider,
        drag_provider=partial(manning_damping, support=support))
    result["arrays"]["bed_m"] = np.asarray(beds)
    result["arrays"]["stage_m"] = np.asarray(beds) + result["arrays"]["depth_m"]
    result["arrays"]["stage_relative_m"] = result["arrays"]["stage_m"] - datum
    result["arrays"]["suspended_solid_m3"] = np.asarray(suspensions)
    result["arrays"]["momentum_x_m2_s"][0] = initial_momentum[:, 0].reshape(bed.shape)
    result["arrays"]["momentum_z_m2_s"][0] = initial_momentum[:, 1].reshape(bed.shape)
    result["sediment_ledgers"] = ledgers
    return result
