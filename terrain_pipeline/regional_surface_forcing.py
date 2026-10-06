"""Streaming independent-cell soil forcing for a full-grid surface solver."""
from dataclasses import asdict
import io
import json
import os
import tempfile
from pathlib import Path
import numpy as np
from terrain_pipeline.rainfall_runoff import RunoffParameters, _release
from terrain_pipeline.mountain_storm_forcing import interval_mean_mm_h
from terrain_pipeline.mountain_source_adapter import publish_bytes, file_sha256, checked_archive
from terrain_pipeline.regional_surface_source import validate_source
MAX_CELLS = 65536
MAX_STEPS = 288
MAX_CELL_STEPS = 25000000
MAX_MEMORY_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 512 * 1024 * 1024

def preflight(cells, steps, block_cells, dt_s):
    if any((type(value) is not int for value in (cells, steps, block_cells))) or not 1 <= cells <= MAX_CELLS or (not 1 <= steps <= MAX_STEPS) or (not 1 <= block_cells <= 4096):
        raise ValueError('independent regional forcing dimensions exceeded')
    if not isinstance(dt_s, (int, float)) or isinstance(dt_s, bool) or (not np.isfinite(dt_s)) or (not 0 < dt_s <= 3600):
        raise ValueError('finite positive physical timestep required')
    work = cells * steps
    memory = 8 * cells * 24 + 8 * block_cells * 24
    output = 8 * cells * (steps + 6) + 65536
    if work > MAX_CELL_STEPS or memory > MAX_MEMORY_BYTES or output > MAX_OUTPUT_BYTES:
        raise ValueError('independent regional forcing work/bytes exceeded')
    return {'cell_steps': work, 'estimated_memory_bytes': memory, 'estimated_uncompressed_output_bytes': output, 'max_cell_steps': MAX_CELL_STEPS, 'max_memory_bytes': MAX_MEMORY_BYTES, 'max_output_bytes': MAX_OUTPUT_BYTES}

def advance_soil(rain_mm_h, states, *, dt_s, parameters):
    if not isinstance(parameters, RunoffParameters):
        raise ValueError('explicit runoff parameters required')
    parameters.__post_init__()
    if not isinstance(states, np.ndarray) or states.ndim != 2 or states.shape[0] != 3 or (states.dtype != np.float64) or (not np.isfinite(states).all()) or (states < 0).any():
        raise ValueError('soil/fast/slow finite nonnegative current states required')
    rain = np.asarray(rain_mm_h)
    if rain.shape != (states.shape[1],) or not np.isfinite(rain).all() or (rain < 0).any() or (rain > 1000).any():
        raise ValueError('bounded unique-cell rainfall required')
    if (states[0] > parameters.soil_capacity_mm).any():
        raise ValueError('soil above prescribed capacity')
    if isinstance(dt_s, bool) or not isinstance(dt_s, (int, float)) or not np.isfinite(dt_s) or not 0 < dt_s <= 3600:
        raise ValueError('positive timestep required')
    hours = dt_s / 3600.0
    soil_before, fast_before, slow_before = states
    depth = rain * hours
    infiltration = np.minimum(np.minimum(depth, parameters.infiltration_capacity_mm_h * hours), np.maximum(parameters.soil_capacity_mm - soil_before, 0))
    soil = soil_before + infiltration
    et = np.minimum(soil, parameters.potential_et_mm_h * hours)
    soil -= et
    percolation = np.minimum(soil, parameters.percolation_mm_h * hours)
    soil -= percolation
    fast, fast_release = _release(fast_before, depth - infiltration, dt_s, parameters.fast_tau_s)
    slow, slow_release = _release(slow_before, percolation, dt_s, parameters.slow_tau_s)
    next_states = np.stack((soil, fast, slow))
    release = fast_release + slow_release
    change = (next_states - states).sum(axis=0)
    if np.abs(depth - et - release - change).max() > 1e-10:
        raise ValueError('cell-local rain/soil/release balance failed')
    return (next_states, release, et, change)

