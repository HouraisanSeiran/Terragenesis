import numpy as np
import pytest

from terrain_pipeline.channel_geometry import heading_path, turn_penalty
from terrain_pipeline.coastal_delta_routes import irregular_valley_path


def heading(angle):
    return np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))])


def test_hyperbolic_turn_penalty_boundaries_and_growth():
    assert turn_penalty(heading(0), heading(45)) == pytest.approx(0., abs=1e-12)
    assert turn_penalty(heading(0), heading(20)) == 0.
    multipliers = [1+turn_penalty(heading(0), heading(a)) for a in (60, 75, 85, 89)]
    assert multipliers == pytest.approx([1.5, 3., 9., 45.])
    assert np.all(np.diff(multipliers) > 0)
    assert np.isinf(turn_penalty(heading(0), heading(90)))
    assert np.isinf(turn_penalty(heading(0), heading(120)))
    assert turn_penalty(heading(0), heading(60), 2.) == pytest.approx(1.)
    for k in (-1., np.nan, np.inf):
        with pytest.raises(ValueError):
            turn_penalty(heading(0), heading(0), k)
    with pytest.raises(ValueError):
        turn_penalty([0., 0.], [1., 0.])


def test_edge_state_retains_more_expensive_arrival_for_legal_exit():
    # Cheapest arrival at junction 3 heads west and cannot turn east to 4.
    # A node-only shortest path would discard the legal arrival from node 2.
    points = np.array([[0., 0.], [2., 0.], [3., 1.], [3., 2.],
                       [2., 3.], [1., 3.], [0., 3.], [0., 1.], [1., 4.]])
    sources = np.array([0, 1, 2, 3, 4, 5, 0, 7, 6])
    ends = np.array([1, 2, 3, 4, 5, 6, 7, 6, 8])
    cost = np.array([1., 1., 1., 1., 1., 1., 5., 5., 1.])
    path = heading_path(sources, ends, cost, points, 0, [8], max_turn_deg=90.)
    assert path.tolist() == [0, 7, 6, 8]
    assert heading_path(sources, ends, cost, points, 0, [8], max_turn_deg=90.,
                        end_directions=[[-1., 0.]]) is None


def test_actual_irregular_path_enforces_endpoint_and_interior_turns():
    bed = np.zeros((10, 10)); valid = np.ones_like(bed, bool)
    cells, points = irregular_valley_path(bed, valid, (2, 2), (7, 7), 1., 100.,
        world_seed=42, max_turn_deg=90., start_directions_xz=[[1., 0.]],
        end_directions_xz=[[0., 1.]])
    assert tuple(cells[0]) == (2, 2) and tuple(cells[-1]) == (7, 7)
    vectors = np.vstack(([1., 0.], np.diff(points, axis=0), [0., 1.]))
    assert all(np.isfinite(turn_penalty(a, b)) for a, b in zip(vectors, vectors[1:]))


def test_penalty_prefers_longer_gentle_legal_route():
    # The cheap branch turns 75 degrees at node 1; the other turns 30.
    points = np.array([[0., 0.], [1., 0.], [1., -1.],
                       [1.+np.cos(np.radians(75)), np.sin(np.radians(75))],
                       [1.+np.cos(np.radians(-15)), -1.+np.sin(np.radians(-15))]])
    sources = np.array([0, 1, 0, 2]); ends = np.array([1, 3, 2, 4])
    cost = np.array([1., 1., 1.2, 1.2])
    without = heading_path(sources, ends, cost, points, 0, [3, 4], max_turn_deg=90., turn_penalty_k=0.)
    penalized = heading_path(sources, ends, cost, points, 0, [3, 4], max_turn_deg=90., turn_penalty_k=1.)
    assert without.tolist() == [0, 1, 3]
    assert penalized.tolist() == [0, 2, 4]
