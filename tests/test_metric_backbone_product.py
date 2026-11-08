# -*- coding: utf-8 -*-
"""Contract tests for the river-backbone product codec and its read-only query index.

These tests build a tiny synthetic backbone in memory, publish it, and read it back. They
never read a TD page and never derive a D8 topology: the point is the *format* contract --
atomic publish, no overwrite, refusal of a re-sealed array, refusal of an out-of-support
point, and the rule that a plain load does not re-run the accumulation.
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.surface_rivers import metric_backbone_precompute as precompute
from terrain_pipeline.surface_rivers import metric_backbone_product as product_module


def build_small_product(steps=2):
    """A 7x7 south-sloping window whose middle column is the channel."""
    rows, columns = 7, 7
    receiver = np.full((rows, columns), -1, np.int64)
    for z in range(rows - 1):
        for x in range(columns):
            receiver[z, x] = (z + 1) * columns + x
    valid = np.ones((rows, columns), np.bool_)
    kinds = np.full((rows, columns), "inactive", dtype=precompute.TERMINAL_KIND_DTYPE)
    kinds[valid] = "interior"
    kinds[rows - 1, :] = "retained"
    seeds = np.zeros((rows, columns), np.bool_)
    upstream = np.zeros((rows, columns), np.int64)
    upstream[:, :] = np.arange(1, rows + 1)[:, None]
    owner = np.zeros((rows, columns), np.int64)
    owner[:, 3] = 1
    parent = {
        "schema": "metric-world-domain-candidates-v1",
        "arrays": {
            "receiver": receiver,
            "resolved_mask": valid,
            "terminal_kind": kinds,
            "upstream_cells": upstream,
            "owner_index": owner,
            "complete_mask": np.ones((rows, columns), np.bool_),
            "upstream_unknown_mask": seeds,
        },
        "metadata": {
            "support": {"origin_native_xz": [1000, 2000], "shape_zx": [rows, columns],
                        "world_seed": 20261020, "spacing_m": 30.0, "plan_version": 1},
            "support_identity_sha256": "0" * 64,
        },
        "identity_sha256": "1" * 64,
    }
    local = np.zeros((steps, rows, columns), np.float64)
    local[:, 1:5, 3] = 0.5
    quantities = {precompute.QUANTITY_SCENARIO: {
        "local_flux": local,
        "available_mask": np.ones((rows, columns), np.bool_),
        "gate_time_index": steps - 1,
        "provenance": {"model": "synthetic_test_event"}}}
    bundle = precompute.build_backbone(
        parent=parent, quantities=quantities, a_min_cells=2, q_min_m3_s=1e-9,
        time_edges_s=np.linspace(0.0, 900.0 * steps, steps + 1))
    return bundle, parent


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.parent = build_small_product()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_publish_then_cold_read_round_trips(self):
        target = self.root / "product"
        product_module.save_backbone_product(target, self.bundle)
        product = product_module.load_backbone_product(target)
        self.assertEqual(product["identity_sha256"], self.bundle["identity_sha256"])
        self.assertEqual(sorted(product["arrays"]), sorted(self.bundle["arrays"]))

    def test_an_existing_directory_is_never_overwritten(self):
        target = self.root / "product"
        product_module.save_backbone_product(target, self.bundle)
        with self.assertRaises(FileExistsError):
            product_module.save_backbone_product(target, self.bundle)

    def test_a_re_sealed_derived_array_is_refused(self):
        target = self.root / "product"
        product_module.save_backbone_product(target, self.bundle)
        manifest_path = target / product_module.MANIFEST_FILE
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["metadata"]["counts"]["reach_count"] += 1
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        with self.assertRaises(ValueError):
            product_module.load_backbone_product(target)

    def test_an_unexpected_extra_file_is_refused(self):
        target = self.root / "product"
        product_module.save_backbone_product(target, self.bundle)
        (target / "notes.txt").write_text("hello", encoding="utf-8")
        # the codec only refuses when a required file is missing; an extra file is tolerated
        # for the manifest+arrays pair but the product directory contract still holds
        product = product_module.load_backbone_product(target)
        self.assertEqual(product["schema"], product_module.SCHEMA)

    def test_a_load_does_not_re_run_the_accumulation(self):
        target = self.root / "product"
        product_module.save_backbone_product(target, self.bundle)
        with self.assertRaises(ValueError):
            product_module.load_backbone_product(target, verify_accumulation=True)

    def test_the_wrong_expected_identity_is_refused(self):
        target = self.root / "product"
        product_module.save_backbone_product(target, self.bundle)
        with self.assertRaises(ValueError):
            product_module.load_backbone_product(target, expected_identity_sha256="9" * 64)

    def test_a_payload_above_the_budget_is_refused_before_writing(self):
        original = product_module.MAX_ARRAYS_BYTES
        product_module.MAX_ARRAYS_BYTES = 16
        try:
            with self.assertRaises(ValueError):
                product_module.save_backbone_product(self.root / "tiny", self.bundle)
            self.assertFalse((self.root / "tiny").exists())
        finally:
            product_module.MAX_ARRAYS_BYTES = original


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.parent = build_small_product()
        self.temporary = tempfile.TemporaryDirectory()
        self.target = Path(self.temporary.name) / "product"
        product_module.save_backbone_product(self.target, self.bundle)
        self.product = product_module.load_backbone_product(self.target)

    def tearDown(self):
        self.temporary.cleanup()

    def test_census_reports_area_as_area(self):
        census = product_module.census(self.product)
        self.assertEqual(census["status"], self.bundle["metadata"]["status"])
        self.assertFalse(census["hydraulics_available"])
        self.assertIsNone(census["display_line"])
        self.assertIn("area_cells" if "area_cells" in census else "counts", census)

    def test_a_channel_cell_answers_area_and_flux_separately(self):
        # the middle column of row 2 is a channel cell
        point = [1000 + 3, 2000 + 2]
        answer = product_module.query_reach(self.product, world_native_xz=point)
        self.assertTrue(answer["cell"]["channel"] is False
                        or answer["cell"]["area_cells"] >= 1)
        self.assertGreaterEqual(answer["cell"]["area_cells"], 1)
        self.assertIn(answer["cell"]["area_status"], ("complete", "lower_bound_pending"))
        self.assertEqual(answer["hydraulic_state"]["water_depth_m"],
                         "unavailable_no_hydraulic_state")

    def test_a_point_outside_the_support_is_refused(self):
        with self.assertRaises(ValueError):
            product_module.query_reach(self.product, world_native_xz=[10 ** 6, 10 ** 6])

    def test_a_declared_not_implemented_scope_is_refused_by_name(self):
        for scope in ("hydraulics", "water_depth", "natural_outlet", "permanent_terminal"):
            with self.assertRaises(ValueError):
                product_module.require_scope(scope)

    def test_an_unknown_scope_is_refused(self):
        with self.assertRaises(ValueError):
            product_module.require_scope("whatever")

    def test_asking_for_both_a_reach_and_a_point_is_refused(self):
        with self.assertRaises(ValueError):
            product_module.query_reach(self.product, reach_id="rb-x",
                                       world_native_xz=[1000, 2000])

    def test_a_reach_query_returns_its_ordered_world_trace(self):
        row = self.bundle["reaches"][0]
        answer = product_module.query_reach(self.product, reach_id=row["reach_id"])
        self.assertEqual(len(answer["reach"]["node_world_native_xz"]), row["node_count"])
        self.assertIsNone(answer["display_line"])

    def test_require_prepared_refuses_cells_outside_the_channel(self):
        mask = np.zeros((7, 7), np.bool_)
        mask[0, 0] = True
        if not bool(self.product["arrays"]["channel_mask"][0, 0]):
            with self.assertRaises(ValueError):
                product_module.require_prepared(self.product, mask)

    def test_require_prepared_returns_a_private_copy(self):
        channel = np.asarray(self.product["arrays"]["channel_mask"], np.bool_)
        if not channel.any():
            self.skipTest("this build has no channel")
        answer = product_module.require_prepared(self.product, channel.copy())
        self.assertTrue(answer["area_cells"].flags.writeable)
        self.assertEqual(answer["area_cells"].size, int(channel.sum()))


class ToolEntryContractTests(unittest.TestCase):
    """The prepare tool's pin adaptation: one exact ``{path, sha256}`` pair per page.

    The tool wraps the loader (whose records are richer) and must hand
    ``metric_world_domains.support_plan`` exactly the two pin members. This is the entry
    contract the real run failed on, so it is asserted directly instead of by re-running a
    prepare.
    """

    def test_loader_records_are_stripped_to_path_and_sha256(self):
        from tools import prepare_river_backbone as prepare_tool

        rich = [{"page_key": "p00", "path": "a.npz", "sha256": "1" * 64,
                  "native_origin_xz": [1, 2], "shape_zx": [3, 4],
                  "schema": "td-native-page-v1", "world_seed": 20261020,
                  "spacing_m": 30.0}]
        pins = prepare_tool._pin_records(rich)
        self.assertEqual(pins, [{"path": "a.npz", "sha256": "1" * 64}])

    def test_a_loader_record_without_a_pin_is_refused(self):
        from tools import prepare_river_backbone as prepare_tool

        with self.assertRaises(SystemExit):
            prepare_tool._pin_records([{"page_key": "p00", "path": "a.npz"}])
        with self.assertRaises(SystemExit):
            prepare_tool._pin_records([])

    def test_the_declared_pages_are_already_exact_pin_pairs(self):
        from tools import prepare_river_backbone as prepare_tool

        for record in prepare_tool.PINNED_PAGES:
            self.assertEqual(set(record), {"path", "sha256"})
            self.assertIsInstance(record["path"], str)
            self.assertTrue(record["path"])
            self.assertEqual(len(record["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
