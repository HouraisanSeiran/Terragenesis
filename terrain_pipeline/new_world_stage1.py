"""Native graph, routing, and immutable finite-support hydrology products."""
from pathlib import Path
import numpy as np

from terrain_pipeline.drainage import _block_neighbors as _block_neighbors
from terrain_pipeline.drainage import _mix64 as _mix64

WORLD_SEED = 20261020


def resource_estimate(shape, block_size=128):
    """Conservative graph-build working budget, excluding OS page cache, bytes."""
    rows, cols = shape
    if min(rows, cols, block_size) < 1:
        raise ValueError("positive shape and block size required")
    n = rows * cols
    # CSR capacity assumes at most 16 directed edges/node; enforce at build time.
    return {"disk_bytes": n * (16 + 8 + 8 + 16 * 4) + 1048576,
            "ram_bytes": 256 * 1024**2 + (block_size + 16)**2 * 512,
            "source_worker_reserve_bytes": 4_900_000_000}


def build_native_graph(shape, origin_native_xz, directory, *, block_size=128):
    """Create disk-backed CSR matching irregular_drainage's native geometry.

    The work directory must not exist. Only one block and its halo are
    triangulated at once. The caller owns the returned read-only mappings.
    This is a graph primitive, not a complete or verified stage-1 product.
    """
    if (len(shape) != 2 or any(type(x) is not int or x < 2 for x in shape) or
        len(origin_native_xz) != 2 or any(type(x) is not int for x in origin_native_xz) or
        type(block_size) is not int or block_size < 1):
        raise ValueError("invalid shape, origin or block size")
    rows, cols = shape
    n = rows * cols
    if n >= 2**31:
        raise ValueError("graph exceeds int32 native node indices")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    def create(name, dtype, size):
        return np.lib.format.open_memmap(root / (name + '.npy'), mode='w+', dtype=dtype, shape=(size,))
    x = create('node_x_m', 'f8', n)
    z = create('node_z_m', 'f8', n)
    ptr = create('indptr', 'i8', n + 1)
    # Generate by row stripes, keeping coordinate/hash temporaries bounded.
    for start in range(0, n, 65536):
        end = min(n, start + 65536)
        cell = np.arange(start, end, dtype=np.int64)
        nx = cell % cols + origin_native_xz[0]
        nz = cell // cols + origin_native_xz[1]
        key = (_mix64(nx.view(np.uint64) ^ np.uint64(0x632BE59BD9B4E019)) ^
               _mix64(nz.view(np.uint64) ^ np.uint64(0x9E3779B97F4A7C15)) ^ np.uint64(WORLD_SEED))
        fx = (_mix64(key ^ np.uint64(0xD1B54A32D192ED03)) >> np.uint64(11)).astype(np.float64) * (2.0 ** -53)
        fz = (_mix64(key ^ np.uint64(0xABC98388FB8FAC03)) >> np.uint64(11)).astype(np.float64) * (2.0 ** -53)
        x[start:end] = (nx + 0.7 * (fx - 0.5)) * 30.
        z[start:end] = (nz + 0.7 * (fz - 0.5)) * 30.
    ptr[0] = 0
    for z0 in range(0, rows, block_size):
        for x0 in range(0, cols, block_size):
            core, degree, _ = _block_neighbors(x, z, shape, 30., z0, x0, block_size)
            ptr[core + 1] = degree
    total = 0
    for start in range(1, n + 1, 65536):
        end = min(n + 1, start + 65536)
        sums = np.cumsum(ptr[start:end]) + total
        ptr[start:end] = sums
        total = int(sums[-1])
    if total > 16 * n:
        raise ValueError('graph exceeds preflight edge budget')
    indices = create('indices', 'i4', total)
    for z0 in range(0, rows, block_size):
        for x0 in range(0, cols, block_size):
            core, degree, neighbors = _block_neighbors(x, z, shape, 30., z0, x0, block_size)
            starts = np.cumsum(degree) - degree
            destination = np.repeat(ptr[core], degree) + np.arange(neighbors.size) - np.repeat(starts, degree)
            indices[destination] = neighbors
    for a in (x, z, ptr, indices):
        a.flush()
        a._mmap.close()
    return {name: np.load(root / (name + '.npy'), mmap_mode='r', allow_pickle=False)
            for name in ('node_x_m', 'node_z_m', 'indptr', 'indices')}

