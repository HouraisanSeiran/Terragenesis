"""Independent expectations for world domain candidates: hand-built terrain, slow references.

The terrain here is synthesised from explicit rules (a 5x5 cone bowl inside a one-cell
ridge ring, surrounded by a strictly outward-draining background), never loaded from a
saved TD page. Every expectation is either written out by hand (pit coordinates, the
49-cell basin, the crossing pairs) or produced by a deliberately slow per-cell
reference walk (:func:`reference_catchments`) that shares no code with the production
CSR/pointer-doubling implementation -- a green test here cannot be green because the
source was silently missing.
"""
import copy
import hashlib
import inspect
import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_world_domains import (
    ARRAY_NAMES, CANDIDATE_KEYS, MAX_SUPPORT_CELLS, SCHEMA, SOURCE_KIND_PINNED,
    SOURCE_KIND_SYNTHETIC, STATUS_CLOSED, STATUS_OPEN_UPSTREAM, STATUS_TRUNCATED,
    domain_candidates, mainstem_chain, member_sha256, native_to_metres,
    root_catchments, segment_donors, segment_retention, shared_divides, support_plan,
    validate_domain_candidates, world_keys)

SEED = 20261020
SPACING = 30.0


def candidates(support, source, *, source_kind=SOURCE_KIND_SYNTHETIC):
    """Direct calls in this file are synthetic fixtures unless a test says otherwise."""
    return domain_candidates(support, source=source, source_kind=source_kind)


def _pin(field):
    """A page record whose digest is the content digest of the synthetic field."""
    digest = hashlib.sha256(np.ascontiguousarray(field, np.float64).tobytes()).hexdigest()
    return [{"path": "synthetic://fixture-%s.npz" % digest[:8], "sha256": digest}]


def _support(field, *, origin=(0, 0), shape=None, plan_version=1, mask=None):
    shape = list(field.shape) if shape is None else list(shape)
    return support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=list(origin),
                        shape_zx=shape, source_records=_pin(field),
                        plan_version=plan_version)


def _source(field, support, *, origin=None, mask=None):
    """A loader-shaped source: unresolved cells carry NaN, exactly like the real loader.

    ``mask`` False anywhere means the elevation there is NaN. That is the convention
    ``load_native_window`` leaves, and the bundle has to round-trip it; passing a
    height under an unresolved mask is what the module explicitly refuses.
    """
    metadata = support["metadata"]
    resolved = (np.ones(field.shape, bool) if mask is None
                else np.ascontiguousarray(mask, bool))
    values = np.where(resolved, np.ascontiguousarray(field, np.float64), np.nan)
    return {
        "field": np.ascontiguousarray(values, np.float64),
        "resolved_mask": resolved,
        "origin_native_xz": list(metadata["origin_native_xz"] if origin is None else origin),
        "shape_zx": list(metadata["shape_zx"]),
        "world_seed": metadata["world_seed"],
        "spacing_m": metadata["spacing_m"],
    }


def _bundle(field, *, origin=(0, 0), plan_version=1, mask=None, source_kind=SOURCE_KIND_SYNTHETIC):
    support = _support(field, origin=origin, plan_version=plan_version, mask=mask)
    source = _source(field, support, origin=origin, mask=mask)
    return support, candidates(support, source=source, source_kind=source_kind)


# --------------------------------------------------------------------------- #
# hand-built terrain
# --------------------------------------------------------------------------- #
def two_basin_field(rows=17, columns=17, first=(4, 4), second=(12, 12), ring_m=400.0):
    """Two isolated closed basins: a cone bowl inside a one-cell ridge ring.

    Around ``first``/``second``: chebyshev radius 0..2 is ``100 + dr^2 + dc^2`` (a bowl
    whose only minimum is the centre); chebyshev radius exactly 3 is the ridge
    (``ring_m``); everything else is ``200 + 10 * distance_to_border + jitter``, which
    strictly decreases outward, so every background chain leaves through the border and
    the border is the support cut. The two basins are 49 cells each: the 5x5 bowl plus
    the 24 ring cells, all of which drain inward because the ring's inward slope
    (>= 292) beats its outward slope (<= 200).
    """
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    border = np.minimum(np.minimum(rr, cc), np.minimum(rows - 1 - rr, columns - 1 - cc))
    field = 200.0 + 10.0 * border + ((7 * rr + 3 * cc) % 5)
    for index, (centre_r, centre_c) in enumerate((first, second)):
        dr = np.abs(rr - centre_r)
        dc = np.abs(cc - centre_c)
        chebyshev = np.maximum(dr, dc)
        bowl = chebyshev <= 2
        field = np.where(bowl, 100.0 + (rr - centre_r) ** 2.0 + (cc - centre_c) ** 2.0,
                         field)
        field = np.where(chebyshev == 3, ring_m + index, field)
    return np.ascontiguousarray(field, np.float64)


def ramp_field(rows=17, columns=17):
    """A strictly north-west descending ramp: every cell flows NW, no interior sink."""
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    return np.ascontiguousarray(10.0 * (rr + cc), np.float64)


def symmetric_bowl(rows=9, columns=9, ring_m=400.0):
    """A closed bowl at the support centre whose interior is transpose-symmetric.

    The bowl is ``100 + dr^2 + dc^2`` inside chebyshev radius 2, a one-cell ridge at
    chebyshev radius 3, and a background at ``200 + 10 * distance_to_border`` beyond,
    which strictly decreases outward. The field is invariant under ``(row, column) ->
    (column, row)``, so the root's donors come in transposed pairs with *exactly* equal
    upstream cell counts: any tie here is genuine, not an artefact of digitising.
    """
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    border = np.minimum(np.minimum(rr, cc), np.minimum(rows - 1 - rr, columns - 1 - cc))
    field = 200.0 + 10.0 * border
    centre_r, centre_c = rows // 2, columns // 2
    dr = np.abs(rr - centre_r)
    dc = np.abs(cc - centre_c)
    chebyshev = np.maximum(dr, dc)
    bowl = chebyshev <= 2
    field = np.where(bowl, 100.0 + (rr - centre_r) ** 2.0 + (cc - centre_c) ** 2.0, field)
    field = np.where(chebyshev == 3, ring_m, field)
    return np.ascontiguousarray(field, np.float64)


def tie_field():
    """The transpose-symmetric bowl: its centre pair tie, and world order decides."""
    return symmetric_bowl()


