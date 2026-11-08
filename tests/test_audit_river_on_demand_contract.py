"""Tests for the on-demand consistency auditor's CONTRACT engine.

The contract engine measures the world-anchored closure contract itself
(`metric_domain_closure` world tiles) rather than the frozen bounded planner.
It exists because the frozen planner's coverage/ocean window dependence is a
property of that frozen product, not a defect of the contract, so the contract
needs an engine that can express it.

The gate this locks: where two anchorings both ANSWER (neither declined), they
must never disagree. A point only one side answers is honest refusal.
"""
import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    ClosureRegion, clear_cache,
)
from tools.audit_river_on_demand_consistency import (
    audit_contract, compare_tile_pair, contract_fields, reason_counts,
)

SEED = 20261020


class ContractEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = PlanningConfig()
        cls.spacing_m = cls.config.macro_span_m / cls.config.samples_per_span

    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_reason_counts_is_a_fixed_vocabulary(self):
        """A new reason cannot hide: it keeps its own key, never a zero slot."""
        tally = reason_counts(np.array(["ocean", "ocean", "new_label"], dtype=object))
        self.assertEqual(tally["ocean"], 2)
        self.assertEqual(tally["coastal"], 0)
        self.assertEqual(tally["new_label"], 1)
        self.assertEqual(tally["unresolved_border"], 0)
        # The known vocabulary keeps a fixed slot; an unknown label is appended
        # rather than folded into one of them.
        for name in ("ocean", "coastal", "closed_basin", "unresolved_border", "out_of_tile"):
            self.assertIn(name, tally)
        self.assertEqual(sum(tally.values()), 3)

    def test_contract_engine_core_is_fully_answered(self):
        """The built margin must be wide enough that no core cell is refused."""
        record = audit_contract(SEED, 1, config=self.config, step=6)
        self.assertEqual(record["schema"], "river-on-demand-contract-v1")
        self.assertTrue(record["tile_rebuild_is_bit_identical"])
        self.assertEqual(record["core"]["worst_core_refused"], 0)
        self.assertEqual(record["core"]["total_core_refused"], 0)
        self.assertGreater(record["core"]["reason_totals"]["ocean"], 0)
        self.assertGreater(record["core"]["reason_totals"]["coastal"], 0)

    def test_confident_anchorings_never_disagree(self):
        """Where both anchorings answer, outlet and ocean are identical.

        This is the contract's core promise: outlet and ocean are pure functions
        of the world coordinate. Two anchorings may only differ by one of them
        declining (honest refusal), never by both asserting different worlds.
        """
        record = audit_contract(SEED, 1, config=self.config, step=2)
        self.assertGreater(record["adjacent_tile_pairs"], 0)
        contract = record["contract"]
        self.assertEqual(contract["outlet_disagreement_pairs"], 0)
        self.assertEqual(contract["confident_ocean_mismatch_points"], 0)
        self.assertEqual(contract["confident_reason_mismatch_points"], 0)
        self.assertEqual(contract["dominant_reason_conflict_points"], 0)
        self.assertGreater(contract["outlet_both_answered_points"], 0)

    def test_load_order_does_not_change_a_single_bit(self):
        """p3.3: shuffled tile builds and shuffled point queries answer identically.

        The module caches tiles by key, so an order dependence would show up as a
        cache effect. Building the same tiles in a shuffled order and answering the
        same points in a shuffled order must be bit-identical to the sorted run.
        """
        record = audit_contract(SEED, 1, config=self.config, step=6)
        load_order = record["load_order"]
        self.assertGreater(load_order["tiles_compared"], 0)
        self.assertGreater(load_order["points_compared"], 0)
        self.assertEqual(load_order["tile_order_mismatches"], 0)
        self.assertEqual(load_order["point_order_mismatches"], 0)

    def test_a_declining_anchoring_is_not_a_conflict(self):
        """A one-sided refusal must be reported as refusal, not as disagreement."""
        left = ClosureRegion(SEED, self.config, 0, 0)
        right = ClosureRegion(SEED, self.config, 0, 1)
        record = compare_tile_pair(left, right, (0, 0), (0, 1), self.spacing_m, step=2)
        self.assertTrue(record["comparable"])
        # A confident mismatch means neither side declined there; a one-sided
        # refusal is honest refusal and is counted separately.
        self.assertEqual(record["confident_ocean_mismatches"], 0)
        self.assertEqual(record["confident_reason_mismatches"], 0)
        self.assertGreater(record["shared_points"], 0)

    def test_contract_fields_marks_a_sea_cell_as_ocean_without_outlet(self):
        """A sea cell is resolved yet carries no outlet of its own."""
        region = ClosureRegion(SEED, self.config, 0, 0)
        margin, core = region.margin, region.core_cells
        rows, columns = np.meshgrid(np.arange(margin, margin + core + 1, 3),
                                    np.arange(margin, margin + core + 1, 3), indexing="ij")
        xs = region.origin_x_m + columns.reshape(-1) * self.spacing_m
        zs = region.origin_z_m + rows.reshape(-1) * self.spacing_m
        reason, outlet_x, outlet_z, ocean = contract_fields(region, xs, zs)
        sea = reason == "ocean"
        self.assertGreater(int(sea.sum()), 0)
        self.assertTrue(bool(ocean[sea].all()))
        self.assertFalse(bool(np.isfinite(outlet_x[sea]).any()),
                         "a sea cell must not carry an outlet")
        land = (reason == "coastal") | (reason == "closed_basin")
        self.assertTrue(bool(np.isfinite(outlet_x[land]).all()), "a land cell must carry its outlet")


if __name__ == "__main__":
    unittest.main()
