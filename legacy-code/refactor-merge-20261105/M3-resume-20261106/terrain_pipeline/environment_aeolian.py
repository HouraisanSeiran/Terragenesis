"""Finite dry loose-solid entrainment, directed wind transport and deposition."""
import numpy as np
from terrain_pipeline.environment_process_contract import _field, _grid, _parameters
from terrain_pipeline.drainage import segments_clear as segments_clear

ALGORITHM = "environment-finite-wind-solid-v1"


def initialize(context, *, loose_solid_m3=0.):
    height, _, _ = _grid(context, 1.)
    return {"loose_solid_m3": _field(loose_solid_m3, height.shape, "loose solid", 0.),
            "airborne_solid_m3": np.zeros(height.shape)}


def step(state, forcing, context, dt_s, parameters=None):
    height, spacing, active = _grid(context, dt_s)
    p = _parameters(parameters, {"threshold_wind_m_s": 5., "entrainment_rate_s_m": 1.e-5,
        "settling_time_s": 600., "solid_fraction": .6})
    if p["solid_fraction"] > 1:
        raise ValueError("solid fraction must not exceed one")
    loose = _field(state["loose_solid_m3"], height.shape, "loose", 0.)
    airborne = _field(state["airborne_solid_m3"], height.shape, "airborne", 0.)
    wx = _field(forcing.get("wind_x_m_s", 0.), height.shape, "wind x")
    wz = _field(forcing.get("wind_z_m_s", 0.), height.shape, "wind z")
    wet = _field(forcing.get("water_saturation", 0.), height.shape, "saturation", 0., 1.)
    cover = _field(forcing.get("vegetation_cover", 0.), height.shape, "vegetation", 0., 1.)
    ocean = _field(context.get("ocean_mask", False), height.shape, "ocean").astype(bool)
    land = active & ~ocean
    speed = np.hypot(wx, wz)
    entrained = loose * -np.expm1(-p["entrainment_rate_s_m"] * np.maximum(speed - p["threshold_wind_m_s"], 0.) * dt_s)
    entrained *= (1 - wet) * (1 - cover) * land
    mobile = airborne + entrained
    rows, cols = np.indices(height.shape)
    dr = np.where(np.abs(wz) >= np.abs(wx), np.sign(wz), 0).astype(int)
    dc = np.where(np.abs(wx) >= np.abs(wz), np.sign(wx), 0).astype(int)
    step_length = spacing * np.maximum(1., np.hypot(dr, dc))
    moved_fraction = np.minimum(1., speed * dt_s / step_length)
    transport = np.where(active, mobile * moved_fraction, 0.)
    rr, cc = rows + dr, cols + dc
    inside = (rr >= 0) & (rr < height.shape[0]) & (cc >= 0) & (cc < height.shape[1])
    tr, tc = np.clip(rr, 0, height.shape[0] - 1), np.clip(cc, 0, height.shape[1] - 1)
    accepted = inside & active[tr, tc]
    origins = np.arange(height.size, dtype=np.int64).reshape(height.shape)
    accepted &= segments_clear(origins.ravel(), (tr * height.shape[1] + tc).ravel(), active).reshape(height.shape)
    exported = np.where(~inside, transport, 0.)
    transferred = np.where(accepted, transport, 0.)
    updated = mobile - transferred - exported
    np.add.at(updated, (tr[accepted], tc[accepted]), transferred[accepted])
    deposited = np.where(active, updated * -np.expm1(-dt_s / p["settling_time_s"]), 0.)
    new_loose = loose - entrained + deposited
    new_airborne = updated - deposited
    delta_height = (deposited - entrained) / (spacing ** 2 * p["solid_fraction"])
    return {"state": {"loose_solid_m3": new_loose, "airborne_solid_m3": new_airborne},
        "fluxes": {"entrained_solid_m3": entrained, "transported_solid_m3": transferred,
            "deposited_solid_m3": deposited, "boundary_export_solid_m3": exported,
            "height_change_m": delta_height},
        "ledger": {"initial_solid_m3": float((loose + airborne).sum()),
            "final_solid_m3": float((new_loose + new_airborne).sum()),
            "boundary_export_solid_m3": float(exported.sum()),
            "solid_residual_m3": float((new_loose + new_airborne).sum() + exported.sum() - (loose + airborne).sum())},
        "metadata": {"algorithm": ALGORITHM, "parameters": p,
            "source": "declared uncalibrated single sand-class finite inventory",
            "units": "inventories and transfers m3 solid per cell; height metres bulk; wind m/s; dt seconds",
            "transport": "one downwind native account per step; protected/unknown block; exterior export explicit",
            "limitation": "no resolved dune migration/loess grain sorting; ocean deposition remains finite tracked solid"}}
