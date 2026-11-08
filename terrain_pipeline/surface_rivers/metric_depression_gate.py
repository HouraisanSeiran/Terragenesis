"""Is this depression a lake, or a puddle a river must flow straight through?

Why this module exists (the P0 gap it closes)
---------------------------------------------
At 30 m a terrain has many small closed depressions. `metric_domain_closure`
builds its domains on the **raw**, unfilled face on purpose (see that module's
`_build_eligibility`: a filled face is window-relative and lets two anchorings
contradict each other), so every inland local minimum is a legitimate domain
endpoint. Measured on four 10 km planning tiles of seed 20261020: domain size
median **3 cells**, 24-26 % of domains a single cell, and **47-50 % of accepted
cells terminate at an inland minimum**.

At 30 m that is not a cosmetic detail. Measured here over one real 2049x2049 TD
page (`world_seed=20261020`, `.scratch/fine-terrain-01/td-window-00.npz`):

* **12 748** closed depressions;
* basin size median **1 cell**, **6 392** of them a **single cell**;
* `capacity_m3` (fill to the spill level) median **577 m3** -- one 30 m cell
  depressed by 0.64 m.

Without a gate every one of those is a place a river may "legitimately" stop,
and at 30 m a river then terminates in every pothole and never reaches the sea.
The fix is not to fill depressions blindly either: that would erase the real
basins. It is to **decide, per depression and on measured numbers, whether it is
a lake or a puddle**, and to route the puddles through.

What this module does NOT do: it does not route water, does not run a soil
bucket, and does not fill depressions itself. Those are existing modules and this
one calls them -- see "Reused, not rebuilt" below. What is new here is only the
**verdict**: a pure function plus the measurements that feed it.

What the gate decides, and how
------------------------------
A depression is an **acceptable domain endpoint** (a lake) only if it passes
**all** of:

  a) ``capacity_m3 >= alpha * inflow_m3``   -- the water arriving over the run
     cannot fill it, so a standing water body survives the storm;
  b) ``basin_area_m2 >= A_min_m2``           -- it is large enough to be a water
     body at all;
  c) the component has **stopped changing** as the measurement window grows --
     otherwise the window is measuring a different object than the one asked for;
  d) its rim clears the window border by at least ``contact_margin_cells``
     (`metric_cross_region.CONTACT_MARGIN_CELLS`, the measured 6-cell band).

About (d), and why `_touches_border` is not used: that helper's threshold is one
cell. On a real page a 513-cell window cut a 43.41 km2 basin down to 24.31 km2
and reported the spill level **19.16 m** too low while `_touches_border` returned
False (`.scratch/fine-terrain-40km/cross-region/report.md` §3b). The measured
clearance is the criterion; the weak boolean is kept in the cross-region report
only so the disagreement stays visible.

Failing (a)-(d) makes it a **run-through pool** (`VERDICT_PASS_THROUGH`): water
spills out at `spill_level_m` over the lowest saddle and the depression is not a
terminal. `reason_code` records **which** criterion failed.

Reused, not rebuilt
-------------------
Every hydrology quantity here comes from an existing module, named exactly:

* **Routing and the filled working surface**:
  `terrain_pipeline.surface_rivers.drainage.route(height, outlet_mask,
  spacing_blocks)`. Its `routing_height` is a border-seeded priority-flood fill
  and its `receiver`/`order` are a irregular single-receiver graph on that filled
  surface. **Semantics, stated so nobody over-reads it:** priority-flood irregular graph, not
  Saint-Venant; no backwater; no natural-outlet certification.
* **Cumulative surface water**: `drainage.accumulate(routing, runoff,
  spacing_blocks)`, which computes ``local = runoff * spacing^2`` per cell and
  sums it downstream along `routing.order`. Its `discharge` is the **cumulative
  volume that has arrived at a cell** -- which is the quantity criterion (a)
  needs. Its `residual = input_total - outlet_total` is reported, never hidden.
* **How much water the run produces per unit area**:
  `terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff`, the repository's
  own soil bucket, run on one unit cell and read back as a depth. `window_runoff_depth_m`
  does that and returns the depth it used; no rain is invented here.

The inflow comes from the UNFILLED catchment, and why
-----------------------------------------------------
An earlier draft of this module took "the water entering a depression" as
``max(discharge)`` over the depression's cells -- the volume crossing its own
saddle on the filled surface -- and I first justified rejecting it with a wrong
number. Both the number and the justification are corrected here, because the
route to a wrong answer is worth recording.

**The wrong argument (retracted).** I reported that the filled arrival was only
**7.8 %** of the real inflow. That 7.8 % divided by the **whole field's**
production, not by the pit's own catchment -- a pit on a slope never receives the
whole field. Measured with the right denominator, on a 61x61 ramp with one 3x3
pit and a 1 m run:

    whole field production      3 348 900 m3
    pit unfilled catchment        270 000 m3   <- the correct denominator
    pit filled arrival            260 100 m3
    filled / unfilled             0.9633      <- 3.7 % apart, not 92 %

So on a sloping pit the two readings nearly agree. That argument is dead.

**The real defect: flat ground.** On a four-pit flat plateau fixture the two
readings come apart completely. The plateau has 92 wet cells inside its pits, yet
the **one** lowest plateau cell outside them -- a raw local minimum, and therefore
a legitimate sink of the unfilled field -- takes **6191 of 6561** cells of
catchment, while the four pits together receive **370**. The reason is structural:
`drainage.route` breaks a flat plateau by **flood order (rank)**, so water on a
plateau runs across it to the border instead of gathering into the pits. A fill
answers "where does the water inside this hole go", never "do the hillside's
puddles drain into this hole".

**On the real page the filled reading is not low at all -- it is HIGH**, by up to
95x. Measured per basin on the 2049x2049 page (`filled / unfilled`): 27.9, 7.3,
1.21, **1.000**, 3.06, 1.34, 15.0, 26.1, **95.3**, 2.59, 11.8, 6.36. The reason is
that a fill sends water spilling over each saddle, so the filled arrival
**includes water that arrived from upstream depressions which had already
overflowed**. That is physically real, and it is not the quantity criterion (a)
wants: an upstream depression is judged separately, so counting its overflow again
double-counts the same water. Using the filled reading would systematically
demote downstream basins -- measured: label 6475 keeps with the unfilled reading
(ratio 1.51) and is rejected with the filled one (ratio 0.0159).

So the two readings measure different physical quantities, and neither is
"wrong":

* **unfilled catchment** = the production of the area that actually drains into
  this hole (adopted);
* **filled arrival** = everything crossing this hole's saddle, including upstream
  overflow (reported, not used).

Between them sits one honest limit: a depression whose catchment is mostly flat
plateau gets a small unfilled catchment, because on a plateau the raw strict irregular-graph
has almost no structure to gather with. That is a real property of the terrain at
30 m and it is why criterion (b) exists alongside (a).

On the choice, the report records that (2) and (3) can give **opposite verdicts**
on real basins, so this is a definition decision rather than a precision detail.

So the quantity criterion (a) uses is:

    inflow_m3 = contributing_cells * cell_area * produced_depth_m

where `contributing_cells` comes from `unfilled_catchment_flow`: the cells whose
**raw** strict irregular-graph chain ends on a local minimum inside the depression. That is
the catchment that actually delivers water to the hole. Measured on the page, it
is what separates a lake from a puddle: the 43.41 km2 basin draws on 95 859 cells
(4.572e7 m3 against a 1.200e9 m3 capacity, ratio 26.25) while a single-cell pit
draws on 75 cells (3.6e4 m3 against 4.6e3 m3, ratio 0.13).

The filled reading is still computed and still reported -- `catchment_comparison`
returns it beside the unfilled one, per depression, with the ratio between them --
so the size of the difference is a number on the record rather than a claim. On
the real page the two agree closely for most basins, and the report says so.

What the fill **is** used for, and why that is right: the depression's extent,
its `spill_level_m` and its `capacity_m3`. Those are properties of the hole and
its lowest saddle, and the border-seeded fill is exactly the measurement that
delivers them (it is asserted bit-identical to
`metric_lake_hypsometry.depression_hierarchy`,
``max|difference| = 0.0`` on the real page).

One more check that is worth stating: with every border cell an outlet, the water
ledger of the accumulate closes to **2.86e-5 m3 on 2.00e9 m3** (relative
1.4e-14). So the fill does **not** trap water. That is a separate fact from
whether the filled arrival is the right *quantity* -- conservation passing does
not make a metric correct, and this module keeps the two apart.

Why (c) is not the existing `converged` flag
-------------------------------------------
`metric_lake_hypsometry.sampled_window_basin` reports `converged=True` when its
two largest windows agree. On the real basin (label 1539, 10 619 cells) a window
family **(45, 61)** reports `converged=True` while **both** windows measure a
**90-cell** pocket inside the real basin, with a spill level **267.35 m** too low
(`.scratch/fine-terrain-40km/lake/pocket-growth.json`): the two windows agree
perfectly because they agree on the *wrong object*. Convergence of an answer to
itself is not evidence that the answer is about the basin.

What does distinguish them is whether **the component is still growing**:

    window    45    61   101   151    211    301    421    843
    cells     90    90   444  3328  10441  10619  10619  10619

So the gate asks exactly that, over an **accepted** window family:
``cells(largest accepted) == cells(second largest accepted)``.

At **(45, 61)** that fails for a reason the code reports explicitly: 90 vs 90 *is*
stable, but neither window is accepted (the pocket's rim lies outside the page),
so there is no accepted pair at all. The verdict is `REASON_STILL_GROWING` with
``convergence_gate = "no_accepted_window"``. A family of truncated windows can
therefore never certify a basin. At **(301, 421)** it passes: 10 619 == 10 619,
``convergence_gate = "cells_stable"``.

Stated rather than hidden: **a depression smaller than the smallest window also
stops changing**, because the window already contains it. So (c) alone is not a
lake test -- a single-cell pothole is "stable" from window 45 up. (c) exists to
stop the gate from certifying a bisected basin; (a) and (b) are what certify
lakes. In this module (c) and (d) can only ever **downgrade**.

Alpha and A_min: declared, with the reasoning, and **not calibrated**
--------------------------------------------------------------------
Both are fields of `DepressionGateConfig` with the defaults below, and every
verdict record carries the values actually used, so a reader can re-derive each
decision instead of trusting this text.

* ``alpha = 1.0`` (dimensionless). The criterion says "the water arriving over
  the run can fill it", and `alpha = 1` is the literal statement of that
  sentence: capacity equals arrival. It is also the only value the page supports
  without eating real lakes, which is measured: the ratio of the 131 basins the
  gate keeps runs from **1.02** up to **76.7**, so `alpha = 2` already rejects
  several of them, while `alpha < 1` changes nothing because the smallest kept
  ratio is 1.02. The 43.41 km2 basin has ratio **26.25**, so any alpha up to 26
  keeps it. In short: the gate is flat on `alpha in [0.5, 1.0]`, starts
  misjudging real basins above 1, and only threatens the biggest basin above 26.
  (`alpha = 1` is therefore not a tuned value -- it is the sentence, and the
  measurement says the sentence happens to be the safe edge.)
* ``A_min_m2 = 10 000`` (11.1 cells of 30 m). Two independent readings agree:
  1. **Hypsometric.** The number of **distinct bed levels** inside a depression
     separates lids from hollows cleanly. Measured medians: single-cell **1.0**,
     2-3 cells **2.0**, then 5, 8, 14, 28, 70, 167, 681 for the size decades. A
     depression with fewer than ~3 distinct levels is not a basin. At
     `A_min = 2 500 m2` (2.8 cells) survivors already have a median of 5 distinct
     levels and **none** have fewer than 3; at 900 m2 two thirds still do. So
     `A_min` must sit above the 2-3 cell class.
  2. **The object named in the acceptance case.** The lake-basin acceptance names
     its **90-cell** truncated pocket as the canonical thing that must not be read
     as a lake. ``90 cells = 81 000 m2``, so `A_min` must be at most that for the
     rule to catch it by size alone. 10 000 m2 keeps a **9x** margin below it and
     sits **11x** above a single 30 m cell.
  Sensitivity, reported not hidden: of the 12 748 depressions on the page, the
  766 that fail criterion (b) are all below 10 000 m2, and raising `A_min` to
  20 000 / 50 000 / 81 000 m2 would move more of the surviving small basins out.

Both numbers are **uncalibrated**. Nothing here is fitted to the page.

The test is well posed without knowing the run length because both sides scale
with it. With ``inflow = A_catch * d`` the inequality
``capacity >= alpha * A_catch * d`` divides through to

    capacity / A_catch  >=  alpha * d      ("absorbable depth of the depression")

which depends on the run only through the declared storm's depth. A longer,
wetter run makes more depressions pass through -- the physically right direction.

Spill: work surface only, original bed untouched
-----------------------------------------------
`spill_work_surface` raises the **work** surface of a pass-through pool, cell by
cell, to that pool's own `spill_level_m`, and returns a **new** array. The
original field is never written to. That is the same discipline as
`metric_td_generated_rivers.spill_candidate`'s ``work_surface_only=True`` (its
`pyflwdir.fill_depressions` result is a working candidate, never the published
bed), and the metadata states it so no consumer can mistake the surface for
terrain.

The result is **stricter than a global fill**: only depressions the gate refused
are raised. A border-seeded fill would raise every wet component; this raises the
refused ones and leaves every lake's bed exactly as the terrain has it, and
reports both cell counts.

Two ledgers, never one on top of the other
------------------------------------------
`DepressionGateReport` carries both, filled by the same run:

* ``closed_basin_by_hypsometry`` -- pure terrain closure: the depression
  component exists and its rim clears the untrusted band. No water, no size, no
  growth test. This is the old answer.
* ``is_domain_terminal`` -- the same depressions after the gate.

Both are reported as counts, cell totals and size distributions, so
"before vs after" is a measurement rather than a claim, and neither value is ever
written over the other. Each depression also carries its full auditable record
``{basin_cells, capacity_m3, inflow_m3, ratio, area_m2, spill_level_m, verdict,
reason_code}`` plus provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff

from terrain_pipeline.drainage import accumulate as accumulate
from terrain_pipeline.drainage import route as route
from .metric_cross_region import CONTACT_MARGIN_CELLS

SCHEMA = "terragenesis-depression-gate-v1"

VERDICT_LAKE = "lake"
VERDICT_PASS_THROUGH = "pass_through"

# Stable reason codes. `judge_depression` applies the checks in a fixed order, so
# a depression failing several is always explained by the same one and two runs
# cannot disagree about why.
REASON_LAKE = "lake_capacity_area_and_growth"
REASON_NO_COMPONENT = "no_depression_at_seed"
REASON_TRUNCATED = "rim_inside_untrusted_band"
REASON_CAPACITY = "inflow_fills_capacity"
REASON_AREA = "basin_too_small"
REASON_STILL_GROWING = "component_still_growing"
REASON_CODES = (REASON_LAKE, REASON_NO_COMPONENT, REASON_TRUNCATED, REASON_CAPACITY,
                REASON_AREA, REASON_STILL_GROWING)

# How criterion (c) was evaluated. Kept as its own field so a reader can tell a
# real two-window growth check from the weaker page-interior statement.
GROWTH_CELLS_STABLE = "cells_stable"
GROWTH_STILL_GROWING = "cells_still_growing"
GROWTH_NO_ACCEPTED_WINDOW = "no_accepted_window"
GROWTH_SINGLE_WINDOW = "single_window_only"
GROWTH_COMPONENT_ABSENT = "component_absent"
GROWTH_PAGE_INTERIOR = "page_interior_no_larger_window_available"

# Which quantity `inflow_m3` is. Records carry this so the reading is auditable
# and cannot be swapped for another without the record changing.
INFLOW_UNFILLED_CATCHMENT = "unfilled_catchment_production"
INFLOW_FILLED_CATCHMENT = "filled_catchment_arrival"
INFLOW_OWN_PRODUCTION = "own_production_only"

DEFAULT_ALPHA = 1.0
DEFAULT_MIN_AREA_M2 = 10_000.0
MAX_GATE_CELLS = 16_777_216


@dataclass(frozen=True)
class DepressionGateConfig:
    """The declared, uncalibrated thresholds of the spill gate.

    Defaults exist so callers can be terse, but every verdict record carries the
    values actually used. See the module docstring for the measurement behind
    each one; neither number was fitted.
    """

    alpha: float = DEFAULT_ALPHA
    min_area_m2: float = DEFAULT_MIN_AREA_M2
    contact_margin_cells: int = CONTACT_MARGIN_CELLS
    require_growth_convergence: bool = True

    def __post_init__(self):
        for name in ("alpha", "min_area_m2"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                    value, (int, float, np.integer, np.floating)):
                raise ValueError(name + " must be numeric")
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(name + " must be finite positive")
        if type(self.contact_margin_cells) is not int or self.contact_margin_cells < 0:
            raise ValueError("non-negative integer contact_margin_cells required")
        if not isinstance(self.require_growth_convergence, (bool, np.bool_)):
            raise ValueError("require_growth_convergence must be a boolean")


# --------------------------------------------------------------------------- #
# the run: what a declared storm produces, as a depth (existing bucket)
# --------------------------------------------------------------------------- #
def window_runoff_depth_m(rain_mm_h, *, dt_s=3600.0, intervals=12, parameters=None):
    """Produced water **depth** over a declared run, from the repository's bucket.

    `rain_mm_h` is a scalar or a per-interval sequence (mm/h) -- the two forms
    `rainfall_runoff.simulate_rainfall_runoff` accepts. The bucket runs over one
    square metre, so ``outflow_volume_m3 / 1 m2`` is a depth in metres. This
    module assumes no duration of its own: the caller's storm is the run.
    """
    parameters = parameters or RunoffParameters()
    if not isinstance(parameters, RunoffParameters):
        raise ValueError("RunoffParameters required")
    if not math.isfinite(float(dt_s)) or float(dt_s) <= 0.0:
        raise ValueError("positive finite dt_s required")
    if type(intervals) is not int or intervals < 1:
        raise ValueError("positive integer intervals required")
    array = np.asarray(rain_mm_h, np.float64)
    if array.ndim == 0:
        array = np.full(int(intervals), float(array))
    if array.ndim != 1 or array.size != int(intervals):
        raise ValueError("rain_mm_h must be a scalar or a sequence of `intervals` values")
    if not np.isfinite(array).all() or np.any(array < 0.0):
        raise ValueError("finite nonnegative rain required")
    runoff = simulate_rainfall_runoff(array.reshape(int(intervals), 1).copy(), np.ones(1),
                                      dt_s=float(dt_s),
                                      source_id="%s:runoff_depth" % SCHEMA,
                                      parameters=parameters)
    produced = float(np.sum(runoff["outflow_volume_m3"], dtype=np.float64))
    if not math.isfinite(produced) or produced < 0.0:
        raise ValueError("runoff produced a nonfinite depth")
    return produced


# --------------------------------------------------------------------------- #
# routing and cumulative water: existing `drainage` module, called not copied
# --------------------------------------------------------------------------- #
def border_outlet_mask(shape):
    """Every border cell is an outlet: a window drains off its own edge.

    This is the same boundary condition `metric_lake_hypsometry.depression_hierarchy`
    and `metric_cross_region._flood` use, so the fill this module routes on and
    the fill the lake support measures are the same fill. It is declared, not
    inferred: no interior cell is ever an outlet here, and no outlet is omitted.
    """
    rows, columns = (int(value) for value in shape)
    if rows < 3 or columns < 3:
        raise ValueError("at least a 3x3 field is required to have an interior")
    outlets = np.zeros((rows, columns), bool)
    outlets[[0, -1], :] = True
    outlets[:, [0, -1]] = True
    return outlets


def route_and_accumulate(elevation_m, spacing_m, produced_depth_m, *, mesh=None,
                         origin_xz_m=(0., 0.), world_seed=20261020):
    """One `drainage.route` + one `drainage.accumulate`, plus their diagnostics.

    `elevation_m` is the **original** bed. It is not modified: `route` works on its
    own copy, and this function returns that working fill separately so the caller
    can see exactly which surface the routing happened on.

    Returns a dict with `routing`, `accumulation`, `filled_m`
    (= `routing.routing_height`), `receiver_flat`, `order`, `discharge_m3` and the
    load-bearing diagnostic `residual_m3` (= `accumulation.residual`). The residual
    is reported, not absorbed: with every border cell an outlet it is a floating
    point quantity and its measured size is quoted in the acceptance report.
    """
    bed = np.asarray(elevation_m, np.float64)
    if bed.ndim != 2:
        raise ValueError("2D elevation required")
    if not np.isfinite(bed).all():
        raise ValueError("finite elevation required")
    spacing = float(spacing_m)
    if not math.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("positive finite spacing_m required")
    depth = float(produced_depth_m)
    if not math.isfinite(depth) or depth < 0.0:
        raise ValueError("finite nonnegative produced_depth_m required")
    outlets = border_outlet_mask(bed.shape)
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import route_graph as route_graph
    from .contracts import RoutingResult
    mesh = grid_mesh(bed.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1], dx_m=spacing,
                     world_seed=world_seed) if mesh is None else mesh
    graph = route_graph(bed, outlets, mesh)
    routing = RoutingResult(graph.receiver, graph.order, graph.filled, outlets, spacing)
    # Uniform production: every valid cell produces `depth` metres over the run.
    # The soil bucket's spatial variation is the caller's business (it lives in
    # `rainfall_runoff` and its parameters), and this module must not invent it.
    runoff = np.full(bed.shape, depth, np.float64)
    accumulation = accumulate(routing, runoff, spacing)
    return {
        "routing": routing,
        "mesh": mesh,
        "accumulation": accumulation,
        "filled_m": np.asarray(routing.routing_height, np.float64),
        "receiver_flat": np.asarray(routing.receiver, np.int64),
        "order": np.asarray(routing.order, np.int64),
        "discharge_m3": np.asarray(accumulation.discharge, np.float64),
        "input_total_m3": float(accumulation.input_total),
        "outlet_total_m3": float(accumulation.outlet_total),
        "residual_m3": float(accumulation.residual),
        "runoff_depth_m": depth,
        "routing_model": "surface_rivers.drainage.route (priority-flood irregular graph, no backwater, "
                         "not Saint-Venant)",
        "accumulation_model": "surface_rivers.drainage.accumulate (conservative, "
                              "local = runoff * spacing^2 summed downstream)",
    }


# --------------------------------------------------------------------------- #
# depression labelling (on the fill these functions already produced)
# --------------------------------------------------------------------------- #
def label_depressions(wet_mask, *, mesh=None):
    """Connected positive-fill components on the routing graph, densely labelled."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    wet = np.asarray(wet_mask, bool)
    if wet.ndim != 2:
        raise ValueError("2D wet mask required")
    mesh = grid_mesh(wet.shape) if mesh is None else mesh
    labels = np.full(wet.size, -1, np.int64)
    count = 0
    for start in np.flatnonzero(wet):
        if labels[start] >= 0:
            continue
        labels[start] = count
        pending = [int(start)]
        while pending:
            cell = pending.pop()
            for edge in range(mesh.indptr[cell], mesh.indptr[cell + 1]):
                target = int(mesh.indices[edge])
                if wet.ravel()[target] and labels[target] < 0:
                    labels[target] = count
                    pending.append(target)
        count += 1
    return labels.reshape(wet.shape), count

