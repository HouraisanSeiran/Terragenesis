import unittest

import numpy as np

from terrain_pipeline.natural_outlet_certification import certify_natural_outlets, validate_certification


class NaturalOutletCertificationTests(unittest.TestCase):
    def setUp(self):
        self.height = np.array([[5., 4., 3., 2.], [6., 5., 4., 1.], [7., 6., 5., 0.]])
        self.valid = np.ones_like(self.height, dtype=bool)
        self.receiver = np.array([[4, 5, 6, 7], [8, 9, 10, 11], [8, 9, 11, -1]])
        self.coast = np.zeros_like(self.valid)
        self.coast[2, 3] = True

    def test_explicit_observed_downhill_connection_certifies(self):
        report = certify_natural_outlets(self.height, self.valid, self.receiver, self.coast, 0., [{
            "terminal_cell_id": 11, "coastline_cell_id": 11, "path_cell_ids": [11],
            "independent_observation": True,
        }])
        validate_certification(report)
        self.assertTrue(report["natural_outlet_verified"])

    def test_missing_observation_cannot_certify(self):
        report = certify_natural_outlets(self.height, self.valid, self.receiver, self.coast, 0., [{
            "terminal_cell_id": 11, "coastline_cell_id": 11, "path_cell_ids": [11],
            "independent_observation": False,
        }])
        validate_certification(report)
        self.assertFalse(report["ocean_outlet_certified"])


if __name__ == "__main__":
    unittest.main()
