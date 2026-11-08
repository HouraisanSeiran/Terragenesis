"""Registry of environment default values currently hard-coded across the pipeline.

Every entry records the value as it is *today*, where it lives, and its status. Nothing
here changes any default: pinned files (``rainfall_runoff``, ``geography_physical``,
``hydrology_seasonal`` ...) keep their literals byte for byte. New callers should read a
value from this registry and pass it explicitly. ``tests/test_environment_defaults.py``
checks each entry against the live value in its source file, so drift is detected.

Status: ``declared`` = chosen by the authors for the fictional world, ``uncalibrated`` =
never fitted to observations. All entries are both unless stated otherwise.
Units are SI unless the unit string says otherwise (mm values keep the unit of their
source module).
"""
from dataclasses import dataclass

REGISTRY_ID = "environment-defaults-v1"


@dataclass(frozen=True)
class Default:
    value: float
    unit: str
    source: str            # file:symbol where the live literal sits
    status: str = "declared/uncalibrated"
    pinned: bool = False   # source file is named by verification evidence (sha-index pin > 0)
    note: str = ""


def _d(value, unit, source, pinned=False, note=""):
    return Default(value, unit, source, "declared/uncalibrated", pinned, note)


DEFAULTS = {
    # --- G5 bucket / runoff (rainfall_runoff.RunoffParameters, pinned 235) ---
    "runoff.infiltration_capacity_mm_h": _d(15.0, "mm/h", "rainfall_runoff.py:RunoffParameters", True),
    "runoff.soil_capacity_mm": _d(150.0, "mm", "rainfall_runoff.py:RunoffParameters", True,
                                  "differs from seasonal.soil_capacity_mm (120); both kept"),
    "runoff.potential_et_mm_h": _d(0.15, "mm/h", "rainfall_runoff.py:RunoffParameters", True),
    "runoff.percolation_mm_h": _d(1.0, "mm/h", "rainfall_runoff.py:RunoffParameters", True),
    "runoff.fast_tau_s": _d(3600.0, "s", "rainfall_runoff.py:RunoffParameters", True),
    "runoff.slow_tau_s": _d(259200.0, "s", "rainfall_runoff.py:RunoffParameters", True),
    "runoff.initial_soil_mm": _d(30.0, "mm", "rainfall_runoff.py:RunoffParameters", True),
    # --- seasonal hydrology (hydrology_seasonal.SeasonalConfig, pinned 1) ---
    "seasonal.soil_capacity_mm": _d(120.0, "mm", "hydrology_seasonal.py:SeasonalConfig", True),
    "seasonal.soil_drainage_days": _d(45.0, "day", "hydrology_seasonal.py:SeasonalConfig", True),
    "seasonal.climate_noise_scale_m": _d(60000.0, "m", "hydrology_seasonal.py:SeasonalConfig", True),
    # --- PET: two copies of the same pair (seasonal config and metric_pet_et) ---
    "pet.base_mm_per_day": _d(0.5, "mm/day", "hydrology_seasonal.py:SeasonalConfig; "
                              "surface_rivers/metric_pet_et.py:PetEtParameters", True,
                              "same value in both files; metric_pet_et is not pinned"),
    "pet.temperature_mm_per_day_c": _d(0.12, "mm/day/degC", "hydrology_seasonal.py:SeasonalConfig; "
                                       "surface_rivers/metric_pet_et.py:PetEtParameters", True),
    "pet.freezing_threshold_c": _d(0.0, "degC", "surface_rivers/metric_pet_et.py:PetEtParameters"),
    # --- temperature lapse rate (single definition) ---
    "climate.lapse_rate_c_per_m": _d(-0.0065, "degC/m", "surface_rivers/metric_noise_forcing.py:"
                                     "NoiseClimateParameters"),
    # --- radiation (environment_radiation step defaults) ---
    "radiation.solar_constant_w_m2": _d(1000.0, "W/m2", "environment_radiation.py:step",
                                        note="effective clear-sky value, not the 1361 W/m2 TOA constant"),
    "radiation.atmospheric_transmission": _d(0.7, "1", "environment_radiation.py:step"),
    "radiation.evaporation_energy_fraction": _d(0.3, "1", "environment_radiation.py:step"),
    "radiation.albedo": _d(0.2, "1", "environment_radiation.py:step (forcing default)"),
    "radiation.day_seconds": _d(86400.0, "s", "environment_radiation.py:step"),
    "radiation.year_days": _d(365.0, "day", "environment_radiation.py:step"),
    # --- frozen ground ---
    "frozen.latent_heat_j_m3": _d(3.34e8, "J/m3", "environment_frozen_ground.py:LATENT_J_M3"),
    "frozen.soil_heat_capacity_j_m2_k": _d(2.0e6, "J/m2/K", "environment_frozen_ground.py:step"),
    "frozen.air_exchange_w_m2_k": _d(5.0, "W/m2/K", "environment_frozen_ground.py:step"),
    "frozen.snow_insulation_per_m_swe": _d(50.0, "1/m", "environment_frozen_ground.py:step"),
    "frozen.thermal_diffusivity_m2_s": _d(5.0e-7, "m2/s", "environment_frozen_ground.py:step"),
    "frozen.soil_depth_m": _d(2.0, "m", "environment_frozen_ground.py:step"),
    # --- porosity (two live copies of 0.35) ---
    "regolith.porosity": _d(0.35, "1", "environment_mass_processes.py:initial_state"),
    "coastal.bed_porosity": _d(0.35, "1", "environment_coastal_exchange.py:PARAMETERS"),
    # --- soil water capacity of land cover ---
    "land_cover.available_water_fraction": _d(0.15, "1", "environment_land_cover.py:138"),
    # --- aeolian / volcanism ---
    "aeolian.threshold_wind_m_s": _d(5.0, "m/s", "environment_aeolian.py:step"),
    "aeolian.entrainment_rate_s_m": _d(1.0e-5, "s/m", "environment_aeolian.py:step"),
    "aeolian.settling_time_s": _d(600.0, "s", "environment_aeolian.py:step"),
    "aeolian.solid_fraction": _d(0.6, "1", "environment_aeolian.py:step"),
    "volcanism.lava_heat_j_m3": _d(2.0e9, "J/m3", "environment_volcanism.py:step"),
    "volcanism.cooling_time_s": _d(3600.0, "s", "environment_volcanism.py:step"),
    "volcanism.lava_speed_m_s": _d(0.05, "m/s", "environment_volcanism.py:step"),
    "volcanism.ash_settling_time_s": _d(1800.0, "s", "environment_volcanism.py:step"),
    "volcanism.ash_solid_fraction": _d(0.5, "1", "environment_volcanism.py:step"),
    # --- roughness (Manning n, s/m^(1/3)) ---
    "succession.bare_manning_n": _d(0.025, "s/m^(1/3)", "environment_succession.py:PARAMETERS"),
    "succession.vegetated_manning_increment": _d(0.09, "s/m^(1/3)", "environment_succession.py:PARAMETERS"),
    # --- slope stability constants inside environment_mass_processes.step ---
    "mass.bulk_density_kg_m3": _d(1800.0, "kg/m3", "environment_mass_processes.py:step"),
    "mass.repose_angle_deg": _d(34.0, "deg", "environment_mass_processes.py:step (forcing default)"),
    "mass.gravity_m_s2": _d(9.80665, "m/s2", "environment_mass_processes.py:step"),
    # --- groundwater ---
    "groundwater.specific_yield": _d(0.2, "1", "environment_groundwater.py:step (forcing default)"),
    "groundwater.aquifer_base_depth_m": _d(10.0, "m", "environment_groundwater.py:step (height - 10)"),
}

# Process-level parameter dicts that already exist as module constants: registered by
# reference name so tests can compare them with the live dictionaries.
PROCESS_PARAMETER_SOURCES = {
    "coastal_exchange": "environment_coastal_exchange.PARAMETERS",
    "habitat": "environment_habitat.PARAMETERS",
    "soil_chemistry": "environment_soil_chemistry.PARAMETERS",
    "succession": "environment_succession.PARAMETERS",
}


def get(name):
    """Return the registered value (a plain float)."""
    return DEFAULTS[name].value


def group(prefix):
    """Return ``{short_name: value}`` for all entries under ``prefix.``."""
    start = prefix + "."
    return {k[len(start):]: v.value for k, v in DEFAULTS.items() if k.startswith(start)}


def describe():
    return {name: {"value": e.value, "unit": e.unit, "source": e.source, "status": e.status,
                   "pinned": e.pinned, "note": e.note} for name, e in sorted(DEFAULTS.items())}