def unfilled_catchment_flow(elevation_m, *, mesh=None, spacing_m=30.,
                            origin_xz_m=(0., 0.), world_seed=20261020):
    """Raw strict irregular catchment counts; no fill and no plateau connection."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import strict_receivers as strict_receivers
    bed = np.asarray(elevation_m, np.float64)
    if bed.ndim != 2 or not bed.size or not np.isfinite(bed).all():
        raise ValueError("finite nonempty 2D elevation required")
    mesh = grid_mesh(bed.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                     dx_m=spacing_m, world_seed=world_seed) if mesh is None else mesh
    receiver, _, _ = strict_receivers(bed, mesh)
    accumulator = np.ones(bed.size, np.float64)
    for cell in np.argsort(-bed.ravel(), kind="stable"):
        downstream = receiver[cell]
        if downstream >= 0:
            accumulator[downstream] += accumulator[cell]
    return accumulator, receiver.reshape(bed.shape), receiver < 0

def rim_clearance_cells(mask, shape):
    """Distance in cells from a component to the nearest border of its window."""
    rows, columns = (int(value) for value in shape)
    rr, cc = np.nonzero(np.asarray(mask, bool))
    if rr.size == 0:
        raise ValueError("nonempty component mask required")
    return int(min(rr.min(), cc.min(), rows - 1 - rr.max(), columns - 1 - cc.max()))


def growth_verdict(window_records):
    """Criterion (c): has the component stopped changing as the window grew?

    `window_records` is a window family as `metric_cross_region.window_family`
    produces it: one record per window carrying at least `size`, `basin_cells` and
    `suspect_window_truncation`. "Accepted" is the same rule as criterion (d),
    applied per window -- so a family of truncated windows can certify nothing.

    Returns ``(converged, gate)`` with `gate` one of the ``GROWTH_*`` constants,
    so the reason stays auditable when the answer is "no".
    """
    records = [record for record in window_records if record is not None]
    if not records:
        return False, GROWTH_COMPONENT_ABSENT
    ordered = sorted(records, key=lambda record: int(record["size"]))
    accepted = [record for record in ordered
                if not record.get("suspect_window_truncation", False)
                and int(record.get("basin_cells", 0)) > 0]
    if not accepted:
        return False, GROWTH_NO_ACCEPTED_WINDOW
    if len(accepted) == 1:
        return False, GROWTH_SINGLE_WINDOW
    last, previous = accepted[-1], accepted[-2]
    stable = int(last["basin_cells"]) == int(previous["basin_cells"])
    return bool(stable), (GROWTH_CELLS_STABLE if stable else GROWTH_STILL_GROWING)


@dataclass(frozen=True)
class DepressionVerdict:
    """One depression's measured case, with the verdict it produced."""

    basin_cells: int
    capacity_m3: float
    inflow_m3: float
    ratio: float
    area_m2: float
    spill_level_m: float
    verdict: str
    reason_code: str
    label: int = -1
    inflow_quantity: str = INFLOW_UNFILLED_CATCHMENT
    contributing_cells: float = float("nan")
    contributing_area_m2: float = float("nan")
    filled_arrival_m3: float = float("nan")
    own_production_m3: float = float("nan")
    bed_min_m: float = float("nan")
    relief_m: float = float("nan")
    rim_clearance_cells: int = -1
    convergence_gate: str = ""
    alpha: float = DEFAULT_ALPHA
    min_area_m2: float = DEFAULT_MIN_AREA_M2
    contact_margin_cells: int = CONTACT_MARGIN_CELLS

    @property
    def is_domain_terminal(self):
        return self.verdict == VERDICT_LAKE

    @property
    def closed_basin_by_hypsometry(self):
        """The pure-terrain verdict, kept beside the gate's answer, never merged.

        **Pure geometry, no water, no size, no growth test, no clearance rule.**
        A depression is closed on the terrain when its component exists. Whether
        the measurement *window* was big enough is a property of the measurement,
        not of the terrain, so truncation is reported in its own column instead of
        being smuggled in here -- see `truncated_not_judged` on the report and
        `REASON_TRUNCATED` on the row. Keeping the two apart is what lets a
        reader see "the terrain has 12 748 closed hollows, of which 208 cannot be
        judged on this page and 131 survive the gate".
        """
        return self.basin_cells > 0 and self.reason_code != REASON_NO_COMPONENT

    @property
    def truncated_not_judged(self):
        """The rim is inside the untrusted band: a measurement defect, not a fact."""
        return self.reason_code == REASON_TRUNCATED

    def as_record(self):
        """The auditable record: every field is a measurement or a declared value.

        `ratio` is `inf` when a depression has no inflow at all, and `json` refuses
        infinities (`allow_nan=False` in `mountain_source_adapter.identity`), so the
        record spells the infinite case explicitly instead of emitting a value the
        serialiser rejects. The number itself stays `inf` on the dataclass.
        """
        ratio = float(self.ratio)
        return {
            "label": int(self.label),
            "basin_cells": int(self.basin_cells),
            "capacity_m3": float(self.capacity_m3),
            "inflow_m3": float(self.inflow_m3),
            "inflow_quantity": self.inflow_quantity,
            "ratio": ratio if math.isfinite(ratio) else None,
            "ratio_infinite": not math.isfinite(ratio),
            "area_m2": float(self.area_m2),
            "spill_level_m": float(self.spill_level_m),
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "closed_basin_by_hypsometry": bool(self.closed_basin_by_hypsometry),
            "truncated_not_judged": bool(self.truncated_not_judged),
            "is_domain_terminal": bool(self.is_domain_terminal),
            "contributing_cells": float(self.contributing_cells),
            "contributing_area_m2": float(self.contributing_area_m2),
            "filled_arrival_m3": float(self.filled_arrival_m3),
            "own_production_m3": float(self.own_production_m3),
            "bed_min_m": float(self.bed_min_m),
            "relief_m": float(self.relief_m),
            "rim_clearance_cells": int(self.rim_clearance_cells),
            "contact_margin_cells": int(self.contact_margin_cells),
            "convergence_gate": self.convergence_gate,
            "alpha": float(self.alpha),
            "min_area_m2": float(self.min_area_m2),
        }


def judge_depression(*, basin_cells, capacity_m3, inflow_m3, area_m2, spill_level_m,
                     config=None, label=-1, input_quantity=INFLOW_UNFILLED_CATCHMENT,
                     contributing_cells=float("nan"),
                     contributing_area_m2=float("nan"),
                     filled_arrival_m3=float("nan"),
                     own_production_m3=float("nan"), bed_min_m=float("nan"),
                     rim_clearance_cells=0, growth_converged=True,
                     convergence_gate=GROWTH_PAGE_INTERIOR, component_absent=False):
    """Apply criteria (a)-(d) to one already-measured depression.

    Pure and total: no routing, no field, no I/O. This is the part that has to be
    wrong-proof, so it is separated from the measurement feeding it and tested
    directly against the real page's own numbers.

    The check order is fixed and matters for `reason_code`: absent component ->
    (d) truncation -> (a) capacity -> (b) area -> (c) growth. Truncation comes
    before capacity and area on purpose: a cut component's capacity and area are
    both artefacts, so reporting "too small" for one would blame the terrain for a
    bug in the window.
    """
    config = config or DepressionGateConfig()
    cells = int(basin_cells)
    if cells < 0:
        raise ValueError("basin_cells must be nonnegative")
    for name, value in (("capacity_m3", capacity_m3), ("inflow_m3", inflow_m3),
                        ("area_m2", area_m2), ("spill_level_m", spill_level_m),
                        ("bed_min_m", bed_min_m)):
        if not math.isfinite(float(value)):
            raise ValueError(name + " must be finite")
    capacity = float(capacity_m3)
    inflow = float(inflow_m3)
    area = float(area_m2)
    if capacity < 0.0 or inflow < 0.0 or area < 0.0:
        raise ValueError("capacity, inflow and area must be nonnegative")
    ratio = capacity / inflow if inflow > 0.0 else float("inf")
    truncated = int(rim_clearance_cells) < int(config.contact_margin_cells)
    if bool(component_absent) or cells == 0:
        verdict, reason = VERDICT_PASS_THROUGH, REASON_NO_COMPONENT
    elif truncated:
        verdict, reason = VERDICT_PASS_THROUGH, REASON_TRUNCATED
    elif ratio < config.alpha:
        verdict, reason = VERDICT_PASS_THROUGH, REASON_CAPACITY
    elif area < config.min_area_m2:
        verdict, reason = VERDICT_PASS_THROUGH, REASON_AREA
    elif config.require_growth_convergence and not growth_converged:
        verdict, reason = VERDICT_PASS_THROUGH, REASON_STILL_GROWING
    else:
        verdict, reason = VERDICT_LAKE, REASON_LAKE
    return DepressionVerdict(
        basin_cells=cells, capacity_m3=capacity, inflow_m3=inflow, ratio=ratio,
        area_m2=area, spill_level_m=float(spill_level_m), verdict=verdict,
        reason_code=reason, label=int(label), inflow_quantity=str(input_quantity),
        contributing_cells=float(contributing_cells),
        contributing_area_m2=float(contributing_area_m2),
        filled_arrival_m3=float(filled_arrival_m3),
        own_production_m3=float(own_production_m3), bed_min_m=float(bed_min_m),
        relief_m=float(spill_level_m) - float(bed_min_m),
        rim_clearance_cells=int(rim_clearance_cells),
        convergence_gate=str(convergence_gate),
        alpha=float(config.alpha), min_area_m2=float(config.min_area_m2),
        contact_margin_cells=int(config.contact_margin_cells))


