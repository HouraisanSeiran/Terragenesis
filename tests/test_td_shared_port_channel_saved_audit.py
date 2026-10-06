from copy import deepcopy
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_td_shared_port_channel import branched_fixture
from terrain_pipeline.td_shared_port_channel import build_midpoint_port, build_node_piece
from tools.td_shared_port_channel_saved_audit import (
    FragmentAudit, audit_midpoint, audit_node, independent_selection,
    check_identity, seal, shared_port, audit_vertices)

WET = dict(covered_native_cell_ids=[], stage_by_leaf=[])


def saved_fixture():
    hierarchy, paths, sections = branched_fixture()
    graph, selection = independent_selection(hierarchy, paths, sections, WET, 128)
    ports = {arc: build_midpoint_port(hierarchy, paths, sections, arc_id=arc, wet_protection=WET)
             for arc in selection["selected_arc_ids"]}
    records = {}
    for identifier in selection["selected_node_ids"]:
        local = [port for port in ports.values() if identifier in port["node_ids"]]
        records[identifier] = build_node_piece(hierarchy, paths, sections, node_id=identifier,
            midpoint_ports=local, wet_protection=WET)
    return hierarchy, paths, sections, selection, ports, records


class SharedPortSavedAuditTests(unittest.TestCase):
    def test_independent_right_turn_four_arm_terminal_native_function_and_evidence_graph(self):
        hierarchy, paths, sections, selection, ports, records = saved_fixture()
        for port in ports.values():
            self.assertTrue(audit_midpoint(port, paths, sections, hierarchy, WET, {}))
        composer = FragmentAudit()
        for identifier in selection["selected_node_ids"]:
            record = records[identifier]
            local = [port for port in ports.values() if identifier in port["node_ids"]]
            result, descriptors = audit_node(record, local, paths, sections, hierarchy, WET, {}, [])
            self.assertTrue(result["source_native_geometry_verified"])
            self.assertEqual(composer.consider(record, None, descriptors)["composition_status"], "selected")
        self.assertTrue(records["turn"]["geometry"]["outer_bank_control_vertex_ids"])
        self.assertEqual(records["branch"]["degree"], 4)
        self.assertFalse(records["upstream"]["terminal_evidence"]["hydraulic_boundary_claimed"])
        manifest, topology = composer.finish(paths, sections, selection, [], {})
        self.assertEqual(topology["joined_arc_count"], 5)
        self.assertEqual(topology["component_count"], 1)
        self.assertEqual(topology["longest_directed_path"]["plan_length_m"], 18.)
        self.assertEqual(topology["branch_node_ids"], ["branch"])
        profile = ports["upstream:turn"]["profile"]["profile_xyz_m"]
        seam = shared_port(records["upstream"]["geometry"], records["turn"]["geometry"], profile, hierarchy, {0})
        self.assertEqual({piece["profile_segment_index"] for piece in seam}, {0, 1, 2})
        self.assertFalse(manifest["replacement"]["original_06_in_fragment_mesh"])

    def test_negative_wet_false_function_and_node_only_attachment_remain_refused(self):
        hierarchy, paths, sections, selection, ports, records = saved_fixture()
        record = records["turn"]
        local = [port for port in ports.values() if "turn" in port["node_ids"]]
        for change in ("cut", "source", "control"):
            bad = deepcopy(record)
            if change == "cut":
                bad["geometry"]["vertex_depths_m"][0] = -1e-16
            elif change == "source":
                edge = bad["edge_proofs"][0]
                edge["source"]["source_coefficients_m_t012"][2] += .025
                edge.pop("identity_sha256")
                bad["edge_proofs"][0] = seal(edge)
            else:
                bad["geometry"]["outer_bank_control_vertex_ids"] = []
            bad.pop("identity_sha256")
            bad = seal(bad)
            check_identity(bad)
            with self.assertRaisesRegex(ValueError, "candidate lacks independent"):
                audit_node(bad, local, paths, sections, hierarchy, WET, {}, [])
        protected = dict(covered_native_cell_ids=list(range(441)), stage_by_leaf=[])
        with self.assertRaisesRegex(ValueError, "wet"):
            audit_vertices(record["geometry"], hierarchy, {0}, protected)
        composer = FragmentAudit()
        terminal = records["upstream"]
        result, descriptors = audit_node(terminal, [ports["upstream:turn"]], paths, sections, hierarchy, WET, {}, [])
        composer.consider(terminal, None, descriptors)
        manifest, topology = composer.finish(paths, sections, selection, [], {})
        self.assertEqual(topology["joined_arc_count"], 0)
        self.assertEqual(len(topology["open_ports"]), 1)
        self.assertFalse(topology["open_ports"][0]["hydraulic_boundary_claimed"])


if __name__ == "__main__":
    unittest.main()
