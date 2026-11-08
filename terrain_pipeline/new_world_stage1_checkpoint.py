"""Checkpointed, CPU-only stage-1 phase workers and their resource monitor."""
import gc
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import psutil
from terrain_pipeline import new_world_stage1 as stage
from terrain_pipeline import td_source as new_world_terrain

PHASES = ('source', 'graph', 'flood', 'derived', 'verified')
DIRS = {'graph': 'graph', 'flood': 'routing', 'derived': 'derived'}


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def memory():
    vm = psutil.virtual_memory()
    if sys.platform == 'win32':
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
        headroom = (info.CommitLimit - info.CommitTotal) * info.PageSize
    else:
        values = {}
        with open('/proc/meminfo', encoding='ascii') as stream:
            for line in stream:
                key, _, value = line.partition(':')
                if key in ('CommitLimit', 'Committed_AS'):
                    values[key] = int(value.split()[0]) * 1024
        headroom = values['CommitLimit'] - values['Committed_AS']
    return {'available_ram_bytes': vm.available, 'commit_headroom_bytes': headroom}


def snapshot(process):
    result = memory()
    rss = private = 0
    try:
        processes = [process] + process.children(recursive=True)
        for child in processes:
            try:
                info = child.memory_full_info()
                rss += info.rss
                private += getattr(info, 'uss', getattr(info, 'private', 0))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except psutil.NoSuchProcess:
        pass
    result.update(rss_bytes=rss, private_bytes=private)
    return result


def terminate_tree(process):
    try:
        children = process.children(recursive=True)
    except psutil.NoSuchProcess:
        children = []
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    try:
        process.terminate()
    except psutil.NoSuchProcess:
        pass
    _, alive = psutil.wait_procs(children + [process], timeout=5)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=5)


def descriptors(root, directory):
    result = {}
    for file in sorted((root / directory).glob('*.npy')):
        a = np.load(file, mmap_mode='r', allow_pickle=False)
        result[file.relative_to(root).as_posix()] = {'sha256': stage._digest(file),
            'dtype': a.dtype.str, 'shape': list(a.shape)}
        del a
    return result


def validate(root, config):
    stored = json.loads((root / 'checkpoint.json').read_text(encoding='utf-8'))
    if stored != config:
        raise ValueError('pending source or configuration mismatch')
    completed = []
    for phase in PHASES:
        path = root / (phase + '.json')
        if not path.exists():
            continue
        if len(completed) != PHASES.index(phase):
            raise ValueError('pending phase order mismatch')
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('phase') != phase or record.get('config_hash') != stage._identity(config):
            raise ValueError('pending phase identity mismatch')
        if phase in DIRS:
            directory = root / DIRS[phase]
            if not directory.is_dir() or directory.is_symlink():
                raise ValueError('invalid pending phase directory')
            files = record.get('files')
            if not isinstance(files, dict) or not files or files != descriptors(root, DIRS[phase]):
                raise ValueError('pending phase hash mismatch: ' + phase)
        if phase == 'verified' and record.get('manifest_sha256') != stage._digest(root / 'manifest.json'):
            raise ValueError('pending manifest hash mismatch')
        if phase == 'source' and record.get('source_manifest_sha256') != stage._digest(Path(config['terrain_path']) / 'manifest.json'):
            raise ValueError('pending source hash mismatch')
        completed.append(phase)
    return completed


def worker(root, phase):
    root = Path(root)
    config = json.loads((root / 'checkpoint.json').read_text(encoding='utf-8'))
    completed = validate(root, config)
    if phase != 'authenticate' and (len(completed) == len(PHASES) or phase != PHASES[len(completed)]):
        raise ValueError('unexpected phase')
    source, terrain = new_world_terrain.read_world_terrain(config['terrain_path'], config['expected_terrain_identity'])
    if phase == 'authenticate':
        return
    shape, origin = source['shape_zx'], source['origin_native_xz']
    record = {'phase': phase, 'config_hash': stage._identity(config)}
    if phase == 'source':
        record['source_manifest_sha256'] = stage._digest(Path(config['terrain_path']) / 'manifest.json')
    elif phase == 'graph':
        graph = stage.build_native_graph(tuple(shape), tuple(origin), root / 'graph', block_size=config['block_size'])
        del graph
    elif phase in ('flood', 'derived'):
        graph = {p.stem: np.load(p, mmap_mode='r', allow_pickle=False) for p in (root / 'graph').glob('*.npy')}
        if phase == 'flood':
            valid = terrain['valid_mask']
            outlets = np.logical_or(terrain['ocean_mask'], terrain['unknown_mask'])
            outlets[0, :] |= valid[0, :]
            outlets[-1, :] |= valid[-1, :]
            outlets[:, 0] |= valid[:, 0]
            outlets[:, -1] |= valid[:, -1]
            outlets &= valid
            route = stage.route_native_graph(terrain['bed_m'], outlets, graph, root / 'routing', valid_mask=valid)
            for name in ('discovered', 'heap_level', 'heap_node'):
                route.pop(name)._mmap.close()
                (root / 'routing' / (name + '.npy')).unlink()
            del route, outlets, valid
        else:
            route = {p.stem: np.load(p, mmap_mode='r', allow_pickle=False) for p in (root / 'routing').glob('*.npy')}
            derived = stage.derive_native_hydrology(graph, route, terrain['bed_m'], terrain['ocean_mask'],
                terrain['unknown_mask'], terrain['valid_mask'], tuple(origin), config['expected_terrain_identity'], root / 'derived')
            record['counts'] = {'pools': len(derived['pools']['id']), 'mouths': len(derived['mouths']['id'])}
            del derived, route
            gc.collect()
            for name in ('_stack.npy', '_terminal_ids.npy'):
                (root / 'derived' / name).unlink()
        del graph
    else:
        files = {}
        for previous in ('graph', 'flood', 'derived'):
            files.update(json.loads((root / (previous + '.json')).read_text(encoding='utf-8'))['files'])
        counts = json.loads((root / 'derived.json').read_text(encoding='utf-8'))['counts']
        manifest = {'schema': 'new-world-stage1-native-v2', 'terrain_path': config['terrain_path'],
            'expected_terrain_identity': config['expected_terrain_identity'], 'terrain_schema': source['schema'],
            'shape_zx': shape, 'origin_native_xz': origin, 'world_seed': stage.WORLD_SEED,
            'spacing_m': 30, 'sea_m': 0, 'block_size': config['block_size'],
            'algorithm': 'native-irregular-flood-derived-v1', 'counts': counts, 'files': files}
        manifest['identity'] = stage._identity(manifest)
        atomic_json(root / 'manifest.json', manifest)
        verified = stage.read_product(root, expected_terrain_identity=config['expected_terrain_identity'])
        del verified
        record['manifest_sha256'] = stage._digest(root / 'manifest.json')
    del terrain
    gc.collect()
    if phase in DIRS:
        for path in (root / DIRS[phase]).glob('*.npy'):
            # Windows requires a writable handle for the underlying commit.
            with path.open('r+b') as stream:
                os.fsync(stream.fileno())
        record['files'] = descriptors(root, DIRS[phase])
    atomic_json(root / (phase + '.json'), record)


