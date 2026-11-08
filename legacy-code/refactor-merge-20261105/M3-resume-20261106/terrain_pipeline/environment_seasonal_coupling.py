"""G3/G4 -> existing G7 snow -> existing G5 bucket, with single inventory owners."""
from copy import deepcopy
from dataclasses import asdict, replace
import math

import numpy as np

from terrain_pipeline.environment_context import array
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.regional_surface_forcing import advance_soil
from terrain_pipeline.seasonal_snow_ice import SnowParameters, advance_snow_ice
from terrain_pipeline.surface_rivers import metric_pet_et

ALGORITHM = "finite-environment-seasonal-coupling-v1"
ALGORITHM_V2 = "finite-environment-seasonal-coupling-v2"
ALGORITHMS = (ALGORITHM, ALGORITHM_V2)
NETWORK_ALGORITHM = "environment-saved-network-frozen-v1"


def is_seasonal(product):
    return product.get("algorithm") in ALGORITHMS


def _climate():
    from terrain_pipeline import environment_climate_driver
    return environment_climate_driver


def driver_slices(context, driver):
    shape = np.asarray(context["height_m"]).shape
    origin = context["origin_native_xz"]
    base = driver["metadata"]["origin_native_xz"]
    extent = driver["metadata"]["shape_zx"]
    col, row = int(origin[0] - base[0]), int(origin[1] - base[1])
    if row < 0 or col < 0 or row + shape[0] > extent[0] or col + shape[1] > extent[1]:
        raise ValueError("product window must stay inside the pinned climate support")
    return slice(row, row + shape[0]), slice(col, col + shape[1])


