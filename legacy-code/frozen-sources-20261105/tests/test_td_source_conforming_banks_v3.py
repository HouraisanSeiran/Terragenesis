import unittest

import numpy as np

from terrain_pipeline import td_source_conforming_banks as v2
from terrain_pipeline import td_source_conforming_banks_v3 as v3
from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.td_fine_bed_raster import _context


def context_for(height):
    arrays = {"height_m": np.asarray(height, float),
              "valid_mask": np.ones(np.shape(height), bool),
              "protected_mask": np.zeros(np.shape(height), bool),
              "open_boundary_mask": np.zeros(np.shape(height), bool),
              "cell_owner": np.zeros(np.shape(height), np.int64),
              "contribution_owner": np.zeros(np.shape(height), np.int64),
              "node_unknown_contact": np.zeros(1, bool)}
    metadata = {"origin_m_xz": [0., 0.], "spacing_m": 1.,
                "source_identity_sha256": "a" * 64}
    hierarchy = {"arrays": arrays, "metadata": metadata,
                 "identity_sha256": identity(arrays, metadata)}
    return _context(hierarchy, [0])


def segments_for(triangles, context, legacy_edge):
    groups = {}
    for triangle in triangles:
        for edge_index in range(3):
            edge = v2._edge_record(triangle, edge_index)
            key = v2._line_key(np.asarray(edge["points_xyz_m"])[:, [0, 2]])
            groups.setdefault(key, []).append(edge)
    key = v2._line_key(np.asarray(legacy_edge["points_xyz_m"])[:, [0, 2]])
    groups[key].append(legacy_edge)
    for number, edges in enumerate(groups.values()):
        if len(edges) == 1:
            edges.append({**edges[0], "triangle_id": "legacy06:outer" + str(number)})
    return v2._segments(groups, context)


class SourceConformingBanksV3Tests(unittest.TestCase):
    def test_whole_native_linear_matching_and_adjacent_fan_vertex_unification(self):
        context = context_for(np.tile([10., 11., 10., 12., 12.], (5, 1)))
        parameters = {"max_cut_m": 5., "conflict_tolerance_m": 1e-8}
        triangles = [
            {"triangle_id": "06:0", "vertices_xyz_m": [
                [.25, 10., .25], [2.75, 10., .25], [.25, 9., 2.25]]},
            {"triangle_id": "06:1", "vertices_xyz_m": [
                [.25, 9., 2.25], [2.75, 10., .25], [2.75, 9., 2.25]]}]
        legacy = {"triangle_id": "legacy06:2", "edge_index": 0,
                  "points_xyz_m": triangles[0]["vertices_xyz_m"][:2]}
        segments = segments_for(triangles, context, legacy)
        old = [v2._proof(segment, context) for segment in segments]
        self.assertTrue(any("unchanged_neighbor_quadratic_function_mismatch"
                            in proof["rejection_reasons"] for proof in old))
        proofs = v3.build_edge_proofs(segments, context, parameters)
        boundary = [proof for proof in proofs if any(
            side["triangle_id"].startswith("legacy06:") for side in proof["sides"])]
        for proof in boundary:
            self.assertEqual(proof["status"], "candidate", proof["rejection_reasons"])
            source = proof["source"]["source_coefficients_m_t012"]
            depth = proof["depth_coefficients_m_t01"]
            for neighbor in proof["v3proof"]["unchanged_neighbor_polynomials"]:
                bed = neighbor["bed_coefficients_m_t012"]
                self.assertLessEqual(max(abs(value) for value in (
                    source[0] - depth[0] - bed[0], source[1] - depth[1] - bed[1], source[2])), 1e-9)
        functions = []
        for triangle in triangles:
            relevant = [proof for proof in proofs if any(
                side["triangle_id"] == triangle["triangle_id"] for side in proof["sides"])]
            function = v3.build_triangle_function(triangle, relevant, context, parameters)
            self.assertEqual(function["status"], "candidate", function["rejection_reasons"])
            functions.append(function)
            vertices = {}
            for fan in function["fans"]:
                for point, depth in zip(fan["vertices_xz_m"], fan["depth_at_vertices_m"]):
                    key = tuple(point)
                    if key in vertices:
                        self.assertAlmostEqual(vertices[key], depth, places=9)
                    vertices[key] = depth
            if triangle["triangle_id"] == "06:0":
                self.assertAlmostEqual(vertices[(1., .25)], 1.)
        for point in ([1., .25], [1.5, 1.25]):
            for function in functions:
                if point == [1., .25] and function["triangle_id"] != "06:0":
                    continue
                source = v2._source_sample(context, *point)["height_m"]
                value = v3.evaluate_bank_function(function, *point, source)
                self.assertGreaterEqual(value["cut_depth_m"], 0.)
        self.assertEqual(v2.SCHEMA, "td-source-conforming-banks-v2")

    def test_quadratic_or_negative_depth_legacy_boundary_is_refused(self):
        for quadratic in (True, False):
            if quadratic:
                rows, columns = np.indices((4, 4))
                context = context_for(10. - .5 * rows * columns)
                endpoints = [[.25, 7., .25], [1.75, 7., 1.75]]
                reason = "legacy_source_quadratic_requires_joint_version"
            else:
                context = context_for(np.tile([10., 8., 10., 10.], (4, 1)))
                endpoints = [[.25, 9., .25], [1.75, 9., .25]]
                reason = "legacy_matching_negative_depth"
            edges = [{"triangle_id": name, "edge_index": 0,
                      "points_xyz_m": endpoints} for name in ("06:0", "legacy06:1")]
            key = v2._line_key(np.asarray(endpoints)[:, [0, 2]])
            proofs = v3.build_edge_proofs(v2._segments({key: edges}, context), context,
                                         {"max_cut_m": 5., "conflict_tolerance_m": 1e-8})
            self.assertTrue(all(proof["status"] == "refused" for proof in proofs))
            self.assertTrue(all(reason in proof["rejection_reasons"] for proof in proofs))
            self.assertTrue(all(proof["depth_coefficients_m_t01"] is None for proof in proofs))


if __name__ == "__main__":
    unittest.main()
