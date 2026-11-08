# -*- coding: utf-8 -*-
"""Prepare one river-backbone product from declared inputs, then audit it cold.

This tool is **scheduling and I/O only**. The gates, the segmentation, the per-quantity
completeness and the side-input contracts belong to
``terrain_pipeline.surface_rivers.metric_backbone_precompute``; the product format belongs
to ``terrain_pipeline.surface_rivers.metric_backbone_product``. Nothing algorithmic lives
here.

Flow, in this order and no other
--------------------------------
1. the support is **declared before any page is read**: world seed, 30 m spacing, signed
   native origin, ``shape_zx``, the plan version and the cell budget;
2. the pinned TD pages are read through ``native_30m_source.load_native_window`` with their
   SHA256 pins, so real pages are read and hashed rather than trusted;
3. the B1 parent is rebuilt through ``metric_world_domains.domain_candidates`` and its
   identity must equal the pinned evidence identity -- a rebuild that drifts is refused
   before any backbone exists;
4. the flux quantities are loaded from **explicit** inputs only (a declared event model or
   a declared climatology estimate); there is no built-in climate estimator, and a missing
   input becomes ``not_available_pending`` rather than zero;
5. the backbone is built and written into a hidden partial directory;
6. a **separate process** runs ``tools/audit_river_backbone.py`` against that partial
   directory;
7. only a PASS is renamed into the requested output path. A failure keeps the partial
   evidence under a ``*.rejected*`` name and the output path stays absent, so a failing run
   can never leave something that looks like a product.

The formal product target is ``artifacts/river-backbone-precompute-v1/``; this tool
defaults to the scratch staging directory and refuses to write under ``artifacts/`` unless
``--allow-artifact-target`` is passed **and** the audit passed in the same run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORLD_SEED = 20261020
SPACING_M = 30.0
MAX_SUPPORT_CELLS = 148_225
AUDIT_TIMEOUT_S = 60.0
STAGE_MEMORY_BUDGET_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024

MANIFEST_NAME = "manifest.json"
ARRAYS_NAME = "arrays.npz"

PINNED_PAGES = (
    {"path": ".scratch\\fine-terrain-40km\\td-pages\\td-page-41981-41364-2049.npz",
     "sha256": "7fcfc426d970cbe9b77cb4221661b1f5f8001d7a3f6b06189041a3f01d1a7142"},
    {"path": ".scratch\\fine-terrain-40km\\td-pages\\td-page-41981-43364-2049.npz",
     "sha256": "efeb11a0f4db4f32b042a14d18615659cf2f73ea00b6fb3a28bc53536847b1a3"},
    {"path": ".scratch\\fine-terrain-40km\\td-pages\\td-page-43981-41364-2049.npz",
     "sha256": "6bf2594c3796466764e66ed44cfe06d951b77bef705eec71553262dc9a0ebcaf"},
    {"path": ".scratch\\fine-terrain-40km\\td-pages\\td-page-43981-43364-2049.npz",
     "sha256": "9b74e605a81246e103c31a799b7486f94bacc76e7bdecb0ec22dc8485061a1d2"},
)

#: Declared supports. Nothing is discovered at run time and no origin is derived from a
#: render window.
DECLARED_SUPPORTS = {
    "p1": {"origin_native_xz": (42173, 42874), "shape_zx": (257, 257),
           "plan_version": 1,
           "note": "P1 development window"},
    "p2": {"origin_native_xz": (42173, 42874), "shape_zx": (385, 385),
           "plan_version": 1,
           "note": "P2 development window: the widest declared support"},
    "p2-shifted": {"origin_native_xz": (42270, 42743), "shape_zx": (385, 385),
                   "plan_version": 1,
                   "note": "P2 same size, translated: the adjacent overlapping window used "
                           "by the cross-window acceptance"},
}

#: Pinned B1 parent identities, read out of the delivered B evidence manifests
#: (``evidence-b-<plan>-v3/manifest.json`` -> ``identity_sha256``). The rebuild must
#: reproduce them exactly; a mismatch means the source pages or the rebuild have drifted.
#: A plan absent from this table is **not** silently accepted: the run records the rebuilt
#: identity and marks ``parent_identity_pinned=False``, so claiming a pin that was never
#: read is impossible.
PINNED_PARENT_IDENTITY = {
    "p1": "7715631d8dd70d3a445e16e4ee0854557ac00c98993d631ccd91d1b1caf6e169",
    "p2": "9caa2919516eef5e15ade1438caf044b89ba3e6fa2154a0307515cd72cac342b",
    "p2-shifted": "8bbc754d2ad422914354c04a510bb3019ab728cb50ec5496baa5d6cd957b6577",
}

#: The delivered finite-sample product. Read-only: this tool never writes into it.
FINITE_PRODUCT = "artifacts/finite-river-sample-v1"
FINITE_PRODUCT_FILES = (
    "product.json",
    "event/arrays.npz",
    "event/active_index.npy",
    "event/land_index.npy",
    "event/lake_bed_index.npy",
    "event/head_path_index.npy",
    "domain/elevation_m.npy",
    "domain/resolved_mask.npy",
    "domain/receiver.npy",
)

STAGING_ROOT = ".scratch/river-precompute-finalization/s1/staging"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _process_tree_rss(handle):
    """Sampled RSS of one process tree, or ``None`` when psutil is unavailable."""
    try:
        total = handle.memory_info().rss
        for child in handle.children(recursive=True):
            try:
                total += child.memory_info().rss
            except Exception:                       # observation only
                continue
        return int(total)
    except Exception:                               # observation only
        return None


def _run_supervised(command, *, timeout_s, sample_s=0.25):
    """Run one child with a hard stop and a **sampled** parent-tree RSS trace.

    The same pattern as ``prepare_world_domains.run_audit``: ``timeout_s`` is the only hard
    stop, and the memory figure is an observation of the child's tree, never a limit. When
    ``psutil`` is missing the peak is ``None`` and the record says so -- this step never
    claims the 512 MiB gate was satisfied.
    """
    try:
        import psutil
    except ImportError:                             # observation only
        psutil = None
    started = time.monotonic()
    peak = None
    peak_at = None
    timed_out = False
    process = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    handle = None
    if psutil is not None:
        try:
            handle = psutil.Process(process.pid)
        except Exception:                           # observation only
            handle = None
    while True:
        if process.poll() is not None:
            break
        elapsed = time.monotonic() - started
        if elapsed > timeout_s:
            timed_out = True
            process.kill()
            break
        if handle is not None:
            value = _process_tree_rss(handle)
            if value is None:
                handle = None
            elif peak is None or value > peak:
                peak = value
                peak_at = round(elapsed, 3)
        time.sleep(sample_s)
    stdout, stderr = process.communicate()
    record = {
        "command": [str(part) for part in command[1:]],
        "returncode": process.returncode,
        "clock": "time.monotonic",
        "elapsed_s": round(time.monotonic() - started, 3),
        "hard_stop_s": float(timeout_s),
        "timed_out": timed_out,
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
        "rss_sample": {
            "observed_peak_bytes": peak,
            "observed_peak_at_s": peak_at,
            "sampled_every_s": sample_s,
            "is_limit": False,
            "note": ("a sampled observation of the child's process tree, not a resource "
                     "limit; None means psutil was unavailable, not zero"),
        },
    }
    return record


def _audit_child(work):
    """Run the independent audit child under the sampled watchdog."""
    return _run_supervised(
        [sys.executable, "-B", str(ROOT / "tools" / "audit_river_backbone.py"),
         "--product", str(work / "product"),
         "--parent-reference", str(work / "parent-reference.json"),
         "--report", str(work / "audit.json")],
        timeout_s=AUDIT_TIMEOUT_S)


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pin_records(records):
    """Strip richer loader records down to the exact ``{path, sha256}`` pin pair.

    ``metric_world_domains.support_plan`` requires records whose key set is exactly
    ``{path, sha256}`` -- the path string is part of the support identity -- while
    ``load_native_window`` returns richer annotations (page key, native origin, shape, seed,
    spacing). Copying the two pin members out keeps both contracts unchanged.
    """
    pins = []
    for record in records or []:
        if not isinstance(record, dict) or "path" not in record or "sha256" not in record:
            raise SystemExit("a loader source record carries no path/sha256 pair")
        pins.append({"path": record["path"], "sha256": record["sha256"]})
    if not pins:
        raise SystemExit("the loader returned no source record; a support cannot be declared")
    return pins


def declared_support(name):
    if name not in DECLARED_SUPPORTS:
        raise SystemExit("unknown declared support %r; declared: %s"
                         % (name, sorted(DECLARED_SUPPORTS)))
    plan = DECLARED_SUPPORTS[name]
    origin = list(plan["origin_native_xz"])
    shape = list(plan["shape_zx"])
    cells = int(shape[0] * shape[1])
    if cells > MAX_SUPPORT_CELLS:
        raise SystemExit("the support %r declares %d cells, above the %d ceiling; a larger "
                         "support needs its own budget and a separate review"
                         % (name, cells, MAX_SUPPORT_CELLS))
    return origin, shape, int(plan["plan_version"])


# --------------------------------------------------------------------------- #
# explicit flux inputs
# --------------------------------------------------------------------------- #
def _map_event_flux(support_origin, support_shape, event_dir):
    """Lift the delivered finite event's local flux onto the declared support.

    The event model owns its own support (origin, shape, active set). Only cells that the
    event model actually declares are given an input; every other valid cell of the wider
    support is marked **unavailable**, which the precompute layer then propagates
    downstream as unknown. Nothing is extrapolated and nothing is filled with zero.
    """
    event = Path(event_dir)
    product = json.loads(((event.parent) / "product.json").read_text(encoding="utf-8"))
    domain = product["domain"]
    event_origin = list(domain["origin_native_xz"])
    event_shape = list(domain["grid_shape_zx"])
    event_arrays = event / "arrays.npz"
    active_arrays = event / "active_index.npy"
    if not event_arrays.is_file() or not active_arrays.is_file():
        raise SystemExit("the declared event model is missing %s or %s"
                         % (event_arrays, active_arrays))
    with np.load(event_arrays, allow_pickle=False) as block:
        seconds_edges = np.asarray(block["seconds_edges"], np.float64)
        local_q = np.asarray(block["local_q_m3_s"], np.float64)
    active_index = np.load(active_arrays, allow_pickle=False).astype(np.int64)
    steps = int(seconds_edges.size - 1)
    if local_q.shape != (steps, active_index.size):
        raise SystemExit("the event model declares local_q %s for %d steps and %d active "
                         "cells" % (list(local_q.shape), steps, active_index.size))
    rows, columns = support_shape
    origin = support_origin
    dz = int(event_origin[1]) - int(origin[1])
    dx = int(event_origin[0]) - int(origin[0])
    if dz < 0 or dx < 0 or dz + event_shape[0] > rows or dx + event_shape[1] > columns:
        raise SystemExit("the event model support origin=%s shape=%s is not inside the "
                         "declared support origin=%s shape=%s"
                         % (event_origin, event_shape, origin, support_shape))
    event_columns = int(event_shape[1])
    local = np.zeros((steps, rows * columns), np.float64)
    available = np.zeros(rows * columns, np.bool_)
    local_flat = np.zeros((event_shape[0] * event_columns), np.int64)
    for z in range(event_shape[0]):
        for x in range(event_columns):
            local_flat[z * event_columns + x] = (dz + z) * columns + (dx + x)
    target = local_flat[active_index]
    np.add.at(local, (slice(None), target), local_q)
    available[target] = True
    provenance = {
        "quantity": "source_model_scenario",
        "model": "finite-event soil production (delivered M2 event)",
        "nature": "actual_event_routed_water",
        "product_directory": str(event.parent).replace(os.sep, "/"),
        "product_identity_sha256": product.get("identity_sha256"),
        "time_edges_s": [float(v) for v in seconds_edges],
        "steps": steps,
        "event_origin_native_xz": [int(v) for v in event_origin],
        "event_shape_zx": [int(v) for v in event_shape],
        "event_active_cells": int(active_index.size),
        "availability_policy": ("only cells the event model declares are available; every "
                               "other valid cell of this support is unavailable and is "
                               "propagated downstream as unknown, never read as zero"),
        "calibration": "declared_uncalibrated",
        "claimed_as": "a declared event scenario on this support, not a climatology and not "
                      "a hydraulic state",
        "source_files_sha256": {
            name: _file_sha256(event.parent / name)
            for name in FINITE_PRODUCT_FILES
            if (event.parent / name).is_file()},
    }
    return {
        "local_flux": local.reshape((steps, rows, columns)),
        "available_mask": available.reshape((rows, columns)),
        "gate_time_index": steps - 1,
        "provenance": provenance,
    }, seconds_edges


def _load_climatology_input(path, support_origin, support_shape, steps, edges):
    """Load a **caller-declared** climatology estimate. No estimator is built in."""
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    declared_steps = source.get("steps")
    if declared_steps != steps:
        raise SystemExit("the declared climatology input has %r steps, the clock has %d"
                         % (declared_steps, steps))
    if [float(v) for v in source.get("time_edges_s", [])] != [float(v) for v in edges]:
        raise SystemExit("the declared climatology input must use exactly the clock edges")
    origin = [int(v) for v in source.get("origin_native_xz", [])]
    shape = [int(v) for v in source.get("shape_zx", [])]
    if origin != list(support_origin) or shape != list(support_shape):
        raise SystemExit("the declared climatology input was produced on another support")
    array_path = Path(source["local_flux_npy"])
    local = np.load(array_path, allow_pickle=False).astype(np.float64)
    rows, columns = support_shape
    if local.shape != (steps, rows, columns):
        raise SystemExit("the climatology local flux is %s, expected %s"
                         % (list(local.shape), [steps, rows, columns]))
    available = np.asarray(source.get("available_mask", np.ones((rows, columns), bool)),
                           np.bool_)
    if available.shape != (rows, columns):
        raise SystemExit("the climatology availability mask has the wrong shape")
    for key in ("model", "time_edges_s", "calibration", "completeness_policy"):
        if key not in source:
            raise SystemExit("a declared climatology input must document %r" % key)
    provenance = {
        "quantity": "climatology_estimate",
        "model": source["model"],
        "nature": "declared_estimate_uncalibrated",
        "time_edges_s": [float(v) for v in source["time_edges_s"]],
        "steps": steps,
        "calibration": source["calibration"],
        "completeness_policy": source["completeness_policy"],
        "source_files_sha256": {"local_flux_npy": _file_sha256(array_path)},
        "claimed_as": "an estimate, never a measured or simulated event",
    }
    return {"local_flux": local, "available_mask": available,
            "gate_time_index": steps - 1, "provenance": provenance}


def _event_receiver(event_dir, terminal_world_native):
    """Adapt the delivered finite-sample lake evidence into an explicit receiver record.

    Everything is read from the **same** product directory the event model came from
    (``event/arrays.npz``'s parent), so a caller that points at another copy of the product
    gets that copy's evidence -- never a hard-coded path that would silently mix two.
    """
    from terrain_pipeline.surface_rivers.metric_backbone_precompute import (
        build_event_receiver_record,
    )

    product_dir = Path(event_dir).resolve().parent
    product = json.loads((product_dir / "product.json").read_text(encoding="utf-8"))
    domain = product["domain"]
    with np.load(Path(event_dir) / "arrays.npz", allow_pickle=False) as block:
        seconds_edges = np.asarray(block["seconds_edges"], np.float64)
        volume = np.asarray(block["lake_volume_m3"], np.float64)
        level = np.asarray(block["lake_level_m"], np.float64)
    return build_event_receiver_record(
        terminal_cell_world_native=terminal_world_native,
        product_schema=product["schema"],
        product_identity=_file_sha256(product_dir / "product.json"),
        origin_native_xz=domain["origin_native_xz"],
        shape_zx=domain["grid_shape_zx"],
        terminal_cell_flat=int(domain["terminal_cell_flat"]),
        safe_level_m=float(domain["safe_level_m"]),
        safe_volume_m3=float(domain["safe_capacity_m3"]),
        seconds_edges_s=seconds_edges,
        time_edge_volume_m3=volume,
        time_edge_level_m=level,
        source_files={name: _file_sha256(product_dir / name)
                      for name in FINITE_PRODUCT_FILES
                      if (product_dir / name).is_file()},
        lake_bed_cell_count=int(domain["lake_bed_cells"]),
        active_cell_count=int(domain["active_cells"]),
    )


def _event_terminal_world_native(event_dir):
    product_dir = Path(event_dir).resolve().parent
    product = json.loads((product_dir / "product.json").read_text(encoding="utf-8"))
    domain = product["domain"]
    origin = [int(v) for v in domain["origin_native_xz"]]
    rows, columns = [int(v) for v in domain["grid_shape_zx"]]
    flat = int(domain["terminal_cell_flat"])
    return [origin[0] + flat % columns, origin[1] + flat // columns]


# --------------------------------------------------------------------------- #
# prepare
# --------------------------------------------------------------------------- #
def build_parent(support_name):
    """Rebuild the B1 parent from pinned pages and check it against the delivered identity.

    Returns ``(parent, window, identity_is_pinned)``. ``identity_is_pinned`` is ``False``
    when the delivered evidence for that support was not read, so a run can never claim a
    pin it did not check.
    """
    from terrain_pipeline.surface_rivers import metric_world_domains as domains
    from terrain_pipeline.surface_rivers import native_30m_source as source

    origin, shape, plan_version = declared_support(support_name)
    window = source.load_native_window(
        PINNED_PAGES, origin_native_xz=origin, shape_zx=shape,
        world_seed=WORLD_SEED, max_cells=MAX_SUPPORT_CELLS)
    support = domains.support_plan(
        world_seed=WORLD_SEED, spacing_m=SPACING_M, origin_native_xz=origin,
        shape_zx=shape, source_records=_pin_records(window["source_records"]),
        plan_version=plan_version, max_cells=MAX_SUPPORT_CELLS)
    parent = domains.domain_candidates(support, source=window,
                                       source_kind=domains.SOURCE_KIND_PINNED)
    pinned = PINNED_PARENT_IDENTITY.get(support_name)
    if pinned is not None and pinned != parent["identity_sha256"]:
        raise SystemExit("the rebuilt parent for %r has identity %s, the delivered evidence "
                         "says %s; refusing to build a backbone on a drifted parent"
                         % (support_name, parent["identity_sha256"], pinned))
    return parent, window, pinned is not None


def prepare(arguments):
    from terrain_pipeline.surface_rivers import metric_backbone_precompute as precompute
    from terrain_pipeline.surface_rivers import metric_backbone_product as product_module

    started = time.monotonic()
    origin, shape, plan_version = declared_support(arguments.plan)
    output = Path(arguments.output).resolve()
    under_artifacts = (ROOT / "artifacts").resolve() in output.parents
    if under_artifacts and not arguments.allow_artifact_target:
        raise SystemExit("refusing to write under artifacts/ without --allow-artifact-target; "
                         "the formal product target is "
                         "artifacts/river-backbone-precompute-v1/ and it may only be written "
                         "after a PASS in the same run")
    if output.exists():
        raise SystemExit("refusing to overwrite an existing output directory: %s" % output)

    parent, window, parent_pinned = build_parent(arguments.plan)

    quantities = {}
    edges = None
    if arguments.event_dir:
        quantities["source_model_scenario"], edges = _map_event_flux(
            origin, shape, arguments.event_dir)
    if arguments.climatology_input:
        if edges is None:
            document = json.loads(Path(arguments.climatology_input).read_text(encoding="utf-8"))
            edges = np.asarray(document["time_edges_s"], np.float64)
        quantities["climatology_estimate"] = _load_climatology_input(
            arguments.climatology_input, origin, shape,
            int(np.asarray(edges).size - 1), edges)
    if edges is None:
        raise SystemExit("at least one explicit flux input is required (--event-dir or "
                         "--climatology-input); this tool builds no estimator of its own")

    event_receiver = None
    if arguments.event_receiver:
        event_receiver = _event_receiver(arguments.event_dir,
                                         _event_terminal_world_native(arguments.event_dir))

    # Every declared flux quantity gets one bounded branch-resolution rule: the branches are
    # the non-channel cells carrying that quantity's local input, and each is resolved to a
    # single side-input slot (aggregated or refined), never to both.
    side_rules = {name: {"mode": arguments.side_mode,
                         "max_branches": arguments.max_branches}
                  for name in quantities}

    bundle = precompute.build_backbone(
        parent=parent, quantities=quantities,
        a_min_cells=arguments.a_min_cells, q_min_m3_s=arguments.q_min_m3_s,
        time_edges_s=edges, event_receiver=event_receiver,
        side_inputs=side_rules, max_cells=MAX_SUPPORT_CELLS)
    precompute.validate_backbone(bundle, parent)

    payload = sum(int(np.asarray(value).nbytes) for value in bundle["arrays"].values())
    if payload > MAX_OUTPUT_BYTES:
        raise SystemExit("the product payload would be %d bytes, above the %d budget; "
                         "refusing before writing" % (payload, MAX_OUTPUT_BYTES))

    work_parent = output.parent
    work_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="." + output.name + ".partial-", dir=work_parent))
    try:
        (work / "parent-reference.json").write_text(_json({
            "schema": "river-backbone-parent-reference-v1",
            "support_name": arguments.plan,
            "origin_native_xz": origin,
            "shape_zx": shape,
            "plan_version": plan_version,
            "world_seed": WORLD_SEED,
            "spacing_m": SPACING_M,
            "parent_schema": parent["schema"],
            "parent_identity_sha256": parent["identity_sha256"],
            "parent_identity_pinned": bool(parent_pinned),
            "support_identity_sha256": parent["metadata"]["support_identity_sha256"],
            "source_records": window["source_records"],
            "assembly_digest": window["assembly_digest"],
        }), encoding="utf-8")
        product_module.save_backbone_product(work / "product", bundle)
        record = {
            "schema": "river-backbone-prepare-v1",
            "support_name": arguments.plan,
            "declared_gates": {"a_min_cells": arguments.a_min_cells,
                               "q_min_m3_s": arguments.q_min_m3_s},
            "quantities": sorted(quantities),
            "side_mode": arguments.side_mode,
            "max_branches": int(arguments.max_branches),
            "event_receiver": bool(event_receiver),
            "side_input_branches": {name: record["branch_count"]
                                     for name, record in
                                     (bundle["metadata"]["side_inputs"] or {}).items()},
            "payload_bytes": payload,
            "stage_wall_s": round(time.monotonic() - started, 3),
            "memory_budget_bytes": STAGE_MEMORY_BUDGET_BYTES,
            "memory_budget_status": "declared_not_measured_by_this_step",
        }
        (work / "prepare-record.json").write_text(_json(record), encoding="utf-8")
        audited = _audit_child(work)
        report = None
        if (work / "audit.json").is_file():
            report = json.loads((work / "audit.json").read_text(encoding="utf-8"))
        record["audit"] = audited
        record["memory_budget_status"] = (
            "sampled_observation_only" if audited["rss_sample"]["observed_peak_bytes"] is not None
            else "unverified_psutil_unavailable")
        (work / "prepare-record.json").write_text(_json(record), encoding="utf-8")
        completed = audited
        if completed["returncode"] != 0 or report is None or report.get("status") != "PASS":
            rejected = _stash_rejected(work, output)
            print(_json({"status": "REJECTED", "evidence": str(rejected),
                         "audit_returncode": completed["returncode"],
                         "audit_status": None if report is None else report.get("status"),
                         "audit_reasons": None if report is None else report.get("reasons"),
                         "audit_stderr_tail": completed["stderr_tail"],
                         "rss_sample": completed["rss_sample"]}))
            return 1
        if output.exists():
            raise SystemExit("refusing to overwrite an existing output directory: %s" % output)
        os.rename(work, output)
        print(_json({"status": "PASS", "output": str(output),
                     "product_identity_sha256": bundle["identity_sha256"],
                     "counts": bundle["metadata"]["counts"],
                     "wall_s": round(time.monotonic() - started, 3),
                     "rss_sample": record["audit"]["rss_sample"],
                     "memory_budget_status": record["memory_budget_status"]}))
        return 0
    except BaseException:
        if work.exists():
            _stash_rejected(work, output)
        raise


def _stash_rejected(work, output):
    target = output.parent / (output.name + ".rejected-" + work.name.split("partial-")[-1])
    if not target.exists():
        shutil.move(str(work), str(target))
        return target
    return work


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", required=True, choices=("prepare", "list-plans", "preflight"))
    parser.add_argument("--plan", choices=tuple(sorted(DECLARED_SUPPORTS)))
    parser.add_argument("--event-dir",
                        help="directory of the delivered finite event model "
                             "(defaults to the promoted product's event/ folder)")
    parser.add_argument("--climatology-input",
                        help="a caller-declared climatology estimate JSON with a local flux "
                             "npy; no estimator is built in")
    parser.add_argument("--event-receiver", action="store_true",
                        help="adapt the delivered finite-sample lake evidence into an explicit "
                             "event_receiver record")
    parser.add_argument("--a-min-cells", type=int, default=48)
    parser.add_argument("--q-min-m3-s", type=float, default=1.0e-3)
    parser.add_argument("--side-mode", choices=("aggregated", "refined"), default="refined",
                        help="the single side-input representation each branch is resolved to; "
                             "both are computed and compared, only one is counted")
    parser.add_argument("--max-branches", type=int, default=1024,
                        help="declared ceiling on resolved branches (default 1024, the core's "
                             "DEFAULT_MAX_BRANCHES); exceeding it refuses rather than "
                             "dropping branches")
    parser.add_argument("--output")
    parser.add_argument("--allow-artifact-target", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.mode == "list-plans":
        print(_json({"declared_supports": DECLARED_SUPPORTS,
                     "pinned_pages": PINNED_PAGES,
                     "staging_root": STAGING_ROOT,
                     "formal_target": "artifacts/river-backbone-precompute-v1/",
                     "budgets": {"max_support_cells": MAX_SUPPORT_CELLS,
                                 "audit_timeout_s": AUDIT_TIMEOUT_S,
                                 "stage_memory_budget_bytes": STAGE_MEMORY_BUDGET_BYTES,
                                 "max_output_bytes": MAX_OUTPUT_BYTES}}))
        return 0
    if arguments.plan is None:
        raise SystemExit("--plan is required")
    if arguments.mode == "preflight":
        origin, shape, plan_version = declared_support(arguments.plan)
        cells = int(shape[0] * shape[1])
        event_available = (ROOT / FINITE_PRODUCT / "event" / "arrays.npz").is_file()
        fields = 0
        if event_available:
            with np.load(ROOT / FINITE_PRODUCT / "event" / "arrays.npz",
                         allow_pickle=False) as block:
                fields = int(np.asarray(block["local_q_m3_s"]).size)
                steps = int(np.asarray(block["seconds_edges"]).size - 1)
        else:
            steps = 0
        report = {
            "schema": "river-backbone-preflight-v1",
            "support_name": arguments.plan,
            "origin_native_xz": origin,
            "shape_zx": shape,
            "plan_version": plan_version,
            "cells": cells,
            "steps": steps,
            "working_arrays": {
                "receiver_int64_bytes": cells * 8,
                "valid_mask_bool_bytes": cells,
                "terminal_kind_u24_bytes": cells * 24 * 4,
                "area_int64_bytes": cells * 8,
                "area_complete_bool_bytes": cells,
                "channel_mask_bool_bytes": cells,
                "local_flux_float64_bytes": steps * cells * 8,
                "accumulated_flux_float64_bytes": steps * cells * 8,
            },
            "single_process_peak_estimate_bytes": (
                cells * (8 + 1 + 96 + 8 + 1 + 1) + 2 * steps * cells * 8),
            "declared_budget": {"max_support_cells": MAX_SUPPORT_CELLS,
                                "stage_memory_budget_bytes": STAGE_MEMORY_BUDGET_BYTES,
                                "audit_timeout_s": AUDIT_TIMEOUT_S,
                                "max_output_bytes": MAX_OUTPUT_BYTES},
            "event_model_available": event_available,
            "event_model_local_q_entries": fields,
            "notes": ("the estimate counts the working arrays this stage holds at once; "
                     "interpreter and library overhead is outside it and is not claimed"),
        }
        print(_json(report))
        return 0
    if arguments.output is None:
        raise SystemExit("--output is required for prepare")
    if arguments.event_dir is None and arguments.climatology_input is None:
        arguments.event_dir = str(ROOT / FINITE_PRODUCT / "event")
    return prepare(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
