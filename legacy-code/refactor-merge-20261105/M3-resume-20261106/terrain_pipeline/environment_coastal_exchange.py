"""Finite tidal prism, signed ocean salt exchange and conservative active bed.

Uses the existing donor-capped coastal face-transfer kernel. This is a reduced
connected-water prism and wave-driven bed model, not 2D wave momentum or Exner.
River input is an explicit mouth boundary packet, never accumulated again.
"""
import numpy as np
from scipy.ndimage import binary_propagation

from .environment_ecology_contract import field, frame, metadata, stocks
from .surface_rivers.metric_coastal_transport import _face_transfer

ALGORITHM = "environment-tidal-prism-salt-active-bed-v1"
PARAMETERS = {"porosity": .35, "exchange_timescale_s": 1800.,
              "wave_transfer_timescale_s": 86400., "max_tide_substep_s": 900.}


def _connected(bed, level, seeds, valid):
    below = (bed < level) & valid
    return binary_propagation(seeds & below, mask=below)


def initialize_coastal_exchange(context, *, sea_level_m=0., ocean_salinity_kg_m3=35.,
                                  mobile_thickness_m=.3):
    shape, area, masks = frame(context, 0.)
    bed = field(context, "height_m", shape, nonnegative=False)
    for number in (sea_level_m, ocean_salinity_kg_m3, mobile_thickness_m):
        if not np.isfinite(number):
            raise ValueError("finite initial coast parameters required")
    if min(ocean_salinity_kg_m3, mobile_thickness_m) < 0.:
        raise ValueError("nonnegative salt and mobile thickness required")
    wet = _connected(bed, sea_level_m, masks["ocean_mask"], masks["valid_mask"])
    water = np.maximum(sea_level_m - bed, 0.) * wet * area
    mobile = mobile_thickness_m * area * (1. - PARAMETERS["porosity"])
    mobile *= masks["valid_mask"] & ~masks["protected_mask"]
    return {"water_m3": water, "salt_kg": water * ocean_salinity_kg_m3,
            "bed_solid_m3": mobile, "bed_m": bed, "time_s": np.zeros(shape)}


