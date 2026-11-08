"""Independent cold-read audit of a prepared metric world-domain candidate package.

A prepared package is a directory holding ``manifest.json`` plus ``arrays.npz``
(written by ``tools/prepare_world_domains.py``). Every structural claim is
re-derived here from the raw arrays; no producer-side validator is trusted:

* ``receiver`` is recomputed from the source-frame shared irregular core;
* the raw unknown seeds, the downstream unknown cone (``complete_mask``) and
  ``upstream_cells`` are recomputed independently of the accumulator;
* every cell is walked along its receiver to a terminal, so owner coverage,
  member sets and root order are checked cell by cell rather than read back;
* each mainstem chain is rebuilt from its root by maximum donor
  ``upstream_cells`` with the declared world ``(x, z)`` tie-break, and the D4
  shared-face pair set is rebuilt from the owner grid.

The graph core is shared; terminal walking, accumulation and domain ledgers are
independent. The audit refuses a process carrying the producer or accumulator,
and records shared-core imports. ``prepare`` runs it in a separate process.

What this proves, and only this: the delivered package is a *structural*
candidate layer over the given original bed inside the declared support window.
Physical endpoints are not certified, ``basin_pending`` stays pending, and
nothing here is a production default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA = "metric-world-domain-candidates-v1"
AUDIT_SCHEMA = "metric-world-domain-candidates-audit-v1"
MANIFEST_NAME = "manifest.json"
ARRAYS_NAME = "arrays.npz"

#: Declared B1 support ceiling (385 x 385 = 148 225). Never raised here: a
#: larger support needs its own declared budget and a separate review.
MAX_SUPPORT_CELLS = 148225

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARRAYS_BYTES = 512 * 1024 * 1024
MAX_TOTAL_ARRAY_BYTES = 640 * 1024 * 1024
MAX_ARRAY_MEMBERS = 64
MAX_HEADER_BYTES = 4096

#: The declared cell spacing of this chain (30 m TD native). Used only to report a
#: mainstem length in metres next to its node/edge counts.
SPACING_M = 30.0

#: The declared world seed of this chain. A support copy that disagrees is refused.
WORLD_SEED = 20261020

#: Support facts that may be repeated in a package. Every copy that carries one of
#: these must equal the authoritative record exactly; this list is the binding surface.
SUPPORT_BOUND_FIELDS = (
    "schema", "world_seed", "spacing_m", "origin_native_xz", "shape_zx",
    "support_cells", "max_cells", "max_support_cells", "plan_version",
    "storage_representation", "range_native", "range_native_m",
    "source_records", "source_sha256", "source_record_count", "coordinate_rule",
)

NEIGHBOURS4 = ((0, 1), (1, 0))

BANNED_MODULES = (
    "terrain_pipeline.surface_rivers.metric_world_domains",
    "terrain_pipeline.surface_rivers.native_30m_source",
    'terrain_pipeline.drainage',
    "terrain_pipeline.surface_rivers.metric_domain_closure",
    "terrain_pipeline.surface_rivers.metric_network_discharge_product",
)

REQUIRED_ARRAYS = {
    "elevation_m": ("float64", 2),
    "resolved_mask": ("bool", 2),
    "receiver": ("int64", 2),
    "terminal_kind": ("unicode", 2),
    "upstream_unknown_mask": ("bool", 2),
    "complete_mask": ("bool", 2),
    "upstream_cells": ("int64", 2),
    "owner_index": ("int64", 2),
    "root_cells": ("int64", 1),
    "root_complete": ("bool", 1),
    "member_counts": ("int64", 1),
    "member_ptr": ("int64", 1),
    "member_cells": ("int64", 1),
    "mainstem_ptr": ("int64", 1),
    "mainstem_cells": ("int64", 1),
    "shared_face_cells": ("int64", 2),
}

#: Candidate fields cross-checked when present. These are the B1 spellings; an
#: absent field is reported once, never mapped onto an invented synonym.
CANDIDATE_FIELDS = ("root_world_xz", "member_sha256", "status", "reason_codes",
                    "physical_endpoint_evidence", "structural_only")

#: Candidate fields that are **mandatory** (the B1 spellings, no synonyms).
#: A package that omits one of these is refused, not merely noted: deleting a field
#: must never be a way past the check that field exists to carry — that is exactly
#: how a false physical claim could otherwise be hidden.
CANDIDATE_REQUIRED_FIELDS = (
    "candidate_id", "root_index", "root_cell", "root_world_xz", "root_kind",
    "member_count", "member_sha256", "status", "reason_codes",
    "physical_endpoint_evidence", "structural_only", "evidence_level",
    "mainstem_node_count", "mainstem_edges", "mainstem_sha256",
)

#: Grid-extent arrays whose NPY header must already equal the declared support.
GRID_ARRAYS = ("elevation_m", "resolved_mask", "receiver", "terminal_kind",
               "upstream_unknown_mask", "complete_mask", "upstream_cells",
               "owner_index")

#: The logical version of one candidate object and the declared owner rule. Both
#: enter ``candidate_id``, and the audit recomputes every ID from the public rule, so
#: a package cannot pass by carrying a well-formed but meaningless 64-character string.
LOGICAL_VERSION = "b1-structural-v1"
OWNER_RULE = (
    "one owner per valid cell: the structural terminal its receiver chain reaches; "
    "invalid cells carry -1; neighbouring owners share one canonical D4 world pair")
CANDIDATE_ALGORITHM = "metric-world-domain-candidate"

STATUS_CLOSED = "candidate_closed"
STATUS_OPEN = "candidate_open_upstream"
STATUS_TRUNCATED = "candidate_truncated"
STATUS_UNPREPARED = "unprepared"
STATUS_TOKENS = (STATUS_CLOSED, STATUS_OPEN, STATUS_TRUNCATED, STATUS_UNPREPARED)

PHYSICAL_TOKENS = ("none", "basin_pending", "lake_object", "ocean_outlet",
                   "endorheic_declared")
#: Tokens that assert physical endpoint evidence. A structural candidate holds no
#: bathymetry, stage, storage or outlet certification, so any of these is a false
#: physical claim in this layer.
PHYSICAL_CLAIM_TOKENS = ("lake_object", "ocean_outlet", "endorheic_declared")

#: The declared reason words this audit recomputes (producer's stable vocabulary).
REASON_COMPLETE = "complete"
REASON_UPSTREAM_UNKNOWN = "upstream_unknown"
REASON_SUPPORT_TRUNCATED = "support_truncated"

INCOMPLETE_REASONS = ("upstream_unknown", "support_truncated")

# --------------------------------------------------------------------------- #
# 0. refusals, independence guard, byte/JSON gates
# --------------------------------------------------------------------------- #
class AuditRefused(Exception):
    """A protocol violation: the audit is not allowed to answer."""

    def __init__(self, reason, detail=None):
        super().__init__(reason if detail is None else "%s: %s" % (reason, detail))
        self.reason = reason
        self.detail = detail


def loaded_banned_modules(modules=None):
    loaded = sys.modules if modules is None else modules
    return sorted(name for name in BANNED_MODULES if name in loaded)


def terrain_pipeline_imported(modules=None):
    loaded = sys.modules if modules is None else modules
    return sorted(name for name in loaded if name.split(".")[0] == "terrain_pipeline")


def require_independent_process(modules=None):
    """Refuse to audit inside a process that already loaded the tested code."""
    seen = loaded_banned_modules(modules)
    if seen:
        raise AuditRefused("independent_process_required",
                           "already imported: " + ", ".join(seen))


def array_sha256(value):
    """The declared arrays hash rule: shape, dtype.str, then C-order bytes."""
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(tuple(array.shape)).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def world_pair_sha256(pairs):
    """sha256 over signed int64 little-endian world ``(x, z)`` pairs, in order.

    The declared member/chain digest format: no packed key, no float coordinate,
    and the pair count is bound by the byte length. This is a re-implementation of
    the *declared rule*, not a call into the producer.
    """
    block = np.ascontiguousarray(np.asarray(pairs, np.int64).reshape(-1, 2), dtype="<i8")
    return hashlib.sha256(block.tobytes()).hexdigest()


def members_digest(member_cells, columns, origin_native_xz):
    """World-sorted member digest for one catchment, from local flat cells."""
    origin_x, origin_z = int(origin_native_xz[0]), int(origin_native_xz[1])
    cells = np.asarray(member_cells, np.int64).reshape(-1)
    rows, cols = np.divmod(cells, int(columns))
    world = np.stack([origin_x + cols, origin_z + rows], axis=1).astype(np.int64)
    order = np.lexsort((world[:, 1], world[:, 0])) if world.size else np.arange(0, dtype=np.int64)
    return world_pair_sha256(world[order])


def _reject_constant(value):
    raise AuditRefused("non_finite_json", value)


def _unique_pairs(pairs):
    parsed = {}
    for key, value in pairs:
        if key in parsed:
            raise AuditRefused("duplicate_json_key", key)
        parsed[key] = value
    return parsed


def read_strict_json(path, *, limit=MAX_MANIFEST_BYTES):
    """``stat`` and byte gate first, then a strict parse."""
    target = Path(path)
    if not target.is_file():
        raise AuditRefused("json_missing", str(target))
    size = target.stat().st_size
    if size > limit:
        raise AuditRefused("manifest_bytes_exceeded", "%d > %d" % (size, limit))
    raw = target.read_bytes()
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant,
                          object_pairs_hook=_unique_pairs)
    except UnicodeDecodeError as error:
        raise AuditRefused("manifest_not_utf8", str(error))
    except json.JSONDecodeError as error:
        raise AuditRefused("manifest_not_json", str(error))


def inspect_archive(path, *, max_bytes=MAX_ARRAYS_BYTES):
    """ZIP/NPY header gate: shape, dtype and byte totals before any allocation."""
    target = Path(path)
    if not target.is_file():
        raise AuditRefused("arrays_missing", str(target))
    size = target.stat().st_size
    if size > max_bytes:
        raise AuditRefused("arrays_bytes_exceeded", "%d > %d" % (size, max_bytes))
    headers = {}
    with open(target, "rb") as stream, zipfile.ZipFile(stream) as archive:
        members = archive.infolist()
        if not 1 <= len(members) <= MAX_ARRAY_MEMBERS:
            raise AuditRefused("invalid_npz", "member count %d" % len(members))
        if len({member.filename for member in members}) != len(members):
            raise AuditRefused("invalid_npz", "duplicate member names")
        total = 0
        for member in members:
            if not member.filename.endswith(".npy") or "/" in member.filename:
                raise AuditRefused("invalid_npz",
                                   "member is not a flat .npy: " + member.filename)
            with archive.open(member) as entry:
                version = np.lib.format.read_magic(entry)
                if version == (1, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(
                        entry, max_header_size=MAX_HEADER_BYTES)
                elif version == (2, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_2_0(
                        entry, max_header_size=MAX_HEADER_BYTES)
                else:
                    raise AuditRefused("invalid_npz", "unsupported NPY version")
                header_bytes = entry.tell()
            if dtype.hasobject:
                raise AuditRefused("object_dtype_rejected", member.filename)
            if fortran:
                raise AuditRefused("fortran_order_rejected", member.filename)
            if any(int(axis) < 0 for axis in shape):
                raise AuditRefused("invalid_npz", "negative axis in " + member.filename)
            payload = int(math.prod(shape)) * int(dtype.itemsize)
            if payload + header_bytes != member.file_size:
                raise AuditRefused(
                    "npy_header_size_mismatch",
                    "%s: shape %s dtype %s claims %d bytes, member holds %d"
                    % (member.filename, list(shape), dtype.str, payload + header_bytes,
                       member.file_size))
            total += member.file_size
            headers[member.filename[:-4]] = {
                "shape": tuple(int(axis) for axis in shape),
                "dtype": dtype,
                "nbytes": payload,
            }
    if total > MAX_TOTAL_ARRAY_BYTES:
        raise AuditRefused("array_budget_exceeded",
                           "%d > %d" % (total, MAX_TOTAL_ARRAY_BYTES))
    return headers


def load_arrays(path, headers):
    """Load with ``allow_pickle=False``; the header set must match exactly."""
    target = Path(path)
    with open(target, "rb") as stream, np.load(stream, allow_pickle=False) as archive:
        names = set(archive.files)
        if names != set(headers):
            raise AuditRefused("array_set_mismatch",
                               "headers %s vs archive %s" % (sorted(headers), sorted(names)))
        return {name: archive[name].copy() for name in archive.files}


# --------------------------------------------------------------------------- #
# 1. independent scalar references (declared rules only)
# --------------------------------------------------------------------------- #
def strict_graph_receiver(elevation_m, resolved_mask, *, origin_native_xz=(0, 0), world_seed=20261020):
    """Shared strict metric graph receiver; independent ledgers remain below."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    from terrain_pipeline.drainage import strict_receivers as strict_receivers
    bed = np.asarray(elevation_m, np.float64)
    mask = np.asarray(resolved_mask, bool)
    if bed.ndim != 2 or mask.shape != bed.shape:
        raise AuditRefused("array_shape_mismatch", "elevation/resolved shape")
    mesh = grid_mesh(bed.shape, x0_m=origin_native_xz[0] * 30.,
                     z0_m=origin_native_xz[1] * 30., world_seed=world_seed)
    return strict_receivers(bed, masked_mesh(mesh, mask), valid_mask=mask)[0].reshape(bed.shape)


