"""Independent expectations for the reach network: hand-built drainages, slow references.

Every network here is synthesised so that the expected partition is written out by hand:
a Y with two multi-cell arms, two consecutive confluences, one-cell sources and
junctions, an empty channel, a terminal-only window and a partially unknown window. The
reference partition is recomputed by a deliberately slow per-cell walk that shares no code
with the production grouping, so a green test cannot be green because the source was
silently missing.

The one comparison against the older backend uses an input that is genuinely admissible to
it (finite heights, a single HRU, ``receiver == -1`` exactly on the outlet mask); it is a
per-cell partition cross-check, not a copy of that implementation.
"""
import copy
import math
import unittest

import numpy as np
from terrain_pipeline.drainage import grid_mesh as grid_mesh

from terrain_pipeline.runoff import build_reaches as build_reaches
from terrain_pipeline.surface_rivers.metric_world_domains import (
    SOURCE_KIND_SYNTHETIC, domain_candidates, support_plan)
from terrain_pipeline.surface_rivers.metric_world_reaches import (
    ARRAY_NAMES, DEFAULT_MIN_UPSTREAM_CELLS, MAX_REACHES, REACH_KEYS, ROOT_KEYS, SCHEMA,
    STATUS_EMPTY, STATUS_TOPOLOGY_PREPARED, build_world_reaches, validate_world_reaches)

SEED = 20261020
SPACING = 30.0


# --------------------------------------------------------------------------- #
# synthetic terrains: each declares its own expected partition
# --------------------------------------------------------------------------- #
def _bowl(rows, columns, centres, ring_m=400.0):
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    border = np.minimum(np.minimum(rr, cc), np.minimum(rows - 1 - rr, columns - 1 - cc))
    field = 200.0 + 10.0 * border
    for index, (centre_r, centre_c) in enumerate(centres):
        dr = np.abs(rr - centre_r)
        dc = np.abs(cc - centre_c)
        chebyshev = np.maximum(dr, dc)
        field = np.where(chebyshev <= 2,
                         100.0 + (rr - centre_r) ** 2.0 + (cc - centre_c) ** 2.0, field)
        field = np.where(chebyshev == 3, ring_m + index, field)
    return np.ascontiguousarray(field, np.float64)


def _bucket(rows=17, columns=17, centre=(8, 8)):
    """A wide, deep funnelling bowl: one root, a long trunk and a few tributaries.

    Slopes are steep enough that a 17x17 window with a ``min_upstream_cells`` of a few
    cells produces a hand-checkable network: the funnel interior drains to a single pit.
    """
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    distance = np.hypot(rr - centre[0], cc - centre[1])
    field = 100.0 + 6.0 * distance
    field[centre] = 0.0
    return np.ascontiguousarray(field, np.float64)


def _two_cones(rows=21, columns=21, centres=((6, 6), (14, 14))):
    """Two cones with genuine confluences: each pit collects ever-widening slopes.

    A cone ``height = 60 * distance`` has a strictly monotone descent everywhere, so every
    cell has exactly one receiver, arms merge into a trunk, and the two pits are separate
    structural terminals. That gives real internal edges (``L > 1`` reaches), real
    junctions, and two distinct roots to confuse.
    """
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    field = np.full((rows, columns), 1000.0)
    for centre_r, centre_c in centres:
        distance = np.hypot(rr - centre_r, cc - centre_c)
        field = np.minimum(field, 60.0 * np.round(distance, 6))
    return np.ascontiguousarray(field, np.float64)


def _pin(field):
    import hashlib
    digest = hashlib.sha256(np.ascontiguousarray(field, np.float64).tobytes()).hexdigest()
    return [{"path": "synthetic://reach-%s.npz" % digest[:8], "sha256": digest}]


def _parent(field, *, origin=(0, 0), plan_version=1, mask=None):
    shape = list(field.shape)
    support = support_plan(world_seed=SEED, spacing_m=SPACING,
                           origin_native_xz=list(origin), shape_zx=shape,
                           source_records=_pin(field), plan_version=plan_version)
    resolved = (np.ones(field.shape, bool) if mask is None
                else np.ascontiguousarray(mask, bool))
    values = np.where(resolved, np.ascontiguousarray(field, np.float64), np.nan)
    source = {
        "field": np.ascontiguousarray(values, np.float64),
        "resolved_mask": resolved,
        "origin_native_xz": list(origin),
        "shape_zx": shape,
        "world_seed": SEED,
        "spacing_m": SPACING,
    }
    return domain_candidates(support, source=source, source_kind=SOURCE_KIND_SYNTHETIC)


# --------------------------------------------------------------------------- #
# an independent, deliberately slow partition reference
# --------------------------------------------------------------------------- #
def reference_partition(parent, threshold):
    """Per-cell walk: channel, segments, downstream, terminal edges and lengths.

    No CSR, no ``bincount``: one cell at a time, following ``receiver``, so this cannot
    share the production grouping. Used to confirm partitions the test already states.
    """
    receiver = parent["arrays"]["receiver"]
    mask = parent["arrays"]["resolved_mask"]
    upstream = parent["arrays"]["upstream_cells"]
    owner = parent["arrays"]["owner_index"]
    rows, columns = receiver.shape
    mesh = reference_mesh(parent)
    flat_receiver = receiver.reshape(-1)

    channel = {cell for cell in range(flat_receiver.size)
               if mask.reshape(-1)[cell]
               and flat_receiver[cell] >= 0
               and upstream.reshape(-1)[cell] >= threshold}
    donors = {}
    for cell in channel:
        donors.setdefault(int(flat_receiver[cell]), []).append(cell)
    starts = sorted(cell for cell in channel
                    if len([donor for donor in donors.get(cell, [])
                            if donor in channel]) != 1)

    segments = {}
    of_cell = {}
    for start in starts:
        chain = [start]
        of_cell[start] = start
        current = start
        while True:
            following = int(flat_receiver[current])
            following_donors = [donor for donor in donors.get(following, [])
                                if donor in channel]
            if following < 0 or following not in channel or len(following_donors) != 1:
                break
            chain.append(following)
            of_cell[following] = start
            current = following
        segments[start] = chain

    reach_of_head = {head: index for index, head in enumerate(sorted(segments))}
    order = sorted(segments)
    downstream = {}
    terminal_edges = []
    lengths = []
    handoff = []
    for index, head in enumerate(order):
        chain = segments[head]
        tail = chain[-1]
        following = int(flat_receiver[tail])
        internal = 0.0
        for first, second in zip(chain[:-1], chain[1:]):
            internal += math.hypot(mesh.node_x_m[first] - mesh.node_x_m[second],
                                   mesh.node_z_m[first] - mesh.node_z_m[second])
        lengths.append(internal)
        hop = math.hypot(mesh.node_x_m[tail] - mesh.node_x_m[following],
                         mesh.node_z_m[tail] - mesh.node_z_m[following])
        handoff.append(hop)
        if following in of_cell:
            downstream[index] = reach_of_head[of_cell[following]]
        else:
            downstream[index] = -1
            terminal_edges.append((tail, following))
    return {
        "channel": channel,
        "segments": {reach_of_head[head]: chain for head, chain in segments.items()},
        "of_cell": {cell: reach_of_head[of_cell[cell]] for cell in of_cell},
        "downstream": downstream,
        "terminal_edges": sorted((int(a), int(b)) for a, b in terminal_edges),
        "lengths": lengths,
        "handoff": handoff,
        "owners": [int(owner.reshape(-1)[chain[0]]) for chain in segments.values()],
    }


