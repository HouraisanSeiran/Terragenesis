"""Cross-region consistency for real 30 m pages: overlap equality, load-order invariance,
and the rule that a window edge is never an outlet.

Why this module exists
----------------------
A 30 m page is built from a *window* of an unbounded field. Three separate things can
go wrong when two windows are combined, and they must not be confused:

1. **Same point, two answers.** If two windows disagree at a world coordinate, every
   quantity derived from that coordinate inherits an ambiguity. The only useful
   question is *where* the disagreement is: a window is decoded from a residual field
   with a fixed kernel margin, so its outermost cells are reconstructed with less
   surrounding context than its interior. That is a **border band** property, and it
   is measurable: this module reports the per-band difference profile instead of a
   single RMS that averages a bit-exact interior together with a 0.3 m edge.

2. **Order-dependent accumulation.** Summing floating point numbers in a different
   order gives a different answer at the ULP level, and *any* accumulated quantity in
   a tiling pipeline is exposed to that. The honest response is not to assert
   "identical"; it is to separate the two populations: exact integer counts (identical
   by construction) from float reductions (identical only under a declared order or a
   compensated summation), and to measure both.

3. **A window edge read as an outlet.** A border-seeded priority flood treats every
   border cell as a drain, because on the page it drains off the page. When the page
   *is* the whole domain that is correct. When the page is a window on a larger field
   it silently invents an outlet wherever the window cuts a basin rim, and the resulting
   spill level is not merely imprecise -- it is a plausible-looking number that can be
   a hundred metres wrong. This already happened here: a 15.39 km window reported
   **228.15 m** for a basin whose 30.75 km window reports **337.18 m**. The small window
   looked entirely reasonable.

So this module refuses to answer basin questions from a window unless the basin's rim
is provably clear of the window border, and it reports the measured clearance instead
of a boolean that can be *narrowly* wrong.

What is deliberately absent
--------------------------
No new hydrology, no solver, no terrain model. Every number here is a difference,
count, or reduction of fields that already exist; the module adds the comparison,
the order-invariance reduction, and the refusal vocabulary.

Reason codes
------------
Refusals use the vocabulary of `metric_domain_pipeline.REASON_ORDER` so a caller can
recognise them without a translation table:

======================  =========================================================
`out_of_tile`           no loaded page covers the point
`unresolved_border`     covered, but only inside a page's declared border band
`overlapping_disagreement`  two covering pages disagree beyond the declared tolerance
`ocean`                 the point is below the declared sea datum (an outlet, not a rim)
`closed_basin`          covered with clearance; the answer is usable
======================  =========================================================
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from terrain_pipeline.common_infra import identity

# A window's outermost cells are decoded with a truncated kernel support
# (see `WorldPipeline._compute_elev`: `pad_lr = kernel_size // 2 + 1` latent cells,
# `pad_hr = pad_lr * latent_compression` fine cells). The number below is **not**
# derived from that constant; it is the measured extent on the real 2049 pages: all
# disagreement between overlapping windows is confined to this many cells of each
# window's own border, and everything beyond it is bit-identical (see the report).
BORDER_BAND_CELLS = 6

# A basin whose rim comes closer than this to the window border is treated as cut, even
# when `metric_lake_hypsometry._touches_border` says otherwise. That check asks whether
# the component leaves the interior `[2:-2]`, i.e. whether it comes within **1** cell of
# the edge -- a probe confirms distance 0 and 1 are flagged and 2 is not. "Is the rim on
# this page" is a different question, and on the real page the two answers come apart: a
# 513-cell window cut the basin, the fill stopped 2 cells short of the edge,
# `_touches_border` returned False, and the spill level came out 19.16 m low.
#
# The margin is set equal to `BORDER_BAND_CELLS` on purpose rather than tuned: inside that
# band the elevations themselves are reconstruction artefacts, so a rim found there is not
# a measured rim. It is a declared margin with a stated reason, and it is overridable.
CONTACT_MARGIN_CELLS = BORDER_BAND_CELLS

REASON_OUT_OF_TILE = "out_of_tile"
REASON_UNRESOLVED_BORDER = "unresolved_border"
REASON_DISAGREEMENT = "overlapping_disagreement"
REASON_OCEAN = "ocean"
REASON_CLOSED_BASIN = "closed_basin"


# --------------------------------------------------------------------------- #
# page bookkeeping
# --------------------------------------------------------------------------- #
def _page_array(page):
    array = np.asarray(page, np.float64)
    if array.ndim != 2 or array.size < 4:
        raise ValueError("each page must be a 2D elevation array")
    if not np.isfinite(array).all():
        raise ValueError("finite elevation required in every page")
    return array


def _native_origin(origin):
    values = np.asarray(origin, np.int64).reshape(-1)
    if values.size != 2:
        raise ValueError("integer [column, row] native origin required")
    return int(values[0]), int(values[1])


def _overlap(a_origin, a_shape, b_origin, b_shape):
    """Half-open native index box shared by two pages, or None when they do not overlap."""
    x0 = max(a_origin[0], b_origin[0])
    x1 = min(a_origin[0] + a_shape[1], b_origin[0] + b_shape[1])
    z0 = max(a_origin[1], b_origin[1])
    z1 = min(a_origin[1] + a_shape[0], b_origin[1] + b_shape[0])
    if x1 <= x0 or z1 <= z0:
        return None
    return x0, x1, z0, z1


def _take(page, origin, box):
    x0, x1, z0, z1 = box
    return page[z0 - origin[1]:z1 - origin[1], x0 - origin[0]:x1 - origin[0]]


def _border_distance(origin, shape, box):
    """Distance, in cells, from each cell of `box` to its own page's nearest border."""
    x0, x1, z0, z1 = box
    columns = np.arange(x0, x1)
    rows = np.arange(z0, z1)
    dc = np.minimum(columns - origin[0], origin[0] + shape[1] - 1 - columns)
    dr = np.minimum(rows - origin[1], origin[1] + shape[0] - 1 - rows)
    return np.minimum(np.broadcast_to(dr[:, None], (rows.size, columns.size)),
                      np.broadcast_to(dc[None, :], (rows.size, columns.size)))


