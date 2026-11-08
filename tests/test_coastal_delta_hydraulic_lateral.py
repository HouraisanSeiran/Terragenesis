"""Physical node lateral exchanges preserve river edge and mouth continuity."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from terrain_pipeline import coastal_delta_graph_hydraulics as hydraulics
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig


def fixture(discharge=20., stage_limit=4.):
    inlet, split = (0, 2), (1, 2)
    left, right = (2, 1), (2, 3)
    left_mouth, right_mouth = (3, 1), (3, 3)
    routes = [[inlet, split, left, left_mouth], [inlet, split, right, right_mouth]]
    sections = {n: (-1., 24., .035) for route in routes for n in route}
    progress = dict(routes=routes, discharge_m3_s=discharge,
                    hydraulic_sections=dict(nodes=[[*n, -1., 24., .035, 1.] for n in sections]))
    return SimpleNamespace(spacing_m=10.), progress, HydraulicConfig(stage_limit), sections, [True, True]


def solve(arguments):
    state, progress, config, sections, faces = arguments
    return hydraulics.solve_graph(state, progress, 0., config, sections, faces)


def assert_balance(result):
    sink = {tuple(row[:2]): row[2] for row in result['lateral_sink_q_m3_s']}
    source = {tuple(row[:2]): row[2] for row in result['lateral_source_q_m3_s']}
    mouth = {tuple(row[:2]): row[2] for row in result['mouth_q_m3_s']}
    edges = {(tuple(row[:2]), tuple(row[2:4])): row[4] for row in result['edge_q_m3_s']}
    inlet = (0, 2)
    for row in result['nodes']:
        node = tuple(row[:2])
        incoming = sum(q for (a, b), q in edges.items() if b == node)
        outgoing = sum(q for (a, b), q in edges.items() if a == node)+mouth.get(node, 0.)
        expected = incoming+source.get(node, 0.)
        if node == inlet:
            expected += result['accepted_q_m3_s']
        assert outgoing+sink.get(node, 0.) == pytest.approx(expected, abs=2e-6)
        assert row[4] == pytest.approx(outgoing+sink.get(node, 0.), abs=1e-12)
    assert result['max_node_residual_m3_s'] < 2e-6
    assert abs(result['lateral_water_balance_residual_m3_s']) < 2e-6


def test_absent_exchange_keeps_existing_output_and_empty_exchange_is_numerically_identical():
    args = fixture()
    previous = solve(args)
    assert not any(key.startswith('lateral_') for key in previous)
    args[1]['river_lateral_exchange'] = {}
    empty = solve(args)
    for key, value in previous.items():
        assert empty[key] == value
    assert empty['lateral_sink_q_m3_s'] == []
    assert empty['lateral_source_q_m3_s'] == []
    assert_balance(empty)


@pytest.mark.parametrize('sparse', [False, True])
@pytest.mark.parametrize('exchange', [
    {'sink_fraction': [[2, 1, .1]]},
    {'source_q_m3_s': [[2, 1, 3.]]},
    {'sink_fraction': [[2, 1, .1], [1, 2, .05]], 'source_q_m3_s': [[2, 1, 3.]]},
])
def test_local_sink_return_and_combined_exchange_balance(exchange, sparse, monkeypatch):
    monkeypatch.setattr(hydraulics, 'SPARSE_NODE_THRESHOLD', 1 if sparse else 128)
    args = fixture()
    baseline = solve(args)
    if sparse:
        args[1]['river_hydraulics'] = baseline
    args[1]['river_lateral_exchange'] = exchange
    result = solve(args)
    assert result['accepted_q_m3_s'] == 20.
    assert_balance(result)
    original_mouths = {tuple(row[:2]): row[2] for row in baseline['mouth_q_m3_s']}
    mouths = {tuple(row[:2]): row[2] for row in result['mouth_q_m3_s']}
    if 'source_q_m3_s' not in exchange:
        assert mouths[(3, 1)] < original_mouths[(3, 1)]
        assert sum(mouths.values()) == pytest.approx(18., abs=2e-6)
        edges = {(tuple(row[:2]), tuple(row[2:4])): row[4] for row in result['edge_q_m3_s']}
        assert edges[((1, 2), (2, 1))]-edges[((2, 1), (3, 1))] == pytest.approx(2., abs=2e-6)
    if 'sink_fraction' not in exchange:
        assert mouths[(3, 1)] > original_mouths[(3, 1)]
        assert sum(mouths.values()) == pytest.approx(23., abs=2e-6)
    assert result['numerical_linearization'] == ('analytic sparse Jacobian' if sparse else 'dense finite differences')


@pytest.mark.parametrize('node', [[0, 2], [3, 1]])
def test_lateral_exchange_at_inlet_and_mouth_uses_the_same_node_balance(node):
    args = fixture()
    args[1]['river_lateral_exchange'] = {
        'sink_fraction': [[*node, .2]], 'source_q_m3_s': [[*node, 2.]]}
    result = solve(args)
    assert result['lateral_sink_q_m3_s'] == [[*node, 4.]]
    assert sum(row[2] for row in result['mouth_q_m3_s']) == pytest.approx(18., abs=2e-6)
    assert_balance(result)


@pytest.mark.parametrize('exchange', [
    None, [], {'unknown': []}, {'sink_fraction': None},
    {'sink_fraction': [[2, 1]]}, {'source_q_m3_s': [[2, 1, 0., 0.]]},
    {'sink_fraction': [[2, 1, -.01]]}, {'source_q_m3_s': [[2, 1, -1.]]},
    {'sink_fraction': [[2, 1, np.nan]]}, {'source_q_m3_s': [[2, 1, np.inf]]},
    {'sink_fraction': [[2, 1, .1], [2, 1, .1]]},
    {'source_q_m3_s': [[2, 1, 1.], [2, 1, 1.]]},
    {'sink_fraction': [[2, 1, .11], [2, 3, .1]]},
    {'source_q_m3_s': [[2.5, 1, 1.]]},
    {'sink_fraction': [[9, 9, 0.]]}, {'source_q_m3_s': [[9, 9, 1.]]},
])
def test_invalid_exchange_is_rejected_without_mutating_progress(exchange):
    args = fixture()
    args[1]['river_lateral_exchange'] = exchange
    before = deepcopy(args[1])
    with pytest.raises(ValueError, match='lateral'):
        solve(args)
    # Deep equality cannot compare the intentional NaN input.
    assert repr(args[1]) == repr(before)


@pytest.mark.parametrize('field', ['sink_fraction', 'source_q_m3_s'])
@pytest.mark.parametrize('blocked', ['sill', 'face', 'sea'])
def test_exchange_at_inactive_or_unreachable_node_is_rejected(field, blocked):
    state, progress, config, sections, faces = fixture()
    if blocked == 'sill':
        sections[(2, 1)] = (config.upstream_stage_limit_m, 24., .035)
    elif blocked == 'face':
        faces[0] = False
    progress['river_lateral_exchange'] = {field: [[3, 1, .1]]}
    with pytest.raises(ValueError, match='reachable active node'):
        hydraulics.solve_graph(state, progress, 4. if blocked == 'sea' else 0., config, sections, faces)


@pytest.mark.parametrize('sparse', [False, True])
def test_stage_limited_inlet_scales_sink_and_preserves_absolute_return(sparse, monkeypatch):
    monkeypatch.setattr(hydraulics, 'SPARSE_NODE_THRESHOLD', 1 if sparse else 128)
    args = fixture(discharge=1000., stage_limit=.05)
    args[1]['river_lateral_exchange'] = {
        'sink_fraction': [[2, 1, .1]], 'source_q_m3_s': [[2, 3, 1.]]}
    result = solve(args)
    assert 0. < result['accepted_q_m3_s'] < 1000.
    assert result['lateral_sink_q_m3_s'][0][2] == pytest.approx(result['accepted_q_m3_s']*.1)
    assert result['lateral_source_q_m3_s'] == [[2, 3, 1.]]
    assert_balance(result)
