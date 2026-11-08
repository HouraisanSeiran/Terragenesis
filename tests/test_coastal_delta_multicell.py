import numpy as np
import pytest

from terrain_pipeline.coastal_delta_evolution import advance_event, advance_years, load, save
from terrain_pipeline.coastal_delta_geological_network import construct
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig, make_state


def fixture(*, world_seed=20261020):
    base = np.full((10, 16), -5.)
    seeds = np.zeros_like(base, bool)
    seeds[:, -1] = True
    state = make_state(base_bed_m=base, bed_solid_m3=18000., mobile_solid_m3=0., porosity=.4,
        valid_mask=True, ocean_seed_mask=seeds, spacing_m=100., origin_xz_m=(0., 0.), source_identity='multi')
    return construct(state, domain=np.ones_like(base, bool), inlet_zx=(5, 1), main_outlet_zx=(5, 14),
        forks=[(0, 3, (2, 14))], hydraulic_config=HydraulicConfig(12.), input_id='formation',
        discharge_m3_s=100., solid_rate_m3_s=.01, depth_m=5., width_m=150.,
        reference_q_m3_s=100., max_width_m=400., subdivisions=12, world_seed=world_seed)[:2]


def total(s):
    return (sum(getattr(s, k).sum() for k in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'))
            + s.exported_solid_m3 + s.unresolved_solid_m3)


def test_multicell_event_budget_cross_cell_and_restart(tmp_path):
    state, progress = fixture()
    cfg = MarineConfig(step_s=2., settling_velocity_m_s=.001, material_source='test')
    kwargs = dict(marine_config=cfg, hydraulic_config=HydraulicConfig(12.), inlet_solid_rate_m3_s=.1)
    out, report = advance_event(state, progress, 2., input_id='first', **kwargs)
    assert total(out)-total(state)+report['undelivered_solid_m3'] == pytest.approx(.2, abs=1e-6)
    assert out.unresolved_solid_m3 == state.unresolved_solid_m3
    centre = {tuple(cell) for route in progress['routes'] for cell in route}
    changed = set(map(tuple, np.argwhere(out.bed_solid_m3 < state.bed_solid_m3-1e-8)))
    assert changed-centre
    assert out.time_s == 2.
    p = report['updated_progress']
    with pytest.raises(ValueError, match='duplicate'):
        advance_event(out, p, 2., input_id='first', **kwargs)
    save(tmp_path/'event', out, p)
    restored, rp = load(tmp_path/'event')
    a, ar = advance_event(out, p, 2., input_id='second', **kwargs)
    b, br = advance_event(restored, rp, 2., input_id='second', **kwargs)
    assert np.array_equal(a.bed_solid_m3, b.bed_solid_m3)
    assert ar == br


def test_multicell_annual_budget_and_fixed_width():
    state, progress = fixture()
    out, p = advance_years(state, progress, .000001, input_id='annual', hydraulic_config=HydraulicConfig(12.))
    requested = .01*.000001*365.25*86400.
    assert total(out)-total(state)+p['integrated']['pending_solid_m3'] == pytest.approx(requested, abs=1e-6)
    assert out.time_s == state.time_s
    assert p['fixed_channel_footprint']['lateral_change'].startswith('fixed')
    with pytest.raises(ValueError, match='duplicate'):
        advance_years(out, p, .000001, input_id='annual', hydraulic_config=HydraulicConfig(12.))


def test_length_scaled_annual_parameters_and_budget():
    state, progress = fixture()
    kwargs = dict(hydraulic_config=HydraulicConfig(12.), river_deposition_fraction=.01,
                  river_deposition_reference_length_m=600.)
    out, p = advance_years(state, progress, .000001, input_id='length', **kwargs)
    assert total(out)-total(state)+p['integrated']['pending_solid_m3'] == pytest.approx(.01*.000001*365.25*86400., abs=1e-6)
    assert p['integrated']['multicell_parameters']['river_deposition_reference_length_m'] == 600.
    with pytest.raises(ValueError, match='parameters'):
        advance_years(out, p, .000001, input_id='changed', **(kwargs | {'river_deposition_reference_length_m': 100.}))


def test_event_rejects_supply_above_carrying_capacity():
    state, progress = fixture()
    out, report = advance_event(state, progress, 1., MarineConfig(step_s=1.), input_id='capacity',
        hydraulic_config=HydraulicConfig(12.), inlet_solid_rate_m3_s=1000., capacity_concentration=.01)
    assert report['delivered_solid_m3'] <= report['delivered_water_m3']*.01
    assert report['undelivered_solid_m3'] > 0
    assert total(out)-total(state)+report['undelivered_solid_m3'] == pytest.approx(1000., abs=1e-6)


def test_filled_section_preserves_bank_and_reports_overflow():
    from copy import deepcopy
    from terrain_pipeline.coastal_delta_hydraulics import solve, HydraulicConfig
    state, progress = fixture()
    progress = deepcopy(progress)
    section = progress['hydraulic_sections']['nodes'][0]
    section[2] = section[4] + .2
    bank = section[4]
    result = solve(state, progress, 0., HydraulicConfig(12.))
    status = {tuple(row[:2]): row[2:] for row in result['section_states']}
    assert status[tuple(section[:2])] == ['filled', True]
    assert section[4] == bank
    assert result['accepted_q_m3_s'] > 0


def test_committed_event_feedback_is_lagged_and_footprint_limited():
    from terrain_pipeline.coastal_delta_routes import route_metrics, node_control_length
    from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
    from terrain_pipeline.coastal_delta_hydraulics import solve
    state, progress = fixture()
    cfg = MarineConfig(step_s=2.)
    out, report = advance_event(state, progress, 2., cfg, input_id='width',
        hydraulic_config=HydraulicConfig(12.), inlet_solid_rate_m3_s=.1)
    p = report['updated_progress']
    feedback = p['fixed_channel_footprint']
    budgets = feedback['last_feedback']['nodes']
    assert len(budgets) == len({tuple(n[:2]) for n in p['hydraulic_sections']['nodes']})
    branch_only = set(map(tuple, p['routes'][1])) - set(map(tuple, p['routes'][0]))
    assert branch_only and all(str(node) in budgets and budgets[str(node)]['formative_q_m3_s'] > 0
                               for node in branch_only)
    assert sum(b['eroded_solid_m3'] for b in budgets.values()) == pytest.approx(report['entrained_solid_m3'])
    assert report['entrained_solid_m3'] > 0
    assert total(out)-total(state)+report['undelivered_solid_m3'] == pytest.approx(.2, abs=1e-6)
    pool = ChannelInventory(out, p)
    metrics = route_metrics(p, out.spacing_m)
    for row in p['hydraulic_sections']['nodes']:
        node = tuple(row[:2]); key = str(node)
        assert row[3] == pytest.approx(min(feedback['design_width_m'][key],
            pool.area(node)/node_control_length(p, node, out.spacing_m, metrics)))
        assert feedback['design_width_m'][key] > 0
    assert any(b['eroded_solid_m3'] > 0 for b in budgets.values())
    assert any(b['feedback_width_delta_m'] > 0 for b in budgets.values())
    assert p['river_hydraulics'] == solve(out, p, p['river_hydraulics']['sea_level_m'], HydraulicConfig(12.))
    assert p['segments'] and p['actual_shares'] == p['river_hydraulics']['actual_shares']


def test_annual_deposition_feedback_and_capacity_preserve_stock():
    from terrain_pipeline.coastal_delta_hydraulics import solve
    state, progress = fixture()
    out, p = advance_years(state, progress, .000001, input_id='annual-width',
        hydraulic_config=HydraulicConfig(12.), river_deposition_fraction=.5)
    budgets = p['fixed_channel_footprint']['last_feedback']['nodes']
    assert any(b['deposited_solid_m3'] > 0 for b in budgets.values())
    assert any(b['feedback_width_delta_m'] < 0 for b in budgets.values())
    assert all(b['transported_solid_m3'] <= b['capacity_solid_m3'] + 1e-9 for b in budgets.values())
    assert total(out)-total(state)+p['integrated']['pending_solid_m3'] == pytest.approx(.01*.000001*365.25*86400., abs=1e-6)
    assert p['river_hydraulics'] == solve(out, p, 0., HydraulicConfig(12.))


def test_legacy_shared_node_formative_q_and_zero_instantaneous_flow():
    from terrain_pipeline.coastal_delta_branching import _record
    from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
    state, progress = fixture()
    progress['geological_network'].pop('node_design_q_m3_s')
    progress.pop('river_hydraulics', None)
    state = _record(state, progress)
    out, report = advance_event(state, progress, 1., MarineConfig(step_s=1.), input_id='dry',
        hydraulic_config=HydraulicConfig(-100.), inlet_solid_rate_m3_s=.1)
    p = report['updated_progress']
    assert p['river_hydraulics']['accepted_q_m3_s'] == 0
    shared = set(map(tuple, progress['routes'][0])) & set(map(tuple, progress['routes'][1]))
    budgets = p['fixed_channel_footprint']['last_feedback']['nodes']
    for node in shared:
        assert budgets[str(node)]['formative_q_m3_s'] == pytest.approx(progress['discharge_m3_s'])
        assert p['fixed_channel_footprint']['design_width_m'][str(node)] > 0
    assert total(out)-total(state)+report['undelivered_solid_m3'] == pytest.approx(.1, abs=1e-6)
    inlet = tuple(p['routes'][0][0])
    pool = ChannelInventory(out, p)
    pool.add(inlet, 'mobile_solid_m3', 5.)
    out, p = pool.commit(out, p)
    p['geological_network']['node_design_q_m3_s'] = [[*inlet, 23.]]
    out = _record(out, p)
    annual, annual_p = advance_years(out, p, .000001, input_id='dry-annual',
        hydraulic_config=HydraulicConfig(-100.), river_deposition_fraction=0.)
    annual_budgets = annual_p['fixed_channel_footprint']['last_feedback']['nodes']
    inlet_budget = annual_budgets[str(inlet)]
    assert inlet_budget['formative_q_m3_s'] == 23.
    assert inlet_budget['capacity_solid_m3'] == inlet_budget['transported_solid_m3'] == 0.
    assert ChannelInventory(annual, annual_p).amount(inlet, 'mobile_solid_m3') == pytest.approx(5.)
    assert total(annual) == pytest.approx(total(out), abs=1e-6)


def test_annual_capacity_retains_excess_mobile():
    from terrain_pipeline.coastal_delta_branching import _record
    from terrain_pipeline.coastal_delta_evolution import FloodplainConfig
    from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
    state, progress = fixture()
    pool = ChannelInventory(state, progress)
    inlet = tuple(progress['routes'][0][0])
    pool.add(inlet, 'mobile_solid_m3', 1000.)
    state, progress = pool.commit(state, progress)
    state = _record(state, progress)
    out, p = advance_years(state, progress, .000001, input_id='capacity-annual',
        hydraulic_config=HydraulicConfig(12.), river_deposition_fraction=0.,
        floodplain_config=FloodplainConfig(exchange_fraction=0.))
    budget = p['fixed_channel_footprint']['last_feedback']['nodes'][str(inlet)]
    assert budget['transported_solid_m3'] == pytest.approx(budget['capacity_solid_m3'])
    expected = budget['initial_mobile_solid_m3'] + budget['external_solid_m3'] - budget['transported_solid_m3']
    assert ChannelInventory(out, p).amount(inlet, 'mobile_solid_m3') == pytest.approx(expected)
    assert total(out)-total(state)+p['integrated']['pending_solid_m3'] == pytest.approx(.01*.000001*365.25*86400., abs=1e-6)

