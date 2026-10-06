import unittest

import numpy as np

from tools.audit_td_source_conforming_banks_v3 import edge_key
from tools.td_ported_junction_saved_audit_v2 import EdgeCandidateIndex

FIRST = np.array([-178318.9680553527, 68880.68796309819])
SECOND = np.array([-178323.47702865908, 68882.31801910605])
SPLIT = np.array([-178320., 68881.06102531386])


def xyz(first, second):
    return np.array([[first[0], 1340., first[1]], [second[0], 1340., second[1]]])


class SpatialEdgeCandidateTests(unittest.TestCase):
    def test_real_segment34_large_coordinate_hash_miss_still_finds_owner(self):
        original_key = edge_key([FIRST, SECOND])
        split_key = edge_key([SECOND, SPLIT])
        self.assertNotEqual(original_key, split_key)
        original = xyz(FIRST, SECOND)
        index = EdgeCandidateIndex(30., [-180000., 68000.])
        index.add("junction:25", 1, original)
        found = list(index.matching_sides(SECOND, SPLIT))
        self.assertEqual([(identifier, edge) for identifier, edge, points, fractions in found], [("junction:25", 1)])
        np.testing.assert_allclose(found[0][3], [1., .22886466101455713], atol=1e-10, rtol=0.)

    def test_broad_phase_does_not_relax_distance_or_original_interval(self):
        vector = SECOND-FIRST
        normal = np.array([-vector[1], vector[0]])/np.linalg.norm(vector)
        index = EdgeCandidateIndex(30., [-180000., 68000.])
        index.add("junction:25", 1, xyz(FIRST, SECOND))
        index.add("legacy06:1", 0, xyz(SECOND, FIRST))
        index.add("near_but_not_collinear", 0, xyz(FIRST+normal*1e-7, SECOND+normal*1e-7))
        found = list(index.matching_sides(SECOND, SPLIT))
        self.assertEqual({identifier for identifier, edge, points, fractions in found}, {"junction:25", "legacy06:1"})
        with self.assertRaisesRegex(ValueError, "omitted original T knot"):
            list(index.matching_sides(SECOND+vector*.1, FIRST-vector*.1))


if __name__ == "__main__":
    unittest.main()
