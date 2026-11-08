import json
import numpy as np
import pytest
from terrain_pipeline.new_world_river_lifecycle import advance, deliver_packet


def test_bounded_hash_preserves_journal_fingerprint_bytes():
    import hashlib
    from terrain_pipeline.new_world_river_lifecycle import _hash_array_bytes

    arrays = [np.arange(300000, dtype='>i8').reshape(500, 600),
              np.arange(1000, dtype=np.float64).reshape(20, 50)[:, ::-2],
              np.empty((0, 2), dtype=np.float32)]
    for array in arrays:
        actual = hashlib.sha256()
        _hash_array_bytes(actual, array)
        expected = hashlib.sha256(np.ascontiguousarray(array).tobytes())
        assert actual.digest() == expected.digest()


def product():
    # Four cells converge into a pool then leave at an ocean outlet.
    shape = (2, 3)
    arrays = {'bed_m': np.array([[3, 2, 0], [4, 1, 0]], dtype=np.float32),
              'valid_mask': np.ones(shape, bool), 'basin_id': np.array([[0, 0, 0], [0, 7, 0]], np.uint64),
              'receiver': np.array([[1, 4, -1], [4, 2, -1]]),
              'rank': np.array([[5, 4, 0], [3, 2, 1]]),
              'terminal_kind': np.ones(shape, np.uint8), 'watershed_id': np.ones(shape, np.uint64),
              'total_water_unknown': np.array([[False, False, True], [False, True, True]])}
    manifest = {'identity': 'a'*64, 'pools': [{'id': '7', 'anchor_index': 4, 'spill_stage_m': 2., 'capacity_m3': 900.}]}
    return manifest, arrays


def test_partitions_and_cold_resume():
    p = product()
    wet = np.zeros((2, 3)); wet[0, 0] = 600
    dry = np.zeros((2, 3)); dry[1, 0] = 600
    first = advance(p, wet, 10, interval=0, source='rain', partitions=1)
    second = advance(p, dry, 10, interval=1, source='rain', state=first['state'])
    assert first['lakes'][0]['storage_m3'] == 600
    assert second['lakes'][0]['storage_m3'] == 900
    assert sum(x['known_local_volume_m3'] for x in second['outlets']) == 300
    for count in (2, 4):
        a = advance(p, wet, 10, interval=0, source='rain', partitions=count, reverse_preparation=True)
        b = advance(p, dry, 10, interval=1, source='rain', state=json.loads(json.dumps(a['state'])), partitions=count)
        assert a['state'] == first['state']
        assert b['state'] == second['state']
        assert b['outlets'] == second['outlets']
        assert a['packets']
    with pytest.raises(ValueError):
        advance(p, dry, 10, interval=2, source='rain', state=first['state'])
    with pytest.raises(ValueError):
        advance(p, dry, 10, interval=1, source='other', state=first['state'])


def test_packet_rejection():
    received = {}
    p = {'id': 'a', 'source': 'rain', 'interval': 0, 'volume_m3': 3.}
    deliver_packet(received, p, source='rain', interval=0)
    with pytest.raises(ValueError): deliver_packet(received, p, source='rain', interval=0)
    with pytest.raises(ValueError): deliver_packet({}, p, source='other', interval=0)
    with pytest.raises(ValueError): deliver_packet({}, p, source='rain', interval=1)


def spanning_product():
    manifest, arrays = product()
    arrays['basin_id'][0, 1] = 7
    return manifest, arrays


