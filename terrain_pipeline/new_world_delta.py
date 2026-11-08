"""Bind actual mouth interval forcing to the existing integrated delta kernel."""
import numpy as np

from terrain_pipeline.surface_rivers.metric_integrated_delta import run_integrated_delta


def _validate_kernel_result(result, bed, ocean, solid, count):
    from terrain_pipeline.surface_rivers.metric_integrated_delta import integrated_solid_ledger
    if not isinstance(result, dict) or len(result.get('records', ())) != count:
        raise ValueError('invalid delta kernel result')
    for key in ('initial_bed_m', 'final_bed_m', 'height_delta_m', 'stored_solid_m3', 'stage_m', 'depth_m'):
        value = np.asarray(result[key])
        if value.shape != bed.shape or not np.isfinite(value).all():
            raise ValueError('invalid delta kernel result array: ' + key)
    if (not np.array_equal(result['initial_bed_m'], bed) or
            not np.array_equal(result['ocean_mask'], ocean) or
            np.any(result['stored_solid_m3'] < 0)):
        raise ValueError('invalid delta kernel source or inventory')
    ledger = integrated_solid_ledger(result, solid)
    if (not all(np.isfinite(v) and v >= 0 for v in ledger.values()) or
            not np.isclose(ledger['input_solid_m3'], ledger['retained_solid_m3'] +
                           ledger['exported_solid_m3'] + ledger['escrow_solid_m3'],
                           rtol=1e-8, atol=1e-8)):
        raise ValueError('invalid delta kernel solid balance')


class MouthConsumer:
    """In-memory transaction guard; persist consumed keys alongside products."""

    def __init__(self, consumed=()):
        keys = list(consumed)
        self.consumed = set(tuple(key) for key in keys)
        if len(keys) != len(self.consumed):
            raise ValueError("duplicate consumed keys")

    def run(self, *, source_identity, mouth_id, interval_ids, duration_s,
            water_m3, solid_m3, sediment_source, bed_m, ocean_mask, geometry,
            prohibited_mask, config=None):
        if not isinstance(source_identity, str) or not source_identity.strip():
            raise ValueError("source identity required")
        if not isinstance(mouth_id, str) or not mouth_id.strip():
            raise ValueError("stable mouth identity required")
        if not isinstance(sediment_source, str) or not sediment_source.strip():
            raise ValueError("sediment source label required")
        ids = list(interval_ids)
        if not ids or any(not isinstance(i, str) or not i.strip() for i in ids):
            raise ValueError("interval identities required")
        keys = [(source_identity, mouth_id, i) for i in ids]
        if len(set(keys)) != len(keys) or self.consumed.intersection(keys):
            raise ValueError("mouth interval already consumed")
        water, solid, duration = (np.asarray(v, dtype=float) for v in
                                  (water_m3, solid_m3, duration_s))
        if any(v.shape != (len(ids),) or not np.isfinite(v).all() for v in (water, solid, duration)):
            raise ValueError("finite forcing must match interval identities")
        if np.any(water < 0) or np.any(solid < 0) or np.any(duration <= 0):
            raise ValueError("nonnegative volumes and positive durations required")
        bed = np.asarray(bed_m, dtype=float)
        ocean = np.asarray(ocean_mask)
        if (bed.ndim != 2 or not np.isfinite(bed).all() or ocean.dtype.kind != "b"
                or ocean.shape != bed.shape or not np.array_equal(ocean, geometry.ocean_mask)):
            raise ValueError("geometry must use the shared ocean classification")
        prohibited = np.asarray(prohibited_mask)
        if (prohibited.dtype.kind != "b" or prohibited.shape != bed.shape
                or np.any(np.asarray(geometry.eligible_mask, bool) & prohibited)):
            raise ValueError("eligible deposition must exclude protected and unknown cells")
        result = run_integrated_delta(bed, geometry, water, solid, duration, config)
        self.consumed.update(keys)
        return {"result": result, "consumed_keys": keys,
                "sediment_source": sediment_source,
                "construction_bulk_is_sediment": False}


def geometry_fingerprint(bed_m, ocean_mask, geometry, prohibited_mask, config):
    """Bind recovered output to the exact geometry and kernel configuration."""
    import hashlib
    import pickle
    return hashlib.sha256(pickle.dumps((bed_m, ocean_mask, geometry, prohibited_mask, config), protocol=5)).hexdigest()


