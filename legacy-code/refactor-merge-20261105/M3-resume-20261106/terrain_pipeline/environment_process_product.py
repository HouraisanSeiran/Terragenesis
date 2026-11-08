"""Persistent finite dynamic environment processes on an immutable saved source.

This orchestrates physical-time inventories. The separate environment_world_product
assembles static sampled fields and is not advanced or changed by this module.
"""
from copy import deepcopy
import math

import numpy as np

from terrain_pipeline import environment_mass_processes as mass
from terrain_pipeline import environment_groundwater as groundwater
from terrain_pipeline import environment_network_transition as transition
from terrain_pipeline import environment_radiation as radiation
from terrain_pipeline import environment_frozen_ground as frozen
from terrain_pipeline import environment_volcanism as volcanism
from terrain_pipeline import environment_aeolian as aeolian
from terrain_pipeline import environment_soil_chemistry as chemistry
from terrain_pipeline import environment_succession as succession
from terrain_pipeline import environment_coastal_exchange as coast
from terrain_pipeline import environment_habitat as habitat
from terrain_pipeline import environment_process_storage as storage
from terrain_pipeline import environment_seasonal_coupling as seasonal_api
from terrain_pipeline.environment_process_source import context_from_store
from terrain_pipeline.environment_process_storage import SCHEMA, ALGORITHM, MAX_CELLS, PACKETS, query_product
from terrain_pipeline.environment_process_accounts import inventory_totals
from terrain_pipeline.environment_context import array, context_arrays

MODULES = {"radiation": radiation, "frozen_ground": frozen, "volcanism": volcanism,
           "aeolian": aeolian, "soil_chemistry": chemistry, "succession": succession,
           "coastal_exchange": coast, "habitat": habitat}
FORCING_KEYS = {
    "radiation": {"latitude_deg", "longitude_deg", "albedo", "time_s"},
    "volcanism": {"lava_input_m3", "ash_input_m3", "geothermal_w_m2", "wind_x_m_s", "wind_z_m_s"},
    "frozen_ground": set(),
    "aeolian": {"wind_x_m_s", "wind_z_m_s"},
    "mass": {"weathering_parameters", "soil_request_solid_m3", "transport_fraction_per_s", "repose_angle_deg"},
    "groundwater": {"specific_yield", "aquifer_base_m", "lateral_conductance_m2_s", "surface_conductance_m2_s", "surface_stage_m", "pumping_request_m3"},
    "soil_chemistry": {"drainage_m3_s", "nutrient_input_kg_s", "litter_nutrient_kg"},
    "succession": {"fire_hazard_s", "disturbance_hazard_s"},
    "coastal_exchange": {"tide_amplitude_m", "tide_period_s", "mean_sea_level_m", "tide_phase_rad", "wave_height_m", "wave_direction_xz", "ocean_salinity_kg_m3", "soil_exchange_m3_s"},
    "habitat": set(),
}


def _land_context(context):
    # A local view of the owned step context; only support and receivers differ.
    result = dict(context)
    land = context["valid_mask"] & ~context["ocean_mask"]
    result["valid_mask"] = land
    rec = context["receiver"].copy()
    donors = np.flatnonzero(rec.ravel() >= 0)
    rec.ravel()[donors[~land.ravel()[rec.ravel()[donors]]]] = -1
    rec[~land] = -1
    result["receiver"] = rec
    return result


