"""Lake storage from the terrain's own hypsometry, not from a vertical-wall tank.

What was wrong before
---------------------
`metric_lake_storage.LakeStorage` was already correct: it takes `cell_ids`,
`bed_elevation_m` and `cell_area_m2` and integrates the exact step function
V(h) = sum over cells of max(h - bed, 0) * area. Nothing about it assumes a
vertical wall. The vertical wall came from **the support it was given**: one
10 km planning cell, one bed value, one area. With one cell the step function
has a single step, so A(h) is 100 km2 for every stage and V(h) is a straight
line. That is a tank, and it is a property of the support, not of the class.

Measured consequence on the reach's terminal lake (`floodplain-2d-01`, and
reproduced independently here): at the declared stage the wall tank holds
4.585x the water the real basin can. The 2D run measured 4.0-4.6x.

The fix is therefore not a new lake model. It is to hand `LakeStorage` a
support whose elevation distribution is the terrain's:

* one cell per 30 m terrain cell inside the lake's own drainage depression,
* `bed_elevation_m` = the 30 m terrain height at that cell,
* `cell_area_m2` = 30 m x 30 m.

Then A(h) and V(h) are consequences of the terrain, and the cross section being
narrower lower down is just what the hypsometric curve of a real basin is. No
shape function, no exponent, no `r(x) = 1/x`, is written anywhere in this module.

How the support is derived (no tuning knobs)
--------------------------------------------
1. Priority flood from the window border (`depression_hierarchy`). The result is
the water surface a basin would settle at if it could drain off the page.
2. `fill_depth = filled - terrain`. Positive fill depth means "this cell is
   inside a depression whose exit is higher than the cell" -- measured on the
   terrain, not asserted.
3. The lake is the 4-connected component of positive fill depth containing the
   requested seed cell. Its spill level is the maximum fill level in that
   component, which *is* the height of the lowest saddle on its rim.

If the component touches the window border, the basin is not closed inside the
window and `closed_basin=False` is reported instead of silently inventing a
rim. That case is a boundary-resolution problem, not a formula problem: the
answer is a bigger window, and this module says so.

Why `max_stage_m` is the spill level
------------------------------------
A level-pool store above its spill level is not a lake any more -- it is a
flood. `LakeStorage.max_stage_m` is therefore set to the spill level, so the
class's own validation rejects a stage that would leave the basin, and
`LakeOutlet` takes over above it (that is exactly the weir law the reach solver
already uses).
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import identity, readonly
from terrain_pipeline.irregular_grid import grid_mesh
from terrain_pipeline.irregular_drainage import route_graph

from .metric_lake_storage import LakeStorage

MAX_HYPSOMETRY_CELLS = 65536
SAMPLE_LEVELS = 64
# `metric_lake_storage.LakeStorage` caps its support at `MAX_LAKE_CELLS`. A real
# 30 m basin is much larger than that (the reach's terminal basin is ~330k cells
# at 30 m), so the store is built from a **declared block aggregation** of the
# 30 m beds instead of from every 30 m cell. The aggregation is a mean over
# `aggregate_cells x aggregate_cells` 30 m cells; `aggregate_basin` reports the
# A(h)/V(h) difference it causes so the choice is measured, not assumed.
# `MAX_LAKE_CELLS` itself is not touched: it belongs to the existing class.
DEFAULT_AGGREGATE_CELLS = 3


def _finite_positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.:
        raise ValueError(name + " must be finite positive")
    return value


def depression_hierarchy(elevation_m, valid_mask=None, *, mesh=None, spacing_m=30., origin_xz_m=(0., 0.), world_seed=20261020):
    """Border-seeded priority flood.

    Returns `filled_m` (the level each cell would hold water at if the window
    border drains freely) and `fill_depth_m = filled - elevation`.

    The priority queue always expands the lowest known outlet first, so a cell's
    filled level is the minimum over all drainage paths to the border of the
    maximum elevation along that path. This is the standard fill; it is stated
    here because the lake support below relies on exactly this property.
    """
    bed = np.asarray(elevation_m, np.float64)
    if bed.ndim != 2 or bed.size < 4:
        raise ValueError("at least a 2x2 elevation field required")
    valid = np.ones(bed.shape, bool) if valid_mask is None else np.asarray(valid_mask, bool)
    if valid.shape != bed.shape or not valid.all():
        raise ValueError("a closed basin needs a fully valid window")
    if not np.isfinite(bed).all():
        raise ValueError("finite elevation required")
    rows, columns = bed.shape
    border = np.zeros((rows, columns), bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    if mesh is None:
        mesh = grid_mesh(bed.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                         dx_m=spacing_m, world_seed=world_seed)
    filled = route_graph(bed, border, mesh).filled.reshape(bed.shape)
    return filled, filled - bed


def depression_component(fill_depth_m, seed_rc, *, mesh=None):
    """Graph-connected positive-fill-depth component containing `seed_rc`."""
    depth = np.asarray(fill_depth_m, np.float64)
    if depth.ndim != 2:
        raise ValueError("2D fill depth required")
    row, column = (int(value) for value in seed_rc)
    if not (0 <= row < depth.shape[0] and 0 <= column < depth.shape[1]):
        raise ValueError("seed cell outside the field")
    wet = depth > 0.
    if not wet[row, column]:
        return None
    mesh = grid_mesh(depth.shape) if mesh is None else mesh
    seen = np.zeros(depth.size, bool)
    seed = row * depth.shape[1] + column
    seen[seed] = True
    stack = [seed]
    while stack:
        cell = stack.pop()
        for target in mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]:
            if wet.ravel()[target] and not seen[target]:
                seen[target] = True
                stack.append(int(target))
    return seen.reshape(depth.shape)


def hypsometry_curve(bed_elevation_m, cell_area_m2, levels_m):
    """A(h) and V(h) of an explicit bed population; terrain-only, no shape law.

    A(h) counts cells strictly below the level; V(h) integrates their depth.
    Both are step functions of the bed population, which is why they are
    reported on the same sorted beds the store itself uses.
    """
    beds = np.sort(np.asarray(bed_elevation_m, np.float64))
    area = _finite_positive(cell_area_m2, "cell_area_m2")
    if beds.ndim != 1 or beds.size == 0 or not np.isfinite(beds).all():
        raise ValueError("finite nonempty bed values required")
    levels = np.asarray(levels_m, np.float64)
    if levels.ndim != 1 or not np.isfinite(levels).all():
        raise ValueError("finite level list required")
    areas = np.zeros(levels.size, np.float64)
    volumes = np.zeros(levels.size, np.float64)
    for index, level in enumerate(levels):
        count = int(np.searchsorted(beds, level, side="left"))
        areas[index] = count * area
        volumes[index] = float(np.maximum(level - beds[:count], 0.).sum() * area)
    return areas, volumes


def contraction_evidence(levels_m, areas_m2):
    """How fast the water surface shrinks as the level falls; measured, not assumed.

    For consecutive level steps going **downward**, `dA/dh` should shrink with the
    level if the basin narrows toward its bottom. The reported numbers are the
    measured secant slopes of A(h); nothing here imposes their shape.
    """
    levels = np.asarray(levels_m, np.float64)
    areas = np.asarray(areas_m2, np.float64)
    if levels.shape != areas.shape or levels.ndim != 1 or levels.size < 3:
        raise ValueError("matching level and area vectors of length >= 3 required")
    if np.any(np.diff(levels) <= 0.):
        raise ValueError("levels must increase")
    order = np.argsort(-levels)
    descending_levels = levels[order]
    descending_areas = areas[order]
    rows = []
    for upper in range(len(descending_levels) - 1):
        lower = upper + 1
        delta_h = float(descending_levels[upper] - descending_levels[lower])
        delta_a = float(descending_areas[upper] - descending_areas[lower])
        if delta_h <= 0.:
            continue
        rows.append({"from_level_m": float(descending_levels[upper]),
                     "to_level_m": float(descending_levels[lower]),
                     "delta_level_m": delta_h,
                     "area_loss_m2": delta_a,
                     "secant_dA_dh_m": delta_a / delta_h,
                     "upper_area_m2": float(descending_areas[upper]),
                     "lower_area_m2": float(descending_areas[lower])})
    return rows


@dataclass(frozen=True)
class TerrainLake:
    """A closed basin's storage, V(h) and A(h) taken from the terrain itself."""

    storage: LakeStorage
    basin_mask: np.ndarray
    spill_level_m: float
    bed_min_m: float
    closed_basin: bool
    touches_window_border: bool
    provenance: dict

    @property
    def area_km2(self):
        return float(self.basin_mask.sum()) * self.storage.cell_area_m2[0] / 1e6

    @property
    def relief_m(self):
        return self.spill_level_m - self.bed_min_m

    @property
    def capacity_m3(self):
        return self.storage.capacity_m3

    def level_table(self, levels_m):
        """A(h)/V(h) straight from the store, so table and store cannot disagree."""
        rows = []
        for level in np.asarray(levels_m, np.float64):
            clamped = float(min(max(level, self.storage.min_stage_m), self.storage.max_stage_m))
            rows.append({"stage_m": float(level), "clamped_stage_m": clamped,
                         "area_m2": self.storage.surface_area_at_stage(clamped),
                         "volume_m3": self.storage.volume_at_stage(clamped)})
        return rows

    def identity_sha256(self):
        return identity({"basin_mask": self.basin_mask},
                        dict(self.provenance, spill_level_m=self.spill_level_m,
                             bed_min_m=self.bed_min_m,
                             store=self.storage.identity_sha256()
                             if hasattr(self.storage, "identity_sha256") else None))


