# -*- coding: utf-8 -*-
"""Bounded multi-year ice body: mass store, SIA flux on a short flowline, declared erosion proxy.

What this module is
-------------------
A **finite, bounded** ice-mass model on a short one-dimensional flowline of native 30 m cells:

* ice thickness is the state; the ice **surface is recomputed every step** as ``bed + thickness``
  (there is no independent surface field that could disagree with the ice);
* flow is the shallow-ice approximation (SIA) for **deformation (creep) only**. It is *not* basal
  sliding: no sliding law is implemented here, and nothing is called "sliding velocity";
* mass is conserved in three separate accounts: ice volume, liquid water, and — separately —
  rock removed from a **finite, explicitly supplied** bedrock stock;
* a declared erosion proxy produces a derived ``bed_delta_m``. It is returned, never written back
  into any TD bed, and it is not presented as a coupled bed-feedback result.

The SIA flux, with units
------------------------
For a flowline along ``x`` with fixed width ``W``, thickness ``H`` and surface ``s = bed + H``:

    q(face) = W * (2A / (n + 2)) * (rho g)^n * H_f^(n + 2) * |ds/dx|^(n - 1) * (-ds/dx)

with

===========  ========================================  ==================================
symbol       meaning                                   unit
===========  ========================================  ==================================
``A``        creep parameter (Glen flow law)           Pa^-n s^-1
``n``        Glen exponent                             dimensionless (3 here)
``rho``      ice density                               kg m^-3
``g``        gravitational acceleration                m s^-2
``H_f``      mean of the two adjacent thicknesses     m
``ds/dx``    surface slope between the two cells       dimensionless (m m^-1)
``W``        cell width (flowline width)               m
``q``        volume flux through that face            m^3 s^-1
===========  ========================================  ==================================

``A`` is **not** a dimensionless fudge factor. ``A = 2.4e-24 Pa^-3 s^-1`` is the declared
typical Glen ``n = 3`` value; if a caller wants a lumped coefficient instead, it must say so and
carry its own dimensions, because ``(2A/(n+2)) * (rho g)^n`` is what is actually multiplied.
This module only accepts the dimensional ``A`` above.

Stability is explicit and declared
----------------------------------
The face diffusivity is ``D = (2A/(n+2)) (rho g)^n H_f^(n+2) |ds/dx|^(n-1)`` (m^2 s^-1), and the
step is bounded by ``dt <= CFL * dx^2 / D_max`` with ``CFL = 0.25``. An interval longer than
``MAX_SUBSTEPS * dt_limit`` is **refused** — the caller must refine, not ask this module to take an
unstable step. Within the limit the step is split into an integer number of fixed sub-steps, and
per-cell outgoing flux is clipped by the available volume (``min(flux, available)``) so thickness
can never go negative. Clipping is recorded, never silently applied as "flux = 0".

What is deliberately not here
-----------------------------
No basal sliding, no ice temperature, no three-dimensional state, no calving, no glacier-lake
outburst, no real-world glacier prediction, and no verdict that a given snow patch *is* a glacier.
A multi-year net loss or gain in this store says nothing about whether a glacier exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest

SCHEMA = "bounded-glacier-v1"
LOGICAL_VERSION = "bounded-ice-mass-flux-v1"
ALGORITHM = "sia-creep-flowline-v1"

GRAVITY_M_S2 = 9.80665
WATER_DENSITY_KG_M3 = 1000.0
CELL_AREA_M2 = 900.0
NATIVE_SPACING_M = 30.0
MAX_CELLS = 9
MIN_CELLS = 3
MAX_INTERVALS = 512
MAX_SUBSTEPS = 64
CFL = 0.25
MAX_THICKNESS_M = 500.0

FLOW_MODELS = ("shallow_ice", "none")
MOTION_FLOWING = "flowing"
MOTION_STATIONARY = "stationary_below_threshold"
MOTION_STATIC = "static_flow_model_none"

EROSION_PROXY_DECLARED = "erosion_proxy_declared"
EROSION_NOT_AVAILABLE = "not_available"

#: The unit of the Glen creep parameter. Stated as a field so a reader never has to pattern-match
#: a prose sentence to find out what ``creep_parameter_pa_n_s`` is measured in.
CREEP_PARAMETER_UNIT = "Pa^-n s^-1"
CREEP_PARAMETER_SEMANTICS = (
    "dimensional Glen creep parameter of the flow law; it is NOT a dimensionless lumped coefficient. "
    "A caller that wants a lumped coefficient must carry its own dimensions instead")
#: Erosion is a **declared proxy**, not a rock-ice conversion: the coefficient times the cumulative
#: absolute face ice flux is an explicit upper bound on the erodible volume, and the only conserved
#: supply is the separately supplied bedrock stock.
EROSION_PROXY_SEMANTICS = (
    "declared proxy: erosion volume = coefficient * cumulative |face ice flux|. That is an explicit "
    "upper bound, not a conversion of rock into ice or ice into rock; the only stock that is "
    "actually decremented is the supplied finite bedrock volume")

LIQUID_TO_LAND = "declared_land_port"
LIQUID_UNRESOLVED = "liquid_export_unresolved"

#: This model does not decide whether a snow/ice body **is** a glacier. A net-positive multi-year
#: balance is neither necessary nor sufficient: a net-negative body can still exist (it retreats),
#: and a body below the flow threshold is just multi-year snow/ice. Existence is out of scope.
GLACIER_EXISTENCE_POLICY = (
    "not_decided_here: a multi-year net balance (positive or negative) is not a glacier-existence "
    "criterion; this bounded store reports mass and flux only")

FORMULA_SOURCE = (
    "shallow ice approximation, deformation (creep) only, Glen flow law with exponent n; the "
    "flux form q = W (2A/(n+2)) (rho g)^n H^(n+2) |ds/dx|^(n-1) (-ds/dx) is the standard 1-D SIA "
    "discretisation on cell centres with mean face thickness and central surface slope. No basal "
    "sliding law is implemented, so no velocity here is a sliding velocity.")
LIMITATIONS = (
    "one-dimensional fixed-width flowline of 3..9 native 30 m cells; not a glacier inventory",
    "deformation-only SIA: no basal sliding, no hydrology, no thermodynamics, no calving",
    "the ice surface is recomputed as bed + thickness every step; there is no separate surface "
    "field that could disagree with the ice",
    "accumulation and ablation inputs are water-equivalent depths; ice volume is derived through "
    "both densities, so ice volume and water volume are never numerically equal",
    "the erosion proxy is declared and requires an explicit finite bedrock stock; without one the "
    "answer is not_available, never an unbounded bed",
    "derived bed_delta_m is returned only; no TD bed is written and no bed feedback is claimed",
    "no real-world glacier is predicted and the multi-year net balance is not a glacier-existence "
    "criterion",
    "the 1 m minimum spacing unit is a bound, not a claimed 1 m accuracy",
)


def _finite(value, name, *, minimum=None, maximum=None, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError("%s must be numeric" % name)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("%s must be finite" % name)
    if positive and number <= 0.0:
        raise ValueError("%s must be positive" % name)
    if nonnegative and number < 0.0:
        raise ValueError("%s must be nonnegative" % name)
    if minimum is not None and number < minimum:
        raise ValueError("%s must be >= %r" % (name, minimum))
    if maximum is not None and number > maximum:
        raise ValueError("%s must be <= %r" % (name, maximum))
    return number


@dataclass(frozen=True)
class GlacierParameters:
    """Declared engineering parameters; uncalibrated, and every value enters the identity."""

    ice_density_kg_m3: float = 917.0
    #: Glen creep parameter, **dimensional** (Pa^-n s^-1). Typical n=3 value, declared.
    creep_parameter_pa_n_s: float = 2.4e-24
    glen_exponent: int = 3
    #: Optional engineering cutoff. ``0`` (the default) means "never truncate on thickness".
    min_flow_thickness_m: float = 0.0
    max_thickness_m: float = MAX_THICKNESS_M
    #: Declared erosion proxy: rock volume per unit ice-flux work. Dimensionless multiplier over
    #: the flux volume, so ``erosion_m3 = coefficient * |flux_m3|``.
    erosion_proxy_coefficient: float = 1.0e-3

    def __post_init__(self):
        _finite(self.ice_density_kg_m3, "ice_density_kg_m3", positive=True)
        _finite(self.creep_parameter_pa_n_s, "creep_parameter_pa_n_s", positive=True)
        if self.glen_exponent not in (1, 2, 3, 4, 5):
            raise ValueError("glen_exponent must be a small positive integer")
        _finite(self.min_flow_thickness_m, "min_flow_thickness_m", nonnegative=True)
        _finite(self.max_thickness_m, "max_thickness_m", positive=True)
        _finite(self.erosion_proxy_coefficient, "erosion_proxy_coefficient", nonnegative=True)

    @property
    def densification(self):
        """Ice volume per unit water-equivalent depth, per unit area."""
        return WATER_DENSITY_KG_M3 / self.ice_density_kg_m3

    def identity(self):
        payload = asdict(self)
        payload["formula_source"] = FORMULA_SOURCE
        payload["densification"] = self.densification
        payload["creep_parameter_unit"] = CREEP_PARAMETER_UNIT
        payload["creep_parameter_semantics"] = CREEP_PARAMETER_SEMANTICS
        payload["glacier_existence_criterion"] = GLACIER_EXISTENCE_POLICY
        return payload


def _edges(time_edges_s):
    edges = np.asarray(time_edges_s, np.float64)
    if edges.ndim != 1 or edges.size < 2 or edges.size - 1 > MAX_INTERVALS:
        raise ValueError("time_edges_s must be 1D with 1..%d intervals" % MAX_INTERVALS)
    if not np.isfinite(edges).all() or np.any(np.diff(edges) <= 0.0):
        raise ValueError("time_edges_s must be finite and strictly increasing")
    return edges


def _grid(x_m, width_m):
    x = np.asarray(x_m, np.float64).reshape(-1)
    if x.size < MIN_CELLS or x.size > MAX_CELLS:
        raise ValueError("this bounded model handles %d..%d cells, got %d"
                         % (MIN_CELLS, MAX_CELLS, x.size))
    if not np.isfinite(x).all() or np.any(np.diff(x) <= 0.0):
        raise ValueError("x_m must be finite and strictly increasing along the flowline")
    dx = np.diff(x)
    if not np.allclose(dx, dx[0], rtol=0.0, atol=1e-9):
        raise ValueError("a uniform cell spacing is required; got %s" % list(dx))
    width = _finite(width_m, "width_m", positive=True)
    return x, float(dx[0]), width


def _per_cell(value, name, cells, *, nonnegative=True):
    array = np.asarray(value, np.float64)
    if array.shape != (cells,):
        raise ValueError("%s must be one value per cell" % name)
    if not np.isfinite(array).all():
        raise ValueError("%s must be finite" % name)
    if nonnegative and np.any(array < 0.0):
        raise ValueError("%s must be nonnegative" % name)
    return array


def _per_interval(value, name, intervals, cells, *, nonnegative=True):
    array = np.asarray(value, np.float64)
    if array.shape != (intervals, cells):
        raise ValueError("%s must be [intervals, cells] = [%d, %d], got %s"
                         % (name, intervals, cells, list(array.shape)))
    if not np.isfinite(array).all():
        raise ValueError("%s must be finite" % name)
    if nonnegative and np.any(array < 0.0):
        raise ValueError("%s must be nonnegative" % name)
    return array


def _face_flux(*, surface_m, thickness_m, dx_m, width_m, parameters):
    """SIA volume flux per face, in m^3 s^-1, positive towards increasing ``x``.

    Closed ends: the two outermost faces carry no flux, so this small grid is a bounded domain and
    nothing leaves it as ice. Liquid leaves only through the declared liquid port.
    """
    cells = thickness_m.size
    flux = np.zeros(cells + 1, np.float64)
    diffusivity = np.zeros(cells + 1, np.float64)
    if cells < 2:
        return flux, diffusivity
    n = parameters.glen_exponent
    prefactor = (2.0 * parameters.creep_parameter_pa_n_s / (n + 2.0)
                 * (parameters.ice_density_kg_m3 * GRAVITY_M_S2) ** n)
    slope = np.diff(surface_m) / dx_m
    mean_thickness = 0.5 * (thickness_m[:-1] + thickness_m[1:])
    positive = mean_thickness > 0.0
    magnitude = np.zeros_like(slope)
    if positive.any():
        magnitude[positive] = (prefactor * mean_thickness[positive] ** (n + 2)
                               * np.abs(slope[positive]) ** (n - 1) * (-slope[positive]))
    flux[1:-1] = width_m * magnitude
    # the SIA flux q = -(2A/(n+2)) (rho g)^n H^(n+2) |ds/dx|^(n-1) (ds/dx) per unit width is
    # exactly D * ds/dx with D = (2A/(n+2)) (rho g)^n H^(n+2) |ds/dx|^(n-1), so the explicit
    # diffusion stability limit CFL * dx^2 / D is the limit of this same operator.
    diffusivity[1:-1] = (prefactor * mean_thickness ** (n + 2)
                         * np.abs(slope) ** (n - 1))
    return flux, diffusivity


def _dt_limit(diffusivity, dx_m, cfl):
    peak = float(np.max(diffusivity)) if diffusivity.size else 0.0
    if peak <= 0.0:
        return math.inf
    return cfl * dx_m * dx_m / peak


def advance_glacier(*, thickness_start_m, bed_m, accumulation_mm, ablation_mm, time_edges_s,
                    x_m, width_m=NATIVE_SPACING_M, bedrock_erodible_m3=None,
                    land_port_mask=None, flow_model="shallow_ice", parameters=None):
    """Advance the bounded ice body over declared intervals, with closed lateral ends.

    ``accumulation_mm`` and ``ablation_mm`` are **water-equivalent depths per interval**. Ice
    volume is derived through ``water_mass = mm/1000 * area * rho_water`` then
    ``ice_volume = water_mass / rho_ice``, so ice volume and water volume are never equal.

    ``ablation_mm`` that melts ice produces liquid water back at water density. Where a cell has a
    declared land port (``land_port_mask``) that water is reported in ``melt_to_land_mm``;
    everywhere else it is reported in ``liquid_export_unresolved_mm``. Ice is never removed
    without the water being accounted for somewhere.

    ``bedrock_erodible_m3`` is an explicit **finite** bedrock stock per cell. Without it the
    erosion answer is ``not_available`` and no rock is removed.
    """
    edges = _edges(time_edges_s)
    intervals = int(edges.size - 1)
    parameters = GlacierParameters() if parameters is None else parameters
    if not isinstance(parameters, GlacierParameters):
        raise ValueError("parameters must be GlacierParameters")
    if flow_model not in FLOW_MODELS:
        raise ValueError("flow_model must be one of %s" % (FLOW_MODELS,))
    x, dx, width = _grid(x_m, width_m)
    cells = x.size
    thickness = _per_cell(thickness_start_m, "thickness_start_m", cells)
    bed = _per_cell(bed_m, "bed_m", cells, nonnegative=False)
    if np.any(thickness > parameters.max_thickness_m):
        raise ValueError("the initial thickness exceeds the declared ceiling %r m"
                         % parameters.max_thickness_m)
    accumulation = _per_interval(accumulation_mm, "accumulation_mm", intervals, cells)
    ablation = _per_interval(ablation_mm, "ablation_mm", intervals, cells)

    if bedrock_erodible_m3 is None:
        rock_stock = None
        erosion_status = EROSION_NOT_AVAILABLE
    else:
        rock_stock = _per_cell(bedrock_erodible_m3, "bedrock_erodible_m3", cells)
        erosion_status = EROSION_PROXY_DECLARED
    if land_port_mask is None:
        land_port = np.zeros(cells, np.bool_)
    else:
        land_port = np.asarray(land_port_mask, np.bool_)
        if land_port.shape != (cells,):
            raise ValueError("land_port_mask must be one boolean per cell")

    area = CELL_AREA_M2
    densification = parameters.densification
    n = parameters.glen_exponent

    thickness_edge = np.zeros((intervals + 1, cells), np.float64)
    surface_edge = np.zeros((intervals + 1, cells), np.float64)
    volume_edge = np.zeros((intervals + 1, cells), np.float64)
    thickness_edge[0] = thickness
    surface_edge[0] = bed + thickness
    volume_edge[0] = thickness * area
    accumulation_ice = np.zeros((intervals, cells), np.float64)
    ablation_ice = np.zeros((intervals, cells), np.float64)
    melt_liquid_mm = np.zeros((intervals, cells), np.float64)
    melt_to_land_mm = np.zeros((intervals, cells), np.float64)
    unresolved_liquid_mm = np.zeros((intervals, cells), np.float64)
    face_flux_cube = np.zeros((intervals, cells + 1), np.float64)
    face_flux_mean = np.zeros((intervals, cells + 1), np.float64)
    erosion_rock = np.zeros((intervals, cells), np.float64)
    solid_export = np.zeros((intervals, cells), np.float64)
    motion = np.full((intervals, cells), MOTION_STATIC, dtype="<U32")
    substeps = np.zeros(intervals, np.int64)
    dt_limit_edge = np.zeros(intervals, np.float64)
    limited_cells = np.zeros((intervals, cells), np.bool_)
    rock_used = np.zeros(cells, np.float64)

    for index in range(intervals):
        span = float(edges[index + 1] - edges[index])
        # 1) accumulation and ablation as ice volume (water-equivalent input, ice-density output)
        acc_ice = accumulation[index] / 1000.0 * area * densification
        abl_ice = np.minimum(ablation[index] / 1000.0 * area * densification,
                             thickness * area)
        thickness = thickness + (acc_ice - abl_ice) / area
        if np.any(thickness < -1e-12):
            raise RuntimeError("ablation drove the ice thickness negative in interval %d" % index)
        thickness = np.maximum(thickness, 0.0)
        if np.any(thickness > parameters.max_thickness_m):
            raise ValueError("interval %d would exceed the declared thickness ceiling %r m"
                             % (index, parameters.max_thickness_m))
        accumulation_ice[index] = acc_ice
        ablation_ice[index] = abl_ice
        # the liquid product of that melt, back at water density
        produced_mm = abl_ice / (area * densification) * 1000.0
        melt_liquid_mm[index] = produced_mm
        melt_to_land_mm[index] = np.where(land_port, produced_mm, 0.0)
        unresolved_liquid_mm[index] = np.where(land_port, 0.0, produced_mm)

        # 2) the flow, if this caller asked for it
        if flow_model == "shallow_ice":
            surface = bed + thickness
            flux, diffusivity = _face_flux(surface_m=surface, thickness_m=thickness,
                                           dx_m=dx, width_m=width, parameters=parameters)
            limit = _dt_limit(diffusivity, dx, CFL)
            dt_limit_edge[index] = limit
            if math.isfinite(limit) and span > MAX_SUBSTEPS * limit:
                raise ValueError(
                    "interval %d spans %r s but the explicit shallow-ice stability limit is "
                    "%r s per sub-step, so at most %d sub-steps cover %r s. Refine the interval "
                    "edges with the caller's own fixed split; this module does not take an "
                    "unstable step and does not clip the store to fake stability."
                    % (index, span, limit, MAX_SUBSTEPS, MAX_SUBSTEPS * limit))
            count = 1 if not math.isfinite(limit) else int(math.ceil(span / limit))
            count = max(1, min(count, MAX_SUBSTEPS))
            sub_dt = span / count
            substeps[index] = count
            flux_sum = np.zeros_like(flux)
            for _ in range(count):
                # CFL uses the current state at every sub-step
                surface = bed + thickness
                flux, diffusivity = _face_flux(surface_m=surface, thickness_m=thickness,
                                               dx_m=dx, width_m=width, parameters=parameters)
                detail = float(np.max(diffusivity)) if diffusivity.size else 0.0
                if detail > 0.0 and sub_dt > CFL * dx * dx / detail:
                    raise RuntimeError("the sub-step violated the declared CFL bound")
                volume = thickness * area
                # face f sits between cell f-1 (left) and cell f (right), so the *left* cell of
                # face f is cell f-1 and the *right* cell is cell f.
                out_left = np.zeros(cells, np.float64)
                out_right = np.zeros(cells, np.float64)
                positive = np.maximum(flux, 0.0) * sub_dt              # left -> right
                negative = np.maximum(-flux, 0.0) * sub_dt             # right -> left
                out_left[:-1] = positive[1:-1]
                out_right[1:] = negative[1:-1]
                requested = out_left + out_right
                # min(flux, available): scale a cell's outgoing faces only when they would
                # remove more ice than that cell holds. Recorded, never silently zeroed — a cell
                # with ice whose outgoing faces are clipped is not the same as a dry cell.
                over = requested > volume
                if over.any():
                    scale = np.ones(cells, np.float64)
                    scale[over] = volume[over] / requested[over]
                    positive[1:-1] *= scale[:-1]
                    negative[1:-1] *= scale[1:]
                    limited_cells[index] = limited_cells[index] | over
                change = np.zeros(cells, np.float64)
                change[:-1] -= positive[1:-1]
                change[1:] += positive[1:-1]
                change[1:] -= negative[1:-1]
                change[:-1] += negative[1:-1]
                thickness = thickness + change / area
                if np.any(thickness < -1e-12):
                    raise RuntimeError("the flow step drove the thickness negative")
                thickness = np.maximum(thickness, 0.0)
                flux_sum += flux
            face_flux_mean[index] = flux_sum / count
            face_flux_cube[index] = np.abs(flux_sum / count) * span
            motion[index] = np.where(thickness >= parameters.min_flow_thickness_m,
                                     MOTION_FLOWING, MOTION_STATIONARY)
            if parameters.min_flow_thickness_m > 0.0:
                thin = thickness < parameters.min_flow_thickness_m
                if thin.any():
                    # an optional engineering cutoff, reported rather than silently applied
                    motion[index][thin] = MOTION_STATIONARY
        else:
            face_flux_mean[index] = 0.0
            substeps[index] = 0
            motion[index] = MOTION_STATIC

        # 3) the declared erosion proxy, bounded by the finite bedrock and the ice present
        if rock_stock is not None:
            if flow_model == "shallow_ice":
                proxy = parameters.erosion_proxy_coefficient * face_flux_cube[index].sum()
            else:
                proxy = np.zeros(cells, np.float64)
            remaining_rock = np.maximum(rock_stock - rock_used, 0.0)
            removed = np.minimum(proxy, np.maximum(remaining_rock, 0.0))
            erosion_rock[index] = removed
            rock_used += removed
            # the removed rock leaves as solid; the ledger is closed here, transport is not modelled
            solid_export[index] = removed

        thickness_edge[index + 1] = thickness
        surface_edge[index + 1] = bed + thickness
        volume_edge[index + 1] = thickness * area

    # ---- ledgers ---------------------------------------------------------------------------
    volume = thickness_edge * area
    flux_divergence = np.zeros((intervals, cells), np.float64)
    for index in range(intervals):
        flux = face_flux_mean[index] * (edges[index + 1] - edges[index])
        flux_divergence[index, :-1] -= flux[1:-1]
        flux_divergence[index, 1:] += flux[1:-1]
    ice_residual = (volume[-1] - volume[0] - accumulation_ice.sum(axis=0)
                    + ablation_ice.sum(axis=0) - flux_divergence.sum(axis=0))
    liquid_total = melt_liquid_mm.sum(axis=0)
    liquid_land = melt_to_land_mm.sum(axis=0)
    liquid_unresolved = unresolved_liquid_mm.sum(axis=0)
    liquid_residual = liquid_total - liquid_land - liquid_unresolved
    if np.abs(liquid_residual).max() > 1e-9:
        raise RuntimeError("the liquid ledger does not close")
    if np.abs(ice_residual).max() > 1e-6:
        raise RuntimeError("the ice ledger does not close (max |residual| = %r m3)"
                           % float(np.abs(ice_residual).max()))
    if rock_stock is not None:
        rock_residual = rock_used - solid_export.sum(axis=0)
        if np.abs(rock_residual).max() > 1e-9:
            raise RuntimeError("the rock ledger does not close")

    bed_delta = -rock_used / area          # derived surface lowering, never written back
    payload = {
        "schema": SCHEMA,
        "logical_version": LOGICAL_VERSION,
        "algorithm": ALGORITHM,
        "flow_model": flow_model,
        "parameters": parameters.identity(),
        "formula_source": FORMULA_SOURCE,
        "flow_law": {
            "model": "shallow_ice_deformation_only",
            "glen_exponent": n,
            "creep_parameter_unit": CREEP_PARAMETER_UNIT,
            "creep_parameter_semantics": CREEP_PARAMETER_SEMANTICS,
            "face_flux_form": ("W * (2A/(n+2)) * (rho g)^n * H_f^(n+2) * |ds/dx|^(n-1) * (-ds/dx)"),
            "surface_rule": "surface = bed + thickness, recomputed every sub-step",
            "basal_sliding": False,
            "ends": "closed: the two outer faces carry no ice flux",
            "cfl": float(CFL),
            "max_substeps_per_interval": int(MAX_SUBSTEPS),
        },
        "units": {
            "thickness": "m", "volume": "m3", "accumulation_input": "mm_water_equivalent",
            "ablation_input": "mm_water_equivalent", "melt_output": "mm_water_equivalent",
            "face_flux": "m3 s^-1", "erosion": "intact_rock_m3", "bed_delta": "m",
            "densification": "ice_volume_per_unit_water_depth",
        },
        "erosion": {
            "status": erosion_status,
            "proxy": EROSION_PROXY_SEMANTICS,
            "bounded_by_ice_store": False,
            "finite_bedrock_supplied": rock_stock is not None,
            "couples_back_to_bed": False,
        },
        "liquid": {
            "to_land_field": "melt_to_land_mm",
            "unresolved_field": "liquid_export_unresolved_mm",
            "policy": ("ice is only ablated when the water it produces is accounted for; a cell "
                       "without a declared land port exports to liquid_export_unresolved_mm"),
            "land_port_cells": int(land_port.sum()),
        },
        "time_edges_s": [float(v) for v in edges],
        "x_m": [float(v) for v in x],
        "dx_m": dx,
        "width_m": width,
        "cell_area_m2": area,
        "spacing_m": NATIVE_SPACING_M,
        "claims_denied": {"basal_sliding": True, "ice_temperature": True, "calving": True,
                          "glacier_existence": True, "bed_feedback_coupled": True,
                          "real_world_prediction": True, "one_metre_accuracy": True,
                          "three_dimensional": True},
    }
    arrays = {
        "thickness_edge_m": thickness_edge,
        "surface_edge_m": surface_edge,
        "ice_volume_edge_m3": volume_edge,
        "accumulation_ice_m3": accumulation_ice,
        "ablation_ice_m3": ablation_ice,
        "melt_liquid_mm": melt_liquid_mm,
        "melt_to_land_mm": melt_to_land_mm,
        "liquid_export_unresolved_mm": unresolved_liquid_mm,
        "face_flux_m3_s": face_flux_mean,
        "face_flux_cumulative_m3": face_flux_cube,
        "erosion_rock_m3": erosion_rock,
        "solid_export_rock_m3": solid_export,
        "bed_delta_m": np.repeat(bed_delta.reshape(1, cells), intervals, axis=0),
        "motion_state": motion,
        "flux_limited": limited_cells,
    }
    ledger = {
        "ice": {
            "volume_start_m3": [float(v) for v in volume[0]],
            "volume_end_m3": [float(v) for v in volume[-1]],
            "accumulation_m3": [float(v) for v in accumulation_ice.sum(axis=0)],
            "ablation_m3": [float(v) for v in ablation_ice.sum(axis=0)],
            "flux_divergence_m3": [float(v) for v in flux_divergence.sum(axis=0)],
            "residual_m3": [float(v) for v in ice_residual],
            "max_abs_residual_m3": float(np.abs(ice_residual).max()),
        },
        "liquid": {
            "produced_mm": [float(v) for v in liquid_total],
            "to_land_mm": [float(v) for v in liquid_land],
            "unresolved_mm": [float(v) for v in liquid_unresolved],
            "residual_mm": [float(v) for v in liquid_residual],
        },
        "rock": {
            "status": erosion_status,
            "supplied_m3": ([float(v) for v in rock_stock] if rock_stock is not None else None),
            "removed_m3": [float(v) for v in rock_used],
            "exported_solid_m3": [float(v) for v in solid_export.sum(axis=0)],
            "remaining_m3": ([float(v) for v in (rock_stock - rock_used)]
                             if rock_stock is not None else None),
        },
        "substeps_per_interval": [int(v) for v in substeps],
        "dt_limit_s_per_interval": [float(v) for v in dt_limit_edge],
        "limited_cells": int(limited_cells.sum()),
        "note": ("ice volume closes against accumulation, ablation and face flux divergence; the "
                 "melt water is fully split between the declared land port and the unresolved "
                 "export, so none is lost; the rock account is separate and closes against its "
                 "own finite supply"),
    }
    return {
        "arrays": arrays,
        "ledger": ledger,
        "metadata": payload,
        "identity_sha256": digest({
            "metadata": payload,
            "arrays": {name: array_hash(np.ascontiguousarray(value))
                       for name, value in sorted(arrays.items())}}),
    }


def describe():
    return {
        "schema": SCHEMA,
        "logical_version": LOGICAL_VERSION,
        "algorithm": ALGORITHM,
        "flow_models": list(FLOW_MODELS),
        "motion_states": [MOTION_FLOWING, MOTION_STATIONARY, MOTION_STATIC],
        "formula_source": FORMULA_SOURCE,
        "limitations": list(LIMITATIONS),
        "default_parameters": GlacierParameters().identity(),
        "cells_bounds": [MIN_CELLS, MAX_CELLS],
        "intervals_bound": MAX_INTERVALS,
        "max_substeps_per_interval": MAX_SUBSTEPS,
        "cfl": CFL,
        "cell_area_m2": CELL_AREA_M2,
        "spacing_m": NATIVE_SPACING_M,
        "not_modelled": ["basal_sliding", "ice_temperature", "calving", "glacier_lake_outburst",
                         "three_dimensional_flow", "bed_feedback_coupled",
                         "real_world_prediction", "one_metre_accuracy",
                         "glacier_existence"],
        "glacier_existence_policy": GLACIER_EXISTENCE_POLICY,
        "creep_parameter_unit": CREEP_PARAMETER_UNIT,
        "erosion_proxy_semantics": EROSION_PROXY_SEMANTICS,
    }
