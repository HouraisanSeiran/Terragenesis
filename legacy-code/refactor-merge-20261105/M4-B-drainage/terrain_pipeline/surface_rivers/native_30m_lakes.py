"""Native 30 m lake basins: membership, a provable saddle, V(h), and a level-pool spill.

What this module adds, and what it does not
-------------------------------------------
At TD's native 30 m a lake needs three things, and the repository already owns the
physics of each:

* **the storage curve** -- ``metric_lake_storage.LakeStorage`` integrates the exact
  step function ``V(h) = sum over cells max(h - bed, 0) * area`` over an explicit
  bed population. It is not a vertical-wall tank as long as it is handed the
  terrain's own bed population; ``metric_lake_hypsometry`` explains at length that
  the tank came from a one-cell *support*, not from the class;
* **the basin and its escape level** -- ``metric_lake_hypsometry.depression_hierarchy``
  (border-seeded priority flood) and ``depression_component``;
* **the level-pool march with saddle overflow** -- ``world_reach_lake.integrate_sill_lake``
  splits each step into storage and spill through the existing
  ``metric_lake_storage.LakeOutlet`` weir rating, capped by the water actually
  present, so its ledger closes by construction.

None of that is rewritten here. This module is the layer the repository did not
have: it **derives** the lake from a 30 m bed, **measures and checks** the lowest
saddle instead of asserting it, and **refuses** every case the window cannot
answer, with a stable reason code, before any storage is built.

Historical raster saddle probe
------------------------------------------------------------------
The previous raster implementation used inconsistent component/rim adjacency. On 40
noise fields (48x48, `world_seed=20261020`) the depression gate found 10 567 closed
depressions, and for **8 173** of them (77.3 %) the lowest *bed* on the 8-neighbour
rim lay **below** the level at which the basin actually escapes -- by up to
**12.54 m**. The reason is geometric, not numerical: the rim of a 4-connected
component is 8-adjacent, so it contains cells that are inside the same lake but
reachable only diagonally. Their bed is a shallow shelf, not a crossing. These are
historical measurements, not results of the current irregular graph. Components,
rims, exits, and raw catchments now all use the same graph connectivity.

What *is* provable is the flood's own answer. The priority flood assigns
``filled`` = the minimum over drainage paths to the border of the maximum elevation
on that path, so **every** cell of a closed depression carries the same ``filled``
value and that value *is* the level at which the basin escapes. Measured on the
same 40 fields plus three analytic bowls: ``max(filled) - min(filled) = 0.0`` over
the component and ``0.0`` over its rim -- exact, on all 5 301 depressions of the
second probe. So this module:

1. treats ``spill_level_m`` as ``filled`` on the basin and **verifies it is
   constant** over the basin (a measured check, not a re-derivation);
2. identifies the **exit set** -- graph-adjacent nodes outside the basin whose
   ``filled`` equals that level exactly -- and requires it to be non-empty;
3. reports the naive ``min bed over rim`` separately, as a *rejected* number with
   its measured difference, so nobody can quietly adopt it again.

What it refuses, and why that is the point
------------------------------------------
A 30 m window has three ways of producing a confident and wrong lake:

1. the basin rim lies inside the untrusted border band, so the flood drained off
   the page and the reported level is the window edge, not a saddle
   (``REASON_RIM_IN_BAND``);
2. every exit cell lies inside that band, so *where* the overflow goes is
   undeclared (``REASON_SADDLE_IN_BAND``);
3. the contributing area reaches the window border, so water enters from outside
   the resolved window and neither inflow nor the storage/inflow balance can be
   judged here (``REASON_UPSTREAM_UNKNOWN``).

All three are ``truncated_not_judged``: a measurement defect, not a fact about the
terrain. The answer is a bigger window, never a smaller number reported as if it
were measured. The band is the repository's own constant
(``metric_cross_region.CONTACT_MARGIN_CELLS``), the same one the micro-depression
gate uses, so the two cannot drift apart.

Two inputs are refused for a different reason -- they are not truncation but a
wrong object:

* a **water surface is never a bed**. ``surface_kind`` is a required declaration
  and must be ``bed_elevation_m``; behaviourally, a flat or filled level field has
  zero fill depth everywhere and therefore yields ``REASON_NO_DEPRESSION`` (the
  tests feed a real lake's own filled surface back in and require the refusal);
* a **lowland that drains** (a slope, a flat, an open valley floor) has no closed
depression at the seed, so it also yields ``REASON_NO_DEPRESSION``. Being low is
  not being a lake.

A second ledger, never merged with the first
--------------------------------------------
``lake / puddle`` is a different question from ``is this basin measurable``, and
`metric_depression_gate.judge_depression` is the repository's answer to it. It is
called here on the same measured numbers and reported under ``gate``; it never
changes ``certified`` and ``certified`` never changes it. Criteria (c) growth and
(d) rim clearance are this module's own band and exit refusals, so the gate is
called with ``require_growth_convergence=False`` and every record says so.

Units, tolerances, budgets
--------------------------
elevation and stage in m, area in m2, volume in m3, physical time in s, discharge
in m3 s-1, the ``LakeOutlet`` coefficient in m3 s-1 m-1.5, spacing in m (native
30 m, cell area = spacing^2). See ``UNITS``, ``TOLERANCES`` and ``BUDGETS``; every
record carries them, so no reader has to trust this paragraph.

Above the saddle, ``LakeStorage`` cannot represent lateral flooding of the plateau
behind a sill, so the store is given ``max_stage_m = spill + head_allowance`` with
an **explicitly declared** ``head_allowance_m``. Between the two, V(h) is
``A(spill) * head`` -- a declared pondage, not measured terrain -- and the record
says so (``above_saddle_pondage_policy``). Nothing is granted silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from terrain_pipeline.common_infra import readonly
from terrain_pipeline.irregular_grid import grid_mesh
from terrain_pipeline.surface_rivers.metric_cross_region import CONTACT_MARGIN_CELLS
from terrain_pipeline.surface_rivers.metric_depression_gate import (
    DEFAULT_ALPHA, DEFAULT_MIN_AREA_M2, GROWTH_SINGLE_WINDOW, INFLOW_UNFILLED_CATCHMENT,
    MAX_GATE_CELLS, DepressionGateConfig, judge_depression, rim_clearance_cells,
    unfilled_catchment_flow)
from terrain_pipeline.surface_rivers.metric_lake_hypsometry import (
    MAX_HYPSOMETRY_CELLS, depression_component, depression_hierarchy)
from terrain_pipeline.surface_rivers.metric_lake_storage import LakeOutlet, LakeStorage
from terrain_pipeline.surface_rivers.world_reach_lake import (
    integrate_sill_lake, sill_coefficient_m3_s_m15)


SCHEMA = "terrain-pipeline-native-30m-lake-v1"
ALGORITHM = "native-30m-irregular-terrain-hypsometry-level-pool-v2"

# The only surface this module may be handed. A water surface is a *result* of a
# lake model; reading one back as a bed would let a lake certify itself.
BED_SURFACE_KIND = "bed_elevation_m"
WATER_SURFACE_KINDS = ("water_surface_m", "stage_m", "filled_surface_m")

REASON_CERTIFIED = "certified_closed_basin_lowest_saddle"
REASON_NO_DEPRESSION = "no_depression_at_seed"
REASON_WINDOW_UNRESOLVED = "window_not_fully_resolved"
REASON_RIM_IN_BAND = "rim_inside_untrusted_band"
REASON_SADDLE_IN_BAND = "exit_set_inside_untrusted_band"
REASON_SADDLE_ABSENT = "basin_has_no_exit_cell"
REASON_FILL_NOT_CONSTANT = "flood_level_not_constant_over_basin"
REASON_UPSTREAM_UNKNOWN = "upstream_unknown_in_catchment"
REASON_MEMBERSHIP_LEAK = "basin_membership_not_self_draining"

REASON_CODES = (REASON_CERTIFIED, REASON_NO_DEPRESSION, REASON_WINDOW_UNRESOLVED,
                REASON_RIM_IN_BAND, REASON_SADDLE_IN_BAND, REASON_SADDLE_ABSENT,
                REASON_FILL_NOT_CONSTANT, REASON_UPSTREAM_UNKNOWN,
                REASON_MEMBERSHIP_LEAK)

# "This window cannot answer" as opposed to "the terrain answered, and the answer
# is not a lake". Only the latter two codes are a statement about the terrain.
TRUNCATION_REASONS = (REASON_WINDOW_UNRESOLVED, REASON_RIM_IN_BAND, REASON_SADDLE_IN_BAND,
                      REASON_SADDLE_ABSENT, REASON_FILL_NOT_CONSTANT,
                      REASON_UPSTREAM_UNKNOWN, REASON_MEMBERSHIP_LEAK)

UNITS = {
    "elevation_m": "m (the supplied bed's own vertical datum)",
    "stage_m": "m",
    "level_m": "m",
    "area_m2": "m2",
    "volume_m3": "m3",
    "time_seconds": "s (physical seconds)",
    "discharge_m3_s": "m3 s-1",
    "outlet_coefficient_m3_s_m15": "m3 s-1 m-1.5 (Q = C * head ** 1.5)",
    "spacing_m": "m (native 30 m; cell area = spacing ** 2)",
    "cells": "cell count at the declared spacing, not an area",
}

# The flood level is a pick from one float64 array, so equality is exact on the
# Python side; the tolerance is stated so a reader can see the check is not a fudge
# factor. The ledger tolerance is the round-off of a closed sum.
LEVEL_TOLERANCE_M = 1e-9
LEDGER_RELATIVE_TOLERANCE = 1e-12

TOLERANCES = {
    "flood_level_constancy_m": LEVEL_TOLERANCE_M,
    "exit_level_agreement_m": LEVEL_TOLERANCE_M,
    "level_round_trip_m": 1e-9,
    "volume_round_trip_relative": 1e-12,
    "ledger_residual_relative": LEDGER_RELATIVE_TOLERANCE,
}

MAX_FIELD_CELLS = MAX_GATE_CELLS          # one field budget, shared with the gate
MAX_MARCH_STEPS = 200_000
MAX_TRACE_BYTES = 64 * 1024 * 1024

BUDGETS = {
    "max_field_cells": MAX_FIELD_CELLS,
    "max_basin_cells": MAX_HYPSOMETRY_CELLS,
    "max_march_steps": MAX_MARCH_STEPS,
    "max_trace_bytes": MAX_TRACE_BYTES,
}



# --------------------------------------------------------------------------- #
# guards
# --------------------------------------------------------------------------- #
def _finite_number(value, name):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not math.isfinite(float(value))):
        raise ValueError(name + " must be finite numeric")
    return float(value)


def _positive_number(value, name):
    number = _finite_number(value, name)
    if number <= 0.:
        raise ValueError(name + " must be finite positive")
    return number


def _sha(value, name):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError(name + " must be a lowercase SHA256")
    return value


def _bed(elevation_m):
    bed = np.asarray(elevation_m, np.float64)
    if bed.ndim != 2 or min(bed.shape) < 3:
        raise ValueError("a 2D bed of at least 3x3 cells is required")
    if bed.size > MAX_FIELD_CELLS:
        raise ValueError("field of %d cells exceeds the declared budget of %d"
                         % (bed.size, MAX_FIELD_CELLS))
    if not np.isfinite(bed).all():
        raise ValueError("finite elevation required: an unknown cell must be declared "
                         "through resolved_mask, never through NaN, which would let a "
                         "hole decide a path")
    return bed


def _mask(resolved_mask, shape):
    mask = np.asarray(resolved_mask)
    if mask.dtype != np.bool_ or mask.shape != shape:
        raise ValueError("a boolean resolved_mask of the bed's shape is required")
    if not mask.any():
        raise ValueError("no resolved cells: an all-unknown window has no basin")
    return mask


def _seed(seed_cell_rc, shape):
    row, column = (int(value) for value in seed_cell_rc)
    if not (0 <= row < shape[0] and 0 <= column < shape[1]):
        raise ValueError("seed cell outside the field")
    return row, column


def _graph_rim(mask, mesh):
    out = np.zeros_like(mask)
    for cell in np.flatnonzero(mask.ravel()):
        out.ravel()[mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]] = True
    return out & ~mask


# --------------------------------------------------------------------------- #
# measurement: membership, exit set, catchment
# --------------------------------------------------------------------------- #
def measure_basin(elevation_m, seed_cell_rc, *, mesh=None):
    """The seed cell's drainage depression: filled level, fill depth, member mask.

    Reuses ``metric_lake_hypsometry``. The returned mask is that module's
    graph-connected positive-fill-depth component -- the basin's **member** set, not
    "every cell below the spill level", which would also include the plateau
    outside the rim.

    Returns ``(filled_m, fill_depth_m, basin_mask_or_None)``.
    """
    bed = _bed(elevation_m)
    seed = _seed(seed_cell_rc, bed.shape)
    mesh = grid_mesh(bed.shape) if mesh is None else mesh
    filled, depth = depression_hierarchy(bed, mesh=mesh)
    mask = depression_component(depth, seed, mesh=mesh)
    return filled, depth, mask


def lowest_saddle(elevation_m, filled_m, basin_mask, spill_level_m,
                  tolerance_m=LEVEL_TOLERANCE_M, *, mesh=None):
    """The exit set of a basin, and the two saddle numbers kept apart.

    ``spill_level_m`` is the flood's own level on the basin, and the exit set is the
    graph-adjacent nodes outside the basin whose ``filled`` equals it exactly. Those are
    the crossings water actually uses, and their presence is the proof that the
    level is a saddle and not the window edge.

    ``geometric_rim_minimum_m`` is the number this module **rejects**: the lowest
    *bed* on the rim. It is reported with its measured difference so a reader can see
    it was considered, and so the 77 % of depressions where it is below the true
    level cannot be quietly re-adopted later.
    """
    bed = np.asarray(elevation_m, np.float64)
    filled = np.asarray(filled_m, np.float64)
    mask = np.asarray(basin_mask, bool)
    if bed.shape != mask.shape or filled.shape != mask.shape:
        raise ValueError("bed, filled level and basin mask must share a shape")
    if not mask.any():
        raise ValueError("nonempty basin mask required")
    spill = _finite_number(spill_level_m, "spill_level_m")
    tolerance = _finite_number(tolerance_m, "tolerance_m")
    mesh = grid_mesh(bed.shape) if mesh is None else mesh
    rim = _graph_rim(mask, mesh)
    record = {"rim_mask": readonly(rim), "rim_cells": int(rim.sum()),
              "spill_level_m": spill, "present": False, "exit_cells": 0,
              "exit_mask": readonly(np.zeros_like(rim)), "exit_flat_indices": (),
              "exit_min_clearance_cells": -1, "exit_max_clearance_cells": -1,
              "geometric_rim_minimum_m": float("nan"),
              "geometric_minus_spill_m": float("nan"),
              "flood_level_constancy_m": 0.0}
    if not rim.any():
        return record
    basin_levels = filled[mask]
    constancy = float(basin_levels.max() - basin_levels.min())
    record["flood_level_constancy_m"] = constancy
    record["geometric_rim_minimum_m"] = float(bed[rim].min())
    record["geometric_minus_spill_m"] = float(bed[rim].min()) - spill
    if constancy > tolerance:
        return record
    exits = rim & (np.abs(filled - spill) <= tolerance)
    if not exits.any():
        return record
    rows, columns = bed.shape
    flat_count = np.flatnonzero(exits.reshape(-1))
    rr, cc = np.nonzero(exits)
    clearance = np.minimum(np.minimum(rr, cc),
                           np.minimum(rows - 1 - rr, columns - 1 - cc))
    record.update(present=True, exit_cells=int(exits.sum()),
                  exit_mask=readonly(exits),
                  exit_flat_indices=tuple(int(value) for value in flat_count),
                  exit_min_clearance_cells=int(clearance.min()),
                  exit_max_clearance_cells=int(clearance.max()),
                  exit_level_agreement_m=float(np.abs(filled[exits] - spill).max()),
                  exit_row_column=[[int(r), int(c)] for r, c in zip(rr, cc)])
    return record


def basin_catchment(elevation_m, basin_mask, *, mesh=None):
    """Cells whose raw metric irregular graph ends on a basin minimum.

    Reuses ``metric_depression_gate.unfilled_catchment_flow`` for the raw receiver
    graph and walks it upward here (one donor list, one stack): a topological sum,
    not a second routing solve.

    ``unknown_mask`` marks catchment cells on the window border, where the flood has
    no neighbour to read: water enters there from outside the resolved window, so the
    inflow is undeclared. ``leaked_cells`` counts basin members the catchment failed
    to reach; a nonempty set means the two traversals disagree about the basin and
    the honest answer is a refusal, not a repair.

    Stated limit: on flat ground raw strict-downhill routing has almost no structure,
    so a basin fed by a plateau draws a small catchment. That is a property of the
    terrain at 30 m, not of this traversal; ``metric_depression_gate`` documents the
    same effect and it is why this module reports the count instead of a verdict.
    """
    bed = np.asarray(elevation_m, np.float64)
    mask = np.asarray(basin_mask, bool)
    if bed.shape != mask.shape:
        raise ValueError("bed and basin mask must share a shape")
    if not mask.any():
        raise ValueError("nonempty basin mask required")
    accumulator, receiver, is_minimum = unfilled_catchment_flow(bed, mesh=mesh)
    flat_receiver = np.asarray(receiver, np.int64).reshape(-1)
    flat_minimum = np.asarray(is_minimum, bool).reshape(-1)
    flat_mask = mask.reshape(-1)
    donors = {}
    for cell, target in enumerate(flat_receiver):
        if target >= 0:
            donors.setdefault(int(target), []).append(cell)
    reached = np.zeros(flat_receiver.size, bool)
    pending = [int(cell) for cell in np.flatnonzero(flat_minimum & flat_mask)]
    for cell in pending:
        reached[cell] = True
    while pending:
        cell = pending.pop()
        for donor in donors.get(cell, ()):
            if not reached[donor]:
                reached[donor] = True
                pending.append(donor)
    catchment = reached.reshape(bed.shape)
    border = np.zeros(bed.shape, bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    unknown = catchment & border
    leaked = mask & ~catchment
    return {"catchment_mask": readonly(catchment), "unknown_mask": readonly(unknown),
            "contributing_cells": int(catchment.sum()),
            "unknown_cells": int(unknown.sum()), "leaked_cells": int(leaked.sum()),
            "basin_minimum_cells": int(np.count_nonzero(flat_minimum & flat_mask)),
            "raw_catchment_cells": accumulator}


# --------------------------------------------------------------------------- #
# the lake
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Native30mLake:
    """One 30 m lake basin: certified geometry, its store, and its saddle rating.

    ``storage`` and ``outlets`` are exactly the two attributes
    ``world_reach_lake.integrate_sill_lake`` reads, so ``march_lake`` hands this
    object to it directly -- that call *is* the reuse, not a second level-pool core.
    """

    certified: bool
    reason_code: str
    seed_row_column: tuple
    spacing_m: float
    cell_area_m2: float
    basin_mask: np.ndarray
    basin_cells: int
    basin_area_m2: float
    bed_min_m: float
    spill_level_m: float
    rim_clearance_cells: int
    saddle: dict
    catchment: dict
    storage: object
    outlets: tuple
    head_allowance_m: float
    provenance: dict = field(default_factory=dict)

    @property
    def truncated_not_judged(self):
        """The window could not answer; the number would be a measurement artefact."""
        return self.reason_code in TRUNCATION_REASONS

    @property
    def capacity_at_spill_m3(self):
        """Water held when the basin is exactly at its lowest saddle."""
        if self.storage is None:
            return float("nan")
        return float(self.storage.volume_at_stage(self.spill_level_m))

    @property
    def storage_capacity_m3(self):
        """Water held at the declared top of the store (spill + head allowance)."""
        if self.storage is None:
            return float("nan")
        return float(self.storage.capacity_m3)

    @property
    def outlet_crest_m(self):
        return float(self.outlets[0].crest_stage_m) if self.outlets else float("nan")

    def level_table(self, levels_m):
        """A(h)/V(h) straight from the store, so a table cannot disagree with it."""
        if self.storage is None:
            raise ValueError("a refused basin has no storage curve to tabulate")
        rows = []
        for level in np.asarray(levels_m, np.float64):
            clamped = float(min(max(level, self.storage.min_stage_m),
                                self.storage.max_stage_m))
            rows.append({"stage_m": float(level), "clamped_stage_m": clamped,
                         "area_m2": float(self.storage.surface_area_at_stage(clamped)),
                         "volume_m3": float(self.storage.volume_at_stage(clamped))})
        return rows

    def as_record(self):
        """JSON-safe record: counts and declared numbers, never an array or an inf."""
        record = {
            "schema": SCHEMA, "algorithm": ALGORITHM,
            "certified": bool(self.certified), "reason_code": self.reason_code,
            "truncated_not_judged": bool(self.truncated_not_judged),
            "seed_row_column": [int(value) for value in self.seed_row_column],
            "spacing_m": float(self.spacing_m), "cell_area_m2": float(self.cell_area_m2),
            "basin_cells": int(self.basin_cells),
            "basin_area_m2": float(self.basin_area_m2),
            "bed_min_m": _jsonable(self.bed_min_m),
            "spill_level_m": _jsonable(self.spill_level_m),
            "rim_clearance_cells": int(self.rim_clearance_cells),
            "saddle_present": bool(self.saddle.get("present", False)),
            "saddle_rim_cells": int(self.saddle.get("rim_cells", 0)),
            "saddle_exit_cells": int(self.saddle.get("exit_cells", 0)),
            "saddle_exit_min_clearance_cells": int(
                self.saddle.get("exit_min_clearance_cells", -1)),
            "saddle_exit_max_clearance_cells": int(
                self.saddle.get("exit_max_clearance_cells", -1)),
            "flood_level_constancy_m": _jsonable(
                self.saddle.get("flood_level_constancy_m", 0.0)),
            "rejected_geometric_rim_minimum_m": _jsonable(
                self.saddle.get("geometric_rim_minimum_m", float("nan"))),
            "rejected_geometric_minus_spill_m": _jsonable(
                self.saddle.get("geometric_minus_spill_m", float("nan"))),
            "contributing_cells": int(self.catchment.get("contributing_cells", 0)),
            "unknown_upstream_cells": int(self.catchment.get("unknown_cells", 0)),
            "catchment_leaked_cells": int(self.catchment.get("leaked_cells", 0)),
            "capacity_at_spill_m3": _jsonable(self.capacity_at_spill_m3),
            "storage_capacity_m3": _jsonable(self.storage_capacity_m3),
            "outlet_crest_m": _jsonable(self.outlet_crest_m),
            "head_allowance_m": float(self.head_allowance_m),
            "units": dict(UNITS), "tolerances": dict(TOLERANCES),
            "budgets": dict(BUDGETS),
            "hydraulic_ready": False, "natural_outlet_verified": False,
            "publishable": False,
        }
        for key, value in self.provenance.items():
            record.setdefault(key, value)
        return record


def _jsonable(value):
    number = float(value)
    return number if math.isfinite(number) else None


def _refused(reason, *, seed, spacing, cell_area, basin_mask, basin_cells, bed_min,
             spill, clearance, saddle, catchment, allowance, provenance):
    return Native30mLake(
        certified=False, reason_code=reason, seed_row_column=seed, spacing_m=spacing,
        cell_area_m2=cell_area, basin_mask=readonly(basin_mask), basin_cells=int(basin_cells),
        basin_area_m2=int(basin_cells) * cell_area, bed_min_m=float(bed_min),
        spill_level_m=float(spill), rim_clearance_cells=int(clearance), saddle=saddle,
        catchment=catchment, storage=None, outlets=(), head_allowance_m=allowance,
        provenance=dict(provenance, refusal_stage=reason,
                        refusal_policy=("a refused basin reports no store, no outlet and "
                                        "no certified spill level; the reason code is "
                                        "stable and it is the window -- not the number "
                                        "-- that has to change")))


def build_native_30m_lake(elevation_m, resolved_mask, *, seed_cell_rc, spacing_m,
                          origin_xz_m, source_identity_sha256, surface_kind,
                          sill_width_m, discharge_coefficient, head_allowance_m,
                          contact_margin_cells=CONTACT_MARGIN_CELLS,
                          level_tolerance_m=LEVEL_TOLERANCE_M,
                          max_cells=MAX_HYPSOMETRY_CELLS, produced_depth_m=None,
                          sill_provenance="declared saddle weir width", provenance=None):
    """Derive one lake from a 30 m **bed**, or refuse it with a stable reason code.

    The checks run in a fixed order, so a basin failing several is always explained
    by the same one and two runs cannot disagree about why:

        surface declaration -> domain facts -> fully resolved window -> basin
        presence -> member budget -> flood level constant -> exit set present ->
        rim clearance -> exit clearance -> catchment unknown -> catchment leak ->
        certified

    ``produced_depth_m`` is optional: when given, the unfilled-catchment inflow and
    the ``lake / pass_through`` gate are computed and reported on the same numbers.
    Certification never depends on it.
    """
    if surface_kind != BED_SURFACE_KIND:
        raise ValueError("surface_kind must be %r: %r names a lake-model result, and a "
                         "water surface must never be read back as a bed"
                         % (BED_SURFACE_KIND, surface_kind))
    bed = _bed(elevation_m)
    mask = _mask(resolved_mask, bed.shape)
    seed = _seed(seed_cell_rc, bed.shape)
    spacing = _positive_number(spacing_m, "spacing_m")
    cell_area = spacing * spacing
    allowance = _positive_number(head_allowance_m, "head_allowance_m")
    width = _positive_number(sill_width_m, "sill_width_m")
    coefficient_cd = _positive_number(discharge_coefficient, "discharge_coefficient")
    strength = contact_margin_cells
    if type(strength) is not int or strength < 0:
        raise ValueError("non-negative integer contact_margin_cells required")
    tolerance = _finite_number(level_tolerance_m, "level_tolerance_m")
    if tolerance < 0.:
        raise ValueError("level_tolerance_m must be nonnegative")
    limit = int(max_cells)
    if not 4 <= limit <= MAX_HYPSOMETRY_CELLS:
        raise ValueError("max_cells must be 4..%d" % MAX_HYPSOMETRY_CELLS)
    _sha(source_identity_sha256, "source_identity_sha256")
    origin = np.asarray(origin_xz_m, np.float64).reshape(-1)
    if origin.size != 2 or not np.isfinite(origin).all():
        raise ValueError("finite [x, z] origin required")
    if not isinstance(sill_provenance, str) or not sill_provenance.strip():
        raise ValueError("sill width provenance required")
    if produced_depth_m is not None:
        depth_value = _finite_number(produced_depth_m, "produced_depth_m")
        if depth_value < 0.:
            raise ValueError("produced_depth_m must be nonnegative")
    else:
        depth_value = None

    base = {
        "surface_kind": surface_kind,
        "sill_width_m": width, "discharge_coefficient": coefficient_cd,
        "outlet_coefficient_m3_s_m15": sill_coefficient_m3_s_m15(
            width, discharge_coefficient=coefficient_cd),
        "sill_provenance": sill_provenance,
        "contact_margin_cells": int(strength), "level_tolerance_m": tolerance,
        "origin_xz_m": [float(origin[0]), float(origin[1])],
        "source_identity_sha256": source_identity_sha256,
        "support_policy": ("one store cell per %.3f m terrain cell of the seed cell's "
                           "graph-connected positive-fill-depth drainage depression" % spacing),
        "saddle_policy": ("exit set = graph-adjacent nodes outside the depression whose "
                          "priority-flood level equals the basin's own; the flood level "
                          "is the saddle elevation, and the lowest rim *bed* is "
                          "reported as rejected"),
        "above_saddle_pondage_policy": (
            "V(h) for h > spill is A(spill) * (h - spill) up to spill + %.6f m of declared "
            "weir head: a declared pondage, not measured terrain" % allowance),
        "gate_policy": ("judge_depression with require_growth_convergence=False; criteria "
                        "(c) growth and (d) rim clearance are this module's own band and "
                        "exit refusals, so they are not evaluated twice"),
        "hydraulic_model": "reduced_level_pool_signed_sill_weir_not_saint_venant",
        "units": dict(UNITS), "tolerances": dict(TOLERANCES),
        "budgets": dict(BUDGETS),
    }
    if provenance:
        base.update(dict(provenance))
    empty_catchment = {"contributing_cells": 0, "unknown_cells": 0, "leaked_cells": 0,
                       "basin_minimum_cells": 0}
    empty_saddle = {"present": False, "rim_cells": 0, "exit_cells": 0,
                    "exit_min_clearance_cells": -1, "exit_max_clearance_cells": -1,
                    "geometric_rim_minimum_m": float("nan"),
                    "geometric_minus_spill_m": float("nan"),
                    "flood_level_constancy_m": 0.0}

    def refuse(reason, basin_mask=None, basin_cells=0, bed_min=float("nan"),
               spill=float("nan"), clearance=-1, saddle=None, catchment=None):
        return _refused(
            reason, seed=(seed[0], seed[1]), spacing=spacing, cell_area=cell_area,
            basin_mask=(np.zeros(bed.shape, bool) if basin_mask is None else basin_mask),
            basin_cells=basin_cells, bed_min=bed_min, spill=spill, clearance=clearance,
            saddle=dict(empty_saddle if saddle is None else saddle),
            catchment=dict(empty_catchment if catchment is None else catchment),
            allowance=allowance, provenance=base)

    if not mask.all():
        # `depression_hierarchy` requires a fully valid window for the same reason:
        # with a hole in it the flood has no neighbour to read and would answer for a
        # different basin.
        return refuse(REASON_WINDOW_UNRESOLVED, bed_min=float(bed[seed]))

    mesh = grid_mesh(bed.shape, x0_m=origin[0], z0_m=origin[1], dx_m=spacing)
    filled, depth, basin = measure_basin(bed, seed, mesh=mesh)
    if basin is None:
        # No closed depression at the seed: a slope, a flat, a lowland that drains --
        # or a water surface, whose fill depth is zero everywhere by construction.
        return refuse(REASON_NO_DEPRESSION, bed_min=float(bed[seed]))
    cells = int(basin.sum())
    if cells > limit:
        raise ValueError("basin of %d cells exceeds the declared store limit of %d"
                         % (cells, limit))
    beds = np.ascontiguousarray(bed[basin], np.float64)
    bed_min = float(beds.min())
    levels = filled[basin]
    spill = float(levels.max())
    clearance = rim_clearance_cells(basin, bed.shape)
    saddle = lowest_saddle(bed, filled, basin, spill, tolerance_m=tolerance, mesh=mesh)
    catchment = basin_catchment(bed, basin, mesh=mesh)

    if float(saddle.get("flood_level_constancy_m", 0.0)) > tolerance:
        return refuse(REASON_FILL_NOT_CONSTANT, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if not saddle["present"]:
        return refuse(REASON_SADDLE_ABSENT, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if clearance < strength:
        return refuse(REASON_RIM_IN_BAND, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if int(saddle["exit_min_clearance_cells"]) < strength:
        return refuse(REASON_SADDLE_IN_BAND, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if int(catchment["unknown_cells"]) > 0:
        return refuse(REASON_UPSTREAM_UNKNOWN, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if int(catchment["leaked_cells"]) > 0:
        return refuse(REASON_MEMBERSHIP_LEAK, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if not spill > bed_min:
        raise ValueError("degenerate basin: the spill level does not exceed the bed")

    cell_ids = np.flatnonzero(basin.reshape(-1)).astype(np.int64)
    areas = np.full(cell_ids.size, cell_area, np.float64)
    store = LakeStorage(
        cell_ids=cell_ids, bed_elevation_m=beds, cell_area_m2=areas,
        seed_cell_id=int(cell_ids[int(np.argmin(beds))]),
        max_stage_m=spill + allowance, source_identity_sha256=source_identity_sha256,
        footprint_policy=(
            "closed_depression_30m_cells; A(h) and V(h) are the terrain's own "
            "hypsometry over %d cells at %.3f m; no shape function is imposed"
            % (cells, spacing)))
    outlets = (LakeOutlet(
        0, -1, spill, sill_coefficient_m3_s_m15(width, discharge_coefficient=coefficient_cd),
        "saddle at the flood level %.9f m with %d exit cells (nearest to the window "
        "border: %d cells); %s"
        % (spill, int(saddle["exit_cells"]), int(saddle["exit_min_clearance_cells"]),
           sill_provenance)),)

    gate = None
    record_extra = {}
    if depth_value is not None:
        inflow = float(catchment["contributing_cells"]) * cell_area * depth_value
        verdict = judge_depression(
            basin_cells=cells, capacity_m3=float(store.volume_at_stage(spill)),
            inflow_m3=inflow, area_m2=cells * cell_area, spill_level_m=spill,
            config=DepressionGateConfig(
                alpha=DEFAULT_ALPHA, min_area_m2=DEFAULT_MIN_AREA_M2,
                contact_margin_cells=strength, require_growth_convergence=False),
            label=-1, input_quantity=INFLOW_UNFILLED_CATCHMENT,
            contributing_cells=float(catchment["contributing_cells"]),
            contributing_area_m2=float(catchment["contributing_cells"]) * cell_area,
            own_production_m3=cells * cell_area * depth_value,
            bed_min_m=bed_min, rim_clearance_cells=clearance, growth_converged=False,
            convergence_gate=GROWTH_SINGLE_WINDOW)
        gate = dict(verdict.as_record(), growth_evaluated=False,
                    produced_depth_m=depth_value)
        record_extra = {"gate": gate}

    return Native30mLake(
        certified=True, reason_code=REASON_CERTIFIED, seed_row_column=(seed[0], seed[1]),
        spacing_m=spacing, cell_area_m2=cell_area, basin_mask=readonly(basin),
        basin_cells=cells, basin_area_m2=cells * cell_area, bed_min_m=bed_min,
        spill_level_m=spill, rim_clearance_cells=clearance, saddle=saddle,
        catchment=catchment, storage=store, outlets=outlets,
        head_allowance_m=allowance,
        provenance=dict(base, relief_m=spill - bed_min,
                        capacity_at_spill_m3=float(store.volume_at_stage(spill)),
                        saddle_pondage_area_m2=float(store.surface_area_at_stage(spill)),
                        **record_extra))


# --------------------------------------------------------------------------- #
# initial water, inflow, and the spill / recession march
# --------------------------------------------------------------------------- #
def initial_volume_m3(lake, *, initial_stage_m):
    """Initial water as the volume at a declared stage, inside the certified support."""
    _require_certified(lake)
    stage = _finite_number(initial_stage_m, "initial_stage_m")
    if stage > lake.spill_level_m:
        raise ValueError("initial stage above the lowest saddle is overflow, not an "
                         "initial stock: start at or below %.9f m" % lake.spill_level_m)
    if stage < lake.storage.min_stage_m:
        raise ValueError("initial stage below the minimum bed")
    return float(lake.storage.volume_at_stage(stage))


def inflow_volume_m3(lake, *, produced_depth_m):
    """Inflow over a run: contributing cells x cell area x produced depth."""
    _require_certified(lake)
    depth = _finite_number(produced_depth_m, "produced_depth_m")
    if depth < 0.:
        raise ValueError("produced_depth_m must be nonnegative")
    cells = int(lake.catchment["contributing_cells"])
    return float(cells) * lake.cell_area_m2 * depth, {
        "contributing_cells": cells, "cell_area_m2": lake.cell_area_m2,
        "produced_depth_m": depth, "own_basin_cells": lake.basin_cells,
        "inflow_quantity": INFLOW_UNFILLED_CATCHMENT,
        "note": ("the unfilled catchment is the area that actually delivers to this "
                 "hole; a filled-arival reading would double-count upstream overflow")}


def march_lake(lake, inflow_volume_m3, dt_seconds, *, initial_volume_m3=0.0):
    """Storage, saddle overflow and recession through the existing sill-lake march.

    ``world_reach_lake.integrate_sill_lake`` does the stepping: storage first, then
    the existing ``LakeOutlet`` weir rating at the resolved stage, capped by the
    water actually present, so its ledger closes by construction. This function adds
    only declarations, the loss terms and the budget.
    """
    _require_certified(lake)
    inflow = np.asarray(inflow_volume_m3, np.float64)
    dt = np.asarray(dt_seconds, np.float64)
    if inflow.ndim != 1 or dt.ndim != 1 or inflow.shape != dt.shape or inflow.size == 0:
        raise ValueError("matching nonempty inflow and dt series required")
    if (not np.isfinite(inflow).all() or not np.isfinite(dt).all()
            or np.any(inflow < 0.) or np.any(dt <= 0.)):
        raise ValueError("finite nonnegative inflow and positive dt required")
    if inflow.size > MAX_MARCH_STEPS:
        raise ValueError("%d steps exceeds the declared march budget of %d"
                         % (inflow.size, MAX_MARCH_STEPS))
    if (inflow.size + 1) * (3 + len(lake.outlets)) * 8 > MAX_TRACE_BYTES:
        raise ValueError("trace byte budget exceeded before any allocation")
    start = _finite_number(initial_volume_m3, "initial_volume_m3")
    if start < 0. or start > lake.storage.capacity_m3:
        raise ValueError("initial lake inventory outside the declared finite support")
    trace = integrate_sill_lake(lake, inflow, dt, initial_volume_m3=start)
    ledger = dict(trace["ledger"])
    residual = float(ledger["residual_m3"])
    gross = float(ledger["initial_m3"]) + float(ledger["inflow_m3"])
    relative = abs(residual) / gross if gross > 0. else abs(residual)
    trace["loss_terms"] = {
        "saddle_overflow_m3": float(ledger["spill_m3"]),
        "residual_m3": residual,
        "evaporation_m3": None, "groundwater_m3": None,
        "policy": ("the only loss of this level pool is saddle overflow; evaporation and "
                   "groundwater are not modelled here and are declared None rather than "
                   "reported as zero"),
    }
    trace["ledger"] = ledger
    trace["ledger_residual_relative"] = relative
    trace["ledger_closed"] = bool(relative <= LEDGER_RELATIVE_TOLERANCE)
    trace["spill_level_m"] = lake.spill_level_m
    trace["requested_steps"] = int(inflow.size)
    trace["hydraulic_model"] = "reduced_level_pool_signed_sill_weir_not_saint_venant"
    trace["hydraulic_ready"] = False
    trace["natural_outlet_verified"] = False
    trace["publishable"] = False
    trace["units"] = dict(UNITS)
    trace["tolerances"] = dict(TOLERANCES)
    return trace


def _require_certified(lake):
    if not isinstance(lake, Native30mLake):
        raise ValueError("Native30mLake required")
    if not lake.certified or lake.storage is None:
        raise ValueError("basin is not certified (%s): it carries no storage curve"
                         % (lake.reason_code,))
    return lake


def validate_native_30m_lake(lake):
    """Internal consistency of one record; raises instead of returning a half lake."""
    if not isinstance(lake, Native30mLake):
        raise ValueError("Native30mLake required")
    if lake.reason_code not in REASON_CODES:
        raise ValueError("unknown reason code: %r" % (lake.reason_code,))
    if not lake.certified:
        if lake.storage is not None or lake.outlets:
            raise ValueError("a refused basin must carry no store and no outlet")
        if lake.reason_code == REASON_CERTIFIED:
            raise ValueError("a certified reason with certified=False")
        return True
    if lake.reason_code != REASON_CERTIFIED:
        raise ValueError("a certified basin must carry the certified reason")
    if lake.storage is None or len(lake.outlets) != 1:
        raise ValueError("a certified basin needs exactly one saddle outlet and a store")
    if abs(lake.storage.min_stage_m - lake.bed_min_m) > LEVEL_TOLERANCE_M:
        raise ValueError("store minimum stage is not the measured minimum bed")
    if abs(lake.storage.max_stage_m
           - (lake.spill_level_m + lake.head_allowance_m)) > LEVEL_TOLERANCE_M:
        raise ValueError("store top is not the spill level plus the declared head allowance")
    if abs(lake.outlets[0].crest_stage_m - lake.spill_level_m) > LEVEL_TOLERANCE_M:
        raise ValueError("outlet crest is not the measured spill level")
    if int(lake.saddle.get("exit_cells", 0)) == 0:
        raise ValueError("a certified basin must have a nonempty exit set")
    if float(lake.saddle.get("flood_level_constancy_m", 1.0)) > LEVEL_TOLERANCE_M:
        raise ValueError("a certified basin's flood level is not constant over it")
    if int(lake.saddle.get("exit_min_clearance_cells", -1)) < 0:
        raise ValueError("a certified basin must carry a measured exit clearance")
    if int(lake.catchment["unknown_cells"]) != 0:
        raise ValueError("a certified basin cannot hide unknown upstream cells")
    if int(lake.catchment["leaked_cells"]) != 0:
        raise ValueError("a certified basin's members must all be in its catchment")
    return True