def neighbourhood_complete(resolved_mask, *, origin_native_xz=(0, 0), world_seed=20261020):
    """True where the full source-frame graph neighborhood is resolved."""
    from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown
    mask = np.asarray(resolved_mask, bool)
    return mask & ~graph_support_unknown(mask, x0_m=origin_native_xz[0] * 30.,
        z0_m=origin_native_xz[1] * 30., world_seed=world_seed)


def upstream_unknown_seeds(resolved_mask, **frame):
    mask = np.asarray(resolved_mask, bool)
    return mask & ~neighbourhood_complete(mask, **frame)


def terminal_kind_reference(receiver, resolved_mask, **frame):
    """The declared terminal vocabulary, recomputed from graph support."""
    rec = np.asarray(receiver, np.int64)
    mask = np.asarray(resolved_mask, bool)
    complete = neighbourhood_complete(mask, **frame)
    kinds = np.full(mask.shape, "inactive", dtype="<U16")
    kinds[mask & (rec >= 0)] = "interior"
    terminal = mask & (rec < 0)
    kinds[terminal & complete] = "retained"
    kinds[terminal & ~complete] = "unknown_boundary"
    return kinds


def _validated_flat(receiver, resolved):
    rec = np.asarray(receiver, np.int64).reshape(-1)
    valid = np.asarray(resolved, bool).reshape(-1)
    n = rec.size
    if rec.size != valid.size:
        raise AuditRefused("array_shape_mismatch", "receiver/resolved size")
    if np.any(rec < -1) or np.any(rec >= n):
        raise AuditRefused("receiver_out_of_range", "flat index outside the window")
    if np.any(rec[~valid] != -1):
        raise AuditRefused("resolved_mask_mismatch", "an unresolved cell carries a receiver")
    index = np.arange(n, dtype=np.int64)
    if np.any(rec[valid] == index[valid]):
        raise AuditRefused("receiver_out_of_range", "self receiver")
    live = valid & (rec >= 0)
    if live.any() and not valid[rec[live]].all():
        raise AuditRefused("resolved_mask_mismatch", "receiver target is unresolved")
    return rec, valid


def walk_to_roots(receiver, resolved_mask):
    """Walk every cell along its receiver; returns terminal cell and upstream depth."""
    rec, valid = _validated_flat(receiver, resolved_mask)
    n = rec.size
    terminal = np.full(n, -1, np.int64)
    depth = np.full(n, -1, np.int64)
    for start in range(n):
        if not valid[start] or terminal[start] >= 0:
            continue
        path = []
        cell = start
        while True:
            path.append(cell)
            nxt = int(rec[cell])
            if nxt < 0:
                base_terminal, base_depth = cell, 0
                break
            if terminal[nxt] >= 0:
                base_terminal, base_depth = int(terminal[nxt]), int(depth[nxt]) + 1
                break
            cell = nxt
        for offset, node in enumerate(reversed(path)):
            terminal[node] = base_terminal
            depth[node] = base_depth + offset
    return terminal, depth


def accumulate_reference(receiver, resolved_mask, depth, **frame):
    """Inclusive upstream counts and the downstream unknown cone, level by level."""
    rec, valid = _validated_flat(receiver, resolved_mask)
    n = rec.size
    counts = np.where(valid, 1, 0).astype(np.int64)
    dirty = np.where(valid, upstream_unknown_seeds(resolved_mask, **frame).reshape(-1), False)
    order = np.flatnonzero(valid)
    order = order[np.argsort(-depth[order], kind="stable")]
    level_values = depth[order]
    boundaries = np.flatnonzero(np.diff(level_values) != 0) + 1
    for group in np.split(order, boundaries):
        if not group.size:
            continue
        targets = rec[group]
        live = targets >= 0
        if not live.any():
            continue
        np.add.at(counts, targets[live], counts[group[live]])
        np.logical_or.at(dirty, targets[live], dirty[group[live]])
    return counts, dirty, valid & ~dirty


def donor_csr(receiver, resolved_mask):
    """Donor lists per cell as CSR (offsets over all cells), for tie-breaks."""
    rec, valid = _validated_flat(receiver, resolved_mask)
    n = rec.size
    src = np.flatnonzero(valid & (rec >= 0))
    tgt = rec[src]
    order = np.argsort(tgt, kind="stable")
    cells = src[order]
    counts = np.bincount(tgt, minlength=n)
    start = np.zeros(n + 1, np.int64)
    np.cumsum(counts, out=start[1:])
    return start, cells


def world_xy(flat, columns, origin_x, origin_z):
    z, x = np.divmod(np.asarray(flat, np.int64), columns)
    return (origin_x + x).astype(np.int64), (origin_z + z).astype(np.int64)


def independent_mainstem(root, receiver, resolved_mask, upstream_cells,
                        origin_native_xz, donors=None):
    """Root-reverse chain: max donor ``upstream_cells``, tie by world ``(x, z)``.

    The tie-break is the declared one: among donors with the same contribution
    count, the smallest world ``(x, z)`` wins. Area is a selection policy, never a
    hydraulic claim, so this function does not look at slope or elevation.

    ``donors`` may carry an already-built CSR so that auditing many roots does
    not re-scan the whole graph once per root.
    """
    if donors is None:
        _validated_flat(receiver, resolved_mask)
    columns = int(np.asarray(receiver).shape[1])
    origin_x, origin_z = int(origin_native_xz[0]), int(origin_native_xz[1])
    up = np.asarray(upstream_cells, np.int64).reshape(-1)
    start, cells = donor_csr(receiver, resolved_mask) if donors is None else donors
    chain = [int(root)]
    current = int(root)
    while True:
        lo, hi = int(start[current]), int(start[current + 1])
        if hi <= lo:
            break
        candidates = cells[lo:hi]
        values = up[candidates]
        tied = candidates[values == values.max()]
        xs, zs = world_xy(tied, columns, origin_x, origin_z)
        current = int(tied[int(np.lexsort((zs, xs))[0])])
        if current in chain:
            raise AuditRefused("mainstem_cycle", "donor chain repeats a cell")
        chain.append(current)
    return np.asarray(chain[::-1], np.int64)


