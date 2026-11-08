"""G8 bounded basin ocean core: conservative water and heat transport.

Scope, stated first
-------------------
This is a **finite, explicitly bounded ocean basin**: a declared connected wet mask, a
declared depth per cell, and explicit boundary faces. It is **not** a global ocean, not
a general circulation model, and not a momentum/Navier-Stokes solver.

What it deliberately is *not*
-----------------------------
* **No random warm/cold current labels.** Flow comes from a declared wind bearing and
  speed acting on real per-cell depth; the resulting face fluxes are non-zero, bounded,
  and auditable.
* **No salinity.** No salt state is built here, so no salt budget is claimed. A later
  card that adds salt must add its own conservative account; this one never implies it.
* **No diffusion dressed up as circulation.** Heat moves only with the conservative
  face advection below. Spreading sea-surface temperature by a diffusion operator and
  calling it a current is exactly what this module refuses to do.

Water account
-------------
Every cell holds a volume in m³. A shared internal face carries **one** per-step
transported **volume in m³** that is applied with opposite signs to its two
neighbours, so the face bookkeeping itself cannot create or destroy water.

Note the distinction the field names keep: the quantity is **volume moved during the
step**, not a rate. It is `speed·dt/dx · V_upwind`, so `dt` is already inside it. A
caller must not multiply by `dt` a second time; anyone wanting a discharge in m³/s must
divide by `dt` explicitly.

An open boundary face discharges out of the **geometric domain edge** and is booked as
outflow. A land coast is **never** used as an open drain: only a face that leaves the
declared grid can be `open`, and a wet cell bordering land is either `closed` or has no
exit at all.

Heat account
------------
Heat moves with the water, on the **upwind** value, and is never re-diffused:

    Δ(V·T)_cell = Σ(inflow·T_upwind) − Σ(outflow·T_cell)

The transported quantity is therefore `m³·°C` — a **relative heat content** under a
constant specific heat, with the reference at 0 °C. It is *not* an absolute energy in
joules. Reporting joules requires multiplying by an explicit `ρ·c_p`:

    energy_J = (V·T)[m³·°C] · ρ·c_p [J/(m³·°C)]

and even then the value is referenced to 0 °C. `SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K`
is declared so that conversion is possible; the ledger below never claims to be in
joules.

Negative temperatures are legitimate (the reference is 0 °C), so the heat scale used for
the tolerance is `Σ|V·T|`, not `|Σ V·T|`: a basin straddling 0 °C must not get an
artificially tiny tolerance just because its signed total happens to cancel.

Shore and land
--------------
A land cell is never transported through: an internal face requires **both** cells wet.
Two wet basins separated by land therefore stay separate, and neither can drain into the
other around a shore.

CFL
---
The speed is a **prescribed current speed derived from a declared wind proxy**, not a
solved wind stress or momentum balance. The scheme requires
`wind_speed_m_s · dt_s / dx ≤ 1`, refused otherwise rather than silently reduced.
"""

from __future__ import annotations

import math

import numpy as np

SCHEMA = "bounded-ocean-coast-v1"
MODEL = "bounded_basin_wind_driven_conservative_water_heat_v1"

#: Declared volumetric heat capacity of seawater, J/(m³·K). Reported, not folded in.
SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K = 4.0e6
#: Toleration on the closing residuals, relative to the largest term of the same step.
LEDGER_RTOL = 1e-9

OPEN = "open"
CLOSED = "closed"

AXIAL_STEPS = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}

DECLARED_LIMITS = (
    "finite declared basin; not a global ocean and not a general circulation model",
    "no salinity state and therefore no salt budget is claimed",
    "heat moves only by conservative upwind advection with the water; sea-surface "
    "temperature is never produced by a diffusion operator and called a current",
    "flow is driven by a declared wind bearing and speed, not by a random warm/cold "
    "label",
    "a land cell is never transported through; basins separated by land stay separate",
)


def water_volume_m3(depth_m, wet_mask, spacing_m):
    """Per-cell water volume in m³ on the declared wet cells; land is exactly zero."""
    depth = np.asarray(depth_m, np.float64)
    wet = np.asarray(wet_mask, bool)
    if depth.shape != wet.shape or depth.ndim != 2:
        raise ValueError("depth_m and wet_mask must be matching 2-D arrays")
    if not np.isfinite(depth).all() or np.any(depth < 0.):
        raise ValueError("finite nonnegative depth required")
    if np.any(depth[~wet] != 0.):
        raise ValueError("land cells must declare exactly zero depth")
    return np.where(wet, depth, 0.) * float(spacing_m) ** 2


def _validate_axial(wind_bearing):
    pair = (int(wind_bearing[0]), int(wind_bearing[1]))
    if pair not in AXIAL_STEPS:
        raise ValueError("wind_bearing must be one of the axial pairs %r; a diagonal "
                         "or continuous wind is not accepted here"
                         % (sorted(AXIAL_STEPS),))
    return pair


