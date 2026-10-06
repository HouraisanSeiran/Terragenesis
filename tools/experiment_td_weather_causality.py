"""Limited common-initial-state experiments; unchanged original v9 formulas."""

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import psutil
from numba import njit
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_storage_compiled import advance_hour
from terrain_pipeline.td_basin_transport_v6 import _compiled_exchange, validate_cfl
from terrain_pipeline.td_basin_storage_compiled_io import load_checkpoint, load_storage
from tools.verify_td_native_weather_storage import ResourceMonitor


@njit(cache=True)
def transport_only(depth, bed, faces, boundary, widths, spacing, seconds, count):
    forward = np.zeros(len(faces))
    reverse = np.zeros(len(faces))
    exported = np.zeros(len(boundary))
    indices = np.empty(0, np.int64)
    for step in range(count):
        result = _compiled_exchange(depth, bed, faces, boundary, widths, spacing,
                                    seconds, .6, indices, indices)
        depth = result[0]
        forward += result[1]
        reverse += result[2]
        exported += result[3]
    return depth, forward, reverse, exported


def write(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))


def save_arrays(path, **arrays):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    publish_bytes(path, buffer.getvalue())
    return {'path': str(path.resolve()), 'sha256': file_sha256(path)}


def run(index_path, expected_sha256):
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError('single-thread environment required')
    if file_sha256(index_path) != expected_sha256:
        raise ValueError('external index SHA mismatch')
    index = json.loads(index_path.read_text(encoding='utf-8'))
    pages = index['scenarios']['eastward']['pages']
    fine_pin = pages['1.25'][17]['checkpoint']
    coarse_pin = pages['2.5'][17]['checkpoint']
    fine = load_checkpoint(**fine_pin)
    coarse = load_checkpoint(**coarse_pin)
    page_pin = pages['1.25'][17]['storage']
    saved = load_storage(**page_pin)
    arrays = saved['arrays']
    bed = arrays['height_m'].ravel()
    faces = arrays['face_cells']
    boundary = arrays['boundary_cells']
    widths = arrays['boundary_width_m']
    receiver = arrays['receiver']
    spacing = saved['metadata']['spacing_m']
    names = ('depth_m', 'soil_mm', 'fast_mm', 'slow_mm')
    errors = ('error_depth', 'error_soil', 'error_fast', 'error_slow')
    parameters = fine['metadata']['runoff_parameters']
    runoff = np.array([parameters[key] for key in ('infiltration_capacity_mm_h',
        'soil_capacity_mm', 'potential_et_mm_h', 'percolation_mm_h', 'fast_tau_s', 'slow_tau_s')])
    config = np.array([.6, 1e-9, .15])
    destination = ROOT / 'verification/td-basin-generation' / ('A-weather-causality-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    sources = ('tools/experiment_td_weather_causality.py', 'terrain_pipeline/td_basin_storage_compiled.py',
        'terrain_pipeline/td_basin_transport_v6.py', 'terrain_pipeline/td_basin_storage_compiled_io.py',
        'terrain_pipeline/td_basin_forcing_compensated.py', 'tools/verify_td_native_weather_storage.py')
    hashes = {name: file_sha256(ROOT / name) for name in sources}
    write(destination / 'inputs.json', {'schema': 'td-weather-common-state-causality-v1',
        'index_pin': {'path': str(index_path.resolve()), 'sha256': expected_sha256},
        'fine_checkpoint': fine_pin, 'coarse_checkpoint': coarse_pin, 'static_page': page_pin,
        'common_initial_time_s': fine['metadata']['elapsed_s'], 'duration_s': 3600,
        'steps_s': [2.5, 1.25, .625, .3125], 'original_formulas_unchanged': True,
        'checkpoint_semantics': 'raw experimental restart of states/errors; local count resets to zero; no production checkpoint or cumulative evidence certification',
        'job_max_bytes': 1073741824, 'max_face_steps_per_case': 6000000000,
        'code_sha256': hashes})
    monitor = ResourceMonitor(psutil.Process())
    monitor.start()
    records = {}
    final_states = {}
    cases = [(mode, step, fine) for mode in ('normal', 'transport_only') for step in (2.5, 1.25, .625, .3125)]
    cases.append(('normal_coarse_initial', 1.25, coarse))
    for mode, step, initial in cases:
        count = int(3600 / step)
        work = count * len(faces)
        if work > 6000000000 or count * step != 3600:
            raise ValueError('experimental case budget/time invalid')
        validate_cfl(faces, boundary, widths, spacing, step, .6, len(bed))
        states = np.vstack([initial['arrays'][name] for name in names]).copy()
        compensation = np.vstack([initial['arrays'][name] for name in errors]).copy()
        initial_states = states.copy()
        began = time.perf_counter()
        if mode == 'transport_only':
            depth, forward, reverse, exported = transport_only(states[0], bed, faces, boundary, widths, spacing, step, count)
            states[0] = depth
            ledger = np.zeros((8, len(bed)))
            ledger[7, boundary] = exported
        else:
            output = advance_hour(states, compensation, np.zeros(len(bed)), bed, faces,
                boundary, widths, receiver, spacing, step, count, runoff, config)
            states, compensation, ledger, forward, reverse = output[:5]
        residual = float((spacing**2 * (states[0] - initial_states[0]
            + (states[1:] - initial_states[1:]).sum(axis=0) / 1000)).sum()
            - ledger[0].sum() + ledger[3].sum() + ledger[5].sum() + ledger[7].sum())
        if abs(residual) > 1e-6 or np.any(states < 0):
            raise ValueError(f'causal experiment water budget/positivity failed: {residual}')
        key = f'{mode}-{step:g}'
        artifact = save_arrays(destination / (key + '.npz'), states=states, errors=compensation,
            ledger=ledger, face_forward_m3=forward, face_reverse_m3=reverse)
        final_states[key] = states.copy()
        records[key] = {'artifact': artifact, 'elapsed_s': time.perf_counter()-began,
            'face_steps': work, 'water_residual_m3': residual,
            'hotspot_depth_m': float(states[0, 60279]), 'max_depth_m': float(states[0].max())}
        write(destination / (key + '.json'), records[key])
        monitor.check()
        print(json.dumps({'run': str(destination), 'case': key, **records[key]}, ensure_ascii=True), flush=True)
    comparisons = {}
    for mode in ('normal', 'transport_only'):
        for first, second in ((2.5, 1.25), (1.25, .625), (.625, .3125)):
            difference = final_states[f'{mode}-{first:g}'][0] - final_states[f'{mode}-{second:g}'][0]
            comparisons[f'{mode}-{first:g}-vs-{second:g}'] = {
                'max_depth_difference_m': float(abs(difference).max()),
                'max_cell': int(abs(difference).argmax()),
                'hotspot_difference_m': float(difference[60279])}
    difference = final_states['normal_coarse_initial-1.25'][0] - final_states['normal-1.25'][0]
    initial_difference = coarse['arrays']['depth_m'] - fine['arrays']['depth_m']
    comparisons['initial_state_effect_at_same_1.25s'] = {
        'initial_max_difference_m': float(abs(initial_difference).max()),
        'initial_hotspot_difference_m': float(initial_difference[60279]),
        'final_max_difference_m': float(abs(difference).max()),
        'final_hotspot_difference_m': float(difference[60279])}
    tiny = []
    actual_rain = float(load_storage(**pages['1.25'][0]['storage'])['arrays']['rain_mm_h'][0,60279])
    for initial_depth in (0., .99e-9, 1.01e-9, 1e-6):
        for step in (2.5, 1.25, .625, .3125):
            state = np.array([[initial_depth], [30.], [0.], [0.]])
            output = advance_hour(state, np.zeros_like(state), np.array([actual_rain]),
                np.array([bed[60279]]), np.empty((0,2),np.int64), np.empty(0,np.int64),
                np.empty(0), np.array([-1]), spacing, step, int(3600/step), runoff, config)
            tiny.append({'initial_depth_m': initial_depth, 'step_s': step, 'rain_mm_h': actual_rain,
                'final_states': output[0][:,0].tolist(), 'lake_rain_m3': float(output[2][1,0]),
                'land_rain_m3': float(output[2][2,0])})
    monitor.stop()
    monitor.check()
    if file_sha256(index_path) != expected_sha256 or any(file_sha256(ROOT/name) != sha for name, sha in hashes.items()):
        raise ValueError('frozen input/code changed')
    write(destination / 'report.json', {'schema': 'td-weather-causal-isolation-report-v1',
        'records': records, 'comparisons': comparisons, 'forcing_only_actual_rain_cases': tiny,
        'resource': monitor.record(), 'scope': 'one original TD hour from common pinned state; forcing-only one-cell threshold perturbations',
        'original_formulas_unchanged': True, 'hydraulic_ready': False, 'publishable': False})
    print(json.dumps({'report': str(destination/'report.json'), 'sha256': file_sha256(destination/'report.json')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--index-sha256', required=True)
    arguments = parser.parse_args()
    run(arguments.index, arguments.index_sha256)