def shared_face_pairs(owner_index, resolved_mask, origin_native_xz):
    """D4 neighbour pairs with different owners, keyed by canonical world pair.

    A stored row is two *local flat* indices (the declared representation); the
    deduplication key is the world ``(x, z)`` pair, so relabelling or shifting the
    window cannot create a second copy of the same divide.
    """
    owner = np.asarray(owner_index, np.int64)
    mask = np.asarray(resolved_mask, bool)
    origin_x, origin_z = int(origin_native_xz[0]), int(origin_native_xz[1])
    rows, columns = owner.shape
    index = np.arange(rows * columns, dtype=np.int64).reshape(rows, columns)
    pairs = {}
    for dr, dc in NEIGHBOURS4:
        r1, c1 = rows - dr, columns - dc
        left = owner[0:r1, 0:c1]
        right = owner[dr:dr + r1, dc:dc + c1]
        both = mask[0:r1, 0:c1] & mask[dr:dr + r1, dc:dc + c1]
        hit = both & (left != right) & (left >= 0) & (right >= 0)
        for row, column in zip(*np.nonzero(hit)):
            first = (origin_x + int(column), origin_z + int(row))
            second = (origin_x + int(column + dc), origin_z + int(row + dr))
            flat = int(index[row, column])
            other = int(index[row + dr, column + dc])
            pairs[canonical_world_pair(first, second)] = (min(flat, other), max(flat, other))
    return pairs


def canonical_world_pair(first, second):
    a = (int(first[0]), int(first[1]))
    b = (int(second[0]), int(second[1]))
    return tuple(sorted((a, b)))


# --------------------------------------------------------------------------- #
# 2. the audit
# --------------------------------------------------------------------------- #
class Audit:
    """Collects named checks; a single failure keeps the already-recorded report."""

    def __init__(self):
        self.checks = []
        self.reasons = []
        self.notes = {}

    def check(self, name, passed, detail=None):
        passed = bool(passed)
        self.checks.append({"check": name, "passed": passed, "detail": detail})
        if not passed:
            self.reasons.append(name)
        return passed

    def note(self, name, detail):
        self.notes[name] = detail

    @property
    def status(self):
        return "PASS" if not self.reasons else "FAILED"


def _dtype_matches(dtype, declared):
    if declared == "unicode":
        return dtype.kind == "U"
    if declared == "bool":
        return dtype.kind == "b"
    if declared == "float64":
        return dtype.kind == "f" and dtype.itemsize == 8
    if declared == "int64":
        return dtype.kind == "i" and dtype.itemsize == 8
    raise AuditRefused("internal_contract", declared)


def audit_bundle(root, *, check_independence=True, modules=None):
    """Audit one prepared directory. Data problems are reported, not raised."""
    root = Path(root)
    report = {
        "schema": AUDIT_SCHEMA,
        "bundle_schema_expected": SCHEMA,
        "bundle": str(root),
        "status": "FAILED",
        "reasons": [],
        "checks": [],
        "notes": {},
        "independence": {
            "banned_modules": list(BANNED_MODULES),
            "banned_modules_loaded": [],
            "terrain_pipeline_loaded": [],
            "module": __name__,
        },
    }
    if check_independence:
        report["independence"]["terrain_pipeline_loaded"] = terrain_pipeline_imported(modules)
    audit = Audit()
    try:
        if check_independence:
            require_independent_process(modules)
        _audit_into(audit, root)
    except AuditRefused as refusal:
        audit.check(refusal.reason, False, refusal.detail)
    except Exception as error:                      # a crash is also a failed audit
        audit.check("audit_crashed", False,
                    {"type": type(error).__name__, "message": str(error)[:2000]})
    report["status"] = audit.status
    report["reasons"] = sorted(set(audit.reasons))
    report["checks"] = audit.checks
    report["notes"] = audit.notes
    report["counters"] = audit.notes.get("counters", {})
    report["scope"] = audit.notes.get("scope", {})
    report["independence"]["banned_modules_loaded"] = loaded_banned_modules(modules)
    report["independence"]["terrain_pipeline_loaded"] = terrain_pipeline_imported(modules)
    return report


def support_fields(support):
    """The one authoritative support record, plus the layout it came from.

    A package repeats support facts in several places (the bundle's
    ``support.metadata``, the envelope's ``metadata.support``, and ``declaration``).
    Trusting whichever copy happens to carry ``origin_native_xz`` is how a single
    edited duplicate slipped past: the audit read one copy while the arrays were
    bound to another. So this function returns **one** authoritative record and the
    caller binds every other copy to it field by field (``bind_support_copies``); no
    place is ever trusted on its own.

    Authority order is declared, not discovered: the bundle's own ``support.metadata``
    (the ``support_plan`` return shape) wins, then a flattened top-level record. Any
    other copy must agree with it.
    """
    if not isinstance(support, dict):
        raise AuditRefused("support_missing", "manifest has no support record")
    nested = support.get("metadata")
    if isinstance(nested, dict) and nested:
        return nested, "support.metadata"
    flattened = {key: support[key] for key in SUPPORT_BOUND_FIELDS if key in support}
    if flattened:
        return flattened, "support"
    raise AuditRefused("support_record_invalid",
                       "no support metadata under support.metadata and no flattened "
                       "support fields at the top level")


def support_copies(manifest):
    """Every place this package repeats support facts, labelled.

    Returning all of them (instead of the first that parses) is what makes a
    disagreement a refusal rather than a silent choice.
    """
    copies = []
    support = manifest.get("support")
    if isinstance(support, dict):
        nested = support.get("metadata")
        if isinstance(nested, dict) and nested:
            copies.append(("support.metadata", nested))
        flattened = {key: support[key] for key in SUPPORT_BOUND_FIELDS if key in support}
        if flattened:
            copies.append(("support", flattened))
    metadata = manifest.get("metadata")
    if isinstance(metadata, dict):
        declared = metadata.get("support")
        if isinstance(declared, dict) and declared:
            copies.append(("metadata.support", declared))
    declaration = manifest.get("declaration")
    if isinstance(declaration, dict):
        flattened = {key: declaration[key] for key in SUPPORT_BOUND_FIELDS
                     if key in declaration}
        if flattened:
            copies.append(("declaration", flattened))
    return copies


def bind_support_copies(audit, manifest, authoritative):
    """Bind every repeated support copy to the authoritative record, field by field.

    Only fields that actually appear in a copy are compared: a place that simply does
    not repeat a fact is not a disagreement. Fields that *do* appear must match
    exactly -- no tolerance and no "close enough" on a plan -- including the derived
    ranges, the cell count, the page SHA list and the seed/spacing/plan version.
    """
    for label, copy in support_copies(manifest):
        if copy is authoritative:
            continue
        compared = sorted(key for key in copy if key in SUPPORT_BOUND_FIELDS)
        differences = []
        for key in compared:
            if key not in authoritative:
                differences.append({"field": key,
                                    "problem": "missing_in_authoritative"})
                continue
            if _support_value(copy[key]) != _support_value(authoritative[key]):
                differences.append({"field": key, "copy": copy[key],
                                    "authoritative": authoritative[key]})
        audit.check("support_copy_mismatch", not differences,
                    {"copy": label, "compared": compared, "differences": differences})


def _support_value(value):
    """Normalise a support value for exact comparison (tuples vs lists, int vs float)."""
    if isinstance(value, (list, tuple)):
        return [_support_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _support_value(value[key]) for key in sorted(value)}
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return value




