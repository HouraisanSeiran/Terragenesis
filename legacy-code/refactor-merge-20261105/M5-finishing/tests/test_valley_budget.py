import unittest
import numpy as np

from terrain_pipeline.channel_geometry import ValleyRecipe, allocate_valley_budget, plan_recovery
from tests.test_channel_stage_inundation import confluence_plan


class ValleyBudgetTests(unittest.TestCase):
    def test_allocator_preserves_source_and_respects_protection(self):
        plan = confluence_plan()
        source = plan["arrays"]["source_height_m"].copy()
        protected = np.zeros(source.shape, bool)
        protected[3, 3] = True
        result = allocate_valley_budget(plan, protected, {"pass": False},
                                        ValleyRecipe(total_area_cells=2, valley_cut_m=8., bed_cut_m=4.))
        self.assertTrue(result["summary"]["inherited_joint_blocker"])
        self.assertLessEqual(result["summary"]["selected_nodes"], 2)
        self.assertEqual(result["arrays"]["valley_allocation_m"][3, 3], 0.)
        np.testing.assert_array_equal(plan["arrays"]["source_height_m"], source)

    def test_recovery_selector_has_explicit_failure_fallback(self):
        blockers = {"stage": True, "plan": True}
        plan = confluence_plan()
        result = plan_recovery(plan, blockers,
                               candidate_routes=[{"id": "blocked", "crosses_protection": True,
                                                  "plan_identity_sha256": plan["identity_sha256"]},
                                                 {"id": "open", "crosses_protection": False,
                                                  "plan_identity_sha256": plan["identity_sha256"]}],
                               lake_spills=[{"id": "unlegal", "legal_outlet": False,
                                             "plan_identity_sha256": plan["identity_sha256"]}])
        self.assertEqual(result["chosen"]["kind"], "reroute")
        self.assertEqual(result["chosen"]["candidate"]["id"], "open")
        failed = plan_recovery(plan, blockers, lake_spills=[{"id": "x", "legal_outlet": False,
                                                             "plan_identity_sha256": plan["identity_sha256"]}])
        self.assertEqual(failed["chosen"]["kind"], "failure")

    def test_invalid_recipe_rejected(self):
        with self.assertRaises(ValueError):
            ValleyRecipe(total_area_cells=0)


if __name__ == "__main__":
    unittest.main()
