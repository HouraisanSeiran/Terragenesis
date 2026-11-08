"""Exported geometry, rather than a new stochastic realization, drives LOD."""

import json
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline.delta_network_frozen import load_graph, topology_identity


BASE = Path(__file__).resolve().parents[1] / ".scratch/delta-completion-20261107/source-controlled-v5-100m-r3/base"


@pytest.fixture
def saved():
    if not BASE.exists():
        pytest.skip("optional immutable TD acceptance product not available")
    return json.loads((BASE / "channel_graph.json").read_text(encoding="utf-8"))


def test_frozen_reader_preserves_every_path_node_and_parallel_arm(saved):
    graph = load_graph(BASE)
    assert len(graph.edge_from) == len(saved["edges"])
    for edge in saved["edges"]:
        start, end = graph.pt_off[edge["id"]:edge["id"] + 2]
        assert np.array_equal(graph.pts_uv[start:end], edge["path_uv_m"])
        assert graph.edge_w[edge["id"]] == edge["width_m"]
        assert graph.edge_q[edge["id"]] == edge["Q_m3s"]
    assert np.array_equal(graph.node_uv, [[node["u_m"], node["v_m"]] for node in saved["nodes"]])


def test_frozen_reader_never_calls_growth_and_repeats_exactly(saved, monkeypatch):
    from terrain_pipeline import delta_network_skeleton_v3 as skeleton

    def forbidden(*args, **kwargs):
        raise AssertionError("loading frozen geometry must not call stochastic growth")

    monkeypatch.setattr(skeleton, "build_delta_network_v3", forbidden)
    first, second = load_graph(BASE), load_graph(BASE)
    assert topology_identity(first) == topology_identity(second)
    assert np.array_equal(first.pts_uv, second.pts_uv)


def test_exported_width_profile_is_consumed_by_existing_hydraulic_accounts():
    from types import SimpleNamespace
    from terrain_pipeline.delta_network_coupling import _accounts

    graph = dict(nodes=[dict(id=0, u_m=15.0, v_m=15.0), dict(id=1, u_m=315.0, v_m=15.0)],
                 edges=[dict(id=0, **{"from": 0, "to": 1}, width_m=80.0,
                             path_uv_m=[[15.0, 15.0], [115.0, 15.0], [215.0, 15.0], [315.0, 15.0]],
                             width_profile_m=[80.0, 50.0, 25.0, 10.0])])
    state = SimpleNamespace(origin_xz_m=(5.0, 5.0), spacing_m=10.0,
                            base_bed_m=np.empty((40, 10)), valid_mask=np.ones((40, 10), bool))
    routes, coordinates, widths = _accounts(graph, state, 100.0, 0.0)
    assert [widths[cell] for cell in routes[0]] == [80.0, 50.0, 25.0, 10.0]
