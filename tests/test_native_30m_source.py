"""Behaviour tests for the native 30 m source stage and its strict irregular-graph topology.

Two rules for every test here:

* **No real page is a fixture.** The 2049 pages under `.scratch` are 33 MB each and
  a test that only passes on one file is a record, not a test. Every page below is
  synthesised, and its content is a function of the **absolute** native index so
  that two pages agree cell-for-cell where they overlap (which is what the assembly
  kernel's interior-equality rule needs).
* **Artifacts stay out of the workspace.** Pages are written into a
  `tempfile.TemporaryDirectory()` (the OS temp directory), which the test deletes.

The tests state behaviour: pins are required and checked, metadata is validated
against the real page format, page order cannot change a value or a digest, an
unanswered cell stays unanswered, and the topology never invents a path through an
unknown cell or calls a window edge an outlet.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown

from terrain_pipeline.surface_rivers import native_30m_source as source
from terrain_pipeline.surface_rivers.metric_domain_closure import _steepest_graph
from terrain_pipeline.surface_rivers.metric_network_discharge_product import TERMINAL_LABELS

SEED = source.DEFAULT_WORLD_SEED
SPACING_M = source.NATIVE_SPACING_M


# --------------------------------------------------------------------------- #
# synthetic pages
# --------------------------------------------------------------------------- #
def plane(origin_xz, shape_zx, shift=0.0):
    """Elevation as a function of the **absolute** native index (a NW-draining ramp).

    Two pages that share a world cell therefore carry the same value there, which is
    the property the assembly's interior-equality rule is built on.
    """
    rows, columns = shape_zx
    z = np.arange(rows)[:, None] + int(origin_xz[1])
    x = np.arange(columns)[None, :] + int(origin_xz[0])
    return 100.0 + 0.25 * z + 0.5 * x + shift


def bowl(origin_xz, shape_zx, centre_rc, depth_m=200.0, width_cells=6.0):
    """The same ramp with one deep pit, so an *interior* terminal can exist.

    Without a pit every chain on a ramp leaves through the window ring, and the
    `retained` label would never be exercised.
    """
    field = plane(origin_xz, shape_zx)
    rr = np.arange(shape_zx[0])[:, None] - float(centre_rc[0])
    cc = np.arange(shape_zx[1])[None, :] - float(centre_rc[1])
    return field - depth_m * np.exp(-(rr ** 2 + cc ** 2) / (2.0 * width_cells ** 2))


def write_page(directory, name, *, origin_xz, elevation, spacing_m=SPACING_M,
               world_seed=SEED, size=None, metadata=None, extra_arrays=None,
               metadata_dtype=None):
    """Write one page in the real format and return its pinned record."""
    path = Path(directory) / name
    if metadata is None:
        rows, columns = elevation.shape
        record = {
            "schema": source.PAGE_SCHEMA,
            "native_origin": [int(origin_xz[0]), int(origin_xz[1])],
            "size": int(rows if size is None else size),
            "spacing_m": float(spacing_m),
            "world_seed": int(world_seed),
            "shape": [int(rows), int(columns)],
        }
    else:
        record = metadata
    payload = dict(extra_arrays or {})
    scalar = np.array(json.dumps(record, sort_keys=True), dtype=metadata_dtype or None)
    np.savez(path, elevation_native=np.asarray(elevation), metadata_json=scalar, **payload)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def window(directory, *, pages, origin_native_xz, shape_zx, **kwargs):
    return source.load_native_window(
        pages, origin_native_xz=origin_native_xz, shape_zx=shape_zx, **kwargs)


class TempPages(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="native30m-")
        self.directory = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()


# --------------------------------------------------------------------------- #
# 1. pins and page format
# --------------------------------------------------------------------------- #
class PinTests(TempPages):
    def test_tampered_page_is_refused_by_pin(self):
        record = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)))
        np.savez(self.directory / "a.npz",
                 elevation_native=plane((100, 100), (40, 40), shift=1.0),
                 metadata_json=np.array(json.dumps({
                     "schema": source.PAGE_SCHEMA, "native_origin": [100, 100],
                     "size": 40, "spacing_m": SPACING_M, "world_seed": SEED})))
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[record], origin_native_xz=(110, 110),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_PIN_MISMATCH, str(caught.exception))

    def test_page_without_a_pin_is_refused(self):
        write_page(self.directory, "a.npz", origin_xz=(100, 100),
                   elevation=plane((100, 100), (40, 40)))
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[{"path": str(self.directory / "a.npz")}],
                   origin_native_xz=(110, 110), shape_zx=(10, 10))
        self.assertIn(source.REASON_PIN_MISSING, str(caught.exception))

    def test_a_missing_source_file_is_named(self):
        record = {"path": str(self.directory / "absent.npz"), "sha256": "0" * 64}
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[record], origin_native_xz=(110, 110),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_PAGE_MISSING, str(caught.exception))

    def test_the_total_page_cell_budget_is_enforced(self):
        records = [write_page(self.directory, "a.npz", origin_xz=(100, 100),
                              elevation=plane((100, 100), (40, 40))),
                   write_page(self.directory, "b.npz", origin_xz=(100, 200),
                              elevation=plane((100, 200), (40, 40)))]
        original = source.MAX_TOTAL_PAGE_CELLS
        try:
            source.MAX_TOTAL_PAGE_CELLS = 40 * 40 * 2 - 1
            with self.assertRaises(ValueError) as caught:
                window(self.directory, pages=records, origin_native_xz=(110, 110),
                       shape_zx=(10, 10))
            self.assertIn(source.REASON_BUDGET, str(caught.exception))
        finally:
            source.MAX_TOTAL_PAGE_CELLS = original

    def test_the_same_page_pinned_twice_is_refused(self):
        record = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)))
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[record, dict(record)],
                   origin_native_xz=(110, 110), shape_zx=(10, 10))
        self.assertIn(source.REASON_DUPLICATE_PAGE, str(caught.exception))

    def test_a_result_archive_is_not_a_page(self):
        record = write_page(self.directory, "r.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)),
                            extra_arrays={"routed_q_m3_s": np.zeros((40, 40))})
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[record], origin_native_xz=(110, 110),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_PAGE_INVALID, str(caught.exception))

    def test_pages_must_be_float64_and_square(self):
        single = write_page(self.directory, "f32.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)).astype(np.float32))
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[single], origin_native_xz=(110, 110),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_PAGE_INVALID, str(caught.exception))

        wide = write_page(self.directory, "wide.npz", origin_xz=(100, 100),
                          elevation=plane((100, 100), (40, 60)))
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[wide], origin_native_xz=(110, 110),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_SHAPE_MISMATCH, str(caught.exception))

    def test_metadata_is_validated_against_the_real_format(self):
        cases = [
            ({"schema": "some-other-page-v9", "native_origin": [100, 100], "size": 40,
              "spacing_m": SPACING_M, "world_seed": SEED}, source.REASON_PAGE_INVALID),
            ({"native_origin": [100, 100], "size": 40, "spacing_m": SPACING_M},
             source.REASON_PAGE_INVALID),
            ({"schema": source.PAGE_SCHEMA, "native_origin": [100.5, 100], "size": 40,
              "spacing_m": SPACING_M, "world_seed": SEED}, source.REASON_PAGE_INVALID),
        ]
        for index, (metadata, reason) in enumerate(cases):
            with self.subTest(index=index):
                record = write_page(self.directory, "m%d.npz" % index,
                                    origin_xz=(100, 100),
                                    elevation=plane((100, 100), (40, 40)),
                                    metadata=metadata)
                with self.assertRaises(ValueError) as caught:
                    window(self.directory, pages=[record], origin_native_xz=(110, 110),
                           shape_zx=(10, 10))
                self.assertIn(reason, str(caught.exception))


# --------------------------------------------------------------------------- #
# 2. seed / spacing / shape / budget
# --------------------------------------------------------------------------- #
class ScalarTests(TempPages):
    def setUp(self):
        super().setUp()
        self.record = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                                 elevation=plane((100, 100), (40, 40)))

    def test_an_illegal_seed_is_refused_before_any_file_is_read(self):
        for value in (True, 20261020.0, "20261020", 0, -5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as caught:
                    window(self.directory, pages=[self.record],
                           origin_native_xz=(110, 110), shape_zx=(10, 10),
                           world_seed=value)
                self.assertIn(source.REASON_SEED_MISMATCH, str(caught.exception))

    def test_a_page_from_another_world_seed_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[self.record], origin_native_xz=(110, 110),
                   shape_zx=(10, 10), world_seed=SEED + 1)
        self.assertIn(source.REASON_SEED_MISMATCH, str(caught.exception))

    def test_a_non_native_spacing_is_refused_and_is_not_a_knob(self):
        record = write_page(self.directory, "s20.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)), spacing_m=20.0)
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[record], origin_native_xz=(110, 110),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_SPACING_MISMATCH, str(caught.exception))

    def test_a_declared_size_that_disagrees_with_the_array_is_refused(self):
        record = write_page(self.directory, "sz.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)), size=39)
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[record], origin_native_xz=(110, 110),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_SHAPE_MISMATCH, str(caught.exception))

    def test_window_shape_and_cell_budget_are_enforced(self):
        for shape in ((1, 10), (10, 1), (0, 10)):
            with self.subTest(shape=shape):
                with self.assertRaises(ValueError) as caught:
                    window(self.directory, pages=[self.record],
                           origin_native_xz=(110, 110), shape_zx=shape)
                self.assertIn(source.REASON_SHAPE_MISMATCH, str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[self.record], origin_native_xz=(110, 110),
                   shape_zx=(10, 10), max_cells=99)
        self.assertIn(source.REASON_BUDGET, str(caught.exception))

    def test_a_non_integer_origin_is_refused(self):
        for origin in (("110", 110), (110,), (110, 110, 0), (110.5, 110)):
            with self.subTest(origin=origin):
                with self.assertRaises(ValueError):
                    window(self.directory, pages=[self.record],
                           origin_native_xz=origin, shape_zx=(10, 10))


# --------------------------------------------------------------------------- #
# 3. the assembled window
# --------------------------------------------------------------------------- #
class AssemblyTests(TempPages):
    def test_a_window_no_page_covers_is_refused_rather_than_returned_empty(self):
        record = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)))
        with self.assertRaises(ValueError) as caught:
            window(self.directory, pages=[record], origin_native_xz=(900, 900),
                   shape_zx=(10, 10))
        self.assertIn(source.REASON_WINDOW_NOT_COVERED, str(caught.exception))

    def test_the_border_band_is_unresolved_and_never_filled(self):
        record = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (60, 60)))
        # The window *is* the page, so its own six-cell ring is inside every
        # candidate's border band: refused, not averaged and not extrapolated.
        result = window(self.directory, pages=[record], origin_native_xz=(100, 100),
                        shape_zx=(60, 60))
        band = source.BORDER_BAND_CELLS
        self.assertEqual(band, 6)
        self.assertEqual(result["border_band_cells"], band)
        self.assertFalse(result["resolved_mask"][:band, :].any())
        self.assertFalse(result["resolved_mask"][-band:, :].any())
        self.assertFalse(result["resolved_mask"][:, :band].any())
        self.assertFalse(result["resolved_mask"][:, -band:].any())
        self.assertTrue(result["resolved_mask"][band:-band, band:-band].all())
        self.assertTrue(np.isnan(result["field"][~result["resolved_mask"]]).all())
        self.assertEqual(result["unresolved_reason"], "unresolved_border")
        self.assertEqual(result["resolved_cells"] + result["unresolved_cells"],
                         result["field"].size)

    def test_resolved_values_are_the_absolute_index_values(self):
        record = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (60, 60)))
        result = window(self.directory, pages=[record], origin_native_xz=(110, 120),
                        shape_zx=(20, 30))
        self.assertEqual(result["origin_native_xz"], [110, 120])
        self.assertEqual(result["shape_zx"], [20, 30])
        self.assertEqual(result["world_seed"], SEED)
        self.assertEqual(result["spacing_m"], SPACING_M)
        expected = plane((110, 120), (20, 30))
        np.testing.assert_array_equal(result["field"], expected)

    def test_a_negative_origin_is_a_native_index_not_a_metre_value(self):
        record = write_page(self.directory, "neg.npz", origin_xz=(-400, -300),
                            elevation=plane((-400, -300), (60, 60)))
        result = window(self.directory, pages=[record], origin_native_xz=(-380, -280),
                        shape_zx=(20, 20))
        self.assertEqual(result["origin_native_xz"], [-380, -280])
        self.assertTrue(result["resolved_mask"].all())
        np.testing.assert_array_equal(result["field"], plane((-380, -280), (20, 20)))

    def test_page_order_cannot_change_a_value_or_the_digest(self):
        # Two pages that overlap over the whole window: the kernel has to pick one
        # per cell, and the pick must not depend on the list order.
        west = write_page(self.directory, "west.npz", origin_xz=(100, 100),
                          elevation=plane((100, 100), (60, 60)))
        east = write_page(self.directory, "east.npz", origin_xz=(130, 100),
                          elevation=plane((130, 100), (60, 60)))
        forward = window(self.directory, pages=[west, east],
                         origin_native_xz=(120, 110), shape_zx=(30, 30))
        backward = window(self.directory, pages=[east, west],
                          origin_native_xz=(120, 110), shape_zx=(30, 30))
        self.assertEqual(forward["assembly_digest"], backward["assembly_digest"])
        np.testing.assert_array_equal(forward["field"], backward["field"])
        np.testing.assert_array_equal(forward["resolved_mask"], backward["resolved_mask"])
        self.assertEqual([item["path"] for item in forward["source_records"]],
                         [item["path"] for item in backward["source_records"]])
        self.assertEqual([item["path"] for item in forward["source_records"]],
                         sorted([item["path"] for item in forward["source_records"]]))

    def test_the_digest_changes_when_the_pinned_content_changes(self):
        first = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                           elevation=plane((100, 100), (60, 60)))
        assembled = window(self.directory, pages=[first], origin_native_xz=(110, 110),
                           shape_zx=(20, 20))
        second = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (60, 60), shift=3.0))
        shifted = window(self.directory, pages=[second], origin_native_xz=(110, 110),
                         shape_zx=(20, 20))
        self.assertNotEqual(assembled["assembly_digest"], shifted["assembly_digest"])
        self.assertNotEqual(assembled["source_records"][0]["sha256"],
                            shifted["source_records"][0]["sha256"])

    def test_source_records_carry_path_hash_origin_and_the_source_code_identity(self):
        record = write_page(self.directory, "a.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (60, 60)))
        result = window(self.directory, pages=[record], origin_native_xz=(110, 110),
                        shape_zx=(20, 20))
        entry = result["source_records"][0]
        self.assertEqual(entry["path"], record["path"])
        self.assertEqual(entry["sha256"], record["sha256"])
        self.assertEqual(entry["native_origin_xz"], [100, 100])
        self.assertEqual(entry["shape_zx"], [60, 60])
        self.assertEqual(entry["spacing_m"], SPACING_M)
        self.assertEqual(entry["world_seed"], SEED)
        identity = result["source_code_sha256"]
        self.assertEqual(list(identity),
                         ["terrain_pipeline.surface_rivers.metric_cross_region"])
        self.assertRegex(identity["terrain_pipeline.surface_rivers.metric_cross_region"],
                         r"^[0-9a-f]{64}$")


# --------------------------------------------------------------------------- #
# 4. strict irregular-graph topology
# --------------------------------------------------------------------------- #
MARGIN = 20  # page margin around the window, so the window is page-interior


def interior_window(directory, *, shape_zx=(40, 40), pit_rc=None):
    """A fully resolved window: one page whose interior contains the window.

    ``pit_rc`` is given in **window** coordinates and shifted into the page, so a
    test can place a local minimum where it means to instead of guessing an offset.
    """
    rows, columns = shape_zx
    page_shape = (rows + 2 * MARGIN, columns + 2 * MARGIN)
    centre = None if pit_rc is None else (pit_rc[0] + MARGIN, pit_rc[1] + MARGIN)
    elevation = (plane((100, 100), page_shape) if centre is None
                 else bowl((100, 100), page_shape, centre))
    record = write_page(directory, "interior.npz", origin_xz=(100, 100),
                        elevation=elevation)
    assembled = window(directory, pages=[record],
                       origin_native_xz=(100 + MARGIN, 100 + MARGIN),
                       shape_zx=shape_zx)
    assert assembled["resolved_mask"].all()
    return assembled


class TopologyTests(TempPages):
    def test_a_ramp_receiver_is_the_existing_kernel_bit_for_bit(self):
        assembled = interior_window(self.directory)
        topology = source.build_strict_topology(assembled["field"],
                                                assembled["resolved_mask"])
        expected = _steepest_graph(assembled["field"]).reshape(-1)
        np.testing.assert_array_equal(topology["receiver"].reshape(-1), expected)
        self.assertEqual(topology["receiver"].dtype, np.dtype(np.int64))
        self.assertEqual(topology["receiver"].shape, assembled["field"].shape)

    def test_the_label_vocabulary_is_the_product_s_vocabulary(self):
        assembled = interior_window(self.directory)
        topology = source.build_strict_topology(assembled["field"],
                                                assembled["resolved_mask"])
        kinds = topology["terminal_kind"]
        self.assertEqual(kinds.dtype, source.TERMINAL_KIND_DTYPE)
        self.assertTrue(np.isin(kinds, TERMINAL_LABELS).all())
        self.assertFalse((kinds == "open_outflow").any())
        self.assertEqual(sum(topology["census"].values()), kinds.size)

    def test_live_cells_are_interior_so_the_accumulator_accepts_them(self):
        assembled = interior_window(self.directory)
        topology = source.build_strict_topology(assembled["field"],
                                                assembled["resolved_mask"])
        live = topology["valid_mask"] & (topology["receiver"] >= 0)
        self.assertTrue(live.any())
        self.assertTrue((topology["terminal_kind"][live] == "interior").all())
        terminal = topology["valid_mask"] & (topology["receiver"] < 0)
        self.assertTrue(np.isin(topology["terminal_kind"][terminal],
                                ("retained", "unknown_boundary")).all())

    def test_window_edge_cells_seed_unknown_upstream_and_are_never_an_outlet(self):
        assembled = interior_window(self.directory)
        topology = source.build_strict_topology(assembled["field"],
                                                assembled["resolved_mask"])
        ring = np.zeros(assembled["field"].shape, bool)
        ring[[0, -1], :] = True
        ring[:, [0, -1]] = True
        self.assertTrue(topology["upstream_unknown_mask"][ring].all())
        edge_terminals = ring & topology["valid_mask"] & (topology["receiver"] < 0)
        if edge_terminals.any():
            self.assertTrue(
                (topology["terminal_kind"][edge_terminals] == "unknown_boundary").all())
        self.assertEqual(topology["upstream_unknown_seed_cells"],
                         int((ring & topology["valid_mask"]).sum()))

    def test_an_interior_terminal_is_retained_and_is_not_a_lake(self):
        assembled = interior_window(self.directory, shape_zx=(40, 40), pit_rc=(22, 18))
        topology = source.build_strict_topology(assembled["field"],
                                                assembled["resolved_mask"])
        retained = topology["terminal_kind"] == "retained"
        self.assertTrue(retained.any())
        self.assertTrue((topology["receiver"][retained] == -1).all())
        # A retained terminal is clean: nothing undeclared flows into it.
        self.assertFalse(topology["upstream_unknown_mask"][retained].any())
        policy = topology["topology_policy"]
        self.assertIn("not a natural lake", policy["retained"])
        self.assertIn("certified outlet", policy["retained"])

    def test_source_seeds_and_accumulation_reference(self):
        assembled = interior_window(self.directory, shape_zx=(48, 48))
        topology = source.build_strict_topology(assembled['field'], assembled['resolved_mask'])
        mask = assembled['resolved_mask']
        expected_seeds = graph_support_unknown(mask)
        np.testing.assert_array_equal(topology['upstream_unknown_mask'], expected_seeds)
        from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge
        result = accumulate_network_discharge(
            topology['receiver'],
            np.where(mask, 1., 0.).astype(np.float64),
            mask,
            terminal_kind=topology['terminal_kind'],
            upstream_unknown_mask=expected_seeds,
        )
        dirty = np.zeros(mask.size, dtype=bool)
        receiverflat = topology['receiver'].ravel()
        seedidx = np.flatnonzero(expected_seeds.ravel())
        for s in seedidx:
            seen = set()
            current = int(s)
            while current >= 0:
                if current in seen:
                    raise AssertionError('cycle')
                seen.add(current)
                dirty[current] = True
                current = int(receiverflat[current])
        expected_complete = mask & ~dirty.reshape(mask.shape)
        np.testing.assert_array_equal(result['complete_mask'], expected_complete)

    def test_terminal_unknown_direction(self):
        import numpy as np
        from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge

        rec = np.array([[1, 2, -1, -1]], np.int64)
        valid = np.ones(rec.shape, bool)
        kinds = np.array([['interior', 'interior', 'retained', 'unknown_boundary']], dtype='U24')
        local = np.ones(rec.shape, np.float64)

        seed1 = np.array([[True, False, False, True]], bool)
        result1 = accumulate_network_discharge(rec, local, valid, terminal_kind=kinds, upstream_unknown_mask=seed1)
        np.testing.assert_array_equal(result1['complete_mask'], [[False, False, False, False]])

        seed2 = np.array([[False, False, True, True]], bool)
        result2 = accumulate_network_discharge(rec, local, valid, terminal_kind=kinds, upstream_unknown_mask=seed2)
        np.testing.assert_array_equal(result2['complete_mask'], [[True, True, False, False]])

        np.testing.assert_array_equal(rec, np.array([[1, 2, -1, -1]], np.int64))

    def test_no_receiver_points_at_an_unresolved_cell(self):
        # The page stops short of the window's east side, so a block of cells is
        # unanswered and sits right beside answered terrain.
        record = write_page(self.directory, "partial.npz", origin_xz=(100, 100),
                            elevation=plane((100, 100), (40, 40)))
        assembled = window(self.directory, pages=[record],
                           origin_native_xz=(90, 100), shape_zx=(40, 60))
        self.assertFalse(assembled["resolved_mask"].all())
        topology = source.build_strict_topology(assembled["field"],
                                                assembled["resolved_mask"])
        unresolved = ~assembled["resolved_mask"]
        self.assertTrue(unresolved.any())
        self.assertTrue((topology["terminal_kind"][unresolved] == "inactive").all())
        self.assertTrue((topology["receiver"][unresolved] == -1).all())
        self.assertFalse(topology["upstream_unknown_mask"][unresolved].any())
        live = assembled["resolved_mask"] & (topology["receiver"] >= 0)
        targets = topology["receiver"][live]
        self.assertTrue(targets.size)
        self.assertFalse(assembled["resolved_mask"].reshape(-1)[targets].__invert__().any())
        self.assertEqual((topology["upstream_unknown_seed_cells"]),
                         int(graph_support_unknown(assembled["resolved_mask"]).sum()))

    def test_a_flat_field_has_no_receiver_and_repeats_identically(self):
        flat = np.full((12, 12), 250.0)
        mask = np.ones((12, 12), bool)
        first = source.build_strict_topology(flat, mask)
        second = source.build_strict_topology(flat, mask)
        self.assertTrue((first["receiver"] == -1).all())
        np.testing.assert_array_equal(first["receiver"], second["receiver"])
        np.testing.assert_array_equal(first["terminal_kind"], second["terminal_kind"])
        np.testing.assert_array_equal(first["upstream_unknown_mask"],
                                     second["upstream_unknown_mask"])
        self.assertTrue((first["terminal_kind"] == "retained").sum() > 0)

    def test_unresolved_values_cannot_decide_a_path(self):
        # Resolved values are legitimate; the unresolved ones are hostile (NaN, inf,
        # -inf) and must not attract a receiver or produce a self loop.
        field = plane((0, 0), (10, 10))
        mask = np.ones((10, 10), bool)
        mask[4, 4] = False
        hostile = field.copy()
        hostile[4, 4] = np.nan
        clean = source.build_strict_topology(field, mask)
        dirty = source.build_strict_topology(hostile, mask)
        np.testing.assert_array_equal(clean["receiver"], dirty["receiver"])
        np.testing.assert_array_equal(clean["terminal_kind"], dirty["terminal_kind"])
        self.assertEqual(dirty["receiver"][4, 4], -1)

    def test_bad_topology_inputs_are_refused(self):
        field = plane((0, 0), (8, 8))
        cases = [
            (field, np.ones((8, 8), np.float32)),
            (field, np.ones((8, 8), bool)[:4, :4]),
            (field, np.zeros((8, 8), bool)),
            (np.array([[1.0]]), np.ones((1, 1), bool)),
        ]
        for index, (bed, mask) in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    source.build_strict_topology(bed, mask)
        broken = field.copy()
        broken[2, 2] = np.nan
        with self.assertRaises(ValueError):
            source.build_strict_topology(broken, np.ones((8, 8), bool))

    def test_the_policy_and_dependency_identity_are_recorded(self):
        assembled = interior_window(self.directory)
        topology = source.build_strict_topology(assembled["field"],
                                                assembled["resolved_mask"])
        policy = topology["topology_policy"]
        self.assertEqual(policy["algorithm"], "strict_downhill_irregular_graph_v2")
        self.assertIn("strict_receivers", policy["implementation"])
        for key in ("representative_position", "unresolved", "upstream_unknown_seed",
                    "terminal_kind", "retained", "unknown_boundary", "natural_outlet",
                    "repair", "receiver", "validity", "upstream_unknown_mask"):
            self.assertIn(key, policy)
        identity = topology["dependency_source_sha256"]
        self.assertEqual(sorted(identity), [
            'terrain_pipeline.drainage',
            "terrain_pipeline.surface_rivers.metric_network_discharge_product",
        ])
        for value in identity.values():
            self.assertRegex(value, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
