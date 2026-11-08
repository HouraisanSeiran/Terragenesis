"""Read-only on-demand river consistency auditor.

This is the referee for the infinite-world river work: it measures whether an
arbitrary world coordinate can be planned at all, and whether the products two
overlapping windows produce for the same world coordinates agree.

It generates nothing that is published, certifies nothing and writes no
verification evidence. It only counts and compares.

What it checks
--------------
1. acceptance  - how many macro cells plan successfully, and every rejection
                 reason (verbatim, so a new reason can never hide as "other")
2. determinism - the same cell planned twice must give one identity
3. cross-window agreement on the physical overlap between neighbouring cells,
   split into: shared base condition, published height, flow direction,
   river mask, and PHYSICAL OUTLET ownership (which outlet world point a cell
   drains to). Outlet is used on purpose, not the owner_domain_id integer:
   `general` mode numbers domains by `enumerate(sorted(selected_terminals))`,
   so the same physical domain gets a different integer in every window and
   comparing those integers over-counts disagreement (pure label noise -- it
   once reported 2533 "owner disagreements" that mean nothing)
4. load order - the same set of cells planned in shuffled order must give the
   same products

Axis note (this bit us once already): support arrays are (z-rows, x-columns)
and adjacent cells are 320 km apart while a support is 1280 km wide, so two
neighbours share 3/4 of a support. A cell differing in z shifts ROWS; a cell
differing in x shifts COLUMNS. Comparing along the wrong axis produces absurd
numbers (it once reported the shared base condition differing by 4635 m, which
cannot happen because that field is a pure function of world coordinates).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hydrology_planning import (  # noqa: E402
    PlanningConfig,
    PlanningError,
    coarse_condition_field,
    plan_canonical_support,
)
from terrain_pipeline.surface_rivers.metric_domain_closure import (  # noqa: E402
    ClosureRegion,
    clear_cache,
    outlet_at,
)

SCHEMA = "river-on-demand-consistency-v2"
CONTRACT_SCHEMA = "river-on-demand-contract-v1"


# ---------------------------------------------------------------------------
# Contract engine: measure the window-independent closure contract itself.
#
# The planner engine below measures the FROZEN bounded product
# (`plan_canonical_support`), whose per-window candidate set makes its
# `outlet_coverage_mismatch_pairs` and `ocean_mismatch_pairs` window-dependent by
# construction -- no amount of work on the new module can drive those to zero,
# and pretending otherwise would be exactly the kind of silent widening the
# contract forbids. The contract engine therefore measures the thing the
# contract actually promises: outlet, ocean and eligibility as
# `f(seed, world coordinate)`, via the world-anchored tiles of
# `metric_domain_closure`, and reports every refusal verbatim.
# ---------------------------------------------------------------------------

REASON_ORDER = ("ocean", "coastal", "closed_basin", "unresolved_border", "out_of_tile")


def reason_counts(reasons):
    """Verbatim reason tally in a fixed order (a new reason cannot hide).

    Known reasons keep a fixed slot so a zero is explicit, and any label the
    vocabulary does not know is appended as its own key rather than dropped --
    dropping it is exactly how a new refusal reason could hide as "nothing".
    """
    values, counts = np.unique(np.asarray(reasons, dtype=object).astype(str), return_counts=True)
    tally = {str(value): int(count) for value, count in zip(values, counts)}
    ordered = {name: tally.pop(name, 0) for name in REASON_ORDER}
    ordered.update({name: tally[name] for name in sorted(tally)})
    return ordered


def _tile_keys(radius, config):
    """Core-tile keys whose built extent covers the macro sample [-r, r]^2."""
    core_span_m = 4.0 * config.macro_span_m
    reach = (radius + 0.5) * config.macro_span_m
    first, last = int(np.floor(-reach / core_span_m)), int(np.floor(reach / core_span_m))
    return [(row, column) for row in range(first, last + 1) for column in range(first, last + 1)]


def contract_fields(region, xs, zs):
    """Vectorised per-point contract answer of ONE anchoring.

    Returns `(reason, outlet_x_m, outlet_z_m, ocean)`, of which the outlet is NaN
    wherever the anchoring declines (sea cells included: a sea cell is resolved
    yet has no outlet of its own).
    """
    rows, columns = region.shape
    row, column = region._node(xs, zs)
    row = np.asarray(row, np.int64).reshape(-1)
    column = np.asarray(column, np.int64).reshape(-1)
    inside = (row >= 0) & (row < rows) & (column >= 0) & (column < columns)
    reason = np.full(row.size, "out_of_tile", dtype=object)
    outlet_x = np.full(row.size, np.nan, np.float64)
    outlet_z = np.full(row.size, np.nan, np.float64)
    ocean = np.zeros(row.size, bool)
    if inside.any():
        r, c = row[inside], column[inside]
        sea = region.ocean[r, c]
        unresolved = region.unresolved[r, c]
        terminal_flat = region.terminal[r, c]
        terminal_sea = region.ocean.reshape(-1)[terminal_flat]
        ocean[inside] = sea
        reason[inside] = np.where(
            unresolved, "unresolved_border",
            np.where(sea, "ocean",
                     np.where(terminal_sea, "coastal", "closed_basin")))
        answered = ~unresolved & ~sea
        terminal_row, terminal_column = np.divmod(terminal_flat, columns)
        outlet_x[inside] = np.where(
            answered, region.origin_x_m + terminal_column * region.spacing_m, np.nan)
        outlet_z[inside] = np.where(
            answered, region.origin_z_m + terminal_row * region.spacing_m, np.nan)
    return reason, outlet_x, outlet_z, ocean


def eligibility_fields(region, xs, zs):
    """Per-point eligibility of ONE anchoring: ``(accepted, owner_x, owner_z)``.

    The owner is the outlet **world coordinate** of the domain the point belongs
    to (the domain's identity), NaN and `False` wherever the anchoring does not
    accept the point. This is the eligibility half of the contract; the
    outlet/ocean half is `contract_fields`.
    """
    row, column = region._node(xs, zs)
    row = np.asarray(row, np.int64).reshape(-1)
    column = np.asarray(column, np.int64).reshape(-1)
    inside = (row >= 0) & (row < region.shape[0]) & (column >= 0) & (column < region.shape[1])
    accepted = np.zeros(row.size, bool)
    owner_x = np.full(row.size, np.nan, np.float64)
    owner_z = np.full(row.size, np.nan, np.float64)
    if inside.any():
        r, c = row[inside], column[inside]
        accepted[inside] = region.accepted[r, c]
        owner_x[inside] = region.owner_outlet[r, c, 0]
        owner_z[inside] = region.owner_outlet[r, c, 1]
    return accepted, owner_x, owner_z


def _overlap_grid(left, right, spacing_m):
    """Node-aligned world grid of the shared physical extent of two tiles."""
    x0 = max(left.origin_x_m, right.origin_x_m)
    x1 = min(left.origin_x_m + (left.shape[1] - 1) * spacing_m,
             right.origin_x_m + (right.shape[1] - 1) * spacing_m)
    z0 = max(left.origin_z_m, right.origin_z_m)
    z1 = min(left.origin_z_m + (left.shape[0] - 1) * spacing_m,
             right.origin_z_m + (right.shape[0] - 1) * spacing_m)
    if x1 < x0 or z1 < z0:
        return None
    xs = np.arange(x0, x1 + 1e-6, spacing_m)
    zs = np.arange(z0, z1 + 1e-6, spacing_m)
    return np.meshgrid(xs, zs)


def compare_tile_pair(left, right, left_cell, right_cell, spacing_m, step=4):
    """Compare two tiles' contract answers over their shared physical extent.

    A disagreement where BOTH anchorings answer is a contract violation and must
    be zero; a point one anchoring refuses is honest refusal and is counted, not
    treated as a conflict. Sampling is strided (`step`) because a tile has no
    window-relative quantities left to miss between adjacent nodes.
    """
    grid = _overlap_grid(left, right, spacing_m)
    if grid is None:
        return {"comparable": False, "reason": "tiles do not overlap"}
    xs, zs = grid
    xs, zs = xs[::step, ::step], zs[::step, ::step]
    lreason, lox, loz, locean = contract_fields(left, xs.reshape(-1), zs.reshape(-1))
    rreason, rox, roz, rocean = contract_fields(right, xs.reshape(-1), zs.reshape(-1))
    both_inside = (lreason != "out_of_tile") & (rreason != "out_of_tile")
    l_answered = (lreason != "out_of_tile") & (lreason != "unresolved_border")
    r_answered = (rreason != "out_of_tile") & (rreason != "unresolved_border")
    l_outlet = np.isfinite(lox)
    r_outlet = np.isfinite(rox)
    both_outlet = l_outlet & r_outlet
    # The gate: a disagreement where BOTH anchorings answer (neither declined).
    # A point only one side answers is honest refusal, not a conflict.
    both_confident = both_inside & l_answered & r_answered
    lacc, low_x, low_z = eligibility_fields(left, xs.reshape(-1), zs.reshape(-1))
    racc, row_x, row_z = eligibility_fields(right, xs.reshape(-1), zs.reshape(-1))
    both_accepted = both_inside & lacc & racc
    l_unresolved = lreason == "unresolved_border"
    r_unresolved = rreason == "unresolved_border"
    # Delivery face. The face a caller actually gets is each point's CORE tile
    # (`_region_for_point`); a core cell is never refused for lack of margin. So
    # where BOTH anchorings hold the point in their core, both are obliged to
    # answer, and any one-sided acceptance there is a real coverage mismatch on
    # the delivery face -- the quantity p3.1 must drive to zero (the pre-p3
    # baseline was 101/101 pairs disagreeing). Margin-only one-sidedness is honest
    # conservative refusal and is deliberately NOT counted here.
    lrow, lcolumn = left._node(xs.reshape(-1), zs.reshape(-1))
    rrow, rcolumn = right._node(xs.reshape(-1), zs.reshape(-1))
    lrow = np.asarray(lrow, np.int64).reshape(-1)
    lcolumn = np.asarray(lcolumn, np.int64).reshape(-1)
    rrow = np.asarray(rrow, np.int64).reshape(-1)
    rcolumn = np.asarray(rcolumn, np.int64).reshape(-1)
    both_core = np.zeros(both_inside.size, bool)
    if both_inside.any():
        both_core[both_inside] = (
            left.in_core[lrow[both_inside], lcolumn[both_inside]]
            & right.in_core[rrow[both_inside], rcolumn[both_inside]])
    l_owns = np.isfinite(low_x)
    r_owns = np.isfinite(row_x)
    return {
        "comparable": True,
        "left_tile": [int(left_cell[0]), int(left_cell[1])],
        "right_tile": [int(right_cell[0]), int(right_cell[1])],
        "shared_points": int(both_inside.sum()),
        "outlet_both_answered": int((both_inside & both_outlet).sum()),
        "outlet_disagreements": int(np.count_nonzero(
            both_inside & both_outlet & ((lox != rox) | (loz != roz)))),
        "outlet_one_sided": int(np.count_nonzero(both_inside & (l_outlet ^ r_outlet))),
        "ocean_mask_disagreements": int(np.count_nonzero(both_inside & (locean != rocean))),
        "answered_one_sided": int(np.count_nonzero(both_inside & (l_answered ^ r_answered))),
        "confident_ocean_mismatches": int(np.count_nonzero(both_confident & (locean != rocean))),
        "confident_reason_mismatches": int(np.count_nonzero(both_confident & (lreason != rreason))),
        "dominant_reason_disagreements": int(np.count_nonzero(
            both_inside & (lreason != rreason) & ~(l_answered ^ r_answered))),
        # eligibility (the second half of the contract)
        "accepted_both_points": int(both_accepted.sum()),
        "eligibility_conflicts": int(np.count_nonzero(
            both_accepted & ((low_x != row_x) | (low_z != row_z)))),
        "eligibility_one_sided": int(np.count_nonzero(both_inside & (lacc ^ racc))),
        "accepted_while_unresolved_points": int(np.count_nonzero(
            both_inside & ((lacc & l_unresolved) | (racc & r_unresolved)))),
        "accepted_while_ocean_points": int(np.count_nonzero(
            both_inside & ((lacc & locean) | (racc & rocean)))),
        # delivery-face (both cores) coverage, the p3.1 acceptance quantity
        "core_points": int(both_core.sum()),
        "core_ownership_one_sided_points": int(np.count_nonzero(both_core & (l_owns ^ r_owns))),
        "core_eligibility_one_sided_points": int(np.count_nonzero(both_core & (lacc ^ racc))),
        "core_owner_mismatch_points": int(np.count_nonzero(
            both_core & lacc & racc & ((low_x != row_x) | (low_z != row_z)))),
        "left_reason_counts": reason_counts(lreason),
        "right_reason_counts": reason_counts(rreason),
    }


def audit_contract(seed, radius, config=None, step=4):
    """Measure the window-independent closure contract directly."""
    config = config or PlanningConfig()
    config.validate()
    spacing_m = config.macro_span_m / config.samples_per_span
    started = time.perf_counter()
    clear_cache()
    keys = _tile_keys(radius, config)
    tiles = {key: ClosureRegion(seed, config, *key) for key in keys}

    key_set = set(keys)
    pair_records = []
    for (row, column) in sorted(keys):
        for other in ((row, column + 1), (row + 1, column)):
            if other in key_set:
                pair_records.append(compare_tile_pair(
                    tiles[(row, column)], tiles[other], (row, column), other, spacing_m, step))
    comparable = [record for record in pair_records if record["comparable"]]

    core_records = []
    for key, region in sorted(tiles.items()):
        margin, core = region.margin, region.core_cells
        rows, columns = np.meshgrid(np.arange(margin, margin + core + 1),
                                    np.arange(margin, margin + core + 1), indexing="ij")
        xs = region.origin_x_m + columns.reshape(-1) * spacing_m
        zs = region.origin_z_m + rows.reshape(-1) * spacing_m
        reason, outlet_x, _, ocean = contract_fields(region, xs, zs)
        answered = np.isfinite(outlet_x) | ocean
        core_records.append({
            "tile": [int(key[0]), int(key[1])],
            "core_points": int(reason.size),
            "reason_counts": reason_counts(reason),
            "core_refused": int(np.count_nonzero(
                (reason == "unresolved_border") | (reason == "out_of_tile"))),
            "core_answered": int(answered.sum()),
        })

    # Purity: the same world-anchored tile rebuilt from scratch must be identical.
    sample_key = sorted(keys)[len(keys) // 2]
    first = tiles[sample_key]
    clear_cache()
    again = ClosureRegion(seed, config, *sample_key)
    purity = bool(np.array_equal(first.height, again.height)
                  and np.array_equal(first.ocean, again.ocean)
                  and np.array_equal(first.terminal, again.terminal)
                  and np.array_equal(first.unresolved, again.unresolved))

    # Load order: building the SAME tiles in a shuffled order, and answering the
    # SAME points in a shuffled order, must not change a single bit. The module
    # caches tiles by key, so a load-order dependence would show up as a cache
    # miss/hit difference or as an insertion-order effect. Everything is compared
    # against the sorted-order build above.
    shuffler = np.random.default_rng(seed)
    shuffled = list(keys)
    shuffler.shuffle(shuffled)
    clear_cache()
    order_tiles = {}
    for key in shuffled:
        order_tiles[key] = ClosureRegion(seed, config, *key)
    tile_order_mismatches = int(sum(
        1 for key in keys
        if not (np.array_equal(tiles[key].height, order_tiles[key].height)
                and np.array_equal(tiles[key].ocean, order_tiles[key].ocean)
                and np.array_equal(tiles[key].terminal, order_tiles[key].terminal)
                and np.array_equal(tiles[key].unresolved, order_tiles[key].unresolved)
                and np.array_equal(tiles[key].accepted, order_tiles[key].accepted)
                and np.array_equal(np.nan_to_num(tiles[key].owner_outlet),
                                   np.nan_to_num(order_tiles[key].owner_outlet)))))

    # A second, independent route: the module-level point API, two orders, cache
    # cleared between them, compared as sorted lists so only the answers matter.
    probe_points = [(region.origin_x_m + region.margin * spacing_m,
                     region.origin_z_m + region.margin * spacing_m)
                    for region in tiles.values()]
    probe_points += [p for p in probe_points]
    shuffler2 = np.random.default_rng(seed + 1)
    shuffled_points = list(probe_points)
    shuffler2.shuffle(shuffled_points)
    clear_cache()
    forward = [outlet_at(seed, x, z, config) for x, z in probe_points]
    clear_cache()
    backward = [outlet_at(seed, x, z, config) for x, z in shuffled_points]
    lookup = {point: answer for point, answer in zip(probe_points, forward)}
    point_order_mismatches = int(sum(
        1 for point, answer in zip(shuffled_points, backward)
        if answer != lookup[point]))

    load_order = {
        "tiles_compared": len(keys),
        "tile_order_mismatches": tile_order_mismatches,
        "points_compared": len(probe_points),
        "point_order_mismatches": point_order_mismatches,
    }

    return {
        "schema": CONTRACT_SCHEMA,
        "engine": "contract",
        "seed": int(seed),
        "radius": int(radius),
        "step": int(step),
        "macro_span_m": float(config.macro_span_m),
        "spacing_m": float(spacing_m),
        "tiles": [[int(row), int(column)] for row, column in sorted(keys)],
        "seconds": round(time.perf_counter() - started, 3),
        "tile_rebuild_is_bit_identical": purity,
        "adjacent_tile_pairs": len(comparable),
        "contract": {
            "outlet_disagreement_pairs": int(sum(
                1 for record in comparable if record["outlet_disagreements"] > 0)),
            "worst_outlet_disagreements": max(
                [record["outlet_disagreements"] for record in comparable] or [0]),
            "ocean_mismatch_pairs": int(sum(
                1 for record in comparable if record["ocean_mask_disagreements"] > 0)),
            "worst_ocean_disagreements": max(
                [record["ocean_mask_disagreements"] for record in comparable] or [0]),
            "one_sided_refusal_points": int(sum(
                record["answered_one_sided"] for record in comparable)),
            "confident_ocean_mismatch_points": int(sum(
                record["confident_ocean_mismatches"] for record in comparable)),
            "confident_reason_mismatch_points": int(sum(
                record["confident_reason_mismatches"] for record in comparable)),
            "dominant_reason_conflict_points": int(sum(
                record["dominant_reason_disagreements"] for record in comparable)),
            "outlet_both_answered_points": int(sum(
                record["outlet_both_answered"] for record in comparable)),
            "eligibility_conflict_points": int(sum(
                record["eligibility_conflicts"] for record in comparable)),
            "eligibility_one_sided_points": int(sum(
                record["eligibility_one_sided"] for record in comparable)),
            "accepted_while_unresolved_points": int(sum(
                record["accepted_while_unresolved_points"] for record in comparable)),
            "accepted_while_ocean_points": int(sum(
                record["accepted_while_ocean_points"] for record in comparable)),
            "accepted_both_points": int(sum(
                record["accepted_both_points"] for record in comparable)),
            # ------------------------------------------------------------------
            # Delivery face (both anchorings hold the point in their core). This
            # is where p3.1 is accepted or rejected: the pre-p3 baseline was
            # `outlet_coverage_mismatch_pairs = 101/101`, and the contract's
            # promise is that the core tile decides a point's territory and
            # outlet, so the delivery face must disagree nowhere.
            # ------------------------------------------------------------------
            "delivery_core_points": int(sum(
                record["core_points"] for record in comparable)),
            "delivery_core_ownership_mismatch_pairs": int(sum(
                1 for record in comparable if record["core_ownership_one_sided_points"] > 0)),
            "worst_core_ownership_one_sided_points": max(
                [record["core_ownership_one_sided_points"] for record in comparable] or [0]),
            "delivery_core_ownership_one_sided_points": int(sum(
                record["core_ownership_one_sided_points"] for record in comparable)),
            "delivery_core_eligibility_one_sided_points": int(sum(
                record["core_eligibility_one_sided_points"] for record in comparable)),
            "delivery_core_owner_mismatch_points": int(sum(
                record["core_owner_mismatch_points"] for record in comparable)),
        },
        "core": {
            "tiles_measured": len(core_records),
            "core_points_per_tile": core_records[0]["core_points"],
            "worst_core_refused": max(
                [record["core_refused"] for record in core_records] or [0]),
            "total_core_refused": int(sum(record["core_refused"] for record in core_records)),
            "reason_totals": {
                name: int(sum(record["reason_counts"][name] for record in core_records))
                for name in REASON_ORDER},
        },
        "pairs": pair_records,
        "cores": core_records,
        "load_order": load_order,
        "limitations": [
            "plane sample only; no claim about the whole infinite world",
            "measures the world-anchored contract, NOT the frozen bounded planner "
            "(use --engine planner for that; its coverage/ocean window dependence "
            "is a property of the frozen product, not a defect of this contract)",
            "one_sided_refusal_points is honest refusal (an anchoring declined), not "
            "a conflict; only outlet_disagreement_pairs and ocean mismatch count as "
            "contract violations",
        ],
        "contract_certified": False,
    }


def plan_cell(seed, cell_x, cell_z, config):
    """Plan one macro cell, returning (product, rejection_reason).

    PlanningError is the planner's documented refusal. Anything else is an
    UNDOCUMENTED failure mode and is recorded verbatim rather than allowed to
    kill the whole audit: an exception nobody expected is a finding, not a
    reason to lose the other 120 cells. (A --radius 5 run once died at exit 1
    with no traceback in the captured log for exactly this reason.)
    """
    try:
        return plan_canonical_support(seed, cell_x, cell_z, config), None
    except PlanningError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 - undocumented failure is data
        return None, f"UNDOCUMENTED {type(exc).__name__}: {exc}"


def acceptance(seed, cells, config):
    accepted, rejected = {}, {}
    started = time.perf_counter()
    for cell_x, cell_z in cells:
        product, reason = plan_cell(seed, cell_x, cell_z, config)
        if product is None:
            rejected[(cell_x, cell_z)] = reason
        else:
            accepted[(cell_x, cell_z)] = product
    return accepted, rejected, time.perf_counter() - started


def _overlap(left, right, axis):
    """Return (left_slice, right_slice) for the shared physical area.

    The right cell is always +1 of the left cell along `axis`. Its window
    origin therefore sits one macro span further along that axis, so at the same
    world coordinate the LEFT product's index is `shift` higher than the
    RIGHT product's. Hence left takes array[shift:], right takes [:shared] --
    for BOTH axes. Getting this backwards on one axis silently compares two
    regions 640 km apart and reports the base condition field disagreeing by
    thousands of metres, which is impossible because that field is a pure
    function of world coordinates. `condition_max_abs_diff_m` must be 0 for
    every pair; anything else means this function is wrong.
    """
    shift = int(round(left["config"]["macro_span_m"] / left["spacing_m"]))
    size = left["height_m"].shape[axis]
    shared = size - shift
    if shared <= 0:
        return None
    return (slice(shift, size), slice(0, shared))


def _flow_vectors(receiver, shape):
    """Row/column step of every cell's steepest receiver, -2 when no receiver.

    Directions are translation invariant, so two windows covering the same world
    cells can be compared without mapping either one's flat indices into the
    other's frame. That mapping is easy to get wrong and produced nonsense when
    it was attempted (a flat-index mapping reported disagreement on cells whose
    receivers both pointed outside the shared window, which is not evidence of
    anything).
    """
    flat = np.asarray(receiver, dtype=np.int64).reshape(shape).ravel()
    rows, columns = np.divmod(np.arange(flat.size), shape[1])
    step_row = np.full(flat.size, -2, np.int64)
    step_column = np.full(flat.size, -2, np.int64)
    valid = flat >= 0
    target_row, target_column = np.divmod(flat, shape[1])
    step_row[valid] = target_row[valid] - rows[valid]
    step_column[valid] = target_column[valid] - columns[valid]
    return (step_row.reshape(shape), step_column.reshape(shape))


def _outlet_fields(product):
    """Per-cell physical outlet world coordinates, NaN where the cell is not owned.

    A catchment carries `terminal_world_xz_m`, which is a world coordinate and
    therefore means the same thing in every window. This is what makes outlet
    ownership comparable across windows while owner_domain_id is not.
    """
    shape = product["height_m"].shape
    outlet_x = np.full(shape, np.nan, np.float64)
    outlet_z = np.full(shape, np.nan, np.float64)
    index = np.asarray(product["catchment_index"])
    for catchment_id in np.unique(index[index >= 0]):
        catchment = product["catchments"][int(catchment_id)]
        pick = index == catchment_id
        outlet_x[pick] = float(catchment["terminal_world_xz_m"][0])
        outlet_z[pick] = float(catchment["terminal_world_xz_m"][1])
    return outlet_x, outlet_z


def compare_pair(left, right, left_cell, right_cell):
    """Compare two neighbouring products over their shared physical area."""
    axis = 0 if left_cell[0] == right_cell[0] else 1
    window = _overlap(left, right, axis)
    if window is None:
        return {"comparable": False, "reason": "supports do not overlap"}
    left_slice, right_slice = window

    def take(arrays, slicer):
        return [array[slicer, :] if axis == 0 else array[:, slicer] for array in arrays]

    lh, lo, lom, lm, lc = take(
        [left["height_m"], left["original_height_m"], left["ocean_mask"],
         left["river_mask"], left["owner_domain_id"]], left_slice)
    rh, ro, rom, rm, rc = take(
        [right["height_m"], right["original_height_m"], right["ocean_mask"],
         right["river_mask"], right["owner_domain_id"]], right_slice)
    left_dr, left_dc = take(list(_flow_vectors(left["receiver"], left["height_m"].shape)), left_slice)
    right_dr, right_dc = take(list(_flow_vectors(right["receiver"], right["height_m"].shape)), right_slice)
    direction_disagreement = int(np.count_nonzero((left_dr != right_dr) | (left_dc != right_dc)))
    lox, loz = take(list(_outlet_fields(left)), left_slice)
    rox, roz = take(list(_outlet_fields(right)), right_slice)
    left_owned, right_owned = np.isfinite(lox), np.isfinite(rox)
    both_owned = left_owned & right_owned
    same_outlet = both_owned & np.isclose(lox, rox) & np.isclose(loz, roz)

    both = int(np.count_nonzero(lm & rm))
    either = int(np.count_nonzero(lm | rm))
    return {
        "comparable": True,
        "axis": "z" if axis == 0 else "x",
        "shared_cells": int(lh.size),
        "condition_max_abs_diff_m": float(np.abs(lo - ro).max()),
        "ocean_mask_disagreements": int(np.count_nonzero(lom != rom)),
        "height_max_abs_diff_m": float(np.abs(lh - rh).max()),
        "height_mean_abs_diff_m": float(np.abs(lh - rh).mean()),
        "receiver_disagreements": direction_disagreement,
        "river_left_cells": int(lm.sum()),
        "river_right_cells": int(rm.sum()),
        "river_shared_cells": both,
        "river_union_cells": either,
        "river_agreement": (both / either) if either else None,
        "owner_label_disagreements": int(np.count_nonzero(lc != rc)),
        "outlet_left_owned": int(left_owned.sum()),
        "outlet_right_owned": int(right_owned.sum()),
        "outlet_both_owned": int(both_owned.sum()),
        "outlet_disagreements": int(np.count_nonzero(both_owned & ~same_outlet)),
        "outlet_agreement": (float(same_outlet.sum()) / float(both_owned.sum())) if both_owned.any() else None,
        "left_domain_count": int(len(left["domains"])),
        "right_domain_count": int(len(right["domains"])),
    }


def neighbour_pairs(cells):
    """Every adjacent pair (differing by one cell in x or z) inside the sample."""
    cell_set = set(cells)
    pairs = []
    for cell_x, cell_z in sorted(cells):
        for other in ((cell_x + 1, cell_z), (cell_x, cell_z + 1)):
            if other in cell_set:
                pairs.append(((cell_x, cell_z), other))
    return pairs


def audit(seed, radius, config=None, sample=None):
    config = config or PlanningConfig()
    cells = sample if sample is not None else [
        (cell_x, cell_z)
        for cell_x in range(-radius, radius + 1)
        for cell_z in range(-radius, radius + 1)
    ]
    accepted, rejected, elapsed = acceptance(seed, cells, config)

    reasons = {}
    for reason in rejected.values():
        reasons[reason] = reasons.get(reason, 0) + 1
    undocumented = {reason: count for reason, count in reasons.items()
                    if reason.startswith("UNDOCUMENTED")}

    # determinism: replan a fixed, small subset
    probe = sorted(accepted)[:3]
    determinism = []
    for cell_x, cell_z in probe:
        again, _ = plan_cell(seed, cell_x, cell_z, config)
        determinism.append({
            "cell": [cell_x, cell_z],
            "identical_identity": bool(again is not None and
                                       again["identity_sha256"] == accepted[(cell_x, cell_z)]["identity_sha256"]),
        })

    # cross-window agreement over every accepted adjacent pair
    pairs = []
    for left_cell, right_cell in neighbour_pairs(accepted):
        record = compare_pair(accepted[left_cell], accepted[right_cell], left_cell, right_cell)
        record["left_cell"] = list(left_cell)
        record["right_cell"] = list(right_cell)
        pairs.append(record)

    comparable = [record for record in pairs if record["comparable"]]
    def worst(field):
        values = [record[field] for record in comparable if record.get(field) is not None]
        return max(values) if values else None
    agreements = [record["river_agreement"] for record in comparable
                  if record.get("river_agreement") is not None]
    outlet_agreements = [record["outlet_agreement"] for record in comparable
                         if record.get("outlet_agreement") is not None]

    # load order: shuffled replanning of the accepted set must be identical
    shuffler = np.random.default_rng(20261020)
    order = list(accepted)
    shuffler.shuffle(order)
    reordered = {}
    for cell_x, cell_z in order:
        product, _ = plan_cell(seed, cell_x, cell_z, config)
        if product is not None:
            reordered[(cell_x, cell_z)] = product["identity_sha256"]
    load_order = {
        "cells_compared": len(order),
        "identity_mismatches": int(sum(
            1 for cell in order
            if cell not in reordered or reordered[cell] != accepted[cell]["identity_sha256"]
        )),
    }

    # base field is a pure function of world coordinates: sample it twice
    base = np.array([
        coarse_condition_field(seed, np.array([x], dtype=float), np.array([z], dtype=float), config)[0][0]
        for x, z in ((-2_080_000.0, -2_080_000.0), (-1_300_000.0, -1_000_000.0), (3_500_000.0, 4_100_000.0))
    ])
    base_again = np.array([
        coarse_condition_field(seed, np.array([x], dtype=float), np.array([z], dtype=float), config)[0][0]
        for x, z in ((-2_080_000.0, -2_080_000.0), (-1_300_000.0, -1_000_000.0), (3_500_000.0, 4_100_000.0))
    ])

    return {
        "schema": SCHEMA,
        "seed": int(seed),
        "macro_span_m": float(config.macro_span_m),
        "samples_per_span": int(config.samples_per_span),
        "spacing_m": float(config.macro_span_m / config.samples_per_span),
        "sample_cells": len(cells),
        "planning_seconds": round(elapsed, 3),
        "seconds_per_cell": round(elapsed / max(len(cells), 1), 4),
        "comparator_aligned": bool(comparable) and all(
            record["condition_max_abs_diff_m"] == 0.0 for record in comparable
        ),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "acceptance_rate": (len(accepted) / len(cells)) if cells else None,
        "rejection_reasons": reasons,
        "undocumented_failure_count": int(sum(undocumented.values())),
        "determinism": determinism,
        "base_field_is_pure_function": bool(np.array_equal(base, base_again)),
        "adjacent_accepted_pairs": len(comparable),
        "cross_window": {
            "conditions_conflict_pairs": int(sum(
                1 for record in comparable if record["condition_max_abs_diff_m"] > 0.0)),
            "worst_condition_diff_m": worst("condition_max_abs_diff_m"),
            "ocean_mismatch_pairs": int(sum(
                1 for record in comparable if record["ocean_mask_disagreements"] > 0)),
            "worst_ocean_disagreements": worst("ocean_mask_disagreements"),
            "worst_height_diff_m": worst("height_max_abs_diff_m"),
            "pairs_with_height_mismatch": int(sum(
                1 for record in comparable if record["height_max_abs_diff_m"] > 0.0)),
            "worst_receiver_disagreements": worst("receiver_disagreements"),
            "outlet_disagreement_pairs": int(sum(
                1 for record in comparable if record["outlet_disagreements"] > 0)),
            "worst_outlet_disagreements": worst("outlet_disagreements"),
            "outlet_coverage_mismatch_pairs": int(sum(
                1 for record in comparable if record["outlet_left_owned"] != record["outlet_right_owned"])),
            "min_outlet_agreement": (min(outlet_agreements) if outlet_agreements else None),
            "mean_outlet_agreement": (sum(outlet_agreements) / len(outlet_agreements)) if outlet_agreements else None,
            "worst_owner_label_disagreements": worst("owner_label_disagreements"),
            "min_river_agreement": min(agreements) if agreements else None,
            "mean_river_agreement": (sum(agreements) / len(agreements)) if agreements else None,
        },
        "load_order": load_order,
        "pairs": pairs,
        "limitations": [
            "plane sample only; no claim about the whole infinite world",
            "agreement is measured over physical overlap, not over a certified domain definition",
            "no naturalness threshold; this auditor certifies consistency only",
            "comparator_aligned only says the overlap comparator is aligned; a false "
            "value invalidates every cross_window number in this report. It is proven "
            "by the shared base condition field, which is a pure function of world "
            "coordinates and therefore must agree exactly. Ocean mask disagreement is "
            "NOT an alignment failure: the ocean is defined by an in-window flood, so "
            "window-dependent ocean is a real finding, not a comparator bug. Consistency "
            "in the exporting sense is independent of naturalness.",
            "owner_label_disagreements is NOT a conflict metric: owner_domain_id is a "
            "per-window enumeration index, so two windows that agree perfectly on the "
            "world still disagree on that integer. Use the physical-outlet fields "
            "(outlet_disagreements / outlet_agreement / outlet_coverage_mismatch_pairs) "
            "for cross-window ownership, and read this label field as informational only."
        ],
        "consistency_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--radius", type=int, default=5,
                        help="sample the macro cells in [-radius, radius]^2")
    parser.add_argument("--output", required=True, help="JSON report path; refuses to overwrite")
    parser.add_argument("--engine", choices=("planner", "contract"), default="planner",
                        help="planner = the frozen bounded product; contract = the "
                             "world-anchored closure contract (metric_domain_closure)")
    parser.add_argument("--step", type=int, default=4,
                        help="contract engine: stride (nodes) of the overlap sampling")
    args = parser.parse_args(argv)
    if args.engine == "contract":
        record = audit_contract(args.seed, args.radius, step=args.step)
        with Path(args.output).open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        print("OK written:", args.output)
        print("engine: contract  tiles:", len(record["tiles"]),
              " adjacent pairs:", record["adjacent_tile_pairs"])
        contract = record["contract"]
        print("outlet disagreement pairs:", contract["outlet_disagreement_pairs"],
              " worst:", contract["worst_outlet_disagreements"])
        print("ocean mismatch pairs:", contract["ocean_mismatch_pairs"],
              " worst:", contract["worst_ocean_disagreements"])
        print("one-sided refusal points:", contract["one_sided_refusal_points"],
              " dominant reason conflicts:", contract["dominant_reason_conflict_points"])
        print("confident ocean mismatches:", contract["confident_ocean_mismatch_points"],
              " confident reason mismatches:", contract["confident_reason_mismatch_points"])
        print("eligibility conflict points:", contract["eligibility_conflict_points"],
              " one-sided:", contract["eligibility_one_sided_points"],
              " accepted-while-unresolved:", contract["accepted_while_unresolved_points"],
              " accepted-while-ocean:", contract["accepted_while_ocean_points"])
        print("delivery face (both cores): points:", contract["delivery_core_points"],
              " ownership-mismatch pairs:", contract["delivery_core_ownership_mismatch_pairs"],
              " worst one-sided:", contract["worst_core_ownership_one_sided_points"],
              " one-sided points:", contract["delivery_core_ownership_one_sided_points"],
              " eligibility one-sided:", contract["delivery_core_eligibility_one_sided_points"],
              " owner mismatches:", contract["delivery_core_owner_mismatch_points"])
        print("core reason totals:", record["core"]["reason_totals"],
              " worst core refused:", record["core"]["worst_core_refused"])
        print("tile rebuild bit-identical:", record["tile_rebuild_is_bit_identical"])
        print("load order: tiles", record["load_order"]["tiles_compared"],
              " mismatches:", record["load_order"]["tile_order_mismatches"],
              " points", record["load_order"]["points_compared"],
              " mismatches:", record["load_order"]["point_order_mismatches"])
        return
    record = audit(args.seed, args.radius)
    with Path(args.output).open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print("OK written:", args.output)
    print("comparator aligned:", record["comparator_aligned"])
    print("acceptance:", record["accepted"], "/", record["sample_cells"],
          "=", f"{record['acceptance_rate']:.3%}")
    cross = record["cross_window"]
    print("adjacent pairs:", record["adjacent_accepted_pairs"],
          " conditions_conflict:", cross["conditions_conflict_pairs"])
    print("worst height diff:", cross["worst_height_diff_m"],
          " min river agreement:", cross["min_river_agreement"])
    print("outlet disagreement pairs:", cross["outlet_disagreement_pairs"],
          " coverage mismatch pairs:", cross["outlet_coverage_mismatch_pairs"],
          " min outlet agreement:", cross["min_outlet_agreement"])
    print("rejection reasons:", record["rejection_reasons"])


if __name__ == "__main__":
    main()
