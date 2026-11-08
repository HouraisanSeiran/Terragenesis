"""Explicit finite lava/ash event, graph transport and cooling heat release."""
import numpy as np
from terrain_pipeline.environment_process_contract import _field, _grid, _parameters
from terrain_pipeline import environment_aeolian
from terrain_pipeline.drainage import segments_clear as segments_clear

ALGORITHM = "environment-event-lava-ash-cooling-v1"


def initialize(context):
    height, _, _ = _grid(context, 1.)
    return {key: np.zeros(height.shape) for key in
            ("mobile_lava_m3", "lava_heat_j", "airborne_ash_m3", "deposited_lava_m3", "deposited_ash_m3")}


def step(state, forcing, context, dt_s, parameters=None):
    height, spacing, active = _grid(context, dt_s)
    p = _parameters(parameters, {"lava_heat_j_m3": 2.e9, "cooling_time_s": 3600.,
        "lava_speed_m_s": .05, "ash_settling_time_s": 1800., "ash_solid_fraction": .5})
    if p["ash_solid_fraction"] > 1:
        raise ValueError("ash solid fraction must not exceed one")
    old = {key: _field(state[key], height.shape, key, 0.) for key in initialize(context)}
    lava_input = _field(forcing.get("lava_input_m3", 0.), height.shape, "lava input", 0.)
    ash_input = _field(forcing.get("ash_input_m3", 0.), height.shape, "ash input", 0.)
    if np.any((lava_input + ash_input)[~active] != 0):
        raise ValueError("eruption input requires unprotected valid source")
    lava = old["mobile_lava_m3"] + lava_input
    heat = old["lava_heat_j"] + lava_input * p["lava_heat_j_m3"]
    receiver = np.asarray(context["receiver"])
    if (receiver.size != height.size or receiver.dtype.kind not in "iu"
            or np.any(receiver < -1) or np.any(receiver >= height.size)):
        raise ValueError("explicit finite graph receivers required")
    receiver = receiver.reshape(-1)
    source = np.flatnonzero((receiver >= 0) & active.ravel())
    target = receiver[source]
    legal = active.ravel()[target] & (height.ravel()[source] > height.ravel()[target])
    legal &= segments_clear(source, target, active)
    source, target = source[legal], target[legal]
    # Geometry may supply true graph nodes; otherwise this explicitly declared
    # process uses the context's native account anchors for transport length.
    if "node_x_m" in context and "node_z_m" in context:
        x = _field(np.asarray(context["node_x_m"]).reshape(height.shape), height.shape, "node x").ravel()
        z = _field(np.asarray(context["node_z_m"]).reshape(height.shape), height.shape, "node z").ravel()
        length = np.hypot(x[source] - x[target], z[source] - z[target])
    else:
        length = spacing * np.hypot(source % height.shape[1] - target % height.shape[1],
                                     source // height.shape[1] - target // height.shape[1])
    if np.any(length <= 0):
        raise ValueError("lava edge requires positive metric length")
    fraction = np.minimum(1., p["lava_speed_m_s"] * dt_s / length)
    moved = lava.ravel()[source] * fraction
    moved_heat = heat.ravel()[source] * fraction
    lava.ravel()[source] -= moved
    heat.ravel()[source] -= moved_heat
    np.add.at(lava.ravel(), target, moved)
    np.add.at(heat.ravel(), target, moved_heat)
    cooling = np.where(active, -np.expm1(-dt_s / p["cooling_time_s"]), 0.)
    solidified = lava * cooling
    released_heat = heat * cooling
    ash = old["airborne_ash_m3"] + ash_input
    ash_transport = environment_aeolian.step(
        {"loose_solid_m3": np.zeros_like(ash), "airborne_solid_m3": ash},
        {"wind_x_m_s": forcing.get("wind_x_m_s", 0.),
         "wind_z_m_s": forcing.get("wind_z_m_s", 0.)}, context, dt_s,
        {"settling_time_s": p["ash_settling_time_s"]})
    ash_deposit = ash_transport["fluxes"]["deposited_solid_m3"]
    ash_export = ash_transport["fluxes"]["boundary_export_solid_m3"]
    new = {"mobile_lava_m3": lava - solidified, "lava_heat_j": heat - released_heat,
        "airborne_ash_m3": ash_transport["state"]["airborne_solid_m3"],
        "deposited_lava_m3": old["deposited_lava_m3"] + solidified,
        "deposited_ash_m3": old["deposited_ash_m3"] + ash_deposit}
    geothermal = _field(forcing.get("geothermal_w_m2", 0.), height.shape, "geothermal", 0.)
    geothermal = np.where(active, geothermal, 0.)
    mass_keys = ("mobile_lava_m3", "airborne_ash_m3", "deposited_lava_m3", "deposited_ash_m3")
    initial_mass = sum(float(old[key].sum()) for key in mass_keys)
    final_mass = sum(float(new[key].sum()) for key in mass_keys)
    return {"state": new, "fluxes": {"solidified_lava_m3": solidified,
        "deposited_ash_solid_m3": ash_deposit,
        "height_change_m": (solidified + ash_deposit / p["ash_solid_fraction"]) / spacing ** 2,
        "lava_transport_solid_m3": np.bincount(source, weights=moved, minlength=height.size).reshape(height.shape),
        "ash_boundary_export_solid_m3": ash_export,
        "geothermal_heat_w_m2": geothermal + released_heat / (spacing ** 2 * dt_s)},
        "ledger": {"event_input_solid_m3": float((lava_input + ash_input).sum()),
            "initial_solid_m3": initial_mass, "final_solid_m3": final_mass,
            "boundary_export_solid_m3": float(ash_export.sum()),
            "solid_residual_m3": final_mass + float(ash_export.sum()) - initial_mass - float((lava_input + ash_input).sum()),
            "cooling_heat_j": float(released_heat.sum()),
            "heat_residual_j": float(new["lava_heat_j"].sum() + released_heat.sum() - old["lava_heat_j"].sum() - lava_input.sum() * p["lava_heat_j_m3"]),
            "geothermal_external_j": float(geothermal.sum() * spacing ** 2 * dt_s)},
        "metadata": {"algorithm": ALGORITHM, "parameters": p,
            "source": "explicit declared eruption and external geothermal scenario; uncalibrated",
            "units": "lava/ash m3 solid per cell; stored heat J per cell; geothermal W/m2; terrain delta metres bulk; dt seconds",
            "coordinates": "context graph nodes when supplied, otherwise native anchors",
            "ash_transport": "shared finite wind transport and settling; no ash re-entrainment in this module",
            "lava_boundary": "terminal lava retained and cooled; no fictitious open lava outlet",
            "limitation": "surface cooling/deposition only; no plume aerodynamics, magma intrusion mechanics or 3D lava tubes"}}
