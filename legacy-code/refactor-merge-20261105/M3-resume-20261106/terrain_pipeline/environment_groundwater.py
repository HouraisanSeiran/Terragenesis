"""Finite unconfined water buckets with graph head flow and river/lake exchange.

Recharge is a supplied transfer already debited by its upstream owner. Surface
exchange changes both returned stocks; its diagnostic flux must not be debited
again by a runoff consumer. This is an engineering reservoir approximation.
"""
import numpy as np

from terrain_pipeline.environment_context import array, context_arrays
from terrain_pipeline.drainage import segments_clear as segments_clear

ALGORITHM = "environment-head-bucket-exchange-v1"


def initial_state(context, *, groundwater_water_m3=0., surface_water_m3=0.):
    height, masks, _, _ = context_arrays(context, 1.)
    state = {"groundwater_water_m3": array(groundwater_water_m3, height.shape, "groundwater_water_m3"),
             "surface_water_m3": array(surface_water_m3, height.shape, "surface_water_m3")}
    if any(np.any(value[~masks["valid_mask"]] != 0.) for value in state.values()):
        raise ValueError("water stock outside valid support")
    return state


def step(initial_state, forcing, context, dt_s):
    height, masks, mesh, _ = context_arrays(context, dt_s)
    shape = height.shape
    state = {
        name: array(initial_state[name], shape, name)
        for name in ("groundwater_water_m3", "surface_water_m3")}
    if any(np.any(value[~masks["valid_mask"]] != 0.) for value in state.values()):
        raise ValueError("water stock outside valid support")
    before = sum(float(value.sum()) for value in state.values())
    area_m2 = float(context["spacing_m"]) ** 2
    specific_yield = array(forcing.get("specific_yield", .2), shape, "specific_yield")
    if np.any(specific_yield <= 0.) or np.any(specific_yield > 1.):
        raise ValueError("specific_yield must be in (0,1]")
    base = array(forcing.get("aquifer_base_m", height - 10.), shape, "aquifer_base_m", nonnegative=False)
    if np.any(base > height):
        raise ValueError("aquifer base cannot exceed terrain")
    recharge = array(forcing.get("recharge_m3", 0.), shape, "recharge_m3")
    surface_input = array(forcing.get("surface_input_m3", 0.), shape, "surface_input_m3")
    if np.any((recharge + surface_input)[~masks["valid_mask"]] != 0.):
        raise ValueError("water forcing outside valid support")
    groundwater = state["groundwater_water_m3"]
    surface = state["surface_water_m3"]
    groundwater += recharge
    surface += surface_input
    head = base + groundwater / (area_m2 * specific_yield)
    conductance = array(forcing.get("lateral_conductance_m2_s", 0.), shape,
                        "lateral_conductance_m2_s")
    sources = np.repeat(np.arange(height.size), np.diff(mesh.indptr))
    targets = mesh.indices.astype(np.int64)
    keep = sources < targets
    sources, targets = sources[keep], targets[keep]
    keep = segments_clear(sources, targets, masks["valid_mask"])
    sources, targets = sources[keep], targets[keep]
    delta_head = head.ravel()[sources] - head.ravel()[targets]
    donors = np.where(delta_head >= 0., sources, targets)
    receivers = np.where(delta_head >= 0., targets, sources)
    requested = np.minimum(conductance.ravel()[donors], conductance.ravel()[receivers]) * np.abs(delta_head) * dt_s
    requested_total = np.bincount(donors, weights=requested, minlength=height.size)
    factor = np.minimum(1., np.divide(groundwater.ravel(), requested_total,
                                     out=np.ones(height.size), where=requested_total > 0.))
    exchanged = requested * factor[donors]
    lateral_delta = np.bincount(receivers, weights=exchanged, minlength=height.size)
    lateral_delta -= np.bincount(donors, weights=exchanged, minlength=height.size)
    groundwater += lateral_delta.reshape(shape)
    head = base + groundwater / (area_m2 * specific_yield)
    lake = np.asarray(context.get("lake_mask", np.zeros(shape, bool)))
    if lake.shape != shape or lake.dtype != bool:
        raise ValueError("lake_mask must be a matching boolean array")
    connected = (masks["river_mask"] | lake) & masks["valid_mask"]
    stage = array(forcing.get("surface_stage_m", height + surface / area_m2), shape,
                  "surface_stage_m", nonnegative=False)
    exchange_k = array(forcing.get("surface_conductance_m2_s", 0.), shape,
                       "surface_conductance_m2_s")
    exchange = exchange_k * (head - stage) * dt_s * connected
    exchange = np.where(exchange >= 0., np.minimum(exchange, groundwater),
                        -np.minimum(-exchange, surface))
    groundwater -= exchange
    surface += exchange
    capacity = (height - base) * area_m2 * specific_yield
    spring = np.maximum(groundwater - capacity, 0.)
    groundwater -= spring
    surface += spring
    pumping = np.minimum(array(forcing.get("pumping_request_m3", 0.), shape,
                               "pumping_request_m3"), groundwater)
    groundwater -= pumping
    after = float(groundwater.sum() + surface.sum())
    return {"state": state,
            "fluxes": {"recharge_m3": recharge, "surface_input_m3": surface_input,
                       "lateral_net_m3": lateral_delta.reshape(shape),
                       "groundwater_to_surface_m3": exchange,
                       "spring_m3": spring, "pumping_m3": pumping,
                       "groundwater_head_m": base + groundwater / (area_m2 * specific_yield)},
            "ledger": {"water_before_m3": before, "water_after_m3": after,
                       "recharge_m3": float(recharge.sum()),
                       "surface_input_m3": float(surface_input.sum()),
                       "pumping_m3": float(pumping.sum()),
                       "water_residual_m3": before + float(recharge.sum() + surface_input.sum())
                                              - float(pumping.sum()) - after},
            "metadata": {"algorithm": ALGORITHM, "dt_s": float(dt_s),
                         "origin_native_xz": list(context["origin_native_xz"]),
                         "spacing_m": float(context["spacing_m"]), "world_seed": int(context["world_seed"]),
                         "parameter_status": "engineering_scenario_uncalibrated",
                         "exchange_semantics": "already applied to both returned stocks; do not debit again",
                         "limitations": ["explicit finite head buckets, donor limited; not a Darcy/PDE aquifer solver",
                                         "no karst conduits or calibrated natural spring certification"]}}
