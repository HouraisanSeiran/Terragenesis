"""Finite local-water routing with persistent lake storage and explicit partition handoffs.

Unknown external water is deliberately not represented as a zero-volume input.
"""
import hashlib
import json

import numpy as np

from terrain_pipeline.basin_storage import PoolStorage as PoolStorage


def _hash_array_bytes(digest, array):
    """Hash C-order array bytes in bounded chunks, including noncontiguous views."""
    iterator = np.nditer(array, flags=['external_loop', 'buffered', 'zerosize_ok'],
                         op_flags=['readonly'], order='C', buffersize=65536)
    for chunk in iterator:
        digest.update(chunk.tobytes())


def advance(product, local_volume_m3, duration_s, *, interval, source, state=None, partitions=1, reverse_preparation=False):
    manifest, arrays = product
    shape = arrays['bed_m'].shape
    n = np.prod(shape)
    if partitions not in (1, 2, 4) or not isinstance(interval, int) or interval < 0:
        raise ValueError('invalid partitions or interval')
    if not isinstance(source, str) or not source.strip() or not np.isfinite(duration_s) or duration_s <= 0:
        raise ValueError('source and positive duration required')
    local = np.asarray(local_volume_m3, dtype=np.float64)
    if local.ndim == 0:
        local = np.full(shape, local)
    if local.shape != shape or not np.isfinite(local).all() or (local < 0).any():
        raise ValueError('invalid local volume')
    valid = arrays['valid_mask'].ravel()
    marine = np.asarray(arrays.get('ocean_mask', np.zeros(shape, bool)), dtype=bool)
    if marine.shape != shape:
        raise ValueError('invalid ocean mask')
    local = local.copy()
    if np.asarray(local_volume_m3).ndim == 0:
        local.ravel()[~valid] = 0
    if np.any(local.ravel()[~valid] != 0):
        raise ValueError('local volume outside valid terrain')
    local[marine] = 0
    marine = marine.ravel()
    cell_area_m2 = float(manifest.get('cell_area_m2', 900.0))
    if not np.isfinite(cell_area_m2) or cell_area_m2 <= 0:
        raise ValueError('invalid cell area')
    pools = manifest['pools']
    if state is None:
        if interval != 0:
            raise ValueError('first interval must be zero')
        storage = np.zeros(len(pools))
    else:
        if state['hydrology_identity'] != manifest['identity'] or state['next_interval'] != interval or state['source'] != source:
            raise ValueError('state identity, source or interval mismatch')
        storage = np.asarray(state['storage_m3'], dtype=np.float64).copy()
    capacity = np.array([float(p['capacity_m3']) for p in pools])
    if storage.shape != capacity.shape or not np.isfinite(storage).all() or (storage < 0).any() or (storage > capacity).any():
        raise ValueError('invalid lake storage')
    initial = storage.copy()
    basin = arrays['basin_id'].ravel()
    labels = np.full(n, -1, np.int32)
    # Sorting avoids a full-domain scan per pool.
    if pools:
        ids = np.array([int(p['id']) for p in pools], dtype=np.uint64)
        order_ids = np.argsort(ids)
        pos = np.searchsorted(ids[order_ids], basin)
        hit = (basin != 0) & (pos < len(ids))
        cells = np.flatnonzero(hit)
        if np.any(ids[order_ids[pos[cells]]] != basin[cells]):
            raise ValueError('unlisted basin')
        labels[cells] = order_ids[pos[cells]]
    receiver = arrays['receiver'].ravel()
    order = np.argsort(arrays['rank'].ravel())[::-1]
    anchors = np.array([p['anchor_index'] for p in pools], dtype=np.int64)
    owners = np.zeros(shape, np.uint8)
    if partitions == 2:
        owners[:, shape[1] // 2:] = 1
    elif partitions == 4:
        owners[shape[0] // 2:, :] += 2
        owners[:, shape[1] // 2:] += 1
    owners = owners.ravel()
    # Preparation order does not alter the global dependency schedule.
    preparation = list(range(partitions))
    if reverse_preparation:
        preparation.reverse()
    queues = [dict() for _ in preparation]
    flow = local.ravel().copy()
    incoming = np.zeros(len(pools))
    outgoing = np.zeros(len(pools))
    packets = []
    mouth_flow = {}
    for cell in order:
        if not valid[cell] or marine[cell]:
            continue
        label = labels[cell]
        if label >= 0:
            incoming[label] += flow[cell]
            if cell != anchors[label]:
                continue
            available = storage[label] + incoming[label]
            storage[label] = min(capacity[label], available)
            flow[cell] = available - storage[label]
            outgoing[label] = flow[cell]
        target = receiver[cell]
        if target >= 0 and marine[target]:
            mouth_flow[int(cell)] = float(flow[cell])
        elif target >= 0:
            volume = float(flow[cell])
            if owners[cell] != owners[target]:
                # Debit before credit. Packet identity binds time, source and edge.
                flow[cell] = 0
                token = hashlib.sha256(f"{manifest['identity']}:{source}:{interval}:{cell}:{target}".encode()).hexdigest()
                packet = {'id': token, 'source': source, 'interval': interval, 'from': int(cell),
                          'to': int(target), 'volume_m3': volume}
                deliver_packet(queues[int(owners[target])], packet, source=source, interval=interval)
                flow[target] += queues[int(owners[target])][token]
                packets.append(packet)
            else:
                flow[target] += volume
    terminals = np.flatnonzero(valid & ~marine & (receiver < 0))
    unknown = arrays['total_water_unknown'].ravel()
    outlets = [{'index': int(i), 'kind': int(arrays['terminal_kind'].ravel()[i]),
                'watershed_id': str(int(arrays['watershed_id'].ravel()[i])),
                'known_local_volume_m3': float(flow[i]), 'known_local_q_m3_s': float(flow[i] / duration_s),
                'total_water_unknown': bool(unknown[i])} for i in terminals]
    outlets.extend({'index': i, 'receiver_index': int(receiver[i]), 'kind': 'marine',
                    'mouth_id': f'{i}:{int(receiver[i])}', 'watershed_id': str(int(arrays['watershed_id'].ravel()[i])),
                    'known_local_volume_m3': volume, 'known_local_q_m3_s': volume / duration_s,
                    'total_water_unknown': bool(unknown[i])} for i, volume in sorted(mouth_flow.items()))
    lakes = []
    bed = arrays['bed_m'].ravel()
    pool_cells = np.flatnonzero(labels >= 0)
    pool_cells = pool_cells[np.argsort(labels[pool_cells], kind='stable')]
    counts = np.bincount(labels[pool_cells], minlength=len(pools))
    offsets = np.concatenate(([0], np.cumsum(counts)))
    for i, pool in enumerate(pools):
        members = pool_cells[offsets[i]:offsets[i + 1]]
        curve = PoolStorage(members, bed, pool['spill_stage_m'], cell_area_m2)
        stage = curve.stage_at_volume(storage[i])
        lakes.append({'id': pool['id'], 'owner': int(owners[anchors[i]]), 'storage_m3': float(storage[i]),
                      'level_m': float(stage), 'wet_area_m2': float(np.count_nonzero(bed[members] < stage) * cell_area_m2),
                      'inflow_m3': float(incoming[i]), 'outflow_m3': float(outgoing[i])})
    total = float(local.sum())
    discharged = sum(x['known_local_volume_m3'] for x in outlets)
    residual = total + float(initial.sum()) - discharged - float(storage.sum())
    if abs(residual) > max(1e-7, (total + float(initial.sum())) * 1e-10):
        raise ValueError('water balance failed')
    return {'interval': interval, 'duration_s': float(duration_s), 'source': source,
            'external_water': 'unknown where flagged', 'marine_semantics': 'ocean_mask' if 'ocean_mask' in arrays else 'legacy_no_ocean_mask', 'local_input_m3': total, 'outlets': outlets,
            'lakes': lakes, 'residual_m3': residual, 'packets': packets,
            'state': {'hydrology_identity': manifest['identity'], 'source': source,
                      'next_interval': interval + 1, 'storage_m3': storage.tolist()}}


def deliver_packet(received, packet, *, source, interval):
    """Accept a handoff exactly once, for its declared source and interval."""
    if packet['source'] != source or packet['interval'] != interval or packet['id'] in received:
        raise ValueError('duplicate, wrong-source or wrong-interval packet')
    volume = packet['volume_m3']
    if not np.isfinite(volume) or volume < 0:
        raise ValueError('invalid packet volume')
    received[packet['id']] = volume





class PartitionRouter:
    """Durable, deterministic finite routing. Only one scheduler may use a journal at a time.

    Node and lake ledgers are stored per owner. A checkpoint commits all changed
    owner ledgers, packet records and the global rank cursor in one transaction.
    """
    def __init__(self, journal, product, local_volume_m3, duration_s, *, interval,
                 source, partitions=1, state=None, reverse_preparation=False, trace=False):
        import sqlite3

        manifest, arrays = product
        self.product = product
        self.shape = arrays['bed_m'].shape
        if len(self.shape) != 2 or partitions not in (1, 2, 4):
            raise ValueError('invalid shape or partitions')
        if type(interval) is not int or interval < 0 or not isinstance(source, str) or not source.strip():
            raise ValueError('invalid interval or source')
        if not np.isfinite(duration_s) or duration_s <= 0:
            raise ValueError('invalid duration')
        local = np.asarray(local_volume_m3, dtype=np.float64)
        valid = np.asarray(arrays['valid_mask'], dtype=bool).ravel()
        marine = np.asarray(arrays.get('ocean_mask', np.zeros(self.shape, bool)), dtype=bool)
        if marine.shape != self.shape:
            raise ValueError('invalid ocean mask')
        self.marine = marine.ravel()
        n = valid.size
        if local.ndim == 0:
            if not np.isfinite(local) or local < 0:
                raise ValueError('invalid local volume')
        elif (local.shape != self.shape or not np.isfinite(local).all() or
              np.any(local < 0) or np.any(local.ravel()[~valid & ~self.marine] != 0)):
            raise ValueError('invalid local volume')
        self.valid = valid
        self.receiver = np.asarray(arrays['receiver']).ravel()
        rank = np.asarray(arrays['rank']).ravel()
        if self.receiver.size != n or rank.size != n or np.any((self.receiver < -1) | (self.receiver >= n)):
            raise ValueError('invalid graph')
        nodes = np.flatnonzero(valid)
        targets = self.receiver[nodes]
        edges = targets >= 0
        if np.any(~valid[targets[edges]]) or np.any(rank[nodes[edges]] <= rank[targets[edges]]):
            raise ValueError('graph is not strictly ranked')
        nodes = nodes[~self.marine[nodes]]
        if n > np.iinfo(np.int32).max or len(nodes) > np.iinfo(np.int32).max:
            raise ValueError('native grid exceeds int32 active index bounds')
        self.active_to_native = nodes.astype(np.int32)
        self.native_to_active = np.full(n, -1, np.int32)
        self.native_to_active[nodes] = np.arange(len(nodes), dtype=np.int32)
        self.order = nodes[np.argsort(rank[nodes], kind='stable')[::-1]].astype(np.int32)
        active_local = (np.full(len(nodes), local, dtype=np.float64) if local.ndim == 0
                        else local.ravel()[self.active_to_native].copy())
        self.pools = manifest['pools']
        self.capacity = np.array([float(p['capacity_m3']) for p in self.pools])
        self.anchors = np.array([int(p['anchor_index']) for p in self.pools], dtype=np.int64)
        ids = np.array([int(p['id']) for p in self.pools], dtype=np.uint64)
        if len(np.unique(ids)) != len(ids) or not np.isfinite(self.capacity).all() or (self.capacity < 0).any() or np.any((self.anchors < 0) | (self.anchors >= n)):
            raise ValueError('invalid pools')
        basin = np.asarray(arrays['basin_id']).ravel()
        self.labels = np.full(len(nodes), -1, np.int32)
        if len(ids):
            sorted_ids = np.argsort(ids)
            cells = np.flatnonzero(basin != 0)
            positions = np.searchsorted(ids[sorted_ids], basin[cells])
            if np.any(positions >= len(ids)) or np.any(ids[sorted_ids[np.minimum(positions, len(ids)-1)]] != basin[cells]):
                raise ValueError('unlisted basin')
            if np.any(self.native_to_active[cells] < 0):
                raise ValueError('pool membership must be active land')
            self.labels[self.native_to_active[cells]] = sorted_ids[positions]
            if np.any(self.native_to_active[self.anchors] < 0) or np.any(self.labels[self.native_to_active[self.anchors]] != np.arange(len(ids))) or np.any(~valid[cells]):
                raise ValueError('invalid pool membership')
            cell_labels = self.labels[self.native_to_active[cells]]
            nonanchors = cells != self.anchors[cell_labels]
            if np.any(rank[cells[nonanchors]] <= rank[self.anchors[cell_labels[nonanchors]]]):
                raise ValueError('pool anchor must be processed last')
        self.partitions = partitions
        self.owners = self._owner_of(self.active_to_native).astype(np.uint8)
        self.members = [None] * partitions
        preparation = range(partitions - 1, -1, -1) if reverse_preparation else range(partitions)
        for owner in preparation:
            self.members[owner] = np.flatnonzero(self.owners == owner).astype(np.int32)
        self.local_index = np.empty(len(nodes), np.int32)
        for member in self.members:
            self.local_index[member] = np.arange(len(member), dtype=np.int32)
        self.pool_owner = self._owner_of(self.anchors).astype(np.uint8)
        self.anchor_positions = np.empty(len(ids), np.int32)
        if len(ids):
            order_active = self.native_to_active[self.order]
            positions = np.empty(len(nodes), np.int32)
            positions[order_active] = np.arange(len(nodes), dtype=np.int32)
            self.anchor_positions[:] = positions[self.native_to_active[self.anchors]]
        storage = np.zeros(len(ids))
        if state is None:
            if interval != 0:
                raise ValueError('first interval must be zero')
        else:
            if state.get('hydrology_identity') != manifest['identity'] or state.get('source') != source or state.get('next_interval') != interval:
                raise ValueError('cold state identity, source or interval mismatch')
            storage = np.asarray(state['storage_m3'], dtype=np.float64)
        if storage.shape != self.capacity.shape or not np.isfinite(storage).all() or np.any(storage < 0) or np.any(storage > self.capacity):
            raise ValueError('invalid cold storage')
        digest = hashlib.sha256()
        for name in ('bed_m', 'valid_mask', 'basin_id', 'receiver', 'rank', 'terminal_kind', 'watershed_id', 'total_water_unknown'):
            a = np.asarray(arrays[name])
            digest.update(name.encode()); digest.update(str(a.shape).encode()); digest.update(a.dtype.str.encode())
            _hash_array_bytes(digest, a)
        if 'ocean_mask' in arrays:
            a = np.asarray(arrays['ocean_mask'])
            digest.update(b'ocean_mask'); digest.update(str(a.shape).encode()); digest.update(a.dtype.str.encode())
            _hash_array_bytes(digest, a)
        digest.update(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
        _hash_array_bytes(digest, active_local)
        digest.update(storage.tobytes())
        config = {'journal_schema': 3, 'fingerprint': digest.hexdigest(), 'source': source, 'interval': interval,
                  'duration_s': float(duration_s), 'partitions': partitions}
        if trace:
            config['trace'] = True
        self.config = config
        # Inspect existing journals read-only before enabling WAL or creating tables.
        # Older mappings are never migrated or modified implicitly.
        from pathlib import Path
        journal_path = Path(journal)
        if str(journal) != ':memory:' and journal_path.is_file():
            from contextlib import closing
            with closing(sqlite3.connect(journal_path.resolve().as_uri() + '?mode=ro', uri=True)) as existing:
                table = existing.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone()
                if table:
                    old_row = existing.execute("SELECT value FROM metadata WHERE key='config'").fetchone()
                    if old_row is not None:
                        try:
                            old_config = json.loads(old_row[0])
                        except (TypeError, json.JSONDecodeError) as exc:
                            raise ValueError('invalid journal schema') from exc
                        if not isinstance(old_config, dict) or old_config.get('journal_schema') != 3:
                            raise ValueError('unsupported journal schema: active-land mapping requires a new journal')
        self.db = sqlite3.connect(str(journal))
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value BLOB NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS nodes (owner INTEGER NOT NULL, cell INTEGER NOT NULL, volume REAL NOT NULL, PRIMARY KEY(owner, cell))')
        self.db.execute('CREATE TABLE IF NOT EXISTS pools (owner INTEGER NOT NULL, pool INTEGER NOT NULL, storage REAL NOT NULL, incoming REAL NOT NULL, outgoing REAL NOT NULL, PRIMARY KEY(owner, pool))')
        if trace:
            self.db.execute('CREATE TABLE IF NOT EXISTS trace (cell INTEGER PRIMARY KEY, volume REAL NOT NULL)')
        self.trace = trace
        self.db.execute('CREATE TABLE IF NOT EXISTS outlets (cell INTEGER PRIMARY KEY, volume REAL NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS packets (id TEXT PRIMARY KEY, source TEXT NOT NULL, interval INTEGER NOT NULL, sender INTEGER NOT NULL, recipient INTEGER NOT NULL, target_kind TEXT NOT NULL, target INTEGER NOT NULL, volume REAL NOT NULL, received INTEGER NOT NULL DEFAULT 0)')
        row = self.db.execute("SELECT value FROM metadata WHERE key='config'").fetchone()
        self.flow = [active_local[m].copy() for m in self.members]
        self.pool_state = [dict() for _ in self.members]
        for i, owner in enumerate(self.pool_owner):
            self.pool_state[int(owner)][i] = [float(storage[i]), 0., 0.]
        self.dirty_nodes = set()
        self.dirty_pools = set()
        self.dirty_outlets = set()
        if row is None:
            self.cursor = 0
            self.initial = float(storage.sum())
            self.input = float(active_local.sum())
            self.outlet = 0.
            self.outlets = {}
            self.pending = None
            with self.db:
                self.db.execute("INSERT INTO metadata VALUES ('config', ?)", (json.dumps(config, sort_keys=True),))
                self._save()
        else:
            try:
                saved_config = json.loads(row[0])
                if saved_config.get('journal_schema') != 3:
                    raise ValueError('unsupported journal schema: active-land mapping requires a new journal')
                if saved_config != config:
                    raise ValueError('journal identity, source, interval or input mismatch')
                for owner, cell, volume in self.db.execute('SELECT owner, cell, volume FROM nodes'):
                    if not 0 <= cell < n or not 0 <= owner < partitions or self.native_to_active[cell] < 0 or self.owners[self.native_to_active[cell]] != owner:
                        raise ValueError('invalid node owner')
                    self.flow[owner][self.local_index[self.native_to_active[cell]]] = volume
                for owner, pool, stored, incoming, outgoing in self.db.execute('SELECT owner, pool, storage, incoming, outgoing FROM pools'):
                    if not 0 <= pool < len(ids) or not 0 <= owner < partitions or self.pool_owner[pool] != owner:
                        raise ValueError('invalid pool owner')
                    self.pool_state[owner][pool] = [stored, incoming, outgoing]
                progress = json.loads(self.db.execute("SELECT value FROM metadata WHERE key='progress'").fetchone()[0])
                if progress.get('schema') != 3:
                    raise ValueError('invalid journal schema')
                self.cursor, self.initial, self.input, self.outlet, self.pending = (progress[k] for k in ('cursor', 'initial', 'input', 'outlet', 'pending'))
                self.outlets = dict(self.db.execute('SELECT cell, volume FROM outlets'))
                self._validate_loaded()
            except (TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ValueError('invalid journal schema') from exc

    def _validate_loaded(self):
        if not 0 <= self.cursor <= len(self.order):
            raise ValueError('invalid journal cursor')
        for owner, flow in enumerate(self.flow):
            if flow.shape != (len(self.members[owner]),) or not np.isfinite(flow).all() or np.any(flow < 0):
                raise ValueError('invalid owner node ledger')
            expected = set(np.flatnonzero(self.pool_owner == owner))
            if set(self.pool_state[owner]) != expected:
                raise ValueError('invalid owner pool ledger')
            for i, values in self.pool_state[owner].items():
                if len(values) != 3 or not np.isfinite(values).all() or min(values) < 0 or values[0] > self.capacity[i]:
                    raise ValueError('invalid owner pool state')
        if not np.isfinite([self.initial, self.input, self.outlet]).all() or min(self.initial, self.input, self.outlet) < 0:
            raise ValueError('invalid progress budget')
        if self.pending is not None and self.db.execute('SELECT received FROM packets WHERE id=?', (self.pending,)).fetchone() != (0,):
            raise ValueError('invalid pending packet')
        if abs(self.budget()['residual_m3']) > max(1e-7, (self.initial + self.input) * 1e-10):
            raise ValueError('invalid journal budget')

    def _save(self):
        self.db.executemany('INSERT OR REPLACE INTO nodes VALUES (?, ?, ?)',
                            ((owner, cell, float(self.flow[owner][self.local_index[self.native_to_active[cell]]])) for owner, cell in self.dirty_nodes))
        self.db.executemany('INSERT OR REPLACE INTO pools VALUES (?, ?, ?, ?, ?)',
                            ((owner, pool, *self.pool_state[owner][pool]) for owner, pool in self.dirty_pools))
        self.db.executemany('INSERT OR REPLACE INTO outlets VALUES (?, ?)',
                            ((cell, self.outlets[cell]) for cell in self.dirty_outlets))
        progress = dict(schema=3, cursor=self.cursor, initial=self.initial, input=self.input,
                        outlet=self.outlet, pending=self.pending)
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('progress', ?)", (json.dumps(progress),))
        self.dirty_nodes.clear()
        self.dirty_pools.clear()
        self.dirty_outlets.clear()

    def _send(self, sender, recipient, kind, target, volume, cell):
        token = hashlib.sha256(f"{self.config['fingerprint']}:{cell}:{kind}:{target}".encode()).hexdigest()
        self.db.execute('INSERT INTO packets VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)',
                        (token, self.config['source'], self.config['interval'], sender, recipient, kind, target, volume))
        self.pending = token

    def _receive(self, packet_id, *, source, interval):
        if source != self.config['source'] or interval != self.config['interval']:
            raise ValueError('wrong source or interval')
        row = self.db.execute('SELECT recipient, target_kind, target, volume, received FROM packets WHERE id=?', (packet_id,)).fetchone()
        if row is None or row[4] or packet_id != self.pending:
            raise ValueError('unknown or duplicate packet')
        owner, kind, target, volume, _ = row
        if kind == 'mouth':
            self.outlet += volume
            self.outlets[target] = volume
            self.dirty_outlets.add(target)
        elif kind == 'pool':
            self.pool_state[owner][target][1] += volume
            self.dirty_pools.add((owner, target))
        else:
            self.flow[owner][self.local_index[self.native_to_active[target]]] += volume
            self.dirty_nodes.add((owner, target))
        self.db.execute('UPDATE packets SET received=1 WHERE id=? AND received=0', (packet_id,))
        self.pending = None

    def receive(self, packet_id, *, source, interval):
        with self.db:
            self._receive(packet_id, source=source, interval=interval)
            self._save()

    def run(self, *, stop_after=None, batch_size=4096, max_cells=None):
        if stop_after not in (None, 'send', 'receive') or batch_size < 1 or (max_cells is not None and (type(max_cells) is not int or max_cells < 1)):
            raise ValueError('invalid run option')
        count = 0
        start_cursor = self.cursor
        with self.db:
            while self.pending is not None or self.cursor < len(self.order):
                if self.pending is not None:
                    self._receive(self.pending, source=self.config['source'], interval=self.config['interval'])
                    self._save()
                    self.db.commit()
                    if stop_after == 'receive' or self.cursor == len(self.order):
                        break
                if max_cells is not None and self.cursor - start_cursor >= max_cells:
                    break
                cell = int(self.order[self.cursor]); self.cursor += 1
                active = self.native_to_active[cell]
                owner = int(self.owners[active]); idx = self.local_index[active]
                volume = float(self.flow[owner][idx]); self.flow[owner][idx] = 0.
                self.dirty_nodes.add((owner, cell))
                label = int(self.labels[active])
                if label >= 0:
                    pool_owner = int(self.pool_owner[label])
                    if owner != pool_owner:
                        self._send(owner, pool_owner, 'pool', label, volume, cell)
                        self._save()
                        self.db.commit()
                        if stop_after == 'send':
                            break
                        continue
                    self.dirty_pools.add((owner, label))
                    pool = self.pool_state[owner][label]
                    pool[1] += volume
                    if cell != self.anchors[label]:
                        continue
                    available = pool[0] + pool[1]
                    pool[0] = min(self.capacity[label], available)
                    volume = available - pool[0]
                    pool[2] = volume
                if self.trace:
                    self.db.execute('INSERT OR REPLACE INTO trace VALUES (?, ?)', (cell, volume))
                target = int(self.receiver[cell])
                if target >= 0 and self.marine[target]:
                    target_owner = int(self._owner_of(target))
                    if owner == target_owner:
                        self.outlet += volume
                        self.outlets[cell] = volume
                        self.dirty_outlets.add(cell)
                    else:
                        self._send(owner, target_owner, 'mouth', cell, volume, cell)
                        self._save()
                        self.db.commit()
                        if stop_after == 'send':
                            break
                elif target < 0:
                    self.outlet += volume
                    self.outlets[cell] = volume
                    self.dirty_outlets.add(cell)
                else:
                    target_owner = int(self._owner_of(target))
                    if owner == target_owner:
                        self.flow[owner][self.local_index[self.native_to_active[target]]] += volume
                        self.dirty_nodes.add((owner, target))
                    else:
                        self._send(owner, target_owner, 'node', target, volume, cell)
                        self._save()
                        self.db.commit()
                        if stop_after == 'send':
                            break
                count += 1
                if count >= batch_size:
                    self._save()
                    self.db.commit()
                    count = 0
            self._save()
        return self.budget()

    def budget(self):
        inflight = self.db.execute('SELECT COALESCE(SUM(volume),0) FROM packets WHERE received=0').fetchone()[0]
        nodes = sum(float(x.sum()) for x in self.flow)
        pools = sum(v[0] + (v[1] if self.cursor <= self._anchor_position(i) else 0.) for owner in self.pool_state for i, v in owner.items())
        return {'input_m3': self.input, 'initial_pool_m3': self.initial, 'outlet_m3': self.outlet,
                'pool_m3': pools, 'node_m3': nodes, 'inflight_m3': inflight,
                'residual_m3': self.input + self.initial - self.outlet - pools - nodes - inflight,
                'complete': self.cursor == len(self.order) and self.pending is None}

    def _owner_of(self, native):
        native = np.asarray(native)
        owner = np.zeros_like(native, dtype=np.uint8)
        if self.partitions >= 2:
            owner += (native % self.shape[1] >= self.shape[1] // 2).astype(np.uint8)
        if self.partitions == 4:
            owner += 2 * (native // self.shape[1] >= self.shape[0] // 2).astype(np.uint8)
        return owner

    def _anchor_position(self, i):
        return self.anchor_positions[i]

    def result(self):
        budget = self.budget()
        if not budget['complete']:
            raise ValueError('routing is incomplete')
        manifest, arrays = self.product
        storage = [self.pool_state[int(self.pool_owner[i])][i][0] for i in range(len(self.pools))]
        outlets = [{'index': int(i), 'kind': int(arrays['terminal_kind'].ravel()[i]),
                    'watershed_id': str(int(arrays['watershed_id'].ravel()[i])),
                    'known_local_volume_m3': float(self.outlets[i]),
                    'known_local_q_m3_s': float(self.outlets[i] / self.config['duration_s']),
                    'total_water_unknown': bool(arrays['total_water_unknown'].ravel()[i])} for i in sorted(self.outlets)]
        for row in outlets:
            target = int(self.receiver[row['index']])
            if target >= 0 and self.marine[target]:
                row.update(kind='marine', receiver_index=target, mouth_id=f"{row['index']}:{target}")
        return {'source': self.config['source'], 'interval': self.config['interval'],
                'marine_semantics': 'ocean_mask' if 'ocean_mask' in arrays else 'legacy_no_ocean_mask',
                'external_water': 'unknown where flagged', 'outlets': outlets, 'budget': budget,
                'lakes': [{'id': p['id'], 'owner': int(self.pool_owner[i]), 'storage_m3': storage[i],
                           'inflow_m3': self.pool_state[int(self.pool_owner[i])][i][1],
                           'outflow_m3': self.pool_state[int(self.pool_owner[i])][i][2]} for i, p in enumerate(self.pools)],
                'state': {'hydrology_identity': manifest['identity'], 'source': self.config['source'],
                          'next_interval': self.config['interval'] + 1, 'storage_m3': storage}}

    def close(self):
        self.db.close()

def main():
    """Route one interval from an existing verified v2 product and .npy volume grid."""
    import argparse
    from pathlib import Path
    from terrain_pipeline.new_world_hydrology import read_product

    parser = argparse.ArgumentParser()
    parser.add_argument('product')
    parser.add_argument('local_volume_npy')
    parser.add_argument('output_json')
    parser.add_argument('--duration-s', type=float, required=True)
    parser.add_argument('--interval', type=int, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--state-json')
    parser.add_argument('--partitions', type=int, choices=(1, 2, 4), default=1)
    parser.add_argument('--journal', help='enable persistent partition-owned routing')
    parser.add_argument('--stop-after', choices=('send', 'receive'))
    parser.add_argument('--reverse-preparation', action='store_true')
    args = parser.parse_args()
    output = Path(args.output_json)
    if output.exists():
        parser.error('output already exists')
    state = None
    if args.state_json:
        state = json.loads(Path(args.state_json).read_text(encoding='utf-8'))['state']
    product = read_product(args.product)
    local = np.load(args.local_volume_npy, allow_pickle=False)
    if args.journal:
        router = PartitionRouter(args.journal, product, local, args.duration_s, interval=args.interval,
                                 source=args.source, state=state, partitions=args.partitions,
                                 reverse_preparation=args.reverse_preparation)
        progress = router.run(stop_after=args.stop_after)
        result = router.result() if progress['complete'] else {'budget': progress, 'pending_packet': router.pending}
        router.close()
    else:
        result = advance(product, local, args.duration_s, interval=args.interval, source=args.source,
                         state=state, partitions=args.partitions, reverse_preparation=args.reverse_preparation)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, allow_nan=False)


if __name__ == '__main__':
    main()
