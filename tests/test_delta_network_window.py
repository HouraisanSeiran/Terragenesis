"""Finite support is configured per graph rather than by module globals."""
from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.delta_network_skeleton_v3 import DeltaParamsV3, build_delta_network_v3, validate_graph


def test_explicit_hundred_km_support_reaches_both_sides():
    params = DeltaParamsV3(variant='base', algorithm_world_seed=20260903,
        window_u_m=(-4000., 54000.), window_v_m=(-58000., 58000.),
        r_young=110000., max_lateral_m=56000., n_lobes=5, spread_deg=38.,
        r_decay=.995, share_ratio=.85, spacing_plain_m=8000., spacing_front_m=4000.,
        beta=18., step_m=400., q_total=30000., max_steps=5000, c_goal=1.6,
        c_coast=.1, forward_deg=85., fan_half_deg=85., width_a=5.2, width_b=.56,
        split_gap_factor=2.1, front_boost=1.1, min_remaining_split_m=2400.,
        min_split_len_factor=2., link_prob=.65, link_spacing_k=28.,
        link_gap_k=12., link_donor_q_min=1400.)
    graph = build_delta_network_v3(params)
    assert validate_graph(graph)['ok']
    assert np.ptp(graph.node_uv[graph.mouth_nodes, 1]) > 100000.
    assert graph.pts_uv[:, 1].min() >= params.window_v_m[0]
    assert graph.pts_uv[:, 1].max() <= params.window_v_m[1]
    assert len(graph.edge_from) - len(graph.node_uv) + 1 > 0


@pytest.mark.parametrize('overrides', [
    {'window_u_m': (0., 0.)}, {'window_v_m': (1000., -1000.)},
    {'window_u_m': (-4000., float('inf'))}, {'boundary_margin_m': -1.},
])
def test_invalid_planning_support_is_rejected(overrides):
    with pytest.raises(ValueError):
        build_delta_network_v3(replace(DeltaParamsV3(), **overrides))


def test_real_shore_and_source_field_replace_analytic_reach():
    class FlatSourceField:
        def __init__(self):
            self.calls = 0

        def sample(self, u, v):
            self.calls += 1
            return np.array([1000., 0., 0., 1., 0.])

    field = FlatSourceField()
    params = DeltaParamsV3(n_lobes=2, spacing_plain_m=6000., spacing_front_m=5000.,
        beta=30., link_prob=0., avul_first_m=4000., avul_gap_m=3000.)
    graph = build_delta_network_v3(params, field_override=field,
        shore_test=lambda u, v: u >= 10000.)
    assert field.calls > 0
    assert validate_graph(graph)['ok']
    assert len(graph.mouth_nodes) >= 2
    # The guide still has a roughly 49 km radius, but every mouth stops at
    # the supplied source shoreline. No plotting or post-hoc graph trimming.
    assert graph.node_uv[graph.mouth_nodes, 0] == pytest.approx(10000., abs=.03)
    assert graph.pts_uv[:, 0].max() <= 10000.03
