"""Cold-readable diagnostic network-discharge product and its consumer gate.

Scope of this module
--------------------
Wrap the frozen diagnostic accumulation
(``metric_network_accumulation.accumulate_network_discharge``) into one
self-describing, content-addressed package: the declared inputs (receiver, local
Q, validity, terminal kind, declared unknown upstream), the accumulated answers
(known routed Q, completeness, terminal Q), the water ledger and the
accumulation policy. This module adds no second accumulation: the only physics
it runs is that one call, at build time and again at cold load and at the
consumer gate.

What the product does not claim
-------------------------------
* ``complete_mask`` means only "no declared unknown upstream contributes". It is
  not a routing certificate: the receiver graph was handed in by the caller, so
  ``topology_window_invariance_verified`` is false by construction, and
  ``finite_graph_only`` states the same limit positively.
* Terminals stay exactly as declared by the caller. ``retained`` is never
  rewritten to ``open_outflow``, and no natural outlet is inferred from grid
  edges.
* No hydraulics, no storage, no physical-time integration, no real runoff:
  ``hydraulic_ready``, ``natural_outlet_certified`` and ``publishable`` are false
  and this API cannot set them true.

Why loading and the gate recompute
----------------------------------
Neither ``load_discharge_product`` nor ``require_complete_discharge`` trusts the
manifest digests: both re-run the frozen accumulation on the stored inputs and
compare the stored Q, completeness and terminal arrays plus the whole ledger and
counts. A package whose digests were re-sealed after editing any derived array,
any ledger entry or any count is therefore still refused.

What the checks prove, and what they cannot
-------------------------------------------
The digest carried in a manifest is an unkeyed content checksum, not a
signature: it proves only that the bytes read are the bytes described, and
anyone can recompute it. Recomputing verifies that the derived Q, masks, ledger
and counts agree with the *declared* inputs. It cannot certify that the declared
inputs themselves are true: rewriting the receiver, local Q, validity, the world
seed or the coordinate origin **and** re-sealing every digest yields a
different, internally consistent product with a new identity. That is a legal
new product, not a forgery this module could detect, and nothing here should be
read as authenticating provenance. Array shapes and dtypes are bound together by
the declared ``shape_zx``, the archive headers and the identity, so no separate
header digest is needed.

Coordinate origin and bounded reading
-------------------------------------
``origin_native_cells`` is a *signed* ``(x, z)`` pair — x first, matching the
source archives — even though every stored array is indexed ``[z, x]``. World
absolute coordinates have negative components, so both entries may be negative;
``shape_zx`` and ``world_seed`` stay non-negative. Before any array is allocated
the reader stats the manifest against its metadata byte budget (and refuses a
manifest that grows while it is being read) and passes a header gate into
``checked_archive``: all eight headers must share one shape equal to
``metadata.shape_zx`` and fit the same cell/byte/dimension budget the loaded
arrays are then held to. Text declarations carry a UTF-8 byte cap at the single
build/load entry point.
"""

import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, canonical_json, digest
from terrain_pipeline.common_infra import checked_archive, file_sha256, readonly
from terrain_pipeline.drainage import MAX_NETWORK_CELLS as MAX_NETWORK_CELLS
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge


__all__ = [
    "ARRAY_NAMES",
    "COMPLETE_DEFINITION",
    "COORDINATES",
    "FORMAT_VERSION",
    "IDENTITY_FIELDS",
    "LEDGER_NAMES",
    "MANIFEST_KEYS",
    "MAX_BYTES",
    "METADATA_KEYS",
    "PRODUCT_KEYS",
    "RECORD_FIELDS",
    "SCHEMA",
    "STATUS",
    "TERMINAL_LABELS",
    "build_discharge_product",
    "load_discharge_product",
    "require_complete_discharge",
    "save_discharge_product",
]