def initialize(product, driver, climate_state=None, parameters=None, *, material_source, version=1):
    climate = _climate()
    climate.validate_climate_driver(driver)
    config = deepcopy(parameters or {})
    if set(config) - {"runoff", "pet", "snow", "initial_swe_mm", "initial_swe_source", "initial_time_s"}:
        raise ValueError("unsupported seasonal configuration")
    initial_time = float(config.get("initial_time_s", 0. if climate_state is None else climate_state["metadata"]["time_s"]))
    if not math.isfinite(initial_time) or initial_time < 0.:
        raise ValueError("finite nonnegative seasonal initial physical time required")
    product["time_s"] = initial_time
    climate_state = climate.initial_climate_state(driver, time_s=initial_time) if climate_state is None else climate_state
    climate.validate_climate_state(climate_state, driver)
    if climate_state["metadata"]["time_s"] != product["time_s"]:
        raise ValueError("climate and environment physical clocks must match")
    window = driver_slices(product["context"], driver)
    ctx = product["context"]
    shape = ctx["height_m"].shape
    if float(ctx["spacing_m"]) != 30.:
        raise ValueError("seasonal mode requires native 30m water accounts")
    if driver["metadata"].get("world_seed", 20261020) != ctx["world_seed"]:
        raise ValueError("climate and environment world seeds must match")
    validate_source_binding(product, driver)
    runoff = RunoffParameters(**config.get("runoff", {}))
    pet = metric_pet_et.PetEtParameters(runoff=runoff, **config.get("pet", {}))
    snow_values = dict(config.get("snow", {}))
    snow_values["phase_parameters"] = pet
    snow_values.setdefault("freezing_threshold_c", pet.freezing_threshold_c)
    snow = SnowParameters(**snow_values)
    active = ctx["valid_mask"] & ~ctx["ocean_mask"] & ~ctx["protected_mask"]
    swe = array(config.get("initial_swe_mm", 0.), shape, "initial_swe_mm") * active
    if np.any(swe > snow.max_swe_mm):
        raise ValueError("initial SWE exceeds declared ceiling")
    source = config.get("initial_swe_source", "declared_zero_no_observed_snow_initialization")
    if swe.any() and (not isinstance(source, str) or not source.strip() or "initial_swe_source" not in config):
        raise ValueError("nonzero initial snow requires an explicit initial_swe_source")
    if np.any(product["states"]["frozen_ground"]["snow_swe_m"]):
        raise ValueError("G7 owns seasonal snow; G12 initial snow_swe_m must be zero")
    if np.any(product["states"]["soil_chemistry"]["water_m3"] / .9 > runoff.soil_capacity_mm):
        raise ValueError("initial chemistry soil water exceeds G5 capacity")
    product["algorithm"] = ALGORITHM if version == 1 else ALGORITHM_V2
    product["seasonal"] = {
        "climate_driver": deepcopy(driver), "climate_state": deepcopy(climate_state),
        "material_source": deepcopy(material_source),
        "snow_swe_mm": swe, "fast_mm": np.full(shape, runoff.initial_fast_mm) * active,
        "slow_mm": np.full(shape, runoff.initial_slow_mm) * active,
        "pending_et_kg": np.zeros(tuple(driver["metadata"]["shape_zx"])), "initial_swe_source": source,
        "initial_time_s": initial_time,
        "runoff_parameters": asdict(runoff), "pet_parameters": asdict(pet),
        "snow_parameters": snow.identity(),
        "kernel_sources": metric_pet_et._source_identities(),
        "network_policy": "frozen_saved_receiver_and_height; derived bed changes are diagnostics",
        "soil_water_owner": "states.soil_chemistry.water_m3; G5 fast/slow are separate inventories",
        "ground_water_owner": "G12 liquid/ground ice are separately declared thermal-layer stocks; no rainfall partition",
        "temperature_contract": "G3 monthly-mean integral on real interval, not measured short-time temperature",
        "pet_policy": "existing monthly temperature-index PET capped by radiation evaporation energy",
        "G2_status": "native-anchor G2 hardness/solubility drive G9; bedrock porosity read-only; permeability/layer geometry pending",
    }
    product["parameters"]["rain_partition"] = "G7 phase once; liquid enters existing G5; release enters saved network once"
    product["limitations"].extend([
        "seasonal mode uses declared initial SWE, never fabricated cold/warm temperatures",
        "G5 slow store owns percolation; it is not also injected into groundwater",
        "seasonal mode freezes saved water geometry and receiver; bed changes are diagnostic only",
        "G7 degree-day melt has its own empirical energy closure, not a complete radiation melt model",
        "seasonal mode excludes soil/coast exchange packets; coastal river-mouth exchange remains active",
        "G2 extended permeability and layer geometry remain pending; sampled bedrock porosity does not replace regolith porosity",
    ])
    if version == 2:
        from terrain_pipeline.environment_land_cover_coupling import assess
        product["seasonal"]["land_cover"] = assess(product)
        product["seasonal"]["land_cover_policy"] = "allocated G9 soil -> G6 -> G15 actual growth support; parent potential separate"
    return product


def advance_driver(product, forcing, dt_s):
    if not 0. < dt_s <= 3600.:
        raise ValueError("seasonal physical interval must be positive and at most 3600s")
    if {"rainfall_m_s", "air_temperature_c"} & set(forcing):
        raise ValueError("seasonal rain and temperature come only from the pinned climate driver")
    seasonal = product["seasonal"]
    request = deepcopy(forcing.get("climate", {}))
    if not isinstance(request, dict) or set(request) - {"external_inflow_kg_per_s", "wind_speed_m_s", "uplift_gain"}:
        raise ValueError("unsupported seasonal climate boundary fields")
    if "external_inflow_kg_per_s" not in request:
        raise ValueError("seasonal climate requires an explicitly declared external_inflow_kg_per_s boundary")
    request = {"wind_speed_m_s": 5., "uplift_gain": 1., **request}
    if np.any(np.asarray(forcing.get("soil_chemistry", {}).get("drainage_m3_s", 0.))):
        raise ValueError("seasonal soil drainage is owned by G5 percolation")
    if np.any(np.asarray(forcing.get("coastal_exchange", {}).get("soil_exchange_m3_s", 0.))):
        raise ValueError("seasonal soil/coast exchange packets are outside this mode")
    if np.any(product["pending_packets"]["soil_water_m3"]) or np.any(product["pending_packets"]["soil_salt_kg"]):
        raise ValueError("seasonal mode cannot consume external coastal soil packets")
    recycled = seasonal["pending_et_kg"].copy()
    state, driving = _climate().advance_climate_driver(
        seasonal["climate_driver"], seasonal["climate_state"], product["time_s"] + dt_s,
        et_recycle_kg=recycled, **request)
    seasonal["climate_state"] = state
    seasonal["pending_et_kg"] = np.zeros_like(recycled)
    window = driver_slices(product["context"], seasonal["climate_driver"])
    result = deepcopy(forcing)
    for key in ("rainfall_m_s", "air_temperature_c"):
        result[key] = np.asarray(driving[key])[window].copy()
    result["wind_x_m_s"] = np.asarray(seasonal["climate_driver"]["arrays"]["wind_bearing_x"])[window] * float(request.get("wind_speed_m_s", 5.))
    result["wind_z_m_s"] = np.asarray(seasonal["climate_driver"]["arrays"]["wind_bearing_z"])[window] * float(request.get("wind_speed_m_s", 5.))
    return result, driving, recycled


