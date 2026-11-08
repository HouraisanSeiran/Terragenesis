"""World-anchored structural domain candidates: support plan, roots, mainstems, divides.

What this module is, and what it deliberately is not
----------------------------------------------------
The B1 layer of the river–lake / infinite-world integration: the interface is the
B1 stage card frozen by the main branch (structural candidate layer, not a
hydrological certification). It answers, for **one declared computation support**,
four structural questions and nothing else:

``support_plan``
    Freeze the support (origin, shape, budget, page pins, ``plan_version``) *before*
    any page is read. The support never follows a render window, and growing it
    requires a new ``plan_version`` rather than an implicit re-window.
``root_catchments`` / ``domain_candidates``
    Which structural terminal each valid cell drains to, which catches are closed,
    and what each candidate's membership and mainstem are.
``mainstem_chain``
    The complete source→root ordered chain of one root: at every step the donor with
    the largest upstream cell count, ties broken by the donor's world ``(x, z)``.
``shared_divides``
    The canonical (world-pair, de-duplicated) D4 edges between two different owners,
    plus any irregular graph edge that crosses an owner boundary.

Deliberately absent: a second irregular graph implementation (the one authority is
``native_30m_source.build_strict_topology``, which itself calls
``irregular_grid.strict_receivers``), a second accumulation (upstream counts and
propagated completeness come from
``metric_network_accumulation.accumulate_network_discharge`` with ``local_q == 1``),
any water balance, any lake level, any outlet certification, any page reading. Reach
slicing is *not* implemented here; ``segment_donors`` only counts cross-segment edges
so a later ``metric_world_reaches`` can consume them.

What a candidate is, and is not
-------------------------------
A ``candidate_id`` is **not** a ``domain_id``. ``candidate_closed`` means only "every
member of this structural catchment has a complete declared upstream"; it does not
make the candidate a legal hydrological domain, and ``final`` needs the C-stage
hierarchy/ports and a new ``plan_version`` published by the main branch. A
``retained`` root is only the terminal of a *finite graph*, so its
``physical_endpoint_evidence`` is ``basin_pending`` -- never a lake, never an outlet.
An ``unknown_boundary`` root is ``none``: a support edge is not a sea.

Identity layers (kept apart on purpose)
---------------------------------------
1. *Support identity* -- ``identity({}, support_metadata)``: origin, shape, budget,
   page pins, ``plan_version``, coordinate rule. No array content.
2. *Source identity* -- the caller's pin declaration plus the content digest
   ``field_mask_sha256`` of the exact elevation/mask pair used. The digest is a
   **content checksum, not a signature**: it proves the bytes are the bytes, and the
   page pins and the real read are the loader's job (``load_native_window``). Nothing
   here re-authenticates a page.
3. *World member identity* -- a member is a **signed int64 world ``(x, z)`` pair**.
   ``member_sha256`` is sha256 over those pairs, little-endian, sorted by ``(x, z)``;
   the pair count is bound by the byte length. No packed ``(z+2**20)*2**22+...`` key
   and no absolute float coordinate ever enters a member identity.
4. *Bundle identity* -- ``identity(arrays, metadata)``: the repository idiom, which
   binds every array's shape and dtype to the declared metadata.

Cost model
----------
One call each of the irregular graph topology and the accumulation. Donor lists are built once as
CSR (``group``-style, ``O(N log N)``) and every root walk reads them, so there is no
per-root full-grid scan and no per-root re-derivation of the receiver graph; the total
mainstem work is bounded by ``N``. Roots are ordered by world ``(x, z)``, never by
local flat index, so a window relabelling cannot reorder the product.
"""
from __future__ import annotations

import hashlib
import importlib
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.drainage import MAX_NETWORK_CELLS as MAX_NETWORK_CELLS
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge
from terrain_pipeline.surface_rivers.metric_network_discharge_product import (
    TERMINAL_KIND_DTYPE,
    TERMINAL_LABELS,
)
from terrain_pipeline.surface_rivers.native_30m_source import (
    DEFAULT_WORLD_SEED,
    NATIVE_SPACING_M,
    build_strict_topology,
)

__all__ = [
    "ARRAY_NAMES",
    "CANDIDATE_KEYS",
    "DECLARED_SPACING_M",
    "DECLARED_WORLD_SEED",
    "MEMBER_SERIALIZATION",
    "BUNDLE_KEYS",
    "MAX_COORDINATE_M",
    "MAX_SUPPORT_CELLS",
    "REASON_COMPLETE",
    "REASON_COORDINATE_PRECISION",
    "REASON_CROSS_DOMAIN_DRAIN",
    "REASON_NO_ROOT",
    "REASON_OWNER_GAP",
    "REASON_OWNER_OVERLAP",
    "REASON_ROOT_NOT_TERMINAL",
    "REASON_SEGMENT_DONOR_MISMATCH",
    "REASON_SUPPORT_TRUNCATED",
    "REASON_UNPREPARED",
    "REASON_UPSTREAM_UNKNOWN",
    "CANDIDATE_IDENTITY_POLICY",
    "LOGICAL_VERSION",
    "OWNER_RULE",
    "SOURCE_KIND_PINNED",
    "SOURCE_KIND_SYNTHETIC",
    "SCHEMA",
    "STATUS_CLOSED",
    "STATUS_OPEN_UPSTREAM",
    "STATUS_TRUNCATED",
    "SUPPORT_SCHEMA",
    "domain_candidates",
    "mainstem_chain",
    "member_sha256",
    "native_to_metres",
    "root_catchments",
    "segment_donors",
    "segment_retention",
    "shared_divides",
    "support_plan",
    "validate_domain_candidates",
    "world_keys",
]


# --------------------------------------------------------------------------- #
# declared vocabulary and budgets
# --------------------------------------------------------------------------- #
SCHEMA = "metric-world-domain-candidates-v1"
SUPPORT_SCHEMA = "metric-world-support-plan-v1"

#: The frozen continuous baseline (``CONTRIBUTING.md``). A request for another seed
#: or another lattice is a different world, not a knob: it is refused here so that a
#: candidate identity can never quietly belong to two lattices.
DECLARED_WORLD_SEED = DEFAULT_WORLD_SEED
DECLARED_SPACING_M = NATIVE_SPACING_M

#: B1 support ceiling: 385² = 148 225 cells (``parameters.md`` P2). A larger support
#: needs its own declared budget and its own measurement, and still may not exceed
#: the reused kernel ceilings (``native_30m_source.MAX_TOPOLOGY_CELLS``,
#: ``metric_network_accumulation.MAX_NETWORK_CELLS``). Never grown implicitly.
MAX_SUPPORT_CELLS = 148_225

#: float64 represents integers exactly only up to 2**53. A metre value beyond this is
#: refused instead of being silently rounded; the native int64 range is checked first
#: in Python integers, so nothing can wrap.
MAX_COORDINATE_M = 2 ** 53
MAX_NATIVE_COORDINATE = 2 ** 63 - 1

#: Per-cell byte cost of the declared array block: elevation 8 + resolved 1 +
#: receiver 8 + terminal_kind 96 (U24) + unknown 1 + complete 1 + upstream 8 +
#: owner 8 = 131, plus the member CSR (8 + 8) and the mainstem CSR (8 + 8).
_BYTES_PER_CELL = 131
_BYTES_PER_CELL_FOR_MEMBERS = 16
_BYTES_PER_CELL_FOR_MAINSTEM = 16
_BYTES_PER_ROOT = 8 + 1 + 8 + 8 + 8 + 64 + 32

#: Declared byte budget for one candidate bundle, checked **before** any full-extent
#: array is allocated. 385² with the worst case (every cell its own root) is about
#: 26 MiB, so this refuses only a package that could not be held, never a legal one.
MAX_BUNDLE_BYTES = 256 * 1024 * 1024

#: A root-count ceiling: every root costs per-root arrays and a candidate dictionary,
#: so an absurd count is refused before those are built rather than after.
MAX_ROOTS = 131_072

MEMBER_SERIALIZATION = {
    "dtype": "int64",
    "order": "sorted_by_(x,z)",
    "byte_order": "little_endian",
    "shape_binding": "pair_count_from_byte_length",
    "forbidden": "packed integer keys and absolute float coordinates are never member identity",
}

MEMBER_IDENTITY_POLICY = (
    "member_sha256 = sha256(world (x,z) int64 little-endian bytes, rows sorted by (x,z)); "
    "the pair count is bound by the byte length; no packed key, no float coordinate")

COORDINATE_RULE = (
    "array cell (z_index, x_index) sits at world native (x, z) = origin_native_xz + "
    "(x_index, z_index); signed int64 native cells on the 30 m Terrain Diffusion lattice; "
    "metres are derived for display only and never hashed")

SUPPORT_POLICY = (
    "the support is frozen before any page is read and does not follow a render window; "
    "a different origin/shape/budget or a different owner rule is a new plan_version")

#: Machine-stable reason vocabulary (issue 01 §7). Additions must not collide with the
#: legacy five/seven-word literals kept by ``metric_domain_pipeline``.
REASON_COMPLETE = "complete"
REASON_UPSTREAM_UNKNOWN = "upstream_unknown"
REASON_SUPPORT_TRUNCATED = "support_truncated"
REASON_UNPREPARED = "unprepared"
REASON_CROSS_DOMAIN_DRAIN = "cross_domain_drain"
REASON_OWNER_OVERLAP = "owner_overlap"
REASON_OWNER_GAP = "owner_gap"
REASON_NO_ROOT = "no_root"
REASON_ROOT_NOT_TERMINAL = "root_not_terminal"
REASON_SEGMENT_DONOR_MISMATCH = "segment_donor_mismatch"
REASON_DIAGONAL_AMBIGUOUS = "diagonal_transition_ambiguous"
REASON_COORDINATE_PRECISION = "coordinate_precision_exceeded"

REASON_VOCABULARY = (
    REASON_COMPLETE, REASON_UPSTREAM_UNKNOWN, REASON_SUPPORT_TRUNCATED,
    REASON_UNPREPARED, REASON_CROSS_DOMAIN_DRAIN, REASON_OWNER_OVERLAP,
    REASON_OWNER_GAP, REASON_NO_ROOT, REASON_ROOT_NOT_TERMINAL,
    REASON_SEGMENT_DONOR_MISMATCH, REASON_DIAGONAL_AMBIGUOUS,
    REASON_COORDINATE_PRECISION,
)

