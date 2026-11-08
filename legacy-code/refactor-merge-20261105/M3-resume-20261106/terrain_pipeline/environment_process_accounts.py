"""Physical inventory totals shared by coupling and persistent validation."""
import numpy as np


def inventory_totals(product):
    s, packets = product["states"], product["pending_packets"]
    area = float(product["context"]["spacing_m"]) ** 2
    def total(module, names):
        return sum(float(np.asarray(s[module][name]).sum()) for name in names)
    result = {"water_m3": total("groundwater", ("groundwater_water_m3", "surface_water_m3"))
            + total("soil_chemistry", ("water_m3",)) + total("coastal_exchange", ("water_m3",))
            + area * total("frozen_ground", ("liquid_water_m", "ground_ice_m", "snow_swe_m"))
            + float(packets["soil_water_m3"].sum()),
            "solid_m3": total("mass", ("bedrock_solid_m3", "regolith_solid_m3", "soil_solid_m3",
                                         "hillslope_deposit_solid_m3", "river_sediment_solid_m3"))
            + total("aeolian", ("loose_solid_m3", "airborne_solid_m3"))
            + total("volcanism", ("mobile_lava_m3", "airborne_ash_m3", "deposited_lava_m3", "deposited_ash_m3"))
            + total("coastal_exchange", ("bed_solid_m3",)),
            "carbon_kg": total("soil_chemistry", ("organic_carbon_kg",))
            + total("succession", ("biomass_carbon_kg", "dead_carbon_kg", "char_carbon_kg"))
            + float(packets["litter_carbon_kg"].sum()),
            "salt_kg": total("soil_chemistry", ("salt_dissolved_kg", "salt_solid_kg"))
            + total("coastal_exchange", ("salt_kg",)) + float(packets["soil_salt_kg"].sum() + packets["subsurface_salt_kg"].sum()),
            "nutrient_kg": total("soil_chemistry", ("nutrient_kg", "organic_nutrient_kg"))
            + total("succession", ("plant_nutrient_kg",)) + float(packets["plant_nutrient_return_kg"].sum() + packets["subsurface_nutrient_kg"].sum())}
    if "seasonal" in product:
        seasonal = product["seasonal"]
        result["water_m3"] += area / 1000. * sum(float(seasonal[key].sum())
                                                  for key in ("snow_swe_mm", "fast_mm", "slow_mm"))
        result["water_m3"] += (float(seasonal["climate_state"]["arrays"]["vapour_kg"].sum())
                               + float(seasonal["pending_et_kg"].sum())) / 1000.
    return result

