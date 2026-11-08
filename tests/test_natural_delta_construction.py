"""Behavioral contracts of the prescribed natural construction geometry."""
import numpy as np
import pytest
from shapely.geometry import LineString

from terrain_pipeline.channel_geometry import construct_mouth_transitions, derived_seed, natural_distributary_geometry, natural_secondary
from terrain_pipeline.surface_rivers.metric_coast_bounded_delta import truncate_at_first_marine


@pytest.mark.parametrize('angle', [0., .7853981634])
def test_seeded_paths_repeat_vary_and_start_downstream_without_crossings(angle):
    trunk = np.column_stack([np.linspace(0., 500., 121), np.zeros(121)])
    trunk[:, 1] = 45.*np.sin(np.linspace(0., 1.5, len(trunk)))
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    trunk = trunk@rotation.T
    first = natural_distributary_geometry(trunk, 20261020)
    repeated = natural_distributary_geometry(trunk, 20261020)
    changed = natural_distributary_geometry(trunk, 20261021)
    for a, b in zip(first, repeated):
        np.testing.assert_array_equal(a, b)
    assert not np.array_equal(first[1], changed[1])
    assert derived_seed(20261020, 'branch') != derived_seed(20261020, 'island')
    new_trunk, branches, splits = first
    assert len(np.unique(splits)) == 4
    for branch in branches:
        direction = new_trunk[-1]-new_trunk[-8]
        assert np.all(np.diff(branch@direction) > 0.)
        index = np.argmin(np.linalg.norm(new_trunk-branch[0], axis=1))
        tangent = new_trunk[min(index+1, len(new_trunk)-1)]-new_trunk[max(index-1, 0)]
        child = branch[1]-branch[0]
        cosine = child@tangent/np.linalg.norm(child)/np.linalg.norm(tangent)
        assert cosine > .999
    for index, branch in enumerate(branches):
        for other in branches[index+1:]:
            assert not LineString(branch).intersects(LineString(other))
    for index, branch in enumerate(changed[1]):
        for other in changed[1][index+1:]:
            assert not LineString(branch).intersects(LineString(other))


def test_curved_incoming_regression_keeps_distributaries_separate():
    points = np.array([[0., 0.], [30.117, 58.271], [61.082, 115.695],
        [93.665, 171.5], [128.493, 225.061], [165.989, 275.953],
        [206.345, 323.985], [249.511, 369.207], [295.208, 411.899]])
    trunk = np.column_stack([np.interp(np.linspace(0., 8., 121), np.arange(9), points[:, axis]) for axis in range(2)])
    for seed in [20261020, 20261021]:
        _, branches, _ = natural_distributary_geometry(trunk, seed)
        for index, branch in enumerate(branches):
            assert LineString(branch).is_simple
            for other in branches[index+1:]:
                assert not LineString(branch).intersects(LineString(other))


def test_secondary_inherits_parent_tangent_and_has_distinct_outlet():
    trunk = np.column_stack([np.linspace(0., 500., 121), np.zeros(121)])
    _, branches, _ = natural_distributary_geometry(trunk, 20261020)
    origin = np.array([-500., -7000.])
    marine = np.zeros((1400, 900), bool)
    marine[:, 450:] = True
    secondary, reason = natural_secondary(branches[0], marine, origin, 10., 20261020)
    assert reason['reason'] == 'selected'
    parent, _ = truncate_at_first_marine(branches[0], marine, origin, 10.)
    child, _ = truncate_at_first_marine(secondary, marine, origin, 10.)
    assert np.linalg.norm(parent[-1]-child[-1]) > 200.
    index = np.argmin(np.linalg.norm(branches[0]-child[0], axis=1))
    tangent = branches[0][index+1]-branches[0][index-1]
    heading = child[1]-child[0]
    assert heading@tangent/np.linalg.norm(heading)/np.linalg.norm(tangent) > .999
    along = np.linspace(child[0, 0]+100., min(child[-1, 0], parent[-1, 0]), 500)
    separation = np.interp(along, parent[:, 0], parent[:, 1])-np.interp(along, child[:, 0], child[:, 1])
    assert np.all(separation > 0.)


def test_natural_terminal_is_inside_first_marine_cell_for_nearest_cell_sampling():
    marine = np.zeros((9, 30), bool)
    marine[:, 9:14] = True
    marine[:, 21:] = True
    path = np.array([[2., 4.], [27., 4.]])
    result, _ = truncate_at_first_marine(path, marine, np.zeros(2), 1.,
        sample_count=101, terminal_inside_cell=True)
    nearest = np.rint(result).astype(int)
    ownership = np.floor(result+.5).astype(int)
    np.testing.assert_array_equal(nearest[-1], ownership[-1])
    assert nearest[-1, 0] == 9
    assert not marine[ownership[:-1, 1], ownership[:-1, 0]].any()
    assert marine[ownership[-1, 1], ownership[-1, 0]]


def test_initial_mouth_excavation_is_finite_and_joins_channel_to_existing_sea():
    bed = np.full((61, 91), .5)
    bed[:, 30:] = -.01
    marine = bed < 0.
    candidate = np.column_stack([np.linspace(10., 80., 301), np.full(301, 30.)])
    path = np.column_stack([np.linspace(10., 30., 101), np.full(101, 30.)])
    constructed, support = construct_mouth_transitions(bed, marine, [candidate], [path],
        [0.], [8.], -2., np.zeros(2), 1., transition_length_m=20.)
    np.testing.assert_array_equal(constructed[~marine], bed[~marine])
    np.testing.assert_array_equal(constructed[:, 51:], bed[:, 51:])
    assert constructed[30, 30] < -2.
    assert constructed[30, 40] < -.5
    assert constructed[30, 50] == bed[30, 50]
    np.testing.assert_array_equal(support, constructed < bed)
    assert np.all(constructed <= bed)