def _audit_into(audit, root):
    """Header-first: nothing is allocated before the declared budget is checked.

    Order matters for a refusal: the strict manifest is parsed, the support record is
    read, the NPY headers are inspected, and **only then** are any arrays loaded. A
    package that declares too many cells, or whose headers disagree with the declared
    support or with each other, is refused without allocating its payload.
    """
    manifest = read_strict_json(root / MANIFEST_NAME)
    audit.check("schema_mismatch", manifest.get("schema") == SCHEMA, manifest.get("schema"))
    support = manifest.get("support")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise AuditRefused("metadata_missing", "manifest has no metadata record")
    authoritative, layout = support_fields(support)
    audit.note("support_record_layout", layout)
    # One authority first, then every repeated copy is bound to it field by field, so
    # a tampered duplicate can never be the copy the arrays are read against.
    audit.note("support_copies_found", [label for label, _c in support_copies(manifest)])
    bind_support_copies(audit, manifest, authoritative)
    origin_from_authority = authoritative["origin_native_xz"]
    shape_from_authority = authoritative["shape_zx"]
    for name, value in (("origin_native_xz", origin_from_authority),
                        ("shape_zx", shape_from_authority)):
        if (not isinstance(value, list) or len(value) != 2
                or not all(isinstance(item, int) and not isinstance(item, bool)
                           for item in value)):
            raise AuditRefused("support_record_invalid", "%s=%r" % (name, value))
    rows, columns = int(shape_from_authority[0]), int(shape_from_authority[1])
    if min(rows, columns) < 2:
        raise AuditRefused("support_record_invalid",
                           "shape %r below 2x2" % (shape_from_authority,))
    cells = rows * columns

    # The declared plan rules, checked on the authority (not on a copy): the 30 m
    # lattice, the frozen world seed, a positive integer plan version, a cell count
    # equal to shape[0]*shape[1], and a range_native derived from origin+shape.
    audit.check("support_spacing_not_30m",
                _support_value(authoritative.get("spacing_m")) == SPACING_M,
                authoritative.get("spacing_m"))
    audit.check("support_world_seed_mismatch",
                authoritative.get("world_seed") == WORLD_SEED,
                authoritative.get("world_seed"))
    plan_version = authoritative.get("plan_version")
    audit.check("support_plan_version_invalid",
                isinstance(plan_version, int) and not isinstance(plan_version, bool)
                and plan_version >= 1, plan_version)
    declared_cells = authoritative.get("support_cells")
    if declared_cells is not None:
        audit.check("support_cells_mismatch", declared_cells == cells,
                    {"declared": declared_cells, "shape_product": cells})
    declared_range = authoritative.get("range_native")
    if isinstance(declared_range, dict):
        expected_range = {
            "x": [int(origin_from_authority[0]),
                  int(origin_from_authority[0]) + columns - 1],
            "z": [int(origin_from_authority[1]),
                  int(origin_from_authority[1]) + rows - 1],
        }
        audit.check("support_range_mismatch",
                    _support_value(declared_range) == expected_range,
                    {"declared": declared_range, "expected": expected_range})

    # Budget first, against the *declared* support and the header byte totals.
    audit.check("cell_budget_exceeded", cells <= MAX_SUPPORT_CELLS,
                {"cells": cells, "declared_max_cells": MAX_SUPPORT_CELLS})
    if cells > MAX_SUPPORT_CELLS:
        raise AuditRefused("cell_budget_exceeded", "%d > %d" % (cells, MAX_SUPPORT_CELLS))
    headers = inspect_archive(root / ARRAYS_NAME)
    audit.check("header_cell_budget_exceeded",
                sum(header["nbytes"] for header in headers.values()) <= MAX_TOTAL_ARRAY_BYTES,
                {"declared_cells": cells})

    # Header contract: names, dtypes, ranks, the support shape and the size relations
    # that can be checked without reading a single value.
    for name, (declared, ndim) in REQUIRED_ARRAYS.items():
        header = headers.get(name)
        if header is None:
            continue
        audit.check("array_dtype_mismatch", _dtype_matches(header["dtype"], declared),
                    {"array": name, "dtype": header["dtype"].str, "expected": declared})
        audit.check("array_rank_mismatch", len(header["shape"]) == ndim,
                    {"array": name, "shape": list(header["shape"]), "rank": ndim})
    missing = sorted(set(REQUIRED_ARRAYS) - set(headers))
    audit.check("array_missing", not missing, missing)
    if missing:
        raise AuditRefused("array_missing", missing)
    unknown = sorted(set(headers) - set(REQUIRED_ARRAYS))
    audit.check("array_unexpected", not unknown, unknown)

    for name in GRID_ARRAYS:
        audit.check("header_grid_shape_mismatch",
                    headers[name]["shape"] == (rows, columns),
                    {"array": name, "header": list(headers[name]["shape"]),
                     "declared": [rows, columns]})
    roots = headers["root_cells"]["shape"][0]
    audit.check("header_root_count_invalid",
                roots >= 1 and roots <= cells,
                {"root_cells": roots, "cells": cells})
    for name in ("root_complete", "member_counts"):
        audit.check("header_root_arrays_length_mismatch",
                    headers[name]["shape"][0] == roots,
                    {"array": name, "length": headers[name]["shape"][0], "roots": roots})
    for name in ("member_ptr", "mainstem_ptr"):
        audit.check("header_pointer_length_mismatch",
                    headers[name]["shape"][0] == roots + 1,
                    {"array": name, "length": headers[name]["shape"][0], "roots": roots})
    audit.check("header_member_cells_over_budget",
                headers["member_cells"]["shape"][0] <= cells,
                {"member_cells": headers["member_cells"]["shape"][0], "cells": cells})
    audit.check("header_mainstem_cells_over_budget",
                headers["mainstem_cells"]["shape"][0] <= cells,
                {"mainstem_cells": headers["mainstem_cells"]["shape"][0], "cells": cells})
    faces = headers["shared_face_cells"]["shape"]
    audit.check("header_shared_face_shape_invalid",
                len(faces) == 2 and faces[1] == 2,
                {"shared_face_cells": list(faces)})
    if any(check["passed"] is False for check in audit.checks
           if check["check"].startswith("header_")):
        raise AuditRefused("header_contract_violated",
                           "the NPY headers contradict the declared support or each other; "
                           "no array was loaded")

    arrays = load_arrays(root / ARRAYS_NAME, headers)

    elevation = arrays["elevation_m"]
    resolved = arrays["resolved_mask"]
    audit.check("resolved_mask_empty", bool(resolved.any()), int(resolved.sum()))
    # The declared unresolved convention, both directions: an unresolved cell keeps NaN
    # and a resolved cell is finite. A package that *filled* a hole with 0.0 (or left a
    # NaN inside the resolved set) is refused rather than quietly accepted.
    unresolved = ~resolved
    nan = np.isnan(elevation)
    audit.check("unresolved_elevation_not_nan",
                bool(np.array_equal(nan, unresolved)),
                {"nan_cells": int(nan.sum()), "unresolved_cells": int(unresolved.sum()),
                 "nan_but_resolved": int((nan & resolved).sum()),
                 "unresolved_but_not_nan": int((unresolved & ~nan).sum())})
    # An explicit input gate, not a side effect of the graph differing: a resolved cell
    # must be *finite*. NaN equality above already covers NaN; +-inf is refused here,
    # so a hole filled with inf (or a resolved inf) fails on the input contract itself.
    resolved_values = elevation[resolved]
    audit.check("resolved_elevation_not_finite",
                bool(np.isfinite(resolved_values).all()),
                {"resolved_cells": int(resolved.sum()),
                 "nonfinite_resolved": int((~np.isfinite(resolved_values)).sum())})
    for name, value in arrays.items():
        if value.dtype.kind == "f" and name != "elevation_m":
            audit.check("non_finite_array", bool(np.isfinite(value).all()), name)

    records = manifest.get("arrays")
    audit.check("arrays_record_missing", isinstance(records, dict), type(records).__name__)
    if isinstance(records, dict):
        audit.check("arrays_record_set_mismatch",
                    sorted(records) == sorted(headers),
                    {"manifest": sorted(records), "npz": sorted(headers)})
        for name in sorted(headers):
            record = records.get(name)
            if not isinstance(record, dict):
                audit.check("arrays_record_missing", False, name)
                continue
            audit.check("arrays_sha_mismatch",
                        record.get("sha256") == array_sha256(arrays[name]),
                        {"array": name,
                         "rule": "sha256(shape, dtype.str, C-order bytes)"})
            audit.check("arrays_shape_mismatch",
                        tuple(record.get("shape", ())) == headers[name]["shape"],
                        {"array": name, "manifest": record.get("shape"),
                         "header": list(headers[name]["shape"])})
            audit.check("arrays_dtype_mismatch",
                        str(record.get("dtype")) == headers[name]["dtype"].str,
                        {"array": name, "manifest": record.get("dtype"),
                         "header": headers[name]["dtype"].str})

    binding = manifest.get("source_binding")
    audit.check("source_binding_invalid", _binding_ok(binding),
                None if not isinstance(binding, dict) else binding.get("kind"))
    audit.note("source_binding_scope",
               "the page SHA256 list is a content binding recorded by prepare, not a "
               "signature; the external pin list plus the real page read are the "
               "source boundary")
    audit.check("identity_digest_missing",
                isinstance(manifest.get("identity_sha256"), str)
                and len(manifest["identity_sha256"]) == 64, None)
    audit.note("identity_digest_scope",
               "the producer's JSON bundle identity is recorded but not recomputed here: "
               "this audit re-derives the graph, membership, completeness, chains and "
               "candidate IDs from the arrays instead")

    _audit_graph(audit, manifest, support, arrays,
                 (origin_from_authority, shape_from_authority))


def _binding_ok(binding):
    if not isinstance(binding, dict):
        return False
    if binding.get("kind") != "content_binding_not_signature":
        return False
    records = binding.get("page_records")
    if not isinstance(records, list) or not records:
        return False
    for item in records:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("path"), str) or not item["path"]:
            return False
        sha = item.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            return False
        if any(character not in "0123456789abcdef" for character in sha):
            return False
    return True


