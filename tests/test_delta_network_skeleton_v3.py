"""Tests for the complex delta network v3 (oblique random links, meanders, soft old-PlanConfig limits)."""
import dataclasses
import math

import numpy as np
import pytest

from terrain_pipeline.delta_network_skeleton_v3 import (
    DeltaParamsV3, EDGE_KINDS, activity_profile, build_delta_network_v3, edge_points, event_profile,
    skeleton_metrics_v3, validate_graph, width_of)
from terrain_pipeline.channel_geometry import turn_allowed


@pytest.fixture(scope='module')
def g():
    return build_delta_network_v3(DeltaParamsV3())


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
    a = build_delta_network_v3(DeltaParamsV3())
    b = build_delta_network_v3(DeltaParamsV3())
    for name in ('node_uv', 'edge_from', 'edge_to', 'edge_q', 'pts_uv'):
        assert np.array_equal(getattr(a, name), getattr(b, name))


def test_confluences_have_indegree_gt_1(g):
    indeg = np.bincount(g.edge_to, minlength=len(g.node_uv))
    assert (indeg > 1).sum() >= 10


def test_splits_along_whole_length(g):
    m = skeleton_metrics_v3(g)
    assert m['frac_splits_beyond_10km'] > 0.4
    assert m['frac_confluences_beyond_10km'] > 0.4
    assert m['loops'] >= 20
    assert m['max_level'] > 6


def test_activity_profile_not_concentrated(g):
    u = np.arange(1000.0, 30000.0, 1000.0)
    n, _ = activity_profile(g, u)
    assert n[10:25].min() >= 3


def test_scale(g):
    assert skeleton_metrics_v3(g)['farthest_mouth_from_apex_m'] >= 30000.0


def test_width_discharge_exponent(g):
    q = g.edge_q[g.edge_q > 1.0]
    b = np.polyfit(np.log(q), np.log(width_of(q, g.params)), 1)[0]
    assert b == pytest.approx(0.5, abs=1e-6)


def test_junction_angles_legal(g):
    out = {}
    for i in range(len(g.edge_from)):
        out.setdefault(int(g.edge_from[i]), []).append(i)
    for i in range(len(g.edge_to)):
        P = edge_points(g, i)
        inc = P[-1] - P[-2]
        for j in out.get(int(g.edge_to[i]), []):
            Q = edge_points(g, j)
            o = Q[1] - Q[0]
            assert turn_allowed(inc / np.hypot(*inc), o / np.hypot(*o), 90.0)


def test_links_are_oblique_and_varied(g):
    kind = EDGE_KINDS.index('link')
    ids = np.nonzero(g.edge_kind == kind)[0]
    assert len(ids) >= 5
    lens = g.edge_len[ids]
    assert lens.std() / lens.mean() > 0.2          # not a regular grid
    out = {}
    for i in range(len(g.edge_from)):
        out.setdefault(int(g.edge_from[i]), []).append(i)
    inc = {}
    for i in range(len(g.edge_to)):
        inc.setdefault(int(g.edge_to[i]), []).append(i)
    angs = []
    for i in ids:
        P = edge_points(g, int(i))
        v = P[min(2, len(P) - 1)] - P[0]
        # donor tangent: incoming edge of the link's start node that is not the link itself
        for d in inc.get(int(g.edge_from[i]), []):
            D = edge_points(g, d)
            t = D[-1] - D[-2]
            a = abs(math.degrees(math.atan2(t[0] * v[1] - t[1] * v[0], t @ v)))
            angs.append(a)
    angs = np.array(angs)
    assert len(angs) and np.median(angs) < 75.0     # clearly oblique, not perpendicular (v2 checkerboard)


@pytest.mark.parametrize('over', [
    dict(variant='few_loops', link_prob=0.5, link_donor_q_min=2500.0, link_spacing_k=22.0, link_gap_k=8.0,
         spacing_plain_m=3200.0, spacing_front_m=900.0, split_gap_factor=1.8),
    dict(variant='many_loops', link_prob=0.95, link_donor_q_min=300.0, link_spacing_k=6.0, link_gap_k=3.0,
         spacing_plain_m=1800.0, spacing_front_m=550.0, split_gap_factor=1.25),
])
def test_variants_valid(over):
    gg = build_delta_network_v3(dataclasses.replace(DeltaParamsV3(), **over))
    rep = validate_graph(gg)
    assert rep['ok'] and rep['turns_ge_90deg'] == 0 and rep['max_node_conservation_error'] <= 1e-9
    su, cu = event_profile(gg)
    assert len(su) > 20 and len(cu) > 10
