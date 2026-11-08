from copy import deepcopy
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.td_shared_port_channel import (
    FragmentComposer, _cut_at, build_midpoint_port, build_node_piece, select_fragment)
from test_td_ported_junction import fixture


def branched_fixture():
    hierarchy, paths, sections = fixture()
    rows, columns = np.indices((21, 21))
    hierarchy["arrays"]["height_m"] = 10. + .01 * columns + .02 * rows + .002 * columns * rows
    hierarchy["identity_sha256"] = identity(hierarchy["arrays"], hierarchy["metadata"])
    locations = {"upstream": [-6., 0.], "turn": [0., 0.], "branch": [0., 6.],
        "left": [-6., 6.], "right": [6., 6.], "top": [0., 9.]}
    nodes = [{"node_id": node_id, "xyz_m": [point[0], 10., point[1]], "kinds": ["land_channel"]}
        for node_id, point in locations.items()]
    pairs = [("upstream", "turn"), ("turn", "branch"), ("left", "branch"), ("top", "branch"), ("branch", "right")]
    paths.update(nodes=nodes, arcs=[{"arc_id": first + ":" + second, "kind": "land_channel", "node_ids": [first, second]}
        for first, second in pairs], hierarchy_identity_sha256=hierarchy["identity_sha256"])
    sections.update(node_sections=[{"node_id": node["node_id"], "source_xyz_m": node["xyz_m"],
        "depth_m": .08, "width_m": .4, "representative_q_m3_s": .01, "anchor": False,
        "cross_section_xyz_m": [], "rejection_reasons": ["needs_junction_patch"] if node["node_id"] in ("branch", "turn") else []}
        for node in nodes], hierarchy_identity_sha256=hierarchy["identity_sha256"],
        mesh={"vertices_xyz_m": [], "triangles": [], "triangle_arc_ids": []}, edge_sections=[])
    return hierarchy, paths, sections


WET = {"covered_native_cell_ids": [], "stage_by_leaf": []}


class SharedPortChannelTests(unittest.TestCase):
    def test_shared_midpoints_real_right_turn_four_arm_branch_and_terminal_continuity(self):
        parents = branched_fixture()
        graph, selection = select_fragment(*parents, wet_protection=WET)
        self.assertEqual(len(selection["selected_node_ids"]), 6)
        ports = {arc_id: build_midpoint_port(*parents, arc_id=arc_id, wet_protection=WET)
            for arc_id in selection["selected_arc_ids"]}
        composer = FragmentComposer(parents[1], parents[2], selection)
        pieces = {}
        for node_id in selection["selected_node_ids"]:
            local = [port for port in ports.values() if node_id in port["node_ids"]]
            piece = build_node_piece(*parents, node_id=node_id, midpoint_ports=local, wet_protection=WET)
            self.assertEqual(piece["status"], "candidate", (node_id, piece["rejection_reasons"]))
            pieces[node_id] = piece
            row = composer.add_node(piece)
            self.assertEqual(row["composition_status"], "selected", (node_id, row["rejection_reasons"]))
            self.assertTrue(piece["source_functions"])
            for function in piece["source_functions"]:
                for fan in function["fans"]:
                    self.assertTrue(all(0. <= cut <= 4. for cut in fan["depth_at_vertices_m"]))
        self.assertTrue(pieces["turn"]["geometry"]["outer_bank_control_vertex_ids"])
        self.assertEqual(len(pieces["turn"]["inner_port_proofs"]), 2)
        for proof in pieces["turn"]["inner_port_proofs"]:
            self.assertEqual(len(proof["profile_segments"]), 3)
            self.assertTrue(all(piece["reverse_seam"] for segment in proof["profile_segments"] for piece in segment["native_pieces"]))
        self.assertEqual(pieces["branch"]["degree"], 4)
        self.assertEqual(len(pieces["upstream"]["geometry"]["terminal_vertex_ids"]), 4)
        self.assertFalse(pieces["upstream"]["terminal_evidence"]["hydraulic_boundary_claimed"])
        bundle = composer.finish([])
        self.assertEqual(bundle["topology"]["joined_arc_count"], 5)
        self.assertEqual(bundle["topology"]["component_count"], 1)
        self.assertEqual(bundle["topology"]["longest_directed_path"]["plan_length_m"], 18.)
        self.assertEqual(bundle["topology"]["branch_node_ids"], ["branch"])
        self.assertEqual(len(bundle["topology"]["branch_arc_ids"]), 2)
        for seam in bundle["manifest"]["shared_midpoint_seams"]:
            self.assertEqual({piece["profile_segment_index"] for piece in seam["native_pieces"]}, {0, 1, 2})
            self.assertTrue(all(piece["reverse_seam"] for piece in seam["native_pieces"]))
        self.assertFalse(bundle["mesh"]["old06_mesh_included"])
        self.assertFalse(bundle["topology"]["verified"])

    def test_illegal_cut_and_wet_source_refuse_without_endpoint_depth_clamping(self):
        parents = branched_fixture()
        graph, selection = select_fragment(*parents, wet_protection=WET)
        self.assertEqual(_cut_at(.6909995322273517, 0., 1.), 0.)
        self.assertLess(_cut_at(-.01, 0., 0.), 0.)
        for depth in (-.01, 4.01):
            changed = deepcopy(parents[2])
            changed["node_sections"][0]["depth_m"] = depth
            port = build_midpoint_port(parents[0], parents[1], changed,
                arc_id="upstream:turn", wet_protection=WET)
            self.assertEqual(port["status"], "refused")
        wet = {"covered_native_cell_ids": list(range(441)), "stage_by_leaf": []}
        port = build_midpoint_port(*parents, arc_id="upstream:turn", wet_protection=wet)
        self.assertEqual(port["status"], "refused")
        piece = build_node_piece(*parents, node_id="upstream", midpoint_ports=[port], wet_protection=wet)
        self.assertEqual(piece["status"], "refused")
        self.assertEqual(piece["geometry"]["triangles"], [])


if __name__ == "__main__":
    unittest.main()
