"""Raw catchment certification follows the actual irregular terrain graph."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import certify_raw_catchments as certify_raw_catchments


def reference_counts(bed, labels, mesh):
    owner = np.full(bed.size, -1, dtype=np.int64)
    for start in range(bed.size):
        cell = start
        while True:
            edges = range(mesh.indptr[cell], mesh.indptr[cell + 1])
            candidates = [(float((bed.ravel()[cell] - bed.ravel()[mesh.indices[e]])
                           / mesh.edge_length_m[e]), int(mesh.indices[e])) for e in edges]
            slopes = [(slope, target) for slope, target in candidates if slope > 0.]
            if not slopes:
                owner[start] = labels.ravel()[cell]
                break
            cell = min(slopes, key=lambda item: (-item[0], item[1]))[1]
    rows, cols = bed.shape
    row, col = np.indices(bed.shape)
    border = (row < 6) | (col < 6) | (row >= rows - 6) | (col >= cols - 6)
    return {int(label): {
        "unknown_cells": int(np.count_nonzero((owner == label) & border.ravel())),
        "leaked_cells": int(np.count_nonzero((labels.ravel() == label) & (owner != label)))}
        for label in np.unique(labels[labels >= 0])}


class DiskCatchmentTests(unittest.TestCase):
    def test_graph_multiple_basins_and_unknown(self):
        z, x = np.indices((41, 51))
        bed = 30. - x * .05 + np.abs(z - 20) * .12
        for centre, depth in ((15, 8.), (34, 12.)):
            bed -= depth * np.maximum(0., 1. - np.hypot(x - centre, z - 20) / 6.)
        labels = np.full(bed.shape, -1, dtype=np.int64)
        labels[np.hypot(x - 15, z - 20) < 4] = 0
        labels[np.hypot(x - 34, z - 20) < 4] = 1
        mesh = build_mesh(bed.shape, origin_native_xz=(-17, 43))
        with tempfile.TemporaryDirectory() as root:
            actual = certify_raw_catchments(bed.astype(np.float64), labels, Path(root) / "work", mesh=mesh)
        self.assertEqual(actual, reference_counts(bed, labels, mesh))
        self.assertGreater(sum(item["unknown_cells"] for item in actual.values()), 0)

    def test_flat_ties_and_leaked_members(self):
        bed = np.full((19, 19), 5., dtype=np.float64)
        bed[9, 9] = 0.
        labels = np.full(bed.shape, -1, dtype=np.int64)
        labels[9, 9] = 0
        labels[1, 1] = 0
        mesh = build_mesh(bed.shape)
        with tempfile.TemporaryDirectory() as root:
            actual = certify_raw_catchments(bed, labels, Path(root) / "work", mesh=mesh)
        self.assertEqual(actual, reference_counts(bed, labels, mesh))
        self.assertGreater(actual[0]["unknown_cells"], 0)


if __name__ == "__main__":
    unittest.main()
