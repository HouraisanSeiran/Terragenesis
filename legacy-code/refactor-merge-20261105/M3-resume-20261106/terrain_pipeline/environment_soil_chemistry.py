"""Finite water, dissolved/solid salt, organic carbon and mineral nutrient pools.

Salt concentration is kg salt / m3 water, not EC or pH. No acid/base or sodicity
chemistry is inferred. External water/solute packets must be supplied once.
"""
import numpy as np

from .environment_ecology_contract import field, frame, metadata, stocks

ALGORITHM = "environment-soil-finite-solutes-v1"
PARAMETERS = {"salt_solubility_kg_m3": 350., "stress_half_salinity_kg_m3": 4.,
              "carbon_decay_s": 20. * 365. * 86400.}


def initialize_soil_chemistry(context, *, water_depth_m=.1, salinity_kg_m3=0.,
                              organic_carbon_kg_m2=1., nutrient_kg_m2=.01,
                              organic_nutrient_kg_m2=.02):
    shape, area, masks = frame(context, 0.)
    valid = masks["valid_mask"]
    water = field({"v": water_depth_m}, "v", shape) * area * valid
    salinity = field({"v": salinity_kg_m3}, "v", shape)
    if np.any(salinity > PARAMETERS["salt_solubility_kg_m3"]):
        raise ValueError("initial dissolved salinity exceeds solubility")
    return {"water_m3": water, "salt_dissolved_kg": water * salinity,
            "salt_solid_kg": np.zeros(shape),
            "organic_carbon_kg": field({"v": organic_carbon_kg_m2}, "v", shape) * area * valid,
            "organic_nutrient_kg": field({"v": organic_nutrient_kg_m2}, "v", shape) * area * valid,
            "nutrient_kg": field({"v": nutrient_kg_m2}, "v", shape) * area * valid}


def advance_soil_chemistry(state, forcing, context, dt_s):
    shape, _, masks = frame(context, dt_s)
    pools = stocks(state, ("water_m3", "salt_dissolved_kg", "salt_solid_kg",
                           "organic_carbon_kg", "organic_nutrient_kg", "nutrient_kg"), shape)
    active = masks["valid_mask"] & ~masks["protected_mask"]
    water_in = field(forcing, "water_input_m3_s", shape) * dt_s * active
    concentration = field(forcing, "inflow_salinity_kg_m3", shape)
    salt_in = water_in * concentration
    water = pools["water_m3"] + water_in
    dissolved = pools["salt_dissolved_kg"] + salt_in
    solid = pools["salt_solid_kg"].copy()
    equilibrium = np.where(active & (dt_s > 0.), np.minimum(dissolved + solid, water * PARAMETERS["salt_solubility_kg_m3"]), dissolved)
    solid = dissolved + solid - equilibrium
    dissolved = equilibrium
    drainage = np.minimum(water, field(forcing, "drainage_m3_s", shape) * dt_s * active)
    fraction = np.divide(drainage, water, out=np.zeros(shape), where=water > 0.)
    salt_leached = dissolved * fraction
    dissolved -= salt_leached
    water -= drainage
    evaporation = np.minimum(water, field(forcing, "evaporation_m3_s", shape) * dt_s * active)
    water -= evaporation
    equilibrium = np.where(active & (dt_s > 0.), np.minimum(dissolved + solid, water * PARAMETERS["salt_solubility_kg_m3"]), dissolved)
    solid = dissolved + solid - equilibrium
    dissolved = equilibrium
    litter = field(forcing, "litter_carbon_kg", shape) * active * (dt_s > 0.)
    carbon = pools["organic_carbon_kg"] + litter
    respiration = carbon * (-np.expm1(-dt_s / PARAMETERS["carbon_decay_s"])) * active
    carbon -= respiration
    nutrient_in = field(forcing, "nutrient_input_kg_s", shape) * dt_s * active
    litter_nutrient = field(forcing, "litter_nutrient_kg", shape) * active * (dt_s > 0.)
    organic_nutrient = pools["organic_nutrient_kg"] + litter_nutrient
    mineralized = organic_nutrient * (-np.expm1(-dt_s / PARAMETERS["carbon_decay_s"])) * active
    organic_nutrient -= mineralized
    nutrient_return = field(forcing, "plant_nutrient_return_kg", shape) * active * (dt_s > 0.)
    nutrients = pools["nutrient_kg"] + nutrient_in + mineralized + nutrient_return
    nutrient_leached = nutrients * fraction
    nutrients -= nutrient_leached
    demand = field(forcing, "plant_uptake_demand_kg", shape) * active * (dt_s > 0.)
    uptake = np.minimum(nutrients, demand)
    nutrients -= uptake
    salinity = np.divide(dissolved, water, out=np.zeros(shape), where=water > 0.)
    stress = 1. / (1. + salinity / PARAMETERS["stress_half_salinity_kg_m3"])
    stress = np.where(water > 0., stress, 0.)
    output = {"water_m3": water, "salt_dissolved_kg": dissolved, "salt_solid_kg": solid,
              "organic_carbon_kg": carbon, "organic_nutrient_kg": organic_nutrient, "nutrient_kg": nutrients}
    ledger = {"water_input_m3": float(water_in.sum()), "drainage_m3": float(drainage.sum()),
              "evaporation_m3": float(evaporation.sum()), "salt_input_kg": float(salt_in.sum()),
              "salt_leached_kg": float(salt_leached.sum()), "litter_carbon_kg": float(litter.sum()),
              "respired_carbon_kg": float(respiration.sum()), "plant_uptake_kg": float(uptake.sum()),
              "nutrient_leached_kg": float(nutrient_leached.sum()), "nutrient_input_kg": float(nutrient_in.sum()),
              "mineralized_nutrient_kg": float(mineralized.sum())}
    ledger["litter_nutrient_kg"] = float(litter_nutrient.sum())
    ledger["plant_nutrient_return_kg"] = float(nutrient_return.sum())
    ledger["water_residual_m3"] = float((pools["water_m3"] + water_in - water - drainage - evaporation).sum())
    ledger["salt_residual_kg"] = float((pools["salt_dissolved_kg"] + pools["salt_solid_kg"] + salt_in - dissolved - solid - salt_leached).sum())
    ledger["carbon_residual_kg"] = float((pools["organic_carbon_kg"] + litter - carbon - respiration).sum())
    ledger["nutrient_residual_kg"] = float((pools["nutrient_kg"] + pools["organic_nutrient_kg"] + nutrient_in + nutrient_return + litter_nutrient - nutrients - organic_nutrient - nutrient_leached - uptake).sum())
    return {"state": output, "fluxes": {"plant_stress_factor": stress, "salinity_kg_m3": salinity,
            "plant_uptake_kg": uptake, "salt_leached_kg": salt_leached,
            "nutrient_leached_kg": nutrient_leached, "respired_carbon_kg": respiration,
            "drainage_m3": drainage, "evaporation_m3": evaporation}, "ledger": ledger,
            "metadata": metadata(ALGORITHM, context, dt_s,
            ["well-mixed account; no pH, alkalinity, ion species or reactive mineral equilibrium",
             "finite organic nutrient pool mineralizes with carbon decay; no nutrient species"], PARAMETERS.copy())}


initialize = initialize_soil_chemistry
step = advance_soil_chemistry