# --------------------------------------------------------------------------- #
# an independent, deliberately slow reference
# --------------------------------------------------------------------------- #
def reference_catchments(receiver, valid, origin):
    """Per-cell chain walks: terminals, members, counts and mainstems, no CSR.

    One cell at a time, following ``receiver`` to its terminal, so the answer cannot
    share the production vectorisation. Used only to *confirm* structure that the test
    has already stated by hand.
    """
    rows, columns = receiver.shape
    flat = receiver.reshape(-1)
    ok = valid.reshape(-1)
    terminals = {}
    for cell in range(flat.size):
        if not ok[cell]:
            continue
        chain = []
        current = cell
        seen = set()
        while current >= 0:
            if current in seen:
                raise AssertionError("cycle")
            seen.add(current)
            chain.append(current)
            current = int(flat[current])
        terminals.setdefault(chain[-1], set()).update(chain)
    members = {}
    world = {}
    for root, cells in terminals.items():
        members[root] = cells
        world[root] = sorted((origin[0] + cell % columns, origin[1] + cell // columns)
                             for cell in cells)
    counts = {cell: 0 for cell in range(flat.size)}
    for cell in range(flat.size):
        if not ok[cell]:
            continue
        current = cell
        while current >= 0:
            counts[current] += 1
            current = int(flat[current])
    donors = {}
    for cell in range(flat.size):
        if ok[cell] and flat[cell] >= 0:
            donors.setdefault(int(flat[cell]), []).append(cell)
    mainstems = {}
    for root in members:
        core = [root]
        current = root
        while donors.get(current):
            best = max(counts[cell] for cell in donors[current])
            tied = [cell for cell in donors[current] if counts[cell] == best]
            coordinates = [(origin[0] + cell % columns, origin[1] + cell // columns)
                           for cell in tied]
            current = tied[coordinates.index(min(coordinates))]
            core.append(current)
        mainstems[root] = list(reversed(core))
    return {"roots": sorted(members), "members": members, "world": world,
            "counts": counts, "mainstems": mainstems}


# --------------------------------------------------------------------------- #
class SupportPlanTests(unittest.TestCase):
    def test_frozen_fields_and_no_arrays(self):
        field = two_basin_field()
        support = _support(field, origin=(-40, -70), plan_version=7)
        self.assertEqual(support["arrays"], {})
        metadata = support["metadata"]
        self.assertEqual(metadata["world_seed"], SEED)
        self.assertEqual(metadata["spacing_m"], SPACING)
        self.assertEqual(metadata["origin_native_xz"], [-40, -70])
        self.assertEqual(metadata["shape_zx"], [17, 17])
        self.assertEqual(metadata["support_cells"], 289)
        self.assertEqual(metadata["storage_representation"], "signed_int64_native_cells")
        self.assertEqual(metadata["plan_version"], 7)
        self.assertEqual(metadata["range_native"], {"x": [-40, -24], "z": [-70, -54]})
        self.assertEqual(len(metadata["source_records"]), 1)
        self.assertEqual(metadata["coordinate_serialization"]["order"], "sorted_by_(x,z)")
        self.assertEqual(metadata["coordinate_serialization"]["byte_order"], "little_endian")
        self.assertEqual(len(support["identity_sha256"]), 64)

    def test_pins_are_path_sorted_and_duplicates_refused(self):
        field = two_basin_field()
        first = {"path": "b.npz", "sha256": "1" * 64}
        second = {"path": "a.npz", "sha256": "2" * 64}
        support = support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                              shape_zx=[17, 17], source_records=[first, second],
                              plan_version=1)
        self.assertEqual([item["path"] for item in support["metadata"]["source_records"]],
                         ["a.npz", "b.npz"])
        swapped = support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                              shape_zx=[17, 17], source_records=[second, first],
                              plan_version=1)
        self.assertEqual(swapped["identity_sha256"], support["identity_sha256"])
        for records in ([first, dict(first)],
                        [first, {"path": "c.npz", "sha256": first["sha256"]}],
                        [{"path": "a.npz"}], [{"path": "a.npz", "sha256": "3" * 64,
                                                "extra": 1}], []):
            with self.subTest(records=records), self.assertRaises(ValueError):
                support_plan(world_seed=SEED, spacing_m=SPACING,
                             origin_native_xz=[0, 0], shape_zx=[17, 17],
                             source_records=records, plan_version=1)

    def test_seed_spacing_and_shape_refusals(self):
        pin = [{"path": "a.npz", "sha256": "0" * 64}]
        cases = [dict(world_seed=1234, spacing_m=SPACING, shape_zx=[17, 17]),
                 dict(world_seed=SEED, spacing_m=10.0, shape_zx=[17, 17]),
                 dict(world_seed=SEED, spacing_m=SPACING, shape_zx=[1, 17]),
                 dict(world_seed=SEED, spacing_m=SPACING, shape_zx=[17.0, 17]),
                 dict(world_seed=True, spacing_m=SPACING, shape_zx=[17, 17]),
                 dict(world_seed=SEED, spacing_m=SPACING, shape_zx=[17, 17],
                      plan_version=0)]
        for case in cases:
            arguments = {"origin_native_xz": [0, 0], "source_records": pin,
                         "plan_version": 1}
            arguments.update(case)
            with self.subTest(case=case), self.assertRaises(ValueError):
                support_plan(**arguments)

    def test_budget_is_refused_before_anything_else(self):
        """T11: the support budget refuses 385^2 + 1 and an inflated ceiling itself."""
        pin = [{"path": "a.npz", "sha256": "0" * 64}]
        with self.assertRaises(ValueError) as caught:
            support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                         shape_zx=[386, 386], source_records=pin, plan_version=1)
        self.assertIn("budget_exceeded", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                         shape_zx=[17, 17], source_records=pin, plan_version=1,
                         max_cells=MAX_SUPPORT_CELLS + 1)
        self.assertIn("budget_exceeded", str(caught.exception))
        with self.assertRaises(ValueError):
            support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                         shape_zx=[17, 17], source_records=pin, plan_version=1,
                         max_cells=100)
        exact = support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                            shape_zx=[385, 385], source_records=pin, plan_version=1)
        self.assertEqual(exact["metadata"]["support_cells"], MAX_SUPPORT_CELLS)

    def test_support_declaration_cannot_be_edited(self):
        field = two_basin_field()
        support = _support(field, plan_version=3)
        edited = copy.deepcopy(support)
        edited["metadata"]["plan_version"] = 4
        source = _source(field, support)
        with self.assertRaises(ValueError):
            domain_candidates(edited, source=source)
        widened = copy.deepcopy(support)
        widened["metadata"]["range_native"]["x"][1] += 1
        with self.assertRaises(ValueError):
            domain_candidates(widened, source=source)

    def test_no_render_window_parameter(self):
        """T12: no entry point accepts a render/window knob, so a view cannot shift it."""
        for function in (support_plan, domain_candidates, root_catchments,
                         mainstem_chain, shared_divides):
            names = set(inspect.signature(function).parameters)
            self.assertFalse({name for name in names
                              if "window" in name or "render" in name}, names)
        field = two_basin_field()
        support = _support(field)
        first = candidates(support, source=_source(field, support))
        second = candidates(support, source=_source(field, support))
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])