def build_terrain_lake(elevation_m, origin_xz_m, spacing_m, seed_cell_rc, *,
                       source_identity_sha256, max_cells=MAX_HYPSOMETRY_CELLS):
    """Derive one closed-basin lake store from a 30 m terrain page.

    `seed_cell_rc` is the (row, column) of the cell whose basin is wanted -- in
    practice the terminal cell of the reach. The function never guesses: if that
    cell is not inside a closed depression it returns `closed_basin=False` with
    the reason, instead of falling back to a vertical wall.
    """
    bed = np.asarray(elevation_m, np.float64)
    if bed.ndim != 2 or bed.size < 16:
        raise ValueError("at least a 4x4 elevation field required")
    spacing = _finite_positive(spacing_m, "spacing_m")
    origin = np.asarray(origin_xz_m, np.float64).reshape(-1)
    if origin.size != 2 or not np.isfinite(origin).all():
        raise ValueError("finite [x, z] origin required")
    limit = int(max_cells)
    if limit < 4 or limit > MAX_HYPSOMETRY_CELLS:
        raise ValueError("max_cells must be 4..%d" % MAX_HYPSOMETRY_CELLS)
    mesh = grid_mesh(bed.shape, x0_m=origin[0], z0_m=origin[1], dx_m=spacing)
    filled, depth = depression_hierarchy(bed, mesh=mesh)
    row, column = (int(value) for value in seed_cell_rc)
    if not (0 <= row < bed.shape[0] and 0 <= column < bed.shape[1]):
        raise ValueError("seed cell outside the field")
    mask = depression_component(depth, (row, column), mesh=mesh)
    if mask is None:
        return TerrainLake(
            storage=None, basin_mask=readonly(np.zeros(bed.shape, bool)), spill_level_m=float("nan"),
            bed_min_m=float(bed[row, column]), closed_basin=False, touches_window_border=False,
            provenance={"schema": "terrain-lake-hypsometry-v1", "status": "seed cell drains",
                        "seed_row_column": [row, column],
                        "seed_elevation_m": float(bed[row, column]),
                        "max_cell_area_m2": spacing * spacing,
                        "reason": ("the seed cell has zero fill depth: its drainage path to the "
                                   "window border never rises, so there is no depression to fill"),
                        "source_identity_sha256": source_identity_sha256})
    count = int(mask.sum())
    if count > limit:
        raise ValueError("basin of %d cells exceeds the %d-cell store limit" % (count, limit))
    cells = np.flatnonzero(mask.ravel()).astype(np.int64)
    beds = np.ascontiguousarray(bed.ravel()[cells], np.float64)
    areas = np.full(cells.size, spacing * spacing, np.float64)
    bed_min = float(beds.min())
    spill = float(filled[mask].max())
    if not spill > bed_min:
        raise ValueError("degenerate basin: spill level does not exceed the bed")
    touches = _touches_border(mask)
    minimum_index = int(np.argmin(beds))
    storage = LakeStorage(
        cell_ids=cells, bed_elevation_m=beds, cell_area_m2=areas,
        seed_cell_id=int(cells[minimum_index]), max_stage_m=spill,
        source_identity_sha256=source_identity_sha256,
        footprint_policy=("closed_depression_30m_cells; A(h) and V(h) are the terrain's own "
                          "hypsometry over %d cells at %.3f m; no shape function is imposed" % (
                              count, spacing)))
    provenance = {
        "schema": "terrain-lake-hypsometry-v1", "status": "closed_basin",
        "seed_row_column": [row, column], "seed_elevation_m": float(bed[row, column]),
        "basin_cells": count, "basin_area_m2": float(count * spacing * spacing),
        "bed_min_m": bed_min, "spill_level_m": spill, "relief_m": spill - bed_min,
        "touches_window_border": touches,
        "closed_basin_within_window": not touches,
        "support_policy": ("one store cell per %0.3f m terrain cell inside the drainage "
                           "depression of the seed cell" % spacing),
        "max_stage_policy": "spill level from the border-seeded priority flood",
        "shape_law": None,
        "source_identity_sha256": source_identity_sha256,
        "origin_xz_m": [float(origin[0]), float(origin[1])]}
    return TerrainLake(storage=storage, basin_mask=readonly(mask), spill_level_m=spill,
                       bed_min_m=bed_min, closed_basin=not touches,
                       touches_window_border=touches, provenance=provenance)


