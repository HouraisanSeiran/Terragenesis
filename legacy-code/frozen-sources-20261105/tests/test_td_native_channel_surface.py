import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_native_channel_geometry import build_channel_geometry
from terrain_pipeline.td_native_channel_tiles import TileRecipe, build_channel_tile, split_window_2x2
from terrain_pipeline.td_native_channel_surface import (
    build_channel_surface, export_surface_obj, load_channel_surface,
    save_channel_surface, validate_channel_surface,
)
from tests.test_td_native_channel_geometry import fixture


class NativeChannelSurfaceTests(unittest.TestCase):
    def inputs(self):
        geometry = build_channel_geometry(*fixture())
        tiles = [build_channel_tile(geometry, window=window) for window in split_window_2x2((0, 60, 0, 60))]
        return tiles, geometry

    def test_shared_vertices_fixed_diagonal_upward_and_order(self):
        tiles, geometry = self.inputs()
        mesh = build_channel_surface(tiles, geometry=geometry)
        reverse = build_channel_surface(tiles[::-1], geometry=geometry)
        self.assertEqual(mesh["identity_sha256"], reverse["identity_sha256"])
        arrays = mesh["arrays"]
        self.assertEqual(len(arrays["vertices_xyz_m"]), 61 * 61)
        self.assertEqual(len(arrays["triangles"]), 2 * 60 * 60)
        self.assertEqual(len(np.unique(arrays["vertex_lattice_xz"], axis=0)), 61 * 61)
        np.testing.assert_array_equal(arrays["triangles"][:2], [[0, 61, 62], [0, 62, 1]])
        self.assertTrue(np.all(arrays["face_normals_xyz"][:, 1] > 0))
        self.assertTrue(np.all(arrays["vertex_normals_xyz"][:, 1] > 0))
        self.assertFalse(mesh["metadata"]["water_generated"])
        full = build_channel_tile(geometry, window=(0, 60, 0, 60))
        np.testing.assert_array_equal(arrays["vertices_xyz_m"][:, 1], full["arrays"]["candidate_bed_m"].ravel())

    def test_obj_and_npz_cold_read_never_build(self):
        tiles, geometry = self.inputs()
        mesh = build_channel_surface(tiles, geometry=geometry)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mesh.npz"
            save_channel_surface(path, mesh)
            with patch("terrain_pipeline.td_native_channel_surface.build_channel_surface", side_effect=AssertionError("cold generation")), \
                    patch("terrain_pipeline.td_native_channel_tiles.build_channel_tile", side_effect=AssertionError("cold derivation")):
                loaded = load_channel_surface(path, expected_sha256=file_sha256(path), expected_identity=mesh["identity_sha256"])
            self.assertFalse(loaded["arrays"]["vertices_xyz_m"].flags.writeable)
            obj = Path(directory) / "mesh.obj"
            export_surface_obj(obj, loaded)
            lines = obj.read_text(encoding="ascii").splitlines()
            vertices = np.array([[float(value) for value in line.split()[1:]] for line in lines if line.startswith("v ")])
            faces = np.array([[int(value.split("//")[0])-1 for value in line.split()[1:]] for line in lines if line.startswith("f ")])
            np.testing.assert_array_equal(vertices, mesh["arrays"]["vertices_xyz_m"])
            np.testing.assert_array_equal(faces, mesh["arrays"]["triangles"])
            with self.assertRaises(ValueError):
                load_channel_surface(path, expected_sha256="0" * 64, expected_identity=mesh["identity_sha256"])

    def test_overlap_hole_mixed_lod_unknown_and_budget_rejected(self):
        tiles, geometry = self.inputs()
        bad = copy.deepcopy(tiles[1])
        bad["arrays"] = {name: values.copy() for name, values in bad["arrays"].items()}
        bad["arrays"]["candidate_cut_m"][0, 0] += .1
        bad["arrays"]["candidate_bed_m"] = bad["arrays"]["native_bilinear_bed_m"] - bad["arrays"]["candidate_cut_m"]
        bad["identity_sha256"] = identity(bad["arrays"], bad["metadata"])
        with self.assertRaisesRegex(ValueError, "conflict"):
            build_channel_surface([tiles[0], bad, tiles[2], tiles[3]], geometry=geometry)
        holes = [build_channel_tile(geometry, window=window) for window in
                 ((0, 20, 0, 20), (40, 60, 0, 20), (0, 20, 40, 60), (40, 60, 40, 60))]
        with self.assertRaisesRegex(ValueError, "hole"):
            build_channel_surface(holes, geometry=geometry)
        mixed = build_channel_tile(geometry, window=(0, 15, 0, 15), recipe=TileRecipe(2.))
        with self.assertRaisesRegex(ValueError, "LOD"):
            build_channel_surface([mixed] + tiles[1:], geometry=geometry)
        with self.assertRaises(ValueError):
            build_channel_surface([tiles[0]] * 4, geometry=geometry)
        unknown = copy.deepcopy(tiles[0])
        unknown["arrays"] = {name: values.copy() for name, values in unknown["arrays"].items()}
        unknown["arrays"]["native_bilinear_bed_m"][0, 0] = np.nan
        unknown["identity_sha256"] = identity(unknown["arrays"], unknown["metadata"])
        with self.assertRaises(ValueError):
            build_channel_surface([unknown] + tiles[1:], geometry=geometry)
        with patch("terrain_pipeline.td_native_channel_surface.MAX_VERTICES", 10):
            with self.assertRaisesRegex(ValueError, "preflight"):
                build_channel_surface(tiles, geometry=geometry)

    def test_rehashed_wrong_topology_normals_validity_flags_rejected(self):
        tiles, geometry = self.inputs()
        baseline = build_channel_surface(tiles, geometry=geometry)
        for kind in ("diagonal", "down", "normal", "duplicate", "unknown", "water", "source"):
            with self.subTest(kind=kind):
                bad = copy.deepcopy(baseline)
                arrays = bad["arrays"] = {name: values.copy() for name, values in bad["arrays"].items()}
                if kind == "diagonal":
                    arrays["triangles"][0, 2] = 1
                elif kind == "down":
                    arrays["triangles"][0] = arrays["triangles"][0, ::-1]
                elif kind == "normal":
                    arrays["face_normals_xyz"][0] *= -1
                elif kind == "duplicate":
                    arrays["vertex_lattice_xz"][1] = arrays["vertex_lattice_xz"][0]
                elif kind == "unknown":
                    arrays["valid_vertex_mask"][0] = False
                elif kind == "water":
                    bad["metadata"]["water_generated"] = True
                else:
                    bad["metadata"]["hierarchy_identity"] = "unknown"
                bad["identity_sha256"] = identity(arrays, bad["metadata"])
                with self.assertRaises(ValueError):
                    validate_channel_surface(bad)


if __name__ == "__main__":
    unittest.main()