def _validate_cfl(wind_speed_m_s, dt_s, spacing_m):
    for name, value in (("wind_speed_m_s", wind_speed_m_s), ("dt_s", dt_s),
                        ("spacing_m", spacing_m)):
        if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)):
            raise ValueError("%s must be a finite positive number" % name)
        if not math.isfinite(float(value)):
            raise ValueError("%s must be finite" % name)
    speed, dt, dx = float(wind_speed_m_s), float(dt_s), float(spacing_m)
    if speed < 0. or dt <= 0. or dx <= 0.:
        raise ValueError("nonnegative speed and positive dt/dx required")
    cfl = speed * dt / dx
    if cfl > 1. + 1e-12:
        raise ValueError("CFL %.6f exceeds 1 (speed %.3f m/s, dt %.3f s, dx %.2f m); "
                         "the step is refused rather than silently reduced"
                         % (cfl, speed, dt, dx))
    return speed, cfl


def _neighbour_index(wind_bearing, shape):
    """Flat index of each cell's downwind neighbour, and the mask of exit cells."""
    rows, columns = shape
    step_x, step_z = wind_bearing
    row = np.arange(rows)[:, None]
    column = np.arange(columns)[None, :]
    to_row = row + step_z
    to_column = column + step_x
    inside = ((to_row >= 0) & (to_row < rows)
              & (to_column >= 0) & (to_column < columns))
    index = np.where(inside, to_row * columns + to_column, -1).astype(np.int64)
    return index.reshape(-1), inside.reshape(-1)