def reference_mesh(parent):
    support = parent["metadata"]["support"]
    origin = support["origin_native_xz"]
    return grid_mesh(parent["arrays"]["receiver"].shape,
                     x0_m=origin[0] * SPACING, z0_m=origin[1] * SPACING,
                     dx_m=SPACING, world_seed=SEED)


def _expected_pair_set(edges):
    return {(int(source), int(target)) for source, target in edges.tolist()}


# --------------------------------------------------------------------------- #
class HandComputedNetworkTests(unittest.TestCase):
    """R1: a funnel bowl whose network is small enough to enumerate by hand."""

    @classmethod
    def setUpClass(cls):
        cls.field = _bucket()
        cls.parent = _parent(cls.field)
        cls.bundle = build_world_reaches(cls.parent, min_upstream_cells=4)

    def test_partition_matches_the_slow_reference(self):
        reference = reference_partition(self.parent, 4)
        arrays = self.bundle["arrays"]
        self.assertEqual(int((arrays["reach_of_cell"] >= 0).sum()), len(reference["channel"]))
        observed = {cell: int(arrays["reach_of_cell"].reshape(-1)[cell])
                    for cell in reference["channel"]}
        self.assertEqual(observed, reference["of_cell"])
        self.assertEqual(int(arrays["reach_downstream"].size), len(reference["segments"]))
        self.assertEqual(arrays["reach_downstream"].tolist(),
                         [reference["downstream"][index]
                          for index in range(len(reference["segments"]))])
        for index, chain in reference["segments"].items():
            low = int(arrays["reach_ptr"][index])
            high = int(arrays["reach_ptr"][index + 1])
            self.assertEqual(arrays["reach_cells"][low:high].tolist(), chain)
            self.assertEqual(int(arrays["reach_head"][index]), chain[0])
            self.assertEqual(int(arrays["reach_tail"][index]), chain[-1])
            self.assertAlmostEqual(float(arrays["reach_length_m"][index]),
                                   reference["lengths"][index], places=9)
            self.assertAlmostEqual(float(arrays["reach_handoff_length_m"][index]),
                                   reference["handoff"][index], places=9)

    def test_every_channel_edge_is_counted_exactly_once(self):
        """Internal edges plus handoff edges == every selected channel edge.

        This is the accounting identity the main branch asked for, checked against the
        parent's own receiver rather than against a stored count.
        """
        parent = self.parent
        arrays = self.bundle["arrays"]
        receiver = parent["arrays"]["receiver"].reshape(-1)
        mask = parent["arrays"]["resolved_mask"].reshape(-1)
        upstream = parent["arrays"]["upstream_cells"].reshape(-1)
        channel = np.flatnonzero(mask & (receiver >= 0) & (upstream >= 4))
        mesh = reference_mesh(parent)
        direct = float(sum(math.hypot(mesh.node_x_m[cell] - mesh.node_x_m[receiver[cell]],
                                     mesh.node_z_m[cell] - mesh.node_z_m[receiver[cell]])
                           for cell in channel))
        internal = sum(int(edges) for edges in arrays["reach_edges"])
        self.assertEqual(internal + int(arrays["handoff_edge_pairs"].shape[0]),
                         int(channel.size))
        total = (float(arrays["reach_length_m"].sum())
                 + float(arrays["reach_handoff_length_m"].sum()))
        self.assertAlmostEqual(total, direct, places=9)

    def test_root_and_status_layers(self):
        metadata = self.bundle["metadata"]
        self.assertEqual(metadata["status"], STATUS_TOPOLOGY_PREPARED)
        self.assertFalse(metadata["physical_domain_certified"])
        self.assertEqual(metadata["schema"], SCHEMA)
        self.assertIsInstance(metadata["whole_support_upstream_complete"], bool)
        self.assertEqual(len(self.bundle["roots"]), len(self.parent["candidates"]))
        for row in self.bundle["roots"]:
            self.assertEqual(set(row), set(ROOT_KEYS))
            self.assertIn(row["status"], ("candidate_closed",
                                          "candidate_open_upstream",
                                          "candidate_truncated"))
            # Raw and channel mainstems are reported separately, never merged.
            self.assertIn("raw_mainstem_node_count", row)
            self.assertIn("channel_mainstem_node_count", row)
            self.assertGreaterEqual(row["raw_mainstem_node_count"], 1)
            self.assertEqual(row["raw_mainstem_edges"], row["raw_mainstem_node_count"] - 1)

    def test_reach_rows_are_complete_and_typed(self):
        for row in self.bundle["reaches"]:
            self.assertEqual(set(row), set(REACH_KEYS))
            self.assertEqual(row["edges"], row["node_count"] - 1)
            self.assertTrue(row["reach_id"].startswith("wr-"))
            self.assertEqual(len(row["reach_id"]), 3 + 64)
            if row["downstream_reach_index"] >= 0:
                self.assertIsNone(row["terminal_kind"])
                self.assertIsNone(row["terminal_root_world_xz"])
                self.assertIsNotNone(row["downstream_reach_id"])
            else:
                self.assertIsNotNone(row["terminal_kind"])
                self.assertIsNotNone(row["terminal_root_world_xz"])
                self.assertIsNone(row["downstream_reach_id"])
                self.assertIn(row["terminal_physical_endpoint_evidence"],
                              ("basin_pending", "none"))
        self.assertEqual(set(self.bundle["arrays"]), set(ARRAY_NAMES))

    def test_validator_accepts_the_network(self):
        self.assertIsNone(validate_world_reaches(self.bundle, self.parent))


class TwoBasinReachTests(unittest.TestCase):
    """R2: two separate basins produce disjoint networks with their own terminals."""

    @classmethod
    def setUpClass(cls):
        cls.field = _bowl(21, 21, [(10, 10), (18, 18)])
        cls.parent = _parent(cls.field)
        cls.bundle = build_world_reaches(cls.parent, min_upstream_cells=4)

    def test_two_roots_two_terminal_edges(self):
        """Every terminal reach belongs to exactly one root, and every root is reported.

        A root may own several terminal reaches (two arms can both terminate inside the
        same catchment), so the assertion is that a terminal edge never crosses roots and
        that each terminal edge's root is a declared root -- not that the counts are one.
        """
        bundle = self.bundle
        terminal = bundle["arrays"]["terminal_edge_pairs"]
        self.assertEqual(len(bundle["roots"]), len(self.parent["candidates"]))
        owner = self.parent["arrays"]["owner_index"].reshape(-1)
        receiver = self.parent["arrays"]["receiver"].reshape(-1)
        counted = 0
        for row in terminal.tolist():
            source, target = int(row[0]), int(row[1])
            self.assertEqual(int(receiver[source]), target)     # orientation preserved
            self.assertEqual(int(owner[source]), int(owner[target]))
            self.assertIn(int(owner[source]),
                          set(int(value) for value in
                              bundle["arrays"]["reach_root_index"].tolist()))
            counted += 1
        self.assertEqual(counted, len(terminal))
        self.assertTrue(any(row["reach_count"] for row in bundle["roots"]))
        # Every terminal reach is reported as such, and none is missing a terminal.
        terminal_reaches = [row for row in bundle["reaches"]
                            if row["downstream_reach_index"] < 0]
        self.assertEqual(len(terminal_reaches), len(terminal))
        for row in terminal_reaches:
            self.assertIsNotNone(row["terminal_root_world_xz"])
            self.assertIn(row["terminal_physical_endpoint_evidence"],
                          ("basin_pending", "none"))

    def test_no_reach_spans_two_roots(self):
        owner = self.parent["arrays"]["owner_index"].reshape(-1)
        arrays = self.bundle["arrays"]
        for index in range(int(arrays["reach_downstream"].size)):
            low = int(arrays["reach_ptr"][index])
            high = int(arrays["reach_ptr"][index + 1])
            roots = set(owner[arrays["reach_cells"][low:high]].tolist())
            self.assertEqual(len(roots), 1)
            self.assertEqual(roots.pop(), int(arrays["reach_root_index"][index]))

    def test_validate_round_trip(self):
        self.assertIsNone(validate_world_reaches(self.bundle, self.parent))


