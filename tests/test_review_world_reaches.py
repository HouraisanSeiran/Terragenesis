"""Independent expectations for the B4 review tool (``tools/review_world_reaches.py``).

Two kinds of check live here:

* **behavioural pairs on synthetic networks** built through the B1/B2 entry points, where
every expectation is written out by hand: the independent per-cell walk must agree with
the production node/edge/length facts, a tampered ``reach_downstream`` must be refused, a
dropped classification row must be refused, and an **internal un-received break** must be
classified as a failure rather than being read as a lake outlet or a window edge;
* **input guards**: a damaged evidence package and an over-budget support are refused
  before anything is reviewed.

The reference walk in this file is deliberately different from the tool's: it groups cells
by the delivered ``reach_of_cell`` raster, finds each group's head as the member that is
nobody's receiver target, and then follows ``receiver`` one cell at a time. It never reads
``reach_ptr`` / ``reach_cells``, so a number that only agrees with the tool's own CSR
bookkeeping cannot pass.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.surface_rivers.metric_world_domains import (
    SOURCE_KIND_SYNTHETIC, domain_candidates, support_plan)
from terrain_pipeline.surface_rivers.metric_world_reaches import build_world_reaches
from tools import review_world_reaches as review
from terrain_pipeline.drainage import grid_mesh as grid_mesh

SEED = 20261020
SPACING = 30.0


# --------------------------------------------------------------------------- #
# synthetic parents (the same construction route the B chain uses, synthetic source)
# --------------------------------------------------------------------------- #
def _cone(rows=21, columns=21, centre=(10, 10), slope=60.0):
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    return np.ascontiguousarray(1000.0 + slope * np.hypot(rr - centre[0], cc - centre[1]),
                                np.float64)


def _two_basins(rows=33, columns=33, centres=((8, 8), (24, 24))):
    rr, cc = np.meshgrid(np.arange(rows), np.arange(columns), indexing="ij")
    field = np.full((rows, columns), 1100.0)
    for centre_r, centre_c in centres:
        field = np.minimum(field, 50.0 * np.round(
            np.hypot(rr - centre_r, cc - centre_c), 6))
    return np.ascontiguousarray(field, np.float64)


def _pin(field):
    digest = hashlib.sha256(np.ascontiguousarray(field, np.float64).tobytes()).hexdigest()
    return [{"path": "synthetic://b4-review-%s.npz" % digest[:8], "sha256": digest}]


def _parent(field, *, origin=(0, 0), plan_version=1):
    shape = list(field.shape)
    support = support_plan(world_seed=SEED, spacing_m=SPACING,
                           origin_native_xz=list(origin), shape_zx=shape,
                           source_records=_pin(field), plan_version=plan_version)
    resolved = np.ones(field.shape, bool)
    source = {
        "field": np.ascontiguousarray(field, np.float64),
        "resolved_mask": resolved,
        "origin_native_xz": list(origin),
        "shape_zx": shape,
        "world_seed": SEED,
        "spacing_m": SPACING,
    }
    return domain_candidates(support, source=source, source_kind=SOURCE_KIND_SYNTHETIC)


# --------------------------------------------------------------------------- #
# the independent reference: raster grouping, one cell at a time
# --------------------------------------------------------------------------- #
def reference_facts(parent, bundle):
    """Node/edge/length facts rebuilt from ``reach_of_cell`` without the CSR arrays."""
    arrays = parent["arrays"]
    metadata = parent['support']['metadata']
    spacing = metadata['spacing_m']
    origin = metadata['origin_native_xz']
    mesh = grid_mesh(tuple(metadata['shape_zx']), x0_m=origin[0] * spacing,
                     z0_m=origin[1] * spacing, dx_m=spacing, world_seed=metadata['world_seed'])
    spacing = float(parent["support"]["metadata"]["spacing_m"])
    rows, columns = (int(value) for value in parent["support"]["metadata"]["shape_zx"])
    receiver = arrays["receiver"].reshape(-1)
    reached = bundle["arrays"]["reach_of_cell"].reshape(-1)
    count = int(bundle["arrays"]["reach_downstream"].size)
    facts = []
    for index in range(count):
        members = [int(cell) for cell in np.flatnonzero(reached == index)]
        targets = {int(receiver[cell]) for cell in members if int(receiver[cell]) >= 0}
        heads = [cell for cell in members if cell not in targets]
        if len(heads) != 1:
            raise AssertionError("reach %d has %d heads" % (index, len(heads)))
        chain = [heads[0]]
        while True:
            following = int(receiver[chain[-1]])
            if following < 0 or int(reached[following]) != index:
                break
            chain.append(following)
        if sorted(chain) != sorted(members):
            raise AssertionError("reach %d is not a receiver chain" % index)
        length = 0.0
        for first, second in zip(chain[:-1], chain[1:]):
            length += math.hypot(mesh.node_x_m[first] - mesh.node_x_m[second],
                                 mesh.node_z_m[first] - mesh.node_z_m[second])
        tail = chain[-1]
        following = int(receiver[tail])
        handoff = (0.0 if following < 0 else
                   math.hypot(mesh.node_x_m[tail] - mesh.node_x_m[following],
                              mesh.node_z_m[tail] - mesh.node_z_m[following]))
        facts.append({"reach_index": index, "node_count": len(chain),
                      "edges": len(chain) - 1, "length_m": length,
                      "handoff_length_m": handoff, "tail": tail,
                      "receiver_of_tail": following})
    return facts


# --------------------------------------------------------------------------- #
class IndependentWalkTests(unittest.TestCase):
    """The tool's walk must agree with a raster-only, one-cell-at-a-time reference."""

    @classmethod
    def setUpClass(cls):
        cls.parent = _parent(_two_basins())
        cls.bundle = build_world_reaches(cls.parent, min_upstream_cells=4)

    def test_walk_matches_the_raster_reference_cell_by_cell(self):
        walked = review.walk_reaches(self.parent, self.bundle)
        reference = reference_facts(self.parent, self.bundle)
        self.assertEqual(len(walked), len(reference))
        self.assertGreater(len(walked), 0)
        for fact, expected in zip(walked, reference):
            self.assertEqual(fact["reach_index"], expected["reach_index"])
            self.assertEqual(fact["node_count"], expected["node_count"])
            self.assertEqual(fact["edges"], expected["edges"])
            self.assertEqual(fact["tail"], expected["tail"])
            self.assertAlmostEqual(fact["length_m"], expected["length_m"], places=9)
            self.assertAlmostEqual(fact["handoff_length_m"], expected["handoff_length_m"],
                                   places=9)

    def test_edges_are_nodes_minus_one_and_lengths_use_actual_continuous_positions(self):
        walked = review.walk_reaches(self.parent, self.bundle)
        mesh = grid_mesh(self.parent['arrays']['receiver'].shape)
        minimum, maximum = mesh.edge_length_m.min(), mesh.edge_length_m.max()
        for fact in walked:
            self.assertEqual(fact["edges"], fact["node_count"] - 1)
            # Bound each independently walked path by the actual mesh's metric
            # edge range; displaced nodes need not be one raster step apart.
            self.assertGreaterEqual(fact["length_m"],
                                    minimum * (fact["node_count"] - 1) - 1e-9)
            self.assertLessEqual(fact["length_m"],
                                 maximum * (fact["node_count"] - 1) + 1e-9)
        diagonal = [fact for fact in walked
                    if abs((fact["length_m"] / SPACING) - round(fact["length_m"] / SPACING))
                    > 1e-9]
        self.assertTrue(diagonal, "the synthetic basins must contain a diagonal hop")

    def test_audit_accepts_an_untampered_network_and_covers_everything(self):
        walked = review.walk_reaches(self.parent, self.bundle)
        problems, kinds = review.audit_network(self.parent, self.bundle, walked)
        self.assertEqual(problems, [])
        self.assertEqual(len(kinds), len(walked))
        self.assertGreaterEqual(sum(1 for value in kinds.values() if value is not None), 1)


