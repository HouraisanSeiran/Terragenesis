"""Real finite-stock events through consecutive attached split/rejoin arms."""
from copy import deepcopy
from time import perf_counter

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_branch_attachment import attach_multicell_branch
from terrain_pipeline.coastal_delta_branching import _record, _update_activity, segment_fluxes, _mouth_forcing, _event_edges
from terrain_pipeline.coastal_delta_evolution import advance_event, advance_years, load, save
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_delta_morphology import prepare_morphology, capture_formative_discharge
from terrain_pipeline.coastal_delta_routes import irregular_valley_path
from terrain_pipeline.coastal_marine_sediment import MarineConfig
from test_coastal_delta_multicell import fixture, total

HYDRAULIC = HydraulicConfig(12.)


def two_rejoins():
    state, p = fixture(world_seed=4)
    p['hydraulics_backend'] = 'physical_edge_graph'
    for fork, rejoin in ((4, 7), (8, 11)):
        route = p['routes'][0]
        start, end = tuple(route[fork]), tuple(route[rejoin])
        forbidden = np.zeros(state.bed_m.shape, bool)
        for old in p['routes']:
            for cell in old:
                forbidden[tuple(cell)] = True
        forbidden[start] = forbidden[end] = False
        xy = next(row[2:] for row in p['route_geometry']['nodes'] if tuple(row[:2]) == start)
        positions = {tuple(r[:2]): np.asarray(r[2:], float) for r in p['route_geometry']['nodes']}
        path, points = irregular_valley_path(state.bed_m, state.valid_mask, start, end, 12.,
            state.spacing_m, origin_xz_m=state.origin_xz_m, world_seed=p['route_geometry']['seed'],
            forbidden=forbidden, start_xz_m=xy, max_turn_deg=90.,
            start_directions_xz=[positions[start]-positions[tuple(e[:2])] for e in p['route_geometry']['edges'] if tuple(e[2:])==start],
            end_directions_xz=[positions[tuple(e[2:])]-positions[end] for e in p['route_geometry']['edges'] if tuple(e[:2])==end])
        state, p, report = attach_multicell_branch(state, p, parent_index=0,
            fork_index=fork, rejoin_index=rejoin, path_zx=path, path_xz_m=points,
            hydraulic_config=HYDRAULIC)
        assert report['attached'], report
    return state, p


def event(state, p, name, seconds=2.):
    return advance_event(state, p, seconds, MarineConfig(step_s=2.), input_id=name,
        hydraulic_config=HYDRAULIC, inlet_solid_rate_m3_s=.1)


def test_two_attachments_event_cover_and_restart(tmp_path):
    state, p = two_rejoins()
    assert len(p['routes']) == 4  # two original mouths plus two arm covers, not 2**forks
    assert len(p['node_footprints']) == len({tuple(row[:2]) for row in p['node_footprints']})
    assert p['river_hydraulics']['algorithm'] == 'river-physical-edge-flux-dag-v1'
    # Add the omitted cross-combination and reorder the cover, preserving the graph.
    other = deepcopy(p)
    a, b = p['routes'][2], p['routes'][3]
    common = p['routes'][0][8]
    combination = a[:a.index(common)] + b[b.index(common):]
    other['routes'] = [combination] + list(reversed(other['routes']))
    other['shares'] = [0.] + list(reversed(other['shares']))
    other['control_references'] = [other['control_references'][0]] + list(reversed(other['control_references']))
    _update_activity(state, other, 0., 'cover', HYDRAULIC)
    other_state = _record(state, other)
    edges = segment_fluxes(p)
    assert len(edges) == len({tuple(e['from_zx']+e['to_zx']) for e in edges})
    mouths = _mouth_forcing(p)
    assert len(mouths) == len({tuple(r[-1]) for r in p['routes']})
    assert sum(m.discharge_m3_s for m in mouths) == pytest.approx(100., rel=1e-4)
    assert len(_event_edges(state, p, 0.)) == len(edges) + len(mouths)
    route = p['routes'][0]
    shared = next(e for e in edges if e['from_zx'] == route[7] and e['to_zx'] == route[8])
    node_q = {tuple(row[:2]): row[4] for row in p['river_hydraulics']['nodes']}
    assert shared['discharge_m3_s'] == pytest.approx(node_q[tuple(route[7])], rel=1e-4)
    start = perf_counter()
    out, result = event(state, p, 'first', 4.)
    print('graph fixture 4s event wall seconds:', perf_counter()-start)
    equivalent, er = event(other_state, other, 'first', 4.)
    assert total(out)-total(state)+result['undelivered_solid_m3'] == pytest.approx(.4, abs=1e-6)
    for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        assert np.allclose(getattr(out, field), getattr(equivalent, field), rtol=1e-4, atol=1e-6)
    assert result['delivered_water_m3'] == pytest.approx(er['delivered_water_m3'], rel=1e-4)
    save(tmp_path/'graph', out, result['updated_progress'])
    restored, rp = load(tmp_path/'graph')
    x, xr = event(out, result['updated_progress'], 'continued')
    y, yr = event(restored, rp, 'continued')
    assert np.array_equal(x.bed_solid_m3, y.bed_solid_m3)
    assert xr == yr