def measure_depressions(elevation_m, *, spacing_m, produced_depth_m, config=None,
                        mesh=None, origin_xz_m=(0., 0.), world_seed=20261020):
    """Measure and judge **every** closed depression on one field.

    One `drainage.route` + one `drainage.accumulate` supply the filled working
    surface, the irregular graph edges, the components and the cumulative water; nothing
    is re-derived here.

    `inflow_m3` is quantity (2) of the module docstring: ``contributing_cells *
    cell_area * depth`` with `contributing_cells` taken from the **unfilled**
    strict irregular-graph catchment (see `unfilled_catchment_flow`). The filled arrival is
    computed too and reported under `filled_arrival_m3`, because it is the number
    an earlier draft used and its size is worth keeping on the record; it decides
    nothing.

    Criterion (c) is evaluated at **page** strength here: the largest window is
    the page itself, so a component clearing the untrusted band by
    `contact_margin_cells` cannot grow within this source. That is weaker than a
    real two-window growth check and is labelled ``GROWTH_PAGE_INTERIOR`` in every
    record so it is never mistaken for one. Use `judge_seed_in_windows` when a
    window family over several pages is available.

    Returns ``(verdicts, context)``; `verdicts` is ordered by decreasing basin
    area, so record 0 is the largest depression on the field.
    """
    config = config or DepressionGateConfig()
    bed = np.asarray(elevation_m, np.float64)
    if bed.ndim != 2 or bed.size < 16:
        raise ValueError("at least a 4x4 elevation field required")
    if not np.isfinite(bed).all():
        raise ValueError("finite elevation required")
    if bed.size > MAX_GATE_CELLS:
        raise ValueError("field of %d cells exceeds the declared gate limit" % bed.size)
    spacing = float(spacing_m)
    depth = float(produced_depth_m)
    if not math.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("positive finite spacing_m required")
    if not math.isfinite(depth) or depth < 0.0:
        raise ValueError("finite nonnegative produced_depth_m required")
    cell_area = spacing * spacing

    routed = route_and_accumulate(bed, spacing, depth, mesh=mesh,
        origin_xz_m=origin_xz_m, world_seed=world_seed)
    filled = routed["filled_m"]
    discharge = routed["discharge_m3"]
    wet = (filled - bed) > 0.0
    labels, count = label_depressions(wet, mesh=routed["mesh"])
    unfilled_accumulator, raw_receiver, raw_is_minimum = unfilled_catchment_flow(bed, mesh=routed["mesh"])

    flat_labels = labels.reshape(-1)
    flat_bed = bed.reshape(-1)
    flat_filled = filled.reshape(-1)
    flat_discharge = discharge.reshape(-1)
    flat_unfilled = unfilled_accumulator
    # Labels are DENSE and 0-based (0 .. count-1), so every per-label array is
    # exactly `count` long. Building them `count + 1` left a trailing slot that
    # belonged to no depression -- it made `basin_cells_by_label` one entry longer
    # than the verdict list, which a four-pit fixture test caught (4 components,
    # 5 sizes). The `-1` (outside) case is handled by masking, never by reserving
    # a slot.
    capacity = np.zeros(count, np.float64)
    spill = np.full(count, np.nan, np.float64)
    minimum = np.full(count, np.nan, np.float64)
    sizes = np.zeros(count, np.int64)
    clearance = np.full(count, -1, np.int64)
    arrival = np.zeros(count, np.float64)
    own = np.zeros(count, np.float64)
    catchment = np.zeros(count, np.float64)
    rows, columns = bed.shape

    inside = np.flatnonzero(flat_labels >= 0)
    groups = []
    if inside.size:
        # The sort is load-bearing and its absence was a real bug: `flatnonzero`
        # returns flat indices in ascending order, and label values are NOT
        # monotone over that order, so `np.diff` on the unsorted run invents
        # boundaries wherever the labelling happened to zig-zag. Measured on a
        # 3x3 field with 4 components: 7 groups instead of 4, one real component
        # split into 3 shards, and `sizes[label]` overwritten by the last shard --
        # which is what produced "verdict and context disagree about the
        # depression's size" on the real page. Every capacity, inflow and area in
        # the first acceptance run was a fragment's value, so that run is void.
        ordered = inside[np.argsort(flat_labels[inside], kind="stable")]
        run = flat_labels[ordered]
        steps = np.diff(run)
        if steps.size and steps.min() < 0:
            # The direct signature of a shredded grouping, caught before any count
            # is compared: on a sorted run the labels cannot go backwards.
            raise AssertionError("label run is not monotone: min(diff) = %d"
                                 % int(steps.min()))
        groups = np.split(ordered, np.flatnonzero(steps) + 1)
        if len(groups) != count:
            raise AssertionError("group count %d disagrees with the %d labels"
                                 % (len(groups), count))
        if len(np.unique(run)) != count:
            raise AssertionError("a label is missing from the grouped cells")
        if sum(len(group) for group in groups) != inside.size:
            raise AssertionError("grouping lost cells")
    for cells in groups:
        label = int(flat_labels[cells[0]])
        beds = flat_bed[cells]
        levels = flat_filled[cells]
        top = float(levels.max())
        spill[label] = top
        minimum[label] = float(beds.min())
        capacity[label] = float(np.sum(top - beds) * cell_area)
        sizes[label] = int(cells.size)
        # reported only: the filled arrival an earlier draft wrongly used
        arrival[label] = float(flat_discharge[cells].max())
        # own production, reported only so the difference from the catchment is visible
        own[label] = float(cells.size * cell_area * depth)
        rr = cells // columns
        cc = cells % columns
        clearance[label] = int(min(rr.min(), cc.min(), rows - 1 - rr.max(),
                                   columns - 1 - cc.max()))

    # (2) the quantity criterion (a) uses: cells whose RAW chain ends on a local
    # minimum inside the depression. Raw local minima are the cells with no
    # strictly-lower neighbour; each contributes its own accumulated cell count.
    minimum_label = np.where(raw_is_minimum, flat_labels, np.int64(-1))
    has = np.flatnonzero(minimum_label >= 0)
    if has.size:
        np.add.at(catchment, minimum_label[has], flat_unfilled[has])

    verdicts = []
    for cells in groups:
        label = int(flat_labels[cells[0]])
        verdicts.append(judge_depression(
            basin_cells=int(cells.size), capacity_m3=float(capacity[label]),
            inflow_m3=float(catchment[label]) * cell_area * depth,
            area_m2=float(cells.size) * cell_area, spill_level_m=float(spill[label]),
            config=config, label=label, input_quantity=INFLOW_UNFILLED_CATCHMENT,
            contributing_cells=float(catchment[label]),
            contributing_area_m2=float(catchment[label]) * cell_area,
            filled_arrival_m3=float(arrival[label]),
            own_production_m3=float(own[label]),
            bed_min_m=float(minimum[label]),
            rim_clearance_cells=int(clearance[label]),
            growth_converged=True, convergence_gate=GROWTH_PAGE_INTERIOR))
    verdicts.sort(key=lambda record: (-record.basin_cells, -record.capacity_m3,
                                      record.spill_level_m, record.label))
    context = {
        "labels": labels, "filled_m": filled, "wet_mask": wet,
        "receiver_flat": np.asarray(routed["receiver_flat"], np.int64),
        "order": np.asarray(routed["order"], np.int64),
        "discharge_m3": discharge,
        "unfilled_catchment_cells": unfilled_accumulator,
        "cell_area_m2": cell_area, "depression_count": count,
        "capacity_m3_by_label": capacity, "spill_level_m_by_label": spill,
        "bed_min_m_by_label": minimum, "basin_cells_by_label": sizes,
        "inflow_m3_by_label": arrival, "own_production_m3_by_label": own,
        "unfilled_catchment_cells_by_label": catchment,
        "produced_depth_m": depth,
        "input_total_m3": routed["input_total_m3"],
        "outlet_total_m3": routed["outlet_total_m3"],
        "residual_m3": routed["residual_m3"],
        "routing_model": routed["routing_model"],
        "accumulation_model": routed["accumulation_model"],
        "config": config,
    }
    return verdicts, context


