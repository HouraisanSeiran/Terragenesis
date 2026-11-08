"""Save reproducible fixed-window Voronoi mountain comparisons."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_forms import VoronoiConfig, rasterize_voronoi as rasterize, sample_voronoi_stages as sample_stages
from terrain_pipeline.common_infra import TerrainGrid, BoundaryGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.terrain_map_style import physical_hillshade
from tools.prepare_procedural_mountains import measured

FAMILIES = ('cellular_massif', 'ridge_network', 'mixed')
WINDOWS = {'main': (0., 0.), 'negative': (-24000., -24000.)}
KEYS = ('advanced_base_m', 'unprotected_height_m', 'height_m')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def routing(fields, origin, spacing, seed):
    shape = fields[KEYS[0]].shape
    kind = np.full(shape, 'interior', dtype='<U24')
    kind[[0, -1], :] = 'unknown_boundary'
    kind[:, [0, -1]] = 'unknown_boundary'
    boundary = BoundaryGrid(kind, np.zeros(shape, bool), 'unknown perimeter', hashlib.sha256(kind.tobytes()).hexdigest())
    graphs, records = [], {}
    saved = {key: fields[key] for key in (*KEYS, 'protection_mask', 'structure_delta_m')}
    for key in KEYS:
        bed = fields[key]
        terrain = TerrainGrid(bed, np.ones(shape, bool), *origin, spacing, spacing, 'generated_terrain',
                              'voronoi_mountains', hashlib.sha256(bed.tobytes()).hexdigest(), generation_seed=seed)
        graph = route_diagnostic(terrain, boundary)
        flow = accumulate_local_discharge(graph, np.full(shape, .001))
        terminal = np.arange(bed.size, dtype=np.int64)
        for cell in graph.order_downstream_first:
            receiver = graph.receiver[cell]
            if receiver >= 0:
                terminal[cell] = terminal[receiver]
        graphs.append((graph, terminal))
        saved[key + '_receiver'] = graph.receiver
        saved[key + '_terminal'] = terminal
        saved[key + '_routed_q_m3_s'] = flow['routed_q_m3_s']
        records[key] = {'terminal_count': int(np.sum(graph.receiver < 0)),
                        'unknown_pending_m3_s': flow['unknown_pending_m3_s'],
                        'lake_retained_m3_s': flow['lake_retained_m3_s'],
                        'residual_m3_s': flow['residual_m3_s'],
                        'mean_edge_slope': float(graph.edge_slope.mean())}
    base, base_terminal = graphs[0]
    for key, (graph, terminal) in zip(KEYS[1:], graphs[1:]):
        records[key]['receiver_changed_fraction'] = float(np.mean(graph.receiver != base.receiver))
        records[key]['terminal_changed_fraction'] = float(np.mean(terminal != base_terminal))
        records[key]['mean_abs_edge_slope_change'] = float(np.mean(np.abs(graph.edge_slope - base.edge_slope)))
        records[key]['mean_abs_elevation_change_m'] = float(np.mean(np.abs(fields[key] - fields[KEYS[0]])))
    mask = fields['protection_mask']
    core = mask == 1
    outside = mask == 0
    delta = fields['height_m'] - fields['advanced_base_m']
    records['protection'] = {'core_fraction': float(core.mean()), 'transition_fraction': float(((mask > 0) & (mask < 1)).mean()),
        'outside_fraction': float(outside.mean()), 'core_max_abs_error_m': float(np.max(np.abs(delta[core]))) if core.any() else None,
        'outside_mean_abs_change_m': float(np.mean(np.abs(delta[outside]))) if outside.any() else None,
        'mean_abs_slope_effect': float(np.mean(np.abs(graphs[2][0].edge_slope - graphs[1][0].edge_slope)))}
    transition = ((mask > 0) & (mask < 1)).ravel()
    core_flat = core.ravel()
    records['protection']['core_receiver_changed_fraction'] = float(np.mean((graphs[2][0].receiver != base.receiver)[core_flat])) if core.any() else None
    records['protection']['core_terminal_changed_fraction'] = float(np.mean((graphs[2][1] != base_terminal)[core_flat])) if core.any() else None
    for label, values in (('protected_slope', graphs[2][0].edge_slope),
                          ('protection_slope_change', np.abs(graphs[2][0].edge_slope - graphs[1][0].edge_slope))):
        selected = values[transition]
        records['protection']['transition_' + label + '_p95'] = float(np.percentile(selected, 95)) if selected.size else None
        records['protection']['transition_' + label + '_max'] = float(np.max(selected)) if selected.size else None
    return records, saved


def render(path, fields, origin, spacing):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    heights = [fields[k] for k in KEYS]
    low, high = min(float(h.min()) for h in heights), max(float(h.max()) for h in heights)
    n = heights[0].shape[0]
    stride = max(1, int(np.ceil(n / 90)))
    xcoords = (origin[0] + np.arange(n) * spacing)[::stride] / 1000
    zcoords = (origin[1] + np.arange(n) * spacing)[::stride] / 1000
    x, z = np.meshgrid(xcoords, zcoords)
    extent = [origin[0] / 1000, (origin[0] + (n - 1) * spacing) / 1000,
              (origin[1] + (n - 1) * spacing) / 1000, origin[1] / 1000]
    fig = plt.figure(figsize=(15, 12), constrained_layout=True)
    for row, az in enumerate((-60, 120)):
        for col, h in enumerate(heights):
            ax = fig.add_subplot(4, 3, row * 3 + col + 1, projection='3d')
            sample = h[::stride, ::stride]
            shade = physical_hillshade(h, spacing)[::stride, ::stride]
            gray = np.repeat(np.clip(.22 + .68 * shade, 0, 1)[..., None], 3, axis=2)
            ax.plot_surface(x, z, sample / 1000, facecolors=gray, shade=False, linewidth=0, antialiased=False,
                            rcount=sample.shape[0], ccount=sample.shape[1])
            ax.set_zlim(low / 1000, high / 1000)
            ax.set_box_aspect((1, 1, .35)); ax.view_init(elev=25, azim=az)
            ax.set_title(f'{KEYS[col]} az={az}°'); ax.set_xlabel('X km'); ax.set_ylabel('Z km')
    for col, h in enumerate(heights):
        ax = fig.add_subplot(4, 3, 7 + col)
        ax.imshow(physical_hillshade(h, spacing), cmap='gray', vmin=0, vmax=1, extent=extent)
        ax.set_xlabel('World X km'); ax.set_ylabel('World Z km')
        ax.set_title(KEYS[col] + ' overhead')
    ax = fig.add_subplot(4, 3, 10)
    im = ax.imshow(fields['protection_mask'], vmin=0, vmax=1, cmap='viridis', extent=extent); fig.colorbar(im, ax=ax); ax.set_title('Protection mask'); ax.set_xlabel('World X km'); ax.set_ylabel('World Z km')
    ax = fig.add_subplot(4, 3, 11)
    effect = fields['height_m'] - fields['unprotected_height_m']
    lim = max(float(np.max(np.abs(effect))), 1e-9)
    im = ax.imshow(effect, cmap='coolwarm', vmin=-lim, vmax=lim, extent=extent); fig.colorbar(im, ax=ax, label='m'); ax.set_title('Protection correction'); ax.set_xlabel('World X km'); ax.set_ylabel('World Z km')
    ax = fig.add_subplot(4, 3, 12)
    for key, h in zip(KEYS, heights):
        ax.plot((origin[0] + np.arange(n) * spacing) / 1000, h[n // 2], label=key)
    ax.set_ylim(low, high); ax.set_xlabel('X km'); ax.set_ylabel('Elevation m'); ax.legend(fontsize=6); ax.set_title('Central section')
    exaggeration = .35 * ((n - 1) * spacing) / (high - low)
    fig.suptitle(f'Origin {origin} m; common scale; vertical exaggeration {exaggeration:.2f}×')
    fig.savefig(path, dpi=110); plt.close(fig)
    fig = plt.figure(figsize=(7, 5), constrained_layout=True)
    ax = fig.add_subplot(111, projection='3d')
    sample = heights[2][::stride, ::stride]
    shade = physical_hillshade(heights[2], spacing)[::stride, ::stride]
    gray = np.repeat(np.clip(.22 + .68 * shade, 0, 1)[..., None], 3, axis=2)
    ax.plot_surface(x, z, sample / 1000, facecolors=gray, shade=False, linewidth=0,
                    rcount=sample.shape[0], ccount=sample.shape[1])
    ax.set_zlim(low / 1000, high / 1000)
    ax.set_box_aspect(((n - 1) * spacing, (n - 1) * spacing, high - low))
    ax.view_init(elev=25, azim=-60); ax.set_title('Protected terrain, physical aspect 1:1')
    ax.set_xlabel('X km'); ax.set_ylabel('Z km'); ax.set_zlabel('height km')
    physical_path = path.with_name(path.stem + '_1to1.png')
    fig.savefig(physical_path, dpi=110); plt.close(fig)
    if origin == (0., 0.):
        lo, hi = int(round(9000 / spacing)), int(round(15000 / spacing))
        fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
        local_extent = [9, 15, 15, 9]
        for col, (key, h) in enumerate(zip(KEYS, heights)):
            axes[0, col].imshow(physical_hillshade(h, spacing)[lo:hi + 1, lo:hi + 1], cmap='gray', vmin=0, vmax=1, extent=local_extent)
            axes[0, col].set_title(key); axes[0, col].set_xlabel('World X km'); axes[0, col].set_ylabel('World Z km')
            axes[1, col].plot((origin[0] + np.arange(lo, hi + 1) * spacing) / 1000, h[(lo + hi) // 2, lo:hi + 1])
            axes[1, col].set_ylim(low, high); axes[1, col].set_xlabel('World X km'); axes[1, col].set_ylabel('Elevation m')
        fig.suptitle('Fixed central 9–15 km window; section at Z=12 km')
        detail_path = path.with_name(path.stem + '_central.png')
        fig.savefig(detail_path, dpi=110); plt.close(fig)
    with Image.open(path) as im:
        result = {'sha256': digest(path), 'width_px': im.width, 'height_px': im.height, 'stride': stride,
                'vertical_exaggeration': exaggeration, 'physical_aspect_file': physical_path.name,
                'physical_aspect_sha256': digest(physical_path)}
        if origin == (0., 0.):
            result.update({'central_file': detail_path.name, 'central_sha256': digest(detail_path)})
        return result


def generate(output, size=201, spacing=120., benchmark_sizes=(), windows=None, families=None):
    target = Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        sources = ['terrain_pipeline/voronoi_mountains.py', 'terrain_pipeline/procedural_mountains.py',
                   'terrain_pipeline/advanced_terrain_filter.py', 'terrain_pipeline/surface_rivers/metric_drainage.py',
                   'terrain_pipeline/surface_rivers/metric_contracts.py', 'terrain_pipeline/terrain_map_style.py',
                   'diffusion/geographic_noise.py', 'terrain_pipeline/world_seed.py', 'tools/prepare_voronoi_mountains.py',
                   'tools/prepare_procedural_mountains.py', 'terrain_pipeline/irregular_grid.py', 'terrain_pipeline/mountain_source_adapter.py']
        hashes = {p: digest(ROOT / p) for p in sources}
        manifest = {'world_seed': 20260903, 'coordinates': 'X east, Z south, metres', 'source_hashes_sha256': hashes,
                    'window_selection': 'fixed before inspection', 'boundary': 'unknown perimeter; diagnostic topology, not preserved river network',
                    'rasters': [], 'images': {}, 'timings': {}, 'diagnostics': {}, 'benchmark': []}
        for window in (windows or tuple(WINDOWS)):
            origin = WINDOWS[window]
            for family in (families or FAMILIES):
                cfg = VoronoiConfig(world_seed=20260903, family=family)
                fields, stats = measured(lambda: rasterize(origin, (size, size), spacing, cfg))
                prefix = f'{window}_{family}'
                metadata = {'source_hashes_sha256': hashes, 'origin_m_xz': origin, 'spacing_m': spacing,
                            'shape_zx': [size, size], 'algorithm': fields['metadata']}
                path = stage / (prefix + '.npz')
                np.savez_compressed(path, **{k: fields[k] for k in (*KEYS, 'structure_delta_m', 'protection_mask')},
                                    metadata_json=np.array(json.dumps(metadata, ensure_ascii=False, allow_nan=False)))
                manifest['rasters'].append({'file': path.name, 'sha256': digest(path), 'metadata': metadata})
                manifest['timings'][prefix + '_generation'] = stats
                render_start = time.perf_counter()
                image = render(stage / (prefix + '.png'), fields, origin, spacing)
                render_stats = {'seconds': time.perf_counter() - render_start,
                                'memory': 'not sampled for rendering'}
                manifest['images'][prefix + '.png'] = image
                manifest['timings'][prefix + '_render'] = render_stats
                diag_fields = rasterize(origin, (65, 65), 375., cfg)
                (record, arrays), diag_stats = measured(lambda: routing(diag_fields, origin, 375., 20260903))
                diag_path = stage / (prefix + '_routing.npz')
                np.savez_compressed(diag_path, **arrays)
                manifest['diagnostics'][prefix] = {'results': record, 'file': diag_path.name, 'sha256': digest(diag_path),
                                                   'size_zx': [65, 65], 'spacing_m': 375., 'local_q_m3_s_per_cell': .001, 'timing': diag_stats}
        for n in benchmark_sizes:
            cfg = VoronoiConfig(world_seed=20260903, family='mixed')
            for origin in (WINDOWS['main'], (500000000., -500000000.)):
                _, stats = measured(lambda: rasterize(origin, (n, n), 60., cfg))
                manifest['benchmark'].append({'size_zx': [n, n], 'origin_m_xz': origin, 'spacing_m': 60., **stats})
        cfg = VoronoiConfig(world_seed=20260903)
        coarse = rasterize((0., 0.), (17, 17), 120., cfg)['height_m']
        fine = rasterize((0., 0.), (33, 33), 60., cfg)['height_m']
        left = rasterize((0., 0.), (17, 8), 120., cfg)['height_m']
        right = rasterize((960., 0.), (17, 9), 120., cfg)['height_m']
        xx, zz = np.meshgrid(np.arange(17) * 120., np.arange(17) * 120.)
        order = np.random.default_rng(17).permutation(xx.size)
        shuffled = sample_stages(xx.ravel()[order], zz.ravel()[order], cfg)['height_m']
        reordered = np.empty_like(shuffled); reordered[order] = shuffled
        manifest['sampling_consistency'] = {'coarse_fine_max_abs_m': float(np.max(np.abs(coarse - fine[::2, ::2]))),
            'split_max_abs_m': float(np.max(np.abs(coarse - np.concatenate((left, right), axis=1)))),
            'shuffled_max_abs_m': float(np.max(np.abs(coarse.ravel() - reordered)))}
        manifest['measurement_scope'] = 'wall seconds and tracemalloc peak; sampled whole-process RSS includes prior allocations and may miss peaks; rendering timed separately'
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        os.rename(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--final', action='store_true', help='401² at 60 m and 128/256/512 benchmarks')
    parser.add_argument('--windows', nargs='+', choices=tuple(WINDOWS), default=None)
    parser.add_argument('--families', nargs='+', choices=FAMILIES, default=None)
    args = parser.parse_args()
    print(generate(args.output_dir, 401 if args.final else 201, 60. if args.final else 120.,
                   (128, 256, 512) if args.final else (), args.windows, args.families))


if __name__ == '__main__':
    main()