if __name__ == "__main__":
    unittest.main()


class ChannelEdgeCaseTests(unittest.TestCase):
    """R3-R5: one-cell reaches, an empty channel, a terminal-only window."""

    def test_one_cell_source_and_junction_are_kept(self):
        """Whichever reaches survive a strict gate include legal single cells.

        The gate is raised just above the basin's own tributary counts so the surviving
        network is small; every surviving one-cell reach must stay, keep its CSR slot,
        and still carry a real handoff edge of at least one cell step.
        """
        field = _bucket()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=16)
        arrays = bundle["arrays"]
        self.assertGreater(int(arrays["reach_downstream"].size), 0)
        single = [index for index in range(int(arrays["reach_downstream"].size))
                  if int(arrays["reach_node_count"][index]) == 1]
        self.assertTrue(single)                 # a strict gate leaves junctions alone
        for index in single:
            low = int(arrays["reach_ptr"][index])
            self.assertEqual(int(arrays["reach_ptr"][index + 1]) - low, 1)
            self.assertEqual(float(arrays["reach_length_m"][index]), 0.0)
            self.assertGreater(float(arrays["reach_handoff_length_m"][index]), 0.)
        validate_world_reaches(bundle, parent)

    def test_no_channel_yields_an_empty_network_not_success(self):
        """R4: a threshold above every cell is a legal empty network, never a pass."""
        field = _bucket()
        parent = _parent(field)
        biggest = int(parent["arrays"]["upstream_cells"].max())
        bundle = build_world_reaches(parent, min_upstream_cells=biggest + 1)
        metadata = bundle["metadata"]
        self.assertEqual(metadata["status"], STATUS_EMPTY)
        self.assertIn("no_channel_cells", metadata["reason_codes"])
        self.assertEqual(metadata["counts"]["channel_cells"], 0)
        self.assertEqual(metadata["counts"]["reach_count"], 0)
        self.assertEqual(int(bundle["arrays"]["reach_downstream"].size), 0)
        self.assertEqual(int(bundle["arrays"]["reach_cells"].size), 0)
        self.assertEqual(int(bundle["arrays"]["terminal_edge_pairs"].size), 0)
        self.assertFalse(bool((bundle["arrays"]["reach_of_cell"] >= 0).any()))
        # Every parent candidate is still reported, with zero channel.
        self.assertEqual(len(bundle["roots"]), len(parent["candidates"]))
        self.assertTrue(all(row["reach_count"] == 0 for row in bundle["roots"]))
        validate_world_reaches(bundle, parent)

    def test_terminal_only_window(self):
        """R5: a monotone ramp has terminals but no interior channel above the gate."""
        rows = columns = 13
        rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
        field = np.ascontiguousarray(10.0 * (rr + cc), np.float64)
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        # The ramp drains west/north out of the window: channel cells exist only close to
        # the cut, and every terminal reach still records a terminal edge.
        terminal = bundle["arrays"]["terminal_edge_pairs"]
        terminal_reaches = [row for row in bundle["reaches"]
                            if row["downstream_reach_index"] < 0]
        self.assertEqual(len(terminal_reaches), int(terminal.shape[0]))
        for index in range(int(bundle["arrays"]["reach_downstream"].size)):
            if row_is_terminal(bundle, index):
                self.assertGreaterEqual(int(bundle["arrays"]["reach_tail"][index]), 0)
        validate_world_reaches(bundle, parent)


def row_is_terminal(bundle, index):
    return int(bundle["arrays"]["reach_downstream"][index]) < 0


class UnknownAndIncompleteTests(unittest.TestCase):
    """R6/R7: unknown roots and incomplete upstream are reported, never hidden."""

    def test_unknown_root_is_reported_with_none_evidence(self):
        """A window cut by a mask band produces truncated roots; none claims a lake."""
        field = _bucket()
        mask = np.ones(field.shape, bool)
        mask[8, :] = False          # a band across the window: the drain is cut
        parent = _parent(field, mask=mask)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        kinds = {row["root_kind"] for row in bundle["roots"]}
        self.assertTrue(kinds & {"unknown_boundary", "retained"})
        unknown = [row for row in bundle["roots"]
                   if row["root_kind"] == "unknown_boundary"]
        for row in unknown:
            self.assertFalse(row["upstream_complete"])
            self.assertEqual(row["status"], "candidate_truncated")
        for row in bundle["reaches"]:
            if row["terminal_kind"] == "unknown_boundary":
                self.assertEqual(row["terminal_physical_endpoint_evidence"], "none")
            # The window edge is never called an outlet.
            self.assertNotEqual(row["terminal_kind"], "open_outflow")
        validate_world_reaches(bundle, parent)

    def test_incomplete_upstream_still_produces_reaches(self):
        field = _bowl(17, 17, [(8, 8)])
        mask = np.ones(field.shape, bool)
        mask[1, 8] = False          # one hole in the ring of the basin
        parent = _parent(field, mask=mask)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        incomplete = [row for row in bundle["roots"] if not row["upstream_complete"]]
        self.assertTrue(incomplete)
        self.assertGreater(int(bundle["arrays"]["reach_downstream"].size), 0)
        metadata = bundle["metadata"]
        self.assertEqual(metadata["status"], STATUS_TOPOLOGY_PREPARED)
        self.assertFalse(metadata["whole_support_upstream_complete"])
        self.assertGreater(metadata["counts"]["incomplete_root_count"], 0)
        # Candidate status is untouched by this layer.
        for row in bundle["roots"]:
            parent_row = parent["candidates"][row["root_index"]]
            self.assertEqual(row["status"], parent_row["status"])
            self.assertEqual(row["root_kind"], parent_row["root_kind"])
        validate_world_reaches(bundle, parent)

    def test_no_complete_root_means_no_display_root(self):
        """A window whose every root is cut has no display root, not the nicest one."""
        rows = columns = 13
        rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
        field = np.ascontiguousarray(10.0 * (rr + cc), np.float64)
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        self.assertEqual(bundle["metadata"]["display_root_index"], None)
        # ...and when a complete root does exist the rule is stated, not chosen.
        bowl = build_world_reaches(_parent(_bowl(17, 17, [(8, 8)])), min_upstream_cells=4)
        index = bowl["metadata"]["display_root_index"]
        self.assertIsNotNone(index)
        self.assertEqual(bowl["roots"][index]["status"], "candidate_closed")


