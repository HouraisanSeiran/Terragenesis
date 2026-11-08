import unittest

import numpy as np

from terrain_pipeline.surface_domain import partition_saved_window, audit_saved_mosaic, account_shared_transfers, partition_fan_geometry, bind_saved_leaf_faces


class FineDomainMosaicTests(unittest.TestCase):
    def setUp(self):
        self.bed = np.zeros((4, 4), np.float64)
        self.depth = np.full((4, 4), .5, np.float64)
        self.owner = np.arange(16).reshape(4, 4)

    def mosaic(self):
        return partition_saved_window(self.bed, self.depth, self.owner, row_cuts=(2,), column_cuts=(2,), version="t0")

    def test_four_domains_cover_inventory_and_unique_seams(self):
        result = audit_saved_mosaic(self.mosaic(), self.bed, self.depth, spacing_m=1., version="t0")
        self.assertEqual(result["domain_volume_m3"], [2., 2., 2., 2.])
        self.assertEqual(result["total_volume_m3"], 8.)
        self.assertEqual(result["shared_face_segments"], 8)
        self.assertEqual(result["mosaic_volume_residual_m3"], 0.)

    def test_signed_exchange_keeps_reverse_volume_and_global_balance(self):
        mosaic = self.mosaic()
        transfers = np.zeros(8, np.float64)
        transfers[0] = 3.; transfers[2] = -2.
        actual = account_shared_transfers(mosaic, transfers)
        np.testing.assert_array_equal(actual, [-3., 3., 2., -2.])
        self.assertEqual(actual.sum(), 0.)

    def test_halo_copies_cannot_change_after_source_mutation(self):
        mosaic = self.mosaic()
        self.depth[:] = 1.
        self.assertEqual(mosaic["windows"][0].depth_m[0, 0], .5)
        with self.assertRaises(ValueError):
            mosaic["windows"][0].depth_m.setflags(write=True)
        with self.assertRaisesRegex(ValueError, "stale halo"):
            audit_saved_mosaic(mosaic, self.bed, self.depth, spacing_m=1., version="t0")

    def test_mixed_versions_and_cut_through_coarse_leaf_rejected(self):
        with self.assertRaisesRegex(ValueError, "version"):
            audit_saved_mosaic(self.mosaic(), self.bed, self.depth, spacing_m=1., version="t1")
        with self.assertRaisesRegex(ValueError, "splits"):
            partition_saved_window(self.bed, self.depth, np.zeros((4, 4), np.int64), column_cuts=(2,), version="t0")

    def test_invalid_cuts_and_nonfinite_source_rejected(self):
        with self.assertRaises(ValueError):
            partition_saved_window(self.bed, self.depth, self.owner, row_cuts=(2, 2), version="t0")
        self.depth[0, 0] = np.nan
        with self.assertRaises(ValueError):
            self.mosaic()

    def fan(self):
        corners = []
        vertices = [[column, 0., row] for row in range(5) for column in range(5)]
        triangles = []
        for row in range(4):
            for column in range(4):
                ids = [row*5+column, (row+1)*5+column, (row+1)*5+column+1, row*5+column+1]
                center = len(vertices)
                vertices.append([column+.5, 0., row+.5])
                corners.append(ids)
                triangles.extend([[ids[index], ids[(index+1)%4], center] for index in range(4)])
        bed = np.array(vertices)
        water = bed.copy()
        water[:, 1] = .5
        return dict(cell_corner_vertex_ids=np.array(corners),bed_vertices_xyz_m=bed,
            water_vertices_xyz_m=water,bed_triangles=np.array(triangles),
            wet_cell_ids=np.arange(16),water_triangles=np.array(triangles))

    def test_independent_meshes_keep_shared_xyz_and_wet_triangles(self):
        source = self.fan()
        meshes, report = partition_fan_geometry(self.mosaic(), source)
        self.assertEqual(report["shared_vertex_count"], 9)
        self.assertEqual(report["max_water_seam_error_m"], 0.)
        self.assertEqual(report["bed_triangle_count"], 64)
        self.assertEqual(report["water_triangle_count"], 64)
        self.assertEqual(sum(len(mesh["wet_cell_ids"]) for mesh in meshes), 16)
        source["water_vertices_xyz_m"][:] = 99.
        self.assertEqual(meshes[0]["water_vertices_xyz_m"][0, 1], .5)

    def test_missing_wet_triangles_and_nonfinite_geometry_rejected(self):
        source = self.fan()
        source["water_triangles"] = source["water_triangles"][:-1]
        with self.assertRaises(ValueError):
            partition_fan_geometry(self.mosaic(), source)
        source = self.fan()
        source["bed_vertices_xyz_m"][0, 1] = np.nan
        with self.assertRaises(ValueError):
            partition_fan_geometry(self.mosaic(), source)

    def test_saved_face_coordinate_conversion_and_original_order(self):
        mosaic = self.mosaic()
        order = np.arange(8)[::-1]
        axes = mosaic["face_axis"][order]
        geometry = dict(face_axis=axes,
            face_canonical_row=mosaic["face_row"][order]+(axes == 1),
            face_canonical_column=mosaic["face_column"][order]+(axes == 0))
        np.testing.assert_array_equal(bind_saved_leaf_faces(mosaic, geometry), order)
        geometry = {name: values[:-1] for name,values in geometry.items()}
        with self.assertRaises(ValueError):
            bind_saved_leaf_faces(mosaic, geometry)
