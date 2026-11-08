"""Tests for the complex delta network skeleton v2 (whole-length bifurcation/confluence, no level cap)."""
import dataclasses

import numpy as np
import pytest

from terrain_pipeline.delta_network_skeleton_v2 import (
    DeltaParamsV2, activity_profile, build_delta_network_v2, event_profile, skeleton_metrics_v2,
    validate_graph, width_of)
from terrain_pipeline.channel_geometry import turn_allowed


@pytest.fixture(scope='module')
def g():
    return build_delta_network_v2(DeltaParamsV2())


def test_hard_acceptance(g):
    rep = validate_graph(g)
    assert rep['ok']
    assert rep['max_node_conservation_error'] <= 1e-9
    assert rep['turns_ge_90deg'] == 0
    assert rep['edges_without_path_to_sea'] == 0
    assert rep['dead_end_nodes'] == 0
    for a in (g.node_uv, g.node_q, g.edge_q, g.edge_w, g.edge_h, g.pts_uv):
        assert np.isfinite(a).all()


def test_deterministic():
    a = build_delta_network_v2(DeltaParamsV2())
    b = build_delta_network_v2(DeltaParamsV2())
    for name in ('node_uv', 'edge_from', 'edge_to', 'edge_q', 'pts_uv'):
        assert np.array_equal(getattr(a, name), getattr(b, name))


def test_confluences_have_indegree_gt_1(g):
    indeg = np.bincount(g.edge_to, minlength=len(g.node_uv))
    assert (indeg > 1).sum() >= 10


def test_splits_along_whole_length(g):
    m = skeleton_metrics_v2(g)
    assert m['frac_splits_beyond_10km'] > 0.4
    assert m['frac_confluences_beyond_10km'] > 0.4
    assert m['loops'] >= 20
    assert m['max_level'] > 6                       # no level cap


def test_activity_profile_not_concentrated(g):
    u = np.arange(1000.0, 30000.0, 1000.0)
    n, _ = activity_profile(g, u)
    assert n[10:25].min() >= 3                      # still a network far from the apex


def test_scale(g):
    m = skeleton_metrics_v2(g)
    assert m['farthest_mouth_from_apex_m'] >= 30000.0


def test_width_discharge_exponent(g):
    q = g.edge_q[g.edge_q > 1.0]
    w = width_of(q, g.params)
    b = np.polyfit(np.log(q), np.log(w), 1)[0]
    assert b == pytest.approx(0.5, abs=1e-6)


def test_junction_angles_legal(g):
    out = {}
    for i in range(len(g.edge_from)):
        out.setdefault(int(g.edge_from[i]), []).append(i)
    from terrain_pipeline.delta_network_skeleton_v2 import edge_points
    for i in range(len(g.edge_to)):
        P = edge_points(g, i)
        inc = P[-1] - P[-2]
        for j in out.get(int(g.edge_to[i]), []):
            Q = edge_points(g, j)
            o = Q[1] - Q[0]
            assert turn_allowed(inc / np.hypot(*inc), o / np.hypot(*o), 90.0)


@pytest.mark.parametrize('over', [
    dict(variant='few_loops', link_prob=0.08, link_donor_q_min=2500.0, spacing_plain_m=3200.0,
         spacing_front_m=900.0, split_gap_factor=1.8),
    dict(variant='many_loops', link_prob=0.95, link_donor_q_min=300.0, spacing_plain_m=1800.0,
         spacing_front_m=550.0, split_gap_factor=1.25),
])
def test_variants_valid(over):
    gg = build_delta_network_v2(dataclasses.replace(DeltaParamsV2(), **over))
    rep = validate_graph(gg)
    assert rep['ok'] and rep['turns_ge_90deg'] == 0 and rep['max_node_conservation_error'] <= 1e-9
    su, cu = event_profile(gg)
    assert len(su) > 20 and len(cu) > 10
