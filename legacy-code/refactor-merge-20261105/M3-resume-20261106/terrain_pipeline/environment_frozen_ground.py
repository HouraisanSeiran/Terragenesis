"""Finite soil-water enthalpy, insulated snow and seasonal thaw diagnostics."""
import numpy as np
from terrain_pipeline.environment_process_contract import _field, _grid, _parameters

ALGORITHM = "environment-soil-water-enthalpy-v1"
LATENT_J_M3 = 3.34e8


def initialize(context, *, liquid_water_m=.1, ground_ice_m=0., soil_temperature_c=0., snow_swe_m=0.):
    height, _, _ = _grid(context, 1.)
    return {"liquid_water_m": _field(liquid_water_m, height.shape, "liquid", 0.),
        "ground_ice_m": _field(ground_ice_m, height.shape, "ice", 0.),
        "soil_temperature_c": _field(soil_temperature_c, height.shape, "temperature"),
        "snow_swe_m": _field(snow_swe_m, height.shape, "snow", 0.),
        "thaw_time_s": np.zeros(height.shape), "frozen_time_s": np.zeros(height.shape)}


def step(state, forcing, context, dt_s, parameters=None):
    height, spacing, active = _grid(context, dt_s)
    active &= ~_field(context.get("ocean_mask", False), height.shape, "ocean").astype(bool)
    p = _parameters(parameters, {"soil_heat_capacity_j_m2_k": 2.e6,
        "air_exchange_w_m2_k": 5., "snow_insulation_per_m_swe": 50.,
        "thermal_diffusivity_m2_s": 5.e-7, "soil_depth_m": 2.})
    old = {key: _field(value, height.shape, key, None if key == "soil_temperature_c" else 0.)
           for key, value in state.items()}
    liquid, ice, snow, temp = (old[key] for key in ("liquid_water_m", "ground_ice_m", "snow_swe_m", "soil_temperature_c"))
    heat = _field(forcing.get("ground_heat_w_m2", 0.), height.shape, "ground heat")
    heat += _field(forcing.get("geothermal_heat_w_m2", 0.), height.shape, "geothermal")
    air = _field(forcing.get("air_temperature_c", temp), height.shape, "air temperature")
    heat += p["air_exchange_w_m2_k"] * (air - temp) / (1 + p["snow_insulation_per_m_swe"] * snow)
    energy = np.where(active, heat * dt_s, 0.)
    snowmelt = np.minimum(snow, np.maximum(energy, 0.) / LATENT_J_M3)
    soil_energy = energy - snowmelt * LATENT_J_M3
    mass = liquid + ice
    initial_enthalpy = temp * p["soil_heat_capacity_j_m2_k"] + liquid * LATENT_J_M3
    enthalpy = initial_enthalpy + soil_energy
    new_liquid = np.clip(enthalpy / LATENT_J_M3, 0., mass)
    new_ice = mass - new_liquid
    new_temp = np.where(enthalpy < 0, enthalpy, np.maximum(enthalpy - mass * LATENT_J_M3, 0.)) / p["soil_heat_capacity_j_m2_k"]
    new = {key: value.copy() for key, value in old.items()}
    for key, value in (("liquid_water_m", new_liquid), ("ground_ice_m", new_ice),
                       ("soil_temperature_c", new_temp), ("snow_swe_m", snow - snowmelt)):
        new[key] = np.where(active, value, old[key])
    frozen = new["ground_ice_m"] > 1e-10
    new["thaw_time_s"] = np.where(active, np.where(frozen, 0., old["thaw_time_s"] + dt_s), old["thaw_time_s"])
    new["frozen_time_s"] = np.where(active, np.where(frozen, old["frozen_time_s"] + dt_s, 0.), old["frozen_time_s"])
    final_enthalpy = new["soil_temperature_c"] * p["soil_heat_capacity_j_m2_k"] + new["liquid_water_m"] * LATENT_J_M3
    area = spacing ** 2
    return {"state": new, "fluxes": {"snow_meltwater_m": snowmelt,
        "frozen_water_m": np.maximum(new["ground_ice_m"] - ice, 0.),
        "thawed_water_m": np.maximum(ice - new["ground_ice_m"], 0.),
        "infiltration_factor": np.divide(new["liquid_water_m"], mass, out=np.ones_like(mass), where=mass > 0),
        "active_layer_depth_m": np.minimum(p["soil_depth_m"], np.sqrt(2 * p["thermal_diffusivity_m2_s"] * new["thaw_time_s"])),
        "height_change_m": .09 * (new["ground_ice_m"] - ice)},
        "ledger": {"heat_input_j": float(energy.sum() * area),
            "snow_latent_j": float(snowmelt.sum() * LATENT_J_M3 * area),
            "energy_residual_j": float(((final_enthalpy - initial_enthalpy) - soil_energy).sum() * area),
            "water_residual_m3": float((new["liquid_water_m"] + new["ground_ice_m"] + new["snow_swe_m"] + snowmelt - liquid - ice - snow).sum() * area)},
        "metadata": {"algorithm": ALGORITHM, "parameters": p, "latent_heat_j_m3_water": LATENT_J_M3,
            "source": "declared uncalibrated one-layer enthalpy and snow insulation",
            "units": "water/ice/snow water-equivalent metres; soil Celsius; time seconds; ledger J and m3 water; height metres",
            "limitation": "no multilayer permafrost/talik mechanics; snow melt exported for water consumer; phase must initially be in thermal equilibrium"}}