STATUS_CLOSED = "candidate_closed"
STATUS_OPEN_UPSTREAM = "candidate_open_upstream"
STATUS_TRUNCATED = "candidate_truncated"
STATUS_UNPREPARED = "unprepared"

SOURCE_KIND_PINNED = "td_pinned"
SOURCE_KIND_SYNTHETIC = "synthetic_fixture"
SOURCE_KINDS = (SOURCE_KIND_PINNED, SOURCE_KIND_SYNTHETIC)

SOURCE_VERIFICATION_PINNED = "caller pinned loader; checksums not signature"
SOURCE_VERIFICATION_SYNTHETIC = (
    "synthetic fixture; no TD page pin and no checksum claim")

#: Fields a ``source`` dictionary may never carry: topology and completeness are
#: rebuilt here from the field and mask, so a caller cannot hand in a receiver or a
#: ``complete_mask`` that skips the rebuild.
FORBIDDEN_SOURCE_KEYS = (
    "receiver", "complete_mask", "terminal_kind", "upstream_unknown_mask",
    "owner_index", "owner", "catchment_of_cell", "upstream_cells",
)

BUNDLE_KEYS = {"schema", "support", "arrays", "candidates", "metadata",
               "identity_sha256"}

#: The public array block. ``member_cells`` / ``mainstem_cells`` are **local flat
#: indices** (positioning only, never world identity); world identity lives in
#: ``candidate['member_sha256']``.
ARRAY_NAMES = (
    "elevation_m", "resolved_mask", "receiver", "terminal_kind",
    "upstream_unknown_mask", "complete_mask", "upstream_cells", "owner_index",
    "root_cells", "root_complete", "member_counts", "member_ptr", "member_cells",
    "mainstem_ptr", "mainstem_cells", "shared_face_cells",
)

CANDIDATE_KEYS = (
    "candidate_id", "root_index", "root_cell", "root_world_xz", "root_kind",
    "member_count", "member_sha256", "status", "reason_codes",
    "physical_endpoint_evidence", "structural_only", "evidence_level",
    "mainstem_node_count", "mainstem_edges", "mainstem_sha256",
)

#: The logical version of one candidate object. It is part of ``candidate_id``, so a
#: semantic change that could move a border is a new object rather than a silent edit.
LOGICAL_VERSION = "b1-structural-irregular-v2"
CANDIDATE_IDENTITY_POLICY = (
    "candidate_id = 'wdc-' + sha256 over a world-anchored logical payload "
    "(algorithm name + logical version, world seed, lattice spacing, plan_version, "
    "owner rule, root world (x,z), member_sha256, root_kind and status). It excludes "
    "the support origin/shape, local flat indices, page paths and support-local root "
    "numbering: the same world root with the same complete member set keeps one id in "
    "a wider or narrower support, and different members, seed, plan_version or "
    "completeness give a different id. root_index is a support-local array offset "
    "only and is never identity.")

_SHA_CHARS = set("0123456789abcdef")
_SHA_CACHE = {}


# --------------------------------------------------------------------------- #
# scalar validation
# --------------------------------------------------------------------------- #
def _strict_int(value, name):
    """An index is an integer: bools, floats and strings are refused."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("%s must be an integer, not a boolean" % name)
    if isinstance(value, (int, np.integer)):
        return int(value)
    raise ValueError("%s must be an integer, got %s" % (name, type(value).__name__))


def _strict_float(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.floating, np.integer)):
        raise ValueError("%s must be a number" % name)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % name)
    return result


def _int_pair(values, name):
    if isinstance(values, np.ndarray):
        if values.shape != (2,):
            raise ValueError("%s must carry exactly two integers" % name)
        items = values.tolist()
    elif isinstance(values, (list, tuple)) and len(values) == 2:
        items = list(values)
    else:
        raise ValueError("%s must be a two-element sequence of integers" % name)
    return [_strict_int(item, name) for item in items]


def _shape_pair(values, minimum=2):
    rows, columns = _int_pair(values, "shape_zx")
    if rows < minimum or columns < minimum:
        raise ValueError("shape_zx must be at least %dx%d, got %dx%d"
                         % (minimum, minimum, rows, columns))
    return rows, columns


def _sha_text(value, name):
    if not isinstance(value, str) or len(value) != 64 or not set(value) <= _SHA_CHARS:
        raise ValueError("%s must be 64 lowercase hexadecimal characters" % name)
    return value


def _source_records(records):
    """Path-sorted page pins; every record needs both members and no other member."""
    if not isinstance(records, (list, tuple)) or len(records) == 0:
        raise ValueError("%s: at least one pinned page record is required" % "pin_missing")
    seen_paths = set()
    seen_sha = set()
    ordered = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise ValueError("%s: each source record carries exactly path and sha256"
                             % "pin_missing")
        path = record["path"]
        if not isinstance(path, str) or not path:
            raise ValueError("%s: path must be a non-empty string" % "pin_missing")
        digest = _sha_text(record["sha256"], "sha256")
        if path in seen_paths:
            raise ValueError("%s: duplicate source path %s" % ("duplicate_page_key", path))
        if digest in seen_sha:
            raise ValueError("%s: two pages share the sha256 %s"
                             % ("duplicate_page_key", digest))
        seen_paths.add(path)
        seen_sha.add(digest)
        ordered.append({"path": path, "sha256": digest})
    return sorted(ordered, key=lambda item: item["path"])


def _pins_of(records, name):
    """Normalise a pin list to path-sorted ``{path, sha256}`` pairs.

    ``load_native_window`` returns *richer* records (page key, native origin, shape,
    seed, spacing). Those extra members are read-only annotations, so they are
    dropped here: the pin is the path and the digest, and nothing else is compared.
    A record that omits either member is refused rather than guessed.
    """
    if not isinstance(records, (list, tuple)) or len(records) == 0:
        raise ValueError("pin_missing: at least one pinned page record is required")
    pairs = []
    for record in records:
        if not isinstance(record, dict) or "path" not in record or "sha256" not in record:
            raise ValueError("pin_missing: each page record must carry path and sha256")
        path = record["path"]
        if not isinstance(path, str) or not path:
            raise ValueError("pin_missing: path must be a non-empty string")
        pairs.append({"path": path, "sha256": _sha_text(record["sha256"], name)})
    return sorted(pairs, key=lambda item: item["path"])


def _native_int64(values, name):
    """Check the native coordinate range in Python integers, so nothing can wrap."""
    for value in values:
        if not isinstance(value, int) or abs(value) > MAX_NATIVE_COORDINATE:
            raise ValueError("%s: %s: native coordinate %r does not fit signed int64"
                             % (REASON_COORDINATE_PRECISION, name, value))
    return list(values)


# --------------------------------------------------------------------------- #
# 1. the computation support, and the leaf conversion
# --------------------------------------------------------------------------- #
def _metres_of(native, spacing_m):
    product = int(native) * float(spacing_m)
    value = float(product)
    if not math.isfinite(value) or abs(product) > MAX_COORDINATE_M:
        raise ValueError("%s: native %d cells at %r m/cell is not exactly representable "
                         "in float64" % (REASON_COORDINATE_PRECISION, int(native),
                                         float(spacing_m)))
    return value


def native_to_metres(native_xz, shape_zx=None, *, spacing_m=DECLARED_SPACING_M):
    """Native cells -> metres, refusing integer overflow and float64 precision loss.

    With ``shape_zx`` the far corner is computed in Python integers first (the
    ``origin + shape - 1`` sum must not wrap) and both corners are returned; without
    it a single ``(x, z)`` pair is returned. Metres are for display and for physical
    recording only -- no metre value enters an identity.
    """
    try:
        spacing = _strict_float(spacing_m, "spacing_m")
    except ValueError as error:
        raise ValueError("%s: %s" % (REASON_COORDINATE_PRECISION, error)) from None
    if spacing <= 0.0:
        raise ValueError("%s: spacing_m must be positive, got %r"
                         % (REASON_COORDINATE_PRECISION, spacing))
    x, z = _int_pair(native_xz, "native_xz")
    if shape_zx is None:
        return [_metres_of(x, spacing), _metres_of(z, spacing)]
    rows, columns = _shape_pair(shape_zx)
    far_x = x + columns - 1
    far_z = z + rows - 1
    _native_int64((x, far_x, z, far_z), "native_xz range")
    return {
        "origin_m": [_metres_of(x, spacing), _metres_of(z, spacing)],
        "max_m": [_metres_of(far_x, spacing), _metres_of(far_z, spacing)],
        "spacing_m": spacing,
    }


def support_plan(*, world_seed, spacing_m, origin_native_xz, shape_zx, source_records,
                 plan_version, max_cells=MAX_SUPPORT_CELLS):
    """Freeze one computation support: no page is read, no window is inferred.

    Every dimension must be at least two cells, the cell count must fit ``max_cells``
    and ``max_cells`` may not exceed :data:`MAX_SUPPORT_CELLS` (148 225 = 385²). The
    pins are path-sorted, both members are required, and a duplicate path or a shared
    digest is refused. ``plan_version`` is explicit and positive.

    Returns ``{arrays: {}, metadata, identity_sha256}``; ``arrays`` stays empty on
    purpose, because a support plan is a declaration and not a derived product.
    """
    seed = _strict_int(world_seed, "world_seed")
    if seed != DECLARED_WORLD_SEED:
        raise ValueError("seed_mismatch: world_seed must be the frozen baseline %d, got %d"
                         % (DECLARED_WORLD_SEED, seed))
    try:
        spacing = _strict_float(spacing_m, "spacing_m")
    except ValueError as error:
        raise ValueError("spacing_mismatch: %s" % error) from None
    if spacing != DECLARED_SPACING_M:
        raise ValueError("spacing_mismatch: spacing_m must be the TD native %r, got %r"
                         % (DECLARED_SPACING_M, spacing))
    budget = _strict_int(max_cells, "max_cells")
    if budget <= 0:
        raise ValueError("budget_exceeded: max_cells must be positive, got %d" % budget)
    if budget > MAX_SUPPORT_CELLS:
        raise ValueError("budget_exceeded: max_cells %d exceeds this level's declared "
                         "support ceiling %d (385^2); a larger support needs its own "
                         "budget and its own measurement" % (budget, MAX_SUPPORT_CELLS))
    rows, columns = _shape_pair(shape_zx)
    cells = rows * columns
    if cells > budget:
        raise ValueError("budget_exceeded: support %dx%d = %d cells exceeds max_cells=%d"
                         % (rows, columns, cells, budget))
    if cells > MAX_SUPPORT_CELLS:
        raise ValueError("budget_exceeded: support %d cells exceeds the declared "
                         "ceiling %d" % (cells, MAX_SUPPORT_CELLS))
    origin = _int_pair(origin_native_xz, "origin_native_xz")
    version = _strict_int(plan_version, "plan_version")
    if version <= 0:
        raise ValueError("plan_version must be a positive integer, got %d" % version)
    records = _source_records(source_records)

    origin_x, origin_z = origin
    far_x = origin_x + columns - 1
    far_z = origin_z + rows - 1
    _native_int64((origin_x, far_x, origin_z, far_z), "support range")
    metres = native_to_metres(origin, [rows, columns], spacing_m=spacing)

    metadata = {
        "schema": SUPPORT_SCHEMA,
        "world_seed": seed,
        "spacing_m": spacing,
        "origin_native_xz": [origin_x, origin_z],
        "shape_zx": [rows, columns],
        "support_cells": cells,
        "max_cells": budget,
        "max_support_cells": MAX_SUPPORT_CELLS,
        "source_records": records,
        "source_record_count": len(records),
        "source_sha256": sorted(record["sha256"] for record in records),
        "range_native": {"x": [origin_x, far_x], "z": [origin_z, far_z]},
        "range_native_m": metres,
        "storage_representation": "signed_int64_native_cells",
        "plan_version": version,
        "coordinate_rule": COORDINATE_RULE,
        "coordinate_serialization": dict(MEMBER_SERIALIZATION),
        "member_identity_policy": MEMBER_IDENTITY_POLICY,
        "support_policy": SUPPORT_POLICY,
    }
    return {"arrays": {}, "metadata": metadata,
            "identity_sha256": identity({}, metadata)}


def _support_metadata(support):
    """Re-derive a support plan from its own declared fields and compare.

    A support bundle whose metadata was edited (a new shape with the old range, a
    changed ``plan_version``, a pin list that does not match its own digest) cannot
    survive this, because the metadata is recomputed from the primitives and required
    to be identical.
    """
    if not isinstance(support, dict):
        raise ValueError("support must be a support_plan result (or its metadata)")
    if "metadata" in support:
        if set(support) != {"arrays", "metadata", "identity_sha256"}:
            raise ValueError("a support plan is {arrays, metadata, identity_sha256}")
        if support["arrays"] not in ({}, None):
            raise ValueError("%s: a support plan carries no arrays; drop the extra ones"
                             % REASON_UNPREPARED)
        metadata = support["metadata"]
        declared_identity = support["identity_sha256"]
    else:
        metadata = support
        declared_identity = None
    if not isinstance(metadata, dict):
        raise ValueError("support metadata must be a mapping")
    rebuilt = support_plan(
        world_seed=metadata.get("world_seed"),
        spacing_m=metadata.get("spacing_m"),
        origin_native_xz=metadata.get("origin_native_xz"),
        shape_zx=metadata.get("shape_zx"),
        source_records=metadata.get("source_records"),
        plan_version=metadata.get("plan_version"),
        max_cells=metadata.get("max_cells", MAX_SUPPORT_CELLS),
    )
    if rebuilt["metadata"] != metadata:
        raise ValueError("%s: the support metadata does not follow from its own declared "
                         "fields (origin/shape/range/budget/pins/plan_version)"
                         % REASON_UNPREPARED)
    if declared_identity is not None and declared_identity != rebuilt["identity_sha256"]:
        raise ValueError("support identity mismatch: the declared digest is not the "
                         "digest of the declared support")
    return rebuilt["metadata"], rebuilt["identity_sha256"]


# --------------------------------------------------------------------------- #
# 2. world keys and the member digest
# --------------------------------------------------------------------------- #
def world_keys(x_z):
    """Validate a signed world ``(x, z)`` pair array; never reorder it."""
    if (not isinstance(x_z, np.ndarray) or x_z.dtype != np.int64 or x_z.ndim != 2
            or x_z.shape[1] != 2 or x_z.shape[0] < 1):
        raise ValueError("world keys must be an int64 [N,2] array with N >= 1")
    return np.ascontiguousarray(x_z, np.int64).copy()


def _sha_world_pairs(pairs):
    block = np.ascontiguousarray(np.asarray(pairs, np.int64).reshape(-1, 2), dtype="<i8")
    return hashlib.sha256(block.tobytes()).hexdigest()


def member_sha256(x_z):
    """sha256 of the world members, sorted by ``(x, z)``, int64 little-endian.

    Permuting the input cannot change the digest, and changing one member always
    does; the pair count is bound by the byte length, so the shape needs no prefix.
    """
    keys = world_keys(x_z)
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    return _sha_world_pairs(keys[order])


def _world_flat(flat, origin_native_xz, columns):
    flat = np.asarray(flat, np.int64)
    x = origin_native_xz[0] + (flat % columns)
    z = origin_native_xz[1] + (flat // columns)
    return np.stack([x, z], axis=1).astype(np.int64)


# --------------------------------------------------------------------------- #
# 3. topology-derived tables (one accumulation, one donor CSR)
# --------------------------------------------------------------------------- #
def _bundle_bytes(cells, roots):
    """Upper bound on the bundle's uncompressed payload, in bytes."""
    return (cells * (_BYTES_PER_CELL + _BYTES_PER_CELL_FOR_MEMBERS
                     + _BYTES_PER_CELL_FOR_MAINSTEM)
            + roots * _BYTES_PER_ROOT)


