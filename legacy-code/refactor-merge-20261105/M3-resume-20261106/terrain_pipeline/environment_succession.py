"""Finite carbon pools, explicit fire/mortality and nutrient-limited recovery.

Carbon stocks are kg C per native account, not dry biomass. Photosynthesis is
an external atmospheric input; fire has separate atmospheric and char sinks.
Root/roughness outputs are declared ecological closures, not calibrated species.
"""
import numpy as np

from .environment_ecology_contract import field, frame, metadata, stocks

ALGORITHM = "environment-succession-carbon-pools-v1"
PARAMETERS = {"growth_carbon_kg_m2_s": 2.e-8, "carrying_carbon_kg_m2": 8.,
              "nutrient_kg_per_carbon_kg": .02, "turnover_s": 5. * 365. * 86400.,
              "char_fraction": .15, "root_cohesion_full_pa": 6000.,
              "bare_manning_n": .025, "vegetated_manning_increment": .09}


def initialize_succession(context, *, biomass_carbon_kg_m2=0., dead_carbon_kg_m2=0.):
    shape, area, masks = frame(context, 0.)
    land = masks["valid_mask"] & ~masks["ocean_mask"]
    return {"biomass_carbon_kg": field({"v": biomass_carbon_kg_m2}, "v", shape) * area * land,
            "dead_carbon_kg": field({"v": dead_carbon_kg_m2}, "v", shape) * area * land,
            "char_carbon_kg": np.zeros(shape), "age_s": np.zeros(shape),
            "plant_nutrient_kg": field({"v": biomass_carbon_kg_m2}, "v", shape) * area * land * PARAMETERS["nutrient_kg_per_carbon_kg"],
            "disturbance_fraction": np.zeros(shape)}


def advance_succession(state, forcing, context, dt_s):
    shape, area, masks = frame(context, dt_s)
    pools = stocks(state, ("biomass_carbon_kg", "dead_carbon_kg", "char_carbon_kg",
                          "plant_nutrient_kg", "age_s", "disturbance_fraction"), shape)
    active = masks["valid_mask"] & ~masks["ocean_mask"] & ~masks["protected_mask"]
    if np.any(pools["disturbance_fraction"] > 1.):
        raise ValueError("disturbance fraction must be <=1")
    fire_rate = field(forcing, "fire_hazard_s", shape)
    mortality_rate = field(forcing, "disturbance_hazard_s", shape)
    stress = field(forcing, "plant_stress_factor", shape, 1.)
    moisture = field(forcing, "water_available_fraction", shape, 1.)
    if np.any(stress > 1.) or np.any(moisture > 1.):
        raise ValueError("stress and water fractions must be <=1")
    temperature = field(forcing, "temperature_c", shape, 20., nonnegative=False)
    fire_fraction = -np.expm1(-fire_rate * dt_s) * active
    burned_live = pools["biomass_carbon_kg"] * fire_fraction
    burned_dead = pools["dead_carbon_kg"] * fire_fraction
    burned = burned_live + burned_dead
    char = burned * PARAMETERS["char_fraction"]
    atmosphere = burned - char
    live = pools["biomass_carbon_kg"] - burned_live
    dead = pools["dead_carbon_kg"] - burned_dead
    mortality = live * (-np.expm1(-mortality_rate * dt_s)) * active
    live -= mortality
    dead += mortality
    turnover = live * (-np.expm1(-dt_s / PARAMETERS["turnover_s"])) * active
    live -= turnover
    litter = dead * (-np.expm1(-dt_s / (365. * 86400.))) * active + turnover
    dead -= litter - turnover
    capacity = area * PARAMETERS["carrying_carbon_kg_m2"]
    thermal = np.clip(1. - np.abs(temperature - 20.) / 25., 0., 1.)
    potential = (area * PARAMETERS["growth_carbon_kg_m2_s"] * dt_s * thermal
                 * moisture * stress * np.clip(1. - live / capacity, 0., 1.) * active)
    potential = np.minimum(potential, np.maximum(capacity - live, 0.))
    uptake = field(forcing, "plant_nutrient_uptake_kg", shape) * (dt_s > 0.)
    growth = np.minimum(potential, uptake / PARAMETERS["nutrient_kg_per_carbon_kg"])
    assimilated = growth * PARAMETERS["nutrient_kg_per_carbon_kg"]
    released_fraction = np.divide(burned + litter, pools["biomass_carbon_kg"] + pools["dead_carbon_kg"],
                                 out=np.zeros(shape), where=(pools["biomass_carbon_kg"] + pools["dead_carbon_kg"]) > 0.)
    released_nutrient = pools["plant_nutrient_kg"] * np.minimum(released_fraction, 1.)
    nutrient_return = uptake - assimilated + released_nutrient
    live += growth
    disturbance = np.maximum(fire_fraction, (-np.expm1(-mortality_rate * dt_s)) * active)
    remembered = np.maximum(pools["disturbance_fraction"] * np.exp(-dt_s / (365. * 86400.)), disturbance)
    remembered = np.where(active, remembered, pools["disturbance_fraction"])
    age = np.where(active, (pools["age_s"] + dt_s) * (1. - disturbance), pools["age_s"])
    cover = np.clip(live / capacity, 0., 1.)
    output = {"biomass_carbon_kg": live, "dead_carbon_kg": dead,
              "char_carbon_kg": pools["char_carbon_kg"] + char,
              "plant_nutrient_kg": pools["plant_nutrient_kg"] + assimilated - released_nutrient,
              "age_s": age, "disturbance_fraction": remembered}
    initial = sum(float(pools[k].sum()) for k in ("biomass_carbon_kg", "dead_carbon_kg", "char_carbon_kg"))
    final = sum(float(output[k].sum()) for k in ("biomass_carbon_kg", "dead_carbon_kg", "char_carbon_kg"))
    ledger = {"initial_carbon_kg": initial, "photosynthesis_carbon_kg": float(growth.sum()),
              "fire_atmosphere_carbon_kg": float(atmosphere.sum()),
              "soil_litter_carbon_kg": float(litter.sum()), "final_carbon_kg": final}
    ledger["carbon_residual_kg"] = initial + ledger["photosynthesis_carbon_kg"] - final - float((atmosphere + litter).sum())
    ledger["nutrient_input_kg"] = float(uptake.sum())
    ledger["soil_nutrient_return_kg"] = float(nutrient_return.sum())
    ledger["nutrient_residual_kg"] = float((pools["plant_nutrient_kg"] + uptake - output["plant_nutrient_kg"] - nutrient_return).sum())
    return {"state": output, "fluxes": {"photosynthesis_carbon_kg": growth,
            "fire_atmosphere_carbon_kg": atmosphere, "litter_carbon_kg": litter,
            "nutrient_assimilated_kg": assimilated, "plant_nutrient_return_kg": nutrient_return,
            "cover_fraction": cover, "root_cohesion_pa": cover * PARAMETERS["root_cohesion_full_pa"],
            "manning_n": PARAMETERS["bare_manning_n"] + cover * PARAMETERS["vegetated_manning_increment"]},
            "ledger": ledger, "metadata": metadata(ALGORITHM, context, dt_s,
            ["declared functional vegetation, no species competition or fire spread; explicit hazards",
             "nutrient uptake must be debited once from the soil process; carbon litter returned once"], PARAMETERS.copy())}


initialize = initialize_succession
step = advance_succession
