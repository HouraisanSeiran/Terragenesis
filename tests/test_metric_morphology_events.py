import copy
import unittest

from terrain_pipeline.surface_rivers.metric_morphology_events import (
    MorphologyEvent, event_from_record)


def event():
    return MorphologyEvent(
        "cutoff-01", "cutoff", "a" * 64, "b" * 64,
        ("edge-old",), ("edge-shortcut",), ("edge-old",), 3., 2.,
        {"deposited_solid_m3": 1., "exported_solid_m3": 1.},
        {"neck_distance_m": 4., "loop_length_m": 40.})


class MorphologyEventTests(unittest.TestCase):
    def test_identity_roundtrip_and_frozen_nested_values(self):
        original = event()
        restored = event_from_record(original.to_record())
        self.assertEqual(restored.identity_sha256, original.identity_sha256)
        with self.assertRaises(TypeError):
            restored.parameters["neck_distance_m"] = 2.

    def test_tampering_and_invalid_topology_rejected(self):
        record = event().to_record()
        changed = copy.deepcopy(record)
        changed["added_edges"] = ["edge-old"]
        with self.assertRaises(ValueError):
            event_from_record(changed)
        with self.assertRaises(ValueError):
            MorphologyEvent("x", "cutoff", "a" * 64, "b" * 64, ("e",), ("e",), ("e",),
                            0., 0., {}, {})


if __name__ == "__main__":
    unittest.main()
