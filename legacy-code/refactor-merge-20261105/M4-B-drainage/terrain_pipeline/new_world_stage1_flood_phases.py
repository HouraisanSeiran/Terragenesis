"""Independent memory-mapped phases of the native priority flood."""
import numpy as np
from numba import njit


@njit(cache=True)
def _flood_order(bed, outlets, valid, indptr, indices, filled, order, rank, discovered, heap_level, heap_node):
    n = bed.size
    size = 0
    for node in range(n):
        filled[node] = bed[node]
        discovered[node] = outlets[node] or not valid[node]
        rank[node] = -1
        order[node] = -1
        if outlets[node]:
            pos = size
            size += 1
            while pos:
                parent = (pos - 1) // 2
                if (heap_level[parent] < bed[node] or
                    (heap_level[parent] == bed[node] and heap_node[parent] <= node)):
                    break
                heap_level[pos] = heap_level[parent]
                heap_node[pos] = heap_node[parent]
                pos = parent
            heap_level[pos] = bed[node]
            heap_node[pos] = node
    visited = 0
    while size:
        level = heap_level[0]
        current = heap_node[0]
        size -= 1
        if size:
            last_level = heap_level[size]
            last_node = heap_node[size]
            pos = 0
            while 2 * pos + 1 < size:
                child = 2 * pos + 1
                if child + 1 < size and (heap_level[child + 1] < heap_level[child] or
                    (heap_level[child + 1] == heap_level[child] and heap_node[child + 1] < heap_node[child])):
                    child += 1
                if (last_level < heap_level[child] or
                    (last_level == heap_level[child] and last_node <= heap_node[child])):
                    break
                heap_level[pos] = heap_level[child]
                heap_node[pos] = heap_node[child]
                pos = child
            heap_level[pos] = last_level
            heap_node[pos] = last_node
        rank[current] = visited
        order[visited] = current
        visited += 1
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            if discovered[neighbor]:
                continue
            discovered[neighbor] = True
            new_level = max(bed[neighbor], level)
            filled[neighbor] = new_level
            pos = size
            size += 1
            while pos:
                parent = (pos - 1) // 2
                if (heap_level[parent] < new_level or
                    (heap_level[parent] == new_level and heap_node[parent] <= neighbor)):
                    break
                heap_level[pos] = heap_level[parent]
                heap_node[pos] = heap_node[parent]
                pos = parent
            heap_level[pos] = new_level
            heap_node[pos] = neighbor
    if visited != np.count_nonzero(valid):
        raise ValueError('Graph has a component without an explicit outlet')


@njit(cache=True)
def _select_receivers(outlets, valid, x, z, indptr, indices, filled, order, rank, receiver):
    n = valid.size
    receiver[:] = -1
    for k in range(n):
        current = order[k]
        if current < 0:
            continue
        if outlets[current]:
            continue
        best_slope = -1.0
        best_rank = n
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            if not valid[neighbor] or rank[neighbor] >= rank[current] or filled[neighbor] > filled[current]:
                continue
            distance = np.hypot(x[current] - x[neighbor], z[current] - z[neighbor])
            slope = (filled[current] - filled[neighbor]) / distance
            if slope > best_slope or (slope == best_slope and rank[neighbor] < best_rank):
                receiver[current] = neighbor
                best_slope = slope
                best_rank = rank[neighbor]
        if receiver[current] < 0:
            raise ValueError('Non-outlet node has no downstream neighbor')



# Each phase opens only the mappings it uses. The checkpoint authenticates the
# immutable inputs and the durable intermediate arrays before heap deletion.
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf8') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def authenticate(terrain, graph, expected):
    terrain, graph = Path(terrain), Path(graph)
    source = json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    gm = json.loads((graph / 'manifest.json').read_text(encoding='utf8'))
    if source['identity'] != expected or gm['source_identity'] != expected or gm['source_manifest_sha256'] != digest(terrain / 'manifest.json'):
        raise ValueError('source identity mismatch')
    if source['shape_zx'] != gm['shape_zx'] or source['origin_native_xz'] != gm['origin_native_xz']:
        raise ValueError('graph source mismatch')
    for name in ('bed_m', 'valid_mask', 'ocean_mask', 'unknown_mask'):
        if digest(terrain / (name + '.npy')) != source['files'][name]:
            raise ValueError('source hash mismatch: ' + name)
    for name, expected_hash in gm['files_sha256'].items():
        if digest(graph / name) != expected_hash:
            raise ValueError('graph hash mismatch: ' + name)
    return source, gm