def _audit_graph(audit, manifest, support, arrays, origin_and_shape):
    origin, shape = origin_and_shape
    rows, columns = shape
    origin_x, origin_z = int(origin[0]), int(origin[1])
    elevation = arrays["elevation_m"]
    resolved = arrays["resolved_mask"]
    receiver = arrays["receiver"]
    terminal_kind = arrays["terminal_kind"]
    seeds = arrays["upstream_unknown_mask"]
    complete = arrays["complete_mask"]
    upstream_cells = arrays["upstream_cells"]
    owner = arrays["owner_index"]
    root_cells = arrays["root_cells"]
    root_complete = arrays["root_complete"]
    member_counts = arrays["member_counts"]
    member_ptr = arrays["member_ptr"]
    member_cells = arrays["member_cells"]
    mainstem_ptr = arrays["mainstem_ptr"]
    mainstem_cells = arrays["mainstem_cells"]
    shared_faces = arrays["shared_face_cells"]

    valid_flat = resolved.reshape(-1)
    n_valid = int(valid_flat.sum())
    rec, _ = _validated_flat(receiver, resolved)

    frame = {"origin_native_xz": origin, "world_seed": WORLD_SEED}
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    mesh = grid_mesh(shape, x0_m=origin_x * SPACING_M, z0_m=origin_z * SPACING_M,
                     dx_m=SPACING_M, world_seed=WORLD_SEED)
    reference_receiver = strict_graph_receiver(elevation, resolved, **frame)
    audit.check("receiver_mismatch", np.array_equal(reference_receiver, receiver),
                {"mismatch_cells": int((reference_receiver != receiver).sum())})
    reference_seeds = upstream_unknown_seeds(resolved, **frame)
    audit.check("unknown_seed_mismatch", np.array_equal(reference_seeds, seeds),
                {"declared": int(seeds.sum()), "recomputed": int(reference_seeds.sum())})
    reference_kinds = terminal_kind_reference(receiver, resolved, **frame)
    audit.check("terminal_kind_mismatch", np.array_equal(reference_kinds, terminal_kind),
                {"mismatch_cells": int((reference_kinds != terminal_kind).sum())})

    terminal, depth = walk_to_roots(receiver, resolved)
    counts, _dirty, reference_complete = accumulate_reference(receiver, resolved, depth, **frame)
    audit.check("complete_mask_mismatch",
                np.array_equal(reference_complete.reshape(shape),
                               complete.reshape(shape)),
                {"declared_complete": int(complete.sum()),
                 "recomputed_complete": int(reference_complete.sum()),
                 "difference_cells": int((reference_complete.reshape(shape)
                                          != complete.reshape(shape)).sum())})
    audit.check("upstream_cells_mismatch",
                np.array_equal(counts.reshape(shape), upstream_cells),
                {"difference_cells": int((counts.reshape(shape) != upstream_cells).sum())})

    root_count = int(root_cells.size)
    audit.check("root_arrays_length_mismatch",
                root_complete.size == root_count and member_counts.size == root_count,
                {"root_cells": root_count, "root_complete": int(root_complete.size),
                 "member_counts": int(member_counts.size)})
    audit.check("member_ptr_length_mismatch", member_ptr.size == root_count + 1, int(member_ptr.size))
    audit.check("mainstem_ptr_length_mismatch", mainstem_ptr.size == root_count + 1,
                int(mainstem_ptr.size))
    if (member_ptr.size != root_count + 1 or mainstem_ptr.size != root_count + 1
            or root_complete.size != root_count):
        raise AuditRefused("pointer_length_mismatch",
                           "member_ptr %d / mainstem_ptr %d / root_complete %d for %d roots"
                           % (member_ptr.size, mainstem_ptr.size, root_complete.size, root_count))
    audit.check("root_duplicate", len(set(int(cell) for cell in root_cells)) == root_count, None)
    audit.check("root_not_valid", bool(np.all(valid_flat[root_cells])), None)
    audit.check("root_not_terminal", bool(np.all(terminal[root_cells] == root_cells)),
                {"non_terminal_roots": int((terminal[root_cells] != root_cells).sum())})
    root_row, root_column = np.divmod(root_cells, columns)
    world_x = (root_column + origin_x).astype(np.int64)
    world_z = (root_row + origin_z).astype(np.int64)
    audit.check("root_order_mismatch",
                np.array_equal(np.lexsort((world_z, world_x)), np.arange(root_count)),
                "roots must be ordered by world (x, z)")

    owner_flat = owner.reshape(-1)
    root_slot = {int(cell): slot for slot, cell in enumerate(root_cells)}
    expected_owner = np.full(rec.size, -1, np.int64)
    owned_cells = np.flatnonzero(valid_flat)
    mapped = np.array([root_slot.get(int(terminal[cell]), -1) for cell in owned_cells], np.int64)
    expected_owner[owned_cells] = mapped
    audit.check("owner_mismatch", np.array_equal(expected_owner, owner_flat),
                {"mismatch_cells": int((expected_owner != owner_flat).sum())})
    audit.check("owner_gap", bool(np.all(owner_flat[valid_flat] >= 0)),
                {"unowned_valid_cells": int((owner_flat[valid_flat] < 0).sum())})
    audit.check("owner_overlap", bool(np.all((owner_flat >= 0) <= valid_flat)),
                {"invalid_cells_with_owner": int(((owner_flat >= 0) & ~valid_flat).sum())})
    audit.check("owner_index_range",
                bool(np.all(owner_flat >= -1)) and bool(np.all(owner_flat < max(root_count, 1))), None)
    audit.check("root_unowned",
                bool(np.all(owner_flat[root_cells] == np.arange(root_count))),
                "each root cell must be owned by its own candidate")

    audit.check("member_ptr_not_monotone", bool(np.all(np.diff(member_ptr) >= 0)), None)
    audit.check("mainstem_ptr_not_monotone", bool(np.all(np.diff(mainstem_ptr) >= 0)), None)
    audit.check("member_total_mismatch",
                int(member_ptr[-1]) == int(member_cells.size) == n_valid,
                {"member_ptr_last": int(member_ptr[-1]),
                 "member_cells": int(member_cells.size), "valid_cells": n_valid})
    audit.check("member_count_mismatch", np.array_equal(np.diff(member_ptr), member_counts), None)
    audit.check("member_cells_range",
                bool(member_cells.size == 0
                     or (member_cells.min() >= 0 and member_cells.max() < rec.size)), None)
    audit.check("member_cells_duplicate",
                member_cells.size == np.unique(member_cells).size, None)

    donors = donor_csr(receiver, resolved)
    start, donor_cells = donors
    # Member sets, vectorised: every declared member must be owned by exactly its
    # candidate slot. Together with the total, range and duplicate checks above
    # (which make the member list a bijection onto the valid cells), per-member
    # owner equality is exactly set equality -- no per-root scan of the grid.
    member_sets_match = True
    if member_cells.size:
        member_index = member_cells.astype(np.int64)
        expected_slot = np.repeat(np.arange(root_count, dtype=np.int64),
                                  np.diff(member_ptr).astype(np.int64))
        member_sets_match = bool(np.array_equal(owner_flat[member_index], expected_slot))
    tributary_total = 0
    mainstem_lengths = []
    mainstem_match = True
    chain_contiguous = True
    chain_descending = True
    chain_starts_at_source = True
    # The declared member/mainstem digests, recomputed once and reused by the
    # candidate cross-check below.
    member_digests = []
    stem_digests = []
    for slot in range(root_count):
        member_digests.append(members_digest(
            member_cells[int(member_ptr[slot]):int(member_ptr[slot + 1])],
            columns, (origin_x, origin_z)))
        chan_lo, chan_hi = int(mainstem_ptr[slot]), int(mainstem_ptr[slot + 1])
        chain = mainstem_cells[chan_lo:chan_hi].astype(np.int64)
        chain_rows, chain_cols = np.divmod(chain, columns)
        stem_world = (np.stack([origin_x + chain_cols, origin_z + chain_rows], axis=1)
                      .astype(np.int64))
        stem_digests.append(world_pair_sha256(stem_world))
        mainstem_lengths.append(int(chain.size))
        reference = independent_mainstem(int(root_cells[slot]), receiver, resolved,
                                         upstream_cells, (origin_x, origin_z), donors)
        if not np.array_equal(reference, chain) or chain.size == 0:
            mainstem_match = False
            continue
        if int(chain[-1]) != int(root_cells[slot]):
            mainstem_match = False
            continue
        if chain.size > 1:
            if not np.array_equal(rec[chain[:-1]], chain[1:]):
                chain_contiguous = False
            if any(target not in mesh.indices[mesh.indptr[source]:mesh.indptr[source + 1]]
                   for source, target in zip(chain[:-1], chain[1:])):
                chain_contiguous = False
            if not np.all(np.diff(elevation.reshape(-1)[chain]) < 0.0):
                chain_descending = False
        head = int(chain[0])
        if int(start[head + 1]) - int(start[head]) != 0:
            chain_starts_at_source = False
    if mainstem_cells.size:
        stem_donors = np.diff(start)[mainstem_cells.astype(np.int64)]
        tributary_total = int(stem_donors.sum()) - (int(mainstem_cells.size) - root_count)

    audit.check("member_set_mismatch", member_sets_match,
                "each candidate's member set must equal its owner catchment exactly")
    audit.check("mainstem_chain_mismatch", mainstem_match,
                "chain rebuilt from the root by max donor upstream_cells, world (x, z) tie-break")
    audit.check("mainstem_not_contiguous", chain_contiguous, None)
    audit.check("mainstem_not_descending", chain_descending, None)
    audit.check("mainstem_head_not_source", chain_starts_at_source,
                "a mainstem must start at a donor-free source cell")
    # Branch counting, defined so it cannot be misread: a *branch cell* is a mainstem
    # cell with two or more donors. That is a confluence count, NOT a count of
    # independent tributaries, and the two are reported under separate names.
    branch_cells = 0
    if mainstem_cells.size:
        stem_donors = np.diff(start)[mainstem_cells.astype(np.int64)]
        branch_cells = int(np.count_nonzero(stem_donors >= 2))

    # Path length of each mainstem chain, summed over its own hops.
    # Sum actual representative-node metric lengths along each ordered chain.
    chain_lengths_m = []
    chain_lower_bounds_m = []
    for slot in range(root_count):
        chan_lo, chan_hi = int(mainstem_ptr[slot]), int(mainstem_ptr[slot + 1])
        chain = mainstem_cells[chan_lo:chan_hi].astype(np.int64)
        if chain.size < 2:
            chain_lengths_m.append(0.0)
            chain_lower_bounds_m.append(0.0)
            continue
        dx = np.diff(mesh.node_x_m[chain])
        dz = np.diff(mesh.node_z_m[chain])
        chain_lengths_m.append(float(np.hypot(dx, dz).sum()))
        chain_lower_bounds_m.append(float((chain.size - 1) * mesh.edge_length_m.min()))

    complete_flat = complete.reshape(-1)
    recomputed_root_complete = np.array(
        [bool(reference_complete[int(cell)]) for cell in root_cells], bool)
    audit.check("root_complete_mismatch", np.array_equal(recomputed_root_complete, root_complete),
                {"declared": int(root_complete.sum()),
                 "recomputed": int(recomputed_root_complete.sum())})
    if member_cells.size:
        incomplete_members = np.add.reduceat(
            (~complete_flat[member_cells.astype(np.int64)]).astype(np.int64),
            member_ptr[:-1].astype(np.int64))
    else:
        incomplete_members = np.zeros(root_count, np.int64)
    whole_catchment = incomplete_members == 0
    audit.check("root_complete_not_whole_catchment",
                np.array_equal(whole_catchment, root_complete),
                "root_complete must hold exactly when every member cell is complete")

    declared_pairs = {}
    pairs_canonical = True
    pairs_d4 = True
    if shared_faces.ndim == 2 and shared_faces.shape[1] == 2:
        for first, second in shared_faces:
            first, second = int(first), int(second)
            if not (0 <= first < rec.size and 0 <= second < rec.size):
                pairs_canonical = False
                continue
            ax, az = world_xy(np.asarray([first]), columns, origin_x, origin_z)
            bx, bz = world_xy(np.asarray([second]), columns, origin_x, origin_z)
            a = (int(ax[0]), int(az[0]))
            b = (int(bx[0]), int(bz[0]))
            pair = canonical_world_pair(a, b)
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
                pairs_d4 = False
            if int(owner_flat[first]) == int(owner_flat[second]):
                pairs_d4 = False
            if not (valid_flat[first] and valid_flat[second]):
                pairs_d4 = False
            # The stored row is two local flat indices in canonical *world* order,
            # so a row naming the same world cells the other way round is a
            # representation slip, not a second divide.
            if first != min(first, second):
                pairs_canonical = False
            if pair in declared_pairs:
                pairs_canonical = False
            declared_pairs[pair] = (min(first, second), max(first, second))
    else:
        audit.check("array_shape_mismatch", False, {"array": "shared_face_cells"})
    reference_pairs = shared_face_pairs(owner, resolved, (origin_x, origin_z))
    audit.check("shared_face_pair_order_invalid", pairs_canonical,
                "each row is one canonical world (x, z) pair, listed once")
    audit.check("shared_face_not_d4", pairs_d4, None)
    reference_keys = set(reference_pairs)
    declared_keys = set(declared_pairs)
    audit.check("shared_face_mismatch", declared_keys == reference_keys,
                {"declared": len(declared_keys), "recomputed": len(reference_keys),
                 "missing": len(reference_keys - declared_keys),
                 "extra": len(declared_keys - reference_keys)})
    audit.check("shared_face_cells_mismatch",
                all(reference_pairs[key] == declared_pairs[key]
                    for key in declared_keys & reference_keys),
                "the two local flat cells of each pair must be the same cells")
    live_cells = valid_flat & (rec >= 0)
    crossing_owners = owner_flat[np.where(live_cells, rec, 0)]
    cross = int(np.count_nonzero(live_cells & (crossing_owners != owner_flat)))
    audit.check("cross_domain_drain", cross == 0, {"crossing_cells": cross})

    kinds = terminal_kind.reshape(-1)
    census = {label: int((kinds == label).sum())
              for label in ("interior", "inactive", "retained", "unknown_boundary",
                            "open_outflow")}
    audit.check("open_outflow_present", census["open_outflow"] == 0,
                "no outlet certification exists in this stage")
    statuses = _audit_candidates(audit, manifest, root_count, world_x, world_z,
                                 root_complete, member_ptr, member_cells, kinds,
                                 root_cells, reference_complete, mainstem_ptr,
                                 mainstem_cells, columns, (origin_x, origin_z),
                                 member_digests, stem_digests)

    longest = max(mainstem_lengths) if mainstem_lengths else 0
    longest_slot = int(np.argmax(mainstem_lengths)) if mainstem_lengths else -1
    complete_lengths = [length for slot, length in enumerate(mainstem_lengths)
                        if bool(root_complete[slot])]
    longest_complete = max(complete_lengths) if complete_lengths else 0
    longest_complete_slot = -1
    if complete_lengths:
        longest_complete_slot = max((slot for slot in range(root_count)
                                     if bool(root_complete[slot])),
                                    key=lambda slot: (mainstem_lengths[slot], -slot))
    audit.note("counters", {
        "support_cells": int(rows * columns),
        "resolved_cells": n_valid,
        "unresolved_cells": int(rows * columns - n_valid),
        "roots": root_count,
        "roots_complete": int(root_complete.sum()),
        "roots_open_upstream": int((~root_complete).sum()),
        "roots_truncated": int(np.sum((~root_complete)
                                      & (kinds[root_cells] == "unknown_boundary"))),
        "terminal_census": census,
        "unknown_seed_cells": int(reference_seeds.sum()),
        "unknown_pending_cells": int((~reference_complete).sum()),
        "member_cells_total": int(member_cells.size),
        "mainstem_cells_total": int(mainstem_cells.size),
        "longest_mainstem_cells": int(longest),
        "longest_complete_mainstem_cells": int(longest_complete),
        "longest_mainstem_root_world_xz": (
            [int(world_x[longest_slot]), int(world_z[longest_slot])]
            if longest_slot >= 0 else None),
        "longest_complete_mainstem_root_world_xz": (
            [int(world_x[longest_complete_slot]), int(world_z[longest_complete_slot])]
            if longest_complete_slot >= 0 else None),
        "longest_complete_mainstem_nodes": int(longest_complete),
        "longest_complete_mainstem_edges": int(max(longest_complete - 1, 0)),
        "longest_complete_mainstem_path_length_m": (
            chain_lengths_m[longest_complete_slot]
            if longest_complete_slot >= 0 else 0.0),
        "longest_complete_mainstem_step_count_lower_bound_m": (
            chain_lower_bounds_m[longest_complete_slot]
            if longest_complete_slot >= 0 else 0.0),
        "longest_mainstem_path_length_m": (
            chain_lengths_m[longest_slot] if longest_slot >= 0 else 0.0),
        "mainstem_branch_cells": int(branch_cells),
        "count_units": {
            "mainstem_cells": "nodes (cell count, one per mainstem cell)",
            "longest_complete_mainstem_cells": "nodes",
            "longest_complete_mainstem_edges": "edges (nodes - 1)",
            "longest_complete_mainstem_path_length_m": (
                "metres summed along source-frame representative-node graph edges; "
                "this is routing geometry, not a refined channel centreline"),
            "longest_complete_mainstem_step_count_lower_bound_m": (
                "edge count multiplied by the minimum source graph edge length; "
                "a conservative lower bound, not path or straight-line distance"),
            "mainstem_branch_cells": (
                "mainstem cells whose donor count is >= 2 (a confluence cell count). "
                "This is NOT a count of independent tributaries: a tributary is not "
                "enumerated in this layer at all"),
        },
        "shared_face_pairs": len(declared_pairs),
        "cross_domain_drain_cells": cross,
    })
    audit.note("scope", {
        "full_support": True,
        "sampled": False,
        "cells_visited": int(rec.size),
        "roots_visited": root_count,
        "statement": ("every cell of the declared support window and every root was "
                      "visited; nothing was sampled and no scope was truncated"),
    })
    audit.note("candidate_status_counts", statuses)
    audit.note("evidence_level", "structural_candidate")
    audit.note("not_certified",
               "this certificate covers irregular-graph structural integrity of the given "
               "original bed only; physical endpoints are not certified, basin_pending "
               "stays pending, and nothing here is a production default")


