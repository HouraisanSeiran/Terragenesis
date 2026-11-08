"""Independent audits of world-domain candidates, on hand-built fixtures only.

The tests never import the producer (``metric_world_domains``) or any other
``terrain_pipeline`` module: the fixture builder below is a second, deliberately
naive implementation (per-cell Python loops, no vectorised kernels) so that a
shared mistake between producer and audit cannot hide behind a green test.

Fixture shape (``DOMAIN_FIXTURE``): an 11x11 bowl inside a rim ring, with a low
outer ring around it. Interior rings are structurally closed (their catchments
are entirely interior), the four outer corners are border sinks. So a passing
fixture must show 2 ``candidate_closed`` roots and 4 incomplete roots, and there
is at least one strictly descending mainstem per closed root.

Negative cases are constructed by mutating one thing at a time:
wrong owner, wrong completeness, wrong mainstem, a false physical claim, an
NPY object member, a truncated NPY member, duplicate JSON keys, non-finite JSON,
non-finite elevation, and an already existing output target.
"""

import io
import json
import contextlib
import hashlib
import math
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import audit_world_domains as auditmod
from tools import prepare_world_domains as preparemod


def os_path_lexists(path):
    return preparemod.os.path.lexists(str(path))


NEIGHBOURS8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
ORIGIN = (-3, -7)          # a deliberately negative signed native origin
PLAN_VERSION = 1
FIELD_MASK_SHA = "6" * 64
ROWS = COLUMNS = 11



# --------------------------------------------------------------------------- #
# fixture elevation, written as explicit declarations
# --------------------------------------------------------------------------- #
def fixture_elevation():
    """Low outer ring, high rim at ring 1, two interior pits inside the rim."""
    rows = columns = ROWS
    height = [[0.0] * columns for _ in range(rows)]
    for r in range(rows):
        for c in range(columns):
            if r in (0, rows - 1) or c in (0, columns - 1):
                # outer ring: descends along the border into its four corners
                distance = min(r + c, r + (columns - 1 - c),
                               (rows - 1 - r) + c, (rows - 1 - r) + (columns - 1 - c))
                height[r][c] = 40.0 + 0.25 * distance
            elif r in (1, rows - 2) or c in (1, columns - 2):
                # the rim: high enough that interior drainage cannot leave,
                # and lower than nothing outward, so it drains out to the ring
                height[r][c] = 60.0
            else:
                first = (r - 4) ** 2 + (c - 4) ** 2
                second = (r - 7) ** 2 + (c - 7) ** 2
                height[r][c] = 30.0 + 0.35 * min(first, second)
    return height


# --------------------------------------------------------------------------- #
# naive reference builder (per cell, pure Python)
# --------------------------------------------------------------------------- #
def brute_receiver(height, mask, origin=ORIGIN):
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    bed, valid = np.asarray(height), np.asarray(mask, bool)
    rows, columns = bed.shape
    mesh = masked_mesh(grid_mesh(bed.shape, x0_m=origin[0] * 30.,
        z0_m=origin[1] * 30., world_seed=20261020), valid)
    receiver = [[None] * columns for _ in range(rows)]
    for node in np.flatnonzero(valid):
        best_slope = 0.
        for edge in range(mesh.indptr[node], mesh.indptr[node + 1]):
            target = int(mesh.indices[edge])
            slope = (bed.ravel()[node] - bed.ravel()[target]) / mesh.edge_length_m[edge]
            if slope > best_slope:
                receiver[node // columns][node % columns] = divmod(target, columns)
                best_slope = slope
    return receiver


def brute_seeds(mask, origin=ORIGIN):
    from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown
    return graph_support_unknown(np.asarray(mask, bool), x0_m=origin[0] * 30.,
        z0_m=origin[1] * 30., world_seed=20261020).tolist()


def brute_walk(receiver, mask):
    rows, columns = len(mask), len(mask[0])
    terminal = [[None] * columns for _ in range(rows)]
    depth = [[-1] * columns for _ in range(rows)]
    for r in range(rows):
        for c in range(columns):
            if not mask[r][c]:
                continue
            path = []
            cell = (r, c)
            while True:
                path.append(cell)
                nxt = receiver[cell[0]][cell[1]]
                if nxt is None:
                    base, base_depth = cell, 0
                    break
                if terminal[nxt[0]][nxt[1]] is not None:
                    base = terminal[nxt[0]][nxt[1]]
                    base_depth = depth[nxt[0]][nxt[1]] + 1
                    break
                cell = nxt
            for offset, node in enumerate(reversed(path)):
                terminal[node[0]][node[1]] = base
                depth[node[0]][node[1]] = base_depth + offset
    return terminal, depth


def build_fixture(height=None, mask=None, origin=ORIGIN, plan_version=PLAN_VERSION):
    """Build the producer-shaped bundle for the declared fixture."""
    height = fixture_elevation() if height is None else height
    rows, columns = len(height), len(height[0])
    if mask is None:
        mask = [[True] * columns for _ in range(rows)]
    receiver = brute_receiver(height, mask, origin)
    seeds = brute_seeds(mask, origin)
    terminal, depth = brute_walk(receiver, mask)

    order = sorted(((r, c) for r in range(rows) for c in range(columns) if mask[r][c]),
                   key=lambda cell: -depth[cell[0]][cell[1]])
    counts = {(r, c): 1 for r in range(rows) for c in range(columns) if mask[r][c]}
    dirty = {(r, c): seeds[r][c] for r in range(rows) for c in range(columns) if mask[r][c]}
    for cell in order:
        nxt = receiver[cell[0]][cell[1]]
        if nxt is None:
            continue
        counts[nxt] += counts[cell]
        dirty[nxt] = dirty[nxt] or dirty[cell]

    interiors = []
    for r in range(rows):
        for c in range(columns):
            if mask[r][c] and receiver[r][c] is None:
                interiors.append((r, c))
    roots = sorted(interiors, key=lambda cell: (origin[0] + cell[1], origin[1] + cell[0]))
    slot_of = {cell: index for index, cell in enumerate(roots)}

    owner = [[-1] * columns for _ in range(rows)]
    members = [[] for _ in roots]
    for r in range(rows):
        for c in range(columns):
            if not mask[r][c]:
                continue
            slot = slot_of[terminal[r][c]]
            owner[r][c] = slot
            members[slot].append((r, c))
    for bucket in members:
        bucket.sort()

    def world(cell):
        return (origin[0] + cell[1], origin[1] + cell[0])

    donors = {}
    for r in range(rows):
        for c in range(columns):
            if mask[r][c] and receiver[r][c] is not None:
                donors.setdefault(receiver[r][c], []).append((r, c))

    chains = []
    for root in roots:
        chain = [root]
        cell = root
        while donors.get(cell):
            pool = donors[cell]
            top = max(counts[donor] for donor in pool)
            tied = [donor for donor in pool if counts[donor] == top]
            tied.sort(key=lambda donor: (world(donor), ))
            cell = tied[0]
            chain.append(cell)
        chains.append(chain[::-1])

    # D4 hetero-owner pairs, deduplicated by world (x, z) pair; the array carries
    # the LOCAL flat index of each side in canonical world order.
    shared = {}
    for r in range(rows):
        for c in range(columns):
            if not mask[r][c]:
                continue
            for dr, dc in ((0, 1), (1, 0)):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < columns) or not mask[nr][nc]:
                    continue
                if owner[r][c] == owner[nr][nc]:
                    continue
                first, second = world((r, c)), world((nr, nc))
                flat = {first: _flat(rows, columns, r, c),
                        second: _flat(rows, columns, nr, nc)}
                pair = tuple(sorted((first, second)))
                shared[pair] = (flat[pair[0]], flat[pair[1]])
    faces = [shared[pair] for pair in sorted(shared)]
    return _bundle(height, mask, receiver, seeds, terminal, counts, dirty,
                   owner, roots, members, chains, faces, origin, plan_version)


