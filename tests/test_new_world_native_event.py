import json
import numpy as np
from terrain_pipeline.new_world_native_event import run, read_product


def test_native_event_saved_resume_and_pool_display(tmp_path):
    terrain = tmp_path / 'terrain'
    route = tmp_path / 'route'
    derived = route / 'derived'
    routing = route / 'routing'
    for path in (terrain, derived, routing): path.mkdir(parents=True)
    (terrain / 'manifest.json').write_text(json.dumps({'identity': 'test'}))
    (route / 'derived.json').write_text(json.dumps({'cell_area_m2': 900}))
    def save(root, name, array): np.save(root / (name + '.npy'), np.asarray(array))
    save(terrain, 'bed_m', [[0., 0., 1., -1.]])
    save(terrain, 'ocean_mask', np.array([[0, 0, 0, 1]], dtype=bool))
    save(terrain, 'unknown_mask', np.array([[0, 0, 0, 0]], dtype=bool))
    save(terrain, 'valid_mask', np.array([[1, 1, 1, 1]], dtype=bool))
    climate = np.zeros((5,1,4)); climate[2] = 1000
    save(terrain, 'climate_base', climate)
    for name, a in {'pool_index': [-1,0,0,-1], 'pool_anchor': [1], 'pool_capacity_m3': [100], 'pool_spill_m': [2.], 'mouth_source': [0], 'mouth_ocean_receiver': [3], 'total_water_unknown': [0,0,0,0], 'pool_id': [42]}.items(): save(derived, name, a)
    save(routing, 'order', [3,0,1,2]); save(routing, 'receiver', [3,0,1,-1])
    out = tmp_path / 'event'
    record = run(terrain=terrain, routing=route, output=out, source_identity='test')
    product = read_product(out)
    assert record['pool_count'] == 1
    assert product.query(0, 1, 1)['pool']['id'] == 42
    assert not product.query(0, 2, 1)['channel']
    assert abs(record['budgets'][0]['residual_m3']) < 1e-8
    assert np.load(out / 'mouth_world_xz_m.npy').tolist() == [[-61440., -61440.]]
    assert np.load(out / 'pool_storage_m3.npy')[1,0] > 0



def test_corrected_v3_reader_binding_and_interval_selection(tmp_path):
    import pytest
    terrain = tmp_path / 'terrain'; derived = tmp_path / 'route' / 'derived'; base = tmp_path / 'base'; corrected = tmp_path / 'corrected'; low = tmp_path / 'low'
    for path in (terrain, derived, base, corrected, low): path.mkdir(parents=True)
    (terrain/'manifest.json').write_text(json.dumps({'identity':'source'}))
    grid=dict(source_identity='source',shape_zx=[1,2],spacing_m=30,cell_area_m2=900,origin_center_m=[-61440,-61440],pool_count=1,mouth_count=1,source_paths=dict(terrain=str(terrain),routing=str(derived.parent)))
    (base/'manifest.json').write_text(json.dumps(dict(grid,schema='native-event-v1')))
    (corrected/'manifest.json').write_text(json.dumps(dict(grid,schema='native-event-v3',base_event=str(base))))
    (low/'manifest.json').write_text(json.dumps(dict(grid,schema='native-lowland-v1')))
    def save(path,name,value): np.save(path/(name+'.npy'),np.asarray(value))
    for name,value in {'time_seconds':[0,1,2], 'mouth_unknown':[True], 'mouth_world_xz_m':[[0.,0.]], 'mouth_ocean_world_xz_m':[[30.,0.]], 'local_contribution_m3':[1.,2.], 'channel_mask':[True,False], 'capture_index':[0,-1]}.items():save(base,name,value)
    for name,value in {'node_water_m3':[[1.,2.],[3.,4.]], 'mouth_water_m3':[[2.],[4.]], 'pool_storage_m3':[[0.],[1.],[2.]], 'pool_level_m':[[np.nan],[1.],[2.]]}.items(): save(base,name,value)
    for name,value in {'node_water_m3':[[10.,20.],[30.,40.]], 'mouth_water_m3':[[20.],[40.]], 'pool_storage_m3':[[0.],[11.],[22.]], 'pool_level_m':[[np.nan],[1.5],[2.5]], 'pool_capacity_m3':[30.]}.items(): save(corrected,name,value)
    for name,value in {'pool_index':[0,-1], 'pool_id':[42], 'total_water_unknown':[False,True], 'mouth_source':[1], 'mouth_id':[99]}.items():save(derived,name,value)
    save(low,'channel_mask',[[True,False]]);save(low,'capture_index',[[0,-1]])
    legacy=read_product(base); assert legacy.query(0,0,0)['channel'] and not legacy.query(0,0,0)['channel_applies_to_interval']
    product=read_product(corrected,lowland=low)
    assert product.query(0,0,1)['known_local_volume_m3']==30.
    assert product.query(0,0,1)['pool']==dict(id=42,storage_m3=22.,level_m=2.5)
    assert product.query(0,1,1)['total_water_unknown']
    assert product.arrays['mouth_world_xz_m'][0,0]==0.
    assert read_product(corrected).query(0,0,1)['channel'] is None
    (low/'manifest.json').write_text(json.dumps(dict(grid,schema='native-lowland-v1',source_identity='wrong')))
    with pytest.raises(ValueError,match='identity or grid mismatch'):read_product(corrected,lowland=low)
    (base / 'manifest.json').unlink()
    with pytest.raises(ValueError,match='manifest'):read_product(corrected)

