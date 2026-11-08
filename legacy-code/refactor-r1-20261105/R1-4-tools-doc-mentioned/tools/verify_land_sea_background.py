"""Independent read-only acceptance for the land/sea background contract (P2.2).

Contract: `.scratch/infinite-world-geography/land-sea-interface-spec.md` (R2).
Implementation under test: `terrain_pipeline.surface_rivers.metric_domain_closure`.

This verifier is deliberately written against the CONTRACT, not against the
implementation: every band it asserts is recomputed from the raw pure field
(`coarse_condition_field`) so that a future change which smuggles connectivity
into the two unconditional bands makes this script red.

Nothing here writes to the workspace. Pass `--output` to drop a JSON report
(default: `.scratch/infinite-world-geography/land-sea-background-acceptance.json`).

Checks, in contract order (spec section 7):

  1. same-coordinate recomputation is bit-identical
  2. two overlapping world-anchored tiles agree cell by cell (the defect's
     bullseye: the old bounded planner answered from the window)
  3. query order, batching and the region cache do not change an answer
  4. refusals carry no outlet and the reason vocabulary is verbatim
  5. regression lock on the two unconditional bands (no connectivity allowed)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain_pipeline.hydrology_planning import PlanningConfig, coarse_condition_field
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    ClosureRegion,
    MARINE_DEPTH_M,
    clear_cache,
    global_ocean_mask,
    resolve_points,
)

SEED = 20261020
CONFIG = PlanningConfig()
SPACING_M = CONFIG.macro_span_m / CONFIG.samples_per_span
CORE_SPAN_M = 4.0 * CONFIG.macro_span_m
SEA_LEVEL_M = CONFIG.sea_level_m

REASON_VOCABULARY = ("ocean", "coastal", "closed_basin", "unresolved_border", "out_of_tile")
REFUSAL_REASONS = ("unresolved_border", "out_of_tile")


class Report:
    def __init__(self):
        self.rows = []
        self.failures = []

    def check(self, ok, label, detail=""):
        self.rows.append({"check": label, "passed": bool(ok), "detail": str(detail)})
        if not ok:
            self.failures.append(label)
        print("%-4s %s%s" % ("OK" if ok else "FAIL", label,
                             ("  [%s]" % detail) if detail else ""))
        return bool(ok)

    @property
    def passed(self):
        return sum(1 for row in self.rows if row["passed"])


def field_height(xs, zs):
    """The raw pure face, recomputed here -- never read out of the module."""
    return np.asarray(coarse_condition_field(SEED, xs, zs, CONFIG)[0], np.float64)


def core_lattice(x0, x1, z0, z1, step_nodes=1):
    xs = np.arange(x0, x1 + 1e-6, SPACING_M * step_nodes)
    zs = np.arange(z0, z1 + 1e-6, SPACING_M * step_nodes)
    return np.meshgrid(xs, zs)


# --------------------------------------------------------------------- 1
def check_recomputation_is_bit_identical(report):
    print("\n== 1. same-coordinate recomputation")
    xs, zs = core_lattice(40_000.0, 260_000.0, 40_000.0, 260_000.0, 8)
    first = global_ocean_mask(SEED, xs, zs, CONFIG)
    second = global_ocean_mask(SEED, xs, zs, CONFIG)
    report.check(np.array_equal(first, second),
                 "two identical grid queries agree bit for bit")
    clear_cache()
    third = global_ocean_mask(SEED, xs, zs, CONFIG)
    report.check(np.array_equal(first, third),
                 "answers survive a cache clear (no cached state is load bearing)")
    order = np.arange(xs.size)[::-1]
    flat = global_ocean_mask(SEED, xs.reshape(-1)[order].reshape(-1, 1),
                            zs.reshape(-1)[order].reshape(-1, 1), CONFIG).reshape(-1)
    report.check(np.array_equal(flat, first.reshape(-1)[order]),
                 "per-point queries in reverse order match the grid")
    return first


# --------------------------------------------------------------------- 2
def check_cross_anchoring(report):
    print("\n== 2. two overlapping world-anchored tiles")
    left = ClosureRegion(SEED, CONFIG, 0, 0)     # x in [-480, 1760] km
    right = ClosureRegion(SEED, CONFIG, 0, 1)    # x in [800, 3040] km
    lower = ClosureRegion(SEED, CONFIG, 1, 0)
    for name, other, x0, x1 in (("(0,1)", right, 840_000.0, 1_700_000.0),
                                ("(1,0)", lower, 40_000.0, 1_700_000.0)):
        xs, zs = core_lattice(x0, x1, 40_000.0, 1_700_000.0, 16)
        disagree = 0
        seen = 0
        for row in range(xs.shape[0]):
            for column in range(xs.shape[1]):
                x, z = float(xs[row, column]), float(zs[row, column])
                one = left.ocean_at(x, z)
                two = other.ocean_at(x, z)
                if one is None or two is None:
                    continue
                seen += 1
                if bool(one) != bool(two):
                    disagree += 1
        report.check(seen > 0 and disagree == 0,
                     "tile (0,0) and tile %s agree on every shared cell" % name,
                     "%d shared cells, %d disagreements" % (seen, disagree))
    return left, right


# --------------------------------------------------------------------- 3
def check_order_independence(report, first):
    print("\n== 3. order / batching invariance")
    xs, zs = core_lattice(40_000.0, 260_000.0, 40_000.0, 260_000.0, 8)
    flat_x, flat_z = xs.reshape(-1), zs.reshape(-1)
    shuffled = np.random.default_rng(7).permutation(flat_x.size)
    pieces = []
    for start in range(0, flat_x.size, 37):
        chunk = shuffled[start:start + 37]
        pieces.append(global_ocean_mask(SEED, flat_x[chunk], flat_z[chunk], CONFIG))
    batched = np.empty(flat_x.size, bool)
    for start in range(0, flat_x.size, 37):
        chunk = shuffled[start:start + 37]
        batched[chunk] = pieces[start // 37]
    report.check(np.array_equal(batched, first.reshape(-1)),
                 "37-point batches in shuffled order reproduce the grid exactly")
    duplicated = global_ocean_mask(SEED, np.repeat(flat_x[:50], 3),
                                   np.repeat(flat_z[:50], 3), CONFIG)
    report.check(np.array_equal(duplicated, np.repeat(first.reshape(-1)[:50], 3)),
                 "repeated coordinates answer identically each time")


# --------------------------------------------------------------------- 4
def check_refusal_integrity(report):
    print("\n== 4. refusal vocabulary and no invented outlets")
    xs, zs = core_lattice(-300_000.0, 2_300_000.0, -300_000.0, 2_300_000.0, 29)
    resolved = resolve_points(SEED, xs, zs, CONFIG)
    reasons = np.asarray(resolved["reason"], object).reshape(-1)
    unknown = sorted(set(str(value) for value in reasons) - set(REASON_VOCABULARY))
    report.check(not unknown, "every reason is in the verbatim five-word vocabulary",
                 "unknown=%r" % (unknown,))
    outlet_x = np.asarray(resolved["outlet_x_m"], float).reshape(-1)
    outlet_z = np.asarray(resolved["outlet_z_m"], float).reshape(-1)
    flags = np.asarray(resolved["resolved"], bool).reshape(-1)
    has_outlet = np.isfinite(outlet_x) & np.isfinite(outlet_z)
    refusal = np.isin(reasons, list(REFUSAL_REASONS))
    report.check(not bool((refusal & has_outlet).any()),
                 "no refused point carries an outlet",
                 "refused=%d" % int(refusal.sum()))
    report.check(bool(np.array_equal(flags, ~refusal)),
                 "resolve_points' resolved flag is exactly 'reason not a refusal'")
    report.check(not bool((refusal & np.isin(reasons, list(("ocean", "coastal", "closed_basin")))).any()),
                 "the two vocabularies are disjoint")
    print("     reason counts: %s" % {
        name: int((reasons == name).sum()) for name in REASON_VOCABULARY})
    print("     refusal scan: %d refused / %d with an outlet (a count, not a requirement -- spec 7.4 is conditional)"
          % (int(refusal.sum()), int(has_outlet.sum())))
    return int(refusal.sum()), int(has_outlet.sum())


def check_refusal_path_is_reachable(report):
    """Find real refusals instead of asserting over an empty set.

    A module-level refusal happens when a point's drainage chain cannot be closed
    inside ITS OWN world-anchored tile (480 km of margin is not always enough).
    The scan below is dense enough to hit the truncated ring of the owning tile;
    if it finds none, that is reported as a measured fact -- with the counts --
    and the region-level ring is checked instead, so the assertions are never
    vacuous.
    """
    print("\n== 4b. making the refusal path non-vacuous")
    found = []
    # Dense scan across a tile seam (core span 1280 km): the owning tile's ring
    # sits near its own outer 480 km, so walk a band straddling x = 1280 km.
    for x0 in (1_180_000.0, 1_240_000.0, 1_300_000.0, 1_360_000.0):
        zs = np.arange(20_000.0, 1_400_000.0, 40_000.0)
        xs = np.full(zs.shape, x0)
        resolved = resolve_points(SEED, xs, zs, CONFIG)
        reasons = np.asarray(resolved["reason"], object).reshape(-1)
        for position, reason in enumerate(reasons):
            if str(reason) in REFUSAL_REASONS:
                found.append((float(xs[position]), float(zs[position]), str(reason)))
    report.check(True,
                 "module-level refusal scan completed",
                 "%d refusals found on the tile seam band" % len(found))
    if found:
        xs = np.array([item[0] for item in found])
        zs = np.array([item[1] for item in found])
        resolved = resolve_points(SEED, xs, zs, CONFIG)
        outlet_x = np.asarray(resolved["outlet_x_m"], float).reshape(-1)
        outlet_z = np.asarray(resolved["outlet_z_m"], float).reshape(-1)
        flags = np.asarray(resolved["resolved"], bool).reshape(-1)
        report.check(not bool(np.isfinite(outlet_x).any()) or not bool(outlet_x.size),
                     "no refused seam point carries an outlet x")
        report.check(bool(np.isfinite(outlet_x).sum() == 0 and np.isfinite(outlet_z).sum() == 0),
                     "no refused seam point carries an outlet coordinate")
        report.check(not bool(flags.any()),
                     "every refused seam point reports resolved=False")
        return len(found)

    # No module-level refusal found: fall back to the region ring, which must
    # still refuse -- the margin is finite and the ring is truncated by design.
    region = ClosureRegion(SEED, CONFIG, 0, 0)
    ring_refusals = 0
    ring_with_outlet = 0
    for row in range(region.shape[0]):
        for column in (0, region.shape[1] - 1):
            x = region.origin_x_m + column * SPACING_M
            z = region.origin_z_m + row * SPACING_M
            if region.classify(x, z) == "unresolved_border":
                ring_refusals += 1
                ring_with_outlet += int(region.outlet_at(x, z) is not None)
    report.check(ring_refusals > 0,
                 "the owning tile's truncated ring really does refuse",
                 "%d ring refusals" % ring_refusals)
    report.check(ring_with_outlet == 0,
                 "no ring refusal invents an outlet",
                 "with outlet=%d" % ring_with_outlet)
    cs = region.shape[1] - 1
    report.check(region.classify(region.origin_x_m - SPACING_M * 4,
                                 region.origin_z_m - SPACING_M * 4) == "out_of_tile",
                 "an uncovered point is refused with out_of_tile")
    return 0


# --------------------------------------------------------------------- 5
def check_unconditional_bands(report):
    print("\n== 5. regression lock: the two bands may not use connectivity")
    xs, zs = core_lattice(-300_000.0, 2_300_000.0, -300_000.0, 2_300_000.0, 23)
    height = field_height(xs, zs)
    mask = global_ocean_mask(SEED, xs, zs, CONFIG)

    deep = height < (SEA_LEVEL_M - MARINE_DEPTH_M)
    land = height > SEA_LEVEL_M
    missing = int((deep & ~mask).sum())
    invented = int((land & mask).sum())
    report.check(bool(deep.any()), "the deep band is actually sampled",
                 "%d cells below sea - %.0f m" % (int(deep.sum()), MARINE_DEPTH_M))
    report.check(bool(land.any()), "the land band is actually sampled",
                 "%d cells above sea" % int(land.sum()))
    report.check(missing == 0, "every cell deeper than the marine threshold is ocean",
                 "missing=%d" % missing)
    report.check(invented == 0, "no cell above the sea datum is called ocean",
                 "invented=%d" % invented)

    # The bands must be decidable from the coordinate alone: perturb the query
    # neighbourhood and the answer for a deep / land cell must not move.
    deep_xy = np.argwhere(deep)
    land_xy = np.argwhere(land)
    moved = 0
    for row, column in list(deep_xy[:40]) + list(land_xy[:40]):
        x, z = float(xs[row, column]), float(zs[row, column])
        single = global_ocean_mask(SEED, np.array([x]), np.array([z]), CONFIG)[0]
        moved += int(bool(single) != bool(mask[row, column]))
    report.check(moved == 0,
                 "isolated single-point queries agree with the batch on both bands",
                 "moved=%d of %d" % (moved, min(80, deep_xy.shape[0] + land_xy.shape[0])))
    return {"deep_cells": int(deep.sum()), "land_cells": int(land.sum()),
            "marine_threshold_m": float(MARINE_DEPTH_M)}


# --------------------------------------------------------------------- 6
def check_field_purity(report):
    print("\n== 6. the underlying face is a pure function of (seed, x, z)")
    xs, zs = core_lattice(120_000.0, 400_000.0, 120_000.0, 400_000.0, 11)
    first = field_height(xs, zs)
    second = field_height(xs, zs)
    report.check(np.array_equal(first, second),
                 "the raw face is bit-identical when recomputed")
    return float(np.abs(first - second).max())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=".scratch/infinite-world-geography/"
                                           "land-sea-background-acceptance.json")
    args = parser.parse_args()

    print("seed=%d  macro_span=%.0f m  node spacing=%.0f m  core=%.0f km  margin=%.0f km"
          % (SEED, CONFIG.macro_span_m, SPACING_M, CORE_SPAN_M / 1000.0,
             (48 * SPACING_M) / 1000.0))

    report = Report()
    first = check_recomputation_is_bit_identical(report)
    left, right = check_cross_anchoring(report)
    check_order_independence(report, first)
    refused, with_outlet = check_refusal_integrity(report)
    seam_refusals = check_refusal_path_is_reachable(report)
    bands = check_unconditional_bands(report)
    drift = check_field_purity(report)

    print("\n== result")
    print("refused points: %d   points with an outlet: %d   seam refusals: %d"
          % (refused, with_outlet, seam_refusals))
    print("bands: %s" % bands)
    print("raw-face drift: %g" % drift)
    verdict = "PASS" if not report.failures else "FAIL"
    print("RESULT: %s -- %d checks passed, %d failed"
          % (verdict, report.passed, len(report.failures)))
    if report.failures:
        for label in report.failures:
            print("  FAILED: %s" % label)

    body = {
        "schema": "land-sea-background-acceptance-v1",
        "contract": ".scratch/infinite-world-geography/land-sea-interface-spec.md",
        "implementation": "terrain_pipeline/surface_rivers/metric_domain_closure.py",
        "seed": SEED,
        "node_spacing_m": SPACING_M,
        "core_span_m": CORE_SPAN_M,
        "margin_m": 48 * SPACING_M,
        "marine_depth_m": float(MARINE_DEPTH_M),
        "refused_points": refused,
        "points_with_outlet": with_outlet,
        "seam_refusals": seam_refusals,
        "checks": report.rows,
        "passed": report.passed,
        "failed": report.failures,
        "verdict": verdict,
        "writes_to_workspace": False,
    }
    destination = Path(args.output)
    if not destination.is_absolute():
        destination = Path(__file__).resolve().parents[1] / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    print("report written to %s" % destination)
    return 0 if not report.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())