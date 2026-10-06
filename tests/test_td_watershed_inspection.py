from copy import deepcopy
import inspect
import unittest

import numpy as np

from tools import export_td_watershed_inspection as exporter


def fixture():
    nodes = [{"node_id": "cell:0", "cell_id": 0, "leaf_id": 1, "xyz_m": [0., 2., 0.]},
             {"node_id": "cell:1", "cell_id": 1, "leaf_id": 1, "xyz_m": [1., 1., 0.]}]
    arc = {"arc_id": "receiver:0:1", "kind": "land_channel", "channel_candidate": True,
           "node_ids": [node["node_id"] for node in nodes], "cell_ids": [0, 1],
           "xyz_m": [node["xyz_m"] for node in nodes]}
    paths = {"schema": "td-watershed-paths-v1", "grid_shape": [1, 2],
             "origin_m_xz": [0., 0.], "spacing_m": 1., "nodes": nodes, "arcs": [arc]}
    mesh = {"vertices_xyz_m": [[0., 1., 0.], [1., 1., 0.], [0., 1., 1.]],
            "triangles": [[0, 1, 2]], "triangle_arc_ids": [arc["arc_id"]], "node_vertex_indices": {"cell:0": [0]}}
    sections = {"schema": "td-watershed-sections-v1", "mesh": mesh,
                "node_sections": [{"node_id": node["node_id"], "source_xyz_m": node["xyz_m"],
                                   "cross_section_xyz_m": [mesh["vertices_xyz_m"][0]]} for node in nodes], "support_arcs": [],
                "edge_sections": [{"arc_id": arc["arc_id"], "node_ids": arc["node_ids"], "triangle_indices": [0]}],
                "reach_diagnostics": [{"arc_id": arc["arc_id"], "status": "geometry_candidate", "rejection_reasons": []}]}
    arrays = {"height_m": np.array([[2., 1.]]), "valid_mask": np.ones((1, 2), dtype=bool),
              "receiver": np.array([1, -1]), "contribution_owner": np.array([[1, 1]])}
    return paths, sections, arrays, {"origin_m_xz": [0., 0.], "spacing_m": 1.}


class WatershedInspectionTest(unittest.TestCase):
    def test_illegal_graph_is_rejected(self):
        for change in ("missing_node", "duplicate_node", "fake_height", "wrong_receiver", "support_as_water"):
            with self.subTest(change=change):
                paths, sections, arrays, metadata = fixture()
                if change == "missing_node":
                    paths["arcs"][0]["node_ids"][1] = "absent"
                elif change == "duplicate_node":
                    paths["nodes"].append(deepcopy(paths["nodes"][0]))
                elif change == "fake_height":
                    paths["nodes"][0]["xyz_m"][1] = 99.
                elif change == "wrong_receiver":
                    arrays["receiver"][0] = -1
                else:
                    paths["arcs"][0]["kind"] = "lake_support"
                with self.assertRaises(ValueError):
                    exporter.validate_geometry(paths, sections, arrays, metadata)

    def test_saved_mesh_references_and_no_fabrication(self):
        paths, sections, arrays, metadata = fixture()
        exporter.validate_geometry(paths, sections, arrays, metadata)
        before = deepcopy(sections)
        review = {"layers": {"saved_bed_mesh": sections["mesh"]}, "pins": {"sections": {}}, "limitations": []}
        artifact = exporter.mesh_caseartifact(review)
        self.assertEqual(artifact["mesh"]["vertices"], sections["mesh"]["vertices_xyz_m"])
        self.assertEqual(artifact["mesh"]["triangles"], sections["mesh"]["triangles"])
        self.assertIsNone(artifact["mesh"]["water"])
        self.assertEqual(sections, before)
        for change in ("vertex", "owner", "edge_index", "duplicate_triangle"):
            with self.subTest(change=change):
                invalid = deepcopy(sections)
                if change == "vertex":
                    invalid["mesh"]["triangles"][0][2] = 99
                elif change == "owner":
                    invalid["mesh"]["triangle_arc_ids"][0] = "invented"
                elif change == "edge_index":
                    invalid["edge_sections"][0]["triangle_indices"] = [99]
                else:
                    invalid["edge_sections"][0]["triangle_indices"] = [0, 0]
                with self.assertRaises(ValueError):
                    exporter.validate_geometry(paths, invalid, arrays, metadata)
        source = inspect.getsource(exporter)
        self.assertNotIn("terrain_pipeline", source)
        self.assertNotIn("scipy", source)


if __name__ == "__main__":
    unittest.main()
