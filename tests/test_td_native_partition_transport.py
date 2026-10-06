"""Independent NumPy full-grid reference for bounded partition transport."""

import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.td_native_domain_partition import NativePartition, StageSnapshot
from terrain_pipeline.td_native_partition_transport import transport
from terrain_pipeline import td_native_partition_transport as prototype


def snapshot(partition, grid, version):
    return StageSnapshot(partition, version, {
        tile.tile_id: (version, grid[tile.interior_zx[0]:tile.interior_zx[1],
                                     tile.interior_zx[2]:tile.interior_zx[3]]) for tile in partition.tiles()})


def reference(bed, depth, valid, opened, spacing, dt_s, steps):
    height, width = bed.shape
    faces = []
    for first in range(height * width):
        row, column = divmod(first, width)
        if not valid.ravel()[first]:
            continue
        if column + 1 < width and valid.ravel()[first + 1]:
            faces.append((2 * first, first, first + 1))
        if row + 1 < height and valid.ravel()[first + width]:
            faces.append((2 * first + 1, first, first + width))
    boundaries = []
    for cell_id in np.flatnonzero(opened):
        row, column = divmod(int(cell_id), width)
        if row not in (0, height - 1) and column not in (0, width - 1):
            raise ValueError("false outlet")
        boundaries.append((int(cell_id), spacing * ((row == 0) + (row == height - 1) +
                                                    (column == 0) + (column == width - 1))))
    bed_flat = bed.ravel()
    current = depth.ravel().copy()
    forward = np.zeros(len(faces))
    reverse = np.zeros(len(faces))
    exported = np.zeros(len(boundaries))

    def stage(values):
        derivative = np.zeros(values.size)
        rates = np.zeros(len(faces))
        exits = np.zeros(len(boundaries))
        for index, (_, first, second) in enumerate(faces):
            first_head = bed_flat[first] + values[first]
            second_head = bed_flat[second] + values[second]
            sill = max(bed_flat[first], bed_flat[second])
            if first_head >= second_head:
                rate = .6 / spacing * max(first_head - max(sill, second_head), 0.)
            else:
                rate = -.6 / spacing * max(second_head - max(sill, first_head), 0.)
            rates[index] = rate
            derivative[first] -= rate
            derivative[second] += rate
        for index, (cell_id, width_m) in enumerate(boundaries):
            exits[index] = .6 * width_m / spacing**2 * values[cell_id]
            derivative[cell_id] -= exits[index]
        return derivative, rates, exits

    for _ in range(steps):
        derivative0, rate0, exit0 = stage(current)
        stage1 = current + dt_s * derivative0
        derivative1, rate1, exit1 = stage(stage1)
        current = .5 * current + .5 * (stage1 + dt_s * derivative1)
        forward += .5 * dt_s * spacing**2 * (np.maximum(rate0, 0) + np.maximum(rate1, 0))
        reverse += .5 * dt_s * spacing**2 * (np.maximum(-rate0, 0) + np.maximum(-rate1, 0))
        exported += .5 * dt_s * spacing**2 * (exit0 + exit1)
    return current.reshape(bed.shape), np.array([face[0] for face in faces]), forward, reverse, exported


