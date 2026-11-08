import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.world_water_formation import form_water_and_rivers
from terrain_pipeline.drainage import certify_raw_catchments as certify_raw_catchments
from terrain_pipeline.drainage import _propagate_unknown as _propagate_unknown
from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry


def form(bed, ocean, runoff=1., duration=86400.):
    return form_water_and_rivers(bed, ocean, [-3, 7], 20261020, {"fixture": "synthetic"},
        runoff_m_per_year=runoff, duration_seconds=duration, channel_threshold_m3_s=1e-6,
        min_lake_area_m2=1000.)


class WorldWaterFormationTest(unittest.TestCase):
    def test_all_ocean_and_zero_runoff(self):
        bed = np.full((8, 8), -4.)
        product = form(bed, np.ones(bed.shape, bool), runoff=0.)
        a = product["arrays"]
        np.testing.assert_array_equal(a["water_surface_m"], np.zeros(bed.shape))
        np.testing.assert_array_equal(a["final_bed_m"], bed)
        self.assertFalse(a["channel_mask"].any())
        self.assertEqual(a["known_q_m3_s"].sum(), 0.)
        land = form(bed, np.zeros(bed.shape, bool), runoff=0.)["arrays"]
        self.assertEqual(land["known_q_m3_s"].sum(), 0.)
        self.assertFalse(land["channel_mask"].any())

    def test_two_basins_keep_bed_and_inventory_account(self):
        z, x = np.indices((51, 51))
        bed = np.zeros((51, 51))
        for cx, cz, bottom in ((15, 15, -3.), (35, 35, -7.)):
            distance = np.hypot(x - cx, z - cz)
            basin = distance <= 6.
            bed[basin] = bottom + distance[basin] * 2.
        original = bed.copy()
        product = form(bed, np.zeros(bed.shape, bool))
        a = product["arrays"]
        np.testing.assert_array_equal(bed, original)
        np.testing.assert_array_equal(a["bed_before_m"], original)
        self.assertGreaterEqual(len(product["metadata"]["basins"]), 2)
        protected = a["lake_support_mask"] | a["pending_basin_mask"]
        np.testing.assert_array_equal(a["final_bed_m"][protected], bed[protected])
        lakes = [basin for basin in product["metadata"]["basins"] if basin["status"] == "lake"]
        self.assertEqual(len(lakes), 2)
        self.assertNotEqual(lakes[0]["water_surface_m"], lakes[1]["water_surface_m"])
        for basin in lakes:
            self.assertAlmostEqual(basin["inflow_m3"], basin["stored_m3"] + basin["outflow_m3"] + basin["residual_m3"])
            row, col = basin["seed_rc"]
            dist = np.hypot(x - col, z - row)
            volume = np.maximum(basin["water_surface_m"] - bed[dist <= 6.], 0.).sum() * 900.
            self.assertAlmostEqual(volume, basin["stored_m3"], places=7)
        np.testing.assert_array_equal(a["final_bed_m"][a["protected_shore_mask"]], bed[a["protected_shore_mask"]])

        dry = form(bed, np.zeros(bed.shape, bool), runoff=0.)
        self.assertTrue(all(basin["status"] == "dry" for basin in dry["metadata"]["basins"]))
        self.assertFalse(dry["arrays"]["pending_basin_mask"].any())

    def test_unknown_boundary_and_ocean_outflow(self):
        bed = np.tile(np.arange(11, -1, -1, dtype=float), (12, 1))
        ocean = np.zeros(bed.shape, bool)
        ocean[:, -1] = True
        a = form(bed, ocean)["arrays"]
        self.assertTrue((a["terminal_kind"] == "open_outflow").any())
        self.assertTrue(a["upstream_unknown_mask"][:, 0].all())
        self.assertFalse(a["complete_mask"][5, -2])
        self.assertTrue(np.isnan(a["representative_q_m3_s"][5, -2]))
        np.testing.assert_array_equal(a["final_bed_m"][ocean], bed[ocean])
        with self.assertRaisesRegex(ValueError, "ocean bed"):
            form(bed + 1., ocean)

    def test_pending_upstream_basin_makes_downstream_basin_pending(self):
        z, x = np.indices((81, 101))
        bed = 30. - x * .05 + np.abs(z - 40) * .12
        for cx, depth in ((35, 8.), (63, 12.)):
            bed -= depth * np.maximum(0., 1. - np.hypot(x - cx, z - 40) / 7.)
        ocean = np.zeros(bed.shape, bool)
        ocean[:10, :] = ocean[-10:, :] = True
        ocean[:, :10] = ocean[:, -10:] = True
        bed[ocean] = 0.
        baseline = form(bed, ocean, runoff=10000.)
        upstream = next(link["source_label"] for link in baseline["metadata"]["basin_transfer_links"]
                        if link["target_label"] is not None)
        downstream = next(link["target_label"] for link in baseline["metadata"]["basin_transfer_links"]
                          if link["source_label"] == upstream)

        def unknown_catchment(*args, **kwargs):
            result = certify_raw_catchments(*args, **kwargs)
            result[upstream]["unknown_cells"] += 1
            return result

        with patch('terrain_pipeline.drainage.certify_raw_catchments', side_effect=unknown_catchment):
            product = form(bed, ocean, runoff=10000.)
        basins = {basin["label"]: basin for basin in product["metadata"]["basins"]}
        for label in (upstream, downstream):
            self.assertEqual(basins[label]["status"], "pending")
            self.assertIsNone(basins[label]["stored_m3"])
            self.assertFalse(product["arrays"]["lake_mask"][product["arrays"]["basin_label"] == label].any())
        self.assertAlmostEqual(product["metadata"]["water_ledger"]["residual_m3"], 0., places=5)

    def test_sea_level_limits_actual_cut_only_when_ocean_exists(self):
        bed = np.full((10, 10), 1.)
        bed[4, 4] = .1
        bed[5, 5] = -.2
        bed[0, 0] = -1.
        ocean = np.zeros(bed.shape, bool)
        ocean[0, 0] = True

        def geometry_with_cut(*args, **kwargs):
            result = build_irregular_channel_geometry(*args, **kwargs)
            result["arrays"]["cut_depth_m"][4, 4] = .3
            result["arrays"]["cut_depth_m"][5, 5] = .4
            result["arrays"]["channel_depth_m"][4, 4] = .3
            return result

        with patch("terrain_pipeline.world_irregular_channels.build_irregular_channel_geometry", side_effect=geometry_with_cut):
            coastal = form(bed, ocean)
            inland = form(bed, np.zeros(bed.shape, bool))
        a = coastal["arrays"]
        self.assertAlmostEqual(a["final_bed_m"][4, 4], 0.)
        self.assertAlmostEqual(a["cut_depth_m"][4, 4], .1)
        self.assertAlmostEqual(a["design_incision_depth_m"][4, 4], .3)
        self.assertAlmostEqual(a["final_bed_m"][5, 5], -.6)
        self.assertAlmostEqual(inland["arrays"]["final_bed_m"][4, 4], -.2)
        policy = coastal["metadata"]["geometry"]["sea_level_cut_limit"]
        self.assertEqual(policy["limited_cells"], 1)
        self.assertAlmostEqual(policy["avoided_cut_bulk_m3"], .2 * 900.)
        budget = coastal["metadata"]["geometry"]["material_budget"]
        self.assertAlmostEqual(budget["removed_terrain_bulk_m3"], a["cut_depth_m"].sum() * 900.)

    def test_real_basin_spill_conserves_finite_volume(self):
        z, x = np.indices((41, 41))
        distance = np.hypot(x - 20, z - 20)
        bed = np.zeros((41, 41))
        mask = distance <= 7.
        bed[mask] = -5. + distance[mask] * 2.
        product = form(bed, np.zeros(bed.shape, bool), runoff=10000., duration=86400.)
        lakes = [item for item in product["metadata"]["basins"] if item["status"] == "lake"]
        self.assertEqual(len(lakes), 1)
        self.assertGreater(lakes[0]["outflow_m3"], 0.)
        links = product["metadata"]["basin_transfer_links"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["volume_m3"], lakes[0]["outflow_m3"])
        self.assertAlmostEqual(product["metadata"]["water_ledger"]["residual_m3"], 0., places=5)

    def test_real_two_basin_transfer(self):
        z, x = np.indices((81, 101))
        bed = 30. - x * .05 + np.abs(z - 40) * .12
        for cx, depth in ((35, 8.), (63, 12.)):
            bed -= depth * np.maximum(0., 1. - np.hypot(x - cx, z - 40) / 7.)
        ocean = np.zeros(bed.shape, bool)
        ocean[:10, :] = ocean[-10:, :] = True
        ocean[:, :10] = ocean[:, -10:] = True
        bed[ocean] = 0.
        product = form(bed, ocean, runoff=10000.)
        links = [link for link in product["metadata"]["basin_transfer_links"]
                 if link["target_label"] is not None and link["volume_m3"] is not None and link["volume_m3"] > 0.]
        self.assertTrue(links)
        self.assertEqual(len([b for b in product["metadata"]["basins"] if b["status"] == "lake"]), 2)
        self.assertEqual(product["arrays"]["spill_edge_volume_m3"].ravel()[links[0]["path_flat"][-1]], 0.)
        self.assertAlmostEqual(product["metadata"]["water_ledger"]["residual_m3"], 0., places=5)

    def test_new_pending_basin_propagates_until_stable(self):
        z, x = np.indices((61, 61))
        bed = np.zeros((61, 61))
        for cx, cz in ((15, 15), (30, 30), (45, 45)):
            distance = np.hypot(x - cx, z - cz)
            mask = distance <= 5.
            bed[mask] = -5. + distance[mask] * 2.
        calls = []

        def staged_unknown(order, receiver, unknown):
            _propagate_unknown(order, receiver, unknown)
            calls.append(1)
            for row, col in ((15, 15), (30, 30), (45, 45))[:min(len(calls), 3)]:
                unknown[row * 61 + col] = 1

        with patch('terrain_pipeline.drainage._propagate_unknown', side_effect=staged_unknown):
            product = form(bed, np.zeros(bed.shape, bool))
        self.assertGreaterEqual(len(calls), 4)
        self.assertTrue(product["arrays"]["pending_basin_mask"][15, 15])
        self.assertTrue(product["arrays"]["pending_basin_mask"][30, 30])
        self.assertTrue(product["arrays"]["pending_basin_mask"][45, 45])


if __name__ == "__main__":
    unittest.main()
