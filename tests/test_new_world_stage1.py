import numpy as np
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.new_world_stage1 import build_native_graph, resource_estimate


def test_block_graph_matches_whole_reference_with_negative_origin(tmp_path):
    shape = (35, 39)
    origin = (-42, -19)
    reference = build_mesh(shape, origin_native_xz=origin)
    result = build_native_graph(shape, origin, tmp_path / 'graph', block_size=10)
    for name in ('node_x_m', 'node_z_m', 'indptr', 'indices'):
        np.testing.assert_array_equal(result[name], getattr(reference, name))
    assert all(isinstance(a, np.memmap) for a in result.values())


def test_resource_budget_is_explicit():
    from terrain_pipeline.new_world_stage1 import product_resource_estimate
    estimate = resource_estimate((4096, 4096))
    assert estimate['disk_bytes'] > 4096**2 * 80
    assert estimate['source_worker_reserve_bytes'] == 4_900_000_000
    product = product_resource_estimate((4096, 4096))
    assert product['ram_bytes'] == estimate['ram_bytes'] + 420 * 4096**2


def test_mapped_route_matches_reference(tmp_path):
    from terrain_pipeline.drainage import route_graph as route_graph
    from terrain_pipeline.new_world_stage1 import route_native_graph
    shape = (17, 19)
    rng = np.random.default_rng(29)
    bed = rng.integers(-5, 20, size=shape).astype(float)
    original = bed.copy()
    outlets = np.zeros(shape, bool)
    outlets[0, :] = True
    outlets[-1, :] = True
    outlets[:, 0] = True
    outlets[:, -1] = True
    graph = build_native_graph(shape, (-17, -9), tmp_path / 'graph', block_size=7)
    result = route_native_graph(bed, outlets, graph, tmp_path / 'route')
    reference = route_graph(bed, outlets, build_mesh(shape, origin_native_xz=(-17, -9)))
    for name in ('filled', 'order', 'rank', 'receiver'):
        np.testing.assert_array_equal(result[name], getattr(reference, name).ravel())
    np.testing.assert_array_equal(bed, original)


def test_invalid_cells_are_never_receivers_and_disconnected_components_fail(tmp_path):
    import pytest
    from terrain_pipeline.new_world_stage1 import route_native_graph

    shape = (9, 9)
    graph = build_native_graph(shape, (0, 0), tmp_path / 'graph', block_size=4)
    bed = np.ones(shape)
    valid = np.ones(shape, dtype=bool)
    valid[4, 4] = False
    bed[4, 4] = np.nan
    outlets = np.zeros(shape, dtype=bool)
    outlets[0, :] = True
    result = route_native_graph(bed, outlets, graph, tmp_path / 'route', valid_mask=valid)
    receiver = result['receiver']
    assert receiver[40] == -1 and result['rank'][40] == -1
    assert not np.any(receiver == 40)
    assert np.all(result['rank'][receiver[receiver >= 0]] < result['rank'][receiver >= 0])

    isolated = np.zeros(shape, dtype=bool)
    isolated[0, 0] = isolated[-1, -1] = True
    outlets[:] = False
    outlets[0, 0] = True
    with pytest.raises(ValueError, match='component without an explicit outlet'):
        route_native_graph(np.ones(shape), outlets, graph, tmp_path / 'disconnected', valid_mask=isolated)


def test_derived_pools_terminals_and_invalid_cells(tmp_path):
    from terrain_pipeline.new_world_stage1 import route_native_graph, derive_native_hydrology
    shape = (9, 9)
    origin = (-23, -41)
    graph = build_native_graph(shape, origin, tmp_path / 'graph', block_size=4)
    bed = np.full(shape, 5.)
    bed[4, 4] = -2.
    bed[0, :] = 0.
    original = bed.copy()
    valid = np.ones(shape, bool)
    valid[7, 7] = False
    ocean = np.zeros(shape, bool)
    ocean[0, :] = True
    unknown = np.zeros(shape, bool)
    outlets = ocean.copy()
    outlets[-1, :] = True
    outlets[:, 0] = True
    outlets[:, -1] = True
    route = route_native_graph(bed, outlets, graph, tmp_path / 'route', valid_mask=valid)
    result = derive_native_hydrology(graph, route, bed, ocean, unknown, valid, origin, 'source-A', tmp_path / 'derived')
    labels = result['arrays']['pool_index']
    label = labels[4 * shape[1] + 4]
    assert label >= 0
    assert result['pools']['capacity_m3'][label] == 7 * 900
    assert result['pools']['spill_m'][label] == 5
    assert labels[7 * shape[1] + 7] == -1
    assert result['arrays']['terminal_index'][7 * shape[1] + 7] == -1
    assert not result['arrays']['total_water_unknown'][7 * shape[1] + 7]
    np.testing.assert_array_equal(bed, original)
    again = derive_native_hydrology(graph, route, bed, ocean, unknown, valid, origin, 'source-A', tmp_path / 'again')
    np.testing.assert_array_equal(result['pools']['id'], again['pools']['id'])
    np.testing.assert_array_equal(result['mouths']['id'], again['mouths']['id'])
    assert np.all(result['mouths']['source_native_xz'][:, 0] < 0)
    for source, target in zip(result['mouths']['source'], result['mouths']['ocean_receiver']):
        assert route['receiver'][source] == target and ocean.ravel()[target]


