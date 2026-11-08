import numpy as np
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval
from terrain_pipeline.new_world_game_hydrology import levels


def test_pool_routing_restart_and_actual_level():
    # 2 and 1 enter a single depression anchored at 1; 0 is its outlet.
    order = np.array([0, 1, 2], dtype=np.int64)
    receiver = np.array([-1, 0, 1], dtype=np.int64)
    labels = np.array([-1, 0, 0], dtype=np.int64)
    anchors = np.array([1], dtype=np.int64)
    capacity = np.array([20.])
    local = np.array([0., 4., 8.])
    state = np.zeros(1)
    first, retained = route_pool_interval(local, order, receiver, labels, anchors, capacity, state)
    assert retained == 12 and first[0] == 0
    saved = state.copy()
    second, retained = route_pool_interval(local, order, receiver, labels, anchors, capacity, state)
    resumed, _ = route_pool_interval(local, order, receiver, labels, anchors, capacity, saved)
    np.testing.assert_array_equal(second, resumed)
    assert second[0] == 4 and retained == 8
    level = levels(labels, np.array([0., 0., 1.]), np.array([2.]), state, 10.)
    assert abs(level[0] - 1.5) < 1e-8


def test_saved_product_query_and_grid_namespace(tmp_path):
    import json
    import pytest
    from terrain_pipeline.new_world_game_hydrology import read_product

    def make(root, spacing):
        (root / 'derived').mkdir(parents=True)
        manifest = dict(schema='game-hydro-v1', source_identity='terrain', shape_zx=[1, 2],
                        spacing_m=spacing, cell_area_m2=spacing ** 2, origin_center_m=[0, 0],
                        pool_count=1, mouth_count=1)
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
        arrays = {'time_seconds': [0, 10], 'node_water_m3': [[3., 4.]],
                  'mouth_water_m3': [[4.]], 'mouth_unknown': [True],
                  'pool_storage_m3': [[0.], [5.]], 'pool_level_m': [[np.nan], [2.]],
                  'derived/pool_index': [0, -1], 'derived/pool_id': [42],
                  'derived/mouth_id': [8], 'derived/mouth_source': [1],
                  'derived/total_water_unknown': [False, True]}
        for name, value in arrays.items():
            np.save(root / (name + '.npy'), np.asarray(value))
        return read_product(root)

    first = make(tmp_path / 'a', 90)
    second = make(tmp_path / 'b', 30)
    assert first.identity != second.identity
    with pytest.raises(ValueError, match='identity mismatch'):
        read_product(tmp_path / 'b', expected_identity=first.identity)
    assert first.query(0, 0, 0)['pool'] == dict(id=42, storage_m3=5., level_m=2.)
    assert first.query(0, 1, 0)['total_water_unknown']
    with pytest.raises(ValueError):
        first.query(1, 0, 0)
    manifest_path = tmp_path / 'a' / 'manifest.json'
    malformed = json.loads(manifest_path.read_text(encoding='utf8'))
    malformed['mouth_count'] = 2
    manifest_path.write_text(json.dumps(malformed), encoding='utf8')
    with pytest.raises(ValueError):
        read_product(tmp_path / 'a')
