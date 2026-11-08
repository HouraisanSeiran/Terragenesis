"""Durable cold-only fine pulse commits in the existing saved-case schemas."""

import json
import math
import os
from pathlib import Path
import tempfile
import time

import numpy as np
import psutil

from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
from terrain_pipeline.td_entry_pulse_execution_v2 import advance_pulse_cold
from terrain_pipeline.td_entry_pulse_propagation import validate_experiment
from terrain_pipeline.td_entry_shallow_water import MAX_BYTES, MAX_CELLS, MAX_WORK, FLAGS, check_resource, finish
from tools.prepare_td_entry_shallow_water import load, save

EXECUTION_VERSION = 'td-entry-pulse-execution-v2-cold'
SNAPSHOT_SCHEMA = 'td-entry-pulse-incremental-snapshot-v1'


def atomic_index(path, record):
    target = Path(path)
    payload = (json.dumps(record, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf8')
    descriptor, temporary = tempfile.mkstemp(prefix='.pulse-index-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PulseLock:
    """Exclusive PID lock; stale locks require explicit operator investigation."""

    def __init__(self, path, run_identity):
        self.path = Path(path)
        self.record = dict(pid=os.getpid(), process_create_time=psutil.Process().create_time(),
                           run_identity=run_identity, snapshot_resumable=False)

    def __enter__(self):
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf8') as stream:
                json.dump(self.record, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            self.path.unlink()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.path.unlink()


def snapshot_binding(carrier, geometry, forcing, max_dt_s, code_sha256):
    return dict(source_identity=carrier['identity_sha256'], forcing_identity=forcing['identity_sha256'],
                geometry_identity_sha256=geometry['identity_sha256'], max_dt_requested_s=max_dt_s,
                execution_version=EXECUTION_VERSION, code_sha256=code_sha256,
                snapshot_resumable=False, restart_requires_time_zero=True)


def read_snapshot(snapshot_pin, expected_binding):
    record = load(snapshot_pin)
    meta, arrays = record['metadata'], record['arrays']
    if meta['schema'] != SNAPSHOT_SCHEMA or any(meta.get(key) != value for key, value in expected_binding.items()):
        raise ValueError('snapshot_identity_or_cold_only_policy_mismatch')
    interval = meta['interval']
    if (type(interval) is not int or interval < 0 or meta['time_s'] != (interval+1)*meta['interval_s'] or
            arrays['interval__time_end_s'].item() != meta['time_s'] or
            arrays['rk__time_start_s'].item() != interval*meta['interval_s']):
        raise ValueError('snapshot_global_time_mismatch')
    depth, momentum = arrays['depth_m'], arrays['momentum_m2_s']
    if (depth.dtype != np.float64 or depth.ndim != 2 or np.any(depth < 0) or
            momentum.dtype != np.float64 or momentum.shape != (depth.size, 2) or arrays['ledger'].shape != (5,) or
            not np.array_equal(depth.ravel(), arrays['interval__depth_after_m']) or
            not np.array_equal(momentum, arrays['interval__momentum_after'])):
        raise ValueError('snapshot_real_state_shape_or_continuity_mismatch')
    if meta['actual_face_work_units'] != meta['face_evaluations']*3//2:
        raise ValueError('snapshot_work_mismatch')
    return record


def run_fine_cold(carrier, geometry, forcing, *, output, code_sha256, on_commit,
                  max_dt_s=.005, work_limit=MAX_WORK, wall_limit_s=7200.):
    """Run once from dry time zero; saved intervals are not resume inputs."""
    validate_experiment(carrier, geometry, forcing)
    if (type(work_limit) is not int or not 0 < work_limit <= MAX_WORK or
            not math.isfinite(wall_limit_s) or not 0 < wall_limit_s <= 7200.):
        raise ValueError('fine_work_or_wall_budget')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('cold_fine_requires_empty_snapshot_directory_no_resume')
    interval_s = forcing['metadata']['interval_s']
    intervals = len(forcing['arrays']['time_s'])-1
    shape = geometry['arrays']['H2_m'].shape
    estimate = geometry['arrays']['H2_m'].size*8*(90+80*intervals)
    if estimate+psutil.Process().memory_info().rss > MAX_BYTES:
        raise MemoryError('saved_witness_estimate_exceeds_1GiB')
    budget = SurfaceBudget(max_dt_s=max_dt_s, max_cells=MAX_CELLS,
                           max_face_evaluations=work_limit*2//3, max_bytes=MAX_BYTES,
                           max_duration_s=forcing['metadata']['duration_s'], max_wall_s=wall_limit_s,
                           max_snapshots=max(3, intervals+1), max_depth_m=20.)
    binding = snapshot_binding(carrier, geometry, forcing, max_dt_s, code_sha256)
    pending, snapshots = {}, []
    started = time.monotonic()

    def capture(name):
        def receive(packet):
            pending[name] = {key: np.asarray(value).copy() for key, value in packet.items()}
        return receive

    def commit(packet):
        progress = {key: value for key, value in packet.items() if not isinstance(value, np.ndarray)}
        arrays = {key: value for key, value in packet.items() if isinstance(value, np.ndarray)}
        for name in ('interval', 'rk'):
            if int(pending[name]['interval']) != packet['interval']:
                raise ValueError('observer_interval_mismatch')
            arrays.update({name+'__'+key: value for key, value in pending[name].items()})
        scalar_keys = [key for key, value in arrays.items() if value.ndim == 0]
        meta = dict(binding, **progress, schema=SNAPSHOT_SCHEMA, interval_s=interval_s, budget=vars(budget),
                    observer_scalar_keys=scalar_keys)
        checkpoint = finish(arrays, meta)
        snapshot_pin = save(output/('interval-'+str(packet['interval']+1).zfill(2)+'.npz'), checkpoint)
        snapshots.append(snapshot_pin)
        pending.clear()
        on_commit(snapshot_pin, progress)

    result = advance_pulse_cold(geometry,
        initial_depth_m=forcing['arrays']['initial_depth_m'][0], forcing_interval_s=interval_s, intervals=intervals,
        forcing_provider=lambda interval: forcing['arrays']['forcing_m3_s'][0, interval].reshape(shape),
        boundary_stage_provider=lambda interval: forcing['arrays']['boundary_stage_m'][0, interval],
        source_identity=carrier['identity_sha256'], forcing_identity=forcing['identity_sha256'], budget=budget,
        snapshot_interval_s=interval_s, interval_observer=capture('interval'), momentum_observer=capture('rk'),
        checkpoint_observer=commit)
    meta = dict(result['metadata'], schema='td-entry-shallow-water-state-v1',
                geometry_identity_sha256=geometry['identity_sha256'], case_index=0,
                case_name=forcing['metadata']['case_names'][0], max_dt_requested_s=max_dt_s,
                diagnostics=result['diagnostics'], gross_boundary_per_face_certified=False,
                gross_boundary_semantics='unchanged v1: all-substep gross totals; first RK only, no per-face gross certification',
                total_wall_s=time.monotonic()-started, **FLAGS)
    state = finish(result['arrays'], meta)
    del result
    observer_arrays = dict(interval={}, rk={})
    for snapshot_pin in snapshots:
        snapshot = read_snapshot(snapshot_pin, binding)
        for key, value in snapshot['arrays'].items():
            for name in observer_arrays:
                prefix = name+'__'
                if key.startswith(prefix):
                    if key in snapshot['metadata']['observer_scalar_keys']:
                        value = value.reshape(())
                    observer_arrays[name].setdefault(key[len(prefix):], []).append(value)
        del snapshot
        check_resource()
    transfers = finish({key: np.stack(values) for key, values in observer_arrays['interval'].items()},
        dict(schema='td-entry-shallow-water-intervals-v1', state_identity_sha256=state['identity_sha256'],
             internal_sign='left to right', boundary_sign='outward positive', mass_units='m3',
             momentum_transfer_units='m4/s', bed_drag_impulse_units='m2/s', **FLAGS))
    del observer_arrays['interval']
    first_rk = finish({key: np.stack(values) for key, values in observer_arrays['rk'].items()},
        dict(schema='td-entry-shallow-water-first-rk-v1', state_identity_sha256=state['identity_sha256'],
             semantics='actual first SSPRK2 substep per forcing interval only, not all-substep gross witness', **FLAGS))
    check_resource()
    return state, transfers, first_rk