def advance_coastal_exchange(state, forcing, context, dt_s):
    shape, area, masks = frame(context, dt_s)
    old = stocks(state, ("water_m3", "salt_kg", "bed_solid_m3", "bed_m", "time_s"), shape, signed=("bed_m",))
    if not np.all(old["time_s"] == old["time_s"].flat[0]):
        raise ValueError("coastal physical time must be uniform across the grid")
    valid = masks["valid_mask"]
    active = valid & ~masks["protected_mask"]
    mouth = np.asarray(forcing.get("mouth_mask", np.zeros(shape, bool)))
    if mouth.shape != shape or mouth.dtype != bool or np.any(mouth & ~valid):
        raise ValueError("explicit valid mouth_mask required")
    river_rate = field(forcing, "river_boundary_water_m3_s", shape)
    solid_rate = field(forcing, "river_boundary_solid_m3_s", shape)
    if np.any((river_rate > 0.) & ~(mouth & active)) or np.any((solid_rate > 0.) & ~(mouth & active)):
        raise ValueError("river water/solid boundary only at explicit unprotected mouths")
    amplitude = float(forcing.get("tide_amplitude_m", 0.))
    period = float(forcing.get("tide_period_s", 44712.))
    mean = float(forcing.get("mean_sea_level_m", 0.))
    phase = float(forcing.get("tide_phase_rad", 0.))
    wave_height = float(forcing.get("wave_height_m", 0.))
    if not np.isfinite([amplitude, period, mean, phase, wave_height]).all() or min(amplitude, wave_height) < 0. or period <= 0.:
        raise ValueError("finite tide/wave forcing and positive period required")
    direction = np.asarray(forcing.get("wave_direction_xz", (1., 0.)), np.float64)
    if direction.shape != (2,) or not np.isfinite(direction).all() or np.linalg.norm(direction) == 0.:
        raise ValueError("nonzero wave direction required")
    direction = direction / np.linalg.norm(direction)
    ocean_salt = field(forcing, "ocean_salinity_kg_m3", shape, 35.)
    water, salt, inventory, bed = (old[k].copy() for k in ("water_m3", "salt_kg", "bed_solid_m3", "bed_m"))
    flux = {name: np.zeros(shape) for name in ("tide_water_m3", "tide_salt_kg", "flood_water_m3", "ebb_water_m3",
             "wave_bed_transfer_m3", "river_water_m3", "river_solid_m3", "soil_water_m3", "soil_salt_kg")}
    soil_rate = field(forcing, "soil_exchange_m3_s", shape) * active
    gross_wave = 0.
    start = float(old["time_s"].flat[0])
    steps = max(1, int(np.ceil(dt_s / min(PARAMETERS["max_tide_substep_s"], period / 16.))))
    if steps > 10000:
        raise ValueError("coastal interval exceeds bounded substep budget")
    step = dt_s / steps
    wet = np.zeros(shape, bool)
    level = mean + amplitude * np.sin(2. * np.pi * start / period + phase)
    for index in range(steps):
        time = start + (index + 1) * step
        level = mean + amplitude * np.sin(2. * np.pi * time / period + phase)
        wet = _connected(bed, level, masks["ocean_mask"], valid)
        river_water = river_rate * step
        river_solid = solid_rate * step
        water += river_water
        inventory += river_solid
        flux["river_water_m3"] += river_water
        flux["river_solid_m3"] += river_solid
        target = np.maximum(level - bed, 0.) * wet * area
        # Previously wet connected accounts can ebb; isolated inland pools cannot.
        exchange_support = wet | _connected(bed, mean + amplitude + 1.e-9, masks["ocean_mask"], valid)
        exchange = (target - water) * (-np.expm1(-step / PARAMETERS["exchange_timescale_s"])) * exchange_support * active
        concentration = np.divide(salt, water, out=np.zeros(shape), where=water > 0.)
        salt_exchange = np.where(exchange >= 0., exchange * ocean_salt, exchange * concentration)
        water += exchange
        salt += salt_exchange
        flux["tide_water_m3"] += exchange
        flux["tide_salt_kg"] += salt_exchange
        flux["flood_water_m3"] += np.maximum(exchange, 0.)
        flux["ebb_water_m3"] += np.maximum(-exchange, 0.)
        soil_water = np.minimum(water, soil_rate * step)
        mixed_salt = np.divide(salt, water, out=np.zeros(shape), where=water > 0.)
        soil_salt = soil_water * mixed_salt
        water -= soil_water
        salt -= soil_salt
        flux["soil_water_m3"] += soil_water
        flux["soil_salt_kg"] += soil_salt
        if wave_height > 0. and step > 0.:
            # Along-isobath wave drift from the same reduced coastal closure.
            gz, gx = np.gradient(bed, float(context["spacing_m"]))
            norm = np.maximum(np.hypot(gx, gz), 1.e-12)
            tx, tz = -gz / norm, gx / norm
            along = direction[0] * tx + direction[1] * tz
            fraction = np.full(shape, -np.expm1(-wave_height * step / PARAMETERS["wave_transfer_timescale_s"]))
            inventory, change, gross = _face_transfer(inventory, along * tx, along * tz,
                fraction, active.astype(float), wet, wet)
            flux["wave_bed_transfer_m3"] += change
            gross_wave += gross
        bed = old["bed_m"] + (inventory - old["bed_solid_m3"]) / (area * (1. - PARAMETERS["porosity"]))
    concentration = np.divide(salt, water, out=np.zeros(shape), where=water > 0.)
    output = {"water_m3": water, "salt_kg": salt, "bed_solid_m3": inventory,
              "bed_m": bed, "time_s": old["time_s"] + dt_s}
    ledger = {"river_water_input_m3": float(flux["river_water_m3"].sum()),
              "river_solid_input_m3": float(flux["river_solid_m3"].sum()),
              "signed_ocean_water_m3": float(flux["tide_water_m3"].sum()),
              "signed_ocean_salt_kg": float(flux["tide_salt_kg"].sum()),
              "soil_water_export_m3": float(flux["soil_water_m3"].sum()),
              "soil_salt_export_kg": float(flux["soil_salt_kg"].sum()),
              "gross_wave_transfer_solid_m3": gross_wave}
    ledger["water_residual_m3"] = float((old["water_m3"] + flux["river_water_m3"] + flux["tide_water_m3"] - flux["soil_water_m3"] - water).sum())
    ledger["salt_residual_kg"] = float((old["salt_kg"] + flux["tide_salt_kg"] - flux["soil_salt_kg"] - salt).sum())
    ledger["solid_residual_m3"] = float((old["bed_solid_m3"] + flux["river_solid_m3"] - inventory).sum())
    flux.update(salinity_kg_m3=concentration, water_stage_m=bed + water / area,
                wet_fraction=(water > 1.e-12).astype(float), tide_level_m=np.full(shape, level))
    return {"state": output, "fluxes": flux, "ledger": ledger,
            "metadata": metadata(ALGORITHM, context, dt_s,
            ["reduced connected prism; no dynamic backwater, 2D wave momentum, refraction or long-term shoreline certification",
             "ocean_mask is explicit external reservoir support, not inferred scene-edge outlet",
             "river boundary volumes are already routed and must be debited upstream exactly once",
             "solid transfers closed at patch perimeter; bedrock below finite mobile inventory immobile"], PARAMETERS.copy())}


initialize = initialize_coastal_exchange
step = advance_coastal_exchange
