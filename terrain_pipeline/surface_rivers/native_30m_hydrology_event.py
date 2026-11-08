"""Opt-in per-cell hydrology account for one declared native-30 m catchment event.

Why this module exists rather than a keyword on ``run_catchment_event``
----------------------------------------------------------------------
The account was first written as an optional return field of
``native_30m_runoff.run_catchment_event``. That file, however, is pinned by the
source-identity snapshot of every earlier ``m1-*`` release under
``.scratch/river-stage1-completion/``: 18 of them name its SHA256, and
``publish_native_30m_bundle._code_pins()`` re-hashes the whole tree. Adding a
single line to it -- even a comment -- therefore makes all 18 fail their strict
source-pin re-verification. Measured before this module existed: 415 pinned files,
414 byte-identical, and exactly one drifting file, ``native_30m_runoff.py``.

The main branch ruled that the frozen file must stay byte-identical, so the hook
moved here: ``run_event_with_account`` calls the untouched
``run_catchment_event`` and then accounts for its result with
``native_30m_hydrology_ledger``. Nothing in this module is pinned and nothing in
this module writes files.

What it returns, and what it refuses
------------------------------------
The event dictionary of ``run_catchment_event`` **unmodified** (same keys, same
arrays, same ``event_identity_sha256``) plus two additions:

``cell_account``                  the per-cell, per-interval account;
``accounted_event_identity_sha256``  an identity that binds the account to the
                                 event, so an accounted run cannot be confused
                                 with a plain one.

The plain ``event_identity_sha256`` is *not* rewritten and *not* shadowed: an
accounted run publishes the exact same event identity as the unaccounted one,
because the account adds no forcing, no runoff law and no routing. Versioning is
carried by the separate ``accounted_event_identity_sha256``.

Boundaries: this is an engineering adapter. It adds no physics, certifies no
natural outlet, certifies no bankfull discharge and calibrates nothing.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff
from terrain_pipeline.surface_rivers.native_30m_hydrology_ledger import (
    cell_hydrology_account)
from terrain_pipeline.runoff import DIAGNOSTIC_TERMINAL_LABEL as DIAGNOSTIC_TERMINAL_LABEL
from terrain_pipeline.runoff import NATIVE_SPACING_M as NATIVE_SPACING_M
from terrain_pipeline.runoff import run_catchment_event as run_catchment_event


__all__ = [
    "ADAPTER",
    "SCHEMA",
    "accounted_identity",
    "run_event_with_account",
]


ADAPTER = "native-30m-hydrology-event-adapter-v1"
SCHEMA = "native-30m-hydrology-event-with-account-dict-v1"


# ``run_catchment_event`` does not publish its bucket result, so the same bucket is
# re-run here on exactly the same declaration (uniform interval series over the
# active catchment cells, one 900 m2 cell each). The re-run is checked against the
# event's own release series before it is trusted; a mismatch is fatal.
BUCKET_IDENTITY_NOTE = (
    "the account re-runs the same soil bucket on the same declaration and checks "
    "its local_q against the event's published series bit-for-bit; the event's own "
    "identity is never rewritten")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def accounted_identity(event, account, *, source_identity_sha256, spacing_m):
    """Identity of the accounted event, kept separate from the event identity."""
    payload = {
        "adapter": ADAPTER,
        "schema": SCHEMA,
        "event_identity_sha256": event["event_identity_sha256"],
        "cell_account_identity_sha256": account["cell_account_identity_sha256"],
        "account_algorithm": account["algorithm"],
        "source_identity_sha256": source_identity_sha256,
        "spacing_m": float(spacing_m),
        "dt_s": float(account["dt_s"]),
        "steps": int(account["steps"]),
        "cells": int(account["cells"]),
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _rebuild_bucket(event, *, active_cells, dt_s, runoff_parameters):
    """Re-run the declared bucket and prove it is the event's own release."""
    if not isinstance(runoff_parameters, RunoffParameters):
        raise ValueError(
            "runoff_parameters_required: the account needs the same declared "
            "RunoffParameters the event was run with")
    intervals = int(event["rain_mm_h"].size)
    cells = int(active_cells.size)
    rain = event["rain_mm_h"]
    block = np.broadcast_to(rain[:, None], (intervals, cells)).copy()
    areas = np.full(cells, float(NATIVE_SPACING_M) ** 2, dtype=np.float64)
    if not np.all(areas == float(event["active_cell_area_m2"])):
        raise ValueError(
            "account_area_mismatch: the event's per-cell area is not the native "
            "30 m cell area")
    bucket = simulate_rainfall_runoff(
        block, areas, dt_s=float(dt_s),
        source_id="%s:account" % (event["runoff"]["source_id"],),
        parameters=runoff_parameters)
    published = event["local_q_m3_s"]
    if published.shape != bucket["local_q_m3_s"].shape:
        raise ValueError(
            "account_rebuild_mismatch: the rebuilt bucket does not share the event's "
            "local-Q shape")
    if not np.array_equal(bucket["local_q_m3_s"], published):
        raise ValueError(
            "account_rebuild_mismatch: re-running the declared bucket does not "
            "reproduce the event's published local Q, so the account would describe "
            "a different event")
    if not np.array_equal(bucket["outflow_volume_m3"].sum(axis=1),
                          event["runoff"]["outflow_volume_m3"]):
        raise ValueError(
            "account_rebuild_mismatch: the rebuilt bucket's release volume does not "
            "reproduce the event's reported release")
    return bucket


