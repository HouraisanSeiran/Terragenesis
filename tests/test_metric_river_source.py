import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, save_bundle
from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.surface_rivers.metric_source import (load_source_registration,
                                                          register_source, save_source_registration,
                                                          slice_tile)


def fixture(height, *, valid=None, dx=3., dz=4., source_path=None):
    values = np.asarray(height, np.float64)
    mask = np.ones(values.shape, bool) if valid is None else np.asarray(valid, bool)
    terrain = TerrainGrid(values, mask, 100., 200., dx, dz, "generated_terrain", "fixture",
                          "a" * 64, crs=None, vertical_datum="sea_zero_m",
                          model_version="td-revision", generation_seed=42,
                          condition_summary="c" * 64, source_path=source_path)
    kinds = np.full(values.shape, "interior", dtype="U24")
    kinds[[0, -1], :] = "closed_wall"
    kinds[:, [0, -1]] = "closed_wall"
    kinds[~mask] = "unknown_boundary"
    boundary = BoundaryGrid(kinds, np.zeros(values.shape, bool), "boundary", "b" * 64)
    return terrain, boundary


class SourceRegistrationTests(unittest.TestCase):
    def test_adjacent_tiles_retain_parent_coordinates_and_cut_edges_are_unknown(self):
        terrain, boundary = fixture([[9., 8., 7., 6.], [5., 4., 3., 2.]])
        left = slice_tile(terrain, boundary, 0, 2, 0, 2)
        right = slice_tile(terrain, boundary, 0, 2, 2, 4)
        self.assertEqual(left["terrain"].world_xz(1), (103., 200.))
        self.assertEqual(right["terrain"].world_xz(0), (106., 200.))
        self.assertEqual(left["terrain"].cell_area_m2, 12.)
        self.assertEqual(right["terrain"].cell_area_m2, 12.)
        self.assertEqual(left["boundary"].kind[0, -1], "unknown_boundary")
        self.assertEqual(right["boundary"].kind[0, 0], "unknown_boundary")
        self.assertEqual(left["metadata"]["parent_terrain_identity_sha256"], terrain.identity_sha256)
        self.assertEqual(left["metadata"]["grid_shape_zx"], [2, 2])
        self.assertEqual(left["metadata"]["elevation_dtype"], "float64")
        self.assertEqual(left["metadata"]["valid_elevation_range_m"], [4., 9.])
        self.assertEqual(left["metadata"]["nodata_fraction"], 0.)
        self.assertEqual(left["metadata"]["coordinate_sample_range_m_xz"], [[100., 103.], [200., 204.]])
        np.testing.assert_array_equal(np.hstack((left["terrain"].elevation_m,
                                                 right["terrain"].elevation_m)), terrain.elevation_m)

    def test_registration_binds_file_and_generation_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            source.write_bytes(b"original td evidence")
            terrain, boundary = fixture([[2., 1.]], source_path=str(source))
            with self.assertRaises(ValueError):
                register_source(terrain, boundary)
            terrain = TerrainGrid(terrain.elevation_m, terrain.valid_mask, terrain.x0_m, terrain.z0_m,
                                  terrain.dx_m, terrain.dz_m, terrain.source_kind, terrain.source_id,
                                  file_sha256(source), vertical_datum="sea_zero_m", model_version="td-revision",
                                  generation_seed=42, condition_summary="c" * 64,
                                  source_path=str(source))
            registration = register_source(terrain, boundary, source_metadata={
                "model_id": "td", "model_revision": "td-revision", "seed": 42,
                "conditioning_sha256": "c" * 64, "vertical_datum": "sea_zero_m",
                "boundary_evidence_sha256": boundary.source_sha256})
            self.assertEqual(registration["metadata"]["provenance_status"], "pending_provenance")
            self.assertEqual(registration["metadata"]["source_sha256"], file_sha256(source))
            archive = Path(directory) / "registered.npz"
            save_source_registration(archive, registration)
            loaded = load_source_registration(archive, expected_sha256=file_sha256(archive))
            self.assertEqual(loaded["identity_sha256"], registration["identity_sha256"])
            np.testing.assert_array_equal(loaded["terrain"].elevation_m, terrain.elevation_m)
            with self.assertRaises(ValueError):
                load_source_registration(archive, expected_sha256=file_sha256(archive),
                                         expected_identity="0" * 64)
            with self.assertRaises(ValueError):
                register_source(terrain, boundary, source_metadata={
                    "generation_metadata": {"seed": 42, "conditioning_identity": "d" * 64}})
            with self.assertRaises(ValueError):
                register_source(terrain, boundary, source_metadata={
                    "source_identity_sha256": "e" * 64})
            source.write_bytes(b"tampered source")
            with self.assertRaises(ValueError):
                register_source(terrain, boundary)
            with self.assertRaises(ValueError):
                load_source_registration(archive, expected_sha256="0" * 64)

    def test_tile_does_not_fill_unknown_and_preserves_parent_outlet(self):
        terrain, boundary = fixture([[4., np.nan, 3.], [2., 1., 0.]],
                                    valid=[[True, False, True], [True, True, True]])
        selected = slice_tile(terrain, boundary, 0, 2, 1, 3)
        self.assertFalse(selected["terrain"].valid_mask[0, 0])
        self.assertEqual(selected["boundary"].kind[0, 0], "unknown_boundary")
        self.assertEqual(selected["terrain"].elevation_m[0, 0], 0.)

    def test_saved_tile_cold_load_validates_parent_window_geometry(self):
        terrain, boundary = fixture([[9., 8., 7.], [6., 5., 4.], [3., 2., 1.]])
        tile = slice_tile(terrain, boundary, 1, 3, 1, 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tile.npz"
            save_source_registration(path, tile)
            loaded = load_source_registration(path, expected_sha256=file_sha256(path),
                                              expected_identity=tile["identity_sha256"])
            self.assertEqual(loaded["terrain"].world_xz(0), (103., 204.))
            self.assertEqual(loaded["metadata"]["parent_shape_zx"], [3, 3])

    def test_rehashed_tile_with_false_parent_origin_is_rejected(self):
        terrain, boundary = fixture([[9., 8., 7.], [6., 5., 4.], [3., 2., 1.]])
        tile = slice_tile(terrain, boundary, 1, 3, 1, 3)
        forged = {"arrays": {"elevation_m": tile["terrain"].elevation_m.copy(),
                             "valid_mask": tile["terrain"].valid_mask.copy(),
                             "boundary_kind": tile["boundary"].kind.copy(),
                             "boundary_allow_inflow": tile["boundary"].allow_inflow.copy()},
                  "metadata": copy.deepcopy(tile["metadata"])}
        forged["metadata"]["parent_origin_m_xz"][0] += 1.
        forged["identity_sha256"] = identity({}, forged["metadata"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged-tile.npz"
            save_bundle(path, forged, validator=lambda _: None)
            with self.assertRaises(ValueError):
                load_source_registration(path, expected_sha256=file_sha256(path))


if __name__ == "__main__":
    unittest.main()
