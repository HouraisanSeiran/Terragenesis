"""Transactional current FV scheduler, independent of historical runner modules."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import time

import numpy as np
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import MorphodynamicStepTooLarge
from tools import natural_fv_growth_interval as interval
from tools.natural_fv_growth_state_io import (STATE, CONTRACT, bind_parameters, file_sha256,
    identities, load_checkpoint, read_arrays, save_checkpoint)


def remove_trial(path, output):
    resolved = path.resolve()
    if resolved.parent != output.resolve() or not resolved.name.startswith('.trial-') or not resolved.name[7:].isdigit():
        raise ValueError("refusing to remove a path outside this output's numbered trial directories")
    if resolved.exists():
        shutil.rmtree(resolved)


def finish(output, snapshots, times, data, start_meta, meta, ledgers, args, started, status, attempts):
    arrays = {key: np.asarray(value) for key, value in snapshots.items()}
    arrays.update(time_s=np.asarray(times), **{key: data[key] for key in
        ('source_floor_m', 'cell_type', 'initial_bed_m', 'local_world_xz_m', 'fixed_boundary_mask')})
    arrays['stage_m'] = arrays['bed_m'] + arrays['depth_m']
    np.savez_compressed(output / 'result.npz', **arrays)
    initial = float(((arrays['bed_m'][0] - data['source_floor_m']) * 25. * .65).sum() + arrays['suspended_solid_m3'][0].sum())
    final = float(((arrays['bed_m'][-1] - data['source_floor_m']) * 25. * .65).sum() + arrays['suspended_solid_m3'][-1].sum())
    injected = meta['cumulative_injected_solid_m3'] - start_meta['cumulative_injected_solid_m3']
    exported = meta['cumulative_exported_solid_m3'] - start_meta['cumulative_exported_solid_m3']
    water = np.zeros(3)
    for path in sorted(output.glob('chunk-audit-*.npz')):
        with np.load(path, allow_pickle=False) as block:
            boundary = block['water_boundary_transfer_m3']
            water += [block['water_forcing_volume_m3'].sum(), -np.minimum(boundary, 0.).sum(), np.maximum(boundary, 0.).sum()]
    checkpoint = sorted(output.glob('checkpoint-*.npz'))[-1]
    parameters = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    parameters.update(intervals=len(ledgers), adaptive_intervals=True)
    report = {'schema': 'finite-FV-suspended-growth-v4', 'status': status, 'checkpoint': str(checkpoint),
        'checkpoint_sha256': file_sha256(checkpoint), 'start': start_meta, 'end': meta, 'parameters': parameters,
        'planned_duration_s': args.duration_s, 'actual_duration_s': float(times[-1] - times[0]),
        'initial_bed_plus_suspended_solid_m3': initial, 'final_bed_plus_suspended_solid_m3': final,
        'injected_solid_m3': injected, 'exported_solid_m3': exported,
        'combined_residual_solid_m3': final + exported - initial - injected,
        'maximum_phase_residual_solid_m3': max(abs(row['combined_residual_solid_m3']) for row in ledgers),
        'remaining_finite_source_solid_m3': meta['source_total_solid_m3'] - meta['cumulative_injected_solid_m3'],
        'water_supplied_imported_exported_m3': water.tolist(),
        'water_volume_residual_m3': float((arrays['depth_m'][-1] - arrays['depth_m'][0]).sum() * 25. - water[0] - water[1] + water[2]),
        'implementation_hashes': identities(), 'runtime_s': time.monotonic() - started, 'attempts': attempts,
        'exchange_config': meta.get('exchange_config'), 'bedload_transport_contract': deepcopy(CONTRACT),
        'limitations': 'same-direction interval-net carrier bound on finite MPM bedload; no oscillatory gross/wave-driven counterflow; v3 exchange and slope; no wave radiation stress; adaptive time accuracy not certified'}
    (output / 'interval-ledgers.json').write_text(json.dumps(ledgers, indent=2), encoding='utf-8')
    (output / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def run(args, *, execute_interval=None):
    if args.recover_completed_prefix:
        raise ValueError('old prefixes require explicit legacy replay')
    if not args.resume:
        raise ValueError('explicit complete current checkpoint required')
    if (args.duration_s <= 0. or args.chunk_duration_s <= 0. or args.interval_s not in (2., 1., .5, .25, .125, .0625)
            or not 0. < args.min_interval_s <= args.interval_s):
        raise ValueError('positive duration/chunk/minimum interval and initial power-of-two interval <=2s required')
    execute_interval = interval.run if execute_interval is None else execute_interval
    started = time.monotonic()
    data, meta = load_checkpoint(args.resume)
    bind_parameters(meta, args)
    if args.append_source:
        interval.append_source(data, meta, args.append_source)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'packets').mkdir()
    snapshots = {key: [data[key].copy()] for key in STATE}
    times = [meta['physical_time_s']]
    start_meta = deepcopy(meta)
    ledgers, attempts = [], []
    target = times[0] + args.duration_s
    dt, done, trial_number = args.interval_s, 0, 0
    while meta['physical_time_s'] < target - 1.e-9:
        remaining = target - meta['physical_time_s']
        trial_dt = min(dt, remaining)
        count = min(64, max(1, int(min(args.chunk_duration_s, remaining) / trial_dt + 1.e-10)))
        trial_number += 1
        temporary = args.output / f'.trial-{trial_number:06d}'
        trial_input = args.output / '.trial-input.npz'
        save_checkpoint(trial_input, {key: value.copy() for key, value in data.items()}, deepcopy(meta))
        trial_args = deepcopy(args)
        trial_args.resume, trial_args.output = trial_input, temporary
        trial_args.intervals, trial_args.interval_s, trial_args.chunk_intervals = count, trial_dt, count
        trial_args.append_source = None
        try:
            report = execute_interval(trial_args)
        except MorphodynamicStepTooLarge as error:
            attempts.append({'attempt': trial_number, 'status': 'rejected', 'time_s': meta['physical_time_s'],
                'interval_s': trial_dt, 'interval_count': count, 'error': str(error),
                'source_cursor_unchanged_s': meta['source_cursor_s']})
            (args.output / 'attempts.json').write_text(json.dumps(attempts, indent=2), encoding='utf-8')
            remove_trial(temporary, args.output)
            trial_input.unlink()
            if dt <= args.min_interval_s:
                raise
            dt = max(args.min_interval_s, dt * .5)
            continue
        reported_checkpoint = Path(report['checkpoint']).resolve(strict=True)
        if reported_checkpoint.parent != temporary.resolve():
            raise ValueError('FV interval checkpoint must belong to its trial directory')
        next_data, next_meta = load_checkpoint(reported_checkpoint, expected_sha256=report['checkpoint_sha256'])
        next_meta.update(resumed_checkpoint=start_meta['resumed_checkpoint'],
                         resumed_checkpoint_sha256=start_meta['resumed_checkpoint_sha256'])
        block_ledgers = json.loads((temporary / 'interval-ledgers.json').read_text(encoding='utf-8'))
        if len(block_ledgers) != count:
            raise ValueError('FV trial interval ledger count differs from requested chunk')
        expected_cursor = meta['source_cursor_s']
        expected_loads = []
        for _ in range(count):
            load, _, expected_cursor = interval.forcing_step(data['source_schedule'], expected_cursor, trial_dt,
                args.source_time_scale, args.max_input_concentration, args.river_q, args.supply_off)
            expected_loads.append(load)
        if (next_meta['physical_time_s'] != meta['physical_time_s'] + count * trial_dt
                or next_meta['source_cursor_s'] != expected_cursor
                or next_meta['cumulative_injected_solid_m3'] != meta['cumulative_injected_solid_m3'] + sum(expected_loads)
                or next_meta['cumulative_exported_solid_m3'] != meta['cumulative_exported_solid_m3'] + sum(row['exported_solid_m3'] for row in block_ledgers)):
            raise ValueError('FV trial checkpoint time/cursor/injected or exported amount differs from complete chunk')
        for key in ('source_floor_m', 'source_schedule', 'initial_bed_m', 'cell_type', 'fixed_boundary_mask', 'local_world_xz_m'):
            if (next_data[key].dtype != data[key].dtype or next_data[key].shape != data[key].shape
                    or next_data[key].tobytes() != data[key].tobytes()):
                raise ValueError('FV trial changed immutable source/geometry state: ' + key)
        for index, row in enumerate(block_ledgers):
            if (row['physical_time_start_s'] != meta['physical_time_s'] + index * trial_dt
                    or row['physical_time_end_s'] != meta['physical_time_s'] + (index + 1) * trial_dt):
                raise ValueError('FV trial ledger time differs from requested interval')
        for path in (temporary / 'packets').glob('*.npz'):
            number, _ = path.name.split('-', 1)
            if not number.isdigit() or not 0 <= int(number) < count:
                raise ValueError('FV trial packet number outside committed chunk')
        for index, row in enumerate(block_ledgers):
            row['global_interval'] = done + index
        done += count
        audit_path = next(temporary.glob('chunk-audit-*.npz'))
        shutil.move(str(audit_path), args.output / f'chunk-audit-{done:07d}.npz')
        save_checkpoint(args.output / f'checkpoint-{done:07d}.npz', next_data, next_meta)
        for path in (temporary / 'packets').glob('*.npz'):
            number, suffix = path.name.split('-', 1)
            shutil.move(str(path), args.output / 'packets' / f'{done - count + int(number):07d}-{suffix}')
        data, meta = next_data, next_meta
        ledgers.extend(block_ledgers)
        for key in STATE:
            snapshots[key].append(data[key].copy())
        times.append(meta['physical_time_s'])
        peak = max(row['maximum_bed_change_m'] for row in block_ledgers)
        attempts.append({'attempt': trial_number, 'status': 'committed', 'interval_s': trial_dt,
            'interval_count': count, 'end_time_s': meta['physical_time_s'], 'peak_bed_change_m': peak})
        (args.output / 'attempts.json').write_text(json.dumps(attempts, indent=2), encoding='utf-8')
        (args.output / 'interval-ledgers.json').write_text(json.dumps(ledgers, indent=2), encoding='utf-8')
        remove_trial(temporary, args.output)
        trial_input.unlink()
        if peak < args.max_bed_change * .2 and dt < args.interval_s:
            dt = min(args.interval_s, dt * 2.)
        if time.monotonic() - started > args.max_wall_s:
            raise RuntimeError('wall budget reached; resume last committed current checkpoint')
    return finish(args.output, snapshots, times, data, start_meta, meta, ledgers, args, started, 'completed', attempts)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('parent', 'water-run', 'resume', 'append-source'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--duration-s', type=float, required=True)
    p.add_argument('--chunk-duration-s', type=float, default=16.)
    p.add_argument('--min-interval-s', type=float, default=.0625)
    p.add_argument('--recover-completed-prefix', type=Path)
    p.add_argument('--intervals', type=int, default=32)
    p.add_argument('--chunk-intervals', type=int, default=16)
    p.add_argument('--interval-s', type=float, default=2.)
    p.add_argument('--source-time-scale', type=float, default=1.)
    p.add_argument('--max-input-concentration', type=float, default=.01)
    p.add_argument('--supply-off', action='store_true')
    p.add_argument('--river-q', type=float)
    p.add_argument('--sea-mean', type=float, default=0.)
    p.add_argument('--tide-amplitude', type=float, default=0.)
    p.add_argument('--tide-period', type=float, default=44714.)
    p.add_argument('--tide-phase', type=float, default=0.)
    p.add_argument('--wave-height', type=float, default=0.)
    p.add_argument('--wave-period', type=float, default=5.)
    p.add_argument('--settling-velocity', type=float, default=.005)
    p.add_argument('--max-bed-change', type=float, default=.01)
    p.add_argument('--packet-stride', type=int, default=1)
    p.add_argument('--max-wall-s', type=float, default=7200.)
    p.add_argument('--max-bytes-mib', type=int, default=768)
    p.add_argument('--disable-exchange', action='store_true')
    p.add_argument('--erosion-velocity', type=float, default=1.e-5)
    p.add_argument('--exchange-max-concentration', type=float, default=.03)
    p.add_argument('--disable-slope', action='store_true')
    p.add_argument('--critical-slope', type=float, default=.35)
    p.add_argument('--slope-mobility', type=float, default=.02)
    return p
