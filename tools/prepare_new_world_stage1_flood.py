"""Report conservative mapping budgets for the experimental split flood."""
import argparse
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_stage1_checkpoint import memory


def main():
    p = argparse.ArgumentParser()
    p.add_argument('terrain', type=Path)
    p.add_argument('graph', type=Path)
    args = p.parse_args()
    source = json.loads((args.terrain / 'manifest.json').read_text(encoding='utf8'))
    n = int(np.prod(source['shape_zx']))
    sizes = lambda root, names: sum((root / (name + '.npy')).stat().st_size for name in names)
    graph_a = sizes(args.graph, ('indptr', 'indices'))
    graph_b = graph_a + sizes(args.graph, ('node_x_m', 'node_z_m'))
    source_a = sizes(args.terrain, ('bed_m', 'valid_mask')) + n + 128
    source_b = sizes(args.terrain, ('valid_mask',)) + n + 128
    # Seven A arrays and four B arrays include their NPY headers.
    mapped_a = graph_a + source_a + 41*n + 6*128
    mapped_b = graph_b + source_b + 32*n + 4*128
    fixed = 384*1024**2 + 1024**3
    resources = memory()
    print(json.dumps({'status': 'experimental; execution unavailable', 'phase_a_mapped_bytes': mapped_a, 'phase_b_mapped_bytes': mapped_b, 'workspace_bytes': 384*1024**2, 'physical_reserve_bytes': 1024**3, 'phase_a_required_bytes': mapped_a + fixed, 'phase_b_required_bytes': mapped_b + fixed, **resources, 'phase_a_gap_bytes': max(0, mapped_a + fixed - resources['available_ram_bytes']), 'phase_b_gap_bytes': max(0, mapped_b + fixed - resources['available_ram_bytes']), 'commit_reserve_bytes': 2*1024**3}, indent=2))


if __name__ == '__main__':
    main()
