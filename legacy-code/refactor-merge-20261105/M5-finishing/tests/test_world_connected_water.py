import unittest

import numpy as np

from terrain_pipeline.surface_hydraulics import form_connected_region, _spill_destinations


def solve(bed, ocean=None, side=8):
    if ocean is None:
        ocean = np.zeros(bed.shape, bool)
    composition = {"composed_elevation_m": bed, "ocean_mask": ocean,
                   "valid_mask": np.ones(bed.shape, bool),
                   "metadata": {"origin_native_xz": [-5, 7], "world_seed": 20261020}}
    return form_connected_region(composition, [-5, 7], runoff_m_per_year=1.,
        duration_seconds=86400., channel_threshold_m3_s=1e-6, tile_side_cells=side,
        min_lake_area_m2=1000.)


class ConnectedRegionTest(unittest.TestCase):
    def test_cross_tile_routing_q_and_unknown(self):
        bed = np.tile(np.arange(23, -1, -1, dtype=float), (24, 1))
        ocean = np.zeros(bed.shape, bool)
        ocean[:, -1] = True
        product = solve(bed, ocean)
        a = product["arrays"]
        r = a["receiver"].ravel()
        q = a["known_q_m3_s"].ravel()
        local = 900. / (365.25 * 86400.)
        sums = np.zeros(q.size)
        live = r >= 0
        np.add.at(sums, r[live], q[live])
        np.testing.assert_allclose(q[~ocean.ravel()], sums[~ocean.ravel()] + local)
        self.assertGreater(product["metadata"]["statistics"]["routing_cross_tile_edges"], 0)
        self.assertFalse(a["complete_mask"][10, -2])
        self.assertTrue(np.isnan(a["representative_q_m3_s"][10, -2]))
        for row, col in np.argwhere(a["receiver"] >= 0):
            target_row, target_col = divmod(int(a["receiver"][row, col]), bed.shape[1])
            self.assertEqual(a["receiver_native_x"][row, col], target_col - 5)
            self.assertEqual(a["receiver_native_z"][row, col], target_row + 7)
        for row, col in np.argwhere(a["spill_receiver"] >= 0):
            target_row, target_col = divmod(int(a["spill_receiver"][row, col]), bed.shape[1])
            self.assertEqual(a["spill_receiver_native_x"][row, col], target_col - 5)
            self.assertEqual(a["spill_receiver_native_z"][row, col], target_row + 7)
        self.assertEqual(product["metadata"]["statistics"]["active_spill_edges"],
                         int(((a["spill_receiver"] >= 0) & (a["spill_edge_volume_m3"] > 0)).sum()))

    def test_spill_chain_destination_is_not_local_lake_terminal(self):
        links = [{"source_label": 1, "target_label": 2, "destination": "lake", "volume_m3": 3.},
                 {"source_label": 2, "target_label": None, "destination": "ocean", "volume_m3": 2.}]
        self.assertEqual(_spill_destinations(links)[0],
                         {"source_label": 1, "labels": [1, 2], "destination": "ocean"})
        links[1]["volume_m3"] = 0.
        self.assertEqual(_spill_destinations(links)[0]["destination"], "retained")

    def test_basin_crosses_tiles_once_and_tile_size_does_not_change_solution(self):
        z, x = np.indices((41, 41))
        distance = np.hypot(x - 20, z - 20)
        bed = np.zeros((41, 41))
        basin = distance <= 7.
        bed[basin] = -5. + distance[basin] * 2.
        first = solve(bed, side=8)
        second = solve(bed, side=13)
        for name in first["arrays"]:
            np.testing.assert_array_equal(first["arrays"][name], second["arrays"][name])
        lakes = [r for r in first["metadata"]["formation"]["basins"] if r["status"] == "lake"]
        self.assertEqual(len(lakes), 1)
        record = lakes[0]
        mask = first["arrays"]["basin_label"] == record["label"]
        self.assertGreater(np.unique((x[mask] - 5) // 8).size, 1)
        volume = np.maximum(record["water_surface_m"] - bed[mask], 0.).sum() * 900.
        self.assertAlmostEqual(volume, record["stored_m3"], places=7)
        rebuilt = np.empty_like(bed)
        slices = [(slice(r, min(r + 8, 41)), slice(c, min(c + 8, 41)))
                  for r in range(0, 41, 8) for c in range(0, 41, 8)]
        for sl in reversed(slices):
            rebuilt[sl] = first["arrays"]["final_bed_m"][sl]
        np.testing.assert_array_equal(rebuilt, first["arrays"]["final_bed_m"])


if __name__ == "__main__":
    unittest.main()