class DurableMouthConsumer:
    """Single-scheduler SQLite handoff; committed result blobs are the saved output.

    Recover with load_result after a crash; callers exporting files must treat the
    database as authoritative. Do not use multiple independent databases for one source.
    """
    def __init__(self, database):
        import sqlite3
        self.database = str(database)
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE IF NOT EXISTS deliveries (delivery_id TEXT PRIMARY KEY, result BLOB NOT NULL)')
            columns = {row[1] for row in db.execute('PRAGMA table_info(deliveries)')}
            if 'result_sha256' not in columns:
                db.execute('ALTER TABLE deliveries ADD COLUMN result_sha256 TEXT')
            db.execute('CREATE TABLE IF NOT EXISTS intervals (hydraulic TEXT, mouth TEXT, interval TEXT, delivery_id TEXT NOT NULL, PRIMARY KEY (hydraulic, mouth, interval))')

    def load_result(self, delivery_id):
        import pickle
        import sqlite3
        import hashlib
        with sqlite3.connect(self.database) as db:
            row = db.execute('SELECT result, result_sha256 FROM deliveries WHERE delivery_id=?', (delivery_id,)).fetchone()
        if row is None:
            raise KeyError(delivery_id)
        if not row[1] or hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise ValueError('committed delta result integrity failure')
        return pickle.loads(row[0])

    def run(self, *, supply, terrain_identity, hydraulic_identity, mouth_id, interval_ids,
            start_seconds, end_seconds, delivery_id, bed_m, ocean_mask, geometry,
            prohibited_mask, config=None):
        import pickle
        import sqlite3
        import hashlib
        from terrain_pipeline.common_infra import identity
        from terrain_pipeline.surface_rivers.metric_sediment import validate_sediment
        h = supply['hydraulic']
        s = supply['sediment']
        validate_sediment(s)
        if (h['metadata']['status'] != 'complete' or identity(h['arrays'], h['metadata']) != hydraulic_identity
                or supply['hydraulic_identity'] != hydraulic_identity
                or s['metadata']['hydraulic_identity_sha256'] != hydraulic_identity
                or supply['terrain_identity'] != terrain_identity):
            raise ValueError('wrong source or terrain identity')
        mapping = supply['mouth_nodes']
        outlets = set(np.flatnonzero(s['arrays']['domain_open_boundary']).tolist())
        if (not isinstance(mapping, dict) or any(type(v) is not int for v in mapping.values())
                or len(set(mapping.values())) != len(mapping) or set(mapping.values()) != outlets
                or mouth_id not in mapping):
            raise ValueError('invalid mouth outlet mapping')
        ids = list(interval_ids)
        starts, ends = list(start_seconds), list(end_seconds)
        if not ids or len(ids) != len(starts) or len(ids) != len(ends) or len(set(ids)) != len(ids):
            raise ValueError('invalid interval selection')
        packets = {(p['mouth_id'], p['interval_id']): p for p in supply['packets']}
        if len(packets) != len(supply['packets']):
            raise ValueError('duplicate supply packet')
        water, solid, durations = [], [], []
        ha, sa = h['arrays'], s['arrays']
        for interval, start, end in zip(ids, starts, ends):
            p = packets.get((mouth_id, interval))
            if p is None or p['start_s'] != start or p['end_s'] != end or p['duration_s'] != end - start or not end > start:
                raise ValueError('wrong mouth, interval or time')
            i = int(interval)
            if str(i) != interval or i < 0 or i >= len(ha['time_seconds']) - 1 or start != ha['time_seconds'][i] or end != ha['time_seconds'][i + 1]:
                raise ValueError('wrong interval time')
            # Packet node binding is independently checked against the declared outlet mapping.
            node = supply['mouth_nodes'][mouth_id]
            step = (sa['trace_time_seconds'][:-1] >= start) & (sa['trace_time_seconds'][:-1] < end)
            actual_solid = float(sa['step_exported_solid_m3'][step, node].sum())
            actual_water = float(ha['boundary_outflow_volume_m3'][i, node])
            if not np.isclose(p['solid_m3'], actual_solid, rtol=1e-12, atol=1e-12) or not np.isfinite(p['water_m3']) or not np.isfinite(p['solid_m3']) or p['water_m3'] != actual_water:
                raise ValueError('supply packet does not match solved exports')
            water.append(actual_water); solid.append(actual_solid); durations.append(end - start)
        if not isinstance(delivery_id, str) or not delivery_id.strip():
            raise ValueError('delivery identity required')
        with sqlite3.connect(self.database, timeout=30, isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT 1 FROM deliveries WHERE delivery_id=?', (delivery_id,)).fetchone():
                    raise ValueError('delivery already committed; recover with load_result')
                for interval in ids:
                    if db.execute('SELECT 1 FROM intervals WHERE hydraulic=? AND mouth=? AND interval=?', (hydraulic_identity, str(mapping[mouth_id]), interval)).fetchone():
                        raise ValueError('mouth interval already consumed')
                result = MouthConsumer().run(source_identity=hydraulic_identity, mouth_id=mouth_id,
                    interval_ids=ids, duration_s=durations, water_m3=water, solid_m3=solid,
                    sediment_source='actual finite sediment replay', bed_m=bed_m, ocean_mask=ocean_mask,
                    geometry=geometry, prohibited_mask=prohibited_mask, config=config)
                _validate_kernel_result(result['result'], np.asarray(bed_m), np.asarray(ocean_mask), solid, len(ids))
                result['binding'] = {'terrain_identity': terrain_identity, 'hydrology_identity': supply['hydrology_identity'],
                    'hydraulic_identity': hydraulic_identity, 'sediment_identity': supply['sediment_identity'],
                    'mouth_id': mouth_id, 'interval_ids': ids, 'start_seconds': list(map(float, starts)),
                    'end_seconds': list(map(float, ends)),
                    'geometry_sha256': geometry_fingerprint(bed_m, ocean_mask, geometry, prohibited_mask, config)}
                result['forcing'] = {'interval_ids': np.asarray(ids), 'duration_s': np.asarray(durations),
                    'water_m3': np.asarray(water), 'solid_m3': np.asarray(solid)}
                blob = pickle.dumps(result, protocol=5)
                db.execute('INSERT INTO deliveries (delivery_id, result, result_sha256) VALUES (?, ?, ?)',
                           (delivery_id, blob, hashlib.sha256(blob).hexdigest()))
                db.executemany('INSERT INTO intervals VALUES (?, ?, ?, ?)',
                    [(hydraulic_identity, str(mapping[mouth_id]), i, delivery_id) for i in ids])
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise

