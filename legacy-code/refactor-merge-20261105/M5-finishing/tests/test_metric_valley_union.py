import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.channel_geometry import GeometryConfig
from terrain_pipeline.channel_geometry import build_valley_union, load_valley_union, save_valley_union, validate_valley_union
from tests.test_metric_valley_incision import uphill_source, build as build_dense


def union():
    source = uphill_source()
    return build_valley_union(
        source, np.array([30, 40], np.int64), np.array([1, -1], np.int64),
        np.array([2., 2.]), np.array([.25, .25]),
        owner_grid=np.zeros(source.elevation_m.shape, np.int64),
        corridor_mask=np.ones(source.elevation_m.shape, bool),
        lake_mask=np.zeros(source.elevation_m.shape, bool),
        source_plan_identity_sha256="b" * 64,
        config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))


class SparseValleyUnionTests(unittest.TestCase):
    def test_unique_sparse_fan4_matches_dense_represented_volume(self):
        sparse = union()
        dense = build_dense()
        self.assertTrue(validate_valley_union(sparse))
        self.assertLess(len(sparse["arrays"]["vertices_xz_m"]),
                        len(dense["arrays"]["vertices_xz_m"]))
        self.assertAlmostEqual(sparse["metadata"]["cut_volume_m3"],
                               dense["metadata"]["cut_volume_m3"], places=7)
        self.assertEqual(len(sparse["arrays"]["port_cut_depth_m"]), 1)
        faces = sparse["arrays"]["triangles"]
        edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]],
                                         faces[:, [2, 0]]]), axis=1)
        _, count = np.unique(edges, axis=0, return_counts=True)
        self.assertTrue(np.all(count <= 2))

    def test_cold_roundtrip_and_rehashed_port_tamper(self):
        bundle = union()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sparse-union.npz"
            save_valley_union(path, bundle)
            loaded = load_valley_union(path, expected_sha256=file_sha256(path),
                                       expected_identity=bundle["identity_sha256"])
        self.assertEqual(loaded["identity_sha256"], bundle["identity_sha256"])
        forged = deepcopy(bundle)
        forged["arrays"]["port_cut_depth_m"] = forged["arrays"]["port_cut_depth_m"].copy()
        forged["arrays"]["port_cut_depth_m"][0, 0] += .01
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "port"):
            validate_valley_union(forged)


if __name__ == "__main__":
    unittest.main()
