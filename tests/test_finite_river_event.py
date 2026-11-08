"""Synthetic duals for finite-event supply: soil kernel + graph receiver + lake stock."""
import unittest

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.finite_river_event import (
    BALANCE_ABSOLUTE_M3,
    BALANCE_RELATIVE,
    ROUTING_POLICY,
    LakeStageCurve,
    advance_finite_event,
    initial_event_state,
    prepare_finite_event_domain,
    run_finite_event,
    soil_volume_m3,
    water_account,
)

AREA = 900.0
DRY = RunoffParameters(initial_soil_mm=0.0)
FAST = RunoffParameters(infiltration_capacity_mm_h=0.0, initial_soil_mm=0.0)


def base_arrays(levels, member_count, *, reach=None):
    """One-row chain draining east into a lake bed of the last ``member_count`` cells."""
    columns = len(levels)
    field = np.array([list(levels)], np.float64)
    mask = np.ones((1, columns), bool)
    receiver = np.full((1, columns), -1, np.int64)
    kinds = np.full((1, columns), 'inactive', 'U24')
    for column in range(columns - 1):
        receiver[0, column] = column + 1
        kinds[0, column] = 'interior'
    kinds[0, -1] = 'retained'
    member = np.zeros(columns, bool)
    member[columns - member_count:] = True
    reach_mask = np.ones(columns, bool) if reach is None else np.asarray(reach, bool)
    return field, mask, receiver, kinds, member, reach_mask


def build(levels=(3.0, 2.0, 1.0, 0.6, 0.4), member_count=2, *, offset=0.25, area=AREA,
          reach=None):
    field, mask, receiver, kinds, member, reach_mask = base_arrays(levels, member_count,
                                                                  reach=reach)
    curve = LakeStageCurve(field.reshape(-1)[member], area)
    level = curve.floor_level_m + offset
    capacity = float(curve.volume(level))
    domain = prepare_finite_event_domain(
        elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
        member_mask=member, reach_mask=reach_mask, cell_area_m2=area,
        safe_level_m=level, safe_capacity_m3=capacity,
        upstream_unknown_mask=np.zeros(field.size, bool))
    return domain, curve, capacity, (field, mask, receiver, kinds, member, reach_mask)


class LakeCurveTests(unittest.TestCase):
    def test_exact_piecewise_linear_volume_and_inverse(self):
        curve = LakeStageCurve(np.array([1.0, 2.0, 4.0]), 100.0)
        self.assertEqual([knot['volume_m3'] for knot in curve.knots()], [0.0, 100.0, 500.0])
        self.assertEqual(curve.volume(1.0), 0.0)
        self.assertEqual(curve.volume(2.0), 100.0)
        self.assertEqual(curve.volume(4.0), 500.0)
        self.assertEqual(curve.volume(1.5), 50.0)
        self.assertEqual(curve.level_of(50.0), 1.5)
        self.assertEqual(curve.level_of(300.0), 3.0)
        self.assertEqual(curve.wet_cells(1.0), 0)
        self.assertEqual(curve.wet_cells(1.0 + 1e-9), 1)
        self.assertEqual(curve.wet_cells(3.0), 2)
        # exact inverse over every knot and a dense interior sample
        for level in (1.0, 1.5, 2.0, 2.75, 3.0, 4.0):
            self.assertAlmostEqual(curve.level_of(curve.volume(level)), level, places=12)

    def test_duplicate_bed_levels_stay_exact(self):
        curve = LakeStageCurve(np.array([2.0, 2.0, 3.0]), 100.0)
        self.assertEqual(curve.volume(2.5), 100.0)
        self.assertEqual(curve.level_of(100.0), 2.5)
        self.assertEqual(curve.wet_cells(2.5), 2)
        with self.assertRaises(ValueError):
            curve.level_of(-1.0)
        with self.assertRaises(ValueError):
            curve.level_of(curve.maximum_volume_m3 + 1.0)