def expected_status(slot, root_complete, kinds, root_cells):
    """The declared status/terminal-kind relation, recomputed from the arrays.

    A complete catchment can only be ``candidate_closed``; an incomplete one is
    ``candidate_truncated`` when its root sits on the support cut
    (``unknown_boundary``) and ``candidate_open_upstream`` otherwise.
    ``unprepared`` is never a property of a delivered package.
    """
    if bool(root_complete[slot]):
        return STATUS_CLOSED
    kind = str(kinds[int(root_cells[slot])])
    if kind == "unknown_boundary":
        return STATUS_TRUNCATED
    if kind == "retained":
        return STATUS_OPEN
    return None


def expected_reason_codes(status):
    """The declared reason list for one recomputed status (order-insensitive)."""
    return {
        STATUS_CLOSED: [REASON_COMPLETE],
        STATUS_TRUNCATED: [REASON_SUPPORT_TRUNCATED, REASON_UPSTREAM_UNKNOWN],
        STATUS_OPEN: [REASON_UPSTREAM_UNKNOWN],
    }.get(status, [])


def _audit_candidates(audit, manifest, root_count, world_x, world_z, root_complete,
                      member_ptr, member_cells, kinds, root_cells, reference_complete,
                      mainstem_ptr, mainstem_cells, columns, origin_native_xz,
                      member_digests, stem_digests):
    """Cross-check candidate records against the arrays, field by field.

    A **missing** mandatory field is a refusal, not a note: the field is checked whether
    or not the producer felt like emitting it, so removing ``physical_endpoint_evidence``
    (or ``structural_only``, or ``candidate_id``) can never be a way past the check it
    carries. Every value that can be re-derived from the arrays is re-derived, including
    the logical candidate ID by the public rule in ``candidate_id_payload``.
    """
    candidates = manifest.get("candidates")
    audit.check("candidates_missing",
                isinstance(candidates, list) and len(candidates) == root_count,
                {"candidates": len(candidates) if isinstance(candidates, list) else None,
                 "roots": root_count})
    statuses = {token: 0 for token in STATUS_TOKENS}
    if not isinstance(candidates, list) or len(candidates) != root_count:
        return statuses
    metadata = manifest.get("metadata") or {}
    declared = {
        "world_seed": metadata.get("support", {}).get("world_seed") if isinstance(
            metadata.get("support"), dict) else None,
        "spacing_m": (metadata.get("support") or {}).get("spacing_m")
        if isinstance(metadata.get("support"), dict) else None,
        "plan_version": (metadata.get("support") or {}).get("plan_version")
        if isinstance(metadata.get("support"), dict) else None,
        "logical_version": metadata.get("logical_version"),
        "owner_rule": metadata.get("owner_rule"),
    }
    audit.check("metadata_logical_version_mismatch",
                declared["logical_version"] == LOGICAL_VERSION, declared["logical_version"])
    audit.check("metadata_owner_rule_mismatch",
                declared["owner_rule"] == OWNER_RULE,
                "the owner rule is part of candidate_id, so a different rule is a "
                "different object")
    for key in ("world_seed", "spacing_m", "plan_version"):
        audit.check("metadata_support_field_missing:%s" % key,
                    declared[key] is not None, declared[key])

    digest_checked = 0
    for slot, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            audit.check("candidate_not_object", False, slot)
            continue
        missing = [field for field in CANDIDATE_REQUIRED_FIELDS if field not in candidate]
        audit.check("candidate_field_missing", not missing,
                    {"candidate": slot, "missing": missing})
        if missing:
            # Keep checking what is present, but the package is already refused.
            continue

        audit.check("candidate_root_index_mismatch",
                    candidate["root_index"] == slot,
                    {"candidate": slot, "root_index": candidate["root_index"]})
        audit.check("candidate_root_cell_mismatch",
                    candidate["root_cell"] == int(root_cells[slot]),
                    {"candidate": slot, "root_cell": candidate["root_cell"],
                     "expected": int(root_cells[slot])})
        expected = [int(world_x[slot]), int(world_z[slot])]
        audit.check("candidate_root_world_mismatch",
                    isinstance(candidate["root_world_xz"], list)
                    and list(candidate["root_world_xz"]) == expected,
                    {"candidate": slot, "declared": candidate["root_world_xz"],
                     "expected": expected})
        audit.check("candidate_member_count_mismatch",
                    candidate["member_count"] == int(member_ptr[slot + 1] - member_ptr[slot]),
                    {"candidate": slot, "declared": candidate["member_count"],
                     "expected": int(member_ptr[slot + 1] - member_ptr[slot])})

        stem_lo, stem_hi = int(mainstem_ptr[slot]), int(mainstem_ptr[slot + 1])
        node_count = stem_hi - stem_lo
        audit.check("candidate_mainstem_node_count_mismatch",
                    candidate["mainstem_node_count"] == node_count,
                    {"candidate": slot, "declared": candidate["mainstem_node_count"],
                     "expected": node_count})
        audit.check("candidate_mainstem_edges_mismatch",
                    candidate["mainstem_edges"] == max(node_count - 1, 0),
                    {"candidate": slot, "declared": candidate["mainstem_edges"],
                     "expected": max(node_count - 1, 0)})
        audit.check("candidate_evidence_level_mismatch",
                    candidate["evidence_level"] == "structural_candidate",
                    {"candidate": slot, "value": candidate["evidence_level"]})

        root_kind = str(kinds[int(root_cells[slot])])
        audit.check("candidate_root_kind_mismatch", candidate["root_kind"] == root_kind,
                    {"candidate": slot, "declared": candidate["root_kind"],
                     "expected": root_kind, "recomputed": root_kind})

        status_token = candidate["status"]
        if status_token not in STATUS_TOKENS:
            audit.check("candidate_status_unknown", False,
                        {"candidate": slot, "status": status_token})
        else:
            statuses[status_token] += 1
            recomputed = expected_status(slot, root_complete, kinds, root_cells)
            audit.check("candidate_status_mismatch", recomputed == status_token,
                        {"candidate": slot, "declared": status_token,
                         "recomputed": recomputed,
                         "root_complete": bool(root_complete[slot]),
                         "root_terminal_kind": root_kind})

        codes = candidate["reason_codes"]
        codes_ok = (isinstance(codes, list) and codes
                    and all(isinstance(code, str) for code in codes))
        if codes_ok:
            expected_codes = expected_reason_codes(expected_status(slot, root_complete,
                                                                   kinds, root_cells))
            codes_ok = sorted(codes) == sorted(expected_codes)
        audit.check("candidate_reason_codes_mismatch", codes_ok,
                    {"candidate": slot, "codes": codes,
                     "recomputed": expected_reason_codes(
                         expected_status(slot, root_complete, kinds, root_cells))})

        token = candidate["physical_endpoint_evidence"]
        if token not in PHYSICAL_TOKENS:
            audit.check("candidate_physical_token_unknown", False,
                        {"candidate": slot, "token": token})
        elif token in PHYSICAL_CLAIM_TOKENS:
            audit.check("false_physical_claim", False,
                        {"candidate": slot, "token": token,
                         "detail": "a structural candidate carries no bathymetry, stage, "
                                   "storage or outlet certification"})
        # basin_pending exactly for a retained root, none for every other terminal.
        expected_physical = "basin_pending" if root_kind == "retained" else "none"
        audit.check("candidate_physical_evidence_mismatch",
                    token == expected_physical,
                    {"candidate": slot, "declared": token,
                     "expected": expected_physical, "root_kind": root_kind})

        audit.check("structural_only_violation", candidate["structural_only"] is True,
                    {"candidate": slot, "value": candidate["structural_only"]})

        digest = candidate["member_sha256"]
        well_formed = (isinstance(digest, str) and len(digest) == 64
                       and all(character in "0123456789abcdef" for character in digest))
        audit.check("candidate_member_digest_shape", well_formed, {"candidate": slot})
        if well_formed:
            digest_checked += 1
            audit.check("candidate_member_digest_mismatch",
                        member_digests[slot] == digest,
                        {"candidate": slot, "rule": "sha256(sorted world (x,z) i64 LE)"})
        stem_digest = candidate["mainstem_sha256"]
        stem_well_formed = (isinstance(stem_digest, str) and len(stem_digest) == 64
                            and all(character in "0123456789abcdef"
                                    for character in stem_digest))
        audit.check("candidate_mainstem_digest_shape", stem_well_formed, {"candidate": slot})
        if stem_well_formed:
            audit.check("candidate_mainstem_digest_mismatch",
                        stem_digests[slot] == stem_digest,
                        {"candidate": slot,
                         "rule": "sha256(source->root world (x,z) i64 LE)"})

        # The logical identity, recomputed from the public rule rather than trusted.
        id_payload = candidate_id_payload(declared, (int(world_x[slot]), int(world_z[slot])),
                                          digest, root_kind, status_token)
        if id_payload is None:
            audit.check("candidate_id_not_verifiable", False,
                        {"candidate": slot,
                         "detail": "world_seed/spacing/plan_version/logical_version/"
                                   "owner_rule must all be present and declared"})
        else:
            audit.check("candidate_id_mismatch",
                        candidate["candidate_id"] == candidate_id_of(id_payload),
                        {"candidate": slot, "declared": candidate["candidate_id"],
                         "rule": "wdc- + sha256(identity({}, world-anchored payload))"})

    if digest_checked:
        audit.note("candidate_digest_and_id_recomputed",
                   "member_sha256, mainstem_sha256 and candidate_id were recomputed from "
                   "the arrays and the public identity rules and compared, for %d "
                   "candidates" % digest_checked)
    else:
        audit.note("candidate_digest_not_compared",
                   "no well-formed member_sha256 was present in any candidate")
    return statuses


