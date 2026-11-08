import copy
import numpy as np
import pytest

from terrain_pipeline.coastal_delta_evolution import initialize, save, load
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_delta_routes import edge_length, node_control_length, channel_area
from terrain_pipeline.coastal_marine_sediment import make_state


def setup_geometry(offset=0.):
    base = np.full((7, 9), -2.)
    seeds = np.zeros(base.shape, bool); seeds[:, -1] = True
    state = make_state(base_bed_m=base, bed_solid_m3=0., mobile_solid_m3=0.,
        porosity=.4, valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
        origin_xz_m=(0., 0.), source_identity='test')
    main = np.array([[3, c] for c in range(8)])
    branch = np.array([[3, 3], [2, 4], [2, 5], [2, 6], [2, 7]])
    xy = main[:, ::-1].astype(float)*100
    xy[1, 0] += offset
    branch_xy = branch[:, ::-1].astype(float)*100
    routes = {'main_cells_zx': main, 'main_points_xz': xy,
        'branch_cells_zx': branch, 'branch_points_xz': branch_xy,
        'branch_offsets': np.array([0, len(branch)]),
        'section_bed_m': np.full(8, -2.), 'section_bank_m': np.ones(8),
        'section_width_m': np.full(8, 15.), 'section_stage_m': np.ones(8)}
    state, p = initialize(state, routes, {'source_identity': 'test',
        'route_geometry_algorithm': 'test-v1', 'route_geometry_seed': 42}, discharge_m3_s=30.)
    return state, p, routes


def test_lengths_affect_stages_and_validate_edges():
    state, p, _ = setup_geometry()
    q = copy.deepcopy(p)
    # Move one coordinate inside its account, changing adjacent edge lengths.
    next(row for row in q['route_geometry']['nodes'] if row[:2] == [3, 1])[3] += 45
    assert edge_length(q, (3, 0), (3, 1), 100) > edge_length(p, (3, 0), (3, 1), 100)
    a = solve(state, p, 0., HydraulicConfig(20.))
    b = solve(state, q, 0., HydraulicConfig(20.))
    assert b['nodes'][0][2] > a['nodes'][0][2]
    with pytest.raises(ValueError):
        edge_length(q, (3, 0), (2, 4), 100)


def test_shared_fork_flow_and_account_area():
    state, p, _ = setup_geometry()
    branch = p['integrated']['candidate_routes'][0]
    p['routes'].append(p['routes'][0][:4] + branch[1:])
    for cell in branch[1:]:
        p['hydraulic_sections']['nodes'].append([*cell, -2., 15., 1.])
    p['shares'] = [.5, .5]
    result = solve(state, p, 0., HydraulicConfig(20.))
    nodes = {tuple(n[:2]): n for n in result['nodes']}
    assert nodes[3, 3][4] == pytest.approx(sum(result['route_q_m3_s']))
    assert node_control_length(p, (3, 3), 100) > 100
    assert channel_area(p, (3, 3), 1000, 100) == 10000


def test_initialize_geometry_cold_reload_and_conflict(tmp_path):
    state, p, routes = setup_geometry()
    save(tmp_path/'delta', state, p)
    restored, loaded = load(tmp_path/'delta')
    assert loaded['route_geometry'] == p['route_geometry']
    assert solve(restored, loaded, 0., HydraulicConfig(20.)) == solve(state, p, 0., HydraulicConfig(20.))
    routes['branch_points_xz'][0, 0] += 1
    with pytest.raises(ValueError, match='conflicting'):
        initialize(state, routes, {'source_identity': 'test', 'route_geometry_algorithm': 'test-v1', 'route_geometry_seed': 42})