def snow_and_bucket(product, forcing, dt_s, radiation, infiltration_factor):
    seasonal, ctx = product["seasonal"], product["context"]
    shape = ctx["height_m"].shape
    active = ctx["valid_mask"] & ~ctx["ocean_mask"] & ~ctx["protected_mask"]
    area = float(ctx["spacing_m"]) ** 2
    edges = np.array([product["time_s"], product["time_s"] + dt_s])
    runoff = RunoffParameters(**seasonal["runoff_parameters"])
    pet_values = dict(seasonal["pet_parameters"])
    pet_values.pop("runoff")
    pet = metric_pet_et.PetEtParameters(runoff=runoff, **pet_values)
    snow_values = dict(seasonal["snow_parameters"])
    snow_values["phase_parameters"] = pet
    snow = advance_snow_ice(
        swe_start_mm=seasonal["snow_swe_mm"].ravel(),
        temperature_c=np.asarray(forcing["air_temperature_c"]).reshape(1, -1),
        precip_mm=(np.asarray(forcing["rainfall_m_s"]) * dt_s * 1000. * active).reshape(1, -1),
        time_edges_s=edges, x_m=ctx["node_x_m"].ravel(), z_m=ctx["node_z_m"].ravel(),
        temperature_source="declared_interval", parameters=SnowParameters(**snow_values))
    seasonal["snow_swe_mm"] = snow["arrays"]["swe_edge_mm"][-1].reshape(shape)
    window = driver_slices(ctx, seasonal["climate_driver"])
    monthly = seasonal["climate_driver"]["arrays"]["monthly_temperature_c"][:, window[0], window[1]].reshape(12, -1)
    pet_mm = metric_pet_et.interval_pet_mm(monthly, edges, pet)[0].reshape(shape)
    limited_pet_mm = np.minimum(pet_mm, radiation["fluxes"]["potential_evaporation_m"] * 1000.) * active
    liquid = snow["arrays"]["liquid_to_land_mm"][0].reshape(shape)
    states = np.stack((product["states"]["soil_chemistry"]["water_m3"] * 1000. / area,
                       seasonal["fast_mm"], seasonal["slow_mm"])).reshape(3, -1)
    rates = limited_pet_mm.ravel() * 3600. / dt_s
    capacity = runoff.infiltration_capacity_mm_h * np.asarray(infiltration_factor).ravel() * active.ravel()
    groups, inverse = np.unique(np.stack((rates, capacity), axis=1), axis=0, return_inverse=True)
    updated = np.empty_like(states)
    arrays = {key: np.zeros(states.shape[1]) for key in
              ("infiltration_mm", "percolation_mm", "actual_et_mm", "release_mm", "fast_release_mm", "slow_release_mm")}
    for index, (et_rate, infiltration_capacity) in enumerate(groups):
        mask = inverse == index
        params = replace(runoff, potential_et_mm_h=float(et_rate),
                         infiltration_capacity_mm_h=float(infiltration_capacity))
        next_state, release, et, _, fluxes = advance_soil(
            liquid.ravel()[mask] * 3600. / dt_s, states[:, mask], dt_s=dt_s,
            parameters=params, return_fluxes=True)
        updated[:, mask] = next_state
        arrays["infiltration_mm"][mask] = fluxes["infiltration_mm"]
        arrays["percolation_mm"][mask] = fluxes["percolation_mm"]
        arrays["actual_et_mm"][mask] = et
        arrays["release_mm"][mask] = release
        arrays["fast_release_mm"][mask] = fluxes["fast_release_mm"]
        arrays["slow_release_mm"][mask] = fluxes["slow_release_mm"]
    seasonal["fast_mm"] = updated[1].reshape(shape)
    seasonal["slow_mm"] = updated[2].reshape(shape)
    volumes = {key.removesuffix("_mm") + "_m3": value.reshape(shape) * area / 1000.
               for key, value in arrays.items()}
    volumes["soil_end_m3"] = updated[0].reshape(shape) * area / 1000.
    volumes["pet_m3"] = pet_mm * area / 1000.
    volumes["energy_limited_pet_m3"] = limited_pet_mm * area / 1000.
    snow_result = {"fluxes": {key.removesuffix("_mm") + "_m3": value[0].reshape(shape) * area / 1000.
                              for key, value in snow["arrays"].items() if key != "swe_edge_mm"},
                   "ledger": snow["ledger_mm"], "metadata": snow["metadata"]}
    snow_result["metadata"]["temperature_source_detail"] = seasonal["temperature_contract"]
    return snow_result, volumes


