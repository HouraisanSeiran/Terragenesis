import copy
import unittest

from terrain_pipeline.surface_rivers.metric_morphology_events import MorphologyEvent
from terrain_pipeline.surface_rivers.metric_morphology_topology import TopologyPatch


class TopologyPatchTests(unittest.TestCase):
    def make_event(self, **changes):
        values = {
            "event_id": "event-1",
            "event_type": "cutoff",
            "parent_graph_identity_sha256": "a" * 64,
            "parent_geometry_identity_sha256": "b" * 64,
            "affected_edges": ("edge-1",),
            "added_edges": ("edge-3",),
            "retired_edges": ("edge-2",),
            "water_transfer_m3": 12.5,
            "sediment_transfer_solid_m3": 2.25,
            "material_ledger": {},
            "parameters": {"threshold": 1},
        }
        values.update(changes)
        return MorphologyEvent(**values)

    def test_identity_and_record_round_trip(self):
        patch = TopologyPatch.from_event(self.make_event(), ("edge-1", "edge-2"), ("lake-1",))
        record = patch.to_record()
        restored = TopologyPatch.from_record(record)
        self.assertEqual(restored, patch)
        self.assertEqual(restored.identity_sha256, patch.identity_sha256)
        self.assertEqual(record["identity_sha256"], patch.identity_sha256)

    def test_edge_gates_reject_duplicates_crossings_and_invalid_retirements(self):
        event = self.make_event()
        with self.assertRaises(ValueError):
            TopologyPatch.from_event(event, ("edge-1", "edge-1"))
        with self.assertRaises(ValueError):
            TopologyPatch.from_event(event, ("edge-1", "edge-2", "edge-3"))
        with self.assertRaises(ValueError):
            TopologyPatch.from_event(event, ("edge-1",))
        with self.assertRaises(ValueError):
            TopologyPatch(
                "a" * 64, "b" * 64, ("edge-1",), ("edge-2",), ("edge-2",), (), 0, 0)

    def test_revalidation_and_negative_inventory_are_gates(self):
        event = self.make_event(revalidation_required=("topology", "geometry", "sediment"))
        with self.assertRaises(ValueError):
            TopologyPatch.from_event(event, ("edge-1", "edge-2"))
        with self.assertRaises(ValueError):
            TopologyPatch("a" * 64, "b" * 64, ("edge-1",), (), (), (), -1, 0)

    def test_tampering_and_input_immutability(self):
        event = self.make_event()
        active = ["edge-1", "edge-2"]
        lakes = ["lake-1"]
        active_before = copy.deepcopy(active)
        lakes_before = copy.deepcopy(lakes)
        patch = TopologyPatch.from_event(event, active, lakes)
        record = patch.to_record()
        record["added_edge_ids"] = ["edge-tampered"]
        with self.assertRaises(ValueError):
            TopologyPatch.from_record(record)
        self.assertEqual(active, active_before)
        self.assertEqual(lakes, lakes_before)
        self.assertEqual(event.added_edges, ("edge-3",))

    def test_validate_against_only_checks_snapshot(self):
        patch = TopologyPatch.from_event(self.make_event(), ("edge-1", "edge-2"))
        self.assertTrue(patch.validate_against(("edge-1", "edge-2")))
        with self.assertRaises(ValueError):
            patch.validate_against(("edge-1",))


if __name__ == "__main__":
    unittest.main()