# --------------------------------------------------------------------------- #
# 1. overlap: the same physical point answered twice
# --------------------------------------------------------------------------- #
def overlap_comparison(page_a, origin_a, page_b, origin_b,
                       border_band_cells=BORDER_BAND_CELLS):
    """Point-by-point comparison of one world region covered by two pages.

    Returns the overlap box, the exact-equality verdict, the difference statistics,
    and -- because a single RMS hides the structure -- the difference count and
    largest difference **per distance band from each page's own border**.

    The `interior_bitwise_identical` verdict is the only tolerance-free statement:
    it says that every cell at least `border_band_cells` away from both borders is
    bit-for-bit equal. Anything inside the band is reported with its measured size
    and is excluded from assembly by `assemble_pages`, not tolerated.
    """
    band = int(border_band_cells)
    if band < 0:
        raise ValueError("border_band_cells must be non-negative")
    a = _page_array(page_a)
    b = _page_array(page_b)
    oa = _native_origin(origin_a)
    ob = _native_origin(origin_b)
    box = _overlap(oa, a.shape, ob, b.shape)
    if box is None:
        return {
            "overlaps": False,
            "page_a": {"native_origin": list(oa), "shape": list(a.shape)},
            "page_b": {"native_origin": list(ob), "shape": list(b.shape)},
            "note": ("the two windows share no native cell; there is no overlap to compare. "
                     "This is reported as a fact, not filled in with a neighbouring pair."),
        }
    sa = _take(a, oa, box)
    sb = _take(b, ob, box)
    difference = sa - sb
    absolute = np.abs(difference)
    differing = absolute > 0.
    distance = np.minimum(_border_distance(oa, a.shape, box),
                          _border_distance(ob, b.shape, box))
    interior = distance >= band

    bands = []
    top = int(distance.max())
    for low in range(0, min(top, band) + 1):
        mask = distance == low
        if not mask.any():
            continue
        hit = mask & differing
        bands.append({"border_distance_cells": low, "cells": int(mask.sum()),
                      "differing_cells": int(hit.sum()),
                      "max_abs_difference_m": float(absolute[hit].max()) if hit.any() else 0.0})

    interior_differing = int((differing & interior).sum())
    scaled = np.maximum(np.abs(sa), np.abs(sb))
    floor = np.finfo(np.float32).tiny
    relative = absolute / np.maximum(scaled, floor)

    return {
        "overlaps": True,
        "overlap_native_box": {"columns": [int(box[0]), int(box[1])],
                               "rows": [int(box[2]), int(box[3])]},
        "overlap_cells": int(sa.size),
        "overlap_km": [ (box[1] - box[0]) * 30.0 / 1000.0, (box[3] - box[2]) * 30.0 / 1000.0 ],
        "page_a": {"native_origin": list(oa), "shape": list(a.shape)},
        "page_b": {"native_origin": list(ob), "shape": list(b.shape)},
        "identical_cells": int(sa.size - int(differing.sum())),
        "differing_cells": int(differing.sum()),
        "differing_fraction": float(differing.mean()),
        "max_abs_difference_m": float(absolute.max()),
        "rms_difference_m": float(np.sqrt((difference ** 2).mean())),
        "max_relative_difference": float(relative.max()),
        "border_band_cells": band,
        "per_border_band": bands,
        "interior_cells": int(interior.sum()),
        "interior_differing_cells": interior_differing,
        "interior_bitwise_identical": bool(interior_differing == 0),
        "differences_confined_to_border_band": bool(interior_differing == 0),
        "declared_tolerance": {
            "interior": "exactly 0.0 (bitwise float64 equality; no tolerance is used)",
            "border_band": {"cells": band,
                            "max_abs_m": float(absolute[~interior].max()) if (~interior).any() else 0.0,
                            "source": ("each window is decoded from the shared residual field with a "
                                       "fixed kernel margin (WorldPipeline._compute_elev pads "
                                       "latent_compression*(kernel_size//2+1) fine cells), so the "
                                       "outermost cells are reconstructed with truncated context; "
                                       "the disagreement is a border-support artefact, not two "
                                       "random samples")},
        },
    }


