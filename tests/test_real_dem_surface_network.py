import unittest

import numpy as np

from terrain_pipeline.drainage import build_real_dem_network as build_real_dem_network
from terrain_pipeline.drainage import validate_real_dem_network as validate_real_dem_network


class RealDemSurfaceNetworkTests(unittest.TestCase):
    def test_valid_dem_routes_downhill_and_keeps_unknown_as_barrier(self):
        height = np.array([[9, 8, 7, 6], [8, 7, 6, 5], [7, 6, 5, 4], [6, 5, 4, 3]], dtype=float)
        valid = np.ones_like(height, dtype=bool)
        valid[1, 1] = False
        height[1, 1] = np.nan
        network = build_real_dem_network(height, valid)
        result = validate_real_dem_network(network, height, valid)
        self.assertTrue(result["verified"])
        self.assertEqual(result["unknown_cells"], 1)
        targets = network.receiver[network.receiver >= 0]
        self.assertTrue(np.all(valid.ravel()[targets]))
        self.assertFalse(result["natural_outlet_verified"])
        self.assertTrue(np.all(network.receiver[valid] >= -1))

    def test_invalid_receiver_into_unknown_is_rejected(self):
        height = np.arange(16, dtype=float).reshape(4, 4)
        valid = np.ones_like(height, dtype=bool)
        valid[1, 1] = False
        network = build_real_dem_network(height, valid)
        network.receiver[0, 0] = 5
        with self.assertRaisesRegex(ValueError, "unknown"):
            validate_real_dem_network(network, height, valid)
