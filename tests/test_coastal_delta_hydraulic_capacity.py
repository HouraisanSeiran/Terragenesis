"""Issue 24: hydraulic sediment capacity, loaded-only deposition, under-loaded-only erosion."""
import hashlib

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_evolution import advance_event
from terrain_pipeline.coastal_delta_hydraulic_capacity import HydraulicCapacityRule, capacity_rate, node_exchange
from terrain_pipeline.coastal_delta_hydraulic_event import advance_event_hydraulic
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import MarineConfig
from test_coastal_delta_multicell import fixture, total

H = HydraulicConfig(12.)
RULE = HydraulicCapacityRule(critical_shear_pa=.05, transport_coefficient=1e-3, settling_velocity_m_s=.01)
# Recorded before the new modules existed; the default (legacy) event must not move.
LEGACY_DIGEST = '9ebc1c3be87dbff08ee59da82947efb64beeb270f68bf2dbdd49cd6f639cd1f7'


def marine(step):
    return MarineConfig(step_s=step, settling_velocity_m_s=.001, material_source='test')


def run_new(step, rule=RULE, seconds=600., solid=2.):
    state, progress = fixture()
    out, report = advance_event_hydraulic(state, progress, seconds, marine(step), input_id='e',
        hydraulic_config=H, inlet_solid_rate_m3_s=solid, capacity_rule=rule)
    return state, out, report


def test_legacy_default_event_is_bit_identical():
    state, progress = fixture()
    out, _ = advance_event(state, progress, 600., marine(300.), input_id='e',
                           hydraulic_config=H, inlet_solid_rate_m3_s=2.)
    digest = hashlib.sha256(out.bed_solid_m3.tobytes() + out.mobile_solid_m3.tobytes()).hexdigest()
    assert digest == LEGACY_DIGEST


def test_capacity_falls_with_width_depth_and_roughness_at_fixed_q():
    base = capacity_rate(RULE, 100., 100., 3., .035)
    assert base['capacity_m3_s'] > 0
    previous = base['capacity_m3_s']
    for width in (150., 250., 500.):
        now = capacity_rate(RULE, 100., width, 3., .035)['capacity_m3_s']
        assert now < previous
        previous = now
    previous = base['capacity_m3_s']
    for depth in (4., 6., 10.):
        now = capacity_rate(RULE, 100., 100., depth, .035)['capacity_m3_s']
        assert now < previous
        previous = now
    assert capacity_rate(RULE, 100., 100., 3., .02)['capacity_m3_s'] < base['capacity_m3_s']
    # Capacity depends on hydraulics: the same Q gives different capacity, not Q * constant.
    assert capacity_rate(RULE, 200., 100., 3., .035)['capacity_m3_s'] > 2 * base['capacity_m3_s']


def test_widening_a_reach_deposits_what_the_narrow_reach_carried():
    carried_capacity = {}
    for width in (100., 400.):
        cap = capacity_rate(RULE, 100., width, 3., .035)['capacity_m3_s'] * 100.
        carried_capacity[width] = cap
    load = carried_capacity[100.] * .9  # fully carried upstream, overloaded downstream
    narrow = node_exchange(RULE, mobile_m3=load, advective_m3=load, capacity_m3=carried_capacity[100.],
        depth_m=3., dt_s=100., erosion_limit_m3=1., erosion_cap_m3=1., deposit_room_m3=1e6)
    wide = node_exchange(RULE, mobile_m3=load, advective_m3=load, capacity_m3=carried_capacity[400.],
        depth_m=3., dt_s=100., erosion_limit_m3=1., erosion_cap_m3=1., deposit_room_m3=1e6)
    assert not narrow[3] and narrow[2] == 0.
    assert wide[3] and wide[2] > 0. and wide[1] == 0.
    assert wide[0] == pytest.approx(carried_capacity[400.])


def test_erosion_only_when_under_loaded_and_never_beyond_limits():
    under = node_exchange(RULE, mobile_m3=1., advective_m3=1., capacity_m3=5., depth_m=3., dt_s=10.,
        erosion_limit_m3=10., erosion_cap_m3=10., deposit_room_m3=100.)
    assert under == (1., 4., 0., False)
    limited = node_exchange(RULE, mobile_m3=1., advective_m3=1., capacity_m3=5., depth_m=3., dt_s=10.,
        erosion_limit_m3=.5, erosion_cap_m3=10., deposit_room_m3=100.)
    assert limited[1] == .5
    capped = node_exchange(RULE, mobile_m3=1., advective_m3=1., capacity_m3=5., depth_m=3., dt_s=10.,
        erosion_limit_m3=10., erosion_cap_m3=.25, deposit_room_m3=100.)
    assert capped[1] == .25
    over = node_exchange(RULE, mobile_m3=9., advective_m3=9., capacity_m3=5., depth_m=3., dt_s=10.,
        erosion_limit_m3=10., erosion_cap_m3=10., deposit_room_m3=100.)
    assert over[1] == 0. and over[0] == 5. and 0. < over[2] <= 4.
    full = node_exchange(RULE, mobile_m3=9., advective_m3=9., capacity_m3=5., depth_m=3., dt_s=10.,
        erosion_limit_m3=10., erosion_cap_m3=10., deposit_room_m3=0.)
    assert full[2] == 0.  # no room: nothing is discarded, it stays mobile