def test_persistent_partitions_restart_and_validation(tmp_path):
    import subprocess
    import sys
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter

    p = spanning_product()
    local = np.array([[600., 100., 0.], [600., 200., 0.]])
    results = []
    for count in (1, 2, 4):
        path = tmp_path / f'{count}.sqlite'
        router = PartitionRouter(path, p, local, 10, interval=0, source='rain', partitions=count, reverse_preparation=True)
        if count > 1:
            budget = router.run(stop_after='send')
            assert budget['inflight_m3'] > 0
            assert abs(budget['residual_m3']) < 1e-9
            token = router.pending
            with pytest.raises(ValueError):
                router.receive(token, source='wrong', interval=0)
            with pytest.raises(ValueError):
                router.receive(token, source='rain', interval=1)
            router.close()
            # A genuinely new interpreter reloads the journal and commits the receive.
            script = '''import sys, numpy as np
from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
sys.path.insert(0, 'tests')
from test_new_world_river_lifecycle import spanning_product
r = PartitionRouter(sys.argv[1], spanning_product(), np.array([[600.,100.,0.],[600.,200.,0.]]), 10, interval=0, source='rain', partitions=int(sys.argv[2]))
r.run(stop_after='receive')
r.close()
'''
            subprocess.run([sys.executable, '-c', script, str(path), str(count)], check=True)
            router = PartitionRouter(path, p, local, 10, interval=0, source='rain', partitions=count)
            assert router.pending is None
            with pytest.raises(ValueError):
                router.receive(token, source='rain', interval=0)
            assert abs(router.budget()['residual_m3']) < 1e-9
            router.close()
            router = PartitionRouter(path, p, local, 10, interval=0, source='rain', partitions=count)
        router.run()
        result = router.result()
        assert result['lakes'][0]['storage_m3'] == 900
        assert sum(o['known_local_volume_m3'] for o in result['outlets']) == 600
        assert all(o['total_water_unknown'] for o in result['outlets'])
        assert abs(result['budget']['residual_m3']) < 1e-9
        results.append(result)
        router.close()
    assert [r['outlets'] for r in results].count(results[0]['outlets']) == 3
    assert [r['state'] for r in results].count(results[0]['state']) == 3
    with pytest.raises(ValueError):
        PartitionRouter(tmp_path / 'bad.sqlite', p, local, 10, interval=1, source='rain', state={'hydrology_identity': p[0]['identity'], 'source': 'rain', 'next_interval': 1, 'storage_m3': [901.]})
    with pytest.raises(ValueError):
        PartitionRouter(tmp_path / '2.sqlite', p, local, 10, interval=0, source='other', partitions=2)


def test_persistent_second_interval_and_corrupt_cold_state(tmp_path):
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
    p = spanning_product()
    first_input = np.array([[600., 100., 0.], [600., 200., 0.]])
    router = PartitionRouter(tmp_path / 'first.db', p, first_input, 10, interval=0, source='rain', partitions=4)
    router.run()
    state = router.result()['state']
    router.close()
    dry = np.zeros((2, 3)); dry[0, 0] = 300
    router = PartitionRouter(tmp_path / 'second.db', p, dry, 10, interval=1, source='rain', state=state, partitions=4)
    router.run()
    result = router.result()
    assert result['state']['storage_m3'] == [900]
    assert sum(x['known_local_volume_m3'] for x in result['outlets']) == 300
    assert abs(result['budget']['residual_m3']) < 1e-9
    router.close()
    bad = dict(state, storage_m3=[float('nan')])
    with pytest.raises(ValueError):
        PartitionRouter(tmp_path / 'bad2.db', p, dry, 10, interval=1, source='rain', state=bad)


