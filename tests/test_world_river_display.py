import unittest

import numpy as np

from terrain_pipeline.world_river_network_io import (
    display_reach_mask, downstream_display_destination,
)


class RiverDisplayTests(unittest.TestCase):
    def graph(self):
        return {"native_shape": np.array([1, 8]), "origin_native_xz": np.array([0, 0]),
                "node_x_m": np.arange(8, dtype=float), "node_z_m": np.zeros(8),
                "receiver": np.array([2, 2, 3, -1, 5, -1, -1, -1]),
                "node_q_m3_s": np.array([1., 2., 3., 3., .2, .2, .3, .1]),
                "node_width_m": np.array([.5, 1., 2., 2., .2, .2, .2, .1]),
                "node_terminal_kind": np.array([0, 0, 0, 4, 0, 3, 2, 1]),
                "reach_source": np.array([0, 1, 2, 4]),
                "reach_target": np.array([2, 2, 3, 5]),
                "reach_projection_blocked": np.array([False, False, True, False])}

    def test_hidden_tributaries_keep_accumulated_main_flow_and_source_arrays(self):
        graph = self.graph()
        before = {key: value.copy() for key, value in graph.items()}
        visible = display_reach_mask(graph, min_q_m3_s=2.5, min_width_m=1.5)
        np.testing.assert_array_equal(visible, [False, False, True, False])
        for node in (0, 1):
            self.assertEqual(downstream_display_destination(graph, node, visible),
                             {"kind": "visible_reach", "node_id": 2, "reach_index": 2})
        self.assertEqual(graph["node_q_m3_s"][2], 3.)
        self.assertEqual(graph["node_q_m3_s"][3], 3.)
        for key, original in before.items():
            np.testing.assert_array_equal(graph[key], original)
        with self.assertRaises(ValueError):
            visible.flags.writeable = True

    def test_nearest_means_downstream_and_preserves_lake_ocean_unknown(self):
        graph = self.graph()
        visible = display_reach_mask(graph, min_q_m3_s=2.5)
        for start, terminal, kind in ((4, 5, 3), (3, 3, 4), (6, 6, 2), (7, 7, 1)):
            self.assertEqual(downstream_display_destination(graph, start, visible),
                             {"kind": "terminal", "node_id": terminal, "terminal_kind": kind})
        # Even a geometrically coincident main river cannot capture a lake branch.
        graph["node_x_m"][4:6] = graph["node_x_m"][2]
        self.assertEqual(downstream_display_destination(graph, 4, visible)["node_id"], 5)

    def test_inclusive_thresholds_both_apply_and_warning_flags_stay_separate(self):
        graph = self.graph()
        np.testing.assert_array_equal(display_reach_mask(graph), np.ones(4, bool))
        np.testing.assert_array_equal(display_reach_mask(graph, min_q_m3_s=2., min_width_m=1.),
                                     [False, True, True, False])
        np.testing.assert_array_equal(display_reach_mask(graph, min_q_m3_s=1., min_width_m=1.5),
                                     [False, False, True, False])
        self.assertTrue(graph["reach_projection_blocked"][2])
        for value in (-1., np.inf, np.nan, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                display_reach_mask(graph, min_q_m3_s=value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                display_reach_mask(graph, min_width_m=value)

    def test_invalid_discharge_and_receiver_cycle_are_rejected(self):
        graph = self.graph()
        graph["node_q_m3_s"][0] = np.nan
        with self.assertRaises(ValueError):
            display_reach_mask(graph)
        graph = self.graph()
        graph["receiver"][3] = 0
        graph["node_terminal_kind"][3] = 0
        with self.assertRaisesRegex(ValueError, "cycle"):
            downstream_display_destination(graph, 0, np.zeros(4, bool))


if __name__ == "__main__":
    unittest.main()
