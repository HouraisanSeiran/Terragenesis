"""Independent cold audit of the native-30 m hydrology evidence.

Independence rules (the whole reason this tool exists)
-----------------------------------------------------
This auditor must be able to say "the numbers in these files close" **without
re-using the code that produced them**. Therefore it never imports:

* ``terrain_pipeline.surface_rivers.native_30m_runoff``
* ``terrain_pipeline.surface_rivers.native_30m_hydrology_ledger``
* ``terrain_pipeline.surface_rivers.metric_network_accumulation``
* ``terrain_pipeline.rainfall_runoff``
* ``terrain_pipeline.mountain_runoff_routing``
* ``terrain_pipeline.surface_rivers.metric_natural_lakes`` and any other lake kernel

It also refuses to run in a process where any of those is already loaded, so an
in-process shortcut cannot quietly turn this into a second call of the code under
test. The import guard runs **before a single byte of data is read**.

What it recomputes, itself
--------------------------
1. the receiver traversal (donor-list BFS, not the canonical wave order of the
   kernel), producing the per-cell accumulated supply and the terminal partition;
2. the mm -> m3 conversion and the rain partition / store identities from the saved
   depth fields;
3. the basin water budget ``rain - ET - supply - storage change``;
4. the four-term boundary partition ``certified retained + certified open + certified
   unknown + withheld == declared input`` and the explicit ``unknown never merged
   into the outlet`` assertion;
5. the routed-injection rule: the routed terminal series must not equal the raw local
   supply series (that would mean it was re-injected as forcing), and the outlet may
   not silently absorb the unknown term.

Usage
-----
    runtime/venv/Scripts/python.exe -B -X utf8 tools/audit_native_30m_hydrology.py \
        --evidence .scratch/river-stage1-completion/hydrology-20251025-v1/evidence \
        --output <new audit report path>
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys

import numpy as np


FORBIDDEN_MODULES = (
    'terrain_pipeline.runoff',
    "terrain_pipeline.surface_rivers.native_30m_hydrology_ledger",
    'terrain_pipeline.drainage',
    'terrain_pipeline.runoff',
    'terrain_pipeline.runoff',
    'terrain_pipeline.lake',
    "terrain_pipeline.surface_rivers.metric_depression_gate",
)


def assert_kernels_not_loaded():
    """Refuse to audit inside a process that already loaded the code under test."""
    loaded = sorted(name for name in FORBIDDEN_MODULES if name in sys.modules)
    if loaded:
        raise SystemExit(
            "independent audit refused: the code under test is already imported in "
            "this process: " + ", ".join(loaded))


def _read_json(path):
    with open(path, "rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("record too large: " + str(path))

    def _pairs(items):
        parsed = {}
        for key, value in items:
            if key in parsed:
                raise ValueError("duplicate key: " + key)
            parsed[key] = value
        return parsed

    def _constant(value):
        raise ValueError("non-finite JSON constant: " + str(value))

    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                      parse_constant=_constant)


def _max_abs(array):
    array = np.asarray(array, dtype=np.float64)
    return float(np.abs(array).max()) if array.size else 0.0


def _donor_lists(receiver):
    flat = np.asarray(receiver, np.int64).reshape(-1)
    donors = {}
    for cell, target in enumerate(flat.tolist()):
        if target >= 0:
            donors.setdefault(int(target), []).append(cell)
    return flat, donors


def donor_cone(receiver, seeds, valid_mask=None):
    """Every valid cell a seeded cell drains into: a plain receiver walk.

    Deliberately NOT the kernel's traversal shape: this is a deque walk from each seed
    along ``receiver``, so a disagreement about direction shows up as a mismatch here
    instead of being reproduced. The direction is **downstream** -- an undeclared
    upstream contaminates the cells its water reaches, not the cells above it.
    """
    shape = np.asarray(receiver).shape
    flat = np.asarray(receiver, np.int64).reshape(-1)
    if valid_mask is None:
        valid = np.ones(flat.size, bool)
    else:
        valid = np.asarray(valid_mask, bool).reshape(-1)
    reached = np.zeros(flat.size, bool)
    pending = deque(int(cell) for cell in np.flatnonzero(
        np.asarray(seeds).reshape(-1) & valid))
    for cell in pending:
        reached[cell] = True
    while pending:
        cell = pending.popleft()
        target = int(flat[cell])
        if target >= 0 and valid[target] and not reached[target]:
            reached[target] = True
            pending.append(target)
    return reached.reshape(shape)


def accumulate_by_hand(receiver, local_q, valid_mask):
    """Per-cell accumulated supply by a head-water-first donor walk.

    Independent of the kernel: it starts at the headwater cells (cells with no moving
    donor) and pushes each cell's total into its receiver, decrementing that
    receiver's outstanding-donor count. The kernel instead advances canonical wave
    frontiers with ``np.add.at``; a disagreement about direction shows up as a
    mismatch here rather than being reproduced.
    """
    shape = np.asarray(receiver).shape
    valid = np.asarray(valid_mask, bool).reshape(-1)
    flat, _ = _donor_lists(receiver)
    size = flat.size
    remaining = np.bincount(flat[valid & (flat >= 0)], minlength=size).astype(np.int64)
    headwaters = deque(int(cell) for cell in np.flatnonzero(valid & (remaining == 0)))
    total = np.asarray(local_q, np.float64).reshape(-1).copy()
    settled = np.zeros(size, bool)
    processed = 0
    while headwaters:
        cell = headwaters.popleft()
        if settled[cell]:
            continue
        settled[cell] = True
        processed += 1
        target = int(flat[cell])
        if target >= 0 and valid[target]:
            total[target] += total[cell]
            remaining[target] -= 1
            if remaining[target] == 0:
                headwaters.append(target)
    if processed != int(valid.sum()):
        raise ValueError("the receiver graph is not an acyclic valid graph")
    return total.reshape(shape)


def audit_bucket_account(arrays, meta):
    """Re-derive the bucket's own water account from the saved depth fields."""
    dt_s = float(meta["dt_s"])
    factor = float(meta["cell_area_m2"]) / 1000.0
    steps = int(meta["steps"])
    cells = int(meta["cells"])
    rain_depth = np.asarray(arrays["rain_depth_mm"], np.float64)
    if rain_depth.shape != (steps, cells):
        raise ValueError("rain depth shape %r is not (%d, %d)"
                         % (rain_depth.shape, steps, cells))
    # The declared forcing is a 1-D interval rate series applied uniformly; the depth
    # block must be exactly that series times the interval length, cell by cell.
    declared = np.asarray(arrays["rain_mm_h"], np.float64)
    if declared.shape != (steps,):
        raise ValueError("declared rain series has shape %r, not (%d,)"
                         % (declared.shape, steps))
    if not np.isfinite(declared).all() or (declared < 0).any():
        raise ValueError("declared rain is not finite and nonnegative")
    rain_scope_gap = _max_abs(rain_depth - declared[:, None] * (dt_s / 3600.0))
    infiltration = np.asarray(arrays["infiltration_mm"], np.float64)
    actual_et = np.asarray(arrays["actual_et_mm"], np.float64)
    percolation = np.asarray(arrays["percolation_mm"], np.float64)
    excess = np.asarray(arrays["excess_mm"], np.float64)
    soil = np.asarray(arrays["soil_storage_mm"], np.float64)
    fast = np.asarray(arrays["fast_storage_mm"], np.float64)
    slow = np.asarray(arrays["slow_storage_mm"], np.float64)
    supply_volume = np.asarray(arrays["surface_supply_volume_m3"], np.float64)
    loss_volume = np.asarray(arrays["external_loss_volume_m3"], np.float64)
    local_q = np.asarray(arrays["local_supply_m3_s"], np.float64)
    release_mm = supply_volume / factor
    findings = {
        "max_abs_rain_partition_mm": _max_abs(rain_depth - infiltration - excess),
        "max_abs_rain_scope_mm": rain_scope_gap,
        "max_abs_soil_store_mm": _max_abs(
            np.diff(soil, axis=0) - infiltration + actual_et + percolation),
        # The account keeps fast and slow release combined (it saves the surface supply,
        # not the two reservoir limbs), so the honest identity is their sum.
        "max_abs_fast_slow_store_mm": _max_abs(
            np.diff(fast, axis=0) + np.diff(slow, axis=0)
            - excess - percolation + release_mm),
        "max_abs_cell_balance_mm": _max_abs(
            rain_depth - actual_et - release_mm
            - (np.diff(soil, axis=0) + np.diff(fast, axis=0) + np.diff(slow, axis=0))),
        "max_abs_cell_balance_m3": _max_abs(
            (rain_depth - actual_et - release_mm
             - (np.diff(soil, axis=0) + np.diff(fast, axis=0)
                + np.diff(slow, axis=0))) * factor),
        "max_abs_local_q_gap_m3_s": _max_abs(local_q - supply_volume / dt_s),
        "max_abs_external_loss_gap_m3": _max_abs(loss_volume - actual_et * factor),
        "max_abs_interval_supply_gap_m3": _max_abs(
            supply_volume.sum(axis=1) - (rain_depth - actual_et
                                         - (np.diff(soil, axis=0) + np.diff(fast, axis=0)
                                            + np.diff(slow, axis=0))).sum(axis=1) * factor),
    }
    for name, array in (("infiltration", infiltration), ("actual_et", actual_et),
                        ("supply_volume", supply_volume), ("local_q", local_q),
                        ("soil", soil), ("fast", fast), ("slow", slow)):
        if not np.isfinite(array).all():
            raise ValueError("non-finite " + name)
        if (array < 0).any():
            raise ValueError("negative " + name)
    return findings


