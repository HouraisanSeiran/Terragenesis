import unittest
import numpy as np
from terrain_pipeline.channel_geometry import build_section
from terrain_pipeline.surface_rivers.native_30m_reach_chain import build_reach_geometry, run_reach_dynamics


def fixture():
    h = np.broadcast_to(100.0 - np.arange(40, dtype=np.float64)[None, :] * 0.1, (40, 40)).copy()
    ids = 20 * 40 + np.arange(10, 21, dtype=np.int64)
    s = build_section(h, {"chosen": {"stem_flat_cells": ids}}, 1.0,
                      origin_native_xz=(0, 0), section_parameters={})
    g = build_reach_geometry(h, np.ones(h.shape, bool), s,
                            origin_native_xz=(0, 0), source_identity_sha256="0" * 64)
    return h, s, g


class TestNative30mReachChain(unittest.TestCase):
    def test_geometry_decreasing_and_metadata(self):
        h, s, g = fixture()
        bed = np.asarray(g["node_bed_m"])
        self.assertTrue(np.all(np.diff(bed) < 0.0))
        length = np.asarray(g["node_length_m"])
        self.assertTrue(np.all(length > 0.0))
        self.assertEqual(list(g["crop_rc"]), [8, 33, 0, 33])
        self.assertEqual(len(g["geometry"]["identity_sha256"]), 64)
        self.assertIs(g["metadata"]["generation_excavation_not_dynamic_erosion"], True)

    def test_wrong_section_origin_rejected(self):
        h, s, _ = fixture()
        with self.assertRaises(ValueError):
            build_reach_geometry(h, np.ones(h.shape, bool), s,
                                 origin_native_xz=(1, 0), source_identity_sha256="0" * 64)

    def test_fresh_support_unknown_inside_crop(self):
        h, s, _ = fixture()
        mask = np.ones(h.shape, bool)
        mask[20, 15] = False
        with self.assertRaises(ValueError):
            build_reach_geometry(h, mask, s, origin_native_xz=(0, 0),
                                 source_identity_sha256="0" * 64)

    def test_run_reach_dynamics_and_source_mismatch(self):
        h, s, g = fixture()
        n = len(g["node_bed_m"])
        e = {"local_q_m3_s": np.full((1, n), 1e-5),
             "time": {"time_edges_s": np.array([0.0, 1.0])},
             "terminal": {"catchment_cells": n}, "event_identity_sha256": "1" * 64,
             "source": {"source_identity_sha256": "0" * 64}, "design_q_m3_s": 1.0}
        d = run_reach_dynamics(g, e, np.ones(n, np.int64), coupled_intervals=1)
        self.assertEqual(d["dynamics"]["metadata"]["status"], "complete")
        self.assertEqual(d["dynamics"]["arrays"]["node_bed_m"].shape, (2, n))
        self.assertEqual(d["metadata"]["simulation_mode"], "storm_transient_local_runoff")
        self.assertIs(d["dynamics"]["metadata"]["dynamic_PL_mesh_updated"], False)
        e["source"]["source_identity_sha256"] = "2" * 64
        with self.assertRaisesRegex(ValueError, "event_geometry_source_mismatch"):
            run_reach_dynamics(g, e, np.ones(n, np.int64), coupled_intervals=1)


if __name__ == "__main__":
    unittest.main()
