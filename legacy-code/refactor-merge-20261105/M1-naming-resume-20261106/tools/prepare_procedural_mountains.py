"""Generate independent procedural-mountain evidence; never modifies existing output."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import tracemalloc
import threading

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_forms import MountainConfig, rasterize_procedural as rasterize, sample_procedural_height as sample_height
from terrain_pipeline.terrain_map_style import physical_hillshade

FAMILIES = ('granite_dome', 'layered_massif', 'glacial_horn', 'mixed')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def measured(call):
    try:
        import psutil
        process = psutil.Process()
    except ImportError:
        process = None
    stop = threading.Event()
    rss = []
    def monitor():
        while not stop.wait(.01):
            rss.append(process.memory_info().rss)
    if process:
        rss.append(process.memory_info().rss)
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
    tracemalloc.start()
    start = time.perf_counter()
    try:
        result = call()
        elapsed = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        stop.set()
        if process:
            thread.join()
    return result, {'seconds': elapsed, 'tracemalloc_peak_bytes': peak,
                    'sampled_process_rss_peak_bytes': max(rss) if rss else None}


def benchmark(origin, spacing, sizes, world_seed):
    cfg = MountainConfig(world_seed=world_seed)
    results = []
    for size in sizes:
        for location, xy in [('selected', origin), ('far', (500_000_000.0, -500_000_000.0))]:
            _, stats = measured(lambda: rasterize(xy, (size, size), spacing, cfg))
            results.append({'size_zx': [size, size], 'location': location, **stats})
    n = min(max(sizes), 256)
    xx, zz = np.meshgrid(origin[0] + np.arange(n) * spacing, origin[1] + np.arange(n) * spacing)
    x, z = xx.ravel(), zz.ravel()
    order = np.random.default_rng(12345).permutation(x.size)
    normal, direct = measured(lambda: sample_height(x, z, cfg))
    shuffled, shuffled_stats = measured(lambda: sample_height(x[order], z[order], cfg))
    reorder = np.empty_like(shuffled)
    reorder[order] = shuffled
    grid = rasterize(origin, (n, n), spacing, cfg)['height_m']
    mid = n // 2
    left = rasterize(origin, (n, mid), spacing, cfg)['height_m']
    right = rasterize((origin[0] + mid * spacing, origin[1]), (n, n - mid), spacing, cfg)['height_m']
    fine = rasterize(origin, (2 * n - 1, 2 * n - 1), spacing / 2, cfg)['height_m']
    return {'raster_runs': results, 'point_queries': {'count': int(x.size), 'ordered': direct,
            'shuffled': shuffled_stats, 'max_abs_difference_m': float(np.max(np.abs(normal - reorder)))},
            'chunk_split_max_abs_difference_m': float(np.max(np.abs(grid - np.concatenate((left, right), axis=1)))),
            'nested_spacing_m': [spacing, spacing / 2],
            'nested_max_abs_difference_m': float(np.max(np.abs(grid - fine[::2, ::2]))),
            'memory_scope': 'tracemalloc traced allocations and 10 ms sampled whole-process RSS; RSS includes prior allocations and can miss peaks',
            'timing_scope': 'perf_counter wall time; each call includes allocation, no cache assumptions'}


def render(out, arrays, origin, spacing):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import cm, colors
    from PIL import Image
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    heights = [arrays[(f, 'detail')] for f in FAMILIES]
    low = min(float(a.min()) for a in heights + [arrays[(f, 'base')] for f in FAMILIES])
    high = max(float(a.max()) for a in heights + [arrays[(f, 'base')] for f in FAMILIES])
    if high <= low:
        raise ValueError('constant terrain cannot produce meaningful comparison')
    norm = colors.Normalize(low, high)
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.8), constrained_layout=True)
    nz, nx = heights[0].shape
    extent = [origin[0] / 1000, (origin[0] + (nx - 1) * spacing) / 1000,
              (origin[1] + (nz - 1) * spacing) / 1000, origin[1] / 1000]
    for ax, family, h in zip(axes, FAMILIES, heights):
        shade = physical_hillshade(h, spacing)
        rgb = cm.terrain(norm(h))[..., :3] * (0.55 + 0.45 * shade[..., None])
        ax.imshow(rgb, extent=extent, origin='upper', vmin=0, vmax=1)
        ax.set_title(family); ax.set_xlabel('X (km)'); ax.set_ylabel('Z south (km)')
    fig.colorbar(cm.ScalarMappable(norm=norm, cmap='terrain'), ax=axes, label='Elevation (m)', shrink=.7)
    fig.suptitle('Independent procedural mountains — morphology-inspired; no real-site reconstruction')
    fig.savefig(out / 'overview.png', dpi=130); plt.close(fig)
    fig = plt.figure(figsize=(16, 8), constrained_layout=True)
    stride = max(1, int(np.ceil(max(nx, nz) / 160)))
    x = (origin[0] + np.arange(nx) * spacing)[::stride] / 1000
    z = (origin[1] + np.arange(nz) * spacing)[::stride] / 1000
    X, Z = np.meshgrid(x, z)
    for row, az in enumerate((-60, 120)):
        for col, family in enumerate(FAMILIES):
            h = arrays[(family, 'detail')][::stride, ::stride]
            ax = fig.add_subplot(2, 4, row * 4 + col + 1, projection='3d')
            shade = physical_hillshade(arrays[(family, 'detail')], spacing)[::stride, ::stride]
            gray = np.clip(.22 + .68 * shade, 0, 1)
            face = np.repeat(gray[..., None], 3, axis=2)
            ax.plot_surface(X, Z, h / 1000, facecolors=face, shade=False, linewidth=0, antialiased=False,
                            rcount=h.shape[0], ccount=h.shape[1])
            ax.set_zlim(low / 1000, high / 1000); ax.set_box_aspect((1, 1, .35))
            ax.view_init(elev=25, azim=az); ax.set_title(f'{family}\nazimuth {az}°')
            ax.tick_params(axis='both', labelsize=6, pad=-2)
            ax.tick_params(axis='z', labelsize=6, pad=-2)
            ax.set_xlabel('X km', fontsize=7, labelpad=-2)
            ax.set_ylabel('Z km', fontsize=7, labelpad=-2)
            ax.set_zlabel('height km', fontsize=7, labelpad=-2)
    exaggeration = .35 * ((nx - 1) * spacing) / (high - low)
    fig.suptitle(f'Fixed light and common scale; vertical exaggeration {exaggeration:.2f}×')
    fig.savefig(out / 'oblique.png', dpi=130); plt.close(fig)
    fig = plt.figure(figsize=(8, 6), constrained_layout=True)
    ax = fig.add_subplot(111, projection='3d')
    h = arrays[('mixed', 'detail')][::stride, ::stride]
    shade = physical_hillshade(arrays[('mixed', 'detail')], spacing)[::stride, ::stride]
    gray = np.repeat(np.clip(.22 + .68 * shade, 0, 1)[..., None], 3, axis=2)
    ax.plot_surface(X, Z, h / 1000, facecolors=gray, shade=False, linewidth=0,
                    rcount=h.shape[0], ccount=h.shape[1])
    ax.set_zlim(low / 1000, high / 1000)
    ax.set_box_aspect(((nx - 1) * spacing, (nz - 1) * spacing, high - low))
    ax.view_init(elev=25, azim=-60)
    ax.set_xlabel('X km'); ax.set_ylabel('Z km'); ax.set_zlabel('height km')
    ax.set_title('Mixed family, 1:1 physical aspect')
    fig.savefig(out / 'physical_aspect.png', dpi=130); plt.close(fig)
    fig, axes = plt.subplots(2, 4, figsize=(16, 7), constrained_layout=True)
    for col, family in enumerate(FAMILIES):
        h = arrays[(family, 'base')]
        shade = physical_hillshade(h, spacing)
        axes[0, col].imshow(shade, cmap='gray', vmin=0, vmax=1, extent=extent)
        axes[0, col].set_title(f'{family}: detail off')
        axes[0, col].set_xlabel('X (km)'); axes[0, col].set_ylabel('Z south (km)')
        axes[1, col].plot((origin[0] + np.arange(nx) * spacing) / 1000, h[nz // 2], label='detail off')
        axes[1, col].plot((origin[0] + np.arange(nx) * spacing) / 1000, arrays[(family, 'detail')][nz // 2], label='detail on', alpha=.7)
        axes[1, col].set_ylim(low, high); axes[1, col].set_xlabel('X (km)'); axes[1, col].set_ylabel('Elevation (m)')
        axes[1, col].legend(fontsize=7)
    fig.suptitle('Detail-off relief and central sections, common elevation scale')
    fig.savefig(out / 'sections.png', dpi=130); plt.close(fig)
    checks = {}
    for name in ('overview.png', 'oblique.png', 'physical_aspect.png', 'sections.png'):
        with Image.open(out / name) as im:
            a = np.asarray(im.convert('RGB'))
            checks[name] = {'width_px': im.width, 'height_px': im.height,
                            'nonblank': bool(np.ptp(a) > 0), 'sha256': digest(out / name)}
            if not checks[name]['nonblank']:
                raise ValueError(f'blank image: {name}')
    return checks, [low, high]


def render_stages(out, stages, origin, spacing):
    import matplotlib.pyplot as plt
    from PIL import Image
    keys = ('base_noise_m', 'advanced_base_m', 'regional_noise_delta_m', 'height_m')
    fig, axes = plt.subplots(4, 4, figsize=(15, 14), constrained_layout=True)
    elevations = [stages[f][k] for f in FAMILIES for k in (keys[0], keys[1], keys[3])]
    low = min(float(a.min()) for a in elevations)
    high = max(float(a.max()) for a in elevations)
    max_delta = max(float(np.max(np.abs(stages[f][keys[2]]))) for f in FAMILIES) or 1.
    shape = elevations[0].shape
    extent = [origin[0] / 1000, (origin[0] + (shape[1] - 1) * spacing) / 1000,
              (origin[1] + (shape[0] - 1) * spacing) / 1000, origin[1] / 1000]
    for row, family in enumerate(FAMILIES):
        for col, key in enumerate(keys):
            ax = axes[row, col]
            value = stages[family][key]
            delta = key == keys[2]
            image = ax.imshow(value, extent=extent, cmap='coolwarm' if delta else 'terrain',
                              vmin=-max_delta if delta else low, vmax=max_delta if delta else high)
            ax.set_title(f'{family}: {key}'); ax.set_xlabel('X km'); ax.set_ylabel('Z south km')
            fig.colorbar(image, ax=ax, shrink=.7, label='m')
    fig.suptitle('Actual sampled stages; regional panel is signed height delta')
    fig.savefig(out / 'stages.png', dpi=120); plt.close(fig)
    with Image.open(out / 'stages.png') as im:
        a = np.asarray(im.convert('RGB'))
        check = {'width_px': im.width, 'height_px': im.height, 'nonblank': bool(np.ptp(a) > 0),
                 'sha256': digest(out / 'stages.png')}
    if not check['nonblank']:
        raise ValueError('blank stage image')
    return check


def render_processes(out, arrays):
    import matplotlib.pyplot as plt
    from PIL import Image
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    im = axes[0].imshow(arrays['routed_q_m3_s'], origin='upper', cmap='viridis')
    axes[0].set_title('Diagnostic routed discharge'); fig.colorbar(im, ax=axes[0], label='m³/s')
    im = axes[1].imshow(arrays['diffusion_delta_m'], origin='upper', cmap='coolwarm')
    axes[1].set_title('Finite diffusion bed delta'); fig.colorbar(im, ax=axes[1], label='m')
    axes[2].plot(arrays['glacier_source_x_m'], arrays['glacier_before_m'], label='before')
    axes[2].plot(arrays['glacier_source_x_m'], arrays['glacier_after_m'], '--', label='after')
    axes[2].set_title('Nine-cell glacier bed'); axes[2].set_xlabel('X m'); axes[2].set_ylabel('Elevation m'); axes[2].legend()
    fig.suptitle('Finite process diagnostics; unknown boundary; glacier is not a valley simulation')
    fig.savefig(out / 'processes.png', dpi=120); plt.close(fig)
    with Image.open(out / 'processes.png') as im:
        a = np.asarray(im.convert('RGB'))
        return {'width_px': im.width, 'height_px': im.height, 'nonblank': bool(np.ptp(a) > 0),
                'sha256': digest(out / 'processes.png')}


def generate(args):
    target = args.output_dir.resolve()
    if target.exists():
        raise FileExistsError(f'output already exists: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f'.{target.name}-', dir=target.parent))
    try:
        source_hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in
                         (ROOT / 'terrain_pipeline/procedural_mountains.py', ROOT / 'terrain_pipeline/advanced_terrain_filter.py', ROOT / 'diffusion/geographic_noise.py', ROOT / 'terrain_pipeline/world_seed.py', Path(__file__).resolve(), ROOT / 'terrain_pipeline/terrain_map_style.py')}
        arrays, records, stages, core_metadata = {}, [], {}, {}
        for family in FAMILIES:
            for label, strength in [('base', 0.0), ('detail', .35)]:
                cfg = MountainConfig(world_seed=args.world_seed, family=family, detail_strength=strength)
                result = rasterize(args.origin, (args.size, args.size), args.spacing, cfg)
                height = result['height_m']
                if height.shape != (args.size, args.size) or not np.isfinite(height).all():
                    raise ValueError('invalid generated height field')
                metadata = {**result['metadata'], 'source_family': 'independent_procedural_mountains',
                            'source_hashes_sha256': source_hashes, 'origin_m_xz': list(args.origin),
                            'spacing_m': args.spacing, 'units': 'm', 'shape_zx': list(height.shape)}
                path = stage / f'{family}_{label}.npz'
                stage_keys = ('base_noise_m', 'advanced_base_m', 'regional_noise_delta_m', 'height_m')
                np.savez_compressed(path, **{key: result[key] for key in stage_keys}, metadata_json=np.array(json.dumps(metadata, ensure_ascii=False, allow_nan=False)))
                arrays[(family, label)] = height
                if label == 'detail':
                    stages[family] = {key: result[key] for key in stage_keys}
                    core_metadata[family] = result['metadata']
                records.append({'file': path.name, 'sha256': digest(path), 'family': family,
                                'detail_strength': strength, 'min_m': float(height.min()), 'max_m': float(height.max())})
        (checks, limits), render_stats = measured(lambda: render(stage, arrays, args.origin, args.spacing))
        stage_check, stage_render_stats = measured(lambda: render_stages(stage, stages, args.origin, args.spacing))
        checks['stages.png'] = stage_check
        bench = benchmark(args.origin, args.spacing, args.benchmark_sizes, args.world_seed)
        bench['rendering'] = {'geometry_figures': render_stats, 'stages_figure': stage_render_stats}
        save_json(stage / 'benchmark.json', bench)
        process_record = None
        if args.with_processes:
            from terrain_pipeline.mountain_forms import prepare_process_evidence
            (process_arrays, process_metadata), process_stats = measured(lambda: prepare_process_evidence(args.origin, args.world_seed))
            np.savez_compressed(stage / 'processes.npz', **process_arrays)
            save_json(stage / 'processes.json', process_metadata)
            checks['processes.png'], process_render_stats = measured(lambda: render_processes(stage, process_arrays))
            process_record = {'npz': 'processes.npz', 'npz_sha256': digest(stage / 'processes.npz'),
                              'metadata': 'processes.json', 'metadata_sha256': digest(stage / 'processes.json'),
                              'timing': process_stats, 'render_timing': process_render_stats,
                              'source_hashes_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in (
                                  ROOT / 'terrain_pipeline/procedural_mountain_processes.py',
                                  ROOT / 'terrain_pipeline/surface_rivers/metric_drainage.py',
                                  ROOT / 'terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py',
                                  ROOT / 'terrain_pipeline/surface_rivers/metric_contracts.py',
                                  ROOT / 'terrain_pipeline/bounded_glacier.py')}}
        manifest = {'source_family': 'independent_procedural_mountains', 'world_seed': args.world_seed,
                    'description': 'Generic morphology-inspired geometric candidates; not real peaks, geology simulation, TD terrain, or hydrology.',
                    'coverage_status': 'complete_in_window', 'origin_m_xz': list(args.origin), 'shape_zx': [args.size, args.size],
                    'spacing_m': args.spacing, 'view_selection': 'Fixed default origin [0, 0] m, chosen before inspecting heights; custom origin and spacing are explicit.', 'coordinates': 'planar X east, Z south, metres',
                    'height_units': 'm', 'source_hashes_sha256': source_hashes, 'rasters': records,
                    'core_metadata_by_family': core_metadata,
                    'images': checks, 'elevation_scale_m': limits,
                    'rendering': {'light': [-0.5, -0.5, 2 ** -0.5], 'oblique_azimuth_degrees': [-60, 120],
                                  'oblique_elevation_degrees': 25, 'oblique_box_aspect': [1, 1, .35],
                                  'oblique_vertical_exaggeration': .35 * ((args.size - 1) * args.spacing) / (limits[1] - limits[0]),
                                  'physical_aspect_image': 'physical_aspect.png (1:1:1)',
                                  'surface_stride_samples': max(1, int(np.ceil(args.size / 160))),
                                  'materials': 'grayscale geometry only for oblique'},
                    'benchmark': {'file': 'benchmark.json', 'sha256': digest(stage / 'benchmark.json')},
                    'advanced_filter_upstream': {'url': 'https://github.com/lpmitchell/AdvancedTerrainErosion',
                        'commit': '57e79cc331d17e2a45c897bea9c4c022d1fc5551', 'license': 'MPL-2.0',
                        'scope': 'pointwise NumPy port; not water or sediment simulation',
                        'hash_change': 'Default stable integer hash intentionally differs from upstream float Hash2 to avoid far-coordinate collapse; upstream mode remains available for comparison.'},
                    'optional_processes': process_record,
                    'image_check_scope': 'dimensions and nonblank pixels only; morphology requires human review'}
        save_json(stage / 'manifest.json', manifest)
        os.rename(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--origin', nargs=2, type=float, default=(0.0, 0.0), metavar=('X_M', 'Z_M'))
    parser.add_argument('--size', type=int, default=401, help='square raster side, 3 to 512')
    parser.add_argument('--spacing', type=float, default=60.0, help='metres')
    parser.add_argument('--world-seed', type=int, default=20260903)
    parser.add_argument('--benchmark-sizes', nargs='+', type=int, default=[128, 256, 512])
    parser.add_argument('--with-processes', action='store_true', help='add separate finite river, diffusion and glacier diagnostics')
    args = parser.parse_args(argv)
    if not 3 <= args.size <= 512 or not np.isfinite(args.spacing) or args.spacing <= 0 or not np.isfinite(args.origin).all():
        parser.error('size must be 3..512, spacing positive and coordinates finite')
    if not args.benchmark_sizes or len(args.benchmark_sizes) > 3 or any(n < 3 or n > 512 for n in args.benchmark_sizes):
        parser.error('benchmark sizes must contain at most three values in 3..512')
    try:
        print(generate(args))
    except (ValueError, FileExistsError, OSError) as exc:
        parser.exit(2, f'error: {exc}\n')


if __name__ == '__main__':
    main()



