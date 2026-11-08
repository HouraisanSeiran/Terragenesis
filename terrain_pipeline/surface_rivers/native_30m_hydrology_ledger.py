"""Per-cell, per-interval hydrology accounts for the native-30 m catchment event.

Scope of this module
--------------------
This is an **accounting layer**. It adds no runoff law, no delay law, no routing
kernel and no hydraulic law, and it modifies no frozen module. Everything it
reports is derived from arrays that already exist and are already validated
elsewhere:

* the soil-bucket result of
  ``terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff``;
* the finite receiver graph and the per-cell reach ownership produced by
  ``terrain_pipeline.mountain_runoff_routing.build_reaches``;
* ``terrain_pipeline.surface_rivers.metric_network_accumulation.accumulate_network_discharge``
  -- the repository's one finite-graph accumulation kernel -- for the
  unknown-boundary account.

Its job is to make four things explicit and checkable that the event dictionary
previously left implicit:

1. **Where every litre goes, per cell and per physical interval.** Rain splits into
   infiltration and excess; infiltration splits into evaporation, percolation and a
   soil-store change; excess and percolation feed two linear reservoirs whose
   releases are the local river supply. Volumes are reported per cell per interval,
   and the bucket identities are *re-derived here* rather than trusted, so a bucket
   that stopped being conservative cannot pass as an accounted one.
2. **Which part of that account is an external loss and which part is an internal
   transfer.** ``percolation`` moves water from the soil store to the slow store and
   ``excess`` moves it out of the soil store into the fast store: both stay inside
   the account, so adding them to an external flux double-counts them -- the same
   mistake the reach sediment ledger already documents for
   ``eroded_loose``/``deposited``. Only evaporation leaves the bucket's accounting.
3. **That an undeclared upstream is booked as unknown and never becomes a certified
   outlet discharge.** The ``certified_*`` totals are recomputed on the cell-by-cell
   complete set only; the water withheld from them is reported as its own term, and
   the water reaching an ``unknown_boundary`` terminal is reported separately again.
   The three terms are never merged into one number.
4. **That the time-delayed routed terminal series is not re-injected as nodal
   forcing.** The nodal supply is built from the *raw* bucket release, attributed cell
   by cell, its integral is checked against that release, and the delayed terminal
   series carries an explicit ``used_for_dynamic_injection = False`` declaration at
   the call site.

Shape discipline (the defect this revision fixes)
-------------------------------------------------
``accumulate_network_discharge`` accepts exactly ``receiver.shape``, i.e. a
``[Z, X]`` block. An earlier revision of this module built ``[T, Z, X]`` blocks and
handed them straight to that kernel, so **every** call failed with
``local_q_m3_s must have matching shape and exact dtype`` and
``hydrology_ledger`` had therefore never run at all. The block builder now
normalises to ``[T, Z, X]`` internally and slices one interval per kernel call;
``[T, Z, X]`` and ``[T, Z*X]`` remain the two accepted spellings and both are
checked against the receiver shape before anything is accumulated.

Subseeds
--------
``world_seed`` is fixed by ``CONTRIBUTING.md`` (20261020). Purpose subseeds are
derived deterministically from the world seed and a stable purpose name with
SHA-256 only -- never ``hash()``, never time, never system entropy. This stage
consumes no noise, so every derived purpose is recorded as **declared and unused**
rather than presented as a noise-driven process.

Nothing here is a certification: no natural outlet, no bankfull discharge, no
calibrated parameter set, no hydraulics.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge


__all__ = [
    "ACCOUNT_ALGORITHM",
    "ACCOUNT_CELL_FIELDS",
    "ACCOUNT_STATE_FIELDS",
    "ALGORITHM",
    "EXTERNAL_LOSS_DEFINITION",
    "INTERNAL_TRANSFER_DEFINITION",
    "LEDGER_FIELDS_PER_ENTRY",
    "MAX_ACCOUNT_BYTES",
    "MAX_LEDGER_BYTES",
    "MAX_LEDGER_ENTRIES",
    "NODAL_SUPPLY_DEFINITION",
    "OWNERSHIP_RULE",
    "SCHEMA",
    "SUBSEED_DERIVATION",
    "SUBSEED_PURPOSES",
    "UNKNOWN_SEMANTICS",
    "account_budget",
    "attribute_declared_nodes",
    "cell_hydrology_account",
    "hydrology_ledger",
    "ledger_budget",
    "node_supply_ledger",
    "purpose_subseeds",
    "storage_ledger",
    "supply_ledger",
    "unknown_boundary_ledger",
    "window_terminal_kind",
]


ALGORITHM = "native-30m-hydrology-ledger-irregular-v3"
SCHEMA = "native-30m-hydrology-ledger-dict-v2"
ACCOUNT_ALGORITHM = "native-30m-cell-hydrology-account-irregular-v2"

# Engineering budgets, not physical thresholds. The ledger stores several [T, C]
# float64 fields, so it refuses a window that would not fit *before* allocating
# anything. This keeps the accounting available at the scale it is verified at
# without ever silently truncating.
MAX_LEDGER_ENTRIES = 2_000_000
MAX_LEDGER_BYTES = 192 * 1024 * 1024
LEDGER_FIELDS_PER_ENTRY = 8

# The per-cell, per-interval account is wider: it keeps the depth fields, the
# volume fields and the three stores. Its budget is stated separately so that a
# refusal names the account and not the narrower split ledger.
MAX_ACCOUNT_BYTES = 640 * 1024 * 1024
ACCOUNT_CELL_FIELDS = 9
ACCOUNT_STATE_FIELDS = 3

SUBSEED_DERIVATION = (
    "subseed = int.from_bytes(sha256('terragenesis/world-seed-subseed-v1'"
    "'|world_seed=' + seed + '|purpose=' + purpose)[:8], 'big') & (2**53 - 1); "
    "deterministic, no run time, no system entropy and no builtin hash()")
SUBSEED_PURPOSES = ("rain_series_modulation", "soil_initial_field", "event_time_phase")

EXTERNAL_LOSS_DEFINITION = (
    "external_loss_volume_m3 is the evaporation volume (actual_et_mm * cell_area) "
    "only: it is the single term that leaves the bucket's own accounting")
INTERNAL_TRANSFER_DEFINITION = (
    "internal_transfer_volume_m3 is percolation_volume_m3 + excess_volume_m3: water "
    "moved between stores of the same bucket within the same interval. It must never "
    "be added to an external flux; doing so double-counts it")
NODAL_SUPPLY_DEFINITION = (
    "nodal_supply is the raw bucket release attributed to the reach that owns each "
    "catchment cell (exactly one owner per cell), so every cell's local Q is injected "
    "exactly once and the time-delayed routed terminal series is not injected again")
UNKNOWN_SEMANTICS = (
    "upstream_unknown_mask marks valid cells whose external contributions are not "
    "declared; the flag propagates downstream along the receiver graph. Water on "
    "those cells is excluded from every certified_* total and reported as "
    "withheld/unknown instead, so an undeclared upstream can never be read as a "
    "certified outlet discharge")
OWNERSHIP_RULE = (
    "node k owns the valid cells whose accumulated upstream cell count lies in "
    "(accumulated[k - 1], accumulated[k]]; the counts are the unit-weight "
    "accumulation on the declared receiver graph, so the rule is a pure function of "
    "the topology and of the declared node path")
ACCOUNT_SEMANTICS = (
    "the per-cell, per-interval account places the bucket's own depth fields, the "
    "derived volumes, the three stores and the raw local supply on the declared "
    "receiver grid, cell by cell, and reports the outlet, the withheld and the "
    "unknown terms as separate per-interval series. Every field is either a bucket "
    "field regrouped or a quantity re-derived here; nothing is re-simulated")


# --------------------------------------------------------------------------- #
# deterministic purpose subseeds
# --------------------------------------------------------------------------- #

def _world_seed(value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer)) or int(value) < 0):
        raise ValueError("invalid_world_seed: a nonnegative integer is required")
    return int(value)


def _purpose(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(
            "invalid_subseed_purpose: a nonempty purpose string of at most 256 "
            "characters is required")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
           for character in value):
        raise ValueError(
            "invalid_subseed_purpose: purposes are stable lowercase names [a-z0-9_]")
    return value


def purpose_subseeds(world_seed, purposes=SUBSEED_PURPOSES):
    """Deterministic per-purpose subseeds derived from one fixed world seed."""
    seed = _world_seed(world_seed)
    if isinstance(purposes, str) or not isinstance(purposes, (tuple, list)):
        raise ValueError(
            "invalid_subseed_purpose_list: a sequence of purposes is required")
    if len(purposes) < 1 or len(set(purposes)) != len(purposes):
        raise ValueError("invalid_subseed_purpose_list: purposes must be unique")
    mask = (1 << 53) - 1
    derived = {}
    for purpose in purposes:
        name = _purpose(purpose)
        payload = ("terragenesis/world-seed-subseed-v1|world_seed=%d|purpose=%s"
                   % (seed, name)).encode("ascii")
        derived[name] = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") & mask
    return {
        "world_seed": seed,
        "derivation": SUBSEED_DERIVATION,
        "subseeds": derived,
        "noise_used": False,
        "note": ("this stage consumes no noise: the declared event is a fixed interval "
                 "series, so the derived subseeds are recorded and marked unused "
                 "instead of being presented as a noise-driven process"),
    }


# --------------------------------------------------------------------------- #
# budget and small guards
# --------------------------------------------------------------------------- #

def _count(value, name):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer)) or int(value) < 0):
        raise ValueError("invalid_%s: a nonnegative integer is required" % name)
    return int(value)


def ledger_budget(steps, cells, nodes):
    """Refuse an accounting window before a single ledger array is allocated."""
    steps = _count(steps, "ledger_steps")
    cells = _count(cells, "ledger_cells")
    nodes = _count(nodes, "ledger_nodes")
    entries = steps * cells
    if steps < 1 or cells < 1:
        raise ValueError("invalid_ledger_shape: a nonempty step and cell axis is required")
    if entries > MAX_LEDGER_ENTRIES:
        raise ValueError(
            "budget_hydrology_ledger: %d intervals x %d cells = %d entries exceed "
            "the ledger MAX_LEDGER_ENTRIES=%d; nothing is truncated and no limit is "
            "raised" % (steps, cells, entries, MAX_LEDGER_ENTRIES))
    estimated_bytes = LEDGER_FIELDS_PER_ENTRY * 8 * (entries + cells)
    if estimated_bytes > MAX_LEDGER_BYTES:
        raise ValueError(
            "budget_hydrology_ledger: estimated %d bytes exceed the ledger "
            "MAX_LEDGER_BYTES=%d" % (estimated_bytes, MAX_LEDGER_BYTES))
    return {"steps": steps, "cells": cells, "nodes": nodes, "entries": entries,
            "estimated_bytes": estimated_bytes,
            "max_entries": MAX_LEDGER_ENTRIES, "max_bytes": MAX_LEDGER_BYTES,
            "fields_per_entry": LEDGER_FIELDS_PER_ENTRY}


def account_budget(steps, cells, grid_cells):
    """Refuse a per-cell account window before any of its arrays exists."""
    steps = _count(steps, "account_steps")
    cells = _count(cells, "account_cells")
    grid_cells = _count(grid_cells, "account_grid_cells")
    if steps < 1 or cells < 1 or grid_cells < cells:
        raise ValueError(
            "invalid_account_shape: a nonempty step/cell axis and grid_cells >= "
            "cells are required")
    entries = steps * cells
    ledger_bytes = (ACCOUNT_CELL_FIELDS + ACCOUNT_STATE_FIELDS) * 8 * entries
    grid_bytes = 8 * (grid_cells + steps * grid_cells // max(1, steps))
    estimated_bytes = ledger_bytes + 8 * grid_cells
    if estimated_bytes > MAX_ACCOUNT_BYTES:
        raise ValueError(
            "budget_cell_account: %d intervals x %d cells x %d fields = %d bytes "
            "exceed the account MAX_ACCOUNT_BYTES=%d; nothing is truncated and no "
            "limit is raised"
            % (steps, cells, ACCOUNT_CELL_FIELDS + ACCOUNT_STATE_FIELDS,
               estimated_bytes, MAX_ACCOUNT_BYTES))
    return {"steps": steps, "cells": cells, "grid_cells": grid_cells,
            "entries": entries, "estimated_bytes": int(estimated_bytes),
            "max_bytes": MAX_ACCOUNT_BYTES,
            "fields_per_entry": ACCOUNT_CELL_FIELDS + ACCOUNT_STATE_FIELDS,
            "grid_bytes_note": grid_bytes}


def _regular(array, name, ndim, dtype):
    if (not isinstance(array, np.ndarray) or array.ndim != ndim
            or array.dtype != np.dtype(dtype)):
        raise ValueError(
            "invalid_%s: a %d-D %s ndarray is required" % (name, ndim, dtype))
    return array


def _finite_nonnegative(array, name):
    if not np.isfinite(array).all() or (array < 0).any():
        raise ValueError(
            "invalid_%s: the ledger accounts only for finite nonnegative stores"
            % name)
    return array


def _scalar(value, name, maximum, positive=False):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not math.isfinite(value) or value < 0 or value > maximum
            or (positive and value == 0)):
        raise ValueError(
            "invalid_%s: finite %s <= %r required"
            % (name, "positive" if positive else "nonnegative", maximum))
    return float(value)


def _relative(residual, gross):
    return float(abs(residual) / gross) if gross > 0 else None


def _max_abs(array):
    return float(np.abs(array).max(initial=0.0)) if np.size(array) else 0.0


def _array_sha256(array):
    digest = hashlib.sha256()
    array = np.ascontiguousarray(array)
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# 1. per-cell, per-interval supply partition
# --------------------------------------------------------------------------- #

_BUCKET_STEP_KEYS = ("infiltration_mm", "actual_et_mm", "percolation_mm", "excess_mm",
                     "fast_release_mm", "slow_release_mm", "local_q_m3_s")
_BUCKET_STATE_KEYS = ("soil_mm", "fast_mm", "slow_mm")


def supply_ledger(bucket, *, dt_s, cell_area_m2, tolerance=1e-12):
    """Derive the per-cell per-interval water partition from a bucket result.

    Every ``*_volume_m3`` field is ``[intervals, cells]``; interval totals are
    ``[intervals]``. Nothing is re-simulated: the fields are the bucket's own saved
    arrays, regrouped, with the four bucket identities and the release rate re-derived
    here so a non-conservative bucket is refused rather than reported.
    """
    if not isinstance(bucket, dict):
        raise ValueError("bucket_result_required: a bucket result dict is required")
    missing = [key for key in ("rain_mm_h",) + _BUCKET_STEP_KEYS + _BUCKET_STATE_KEYS
               if key not in bucket]
    if missing:
        raise ValueError("bucket_result_incomplete: missing %s" % (missing,))
    dt_s = _scalar(dt_s, "dt_s", 1e7, positive=True)
    if dt_s < 1e-6:
        raise ValueError("invalid_dt_s: dt_s must be >= 1e-6 s")
    cell_area_m2 = _scalar(cell_area_m2, "cell_area_m2", 1e12, positive=True)
    rain_in = _regular(bucket["rain_mm_h"], "rain_mm_h", 2, "float64")
    steps, cells = rain_in.shape
    if steps < 1 or cells < 1:
        raise ValueError("invalid_bucket_shape: a nonempty [T, N] rain block is required")
    ledger_budget(steps, cells, 0)
    fields = {}
    for key in _BUCKET_STEP_KEYS:
        array = _regular(bucket[key], key, 2, "float64")
        if array.shape != (steps, cells):
            raise ValueError(
                "bucket_result_inconsistent: %s has shape %r, not (%d, %d)"
                % (key, array.shape, steps, cells))
        fields[key] = _finite_nonnegative(array, key)
    states = {}
    for key in _BUCKET_STATE_KEYS:
        array = _regular(bucket[key], key, 2, "float64")
        if array.shape != (steps + 1, cells):
            raise ValueError(
                "bucket_result_inconsistent: %s has shape %r, not (%d, %d)"
                % (key, array.shape, steps + 1, cells))
        states[key] = _finite_nonnegative(array, key)

    hours = dt_s / 3600.0
    volume_factor = cell_area_m2 / 1000.0
    rain_depth_mm = _finite_nonnegative(rain_in, "rain_mm_h") * hours
    infiltration = fields["infiltration_mm"]
    actual_et = fields["actual_et_mm"]
    percolation = fields["percolation_mm"]
    excess = fields["excess_mm"]
    fast_release = fields["fast_release_mm"]
    slow_release = fields["slow_release_mm"]
    local_q = fields["local_q_m3_s"]
    soil, fast, slow = states["soil_mm"], states["fast_mm"], states["slow_mm"]

    # The four bucket identities, recomputed here (cross-interval, so no saved
    # residual ledger is reused).
    identity = {
        "rain_partition_mm": _max_abs(rain_depth_mm - infiltration - excess),
        "soil_store_mm": _max_abs(
            np.diff(soil, axis=0) - infiltration + actual_et + percolation),
        "fast_store_mm": _max_abs(np.diff(fast, axis=0) - excess + fast_release),
        "slow_store_mm": _max_abs(
            np.diff(slow, axis=0) - percolation + slow_release),
    }
    mm_scale = max(1.0, _max_abs(rain_depth_mm))
    mm_gate = 1e-9 + 1e-12 * mm_scale
    for name, value in identity.items():
        if value > mm_gate:
            raise ValueError(
                "nonconservative_bucket_interval: the recomputed %s identity does not "
                "close (max |residual| = %.6e mm, gate %.6e mm)"
                % (name, value, mm_gate))

    rain_volume = rain_depth_mm * volume_factor
    infiltration_volume = infiltration * volume_factor
    et_volume = actual_et * volume_factor
    percolation_volume = percolation * volume_factor
    excess_volume = excess * volume_factor
    fast_release_volume = fast_release * volume_factor
    slow_release_volume = slow_release * volume_factor
    soil_store_volume = soil[:-1] * volume_factor
    fast_store_volume = fast[:-1] * volume_factor
    slow_store_volume = slow[:-1] * volume_factor
    soil_column_volume = soil_store_volume + fast_store_volume + slow_store_volume
    surface_supply_volume = fast_release_volume + slow_release_volume
    storage_change_volume = (np.diff(soil, axis=0) + np.diff(fast, axis=0)
                             + np.diff(slow, axis=0)) * volume_factor
    internal_transfer_volume = percolation_volume + excess_volume
    balance_residual_volume = (rain_volume - et_volume - surface_supply_volume
                               - storage_change_volume)

    m3_scale = max(1.0, _max_abs(rain_volume))
    m3_gate = 1e-8 + float(tolerance) * m3_scale
    balance_gap = _max_abs(balance_residual_volume)
    if balance_gap > m3_gate:
        raise ValueError(
            "nonconservative_bucket_interval: rain - ET - river supply - storage "
            "change does not close (max |residual| = %.6e m3, gate %.6e m3)"
            % (balance_gap, m3_gate))
    q_gap = _max_abs(local_q - surface_supply_volume / dt_s)
    q_gate = 1e-12 * max(1.0, _max_abs(local_q))
    if q_gap > q_gate:
        raise ValueError(
            "bucket_supply_mismatch: local_q_m3_s is not the release rate of the "
            "reported reservoir releases (max |gap| = %.6e m3/s)" % q_gap)

    interval_rain_m3 = rain_volume.sum(axis=1)
    interval_et_m3 = et_volume.sum(axis=1)
    interval_infiltration_m3 = infiltration_volume.sum(axis=1)
    interval_percolation_m3 = percolation_volume.sum(axis=1)
    interval_excess_m3 = excess_volume.sum(axis=1)
    interval_supply_m3 = surface_supply_volume.sum(axis=1)
    interval_storage_change_m3 = storage_change_volume.sum(axis=1)
    interval_internal_transfer_m3 = internal_transfer_volume.sum(axis=1)
    return {
        "algorithm": ALGORITHM,
        "schema": SCHEMA,
        "dt_s": dt_s,
        "cell_area_m2": cell_area_m2,
        "volume_factor_m3_per_mm": volume_factor,
        "steps": int(steps),
        "cells": int(cells),
        "cell_order": ("columns follow the event's active_cells order; the ledger is "
                       "never reordered here"),
        "rain_depth_mm": rain_depth_mm,
        "rain_volume_m3": rain_volume,
        "infiltration_mm": infiltration,
        "infiltration_volume_m3": infiltration_volume,
        "actual_et_mm": actual_et,
        "et_volume_m3": et_volume,
        "percolation_mm": percolation,
        "percolation_volume_m3": percolation_volume,
        "excess_mm": excess,
        "excess_volume_m3": excess_volume,
        "fast_release_mm": fast_release,
        "fast_release_volume_m3": fast_release_volume,
        "slow_release_mm": slow_release,
        "slow_release_volume_m3": slow_release_volume,
        "surface_supply_volume_m3": surface_supply_volume,
        "local_supply_m3_s": local_q,
        "storage_change_volume_m3": storage_change_volume,
        "soil_column_volume_m3": soil_column_volume,
        "balance_residual_m3": balance_residual_volume,
        "external_loss_volume_m3": et_volume,
        "internal_transfer_volume_m3": internal_transfer_volume,
        "interval_rain_m3": interval_rain_m3,
        "interval_infiltration_m3": interval_infiltration_m3,
        "interval_percolation_m3": interval_percolation_m3,
        "interval_excess_m3": interval_excess_m3,
        "interval_et_m3": interval_et_m3,
        "interval_external_loss_m3": interval_et_m3,
        "interval_internal_transfer_m3": interval_internal_transfer_m3,
        "interval_surface_supply_m3": interval_supply_m3,
        "interval_storage_change_m3": interval_storage_change_m3,
        "cumulative_rain_m3": float(interval_rain_m3.sum()),
        "cumulative_external_loss_m3": float(interval_et_m3.sum()),
        "cumulative_internal_transfer_m3": float(interval_internal_transfer_m3.sum()),
        "cumulative_surface_supply_m3": float(interval_supply_m3.sum()),
        "cumulative_storage_change_m3": float(interval_storage_change_m3.sum()),
        "definitions": {
            "external_loss": EXTERNAL_LOSS_DEFINITION,
            "internal_transfer": INTERNAL_TRANSFER_DEFINITION,
            "external_loss_and_internal_transfer_are_separate": (
                "percolation and excess are internal transfers reported in their own "
                "term; adding them to external_loss double-counts them"),
            "bucket_kernel": ("terrain_pipeline.rainfall_runoff"
                              ".simulate_rainfall_runoff (unchanged)"),
        },
        "checks": {
            "max_abs_balance_residual_m3": balance_gap,
            "relative_balance_residual": _relative(balance_gap, m3_scale),
            "max_abs_local_q_gap_m3_s": q_gap,
            "max_abs_rain_partition_residual_mm": identity["rain_partition_mm"],
            "max_abs_soil_store_residual_mm": identity["soil_store_mm"],
            "max_abs_fast_store_residual_mm": identity["fast_store_mm"],
            "max_abs_slow_store_residual_mm": identity["slow_store_mm"],
            "internal_transfer_included_in_external_loss": False,
        },
    }


# --------------------------------------------------------------------------- #
# 2. per-cell, per-stage store account
# --------------------------------------------------------------------------- #

def storage_ledger(bucket, *, dt_s, cell_area_m2):
    """Per-cell per-stage stores in mm and m3, with the closing residuals."""
    supply = supply_ledger(bucket, dt_s=dt_s, cell_area_m2=cell_area_m2)
    factor = supply["volume_factor_m3_per_mm"]
    soil = bucket["soil_mm"]
    fast = bucket["fast_mm"]
    slow = bucket["slow_mm"]
    total_mm = soil + fast + slow
    total_m3 = total_mm * factor
    change_m3 = np.diff(total_m3, axis=0)
    reported = supply["storage_change_volume_m3"]
    gap = _max_abs(change_m3 - reported)
    scale = max(1.0, _max_abs(total_m3))
    if gap > 1e-12 * scale:
        raise ValueError(
            "storage_ledger_mismatch: the per-stage change does not reproduce the "
            "supply ledger's storage change (max |residual| = %.6e m3)" % gap)
    return {
        "soil_mm": soil,
        "fast_mm": fast,
        "slow_mm": slow,
        "soil_store_m3": soil * factor,
        "fast_store_m3": fast * factor,
        "slow_store_m3": slow * factor,
        "total_store_mm": total_mm,
        "total_store_m3": total_m3,
        "storage_change_m3": change_m3,
        "interval_total_store_m3": total_m3[:-1],
        "interval_storage_change_m3": change_m3.sum(axis=1),
        "initial_store_m3": total_m3[0],
        "final_store_m3": total_m3[-1],
        "cumulative_storage_change_m3": total_m3[-1] - total_m3[0],
        "checks": {
            "max_abs_storage_residual_m3": gap,
            "relative_storage_residual": _relative(gap, max(1.0, _max_abs(change_m3))),
            "total_cumulative_change_m3": float((total_m3[-1] - total_m3[0]).sum()),
        },
    }


# --------------------------------------------------------------------------- #
# 3. unknown boundary versus certified outlet
# --------------------------------------------------------------------------- #

def _local_q_block(local_q_m3_s, shape, valid_mask):
    """Normalise a per-interval local-Q input to ``[T, Z, X]``.

    Two spellings are accepted and both are unambiguous: ``[T, Z, X]`` on the receiver
    grid itself, or ``[T, Z*X]`` in the same flat order the receiver uses. A block that
    matches neither is refused; nothing is broadcast, tiled or guessed.

    The returned block is **always three-dimensional**; callers hand one ``[Z, X]``
    slice at a time to ``accumulate_network_discharge``, which accepts exactly the
    receiver shape. Handing it the three-dimensional block was the defect that made
    every call of this module fail.
    """
    if (not isinstance(local_q_m3_s, np.ndarray)
            or local_q_m3_s.dtype != np.dtype("float64")):
        raise ValueError(
            "invalid_local_q_m3_s: a float64 local-Q block is required")
    if local_q_m3_s.ndim == 3:
        if tuple(local_q_m3_s.shape[1:]) != tuple(shape):
            raise ValueError(
                "invalid_local_q_m3_s: a [T, Z, X] block must match the receiver shape "
                "%r, got %r" % (tuple(shape), tuple(local_q_m3_s.shape[1:])))
        block = local_q_m3_s
    elif local_q_m3_s.ndim == 2:
        if local_q_m3_s.shape[1] != int(np.prod(shape)):
            raise ValueError(
                "invalid_local_q_m3_s: the flat cell axis must equal receiver.size "
                "(%d), got %d" % (int(np.prod(shape)), local_q_m3_s.shape[1]))
        block = local_q_m3_s.reshape((local_q_m3_s.shape[0],) + tuple(shape))
    else:
        raise ValueError(
            "invalid_local_q_m3_s: a [T, Z, X] or [T, Z*X] float64 block is required")
    if block.shape[0] < 1:
        raise ValueError("invalid_local_q_m3_s: at least one interval is required")
    if not np.isfinite(block).all() or (block < 0).any():
        raise ValueError(
            "invalid_local_q_m3_s: local Q must be finite and nonnegative")
    if np.any(block[:, ~valid_mask] != 0.0):
        raise ValueError(
            "invalid_local_q_m3_s: an inactive cell must carry exactly zero local Q")
    return np.ascontiguousarray(block)


def unknown_boundary_ledger(receiver, valid_mask, terminal_kind, local_q_m3_s, *,
                            upstream_unknown_mask=None):
    """Split one interval's discharge into certified, withheld and unknown terms.

    Three quantities are produced and are never merged:

    ``certified_retained_m3_s`` / ``certified_open_outflow_m3_s``
        the terminal totals recomputed with every cell inside the unknown cone zeroed
        out, so water downstream of an undeclared upstream cannot appear here;
    ``withheld_local_q_m3_s``
        exactly the local discharge excluded to obtain those totals, i.e. the water a
        naive summation would have folded into the outlet;
    ``unknown_pending_m3_s``
        the water that reaches a terminal explicitly declared ``unknown_boundary``.

    Neither ``unknown_pending_m3_s`` nor ``withheld_local_q_m3_s`` is part of any
    ``certified_retained``/``certified_open_outflow`` total, and the four terms
    partition the declared input exactly:

    ``declared_input == certified_retained + certified_open_outflow
    + certified_unknown_pending + withheld``

    The certified unknown term is recomputed on the certified (cone-zeroed) run, not
    copied from the declared run: water withheld upstream never reaches the unknown
    terminal either, so the two differ and substituting one for the other would make
    the partition close only by accident.
    """
    receiver = _regular(receiver, "receiver", 2, "int64")
    valid_mask = _regular(valid_mask, "valid_mask", 2, "bool")
    if receiver.shape != valid_mask.shape:
        raise ValueError("invalid_shape: receiver and valid_mask must share one shape")
    if (not isinstance(terminal_kind, np.ndarray)
            or terminal_kind.shape != receiver.shape or terminal_kind.dtype.kind != "U"):
        raise ValueError("matching Unicode terminal_kind array required")
    block = _local_q_block(local_q_m3_s, receiver.shape, valid_mask)
    steps = int(block.shape[0])
    ledger_budget(steps, int(receiver.size), 0)
    if np.any(np.asarray(terminal_kind)[~valid_mask] != "inactive"):
        raise ValueError(
            "invalid_terminal_kind: an inactive cell must be labelled 'inactive'")
    if np.any(np.asarray(terminal_kind)[valid_mask & (receiver >= 0)] != "interior"):
        raise ValueError(
            "invalid_terminal_kind: a valid cell with a receiver must be labelled "
            "'interior'")
    unknown_shape = np.zeros(receiver.shape, bool)
    if upstream_unknown_mask is not None:
        _regular(upstream_unknown_mask, "upstream_unknown_mask", 2, "bool")
        if upstream_unknown_mask.shape != receiver.shape:
            raise ValueError(
                "invalid_upstream_unknown_mask: it must share the receiver shape")
        unknown_shape = upstream_unknown_mask
    if np.any(unknown_shape & ~valid_mask):
        raise ValueError(
            "unknown_seed_outside_valid: an inactive cell cannot seed an undeclared "
            "upstream contribution")

    declared = accumulate_network_discharge(
        receiver, block[0], valid_mask, terminal_kind=terminal_kind,
        upstream_unknown_mask=unknown_shape)
    complete_mask = np.asarray(declared["complete_mask"])
    certified_block = np.where(complete_mask, block[0], 0.0)
    certified = accumulate_network_discharge(
        receiver, certified_block, valid_mask, terminal_kind=terminal_kind)

    withheld_by_cell = block[0] - certified_block
    withheld = float(withheld_by_cell.sum(dtype=np.float64))
    certified_input = float(certified["input_total_m3_s"])
    declared_input = float(declared["input_total_m3_s"])
    certified_unknown = float(certified["unknown_pending_m3_s"])
    scale = max(1.0, abs(declared_input))
    split_gap = (certified_input + withheld) - declared_input
    if abs(split_gap) > 1e-12 * scale:
        raise ValueError(
            "unknown_boundary_mismatch: certified + withheld does not reproduce the "
            "declared input (%.6e + %.6e vs %.6e m3/s)"
            % (certified_input, withheld, declared_input))
    partition_gap = (float(certified["retained_m3_s"])
                     + float(certified["open_outflow_m3_s"])
                     + certified_unknown + withheld) - declared_input
    if abs(partition_gap) > 1e-12 * scale:
        raise ValueError(
            "unknown_boundary_mismatch: certified retained + certified open + "
            "certified unknown + withheld does not reproduce the declared input "
            "(gap %.6e m3/s); the four boundary terms must partition it exactly"
            % partition_gap)
    for name, ledger in (("declared", declared), ("certified", certified)):
        if abs(float(ledger["residual_m3_s"])) > 1e-12 * scale:
            raise ValueError(
                "unknown_boundary_mismatch: the %s terminal account does not close "
                "(residual %.6e m3/s)" % (name, float(ledger["residual_m3_s"])))
    contaminated = bool(np.any(certified_block[~complete_mask & valid_mask] != 0.0))
    if contaminated:
        raise ValueError(
            "unknown_folded_into_outlet: a cell inside the undeclared cone still "
            "carries water in the certified total")
    unknown_kind = (np.asarray(terminal_kind) == "unknown_boundary")
    unknown_local = float(block[0][unknown_kind & valid_mask].sum(dtype=np.float64))
    return {
        "steps": steps,
        "upstream_unknown_mask": np.array(unknown_shape, copy=True),
        "complete_mask": np.array(complete_mask, copy=True),
        "unknown_seed_cells": int(unknown_shape.sum()),
        "incomplete_cone_cells": int((~complete_mask & valid_mask).sum()),
        "complete_cells": int((complete_mask & valid_mask).sum()),
        "terminal_count_unknown_boundary": int(unknown_kind.sum()),
        "unknown_terminal_local_q_m3_s": unknown_local,
        "unknown_pending_m3_s": float(declared["unknown_pending_m3_s"]),
        "retained_m3_s": float(declared["retained_m3_s"]),
        "open_outflow_m3_s": float(declared["open_outflow_m3_s"]),
        "certified_retained_m3_s": float(certified["retained_m3_s"]),
        "certified_open_outflow_m3_s": float(certified["open_outflow_m3_s"]),
        "certified_unknown_pending_m3_s": certified_unknown,
        "certified_input_m3_s": certified_input,
        "declared_input_m3_s": declared_input,
        "withheld_local_q_m3_s": withheld,
        "withheld_local_q_by_cell_m3_s": np.array(withheld_by_cell, copy=True),
        "certified_by_cell_m3_s": np.array(certified["known_routed_q_m3_s"], copy=True),
        "declared_by_cell_m3_s": np.array(declared["known_routed_q_m3_s"], copy=True),
        "terminal_q_m3_s": np.array(declared["terminal_q_m3_s"], copy=True),
        "semantics": UNKNOWN_SEMANTICS,
        "checks": {
            "certified_plus_withheld_minus_declared_m3_s": float(split_gap),
            "four_term_partition_minus_declared_m3_s": float(partition_gap),
            "declared_terminal_residual_m3_s": float(declared["residual_m3_s"]),
            "certified_terminal_residual_m3_s": float(certified["residual_m3_s"]),
            "unknown_in_certified_outlet": contaminated,
            "unknown_folded_into_outlet": False,
            "withheld_is_nonnegative": bool(withheld >= 0.0),
            "policy": declared["policy"],
        },
    }


def hydrology_ledger(bucket, receiver, valid_mask, *, cell_area_m2, dt_s,
                     active_cells, terminal_kind=None, upstream_unknown_mask=None,
                     owner_of_cell=None, node_cell_ids=None, world_seed=None,
                     routed_terminal_q_m3_s=None, origin_native_xz=(0, 0)):
    """Assemble the full per-cell, per-interval native-30 m hydrology account.

    ``active_cells`` are the flat cell ids of the bucket's ``[T, N]`` block, in the
    bucket's own column order -- the same ids the event report already publishes. The
    bucket is therefore accounted for at the resolution it was run at, and the local
    release is then placed on the declared finite receiver graph, one cell per column.

    Per interval the report carries, separately and never merged: rain, infiltration,
    evaporation (the external loss), percolation and excess (internal transfers),
    surface supply, storage change and the closing residual; plus the accumulation
    split into certified retained, certified open outflow, withheld-because-undeclared
    and the water standing on an ``unknown_boundary`` terminal. ``routing.nodal_supply``
    is the raw release attributed to declared nodes; ``routed_terminal_q_m3_s`` is
    declared as **not** used for dynamic injection, so a delayed endpoint series can
    never be injected a second time.
    """
    supply = supply_ledger(bucket, dt_s=dt_s, cell_area_m2=cell_area_m2)
    storage = storage_ledger(bucket, dt_s=dt_s, cell_area_m2=cell_area_m2)
    receiver = _regular(receiver, "receiver", 2, "int64")
    valid_mask = _regular(valid_mask, "valid_mask", 2, "bool")
    if receiver.shape != valid_mask.shape:
        raise ValueError("invalid_shape: receiver and valid_mask must share one shape")
    _regular(active_cells, "active_cells", 1, "int64")
    cells = supply["cells"]
    if active_cells.size != cells:
        raise ValueError(
            "invalid_active_cells: %d active cells given for a %d-column bucket block"
            % (int(active_cells.size), cells))
    if np.unique(active_cells).size != cells:
        raise ValueError("invalid_active_cells: active cells must be unique")
    if (active_cells < 0).any() or (active_cells >= receiver.size).any():
        raise ValueError(
            "invalid_active_cells: every active cell must be a flat id of the grid")
    if np.any(~valid_mask.reshape(-1)[active_cells]):
        raise ValueError(
            "invalid_active_cells: a cell carrying local supply must be valid on the "
            "receiver graph")
    kinds = terminal_kind
    if kinds is None:
        kinds = window_terminal_kind(receiver, valid_mask, origin_native_xz=origin_native_xz,
            world_seed=20261020 if world_seed is None else world_seed)["terminal_kind"]
    else:
        if (not isinstance(kinds, np.ndarray) or kinds.shape != receiver.shape
                or kinds.dtype.kind != "U"):
            raise ValueError("matching Unicode terminal_kind array required")
        kinds = np.array(kinds, copy=True)
    active = np.asarray(active_cells, dtype=np.int64)
    steps = supply["steps"]
    block = np.zeros((steps,) + tuple(receiver.shape), dtype=np.float64)
    block.reshape(steps, -1)[:, active] = supply["local_supply_m3_s"]

    withheld = np.zeros(steps, dtype=np.float64)
    certified_retained = np.zeros(steps, dtype=np.float64)
    certified_open = np.zeros(steps, dtype=np.float64)
    declared_retained = np.zeros(steps, dtype=np.float64)
    unknown_pending = np.zeros(steps, dtype=np.float64)
    certified_unknown = np.zeros(steps, dtype=np.float64)
    complete_cells = np.zeros(steps, dtype=np.int64)
    for step in range(steps):
        record = unknown_boundary_ledger(
            receiver, valid_mask, kinds, block[step:step + 1],
            upstream_unknown_mask=upstream_unknown_mask)
        withheld[step] = record["withheld_local_q_m3_s"]
        certified_retained[step] = record["certified_retained_m3_s"]
        certified_open[step] = record["certified_open_outflow_m3_s"]
        certified_unknown[step] = record["certified_unknown_pending_m3_s"]
        declared_retained[step] = record["retained_m3_s"]
        unknown_pending[step] = record["unknown_pending_m3_s"]
        complete_cells[step] = record["complete_cells"]

    routing = {
        "routed_terminal_q_m3_s": (np.array(routed_terminal_q_m3_s, copy=True)
                                   if routed_terminal_q_m3_s is not None else None),
        "used_for_dynamic_injection": False,
        "declaration": ("the routed terminal series carries travel delay and is a "
                        "diagnostic of the endpoint; dynamic forcing must consume the "
                        "raw per-cell release attributed to nodes, never this series"),
    }
    node_owner = owner_of_cell
    if node_owner is None and node_cell_ids is not None:
        attributed = attribute_declared_nodes(
            receiver, valid_mask, kinds, np.asarray(node_cell_ids, dtype=np.int64),
            upstream_unknown_mask=upstream_unknown_mask, cells_of_local_q=active,
            local_q_m3_s=supply["local_supply_m3_s"], dt_s=dt_s)
        routing["node_attribution"] = {key: value for key, value in attributed.items()
                                       if key != "nodal_supply"}
        routing["nodal_supply"] = attributed["nodal_supply"]
        node_owner = np.asarray(attributed["node_owner_of_cell"], dtype=np.int64)[active]
    elif node_owner is not None:
        _regular(node_owner, "owner_of_cell", 1, "int64")
        if node_owner.size != cells:
            raise ValueError(
                "invalid_owner_of_cell: %d owners given for a %d-column block"
                % (int(node_owner.size), cells))
        if (node_owner < 0).any():
            raise ValueError(
                "invalid_owner_of_cell: every accounted cell must own a node")
        routing["nodal_supply"] = node_supply_ledger(
            supply["local_supply_m3_s"], np.asarray(node_owner, dtype=np.int64),
            dt_s=dt_s, nodes=int(node_owner.max()) + 1)
    else:
        routing["nodal_supply"] = None
        routing["nodal_supply_declaration"] = (
            "no node attribution was declared, so no nodal supply is reported; the "
            "routed terminal series is still explicitly not used for injection")

    interval_supply_m3 = supply["interval_surface_supply_m3"]
    # The accumulation kernel reports rates (m3/s); the supply ledger reports
    # interval volumes (m3). They may only be compared after one is converted, and
    # an earlier revision compared them directly -- a dimension mismatch that no
    # correct run could ever satisfy.
    interval_supply_rate = interval_supply_m3 / supply["dt_s"]
    interval_balance = {
        "rain_m3": supply["interval_rain_m3"],
        "infiltration_m3": supply["interval_infiltration_m3"],
        "external_loss_m3": supply["interval_external_loss_m3"],
        "internal_transfer_m3": supply["interval_internal_transfer_m3"],
        "surface_supply_m3": interval_supply_m3,
        "storage_change_m3": supply["interval_storage_change_m3"],
        "balance_residual_m3": (supply["interval_rain_m3"]
                                - supply["interval_external_loss_m3"]
                                - interval_supply_m3
                                - supply["interval_storage_change_m3"]),
    }
    account_gap = (certified_retained + certified_open + certified_unknown
                   + withheld - interval_supply_rate)
    scale = max(1.0, _max_abs(interval_supply_rate))
    if _max_abs(account_gap) > 1e-12 * scale:
        raise ValueError(
            "hydrology_ledger_mismatch: certified retained + certified open + "
            "certified unknown + withheld does not reproduce the interval supply "
            "(max |gap| = %.6e m3/s)" % _max_abs(account_gap))
    subseeds = (purpose_subseeds(world_seed) if world_seed is not None else None)
    return {
        "algorithm": ALGORITHM,
        "schema": SCHEMA,
        "source": {"world_seed": (int(world_seed) if world_seed is not None else None),
                   "grid_shape": [int(receiver.shape[0]), int(receiver.shape[1])],
                   "active_cells": int(cells),
                   "active_cells_sha256": hashlib.sha256(
                       active.astype(np.int64).tobytes(order="C")).hexdigest()},
        "subseeds": subseeds,
        "supply": supply,
        "storage": storage,
        "interval_account": interval_balance,
        "unknown_boundary": {
            "policy": "finite_window_graph_terminal_declaration_v2",
            "semantics": UNKNOWN_SEMANTICS,
            "terminal_census": {kind: int((kinds == kind).sum())
                                for kind in ("inactive", "interior", "retained",
                                             "unknown_boundary", "open_outflow")},
            "certified_retained_m3_s": certified_retained,
            "certified_open_outflow_m3_s": certified_open,
            "certified_unknown_pending_m3_s": certified_unknown,
            "declared_retained_m3_s": declared_retained,
            "withheld_local_q_m3_s": withheld,
            "unknown_pending_m3_s": unknown_pending,
            "complete_cells": complete_cells,
            "cumulative_certified_retained_m3": float(
                certified_retained.sum() * supply["dt_s"]),
            "cumulative_certified_open_outflow_m3": float(
                certified_open.sum() * supply["dt_s"]),
            "cumulative_certified_unknown_pending_m3": float(
                certified_unknown.sum() * supply["dt_s"]),
            "cumulative_withheld_m3": float(withheld.sum() * supply["dt_s"]),
            "cumulative_unknown_pending_m3": float(
                unknown_pending.sum() * supply["dt_s"]),
            "unknown_folded_into_outlet": False,
        },
        "routing": routing,
        "checks": {
            "max_abs_interval_balance_residual_m3": _max_abs(
                interval_balance["balance_residual_m3"]),
            "max_abs_certified_account_gap_m3_s": _max_abs(account_gap),
            "max_abs_storage_residual_m3": storage["checks"][
                "max_abs_storage_residual_m3"],
            "max_abs_supply_balance_residual_m3": supply["checks"][
                "max_abs_balance_residual_m3"],
            "max_abs_local_q_gap_m3_s": supply["checks"]["max_abs_local_q_gap_m3_s"],
            "internal_transfer_included_in_external_loss": False,
            "unknown_folded_into_outlet": False,
            "routed_terminal_series_reinjected": False,
            "cumulative_rain_m3": supply["cumulative_rain_m3"],
            "cumulative_external_loss_m3": supply["cumulative_external_loss_m3"],
            "cumulative_internal_transfer_m3": supply[
                "cumulative_internal_transfer_m3"],
            "cumulative_surface_supply_m3": supply["cumulative_surface_supply_m3"],
            "cumulative_storage_change_m3": supply["cumulative_storage_change_m3"],
            "cumulative_withheld_m3": float(withheld.sum() * supply["dt_s"]),
            "cumulative_certified_outlet_m3": float(
                (certified_retained + certified_open).sum() * supply["dt_s"]),
        },
        "capabilities": {
            "natural_outlet_certified": False,
            "hydraulic_ready": False,
            "bankfull": False,
            "calibrated": False,
            "publishable": False,
            "spatially_variable_forcing_supported": False,
            "noise_driven_forcing": False,
            "unknown_never_merged_into_outlet": True,
            "permeability_and_losses_are_declared_not_observed": True,
        },
    }


# --------------------------------------------------------------------------- #
# 4. nodal supply: the raw release, attributed, never the routed endpoint
# --------------------------------------------------------------------------- #

def node_supply_ledger(local_q_m3_s, owner_of_cell, *, dt_s, nodes):
    """Attribute the raw per-cell release to its single owning node.

    ``owner_of_cell`` is the per-cell owner of the flat cell axis (``-1`` for a cell
    that carries no supply). Every cell appears in exactly one node column, so the
    nodal series integrates to the declared release with no spreading along a
    flowline and no second injection of a delayed terminal series.
    """
    _regular(local_q_m3_s, "local_q_m3_s", 2, "float64")
    _regular(owner_of_cell, "owner_of_cell", 1, "int64")
    dt_s = _scalar(dt_s, "dt_s", 1e7, positive=True)
    if dt_s < 1e-6:
        raise ValueError("invalid_dt_s: dt_s must be >= 1e-6 s")
    nodes = _count(nodes, "node_count")
    if nodes < 1:
        raise ValueError("invalid_node_count: a positive node count is required")
    steps, cells = local_q_m3_s.shape
    if owner_of_cell.size != cells:
        raise ValueError("invalid_owner_of_cell: the owner axis must match the cells")
    if (owner_of_cell < -1).any() or (owner_of_cell >= nodes).any():
        raise ValueError(
            "invalid_owner_of_cell: every entry must be -1 or a node id in [0, %d)"
            % nodes)
    ledger_budget(steps, cells, nodes)
    _finite_nonnegative(local_q_m3_s, "local_q_m3_s")
    owned = owner_of_cell >= 0
    if not owned.any():
        raise ValueError("invalid_owner_of_cell: at least one cell must own a node")
    counts = np.bincount(owner_of_cell[owned], minlength=nodes).astype(np.int64)
    nodal_q = np.zeros((steps, nodes), dtype=np.float64)
    for step in range(steps):
        nodal_q[step] = np.bincount(owner_of_cell[owned],
                                    weights=local_q_m3_s[step][owned], minlength=nodes)
    nodal_volume = nodal_q * dt_s
    gap = _max_abs(nodal_q.sum(axis=1) - local_q_m3_s.sum(axis=1))
    scale = max(1.0, _max_abs(local_q_m3_s))
    if gap > 1e-12 * scale:
        raise ValueError(
            "nodal_supply_mismatch: the attributed nodal supply does not reproduce "
            "the declared release (max |gap| = %.6e m3/s)" % gap)
    return {
        "dt_s": dt_s,
        "node_count": nodes,
        "steps": int(steps),
        "ownership": ("one owner per cell: the reach that owns the cell's first "
                      "downstream flowline cell, so each cell's release enters exactly "
                      "one node"),
        "owner_of_cell": owner_of_cell.copy(),
        "node_lateral_cell_counts": counts,
        "q_m3_s": nodal_q,
        "volume_m3": nodal_volume,
        "cumulative_volume_m3": nodal_volume.sum(axis=0),
        "interval_total_m3": nodal_volume.sum(axis=1),
        "declared_release_total_m3": float(local_q_m3_s.sum() * dt_s),
        "checks": {
            "nodal_minus_declared_max_m3_s": gap,
            "node_columns_never_overlap": True,
            "empty_nodes": int((counts == 0).sum()),
            "used_for_dynamic_injection": True,
            "routed_terminal_series_reinjected": False,
        },
        "definition": NODAL_SUPPLY_DEFINITION,
    }


def attribute_declared_nodes(receiver, valid_mask, terminal_kind, node_cell_ids, *,
                             upstream_unknown_mask=None, cells_of_local_q=None,
                             local_q_m3_s=None, dt_s=None):
    """Attribute the raw release onto a **declared** downstream node path.

    The ownership rule is a pure function of the topology and of the declared node
    path (see ``OWNERSHIP_RULE``); it is the same rule the event publisher applies,
    but written over the raw per-cell release rather than over a time-delayed terminal
    series, so a consumer can inject nodal forcing without ever re-injecting the
    delayed endpoint.
    """
    receiver = _regular(receiver, "receiver", 2, "int64")
    valid_mask = _regular(valid_mask, "valid_mask", 2, "bool")
    node_cell_ids = _regular(node_cell_ids, "node_cell_ids", 1, "int64")
    if node_cell_ids.size < 2:
        raise ValueError("invalid_node_cell_ids: at least two declared nodes required")
    if np.unique(node_cell_ids).size != node_cell_ids.size:
        raise ValueError("invalid_node_cell_ids: node cells must be unique")
    fields = int(receiver.size)
    if (node_cell_ids < 0).any() or (node_cell_ids >= fields).any():
        raise ValueError("invalid_node_cell_ids: every node cell must lie in the grid")
    unit = np.where(valid_mask, 1.0, 0.0)
    counts = np.asarray(accumulate_network_discharge(
        receiver, unit, valid_mask, terminal_kind=terminal_kind,
        upstream_unknown_mask=upstream_unknown_mask)["known_routed_q_m3_s"]).reshape(-1)
    node_accumulated = counts[node_cell_ids]
    if not np.allclose(node_accumulated, np.round(node_accumulated), atol=1e-9):
        raise ValueError("node_accumulated_counts_not_integral")
    node_accumulated = np.round(node_accumulated).astype(np.int64)
    if np.any(np.diff(node_accumulated) <= 0):
        raise ValueError(
            "node_accumulated_counts_not_increasing: the declared node path does not "
            "accumulate strictly more cells downstream")
    valid_cells = int(np.count_nonzero(valid_mask))
    if int(node_accumulated[-1]) != valid_cells:
        raise ValueError(
            "node_path_not_complete: the last declared node accumulates %d of %d valid "
            "cells, so the path does not own the whole catchment"
            % (int(node_accumulated[-1]), valid_cells))
    owner = np.full(fields, -1, dtype=np.int64)
    inside = valid_mask.reshape(-1)
    owner[inside] = np.searchsorted(node_accumulated, counts[inside], side="left")
    if (owner[inside] >= node_cell_ids.size).any():
        raise ValueError(
            "node_attribution_out_of_range: a valid cell accumulates more cells than "
            "the declared path owns")
    complete = np.asarray(accumulate_network_discharge(
        receiver, unit, valid_mask, terminal_kind=terminal_kind,
        upstream_unknown_mask=upstream_unknown_mask)["complete_mask"])
    result = {
        "node_cell_ids": node_cell_ids.copy(),
        "node_accumulated_cells": node_accumulated,
        "node_lateral_cell_counts": np.r_[node_accumulated[0],
                                          np.diff(node_accumulated)],
        "node_owner_of_cell": owner,
        "node_count": int(node_cell_ids.size),
        "complete_cells": int((complete & valid_mask).sum()),
        "ownership_rule": OWNERSHIP_RULE,
    }
    if cells_of_local_q is None:
        return result
    _regular(cells_of_local_q, "cells_of_local_q", 1, "int64")
    if (cells_of_local_q < 0).any() or (cells_of_local_q >= fields).any():
        raise ValueError("invalid_cells_of_local_q: flat cell ids must lie in the grid")
    if local_q_m3_s is None or dt_s is None:
        raise ValueError(
            "node_supply_inputs_required: local_q_m3_s and dt_s are required together "
            "with cells_of_local_q")
    _regular(local_q_m3_s, "local_q_m3_s", 2, "float64")
    if local_q_m3_s.shape[1] != cells_of_local_q.size:
        raise ValueError(
            "invalid_local_q_m3_s: the cell axis must match cells_of_local_q")
    owner_of_catchment = owner[cells_of_local_q]
    if (owner_of_catchment < 0).any():
        raise ValueError(
            "node_attribution_incomplete: %d catchment cell(s) have no declared node"
            % int((owner_of_catchment < 0).sum()))
    result["nodal_supply"] = node_supply_ledger(
        local_q_m3_s, owner_of_catchment, dt_s=dt_s,
        nodes=int(node_cell_ids.size))
    return result


# --------------------------------------------------------------------------- #
# 5. window boundary declaration (used to keep an undeclared edge out of 'retained')
# --------------------------------------------------------------------------- #

TERMINAL_KIND_DTYPE = np.dtype("U24")


def window_terminal_kind(receiver, valid_mask, *, origin_native_xz=(0, 0),
                         spacing_m=30., world_seed=20261020):
    """Label every receiver-less valid cell ``retained`` or ``unknown_boundary``.

    A boundary cell whose full irregular graph support lies within resolved cells
    is an interior minimum: the window can answer for it, so it is ``retained``. Any
    other receiver-less cell -- on the window rim, or next to a cell the window could
    not resolve -- is an **undeclared boundary**: its upstream is not declared by this
    window, so it is labelled ``unknown_boundary`` and its water is excluded from the
    certified totals downstream.

    This is the same declaration rule ``native_30m_source.build_strict_topology``
    applies (paired with the same full graph support test); it is
    re-expressed here so that an event run does not have to assemble Terrain Diffusion
    pages in order to account for its own window edge. It is a declaration, not a
    solver: nothing is routed, filled or inferred.
    """
    receiver = _regular(receiver, "receiver", 2, "int64")
    valid_mask = _regular(valid_mask, "valid_mask", 2, "bool")
    if receiver.shape != valid_mask.shape:
        raise ValueError("invalid_shape: receiver and valid_mask must share one shape")
    if not valid_mask.any():
        raise ValueError("invalid_valid_mask: at least one valid cell is required")
    receiver_flat = receiver.reshape(-1)
    if (receiver_flat < -1).any() or (receiver_flat >= receiver_flat.size).any():
        raise ValueError(
            "receiver_index_out_of_range: receiver entries must be -1 or a flat id in "
            "[0, %d)" % receiver_flat.size)
    from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown
    unknown = graph_support_unknown(valid_mask,
        x0_m=origin_native_xz[0] * spacing_m, z0_m=origin_native_xz[1] * spacing_m,
        dx_m=spacing_m, world_seed=world_seed)
    fully_resolved = valid_mask & ~unknown
    kinds = np.full(receiver.shape, "inactive", dtype=TERMINAL_KIND_DTYPE)
    live = valid_mask & (receiver >= 0)
    kinds[live] = "interior"
    terminal = valid_mask & (receiver < 0)
    kinds[terminal & fully_resolved] = "retained"
    kinds[terminal & ~fully_resolved] = "unknown_boundary"
    retained = terminal & fully_resolved
    unknown = terminal & ~fully_resolved
    return {
        "terminal_kind": kinds,
        "retained_mask": retained,
        "unknown_boundary_mask": unknown,
        "fully_resolved_cells": int(fully_resolved.sum()),
        "census": {
            "inactive": int((kinds == "inactive").sum()),
            "interior": int((kinds == "interior").sum()),
            "retained": int(retained.sum()),
            "unknown_boundary": int(unknown.sum()),
            "open_outflow": 0,
        },
        "rule": ("a receiver-less valid cell with complete irregular graph support is "
                 "retained; every other receiver-less valid cell is an undeclared "
                 "unknown_boundary. open_outflow is never emitted by a finite window"),
        "policy": "finite_window_terminal_declaration_v1",
    }


# --------------------------------------------------------------------------- #
# 6. the per-cell, per-interval account the stage p4 gate asks for
# --------------------------------------------------------------------------- #

_ACCOUNT_ARRAY_KEYS = (
    "local_supply_m3_s", "rain_depth_mm", "rain_volume_m3", "infiltration_mm",
    "infiltration_volume_m3", "actual_et_mm", "et_volume_m3",
    "external_loss_volume_m3", "percolation_mm", "percolation_volume_m3",
    "excess_mm", "excess_volume_m3", "surface_supply_volume_m3",
    "storage_change_volume_m3", "balance_residual_m3", "soil_storage_mm",
    "soil_storage_m3", "fast_storage_mm", "fast_storage_m3", "slow_storage_mm",
    "slow_storage_m3", "total_storage_mm", "total_storage_m3",
)


def cell_hydrology_account(bucket, receiver, valid_mask, *, cell_area_m2, dt_s,
                           active_cells, terminal_kind=None,
                           upstream_unknown_mask=None, world_seed=None,
                           outlet_q_m3_s=None, routed_terminal_q_m3_s=None,
                           route_lateral_volume_m3=None, origin_native_xz=(0, 0)):
    """Per-cell, per-interval account of every litre, with the terms kept apart.

    The fields fall into four groups and are **never** merged:

    =========================  =====================================================
    group                      fields
    =========================  =====================================================
    soil-bucket transfer       rain, infiltration, excess, percolation, storage
                               change, and their volumes
    external loss              ``actual_et_mm`` / ``et_volume_m3`` /
                               ``external_loss_volume_m3`` -- the only term that
                               leaves the bucket
    local supply               ``local_supply_m3_s`` / ``surface_supply_volume_m3`` --
                               what the two linear reservoirs release, per cell
    boundary destination       ``certified_supply_volume_m3`` (goes to a declared
                               terminal), ``withheld_volume_m3`` (dropped because its
                               upstream is undeclared), ``unknown_pending_volume_m3``
                               (standing on an ``unknown_boundary`` terminal) and
                               ``outlet_volume_m3`` (the routed reach outlet)
    =========================  =====================================================

    Invariants checked before returning, all of them fatal:

    1. every interval's certified supply plus its withheld part equals the interval's
       surface supply -- so the boundary split neither creates nor loses water;
    2. no cell inside the undeclared cone carries water into a certified total;
    3. the unknown term is never added to the outlet term;
    4. the routed terminal series is *not* used as nodal forcing: when a routed series
       is supplied for comparison it is checked against the interval volumes the
       router was given, not substituted for them.
    """
    supply = supply_ledger(bucket, dt_s=dt_s, cell_area_m2=cell_area_m2)
    storage = storage_ledger(bucket, dt_s=dt_s, cell_area_m2=cell_area_m2)
    receiver = _regular(receiver, "receiver", 2, "int64")
    valid_mask = _regular(valid_mask, "valid_mask", 2, "bool")
    if receiver.shape != valid_mask.shape:
        raise ValueError("invalid_shape: receiver and valid_mask must share one shape")
    _regular(active_cells, "active_cells", 1, "int64")
    steps, cells = supply["steps"], supply["cells"]
    account_budget(steps, cells, int(receiver.size))
    if active_cells.size != cells:
        raise ValueError(
            "invalid_active_cells: %d active cells given for a %d-column bucket block"
            % (int(active_cells.size), cells))
    active = np.asarray(active_cells, dtype=np.int64)
    if np.unique(active).size != cells:
        raise ValueError("invalid_active_cells: active cells must be unique")
    if (active < 0).any() or (active >= receiver.size).any():
        raise ValueError(
            "invalid_active_cells: every active cell must be a flat id of the grid")
    if np.any(~valid_mask.reshape(-1)[active]):
        raise ValueError(
            "invalid_active_cells: a cell carrying local supply must be valid on the "
            "receiver graph")
    kinds = terminal_kind
    if kinds is None:
        kinds = window_terminal_kind(receiver, valid_mask, origin_native_xz=origin_native_xz,
            world_seed=20261020 if world_seed is None else world_seed)["terminal_kind"]
    else:
        if (not isinstance(kinds, np.ndarray) or kinds.shape != receiver.shape
                or kinds.dtype.kind != "U"):
            raise ValueError("matching Unicode terminal_kind array required")
        kinds = np.array(kinds, copy=True)

    factor = supply["volume_factor_m3_per_mm"]
    local = supply["local_supply_m3_s"]
    block = np.zeros((steps,) + tuple(receiver.shape), dtype=np.float64)
    block.reshape(steps, -1)[:, active] = local

    withheld = np.zeros(steps, dtype=np.float64)
    certified_retained = np.zeros(steps, dtype=np.float64)
    certified_open = np.zeros(steps, dtype=np.float64)
    certified_unknown = np.zeros(steps, dtype=np.float64)
    unknown_pending = np.zeros(steps, dtype=np.float64)
    declared_retained = np.zeros(steps, dtype=np.float64)
    complete_cells = np.zeros(steps, dtype=np.int64)
    terminal_ids = np.flatnonzero(valid_mask.reshape(-1) & (receiver.reshape(-1) < 0))
    terminal_q = np.zeros((steps, terminal_ids.size), dtype=np.float64)
    seeds = np.zeros(receiver.shape, bool)
    if upstream_unknown_mask is not None:
        _regular(upstream_unknown_mask, "upstream_unknown_mask", 2, "bool")
        if upstream_unknown_mask.shape != receiver.shape:
            raise ValueError(
                "invalid_upstream_unknown_mask: it must share the receiver shape")
        seeds = upstream_unknown_mask
    for step in range(steps):
        record = unknown_boundary_ledger(
            receiver, valid_mask, kinds, block[step:step + 1],
            upstream_unknown_mask=seeds)
        withheld[step] = record["withheld_local_q_m3_s"]
        certified_retained[step] = record["certified_retained_m3_s"]
        certified_open[step] = record["certified_open_outflow_m3_s"]
        certified_unknown[step] = record["certified_unknown_pending_m3_s"]
        declared_retained[step] = record["retained_m3_s"]
        unknown_pending[step] = record["unknown_pending_m3_s"]
        complete_cells[step] = record["complete_cells"]
        terminal_q[step] = record["terminal_q_m3_s"].reshape(-1)[terminal_ids]

    dt = supply["dt_s"]
    supply_total = (certified_retained + certified_open + certified_unknown + withheld)
    interval_supply = supply["interval_surface_supply_m3"]
    # Rates (m3/s, the accumulation kernel) against volumes (m3, the bucket): only
    # converted quantities are ever compared here.
    supply_rate = interval_supply / dt
    scale = max(1.0, _max_abs(supply_rate))
    split_gap = _max_abs(supply_total - supply_rate)
    if split_gap > 1e-12 * scale:
        raise ValueError(
            "cell_account_mismatch: certified retained + certified open + certified "
            "unknown + withheld does not reproduce the interval surface supply "
            "(max |gap| = %.6e m3/s)" % split_gap)
    if np.any(withheld < -1e-15 * scale):
        raise ValueError(
            "cell_account_mismatch: the withheld term is negative, so water was "
            "invented inside the undeclared cone")

    outlet_q = np.zeros(steps, dtype=np.float64)
    if outlet_q_m3_s is not None:
        outlet_q = np.asarray(outlet_q_m3_s, dtype=np.float64)
        if outlet_q.shape != (steps,) or not np.isfinite(outlet_q).all() \
                or (outlet_q < 0).any():
            raise ValueError(
                "invalid_outlet_q_m3_s: a finite nonnegative [steps] series is required")
    routed = None
    if routed_terminal_q_m3_s is not None:
        routed = np.asarray(routed_terminal_q_m3_s, dtype=np.float64)
        if routed.shape != (steps,) or not np.isfinite(routed).all():
            raise ValueError(
                "invalid_routed_terminal_q_m3_s: a finite [steps] series is required")
    lateral_total = None
    if route_lateral_volume_m3 is not None:
        lateral_total = float(np.asarray(route_lateral_volume_m3, dtype=np.float64).sum())
        declared_total = float(local.sum() * dt)
        if abs(lateral_total - declared_total) > 1e-12 * max(1.0, declared_total):
            raise ValueError(
                "routing_injection_mismatch: the router's lateral volume %.6e m3 is "
                "not the account's declared release %.6e m3"
                % (lateral_total, declared_total))

    outlet_volume = outlet_q * dt
    certified_supply = certified_retained + certified_open
    certified_volume = certified_supply * dt
    withheld_volume = withheld * dt
    unknown_volume = unknown_pending * dt
    certified_unknown_volume = certified_unknown * dt
    bucket_total = float(supply["cumulative_surface_supply_m3"])
    routed_total = float(routed.sum() * dt) if routed is not None else None

    account = {
        "algorithm": ACCOUNT_ALGORITHM,
        "schema": SCHEMA,
        "dt_s": dt,
        "steps": int(steps),
        "cells": int(cells),
        "cell_area_m2": float(supply["cell_area_m2"]),
        "volume_factor_m3_per_mm": factor,
        "semantics": ACCOUNT_SEMANTICS,
        "active_cells": active.copy(),
        "rain_depth_mm": supply["rain_depth_mm"],
        "rain_volume_m3": supply["rain_volume_m3"],
        "infiltration_mm": supply["infiltration_mm"],
        "infiltration_volume_m3": supply["infiltration_volume_m3"],
        "actual_et_mm": supply["actual_et_mm"],
        "et_volume_m3": supply["et_volume_m3"],
        "external_loss_volume_m3": supply["external_loss_volume_m3"],
        "percolation_mm": supply["percolation_mm"],
        "percolation_volume_m3": supply["percolation_volume_m3"],
        "excess_mm": supply["excess_mm"],
        "excess_volume_m3": supply["excess_volume_m3"],
        "surface_supply_volume_m3": supply["surface_supply_volume_m3"],
        "local_supply_m3_s": local,
        "storage_change_volume_m3": supply["storage_change_volume_m3"],
        "balance_residual_m3": supply["balance_residual_m3"],
        "soil_storage_mm": storage["soil_mm"],
        "soil_storage_m3": storage["soil_store_m3"],
        "fast_storage_mm": storage["fast_mm"],
        "fast_storage_m3": storage["fast_store_m3"],
        "slow_storage_mm": storage["slow_mm"],
        "slow_storage_m3": storage["slow_store_m3"],
        "total_storage_mm": storage["total_store_mm"],
        "total_storage_m3": storage["total_store_m3"],
        "terminal_flat_cells": terminal_ids.astype(np.int64),
        "terminal_kind_census": {kind: int((kinds == kind).sum())
                                 for kind in ("inactive", "interior", "retained",
                                              "unknown_boundary", "open_outflow")},
        "terminal_q_m3_s": terminal_q,
        "certified_retained_m3_s": certified_retained,
        "certified_open_outflow_m3_s": certified_open,
        "declared_retained_m3_s": declared_retained,
        "certified_unknown_pending_m3_s": certified_unknown,
        "certified_supply_m3_s": certified_supply,
        "certified_supply_volume_m3": certified_volume,
        "withheld_m3_s": withheld,
        "withheld_volume_m3": withheld_volume,
        "unknown_pending_m3_s": unknown_pending,
        "unknown_pending_volume_m3": unknown_volume,
        "certified_unknown_pending_volume_m3": certified_unknown_volume,
        "outlet_q_m3_s": outlet_q,
        "outlet_volume_m3": outlet_volume,
        "routed_terminal_q_m3_s": routed,
        "complete_cells": complete_cells,
        "upstream_unknown_mask": np.array(seeds, copy=True),
        "interval_rain_m3": supply["interval_rain_m3"],
        "interval_infiltration_m3": supply["interval_infiltration_m3"],
        "interval_external_loss_m3": supply["interval_external_loss_m3"],
        "interval_internal_transfer_m3": supply["interval_internal_transfer_m3"],
        "interval_surface_supply_m3": interval_supply,
        "interval_storage_change_m3": supply["interval_storage_change_m3"],
        "interval_balance_residual_m3": (supply["interval_rain_m3"]
                                         - supply["interval_external_loss_m3"]
                                         - interval_supply
                                         - supply["interval_storage_change_m3"]),
        "checks": {
            "max_abs_interval_balance_residual_m3": _max_abs(
                supply["interval_rain_m3"] - supply["interval_external_loss_m3"]
                - interval_supply - supply["interval_storage_change_m3"]),
            "max_abs_certified_plus_withheld_minus_supply_m3_s": split_gap,
            "max_abs_local_q_gap_m3_s": supply["checks"]["max_abs_local_q_gap_m3_s"],
            "max_abs_storage_residual_m3": storage["checks"][
                "max_abs_storage_residual_m3"],
            "cumulative_rain_m3": supply["cumulative_rain_m3"],
            "cumulative_external_loss_m3": supply["cumulative_external_loss_m3"],
            "cumulative_internal_transfer_m3": supply[
                "cumulative_internal_transfer_m3"],
            "cumulative_surface_supply_m3": bucket_total,
            "cumulative_storage_change_m3": supply["cumulative_storage_change_m3"],
            "cumulative_certified_supply_m3": float(certified_volume.sum()),
            "cumulative_certified_unknown_pending_m3": float(certified_unknown_volume.sum()),
            "cumulative_withheld_m3": float(withheld_volume.sum()),
            "cumulative_unknown_pending_m3": float(unknown_volume.sum()),
            "cumulative_outlet_m3": float(outlet_volume.sum()),
            "cumulative_routed_terminal_m3": routed_total,
            "unknown_folded_into_outlet": False,
            "withheld_folded_into_outlet": False,
            "routed_terminal_series_reinjected": False,
            "nodal_forcing_is_raw_local_supply": True,
        },
        "declarations": {
            "unknown_never_merged_into_outlet": True,
            "withheld_never_merged_into_outlet": True,
            "routed_terminal_not_reinjected": True,
            "internal_transfer_included_in_external_loss": False,
            "subseeds": (purpose_subseeds(world_seed)
                         if world_seed is not None else None),
            "unknown_semantics": UNKNOWN_SEMANTICS,
            "external_loss": EXTERNAL_LOSS_DEFINITION,
            "internal_transfer": INTERNAL_TRANSFER_DEFINITION,
            "routing_injection": ("the router's lateral volume is checked against the "
                                  "account's own raw release; the routed terminal "
                                  "series is reported for comparison only and is "
                                  "never injected back as nodal forcing"),
        },
    }
    digest = hashlib.sha256()
    for key in sorted(account):
        value = account[key]
        if isinstance(value, np.ndarray):
            digest.update(key.encode("ascii"))
            digest.update(_array_sha256(value).encode("ascii"))
    account["cell_account_identity_sha256"] = digest.hexdigest()
    return account
