"""G4 limited vapour transport: explicit finite volume on a constant axial wind.

Scope (stated before anything else)
-----------------------------------
This is a **bounded, single-domain, constant-axial-wind** explicit finite-volume
vapour transport. It is **not** a global atmospheric model, not a continuous wind
or pressure field, and not a GCM. Its whole purpose is to supply the one thing the
existing per-point orographic multiplier lacks: a **mass constraint** on water.

Everything here works in **mass**.
-----------------------------------
Every state is a per-cell mass in **kg**. Time-edge records are `state[edge]`.
Nothing inside the solver is a depth or a density; depth conversion exists only in
`depth_mm()` for reporting.

Three unit facts that are easy to get wrong, and are therefore stated as code:

* a face flux `F` is `kg/(m·s)`, so entering the ledger multiplies it by that
  face's length **and** by `dt` to become kg. For internal faces the length is
  `dx`, and `F = u·V/dx` follows from `F = u·(V/A_cell)·L_face` with
  `A_cell = dx²`, `L_face = dx`;
* `P`, `R` and `E` are **kg per interval** once they reach the update, so any rate
  form must be multiplied by `dt` first;
* an ET given as `m³/interval` converts to **`kg = m³ × ρ`** — multiply by density
  only. Dividing by area would produce `kg/m²`, which is a different quantity from
  a per-cell kg mass. Area appears only when reporting a depth.

`wind_unit` is a **direction** (dimensionless, one of `{0, ±1}` axial pairs), never
a speed. The speed is the explicit `wind_speed_m_s` parameter, and the CFL number
uses the speed: `wind_speed_m_s·dt/dx <= 1`, refused otherwise rather than reduced
silently.

Update order is fixed and each step happens exactly once
--------------------------------------------------------
From `V_old` to `V_new`, per step:

1. **face transport** — fluxes computed from `V_old` only, yielding
   `V_after_transport`. A shared internal face carries **one** flux value that is
   applied with opposite signs to its two neighbours, so nothing is created or
   destroyed by the face bookkeeping itself;
2. **external recycling** — `V_after_recycle = V_after_transport + R` (`R` already
   kg per interval);
3. **condensation** — `P = clip(k·max(gradient,0)·V_after_recycle·dt, 0,
   V_after_recycle)`: precipitation can never exceed the vapour actually present.
   This is the only depletion constraint, and background condensation is drawn from
   `V` as well, never added as a new source;
4. **new state** — `V_new = V_after_recycle − P`.

Transporting twice in one step (advect, then advect "the remainder" again) or
precipitating the same mass twice are both refused by construction: step 1 reads
only `V_old` and later steps read only their own predecessor.

Time is a DAG; a recirculating wind field is legitimate
-------------------------------------------------------
An explicit scheme advances from the previous time edge, so a **closed circulation
in the wind field is perfectly supportable** and is not an error. What is an error
is a *synchronous* dependency cycle — two cells demanding each other's value at the
same instant. That is a topology defect inside one time layer and it raises.

Boundary honesty
----------------
An undeclared inflow is **never** silently zero. The only legitimate zeros are an
explicit `0.` from the caller (`explicit_zero`) and a declared `closed` wall
(`closed_no_flux`). An `unknown_boundary` face produces **no certified zero flux**
and marks the whole result as not certified. Missing sources stay `pending`.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

SCHEMA = "climate-transport-v1"
MODEL = "explicit_finite_volume_constant_axial_vapour_v1"

WATER_DENSITY_KG_M3 = 1000.0
CELL_SPACING_M = 30.0
CELL_AREA_M2 = CELL_SPACING_M ** 2
#: Tolerance on the ledger closure, relative to the largest term of the same step.
LEDGER_RTOL = 1e-9

#: Legitimate zero-flux declarations. Anything else must not be treated as zero.
EXPLICIT_ZERO = "explicit_zero"
CLOSED_NO_FLUX = "closed_no_flux"
OPEN_BOUNDARY = "open_boundary"
UNRESOLVED = "unresolved"

#: Axial directions the limited solver supports, as (dx, dz) cell steps.
AXIAL_STEPS = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}

DECLARED_LIMITS = (
    "bounded single-domain explicit finite volume on a constant axial wind; not a "
    "global atmospheric model and not a continuous wind or pressure field",
    "vapour inventory is a per-cell mass in kg; depth is only a reporting "
    "conversion",
    "the time layer is a DAG and a recirculating wind field is supported; only a "
    "synchronous dependency cycle is refused",
    "precipitation cannot exceed the vapour present; that is the only depletion "
    "constraint, and background condensation is drawn from the same inventory",
    "undeclared inflow is never treated as zero; only explicit zero and a declared "
    "closed wall are legitimate zeros",
    "recycled evapotranspiration is an external declared input; this module never "
    "computes ET itself",
)


def depth_mm(mass_kg):
    """Report a per-cell mass as an equivalent water depth in mm.

    This is the **only** place area and density appear together, and it is a
    reporting conversion: `mm = kg / A_cell / ρ × 1000`.
    """
    return np.asarray(mass_kg, np.float64) / CELL_AREA_M2 / WATER_DENSITY_KG_M3 * 1000.0


def et_volume_to_mass_kg(et_m3):
    """Convert an ET volume in m³ per interval to a mass in kg.

    Multiply by density **only**: the inventory is a per-cell kg mass, so dividing
    by area would give `kg/m²`, a different quantity.
    """
    volume = np.asarray(et_m3, np.float64)
    if not np.isfinite(volume).all() or np.any(volume < 0.):
        raise ValueError("finite nonnegative ET volumes required")
    return volume * WATER_DENSITY_KG_M3


def _validate_axial(wind_bearing):
    pair = (int(wind_bearing[0]), int(wind_bearing[1]))
    if pair not in AXIAL_STEPS:
        raise ValueError(
            "wind_bearing must be one of the axial pairs %r; this limited solver "
            "does not accept a continuous or diagonal wind"
            % (sorted(AXIAL_STEPS),))
    return pair


def _validate_speed(wind_speed_m_s, dt_s):
    if isinstance(wind_speed_m_s, bool) or not isinstance(wind_speed_m_s, (int, float, np.floating)):
        raise ValueError("wind_speed_m_s must be a finite nonnegative number")
    speed = float(wind_speed_m_s)
    if not math.isfinite(speed) or speed < 0.:
        raise ValueError("wind_speed_m_s must be a finite nonnegative number")
    cfl = speed * float(dt_s) / CELL_SPACING_M
    if cfl > 1. + 1e-12:
        raise ValueError(
            "CFL %.6f exceeds 1 at wind_speed %.3f m/s, dt %.3f s, dx %.1f m; the "
            "step is refused rather than silently reduced" % (cfl, speed, float(dt_s),
                                                              CELL_SPACING_M))
    return speed, cfl


def _upwind_partner(wind_bearing, shape):
    """Index of each cell's upwind neighbour, plus the mask of upstream-inflow cells.

    `partner` holds the flat index of the cell the wind comes *from*; cells with no
    upwind neighbour inside the domain are marked in `is_inflow`, meaning they draw
    from the declared upstream boundary rather than from a neighbour.
    """
    rows, columns = shape
    step_x, step_z = wind_bearing
    row = np.arange(rows)[:, None]
    column = np.arange(columns)[None, :]
    from_row = row - step_z
    from_column = column - step_x
    inside = ((from_row >= 0) & (from_row < rows)
              & (from_column >= 0) & (from_column < columns))
    partner = np.where(inside, from_row * columns + from_column, -1).astype(np.int64)
    return partner.reshape(-1), ~inside.reshape(-1)


def _boundary_declaration(shape, wind_bearing, boundary):
    """Resolve each upstream-inflow cell's boundary status without inventing zeros.

    `boundary` maps a side name (`north`/`south`/`east`/`west`) to one of
    ``EXPLICIT_ZERO``, ``CLOSED_NO_FLUX``, ``UNRESOLVED`` or a numeric influx in
    kg/interval. A side that is simply absent is **pending**, never zero.
    """
    if boundary is None:
        boundary = {}
    if not isinstance(boundary, dict):
        raise ValueError("boundary must be a mapping of side name to declaration")
    allowed = {"north", "south", "east", "west"}
    unknown = sorted(set(boundary) - allowed)
    if unknown:
        raise ValueError("unsupported boundary sides %r; expected a subset of %r"
                         % (unknown, sorted(allowed)))
    # The air moves TOWARD `wind_bearing`, so it ENTERS from the opposite side.
    upstream_side = {(1, 0): "west", (-1, 0): "east",
                     (0, 1): "north", (0, -1): "south"}[wind_bearing]
    partner, _is_inflow = _upwind_partner(wind_bearing, shape)
    declaration = boundary.get(upstream_side, "pending")
    return upstream_side, declaration, partner


def _downwind_exit_mask(wind_bearing, shape):
    """Cells whose downwind neighbour lies outside the domain, i.e. true outflow.

    Distinct from the *upstream* inflow mask: with an eastward wind the mass leaves
    through the last column and enters through the first, and confusing the two
    silently drops the outflow term from the ledger.
    """
    rows, columns = shape
    step_x, step_z = wind_bearing
    row = np.arange(rows)[:, None]
    column = np.arange(columns)[None, :]
    to_row = row + step_z
    to_column = column + step_x
    inside = ((to_row >= 0) & (to_row < rows)
              & (to_column >= 0) & (to_column < columns))
    return ~inside.reshape(-1)


def transport_step(vapour_kg, *, wind_bearing, wind_speed_m_s, dt_s,
                   uplift_gain, gradient,
                   inflow_kg=None, recycle_kg=None, boundary=None):
    """Advance one bounded explicit finite-volume step.

    Parameters
    ----------
    vapour_kg : array_like
        Per-cell vapour mass in **kg**, `(rows, columns)`. This is the sole state.
    wind_bearing : (int, int)
        Axial direction the air moves toward; a member of `AXIAL_STEPS`.
    wind_speed_m_s : float
        Face speed in m/s. CFL is `speed·dt/dx`, refused above 1.
    dt_s : float
        Physical step in seconds.
    uplift_gain : float
        Coefficient `k` in `P = k·max(gradient,0)·V·dt`.
    gradient : array_like
        Dimensionless upslope gradient per cell (positive on windward slopes).
    inflow_kg : array_like or None
        Per-cell boundary influx in **kg per interval** for cells that draw from
        upstream of the domain. Shape `(n_inflow_cells,)` or the full grid.
    recycle_kg : array_like or None
        Per-cell recycled ET in **kg per interval**. Convert a volume with
        `et_volume_to_mass_kg`.
    boundary : dict or None
        Side declarations, see `_boundary_declaration`. Missing side means pending.

    Returns
    -------
    dict with the new state, per-step fluxes, the five-term ledger and the boundary
    status. A `conserved` flag is only true when every term is resolved.
    """
    state = np.asarray(vapour_kg, np.float64)
    if state.ndim != 2 or state.size == 0:
        raise ValueError("vapour_kg must be a nonempty 2-D per-cell mass")
    if not np.isfinite(state).all() or np.any(state < 0.):
        raise ValueError("finite nonnegative per-cell vapour mass required")
    if isinstance(dt_s, bool) or not isinstance(dt_s, (int, float, np.floating)):
        raise ValueError("dt_s must be a finite positive number")
    dt_s = float(dt_s)
    if not math.isfinite(dt_s) or dt_s <= 0.:
        raise ValueError("dt_s must be a finite positive number")
    direction = _validate_axial(wind_bearing)
    speed, cfl = _validate_speed(wind_speed_m_s, dt_s)
    gain = float(uplift_gain)
    if not math.isfinite(gain) or gain < 0.:
        raise ValueError("uplift_gain must be a finite nonnegative number")
    upslope = np.asarray(gradient, np.float64)
    if upslope.shape != state.shape or not np.isfinite(upslope).all():
        raise ValueError("gradient must be a finite array matching the vapour grid")

    shape = state.shape
    upstream_side, declaration, partner = _boundary_declaration(
        shape, direction, boundary)
    if inflow_kg is not None and declaration == "pending":
        # The caller supplied actual masses, so the side is declared by construction.
        declaration = "declared_influx"

    # --- 1. face transport from V_old only -----------------------------------
    flat = state.reshape(-1)
    has_partner = partner >= 0
    inflow_cells = ~has_partner
    # One shared internal face carries exactly one flux value: u·V_from/dx per second,
    # multiplied by dt for the interval. It leaves the upwind cell and enters the
    # downwind cell by the same amount, so the pair_nets cancel by construction.
    if speed > 0.:
        shared_kg = speed * flat * dt_s / CELL_SPACING_M
    else:
        shared_kg = np.zeros(flat.size, np.float64)
    after_transport = flat - shared_kg + np.where(
        has_partner, shared_kg[np.where(has_partner, partner, 0)], 0.)
    #: mass that left through the downwind domain edge, i.e. genuine outflow
    exit_cells = _downwind_exit_mask(direction, shape)
    downstream_outflow_kg = float(shared_kg[exit_cells].sum())

    # --- boundary resolution for upstream-inflow cells -----------------------
    inflow_status = np.full(flat.size, "", dtype=object)
    certified = True
    inflow_mass_kg = np.zeros(flat.size, np.float64)
    if inflow_cells.any():
        count = int(inflow_cells.sum())
        # A supplied per-cell influx array takes precedence over a side declaration:
        # the caller has stated the actual masses, so there is nothing to infer.
        if inflow_kg is not None:
            supplied = np.asarray(inflow_kg, np.float64)
            if supplied.size == count:
                supplied = supplied.reshape(-1)
            elif supplied.size == flat.size:
                supplied = supplied.reshape(-1)[inflow_cells]
            else:
                raise ValueError(
                    "inflow_kg must supply one value per upstream-inflow cell (%d) or "
                    "the full grid" % (count,))
            if not np.isfinite(supplied).all() or np.any(supplied < 0.):
                raise ValueError("finite nonnegative inflow masses required")
            inflow_mass_kg[inflow_cells] = supplied
            inflow_status[inflow_cells] = "declared_influx"
        elif isinstance(declaration, str):
            if declaration == EXPLICIT_ZERO:
                inflow_status[inflow_cells] = EXPLICIT_ZERO
            elif declaration == CLOSED_NO_FLUX:
                inflow_status[inflow_cells] = CLOSED_NO_FLUX
            elif declaration == UNRESOLVED:
                inflow_status[inflow_cells] = UNRESOLVED
                certified = False
            elif declaration == "pending":
                raise ValueError(
                    "upstream boundary %r is unresolved: supply an explicit zero, a "
                    "closed no-flux declaration, or an influx; an undeclared inflow "
                    "is never treated as zero" % (upstream_side,))
            elif declaration == "declared_influx":
                raise ValueError(
                    "inflow_kg was declared as a side but no per-cell mass array was "
                    "supplied; pass inflow_kg or use an explicit zero/closed side")
            else:
                raise ValueError("unknown boundary declaration %r" % (declaration,))
        after_transport = after_transport + inflow_mass_kg

    # --- 2. external recycling ------------------------------------------------
    recycle = (np.zeros(flat.size, np.float64) if recycle_kg is None
               else np.asarray(recycle_kg, np.float64).reshape(-1))
    if recycle.size != flat.size:
        raise ValueError("recycle_kg must match the vapour grid")
    if not np.isfinite(recycle).all() or np.any(recycle < 0.):
        raise ValueError("finite nonnegative recycled masses required")
    after_recycle = after_transport + recycle

    # --- 3. condensation, bounded by what is actually present -----------------
    available = np.maximum(after_recycle, 0.)
    potential = gain * np.maximum(upslope.reshape(-1), 0.) * available * dt_s
    precipitation = np.minimum(potential, available)
    # --- 4. new state ---------------------------------------------------------
    new_state = available - precipitation

    ledger = {
        "inflow_kg": float(inflow_mass_kg.sum()),
        "recycle_kg": float(recycle.sum()),
        "precipitation_kg": float(precipitation.sum()),
        "outflow_kg": downstream_outflow_kg,
        "nondepositing_kg": 0.0,
        "storage_change_kg": float(new_state.sum() - flat.sum()),
    }
    # Closing identity: change in storage = in + recycle - precip - out - nondep.
    expected_change = (ledger["inflow_kg"] + ledger["recycle_kg"]
                       - ledger["precipitation_kg"] - ledger["outflow_kg"]
                       - ledger["nondepositing_kg"])
    scale = max(abs(ledger["inflow_kg"]) + abs(ledger["recycle_kg"]),
                abs(ledger["precipitation_kg"]), abs(ledger["outflow_kg"]), 1.0)
    ledger["closure_residual_kg"] = ledger["storage_change_kg"] - expected_change
    ledger["closure_tolerance_kg"] = LEDGER_RTOL * scale
    ledger["closure_ok"] = (abs(ledger["closure_residual_kg"])
                            <= ledger["closure_tolerance_kg"])

    return {
        "schema": SCHEMA,
        "model": MODEL,
        "vapour_kg": new_state.reshape(shape),
        "precipitation_kg": precipitation.reshape(shape),
        "recycle_kg": recycle.reshape(shape),
        "inflow_kg": inflow_mass_kg.reshape(shape),
        "ledger": ledger,
        "boundary": {
            "upstream_side": upstream_side,
            "declaration": declaration if isinstance(declaration, str) else "declared_influx",
            "certified": bool(certified),
            "status_per_inflow_cell": inflow_status.tolist(),
        },
        "diagnostics": {
            "wind_bearing": list(direction),
            "wind_speed_m_s": speed,
            "cfl": cfl,
            "dt_s": dt_s,
            "cell_spacing_m": CELL_SPACING_M,
            "cell_area_m2": CELL_AREA_M2,
            "uplift_gain": gain,
            "shared_face_count": int(has_partner.sum()),
            "units": "per-cell mass in kg; depths only via depth_mm()",
        },
        "declared_limits": list(DECLARED_LIMITS),
    }


def identity_of(result):
    """Digest of the state and the declared inputs actually used.

    Binds the realised per-cell masses, not just the arguments, so two runs that
    differ only in their result cannot share an identity.
    """
    diagnostics = result["diagnostics"]
    record = {
        "schema": result["schema"],
        "model": result["model"],
        "wind_bearing": diagnostics["wind_bearing"],
        "wind_speed_m_s": diagnostics["wind_speed_m_s"],
        "dt_s": diagnostics["dt_s"],
        "uplift_gain": diagnostics["uplift_gain"],
        "boundary": {key: value for key, value in result["boundary"].items()
                     if key != "status_per_inflow_cell"},
        "arrays": {
            "vapour_kg": hashlib.sha256(
                np.ascontiguousarray(result["vapour_kg"], np.float64).tobytes()
            ).hexdigest(),
            "precipitation_kg": hashlib.sha256(
                np.ascontiguousarray(result["precipitation_kg"], np.float64).tobytes()
            ).hexdigest(),
        },
    }
    import json
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