def transport_step(volume_m3, temperature_c, wet_mask, *, wind_bearing,
                   wind_speed_m_s, dt_s, spacing_m, boundary=OPEN):
    """One bounded conservative step of water and heat.

    Parameters
    ----------
    volume_m3 : array_like
        Per-cell water volume in m³, `(rows, columns)`. Land cells must be exactly 0.
    temperature_c : array_like
        Per-cell water temperature in °C on wet cells.
    wet_mask : array_like
        Boolean `(rows, columns)`. A land cell is never transported through.
    wind_bearing : (int, int)
        Axial direction the water is pushed toward.
    wind_speed_m_s, dt_s, spacing_m :
        Face speed, step, and cell spacing; CFL is `speed·dt/dx ≤ 1`.
    boundary : OPEN or CLOSED
        What happens at a wet cell whose downwind neighbour is land or outside.

    Returns
    -------
    dict
        New volume and temperature, per-step face discharge, the water and heat
        ledgers, and the diagnostics that make the step auditable.
    """
    volume = np.asarray(volume_m3, np.float64)
    temperature = np.asarray(temperature_c, np.float64)
    wet = np.asarray(wet_mask, bool)
    if not (volume.shape == temperature.shape == wet.shape) or volume.ndim != 2:
        raise ValueError("volume_m3, temperature_c and wet_mask must be matching 2-D")
    if not np.isfinite(volume).all() or np.any(volume < 0.):
        raise ValueError("finite nonnegative volume required")
    if not np.isfinite(temperature).all():
        raise ValueError("finite temperature required")
    if np.any(volume[~wet] != 0.):
        raise ValueError("land cells must declare exactly zero volume")
    if boundary not in (OPEN, CLOSED):
        raise ValueError("boundary must be %r or %r" % (OPEN, CLOSED))
    direction = _validate_axial(wind_bearing)
    speed, cfl = _validate_cfl(wind_speed_m_s, dt_s, spacing_m)
    spacing = float(spacing_m)

    shape = volume.shape
    flat_volume = volume.reshape(-1)
    flat_wet = wet.reshape(-1)
    flat_temperature = temperature.reshape(-1)
    partner, inside = _neighbour_index(direction, shape)

    # --- face discharge: one value per shared face ----------------------------
    # A face may only move water that (a) exists upwind and (b) has a wet downwind
    # cell. `inside` already excludes land/outside partners, so nothing crosses land.
    open_face = flat_wet & inside & np.where(partner >= 0, flat_wet[
        np.where(partner >= 0, partner, 0)], False)
    face_discharge = np.where(
        open_face, speed * dt_s / spacing * flat_volume, 0.)
    # Bounded by what the upwind cell actually holds: never more than its own volume.
    face_discharge = np.minimum(face_discharge, flat_volume)

    outflow = np.zeros(flat_volume.size, np.float64)
    inflow = np.zeros(flat_volume.size, np.float64)
    if face_discharge.any():
        outflow += face_discharge
        # The same face value enters the downwind cell: opposite signs, one number.
        receiving = partner[open_face]
        np.add.at(inflow, receiving, face_discharge[open_face])

    # --- exit faces: leaving the declared grid ONLY ---------------------------
    # `inside` already means "the downwind neighbour is a cell of this grid". So
    # `wet & ~inside` is exactly "downwind is off-grid", and a wet cell whose downwind
    # neighbour is land *inside* the grid is not in it. A land coast therefore never
    # acts as an open drain: shore cells retain their water instead of leaking into
    # land, which is what keeps a land-separated basin closed.
    exit_face = flat_wet & ~inside
    exit_discharge = np.zeros(flat_volume.size, np.float64)
    if boundary == OPEN and exit_face.any():
        exit_discharge[exit_face] = np.minimum(
            speed * dt_s / spacing * flat_volume[exit_face], flat_volume[exit_face])
    outflow += exit_discharge

    new_volume = flat_volume - outflow + inflow

    # --- heat travels with the water on the upwind value ----------------------
    # Outflow heat is the sum of the two discharge kinds, each carrying the temperature
    # of the cell it leaves. Computed once, from the same arrays the water used.
    heat_outflow = (np.where(face_discharge > 0., face_discharge * flat_temperature, 0.)
                    + exit_discharge * flat_temperature)
    heat_inflow = np.zeros(flat_volume.size, np.float64)
    if face_discharge.any():
        np.add.at(heat_inflow, partner[open_face],
                  face_discharge[open_face] * flat_temperature[open_face])

    old_heat = flat_volume * flat_temperature
    new_heat = old_heat - heat_outflow + heat_inflow
    new_temperature = np.divide(new_heat, new_volume, out=np.zeros_like(new_heat),
                                where=new_volume > 0.)

    # --- ledgers ---------------------------------------------------------------
    water_change = float(new_volume.sum() - flat_volume.sum())
    water_outflow_total = float(exit_discharge.sum())   # only true boundary loss
    heat_change = float(new_heat.sum() - old_heat.sum())
    heat_outflow_total = float((exit_discharge * flat_temperature).sum())
    scale = max(float(flat_volume.sum()), 1.0)
    # Magnitude-based scale: a basin straddling 0 degC must not get a tiny tolerance
    # merely because its signed total happens to cancel.
    heat_scale = max(float(np.abs(old_heat).sum()), 1.0)
    ledger = {
        "water_start_m3": float(flat_volume.sum()),
        "water_end_m3": float(new_volume.sum()),
        "water_change_m3": water_change,
        "boundary_outflow_m3": water_outflow_total,
        "internal_transported_volume_m3": float(face_discharge.sum()),
        "heat_start_m3_degc": float(old_heat.sum()),
        "heat_end_m3_degc": float(new_heat.sum()),
        "heat_change_m3_degc": heat_change,
        "boundary_heat_outflow_m3_degc": heat_outflow_total,
        "heat_reference": "0 degC; constant specific heat; NOT joules",
        "heat_capacity_j_m3k_if_converted": SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K,
        "heat_energy_j_if_converted": float(new_heat.sum())
        * SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K,
        "water_tolerance_m3": LEDGER_RTOL * scale,
        "heat_tolerance_m3_degc": LEDGER_RTOL * heat_scale,
    }
    # Water closes once the boundary loss is booked: change = -loss.
    ledger["water_residual_m3"] = water_change + water_outflow_total
    ledger["water_ok"] = abs(ledger["water_residual_m3"]) <= ledger["water_tolerance_m3"]
    ledger["heat_residual_m3_degc"] = heat_change + heat_outflow_total
    ledger["heat_ok"] = (abs(ledger["heat_residual_m3_degc"])
                         <= ledger["heat_tolerance_m3_degc"])

    return {
        "schema": SCHEMA,
        "model": MODEL,
        "volume_m3": new_volume.reshape(shape),
        "temperature_c": new_temperature.reshape(shape),
        "transported_volume_m3": face_discharge.reshape(shape),
        "exit_volume_m3": exit_discharge.reshape(shape),
        "ledger": ledger,
        "diagnostics": {
            "wind_bearing": list(direction),
            "prescribed_current_speed_from_declared_wind_proxy_m_s": speed,
            "wind_stress_solved": False,
            "dt_s": float(dt_s),
            "spacing_m": spacing,
            "cfl": cfl,
            "boundary": boundary,
            "shared_face_count": int(open_face.sum()),
            "open_exit_count": int(exit_face.sum()),
            "open_boundary_means": "geometric domain edge only; a land coast is never "
                                  "an open drain",
            "heat_content_units": "m3*degC relative to 0 degC; not joules",
            "salinity": "not_modelled",
            "units": "volume m3; temperature degC; transported quantity is per step, "
                     "not a rate (divide by dt for m3/s)",
        },
        "declared_limits": list(DECLARED_LIMITS),
    }