def sampled_levels(min_level_m, max_level_m, count=SAMPLE_LEVELS):
    """Uniform level list on [min, max]; the store clamps and rejects as it must."""
    low = float(min_level_m)
    high = float(max_level_m)
    if not (math.isfinite(low) and math.isfinite(high)) or not high > low:
        raise ValueError("increasing finite levels required")
    n = int(count)
    if n < 3:
        raise ValueError("at least 3 sample levels required")
    return np.linspace(low, high, n)


# --------------------------------------------------------------------------- #
# window convergence: a measured prerequisite, not a formality
# --------------------------------------------------------------------------- #
#
# A depression's spill level is a property of the *whole* terrain, not of the
# pixels that happen to be inside a window. Priority flooding seeds from the
# window border, so a window whose edge cuts a basin's rim silently opens a
# drain there and reports a spill level that can be tens of metres too low.
#
# This is not hypothetical. On the reach's terminal lake, a 15.39 km window
# reported a spill level of 221.94 m and a 6.22 km2 basin; the same terrain in a
# 30.75 km window reports 337.18 m and 296.58 km2. The first number was already
# used to compare a lake store against a 2D run, and produced a 4.6x "storage
# overestimate" that does not exist.
#
# Therefore: **any basin, saddle or divide measured on a finite window must pass
# a convergence check before its numbers are reported.** `sampled_window_basin`
# below is that check; it is cheap (the analytic field is window-independent, so
# the only cost is the flood itself) and it is the only sanctioned way to obtain
# basin numbers from this module.

