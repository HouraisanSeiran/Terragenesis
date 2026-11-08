"""Static synthetic material scaling; no terrain or hydrological generation."""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
import tracemalloc
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.geology import make_material_field
SEED = 20261002
SPACING = 30
ORIGIN = (-184320, 61440)
LIMIT_BYTES = 1024 ** 3

def sample(shape, row=0, col=0):
    return make_material_field(shape, origin_m_xz=(ORIGIN[0] + col * SPACING, ORIGIN[1] + row * SPACING), spacing_m=SPACING, seed=SEED)

def hashes(bundle):
    return {name: hashlib.sha256(values.tobytes()).hexdigest() for name, values in bundle['arrays'].items()}

def memory():
    current, peak = tracemalloc.get_traced_memory()
    result = {'traced_current_bytes': current, 'traced_peak_bytes': peak}
    try:
        import psutil
        process = psutil.Process()
        information = process.memory_info()
        result['process_rss_bytes'] = information.rss
        result['process_peak_working_set_bytes'] = getattr(information, 'peak_wset', information.rss)
    except ImportError:
        if sys.platform == 'win32':

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong), ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t), ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            query = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
            query.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_ulong]
            if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                raise OSError(ctypes.get_last_error(), 'GetProcessMemoryInfo failed')
            result['process_rss_bytes'] = counters.WorkingSetSize
            result['process_peak_working_set_bytes'] = counters.PeakWorkingSetSize
        else:
            result['process_rss_bytes'] = None
    if max((value for value in result.values() if value is not None)) > LIMIT_BYTES:
        raise ValueError('material scaling job exceeded 1GiB memory budget')
    return result

def full_case(size):
    tracemalloc.reset_peak()
    started = perf_counter()
    field = sample((size, size))
    expected = hashes(field)
    identity = field['identity_sha256']
    first_memory = memory()
    replay = sample((size, size))
    assert replay['identity_sha256'] == identity and hashes(replay) == expected
    replay_memory = memory()
    del replay
    for row, col in ((0, 0), (size - 32, size - 32), (size // 2 - 8, size // 2 - 8)):
        window = sample((32, 32), row, col)
        for name, values in field['arrays'].items():
            np.testing.assert_array_equal(window['arrays'][name], values[row:row + 32, col:col + 32])
        del window
    maximum_adjacent_difference = {name: float(max(np.max(np.abs(np.diff(values, axis=0))), np.max(np.abs(np.diff(values, axis=1))))) for name, values in field['arrays'].items() if values.dtype.kind == 'f'}
    result = {'shape': [size, size], 'identity_sha256': identity, 'array_sha256': expected, 'same_seed_exact': True, 'global_windows_exact': True, 'native_array_bytes': sum((values.nbytes for values in field['arrays'].values())), 'maximum_adjacent_difference': maximum_adjacent_difference, 'memory_after_first': first_memory, 'memory_with_replay': replay_memory, 'elapsed_s': perf_counter() - started}
    del field
    return result

def tiled_case(size=2048, tile_size=512):
    tracemalloc.reset_peak()
    started = perf_counter()
    positions = [(row, col) for row in range(0, size, tile_size) for col in range(0, size, tile_size)]
    reference = {}
    peaks = []
    for reverse in (False, True):
        ordered = list(reversed(positions)) if reverse else positions
        for row, col in ordered:
            field = sample((tile_size, tile_size), row, col)
            record = {'identity_sha256': field['identity_sha256'], 'array_sha256': hashes(field)}
            if reverse:
                assert reference[row, col] == record
            else:
                reference[row, col] = record
            if col + tile_size < size:
                seam = sample((tile_size, 2), row, col + tile_size - 1)
                neighbor = sample((tile_size, 1), row, col + tile_size)
                for name in field['arrays']:
                    np.testing.assert_array_equal(seam['arrays'][name][:, 0], field['arrays'][name][:, -1])
                    np.testing.assert_array_equal(seam['arrays'][name][:, 1], neighbor['arrays'][name][:, 0])
                del seam, neighbor
            if row + tile_size < size:
                seam = sample((2, tile_size), row + tile_size - 1, col)
                neighbor = sample((1, tile_size), row + tile_size, col)
                for name in field['arrays']:
                    np.testing.assert_array_equal(seam['arrays'][name][0], field['arrays'][name][-1])
                    np.testing.assert_array_equal(seam['arrays'][name][1], neighbor['arrays'][name][0])
                del seam, neighbor
            peaks.append(memory())
            del field
    canonical = [{'row': row, 'col': col, **reference[row, col]} for row, col in positions]
    aggregate = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'logical_shape': [size, size], 'tile_shape': [tile_size, tile_size], 'tile_count': len(positions), 'aggregate_tile_manifest_sha256': aggregate, 'hash_semantics': 'canonical sorted tile hashes; not a full-array byte hash', 'tile_records': canonical, 'forward_reverse_exact': True, 'overlapping_seams_exact': True, 'maximum_observed_memory': {name: max((item[name] for item in peaks if item[name] is not None)) for name in peaks[0] if any((item[name] is not None for item in peaks))}, 'full_domain_array_allocated': False, 'elapsed_s': perf_counter() - started}

def verify(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    tracemalloc.start()
    try:
        complete = [full_case(512), full_case(1024)]
        tiled = tiled_case()
        report = {'verified': True, 'model': 'static synthetic continuous material field only', 'large_river_network_generated': False, 'hydrology_run': False, 'seed': SEED, 'spacing_m': SPACING, 'origin_m_xz': list(ORIGIN), 'memory_budget_bytes': LIMIT_BYTES, 'complete_fields': complete, 'windowed_2048': tiled, 'code_sha256': {name: file_sha256(ROOT / name) for name in ('terrain_pipeline/geology.py', 'tools/verify_td_material_scaling.py')}, 'limitations': '2048 square is a logical global synthetic field sampled in <=1024-cap windows, not a new TD source, hydrological solve or large river-network acceptance. Memory is sampled RSS/OS peak and tracemalloc; not an enforced OS quota.'}
    finally:
        tracemalloc.stop()
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))
    return report
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / ('verification/td-basin-generation/B-material-scaling-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '/report.json'))
    arguments = parser.parse_args()
    result = verify(arguments.output)
    print(json.dumps({'report': str(arguments.output.resolve()), 'verified': result['verified'], 'full_memory': [case['memory_with_replay'] for case in result['complete_fields']], 'windowed_memory': result['windowed_2048']['maximum_observed_memory']}, ensure_ascii=False))
