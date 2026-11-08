"""Audit frozen 30 m identity and replay actual event with owner transfers."""
import hashlib
import json
from pathlib import Path
import numpy as np
from numba import njit
from terrain_pipeline.new_world_native_event import read_product

ROOT = Path('.scratch/river-upgrade-20261101')
IDENTITY = 'c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'


def stable_id(kind, cell, cols, origin, identity=IDENTITY):
    payload = json.dumps([identity, kind, origin[0] + int(cell) % cols, origin[1] + int(cell) // cols], separators=(',', ':')).encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8, person=b'terra-s1-v1').digest(), 'little') or 1


@njit
def replay(order, receiver, labels, anchors, capacity, flow, incoming, storage, begin, end, partitions, rows, cols, counts, volumes):
    for pos in range(begin, end):
        cell = order[order.size - 1 - pos]
        if cell < 0:
            continue
        label = labels[cell]
        owner = 0
        if partitions >= 2 and cell % cols >= cols // 2:
            owner += 1
        if partitions == 4 and cell // cols >= rows // 2:
            owner += 2
        if label >= 0:
            anchor = anchors[label]
            target_owner = 0
            if partitions >= 2 and anchor % cols >= cols // 2:
                target_owner += 1
            if partitions == 4 and anchor // cols >= rows // 2:
                target_owner += 2
            if owner != target_owner:
                counts[0] += 1
                volumes[0] += flow[cell]
            incoming[label] += flow[cell]
            if cell != anchor:
                continue
            available = storage[label] + incoming[label]
            updated = min(capacity[label], available)
            storage[label] = updated
            flow[cell] = available - updated
        target = receiver[cell]
        if target >= 0:
            target_owner = 0
            if partitions >= 2 and target % cols >= cols // 2:
                target_owner += 1
            if partitions == 4 and target // cols >= rows // 2:
                target_owner += 2
            if owner != target_owner:
                counts[1] += 1
                volumes[1] += flow[cell]
            flow[target] += flow[cell]


def main():
    base = ROOT / 'native-final-routing-v1'
    terrain = ROOT / 'terrain-v3'
    event = ROOT / 'native-event-v1'
    manifest = json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    assert manifest['identity'] == IDENTITY
    rows, cols = manifest['shape_zx']
    origin = manifest['origin_native_xz']
    load = lambda path: np.load(path, mmap_mode='r', allow_pickle=False)
    d = lambda name: load(base / 'derived' / (name + '.npy'))
    valid, ocean, unknown = (load(terrain / (name + '.npy')).ravel() for name in ('valid_mask', 'ocean_mask', 'unknown_mask'))
    receiver, rank, order = (load(base / 'routing' / (name + '.npy')) for name in ('receiver', 'rank', 'order'))
    terminal, kind, watershed, uncertain, labels = (d(name) for name in ('terminal_index', 'terminal_type', 'watershed_id', 'total_water_unknown', 'pool_index'))
    anchors, pool_ids, capacity, mouths, mouth_ids = (d(name) for name in ('pool_anchor', 'pool_id', 'pool_capacity_m3', 'mouth_source', 'mouth_id'))
    assert len(np.unique(pool_ids)) == len(pool_ids) and len(np.unique(mouth_ids)) == len(mouth_ids)
    assert all(int(v) == stable_id('pool', c, cols, origin) for v, c in zip(pool_ids, anchors))
    assert all(int(v) == stable_id('mouth', c, cols, origin) for v, c in zip(mouth_ids, mouths))
    terminals = set()
    types = np.zeros(4, dtype=np.int64)
    owners = {p: np.zeros(p, dtype=np.int64) for p in (1, 2, 4)}
    for start in range(0, len(valid), 262144):
        stop = min(start + 262144, len(valid))
        cells = np.arange(start, stop)
        v, sea, u = valid[start:stop], ocean[start:stop], unknown[start:stop]
        rec, k, t = receiver[start:stop], kind[start:stop], terminal[start:stop]
        assert np.all((rec >= -1) & (rec < len(valid)))
        edge = rec >= 0
        assert np.all(valid[rec[edge]]) and np.all(rank[rec[edge]] < rank[start:stop][edge])
        assert np.all(k <= 3) and np.all((k == 0) == ~v)
        land = v & ~sea & ~u
        assert np.all(t[land] >= 0) and np.all(watershed[start:stop][land] != 0)
        assert np.all(kind[t[land]] == k[land]) and np.all(terminal[t[land]] == t[land])
        assert np.all(watershed[start:stop][land] == watershed[t[land]])
        assert np.all(~uncertain[start:stop][edge] | uncertain[rec[edge]])
        types += np.bincount(k[land], minlength=4)
        terminals.update(np.unique(t[land]).tolist())
        ids = cells[land]
        for p in owners:
            owner = np.zeros(ids.size, dtype=np.uint8)
            if p >= 2: owner += (ids % cols >= cols // 2)
            if p == 4: owner += (2 * (ids // cols >= rows // 2)).astype(np.uint8)
            owners[p] += np.bincount(owner, minlength=p)
    expected = [stable_id('watershed', t, cols, origin) for t in terminals]
    assert len(set(expected)) == len(expected)
    assert all(int(watershed[t]) == i for t, i in zip(terminals, expected))
    assert np.array_equal(receiver[mouths], d('mouth_ocean_receiver')) and np.all(ocean[receiver[mouths]])
    assert np.all(labels[anchors] == np.arange(len(anchors)))
    product = read_product(event)
    probes = [(1024, 1024), (2048, 2048), (3072, 3072), (2000, 2100)]
    forward = {p: product.query(*p, 1) for p in probes}
    restored = read_product(event)
    assert all(forward[p] == restored.query(*p, 1) for p in reversed(probes))
    local = load(event / 'local_contribution_m3.npy')
    reference = load(event / 'node_water_m3.npy')
    stores = load(event / 'pool_storage_m3.npy')
    output = ROOT / 'native-ownership-v1'
    output.mkdir(exist_ok=True)
    runs = []
    for partitions in (1, 2, 4):
        for interval in (0, 1):
            flow = np.array(local)
            incoming = np.zeros(len(anchors))
            storage = np.array(stores[interval])
            counts = np.zeros(2, np.int64)
            volumes = np.zeros(2)
            split = len(order) // 2
            replay(order, receiver, labels, anchors, capacity, flow, incoming, storage, 0, split, partitions, rows, cols, counts, volumes)
            checkpoint = output / 'checkpoint.npz'
            np.savez(checkpoint, flow=flow, incoming=incoming, storage=storage, counts=counts, volumes=volumes)
            del flow, incoming, storage, counts, volumes
            with np.load(checkpoint) as saved:
                flow, incoming, storage, counts, volumes = (saved[x] for x in ('flow', 'incoming', 'storage', 'counts', 'volumes'))
            checkpoint.unlink()
            replay(order, receiver, labels, anchors, capacity, flow, incoming, storage, split, len(order), partitions, rows, cols, counts, volumes)
            max_flow = max(float(np.max(np.abs(flow[a:a+262144] - reference[interval,a:a+262144]))) for a in range(0, len(flow), 262144))
            max_storage = float(np.max(np.abs(storage - stores[interval+1])))
            assert max_flow == 0 and max_storage == 0
            runs.append(dict(partitions=partitions, interval=interval, pool_crossings=int(counts[0]), receiver_crossings=int(counts[1]), pool_transfer_m3=float(volumes[0]), receiver_transfer_m3=float(volumes[1]), max_node_error_m3=max_flow, max_pool_error_m3=max_storage))
            del flow, incoming, storage
    result = dict(source_identity=IDENTITY, land_terminal_types=types.tolist(), distinct_land_terminals=len(terminals), pool_count=len(anchors), mouth_count=len(mouths), owners={str(k): v.tolist() for k,v in owners.items()}, query_probes=probes, replay=runs)
    (output / 'metrics.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()

