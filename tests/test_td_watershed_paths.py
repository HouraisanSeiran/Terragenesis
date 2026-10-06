from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_overflow import _boundary_faces, _physical_faces
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_lake_outlet_forest import build_outlet_forest
from terrain_pipeline.td_lake_spill_geometry import trace_engineering_outlet, trace_spill_connection
from terrain_pipeline.td_lake_spill_graph import digest, sampled_stage
from terrain_pipeline.td_watershed_paths import (
    FLAGS, build_watershed_paths, load_watershed_paths, save_watershed_paths,
    validate_watershed_paths,
)


def fixture():
    bed = np.array([[2., 3., 6., 4., 3., 1.]])
    opened = np.array([[False, False, False, False, False, True]])
    hierarchy = build_basin_hierarchy(make_td_source(
        bed, spacing_m=2, origin_m_xz=(10, 20), open_boundary_mask=opened))
    owners = hierarchy["arrays"]["contribution_owner"].ravel()
    leaves = np.unique(owners).tolist()
    lookup = {leaf: position for position, leaf in enumerate(leaves)}
    source, root = int(owners[0]), int(owners[-1])
    face = _physical_faces(hierarchy, leaves, lookup)[0]
    boundary = _boundary_faces(hierarchy, leaves, lookup)[0]
    direction = 1 if face["leaf_ids"][0] == source else -1
    stages = np.zeros((289, 2))
    stages[:, lookup[source]] = 6.
    stages[:, lookup[root]] = 1.
    stages[200, lookup[root]] = 2.
    forward, reverse = np.zeros((288, 1)), np.zeros((288, 1))
    (forward if direction == 1 else reverse)[0, 0] = 1.
    engineering = np.zeros((288, 1))
    engineering[0, 0] = 1.
    metadata = {"schema": "td-basin-runoff-exchange-v1", "steps": 288,
                "duration_s": 86400., "timestep_s": 300.,
                "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
                "topology_identity_sha256": "a" * 64,
                "hydraulic_ready": False, "transient_converged": False,
                "natural_outlet_verified": False, "publishable": False}
    event_arrays = {"stage_m": stages, "face_forward_m3": forward,
                    "face_reverse_m3": reverse, "engineering_boundary_outflow_m3": engineering}
    ordinary = {"arrays": event_arrays, "metadata": metadata,
                "identity_sha256": identity(event_arrays, metadata)}
    source_sample = sampled_stage(ordinary, lookup[source], direction * (forward[:, 0] - reverse[:, 0]))
    root_sample = sampled_stage(ordinary, lookup[root], engineering[:, 0])
    edge = {**face, "routing_eligible": True, "source_leaf_id": source, "receiver_leaf_id": root,
            "ordinary": {"direction": direction, "net_m3": float(direction)},
            "sampled_source_stage": source_sample,
            "geometry": trace_spill_connection(hierarchy, face, source, root, source_stage_m=6.)}
    outlet = {**boundary, "routing_eligible": True, "outflow_m3": 1.,
              "sampled_source_stage": root_sample,
              "geometry": trace_engineering_outlet(hierarchy, boundary, source_stage_m=1.)}
    nodes = []
    for leaf in leaves:
        cells = np.flatnonzero(owners == leaf)
        terminal = int(cells[hierarchy["arrays"]["receiver"][cells] < 0][0])
        nodes.append({"leaf_id": leaf, "terminal_cell_id": terminal,
                      "exclusive_area_m2": len(cells) * 4., "blocked_reasons": [],
                      "ordinary_stage_max_m": float(stages[:, lookup[leaf]].max())})
    forest = build_outlet_forest(leaves, [node["exclusive_area_m2"] for node in nodes],
                                [{"face_id": face["face_id"], "source_leaf_id": source,
                                  "receiver_leaf_id": root, "net_m3": 1.}],
                                [{"leaf_id": root, "cell_id": boundary["cell_id"], "outflow_m3": 1.}])
    graph = {"schema": "td-lake-spill-graph-v1", "nodes": nodes, "edges": [edge],
             "outlets": [outlet], "routing_forest": forest,
             "source_identity_sha256": metadata["source_identity_sha256"],
             "hierarchy_identity_sha256": hierarchy["identity_sha256"],
             "topology_identity_sha256": metadata["topology_identity_sha256"],
             "event_identity_sha256": {"ordinary": ordinary["identity_sha256"]},
             **{name: False for name in FLAGS}}
    graph["identity_sha256"] = digest(graph)
    return graph, hierarchy, ordinary


