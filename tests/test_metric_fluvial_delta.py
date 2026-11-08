import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import (
    FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval, simulate_fluvial_delta,
)
from tools.verify_fluvial_delta import audit_archive, growth_metrics, save_result


class FluvialDeltaTests(unittest.TestCase):
    def reentrainment_fixture(self, porosity=.25, max_depth=.2):
        bed = np.array([[.1, -.5, -.5, -.5]], dtype=np.float64)
        terrain = TerrainGrid(bed, np.ones(bed.shape, bool), 0., 0., 2., 3.,
                              "diagnostic_dem_proxy", "cover-fixture", "c" * 64)
        exports = np.array([[False, False, False, True]])
        boundary = FluvialDeltaBoundary(bed < 0., exports, 0., 10., "cover-sea")
        config = FluvialDeltaConfig(porosity=porosity, capacity_solid_per_water=.1,
                                    marine_capacity_decay_per_m=0., max_deposit_depth_per_interval_m=2.,
                                    max_reentrainment_depth_per_interval_m=max_depth)
        return terrain, boundary, config

    def test_clear_water_reentrains_cover_and_exports_it_with_cellwise_ledgers(self):
        terrain, boundary, config = self.reentrainment_fixture()
        forcing = [FluvialDeltaInterval((0, 0), 10., 10.), FluvialDeltaInterval((0, 0), 100., 0.)]
        original = terrain.elevation_m.copy()
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        repeated = simulate_fluvial_delta(terrain, boundary, forcing, config)
        for name in ("final_bed_m", "deposited_solid_m3", "reentrained_solid_m3", "stored_solid_m3"):
            np.testing.assert_array_equal(result[name], repeated[name])
        self.assertEqual(result["metadata"], repeated["metadata"])
        self.assertEqual(result["solid_ledger"], repeated["solid_ledger"])
        first, second = result["intervals"]
        self.assertAlmostEqual(first["deposited_solid_m3"].sum(), 9.)
        self.assertAlmostEqual(second["reentrained_solid_m3"].sum(), .9)
        self.assertAlmostEqual(second["solid_ledger"]["ocean_export_solid_m3"], .9)
        self.assertLess(result["final_bed_m"][0, 0], original[0, 0] + 2.)
        previous = np.zeros(original.shape)
        for record in result["intervals"]:
            np.testing.assert_allclose(previous + record["deposited_solid_m3"] - record["reentrained_solid_m3"],
                                       record["stored_solid_m3"])
            self.assertTrue(np.all(record["reentrained_solid_m3"] <= previous))
            self.assertFalse(np.any((record["deposited_solid_m3"] > 0.) & (record["reentrained_solid_m3"] > 0.)))
            outgoing = np.zeros(original.shape)
            for edge in record["flow_edges"]:
                outgoing[edge["from_cell"]] += edge["sediment_solid_m3"]
            outgoing[boundary.ocean_export_mask] = record["sediment_throughput_solid_m3"][boundary.ocean_export_mask]
            np.testing.assert_allclose(record["sediment_throughput_solid_m3"] + record["reentrained_solid_m3"],
                                       outgoing + record["deposited_solid_m3"], atol=1e-14)
            self.assertAlmostEqual(record["solid_ledger"]["residual_solid_m3"], 0.)
            previous = record["stored_solid_m3"]
        np.testing.assert_allclose(result["deposited_solid_m3"] - result["reentrained_solid_m3"], result["stored_solid_m3"])
        np.testing.assert_allclose(result["height_delta_m"], result["stored_solid_m3"] / (6. * .75))
        np.testing.assert_array_equal(terrain.elevation_m, original)
        self.assertAlmostEqual(result["solid_ledger"]["residual_solid_m3"], 0.)

    def test_reentrainment_never_cuts_original_bed_or_exceeds_inventory(self):
        terrain, boundary, config = self.reentrainment_fixture(max_depth=100.)
        clear = FluvialDeltaInterval((0, 0), 1000., 0.)
        empty = simulate_fluvial_delta(terrain, boundary, [clear], config)
        np.testing.assert_array_equal(empty["final_bed_m"], terrain.elevation_m)
        self.assertEqual(empty["reentrained_solid_m3"].sum(), 0.)
        result = simulate_fluvial_delta(terrain, boundary,
                                        [FluvialDeltaInterval((0, 0), 10., 10.), clear, clear], config)
        self.assertAlmostEqual(result["reentrained_solid_m3"].sum(), 9.)
        np.testing.assert_array_equal(result["final_bed_m"], terrain.elevation_m)
        self.assertEqual(result["intervals"][-1]["reentrained_solid_m3"].sum(), 0.)

    def test_porosity_converts_reentrainment_depth_and_net_inventory(self):
        for porosity in (0., .5, .8):
            with self.subTest(porosity=porosity):
                terrain, boundary, config = self.reentrainment_fixture(porosity)
                first_forcing = FluvialDeltaInterval((0, 0), 10., 2.)
                deposited = simulate_fluvial_delta(terrain, boundary, [first_forcing], config)
                result = simulate_fluvial_delta(terrain, boundary,
                                                [first_forcing, FluvialDeltaInterval((0, 0), 100., 0.)], config)
                expected_solid = min(1., .2 * 6. * (1. - porosity))
                self.assertAlmostEqual(result["reentrained_solid_m3"].sum(), expected_solid)
                self.assertAlmostEqual(deposited["final_bed_m"][0, 0] - result["final_bed_m"][0, 0],
                                       expected_solid / (6. * (1. - porosity)))
                self.assertAlmostEqual(result["solid_ledger"]["stored_bulk_m3"],
                                       result["stored_solid_m3"].sum() / (1. - porosity))

    def test_zero_water_preserves_cover_and_escrows_new_solids(self):
        terrain, boundary, config = self.reentrainment_fixture()
        result = simulate_fluvial_delta(terrain, boundary,
                                        [FluvialDeltaInterval((0, 0), 10., 10.),
                                         FluvialDeltaInterval((0, 0), 0., 2.)], config)
        first, second = result["intervals"]
        np.testing.assert_array_equal(first["stored_solid_m3"], second["stored_solid_m3"])
        self.assertEqual(second["reentrained_solid_m3"].sum(), 0.)
        self.assertEqual(second["solid_ledger"]["unresolved_solid_m3"], 2.)
        self.assertAlmostEqual(second["solid_ledger"]["residual_solid_m3"], 0.)

    def test_disconnected_clear_water_cannot_reentrain_other_component(self):
        terrain, boundary, config = self.reentrainment_fixture()
        bed = np.tile(terrain.elevation_m, (3, 1))
        valid = np.ones(bed.shape, bool)
        valid[1, :] = False
        terrain = replace(terrain, elevation_m=bed, valid_mask=valid)
        ocean = (bed < 0.) & valid
        exports = np.zeros(bed.shape, bool)
        exports[0, -1] = True
        boundary = FluvialDeltaBoundary(ocean, exports, 0., 10., "isolated-sea")
        result = simulate_fluvial_delta(terrain, boundary,
                                        [FluvialDeltaInterval((0, 0), 10., 10.),
                                         FluvialDeltaInterval((2, 0), 100., 0.)], config)
        first, second = result["intervals"]
        np.testing.assert_array_equal(first["stored_solid_m3"], second["stored_solid_m3"])
        self.assertEqual(second["water_ledger"]["retained_m3"], 100.)
        self.assertEqual(second["reentrained_solid_m3"].sum(), 0.)

    def test_reentrainment_config_rejects_invalid_or_overflowing_depth(self):
        for value in (-1., float("inf"), float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FluvialDeltaConfig(max_reentrainment_depth_per_interval_m=value)
        terrain, boundary, config = self.reentrainment_fixture(max_depth=1e308)
        with self.assertRaises(ValueError):
            simulate_fluvial_delta(terrain, boundary, [FluvialDeltaInterval((0, 0), 10., 0.)], config)

    def test_default_and_explicit_disabled_reentrainment_preserve_v2(self):
        terrain, boundary, forcing, config = self.fixture()
        default = simulate_fluvial_delta(terrain, boundary, forcing[:2], config)
        disabled = simulate_fluvial_delta(terrain, boundary, forcing[:2],
                                          replace(config, max_reentrainment_depth_per_interval_m=0.))
        self.assertEqual(default["metadata"], disabled["metadata"])
        self.assertEqual(default["metadata"]["algorithm_version"], "fluvial-delta-volume-routing-v2")
        self.assertNotIn("max_reentrainment_depth_per_interval_m", default["metadata"]["config"])
        for name in ("final_bed_m", "height_delta_m", "deposited_solid_m3", "stored_solid_m3"):
            np.testing.assert_array_equal(default[name], disabled[name])
        np.testing.assert_array_equal(default["stored_solid_m3"], default["deposited_solid_m3"])
        self.assertEqual(default["reentrained_solid_m3"].sum(), 0.)

    def fixture(self):
        bed = np.full((9, 13), .1, np.float64)
        bed[:, 4:] = -.5
        ocean = bed < 0.
        export = np.zeros(bed.shape, bool)
        export[:, -1] = True
        terrain = TerrainGrid(bed, np.ones(bed.shape, bool), 0., 0., 1., 1.,
                              "diagnostic_dem_proxy", "explicit-fixture", "a" * 64)
        boundary = FluvialDeltaBoundary(ocean, export, 0., 2., "declared-fixture-sea")
        forcing = tuple(FluvialDeltaInterval((4, 0), 100., 1.5) for _ in range(32))
        config = FluvialDeltaConfig()
        return terrain, boundary, forcing, config

    def test_marine_bar_changes_next_interval_paths_and_conserves(self):
        terrain, boundary, forcing, config = self.fixture()
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        first = result["intervals"][0]
        self.assertGreater(first["deposited_solid_m3"][:, 4:].sum(), 0.)
        self.assertTrue(np.any(boundary.initial_ocean_mask & (result["final_bed_m"] > boundary.sea_level_m)))
        self.assertFalse(np.array_equal(first["water_throughput_m3"], result["intervals"][-1]["water_throughput_m3"]))
        ledger = result["solid_ledger"]
        self.assertAlmostEqual(48., ledger["deposited_solid_m3"] + ledger["ocean_export_solid_m3"] + ledger["unresolved_solid_m3"])
        np.testing.assert_allclose(result["final_bed_m"] - terrain.elevation_m,
                                   result["deposited_solid_m3"] / (1. - config.porosity))

    def test_disconnected_inlet_retains_water_and_unresolved_sediment(self):
        terrain, boundary, forcing, config = self.fixture()
        bed = terrain.elevation_m.copy()
        bed[:, 2] = 3.
        blocked = TerrainGrid(bed, terrain.valid_mask, 0., 0., 1., 1., "diagnostic_dem_proxy", "blocked", "b" * 64)
        result = simulate_fluvial_delta(blocked, boundary, forcing[:1], config)
        self.assertEqual(result["water_ledger"]["retained_m3"], 100.)
        self.assertEqual(result["solid_ledger"]["unresolved_solid_m3"], 1.5)
        self.assertEqual(result["deposited_solid_m3"].sum(), 0.)

    def test_ocean_export_requires_declared_sea_and_perimeter(self):
        terrain, boundary, forcing, config = self.fixture()
        export = boundary.ocean_export_mask.copy()
        export[3, 5] = True
        with self.assertRaises(ValueError):
            simulate_fluvial_delta(terrain, FluvialDeltaBoundary(boundary.initial_ocean_mask, export, 0., 1., "bad"), forcing, config)

    def test_growth_gate_distinguishes_connected_bar_growth_from_inlet_clogging(self):
        terrain, boundary, forcing, config = self.fixture()
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        metrics = growth_metrics(result, boundary, forcing, terrain.cell_area_m2)
        self.assertTrue(metrics["passed"])
        self.assertTrue(metrics["all_intervals_export_supplied_water"])
        self.assertGreater(metrics["significant_split_cell_count_last_interval"], 0)
        self.assertGreater(metrics["new_land_connected_to_initial_land_cell_count"], 0)
        overloaded = tuple(FluvialDeltaInterval((4, 0), 100., 30.) for _ in range(16))
        clogged = simulate_fluvial_delta(terrain, boundary, overloaded, config)
        metrics = growth_metrics(clogged, boundary, overloaded, terrain.cell_area_m2)
        self.assertFalse(metrics["passed"])
        self.assertGreater(metrics["inlet_above_head_interval_count"], 0)
        self.assertGreater(metrics["water_retained_interval_count"], 0)

    def test_archive_cold_audit_rejects_cell_flux_and_bed_tampering(self):
        terrain, boundary, forcing, config = self.fixture()
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delta.npz"
            save_result(path, terrain, boundary, forcing, result, {"path": "fixture", "sha256": "a" * 64}, terrain.elevation_m)
            self.assertTrue(audit_archive(path, verify_source=False)["passed"])
            with np.load(path, allow_pickle=False) as archive:
                saved = {key: archive[key].copy() for key in archive.files}
            for key in ("water", "final_bed_m", "edge_volumes"):
                tampered = {name: value.copy() for name, value in saved.items()}
                tampered[key].flat[0] += 1.
                bad = Path(directory) / (key + ".npz")
                np.savez_compressed(bad, **tampered)
                with self.assertRaises((ValueError, AssertionError)):
                    audit_archive(bad, verify_source=False)

    def test_zero_datum_original_land_is_not_new_marine_land(self):
        terrain, boundary, forcing, config = self.fixture()
        bed = terrain.elevation_m.copy()
        bed[:, :4] = 0.
        terrain = TerrainGrid(bed, terrain.valid_mask, 0., 0., 1., 1., "diagnostic_dem_proxy", "zero-land", "b" * 64)
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        metrics = growth_metrics(result, boundary, forcing, terrain.cell_area_m2)
        actual_marine_emerged = boundary.initial_ocean_mask & (bed < 0.) & (result["final_bed_m"] > 0.)
        self.assertEqual(metrics["new_land_cell_count"], int(actual_marine_emerged.sum()))
        self.assertGreater(metrics["raised_zero_datum_original_land_cell_count"], 0)


if __name__ == "__main__":
    unittest.main()