def catchment_comparison(verdicts, context):
    """The two readings of "water entering this depression", side by side.

    Returns one row per depression with the quantity the gate uses
    (`inflow_m3`, from the unfilled catchment), the filled arrival an earlier
    draft wrongly used (`filled_arrival_m3`), own production, and the ratio
    between the two readings. The ratio is the measurement the objection asked
    for: it says how much the fill distorts the number, instead of claiming it
    does not.
    """
    rows = []
    for verdict in verdicts:
        filled = float(verdict.filled_arrival_m3)
        used = float(verdict.inflow_m3)
        rows.append({
            "label": int(verdict.label),
            "basin_cells": int(verdict.basin_cells),
            "inflow_m3_used": used,
            "filled_arrival_m3_rejected": filled,
            "own_production_m3": float(verdict.own_production_m3),
            "ratio_rejected_over_used": (filled / used) if used > 0.0 else float("inf"),
            "contributing_cells_used": float(verdict.contributing_cells),
            "verdict": verdict.verdict,
        })
    return rows


def _seed_windows(sampler, lake_xz_m, sizes, spacing_m, config):
    """Measure one basin in a growing centred window family, from absolute coordinates."""
    lake = np.asarray(lake_xz_m, np.float64).reshape(-1)
    if lake.size != 2 or not np.isfinite(lake).all():
        raise ValueError("finite [x, z] lake position required")
    spacing = float(spacing_m)
    cell_area = spacing * spacing
    centre_column = int(round(float(lake[0]) / spacing))
    centre_row = int(round(float(lake[1]) / spacing))
    records = []
    for size in sorted(int(value) for value in sizes):
        origin_column = centre_column - size // 2
        origin_row = centre_row - size // 2
        field = np.ascontiguousarray(
            np.asarray(sampler((origin_column * spacing, origin_row * spacing),
                               (size, size)), np.float64))
        if field.shape != (size, size):
            raise ValueError("sampler returned %s for a %dx%d window"
                             % (field.shape, size, size))
        routed = route_and_accumulate(field, spacing, 1.0)
        filled, discharge = routed["filled_m"], routed["discharge_m3"]
        labels, count = label_depressions((filled - field) > 0.0)
        seed = (centre_row - origin_row, centre_column - origin_column)
        label = int(labels[seed]) if count else -1
        record = {"size": size, "window_km": size * spacing / 1000.0,
                  "origin_xz_m": [float(origin_column * spacing),
                                  float(origin_row * spacing)],
                  "seed_rc": [int(seed[0]), int(seed[1])]}
        if label < 0:
            record.update(component_absent=True, basin_cells=0, basin_area_m2=0.0,
                          capacity_m3=0.0, spill_level_m=float("nan"),
                          bed_min_m=float(field[seed]), rim_clearance_cells=0,
                          inflow_per_metre_m3=0.0, suspect_window_truncation=True)
            records.append(record)
            continue
        component = labels == label
        beds = field[component]
        top = float(filled[component].max())
        cells = int(component.sum())
        clearance = rim_clearance_cells(component, field.shape)
        record.update(
            component_absent=False, basin_cells=cells,
            basin_area_m2=float(cells) * cell_area,
            capacity_m3=float(np.sum(top - beds) * cell_area),
            spill_level_m=top, bed_min_m=float(beds.min()),
            rim_clearance_cells=clearance,
            # accumulated for a 1 m run, so the caller scales it by its own depth
            inflow_per_metre_m3=float(discharge[component].max()),
            suspect_window_truncation=bool(clearance < config.contact_margin_cells))
        records.append(record)
    return records


