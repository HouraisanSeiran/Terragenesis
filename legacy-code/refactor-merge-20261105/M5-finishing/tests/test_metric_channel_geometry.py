import unittest
from copy import deepcopy
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import GeometryConfig, build_channel_geometry, load_channel_geometry, save_channel_geometry, validate_channel_geometry
from terrain_pipeline.channel_geometry import _cut_overlap, _modified_bed_slope, _wet_guard


def terrain():
    rows, cols = np.indices((9, 9))
    return TerrainGrid(20. - .1 * cols + .05 * rows,
                       np.ones((9, 9), bool), x0_m=0., z0_m=0.,
                       dx_m=4., dz_m=4., source_kind="observed_dem",
                       source_id="worked valley", source_sha256="a" * 64)


def build(*, owner=None, corridor=None, lake=None, config=None):
    source = terrain()
    shape = source.elevation_m.shape
    return build_channel_geometry(
        source, np.array([3 * 9 + 2, 3 * 9 + 5], np.int64),
        np.array([1, -1], np.int64), np.array([2., 2.]),
        np.array([.5, .5]), owner_grid=np.zeros(shape, np.int64) if owner is None else owner,
        corridor_mask=np.ones(shape, bool) if corridor is None else corridor,
        lake_mask=np.zeros(shape, bool) if lake is None else lake,
        anchor_mask=np.zeros(2, bool), config=config or GeometryConfig(fine_spacing_m=.5),
    )