def test_inner_rim_ingress_and_supported_interior(tmp_path):
    from terrain_pipeline.new_world_stage1 import derive_native_hydrology
    # A small frozen graph: interior cell 6 drains to ocean 7; rim node 1 is
    # its neighbor and a sink, so ingress must be seeded at 6 directly.
    rows = cols = 5
    n = rows * cols
    adjacency = [[] for _ in range(n)]
    for a, b in [(1, 6), (6, 7), (12, 13)]:
        adjacency[a].append(b)
        adjacency[b].append(a)
    ptr = np.zeros(n + 1, np.int64)
    ptr[1:] = np.cumsum([len(x) for x in adjacency])
    graph = {'indptr': ptr, 'indices': np.array([b for row in adjacency for b in row], np.int32)}
    order = np.array([7, 1, 6, 13, 12] + [i for i in range(n) if i not in (7, 1, 6, 13, 12)], np.int64)
    rank = np.empty(n, np.int64)
    rank[order] = np.arange(n)
    receiver = np.full(n, -1, np.int64)
    receiver[6] = 7
    receiver[12] = 13
    bed = np.zeros((rows, cols))
    masks = np.zeros_like(bed, dtype=bool)
    ocean = masks.copy()
    ocean.flat[7] = True
    result = derive_native_hydrology(graph, {'order': order, 'rank': rank, 'receiver': receiver,
        'filled': bed.ravel().copy()}, bed, ocean, masks, ~masks, (-4, -8), 'identity', tmp_path / 'derived')
    water = result['arrays']['total_water_unknown']
    assert water[6] and water[7]
    assert not water[12] and not water[13]
    assert result['arrays']['terminal_type'][6] == 1
    assert result['arrays']['terminal_type'][12] == 2
    np.testing.assert_array_equal(result['mouths']['source'], [6])
    np.testing.assert_array_equal(result['mouths']['source_native_xz'], [[-3, -7]])
    np.testing.assert_array_equal(result['mouths']['ocean_native_xz'], [[-2, -7]])


def test_interior_invalid_boundary_ingress_reaches_downstream(tmp_path):
    from terrain_pipeline.new_world_stage1 import route_native_graph, derive_native_hydrology
    shape = (9, 9)
    graph = build_native_graph(shape, (0, 0), tmp_path / 'graph', block_size=4)
    bed = np.indices(shape)[0].astype(float)
    valid = np.ones(shape, bool)
    valid[4, 4] = False
    ocean = np.zeros(shape, bool)
    ocean[0, :] = True
    unknown = np.zeros(shape, bool)
    route = route_native_graph(bed, ocean, graph, tmp_path / 'route', valid_mask=valid)
    result = derive_native_hydrology(graph, route, bed, ocean, unknown, valid, (0, 0), 'source', tmp_path / 'derived')
    water = result['arrays']['total_water_unknown']
    node = int(graph['indices'][graph['indptr'][40]])
    assert water[node]
    while route['receiver'][node] >= 0:
        node = int(route['receiver'][node])
        assert water[node]