class CoordinateTests(unittest.TestCase):
    def test_world_keys_keep_signed_values(self):
        """T7: signed negative coordinates are ordinary; no packing enters identity."""
        keys = world_keys(np.array([[-5, 7], [3, -2]], np.int64))
        self.assertEqual(keys.tolist(), [[-5, 7], [3, -2]])
        with self.assertRaises(ValueError):
            world_keys(np.array([[1.0, 2.0]], np.float64))
        pair_digest = member_sha256(np.array([[-5, 7], [3, -2]], np.int64))
        packed = [(z + 2 ** 20) * 2 ** 22 + (x + 2 ** 20) for x, z in ((-5, 7), (3, -2))]
        packed_digest = hashlib.sha256(np.array(sorted(packed), np.int64).tobytes()).hexdigest()
        self.assertNotEqual(pair_digest, packed_digest)

    def test_member_hash_is_order_invariant_and_member_bound(self):
        """T6: permuting members cannot change the digest; changing one must."""
        members = np.array([[3, 4], [-1, 2], [3, 5], [0, 0]], np.int64)
        permuted = members[[2, 0, 3, 1]]
        self.assertEqual(member_sha256(members), member_sha256(permuted))
        reversed_order = members[::-1]
        self.assertEqual(member_sha256(members), member_sha256(reversed_order))
        changed = members.copy()
        changed[0] = [3, 6]
        self.assertNotEqual(member_sha256(members), member_sha256(changed))
        smaller = members[:3]
        self.assertNotEqual(member_sha256(members), member_sha256(smaller))

    def test_metre_conversion_refuses_precision_loss(self):
        """T8: a metre value beyond 2^53 is refused, and the shape sum cannot wrap."""
        self.assertEqual(native_to_metres([1, -2]), [30.0, -60.0])
        corners = native_to_metres([-10, -20], [4, 5])
        self.assertEqual(corners["origin_m"], [-300.0, -600.0])
        self.assertEqual(corners["max_m"], [-300.0 + 4 * 30.0, -600.0 + 3 * 30.0])
        with self.assertRaises(ValueError) as caught:
            native_to_metres([2 ** 60, 0])
        self.assertIn("coordinate_precision_exceeded", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            native_to_metres([2 ** 63 - 3, 0], [2, 4])
        self.assertIn("coordinate_precision_exceeded", str(caught.exception))
        with self.assertRaises(ValueError):
            native_to_metres([0, 0], [4, 5], spacing_m=float("inf"))


class TwoBasinTests(unittest.TestCase):
    """T1 and T3: two hand-computed closed basins, and the all-open refusal."""

    @classmethod
    def setUpClass(cls):
        cls.field = two_basin_field()
        cls.support, cls.bundle = _bundle(cls.field, origin=(-9, -9), plan_version=1)

    def test_exactly_two_closed_basins_contain_their_bowl_interiors(self):
        bundle = self.bundle
        self.assertEqual(bundle["schema"], SCHEMA)
        closed = [item for item in bundle["candidates"]
                  if item["status"] == STATUS_CLOSED]
        self.assertEqual(len(closed), 2)
        roots = sorted(tuple(item["root_world_xz"]) for item in closed)
        # origin (-9,-9): the pits sit at local (4,4) and (12,12).
        self.assertEqual(roots, [(-5, -5), (3, 3)])
        for item in closed:
            self.assertGreaterEqual(item["member_count"], 25)
            self.assertLessEqual(item["member_count"], 49)
            self.assertEqual(item["root_kind"], "retained")
            self.assertEqual(item["physical_endpoint_evidence"], "basin_pending")
            self.assertEqual(item["reason_codes"], ["complete"])
            self.assertTrue(item["structural_only"])
            self.assertEqual(item["evidence_level"], "structural_candidate")
        # The 5x5 interior drains inward; metric slopes divide the ridge ring.
        arrays = bundle["arrays"]
        owner = arrays["owner_index"]
        for index, item in enumerate(bundle["candidates"]):
            if item["status"] != STATUS_CLOSED:
                continue
            local = item["root_cell"]
            row, column = divmod(local, arrays["receiver"].shape[1])
            block = owner[row - 2:row + 3, column - 2:column + 3]
            expected = np.full((5, 5), index, np.int64)
            np.testing.assert_array_equal(block, expected)
            self.assertEqual(int((owner == index).sum()), item["member_count"])

    def test_membership_and_mainstem_match_the_slow_reference(self):
        arrays = self.bundle["arrays"]
        reference = reference_catchments(arrays["receiver"], arrays["resolved_mask"],
                                        (-9, -9))
        table = {}
        for index, item in enumerate(self.bundle["candidates"]):
            table[int(item["root_cell"])] = (index, item)
        self.assertEqual(sorted(reference["roots"]), sorted(table))
        for root, (index, item) in table.items():
            members = arrays["member_ptr"][index]
            high = arrays["member_ptr"][index + 1]
            cells = arrays["member_cells"][members:high]
            self.assertEqual(sorted(int(cell) for cell in cells),
                             sorted(reference["members"][root]))
            self.assertEqual(item["member_count"], len(reference["members"][root]))
            self.assertEqual(item["member_sha256"],
                             member_sha256(np.asarray(reference["world"][root], np.int64)))
            chain = [int(cell) for cell in
                     arrays["mainstem_cells"][arrays["mainstem_ptr"][index]:
                                             arrays["mainstem_ptr"][index + 1]]]
            self.assertEqual(chain, reference["mainstems"][root])
            self.assertEqual(chain[-1], root)

    def test_mainstem_steps_are_strict_graph_descent(self):
        arrays = self.bundle["arrays"]
        receiver = arrays["receiver"]
        elevation = arrays["elevation_m"]
        rows, columns = receiver.shape
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        mesh = grid_mesh(receiver.shape, x0_m=-9 * SPACING, z0_m=-9 * SPACING)
        for item in self.bundle["candidates"]:
            index = self.bundle["candidates"].index(item)
            cells = arrays["mainstem_cells"][arrays["mainstem_ptr"][index]:
                                             arrays["mainstem_ptr"][index + 1]]
            self.assertGreaterEqual(cells.size, 2)
            for here, following in zip(cells[:-1], cells[1:]):
                self.assertEqual(int(receiver.reshape(-1)[here]), int(following))
                self.assertIn(following, mesh.indices[mesh.indptr[here]:mesh.indptr[here + 1]])
                self.assertGreater(elevation.reshape(-1)[here],
                                   elevation.reshape(-1)[following])
            self.assertEqual(int(receiver.reshape(-1)[cells[-1]]), -1)
            self.assertEqual(item["mainstem_node_count"], int(cells.size))
            self.assertEqual(item["mainstem_edges"], int(cells.size) - 1)

    def test_all_open_result_is_not_a_pass(self):
        """T3: a ramp whose every root is cut at the border yields no closed candidate."""
        field = ramp_field()
        support, bundle = _bundle(field, origin=(0, 0))
        self.assertEqual(bundle["metadata"]["counts"]["closed_candidate_count"], 0)
        self.assertTrue(all(item["status"] != STATUS_CLOSED
                            for item in bundle["candidates"]))
        self.assertTrue(all(item["status"] in (STATUS_TRUNCATED, STATUS_OPEN_UPSTREAM)
                            for item in bundle["candidates"]))
        self.assertTrue(all("support_truncated" in item["reason_codes"]
                            for item in bundle["candidates"]))
        self.assertTrue(all(item["physical_endpoint_evidence"] == "none"
                            for item in bundle["candidates"]))
        # Not a pass: the bundle says so in metadata, and a support edge is not an outlet.
        self.assertEqual(bundle["metadata"]["final_domain"], "unsupported")
        self.assertNotIn("open_outflow", set(bundle["arrays"]["terminal_kind"].ravel().tolist()))
        validate_domain_candidates(bundle)

    def test_no_cell_is_left_unowned_and_inactive_cells_are_minus_one(self):
        arrays = self.bundle["arrays"]
        mask = arrays["resolved_mask"]
        owner = arrays["owner_index"]
        self.assertTrue(bool((owner[mask] >= 0).all()))
        self.assertTrue(bool((owner[~mask] == -1).all()))
        self.assertEqual(int(arrays["member_counts"].sum()), int(mask.sum()))
        self.assertEqual(int(arrays["member_ptr"][-1]), int(mask.sum()))


class TruncationTests(unittest.TestCase):
    """T2: a cut upstream must not report closed, by hole or by support edge."""

    def test_support_window_that_cuts_the_ring_is_not_closed(self):
        """Shrinking the support so it cuts the ring keeps the basin non-closed.

        The root itself is still an interior ``retained`` terminal, so the honest label
        is ``candidate_open_upstream`` (its declared upstream is incomplete), not
        ``candidate_truncated`` -- that word is reserved for a terminal the support edge
        actually cut. Either way it must not be ``candidate_closed``.
        """
        big = two_basin_field()
        window = np.ascontiguousarray(big[1:8, 1:8], np.float64)
        support, bundle = _bundle(window, origin=(1, 1))
        self.assertEqual(bundle["metadata"]["counts"]["closed_candidate_count"], 0)
        around = [item for item in bundle["candidates"]
                  if tuple(item["root_world_xz"]) == (4, 4)]
        self.assertEqual(len(around), 1)
        self.assertEqual(around[0]["root_kind"], "retained")
        self.assertEqual(around[0]["status"], STATUS_OPEN_UPSTREAM)
        self.assertIn("upstream_unknown", around[0]["reason_codes"])
        self.assertNotEqual(around[0]["status"], STATUS_CLOSED)
        validate_domain_candidates(bundle)

    def test_two_supports_agree_only_where_both_are_complete(self):
        """§9: a shared world root that is complete on both sides has one member set.

        Both windows contain the same closed basin with at least one cell of margin, so
        both candidates are ``candidate_closed``; then the member set and the mainstem
        must be *exactly* equal as world coordinates. Nothing is compared where a side
        is incomplete -- that case is listed separately instead of being averaged in.
        """
        field = two_basin_field(rows=21, columns=21, first=(10, 10), second=(18, 18))
        wide_support, wide = _bundle(field, origin=(0, 0))
        narrow = np.ascontiguousarray(field[3:18, 3:18], np.float64)
        narrow_support, close = _bundle(narrow, origin=(3, 3))
        self.assertEqual(wide["metadata"]["support"]["origin_native_xz"], [0, 0])
        self.assertEqual(close["metadata"]["support"]["origin_native_xz"], [3, 3])
        wide_roots = {tuple(item["root_world_xz"]): item for item in wide["candidates"]}
        close_roots = {tuple(item["root_world_xz"]): item for item in close["candidates"]}
        shared = [root for root, item in close_roots.items()
                  if item["status"] == STATUS_CLOSED and root in wide_roots
                  and wide_roots[root]["status"] == STATUS_CLOSED]
        self.assertEqual(shared, [(10, 10)])
        for root in shared:
            first, second = wide_roots[root], close_roots[root]
            self.assertEqual(first["member_count"], second["member_count"])
            self.assertEqual(first["member_sha256"], second["member_sha256"])
            self.assertEqual(first["mainstem_sha256"], second["mainstem_sha256"])
            self.assertEqual(first["mainstem_node_count"], second["mainstem_node_count"])
            self.assertEqual(first["mainstem_edges"], second["mainstem_edges"])
            self.assertEqual(first["root_kind"], second["root_kind"])
        # The other basin lies outside the narrow support: absent, not "equal".
        self.assertNotIn((18, 18), close_roots)

    def test_hole_makes_one_basin_open_upstream(self):
        field = two_basin_field()
        mask = np.ones(field.shape, bool)
        mask[1, 4] = False          # a ring cell of the first basin
        support, bundle = _bundle(field, origin=(0, 0), mask=mask)
        candidates = bundle["candidates"]
        closed = [item for item in candidates if item["status"] == STATUS_CLOSED]
        self.assertEqual(len(closed), 1)
        self.assertEqual(tuple(closed[0]["root_world_xz"]), (12, 12))
        opened = [item for item in candidates if tuple(item["root_world_xz"]) == (4, 4)]
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["status"], STATUS_OPEN_UPSTREAM)
        self.assertIn("upstream_unknown", opened[0]["reason_codes"])
        self.assertEqual(opened[0]["root_kind"], "retained")
        self.assertEqual(opened[0]["physical_endpoint_evidence"], "basin_pending")
        # The hole kept its own ownership refused, and the completeness array says why.
        arrays = bundle["arrays"]
        self.assertFalse(bool(arrays["complete_mask"][4, 4]))
        self.assertTrue(bool(arrays["complete_mask"][12, 12]))
        validate_domain_candidates(bundle)

    def test_unresolved_hole_is_not_an_outlet(self):
        """An unresolved cell is impassable: it is never a receiver and never a drain."""
        field = two_basin_field()
        mask = np.ones(field.shape, bool)
        mask[8, 8] = False
        support, bundle = _bundle(field, origin=(0, 0), mask=mask)
        arrays = bundle["arrays"]
        flat = arrays["receiver"].reshape(-1)
        self.assertEqual(int(flat[8 * 17 + 8]), -1)
        self.assertFalse(bool(arrays["resolved_mask"][8, 8]))
        self.assertNotEqual(str(arrays["terminal_kind"][8, 8]), "open_outflow")
        self.assertEqual(int(arrays["owner_index"][8, 8]), -1)
        self.assertEqual(int(arrays["upstream_cells"][8, 8]), 0)


