"""Run the frozen native flood in monitored, resumable worker phases."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import psutil

ROOT = Path('.scratch/river-upgrade-20261101').resolve()
TERRAIN = ROOT / 'terrain-v3'
GRAPH = ROOT / 'stage1-native-graph-v3'
OUT = ROOT / 'native-final-routing-v1'
IDENTITY = 'c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'


def memory():
    import ctypes
    from ctypes import wintypes
    class PerformanceInformation(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
            ('CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal', 'PhysicalAvailable',
             'SystemCache', 'KernelTotal', 'KernelPaged', 'KernelNonpaged', 'PageSize')] + [
            ('HandleCount', wintypes.DWORD), ('ProcessCount', wintypes.DWORD), ('ThreadCount', wintypes.DWORD)]
    info = PerformanceInformation()
    info.cb = ctypes.sizeof(info)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
        raise OSError('GetPerformanceInfo failed')
    return psutil.virtual_memory().available, (info.CommitLimit - info.CommitTotal) * info.PageSize


def worker(phase):
    import terrain_pipeline.drainage as flood
    binding = json.loads((OUT / 'binding.json').read_text(encoding='utf8'))
    if flood.flood_phase_digest(TERRAIN / 'manifest.json') != binding['terrain_manifest'] or flood.flood_phase_digest(GRAPH / 'manifest.json') != binding['graph_manifest']:
        raise ValueError('manifest binding changed')
    source = json.loads((TERRAIN / 'manifest.json').read_text(encoding='utf8'))
    graph_manifest = json.loads((GRAPH / 'manifest.json').read_text(encoding='utf8'))
    # Inputs were fully authenticated once by the supervisor, before any worker.
    flood.authenticate = lambda terrain, graph, expected: (source, graph_manifest)
    routing = OUT / 'routing'
    if phase == 'a':
        flood.phase_a(TERRAIN, GRAPH, routing, IDENTITY)
    elif phase == 'b':
        flood.phase_b(TERRAIN, GRAPH, routing, IDENTITY)
    else:
        from terrain_pipeline.new_world_stage1 import derive_native_hydrology
        graph = {name: flood.mapped(GRAPH, name) for name in ('indptr', 'indices')}
        route = {name: flood.mapped(routing, name) for name in ('filled', 'order', 'rank', 'receiver')}
        bed, ocean, unknown, valid = (flood.mapped(TERRAIN, name) for name in ('bed_m', 'ocean_mask', 'unknown_mask', 'valid_mask'))
        result = derive_native_hydrology(graph, route, bed, ocean, unknown, valid, (-2048, -2048), IDENTITY, OUT / 'derived')
        counts = {'pools': len(result['pools']['id']), 'mouths': len(result['mouths']['id'])}
        del result, graph, route, bed, ocean, unknown, valid
        import gc
        gc.collect()
        for name in ('_stack.npy', '_terminal_ids.npy'):
            (OUT / 'derived' / name).unlink()
        files = {p.name: flood.flood_phase_digest(p) for p in sorted((OUT / 'derived').glob('*.npy'))}
        flood.atomic_json(OUT / 'derived.json', {'counts': counts, 'files_sha256': files, 'cell_area_m2': 900})


def main():
    import terrain_pipeline.drainage as flood
    OUT.mkdir(exist_ok=True)
    binding_path = OUT / 'binding.json'
    if not binding_path.exists():
        source, graph = flood.authenticate(TERRAIN, GRAPH, IDENTITY)
        if source['shape_zx'] != [4096, 4096] or source['origin_native_xz'] != [-2048, -2048] or graph['total_edges'] != 100636044:
            raise ValueError('unexpected native artifact')
        flood.atomic_json(binding_path, {'terrain_manifest': flood.flood_phase_digest(TERRAIN / 'manifest.json'), 'graph_manifest': flood.flood_phase_digest(GRAPH / 'manifest.json'), 'identity': IDENTITY})
    else:
        binding = json.loads(binding_path.read_text(encoding='utf8'))
        if binding['identity'] != IDENTITY or binding['terrain_manifest'] != flood.flood_phase_digest(TERRAIN / 'manifest.json') or binding['graph_manifest'] != flood.flood_phase_digest(GRAPH / 'manifest.json'):
            raise ValueError('binding changed')
    if (OUT / 'routing/phase_b.json').exists():
        record = json.loads((OUT / 'routing/phase_b.json').read_text(encoding='utf8'))
        for name, expected in record['files'].items():
            if flood.flood_phase_digest(OUT / 'routing' / (name + '.npy')) != expected:
                raise ValueError('routing checkpoint mismatch: ' + name)
    for phase, marker, partial in [('a', OUT / 'routing/phase_a.json', OUT / 'routing'), ('b', OUT / 'routing/phase_b.json', None), ('derived', OUT / 'derived.json', OUT / 'derived')]:
        if marker.exists():
            print('checkpoint exists:', phase, flush=True)
            continue
        if partial and partial.exists():
            shutil.rmtree(partial)
        available, commit = memory()
        if available < 1024**3 or commit < 2*1024**3:
            raise RuntimeError(f'resource admission: available={available} commit={commit}')
        started = time.monotonic()
        proc = subprocess.Popen([sys.executable, '-m', 'tools.run_native_final_routing', phase])
        process = psutil.Process(proc.pid)
        peak_rss = peak_private = 0
        min_avail, min_commit = available, commit
        last_progress = 0
        while proc.poll() is None:
            available, commit = memory()
            min_avail, min_commit = min(min_avail, available), min(min_commit, commit)
            rss = private = 0
            try:
                children = process.children(recursive=True)
                for member in [process, *children]:
                    try:
                        info = member.memory_full_info()
                        rss += info.rss
                        private += getattr(info, 'private', 0)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except psutil.NoSuchProcess:
                children = []
            peak_rss = max(peak_rss, rss)
            peak_private = max(peak_private, private)
            elapsed = time.monotonic() - started
            if elapsed - last_progress >= 30:
                print(json.dumps({'phase': phase, 'elapsed_s': round(elapsed), 'available': available, 'commit_headroom': commit, 'peak_rss': peak_rss, 'peak_private_commit': peak_private}), flush=True)
                last_progress = elapsed
            if available < 1024**3 or commit < 2*1024**3:
                for child in reversed(children):
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                proc.terminate()
                proc.wait()
                _, alive = psutil.wait_procs(children, timeout=5)
                for child in alive:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                psutil.wait_procs(alive, timeout=5)
                flood.atomic_json(OUT / (phase + '-measurements.json'), {'phase': phase, 'seconds': elapsed, 'peak_rss': peak_rss, 'peak_private_commit': peak_private, 'minimum_available': min_avail, 'minimum_commit_headroom': min_commit, 'status': 'resource abort'})
                raise RuntimeError(f'resource abort {phase}: available={available} commit={commit}')
            time.sleep(.5)
        stats = {'phase': phase, 'seconds': time.monotonic() - started, 'peak_rss': peak_rss, 'peak_private_commit': peak_private, 'minimum_available': min_avail, 'minimum_commit_headroom': min_commit, 'exit_code': proc.returncode}
        flood.atomic_json(OUT / (phase + '-measurements.json'), stats)
        print(json.dumps(stats), flush=True)
        if proc.returncode or not marker.exists():
            raise RuntimeError('worker failed: ' + phase)


if __name__ == '__main__':
    if len(sys.argv) == 2:
        worker(sys.argv[1])
    else:
        main()
