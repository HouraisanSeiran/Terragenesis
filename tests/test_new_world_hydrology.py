import numpy as np
import pytest

from terrain_pipeline import new_world_hydrology as hydrology


def test_finite_product(monkeypatch, tmp_path):
    bed = np.full((7, 7), 10, dtype=np.float32)
    bed[3, 3] = -4
    bed[0, 3] = -2
    ocean = np.zeros_like(bed, dtype=bool)
    ocean[0, 3] = True
    closed = np.zeros_like(ocean)
    closed[3, 3] = True
    source = {'bed_m': bed, 'raw_td_m': bed.copy(), 'valid_mask': np.ones_like(ocean),
              'ocean_mask': ocean, 'closed_below_sea_mask': closed,
              'unknown_mask': np.zeros_like(ocean), 'climate_base': np.ones((5, 7, 7), np.float32)}
    terrain = {'identity': 'a' * 64, 'origin_native_xz': [100, 200], 'world_seed': 20261020, 'shape_zx': [7, 7], 'spacing_m': 30}
    def read(path, expected_identity=None):
        if expected_identity != terrain['identity']:
            raise ValueError('identity mismatch')
        return terrain, source
    monkeypatch.setattr(hydrology.new_world_terrain, 'read_product', read)
    path = tmp_path / 'product'
    product = hydrology.prepare('source', path, expected_terrain_identity='a' * 64)
    manifest, arrays = hydrology.read_product(path, expected_terrain_identity='a' * 64)
    assert np.array_equal(arrays['bed_m'], bed)
    assert arrays['basin_id'][3, 3] != 0
    assert not arrays['ocean_mask'][3, 3]
    assert manifest['pools'][0]['capacity_m3'] > 0
    assert arrays['boundary_unknown'][0, 0]
    assert arrays['total_water_unknown'].all()
    assert np.all(arrays['known_local_area_m2'] >= 900)
    first = hydrology.query_window(product, (101, 201), (4, 4))
    second = hydrology.query_window(product, (102, 202), (3, 3))
    assert np.array_equal(first['watershed_id'][1:, 1:], second['watershed_id'])
    assert np.array_equal(first['ocean_mask'][1:, 1:], second['ocean_mask'])
    assert hydrology.query_mouth(product, 103, 200)['ocean']
    assert np.array_equal(hydrology.sample_climate(product, 103, 203), np.ones(5))
    with pytest.raises(ValueError):
        hydrology.read_product(path, expected_terrain_identity='b' * 64)
    with pytest.raises(FileExistsError):
        hydrology.prepare('source', path, expected_terrain_identity='a' * 64)
    with pytest.raises(ValueError):
        hydrology.prepare('source', tmp_path / 'wrong', expected_terrain_identity='b' * 64)


@pytest.fixture
def finite(monkeypatch, tmp_path):
    bed = np.full((7, 7), 10, dtype=np.float32)
    bed[3, 3] = -4
    bed[0, 3] = -2
    ocean = np.zeros_like(bed, dtype=bool)
    ocean[0, 3] = True
    closed = np.zeros_like(ocean)
    closed[3, 3] = True
    source = {'bed_m': bed, 'raw_td_m': bed.copy(), 'valid_mask': np.ones_like(ocean),
              'ocean_mask': ocean, 'closed_below_sea_mask': closed,
              'unknown_mask': np.zeros_like(ocean), 'climate_base': np.ones((5, 7, 7), np.float32)}
    terrain = {'identity': 'a' * 64, 'origin_native_xz': [100, 200], 'world_seed': 20261020,
               'shape_zx': [7, 7], 'spacing_m': 30}
    def read(path, expected_identity=None):
        if expected_identity != terrain['identity']:
            raise ValueError('source identity mismatch')
        return terrain, source
    monkeypatch.setattr(hydrology.new_world_terrain, 'read_product', read)
    return tmp_path, source, hydrology.prepare('source', tmp_path / 'one', expected_terrain_identity='a' * 64)


def test_event_fills_before_overflow_and_balances(finite):
    _, _, product = finite
    manifest, arrays = product
    pool = manifest['pools'][0]
    anchor = pool['anchor_index']
    depth = np.zeros(arrays['bed_m'].shape)
    depth.flat[anchor] = pool['capacity_m3'] / 900 / 2
    small = hydrology.route_event(product, depth, 3600, input_source='declared test runoff')
    assert small['stored_m3'] == pytest.approx(pool['capacity_m3'] / 2)
    assert small['outflow_m3'] == pytest.approx(0)
    depth.flat[anchor] *= 4
    large = hydrology.route_event(product, depth, 3600, input_source='declared test runoff')
    assert large['stored_m3'] == pytest.approx(pool['capacity_m3'])
    assert large['outflow_m3'] == pytest.approx(pool['capacity_m3'])
    assert large['residual_m3'] == pytest.approx(0)
    assert large['external_water'] == 'unknown'


def test_identity_independent_of_output_and_window(finite):
    path, _, product = finite
    other = hydrology.prepare('source', path / 'two', expected_terrain_identity='a' * 64)
    assert product[0]['identity'] == other[0]['identity']
    a = hydrology.query_window(product, (100, 200), (5, 5))
    b = hydrology.query_window(product, (101, 201), (4, 4))
    for name in ('watershed_id', 'basin_id', 'ocean_mask'):
        assert np.array_equal(a[name][1:, 1:], b[name])


def test_source_and_array_tampering_rejected(finite):
    path, source, product = finite
    source['bed_m'][1, 1] += 1
    with pytest.raises(ValueError, match='terrain array mismatch'):
        hydrology.read_product(path / 'one')
    source['bed_m'][1, 1] -= 1
    import json
    file = path / 'one' / 'manifest.json'
    manifest = json.loads(file.read_text(encoding='utf-8'))
    manifest['files']['receiver'] = '0' * 64
    manifest['identity'] = hydrology._identity(manifest)
    file.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        hydrology.read_product(path / 'one')
    with pytest.raises(ValueError):
        hydrology.read_product(path / 'one', expected_terrain_identity='b' * 64)

