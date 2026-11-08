"""Saved forward states must match actual evolution, with no numerical change."""
import numpy as np
from terrain_pipeline import tectonic


def test_capture_matches_initial_final_without_changing_evolution():
    config = tectonic.TectonicConfig(shape=(8, 8), steps=3, plate_count=3, world_seed=20260903)
    snapshots = []
    actual = tectonic.evolve(config, stage_callback=lambda index, fields: snapshots.append(
        (index, {k: np.asarray(v).copy() for k, v in fields.items()})))
    plain = tectonic.evolve(config)
    assert [item[0] for item in snapshots] == [0, 1, 2, 3]
    np.testing.assert_array_equal(snapshots[0][1]['elevation_m'], actual.initial_elevation_m)
    np.testing.assert_array_equal(snapshots[-1][1]['elevation_m'], actual.elevation_m)
    np.testing.assert_array_equal(actual.elevation_m, plain.elevation_m)
