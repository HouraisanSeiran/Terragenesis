import numpy as np
import pytest
from terrain_pipeline import td_source as terrain
from terrain_pipeline import new_world_stage1 as stage
from terrain_pipeline import new_world_native_water as water


def test_native_water_product_and_continuation(tmp_path, monkeypatch):
    shape = (12, 13)
    raw = np.full(shape, 5, np.float32)
    raw[0, :] = -1
    raw[6, 6] = -2
    source = {'raw_td': raw, 'td_climate': np.zeros((5, *shape), np.float32)}
    parent = {'coastal': True, 'origin_native_xz': [-10, 20], 'bed_origin_native_xz': [-10, 20],
              'anchor_bed_zx': [0, 0], 'source_shape_zx': list(shape), 'world_seed': 20261020,
              'spacing_m': 30, 'sea_m': 0, 'plate_identity': 'b'*64}
    upstream = tmp_path / 'parent'
    upstream.mkdir()
    def read_parent(path, expected_identity):
        if expected_identity != 'a'*64:
            raise ValueError('bad parent')
        return parent, source
    monkeypatch.setattr(terrain.plate_td_product, "read_plate_source", read_parent)
    tm, _ = terrain.prepare_world_terrain(upstream, tmp_path / 'terrain', expected_source_identity='a'*64)
    sm, _ = stage.prepare(tmp_path / 'terrain', tmp_path / 'planner', expected_terrain_identity=tm['identity'], block_size=5)
    common = dict(expected_terrain_identity=tm['identity'], expected_planner_identity=sm['identity'])
    first, result = water.prepare(tmp_path / 'planner', tmp_path / 'water', **common, source='rain event', duration_s=3600, runoff_depth_m=0.01)
    cold = water.read_product(tmp_path / 'water', **common)
    assert cold[0]['identity'] == first['identity']
    cell = water.query_cell(cold, -10, 20)
    assert cell['ocean'] and cell['routed_volume_m3'] is None
    assert cell['source'] == 'rain event'
    assert water.query_window(cold, -10, 20, -9, 21) == [[cell]]
    with pytest.raises(ValueError, match='outside'):
        water.query_cell(cold, -11, 20)
    assert result['budget']['complete']
    assert result['budget']['input_m3'] == pytest.approx(143 * 9)
    assert any(x['storage_m3'] > 0 for x in result['lakes'])
    assert all(x['known_local_volume_m3'] > 0 for x in result['outlets'] if x['kind'] == 'marine')
    _, second = water.prepare(tmp_path / 'planner', tmp_path / 'water2', **common, source='rain event', duration_s=3600, runoff_depth_m=10, previous=tmp_path / 'water')
    assert second['initial_state'] == result['state']
    assert any(x['outflow_m3'] > 0 for x in second['lakes'])
    with pytest.raises(ValueError, match='identity'):
        water.read_product(tmp_path / 'water', expected_terrain_identity=tm['identity'], expected_planner_identity='f'*64)
    with (tmp_path / 'water' / 'result.json').open('a') as f:
        f.write(' ')
    with pytest.raises(ValueError, match='hash'):
        water.read_product(tmp_path / 'water', **common)



@pytest.fixture
def native_event(tmp_path, monkeypatch):
    shape = (12, 13)
    raw = np.full(shape, 5, np.float32)
    raw[0, :] = -1
    raw[6, 5:8] = -2
    source = {'raw_td': raw, 'td_climate': np.zeros((5, *shape), np.float32)}
    parent = {'coastal': True, 'origin_native_xz': [-10, 20], 'bed_origin_native_xz': [-10, 20],
              'anchor_bed_zx': [0, 0], 'source_shape_zx': list(shape), 'world_seed': 20261020,
              'spacing_m': 30, 'sea_m': 0, 'plate_identity': 'b'*64}
    upstream = tmp_path / 'parent'
    upstream.mkdir()
    monkeypatch.setattr(terrain.plate_td_product, "read_plate_source", lambda path, expected_identity: (parent, source))
    tm, _ = terrain.prepare_world_terrain(upstream, tmp_path / 'terrain', expected_source_identity='a'*64)
    sm, arrays = stage.prepare(tmp_path / 'terrain', tmp_path / 'planner', expected_terrain_identity=tm['identity'], block_size=5)
    common = dict(expected_terrain_identity=tm['identity'], expected_planner_identity=sm['identity'])
    manifest, result = water.prepare(tmp_path / 'planner', tmp_path / 'event', **common,
                                     source='rain', duration_s=60, runoff_depth_m=0.1, partitions=2)
    return tmp_path / 'event', common, manifest, result, sm, arrays