def test_grid_mesh_cross_cell_edge_is_accepted_and_checks_invalid_segment():
    from dataclasses import replace
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.coastal_delta_routes import build_route_geometry
    from terrain_pipeline.channel_geometry import _segment_owner_samples

    state, _, _ = setup_geometry()
    mesh = grid_mesh(state.bed_m.shape, dx_m=100., world_seed=20260903)
    points = np.column_stack((mesh.node_x_m, mesh.node_z_m))
    found = None
    for i in range(len(points)):
        a = np.unravel_index(i, state.bed_m.shape)
        for j in mesh.indices[mesh.indptr[i]:mesh.indptr[i+1]]:
            b = np.unravel_index(j, state.bed_m.shape)
            if max(abs(a[0]-b[0]), abs(a[1]-b[1])) > 1:
                found = (i, j, a, b)
                break
        if found:
            break
    assert found is not None
    i, j, a, b = found
    xy = points[[i, j]]
    geometry = build_route_geometry(state, [[a, b]], [xy], 'mesh', 20260903)
    progress = {'route_geometry': geometry, 'routes': [[a, b]]}
    assert edge_length(progress, a, b, 100.) == pytest.approx(np.linalg.norm(xy[0]-xy[1]))
    samples = _segment_owner_samples(xy, np.zeros(2), 100.)
    owners = np.floor(samples / 100. + .5).astype(int)
    middle = next((tuple(v[::-1]) for v in owners if tuple(v[::-1]) not in (a, b)), None)
    assert middle is not None
    valid = state.valid_mask.copy(); valid[middle] = False
    with pytest.raises(ValueError, match='invalid account'):
        build_route_geometry(replace(state, valid_mask=valid), [[a, b]], [xy], 'mesh', 20260903)


def test_refresh_candidates_preserves_geometry_and_stocks():
    from terrain_pipeline.coastal_delta_avulsion import propose_candidates
    state, progress, _ = setup_geometry()
    state2, updated, report = propose_candidates(state, progress, hydraulic_config=HydraulicConfig(20.))
    assert len(updated['routes']) == 1
    assert report['candidate_count'] >= 1
    for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        assert np.array_equal(getattr(state, field), getattr(state2, field))
    _, again, _ = propose_candidates(state2, updated, hydraulic_config=HydraulicConfig(20.))
    assert again['integrated']['candidate_routes'] == updated['integrated']['candidate_routes']
    assert again['route_geometry'] == updated['route_geometry']


def test_refresh_budget_reuses_one_mesh_and_preserves_candidate(monkeypatch):
    from terrain_pipeline.coastal_delta_avulsion import propose_candidates
    from terrain_pipeline import coastal_delta_routes
    import terrain_pipeline.drainage as irregular_grid

    state, progress, _ = setup_geometry()
    candidate = copy.deepcopy(progress['integrated']['candidate_routes'])
    calls = []
    original = irregular_grid.grid_mesh
    def count_mesh(*args, **kwargs):
        calls.append('mesh')
        return original(*args, **kwargs)
    def no_path(*args, **kwargs):
        calls.append(kwargs['mesh'])
        raise ValueError('no path')
    monkeypatch.setattr(irregular_grid, 'grid_mesh', count_mesh)
    monkeypatch.setattr(coastal_delta_routes, 'irregular_valley_path', no_path)
    # Remove the existing candidate only for the multiple-attempt case.
    empty = copy.deepcopy(progress)
    empty['integrated']['candidate_routes'] = []
    out, updated, report = propose_candidates(state, empty, hydraulic_config=HydraulicConfig(20.),
                                               max_candidates=2, max_fork_attempts=3)
    assert report['attempt_count'] == 3 and report['candidate_count'] == 0
    assert calls[0] == 'mesh' and len(calls) == 4 and all(mesh is calls[1] for mesh in calls[1:])
    for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        np.testing.assert_array_equal(getattr(out, field), getattr(state, field))
    _, preserved, result = propose_candidates(state, progress, hydraulic_config=HydraulicConfig(20.),
                                              max_candidates=2, max_fork_attempts=0)
    assert preserved['integrated']['candidate_routes'] == candidate
    assert result['candidate_count'] == 1 and result['attempt_count'] == 0