def test_journal_writes_track_changed_rows_not_owner_size(tmp_path):
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter

    writes = []
    for width in (4, 4000):
        shape = (2, width)
        arrays = {'bed_m': np.zeros(shape), 'valid_mask': np.ones(shape, bool),
                  'basin_id': np.zeros(shape, np.uint64), 'receiver': np.full(shape, -1),
                  'rank': np.zeros(shape, np.int64), 'terminal_kind': np.ones(shape, np.uint8),
                  'watershed_id': np.ones(shape, np.uint64), 'total_water_unknown': np.ones(shape, bool)}
        arrays['rank'][0, 0] = 2
        arrays['rank'][0, width // 2] = 1
        arrays['receiver'][0, 0] = width // 2
        local = np.zeros(shape); local[0, 0] = 5
        r = PartitionRouter(tmp_path / f'{width}.db', ({'identity': 'test', 'pools': []}, arrays), local, 1,
                            interval=0, source='rain', partitions=2)
        before = r.db.total_changes
        r.run(stop_after='send')
        writes.append(r.db.total_changes - before)
        assert r.db.execute('select count(*) from nodes').fetchone()[0] == 1
        r.close()
    assert writes[0] == writes[1]


def marine_product(width=6):
    shape = (2, width)
    arrays = {'bed_m': np.zeros(shape), 'valid_mask': np.ones(shape, bool),
              'ocean_mask': np.ones(shape, bool), 'basin_id': np.zeros(shape, np.uint64),
              'receiver': np.full(shape, -1), 'rank': np.zeros(shape, np.int64),
              'terminal_kind': np.ones(shape, np.uint8), 'watershed_id': np.ones(shape, np.uint64),
              'total_water_unknown': np.zeros(shape, bool)}
    arrays['ocean_mask'][0, :2] = False
    arrays['receiver'][0, :2] = width // 2
    arrays['rank'][0, :2] = [2, 1]
    arrays['total_water_unknown'][0, 1] = True
    return {'identity': 'marine', 'pools': []}, arrays


def test_marine_mouths_restart_and_identity(tmp_path):
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
    p = marine_product()
    local = np.zeros((2, 6)); local[0, :2] = [3, 7]; local[1, :] = 99
    path = tmp_path / 'marine.db'
    r = PartitionRouter(path, p, local, 2, interval=0, source='rain', partitions=2)
    budget = r.run(stop_after='send')
    assert budget['inflight_m3'] == 3
    assert budget['residual_m3'] == 0
    r.close()
    r = PartitionRouter(path, p, local, 2, interval=0, source='rain', partitions=2)
    r.run(stop_after='receive')
    assert r.budget()['outlet_m3'] == 3
    r.close()
    r = PartitionRouter(path, p, local, 2, interval=0, source='rain', partitions=2)
    r.run()
    result = r.result()
    assert [(o['index'], o['receiver_index'], o['known_local_volume_m3']) for o in result['outlets']] == [(0, 3, 3), (1, 3, 7)]
    assert len({o['mouth_id'] for o in result['outlets']}) == 2
    assert result['outlets'][1]['total_water_unknown']
    assert result['budget']['residual_m3'] == 0
    r.close()
    p[1]['ocean_mask'][1, 0] = False
    with pytest.raises(ValueError, match='mismatch'):
        PartitionRouter(path, p, local, 2, interval=0, source='rain', partitions=2)


def test_ocean_forcing_and_sparse_mouth_rows(tmp_path):
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
    p = marine_product(5001)
    local = np.zeros((2, 5001)); local[p[1]['ocean_mask']] = 4
    r = PartitionRouter(tmp_path / 'ocean.db', p, local, 1, interval=0, source='rain')
    r.run()
    assert r.budget()['input_m3'] == 0
    assert sum(o['known_local_volume_m3'] for o in r.result()['outlets']) == 0
    assert r.db.execute('select count(*) from outlets').fetchone()[0] == 2
    r.close()
    result = advance(p, local, 1, interval=0, source='rain')
    assert sum(o['known_local_volume_m3'] for o in result['outlets']) == 0
    assert len(result['outlets']) == 2
    scalar = advance(p, 2., 1, interval=0, source='rain')
    assert scalar['local_input_m3'] == 4
    assert sum(o['known_local_volume_m3'] for o in scalar['outlets']) == 4


def test_sparse_ocean_active_state_and_distinct_mouths(tmp_path):
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
    n = 100_000
    shape = (2, n // 2)
    marine = np.ones(shape, bool)
    marine.flat[[0, n - 1]] = False
    receiver = np.full(shape, -1, np.int32)
    receiver.flat[[0, n - 1]] = n // 2 - 1
    rank = np.zeros(shape, np.int32)
    rank.flat[[0, n - 1]] = 1
    arrays = {'bed_m': np.zeros(shape, np.float32), 'valid_mask': np.ones(shape, bool),
              'ocean_mask': marine, 'basin_id': np.zeros(shape, np.uint64),
              'receiver': receiver, 'rank': rank, 'terminal_kind': np.ones(shape, np.uint8),
              'watershed_id': np.ones(shape, np.uint64), 'total_water_unknown': np.ones(shape, bool)}
    product = ({'identity': 'sparse', 'pools': []}, arrays)
    expected = None
    for partitions in (1, 2, 4):
        path = tmp_path / f'sparse-{partitions}.db'
        router = PartitionRouter(path, product, 3., 1, interval=0, source='rain', partitions=partitions, trace=True)
        assert len(router.native_to_active) == n and router.native_to_active.nbytes == 4*n
        assert len(router.active_to_native) == len(router.order) == len(router.owners) == len(router.labels) == len(router.local_index) == 2
        assert sum(len(x) for x in router.flow) == sum(len(x) for x in router.members) == 2
        router.run()
        result = router.result()
        assert [(x['index'], x['receiver_index'], x['known_local_volume_m3']) for x in result['outlets']] == [(0, n//2-1, 3.), (n-1, n//2-1, 3.)]
        assert all(x['total_water_unknown'] for x in result['outlets'])
        assert router.db.execute('select count(*) from nodes').fetchone()[0] == 2
        assert router.db.execute('select count(*) from trace').fetchone()[0] == 2
        assert router.db.execute('select count(*) from outlets').fetchone()[0] == 2
        if expected is None:
            expected = result['outlets']
        assert result['outlets'] == expected
        router.close()


def test_old_journal_mapping_is_rejected(tmp_path):
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
    path = tmp_path / 'old.db'
    router = PartitionRouter(path, product(), 0., 1, interval=0, source='rain')
    config = dict(router.config)
    del config['journal_schema']
    with router.db:
        router.db.execute("UPDATE metadata SET value=? WHERE key='config'", (json.dumps(config),))
    router.close()
    with pytest.raises(ValueError, match='unsupported journal schema'):
        PartitionRouter(path, product(), 0., 1, interval=0, source='rain')