# --------------------------------------------------------------------------- #
# 2. assembly: order-invariant by construction
# --------------------------------------------------------------------------- #
def assemble_pages(pages, border_band_cells=BORDER_BAND_CELLS, origin=None, shape=None,
                   order=None):
    """Assemble one field from overlapping pages without depending on their order.

    Each cell is taken from the covering page that has the **largest clearance from
    its own border**; ties go to the lexicographically smallest page key. That rule
    is a pure function of the (position, clearance) set and therefore commutative and
    associative -- `order` may be permuted without changing the output by one bit.

    Cells covered only inside every candidate's border band are reported as
    `unresolved_border` and filled with NaN: they are not answered, and they are not
    silently closed either.

    `order` is accepted only so that a caller can *demonstrate* the invariance; it does
    not change the result.
    """
    band = int(border_band_cells)
    if band < 0:
        raise ValueError("border_band_cells must be non-negative")
    if not pages:
        raise ValueError("at least one page required")
    prepared = []
    for entry in pages:
        if isinstance(entry, dict):
            key = str(entry["key"])
            array = entry["page"]
            origin_native = entry["native_origin"]
        else:
            key, array, origin_native = entry
        prepared.append((key, _page_array(array), _native_origin(origin_native)))
    keys = [key for key, _, _ in prepared]
    if len(set(keys)) != len(keys):
        raise ValueError("page keys must be unique")
    if order is not None:
        requested = [str(value) for value in order]
        if sorted(requested) != sorted(keys):
            raise ValueError("order must be a permutation of the page keys")

    if origin is None or shape is None:
        raise ValueError("explicit origin and shape required (no inferred extent)")
    rows, columns = (int(value) for value in shape)
    if rows < 2 or columns < 2:
        raise ValueError("at least 2x2 cells required")
    origin = _native_origin(origin)
    x0, z0 = origin
    box = (x0, x0 + columns, z0, z0 + rows)

    best_value = np.full((rows, columns), np.nan, np.float64)
    best_score = np.full((rows, columns), -1, np.int64)
    best_key = np.full((rows, columns), "", dtype="U32")
    covered = np.zeros((rows, columns), bool)
    for key, array, origin_native in prepared:
        shared = _overlap(origin_native, array.shape, origin, (rows, columns))
        if shared is None:
            continue
        distance = _border_distance(origin_native, array.shape, shared)
        values = _take(array, origin_native, shared)
        score = distance
        # Window the shared box into our own array.
        sx0, sx1, sz0, sz1 = shared
        local = (slice(sz0 - z0, sz1 - z0), slice(sx0 - x0, sx1 - x0))
        better = (score > best_score[local]) | (
            (score == best_score[local]) & (best_key[local] < key))
        take = score >= band
        update = better & take
        best_value[local] = np.where(update, values, best_value[local])
        best_score[local] = np.where(update, score, best_score[local])
        best_key[local] = np.where(update, key, best_key[local])
        covered[local] = covered[local] | take

    resolved = np.isfinite(best_value)
    return {
        "field": best_value,
        "resolved_mask": resolved,
        "unresolved_mask": ~resolved,
        "origin_native": list(origin),
        "shape": [rows, columns],
        "border_band_cells": band,
        "page_keys": sorted(keys),
        "order_requested": list(order) if order is not None else sorted(keys),
        "resolved_cells": int(resolved.sum()),
        "unresolved_cells": int((~resolved).sum()),
        "unresolved_reason": REASON_UNRESOLVED_BORDER if (~resolved).any() else None,
        "selection_rule": ("per cell, the page with the largest clearance from its own border; "
                           "ties by lexicographically smallest page key; cells with clearance "
                           "below the band from every page are left unresolved"),
        "selection_key_digest": hashlib.sha256(
            _json_bytes(best_key.tobytes())).hexdigest(),
    }


def _json_bytes(payload):
    return payload if isinstance(payload, bytes) else str(payload).encode("utf-8")


def assembly_digest(assembly):
    """Digest of an assembly including *which* page supplied each cell.

    Two assemblies with the same elevations but a different provenance are not the
    same assembly, so the selection key is part of the digest.
    """
    return identity({"field": np.asarray(assembly["field"], np.float64),
                     "resolved": np.asarray(assembly["resolved_mask"], bool)},
                    {"origin_native": list(assembly["origin_native"]),
                     "shape": list(assembly["shape"]),
                     "border_band_cells": int(assembly["border_band_cells"]),
                     "selection_key_digest": assembly["selection_key_digest"]})