# The flood heap and outputs are caller-provided mappings. Each node is inserted
# once, so the heap capacity is bounded by the node count.
from numba import njit


@njit(cache=True)
def _mapped_route(bed, outlets, valid, x, z, indptr, indices, filled, order, rank,
                  receiver, discovered, heap_level, heap_node):
    n = bed.size
    size = 0
    for node in range(n):
        filled[node] = bed[node]
        discovered[node] = outlets[node] or not valid[node]
        receiver[node] = -1
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


def route_native_graph(bed, outlets, graph, directory, *, valid_mask=None):
    """Flood a finite graph into independent mmap arrays; bed is never modified.

    The caller must account for source, graph, output, heap and page-cache
    residency before using this primitive on a large domain.
    """
    bed = np.asarray(bed)
    outlets = np.asarray(outlets)
    valid = np.ones(bed.shape, dtype=np.bool_) if valid_mask is None else np.asarray(valid_mask)
    if bed.ndim != 2 or outlets.shape != bed.shape or outlets.dtype != np.bool_:
        raise ValueError('bed and boolean outlets must share a two-dimensional shape')
    if valid.shape != bed.shape or valid.dtype != np.bool_:
        raise ValueError('valid_mask must be boolean and match bed')
    has_outlet = False
    for start in range(0, bed.size, 65536):
        b = bed.flat[start:start + 65536]
        o = outlets.flat[start:start + 65536]
        v = valid.flat[start:start + 65536]
        if np.any(o & ~v) or not np.isfinite(b[v]).all():
            raise ValueError('finite valid bed and at least one valid outlet required')
        has_outlet |= bool(o.any())
    if not has_outlet:
        raise ValueError('finite valid bed and at least one valid outlet required')
    n = bed.size
    if graph['indptr'].shape != (n + 1,) or graph['node_x_m'].shape != (n,) or graph['node_z_m'].shape != (n,):
        raise ValueError('graph shape mismatch')
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    arrays = {}
    for name, dtype in [('filled', 'f8'), ('order', 'i8'), ('rank', 'i8'),
                        ('receiver', 'i8'), ('discovered', '?'),
                        ('heap_level', 'f8'), ('heap_node', 'i8')]:
        arrays[name] = np.lib.format.open_memmap(root / (name + '.npy'), mode='w+', dtype=dtype, shape=(n,))
    _mapped_route(bed.ravel(), outlets.ravel(), valid.ravel(), graph['node_x_m'], graph['node_z_m'],
                  graph['indptr'], graph['indices'], arrays['filled'], arrays['order'],
                  arrays['rank'], arrays['receiver'], arrays['discovered'],
                  arrays['heap_level'], arrays['heap_node'])
    for array in arrays.values():
        array.flush()
    return arrays

# Terminal types: 0 excluded, 1 ocean, 2 nonmarine outlet, 3 unknown classification.
@njit(cache=True)
def _label_pools(bed, valid, ocean, unknown, filled, ptr, edges, labels, stack):
    n = bed.size
    labels[:] = -1
    pools = 0
    for start in range(n):
        if not valid[start] or ocean[start] or unknown[start] or labels[start] >= 0 or filled[start] <= bed[start]:
            continue
        labels[start] = pools
        stack[0] = start
        size = 1
        while size:
            size -= 1
            cell = stack[size]
            for edge in range(ptr[cell], ptr[cell + 1]):
                target = edges[edge]
                if (valid[target] and not ocean[target] and not unknown[target] and
                    labels[target] < 0 and filled[target] > bed[target] and filled[target] == filled[start]):
                    labels[target] = pools
                    stack[size] = target
                    size += 1
        pools += 1
    return pools