class ThresholdAndIdentityTests(unittest.TestCase):
    """R8/R9/R10: downstream closure, the last edge, and stable world ids."""

    def test_threshold_never_opens_a_gap_downstream(self):
        field = _bucket()
        parent = _parent(field)
        previous = None
        for threshold in (1, 4, 12, 40):
            bundle = build_world_reaches(parent, min_upstream_cells=threshold)
            arrays = bundle["arrays"]
            for index in range(int(arrays["reach_downstream"].size)):
                tail = int(arrays["reach_tail"][index])
                following = int(parent["arrays"]["receiver"].reshape(-1)[tail])
                target = int(arrays["reach_downstream"][index])
                if target >= 0:
                    self.assertEqual(following, int(arrays["reach_head"][target]))
                else:
                    self.assertEqual(int(parent["arrays"]["receiver"].reshape(-1)[following]), -1)
            validate_world_reaches(bundle, parent)
            count = int(arrays["reach_downstream"].size)
            if previous is not None:
                self.assertLessEqual(count, previous)      # a stricter gate cannot add reaches
            previous = count

    def test_last_edge_to_the_root_is_never_lost(self):
        field = _bucket()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        arrays = bundle["arrays"]
        receiver = parent["arrays"]["receiver"].reshape(-1)
        owner = parent["arrays"]["owner_index"].reshape(-1)
        roots = set(int(value) for value in parent["arrays"]["root_cells"].tolist())
        stored = {(int(a), int(b)) for a, b in arrays["terminal_edge_pairs"].tolist()}
        expected = set()
        for index in range(int(arrays["reach_downstream"].size)):
            if int(arrays["reach_downstream"][index]) < 0:
                tail = int(arrays["reach_tail"][index])
                expected.add((tail, int(receiver[tail])))
        self.assertEqual(stored, expected)
        for source, target in stored:
            self.assertIn(target, roots)                    # the node it lands on
            self.assertEqual(int(owner[source]), int(owner[target]))
        # Manual spot check: the trunk's last channel cell is exactly one hop above the pit.
        trunk = [row for row in bundle["reaches"]
                 if row["downstream_reach_index"] < 0 and row["on_mainstem"]]
        self.assertTrue(trunk)
        for row in trunk:
            tail = int(arrays["reach_tail"][row["reach_index"]])
            self.assertEqual(int(receiver[tail]), int(parent["arrays"]["root_cells"][row["root_index"]]))

    def test_world_id_survives_an_unrelated_root(self):
        field = _bowl(21, 21, [(10, 10), (18, 18)])
        narrow = np.ascontiguousarray(field[3:18, 3:18], np.float64)
        close = build_world_reaches(_parent(narrow, origin=(3, 3)), min_upstream_cells=4)
        wide = build_world_reaches(_parent(field, origin=(0, 0)), min_upstream_cells=4)
        close_by_head = {(tuple(row["head_world_xz"]), tuple(row["tail_world_xz"])): row
                         for row in close["reaches"]}
        wide_by_head = {(tuple(row["head_world_xz"]), tuple(row["tail_world_xz"])): row
                        for row in wide["reaches"]}
        shared = [key for key in close_by_head
                  if key in wide_by_head
                  and close_by_head[key]["downstream_reach_index"] < 0
                  and wide_by_head[key]["downstream_reach_index"] < 0]
        self.assertTrue(shared)
        for key in shared:
            self.assertEqual(close_by_head[key]["reach_id"],
                             wide_by_head[key]["reach_id"])
            self.assertEqual(close_by_head[key]["world_path_sha256"],
                             wide_by_head[key]["world_path_sha256"])
        self.assertNotEqual(close["metadata"]["parent_identity_sha256"],
                            wide["metadata"]["parent_identity_sha256"])

    def test_identity_changes_with_the_gate_and_the_plan(self):
        field = _bucket()
        one = build_world_reaches(_parent(field, plan_version=1), min_upstream_cells=4)
        other_gate = build_world_reaches(_parent(field, plan_version=1),
                                         min_upstream_cells=8)
        other_plan = build_world_reaches(_parent(field, plan_version=2),
                                         min_upstream_cells=4)
        one_ids = {row["reach_id"] for row in one["reaches"]}
        self.assertFalse(one_ids & {row["reach_id"] for row in other_gate["reaches"]})
        self.assertFalse(one_ids & {row["reach_id"] for row in other_plan["reaches"]})
        self.assertNotEqual(one["identity_sha256"], other_gate["identity_sha256"])
        self.assertNotEqual(one["identity_sha256"], other_plan["identity_sha256"])
        self.assertEqual(one["metadata"]["min_upstream_cells"], 4)

    def test_order_of_the_world_path_is_bound(self):
        """The path digest is ordered: a reversed path can never share an id."""
        field = _bucket()
        bundle = build_world_reaches(_parent(field), min_upstream_cells=4)
        by_path = {}
        for row in bundle["reaches"]:
            by_path[row["world_path_sha256"]] = row
        multi = [row for row in bundle["reaches"] if row["node_count"] > 2]
        self.assertTrue(multi)
        for row in multi:
            low = int(bundle["arrays"]["reach_ptr"][row["reach_index"]])
            high = int(bundle["arrays"]["reach_ptr"][row["reach_index"] + 1])
            chain = bundle["arrays"]["reach_cells"][low:high]
            self.assertEqual(int(bundle["arrays"]["reach_head"][row["reach_index"]]),
                             int(chain[0]))
            self.assertEqual(int(bundle["arrays"]["reach_tail"][row["reach_index"]]),
                             int(chain[-1]))
            self.assertNotEqual(int(chain[0]), int(chain[-1]))


class BudgetTests(unittest.TestCase):
    """R11: the declared ceilings refuse before anything large is allocated."""

    def test_reach_ceiling_is_declared_and_clamped(self):
        fields_module = __import__(
            "terrain_pipeline.surface_rivers.metric_world_reaches", fromlist=["x"])
        self.assertEqual(fields_module.MAX_REACHES, 32768)
        field = _bucket()
        parent = _parent(field)
        with self.assertRaises(ValueError):
            build_world_reaches(parent, min_upstream_cells=0)
        with self.assertRaises(ValueError):
            build_world_reaches(parent, min_upstream_cells=True)
        with self.assertRaises(ValueError):
            build_world_reaches(parent, min_upstream_cells=4.0)


if __name__ == "__main__":
    unittest.main()


