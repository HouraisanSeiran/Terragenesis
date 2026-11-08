"""Absolute world coordinates and conservative native-to-review sampling."""
import unittest

import numpy as np

from terrain_pipeline.td_source import area_mean_3, compose_native, macro_fields, overlap_comparison, preparation_plan, terrain_identity, tile_requests


class AcceptanceTerrainTests(unittest.TestCase):
    def test_identity_excludes_execution_and_storage_location(self):
        plan = preparation_plan()
        paths = {"raw": {"path": "first.npy", "array_sha256": "abc"}}
        first = terrain_identity(plan, paths, "backend", {"gain": .65})
        paths["raw"]["path"] = "elsewhere.npy"
        plan["runtime_seconds"] = 99
        plan["sampled_peak_rss_bytes"] = 1234
        self.assertEqual(first, terrain_identity(plan, paths, "backend", {"gain": .65}))
        paths["raw"]["array_sha256"] = "changed"
        self.assertNotEqual(first, terrain_identity(plan, paths, "backend", {"gain": .65}))

    def test_overlap_compares_halo_without_mutating_owned_core(self):
        raw = np.arange(100, dtype=np.float32).reshape(10, 10)
        original = raw.copy()
        covered = np.zeros(raw.shape, dtype=bool)
        covered[3:7, 4:8] = True
        tile = raw[2:9, 2:9] + 2
        report = overlap_comparison(raw, covered, tile,
            {"native_x": 12, "native_z": 22, "size": 7}, (10, 20))
        self.assertEqual(report["count"], 16)
        self.assertEqual(report["maximum_absolute_difference_m"], 2)
        np.testing.assert_array_equal(raw, original)

    def test_macro_overlap_independent_of_requested_window(self):
        x = np.arange(110000, 200000, 90)[None, :]
        z = np.arange(-40000, 40000, 90)[:, None]
        whole = macro_fields(x, z)
        crop = macro_fields(x[:, 123:543], z[111:333])
        for name in whole:
            np.testing.assert_array_equal(whole[name][111:333, 123:543], crop[name])

    def test_area_aggregation_preserves_integral_and_cell_centres(self):
        values = np.arange(18 * 12, dtype=np.float32).reshape(18, 12)
        coarse = area_mean_3(values)
        self.assertAlmostEqual(float(values.sum() * 30**2), float(coarse.sum() * 90**2))
        np.testing.assert_array_equal(area_mean_3(np.stack([values, values + 9]))[1], coarse + 9)
        plan = preparation_plan()
        self.assertEqual(plan["origin_xz_m"], [126030, -32010])
        self.assertEqual(plan["shape_native_zx"], [2136, 2136])

    def test_500km_and_64km_share_global_90m_cells(self):
        whole = preparation_plan((-250000, -250000, 250000, 250000))
        sample = preparation_plan()
        self.assertEqual(whole["origin_native_xz"], [-8334, -8334])
        self.assertEqual(whole["origin_xz_m"], [-249990, -249990])
        for plan in (whole, sample):
            self.assertEqual([v % 3 for v in plan["origin_native_xz"]], [0, 0])
            self.assertEqual([v % 90 for v in plan["origin_xz_m"]], [30, 30])
        coarse_offset = np.subtract(sample["origin_xz_m"], whole["origin_xz_m"]) / 90
        np.testing.assert_array_equal(coarse_offset, np.floor(coarse_offset))
        # Query a 12x15-native-cell subset through each plan's virtual full grid.
        # This verifies exactly the cells a 500km aggregation would use without
        # allocating a 16668-square field.
        def aggregate_subset(plan, coarse_x, coarse_z):
            x0, z0 = plan["origin_native_xz"]
            x = (x0 + coarse_x * 3 + np.arange(15))[None, :] * 30
            z = (z0 + coarse_z * 3 + np.arange(12))[:, None] * 30
            return area_mean_3(macro_fields(x, z)["elevation_m"])
        full_x, full_z = coarse_offset.astype(int) + [31, 47]
        np.testing.assert_array_equal(aggregate_subset(whole, full_x, full_z),
                                      aggregate_subset(sample, 31, 47))

    def test_requests_cover_halo_without_exceeding_budget(self):
        plan = preparation_plan()
        coverage = np.zeros(plan["source_shape_zx"], dtype=np.uint8)
        for request in tile_requests(plan["source_shape_zx"], plan["source_origin_native_xz"]):
            self.assertLessEqual(request["size"], 1337)
            r, c = request["row"], request["column"]
            coverage[r:r + request["rows"], c:c + request["columns"]] += 1
        self.assertTrue(np.all(coverage > 0))
        self.assertTrue(np.all(coverage == 1))

    def test_source_support_covers_climate_queries_and_filter(self):
        plan = preparation_plan()
        support = plan["source_support"]
        required = (1.5 * support["climate_orographic_scale_m"]
                    + support["interpolation_support_m"] + support["composition_filter_support_m"])
        self.assertGreaterEqual(plan["halo_native_cells"] * 30, required)
        self.assertEqual(support["inference_tile_halo_native_cells"], 96)

    def test_expanding_window_and_reverse_traversal_preserve_native_samples(self):
        def assemble(shape, origin, reverse=False):
            result = np.empty(shape, dtype=np.float32)
            requests = list(tile_requests(shape, origin))
            for request in reversed(requests) if reverse else requests:
                size = request["size"]
                # Fake model deliberately depends on requested page coordinates.
                x = request["native_x"] + np.arange(size)[None, :]
                z = request["native_z"] + np.arange(size)[:, None]
                tile = x + 2 * z + request["native_x"] * .25
                r, c, tr, tc = (request[k] for k in ("row", "column", "tile_row", "tile_column"))
                nr, nc = request["rows"], request["columns"]
                result[r:r + nr, c:c + nc] = tile[tr:tr + nr, tc:tc + nc]
            return result
        whole = assemble((2400, 2400), (-1200, 4000))
        crop = assemble((1200, 1200), (-900, 4500), reverse=True)
        np.testing.assert_array_equal(whole[500:1700, 300:1500], crop)

    def test_composition_retains_low_frequency_td_and_macro_shore_sign(self):
        plan = preparation_plan((156000, -3000, 174000, 3000))
        shape = plan["source_shape_zx"]
        raw = np.full(shape, 750, dtype=np.float32)
        composed, fields = compose_native(raw, plan)
        shifted, _ = compose_native(raw + 100, plan)
        land = fields["elevation_m"] > 400
        self.assertGreater(np.count_nonzero(land), 0)
        self.assertGreater(float(np.max(shifted[land] - composed[land])), 50)
        np.testing.assert_array_equal(composed < 0, fields["ocean_mask"])

    def test_single_macro_landmass_has_land_to_sea_acceptance_window(self):
        plan = preparation_plan()
        x0, z0, x1, z1 = plan["requested_view_bounds_m"]
        fields = macro_fields(np.linspace(x0, x1, 240)[None], np.linspace(z0, z1, 240)[:, None])
        self.assertGreater(float(fields["elevation_m"].max()), 1000)
        self.assertGreater(float(fields["ocean_mask"].mean()), .1)
        self.assertLess(float(fields["ocean_mask"].mean()), .65)

    def test_composition_valid_interior_matches_expanded_request(self):
        def product(plan):
            ox, oz = plan["source_origin_native_xz"]
            nr, nc = plan["source_shape_zx"]
            x = (ox + np.arange(nc))[None, :] * 30
            z = (oz + np.arange(nr))[:, None] * 30
            raw = macro_fields(x, z)["elevation_m"] + 160 * np.sin(x / 2000) * np.cos(z / 3400)
            return compose_native(raw.astype(np.float32), plan)[0]
        large_plan = preparation_plan((140000, -9000, 152000, 3000))
        small_plan = preparation_plan((143000, -6000, 149000, 0))
        large, small = product(large_plan), product(small_plan)
        dx, dz = np.subtract(small_plan["source_origin_native_xz"], large_plan["source_origin_native_xz"])
        halo = small_plan["halo_native_cells"]
        nr, nc = small_plan["shape_native_zx"]
        np.testing.assert_array_equal(small[halo:halo + nr, halo:halo + nc],
                                      large[dz + halo:dz + halo + nr, dx + halo:dx + halo + nc])


if __name__ == "__main__":
    unittest.main()
