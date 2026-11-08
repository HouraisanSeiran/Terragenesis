from pathlib import Path
import numpy as np
from terrain_pipeline import new_world_stage1 as old
import terrain_pipeline.drainage as split


def test_split_matches_reference_with_mapped_arrays(tmp_path):
    shape = (12, 13)
    graph = old.build_native_graph(shape, (-17, -23), tmp_path / 'graph', block_size=4)
    bed = np.full(shape, 5., dtype='f8')
    bed[3:9, 3:10] = -2
    bed[5:7, 5:8] = -5
    valid = np.ones(shape, dtype=bool)
    valid[4, 4] = False
    outlets = np.zeros(shape, dtype=bool)
    outlets[0, :] = True
    outlets[-1, :] = True
    outlets[:, 0] = True
    outlets[:, -1] = True
    reference = old.route_native_graph(bed, outlets, graph, tmp_path / 'reference', valid_mask=valid)
    root = tmp_path / 'split'
    root.mkdir()
    n = bed.size
    arrays = {name: split.create(root, name, dtype, n) for name, dtype in [('filled','f8'), ('order','i8'), ('rank','i8'), ('receiver','i8'), ('discovered','?'), ('heap_level','f8'), ('heap_node','i8')]}
    split.flood_order(bed.ravel(), outlets.ravel(), valid.ravel(), graph['indptr'], graph['indices'], arrays['filled'], arrays['order'], arrays['rank'], arrays['discovered'], arrays['heap_level'], arrays['heap_node'])
    split.select_receivers(outlets.ravel(), valid.ravel(), graph['node_x_m'], graph['node_z_m'], graph['indptr'], graph['indices'], arrays['filled'], arrays['order'], arrays['rank'], arrays['receiver'])
    for name in ('filled', 'order', 'rank', 'receiver'):
        np.testing.assert_array_equal(arrays[name], reference[name])