def _flat(rows, columns, r, c):
    return r * columns + c


def _world_digest(pairs):
    block = np.ascontiguousarray(np.asarray(pairs, np.int64).reshape(-1, 2), dtype="<i8")
    return hashlib.sha256(block.tobytes()).hexdigest()


def _candidate_id(slot, root, kind, status, member_world, origin, plan_version):
    """The declared logical ID, built here from the public rule (not copied from code)."""
    payload = {
        "algorithm": "metric-world-domain-candidate",
        "logical_version": auditmod.LOGICAL_VERSION,
        "world_seed": 20261020,
        "spacing_m": 30.0,
        "plan_version": plan_version,
        "owner_rule": auditmod.OWNER_RULE,
        "root_world_xz": [origin[0] + root[1], origin[1] + root[0]],
        "member_sha256": _world_digest(member_world),
        "root_kind": kind,
        "status": status,
    }
    body = json.dumps({"metadata": payload, "arrays": {}}, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    return "wdc-" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _bundle(height, mask, receiver, seeds, terminal, counts, dirty,
            owner, roots, members, chains, shared, origin, plan_version):
    rows, columns = len(height), len(height[0])
    n = rows * columns
    elevation = np.array(height, np.float64)
    resolved = np.array(mask, bool)
    rec = np.full((rows, columns), -1, np.int64)
    kinds = np.full((rows, columns), "inactive", dtype="<U16")
    seed_array = np.zeros((rows, columns), bool)
    complete = np.zeros((rows, columns), bool)
    up = np.zeros((rows, columns), np.int64)
    owner_array = np.full((rows, columns), -1, np.int64)
    for r in range(rows):
        for c in range(columns):
            if not mask[r][c]:
                continue
            nxt = receiver[r][c]
            rec[r][c] = -1 if nxt is None else _flat(rows, columns, nxt[0], nxt[1])
            kinds[r][c] = "interior" if nxt is not None else (
                "retained" if not seeds[r][c] else "unknown_boundary")
            seed_array[r][c] = seeds[r][c]
            complete[r][c] = not dirty[(r, c)]
            up[r][c] = counts[(r, c)]
            owner_array[r][c] = owner[r][c]

    root_cells = np.array([_flat(rows, columns, r, c) for r, c in roots], np.int64)
    root_complete = np.array([not dirty[root] for root in roots], bool)
    member_counts = np.array([len(bucket) for bucket in members], np.int64)
    member_ptr = np.zeros(len(roots) + 1, np.int64)
    member_ptr[1:] = np.cumsum(member_counts)
    member_cells = np.array([_flat(rows, columns, r, c) for bucket in members
                             for r, c in bucket], np.int64)
    stem_lengths = [len(chain) for chain in chains]
    mainstem_ptr = np.zeros(len(roots) + 1, np.int64)
    mainstem_ptr[1:] = np.cumsum(stem_lengths)
    mainstem_cells = np.array([_flat(rows, columns, r, c) for chain in chains
                               for r, c in chain], np.int64)
    faces = np.array(shared, np.int64).reshape(-1, 2)

    arrays = {
        "elevation_m": elevation,
        "resolved_mask": resolved,
        "receiver": rec,
        "terminal_kind": kinds,
        "upstream_unknown_mask": seed_array,
        "complete_mask": complete,
        "upstream_cells": up,
        "owner_index": owner_array,
        "root_cells": root_cells,
        "root_complete": root_complete,
        "member_counts": member_counts,
        "member_ptr": member_ptr,
        "member_cells": member_cells,
        "mainstem_ptr": mainstem_ptr,
        "mainstem_cells": mainstem_cells,
        "shared_face_cells": faces,
    }
    candidates = []
    for slot, root in enumerate(roots):
        closed = bool(root_complete[slot])
        kind = str(kinds[root[0], root[1]])
        if closed:
            status = "candidate_closed"
            reasons = ["complete"]
        elif kind == "unknown_boundary":
            status = "candidate_truncated"
            reasons = ["support_truncated", "upstream_unknown"]
        else:
            status = "candidate_open_upstream"
            reasons = ["upstream_unknown"]
        # the declared member/mainstem digests, recomputed here with the same
        # independent rule the audit uses (world (x, z), int64 little-endian)
        member_world = np.stack([origin[0] + np.array([c for _, c in members[slot]]),
                                 origin[1] + np.array([r for r, _ in members[slot]])],
                                axis=1).astype(np.int64)
        member_world = member_world[np.lexsort((member_world[:, 1], member_world[:, 0]))]
        chain_world = np.stack([origin[0] + np.array([c for _, c in chains[slot]]),
                                origin[1] + np.array([r for r, _ in chains[slot]])],
                               axis=1).astype(np.int64)
        candidates.append({
            "candidate_id": _candidate_id(slot, root, kind, status, member_world, origin, plan_version),
            "root_index": slot,
            "root_cell": int(root_cells[slot]),
            "root_world_xz": [origin[0] + root[1], origin[1] + root[0]],
            "root_kind": kind,
            "member_count": int(member_counts[slot]),
            "member_sha256": _world_digest(member_world),
            "status": status,
            "reason_codes": reasons,
            "physical_endpoint_evidence": "basin_pending" if kind == "retained" else "none",
            "structural_only": True,
            "evidence_level": "structural_candidate",
            "mainstem_node_count": int(stem_lengths[slot]),
            "mainstem_edges": int(max(stem_lengths[slot] - 1, 0)),
            "mainstem_sha256": _world_digest(chain_world),
        })
    support = {
        "world_seed": 20261020,
        "spacing_m": 30.0,
        "origin_native_xz": [origin[0], origin[1]],
        "shape_zx": [rows, columns],
        "support_cells": n,
        "max_cells": 148225,
        "plan_version": plan_version,
        "storage_representation": "signed_int64_native_cells",
        "source_sha256": "5" * 64,
    }
    metadata = {
        "schema": "metric-world-domain-candidates-v1",
        "source_kind": "synthetic_fixture",
        "support_identity_sha256": "1" * 64,
        "field_mask_sha256": FIELD_MASK_SHA,
        "logical_version": auditmod.LOGICAL_VERSION,
        "owner_rule": auditmod.OWNER_RULE,
        "support": {"world_seed": 20261020, "spacing_m": 30.0,
                    "plan_version": plan_version,
                    "source_sha256": "5" * 64},
        "counts": {"root_count": len(roots)},
    }
    return {
        "schema": "metric-world-domain-candidates-v1",
        "support": support,
        "metadata": metadata,
        "arrays": arrays,
        "candidates": candidates,
        "identity_sha256": "2" * 64,
    }


def write_package(directory, bundle, *, manifest_text=None, arrays_override=None):
    """Write manifest.json + arrays.npz in the declared on-disk shape."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    arrays = bundle["arrays"] if arrays_override is None else arrays_override
    with open(target / "arrays.npz", "wb") as stream:
        np.savez(stream, **{name: arrays[name] for name in sorted(arrays)})
    records = {}
    for name in sorted(arrays):
        value = arrays[name]
        records[name] = {"shape": list(value.shape), "dtype": value.dtype.str,
                         "sha256": auditmod.array_sha256(value)}
    manifest = {
        "schema": bundle["schema"],
        "support": bundle["support"],
        "metadata": bundle["metadata"],
        "candidates": bundle["candidates"],
        "identity_sha256": bundle["identity_sha256"],
        "arrays": records,
        "source_binding": {
            "kind": "content_binding_not_signature",
            "page_records": [{"path": "synthetic/fixture.npz", "sha256": "3" * 64}],
        },
    }
    text = json.dumps(manifest, sort_keys=True) if manifest_text is None else manifest_text
    (target / "manifest.json").write_text(text, encoding="utf-8")
    return target


class WindowFamilyMixin:
    """Negative cases and window-family comparisons, mixed into the audit tests."""

    def test_cross_domain_drain_is_caught(self):
        def mutate(bundle):
            arrays = bundle["arrays"]
            owner = arrays["owner_index"].reshape(-1)
            rec = arrays["receiver"].reshape(-1)
            # point one cell's receiver at a cell owned by another candidate
            for cell in range(rec.size):
                target = int(rec[cell])
                if target >= 0 and owner[target] != owner[cell]:
                    self.fail("the fixture already drains across owners")
            victim = int(np.flatnonzero(owner >= 0)[0])
            donor = int(np.flatnonzero(owner == owner[victim])[0])
            donor = int(np.flatnonzero((owner >= 0))[-1])
            rec[donor] = victim
            if owner[donor] == owner[victim]:
                other = int(np.flatnonzero((owner >= 0) & (owner != owner[victim]))[0])
                rec[donor] = other
            arrays["receiver"] = rec.reshape(arrays["receiver"].shape)
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("cross_domain_drain", report["reasons"])
        self.assertGreater(report["counters"]["cross_domain_drain_cells"], 0)

    def test_duplicate_root_is_caught(self):
        def mutate(bundle):
            roots = bundle["arrays"]["root_cells"]
            roots[1] = roots[0]
            bundle["arrays"]["root_cells"] = roots
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("root_duplicate", report["reasons"])

    def test_open_outflow_label_is_not_emitted(self):
        def mutate(bundle):
            kinds = bundle["arrays"]["terminal_kind"]
            kinds[0, 0] = "open_outflow"
            bundle["arrays"]["terminal_kind"] = kinds
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertIn("terminal_kind_mismatch", report["reasons"])
        self.assertIn("open_outflow_present", report["reasons"])

    def test_unexpected_array_is_reported(self):
        bundle = build_fixture()
        package = write_package(self.root / "extra", bundle)
        manifest = json.loads(package.joinpath("manifest.json").read_text(encoding="utf-8"))
        manifest["arrays"]["some_extra"] = {"shape": [3], "dtype": "<i8",
                                             "sha256": "0" * 64}
        package.joinpath("manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8")
        report = auditmod.audit_bundle(package)
        self.assertIn("arrays_record_set_mismatch", report["reasons"])

    # -- window family ------------------------------------------------------ #
    def test_window_comparison_compares_shared_complete_roots_only(self):
        bundle = build_fixture()
        left = write_package(self.root / "left", bundle)
        shifted_root = self.root / "right"
        write_package(shifted_root, bundle)
        comparison = auditmod.compare_windows(left, shifted_root)
        self.assertEqual(comparison["status"], "PASS")
        self.assertEqual(comparison["shared_roots_complete_on_both"], 2)
        self.assertEqual(comparison["member_set_mismatches"], [])
        self.assertEqual(comparison["mainstem_mismatches"], [])
        self.assertEqual(comparison["complete_in_one_window_only"], [])
        # the four border corners are incomplete on both sides and are listed
        self.assertEqual(len(comparison["incomplete_on_both_sides"]), 4)

    def test_window_comparison_reports_a_member_mismatch(self):
        """A tampered package is refused outright instead of being compared."""
        bundle = build_fixture()
        left = write_package(self.root / "left", bundle)
        other = build_fixture()
        arrays = dict(other["arrays"])
        ptr = arrays["member_ptr"]
        cells = arrays["member_cells"].copy()
        complete_slots = [slot for slot in range(int(ptr.size) - 1)
                          if bool(arrays["root_complete"][slot])]
        self.assertEqual(len(complete_slots), 2)
        first = int(ptr[complete_slots[0]])
        second = int(ptr[complete_slots[1]])
        cells[first], cells[second] = cells[second], cells[first]
        arrays["member_cells"] = cells
        right = write_package(self.root / "right", other, arrays_override=arrays)
        with self.assertRaises(auditmod.AuditRefused) as caught:
            auditmod.compare_windows(left, right)
        self.assertEqual(caught.exception.reason, "compare_refused_bundle_failed_audit")

    def test_window_comparison_keeps_incomplete_roots_separate(self):
        """A one-sided completeness claim is refused, not silently compared."""
        left_bundle = build_fixture()
        left = write_package(self.root / "left", left_bundle)
        right_bundle = build_fixture()
        arrays = dict(right_bundle["arrays"])
        complete = arrays["root_complete"]
        slot = int(np.flatnonzero(complete)[0])
        complete[slot] = False
        arrays["root_complete"] = complete
        right = write_package(self.root / "right", right_bundle, arrays_override=arrays)
        with self.assertRaises(auditmod.AuditRefused) as caught:
            auditmod.compare_windows(left, right)
        self.assertEqual(caught.exception.reason, "compare_refused_bundle_failed_audit")

    def test_full_support_is_audited_within_the_declared_time_budget(self):
        """A 65x65 window is audited in full, well inside the per-case budget.

        The time figures are observations of this machine, not a performance
        guarantee; the assertion only guards against an accidental quadratic (or
        per-root re-scan) blow-up in the audit.
        """
        size = 65
        rows = np.arange(size)[:, None]
        cols = np.arange(size)[None, :]
        height = (200.0 + 0.05 * (rows - size / 2) ** 2 + 0.07 * (cols - size / 2) ** 2
                  + 25.0 * np.cos(cols / 9.0) + 20.0 * np.sin(rows / 6.0)).tolist()
        bundle = build_fixture(height=height)
        package = write_package(self.root / "p65", bundle)
        started = time.monotonic()
        report = auditmod.audit_bundle(package)
        elapsed = time.monotonic() - started
        self.assertEqual(report["status"], "PASS", report["reasons"])
        self.assertLess(elapsed, 60.0)
        self.assertEqual(report["counters"]["support_cells"], size * size)
        self.assertEqual(report["scope"]["cells_visited"], size * size)
        self.assertFalse(report["scope"]["sampled"])
        report["notes"]["timing_observation"] = {"wall_s": round(elapsed, 3),
                                                "is_limit": False}


class FieldBypassRegressionTests(unittest.TestCase):
    """The two bypasses the main branch reproduced, pinned as regressions.

    Both were *actual* passes of the previous auditor. They are kept here so a future
    edit cannot quietly restore either one.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_deleting_candidate_fields_is_refused_not_ignored(self):
        """Bypass 1: delete every candidate's keys and the old audit still passed."""
        bundle = build_fixture()
        for candidate in bundle["candidates"]:
            for field in ("physical_endpoint_evidence", "member_sha256",
                          "candidate_id", "structural_only", "status", "root_kind",
                          "reason_codes", "mainstem_sha256", "root_index"):
                candidate.pop(field, None)
        package = write_package(self.root / "stripped", bundle)
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("candidate_field_missing", report["reasons"])
        missing = [check["detail"]["missing"] for check in report["checks"]
                   if check["check"] == "candidate_field_missing" and check["passed"] is False]
        self.assertTrue(missing)
        self.assertIn("physical_endpoint_evidence", missing[0])

    def test_deleting_only_the_physical_claim_field_is_refused(self):
        """The narrow version: removing just the physical field must not be free."""
        bundle = build_fixture()
        for candidate in bundle["candidates"]:
            candidate.pop("physical_endpoint_evidence", None)
        package = write_package(self.root / "nophysical", bundle)
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("candidate_field_missing", report["reasons"])

    def test_incoherent_package_cannot_join_a_comparison(self):
        """Bypass 2: shift the origin of one copy and the old compare still passed."""
        bundle = build_fixture()
        left = write_package(self.root / "left", bundle)
        other = build_fixture()
        other["support"]["origin_native_xz"] = [1000000, 1000000]
        right = write_package(self.root / "right", other)
        with self.assertRaises(auditmod.AuditRefused) as caught:
            auditmod.compare_windows(left, right)
        self.assertEqual(caught.exception.reason, "compare_refused_bundle_failed_audit")

    def test_comparison_with_zero_comparable_roots_is_not_run(self):
        """Nothing comparable must never read as a pass."""
        bundle = build_fixture()
        left = write_package(self.root / "left", bundle)
        # A self-consistent package with a *different* world root set: the same
        # fixture area, but every root is measured 100 cells away.
        other = build_fixture(origin=(ORIGIN[0] + 100, ORIGIN[1] + 100))
        right = write_package(self.root / "right", other)
        report = auditmod.audit_bundle(right)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        comparison = auditmod.compare_windows(left, right)
        self.assertEqual(comparison["status"], "NOT_RUN")
        self.assertEqual(comparison["reason"], "no_root_complete_on_both_sides")
        self.assertEqual(comparison["shared_roots_complete_on_both"], 0)
        self.assertEqual(comparison["shared_roots"], 0)

    def test_plan_version_mismatch_is_not_a_same_object_pass(self):
        bundle = build_fixture()
        left = write_package(self.root / "left", bundle)
        other = build_fixture()
        other["support"]["plan_version"] = 2
        other["metadata"]["support"]["plan_version"] = 2
        # The IDs were produced under plan_version 1, so re-derive nothing: the audit
        # must refuse the copy outright rather than compare across versions.
        right = write_package(self.root / "right", other)
        report = auditmod.audit_bundle(right)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("candidate_id_mismatch", report["reasons"])

    def test_version_mismatch_is_rejected_not_passed(self):
        """Two self-consistent packages under different plan versions: REJECTED.

        The structural comparison is still informative (and is reported), but it is
        explicitly *not* a same-logical-object acceptance.
        """
        left_bundle = build_fixture()
        left = write_package(self.root / "left", left_bundle)
        other = build_fixture(plan_version=2)
        right = write_package(self.root / "right", other)
        report = auditmod.audit_bundle(right)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        comparison = auditmod.compare_windows(left, right)
        self.assertEqual(comparison["status"], "REJECTED")
        self.assertEqual(comparison["reason"], "version_mismatch")
        self.assertFalse(comparison["same_logical_objects"])
        self.assertTrue(comparison["structural_comparison"])
        self.assertEqual(comparison["member_set_mismatches"], [])
        self.assertEqual(comparison["shared_roots_complete_on_both"], 2)

    def test_same_plan_version_requires_matching_candidate_ids(self):
        bundle = build_fixture()
        left = write_package(self.root / "left", bundle)
        other = build_fixture()
        right = write_package(self.root / "right", other)
        comparison = auditmod.compare_windows(left, right)
        self.assertEqual(comparison["status"], "PASS", comparison["reason"])
        self.assertTrue(comparison["same_logical_objects"])
        self.assertEqual(comparison["candidate_id_mismatches"], [])

    def test_a_different_source_bed_is_refused(self):
        left_bundle = build_fixture()
        left = write_package(self.root / "left", left_bundle)
        other = build_fixture()
        other["metadata"]["field_mask_sha256"] = "7" * 64
        other["support"]["source_sha256"] = "8" * 64
        other["metadata"]["support"]["source_sha256"] = "8" * 64
        right = write_package(self.root / "right", other)
        comparison = auditmod.compare_windows(left, right)
        self.assertEqual(comparison["status"], "REJECTED")
        self.assertEqual(comparison["reason"],
                         "source_identity_mismatch:source_sha256")

    def test_metadata_support_origin_is_bound_to_the_authority(self):
        """The reproduced bypass: edit ONLY metadata.support.origin and nothing else."""
        bundle = build_fixture()
        bundle["metadata"]["support"]["origin_native_xz"] = [1000000, 1000000]
        package = write_package(self.root / "origin", bundle)
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("support_copy_mismatch", report["reasons"])
        detail = next(check["detail"] for check in report["checks"]
                      if check["check"] == "support_copy_mismatch"
                      and check["passed"] is False)
        self.assertEqual(detail["copy"], "metadata.support")
        self.assertEqual([item["field"] for item in detail["differences"]],
                         ["origin_native_xz"])

    def test_metadata_support_shape_and_count_cannot_be_edited_alone(self):
        for field, falsified in (("shape_zx", [257, 256]),
                                 ("support_cells", 66048),
                                 ("spacing_m", 10.0),
                                 ("world_seed", 20261021),
                                 ("plan_version", 2)):
            with self.subTest(field=field):
                bundle = build_fixture()
                bundle["metadata"]["support"][field] = falsified
                package = write_package(self.root / ("falsified-" + field), bundle)
                report = auditmod.audit_bundle(package)
                self.assertEqual(report["status"], "FAILED")
                self.assertIn("support_copy_mismatch", report["reasons"])

    def test_declaration_origin_is_bound_too(self):
        bundle = build_fixture()
        package = write_package(self.root / "decl", bundle)
        manifest = json.loads(package.joinpath("manifest.json").read_text(encoding="utf-8"))
        manifest["declaration"] = {"origin_native_xz": [1, 2],
                                   "shape_zx": bundle["support"]["shape_zx"]}
        package.joinpath("manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8")
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("support_copy_mismatch", report["reasons"])

    def test_authority_plan_rules_are_enforced(self):
        """30 m, the frozen seed and a cell count come from the authority itself."""
        bundle = build_fixture()
        bundle["support"]["spacing_m"] = 10.0
        report = auditmod.audit_bundle(write_package(self.root / "sp", bundle))
        self.assertIn("support_spacing_not_30m", report["reasons"])

        bundle = build_fixture()
        bundle["support"]["world_seed"] = 1
        report = auditmod.audit_bundle(write_package(self.root / "seed", bundle))
        self.assertIn("support_world_seed_mismatch", report["reasons"])

        bundle = build_fixture()
        bundle["support"]["support_cells"] = 66048
        report = auditmod.audit_bundle(write_package(self.root / "cells", bundle))
        self.assertIn("support_cells_mismatch", report["reasons"])

    def test_resolved_infinity_is_refused_by_the_input_gate(self):
        """+-inf inside the resolved set: explicit gate, not a side effect of topology."""
        bundle = build_fixture()
        elevation = bundle["arrays"]["elevation_m"]
        elevation[5, 5] = np.inf
        bundle["arrays"]["elevation_m"] = elevation
        report = auditmod.audit_bundle(write_package(self.root / "inf", bundle))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("resolved_elevation_not_finite", report["reasons"])

    def test_mainstem_path_length_counts_diagonal_hops(self):
        """Path length is sum(30*hypot(dx,dz)), strictly above the edges*30 bound."""
        import math as _math
        rows = columns = 5
        receiver = np.full((rows, columns), -1, np.int64)
        resolved = np.ones((rows, columns), bool)
        root = 2 * columns + 2
        receiver.reshape(-1)[0] = 1 * columns + 1
        receiver.reshape(-1)[1 * columns + 1] = root
        upstream = np.zeros((rows, columns), np.int64)
        upstream.reshape(-1)[0] = 1
        upstream.reshape(-1)[1 * columns + 1] = 2
        upstream.reshape(-1)[root] = 3
        chain = auditmod.independent_mainstem(root, receiver, resolved, upstream, ORIGIN)
        self.assertEqual([int(cell) for cell in chain],
                         [0, 1 * columns + 1, root])
        chain_rows, chain_cols = np.divmod(chain, columns)
        dx = np.diff(chain_cols.astype(np.float64))
        dz = np.diff(chain_rows.astype(np.float64))
        expected = float(auditmod.SPACING_M * np.hypot(dx, dz).sum())
        self.assertAlmostEqual(expected, 2 * 30.0 * _math.sqrt(2.0), places=9)
        self.assertGreater(expected, 2 * 30.0)

    def test_same_world_seed_is_required_for_a_comparison(self):
        bundle = build_fixture()
        left = write_package(self.root / "left", bundle)
        other = build_fixture()
        other["support"]["world_seed"] = 20261021
        other["metadata"]["support"]["world_seed"] = 20261021
        right = write_package(self.root / "right", other)
        # The copy's IDs no longer match its declared seed, so it is refused; either
        # refusal is a failure, never a PASS.
        report = auditmod.audit_bundle(right)
        self.assertEqual(report["status"], "FAILED")


class WorldDomainAuditTests(WindowFamilyMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # -- the passing fixture ------------------------------------------------ #
    def test_hand_fixture_passes_and_shows_closed_and_open_roots(self):
        bundle = build_fixture()
        package = write_package(self.root / "p1", bundle)
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        counters = report["counters"]
        self.assertEqual(counters["roots"], 6)
        self.assertEqual(counters["roots_complete"], 2)
        self.assertEqual(counters["roots_open_upstream"], 4)
        self.assertFalse(report["scope"]["sampled"])
        self.assertEqual(report["scope"]["cells_visited"], ROWS * COLUMNS)
        self.assertEqual(report["independence"]["banned_modules_loaded"], [])
        # the two closed roots are the two interior pits, by world coordinate
        closed = [candidate["root_world_xz"] for candidate in bundle["candidates"]
                  if candidate["status"] == "candidate_closed"]
        self.assertEqual(closed, [[ORIGIN[0] + 4, ORIGIN[1] + 4],
                                  [ORIGIN[0] + 7, ORIGIN[1] + 7]])
        # a strictly descending mainstem exists for each closed root
        self.assertGreaterEqual(counters["longest_mainstem_cells"], 2)
        self.assertEqual(report["notes"]["evidence_level"], "structural_candidate")
        self.assertEqual(report["notes"]["candidate_status_counts"]["candidate_closed"], 2)

    def test_member_sets_and_mainstems_are_independently_derived(self):
        bundle = build_fixture()
        arrays = bundle["arrays"]
        eleva = arrays["elevation_m"]
        # every member of a closed root drains to that root, and the chain is
        # strictly descending with a donor-free head
        for slot, candidate in enumerate(bundle["candidates"]):
            lo = int(arrays["member_ptr"][slot])
            hi = int(arrays["member_ptr"][slot + 1])
            cells = arrays["member_cells"][lo:hi]
            self.assertGreater(cells.size, 0)
            for cell in cells:
                walk = int(cell)
                seen = set()
                while int(arrays["receiver"].reshape(-1)[walk]) >= 0:
                    self.assertNotIn(walk, seen)
                    seen.add(walk)
                    walk = int(arrays["receiver"].reshape(-1)[walk])
                self.assertEqual(walk, int(arrays["root_cells"][slot]))
            stem_lo = int(arrays["mainstem_ptr"][slot])
            stem_hi = int(arrays["mainstem_ptr"][slot + 1])
            chain = arrays["mainstem_cells"][stem_lo:stem_hi]
            self.assertEqual(int(chain[-1]), int(arrays["root_cells"][slot]))
            heights = eleva.reshape(-1)[chain]
            self.assertTrue(np.all(np.diff(heights) < 0.0))

    def test_member_digest_must_match_the_declared_rule(self):
        def mutate(bundle):
            bundle["candidates"][0]["member_sha256"] = "0" * 64
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("candidate_member_digest_mismatch", report["reasons"])

    def test_mainstem_digest_must_match_the_declared_rule(self):
        def mutate(bundle):
            bundle["candidates"][0]["mainstem_sha256"] = "1" * 64
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertIn("candidate_mainstem_digest_mismatch", report["reasons"])

    def test_top_level_support_layout_is_accepted_and_recorded(self):
        """A flattened support record is read too, and the layout used is reported."""
        bundle = build_fixture()
        package = write_package(self.root / "flat", bundle)
        manifest = json.loads(package.joinpath("manifest.json").read_text(encoding="utf-8"))
        manifest["support"] = dict(bundle["support"])
        package.joinpath("manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8")
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        self.assertEqual(report["notes"]["support_record_layout"], "support")

    def test_nested_support_layout_is_the_declared_one(self):
        bundle = build_fixture()
        package = write_package(self.root / "nested", bundle)
        manifest = json.loads(package.joinpath("manifest.json").read_text(encoding="utf-8"))
        manifest["support"] = {"arrays": {}, "identity_sha256": "4" * 64,
                               "metadata": dict(bundle["support"])}
        package.joinpath("manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8")
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "PASS", report["reasons"])
        self.assertEqual(report["notes"]["support_record_layout"], "support.metadata")

    def test_cold_subprocess_audit_is_independent(self):
        bundle = build_fixture()
        package = write_package(self.root / "p1", bundle)
        report_path = self.root / "audit.json"
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools" / "audit_world_domains.py"),
             "--bundle", str(package), "--report", str(report_path)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS", report["reasons"])
        self.assertIn('terrain_pipeline.drainage', report["independence"]["terrain_pipeline_loaded"])
        self.assertEqual(report["independence"]["banned_modules_loaded"], [])

    def test_audit_refuses_inside_a_process_that_loaded_the_producer(self):
        fake = {"terrain_pipeline.surface_rivers.metric_world_domains": object()}
        with self.assertRaises(auditmod.AuditRefused) as caught:
            auditmod.require_independent_process(fake)
        self.assertEqual(caught.exception.reason, "independent_process_required")
        bundle = build_fixture()
        package = write_package(self.root / "p1", bundle)
        report = auditmod.audit_bundle(package, modules=fake)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("independent_process_required", report["reasons"])

    # -- negative cases ----------------------------------------------------- #
    def _mutated(self, mutate, name="mutated"):
        bundle = build_fixture()
        mutate(bundle)
        return write_package(self.root / name, bundle)

    def test_wrong_owner_is_caught(self):
        def mutate(bundle):
            owner = bundle["arrays"]["owner_index"]
            flat = owner.reshape(-1)
            # move one owned cell to a different candidate
            victim = int(np.flatnonzero(flat == 0)[0])
            flat[victim] = 1
            bundle["arrays"]["owner_index"] = flat.reshape(owner.shape)
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("owner_mismatch", report["reasons"])

    def test_wrong_completeness_is_caught(self):
        def mutate(bundle):
            complete = bundle["arrays"]["complete_mask"]
            complete[5, 5] = not complete[5, 5]
            bundle["arrays"]["complete_mask"] = complete
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("complete_mask_mismatch", report["reasons"])

    def test_wrong_upstream_counts_are_caught(self):
        def mutate(bundle):
            up = bundle["arrays"]["upstream_cells"]
            up[0, 0] += 1
            bundle["arrays"]["upstream_cells"] = up
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertIn("upstream_cells_mismatch", report["reasons"])

    def test_wrong_mainstem_is_caught(self):
        def mutate(bundle):
            ptr = bundle["arrays"]["mainstem_ptr"]
            cells = bundle["arrays"]["mainstem_cells"]
            slot = next(index for index in range(ptr.size - 1)
                        if int(ptr[index + 1]) - int(ptr[index]) > 1)
            lo, hi = int(ptr[slot]), int(ptr[slot + 1])
            # reverse a real multi-cell chain: contiguity and donor choice break
            cells[lo:hi] = cells[lo:hi][::-1]
            bundle["arrays"]["mainstem_cells"] = cells
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("mainstem_chain_mismatch", report["reasons"])

    def test_mainstem_tie_break_is_world_dictionary_order(self):
        """Two donors with equal contribution counts: the smaller world (x, z) wins."""
        # A hand-written receiver graph, so the tie is exact and not a side effect
        # of some other part of the fixture: root (2, 2) has exactly two donors,
        # both carrying the same upstream count.
        rows = columns = 5
        receiver = np.full((rows, columns), -1, np.int64)
        resolved = np.ones((rows, columns), bool)
        upstream = np.zeros((rows, columns), np.int64)
        root = 2 * columns + 2
        left_donor = 1 * columns + 1
        right_donor = 1 * columns + 3
        receiver.reshape(-1)[left_donor] = root
        receiver.reshape(-1)[right_donor] = root
        upstream.reshape(-1)[left_donor] = 5
        upstream.reshape(-1)[right_donor] = 5
        upstream.reshape(-1)[root] = 11

        chain = auditmod.independent_mainstem(root, receiver, resolved, upstream, ORIGIN)
        picked = int(chain[-2])
        self.assertEqual(picked, left_donor)
        self.assertEqual(int(chain[-1]), root)
        self.assertEqual(chain.size, 2)

        # a tie between two donors in the same column is broken by world z (the
        # smaller one wins), which is the same declared rule seen on the other axis
        receiver = np.full((rows, columns), -1, np.int64)
        upper_donor = 1 * columns + 2
        lower_donor = 3 * columns + 2
        receiver.reshape(-1)[upper_donor] = root
        receiver.reshape(-1)[lower_donor] = root
        upstream = np.zeros((rows, columns), np.int64)
        upstream.reshape(-1)[upper_donor] = 7
        upstream.reshape(-1)[lower_donor] = 7
        upstream.reshape(-1)[root] = 15
        chain = auditmod.independent_mainstem(root, receiver, resolved, upstream, ORIGIN)
        self.assertEqual(int(chain[-2]), upper_donor)

        # and the higher contribution wins regardless of coordinate order
        upstream.reshape(-1)[lower_donor] = 8
        chain = auditmod.independent_mainstem(root, receiver, resolved, upstream, ORIGIN)
        self.assertEqual(int(chain[-2]), lower_donor)

    def test_wrong_donor_tie_break_is_caught(self):
        def mutate(bundle):
            ptr = bundle["arrays"]["mainstem_ptr"]
            cells = bundle["arrays"]["mainstem_cells"]
            # drop the head of a multi-cell chain: the chain then starts at a cell
            # that still has a donor, so the rebuilt chain must differ
            slot = next(index for index in range(ptr.size - 1)
                        if int(ptr[index + 1]) - int(ptr[index]) > 3)
            lo, hi = int(ptr[slot]), int(ptr[slot + 1])
            cells[lo:hi - 1] = cells[lo + 1:hi]
            bundle["arrays"]["mainstem_ptr"] = np.concatenate(
                [ptr[:slot + 1], [ptr[slot + 1] - 1], ptr[slot + 2:]])
            bundle["arrays"]["mainstem_cells"] = cells[:cells.size - 1]
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("mainstem_chain_mismatch", report["reasons"])

    def test_false_physical_claim_is_caught(self):
        def mutate(bundle):
            bundle["candidates"][0]["physical_endpoint_evidence"] = "ocean_outlet"
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("false_physical_claim", report["reasons"])

    def test_closed_claim_on_an_open_root_is_caught(self):
        def mutate(bundle):
            changed = False
            for candidate in bundle["candidates"]:
                if candidate["status"] != "candidate_closed":
                    candidate["status"] = "candidate_closed"
                    changed = True
                    break
            assert changed, "the fixture must contain an incomplete root"
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertIn("candidate_status_mismatch", report["reasons"])

    def test_upstream_only_claim_on_a_cut_root_is_caught(self):
        """A root on the support cut must be ``candidate_truncated``, not merely open."""
        def mutate(bundle):
            changed = False
            for candidate in bundle["candidates"]:
                if candidate["status"] == "candidate_truncated":
                    candidate["status"] = "candidate_open_upstream"
                    changed = True
                    break
            assert changed, "the fixture must contain a root on the support cut"
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertIn("candidate_status_mismatch", report["reasons"])

    def test_missing_structural_only_flag_is_caught(self):
        def mutate(bundle):
            bundle["candidates"][0]["structural_only"] = False
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertIn("structural_only_violation", report["reasons"])

    def test_root_order_must_be_world_dictionary_order(self):
        def mutate(bundle):
            bundle["arrays"]["root_cells"] = bundle["arrays"]["root_cells"][::-1].copy()
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("root_order_mismatch", report["reasons"])

    def test_shared_face_mismatch_is_caught(self):
        def mutate(bundle):
            faces = bundle["arrays"]["shared_face_cells"]
            bundle["arrays"]["shared_face_cells"] = faces[: max(0, faces.shape[0] - 1)].copy()
        report = auditmod.audit_bundle(self._mutated(mutate))
        self.assertIn("shared_face_mismatch", report["reasons"])

    def test_object_array_is_refused_before_allocation(self):
        bundle = build_fixture()
        arrays = dict(bundle["arrays"])
        arrays["elevation_m"] = np.array([[{"a": 1}]], dtype=object)
        package = write_package(self.root / "object", bundle, arrays_override=arrays)
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("object_dtype_rejected", report["reasons"])

    def test_truncated_npy_member_is_refused(self):
        bundle = build_fixture()
        package = write_package(self.root / "short", bundle)
        # replace arrays.npz with a member whose header claims far more bytes
        payload = io.BytesIO()
        np.lib.format.write_array_header_1_0(
            payload, {"descr": "<f8", "fortran_order": False, "shape": (100, 100)})
        header = payload.getvalue()
        import zipfile
        with zipfile.ZipFile(package / "arrays.npz", "w") as archive:
            archive.writestr("elevation_m.npy", header + b"\x00" * 16)
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("npy_header_size_mismatch", report["reasons"])

    def test_duplicate_json_key_is_refused(self):
        bundle = build_fixture()
        package = write_package(self.root / "dup", bundle)
        text = (package / "manifest.json").read_text(encoding="utf-8")
        duplicated = text.replace('{"arrays"', '{"arrays": {}, "arrays"', 1)
        self.assertNotEqual(text, duplicated)
        package.joinpath("manifest.json").write_text(duplicated, encoding="utf-8")
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("duplicate_json_key", report["reasons"])

    def test_non_finite_json_and_elevation_are_refused(self):
        bundle = build_fixture()
        package = write_package(self.root / "nanjson", bundle)
        text = (package / "manifest.json").read_text(encoding="utf-8")
        package.joinpath("manifest.json").write_text(
            text.replace('"spacing_m": 30.0', '"spacing_m": NaN', 1), encoding="utf-8")
        report = auditmod.audit_bundle(package)
        self.assertIn("non_finite_json", report["reasons"])

        def mutate(bundle):
            elevation = bundle["arrays"]["elevation_m"]
            elevation[5, 5] = np.nan
            bundle["arrays"]["elevation_m"] = elevation
        report = auditmod.audit_bundle(self._mutated(mutate, "nanfield"))
        self.assertIn("unresolved_elevation_not_nan", report["reasons"])

    def test_array_hash_mismatch_is_caught(self):
        bundle = build_fixture()
        package = write_package(self.root / "hash", bundle)
        manifest = json.loads(package.joinpath("manifest.json").read_text(encoding="utf-8"))
        manifest["arrays"]["receiver"]["sha256"] = "0" * 64
        package.joinpath("manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8")
        report = auditmod.audit_bundle(package)
        self.assertIn("arrays_sha_mismatch", report["reasons"])

    def test_cell_budget_is_refused(self):
        bundle = build_fixture()
        bundle["support"]["shape_zx"] = [386, 386]
        package = write_package(self.root / "budget", bundle)
        report = auditmod.audit_bundle(package)
        self.assertEqual(report["status"], "FAILED")
        self.assertIn("cell_budget_exceeded", report["reasons"])

    def test_report_target_must_not_exist(self):
        target = self.root / "audit.json"
        target.write_text("keep", encoding="utf-8")
        with self.assertRaises(auditmod.AuditRefused) as caught:
            auditmod.write_report(target, {"status": "PASS"})
        self.assertEqual(caught.exception.reason, "report_target_exists")
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")


class PrepareToolTests(unittest.TestCase):
    """Only the scheduling and I/O duties; the producer is never imported."""

    def test_declared_supports_match_the_scale_ladder(self):
        origin, shape = preparemod.declared_support("p1")
        self.assertEqual(origin, (42173, 42874))
        self.assertEqual(shape, (257, 257))
        origin, shape = preparemod.declared_support("p2")
        self.assertEqual(origin, (42173, 42874))
        self.assertEqual(shape, (385, 385))
        self.assertEqual(385 * 385, preparemod.MAX_SUPPORT_CELLS)
        origin, shape = preparemod.declared_support("p2-shifted")
        self.assertEqual(origin, (42270, 42743))
        self.assertEqual(shape, (385, 385))
        self.assertNotEqual(origin, preparemod.declared_support("p2")[0])

    def test_support_budget_and_window_are_never_implicitly_enlarged(self):
        with self.assertRaises(SystemExit):
            preparemod.resolve_support(None, (0, 0), (386, 386))
        with self.assertRaises(SystemExit):
            preparemod.resolve_support(None, (0, 0), (1, 10))
        with self.assertRaises(SystemExit):
            preparemod.resolve_support(None, None, None)
        with self.assertRaises(SystemExit):
            preparemod.resolve_support("p2", (1, 2), None)
        origin, shape = preparemod.resolve_support("p2-shifted", None, None)
        self.assertEqual((origin, shape), ((42270, 42743), (385, 385)))

    def test_source_request_records_are_read_with_their_pins(self):
        """The source request is data, so the fixture is built here, not read from disk."""
        directory = tempfile.mkdtemp()
        request = Path(directory) / "request.json"
        pins = [{"path": "pages/td-page-%d.npz" % index, "sha256": "%064x" % index}
                for index in range(4)]
        request.write_text(json.dumps({"schema": "native-30m-source-request-v1",
                                       "world_seed": 20261020,
                                       "source_records": pins}), encoding="utf-8")
        records, path = preparemod.read_source_records(request)
        self.assertEqual(len(records), 4)
        self.assertEqual([record["sha256"] for record in records],
                         [pin["sha256"] for pin in pins])
        self.assertTrue(all(len(record["sha256"]) == 64 for record in records))
        self.assertEqual(path, request)

        request.write_text(json.dumps({"source_records": [{"path": "a.npz"}]}),
                           encoding="utf-8")
        with self.assertRaises(SystemExit):
            preparemod.read_source_records(request)
        request.write_text(json.dumps({"world_seed": 12345, "source_records": pins}),
                           encoding="utf-8")
        with self.assertRaises(SystemExit):
            preparemod.read_source_records(request)
        request.write_text(json.dumps({"source_records": []}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            preparemod.read_source_records(request)

    def test_check_bundle_rejects_object_and_missing_arrays(self):
        bundle = build_fixture()
        preparemod.check_bundle(bundle)
        broken = dict(bundle)
        broken["arrays"] = dict(bundle["arrays"])
        broken["arrays"].pop("receiver")
        with self.assertRaises(SystemExit):
            preparemod.check_bundle(broken)
        objecty = dict(bundle)
        objecty["arrays"] = dict(bundle["arrays"])
        objecty["arrays"]["elevation_m"] = np.array([[{"x": 1}]], dtype=object)
        with self.assertRaises(SystemExit):
            preparemod.check_bundle(objecty)
        wrong = dict(bundle)
        wrong["schema"] = "something-else"
        with self.assertRaises(SystemExit):
            preparemod.check_bundle(wrong)

    def test_existing_output_target_is_refused_and_rejected_evidence_is_renamed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "evidence-b-p1"
            output.mkdir()
            output.joinpath("keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(SystemExit):
                preparemod.publish(root / "partial", output)
            self.assertTrue(output.is_dir())
            self.assertEqual(sorted(item.name for item in output.iterdir()), ["keep.txt"])

            partial = root / ".partial"
            partial.mkdir()
            partial.joinpath("manifest.json").write_text("{}", encoding="utf-8")
            fresh = root / "evidence-b-new"
            rejected = preparemod.stash_rejected(partial, fresh)
            self.assertEqual(rejected.name, "evidence-b-new.rejected")
            self.assertFalse(fresh.exists())
            self.assertTrue(rejected.is_dir())

            second = root / "partial2"
            second.mkdir()
            again = preparemod.stash_rejected(second, fresh)
            self.assertEqual(again.name, "evidence-b-new.rejected-2")
            self.assertFalse(fresh.exists())

    def test_prepare_refuses_a_target_that_already_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "taken"
            output.mkdir()
            arguments = type("Arguments", (), {
                "output": str(output), "plan": "p1", "origin_native_xz": None,
                "shape_zx": None, "plan_version": 1,
                "source_request": str(root / "missing.json"),
            })()
            with self.assertRaises(SystemExit):
                preparemod.prepare(arguments)
            self.assertEqual(sorted(item.name for item in output.iterdir()), [])
            self.assertEqual(sorted(item.name for item in root.iterdir()), ["taken"])

    def test_commit_never_overwrites_a_target_that_appears_after_the_check(self):
        """The commit is checked twice and never uses os.replace."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / ".partial"
            work.mkdir()
            work.joinpath("manifest.json").write_text("{}", encoding="utf-8")
            target = root / "evidence-b-p1-v1"
            # Simulate a racer: the target shows up after prepare() looked and before
            # publish() commits. publish() must refuse and change nothing.
            target.mkdir()
            target.joinpath("keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(SystemExit):
                preparemod.publish(work, target)
            self.assertEqual(sorted(item.name for item in target.iterdir()), ["keep.txt"])
            self.assertTrue(work.is_dir(), "the partial evidence must survive a refusal")

    def test_dangling_symlink_target_is_refused(self):
        """lexists, so a broken symlink at the output path counts as taken."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / ".partial"
            work.mkdir()
            target = root / "evidence-b-p1-v1"
            try:
                target.symlink_to(root / "does-not-exist")
            except (OSError, NotImplementedError) as error:      # pragma: no cover
                self.skipTest("symlinks unavailable on this platform: %s" % error)
            self.assertFalse(target.exists())
            self.assertTrue(os_path_lexists(target))
            with self.assertRaises(SystemExit):
                preparemod.publish(work, target)
            self.assertTrue(work.is_dir())

    def test_a_symlinked_output_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError) as error:      # pragma: no cover
                self.skipTest("symlinks unavailable on this platform: %s" % error)
            arguments = type("Arguments", (), {
                "output": str(link / "nested"), "plan": "p1", "origin_native_xz": None,
                "shape_zx": None, "plan_version": 1,
                "source_request": str(root / "missing.json"),
            })()
            with self.assertRaises(SystemExit):
                preparemod.prepare(arguments)
            self.assertEqual(sorted(item.name for item in real.iterdir()), [])

    def test_audit_hard_stop_is_sixty_seconds_and_monotonic(self):
        """The declared hard stop for one audit, and the clock it is measured with."""
        import inspect
        signature = inspect.signature(preparemod.run_audit)
        self.assertEqual(signature.parameters["timeout_s"].default,
                         preparemod.AUDIT_TIMEOUT_S)
        self.assertEqual(preparemod.AUDIT_TIMEOUT_S, 60.0)
        source = inspect.getsource(preparemod.run_audit)
        self.assertIn("time.monotonic()", source)
        self.assertNotIn("time.time()", source)
        self.assertNotIn("3600", source)

    def test_a_timed_out_audit_child_is_killed_and_reported(self):
        """A short timeout on a deliberately slow child: killed, not waited out."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "partial"
            work.mkdir()
            original = preparemod.ROOT
            fake = Path(directory) / "fake-tools"
            fake.mkdir()
            # A stand-in audit script that never finishes on its own.
            fake.joinpath("audit_world_domains.py").write_text(
                "import time\nwhile True: time.sleep(0.05)\n", encoding="utf-8")
            script_dir = Path(directory) / "tools"
            script_dir.mkdir()
            script_dir.joinpath("audit_world_domains.py").write_text(
                "import time\nwhile True: time.sleep(0.05)\n", encoding="utf-8")
            preparemod.ROOT = Path(directory)
            try:
                started = time.monotonic()
                code, report, record = preparemod.run_audit(work, timeout_s=0.6,
                                                            sample_s=0.05)
                elapsed = time.monotonic() - started
            finally:
                preparemod.ROOT = original
            self.assertTrue(record["timed_out"])
            self.assertEqual(record["clock"], "time.monotonic")
            self.assertLess(elapsed, 10.0, "the child must be killed, not waited out")
            self.assertIsNone(report)
            self.assertNotEqual(code, 0)
            self.assertFalse(record["rss_sample"]["is_limit"])

    def test_cli_requires_an_explicit_plan_version(self):
        with self.assertRaises(SystemExit):
            preparemod.main(["--mode", "prepare", "--source-request", "x.json",
                             "--output", "out", "--plan", "p1"])
        with self.assertRaises(SystemExit):
            preparemod.main(["--mode", "prepare", "--plan", "p1"])

    def test_list_plans_is_declared_and_side_effect_free(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(preparemod.main(["--mode", "list-plans"]), 0)
        declared = json.loads(buffer.getvalue())
        self.assertEqual(sorted(declared), ["p1", "p2", "p2-shifted"])


if __name__ == "__main__":
    unittest.main()
