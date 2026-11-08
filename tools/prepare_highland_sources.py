"""Prepare one declared highland source region package, then validate it cold.

This tool is scheduling and I/O only. The geometry rule, the region membership, the
head selection, the arrays and the identity belong to
``terrain_pipeline.surface_rivers.metric_highland_sources``; nothing algorithmic is
re-implemented here.

Flow, in this order and no other:

1. the support is **declared before any page is read**: world seed, 30 m spacing,
   signed native origin, ``shape_zx`` and the cell budget. Only the supports declared
   in this tool's ``DECLARED_SUPPORTS`` table are accepted -- the development support
   D, the pre-registered lowland hold-out H, and (per
   ``.scratch/infinite-river-completion/issues/02-source-support-validation.md``) the
   development re-check E and its consistency control V -- so a run cannot quietly
   pick a nicer window. Each entry carries an explicit ``role`` and ``holdout`` flag:
   D and E are development, V is a consistency control, and **only H is a hold-out**.
   E extends D by 60 cells towards high z, in a direction that was already explored,
   and V is E read with 5 cells of margin on every side -- both are declared
   **non-holdout** and neither is an independent confirmation;
2. the source request is read with a **byte limit and a strict JSON parser** and must
   carry an external SHA256 pin of its own file; every page record carries its own
   pin. Nothing is discovered at run time;
3. every page archive passes an **NPY-header gate before any array is allocated**: the
   member set, dtype, Fortran order and the byte count the ZIP reports are all checked
   against the header, so a header that claims one extent and holds another is refused
   without ``numpy`` ever building the array;
4. the pinned pages are assembled through ``native_30m_source.load_native_window``, so
   unresolved cells stay unresolved: the original ``NaN`` / ``mask`` pattern is
   preserved and never filled, extrapolated or repaired here either;
5. the geometry bundle is built and then **fully validated** by
   ``metric_highland_sources.validate_highland_sources`` -- the validator rebuilds the
   strict D8, the contribution and the completeness from the stored field and mask;
6. only a successful validation is written, into a fresh output directory created
   exclusively (``exist_ok=False``): an existing destination is refused and **no
   partial product is ever left behind**;
7. the input pages are hashed again after the run; a changed input fails the run
   instead of producing evidence of a source that no longer exists;

8. the manifest records what the run actually observed, and never dresses an
   observation up as a stronger claim: the **code** digest of this tool and of every
   producer module it calls, and **sampled current RSS** at named stages -- explicitly
   labelled ``sampled_current_rss_not_peak``, because a sample is not a peak and a
   payload estimate is not a memory limit. The manifest also carries a per-head
   diagnostic table that keeps ``own_upstream_complete`` and ``region_complete``
   **separate**, so a reader cannot mistake a region's edge reason for the head's own
   upstream state. That table is derived from the stored arrays and is re-derived and
   compared at cold read; it is not a new field of the algorithm bundle.

The stage boundary is restated in every manifest: this product is
``geometry_candidates_only``. ``rainfall_supported`` stays
``rainfall_supported_pending`` and ``perennial_flow_certified`` stays ``False``. A
region or a head candidate is not water, not a discharge and not a perennial river.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import math
import shutil
import tempfile
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "metric-highland-sources-prepare-v2"
#: The previous manifest schema. Its packages are still read (a package written before the
#: head diagnostics, the code digest and the RSS samples existed is not invalidated by
#: their arrival), but the new blocks are **required** only under ``SCHEMA``. Reading an old
#: package therefore keeps working while a new one cannot quietly omit them, and no old
#: evidence file has to be rewritten.
LEGACY_SCHEMAS = ("metric-highland-sources-prepare-v1",)
MANIFEST_NAME = "manifest.json"
ARRAYS_NAME = "arrays.npz"
VALIDATION_NAME = "validation.json"

WORLD_SEED = 20261020
SPACING_M = 30.0
MAX_SUPPORT_CELLS = 148_225

#: Input gates of this tool, all applied **before** an array is materialised.
MAX_REQUEST_BYTES = 1 * 1024 * 1024
MAX_PAGE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_PAGE_BYTES = 192 * 1024 * 1024
MAX_PAGE_MEMBERS = 8
MAX_HEADER_BYTES = 4096
#: A native page is square; the side budget is checked on the NPY header **before** any
#: array exists, so a header claiming an enormous side is refused without allocation.
MAX_PAGE_SIDE = 4096

#: The RSS label this tool records. A sample is taken at named stages and is **not** a
#: peak: no continuous monitor runs, and a payload estimate is not a memory limit.
RSS_METRIC = "sampled_current_rss_not_peak"

#: Producer modules whose content digest is recorded. Self-reported and not a signature,
#: but it makes the code that produced a package observable, and duplicated digests are
#: cross-bound at cold read.
CODE_FILES = (
    "tools/prepare_highland_sources.py",
    "terrain_pipeline/surface_rivers/metric_highland_sources.py",
    "terrain_pipeline/surface_rivers/native_30m_source.py",
    "terrain_pipeline/surface_rivers/metric_cross_region.py",
    'terrain_pipeline/drainage.py',
    "terrain_pipeline/mountain_source_adapter.py",
)

HEAD_DIAGNOSTICS_SCHEMA = "highland-head-diagnostics-v1"

#: The only supports this tool will prepare, declared in advance. D is the development
#: support, H the frozen lowland hold-out, E the development re-check that extends D
#: towards high z, and V the consistency control that reads E's ground with 5 cells of
#: margin on every side. No origin is derived from a render window, H is not a
#: substitute for D, and **E and V are not hold-outs**: E extends a direction that was
#: already explored (so it is a development re-check, not a fresh confirmation) and V is
#: a second read of almost the same ground, not an independent sample of the world. No
#: entry may be re-used to claim a hold-out result.
DECLARED_SUPPORTS = {
    "D": {
        "origin_native_xz": (42173, 42874),
        "shape_zx": (257, 257),
        "role": "development",
        "holdout": False,
        "note": "fixed development support; thresholds were frozen on its survey",
    },
    "H": {
        "origin_native_xz": (42685, 42874),
        "shape_zx": (257, 257),
        "role": "holdout",
        "holdout": True,
        "note": ("frozen hold-out: D origin plus 512 native cells in x, same z span; "
                 "pre-registered by a space rule without reading H's terrain or any "
                 "candidate river line; not statistically independent of D (same "
                 "saved page set)"),
    },
    # The two supports of the source-support-validation card, fixed there before any run
    # of it and not re-chosen here.
    "E": {
        "origin_native_xz": (42173, 42874),
        "shape_zx": (317, 257),
        "role": "development_recheck",
        "holdout": False,
        "note": ("development re-check: the D origin extended by 60 native cells towards "
                 "high z (same x span, z span 317 instead of 257); that direction was "
                 "already explored, so this is a development re-check and NOT a "
                 "hold-out; the frozen thresholds are not re-fitted on it and the "
                 "148225-cell support ceiling is not raised for it"),
    },
    "V": {
        "origin_native_xz": (42168, 42869),
        "shape_zx": (327, 267),
        "role": "consistency_control",
        "holdout": False,
        "note": ("support-consistency control: E read again with 5 native cells of margin "
                 "on every side (z 317+10, x 257+10); it is a second read of the same "
                 "saved pages, not the same saved image re-cropped and not an "
                 "independent sample of the world, so agreement with E is a "
                 "consistency check and never a hold-out confirmation"),
    },
}


def _reject_constant(value):
    raise ValueError("non-finite JSON constant: %s" % (value,))


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: %s' % key)
        result[key] = value
    return result


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(value):
    """The shared array digest rule: shape, dtype, C-order bytes."""
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(tuple(array.shape)).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _stable_json(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False)


def code_digests():
    """Content digest of this tool and of each producer module it calls.

    A self-report, not a signature: it makes the code that produced a package
    observable, and a digest recorded twice is cross-bound at cold read. It never
    claims the pin of a page, and a mismatch with a later checkout means "the code
    moved", not "the package is forged".
    """
    digests = {}
    for relative in CODE_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError("declared code file is missing: %s" % relative)
        digests[relative] = file_sha256(path)
    return {
        "files": digests,
        "statement": ("content digests of the tool and the producer modules; a "
                      "self-report, not a signature and not an external pin"),
    }


def rss_sample_bytes():
    """Current process RSS, or ``None`` when it cannot be measured here.

    A **sample**, taken at a named stage. It is not read as a peak, and an absent
    value is recorded as absent instead of filled with an estimate.
    """
    try:
        import psutil
    except ImportError:
        return None
    try:
        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


def rss_sample(samples, stage, started):
    """Append one labelled sample; nothing here is called a peak."""
    samples.append({
        "stage": str(stage),
        "elapsed_s": float(time.monotonic() - started),
        "current_rss_bytes": rss_sample_bytes(),
    })
    return samples


def head_diagnostics(bundle):
    """Per-head table that keeps the two certification conjuncts **apart**.

    A head is certified only when its own upstream is complete *and* its region is
    complete, so a head row carries its region's reasons too. That makes it easy to
    read a region's edge reason as the head's own upstream state, which is exactly the
    misreading this table removes: ``own_upstream_complete`` comes from the stored
    ``upstream_complete`` array at the head's own cell, ``region_complete`` from the
    region record's status. Nothing is added to the algorithm bundle's schema -- this
    is a manifest diagnostic re-derived from the stored arrays at cold read.
    """
    from terrain_pipeline.surface_rivers.metric_highland_sources import (
        STATUS_REGION_COMPLETE)

    arrays = bundle["arrays"]
    complete = np.asarray(arrays["upstream_complete"], np.bool_)
    counts = np.asarray(arrays["known_upstream_cells"], np.int64)
    flags = np.asarray(arrays["head_flags"], np.bool_)
    metadata = bundle["metadata"]
    origin = [int(value) for value in metadata["origin_native_xz"]]
    rows_axis, columns = [int(value) for value in metadata["shape_zx"]]
    if complete.shape != (rows_axis, columns) or counts.shape != complete.shape:
        raise ValueError("head diagnostics: stored arrays do not share the window shape")
    regions = {item["region_id"]: item for item in bundle["regions"]}
    expected_flags = np.zeros(complete.shape, np.bool_)
    rows = []
    for head in bundle["heads"]:
        x, z = int(head["world_xz"][0]), int(head["world_xz"][1])
        row, column = z - origin[1], x - origin[0]
        if not (0 <= row < rows_axis and 0 <= column < columns):
            raise ValueError("head diagnostics: a head fell outside the stored window")
        expected_flags[row, column] = True
        if head["region_id"] not in regions:
            raise ValueError("head diagnostics: a head names a region that is not stored")
        region = regions[head["region_id"]]
        record = {
            "head_id": head["head_id"],
            "region_id": head["region_id"],
            "world_xz": [x, z],
            "known_upstream_cells": int(counts[row, column]),
            "own_upstream_complete": bool(complete[row, column]),
            "region_complete": region["status"] == STATUS_REGION_COMPLETE,
            "region_status": region["status"],
            "region_reason_codes": list(region["reason_codes"]),
            "head_status": head["status"],
            "head_reason_codes": list(head["reason_codes"]),
            "geometry_certified": bool(head["geometry_certified"]),
        }
        if int(head["known_upstream_cells"]) != record["known_upstream_cells"]:
            raise ValueError("head diagnostics: a head's stored contribution disagrees "
                             "with the stored contribution array")
        if record["geometry_certified"] != (record["own_upstream_complete"]
                                           and record["region_complete"]):
            raise ValueError("head diagnostics: certification is not the conjunction of "
                             "the head's own upstream and its region")
        rows.append(record)
    if not np.array_equal(flags, expected_flags):
        raise ValueError("head diagnostics: the stored head mask disagrees with the "
                         "head table")
    both = sum(1 for item in rows if item["own_upstream_complete"] and item["region_complete"])
    return {
        "schema": HEAD_DIAGNOSTICS_SCHEMA,
        "counts": {
            "heads": len(rows),
            "own_upstream_complete": sum(1 for item in rows
                                         if item["own_upstream_complete"]),
            "own_upstream_incomplete": sum(1 for item in rows
                                           if not item["own_upstream_complete"]),
            "region_complete": sum(1 for item in rows if item["region_complete"]),
            "region_pending": sum(1 for item in rows if not item["region_complete"]),
            "both_conditions": both,
            "geometry_certified": sum(1 for item in rows if item["geometry_certified"]),
        },
        "statement": ("own_upstream_complete (strict-D8 upstream of this head) and "
                      "region_complete (status of the patch it sits in) are the two "
                      "conjuncts of certification and are reported separately, never "
                      "merged; a pending region does not mean a pending own upstream"),
        "rows": rows,
    }


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


# --------------------------------------------------------------------------- #
# 1. declared support and the source request (no array exists yet)
# --------------------------------------------------------------------------- #
def declared_support(name):
    if name not in DECLARED_SUPPORTS:
        raise ValueError("unknown declared support %r; this tool prepares only %s"
                         % (name, sorted(DECLARED_SUPPORTS)))
    entry = DECLARED_SUPPORTS[name]
    origin = tuple(int(value) for value in entry["origin_native_xz"])
    shape = tuple(int(value) for value in entry["shape_zx"])
    cells = int(shape[0]) * int(shape[1])
    if min(shape) < 2:
        raise ValueError("support %s is %s, below the declared 2x2 minimum"
                         % (name, list(shape)))
    if cells > MAX_SUPPORT_CELLS:
        raise ValueError("support %s is %dx%d = %d cells, above the declared ceiling %d"
                         % (name, shape[0], shape[1], cells, MAX_SUPPORT_CELLS))
    return origin, shape, entry


def read_request(path, expected_sha256):
    """Strict, byte-limited read of a pinned source request; the pin is mandatory."""
    target = Path(path)
    if not target.is_file():
        raise ValueError("source request not found: %s" % target)
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("a 64-character external sha256 pin of the source request is "
                         "required; an unpinned request is not read")
    size = target.stat().st_size
    if size > MAX_REQUEST_BYTES:
        raise ValueError("source request is %d bytes, above the declared %d"
                         % (size, MAX_REQUEST_BYTES))
    if file_sha256(target) != expected_sha256:
        raise ValueError("source request pin mismatch: %s is not %s"
                         % (target, expected_sha256))
    request = json.loads(target.read_text(encoding="utf-8"),
                         parse_constant=_reject_constant, object_pairs_hook=_unique_pairs)
    if not isinstance(request, dict):
        raise ValueError("a source request is a JSON object")
    records = request.get("source_records")
    if not isinstance(records, list) or not records:
        raise ValueError("a source request carries a non-empty source_records list")
    cleaned = []
    seen = set()
    for item in records:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("a source record is exactly {path, sha256}")
        page, sha = item["path"], item["sha256"]
        if not isinstance(page, str) or not page:
            raise ValueError("a source record has no path")
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError("source record %r carries no 64-character sha256" % page)
        if page in seen:
            raise ValueError("duplicate source record %r: a page is pinned once" % page)
        seen.add(page)
        cleaned.append({"path": page, "sha256": sha})
    seed = request.get("world_seed")
    if seed is not None and int(seed) != WORLD_SEED:
        raise ValueError("source request world_seed %r contradicts the frozen seed %d"
                         % (seed, WORLD_SEED))
    return cleaned, target, file_sha256(target)


def page_paths(records):
    """Resolve the pinned page paths, relative paths read against the project root."""
    resolved = []
    for record in records:
        page = Path(record["path"])
        if not page.is_absolute():
            page = ROOT / page
        if not page.is_file():
            raise ValueError("pinned page missing: %s" % page)
        resolved.append((record, page))
    return resolved


def inspect_page_headers(records):
    """ZIP/NPY header gate: member set, dtype, order and byte count, no allocation.

    A page is exactly ``elevation_native`` (2-D ``<f8``, C order) plus
    ``metadata_json`` (0-d ``U``). The declared payload byte count is checked against
    the bytes the ZIP reports, so a header cannot claim a different extent or dtype
    than the member holds.
    """
    total = 0
    total_payload = 0
    headers = {}
    all_headers = {}
    for record, page in page_paths(records):
        size = page.stat().st_size
        if size > MAX_PAGE_BYTES:
            raise ValueError("page %s is %d bytes, above the declared %d"
                             % (page.name, size, MAX_PAGE_BYTES))
        total += size
        with open(page, "rb") as stream:
            import zipfile
            with zipfile.ZipFile(stream) as archive:
                members = archive.infolist()
                if not 1 <= len(members) <= MAX_PAGE_MEMBERS:
                    raise ValueError("page %s carries %d members, above the declared %d"
                                     % (page.name, len(members), MAX_PAGE_MEMBERS))
                names = {member.filename for member in members}
                if len(names) != len(members):
                    raise ValueError("page %s has duplicate member names" % page.name)
                if names != {"elevation_native.npy", "metadata_json.npy"}:
                    raise ValueError("page %s carries %s; a page is exactly elevation_native "
                                     "and metadata_json" % (page.name, sorted(names)))
                for member in members:
                    with archive.open(member) as entry:
                        version = np.lib.format.read_magic(entry)
                        if version == (1, 0):
                            shape, fortran, dtype = np.lib.format.read_array_header_1_0(
                                entry, max_header_size=MAX_HEADER_BYTES)
                        elif version == (2, 0):
                            shape, fortran, dtype = np.lib.format.read_array_header_2_0(
                                entry, max_header_size=MAX_HEADER_BYTES)
                        else:
                            raise ValueError("page %s carries an unsupported NPY version"
                                             % page.name)
                        used = entry.tell()
                    if dtype.hasobject:
                        raise ValueError("page %s member %s is an object array"
                                         % (page.name, member.filename))
                    if fortran:
                        raise ValueError("page %s member %s is Fortran-ordered"
                                         % (page.name, member.filename))
                    payload = math.prod(shape) * int(dtype.itemsize)
                    total_payload += payload
                    if total_payload > MAX_TOTAL_PAGE_BYTES:
                        raise ValueError('decompressed page payload budget exceeded')
                    if payload + used != member.file_size:
                        raise ValueError("page %s member %s declares %d bytes but the "
                                         "archive holds %d"
                                         % (page.name, member.filename,
                                            payload + used, member.file_size))
                    headers[member.filename[:-4]] = {
                        "shape": [int(value) for value in shape],
                        "dtype": dtype.str, "nbytes": payload,
                        "kind": dtype.kind}
        elevation = headers["elevation_native"]
        if len(elevation["shape"]) != 2:
            raise ValueError("page %s elevation is not 2-D" % page.name)
        if elevation["shape"][0] != elevation["shape"][1]:
            raise ValueError("page %s elevation is %s, a native page is square"
                             % (page.name, elevation["shape"]))
        if elevation["dtype"] != "<f8":
            raise ValueError("page %s elevation dtype is %s, not <f8"
                             % (page.name, elevation["dtype"]))
        if headers["metadata_json"]["kind"] != "U":
            raise ValueError("page %s metadata_json is %s, not a Unicode array"
                             % (page.name, headers["metadata_json"]["dtype"]))
        if not 2 <= elevation['shape'][0] <= MAX_PAGE_SIDE:
            raise ValueError("page %s elevation side %d is outside the declared 2..%d "
                             "budget" % (page.name, elevation['shape'][0], MAX_PAGE_SIDE))
        # metadata_json is a 0-d Unicode scalar: its extent must be empty and its byte
        # count is the string length, so it is gated as a length, never as a raw payload.
        metadata = headers['metadata_json']
        if metadata['shape'] != []:
            raise ValueError("page %s metadata_json is %s, not a 0-d scalar"
                             % (page.name, metadata['shape']))
        if not metadata['dtype'].startswith('<U') or metadata['kind'] != 'U':
            raise ValueError("page %s metadata_json dtype is %s, not a little-endian "
                             "Unicode scalar" % (page.name, metadata['dtype']))
        if metadata['nbytes'] > MAX_REQUEST_BYTES:
            raise ValueError("page %s metadata_json carries %d bytes, above the declared %d"
                             % (page.name, metadata['nbytes'], MAX_REQUEST_BYTES))
        all_headers[record['path']] = dict(headers)
    if total > MAX_TOTAL_PAGE_BYTES:
        raise ValueError("the pinned pages hold %d bytes, above the declared %d"
                         % (total, MAX_TOTAL_PAGE_BYTES))
    return all_headers, total


# --------------------------------------------------------------------------- #
# 2. build and validate (the only place the producer is imported)
# --------------------------------------------------------------------------- #
def build_bundle(records, *, origin, shape):
    """Load the pinned window and build the geometry bundle. No GPU, no generation."""
    from terrain_pipeline.surface_rivers import metric_highland_sources as highland
    from terrain_pipeline.surface_rivers.native_30m_source import load_native_window

    cells = int(shape[0]) * int(shape[1])
    if cells > highland.DEFAULT_MAX_CELLS:
        raise ValueError("support %d cells exceeds the module's declared budget %d"
                         % (cells, highland.DEFAULT_MAX_CELLS))
    source = load_native_window(records, origin_native_xz=[int(origin[0]), int(origin[1])],
                                shape_zx=[int(shape[0]), int(shape[1])],
                                world_seed=WORLD_SEED, max_cells=MAX_SUPPORT_CELLS)
    window = {
        "field": source["field"],
        "resolved_mask": source["resolved_mask"],
        "origin_native_xz": list(source["origin_native_xz"]),
        "shape_zx": list(source["shape_zx"]),
        "world_seed": int(source["world_seed"]),
        "spacing_m": float(source["spacing_m"]),
        "assembly_digest": source.get("assembly_digest"),
        "source_records": list(source.get("source_records", [])),
    }
    bundle = highland.build_highland_sources(window, max_cells=cells)
    return bundle, window, source


def check_unresolved_pattern(window):
    """The original unknown pattern must survive: NaN exactly on unresolved cells.

    Stated as an explicit gate rather than assumed, because a filled hole or a zero
    fill would still be numerically plausible and would silently turn a pending region
    into a complete one.
    """
    field = np.asarray(window["field"])
    mask = np.asarray(window["resolved_mask"])
    if field.dtype != np.float64 or mask.dtype != np.bool_ or field.shape != mask.shape:
        raise ValueError("the assembled window is not a float64 field with a bool mask")
    if not np.array_equal(np.isnan(field), ~mask):
        raise ValueError("the assembled window does not keep NaN exactly on the "
                         "unresolved cells; a filled unknown would be a fabricated "
                         "surface")
    if not np.isfinite(field[mask]).all():
        raise ValueError("a resolved cell carries a non-finite elevation")
    if not mask.any():
        raise ValueError("no resolved cell: an all-unknown window is not a source region")
    return {
        "support_cells": int(field.size),
        "resolved_cells": int(mask.sum()),
        "unresolved_cells": int((~mask).sum()),
        "unknown_kept_as_nan": True,
    }


def validate_bundle(bundle):
    """Full validation: the strict D8, counts, completeness and heads are rebuilt."""
    from terrain_pipeline.surface_rivers import metric_highland_sources as highland

    report = highland.validate_highland_sources(bundle)
    if report.get("head_table_rederived") is not True:
        raise ValueError("the validator did not re-derive the head table; this bundle is "
                         "not accepted")
    return report


# --------------------------------------------------------------------------- #
# 3. write the package (exclusive creation, no partial product)
# --------------------------------------------------------------------------- #
def write_package(output, *, support_name, origin, shape, entry, request_path,
                  request_sha, records, page_bytes, headers, window, source, bundle,
                  validation, timing, code=None, rss_samples=None,
                  request_sha_after=None):
    destination = Path(output)
    if os.path.lexists(destination):
        raise ValueError("output already exists: %s (this tool never overwrites a "
                         "saved package)" % destination)
    destination.mkdir(parents=True, exist_ok=False)
    # ``write_package`` is called directly by tests as well, so it owns its own cleanup:
    # a failure anywhere below removes **this call's** directory and nothing else. A
    # half-written directory that merely lacks its manifest would be indistinguishable
    # from a package on disk, so there is no such state left behind.
    try:
        return _write_package_files(destination, support_name=support_name, origin=origin,
                                    shape=shape, entry=entry, request_path=request_path,
                                    request_sha=request_sha, records=records,
                                    page_bytes=page_bytes, headers=headers, window=window,
                                    source=source, bundle=bundle, validation=validation,
                                    timing=timing, code=code, rss_samples=rss_samples,
                                    request_sha_after=request_sha_after)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _write_package_files(destination, *, support_name, origin, shape, entry, request_path,
                         request_sha, records, page_bytes, headers, window, source, bundle,
                         validation, timing, code, rss_samples, request_sha_after):
    """The body of a package write; the caller owns the exclusive directory."""
    arrays = bundle["arrays"]
    npz_path = destination / ARRAYS_NAME
    with open(npz_path, "xb") as stream:
        np.savez(stream, **{name: np.ascontiguousarray(arrays[name])
                            for name in sorted(arrays)})
    array_records = {
        name: {"shape": list(arrays[name].shape), "dtype": arrays[name].dtype.str,
               "sha256": array_sha256(arrays[name])}
        for name in sorted(arrays)
    }
    metadata = bundle["metadata"]
    diagnostics = head_diagnostics(bundle)
    manifest = {
        "schema": SCHEMA,
        "bundle": {key: value for key, value in bundle.items() if key != 'arrays'},
        "bundle_schema": bundle["schema"],
        "support": {
            "name": support_name,
            "role": entry["role"],
            "holdout": bool(entry["holdout"]),
            "note": entry["note"],
            "origin_native_xz": list(origin),
            "shape_zx": list(shape),
            "support_cells": int(shape[0]) * int(shape[1]),
            "world_seed": WORLD_SEED,
            "spacing_m": SPACING_M,
            "storage_representation": "signed_int64_native_cells",
            "role_statement": ("development_recheck and consistency_control are NOT "
                               "hold-outs: E extends a direction that was already "
                               "explored and V re-reads almost the same ground, so "
                               "agreement between them is a support-consistency check "
                               "and never an independent confirmation"),
        },
        "rule": {
            "rule_version": metadata["rule_version"],
            "logical_version": metadata["logical_version"],
            "parameters": metadata["parameters"],
            "parameters_sha256": metadata["parameters_sha256"],
            "calibration": metadata["calibration"],
            "geometry": metadata["geometry"],
        },
        "stage": {
            "status": metadata["status"],
            "rainfall_supported": metadata["rainfall_supported"],
            "perennial_flow_certified": metadata["perennial_flow_certified"],
            "water_budget": metadata["water_budget"],
            "mainstem_generated": metadata["mainstem_generated"],
            "statement": ("geometry candidates only: a region or a head is not water, "
                          "not a discharge and not a perennial river"),
        },
        "source": {
            "request_path": str(request_path),
            "request_sha256": request_sha,
            "request_sha256_after_run": request_sha_after,
            "page_records": records,
            "page_npz_bytes": int(page_bytes),
            "page_headers": headers,
            "assembly_digest": source.get("assembly_digest"),
            "loader_source_records": source.get("source_records"),
            "unresolved": {
                "resolved_cells": int(source["resolved_cells"]),
                "unresolved_cells": int(source["unresolved_cells"]),
                "unresolved_reason": source.get("unresolved_reason"),
                "border_band_cells": source.get("border_band_cells"),
            },
            "field_mask_sha256": metadata["source"]["field_mask_sha256"],
            "binding": ("the page sha256 list and the assembly digest are content "
                        "bindings recorded here; they are not signatures"),
        },
        "counts": {
            "regions": len(bundle["regions"]),
            "regions_complete": sum(1 for item in bundle["regions"]
                                    if item["status"] == "region_candidate_complete"),
            "regions_pending": sum(1 for item in bundle["regions"]
                                   if item["status"] == "region_candidate_pending"),
            "regions_below_area": sum(1 for item in bundle["regions"]
                                      if item["status"] == "region_below_area"),
            "heads": len(bundle["heads"]),
            "heads_certified": metadata["certified_world_heads"],
            "head_census": metadata["head_census"],
            "region_census": metadata["region_census"],
        },
        "identity": {
            "bundle_identity_sha256": bundle["identity_sha256"],
            "region_ids": [item["region_id"] for item in bundle["regions"]],
            "region_source_identity_sha256": [item["source_identity_sha256"]
                                              for item in bundle["regions"]],
            "head_ids": [item["head_id"] for item in bundle["heads"]],
        },
        "arrays": array_records,
        "validation": {
            "schema": validation["schema"],
            "head_table_rederived": validation["head_table_rederived"],
            "regions_rederived": validation["regions_rederived"],
            "heads_stored": validation["heads_stored"],
            "routing_origin": validation["routing_origin"],
            "head_census_independent": validation["head_census_independent"],
            "note": ("the validator rebuilt the strict D8, the contribution, the "
                     "completeness, the region members and the head table from the "
                     "stored field and mask; it is not a re-hash of the bundle"),
        },
        "head_diagnostics": diagnostics,
        "code": code if code is not None else code_digests(),
        "resources": {
            "rss_metric": RSS_METRIC,
            "samples": list(rss_samples or []),
            "statement": ("current RSS sampled at named stages, not a peak and not a "
                          "continuous monitor; an absent sample is absent, and a "
                          "payload estimate is not a memory limit"),
        },
        "timing": timing,
        "scope": ("one declared support of the fixed 30 m world; not a regional or global "
                  "highland distribution and not a supply certification"),
    }
    (destination / MANIFEST_NAME).write_text(_stable_json(manifest) + "\n", encoding="utf-8")
    (destination / VALIDATION_NAME).write_text(_stable_json(validation) + "\n",
                                               encoding="utf-8")
    return manifest, npz_path


# --------------------------------------------------------------------------- #
# 4. the run
# --------------------------------------------------------------------------- #
def run(output, *, support, source_request, request_sha256):
    started = time.monotonic()
    if os.path.lexists(output):
        raise ValueError('output already exists: %s' % output)
    origin, shape, entry = declared_support(support)
    records, request_path, request_sha = read_request(source_request, request_sha256)
    samples = []
    rss_sample(samples, "after_request_read", started)
    headers, page_bytes = inspect_page_headers(records)
    rss_sample(samples, "after_header_gate", started)
    before = {record["path"]: file_sha256(page) for record, page in page_paths(records)}

    bundle, window, source = build_bundle(records, origin=origin, shape=shape)
    rss_sample(samples, "after_build", started)
    unresolved = check_unresolved_pattern(window)
    validation = validate_bundle(bundle)
    rss_sample(samples, "after_full_validation", started)

    after = {record["path"]: file_sha256(page) for record, page in page_paths(records)}
    request_sha_after = file_sha256(request_path)
    if before != after:
        raise ValueError("a pinned page changed during the run: the package would describe "
                         "a source that no longer exists")
    if request_sha_after != request_sha:
        raise ValueError("the source request changed during the run")
    for record in records:
        if before[record["path"]] != record["sha256"]:
            raise ValueError("page %r does not match its pin" % record["path"])
    code = code_digests()
    rss_sample(samples, "after_input_rehash", started)

    timing = {
        "clock": "time.monotonic",
        "elapsed_s": time.monotonic() - started,
        "hard_stop_s": None,
        "note": ("the command is run under an external 60 s wall budget; this number is "
                 "the tool's own observation, not a limit"),
    }
    manifest, npz_path = publish_package(
        output, support_name=support, origin=origin, shape=shape, entry=entry,
        request_path=request_path, request_sha=request_sha, records=records,
        page_bytes=page_bytes, headers=headers, window=window, source=source,
        bundle=bundle, validation=validation, timing=timing,
        code=code, rss_samples=samples, request_sha_after=request_sha_after)
    return {
        "schema": SCHEMA,
        "support": support,
        "output": str(Path(output)),
        "arrays_npz": str(npz_path),
        "arrays_npz_sha256": file_sha256(npz_path),
        "unresolved": unresolved,
        "regions": manifest["counts"]["regions"],
        "heads": manifest["counts"]["heads"],
        "heads_certified": manifest["counts"]["heads_certified"],
        "bundle_identity_sha256": manifest["identity"]["bundle_identity_sha256"],
        "validation_head_table_rederived": validation["head_table_rederived"],
        "head_diagnostics": manifest["head_diagnostics"]["counts"],
        "rss_metric": RSS_METRIC,
        "elapsed_s": timing["elapsed_s"],
    }


def read_package(directory):
    """Cold-read arrays only after bounded JSON and NPY header checks.

    Two manifest generations are accepted, and they are **not** the same claim:

    * ``SCHEMA`` (v2) additionally requires the head diagnostic table, the code digests
      and the named RSS samples, and re-derives the diagnostic table from the stored
      arrays;
    * ``LEGACY_SCHEMAS`` (v1) has none of those blocks, so they are neither required nor
      invented -- an old package is checked by exactly the checks it could have passed.
      Refusing to read it, or silently fabricating an empty diagnostic table for it,
      would be worse than saying "this package predates those claims".

    Everything that both generations carry is checked identically, so the numeric gates
    did not become generation-dependent.
    """
    from tools.review_world_reaches import read_strict_json, inspect_archive, load_arrays
    root = Path(directory)
    manifest = read_strict_json(root / MANIFEST_NAME)
    schema = manifest.get('schema')
    if schema != SCHEMA and schema not in LEGACY_SCHEMAS:
        raise ValueError('package schema mismatch')
    legacy = schema != SCHEMA
    support = manifest['support']
    origin, shape, entry = declared_support(support['name'])
    if (support['origin_native_xz'] != list(origin)
            or support['shape_zx'] != list(shape)
            or support['world_seed'] != WORLD_SEED or support['spacing_m'] != SPACING_M):
        raise ValueError('package support mismatch')
    headers = inspect_archive(root / ARRAYS_NAME)
    records = manifest['arrays']
    if set(headers) != set(records):
        raise ValueError('package array names mismatch')
    cells = math.prod(shape)
    for name, header in headers.items():
        record = records[name]
        if list(header['shape']) != record['shape'] or header['dtype'] != record['dtype']:
            raise ValueError('package array header mismatch: ' + name)
        if math.prod(header['shape']) > cells * 4:
            raise ValueError('package array extent budget: ' + name)
    arrays = load_arrays(root / ARRAYS_NAME, sorted(records))
    for name, value in arrays.items():
        if array_sha256(value) != records[name]['sha256']:
            raise ValueError('package array digest mismatch: ' + name)
    bundle = dict(manifest['bundle'])
    bundle['arrays'] = arrays
    metadata = bundle['metadata']
    if (metadata['origin_native_xz'] != list(origin)
            or metadata['shape_zx'] != list(shape)
            or metadata['world_seed'] != WORLD_SEED or metadata['spacing_m'] != SPACING_M):
        raise ValueError('package bundle support mismatch')
    report = validate_bundle(bundle)
    expected_counts = {
        'regions': len(bundle['regions']),
        'regions_complete': sum(r['status'] == 'region_candidate_complete' for r in bundle['regions']),
        'regions_pending': sum(r['status'] == 'region_candidate_pending' for r in bundle['regions']),
        'regions_below_area': sum(r['status'] == 'region_below_area' for r in bundle['regions']),
        'heads': len(bundle['heads']), 'heads_certified': metadata['certified_world_heads'],
        'head_census': metadata['head_census'], 'region_census': metadata['region_census']}
    if manifest.get('counts') != expected_counts:
        raise ValueError('package counts mismatch')
    for key in ('rule_version', 'logical_version', 'parameters', 'parameters_sha256',
                'calibration', 'geometry'):
        if manifest.get('rule', {}).get(key) != metadata[key]:
            raise ValueError('package rule mismatch: ' + key)
    for key in ('status', 'rainfall_supported', 'perennial_flow_certified',
                'water_budget', 'mainstem_generated'):
        if manifest.get('stage', {}).get(key) != metadata[key]:
            raise ValueError('package stage mismatch: ' + key)
    expected_identity = {
        'bundle_identity_sha256': bundle['identity_sha256'],
        'region_ids': [r['region_id'] for r in bundle['regions']],
        'region_source_identity_sha256': [r['source_identity_sha256'] for r in bundle['regions']],
        'head_ids': [h['head_id'] for h in bundle['heads']]}
    if manifest.get('identity') != expected_identity:
        raise ValueError('package identity mismatch')
    if (support.get('support_cells') != cells or support.get('role') != entry['role']
            or (not legacy and support.get('holdout') is not bool(entry['holdout']))
            or support.get('storage_representation') != 'signed_int64_native_cells'):
        raise ValueError('package support declaration mismatch')
    if manifest.get('bundle_schema') != bundle['schema']:
        raise ValueError('package bundle schema mismatch')
    if manifest.get('source', {}).get('field_mask_sha256') != metadata['source']['field_mask_sha256']:
        raise ValueError('package source content mismatch')
    for key in ('schema', 'head_table_rederived', 'regions_rederived', 'heads_stored',
                'routing_origin', 'head_census_independent'):
        if manifest.get('validation', {}).get(key) != report[key]:
            raise ValueError('package validation declaration mismatch: ' + key)
    if not legacy:
        expected_diagnostics = head_diagnostics(bundle)
        if manifest.get('head_diagnostics') != expected_diagnostics:
            raise ValueError('package head diagnostics mismatch')
        resources = manifest.get('resources')
        if not isinstance(resources, dict) or resources.get('rss_metric') != RSS_METRIC:
            raise ValueError('package resource declaration mismatch')
        samples = resources.get('samples')
        if not isinstance(samples, list):
            raise ValueError('package resource samples mismatch')
        for position, sample in enumerate(samples):
            if not isinstance(sample, dict) or set(sample) != {
                    'stage', 'elapsed_s', 'current_rss_bytes'}:
                raise ValueError('package resource sample %d is not a named RSS sample'
                                 % position)
            if not isinstance(sample['stage'], str) or not sample['stage']:
                raise ValueError('package resource sample %d has no stage' % position)
            value = sample['current_rss_bytes']
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)
                                      or value <= 0):
                raise ValueError('package resource sample %d has an invalid RSS value'
                                 % position)
        code = manifest.get('code')
        if not isinstance(code, dict) or set(code) != {'files', 'statement'}:
            raise ValueError('package code declaration mismatch')
        if not isinstance(code.get('files'), dict) or not code['files']:
            raise ValueError('package code declaration carries no digests')
        for relative, digest in code['files'].items():
            if relative not in CODE_FILES:
                raise ValueError('package code declaration names an undeclared file: '
                                 + str(relative))
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError('package code declaration has no 64-character digest for '
                                 + str(relative))
        # Cross-binding: a digest duplicated elsewhere in the manifest must agree. These
        # are self-reports, not signatures, but two copies of one number that disagree
        # mean the manifest was edited after it was written.
        source_module = 'terrain_pipeline/surface_rivers/native_30m_source.py'
        stored_copies = {
            'code': code['files'].get(source_module),
            'bundle_dependency': metadata.get('dependency_source_sha256', {}).get(
                'terrain_pipeline.surface_rivers.native_30m_source'),
        }
        present = {key: value for key, value in stored_copies.items()
                   if value is not None}
        if len(set(present.values())) > 1:
            raise ValueError('package code declaration disagrees with the bundle '
                             'dependency digest: %s' % sorted(present))
        # The same input is recorded in **three separate places** -- the page list, the
        # loader's own records and the bundle metadata. None of those copies is a
        # signature, but they are repeated fields, and two copies of one input that
        # disagree mean the manifest was edited after it was written. Binding them is a
        # consistency gate, not a new trust anchor.
        #
        # Each copy is checked **on its own**, not merged: merging would let a deleted
        # copy pass whenever the other one still matched, which is exactly the edit this
        # gate exists to catch.
        source_block = manifest.get('source', {})
        before_pin = source_block.get('request_sha256')
        after_pin = source_block.get('request_sha256_after_run')
        for name, value in (('request_sha256', before_pin),
                            ('request_sha256_after_run', after_pin)):
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError('package source %s is not a 64-character digest' % name)
        if before_pin != after_pin:
            raise ValueError('package source request pin disagrees with the pin '
                             'recorded after the run')
        pinned = _page_table(source_block.get('page_records'),
                             'source.page_records')
        for label, records in (
                ('source.loader_source_records',
                 source_block.get('loader_source_records')),
                ('bundle.metadata.source.source_records',
                 metadata['source'].get('source_records'))):
            # Each copy stands on its own: required, non-empty and internally unique. Only
            # then is it compared with the page list, so a deleted copy cannot pass by
            # matching "nothing", and a copy with a duplicate path cannot hide behind the
            # other one.
            if _page_table(records, label) != pinned:
                raise ValueError('package %s disagrees with source.page_records; each '
                                 'copy of the page list is checked on its own, never '
                                 'merged' % label)
    return bundle, report


def _page_table(records, label):
    """One page list, validated on its own: required, non-empty, unique, 64-hex pins.

    Returns ``{path: sha256}``. A missing key, a repeated path, a digest that is not
    lowercase 64-hex and a ``None`` pin are all refusals -- a missing field must never
    compare equal to another missing field.
    """
    if not isinstance(records, list) or not records:
        raise ValueError('package %s is missing or empty' % label)
    table = {}
    for item in records:
        if not isinstance(item, dict):
            raise ValueError('package %s row is not a mapping' % label)
        path = item.get('path')
        digest = item.get('sha256')
        if not isinstance(path, str) or not path:
            raise ValueError('package %s row has no path' % label)
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError('package %s row %r has no 64-character digest' % (label, path))
        if any(character not in '0123456789abcdef' for character in digest):
            raise ValueError('package %s row %r carries a digest that is not '
                             'lowercase hex' % (label, path))
        if path in table:
            raise ValueError('package %s pins %r twice' % (label, path))
        table[path] = digest
    return table


def publish_package(output, **kwargs):
    """Windows no-clobber commit; remove only this call's private staging tree."""
    if os.name != 'nt':
        raise ValueError('atomic no-clobber publish certified for Windows only')
    destination = Path(output)
    if os.path.lexists(destination):
        raise ValueError('output already exists: %s' % destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + destination.name + '-partial-',
                                    dir=destination.parent))
    work = staging / 'package'
    try:
        manifest, _ = write_package(work, **kwargs)
        read_package(work)
        if os.path.lexists(destination):
            raise ValueError('output appeared during preparation')
        os.rename(work, destination)
        return manifest, destination / ARRAYS_NAME
    finally:
        shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--support", required=True, choices=sorted(DECLARED_SUPPORTS))
    parser.add_argument("--source-request", type=Path, required=True)
    parser.add_argument("--source-request-sha256", required=True)
    args = parser.parse_args(argv)
    result = run(args.output, support=args.support,
                 source_request=args.source_request,
                 request_sha256=args.source_request_sha256)
    print(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
