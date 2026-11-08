from copy import deepcopy
import unittest

from terrain_pipeline.td_ported_junction import build_ported_junction
from terrain_pipeline.td_ported_network_composition import NetworkComposer, census_hubs, match_ports, _new_ports
from test_td_ported_junction import fixture


def candidate():
    parents = fixture()
    record = build_ported_junction(*parents, hub_node_id="hub",
        wet_protection={"covered_native_cell_ids": [], "stage_by_leaf": []})
    return parents, record


class PortedNetworkCompositionTests(unittest.TestCase):
    def test_complete_ports_unique_arcs_kept_prefix_and_actual_global_metrics(self):
        parents, record = candidate()
        composer = NetworkComposer(parents[1], parents[2])
        row = composer.add_junction(record)
        self.assertEqual(row["composition_status"], "selected", row["rejection_reasons"])
        bundle = composer.finish()
        old = parents[2]["mesh"]
        mesh = bundle["composed_mesh"]
        self.assertEqual(mesh["vertices_xyz_m"][:len(old["vertices_xyz_m"])], old["vertices_xyz_m"])
        self.assertEqual(mesh["triangles"][:len(old["triangles"])], old["triangles"])
        self.assertEqual(len(bundle["manifest"]["arc_owners"]), 5)
        self.assertEqual(bundle["topology"]["component_count"], 1)
        self.assertEqual(bundle["topology"]["longest_directed_path"]["plan_length_m"], 15.)
        self.assertEqual(bundle["topology"]["open_port_count"], 3)
        self.assertFalse(bundle["topology"]["verified"])
        self.assertEqual(len(census_hubs(*parents[1:])), 1)
        first = deepcopy(_new_ports(record)[2])
        second = deepcopy(first)
        second["hub_node_id"] = "other"
        second["arc_id"] = "other-arc"
        segment = second["segments"][1]
        piece = segment["pieces"][0]
        start, end = piece["start_xz_m"], piece["end_xz_m"]
        midpoint = [(left + right) / 2. for left, right in zip(start, end)]
        constant, linear, quadratic = piece["bed_coefficients_m_t012"]
        source_constant, source_linear, source_quadratic = piece["source_coefficients_m_t012"]
        halves = []
        for offset in (0., .5):
            half = deepcopy(piece)
            half["start_xz_m"] = start if offset == 0. else midpoint
            half["end_xz_m"] = midpoint if offset == 0. else end
            half["bed_coefficients_m_t012"] = [constant + linear * offset + quadratic * offset**2,
                .5 * (linear + 2 * quadratic * offset), .25 * quadratic]
            half["source_coefficients_m_t012"] = [source_constant + source_linear * offset + source_quadratic * offset**2,
                .5 * (source_linear + 2 * source_quadratic * offset), .25 * source_quadratic]
            halves.append(half)
        segment["pieces"] = halves + segment["pieces"][1:]
        for current in second["segments"]:
            for current_piece in current["pieces"]:
                current_piece["side"]["points_xyz_m"].reverse()
        seam, reason = match_ports(first, second)
        self.assertIsNone(reason)
        self.assertTrue(all(piece["reverse_seam"] for piece in seam["native_pieces"]))
        self.assertGreater(len(seam["native_pieces"]), sum(len(segment["pieces"]) for segment in first["segments"]))

    def test_whole_hub_duplicate_overlap_and_whole_function_mismatch_refused(self):
        parents, record = candidate()
        composer = NetworkComposer(parents[1], parents[2])
        composer.add_junction(record)
        before = deepcopy(composer.mesh)
        duplicate = deepcopy(record)
        duplicate["hub_node_id"] = "second"
        row = composer.add_junction(duplicate)
        self.assertEqual(row["composition_status"], "refused")
        self.assertIn("duplicate_or_existing_incident_arc", row["rejection_reasons"])
        self.assertIn("positive_projected_overlap", row["rejection_reasons"])
        self.assertEqual(composer.mesh, before)
        self.assertEqual(row["added_arc_ids"], [])
        first = _new_ports(record)[2]
        second = deepcopy(first)
        for segment in second["segments"]:
            for piece in segment["pieces"]:
                piece["side"]["points_xyz_m"].reverse()
        second["segments"][1]["pieces"][0]["bed_coefficients_m_t012"][2] += .01
        seam, reason = match_ports(first, second)
        self.assertIsNone(seam)
        self.assertEqual(reason, "whole native bed coefficient mismatch")


if __name__ == "__main__":
    unittest.main()
