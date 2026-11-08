"""Facet noise and hydraulic dissection on top of the L0 special-terrain chart.

``metric_special_terrain_forms`` builds every L0 target as one smooth elliptical
flat-top bump, so the raw chart reads as a polished cone.  This module adds the two
things that chart is missing, and it adds them by *calling* existing repository
kernels rather than by growing new physics:

* facet roughness  -- ``diffusion.geographic_noise.field``, the repository's metre
  coordinate, seed/salt, multi-octave smooth noise.
* hydraulic dissection -- ``metric_drainage.route_diagnostic`` +
  ``accumulate_local_discharge`` for flow routing and discharge, a declared
  stream-power detachment term, and then
  ``metric_fluvial_morphodynamics.conservative_diffusion_step`` to carry the eroded
  volume downslope as donor-limited paired transfers, plus
  ``metric_fluvial_slope_stability.relax_mobile_slopes`` for the gravity/repose
  relaxation.  ``phase_record`` supplies the phase ledger.

Every reused kernel is imported, never edited: those files are sha256-pinned by
published verification evidence.  ``KERNEL_FILES`` records the exact revisions this
module was built against.

## The mobile column is at repose, not the landform

The gravity phase is deliberately *not* "relax the whole landform to the angle of
repose".  A 264 m standing rock tower is rock: it cannot be at repose and must not be
flattened into one.  The native morphodynamics code already carries the right
semantics -- ``metric_fluvial_morphodynamics.py:584`` keeps ``mobile_base`` as the
running minimum of the bed -- so the mobile column here is only the material that has
actually been detached and is still in transit.  Untouched rock has an empty mobile
column, and the relaxation provably leaves it alone (``available = bed - mobile_base
== 0``).

That distinction was measured, not assumed.  Throwaway probes gave every cell of the
tower a loose skin and relaxed it: 1.8e7 m3 of internal relocation against 5.2e3 m3
of detachment, eating the volcanic plug column down by 36.5 m and *raising* karst
cells by 104 m.  The in-transit column relocated 3.9e5 m3 on the same chart and held
the maximum column loss to the incision depth, 8.6 m.  So the detachment term is
bounded by a declared rock *floor*, not by the mobile column -- otherwise no material
could ever be loosened in the first place.

## Structural guarantees

* the perimeter stays at zero displacement and zero change, because both new fields
  are tapered to zero wherever the parent displacement is zero and every operator runs
  inside a sacrificial outer ring;
* ``floor <= bed`` and ``mobile_base <= bed`` everywhere, because both are clamped to
  the bed after every phase;
* no cell is ever cut below its rock floor, so nothing is silently clipped.

The rock floor is a declared depth below the *roughened* surface -- the surface the
river actually flows on -- so ``roughened_relief_reference_m`` is the relief both that
floor and the mobile column are measured against.  ``relief_reference_m`` records the
parent chart's own peak relief instead, because that is what the facet amplitude and the
collar taper are referenced to.  The two differ once the facets add relief, and keeping
them as separate fields is what makes the floor recomputable from the stored arrays.

Accounting keeps quarry and fill as separate ledgers that never cancel each other:
``detachment_ledger_m3`` records what the stream-power term cut,
``transport_deposition_ledger_m3`` records what the transport operator put back, and
``relaxation_transferred_ledger_m3`` records the paired internal transfers that moved
material without changing the total.  Nothing here writes back into the parent chart.
Nothing here is a certification: every status flag stays False.

## Convergence is recorded, not asserted

The repose relaxation is a finite-budget iteration: ``relax_mobile_slopes`` stops at
``max_sweeps`` and states plainly that it returns "the actual relaxed state, including an
unconverged finite-stop state".  Its own test is ``maximum_mobile_excess_after_m <=
tolerance_m``.  This module therefore stores *every operand of that test* -- per step and
in the summary (``relaxation_maximum_excess_m``, ``relaxation_tolerance_m``,
``relaxation_sweep_budget``, ``relaxation_sweeps_max``) -- and ``validate_special_form_surface``
re-derives ``relaxation_converged`` from them instead of trusting the boolean.  A bundle
may honestly record an unconverged step; it may not claim a convergence its own numbers
contradict, and a step that stops short of repose while still stalled at float64
resolution is refused outright.  The declared budgets in ``surface_preset`` were sized by
measurement (see ``DISSECTION_SOURCE``), not assumed.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from diffusion.geographic_noise import field
from terrain_pipeline.metric_special_terrain_forms import (
    SAMPLES_PER_FEATURE, SCHEMA as PARENT_SCHEMA, load_special_form_vdm,
    validate_special_form_vdm,
)
from terrain_pipeline.metric_vdm import _check_mesh, _triangles
from terrain_pipeline.common_infra import (
    SOURCE_MAX_CELLS,
    GRID_MAX_CELLS as MAX_CELLS,
    MAX_METADATA,
    identity,
    readonly,
    load_bundle,
    save_bundle,
)
from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import (
    conservative_diffusion_step, phase_record,
)
from terrain_pipeline.surface_rivers.metric_fluvial_slope_stability import relax_mobile_slopes


SCHEMA = "metric-special-terrain-surface-v2"
ALGORITHM = "special-terrain-facet-noise-hydraulic-dissection-v2"
SUPERSEDES_ALGORITHM = "special-terrain-facet-noise-hydraulic-dissection-v1"
COORDINATES = "xyz metres; chart [row,col]"
ARRAY_KEYS = {"reference_xyz_m", "displacement_xyz_m", "vertices_xyz_m", "triangles",
              "protected_mask", "surface_xyz_m", "erosion_change_m"}
PARENT_ARRAY_KEYS = {"reference_xyz_m", "displacement_xyz_m", "vertices_xyz_m", "triangles",
                     "protected_mask"}

# v1 declared ``immobile_rock_fraction`` -- a loose skin on every cell of the tower.
# The probes disproved that reading, so the field is retired; it is named here so a
# stale artifact is recognised instead of silently re-read under the new schema.
RETIRED_RECIPE_FIELDS = ("immobile_rock_fraction",)

# The revisions this module was written against.  Any change to one of these digests
# means a reused kernel moved and the products must be re-derived, not merely re-run:
# the numeric output is only meaningful for the pinned revision.
KERNEL_FILES = (
    "diffusion/geographic_noise.py",
    "terrain_pipeline/surface_rivers/metric_drainage.py",
    "terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py",
    "terrain_pipeline/surface_rivers/metric_fluvial_slope_stability.py",
    "terrain_pipeline/surface_rivers/metric_contracts.py",
)
ROOT = Path(__file__).resolve().parents[1]
GRADES = frozenset({"verified", "secondary", "assumed"})

# Kept out of GRADES on purpose: these are not landform measurements, they are declared
# model settings with no source anywhere in the repository.
FACET_SOURCE = ("assumed", "parameters-and-sources.md#5.1 facet roughness scale and amplitude")
DISSECTION_SOURCE = ("assumed", "parameters-and-sources.md#5.2 stream-power depth, cut cap, "
                                 "rock floor, mobile column and repose angle")

# The repose budget is measured, not declared.  Probes over the four production charts found
# that a 1e-6 tolerance needs 59 to more than 512 sweeps (volcanic_plug is still 9.5e-4 m
# out of repose after 512), while 1e-3 m -- 1 mm, on charts of 150 to 348 m of relief --
# converges every karst and sandstone step and all but the last two inselberg steps.  The
# budget is the kernel's own ceiling: ``relax_mobile_slopes`` defaults to it and the native
# ``GRAVITY_PARAMETERS`` value is checked as a frozen mechanism by
# ``tools/verify_fluvial_morphodynamics.py``, so it must not be changed here either.
# Both numbers are recorded in the ledger, and ``relaxation_converged`` is re-derived from
# them rather than trusted, because the kernel's contract explicitly includes the
# unconverged finite-stop state.
REPOSE_TOLERANCE_M = 1e-3
REPOSE_SWEEP_BUDGET = 512


def _canonical(value):
    """The JSON-native form an in-memory record takes after a bundle round-trip.

    ``asdict`` hands back tuples where JSON hands back lists, and every bundle is
    written and read through JSON, so comparing a live recipe against a loaded one
    needs one canonical shape on both sides.  Storing the canonical form also keeps an
    in-memory bundle equal, field for field, to the same bundle after ``load_bundle``.
    """
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _finite_number(value, name, *, positive=False, nonnegative=False):
    if (type(value) not in (int, float) or not math.isfinite(value) or
            (positive and value <= 0.0) or (nonnegative and value < 0.0)):
        raise ValueError(f"invalid {name}")


def kernel_revisions(root=None):
    """sha256 of every reused kernel, so a moved pin is visible in the artifact."""
    base = ROOT if root is None else Path(root)
    return {name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in KERNEL_FILES}


@dataclass(frozen=True)
class FacetRoughnessRecipe:
    """Multi-octave noise applied to the parent relief, tapered to the collar.

    ``scales`` declares each octave as a **wavelength in chart cells** plus a weight;
    ``wavelengths_m`` converts them with the parent chart's own spacing at build time.
    Declaring cells rather than metres makes the parent's sampling gate structural
    instead of hopeful: the four L0 charts run from 0.5 m to 8 m cells, so one absolute
    metre figure can be well resolved on one chart and aliased on another.

    ``amplitude_fraction`` is the peak facet relief as a fraction of the parent chart's
    maximum relief, so the result scales with the landform instead of with an absolute
    metre figure.
    """

    seed: int
    scales: tuple
    amplitude_fraction: float

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed < 2 ** 64:
            raise ValueError("facet seed must be uint64")
        if not isinstance(self.scales, (tuple, list)) or not 1 <= len(self.scales) <= 8:
            raise ValueError("one to eight facet octaves required")
        # A bundle round-trips through JSON, which turns the tuple of pairs into lists;
        # normalising here keeps saved and rebuilt recipes comparable field by field.
        normalised = []
        for pair in self.scales:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError("facet octave is (wavelength_cells, weight)")
            cells, weight = pair
            _finite_number(cells, "facet octave wavelength", positive=True)
            _finite_number(weight, "facet octave weight", positive=True)
            normalised.append((float(cells), float(weight)))
        object.__setattr__(self, "scales", tuple(normalised))
        if self.finest_cells < SAMPLES_PER_FEATURE:
            raise ValueError(
                f"finest facet octave {self.finest_cells:g} cells is below the "
                f"{SAMPLES_PER_FEATURE}-cell sampling limit")
        _finite_number(self.amplitude_fraction, "facet amplitude fraction", positive=True)
        if self.amplitude_fraction > 0.5:
            raise ValueError("facet amplitude must stay below half the parent relief")

    @property
    def finest_cells(self):
        return min(cells for cells, _ in self.scales)

    def wavelengths_m(self, spacing_m):
        """The octave list in absolute metres, as the noise kernel wants it."""
        _finite_number(spacing_m, "chart spacing", positive=True)
        return tuple((cells * spacing_m, weight) for cells, weight in self.scales)


@dataclass(frozen=True)
class DissectionRecipe:
    """Declared hydraulic dissection settings.

    ``detachment_per_step_m`` is the cut depth at reference accumulated discharge and
    unit slope, capped by ``maximum_cut_fraction`` of the relief.  No total cut may pass
    ``maximum_incision_fraction`` of the *roughened* relief below the roughened surface,
    and no cut may ever pass the parent base bed -- together those two are the declared
    rock floor.  The roughened relief is the one recorded as
    ``roughened_relief_reference_m``, so the floor is recomputable from the bundle.

    The mobile column is the native one: it starts empty on the roughened surface and
    deepens only where the bed was actually cut.  ``mobile_reference_m`` -- the larger of
    ``mobile_minimum_m`` and ``mobile_fraction`` x relief -- is the thickness the deposit
    coefficient is calibrated against, so deposition stays comparable with the material
    in transit rather than with the whole landform.  Only that in-transit column is
    relaxed to ``repose_angle_deg``; standing rock is never touched.
    """

    repose_angle_deg: float
    steps: int
    detachment_per_step_m: float
    maximum_cut_fraction: float
    maximum_incision_fraction: float
    mobile_fraction: float
    mobile_minimum_m: float
    deposition_fraction: float
    tolerance_m: float
    max_sweeps: int

    def __post_init__(self):
        _finite_number(self.repose_angle_deg, "repose angle", positive=True)
        if not 0.0 < self.repose_angle_deg < 90.0:
            raise ValueError("repose angle must lie strictly inside (0, 90)")
        if type(self.steps) is not int or not 1 <= self.steps <= 256:
            raise ValueError("dissection steps outside the finite budget")
        _finite_number(self.detachment_per_step_m, "detachment per step", positive=True)
        _finite_number(self.maximum_cut_fraction, "maximum cut fraction", positive=True)
        if not 0.0 < self.maximum_cut_fraction <= 0.5:
            raise ValueError("maximum cut fraction must lie in (0, 0.5]")
        _finite_number(self.maximum_incision_fraction, "maximum incision fraction", positive=True)
        if not 0.0 < self.maximum_incision_fraction <= 0.5:
            raise ValueError("maximum incision fraction must lie in (0, 0.5]")
        _finite_number(self.mobile_fraction, "mobile fraction", positive=True)
        if not 0.0 < self.mobile_fraction < 1.0:
            raise ValueError("mobile fraction must lie in (0, 1)")
        _finite_number(self.mobile_minimum_m, "mobile minimum", positive=True)
        _finite_number(self.deposition_fraction, "deposition fraction", positive=True)
        if not 0.0 < self.deposition_fraction <= 1.0:
            raise ValueError("deposition fraction must lie in (0, 1]")
        _finite_number(self.tolerance_m, "repose tolerance", positive=True)
        if type(self.max_sweeps) is not int or not 1 <= self.max_sweeps <= 512:
            raise ValueError("repose sweeps outside the finite budget")

    def mobile_reference_m(self, relief_m):
        return max(self.mobile_minimum_m, self.mobile_fraction * relief_m)


def surface_preset(kind):
    """Deterministic facet + dissection settings per L0 form kind.

    Facet octave spacing is tied to the parent chart cell size so the noise is resolved
    on every chart the parent accepts, and the declared detachment depth is per kind
    because the four landforms span 0.5 m to 8 m cells and 150 m to 348 m of relief.
    Amplitude and the remaining dissection settings are declared choices
    (see ``FACET_SOURCE`` / ``DISSECTION_SOURCE``).
    """
    facets = {
        "volcanic_plug": (0.10, ((32.0, 1.0), (12.0, 0.5), (5.0, 0.25)), 8.0),
        "inselberg": (0.07, ((32.0, 1.0), (12.0, 0.5), (5.0, 0.25)), 8.0),
        "sandstone_pillar_field": (0.13, ((8.0, 1.0), (5.0, 0.5), (4.0, 0.25)), 2.0),
        "karst_tower_field": (0.09, ((24.0, 1.0), (9.0, 0.5), (5.0, 0.25)), 6.0),
    }
    if not isinstance(kind, str) or kind not in facets:
        raise ValueError("invalid special terrain form kind")
    amplitude, scales, detachment = facets[kind]
    roughness = FacetRoughnessRecipe(20261003 if kind != "karst_tower_field" else 20261004,
                                     scales, amplitude)
    dissection = DissectionRecipe(repose_angle_deg=34.0, steps=12,
                                  detachment_per_step_m=detachment,
                                  maximum_cut_fraction=0.05,
                                  maximum_incision_fraction=0.15,
                                  mobile_fraction=0.03, mobile_minimum_m=4.0,
                                  deposition_fraction=0.35,
                                  tolerance_m=REPOSE_TOLERANCE_M, max_sweeps=REPOSE_SWEEP_BUDGET)
    return roughness, dissection


def _check_uniform_chart(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = np.concatenate((np.linalg.norm(np.diff(horizontal, axis=0), axis=2).ravel(),
                               np.linalg.norm(np.diff(horizontal, axis=1), axis=2).ravel()))
    if not np.isfinite(adjacent).all() or np.any(adjacent <= 0.0):
        raise ValueError("invalid adjacent horizontal chart spacing")
    minimum, maximum = float(np.min(adjacent)), float(np.max(adjacent))
    if maximum - minimum > 1e-6 * maximum:
        raise ValueError("special terrain surface chart must be a uniform grid")
    return minimum, maximum


def _facet_relief(reference, displacement, roughness, spacing):
    """Peak-normalised octave noise, tapered by the normalised parent relief."""
    top = displacement[:, :, 1]
    peak = float(np.max(top))
    if not math.isfinite(peak) or peak <= 0.0:
        raise ValueError("parent chart carries no relief to roughen")
    scales = roughness.wavelengths_m(spacing)
    noise = field(reference[:, :, 0], reference[:, :, 2], roughness.seed, 1901, scales)
    if noise.shape != top.shape or not np.isfinite(noise).all():
        raise ValueError("facet noise field does not match the chart")
    noise = noise - float(np.mean(noise, dtype=np.float64))
    scale = float(np.max(np.abs(noise)))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("degenerate facet noise field")
    taper = np.clip(top / peak, 0.0, 1.0)
    return (noise / scale) * taper * (roughness.amplitude_fraction * peak)


def _per_target_depth(change, reference, recipe):
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    record = {}
    for target in recipe.targets:
        across = (x - target.center_x_m) / target.radius_x_m
        along = (z - target.center_z_m) / target.radius_z_m
        inside = np.sqrt(across * across + along * along) <= 1.0
        record[target.target_id] = {
            "footprint_cells": int(inside.sum()),
            "maximum_incision_m": float(np.max(-change[inside])) if inside.any() else 0.0,
            "maximum_deposition_m": float(np.max(change[inside])) if inside.any() else 0.0,
        }
    return record


def _parent_geometry(parent):
    """Pull and re-validate the five parent arrays plus its recipe."""
    validate_special_form_vdm(parent)
    arrays = {key: np.array(parent["arrays"][key], dtype=parent["arrays"][key].dtype, copy=True)
              for key in PARENT_ARRAY_KEYS}
    metadata = parent["metadata"]
    if metadata["schema"] != PARENT_SCHEMA:
        raise ValueError("special terrain surface requires a matching parent schema")
    reference = arrays["reference_xyz_m"]
    if (reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or
            reference.shape[0] * reference.shape[1] > MAX_CELLS or
            reference.dtype != np.float64 or not np.isfinite(reference).all()):
        raise ValueError("invalid parent reference chart")
    return arrays, metadata


def _dissect(bed, reference, displacement, dissection, *, protected_mask):
    """Two-phase dissection returning the final bed plus the three ledgers.

    Phase A (detachment) uses the routed graph and a declared stream-power law, bounded
    by the rock floor.  Phase B (transport) hands the eroded volume to the repository's
    donor-limited eight-neighbour operator, then relaxes only the resulting in-transit
    mobile column to the declared repose angle.  ``mobile_base`` follows the native
    update: the running minimum of the bed after every non-gravity phase.
    """
    shape = bed.shape
    spacing = float(reference[0, 1, 0] - reference[0, 0, 0])
    top = displacement[:, :, 1]
    relief = float(np.max(top))
    active = top > 0.0
    if not math.isfinite(relief) or relief <= 0.0:
        raise ValueError("parent chart carries no relief to dissect")

    surface = bed.copy()
    base_bed = reference[:, :, 1]
    floor = np.maximum(bed - dissection.maximum_incision_fraction * relief, base_bed)
    floor = np.minimum(floor, bed)
    if np.any(floor > bed):
        raise ValueError("rock floor above the bed")
    mobile_base = bed.copy()          # nothing is in transit anywhere yet

    # One sacrificial outer ring absorbs the transport operator's boundary bias; the
    # operator always excludes row zero, so both are kept immobile for symmetry.
    ring = np.zeros(shape, bool)
    ring[[0, -1], :] = True
    ring[:, [0, -1]] = True
    outer = ring.copy()
    for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
        outer |= np.roll(ring, shift, axis=axis)
    edge_kind = np.full(shape, "interior", dtype="U24")
    edge_kind[ring] = "open_outflow"
    cell_type = np.where(active & ~outer, 0, -2)
    cell_type[0, :] = -2
    cell_type = cell_type.astype(np.int64)

    eligible = active.copy()
    eligible &= ~ring
    eligible[0, :] = False
    if protected_mask is not None:
        eligible &= ~protected_mask
    local_rain = np.where(active, 1.0, 0.0)

    boundary = BoundaryGrid(edge_kind, np.zeros(shape, bool), "special-terrain-chart-edge", "0" * 64)
    steps = []
    coefficient = None
    detachment_total = 0.0
    deposition_total = 0.0
    relaxation_total = 0.0
    relaxed_all = True
    for index in range(dissection.steps):
        terrain = TerrainGrid(elevation_m=np.ascontiguousarray(bed), valid_mask=np.ones(shape, bool),
                              x0_m=float(reference[0, 0, 0]), z0_m=float(reference[0, 0, 2]),
                              dx_m=spacing, dz_m=spacing, source_kind="generated_terrain",
                              source_id="special-terrain-surface-chart", source_sha256="0" * 64)
        graph = route_diagnostic(terrain, boundary)
        budget = accumulate_local_discharge(graph, local_rain)
        flux = np.asarray(budget["routed_q_m3_s"], dtype=np.float64)
        if not np.isfinite(flux).all() or np.any(flux < 0.0) or float(flux.max()) <= 0.0:
            raise ValueError("routed discharge is degenerate on the special terrain chart")
        slope = np.zeros(shape)
        donors = graph.receiver >= 0
        slope.ravel()[donors] = graph.edge_slope[donors]
        reference_flux = float(flux.max())
        demand = (dissection.detachment_per_step_m * (flux / reference_flux)
                  * np.clip(slope, 0.0, 1.0))
        demand = np.minimum(demand, dissection.maximum_cut_fraction * relief)
        cut = np.where(eligible, np.clip(np.minimum(demand, bed - floor), 0.0, None), 0.0)
        if not np.isfinite(cut).all():
            raise ValueError("nonfinite detachment depth")
        change = bed - cut
        if np.any(change < floor - 1e-12):
            raise ValueError("detachment crossed the rock floor")
        bed = change
        mobile_base = np.minimum(mobile_base, bed)      # native update
        detachment_volume = float(np.sum(cut) * spacing ** 2)

        supply = cut / spacing ** 2
        if coefficient is None:
            unit = conservative_diffusion_step(bed, supply, cell_type, floor, 1.0, spacing)
            span = float(np.max(np.abs(unit - bed)))
            if not math.isfinite(span):
                raise ValueError("nonfinite unit-coefficient transport response")
            reference_mobile = dissection.mobile_reference_m(relief)
            coefficient = (dissection.deposition_fraction * reference_mobile / span
                           if span > 0.0 else 0.0)
        before = bed.copy()
        bed = conservative_diffusion_step(bed, supply, cell_type, floor, coefficient, spacing)
        if not np.isfinite(bed).all() or np.any(bed < floor - 1e-12):
            raise ValueError("nonfinite or under-floor transported bed")
        mobile_base = np.minimum(mobile_base, bed)
        moved = bed - before
        deposition_volume = float(np.sum(moved[moved > 0.0]) * spacing ** 2)

        relaxed = relax_mobile_slopes(bed, mobile_base, np.full(shape, 0.5), np.full(shape, 0.5),
                                      eligible, dx_m=spacing,
                                      repose_angle_deg=dissection.repose_angle_deg,
                                      tolerance_m=dissection.tolerance_m,
                                      max_sweeps=dissection.max_sweeps)
        before_relax = bed.copy()
        bed = relaxed.bed_m
        mobile_base = np.minimum(mobile_base, bed)
        ledger = relaxed.ledger
        if not np.isfinite(bed).all() or np.any(bed < mobile_base - 1e-12):
            raise ValueError("nonfinite or under-mobile-base relaxed bed")
        relaxed_move = bed - before_relax
        detachment_total += detachment_volume
        deposition_total += deposition_volume
        relaxation_total += float(ledger["transferred_bulk_m3"])
        relaxed_all &= bool(relaxed.converged)
        steps.append({
            "step_index": index,
            "routed_discharge_max_m3_s": reference_flux,
            "edge_slope_max_m_per_m": float(np.max(slope)),
            "detachment_volume_m3": detachment_volume,
            "detachment_depth_max_m": float(np.max(cut)),
            "transport_deposition_volume_m3": deposition_volume,
            "transport_change_max_m": float(np.max(np.abs(moved))),
            "relaxation_transferred_volume_m3": float(ledger["transferred_bulk_m3"]),
            "relaxation_change_max_m": float(np.max(np.abs(relaxed_move))),
            "relaxation_raw_residual_bulk_m3": float(ledger["raw_residual_bulk_m3"]),
            "relaxation_sweeps": int(ledger["sweeps"]),
            "relaxation_converged": bool(relaxed.converged),
            # The convergence flag is not a trusted boolean: it is `excess <= tolerance` in
            # the kernel, and both sides of that comparison are recorded here so a reader
            # that never imports the builder can re-derive the flag instead of believing it.
            "relaxation_maximum_excess_m": float(ledger["maximum_mobile_excess_after_m"]),
            "relaxation_immobile_excess_m": float(ledger["maximum_immobile_excess_after_m"]),
            "relaxation_stalled_at_float64_resolution": bool(
                ledger["stalled_at_float64_resolution"]),
            "mobile_column_volume_m3": float(np.sum(bed - mobile_base) * spacing ** 2),
        })
    change = bed - surface
    phase = phase_record(surface, bed, phase="hydraulic-dissection",
                         step_index=dissection.steps - 1, dx_m=spacing,
                         exported_bulk_m3=-float(np.sum(change) * spacing ** 2))
    # The phase record carries whole beds, which cannot go into a JSON identity; the
    # ledger keeps its scalar balance.  Its per-cell delta is exactly
    # ``erosion_change_m * spacing ** 2``, which the validator re-derives from the
    # stored arrays instead of trusting a second copy of the same numbers.
    ledger = {
        "transport_coefficient": coefficient,
        "mobile_reference_m": dissection.mobile_reference_m(relief),
        "rock_floor_depth_m": dissection.maximum_incision_fraction * relief,
        "detachment_ledger_m3": detachment_total,
        "transport_deposition_ledger_m3": deposition_total,
        "relaxation_transferred_ledger_m3": relaxation_total,
        "relaxation_converged": relaxed_all,
        # The three scalars below make the flag auditable: a cold reader recomputes
        # `all(step excess <= tolerance)` from the per-step records and refuses a bundle
        # whose flag disagrees with its own numbers.
        "relaxation_tolerance_m": dissection.tolerance_m,
        "relaxation_sweep_budget": dissection.max_sweeps,
        "relaxation_maximum_excess_m": max(
            (step["relaxation_maximum_excess_m"] for step in steps), default=0.0),
        "relaxation_sweeps_max": max((step["relaxation_sweeps"] for step in steps), default=0),
        "maximum_incision_m": float(np.max(-change)),
        "maximum_deposition_m": float(np.max(change)),
        "incised_cells": int(np.sum(change < 0.0)),
        "deposited_cells": int(np.sum(change > 0.0)),
        "net_change_ledger_m3": float(np.sum(change) * spacing ** 2),
        "phase_balance": {key: phase[key] for key in
                          ("step_index", "phase", "injected_bulk_m3", "exported_bulk_m3",
                           "lost_bulk_m3", "inlet_correction_bulk_m3", "raw_residual_bulk_m3")},
        "steps": steps,
    }
    return bed, ledger


def build_special_form_surface(parent, *, roughness: FacetRoughnessRecipe,
                               dissection: DissectionRecipe, base_kind=None):
    """Return a new bundle: the parent chart plus facet noise and dissection."""
    if not isinstance(roughness, FacetRoughnessRecipe):
        raise ValueError("FacetRoughnessRecipe required")
    if not isinstance(dissection, DissectionRecipe):
        raise ValueError("DissectionRecipe required")
    arrays, metadata = _parent_geometry(parent)
    reference = arrays["reference_xyz_m"]
    displacement = arrays["displacement_xyz_m"]
    mask = arrays["protected_mask"]
    maximum = _check_uniform_chart(reference)[1]
    if maximum <= 0.0:
        raise ValueError("invalid special terrain surface chart spacing")
    if base_kind is None:
        base_kind = metadata["base"]

    facets = _facet_relief(reference, displacement, roughness, maximum)
    facets[mask] = 0.0
    roughened = displacement.copy()
    roughened[:, :, 1] = displacement[:, :, 1] + facets
    # The parent already closes on its collar; roughening must not reopen it.
    if (np.any(roughened[0, :, 1] != 0.0) or np.any(roughened[-1, :, 1] != 0.0) or
            np.any(roughened[:, 0, 1] != 0.0) or np.any(roughened[:, -1, 1] != 0.0)):
        raise ValueError("facet roughness left the collar")
    roughened[0, :, :] = 0.0
    roughened[-1, :, :] = 0.0
    roughened[:, 0, :] = 0.0
    roughened[:, -1, :] = 0.0
    surface = reference + roughened
    if not np.isfinite(surface).all():
        raise ValueError("nonfinite special terrain surface")

    final_bed, ledger = _dissect(surface[:, :, 1], reference, roughened, dissection,
                                 protected_mask=mask)
    final_bed = np.array(final_bed, dtype=np.float64, copy=True)
    if not np.isfinite(final_bed).all():
        raise ValueError("nonfinite dissected bed")
    change = final_bed - surface[:, :, 1]
    if (np.any(change[0] != 0.0) or np.any(change[-1] != 0.0) or
            np.any(change[:, 0] != 0.0) or np.any(change[:, -1] != 0.0)):
        raise ValueError("dissection left the collar")
    if np.any(change[mask] != 0.0):
        raise ValueError("dissection touched a protected cell")
    if np.any(final_bed < 0.0) and metadata["base"] == "synthetic_analytic":
        raise ValueError("dissection cut the synthetic base plane")

    final_surface = surface.copy()
    # Rebuild the bed from the stored change so the bundle satisfies
    # ``surface == reference + displacement + vertical(change)`` bit for bit.  The ledger
    # already recorded the cut against the rock floor with its own tolerance, so the
    # identity arithmetic must not introduce a second, different rounding.
    final_bed = surface[:, :, 1] + change
    final_surface[:, :, 1] = final_bed
    vertices = final_surface.reshape(-1, 3)
    triangles = _triangles(*mask.shape)
    _check_mesh(vertices, triangles)
    if not (np.array_equal(final_surface[0], reference[0])
            and np.array_equal(final_surface[-1], reference[-1])
            and np.array_equal(final_surface[:, 0], reference[:, 0])
            and np.array_equal(final_surface[:, -1], reference[:, -1])):
        raise ValueError("special terrain surface left the collar")

    from terrain_pipeline.metric_special_terrain_forms import _parse_recipe_record
    recipe = _parse_recipe_record(metadata["recipe"])
    out_arrays = {"reference_xyz_m": readonly(reference),
                  "displacement_xyz_m": readonly(roughened),
                  "vertices_xyz_m": readonly(vertices),
                  "triangles": readonly(triangles),
                  "protected_mask": readonly(mask),
                  "surface_xyz_m": readonly(final_surface),
                  "erosion_change_m": readonly(change)}
    out_metadata = {
        "schema": SCHEMA, "algorithm": ALGORITHM, "coordinates": COORDINATES, "base": base_kind,
        "supersedes_algorithm": SUPERSEDES_ALGORITHM,
        "recipe": metadata["recipe"], "parameter_sources": metadata["parameter_sources"],
        "source_identity": metadata["source_identity"],
        "protection_identity": metadata["protection_identity"],
        "parent_schema": metadata["schema"], "parent_algorithm": metadata["algorithm"],
        "parent_identity_sha256": parent["identity_sha256"],
        "parent_kind": recipe.kind,
        "facet_recipe": _canonical(asdict(roughness)),
        "facet_source": {"grade": FACET_SOURCE[0], "reference": FACET_SOURCE[1]},
        "facet_wavelengths_m": [list(pair) for pair in roughness.wavelengths_m(maximum)],
        "dissection_recipe": _canonical(asdict(dissection)),
        "dissection_source": {"grade": DISSECTION_SOURCE[0], "reference": DISSECTION_SOURCE[1]},
        "kernel_revisions": kernel_revisions(),
        "relief_reference_m": float(np.max(displacement[:, :, 1])),
        "roughened_relief_reference_m": float(np.max(roughened[:, :, 1])),
        "targets": _per_target_depth(change, reference, recipe),
        "ledger": ledger,
        "hydraulic_ready": False, "natural_outlet_verified": False,
        "publishable": False, "self_intersection_verified": False,
    }
    result = {"arrays": out_arrays, "metadata": out_metadata,
              "identity_sha256": identity(out_arrays, out_metadata)}
    validate_special_form_surface(result)
    return result


def validate_special_form_surface(result):
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid special terrain surface bundle")
    arrays, metadata = result["arrays"], result["metadata"]
    if not isinstance(arrays, dict) or set(arrays) != ARRAY_KEYS or not isinstance(metadata, dict):
        raise ValueError("invalid special terrain surface fields")
    required = {"schema", "algorithm", "coordinates", "base", "supersedes_algorithm", "recipe",
                "parameter_sources", "source_identity", "protection_identity", "parent_schema",
                "parent_algorithm", "parent_identity_sha256", "parent_kind", "facet_recipe",
                "facet_source", "facet_wavelengths_m", "dissection_recipe", "dissection_source",
                "kernel_revisions", "relief_reference_m", "roughened_relief_reference_m", "targets",
                "ledger", "hydraulic_ready", "natural_outlet_verified", "publishable",
                "self_intersection_verified"}
    if set(metadata) != required or metadata["schema"] != SCHEMA or \
            metadata["algorithm"] != ALGORITHM or \
            metadata["supersedes_algorithm"] != SUPERSEDES_ALGORITHM or \
            metadata["coordinates"] != COORDINATES or \
            metadata["parent_schema"] != PARENT_SCHEMA or \
            any(metadata[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified",
                                                       "publishable", "self_intersection_verified")):
        raise ValueError("invalid special terrain surface metadata")
    if metadata["facet_source"] != {"grade": FACET_SOURCE[0], "reference": FACET_SOURCE[1]} or \
            metadata["dissection_source"] != {"grade": DISSECTION_SOURCE[0],
                                              "reference": DISSECTION_SOURCE[1]}:
        raise ValueError("special terrain surface provenance mismatch")
    wavelengths = metadata["facet_wavelengths_m"]
    if (not isinstance(wavelengths, list) or
            any(not isinstance(pair, list) or len(pair) != 2 or
                type(pair[0]) is not float or type(pair[1]) is not float
                for pair in wavelengths)):
        raise ValueError("special terrain surface facet wavelength record is incomplete")
    if set(metadata["kernel_revisions"]) != set(KERNEL_FILES) or any(
            not isinstance(value, str) or len(value) != 64
            for value in metadata["kernel_revisions"].values()):
        raise ValueError("special terrain surface kernel revision record is incomplete")
    if not isinstance(metadata["parent_identity_sha256"], str) or \
            len(metadata["parent_identity_sha256"]) != 64:
        raise ValueError("missing parent identity")
    if any(field in metadata["dissection_recipe"] for field in RETIRED_RECIPE_FIELDS):
        raise ValueError("retired dissection recipe field is still present")
    try:
        facet = FacetRoughnessRecipe(**metadata["facet_recipe"])
        dissection = DissectionRecipe(**metadata["dissection_recipe"])
    except TypeError as error:
        raise ValueError(f"invalid special terrain surface recipe: {error}") from error
    if metadata["facet_recipe"] != _canonical(asdict(facet)) or \
            metadata["dissection_recipe"] != _canonical(asdict(dissection)):
        raise ValueError("invalid special terrain surface recipe")
    if not all(isinstance(value, np.ndarray) for value in arrays.values()):
        raise ValueError("invalid special terrain surface arrays")
    reference = arrays["reference_xyz_m"]
    displacement = arrays["displacement_xyz_m"]
    vertices = arrays["vertices_xyz_m"]
    triangles = arrays["triangles"]
    mask = arrays["protected_mask"]
    surface = arrays["surface_xyz_m"]
    change = arrays["erosion_change_m"]
    shape = reference.shape[:2]
    if (reference.ndim != 3 or reference.shape[2] != 3 or min(shape) < 3 or
            shape[0] * shape[1] > MAX_CELLS or reference.dtype != np.float64 or
            displacement.shape != reference.shape or displacement.dtype != np.float64 or
            surface.shape != reference.shape or surface.dtype != np.float64 or
            change.shape != shape or change.dtype != np.float64 or
            vertices.shape != (shape[0] * shape[1], 3) or vertices.dtype != np.float64 or
            mask.shape != shape or mask.dtype != bool or
            triangles.shape != (2 * (shape[0] - 1) * (shape[1] - 1), 3) or
            triangles.dtype != np.int64):
        raise ValueError("invalid special terrain surface array shape or dtype")
    maximum = _check_uniform_chart(reference)[1]
    if maximum <= 0.0:
        raise ValueError("invalid special terrain surface chart spacing")
    if [tuple(pair) for pair in wavelengths] != list(facet.wavelengths_m(maximum)):
        raise ValueError("special terrain surface facet wavelengths disagree with the recipe")
    if facet.finest_cells < SAMPLES_PER_FEATURE:
        raise ValueError("special terrain surface facet octave below the sampling limit")
    # The rock floor is a depth below the roughened surface, so the relief the floor and
    # the mobile column are measured against is the *post-facet* one the producer saw.
    # Pinning it to the stored displacement keeps both bounds recomputable by a reader
    # that never imports the builder.
    for name in ("relief_reference_m", "roughened_relief_reference_m"):
        _finite_number(metadata[name], name, positive=True)
    if (metadata["roughened_relief_reference_m"] != float(np.max(displacement[:, :, 1])) or
            metadata["roughened_relief_reference_m"] < metadata["relief_reference_m"]):
        raise ValueError("special terrain surface roughened relief disagrees with the arrays")
    vertical = np.zeros_like(reference)
    vertical[:, :, 1] = change
    if (not np.isfinite(reference).all() or not np.isfinite(displacement).all() or
            not np.isfinite(surface).all() or not np.isfinite(change).all() or
            not np.array_equal(vertices, surface.reshape(-1, 3)) or
            not np.array_equal(triangles, _triangles(*shape)) or
            not np.array_equal(surface, reference + displacement + vertical)):
        raise ValueError("invalid special terrain surface geometry")
    if (np.any(displacement[:, :, 0] != 0) or np.any(displacement[:, :, 2] != 0) or
            np.any(displacement[0, :, 1] != 0) or np.any(displacement[-1, :, 1] != 0) or
            np.any(displacement[:, 0, 1] != 0) or np.any(displacement[:, -1, 1] != 0) or
            np.any(change[mask] != 0.0) or
            not np.array_equal(surface[0], reference[0]) or
            not np.array_equal(surface[-1], reference[-1]) or
            not np.array_equal(surface[:, 0], reference[:, 0]) or
            not np.array_equal(surface[:, -1], reference[:, -1])):
        raise ValueError("special terrain surface does not close on its collar")
    _check_mesh(vertices, triangles)
    ledger = metadata["ledger"]
    if (ledger["relaxation_tolerance_m"] != dissection.tolerance_m or
            ledger["relaxation_sweep_budget"] != dissection.max_sweeps):
        raise ValueError("special terrain surface relaxation budget disagrees with the recipe")
    steps = ledger["steps"]
    if (not isinstance(steps, list) or len(steps) != dissection.steps or
            [step["step_index"] for step in steps] != list(range(dissection.steps))):
        raise ValueError("special terrain surface step ledger does not match the recipe")
    # ``relaxation_converged`` is a *derived* quantity, never a trusted one: the kernel
    # defines convergence as ``maximum_mobile_excess_after_m <= tolerance_m``, and every
    # operand of that comparison is stored per step.  Re-deriving it here means a bundle
    # cannot assert a convergence its own numbers contradict.
    if any(bool(step["relaxation_converged"]) !=
           (step["relaxation_maximum_excess_m"] <= dissection.tolerance_m)
           for step in steps):
        raise ValueError("special terrain surface relaxation flag disagrees with its excess")
    if ledger["relaxation_converged"] is not all(
            step["relaxation_maximum_excess_m"] <= dissection.tolerance_m for step in steps):
        raise ValueError("special terrain surface relaxation summary disagrees with its steps")
    if (ledger["relaxation_maximum_excess_m"] !=
            max(step["relaxation_maximum_excess_m"] for step in steps) or
            ledger["relaxation_sweeps_max"] !=
            max(step["relaxation_sweeps"] for step in steps)):
        raise ValueError("special terrain surface relaxation extremes disagree with its steps")
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("special terrain surface identity mismatch")
    return True


def _surface_headers(headers):
    if set(headers) != ARRAY_KEYS | {"manifest"}:
        raise ValueError("unexpected special terrain surface archive fields")
    shape, dtype = headers["reference_xyz_m"]
    if (len(shape) != 3 or shape[2] != 3 or min(shape[:2]) < 3 or
            shape[0] * shape[1] > MAX_CELLS or dtype != np.float64):
        raise ValueError("invalid special terrain surface reference header")
    rows, cols = shape[:2]
    expected = {"displacement_xyz_m": (shape, np.dtype("float64")),
                "surface_xyz_m": (shape, np.dtype("float64")),
                "erosion_change_m": ((rows, cols), np.dtype("float64")),
                "vertices_xyz_m": ((rows * cols, 3), np.dtype("float64")),
                "triangles": ((2 * (rows - 1) * (cols - 1), 3), np.dtype("int64")),
                "protected_mask": ((rows, cols), np.dtype("bool"))}
    if any(headers[key] != value for key, value in expected.items()):
        raise ValueError("invalid special terrain surface array header")
    manifest_shape, manifest_dtype = headers["manifest"]
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= MAX_METADATA or manifest_dtype != np.uint8:
        raise ValueError("invalid special terrain surface manifest header")


def save_special_form_surface(path, result):
    save_bundle(path, result, validator=validate_special_form_surface)


def load_special_form_surface(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError("expected special terrain surface identity required")
    result = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_special_form_surface, header_validator=_surface_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external special terrain surface identity mismatch")
    return result