def net_water(entries):
    get = lambda key: float(entries.get(key, 0.))
    return (get("atmosphere_inflow_m3") - get("atmosphere_outflow_m3")
            - get("precipitation_unmodelled_export_m3") - get("sublimation_m3")
            + get("ocean_water_input_m3") - get("window_water_export_m3") - get("pumping_m3")
            - get("external_hydraulic_water_m3"))


def validate_source_binding(product, driver):
    source, climate_source = product["sources"], driver["metadata"]["source"]
    for environment_key, climate_key in (("source_world_identity", "world_identity"),
                                          ("registry_sha256", "registry_sha256"),
                                          ("manifest_sha256", "manifest_sha256")):
        if environment_key not in source or source[environment_key] != climate_source.get(climate_key):
            raise ValueError("climate and environment saved-source binding mismatch: " + environment_key)
    window = driver_slices(product["context"], driver)
    bed = product["context"].get("source_height_m", product["context"]["height_m"])
    if not np.array_equal(driver["arrays"]["elevation_m"][window], bed):
        raise ValueError("climate must use the same saved TD-derived bed as the environment network")


def validate(product):
    seasonal = product["seasonal"]
    climate = _climate()
    climate.validate_climate_driver(seasonal["climate_driver"])
    climate.validate_climate_state(seasonal["climate_state"], seasonal["climate_driver"])
    if seasonal["climate_state"]["metadata"]["time_s"] != product["time_s"]:
        raise ValueError("persistent climate/environment clocks disagree")
    driver_slices(product["context"], seasonal["climate_driver"])
    validate_source_binding(product, seasonal["climate_driver"])
    from terrain_pipeline.environment_material_source import validate_material_source
    validate_material_source(seasonal["material_source"], product["context"])
    shape = product["context"]["height_m"].shape
    for key in ("snow_swe_mm", "fast_mm", "slow_mm"):
        array(seasonal[key], shape, key)
    array(seasonal["pending_et_kg"], tuple(seasonal["climate_driver"]["metadata"]["shape_zx"]), "pending_et_kg")
    if np.any(product["states"]["frozen_ground"]["snow_swe_m"]):
        raise ValueError("persistent G7/G12 snow ownership overlaps")
    if product["algorithm"] == ALGORITHM_V2:
        from terrain_pipeline.environment_land_cover_coupling import validate as validate_land_cover
        validate_land_cover(product)