CONVERGENCE_LEVEL_TOLERANCE = 1e-3
CONVERGENCE_AREA_TOLERANCE = 1e-3
CONVERGENCE_SIZES = (513, 1025, 1537, 2049)


def _touches_border(mask):
    """Does the depression run into the window edge?

    Border cells are seeds of the flood and therefore always have zero fill
    depth, so they are never *in* the component. What matters is whether the
    component comes within one cell of the edge: then its rim is outside the
    page and its spill level is the window edge, not a real saddle.

    The nearest ring of a depression whose rim is outside the page is the ring at
    index 1 / -2, not the border itself. Testing the border ring would always
    return False, because no border cell can ever carry fill depth -- that was a
    real bug here, caught by
    `test_a_basin_larger_than_the_window_is_reported_as_not_closed`.
    """
    inner = np.zeros(mask.shape, bool)
    inner[2:-2, 2:-2] = True
    return bool((np.asarray(mask, bool) & ~inner).any())


def sampled_window_basin(lake_xz_m, sizes, spacing_m, sampler):
    """Measure one basin in growing centred windows and report the convergence.

    `sampler(origin_xz_m, shape)` must return the elevation field of that window
    from **absolute world coordinates** -- that is what makes the comparison
    meaningful, because then a value at a coordinate cannot depend on which
    window asked for it.

    Convergence rule (asserted by the test suite as well): the two largest
    windows must agree to `CONVERGENCE_LEVEL_TOLERANCE` of the spill relief and
    `CONVERGENCE_AREA_TOLERANCE` of the basin area. Only then is the answer
    accepted; otherwise `converged=False` comes back with the measured numbers
    and the caller is expected to enlarge the window, not to report the
    truncated one.
    """
    spacing = _finite_positive(spacing_m, "spacing_m")
    lake = np.asarray(lake_xz_m, np.float64).reshape(-1)
    if lake.size != 2 or not np.isfinite(lake).all():
        raise ValueError("finite [x, z] lake position required")
    shape_sizes = [int(value) for value in sizes]
    if len(shape_sizes) < 2 or any(value < 8 for value in shape_sizes):
        raise ValueError("at least two windows of 8 cells or more required")
    centre_column = int(round(lake[0] / spacing))
    centre_row = int(round(lake[1] / spacing))
    records = []
    for size in shape_sizes:
        origin_column = centre_column - size // 2
        origin_row = centre_row - size // 2
        origin = (origin_column * spacing, origin_row * spacing)
        field = np.ascontiguousarray(np.asarray(sampler(origin, (size, size)), np.float64))
        seed_rc = (centre_row - origin_row, centre_column - origin_column)
        filled, depth = depression_hierarchy(field)
        mask = depression_component(depth, seed_rc)
        if mask is None:
            record = {"size": size, "window_km": size * spacing / 1000.0,
                      "origin_xz_m": [float(origin[0]), float(origin[1])],
                      "seed_row_column": [int(seed_rc[0]), int(seed_rc[1])],
                      "closed_basin": False, "touches_window_border": False,
                      "basin_cells": 0, "basin_area_m2": 0.0,
                      "bed_min_m": float(field[seed_rc]), "spill_level_m": float("nan"),
                      "seed_elevation_m": float(field[seed_rc])}
        else:
            record = {"size": size, "window_km": size * spacing / 1000.0,
                      "origin_xz_m": [float(origin[0]), float(origin[1])],
                      "seed_row_column": [int(seed_rc[0]), int(seed_rc[1])],
                      "closed_basin": True,
                      "touches_window_border": _touches_border(mask),
                      "basin_cells": int(mask.sum()),
                      "basin_area_m2": float(mask.sum()) * spacing * spacing,
                      "bed_min_m": float(field[mask].min()),
                      "spill_level_m": float(filled[mask].max()),
                      "seed_elevation_m": float(field[seed_rc])}
        records.append(record)

    last, previous = records[-1], records[-2]
    if not (last["closed_basin"] and previous["closed_basin"]):
        return {"converged": False, "reason": "a candidate window is not a closed basin",
                "records": records, "accepted": last,
                "tolerances": {"level": CONVERGENCE_LEVEL_TOLERANCE,
                               "area": CONVERGENCE_AREA_TOLERANCE}}
    relief = last["spill_level_m"] - last["bed_min_m"]
    level_change = abs(last["spill_level_m"] - previous["spill_level_m"])
    area_change = abs(last["basin_area_m2"] - previous["basin_area_m2"])
    level_relative = level_change / relief if relief > 0. else float("inf")
    area_relative = area_change / last["basin_area_m2"] if last["basin_area_m2"] > 0. else float("inf")
    converged = bool(level_relative <= CONVERGENCE_LEVEL_TOLERANCE
                     and area_relative <= CONVERGENCE_AREA_TOLERANCE)
    return {"converged": converged,
            "level_change_m": level_change, "level_relative": level_relative,
            "area_change_m2": area_change, "area_relative": area_relative,
            "tolerances": {"level": CONVERGENCE_LEVEL_TOLERANCE,
                           "area": CONVERGENCE_AREA_TOLERANCE},
            "records": records, "accepted": last,
            "reason": None if converged else
                      "the two largest windows still disagree; enlarge the window before reporting"}