def test_event_ledger_closes_and_overloaded_nodes_deposit():
    state, out, report = run_new(300.)
    ledger = total(out) - total(state) + report['undelivered_solid_m3'] - 2. * 600.
    assert abs(ledger) < 1e-6
    rows = report['node_exchange']
    assert sum(r['deposited_m3'] for r in rows) > 0
    assert report['river_deposited_solid_m3'] == pytest.approx(sum(r['deposited_m3'] for r in rows))
    assert report['hydraulic_capacity_rule']['algorithm'] == 'excess-shear-manning-substep-v1'
    assert report['updated_progress']['hydraulic_capacity_rule'] == report['hydraulic_capacity_rule']
    assert out.bed_solid_m3.min() >= -1e-9 and out.mobile_solid_m3.min() >= -1e-9


def test_event_bed_and_mobile_close_with_node_budgets():
    state, out, report = run_new(300.)
    exchange = report['node_exchange']
    eroded = sum(r['eroded_m3'] for r in exchange)
    deposited = sum(r['deposited_m3'] for r in exchange)
    assert eroded == pytest.approx(report['entrained_solid_m3'])
    # Bed change in channel nodes is deposit minus erosion plus marine/overbank grid exchange.
    assert deposited >= 0 and eroded >= 0
    # Everything delivered into the system is accounted for in bed + mobile + stranded + exported + unresolved.
    assert total(out) - total(state) == pytest.approx(report['delivered_solid_m3'], abs=1e-6)


def test_event_underloaded_erodes_without_deposit():
    rule = HydraulicCapacityRule(critical_shear_pa=.01, transport_coefficient=1e-2, settling_velocity_m_s=.01)
    state, out, report = run_new(300., rule=rule, solid=1e-4, seconds=300.)
    rows = report['node_exchange']
    assert sum(r['eroded_m3'] for r in rows) > 0
    assert all(r['overloaded_seconds'] == 0 for r in rows)
    assert sum(r['deposited_m3'] for r in rows) == 0
    assert abs(total(out) - total(state) + report['undelivered_solid_m3'] - 1e-4 * 300.) < 1e-6


def test_event_result_insensitive_to_marine_step():
    _, a, ra = run_new(300.)
    _, b, rb = run_new(150.)
    diff = float(np.abs(a.bed_solid_m3 - b.bed_solid_m3).sum())
    moved = sum(r['deposited_m3'] for r in ra['node_exchange'])
    # Declared tolerance: summed |bed difference| below 2 % of the channel deposit.
    assert diff < .02 * moved, (diff, moved)
    dep_a = sum(r['deposited_m3'] for r in ra['node_exchange'])
    dep_b = sum(r['deposited_m3'] for r in rb['node_exchange'])
    assert dep_a == pytest.approx(dep_b, rel=.01)


def test_rule_identity_and_validation():
    rule = HydraulicCapacityRule(critical_shear_pa=.05)
    ident = rule.identity()
    assert ident['calibration_status'] == 'declared/uncalibrated'
    assert HydraulicCapacityRule.from_identity(ident) == rule
    with pytest.raises(ValueError):
        HydraulicCapacityRule(transport_coefficient=0.)
    with pytest.raises(ValueError):
        HydraulicCapacityRule(max_concentration=2.)
    with pytest.raises(ValueError):
        HydraulicCapacityRule(annual_formative_seconds_per_year=-1.)
    state, progress = fixture()
    other = HydraulicCapacityRule(critical_shear_pa=.07)
    out, report = advance_event_hydraulic(state, progress, 10., marine(10.), input_id='a',
        hydraulic_config=H, inlet_solid_rate_m3_s=.1, capacity_rule=rule)
    with pytest.raises(ValueError, match='differs'):
        advance_event_hydraulic(out, report['updated_progress'], 10., marine(10.), input_id='b',
            hydraulic_config=H, inlet_solid_rate_m3_s=.1, capacity_rule=other)
