import numpy as np
import pytest

from tools.prepare_natural_delta_expanded_initial import prepare, sample_piece


@pytest.fixture(scope="module")
def prepared():
    return prepare()


def test_independent_geometry_preserves_marine_source_and_mutable_interior(prepared):
    arrays, report = prepared
    marine = arrays["station_m"] >= 0.
    np.testing.assert_array_equal(arrays["initial_bed_m"][marine], arrays["source_base_bed_m"][marine])
    assert not np.any(arrays["construction_height_delta_m"] > 0.)
    assert np.count_nonzero(arrays["cell_type"] == 1) == 2
    assert np.all(arrays["cell_type"][2:-1, 1:-1] == 0)
    assert report["parent_checkpoint"] is None
    assert report["new_boundary_supply_delivered_solid_m3"] == 0.


def test_preflight_exposes_mouth_lip_and_rejects_short_run(prepared):
    arrays, report = prepared
    assert arrays["initial_bed_m"][72, 120] > arrays["initial_bed_m"][71, 120]
    assert report["mouth_last_land_to_base_jump_m"] > .7
    assert report["short_validation"]["status"] == "not-runnable-preflight-failed"
    assert report["short_validation"]["command"] is None
    assert not report["inlet"]["hydraulic_acceptance"]
    assert report["inlet"]["first_q_inlet_froude"] > 30.


def test_relative_cut_interpolates_archived_triangle_and_clips_unknown_support(tmp_path):
    path = tmp_path / "piece.npz"
    np.savez(path, vertices_xz_m=np.array([[100., 200.], [102., 200.], [100., 202.]]),
        triangles=np.array([[0, 1, 2]]), local_channel_delta_m=np.array([0., -2., -2.]), width_m=np.array([8.]))
    world = np.array([[[100.5, 200.5], [103., 203.]]])
    delta, support, identity = sample_piece({"source_path": str(path), "index": 15, "identity": "fixture"}, world)
    np.testing.assert_allclose(delta, [[-1., 0.]])
    np.testing.assert_array_equal(support, [[True, False]])
    assert identity["field"] == "local_channel_delta_m"
