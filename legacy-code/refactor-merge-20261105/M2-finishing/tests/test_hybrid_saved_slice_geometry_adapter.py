import unittest

from tools.hybrid_saved_slice_geometry_adapter import consume_saved_slice, describe_saved_slice


class SavedSliceGeometryAdapterTests(unittest.TestCase):
    def test_consumes_declared_empty_slice_without_fabricating_area(self):
        domain = consume_saved_slice({"polygons_uv_m": [], "holes_uv_m": [], "area_m2": 0.0})
        self.assertTrue(domain.is_empty)
        self.assertEqual(domain.area, 0.0)

    def test_keeps_positive_numeric_sliver_and_hole_owner(self):
        record = {"polygons_uv_m": [
                      [[0, 0], [1e-5, 0], [0, 1e-5]],
                      [[2, 0], [4, 0], [4, 2], [2, 2]]],
                  "holes_uv_m": [[], [[[2.25, .25], [2.5, .25], [2.5, .5], [2.25, .5]]]]}
        domain = consume_saved_slice(record)
        self.assertGreater(domain.area, 0.0)
        self.assertEqual(len(domain.geoms), 2)
        description = describe_saved_slice(record)
        self.assertEqual(description["positive_area_sliver_polygon_count"], 1)
        self.assertEqual(description["hole_ownership"], [0, 1])

    def test_consumes_owned_hole_without_filling_it(self):
        record = {"polygons_uv_m": [[[0, 0], [4, 0], [4, 4], [0, 4]]],
                  "holes_uv_m": [[[[1, 1], [3, 1], [3, 3], [1, 3]]]],
                  "area_m2": 12.0}
        domain = consume_saved_slice(record)
        self.assertEqual(domain.area, 12.0)
        self.assertEqual(len(domain.interiors), 1)

    def test_rejects_hole_outside_owner_without_repair(self):
        record = {"polygons_uv_m": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
                  "holes_uv_m": [[[[2, 2], [3, 2], [3, 3], [2, 3]]]],
                  "area_m2": 1.0}
        with self.assertRaisesRegex(ValueError, "hole"):
            consume_saved_slice(record)

    def test_rejects_non_adjacent_polygon_overlap(self):
        square = [[0, 0], [2, 0], [2, 2], [0, 2]]
        record = {"polygons_uv_m": [square, [[1, 1], [3, 1], [3, 3], [1, 3]],
                                     [[10, 10], [11, 10], [11, 11], [10, 11]]],
                  "holes_uv_m": [[], [], []]}
        with self.assertRaisesRegex(ValueError, "overlapping"):
            consume_saved_slice(record)

    def test_rejects_nan_boundary_coordinate(self):
        record = {"polygons_uv_m": [[[0, 0], [1, 0], [float("nan"), 1]]],
                  "holes_uv_m": [[]]}
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            consume_saved_slice(record)


if __name__ == "__main__":
    unittest.main()
