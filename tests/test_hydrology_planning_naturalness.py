import unittest

import numpy as np

from tools.audit_hydrology_planning_naturalness import audit_plan


class PlanningNaturalnessTests(unittest.TestCase):
    def test_equal_order_merger_is_not_tokunaga_side_branch(self):
        height = np.array([[9., 8., 7.], [6., 5., 4.], [3., 2., 1.]])
        receiver = np.full((3, 3), -1, np.int64)
        receiver.ravel()[[0, 2, 4, 6]] = [4, 4, 7, 7]
        mask = np.zeros((3, 3), bool)
        mask.ravel()[[0, 2, 4, 6, 7]] = True
        plan = {"height_m": height, "receiver": receiver, "owner_domain_id": np.zeros((3, 3), np.int32),
                "river_mask": mask, "spacing_m": 10., "seed": 3, "macro_cell": [0, -5],
                "identity_sha256": "fixture", "algorithm_version": "fixture", "source": {},
                "domains": [{"domain_id": 0, "kind": "inland", "terminal_indices": [7], "lake_terminal_index": 7}],
                "catchments": [{}]}
        record = audit_plan(plan)
        self.assertEqual(record["maximum_strahler_order"], 2)
        self.assertEqual(record["strahler_branch_counts"], {"1": 3, "2": 1})
        self.assertEqual(record["tokunaga_order_pair_samples"], [{"lower_order": 1, "receiving_order": 2,
                         "side_branch_count": 1, "receiving_branch_count": 1, "ratio": 1.}])
        self.assertFalse(record["naturalness_certified"])

    def test_direction_length_includes_final_nonriver_terminal_edge(self):
        plan = {"height_m": np.array([[3., 2., 1.]]), "receiver": np.array([[1, 2, -1]]),
                "owner_domain_id": np.array([[0, 0, -1]]), "river_mask": np.array([[True, True, False]]),
                "spacing_m": 10., "seed": 3, "macro_cell": [0, -5], "identity_sha256": "fixture",
                "algorithm_version": "fixture", "source": {}, "domains": [], "catchments": []}
        record = audit_plan(plan)
        self.assertEqual(record["d8_direction_counts"], {"0,1": 2})
        self.assertEqual(record["river_receiver_edge_count"], 2)
        self.assertEqual(record["longest_same_direction_run_m"], 20.)
        self.assertEqual(record["strahler_branch_counts"], {"1": 1})


if __name__ == "__main__":
    unittest.main()
