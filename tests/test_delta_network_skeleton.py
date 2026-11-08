import dataclasses

import numpy as np
import pytest

from terrain_pipeline.delta_network_site import derive_seed
from terrain_pipeline.delta_network_skeleton import (
    DeltaParams, build_delta_network, edge_points, skeleton_metrics, solve_flow, validate_graph, width_of)
from terrain_pipeline.channel_geometry import turn_allowed


@pytest.fixture(scope='module')
def graph():
    return build_delta_network(DeltaParams())


def test_seed_derivation_is_stable_and_purpose_specific():
    assert derive_seed('delta-network/growth', 'base') == derive_seed('delta-network/growth', 'base')
    assert derive_seed('delta-network/growth', 'base') != derive_seed('delta-network/lobes', 'base')
    assert derive_seed('delta-network/growth', 'base') != derive_seed('delta-network/growth', 'other')


def test_hard_acceptance(graph):
    rep = validate_graph(graph)
    assert rep['ok']
    assert rep['max_node_conservation_error'] <= 1e-9
    assert rep['edges_without_path_to_sea'] == 0
    assert rep['turns_ge_90deg'] == 0 and rep['turns_not_allowed'] == 0
    assert rep['nan_count'] == 0 and rep['dead_end_nodes'] == 0


def test_flow_sums_to_total_at_mouths(graph):
    assert graph.node_q[graph.mouth_nodes].sum() == pytest.approx(graph.params.q_total, abs=1e-6)


def test_loops_levels_and_hydraulic_geometry(graph):
    m = skeleton_metrics(graph)
    assert m['components'] == 1
    assert m['loops'] >= 3                      # confluences / links close cycles
    assert m['n_mouths'] >= 5
    assert m['max_level'] >= 3
    assert m['width_exponent_fit'] == pytest.approx(graph.params.width_b, abs=1e-6)
    assert np.allclose(graph.edge_w, width_of(graph.edge_q, graph.params))


def test_some_node_has_in_degree_above_one(graph):
    indeg = np.bincount(graph.edge_to, minlength=len(graph.node_uv))
    assert indeg.max() >= 2


def test_every_polyline_step_is_a_legal_turn(graph):
    for i in range(len(graph.edge_from)):
        d = np.diff(edge_points(graph, i), axis=0)
        for a, b in zip(d[:-1], d[1:]):
            assert turn_allowed(a, b, 90.0)


def test_same_parameters_same_arrays():
    a = build_delta_network(DeltaParams())
    b = build_delta_network(DeltaParams())
    for name in ('node_uv', 'edge_from', 'edge_to', 'edge_q', 'pts_uv'):
        assert np.array_equal(getattr(a, name), getattr(b, name))


def test_variant_changes_network_but_still_valid():
    p = dataclasses.replace(DeltaParams(), variant='other-seed')
    g = build_delta_network(p)
    assert validate_graph(g)['ok']
    assert not np.array_equal(g.node_uv.shape, ()) and g.pts_uv.shape != ()


def test_solve_flow_conserves_on_small_dag():
    # 0 -> 1 ; 1 -> 2 (0.7), 1 -> 3 (0.3) ; 2 -> 3 ; 3 -> sea (-1) ; 2 -> sea
    frm = [0, 1, 1, 2, 2, 3]
    to = [1, 2, 3, 3, -1, -1]
    frac = [1.0, 0.7, 0.3, 0.4, 0.6, 1.0]
    qn, qe, fr, order = solve_flow(4, frm, to, frac, 100.0, 0)
    assert qe[0] == pytest.approx(100.0)
    assert qn[3] == pytest.approx(100.0 * (0.3 + 0.7 * 0.4))
    assert qe[4] + qe[5] == pytest.approx(100.0, abs=1e-12)
    assert len(order) == 4


def test_cycle_is_rejected():
    with pytest.raises(RuntimeError):
        solve_flow(3, [0, 1, 2], [1, 2, 1], [1.0, 1.0, 1.0], 10.0, 0)