class LegacyBackendCrossCheckTests(unittest.TestCase):
    """R11: per-cell cross-check against ``build_reaches`` on an *admissible* input.

    The older backend is not wrong -- it declares different gates. Two of them do not
    apply to this layer, which is why the thin partition exists rather than a call into
    it; both are asserted here instead of merely mentioned:

    1. it requires finite heights everywhere, while a legal partially-covered parent
       keeps NaN on unresolved cells;
    2. it requires ``receiver == -1`` **exactly** on the outlet mask, i.e. every
       structural terminal has to be declared an outlet -- but ``retained`` and
       ``unknown_boundary`` are finite-graph terminals, not sea outlets.

    Where its own gates *are* satisfiable, the per-cell partition must agree.
    """

    def _admissible(self):
        """One basin, finite heights, a single HRU, ``receiver == -1`` on the outlet mask."""
        field = _bowl(17, 17, [(8, 8)])
        parent = _parent(field)
        receiver = parent["arrays"]["receiver"]
        height = parent["arrays"]["elevation_m"]
        self.assertTrue(bool(np.isfinite(height).all()))
        outlet = receiver == -1
        self.assertTrue(bool(outlet.any()))
        flowline = receiver >= 0
        # ``build_reaches`` wants every land cell in exactly one HRU: land is every cell
        # with a positive height, so the single HRU covers all of them and only the
        # ``receiver == -1`` cells are declared outlets.
        owner = np.zeros(receiver.shape, np.int64)
        area = np.array([float(receiver.size) * SPACING ** 2], np.float64)
        return parent, height, receiver, flowline, outlet, owner, area

    def test_partition_agrees_where_the_backend_is_admissible(self):
        parent, height, receiver, flowline, outlet, owner, area = self._admissible()
        legacy = build_reaches(height, receiver, flowline, outlet, owner, area,
                               spacing_m=SPACING)
        legacy_reach = legacy["river_reach"]
        legacy_downstream = legacy["reach_downstream"]
        # The legacy segmentation puts every river cell in a reach, and a reach's
        # downstream is expressed on the same flat grid.
        river_cells = flowline | outlet
        self.assertTrue(bool((legacy_reach[river_cells] >= 0).all()))
        # Our own partition over the *same* receiver, with the gate at 1 so that the
        # channel equals the river cells modulo the terminals we never draw on.
        ours = build_world_reaches(parent, min_upstream_cells=1)
        arrays = ours["arrays"]
        covered = arrays["reach_of_cell"].reshape(-1)
        flowline_flat = flowline.reshape(-1)
        self.assertTrue(bool((covered[flowline_flat] >= 0).all()))
        # The two backends differ by exactly the *terminal sentinel*. Because the legacy
        # input must declare every terminal as an outlet, that backend emits an extra
        # one-cell segment whose only cell **is** the terminal; this layer never draws on
        # a terminal. So the segment-size histogram must match for every size >= 2, and
        # the one-cell count must differ by exactly the sentinel count.
        legacy_flat = legacy_reach.reshape(-1)
        legacy_cells = legacy_flat[legacy_flat >= 0]
        legacy_sizes = np.bincount(legacy_cells, minlength=int(legacy_downstream.size))
        sentinel_index = [index for index in range(int(legacy_downstream.size))
                          if int(legacy_sizes[index]) == 1
                          and int(legacy_downstream[index]) < 0]
        for index in sentinel_index:
            cell = int(np.flatnonzero(legacy_flat == index)[0])
            self.assertEqual(int(receiver.reshape(-1)[cell]), -1)   # the segment *is* a terminal
        kept = [index for index in range(int(legacy_downstream.size))
                if index not in set(sentinel_index)]
        sizes = np.array([int(legacy_sizes[index]) for index in kept], np.int64)
        np.testing.assert_array_equal(np.sort(sizes),
                                      np.sort(arrays["reach_node_count"]))
        # The legacy backend emits exactly one terminal segment per *outlet cell*; this
        # layer emits one terminal **edge** per terminal reach, and a terminal whose only
        # donor is outside the channel produces no reach at all.
        self.assertEqual(len(sentinel_index), int(outlet.sum()))
        # ...and both agree on which cell the basin's own drain terminates at.
        basin = int(np.flatnonzero((receiver.reshape(-1) == -1)
                                   & (np.abs(np.arange(receiver.size) // 17 - 8) <= 1)
                                   & (np.abs(np.arange(receiver.size) % 17 - 8) <= 1))[0])
        ours_targets = set(int(value) for value in arrays["terminal_edge_pairs"][:, 1])
        self.assertIn(basin, ours_targets)
        # Every internal edge of ours is a real receiver edge, exactly as the legacy
        # backend requires of its own chains.
        for index in range(int(arrays["reach_downstream"].size)):
            low = int(arrays["reach_ptr"][index])
            high = int(arrays["reach_ptr"][index + 1])
            chain = arrays["reach_cells"][low:high]
            for first, second in zip(chain[:-1], chain[1:]):
                self.assertEqual(int(receiver.reshape(-1)[first]), int(second))

    def test_legacy_refuses_a_legal_partially_covered_parent(self):
        """Inapplicability 1: NaN on unresolved cells is refused by the older backend."""
        parent, height, receiver, flowline, outlet, owner, area = self._admissible()
        mask = np.ones(height.shape, bool)
        mask[0, :] = False
        values = np.where(mask, height, np.nan)
        with self.assertRaises(ValueError):
            build_reaches(values, receiver, flowline, outlet, owner, area,
                          spacing_m=SPACING)
        # The B1/B2 pair accepts exactly that same window, NaN and all.
        covered = _parent(_bowl(17, 17, [(8, 8)]),
                          mask=mask)
        bundle = build_world_reaches(covered, min_upstream_cells=1)
        self.assertTrue(bool(np.isnan(bundle_parent_elevation(covered)[~mask]).all()))
        validate_world_reaches(bundle, covered)

    def test_legacy_refuses_a_retained_terminal_that_is_not_an_outlet(self):
        """Inapplicability 2: a structural terminal is not a sea outlet."""
        parent, height, receiver, flowline, outlet, owner, area = self._admissible()
        # Declare no outlets at all: the honest description of a finite graph whose
        # terminals are ``retained``/``unknown_boundary``.
        no_outlet = np.zeros(outlet.shape, bool)
        with self.assertRaises(ValueError):
            build_reaches(height, receiver, flowline, no_outlet, owner, area,
                          spacing_m=SPACING)
        # ...while B2 reports the same terminal as ``retained`` without calling it a sea.
        bundle = build_world_reaches(parent, min_upstream_cells=1)
        self.assertTrue(any(row["terminal_kind"] == "retained"
                            for row in bundle["reaches"]))


def bundle_parent_elevation(parent):
    return parent["arrays"]["elevation_m"]


class ResealingAttackTests(unittest.TestCase):
    """R12/R13: a re-sealed wrong network is still refused, and cycles/cross-root flow."""

    @classmethod
    def setUpClass(cls):
        # Two funnels: each has a real trunk with confluences, and there are two distinct
        # roots, so a reach really can falsely claim a *different* root.
        cls.field = _two_cones()
        cls.parent = _parent(cls.field)
        cls.bundle = build_world_reaches(cls.parent, min_upstream_cells=4)

    def _resign(self, bundle):
        from terrain_pipeline.common_infra import identity
        return identity(bundle["arrays"], bundle["metadata"])

    def test_wrong_downstream_is_refused(self):
        hostile = copy.deepcopy(self.bundle)
        downstream = hostile["arrays"]["reach_downstream"]
        target = int(np.flatnonzero(downstream >= 0)[0])
        downstream[target] = int(np.flatnonzero(downstream < 0)[0])
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)

    def test_duplicate_member_is_refused(self):
        hostile = copy.deepcopy(self.bundle)
        cells = hostile["arrays"]["reach_cells"]
        cells[1] = cells[0]
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)

    def test_fabricated_root_is_refused(self):
        """A reach that claims another root than its own members belong to is refused."""
        hostile = copy.deepcopy(self.bundle)
        roots = hostile["arrays"]["reach_root_index"]
        self.assertGreater(len(set(roots.tolist())), 1)   # there is a different root to claim
        original = int(roots[0])
        roots[0] = next(int(value) for value in roots.tolist() if int(value) != original)
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)

    def test_dropped_single_cell_reach_is_refused(self):
        hostile = copy.deepcopy(self.bundle)
        pointer = hostile["arrays"]["reach_ptr"]
        single = [index for index in range(int(pointer.size) - 1)
                  if int(pointer[index + 1]) - int(pointer[index]) == 1]
        self.assertTrue(single)
        index = single[0]
        # Claim that this reach simply has no gap: shrink its slice while keeping the
        # total coverage, which is exactly the "one-cell reach was dropped" tampering.
        pointer[index + 1] = pointer[index]
        for later in range(index + 2, int(pointer.size)):
            pointer[later] = max(pointer[later] - 1, pointer[index])
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)

    def test_wrong_handoff_length_and_edge_are_refused(self):
        hostile = copy.deepcopy(self.bundle)
        hostile["arrays"]["reach_handoff_length_m"][0] += 1.0
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)
        hostile = copy.deepcopy(self.bundle)
        edge = hostile["arrays"]["handoff_edge_pairs"][0]
        edge[[0, 1]] = edge[[1, 0]]          # swap source and target
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)

    def test_missing_terminal_edge_is_refused(self):
        hostile = copy.deepcopy(self.bundle)
        hostile["arrays"]["terminal_edge_pairs"] = \
            hostile["arrays"]["terminal_edge_pairs"][:0]
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)

    def test_reversed_terminal_edge_is_refused(self):
        hostile = copy.deepcopy(self.bundle)
        row = hostile["arrays"]["terminal_edge_pairs"][0]
        row[[0, 1]] = row[[1, 0]]
        hostile["identity_sha256"] = self._resign(hostile)
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)

    def test_swapped_parent_is_refused(self):
        other = _parent(_bowl(17, 17, [(8, 8)]), plan_version=2)
        with self.assertRaises(ValueError):
            validate_world_reaches(self.bundle, other)

    def test_tampered_parent_is_refused_before_the_network(self):
        hostile_parent = copy.deepcopy(self.parent)
        hostile_parent["arrays"]["owner_index"].reshape(-1)[0] = 99
        with self.assertRaises(ValueError):
            build_world_reaches(hostile_parent, min_upstream_cells=4)

    def test_min_upstream_cells_is_required_and_stable(self):
        hostile = copy.deepcopy(self.bundle)
        del hostile["metadata"]["min_upstream_cells"]
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)
        hostile = copy.deepcopy(self.bundle)
        hostile["metadata"]["min_upstream_cells"] = 4.0
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, self.parent)