def judge_seed_in_windows(sampler, lake_xz_m, sizes, spacing_m, *, produced_depth_m,
                          config=None, window_records=None):
    """Measure one basin in a window family and put it through the full gate.

    `sampler(origin_xz_m, shape)` must serve elevation from **absolute** world
    coordinates (the `PageMosaic.sampler` contract), so a value cannot depend on
    which window asked for it. `sizes` is the window family; criterion (c) is
    judged by `growth_verdict` on the accepted members, at full strength.

    The largest **accepted** window supplies capacity, area, spill level and
    clearance; the whole family supplies the growth answer. Returns
    ``(verdict, family)``, `family` carrying every window record and the growth
    verdict, so a caller can audit each window that was tried.

    `window_records` lets a caller hand in records measured elsewhere (e.g.
    `metric_cross_region.window_family`, whose windows are clamped inside a page
    rather than centred); those must carry `size`, `basin_cells`,
    `suspect_window_truncation` and `inflow_per_metre_m3`.
    """
    config = config or DepressionGateConfig()
    depth = float(produced_depth_m)
    if not math.isfinite(depth) or depth < 0.0:
        raise ValueError("finite nonnegative produced_depth_m required")
    cell_area = float(spacing_m) ** 2
    records = list(window_records) if window_records is not None else _seed_windows(
        sampler, lake_xz_m, sizes, spacing_m, config)
    if not records:
        raise ValueError("at least one window record required")
    accepted = [record for record in records
                if not record.get("suspect_window_truncation", False)
                and int(record.get("basin_cells", 0)) > 0]
    best = max(accepted or records, key=lambda record: int(record["size"]))
    converged, gate = growth_verdict(records) if len(records) > 1 \
        else (False, GROWTH_SINGLE_WINDOW)
    spill = best.get("spill_level_m", float("nan"))
    bed_min = best.get("bed_min_m", float("nan"))
    finite = all(math.isfinite(float(value)) for value in (spill, bed_min))
    inflow = float(best.get("inflow_per_metre_m3", 0.0) or 0.0) * depth
    verdict = judge_depression(
        basin_cells=int(best.get("basin_cells", 0)),
        capacity_m3=float(best.get("capacity_m3", 0.0) or 0.0),
        inflow_m3=inflow,
        area_m2=float(best.get("basin_area_m2", 0.0) or 0.0),
        spill_level_m=float(spill) if finite else 0.0,
        config=config, label=-1, input_quantity=INFLOW_FILLED_CATCHMENT,
        contributing_cells=(inflow / (cell_area * depth)) if depth > 0.0 else float("nan"),
        contributing_area_m2=(inflow / depth) if depth > 0.0 else float("nan"),
        bed_min_m=float(bed_min) if finite else 0.0,
        rim_clearance_cells=int(best.get("rim_clearance_cells", 0)),
        growth_converged=converged, convergence_gate=gate,
        component_absent=bool(best.get("component_absent", False)))
    return verdict, {"records": records, "growth_converged": converged,
                     "convergence_gate": gate,
                     "accepted_sizes": [int(record["size"]) for record in accepted],
                     "measured_on_size": int(best["size"])}


