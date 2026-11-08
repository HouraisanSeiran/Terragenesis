import numpy as np
from terrain_pipeline.new_world_game_connectivity import audit_edges


def test_short_crossing_and_downstream_blocker():
    bed = np.array([[0., 10., 0.], [0., 0., 0.]])
    ocean = np.zeros_like(bed, dtype=bool)
    ocean[0, 1] = True
    # Segment crosses a tiny corner of the high/ocean cell between endpoints.
    x = np.array([0., 2.]); z = np.array([0., .51])
    result = audit_edges(bed, ocean, x, z, [0], [1], origin_m=0., spacing_m=1.)
    assert result['max_rise_m'][0] == 10
    assert result['blocker_row_col'][0].tolist() == [0, 1]
    assert result['ocean_crossing'][0]
    assert not result['ocean_at_target'][0]


def test_nonincreasing_and_reversed_profile():
    bed = np.array([[3., 2., 1.]])
    ocean = np.zeros_like(bed, dtype=bool)
    x = np.array([0., 2.]); z = np.array([0., 0.])
    r = audit_edges(bed, ocean, x, z, [0, 1], [1, 0], origin_m=0., spacing_m=1.)
    np.testing.assert_array_equal(r['max_rise_m'], [0., 2.])
    np.testing.assert_array_equal(r['max_step_m'], [0., 1.])
    np.testing.assert_array_equal(r['blocker_row_col'][1], [0, 0])
