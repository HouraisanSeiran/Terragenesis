"""Prepare one declared metric world-domain candidate package, then audit it cold.

This tool is scheduling and I/O only: the support plan, the domain candidates and
their identity belong to ``terrain_pipeline.surface_rivers.metric_world_domains``
(lazily imported, and only on the ``prepare`` path). Nothing algorithmic lives
here.

Flow, in this order and no other:

1. the support is **declared before any page is read**: world seed, 30 m spacing,
   signed native origin, ``shape_zx``, the plan version and the cell budget;
2. the four pinned TD pages are loaded through ``load_native_window`` with their
   SHA256 pins, so the real pages are read and hashed rather than trusted;
3. the producer builds the candidate bundle;
4. the bundle is written as ``manifest.json`` + ``arrays.npz`` inside a hidden
   partial directory (never as an object array, never as non-finite JSON);
5. a **separate process** runs ``tools/audit_world_domains.py`` against that
   partial directory;
6. only a ``PASS`` is renamed into the requested output path. A failure keeps the
   partial evidence under a new ``*.rejected*`` name and the output path stays
   absent, so a failing run can never leave something that looks like a product.

Declared scale ladder (``parameters.md``): P1 ``257²`` = 66 049 and P2 ``385²`` =
148 225 cells are the only supports declared here; every run is checked against
that budget and a window is never silently enlarged.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "metric-world-domain-candidates-v1"
PREPARE_SCHEMA = "metric-world-domain-candidates-prepare-v1"
MANIFEST_NAME = "manifest.json"
ARRAYS_NAME = "arrays.npz"
AUDIT_NAME = "audit.json"

WORLD_SEED = 20261020
SPACING_M = 30.0
MAX_SUPPORT_CELLS = 148225

#: Hard stop for the **cold audit step only** (not for the whole prepare: reading the
#: pinned pages and the producer run have their own, separately observed cost).
#: A single audit of a declared window takes a few seconds; 60 s leaves headroom
#: without pretending the whole prepare is bounded by this number.
AUDIT_TIMEOUT_S = 60.0

#: Declared supports. Nothing here is discovered at run time, and no origin is
#: derived from a render window.
DECLARED_SUPPORTS = {
    "p1": {"origin_native_xz": (42173, 42874), "shape_zx": (257, 257),
           "note": "P1 development window: pipeline and decision words"},
    "p2": {"origin_native_xz": (42173, 42874), "shape_zx": (385, 385),
           "note": "P2 development window: topology and hierarchy at 385x385"},
    "p2-shifted": {"origin_native_xz": (42270, 42743), "shape_zx": (385, 385),
                   "note": "P2 same size, translated: a window-family comparison "
                           "of overlapping world roots"},
}

ARRAY_DTYPES = {
    "elevation_m": np.dtype(np.float64),
    "resolved_mask": np.dtype(np.bool_),
    "receiver": np.dtype(np.int64),
    "terminal_kind": None,
    "upstream_unknown_mask": np.dtype(np.bool_),
    "complete_mask": np.dtype(np.bool_),
    "upstream_cells": np.dtype(np.int64),
    "owner_index": np.dtype(np.int64),
    "root_cells": np.dtype(np.int64),
    "root_complete": np.dtype(np.bool_),
    "member_counts": np.dtype(np.int64),
    "member_ptr": np.dtype(np.int64),
    "member_cells": np.dtype(np.int64),
    "mainstem_ptr": np.dtype(np.int64),
    "mainstem_cells": np.dtype(np.int64),
    "shared_face_cells": np.dtype(np.int64),
}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _stable_json(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False)


def array_sha256(value):
    """The declared arrays hash rule shared with the audit: shape, dtype, bytes."""
    import hashlib
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(tuple(array.shape)).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# 1. declared support and source records
# --------------------------------------------------------------------------- #
def declared_support(name):
    if name not in DECLARED_SUPPORTS:
        raise SystemExit("unknown declared plan %r; known: %s"
                         % (name, sorted(DECLARED_SUPPORTS)))
    entry = DECLARED_SUPPORTS[name]
    origin = tuple(int(value) for value in entry["origin_native_xz"])
    shape = tuple(int(value) for value in entry["shape_zx"])
    return origin, shape


def resolve_support(plan, origin_native_xz, shape_zx):
    """Explicit origin/shape wins, but the budget is checked either way."""
    if plan is not None:
        declared_origin, declared_shape = declared_support(plan)
        if origin_native_xz is not None and tuple(origin_native_xz) != declared_origin:
            raise SystemExit("origin %s contradicts declared plan %s (%s)"
                             % (list(origin_native_xz), plan, list(declared_origin)))
        if shape_zx is not None and tuple(shape_zx) != declared_shape:
            raise SystemExit("shape %s contradicts declared plan %s (%s)"
                             % (list(shape_zx), plan, list(declared_shape)))
        origin, shape = declared_origin, declared_shape
    else:
        if origin_native_xz is None or shape_zx is None:
            raise SystemExit("an ad-hoc support needs both --origin-native-xz and "
                             "--shape-zx, or name a declared plan with --plan")
        origin, shape = tuple(origin_native_xz), tuple(shape_zx)
    if len(origin) != 2 or len(shape) != 2:
        raise SystemExit("origin and shape are both two-element pairs")
    if min(shape) < 2:
        raise SystemExit("shape %s is below the declared 2x2 minimum" % (list(shape),))
    cells = int(shape[0]) * int(shape[1])
    if cells > MAX_SUPPORT_CELLS:
        raise SystemExit("support %dx%d = %d cells exceeds the declared budget of %d; "
                         "a larger support needs its own declared budget and a "
                         "separate review"
                         % (shape[0], shape[1], cells, MAX_SUPPORT_CELLS))
    return origin, shape


def read_source_records(path):
    """The four pinned page records from a ``native-30m-source-request`` file."""
    target = Path(path)
    if not target.is_file():
        raise SystemExit("source request not found: %s" % target)
    request = json.loads(target.read_text(encoding="utf-8"), parse_constant=_reject)
    records = request.get("source_records")
    if not isinstance(records, list) or not records:
        raise SystemExit("source request carries no source_records: %s" % target)
    cleaned = []
    for item in records:
        if not isinstance(item, dict):
            raise SystemExit("a source record must be an object")
        page = item.get("path")
        sha = item.get("sha256")
        if not isinstance(page, str) or not page:
            raise SystemExit("a source record has no path")
        if not isinstance(sha, str) or len(sha) != 64:
            raise SystemExit("a source record has no 64-character sha256")
        cleaned.append({"path": page, "sha256": sha})
    seeds = {item.get("world_seed") for item in [request] if item.get("world_seed") is not None}
    if seeds and seeds != {WORLD_SEED}:
        raise SystemExit("source request world_seed %s contradicts the frozen seed %d"
                         % (sorted(seeds), WORLD_SEED))
    return cleaned, target


def _reject(value):
    raise SystemExit("non-finite JSON constant: %s" % value)


# --------------------------------------------------------------------------- #
# 2. the prepare path (the only place the producer is imported)
# --------------------------------------------------------------------------- #
def build_bundle(source_request, *, origin, shape, plan_version, source_kind="td_pinned"):
    """Call the producer. Imported here so no other path can load it."""
    from terrain_pipeline.surface_rivers import metric_world_domains
    from terrain_pipeline.surface_rivers.native_30m_source import load_native_window

    records, request_path = read_source_records(source_request)
    support = metric_world_domains.support_plan(
        world_seed=WORLD_SEED, spacing_m=SPACING_M,
        origin_native_xz=origin, shape_zx=shape,
        source_records=records, plan_version=plan_version,
        max_cells=MAX_SUPPORT_CELLS)
    source = load_native_window(records, origin_native_xz=origin, shape_zx=shape,
                                world_seed=WORLD_SEED, max_cells=MAX_SUPPORT_CELLS)
    bundle = metric_world_domains.domain_candidates(support, source=source,
                                                    source_kind=source_kind)
    return bundle, source, request_path, records


def check_bundle(bundle):
    """Only the structural declarations this tool is allowed to insist on."""
    if not isinstance(bundle, dict):
        raise SystemExit("the producer did not return a bundle")
    if bundle.get("schema") != SCHEMA:
        raise SystemExit("unexpected bundle schema %r (expected %r)"
                         % (bundle.get("schema"), SCHEMA))
    arrays = bundle.get("arrays")
    if not isinstance(arrays, dict) or not arrays:
        raise SystemExit("the bundle carries no arrays")
    missing = sorted(set(ARRAY_DTYPES) - set(arrays))
    if missing:
        raise SystemExit("the bundle is missing declared arrays: %s" % missing)
    for name, expected in ARRAY_DTYPES.items():
        value = arrays[name]
        if not isinstance(value, np.ndarray):
            raise SystemExit("array %s is not an ndarray" % name)
        if value.dtype.hasobject:
            raise SystemExit("array %s would need pickle; object arrays are refused" % name)
        if expected is not None and value.dtype != expected:
            raise SystemExit("array %s has dtype %s, expected %s"
                             % (name, value.dtype.str, expected.str))
        if expected is None and value.dtype.kind != "U":
            raise SystemExit("array %s must be a Unicode string array" % name)
        if value.dtype.kind == "f" and name != "elevation_m":
            if not np.isfinite(value).all():
                raise SystemExit("array %s carries non-finite values" % name)
    if "identity_sha256" not in bundle:
        raise SystemExit("the bundle has no identity_sha256")
    for key in ("support", "metadata", "candidates"):
        if key not in bundle:
            raise SystemExit("the bundle has no %s record" % key)
    return arrays


# --------------------------------------------------------------------------- #
# 3. writing the partial package
# --------------------------------------------------------------------------- #
def write_partial(work, bundle, arrays, *, plan_name, origin, shape, plan_version,
                  source_request, records, source):
    work.mkdir(parents=True, exist_ok=False)
    npz_path = work / ARRAYS_NAME
    # ``np.savez`` writes a plain archive of .npy members; nothing is pickled.
    with open(npz_path, "wb") as stream:
        np.savez(stream, **{name: arrays[name] for name in sorted(arrays)})
    records_out = {
        name: {"shape": list(arrays[name].shape), "dtype": arrays[name].dtype.str,
               "sha256": array_sha256(arrays[name])}
        for name in sorted(arrays)
    }
    assembly = source.get("assembly_digest")
    manifest = {
        "schema": bundle["schema"],
        "prepare_schema": PREPARE_SCHEMA,
        "support": bundle["support"],
        "metadata": bundle["metadata"],
        "candidates": bundle["candidates"],
        "identity_sha256": bundle["identity_sha256"],
        "arrays": records_out,
        "source_binding": {
            "kind": "content_binding_not_signature",
            "page_records": records,
            "source_request": str(source_request),
            "assembly_digest": assembly,
            "source_kind": source.get("source_kind", "td_pinned"),
            "statement": ("the page SHA256 list is a content binding recorded here; "
                          "it is not a signature and not an external pin"),
        },
        "declaration": {
            "plan_name": plan_name,
            "plan_version": int(plan_version),
            "origin_native_xz": list(origin),
            "shape_zx": list(shape),
            "support_cells": int(shape[0]) * int(shape[1]),
            "max_cells": MAX_SUPPORT_CELLS,
            "world_seed": WORLD_SEED,
            "spacing_m": SPACING_M,
            "storage_representation": "signed_int64_native_cells",
            "layer": "structural_candidate",
            "not_a_lake": ("basin_pending is not a natural lake and not a legal "
                           "hydrological domain"),
            "not_production_default": True,
        },
    }
    (work / MANIFEST_NAME).write_text(_stable_json(manifest) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------- #
# 4. cold audit in a separate process, then publish
# --------------------------------------------------------------------------- #
def run_audit(work, *, timeout_s=AUDIT_TIMEOUT_S, sample_s=0.25):
    """Audit in a fresh interpreter so the producer cannot be reused.

    ``timeout_s`` is the only *hard* stop and it belongs to **this audit step only**;
    it is not a claim that the whole prepare (page read + producer + audit) fits in it.
    The elapsed time is measured with ``time.monotonic``, so a wall-clock adjustment
    cannot move the deadline. The memory figure is a **sample observation**, not a limit,
    read from the child's process tree when ``psutil`` is importable and reported as
    ``None`` otherwise.
    """
    audit_path = work / AUDIT_NAME
    command = [sys.executable, "-B", str(ROOT / "tools" / "audit_world_domains.py"),
               "--bundle", str(work), "--report", str(audit_path)]
    try:
        import psutil
    except ImportError:                                  # observation only
        psutil = None
    started = time.monotonic()
    peak_rss = None
    peak_rss_at_s = None
    timed_out = False
    process = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    handle = psutil.Process(process.pid) if psutil is not None else None
    while True:
        if process.poll() is not None:
            break
        elapsed = time.monotonic() - started
        if elapsed > timeout_s:
            timed_out = True
            process.kill()
            break
        if handle is not None:
            try:
                total = handle.memory_info().rss
                for child in handle.children(recursive=True):
                    try:
                        total += child.memory_info().rss
                    except psutil.Error:
                        continue
                if peak_rss is None or total > peak_rss:
                    peak_rss = int(total)
                    peak_rss_at_s = round(elapsed, 3)
            except psutil.Error:
                handle = None
        time.sleep(sample_s)
    stdout, stderr = process.communicate()
    elapsed = time.monotonic() - started
    record = {
        "command": command[1:],
        "returncode": process.returncode,
        "clock": "time.monotonic",
        "elapsed_s": round(elapsed, 3),
        "timed_out": timed_out,
        "hard_stop_s": timeout_s,
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
        "rss_sample": {
            "observed_peak_bytes": peak_rss,
            "observed_peak_at_s": peak_rss_at_s,
            "sampled_every_s": sample_s,
            "is_limit": False,
            "note": ("a sampled observation of the audit child's RSS, not a "
                     "resource limit and not a per-stage peak"),
        },
    }
    try:
        report = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = None
    return process.returncode, report, record


def publish(work, output):
    """Commit the partial directory, without ever overwriting a target.

    ``os.rename`` is used, not ``os.replace``: on this platform a rename onto an
    existing directory fails, which is exactly the guarantee wanted here (``replace``
    could silently swap in an empty or populated POSIX target). The target is checked
    with ``lexists`` so a dangling symlink also counts as taken.

    Platform boundary, stated rather than claimed away: this makes the commit
    non-overwriting on Windows; on POSIX ``rename`` onto a *file* would still replace
    it. A portable atomic no-clobber claim (``link`` / ``renameat2(RENAME_NOREPLACE)``)
    is a separate design and is **not** claimed to be certified here.
    """
    target = Path(output)
    if os.path.lexists(str(target)):
        raise SystemExit("output already exists (including a dangling symlink), "
                         "refusing to commit: %s" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(str(target)):
        raise SystemExit("output appeared while preparing, refusing to commit: %s" % target)
    os.rename(str(work), str(target))       # not os.replace: never clobbers
    return target


def stash_rejected(work, output):
    """Keep the failing evidence under a new name; never at the output path."""
    base = Path(output)
    for suffix in ["rejected"] + ["rejected-%d" % index for index in range(2, 100)]:
        candidate = base.with_name(base.name + "." + suffix)
        if not candidate.exists():
            os.replace(str(work), str(candidate))
            return candidate
    raise SystemExit("no free rejected-evidence name next to %s; the partial evidence "
                     "stays at %s" % (base, work))


def prepare(arguments):
    requested = Path(arguments.output)
    # Do not follow a symlinked target: the commit must land on the path asked for.
    if requested.is_symlink():
        raise SystemExit("refusing to follow a symlinked output target: %s" % requested)
    output = requested.resolve()
    if os.path.lexists(str(requested)):
        raise SystemExit("output already exists (including a dangling symlink), "
                         "refusing to prepare: %s" % requested)
    origin, shape = resolve_support(arguments.plan, arguments.origin_native_xz,
                                    arguments.shape_zx)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".%s.partial-" % output.name, dir=str(output.parent)))
    work.rmdir()
    try:
        bundle, source, request_path, records = build_bundle(
            arguments.source_request, origin=origin, shape=shape,
            plan_version=arguments.plan_version)
        arrays = check_bundle(bundle)
        write_partial(work, bundle, arrays, plan_name=arguments.plan,
                      origin=origin, shape=shape, plan_version=arguments.plan_version,
                      source_request=request_path, records=records, source=source)
        returncode, report, audit_record = run_audit(work)
        status = None if report is None else report.get("status")
        (work / "prepare-record.json").write_text(
            _stable_json({"schema": PREPARE_SCHEMA, "audit": audit_record,
                          "audit_status": status}) + "\n", encoding="utf-8")
        if returncode == 0 and status == "PASS":
            target = publish(work, output)
            print(_json({"status": "PUBLISHED", "output": str(target),
                         "plan": arguments.plan, "origin": list(origin),
                         "shape": list(shape), "counters": report.get("counters", {})}))
            return 0
        rejected = stash_rejected(work, output)
        print(_json({"status": "REJECTED", "evidence": str(rejected),
                     "audit_returncode": returncode,
                     "audit_reasons": None if report is None else report.get("reasons")}))
        return 1
    except BaseException:
        if work.exists():
            stash_rejected(work, output)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", required=True, choices=("prepare", "list-plans"))
    parser.add_argument("--source-request",
                        help="existing native-30m-source-request JSON with the pinned pages")
    parser.add_argument("--origin-native-xz", nargs=2, type=int, metavar=("X", "Z"),
                        help="signed native origin; declared before any page is read")
    parser.add_argument("--shape-zx", nargs=2, type=int, metavar=("ROWS", "COLS"))
    parser.add_argument("--plan", choices=tuple(sorted(DECLARED_SUPPORTS)),
                        help="a declared support from the scale ladder")
    parser.add_argument("--plan-version", type=int, default=None,
                        help="explicit integer plan version (required for prepare)")
    parser.add_argument("--output", help="new output directory; must not exist")
    arguments = parser.parse_args(argv)
    if arguments.mode == "list-plans":
        print(_stable_json(DECLARED_SUPPORTS))
        return 0
    if arguments.source_request is None or arguments.output is None:
        raise SystemExit("--source-request and --output are required for prepare")
    if arguments.plan_version is None or arguments.plan_version < 1:
        raise SystemExit("--plan-version must be an explicit positive integer")
    return prepare(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
