import copy

import numpy as np
import pytest

from terrain_pipeline.channel_geometry import turn_penalty
from terrain_pipeline.delta_network_path_refinement import _intersects, _resample, _sample, refine_graph
from terrain_pipeline.delta_network_sections import rasterize_channels
from terrain_pipeline.delta_network_site import SiteSpec
from terrain_pipeline.delta_network_skeleton import DeltaGraph, DeltaParams, edge_points, solve_flow, validate_graph


def _graph(branches=True):
    graph = DeltaGraph()
    graph.params = DeltaParams(q_total=100.0)
    if branches:
        graph.node_uv = np.array([[300., 1500.], [2000., 1500.], [5700., 2400.], [5700., 600.]])
        graph.edge_from = np.array([0, 1, 1])
        graph.edge_to = np.array([1, 2, 3])
        graph.node_kind = np.array([0, 2, 5, 5])
        graph.mouth_nodes = np.array([2, 3])
        fractions = [1., .6, .4]
        graph.edge_w = np.array([150., 110., 90.])
    else:
        graph.node_uv = np.array([[300., 1500.], [5700., 1500.]])
        graph.edge_from = np.array([0])
        graph.edge_to = np.array([1])
        graph.node_kind = np.array([0, 5])
        graph.mouth_nodes = np.array([1])
        fractions = [1.]
        graph.edge_w = np.array([150.])
    graph.node_q, graph.edge_q, graph.edge_frac, graph.topo = solve_flow(
        len(graph.node_uv), graph.edge_from, graph.edge_to, fractions, graph.params.q_total, 0)
    graph.edge_h = np.ones(len(graph.edge_from))
    graph.edge_level = np.zeros(len(graph.edge_from), int)
    graph.edge_lobe = np.zeros(len(graph.edge_from), int)
    graph.edge_kind = np.zeros(len(graph.edge_from), int)
    paths = [np.linspace(graph.node_uv[start], graph.node_uv[end], 19)
             for start, end in zip(graph.edge_from, graph.edge_to)]
    graph.pt_off = np.r_[0, np.cumsum([len(path) for path in paths])]
    graph.pts_uv = np.vstack(paths)
    graph.edge_len = np.array([np.linalg.norm(np.diff(path, axis=0), axis=1).sum() for path in paths])
    assert validate_graph(graph)['ok']
    return graph


@pytest.fixture
def site():
    spec = SiteSpec(u0_m=0., v0_m=0., nu=120, nv=60, spacing_m=50.)
    return spec, np.zeros((120, 60)), np.zeros((120, 60)), np.zeros((120, 60), bool)


def test_frozen_graph_is_independent_and_topology_endpoints_and_junction_turns_survive(site):
    graph = _graph()
    original = copy.deepcopy(vars(graph))
    refined, report = refine_graph(graph, *site)
    assert report['accepted_reaches'] > 0
    assert report['validation']['ok']
    assert report['final_crossing_pairs'] == []
    for name, values in original.items():
        if isinstance(values, np.ndarray):
            assert np.array_equal(getattr(graph, name), values), name
            if name not in ('pts_uv', 'pt_off', 'edge_len'):
                assert np.array_equal(getattr(refined, name), values), name
                assert not np.shares_memory(getattr(refined, name), getattr(graph, name))
    for index in range(len(graph.edge_from)):
        before, after = edge_points(graph, index), edge_points(refined, index)
        assert np.array_equal(after[[0, -1]], before[[0, -1]])
        for old, new in ((before[1] - before[0], after[1] - after[0]),
                         (before[-1] - before[-2], after[-1] - after[-2])):
            assert np.allclose(old / np.linalg.norm(old), new / np.linalg.norm(new))
        directions = np.diff(after, axis=0)
        assert all(np.isfinite(turn_penalty(a, b)) for a, b in zip(directions[:-1], directions[1:]))


def test_repeatability_and_explicit_seed_variation(site):
    graph = _graph(False)
    first, report = refine_graph(graph, *site, seed=20260903)
    repeated, repeated_report = refine_graph(graph, *site, seed=20260903)
    other, _ = refine_graph(graph, *site, seed=20260904)
    assert np.array_equal(first.pts_uv, repeated.pts_uv)
    assert report == repeated_report
    assert not np.array_equal(first.pts_uv, other.pts_uv)
    # Restrained bends contain changing curvature, with no new sharp corners.
    assert 1.0 < report['reaches'][0]['max_displacement_m'] <= 380.
    assert report['validation']['max_turn_deg'] < 45.


def test_protected_source_hill_uses_reach_width_clearance(site):
    spec, surface, source, ocean = site
    source[:, 35:] = 65.0
    surface[:] = source
    graph = _graph(False)
    graph.edge_w[:] = 300.
    refined, report = refine_graph(graph, spec, surface, source, ocean)
    assert report['accepted_reaches'] == 1
    after = report['reaches'][0]['after']
    assert after['protected_conflict_length_m'] == 0.
    assert after['protected_max_intrusion_m'] == 0.
    # The hill starts at v=1750. Its cell footprint remains outside the
    # 150 m half width of the entire centreline, including interpolated bends.
    assert np.max(refined.pts_uv[:, 1]) + 150. < 1750.
    assert source.max() == 65.0


