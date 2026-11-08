"""Small external-behavior checks for the large-map independent reviewer."""
import unittest
import numpy as np

from tools.review_large_td_confluence import accumulate, cold_audit, square_wall_port_review, strahler, topology
from terrain_pipeline.common_infra import identity


class ColdConfluenceReviewTests(unittest.TestCase):
    def candidate(self):
        # Two native tributaries share cell 4 on a shallow candidate water surface.
        rec = np.array([4, 4, 5, 4, 7, 8, 7, 8, -1], np.int64)
        order, cycles = topology(rec)
        self.assertEqual(cycles, 0)
        local = np.arange(1., 10.)
        area = accumulate(rec, order, np.full(9, 1_000_000.))
        q = accumulate(rec, order, local)
        raw = np.array([[5., 5., 5.], [4., 1., 4.], [3., 2., 0.]])
        work = raw.copy(); work[1, 1] = 3.
        selected = area >= 1_000_000.
        ids = np.flatnonzero(rec >= 0)
        arrays = dict(original_td_m=raw, receiver=rec, topological_order=order,
            contributing_area_m2=area, local_q_m3_s=local, routed_q_m3_s=q,
            frozen_owner_domain_id=np.zeros((3, 3), np.int32), working_height_m=work,
            working_raise_m=work-raw, selected_edge_source_ids=ids, selected_edge_target_ids=rec[ids],
            strahler_order=strahler(rec, order, selected), terminal_status=np.array([0]*8+[1], np.uint8))
        metadata = dict(spacing_m=1000., routing={"max_fill_depth_m": 4.,
            "terminal_status_codes": {"interior": 0, "unresolved_deep_depression": 1}})
        return arrays, metadata

    def test_shared_water_surface_confluence_and_conserved_q(self):
        arrays, metadata = self.candidate()
        report, nodes = cold_audit(arrays, metadata)
        self.assertIn(4, nodes)
        self.assertEqual(arrays["routed_q_m3_s"][4], 1.+2.+4.+5.)
        self.assertEqual(report["q_accumulation_max_residual_m3_s"], 0.)
        self.assertTrue(all(report["gates"].values()))
        self.assertEqual(report["selected_terminal_classification"], {"unresolved_deep_depression": 1})

    def test_rejects_cross_owner_and_corrupt_saved_q(self):
        arrays, metadata = self.candidate()
        arrays["frozen_owner_domain_id"][1, 1] = 1
        arrays["routed_q_m3_s"][4] += 1.
        report, _ = cold_audit(arrays, metadata)
        self.assertFalse(report["gates"]["same_owner_every_edge"])
        self.assertFalse(report["gates"]["q_residual"])

    def test_cycle_is_detected_without_per_cell_objects(self):
        _, unresolved = topology(np.array([1, 0, -1]))
        self.assertEqual(unresolved, 2)

    def test_isolated_above_threshold_terminal_is_not_visible_network(self):
        arrays, metadata = self.candidate()
        arrays["receiver"][2] = -1
        order, _ = topology(arrays["receiver"])
        arrays["topological_order"] = order
        arrays["contributing_area_m2"] = accumulate(arrays["receiver"], order, np.full(9, 1_000_000.))
        arrays["routed_q_m3_s"] = accumulate(arrays["receiver"], order, arrays["local_q_m3_s"])
        ids = np.flatnonzero(arrays["receiver"] >= 0)
        arrays["selected_edge_source_ids"] = ids
        arrays["selected_edge_target_ids"] = arrays["receiver"][ids]
        arrays["strahler_order"] = strahler(arrays["receiver"], order, arrays["contributing_area_m2"] >= 1_000_000.)
        arrays["terminal_status"][2] = 1
        report, _ = cold_audit(arrays, metadata)
        self.assertEqual(report["all_terminal_count"], 2)
        self.assertEqual(report["isolated_above_threshold_terminal_count"], 1)
        self.assertEqual(report["selected_terminal_count"], 1)
        self.assertEqual(report["selected_source_count"], 5)
        self.assertEqual(report["single_source_component_count"], 0)
        self.assertTrue(all(report["gates"].values()))

    def native_candidate(self):
        arrays, metadata = self.candidate()
        metadata["planning_policy"] = "native-source-replan"
        metadata["routing"]["terminal_status_codes"]["unresolved_domain_boundary"] = 2
        metadata["native_planning_metadata"] = {"algorithm": "test_fixed_native_support"}
        self.update_native_owner(arrays, metadata)
        return arrays, metadata

    def update_native_owner(self, arrays, metadata):
        rec = arrays["receiver"]
        order, _ = topology(rec)
        owner = np.arange(rec.size, dtype=np.int64)
        for cell in order[::-1]:
            if rec[cell] >= 0:
                owner[cell] = owner[rec[cell]]
        arrays["native_planning_owner_domain_id"] = owner.reshape(arrays["original_td_m"].shape)
        metadata["native_planning_identity_sha256"] = identity(
            {"native_planning_owner_domain_id": arrays["native_planning_owner_domain_id"]}, metadata["native_planning_metadata"])

    def test_native_replan_reference_label_crossing_is_diagnostic(self):
        arrays, metadata = self.native_candidate()
        arrays["frozen_owner_domain_id"][1, 1] = 1
        report, _ = cold_audit(arrays, metadata)
        self.assertGreater(report["strict_owner_change_edge_count"], 0)
        self.assertNotIn("same_owner_every_edge", report["gates"])
        self.assertTrue(all(report["gates"].values()))
        self.assertFalse(report["naturalness_certified"])

    def test_native_replan_rejects_artificial_internal_port(self):
        arrays, metadata = self.native_candidate()
        arrays["receiver"][4] = -1
        order, _ = topology(arrays["receiver"])
        arrays["topological_order"] = order
        arrays["contributing_area_m2"] = accumulate(arrays["receiver"], order, np.full(9, 1_000_000.))
        arrays["routed_q_m3_s"] = accumulate(arrays["receiver"], order, arrays["local_q_m3_s"])
        ids = np.flatnonzero(arrays["receiver"] >= 0)
        arrays["selected_edge_source_ids"] = ids
        arrays["selected_edge_target_ids"] = arrays["receiver"][ids]
        arrays["strahler_order"] = strahler(arrays["receiver"], order, arrays["contributing_area_m2"] >= 1_000_000.)
        arrays["terminal_status"][4] = 2
        self.update_native_owner(arrays, metadata)
        report, _ = cold_audit(arrays, metadata)
        self.assertFalse(report["boundary_gates"]["no_artificial_internal_domain_ports"])
        self.assertFalse(report["boundary_gates"]["nondeep_terminals_on_actual_perimeter"])
        self.assertEqual(report["selected_internal_artificial_domain_port_count"], 1)

    def test_former_port_review_follows_actual_new_receiver(self):
        candidate, metadata = self.native_candidate()
        reference, reference_metadata = self.candidate()
        reference["receiver"][4] = -1
        reference["selected_edge_source_ids"] = np.flatnonzero(reference["receiver"] >= 0)
        reference["terminal_status"][4] = 2
        reference_metadata["routing"]["terminal_status_codes"]["unresolved_domain_boundary"] = 2
        ports, review = square_wall_port_review(reference, reference_metadata, candidate, metadata)
        np.testing.assert_array_equal(ports, [4])
        self.assertEqual(review["former_ports_same_pixel_has_receiver_count"], 1)
        self.assertEqual(review["nearby_route_records"][0]["nearest_new_selected_actual_downstream_length_m"], 2000.)


if __name__ == "__main__":
    unittest.main()