def generate_forcing(source, destination, *, steps=288, dt_s=900.0, parameters=None, storm=None, block_cells=4096):
    validate_source(source)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    parameters = RunoffParameters() if parameters is None else parameters
    parameters.__post_init__()
    resources = preflight(65536, steps, block_cells, dt_s)
    meta = {'schema': 'regional-surface-forcing-v1', 'source_identity': source['identity_sha256'], 'steps': steps, 'dt_s': float(dt_s), 'shape': [256, 256], 'cell_area_m2': 900.0, 'parameters': asdict(parameters), 'storm': None if storm is None else asdict(storm), 'resources': resources, 'block_cells': block_cells, 'origin_m_xz': source['metadata']['origin_m_xz'], 'rain_support': 'all-grid conceptual terrestrial soil; includes temporarily wet/depression cells; no lake direct rain', 'B_input': 'runoff_volume_m3 exactly once; never add full rainfall again', 'trust': 'external trusted manifest SHA and payload SHA; balances are not resigned physical-model authentication', 'coordinates': 'origin+index*30m cell centers; footprint center +/-15m', 'surface_initial_storage_m3': 0.0}
    publish_bytes(destination / 'predeclared.json', json.dumps(meta, allow_nan=False, indent=2).encode())
    descriptor, temporary = tempfile.mkstemp(dir=destination, prefix='.forcing-', suffix='.npy')
    os.close(descriptor)
    output = None
    try:
        output = np.lib.format.open_memmap(temporary, mode='w+', dtype=np.float64, shape=(steps, 256, 256))
        states = np.tile(np.array([parameters.initial_soil_mm, parameters.initial_fast_mm, parameters.initial_slow_mm])[:, None], (1, 65536))
        initial = states.copy()
        flat = np.arange(65536)
        origin = meta['origin_m_xz']
        east = origin[0] + flat % 256 * 30.0
        south = origin[1] + flat // 256 * 30.0
        ledger = {key: [] for key in ('rain_m3', 'et_m3', 'runoff_m3', 'storage_change_m3', 'residual_m3')}
        storage = [float(states.sum() * 0.9)]
        soil_storage = [float(states[0].sum() * 0.9)]
        maximum = 0.0
        for step in range(steps):
            totals = np.zeros(5)
            for lower in range(0, 65536, block_cells):
                upper = min(lower + block_cells, 65536)
                rain = np.zeros(upper - lower) if storm is None else interval_mean_mm_h(east[lower:upper], south[lower:upper], float(step * dt_s), float((step + 1) * dt_s), storm)
                updated, release, et, change = advance_soil(rain, states[:, lower:upper], dt_s=dt_s, parameters=parameters)
                states[:, lower:upper] = updated
                runoff = release * 0.9
                rain_volume = rain * dt_s / 3600.0 * 0.9
                residual = rain_volume - et * 0.9 - runoff - change * 0.9
                maximum = max(maximum, float(np.abs(residual).max()))
                output[step].ravel()[lower:upper] = runoff
                totals += np.array([rain_volume.sum(), et.sum() * 0.9, runoff.sum(), change.sum() * 0.9, residual.sum()])
            for key, value in zip(ledger, totals):
                ledger[key].append(float(value))
            storage.append(float(states.sum() * 0.9))
            soil_storage.append(float(states[0].sum() * 0.9))
            output.flush()
            output._mmap.close()
            output = np.lib.format.open_memmap(temporary, mode='r+', dtype=np.float64, shape=(steps, 256, 256))
        output._mmap.close()
        output = None
        os.link(temporary, destination / 'runoff_volume_m3.npy')
        buffer = io.BytesIO()
        np.savez_compressed(buffer, initial_states_mm=initial.reshape(3, 256, 256), final_states_mm=states.reshape(3, 256, 256), seconds_edges=np.arange(steps + 1, dtype=np.float64) * dt_s)
        publish_bytes(destination / 'soil-final-and-time.npz', buffer.getvalue())
        report = {**meta, 'runoff_path': 'runoff_volume_m3.npy', 'runoff_sha256': file_sha256(destination / 'runoff_volume_m3.npy'), 'soil_time_path': 'soil-final-and-time.npz', 'soil_time_sha256': file_sha256(destination / 'soil-final-and-time.npz'), 'ledger': ledger, 'total_soil_fast_slow_storage_m3': storage, 'soil_storage_m3': soil_storage, 'max_cell_residual_m3': maximum, 'total_rain_m3': sum(ledger['rain_m3']), 'total_et_m3': sum(ledger['et_m3']), 'total_runoff_to_B_m3': sum(ledger['runoff_m3']), 'whole_account_residual_m3': sum(ledger['rain_m3']) - sum(ledger['et_m3']) - sum(ledger['runoff_m3']) - storage[-1] + storage[0]}
        publish_bytes(destination / 'manifest.json', json.dumps(report, allow_nan=False, indent=2).encode())
        return report
    except BaseException as error:
        publish_bytes(destination / 'failure.json', json.dumps({'type': type(error).__name__, 'message': str(error)}).encode())
        raise
    finally:
        if output is not None:
            output._mmap.close()
        if os.path.exists(temporary):
            os.unlink(temporary)

