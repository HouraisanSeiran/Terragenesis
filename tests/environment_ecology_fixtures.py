"""Small shared environment process fixtures; no saved-world dependency."""
import copy
import tempfile
from pathlib import Path

import numpy as np


def context():
    rows, cols = np.indices((7, 7))
    height = .3 - cols * .1 + rows * .005
    ocean = cols >= 5
    protected = np.zeros(height.shape, bool)
    protected[0, 0] = True
    river = np.zeros(height.shape, bool)
    river[3, :5] = True
    return {"height_m": height, "spacing_m": 30., "origin_native_xz": (-4, 8),
            "world_seed": 20261020, "receiver": np.full(height.shape, -1, np.int64),
            "valid_mask": np.ones(height.shape, bool), "protected_mask": protected,
            "ocean_mask": ocean, "river_mask": river}


def cold(state):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.npz"
        np.savez(path, **state)
        with np.load(path, allow_pickle=False) as archive:
            return {key: archive[key].copy() for key in archive.files}


def assert_same(test, first, second):
    test.assertEqual(set(first), set(second))
    for key in first:
        np.testing.assert_array_equal(first[key], second[key], err_msg=key)


def immutable_call(test, step, state, forcing, ctx, dt_s):
    snapshots = copy.deepcopy((state, forcing, ctx))
    result = step(state, forcing, ctx, dt_s)
    for original, snapshot in zip((state, forcing, ctx), snapshots):
        assert_same(test, original, snapshot)
    return result