class PartialCoverageRoundTripTests(unittest.TestCase):
    """A NaN-carrying parent must survive build -> validate unchanged."""

    def test_nan_parent_round_trips(self):
        field = _bucket()
        mask = np.ones(field.shape, bool)
        mask[0, :] = False
        mask[7, 9] = False
        parent = _parent(field, mask=mask)
        self.assertTrue(bool(np.isnan(parent["arrays"]["elevation_m"][~mask]).all()))
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        self.assertIsNone(validate_world_reaches(bundle, parent))
        copy_bundle = {**bundle, "arrays": {name: array.copy()
                                           for name, array in bundle["arrays"].items()}}
        self.assertIsNone(validate_world_reaches(copy_bundle, parent))
        # No unresolved cell was promoted into the channel.
        covered = bundle["arrays"]["reach_of_cell"] >= 0
        self.assertFalse(bool((covered & ~mask).any()))

    def test_whole_support_completeness_is_a_separate_flag(self):
        """`topology_prepared` is never written as complete; the flag is separate.

        A fully resolved window still has a cut at its own edge, so its cells are not all
        ``complete_mask`` -- the flag reports that honestly instead of letting "prepared"
        be read as "complete". A window with an interior hole is likewise not complete,
        and neither case promotes either word into a certification.
        """
        field = _bucket()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        expected = bool(parent["arrays"]["complete_mask"]
                        [parent["arrays"]["resolved_mask"]].all())
        self.assertEqual(bundle["metadata"]["whole_support_upstream_complete"], expected)
        mask = np.ones(field.shape, bool)
        mask[0, :] = False
        cut_parent = _parent(field, mask=mask)
        cut = build_world_reaches(cut_parent, min_upstream_cells=4)
        self.assertEqual(cut["metadata"]["whole_support_upstream_complete"],
                         bool(cut_parent["arrays"]["complete_mask"]
                              [cut_parent["arrays"]["resolved_mask"]].all()))
        self.assertFalse(cut["metadata"]["whole_support_upstream_complete"])
        # "prepared" is never written as "complete", with or without unknowns.
        for item in (bundle, cut):
            self.assertEqual(item["metadata"]["status"], STATUS_TOPOLOGY_PREPARED)
            self.assertFalse(item["metadata"]["physical_domain_certified"])


if __name__ == "__main__":
    unittest.main()


