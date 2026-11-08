import numpy as np

from terrain_pipeline.new_world_game_river_detail import local_path, required_cut


def test_local_path_avoids_ocean_until_the_bound_mouth():
    bed = np.zeros((5, 5))
    ocean = np.zeros((5, 5), bool)
    ocean[1:4, 2] = True
    ocean[2, 4] = True
    path = local_path(bed, ocean, (2, 0), (2, 4), margin=2, allow_ocean_end=True)
    assert path[0] == (2, 0) and path[-1] == (2, 4)
    assert not any(ocean[cell] for cell in path[:-1])


def test_required_cut_is_cumulative_not_just_adjacent_rise():
    np.testing.assert_array_equal(required_cut([10, 8, 9, 11]), [0, 0, 1, 3])
