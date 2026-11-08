"""B4 review: read-only IO, diagnosis and cartography over the B2 reach network.

What this tool is
-----------------
It is a **review** tool, not a producer. It reads the three pinned B evidence
packages (``evidence-b-p1-v3``, ``evidence-b-p2-v3``,
``evidence-b-p2-shifted-v3``) straight from their ``manifest.json`` + ``arrays.npz``,
rebuilds the B1 parent bundle from the declared schema/support/candidates/metadata/
identity plus the NPZ arrays, and then consumes the B2 production entry points
``metric_world_reaches.build_world_reaches`` / ``validate_world_reaches`` without
changing them.

What it adds on top of them, and only that:

1. a **machine-checkable classification table** for every root and every reach end
   point of every window -- terminal kind, upstream completeness, the pending reason,
   channel / no-channel, and downstream link / terminal-endpoint ownership;
2. an **independent per-cell walk** of the delivered receiver graph that reconstructs
   the node count, edge count, internal hop length and hand-off hop length of every
   reach, and refuses any reach whose tail does not actually continue (an internal
   un-received break is a **failure**, never a lake outlet and never a window edge);
3. **coverage assertions** over all roots and all segments (no sampling, no "a few
delegates"), so a missing classification is a refusal;
4. offline **figures**: the full network of each window over the real bed, the trunk
   highlighted, unknown / retained-pending marked explicitly, in real 30 m world
   coordinates; the legend of every panel is asserted to sit outside both its own axes
   rectangle **and the figure rectangle** (so nothing is clipped at the canvas edge), and
   the saved PNG dimensions are checked; plus a detail map of one chosen root and its
   along-trunk bed profile.

What it deliberately does **not** do
------------------------------------
No second D8, no new routing, no filling, no hydraulics, no water, no lake. The tool
never re-derives a receiver, never patches an edge, and never raises a budget: the
support ceiling stays 148 225 cells and a larger support is refused **from the declared
manifest, before any array is materialised**. ``retained`` stays ``basin_pending``;
nothing here is a lake, an outlet or a certified hydrological domain. Cell counts are
never called discharge and a segment count is never called a river count.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "metric-world-reach-review-v2"
PARENT_SCHEMA = "metric-world-domain-candidates-v1"
REACH_SCHEMA = "metric-world-reach-network-v1"
MANIFEST_NAME = "manifest.json"
ARRAYS_NAME = "arrays.npz"
DEFAULT_MIN_UPSTREAM_CELLS = 48

#: The declared supports of the B ladder. Nothing is discovered at run time and no
#: window is derived from a render window.
DECLARED_PLANS = ("p1", "p2", "p2-shifted")
EVIDENCE_DIR = ".scratch/river-lake-world-integration/evidence-b-%s-v3"

#: Support ceiling of this chain. Never raised here: a bigger support needs its own
#: declared budget and a separate review.
MAX_SUPPORT_CELLS = 148_225

#: Input gates of this tool. Every one of them is applied **before an array is
#: materialised**: the manifest is read with a byte limit and a strict parser, the NPZ
#: member headers (shape, dtype, byte count) are read straight out of the ZIP, and the
#: declared support is checked against those headers. Only then is ``allow_pickle=False``
#: loading performed. None of these limits is raised by this review.
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARRAYS_BYTES = 512 * 1024 * 1024
MAX_TOTAL_ARRAY_BYTES = 640 * 1024 * 1024
MAX_ARRAY_MEMBERS = 64
MAX_HEADER_BYTES = 4096

#: Grid-extent arrays: their NPY headers must already equal the declared support shape.
GRID_ARRAYS = ("elevation_m", "resolved_mask", "receiver", "terminal_kind",
               "upstream_unknown_mask", "complete_mask", "upstream_cells",
               "owner_index")

#: The world cell of the historical window-lake diagnosis case (report.md case 1).
HISTORICAL_CASE_WORLD_XZ = (42399, 42958)
HISTORICAL_EXPECTED_257 = 5760
HISTORICAL_EXPECTED_OTHER = 2895
WORLD_SEED = 20261020
SPACING_M = 30.0

#: Verdict words. No partial credit is added up.
PASS = "PASS"
FAILED = "FAILED"
NOT_RUN = "NOT_RUN"

#: Reach end-point classification (the vocabulary written into the tables).
LINK_HANDOFF = "handoff_to_downstream_reach"
LINK_STRUCTURAL_TERMINAL = "ends_on_structural_terminal"
LINK_EMPTY_CHANNEL = "no_channel_in_this_root"
LINK_BREAK_VALID_BELOW_GATE = "break_into_valid_cell_below_gate"
LINK_BREAK_INACTIVE = "break_into_inactive_cell"
LINK_BREAK_ROOT_MISMATCH = "break_downstream_in_other_root"
LINK_BREAK_HANDOFF_MISMATCH = "break_handoff_target_is_not_downstream_head"
LINK_BREAK_TAIL_WITHOUT_RECEIVER = "break_tail_has_no_receiver"
BREAK_LINKS = (LINK_BREAK_VALID_BELOW_GATE, LINK_BREAK_INACTIVE,
               LINK_BREAK_ROOT_MISMATCH, LINK_BREAK_HANDOFF_MISMATCH,
               LINK_BREAK_TAIL_WITHOUT_RECEIVER)

#: Reasons a terminal is pending physical evidence (never upgraded here).
PENDING_RETAINED = "basin_pending_retained_terminal"
PENDING_UNKNOWN = "unknown_boundary_needs_wider_support"
PENDING_NONE = "none"


# --------------------------------------------------------------------------- #
# time and resource observation (observations, never limits)
# --------------------------------------------------------------------------- #
def _rss_bytes():
    """Sampled RSS of this process tree, or ``None`` when psutil is unavailable."""
    try:
        import psutil
    except ImportError:                                      # observation only
        return None
    try:
        process = psutil.Process(os.getpid())
        total = process.memory_info().rss
        for child in process.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                continue
        return int(total)
    except Exception:                                        # observation only
        return None


class Stopwatch:
    """Wall time per stage plus a sampled RSS range. Both are observations."""

    def __init__(self):
        self.stages = []
        self.rss = []

    def sample(self):
        value = _rss_bytes()
        if value is not None:
            self.rss.append(value)

    def stage(self, name, function, *arguments, **keywords):
        self.sample()
        started = time.monotonic()
        result = function(*arguments, **keywords)
        elapsed = time.monotonic() - started
        self.sample()
        self.stages.append({"stage": name, "elapsed_s": round(elapsed, 3)})
        return result

    def report(self):
        observed = [value for value in self.rss if value is not None]
        return {
            "clock": "time.monotonic",
            "stages": list(self.stages),
            "elapsed_total_s": round(sum(item["elapsed_s"] for item in self.stages), 3),
            "rss_observation": {
                "samples": len(self.rss),
                "observed_min_bytes": (min(observed) if observed else None),
                "observed_max_bytes": (max(observed) if observed else None),
                "is_limit": False,
                "note": ("sampled RSS of this review process at stage boundaries; an "
                         "observation, not a resource limit and not a per-stage peak"),
            },
        }


# --------------------------------------------------------------------------- #
# 1. read-only input: the pinned evidence packages
# --------------------------------------------------------------------------- #
def array_sha256(value):
    """The declared array hash rule of the B chain: shape, dtype.str, C-order bytes."""
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(tuple(array.shape)).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_constant(value):
    raise ValueError("non_finite_json: %s" % value)


def _unique_pairs(pairs):
    parsed = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError("duplicate_json_key: %s" % key)
        parsed[key] = value
    return parsed


def read_strict_json(path, *, limit=MAX_MANIFEST_BYTES):
    """Byte gate, then a strict parse: no NaN/Inf, no duplicate keys.

    The byte limit is applied to ``stat().st_size`` before the file is read, so a huge or
    padded manifest is refused without being pulled into memory first.
    """
    target = Path(path)
    if not target.is_file():
        raise ValueError("manifest_missing: %s" % target)
    size = target.stat().st_size
    if size > limit:
        raise ValueError("manifest_bytes_exceeded: %d > %d" % (size, limit))
    raw = target.read_bytes()
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant,
                          object_pairs_hook=_unique_pairs)
    except UnicodeDecodeError as error:
        raise ValueError("manifest_not_utf8: %s" % error)
    except json.JSONDecodeError as error:
        raise ValueError("manifest_not_json: %s" % error)


def inspect_archive(path, *, max_bytes=MAX_ARRAYS_BYTES, max_members=MAX_ARRAY_MEMBERS,
                    max_total_bytes=MAX_TOTAL_ARRAY_BYTES,
                    max_header_bytes=MAX_HEADER_BYTES):
    """ZIP/NPY header gate: shape, dtype and byte totals **before any allocation**.

    Only the member headers are read. Each NPY header must be a flat ``.npy`` member whose
    declared shape and dtype account for exactly the bytes the ZIP reports, no object dtype
    and no Fortran order, so a member whose header claims one thing and holds another is
    refused without ``numpy`` ever building an array for it.
    """
    import zipfile
    target = Path(path)
    if not target.is_file():
        raise ValueError("arrays_missing: %s" % target)
    size = target.stat().st_size
    if size > max_bytes:
        raise ValueError("arrays_bytes_exceeded: %d > %d" % (size, max_bytes))
    headers = {}
    with open(target, "rb") as stream, zipfile.ZipFile(stream) as archive:
        members = archive.infolist()
        if not 1 <= len(members) <= max_members:
            raise ValueError("invalid_npz: member count %d" % len(members))
        if len({member.filename for member in members}) != len(members):
            raise ValueError("invalid_npz: duplicate member names")
        total = 0
        for member in members:
            if not member.filename.endswith(".npy") or "/" in member.filename:
                raise ValueError("invalid_npz: member is not a flat .npy: %s"
                                 % member.filename)
            with archive.open(member) as entry:
                version = np.lib.format.read_magic(entry)
                if version == (1, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(
                        entry, max_header_size=max_header_bytes)
                elif version == (2, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_2_0(
                        entry, max_header_size=max_header_bytes)
                else:
                    raise ValueError("invalid_npz: unsupported NPY version")
                header_bytes = entry.tell()
            if dtype.hasobject:
                raise ValueError("object_dtype_rejected: %s" % member.filename)
            if fortran:
                raise ValueError("fortran_order_rejected: %s" % member.filename)
            if any(int(axis) < 0 for axis in shape):
                raise ValueError("invalid_npz: negative axis in %s" % member.filename)
            payload = int(math.prod(shape)) * int(dtype.itemsize)
            if payload + header_bytes != member.file_size:
                raise ValueError("npy_header_size_mismatch: %s declares %d bytes, the "
                                 "member holds %d"
                                 % (member.filename, payload + header_bytes,
                                    member.file_size))
            total += member.file_size
            headers[member.filename[:-4]] = {"shape": [int(axis) for axis in shape],
                                            "dtype": dtype.str,
                                            "nbytes": payload}
    if total > max_total_bytes:
        raise ValueError("array_budget_exceeded: %d > %d" % (total, max_total_bytes))
    return headers


def load_arrays(path, names):
    """Materialise the declared arrays only, with ``allow_pickle=False`` stated."""
    target = Path(path)
    wanted = set(names)
    with open(target, "rb") as stream, np.load(stream, allow_pickle=False) as archive:
        present = set(archive.files)
        if present != wanted:
            raise ValueError("array_set_mismatch: headers %s vs archive %s"
                             % (sorted(wanted), sorted(present)))
        return {name: np.ascontiguousarray(archive[name]) for name in sorted(present)}


def declared_support_shape(manifest):
    """The declared support shape and cell count, read **before** any array is loaded."""
    try:
        support = manifest["support"]["metadata"]
        shape = [int(value) for value in support["shape_zx"]]
    except (KeyError, TypeError, ValueError):
        raise ValueError("support_header_missing: the manifest declares no readable "
                         "support shape") from None
    if len(shape) != 2 or min(shape) < 1:
        raise ValueError("support_header_invalid: shape_zx=%s" % (shape,))
    return shape


def check_headers(manifest, headers, support_shape):
    """Cross-bind the declared records, the NPY headers and the declared support.

    All three must agree before a single array is materialised: every declared array has a
    member, the member's own header carries the declared shape and dtype, and every
    grid-extent array already has the declared support shape. An array whose header claims
    a bigger extent than the declared support is therefore refused here, not after it has
    been allocated.
    """
    records = manifest.get("arrays")
    if not isinstance(records, dict) or not records:
        raise ValueError("the evidence manifest declares no arrays")
    missing = sorted(set(records) - set(headers))
    extra = sorted(set(headers) - set(records))
    if missing:
        raise ValueError("array_member_missing: %s" % missing)
    if extra:
        raise ValueError("array_member_undeclared: %s" % extra)
    for name, record in sorted(records.items()):
        header = headers[name]
        if header["dtype"] != record["dtype"]:
            raise ValueError("array_header_dtype_mismatch: %s header %s vs declared %s"
                             % (name, header["dtype"], record["dtype"]))
        if header["shape"] != [int(value) for value in record["shape"]]:
            raise ValueError("array_header_shape_mismatch: %s header %s vs declared %s"
                             % (name, header["shape"], list(record["shape"])))
    for name in GRID_ARRAYS:
        header = headers[name]
        if header["shape"] != list(support_shape):
            raise ValueError("grid_array_extent_mismatch: %s has shape %s but the "
                             "declared support is %s"
                             % (name, header["shape"], list(support_shape)))
    return records


def load_evidence(directory):
    """Read one evidence package and rebuild the B1 parent bundle from it.

    The order is fixed and observable: strict manifest read → declared support budget →
    NPY header gate (no allocation) → header/record/support cross-binding → only then
    ``allow_pickle=False`` loading. A support over the declared ceiling, or an array whose
    header claims a false extent, is refused **before** any array exists; that claim is
    covered by tests that mock the loader rather than by re-reading the error text.
    """
    folder = Path(directory)
    manifest_path = folder / MANIFEST_NAME
    arrays_path = folder / ARRAYS_NAME
    if not manifest_path.is_file() or not arrays_path.is_file():
        raise ValueError("evidence_package_incomplete: %s needs %s and %s"
                         % (folder, MANIFEST_NAME, ARRAYS_NAME))
    manifest = read_strict_json(manifest_path)
    if manifest.get("schema") != PARENT_SCHEMA:
        raise ValueError("unexpected evidence schema %r" % (manifest.get("schema"),))
    # 1. declared support budget, from the manifest alone.
    support_shape = declared_support_shape(manifest)
    cells = int(support_shape[0]) * int(support_shape[1])
    if cells > MAX_SUPPORT_CELLS:
        raise ValueError("support_budget_exceeded: %dx%d = %d cells exceeds the declared "
                         "ceiling %d; a larger support needs its own budget and a "
                         "separate review"
                         % (support_shape[0], support_shape[1], cells, MAX_SUPPORT_CELLS))
    # 2. NPY headers only: still no allocation.
    headers = inspect_archive(arrays_path)
    # 3. records vs headers vs support shape, still no allocation.
    records = check_headers(manifest, headers, support_shape)
    # 4. now, and only now, materialise the arrays.
    arrays = load_arrays(arrays_path, sorted(records))
    for name, record in sorted(records.items()):
        value = arrays[name]
        if value.dtype.str != record["dtype"] or list(value.shape) != list(record["shape"]):
            raise ValueError("array_header_changed_after_load: %s" % name)
        if array_sha256(value) != record["sha256"]:
            raise ValueError("array %r does not match its declared sha256" % name)
    support = manifest["support"]
    metadata = manifest["metadata"]
    shape = tuple(support_shape)
    parent = {
        "schema": manifest["schema"],
        "support": support,
        "arrays": arrays,
        "candidates": manifest["candidates"],
        "metadata": metadata,
        "identity_sha256": manifest["identity_sha256"],
    }
    provenance = {
        "directory": str(folder).replace(os.sep, "/"),
        "manifest_sha256": file_sha256(manifest_path),
        "arrays_sha256": file_sha256(arrays_path),
        "parent_identity_sha256": manifest["identity_sha256"],
        "support_identity_sha256": metadata["support_identity_sha256"],
        "world_seed": int(support["metadata"]["world_seed"]),
        "spacing_m": float(support["metadata"]["spacing_m"]),
        "origin_native_xz": [int(support["metadata"]["origin_native_xz"][0]),
                             int(support["metadata"]["origin_native_xz"][1])],
        "shape_zx": [int(shape[0]), int(shape[1])],
        "plan_version": int(support["metadata"]["plan_version"]),
        "source_records": list(metadata["source"].get("source_records", [])),
        "array_record_sha256": {name: record["sha256"] for name, record in records.items()},
        "input_gates": {
            "order": ["strict_manifest", "declared_support_budget", "npy_header_gate",
                      "header_record_support_cross_binding", "allow_pickle_false_load"],
            "max_manifest_bytes": MAX_MANIFEST_BYTES,
            "max_arrays_bytes": MAX_ARRAYS_BYTES,
            "max_total_array_bytes": MAX_TOTAL_ARRAY_BYTES,
            "max_support_cells": MAX_SUPPORT_CELLS,
            "declared_support_cells": cells,
            "npz_bytes": int(arrays_path.stat().st_size),
            "header_payload_bytes": int(sum(item["nbytes"] for item in
                                            headers.values())),
            "array_header_shapes": {name: list(headers[name]["shape"])
                                    for name in sorted(headers)},
            "allow_pickle": False,
            "arrays_materialised_only_after_headers": True,
        },
    }
    return parent, provenance


# --------------------------------------------------------------------------- #
# 2. independent per-cell walk (no production grouping is trusted)
# --------------------------------------------------------------------------- #
def _graph_positions(parent):
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    metadata = parent['support']['metadata']
    spacing = float(metadata['spacing_m'])
    origin = metadata['origin_native_xz']
    mesh = grid_mesh(tuple(metadata['shape_zx']), x0_m=origin[0] * spacing,
                     z0_m=origin[1] * spacing, dx_m=spacing,
                     world_seed=metadata['world_seed'])
    return mesh.node_x_m, mesh.node_z_m


def walk_reaches(parent, bundle):
    """Recompute every reach's node/edge/length facts one cell at a time.

    This is a plain receiver walk over the delivered arrays: it does not use the
    production segmentation, it does not re-derive the receiver, and it never patches
    an edge. Node count, edge count, internal hop length and the single hand-off hop
    are all recomputed here, so a number that only agrees with the builder's own
    bookkeeping cannot pass.
    """
    arrays = parent["arrays"]
    node_x, node_z = _graph_positions(parent)
    spacing = float(parent["support"]["metadata"]["spacing_m"])
    rows, columns = (int(value) for value in parent["support"]["metadata"]["shape_zx"])
    receiver = arrays["receiver"].reshape(-1)
    resolved = arrays["resolved_mask"].reshape(-1)
    owner = arrays["owner_index"].reshape(-1)
    reach_arrays = bundle["arrays"]
    pointer = reach_arrays["reach_ptr"]
    members = reach_arrays["reach_cells"]
    reach_count = int(reach_arrays["reach_downstream"].size)
    if int(pointer.size) != reach_count + 1 or int(pointer[0]) != 0:
        raise ValueError("break_malformed_reach_csr: the reach pointer does not match the "
                         "reach count")
    facts = []
    for index in range(reach_count):
        low, high = int(pointer[index]), int(pointer[index + 1])
        chain = [int(cell) for cell in members[low:high]]
        if not chain:
            raise ValueError("break_empty_reach: reach %d has no member" % index)
        for cell in chain:
            if not bool(resolved[cell]):
                raise ValueError("break_reach_on_inactive_cell: reach %d carries inactive "
                                 "cell %d" % (index, cell))
        length = 0.0
        for first, second in zip(chain[:-1], chain[1:]):
            if int(receiver[first]) != second:
                raise ValueError("break_reach_not_a_chain: reach %d leaves cell %d into "
                                 "%d, not its member %d"
                                 % (index, first, int(receiver[first]), second))
            length += math.hypot(node_x[first] - node_x[second], node_z[first] - node_z[second])
        tail = chain[-1]
        following = int(receiver[tail])
        if following < 0:
            # A channel cell always has a receiver (its upstream count is non-decreasing
            # downstream, so the selected channel closes downstream); a tail without one
            # is an internal break rather than a terminal.
            link = LINK_BREAK_TAIL_WITHOUT_RECEIVER
            handoff = 0.0
        else:
            handoff = math.hypot(node_x[tail] - node_x[following], node_z[tail] - node_z[following])
            target = int(reach_arrays["reach_of_cell"].reshape(-1)[following])
            if target >= 0:
                if int(owner[tail]) != int(owner[following]):
                    link = LINK_BREAK_ROOT_MISMATCH
                elif int(reach_arrays["reach_head"][target]) != following:
                    link = LINK_BREAK_HANDOFF_MISMATCH
                else:
                    link = LINK_HANDOFF
            elif int(receiver[following]) < 0:
                # The successor is a **structural terminal**: the finite graph's own end
                # point. It is never drawn on, never rebuilt and never called a lake.
                link = LINK_STRUCTURAL_TERMINAL
            elif not bool(resolved[following]):
                link = LINK_BREAK_INACTIVE
            else:
                # A live cell that still drains onward is an internal un-received break:
                # the selected channel did not close downstream. That is a failure, not a
                # window edge and not an outlet.
                link = LINK_BREAK_VALID_BELOW_GATE
        facts.append({
            "reach_index": index,
            "node_count": len(chain),
            "edges": len(chain) - 1,
            "length_m": length,
            "handoff_length_m": handoff,
            "tail": tail,
            "receiver_of_tail": following,
            "link": link,
            "root_index": int(owner[chain[0]]),
        })
    return facts


def audit_network(parent, bundle, walked):
    """Independent structural verdict for one already-built network.

    Every root and every segment is covered; a missing row is a refusal, and a reach
    whose tail does not continue into either a downstream reach or its own root's
    structural terminal is a **failure** classified as a break -- never as a lake, a
    window edge or an open outflow.
    """
    arrays = parent["arrays"]
    reach_arrays = bundle["arrays"]
    roots = arrays["root_cells"]
    resolved = arrays["resolved_mask"].reshape(-1)
    owner = arrays["owner_index"].reshape(-1)
    root_rows = bundle["roots"]
    reach_rows = bundle["reaches"]
    problems = []
    if bundle.get("schema") != REACH_SCHEMA:
        problems.append("schema: the network declares %r, expected %r"
                        % (bundle.get("schema"), REACH_SCHEMA))
    if len(root_rows) != int(roots.size):
        problems.append("coverage_root_rows: %d rows for %d roots"
                        % (len(root_rows), int(roots.size)))
    for index, row in enumerate(root_rows):
        if int(row["root_index"]) != index:
            problems.append("coverage_root_order: row %d declares root_index %s"
                            % (index, row["root_index"]))
    reach_count = int(reach_arrays["reach_downstream"].size)
    if len(reach_rows) != reach_count:
        problems.append("coverage_reach_rows: %d rows for %d segments"
                        % (len(reach_rows), reach_count))
    for index, row in enumerate(reach_rows):
        if int(row["reach_index"]) != index:
            problems.append("coverage_reach_order: row %d declares reach_index %s"
                            % (index, row["reach_index"]))
    if len(walked) != reach_count:
        problems.append("coverage_walk: %d walked segments for %d segments"
                        % (len(walked), reach_count))

    terminal_kinds = {}
    for fact in walked:
        index = fact["reach_index"]
        if index >= len(reach_rows):
            # A missing row is already reported by the coverage checks above; it must not
            # also crash the walk, or a refusal would look like a tool failure.
            continue
        row = reach_rows[index]
        if int(row["node_count"]) != fact["node_count"]:
            problems.append("node_count: segment %d says %s, the walk counts %d"
                            % (fact["reach_index"], row["node_count"], fact["node_count"]))
        if int(row["edges"]) != fact["edges"]:
            problems.append("edges: segment %d says %s, the walk counts %d"
                            % (fact["reach_index"], row["edges"], fact["edges"]))
        if int(row["root_index"]) != fact["root_index"]:
            problems.append("root_index: segment %d says %s, the walk reads owner %d"
                            % (fact["reach_index"], row["root_index"], fact["root_index"]))
        if not math.isclose(float(row["length_m"]), fact["length_m"],
                            rel_tol=0.0, abs_tol=1e-9):
            problems.append("length_m: segment %d says %s, the walk measures %.9f"
                            % (fact["reach_index"], row["length_m"], fact["length_m"]))
        if not math.isclose(float(row["handoff_length_m"]), fact["handoff_length_m"],
                            rel_tol=0.0, abs_tol=1e-9):
            problems.append("handoff_length_m: segment %d says %s, the walk measures %.9f"
                            % (fact["reach_index"], row["handoff_length_m"],
                               fact["handoff_length_m"]))
        if fact["link"] in BREAK_LINKS:
            problems.append("break: segment %d ends on cell %d into cell %d (%s); an "
                            "internal break is never a lake outlet and never a window "
                            "edge" % (fact["reach_index"], fact["tail"],
                                      fact["receiver_of_tail"], fact["link"]))
        if fact["link"] == LINK_STRUCTURAL_TERMINAL:
            target = fact["receiver_of_tail"]
            if int(owner[target]) != fact["root_index"]:
                problems.append("terminal: segment %d ends on cell %d, which belongs to "
                                "root %d, not root %d"
                                % (fact["reach_index"], target, int(owner[target]),
                                   fact["root_index"]))
            if int(reach_arrays["reach_downstream"][fact["reach_index"]]) != -1:
                problems.append("terminal: segment %d ends on a terminal cell but declares "
                                "a downstream segment" % fact["reach_index"])
        expected = int(reach_arrays["reach_downstream"][fact["reach_index"]])
        if fact["link"] == LINK_HANDOFF and expected != int(
                reach_arrays["reach_of_cell"].reshape(-1)[fact["receiver_of_tail"]]):
            problems.append("downstream: segment %d hands off into segment %d, the array "
                            "declares %d" % (fact["reach_index"],
                                             int(reach_arrays["reach_of_cell"].reshape(-1)[
                                                 fact["receiver_of_tail"]]), expected))
        if fact["link"] != LINK_HANDOFF and expected >= 0:
            problems.append("downstream: segment %d declares downstream %d but its tail "
                            "does not continue into a segment"
                            % (fact["reach_index"], expected))
        terminal_kinds[fact["reach_index"]] = (
            str(arrays["terminal_kind"].reshape(-1)[fact["receiver_of_tail"]])
            if fact["link"] == LINK_STRUCTURAL_TERMINAL else None)

    # Identity and the segment gate must be reproducible from the arrays and metadata.
    metadata = bundle["metadata"]
    recorded = int(metadata["counts"]["channel_cells"])
    covered = int((reach_arrays["reach_of_cell"] >= 0).sum())
    if covered != recorded:
        problems.append("coverage_channel_cells: reach_of_cell covers %d cells, the "
                        "metadata declares %d" % (covered, recorded))
    threshold = int(metadata["min_upstream_cells"])
    declared = int((arrays["resolved_mask"].reshape(-1)
                    & (arrays["receiver"].reshape(-1) >= 0)
                    & (arrays["upstream_cells"].reshape(-1) >= threshold)).sum())
    if declared != recorded:
        problems.append("coverage_gate_reproduction: min_upstream_cells=%d selects %d "
                        "cells, the metadata declares %d"
                        % (threshold, declared, recorded))
    if any(str(row["terminal_kind"]) == "open_outflow" for row in reach_rows):
        problems.append("terminal_kind: this chain never certifies an open outflow")
    return problems, terminal_kinds


# --------------------------------------------------------------------------- #
# 3. classification tables (every root, every segment)
# --------------------------------------------------------------------------- #
def _pending_reason(candidate):
    kind = candidate["root_kind"]
    if kind == "retained":
        return PENDING_RETAINED
    if kind == "unknown_boundary":
        return PENDING_UNKNOWN
    if kind == "open_outflow":
        return "open_outflow_declared"
    return PENDING_NONE


def classify_window(parent, bundle, provenance, walked, terminal_kinds):
    """One row per root and one row per segment end point, with no sampling."""
    arrays = parent["arrays"]
    reach_arrays = bundle["arrays"]
    candidates = parent["candidates"]
    metadata = bundle["metadata"]
    origin = provenance["origin_native_xz"]
    columns = int(provenance["shape_zx"][1])
    downstream = reach_arrays["reach_downstream"]

    def world_of(flat):
        return [origin[0] + int(flat) % columns, origin[1] + int(flat) // columns]

    # Downstream chain of every segment, ending at the structural terminal. This is
    # what makes "tributary -> trunk -> terminal" traceable instead of asserted.
    traces = {}
    for index in range(int(downstream.size)):
        chain = [index]
        current = int(downstream[index])
        seen = {index}
        while current >= 0:
            if current in seen:
                chain.append(-1)
                break
            seen.add(current)
            chain.append(current)
            current = int(downstream[current])
        traces[index] = chain

    root_rows = []
    for index, row in enumerate(bundle["roots"]):
        candidate = candidates[index]
        facts = [fact for fact in walked if fact["root_index"] == index]
        breaks = [fact["reach_index"] for fact in facts if fact["link"] in BREAK_LINKS]
        terminal_links = [fact for fact in facts
                          if fact["link"] == LINK_STRUCTURAL_TERMINAL]
        root_rows.append({
            "plan": provenance["plan"],
            "root_index": index,
            "root_world_x": int(candidate["root_world_xz"][0]),
            "root_world_z": int(candidate["root_world_xz"][1]),
            "root_kind": candidate["root_kind"],
            "status": candidate["status"],
            "upstream_complete": bool(row["upstream_complete"]),
            "member_count": int(candidate["member_count"]),
            "channel": ("channel" if int(row["channel_cell_count"]) else "nochannel"),
            "reach_count_segments": int(row["reach_count"]),
            "tributary_segment_count": int(row["tributary_reach_count"]),
            "channel_mainstem_segment_count": int(row["channel_mainstem_reach_count"]),
            "channel_mainstem_node_count": int(row["channel_mainstem_node_count"]),
            "channel_mainstem_edges": int(row["channel_mainstem_edges"]),
            "channel_mainstem_length_m": float(row["channel_mainstem_length_m"]),
            "raw_mainstem_node_count": int(row["raw_mainstem_node_count"]),
            "raw_mainstem_edges": int(row["raw_mainstem_edges"]),
            "raw_mainstem_length_m": float(row["raw_mainstem_length_m"]),
            "terminal_edge_count": int(row["terminal_edge_count"]),
            "terminal_kind": _terminal_kind_of(candidate, terminal_kinds, facts),
            "physical_endpoint_evidence": candidate["physical_endpoint_evidence"],
            "pending_reason": _pending_reason(candidate),
            "endpoint_ownership": ("own_root_cell" if terminal_links else "no_terminal_reach"),
            "break_segment_count": len(breaks),
            "classification": ("failed_break" if breaks
                               else (LINK_EMPTY_CHANNEL if not int(row["reach_count"])
                                     else LINK_STRUCTURAL_TERMINAL)),
            "verdict": FAILED if breaks else PASS,
        })

    reach_rows = []
    for fact in walked:
        row = bundle["reaches"][fact["reach_index"]]
        root_index = fact["root_index"]
        if fact["link"] == LINK_STRUCTURAL_TERMINAL:
            terminal_world = world_of(fact["receiver_of_tail"])
            terminal_root_world = [int(candidates[root_index]["root_world_xz"][0]),
                                   int(candidates[root_index]["root_world_xz"][1])]
        else:
            terminal_world = None
            terminal_root_world = None
        chain = traces[fact["reach_index"]]
        reach_rows.append({
            "plan": provenance["plan"],
            "reach_index": fact["reach_index"],
            "reach_id": row["reach_id"],
            "root_index": root_index,
            "root_world_x": int(row["root_world_xz"][0]),
            "root_world_z": int(row["root_world_xz"][1]),
            "node_count": fact["node_count"],
            "edges": fact["edges"],
            "length_m": round(fact["length_m"], 6),
            "handoff_length_m": round(fact["handoff_length_m"], 6),
            "on_mainstem": bool(row["on_mainstem"]),
            "downstream_reach_index": int(downstream[fact["reach_index"]]),
            "link_kind": fact["link"],
            "hops_to_terminal": len(chain) - 1,
            "terminal_reach_index": (chain[-1] if chain else -1),
            "terminal_kind": (str(arrays["terminal_kind"].reshape(-1)[fact["receiver_of_tail"]])
                              if fact["link"] == LINK_STRUCTURAL_TERMINAL else None),
            "terminal_cell_world_x": (terminal_world[0] if terminal_world else None),
            "terminal_cell_world_z": (terminal_world[1] if terminal_world else None),
            "terminal_root_world_x": (terminal_root_world[0] if terminal_root_world else None),
            "terminal_root_world_z": (terminal_root_world[1] if terminal_root_world else None),
            "physical_endpoint_evidence": ("basin_pending"
                                           if fact["link"] == LINK_STRUCTURAL_TERMINAL
                                           and candidates[root_index]["root_kind"] == "retained"
                                           else ("none" if fact["link"]
                                                 == LINK_STRUCTURAL_TERMINAL else None)),
            "upstream_complete": bool(candidates[root_index]["status"] == "candidate_closed"),
            "pending_reason": _pending_reason(candidates[root_index]),
            "classification": fact["link"],
            "verdict": FAILED if fact["link"] in BREAK_LINKS else PASS,
        })
    coverage = {
        "roots_total": int(arrays["root_cells"].size),
        "roots_classified": len(root_rows),
        "segments_total": int(downstream.size),
        "segments_classified": len(reach_rows),
        "channel_cells": int(metadata["counts"]["channel_cells"]),
        "unselected_valid_cells": int(metadata["counts"]["unselected_valid_cells"]),
        "roots_with_channel": sum(1 for row in root_rows if row["channel"] == "channel"),
        "roots_without_channel": sum(1 for row in root_rows if row["channel"] == "nochannel"),
        "segments_on_trunk": sum(1 for row in reach_rows if row["on_mainstem"]),
        "breaks": sum(1 for row in reach_rows if row["verdict"] == FAILED),
        "sampling": "none: every root and every segment row is written",
    }
    return root_rows, reach_rows, traces, coverage


def _terminal_kind_of(candidate, terminal_kinds, facts):
    for fact in facts:
        kind = terminal_kinds.get(fact["reach_index"])
        if kind is not None:
            return kind
    return None


# --------------------------------------------------------------------------- #
# 4. figures
# --------------------------------------------------------------------------- #
def _matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.lines import Line2D
    for family in ("Microsoft YaHei", "SimHei", "DengXian", "DejaVu Sans"):
        try:
            plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
            break
        except Exception:                                    # style only
            continue
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _terrain_image(parent, style):
    arrays = parent["arrays"]
    height = np.asarray(arrays["elevation_m"], np.float64)
    resolved = np.asarray(arrays["resolved_mask"], bool)
    filled = np.where(resolved, height, float(np.nanmin(height[resolved])))
    rgb = style.banded_relief_rgb(filled, float(parent["support"]["metadata"]["spacing_m"]),
                                  ocean_mask=np.zeros(filled.shape, bool))
    invalid = ~resolved
    if invalid.any():
        rgb[invalid] = np.array([0.72, 0.72, 0.74])
    return rgb, filled, resolved


def _extent_m(parent):
    metadata = parent["support"]["metadata"]
    origin = metadata["origin_native_xz"]
    rows, columns = metadata["shape_zx"]
    spacing = float(metadata["spacing_m"])
    x0 = origin[0] * spacing
    z0 = origin[1] * spacing
    return [x0, x0 + (columns - 1) * spacing, z0 + (rows - 1) * spacing, z0]


def _segment_lines(parent, bundle):
    """Continuous graph polylines of every segment, in world metres."""
    node_x, node_z = _graph_positions(parent)
    metadata = parent["support"]["metadata"]
    origin = metadata["origin_native_xz"]
    columns = int(metadata["shape_zx"][1])
    spacing = float(metadata["spacing_m"])
    pointer = bundle["arrays"]["reach_ptr"]
    members = bundle["arrays"]["reach_cells"]
    lines = []
    for index in range(int(bundle["arrays"]["reach_downstream"].size)):
        low, high = int(pointer[index]), int(pointer[index + 1])
        chain = [int(cell) for cell in members[low:high]]
        xs = node_x[chain].tolist()
        zs = node_z[chain].tolist()
        lines.append((xs, zs))
    return lines


def _legend_geometry(figure, axes, labels):
    """Machine-checkable proof that no legend sits on the map or runs off the canvas.

    Three things are asserted rather than promised, because a reader cannot un-see them:

    1. every panel has a legend at all;
    2. no legend rectangle intersects its **own axes** rectangle (a legend over the terrain);
    3. no legend rectangle leaves the **figure** rectangle (a legend clipped at the canvas
       edge -- which is what "the bottom legend touches the bottom border" looks like in a
       saved PNG). Not overlapping the axes is **not** the same as fitting the canvas.

    The drawn canvas size in pixels is returned so the saved file can be compared with it
    by :func:`_saved_png_pixels`.
    """
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    if not figure._suptitle or not figure._suptitle.get_text().strip():
        raise ValueError("missing_figure_title: a review figure must state its scope")
    figure_box = figure.bbox
    records = []
    for axis, label in zip(axes, labels):
        legend = axis.get_legend()
        if legend is None:
            raise ValueError("missing_legend: %s has no legend" % label)
        legend_box = legend.get_window_extent(renderer=renderer)
        axis_box = axis.get_window_extent(renderer=renderer)
        overlaps = not (legend_box.y1 <= axis_box.y0 or legend_box.y0 >= axis_box.y1
                        or legend_box.x1 <= axis_box.x0 or legend_box.x0 >= axis_box.x1)
        if overlaps:
            raise ValueError("legend_overlaps_map: the legend of %s covers its own axes "
                             "(legend y %.1f-%.1f vs axes y %.1f-%.1f)"
                             % (label, legend_box.y0, legend_box.y1, axis_box.y0,
                                axis_box.y1))
        outside = (legend_box.x0 < figure_box.x0 or legend_box.y0 < figure_box.y0
                   or legend_box.x1 > figure_box.x1 or legend_box.y1 > figure_box.y1)
        if outside:
            raise ValueError("legend_outside_figure: the legend of %s is clipped at the "
                             "canvas edge (legend x %.1f-%.1f y %.1f-%.1f vs figure "
                             "x %.1f-%.1f y %.1f-%.1f)"
                             % (label, legend_box.x0, legend_box.x1, legend_box.y0,
                                legend_box.y1, figure_box.x0, figure_box.x1,
                                figure_box.y0, figure_box.y1))
        records.append({
            "panel": label,
            "legend_px": [round(float(value), 3) for value in
                          (legend_box.x0, legend_box.y0, legend_box.x1, legend_box.y1)],
            "axes_px": [round(float(value), 3) for value in
                        (axis_box.x0, axis_box.y0, axis_box.x1, axis_box.y1)],
            "overlaps_own_axes": False,
            "inside_figure": True,
            "entries": len(legend.get_texts()),
        })
    figure_px = [int(round(float(value))) for value in (figure_box.x1 - figure_box.x0,
                                                        figure_box.y1 - figure_box.y0)]
    return {"panels": records, "figure_px": figure_px,
            "legends_inside_figure_canvas": True,
            "legend_gate": ("every legend must sit outside its own axes rectangle and "
                            "inside the figure rectangle; not overlapping the axes is "
                            "not by itself a passing layout")}


def _saved_png_pixels(path, expected_px):
    """Compare the saved PNG's pixel size with the drawn canvas; ``None`` if Pillow is absent."""
    try:
        from PIL import Image
    except ImportError:                                      # observation only
        return None
    with Image.open(path) as image:
        saved = [int(image.size[0]), int(image.size[1])]
    if saved != list(expected_px):
        raise ValueError("saved_png_size_mismatch: %s is %s but the figure drew %s"
                         % (path, saved, list(expected_px)))
    return saved