def test_inherited_hill_conflict_reduces_without_forcing_arbitrary_crossing(site):
    spec, surface, source, ocean = site
    source[45:62, 29:34] = 65.
    surface[:] = source
    graph = _graph(False)
    refined, report = refine_graph(graph, spec, surface, source, ocean)
    change = report['reaches'][0]
    assert change['accepted']
    assert change['after']['high_bed_cost'] < change['before']['high_bed_cost']
    assert change['after']['protected_conflict_length_m'] < change['before']['protected_conflict_length_m']
    assert report['validation']['ok']
    assert np.array_equal(refined.node_uv, graph.node_uv)


def test_crossing_detection_allows_only_shared_endpoint_contacts():
    base = np.array([[0., 0.], [1., 0.], [2., 0.]])
    assert _intersects(base, np.array([[1., -1.], [1., 1.]]))
    assert not _intersects(base, np.array([[2., 0.], [3., 1.]]))
    assert _intersects(base, np.array([[2., 0.], [1.5, 0.]]))
    loop = np.array([[0., 0.], [2., 2.], [0., 2.], [2., 0.]])
    assert _intersects(loop, loop, same=True)


def test_close_parallel_branches_do_not_acquire_crossings(site):
    graph = _graph()
    graph.node_uv[2:, 1] = [1580., 1420.]
    paths = [np.linspace(graph.node_uv[start], graph.node_uv[end], 19)
             for start, end in zip(graph.edge_from, graph.edge_to)]
    graph.pts_uv = np.vstack(paths)
    graph.edge_len = np.array([np.linalg.norm(np.diff(path, axis=0), axis=1).sum() for path in paths])
    refined, report = refine_graph(graph, *site)
    assert report['accepted_reaches'] > 0
    assert report['final_crossing_pairs'] == []
    assert not _intersects(edge_points(refined, 1), edge_points(refined, 2))
    assert validate_graph(refined)['ok']


def test_high_source_bed_below_protection_threshold_is_still_avoided(site):
    spec, surface, source, ocean = site
    source[45:62, 29:34] = 35.
    surface[:] = source
    _, report = refine_graph(_graph(False), spec, surface, source, ocean)
    change = report['reaches'][0]
    assert change['accepted']
    assert change['after']['high_bed_cost'] < change['before']['high_bed_cost']
    assert change['after']['protected_conflict_length_m'] == 0.


def test_invalid_grid_or_nonfinite_source_is_rejected_before_edit(site):
    spec, surface, source, ocean = site
    graph = _graph(False)
    before = graph.pts_uv.copy()
    source[10, 10] = np.nan
    with pytest.raises(ValueError, match='finite surfaces'):
        refine_graph(graph, spec, surface, source, ocean)
    assert np.array_equal(before, graph.pts_uv)


def test_low_endpoints_route_around_interior_35m_island_with_native_cell_tangents():
    spec = SiteSpec(u0_m=0., v0_m=0., nu=200, nv=100, spacing_m=30.)
    surface = np.ones((200, 100))
    surface[75:104, 47:53] = 35.
    source = surface.copy()
    ocean = np.zeros_like(source, bool)
    graph = _graph(False)
    refined, report = refine_graph(graph, spec, surface, source, ocean)
    assert report['lowland_repairs'] == 1
    assert report['remaining_lowland_blockers'] == []
    samples = _resample(refined.pts_uv, 5.)
    assert _sample(surface, samples, spec, order=0).max() <= 10.
    assert report['validation']['max_turn_deg'] < 45.
    assert report['final_crossing_pairs'] == []
    assert np.array_equal(refined.pts_uv[[0, -1]], graph.pts_uv[[0, -1]])
    assert np.allclose(np.diff(refined.pts_uv[:2], axis=0)[0] / np.linalg.norm(np.diff(refined.pts_uv[:2], axis=0)), [1., 0.])
    assert np.allclose(np.diff(refined.pts_uv[-2:], axis=0)[0] / np.linalg.norm(np.diff(refined.pts_uv[-2:], axis=0)), [1., 0.])
    sections = rasterize_channels(spec, surface, source, ocean, refined)
    assert sections['report']['blocked_centreline_cell_count'] == 0
    assert sections['report']['blocked_section_count'] == 0
    assert sections['report']['protected_source_cells_cut'] == 0
    assert np.array_equal(source, surface)


def test_impassable_lowland_barrier_is_reported_and_source_left_untouched(site):
    spec, surface, source, ocean = site
    source[45:62, :] = 35.
    surface[:] = source
    original = source.copy()
    _, report = refine_graph(_graph(False), spec, surface, source, ocean)
    assert report['remaining_lowland_blockers'] == [0]
    assert not report['reaches'][0]['lowland_repair']['accepted']
    assert np.array_equal(source, original)
