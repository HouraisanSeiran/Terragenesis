from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity, file_sha256
from terrain_pipeline import environment_delta_fv as fv
from terrain_pipeline import environment_delta_source as source
from terrain_pipeline.environment_regional_hydraulics import _digest


class DeltaSourceTests(unittest.TestCase):
    def fixture(self):
        bed = np.full((5, 7), -.5)
        receiver = np.full(bed.size, -1, dtype=np.int64)
        receiver[24] = 17
        arrays = {"bed_m": bed, "ocean_mask": np.ones_like(bed, bool), "receiver": receiver}
        metadata = {"source_world_identity": "test-world", "origin_native_xz": [100, 200]}
        prepared = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
        packet = {"source_world_identity": "test-world", "source_node": 24, "target_node": 17,
                  "source_native_xz": [103, 203], "target_native_xz": [103, 202],
                  "time_start_s": 100., "time_end_s": 102., "water_m3": 1., "solid_m3": .001}
        packet["packet_id"] = _digest(packet)
        return prepared, packet

    def changed(self, packet, **changes):
        packet = dict(packet, **changes)
        packet["packet_id"] = _digest({k: v for k, v in packet.items() if k != "packet_id"})
        return packet

    def test_crop_maps_original_receiver_and_native_world_coordinates(self):
        prepared, packet = self.fixture()
        initial = source.initialize(prepared, packet, bounds=(1, 1, 6, 5))
        self.assertEqual(initial["metadata"]["origin_m_xz"], [3030., 6030.])
        self.assertEqual(initial["arrays"]["inlet_cells"].tolist(), [7])
        np.testing.assert_array_equal(initial["arrays"]["initial_bed_m"], prepared["arrays"]["bed_m"][1:5, 1:6])
        result = source.advance(initial, [packet])
        self.assertEqual(result["metadata"]["ledger"]["solid_input_m3"], .001)
        self.assertEqual(result["metadata"]["forcing_records"][0]["source_packet"], packet)
        self.assertNotIn("receiver", result["arrays"])

    def test_foreign_world_wrong_edge_coords_and_invalid_crop_are_rejected(self):
        prepared, packet = self.fixture()
        for changes in ({"source_world_identity": "other"}, {"source_node": 23},
                        {"target_native_xz": [3, 2]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                source.initialize(prepared, self.changed(packet, **changes))
        with self.assertRaises(ValueError):
            source.initialize(prepared, packet, bounds=(0, 0, 2, 2))

    def test_duplicate_and_time_gap_rejected_before_any_advance(self):
        prepared, packet = self.fixture()
        initial = source.initialize(prepared, packet)
        before = initial["identity_sha256"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            source.advance(initial, [packet, packet])
        gap = self.changed(packet, time_start_s=103., time_end_s=104.)
        with self.assertRaisesRegex(ValueError, "contiguous"):
            source.advance(initial, [packet, gap])
        self.assertEqual(initial["identity_sha256"], before)

    def test_diagnostic_control_cannot_receive_actual_world_packets(self):
        prepared, packet = self.fixture()
        initial = source.initialize(prepared, packet)
        initial["metadata"]["diagnostic_control"] = True
        initial["identity_sha256"] = identity(initial["arrays"], initial["metadata"])
        with self.assertRaisesRegex(ValueError, "diagnostic"):
            source.advance(initial, [packet])

    def test_cold_continue_preserves_packet_provenance_and_matches_batch(self):
        prepared, packet = self.fixture()
        initial = source.initialize(prepared, packet)
        second = self.changed(packet, time_start_s=102., time_end_s=104.)
        first = source.advance(initial, [packet])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delta.npz"
            fv.save(path, first)
            cold = fv.load(path, expected_sha256=file_sha256(path))
            continued = source.advance(cold, [second])
        whole = source.advance(initial, [packet, second])
        self.assertEqual(whole["identity_sha256"], continued["identity_sha256"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            source.advance(continued, [packet])


if __name__ == "__main__":
    unittest.main()
