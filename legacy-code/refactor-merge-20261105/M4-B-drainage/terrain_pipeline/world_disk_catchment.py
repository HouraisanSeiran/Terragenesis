"""Disk-backed raw irregular-graph catchment certification for labelled basins."""
from pathlib import Path

import numpy as np
from numba import njit

from terrain_pipeline.irregular_drainage import build_mesh


@njit
def _assign(bed, labels, owner, stack, indptr, indices, lengths):
    for start in range(bed.size):
        if owner[start] != -2:
            continue
        current = start
        count = 0
        while owner[current] == -2:
            stack[count] = current
            count += 1
            best = 0.0
            target = -1
            for edge in range(indptr[current], indptr[current + 1]):
                neighbour = indices[edge]
                slope = (bed[current] - bed[neighbour]) / lengths[edge]
                if slope > best or (slope == best and slope > 0. and neighbour < target):
                    best = slope
                    target = neighbour
            if target < 0:
                owner[current] = labels[current]
                break
            current = target
        root = owner[current]
        while count:
            count -= 1
            owner[stack[count]] = root


@njit
def _counts(labels, owner, rows, cols, unknown, leaked):
    for cell in range(rows * cols):
        label = labels[cell]
        if label >= 0 and owner[cell] != label:
            leaked[label] += 1
        row, col = cell // cols, cell % cols
        root = owner[cell]
        if root >= 0 and (row < 6 or col < 6 or row >= rows - 6 or col >= cols - 6):
            unknown[root] += 1


def certify_raw_catchments(bed, labels, work_dir, *, mesh=None):
    """Return native-lake raw catchment unknown/leak counts for each label.

    Uses disk-backed owner and traversal-stack arrays. Labels must be dense
    nonnegative integers (or -1 outside basins), matching the basin label grid.
    Input arrays remain open and untouched; all internally opened maps close.
    """
    terrain = np.asarray(bed)
    basin = np.asarray(labels)
    if (terrain.ndim != 2 or terrain.dtype != np.float64 or basin.shape != terrain.shape or
            basin.dtype.kind not in "iu" or not np.isfinite(terrain).all()):
        raise ValueError("finite float64 terrain and matching integer labels required")
    if basin.dtype.kind == "u" or np.any(basin < -1):
        raise ValueError("labels must be signed integers with -1 for non-basin cells")
    ids = np.unique(basin[basin >= 0])
    if ids.size and not np.array_equal(ids, np.arange(ids.size)):
        raise ValueError("basin labels must be dense from zero")
    if mesh is None:
        mesh = build_mesh(terrain.shape)
    if mesh.shape != terrain.shape:
        raise ValueError("mesh must match terrain shape")
    directory = Path(work_dir)
    directory.mkdir(parents=True, exist_ok=False)
    owner = stack = None
    try:
        owner = np.lib.format.open_memmap(directory / "raw-owner.npy", mode="w+",
                                          dtype=np.int64, shape=(terrain.size,))
        stack = np.lib.format.open_memmap(directory / "raw-stack.npy", mode="w+",
                                          dtype=np.int64, shape=(terrain.size,))
        owner[:] = -2
        _assign(terrain.ravel(), basin.ravel(), owner, stack, mesh.indptr, mesh.indices, mesh.edge_length_m)
        unknown = np.zeros(ids.size, dtype=np.int64)
        leaked = np.zeros(ids.size, dtype=np.int64)
        _counts(basin.ravel(), owner, *terrain.shape, unknown, leaked)
        owner.flush()
        return {int(label): {"unknown_cells": int(unknown[label]),
                             "leaked_cells": int(leaked[label])} for label in ids}
    finally:
        for array in (owner, stack):
            if array is not None:
                array._mmap.close()