@njit(cache=True)
def _derive_arrays(bed, filled, valid, ocean, unknown, order, rank, receiver, ptr, edges,
                   rows, cols, labels, stack, anchors, capacity, counts, spill,
                   terminal, terminal_type, water_unknown, cell_area_m2):
    n = bed.size
    # Repeat the original depth-first order so floating-point sums remain exact.
    for start in range(n):
        label = labels[start]
        if label < 0:
            continue
        anchors[label] = start
        capacity[label] = 0.
        counts[label] = 0
        spill[label] = filled[start]
        labels[start] = -label - 2
        stack[0] = start
        size = 1
        while size:
            size -= 1
            cell = stack[size]
            counts[label] += 1
            capacity[label] += (filled[cell] - bed[cell]) * cell_area_m2
            if rank[cell] < rank[anchors[label]]:
                anchors[label] = cell
            for edge in range(ptr[cell], ptr[cell + 1]):
                target = edges[edge]
                if labels[target] == label:
                    labels[target] = -label - 2
                    stack[size] = target
                    size += 1
    for cell in range(n):
        if labels[cell] < -1:
            labels[cell] = -labels[cell] - 2
    terminal[:] = -1
    terminal_type[:] = 0
    water_unknown[:] = False
    # Flood order contains valid nodes followed by -1; receiver always precedes source.
    for k in range(n):
        cell = order[k]
        if cell < 0:
            continue
        target = receiver[cell]
        if ocean[cell]:
            terminal[cell] = cell
            terminal_type[cell] = 1
        elif unknown[cell]:
            terminal[cell] = cell
            terminal_type[cell] = 3
        elif target < 0:
            terminal[cell] = cell
            terminal_type[cell] = 2
        else:
            terminal[cell] = terminal[target]
            terminal_type[cell] = terminal_type[target]
        row, col = cell // cols, cell % cols
        if unknown[cell]:
            water_unknown[cell] = True
        # An unclassified or invalid neighbor is an unresolved ingress boundary,
        # including holes in the interior of the finite source support.
        if not ocean[cell]:
            for edge in range(ptr[cell], ptr[cell + 1]):
                neighbor = edges[edge]
                if not valid[neighbor] or unknown[neighbor]:
                    water_unknown[cell] = True
        if not ocean[cell] and (row == 0 or col == 0 or row == rows - 1 or col == cols - 1):
            water_unknown[cell] = True
            for edge in range(ptr[cell], ptr[cell + 1]):
                neighbor = edges[edge]
                if valid[neighbor] and not ocean[neighbor]:
                    water_unknown[neighbor] = True
    # Collapse pool ownership at its minimum-rank anchor before routing downstream.
    for k in range(n - 1, -1, -1):
        cell = order[k]
        if cell < 0 or not water_unknown[cell]:
            continue
        label = labels[cell]
        if label >= 0:
            water_unknown[anchors[label]] = True
        target = receiver[cell]
        if target >= 0:
            water_unknown[target] = True
    for cell in range(n):
        label = labels[cell]
        if label >= 0 and water_unknown[anchors[label]]:
            water_unknown[cell] = True