def test_native_geometry_and_readonly_queries(native_event):
    path, common, manifest, result, planner, arrays = native_event
    cold = water.read_product(path, **common, expected_water_identity=manifest['identity'])
    mouths = [row for row in result['outlets'] if row['kind'] == 'marine']
    assert len({row['index'] for row in mouths}) == len(mouths)
    assert len({row['receiver_index'] for row in mouths}) < len(mouths)
    assert any(row['total_water_unknown'] for row in result['outlets'])
    assert all('total_q_m3_s' not in row for row in result['outlets'])
    assert result['lakes']
    labels = arrays['derived/pool_index'].reshape(planner['shape_zx'])
    assert any(np.any(labels[:, :6] == i) and np.any(labels[:, 6:] == i) for i in range(len(result['lakes'])))
    for mouth in mouths:
        cell = water.query_cell(cold, *mouth['source_native_xz'])
        assert cell['routed_volume_m3'] == pytest.approx(mouth['known_local_volume_m3'])
        assert water.query_mouth(cold, mouth['mouth_id']) == mouth
    for coords in [(True, 20), (-11, 20), (-10, 32)]:
        with pytest.raises(ValueError):
            water.query_cell(cold, *coords)
    with pytest.raises(ValueError):
        water.query_window(cold, -10, 20, 4, 21)


@pytest.mark.parametrize('mutation', ['trace', 'mouth', 'source', 'time', 'q', 'mask', 'budget', 'lake'])
def test_rehashed_corruption_rejected(native_event, mutation):
    import json
    path, common, manifest, result, _, _ = native_event
    if mutation == 'trace':
        trace = np.load(path / 'routed_volume_m3.npy', mmap_mode='r+')
        index = np.flatnonzero(np.isfinite(trace))[0]
        trace.flat[index] += 1
        trace.flush()
        del trace
    elif mutation in ('source', 'time'):
        manifest['source' if mutation == 'source' else 'duration_s'] = 'forged' if mutation == 'source' else 120
    else:
        mouth = next(row for row in result['outlets'] if row['kind'] == 'marine')
        if mutation == 'mouth':
            mouth['target_native_xz'][0] += 1
        elif mutation == 'q':
            mouth['known_local_q_m3_s'] += 1
        elif mutation == 'mask':
            mouth['total_water_unknown'] = not mouth['total_water_unknown']
        elif mutation == 'budget':
            result['budget']['residual_m3'] += 1
        else:
            result['lakes'][0]['wet_area_m2'] += 900
        (path / 'result.json').write_text(json.dumps(result), encoding='utf8')
    manifest['files'] = {name: water._hash(path / name) for name in manifest['files']}
    manifest['identity'] = water._identity(manifest)
    (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError):
        water.read_product(path, **common)
    with pytest.raises(ValueError, match='identity'):
        water.read_product(path, **common, expected_water_identity='0' * 64)


def test_queries_reuse_authenticated_context(native_event, monkeypatch):
    path, common, manifest, _, _, _ = native_event
    original = stage.read_product
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(stage, 'read_product', counted)
    product = water.read_product(path, **common, expected_water_identity=manifest['identity'])
    for _ in range(3):
        water.query_cell(product, -10, 20)
        water.query_window(product, -10, 20, -8, 22)
    assert len(calls) == 1
    assert all(not a.flags.writeable for a in product.context[1].values() if isinstance(a, np.ndarray))
    assert not product.context[2].flags.writeable


