import copy

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_branch_attachment import attach_multicell_branch, _illegal_intersection
from terrain_pipeline.coastal_delta_branching import segment_fluxes
from terrain_pipeline.coastal_delta_evolution import load, save
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_delta_routes import irregular_valley_path
from test_coastal_delta_multicell import fixture


def test_intersection_at_shared_endpoint_allows_only_point_contact():
    positions = {(0, 0): np.array([0., 0.]), (0, 1): np.array([1., 0.]),
                 (0, 2): np.array([2., 0.]), (1, 0): np.array([0., 1.]),
                 (1, 1): np.array([1., -1.]), (1, 2): np.array([1., 1.])}
    assert _illegal_intersection((0, 0), (0, 1), (0, 0), (0, 2), positions)
    assert _illegal_intersection((0, 0), (0, 1), (0, 1), (0, 0), positions)
    assert not _illegal_intersection((0, 0), (0, 1), (0, 0), (1, 0), positions)
    assert _illegal_intersection((0, 0), (0, 2), (1, 1), (1, 2), positions)


def candidate(state, progress):
    route = progress['routes'][0]
    fork_index = 6
    start = tuple(route[fork_index])
    forbidden = np.zeros(state.bed_m.shape, bool)
    for old in progress['routes']:
        for cell in old:
            forbidden[tuple(cell)] = True
    forbidden[start] = False
    xy = next(row[2:] for row in progress['route_geometry']['nodes'] if tuple(row[:2]) == start)
    positions = {tuple(r[:2]): np.asarray(r[2:], float) for r in progress['route_geometry']['nodes']}
    path, points = irregular_valley_path(state.bed_m, state.valid_mask, start, (8, 14), 12.,
        state.spacing_m, origin_xz_m=state.origin_xz_m, world_seed=progress['route_geometry']['seed'],
        forbidden=forbidden, start_xz_m=xy, max_turn_deg=90.,
        start_directions_xz=[positions[start]-positions[tuple(e[:2])] for e in progress['route_geometry']['edges'] if tuple(e[2:])==start])
    return fork_index, path, points


def attach(state, progress, **kwargs):
    fork, path, xy = candidate(state, progress)
    return attach_multicell_branch(state, progress, parent_index=0, fork_index=fork,
        path_zx=path, path_xz_m=xy, hydraulic_config=HydraulicConfig(12.), **kwargs)


def test_attachment_conserves_inventory_and_restart(tmp_path):
    state, progress = fixture()
    old_parts = copy.deepcopy(progress['node_footprints'])
    old_shares = progress['shares'][:]
    out, p, report = attach(state, progress)
    assert report['attached'], report
    assert p['node_footprints'][:len(old_parts)] == old_parts
    assert np.array_equal(out.base_bed_m, state.base_bed_m)
    fields = ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')
    assert sum(getattr(out, f).sum() for f in fields) == pytest.approx(sum(getattr(state, f).sum() for f in fields))
    assert out.unresolved_solid_m3 == state.unresolved_solid_m3
    assert p['shares'][0] + p['shares'][-1] == pytest.approx(old_shares[0])
    assert sum(p['shares']) == pytest.approx(sum(old_shares))
    assert p['river_hydraulics']['route_q_m3_s'][-1] > 0
    assert report['widths_m'] and max(report['widths_m']) <= report['nominal_width_m']
    inlet = next(s for s in segment_fluxes(p) if s['from_zx'] == p['routes'][0][0])
    assert inlet['share'] <= 1.000001
    save(tmp_path/'branch', out, p)
    restored, rp = load(tmp_path/'branch')
    assert rp == p
    for f in fields:
        assert np.array_equal(getattr(restored, f), getattr(out, f))


def test_rejected_attachment_leaves_inputs_unchanged():
    state, progress = fixture()
    before = copy.deepcopy(progress)
    out, p, report = attach(state, progress, sea_level_m=-100.)
    assert not report['attached'] and report['reason']
    assert out is state and p is progress and progress == before
    fork, path, xy = candidate(state, progress)
    out, p, report = attach_multicell_branch(state, progress, parent_index=0, fork_index=1,
        path_zx=path, path_xz_m=xy, hydraulic_config=HydraulicConfig(12.))
    assert not report['attached'] and out is state and p is progress