def spill_work_surface(elevation_m, verdicts, context, *, config=None):
    """Raise the **work** surface of every refused pool; never touch the bed.

    Only cells of a `pass_through` depression are raised, and only to that
    depression's own `spill_level_m`. Cells of a `lake` keep their terrain height
    exactly, so a real basin is not flattened into its surroundings -- a stated
    difference from a global fill.

    Returns ``(work_m, metadata)``. `work_m` is a new array; `elevation_m` is
    never written to, and ``metadata["work_surface_only"]`` is ``True`` for the
    same reason `spill_candidate` sets it: this is a routing candidate, not
    published terrain.
    """
    config = config or DepressionGateConfig()
    bed = np.asarray(elevation_m, np.float64)
    labels = np.asarray(context["labels"], np.int64)
    if labels.shape != bed.shape:
        raise ValueError("labels and elevation must share a shape")
    spill = np.asarray(context["spill_level_m_by_label"], np.float64)
    sizes = np.asarray(context["basin_cells_by_label"], np.int64)
    refused = np.zeros(spill.size, bool)
    for verdict in verdicts:
        if verdict.verdict != VERDICT_PASS_THROUGH:
            continue
        label = int(verdict.label)
        if not 0 <= label < spill.size:
            raise ValueError("a refused verdict must carry the label it was measured on")
        if int(sizes[label]) != int(verdict.basin_cells):
            raise ValueError("verdict and context disagree about the depression's size")
        refused[label] = True
    work = bed.copy()
    flat_labels = labels.reshape(-1)
    flat_bed = bed.reshape(-1)
    flat_work = work.reshape(-1)
    wet = flat_labels >= 0
    raise_here = wet & refused[np.where(wet, flat_labels, 0)]
    flat_work[raise_here] = spill[flat_labels[raise_here]]
    raised_cells = int(raise_here.sum())
    total_wet = int(wet.sum())
    raised_volume = float(np.sum(flat_work[raise_here] - flat_bed[raise_here])
                          * context["cell_area_m2"])
    return work, {
        "work_surface_only": True,
        "publishable_terrain": False,
        "original_bed_unmodified": True,
        "raised_cells": raised_cells,
        "preserved_lake_cells": total_wet - raised_cells,
        "wet_cells_total": total_wet,
        "raised_volume_m3": raised_volume,
        "maximum_raise_m": float(np.max(work - bed)),
        "refused_depressions": int(refused.sum()),
        "policy": ("raise only the depressions the gate refused, each to its own spill "
                   "level; every lake keeps its terrain height"),
        "compare_with_global_fill": ("a border-seeded fill would raise all %d wet cells; "
                                     "this raises %d and leaves %d as terrain"
                                     % (total_wet, raised_cells, total_wet - raised_cells)),
        "config": {"alpha": float(config.alpha),
                   "min_area_m2": float(config.min_area_m2),
                   "contact_margin_cells": int(config.contact_margin_cells)},
    }