def _terminal_edge_lines(parent, bundle):
    """The final hop of every terminal segment, in world metres.

    A reach is never drawn **onto** its structural terminal, so the last edge lives only in
    ``terminal_edge_pairs``. It is drawn here as its own short segment, which is what makes
    ``tributary -> trunk -> terminal`` traceable by eye rather than merely asserted.
    """
    node_x, node_z = _graph_positions(parent)
    metadata = parent["support"]["metadata"]
    origin = metadata["origin_native_xz"]
    columns = int(metadata["shape_zx"][1])
    spacing = float(metadata["spacing_m"])
    lines = []
    for row in np.asarray(bundle["arrays"]["terminal_edge_pairs"], np.int64).reshape(-1, 2):
        source, target = int(row[0]), int(row[1])
        lines.append(([node_x[source], node_x[target]], [node_z[source], node_z[target]]))
    return lines


def render_network_figure(parent, bundle, provenance, path):
    """Three panels per window: full network, trunk, and pending/unknown state."""
    plt = _matplotlib()
    from matplotlib.lines import Line2D
    from terrain_pipeline import terrain_map_style as style

    node_x, node_z = _graph_positions(parent)
    rgb, _, resolved = _terrain_image(parent, style)
    arrays = parent["arrays"]
    metadata = parent["support"]["metadata"]
    origin = metadata["origin_native_xz"]
    columns = int(metadata["shape_zx"][1])
    spacing = float(metadata["spacing_m"])
    extent = _extent_m(parent)
    lines = _segment_lines(parent, bundle)
    terminal_lines = _terminal_edge_lines(parent, bundle)
    on_trunk = np.asarray(bundle["arrays"]["mainstem_reach_mask"], bool)
    figure, axes = plt.subplots(1, 3, figsize=(21.0, 8.6), dpi=105)

    def decorate(axis):
        axis.set_xlabel("世界坐标 x（米，TD 原生 30 m 格）")
        axis.set_ylabel("世界坐标 z（米）")
        axis.set_aspect("equal")

    # (A) the whole network over the real bed
    axes[0].imshow(rgb, extent=extent, origin="upper", interpolation="nearest")
    for xs, zs in lines:
        axes[0].plot(xs, zs, color="#1f4fd8", linewidth=0.5, alpha=0.75, zorder=3)
    for xs, zs in terminal_lines:
        axes[0].plot(xs, zs, color="#d2691e", linewidth=1.0, linestyle=":", zorder=5)
    axes[0].set_title("A 全网段（%d 段，段数≠河流条数）"
                      % int(bundle["arrays"]["reach_downstream"].size))
    decorate(axes[0])
    axes[0].legend(handles=[
        Line2D([], [], color="#1f4fd8", linewidth=1.2, label="通道段（声明阈值内）"),
        Line2D([], [], color="#d2691e", linewidth=1.2, linestyle=":",
               label="末段→结构终端的最后一条边（%d 条）" % len(terminal_lines)),
        Line2D([], [], color="#8a8a8a", linewidth=1.2, label="地形背景（原床，NaN 未解析为灰）")],
        loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=1, fontsize=9,
        framealpha=0.9)

    # (B) trunk only, plus the raw parent trunk for contrast
    axes[1].imshow(rgb, extent=extent, origin="upper", interpolation="nearest",
                   alpha=0.92)
    for index, (xs, zs) in enumerate(lines):
        if bool(on_trunk[index]):
            axes[1].plot(xs, zs, color="#c0143c", linewidth=1.5, zorder=4)
    for root_index in range(int(arrays["root_cells"].size)):
        low = int(arrays["mainstem_ptr"][root_index])
        high = int(arrays["mainstem_ptr"][root_index + 1])
        chain = [int(cell) for cell in arrays["mainstem_cells"][low:high]]
        xs = node_x[chain].tolist()
        zs = node_z[chain].tolist()
        axes[1].plot(xs, zs, color="#4d4d4d", linewidth=0.4, alpha=0.55, zorder=3)
    for xs, zs in terminal_lines:
        axes[1].plot(xs, zs, color="#d2691e", linewidth=1.2, linestyle=":", zorder=5)
    axes[1].set_title("B 主干（红=阈值内通道主干；灰=父完整有序主干；橙虚线=到终端最后一边）")
    decorate(axes[1])
    axes[1].legend(handles=[
        Line2D([], [], color="#c0143c", linewidth=1.8, label="通道主干段"),
        Line2D([], [], color="#4d4d4d", linewidth=1.2, label="父 raw 主干（阈值无关，全格路径）"),
        Line2D([], [], color="#d2691e", linewidth=1.2, linestyle=":",
               label="末段→结构终端边（%d 条，不在段内）" % len(terminal_lines))],
        loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=1, fontsize=9,
        framealpha=0.9)

    # (C) pending / unknown state, explicitly labelled
    axes[2].imshow(rgb, extent=extent, origin="upper", interpolation="nearest",
                   alpha=0.85)
    unselected = np.asarray(bundle["arrays"]["reach_of_cell"], np.int64) < 0
    mask_image = np.asarray(unselected, bool) & np.asarray(resolved, bool)
    axes[2].imshow(np.where(mask_image, 1.0, np.nan), extent=extent, origin="upper",
                   cmap="Greys", alpha=0.28, vmin=0.0, vmax=1.0)
    kinds = np.asarray(arrays["terminal_kind"]).reshape(-1)
    unknown_members = ((kinds == "unknown_boundary")
                       & (np.asarray(arrays["owner_index"], np.int64).reshape(-1) >= 0)
                       & (np.asarray(arrays["receiver"], np.int64).reshape(-1) < 0))
    unknown_cells = np.flatnonzero(unknown_members)
    if unknown_cells.size:
        axes[2].scatter([(origin[0] + cell % columns) * spacing for cell in unknown_cells],
                        [(origin[1] + cell // columns) * spacing for cell in unknown_cells],
                        marker="s", s=16, facecolor="none", edgecolor="#7a1fa2",
                        linewidth=1.2, zorder=5)
    retained_cells = np.flatnonzero(kinds == "retained")
    if retained_cells.size:
        axes[2].scatter([(origin[0] + cell % columns) * spacing for cell in retained_cells],
                        [(origin[1] + cell // columns) * spacing for cell in retained_cells],
                        marker="^", s=26, facecolor="none", edgecolor="#d2691e",
                        linewidth=1.3, zorder=6)
    for xs, zs in lines:
        axes[2].plot(xs, zs, color="#1f4fd8", linewidth=0.4, alpha=0.45, zorder=4)
    for xs, zs in terminal_lines:
        axes[2].plot(xs, zs, color="#d2691e", linewidth=1.0, linestyle=":", zorder=5)
    axes[2].set_title("C 明确 pending / unknown（retained≠湖，unknown≠出口）")
    decorate(axes[2])
    axes[2].legend(handles=[
        Line2D([], [], color="#7a1fa2", marker="s", linestyle="none", markersize=7,
               markerfacecolor="none", label="unknown_boundary 结构终端（%d）"
               % int(unknown_cells.size)),
        Line2D([], [], color="#d2691e", marker="^", linestyle="none", markersize=8,
               markerfacecolor="none", label="retained 结构终端 = basin_pending（%d）"
               % int(retained_cells.size)),
        Line2D([], [], color="#555555", linewidth=6, alpha=0.28,
               label="阈值内未入选的 valid 格（不是干河）"),
        Line2D([], [], color="#1f4fd8", linewidth=1.0, label="通道段")],
        loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=1, fontsize=9,
        framealpha=0.9)

    figure.suptitle(
        figure_title := (
            "%s · support origin %s shape %s · %d roots / %d 段 / 通道格 %d · 仅严格不规则图结构，"
            "retained 不是湖，无 Q 物理过程"
            % (provenance["plan"], provenance["origin_native_xz"], provenance["shape_zx"],
               int(arrays["root_cells"].size),
               int(bundle["arrays"]["reach_downstream"].size),
               int(bundle["metadata"]["counts"]["channel_cells"]))),
        fontsize=12, y=0.985)
    figure.tight_layout(rect=(0.0, 0.115, 1.0, 0.95))
    panels = _legend_geometry(figure, axes, ["A_full_network", "B_mainstem",
                                             "C_pending_state"])
    figure.savefig(path, dpi=105)
    saved_px = _saved_png_pixels(path, panels["figure_px"])
    plt.close(figure)
    return {"path": str(path),
            "panels": panels["panels"],
            "figure_px": panels["figure_px"],
            "saved_png_px": saved_px,
            "legends_inside_figure_canvas": panels["legends_inside_figure_canvas"],
            "legend_gate": panels["legend_gate"],
            "title": figure_title, "full_support": True}


def render_detail_figure(parent, bundle, provenance, root_index, path):
    """One chosen root: detail map plus the along-trunk bed profile."""
    plt = _matplotlib()
    from matplotlib.lines import Line2D
    from terrain_pipeline import terrain_map_style as style

    node_x, node_z = _graph_positions(parent)
    rgb, _, resolved = _terrain_image(parent, style)
    arrays = parent["arrays"]
    candidates = parent["candidates"]
    metadata = parent["support"]["metadata"]
    origin = metadata["origin_native_xz"]
    columns = int(metadata["shape_zx"][1])
    rows_n = int(metadata["shape_zx"][0])
    spacing = float(metadata["spacing_m"])
    extent = _extent_m(parent)
    owner_flat = np.asarray(arrays["owner_index"], np.int64).reshape(-1)
    members = np.flatnonzero(owner_flat == root_index)
    member_x = (origin[0] + members % columns) * spacing
    member_z = (origin[1] + members // columns) * spacing
    low = int(arrays["mainstem_ptr"][root_index])
    high = int(arrays["mainstem_ptr"][root_index + 1])
    raw_chain = [int(cell) for cell in arrays["mainstem_cells"][low:high]]
    raw_x = node_x[raw_chain]
    raw_z = node_z[raw_chain]
    margin = 12 * spacing
    x_low, x_high = float(member_x.min() - margin), float(member_x.max() + margin)
    z_low, z_high = float(member_z.min() - margin), float(member_z.max() + margin)

    figure, axes = plt.subplots(1, 2, figsize=(19.0, 8.4), dpi=105)
    axes[0].imshow(rgb, extent=extent, origin="upper", interpolation="nearest")
    other = owner_flat >= 0
    other_image = np.zeros((rows_n, columns), bool)
    other_image = np.asarray(other, bool).reshape(rows_n, columns) & ~np.isin(
        owner_flat.reshape(rows_n, columns), [root_index])
    axes[0].imshow(np.where(other_image, 1.0, np.nan), extent=extent, origin="upper",
                   cmap="Greys", alpha=0.22, vmin=0.0, vmax=1.0)
    lines = _segment_lines(parent, bundle)
    on_trunk = np.asarray(bundle["arrays"]["mainstem_reach_mask"], bool)
    for index, (xs, zs) in enumerate(lines):
        if int(bundle["reaches"][index]["root_index"]) != root_index:
            continue
        axes[0].plot(xs, zs, color=("#c0143c" if bool(on_trunk[index]) else "#1f4fd8"),
                     linewidth=(1.8 if bool(on_trunk[index]) else 0.8),
                     zorder=(5 if bool(on_trunk[index]) else 4))
    axes[0].plot(raw_x, raw_z, color="#2b2b2b", linewidth=0.8, linestyle="--",
                 alpha=0.8, zorder=6)
    axes[0].scatter([raw_x[-1]], [raw_z[-1]], marker="X", s=90, color="#d2691e",
                    zorder=7)
    axes[0].set_xlim(x_low, x_high)
    axes[0].set_ylim(z_high, z_low)
    axes[0].set_title("选定 root 详图（root world %s，成员 %d 格）"
                      % (candidates[root_index]["root_world_xz"],
                         int(candidates[root_index]["member_count"])))
    axes[0].set_xlabel("世界坐标 x（米）")
    axes[0].set_ylabel("世界坐标 z（米）")
    axes[0].set_aspect("equal")
    axes[0].legend(handles=[
        Line2D([], [], color="#c0143c", linewidth=2.0, label="通道主干段"),
        Line2D([], [], color="#1f4fd8", linewidth=1.2, label="该 root 的支流段"),
        Line2D([], [], color="#2b2b2b", linewidth=1.2, linestyle="--", label="父 raw 主干（有序，含阈值下格）"),
        Line2D([], [], color="#d2691e", marker="X", linestyle="none", markersize=10,
               label="结构终端（root 格，pending）"),
        Line2D([], [], color="#8a8a8a", linewidth=6, alpha=0.25, label="其他 root 归属格")],
        loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=2, fontsize=9,
        framealpha=0.9)

    # Along-trunk bed profile: hop length in metres, bed elevation in metres.
    hops = []
    distances = [0.0]
    for first, second in zip(raw_chain[:-1], raw_chain[1:]):
        hop = math.hypot(node_x[first] - node_x[second], node_z[first] - node_z[second])
        hops.append(hop)
        distances.append(distances[-1] + hop)
    heights = [float(arrays["elevation_m"].reshape(-1)[cell]) for cell in raw_chain]
    threshold = int(bundle["metadata"]["min_upstream_cells"])
    upstream = np.asarray(arrays["upstream_cells"], np.int64).reshape(-1)
    channel_flags = [bool(int(upstream[cell]) >= threshold) for cell in raw_chain]
    axes[1].plot(distances, heights, color="#2b2b2b", linewidth=1.4, zorder=3)
    for index in range(1, len(distances)):
        if channel_flags[index] and channel_flags[index - 1]:
            axes[1].plot(distances[index - 1:index + 1], heights[index - 1:index + 1],
                         color="#c0143c", linewidth=2.4, zorder=4)
    axes[1].scatter([distances[-1]], [heights[-1]], marker="X", s=90, color="#d2691e",
                    zorder=5)
    axes[1].set_title("沿主干床面纵剖（横轴=连续图边累计米，纵轴=床面高程 m）")
    axes[1].set_xlabel("沿主干累计距离（米，不规则图路径）")
    axes[1].set_ylabel("床面高程（米）")
    axes[1].grid(alpha=0.25)
    axes[1].legend(handles=[
        Line2D([], [], color="#2b2b2b", linewidth=1.6, label="父 raw 主干全链（%d 节点 / %d 边）"
               % (len(raw_chain), len(raw_chain) - 1)),
        Line2D([], [], color="#c0143c", linewidth=2.4,
               label="阈值内通道主干段（min_upstream_cells=%d）" % threshold),
        Line2D([], [], color="#d2691e", marker="X", linestyle="none", markersize=10,
               label="结构终端格")],
        loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=1, fontsize=9,
        framealpha=0.9)
    figure.suptitle(detail_title := (
        "%s · 选定 root 详图 + 沿程床面纵剖 · 不按好看换样（规则：complete + 成员最多 + world 并列）"
        % provenance["plan"]), fontsize=12, y=0.985)
    figure.tight_layout(rect=(0.0, 0.115, 1.0, 0.94))
    panels = _legend_geometry(figure, axes, ["detail_map", "along_trunk_profile"])
    figure.savefig(path, dpi=105)
    saved_px = _saved_png_pixels(path, panels["figure_px"])
    plt.close(figure)
    return {"path": str(path), "panels": panels["panels"],
            "figure_px": panels["figure_px"], "saved_png_px": saved_px,
            "legends_inside_figure_canvas": panels["legends_inside_figure_canvas"],
            "legend_gate": panels["legend_gate"],
            "title": detail_title,
            "root_index": int(root_index),
            "root_world_xz": list(candidates[root_index]["root_world_xz"]),
            "selection_rule": ("complete + most members + world (x, z) tie-break; the "
                               "same rule as the bundle's display_root_index")}


# --------------------------------------------------------------------------- #
# 5. outputs
# --------------------------------------------------------------------------- #
def write_csv(path, rows):
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return str(path)
    keys = list(rows[0])
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return str(path)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2,
                                     ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8")
    return str(path)


def select_display_root(parent):
    """The frozen selection rule: complete first, most members, world (x,z) tie-break.

    It is recomputed here from the candidates instead of being read back from the
    bundle metadata, so "whichever looked best in the figure" cannot replace it.
    """
    complete = [index for index, candidate in enumerate(parent["candidates"])
                if candidate["status"] == "candidate_closed"]
    if not complete:
        return None
    ranked = sorted(complete, key=lambda index: (
        -int(parent["candidates"][index]["member_count"]),
        int(parent["candidates"][index]["root_world_xz"][0]),
        int(parent["candidates"][index]["root_world_xz"][1])))
    return int(ranked[0])


def historical_case(parent, provenance):
    """Read-only cross-check of the historical window-lake case world cell.

    The historical diagnosis (``.scratch/river-window-lake-diagnosis-20261026/report.md``
    case 1) reported the same world cell with **different** member counts under different
    window origins: 5 760 under origin ``42173/42874`` (257²) and 2 895 under origin
    ``42270/42743`` (257²). Only the first support is in the declared B ladder here. The
    second one is therefore reported **NOT_RUN**, not re-derived by inventing a new window:
    this review must not claim that its three declared windows cover the old 2 895
    support.

    The same root is also reported on the **incomplete axis** separately, because the two
    windows disagree about its completeness: a root can carry the same world terminal
    while its upstream cone is still unknown.
    """
    metadata = parent["support"]["metadata"]
    origin = metadata["origin_native_xz"]
    rows, columns = (int(value) for value in metadata["shape_zx"])
    x, z = HISTORICAL_CASE_WORLD_XZ
    if not (origin[0] <= x < origin[0] + columns and origin[1] <= z < origin[1] + rows):
        return {"plan": provenance["plan"], "window_contains_cell": False,
                "verdict": NOT_RUN,
                "note": "this support does not contain the historical case cell"}
    flat = (z - origin[1]) * columns + (x - origin[0])
    owner = int(np.asarray(parent["arrays"]["owner_index"], np.int64).reshape(-1)[flat])
    candidate = parent["candidates"][owner]
    complete_mask = np.asarray(parent["arrays"]["complete_mask"], bool).reshape(-1)
    unresolved = int((~complete_mask[np.asarray(parent["arrays"]["owner_index"],
                                                np.int64).reshape(-1) == owner]).sum())
    return {
        "plan": provenance["plan"],
        "window_contains_cell": True,
        "root_index": owner,
        "root_world_xz": list(candidate["root_world_xz"]),
        "member_count": int(candidate["member_count"]),
        "upstream_incomplete_member_count": unresolved,
        "root_kind": candidate["root_kind"],
        "status": candidate["status"],
        "reason_codes": list(candidate["reason_codes"]),
        "upstream_complete": bool(candidate["status"] == "candidate_closed"),
        "reproduces_5760": int(candidate["member_count"]) == HISTORICAL_EXPECTED_257,
        "reproduces_2895": int(candidate["member_count"]) == HISTORICAL_EXPECTED_OTHER,
        "verdict": (PASS if int(candidate["member_count"]) == HISTORICAL_EXPECTED_257
                    else NOT_RUN),
        "note": ("scope statement of THIS review, not a project-level verdict: the "
                 "historical 5 760 support (origin 42173/42874) is reviewed here as p1 "
                 "and reproduces exactly; the historical 2 895 support (origin "
                 "42270/42743 at 257²) is NOT one of the declared supports of this "
                 "review, so the three windows here do NOT cover it and it stays "
                 "NOT_RUN (a scope statement, not a failure). The case itself is "
                 "source-level reproduced elsewhere: "
                 ".scratch/river-lake-world-integration/evidence-b4-historical-v1/ "
                 "(rev2, pages 4/4 match their pins) and the main-branch recomputation "
                 "cmd-20261026115118-db24bcd747. A same world root may appear complete "
                 "in one support and upstream-incomplete in another; that axis is "
                 "reported separately and never folded into the member count."),
    }


def review(output, *, plans=DECLARED_PLANS, min_upstream_cells=DEFAULT_MIN_UPSTREAM_CELLS,
           figures=True, evidence_root=None):
    target = Path(output)
    if target.exists():
        raise SystemExit("refusing to overwrite an existing output directory: %s" % target)
    target.mkdir(parents=True)
    from terrain_pipeline.surface_rivers import metric_world_domains as domains
    from terrain_pipeline.surface_rivers import metric_world_reaches as reaches

    watch = Stopwatch()
    report = {
        "schema": SCHEMA,
        "evidence": "B4 main-stem and end-point review over the pinned B3 packages",
        "min_upstream_cells": int(min_upstream_cells),
        "declared_plans": list(plans),
        "input_sha256": {},
        "stages": [],
        "windows": {},
        "coverage": {},
        "figures": {},
        "verdict": {},
        "historical_case": {},
        "limits": {
            "no_second_d8": True,
            "no_new_production_algorithm": True,
            "retained_is_not_a_lake": True,
            "unknown_is_not_an_outlet": True,
            "reach_count_is_not_river_count": True,
            "node_edge_segment_units_kept_apart": True,
            "support_ceiling_cells": MAX_SUPPORT_CELLS,
            "budget_not_raised_here": True,
            "no_physical_process": "no Q, no flow, no discharge, no hydraulics, no lake",
        },
    }
    for plan in plans:
        directory = (Path(evidence_root) / ("evidence-b-%s-v3" % plan)) if evidence_root \
            else ROOT / (EVIDENCE_DIR % plan)
        parent, provenance = watch.stage("load_%s" % plan, load_evidence, directory)
        provenance = dict(provenance, plan=plan)
        report["input_sha256"][plan] = {
            "manifest_sha256": provenance["manifest_sha256"],
            "arrays_sha256": provenance["arrays_sha256"],
            "parent_identity_sha256": provenance["parent_identity_sha256"],
            "support_identity_sha256": provenance["support_identity_sha256"],
            "source_records": provenance["source_records"],
        }
        watch.stage("validate_parent_%s" % plan, domains.validate_domain_candidates, parent)
        watch.sample()
        started = time.monotonic()
        bundle = reaches.build_world_reaches(parent, min_upstream_cells=min_upstream_cells)
        build_s = time.monotonic() - started
        watch.sample()
        started = time.monotonic()
        reaches.validate_world_reaches(bundle, parent)
        validate_s = time.monotonic() - started
        watch.stages.append({"stage": "build_%s" % plan, "elapsed_s": round(build_s, 3)})
        watch.stages.append({"stage": "validate_%s" % plan, "elapsed_s": round(validate_s, 3)})
        watch.sample()

        started = time.monotonic()
        walked = walk_reaches(parent, bundle)
        problems, terminal_kinds = audit_network(parent, bundle, walked)
        audit_s = time.monotonic() - started
        watch.stages.append({"stage": "audit_%s" % plan, "elapsed_s": round(audit_s, 3)})
        root_rows, reach_rows, traces, coverage = classify_window(
            parent, bundle, provenance, walked, terminal_kinds)
        write_csv(target / ("roots-%s.csv" % plan), root_rows)
        write_csv(target / ("reach-endpoints-%s.csv" % plan), reach_rows)
        write_json(target / ("trace-%s.json" % plan), {
            "plan": plan,
            "note": ("segment index -> ordered downstream chain of segments ending at the "
                     "structural terminal (-1 marks a broken chain)"),
            "traces": {str(key): value for key, value in traces.items()},
        })
        selected = select_display_root(parent)
        declared = bundle["metadata"]["display_root_index"]
        if selected != declared:
            problems.append("display_root_rule: recomputed %s, the bundle declares %s"
                            % (selected, declared))
        report["windows"][plan] = {
            "provenance": provenance,
            "status": bundle["metadata"]["status"],
            "whole_support_upstream_complete": bool(
                bundle["metadata"]["whole_support_upstream_complete"]),
            "physical_domain_certified": bool(
                bundle["metadata"]["physical_domain_certified"]),
            "counts": bundle["metadata"]["counts"],
            "budget": bundle["metadata"]["budget"],
            "display_root_index": selected,
            "display_root_world_xz": (None if selected is None else
                                      list(parent["candidates"][selected]["root_world_xz"])),
            "display_root_member_count": (None if selected is None else
                                          int(parent["candidates"][selected]["member_count"])),
            "audit_problems": problems,
            "verdict": PASS if not problems else FAILED,
            "timing_s": {"build": round(build_s, 3), "validate": round(validate_s, 3),
                         "independent_audit": round(audit_s, 3)},
        }
        report["coverage"][plan] = coverage
        report["verdict"][plan] = PASS if not problems else FAILED
        report["historical_case"][plan] = historical_case(parent, provenance)

        if figures:
            style_name = "network-%s.png" % plan
            report["figures"][style_name] = watch.stage(
                "figure_network_%s" % plan, render_network_figure, parent, bundle,
                provenance, target / style_name)
            if selected is not None:
                detail = "detail-root-%s-r%03d.png" % (plan, int(selected))
                report["figures"][detail] = watch.stage(
                    "figure_detail_%s" % plan, render_detail_figure, parent, bundle,
                    provenance, int(selected), target / detail)

    report["verdict"]["all_windows"] = (
        PASS if all(value == PASS for key, value in report["verdict"].items()
                    if key in plans) else FAILED)
    report["historical_case"]["summary"] = {
        "case_world_xz": list(HISTORICAL_CASE_WORLD_XZ),
        "expected_257_member_count": HISTORICAL_EXPECTED_257,
        "expected_other_window_member_count": HISTORICAL_EXPECTED_OTHER,
        "reproduced_5760_supports": [plan for plan in plans
                                     if report["historical_case"][plan].get(
                                         "reproduces_5760")],
        "verdict": (PASS if any(report["historical_case"][plan].get("reproduces_5760")
                                for plan in plans) else NOT_RUN),
        "reviewed_supports": list(plans),
        "historical_2895_support_reviewed_here": False,
        "project_level_case_status": (
            "source-level reproduced outside this review: "
            ".scratch/river-lake-world-integration/evidence-b4-historical-v1/ (rev2) and "
            "cmd-20261026115118-db24bcd747; this review issues no project verdict and "
            "its NOT_RUN for the 2 895 support is a scope statement, not a failure"),
        "note": ("the historical 5 760 support (origin 42173/42874) is reviewed here as "
                 "p1; the historical 2 895 support (origin 42270/42743 at 257²) is NOT "
                 "one of the declared supports of this review, so the three windows "
                 "below do NOT cover it and it stays NOT_RUN rather than being "
                 "re-derived from an invented window"),
    }
    report["stages"] = watch.report()
    write_json(target / "diagnosis.json", report)
    write_json(target / "classification.json", {
        "schema": SCHEMA,
        "coverage": report["coverage"],
        "verdict": report["verdict"],
        "windows": {plan: {"audit_problems": report["windows"][plan]["audit_problems"],
                           "display_root_index": report["windows"][plan]["display_root_index"]}
                    for plan in plans},
        "tables": {"%s/roots" % plan: "roots-%s.csv" % plan for plan in plans},
        "endpoint_tables": {"%s/reach_endpoints" % plan: "reach-endpoints-%s.csv" % plan
                            for plan in plans},
    })
    return report, target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True,
                        help="new evidence directory; must not exist")
    parser.add_argument("--plans", nargs="*", default=list(DECLARED_PLANS))
    parser.add_argument("--min-upstream-cells", type=int,
                        default=DEFAULT_MIN_UPSTREAM_CELLS)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--evidence-root", default=None,
                        help="optional directory holding evidence-b-<plan>-v3")
    arguments = parser.parse_args(argv)
    report, target = review(arguments.output, plans=tuple(arguments.plans),
                            min_upstream_cells=arguments.min_upstream_cells,
                            figures=not arguments.no_figures,
                            evidence_root=arguments.evidence_root)
    print(json.dumps({"output": str(target), "verdict": report["verdict"],
                      "coverage": report["coverage"], "stages": report["stages"]},
                     sort_keys=True, ensure_ascii=False))
    return 0 if report["verdict"]["all_windows"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