class RootCatchmentTests(unittest.TestCase):
    def test_root_catchments_recompute_completeness_itself(self):
        field = two_basin_field()
        support = _support(field)
        bundle = candidates(support, source=_source(field, support))
        arrays = bundle["arrays"]
        result = root_catchments(receiver=arrays["receiver"],
                                 valid_mask=arrays["resolved_mask"],
                                 terminal_kind=arrays["terminal_kind"],
                                 upstream_unknown_mask=arrays["upstream_unknown_mask"],
                                 origin_native_xz=[0, 0])
        np.testing.assert_array_equal(result["complete_mask"], arrays["complete_mask"])
        np.testing.assert_array_equal(result["upstream_cells"], arrays["upstream_cells"])
        np.testing.assert_array_equal(result["catchment_of_cell"], arrays["owner_index"])
        self.assertEqual(sorted(result["root_cell"].tolist()),
                         sorted(arrays["root_cells"].tolist()))
        for key in ("root_cell", "catchment_of_cell", "member_count", "members_sha256",
                    "upstream_complete", "unknown_member_count", "root_kind"):
            self.assertIn(key, result)
        self.assertEqual(len(result["members_sha256"]), len(result["root_cell"]))

    def test_catchment_owner_is_world_sorted(self):
        """Roots are ordered by world (x,z), not by the local flat index."""
        field = two_basin_field()
        for origin in ((0, 0), (-9, -9), (1000, -2000)):
            support, bundle = _bundle(field, origin=origin)
            pairs = [tuple(item["root_world_xz"]) for item in bundle["candidates"]]
            self.assertEqual(pairs, sorted(pairs))
            self.assertEqual(len(set(pairs)), len(pairs))

    def test_caller_cannot_inject_a_receiver_or_complete_mask(self):
        field = two_basin_field()
        support = _support(field)
        source = _source(field, support)
        good = candidates(support, source=source)
        for key, value in (("receiver", good["arrays"]["receiver"]),
                           ("complete_mask", good["arrays"]["complete_mask"]),
                           ("owner", good["arrays"]["owner_index"]),
                           ("upstream_cells", good["arrays"]["upstream_cells"]),
                           ("terminal_kind", good["arrays"]["terminal_kind"])):
            hostile = dict(source)
            hostile[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidates(support, source=hostile)

    def test_inputs_are_never_modified(self):
        field = two_basin_field()
        mask = np.ones(field.shape, bool)
        mask[3, 4] = False
        field_before = field.copy()
        mask_before = mask.copy()
        support = _support(field, mask=mask)
        source = _source(field, support, mask=mask)
        support_before = copy.deepcopy(support)
        source_before = {key: (value.copy() if isinstance(value, np.ndarray) else value)
                         for key, value in source.items()}
        bundle = candidates(support, source=source)
        np.testing.assert_array_equal(field, field_before)
        np.testing.assert_array_equal(mask, mask_before)
        self.assertEqual(support, support_before)
        for key, value in source.items():
            if isinstance(value, np.ndarray):
                np.testing.assert_array_equal(value, source_before[key])
            else:
                self.assertEqual(value, source_before[key])
        stored = {name: bundle["arrays"][name].copy() for name in ARRAY_NAMES}
        validate_domain_candidates(bundle)
        for name in ARRAY_NAMES:
            np.testing.assert_array_equal(bundle["arrays"][name], stored[name])


class IllegalGraphTests(unittest.TestCase):
    """Illegal graphs are refused, not repaired: adjacency, cycles, bools, dtypes."""

    def _call(self, receiver, valid=None, kinds=None, origin=(0, 0)):
        # The receiver is passed through untouched: a dtype check that coerced first
        # would be unable to see the dtype it is meant to refuse.
        receiver = np.asarray(receiver)
        valid = (np.ones(receiver.shape, bool) if valid is None else valid)
        kinds = (np.where(receiver < 0, "retained", "interior").astype("U24")
                 if kinds is None else kinds)
        return root_catchments(receiver=receiver, valid_mask=valid, terminal_kind=kinds,
                               upstream_unknown_mask=np.zeros(receiver.shape, bool),
                               origin_native_xz=list(origin))

    def test_non_adjacent_and_self_edges_are_refused(self):
        """A long-range edge would pass the count check while describing no 30 m path."""
        receiver = np.full((4, 4), -1, np.int64)
        receiver[0, 0] = 15        # a jump to the far corner: not D8 adjacent
        with self.assertRaises(ValueError) as caught:
            self._call(receiver)
        self.assertIn("irregular graph", str(caught.exception))
        receiver = np.full((4, 4), -1, np.int64)
        receiver[1, 1] = 5         # two columns away
        with self.assertRaises(ValueError):
            self._call(receiver)
        receiver = np.full((4, 4), -1, np.int64)
        receiver[2, 2] = 10        # its own flat index
        with self.assertRaises(ValueError):
            self._call(receiver)

    def test_cycles_are_refused(self):
        receiver = np.full((2, 2), -1, np.int64)
        receiver[0, 0] = 1
        receiver[0, 1] = 4
        receiver[1, 0] = 0         # closes the loop 0 -> 1 -> 2 -> 0
        receiver[1, 1] = 2
        with self.assertRaises(ValueError):
            self._call(receiver)

    def test_wrong_dtypes_and_illegal_kinds_are_refused(self):
        good = np.array([[1, -1]], np.int64)
        for receiver in (np.array([[1.0, -1.0]], np.float64),
                         np.array([[1, -1]], np.int32),
                         np.array([[1, -1]], np.bool_)):
            with self.subTest(dtype=receiver.dtype), self.assertRaises(ValueError):
                self._call(receiver)
        with self.assertRaises(ValueError):
            self._call(good, valid=np.array([[1, 1]], np.int64))
        with self.assertRaises(ValueError):
            self._call(good, kinds=np.array([["interior", "ocean"]], "U24"))
        with self.assertRaises(ValueError):
            self._call(good, kinds=np.array([["interior", "retained"]], "O"))

    def test_bool_and_float_budgets_are_refused(self):
        receiver = np.array([[1, -1]], np.int64)
        kinds = np.array([["interior", "retained"]], "U24")
        for budget in (True, 0, -1, 1.5, MAX_SUPPORT_CELLS + 1):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                root_catchments(receiver=receiver, valid_mask=np.ones((1, 2), bool),
                                terminal_kind=kinds,
                                upstream_unknown_mask=np.zeros((1, 2), bool),
                                origin_native_xz=[0, 0], max_cells=budget)

    def test_non_finite_elevation_is_refused(self):
        receiver = np.array([[1, -1]], np.int64)
        counts = np.array([[1, 2]], np.int64)
        valid = np.ones((1, 2), bool)
        for value in (np.nan, np.inf, -np.inf):
            elevation = np.array([[1.0, value]], np.float64)
            with self.subTest(value=value), self.assertRaises(ValueError):
                mainstem_chain(receiver=receiver, valid_mask=valid, upstream_cells=counts,
                               root_cell=1, origin_native_xz=[0, 0],
                               elevation_m=elevation)

    def test_a_flat_or_ascending_mainstem_step_is_refused(self):
        receiver = np.array([[1, -1]], np.int64)
        counts = np.array([[1, 2]], np.int64)
        valid = np.ones((1, 2), bool)
        for elevation in ([[5.0, 5.0]], [[5.0, 6.0]]):
            with self.subTest(elevation=elevation), self.assertRaises(ValueError):
                mainstem_chain(receiver=receiver, valid_mask=valid, upstream_cells=counts,
                               root_cell=1, origin_native_xz=[0, 0],
                               elevation_m=np.array(elevation, np.float64))


class CandidateIdentityTests(unittest.TestCase):
    """A candidate id is world-anchored logical identity, not a support-local number."""

    def test_an_unrelated_root_in_a_wider_support_keeps_the_same_id(self):
        """The negative case the main branch asked for.

        The narrow support contains one closed basin; the wide support contains the
        same basin *plus* a second, unrelated one. The shared candidate is complete on
        both sides with the same members, so its ``candidate_id`` must be identical --
        the extra root shifts its local root number and its support origin/shape, and
        none of that may leak into the id.
        """
        field = two_basin_field(rows=21, columns=21, first=(10, 10), second=(18, 18))
        narrow = np.ascontiguousarray(field[3:18, 3:18], np.float64)
        narrow_support, close = _bundle(narrow, origin=(3, 3))
        wide_support, wide = _bundle(field, origin=(0, 0))
        close_roots = {tuple(item["root_world_xz"]): item for item in close["candidates"]}
        wide_roots = {tuple(item["root_world_xz"]): item for item in wide["candidates"]}
        shared = (10, 10)
        self.assertEqual(close_roots[shared]["status"], STATUS_CLOSED)
        self.assertEqual(wide_roots[shared]["status"], STATUS_CLOSED)
        self.assertEqual(close_roots[shared]["member_sha256"],
                         wide_roots[shared]["member_sha256"])
        self.assertEqual(close_roots[shared]["candidate_id"],
                         wide_roots[shared]["candidate_id"])
        # ...while the support-local numbering really did change.
        self.assertNotEqual(close_roots[shared]["root_index"],
                            wide_roots[shared]["root_index"])
        self.assertNotEqual(close_roots[shared]["root_cell"],
                            wide_roots[shared]["root_cell"])
        self.assertNotEqual(close["support"]["identity_sha256"],
                            wide["support"]["identity_sha256"])
        # The second basin exists only in the wide support, and its id is its own.
        self.assertNotIn((18, 18), close_roots)
        self.assertNotEqual(wide_roots[(18, 18)]["candidate_id"],
                            wide_roots[shared]["candidate_id"])
        # Ids are unique within a bundle, and none of them is a positional string.
        identifiers = [item["candidate_id"] for item in wide["candidates"]]
        self.assertEqual(len(set(identifiers)), len(identifiers))
        for value in identifiers:
            self.assertTrue(value.startswith("wdc-"))
            self.assertEqual(len(value), 4 + 64)      # a sha256, not a counter

    def test_seed_plan_version_members_and_completeness_change_the_id(self):
        field = two_basin_field()
        base = _bundle(field, plan_version=1)[1]
        other_plan = _bundle(field, plan_version=2)[1]
        base_ids = [item["candidate_id"] for item in base["candidates"]]
        self.assertFalse(set(base_ids)
                         & {item["candidate_id"] for item in other_plan["candidates"]})
        # A different member set (a hole inside the first basin)
        # is a different object; the untouched second basin legitimately keeps its id,
        # because nothing about that world object changed.
        mask = np.ones(field.shape, bool)
        mask[3, 4] = False
        holed = _bundle(field, mask=mask)[1]
        holed_ids = {tuple(item["root_world_xz"]): item for item in holed["candidates"]}
        touched = holed_ids[(4, 4)]
        self.assertNotEqual(touched["status"], STATUS_CLOSED)     # explicitly incomplete
        for item in base["candidates"]:
            root = tuple(item["root_world_xz"])
            if root not in holed_ids:
                continue
            if root == (4, 4):
                self.assertNotEqual(item["member_sha256"],
                                    holed_ids[root]["member_sha256"])
                self.assertNotEqual(item["candidate_id"], holed_ids[root]["candidate_id"])
            elif root == (12, 12):
                self.assertEqual(item["member_sha256"],
                                 holed_ids[root]["member_sha256"])
                self.assertEqual(item["candidate_id"], holed_ids[root]["candidate_id"])
        # Incomplete candidates stay incomplete objects with their own ids.
        opened = [item for item in holed["candidates"]
                  if item["status"] != STATUS_CLOSED]
        self.assertTrue(opened)
        for item in opened:
            self.assertTrue(item["candidate_id"].startswith("wdc-"))
        # A different world seed cannot even build a support, so it cannot reuse an id.
        with self.assertRaises(ValueError):
            support_plan(world_seed=SEED + 1, spacing_m=SPACING, origin_native_xz=[0, 0],
                         shape_zx=[17, 17], source_records=_pin(field), plan_version=1)

    def test_support_origin_does_not_enter_the_id_but_members_do(self):
        """Same local grid, two origins: the ids differ only because members move."""
        field = two_basin_field()
        one = _bundle(field, origin=(0, 0))[1]
        two = _bundle(field, origin=(5000, -7000))[1]
        first = {tuple(item["root_world_xz"]): item for item in one["candidates"]}
        second = {tuple(item["root_world_xz"]): item for item in two["candidates"]}
        self.assertFalse(set(first) & set(second))
        self.assertFalse({item["candidate_id"] for item in one["candidates"]}
                         & {item["candidate_id"] for item in two["candidates"]})
        # Interior pits remain accounts, while absolute-position graph edges can
        # change the outward background drainage under a world translation.
        for bundle in (one, two):
            closed = {item["root_cell"] for item in bundle["candidates"]
                      if item["status"] == STATUS_CLOSED}
            self.assertEqual(closed, {4 * 17 + 4, 12 * 17 + 12})


class PartialCoverageTests(unittest.TestCase):
    """A legal partially-covered window must survive build -> validate with its NaN."""

    def _window(self):
        field = two_basin_field()
        mask = np.ones(field.shape, bool)
        mask[0, :] = False        # a whole unresolved band at the support edge
        mask[7, 9] = False        # plus one interior hole
        mask[16, 16] = False
        return field, mask

    def test_partial_coverage_round_trips_with_nan(self):
        field, mask = self._window()
        support, bundle = _bundle(field, origin=(-3, 4), mask=mask)
        elevations = bundle["arrays"]["elevation_m"]
        self.assertTrue(bool(np.isnan(elevations[~mask]).all()))
        self.assertFalse(bool(np.isnan(elevations[mask]).any()))
        self.assertFalse(bool(bundle["arrays"]["resolved_mask"][~mask].any()))
        self.assertEqual(bundle["metadata"]["counts"]["inactive_cells"],
                         int((~mask).sum()))
        # The real round trip: the validator re-derives everything from that NaN array.
        validate_domain_candidates(bundle)
        again = validate_domain_candidates(
            {**bundle, "arrays": {name: array.copy()
                                   for name, array in bundle["arrays"].items()}})
        self.assertIsNone(again)

    def test_filling_a_hole_is_refused(self):
        """An unresolved cell may not be presented as terrain (height or zero)."""
        field, mask = self._window()
        support = _support(field, mask=mask)
        source = _source(field, support, mask=mask)
        for filler in (0.0, 250.0, -1.0):
            hostile = dict(source)
            values = source["field"].copy()
            values[~mask] = filler
            hostile["field"] = values
            with self.subTest(filler=filler), self.assertRaises(ValueError) as caught:
                candidates(support, source=hostile)
            self.assertIn("unprepared", str(caught.exception))

    def test_resolved_nan_is_refused(self):
        field, mask = self._window()
        support = _support(field, mask=mask)
        source = _source(field, support, mask=mask)
        broken = dict(source)
        values = source["field"].copy()
        row, column = 5, 5
        self.assertTrue(bool(mask[row, column]))
        values[row, column] = np.nan
        broken["field"] = values
        with self.assertRaises(ValueError):
            candidates(support, source=broken)

    def test_validator_refuses_a_resealed_filled_hole(self):
        """A tampered NaN pattern cannot be hidden by resealing the digests."""
        field, mask = self._window()
        support, bundle = _bundle(field, origin=(0, 0), mask=mask)
        hostile = copy.deepcopy(bundle)
        hostile["arrays"]["elevation_m"][~mask] = 0.0
        hostile["metadata"]["field_mask_sha256"] = _resign({
            "arrays": {"elevation_m": hostile["arrays"]["elevation_m"],
                       "resolved_mask": hostile["arrays"]["resolved_mask"]},
            "metadata": {"origin_native_xz": [0, 0],
                         "shape_zx": list(mask.shape),
                         "world_seed": SEED, "spacing_m": SPACING}})
        hostile["identity_sha256"] = _resign(hostile)
        with self.assertRaises(ValueError):
            validate_domain_candidates(hostile)

    def test_unresolved_cells_stay_non_members(self):
        field, mask = self._window()
        support, bundle = _bundle(field, origin=(0, 0), mask=mask)
        arrays = bundle["arrays"]
        self.assertTrue(bool((arrays["owner_index"][~mask] == -1).all()))
        self.assertTrue(bool((arrays["upstream_cells"][~mask] == 0).all()))
        self.assertTrue(bool((arrays["receiver"][~mask] == -1).all()))
        self.assertTrue(bool((arrays["complete_mask"][~mask] == False).all()))  # noqa: E712
        self.assertTrue(bool(np.isnan(arrays["elevation_m"][~mask]).all()))
        self.assertEqual(int(arrays["member_counts"].sum()), int(mask.sum()))


class MainstemCountTests(unittest.TestCase):
    """Nodes and edges are reported separately, so no downstream budget is off by one."""

    def test_single_cell_and_multi_cell_chains_report_both_counts(self):
        field = two_basin_field()
        support, bundle = _bundle(field, origin=(0, 0))
        arrays = bundle["arrays"]
        for item in bundle["candidates"]:
            low = int(arrays["mainstem_ptr"][item["root_index"]])
            high = int(arrays["mainstem_ptr"][item["root_index"] + 1])
            nodes = high - low
            self.assertEqual(item["mainstem_node_count"], nodes)
            self.assertEqual(item["mainstem_edges"], nodes - 1)
            self.assertGreaterEqual(nodes, 1)
        result = mainstem_chain(receiver=arrays["receiver"],
                                valid_mask=arrays["resolved_mask"],
                                upstream_cells=arrays["upstream_cells"],
                                root_cell=int(arrays["root_cells"][0]),
                                origin_native_xz=[0, 0],
                                elevation_m=arrays["elevation_m"])
        self.assertEqual(result["node_count"],
                         int(result["chain_cells_ordered"].size))
        self.assertEqual(result["edges"], result["node_count"] - 1)


class SegmentTests(unittest.TestCase):
    """T4 and T5: cross-segment counting, kept single-cell segments, no L-1."""

    def test_multi_cell_source_reports_zero(self):
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones(receiver.shape, bool)
        reach = np.array([[0, 0, 0, 1]], np.int64)
        donors = segment_donors(receiver, valid, reach)
        np.testing.assert_array_equal(donors, [0, 1])
        self.assertEqual(int(donors[0]), 0)      # not L - 1 == 2
        retention = segment_retention(receiver, valid, reach)
        self.assertEqual(retention["keep"].tolist(), [True, False])
        self.assertEqual(retention["sentinel"].tolist(), [False, True])
        self.assertEqual(retention["reason_codes"].tolist(), ["chain", "terminal_sentinel"])

    def test_single_cell_source_and_confluence_are_kept(self):
        receiver = np.array([[3, 3, 3, 4, -1]], np.int64)
        valid = np.ones(receiver.shape, bool)
        reach = np.array([[0, 1, 2, 3, 4]], np.int64)
        donors = segment_donors(receiver, valid, reach)
        np.testing.assert_array_equal(donors, [0, 0, 0, 3, 1])
        retention = segment_retention(receiver, valid, reach)
        self.assertEqual(retention["keep"].tolist(), [True, True, True, True, False])
        self.assertEqual(retention["reason_codes"].tolist(),
                         ["single_cell_source", "single_cell_source",
                          "single_cell_source", "single_cell_confluence",
                          "terminal_sentinel"])

    def test_segment_donor_assertion_fires_on_a_branching_segment(self):
        receiver = np.array([[4, 4, 4, 3, -1]], np.int64)
        valid = np.ones(receiver.shape, bool)
        reach = np.array([[1, 1, 1, 1, 0]], np.int64)
        with self.assertRaises(RuntimeError):
            segment_donors(receiver, valid, reach)

    def test_segment_inputs_are_rejected(self):
        receiver = np.array([[1, -1]], np.int64)
        valid = np.ones(receiver.shape, bool)
        for reach in (np.array([[0.0, 1.0]], np.float64),
                      np.array([[0, 2]], np.int64),
                      np.array([[0, -1]], np.int64)):
            with self.subTest(reach=reach), self.assertRaises(ValueError):
                segment_donors(receiver, valid, reach)


class MainstemTests(unittest.TestCase):
    def test_tie_breaks_on_world_xz_not_row_order(self):
        """T10: a *genuine* area tie where world order and row order disagree.

        Grid ``3x3``; root is flat 4 ``=(row 1, col 1)``. Its two donors tie at two
        upstream cells each:

        =======  =========  ==============  ============
        cell     flat       world (x, z)    row-major
        =======  =========  ==============  ============
        (1, 0)   3          (0, 1)          later
        (0, 1)   1          (1, 0)          earlier
        =======  =========  ==============  ============

        World ``(x, z)`` lexicographic keeps ``(0, 1)``; row-major flat order would keep
        ``(1, 0)``. The chain is the same on a re-run, so the rule is replayable.
        """
        # A tiny 3x3 graph whose only confluence is a genuine two-cell tie.
        #   flat 0 (x0,z0) -> flat 1 (x1,z0) -\
        #   flat 6 (x0,z2) -> flat 3 (x0,z1) --> flat 4 (x1,z1) = root
        receiver = np.array([[1, 4, -1],
                             [4, -1, -1],
                             [3, -1, -1]], np.int64)
        valid = np.ones((3, 3), bool)
        upstream = np.array([[1, 2, 1],
                             [2, 5, 1],
                             [1, 1, 1]], np.int64)
        elevation = np.array([[13.0, 11.0, 30.0],
                              [9.0, 0.0, 30.0],
                              [12.0, 30.0, 30.0]], np.float64)
        west = 3        # (row 1, col 0) -> world (x=0, z=1), chosen by (x,z)
        north = 1       # (row 0, col 1) -> world (x=1, z=0), chosen by row-major order
        self.assertEqual(int(upstream.reshape(-1)[west]), int(upstream.reshape(-1)[north]))
        self.assertGreater(west, north)   # row-major flat order would take `north`...
        result = mainstem_chain(receiver=receiver, valid_mask=valid,
                                upstream_cells=upstream, root_cell=4,
                                origin_native_xz=[0, 0], elevation_m=elevation)
        self.assertEqual(result["chain_cells_ordered"].tolist(), [6, west, 4])
        self.assertEqual(result["chain_world_xz"].tolist(), [[0, 2], [0, 1], [1, 1]])
        self.assertEqual(result["node_count"], 3)
        self.assertEqual(result["edges"], 2)      # 3 chain cells carry 2 edges
        # The chain digest keeps the *path order*: it must not be the set digest.
        self.assertNotEqual(result["chain_sha256"], member_sha256(result["chain_world_xz"]))
        reversed_chain = np.ascontiguousarray(result["chain_world_xz"][::-1])
        self.assertEqual(member_sha256(result["chain_world_xz"]), member_sha256(reversed_chain))
        self.assertNotEqual(result["chain_sha256"],
                            hashlib.sha256(reversed_chain.tobytes()).hexdigest())
        repeat = mainstem_chain(receiver=receiver, valid_mask=valid,
                                upstream_cells=upstream, root_cell=4,
                                origin_native_xz=[0, 0], elevation_m=elevation)
        self.assertEqual(repeat["chain_sha256"], result["chain_sha256"])

    def test_pipeline_mainstem_is_strict_and_world_ordered(self):
        """The same rule over a derived graph: every step is an actual graph edge."""
        field = symmetric_bowl()
        support, bundle = _bundle(field, origin=(0, 0))
        arrays = bundle["arrays"]
        rows, columns = arrays["receiver"].shape
        root = 4 * columns + 4
        result = mainstem_chain(receiver=arrays["receiver"],
                                valid_mask=arrays["resolved_mask"],
                                upstream_cells=arrays["upstream_cells"],
                                root_cell=root, origin_native_xz=[0, 0],
                                elevation_m=arrays["elevation_m"])
        chain = result["chain_cells_ordered"].tolist()
        self.assertEqual(chain[-1], root)
        flat_receiver = arrays["receiver"].reshape(-1)
        flat_elevation = arrays["elevation_m"].reshape(-1)
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        mesh = grid_mesh(arrays["receiver"].shape)
        for here, following in zip(chain[:-1], chain[1:]):
            self.assertEqual(int(flat_receiver[here]), following)
            self.assertGreater(float(flat_elevation[here]), float(flat_elevation[following]))
            self.assertIn(following, mesh.indices[mesh.indptr[here]:mesh.indptr[here + 1]])
        self.assertEqual(int(result["chain_world_xz"][-1, 0]), 4)
        self.assertEqual(int(result["chain_world_xz"][-1, 1]), 4)

    def test_forged_upstream_counts_are_refused(self):
        field = symmetric_bowl()
        support, bundle = _bundle(field, origin=(0, 0))
        arrays = bundle["arrays"]
        root = 36
        forged = arrays["upstream_cells"].copy()
        forged[4, 3] = 1                      # claim the west donor carries almost nothing
        with self.assertRaises(ValueError):
            mainstem_chain(receiver=arrays["receiver"], valid_mask=arrays["resolved_mask"],
                           upstream_cells=forged, root_cell=root,
                           origin_native_xz=[0, 0], elevation_m=arrays["elevation_m"])

    def test_non_terminal_root_and_out_of_range_roots_are_refused(self):
        field = symmetric_bowl()
        support, bundle = _bundle(field, origin=(0, 0))
        arrays = bundle["arrays"]
        fresh = arrays["receiver"].reshape(-1)
        interior = int(np.flatnonzero(fresh >= 0)[0])
        for root in (interior, -1, fresh.size, fresh.size + 5):
            with self.subTest(root=root), self.assertRaises(ValueError):
                mainstem_chain(receiver=arrays["receiver"],
                               valid_mask=arrays["resolved_mask"],
                               upstream_cells=arrays["upstream_cells"], root_cell=root,
                               origin_native_xz=[0, 0], elevation_m=arrays["elevation_m"])


class SharedDivideTests(unittest.TestCase):
    """T9: canonical symmetric pairs, and a cross-owner D8 edge is refused."""

    def setUp(self):
        field = two_basin_field()
        self.support = _support(field)
        self.bundle = candidates(self.support, source=_source(field, self.support))

    def test_pairs_are_symmetric_under_owner_relabelling(self):
        owner = np.array([[0, 0, 1, 1],
                          [0, 0, 1, 1],
                          [2, 2, 3, 3],
                          [2, 2, 3, 3]], np.int64)
        receiver = np.full((4, 4), -1, np.int64)   # every cell is its own terminal at D4
        valid = np.ones((4, 4), bool)
        support = support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                              shape_zx=[4, 4],
                              source_records=[{"path": "a.npz", "sha256": "0" * 64}],
                              plan_version=1)
        first = shared_divides(owner=owner, receiver=receiver, valid_mask=valid,
                              support=support)
        swapped = np.where(owner == 0, 1, np.where(owner == 1, 0, owner))
        second = shared_divides(owner=swapped, receiver=receiver, valid_mask=valid,
                                support=support)
        np.testing.assert_array_equal(first["pairs_world"], second["pairs_world"])
        self.assertEqual(first["info"]["pair_count"], 8)
        self.assertEqual(first["info"]["reason_codes"], [])
        for row in first["pairs_world"].tolist():
            self.assertLess((row[0], row[1]), (row[2], row[3]))

    def test_cross_owner_drain_is_reported_and_refused(self):
        owner = np.array([[0, 1], [0, 0]], np.int64)
        receiver = np.array([[-1, -1], [-1, -1]], np.int64)
        receiver[0, 0] = 1
        valid = np.ones((2, 2), bool)
        support = support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                              shape_zx=[2, 2],
                              source_records=[{"path": "a.npz", "sha256": "0" * 64}],
                              plan_version=1)
        result = shared_divides(owner=owner, receiver=receiver, valid_mask=valid,
                               support=support)
        self.assertEqual(result["info"]["reason_codes"], ["cross_domain_drain"])
        self.assertEqual(result["cross_domain_drain_local"].tolist(), [[0, 1]])
        self.assertEqual(len(result["identity_sha256"]), 64)

    def test_owner_gaps_and_overlaps_are_refused(self):
        valid = np.ones((2, 2), bool)
        receiver = np.full((2, 2), -1, np.int64)
        support = support_plan(world_seed=SEED, spacing_m=SPACING, origin_native_xz=[0, 0],
                              shape_zx=[2, 2],
                              source_records=[{"path": "a.npz", "sha256": "0" * 64}],
                              plan_version=1)
        with self.assertRaises(ValueError) as caught:
            shared_divides(owner=np.array([[0, 0], [0, -1]], np.int64), receiver=receiver,
                           valid_mask=valid, support=support)
        self.assertIn("owner_gap", str(caught.exception))
        inactive = valid.copy()
        inactive[0, 0] = False
        with self.assertRaises(ValueError) as caught:
            shared_divides(owner=np.array([[0, 0], [0, 0]], np.int64), receiver=receiver,
                           valid_mask=inactive, support=support)
        self.assertIn("owner_overlap", str(caught.exception))

    def test_bundle_reports_no_cross_drain_and_validation_refuses_tampering(self):
        self.assertEqual(self.bundle["metadata"]["counts"]["cross_domain_drain_pair_count"], 0)
        self.assertEqual(int(self.bundle["arrays"]["shared_face_cells"].shape[0]),
                         self.bundle["metadata"]["counts"]["shared_face_pair_count"])
        self.assertGreater(self.bundle["metadata"]["counts"]["shared_face_pair_count"], 0)
        tampered = copy.deepcopy(self.bundle)
        owner = tampered["arrays"]["owner_index"]
        receiver = tampered["arrays"]["receiver"].reshape(-1)
        for cell in range(receiver.size):
            if receiver[cell] >= 0 and owner.reshape(-1)[cell] != owner.reshape(-1)[receiver[cell]]:
                break
        else:
            first = int(np.flatnonzero(receiver >= 0)[0])
            owner.reshape(-1)[first] = (owner.reshape(-1)[first] + 1) % int(owner.max() + 1)
        tampered["identity_sha256"] = _resign(tampered)
        with self.assertRaises(ValueError):
            validate_domain_candidates(tampered)


