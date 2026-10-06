import copy
import unittest

import numpy as np

from tools.audit_td_native_water_surface import check_arrays


class IndependentWaterTests(unittest.TestCase):
    def fixture(self):
        bed = np.array([[1., 2.], [3., 4.]])
        depth = np.array([[.1, .2], [.3, .4]])
        source = dict(height_m=bed, valid_mask=np.ones((2, 2), bool),
                      depth_m=np.stack((np.zeros(4), depth.ravel())))
        grid = dict(origin_m_xz=[100., 200.], spacing_m=30., start_s=0., end_s=3600.,
                    hierarchy_identity="h", forcing_identity="f")
        record = dict(expected_sha256="a" * 64, expected_identity="b" * 64)
        metadata = dict(**grid, source_page_sha256=record["expected_sha256"],
                        source_page_identity=record["expected_identity"], grid_shape=[2, 2],
                        wet_threshold_m=.05, valid_cell_count=4, wet_cell_count=4,
                        drawn_quad_count=1, undrawn_wet_cell_count=0,
                        grid_water_volume_m3=900., undrawn_wet_grid_volume_m3=0.,
                        derived_fine_hydraulics=False, water_generated=False, hydraulic_ready=False,
                        natural_outlet_verified=False, publishable=False)
        mesh = dict(cell_ids=np.arange(4), native_bed_m=bed.ravel(), hour_end_depth_m=depth.ravel(),
                    vertex_cell_ids=np.arange(4), vertices_xyz_m=np.array([[100., 1.1, 200.],
                        [130., 2.2, 200.], [100., 3.3, 230.], [130., 4.4, 230.]]),
                    triangles=np.array([[0, 2, 3], [0, 3, 1]], np.int64))
        return source, grid, mesh, metadata, record

    def test_independent_grid_volume_topology_and_vertices(self):
        result = check_arrays(*self.fixture())
        self.assertEqual(result["triangles"], 2)
        self.assertAlmostEqual(result["independently_summed_grid_volume_m3"], 900.)
        self.assertTrue(result["grid_volume_not_mesh_volume"])

    def test_false_volume_wrong_bed_and_certification_rejected(self):
        for field, value in (("grid_water_volume_m3", 899.), ("hydraulic_ready", True),
                             ("source_page_identity", "c" * 64)):
            source, grid, mesh, metadata, record = self.fixture()
            metadata[field] = value
            with self.assertRaises(ValueError):
                check_arrays(source, grid, mesh, metadata, record)
        source, grid, mesh, metadata, record = self.fixture()
        mesh["vertices_xyz_m"][0, 1] += .1
        with self.assertRaises(AssertionError):
            check_arrays(source, grid, mesh, metadata, record)

    def test_dry_invalid_and_threshold_holes_rejected(self):
        for invalid in (True, False):
            source, grid, mesh, metadata, record = self.fixture()
            if invalid:
                source["valid_mask"][0, 0] = False
            source["depth_m"][-1, 0] = 0.
            with self.assertRaises(AssertionError):
                check_arrays(source, grid, mesh, metadata, record)


if __name__ == "__main__":
    unittest.main()
