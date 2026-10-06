import copy
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.real_dem_flat_routing import resolve_dem_flats, validate_flat_routing
from terrain_pipeline.real_dem_tiled_network import build_tiled_network


def fixture(height):
    values = np.asarray(height, np.float64)
    return {"arrays": {"height_m": values, "valid_mask": np.isfinite(values), "unknown_mask": ~np.isfinite(values)}}


class RealDemFlatRoutingTests(unittest.TestCase):
    def assert_network_same(self, first, second):
        for name in ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal"):
            np.testing.assert_array_equal(getattr(first, name), getattr(second, name))

    def test_equal_plate_drains_to_lower_exit_without_height_changes(self):
        candidate = fixture([[5, 5, 5, 5, 5], [5, 5, 5, 5, 5], [5, 5, 5, 5, 0]])
        before = array_hash(candidate["arrays"]["height_m"])
        raw = build_tiled_network(candidate)
        result = resolve_dem_flats(candidate, tile_size=2)
        self.assertTrue(validate_flat_routing(candidate, result)["verified"])
        summary = result["summary"]
        self.assertEqual(summary["resolved_terminals"], 1)
        self.assertEqual(summary["closed_component_count"], 1)
        self.assertEqual(summary["draining_component_count"], 1)
        self.assertEqual(summary["contributing_cells_sum"], 15)
        self.assertEqual(result["components"][0]["exit_seed_cell_ids"], [8, 9, 13])
        self.assertEqual(result["distance_to_exit"][0, 0], 3)
        np.testing.assert_array_equal(result["network"].receiver[raw.receiver >= 0], raw.receiver[raw.receiver >= 0])
        self.assertEqual(array_hash(candidate["arrays"]["height_m"]), before)
        self.assertFalse(summary["natural_outlet_verified"])

    def test_closed_plate_one_root_risk_and_retention_not_ocean(self):
        candidate = fixture(np.ones((4, 6)))
        result = resolve_dem_flats(candidate)
        self.assertTrue(validate_flat_routing(candidate, result)["verified"])
        self.assertEqual(result["summary"]["raw_terminals"], 24)
        self.assertEqual(result["summary"]["resolved_terminals"], 1)
        self.assertEqual(result["network"].receiver[0, 0], -1)
        self.assertEqual(result["network"].accumulation_cells[0, 0], 24)
        self.assertEqual(result["components"][0]["root_cell_id"], 0)
        self.assertEqual(result["components"][0]["classification"], "closed_flat_retention")
        self.assertTrue(result["components"][0]["touches_boundary"])
        self.assertFalse(result["components"][0]["ocean_outlet_certified"])

    def test_unknown_splits_components_and_risks_propagate_separately(self):
        candidate = fixture([[7, 7, np.nan, 7, 7], [7, 7, np.nan, 7, 7], [7, 7, np.nan, 7, 7]])
        result = resolve_dem_flats(candidate, tile_size=2)
        self.assertTrue(validate_flat_routing(candidate, result)["verified"])
        self.assertEqual([record["component_id"] for record in result["components"]], [0, 3])
        self.assertEqual(result["summary"]["resolved_terminals"], 2)
        self.assertTrue(all(record["touches_unknown"] for record in result["components"]))
        self.assertFalse(result["network"].unknown_adjacent_terminal[0, 0])
        self.assertTrue(result["network"].unknown_adjacent_terminal[0, 3])
        self.assertTrue(np.all(result["component_id"][:, 2] == -1))
        self.assertTrue(np.all(result["distance_to_exit"][:, 2] == -1))

    def test_saddle_multiple_seeds_and_minimum_global_id_tie(self):
        candidate = fixture([[0, 5, 5, 5, 0], [5, 5, 5, 5, 5], [5, 5, 5, 5, 5]])
        result = resolve_dem_flats(candidate)
        self.assertTrue(validate_flat_routing(candidate, result)["verified"])
        self.assertEqual(result["distance_to_exit"][1, 2], 1)
        self.assertEqual(result["network"].receiver[1, 2], 1)
        self.assertEqual(result["summary"]["resolved_terminals"], 2)
        self.assertEqual(result["summary"]["contributing_cells_sum"], 15)

    def test_d8_diagonal_equal_connectivity_and_singletons(self):
        candidate = fixture([[2, np.nan, np.nan], [np.nan, 2, np.nan], [np.nan, np.nan, 2]])
        result = resolve_dem_flats(candidate)
        self.assertEqual(len(result["components"]), 1)
        self.assertEqual(result["network"].receiver[2, 2], 4)
        self.assertTrue(validate_flat_routing(candidate, result)["verified"])
        single = fixture([[3.]])
        result = resolve_dem_flats(single)
        self.assertEqual(result["network"].order.tolist(), [0])
        self.assertTrue(validate_flat_routing(single, result)["verified"])

    def test_deterministic_tile_sizes_and_orders_all_result_fields(self):
        height = np.random.default_rng(87).integers(0, 4, (23, 29)).astype(float)
        height[10:13, 15] = np.nan
        candidate = fixture(height)
        expected = resolve_dem_flats(candidate, tile_size=1)
        for size in (3, 8, 256, 512):
            for order in ("row_major", "reversed"):
                with self.subTest(size=size, order=order):
                    result = resolve_dem_flats(candidate, tile_size=size, tile_order=order)
                    self.assert_network_same(result["network"], expected["network"])
                    np.testing.assert_array_equal(result["component_id"], expected["component_id"])
                    np.testing.assert_array_equal(result["distance_to_exit"], expected["distance_to_exit"])
                    self.assertEqual(result["components"], expected["components"])
                    self.assertEqual(result["summary"], expected["summary"])
                    self.assertTrue(validate_flat_routing(candidate, result)["verified"])

    def test_validator_does_not_replay_resolver_or_tiled_builder(self):
        candidate = fixture([[5, 5, 5], [5, 5, 0]])
        result = resolve_dem_flats(candidate)
        with patch("terrain_pipeline.real_dem_flat_routing.resolve_dem_flats", side_effect=AssertionError("no replay")), \
                patch("terrain_pipeline.real_dem_flat_routing.build_tiled_network", side_effect=AssertionError("no rebuild")):
            self.assertTrue(validate_flat_routing(candidate, result)["verified"])

    def test_malicious_receiver_order_component_distance_accumulation_and_flags(self):
        candidate = fixture([[5, 5, 5, 5], [5, 5, 5, 0]])
        original = resolve_dem_flats(candidate)
        mutations = []
        for cell, target in ((7, 6), (0, 7), (6, 0), (0, 0)):
            result = copy.deepcopy(original)
            result["network"].receiver.flat[cell] = target
            mutations.append(result)
        result = copy.deepcopy(original)
        result["network"].order[:] = result["network"].order[::-1]
        mutations.append(result)
        result = copy.deepcopy(original)
        result["network"] = replace(result["network"], order=result["network"].order[:-1])
        mutations.append(result)
        for name in ("component_id", "distance_to_exit"):
            result = copy.deepcopy(original)
            result[name].flat[0] += 2
            mutations.append(result)
        result = copy.deepcopy(original)
        result["network"].accumulation_cells.flat[7] += 1
        mutations.append(result)
        result = copy.deepcopy(original)
        result["network"].boundary_outlet.flat[7] = False
        mutations.append(result)
        result = copy.deepcopy(original)
        result["components"][0]["touches_boundary"] = False
        mutations.append(result)
        result = copy.deepcopy(original)
        result["components"][0]["exit_seed_cell_ids"] = []
        mutations.append(result)
        result = copy.deepcopy(original)
        result["distance_to_exit"][:] += 1
        mutations.append(result)
        result = copy.deepcopy(original)
        result["components"][0]["natural_outlet_verified"] = True
        mutations.append(result)
        result = copy.deepcopy(original)
        result["summary"]["natural_outlet_verified"] = True
        mutations.append(result)
        for index, result in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_flat_routing(candidate, result)

    def test_source_height_change_rejected_even_if_mask_stays_valid(self):
        candidate = fixture([[1, 1], [1, 1]])
        result = resolve_dem_flats(candidate)
        candidate["arrays"]["height_m"] += 1
        with self.assertRaises(ValueError):
            validate_flat_routing(candidate, result)

    def test_invalid_parameters_unknown_resource_and_result_types(self):
        for size in (True, 0, -1, 1025, 1.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                resolve_dem_flats(fixture([[2, 1]]), tile_size=size)
        with self.assertRaises(ValueError):
            resolve_dem_flats(fixture([[2, 1]]), tile_order="random")
        with self.assertRaises(ValueError):
            resolve_dem_flats(fixture(np.zeros((701, 714))))
        with self.assertRaises(ValueError):
            resolve_dem_flats(fixture([[np.nan]]))
        candidate = fixture([[1, 1]])
        result = resolve_dem_flats(candidate)
        result["component_id"] = result["component_id"].astype(float)
        with self.assertRaises(ValueError):
            validate_flat_routing(candidate, result)


if __name__ == "__main__":
    unittest.main()
