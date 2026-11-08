"""Synthetic duals for block-scheduled finite events, port exchange and checkpoint resume."""
import hashlib
import inspect
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.finite_river_block_schedule import (
    CHECKPOINT_FILES,
    DISPATCH_ORDERS,
    BlockSchedule,
    PortExchange,
    advance_block_event,
    check_layout_cover,
    layout_from_block_of,
    load_checkpoint,
    prepare_block_layout,
    run_block_event,
    save_checkpoint,
)
from terrain_pipeline.surface_rivers.finite_river_event import (
    LakeStageCurve,
    prepare_finite_event_domain,
    soil_volume_m3,
)

AREA = 900.0
DRY = RunoffParameters(initial_soil_mm=0.0)
FAST = RunoffParameters(infiltration_capacity_mm_h=0.0, initial_soil_mm=0.0)


def chain_domain(levels, member_count):
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
    curve = LakeStageCurve(field.reshape(-1)[member], AREA)
    level = curve.floor_level_m + 0.25
    domain = prepare_finite_event_domain(
        elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
        member_mask=member, reach_mask=np.ones(columns, bool), cell_area_m2=AREA,
        safe_level_m=level, safe_capacity_m3=float(curve.volume(level)),
        upstream_unknown_mask=np.zeros(field.size, bool))
    return domain


def confluence_domain():
    """2x3 grid: cells 0,1,2 drain into 3->5 and 4->5, with 5 the retained terminal."""
    field = np.array([[3.0, 2.5, 1.5], [3.5, 1.0, 0.5]], np.float64)
    mask = np.ones((2, 3), bool)
    receiver = np.array([[3, 4, 5], [5, 5, -1]], np.int64)
    kinds = np.array([['interior', 'interior', 'interior'],
                      ['interior', 'interior', 'retained']], 'U24')
    member = np.array([[False, False, False], [False, True, True]])
    curve = LakeStageCurve(field.reshape(-1)[member.reshape(-1)], AREA)
    level = curve.floor_level_m + 0.25
    domain = prepare_finite_event_domain(
        elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
        member_mask=member, reach_mask=np.ones(6, bool).reshape(2, 3), cell_area_m2=AREA,
        safe_level_m=level, safe_capacity_m3=float(curve.volume(level)),
        upstream_unknown_mask=np.zeros(6, bool))
    return domain


def schedule_for(domain, block_of, order='forward'):
    layout = layout_from_block_of(domain, np.asarray(block_of, np.int64))
    return BlockSchedule(domain, layout, dispatch_order=order)


def initial(domain, parameters=DRY):
    states = np.zeros((3, domain.land_cells), np.float64)
    for row, value in enumerate((parameters.initial_soil_mm, parameters.initial_fast_mm,
                                 parameters.initial_slow_mm)):
        states[row] = float(value)
    return {'soil_states_mm': states, 'lake_volume_m3': 0.0, 'elapsed_s': 0.0}


class LayoutTests(unittest.TestCase):
    def test_row_bands_are_deterministic_and_cover_every_cell(self):
        domain = confluence_domain()
        layout = prepare_block_layout(domain, 2)
        self.assertEqual(layout.cells, 6)
        self.assertEqual(sum(layout.sizes()), 6)
        self.assertTrue(all(size > 0 for size in layout.sizes()))
        self.assertTrue(check_layout_cover(layout, layout.masks()))
        again = prepare_block_layout(domain, 2)
        self.assertEqual(layout.sha256(), again.sha256())
        # a one-row support cannot host two row bands; that is refused rather than faked
        with self.assertRaises(ValueError):
            prepare_block_layout(chain_domain((3.0, 2.0, 1.0, 0.6, 0.4), 2), 2)

    def test_empty_negative_and_inconsistent_layouts_are_refused(self):
        domain = chain_domain((3.0, 2.0, 1.0, 0.6, 0.4), 2)
        with self.assertRaises(ValueError):
            layout_from_block_of(domain, np.array([0, 0, 2, 2, 2]))
        with self.assertRaises(ValueError):
            layout_from_block_of(domain, np.array([0, 0, -1, 1, 1]))
        with self.assertRaises(ValueError):
            layout_from_block_of(domain, np.array([0, 0, 0, 0]))
        layout = layout_from_block_of(domain, np.array([0, 0, 1, 1, 1]))
        with self.assertRaises(ValueError):
            check_layout_cover(layout, np.stack([np.ones(5, bool), np.ones(5, bool)]))
        with self.assertRaises(ValueError):
            check_layout_cover(layout, np.stack([np.array([True, True, True, True, False]),
                                                 np.array([False, False, True, True, False])]))