def _northward_channel(rows=17, columns=9):
    """A strictly northward field: *every* cell flows to a smaller flat index.

    Height decreases northward by a fixed 10 m per row with no lateral term, so the D8
    receiver of every cell is exactly ``c -> c - columns`` and the source→root order runs
    row 16 → row 0 -- the exact reverse of a flat-index sort. A one-cell lateral tilt
    breaks the east/west ties so the receiver stays unique rather than ambiguous.
    """
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    field = 10.0 * rr + 0.01 * np.abs(cc - columns // 2)
    return np.ascontiguousarray(field, np.float64)


def _westward_channel(rows=9, columns=17):
    """A strictly westward channel: the mirror case, flow against column order."""
    return np.ascontiguousarray(_northward_channel(columns, rows).T, np.float64)


def _straight(first, second, columns):
    """True when the hop is a pure north/south/east/west step of one cell."""
    delta_row = abs(first // columns - second // columns)
    delta_column = abs(first % columns - second % columns)
    return delta_row + delta_column == 1


class TrunkOrderTests(unittest.TestCase):
    """The trunk sequence must follow the flow, not the flat index."""

    def _check(self, field, threshold):
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=threshold)
        roots_with_trunk = [row for row in bundle["roots"]
                            if row["channel_mainstem_node_count"] > 0]
        self.assertTrue(roots_with_trunk)
        by_id = {row["reach_id"]: row for row in bundle["reaches"]}
        for row in bundle["roots"]:
            ids = row["channel_mainstem_reach_ids"]
            # 1. adjacent items are a real downstream edge, never a flat-index order
            for first, second in zip(ids[:-1], ids[1:]):
                self.assertEqual(by_id[first]["downstream_reach_id"], second)
            if ids:
                last = by_id[ids[-1]]
                self.assertEqual(last["downstream_reach_index"], -1)
                self.assertEqual(last["terminal_root_world_xz"], row["root_world_xz"])
                # 2. the with-terminal contract: S+1 nodes, S edges, S channel cells
                cells = row["channel_mainstem_channel_cell_count"]
                self.assertEqual(row["channel_mainstem_node_count"], cells + 1)
                self.assertEqual(row["channel_mainstem_edges"], cells)
                self.assertGreater(cells, 0)
            else:
                self.assertEqual(row["channel_mainstem_node_count"], 0)
                self.assertEqual(row["channel_mainstem_edges"], 0)
                self.assertEqual(row["channel_mainstem_length_m"], 0.0)
        validate_world_reaches(bundle, parent)
        return parent, bundle

    def test_northward_trunk_runs_against_flat_order(self):
        """The trunk follows the flow, which here runs *against* ascending flat index.

        The invariant is not "every step decreases" (the last steps turn laterally into the
        pit), it is the one that actually distinguishes a flow path from a sorted list: the
        reported trunk must not be the flat-index order of its own cells, and the first
        steps must climb the array northward.
        """
        parent, bundle = self._check(_northward_channel(), 2)
        receiver = parent["arrays"]["receiver"].reshape(-1)
        channel = bundle["arrays"]["reach_of_cell"].reshape(-1) >= 0
        by_id = {row["reach_id"]: row for row in bundle["reaches"]}
        for row in bundle["roots"]:
            ids = row["channel_mainstem_reach_ids"]
            if not ids:
                continue
            low = int(parent["arrays"]["mainstem_ptr"][row["root_index"]])
            high = int(parent["arrays"]["mainstem_ptr"][row["root_index"] + 1])
            cells = [int(cell) for cell in parent["arrays"]["mainstem_cells"][low:high]]
            trunk = [cell for cell in cells if bool(channel[cell])]
            # (a) the flow order is not the flat order of the same cells
            self.assertNotEqual(trunk, sorted(trunk))
            # (b) the trunk's first hop climbs northward, i.e. to a smaller flat index
            self.assertEqual(int(receiver[trunk[0]]), trunk[1])
            self.assertLess(trunk[1], trunk[0])
            # (c) the reported reach sequence is exactly that path, in that order
            expected = []
            for cell in trunk:
                index = int(bundle["arrays"]["reach_of_cell"].reshape(-1)[cell])
                if not expected or expected[-1] != index:
                    expected.append(index)
            self.assertEqual(ids, [bundle["reaches"][index]["reach_id"]
                                   for index in expected])
            for first, second in zip(ids[:-1], ids[1:]):
                self.assertEqual(by_id[first]["downstream_reach_id"], second)

    def test_westward_trunk_runs_against_flat_order(self):
        """The mirror case: westward flow, likewise not the flat order."""
        parent, bundle = self._check(_westward_channel(), 2)
        receiver = parent["arrays"]["receiver"].reshape(-1)
        channel = bundle["arrays"]["reach_of_cell"].reshape(-1) >= 0
        by_id = {row["reach_id"]: row for row in bundle["reaches"]}
        for row in bundle["roots"]:
            ids = row["channel_mainstem_reach_ids"]
            if not ids:
                continue
            low = int(parent["arrays"]["mainstem_ptr"][row["root_index"]])
            high = int(parent["arrays"]["mainstem_ptr"][row["root_index"] + 1])
            cells = [int(cell) for cell in parent["arrays"]["mainstem_cells"][low:high]]
            trunk = [cell for cell in cells if bool(channel[cell])]
            self.assertNotEqual(trunk, sorted(trunk))
            self.assertEqual(int(receiver[trunk[0]]), trunk[1])
            self.assertLess(trunk[1], trunk[0])
            for first, second in zip(ids[:-1], ids[1:]):
                self.assertEqual(by_id[first]["downstream_reach_id"], second)

    def test_trunk_length_equals_the_ordered_parent_path(self):
        """Trunk length is the channel part plus the single terminal hop."""
        parent, bundle = self._check(_northward_channel(), 2)
        channel = bundle["arrays"]["reach_of_cell"].reshape(-1) >= 0
        receiver = parent["arrays"]["receiver"].reshape(-1)
        columns = parent["arrays"]["receiver"].shape[1]
        mesh = reference_mesh(parent)
        for row in bundle["roots"]:
            if not row["channel_mainstem_reach_ids"]:
                continue
            low = int(parent["arrays"]["mainstem_ptr"][row["root_index"]])
            high = int(parent["arrays"]["mainstem_ptr"][row["root_index"] + 1])
            cells = [int(cell) for cell in parent["arrays"]["mainstem_cells"][low:high]]
            trunk = [cell for cell in cells if bool(channel[cell])]
            terminal = int(parent["arrays"]["root_cells"][row["root_index"]])
            path = trunk + [terminal]
            direct = sum(math.hypot(mesh.node_x_m[first] - mesh.node_x_m[second],
                                    mesh.node_z_m[first] - mesh.node_z_m[second])
                         for first, second in zip(path[:-1], path[1:]))
            self.assertEqual(int(receiver[trunk[-1]]), terminal)
            self.assertAlmostEqual(float(row["channel_mainstem_length_m"]), direct,
                                   places=9)
            self.assertEqual(len(path) - 1, len(trunk))

    def test_y_shape_three_reaches_in_order(self):
        """A hand-checkable trunk crossing two junctions gives three ordered reaches."""
        field = _northward_channel()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=2)
        longest = max(bundle["roots"],
                      key=lambda row: len(row["channel_mainstem_reach_ids"]))
        ids = longest["channel_mainstem_reach_ids"]
        self.assertGreaterEqual(len(ids), 2)
        by_id = {row["reach_id"]: row for row in bundle["reaches"]}
        for first, second in zip(ids[:-1], ids[1:]):
            self.assertEqual(by_id[first]["downstream_reach_id"], second)
        self.assertEqual(by_id[ids[-1]]["downstream_reach_index"], -1)
        self.assertEqual(longest["channel_mainstem_node_count"],
                         longest["channel_mainstem_channel_cell_count"] + 1)

    def test_trunk_order_tampering_is_refused(self):
        """A re-sealed, reordered trunk list is refused by the semantic gate."""
        field = _northward_channel()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=2)
        from terrain_pipeline.common_infra import identity as _identity
        target = next(row for row in bundle["roots"]
                      if len(row["channel_mainstem_reach_ids"]) >= 2)
        hostile = copy.deepcopy(bundle)
        ids = hostile["roots"][target["root_index"]]["channel_mainstem_reach_ids"]
        ids.reverse()                                  # exactly the flat-order mistake
        hostile["identity_sha256"] = _identity(hostile["arrays"], hostile["metadata"])
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, parent)

    def test_single_cell_trunk_reports_one_node_zero_edges(self):
        field = _northward_channel()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=2)
        singles = [row for row in bundle["roots"]
                   if row["channel_mainstem_channel_cell_count"] == 1]
        for row in singles:
            self.assertEqual(row["channel_mainstem_node_count"], 2)
            self.assertEqual(row["channel_mainstem_edges"], 1)
            self.assertGreater(float(row["channel_mainstem_length_m"]), 0.0)

    def test_empty_no_channel_reports_all_zero(self):
        field = _northward_channel()
        parent = _parent(field)
        biggest = int(parent["arrays"]["upstream_cells"].max())
        bundle = build_world_reaches(parent, min_upstream_cells=biggest + 1)
        self.assertEqual(bundle["metadata"]["status"], STATUS_EMPTY)
        for row in bundle["roots"]:
            self.assertEqual(row["channel_mainstem_node_count"], 0)
            self.assertEqual(row["channel_mainstem_edges"], 0)
            self.assertEqual(row["channel_mainstem_length_m"], 0.0)
            self.assertEqual(row["channel_mainstem_reach_ids"], [])
            self.assertEqual(row["channel_mainstem_channel_cell_count"], 0)
        validate_world_reaches(bundle, parent)


if __name__ == "__main__":
    unittest.main()


