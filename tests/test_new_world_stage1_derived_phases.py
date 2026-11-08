import numpy as np

from terrain_pipeline.new_world_stage1 import (
    _label_pools, build_native_graph, derive_native_hydrology, route_native_graph,
)
from terrain_pipeline.new_world_stage1_derived_phases import graph_dependent_stage


def test_graph_stage_matches_reference_after_downstream_propagation(tmp_path):
    shape = (13, 15)
    n = np.prod(shape)
    graph = build_native_graph(shape, (-31, -17), tmp_path / 'graph', block_size=5)
    rng = np.random.default_rng(8)
    bed = rng.integers(0, 12, shape).astype(np.float64)
    valid = np.ones(shape, bool)
    valid[5, 5] = False
    ocean = np.zeros(shape, bool)
    ocean[0, :] = True
    unknown = np.zeros(shape, bool)
    unknown[7, 7] = True
    outlets = ocean | unknown
    outlets[-1, :] = True
    outlets[:, 0] = True
    outlets[:, -1] = True
    route = route_native_graph(bed, outlets, graph, tmp_path / 'route', valid_mask=valid)
    reference = derive_native_hydrology(graph, route, bed, ocean, unknown, valid,
                                        (-31, -17), 'fixture', tmp_path / 'reference')
    labels = np.empty(n, np.int64)
    stack = np.empty(n, np.int64)
    count = _label_pools(bed.ravel(), valid.ravel(), ocean.ravel(), unknown.ravel(),
                         route['filled'], graph['indptr'], graph['indices'], labels, stack)
    anchors = np.empty(count, np.int64)
    capacity = np.empty(count, np.float64)
    counts = np.empty(count, np.int64)
    spill = np.empty(count, np.float64)
    seeds = np.empty(n, bool)
    graph_dependent_stage(bed.ravel(), valid.ravel(), ocean.ravel(), unknown.ravel(),
                          route['filled'], route['rank'], graph['indptr'], graph['indices'],
                          *shape, labels, stack, anchors, capacity, counts, spill, seeds)
    for actual, expected in ((labels, reference['arrays']['pool_index']),
                             (anchors, reference['pools']['anchor']),
                             (capacity, reference['pools']['capacity_m3']),
                             (counts, reference['pools']['cell_count']),
                             (spill, reference['pools']['spill_m'])):
        np.testing.assert_array_equal(actual, expected)
    for cell in route['order'][::-1]:
        if cell < 0 or not seeds[cell]:
            continue
        label = labels[cell]
        if label >= 0:
            seeds[anchors[label]] = True
        target = route['receiver'][cell]
        if target >= 0:
            seeds[target] = True
    for cell in range(n):
        label = labels[cell]
        if label >= 0 and seeds[anchors[label]]:
            seeds[cell] = True
    np.testing.assert_array_equal(seeds, reference['arrays']['total_water_unknown'])