class DomainTests(unittest.TestCase):
    def test_prepared_domain_maps_land_lake_and_terminal(self):
        domain, curve, capacity, arrays = build()
        field, mask, receiver, kinds, member, reach = arrays
        self.assertEqual(domain.active_cells, 5)
        self.assertEqual(domain.land_cells, 3)
        self.assertEqual(domain.member_cells, 2)
        self.assertEqual(domain.terminal_cell, 4)
        self.assertTrue(np.all(domain.receiver_active.reshape(-1)[~reach] == -1))
        self.assertEqual(domain.terminal_kinds.reshape(-1)[4], 'retained')
        self.assertEqual(sorted(set(domain.terminal_kinds.reshape(-1))),
                         ['interior', 'retained'])
        self.assertEqual(domain.metadata()['routing_policy'], ROUTING_POLICY)
        self.assertEqual(float(curve.volume(domain.safe_level_m)), capacity)

    def test_cells_outside_the_reach_become_inactive(self):
        field = np.array([[3.0, 2.0, 1.0, 0.6, 0.4]], np.float64)
        mask = np.ones((1, 5), bool)
        receiver = np.array([[1, 2, -1, -1, -1]], np.int64)
        kinds = np.array([['interior', 'interior', 'retained', 'inactive', 'inactive']], 'U24')
        member = np.array([False, True, True, False, False])
        reach = np.array([True, True, True, False, False])
        curve = LakeStageCurve(field.reshape(-1)[member], AREA)
        level = curve.floor_level_m + 0.25
        domain = prepare_finite_event_domain(
            elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
            member_mask=member, reach_mask=reach, cell_area_m2=AREA,
            safe_level_m=level, safe_capacity_m3=float(curve.volume(level)))
        self.assertEqual(domain.active_cells, 3)
        self.assertEqual(domain.land_cells, 1)
        self.assertEqual(domain.member_cells, 2)
        self.assertEqual(domain.terminal_cell, 2)
        flat_receiver = domain.receiver_active.reshape(-1)
        self.assertEqual(flat_receiver[3], -1)
        self.assertEqual(flat_receiver[4], -1)
        flat_kinds = domain.terminal_kinds.reshape(-1)
        self.assertEqual([flat_kinds[index] for index in (3, 4)], ['inactive', 'inactive'])
        # the inactive cells never carry water
        state = initial_event_state(domain, parameters=DRY)
        outcome = advance_finite_event(domain, state['soil_states_mm'], 0.0, 2.0, dt_s=900.0,
                                       parameters=DRY)
        self.assertEqual(outcome['local_q_m3_s_active'].size, 3)

    def test_rejects_a_reach_that_cuts_off_an_upstream_donor(self):
        # the reach keeps only the two downstream cells of a four-cell chain: the cut-out donors
        # still route into it, so a complete-looking domain would silently drop real water
        field = np.array([[3.0, 2.0, 1.0, 0.5]], np.float64)
        mask = np.ones((1, 4), bool)
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        kinds = np.array([['interior', 'interior', 'interior', 'retained']], 'U24')
        member = np.array([False, False, True, True])
        reach = np.array([False, False, True, True])
        curve = LakeStageCurve(field.reshape(-1)[member], AREA)
        level = curve.floor_level_m + 0.25
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(
                elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
                member_mask=member, reach_mask=reach, cell_area_m2=AREA,
                safe_level_m=level, safe_capacity_m3=float(curve.volume(level)))

    def test_an_outside_catchment_that_drains_inside_itself_stays_inactive(self):
        # cells 0 -> 1 -> 2 form an independent pit outside the reach; they feed nothing inside it
        field = np.array([[3.0, 2.0, 1.0, 4.0, 3.0, 2.0]], np.float64)
        mask = np.ones((1, 6), bool)
        receiver = np.array([[1, 2, -1, 4, 5, -1]], np.int64)
        kinds = np.array([['interior', 'interior', 'retained', 'interior', 'interior',
                           'retained']], 'U24')
        member = np.array([False, False, False, False, True, True])
        reach = np.array([False, False, False, True, True, True])
        curve = LakeStageCurve(field.reshape(-1)[member], AREA)
        level = curve.floor_level_m + 0.25
        domain = prepare_finite_event_domain(
            elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
            member_mask=member, reach_mask=reach, cell_area_m2=AREA,
            safe_level_m=level, safe_capacity_m3=float(curve.volume(level)))
        self.assertEqual(domain.active_cells, 3)
        self.assertEqual(domain.terminal_cell, 5)
        flat_receiver = domain.receiver_active.reshape(-1)
        self.assertEqual([flat_receiver[index] for index in (0, 1, 2)], [-1, -1, -1])
        self.assertEqual([str(kind) for kind in domain.terminal_kinds.reshape(-1)[:2]],
                         ['inactive', 'inactive'])
        state = initial_event_state(domain, parameters=DRY)
        outcome = advance_finite_event(domain, state['soil_states_mm'], 0.0, 2.0, dt_s=900.0,
                                       parameters=DRY)
        # only the reach's own land cell feeds the lake; the outside pit water is never counted
        self.assertAlmostEqual(outcome['ledger']['rain_land_m3'],
                               2.0 * 0.25 * AREA / 1000.0, places=12)
        self.assertAlmostEqual(outcome['ledger']['local_input_m3'],
                               outcome['ledger']['routed_total_m3'], places=12)

    def test_rejects_receiver_leaving_the_reach(self):
        field, mask, receiver, kinds, member, reach = base_arrays((3., 2., 1., .5), 1,
                                                                 reach=[True, True, False, False])
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=receiver,
                                        terminal_kind=kinds, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=1.0, safe_capacity_m3=1.0)

    def test_rejects_receiver_below_minus_one(self):
        # -2 must never be read as an extra terminal: it is refused before any clipping
        field, mask, receiver, kinds, member, reach = base_arrays((3., 2., 1., .5), 2)
        broken = receiver.copy()
        broken[0, 0] = -2
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=broken,
                                        terminal_kind=kinds, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=1.0, safe_capacity_m3=1.0)
        beyond = receiver.copy()
        beyond[0, 1] = 99
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=beyond,
                                        terminal_kind=kinds, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=1.0, safe_capacity_m3=1.0)

    def test_rejects_cycle_and_two_terminals(self):
        field, mask, receiver, kinds, member, reach = base_arrays((3., 2., 1.), 1)
        cycle = receiver.copy()
        cycle[0, 1] = 0
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=cycle,
                                        terminal_kind=kinds, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=1.0, safe_capacity_m3=1.0)
        two = receiver.copy()
        two[0, 0] = -1
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=two,
                                        terminal_kind=kinds, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=1.0, safe_capacity_m3=1.0)

    def test_rejects_lake_bed_that_routes_out(self):
        field, mask, receiver, kinds, member, reach = base_arrays((3., 2., 1., .5), 1)
        leaky = np.array([True, False, False, True])
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=receiver,
                                        terminal_kind=kinds, member_mask=leaky,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=1.0, safe_capacity_m3=1.0)

    def test_rejects_open_or_unknown_kinds_and_bad_capacity(self):
        field, mask, receiver, kinds, member, reach = base_arrays((3., 2., 1., .5), 1)
        opened = kinds.copy()
        opened[0, 0] = 'open_outflow'
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=receiver,
                                        terminal_kind=opened, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=1.0, safe_capacity_m3=1.0)
        unknown = np.zeros(field.size, bool)
        unknown[0] = True
        curve = LakeStageCurve(field.reshape(-1)[member], AREA)
        level = curve.floor_level_m + 0.25
        capacity = float(curve.volume(level))
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=receiver,
                                        terminal_kind=kinds, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=level, safe_capacity_m3=capacity,
                                        upstream_unknown_mask=unknown)
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(elevation_m=field, resolved_mask=mask, receiver=receiver,
                                        terminal_kind=kinds, member_mask=member,
                                        reach_mask=reach, cell_area_m2=AREA,
                                        safe_level_m=level, safe_capacity_m3=capacity * 1.5)