def initialize(context, sources=None, initial=None, *, mode="explicit", climate_driver=None,
               climate_state=None, seasonal_parameters=None):
    if mode not in ("explicit", "explicit-v2", "seasonal", "seasonal-v2"):
        raise ValueError("environment mode must be explicit, explicit-v2, seasonal or seasonal-v2")
    if mode in ("explicit", "explicit-v2") and any(value is not None for value in (climate_driver, climate_state, seasonal_parameters)):
        raise ValueError("climate driver/state/config require seasonal mode")
    context = deepcopy(context)
    height, masks, mesh, _ = context_arrays(context, 1.)
    if height.size > MAX_CELLS:
        raise ValueError("dynamic product exceeds finite cell budget")
    if "node_x_m" not in context:
        context["node_x_m"] = mesh.node_x_m.reshape(height.shape).copy()
        context["node_z_m"] = mesh.node_z_m.reshape(height.shape).copy()
    context.setdefault("external_receiver_mask", np.zeros(height.shape, bool))
    context.setdefault("source_terminal_mask", context["receiver"] < 0)
    context.setdefault("routing_policy", "source_terminal_flood")
    declarations = deepcopy(initial or {})
    material_source = None
    if mode in ("seasonal", "seasonal-v2"):
        if {"bed_hardness", "solubility"} & set(declarations.get("mass", {})):
            raise ValueError("seasonal G2 sampled bed_hardness/solubility cannot be overridden by initial.mass")
        from terrain_pipeline.environment_material_source import prepare_material_source, material_mass_inputs
        material_source = prepare_material_source(context)
        context.update(material_mass_inputs(material_source, context))
        sources = deepcopy(sources or {"kind": "explicit_synthetic_context"})
        sources["solubility"] = "same-world G2 properties_at at native account anchors; original rock-table solubility"
        sources["porosity"] = "regolith engineering porosity0.35; G2 bedrock_porosity is a separate read-only property"
    land_ctx = _land_context(context)
    land = land_ctx["valid_mask"] & ~land_ctx["protected_mask"]
    mass_args = {"bed_hardness": context.get("bed_hardness", .5), "solubility": context.get("solubility", .2)}
    mass_args.update(declarations.get("mass", {}))
    groundwater_args = {name: array(value, height.shape, name) * land
                        for name, value in declarations.get("groundwater", {}).items()}
    states = {"mass": mass.initial_state(land_ctx, **mass_args),
              "groundwater": groundwater.initial_state(land_ctx, **groundwater_args)}
    for name, module in MODULES.items():
        ctx = context if name in ("radiation", "coastal_exchange", "aeolian", "habitat") else land_ctx
        args = deepcopy(declarations.get(name, {}))
        # Land-only process initializers have differing mask conventions; enforce
        # zero physical stocks over oceans before their first transition.
        states[name] = module.initialize(ctx, **args)
        if name in ("frozen_ground", "soil_chemistry", "succession", "habitat"):
            for key in states[name]:
                states[name][key] = np.where(land, states[name][key], 0.)
    states["network_transition"] = transition.initial_state(context)
    product = {"schema": SCHEMA, "algorithm": ALGORITHM, "context": context, "states": states,
               "results": {}, "sources": deepcopy(sources or {"kind": "explicit_synthetic_context"}),
               "initial_declarations": declarations, "time_s": 0., "step_index": 0,
               "parameters": {"status": "declared_engineering_scenario_uncalibrated",
                              "rain_partition": "0.2 frozen; infiltration_factor*(0.6 soil+0.2 aquifer); remainder runoff",
                              "surface_packet_speed_m_s": ".5*.025/manning_n; one delivered graph edge per step",
                              "aquifer_exchange_roughness": "surface conductance multiplied by .025/manning_n",
                              "process_parameters": {}},
               "pending_packets": {key: np.zeros(height.shape) for key in PACKETS},
               "cumulative_ledger": {}, "last_transfers": {}, "last_budget": {}, "last_energy_budget": {}, "forcing_history": [],
               "limitations": ["finite engineering mechanism coupling, not calibrated natural-process certification",
                               "saved representative Q is never used as local rain or reinjected water",
                               "land soil/frozen/GW reservoirs are separately declared control-volume stocks",
                               "leached salt/nutrient stay in explicit pending subsurface stores; aquifer solute transport not implemented",
                               "network_transition inventories are read-only native-cell accounting views, not additional stores"]}
    if mode in ("seasonal", "seasonal-v2"):
        if climate_driver is None:
            raise ValueError("seasonal mode requires a pinned climate driver")
        seasonal_api.initialize(product, climate_driver, climate_state, seasonal_parameters,
                                material_source=material_source, version=2 if mode == "seasonal-v2" else 1)
    if mode == "explicit-v2":
        product["algorithm"] = storage.EXPLICIT_V2_ALGORITHM
    product["initial_inventory"] = inventory_totals(product)
    return product


def _route_packet(stock, context, dt_s, manning_n):
    """Move each local packet at most one delivered receiver edge per step."""
    shape = stock.shape
    receiver = context["receiver"].ravel()
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    x, z = context["node_x_m"].ravel(), context["node_z_m"].ravel()
    length = np.hypot(x[donors] - x[targets], z[donors] - z[targets])
    fraction = np.minimum(1., .5 * .025 / manning_n.ravel()[donors] * dt_s / length)
    moved = stock.ravel()[donors] * fraction
    updated = stock.copy()
    updated.ravel()[donors] -= moved
    ocean = context["ocean_mask"].ravel()[targets]
    coast_packet = np.zeros(shape)
    np.add.at(coast_packet.ravel(), targets[ocean], moved[ocean])
    np.add.at(updated.ravel(), targets[~ocean], moved[~ocean])
    external = context["external_receiver_mask"] & (context["receiver"] < 0)
    exported = np.where(external, updated, 0.)
    updated -= exported
    return updated, coast_packet, exported


