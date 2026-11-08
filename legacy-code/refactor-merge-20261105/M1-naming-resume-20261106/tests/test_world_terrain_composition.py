"""Fixed-source macro and native terrain composition contracts."""
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.td_source import compose_source, crop_composition, make_ocean_plan, sample_ocean_mask
from terrain_pipeline.world_water_layout import LayoutSpec, layout_field


class WorldTerrainCompositionTests(unittest.TestCase):
    def setUp(self):
        self.spec = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                               frame_side_m=12_288_000)
        z, x = np.indices((80, 90), dtype=np.float64)
        self.source = x * 0.5 + z * 0.3 + 12 * np.sin(x / 3)
        self.record = {"sha256": "a" * 64, "world_seed": 20261020}

    def test_crops_share_fixed_source_residual_and_preserve_td(self):
        original = self.source.copy()
        product = compose_source(self.spec, self.source, (2000, 3000),
                                 source_record=self.record, sigma_cells=3)
        first = crop_composition(product, (2015, 3014), (30, 35))
        second = crop_composition(product, (2020, 3018), (20, 25))
        np.testing.assert_array_equal(first["composed_elevation_m"][4:24, 5:30],
                                      second["composed_elevation_m"])
        np.testing.assert_array_equal(product["td_elevation_m"], original)
        np.testing.assert_array_equal(self.source, original)
        self.assertIsNone(product["ocean_mask"])
        self.assertIsNone(product["metadata"]["sea_level_m"])
        self.assertEqual(product["metadata"]["lake_status"], "not_modelled")
        with self.assertRaises(ValueError):
            crop_composition(product, (2000, 3000), (10, 10))

    def test_seed_and_lake_mask_are_rejected(self):
        with self.assertRaises(ValueError):
            compose_source(self.spec, self.source, (0, 0),
                           source_record={**self.record, "world_seed": 1})
        with self.assertRaises(ValueError):
            compose_source(self.spec, self.source, (0, 0), source_record=self.record,
                           ocean_mask=np.zeros(self.source.shape, dtype=bool))

    def test_ocean_mask_is_explicit_and_sea_side_stays_below_datum(self):
        spec = LayoutSpec("archipelago", .8, mode="finite", frame_origin_m=(0, 0),
                          frame_side_m=12_288_000)
        z, x = np.indices(self.source.shape)
        x = (x + 2000) * 30.0
        z = (z + 3000) * 30.0
        mask = layout_field(spec, x, z) < 0
        product = compose_source(spec, self.source, (2000, 3000), source_record=self.record,
                                 ocean_mask=mask, sigma_cells=3)
        self.assertTrue(np.all(product["composed_elevation_m"][mask] <= 0))
        with self.assertRaises(ValueError):
            compose_source(spec, self.source, (2000, 3000), source_record=self.record)
        self.assertEqual(product["metadata"]["ocean_classification"], "externally_supplied")

    def test_source_content_and_mask_are_part_of_identity(self):
        first = compose_source(self.spec, self.source, (0, 0), source_record=self.record)
        changed = self.source.copy()
        changed[40, 40] += 1
        second = compose_source(self.spec, changed, (0, 0), source_record=self.record)
        self.assertNotEqual(first["metadata"]["identity"], second["metadata"]["identity"])


class OceanPlanTests(unittest.TestCase):
    def test_off_grid_shore_uses_exact_field_not_coarse_cell_edge(self):
        spec = LayoutSpec("earth", .62, mode="finite", frame_origin_m=(0, 0),
                          frame_side_m=800_000)

        def field(_spec, x, z):
            x, z = np.broadcast_arrays(x, z)
            return x - 150_000.0

        with patch('terrain_pipeline.td_source.layout_field', side_effect=field):
            plan = make_ocean_plan(spec, pixels=8)
            result = sample_ocean_mask(plan, spec,
                                       np.array([99_999., 100_001., 125_000., 149_999., 150_001.]),
                                       np.full(5, 350_000.))
        np.testing.assert_array_equal(result, [True, True, True, True, False])
        self.assertIn("nearest classified water", plan["metadata"]["ownership"])

    def test_global_components_and_crop_consistency(self):
        spec = LayoutSpec("earth", .62, mode="finite", frame_origin_m=(0, 0),
                          frame_side_m=800_000)

        def field(_spec, x, z):
            x, z = np.broadcast_arrays(x, z)
            large = (x < 300_000) & (z < 500_000)
            small = (x >= 600_000) & (z >= 600_000)
            return np.where(large | small, -1.0, 1.0)

        with patch('terrain_pipeline.td_source.layout_field', side_effect=field):
            plan = make_ocean_plan(spec, pixels=8, min_ocean_area_fraction=.1)
            x, z = np.meshgrid((np.arange(8) + .5) * 100_000,
                               (np.arange(8) + .5) * 100_000)
            whole = sample_ocean_mask(plan, spec, x, z)
            part = sample_ocean_mask(plan, spec, x[3:, 2:], z[3:, 2:])
        np.testing.assert_array_equal(whole[3:, 2:], part)
        self.assertTrue(whole[0, 0])
        self.assertFalse(whole[7, 7])
        self.assertEqual(plan["metadata"]["water_components"], 2)
        self.assertEqual(plan["metadata"]["ocean_components"], 1)

    def test_lakes_reject_ocean_plan(self):
        spec = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                          frame_side_m=12_288_000)
        with self.assertRaises(ValueError):
            make_ocean_plan(spec)


if __name__ == "__main__":
    unittest.main()