def basin_size_distribution(values):
    """Counts by size decade -- the 'before vs after' shape, not a mean."""
    array = np.asarray(values, np.int64).reshape(-1)
    edges = (1, 2, 4, 8, 16, 32, 64, 128, 512, 2048, 8192, 32768)
    rows = []
    for index, low in enumerate(edges):
        if index + 1 < len(edges):
            high = edges[index + 1] - 1
            mask = array == low if low == 1 else ((array >= low) & (array <= high))
        else:
            high = None
            mask = array >= low
        rows.append({"lowest_cells": int(low),
                     "highest_cells": None if high is None else int(high),
                     "count": int(mask.sum())})
    return rows


@dataclass(frozen=True)
class DepressionGateReport:
    """Both ledgers from one run: pure closure and the gate. Neither overwrites."""

    verdicts: tuple
    context: dict = field(repr=False)
    spacing_m: float = 30.0
    produced_depth_m: float = float("nan")
    config: DepressionGateConfig = DepressionGateConfig()

    @property
    def by_hypsometry(self):
        return [record for record in self.verdicts if record.closed_basin_by_hypsometry]

    @property
    def by_gate(self):
        return [record for record in self.verdicts if record.is_domain_terminal]

    @property
    def truncated(self):
        return [record for record in self.verdicts if record.truncated_not_judged]

    def summary(self):
        """Headline counts, size distributions and the reason tally.

        Three columns that must never be collapsed into two:

        * ``closed_basin_by_hypsometry`` -- pure terrain closure;
        * ``truncated_not_judged`` -- closed on the terrain but the rim lies inside
          the untrusted border band, so this page cannot judge it;
        * ``is_domain_terminal`` -- what the gate keeps.
        """
        before = self.by_hypsometry
        after = self.by_gate
        truncated = self.truncated
        reasons = {code: 0 for code in REASON_CODES}
        for record in self.verdicts:
            reasons[record.reason_code] = reasons.get(record.reason_code, 0) + 1
        single_before = sum(1 for record in before if record.basin_cells == 1)
        single_after = sum(1 for record in after if record.basin_cells == 1)
        return {
            "schema": SCHEMA,
            "spacing_m": float(self.spacing_m),
            "produced_depth_m": float(self.produced_depth_m),
            "alpha": float(self.config.alpha),
            "min_area_m2": float(self.config.min_area_m2),
            "contact_margin_cells": int(self.config.contact_margin_cells),
            "require_growth_convergence": bool(self.config.require_growth_convergence),
            "inflow_quantity": INFLOW_FILLED_CATCHMENT,
            "routing_model": self.context["routing_model"],
            "accumulation_model": self.context["accumulation_model"],
            "water_ledger": {
                "input_total_m3": float(self.context["input_total_m3"]),
                "outlet_total_m3": float(self.context["outlet_total_m3"]),
                "residual_m3": float(self.context["residual_m3"]),
                "residual_relative": (
                    float(self.context["residual_m3"]) / float(self.context["input_total_m3"])
                    if float(self.context["input_total_m3"]) > 0.0 else 0.0),
            },
            "depression_count": len(self.verdicts),
            "single_cell_before": int(single_before),
            "single_cell_after": int(single_after),
            "closed_basin_by_hypsometry": {
                "count": len(before),
                "cells_total": int(sum(record.basin_cells for record in before)),
                "area_m2_total": float(sum(record.area_m2 for record in before)),
                "size_distribution": basin_size_distribution(
                    [record.basin_cells for record in before]),
            },
            "truncated_not_judged": {
                "count": len(truncated),
                "cells_total": int(sum(record.basin_cells for record in truncated)),
                "area_m2_total": float(sum(record.area_m2 for record in truncated)),
                "size_distribution": basin_size_distribution(
                    [record.basin_cells for record in truncated]),
                "why": ("the rim lies inside the untrusted border band, so this window "
                        "cannot measure the basin; reported, never used as a verdict"),
            },
            "is_domain_terminal": {
                "count": len(after),
                "cells_total": int(sum(record.basin_cells for record in after)),
                "area_m2_total": float(sum(record.area_m2 for record in after)),
                "size_distribution": basin_size_distribution(
                    [record.basin_cells for record in after]),
            },
            "reclassified_pass_through": len(before) - len(after) - len(truncated),
            "truncated_depressions": len(truncated),
            "reason_counts": reasons,
        }

    def identity_sha256(self):
        return identity(
            {"labels": np.asarray(self.context["labels"], np.int64)},
            dict(self.summary(),
                 verdicts=[record.as_record() for record in self.verdicts],
                 config={"alpha": self.config.alpha,
                         "min_area_m2": self.config.min_area_m2,
                         "contact_margin_cells": self.config.contact_margin_cells,
                         "require_growth_convergence":
                             self.config.require_growth_convergence}))


def gate_report(elevation_m, *, spacing_m, produced_depth_m, config=None):
    """Measure, judge and package both ledgers for one field."""
    config = config or DepressionGateConfig()
    verdicts, context = measure_depressions(
        elevation_m, spacing_m=spacing_m, produced_depth_m=produced_depth_m,
        config=config)
    return DepressionGateReport(verdicts=tuple(verdicts), context=context,
                                spacing_m=float(spacing_m),
                                produced_depth_m=float(produced_depth_m), config=config)