class ScheduleTests(unittest.TestCase):
    def test_block_graph_may_cycle_while_the_cell_dag_does_not(self):
        domain = chain_domain((3.0, 2.0, 1.0, 0.6, 0.4), 2)
        schedule = schedule_for(domain, [0, 1, 0, 1, 0])
        pairs = schedule.metadata()['cross_block_edge_pairs']
        self.assertIn('0->1', pairs)
        self.assertIn('1->0', pairs)          # the block graph really is cyclic
        state = initial(domain)
        outcome = advance_block_event(schedule, state['soil_states_mm'], 0.0, 2.0, dt_s=900.0,
                                      parameters=DRY, elapsed_s=0.0, interval_index=0)
        self.assertEqual(outcome['dispatch']['waves'] >= 1, True)
        self.assertTrue(outcome['complete_mask'].all())
        self.assertGreater(outcome['ledger']['delivered_to_lake_m3'], 0.0)

    def test_confluence_from_two_blocks_delivers_each_donor_once(self):
        domain = confluence_domain()
        schedule = schedule_for(domain, [1, 0, 1, 0, 1, 0])
        state = initial(domain)
        outcome = advance_block_event(schedule, state['soil_states_mm'], 0.0, 4.0, dt_s=900.0,
                                      parameters=DRY, elapsed_s=0.0, interval_index=0)
        ledger = outcome['ledger']
        self.assertAlmostEqual(ledger['local_input_m3'], ledger['delivered_to_lake_m3'], places=12)
        self.assertEqual(sum(ledger['block_balance_m3']) * 0.0, 0.0)
        for value in ledger['block_balance_m3']:
            self.assertLessEqual(abs(value), 1e-8)
        inbound = sum(ledger['port_in_by_block_m3'])
        outbound = sum(ledger['port_out_by_block_m3'])
        self.assertAlmostEqual(inbound, outbound, places=12)
        self.assertGreater(inbound, 0.0)
        self.assertAlmostEqual(ledger['port_exchange_m3'], inbound, places=12)

    def test_dispatch_order_changes_the_event_stream_but_not_the_water(self):
        domain = confluence_domain()
        state = initial(domain)
        results = {}
        for order in DISPATCH_ORDERS:
            schedule = schedule_for(domain, [1, 0, 1, 0, 1, 0], order)
            results[order] = advance_block_event(schedule, state['soil_states_mm'], 0.0, 4.0,
                                                 dt_s=900.0, parameters=DRY, elapsed_s=0.0,
                                                 interval_index=0)
        forward = results['forward']['exchange']['source'].tolist()
        reverse = results['reverse']['exchange']['source'].tolist()
        self.assertNotEqual(forward, reverse)          # the dispatch order is real
        reference = results['forward']['routed_q_m3_s']
        for order in DISPATCH_ORDERS:
            self.assertTrue(np.array_equal(results[order]['routed_q_m3_s'], reference))
            self.assertEqual(results[order]['lake_volume_m3'],
                             results['forward']['lake_volume_m3'])
            self.assertTrue(np.array_equal(results[order]['soil_states_mm'],
                                           results['forward']['soil_states_mm']))

    def test_duplicate_port_delivery_is_refused(self):
        exchange = PortExchange()
        exchange.record(0, 1, 7, 9, 0.5, 900.0)
        with self.assertRaises(ValueError):
            exchange.record(0, 2, 7, 9, 0.5, 900.0)
        exchange.record(1, 1, 7, 9, 0.5, 900.0)      # a new interval is a new delivery
        self.assertAlmostEqual(exchange.total_volume_m3(), 900.0, places=12)

    def test_unknown_upstream_is_refused_by_preparation_not_washed(self):
        # the prepared finite domain already refuses unknown upstream, so the scheduler carries no
        # dirty input and ``complete_mask`` is an invariant report rather than restart state
        names = set(inspect.signature(advance_block_event).parameters)
        self.assertFalse({'dirty', 'upstream_unknown_mask'} & names)
        levels = (3.0, 2.0, 1.0, 0.6, 0.4)
        columns = len(levels)
        field = np.array([list(levels)], np.float64)
        mask = np.ones((1, columns), bool)
        receiver = np.full((1, columns), -1, np.int64)
        kinds = np.full((1, columns), 'inactive', 'U24')
        for column in range(columns - 1):
            receiver[0, column] = column + 1
            kinds[0, column] = 'interior'
        kinds[0, -1] = 'retained'
        member = np.array([False, False, False, True, True])
        curve = LakeStageCurve(field.reshape(-1)[member], AREA)
        level = curve.floor_level_m + 0.25
        unknown = np.zeros(columns, bool)
        unknown[1] = True
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(
                elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
                member_mask=member, reach_mask=np.ones(columns, bool), cell_area_m2=AREA,
                safe_level_m=level, safe_capacity_m3=float(curve.volume(level)),
                upstream_unknown_mask=unknown)
        cut = np.array([False, False, True, True, True])   # reach cuts off donors 0 -> 1 -> 2
        with self.assertRaises(ValueError):
            prepare_finite_event_domain(
                elevation_m=field, resolved_mask=mask, receiver=receiver, terminal_kind=kinds,
                member_mask=member, reach_mask=cut, cell_area_m2=AREA,
                safe_level_m=level, safe_capacity_m3=float(curve.volume(level)))

    def test_capacity_overflow_refuses_the_interval(self):
        domain = chain_domain((3.0, 2.0, 1.0, 0.6, 0.4), 2)
        tight = prepare_finite_event_domain(
            elevation_m=np.array([[3.0, 2.0, 1.0, 0.6, 0.4]]),
            resolved_mask=np.ones((1, 5), bool),
            receiver=np.array([[1, 2, 3, 4, -1]], np.int64),
            terminal_kind=np.array([['interior', 'interior', 'interior', 'interior',
                                     'retained']], 'U24'),
            member_mask=np.array([False, False, False, True, True]),
            reach_mask=np.ones(5, bool), cell_area_m2=AREA,
            safe_level_m=float(LakeStageCurve(np.array([0.6, 0.4]), AREA).floor_level_m) + 1e-9,
            safe_capacity_m3=float(LakeStageCurve(np.array([0.6, 0.4]), AREA)
                                   .volume(LakeStageCurve(np.array([0.6, 0.4]), AREA)
                                           .floor_level_m + 1e-9)))
        schedule = schedule_for(tight, [0, 0, 1, 1, 1])
        state = initial(tight, FAST)
        with self.assertRaises(ValueError):
            advance_block_event(schedule, state['soil_states_mm'], 0.0, 40.0, dt_s=900.0,
                                parameters=FAST, elapsed_s=0.0, interval_index=0)
        self.assertGreater(domain.land_cells, 0)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.domain = chain_domain((3.0, 2.0, 1.0, 0.6, 0.4), 2)
        self.schedule = schedule_for(self.domain, [0, 0, 1, 1, 1])
        self.rain = [2.0, 2.0, 0.0, 0.0]
        self.run = run_block_event(self.schedule, initial(self.domain), self.rain, dt_s=900.0,
                                   parameters=DRY)
        self.steps = self.run['steps']
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.directory.cleanup()

    def checkpoint(self, index=2, name='ck', *, cumulative=None, initial_totals=None):
        root = Path(self.directory.name) / name
        partial = run_block_event(self.schedule, initial(self.domain), self.rain[:index],
                                  dt_s=900.0, parameters=DRY)
        area = self.domain.cell_area_m2
        totals = {'rain_m3': partial['rain_volume_m3'],
                  'et_m3': partial['et_total_m3'],
                  'delivered_m3': partial['delivered_total_m3'],
                  'soil_volume_m3': soil_volume_m3(partial['final_state']['soil_states_mm'], area)}
        started = {'soil_m3': soil_volume_m3(partial['initial_state']['soil_states_mm'], area),
                   'lake_m3': partial['initial_state']['lake_volume_m3']}
        saved = save_checkpoint(
            root, schedule=self.schedule, state=partial['final_state'], interval_index=index,
            cumulative=totals if cumulative is None else cumulative,
            initial=started if initial_totals is None else initial_totals,
            dt_s=900.0, parameters=DRY, rain_sequence=self.rain, protocol_sha256='abc')
        return root, partial, saved

    def test_roundtrip_continues_to_the_same_event(self):
        root, partial, saved = self.checkpoint()
        loaded = load_checkpoint(root, schedule=self.schedule, expected_interval_index=2,
                                 dt_s=900.0, parameters=DRY, rain_sequence=self.rain,
                                 protocol_sha256='abc')
        self.assertTrue(np.array_equal(loaded['state']['soil_states_mm'],
                                       partial['final_state']['soil_states_mm']))
        self.assertEqual(loaded['state']['lake_volume_m3'],
                         partial['final_state']['lake_volume_m3'])
        tail = run_block_event(self.schedule, loaded['state'], self.rain[2:], dt_s=900.0,
                               parameters=DRY, start_index=2)
        for offset, step in enumerate(tail['steps']):
            reference = self.steps[2 + offset]
            self.assertTrue(np.array_equal(step['soil_states_mm'], reference['soil_states_mm']))
            self.assertTrue(np.array_equal(step['routed_q_m3_s'], reference['routed_q_m3_s']))
            self.assertEqual(step['lake_volume_m3'], reference['lake_volume_m3'])
        self.assertEqual(saved['state_sha256'], loaded['manifest']['state_sha256'])

    def test_misaligned_or_damaged_checkpoints_are_refused(self):
        root, _, _ = self.checkpoint()
        cases = {
            'wrong_index': dict(expected_interval_index=1),
            'wrong_dt': dict(dt_s=1800.0),
            'wrong_parameters': dict(parameters=FAST),
            'wrong_protocol': dict(protocol_sha256='other'),
            'wrong_forcing': dict(rain_sequence=[2.0, 2.0, 0.0, 5.0]),
        }
        base = dict(schedule=self.schedule, expected_interval_index=2, dt_s=900.0,
                    parameters=DRY, rain_sequence=self.rain, protocol_sha256='abc')
        for name, override in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    load_checkpoint(root, **{**base, **override})
        with self.assertRaises(ValueError):
            load_checkpoint(root, **{**base, 'schedule': schedule_for(
                self.domain, [0, 1, 0, 1, 0])})
        state_path = root / CHECKPOINT_FILES[0]
        raw = bytearray(state_path.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        state_path.write_bytes(bytes(raw))
        with self.assertRaises(ValueError):
            load_checkpoint(root, **base)

    def test_missing_members_and_existing_targets_are_refused(self):
        root, partial, _ = self.checkpoint()
        area = self.domain.cell_area_m2
        totals = {'rain_m3': partial['rain_volume_m3'], 'et_m3': partial['et_total_m3'],
                  'delivered_m3': partial['delivered_total_m3'],
                  'soil_volume_m3': soil_volume_m3(partial['final_state']['soil_states_mm'], area)}
        started = {'soil_m3': soil_volume_m3(partial['initial_state']['soil_states_mm'], area),
                   'lake_m3': partial['initial_state']['lake_volume_m3']}
        with self.assertRaises(FileExistsError):
            save_checkpoint(root, schedule=self.schedule, state=partial['final_state'],
                            interval_index=2, cumulative=totals, initial=started,
                            dt_s=900.0, parameters=DRY, rain_sequence=self.rain)
        (root / CHECKPOINT_FILES[1]).unlink()
        with self.assertRaises(FileNotFoundError):
            load_checkpoint(root, schedule=self.schedule, expected_interval_index=2, dt_s=900.0,
                            parameters=DRY, rain_sequence=self.rain, protocol_sha256='abc')

    def test_empty_continuation_at_the_end_is_legal(self):
        root, partial, _ = self.checkpoint(index=4, name='end')
        loaded = load_checkpoint(root, schedule=self.schedule, expected_interval_index=4,
                                 dt_s=900.0, parameters=DRY, rain_sequence=self.rain,
                                 protocol_sha256='abc')
        tail = run_block_event(self.schedule, loaded['state'], self.rain[4:], dt_s=900.0,
                               parameters=DRY, start_index=4)
        self.assertEqual(tail['intervals'], 0)
        self.assertTrue(np.array_equal(tail['final_state']['soil_states_mm'],
                                       partial['final_state']['soil_states_mm']))
        self.assertEqual(tail['final_state']['lake_volume_m3'],
                         partial['final_state']['lake_volume_m3'])
        self.assertEqual(tail['final_state']['elapsed_s'], 4 * 900.0)
        self.assertTrue(tail['account']['closed'])
        self.assertAlmostEqual(tail['account']['final_lake_m3'],
                               partial['final_state']['lake_volume_m3'], places=12)

    def test_cumulative_totals_must_bind_state_and_forcing(self):
        area = self.domain.cell_area_m2
        partial = run_block_event(self.schedule, initial(self.domain), self.rain[:2],
                                  dt_s=900.0, parameters=DRY)
        good = {'rain_m3': partial['rain_volume_m3'], 'et_m3': partial['et_total_m3'],
                'delivered_m3': partial['delivered_total_m3'],
                'soil_volume_m3': soil_volume_m3(partial['final_state']['soil_states_mm'], area)}
        started = {'soil_m3': 0.0, 'lake_m3': 0.0}
        for key in good:
            tampered = dict(good)
            tampered[key] = good[key] + 1.0
            with self.subTest(field=key):
                with self.assertRaises(ValueError):
                    save_checkpoint(Path(self.directory.name) / ('bad-' + key),
                                    schedule=self.schedule, state=partial['final_state'],
                                    interval_index=2, cumulative=tampered, initial=started,
                                    dt_s=900.0, parameters=DRY, rain_sequence=self.rain)
        with self.assertRaises(ValueError):
            save_checkpoint(Path(self.directory.name) / 'missing-key', schedule=self.schedule,
                            state=partial['final_state'], interval_index=2,
                            cumulative={key: value for key, value in good.items()
                                        if key != 'et_m3'},
                            initial=started, dt_s=900.0, parameters=DRY,
                            rain_sequence=self.rain)
        with self.assertRaises(ValueError):
            save_checkpoint(Path(self.directory.name) / 'extra-key', schedule=self.schedule,
                            state=partial['final_state'], interval_index=2,
                            cumulative=dict(good, extra=0.0), initial=started, dt_s=900.0,
                            parameters=DRY, rain_sequence=self.rain)
        # a manifest written after the fact is refused at load time as well
        root, _, _ = self.checkpoint(name='tamper-manifest')
        manifest = json.loads((root / CHECKPOINT_FILES[1]).read_text(encoding='utf-8'))
        manifest['cumulative']['et_m3'] = manifest['cumulative']['et_m3'] + 1.0
        (root / CHECKPOINT_FILES[1]).write_text(json.dumps(manifest, sort_keys=True),
                                               encoding='utf-8')
        with self.assertRaises(ValueError):
            load_checkpoint(root, schedule=self.schedule, expected_interval_index=2, dt_s=900.0,
                            parameters=DRY, rain_sequence=self.rain, protocol_sha256='abc')

    def test_nonzero_initial_inventory_must_be_declared(self):
        area = self.domain.cell_area_m2
        parameters = RunoffParameters(initial_soil_mm=10.0, initial_fast_mm=1.0)
        start = initial(self.domain, parameters)
        start['lake_volume_m3'] = 5.0
        partial = run_block_event(self.schedule, start, self.rain[:2], dt_s=900.0,
                                  parameters=parameters)
        totals = {'rain_m3': partial['rain_volume_m3'], 'et_m3': partial['et_total_m3'],
                  'delivered_m3': partial['delivered_total_m3'],
                  'soil_volume_m3': soil_volume_m3(partial['final_state']['soil_states_mm'], area)}
        with self.assertRaises(ValueError):
            save_checkpoint(Path(self.directory.name) / 'zero-initial', schedule=self.schedule,
                            state=partial['final_state'], interval_index=2, cumulative=totals,
                            initial={'soil_m3': 0.0, 'lake_m3': 0.0}, dt_s=900.0,
                            parameters=parameters, rain_sequence=self.rain)
        declared = {'soil_m3': soil_volume_m3(partial['initial_state']['soil_states_mm'], area),
                    'lake_m3': 5.0}
        saved = save_checkpoint(Path(self.directory.name) / 'declared', schedule=self.schedule,
                                state=partial['final_state'], interval_index=2,
                                cumulative=totals, initial=declared, dt_s=900.0,
                                parameters=parameters, rain_sequence=self.rain)
        self.assertEqual(saved['initial']['lake_m3'], 5.0)
        self.assertGreater(saved['initial']['soil_m3'], 0.0)

    def test_invalid_state_is_refused_at_the_end_boundary(self):
        # k = len(rain) has no following step, so NaN/negative state must be caught here
        root, _, _ = self.checkpoint(index=4, name='end-invalid')
        manifest = json.loads((root / CHECKPOINT_FILES[1]).read_text(encoding='utf-8'))
        with np.load(root / CHECKPOINT_FILES[0]) as archive:
            payload = {key: np.array(archive[key]) for key in archive.files}

        def tampered_case(name, mutate):
            target = Path(self.directory.name) / name
            shutil.copytree(root, target)
            values = {key: np.array(value) for key, value in payload.items()}
            values, changes = mutate(values)
            np.savez_compressed(target / CHECKPOINT_FILES[0], **values)
            written = dict(manifest)
            written.update(changes)
            written['state_sha256'] = hashlib.sha256(
                (target / CHECKPOINT_FILES[0]).read_bytes()).hexdigest()
            (target / CHECKPOINT_FILES[1]).write_text(json.dumps(written), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_checkpoint(target, schedule=self.schedule, expected_interval_index=4,
                                dt_s=900.0, parameters=DRY, rain_sequence=self.rain,
                                protocol_sha256='abc')

        def nan_lake(values):
            values['lake_volume_m3'] = np.array([np.nan], np.float64)
            return values, {'lake_volume_m3': float('nan')}

        def negative_elapsed(values):
            values['lake_volume_m3'] = np.array([0.0], np.float64)
            values['elapsed_s'] = np.array([-900.0], np.float64)
            return values, {'lake_volume_m3': 0.0, 'elapsed_s': -900.0}

        def wrong_shape(values):
            values['soil_states_mm'] = values['soil_states_mm'][:, :-1]
            return values, {'soil_states_shape': [3, int(values['soil_states_mm'].shape[1])]}

        tampered_case('nan-lake', nan_lake)
        tampered_case('negative-elapsed', negative_elapsed)
        tampered_case('wrong-shape', wrong_shape)


if __name__ == '__main__':
    unittest.main()
