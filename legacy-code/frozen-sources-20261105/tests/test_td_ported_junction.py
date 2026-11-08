from copy import deepcopy
import unittest

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.td_ported_junction import build_ported_junction


def fixture():
    shape = (21, 21)
    arrays = {"height_m": np.full(shape, 10.), "valid_mask": np.ones(shape, bool),
        "protected_mask": np.zeros(shape, bool), "open_boundary_mask": np.zeros(shape, bool),
        "cell_owner": np.zeros(shape, np.int64), "contribution_owner": np.zeros(shape, np.int64),
        "node_unknown_contact": np.zeros(1, bool)}
    metadata = {"origin_m_xz": [-10., -10.], "spacing_m": 1., "source_identity_sha256": "a" * 64}
    hierarchy = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    nodes = [{"node_id": name, "xyz_m": [point[0], 10., point[1]], "kinds": ["land_channel"]}
             for name, point in (("hub", [0., 0.]), ("north", [0., -6.]), ("west", [-6., 0.]), ("south", [0., 6.]))]
    arcs = [{"arc_id": name, "kind": "land_channel", "node_ids": pair}
            for name, pair in (("north-hub", ["north", "hub"]), ("west-hub", ["west", "hub"]), ("hub-south", ["hub", "south"]))]
    paths = {"identity_sha256": "b" * 64, "hierarchy_identity_sha256": hierarchy["identity_sha256"],
        "source_identity_sha256": "a" * 64, "ordinary_identity_sha256": "c" * 64, "nodes": nodes, "arcs": arcs}
    node_map = {node["node_id"]: node for node in nodes}
    node_sections = [{"node_id": "hub", "source_xyz_m": [0., 10., 0.], "depth_m": .3,
                      "anchor": False, "rejection_reasons": ["needs_junction_patch"]}]
    mesh = {"vertices_xyz_m": [], "triangles": [], "triangle_arc_ids": []}
    edge_sections = []
    for number, arc in enumerate(arcs):
        outer_id = next(identifier for identifier in arc["node_ids"] if identifier != "hub")
        center = np.asarray(node_map[outer_id]["xyz_m"])[[0, 2]]
        flow = np.asarray(node_map[arc["node_ids"][1]]["xyz_m"])[[0, 2]] - np.asarray(node_map[arc["node_ids"][0]]["xyz_m"])[[0, 2]]
        flow /= np.linalg.norm(flow)
        normal = np.array([-flow[1], flow[0]])
        offsets = np.array([-.8 - .2 * number, -.3 - .2 * number, .3 + .2 * number, .8 + .2 * number])
        profile = [[*(center + normal * offset)[:1], 10. - depth, (center + normal * offset)[1]]
                   for offset, depth in zip(offsets, [0., .2, .2, 0.])]
        node_sections.append({"node_id": outer_id, "source_xyz_m": node_map[outer_id]["xyz_m"],
            "cross_section_xyz_m": profile, "depth_m": .2, "anchor": False, "rejection_reasons": []})
        if outer_id == "south":
            continue
        radial = center / np.linalg.norm(center)
        far = [[point[0] + radial[0] * 3., point[1], point[2] + radial[1] * 3.] for point in profile]
        start = len(mesh["vertices_xyz_m"])
        mesh["vertices_xyz_m"].extend(far + profile)
        triangle_ids = []
        for profile_segment in range(3):
            for triangle in ([profile_segment, profile_segment + 4, profile_segment + 1],
                             [profile_segment + 1, profile_segment + 4, profile_segment + 5]):
                points = np.asarray([mesh["vertices_xyz_m"][start + index] for index in triangle])[:, [0, 2]]
                if np.linalg.det(np.stack([points[1] - points[0], points[2] - points[0]])) < 0.:
                    triangle = triangle[::-1]
                triangle_ids.append(len(mesh["triangles"]))
                mesh["triangles"].append([start + index for index in triangle])
                mesh["triangle_arc_ids"].append("neighbor:" + outer_id)
        edge_sections.append({"arc_id": "neighbor:" + outer_id, "node_ids": ["far:" + outer_id, outer_id],
                              "cross_section_xyz_m": [far, profile], "triangle_indices": triangle_ids})
    sections = {"identity_sha256": "d" * 64, "hierarchy_identity_sha256": hierarchy["identity_sha256"],
        "source_identity_sha256": "a" * 64, "ordinary_identity_sha256": "c" * 64,
        "selected_leaf_ids": [0], "node_sections": node_sections, "mesh": mesh, "edge_sections": edge_sections,
        "reach_diagnostics": [{"arc_id": arc["arc_id"], "status": "rejected", "rejection_reasons": ["needs_junction_patch"]} for arc in arcs]}
    return hierarchy, paths, sections


