from copy import deepcopy
import json
import unittest

from terrain_pipeline.td_lake_outlet_forest import build_outlet_forest


def edge(face_id, source, receiver, net=1.0):
    return {"face_id": face_id, "source_leaf_id": source,
            "receiver_leaf_id": receiver, "net_m3": net}


class OutletForestTests(unittest.TestCase):
    def test_diamond_exclusive_area_determinism_and_reachability(self):
        leaf_ids = [0, 1, 2, 3, 4, 5, 6]
        areas = [10., 20., 30., 40., 50., 60., 70.]
        edges = [edge(0, 3, 1, 2.), edge(1, 3, 2, 4.),
                 edge(2, 1, 0), edge(3, 2, 0), edge(4, 3, 5, 100.)]
        outlets = [{"leaf_id": 0, "cell_id": 8, "outflow_m3": 2.},
                   {"leaf_id": 0, "cell_id": 7, "outflow_m3": 3.},
                   {"leaf_id": 0, "cell_id": 6, "outflow_m3": 3.},
                   {"leaf_id": 5, "cell_id": 9, "outflow_m3": 9.},
                   {"leaf_id": 6, "cell_id": 10, "outflow_m3": 1.}]
        original = deepcopy((leaf_ids, areas, edges, outlets))
        result = build_outlet_forest(leaf_ids, areas, edges, outlets)
        records = {record["leaf_id"]: record for record in result["records"]}
        self.assertEqual(records[3]["parent_leaf_id"], 5)
        self.assertEqual(records[0]["root_boundary_cell_id"], 6)
        self.assertEqual(result["primary_component"]["leaf_ids"], [3, 5])
        self.assertEqual(result["primary_component"]["area_m2"], 100.)
        self.assertEqual(result["main_path"], [5, 3])
        self.assertEqual(result["main_path_face_ids"], [4])
        self.assertEqual(sum(component["area_m2"] for component in result["components"]), 230.)
        self.assertEqual(records[4]["reason"], "no_event_supported_route_to_export")
        self.assertEqual((leaf_ids, areas, edges, outlets), original)
        shuffled = build_outlet_forest(leaf_ids[::-1], areas[::-1], edges[::-1], outlets[::-1])
        self.assertEqual(result, shuffled)
        diamond = build_outlet_forest(leaf_ids, areas, edges[:-1] + [edge(6, 3, 2, 4.)], outlets[:3])
        diamond_records = {record["leaf_id"]: record for record in diamond["records"]}
        self.assertEqual(diamond_records[3]["parent_leaf_id"], 2)
        self.assertEqual(diamond_records[3]["parent_face_id"], 1)
        self.assertEqual(diamond_records[0]["supported_area_m2"], 100.)
        self.assertEqual(diamond["primary_component"]["area_m2"], 100.)
        self.assertEqual(diamond["main_path"], [0, 2, 3])
        self.assertEqual(diamond["main_path_face_ids"], [1, 3])
        root_tie = build_outlet_forest(leaf_ids, areas, edges + [edge(5, 1, 5, 100.)], outlets)
        self.assertEqual(root_tie["records"][1]["root_leaf_id"], 0)
        self.assertEqual(root_tie["records"][1]["parent_face_id"], 2)
        string_edges = [dict(selected, face_id=f"physical-face-{selected['face_id']}")
                        for selected in edges[:-1]]
        string_result = build_outlet_forest(leaf_ids, areas, string_edges, outlets[:3])
        self.assertEqual(string_result["main_path_face_ids"], ["physical-face-1", "physical-face-3"])
        self.assertEqual(string_result, build_outlet_forest(
            leaf_ids[::-1], areas[::-1], string_edges[::-1], outlets[:3][::-1]))
        json.dumps(result, allow_nan=False)

    def test_original_cycles_preserved_forest_acyclic_and_blocked_terminal(self):
        edges = [edge(0, 0, 1), edge(1, 1, 0), edge(2, 1, 2),
                 edge(3, 3, 4), edge(4, 4, 2)]
        outlets = [{"leaf_id": 2, "cell_id": 20, "outflow_m3": 1.},
                   {"leaf_id": 4, "cell_id": 40, "outflow_m3": 100.}]
        original = deepcopy((edges, outlets))
        result = build_outlet_forest(list(range(5)), [1., 2., 3., 4., 5.],
                                     edges, outlets, blocked_leaf_ids=[4])
        records = {record["leaf_id"]: record for record in result["records"]}
        self.assertEqual(result["graph_diagnostics"]["directed_edges"], edges)
        self.assertEqual(result["graph_diagnostics"]["cyclic_components"], [[0, 1]])
        self.assertEqual(result["graph_diagnostics"]["edge_count"], 5)
        self.assertEqual(result["primary_component"]["leaf_ids"], [0, 1, 2])
        self.assertEqual(result["primary_component"]["area_m2"], 6.)
        self.assertEqual(records[4]["reason"], "blocked")
        self.assertEqual(records[3]["reason"], "no_event_supported_route_to_export")
        self.assertEqual(records[4]["supported_area_m2"], 0.)
        self.assertEqual(result["main_path"], [2, 1, 0])
        self.assertEqual(result["main_path_face_ids"], [0, 2])
        for record in result["records"]:
            if record["parent_leaf_id"] is not None:
                parent = records[record["parent_leaf_id"]]
                self.assertEqual(parent["hops"], record["hops"] - 1)
                self.assertNotEqual(parent["leaf_id"], 4)
        for flag in ("permanent_trunk_ready", "hydraulic_ready", "natural_outlet_verified", "publishable"):
            self.assertFalse(result[flag])
        self.assertEqual((edges, outlets), original)
        invalid_edges = [edges + [edges[0]], [edge(9, 0, 0)], [edge(9, 0, 8)],
                         [edge(9, 0, 1, float("nan"))]]
        for invalid in invalid_edges:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                build_outlet_forest(list(range(5)), [1.] * 5, invalid, outlets)
        for invalid_areas in ([1., 2., 3., 4., 0.], [1., 2., 3., 4., float("inf")]):
            with self.subTest(areas=invalid_areas), self.assertRaises(ValueError):
                build_outlet_forest(list(range(5)), invalid_areas, edges, outlets)
        with self.assertRaises(ValueError):
            build_outlet_forest([0, 0], [1., 1.], [], [])
        with self.assertRaises(ValueError):
            build_outlet_forest([0], [1.], [], [{"leaf_id": 0, "cell_id": -1, "outflow_m3": 1.}])
        with self.assertRaises(ValueError):
            build_outlet_forest([0], [1.], [], [{"leaf_id": 0, "cell_id": 0, "outflow_m3": 0.}])


if __name__ == "__main__":
    unittest.main()
