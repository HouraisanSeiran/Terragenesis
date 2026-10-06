from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.dem_domain import load_dem_candidate
from terrain_pipeline.real_dem_surface_network import build_real_dem_network
from terrain_pipeline.real_dem_tiled_network import (
    CandidateTileReader, build_tiled_network, validate_tiled_network,
)


def fixture(height):
    values = np.asarray(height, dtype=np.float64)
    return {"arrays": {"height_m": values, "valid_mask": np.isfinite(values),
                       "unknown_mask": ~np.isfinite(values)}}


class RealDemTiledNetworkTests(unittest.TestCase):
    def assert_same(self, actual, expected):
        for name in ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal"):
            np.testing.assert_array_equal(getattr(actual, name), getattr(expected, name), err_msg=name)

    def test_unknown_seams_ragged_tiles_and_loading_order_match_reference(self):
        height = np.random.default_rng(812).integers(-5, 20, (13, 17)).astype(float)
        height[3:6, 4] = np.nan
        height[0, 1] = np.nan
        height[8, 9] = np.nan
        candidate = fixture(height)
        expected = build_real_dem_network(height, candidate["arrays"]["valid_mask"])
        for size in (1, 2, 4, 7, 256):
            for order in ("row_major", "reversed"):
                with self.subTest(size=size, order=order):
                    actual = build_tiled_network(candidate, tile_size=size, tile_order=order)
                    self.assert_same(actual, expected)
                    result = validate_tiled_network(candidate, actual, tile_size=size)
                    self.assertTrue(result["verified"])
                    self.assertEqual(result["contributing_cells_sum"], np.isfinite(height).sum())

    def test_direction_ties_strict_flat_and_unknown_barriers(self):
        height = np.array([[1, 1, 1], [1, 9, 1], [1, 1, 1]], float)
        actual = build_tiled_network(fixture(height), tile_size=1)
        self.assertEqual(actual.receiver[1, 1], 0)
        self.assertEqual(actual.order.tolist(), [4, 0, 1, 2, 3, 5, 6, 7, 8])
        self.assertEqual(actual.accumulation_cells[0, 0], 2.)
        height[0, 0] = np.nan
        actual = build_tiled_network(fixture(height), tile_size=2)
        self.assertEqual(actual.receiver[1, 1], 1)
        self.assertTrue(actual.unknown_adjacent_terminal[0, 1])
        self.assertTrue(actual.boundary_outlet[0, 1])
        flat = fixture(np.ones((5, 7)))
        result = validate_tiled_network(flat, build_tiled_network(flat), tile_size=2)
        self.assertEqual(result["terminal_cells"], 35)

    def test_single_row_column_and_single_cell(self):
        for height in (np.array([[3, 2, 1.]]), np.array([[3.], [2.], [1.]]), np.array([[5.]])):
            candidate = fixture(height)
            actual = build_tiled_network(candidate, tile_size=1)
            self.assert_same(actual, build_real_dem_network(height, np.isfinite(height)))
            self.assertTrue(validate_tiled_network(candidate, actual, tile_size=1)["verified"])

    def test_256_512_partial_tiles_at_real_candidate_shape(self):
        rows, cols = np.indices((674, 438))
        height = (rows * 2 + cols).astype(float)
        height[255:258, 255] = np.nan
        candidate = fixture(height)
        expected = build_real_dem_network(height, np.isfinite(height))
        for size in (256, 512):
            actual = build_tiled_network(candidate, tile_size=size, tile_order="reversed")
            self.assert_same(actual, expected)
            result = validate_tiled_network(candidate, actual, tile_size=size)
            self.assertTrue(result["verified"])
            self.assertLessEqual(result["reader"]["peak_window_cells"], (size + 2) ** 2)
            self.assertEqual(result["reader"]["read_windows"], ((674 + size - 1) // size) * ((438 + size - 1) // size))

    def test_reader_readonly_views_halo_bounds_counters_and_no_input_mutation(self):
        candidate = fixture(np.arange(35.).reshape(5, 7))
        before = candidate["arrays"]["height_m"].copy()
        reader = CandidateTileReader(candidate, tile_size=3)
        tiles = list(reader.iter_tiles())
        self.assertEqual(tiles[0].core_bounds, (0, 3, 0, 3))
        self.assertEqual(tiles[0].window_bounds, (0, 4, 0, 4))
        self.assertEqual(tiles[-1].core_bounds, (3, 5, 6, 7))
        self.assertEqual(tiles[-1].window_bounds, (2, 5, 5, 7))
        self.assertEqual(reader.read_windows, 6)
        self.assertEqual(reader.peak_window_cells, 20)
        self.assertTrue(np.shares_memory(tiles[0].height_m, candidate["arrays"]["height_m"]))
        with self.assertRaises(ValueError):
            tiles[0].height_m[0, 0] = 99
        with self.assertRaises(ValueError):
            tiles[0].valid_mask[0, 0] = False
        build_tiled_network(candidate, tile_size=2)
        np.testing.assert_array_equal(before, candidate["arrays"]["height_m"])
        self.assertTrue(candidate["arrays"]["height_m"].flags.writeable)

    def test_invalid_tile_order_sizes_windows_and_resource_budget(self):
        candidate = fixture([[1., 2.], [3., 4.]])
        for size in (True, False, 0, -1, 1.5, "256", 1025):
            with self.subTest(size=size), self.assertRaises(ValueError):
                build_tiled_network(candidate, tile_size=size)
        for order in (True, "random", None):
            with self.subTest(order=order), self.assertRaises(ValueError):
                build_tiled_network(candidate, tile_order=order)
        reader = CandidateTileReader(candidate)
        for bounds in ((True, 2, 0, 2), (-1, 2, 0, 2), (0, 0, 0, 2), (0, 3, 0, 2), (0., 2, 0, 2)):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                reader.read_window(*bounds)
        with self.assertRaises(ValueError):
            build_tiled_network(fixture(np.zeros((701, 714))))

    def test_invalid_candidate_shape_dtype_and_masks(self):
        for candidate in (fixture(np.empty((0, 3))), fixture([[np.nan]]), fixture([[np.inf]]),
                          {"arrays": {"height_m": np.zeros((2, 2), np.float32), "valid_mask": np.ones((2, 2), bool)}},
                          {"arrays": {"height_m": np.zeros((2, 2)), "valid_mask": np.ones((2, 3), bool)}},
                          {"arrays": {"height_m": np.zeros((2, 2)), "valid_mask": np.ones((2, 2), int)}},
                          {"arrays": {"height_m": np.zeros((2, 2)), "valid_mask": np.ones((2, 2), bool),
                                      "unknown_mask": np.ones((2, 2), bool)}}):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                build_tiled_network(candidate)

    def test_validation_is_independent_and_rejects_tampered_fields(self):
        candidate = fixture([[1., 1., 1.], [1., 9., 1.], [1., 1., np.nan]])
        original = build_tiled_network(candidate, tile_size=2)
        with patch("terrain_pipeline.real_dem_tiled_network.build_tiled_network", side_effect=AssertionError("no replay")):
            self.assertTrue(validate_tiled_network(candidate, original)["verified"])
        changes = []
        for target in (1, 4, 8, 99, -2):
            receiver = original.receiver.copy()
            receiver[1, 1] = target
            changes.append(replace(original, receiver=receiver))
        for name in ("boundary_outlet", "unknown_adjacent_terminal"):
            values = getattr(original, name).copy()
            values[0, 0] = ~values[0, 0]
            changes.append(replace(original, **{name: values}))
        accumulation = original.accumulation_cells.copy()
        accumulation[0, 0] += 1
        changes.append(replace(original, accumulation_cells=accumulation))
        order = original.order.copy()
        order[1:3] = order[1:3][::-1]
        changes.append(replace(original, order=order))
        changes.append(replace(original, order=original.order[:-1]))
        changes.append(replace(original, receiver=original.receiver.astype(float)))
        for network in changes:
            with self.subTest(network=network), self.assertRaises(ValueError):
                validate_tiled_network(candidate, network, tile_size=2)

    def test_graph_bytes_are_exact_payload_not_total_solver_ram(self):
        candidate = fixture([[3., 2., np.nan], [4., 1., 0.]])
        network = build_tiled_network(candidate)
        result = validate_tiled_network(candidate, network)
        expected_bytes = sum(getattr(network, name).nbytes for name in result["graph_array_nbytes"])
        self.assertEqual(result["graph_arrays_nbytes"], expected_bytes)
        self.assertTrue(result["global_graph_state"])
        self.assertFalse(result["disk_streamed_full_state"])
        self.assertFalse(result["natural_outlet_verified"])

    def test_real_candidate_small_window_preserves_masks_without_heavy_routing(self):
        path = Path(__file__).resolve().parents[1] / "verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz"
        if not path.exists():
            self.skipTest("local real DEM candidate not available")
        candidate = load_dem_candidate(path, verify_source=False)
        reader = CandidateTileReader(candidate, tile_size=256)
        window = reader.read_window(250, 263, 250, 269)
        for name in ("height_m", "valid_mask"):
            np.testing.assert_array_equal(window[name], candidate["arrays"][name][250:263, 250:269])
            self.assertFalse(window[name].flags.writeable)
        local = fixture(window["height_m"].copy())
        network = build_tiled_network(local, tile_size=7)
        self.assert_same(network, build_real_dem_network(local["arrays"]["height_m"], local["arrays"]["valid_mask"]))
        self.assertTrue(validate_tiled_network(local, network, tile_size=7)["verified"])


if __name__ == "__main__":
    unittest.main()