class PortedJunctionTests(unittest.TestCase):
    def test_real_three_arm_ports_complete_reverse_seams_with_two_external_attachments(self):
        parents = fixture()
        original = deepcopy(parents[2])
        record = build_ported_junction(*parents, hub_node_id="hub",
            wet_protection={"covered_native_cell_ids": [], "stage_by_leaf": []})
        self.assertEqual(record["status"], "candidate", record["rejection_reasons"])
        self.assertTrue(record["internal_three_arm_geometry_candidate"])
        self.assertEqual(record["actual_external_attachment_count"], 2)
        self.assertFalse(record["external_closure_verified"])
        self.assertFalse(record["fine_generated"])
        self.assertEqual(parents[2], original)
        self.assertEqual(len(record["geometry"]["ring_vertex_indices"]), 12)
        self.assertEqual(len(record["port_proofs"]), 6)
        for proof in record["port_proofs"]:
            self.assertEqual(proof["status"], "candidate", proof["rejection_reasons"])
            self.assertEqual(len(proof["profile_segments"]), 3)
            for segment in proof["profile_segments"]:
                self.assertTrue(segment["native_pieces"])
                if proof["kind"] == "inner_port_proof" or proof["attachment_status"] == "actual_old_mesh":
                    self.assertTrue(all(piece["reverse_seam"] for piece in segment["native_pieces"]))
        widths = [arm["preserved_outer_channel_width_m"] for arm in record["arms"]]
        self.assertEqual(len(set(round(width, 6) for width in widths)), 3)
        stub_arm = next(arm for arm in record["arms"] if arm["attachment_status"] != "actual_old_mesh")
        stub_proofs = [proof for proof in record["edge_proofs"] if proof["bound_original_section"] is not None]
        self.assertGreater(len(stub_proofs), 3)
        for proof in stub_proofs:
            binding = proof["bound_original_section"]
            profile_segment = binding["profile_segment_index"]
            original_pair = stub_arm["outer_profile_xyz_m"][profile_segment:profile_segment + 2]
            self.assertEqual(binding["original_points_xyz_m"], original_pair)
            self.assertEqual(len(proof["sides"]), 1)
            self.assertTrue(proof["sides"][0]["triangle_id"].startswith("junction:"))
            self.assertIn(proof["sides"][0]["points_xyz_m"], [original_pair, original_pair[::-1]])
            self.assertLessEqual(max(abs(value) for value in binding["difference_coefficients_m_t012"]), 1e-9)
        self.assertEqual(record["transaction"]["replaced_original_triangle_indices"], [])

    def test_invalid_outer_profile_and_no_fill_are_atomic_refusals(self):
        for invalid_profile in (True, False):
            hierarchy, paths, sections = fixture()
            outer = sections["node_sections"][1]
            if invalid_profile:
                outer["cross_section_xyz_m"] = []
            else:
                outer["cross_section_xyz_m"][1][1] = 11.
            record = build_ported_junction(hierarchy, paths, sections, hub_node_id="hub",
                wet_protection={"covered_native_cell_ids": [], "stage_by_leaf": []})
            self.assertEqual(record["status"], "refused")
            self.assertFalse(record["internal_three_arm_geometry_candidate"])
            self.assertEqual(record["transaction"]["candidate_replacement_arc_ids"], [])
            self.assertTrue(any("four_point_profile" in reason if invalid_profile else
                                "fill_unknown_or_cut_exceeded" in reason for reason in record["rejection_reasons"]))


if __name__ == "__main__":
    unittest.main()