def derive_native_hydrology(graph, routing, bed, ocean_mask, classification_unknown_mask,
                            valid_mask, origin_native_xz, terrain_identity, output_path, *, cell_area_m2=900.0):
    """Derive mmap arrays from a frozen native flood; coordinates are native x,z cells.

    All masks are boolean, classification unknown is independent of water uncertainty.
    Output directory must be new. Returned tables are views of disk-backed arrays.
    IDs are BLAKE2b-64 over identity, feature kind and signed absolute cell coordinates;
    zero is reserved for absent IDs. Ocean catchments terminate at the first ocean cell.
    """
    import hashlib
    import json

    if not np.isfinite(cell_area_m2) or cell_area_m2 <= 0:
        raise ValueError('positive finite cell area required')
    bed = np.asarray(bed)
    masks = [np.asarray(a) for a in (ocean_mask, classification_unknown_mask, valid_mask)]
    if bed.ndim != 2 or any(a.shape != bed.shape or a.dtype != np.bool_ for a in masks):
        raise ValueError('bed and boolean masks must share a two-dimensional shape')
    ocean, unknown, valid = masks
    if (not isinstance(terrain_identity, str) or not terrain_identity or
        len(origin_native_xz) != 2 or any(type(v) is not int for v in origin_native_xz)):
        raise ValueError('terrain identity and integer native origin required')
    for start in range(0, bed.size, 65536):
        b = bed.flat[start:start + 65536]
        o = ocean.flat[start:start + 65536]
        u = unknown.flat[start:start + 65536]
        v = valid.flat[start:start + 65536]
        if np.any((o | u) & ~v) or np.any(o & u) or not np.isfinite(b[v]).all():
            raise ValueError('invalid classification or bed')
    rows, cols = bed.shape
    n = bed.size
    ptr, edges = graph['indptr'], graph['indices']
    if ptr.shape != (n + 1,) or any(routing[k].shape != (n,) for k in ('filled', 'order', 'rank', 'receiver')):
        raise ValueError('graph or routing shape mismatch')
    # Validate the frozen DAG in bounded chunks before creating output files.
    for start in range(0, n, 65536):
        stop = min(n, start + 65536)
        v = valid.ravel()[start:stop]
        rec = routing['receiver'][start:stop]
        if np.any(rec < -1) or np.any(rec >= n) or np.any((~v) & (rec != -1)):
            raise ValueError('invalid receiver')
        selected = rec >= 0
        if np.any(selected):
            targets = rec[selected]
            if np.any(~valid.ravel()[targets]) or np.any(routing['rank'][targets] >= routing['rank'][start:stop][selected]):
                raise ValueError('receiver must be valid and downstream in rank')
    root = Path(output_path)
    root.mkdir(parents=True, exist_ok=False)
    def create(name, dtype, size=n):
        return np.lib.format.open_memmap(root / (name + '.npy'), mode='w+', dtype=dtype, shape=(size,))
    arrays = {name: create(name, dtype) for name, dtype in (
        ('pool_index', 'i8'), ('terminal_index', 'i8'), ('terminal_type', 'u1'),
        ('watershed_id', 'u8'), ('total_water_unknown', '?'), ('classification_unknown', '?'))}
    for start in range(0, n, 65536):
        arrays['classification_unknown'][start:start + 65536] = unknown.ravel()[start:start + 65536]
    stack = create('_stack', 'i8')
    pool_count = _label_pools(bed.ravel(), valid.ravel(), ocean.ravel(), unknown.ravel(),
        routing['filled'], ptr, edges, arrays['pool_index'], stack)
    anchors = create('pool_anchor', 'i8', pool_count)
    capacity = create('pool_capacity_m3', 'f8', pool_count)
    counts = create('pool_cell_count', 'i8', pool_count)
    spill = create('pool_spill_m', 'f8', pool_count)
    _derive_arrays(bed.ravel(), routing['filled'], valid.ravel(), ocean.ravel(), unknown.ravel(), routing['order'], routing['rank'], routing['receiver'], ptr, edges,
        rows, cols, arrays['pool_index'], stack, anchors, capacity, counts, spill,
        arrays['terminal_index'], arrays['terminal_type'], arrays['total_water_unknown'], cell_area_m2)
    def stable_id(kind, cell):
        x = origin_native_xz[0] + int(cell) % cols
        z = origin_native_xz[1] + int(cell) // cols
        payload = json.dumps([terrain_identity, kind, x, z], ensure_ascii=True, separators=(',', ':')).encode()
        return int.from_bytes(hashlib.blake2b(payload, digest_size=8, person=b'terra-s1-v1').digest(), 'little') or 1
    pool_ids = create('pool_id', 'u8', pool_count)
    for i in range(pool_count):
        pool_ids[i] = stable_id('pool', anchors[i])
    # One hash per distinct terminal, with an mmap lookup rather than a Python dictionary.
    ids = create('_terminal_ids', 'u8')
    ids[:] = 0
    for k in range(n):
        cell = int(routing['order'][k])
        if cell >= 0 and arrays['terminal_index'][cell] == cell:
            ids[cell] = stable_id('watershed', cell)
    mouth_count = 0
    for start in range(0, n, 65536):
        stop = min(n, start + 65536)
        rec = routing['receiver'][start:stop]
        candidates = np.flatnonzero(valid.ravel()[start:stop] & ~ocean.ravel()[start:stop] & ~unknown.ravel()[start:stop] & (rec >= 0))
        mouth_count += int(np.count_nonzero(ocean.ravel()[rec[candidates]]))
    mouth_sources = create('mouth_source', 'i8', mouth_count)
    mouth_targets = create('mouth_ocean_receiver', 'i8', mouth_count)
    mouth_ids = create('mouth_id', 'u8', mouth_count)
    mouth_count = 0
    for start in range(0, n, 65536):
        stop = min(n, start + 65536)
        terminals = arrays['terminal_index'][start:stop]
        section = arrays['watershed_id'][start:stop]
        section[:] = 0
        good = terminals >= 0
        section[good] = ids[terminals[good]]
        rec = routing['receiver'][start:stop]
        candidates = np.flatnonzero(valid.ravel()[start:stop] & ~ocean.ravel()[start:stop] & ~unknown.ravel()[start:stop] & (rec >= 0))
        candidates = candidates[ocean.ravel()[rec[candidates]]]
        for local in candidates:
            source = start + int(local)
            mouth_sources[mouth_count] = source
            mouth_targets[mouth_count] = rec[local]
            mouth_ids[mouth_count] = stable_id('mouth', source)
            mouth_count += 1
    for a in (*arrays.values(), anchors, capacity, counts, spill, pool_ids, mouth_sources, mouth_targets, mouth_ids):
        a.flush()
    def coordinates(name, nodes):
        result = np.lib.format.open_memmap(root / (name + '.npy'), mode='w+', dtype='i8', shape=(mouth_count, 2))
        for start in range(0, mouth_count, 65536):
            part = nodes[start:start + 65536]
            result[start:start + len(part), 0] = part % cols + origin_native_xz[0]
            result[start:start + len(part), 1] = part // cols + origin_native_xz[1]
        result.flush()
        return result
    return {'arrays': arrays, 'pools': {'id': pool_ids, 'anchor': anchors[:pool_count],
        'spill_m': spill[:pool_count], 'capacity_m3': capacity[:pool_count], 'cell_count': counts[:pool_count]},
        'mouths': {'id': mouth_ids[:mouth_count], 'source': mouth_sources[:mouth_count],
        'ocean_receiver': mouth_targets[:mouth_count], 'source_native_xz': coordinates('mouth_source_native_xz', mouth_sources[:mouth_count]),
        'ocean_native_xz': coordinates('mouth_ocean_native_xz', mouth_targets[:mouth_count])},
        'metadata': {'terrain_identity': terrain_identity, 'origin_native_xz': tuple(origin_native_xz),
        'shape': bed.shape, 'cell_area_m2': cell_area_m2, 'scope': 'local-complete-under-frozen-directed-model',
        'workspace_bytes_per_node_upper_bound': 160, 'terminal_types': {0: 'excluded', 1: 'ocean', 2: 'nonmarine outlet', 3: 'classification unknown'}}}