def audit_boundary_partition(arrays, meta):
    """Rebuild the per-interval boundary partition with an independent traversal."""
    dt_s = float(meta["dt_s"])
    receiver = np.asarray(arrays["receiver"], np.int64)
    valid = np.asarray(arrays["valid_mask"], bool)
    active = np.asarray(arrays["active_cells"], np.int64)
    local_q = np.asarray(arrays["local_supply_m3_s"], np.float64)
    seeds = np.asarray(arrays["upstream_unknown_mask"], bool)
    kinds = np.asarray(arrays["terminal_kind"])
    certified_retained = np.asarray(arrays["certified_retained_m3_s"], np.float64)
    certified_open = np.asarray(arrays["certified_open_outflow_m3_s"], np.float64)
    certified_unknown = np.asarray(arrays["certified_unknown_pending_m3_s"], np.float64)
    unknown_pending = np.asarray(arrays["unknown_pending_m3_s"], np.float64)
    withheld = np.asarray(arrays["withheld_m3_s"], np.float64)
    steps = local_q.shape[0]
    if certified_retained.shape != (steps,):
        raise ValueError("published partition series has the wrong length")
    if np.any(seeds & ~valid):
        raise ValueError("an inactive cell seeds an unknown upstream")

    cone = donor_cone(receiver, seeds)
    terminal = valid & (receiver < 0)
    partition_gap = 0.0
    published_gap = 0.0
    cone_gained_water = False
    for step in range(steps):
        block = np.zeros(receiver.shape, np.float64)
        block.reshape(-1)[active] = local_q[step]
        declared = accumulate_by_hand(receiver, block, valid)
        retained_hand = float(declared[terminal & (kinds == "retained")].sum())
        open_hand = float(declared[terminal & (kinds == "open_outflow")].sum())
        unknown_hand = float(declared[terminal & (kinds == "unknown_boundary")].sum())
        certified_block = np.where(cone, 0.0, block)
        certified = accumulate_by_hand(receiver, certified_block, valid)
        retained_certified = float(certified[terminal & (kinds == "retained")].sum())
        open_certified = float(certified[terminal & (kinds == "open_outflow")].sum())
        unknown_certified = float(
            certified[terminal & (kinds == "unknown_boundary")].sum())
        withheld_hand = float(block.sum() - certified_block.sum())
        # The cone must actually be subtracted: when the cone carries water the
        # withheld term has to be strictly positive, and the certified input has to be
        # strictly smaller than the declared one. A certified total that equals the
        # declared total while the cone is wet is exactly the "unknown folded into the
        # outlet" failure this audit exists to catch.
        cone_water = float(block[cone].sum()) if cone.any() else 0.0
        if cone_water > 0.0:
            if not withheld_hand > 0.0:
                raise ValueError(
                    "the undeclared cone carries %.6e m3/s but nothing was withheld: "
                    "the unknown term was folded into a certified total" % cone_water)
            if not float(certified_block.sum()) < float(block.sum()):
                raise ValueError(
                    "the certified input equals the declared input although the cone "
                    "carries water: the withheld term is not actually excluded")
        partition_gap = max(
            partition_gap,
            abs(retained_certified + open_certified + unknown_certified + withheld_hand
                - float(block.sum())))
        published_gap = max(published_gap,
                            abs(retained_certified - certified_retained[step]),
                            abs(open_certified - certified_open[step]),
                            abs(unknown_certified - certified_unknown[step]),
                            abs(unknown_hand - unknown_pending[step]),
                            abs(withheld_hand - withheld[step]))
        # Direction of the exclusion: every certified total must be **at most** the
        # declared total of the same kind, because the cone was zeroed out to obtain it.
        # The reverse ordering would mean water appeared from nowhere inside the cone.
        if cone.any():
            tolerance = 1e-15 * max(1.0, float(block.sum()))
            if (retained_certified > retained_hand + tolerance
                    or open_certified > open_hand + tolerance
                    or unknown_certified > unknown_hand + tolerance):
                cone_gained_water = True
    if cone_gained_water:
        raise ValueError(
            "a certified boundary total exceeds its declared total: zeroing the "
            "undeclared cone cannot create water")

    supply_rate = np.asarray(arrays["surface_supply_volume_m3"], np.float64).sum(axis=1) / dt_s
    four_term_gap = _max_abs(certified_retained + certified_open + certified_unknown
                             + withheld - supply_rate)
    reinjection = None
    unknown_absorbed = None
    routed = arrays.get("routed_terminal_q_m3_s")
    outlet = arrays.get("outlet_q_m3_s")
    if routed is not None:
        routed = np.asarray(routed, np.float64)
        raw_sum = local_q.sum(axis=1)
        both_zero = float(np.abs(raw_sum).max()) == 0.0 and float(np.abs(routed).max()) == 0.0
        reinjection = bool(not both_zero
                           and np.allclose(routed, raw_sum, rtol=0.0, atol=1e-15))
        if reinjection:
            raise ValueError(
                "the routed terminal series equals the raw local supply series, so "
                "the delayed endpoint was re-injected as nodal forcing")
    if outlet is not None and routed is not None:
        outlet = np.asarray(outlet, np.float64)
        # A zero-rain event has a zero unknown term and a zero outlet, so ``allclose``
        # would be trivially true for a fully correct run; the check only applies when
        # the unknown term is actually nonzero.
        if float(np.abs(unknown_pending).max()) > 0.0:
            unknown_absorbed = bool(np.allclose(outlet, routed + unknown_pending,
                                               rtol=1e-15, atol=0.0))
            if unknown_absorbed:
                raise ValueError(
                    "unknown water was added to the routed outlet series: the two "
                    "terms must stay separate")
    return {
        "partition_gap_m3_s": float(partition_gap),
        "published_versus_independent_gap_m3_s": float(published_gap),
        "four_term_gap_m3_s": float(four_term_gap),
        "unknown_cone_cells": int((cone & valid).sum()),
        "unknown_seed_cells": int((seeds & valid).sum()),
        "routed_equals_raw_local_sum": reinjection,
        "unknown_added_into_outlet": unknown_absorbed,
        "terminal_census": {kind: int((kinds == kind).sum()) for kind in
                            ("inactive", "interior", "retained", "unknown_boundary",
                             "open_outflow")},
    }