def candidate_id_payload(declared, root_world_xz, member_digest, root_kind, status):
    """The declared world-anchored logical payload of one candidate ID, or None.

    Nothing support-local enters: no origin, no shape, no local flat index, no root
    numbering, no page path. That is why the same world root with the same members keeps
    one ID across a wider or narrower window — and why comparing IDs is a meaningful
    check only under the same ``plan_version`` (see ``compare_windows``).
    """
    for key in ("world_seed", "spacing_m", "plan_version", "logical_version",
                "owner_rule"):
        if declared.get(key) is None:
            return None
    if not isinstance(member_digest, str) or len(member_digest) != 64:
        return None
    return {
        "algorithm": CANDIDATE_ALGORITHM,
        "logical_version": declared["logical_version"],
        "world_seed": declared["world_seed"],
        "spacing_m": declared["spacing_m"],
        "plan_version": declared["plan_version"],
        "owner_rule": declared["owner_rule"],
        "root_world_xz": [int(root_world_xz[0]), int(root_world_xz[1])],
        "member_sha256": member_digest,
        "root_kind": root_kind,
        "status": status,
    }


def candidate_id_of(payload):
    """``wdc-`` + sha256 of the canonical ``identity({}, payload)`` serialisation."""
    body = json.dumps({"metadata": payload, "arrays": {}}, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    return "wdc-" + hashlib.sha256(body.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 3. window-family comparison
# --------------------------------------------------------------------------- #
def load_members(directory):
    """Load one package **only after** it independently passed this audit.

    A comparison reads the same facts an audit reads, so it refuses to compare a
    package that has not just been audited in this process. Comparing two packages
    without auditing them would let an incoherent package (a shifted origin, a
    rewritten member table) take part in a ``PASS``.
    """
    report = audit_bundle(directory)
    if report.get("status") != "PASS":
        raise AuditRefused("compare_refused_bundle_failed_audit",
                           {"bundle": str(directory), "reasons": report.get("reasons")})
    headers = inspect_archive(Path(directory) / ARRAYS_NAME)
    arrays = load_arrays(Path(directory) / ARRAYS_NAME, headers)
    manifest = read_strict_json(Path(directory) / MANIFEST_NAME)
    authoritative, _layout = support_fields(manifest.get("support"))
    origin = authoritative["origin_native_xz"]
    shape = authoritative["shape_zx"]
    metadata = manifest.get("metadata") or {}
    declared = metadata.get("support") if isinstance(metadata.get("support"), dict) else {}
    identity = {
        "world_seed": declared.get("world_seed"),
        "spacing_m": declared.get("spacing_m"),
        "plan_version": declared.get("plan_version"),
        "logical_version": metadata.get("logical_version"),
        "owner_rule": metadata.get("owner_rule"),
        "field_mask_sha256": metadata.get("field_mask_sha256"),
        "source_sha256": declared.get("source_sha256"),
    }
    return (manifest, arrays, int(origin[0]), int(origin[1]), int(shape[1]),
            identity, report)


def member_world_sequence(directory):
    """Per root: world root point, completeness, ordered world member cells, chain."""
    (manifest, arrays, origin_x, origin_z, columns,
     identity, audit_report) = load_members(directory)
    roots = arrays["root_cells"]
    complete = arrays["root_complete"]
    member_ptr = arrays["member_ptr"]
    member_cells = arrays["member_cells"]
    stem_ptr = arrays["mainstem_ptr"]
    stem_cells = arrays["mainstem_cells"]
    resolved = arrays["resolved_mask"]
    candidates = manifest.get("candidates") or []
    root_rows, root_columns = np.divmod(roots, columns)
    out = {}
    for slot in range(int(roots.size)):
        point = (int(root_columns[slot]) + origin_x, int(root_rows[slot]) + origin_z)
        lo, hi = int(member_ptr[slot]), int(member_ptr[slot + 1])
        cells = member_cells[lo:hi].astype(np.int64)
        rows, cols = np.divmod(cells, columns)
        world = sorted((int(c) + origin_x, int(r) + origin_z) for r, c in zip(rows, cols))
        stem_lo, stem_hi = int(stem_ptr[slot]), int(stem_ptr[slot + 1])
        chain = stem_cells[stem_lo:stem_hi].astype(np.int64)
        chain_rows, chain_cols = np.divmod(chain, columns)
        ordered = [(int(c) + origin_x, int(r) + origin_z)
                   for r, c in zip(chain_rows, chain_cols)]
        out[point] = {"complete": bool(complete[slot]), "members": world,
                      "mainstem": ordered,
                      "candidate_id": candidates[slot].get("candidate_id")}
    origin_x, origin_z = int(origin_x), int(origin_z)
    return {"origin_native_xz": [origin_x, origin_z],
            "shape_zx": [int(value) for value in resolved.shape],
            "resolved_cells": int(resolved.sum()),
            "identity": identity,
            "audit_status": audit_report.get("status"),
            "roots": out}


def compare_windows(first, second):
    """Compare two **audited** packages on the *same world roots*.

    Refusal rules, in order, so that a comparison can never pass by not comparing:

    1. each side must first pass ``audit_bundle`` in its own right — a package that is
       not internally coherent (a shifted origin, a rewritten member table) is refused
       instead of participating in a comparison;
    2. the two sides must declare the same ``world_seed``, ``spacing_m``, ``owner_rule``
       and ``logical_version``. Without that they are not the same world at all;
    3. ``plan_version`` must match for a **same-object** verdict. Different plan
       versions are reported as ``version_mismatch`` and never compared as one object,
       even though the structural set/chain comparison itself may still be informative
       — that is reported separately and explicitly as cross-version evidence, not as a
       same-logical-object acceptance;
    4. if no root is complete on both sides there is nothing to compare: the result is
       ``NOT_RUN``, not ``PASS``.

    Roots complete on only one side, or present in only one window, are listed — never
    dropped — so a pass is not obtained by filtering down to whatever agrees.
    """
    left = member_world_sequence(first)
    right = member_world_sequence(second)
    left_identity = left["identity"]
    right_identity = right["identity"]
    result = {
        "schema": "metric-world-domain-candidates-window-comparison-v1",
        "left": {"bundle": str(first),
                 "origin_native_xz": left["origin_native_xz"],
                 "shape_zx": left["shape_zx"], "roots": len(left["roots"]),
                 "resolved_cells": left["resolved_cells"],
                 "audit_status": left["audit_status"],
                 "identity": left_identity},
        "right": {"bundle": str(second),
                  "origin_native_xz": right["origin_native_xz"],
                  "shape_zx": right["shape_zx"], "roots": len(right["roots"]),
                  "resolved_cells": right["resolved_cells"],
                  "audit_status": right["audit_status"],
                  "identity": right_identity},
        "status": "NOT_RUN",
        "reason": None,
        "same_logical_objects": False,
        "structural_comparison": False,
        "shared_roots": 0,
        "shared_roots_complete_on_both": 0,
        "member_set_mismatches": [],
        "mainstem_mismatches": [],
        "complete_in_one_window_only": [],
        "incomplete_on_both_sides": [],
        "root_present_in_one_window_only": [],
        "scope": (
            "both packages must independently pass the audit; only roots complete on "
            "both sides are compared, by world root point, as ordered world member "
            "sequences and ordered mainstem chains; one-sided and incomplete roots are "
            "listed, never filtered out; a same-logical-object verdict additionally "
            "requires the same plan_version"),
    }

    for label, identity in (("left", left_identity), ("right", right_identity)):
        for key in ("world_seed", "spacing_m", "owner_rule", "logical_version"):
            if identity.get(key) is None:
                result["reason"] = "%s_identity_incomplete:%s" % (label, key)
                return result
    for key in ("world_seed", "spacing_m", "owner_rule", "logical_version"):
        if left_identity[key] != right_identity[key]:
            result["reason"] = "object_identity_mismatch:%s" % key
            result["status"] = "REJECTED"
            return result
    # The *pages* are what proves both windows are cut from one bed. The field/mask
    # digest is per-window by construction (a wider window hashes more cells), so it
    # is recorded but never used as a cross-window identity.
    if left_identity.get("source_sha256") != right_identity.get("source_sha256"):
        result["reason"] = "source_identity_mismatch:source_sha256"
        result["status"] = "REJECTED"
        return result

    same_plan = left_identity["plan_version"] == right_identity["plan_version"]
    result["same_logical_objects"] = bool(same_plan)
    result["structural_comparison"] = True
    if not same_plan:
        result["reason"] = "version_mismatch"

    both = sorted(set(left["roots"]) & set(right["roots"]))
    both_complete = [point for point in both
                     if left["roots"][point]["complete"]
                     and right["roots"][point]["complete"]]
    member_mismatch = []
    mainstem_mismatch = []
    id_mismatch = []
    for point in both_complete:
        if left["roots"][point]["members"] != right["roots"][point]["members"]:
            member_mismatch.append(list(point))
        if left["roots"][point]["mainstem"] != right["roots"][point]["mainstem"]:
            mainstem_mismatch.append(list(point))
        # The candidate ID is world-anchored, so *under one plan version* the same
        # world root with the same complete members must carry the same ID.
        if same_plan and left["roots"][point]["candidate_id"] \
                != right["roots"][point]["candidate_id"]:
            id_mismatch.append(list(point))
    one_sided = sorted(set(left["roots"]) ^ set(right["roots"]))

    result["shared_roots"] = len(both)
    result["shared_roots_complete_on_both"] = len(both_complete)
    result["member_set_mismatches"] = member_mismatch
    result["mainstem_mismatches"] = mainstem_mismatch
    result["candidate_id_mismatches"] = id_mismatch
    result["complete_in_one_window_only"] = [
        list(point) for point in both
        if left["roots"][point]["complete"] != right["roots"][point]["complete"]]
    result["incomplete_on_both_sides"] = [
        list(point) for point in both
        if not left["roots"][point]["complete"]
        and not right["roots"][point]["complete"]]
    result["root_present_in_one_window_only"] = [list(point) for point in one_sided]

    if not both_complete:
        result["status"] = "NOT_RUN"
        result["reason"] = "no_root_complete_on_both_sides"
        return result
    if member_mismatch or mainstem_mismatch or id_mismatch:
        result["status"] = "FAILED"
        result["reason"] = "object_mismatch"
        return result
    if not same_plan:
        result["status"] = "REJECTED"
        return result
    result["status"] = "PASS"
    return result


# --------------------------------------------------------------------------- #
# 4. CLI
# --------------------------------------------------------------------------- #
def write_report(path, report):
    target = Path(path)
    if target.exists():
        raise AuditRefused("report_target_exists", str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, sort_keys=True, indent=2, allow_nan=False)
    target.write_text(payload + "\n", encoding="utf-8")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", help="prepared directory holding manifest.json + arrays.npz")
    parser.add_argument("--report", help="report path; must not already exist")
    parser.add_argument("--compare", nargs=2, metavar=("LEFT", "RIGHT"),
                        help="compare two prepared windows on shared world roots")
    arguments = parser.parse_args(argv)
    if arguments.compare:
        try:
            comparison = compare_windows(*arguments.compare)
        except AuditRefused as refusal:
            print("REFUSED %s: %s" % (refusal.reason, refusal.detail), file=sys.stderr)
            return 2
        if arguments.report:
            write_report(arguments.report, comparison)
        print(json.dumps(comparison, sort_keys=True))
        return 0 if comparison["status"] == "PASS" else 1
    if arguments.bundle is None:
        parser.error("--bundle or --compare is required")
    try:
        report = audit_bundle(arguments.bundle)
    except AuditRefused as refusal:
        print("REFUSED %s: %s" % (refusal.reason, refusal.detail), file=sys.stderr)
        return 2
    if arguments.report:
        write_report(arguments.report, report)
    print(json.dumps({"status": report["status"], "reasons": report["reasons"],
                      "counters": report["counters"]}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
