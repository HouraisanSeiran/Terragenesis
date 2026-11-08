from dataclasses import replace
import runpy
import pytest
from terrain_pipeline.coastal_delta_branching import mouth_exterior_faces
from terrain_pipeline.coastal_delta_graph_hydraulics import solve_graph
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig

fixtures = runpy.run_path('tests/test_coastal_delta_hydraulics.py')

def run(state, progress, width=30., limit=10.):
    progress = fixtures['section_progress'](state, progress, width)
    config = HydraulicConfig(limit)
    sections = {(r[0], r[1]): (r[2], r[3], config.roughness) for r in progress['hydraulic_sections']['nodes']}
    return solve_graph(state, progress, 0., config, sections, mouth_exterior_faces(state, progress, sea_level_m=0.))

def test_bypass_and_multiple_mouths():
    state, progress = fixtures['fixture']()
    narrow, wide = run(state, progress, 10.), run(state, progress, 80.)
    for result in (narrow, wide):
        assert result['accepted_q_m3_s'] == 30.
        assert sum(row[2] for row in result['mouth_q_m3_s']) == pytest.approx(30., rel=1e-4)
        assert result['max_node_residual_m3_s'] < .003
    assert narrow['nodes'][0][2] > wide['nodes'][0][2]
    assert wide['nodes'][0][2] < .05
    edge = {(r[0],r[1],r[2],r[3]):r[4] for r in wide['edge_q_m3_s']}
    assert edge[4,5,4,6] < .003

def test_blocked_and_capacity():
    state, progress = fixtures['fixture']()
    bed = state.base_bed_m.copy(); bed[4,2] = 10.
    blocked = run(replace(state, base_bed_m=bed), progress, 10., 4.)
    assert blocked['physical_blocked'] and blocked['accepted_q_m3_s'] == 0.
    limited = run(state, progress, 1., .5)
    assert 0 < limited['accepted_q_m3_s'] < 30.
    assert limited['nodes'][0][2] <= .5

def test_two_rejoins_cover_order():
    state, progress = fixtures['fixture']()
    upper = [[4,0],[4,1],[3,2],[3,3],[4,4],[4,5],[3,6],[3,7],[4,8],[4,9],[4,10],[4,11]]
    lower = [[4,0],[4,1],[5,2],[5,3],[4,4],[4,5],[5,6],[5,7],[4,8],[4,9],[4,10],[4,11]]
    p = dict(progress, routes=[upper, lower])
    a = run(state, p)
    p['routes'] = [lower[:6]+upper[6:], upper[:6]+lower[6:], lower, upper]
    b = run(state, p)
    assert a['accepted_q_m3_s'] == b['accepted_q_m3_s'] == 30.
    assert [r[:4] for r in a['edge_q_m3_s']] == [r[:4] for r in b['edge_q_m3_s']]
    assert [r[4] for r in a['edge_q_m3_s']] == pytest.approx([r[4] for r in b['edge_q_m3_s']], rel=1e-4)
    nodes = {(r[0],r[1]):r for r in a['nodes']}
    for cell in ((4,0),(4,4),(4,8),(4,11)):
        assert nodes[cell][4] == pytest.approx(30., rel=1e-4)


def test_analytic_sparse_jacobian_matches_dense_with_rejoins(monkeypatch):
    import terrain_pipeline.coastal_delta_graph_hydraulics as graph_solver
    state,progress=fixtures['fixture']()
    dense=run(state,progress)
    monkeypatch.setattr(graph_solver,'SPARSE_NODE_THRESHOLD',0)
    sparse=run(state,progress)
    assert sparse['accepted_q_m3_s']==dense['accepted_q_m3_s']
    assert [r[4] for r in sparse['edge_q_m3_s']]==pytest.approx(
        [r[4] for r in dense['edge_q_m3_s']],rel=1e-4,abs=.0001)
    assert [r[2] for r in sparse['mouth_q_m3_s']]==pytest.approx(
        [r[2] for r in dense['mouth_q_m3_s']],rel=1e-4,abs=.0001)
    assert sparse['max_node_residual_m3_s']<.003
