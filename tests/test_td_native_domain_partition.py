"""Independent tiny-grid checks for native partition topology and stage halos."""

import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError

import numpy as np

from terrain_pipeline.td_native_domain_partition import NativePartition, StageSnapshot


class PartitionTests(unittest.TestCase):
    def test_tiny_exhaustive_faces_and_no_false_open_boundary(self):
        shape = (259, 258)
        partition = NativePartition(shape)
        mask = np.ones(shape, dtype=bool)
        mask[0, 2] = False
        mask[256, 257] = False
        valid = mask.ravel()
        actual = {}
        owned_cells = set()
        for tile in partition.tiles():
            for cell_id in tile.interior_ids():
                self.assertNotIn(cell_id, owned_cells)
                owned_cells.add(cell_id)
            for face in partition.faces(tile, lambda cell_id: valid[cell_id]):
                self.assertNotIn(face.face_id, actual)
                self.assertEqual(face.owner_tile_id, partition.owner_of_cell(face.first_cell_id))
                expected_neighbor = partition.owner_of_cell(face.second_cell_id)
                self.assertEqual(face.neighbor_tile_id,
                                 expected_neighbor if expected_neighbor != face.owner_tile_id else None)
                actual[face.face_id] = (face.first_cell_id, face.second_cell_id)
        self.assertEqual(len(owned_cells), shape[0] * shape[1])
        expected = {}
        for first in range(valid.size):
            if not valid[first]:
                continue
            row, column = divmod(first, shape[1])
            if column + 1 < shape[1] and valid[first + 1]:
                expected[2 * first] = (first, first + 1)
            if row + 1 < shape[0] and valid[first + shape[1]]:
                expected[2 * first + 1] = (first, first + shape[1])
        self.assertEqual(actual, expected)
        opened = np.zeros(valid.size, dtype=bool)
        opened[1] = True
        opened[shape[1] * 256 + 256] = True
        with self.assertRaises(ValueError):
            for tile in partition.tiles():
                list(partition.open_boundary_cells(tile, lambda cell_id: valid[cell_id],
                                                   lambda cell_id: opened[cell_id]))
        opened[shape[1] * 256 + 256] = False
        self.assertEqual([cell for tile in partition.tiles() for cell in partition.open_boundary_cells(
            tile, lambda cell_id: valid[cell_id], lambda cell_id: opened[cell_id])], [1])

    def test_halo_snapshot_is_copied_readonly_and_order_independent(self):
        partition = NativePartition((258, 258))
        chunks = {}
        for tile in partition.tiles():
            z0, z1, x0, x1 = tile.interior_zx
            values = np.arange(z0, z1)[:, None] * 258 + np.arange(x0, x1)[None, :]
            chunks[tile.tile_id] = ("stage-4", values.astype(np.float64))
        snapshot = StageSnapshot(partition, "stage-4", chunks)
        chunks[0][1][:] = -1
        samples = {}
        for tile in reversed(list(partition.tiles())):
            halo = snapshot.sample_halo(tile, version="stage-4")
            self.assertFalse(halo.flags.writeable)
            z0, z1, x0, x1 = tile.halo_zx
            expected = np.arange(z0, z1)[:, None] * 258 + np.arange(x0, x1)[None, :]
            np.testing.assert_array_equal(halo, expected)
            samples[tile.tile_id] = halo.copy()
            with self.assertRaises(ValueError):
                halo[0, 0] = 999
        for tile in partition.tiles():
            np.testing.assert_array_equal(snapshot.sample_halo(tile, version="stage-4"), samples[tile.tile_id])
        with self.assertRaises(ValueError):
            snapshot.sample_halo(partition.tile(0), version="stage-5")
        mixed = dict(chunks)
        mixed[1] = ("stage-5", chunks[1][1])
        with self.assertRaises(ValueError):
            StageSnapshot(partition, "stage-4", mixed)

    def test_snapshot_and_partition_cannot_be_rebound_or_mutated(self):
        partition = NativePartition((2, 3))
        values = np.arange(6, dtype=np.float64).reshape(2, 3)
        snapshot = StageSnapshot(partition, "stage-0", {0: ("stage-0", values)})
        for name, replacement in (("shape_zx", (9, 9)), ("tile_columns", 9),
                                  ("tile_rows", 9), ("tile_count", 9)):
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(partition, name, replacement)
        for name, replacement in (("partition", NativePartition((3, 3))),
                                  ("version", "stage-1"), ("chunks", {})):
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(snapshot, name, replacement)
        with self.assertRaises(TypeError):
            snapshot.chunks[0] = np.zeros((2, 3))
        with self.assertRaises(TypeError):
            del snapshot.chunks[0]
        with self.assertRaises(ValueError):
            snapshot.chunks[0].setflags(write=True)
        with self.assertRaises(ValueError):
            snapshot.sample_halo(partition.tile(0), version="stage-0").setflags(write=True)
        values[:] = -1
        np.testing.assert_array_equal(snapshot.chunks[0], np.arange(6).reshape(2, 3))
        with self.assertRaises((AttributeError, TypeError)):
            partition.extra = 1
        with self.assertRaises((AttributeError, TypeError)):
            snapshot.extra = 1

    def test_invalid_shape_ids_masks_and_tile(self):
        for shape in ((0, 3), (2049, 4), (1.0, 2), [2, 2]):
            with self.assertRaises(ValueError):
                NativePartition(shape)
        partition = NativePartition((2, 3))
        for cell_id in (-1, 6, 1.0):
            with self.assertRaises(ValueError):
                partition.owner_of_cell(cell_id)
        with self.assertRaises(ValueError):
            partition.tile(1)
        with self.assertRaises(ValueError):
            list(partition.faces(partition.tile(0), lambda cell_id: 1))
        with self.assertRaises(ValueError):
            list(partition.open_boundary_cells(partition.tile(0), lambda cell_id: True,
                                               lambda cell_id: "yes"))

    def test_import_has_no_solver_or_numba(self):
        code = ("import terrain_pipeline.td_native_domain_partition; import sys; "
                "assert 'numba' not in sys.modules; "
                "assert 'terrain_pipeline.td_basin_storage_v10' not in sys.modules")
        subprocess.run([sys.executable, "-c", code], check=True)


if __name__ == "__main__":
    unittest.main()
