"""Audit the native-30 m lake / depression storage-and-spill mechanism (p2).

What it does
-----------
It re-measures every claim the module and its tests make, on tiny analytic beds and
on seeded noise fields, and writes one machine-readable record:

* source identity (SHA256 of the module, the tests and every frozen dependency it
  reuses) so a later run can tell that it audited the same bytes;
* the declared units, tolerances and budgets **as read from the module**, not
  re-typed here;
* the saddle-definition census: how often the naive "lowest bed on the rim"
  differs from the provable flood level, with the maximum difference -- the number
  that justifies the design;
* each synthetic scenario's measured value against an independent reference
  (closed-form arithmetic or an independent traversal written here);
* a refusal census over seeded noise, so the reason codes are counted rather than
  asserted;
* the recorded gaps, as strings copied from the tests that pin them.

What it deliberately does **not** do
------------------------------------
No 48 km run, no GPU, no archived terrain page, no writing into
``verification/``, no touching a frozen pin. Every field here is tens to a few
thousand 30 m cells.

Usage
-----
    runtime/venv/Scripts/python.exe -B -X utf8 tools/audit_native_30m_lakes.py \\
        --out .scratch/river-stage1-completion/lakes-20251025-v1/evidence.json

The exit status is 0 only when every measured check agrees with its independent
reference and every declared invariance holds. Anything else is a failure and is
reported as one -- a green run is never assumed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np


WORLD_SEED = 20261020            # CONTRIBUTING.md:35
SPACING_M = 30.0
CELL_AREA_M2 = SPACING_M * SPACING_M
SOURCE_SHA = "c" * 64
NOISE_FIELDS = 12
NOISE_SIDE = 32

REPO_ROOT = Path(__file__).resolve().parent.parent

DEPENDENCIES = (
    "terrain_pipeline/surface_rivers/native_30m_lakes.py",
    "terrain_pipeline/surface_rivers/metric_lake_storage.py",
    "terrain_pipeline/surface_rivers/metric_lake_hypsometry.py",
    "terrain_pipeline/surface_rivers/metric_depression_gate.py",
    "terrain_pipeline/surface_rivers/metric_cross_region.py",
    "terrain_pipeline/surface_rivers/world_reach_lake.py",
    "tests/test_native_30m_lakes.py",
)


# --------------------------------------------------------------------------- #
# independent reference: no import of the module under test
# --------------------------------------------------------------------------- #
def reference_priority_flood(bed):
    """filled[i] = min over border paths of (max elevation on the path), 8-neighbour."""
    import heapq
    field = np.asarray(bed, np.float64)
    rows, columns = field.shape
    filled = np.full(field.shape, np.inf)
    done = np.zeros(field.shape, bool)
    heap = []
    for row in range(rows):
        for column in range(columns):
            if row in (0, rows - 1) or column in (0, columns - 1):
                filled[row, column] = field[row, column]
                heapq.heappush(heap, (float(field[row, column]), row, column))
    while heap:
        level, row, column = heapq.heappop(heap)
        if done[row, column]:
            continue
        done[row, column] = True
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = row + dr, column + dc
                if not (0 <= rr < rows and 0 <= cc < columns) or done[rr, cc]:
                    continue
                candidate = max(level, float(field[rr, cc]))
                if candidate < filled[rr, cc]:
                    filled[rr, cc] = candidate
                    heapq.heappush(heap, (candidate, rr, cc))
    return filled


def reference_component(bed, filled, seed):
    depth = np.asarray(filled, np.float64) - np.asarray(bed, np.float64)
    rows, columns = depth.shape
    found = np.zeros(depth.shape, bool)
    if depth[seed] <= 0.:
        return found
    found[seed] = True
    stack = [seed]
    while stack:
        row, column = stack.pop()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = row + dr, column + dc
            if (0 <= rr < rows and 0 <= cc < columns and depth[rr, cc] > 0.
                    and not found[rr, cc]):
                found[rr, cc] = True
                stack.append((rr, cc))
    return found


def reference_rim(mask):
    mask = np.asarray(mask, bool)
    rows, columns = mask.shape
    out = np.zeros(mask.shape, bool)
    for row in range(rows):
        for column in range(columns):
            if mask[row, column]:
                continue
            hit = False
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = row + dr, column + dc
                    if 0 <= rr < rows and 0 <= cc < columns and mask[rr, cc]:
                        hit = True
                        break
                if hit:
                    break
            out[row, column] = hit
    return out


def reference_volume(bed, mask, stage):
    beds = np.asarray(bed, np.float64)[np.asarray(mask, bool)]
    return float(CELL_AREA_M2 * np.maximum(stage - beds, 0.).sum())


def reference_area(bed, mask, stage):
    beds = np.asarray(bed, np.float64)[np.asarray(mask, bool)]
    return float(CELL_AREA_M2 * int((beds < stage).sum()))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def file_sha256(relative):
    path = REPO_ROOT / relative
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return {"path": relative, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def jsonable(value):
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return None
    return value


def check(record, name, measured, reference, tolerance, units, note=""):
    """Append one measured-vs-independent comparison; returns True when it passes."""
    measured = float(measured)
    reference = float(reference)
    difference = abs(measured - reference)
    passed = bool(difference <= tolerance)
    record.append({"check": name, "measured": measured, "reference": reference,
                   "absolute_difference": difference, "tolerance": float(tolerance),
                   "units": units, "passed": passed, "note": note})
    return passed


# --------------------------------------------------------------------------- #
# fixtures (same analytic beds the tests use, so a reader can cross-check)
# --------------------------------------------------------------------------- #
def tied_rim_box(size=21, plateau_m=10.0, bed_m=3.0, low=8, high=13):
    field = np.full((size, size), float(plateau_m))
    field[low:high, low:high] = float(bed_m)
    return field


def cone_bowl(size=31, bottom_m=100.0, rim_m=112.0, radius_cells=6.0):
    zs = np.arange(size, dtype=np.float64) - (size - 1) / 2.
    xs = np.arange(size, dtype=np.float64) - (size - 1) / 2.
    radius = np.hypot(zs[:, None], xs[None, :])
    inside = np.clip(1.0 - radius / radius_cells, 0.0, None)
    return rim_m - (rim_m - bottom_m) * inside


def plateau_pit(size=15, plateau_m=10.0, pit_m=0.0):
    field = np.full((size, size), float(plateau_m))
    field[size // 2, size // 2] = float(pit_m)
    return field


def sloped_lowland(size=21):
    zs = np.arange(size, dtype=np.float64)
    xs = np.arange(size, dtype=np.float64)
    return 0.5 * zs[:, None] + 0.5 * xs[None, :]


def pit_on_a_slope(size=15, gradient=0.4, base_m=10.0, dig_m=6.0):
    zs = np.arange(size, dtype=np.float64)
    xs = np.arange(size, dtype=np.float64)
    field = base_m + gradient * zs[:, None] + gradient * xs[None, :]
    field[size // 2, size // 2] -= dig_m
    return field


def noise_field(side=NOISE_SIDE, seed_offset=0):
    """Seeded white noise on a declared sub-stream of the fixed world seed.

    The sub-seed is derived from ``WORLD_SEED`` and a stable purpose string with
    SHA256, never from time, system entropy or ``hash()`` (CONTRIBUTING.md:37-38).
    """
    material = ("terragenesis/world-seed-subseed-v1|world_seed=%d|lake-audit-noise|%d"
                % (WORLD_SEED, seed_offset)).encode("utf-8")
    subseed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") & (2 ** 53 - 1)
    generator = np.random.default_rng(subseed)
    return 100.0 + generator.normal(0.0, 3.0, size=(side, side)), subseed


# --------------------------------------------------------------------------- #
# scenarios
# --------------------------------------------------------------------------- #
def run(out_path):
    from terrain_pipeline.surface_rivers import native_30m_lakes as module

    checks = []
    scenarios = []

    def build(bed, seed, **overrides):
        arguments = dict(
            seed_cell_rc=seed, spacing_m=SPACING_M, origin_xz_m=(1_200_000.0, 1_300_000.0),
            source_identity_sha256=SOURCE_SHA, surface_kind=module.BED_SURFACE_KIND,
            sill_width_m=40.0, discharge_coefficient=0.4, head_allowance_m=2.0)
        arguments.update(overrides)
        bed = np.asarray(bed, np.float64)
        return module.build_native_30m_lake(bed, np.ones(bed.shape, bool), **arguments)

    # ---- S1: membership, escape level, exit set ---------------------------- #
    bed = cone_bowl()
    lake = build(bed, (15, 15))
    filled = reference_priority_flood(bed)
    members = reference_component(bed, filled, (15, 15))
    rim = reference_rim(members)
    spill = float(filled[members].max())
    exits = rim & (np.abs(filled - spill) <= module.LEVEL_TOLERANCE_M)
    scenarios.append({
        "scenario": "S1_cone_bowl_membership_and_exit_set",
        "bed_shape": list(bed.shape), "spacing_m": SPACING_M,
        "certified": bool(lake.certified), "reason_code": lake.reason_code,
        "basin_cells": int(lake.basin_cells),
        "basin_cells_reference": int(members.sum()),
        "spill_level_m": float(lake.spill_level_m),
        "spill_level_reference_m": spill,
        "exit_cells": int(lake.saddle["exit_cells"]),
        "exit_cells_reference": int(exits.sum()),
        "flood_level_constancy_m": float(lake.saddle["flood_level_constancy_m"]),
        "geometric_rim_minimum_m": float(lake.saddle["geometric_rim_minimum_m"]),
    })
    check(checks, "membership cells", lake.basin_cells, members.sum(), 0, "cells")
    check(checks, "spill level", lake.spill_level_m, spill, module.LEVEL_TOLERANCE_M, "m")
    check(checks, "exit set cells", lake.saddle["exit_cells"], exits.sum(), 0, "cells")
    check(checks, "flood level constancy", lake.saddle["flood_level_constancy_m"], 0.0,
          module.LEVEL_TOLERANCE_M, "m")

    # ---- S2: storage curve against the definition ------------------------- #
    for name, field, seed, stages in (("S2_tied_rim_box", tied_rim_box(), (10, 10),
                                      (3.0, 4.5, 7.0, 9.5, 10.0)),
                                     ("S2_cone_bowl", cone_bowl(), (15, 15),
                                      (100.0, 103.0, 106.0, 111.0, 112.0))):
        lake = build(field, seed)
        mask = np.asarray(lake.basin_mask)
        rows = []
        for stage in stages:
            rows.append({
                "stage_m": float(stage),
                "volume_m3": float(lake.storage.volume_at_stage(stage)),
                "volume_reference_m3": reference_volume(field, mask, stage),
                "area_m2": float(lake.storage.surface_area_at_stage(stage)),
                "area_reference_m2": reference_area(field, mask, stage)})
            check(checks, "%s V(%.3f)" % (name, stage),
                  lake.storage.volume_at_stage(stage),
                  reference_volume(field, mask, stage), 1e-6, "m3")
            check(checks, "%s A(%.3f)" % (name, stage),
                  lake.storage.surface_area_at_stage(stage),
                  reference_area(field, mask, stage), 1e-6, "m2")
        scenarios.append({
            "scenario": name, "certified": bool(lake.certified),
            "basin_cells": int(lake.basin_cells),
            "spill_level_m": float(lake.spill_level_m),
            "capacity_at_spill_m3": float(lake.capacity_at_spill_m3),
            "storage_capacity_m3": float(lake.storage_capacity_m3),
            "head_allowance_m": float(lake.head_allowance_m), "levels": rows})

    # ---- S3: initial water, overflow, recession --------------------------- #
    field = tied_rim_box()
    lake = build(field, (10, 10))
    start = float(lake.capacity_at_spill_m3)
    initial = module.initial_volume_m3(lake, initial_stage_m=6.0)
    check(checks, "initial volume at 6 m", initial,
          reference_volume(field, lake.basin_mask, 6.0), 1e-6, "m3")
    inflow, inflow_record = module.inflow_volume_m3(lake, produced_depth_m=0.05)
    check(checks, "inflow volume", inflow,
          inflow_record["contributing_cells"] * CELL_AREA_M2 * 0.05, 1e-6, "m3")

    inflow_series = np.array([4000.0] + [0.0] * 399)
    dt_series = np.full(400, 60.0)
    trace = module.march_lake(lake, inflow_series, dt_series, initial_volume_m3=start)
    ledger = trace["ledger"]
    check(checks, "ledger closure",
          ledger["initial_m3"] + ledger["inflow_m3"] - ledger["spill_m3"]
          - ledger["final_m3"], ledger["residual_m3"], 1e-9, "m3")
    check(checks, "ledger residual relative to gross",
          float(trace["ledger_residual_relative"]), 0.0, 1e-9, "-")
    stage = np.asarray(trace["stage_m"])
    scenarios.append({
        "scenario": "S3_overflow_then_recession",
        "certified": bool(lake.certified),
        "initial_m3": start, "inflow_m3": float(inflow_series.sum()),
        "spill_m3": float(trace["spill_volume_m3"].sum()),
        "final_m3": float(trace["volume_m3"][-1]),
        "spill_level_m": float(lake.spill_level_m),
        "stage_peak_m": float(stage.max()), "stage_final_m": float(stage[-1]),
        "stage_monotone_after_peak": bool(np.all(np.diff(stage[1:]) <= 0.0)),
        "requested_steps": int(inflow_series.size),
        "dt_seconds": 60.0,
        "loss_terms": trace["loss_terms"],
    })

    # ---- S4: the saddle census that justifies the design ------------------ #
    census = {"fields": 0, "depressions": 0, "geometric_below_spill": 0,
              "max_geometric_minus_spill_m": 0.0, "constancy_nonzero": 0,
              "subseeds": []}
    for offset in range(NOISE_FIELDS):
        field, subseed = noise_field(seed_offset=offset)
        census["subseeds"].append(subseed)
        filled = reference_priority_flood(field)
        depth = filled - field
        wet = depth > 0.0
        # label the 4-connected wet components with a plain stack walk
        seen = np.zeros(wet.shape, np.int64) - 1
        used = 0
        for row in range(wet.shape[0]):
            for column in range(wet.shape[1]):
                if not wet[row, column] or seen[row, column] >= 0:
                    continue
                stack = [(row, column)]
                seen[row, column] = used
                while stack:
                    r, c = stack.pop()
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        rr, cc = r + dr, c + dc
                        if (0 <= rr < wet.shape[0] and 0 <= cc < wet.shape[1]
                                and wet[rr, cc] and seen[rr, cc] < 0):
                            seen[rr, cc] = used
                            stack.append((rr, cc))
                used += 1
        census["fields"] += 1
        for label in range(used):
            mask = seen == label
            level = float(filled[mask].max())
            if float(filled[mask].max() - filled[mask].min()) > 1e-12:
                census["constancy_nonzero"] += 1
            rim = reference_rim(mask)
            if not rim.any():
                continue
            census["depressions"] += 1
            lowest = float(field[rim].min())
            if lowest < level - 1e-12:
                census["geometric_below_spill"] += 1
                census["max_geometric_minus_spill_m"] = max(
                    census["max_geometric_minus_spill_m"], level - lowest)
    census["fraction_where_naive_is_wrong"] = (
        census["geometric_below_spill"] / census["depressions"]
        if census["depressions"] else 0.0)
    census["policy"] = ("spill_level is the priority flood's own level; the lowest rim "
                        "bed is reported only as a rejected number")
    check(checks, "flood level is constant on every closed depression",
          census["constancy_nonzero"], 0, 0, "components")

    # ---- S5: refusal census ------------------------------------------------ #
    refusals = []
    for name, field, seed, overrides in (
            ("sloped_lowland", sloped_lowland(), (10, 10), {}),
            ("flat_lowland", np.full((15, 15), 2.0), (7, 7), {}),
            ("plateau_pit_11", plateau_pit(size=11), (5, 5), {}),
            ("plateau_pit_13_exit_band", plateau_pit(size=13), (6, 6), {}),
            ("pit_on_a_slope", pit_on_a_slope(), (7, 7), {"contact_margin_cells": 1}),
    ):
        lake = build(field, seed, **overrides)
        refusals.append({
            "fixture": name, "certified": bool(lake.certified),
            "reason_code": lake.reason_code,
            "truncated_not_judged": bool(lake.truncated_not_judged),
            "rim_clearance_cells": int(lake.rim_clearance_cells),
            "exit_min_clearance_cells": int(lake.saddle.get("exit_min_clearance_cells", -1)),
            "unknown_upstream_cells": int(lake.catchment.get("unknown_cells", 0)),
            "policy": "a refusal carries no store, no outlet and no certified level"})
        if not lake.certified:
            check(checks, "refusal %s carries no store" % name,
                  0 if lake.storage is None else 1, 0, 0, "bool")

    # ---- S6: a water surface must never certify as a bed ------------------ #
    field = tied_rim_box()
    filled = reference_priority_flood(field)
    surface = np.where(filled > field, filled, field)
    surface_lake = build(surface, (10, 10))
    declared_refusal = None
    try:
        build(field, (10, 10), surface_kind=module.WATER_SURFACE_KINDS[0])
    except ValueError as error:
        declared_refusal = str(error)
    check(checks, "a filled surface is refused",
          0 if surface_lake.reason_code == module.REASON_NO_DEPRESSION else 1, 0, 0, "bool")
    check(checks, "a declared water surface is refused",
          0 if declared_refusal else 1, 0, 0, "bool")

    # ---- S7: the gate is a separate ledger -------------------------------- #
    pit = plateau_pit(size=41)
    gate_lake = build(pit, (20, 20), produced_depth_m=50.0)
    gate = gate_lake.provenance.get("gate", {})
    check(checks, "a certified basin can be refused by the gate",
          0 if (gate_lake.certified and gate.get("verdict") == "pass_through") else 1,
          0, 0, "bool")

    failures = [row for row in checks if not row["passed"]]
    payload = {
        "schema": "terragenesis-native-30m-lakes-audit-v1",
        "algorithm": module.ALGORITHM,
        "module_schema": module.SCHEMA,
        "world_seed": WORLD_SEED,
        "spacing_m": SPACING_M, "cell_area_m2": CELL_AREA_M2,
        "units": dict(module.UNITS),
        "tolerances": dict(module.TOLERANCES),
        "budgets": dict(module.BUDGETS),
        "reason_codes": list(module.REASON_CODES),
        "truncation_reasons": list(module.TRUNCATION_REASONS),
        "sources": [file_sha256(relative) for relative in DEPENDENCIES],
        "environment": {"python": sys.version.split()[0],
                        "numpy": np.__version__, "platform": platform.platform()},
        "scenarios": scenarios,
        "saddle_census": census,
        "refusals": refusals,
        "gate_separation": {"gate": gate, "still_certified": bool(gate_lake.certified)},
        "recorded_gaps": [
            "flood_level_not_constant_over_basin is a unit guard; it cannot fire on a "
            "bed produced by the repository's priority flood",
            "a diagonal deep shelf can remove a basin cell from the raw catchment, which "
            "is refused as basin_membership_not_self_draining rather than measured",
            "march_lake solves one lake; a shared-stage multi-lake solve lives in "
            "metric_natural_lakes and is not exposed here",
            "evaporation and groundwater are declared absent (None), not zero",
            "the saddle weir width is a caller declaration; what is measured is the "
            "exit-cell count and the nearest exit's distance to the window border",
            "above the saddle, V(h) is a declared pondage A(spill)*(h-spill), not "
            "measured terrain",
        ],
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(failures),
        "failures": failures,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(jsonable(payload), indent=2, sort_keys=True, allow_nan=False)
    out_path.write_text(text + "\n", encoding="utf-8")
    print("checks: %d, failures: %d" % (len(checks), len(failures)))
    print("saddle census: %d depressions / %d fields, naive-below-spill %d (%.1f %%), "
          "max gap %.6f m"
          % (census["depressions"], census["fields"], census["geometric_below_spill"],
             100.0 * census["fraction_where_naive_is_wrong"],
             census["max_geometric_minus_spill_m"]))
    for row in failures:
        print("FAILED: %s measured=%r reference=%r difference=%r tolerance=%r"
              % (row["check"], row["measured"], row["reference"],
                 row["absolute_difference"], row["tolerance"]))
    print("written: %s" % out_path)
    return 0 if not failures else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=".scratch/river-stage1-completion/"
                                          "lakes-20251025-v1/evidence.json",
                        help="where the machine-readable record is written")
    arguments = parser.parse_args(argv)
    return run(arguments.out)


if __name__ == "__main__":
    sys.exit(main())