SCHEMA = "metric-network-discharge-product-v1"
FORMAT_VERSION = 1
STATUS = "diagnostic_not_publishable"
ALGORITHM = "diagnostic-network-discharge-accumulation"
ALGORITHM_VERSION = "v1"
MANIFEST_FILE = "manifest.json"
ARRAYS_FILE = "arrays.npz"
# The cell budget allows 16,777,216 cells; the eight canonical dtypes cost 131
# bytes per cell uncompressed (8+8+1+96+1+8+1+8), so a legal package can reach
# about 2.05 GiB of payload inside this hard byte ceiling.
MAX_BYTES = 3 * 1024 * 1024 * 1024
# NPY headers refuse a single dimension beyond this, so a product must never be
# built in a shape the cold reader would then reject.
MAX_DIMENSION = 8_000_000
MAX_METADATA_BYTES = 1_048_576
# Free-text declarations are capped in UTF-8 bytes at the one build/load entry
# point, so a manifest cannot carry an arbitrarily large declaration.
MAX_TEXT_BYTES = 65_536
TERMINAL_KIND_DTYPE = np.dtype("U24")
TERMINAL_LABELS = ("inactive", "interior", "retained", "open_outflow", "unknown_boundary")
COMPLETE_DEFINITION = (
    "complete_mask marks only that no declared unknown upstream contributes; "
    "it certifies neither the receiver topology nor a natural outlet, "
    "and it is not real runoff")
COORDINATES = (
    "arrays are [z,x] over Terrain Diffusion native 30 m cells; "
    "cell_id = z * nx + x; origin_native_cells is a signed (x,z) pair in native "
    "cells from the world origin, x first, and both entries may be negative")

ARRAY_NAMES = ("receiver", "local_q_m3_s", "valid_mask", "terminal_kind",
               "upstream_unknown_mask", "known_routed_q_m3_s", "complete_mask",
               "terminal_q_m3_s")
ARRAY_DTYPES = {
    "receiver": np.dtype(np.int64),
    "local_q_m3_s": np.dtype(np.float64),
    "valid_mask": np.dtype(np.bool_),
    "terminal_kind": TERMINAL_KIND_DTYPE,
    "upstream_unknown_mask": np.dtype(np.bool_),
    "known_routed_q_m3_s": np.dtype(np.float64),
    "complete_mask": np.dtype(np.bool_),
    "terminal_q_m3_s": np.dtype(np.float64),
}
LEDGER_NAMES = ("input_total_m3_s", "open_outflow_m3_s", "retained_m3_s",
                "unknown_pending_m3_s", "residual_m3_s", "valid_cells", "processed_cells")
COUNT_NAMES = ("valid_cells", "incomplete_valid_cells", "unknown_upstream_seed_cells")
METADATA_KEYS = ("schema", "algorithm", "algorithm_version", "status", "coordinates",
                 "origin_native_cells", "shape_zx", "spacing_m", "world_seed",
                 "interval_seconds", "source_sha256", "forcing_semantics", "policy",
                 "ledger", "counts", "complete_definition", "finite_graph_only",
                 "topology_window_invariance_verified", "natural_outlet_certified",
                 "hydraulic_ready", "publishable")
# The content identity binds schema, metadata and every array digest, so it can be
# computed identically at build time and at cold load. The array file digest is
# carried and verified separately: it can only exist after the file is written.
IDENTITY_FIELDS = ("format_version", "schema", "status", "metadata", "array_sha256")
RECORD_FIELDS = IDENTITY_FIELDS + ("identity_sha256",)
PRODUCT_KEYS = RECORD_FIELDS + ("arrays",)
MANIFEST_KEYS = RECORD_FIELDS + ("arrays_file", "arrays_file_sha256")


def _sha256_text(value, label):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError(label + " must be 64 lowercase hexadecimal characters")
    return value


def _integer(value, label, minimum=0):
    """An integer; ``minimum=None`` accepts signed values (world coordinates)."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(label + " must be an integer")
    number = int(value)
    if minimum is not None and number < minimum:
        raise ValueError(label + " must be at least " + str(minimum))
    return number


def _finite_float(value, label):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        raise ValueError(label + " must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(label + " must be finite")
    return number


def _positive_float(value, label):
    number = _finite_float(value, label)
    if number <= 0.:
        raise ValueError(label + " must be positive")
    return number


def _nonempty_text(value, label, max_bytes=None):
    """Nonempty text whose UTF-8 encoding fits the declaration byte budget."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be nonempty text")
    limit = MAX_TEXT_BYTES if max_bytes is None else max_bytes
    text = value.strip()
    if len(text.encode("utf-8")) > limit:
        raise ValueError(label + " exceeds " + str(limit) + " UTF-8 bytes")
    return text