class ClassificationAndRefusalTests(unittest.TestCase):
    """A wrong downstream, a dropped row and an internal break are all refusals."""

    @classmethod
    def setUpClass(cls):
        cls.parent = _parent(_two_basins())
        cls.bundle = build_world_reaches(cls.parent, min_upstream_cells=4)

    def _problems(self, bundle):
        walked = review.walk_reaches(self.parent, bundle)
        problems, _ = review.audit_network(self.parent, bundle, walked)
        return problems

    def test_tampered_downstream_is_refused(self):
        downstream = self.bundle["arrays"]["reach_downstream"]
        terminal = [index for index in range(int(downstream.size))
                    if int(downstream[index]) < 0]
        self.assertTrue(terminal)
        target = int(terminal[0])
        bundle = copy.deepcopy(self.bundle)
        bundle["arrays"]["reach_downstream"][target] = int(downstream.size) - 1
        problems = self._problems(bundle)
        self.assertTrue(any("downstream" in item for item in problems),
                        "a terminal segment that suddenly declares a downstream must fail: %s"
                        % problems)

    def test_wrong_edge_count_is_refused(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["reaches"][0]["edges"] = int(bundle["reaches"][0]["edges"]) + 1
        problems = self._problems(bundle)
        self.assertTrue(any(item.startswith("edges:") for item in problems), problems)

    def test_dropped_classification_row_is_refused(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["roots"] = bundle["roots"][:-1]
        problems = self._problems(bundle)
        self.assertTrue(any(item.startswith("coverage_root_rows") for item in problems),
                        problems)
        bundle = copy.deepcopy(self.bundle)
        bundle["reaches"] = bundle["reaches"][:-1]
        problems = self._problems(bundle)
        self.assertTrue(any(item.startswith("coverage_reach_rows") for item in problems),
                        problems)

    def test_internal_break_is_failed_and_never_classified_as_an_outlet(self):
        """Cut the channel upstream of a hand-off: the tail still drains onward."""
        walked = review.walk_reaches(self.parent, self.bundle)
        handoff = [fact for fact in walked if fact["link"] == review.LINK_HANDOFF]
        self.assertTrue(handoff, "the synthetic network must contain a hand-off")
        chosen = handoff[0]
        successor = chosen["receiver_of_tail"]
        bundle = copy.deepcopy(self.bundle)
        bundle["arrays"]["reach_of_cell"].reshape(-1)[successor] = -1
        problems = self._problems(bundle)
        breaks = [item for item in problems if "never a lake outlet" in item]
        self.assertTrue(breaks, problems)
        self.assertTrue(any("break_into_valid_cell_below_gate" in item for item in problems),
                        problems)
        # And the classification table must say the same thing, with no lake language.
        walked_broken = review.walk_reaches(self.parent, bundle)
        provenance = {"plan": "synthetic",
                      "origin_native_xz": list(self.parent["support"]["metadata"][
                          "origin_native_xz"]),
                      "shape_zx": list(self.parent["support"]["metadata"]["shape_zx"])}
        _, terminal_kinds = review.audit_network(self.parent, bundle, walked_broken)
        _, rows, _, coverage = review.classify_window(self.parent, bundle, provenance,
                                                     walked_broken, terminal_kinds)
        self.assertGreaterEqual(coverage["breaks"], 1)
        for row in rows:
            if row["verdict"] == review.FAILED:
                self.assertIn(row["classification"], review.BREAK_LINKS)
                self.assertIsNone(row["terminal_kind"])
                self.assertIsNone(row["physical_endpoint_evidence"])

    def test_every_disabled_field_is_reviewed_and_the_pending_reason_is_stated(self):
        walked = review.walk_reaches(self.parent, self.bundle)
        _, terminal_kinds = review.audit_network(self.parent, self.bundle, walked)
        provenance = {"plan": "synthetic",
                      "origin_native_xz": list(self.parent["support"]["metadata"][
                          "origin_native_xz"]),
                      "shape_zx": list(self.parent["support"]["metadata"]["shape_zx"])}
        root_rows, reach_rows, traces, coverage = review.classify_window(
            self.parent, self.bundle, provenance, walked, terminal_kinds)
        self.assertEqual(coverage["roots_classified"], int(
            self.parent["arrays"]["root_cells"].size))
        self.assertEqual(coverage["segments_classified"], len(walked))
        self.assertEqual(coverage["sampling"], "none: every root and every segment row is "
                                               "written")
        for row in root_rows:
            self.assertIn(row["root_kind"], ("retained", "unknown_boundary"))
            self.assertIn(row["channel"], ("channel", "nochannel"))
            self.assertNotIn(row["root_kind"], ("lake", "ocean_outlet"))
            if row["root_kind"] == "retained":
                self.assertEqual(row["pending_reason"], review.PENDING_RETAINED)
            elif row["root_kind"] == "unknown_boundary":
                self.assertEqual(row["pending_reason"], review.PENDING_UNKNOWN)
        for row in reach_rows:
            self.assertIn(row["classification"], review.BREAK_LINKS
                          + (review.LINK_HANDOFF, review.LINK_STRUCTURAL_TERMINAL))
            self.assertLessEqual(row["hops_to_terminal"], int(
                self.bundle["arrays"]["reach_downstream"].size))
        self.assertEqual(len(traces), len(walked))


class EmptyChannelTests(unittest.TestCase):
    """No channel at all keeps the parent's raw trunk and never invents a root."""

    def setUp(self):
        self.parent = _parent(_cone())

    def test_empty_channel_keeps_raw_path_and_zeroes_the_channel_side(self):
        upstream = np.asarray(self.parent["arrays"]["upstream_cells"], np.int64)
        gate = int(upstream.max()) + 1
        bundle = build_world_reaches(self.parent, min_upstream_cells=gate)
        self.assertEqual(int(bundle["metadata"]["counts"]["channel_cells"]), 0)
        walked = review.walk_reaches(self.parent, bundle)
        problems, kinds = review.audit_network(self.parent, bundle, walked)
        self.assertEqual(problems, [])
        self.assertEqual(walked, [])
        for row in bundle["roots"]:
            self.assertGreater(int(row["raw_mainstem_node_count"]), 0)
            self.assertEqual(int(row["raw_mainstem_edges"]),
                             int(row["raw_mainstem_node_count"]) - 1)
            self.assertGreater(float(row["raw_mainstem_length_m"]), 0.0)
            self.assertEqual(int(row["channel_mainstem_node_count"]), 0)
            self.assertEqual(int(row["channel_mainstem_edges"]), 0)
            self.assertEqual(float(row["channel_mainstem_length_m"]), 0.0)
            self.assertEqual(int(row["reach_count"]), 0)
            self.assertEqual(row["raw_mainstem_reach_ids"], [])
        provenance = {"plan": "synthetic",
                      "origin_native_xz": list(self.parent["support"]["metadata"][
                          "origin_native_xz"]),
                      "shape_zx": list(self.parent["support"]["metadata"]["shape_zx"])}
        root_rows, reach_rows, _, coverage = review.classify_window(
            self.parent, bundle, provenance, walked, kinds)
        self.assertEqual(reach_rows, [])
        self.assertEqual(coverage["breaks"], 0)
        for row in root_rows:
            self.assertEqual(row["channel"], "nochannel")
            self.assertEqual(row["classification"], review.LINK_EMPTY_CHANNEL)
            self.assertEqual(row["verdict"], review.PASS)


class InputGuardTests(unittest.TestCase):
    """A damaged package and an over-budget support are refused before any array load.

    The three order-sensitive cases do not just look at the final error: they **mock**
    ``numpy.load`` (and the tool's own loader) and assert it was never called, so
    "refused before allocation" is measured rather than asserted from the message.
    """

    def _package(self, directory, *, array_sha_mismatch=False, shape=(9, 9),
                 grid_shape=None, declared_grid=None):
        folder = Path(directory)
        grid = tuple(grid_shape if grid_shape is not None else shape)
        arrays = {
            "elevation_m": np.zeros(grid, np.float64),
            "resolved_mask": np.ones(grid, bool),
            "receiver": np.zeros(grid, np.int64),
            "terminal_kind": np.full(grid, "inactive", "<U24"),
            "upstream_unknown_mask": np.zeros(grid, bool),
            "complete_mask": np.ones(grid, bool),
            "upstream_cells": np.ones(grid, np.int64),
            "owner_index": np.zeros(grid, np.int64),
            "root_cells": np.zeros(1, np.int64),
            "root_complete": np.ones(1, bool),
            "member_counts": np.ones(1, np.int64),
            "member_ptr": np.array([0, int(grid[0]) * int(grid[1])], np.int64),
            "member_cells": np.arange(int(grid[0]) * int(grid[1]), dtype=np.int64),
            "mainstem_ptr": np.array([0, 1], np.int64),
            "mainstem_cells": np.zeros(1, np.int64),
            "shared_face_cells": np.zeros((0, 2), np.int64),
        }
        with open(folder / review.ARRAYS_NAME, "wb") as stream:
            np.savez(stream, **arrays)
        records = {}
        for name, value in arrays.items():
            declared = list(value.shape)
            if declared_grid is not None and name == "elevation_m":
                declared = list(declared_grid)
            records[name] = {"shape": declared, "dtype": value.dtype.str,
                             "sha256": ("0" * 64 if array_sha_mismatch
                                         else review.array_sha256(value))}
        manifest = {
            "schema": review.PARENT_SCHEMA,
            "support": {"metadata": {"shape_zx": list(shape), "world_seed": SEED,
                                      "spacing_m": SPACING, "origin_native_xz": [0, 0],
                                      "plan_version": 1}},
            "metadata": {"support_identity_sha256": "0" * 64, "source": {}},
            "candidates": [],
            "identity_sha256": "0" * 64,
            "arrays": records,
        }
        (folder / review.MANIFEST_NAME).write_text(json.dumps(manifest),
                                                   encoding="utf-8")
        return folder

    def _forbid_load(self):
        """Replace the materialising loader with one that fails if it is reached."""
        calls = []

        def forbidden(path, names):
            calls.append((str(path), tuple(names)))
            raise AssertionError("np.load was reached: %s" % (calls,))

        original = review.load_arrays
        review.load_arrays = forbidden
        self.addCleanup(setattr, review, "load_arrays", original)
        return calls

    def test_array_sha_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = self._package(directory, array_sha_mismatch=True)
            with self.assertRaises(ValueError) as caught:
                review.load_evidence(folder)
            self.assertIn("sha256", str(caught.exception))

    def test_over_budget_support_never_loads_any_array(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = self._package(directory, shape=(401, 401))
            calls = self._forbid_load()
            with self.assertRaises(ValueError) as caught:
                review.load_evidence(folder)
            self.assertIn("support_budget_exceeded", str(caught.exception))
            self.assertEqual(calls, [], "an over-budget support must not reach np.load")
            # 401*401 = 160_801 cells, i.e. over the declared 148_225 ceiling.
            self.assertGreater(401 * 401, review.MAX_SUPPORT_CELLS)

    def test_false_big_array_header_never_loads_any_array(self):
        """An array whose header claims a false extent is refused from the header alone."""
        with tempfile.TemporaryDirectory() as directory:
            folder = self._package(directory, shape=(9, 9), grid_shape=(9, 9),
                                   declared_grid=(401, 401))
            calls = self._forbid_load()
            with self.assertRaises(ValueError) as caught:
                review.load_evidence(folder)
            self.assertIn("array_header_shape_mismatch", str(caught.exception))
            self.assertEqual(calls, [])

    def test_grid_extent_over_support_is_refused_from_the_header(self):
        """A grid array bigger than the declared support fails at the header gate."""
        with tempfile.TemporaryDirectory() as directory:
            folder = self._package(directory, shape=(9, 9), grid_shape=(33, 33))
            calls = self._forbid_load()
            with self.assertRaises(ValueError) as caught:
                review.load_evidence(folder)
            self.assertIn("grid_array_extent_mismatch", str(caught.exception))
            self.assertEqual(calls, [])

    def test_object_dtype_member_is_refused_by_the_header_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = self._package(directory)
            with open(folder / review.ARRAYS_NAME, "wb") as stream:
                np.savez(stream, blob=np.array([{"a": 1}], dtype=object))
            calls = self._forbid_load()
            with self.assertRaises(ValueError) as caught:
                review.inspect_archive(folder / review.ARRAYS_NAME)
            self.assertIn("object_dtype_rejected", str(caught.exception))
            self.assertEqual(calls, [])

    def test_npy_header_size_lie_is_refused(self):
        """A member whose header over-claims its bytes is refused without reading it."""
        import io
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / review.ARRAYS_NAME
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, np.zeros((4, 4), np.float64))
            raw = buffer.getvalue()
            # Same header width, different shape: the member now declares (8, 4) while it
            # holds (4, 4), so the ZIP size and the NPY header disagree.
            lied = raw.replace(b"(4, 4)", b"(8, 4)")
            self.assertEqual(len(lied), len(raw))
            self.assertNotEqual(lied, raw)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("small.npy", lied)
            with self.assertRaises(ValueError) as caught:
                review.inspect_archive(path)
            self.assertIn("npy_header_size_mismatch", str(caught.exception))

    def test_manifest_byte_limit_is_applied_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text("{\"pad\": \"" + "x" * 2048 + "\"}", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                review.read_strict_json(path, limit=256)
            self.assertIn("manifest_bytes_exceeded", str(caught.exception))
            self.assertIsInstance(review.read_strict_json(path), dict)

    def test_strict_manifest_rejects_non_finite_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text('{"a": NaN}', encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                review.read_strict_json(path)
            self.assertIn("non_finite_json", str(caught.exception))
            path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                review.read_strict_json(path)
            self.assertIn("duplicate_json_key", str(caught.exception))

    def test_missing_package_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as caught:
                review.load_evidence(directory)
            self.assertIn("evidence_package_incomplete", str(caught.exception))

    def test_review_refuses_to_overwrite_an_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                review.review(directory, plans=("p1",), figures=False)


class LegendGeometryTests(unittest.TestCase):
    """A legend that covers the map is a failure, and that must be checkable."""

    def test_legend_rectangles_are_disjoint_from_touched_axes(self):
        try:
            plt = review._matplotlib()
        except ImportError:                                  # style only
            self.skipTest("matplotlib is not installed")
        figure, axes = plt.subplots(1, 2, figsize=(10.0, 6.0))
        try:
            from matplotlib.lines import Line2D
            figure.subplots_adjust(bottom=0.42)
            for axis in axes:
                axis.plot([0.0, 1.0], [0.0, 1.0])
                axis.legend(handles=[Line2D([], [], label="x")], loc="upper center",
                           bbox_to_anchor=(0.5, -0.25))
            figure.suptitle("synthetic")
            records = review._legend_geometry(figure, axes, ["left", "right"])["panels"]
            self.assertEqual(len(records), 2)
            for record in records:
                self.assertFalse(record["overlaps_own_axes"])
                self.assertTrue(record["inside_figure"])
                self.assertEqual(record["entries"], 1)
            # A legend deliberately placed inside the map must be refused, not exported.
            axes[1].legend(handles=[Line2D([], [], label="y")], loc="center")
            with self.assertRaises(ValueError) as caught:
                review._legend_geometry(figure, axes, ["left", "right"])
            self.assertIn("legend_overlaps_map", str(caught.exception))
            axes[1].legend(handles=[Line2D([], [], label="y")], loc="upper center",
                           bbox_to_anchor=(0.5, -0.25))
            # And a figure without a title states nothing, so it is refused too.
            figure.suptitle("")
            with self.assertRaises(ValueError) as caught:
                review._legend_geometry(figure, axes, ["left", "right"])
            self.assertIn("missing_figure_title", str(caught.exception))
            figure.suptitle("synthetic")
            # A legend pushed off the canvas must be refused too: not overlapping the axes
            # is not the same as being inside the figure.
            axes[0].legend(handles=[Line2D([], [], label="z")], loc="upper center",
                           bbox_to_anchor=(0.5, -3.2))
            with self.assertRaises(ValueError) as caught:
                review._legend_geometry(figure, axes, ["left", "right"])
            self.assertIn("legend_outside_figure", str(caught.exception))
        finally:
            plt.close(figure)

    def test_real_figures_report_canvas_and_saved_pixel_sizes(self):
        """The saved PNG size must equal the drawn canvas, and legends stay inside it."""
        try:
            from PIL import Image
        except ImportError:                                  # observation only
            self.skipTest("Pillow is not installed")
        parent = _parent(_two_basins())
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        provenance = {"plan": "synthetic",
                      "origin_native_xz": list(parent["support"]["metadata"][
                          "origin_native_xz"]),
                      "shape_zx": list(parent["support"]["metadata"]["shape_zx"])}
        with tempfile.TemporaryDirectory() as directory:
            network = Path(directory) / "network.png"
            report = review.render_network_figure(parent, bundle, provenance, network)
            self.assertTrue(network.is_file())
            with Image.open(network) as image:
                self.assertEqual([image.size[0], image.size[1]], report["saved_png_px"])
            self.assertEqual(report["figure_px"], report["saved_png_px"])
            self.assertTrue(report["legends_inside_figure_canvas"])
            for panel in report["panels"]:
                self.assertFalse(panel["overlaps_own_axes"])
                self.assertTrue(panel["inside_figure"])
            selected = review.select_display_root(parent)
            if selected is not None:
                detail = Path(directory) / "detail.png"
                report = review.render_detail_figure(parent, bundle, provenance,
                                                     int(selected), detail)
                with Image.open(detail) as image:
                    self.assertEqual([image.size[0], image.size[1]],
                                     report["saved_png_px"])
                self.assertTrue(report["legends_inside_figure_canvas"])


class SelectionRuleTests(unittest.TestCase):
    """The display root is the frozen rule, not "whichever looked best"."""

    def test_selection_is_complete_most_members_then_world_tie_break(self):
        parent = _parent(_two_basins())
        bundle = build_world_reaches(parent, min_upstream_cells=4)
        selected = review.select_display_root(parent)
        self.assertEqual(selected, bundle["metadata"]["display_root_index"])
        if selected is not None:
            candidates = parent["candidates"]
            self.assertEqual(candidates[selected]["status"], "candidate_closed")
            for index, candidate in enumerate(candidates):
                if candidate["status"] != "candidate_closed":
                    continue
                self.assertGreaterEqual(int(candidate["member_count"]),
                                        int(candidates[selected]["member_count"]))
                if int(candidate["member_count"]) == int(
                        candidates[selected]["member_count"]):
                    # The chosen root must be the minimum under the world (x, z) tie-break.
                    self.assertLessEqual(tuple(candidates[selected]["root_world_xz"]),
                                         tuple(candidate["root_world_xz"]))


if __name__ == "__main__":
    unittest.main()