class EventTests(unittest.TestCase):
    def test_zero_rain_on_an_empty_state_produces_no_water(self):
        domain, curve, _, _ = build()
        state = initial_event_state(domain, parameters=DRY)
        outcome = advance_finite_event(domain, state['soil_states_mm'], 0.0, 0.0,
                                       dt_s=900.0, parameters=DRY)
        self.assertEqual(outcome['ledger']['rain_total_m3'], 0.0)
        self.assertEqual(outcome['ledger']['delivered_to_lake_m3'], 0.0)
        self.assertEqual(outcome['lake_volume_m3'], 0.0)
        self.assertTrue(outcome['lake']['dry'])
        self.assertEqual(outcome['lake']['wet_cells'], 0)
        self.assertEqual(outcome['lake']['level_m'], curve.floor_level_m)
        self.assertEqual(float(np.abs(outcome['routed_q_m3_s_active']).max()), 0.0)
        # the dry empty state is a fixed point of the frozen kernel too
        self.assertEqual(float(np.abs(outcome['soil_states_mm']).max()), 0.0)

    def test_positive_rain_releases_soil_and_fills_the_lake_exactly_once(self):
        domain, _, _, _ = build()
        state = initial_event_state(domain, parameters=DRY)
        outcome = advance_finite_event(domain, state['soil_states_mm'], 0.0, 2.0,
                                       dt_s=900.0, parameters=DRY)
        ledger = outcome['ledger']
        self.assertGreater(ledger['land_release_m3'], 0.0)
        self.assertGreater(ledger['delivered_to_lake_m3'], 0.0)
        self.assertEqual(ledger['delivered_to_lake_m3'], ledger['routed_total_m3'])
        self.assertAlmostEqual(ledger['local_input_m3'], ledger['routed_total_m3'], places=12)
        self.assertAlmostEqual(ledger['rain_lake_m3'],
                               2.0 * 0.25 * AREA / 1000.0 * domain.member_cells, places=12)
        self.assertAlmostEqual(ledger['rain_land_m3'],
                               2.0 * 0.25 * AREA / 1000.0 * domain.land_cells, places=12)
        self.assertGreater(outcome['lake_volume_m3'], 0.0)
        self.assertFalse(outcome['lake']['dry'])
        self.assertGreater(outcome['lake']['wet_cells'], 0)
        self.assertGreater(float(outcome['routed_q_m3_s_active'].sum()), 0.0)
        self.assertLessEqual(outcome['lake']['level_m'], domain.safe_level_m + 1e-12)

    def test_rain_stops_and_the_finite_inventory_declines(self):
        domain, _, _, _ = build()
        rain = [4.0, 4.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        run = run_finite_event(domain, initial_event_state(domain, parameters=FAST), rain,
                               dt_s=900.0, parameters=FAST)
        delivered = [step['delivered_to_lake_m3'] for step in run['steps']]
        self.assertTrue(all(value > 0.0 for value in delivered))
        self.assertLess(delivered[-1], max(delivered))
        tail = delivered[3:]
        self.assertTrue(all(later < earlier for earlier, later in zip(tail, tail[1:])))
        final_soil = soil_volume_m3(run['final_state']['soil_states_mm'], AREA)
        rain_phase = run['steps'][:3]
        stored_at_rain_end = (sum(step['ledger']['rain_total_m3'] for step in rain_phase)
                              - sum(step['ledger']['delivered_to_lake_m3'] for step in rain_phase))
        self.assertLess(final_soil, stored_at_rain_end)
        # the all-excess limb never fills the soil store, so its decline is in the quick store
        self.assertEqual(float(np.abs(run['final_state']['soil_states_mm'][0]).max()), 0.0)
        self.assertGreater(float(run['final_state']['soil_states_mm'][1].max()), 0.0)
        self.assertGreater(run['final_state']['lake_volume_m3'], 0.0)

    def test_cumulative_delivery_is_not_counted_twice(self):
        domain, _, _, _ = build()
        rain = [3.0, 3.0, 0.0, 0.0]
        run = run_finite_event(domain, initial_event_state(domain, parameters=DRY), rain,
                               dt_s=900.0, parameters=DRY)
        delivered = sum(step['ledger']['delivered_to_lake_m3'] for step in run['steps'])
        routed = sum(step['ledger']['routed_total_m3'] for step in run['steps'])
        local = sum(step['ledger']['local_input_m3'] for step in run['steps'])
        self.assertAlmostEqual(delivered, routed, places=12)
        self.assertAlmostEqual(delivered, local, places=12)
        self.assertAlmostEqual(run['final_state']['lake_volume_m3'], delivered, places=12)
        self.assertAlmostEqual(run['delivered_total_m3'], delivered, places=12)
        edges = [step['seconds_edges'] for step in run['steps']]
        self.assertEqual(edges[0], [0.0, 900.0])
        self.assertEqual(edges[-1][1], 4 * 900.0)

    def test_nonzero_initial_inventories_close_the_external_account(self):
        domain, _, _, _ = build()
        parameters = RunoffParameters(initial_soil_mm=10.0, initial_fast_mm=2.0,
                                      initial_slow_mm=1.0)
        state = initial_event_state(domain, parameters=parameters)
        state['lake_volume_m3'] = 5.0
        state = {'soil_states_mm': state['soil_states_mm'], 'lake_volume_m3': 5.0,
                 'elapsed_s': 0.0}
        run = run_finite_event(domain, state, [0.0, 0.0], dt_s=900.0, parameters=parameters)
        account = run['account']
        self.assertTrue(account['closed'], account)
        self.assertLessEqual(abs(account['residual_m3']),
                             BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * account['inputs_m3'])
        self.assertAlmostEqual(account['initial_lake_m3'], 5.0, places=12)
        self.assertGreater(account['initial_soil_m3'], 0.0)
        self.assertGreater(account['et_m3'], 0.0)
        self.assertEqual(account['units'], 'm3')

    def test_capacity_overflow_is_refused_without_touching_inputs(self):
        levels = (3.0, 2.0, 1.0, 0.6, 0.4)
        field, mask, receiver, kinds, member, reach = base_arrays(levels, 2)
        curve = LakeStageCurve(field.reshape(-1)[member], AREA)
        level = curve.floor_level_m + 1e-9
        capacity = float(curve.volume(level))
        domain = prepare_finite_event_domain(
            elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
            member_mask=member, reach_mask=reach, cell_area_m2=AREA,
            safe_level_m=level, safe_capacity_m3=capacity)
        state = initial_event_state(domain, parameters=FAST)
        states = state['soil_states_mm'].copy()
        with self.assertRaises(ValueError):
            advance_finite_event(domain, states, 0.0, 40.0, dt_s=900.0, parameters=FAST)
        self.assertTrue(np.array_equal(states, state['soil_states_mm']))
        with self.assertRaises(ValueError):
            advance_finite_event(domain, states, capacity + 1.0, 0.0, dt_s=900.0,
                                 parameters=FAST)

    def test_invalid_timestep_and_state_are_refused(self):
        domain, _, _, _ = build()
        state = initial_event_state(domain, parameters=DRY)
        with self.assertRaises(ValueError):
            advance_finite_event(domain, state['soil_states_mm'], 0.0, 1.0, dt_s=0.0,
                                 parameters=DRY)
        with self.assertRaises(ValueError):
            advance_finite_event(domain, state['soil_states_mm'][:, :-1], 0.0, 1.0, dt_s=900.0,
                                 parameters=DRY)


class AccountTests(unittest.TestCase):
    def test_account_terms_and_gate_are_m3(self):
        account = water_account(rain_volume_m3=100.0, initial_soil_m3=10.0, final_soil_m3=40.0,
                                initial_lake_m3=0.0, final_lake_m3=60.0, et_volume_m3=10.0)
        self.assertEqual(account['inputs_m3'], 110.0)
        self.assertEqual(account['outputs_m3'], 110.0)
        self.assertEqual(account['residual_m3'], 0.0)
        self.assertTrue(account['closed'])
        self.assertEqual(account['gate_m3'], BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * 110.0)
        bad = water_account(rain_volume_m3=100.0, initial_soil_m3=0.0, final_soil_m3=0.0,
                            initial_lake_m3=0.0, final_lake_m3=0.0, et_volume_m3=0.0)
        self.assertFalse(bad['closed'])
        self.assertIn(ROUTING_POLICY, account['semantics'])


if __name__ == '__main__':
    unittest.main()
