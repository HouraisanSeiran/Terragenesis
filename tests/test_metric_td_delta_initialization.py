import numpy as np

from terrain_pipeline.surface_rivers.metric_td_delta_initialization import prepare_td_initialization


def test_td_boundary_labels_follow_real_coast_and_interior_land_is_mobile():
    rows, cols = np.indices((101, 101))
    base = (50.-rows)*.1+(cols-50.)*.06
    arrays, report = prepare_td_initialization(base, base, base+100., np.zeros_like(base),
        source_origin_xz=[0., 0.], source_spacing_m=5., mouth_xz=[250., 250.], direction_xz=[0., 1.],
        shape=(41, 41), spacing_m=5., stub_length_m=20., stub_width_m=20.)
    bed, types = arrays["initial_bed_m"], arrays["cell_type"]
    edge = arrays["fixed_boundary_mask"]
    stub = arrays["inlet_stub_mask"]
    np.testing.assert_array_equal(arrays["initial_depth_m"], np.maximum(arrays["initial_stage_m"]-bed, 0.))
    assert np.all(bed[types == 1] == -1.5)
    assert np.all(bed[(types == -1)] < 0.)
    assert np.all(bed[(types == -2)] >= 0.)
    assert not np.any((types == -2) & ~edge)
    assert np.count_nonzero((bed >= 0.) & ~edge & (types == 0)) > 0
    np.testing.assert_array_equal(bed[~stub], arrays["source_base_bed_m"][~stub])
    np.testing.assert_array_equal(arrays["source_floor_m"][edge], bed[edge])
    np.testing.assert_allclose(arrays["local_world_xz_m"][4, 20], [250., 250.])
    assert report["marine_boundary_cells"]["upstream"] > 0
    assert report["marine_boundary_cells"]["left"] > 0
    assert report["marine_boundary_cells"]["downstream"] > 0
