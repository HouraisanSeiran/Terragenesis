import copy
import tempfile
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.channel_geometry import build_watershed_sections, load_watershed_sections, save_watershed_sections, validate_watershed_sections


def fixture():
    shape = (7, 7)
    height = np.full(shape, 100.)
    height.ravel()[[23, 17, 24, 25]] = [90., 90., 85., 80.]
    receiver = np.full(height.size, -1, dtype=np.int64)
    for first, second in ((22, 23), (16, 23), (30, 23), (23, 24),
                          (9, 10), (11, 10), (10, 17), (17, 24), (24, 25)):
        receiver[first] = second
    owner = np.zeros(shape, dtype=np.int64)
    owner.ravel()[0] = 1
    hierarchy = {"identity_sha256": "hierarchy", "metadata": {
        "spacing_m": 30., "origin_m_xz": [0., 0.], "source_identity_sha256": "source"},
        "arrays": {"height_m": height, "receiver": receiver, "contribution_owner": owner,
                   "valid_mask": np.ones(shape, dtype=bool), "protected_mask": np.zeros(shape, dtype=bool),
                   "open_boundary_mask": np.zeros(shape, dtype=bool), "face_cells": np.array([[0, 1]])}}
    topology = {"identity_sha256": "topology", "arrays": {
        "leaf_ids": np.array([0, 1]), "leaf_area_m2": np.array([48 * 900., 900.])},
        "faces": [{"face_id": "external", "face_index": 0, "leaf_ids": [0, 1], "cell_ids": [0, 1]}]}
    ordinary = {"identity_sha256": "ordinary", "metadata": {"duration_s": 100.},
        "arrays": {"outflow_volume_m3": np.array([[48., 1.]]), "stage_m": np.array([[0., 0.], [0., 0.]]),
                   "face_forward_m3": np.array([[2.]]), "face_reverse_m3": np.array([[5.]])}}
    nodes = []
    for cell, area in ((23, 3600.), (17, 3600.), (24, 8100.), (25, 9000.), (1, 900.)):
        nodes.append({"node_id": f"cell:{cell}", "cell_id": cell, "leaf_id": 0,
                      "xyz_m": [float(cell % 7 * 30), float(height.ravel()[cell]), float(cell // 7 * 30)],
                      "local_upstream_area_m2": area, "kinds": ["land_channel"] if cell != 1 else ["spill"]})
    lookup = {node["cell_id"]: node for node in nodes}
    arcs = []
    for first, second in ((23, 24), (24, 25)):
        arcs.append({"arc_id": f"receiver:{first}:{second}", "kind": "land_channel",
                     "node_ids": [f"cell:{first}", f"cell:{second}"], "cell_ids": [first, second],
                     "xyz_m": [lookup[first]["xyz_m"], lookup[second]["xyz_m"]], "leaf_id": 0,
                     "face_id": None, "is_main_path": True, "channel_candidate": True})
    arcs.append({"arc_id": "support", "kind": "source_lake_approach", "node_ids": ["cell:1"],
                 "cell_ids": [1], "xyz_m": [lookup[1]["xyz_m"]], "leaf_id": 0,
                 "face_id": "external", "is_main_path": True, "channel_candidate": False})
    paths = {"identity_sha256": "paths", "graph_identity_sha256": "graph-with-strong",
             "nodes": nodes, "arcs": arcs, "lakes": [], "selected_leaf_ids": [0],
             "parameters": {"minimum_area_m2": 3600.}}
    return paths, hierarchy, topology, ordinary


class WatershedSectionsTests(unittest.TestCase):
    def test_shared_bank_mesh_actual_net_proxy_and_shape_identity(self):
        paths, hierarchy, topology, ordinary = fixture()
        original = hierarchy["arrays"]["height_m"].copy()
        result = build_watershed_sections(paths, hierarchy, topology, ordinary)
        sections = {section["node_id"]: section for section in result["node_sections"]}
        self.assertAlmostEqual(sections["cell:1"]["incoming_exchange_q_m3_s"], .03)
        self.assertEqual(result["exchange_injections"][0]["receiver_cell_id"], 1)
        self.assertEqual(result["exchange_injections"][0]["net_volume_m3"], 3.)
        self.assertGreater(len(result["mesh"]["triangles"]), 0)
        self.assertEqual(len(result["mesh"]["node_vertex_indices"]["cell:24"]), 4)
        shared = [edge for edge in result["edge_sections"] if "cell:24" in edge["node_ids"]]
        self.assertEqual(len(shared), 2)
        for edge in shared:
            index = edge["node_ids"].index("cell:24")
            self.assertEqual(edge["cross_section_xyz_m"][index], sections["cell:24"]["cross_section_xyz_m"])
        self.assertEqual(result["support_arcs"], [paths["arcs"][-1]])
        self.assertEqual(sections["cell:1"]["bed_m"], 100.)
        for section in result["node_sections"]:
            self.assertFalse(section["flow_regime_certified"])
        changed = copy.deepcopy(paths)
        changed["graph_identity_sha256"] = "different-strong-only"
        changed["identity_sha256"] = "different-composite"
        other = build_watershed_sections(changed, hierarchy, topology, ordinary)
        self.assertEqual(result["candidate_shape_identity_sha256"], other["candidate_shape_identity_sha256"])
        self.assertNotEqual(result["identity_sha256"], other["identity_sha256"])
        np.testing.assert_array_equal(hierarchy["arrays"]["height_m"], original)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sections.json"
            save_watershed_sections(result, path)
            self.assertEqual(load_watershed_sections(path), result)

    def test_refusals_fine_resolution_and_tampered_or_nonfinite_json(self):
        paths, hierarchy, topology, ordinary = fixture()
        hierarchy["arrays"]["protected_mask"][2, 4] = True
        topology["arrays"]["leaf_area_m2"][0] -= 900.
        ordinary["arrays"]["outflow_volume_m3"][0, 0] -= 1.
        result = build_watershed_sections(paths, hierarchy, topology, ordinary)
        self.assertTrue(any("protected_source_coverage" in request["refusal_reasons"] for request in result["fine_requests"]))
        for request in result["fine_requests"]:
            self.assertLessEqual(request["target_spacing_m"], request["width_m"] / 2)
            self.assertFalse(request["fine_dem_available"])
        anchored = copy.deepcopy(paths)
        anchored["nodes"][0]["kinds"].append("spill")
        refused = build_watershed_sections(anchored, hierarchy, topology, ordinary)
        self.assertTrue(any("anchor_cut_conflict" in reach["rejection_reasons"] for reach in refused["reach_diagnostics"]))
        junction = copy.deepcopy(paths)
        lookup = {node["node_id"]: node for node in junction["nodes"]}
        junction["arcs"].append({"arc_id": "receiver:17:24", "kind": "land_channel",
            "node_ids": ["cell:17", "cell:24"], "cell_ids": [17, 24],
            "xyz_m": [lookup["cell:17"]["xyz_m"], lookup["cell:24"]["xyz_m"]],
            "leaf_id": 0, "face_id": None, "is_main_path": False, "channel_candidate": True})
        junction_result = build_watershed_sections(junction, hierarchy, topology, ordinary)
        self.assertTrue(all("needs_junction_patch" in reach["rejection_reasons"] for reach in junction_result["reach_diagnostics"]))
        self.assertEqual(junction_result["mesh"]["triangles"], [])
        for field, value in (("hydraulic_ready", True), ("ordinary_duration_s", float("nan")),
                             ("identity_sha256", "tampered")):
            damaged = copy.deepcopy(result)
            damaged[field] = value
            with self.assertRaises(ValueError):
                validate_watershed_sections(damaged)


if __name__ == "__main__":
    unittest.main()
