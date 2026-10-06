import copy
import unittest

import numpy as np

from terrain_pipeline.large_surface_network_validation import (
    build_large_surface_network,
    preflight_large_network,
    validate_large_surface_network,
)


class LargeSurfaceNetworkTests(unittest.TestCase):
    def test_small_grid_covers_cells_and_cross_tile_edges(self):
        network = build_large_surface_network(64, seed=7, tile_cells=16)
        result = validate_large_surface_network(network)
        self.assertTrue(result["verified"])
        self.assertEqual(result["cells"], 4096)
        self.assertGreater(result["cross_tile_edges"], 0)
        self.assertEqual(network["manifest"]["stats"]["natural_outlet_cells"], 64)
        self.assertGreater(network["manifest"]["stats"]["engineering_outlet_cells"], 0)

    def test_same_seed_is_stable_and_different_seed_changes_identity(self):
        first = build_large_surface_network(32, seed=12, tile_cells=8)
        second = build_large_surface_network(32, seed=12, tile_cells=8)
        different = build_large_surface_network(32, seed=13, tile_cells=8)
        self.assertEqual(first["manifest"]["network_sha256"], second["manifest"]["network_sha256"])
        self.assertNotEqual(first["manifest"]["network_sha256"], different["manifest"]["network_sha256"])

    def test_tile_gap_receiver_and_outlet_tampering_rejected(self):
        network = build_large_surface_network(32, seed=2, tile_cells=8)
        for operation in ("gap", "receiver", "outlet"):
            changed = copy.deepcopy(network)
            if operation == "gap":
                changed["manifest"]["tiles"].pop()
            elif operation == "receiver":
                changed["receiver"] = changed["receiver"].copy()
                changed["receiver"][10, 10] = 0
            else:
                changed["outlet_kind"] = changed["outlet_kind"].copy()
                changed["outlet_kind"][0, 0] = 3
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    validate_large_surface_network(changed)

    def test_tile_summary_tampering_rejected(self):
        network = build_large_surface_network(32, seed=2, tile_cells=8)
        changed = copy.deepcopy(network)
        changed["manifest"]["tiles"][0]["height_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "tile summary"):
            validate_large_surface_network(changed)

    def test_preflight_rejects_before_building_large_arrays(self):
        with self.assertRaises(ValueError):
            preflight_large_network(4096)
        with self.assertRaises(ValueError):
            preflight_large_network(1024, tile_cells=0)

    def test_manifest_does_not_claim_dynamic_hydrology(self):
        network = build_large_surface_network(16, seed=5, tile_cells=4)
        self.assertEqual(network["manifest"]["dynamic_status"], "not_computed")
        self.assertEqual(network["manifest"]["source"]["mode"], "deterministic_synthetic")


if __name__ == "__main__":
    unittest.main()