# Product wrapper. All large files remain memory mapped; source verification is
# delegated to the authoritative terrain reader and has its own working set.
def product_resource_estimate(shape, block_size=128):
    base = resource_estimate(shape, block_size)
    n = int(shape[0]) * int(shape[1])
    return {'graph_disk_bytes': base['disk_bytes'], 'routing_heap_disk_bytes': 49*n,
            'derived_disk_bytes': 160*n + 4*1024**2,
            'source_reader_ram_bytes': 100*n,
            'live_array_page_cache_bytes': 320*n,
            'graph_build_ram_bytes': base['ram_bytes'],
            'source_worker_reserve_bytes': base['source_worker_reserve_bytes'],
            'disk_bytes': base['disk_bytes'] + 209*n + 16*1024**2,
            # Source generation must have exited before this CPU job starts.
            'ram_bytes': base['ram_bytes'] + 420*n}


def _digest(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _identity(record):
    import hashlib, json
    return hashlib.sha256(json.dumps({k: v for k, v in record.items()
        if k not in ('identity', 'terrain_path')}, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _source_header(path, expected):
    import json
    m = json.loads((Path(path) / 'manifest.json').read_text(encoding='utf-8'))
    shape, origin = m.get('shape_zx'), m.get('origin_native_xz')
    if (not isinstance(expected, str) or len(expected) != 64 or
        any(c not in '0123456789abcdef' for c in expected) or m.get('identity') != expected or
        m.get('schema') not in ('new-world-terrain-v2', 'new-world-terrain-v3') or
        m.get('world_seed') != WORLD_SEED or type(m.get('world_seed')) is not int or
        m.get('spacing_m') != 30 or m.get('sea_m') != 0 or
        not isinstance(shape, list) or len(shape) != 2 or
        any(type(v) is not int or v < 2 for v in shape) or
        not isinstance(origin, list) or len(origin) != 2 or any(type(v) is not int for v in origin)):
        raise ValueError('invalid terrain header or expected identity')
    return m


def preflight(terrain_path, output, expected_terrain_identity, *, block_size=128):
    import shutil
    m = _source_header(terrain_path, expected_terrain_identity)
    estimate = product_resource_estimate(m['shape_zx'], block_size)
    try:
        import psutil
        available = psutil.virtual_memory().available
    except ImportError:
        available = None
    disk = shutil.disk_usage(Path(output).resolve().parent).free
    return {**estimate, 'available_ram_bytes': available, 'available_disk_bytes': disk,
            'sufficient': available is not None and available >= estimate['ram_bytes'] and disk >= estimate['disk_bytes'],
            'terrain_schema': m['schema'], 'shape_zx': m['shape_zx']}


def prepare(terrain_path, output, *, expected_terrain_identity, block_size=128):
    import gc, json, os, shutil, tempfile
    from terrain_pipeline import td_source as new_world_terrain
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    budget = preflight(terrain_path, output, expected_terrain_identity, block_size=block_size)
    if not budget['sufficient']:
        raise ValueError('insufficient preflight RAM or disk')
    source, terrain = new_world_terrain.read_world_terrain(terrain_path, expected_terrain_identity)
    shape, origin = source['shape_zx'], source['origin_native_xz']
    # Climate and other authenticated mappings are not needed by planning.
    terrain = {key: terrain[key] for key in ('bed_m', 'valid_mask', 'ocean_mask', 'unknown_mask')}
    gc.collect()
    if terrain['bed_m'].dtype != np.float32 or terrain['bed_m'].shape != tuple(shape):
        raise ValueError('source bed must be native float32')
    tmp = Path(tempfile.mkdtemp(prefix='.stage1-', dir=output.parent))
    try:
        graph = build_native_graph(tuple(shape), tuple(origin), tmp / 'graph', block_size=block_size)
        valid = terrain['valid_mask']
        # Ocean, classification unknown and valid finite support rim are outlets.
        outlets = np.logical_or(terrain['ocean_mask'], terrain['unknown_mask'])
        outlets[0, :] |= valid[0, :]
        outlets[-1, :] |= valid[-1, :]
        outlets[:, 0] |= valid[:, 0]
        outlets[:, -1] |= valid[:, -1]
        outlets &= valid
        route = route_native_graph(terrain['bed_m'], outlets, graph, tmp / 'routing', valid_mask=valid)
        # These mappings are no longer read after flood routing. Release them
        # before allocating the derived workspace, including on Windows.
        for name in ('discovered', 'heap_level', 'heap_node'):
            route.pop(name)._mmap.close()
            (tmp / 'routing' / (name + '.npy')).unlink()
        del outlets
        gc.collect()
        derived = derive_native_hydrology(graph, route, terrain['bed_m'], terrain['ocean_mask'],
            terrain['unknown_mask'], valid, tuple(origin), expected_terrain_identity, tmp / 'derived')
        counts = {'pools': len(derived['pools']['id']), 'mouths': len(derived['mouths']['id'])}
        # Flush and release mappings before publishing (also required on Windows).
        del derived, route, graph, valid, terrain
        gc.collect()
        for name in ('derived/_stack.npy', 'derived/_terminal_ids.npy'):
            (tmp / name).unlink()
        files = {}
        for file in sorted(tmp.glob('*/*.npy')):
            a = np.load(file, mmap_mode='r', allow_pickle=False)
            key = file.relative_to(tmp).as_posix()
            files[key] = {'sha256': _digest(file), 'dtype': a.dtype.str, 'shape': list(a.shape)}
            del a
        manifest = {'schema': 'new-world-stage1-native-v2', 'terrain_path': str(Path(terrain_path).resolve()),
            'expected_terrain_identity': expected_terrain_identity, 'terrain_schema': source['schema'],
            'shape_zx': shape, 'origin_native_xz': origin, 'world_seed': WORLD_SEED,
            'spacing_m': 30, 'sea_m': 0, 'block_size': block_size,
            'algorithm': 'native-irregular-flood-derived-v1', 'counts': counts, 'files': files}
        manifest['identity'] = _identity(manifest)
        (tmp / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        verified = read_product(tmp, expected_terrain_identity=expected_terrain_identity)
        del verified
        gc.collect()
        if output.exists():
            raise FileExistsError(output)
        os.rename(tmp, output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_product(output, expected_terrain_identity=expected_terrain_identity)


def read_product(path, *, expected_terrain_identity):
    import json
    from terrain_pipeline import td_source as new_world_terrain
    root = Path(path)
    m = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if (m.get('schema') not in ('new-world-stage1-native-v1', 'new-world-stage1-native-v2') or m.get('identity') != _identity(m) or
        m.get('expected_terrain_identity') != expected_terrain_identity or
        m.get('world_seed') != WORLD_SEED or type(m.get('world_seed')) is not int or
        m.get('spacing_m') != 30 or m.get('sea_m') != 0 or
        m.get('algorithm') != 'native-irregular-flood-derived-v1' or
        not Path(m.get('terrain_path', '')).is_absolute()):
        raise ValueError('stage1 contract or identity mismatch')
    header = _source_header(m['terrain_path'], expected_terrain_identity)
    source, terrain = new_world_terrain.read_world_terrain(m['terrain_path'], expected_terrain_identity)
    if any(m[k] != source[k] for k in ('shape_zx', 'origin_native_xz', 'world_seed', 'spacing_m', 'sea_m')) or m['terrain_schema'] != header['schema']:
        raise ValueError('terrain metadata mismatch')
    n = int(np.prod(m['shape_zx']))
    pools, mouths = m['counts']['pools'], m['counts']['mouths']
    if type(pools) is not int or type(mouths) is not int or not 0 <= pools <= n or not 0 <= mouths <= n:
        raise ValueError('invalid counts')
    specs = {
        'graph/node_x_m': ('f8', (n,)), 'graph/node_z_m': ('f8', (n,)),
        'graph/indptr': ('i8', (n+1,)), 'graph/indices': ('i4', None),
        **{'routing/'+k: (d, (n,)) for k,d in [('filled','f8'),('order','i8'),('rank','i8'),('receiver','i8')]},
        **{'derived/'+k: (d, (n,)) for k,d in [('pool_index','i8'),('terminal_index','i8'),('terminal_type','u1'),('watershed_id','u8'),('total_water_unknown','?'),('classification_unknown','?')]},
        **{'derived/'+k: (d, (n if m['schema'].endswith('-v1') else pools,)) for k, d in [('pool_anchor','i8'),('pool_capacity_m3','f8'),('pool_cell_count','i8'),('pool_spill_m','f8')]},
        **{'derived/'+k: (d, (n if m['schema'].endswith('-v1') else mouths,)) for k, d in [('mouth_source','i8'),('mouth_ocean_receiver','i8'),('mouth_id','u8')]},
        'derived/pool_id': ('u8',(pools,)),
        'derived/mouth_source_native_xz': ('i8',(mouths,2)), 'derived/mouth_ocean_native_xz': ('i8',(mouths,2))}
    if set(m['files']) != {k+'.npy' for k in specs}:
        raise ValueError('unexpected array files')
    arrays = {}
    for key, (dtype, shape) in specs.items():
        name = key+'.npy'
        file = root / name
        desc = m['files'][name]
        if _digest(file) != desc['sha256']:
            raise ValueError('output hash mismatch: '+name)
        a = np.load(file, mmap_mode='r', allow_pickle=False)
        if a.dtype != np.dtype(dtype) or (shape is not None and a.shape != shape) or (shape is None and (a.ndim != 1 or a.size > 16*n)) or desc['shape'] != list(a.shape) or desc['dtype'] != a.dtype.str:
            raise ValueError('output array contract: '+name)
        arrays[key] = a
    ptr, edges = arrays['graph/indptr'], arrays['graph/indices']
    if ptr[0] != 0 or ptr[-1] != edges.size:
        raise ValueError('invalid graph offsets')
    valid = terrain['valid_mask'].ravel()
    rank, order, rec = (arrays['routing/'+k] for k in ('rank','order','receiver'))
    valid_count = int(np.count_nonzero(valid))
    for start in range(0, n, 65536):
        end = min(n, start+65536)
        p = ptr[start:end+1]
        r = rec[start:end]
        v = valid[start:end]
        idx = np.arange(start, end)
        if np.any(p[1:] < p[:-1]) or np.any(p < 0) or np.any(p > edges.size) or np.any(r < -1) or np.any(r >= n) or np.any(r[~v] != -1):
            raise ValueError('invalid graph or receiver')
        good = r >= 0
        if np.any(~valid[r[good]]) or np.any(rank[r[good]] >= rank[start:end][good]):
            raise ValueError('invalid receiver rank')
        ranks = rank[start:end]
        if np.any(ranks[~v] != -1) or np.any(ranks[v] < 0) or np.any(ranks[v] >= valid_count) or np.any(order[ranks[v]] != idx[v]):
            raise ValueError('invalid rank/order')
        if np.any(order[max(start, valid_count):end] != -1):
            raise ValueError('invalid order tail')
        if not np.array_equal(arrays['derived/classification_unknown'][start:end], terrain['unknown_mask'].ravel()[start:end]):
            raise ValueError('classification mismatch')
        label = arrays['derived/pool_index'][start:end]
        if np.any(label < -1) or np.any(label >= pools):
            raise ValueError('invalid pool index')
    for start in range(0, edges.size, 65536):
        e = edges[start:start+65536]
        if np.any(e < 0) or np.any(e >= n):
            raise ValueError('invalid graph index')
    for start in range(0, pools, 65536):
        end = min(pools, start + 65536)
        anchors = arrays['derived/pool_anchor'][start:end]
        capacities = arrays['derived/pool_capacity_m3'][start:end]
        spills = arrays['derived/pool_spill_m'][start:end]
        if (np.any(anchors < 0) or np.any(anchors >= n) or
            np.any(arrays['derived/pool_index'][anchors] != np.arange(start, end)) or
            np.any(~np.isfinite(capacities)) or np.any(capacities < 0) or
            np.any(~np.isfinite(spills)) or np.any(arrays['derived/pool_id'][start:end] == 0)):
            raise ValueError('invalid pool records')
    for start in range(0, mouths, 65536):
        end = min(mouths, start + 65536)
        sources = arrays['derived/mouth_source'][start:end]
        targets = arrays['derived/mouth_ocean_receiver'][start:end]
        if (np.any(sources < 0) or np.any(sources >= n) or np.any(targets < 0) or np.any(targets >= n) or
            np.any(rec[sources] != targets) or np.any(~terrain['ocean_mask'].ravel()[targets]) or
            np.any(arrays['derived/mouth_id'][start:end] == 0)):
            raise ValueError('invalid mouth records')
    arrays.update(terrain)
    return m, arrays


def query_window(product, origin_native_xz, shape):
    m, a = product
    if len(origin_native_xz) != 2 or len(shape) != 2 or any(type(v) is not int for v in (*origin_native_xz, *shape)) or min(shape) < 1:
        raise ValueError('invalid window')
    x, z = origin_native_xz[0]-m['origin_native_xz'][0], origin_native_xz[1]-m['origin_native_xz'][1]
    rows, cols = m['shape_zx']
    if x < 0 or z < 0 or x+shape[1] > cols or z+shape[0] > rows:
        raise ValueError('window outside product')
    result = {}
    for key, arr in a.items():
        if key.startswith('routing/') and arr.shape == (rows*cols,) or key.startswith('derived/') and key.split('/')[-1] in ('pool_index','terminal_index','terminal_type','watershed_id','total_water_unknown','classification_unknown'):
            view = arr.reshape(rows, cols)[z:z+shape[0], x:x+shape[1]]
        elif '/' not in key and arr.shape[-2:] == (rows, cols):
            view = arr[..., z:z+shape[0], x:x+shape[1]]
        else:
            continue
        view.setflags(write=False)
        result[key] = view
    return {'identity': m['identity'], 'origin_native_xz': list(origin_native_xz), 'shape_zx': list(shape), 'spacing_m': 30}, result


def lifecycle_adapter(product, *, max_nodes=1000000):
    """Materialize the legacy PartitionRouter contract, guarded by a node limit."""
    m, a = product
    rows, cols = m['shape_zx']
    n = rows*cols
    if n > max_nodes:
        raise ValueError('legacy lifecycle adapter node limit exceeded; PartitionRouter uses O(nodes + pools) RAM and Python dictionaries')
    count = m['counts']['pools']
    labels = a['derived/pool_index']
    ids = a['derived/pool_id']
    basin = np.zeros(n, dtype=np.uint64)
    good = labels >= 0
    basin[good] = ids[labels[good]]
    pools = [{'id': str(int(ids[i])), 'anchor_index': int(a['derived/pool_anchor'][i]),
              'capacity_m3': float(a['derived/pool_capacity_m3'][i]),
              'spill_stage_m': float(a['derived/pool_spill_m'][i])} for i in range(count)]
    manifest = {'identity': m['identity'], 'pools': pools}
    arrays = {'bed_m': a['bed_m'], 'valid_mask': a['valid_mask'], 'basin_id': basin.reshape(rows,cols),
              'receiver': a['routing/receiver'].reshape(rows,cols), 'rank': a['routing/rank'].reshape(rows,cols),
              'terminal_kind': a['derived/terminal_type'].reshape(rows,cols),
              'watershed_id': a['derived/watershed_id'].reshape(rows,cols),
              'total_water_unknown': a['derived/total_water_unknown'].reshape(rows,cols)}
    return manifest, arrays
