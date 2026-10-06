import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_native_channel_geometry import build_channel_geometry
from terrain_pipeline.td_native_channel_tiles import build_channel_tile, save_channel_tile, split_window_2x2
from tests.test_td_native_channel_geometry import fixture
from tools.audit_td_native_channel_tiles import assemble, sample_reference


class IndependentTileAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hierarchy, page = fixture()
        self.geometry = build_channel_geometry(self.hierarchy, page)
        self.tiles = [build_channel_tile(self.geometry, window=window)
                      for window in split_window_2x2((0, 60, 0, 60))]
        self.records = self.save(self.tiles)

    def save(self, tiles, prefix="tile"):
        records = []
        for index, tile in enumerate(tiles):
            path = Path(self.directory.name) / f"{prefix}-{index}.npz"
            save_channel_tile(path, tile)
            records.append(dict(path=str(path), expected_sha256=file_sha256(path),
                                expected_identity=tile["identity_sha256"]))
        return records

    def test_raw_interpolation_and_independent_channel_samples(self):
        grids, metadata, bounds, shared = assemble(self.records, self.geometry["identity_sha256"])
        checked = sample_reference(self.hierarchy["arrays"], self.hierarchy["metadata"],
                                   self.geometry["arrays"], metadata, bounds, grids)
        self.assertEqual(checked["native_samples"], 61 * 61)
        self.assertGreater(shared, 0)
        self.assertLess(checked["cut_max_error_m"], 2e-12)
        reverse = assemble(list(reversed(self.records)), self.geometry["identity_sha256"])[0]
        np.testing.assert_array_equal(grids["candidate_bed_m"], reverse["candidate_bed_m"])

    def test_missing_quadrant_and_rehashed_boundary_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError, "hole"):
            assemble(self.records[:3], self.geometry["identity_sha256"])
        tiles = copy.deepcopy(self.tiles)
        tile = tiles[0]
        tile["arrays"] = {name: values.copy() for name, values in tile["arrays"].items()}
        tile["arrays"]["candidate_cut_m"][:, -1] += .01
        tile["arrays"]["candidate_bed_m"] = tile["arrays"]["native_bilinear_bed_m"] - tile["arrays"]["candidate_cut_m"]
        tile["identity_sha256"] = identity(tile["arrays"], tile["metadata"])
        with self.assertRaisesRegex(ValueError, "conflict"):
            assemble(self.save(tiles, prefix="tampered"), self.geometry["identity_sha256"])

    def test_self_consistent_fake_incision_rejected_by_raw_reference(self):
        grids, metadata, bounds, shared = assemble(self.records, self.geometry["identity_sha256"])
        grids["candidate_cut_m"] += .01
        grids["candidate_bed_m"] = grids["native_bilinear_bed_m"] - grids["candidate_cut_m"]
        with self.assertRaisesRegex(ValueError, "channel support"):
            sample_reference(self.hierarchy["arrays"], self.hierarchy["metadata"],
                             self.geometry["arrays"], metadata, bounds, grids)

    def test_unknown_native_stencil_rejected(self):
        grids, metadata, bounds, shared = assemble(self.records, self.geometry["identity_sha256"])
        topology = {name: values.copy() for name, values in self.hierarchy["arrays"].items()}
        topology["valid_mask"][1, 1] = False
        with self.assertRaisesRegex(ValueError, "unknown"):
            sample_reference(topology, self.hierarchy["metadata"], self.geometry["arrays"], metadata, bounds, grids)


if __name__ == "__main__":
    unittest.main()