def advance(product, forcing, dt_s):
    """Advance one physical interval; every cross-module packet is debited once."""
    if not np.isfinite(dt_s) or dt_s <= 0.:
        raise ValueError("positive physical dt_s required")
    seasonal_mode = seasonal_api.is_seasonal(product)
    land_cover_mode = product.get("algorithm") == seasonal_api.ALGORITHM_V2
    handoff_mode = land_cover_mode or product.get("algorithm") == storage.EXPLICIT_V2_ALGORITHM
    allowed = set(FORCING_KEYS) | {"rainfall_m_s", "air_temperature_c", "wind_x_m_s", "wind_z_m_s"}
    if seasonal_mode:
        allowed.add("climate")
    if handoff_mode:
        allowed.add("hydraulic_handoff_mask")
    allowed |= {name + "_parameters" for name in ("radiation", "frozen_ground", "volcanism", "aeolian")}
    if set(forcing) - allowed:
        raise ValueError("unsupported product forcing fields: " + str(sorted(set(forcing) - allowed)))
    for name, keys in FORCING_KEYS.items():
        if name in forcing and (not isinstance(forcing[name], dict) or set(forcing[name]) - keys):
            raise ValueError("unsupported or internally coupled forcing fields for " + name)
    handoff_mask = None
    if handoff_mode:
        handoff_mask = np.asarray(forcing.get("hydraulic_handoff_mask", np.zeros_like(product["context"]["valid_mask"])))
        active = product["context"]["valid_mask"] & ~product["context"]["ocean_mask"] & ~product["context"]["protected_mask"]
        if handoff_mask.dtype != bool or handoff_mask.shape != active.shape or np.any(handoff_mask & ~active):
            raise ValueError("hydraulic_handoff_mask must be matching bool active-land support")
    out = deepcopy(product)
    ctx, s = out["context"], out["states"]
    land_ctx = _land_context(ctx)
    shape = ctx["height_m"].shape
    area = float(ctx["spacing_m"]) ** 2
    land = land_ctx["valid_mask"] & ~ctx["protected_mask"]
    before = inventory_totals(out)
    # Each mass transition returns fresh inventory arrays, preserving this snapshot.
    old_mass = s["mass"]
    results, transfers, entries = {}, {}, {}
    f = deepcopy(forcing)
    if seasonal_mode:
        f, climate_driving, recycled_et_kg = seasonal_api.advance_driver(out, forcing, dt_s)
        results["climate"] = {"fluxes": {key: climate_driving[key] for key in
                                         ("rainfall_m_s", "air_temperature_c", "precipitation_mm")},
                              "ledger": climate_driving["ledger"],
                              "metadata": climate_driving["seasonal_source"]}
    def driver(name):
        value = f.get(name, {})
        if not isinstance(value, dict):
            raise ValueError(name + " forcing must be a mapping")
        return deepcopy(value)
    def run(name, module, driving, context, parameters=None):
        if parameters is None:
            result = module.step(s[name], driving, context, dt_s)
        else:
            result = module.step(s[name], driving, context, dt_s, parameters=parameters)
        s[name] = result["state"]
        results[name] = {key: result[key] for key in ("fluxes", "ledger", "metadata")}
        return result
    wind = {"wind_x_m_s": f.get("wind_x_m_s", 0.), "wind_z_m_s": f.get("wind_z_m_s", 0.)}
    vol = run("volcanism", volcanism, {**wind, **driver("volcanism")}, land_ctx, f.get("volcanism_parameters"))
    rad = run("radiation", radiation, {**driver("radiation"), "time_s": out["time_s"]}, ctx, f.get("radiation_parameters"))
    rad["metadata"]["clock_policy"] = "product physical time is authoritative; any declared radiation.time_s is recorded but overridden"
    rain = array(f.get("rainfall_m_s", 0.), shape, "rainfall_m_s") * area * dt_s * land
    infiltration = np.clip(np.divide(s["frozen_ground"]["liquid_water_m"],
        s["frozen_ground"]["liquid_water_m"] + s["frozen_ground"]["ground_ice_m"],
        out=np.ones(shape), where=(s["frozen_ground"]["liquid_water_m"] + s["frozen_ground"]["ground_ice_m"]) > 0.), 0., 1.)
    if seasonal_mode:
        soil_rain, aquifer_rain, frozen_rain, runoff_rain = (np.zeros(shape) for _ in range(4))
    else:
        soil_rain = rain * .6 * infiltration
        aquifer_rain = rain * .2 * infiltration
        frozen_rain = rain * .2
        runoff_rain = rain - soil_rain - aquifer_rain - frozen_rain
    s["frozen_ground"]["liquid_water_m"] += frozen_rain / area
    ice = run("frozen_ground", frozen, {**driver("frozen_ground"),
        "air_temperature_c": f.get("air_temperature_c", 10.),
        "ground_heat_w_m2": rad["fluxes"]["net_ground_heat_w_m2"],
        "geothermal_heat_w_m2": vol["fluxes"]["geothermal_heat_w_m2"]}, land_ctx, f.get("frozen_ground_parameters"))
    if seasonal_mode:
        snow, bucket = seasonal_api.snow_and_bucket(out, f, dt_s, rad, ice["fluxes"]["infiltration_factor"])
        results["seasonal_snow"] = snow
        soil_rain = bucket["infiltration_m3"]
        runoff_rain = bucket["release_m3"]
        results["seasonal_soil"] = {"fluxes": bucket,
            "ledger": {key: float(value.sum()) for key, value in bucket.items()},
            "metadata": {"algorithm": "existing-regional-soil-bucket-seasonal-adapter-v1",
                         "parameters": out["seasonal"]["runoff_parameters"],
                         "phase_policy": "G7 liquid consumed once; no second PET phase decision",
                         "infiltration_policy": "G12 liquid/(liquid+ground ice) scales G5 infiltration capacity"}}
    packets = out["pending_packets"]
    water_packet = soil_rain + packets["soil_water_m3"]
    salt_concentration = np.divide(packets["soil_salt_kg"], water_packet,
                                    out=np.zeros(shape), where=water_packet > 0.)
    soil_driver = driver("soil_chemistry")
    soil_et_m3 = rad["fluxes"]["potential_evaporation_m"] * area
    if seasonal_mode:
        soil_driver["drainage_m3_s"] = bucket["percolation_m3"] / dt_s
        soil_et_m3 = bucket["actual_et_m3"]
    # Coupled nutrient demand is an upper bound; succession returns unused uptake.
    demand = area * succession.PARAMETERS["growth_carbon_kg_m2_s"] * dt_s * succession.PARAMETERS["nutrient_kg_per_carbon_kg"] * land
    soil = run("soil_chemistry", chemistry, {**soil_driver,
        "water_input_m3_s": water_packet / dt_s, "inflow_salinity_kg_m3": salt_concentration,
        "evaporation_m3_s": soil_et_m3 / dt_s,
        "litter_carbon_kg": packets["litter_carbon_kg"],
        "plant_nutrient_return_kg": packets["plant_nutrient_return_kg"],
        "plant_uptake_demand_kg": demand}, land_ctx)
    if seasonal_mode:
        if not np.allclose(s["soil_chemistry"]["water_m3"], bucket["soil_end_m3"], rtol=1.e-12, atol=1.e-10):
            raise ValueError("G5 and sole chemistry soil-water owner diverged")
        window = seasonal_api.driver_slices(ctx, out["seasonal"]["climate_driver"])
        out["seasonal"]["pending_et_kg"][window] = bucket["actual_et_m3"] * 1000.
    packets.update({name: np.zeros(shape) for name in PACKETS[:4]})
    packets["subsurface_salt_kg"] += soil["fluxes"]["salt_leached_kg"]
    packets["subsurface_nutrient_kg"] += soil["fluxes"]["nutrient_leached_kg"]
    moisture = np.clip(s["soil_chemistry"]["water_m3"] / (area * .2), 0., 1.)
    plant_stress = soil["fluxes"]["plant_stress_factor"]
    if land_cover_mode:
        from terrain_pipeline import environment_land_cover_coupling as land_cover
        consumed_land_cover = land_cover.assess(out)
        plant_stress = plant_stress * consumed_land_cover["growth_support_factor"]
        results["land_cover"] = {"fluxes": {key: consumed_land_cover[key] for key in
                                           ("growth_support_factor", "suitability", "soil_thickness_bulk_m", "land_cover_index")},
                                 "ledger": {}, "metadata": consumed_land_cover["adapter"]}
    plant = run("succession", succession, {**driver("succession"),
        "plant_nutrient_uptake_kg": soil["fluxes"]["plant_uptake_kg"],
        "plant_stress_factor": plant_stress,
        "water_available_fraction": moisture, "temperature_c": f.get("air_temperature_c", 10.)}, land_ctx)
    packets["litter_carbon_kg"] = plant["fluxes"]["litter_carbon_kg"].copy()
    packets["plant_nutrient_return_kg"] = plant["fluxes"]["plant_nutrient_return_kg"].copy()
    matter = run("mass", mass, {**driver("mass"), "temperature_c": f.get("air_temperature_c", 10.),
        "moisture": moisture, "bio_activity": plant["fluxes"]["cover_fraction"],
        "root_cohesion_pa": plant["fluxes"]["root_cohesion_pa"]}, land_ctx)
    sand = run("aeolian", aeolian, {**wind, **driver("aeolian"), "water_saturation": moisture,
        "vegetation_cover": plant["fluxes"]["cover_fraction"]}, ctx, f.get("aeolian_parameters"))
    gw = run("groundwater", groundwater, {**driver("groundwater"),
        "recharge_m3": (np.zeros(shape) if seasonal_mode else
                         aquifer_rain + soil["fluxes"]["drainage_m3"] + ice["fluxes"]["snow_meltwater_m"] * area),
        "surface_input_m3": runoff_rain,
        "surface_conductance_m2_s": array(driver("groundwater").get("surface_conductance_m2_s", .001), shape,
            "surface conductance") * .025 / plant["fluxes"]["manning_n"]}, land_ctx)
    if handoff_mode:
        hydraulic_water = np.where(handoff_mask, s["groundwater"]["surface_water_m3"], 0.)
        hydraulic_solid = np.where(handoff_mask, s["mass"]["river_sediment_solid_m3"], 0.)
        s["groundwater"]["surface_water_m3"] -= hydraulic_water
        s["mass"]["river_sediment_solid_m3"] -= hydraulic_solid
        s["mass"]["downstream_delivered_solid_m3"] += hydraulic_solid
        transfers.update(external_hydraulic_water_m3=hydraulic_water, external_hydraulic_solid_m3=hydraulic_solid)
        entries.update(external_hydraulic_water_m3=float(hydraulic_water.sum()),
                       external_hydraulic_solid_m3=float(hydraulic_solid.sum()))
    s["groundwater"]["surface_water_m3"], coast_water, water_export = _route_packet(
        s["groundwater"]["surface_water_m3"], ctx, dt_s, plant["fluxes"]["manning_n"])
    s["mass"]["river_sediment_solid_m3"], coast_solid, solid_export = _route_packet(
        s["mass"]["river_sediment_solid_m3"], ctx, dt_s, plant["fluxes"]["manning_n"])
    direct_ocean_solid = s["mass"]["ocean_export_solid_m3"] - old_mass["ocean_export_solid_m3"]
    coast_solid += direct_ocean_solid
    s["mass"]["downstream_delivered_solid_m3"] += coast_solid - direct_ocean_solid + solid_export
    coastal = None
    if ctx["ocean_mask"].any():
        mouth = (coast_water + coast_solid) > 0.
        coast_driver = driver("coastal_exchange")
        if "soil_exchange_m3_s" in coast_driver:
            coast_driver["soil_exchange_m3_s"] = array(coast_driver["soil_exchange_m3_s"], shape,
                                                          "soil_exchange_m3_s") * land
        coastal = run("coastal_exchange", coast, {**coast_driver,
            "mouth_mask": mouth, "river_boundary_water_m3_s": coast_water / dt_s,
            "river_boundary_solid_m3_s": coast_solid / dt_s}, ctx)
        packets["soil_water_m3"] = coastal["fluxes"]["soil_water_m3"].copy()
        packets["soil_salt_kg"] = coastal["fluxes"]["soil_salt_kg"].copy()
    animal = run("habitat", habitat, {**driver("habitat"),
        "vegetation_cover_fraction": plant["fluxes"]["cover_fraction"],
        "water_available_fraction": moisture, "water_temperature_c": f.get("air_temperature_c", 10.),
        "disturbance_fraction": s["succession"]["disturbance_fraction"]}, ctx)
    # Material geometry is derived separately; original source height stays pinned.
    mass_bulk_change = (s["mass"]["regolith_bulk_m3"] - old_mass["regolith_bulk_m3"]
        + (s["mass"]["soil_solid_m3"] - old_mass["soil_solid_m3"]
           + s["mass"]["hillslope_deposit_solid_m3"] - old_mass["hillslope_deposit_solid_m3"]) / (1. - s["mass"]["regolith_porosity"])
        - matter["fluxes"]["weathered_solid_m3"])
    bed_change = (mass_bulk_change / area + ice["fluxes"]["height_change_m"]
                  + vol["fluxes"]["height_change_m"] + sand["fluxes"]["height_change_m"])
    if coastal:
        bed_change += s["coastal_exchange"]["bed_m"] - product["states"]["coastal_exchange"]["bed_m"]
    bed_change[~ctx["valid_mask"] | ctx["protected_mask"]] = 0.
    s["network_transition"] = transition.initial_state(ctx,
        water_m3=s["groundwater"]["surface_water_m3"], sediment_solid_m3=s["mass"]["river_sediment_solid_m3"],
        floodplain_solid_m3=s["mass"]["hillslope_deposit_solid_m3"])
    if seasonal_mode:
        results["network_transition"] = {
            "fluxes": {"diagnostic_bed_change_m": bed_change.copy()},
            "ledger": {name + "_residual": 0. for name in transition.INVENTORIES},
            "metadata": {"algorithm": seasonal_api.NETWORK_ALGORITHM, "status": "frozen_saved_network",
                         "dt_s": float(dt_s), "parameters": {},
                         "policy": "keep saved receiver and water geometry; no natural capture advancement"}}
    else:
        proposed = transition.step(s["network_transition"], {"bed_change_m": bed_change}, ctx, dt_s)
        committed = transition.commit_transition(s["network_transition"], proposed, ctx)
        s["network_transition"] = committed["state"]
        results["network_transition"] = {key: committed[key] for key in ("fluxes", "ledger", "metadata")}
        ctx["height_m"] = committed["state"]["height_m"].copy()
        ctx["receiver"] = committed["state"]["receiver"].copy()
        if np.any(bed_change):
            ctx["active_routing_policy"] = ctx["routing_policy"]
    s["coastal_exchange"]["bed_m"] = ctx["height_m"].copy()
    if land_cover_mode:
        # The completed snapshot reflects G9's newly delivered soil; G15 consumed
        # the actual pre-weathering soil and current G5 water above.
        out["seasonal"]["land_cover"] = land_cover.assess(out)
    transfers.update(rainfall_m3=rain, rain_to_soil_m3=soil_rain, rain_to_aquifer_m3=aquifer_rain,
        rain_to_frozen_m3=frozen_rain, rain_to_runoff_m3=runoff_rain,
        river_to_coast_water_m3=coast_water, river_to_coast_solid_m3=coast_solid,
        window_water_export_m3=water_export, window_solid_export_m3=solid_export,
        soil_nutrient_to_plant_kg=soil["fluxes"]["plant_uptake_kg"],
        litter_to_pending_kg=packets["litter_carbon_kg"], soil_root_cohesion_pa=plant["fluxes"]["root_cohesion_pa"],
        hydraulic_manning_n=plant["fluxes"]["manning_n"], derived_bed_change_m=bed_change)
    entries.update(rainfall_m3=float(rain.sum()), evaporation_m3=soil["ledger"]["evaporation_m3"],
        window_water_export_m3=float(water_export.sum()), pumping_m3=gw["ledger"]["pumping_m3"],
        ocean_water_input_m3=coastal["ledger"]["signed_ocean_water_m3"] if coastal else 0.,
        eruption_solid_input_m3=vol["ledger"]["event_input_solid_m3"],
        solid_boundary_export_m3=float(solid_export.sum()) + sand["ledger"]["boundary_export_solid_m3"] + vol["ledger"]["boundary_export_solid_m3"],
        dissolved_solid_export_m3=float((s["mass"]["dissolved_solid_m3"] - old_mass["dissolved_solid_m3"]).sum()),
        photosynthesis_carbon_kg=plant["ledger"]["photosynthesis_carbon_kg"],
        atmosphere_carbon_export_kg=plant["ledger"]["fire_atmosphere_carbon_kg"] + soil["ledger"]["respired_carbon_kg"],
        salt_boundary_input_kg=coastal["ledger"]["signed_ocean_salt_kg"] if coastal else 0.,
        salt_boundary_export_kg=0.,
        nutrient_boundary_input_kg=soil["ledger"]["nutrient_input_kg"] + soil["ledger"]["litter_nutrient_kg"],
        nutrient_boundary_export_kg=0.)
    if seasonal_mode:
        snow_fluxes = snow["fluxes"]
        transfers.update({"seasonal_" + key: value
                          for key, value in snow_fluxes.items()})
        transfers.update(g5_infiltration_m3=bucket["infiltration_m3"],
                         g5_percolation_m3=bucket["percolation_m3"],
                         g5_et_m3=bucket["actual_et_m3"], g5_release_m3=bucket["release_m3"],
                         g5_fast_release_m3=bucket["fast_release_m3"], g5_slow_release_m3=bucket["slow_release_m3"],
                         seasonal_et_recycle_kg=recycled_et_kg)
        climate_ledger = climate_driving["ledger"]
        entries.update(atmosphere_inflow_m3=float(climate_ledger["inflow_kg"]) / 1000.,
                       atmosphere_outflow_m3=float(climate_ledger["outflow_kg"]) / 1000.,
                       precipitation_unmodelled_export_m3=float(climate_ledger["precipitation_kg"]) / 1000. - float(rain.sum()),
                       sublimation_m3=float(snow_fluxes["sublimation_m3"].sum()),
                       seasonal_et_recycle_kg=float(recycled_et_kg.sum()))
    after = inventory_totals(out)
    net = {"water_m3": entries["rainfall_m3"] + entries["ocean_water_input_m3"] - entries["evaporation_m3"] - entries["window_water_export_m3"] - entries["pumping_m3"],
           "solid_m3": entries["eruption_solid_input_m3"] - entries["solid_boundary_export_m3"] - entries["dissolved_solid_export_m3"],
           "carbon_kg": entries["photosynthesis_carbon_kg"] - entries["atmosphere_carbon_export_kg"],
           "salt_kg": entries["salt_boundary_input_kg"] - entries["salt_boundary_export_kg"],
           "nutrient_kg": entries["nutrient_boundary_input_kg"] - entries["nutrient_boundary_export_kg"]}
    if seasonal_mode:
        net["water_m3"] = seasonal_api.net_water(entries)
    if handoff_mode:
        net["solid_m3"] -= entries["external_hydraulic_solid_m3"]
        if not seasonal_mode:
            net["water_m3"] -= entries["external_hydraulic_water_m3"]
    budget = {name + "_residual": before[name] + net[name] - after[name] for name in before}
    for name, residual in budget.items():
        key = name.removesuffix("_residual")
        if abs(residual) > 1.e-9 * max(1., abs(before[key]), abs(after[key])):
            raise ValueError("coupled product inventory does not close: " + name)
    absorbed_j = rad["ledger"]["absorbed_j"]
    solar_ground_j = float(rad["fluxes"]["net_ground_heat_w_m2"].sum() * area * dt_s)
    solar_to_frozen_j = float((rad["fluxes"]["net_ground_heat_w_m2"] * land).sum() * area * dt_s)
    potential_et_j = float(rad["fluxes"]["potential_evaporation_m"].sum() * area * 2.45e9)
    actual_et_j = entries["evaporation_m3"] * 2.45e9
    old_frozen = product["states"]["frozen_ground"]
    thermal_p = ice["metadata"]["parameters"]
    air = array(f.get("air_temperature_c", 10.), shape, "air_temperature_c", nonnegative=False)
    air_heat_j = float((thermal_p["air_exchange_w_m2_k"] * (air - old_frozen["soil_temperature_c"])
        / (1. + thermal_p["snow_insulation_per_m_swe"] * old_frozen["snow_swe_m"]) * land).sum() * area * dt_s)
    geothermal_to_frozen_j = float((vol["fluxes"]["geothermal_heat_w_m2"] * land).sum() * area * dt_s)
    energy_budget = {"solar_absorbed_j": absorbed_j, "solar_to_frozen_j": solar_to_frozen_j,
        "unused_ocean_or_inactive_ground_shortwave_j": solar_ground_j - solar_to_frozen_j,
        "actual_evaporation_latent_j": actual_et_j, "unused_potential_evaporation_j": max(potential_et_j - actual_et_j, 0.),
        "shortwave_partition_residual_j": absorbed_j - solar_ground_j - potential_et_j,
        "geothermal_to_frozen_j": geothermal_to_frozen_j, "air_to_frozen_j": air_heat_j,
        "frozen_heat_supply_residual_j": ice["ledger"]["heat_input_j"] - solar_to_frozen_j - geothermal_to_frozen_j - air_heat_j,
        "frozen_enthalpy_residual_j": ice["ledger"]["energy_residual_j"],
        "volcanic_heat_residual_j": vol["ledger"]["heat_residual_j"]}
    for name in ("shortwave_partition_residual_j", "frozen_heat_supply_residual_j", "frozen_enthalpy_residual_j", "volcanic_heat_residual_j"):
        if abs(energy_budget[name]) > 1.e-9 * max(1., abs(absorbed_j), abs(ice["ledger"]["heat_input_j"]), abs(vol["ledger"]["cooling_heat_j"])):
            raise ValueError("coupled product energy does not close: " + name)
    entries.update({name: value for name, value in energy_budget.items() if "residual" not in name})
    for name, amount in entries.items():
        out["cumulative_ledger"][name] = out["cumulative_ledger"].get(name, 0.) + amount
    out.update(results=results, last_transfers=transfers, last_budget=budget, last_energy_budget=energy_budget,
               time_s=out["time_s"] + dt_s, step_index=out["step_index"] + 1)
    out["parameters"]["process_parameters"] = {name: result["metadata"].get("parameters", result["metadata"].get("weathering_parameters", {}))
                                                for name, result in results.items()}
    out["forcing_history"].append({"start_time_s": product["time_s"], "dt_s": float(dt_s),
                                   "declaration": deepcopy(forcing)})
    return out



