import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import hashlib
import json

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.td_natural_river_network import (
    NaturalNetworkRecipe,
    build_natural_river_network,
    load_natural_river_network,
    save_natural_river_network,
    validate_natural_river_network,
)


def hierarchy(height, *, protected=None, valid=None, opened=None):
    source = make_td_source(np.asarray(height, np.float64), spacing_m=30.0,
                            valid_mask=valid, protected_mask=protected, open_boundary_mask=opened)
    return build_basin_hierarchy(source)


def build(height, *, recipe=None):
    source = hierarchy(height)
    return build_natural_river_network(source, expected_hierarchy_identity=source["identity_sha256"],
                                       recipe=recipe or NaturalNetworkRecipe())


def slope_grid(size=9):
    row, column = np.indices((size, size))
    return (size - row + size - column).astype(np.float64)


class NaturalRiverNetworkTests(unittest.TestCase):
    def test_selected_edges_close_to_terminal_and_filter_hillslopes(self):
        source = hierarchy(slope_grid())
        network = build_natural_river_network(source, expected_hierarchy_identity=source["identity_sha256"])
        arrays = network["arrays"]
        edges = arrays["edge_cell_ids"]
        self.assertLess(len(edges), np.count_nonzero(source["arrays"]["receiver"] >= 0))
        self.assertEqual(network["metadata"]["summary"]["basin_count"], 1)
        self.assertEqual(network["metadata"]["summary"]["selected_terminal_cell_id"], 80)
        self.assertIn(80, arrays["node_cell_ids"])
        self.assertTrue(np.array_equal(edges[:, 1], arrays["receiver"][edges[:, 0]]))
        self.assertTrue(np.array_equal(np.unique(edges), arrays["node_cell_ids"]))
        self.assertEqual(sum(np.diff(arrays["reach_offsets"]) - 1), len(edges))

    def test_strong_event_changes_discharge_only(self):
        height = slope_grid()
        original = build(height)
        changed = build(height, recipe=replace(NaturalNetworkRecipe(), strong_rainfall_mm=180.0,
                                               strong_duration_s=3600.0, strong_frequency_per_year=1.0))
        for key in ("edge_cell_ids", "edge_level_code", "node_cell_ids", "node_width_m", "node_depth_m",
                    "node_native_xyz_m", "reach_offsets", "reach_cell_ids"):
            np.testing.assert_array_equal(original["arrays"][key], changed["arrays"][key])
        self.assertEqual(original["metadata"]["stable_identity_sha256"], changed["metadata"]["stable_identity_sha256"])
        self.assertNotEqual(original["metadata"]["forcing_identity_sha256"], changed["metadata"]["forcing_identity_sha256"])
        self.assertFalse(np.array_equal(original["arrays"]["edge_q_strong_m3_s"], changed["arrays"]["edge_q_strong_m3_s"]))
        metadata = original["metadata"]
        payload = {"algorithm": metadata["algorithm"], "hierarchy": metadata["hierarchy_identity_sha256"],
                   "ordinary": metadata["forcing"][:3],
                   "geometry_recipe": {key: value for key, value in metadata["recipe"].items()
                                       if not key.startswith("strong_")}}
        expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                             allow_nan=False).encode()).hexdigest()
        self.assertEqual(metadata["stable_identity_sha256"], expected)

    def test_area_alone_cannot_make_perennial(self):
        recipe = replace(NaturalNetworkRecipe(), baseflow_mm_per_day=0,
                         minimum_area_m2=900, seasonal_area_m2=1800, perennial_area_m2=2700,
                         mainstem_area_m2=3600, minimum_q_m3_s=1e-8,
                         seasonal_q_m3_s=1e-8, perennial_q_m3_s=1e-8, mainstem_q_m3_s=1e-8)
        network = build(slope_grid(), recipe=recipe)
        self.assertGreater(network["metadata"]["summary"]["edge_count"], 0)
        self.assertLessEqual(int(network["arrays"]["edge_level_code"].max()), 1)

    def test_confluence_includes_local_runoff(self):
        network = build(slope_grid())
        arrays = network["arrays"]
        receiver = arrays["receiver"]
        junctions = np.flatnonzero(np.bincount(receiver[receiver >= 0], minlength=receiver.size) >= 2)
        self.assertGreater(len(junctions), 0)
        cell = int(junctions[0])
        donors = np.flatnonzero(receiver == cell)
        for scenario in range(4):
            self.assertAlmostEqual(arrays["routed_q_m3_s"][scenario, cell],
                                   arrays["local_q_m3_s"][scenario, cell] +
                                   arrays["routed_q_m3_s"][scenario, donors].sum())

    def test_normal_twelve_by_twelve_produces_gullies(self):
        network = build(slope_grid(12))
        self.assertGreater(network["metadata"]["summary"]["edge_count"], 0)
        self.assertGreater(network["metadata"]["summary"]["level_counts"]["small_gully"], 0)

    def test_refinement_and_basin_score_are_reviewable(self):
        network = build(slope_grid(12))
        arrays = network["arrays"]
        metadata = network["metadata"]
        weights = metadata["basin_score_weights"]
        basin = metadata["selected_basin"]
        self.assertAlmostEqual(basin["score"], sum(weights[key] * basin["score_components"][key] for key in weights))
        self.assertEqual(basin["strahler_order"], int(arrays["basin_strahler_order"][0]))
        self.assertTrue(np.array_equal(arrays["edge_requires_refinement"], arrays["edge_refinement_reason_bits"] != 0))
        self.assertTrue(np.all(arrays["edge_target_spacing_m"] <= arrays["node_width_m"][
            np.searchsorted(arrays["node_cell_ids"], arrays["edge_cell_ids"][:, 0])] / 4))
        self.assertTrue(np.all(arrays["edge_target_spacing_m"] < 0.25))
        self.assertEqual(metadata["summary"]["mainstem_diagnostic"]["reason"],
                         "area_or_discharge_threshold_unmet")
        self.assertIn("no temporal runoff release", metadata["physics_semantics"])

    def test_flat_valley_support_is_relative_to_banks(self):
        height = np.array([[8, 8, 8, 8, 8, 8, 8], [5, 5, 5, 5, 5, 5, 4],
                           [8, 8, 8, 8, 8, 8, 8]], np.float64)
        network = build(height, recipe=replace(NaturalNetworkRecipe(), minimum_q_m3_s=1e-6))
        arrays = network["arrays"]
        flat = arrays["edge_slope_m_per_m"] == 0
        self.assertTrue(np.any(flat))
        self.assertTrue(np.all(arrays["edge_valley_support"][flat] > 0))
        self.assertEqual(arrays["receiver"][network["metadata"]["summary"]["selected_terminal_cell_id"]], -1)

    def test_protected_or_unknown_contact_is_diagnosed_and_rejected(self):
        height = slope_grid()
        protected = np.zeros(height.shape, bool)
        protected[4, 4] = True
        source = hierarchy(height, protected=protected)
        with self.assertRaisesRegex(ValueError, "protected contact diagnostics"):
            build_natural_river_network(source, expected_hierarchy_identity=source["identity_sha256"])
        valid = np.ones(height.shape, bool)
        valid[4, 4] = False
        source = hierarchy(height, valid=valid)
        with self.assertRaisesRegex(ValueError, "unknown/protected contact diagnostics"):
            build_natural_river_network(source, expected_hierarchy_identity=source["identity_sha256"])

    def test_save_load_external_pins_and_source_audit(self):
        source = hierarchy(slope_grid())
        network = build_natural_river_network(source, expected_hierarchy_identity=source["identity_sha256"])
        self.assertTrue(validate_natural_river_network(network, hierarchy=source))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.npz"
            save_natural_river_network(path, network)
            sha = file_sha256(path)
            loaded = load_natural_river_network(path, expected_sha256=sha,
                                                expected_identity=network["identity_sha256"], hierarchy=source)
            with self.assertRaises(ValueError):
                loaded["arrays"]["node_width_m"][0] = 0
            with self.assertRaises(ValueError):
                load_natural_river_network(path, expected_sha256="0" * 64,
                                           expected_identity=network["identity_sha256"])
            with self.assertRaises(ValueError):
                load_natural_river_network(path, expected_sha256=sha, expected_identity="0" * 64)

    def test_rehashed_tampering_and_invalid_recipe_are_rejected(self):
        source = hierarchy(slope_grid())
        network = build_natural_river_network(source, expected_hierarchy_identity=source["identity_sha256"])
        arrays = {key: value.copy() for key, value in network["arrays"].items()}
        arrays["source_height_m"][0, 0] += 1
        altered = {"arrays": arrays, "metadata": network["metadata"],
                   "identity_sha256": identity(arrays, network["metadata"])}
        with self.assertRaisesRegex(ValueError, "source audit mismatch"):
            validate_natural_river_network(altered, hierarchy=source)
        arrays = {key: value.copy() for key, value in network["arrays"].items()}
        arrays["routed_q_m3_s"][1, -1] += 1
        altered = {"arrays": arrays, "metadata": network["metadata"],
                   "identity_sha256": identity(arrays, network["metadata"])}
        with self.assertRaisesRegex(ValueError, "not conserved"):
            validate_natural_river_network(altered)
        for key, new_value in (("edge_level_code", 3), ("node_width_m", 7.0),
                               ("edge_refinement_reason_bits", 0), ("basin_score", 0.0),
                               ("contributing_area_m2", 0.0)):
            arrays = {name: value.copy() for name, value in network["arrays"].items()}
            arrays[key][0] = new_value
            altered = {"arrays": arrays, "metadata": network["metadata"],
                       "identity_sha256": identity(arrays, network["metadata"])}
            with self.assertRaises(ValueError, msg=key):
                validate_natural_river_network(altered)
        with self.assertRaises(ValueError):
            NaturalNetworkRecipe(strong_rainfall_mm=True)
        with self.assertRaises(ValueError):
            NaturalNetworkRecipe(baseflow_mm_per_day=float("nan"))


if __name__ == "__main__":
    unittest.main()