def _check_bundle_budget(cells, roots):
    """Refuse an over-budget support or root count before anything is allocated."""
    if roots > MAX_ROOTS:
        raise ValueError("budget_exceeded: %d structural roots exceeds the declared "
                         "root budget %d; the support is too fragmented for this level "
                         "(split the support instead of relaxing the budget)"
                         % (roots, MAX_ROOTS))
    estimate = _bundle_bytes(cells, roots)
    if estimate > MAX_BUNDLE_BYTES:
        raise ValueError("budget_exceeded: the bundle needs about %d bytes (%d cells, "
                         "%d roots) but the declared byte budget is %d"
                         % (estimate, cells, roots, MAX_BUNDLE_BYTES))
    return estimate


def _check_receiver_adjacency(receiver, valid_mask, name="receiver", *, origin_native_xz=(0, 0)):
    """A receiver must be a real irregular graph neighbour; a jump or a self edge is refused.

    The graph this module derives comes from ``build_strict_topology`` and is adjacent
    by construction, so this guard exists for the entry points that accept a caller's
    graph (``root_catchments``, ``mainstem_chain``): a long-range edge would pass every
    downstream count check while describing a graph no 30 m irregular graph kernel can produce.
    """
    receiver = _check_int_grid(receiver, name)
    valid_mask = _check_bool_grid(valid_mask, "valid_mask", receiver.shape)
    rows, columns = receiver.shape
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    if not flat_valid.any():
        raise ValueError("at least one valid cell is required")
    if np.any(flat_receiver[~flat_valid] != -1):
        raise ValueError("inactive cells must carry receiver -1")
    source = np.flatnonzero(flat_valid & (flat_receiver >= 0))
    target = flat_receiver[source]
    if target.size and (np.any(target < 0) or np.any(target >= flat_receiver.size)):
        raise ValueError("receiver index outside the grid")
    if np.any(target == source):
        raise ValueError("a cell cannot be its own receiver")
    if target.size and np.any(~flat_valid[target]):
        raise ValueError("a receiver target must be a valid cell")
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
    mesh = masked_mesh(grid_mesh(receiver.shape,
        x0_m=origin_native_xz[0] * 30., z0_m=origin_native_xz[1] * 30., dx_m=30.,
        world_seed=20261020), valid_mask)
    if not receiver_edges_valid(receiver, mesh):
        raise ValueError("%s: receiver is not an edge of the masked irregular graph"
                         % REASON_ROOT_NOT_TERMINAL)
    return receiver, valid_mask


def _accumulated_counts(receiver, valid_mask, terminal_kind, upstream_unknown_mask,
                        max_cells):
    """Upstream cell counts and propagated completeness from the existing kernel."""
    local_q = valid_mask.astype(np.float64)
    budget = int(max_cells)
    if receiver.size > budget or budget > MAX_NETWORK_CELLS:
        raise ValueError("budget_exceeded: %d cells outside the accumulation budget "
                         "%d (ceiling %d)" % (receiver.size, budget, MAX_NETWORK_CELLS))
    result = accumulate_network_discharge(
        receiver, local_q, valid_mask, terminal_kind=terminal_kind,
        upstream_unknown_mask=upstream_unknown_mask, max_cells=budget)
    routed = result["known_routed_q_m3_s"]
    counts = np.rint(routed).astype(np.int64)
    if not np.array_equal(counts.astype(np.float64), routed):
        raise RuntimeError("the accumulated upstream counts are not integral; a unit "
                           "local Q must produce exact cell counts")
    if np.any(counts[~valid_mask] != 0):
        raise RuntimeError("an inactive cell accumulated upstream cells")
    return np.ascontiguousarray(counts, np.int64), np.ascontiguousarray(
        result["complete_mask"], bool)


def _terminal_of_cell(receiver, valid_mask):
    """Flat terminal index per cell, by pointer doubling (no per-cell Python walk)."""
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    index = np.arange(flat_receiver.size, dtype=np.int64)
    step = np.where(flat_valid, np.where(flat_receiver >= 0, flat_receiver, index), index)
    reach = step
    limit = int(math.ceil(math.log2(max(flat_receiver.size, 2)))) + 2
    for _ in range(limit):
        following = reach[reach]
        if np.array_equal(following, reach):
            break
        reach = following
    else:
        raise ValueError("the receiver graph does not terminate (cycle)")
    resolved = np.where(flat_valid, reach, -1).astype(np.int64)
    if np.any(flat_receiver[resolved[flat_valid]] >= 0):
        raise ValueError("the receiver graph does not terminate (cycle)")
    return resolved


def _donor_csr(receiver, valid_mask):
    """Group donors once: ``donors_sorted[ptr[i]:ptr[i+1]]`` are the cells into ``i``."""
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    source = np.flatnonzero(flat_valid & (flat_receiver >= 0))
    target = flat_receiver[source]
    order = np.argsort(target, kind="stable")
    donors_sorted = source[order].astype(np.int64)
    counts = np.bincount(target, minlength=flat_receiver.size).astype(np.int64)
    pointer = np.zeros(flat_receiver.size + 1, np.int64)
    np.cumsum(counts, out=pointer[1:])
    return donors_sorted, pointer


