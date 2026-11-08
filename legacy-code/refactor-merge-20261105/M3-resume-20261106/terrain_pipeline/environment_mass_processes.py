"""Finite G9/G10 weathering and one-hop loose-solid transport.

Native cells own spacing**2 area. Volumes are solid m3, never bulk m3.
Coefficients are engineering scenarios, not calibrated geomorphic rates.
"""
from copy import deepcopy

import numpy as np

from terrain_pipeline import weathering_soil_inventory as weathering
from terrain_pipeline.drainage import segments_clear as segments_clear
from terrain_pipeline.environment_context import array, context_arrays

ALGORITHM = "environment-finite-weathering-transport-v1"
STOCKS = ("soil_solid_m3", "hillslope_deposit_solid_m3", "river_sediment_solid_m3",
          "ocean_export_solid_m3", "downstream_delivered_solid_m3")
WEATHER_FIELDS = ("bedrock_solid_m3", "regolith_solid_m3", "regolith_bulk_m3",
                  "parent_solid_m3", "dissolved_solid_m3", "delivered_regolith_solid_m3",
                  "delivered_parent_solid_m3", "weatherable_thickness_m", "area_m2",
                  "bed_hardness", "solubility", "initial_bedrock_solid_m3")


def initial_state(context, *, bedrock_thickness_m=1., bed_hardness=.5, solubility=.2):
    height, masks, _, _ = context_arrays(context, 1.)
    shape = height.shape
    values = [array(v, shape, n) for v, n in
              ((bedrock_thickness_m, "bedrock_thickness_m"),
               (bed_hardness, "bed_hardness"), (solubility, "solubility"))]
    if np.any(values[1] > 1.) or np.any(values[2] > 1.):
        raise ValueError("bed_hardness and solubility must be fractions")
    values[0][~masks["valid_mask"] | masks["ocean_mask"]] = 0.
    parts = {name: [] for name in WEATHER_FIELDS}
    for start in range(0, height.size, weathering.MAX_COLUMNS):
        stop = start + weathering.MAX_COLUMNS
        block = weathering.initial_state(bedrock_thickness_m=values[0].ravel()[start:stop],
                                        area_m2=float(context["spacing_m"]) ** 2,
                                        bed_hardness=values[1].ravel()[start:stop],
                                        solubility=values[2].ravel()[start:stop])
        for name in WEATHER_FIELDS:
            parts[name].append(block[name])
    state = {name: np.concatenate(parts[name]).reshape(shape) for name in WEATHER_FIELDS}
    state.update({name: np.zeros(shape) for name in STOCKS})
    state["regolith_porosity"] = np.full(shape, .35)
    return state