def _validate_product(product):
    """Static checks only: cold loading does not route, sample or advance."""
    if product.get("schema") != SCHEMA or product.get("algorithm") not in (ALGORITHM, storage.EXPLICIT_V2_ALGORITHM) + seasonal_api.ALGORITHMS:
        raise ValueError("invalid environment process product")
    ctx = product["context"]
    shape = np.asarray(ctx["height_m"]).shape
    if len(shape) != 2 or not 0 < math.prod(shape) <= MAX_CELLS:
        raise ValueError("invalid finite product shape")
    if set(product["states"]) != set(MODULES) | {"mass", "groundwater", "network_transition"}:
        raise ValueError("incomplete process state")
    for name, state in product["states"].items():
        for field, value in state.items():
            data = np.asarray(value)
            if data.shape != shape or data.dtype.kind not in "biuf" or not np.isfinite(data).all():
                raise ValueError("invalid persistent state array: " + name + "." + field)
    if not np.array_equal(product["states"]["network_transition"]["height_m"], ctx["height_m"]):
        raise ValueError("committed height/context mismatch")
    if not np.array_equal(product["states"]["network_transition"]["receiver"], ctx["receiver"]):
        raise ValueError("committed receiver/context mismatch")
    if not np.isfinite(product["time_s"]) or product["time_s"] < 0. or product["step_index"] != len(product["forcing_history"]):
        raise ValueError("invalid persistent physical time/history")
    ledger = product["cumulative_ledger"]
    get = lambda name: float(ledger.get(name, 0.))
    net = {"water_m3": get("rainfall_m3") + get("ocean_water_input_m3") - get("evaporation_m3") - get("window_water_export_m3") - get("pumping_m3"),
           "solid_m3": get("eruption_solid_input_m3") - get("solid_boundary_export_m3") - get("dissolved_solid_export_m3"),
           "carbon_kg": get("photosynthesis_carbon_kg") - get("atmosphere_carbon_export_kg"),
           "salt_kg": get("salt_boundary_input_kg") - get("salt_boundary_export_kg"),
           "nutrient_kg": get("nutrient_boundary_input_kg") - get("nutrient_boundary_export_kg")}
    if seasonal_api.is_seasonal(product):
        seasonal_api.validate(product)
        net["water_m3"] = seasonal_api.net_water(ledger)
        if product["algorithm"] == seasonal_api.ALGORITHM_V2:
            net["solid_m3"] -= get("external_hydraulic_solid_m3")
    if product["algorithm"] == storage.EXPLICIT_V2_ALGORITHM:
        net["water_m3"] -= get("external_hydraulic_water_m3")
        net["solid_m3"] -= get("external_hydraulic_solid_m3")
    current = inventory_totals(product)
    for name, amount in current.items():
        initial = float(product["initial_inventory"][name])
        if abs(initial + net[name] - amount) > 1.e-9 * max(1., abs(initial), abs(amount)):
            raise ValueError("persistent coupled inventory mismatch: " + name)



def _pack(product):
    return storage._pack(product, _validate_product)


def _validate_bundle(bundle):
    return storage._validate_bundle(bundle, _validate_product)


_unpack = storage._unpack


def save_product(product, path):
    return storage.save_product(product, path, _validate_product)


def product_identity(product):
    return storage.product_identity(product, _validate_product)


def load_product(path, *, expected_sha256):
    return storage.load_product(path, expected_sha256=expected_sha256,
                                validate_product=_validate_product)