def prepare(terrain_path, output, *, expected_terrain_identity, block_size=128, resume=False,
            budget_callback=None, stop_after=None, monitor_callback=None):
    output = Path(output).resolve()
    pending = output.with_name(output.name + '.pending')
    config = {'schema': 'stage1-checkpoint-v1', 'terrain_path': str(Path(terrain_path).resolve()),
              'expected_terrain_identity': expected_terrain_identity, 'block_size': block_size}
    if output.exists():
        raise FileExistsError(output)
    budget = stage.preflight(terrain_path, output, expected_terrain_identity, block_size=block_size)
    if not budget['sufficient']:
        raise ValueError('insufficient preflight RAM or disk')
    if resume:
        if not pending.is_dir() or pending.is_symlink():
            raise ValueError('missing or invalid pending directory')
        completed = validate(pending, config)
    else:
        pending.mkdir(exist_ok=False)
        atomic_json(pending / 'checkpoint.json', config)
        completed = []
    # Authentication also runs inside the monitored process tree on every resume.
    phases = (('authenticate',) if resume else ()) + PHASES[len(completed):]
    for phase in phases:
        if budget_callback is not None and not budget_callback(phase, budget):
            raise RuntimeError('phase budget denied: ' + phase)
        if phase in DIRS:
            partial = pending / DIRS[phase]
            if partial.is_symlink():
                raise ValueError('invalid pending phase path')
            if partial.exists():
                shutil.rmtree(partial)
        initial = snapshot(psutil.Process())
        if initial['available_ram_bytes'] < 1024**3 or initial['commit_headroom_bytes'] < 2*1024**3:
            raise RuntimeError('resource-abort: ' + phase)
        command = [sys.executable, '-m', 'terrain_pipeline.new_world_stage1_checkpoint', str(pending), phase]
        proc = subprocess.Popen(command)
        process = psutil.Process(proc.pid)
        stats = initial
        try:
            while proc.poll() is None:
                stats = snapshot(process)
                allowed = stats['available_ram_bytes'] >= 1024**3 and stats['commit_headroom_bytes'] >= 2*1024**3
                if monitor_callback is not None:
                    allowed = allowed and bool(monitor_callback(phase, stats))
                if not allowed:
                    terminate_tree(process)
                    proc.wait()
                    raise RuntimeError('resource-abort: ' + phase)
                time.sleep(.25)
            if proc.returncode:
                raise RuntimeError('phase failed: ' + phase)
        finally:
            if proc.poll() is None:
                terminate_tree(process)
                proc.wait()
        gc.collect()
        print(json.dumps({'phase_barrier': phase, 'worker_last_sample': stats, 'parent': snapshot(psutil.Process())}), flush=True)
        validate(pending, config)
        if stop_after == phase:
            return None
    verified_record = json.loads((pending / 'verified.json').read_text(encoding='utf-8'))
    if stage._digest(pending / 'manifest.json') != verified_record['manifest_sha256']:
        raise ValueError('pending manifest hash mismatch')
    if output.exists():
        raise FileExistsError(output)
    if sys.platform.startswith('linux'):
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renameat2(-100, os.fsencode(pending), -100, os.fsencode(output), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(output))
    else:
        os.rename(pending, output)
    return json.loads((output / 'manifest.json').read_text(encoding='utf-8')), {}


if __name__ == '__main__':
    worker(sys.argv[1], sys.argv[2])
