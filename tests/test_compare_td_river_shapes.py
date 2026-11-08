import unittest
import copy
import tempfile
from unittest.mock import patch

import numpy as np

from tools.compare_td_river_shapes import coverage, section_metrics, turn_metrics, local_mesh, sample_bed, empty_mesh, selection_transitions, bind_component_to_sample, compare_components, frozen_anchors
from tools.audit_td_generated_rivers import audit_saved_centerline, audit_transverse_bed
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import _sparse_mesh


class SavedRiverShapeComparisonTests(unittest.TestCase):
    def test_narrow_deep_center_is_distinct_from_broad_bottom(self):
        distance = np.linspace(-10, 10, 2001)
        narrow = 100 - 3 * np.maximum(0, 1 - abs(distance))
        broad = np.full_like(distance, 97.)
        trench = section_metrics(distance, narrow, 10)
        fixed = section_metrics(distance, broad, 10)
        self.assertAlmostEqual(trench["center_below_lower_bottom_shoulder_m"], 3)
        self.assertLess(trench["center_trench_half_depth_width_ratio"], .11)
        self.assertEqual(fixed["bottom_elevation_span_m"], 0)
        self.assertEqual(fixed["center_below_lower_bottom_shoulder_m"], 0)

    def test_distant_lower_valley_does_not_fail_channel(self):
        distance = np.linspace(-150, 150, 3001)
        source = 100 + (distance - 90) ** 2 / 10000
        result = section_metrics(distance, np.full_like(distance, 99.), 10, source)
        self.assertTrue(result["available"])
        self.assertEqual(result["nearby_source_valley_offset_m"], 30)
        self.assertGreater(result["source_center_above_nearby_valley_m"], 0)

    def test_missing_bottom_is_reported_without_passing_shape(self):
        distance = np.linspace(-5, 5, 101)
        bed = np.zeros(101)
        bed[50] = np.nan
        result = section_metrics(distance, bed, 8)
        self.assertFalse(result["available"])
        self.assertLess(result["bottom_sample_coverage_fraction"], 1)

    def test_real_turns_and_confluence_are_separate(self):
        mesh = {"source_node_cell_ids": np.arange(5), "receiver": np.array([1, 2, 3, -1, 2]),
                "node_xz_m": np.array([[0., 0.], [1., 0.], [1., 1.], [2., 1.], [0., 1.]])}
        result = turn_metrics(mesh)
        self.assertEqual(result["ordinary"]["near_45_or_90_count"], 1)
        self.assertEqual(result["confluence"]["count"], 2)
        self.assertEqual(result["terminal_incoming_edge_count"], 1)
        self.assertEqual(sum(result["ordinary"]["angle_histogram"]["counts"]), 1)
        self.assertEqual(sum(result["confluence"]["angle_histogram"]["counts"]), 2)
        common = turn_metrics(mesh, {(0, 1), (1, 2)})
        self.assertEqual(common["ordinary"]["count"], 1)
        self.assertEqual(common["confluence"]["count"], 0)

    def test_coverage_names_every_lost_and_added_edge(self):
        result = coverage({(0, 1), (1, 2)}, {(1, 2), (2, 3)})
        self.assertEqual(result["common_count"], 1)
        self.assertEqual(result["lost_edge_ids"], [(0, 1)])
        self.assertEqual(result["added_edge_ids"], [(2, 3)])

    def test_fixed_anchor_count_is_preserved_when_center_duplicates_stratified_edge(self):
        mesh = {"source_node_cell_ids": np.arange(6), "receiver": np.array([1, 2, 3, 4, 5, -1]),
                "node_xz_m": np.column_stack((np.arange(6), np.zeros(6))), "width_m": np.full(6, 6.)}
        sample = {"meshes": [mesh], "report": {"terrain_metadata": {"x0_m": 0., "z0_m": 0., "dx_m": 1., "dz_m": 1.}},
                  "arrays": {"source_height_m": np.zeros((1, 6))}}
        anchors = frozen_anchors(sample, count=4)
        self.assertEqual(len(anchors), 4)
        self.assertEqual(len({tuple(anchor["edge_cell_ids"]) for anchor in anchors}), 4)
        self.assertEqual(anchors[0]["edge_cell_ids"], [2, 3])
        self.assertEqual(len(frozen_anchors(sample, count=13)), 5)

    def test_saved_triangle_section_in_metres_at_large_world_coordinates(self):
        origin = np.array([-491520., -1966080.])
        mesh = {"vertices_xz_m": origin + np.array([[-10., -10.], [10., -10.], [10., 10.], [-10., 10.]]),
                "triangles": np.array([[0, 1, 2], [0, 2, 3]]),
                "bed_elevation_m": np.array([95., 97., 101., 99.]),
                "source_elevation_m": np.full(4, 105.)}
        local = local_mesh(mesh, origin, 5)
        self.assertEqual(len(local["triangles"]), 2)
        actual = sample_bed(local, origin + np.array([[-5., 0.], [0., 0.], [5., 0.]]))
        np.testing.assert_allclose(actual, [97.5, 98., 98.5])

    def test_absent_saved_mesh_preserves_unavailable_sections(self):
        local = local_mesh(empty_mesh(), np.array([1000., 2000.]))
        self.assertTrue(np.isnan(sample_bed(local, np.array([[1000., 2000.]]))).all())

    def test_new_centerline_corridor_does_not_relax_legacy_gate(self):
        terrain = TerrainGrid(np.ones((2, 3)), np.ones((2, 3), bool),
                              0., 0., 30., 30., "generated_terrain", "fixture", "a" * 64)
        original = np.array([[0., 0.], [30., 0.], [60., 0.]])
        arrays = {"source_node_cell_ids": np.array([0, 1, 2]), "receiver": np.array([1, 2, -1]),
                  "node_xz_m": original.copy(), "original_node_xz_m": original,
                  "anchor_mask": np.array([True, False, True])}
        arrays["node_xz_m"][1, 1] = 20.
        bundle = {"arrays": arrays, "metadata": {"config": {"centerline_corridor_m": 30.}}}
        with self.assertRaisesRegex(ValueError, "corridor"):
            audit_saved_centerline(bundle, terrain)
        bundle["metadata"]["centerline_policy"] = {"corridor_m": 30., "maximum_original_source_rise_m": .5}
        self.assertEqual(audit_saved_centerline(bundle, terrain)["maximum_offset_m"], 20.)
        arrays["node_xz_m"][0, 0] += 1
        with self.assertRaisesRegex(ValueError, "anchor moved"):
            audit_saved_centerline(bundle, terrain)

    def test_independent_transverse_audit_detects_saved_bottom_shoulder_spike(self):
        terrain = TerrainGrid(np.full((5, 5), 100.), np.ones((5, 5), bool),
                              0., 0., 10., 10., "generated_terrain", "fixture", "a" * 64)
        cells = np.array([(x, z) for z in range(40) for x in range(40)])
        vertices, triangles = _sparse_mesh(cells, terrain, 1., 10000)
        bundle = {"arrays": {"sparse_cell_xy": cells, "vertices_xz_m": vertices,
                             "triangles": triangles, "bed_elevation_m": np.full(len(vertices), 99.),
                             "node_xz_m": np.array([[10., 10.], [20., 10.]]),
                             "receiver": np.array([1, -1]), "width_m": np.array([6., 6.])},
                  "metadata": {"config": {"fine_spacing_m": 1., "max_cut_m": 4.},
                               "design_bed_policy": {"transverse_bed_policy": "declared",
                                                     "transverse_bottom_slope_m_per_m": .02,
                                                     "transverse_bank_horizontal_per_vertical": 2.,
                                                     "transverse_bottom_guard_m": np.sqrt(2.)}}}
        self.assertEqual(audit_transverse_bed(bundle, terrain)["status"], "verified")
        spike = np.flatnonzero(np.all(vertices == [15., 12.], axis=1))[0]
        bundle["arrays"]["bed_elevation_m"][spike] += .5
        with self.assertRaisesRegex(ValueError, "center-coupled ceiling"):
            audit_transverse_bed(bundle, terrain)

    def test_independent_saved_path_audit_detects_crossing(self):
        terrain = TerrainGrid(np.ones((3, 3)), np.ones((3, 3), bool),
                              0., 0., 10., 10., "generated_terrain", "fixture", "a" * 64)
        original = np.array([[0., 0.], [20., 20.], [20., 0.], [0., 20.]])
        bundle = {"arrays": {"source_node_cell_ids": np.array([0, 8, 2, 6]),
                             "receiver": np.array([1, -1, 3, -1]), "node_xz_m": original.copy(),
                             "original_node_xz_m": original, "anchor_mask": np.ones(4, bool)},
                  "metadata": {"config": {}}}
        with self.assertRaisesRegex(ValueError, "edges cross"):
            audit_saved_centerline(bundle, terrain)

    def test_declared_node_cap_detects_actual_s1c3_tooth_outside_both_edge_strips(self):
        terrain = TerrainGrid(np.full((11, 11), 100.), np.ones((11, 11), bool),
                              0., 0., 10., 10., "generated_terrain", "fixture", "a" * 64)
        cells = np.array([(x, z) for z in range(100) for x in range(100)])
        vertices, triangles = _sparse_mesh(cells, terrain, 1., 30000)
        # Measured node 33045 geometry translated from the saved world origin.
        middle = np.array([50.8326421768, 50.4053272577])
        points = np.array([middle + [-34.0507506413, -5.6066848058], middle,
                           middle + [32.3683298647, -2.0541277805]])
        bed = np.full(len(vertices), 99.)
        tooth = np.flatnonzero(np.all(vertices == [50.5, 52.5], axis=1))[0]
        bed[tooth] += 2.4329661399883094
        policy = {"transverse_bed_policy": "declared", "transverse_bottom_slope_m_per_m": .02,
                  "transverse_bank_horizontal_per_vertical": 2., "transverse_bottom_guard_m": np.sqrt(2.)}
        bundle = {"arrays": {"sparse_cell_xy": cells, "vertices_xz_m": vertices, "triangles": triangles,
                             "bed_elevation_m": bed, "node_xz_m": points,
                             "receiver": np.array([1, 2, -1]), "width_m": np.full(3, 6.)},
                  "metadata": {"config": {"fine_spacing_m": 1., "max_cut_m": 4.}, "design_bed_policy": policy}}
        legacy = audit_transverse_bed(bundle, terrain)
        self.assertEqual(legacy["node_exterior_cap_audit"]["status"], "not_declared_for_this_artifact")
        policy.update(transverse_node_cap_policy="all incident unit-direction dot distances <= 1e-10m; actual node bed coupled",
                      transverse_node_cap_dot_tolerance_m=1e-10)
        with self.assertRaisesRegex(ValueError, "node exterior cap"):
            audit_transverse_bed(bundle, terrain)
        bed[tooth] = 99.
        fixed = audit_transverse_bed(bundle, terrain)["node_exterior_cap_audit"]
        self.assertEqual(fixed["status"], "verified")
        self.assertGreater(fixed["checked_node_vertex_pairs"], 0)

    def test_rejected_coverage_is_not_hidden_by_retained_geometry(self):
        before = {"selected_edge_source_ids": [1, 2, 3], "selected_edge_target_ids": [2, 3, 4],
                  "selected_edge_status": ["accepted", "rejected", "rejected"]}
        after = {"selected_edge_source_ids": [1, 2, 5], "selected_edge_target_ids": [2, 3, 6],
                 "selected_edge_status": ["rejected", "accepted", "rejected"]}
        result = selection_transitions(before, after)
        self.assertEqual(result["previously_accepted_now_rejected_edge_ids"], [(1, 2)])
        self.assertEqual(result["previously_rejected_now_accepted_edge_ids"], [(2, 3)])
        self.assertEqual(result["no_longer_selected_edge_ids"], [(3, 4)])

    def test_component_binding_rejects_shared_wrong_source_and_wrong_coordinates(self):
        terrain = TerrainGrid(np.ones((2, 2)), np.ones((2, 2), bool),
                              1000., -2000., 30., 30., "generated_terrain", "fixture", "a" * 64)
        registration = {"terrain": terrain, "metadata": {"boundary_identity_sha256": "b" * 64}}
        sample = {"report": {"terrain_metadata": terrain.metadata()},
                  "arrays": {"selected_edge_source_ids": np.array([0]), "selected_edge_target_ids": np.array([1])}}
        bundle = {"metadata": {"source_identity_sha256": terrain.identity_sha256, "terrain_metadata": terrain.metadata()},
                  "arrays": {"source_height_m": terrain.elevation_m.copy(), "source_valid_mask": terrain.valid_mask.copy(),
                             "source_node_cell_ids": np.array([0, 1]), "receiver": np.array([1, -1])}}
        self.assertEqual(bind_component_to_sample(bundle, sample, registration)["boundary_identity_sha256"], "b" * 64)
        wrong_source = copy.deepcopy(bundle)
        wrong_source["metadata"]["source_identity_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "original TD"):
            bind_component_to_sample(wrong_source, sample, registration)
        wrong_coordinate = copy.deepcopy(bundle)
        wrong_coordinate["metadata"]["terrain_metadata"]["x0_m"] += 30
        with self.assertRaisesRegex(ValueError, "coordinates"):
            bind_component_to_sample(wrong_coordinate, sample, registration)
        wrong_network = copy.deepcopy(bundle)
        wrong_network["arrays"]["source_node_cell_ids"] = np.array([0, 2])
        with self.assertRaisesRegex(ValueError, "boundary-bound"):
            bind_component_to_sample(wrong_network, sample, registration)

    def test_component_comparison_rejects_network_sample_boundary_registration_change(self):
        source_metadata = {"generation_report_path": "pinned-source.json", "sample_index": 1,
                           "generation_report_sha256": "a" * 64}
        saved_registration = {"source_metadata": source_metadata, "boundary_identity_sha256": "b" * 64}
        sample = {"report": {"source_registration": saved_registration}}
        actual_registration = copy.deepcopy(saved_registration)
        actual_registration["boundary_identity_sha256"] = "c" * 64
        with tempfile.TemporaryDirectory() as output:
            with patch("tools.compare_td_river_shapes.load_sample", return_value=sample), \
                 patch("tools.compare_td_river_shapes.load_generated_td_source", return_value={"metadata": actual_registration}), \
                 patch("tools.compare_td_river_shapes.load_component_geometry") as geometry_loader:
                with self.assertRaisesRegex(ValueError, "boundary registration differs"):
                    compare_components("old.npz", "new.npz", "sample-1", output, [1, 2])
                geometry_loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