def test_multiblock_pool_reference(tmp_path):
    from terrain_pipeline.new_world_stage1 import route_native_graph, derive_native_hydrology
    from terrain_pipeline.drainage import pool_labels as pool_labels
    shape = (16, 18)
    bed = np.random.default_rng(82).integers(-3, 8, size=shape).astype(float)
    valid = np.ones(shape, bool)
    ocean = np.zeros(shape, bool)
    outlets = np.zeros(shape, bool)
    outlets[0, :] = outlets[-1, :] = True
    outlets[:, 0] = outlets[:, -1] = True
    graph = build_native_graph(shape, (-10, 7), tmp_path / 'graph', block_size=5)
    route = route_native_graph(bed, outlets, graph, tmp_path / 'route')
    result = derive_native_hydrology(graph, route, bed, ocean, ocean, valid, (-10, 7), 'reference', tmp_path / 'derived')
    labels, count = pool_labels(bed.ravel(), route['filled'], graph['indptr'], graph['indices'])
    np.testing.assert_array_equal(result['arrays']['pool_index'], labels)
    assert len(result['pools']['id']) == count
    for label in range(count):
        cells = np.flatnonzero(labels == label)
        assert result['pools']['anchor'][label] == cells[np.argmin(route['rank'][cells])]
        assert np.isclose(result['pools']['capacity_m3'][label], np.sum((route['filled'][cells] - bed.ravel()[cells]) * 900))


def test_classification_unknown_is_separate_and_excluded_from_pool(tmp_path):
    from terrain_pipeline.new_world_stage1 import route_native_graph, derive_native_hydrology
    shape = (7, 7)
    graph = build_native_graph(shape, (0, 0), tmp_path / 'graph', block_size=3)
    bed = np.full(shape, 4.)
    bed[3, 3] = -1.
    outlets = np.zeros(shape, bool)
    outlets[0, :] = True
    unknown = np.zeros(shape, bool)
    unknown[3, 3] = True
    valid = np.ones(shape, bool)
    ocean = np.zeros(shape, bool)
    route = route_native_graph(bed, outlets, graph, tmp_path / 'route')
    result = derive_native_hydrology(graph, route, bed, ocean, unknown, valid, (0, 0), 'source', tmp_path / 'derived')
    index = 3 * shape[1] + 3
    assert result['arrays']['pool_index'][index] == -1
    assert result['arrays']['terminal_type'][index] == 3
    assert result['arrays']['classification_unknown'][index]
    assert result['arrays']['total_water_unknown'][index]
    np.testing.assert_array_equal(result['arrays']['classification_unknown'], unknown.ravel())

def test_product_lifecycle_and_corruption(tmp_path, monkeypatch):
    import json
    import pytest
    from terrain_pipeline import td_source as terrain
    from terrain_pipeline import new_world_stage1 as stage
    from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
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
    (upstream / 'intact').touch()
    def read_parent(path, expected_identity):
        if expected_identity != 'a'*64 or not (upstream / 'intact').exists():
            raise ValueError('damaged parent')
        return parent, source
    monkeypatch.setattr(terrain.plate_td_product, "read_plate_source", read_parent)
    tm, _ = terrain.prepare_world_terrain(upstream, tmp_path / 'terrain', expected_source_identity='a'*64)
    out = tmp_path / 'stage'
    m, arrays = stage.prepare(tmp_path / 'terrain', out, expected_terrain_identity=tm['identity'], block_size=5)
    del arrays
    # Construct a v1 fixture with the historical N-length record arrays.
    import shutil
    legacy = tmp_path / 'legacy'
    shutil.copytree(out, legacy)
    legacy_manifest = json.loads((legacy / 'manifest.json').read_text(encoding='utf-8'))
    legacy_manifest['schema'] = 'new-world-stage1-native-v1'
    for name in ('pool_anchor', 'pool_capacity_m3', 'pool_cell_count', 'pool_spill_m',
                 'mouth_source', 'mouth_ocean_receiver', 'mouth_id'):
        path = legacy / 'derived' / (name + '.npy')
        old = np.load(path, allow_pickle=False)
        padded = np.zeros(np.prod(shape), dtype=old.dtype)
        padded[:len(old)] = old
        np.save(path, padded)
        desc = legacy_manifest['files']['derived/' + name + '.npy']
        desc.update(sha256=stage._digest(path), shape=list(padded.shape), dtype=padded.dtype.str)
    legacy_manifest['identity'] = stage._identity(legacy_manifest)
    (legacy / 'manifest.json').write_text(json.dumps(legacy_manifest), encoding='utf-8')
    old_product = stage.read_product(legacy, expected_terrain_identity=tm['identity'])
    assert old_product[0]['schema'].endswith('-v1')
    assert old_product[1]['derived/pool_anchor'].shape == (np.prod(shape),)
    del old_product
    cold = stage.read_product(out, expected_terrain_identity=tm['identity'])
    meta, window = stage.query_window(cold, (-8, 23), (4, 5))
    assert meta['shape_zx'] == [4, 5]
    assert np.shares_memory(window['bed_m'], cold[1]['bed_m'])
    assert not window['routing/receiver'].flags.writeable
    reference = build_mesh(shape, origin_native_xz=(-10, 20))
    np.testing.assert_array_equal(cold[1]['graph/indices'], reference.indices)
    adapter = stage.lifecycle_adapter(cold)
    router = PartitionRouter(tmp_path / 'journal.sqlite', adapter, np.ones(shape), 1., interval=0, source='fixture')
    assert router.run()['complete']
    router.close()
    with pytest.raises(FileExistsError):
        stage.prepare(tmp_path / 'terrain', out, expected_terrain_identity=tm['identity'])
    with pytest.raises(ValueError, match='identity'):
        stage.read_product(out, expected_terrain_identity='f'*64)
    file = out / 'routing/receiver.npy'
    with file.open('r+b') as f:
        f.seek(-1, 2)
        b = f.read(1)
        f.seek(-1, 2)
        f.write(bytes([b[0] ^ 1]))
    with pytest.raises(ValueError, match='hash'):
        stage.read_product(out, expected_terrain_identity=tm['identity'])
    (upstream / 'intact').unlink()
    with pytest.raises(ValueError, match='damaged'):
        stage.prepare(tmp_path / 'terrain', tmp_path / 'failed', expected_terrain_identity=tm['identity'])
    assert not (tmp_path / 'failed').exists()