def test_hierarchy_and_dry_trial_are_transactional():
    from terrain_pipeline.coastal_delta_branching import _record

    state, progress = fixture()
    progress['hierarchical_plan'] = {
        'forks': [[0, 3, progress['routes'][1][-1]]],
        'route_depths': [1, 1], 'side_branch_counts': [1, 0],
        'route_shares': list(progress['shares']), 'design_q_m3_s': [50., 50.],
        'prepared_paths': {'cells': copy.deepcopy(progress['routes']), 'points_xz': []},
        'config': {'max_mouths': 4, 'max_depth': 3, 'max_side_branches': 3,
                   'min_fraction': .1, 'min_design_q_m3_s': 1.}}
    state = _record(state, progress)
    original_paths = copy.deepcopy(progress['hierarchical_plan']['prepared_paths'])
    out, p, report = attach(state, progress)
    assert report['attached'], report
    plan = p['hierarchical_plan']
    assert plan['route_depths'] == [2, 1, 2]
    assert plan['side_branch_counts'] == [2, 0, 0]
    assert plan['initial_prepared_paths'] == original_paths
    assert plan['current_paths']['cells'] == p['routes']
    assert sum(plan['design_q_m3_s']) == pytest.approx(progress['discharge_m3_s'])
    fork, path, xy = candidate(state, progress)
    out, p, report = attach_multicell_branch(state, progress, parent_index=0, fork_index=fork,
        path_zx=path, path_xz_m=xy, hydraulic_config=HydraulicConfig(-100.))
    assert not report['attached'] and out is state and p is progress


def test_rejoin_event_shared_inventory_and_restart(tmp_path):
    from terrain_pipeline.coastal_delta_evolution import advance_event
    from terrain_pipeline.coastal_marine_sediment import MarineConfig
    from test_coastal_delta_multicell import total

    state, progress = fixture(world_seed=4)
    route = progress['routes'][0]
    fork, rejoin = 4, 7
    start, end = tuple(route[fork]), tuple(route[rejoin])
    forbidden = np.zeros(state.bed_m.shape, bool)
    for old in progress['routes']:
        for cell in old:
            forbidden[tuple(cell)] = True
    forbidden[start] = forbidden[end] = False
    xy = next(row[2:] for row in progress['route_geometry']['nodes'] if tuple(row[:2]) == start)
    positions = {tuple(r[:2]): np.asarray(r[2:], float) for r in progress['route_geometry']['nodes']}
    path, points = irregular_valley_path(state.bed_m, state.valid_mask, start, end, 12.,
        state.spacing_m, origin_xz_m=state.origin_xz_m, world_seed=progress['route_geometry']['seed'],
        forbidden=forbidden, start_xz_m=xy, max_turn_deg=90.,
        start_directions_xz=[positions[start]-positions[tuple(e[:2])] for e in progress['route_geometry']['edges'] if tuple(e[2:])==start],
        end_directions_xz=[positions[tuple(e[2:])]-positions[end] for e in progress['route_geometry']['edges'] if tuple(e[:2])==end])
    state, p, report = attach_multicell_branch(state, progress, parent_index=0, fork_index=fork,
        rejoin_index=rejoin, path_zx=path, path_xz_m=points, hydraulic_config=HydraulicConfig(12.))
    assert report['attached'], report
    assert p['routes'][-1][-(len(route)-rejoin):] == route[rejoin:]
    assert len({tuple(row[:2]) for row in p['node_footprints']}) == len(p['node_footprints'])
    shared = next(edge for edge in segment_fluxes(p) if edge['from_zx'] == route[rejoin]
                  and edge['to_zx'] == route[rejoin+1])
    assert shared['discharge_m3_s'] == pytest.approx(sum(p['river_hydraulics']['route_q_m3_s'][i] for i in (0, 2)))
    config = dict(marine_config=MarineConfig(step_s=2.), hydraulic_config=HydraulicConfig(12.),
                  inlet_solid_rate_m3_s=.1)
    out, result = advance_event(state, p, 2., input_id='rejoin-first', **config)
    assert total(out)-total(state)+result['undelivered_solid_m3'] == pytest.approx(.2, abs=1e-6)
    save(tmp_path/'rejoin', out, result['updated_progress'])
    restored, saved = load(tmp_path/'rejoin')
    a, ar = advance_event(out, result['updated_progress'], 2., input_id='rejoin-second', **config)
    b, br = advance_event(restored, saved, 2., input_id='rejoin-second', **config)
    assert np.array_equal(a.bed_solid_m3, b.bed_solid_m3)
    assert ar == br


