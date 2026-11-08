# -*- coding: utf-8 -*-
"""Cold-readable product codec and read-only query index for the river backbone.

Scope
-----
This module **stores and reads** one prepared backbone product and answers read-only
questions about it. It adds no physics: it never routes, never re-derives D8, never
fills a depression and never accumulates discharge.

Why ``load`` does not recompute the accumulation
------------------------------------------------
A cold load answers three questions and no more: are the bytes the bytes declared, does
the declared support match the archive headers, and is the stored content internally
coherent (shapes, dtypes, index ranges, monotone pointers, identity digest). Re-running
the network accumulation on every load would make an ordinary query pay a whole-graph
pass, and would turn "read a product" into "recompute a product". The explicit
verification entry lives in ``tools/audit_river_backbone.py`` and is called once, on
demand; ``metric_backbone_precompute.validate_backbone`` is the in-process form of it.

Import discipline
-----------------
This module deliberately does **not** import ``metric_backbone_precompute`` and does not
touch ``metric_domain_closure`` / ``native_30m_source``. Loading a product therefore
cannot drag the D8 kernel (and its planning-configuration transitive imports) into a
process that only wants to read numbers.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, canonical_json, digest
from terrain_pipeline.common_infra import checked_archive, file_sha256, readonly

SCHEMA = "metric-river-backbone-v1"
FORMAT_VERSION = 1
ALGORITHM = "metric-river-backbone"

MANIFEST_FILE = "manifest.json"
ARRAYS_FILE = "arrays.npz"

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARRAYS_BYTES = 128 * 1024 * 1024
MAX_TOTAL_ARRAY_BYTES = 160 * 1024 * 1024
MAX_ARRAY_MEMBERS = 128
MAX_SUPPORT_CELLS = 148_225
MAX_DIMENSION = 8_000_000
MAX_STEPS = 512
MAX_NODES = MAX_SUPPORT_CELLS

TERMINAL_KIND_DTYPE = np.dtype("U24")
TERMINAL_LABELS = ("inactive", "interior", "retained", "open_outflow", "unknown_boundary")

FLUX_QUANTITIES = ("source_model_scenario", "climatology_estimate")
QUANTITY_STATUS_AVAILABLE = "available"
QUANTITY_STATUS_PENDING = "not_available_pending"

#: Read-only scopes this codec can answer. Anything not listed is a refusal, not a
#: silently empty answer.
SCOPES = ("backbone_topology", "backbone_area", "backbone_flux", "backbone_terminal",
          "backbone_path")

#: Things a caller may reasonably ask for that this product does **not** contain.
#: They are named so the refusal is specific instead of a generic "unknown scope".
NOT_IMPLEMENTED = (
    "water_depth", "stage", "hydraulics", "natural_outlet", "permanent_terminal",
    "floodplain_2d", "world_complete", "display_line",
)

GRID_ARRAY_NAMES = ("receiver", "valid_mask", "terminal_kind", "upstream_unknown_mask",
                    "area_cells", "area_complete", "channel_mask", "gate_mask",
                    "gate_terminal_mask", "a_gate_mask", "q_gate_mask", "reach_of_cell")

RECORD_KEYS = ("format_version", "schema", "algorithm", "metadata", "array_sha256",
               "identity_sha256")


class BackboneProductRefused(ValueError):
    """A product, a request or an index is refused; never partially answered."""


def _refuse(message):
    raise BackboneProductRefused(message)


def _sha256_text(value, label):
    if not isinstance(value, str) or len(value) != 64 \
            or any(character not in "0123456789abcdef" for character in value):
        _refuse("%s must be a lowercase 64-character sha256" % label)
    return value


def _shape_zx(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        _refuse("shape_zx must be a two-element list")
    rows = value[0]
    columns = value[1]
    for side in (rows, columns):
        if isinstance(side, bool) or not isinstance(side, int) or not 2 <= side <= MAX_DIMENSION:
            _refuse("shape_zx sides must be integers in [2, %d]" % MAX_DIMENSION)
    if rows * columns > MAX_SUPPORT_CELLS:
        _refuse("this product declares %d cells, above the %d ceiling; a larger support "
                "needs its own budget and a separate review"
                % (rows * columns, MAX_SUPPORT_CELLS))
    return int(rows), int(columns)


def _parse_manifest(payload):
    def reject(constant):
        raise ValueError("non-finite constant %r in the manifest" % constant)

    try:
        value = json.loads(payload.decode("utf-8"), parse_constant=reject)
    except UnicodeDecodeError:
        _refuse("the manifest is not UTF-8")
    except ValueError as error:
        _refuse("the manifest is not valid JSON: %s" % error)
    if not isinstance(value, dict):
        _refuse("the manifest must be a JSON object")
    return value


def _header_validator(shape_zx):
    rows, columns = shape_zx

    def validate(headers):
        if not headers:
            _refuse("the archive holds no array")
        if len(headers) > MAX_ARRAY_MEMBERS:
            _refuse("the archive holds %d arrays, above the %d member budget"
                    % (len(headers), MAX_ARRAY_MEMBERS))
        total = 0
        for name, (shape, dtype) in headers.items():
            if dtype.hasobject:
                _refuse("the array %r has an object dtype" % name)
            if name in GRID_ARRAY_NAMES and tuple(shape) != (rows, columns):
                _refuse("the grid array %r declares shape %s, the support says %s"
                        % (name, list(shape), [rows, columns]))
            total += int(np.prod(shape)) * int(dtype.itemsize)
        if total > MAX_TOTAL_ARRAY_BYTES:
            _refuse("the arrays total %d bytes, above the %d budget"
                    % (total, MAX_TOTAL_ARRAY_BYTES))
    return validate


def _check_arrays(arrays, shape_zx, steps, nodes, reach_count):
    rows, columns = shape_zx
    for name in GRID_ARRAY_NAMES:
        if name not in arrays:
            _refuse("the product is missing the grid array %r" % name)
        value = arrays[name]
        if value.shape != (rows, columns):
            _refuse("the array %r must be [%d, %d]" % (name, rows, columns))
    expected = {
        "receiver": np.dtype(np.int64),
        "valid_mask": np.dtype(np.bool_),
        "upstream_unknown_mask": np.dtype(np.bool_),
        "area_cells": np.dtype(np.int64),
        "area_complete": np.dtype(np.bool_),
        "channel_mask": np.dtype(np.bool_),
        "gate_mask": np.dtype(np.bool_),
        "gate_terminal_mask": np.dtype(np.bool_),
        "a_gate_mask": np.dtype(np.bool_),
        "q_gate_mask": np.dtype(np.bool_),
        "reach_of_cell": np.dtype(np.int64),
    }
    for name, dtype in expected.items():
        if arrays[name].dtype != dtype:
            _refuse("the array %r must have dtype %s" % (name, np.dtype(dtype).name))
    if arrays["terminal_kind"].dtype.kind != "U":
        _refuse("terminal_kind must be a Unicode array")
    valid = arrays["valid_mask"]
    receiver = arrays["receiver"].reshape(-1)
    cells = rows * columns
    if np.any(receiver < -1) or np.any(receiver >= cells):
        _refuse("a stored receiver index is outside the grid")
    if np.any(receiver[~valid.reshape(-1)] != -1):
        _refuse("a stored inactive cell carries a receiver")
    live = valid.reshape(-1) & (receiver >= 0)
    if live.any() and np.any(~valid.reshape(-1)[receiver[live]]):
        _refuse("a stored receiver points at an inactive cell")
    if np.any(arrays["upstream_unknown_mask"][~valid]):
        _refuse("a stored unknown seed sits on an inactive cell")
    if not np.isin(arrays["terminal_kind"][valid],
                   ("interior", "retained", "open_outflow", "unknown_boundary")).all():
        _refuse("a stored terminal kind is outside the declared vocabulary")
    if np.any(arrays["terminal_kind"][~valid] != "inactive"):
        _refuse("a stored inactive cell does not declare 'inactive'")
    if np.any(arrays["area_cells"][~valid] != 0):
        _refuse("a stored inactive cell carries an upstream area")
    if np.any(arrays["area_cells"] < 0):
        _refuse("a stored upstream area is negative")
    if np.any(arrays["area_cells"][valid] < 1):
        _refuse("a stored valid cell has no self area")
    for name in ("channel_mask", "gate_mask", "gate_terminal_mask", "a_gate_mask",
                 "q_gate_mask"):
        if np.any(arrays[name][~valid]):
            _refuse("the mask %r selects an inactive cell" % name)
    gate = arrays["gate_mask"].reshape(-1)
    channel = arrays["channel_mask"].reshape(-1)
    gate_terminal = arrays["gate_terminal_mask"].reshape(-1)
    if not np.array_equal(gate, channel | gate_terminal):
        _refuse("gate_mask is not channel_mask | gate_terminal_mask")
    if np.any(gate_terminal & (arrays["receiver"].reshape(-1) >= 0)):
        _refuse("a stored gate terminal anchor carries a receiver")
    if not np.array_equal(arrays["reach_of_cell"].reshape(-1) >= 0,
                          arrays["channel_mask"].reshape(-1)):
        _refuse("reach_of_cell does not cover exactly the stored channel")
    for name, size in (("reach_ptr", reach_count + 1),
                       ("reach_downstream", reach_count),
                       ("reach_head", reach_count),
                       ("reach_tail", reach_count),
                       ("reach_root_index", reach_count),
                       ("reach_source", reach_count),
                       ("reach_donors", reach_count),
                       ("reach_node_count", reach_count),
                       ("reach_length_m", reach_count),
                       ("reach_handoff_length_m", reach_count)):
        if name not in arrays or int(np.asarray(arrays[name]).size) != size:
            _refuse("the reach array %r must hold %d entries" % (name, size))
    pointer = np.asarray(arrays["reach_ptr"], np.int64)
    if int(pointer[0]) != 0 or int(pointer[-1]) != nodes:
        _refuse("reach_ptr does not close over the node count %d" % nodes)
    if reach_count and (np.any(np.diff(pointer) < 1) or np.any(pointer < 0)):
        _refuse("reach_ptr is not monotone")
    for name in ("reach_cells", "node_area_cells"):
        if name not in arrays:
            _refuse("the product is missing the node array %r" % name)
    if int(np.asarray(arrays["reach_cells"]).size) != nodes:
        _refuse("reach_cells must hold %d entries" % nodes)
    if int(np.asarray(arrays["node_area_cells"]).size) != nodes:
        _refuse("node_area_cells must hold %d entries" % nodes)
    if int(np.asarray(arrays["node_area_complete"]).size) != nodes:
        _refuse("node_area_complete must hold %d entries" % nodes)
    edges = np.asarray(arrays["time_edges_s"], np.float64)
    if edges.size != steps + 1:
        _refuse("time_edges_s must hold steps+1 entries")
    if not np.isfinite(edges).all() or np.any(np.diff(edges) <= 0.0):
        _refuse("time_edges_s must be finite and strictly increasing")
    index = np.asarray(arrays["local_input_index"], np.int64)
    if index.size != int(valid.sum()):
        _refuse("local_input_index must hold one entry per valid cell")
    if index.size and (int(index.min()) < 0 or int(index.max()) >= cells):
        _refuse("local_input_index leaves the grid")
    if np.unique(index).size != index.size:
        _refuse("local_input_index repeats a cell")
    if not np.array_equal(np.sort(index), np.flatnonzero(valid.reshape(-1))):
        _refuse("local_input_index must list exactly the valid cells")
    for name, value in arrays.items():
        if name.startswith("node_q_") and name.endswith("_m3_s"):
            if value.shape != (steps, nodes):
                _refuse("the node flux series %r must be [steps, nodes]" % name)
            if not np.isfinite(value).all() or np.any(value < 0.0):
                _refuse("the node flux series %r must be finite and nonnegative" % name)
        if name.startswith("node_q_") and name.endswith("_complete"):
            if value.shape != (nodes,):
                _refuse("the node completeness array %r must be [nodes]" % name)
        if name.startswith("local_input_") and name.endswith("_m3_s"):
            if value.shape != (steps, index.size):
                _refuse("the local input %r must be [steps, valid_cells]" % name)
            if not np.isfinite(value).all() or np.any(value < 0.0):
                _refuse("the local input %r must be finite and nonnegative" % name)
        if name.startswith("local_input_") and name.endswith("_available"):
            if value.shape != (index.size,):
                _refuse("the local availability %r must be [valid_cells]" % name)
    return None


def _parse_metadata(metadata):
    if not isinstance(metadata, dict):
        _refuse("the manifest carries no metadata record")
    if metadata.get("schema") != SCHEMA:
        _refuse("the metadata declares schema %r, expected %r"
                % (metadata.get("schema"), SCHEMA))
    if metadata.get("algorithm") != ALGORITHM:
        _refuse("the metadata declares algorithm %r" % (metadata.get("algorithm"),))
    shape_zx = _shape_zx(metadata.get("shape_zx"))
    counts = metadata.get("counts")
    if not isinstance(counts, dict):
        _refuse("the metadata carries no counts record")
    reach_count = counts.get("reach_count")
    node_count = counts.get("node_count_total")
    if isinstance(reach_count, bool) or not isinstance(reach_count, int) or reach_count < 0:
        _refuse("counts.reach_count must be a nonnegative integer")
    if isinstance(node_count, bool) or not isinstance(node_count, int) or node_count < 0:
        _refuse("counts.node_count_total must be a nonnegative integer")
    clock = metadata.get("clock")
    if not isinstance(clock, dict):
        _refuse("the metadata carries no clock record")
    steps = clock.get("steps")
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS:
        _refuse("clock.steps must be an integer in [1, %d]" % MAX_STEPS)
    quantities = metadata.get("quantities")
    if not isinstance(quantities, dict):
        _refuse("the metadata carries no quantity record")
    for name, report in quantities.items():
        if name not in FLUX_QUANTITIES:
            _refuse("%r is not a declared flux quantity" % (name,))
        if not isinstance(report, dict) or report.get("status") != QUANTITY_STATUS_AVAILABLE:
            _refuse("the quantity %r is not stored as available" % (name,))
        if report.get("steps") != steps:
            _refuse("the quantity %r declares %r steps, the clock says %d"
                    % (name, report.get("steps"), steps))
    gates = metadata.get("declared_gates")
    if not isinstance(gates, dict) or "a_min_cells" not in gates or "q_min_m3_s" not in gates:
        _refuse("the metadata must declare both gates")
    if not isinstance(metadata.get("origin_native_xz"), (list, tuple)) \
            or len(metadata["origin_native_xz"]) != 2:
        _refuse("the metadata must declare a signed native (x,z) origin")
    return shape_zx, reach_count, node_count, steps


def _identity_of(metadata, arrays):
    return digest({"metadata": metadata,
                   "arrays": {name: array_hash(np.asarray(value))
                              for name, value in sorted(arrays.items())}})


#: Per-reach fields a reader needs to find and describe a reach by its **world** id. The
#: node trace is not stored per cell (it rebuilds from ``reach_cells`` + the origin); the id,
#: the world anchors and the terminal classification are not derivable from the raster alone,
#: so they are persisted with the product and come back on a cold load.
REACH_RECORD_FIELDS = (
    "reach_id", "reach_index", "root_index", "root_world_xz", "head_world_xz",
    "tail_world_xz", "node_count", "edges", "length_m", "handoff_length_m",
    "downstream_reach_index", "downstream_reach_id", "terminal_kind", "terminal_reason",
    "terminal_cell_world_xz", "permanent_terminal", "event_receiver",
    "world_path_sha256", "area_status_at_tail", "area_cells_at_tail")


def _reach_records(rows):
    return [{key: row.get(key) for key in REACH_RECORD_FIELDS} for row in rows or []]


def build_record(*, metadata, arrays):
    """Assemble the manifest half of a product from already-built content."""
    record = {
        "format_version": FORMAT_VERSION,
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "metadata": metadata,
        "array_sha256": {name: array_hash(np.asarray(value))
                         for name, value in sorted(arrays.items())},
    }
    record["identity_sha256"] = _identity_of(metadata, arrays)
    return record


def save_backbone_product(path, product):
    """Publish one product directory; never overwrite, never leave debris.

    Both files are flushed and fsynced before the temporary package is cold-read and
    renamed into place, so a published directory holds fully written bytes. This is file
    durability, not a directory transaction: no POSIX rename race and no power-loss
    promise is made.
    """
    if not isinstance(product, dict) or "metadata" not in product or "arrays" not in product:
        _refuse("a product needs metadata and arrays")
    metadata = product["metadata"]
    arrays = product["arrays"]
    identity = product.get("identity_sha256")
    record = build_record(metadata=metadata, arrays=arrays)
    if identity is not None and identity != record["identity_sha256"]:
        _refuse("the declared product identity is not the identity of its own content")
    record["identity_sha256"] = record["identity_sha256"]
    shape_zx, reach_count, nodes, steps = _parse_metadata(metadata)
    _check_arrays(arrays, shape_zx, steps, nodes, reach_count)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(str(destination))
    if not destination.parent.is_dir():
        raise FileNotFoundError(str(destination.parent))
    total = sum(int(np.asarray(value).nbytes) for value in arrays.values())
    if total > MAX_ARRAYS_BYTES:
        _refuse("the payload would be %d bytes, above the %d budget; refusing before any "
                "byte is written" % (total, MAX_ARRAYS_BYTES))
    temporary = Path(tempfile.mkdtemp(prefix="." + destination.name + "-",
                                      dir=destination.parent))
    try:
        arrays_path = temporary / ARRAYS_FILE
        manifest_path = temporary / MANIFEST_FILE
        with open(arrays_path, "wb") as stream:
            np.savez(stream, **{name: np.asarray(value) for name, value in arrays.items()})
            stream.flush()
            os.fsync(stream.fileno())
        manifest = dict(record)
        manifest["arrays_file"] = ARRAYS_FILE
        manifest["arrays_file_sha256"] = file_sha256(arrays_path)
        manifest["payload_bytes"] = int(total)
        manifest["reaches"] = _reach_records(product.get("reaches"))
        with open(manifest_path, "wb") as stream:
            stream.write(canonical_json(manifest).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        load_backbone_product(temporary)
        if destination.exists():
            raise FileExistsError(str(destination))
        os.rename(temporary, destination)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def load_backbone_product(path, *, expected_identity_sha256=None, verify_accumulation=False):
    """Cold-read one product: bytes, budget, headers, identity, and stored-array coherence.

    Nothing here re-runs the network accumulation. A plain read answers only: are the bytes
    the bytes declared, does the declared support match the archive headers, and is the
    stored content internally coherent. Fully re-deriving the network is a **separate,
    explicit** step: ``metric_backbone_precompute.validate_backbone`` in process (used by
    ``tools/prepare_river_backbone.py`` before it publishes) and the independent recomputation
    in ``tools/audit_river_backbone.py``, which does it once, with its own implementation.

    ``verify_accumulation`` is therefore **refused**: the product directory carries only its
    parent's identity, which cannot re-derive the parent's topology, so a loaded product can
    never be re-accumulated on its own. Passing it is an error, not a silent no-op.
    """
    if verify_accumulation:
        _refuse("a cold-loaded product cannot re-run the accumulation: the parent bundle is not "
                "stored, only its identity. Use tools/audit_river_backbone.py, which "
                "recomputes independently, or validate_backbone() before publishing")
    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(str(directory))
    present = {entry.name for entry in directory.iterdir()}
    if MANIFEST_FILE not in present or ARRAYS_FILE not in present:
        _refuse("a product directory must hold %s and %s" % (MANIFEST_FILE, ARRAYS_FILE))
    for name in (MANIFEST_FILE, ARRAYS_FILE):
        entry = directory / name
        if not entry.is_file() or entry.is_symlink():
            _refuse("the product files must be regular files")
    manifest_path = directory / MANIFEST_FILE
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        _refuse("the manifest exceeds the %d byte budget" % MAX_MANIFEST_BYTES)
    with open(manifest_path, "rb") as stream:
        payload = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(payload) > MAX_MANIFEST_BYTES:
        _refuse("the manifest grew past its byte budget while being read")
    manifest = _parse_manifest(payload)
    for key in RECORD_KEYS:
        if key not in manifest:
            _refuse("the manifest is missing the field %r" % (key,))
    if manifest["format_version"] != FORMAT_VERSION:
        _refuse("unsupported product format %r" % (manifest["format_version"],))
    if manifest["schema"] != SCHEMA or manifest["algorithm"] != ALGORITHM:
        _refuse("unexpected product schema/algorithm")
    if manifest.get("arrays_file") != ARRAYS_FILE:
        _refuse("the manifest names an unexpected array file")
    shape_zx, reach_count, nodes, steps = _parse_metadata(manifest["metadata"])
    declared_cells = shape_zx[0] * shape_zx[1]
    if declared_cells > MAX_SUPPORT_CELLS:
        _refuse("the declared support is above the ceiling")
    arrays = checked_archive(
        directory / ARRAYS_FILE,
        expected_sha256=_sha256_text(manifest.get("arrays_file_sha256"),
                                     "arrays_file_sha256"),
        max_bytes=MAX_ARRAYS_BYTES,
        header_validator=_header_validator(shape_zx))
    declared = manifest.get("array_sha256")
    if not isinstance(declared, dict) or set(declared) != set(arrays):
        _refuse("the manifest array digests do not name exactly the stored arrays")
    for name in sorted(arrays):
        if array_hash(arrays[name]) != _sha256_text(declared[name], "array_sha256[%s]" % name):
            _refuse("the stored array %r does not match its declared digest" % name)
    _check_arrays(arrays, shape_zx, steps, nodes, reach_count)
    identity = _identity_of(manifest["metadata"], arrays)
    if identity != _sha256_text(manifest["identity_sha256"], "identity_sha256"):
        _refuse("the product identity is not the identity of its own content")
    if expected_identity_sha256 is not None:
        if identity != _sha256_text(expected_identity_sha256, "expected_identity_sha256"):
            _refuse("the product identity is not the expected one")
    product = {
        "format_version": manifest["format_version"],
        "schema": manifest["schema"],
        "algorithm": manifest["algorithm"],
        "metadata": manifest["metadata"],
        "array_sha256": dict(declared),
        "identity_sha256": identity,
        "arrays": {name: readonly(value) for name, value in arrays.items()},
        "directory": str(directory),
        "payload_bytes": int(sum(int(value.nbytes) for value in arrays.values())),
        "reaches": manifest.get("reaches") or [],
    }
    reaches = product["reaches"]
    if len(reaches) != int(np.asarray(arrays["reach_downstream"]).size):
        _refuse("the manifest holds %d reach records for %d stored reaches"
                % (len(reaches), int(np.asarray(arrays["reach_downstream"]).size)))
    if len({row.get("reach_id") for row in reaches}) != len(reaches):
        _refuse("the manifest repeats a reach id")
    return product


# --------------------------------------------------------------------------- #
# read-only query index
# --------------------------------------------------------------------------- #
def require_scope(scope):
    if scope in NOT_IMPLEMENTED:
        _refuse("%s is not available in this product; it is declared NOT_IMPLEMENTED so the "
                "refusal is specific" % scope)
    if scope not in SCOPES:
        _refuse("unknown scope %r; this product answers %s" % (scope, list(SCOPES)))
    return scope


def _cell_of_point(product, world_native_xz):
    metadata = product["metadata"]
    origin = metadata["origin_native_xz"]
    rows, columns = metadata["shape_zx"]
    point = np.asarray(world_native_xz, np.int64).reshape(-1)
    if point.size != 2:
        _refuse("a world point must be a native (x, z) pair")
    dx = int(point[0]) - int(origin[0])
    dz = int(point[1]) - int(origin[1])
    if not (0 <= dx < columns and 0 <= dz < rows):
        _refuse("the point %s is outside the declared support origin=%s shape=%s; it is "
                "refused, not clipped" % (list(point.tolist()), list(origin),
                                          list(metadata["shape_zx"])))
    flat = dz * columns + dx
    if not bool(product["arrays"]["valid_mask"].reshape(-1)[flat]):
        _refuse("the point %s lands on an unresolved cell; it is refused, not zero-filled"
                % (list(point.tolist()),))
    return int(flat)


def _reach_row(product, reach_id):
    for row in product.get("reaches", []) or []:
        if row.get("reach_id") == reach_id:
            return row
    _refuse("no reach with id %r" % (reach_id,))


def reach_index(product):
    """``{reach_id: (reach_index, head_flat, tail_flat)}`` from the stored arrays only."""
    arrays = product["arrays"]
    pointer = np.asarray(arrays["reach_ptr"], np.int64)
    rows = product.get("reaches", []) or []
    if len(rows) != pointer.size - 1:
        _refuse("the product holds %d reach rows for %d stored reaches"
                % (len(rows), pointer.size - 1))
    return {row["reach_id"]: (index, int(pointer[index]), int(pointer[index + 1] - 1))
            for index, row in enumerate(rows)}


def query_reach(product, *, reach_id=None, world_native_xz=None):
    """Answer one read-only question about a cell or a reach.

    Only stored numbers are read: no accumulation, no routing, no D8. A request that
    cannot be answered exactly is refused rather than approximated.
    """
    arrays = product["arrays"]
    metadata = product["metadata"]
    steps = int(metadata["clock"]["steps"])
    edges = np.asarray(arrays["time_edges_s"], np.float64)
    answered = {
        "schema": SCHEMA,
        "product_identity_sha256": product["identity_sha256"],
        "origin_native_xz": list(metadata["origin_native_xz"]),
        "shape_zx": list(metadata["shape_zx"]),
        "spacing_m": float(metadata["spacing_m"]),
        "cell_area_m2": float(metadata["cell_area_m2"]),
        "time_edges_s": [float(v) for v in edges],
        "steps": steps,
        "quantities": {},
        "hydraulic_state": dict(metadata["hydraulic_state"]),
        "display_line": None,
        "display_line_policy": metadata["display_line_policy"],
    }
    if (reach_id is None) == (world_native_xz is None):
        _refuse("ask about exactly one of reach_id or world_native_xz")
    if world_native_xz is not None:
        flat = _cell_of_point(product, world_native_xz)
        flat_area = np.asarray(arrays["area_cells"], np.int64).reshape(-1)
        flat_complete = np.asarray(arrays["area_complete"], np.bool_).reshape(-1)
        flat_valid = np.asarray(arrays["valid_mask"], np.bool_).reshape(-1)
        flat_channel = np.asarray(arrays["channel_mask"], np.bool_).reshape(-1)
        flat_kind = np.asarray(arrays["terminal_kind"]).reshape(-1)
        flat_reach = np.asarray(arrays["reach_of_cell"], np.int64).reshape(-1)
        answered["cell"] = {
            "kind": "cell",
            "world_native_xz": [int(world_native_xz[0]), int(world_native_xz[1])],
            "valid": bool(flat_valid[flat]),
            "channel": bool(flat_channel[flat]),
            "reach_index": int(flat_reach[flat]),
            "terminal_kind_of_cell": str(flat_kind[flat]),
            "is_channel_node": bool(flat_channel[flat]),
            "area_cells": int(flat_area[flat]),
            "area_m2": float(int(flat_area[flat]) * float(metadata["cell_area_m2"])),
            "area_status": ("complete" if bool(flat_complete[flat])
                            else "lower_bound_pending"),
        }
        position = None
        if int(flat_reach[flat]) >= 0:
            pointer = np.asarray(arrays["reach_ptr"], np.int64)
            index = int(flat_reach[flat])
            node_start = int(pointer[index])
            node_stop = int(pointer[index + 1])
            cells = np.asarray(arrays["reach_cells"], np.int64)[node_start:node_stop]
            offset = int(np.flatnonzero(cells == flat)[0])
            position = node_start + offset
        answered["node_offset"] = position
    else:
        row = _reach_row(product, reach_id)
        pointer = np.asarray(arrays["reach_ptr"], np.int64)
        index = int(row["reach_index"])
        node_start = int(pointer[index])
        node_stop = int(pointer[index + 1])
        cells = np.asarray(arrays["reach_cells"], np.int64)[node_start:node_stop]
        columns = metadata["shape_zx"][1]
        origin = metadata["origin_native_xz"]
        world = np.stack([origin[0] + cells % columns, origin[1] + cells // columns], axis=1)
        answered["cell"] = None
        answered["reach"] = dict(row)
        answered["reach"]["node_world_native_xz"] = [[int(a), int(b)] for a, b in
                                                     world.tolist()]
        answered["node_offset"] = None

    quantities = {}
    if answered["node_offset"] is not None:
        offset = answered["node_offset"]
        for name, report in sorted(metadata["quantities"].items()):
            series = np.asarray(arrays["node_q_%s_m3_s" % name], np.float64)
            complete = np.asarray(arrays["node_q_%s_complete" % name], np.bool_)
            quantities[name] = {
                "unit": "m3/s",
                "nature": report["semantics"]["nature"],
                "status": QUANTITY_STATUS_AVAILABLE,
                "q_m3_s_by_interval": [float(v) for v in series[:, offset]],
                "q_complete": bool(complete[offset]),
                "q_status": ("complete" if bool(complete[offset])
                             else "lower_bound_pending"),
                "gate_time_index": int(report["gate_time_index"]),
                "provenance": report.get("provenance") or {},
            }
    answered["quantities"] = quantities
    answered["area_status_policy"] = (
        "area completeness and every flux quantity's completeness are separate "
        "accumulations; one is never read off the other")
    answered["notes"] = {
        "no_accumulation_on_query": True,
        "no_d8_on_load": True,
        "refusals": "unknown scope, out-of-support point, unresolved cell, pending "
                    "quantity and missing product are refused, not approximated",
    }
    return answered


def require_prepared(product, requested_mask):
    """Return a private copy of the requested channel cells' area, or refuse the request.

    Cells outside the support, unresolved cells and cells outside the prepared channel are
    refused rather than silently reported as zero. The returned arrays are fresh writable
    copies, never views of the product.
    """
    arrays = product["arrays"]
    shape = arrays["valid_mask"].shape
    if (not isinstance(requested_mask, np.ndarray) or requested_mask.dtype != np.dtype(np.bool_)
            or requested_mask.shape != shape):
        _refuse("requested_mask must be a matching boolean [z, x] array")
    if not requested_mask.any():
        _refuse("requested_mask must request at least one cell")
    invalid = requested_mask & ~arrays["valid_mask"]
    if invalid.any():
        _refuse("requested_mask includes %d unresolved cells; they are refused, not "
                "zero-filled" % int(invalid.sum()))
    outside = requested_mask & ~arrays["channel_mask"]
    if outside.any():
        _refuse("requested_mask includes %d cells outside the prepared channel; they are "
                "refused, not read as zero" % int(outside.sum()))
    return {"area_cells": np.array(arrays["area_cells"][requested_mask], dtype=np.int64),
            "area_m2": np.array(arrays["area_cells"][requested_mask], dtype=np.int64)
            * float(product["metadata"]["cell_area_m2"]),
            "area_complete": np.array(arrays["area_complete"][requested_mask],
                                      dtype=np.bool_)}


def census(product):
    """A count-only overview; no per-cell array is materialised beyond the stored masks."""
    metadata = product["metadata"]
    counts = metadata["counts"]
    arrays = product["arrays"]
    present = {name: int(np.asarray(arrays[name]).size) for name in sorted(arrays)}
    return {
        "schema": SCHEMA,
        "product_identity_sha256": product["identity_sha256"],
        "status": metadata["status"],
        "counts": dict(counts),
        "quantities": sorted(metadata["quantities"]),
        "hydraulics_available": bool(metadata["hydraulic_state"]["available"]),
        "display_line": None,
        "array_sizes": present,
        "declared_gates": dict(metadata["declared_gates"]),
        "payload_bytes": int(sum(int(np.asarray(arrays[name]).nbytes) for name in arrays)),
    }