def mapped(root, name, mode='r'):
    return np.load(Path(root) / (name + '.npy'), mmap_mode=mode, allow_pickle=False)


def create(root, name, dtype, n):
    return np.lib.format.open_memmap(Path(root) / (name + '.npy'), mode='w+', dtype=dtype, shape=(n,))


def close(*arrays):
    for a in arrays:
        if a.flags.writeable:
            a.flush()
        a._mmap.close()


def phase_a(terrain, graph, root, expected):
    source, gm = authenticate(terrain, graph, expected)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    shape = source['shape_zx']
    n = int(np.prod(shape))
    bed, valid, ocean, unknown = (mapped(terrain, name) for name in ('bed_m', 'valid_mask', 'ocean_mask', 'unknown_mask'))
    outlets = create(root, 'outlets', '?', n)
    for start in range(0, n, 65536):
        end = min(start + 65536, n)
        outlets[start:end] = (ocean.flat[start:end] | unknown.flat[start:end]) & valid.flat[start:end]
    o = outlets.reshape(shape)
    o[0, :] |= valid[0, :]; o[-1, :] |= valid[-1, :]
    o[:, 0] |= valid[:, 0]; o[:, -1] |= valid[:, -1]
    close(ocean, unknown)
    ptr, edges = (mapped(graph, name) for name in ('indptr', 'indices'))
    filled, order, rank, discovered, heap_level, heap_node = (create(root, name, dtype, n) for name, dtype in
        [('filled','f8'), ('order','i8'), ('rank','i8'), ('discovered','?'), ('heap_level','f8'), ('heap_node','i8')])
    _flood_order(bed.reshape(-1), outlets, valid.reshape(-1), ptr, edges, filled, order, rank, discovered, heap_level, heap_node)
    close(bed, valid, ptr, edges, outlets, filled, order, rank, discovered, heap_level, heap_node)
    names = ('outlets', 'filled', 'order', 'rank', 'discovered', 'heap_level', 'heap_node')
    record = {'phase': 'A', 'source_manifest': digest(Path(terrain) / 'manifest.json'), 'graph_manifest': digest(Path(graph) / 'manifest.json'), 'files': {name: digest(root / (name + '.npy')) for name in names}}
    atomic_json(root / 'phase_a.json', record)
    validate_a(terrain, graph, root, expected)
    for name in ('discovered', 'heap_level', 'heap_node'):
        if digest(root / (name + '.npy')) != record['files'][name]:
            raise ValueError('checkpoint hash mismatch: ' + name)
    for name in ('discovered', 'heap_level', 'heap_node'):
        (root / (name + '.npy')).unlink()


def validate_a(terrain, graph, root, expected):
    authenticate(terrain, graph, expected)
    root = Path(root)
    record = json.loads((root / 'phase_a.json').read_text(encoding='utf8'))
    if record['source_manifest'] != digest(Path(terrain) / 'manifest.json') or record['graph_manifest'] != digest(Path(graph) / 'manifest.json'):
        raise ValueError('checkpoint provenance mismatch')
    for name in ('outlets', 'filled', 'order', 'rank'):
        if digest(root / (name + '.npy')) != record['files'][name]:
            raise ValueError('checkpoint hash mismatch: ' + name)


def phase_b(terrain, graph, root, expected):
    validate_a(terrain, graph, root, expected)
    root = Path(root)
    valid = mapped(terrain, 'valid_mask')
    outlets, filled, order, rank = (mapped(root, name) for name in ('outlets', 'filled', 'order', 'rank'))
    x, z, ptr, edges = (mapped(graph, name) for name in ('node_x_m', 'node_z_m', 'indptr', 'indices'))
    receiver = create(root, 'receiver', 'i8', valid.size)
    _select_receivers(outlets, valid.reshape(-1), x, z, ptr, edges, filled, order, rank, receiver)
    close(valid, outlets, filled, order, rank, x, z, ptr, edges, receiver)
    atomic_json(root / 'phase_b.json', {'phase': 'B', 'files': {name: digest(root / (name + '.npy')) for name in ('filled', 'order', 'rank', 'receiver')}, 'implementation_sha256': digest(__file__), 'reference_sha256': digest(Path(__file__).with_name('new_world_stage1.py'))})