def step(initial_state, forcing, context, dt_s):
    height, masks, mesh, receiver = context_arrays(context, dt_s)
    shape = height.shape
    state = {name: array(initial_state[name], shape, name) for name in (*WEATHER_FIELDS, *STOCKS)}
    active = masks["valid_mask"] & ~masks["protected_mask"] & ~masks["ocean_mask"]
    parameters = weathering.normalize_parameters(forcing.get("weathering_parameters"))
    previous_porosity = array(initial_state["regolith_porosity"], shape, "regolith_porosity")
    porosity = float(parameters["regolith_porosity"]["value"])
    if np.any((previous_porosity != porosity) & (state["regolith_solid_m3"] > 0.)):
        raise ValueError("cannot change porosity of an existing regolith stock")
    state["regolith_porosity"] = np.full(shape, porosity)
    temperature = array(forcing.get("temperature_c", 10.), shape, "temperature_c", nonnegative=False)
    moisture = array(forcing.get("moisture", 0.), shape, "moisture")
    biology = array(forcing.get("bio_activity", 0.), shape, "bio_activity")
    if np.any(moisture > 1.) or np.any(biology > 1.):
        raise ValueError("moisture and bio_activity must be fractions")
    soil_request = array(forcing.get("soil_request_solid_m3", 0.), shape, "soil_request_solid_m3")
    rate = array(forcing.get("transport_fraction_per_s", 0.), shape, "transport_fraction_per_s")
    repose = array(forcing.get("repose_angle_deg", 34.), shape, "repose_angle_deg")
    if np.any(repose >= 90.):
        raise ValueError("repose_angle_deg must be below 90")
    slope = np.zeros(height.size)
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    distance = np.hypot(mesh.node_x_m[targets] - mesh.node_x_m[donors],
                        mesh.node_z_m[targets] - mesh.node_z_m[donors])
    slope[donors] = (height.ravel()[donors] - height.ravel()[targets]) / distance
    root = array(forcing.get("root_cohesion_pa", 0.), shape, "root_cohesion_pa")
    # Infinite-slope engineering shear term; 1800 kg/m3 is declared bulk density.
    loose_depth = (state["regolith_bulk_m3"] + state["hillslope_deposit_solid_m3"] / (1. - state["regolith_porosity"])) / state["area_m2"]
    threshold = np.tan(np.deg2rad(repose)) * (1. - .5 * moisture)
    threshold += root / (1800. * 9.80665 * np.maximum(loose_depth, .01))
    unstable = (slope.reshape(shape) > threshold) & active
    fraction = np.minimum(rate * dt_s, 1.) * unstable
    delivery = np.zeros(shape)
    weathered = np.zeros(shape)
    for start in range(0, height.size, weathering.MAX_COLUMNS):
        stop = min(start + weathering.MAX_COLUMNS, height.size)
        section = slice(start, stop)
        block = {name: state[name].ravel()[section].copy() for name in WEATHER_FIELDS}
        block.update(status=np.where(block["bedrock_solid_m3"] > 0., "active", "exhausted"),
                     density_kg_m3=None, parameters=deepcopy(parameters))
        # Mask all three physical drivers, including the dry physical term.
        hardness = block["bed_hardness"].copy()
        block["bed_hardness"][~active.ravel()[section]] = 1.
        block, flux = weathering.advance(
            block, dt_s=dt_s, temperature_c=temperature.ravel()[section],
            moisture=moisture.ravel()[section] * active.ravel()[section],
            bio_activity=biology.ravel()[section] * active.ravel()[section],
            parameters=forcing.get("weathering_parameters"))
        block["bed_hardness"] = hardness
        weathered.ravel()[section] = flux["weathered_solid_m3"]
        request = block["regolith_solid_m3"] * fraction.ravel()[section]
        block, soil, sediment, _, _ = weathering.allocate(
            block, soil_parent_solid_m3=soil_request.ravel()[section] * active.ravel()[section],
            sediment_solid_m3=request, shortage_policy="proportional")
        for name in WEATHER_FIELDS:
            state[name].ravel()[section] = block[name]
        state["soil_solid_m3"].ravel()[section] += soil["soil_parent_solid_m3"]
        delivery.ravel()[section] = sediment["sediment_solid_m3"]
    deposit_out = state["hillslope_deposit_solid_m3"] * fraction
    state["hillslope_deposit_solid_m3"] -= deposit_out
    moved = delivery + deposit_out
    flux_river = np.zeros(shape)
    flux_ocean = np.zeros(shape)
    for donor in np.flatnonzero(moved.ravel() > 0.):
        target = receiver[donor]
        if target < 0 or masks["protected_mask"].ravel()[target]:
            state["hillslope_deposit_solid_m3"].ravel()[donor] += moved.ravel()[donor]
        elif masks["ocean_mask"].ravel()[target]:
            flux_ocean.ravel()[target] += moved.ravel()[donor]
        elif masks["river_mask"].ravel()[target]:
            flux_river.ravel()[target] += moved.ravel()[donor]
        else:
            state["hillslope_deposit_solid_m3"].ravel()[target] += moved.ravel()[donor]
    state["river_sediment_solid_m3"] += flux_river
    state["ocean_export_solid_m3"] += flux_ocean
    total = sum(float(state[name].sum()) for name in
                ("bedrock_solid_m3", "regolith_solid_m3", "dissolved_solid_m3", *STOCKS))
    residual = float(state["initial_bedrock_solid_m3"].sum()) - total
    return {"state": state, "fluxes": {"weathered_solid_m3": weathered,
            "mobilized_solid_m3": moved, "river_delivery_solid_m3": flux_river,
            "ocean_delivery_solid_m3": flux_ocean, "unstable_mask": unstable},
            "ledger": {"solid_residual_m3": residual, "current_total_solid_m3": total},
            "metadata": {"algorithm": ALGORITHM, "dt_s": float(dt_s),
                         "origin_native_xz": list(context["origin_native_xz"]),
                         "spacing_m": float(context["spacing_m"]), "world_seed": int(context["world_seed"]),
                         "parameter_status": "engineering_scenario_uncalibrated",
                         "weathering_parameters": parameters,
                         "limitations": ["one-hop loose regolith transport per physical step",
                                         "no rigid blocks, impact, rheology or calibrated landslide hazard"]}}
