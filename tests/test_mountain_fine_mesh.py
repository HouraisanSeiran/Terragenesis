"""Read-only mesh source topology and exact wet-support volume representation."""

import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import mountain_depression_geometry as geometry
from terrain_pipeline import mountain_fine_geometry as fine
from terrain_pipeline import mountain_fine_storage as storage
from terrain_pipeline.mountain_fine_mesh import export_fine_mesh
from tools.verify_mountain_rainfall import load_source


class MountainFineMeshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_source("normal_mountain")
        cls.geometry = geometry.prepare_mountain_geometry(source["height_m"], spacing_m=30.,
            origin_m_xz=source["origin_m_xz"], source_binding={"mountain": "normal_mountain"},
            boundary_mask=geometry.window_boundary(source["height_m"].shape),
            protected_mask=np.zeros(source["height_m"].shape, dtype=bool))
        cls.chain = fine.select_continuous_fine_geometry(cls.geometry)["accepted"]
        support = storage.fine_storage_support(cls.chain)
        level = float(support["max_stage_m"].min() - .02)
        cls.saved = storage.prepare_fine_storage(cls.chain, cls.geometry,
            initial_stage_m=np.maximum(support["min_bed_m"], level), local_q_m3_s=np.zeros((8, 4)),
            upstream_stage_m=np.full(9, level), tailwater_stage_m=np.full(9, level), dt_s=10.)

    def test_shared_vertices_nonzero_triangles_and_exact_original_positions(self):
        mesh = export_fine_mesh(self.chain, self.saved, self.geometry)
        arrays = mesh["arrays"]
        self.assertEqual(arrays["triangles"].shape, (90 * 10 * 2, 3))
        self.assertEqual(arrays["vertices_H2_local_xyz_m"].shape, (91 * 11, 3))
        world = arrays["vertices_H0_local_xyz_m"] + arrays["origin_world_xyz_m"]
        np.testing.assert_allclose(world[:, 1], self.chain["arrays"]["H0_m"].ravel(), rtol=0., atol=1e-10)
        self.assertEqual(arrays["shared_section_vertex_ids"].shape, (2, 11))
        self.assertEqual(np.unique(arrays["shared_section_vertex_ids"]).size, 22)
        vertices = arrays["vertices_H2_local_xyz_m"]
        triangles = arrays["triangles"]
        normals = np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
        self.assertTrue((normals[:, 1] > 0).all())

    def test_wet_support_depth_and_volume_match_solver_not_triangle_interpolation(self):
        mesh = export_fine_mesh(self.chain, self.saved, self.geometry)
        arrays = mesh["arrays"]
        np.testing.assert_array_equal(arrays["wet_mask"], arrays["water_depth_m"] > 0)
        self.assertTrue((arrays["water_depth_m"] == 0).any())
        self.assertTrue((arrays["water_depth_m"] > 0).any())
        np.testing.assert_allclose(arrays["water_volume_m3"], arrays["solver_volume_m3"], atol=1e-9, rtol=0.)
        self.assertEqual(arrays["time_s"].size, arrays["qedges_m3_s"].shape[0] + 1)

    def test_export_is_readonly_and_never_prepares_or_advances(self):
        before = self.chain["arrays"]["H0_m"].copy()
        with patch.object(storage, "prepare_fine_storage", side_effect=AssertionError("advance")), \
             patch.object(storage, "fine_storage_support", side_effect=AssertionError("assemble")), \
             patch.object(fine, "prepare_fine_segment", side_effect=AssertionError("prepare")):
            export_fine_mesh(self.chain, self.saved, self.geometry)
        np.testing.assert_array_equal(before, self.chain["arrays"]["H0_m"])


if __name__ == "__main__":
    unittest.main()