class WatershedPathsTests(unittest.TestCase):
    def test_shared_continuous_typed_receiver_local_area_and_cold_roundtrip(self):
        graph, hierarchy, ordinary = fixture()
        original_graph = deepcopy(graph)
        original_bed = hierarchy["arrays"]["height_m"].copy()
        paths = build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.)
        self.assertEqual(paths, build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.))
        self.assertTrue(validate_watershed_paths(paths, graph, hierarchy, ordinary))
        nodes = {node["node_id"]: node for node in paths["nodes"]}
        self.assertEqual(len(nodes), len(paths["nodes"]))
        land = [arc for arc in paths["arcs"] if arc["channel_candidate"]]
        self.assertEqual([arc["cell_ids"] for arc in land], [[3, 4]])
        self.assertEqual(land[0]["local_upstream_area_m2"], 4.)
        self.assertEqual(nodes["cell:4"]["local_upstream_area_m2"], 8.)
        self.assertEqual(nodes["cell:5"]["local_upstream_area_m2"], 12.)
        self.assertIn("lake_entry", nodes["cell:5"]["kinds"])
        self.assertIn("lake_entry", nodes["cell:4"]["kinds"])
        self.assertIn("lake_interface", nodes["cell:4"]["lake_interfaces"])
        self.assertIn("engineering", nodes["cell:5"]["lake_interfaces"])
        self.assertIn("spill", nodes["cell:3"]["lake_interfaces"])
        for arc in paths["arcs"]:
            if arc["kind"] != "land_channel":
                self.assertFalse(arc["channel_candidate"])
            for node_id, xyz in zip(arc["node_ids"], arc["xyz_m"]):
                self.assertEqual(xyz, nodes[node_id]["xyz_m"])
        wet = next(arc for arc in paths["arcs"] if arc["kind"] == "source_lake_approach")
        self.assertEqual(wet["cell_ids"], [0, 1, 2])
        self.assertEqual(wet["source_geometry"]["source_stage_m"], 6.)
        self.assertTrue(wet["source_geometry"]["all_samples_stage_covered"])
        entry = next(arc for arc in paths["arcs"] if arc["arc_id"] == "receiver:4:5")
        self.assertEqual(entry["kind"], "lake_entry_support")
        self.assertEqual(entry["lake_interface"], {"land_node_id": "cell:4", "wet_node_id": "cell:5",
                                                  "support_arc_id": "receiver:4:5"})
        self.assertTrue(all(paths[name] is False for name in FLAGS))
        self.assertEqual(graph, original_graph)
        np.testing.assert_array_equal(hierarchy["arrays"]["height_m"], original_bed)
        json.dumps(paths, allow_nan=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paths.json"
            save_watershed_paths(paths, path)
            loaded = load_watershed_paths(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                          expected_identity=paths["identity_sha256"], graph=graph,
                                          hierarchy=hierarchy, ordinary=ordinary)
            self.assertEqual(loaded, paths)
            with self.assertRaises(FileExistsError):
                save_watershed_paths(paths, path)

    def test_stage_identity_geometry_protection_and_budget_rejections(self):
        graph, hierarchy, ordinary = fixture()
        paths = build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.)
        for case in ("source", "parent", "stage", "geometry", "unknown", "protected", "nan", "flags"):
            with self.subTest(case=case):
                candidate_graph, candidate_hierarchy, candidate_event = deepcopy((graph, hierarchy, ordinary))
                if case == "source":
                    candidate_graph["source_identity_sha256"] = "b" * 64
                elif case == "parent":
                    candidate_graph["routing_forest"]["records"][1]["parent_face_id"] = "wrong"
                elif case == "stage":
                    candidate_event["arrays"]["stage_m"][200, 0] += 1.
                    candidate_event["identity_sha256"] = identity(candidate_event["arrays"], candidate_event["metadata"])
                elif case == "geometry":
                    candidate_graph["edges"][0]["geometry"]["downhill_terrain_approach"]["xyz_m"][0][1] += 1.
                elif case == "unknown":
                    candidate_hierarchy["arrays"]["node_unknown_contact"][0] = True
                elif case == "protected":
                    candidate_hierarchy["arrays"]["protected_mask"].ravel()[3] = True
                elif case == "nan":
                    candidate_event["arrays"]["stage_m"][0, 0] = float("nan")
                elif case == "flags":
                    candidate_graph["publishable"] = True
                candidate_graph["identity_sha256"] = digest({key: value for key, value in candidate_graph.items()
                                                               if key != "identity_sha256"})
                with self.assertRaises(ValueError):
                    build_watershed_paths(candidate_graph, candidate_hierarchy, candidate_event, minimum_area_m2=4.)
        with patch("terrain_pipeline.td_watershed_paths.MAX_ARCS", 1), self.assertRaises(MemoryError):
            build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=4.)
        for minimum in (0., -1., float("inf"), float("nan"), True):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                build_watershed_paths(graph, hierarchy, ordinary, minimum_area_m2=minimum)
        corrupted = deepcopy(paths)
        corrupted["arcs"][0]["xyz_m"][0][1] += 1.
        corrupted["identity_sha256"] = digest({key: value for key, value in corrupted.items() if key != "identity_sha256"})
        with self.assertRaises(ValueError):
            validate_watershed_paths(corrupted)
        with self.assertRaises(ValueError):
            validate_watershed_paths(paths, graph=graph)


if __name__ == "__main__":
    unittest.main()
