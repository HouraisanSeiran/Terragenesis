import json
import numpy as np
import pytest
from terrain_pipeline import td_source as terrain
from terrain_pipeline import new_world_stage1 as stage
from terrain_pipeline import new_world_native_water as water
from terrain_pipeline import new_world_river_scene as scene


@pytest.fixture
def event(tmp_path, monkeypatch):
    shape = (12, 13)
    raw = np.full(shape, 5, np.float32)
    raw[0, :] = -1
    raw[6, 5:8] = -2
    parent = {'coastal': True, 'origin_native_xz': [-10, 20], 'bed_origin_native_xz': [-10, 20],
              'anchor_bed_zx': [0, 0], 'source_shape_zx': list(shape), 'world_seed': 20261020,
              'spacing_m': 30, 'sea_m': 0, 'plate_identity': 'b'*64}
    source = {'raw_td': raw, 'td_climate': np.zeros((5, *shape), np.float32)}
    upstream = tmp_path / 'parent'; upstream.mkdir()
    monkeypatch.setattr(terrain.plate_td_product, "read_plate_source", lambda path, expected_identity: (parent, source))
    tm, _ = terrain.prepare_world_terrain(upstream, tmp_path / 'terrain', expected_source_identity='a'*64)
    sm, arrays = stage.prepare(tmp_path / 'terrain', tmp_path / 'planner', expected_terrain_identity=tm['identity'], block_size=5)
    common = dict(expected_terrain_identity=tm['identity'], expected_planner_identity=sm['identity'])
    wm, result = water.prepare(tmp_path / 'planner', tmp_path / 'event', **common, source='rain', duration_s=60, runoff_depth_m=.1)
    common['expected_water_identity'] = wm['identity']
    return tmp_path / 'event', common, result, arrays


def test_scene_authentication_and_mouth_selection(event, tmp_path):
    path, common, result, parent = event
    mouths = [r for r in result['outlets'] if r['kind'] == 'marine']
    assert len(mouths) >= 2
    args = dict(common, mouth_id=mouths[0]['mouth_id'], interval=0, origin_native_xz=[-10, 20], shape_zx=[12, 13])
    m, a = scene.prepare(path, tmp_path / 'scene', **args)
    read, b = scene.read_product(tmp_path / 'scene', expected_identity=m['identity'], **common)
    assert read['mouth_source_index'] == mouths[0]['index']
    assert not read['physical_solve_ready'] and read['mouth_total_water_unknown']
    np.testing.assert_array_equal(a['bed_m'], parent['bed_m'])
    np.testing.assert_array_equal(a['ocean_mask'], parent['ocean_mask'])
    assert a['closed_below_sea_mask'][6, 6] and not a['ocean_mask'][6, 6]
    assert not b['bed_m'].flags.writeable
    m2, _ = scene.extract(path, **dict(args, mouth_id=mouths[1]['mouth_id']))
    assert m2['mouth_source_index'] != m['mouth_source_index']
    with pytest.raises(FileExistsError):
        scene.prepare(path, tmp_path / 'scene', **args)
    with pytest.raises(ValueError):
        scene.extract(path, **dict(args, interval=1))
    with pytest.raises(ValueError):
        scene.extract(path, **dict(args, expected_water_identity='f'*64))
    with pytest.raises(ValueError):
        scene.extract(path, **dict(args, origin_native_xz=[-11, 20]))
    manifest = tmp_path / 'scene' / 'manifest.json'
    forged = json.loads(manifest.read_text(encoding='utf8'))
    forged['water_path'] = str(tmp_path / 'forged')
    forged['identity'] = scene._identity(forged)
    manifest.write_text(json.dumps(forged), encoding='utf8')
    with pytest.raises((ValueError, OSError)):
        scene.read_product(tmp_path / 'scene', expected_identity=forged['identity'], **common)


def test_upstream_selection_and_boundary_accounting(event):
    path, common, result, parent = event
    mouth = max((r for r in result['outlets'] if r['kind'] == 'marine'), key=lambda r: r['known_local_volume_m3'])
    args = dict(common, mouth_id=mouth['mouth_id'], interval=0, origin_native_xz=[-10, 20], shape_zx=[12, 13])
    m, a = scene.extract(path, **args)
    m2, b = scene.extract(path, **args)
    np.testing.assert_array_equal(a['parent_index'], b['parent_index'])
    assert m['boundary_contributions'] == m2['boundary_contributions']
    rec = parent['routing/receiver']; trace = water.read_product(path, **common).context[2].ravel()
    for upstream, downstream in zip(a['parent_index'][:-1], a['parent_index'][1:]):
        candidates = np.flatnonzero((rec == downstream) & np.isfinite(trace))
        assert upstream == sorted(candidates, key=lambda i: (-trace[i], i))[0]
    for edge in m['boundary_contributions']:
        assert rec[edge['source_index']] == edge['receiver_index']
        assert edge['known_volume_m3'] == trace[edge['source_index']]
    assert m['boundary_contributions']