def test_new_bank_uses_actual_unowned_surface_in_mixed_channel_cells():
    from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
    state, progress = fixture()
    fork, path, xy = candidate(state, progress)
    from dataclasses import replace
    from terrain_pipeline.coastal_delta_branching import _record
    occupied = np.zeros(state.bed_m.shape)
    for _, _, parts in progress['node_footprints']:
        for z, x, fraction, *_ in parts:
            occupied[z, x] += fraction
    # Add a real unowned bank layer. Existing channel parts stay at their old bed.
    stock = state.bed_solid_m3.copy()
    stock[5:8, 6:10] += 4.*np.maximum(1-occupied[5:8, 6:10], 0.)*state.spacing_m**2*(1-state.porosity[5:8, 6:10])
    state = _record(replace(state, bed_solid_m3=stock), progress)
    out, p, report = attach_multicell_branch(state, progress, parent_index=0, fork_index=fork,
        path_zx=path, path_xz_m=xy, hydraulic_config=HydraulicConfig(12.), max_cut_m=4.)
    assert report['attached'], report
    free = np.ones(state.bed_m.shape)
    outer = state.bed_solid_m3.copy()
    for _, _, parts in progress['node_footprints']:
        for z, x, fraction, bed, *_ in parts:
            free[z, x] -= fraction
            outer[z, x] -= bed
    old = {tuple(row[:2]): row for row in progress['hydraulic_sections']['nodes']}
    sections = {tuple(row[:2]): row for row in p['hydraulic_sections']['nodes']}
    stages = {tuple(row[:2]): row[2] for row in p['river_hydraulics']['nodes']}
    mixed = []
    for z, x, parts in p['node_footprints']:
        cell = (z, x)
        if cell in old:
            assert sections[cell][4] == old[cell][4]
            continue
        expected = sum(f * (state.base_bed_m[r,c] + outer[r,c]/
            (free[r,c]*state.spacing_m**2*(1-state.porosity[r,c])))
            for r,c,f,*_ in parts)/sum(part[2] for part in parts)
        assert sections[cell][4] == pytest.approx(expected, abs=1e-10)
        if state.bed_m[cell] < stages[cell] < expected:
            mixed.append(cell)
    assert mixed, 'fixture must distinguish the mixed grid bed from the real outer bank'
    pool = ChannelInventory(out, p)
    assert all(row[2] == pytest.approx(pool.section_bed(tuple(row[:2])))
               for row in p['hydraulic_sections']['nodes'])
    assert np.array_equal(out.base_bed_m, state.base_bed_m)
    fields = ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')
    assert sum(getattr(out,f).sum() for f in fields) == pytest.approx(sum(getattr(state,f).sum() for f in fields))


@pytest.mark.parametrize('constrain_start', [False, True])
def test_sharp_supplied_arm_is_rejected_before_stock_changes(constrain_start):
    from terrain_pipeline.channel_geometry import turn_penalty
    state, progress = fixture()
    route = progress['routes'][0]
    fork, rejoin = 4, 7
    start, end = tuple(route[fork]), tuple(route[rejoin])
    positions = {tuple(r[:2]): np.asarray(r[2:], float) for r in progress['route_geometry']['nodes']}
    forbidden = np.zeros(state.bed_m.shape, bool)
    for old in progress['routes']:
        for cell in old:
            forbidden[tuple(cell)] = True
    forbidden[start] = forbidden[end] = False
    incoming = positions[start]-positions[tuple(route[fork-1])]
    kwargs = dict(max_turn_deg=90.) if constrain_start else {}
    path, points = irregular_valley_path(state.bed_m, state.valid_mask, start, end, 12.,
        state.spacing_m, origin_xz_m=state.origin_xz_m, world_seed=progress['route_geometry']['seed'],
        forbidden=forbidden, **kwargs)
    vectors = np.vstack((incoming, np.diff(points, axis=0), positions[tuple(route[rejoin+1])]-points[-1]))
    assert any(np.isinf(turn_penalty(a, b)) for a, b in zip(vectors, vectors[1:]))
    if constrain_start:
        assert all(np.isfinite(turn_penalty(a, b)) for a, b in zip(vectors[1:-2], vectors[2:-1]))
    before = copy.deepcopy(progress)
    out, result, report = attach_multicell_branch(state, progress, parent_index=0, fork_index=fork,
        rejoin_index=rejoin, path_zx=path, path_xz_m=points, hydraulic_config=HydraulicConfig(12.))
    assert not report['attached'] and 'turn' in report['reason'], report
    assert out is state and result is progress and progress == before