def _check_upstream_counts(receiver, valid_mask, upstream_cells):
    """The counts must satisfy ``count(c) == 1 + sum(count(donors of c))`` for every cell.

    This is an ``O(N)`` consistency proof against the receiver graph, not a second
    accumulation: a forged or stale count array is refused before it can be used to
    choose a mainstem.
    """
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    flat_up = upstream_cells.reshape(-1)
    if np.any(flat_up[~flat_valid] != 0):
        raise ValueError("inactive cells must carry an upstream count of 0")
    if np.any(flat_up[flat_valid] < 1):
        raise ValueError("every valid cell contributes itself, so its upstream count is >= 1")
    source = np.flatnonzero(flat_valid & (flat_receiver >= 0))
    totals = np.where(flat_valid, 1, 0).astype(np.int64)
    np.add.at(totals, flat_receiver[source], flat_up[source])
    wrong = flat_valid & (totals != flat_up)
    if np.any(wrong):
        index = int(np.flatnonzero(wrong)[0])
        raise ValueError("upstream_cells does not match the receiver topology at flat cell "
                         "%d: %d != %d (a forged or stale count is never used to certify "
                         "a mainstem)" % (index, int(flat_up[index]), int(totals[index])))


def _root_table(receiver, valid_mask, terminal_kind, upstream_cells, complete_mask,
                origin_native_xz):
    """Roots (world-sorted), per-cell ownership, CSR members and per-root status."""
    rows, columns = receiver.shape
    origin_x, origin_z = origin_native_xz
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    flat_kind = terminal_kind.reshape(-1)
    flat_complete = complete_mask.reshape(-1)

    terminal = _terminal_of_cell(receiver, valid_mask)
    root_flat = np.flatnonzero(flat_valid & (flat_receiver < 0))
    if root_flat.size == 0:
        raise ValueError("%s: the finite receiver graph has no structural terminal"
                         % REASON_NO_ROOT)
    root_rows = root_flat // columns
    root_columns = root_flat % columns
    root_flat = root_flat[np.lexsort((root_rows, root_columns))]
    root_count = int(root_flat.size)

    lookup = np.full(flat_receiver.size, -1, np.int64)
    lookup[root_flat] = np.arange(root_count, dtype=np.int64)
    owner_flat = np.where(flat_valid, lookup[np.maximum(terminal, 0)], -1).astype(np.int64)
    if np.any(flat_valid & (owner_flat < 0)):
        raise RuntimeError("a valid cell is not attached to a structural root")
    if np.any(~flat_valid & (owner_flat != -1)):
        raise RuntimeError("an inactive cell carries an owner")

    selected = np.flatnonzero(flat_valid)
    selected_owner = owner_flat[selected]
    selected_x = origin_x + (selected % columns)
    selected_z = origin_z + (selected // columns)
    order = np.lexsort((selected_z, selected_x, selected_owner))
    member_cells = selected[order].astype(np.int64)
    member_owner = selected_owner[order]
    member_world = np.stack([selected_x[order], selected_z[order]], axis=1).astype(np.int64)

    member_counts = np.bincount(member_owner, minlength=root_count).astype(np.int64)
    member_ptr = np.zeros(root_count + 1, np.int64)
    np.cumsum(member_counts, out=member_ptr[1:])
    # The root of a structural catchment receives every one of its members, so its
    # upstream cell count and its member count are the same number. Two independent
    # paths to it (accumulated kernel, member CSR) must agree.
    upstream_flat_all = np.asarray(upstream_cells, np.int64).reshape(-1)
    for index in range(root_count):
        if int(upstream_flat_all[root_flat[index]]) != int(member_counts[index]):
            raise RuntimeError("root %d has %d accumulated upstream cells but %d "
                               "members; the completeness/membership tables disagree"
                               % (index, int(upstream_flat_all[root_flat[index]]),
                                  int(member_counts[index])))

    members_sha = np.empty(root_count, dtype="U64")
    unknown_counts = np.zeros(root_count, np.int64)
    member_complete = flat_complete[member_cells]
    np.add.at(unknown_counts, member_owner[~member_complete], 1)
    for index in range(root_count):
        low = int(member_ptr[index])
        high = int(member_ptr[index + 1])
        members_sha[index] = _sha_world_pairs(member_world[low:high])

    root_kind = np.array([str(flat_kind[cell]) for cell in root_flat], dtype="U24")
    root_complete = unknown_counts == 0
    world_flat = _world_flat(np.arange(flat_receiver.size, dtype=np.int64),
                             origin_native_xz, columns)

    candidates = []
    for index in range(root_count):
        kind = str(root_kind[index])
        closed = bool(root_complete[index])
        if closed and kind != "retained":
            raise RuntimeError("only a retained root can have a complete declared "
                               "upstream; %r reported complete" % kind)
        if closed:
            status = STATUS_CLOSED
            reasons = [REASON_COMPLETE]
        elif kind == "unknown_boundary":
            status = STATUS_TRUNCATED
            reasons = [REASON_SUPPORT_TRUNCATED, REASON_UPSTREAM_UNKNOWN]
        else:
            status = STATUS_OPEN_UPSTREAM
            reasons = [REASON_UPSTREAM_UNKNOWN]
        root_cell = int(root_flat[index])
        candidates.append({
            "root_cell": root_cell,
            "root_world_xz": [int(world_flat[root_cell, 0]),
                              int(world_flat[root_cell, 1])],
            "root_kind": kind,
            "member_count": int(member_counts[index]),
            "member_sha256": str(members_sha[index]),
            "status": status,
            "reason_codes": reasons,
            # A retained root is the terminal of a finite graph: it is a basin
            # awaiting C-stage evidence, never a lake and never an ocean outlet.
            "physical_endpoint_evidence": "basin_pending" if kind == "retained" else "none",
        })

    return {
        "root_flat": root_flat,
        "root_count": root_count,
        "root_world": world_flat[root_flat],
        "root_kind": root_kind,
        "root_complete": root_complete.astype(bool),
        "owner_flat": owner_flat,
        "owner": owner_flat.reshape(rows, columns),
        "member_cells": member_cells,
        "member_owner": member_owner,
        "member_world": member_world,
        "member_counts": member_counts,
        "member_ptr": member_ptr,
        "members_sha256": members_sha,
        "unknown_member_counts": unknown_counts,
        "candidates": candidates,
        "world_flat": world_flat,
    }


# --------------------------------------------------------------------------- #
# 4. public catchments
# --------------------------------------------------------------------------- #
def root_catchments(*, receiver, valid_mask, terminal_kind, upstream_unknown_mask,
                    origin_native_xz, max_cells=MAX_SUPPORT_CELLS):
    """Structural catchments of a supplied finite receiver graph.

    Upstream counts and the propagated completeness come from **one** call of
    ``accumulate_network_discharge`` with ``local_q == 1``; a caller's own
    ``complete_mask`` is not accepted, because the whole point is that this function
    re-derives completeness from the declared topology.

    Returns ``root_cell``, ``catchment_of_cell`` (``-1`` = non-member),
    ``member_count``, ``members_sha256``, ``upstream_complete``,
    ``unknown_member_count`` and ``root_kind``, plus the derived arrays the candidate
    bundle also needs. ``members_sha256`` is kept under that name here so an existing
    draft caller does not break; the candidate dictionary uses ``member_sha256``.
    """
    receiver = _check_int_grid(receiver, "receiver")
    valid_mask = _check_bool_grid(valid_mask, "valid_mask", receiver.shape)
    origin = _int_pair(origin_native_xz, "origin_native_xz")
    budget = _strict_int(max_cells, "max_cells")
    if budget <= 0 or budget > MAX_SUPPORT_CELLS:
        raise ValueError("budget_exceeded: max_cells %d outside 1..%d"
                         % (budget, MAX_SUPPORT_CELLS))
    if receiver.size > budget:
        raise ValueError("budget_exceeded: %d cells exceeds max_cells=%d"
                         % (receiver.size, budget))
    receiver, valid_mask = _check_receiver_adjacency(receiver, valid_mask, origin_native_xz=origin)
    kinds = _check_kind_grid(terminal_kind, receiver.shape)
    seeds = _check_bool_grid(upstream_unknown_mask, "upstream_unknown_mask",
                             receiver.shape)
    if np.any(seeds[~valid_mask]):
        raise ValueError("inactive cells cannot seed an unknown upstream")
    # The structural root count is known from the mask alone, so the root and byte
    # budgets refuse before the accumulation allocates anything full-extent.
    _check_bundle_budget(receiver.size, int((valid_mask & (receiver < 0)).sum()))
    upstream, complete = _accumulated_counts(receiver, valid_mask, kinds, seeds, budget)
    table = _root_table(receiver, valid_mask, kinds, upstream, complete, origin)
    return {
        "root_cell": table["root_flat"],
        "root_world_xz": table["root_world"],
        "root_kind": table["root_kind"],
        "catchment_of_cell": table["owner"],
        "member_count": table["member_counts"],
        "member_ptr": table["member_ptr"],
        "member_cells": table["member_cells"],
        "members_sha256": table["members_sha256"],
        "upstream_complete": table["root_complete"],
        "unknown_member_count": table["unknown_member_counts"],
        "status": [item["status"] for item in table["candidates"]],
        "reason_codes": [item["reason_codes"] for item in table["candidates"]],
        "upstream_cells": upstream,
        "complete_mask": complete,
        "origin_native_xz": list(origin),
    }


# --------------------------------------------------------------------------- #
# 5. grids
# --------------------------------------------------------------------------- #
def _check_int_grid(array, name, shape=None):
    if (not isinstance(array, np.ndarray) or array.dtype != np.int64 or array.ndim != 2
            or min(array.shape) < 1):
        raise ValueError("%s must be a non-empty int64 [Z,X] array" % name)
    if shape is not None and array.shape != shape:
        raise ValueError("%s must have shape %s, got %s" % (name, list(shape),
                                                            list(array.shape)))
    return np.ascontiguousarray(array, np.int64)


def _check_bool_grid(array, name, shape):
    if (not isinstance(array, np.ndarray) or array.dtype != np.bool_
            or array.shape != shape):
        raise ValueError("%s must be a boolean array of shape %s" % (name, list(shape)))
    return np.ascontiguousarray(array, bool)


def _check_kind_grid(kinds, shape):
    if (not isinstance(kinds, np.ndarray) or kinds.dtype.kind != "U"
            or kinds.shape != shape):
        raise ValueError("terminal_kind must be a Unicode array of shape %s"
                         % (list(shape),))
    if not np.isin(kinds, TERMINAL_LABELS).all():
        raise ValueError("terminal_kind may only use %s" % (list(TERMINAL_LABELS),))
    return kinds


OWNER_RULE = (
    "one owner per valid cell: the structural terminal its receiver chain reaches; "
    "invalid cells carry -1; neighbouring owners share one canonical D4 world pair")


def _candidate_id(metadata, root_world_xz, member_sha256_value, root_kind, status):
    """World-anchored logical identity of one candidate.

    The payload is deliberately *outside* the support: world seed, lattice, plan
    version, owner rule, the root's world coordinate, its member digest, its graph
    label and its completeness status. Nothing local (support origin/shape, flat
    index, root number, page path) enters, so the same world root keeps the same id
    when an unrelated basin is added to the support.
    """
    payload = {
        "algorithm": "metric-world-domain-candidate",
        "logical_version": LOGICAL_VERSION,
        "world_seed": metadata["world_seed"],
        "spacing_m": metadata["spacing_m"],
        "plan_version": metadata["plan_version"],
        "owner_rule": OWNER_RULE,
        "root_world_xz": [int(root_world_xz[0]), int(root_world_xz[1])],
        "member_sha256": member_sha256_value,
        "root_kind": root_kind,
        "status": status,
    }
    return "wdc-" + identity({}, payload)


def _check_elevation(array, shape):
    if (not isinstance(array, np.ndarray) or array.dtype != np.float64
            or array.shape != shape):
        raise ValueError("elevation_m must be a float64 array of shape %s"
                         % (list(shape),))
    return np.ascontiguousarray(array, np.float64)


# --------------------------------------------------------------------------- #
# 6. mainstem
# --------------------------------------------------------------------------- #
def _walk_mainstem(root_flat, donors_sorted, donor_pointer, upstream_flat,
                   elevation_flat, world_flat, flat_receiver, columns):
    """Source→root chain of one root: largest upstream count, tie by world ``(x,z)``.

    Area only chooses *which* donor continues the chain; it is not hydraulic
    evidence. Every step is asserted: the donor must be the actual irregular graph receiver
    target of its upstream cell, must follow the validated graph, and the elevation must decrease
    strictly (this chain has no flat-slope exception).
    """
    chain = [int(root_flat)]
    current = int(root_flat)
    while True:
        low = int(donor_pointer[current])
        high = int(donor_pointer[current + 1])
        if high <= low:
            break
        donors = donors_sorted[low:high]
        counts = upstream_flat[donors]
        best = int(counts.max())
        tied = donors[counts == best]
        if tied.size > 1:
            # ``(x, z)`` lexicographic, primary x: not the (row, column) order.
            pick = int(tied[np.lexsort((world_flat[tied, 1], world_flat[tied, 0]))[0]])
        else:
            pick = int(tied[0])
        chain.append(pick)
        current = pick
    ordered = chain[::-1]
    for index in range(len(ordered) - 1):
        here = ordered[index]
        following = ordered[index + 1]
        if int(flat_receiver[here]) != following:
            raise ValueError("%s: the mainstem step %d->%d is not a receiver edge"
                             % (REASON_ROOT_NOT_TERMINAL, here, following))
        if not elevation_flat[here] > elevation_flat[following]:
            raise ValueError("the mainstem must descend strictly; cell %d is not above "
                             "cell %d" % (here, following))
    if int(flat_receiver[ordered[-1]]) >= 0:
        raise ValueError("%s: the mainstem does not end at the requested root"
                         % REASON_ROOT_NOT_TERMINAL)
    return ordered


def mainstem_chain(*, receiver, valid_mask, upstream_cells, root_cell,
                   origin_native_xz, elevation_m, max_cells=MAX_SUPPORT_CELLS):
    """One root's complete source→root mainstem over the *existing* receiver graph.

    ``upstream_cells`` must come from the shared accumulation kernel; this function
    re-checks it against the receiver topology (``count == 1 + sum(donor counts)``)
    before choosing anything, so a fabricated count array cannot certify a chain. No
    second irregular graph and no second accumulation is run.
    """
    receiver = _check_int_grid(receiver, "receiver")
    valid_mask = _check_bool_grid(valid_mask, "valid_mask", receiver.shape)
    elevation = _check_elevation(elevation_m, receiver.shape)
    counts = _check_int_grid(upstream_cells, "upstream_cells", receiver.shape)
    origin = _int_pair(origin_native_xz, "origin_native_xz")
    budget = _strict_int(max_cells, "max_cells")
    if budget <= 0 or budget > MAX_SUPPORT_CELLS or receiver.size > budget:
        raise ValueError("budget_exceeded: %d cells outside 1..%d"
                         % (receiver.size, MAX_SUPPORT_CELLS))
    rows, columns = receiver.shape
    receiver, valid_mask = _check_receiver_adjacency(receiver, valid_mask, origin_native_xz=origin)
    flat_receiver = receiver.reshape(-1)
    root = _strict_int(root_cell, "root_cell")
    if not 0 <= root < receiver.size:
        raise ValueError("root_cell %d is outside the grid" % root)
    if not bool(valid_mask.reshape(-1)[root]):
        raise ValueError("%s: the root must be a valid cell" % REASON_ROOT_NOT_TERMINAL)
    if int(flat_receiver[root]) >= 0:
        raise ValueError("%s: the root must be a structural terminal (receiver -1)"
                         % REASON_ROOT_NOT_TERMINAL)
    if not np.isfinite(elevation[valid_mask]).all():
        raise ValueError("resolved cells must carry finite elevation")
    _check_upstream_counts(receiver, valid_mask, counts)

    donors_sorted, donor_pointer = _donor_csr(receiver, valid_mask)
    world_flat = _world_flat(np.arange(receiver.size, dtype=np.int64), origin, columns)
    ordered = _walk_mainstem(root, donors_sorted, donor_pointer, counts.reshape(-1),
                            elevation.reshape(-1), world_flat, flat_receiver, columns)
    chain_world = world_flat[np.asarray(ordered, np.int64)]
    node_count = len(ordered)
    return {
        "root_cell": root,
        "root_world_xz": [int(world_flat[root, 0]), int(world_flat[root, 1])],
        "chain_cells_ordered": np.asarray(ordered, np.int64),
        "chain_world_xz": np.ascontiguousarray(chain_world, np.int64),
        "chain_sha256": _sha_world_pairs(chain_world),
        # Both counts are reported: a chain of L cells has L nodes and L-1 edges, and
        # no caller should have to infer which number it received.
        "node_count": node_count,
        "edges": node_count - 1,
        "elevation_span_m": float(elevation.reshape(-1)[ordered[0]]
                                  - elevation.reshape(-1)[ordered[-1]]),
        "selection_policy": ("largest upstream cell count, ties by the donor's world "
                             "(x,z); area selects the chain, it is not hydraulic evidence"),
    }


# --------------------------------------------------------------------------- #
# 7. segments (counts only; reach slicing belongs to metric_world_reaches)
# --------------------------------------------------------------------------- #
def _segment_inputs(receiver, valid_mask, reach_of_cell):
    receiver = _check_int_grid(receiver, "receiver")
    valid_mask = _check_bool_grid(valid_mask, "valid_mask", receiver.shape)
    reach = _check_int_grid(reach_of_cell, "reach_of_cell", receiver.shape)
    flat_reach = reach.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    if np.any(flat_reach[~flat_valid] != -1):
        raise ValueError("inactive cells must carry reach_of_cell == -1")
    if np.any(flat_reach[flat_valid] < 0):
        raise ValueError("every valid cell belongs to exactly one reach")
    count = int(flat_reach.max()) + 1
    present = np.unique(flat_reach[flat_valid])
    if present.size != count or not np.array_equal(present, np.arange(count)):
        raise ValueError("reach ids must be dense 0..R-1")
    return receiver, valid_mask, reach, count


def _segment_tables(receiver, valid_mask, reach_of_cell):
    """One grouped pass over the cells: donor counts, heads and cell counts per reach.

    Grouped by reach id (``bincount``/``argsort``), never by scanning the grid once per
    reach, so the cost stays ``O(N log N)`` however many reaches there are.
    """
    receiver, valid_mask, reach, count = _segment_inputs(receiver, valid_mask, reach_of_cell)
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    flat_reach = reach.reshape(-1)
    source = np.flatnonzero(flat_valid & (flat_receiver >= 0))
    target = flat_receiver[source]
    same = flat_reach[source] == flat_reach[target]

    donors = np.bincount(flat_reach[target][~same], minlength=count).astype(np.int64)
    inside = np.bincount(target[same], minlength=flat_receiver.size).astype(np.int64)
    total = np.bincount(target, minlength=flat_receiver.size).astype(np.int64)
    cell_counts = np.bincount(flat_reach[flat_valid], minlength=count).astype(np.int64)

    head_index = np.flatnonzero(flat_valid & (inside == 0))
    head_reach = flat_reach[head_index]
    head_count = np.bincount(head_reach, minlength=count).astype(np.int64)
    head = np.zeros(count, np.int64)
    head[head_reach] = head_index
    return {"donors": donors, "inside": inside, "total": total,
            "cell_counts": cell_counts, "head": head, "head_count": head_count,
            "receiver_flat": flat_receiver, "reach_flat": flat_reach,
            "valid_flat": flat_valid, "reach_count": count}


def _donors_from_table(table):
    """Apply the two segment assertions to an already-grouped table."""
    donors = table["donors"]
    bad = np.flatnonzero(table["head_count"] != 1)
    if bad.size:
        identity = int(bad[0])
        raise RuntimeError("%s: reach %d has %d head cells; a segment is a single chain "
                           "(cells of one reach may not feed each other twice)"
                           % (REASON_SEGMENT_DONOR_MISMATCH, identity,
                              int(table["head_count"][identity])))
    expected = table["total"][table["head"]]
    wrong = np.flatnonzero(expected != donors)
    if wrong.size:
        identity = int(wrong[0])
        raise RuntimeError("%s: reach %d reports %d upstream segments but its head cell "
                           "has %d donors (an intra-segment edge is not an upstream "
                           "segment)" % (REASON_SEGMENT_DONOR_MISMATCH, identity,
                                         int(donors[identity]), int(expected[identity])))
    return donors


def segment_donors(receiver, valid_mask, reach_of_cell):
    """Upstream *segment* count per reach: cross-segment edges only.

    An edge inside a reach is not an upstream segment; counting it was the range
    prototype's ``L-1`` mistake. A legal one-cell source or confluence reach keeps
    its own count (0 for a source, the number of feeding reaches otherwise) -- it is
    never dropped because it is short.
    """
    return _donors_from_table(_segment_tables(receiver, valid_mask, reach_of_cell))


def segment_retention(receiver, valid_mask, reach_of_cell):
    """Which reaches to keep: everything except a pure terminal sentinel segment.

    Only a one-cell reach whose single cell is a terminal can be a sentinel (the
    ``(donors != 1) | outlets`` artefact). A one-cell *source* or *confluence* reach is
    legal and is kept, and so is every multi-cell reach.
    """
    table = _segment_tables(receiver, valid_mask, reach_of_cell)
    donors = _donors_from_table(table)
    single = table["cell_counts"] == 1
    terminal = table["receiver_flat"][table["head"]] < 0
    sentinel = single & terminal
    source = single & ~terminal & (donors == 0)
    confluence = single & ~terminal & (donors > 0)
    reasons = np.full(table["reach_count"], "chain", dtype="U32")
    reasons[sentinel] = "terminal_sentinel"
    reasons[source] = "single_cell_source"
    reasons[confluence] = "single_cell_confluence"
    return {"keep": ~sentinel, "sentinel": sentinel, "single": single,
            "source": source, "confluence": confluence, "reason_codes": reasons,
            "segment_donors": donors}


# --------------------------------------------------------------------------- #
# 8. shared divides
# --------------------------------------------------------------------------- #
def _shared_face_pairs(owner, valid_mask):
    """Canonical D4 pairs between two different owners, world-pair de-duplicated.

    Only right and down neighbours are enumerated, so each D4 edge appears once and
    the first cell of a pair is always the world-lexicographically smaller one
    (``x`` then ``z``). The world pair is the identity; the returned flat indices are
    only a positioning convenience.
    """
    rows, columns = owner.shape
    index = np.arange(rows * columns, dtype=np.int64).reshape(rows, columns)
    left = owner[:, :-1]
    right = owner[:, 1:]
    horizontal = (valid_mask[:, :-1] & valid_mask[:, 1:] & (left >= 0) & (right >= 0)
                  & (left != right))
    first = index[:, :-1][horizontal]
    second = index[:, 1:][horizontal]
    upper = owner[:-1, :]
    lower = owner[1:, :]
    vertical = (valid_mask[:-1, :] & valid_mask[1:, :] & (upper >= 0) & (lower >= 0)
                & (upper != lower))
    first = np.concatenate([first, index[:-1, :][vertical]])
    second = np.concatenate([second, index[1:, :][vertical]])
    if first.size == 0:
        return np.zeros((0, 2), np.int64), np.zeros((0, 4), np.int64)
    if np.any(first >= second):
        raise RuntimeError("a shared-face pair is not in canonical order")
    code = first * np.int64(rows * columns) + second
    _, unique = np.unique(code, return_index=True)
    first = first[unique]
    second = second[unique]
    first_x = first % columns
    first_z = first // columns
    second_x = second % columns
    second_z = second // columns
    order = np.lexsort((second_z, second_x, first_z, first_x))
    pairs = np.stack([first[order], second[order]], axis=1).astype(np.int64)
    world = np.stack([first_x[order], first_z[order], second_x[order],
                      second_z[order]], axis=1).astype(np.int64)
    return pairs, world


def _cross_owner_drain(owner, receiver, valid_mask):
    flat_owner = owner.reshape(-1)
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    source = np.flatnonzero(flat_valid & (flat_receiver >= 0))
    target = flat_receiver[source]
    crossing = flat_owner[source] != flat_owner[target]
    if not crossing.any():
        return np.zeros((0, 2), np.int64)
    return np.stack([source[crossing], target[crossing]], axis=1).astype(np.int64)


def shared_divides(*, owner, receiver, valid_mask, support):
    """Canonical shared divides of one owner grid, and any cross-owner irregular graph drainage.

    The pair set is symmetric by construction: relabelling the owners cannot change
    it. A ``receiver`` edge that points at a cell of another owner is
    ``cross_domain_drain`` -- it is reported and refuses the candidate; the receiver
    is never edited to hide it.
    """
    metadata, _ = _support_metadata(support)
    shape = tuple(metadata["shape_zx"])
    owner = _check_int_grid(owner, "owner", shape)
    receiver = _check_int_grid(receiver, "receiver", shape)
    valid_mask = _check_bool_grid(valid_mask, "valid_mask", shape)
    flat_owner = owner.reshape(-1)
    flat_valid = valid_mask.reshape(-1)
    if np.any(flat_owner[~flat_valid] != -1):
        raise ValueError("%s: an inactive cell must carry owner -1" % REASON_OWNER_OVERLAP)
    if np.any(flat_owner[flat_valid] < 0):
        raise ValueError("%s: every valid cell needs an owner before divides can be "
                         "compared" % REASON_OWNER_GAP)
    pairs, world = _shared_face_pairs(owner, valid_mask)
    crossing = _cross_owner_drain(owner, receiver, valid_mask)
    reasons = []
    if crossing.shape[0]:
        reasons.append(REASON_CROSS_DOMAIN_DRAIN)
    support_identity = identity({}, metadata)
    info = {
        "schema": "metric-world-shared-divides-v1",
        "owner_count": int(flat_owner[flat_valid].max()) + 1,
        "pair_count": int(pairs.shape[0]),
        "cross_domain_drain_count": int(crossing.shape[0]),
        "reason_codes": reasons,
        "support_identity_sha256": support_identity,
        "policy": ("D4 shared faces are stored as canonical world pairs (x,z sorted) "
                   "and de-duplicated; a irregular graph edge across owners is cross_domain_drain "
                   "and refuses the candidate, and the receiver is never edited to "
                   "hide it"),
    }
    return {
        "info": info,
        "pairs_local": pairs,
        "pairs_world": world,
        "cross_domain_drain_local": crossing,
        "identity_sha256": identity(
            {"pairs_local": pairs, "cross_domain_drain_local": crossing}, info),
    }


# --------------------------------------------------------------------------- #
# 9. source declaration
# --------------------------------------------------------------------------- #
def _source_block(metadata, source, source_kind):
    """Validate the loaded-source declaration and bind it to the support.

    ``source`` is the result of ``load_native_window`` (or an explicit synthetic
    fixture). The page pins, the seed, the lattice, the origin and the shape are
    compared item by item. What comes back is a *declaration*: the content digest of
    the field and mask is recomputed here, but no page is re-read and nothing is
    re-authenticated -- checksums are not signatures.
    """
    if source_kind not in SOURCE_KINDS:
        raise ValueError("source_kind must be one of %s, got %r"
                         % (list(SOURCE_KINDS), source_kind))
    if not isinstance(source, dict):
        raise ValueError("source must be the result of load_native_window")
    forbidden = sorted(set(FORBIDDEN_SOURCE_KEYS) & set(source))
    if forbidden:
        raise ValueError("%s: source may not carry %s; the receiver graph, the "
                         "completeness and the ownership are rebuilt from the field "
                         "and mask" % (REASON_UNPREPARED, forbidden))
    shape = tuple(metadata["shape_zx"])
    origin = list(metadata["origin_native_xz"])
    for key in ("field", "resolved_mask"):
        if key not in source:
            raise ValueError("source must carry %r (the loaded window)" % key)
    declared_origin = source.get("origin_native_xz")
    declared_shape = source.get("shape_zx")
    declared_seed = source.get("world_seed")
    declared_spacing = source.get("spacing_m")
    if source_kind == SOURCE_KIND_PINNED:
        for key, value in (("origin_native_xz", declared_origin),
                           ("shape_zx", declared_shape),
                           ("world_seed", declared_seed),
                           ("spacing_m", declared_spacing),
                           ("source_records", source.get("source_records")),
                           ("assembly_digest", source.get("assembly_digest"))):
            if value is None:
                raise ValueError("%s: a td_pinned source must declare %r; pass an "
                                 "explicit source_kind='synthetic_fixture' for a "
                                 "synthetic terrain" % (REASON_UNPREPARED, key))
    if declared_origin is not None and _int_pair(declared_origin, "source origin") != origin:
        raise ValueError("source origin %s does not match the support origin %s"
                         % (list(declared_origin), origin))
    if declared_shape is not None and tuple(_shape_pair(declared_shape)) != shape:
        raise ValueError("source shape %s does not match the support shape %s"
                         % (list(declared_shape), list(shape)))
    if declared_seed is not None and _strict_int(declared_seed, "source world_seed") != metadata["world_seed"]:
        raise ValueError("seed_mismatch: source world_seed %r is not the support seed %d"
                         % (declared_seed, metadata["world_seed"]))
    if declared_spacing is not None and _strict_float(declared_spacing, "source spacing_m") != metadata["spacing_m"]:
        raise ValueError("spacing_mismatch: source spacing %r is not the support spacing %r"
                         % (declared_spacing, metadata["spacing_m"]))

    block = {
        "source_kind": source_kind,
        "declared_keys": sorted(source),
        "origin_native_xz": origin,
        "shape_zx": list(shape),
        "world_seed": metadata["world_seed"],
        "spacing_m": metadata["spacing_m"],
    }
    if source_kind == SOURCE_KIND_PINNED:
        records = _pins_of(source.get("source_records"), "sha256")
        if records != metadata["source_records"]:
            raise ValueError("pin_mismatch: the source page pins are not the pins the "
                             "support froze (path or sha256 differ)")
        block["source_records"] = records
        block["source_record_count"] = len(records)
        block["assembly_digest"] = _sha_text(source.get("assembly_digest"),
                                            "assembly_digest")
        block["source_verification"] = SOURCE_VERIFICATION_PINNED
        block["source_identity_policy"] = (
            "page pins + assembly digest as declared by the loader, bound to the "
            "content digest below; a checksum is not a signature")
    else:
        block["source_records"] = []
        block["source_record_count"] = 0
        block["assembly_digest"] = None
        block["source_verification"] = SOURCE_VERIFICATION_SYNTHETIC
        block["source_identity_policy"] = (
            "synthetic fixture: no TD page pin is claimed, the content digest is the "
            "only source identity, and the result is not a TD-sourced product")
    block["field_mask_sha256"] = identity(
        {"elevation_m": np.ascontiguousarray(source["field"], np.float64),
         "resolved_mask": np.ascontiguousarray(source["resolved_mask"], bool)},
        {"origin_native_xz": origin, "shape_zx": list(shape),
         "world_seed": metadata["world_seed"], "spacing_m": metadata["spacing_m"]})
    return block


def _field_and_mask(source, metadata):
    """The exact elevation/mask pair, with the loader's unresolved convention kept.

    A resolved cell must carry a finite height. An unresolved cell must carry NaN and
    nothing else: that is what ``load_native_window`` leaves, and accepting a height or
    a zero there would let an unknown be presented as terrain in the very array the
    bundle publishes and hashes. The pair is copied, never rewritten.
    """
    shape = tuple(metadata["shape_zx"])
    field = _check_elevation(source.get("field"), shape)
    mask = _check_bool_grid(source.get("resolved_mask"), "resolved_mask", shape)
    if not mask.any():
        raise ValueError("no resolved cells: an all-unknown window has no topology")
    if not np.isfinite(field[mask]).all():
        raise ValueError("resolved cells must carry finite elevation; unresolved "
                         "values stay NaN and are ignored")
    if not np.isnan(field[~mask]).all():
        raise ValueError(
            "%s: an unresolved cell must carry NaN, not a height or a zero; filling a "
            "hole would disguise an unknown as terrain" % REASON_UNPREPARED)
    return field.copy(), mask.copy()


# --------------------------------------------------------------------------- #
# 10. the candidate bundle
# --------------------------------------------------------------------------- #
def _module_source_sha256(name):
    if name not in _SHA_CACHE:
        module = importlib.import_module(name)
        path = getattr(module, "__file__", None)
        _SHA_CACHE[name] = (hashlib.sha256(Path(path).read_bytes()).hexdigest()
                            if path and Path(path).is_file() else None)
    return _SHA_CACHE[name]


def _dependency_sha256():
    return {name: _module_source_sha256(name) for name in (
        "terrain_pipeline.surface_rivers.metric_world_domains",
        "terrain_pipeline.surface_rivers.native_30m_source",
        'terrain_pipeline.drainage',
        "terrain_pipeline.surface_rivers.metric_network_discharge_product",
        "terrain_pipeline.surface_rivers.metric_domain_closure",
        "terrain_pipeline.common_infra",
    )}


def _build(metadata, support_identity, block, field, mask):
    """Rebuild the whole candidate layer from a support, a source block and the grids.

    ``domain_candidates`` and :func:`validate_domain_candidates` both go through this
    one path, so validation is a recomputation and not a comparison of two
    independent implementations of the same rule.
    """
    rows, columns = metadata["shape_zx"]
    origin = list(metadata["origin_native_xz"])
    budget = metadata["max_cells"]
    cells = int(field.size)
    if cells > MAX_SUPPORT_CELLS or cells > budget:
        raise ValueError("budget_exceeded: %d cells exceeds the declared support budget %d"
                         % (cells, min(MAX_SUPPORT_CELLS, budget)))
    if tuple(field.shape) != (rows, columns) or tuple(mask.shape) != (rows, columns):
        raise ValueError("the source grids do not match the declared support shape")

    topology = build_strict_topology(field, mask, origin_native_xz=origin,
                                     world_seed=metadata.get("world_seed", 20261020))
    receiver = np.ascontiguousarray(topology["receiver"], np.int64)
    kinds = topology["terminal_kind"]
    seeds = np.ascontiguousarray(topology["upstream_unknown_mask"], bool)
    if np.any(kinds == "open_outflow"):
        raise RuntimeError("a finite support never certifies an open outflow")
    # Roots come from the mask and the receiver alone, so the root and byte budgets are
    # checked before the accumulation and the CSR tables are built.
    _check_bundle_budget(cells, int((mask & (receiver < 0)).sum()))
    upstream, complete = _accumulated_counts(receiver, mask, kinds, seeds, budget)

    table = _root_table(receiver, mask, kinds, upstream, complete, origin)
    root_count = table["root_count"]
    donors_sorted, donor_pointer = _donor_csr(receiver, mask)
    flat_receiver = receiver.reshape(-1)
    upstream_flat = upstream.reshape(-1)
    elevation_flat = field.reshape(-1)
    world_flat = table["world_flat"]

    chains = []
    mainstem_sha = []
    for index in range(root_count):
        ordered = _walk_mainstem(int(table["root_flat"][index]), donors_sorted,
                                donor_pointer, upstream_flat, elevation_flat,
                                world_flat, flat_receiver, columns)
        chains.append(ordered)
        mainstem_sha.append(_sha_world_pairs(world_flat[np.asarray(ordered, np.int64)]))

    mainstem_counts = np.array([len(chain) for chain in chains], np.int64)
    mainstem_ptr = np.zeros(root_count + 1, np.int64)
    np.cumsum(mainstem_counts, out=mainstem_ptr[1:])
    mainstem_cells = (np.concatenate([np.asarray(chain, np.int64) for chain in chains])
                      if chains else np.zeros(0, np.int64))

    owner = table["owner"]
    pairs, pairs_world = _shared_face_pairs(owner, mask)
    crossing = _cross_owner_drain(owner, receiver, mask)
    # Ownership is *derived from* the receiver graph, so a crossing edge cannot occur
    # in a self-consistent bundle; if the table ever disagrees it is flagged on the
    # owners involved (never silently ignored) and the validation gate refuses the
    # bundle instead of repairing the receiver.
    offending = set()
    if crossing.shape[0]:
        flat_owner = owner.reshape(-1)
        for source, target in crossing.tolist():
            offending.add(int(flat_owner[source]))
            offending.add(int(flat_owner[target]))

    candidates = []
    for index, base in enumerate(table["candidates"]):
        candidate = {"candidate_id": None, "root_index": int(index)}
        candidate.update(base)
        candidate["structural_only"] = True
        candidate["evidence_level"] = "structural_candidate"
        # A chain of L cells has L-1 edges: both are stored so no downstream budget
        # has to guess which one it received.
        candidate["mainstem_node_count"] = int(mainstem_counts[index])
        candidate["mainstem_edges"] = int(mainstem_counts[index] - 1)
        candidate["mainstem_sha256"] = mainstem_sha[index]
        if index in offending:
            candidate["reason_codes"] = list(candidate["reason_codes"]) + [
                REASON_CROSS_DOMAIN_DRAIN]
            candidate["status"] = STATUS_OPEN_UPSTREAM
        candidate["candidate_id"] = _candidate_id(
            metadata, candidate["root_world_xz"], candidate["member_sha256"],
            candidate["root_kind"], candidate["status"])
        candidates.append({key: candidate[key] for key in CANDIDATE_KEYS})

    arrays = {
        "elevation_m": np.ascontiguousarray(field, np.float64),
        "resolved_mask": np.ascontiguousarray(mask, bool),
        "receiver": receiver,
        "terminal_kind": np.ascontiguousarray(kinds, TERMINAL_KIND_DTYPE),
        "upstream_unknown_mask": seeds,
        "complete_mask": complete,
        "upstream_cells": upstream,
        "owner_index": np.ascontiguousarray(owner, np.int64),
        "root_cells": np.ascontiguousarray(table["root_flat"], np.int64),
        "root_complete": np.ascontiguousarray(table["root_complete"], bool),
        "member_counts": np.ascontiguousarray(table["member_counts"], np.int64),
        "member_ptr": np.ascontiguousarray(table["member_ptr"], np.int64),
        "member_cells": np.ascontiguousarray(table["member_cells"], np.int64),
        "mainstem_ptr": mainstem_ptr,
        "mainstem_cells": mainstem_cells,
        "shared_face_cells": pairs,
    }

    closed = sum(1 for item in candidates if item["status"] == STATUS_CLOSED)
    truncated = sum(1 for item in candidates if item["status"] == STATUS_TRUNCATED)
    open_upstream = sum(1 for item in candidates if item["status"] == STATUS_OPEN_UPSTREAM)
    metadata_out = {
        "schema": SCHEMA,
        "support_identity_sha256": support_identity,
        "support": {
            "world_seed": metadata["world_seed"],
            "spacing_m": metadata["spacing_m"],
            "origin_native_xz": origin,
            "shape_zx": list(metadata["shape_zx"]),
            "support_cells": metadata["support_cells"],
            "max_cells": metadata["max_cells"],
            "plan_version": metadata["plan_version"],
            "storage_representation": metadata["storage_representation"],
            "range_native": metadata["range_native"],
            "source_record_count": metadata["source_record_count"],
            "source_sha256": metadata["source_sha256"],
            "coordinate_rule": metadata["coordinate_rule"],
        },
        "source_kind": block["source_kind"],
        "source": block,
        "source_verification": block["source_verification"],
        "field_mask_sha256": block["field_mask_sha256"],
        "algorithm": {
            "name": "metric-world-domain-candidates",
            "version": LOGICAL_VERSION,
            "graph_authority": ("terrain_pipeline.surface_rivers.native_30m_source."
                             "build_strict_topology (the one irregular graph authority of this chain)"),
            "accumulation": ("terrain_pipeline.surface_rivers.metric_network_accumulation."
                             "accumulate_network_discharge with local_q == 1"),
            "mainstem": ("root-reverse walk over one donor CSR; largest upstream cell "
                         "count, ties by the donor's world (x,z); strict irregular graph adjacency "
                         "and strictly decreasing elevation every step"),
            "no_second_routing": True,
            "no_second_accumulation": True,
            "no_water_budget": True,
        },
        "algorithm_dependency_sha256": _dependency_sha256(),
        "coordinate_serialization": dict(MEMBER_SERIALIZATION),
        "member_identity_policy": MEMBER_IDENTITY_POLICY,
        "candidate_identity_policy": CANDIDATE_IDENTITY_POLICY,
        "logical_version": LOGICAL_VERSION,
        "owner_rule": OWNER_RULE,
        "coordinate_rule": metadata["coordinate_rule"],
        "completeness_policy": (
            "complete_mask comes from accumulate_network_discharge propagation of the "
            "topology's raw unknown-upstream seeds; a candidate is candidate_closed "
            "only when every one of its members is complete; a support edge and a mask "
            "hole are never outlets; an all-open result is not a pass"),
        "unresolved_policy": (
            "an unresolved cell keeps NaN in elevation_m and False in resolved_mask, "
            "exactly as the loader left it; the unresolved pattern is part of "
            "field_mask_sha256 and of the bundle identity, so a round trip must "
            "preserve it bit for bit (NaN compares equal to NaN only there)"),
        "physical_endpoint_policy": (
            "a retained root is basin_pending (a finite-graph terminal awaiting C-stage "
            "evidence); every other root is none; no lake, no endorheic basin and no "
            "ocean outlet is certified here"),
        "scope": (
            "structural candidates over one declared support; not a solution of the "
            "infinite world and not a final hydrological domain (final_domain "
            "unsupported at this stage)"),
        "final_domain": "unsupported",
        "evidence_level": "structural_candidate",
        "reason_vocabulary": list(REASON_VOCABULARY),
        "terminal_vocabulary": list(TERMINAL_LABELS),
        "counts": {
            "cells": cells,
            "valid_cells": int(mask.sum()),
            "inactive_cells": int((~mask).sum()),
            "root_count": root_count,
            "closed_candidate_count": closed,
            "truncated_candidate_count": truncated,
            "open_upstream_candidate_count": open_upstream,
            "member_cell_count": int(table["member_cells"].size),
            "mainstem_cell_count": int(mainstem_cells.size),
            "shared_face_pair_count": int(pairs.shape[0]),
            "cross_domain_drain_pair_count": int(crossing.shape[0]),
        },
        "budget": {
            "max_cells": budget,
            "max_support_cells": MAX_SUPPORT_CELLS,
            "support_cells": cells,
            "accumulation_ceiling": MAX_NETWORK_CELLS,
        },
        "plan_version": metadata["plan_version"],
    }
    return arrays, candidates, metadata_out


def domain_candidates(support, *, source, source_kind=SOURCE_KIND_PINNED):
    """Structural domain candidates of one declared support.

    ``source`` is the already-loaded window (``load_native_window``) and is never
    re-read: page pins, seed, lattice, origin and shape are compared with the support,
    and the field/mask content digest is recomputed and bound into the identity. A
    synthetic fixture must say so explicitly (``source_kind='synthetic_fixture'``) and
    is then never described as TD-sourced.

    The irregular graph topology, the completeness and the ownership are **rebuilt here** from the
    field and the resolved mask; a source that carries a ``receiver``, a
    ``complete_mask`` or an ``owner`` is refused, so no caller can skip the rebuild.

    Returns ``{schema, support, arrays, candidates, metadata, identity_sha256}``.
    """
    metadata, support_identity = _support_metadata(support)
    canonical_support = {"arrays": {}, "metadata": metadata,
                         "identity_sha256": support_identity}
    block = _source_block(metadata, source, source_kind)
    field, mask = _field_and_mask(source, metadata)
    arrays, candidates, metadata_out = _build(metadata, support_identity, block, field, mask)
    return {
        "schema": SCHEMA,
        "support": canonical_support,
        "arrays": arrays,
        "candidates": candidates,
        "metadata": metadata_out,
        "identity_sha256": identity(arrays, metadata_out),
    }


# --------------------------------------------------------------------------- #
# 11. semantic validation
# --------------------------------------------------------------------------- #
def _compare_arrays(stored, rebuilt, mask):
    """Strict array comparison, with NaN allowed **only** where the mask is False.

    The elevation array legitimately carries NaN on unresolved cells (that is exactly
    what the loader leaves there), so a bit-exact comparison would reject a legal
    partially-covered bundle. The rule is therefore narrow and stateable:

    * ``elevation_m``: elementwise equal with NaN matching NaN (``equal_nan``), and
      NaN is required at every unresolved cell and forbidden at every resolved one.
      A resolved NaN is refused; an unresolved value filled with a height (or zero) is
      refused, because the unresolved state must survive the round trip.
    * every other array: exact equality, no tolerance, no NaN (it is integer, boolean
      or a fixed-width label).

    Nothing else is relaxed: a difference of one ULP in a derived array still fails,
    and ``field_mask_sha256`` is a content digest over the same bytes, so the
    unresolved NaN pattern is content-bound rather than merely tolerated.
    """
    if not isinstance(stored, dict) or set(stored) != set(ARRAY_NAMES):
        raise ValueError("the candidate arrays must be exactly %s" % (list(ARRAY_NAMES),))
    for name in ARRAY_NAMES:
        value = stored[name]
        expected = rebuilt[name]
        if not isinstance(value, np.ndarray) or value.dtype != expected.dtype:
            raise ValueError("array %r must have dtype %s" % (name, expected.dtype))
        if value.shape != expected.shape:
            raise ValueError("array %r must have shape %s, got %s"
                             % (name, list(expected.shape), list(value.shape)))
        if name == "elevation_m":
            if not np.array_equal(value, expected, equal_nan=True):
                raise ValueError("array 'elevation_m' does not agree with the "
                                 "recomputation from the stored elevation and resolved "
                                 "mask")
            if not np.array_equal(np.isnan(value), ~mask):
                raise ValueError(
                    "array 'elevation_m' must carry NaN exactly on the unresolved cells: a "
                    "resolved NaN is a broken input and a filled unresolved cell "
                    "disguises an unknown as terrain")
            continue
        if not np.array_equal(value, expected):
            raise ValueError("array %r does not agree with the recomputation from the "
                             "stored elevation and resolved mask" % name)


def validate_domain_candidates(bundle):
    """Recompute every derived quantity from the stored elevation and mask.

    Topology, completeness, counts, ownership, members, mainstems, shared divides and
    the identity are all recomputed and compared. Re-sealing the metadata after
    editing a derived array, an owner, a member list, a status or the completeness
    therefore cannot pass: the semantic comparison is not a digest comparison.

    Source re-authentication is *not* attempted here (a checksum is not a signature)
    and no page is read; the loader's pins remain the source boundary.
    """
    if not isinstance(bundle, dict) or set(bundle) != BUNDLE_KEYS:
        raise ValueError("a candidate bundle is %s" % (sorted(BUNDLE_KEYS),))
    if bundle["schema"] != SCHEMA:
        raise ValueError("unexpected bundle schema %r" % (bundle["schema"],))
    metadata = bundle["metadata"]
    if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA:
        raise ValueError("the bundle metadata must declare schema %r" % (SCHEMA,))
    support_metadata, support_identity = _support_metadata(bundle["support"])
    if metadata.get("support_identity_sha256") != support_identity:
        raise ValueError("the bundle is not bound to the support it declares")
    if metadata.get("plan_version") != support_metadata["plan_version"]:
        raise ValueError("the bundle plan_version does not match the support plan")
    block = metadata.get("source")
    if not isinstance(block, dict) or block.get("source_kind") not in SOURCE_KINDS:
        raise ValueError("the bundle must declare a source block with a known source_kind")
    if block["source_kind"] == SOURCE_KIND_PINNED:
        if block.get("source_records") != support_metadata["source_records"]:
            raise ValueError("pin_mismatch: the declared source pins are not the support's")

    stored = bundle["arrays"]
    if not isinstance(stored, dict):
        raise ValueError("the candidate arrays must be a mapping")
    shape = tuple(support_metadata["shape_zx"])
    field = _check_elevation(stored.get("elevation_m"), shape).copy()
    mask = _check_bool_grid(stored.get("resolved_mask"), "resolved_mask", shape).copy()
    declared_field = identity(
        {"elevation_m": np.ascontiguousarray(field, np.float64),
         "resolved_mask": np.ascontiguousarray(mask, bool)},
        {"origin_native_xz": list(support_metadata["origin_native_xz"]),
         "shape_zx": list(shape), "world_seed": support_metadata["world_seed"],
         "spacing_m": support_metadata["spacing_m"]})
    if metadata.get("field_mask_sha256") != declared_field:
        raise ValueError("the stored elevation/mask do not match the declared "
                         "field_mask_sha256")

    rebuilt_arrays, rebuilt_candidates, rebuilt_metadata = _build(
        support_metadata, support_identity, block, field, mask)
    _compare_arrays(stored, rebuilt_arrays, mask)
    if bundle["candidates"] != rebuilt_candidates:
        raise ValueError("the candidate list does not agree with the recomputation "
                         "from the stored elevation and mask")
    if metadata != rebuilt_metadata:
        raise ValueError("the bundle metadata does not agree with the recomputation; a "
                         "re-sealed derived field is still refused")
    if bundle["identity_sha256"] != identity(stored, metadata):
        raise ValueError("the bundle identity_sha256 is not the identity of its arrays "
                         "and metadata")

    # Explicit semantic assertions, so a future metadata edit cannot relax them
    # silently. Each of these follows from the rebuild; stating them keeps the refusal
    # reason precise instead of "something differed".
    owner = stored["owner_index"]
    if np.any(owner[~mask] != -1):
        raise ValueError("%s: an inactive cell carries an owner" % REASON_OWNER_OVERLAP)
    if np.any(owner[mask] < 0):
        raise ValueError("%s: a valid cell has no candidate owner" % REASON_OWNER_GAP)
    roots = stored["root_cells"]
    if np.unique(roots).size != roots.size:
        raise ValueError("%s: duplicate root cells" % REASON_NO_ROOT)
    if set(np.unique(owner[mask]).tolist()) != set(range(roots.size)):
        raise ValueError("%s: owner ids and roots disagree" % REASON_OWNER_OVERLAP)
    counts = np.bincount(owner[mask], minlength=roots.size)
    if not np.array_equal(counts, stored["member_counts"]):
        raise ValueError("member_counts does not match the owner grid")
    pointer = stored["member_ptr"]
    if pointer[0] != 0 or pointer[-1] != int(mask.sum()):
        raise ValueError("the member CSR does not cover the valid cells exactly once")
    if int(stored["shared_face_cells"].shape[0]) != metadata["counts"]["shared_face_pair_count"]:
        raise ValueError("the shared-face count is not the stored pair count")
    if metadata["counts"]["cross_domain_drain_pair_count"] != 0:
        raise ValueError("%s: an owner was split across a receiver edge"
                         % REASON_CROSS_DOMAIN_DRAIN)
    for candidate, kind, complete in zip(bundle["candidates"], stored["root_cells"],
                                        stored["root_complete"]):
        if candidate["root_kind"] not in TERMINAL_LABELS:
            raise ValueError("candidate root_kind %r is not in the terminal vocabulary"
                             % (candidate["root_kind"],))
        if candidate["root_kind"] == "open_outflow":
            raise ValueError("a finite support never certifies an open outflow")
        if bool(complete) != (candidate["status"] == STATUS_CLOSED):
            raise ValueError("candidate status and root_complete disagree")
        if candidate["physical_endpoint_evidence"] not in ("basin_pending", "none"):
            raise ValueError("this stage may only report basin_pending or none")
        if not candidate["structural_only"]:
            raise ValueError("a B1 candidate is structural only")
    return None