def test_route_validation_checks_later_chunks_before_creating_output(tmp_path):
    import pytest
    from terrain_pipeline.new_world_stage1 import route_native_graph
    shape = (257, 256)
    bed = np.ones(shape)
    valid = np.ones(shape, dtype=bool)
    outlets = np.zeros(shape, dtype=bool)
    outlets[0, 0] = True
    bed.flat[65536] = np.nan
    with pytest.raises(ValueError, match='finite valid bed'):
        route_native_graph(bed, outlets, {}, tmp_path / 'route', valid_mask=valid)
    assert not (tmp_path / 'route').exists()


def test_compact_tables_empty_and_many_pools(tmp_path):
    from terrain_pipeline.new_world_stage1 import route_native_graph, derive_native_hydrology

    shape = (21, 21)
    origin = (-100, -200)
    graph = build_native_graph(shape, origin, tmp_path / 'graph', block_size=7)
    valid = np.ones(shape, bool)
    unknown = np.zeros(shape, bool)
    for marine in (True, False):
        bed = np.full(shape, 5.)
        ocean = np.full(shape, marine, bool)
        if not marine:
            bed[2:-2:3, 2:-2:3] = -2.
            ocean[0, :] = True
        original = bed.copy()
        outlets = np.zeros(shape, bool)
        outlets[0, :] = outlets[-1, :] = True
        outlets[:, 0] = outlets[:, -1] = True
        route = route_native_graph(bed, outlets, graph, tmp_path / ('route' + str(marine)))
        root = tmp_path / ('derived' + str(marine))
        result = derive_native_hydrology(graph, route, bed, ocean, unknown, valid, origin, 'compact', root)
        pools, mouths = len(result['pools']['id']), len(result['mouths']['id'])
        for name in ('pool_anchor', 'pool_capacity_m3', 'pool_cell_count', 'pool_spill_m'):
            assert np.load(root / (name + '.npy'), mmap_mode='r').shape == (pools,)
        for name in ('mouth_source', 'mouth_ocean_receiver', 'mouth_id'):
            assert np.load(root / (name + '.npy'), mmap_mode='r').shape == (mouths,)
        for name in ('mouth_source_native_xz', 'mouth_ocean_native_xz'):
            assert np.load(root / (name + '.npy'), mmap_mode='r').shape == (mouths, 2)
        if marine:
            assert pools == mouths == 0
        else:
            assert pools == 36
            np.testing.assert_array_equal(result['pools']['cell_count'], np.ones(pools))
            np.testing.assert_array_equal(result['pools']['capacity_m3'], np.full(pools, 6300.))
            assert np.all(result['mouths']['source_native_xz'] < 0)
        np.testing.assert_array_equal(bed, original)
        # NPY headers have identical sizes here, so the difference is exact.
        actual = sum((root / (name + '.npy')).stat().st_size for name in
                     ('pool_anchor', 'pool_capacity_m3', 'pool_cell_count', 'pool_spill_m',
                      'mouth_source', 'mouth_ocean_receiver', 'mouth_id'))
        assert actual == 7 * 128 + 32 * pools + 24 * mouths
        if marine:
            legacy_file = tmp_path / 'legacy_table.npy'
            np.save(legacy_file, np.zeros(np.prod(shape), dtype='i8'))
            assert 7 * legacy_file.stat().st_size - actual == 24696
