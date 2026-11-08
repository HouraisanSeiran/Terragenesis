import unittest

from tools.prepare_climate_matched_river_reference import source_tile
from tools.survey_global_river_climate import distance_km, select_locations


class GlobalReferenceSourcesTests(unittest.TestCase):
    def test_geographic_selection_is_input_order_invariant_and_separated(self):
        coordinates = [(-94.25 + index / 10, 39.1) for index in range(12)]
        selected = select_locations(coordinates, minimum_distance_km=25, maximum=12)
        self.assertEqual(selected, select_locations(list(reversed(coordinates)), minimum_distance_km=25, maximum=12))
        self.assertGreater(len(selected), 1)
        for index, first in enumerate(selected):
            for second in selected[index + 1:]:
                self.assertGreaterEqual(distance_km(first, second), 25)

    def test_official_source_tile_index_for_separated_missouri_windows(self):
        self.assertEqual(source_tile((-94.25, 39.083333)), "srtm_18_05")
        self.assertEqual(source_tile((-93.41666, 40.25)), "srtm_18_04")
        self.assertEqual(source_tile((-95.08333, 39.08333)), "srtm_17_05")


if __name__ == "__main__":
    unittest.main()
