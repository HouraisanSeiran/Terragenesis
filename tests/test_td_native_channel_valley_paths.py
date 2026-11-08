import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_native_channel_geometry import build_channel_geometry, load_channel_geometry
from terrain_pipeline.td_native_channel_valley_paths import (
    _candidate, _continuous_checks, _distance_to_path, _sample_native, _within_corridor, ValleyPathRecipe,
    build_valley_paths, load_valley_paths, save_valley_paths, validate_valley_paths,
)
from tests.test_td_native_channel_geometry import fixture


ROOT = Path(__file__).resolve().parents[1]
REAL_GEOMETRY = ROOT / "verification/td-native-channel-geometry/A-prototype-20261002T170035732414Z/geometry.npz"
REAL_HIERARCHY = ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
REAL_WINDOW = [19, 29, 104, 114]


class ValleyPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hierarchy, cls.hour = fixture()
        cls.geometry = build_channel_geometry(cls.hierarchy, cls.hour)

    def test_paths_cover_active_edges_and_cold_read(self):
        paths = build_valley_paths(self.geometry, self.hierarchy)
        arrays = paths["arrays"]
        np.testing.assert_array_equal(np.sort(arrays["chain_edge_indices"]),
                                      np.flatnonzero(self.geometry["arrays"]["edge_geometry_active"]))
        self.assertLessEqual(len(arrays["points_xyz_m"]), 262144)
        self.assertEqual(paths["metadata"]["omitted_active_edges"], 0)
        self.assertFalse(paths["metadata"]["hydraulic_ready"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "paths.npz"
            save_valley_paths(target, paths)
            with patch("terrain_pipeline.td_native_channel_valley_paths.build_valley_paths", side_effect=AssertionError("built")):
                loaded = load_valley_paths(target, expected_sha256=file_sha256(target), expected_identity=paths["identity_sha256"])
            self.assertEqual(paths["identity_sha256"], loaded["identity_sha256"])
            with self.assertRaises(ValueError):
                load_valley_paths(target, expected_sha256="0" * 64, expected_identity=paths["identity_sha256"])
            with self.assertRaises(FileExistsError):
                save_valley_paths(target, paths)

    def test_stencil_rejection_and_window_omission(self):
        metadata = self.geometry["metadata"]
        origin = metadata["origin_m_xz"]
        spacing = metadata["spacing_m"]
        point = np.array([[origin[0] + .5 * spacing, origin[1] + .5 * spacing]])
        modified = copy.deepcopy(self.hierarchy)
        modified["arrays"] = {name: value.copy() for name, value in modified["arrays"].items()}
        modified["arrays"]["protected_mask"][0, 0] = True
        self.assertIsNone(_sample_native(modified, self.geometry, point))
        modified["arrays"]["protected_mask"][0, 0] = False
        modified["arrays"]["contribution_owner"][0, 0] = -1
        self.assertIsNone(_sample_native(modified, self.geometry, point))
        modified["arrays"]["contribution_owner"][0, 0] = self.hierarchy["arrays"]["contribution_owner"][0, 0]
        modified["arrays"]["open_boundary_mask"][0, 0] = True
        self.assertIsNone(_sample_native(modified, self.geometry, point))
        paths = build_valley_paths(self.geometry, self.hierarchy, window=[0, 2, 0, 2])
        self.assertGreaterEqual(paths["metadata"]["omitted_active_edges"], 0)
        self.assertEqual(paths["metadata"]["total_active_edges"],
                         len(paths["arrays"]["included_active_edge_indices"]) + paths["metadata"]["omitted_active_edges"])

    def test_quadratic_corner_and_corridor(self):
        original = np.array([[0., 0.], [30., 0.], [30., 30.]])
        points, corners = _candidate(original, 30., ValleyPathRecipe())
        self.assertEqual(corners, 1)
        np.testing.assert_array_equal(points[0], original[0])
        np.testing.assert_array_equal(points[-1], original[-1])
        self.assertLessEqual(float(_distance_to_path(points, original).max()), 30. / 4.)
        self.assertTrue(_within_corridor(points, original, 30. / 4.))
        self.assertFalse(np.any(np.all(points == original[1], axis=1)))
        checks = _continuous_checks(np.array([[0., 0.], [60., 30.]]), [0., 0.], 30.)
        self.assertTrue(np.any(np.all(checks == [30., 15.], axis=1)))
        self.assertGreater(len(checks), 3)

    def test_continuous_corridor_endpoint_minimum_counterexample(self):
        original = np.array([[-1., 1.], [-1., -10.], [1., -10.], [1., 1.]])
        rendered = np.array([[-.8, 1.], [.6, 1.]])
        distances = _distance_to_path(rendered, original)
        length = np.linalg.norm(rendered[1] - rendered[0])
        self.assertLess(float(min(distances) + length / 2), .95)
        self.assertGreater(float(_distance_to_path(np.array([[0., 1.]]), original)[0]), .95)
        self.assertFalse(_within_corridor(rendered, original, .95))

    def test_tampered_coverage_and_source_rejected(self):
        paths = build_valley_paths(self.geometry, self.hierarchy)
        bad = copy.deepcopy(paths)
        bad["arrays"] = {name: value.copy() for name, value in bad["arrays"].items()}
        if len(bad["arrays"]["chain_edge_indices"]):
            bad["arrays"]["chain_edge_indices"][0] = -1
            bad["identity_sha256"] = identity(bad["arrays"], bad["metadata"])
            with self.assertRaisesRegex(ValueError, "coverage"):
                validate_valley_paths(bad)
            bad = copy.deepcopy(paths)
            bad["arrays"] = {name: value.copy() for name, value in bad["arrays"].items()}
            bad["arrays"]["points_xyz_m"][0, 0] += 1.
            bad["identity_sha256"] = identity(bad["arrays"], bad["metadata"])
            with self.assertRaisesRegex(ValueError, "endpoint"):
                validate_valley_paths(bad)
        geometry = copy.deepcopy(self.geometry)
        geometry["metadata"] = dict(geometry["metadata"])
        geometry["metadata"]["hierarchy_identity"] = "0" * 64
        geometry["identity_sha256"] = identity(geometry["arrays"], geometry["metadata"])
        with self.assertRaises(ValueError):
            build_valley_paths(geometry, self.hierarchy)

    def test_real_chain_cross_leaf_and_protected_fall_back(self):
        geometry = load_channel_geometry(REAL_GEOMETRY,
                                         expected_sha256="ae50faeeb0d489abe6fab2d34294a5845bcf74fc8bf03fc68c5b6bf64dcbf810",
                                         expected_identity="bc064e888bb6e3ce7e650aedbf14ac5af80148ff1bf95ed48ec6139d54e165fe")
        hierarchy = load_basin_hierarchy(REAL_HIERARCHY,
                                         expected_sha256="36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                                         expected_identity="cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998")
        original = build_valley_paths(geometry, hierarchy, window=REAL_WINDOW)
        self.assertGreater(original["metadata"]["accepted_curved_chains"], 0)
        from terrain_pipeline.td_native_channel_valley_paths import _sample_native

        def cross_leaf(source, graph, points, *, strict=True, return_owner=False):
            sampled = _sample_native(source, graph, points, strict=strict, return_owner=return_owner)
            if return_owner and sampled is not None and len(sampled[1]) > 1:
                heights, owners = sampled
                owners = owners.copy()
                owners[-1] = owners[0] + 1
                return heights, owners
            return sampled

        with patch("terrain_pipeline.td_native_channel_valley_paths._sample_native", side_effect=cross_leaf):
            cross = build_valley_paths(geometry, hierarchy, window=REAL_WINDOW)
        self.assertEqual(cross["metadata"]["accepted_curved_chains"], 0)
        np.testing.assert_array_equal(cross["arrays"]["chain_edge_indices"], original["arrays"]["chain_edge_indices"])

        def protected(source, graph, points, *, strict=True, return_owner=False):
            if strict:
                return None
            return _sample_native(source, graph, points, strict=False)

        with patch("terrain_pipeline.td_native_channel_valley_paths._sample_native", side_effect=protected):
            fallback = build_valley_paths(geometry, hierarchy, window=REAL_WINDOW)
        self.assertEqual(fallback["metadata"]["accepted_curved_chains"], 0)
        self.assertEqual(fallback["metadata"]["accepted_chains"], 0)
        np.testing.assert_array_equal(fallback["arrays"]["chain_edge_indices"], original["arrays"]["chain_edge_indices"])
        self.assertTrue(np.any(geometry["arrays"]["node_internal_sink"]))


if __name__ == "__main__":
    unittest.main()