# --------------------------------------------------------------------------- #
# 3. cumulative quantities, and what "equal" can mean for them
# --------------------------------------------------------------------------- #
def _flood(field, resolved):
    """Priority flood seeded from the boundary of the *resolved* set.

    Two things are deliberate here.

    * **Unresolved cells are impassable, not drains.** A hole in the support is not an
      outlet. Treating it as one would be the edge-as-outlet mistake in disguise.
    * **The seed set is the resolved set's own boundary**, not the array border. When a
      caller assemblies pages with a border band removed, the array border is entirely
      unresolved, so a border-seeded flood would have no seed at all and would report
      zero depressions -- a silently empty answer.

    Seeding from the resolved boundary means the returned spill levels describe the
    *analysis region*, whose outer edge is a declared open boundary of the test and not
    a terrain outlet. `cumulative_quantities` states this in `region_relative`; these
    numbers are compared across assembly orders and are never reported as terrain truth.
    """
    import heapq

    bed = np.asarray(field, np.float64)
    valid = np.asarray(resolved, bool)
    if bed.shape != valid.shape:
        raise ValueError("matching field and mask required")
    if not valid.any():
        raise ValueError("no resolved cells: nothing to flood")
    rows, columns = bed.shape
    filled = np.full(bed.shape, np.inf, np.float64)
    seen = np.zeros(bed.shape, bool)
    heap = []
    # A resolved cell is a seed when any 4-neighbour is outside the array or unresolved.
    padded = np.pad(valid, 1, mode="constant", constant_values=False)
    neighbour_count = sum(padded[1 + dr:rows + 1 + dr, 1 + dc:columns + 1 + dc]
                          for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
    boundary = valid & (neighbour_count < 4)
    if not boundary.any():
        # Fully resolved with no gap: the array border is the region boundary.
        boundary = np.zeros((rows, columns), bool)
        boundary[[0, -1], :] = True
        boundary[:, [0, -1]] = True
        boundary = boundary & valid
    seeds = boundary
    for cell in np.argwhere(seeds):
        r, c = int(cell[0]), int(cell[1])
        seen[r, c] = True
        filled[r, c] = bed[r, c]
        heapq.heappush(heap, (float(bed[r, c]), r, c))
    neighbours = ((-1, 0), (1, 0), (0, -1), (0, 1))
    while heap:
        level, r, c = heapq.heappop(heap)
        for dr, dc in neighbours:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < rows and 0 <= cc < columns):
                continue
            if seen[rr, cc] or not valid[rr, cc]:
                continue
            seen[rr, cc] = True
            value = max(float(bed[rr, cc]), level)
            filled[rr, cc] = value
            heapq.heappush(heap, (value, rr, cc))
    return filled, filled - bed, seen


def cumulative_quantities(field, resolved_mask, spacing_m=30.0, float_order=None):
    """Accumulated quantities with their exactness class declared.

    Two kinds of quantity are returned and they must not be compared the same way:

    * **integer counts and extrema** (`resolved_cells`, `depression_count`,
      `largest_depression_cells`, `largest_spill_level_m`, `largest_bed_m`). An
      integer count is order-free by construction, and an extremum is idempotent,
      commutative and associative, so it is reproduced exactly.
    * **float sums** (`resolved_elevation_sum_m`). This one follows the summation order
      and is the only order-dependent reduction in the set. `wetted_area_m2` and the
      other areas are an integer count times a constant, so they are exact floats and
      are listed as such rather than as reductions.
    """
    bed = np.asarray(field, np.float64)
    valid = np.asarray(resolved_mask, bool)
    if bed.shape != valid.shape:
        raise ValueError("matching field and mask required")
    spacing = float(spacing_m)
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("finite positive spacing required")
    filled, depth, reached = _flood(bed, valid)
    wet = (depth > 0.) & valid & reached

    from scipy import ndimage

    labels, count = ndimage.label(wet)
    sizes = ndimage.sum(wet, labels, range(1, count + 1)) if count else np.array([])
    if count:
        largest = int(np.argmax(sizes)) + 1
        component = labels == largest
        largest_cells = int(sizes[largest - 1])
        largest_spill = float(filled[component].max())
        largest_bed = float(bed[component].min())
    else:
        largest_cells = 0
        largest_spill = float("nan")
        largest_bed = float("nan")

    values = bed[valid]
    if float_order is None:
        forward = float(np.float64(values.sum()))
        backward = float(np.float64(values[::-1].sum()))
        spread = abs(forward - backward)
        total = forward
        order_used = "numpy C-order sum"
    else:
        indexes = np.asarray(float_order, np.int64)
        if indexes.size != values.size or sorted(indexes.tolist()) != list(range(values.size)):
            raise ValueError("float_order is not a permutation of the resolved cells")
        total = float(np.float64(values[indexes].sum()))
        reference = float(np.float64(values.sum()))
        spread = abs(total - reference)
        order_used = "caller-supplied permutation"

    return {
        "resolved_cells": int(valid.sum()),
        "unresolved_cells": int((~valid).sum()),
        "resolved_area_m2": float(valid.sum()) * spacing * spacing,
        "resolved_elevation_sum_m": total,
        "sum_order_spread_m": spread,
        "sum_order_used": order_used,
        "depression_count": int(count),
        "wetted_cells": int(wet.sum()),
        "wetted_area_m2": float(wet.sum()) * spacing * spacing,
        "depression_area_m2": float(wet.sum()) * spacing * spacing,
        "largest_depression_cells": largest_cells,
        "largest_depression_area_m2": float(largest_cells) * spacing * spacing,
        "largest_spill_level_m": largest_spill,
        "largest_bed_m": largest_bed,
        "exactness": {
            "integer_counts": ["resolved_cells", "depression_count", "wetted_cells",
                               "largest_depression_cells"],
            "extrema": ["largest_spill_level_m", "largest_bed_m"],
            "exact_float_products": ["resolved_area_m2", "wetted_area_m2",
                                     "depression_area_m2", "largest_depression_area_m2"],
            "order_dependent_float_reduction": ["resolved_elevation_sum_m"],
        },
        "region_relative": ("the flood is seeded from the analysis region's own border, so the "
                            "counts describe this region, not the unbounded terrain; they are "
                            "compared across assembly orders, never reported as terrain truth"),
    }


