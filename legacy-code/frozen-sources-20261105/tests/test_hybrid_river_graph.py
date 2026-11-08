import json
import unittest
from dataclasses import FrozenInstanceError

from terrain_pipeline.hybrid_river_graph import build_graph, load_graph, native_bed_pieces, port_floor_xyz


def port(key, nodes, x):
    pieces = []
    for ordinal in range(3):
        pieces.append({"native_pieces": [{"interval_t01": [0, 1],
            "start_xz_m": [x, ordinal], "end_xz_m": [x, ordinal + 1],
            "source": {"source_coefficients_m_t012": [10, 0, 0.4 if ordinal == 1 else 0]},
            "depth_coefficients_m_t01": [0.2, 0]}]})
    return {"arc_id": key, "identity_sha256": key, "midpoint_xz_m": [x, 1.5], "node_ids": nodes,
            "profile": {"profile_segments": pieces}, "upstream_parent_section": {"anchor": False}, "rejection_reasons": []}


class HybridGraphTests(unittest.TestCase):
    def fixtures(self):
        nodes = [{"node_id": str(ordinal), "xyz_m": [ordinal, 10, 0], "source_note": "unchanged"} for ordinal in range(4)]
        arcs = [{"arc_id": str(ordinal), "node_ids": [str(ordinal), str(ordinal + 1)], "q_prior_not_new_supply": 0.1} for ordinal in range(3)]
        graph = {"nodes": nodes, "arcs": arcs}
        manifest = {"selected_node_ids": [node["node_id"] for node in nodes]}
        topology = {"joined_arc_ids": [arc["arc_id"] for arc in arcs]}
        ports = {arc["arc_id"]: port(arc["arc_id"], arc["node_ids"], int(arc["arc_id"])) for arc in arcs}
        audit = {"status": "passed", "complete_actual_reverse_midpoint_functions_verified": True,
                 "selected_node_ids": manifest["selected_node_ids"],
                 "ports": {key: {"identity_sha256": key} for key in ports},
                 "nodes": {node["node_id"]: {"identity_sha256": "node:" + node["node_id"]} for node in nodes}}
        saved_nodes = {}
        for node in nodes:
            key = node["node_id"]
            incident = [arc for arc in arcs if key in arc["node_ids"]]
            saved_nodes[key] = {"identity_sha256": "node:" + key, "status": "candidate", "source_xyz_m": node["xyz_m"], "center_depth_m": 0.2,
                "arms": [{"arc_id": arc["arc_id"], "midpoint_port_identity_sha256": arc["arc_id"]} for arc in incident],
                "port_proofs": [{"arc_id": arc["arc_id"], "midpoint_port_identity_sha256": arc["arc_id"],
                    "segments": [{"profile_segment_index": ordinal, "pieces": [{"side": {"triangle_index": index}}]} for ordinal in range(3)]} for index, arc in enumerate(incident)],
                "geometry": {"triangle_roles": [{"region": "half_arm", "arc_id": arc["arc_id"]} for arc in incident] + [{"region": "node_ring"}]}}
        self.saved_nodes = saved_nodes
        return graph, manifest, topology, audit, ports

    def test_preserves_surface_and_immutable_native_midpoint(self):
        arguments = self.fixtures()
        graph = build_graph(*arguments, {}, "0", "2", self.saved_nodes)
        record = graph.to_record()
        self.assertEqual(record, load_graph(record).to_record())
        self.assertEqual(graph.bypass_arc_ids, ("0", "1", "2"))
        self.assertEqual([json.loads(node.source_record_json) for node in graph.nodes if node.kind == "surface"], arguments[0]["nodes"])
        self.assertTrue(all(arc.hydraulic_role == "context_only" for arc in graph.arcs if arc.kind == "surface"))
        active = {arc.node_ids[0]: arc.node_ids[1] for arc in graph.arcs if arc.hydraulic_role == "sample_route"}
        self.assertEqual(active[active[active["0"]]], "3")
        self.assertEqual(graph.nodes[0].source_xyz_m[1], 10)
        self.assertEqual(graph.nodes[0].bed_xyz_m[1], 9.8)
        with self.assertRaises(FrozenInstanceError):
            graph.nodes[0].kind = "spring"
        self.assertAlmostEqual(port_floor_xyz(arguments[4]["0"])[1], 9.9)
        self.assertEqual(native_bed_pieces(arguments[4]["0"])[1]["bed_coefficients_m_t012"], [9.8, 0, 0.4])

    def test_rejects_fake_attachment_anchor_reverse_and_tampering(self):
        arguments = self.fixtures()
        with self.assertRaises(ValueError):
            build_graph(*arguments, {}, "2", "0", self.saved_nodes)
        arguments[4]["0"]["upstream_parent_section"]["anchor"] = True
        with self.assertRaises(ValueError):
            build_graph(*arguments, {}, "0", "2", self.saved_nodes)
        arguments = self.fixtures()
        arguments[2]["joined_arc_ids"].remove("0")
        with self.assertRaises(ValueError):
            build_graph(*arguments, {}, "0", "2", self.saved_nodes)
        arguments = self.fixtures()
        record = build_graph(*arguments, {}, "0", "2", self.saved_nodes).to_record()
        record["nodes"][0]["xyz_m"][1] = -1
        with self.assertRaises(ValueError):
            load_graph(record)


if __name__ == "__main__":
    unittest.main()