class TransportTests(unittest.TestCase):
    def test_cross_seam_reverse_hole_open_and_order(self):
        shape = (259, 258)
        partition = NativePartition(shape)
        bed = np.zeros(shape, dtype=np.float64)
        depth = np.zeros(shape, dtype=np.float64)
        depth[255, 255] = .2
        depth[255, 256] = 1.0
        depth[256, 255] = .8
        valid = np.ones(shape, dtype=bool)
        valid[3, 4] = False
        opened = np.zeros(shape, dtype=bool)
        opened[0, 0] = True
        depth[0, 0] = .4
        bed_snapshot = snapshot(partition, bed, "bed")
        depth_snapshot = snapshot(partition, depth, "start")
        expected = reference(bed, depth, valid, opened, 30., 1., 2)
        forward = transport(partition, bed_snapshot, depth_snapshot, valid, opened, spacing_m=30., dt_s=1., steps=2)
        backward = transport(partition, bed_snapshot, depth_snapshot, valid, opened, spacing_m=30., dt_s=1., steps=2,
                             tile_order=reversed(range(partition.tile_count)))
        assembled = np.zeros(shape)
        for tile in partition.tiles():
            z0, z1, x0, x1 = tile.interior_zx
            assembled[z0:z1, x0:x1] = forward["final_tile_chunks"][tile.tile_id]
            np.testing.assert_array_equal(forward["final_tile_chunks"][tile.tile_id],
                                          backward["final_tile_chunks"][tile.tile_id])
        np.testing.assert_allclose(assembled, expected[0], rtol=0, atol=1e-15)
        np.testing.assert_array_equal(forward["face_ids"], expected[1])
        np.testing.assert_allclose(forward["forward_m3"], expected[2], rtol=0, atol=1e-13)
        np.testing.assert_allclose(forward["reverse_m3"], expected[3], rtol=0, atol=1e-13)
        np.testing.assert_allclose(forward["boundary_outflow_m3"], expected[4], rtol=0, atol=1e-13)
        np.testing.assert_array_equal(forward["forward_m3"], backward["forward_m3"])
        np.testing.assert_array_equal(forward["reverse_m3"], backward["reverse_m3"])
        np.testing.assert_array_equal(forward["boundary_outflow_m3"], backward["boundary_outflow_m3"])
        self.assertGreater(float(forward["reverse_m3"].sum()), 0.)
        self.assertEqual(forward["boundary_cells"].tolist(), [0])
        self.assertLess(abs(forward["volume_budget"]["residual_m3"]), 1e-6)

    def test_closed_constant_head(self):
        partition = NativePartition((3, 4))
        bed = np.full((3, 4), 2.)
        depth = np.full((3, 4), .2)
        valid = np.ones((3, 4), bool)
        result = transport(partition, snapshot(partition, bed, "bed"), snapshot(partition, depth, "start"),
                           valid, np.zeros_like(valid), spacing_m=30., dt_s=1.)
        self.assertEqual(result["forward_m3"].sum(), 0.)
        self.assertEqual(result["reverse_m3"].sum(), 0.)
        self.assertEqual(result["boundary_outflow_m3"].size, 0)

    def test_rejects_false_outlet_cfl_and_budget(self):
        partition = NativePartition((3, 3))
        bed = snapshot(partition, np.zeros((3, 3)), "bed")
        depth = snapshot(partition, np.ones((3, 3)), "start")
        valid = np.ones((3, 3), bool)
        opened = np.zeros((3, 3), bool)
        opened[1, 1] = True
        with self.assertRaises(ValueError):
            transport(partition, bed, depth, valid, opened, spacing_m=30., dt_s=1.)
        with self.assertRaises(ValueError):
            transport(partition, bed, depth, valid, np.zeros_like(valid), spacing_m=1., dt_s=10.)
        with self.assertRaises(ValueError):
            transport(partition, bed, depth, valid, np.zeros_like(valid), spacing_m=30., dt_s=1., steps=9)
        with self.assertRaises(ValueError):
            transport(partition, bed, depth, valid, np.zeros_like(valid), spacing_m=30., dt_s=1., tile_order=(0, 0))
        with patch.object(prototype, "MAX_BYTES", 1):
            with self.assertRaises(MemoryError):
                transport(partition, bed, depth, valid, np.zeros_like(valid), spacing_m=30., dt_s=1.)
        with patch.object(prototype, "MAX_FACE_STEPS", 1):
            with self.assertRaises(ValueError):
                transport(partition, bed, depth, valid, np.zeros_like(valid), spacing_m=30., dt_s=1.)

    def test_import_has_no_numba_or_v6_solver(self):
        code = ("import terrain_pipeline.td_native_partition_transport; import sys; "
                "assert 'numba' not in sys.modules; "
                "assert 'terrain_pipeline.td_basin_transport_v6' not in sys.modules")
        subprocess.run([sys.executable, "-c", code], check=True)


if __name__ == "__main__":
    unittest.main()