def test_morphology_recomputes_and_captures_actual_q():
    state, p = two_rejoins()
    for key in p['fixed_channel_footprint']['design_width_m']:
        p['fixed_channel_footprint']['design_width_m'][key] = 350.
    state = _record(state, p)
    out, updated, report = prepare_morphology(state, p, sea_level_m=0.,
        hydraulic_config=HYDRAULIC, capture_formative=True)
    assert report['added_area_m2'] > 0
    assert not report['hydraulics_recompute_required']
    assert total(out) == pytest.approx(total(state), abs=1e-6)
    assert np.array_equal(out.base_bed_m, state.base_bed_m)
    recomputed = solve(out, updated, 0., HYDRAULIC)
    assert updated['river_hydraulics'] == recomputed
    assert updated['formative_discharge']['nodes']
    positive = deepcopy(updated['formative_discharge']['nodes'])
    _, dry = capture_formative_discharge(out, updated, hydraulic_config=HYDRAULIC,
        reference_sea_level_m=12.)
    assert dry['formative_discharge']['nodes'] == positive
    assert all(row[2] == 0. for row in dry['formative_discharge']['node_reference_sea_level_m'])
    assert dry['river_hydraulics'] == recomputed
    yearly, yp = advance_years(out, updated, .000001, input_id='actual-formative',
        hydraulic_config=HYDRAULIC, river_deposition_reference_length_m=1000.)
    assert total(yearly)-total(out)+yp['integrated']['pending_solid_m3'] == pytest.approx(
        .01*.000001*365.25*86400., abs=1e-6)
    actual = {str(tuple(row[:2])): row[2] for row in positive}
    for key, budget in yp['fixed_channel_footprint']['last_feedback']['nodes'].items():
        if key in actual:
            assert budget['formative_q_m3_s'] == actual[key]


def test_high_sill_arm_does_not_starve_real_bypass_event():
    from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
    state, p = two_rejoins()
    pool = ChannelInventory(state, p)
    sill = tuple(p['routes'][0][5])
    pool.add(sill, 'bed_solid_m3', (1.-pool.section_bed(sill))*pool.area(sill)*.6)
    state, p = pool.commit(state, p)
    _update_activity(state, p, 0., 'sill', HYDRAULIC)
    state = _record(state, p)
    assert p['river_hydraulics']['accepted_q_m3_s'] == pytest.approx(100.)
    flows = {(tuple(e[:2]), tuple(e[2:4])): e[4] for e in p['river_hydraulics']['edge_q_m3_s']}
    assert flows[tuple(p['routes'][0][4]), sill] < 1e-3
    out, result = event(state, p, 'sill-event')
    assert result['delivered_water_m3'] == pytest.approx(200., rel=1e-4)
    assert total(out)-total(state)+result['undelivered_solid_m3'] == pytest.approx(.2, abs=1e-6)
