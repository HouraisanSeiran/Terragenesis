import unittest

import numpy as np

from terrain_pipeline.large_scale_surface_tiles import (
    BoundedTileReader, LargeScaleSpec, SyntheticMountain,
    build_river_network, propagate_windowed, run_benchmark,
)


class LargeScaleSurfaceTileTests(unittest.TestCase):
    def test_shared_edges_are_exact(self):
        spec = LargeScaleSpec(rows=256, cols=256, tile_size=64)
        source = SyntheticMountain(spec)
        reader = BoundedTileReader(source, max_windows=2)
        left_halo = reader.window(0, 0)
        right_halo = reader.window(0, 1)
        bottom_halo = reader.window(1, 0)
        # The right tile's left halo and the left tile's final column refer
        # to the same global column; likewise for the horizontal seam.
        np.testing.assert_array_equal(left_halo[:, -2], right_halo[:, 0])
        np.testing.assert_array_equal(left_halo[-2, :], bottom_halo[0, :])
        self.assertEqual(float(right_halo[0, 0]), float(source.read_window(0, 63, 1, 1)[0, 0]))
        self.assertEqual(float(bottom_halo[0, 0]), float(source.read_window(63, 0, 1, 1)[0, 0]))

    def test_cross_tile_ids_and_outlets(self):
        spec = LargeScaleSpec(rows=256, cols=256, tile_size=64)
        reader = BoundedTileReader(SyntheticMountain(spec), max_windows=2)
        network = build_river_network(spec, reader)
        cross = [int(t) for c, t in enumerate(network.receiver) if t >= 0 and spec.tile_key(c // spec.cols, c % spec.cols) != spec.tile_key(int(t) // spec.cols, int(t) % spec.cols)]
        self.assertTrue(cross)
        self.assertTrue(np.all(network.outlets >= 0))
        self.assertTrue(np.all(network.river_id[network.river_id >= 0] < spec.cell_count))

    def test_windowed_propagation_conserves_water(self):
        spec = LargeScaleSpec(rows=256, cols=256, tile_size=64)
        reader = BoundedTileReader(SyntheticMountain(spec), max_windows=2)
        network = build_river_network(spec, reader)
        result = propagate_windowed(spec, reader, network, steps=2)
        self.assertLess(abs(result.residual_m3), 1e-6)
        self.assertLessEqual(reader.peak_windows, 2)
        self.assertGreater(result.outlet_m3, 0.0)

    def test_1024_benchmark_has_large_cross_tile_network(self):
        report = run_benchmark(LargeScaleSpec(), max_windows=3)
        self.assertEqual(report["cell_count"], 1024 * 1024)
        self.assertGreater(report["cross_tile_edges"], 100)
        self.assertGreater(report["river_cell_count"], 1000)
        self.assertTrue(report["conservation_passed"])
        self.assertEqual(report["peak_windows"], 3)


if __name__ == "__main__":
    unittest.main()