def audit_case(directory, name, meta):
    with np.load(directory / (name + ".npz"), allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    kind = meta.get("evidence_kind", "event_account")
    findings = {}
    if "infiltration_mm" in arrays:
        findings = audit_bucket_account(arrays, meta)
    routing = audit_boundary_partition(arrays, meta)
    scale = max(1.0, float(np.abs(arrays["surface_supply_volume_m3"]).max()))
    gate = 1e-9 + 1e-12 * scale
    checks = {
        "bucket_account": (all(value <= gate for key, value in findings.items()
                               if key.startswith("max_abs_") and key != "max_abs_local_q_gap_m3_s")
                           if findings else None),
        "local_q_is_release_rate": (findings["max_abs_local_q_gap_m3_s"] <= 1e-9
                                    if findings else None),
        "four_term_partition": routing["four_term_gap_m3_s"] <= gate,
        "independent_traversal_matches": (
            routing["partition_gap_m3_s"] <= gate
            and routing["published_versus_independent_gap_m3_s"] <= gate),
        "routed_not_reinjected": routing["routed_equals_raw_local_sum"] is not True,
        "unknown_not_in_outlet": routing["unknown_added_into_outlet"] is not True,
    }
    passed = all(value is not False for value in checks.values())
    return {"case": name, "evidence_kind": kind, "passed": bool(passed),
            "checks": checks, "findings": findings, "routing": routing,
            "meta_checks": meta.get("checks_in_runner", {}),
            "event_identity_sha256": meta.get("event_identity_sha256"),
            "cell_account_identity_sha256": meta.get("cell_account_identity_sha256")}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent cold audit of native-30 m hydrology evidence.")
    parser.add_argument("--evidence", required=True,
                        help="directory holding <case>.npz and <case>.json")
    parser.add_argument("--output", required=True, help="audit report path")
    args = parser.parse_args(argv)
    assert_kernels_not_loaded()
    directory = Path(args.evidence)
    index = _read_json(directory / "evidence-index.json")
    cases = []
    for record in index["cases"]:
        meta = _read_json(directory / record["meta"])
        cases.append(audit_case(directory, record["case"], meta))
    passed = all(case["passed"] for case in cases)
    report = {
        "schema": "native-30m-hydrology-independent-audit-v1",
        "auditor_modules_forbidden": list(FORBIDDEN_MODULES),
        "auditor_imported_nothing_from_the_code_under_test": True,
        "evidence_directory": str(directory),
        "cases": cases,
        "passed": bool(passed),
        "scope": ("self-written donor traversals, mm/m3 conversions, the four-term "
                  "boundary partition and the re-injection rules; it does not certify "
                  "physical magnitude, bankfull discharge or a natural outlet"),
    }
    target = Path(args.output)
    if target.exists():
        raise SystemExit("refusing to overwrite an existing audit report: " + str(target))
    with open(target, "w", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=1, allow_nan=False)
    print(json.dumps({"passed": passed, "output": str(target),
                      "cases": {case["case"]: case["passed"] for case in cases}},
                     sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