def soil_headers(headers, steps):
    if set(headers) != {'initial_states_mm', 'final_states_mm', 'seconds_edges'}:
        raise ValueError('exact soil/time members required')
    for key in ('initial_states_mm', 'final_states_mm'):
        if headers[key] != ((3, 256, 256), np.dtype(np.float64)):
            raise ValueError('typed soil header rejected')
    if headers['seconds_edges'] != ((steps + 1,), np.dtype(np.float64)):
        raise ValueError('typed time header rejected')

def load_forcing(directory, *, expected_manifest_sha256, source_identity):
    directory = Path(directory)
    manifest = directory / 'manifest.json'
    if manifest.stat().st_size > 262144 or file_sha256(manifest) != expected_manifest_sha256:
        raise ValueError('external trusted manifest SHA/budget required')
    from terrain_pipeline.rainfall_runoff import _strict_json
    meta = _strict_json(manifest.read_text(encoding='utf-8'))
    keys = {'schema', 'source_identity', 'steps', 'dt_s', 'shape', 'cell_area_m2', 'parameters', 'storm', 'resources', 'block_cells', 'origin_m_xz', 'rain_support', 'B_input', 'trust', 'coordinates', 'surface_initial_storage_m3', 'runoff_path', 'runoff_sha256', 'soil_time_path', 'soil_time_sha256', 'ledger', 'total_soil_fast_slow_storage_m3', 'soil_storage_m3', 'max_cell_residual_m3', 'total_rain_m3', 'total_et_m3', 'total_runoff_to_B_m3', 'whole_account_residual_m3'}
    if set(meta) != keys or meta['schema'] != 'regional-surface-forcing-v1' or meta['source_identity'] != source_identity:
        raise ValueError('forcing schema/source binding mismatch')
    if meta['resources'] != preflight(65536, meta['steps'], meta['block_cells'], meta['dt_s']) or meta['shape'] != [256, 256] or meta['cell_area_m2'] != 900.0:
        raise ValueError('full-grid resource metadata mismatch')
    if len(meta['origin_m_xz']) != 2 or not np.isfinite(meta['origin_m_xz']).all():
        raise ValueError('finite origin required')
    if meta['origin_m_xz'] != [-184320.0, 61440.0] or meta['surface_initial_storage_m3'] != 0.0:
        raise ValueError('fixed source origin and initial surface contract required')
    for key, value in {'rain_support': 'all-grid conceptual terrestrial soil; includes temporarily wet/depression cells; no lake direct rain', 'B_input': 'runoff_volume_m3 exactly once; never add full rainfall again', 'trust': 'external trusted manifest SHA and payload SHA; balances are not resigned physical-model authentication', 'coordinates': 'origin+index*30m cell centers; footprint center +/-15m'}.items():
        if meta[key] != value:
            raise ValueError('forcing water support/semantics mismatch')
    if meta['storm'] is not None:
        from terrain_pipeline.mountain_storm_forcing import StormParameters
        StormParameters(**meta['storm'])
    parameters = RunoffParameters(**meta['parameters'])
    if meta['runoff_path'] != 'runoff_volume_m3.npy' or meta['soil_time_path'] != 'soil-final-and-time.npz':
        raise ValueError('fixed safe basenames required')
    path = directory / meta['runoff_path']
    if path.stat().st_size > MAX_OUTPUT_BYTES or file_sha256(path) != meta['runoff_sha256']:
        raise ValueError('runoff payload SHA mismatch')
    with open(path, 'rb') as stream:
        if np.lib.format.read_magic(stream) != (1, 0):
            raise ValueError('fixed NPY v1 required')
        shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=4096)
        if shape != (meta['steps'], 256, 256) or fortran or dtype != np.float64 or (stream.tell() + int(np.prod(shape)) * 8 != path.stat().st_size):
            raise ValueError('typed NPY rejected before np.load')
    soil = checked_archive(directory / meta['soil_time_path'], expected_sha256=meta['soil_time_sha256'], max_bytes=4 * 1024 * 1024, header_validator=lambda h: soil_headers(h, meta['steps']))
    if not np.array_equal(soil['seconds_edges'], np.arange(meta['steps'] + 1) * meta['dt_s']):
        raise ValueError('exact T+1 time edges required')
    initial = np.array([parameters.initial_soil_mm, parameters.initial_fast_mm, parameters.initial_slow_mm])[:, None, None]
    if not np.array_equal(soil['initial_states_mm'], np.broadcast_to(initial, (3, 256, 256))):
        raise ValueError('initial state must equal parameters')
    for key in ('initial_states_mm', 'final_states_mm'):
        if not np.isfinite(soil[key]).all() or (soil[key] < 0).any():
            raise ValueError('finite nonnegative soil required')
        soil[key].flags.writeable = False
    ledger = meta['ledger']
    if set(ledger) != {'rain_m3', 'et_m3', 'runoff_m3', 'storage_change_m3', 'residual_m3'}:
        raise ValueError('known T ledger columns required')
    for key, values in ledger.items():
        if len(values) != meta['steps'] or not np.isfinite(values).all() or (key in {'rain_m3', 'et_m3', 'runoff_m3'} and min(values) < 0):
            raise ValueError('finite T ledger required')
    storage = np.asarray(meta['total_soil_fast_slow_storage_m3'])
    soil_storage = np.asarray(meta['soil_storage_m3'])
    if storage.shape != (meta['steps'] + 1,) or soil_storage.shape != storage.shape or (not np.isfinite(storage).all()) or (not np.isfinite(soil_storage).all()):
        raise ValueError('finite T+1 storage required')
    if (storage < 0).any() or (soil_storage < 0).any() or (soil_storage > storage + 1e-07).any():
        raise ValueError('nonnegative consistent soil/component storage required')
    if not np.allclose(np.diff(storage), ledger['storage_change_m3'], rtol=0, atol=1e-06):
        raise ValueError('storage recurrence fails')
    residual = np.asarray(ledger['rain_m3']) - ledger['et_m3'] - np.asarray(ledger['runoff_m3']) - np.diff(storage)
    if np.abs(residual).max() > 1e-06 or not np.allclose(residual, ledger['residual_m3'], rtol=0, atol=1e-06):
        raise ValueError('regional water account fails')
    if not np.allclose([storage[0], storage[-1]], [soil['initial_states_mm'].sum() * 0.9, soil['final_states_mm'].sum() * 0.9], rtol=0, atol=1e-06):
        raise ValueError('initial/final storage mismatch')
    for column, total in (('rain_m3', 'total_rain_m3'), ('et_m3', 'total_et_m3'), ('runoff_m3', 'total_runoff_to_B_m3')):
        if not np.isclose(sum(ledger[column]), meta[total], rtol=0, atol=1e-07):
            raise ValueError('manifest total ledger mismatch')
    whole = sum(ledger['rain_m3']) - sum(ledger['et_m3']) - sum(ledger['runoff_m3']) - storage[-1] + storage[0]
    if not np.isfinite(meta['whole_account_residual_m3']) or not np.isclose(whole, meta['whole_account_residual_m3'], rtol=0, atol=1e-07) or (not np.isfinite(meta['max_cell_residual_m3'])) or (not 0 <= meta['max_cell_residual_m3'] <= 1e-09):
        raise ValueError('finite cumulative account summary required')
    runoff = np.load(path, allow_pickle=False, mmap_mode='r')
    try:
        for step in range(meta['steps']):
            if not np.isfinite(runoff[step]).all() or (runoff[step] < 0).any() or (not np.isclose(runoff[step].sum(), ledger['runoff_m3'][step], rtol=0, atol=1e-07)):
                raise ValueError('saved grid runoff ledger mismatch')
            if (step + 1) % 16 == 0:
                runoff._mmap.close()
                runoff = np.load(path, allow_pickle=False, mmap_mode='r')
        runoff._mmap.close()
        runoff = np.load(path, allow_pickle=False, mmap_mode='r')
    except BaseException:
        runoff._mmap.close()
        raise
    return {'metadata': meta, 'runoff_volume_m3': runoff, 'seconds_edges': soil['seconds_edges'], 'initial_states_mm': soil['initial_states_mm'], 'final_states_mm': soil['final_states_mm']}

def iter_intervals(directory, *, expected_manifest_sha256, source_identity):
    loaded = load_forcing(directory, expected_manifest_sha256=expected_manifest_sha256, source_identity=source_identity)
    try:
        for index, values in enumerate(loaded['runoff_volume_m3']):
            yield (index, values)
    finally:
        loaded['runoff_volume_m3']._mmap.close()
