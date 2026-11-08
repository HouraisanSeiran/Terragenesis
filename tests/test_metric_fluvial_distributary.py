from dataclasses import replace
import unittest

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary, FluvialDeltaInterval
from terrain_pipeline.surface_rivers.metric_fluvial_distributary import (
    FluvialDistributaryConfig, prepare_marine_transition, simulate_fluvial_distributary,
)


class DistributaryTests(unittest.TestCase):
    def fixture(self):
        bed = np.full((25, 49), .1, np.float64)
        bed[:, 16:] = -.5
        terrain = TerrainGrid(bed, np.ones(bed.shape, bool), 0., 0., 5., 5.,
                              "diagnostic_dem_proxy", "unincised-flat-mouth", "a" * 64)
        exports = np.zeros(bed.shape, bool)
        exports[:, -1] = True
        boundary = FluvialDeltaBoundary(bed < 0., exports, 0., 2., "declared-mouth")
        config = FluvialDistributaryConfig(branch_landward_distance_m=20., minimum_branch_separation_m=30.,
                                           max_source_eroded_bulk_m3=100000.)
        forcing = [FluvialDeltaInterval((12, 2), 200000., 3000.) for _ in range(8)]
        forcing += [FluvialDeltaInterval((12, 2), 200000., 0.) for _ in range(8)]
        return terrain, boundary, config, forcing

    def test_real_excavation_shared_split_continuity_and_material(self):
        terrain, boundary, config, forcing = self.fixture()
        original = terrain.elevation_m.copy()
        result = simulate_fluvial_distributary(terrain, boundary, forcing, config)
        self.assertGreater(result["source_eroded_bulk_m3"].sum(), 0.)
        self.assertGreater(result["deposited_solid_m3"].sum(), 0.)
        self.assertGreater(result["reentrained_solid_m3"].sum(), 0.)
        self.assertTrue(np.all(result["source_eroded_bulk_m3"] / 25. <= 4.))
        np.testing.assert_allclose(result["final_bed_m"], original - result["source_eroded_bulk_m3"] / 25.
                                   + result["stored_solid_m3"] / (.65 * 25.))
        previous = np.zeros(original.shape)
        for record in result["intervals"]:
            self.assertAlmostEqual(record["water_ledger"]["residual_m3"], 0.)
            self.assertAlmostEqual(record["solid_ledger"]["residual_solid_m3"], 0., places=8)
            np.testing.assert_allclose(previous + record["deposited_solid_m3"] - record["reentrained_solid_m3"],
                                       record["stored_solid_m3"], atol=1e-12)
            outgoing = np.zeros(original.shape)
            incoming = np.zeros(original.shape)
            incoming[forcing[0].inlet_cell] = record["solid_ledger"]["input_solid_m3"]
            for edge in record["flow_edges"]:
                outgoing[edge["from_cell"]] += edge["sediment_solid_m3"]
                incoming[edge["to_cell"]] += edge["sediment_solid_m3"]
                a, b = edge["from_cell"], edge["to_cell"]
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)
            np.testing.assert_allclose(incoming, record["sediment_throughput_solid_m3"], atol=1e-10)
            outgoing[boundary.ocean_export_mask] = incoming[boundary.ocean_export_mask]
            # Export nodes can also entrain explicitly accounted local excavation.
            outgoing[boundary.ocean_export_mask] += (record["source_eroded_solid_m3"] + record["reentrained_solid_m3"]
                                                       - record["unresolved_solid_m3"])[boundary.ocean_export_mask]
            np.testing.assert_allclose(incoming + record["source_eroded_solid_m3"] + record["reentrained_solid_m3"],
                                       outgoing + record["deposited_solid_m3"] + record["unresolved_solid_m3"], atol=1e-10)
            previous = record["stored_solid_m3"]
        self.assertAlmostEqual(result["solid_ledger"]["residual_solid_m3"], 0., places=8)
        for record in result["intervals"][-3:]:
            paths = record["channel_paths"]
            trunk, branches = paths["trunk"], paths["branches"]
            self.assertEqual(branches[0][0], trunk[-1])
            self.assertEqual(branches[1][0], trunk[-1])
            self.assertFalse(set(branches[0][1:]) & set(branches[1][1:]))
            for branch in branches:
                self.assertTrue(boundary.ocean_export_mask[branch[-1]])
                self.assertGreaterEqual(record["water_throughput_m3"][branch[-1]], .05 * forcing[0].water_volume_m3)
                for a, b in zip(branch, branch[1:]):
                    self.assertLessEqual(record["bed_m"][b], record["bed_m"][a] + 1e-10)
        np.testing.assert_array_equal(terrain.elevation_m, original)

    def test_zero_water_never_excavates_and_preserves_initial_cover(self):
        terrain, boundary, config, _ = self.fixture()
        cover = np.ones(terrain.elevation_m.shape)
        result = simulate_fluvial_distributary(terrain, boundary, [FluvialDeltaInterval((12, 2), 0., 3.)],
                                               config, initial_cover_solid_m3=cover)
        self.assertEqual(result["source_eroded_bulk_m3"].sum(), 0.)
        np.testing.assert_array_equal(result["stored_solid_m3"], cover)
        self.assertEqual(result["solid_ledger"]["unresolved_solid_m3"], 3.)
        self.assertAlmostEqual(result["solid_ledger"]["residual_solid_m3"], 0.)

    def test_budget_and_disconnected_branch_reject(self):
        terrain, boundary, config, forcing = self.fixture()
        with self.assertRaisesRegex(ValueError, "budget"):
            simulate_fluvial_distributary(terrain, boundary, forcing[:1], replace(config, max_source_eroded_bulk_m3=1.))
        bed = terrain.elevation_m.copy()
        bed[:, 10] = 3.
        with self.assertRaisesRegex(ValueError, "cannot reach"):
            simulate_fluvial_distributary(replace(terrain, elevation_m=bed), boundary, forcing[:1], config)

    def test_source_fraction_and_determinism(self):
        terrain, boundary, config, forcing = self.fixture()
        config = replace(config, source_solid_fraction=.8)
        first = simulate_fluvial_distributary(terrain, boundary, forcing[:2], config)
        second = simulate_fluvial_distributary(terrain, boundary, forcing[:2], config)
        np.testing.assert_allclose(first["source_eroded_solid_m3"], .8 * first["source_eroded_bulk_m3"])
        for key in ("final_bed_m", "source_eroded_bulk_m3", "stored_solid_m3"):
            np.testing.assert_array_equal(first[key], second[key])

    def test_source_excavation_requires_all_overlying_cover_removed(self):
        terrain, boundary, config, forcing = self.fixture()
        cover = np.full(terrain.elevation_m.shape, .5 * 25. * (1. - config.porosity))
        result = simulate_fluvial_distributary(terrain, boundary, forcing[:4], config,
                                               initial_cover_solid_m3=cover)
        previous = cover
        for record in result["intervals"]:
            worked = record["source_eroded_bulk_m3"] > 0.
            np.testing.assert_allclose((previous - record["reentrained_solid_m3"])[worked], 0., atol=1e-12)
            previous = record["stored_solid_m3"]

    def test_invalid_configuration_and_preparation_cover_reject(self):
        for value in (-1., float("inf"), float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FluvialDistributaryConfig(max_source_cut_depth_per_interval_m=value)
        with self.assertRaises(ValueError):
            FluvialDistributaryConfig(max_source_cut_depth_m=4.01)
        terrain, boundary, config, forcing = self.fixture()
        for cover in (np.full(terrain.elevation_m.shape, -1.), np.full(terrain.elevation_m.shape, np.inf)):
            with self.assertRaises(ValueError):
                simulate_fluvial_distributary(terrain, boundary, forcing[:1], config, initial_cover_solid_m3=cover)

    def test_marine_preparation_is_budgeted_finite_and_reconnects(self):
        terrain, boundary, config, _ = self.fixture()
        bed = terrain.elevation_m.copy()
        bed[:, 16:] = -10.
        terrain = replace(terrain, elevation_m=bed)
        options = dict(radius_m=100., slope_m_per_m=.02, maximum_raise_m=10.,
                       maximum_fill_bulk_m3=1000000., supplied_solid_m3=1000000.)
        prepared = prepare_marine_transition(terrain, boundary, (12, 14), **options)
        self.assertGreater(prepared["initial_cover_solid_m3"].sum(), 0.)
        np.testing.assert_array_equal(prepared["coordinated_bed_m"][:, -1], bed[:, -1])
        np.testing.assert_array_equal(prepared["coordinated_bed_m"][:, :16], bed[:, :16])
        self.assertTrue(np.all(prepared["coordinated_bed_m"][boundary.initial_ocean_mask] < 0.))
        with self.assertRaisesRegex(ValueError, "insufficient"):
            prepare_marine_transition(terrain, boundary, (12, 14), **dict(options, supplied_solid_m3=1.))
        np.testing.assert_array_equal(terrain.elevation_m, bed)


if __name__ == "__main__":
    unittest.main()