def test_cli_checkpoints_fresh_process(native_event, tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    _, common, _, _, _, _ = native_event
    root = Path(__file__).resolve().parents[1]
    hook = tmp_path / 'hook'
    hook.mkdir()
    # The controlled upstream reader is installed only in the subprocess test environment;
    # the terrain and planner readers still authenticate their persisted products normally.
    (hook / 'sitecustomize.py').write_text('''\
import numpy as np
from terrain_pipeline import plate_td_product
shape = (12, 13)
raw = np.full(shape, 5, np.float32)
raw[0, :] = -1
raw[6, 5:8] = -2
parent = {'coastal': True, 'origin_native_xz': [-10, 20], 'bed_origin_native_xz': [-10, 20], 'anchor_bed_zx': [0, 0], 'source_shape_zx': list(shape), 'world_seed': 20261020, 'spacing_m': 30, 'sea_m': 0, 'plate_identity': 'b'*64}
def read(path, expected_identity):
    if expected_identity != 'a'*64:
        raise ValueError('bad parent identity')
    return parent, {'raw_td': raw, 'td_climate': np.zeros((5, *shape), np.float32)}
plate_td_product.read_product = read
''', encoding='utf8')
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join((str(hook), str(root)))
    def run(output, *extra):
        cmd = [sys.executable, str(root / 'tools/prepare_new_world_native_water.py'), str(tmp_path / 'planner'), str(output),
               '--expected-terrain-identity', common['expected_terrain_identity'], '--expected-planner-identity', common['expected_planner_identity'],
               '--source', 'rain', '--duration-s', '60', '--runoff-depth-m', '0.1', '--partitions', '2', '--generate', *extra]
        return subprocess.run(cmd, env=env, cwd=root, text=True, capture_output=True)
    continuous = tmp_path / 'continuous'
    assert run(continuous).returncode == 0
    for boundary in ('send', 'receive'):
        out = tmp_path / boundary
        stopped = run(out, '--stop-after', boundary)
        assert stopped.returncode == 0, stopped.stderr
        assert json.loads(stopped.stdout)['status'] == 'pending'
        pending = out.with_name(out.name + '.pending')
        assert (pending / 'journal.sqlite').exists() and not out.exists()
        for changed in (('--source', 'other'), ('--duration-s', '61'), ('--previous', str(tmp_path / 'event'))):
            assert run(out, '--resume', *changed).returncode != 0
        finished = run(out, '--resume')
        assert finished.returncode == 0, finished.stderr
        assert json.loads((out / 'result.json').read_text()) == json.loads((continuous / 'result.json').read_text())
        np.testing.assert_equal(np.load(out / 'routed_volume_m3.npy'), np.load(continuous / 'routed_volume_m3.npy'))
        before = (out / 'manifest.json').read_bytes()
        assert run(out).returncode != 0
        assert run(out, '--resume').returncode == 0
        assert (out / 'manifest.json').read_bytes() == before
    corrupt = tmp_path / 'corrupt'
    assert run(corrupt, '--stop-after', 'send').returncode == 0
    (corrupt.with_name(corrupt.name + '.pending') / 'journal.sqlite').write_bytes(b'broken')
    assert run(corrupt, '--resume').returncode != 0
    assert not corrupt.exists()


def test_resource_estimate_uses_verified_active_count():
    manifest = {'shape_zx': [2, 50_000], 'counts': {'pools': 1}}
    ocean = np.ones((2, 50_000), dtype=bool)
    ocean.flat[[0, -1]] = False
    estimate = water.resource_estimate(manifest, {'valid_mask': np.ones_like(ocean), 'ocean_mask': ocean})
    assert estimate['active_nodes'] == 2
    assert estimate['active_working_bytes'] == 400
    assert estimate['mapped_and_native_bytes'] == 8_000_000
    assert water.resource_estimate(manifest)['active_nodes'] == 100_000
