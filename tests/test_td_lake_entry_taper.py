import copy
import unittest

import numpy as np

from terrain_pipeline.td_lake_entry_taper import build_lake_entry_tapers, sample_source


def fixture():
    height = np.tile(np.array([6., 5., 4., 3., 2.]), (5, 1))
    hierarchy = {"identity_sha256": "hierarchy", "metadata": {"spacing_m": 1., "origin_m_xz": [0., 0.]},
                 "arrays": {"height_m": height, "valid_mask": np.ones((5, 5), bool),
                            "protected_mask": np.zeros((5, 5), bool), "open_boundary_mask": np.zeros((5, 5), bool),
                            "contribution_owner": np.zeros((5, 5), int), "receiver": np.arange(25).reshape(5, 5) + 1}}
    nodes = [{"node_id": f"cell:{cell}", "cell_id": cell, "xyz_m": [float(column), float(height[2, column]), 2.]}
             for column, cell in ((0, 10), (1, 11), (2, 12), (3, 13))]
    paths = {"identity_sha256": "paths", "hierarchy_identity_sha256": "hierarchy", "ordinary_identity_sha256": "rain",
             "selected_leaf_ids": [0], "nodes": nodes,
             "lakes": [{"leaf_id": 0, "covered_cell_ids": [], "ordinary_stage_max_m": 0.}],
             "arcs": [{"arc_id": "land", "kind": "land_channel", "node_ids": ["cell:11", "cell:12"]},
                      {"arc_id": "entry", "kind": "lake_entry_support", "node_ids": ["cell:12", "cell:13"], "leaf_id": 0}]}
    profile = [[1., 5., 1.5], [1., 4.8, 1.75], [1., 4.8, 2.25], [1., 5., 2.5]]
    sections = {"identity_sha256": "sections", "hierarchy_identity_sha256": "hierarchy", "ordinary_identity_sha256": "rain",
                "composite_parent_identity": {"paths": "paths"}, "selected_leaf_ids": [0],
                "edge_sections": [{"arc_id": "accepted", "node_ids": ["cell:10", "cell:11"],
                                   "cross_section_xyz_m": [profile, profile]}]}
    return paths, sections, hierarchy


class LakeEntryTaperTests(unittest.TestCase):
    def test_exact_port_source_anchor_and_unmodified_parent(self):
        paths, sections, hierarchy = fixture()
        original = copy.deepcopy(sections)
        result = build_lake_entry_tapers(paths, sections, hierarchy)
        entry = result["entries"][0]
        self.assertEqual(entry["status"], "candidate")
        vertices = np.asarray(entry["vertices_xyz_m"]).reshape(-1, 5, 3)
        np.testing.assert_array_equal(vertices[0, [0, 1, 3, 4]], entry["accepted_port_xyz_m"])
        np.testing.assert_array_equal(vertices[-1, :, 1], np.full(5, 4.))
        self.assertTrue(np.all(np.diff(vertices[:, 2, 1]) <= 0))
        self.assertEqual(sections, original)
        self.assertFalse(result["hydraulic_ready"])

    def test_zero_weight_corners_and_protection_rejection(self):
        paths, sections, hierarchy = fixture()
        hierarchy["arrays"]["protected_mask"][3, 2] = True
        np.testing.assert_array_equal(sample_source(hierarchy, [0], [[1., 2.]]), [5.])
        result = build_lake_entry_tapers(paths, sections, hierarchy)
        self.assertEqual(result["entries"][0]["rejection_reasons"], ["protected_source_coverage"])
        hierarchy["arrays"]["protected_mask"].fill(False)
        paths["lakes"][0]["ordinary_stage_max_m"] = 6.
        result = build_lake_entry_tapers(paths, sections, hierarchy)
        self.assertEqual(result["entries"][0]["rejection_reasons"], ["lake_wet_bed_cut_refused"])

    def test_uphill_return_and_ambiguous_ports_refused(self):
        paths, sections, hierarchy = fixture()
        for point in sections["edge_sections"][0]["cross_section_xyz_m"][-1][1:3]:
            point[1] = 3.9
        result = build_lake_entry_tapers(paths, sections, hierarchy)
        self.assertEqual(result["entries"][0]["status"], "refused")
        sections["edge_sections"].append(copy.deepcopy(sections["edge_sections"][0]))
        result = build_lake_entry_tapers(paths, sections, hierarchy)
        self.assertEqual(result["entries"][0]["rejection_reasons"], ["missing_or_ambiguous_accepted_port"])
        sections["composite_parent_identity"]["paths"] = "other-paths"
        with self.assertRaisesRegex(ValueError, "sections_paths_identity_mismatch"):
            build_lake_entry_tapers(paths, sections, hierarchy)


if __name__ == "__main__":
    unittest.main()