class SourceBindingTests(unittest.TestCase):
    def test_origin_shape_seed_and_pin_mismatches_are_refused(self):
        field = two_basin_field()
        support = _support(field, origin=(0, 0))
        source = _source(field, support)
        candidates(support, source=source)
        for key, value in (("origin_native_xz", [1, 0]),
                           ("shape_zx", [17, 16]),
                           ("world_seed", SEED + 1),
                           ("spacing_m", 10.0)):
            hostile = dict(source)
            hostile[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidates(support, source=hostile)

    def test_pinned_source_must_match_the_frozen_pins(self):
        field = two_basin_field()
        support = _support(field)
        source = _source(field, support)
        source["source_records"] = [{"path": "other.npz", "sha256": "9" * 64}]
        source["assembly_digest"] = "8" * 64
        with self.assertRaises(ValueError) as caught:
            candidates(support, source=source, source_kind=SOURCE_KIND_PINNED)
        self.assertIn("pin_mismatch", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            candidates(support, source=_source(field, support),
                              source_kind=SOURCE_KIND_PINNED)
        self.assertIn("unprepared", str(caught.exception))

    def test_pinned_source_binds_pins_and_assembly_digest(self):
        field = two_basin_field()
        support = _support(field)
        source = _source(field, support)
        source["source_records"] = [
            {"page_key": "p00", "path": support["metadata"]["source_records"][0]["path"],
             "sha256": support["metadata"]["source_records"][0]["sha256"],
             "native_origin_xz": [0, 0], "shape_zx": [17, 17],
             "schema": "td-native-page-v1", "world_seed": SEED, "spacing_m": SPACING}]
        source["assembly_digest"] = "7" * 64
        bundle = candidates(support, source=source, source_kind=SOURCE_KIND_PINNED)
        self.assertEqual(bundle["metadata"]["source_kind"], SOURCE_KIND_PINNED)
        self.assertEqual(bundle["metadata"]["source_verification"],
                         "caller pinned loader; checksums not signature")
        self.assertEqual(bundle["metadata"]["source"]["assembly_digest"], "7" * 64)
        self.assertEqual(bundle["metadata"]["source"]["source_record_count"], 1)
        validate_domain_candidates(bundle)

    def test_synthetic_source_is_labelled_and_never_claims_td(self):
        field = two_basin_field()
        support = _support(field)
        bundle = candidates(support, source=_source(field, support),
                                   source_kind=SOURCE_KIND_SYNTHETIC)
        metadata = bundle["metadata"]
        self.assertEqual(metadata["source_kind"], SOURCE_KIND_SYNTHETIC)
        self.assertIn("synthetic fixture", metadata["source_verification"])
        self.assertIsNone(metadata["source"]["assembly_digest"])
        self.assertEqual(metadata["source"]["source_records"], [])
        self.assertEqual(len(metadata["source"]["field_mask_sha256"]), 64)
        with self.assertRaises(ValueError):
            candidates(support, source=_source(field, support), source_kind="td_like")

    def test_field_content_is_bound_into_the_identity(self):
        field = two_basin_field()
        support = _support(field)
        first = candidates(support, source=_source(field, support))
        changed = field.copy()
        changed[4, 4] = field[4, 4] - 1.0
        second = candidates(support, source=_source(changed, support))
        self.assertNotEqual(first["metadata"]["field_mask_sha256"],
                            second["metadata"]["field_mask_sha256"])
        self.assertNotEqual(first["identity_sha256"], second["identity_sha256"])


class IdentityTests(unittest.TestCase):
    def test_plan_version_and_members_change_the_identity(self):
        field = two_basin_field()
        one = _bundle(field, plan_version=1)[1]
        two = _bundle(field, plan_version=2)[1]
        self.assertNotEqual(one["support"]["identity_sha256"],
                            two["support"]["identity_sha256"])
        self.assertNotEqual(one["identity_sha256"], two["identity_sha256"])
        self.assertEqual(one["arrays"]["member_cells"].tolist(),
                         two["arrays"]["member_cells"].tolist())
        self.assertEqual([item["member_sha256"] for item in one["candidates"]],
                         [item["member_sha256"] for item in two["candidates"]])

    def test_member_hash_ignores_the_storage_order_of_the_grid(self):
        """Root hashes are world-sorted: a grid relabelled by a shift cannot reorder them."""
        field = two_basin_field()
        base = _bundle(field, origin=(0, 0))[1]
        moved = _bundle(field, origin=(-500, 250))[1]
        self.assertNotEqual(base["identity_sha256"], moved["identity_sha256"])
        for bundle in (base, moved):
            origin = bundle["metadata"]["support"]["origin_native_xz"]
            arrays = bundle["arrays"]
            for index, item in enumerate(bundle["candidates"]):
                cells = arrays["member_cells"][arrays["member_ptr"][index]:
                                                 arrays["member_ptr"][index + 1]]
                points = np.column_stack((cells % 17 + origin[0], cells // 17 + origin[1]))
                self.assertEqual(member_sha256(points), item["member_sha256"])
                self.assertEqual(member_sha256(points[::-1]), item["member_sha256"])

    def test_candidate_keys_are_exactly_the_declared_ones(self):
        field = two_basin_field()
        bundle = _bundle(field)[1]
        for item in bundle["candidates"]:
            self.assertEqual(set(item), set(CANDIDATE_KEYS))
            self.assertEqual(len(item["member_sha256"]), 64)
            self.assertEqual(len(item["mainstem_sha256"]), 64)
        self.assertEqual(set(bundle["arrays"]), set(ARRAY_NAMES))
        self.assertEqual(bundle["arrays"]["elevation_m"].dtype, np.float64)
        self.assertEqual(bundle["arrays"]["resolved_mask"].dtype, np.bool_)
        self.assertEqual(bundle["arrays"]["receiver"].dtype, np.int64)
        self.assertEqual(bundle["arrays"]["owner_index"].dtype, np.int64)
        self.assertEqual(bundle["arrays"]["terminal_kind"].dtype.kind, "U")
        self.assertEqual(bundle["arrays"]["upstream_cells"].dtype, np.int64)
        self.assertEqual(bundle["arrays"]["root_cells"].dtype, np.int64)
        self.assertEqual(bundle["arrays"]["root_complete"].dtype, np.bool_)
        self.assertEqual(bundle["arrays"]["member_ptr"].shape[0],
                         bundle["arrays"]["root_cells"].size + 1)
        self.assertEqual(bundle["arrays"]["mainstem_ptr"].shape[0],
                         bundle["arrays"]["root_cells"].size + 1)
        self.assertEqual(bundle["arrays"]["shared_face_cells"].shape[1], 2)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        field = two_basin_field()
        mask = np.ones(field.shape, bool)
        mask[1, 4] = False
        self.support, self.bundle = _bundle(field, origin=(-9, -9), mask=mask)
        validate_domain_candidates(self.bundle)

    def test_resealed_derived_array_is_refused(self):
        for name in ("complete_mask", "owner_index", "upstream_cells", "receiver",
                     "member_cells", "mainstem_cells", "root_complete"):
            hostile = copy.deepcopy(self.bundle)
            array = hostile["arrays"][name]
            if array.dtype == np.bool_:
                flat = array.reshape(-1)
                flat[0] = not bool(flat[0])
            else:
                array.reshape(-1)[0] = array.reshape(-1)[0] + 1
            hostile["identity_sha256"] = _resign(hostile)
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_domain_candidates(hostile)

    def test_resealed_status_and_membership_are_refused(self):
        hostile = copy.deepcopy(self.bundle)
        opened = [item for item in hostile["candidates"]
                  if item["status"] != STATUS_CLOSED][0]
        opened["status"] = STATUS_CLOSED
        opened["reason_codes"] = ["complete"]
        hostile["identity_sha256"] = _resign(hostile)
        with self.assertRaises(ValueError):
            validate_domain_candidates(hostile)
        hostile2 = copy.deepcopy(self.bundle)
        closed = [item for item in hostile2["candidates"]
                  if item["status"] == STATUS_CLOSED][0]
        closed["member_count"] += 1
        hostile2["identity_sha256"] = _resign(hostile2)
        with self.assertRaises(ValueError):
            validate_domain_candidates(hostile2)

    def test_fake_completeness_is_refused(self):
        """A package claiming every member complete while the mask says otherwise."""
        hostile = copy.deepcopy(self.bundle)
        arrays = hostile["arrays"]
        arrays["complete_mask"][:] = True
        arrays["root_complete"][:] = True
        for item in hostile["candidates"]:
            item["status"] = STATUS_CLOSED
            item["reason_codes"] = ["complete"]
        hostile["metadata"]["counts"]["closed_candidate_count"] = len(hostile["candidates"])
        hostile["metadata"]["counts"]["open_upstream_candidate_count"] = 0
        hostile["metadata"]["counts"]["truncated_candidate_count"] = 0
        hostile["identity_sha256"] = _resign(hostile)
        with self.assertRaises(ValueError):
            validate_domain_candidates(hostile)

    def test_structure_of_the_bundle_is_checked(self):
        for key in sorted(self.bundle):
            missing = {name: value for name, value in self.bundle.items() if name != key}
            with self.subTest(missing=key), self.assertRaises(ValueError):
                validate_domain_candidates(missing)
        for schema in ("other-schema", None):
            hostile = copy.deepcopy(self.bundle)
            hostile["metadata"]["schema"] = schema
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                validate_domain_candidates(hostile)

    def test_metadata_declares_the_scope_limits(self):
        metadata = self.bundle["metadata"]
        self.assertEqual(metadata["final_domain"], "unsupported")
        self.assertEqual(metadata["evidence_level"], "structural_candidate")
        self.assertEqual(metadata["algorithm"]["no_second_routing"], True)
        self.assertEqual(metadata["algorithm"]["no_second_accumulation"], True)
        self.assertEqual(metadata["algorithm"]["no_water_budget"], True)
        self.assertEqual(len(metadata["algorithm_dependency_sha256"]), 6)
        for digest in metadata["algorithm_dependency_sha256"].values():
            self.assertEqual(len(digest), 64)
        self.assertEqual(metadata["budget"]["max_support_cells"], MAX_SUPPORT_CELLS)
        self.assertEqual(metadata["source_verification"],
                         "synthetic fixture; no TD page pin and no checksum claim")
        self.assertEqual(metadata["counts"]["root_count"],
                         len(self.bundle["candidates"]))
        for item in self.bundle["candidates"]:
            self.assertIn(item["physical_endpoint_evidence"], ("basin_pending", "none"))
            for reason in item["reason_codes"]:
                self.assertIn(reason, metadata["reason_vocabulary"])


def _resign(bundle):
    """Recompute the bundle digest after tampering, to prove digests are not the gate."""
    from terrain_pipeline.common_infra import identity
    return identity(bundle["arrays"], bundle["metadata"])


if __name__ == "__main__":
    unittest.main()
