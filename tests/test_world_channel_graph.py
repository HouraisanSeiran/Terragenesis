"""Behavior tests for world graph ownership, overlap and physical edge exchange."""
import unittest
import numpy as np

from terrain_pipeline.surface_rivers.world_channel_graph import (
    WorldNode, node_id, assemble_world_graph, assemble_local_forcing, regional_exchange)


class WorldChannelGraphTests(unittest.TestCase):
    def records(self):
        seed = 7
        coordinates = [(10., 10.), (10., 30.), (30., 10.), (50., 10.)]
        receiver = [2, 2, 3, -1]
        return [WorldNode(seed, *p, None if j < 0 else node_id(seed, *coordinates[j]))
                for p, j in zip(coordinates, receiver)]

    def test_overlapping_pages_and_loading_order_produce_one_world_graph(self):
        records = self.records()
        first = assemble_world_graph(records + records[:2], 40.)
        second = assemble_world_graph(list(reversed(records)), 40.)
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        np.testing.assert_array_equal(first["receiver"], second["receiver"])
        self.assertEqual(len(first["node_ids"]), 4)
        self.assertEqual(len(first["cross_region_donors"]), 1)

    def test_shared_source_counts_once_and_conflict_is_not_summed(self):
        graph = assemble_world_graph(self.records(), 40.)
        target = graph["node_ids"][0]
        source = ("catchment-A", target, [2., 1.])
        actual = assemble_local_forcing(graph, [0., 10., 20.], [source, source])
        np.testing.assert_array_equal(actual[:, 0], [2., 1.])
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            assemble_local_forcing(graph, [0., 10., 20.], [source, ("catchment-A", target, [1., 1.])])

    def test_receiver_conflict_missing_downstream_and_cycle_refuse(self):
        records = self.records()
        with self.assertRaisesRegex(ValueError, "conflicting world-node"):
            assemble_world_graph(records + [WorldNode(7, 10., 10., None)], 40.)
        with self.assertRaisesRegex(ValueError, "missing downstream"):
            assemble_world_graph(records[:-1], 40.)
        with self.assertRaisesRegex(ValueError, "acyclic"):
            assemble_world_graph([WorldNode(7, 0., 0., node_id(7, 1., 0.)),
                                  WorldNode(7, 1., 0., node_id(7, 0., 0.))], 40.)

    def test_engineering_scene_uses_carved_geometry_and_one_owned_source(self):
        from tools.run_cross_region_tributary import make_scene
        graph, geometry, network, forcing = make_scene()
        self.assertEqual(len(set(graph["region_ids"])), 2)
        self.assertEqual(len(graph["cross_region_donors"]), 2)
        donors = np.bincount(network.receiver[network.receiver >= 0], minlength=len(network.receiver))
        self.assertEqual(np.count_nonzero(donors == 2), 1)
        self.assertEqual(network.source_identity_sha256, geometry["identity_sha256"])
        self.assertTrue(np.all(geometry["arrays"]["cut_depth_m"] >= 0.))
        self.assertGreater(geometry["metadata"]["cut_volume_m3"], 0.)
        self.assertAlmostEqual(float(np.sum(forcing.local_q_m3_s * np.diff(forcing.time_seconds)[:, None])), 871.5)

    def test_internal_crossing_debits_and_credits_exactly_once(self):
        graph = assemble_world_graph(self.records(), 40.)
        outgoing = np.arange(8., dtype=np.float64).reshape(2, 4)
        exchange = regional_exchange(graph, outgoing)
        np.testing.assert_array_equal(exchange["incoming_m3"].sum(axis=1),
                                      exchange["outgoing_m3"].sum(axis=1))
        donor = graph["cross_region_donors"][0]
        self.assertEqual(exchange["edge_transfers"][0]["total_volume_m3"], outgoing[:, donor].sum())
        self.assertEqual(exchange["region_ids"], ["0:0", "1:0"])


if __name__ == "__main__":
    unittest.main()