class ChannelGeometryTests(unittest.TestCase):
    def test_nonlocal_continuous_bank_overlap_rejects_unsampled_lens(self):
        points = np.array([[0., 0.], [10., 0.], [0.2, 1.9], [10.2, 1.9]])
        receiver = np.array([1, -1, 3, -1], np.int64)
        width = np.ones(4)
        depth = np.full(4, .25)
        with self.assertRaisesRegex(ValueError, "overlap"):
            _cut_overlap(points, receiver, width, depth)

    def test_canonical_triangle_slope_rejects_local_hump(self):
        arrays = build()["arrays"]
        bed = arrays["bed_elevation_m"].copy()
        vertex = np.flatnonzero(np.all(np.isclose(arrays["vertices_xz_m"], [12., 12.]), axis=1))[0]
        bed[vertex] += 2.
        with self.assertRaisesRegex(ValueError, "uphill"):
            _modified_bed_slope(arrays["node_xz_m"], arrays["receiver"],
                                arrays["vertices_xz_m"], arrays["triangles"], bed, .5)

    def test_mixed_wet_native_cells_have_zero_pl_cut(self):
        from tools.verify_td_river_geometry import fixture

        source, ids, receiver, options = fixture("lake", 1.)
        bundle = build_channel_geometry(source, ids, receiver, **options)
        arrays = bundle["arrays"]
        guarded = _wet_guard(arrays["vertices_xz_m"], options["lake_mask"], source)
        self.assertTrue(np.any(guarded))
        np.testing.assert_array_equal(arrays["cut_depth_m"][guarded], 0.)
        self.assertEqual(bundle["metadata"]["lake_cut_policy"],
                         "zero_on_native_cells_touching_known_wet_nodes")

    def test_single_reach_has_one_fan_mesh_and_exact_represented_cut_budget(self):
        bundle = build()
        arrays, meta = bundle["arrays"], bundle["metadata"]
        self.assertTrue(validate_channel_geometry(bundle))
        self.assertTrue(meta["geometry_verified"])
        self.assertFalse(meta["hydraulic_ready"])
        self.assertGreater(meta["cut_volume_m3"], 0.)
        self.assertEqual(meta["deposition_bulk_m3"], 0.)
        self.assertAlmostEqual(meta["original_mesh_volume_m3"]
                               - meta["final_mesh_volume_m3"], meta["cut_volume_m3"], places=8)
        np.testing.assert_allclose(arrays["bed_elevation_m"],
                                   arrays["source_elevation_m"] - arrays["cut_depth_m"])
        self.assertEqual(len(arrays["triangles"]) % 4, 0)
        self.assertEqual(len(arrays["canonical_port_edge_node_indices"]), 1)

    def test_turn_y_and_lake_use_one_mesh_with_zero_cut_on_wet_support(self):
        from tools.verify_td_river_geometry import fixture, mesh_evidence

        for name in ("turn", "y", "lake"):
            with self.subTest(name=name):
                source, ids, receiver, options = fixture(name, 1.)
                bundle = build_channel_geometry(source, ids, receiver, **options)
                evidence = mesh_evidence(bundle)
                self.assertTrue(evidence["internal_edges_reversed"])
                self.assertTrue(evidence["shared_port_observations_verified"])
                if name == "lake":
                    arrays = bundle["arrays"]
                    grid = arrays["vertices_xz_m"] / 10.
                    on_source_node = np.all(np.isclose(grid, np.round(grid)), axis=1)
                    source_ids = (np.round(grid[:, 1]).astype(int) * 13
                                  + np.round(grid[:, 0]).astype(int))
                    wet_vertex = on_source_node & arrays["lake_mask"].ravel()[source_ids]
                    self.assertTrue(np.any(wet_vertex))
                    self.assertTrue(np.all(arrays["cut_depth_m"][wet_vertex] <= 1e-10))
                    inside_wet_rectangle = ((grid[:, 0] >= 5.) & (grid[:, 0] <= 8.)
                                            & (grid[:, 1] >= 3.) & (grid[:, 1] <= 6.))
                    self.assertTrue(np.any(inside_wet_rectangle))
                    self.assertTrue(np.all(arrays["cut_depth_m"][inside_wet_rectangle] <= 1e-10))

    def test_source_unknown_owner_divide_and_flat_route_reject(self):
        source = terrain()
        ids = np.array([3 * 9 + 2, 3 * 9 + 5], np.int64)
        receiver = np.array([1, -1], np.int64)
        width = np.array([2., 2.])
        depth = np.array([.5, .5])
        good = dict(owner_grid=np.zeros((9, 9), np.int64),
                    corridor_mask=np.ones((9, 9), bool),
                    lake_mask=np.zeros((9, 9), bool),
                    anchor_mask=np.zeros(2, bool),
                    config=GeometryConfig(fine_spacing_m=.5))
        unknown = source.valid_mask.copy()
        unknown[3, 4] = False
        bad_source = TerrainGrid(source.elevation_m.copy(), unknown, 0., 0., 4., 4.,
                                 "observed_dem", "worked valley", "a" * 64)
        with self.assertRaisesRegex(ValueError, "unknown|footprint"):
            build_channel_geometry(bad_source, ids, receiver, width, depth, **good)
        owner = good["owner_grid"].copy()
        owner[3, 4] = 1
        with self.assertRaisesRegex(ValueError, "divide|owner"):
            build_channel_geometry(source, ids, receiver, width, depth,
                                   **(good | {"owner_grid": owner}))
        flat = TerrainGrid(np.full((9, 9), 20.), np.ones((9, 9), bool),
                           0., 0., 4., 4., "observed_dem", "flat", "a" * 64)
        with self.assertRaisesRegex(ValueError, "flat|uphill"):
            build_channel_geometry(flat, ids, receiver, width, depth, **good)

    def test_cold_validator_rejects_rehashed_cut_and_port_forgery(self):
        bundle = build()
        for field in ("cut_depth_m", "canonical_port_cut_depth_m"):
            with self.subTest(field=field):
                forged = deepcopy(bundle)
                forged["arrays"][field] = forged["arrays"][field].copy()
                forged["arrays"][field].flat[0] += .01
                forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
                with self.assertRaisesRegex(ValueError, "cut|port"):
                    validate_channel_geometry(forged)

    def test_cold_roundtrip_keeps_source_and_represented_volume(self):
        bundle = build()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "channel-geometry.npz"
            save_channel_geometry(path, bundle)
            loaded = load_channel_geometry(path, expected_sha256=file_sha256(path),
                                           expected_identity=bundle["identity_sha256"])
        np.testing.assert_array_equal(loaded["arrays"]["source_height_m"],
                                      terrain().elevation_m)
        self.assertEqual(loaded["metadata"]["cut_volume_m3"],
                         bundle["metadata"]["cut_volume_m3"])


if __name__ == "__main__":
    unittest.main()
