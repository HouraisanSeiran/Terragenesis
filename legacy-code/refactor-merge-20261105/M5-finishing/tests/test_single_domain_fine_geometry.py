import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.fine_subgrid import build_fine_geometry, build_fine_water_frame, coarsen_cell_field, load_fine_geometry, load_fine_water_frame, save_fine_geometry, save_fine_water_frame, validate_fine_geometry, validate_fine_water_frame
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source


def fixture(protected=None):
    height = np.array([[4., 3., 4.], [3., 0., 3.], [4., 2., 4.]])
    hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=30., origin_m_xz=(120., -60.),
                                                    protected_mask=protected))
    geometry = build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256="a"*64)
    return hierarchy, geometry


def states(geometry, depth):
    arrays = dict(depth_m=np.array([depth], dtype=np.float64), time_s=np.array([60.], np.float64))
    metadata = dict(schema="single-domain-fine-states-v1", bed_identity=geometry["identity_sha256"])
    return dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))


def mutable(result):
    result = copy.deepcopy(result)
    result["arrays"] = {name: value.copy() for name, value in result["arrays"].items()}
    return result


class FineGeometryTests(unittest.TestCase):
    def test_complete_window_upward_shared_junction_fan(self):
        hierarchy, geometry = fixture()
        arrays = geometry["arrays"]
        self.assertEqual(arrays["H2_m"].shape, (60, 60))
        self.assertEqual(len(arrays["bed_triangles"]), 14400)
        corners = arrays["bed_vertices_xyz_m"][arrays["cell_corner_vertex_ids"], 1]
        self.assertTrue(np.isfinite(arrays["H2_m"]).all())
        entering = arrays["edge_node_indices"][:, 1] == 4
        self.assertEqual(int(entering.sum()), 4)
        endpoints = arrays["node_xyz_m"][arrays["edge_node_indices"]]
        np.testing.assert_array_equal(endpoints[entering, 1], np.tile([150., -1., -30.], (4, 1)))
        vertices, triangles = arrays["bed_vertices_xyz_m"], arrays["bed_triangles"]
        normals = np.cross(vertices[triangles[:, 1]]-vertices[triangles[:, 0]],
                           vertices[triangles[:, 2]]-vertices[triangles[:, 0]])
        self.assertTrue(np.all(normals[:, 1] > 0))
        self.assertTrue(arrays["internal_sink_mask"][4])
        np.testing.assert_array_equal(arrays["native_height_m"], hierarchy["arrays"]["height_m"])
        self.assertFalse(arrays["bed_vertices_xyz_m"].flags.writeable)

    def test_protection_preserves_original_and_cut_is_max_not_sum(self):
        protected = np.zeros((3, 3), bool)
        protected[1, 1] = True
        _, geometry = fixture(protected)
        arrays = geometry["arrays"]
        self.assertFalse(arrays["cut_corner_m"][arrays["protected_corner_mask"]].any())
        np.testing.assert_array_equal(arrays["bed_corner_m"][arrays["protected_corner_mask"]],
                                      arrays["native_bilinear_corner_m"][arrays["protected_corner_mask"]])
        _, unprotected = fixture()
        self.assertEqual(unprotected["metadata"]["maximum_cut_m"], 1.)
        self.assertEqual(unprotected["arrays"]["cut_corner_m"][30, 30], 1.)

    def test_isolated_wet_cell_continuous_nonnegative_exact_local_volume(self):
        _, geometry = fixture()
        depth = np.zeros((60, 60), np.float64)
        depth[30, 30] = .25
        frame = build_fine_water_frame(geometry, states(geometry, depth), state_index=0)
        arrays = frame["arrays"]
        self.assertEqual(len(arrays["water_triangles"]), 4)
        self.assertEqual(arrays["center_depth_m"][30, 30], .75)
        self.assertEqual(arrays["cell_volume_m3"][30, 30], .25)
        self.assertEqual(frame["metadata"]["raster_volume_m3"], .25)
        expected_offset = (geometry["arrays"]["bed_fan_center_m"]+arrays["center_depth_m"])-(geometry["arrays"]["H2_m"]+depth)
        self.assertEqual(frame["metadata"]["max_center_stage_offset_m"], float(abs(expected_offset).max()))
        self.assertEqual(frame["metadata"]["omitted_wet_cell_count"], 0)
        self.assertFalse(arrays["corner_depth_m"].any())
        np.testing.assert_array_equal(arrays["water_vertices_xyz_m"][:, [0, 2]],
                                      geometry["arrays"]["bed_vertices_xyz_m"][:, [0, 2]])

    def test_random_wet_dry_depths_conserve_every_cell_and_share_edges(self):
        _, geometry = fixture()
        depth = np.random.default_rng(31).random((60, 60))
        depth[depth < .4] = 0.
        frame = build_fine_water_frame(geometry, states(geometry, depth), state_index=0)
        arrays = frame["arrays"]
        np.testing.assert_allclose(arrays["cell_volume_m3"], depth, rtol=0., atol=1e-15)
        self.assertTrue(np.all(arrays["center_depth_m"] >= 0.))
        corner_ids = geometry["arrays"]["cell_corner_vertex_ids"].reshape(60, 60, 4)
        np.testing.assert_array_equal(corner_ids[:, :-1, [3, 2]], corner_ids[:, 1:, [0, 1]])
        corner_depths = arrays["corner_depth_m"].ravel()[corner_ids.reshape(-1, 4)]
        self.assertFalse(corner_depths[depth.ravel() == 0].any())
        self.assertEqual(len(arrays["water_triangles"]), int(np.count_nonzero(depth))*4)

    def test_resolution_samples_same_original_and_all_window_cells(self):
        hierarchy, fine = fixture()
        for spacing in (2., 4.):
            geometry = build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2],
                                           source_hierarchy_sha256="a"*64, spacing_m=spacing)
            arrays = geometry["arrays"]
            np.testing.assert_array_equal(arrays["native_bilinear_corner_m"],
                                          fine["arrays"]["native_bilinear_corner_m"][::int(spacing), ::int(spacing)])
            self.assertEqual(arrays["H2_m"].shape, (int(60/spacing),)*2)
            frame = build_fine_water_frame(geometry, states(geometry, np.ones_like(arrays["H2_m"])), state_index=0)
            self.assertEqual(frame["metadata"]["triangulated_volume_m3"], 3600.)
            expected_offset = abs(arrays["bed_fan_center_m"]-arrays["H2_m"])
            self.assertAlmostEqual(frame["metadata"]["max_center_stage_offset_m"], float(expected_offset.max()))

    def test_coarse_bed_is_canonical_one_metre_area_transfer(self):
        hierarchy, one = fixture()
        two = build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256="a"*64, spacing_m=2.)
        four = build_fine_geometry(hierarchy, native_window=[0, 2, 0, 2], source_hierarchy_sha256="a"*64, spacing_m=4.)
        expected_two = one["arrays"]["H2_m"].reshape(30, 2, 30, 2).mean(axis=(1, 3))
        expected_four = one["arrays"]["H2_m"].reshape(15, 4, 15, 4).mean(axis=(1, 3))
        np.testing.assert_allclose(two["arrays"]["H2_m"], expected_two, rtol=0., atol=1e-12)
        np.testing.assert_allclose(four["arrays"]["H2_m"], expected_four, rtol=0., atol=1e-12)
        for geometry in (one, two, four):
            corners = geometry["arrays"]["bed_corner_m"]
            centre = geometry["arrays"]["bed_fan_center_m"]
            integrated = (corners[:-1, :-1]+corners[1:, :-1]+corners[1:, 1:]+corners[:-1, 1:]+2*centre)/6
            np.testing.assert_allclose(integrated, geometry["arrays"]["H2_m"], rtol=0., atol=1e-12)

    def test_initial_depth_transfer_uses_area_mean_not_recomputed_clipping(self):
        fine_depth = np.zeros((60, 60), np.float64)
        fine_depth[10:14, 10:14] = np.arange(16, dtype=np.float64).reshape(4, 4)
        coarse = coarsen_cell_field(fine_depth, factor=2)
        np.testing.assert_array_equal(coarse[5:7, 5:7],
                                      [[2.5, 4.5], [10.5, 12.5]])
        with self.assertRaises(ValueError):
            coarsen_cell_field(fine_depth, factor=3)

    def test_native_boundary_crossings_and_true_internal_sinks(self):
        height = np.tile(np.arange(5., 0., -1), (5, 1))
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=30., origin_m_xz=(0., 0.)))
        geometry = build_fine_geometry(hierarchy, native_window=[1, 3, 1, 3], source_hierarchy_sha256="a"*64)
        arrays = geometry["arrays"]
        self.assertEqual(len(arrays["incoming_boundary_edge_cell_ids"]), 3)
        self.assertEqual(len(arrays["outgoing_boundary_edge_cell_ids"]), 3)
        self.assertFalse(arrays["internal_sink_mask"].any())

    def test_rehashed_geometry_and_water_corruption_rejected(self):
        _, geometry = fixture()
        frame = build_fine_water_frame(geometry, states(geometry, np.ones((60, 60))), state_index=0)
        for original, validator, field in ((geometry, validate_fine_geometry, "bed_corner_m"),
                                           (geometry, validate_fine_geometry, "H2_m"),
                                           (geometry, validate_fine_geometry, "node_xyz_m"),
                                           (frame, validate_fine_water_frame, "center_depth_m"),
                                           (frame, validate_fine_water_frame, "water_vertices_xyz_m"),
                                           (frame, validate_fine_water_frame, "cell_volume_m3")):
            result = mutable(original)
            result["arrays"][field].flat[0] += 1.
            result["identity_sha256"] = identity(result["arrays"], result["metadata"])
            with self.subTest(field=field), self.assertRaises(ValueError):
                validator(result)

    def test_native_water_and_invalid_state_or_window_refused(self):
        hierarchy, geometry = fixture()
        saved = states(geometry, np.ones((60, 60)))
        for kind in ("native", "identity", "negative"):
            bad = mutable(saved)
            if kind == "native":
                bad["metadata"]["bed_identity"] = hierarchy["identity_sha256"]
            elif kind == "identity":
                bad["identity_sha256"] = "b"*64
            else:
                bad["arrays"]["depth_m"][0, 0, 0] = -1.
            if kind != "identity":
                bad["identity_sha256"] = identity(bad["arrays"], bad["metadata"])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                build_fine_water_frame(geometry, bad, state_index=0)
        for kwargs in (dict(native_window=[0, 3, 0, 2]), dict(native_window=[0, 2, 0, 2], spacing_m=.5),
                       dict(native_window=[0, 2, 0, 2], width_m=9.)):
            with self.assertRaises(ValueError):
                build_fine_geometry(hierarchy, source_hierarchy_sha256="a"*64, **kwargs)

    def test_roundtrip_readonly_without_constructor_calls(self):
        _, geometry = fixture()
        frame = build_fine_water_frame(geometry, states(geometry, np.ones((60, 60))), state_index=0)
        with tempfile.TemporaryDirectory() as directory:
            for name, result, saver, loader in (("bed", geometry, save_fine_geometry, load_fine_geometry),
                                                ("water", frame, save_fine_water_frame, load_fine_water_frame)):
                path = Path(directory)/(name+".npz")
                saver(path, result)
                with patch('terrain_pipeline.fine_subgrid.build_fine_geometry', side_effect=AssertionError), \
                        patch('terrain_pipeline.fine_subgrid.build_fine_water_frame', side_effect=AssertionError):
                    loaded = loader(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
                self.assertTrue(all(not value.flags.writeable for value in loaded["arrays"].values()))
                with self.assertRaises(ValueError):
                    loader(path, expected_sha256="0"*64, expected_identity=result["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