def load_order_invariance(pages, orders, origin=None, shape=None,
                          border_band_cells=BORDER_BAND_CELLS, spacing_m=30.0):
    """Assemble the same pages in several orders and compare the accumulated quantities."""
    if not orders:
        raise ValueError("at least one order required")
    runs = []
    for order in orders:
        assembly = assemble_pages(pages, border_band_cells=border_band_cells,
                                  origin=origin, shape=shape, order=order)
        quantities = cumulative_quantities(assembly["field"], assembly["resolved_mask"],
                                          spacing_m=spacing_m)
        runs.append({"order": list(order), "digest": assembly_digest(assembly),
                     "resolved_cells": assembly["resolved_cells"],
                     "unresolved_cells": assembly["unresolved_cells"],
                     "quantities": quantities})
    reference = runs[0]
    comparison = {"identical_digests": len({run["digest"] for run in runs}) == 1,
                  "identical_quantities": len({_quantities_key(run["quantities"]) for run in runs}) == 1}
    differences = {}
    undefined = []
    for key, value in reference["quantities"].items():
        if isinstance(value, bool) or not isinstance(value, float):
            continue
        values = [run["quantities"][key] for run in runs]
        if not all(math.isfinite(item) for item in values):
            # NaN is not a spread. Saying "spread = NaN" would quietly turn the
            # comparison into a non-comparison; the quantity is listed as undefined.
            undefined.append(key)
            continue
        spread = max(values) - min(values)
        if spread != 0.0:
            differences[key] = spread
    return {"page_keys": sorted(str(entry[0] if not isinstance(entry, dict) else entry["key"])
                                 for entry in pages),
            "orders": [[str(key) for key in order] for order in orders],
            "runs": runs, "comparison": comparison,
            "float_quantity_spread": differences,
            "nonfinite_quantities": undefined,
            "note": ("float reductions are compared by spread, not by equality. An empty "
                     "`float_quantity_spread` means every finite float quantity was also "
                     "reproduced exactly for these orders -- which is a measurement, not a "
                     "guarantee: `resolved_elevation_sum_m` is order-dependent in general.")}


def _quantities_key(quantities):
    record = {key: value for key, value in quantities.items()
              if isinstance(value, (int, float, str, bool, type(None)))}
    return json.dumps(record, sort_keys=True, allow_nan=True, default=str)


# --------------------------------------------------------------------------- #
# 4. window edge is not an outlet
# --------------------------------------------------------------------------- #
def basin_reaches_window_edge(component_mask, contact_margin_cells=CONTACT_MARGIN_CELLS):
    """Measured rim clearance, not a boolean that can be narrowly wrong.

    `metric_lake_hypsometry._touches_border` asks whether the depression component
    reaches the ring at index 2. That is not the same question as "is the rim on this
    page": on the real page below, a 513-cell window cuts the basin and the fill stops
    two cells short of the row edge, so `_touches_border` returns False while the spill
    level is 19 m too low. This function returns the distance so the caller can apply
    a declared margin, and `suspect` says whether that margin is violated.
    """
    mask = np.asarray(component_mask, bool)
    if mask.ndim != 2 or not mask.any():
        raise ValueError("nonempty 2D component mask required")
    margin = int(contact_margin_cells)
    if margin < 0:
        raise ValueError("contact_margin_cells must be non-negative")
    rows, columns = mask.shape
    rr, cc = np.nonzero(mask)
    distance = int(min(rr.min(), cc.min(), rows - 1 - rr.max(), columns - 1 - cc.max()))
    return {"rim_clearance_cells": distance,
            "rim_clearance_m": distance * 30.0,
            "contact_margin_cells": margin,
            "suspect_window_truncation": bool(distance < margin),
            "touches_border_by_hypsometry_ring_2": bool(distance <= 1),
            "hypsometry_test_threshold_cells": 1,
            "note": ("a rim closer than the declared margin is treated as cut. The hypsometry "
                     "test is reported alongside so the two criteria can be compared, not so one "
                     "can excuse the other. Its threshold is 1 cell, not 2: it builds "
                     "`inner[2:-2]` and asks whether the component leaves that interior, which "
                     "happens at distance 0 or 1 -- verified by direct probe, not by reading the "
                     "slice.")}


