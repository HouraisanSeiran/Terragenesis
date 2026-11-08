import numpy as np
import pytest

from terrain_pipeline.coastal_delta_routes import irregular_valley_path


def test_irregular_path_uses_metric_mesh_and_obeys_barriers():
    bed = np.zeros((8, 8))
    valid = np.ones_like(bed, dtype=bool)
    valid[:, 4] = False
    valid[5, 4] = True
    bed[2, 2] = 2.
    cells, points = irregular_valley_path(bed, valid, (1, 1), (6, 6), 1., 200.)
    assert tuple(cells[0]) == (1, 1)
    assert tuple(cells[-1]) == (6, 6)
    assert valid[tuple(cells.T)].all()
    assert (bed[tuple(cells.T)] < 1.).all()
    assert not np.allclose(np.linalg.norm(np.diff(points, axis=0), axis=1), 200.)
    valid[:, 4] = False
    with pytest.raises(ValueError, match='no irregular path'):
        irregular_valley_path(bed, valid, (1, 1), (6, 6), 1., 200.)


def test_mask_target_and_exact_start_are_deterministic_and_segments_legal():
    from terrain_pipeline.channel_geometry import _segment_owner_samples

    bed = np.zeros((9, 9))
    valid = np.ones_like(bed, dtype=bool)
    valid[3:7, 4] = False
    targets = np.zeros_like(valid)
    targets[1, 7] = targets[7, 7] = True
    kwargs = dict(target_mask=targets, start_xz_m=(210., 190.), world_seed=20260903)
    cells, points = irregular_valley_path(bed, valid, (1, 1), None, 1., 200., **kwargs)
    repeated = irregular_valley_path(bed, valid, (1, 1), None, 1., 200., **kwargs)
    np.testing.assert_array_equal(cells, repeated[0])
    np.testing.assert_array_equal(points, repeated[1])
    np.testing.assert_array_equal(points[0], [210., 190.])
    assert targets[tuple(cells[-1])]
    samples = _segment_owner_samples(points, np.zeros(2), 200.)
    owners = np.floor(samples / 200. + .5).astype(int)
    assert valid[owners[:, 1], owners[:, 0]].all()
    with pytest.raises(ValueError, match='exact start'):
        irregular_valley_path(bed, valid, (1, 1), None, 1., 200.,
                              target_mask=targets, start_xz_m=(400., 200.))


def test_reused_mesh_matches_independently_built_mesh():
    from terrain_pipeline.drainage import grid_mesh as grid_mesh

    bed = np.zeros((9, 9))
    valid = np.ones_like(bed, dtype=bool)
    valid[3:7, 4] = False
    targets = np.zeros_like(valid); targets[1, 7] = targets[7, 7] = True
    kwargs = dict(origin_xz_m=(35., -70.), world_seed=42, target_mask=targets,
                  start_xz_m=(245., 120.))
    mesh = grid_mesh(bed.shape, x0_m=35., z0_m=-70., dx_m=200., world_seed=42)
    old = irregular_valley_path(bed, valid, (1, 1), None, 1., 200., **kwargs)
    reused = irregular_valley_path(bed, valid, (1, 1), None, 1., 200., mesh=mesh, **kwargs)
    np.testing.assert_array_equal(old[0], reused[0])
    np.testing.assert_array_equal(old[1], reused[1])
