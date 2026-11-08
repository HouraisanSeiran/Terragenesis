import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import route_graph as route_graph
from terrain_pipeline.drainage import route_disk as route_disk
from terrain_pipeline.drainage import solve_disk_region as solve_disk_region
from terrain_pipeline.world_water_formation import form_water_and_rivers


class DiskRoutingTest(unittest.TestCase):
    def test_matches_reference_on_flat_and_depression(self):
        bed = np.full((19, 23), 10., np.float64)
        bed[5:15, 7:17] = 2.
        bed[8:12, 10:14] = 0.
        outlets = np.zeros(bed.shape, bool)
        outlets[[0, -1], :] = True
        outlets[:, [0, -1]] = True
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.save(root / "height.npy", bed)
            np.save(root / "outlets.npy", outlets)
            result = route_disk(root / "height.npy", root / "outlets.npy", root / "work", local_q_m3_s=1.)
            mesh = build_mesh(bed.shape)
            expected = route_graph(bed, outlets, mesh)
            np.testing.assert_array_equal(result["filled"].reshape(bed.shape), expected.filled)
            np.testing.assert_array_equal(result["order"], expected.order)
            np.testing.assert_array_equal(result["receiver"], expected.receiver)
            receiver = result["receiver"]
            live = receiver >= 0
            self.assertTrue(np.all(result["rank"][receiver[live]] < result["rank"][live]))
            for node in np.flatnonzero(live):
                self.assertIn(receiver[node], mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]])
            self.assertTrue(np.all(result["filled"] >= bed.ravel()))
            self.assertTrue(np.all(result["basin_label"][result["filled"] <= bed.ravel()] == -1))
            self.assertAlmostEqual(result["flow"][outlets.ravel()].sum(), bed.size)
            for array in result.values():
                array._mmap.close()

    def test_finite_region_lake_and_conservation(self):
        z, x = np.indices((41, 41))
        distance = np.hypot(x - 20, z - 20)
        bed = np.zeros((41, 41), np.float64)
        mask = distance <= 7.
        bed[mask] = -5. + distance[mask] * 2.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.save(root / "height.npy", bed)
            np.save(root / "ocean.npy", np.zeros(bed.shape, bool))
            result = solve_disk_region(root / "height.npy", root / "ocean.npy", root / "product",
                origin_native_xz=[0, 0], runoff_m_per_year=1., duration_seconds=86400.,
                channel_threshold_m3_s=1e-6, min_lake_area_m2=1000.)
            self.assertTrue(any(b["complete"] and b["stored_m3"] > 0. for b in result["metadata"]["basins"]))

    def test_two_lakes_transfer_on_joint_terrain(self):
        z, x = np.indices((81, 101))
        bed = 30. - x * .05 + np.abs(z - 40) * .12
        for cx, depth in ((35, 8.), (63, 12.)):
            bed -= depth * np.maximum(0., 1. - np.hypot(x - cx, z - 40) / 7.)
        ocean = np.zeros(bed.shape, bool)
        ocean[:10, :] = ocean[-10:, :] = True
        ocean[:, :10] = ocean[:, -10:] = True
        bed[ocean] = 0.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.save(root / "height.npy", bed)
            np.save(root / "ocean.npy", ocean)
            result = solve_disk_region(root / "height.npy", root / "ocean.npy", root / "product",
                origin_native_xz=[0, 0], runoff_m_per_year=10000., duration_seconds=86400.,
                channel_threshold_m3_s=1e-6, min_lake_area_m2=1000.)
            self.assertTrue(any(b["downstream"] is not None and b["outflow_m3"] for b in result["metadata"]["basins"]))
            self.assertTrue(any(link["target_label"] is not None and link["volume_m3"] for link in result["metadata"]["basin_transfer_links"]))
            with np.load(root / "product" / result["network"]["file"]) as graph:
                self.assertTrue(np.all(graph["spill_volume_m3"] > 0.))
                for link in result["metadata"]["basin_transfer_links"]:
                    if link["volume_m3"] is None or link["volume_m3"] <= 0.:
                        continue
                    selected = ((graph["spill_source_node"] == link["lake_exit_source_node"])
                                & (graph["spill_target_node"] == link["path_flat"][0]))
                    self.assertTrue(selected.any())
                    np.testing.assert_allclose(graph["spill_volume_m3"][selected], link["volume_m3"])
                targets = graph["reach_target"]
                self.assertTrue(np.any(graph["node_terminal_kind"][targets] == 4))
            self.assertAlmostEqual(result["metadata"]["water_ledger"]["residual_m3"], 0., places=5)
            reference = form_water_and_rivers(bed, ocean, [0, 0], 20261020, {"fixture": "synthetic"},
                runoff_m_per_year=10000., duration_seconds=86400., channel_threshold_m3_s=1e-6,
                min_lake_area_m2=1000.)
            for name in ("lake_mask", "pending_basin_mask", "known_q_m3_s", "final_bed_m",
                         "channel_mask", "channel_width_m", "design_incision_depth_m", "representative_q_m3_s"):
                actual = np.load(root / "product" / result["fields"][name])
                np.testing.assert_allclose(actual, reference["arrays"][name], atol=1e-8)

    def test_failure_closes_disk_mappings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.save(root / "height.npy", np.ones((8, 8)))
            np.save(root / "ocean.npy", np.zeros((8, 8), bool))
            with patch('terrain_pipeline.drainage.certify_raw_catchments', side_effect=ValueError("failure")):
                with self.assertRaisesRegex(ValueError, "failure"):
                    solve_disk_region(root / "height.npy", root / "ocean.npy", root / "product",
                        origin_native_xz=[0, 0], runoff_m_per_year=1., duration_seconds=1.,
                        channel_threshold_m3_s=1e-6)

    def test_basin_larger_than_in_memory_lake_limit(self):
        bed = np.full((300, 300), 10., np.float64)
        z, x = np.indices((270, 270))
        bed[15:285, 15:285] = np.hypot(x - 134, z - 134) / 40.
        ocean = np.zeros(bed.shape, bool)
        ocean[:10, :] = ocean[-10:, :] = True
        ocean[:, :10] = ocean[:, -10:] = True
        bed[ocean] = 0.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.save(root / "height.npy", bed)
            np.save(root / "ocean.npy", ocean)
            result = solve_disk_region(root / "height.npy", root / "ocean.npy", root / "product",
                origin_native_xz=[0, 0], runoff_m_per_year=1., duration_seconds=86400.,
                channel_threshold_m3_s=1e-6, min_lake_area_m2=1000.)
            basin = result["metadata"]["basins"][0]
            self.assertGreater(basin["capacity_m3"], 0.)
            self.assertTrue(basin["complete"])
            self.assertGreater(basin["stored_m3"], 0.)
            labels = np.load(root / "product" / result["fields"]["basin_label"])
            self.assertGreater(np.count_nonzero(labels == basin["label"]), 65536)
            surface = np.load(root / "product" / result["fields"]["water_surface_m"])
            final_bed = np.load(root / "product" / result["fields"]["final_bed_m"])
            volume = np.where(np.isfinite(surface) & ~ocean, np.maximum(surface - final_bed, 0.), 0.).sum() * 900.
            self.assertAlmostEqual(volume, basin["stored_m3"], delta=1e-6)
            self.assertAlmostEqual(result["metadata"]["water_ledger"]["residual_m3"], 0., delta=1e-6)


if __name__ == "__main__":
    unittest.main()
