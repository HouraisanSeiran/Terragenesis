import unittest
import tempfile
from pathlib import Path
import numpy as np

from tools.prepare_hydrology_full_edges import edge_request, audit_basin_continuity, prepare_coarse_bed_graph, audit_saved_coarse_bed_graph, stitch_fractional_coarse_profiles


class CompleteEdgeScheduleTests(unittest.TestCase):
    def test_fractional_fine_interval_keeps_actual_ports_and_outside_source(self):
        plan = {"height_m": np.array([[20., 10.], [20., 10.]]),
                "owner_domain_id": np.zeros((2, 2), int), "river_mask": np.array([[True, False], [False, False]]),
                "receiver": np.array([[1, -1], [-1, -1]]), "origin_xz_m": [0., 0.], "spacing_m": 100., "identity_sha256": "frozen"}
        with tempfile.TemporaryDirectory() as temporary:
            graph = prepare_coarse_bed_graph(plan, 1., {}, set(), temporary)
            coverage = [{"source_edge": [0, 1], "fraction_interval": [.4, .6],
                         "upstream_realized_center_m": 15.6, "downstream_realized_center_m": 13.6,
                         "frozen_coarse_account_stage_m": 1.}]
            result = stitch_fractional_coarse_profiles(plan, graph, coverage, temporary)
            self.assertTrue(result["fine_to_coarse_fraction_interfaces_verified"])
            self.assertTrue(result["independent_coarse_cold_audit"]["accepted"])
            self.assertEqual([record["fraction_interval"] for record in result["edge_profiles"]], [[0., .4], [.6, 1.]])
            for item in result["fraction_interfaces"]:
                self.assertAlmostEqual(item["coarse_center_difference_m"], 0.)
            sidecar_plan = {**plan, "river_mask": np.zeros((2, 2), dtype=bool)}
            empty_graph = prepare_coarse_bed_graph(sidecar_plan, 1., {}, set(), temporary)
            sidecar = stitch_fractional_coarse_profiles(sidecar_plan, empty_graph, coverage, temporary, extra_edges=[(0, 1)])
            self.assertTrue(sidecar["fine_to_coarse_fraction_interfaces_verified"])
            self.assertEqual(sidecar["extra_registered_receiver_edges"][0]["source_edge"], [0, 1])
            self.assertTrue(sidecar["extra_registered_receiver_edges"][0]["actual_receiver_verified"])
            coverage[0]["upstream_realized_center_m"] = 17.
            rejected = stitch_fractional_coarse_profiles(plan, graph, coverage, temporary)
            self.assertFalse(rejected["fine_to_coarse_fraction_interfaces_verified"])
        with self.assertRaisesRegex(ValueError, "actual owned receiver"):
            stitch_fractional_coarse_profiles(plan, graph, coverage, temporary, extra_edges=[(1, 0)])

    def test_actual_fine_port_extends_into_source_bounded_coarse_profile(self):
        plan = {"height_m": np.array([[20., 10., 0.], [20., 10., 0.]]),
                "owner_domain_id": np.zeros((2, 3), int), "river_mask": np.array([[True, True, False], [False, False, False]]),
                "receiver": np.array([[1, 2, -1], [-1, -1, -1]]), "origin_xz_m": [0., 0.], "spacing_m": 100., "identity_sha256": "frozen"}
        with tempfile.TemporaryDirectory() as temporary:
            result = prepare_coarse_bed_graph(plan, 1., {1: {"realized_center_m": 9.5}}, {(0, 1)}, temporary)
            self.assertTrue(result["accepted"])
            self.assertTrue(audit_saved_coarse_bed_graph(plan, result)["accepted"])
            self.assertEqual(len(result["edge_profiles"]), 1)
            with np.load(result["edge_profiles"][0]["path"], allow_pickle=False) as archive:
                bed, source = archive["coarse_bed_elevation_m"], archive["source_macro_surface_m"]
                self.assertEqual(bed[0], 9.5)
                self.assertTrue(np.all(source - bed <= 4. + 1e-6))
                self.assertTrue(np.all(source - bed >= 0.5 - 1e-6))
            shallow_port = prepare_coarse_bed_graph(plan, 1., {1: {"realized_center_m": 9.6}}, {(0, 1)}, temporary)
            self.assertTrue(shallow_port["accepted"])
            self.assertAlmostEqual(shallow_port["edge_profiles"][0]["audit"]["minimum_cut_m"], 0.4)
            rejected = prepare_coarse_bed_graph(plan, 1., {1: {"realized_center_m": 10.5}}, {(0, 1)}, temporary)
            self.assertFalse(rejected["accepted"])
            self.assertTrue(any(item["reason"] == "coarse_profile_geometry_rejected" for item in rejected["failures"]))

    def test_complete_owned_basin_traces_every_cell_without_claiming_missing_fine_interfaces(self):
        from terrain_pipeline.hydrology_planning import plan_macro_cell, save_plan

        plan = plan_macro_cell(3)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "plan.npz"
            save_plan(plan, path)
            audit = audit_basin_continuity(path, [], directory)
        self.assertTrue(audit["coarse_dag_accepted"])
        self.assertEqual(audit["owned_cell_count"], audit["traced_owned_cell_count"])
        self.assertEqual(sum(item["owned_path_count"] for item in audit["terminal_paths"]), audit["owned_cell_count"])
        self.assertEqual(audit["coarse_only_river_edges"], audit["coarse_river_edges"])
        self.assertFalse(audit["fine_to_coarse_interfaces_accepted"])
        self.assertFalse(audit["global_hydrology_certified"])

    def test_complete_edge_fraction_coverage_fixed_tiles_and_endpoint_identity(self):
        plan = {
            "identity_sha256": "frozen",
            "height_m": np.zeros((2, 2)),
            "origin_xz_m": [0, 0],
            "spacing_m": 10000.0,
            "receiver": np.array([-1, 0, -1, -1]),
            "river_mask": np.array([[False, True], [False, False]]),
        }
        request = edge_request(plan, [1, 0])
        intervals = request["piece_fraction_intervals"]
        self.assertEqual(len(intervals), 20)
        self.assertEqual(intervals[0][0], 0.0)
        self.assertEqual(intervals[-1][1], 1.0)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(intervals, intervals[1:])))
        self.assertEqual(request["endpoint_ids"], ["frozen:1", "frozen:0"])
        self.assertEqual(request["length_m"], 10000.0)
        self.assertEqual(
            len(request["source_tiles"]), len(set(map(tuple, request["source_tiles"])))
        )

    def test_non_frozen_receiver_edge_refused(self):
        plan = {"receiver": np.array([-1, 0]), "river_mask": np.array([False, True])}
        with self.assertRaisesRegex(ValueError, "actual selected"):
            edge_request(plan, [1, 1])


if __name__ == "__main__":
    unittest.main()