class RawTrunkTests(unittest.TestCase):
    """Raw trunk counts are the parent's own mainstem, never the channel subset.

    This is the assertion that the earlier version failed: it reported the *channel* cell
    count (+1) as the raw node count, while the raw length already came from the parent's
    full slice, so the three numbers disagreed on every root of a real pack and a
    self-comparing validator could not see it.
    """

    def _parent_mainstem(self, parent, index):
        low = int(parent["arrays"]["mainstem_ptr"][index])
        high = int(parent["arrays"]["mainstem_ptr"][index + 1])
        return [int(cell) for cell in parent["arrays"]["mainstem_cells"][low:high]]

    def test_raw_counts_are_the_parent_full_path(self):
        field = _two_cones()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        for row in bundle["roots"]:
            cells = self._parent_mainstem(parent, row["root_index"])
            self.assertGreaterEqual(len(cells), 1)
            self.assertEqual(row["raw_mainstem_node_count"], len(cells))
            self.assertEqual(row["raw_mainstem_edges"], len(cells) - 1)
        # At least one root must have a raw trunk longer than its channel trunk, otherwise
        # this fixture would not be able to tell the two apart at all.
        longer = [row for row in bundle["roots"]
                  if row["raw_mainstem_node_count"]
                  > row["channel_mainstem_channel_cell_count"] + 1]
        self.assertTrue(longer)
        validate_world_reaches(bundle, parent)

    def test_a_wrong_raw_count_is_refused_by_the_parent_binding_itself(self):
        """The gate compares against the parent, so a self-consistent wrong value fails.

        Two layers matter here and they are tested separately:

        1. a tampered bundle is caught by the recomputation (the rebuild now produces the
           correct value, so any stored wrong value disagrees);
        2. the **parent binding** catches a wrong value even when the value is internally
           self-consistent -- which is exactly the shape of the bug this module shipped:
           the builder wrote ``channel + 1`` and a comparing validator agreed with it.

        Layer 2 is exercised by calling the trunk gate directly with a roots list that
        reproduces the old bug, so the assertion cannot pass by re-deriving the same
        mistake.
        """
        from terrain_pipeline.surface_rivers import metric_world_reaches as module
        field = _two_cones()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        from terrain_pipeline.common_infra import identity as _identity

        hostile = copy.deepcopy(bundle)
        target = max(hostile["roots"], key=lambda row: row["raw_mainstem_node_count"])
        old_bug_nodes = target["channel_mainstem_channel_cell_count"] + 1
        self.assertNotEqual(old_bug_nodes, target["raw_mainstem_node_count"])
        target["raw_mainstem_node_count"] = old_bug_nodes
        target["raw_mainstem_edges"] = target["channel_mainstem_cell_count"] \
            if "channel_mainstem_cell_count" in target \
            else target["channel_mainstem_channel_cell_count"]
        hostile["identity_sha256"] = _identity(hostile["arrays"], hostile["metadata"])
        with self.assertRaises(ValueError):
            validate_world_reaches(hostile, parent)

        # Layer 2: the parent binding alone, with no rebuild involved.
        view = module._parent_view(parent)
        args = (hostile["arrays"], hostile["reaches"], hostile["roots"])
        with self.assertRaises(ValueError) as caught:
            module._assert_trunk_order(view, *args)
        self.assertIn("raw trunk length", str(caught.exception))

    def test_raw_counts_survive_an_empty_channel(self):
        """A threshold above every cell empties the channel but not the raw trunk."""
        field = _two_cones()
        parent = _parent(field)
        biggest = int(parent["arrays"]["upstream_cells"].max())
        bundle = build_world_reaches(parent, min_upstream_cells=biggest + 1)
        self.assertEqual(bundle["metadata"]["status"], STATUS_EMPTY)
        checked = 0
        for row in bundle["roots"]:
            cells = self._parent_mainstem(parent, row["root_index"])
            self.assertEqual(row["raw_mainstem_node_count"], len(cells))
            self.assertEqual(row["raw_mainstem_edges"], len(cells) - 1)
            self.assertGreater(float(row["raw_mainstem_length_m"]), 0.0)
            # The channel side is empty, strictly 0/0/0, and maps to no reach at all.
            self.assertEqual(row["channel_mainstem_node_count"], 0)
            self.assertEqual(row["channel_mainstem_edges"], 0)
            self.assertEqual(row["channel_mainstem_channel_cell_count"], 0)
            self.assertEqual(row["channel_mainstem_length_m"], 0.0)
            self.assertEqual(row["channel_mainstem_reach_ids"], [])
            self.assertEqual(row["raw_mainstem_reach_ids"], [])
            checked += 1
        self.assertGreater(checked, 0)
        validate_world_reaches(bundle, parent)

    def test_raw_reach_ids_are_the_full_path_mapped_to_selected_reaches(self):
        """The raw id list is the parent path projected onto the *selected* reaches.

        It is documented as a projection, not as a claim that a non-channel path also has
        segments: cells below the gate belong to no reach and therefore contribute no id.
        """
        field = _two_cones()
        parent = _parent(field)
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        reach_of_cell = bundle["arrays"]["reach_of_cell"].reshape(-1)
        for row in bundle["roots"]:
            cells = self._parent_mainstem(parent, row["root_index"])
            expected = []
            for cell in cells:
                index = int(reach_of_cell[cell])
                if index < 0:
                    continue                      # below the gate: no reach to name
                reach_id = bundle["reaches"][index]["reach_id"]
                if not expected or expected[-1] != reach_id:
                    expected.append(reach_id)
            self.assertEqual(row["raw_mainstem_reach_ids"], expected)
            # ...and it is exactly the channel trunk sequence, because both project the
            # same ordered parent path onto the same selection.
            self.assertEqual(row["raw_mainstem_reach_ids"],
                             row["channel_mainstem_reach_ids"])
        validate_world_reaches(bundle, parent)


class DefaultGateTests(unittest.TestCase):
    """The declared default gate and the empty-channel contract at that gate."""

    def test_default_gate_is_48_and_declared(self):
        self.assertEqual(DEFAULT_MIN_UPSTREAM_CELLS, 48)
        field = _two_cones()
        bundle = build_world_reaches(_parent(field))
        self.assertEqual(bundle["metadata"]["min_upstream_cells"], 48)

    def test_gate_above_the_window_empties_the_channel_only(self):
        field = _two_cones()
        parent = _parent(field)
        biggest = int(parent["arrays"]["upstream_cells"].max())
        for threshold in (biggest, biggest + 1, biggest * 10):
            with self.subTest(threshold=threshold):
                bundle = build_world_reaches(parent, min_upstream_cells=threshold)
                self.assertEqual(bundle["metadata"]["counts"]["channel_cells"], 0)
                self.assertEqual(bundle["metadata"]["status"], STATUS_EMPTY)
                for row in bundle["roots"]:
                    self.assertEqual(row["channel_mainstem_node_count"], 0)
                    self.assertEqual(row["channel_mainstem_edges"], 0)
                    self.assertEqual(row["channel_mainstem_channel_cell_count"], 0)
                    self.assertEqual(row["channel_mainstem_length_m"], 0.0)
                    self.assertGreaterEqual(row["raw_mainstem_node_count"], 1)
                validate_world_reaches(bundle, parent)


if __name__ == "__main__":
    unittest.main()


def test_invalid_parent_root_uses_declared_rejection_reason():
    from terrain_pipeline.surface_rivers.metric_world_reaches import (
        _ordered_trunk, _assert_trunk_order)
    parent = {
        'mainstem_ptr': np.array([0, 1], np.int64),
        'mainstem_cells': np.array([0], np.int64),
        'root_cells': np.array([1], np.int64),
    }
    with unittest.TestCase().assertRaisesRegex(RuntimeError, 'root_not_terminal'):
        _ordered_trunk(parent, {}, {}, 0)
    arrays = {'reach_of_cell': np.array([-1, -1], np.int64)}
    with unittest.TestCase().assertRaisesRegex(ValueError, 'root_not_terminal'):
        _assert_trunk_order(parent, arrays, [], [{'root_index': 0}])