def _pair_of_integers(value, label, minimum=0):
    """Two integers; ``minimum=None`` allows signed world-coordinate origins."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(label + " must be two integers")
    return [_integer(item, label, minimum) for item in value]


def _interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("interval_seconds must be a start and an end in physical seconds")
    start = _finite_float(value[0], "interval_seconds start")
    end = _finite_float(value[1], "interval_seconds end")
    if not start < end:
        raise ValueError("interval_seconds must increase")
    return [start, end]


def _origin(value):
    """Signed (x, z) native-cell origin, x first; arrays themselves stay [z, x]."""
    origin = _pair_of_integers(value, "origin_native_cells", minimum=None)
    return [origin[0], origin[1]]


def _shape_zx(value):
    shape = _pair_of_integers(value, "shape_zx", minimum=1)
    return (shape[0], shape[1])


def _grid_budget(shape):
    """Refuse a declared [z, x] grid the cold reader could not hold, before allocation."""
    rows = int(shape[0])
    columns = int(shape[1])
    if rows < 1 or columns < 1:
        raise ValueError("stored grid dimensions must be positive")
    if rows > MAX_DIMENSION or columns > MAX_DIMENSION:
        raise ValueError("stored grid dimension exceeds the readable NPY header limit")
    cells = rows * columns
    if cells > MAX_NETWORK_CELLS:
        raise ValueError("stored grid exceeds the diagnostic cell budget")
    payload_bytes = cells * sum(ARRAY_DTYPES[name].itemsize for name in ARRAY_NAMES)
    if payload_bytes > MAX_BYTES:
        raise ValueError("stored arrays exceed the package byte budget")
    return cells


def _identity(record):
    return digest({name: record.get(name) for name in IDENTITY_FIELDS})


def _pairs_without_duplicates(pairs):
    parsed = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError("duplicate manifest key: " + str(key))
        parsed[key] = value
    return parsed


def _reject_constant(value):
    raise ValueError("nonfinite manifest constant: " + str(value))


def _parse_manifest(payload):
    if not isinstance(payload, (bytes, bytearray)) or not 1 <= len(payload) <= MAX_METADATA_BYTES:
        raise ValueError("manifest must be nonempty bounded JSON bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("manifest must be UTF-8") from None
    try:
        return json.loads(text, object_pairs_hook=_pairs_without_duplicates,
                          parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise ValueError("invalid manifest JSON: " + str(error)) from None


def _validate_metadata(metadata):
    if not isinstance(metadata, dict) or set(metadata) != set(METADATA_KEYS):
        raise ValueError("invalid discharge product metadata fields")
    if (metadata["schema"] != SCHEMA or metadata["algorithm"] != ALGORITHM
            or metadata["algorithm_version"] != ALGORITHM_VERSION
            or metadata["status"] != STATUS or metadata["coordinates"] != COORDINATES
            or metadata["complete_definition"] != COMPLETE_DEFINITION):
        raise ValueError("unexpected discharge product schema, algorithm or declaration")
    if (metadata["finite_graph_only"] is not True
            or metadata["topology_window_invariance_verified"] is not False
            or metadata["natural_outlet_certified"] is not False
            or metadata["hydraulic_ready"] is not False
            or metadata["publishable"] is not False):
        raise ValueError("a diagnostic discharge product may not claim routing, "
                         "hydraulics, natural outlets or publication")
    _origin(metadata["origin_native_cells"])
    _shape_zx(metadata["shape_zx"])
    _positive_float(metadata["spacing_m"], "spacing_m")
    _integer(metadata["world_seed"], "world_seed")
    _interval(metadata["interval_seconds"])
    _sha256_text(metadata["source_sha256"], "source_sha256")
    _nonempty_text(metadata["forcing_semantics"], "forcing_semantics")
    if not isinstance(metadata["policy"], str) or not metadata["policy"].strip():
        raise ValueError("accumulation policy declaration required")
    ledger = metadata["ledger"]
    if not isinstance(ledger, dict) or set(ledger) != set(LEDGER_NAMES):
        raise ValueError("invalid discharge ledger fields")
    for name in ("valid_cells", "processed_cells"):
        if type(ledger[name]) is not int or ledger[name] < 0:
            raise ValueError("invalid ledger count: " + name)
    for name in LEDGER_NAMES:
        if name in ("valid_cells", "processed_cells"):
            continue
        value = ledger[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise ValueError("invalid ledger value: " + name)
    counts = metadata["counts"]
    if (not isinstance(counts, dict) or set(counts) != set(COUNT_NAMES)
            or any(type(value) is not int or value < 0 for value in counts.values())):
        raise ValueError("invalid discharge counts")
    return metadata


def _validate_arrays(arrays, shape_zx):
    if not isinstance(arrays, dict) or set(arrays) != set(ARRAY_NAMES):
        raise ValueError("invalid discharge product array set")
    shape = _shape_zx(shape_zx)
    for name in ARRAY_NAMES:
        value = arrays[name]
        if (not isinstance(value, np.ndarray) or value.dtype != ARRAY_DTYPES[name]
                or value.shape != shape):
            raise ValueError("invalid stored array: " + name)
    _grid_budget(shape)
    valid = arrays["valid_mask"]
    kinds = arrays["terminal_kind"]
    if not np.isin(kinds, TERMINAL_LABELS).all():
        raise ValueError("stored terminal_kind carries an undeclared destination")
    local = arrays["local_q_m3_s"]
    if not np.isfinite(local).all() or np.any(local < 0):
        raise ValueError("stored local Q must be finite and nonnegative")
    if np.any(local[~valid] != 0) or np.any(arrays["receiver"][~valid] != -1):
        raise ValueError("stored inactive cells must carry zero local Q and receiver -1")
    if np.any(arrays["upstream_unknown_mask"][~valid]):
        raise ValueError("stored inactive cells cannot seed unknown upstream")
    known = arrays["known_routed_q_m3_s"]
    if not np.isfinite(known).all() or np.any(known < 0):
        raise ValueError("stored known routed Q must be finite and nonnegative")
    if np.any(known[~valid] != 0):
        raise ValueError("stored inactive cells must carry zero routed Q")
    complete = arrays["complete_mask"]
    if np.any(complete & ~valid):
        raise ValueError("stored completeness cannot mark invalid cells")
    terminal_q = arrays["terminal_q_m3_s"]
    if not np.isfinite(terminal_q).all() or np.any(terminal_q < 0):
        raise ValueError("stored terminal Q must be finite and nonnegative")
    interior = valid & (arrays["receiver"] >= 0)
    if np.any(terminal_q[interior] != 0):
        raise ValueError("stored terminal Q must be zero at nonterminal cells")


def _validate_headers(headers, shape_zx):
    """Reject unsafe archives from headers alone, before any array is allocated.

    Every stored header must carry the canonical dtype of its name, be a genuine
    two-dimensional [z, x] array and share one shape: the same shape the manifest
    declares. That shared shape must itself fit the cell, byte and dimension
    budgets the loaded arrays are later held to, so an archive cannot make the
    reader allocate first and discover the budget afterwards.
    """
    if set(headers) != set(ARRAY_NAMES):
        raise ValueError("stored array set differs from the declared array set")
    shape = _shape_zx(shape_zx)
    _grid_budget(shape)
    seen = None
    for name in ARRAY_NAMES:
        shape_value, dtype = headers[name]
        if (dtype != ARRAY_DTYPES[name] or len(shape_value) != 2
                or any(int(size) < 1 for size in shape_value)):
            raise ValueError("invalid stored array header: " + name)
        current = (int(shape_value[0]), int(shape_value[1]))
        if seen is None:
            seen = current
        elif current != seen:
            raise ValueError("stored array headers disagree on the grid shape")
        if current != shape:
            raise ValueError("stored array header shape differs from the declared shape_zx: "
                             + name)


def _header_validator(shape_zx):
    """Bind the declared shape into the single-argument header gate."""
    return lambda headers: _validate_headers(headers, shape_zx)


def _verify_accumulation(arrays, metadata):
    result = accumulate_network_discharge(
        arrays["receiver"], arrays["local_q_m3_s"], arrays["valid_mask"],
        terminal_kind=arrays["terminal_kind"],
        upstream_unknown_mask=arrays["upstream_unknown_mask"])
    for name in ("known_routed_q_m3_s", "complete_mask", "terminal_q_m3_s"):
        if not np.array_equal(arrays[name], result[name]):
            raise ValueError("stored " + name + " disagrees with a fresh accumulation")
    if metadata["policy"] != result["policy"]:
        raise ValueError("stored accumulation policy disagrees with the frozen module")
    ledger = metadata["ledger"]
    for name in LEDGER_NAMES:
        stored = ledger[name]
        fresh = result[name]
        if name in ("valid_cells", "processed_cells"):
            if type(stored) is not int or stored != int(fresh):
                raise ValueError("ledger entry disagrees with a fresh accumulation: " + name)
        elif (isinstance(stored, bool) or not isinstance(stored, (int, float))
              or not math.isfinite(stored)
              or abs(float(stored) - float(fresh)) > 1e-12 * max(1., abs(float(fresh)))):
            raise ValueError("ledger entry disagrees with a fresh accumulation: " + name)
    valid = arrays["valid_mask"]
    expected_counts = {
        "valid_cells": int(valid.sum()),
        "incomplete_valid_cells": int((valid & ~arrays["complete_mask"]).sum()),
        "unknown_upstream_seed_cells": int(arrays["upstream_unknown_mask"].sum())}
    if metadata["counts"] != expected_counts:
        raise ValueError("declared counts disagree with the stored arrays")


def _format_version(record):
    """The stored format version must be the integer 1, not ``True`` or ``1.0``."""
    value = record.get("format_version")
    if isinstance(value, (bool, np.bool_)) or type(value) is not int:
        raise ValueError("format_version must be the integer " + str(FORMAT_VERSION))
    if value != FORMAT_VERSION:
        raise ValueError("unexpected discharge product format version")
    return value


def _validate_common(record, arrays, *, recompute, hash_arrays):
    if not isinstance(record, dict):
        raise ValueError("discharge product record required")
    _format_version(record)
    if record.get("schema") != SCHEMA or record.get("status") != STATUS:
        raise ValueError("unexpected discharge product schema, format version or status")
    metadata = _validate_metadata(record.get("metadata"))
    _validate_arrays(arrays, metadata["shape_zx"])
    declared = record.get("array_sha256")
    if not isinstance(declared, dict) or set(declared) != set(ARRAY_NAMES):
        raise ValueError("invalid stored array declarations")
    for name in ARRAY_NAMES:
        _sha256_text(declared[name], "array digest " + name)
        if hash_arrays and array_hash(arrays[name]) != declared[name]:
            raise ValueError("stored array differs from its declared digest: " + name)
    if record.get("identity_sha256") != _identity(record):
        raise ValueError("discharge product identity mismatch")
    if recompute:
        _verify_accumulation(arrays, metadata)


def _validate_product(product, *, recompute, hash_arrays=True):
    if not isinstance(product, dict) or set(product) != set(PRODUCT_KEYS):
        raise ValueError("invalid discharge product fields")
    _validate_common(product, product["arrays"], recompute=recompute, hash_arrays=hash_arrays)


def build_discharge_product(receiver, local_q_m3_s, valid_mask, terminal_kind,
                            upstream_unknown_mask, *, origin_native_cells, world_seed,
                            interval_seconds, source_sha256, forcing_semantics,
                            spacing_m=30., max_cells=MAX_NETWORK_CELLS):
    """Accumulate one bounded receiver graph into a cold-readable diagnostic product.

    ``upstream_unknown_mask`` is a required array: there is no default that would
    silently declare the upstream complete. ``terminal_kind`` is stored exactly as
    declared. Storage layout, coordinate origin in native cells, world seed, the
    physical interval, the source digest and the forcing semantics are bound into
    the product identity; no code path here certifies routing or real runoff.
    """
    if (not isinstance(receiver, np.ndarray) or receiver.dtype != np.dtype(np.int64)
            or receiver.ndim != 2 or not 1 <= receiver.size):
        raise ValueError("bounded nonempty int64 [z,x] receiver required")
    shape = receiver.shape
    for array, dtype, label in ((local_q_m3_s, np.dtype(np.float64), "local_q_m3_s"),
                                (valid_mask, np.dtype(np.bool_), "valid_mask")):
        if not isinstance(array, np.ndarray) or array.dtype != dtype or array.shape != shape:
            raise ValueError(label + " must have matching shape and exact dtype")
    if (not isinstance(terminal_kind, np.ndarray) or terminal_kind.shape != shape
            or terminal_kind.dtype.kind != "U"):
        raise ValueError("matching Unicode terminal_kind array required")
    if (not isinstance(upstream_unknown_mask, np.ndarray)
            or upstream_unknown_mask.dtype != np.dtype(np.bool_)
            or upstream_unknown_mask.shape != shape):
        raise ValueError("an explicit matching boolean upstream_unknown_mask is required")
    width = TERMINAL_KIND_DTYPE.itemsize // 4
    if terminal_kind.dtype.itemsize // 4 > width:
        # Vectorized width check: never build a per-cell Python string list.
        if np.any(np.char.str_len(terminal_kind.ravel()) > width):
            raise ValueError("terminal_kind label exceeds the canonical " + str(width) + " characters")
    kinds = np.ascontiguousarray(terminal_kind, dtype=TERMINAL_KIND_DTYPE)
    origin = _origin(origin_native_cells)
    spacing = _positive_float(spacing_m, "spacing_m")
    seed = _integer(world_seed, "world_seed")
    interval = _interval(interval_seconds)
    source = _sha256_text(source_sha256, "source_sha256")
    semantics = _nonempty_text(forcing_semantics, "forcing_semantics")

    result = accumulate_network_discharge(receiver, local_q_m3_s, valid_mask,
                                         terminal_kind=kinds,
                                         upstream_unknown_mask=upstream_unknown_mask,
                                         max_cells=max_cells)

    arrays = {
        "receiver": readonly(np.ascontiguousarray(receiver, dtype=np.int64)),
        "local_q_m3_s": readonly(np.ascontiguousarray(local_q_m3_s, dtype=np.float64)),
        "valid_mask": readonly(valid_mask),
        "terminal_kind": readonly(kinds),
        "upstream_unknown_mask": readonly(upstream_unknown_mask),
        "known_routed_q_m3_s": readonly(result["known_routed_q_m3_s"]),
        "complete_mask": readonly(result["complete_mask"]),
        "terminal_q_m3_s": readonly(result["terminal_q_m3_s"]),
    }
    metadata = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "algorithm_version": ALGORITHM_VERSION,
        "status": STATUS,
        "coordinates": COORDINATES,
        "origin_native_cells": origin,
        "shape_zx": [int(shape[0]), int(shape[1])],
        "spacing_m": spacing,
        "world_seed": seed,
        "interval_seconds": interval,
        "source_sha256": source,
        "forcing_semantics": semantics,
        "policy": str(result["policy"]),
        "ledger": {name: (int(result[name]) if name in ("valid_cells", "processed_cells")
                          else float(result[name])) for name in LEDGER_NAMES},
        "counts": {
            "valid_cells": int(valid_mask.sum()),
            "incomplete_valid_cells": int((valid_mask & ~result["complete_mask"]).sum()),
            "unknown_upstream_seed_cells": int(upstream_unknown_mask.sum()),
        },
        "complete_definition": COMPLETE_DEFINITION,
        "finite_graph_only": True,
        "topology_window_invariance_verified": False,
        "natural_outlet_certified": False,
        "hydraulic_ready": False,
        "publishable": False,
    }
    record = {
        "format_version": FORMAT_VERSION,
        "schema": SCHEMA,
        "status": STATUS,
        "metadata": metadata,
        "array_sha256": {name: array_hash(arrays[name]) for name in ARRAY_NAMES},
    }
    record["identity_sha256"] = _identity(record)
    product = dict(record)
    product["arrays"] = arrays
    # The digests were just computed from exactly these arrays; do not rehash them.
    _validate_product(product, recompute=False, hash_arrays=False)
    return product


def save_discharge_product(path, product):
    """Publish a product directory; never overwrite, never leave debris.

    Both files are flushed and fsynced before the temporary package is cold-read
    and renamed into place, so a published directory holds fully written bytes.
    This is file durability only: it is not a directory transaction and it makes
    no promise about a POSIX rename race or a power loss outside this process.
    """
    _validate_product(product, recompute=False)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(str(destination))
    if not destination.parent.is_dir():
        raise FileNotFoundError(str(destination.parent))
    temporary = Path(tempfile.mkdtemp(prefix="." + destination.name + "-",
                                      dir=destination.parent))
    try:
        arrays = product["arrays"]
        arrays_path = temporary / ARRAYS_FILE
        manifest_path = temporary / MANIFEST_FILE
        with open(arrays_path, "wb") as stream:
            np.savez(stream, **{name: arrays[name] for name in ARRAY_NAMES})
            stream.flush()
            os.fsync(stream.fileno())
        manifest = {name: product[name] for name in RECORD_FIELDS}
        manifest["arrays_file"] = ARRAYS_FILE
        manifest["arrays_file_sha256"] = file_sha256(arrays_path)
        with open(manifest_path, "wb") as stream:
            stream.write(canonical_json(manifest).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        # Cold-read the flushed temporary package before publishing it.
        load_discharge_product(temporary)
        if destination.exists():
            raise FileExistsError(str(destination))
        os.rename(temporary, destination)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def load_discharge_product(path):
    """Cold-read and re-verify a saved product; any inconsistency is refused."""
    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(str(directory))
    if {entry.name for entry in directory.iterdir()} != {MANIFEST_FILE, ARRAYS_FILE}:
        raise ValueError("discharge product must contain exactly manifest.json and arrays.npz")
    for name in (MANIFEST_FILE, ARRAYS_FILE):
        entry = directory / name
        if not entry.is_file() or entry.is_symlink():
            raise ValueError("discharge product files must be regular files")
    manifest_path = directory / MANIFEST_FILE
    declared_bytes = manifest_path.stat().st_size
    if declared_bytes > MAX_METADATA_BYTES:
        raise ValueError("manifest exceeds the metadata byte budget")
    # Bounded read: one byte past the budget is enough to detect a file that grew
    # between the stat above and this read, so no unbounded read is ever issued.
    with open(manifest_path, "rb") as stream:
        payload = stream.read(MAX_METADATA_BYTES + 1)
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError("manifest exceeds the metadata byte budget")
    manifest = _parse_manifest(payload)
    if not isinstance(manifest, dict) or set(manifest) != set(MANIFEST_KEYS):
        raise ValueError("invalid discharge manifest fields")
    if manifest["arrays_file"] != ARRAYS_FILE:
        raise ValueError("discharge manifest names an unexpected array file")
    # The declared shape is checked against the archive headers before any array
    # is allocated; a package cannot bypass the cell/byte budget by growing here.
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("discharge manifest carries no metadata record")
    declared_shape = _shape_zx(metadata.get("shape_zx"))
    arrays = checked_archive(directory / ARRAYS_FILE,
                             expected_sha256=_sha256_text(manifest["arrays_file_sha256"],
                                                          "arrays_file_sha256"),
                             max_bytes=MAX_BYTES,
                             header_validator=_header_validator(declared_shape))
    _validate_common(manifest, arrays, recompute=True, hash_arrays=True)
    product = {name: manifest[name] for name in RECORD_FIELDS}
    product["arrays"] = {name: readonly(arrays[name]) for name in ARRAY_NAMES}
    return product


def require_complete_discharge(product, requested_mask):
    """Return a private copy of the requested Q, or refuse the whole request.

    Cells the product marks invalid, and cells whose upstream is declared
    incomplete, are refused rather than silently reported as zero discharge.
    The returned array is a fresh writable copy in canonical flat-index order
    (``np.flatnonzero(requested_mask)``), never a view of the product.

    The gate re-runs the frozen accumulation on the stored inputs every time it
    is called (``recompute=True``), exactly as ``load_discharge_product`` does,
    and then enforces the refusal semantics. Re-sealed edits to the routed Q, the
    completeness mask, the ledger or the declared counts are therefore refused
    here too, not only at cold load. Recomputing proves the derived arrays match
    the declared inputs; it does not authenticate those inputs (see the module
    docstring). It does not prove a natural outlet and does not make the result
    usable as hydraulic input.
    """
    _validate_product(product, recompute=True, hash_arrays=True)
    arrays = product["arrays"]
    shape = arrays["valid_mask"].shape
    if (not isinstance(requested_mask, np.ndarray) or requested_mask.dtype != np.dtype(np.bool_)
            or requested_mask.shape != shape):
        raise ValueError("requested_mask must be a matching boolean [z,x] array")
    if not requested_mask.any():
        raise ValueError("requested_mask must request at least one cell")
    invalid = requested_mask & ~arrays["valid_mask"]
    if invalid.any():
        raise ValueError("requested_mask includes " + str(int(invalid.sum()))
                         + " invalid cells; they are refused, not zero-filled")
    incomplete = requested_mask & ~arrays["complete_mask"]
    if incomplete.any():
        raise ValueError("requested_mask includes " + str(int(incomplete.sum()))
                         + " cells with declared unknown upstream; the request is refused, "
                           "not partially zero-filled")
    return arrays["known_routed_q_m3_s"][requested_mask].copy()