def run_event_with_account(elevation_m, receiver, catchment_mask, flowline_mask, *,
                           origin_native_xz, source_identity_sha256, world_seed,
                           rain_mm_h, dt_s, runoff_parameters,
                           travel_speed_m_s=1.0, minimum_reach_length_m=30.0):
    """Run the untouched event and attach its per-cell, per-interval account.

    The event is produced by ``native_30m_runoff.run_catchment_event`` exactly as
    before; every rejection, every array and ``event_identity_sha256`` are that
    function's. This wrapper only adds ``cell_account`` and
    ``accounted_event_identity_sha256``.
    """
    event = run_catchment_event(
        elevation_m, receiver, catchment_mask, flowline_mask,
        origin_native_xz=origin_native_xz,
        source_identity_sha256=source_identity_sha256, world_seed=world_seed,
        rain_mm_h=rain_mm_h, dt_s=dt_s, runoff_parameters=runoff_parameters,
        travel_speed_m_s=travel_speed_m_s,
        minimum_reach_length_m=minimum_reach_length_m)
    active = np.asarray(event["active_cells"], dtype=np.int64)
    receiver_array = np.asarray(receiver, dtype=np.int64)
    shape = receiver_array.shape
    valid = np.ones(shape, dtype=bool)
    terminal_kind = np.full(shape, "interior", dtype="U24")
    terminal_kind[receiver_array < 0] = DIAGNOSTIC_TERMINAL_LABEL
    bucket = _rebuild_bucket(event, active_cells=active, dt_s=dt_s,
                             runoff_parameters=runoff_parameters)
    account = cell_hydrology_account(
        bucket, receiver_array, valid,
        cell_area_m2=float(event["active_cell_area_m2"]), dt_s=float(dt_s),
        active_cells=active, terminal_kind=terminal_kind, world_seed=world_seed,
        outlet_q_m3_s=event["routing"]["outlet_q_m3_s"],
        routed_terminal_q_m3_s=event["routed_terminal_q_m3_s"],
        route_lateral_volume_m3=event["routing"]["lateral_volume_m3"])
    result = dict(event)
    result["adapter"] = ADAPTER
    result["adapter_schema"] = SCHEMA
    result["cell_account"] = account
    result["accounted_event_identity_sha256"] = accounted_identity(
        event, account, source_identity_sha256=source_identity_sha256,
        spacing_m=NATIVE_SPACING_M)
    result["account_declarations"] = {
        "bucket_identity": BUCKET_IDENTITY_NOTE,
        "event_identity_unchanged": True,
        "account_adds_no_forcing_no_runoff_law_no_routing": True,
        "cell_account_included": True,
    }
    return result