def window_family(page, origin_native, seed_rc, sizes, spacing_m=30.0,
                  contact_margin_cells=CONTACT_MARGIN_CELLS, spacing_cells=None):
    """Measure one basin in a family of windows placed around it, inside one page.

    Window placement is a declared rule, not a choice made after seeing the numbers:
    each window is centred on the seed cell and then clamped so it stays inside the
    page (`min(max(seed - size//2, 0), extent - size)`). Enlarging the window therefore
    only ever *adds* terrain around the basin.

    Every record carries the naive spill level alongside the truncation verdict, so the
    wrong number stays visible next to the measurement that condemns it.
    """
    from terrain_pipeline.lake import depression_component as depression_component
    from terrain_pipeline.lake import depression_hierarchy as depression_hierarchy

    array = _page_array(page)
    origin = _native_origin(origin_native)
    seed = (int(seed_rc[0]), int(seed_rc[1]))
    rows, columns = array.shape
    if not (0 <= seed[0] < rows and 0 <= seed[1] < columns):
        raise ValueError("seed cell outside the page")
    ordered = sorted(int(value) for value in sizes)
    if len(ordered) < 2 or ordered[0] < 8:
        raise ValueError("at least two window sizes of 8 cells or more required")
    records = []
    for size in ordered:
        if size > min(rows, columns):
            raise ValueError("window size %d exceeds the page %s" % (size, array.shape))
        o_r = min(max(seed[0] - size // 2, 0), rows - size)
        o_c = min(max(seed[1] - size // 2, 0), columns - size)
        field = np.ascontiguousarray(array[o_r:o_r + size, o_c:o_c + size])
        local_seed = (seed[0] - o_r, seed[1] - o_c)
        filled, depth = depression_hierarchy(field)
        component = depression_component(depth, local_seed)
        record = {"size": size, "window_km": size * spacing_m / 1000.0,
                  "window_origin_rc": [int(o_r), int(o_c)],
                  "seed_rc": [int(local_seed[0]), int(local_seed[1])]}
        if component is None:
            record.update(closed_basin=False, closed_basin_by_hypsometry=False,
                          basin_cells=0, basin_area_m2=0.0,
                          bed_min_m=float(field[local_seed]), spill_level_m=float("nan"),
                          rim_clearance_cells=None, suspect_window_truncation=True)
        else:
            edge = basin_reaches_window_edge(component, contact_margin_cells)
            # `closed_basin` here means "usable under the declared margin". The weaker
            # hypsometry verdict is kept beside it under its own name so a reader can see
            # exactly where the two disagree -- that disagreement is the finding.
            record.update(closed_basin=not edge["suspect_window_truncation"],
                          closed_basin_by_hypsometry=
                              not edge["touches_border_by_hypsometry_ring_2"],
                          basin_cells=int(component.sum()),
                          basin_area_m2=float(component.sum()) * spacing_m ** 2,
                          bed_min_m=float(field[component].min()),
                          spill_level_m=float(filled[component].max()),
                          rim_clearance_cells=edge["rim_clearance_cells"],
                          touches_border_by_hypsometry_ring_2=
                              edge["touches_border_by_hypsometry_ring_2"],
                          suspect_window_truncation=edge["suspect_window_truncation"])
        record["naive_spill_level_m"] = (record["spill_level_m"]
                                         if math.isfinite(record["spill_level_m"]) else None)
        records.append(record)

    accepted = [record for record in records if not record["suspect_window_truncation"]]
    converged = None
    level_spread = None
    area_spread = None
    if accepted:
        largest, runner_up = (accepted[-1], accepted[-2]) if len(accepted) > 1 else (accepted[-1], None)
        if runner_up is not None and runner_up["basin_area_m2"] > 0:
            level_spread = abs(largest["spill_level_m"] - runner_up["spill_level_m"])
            area_spread = abs(largest["basin_area_m2"] - runner_up["basin_area_m2"])
            relief = largest["spill_level_m"] - largest["bed_min_m"]
            converged = bool(relief > 0 and level_spread / relief <= 1e-3
                             and area_spread / largest["basin_area_m2"] <= 1e-3)
    return {
        "records": records,
        "sizes": ordered,
        "contact_margin_cells": int(contact_margin_cells),
        "suspect_sizes": [record["size"] for record in records if record["suspect_window_truncation"]],
        "hypsometry_only_says_closed": [
            record["size"] for record in records
            if record.get("closed_basin_by_hypsometry") and record["suspect_window_truncation"]],
        "accepted_sizes": [record["size"] for record in accepted],
        "first_accepted_size": accepted[0]["size"] if accepted else None,
        "converged_between_largest_accepted": converged,
        "level_spread_m_between_largest_accepted": level_spread,
        "area_spread_m2_between_largest_accepted": area_spread,
        "placement_rule": ("centre on the seed cell, then clamp inside the page: "
                           "origin = min(max(seed - size//2, 0), extent - size); enlarging adds "
                           "terrain around the basin and never moves the seed"),
    }


def truncation_cost(family):
    """How much a truncating window under-reports the spill level.

    Returns one row per suspect window against the largest accepted window, which is
    the only quantity this module is willing to call a cost.
    """
    accepted = [record for record in family["records"]
                if not record["suspect_window_truncation"]]
    if not accepted:
        return {"rows": [], "accepted_size": None,
                "reason": "no window in the family clears the declared rim margin; "
                          "no spill level may be reported"}
    reference = accepted[-1]
    rows = []
    for record in family["records"]:
        if not record["suspect_window_truncation"]:
            continue
        if record["spill_level_m"] is None or not math.isfinite(record["spill_level_m"]):
            rows.append({"size": record["size"], "window_km": record["window_km"],
                         "reported_spill_level_m": None,
                         "under_report_m": None,
                         "note": "the truncating window does not close a basin at all, so it "
                                 "reports nothing -- which is the correct outcome, not a gap"})
            continue
        under_report = float(reference["spill_level_m"] - record["spill_level_m"])
        rows.append({"size": record["size"], "window_km": record["window_km"],
                     "reported_spill_level_m": record["spill_level_m"],
                     "accepted_spill_level_m": reference["spill_level_m"],
                     "under_report_m": under_report,
                     "reported_basin_area_km2": record["basin_area_m2"] / 1e6,
                     "accepted_basin_area_km2": reference["basin_area_m2"] / 1e6,
                     "rim_clearance_cells": record["rim_clearance_cells"],
                     "verdict": ("harmless_on_this_terrain" if under_report == 0.0
                                 else "under_reported"),
                     "note": ("the rim is inside the untrusted band, so this number must not be "
                              "reported even when it happens to match: agreement with the "
                              "accepted window is a coincidence on this terrain, not "
                              "evidence that the window was big enough")})
    return {"rows": rows, "accepted_size": reference["size"],
            "accepted_spill_level_m": reference["spill_level_m"],
            "accepted_basin_area_km2": reference["basin_area_m2"] / 1e6}


# --------------------------------------------------------------------------- #
# 5. point resolution with reason codes
# --------------------------------------------------------------------------- #
def resolve_point(pages, native_xz, border_band_cells=BORDER_BAND_CELLS,
                  sea_level_m=None):
    """One world point, every covering page, an explicit verdict.

    The window edge is never an accepted answer and never an outlet: a point that is
    only covered inside a page's border band is refused as `unresolved_border` rather
    than reported with the band's value.
    """
    x, z = (int(value) for value in np.asarray(native_xz, np.int64).reshape(-1))
    band = int(border_band_cells)
    candidates = []
    for entry in pages:
        if isinstance(entry, dict):
            key, array, origin_native = str(entry["key"]), entry["page"], entry["native_origin"]
        else:
            key, array, origin_native = entry
        array = _page_array(array)
        origin = _native_origin(origin_native)
        column, row = x - origin[0], z - origin[1]
        if not (0 <= row < array.shape[0] and 0 <= column < array.shape[1]):
            continue
        distance = int(min(row, column,
                           array.shape[0] - 1 - row, array.shape[1] - 1 - column))
        candidates.append({"page": key, "elevation_m": float(array[row, column]),
                           "border_distance_cells": distance,
                           "supplied": bool(distance >= band)})

    evidence = {"native_xz": [x, z], "border_band_cells": band, "candidates": candidates}
    if not candidates:
        return {**evidence, "resolved": False, "reason": REASON_OUT_OF_TILE,
                "value_m": None,
                "explanation": "no loaded page covers this native cell; it is outside the tile "
                               "set, not zero and not extrapolated"}
    accepted = [item for item in candidates if item["supplied"]]
    if not accepted:
        return {**evidence, "resolved": False, "reason": REASON_UNRESOLVED_BORDER,
                "value_m": None,
                "explanation": ("every covering page has this cell inside its border band, so the "
                                "cell's value depends on which window asked; reporting it would "
                                "launder a border artefact as terrain")}
    values = sorted({item["elevation_m"] for item in accepted})
    if len(values) > 1:
        return {**evidence, "resolved": False, "reason": REASON_DISAGREEMENT,
                "value_m": None, "disagreeing_values_m": values,
                "explanation": ("two pages with sufficient clearance disagree; that contradicts the "
                                "measured interior equality and must be investigated, not averaged")}
    value = values[0]
    if sea_level_m is not None and value < float(sea_level_m):
        return {**evidence, "resolved": True, "reason": REASON_OCEAN, "value_m": value,
                "explanation": "below the declared sea datum: an outlet, not a rim"}
    return {**evidence, "resolved": True, "reason": REASON_CLOSED_BASIN, "value_m": value,
            "explanation": "covered with at least the declared clearance by every agreeing page"}


# --------------------------------------------------------------------------- #
# 6. digest for a cold read
# --------------------------------------------------------------------------- #
DIGEST_SCHEMA = "terragenesis-cross-region-digest-v1"


def derive_sub_seed(world_seed, purpose):
    """The project's declared sub-seed derivation, spelled out so a cold read can redo it."""
    payload = json.dumps(["terragenesis-world-noise-v1", int(world_seed), str(purpose)],
                         sort_keys=True)
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:4], "big")


def build_digest(*, world_seed, pages, spacing_m, border_band_cells=BORDER_BAND_CELLS,
                 generation_config=None, source_paths=(), climate=None, extra=None):
    """Everything a fresh process needs to recompute, and nothing it has to guess.

    `pages` entries are `(key, page_array, native_origin, metadata)`. The elevation
    bytes of every page are hashed, so a cold read can reject a substituted file
    instead of silently recomputing on a different world.
    """
    import hashlib as _hashlib
    from pathlib import Path

    records = []
    for key, array, origin_native, metadata in pages:
        array = _page_array(array)
        origin = _native_origin(origin_native)
        records.append({"key": str(key), "shape": list(array.shape),
                        "native_origin": list(origin),
                        "world_origin_xz_m": [origin[0] * spacing_m, origin[1] * spacing_m],
                        "elevation_sha256": _hashlib.sha256(
                            np.ascontiguousarray(array, np.float64).tobytes()).hexdigest(),
                        "elevation_min_m": float(array.min()),
                        "elevation_max_m": float(array.max()),
                        "metadata": metadata})
    files = {}
    for path in source_paths:
        target = Path(path)
        files[target.name if target.name else str(target)] = {
            "path": str(target).replace("\\", "/"),
            "bytes": target.stat().st_size,
            "sha256": _file_sha256(target)}
    digest = {
        "schema": DIGEST_SCHEMA,
        "world_seed": int(world_seed),
        "spacing_m": float(spacing_m),
        "border_band_cells": int(border_band_cells),
        "pages": records,
        "generation_config": generation_config,
        "source_files": files,
        "climate": climate or {"sub_seeds": {
            purpose: derive_sub_seed(world_seed, purpose)
            for purpose in ("climate", "rainfall", "light")},
            "derivation": ("int.from_bytes(sha256(json.dumps([\"terragenesis-world-noise-v1\", "
                           "world_seed, purpose], sort_keys=True)).digest()[:4], \"big\")"),
            "status": ("sub-seeds only: no noise-driven climate field is present in these pages, and "
                       "the pages were generated with `with_climate=False`")},
        "extra": extra or {},
    }
    digest["digest_sha256"] = identity({}, digest)
    return digest


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_digest(digest, *, pages, spacing_m):
    """Recheck a digest against freshly loaded pages; every mismatch is named."""
    import hashlib as _hashlib

    problems = []
    if digest.get("schema") != DIGEST_SCHEMA:
        problems.append("schema mismatch: %r" % (digest.get("schema"),))
    if float(digest.get("spacing_m", -1.)) != float(spacing_m):
        problems.append("spacing mismatch: %r vs %r" % (digest.get("spacing_m"), spacing_m))
    recorded = {record["key"]: record for record in digest.get("pages", [])}
    supplied = []
    for key, array, origin_native, _metadata in pages:
        array = _page_array(array)
        origin = _native_origin(origin_native)
        supplied.append(str(key))
        entry = recorded.get(str(key))
        if entry is None:
            problems.append("page %r is not in the digest" % (str(key),))
            continue
        if list(array.shape) != list(entry["shape"]):
            problems.append("page %r shape %s != recorded %s" % (
                str(key), list(array.shape), entry["shape"]))
        if list(origin) != list(entry["native_origin"]):
            problems.append("page %r origin %s != recorded %s" % (
                str(key), list(origin), entry["native_origin"]))
        actual = _hashlib.sha256(
            np.ascontiguousarray(array, np.float64).tobytes()).hexdigest()
        if actual != entry["elevation_sha256"]:
            problems.append("page %r elevation sha256 %s != recorded %s" % (
                str(key), actual, entry["elevation_sha256"]))
    missing = sorted(set(recorded) - set(supplied))
    if missing:
        problems.append("digest lists pages that were not supplied: %s" % (missing,))
    recomputed = identity({}, {key: value for key, value in digest.items()
                              if key != "digest_sha256"})
    if recomputed != digest.get("digest_sha256"):
        problems.append("digest body no longer hashes to digest_sha256")
    return {"verified": not problems, "problems": problems,
            "digest_sha256": digest.get("digest_sha256"),
            "recomputed_sha256": recomputed,
            "pages_checked": len(supplied)}
