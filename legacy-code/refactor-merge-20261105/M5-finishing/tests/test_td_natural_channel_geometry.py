import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import identity as bundle_identity
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.channel_geometry import NaturalGeometryRecipe, build_natural_channel_geometry, evaluate_natural_channel_window, load_natural_channel_geometry, load_natural_channel_window, save_natural_channel_geometry, save_natural_channel_window, validate_natural_channel_geometry, validate_natural_channel_window


def network_fixture(*, protected=False, unknown=False):
    shape = (7, 7)
    height = np.fromfunction(lambda row, column: 25. - row + abs(column - 3), shape)
    edges = np.array(((9, 16), (16, 23), (23, 24), (11, 18), (18, 25),
                      (25, 24), (24, 31), (31, 38)), np.int64)
    nodes = np.unique(edges)
    receiver = np.full(height.size, -1, np.int64)
    receiver[edges[:, 0]] = edges[:, 1]
    active_order = np.array((38, 31, 24, 23, 25, 16, 18, 9, 11), np.int64)
    inactive_order = np.setdiff1d(np.arange(height.size), nodes)
    order = np.concatenate((inactive_order, active_order))
    valid = np.ones(shape, bool)
    protection = np.zeros(shape, bool)
    if protected:
        protection[2, 1] = True
    if unknown:
        valid[2, 1] = False
    native = np.column_stack((nodes % shape[1] * 30., height.ravel()[nodes],
                              nodes // shape[1] * 30.))
    arrays = {"source_height_m": height, "valid_mask": valid,
              "protected_mask": protection,
              "open_boundary_mask": np.zeros(shape, bool),
              "receiver": receiver, "routing_order": order,
              "selected_basin_mask": valid & ~protection,
              "edge_cell_ids": edges, "node_cell_ids": nodes,
              "node_native_xyz_m": native,
              "node_width_m": np.full(len(nodes), 3.),
              "node_depth_m": np.full(len(nodes), 1.),
              "node_representative_q_m3_s": np.full(len(nodes), .1),
              "edge_requires_refinement": np.ones(len(edges), bool)}
    metadata = {"grid_shape": list(shape), "spacing_m": 30., "origin_m_xz": [0., 0.],
                "recipe": {"reference_q_m3_s": .1, "reference_width_m": 3.,
                           "reference_depth_m": 1., "width_exponent": .4,
                           "depth_exponent": .3, "minimum_width_m": 1.,
                           "maximum_width_m": 20., "minimum_depth_m": .1,
                           "maximum_depth_m": 4.}}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": "fixture-network"}


class NaturalChannelGeometryTests(unittest.TestCase):
    def build(self, network, recipe=NaturalGeometryRecipe()):
        with patch('terrain_pipeline.channel_geometry._i45_validate_natural_river_network'):
            return build_natural_channel_geometry(network, recipe)

    def window(self, geometry, network):
        with patch('terrain_pipeline.channel_geometry._i45_validate_natural_river_network'):
            return evaluate_natural_channel_window(
                geometry, network, window_origin_m_xz=(30., 30.), spacing_m=1.,
                shape_zx=(121, 121))

    def test_shared_junction_bed_sections_and_downhill_edges(self):
        geometry = self.build(network_fixture())
        arrays = geometry["arrays"]
        self.assertTrue(validate_natural_channel_geometry(geometry))
        endpoints = arrays["node_world_xyz_m"][np.searchsorted(
            arrays["node_cell_ids"], arrays["edge_cell_ids"])]
        np.testing.assert_array_equal(arrays["edge_centerline_xyz_m"], endpoints)
        np.testing.assert_array_equal(arrays["edge_sections_xyz_m"][:, (1, 4)], endpoints)
        self.assertTrue(np.all(endpoints[:, 0, 1] > endpoints[:, 1, 1]))
        self.assertTrue(geometry["metadata"]["summary"]["moved_nodes"] > 0)

    def test_centerline_changes_actual_cut_and_preserves_source(self):
        network = network_fixture()
        original = network["arrays"]["source_height_m"].copy()
        smooth = self.build(network)
        straight = self.build(network, NaturalGeometryRecipe(smoothing_strength=0.))
        smooth_window = self.window(smooth, network)
        straight_window = self.window(straight, network)
        self.assertGreater(np.count_nonzero(smooth_window["arrays"]["actual_cut_m"] !=
                                            straight_window["arrays"]["actual_cut_m"]), 0)
        np.testing.assert_array_equal(network["arrays"]["source_height_m"], original)
        self.assertTrue(validate_natural_channel_window(smooth_window))
        self.assertGreater(smooth_window["metadata"]["summary"]["actual_cut_volume_m3"], 0.)

    def test_protected_unknown_anchor_and_budget_diagnostics(self):
        for network in (network_fixture(protected=True), network_fixture(unknown=True)):
            geometry = self.build(network, NaturalGeometryRecipe(max_cut_m=.5))
            self.assertTrue(geometry["metadata"]["summary"]["over_budget_nodes"] > 0)
            window = self.window(geometry, network)
            self.assertTrue(np.all(window["arrays"]["actual_cut_m"][window["arrays"]["protected_mask"]] == 0))
            self.assertTrue(window["arrays"]["protected_mask"][30, 16])
            self.assertEqual(window["arrays"]["unknown_mask"][30, 16],
                             not network["arrays"]["valid_mask"][2, 1])
            self.assertTrue(window["metadata"]["summary"]["blocked_by_plan"])
            self.assertFalse(window["metadata"]["publishable"])

    def test_externally_pinned_cold_load(self):
        network = network_fixture()
        geometry = self.build(network)
        window = self.window(geometry, network)
        with tempfile.TemporaryDirectory() as directory:
            geometry_path = Path(directory) / "geometry.npz"
            window_path = Path(directory) / "window.npz"
            save_natural_channel_geometry(geometry_path, geometry)
            save_natural_channel_window(window_path, window)
            with patch('terrain_pipeline.channel_geometry.build_natural_channel_geometry',
                       side_effect=AssertionError("cold load rebuilt geometry")):
                loaded_geometry = load_natural_channel_geometry(
                    geometry_path, expected_sha256=file_sha256(geometry_path),
                    expected_identity=geometry["identity_sha256"])
                loaded_window = load_natural_channel_window(
                    window_path, expected_sha256=file_sha256(window_path),
                    expected_identity=window["identity_sha256"])
            self.assertFalse(loaded_geometry["arrays"]["node_world_xyz_m"].flags.writeable)
            self.assertFalse(loaded_window["arrays"]["actual_cut_m"].flags.writeable)
            with self.assertRaises(ValueError):
                load_natural_channel_window(window_path, expected_sha256="0" * 64,
                                            expected_identity=window["identity_sha256"])

    def test_rehashed_bank_and_budget_tampering_rejected(self):
        network = network_fixture()
        geometry = self.build(network)
        altered = {"metadata": geometry["metadata"],
                   "arrays": {key: value.copy() for key, value in geometry["arrays"].items()}}
        altered["arrays"]["edge_sections_xyz_m"][0, 0, 0] += 1.
        altered["identity_sha256"] = bundle_identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            validate_natural_channel_geometry(altered)
        window = self.window(geometry, network)
        altered_window = {"metadata": window["metadata"],
                          "arrays": {key: value.copy() for key, value in window["arrays"].items()}}
        altered_window["arrays"]["actual_cut_m"][1, 1] += .1
        altered_window["identity_sha256"] = bundle_identity(altered_window["arrays"],
                                                              altered_window["metadata"])
        with self.assertRaises(ValueError):
            validate_natural_channel_window(altered_window)

    def test_real_core_network_contract(self):
        from terrain_pipeline.td_natural_river_network import build_natural_river_network

        height = np.fromfunction(lambda row, column: 25. - row + abs(column - 3), (7, 7))
        source = make_td_source(height, spacing_m=30.)
        hierarchy = build_basin_hierarchy(source)
        network = build_natural_river_network(
            hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"])
        geometry = build_natural_channel_geometry(network)
        self.assertEqual(geometry["metadata"]["network_identity_sha256"],
                         network["identity_sha256"])
        self.assertEqual(geometry["metadata"]["summary"]["edge_count"],
                         network["metadata"]["summary"]["edge_count"])
        window = evaluate_natural_channel_window(
            geometry, network, window_origin_m_xz=(30., 30.), spacing_m=1.,
            shape_zx=(121, 121))
        self.assertGreater(window["metadata"]["summary"]["actual_cut_volume_m3"], 0.)


if __name__ == "__main__":
    unittest.main()
