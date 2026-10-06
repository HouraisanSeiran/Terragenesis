import copy
from types import SimpleNamespace
import unittest

from tools.td_ported_network_saved_audit import SelectionAudit, match_ports, topology


def port(arc, reverse=False):
    profile = [[0., 10., float(number)] for number in range(4)]
    segments = []
    for number in range(3):
        pair = profile[number:number+2]
        segments.append(dict(profile_segment_index=number, points_xyz_m=pair, pieces=[dict(
            interval_t01=[0., 1.], start_xz_m=[0., float(number)], end_xz_m=[0., float(number+1)],
            bed_coefficients_m_t012=[10., 0., 0.], source_coefficients_m_t012=None, segment_id=None,
            side=dict(kind="legacy06", triangle_index=number, edge_index=0,
                      points_xyz_m=pair[::-1] if reverse else pair))]))
    return dict(kind="legacy06", hub_node_id=None, arc_id=arc, outer_node_id="shared",
                original_profile_xyz_m=profile, segments=segments)


def strip(left, right):
    vertices = [[position, 10., float(number)] for position in (left, right) for number in range(4)]
    faces = []
    for number in range(3):
        faces.extend([[number, number+4, number+5], [number, number+5, number+1]])
    return dict(vertices_xyz_m=vertices, triangles=faces)


class CompositionAuditTests(unittest.TestCase):
    def test_whole_three_segment_function_and_reverse_boundary_not_endpoints(self):
        first, second = port("first"), port("second", True)
        seam, reason = match_ports(first, second)
        self.assertIsNone(reason)
        self.assertEqual({piece["profile_segment_index"] for piece in seam["native_pieces"]}, {0, 1, 2})
        damaged = copy.deepcopy(second)
        damaged["segments"][1]["pieces"][0]["bed_coefficients_m_t012"] = [10., .025, -.025]
        self.assertEqual(match_ports(first, damaged)[1], "whole native bed coefficient mismatch")
        damaged = copy.deepcopy(second)
        damaged["segments"][2]["pieces"].clear()
        self.assertEqual(match_ports(first, damaged)[1], "native interval incomplete")
        self.assertEqual(match_ports(first, port("same_direction"))[1], "actual boundary edges not reverse")

    def test_selection_actual_strip_conflicts_and_no_node_only_connectivity(self):
        old = strip(0., 1.)
        old["triangle_arc_ids"] = ["first"]*6
        sections = dict(mesh=old, edge_sections=[])
        selection = SelectionAudit(sections)
        candidate = dict(geometry=strip(-1., 0.))
        seam, reason = match_ports(port("first"), port("second", True))
        self.assertIsNone(reason)
        self.assertEqual(selection.conflicts(candidate, [seam])[0], set())
        self.assertIn("partial_unbound_or_wrong_direction_edge_contact", selection.conflicts(candidate, [])[0])
        self.assertIn("positive_projected_overlap", selection.conflicts(dict(geometry=strip(.25, .75)), [])[0])
        doubled = copy.deepcopy(candidate)
        doubled["geometry"]["triangles"] *= 2
        self.assertIn("nonmanifold_or_same_direction_seam", selection.conflicts(doubled, [seam])[0])
        paths = dict(source_identity_sha256="source", nodes=[dict(node_id=name, xyz_m=[float(index), 10., 0.])
                     for index, name in enumerate(("start", "shared", "end"))], arcs=[
                     dict(arc_id="first", node_ids=["start", "shared"]),
                     dict(arc_id="second", node_ids=["shared", "end"])])
        graph = SimpleNamespace(owners={"first": {}, "second": {}}, connections=[], ports=[], closed=set())
        self.assertEqual(topology(paths, sections, graph)["component_count"], 2)
        graph.connections.append(seam)
        connected = topology(paths, sections, graph)
        self.assertEqual(connected["component_count"], 1)
        self.assertEqual(connected["longest_directed_path"]["arc_ids"], ["first", "second"])


if __name__ == "__main__":
    unittest.main()
