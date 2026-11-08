"""Consolidated tools.prepare_mountain_forms implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse as _i3_argparse
import hashlib as _i3_hashlib
import json as _i3_json
import os as _i3_os
from pathlib import Path as _i3_Path
import shutil as _i3_shutil
import sys as _i3_sys
import tempfile as _i3_tempfile
import time as _i3_time
import tracemalloc as _i3_tracemalloc
import threading as _i3_threading
import numpy as _i3_np
from terrain_pipeline.mountain_forms import MountainConfig as _i3_MountainConfig
from terrain_pipeline.mountain_forms import rasterize_procedural as _i3_rasterize
from terrain_pipeline.mountain_forms import sample_procedural_height as _i3_sample_height
from terrain_pipeline.terrain_map_style import physical_hillshade as _i3_physical_hillshade
import argparse as _i1_argparse
from dataclasses import asdict as _i1_asdict
import hashlib as _i1_hashlib
import json as _i1_json
import os as _i1_os
from pathlib import Path as _i1_Path
import shutil as _i1_shutil
import sys as _i1_sys
import tempfile as _i1_tempfile
import time as _i1_time
import numpy as _i1_np
from PIL import Image as _i1_Image
from terrain_pipeline.mountain_forms import LOCAL_VOLUME_ALGORITHM_ID as _i1_LOCAL_VOLUME_ALGORITHM_ID
from terrain_pipeline.mountain_forms import LocalVolumeConfig as _i1_LocalVolumeConfig
from terrain_pipeline.mountain_forms import sample_local_volume_mountains as _i1_sample_local_volume_mountains
from terrain_pipeline.mountain_forms import PRODUCT_ALGORITHM_ID as _i1_ORIGINAL_ID
from terrain_pipeline.mountain_forms import AdvancedFilterConfig as _i1_AdvancedFilterConfig
from terrain_pipeline.mountain_forms import ADVANCED_ALGORITHM_ID as _i1_ADVANCED_ID
from terrain_pipeline.terrain_map_style import physical_hillshade as _i1_physical_hillshade
from terrain_pipeline.common_infra import derive_subseed as _i1_derive_subseed
import argparse as _i0_argparse
from dataclasses import asdict as _i0_asdict
import hashlib as _i0_hashlib
import json as _i0_json
import math as _i0_math
import os as _i0_os
from pathlib import Path as _i0_Path
import platform as _i0_platform
import shutil as _i0_shutil
import sys as _i0_sys
import tempfile as _i0_tempfile
import time as _i0_time
import numpy as _i0_np
from terrain_pipeline import mountain_forms as _i0_advanced
from terrain_pipeline.mountain_forms import LocalVolumeConfig as _i0_LocalVolumeConfig
from terrain_pipeline.mountain_forms import sample_local_volume_mountains as _i0_sample_local_volume_mountains
from terrain_pipeline.skeleton_mountains import ALGORITHM_ID as _i0_ALGORITHM_ID
from terrain_pipeline.skeleton_mountains import CACHE_CAPACITY as _i0_CACHE_CAPACITY
from terrain_pipeline.skeleton_mountains import HALO_M as _i0_HALO_M
from terrain_pipeline.skeleton_mountains import PURPOSES as _i0_PURPOSES
from terrain_pipeline.skeleton_mountains import SOURCE_SUPPORT_CELLS as _i0_SOURCE_SUPPORT_CELLS
from terrain_pipeline.skeleton_mountains import SkeletonMountainConfig as _i0_SkeletonMountainConfig
from terrain_pipeline.skeleton_mountains import describe_skeleton as _i0_describe_skeleton
from terrain_pipeline.skeleton_mountains import sample_skeleton_mountains as _i0_sample_skeleton_mountains
from terrain_pipeline.terrain_map_style import physical_hillshade as _i0_physical_hillshade
from terrain_pipeline.common_infra import WORLD_SEED as _i0_WORLD_SEED
from terrain_pipeline.common_infra import derive_subseed as _i0_derive_subseed
import argparse as _i2_argparse
from dataclasses import asdict as _i2_asdict
import hashlib as _i2_hashlib
import json as _i2_json
import os as _i2_os
from pathlib import Path as _i2_Path
import shutil as _i2_shutil
import sys as _i2_sys
import tempfile as _i2_tempfile
import time as _i2_time
import numpy as _i2_np
from PIL import Image as _i2_Image
from terrain_pipeline.mountain_forms import PRODUCT_ALGORITHM_ID as _i2_PRODUCT_ALGORITHM_ID
from terrain_pipeline.mountain_forms import ProductMountainConfig as _i2_ProductMountainConfig
from terrain_pipeline.mountain_forms import sample_product_mountains as _i2_sample_product_mountains
from terrain_pipeline.mountain_forms import AdvancedFilterConfig as _i2_AdvancedFilterConfig
from terrain_pipeline.mountain_forms import ADVANCED_ALGORITHM_ID as _i2_ADVANCED_ID
from terrain_pipeline.terrain_map_style import physical_hillshade as _i2_physical_hillshade
from terrain_pipeline.common_infra import derive_subseed as _i2_derive_subseed
import argparse as _i4_argparse
import hashlib as _i4_hashlib
import json as _i4_json
import os as _i4_os
from pathlib import Path as _i4_Path
import shutil as _i4_shutil
import sys as _i4_sys
import tempfile as _i4_tempfile
import time as _i4_time
import numpy as _i4_np
from terrain_pipeline.mountain_forms import VoronoiConfig as _i4_VoronoiConfig
from terrain_pipeline.mountain_forms import rasterize_voronoi as _i4_rasterize
from terrain_pipeline.mountain_forms import sample_voronoi_stages as _i4_sample_stages
from terrain_pipeline.common_infra import TerrainGrid as _i4_TerrainGrid
from terrain_pipeline.common_infra import BoundaryGrid as _i4_BoundaryGrid
from terrain_pipeline.drainage import route_diagnostic as _i4_route_diagnostic
from terrain_pipeline.drainage import accumulate_local_discharge as _i4_accumulate_local_discharge
from terrain_pipeline.terrain_map_style import physical_hillshade as _i4_physical_hillshade

CATEGORY = 'B'

# Source: tools.prepare_procedural_mountains
_i3_sys.path.insert(0, str(ROOT))

# Source: tools.prepare_procedural_mountains
FAMILIES = ('granite_dome', 'layered_massif', 'glacial_horn', 'mixed')

# Source: tools.prepare_procedural_mountains
def save_json(path, value):
    path.write_text(_i3_json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

# Source: tools.prepare_procedural_mountains
def measured(call):
    try:
        import psutil
        process = psutil.Process()
    except ImportError:
        process = None
    stop = _i3_threading.Event()
    rss = []

    def monitor():
        while not stop.wait(0.01):
            rss.append(process.memory_info().rss)
    if process:
        rss.append(process.memory_info().rss)
        thread = _i3_threading.Thread(target=monitor, daemon=True)
        thread.start()
    _i3_tracemalloc.start()
    start = _i3_time.perf_counter()
    try:
        result = call()
        elapsed = _i3_time.perf_counter() - start
        _, peak = _i3_tracemalloc.get_traced_memory()
    finally:
        _i3_tracemalloc.stop()
        stop.set()
        if process:
            thread.join()
    return (result, {'seconds': elapsed, 'tracemalloc_peak_bytes': peak, 'sampled_process_rss_peak_bytes': max(rss) if rss else None})

# Source: tools.prepare_procedural_mountains
def benchmark_procedural(origin, spacing, sizes, world_seed):
    cfg = _i3_MountainConfig(world_seed=world_seed)
    results = []
    for size in sizes:
        for location, xy in [('selected', origin), ('far', (500000000.0, -500000000.0))]:
            _, stats = measured(lambda: _i3_rasterize(xy, (size, size), spacing, cfg))
            results.append({'size_zx': [size, size], 'location': location, **stats})
    n = min(max(sizes), 256)
    xx, zz = _i3_np.meshgrid(origin[0] + _i3_np.arange(n) * spacing, origin[1] + _i3_np.arange(n) * spacing)
    x, z = (xx.ravel(), zz.ravel())
    order = _i3_np.random.default_rng(12345).permutation(x.size)
    normal, direct = measured(lambda: _i3_sample_height(x, z, cfg))
    shuffled, shuffled_stats = measured(lambda: _i3_sample_height(x[order], z[order], cfg))
    reorder = _i3_np.empty_like(shuffled)
    reorder[order] = shuffled
    grid = _i3_rasterize(origin, (n, n), spacing, cfg)['height_m']
    mid = n // 2
    left = _i3_rasterize(origin, (n, mid), spacing, cfg)['height_m']
    right = _i3_rasterize((origin[0] + mid * spacing, origin[1]), (n, n - mid), spacing, cfg)['height_m']
    fine = _i3_rasterize(origin, (2 * n - 1, 2 * n - 1), spacing / 2, cfg)['height_m']
    return {'raster_runs': results, 'point_queries': {'count': int(x.size), 'ordered': direct, 'shuffled': shuffled_stats, 'max_abs_difference_m': float(_i3_np.max(_i3_np.abs(normal - reorder)))}, 'chunk_split_max_abs_difference_m': float(_i3_np.max(_i3_np.abs(grid - _i3_np.concatenate((left, right), axis=1)))), 'nested_spacing_m': [spacing, spacing / 2], 'nested_max_abs_difference_m': float(_i3_np.max(_i3_np.abs(grid - fine[::2, ::2]))), 'memory_scope': 'tracemalloc traced allocations and 10 ms sampled whole-process RSS; RSS includes prior allocations and can miss peaks', 'timing_scope': 'perf_counter wall time; each call includes allocation, no cache assumptions'}

# Source: tools.prepare_procedural_mountains
def render_procedural(out, arrays, origin, spacing):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import cm
    from matplotlib import colors
    from PIL import Image
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    heights = [arrays[f, 'detail'] for f in FAMILIES]
    low = min((float(a.min()) for a in heights + [arrays[f, 'base'] for f in FAMILIES]))
    high = max((float(a.max()) for a in heights + [arrays[f, 'base'] for f in FAMILIES]))
    if high <= low:
        raise ValueError('constant terrain cannot produce meaningful comparison')
    norm = colors.Normalize(low, high)
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.8), constrained_layout=True)
    nz, nx = heights[0].shape
    extent = [origin[0] / 1000, (origin[0] + (nx - 1) * spacing) / 1000, (origin[1] + (nz - 1) * spacing) / 1000, origin[1] / 1000]
    for ax, family, h in zip(axes, FAMILIES, heights):
        shade = _i3_physical_hillshade(h, spacing)
        rgb = cm.terrain(norm(h))[..., :3] * (0.55 + 0.45 * shade[..., None])
        ax.imshow(rgb, extent=extent, origin='upper', vmin=0, vmax=1)
        ax.set_title(family)
        ax.set_xlabel('X (km)')
        ax.set_ylabel('Z south (km)')
    fig.colorbar(cm.ScalarMappable(norm=norm, cmap='terrain'), ax=axes, label='Elevation (m)', shrink=0.7)
    fig.suptitle('Independent procedural mountains — morphology-inspired; no real-site reconstruction')
    fig.savefig(out / 'overview.png', dpi=130)
    plt.close(fig)
    fig = plt.figure(figsize=(16, 8), constrained_layout=True)
    stride = max(1, int(_i3_np.ceil(max(nx, nz) / 160)))
    x = (origin[0] + _i3_np.arange(nx) * spacing)[::stride] / 1000
    z = (origin[1] + _i3_np.arange(nz) * spacing)[::stride] / 1000
    X, Z = _i3_np.meshgrid(x, z)
    for row, az in enumerate((-60, 120)):
        for col, family in enumerate(FAMILIES):
            h = arrays[family, 'detail'][::stride, ::stride]
            ax = fig.add_subplot(2, 4, row * 4 + col + 1, projection='3d')
            shade = _i3_physical_hillshade(arrays[family, 'detail'], spacing)[::stride, ::stride]
            gray = _i3_np.clip(0.22 + 0.68 * shade, 0, 1)
            face = _i3_np.repeat(gray[..., None], 3, axis=2)
            ax.plot_surface(X, Z, h / 1000, facecolors=face, shade=False, linewidth=0, antialiased=False, rcount=h.shape[0], ccount=h.shape[1])
            ax.set_zlim(low / 1000, high / 1000)
            ax.set_box_aspect((1, 1, 0.35))
            ax.view_init(elev=25, azim=az)
            ax.set_title(f'{family}\nazimuth {az}°')
            ax.tick_params(axis='both', labelsize=6, pad=-2)
            ax.tick_params(axis='z', labelsize=6, pad=-2)
            ax.set_xlabel('X km', fontsize=7, labelpad=-2)
            ax.set_ylabel('Z km', fontsize=7, labelpad=-2)
            ax.set_zlabel('height km', fontsize=7, labelpad=-2)
    exaggeration = 0.35 * ((nx - 1) * spacing) / (high - low)
    fig.suptitle(f'Fixed light and common scale; vertical exaggeration {exaggeration:.2f}×')
    fig.savefig(out / 'oblique.png', dpi=130)
    plt.close(fig)
    fig = plt.figure(figsize=(8, 6), constrained_layout=True)
    ax = fig.add_subplot(111, projection='3d')
    h = arrays['mixed', 'detail'][::stride, ::stride]
    shade = _i3_physical_hillshade(arrays['mixed', 'detail'], spacing)[::stride, ::stride]
    gray = _i3_np.repeat(_i3_np.clip(0.22 + 0.68 * shade, 0, 1)[..., None], 3, axis=2)
    ax.plot_surface(X, Z, h / 1000, facecolors=gray, shade=False, linewidth=0, rcount=h.shape[0], ccount=h.shape[1])
    ax.set_zlim(low / 1000, high / 1000)
    ax.set_box_aspect(((nx - 1) * spacing, (nz - 1) * spacing, high - low))
    ax.view_init(elev=25, azim=-60)
    ax.set_xlabel('X km')
    ax.set_ylabel('Z km')
    ax.set_zlabel('height km')
    ax.set_title('Mixed family, 1:1 physical aspect')
    fig.savefig(out / 'physical_aspect.png', dpi=130)
    plt.close(fig)
    fig, axes = plt.subplots(2, 4, figsize=(16, 7), constrained_layout=True)
    for col, family in enumerate(FAMILIES):
        h = arrays[family, 'base']
        shade = _i3_physical_hillshade(h, spacing)
        axes[0, col].imshow(shade, cmap='gray', vmin=0, vmax=1, extent=extent)
        axes[0, col].set_title(f'{family}: detail off')
        axes[0, col].set_xlabel('X (km)')
        axes[0, col].set_ylabel('Z south (km)')
        axes[1, col].plot((origin[0] + _i3_np.arange(nx) * spacing) / 1000, h[nz // 2], label='detail off')
        axes[1, col].plot((origin[0] + _i3_np.arange(nx) * spacing) / 1000, arrays[family, 'detail'][nz // 2], label='detail on', alpha=0.7)
        axes[1, col].set_ylim(low, high)
        axes[1, col].set_xlabel('X (km)')
        axes[1, col].set_ylabel('Elevation (m)')
        axes[1, col].legend(fontsize=7)
    fig.suptitle('Detail-off relief and central sections, common elevation scale')
    fig.savefig(out / 'sections.png', dpi=130)
    plt.close(fig)
    checks = {}
    for name in ('overview.png', 'oblique.png', 'physical_aspect.png', 'sections.png'):
        with Image.open(out / name) as im:
            a = _i3_np.asarray(im.convert('RGB'))
            checks[name] = {'width_px': im.width, 'height_px': im.height, 'nonblank': bool(_i3_np.ptp(a) > 0), 'sha256': digest(out / name)}
            if not checks[name]['nonblank']:
                raise ValueError(f'blank image: {name}')
    return (checks, [low, high])

# Source: tools.prepare_procedural_mountains
def render_stages(out, stages, origin, spacing):
    import matplotlib.pyplot as plt
    from PIL import Image
    keys = ('base_noise_m', 'advanced_base_m', 'regional_noise_delta_m', 'height_m')
    fig, axes = plt.subplots(4, 4, figsize=(15, 14), constrained_layout=True)
    elevations = [stages[f][k] for f in FAMILIES for k in (keys[0], keys[1], keys[3])]
    low = min((float(a.min()) for a in elevations))
    high = max((float(a.max()) for a in elevations))
    max_delta = max((float(_i3_np.max(_i3_np.abs(stages[f][keys[2]]))) for f in FAMILIES)) or 1.0
    shape = elevations[0].shape
    extent = [origin[0] / 1000, (origin[0] + (shape[1] - 1) * spacing) / 1000, (origin[1] + (shape[0] - 1) * spacing) / 1000, origin[1] / 1000]
    for row, family in enumerate(FAMILIES):
        for col, key in enumerate(keys):
            ax = axes[row, col]
            value = stages[family][key]
            delta = key == keys[2]
            image = ax.imshow(value, extent=extent, cmap='coolwarm' if delta else 'terrain', vmin=-max_delta if delta else low, vmax=max_delta if delta else high)
            ax.set_title(f'{family}: {key}')
            ax.set_xlabel('X km')
            ax.set_ylabel('Z south km')
            fig.colorbar(image, ax=ax, shrink=0.7, label='m')
    fig.suptitle('Actual sampled stages; regional panel is signed height delta')
    fig.savefig(out / 'stages.png', dpi=120)
    plt.close(fig)
    with Image.open(out / 'stages.png') as im:
        a = _i3_np.asarray(im.convert('RGB'))
        check = {'width_px': im.width, 'height_px': im.height, 'nonblank': bool(_i3_np.ptp(a) > 0), 'sha256': digest(out / 'stages.png')}
    if not check['nonblank']:
        raise ValueError('blank stage image')
    return check

# Source: tools.prepare_procedural_mountains
def render_processes(out, arrays):
    import matplotlib.pyplot as plt
    from PIL import Image
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    im = axes[0].imshow(arrays['routed_q_m3_s'], origin='upper', cmap='viridis')
    axes[0].set_title('Diagnostic routed discharge')
    fig.colorbar(im, ax=axes[0], label='m³/s')
    im = axes[1].imshow(arrays['diffusion_delta_m'], origin='upper', cmap='coolwarm')
    axes[1].set_title('Finite diffusion bed delta')
    fig.colorbar(im, ax=axes[1], label='m')
    axes[2].plot(arrays['glacier_source_x_m'], arrays['glacier_before_m'], label='before')
    axes[2].plot(arrays['glacier_source_x_m'], arrays['glacier_after_m'], '--', label='after')
    axes[2].set_title('Nine-cell glacier bed')
    axes[2].set_xlabel('X m')
    axes[2].set_ylabel('Elevation m')
    axes[2].legend()
    fig.suptitle('Finite process diagnostics; unknown boundary; glacier is not a valley simulation')
    fig.savefig(out / 'processes.png', dpi=120)
    plt.close(fig)
    with Image.open(out / 'processes.png') as im:
        a = _i3_np.asarray(im.convert('RGB'))
        return {'width_px': im.width, 'height_px': im.height, 'nonblank': bool(_i3_np.ptp(a) > 0), 'sha256': digest(out / 'processes.png')}

# Source: tools.prepare_procedural_mountains
def generate_procedural(args):
    target = args.output_dir.resolve()
    if target.exists():
        raise FileExistsError(f'output already exists: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = _i3_Path(_i3_tempfile.mkdtemp(prefix=f'.{target.name}-', dir=target.parent))
    try:
        source_hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in (ROOT / 'terrain_pipeline/mountain_forms.py', ROOT / 'terrain_pipeline/mountain_forms.py', ROOT / 'diffusion/geographic_noise.py', ROOT / 'terrain_pipeline/common_infra.py', _i3_Path(__file__).resolve(), ROOT / 'terrain_pipeline/terrain_map_style.py')}
        arrays, records, stages, core_metadata = ({}, [], {}, {})
        for family in FAMILIES:
            for label, strength in [('base', 0.0), ('detail', 0.35)]:
                cfg = _i3_MountainConfig(world_seed=args.world_seed, family=family, detail_strength=strength)
                result = _i3_rasterize(args.origin, (args.size, args.size), args.spacing, cfg)
                height = result['height_m']
                if height.shape != (args.size, args.size) or not _i3_np.isfinite(height).all():
                    raise ValueError('invalid generated height field')
                metadata = {**result['metadata'], 'source_family': 'independent_procedural_mountains', 'source_hashes_sha256': source_hashes, 'origin_m_xz': list(args.origin), 'spacing_m': args.spacing, 'units': 'm', 'shape_zx': list(height.shape)}
                path = stage / f'{family}_{label}.npz'
                stage_keys = ('base_noise_m', 'advanced_base_m', 'regional_noise_delta_m', 'height_m')
                _i3_np.savez_compressed(path, **{key: result[key] for key in stage_keys}, metadata_json=_i3_np.array(_i3_json.dumps(metadata, ensure_ascii=False, allow_nan=False)))
                arrays[family, label] = height
                if label == 'detail':
                    stages[family] = {key: result[key] for key in stage_keys}
                    core_metadata[family] = result['metadata']
                records.append({'file': path.name, 'sha256': digest(path), 'family': family, 'detail_strength': strength, 'min_m': float(height.min()), 'max_m': float(height.max())})
        (checks, limits), render_stats = measured(lambda: render_procedural(stage, arrays, args.origin, args.spacing))
        stage_check, stage_render_stats = measured(lambda: render_stages(stage, stages, args.origin, args.spacing))
        checks['stages.png'] = stage_check
        bench = benchmark_procedural(args.origin, args.spacing, args.benchmark_sizes, args.world_seed)
        bench['rendering'] = {'geometry_figures': render_stats, 'stages_figure': stage_render_stats}
        save_json(stage / 'benchmark.json', bench)
        process_record = None
        if args.with_processes:
            from terrain_pipeline.mountain_forms import prepare_process_evidence
            (process_arrays, process_metadata), process_stats = measured(lambda: prepare_process_evidence(args.origin, args.world_seed))
            _i3_np.savez_compressed(stage / 'processes.npz', **process_arrays)
            save_json(stage / 'processes.json', process_metadata)
            checks['processes.png'], process_render_stats = measured(lambda: render_processes(stage, process_arrays))
            process_record = {'npz': 'processes.npz', 'npz_sha256': digest(stage / 'processes.npz'), 'metadata': 'processes.json', 'metadata_sha256': digest(stage / 'processes.json'), 'timing': process_stats, 'render_timing': process_render_stats, 'source_hashes_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in (ROOT / 'terrain_pipeline/mountain_forms.py', ROOT / 'terrain_pipeline/drainage.py', ROOT / 'terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py', ROOT / 'terrain_pipeline/common_infra.py', ROOT / 'terrain_pipeline/environment_processes.py')}}
        manifest = {'source_family': 'independent_procedural_mountains', 'world_seed': args.world_seed, 'description': 'Generic morphology-inspired geometric candidates; not real peaks, geology simulation, TD terrain, or hydrology.', 'coverage_status': 'complete_in_window', 'origin_m_xz': list(args.origin), 'shape_zx': [args.size, args.size], 'spacing_m': args.spacing, 'view_selection': 'Fixed default origin [0, 0] m, chosen before inspecting heights; custom origin and spacing are explicit.', 'coordinates': 'planar X east, Z south, metres', 'height_units': 'm', 'source_hashes_sha256': source_hashes, 'rasters': records, 'core_metadata_by_family': core_metadata, 'images': checks, 'elevation_scale_m': limits, 'rendering': {'light': [-0.5, -0.5, 2 ** (-0.5)], 'oblique_azimuth_degrees': [-60, 120], 'oblique_elevation_degrees': 25, 'oblique_box_aspect': [1, 1, 0.35], 'oblique_vertical_exaggeration': 0.35 * ((args.size - 1) * args.spacing) / (limits[1] - limits[0]), 'physical_aspect_image': 'physical_aspect.png (1:1:1)', 'surface_stride_samples': max(1, int(_i3_np.ceil(args.size / 160))), 'materials': 'grayscale geometry only for oblique'}, 'benchmark': {'file': 'benchmark.json', 'sha256': digest(stage / 'benchmark.json')}, 'advanced_filter_upstream': {'url': 'https://github.com/lpmitchell/AdvancedTerrainErosion', 'commit': '57e79cc331d17e2a45c897bea9c4c022d1fc5551', 'license': 'MPL-2.0', 'scope': 'pointwise NumPy port; not water or sediment simulation', 'hash_change': 'Default stable integer hash intentionally differs from upstream float Hash2 to avoid far-coordinate collapse; upstream mode remains available for comparison.'}, 'optional_processes': process_record, 'image_check_scope': 'dimensions and nonblank pixels only; morphology requires human review'}
        save_json(stage / 'manifest.json', manifest)
        _i3_os.rename(stage, target)
    finally:
        if stage.exists():
            _i3_shutil.rmtree(stage)
    return target

# Source: tools.prepare_procedural_mountains
def _run_procedural(args, parser):
    if not 3 <= args.size <= 512 or not _i3_np.isfinite(args.spacing) or args.spacing <= 0 or (not _i3_np.isfinite(args.origin).all()):
        parser.error('size must be 3..512, spacing positive and coordinates finite')
    if not args.benchmark_sizes or len(args.benchmark_sizes) > 3 or any((n < 3 or n > 512 for n in args.benchmark_sizes)):
        parser.error('benchmark sizes must contain at most three values in 3..512')
    try:
        print(generate_procedural(args))
    except (ValueError, FileExistsError, OSError) as exc:
        parser.exit(2, f'error: {exc}\n')

# Source: tools.prepare_local_volume_mountains
_i1_sys.path.insert(0, str(ROOT))

# Source: tools.prepare_local_volume_mountains
LOW, HIGH = (-500.0, 6000.0)

# Source: tools.prepare_local_volume_mountains
CASES = [('control', 0.0, 1.0), ('deep_only', 0.0, 2.4), ('local_only', 0.35, 1.0), ('combined', 0.35, 2.4)]

# Source: tools.prepare_local_volume_mountains
def digest(path):
    return _i1_hashlib.sha256(path.read_bytes()).hexdigest()

# Source: tools.prepare_local_volume_mountains
def encode_height(height):
    height = _i1_np.asarray(height, dtype=_i1_np.float64)
    if not _i1_np.isfinite(height).all():
        raise ValueError('height must be finite')
    return _i1_np.rint(_i1_np.clip((height - LOW) / (HIGH - LOW), 0, 1) * 65535).astype(_i1_np.uint16)

# Source: tools.prepare_local_volume_mountains
def decode_height(code):
    return LOW + _i1_np.asarray(code, dtype=_i1_np.float64) * (HIGH - LOW) / 65535

# Source: tools.prepare_local_volume_mountains
def save_height(path, height):
    code = encode_height(height)
    _i1_Image.fromarray(code, mode='I;16').save(path)
    preview = path.with_name(path.stem + '_preview.png')
    _i1_Image.fromarray(_i1_np.rint(code.astype(_i1_np.float64) / 257).astype(_i1_np.uint8), mode='L').save(preview)
    with _i1_Image.open(path) as image:
        actual = _i1_np.asarray(image)
    return {'file': path.name, 'sha256': digest(path), 'preview_sha256': digest(preview), 'min_m': float(_i1_np.min(height)), 'max_m': float(_i1_np.max(height)), 'saturated_below_count': int(_i1_np.count_nonzero(height < LOW)), 'saturated_above_count': int(_i1_np.count_nonzero(height > HIGH)), 'png_matches_encoded': bool(_i1_np.array_equal(actual, code)), 'max_abs_decode_error_m': float(_i1_np.max(_i1_np.abs(decode_height(actual) - height)))}

# Source: tools.prepare_local_volume_mountains
def render_local_volume(path, cases, spacing, origin):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    span = (cases[0][1]['height_m'].shape[0] - 1) * spacing / 1000
    extent = [origin[0] / 1000, (origin[0] + span * 1000) / 1000, (origin[1] + span * 1000) / 1000, origin[1] / 1000]
    fig, axes = plt.subplots(1, len(cases), figsize=(4 * len(cases), 4), squeeze=False, constrained_layout=True)
    for ax, (name, f) in zip(axes[0], cases):
        ax.imshow(f['height_m'], cmap='gray', vmin=LOW, vmax=HIGH, extent=extent)
        ax.set_title(name + ' | elevation (m)')
        ax.set_xlabel('X east (km)')
        ax.set_ylabel('Z south (km)')
    fig.suptitle('Fixed elevation mapping: -500 to 6000 m')
    fig.savefig(path, dpi=140)
    plt.close(fig)
    fig = plt.figure(figsize=(4 * len(cases), 8), constrained_layout=True)
    stride = max(1, int(_i1_np.ceil(cases[0][1]['height_m'].shape[0] / 100)))
    for i, (name, f) in enumerate(cases):
        h = f['height_m']
        ax = fig.add_subplot(2, len(cases), i + 1)
        ax.imshow(_i1_physical_hillshade(h, spacing), cmap='gray', vmin=0, vmax=1, extent=extent)
        ax.set_title(name + ' | hillshade')
        ax.set_xlabel('X east (km)')
        ax.set_ylabel('Z south (km)')
        ax = fig.add_subplot(2, len(cases), len(cases) + i + 1, projection='3d')
        sample = h[::stride, ::stride]
        zz, xx = _i1_np.mgrid[0:h.shape[0]:stride, 0:h.shape[1]:stride] * spacing / 1000
        ax.plot_surface(xx + origin[0] / 1000, zz + origin[1] / 1000, sample / 1000, cmap='gray', vmin=LOW / 1000, vmax=HIGH / 1000, linewidth=0, rcount=sample.shape[0], ccount=sample.shape[1])
        ax.set_zlim(LOW / 1000, HIGH / 1000)
        ax.set_box_aspect((1, 1, 0.35))
        ax.view_init(elev=25, azim=-60)
        ax.set_title(name + ' | bare surface')
        ax.set_xlabel('X km')
        ax.set_ylabel('Z km')
        ax.set_zlabel('height km')
    fig.suptitle(f'Hillshade and bare surface | stride {stride} | vertical exaggeration {0.35 * span / ((HIGH - LOW) / 1000):.2f}x')
    fig.savefig(path.with_name(path.stem + '_terrain.png'), dpi=140)
    plt.close(fig)
    if len(cases) != 4:
        return
    data = dict(cases)
    diffs = [('deep − control', data['deep_only']['height_m'] - data['control']['height_m']), ('local − control', data['local_only']['height_m'] - data['control']['height_m']), ('combined − control', data['combined']['height_m'] - data['control']['height_m'])]
    limit = max(1.0, max((float(_i1_np.max(_i1_np.abs(d))) for _, d in diffs)))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
    for ax, (name, d) in zip(axes, diffs):
        im = ax.imshow(d, cmap='coolwarm', vmin=-limit, vmax=limit, extent=extent)
        ax.set_title(name + ' | actual height difference (m)')
        ax.set_xlabel('X east (km)')
        ax.set_ylabel('Z south (km)')
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.savefig(path.with_name(path.stem + '_differences.png'), dpi=140)
    plt.close(fig)
    indices = _i1_np.arange(cases[0][1]['height_m'].shape[0]) * spacing
    selected = (indices >= 9000) & (indices <= 15000)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), constrained_layout=True)
    for i, (name, f) in enumerate(cases):
        local = f['height_m'][_i1_np.ix_(selected, selected)]
        axes[0, i].imshow(local, cmap='gray', vmin=LOW, vmax=HIGH, extent=[9, 15, 15, 9])
        axes[0, i].set_title(name + ' | 9–15 km')
        axes[0, i].set_xlabel('X km')
        axes[0, i].set_ylabel('Z km')
        axes[1, i].plot(indices[selected] / 1000, f['height_m'][_i1_np.argmin(abs(indices - 12000)), selected])
        axes[1, i].set_title(name + ' | Z = 12 km')
        axes[1, i].set_xlabel('X km')
        axes[1, i].set_ylabel('height m')
        axes[1, i].set_ylim(LOW, HIGH)
        axes[1, i].grid(True)
    fig.savefig(path.with_name(path.stem + '_local_profiles.png'), dpi=140)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4), constrained_layout=True)
    row = _i1_np.argmin(abs(indices - 12000))
    for label, changed, baseline in [('deep − control', 'deep_only', 'control'), ('combined − local', 'combined', 'local_only')]:
        difference = data[changed]['height_m'][row, selected] - data[baseline]['height_m'][row, selected]
        ax.plot(indices[selected] / 1000, difference, label=label)
    ax.axhline(0, color='black', linewidth=0.7)
    ax.set_title('Actual depth-gain difference | Z = 12 km')
    ax.set_xlabel('X east (km)')
    ax.set_ylabel('height difference (m)')
    ax.grid(True)
    ax.legend()
    fig.savefig(path.with_name(path.stem + '_depth_profile.png'), dpi=140)
    plt.close(fig)

# Source: tools.prepare_local_volume_mountains
def generate_local_volume(output, size=121, spacing=200.0, benchmark=False):
    target = _i1_Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    if size < 2 or not _i1_np.isfinite(spacing) or spacing <= 0:
        raise ValueError('invalid grid')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = _i1_Path(_i1_tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        sources = ['terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/common_infra.py', 'diffusion/geographic_noise.py', 'terrain_pipeline/terrain_map_style.py', 'tools/prepare_mountain_forms.py']
        manifest = {'algorithm_id': _i1_LOCAL_VOLUME_ALGORITHM_ID, 'original_algorithm_id': _i1_ORIGINAL_ID, 'world_seed': 20260903, 'source_sha256': {p: digest(ROOT / p) for p in sources}, 'subseed_derivation': 'terrain_pipeline.world_seed.derive_subseed', 'subseeds': {purpose: _i1_derive_subseed(20260903, purpose) for purpose in ('product-ridge', 'product-warp', 'product-voronoi-sites', 'local-volume-sites', 'local-volume-selection')}, 'advanced_filter': {'algorithm_id': _i1_ADVANCED_ID, 'config': _i1_asdict(_i1_AdvancedFilterConfig(amplitude_m=150.0, wavelength_m=1800.0, octaves=3)), 'stable_seed': int.from_bytes(_i1_hashlib.sha256(b'advanced-terrain-filter-v1:20260903:phacelle').digest()[:8], 'little')}, 'coordinate_convention': 'row Z south, column X east; origin + index * spacing, metres', 'mapping': {'minimum_m': LOW, 'maximum_m': HIGH, 'encoding': 'round(clip((height+500)/6500,0,1)*65535)', 'legacy_mapping': 'previous product images use -500 to 4500 m'}, 'formulas': {'original_macro': 'product-mountains-v2-smooth-mass, default alpha=0.65, Advanced disabled', 'local_macro': 'H0 + k * P * max(H0 - 200 m, 0)', 'fade': 'smoothstep(0.02, 0.08, hypot(slope_x, slope_z))', 'actual_advanced_delta': 'fade * (raw_delta * depth_gain if raw_delta < 0 else raw_delta)', 'control': 'k=0, gain=1, with slope fade; not the old un-faded product baseline', 'boundary': 'P=0 guarantees macro equality only; Advanced neighborhood up to 600 m can change final heights near patch edges'}, 'plot_geometry': {'surface_stride': max(1, int(_i1_np.ceil(size / 100))), 'surface_rcount_ccount': 'actual strided array dimensions', 'vertical_exaggeration': 0.35 * (size - 1) * spacing / (HIGH - LOW)}, 'cases': [], 'images': {}, 'benchmark': [], 'timings_seconds': {'generation': 0.0, 'save': 0.0, 'plot': 0.0}}
        for window, origin, choices in [('main', (0.0, 0.0), CASES), ('negative', (-24000.0, -24000.0), [CASES[-1]])]:
            cases = []
            x, z = _i1_np.meshgrid(origin[0] + _i1_np.arange(size) * spacing, origin[1] + _i1_np.arange(size) * spacing)
            for name, k, gain in choices:
                config = _i1_LocalVolumeConfig(k=k, depth_gain=gain)
                start = _i1_time.perf_counter()
                fields = _i1_sample_local_volume_mountains(x, z, config)
                manifest['timings_seconds']['generation'] += _i1_time.perf_counter() - start
                start = _i1_time.perf_counter()
                npz = stage / f'{window}_{name}.npz'
                _i1_np.savez_compressed(npz, **{key: _i1_np.asarray(value, dtype=_i1_np.float64) for key, value in fields.items()})
                outside = fields['selection_w'] == 0
                item = {'name': f'{window}_{name}', 'origin_xz_m': origin, 'shape_zx': [size, size], 'spacing_m': spacing, 'config': _i1_asdict(config), 'npz': npz.name, 'npz_sha256': digest(npz), 'selection_support_fraction': float(_i1_np.mean(~outside)), 'p_support_fraction': float(_i1_np.mean(fields['p'] > 0)), 'outside_selection_macro_max_abs_error_m': float(_i1_np.max(_i1_np.abs(fields['macro_height_m'][outside] - fields['h0_m'][outside]))) if _i1_np.any(outside) else None, 'outside_patch_macro_max_abs_error_m': float(_i1_np.max(_i1_np.abs(fields['macro_height_m'][fields['p'] == 0] - fields['h0_m'][fields['p'] == 0]))) if _i1_np.any(fields['p'] == 0) else None, 'max_volume_lift_m': float(_i1_np.max(fields['volume_delta_m'])), 'raw_delta_min_m': float(_i1_np.min(fields['raw_advanced_delta_m'])), 'raw_delta_max_m': float(_i1_np.max(fields['raw_advanced_delta_m'])), 'final_delta_min_m': float(_i1_np.min(fields['final_delta_m'])), 'final_delta_max_m': float(_i1_np.max(fields['final_delta_m'])), 'height_images': {key: save_height(stage / f'{window}_{name}_{key}.png', fields[key]) for key in ('macro_height_m', 'height_m')}}
                manifest['cases'].append(item)
                manifest['timings_seconds']['save'] += _i1_time.perf_counter() - start
                cases.append((name, fields))
            start = _i1_time.perf_counter()
            path = stage / f'{window}_comparison.png'
            render_local_volume(path, cases, spacing, origin)
            manifest['timings_seconds']['plot'] += _i1_time.perf_counter() - start
            for p in stage.glob(f'{window}_comparison*.png'):
                manifest['images'][p.name] = digest(p)
        if benchmark:
            for name, origin in [('near', (0.0, 0.0)), ('far', (500000000.0, -500000000.0))]:
                x, z = _i1_np.meshgrid(origin[0] + _i1_np.arange(512) * 60, origin[1] + _i1_np.arange(512) * 60)
                _, stats = measured(lambda: _i1_sample_local_volume_mountains(x, z, _i1_LocalVolumeConfig()))
                manifest['benchmark'].append({'location': name, 'origin_xz_m': origin, 'shape_zx': [512, 512], 'spacing_m': 60, **stats})
            manifest['benchmark_scope'] = 'measured: wall time, tracemalloc and sampled whole-process RSS; peaks may be missed'
        (stage / 'README.md').write_text(f'# 局部站点体量与深沟壑\n\n来源 `{_i1_LOCAL_VOLUME_ALGORITHM_ID}`，原宏观 `{_i1_ORIGINAL_ID}`（默认 alpha=0.65，关闭 Advanced）；世界种子 20260903。详细来源、参数、子种子、量化和计时见 manifest.json。control 已使用坡度淡入，不能视为上一轮未淡入的基准。\n\n网格 {size} × {size}，间距 {spacing:g} 米。行 Z 向南、列 X 向东；主窗原点 (0,0)，负窗原点 (-24000,-24000) 米。P=0 的体量区外宏观不变，但 Advanced 使用 600 米邻域，区外边缘的最终高程仍可能改变。\n\n16 位单通道原始高程及 8 位预览统一固定 -500 至 6000 米、黑低白高，与旧图的 -500 至 4500 米映射不同。NPZ 字段为 float64。阴影及裸山图仅用于观察；Advanced 是外观雕刻，不是水沙侵蚀。\n', encoding='utf-8')
        (stage / 'manifest.json').write_text(_i1_json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        _i1_os.rename(stage, target)
    except BaseException:
        _i1_shutil.rmtree(stage, ignore_errors=True)
        raise
    return target

# Source: tools.prepare_local_volume_mountains
def _run_local_volume(args, parser):
    print(generate_local_volume(args.output, args.size, args.spacing, args.benchmark))

# Source: tools.prepare_skeleton_mountains
ROOT = _i0_Path(__file__).resolve().parents[1]

# Source: tools.prepare_skeleton_mountains
_i0_sys.path.insert(0, str(ROOT))

# Source: tools.prepare_skeleton_mountains
def cases_skeleton():
    return [('previous', _i0_LocalVolumeConfig()), ('skeleton_bare', _i0_SkeletonMountainConfig(base_relief_m=0, detail_amplitude_m=0, advanced_enabled=False))] + [(p, _i0_SkeletonMountainConfig(profile=p)) for p in ('granite', 'alpine', 'asymmetric', 'mixed')]

# Source: tools.prepare_skeleton_mountains
def sample_skeleton(config, x, z):
    if isinstance(config, _i0_LocalVolumeConfig):
        return _i0_sample_local_volume_mountains(x, z, config)
    return _i0_sample_skeleton_mountains(x, z, config)

# Source: tools.prepare_skeleton_mountains
def plot_results_skeleton(directory, window, data, spacing, origin):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    size = next(iter(data.values()))['height_m'].shape[0]
    span = (size - 1) * spacing
    extent = [origin[0] / 1000, (origin[0] + span) / 1000, (origin[1] + span) / 1000, origin[1] / 1000]
    names = list(data)
    cols = 3 if len(names) > 1 else 1
    rows = _i0_math.ceil(len(names) / cols)
    for kind in ('gray', 'hillshade'):
        fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4.7 * rows), squeeze=False, constrained_layout=True)
        for ax, name in zip(axes.flat, names):
            h = data[name]['height_m']
            values, low, high = (h, LOW, HIGH) if kind == 'gray' else (_i0_physical_hillshade(h, spacing), 0, 1)
            ax.imshow(values, cmap='gray', vmin=low, vmax=high, extent=extent)
            ax.set_title(name)
            ax.set_xlabel('X east (km)')
            ax.set_ylabel('Z south (km)')
        for ax in list(axes.flat)[len(names):]:
            ax.set_visible(False)
        fig.suptitle(f'{window}: real sampled heights | ' + ('fixed -500 to 6000 m' if kind == 'gray' else 'same physical hillshade'))
        fig.savefig(directory / f'{window}_{kind}_comparison.png', dpi=130)
        plt.close(fig)
    show = [n for n in ('granite', 'alpine', 'asymmetric', 'mixed') if n in data]
    if not show:
        show = names
    stride = max(1, _i0_math.ceil(size / 140))
    fig = plt.figure(figsize=(5 * len(show), 9), constrained_layout=True)
    for row, azimuth in enumerate((-60, 125)):
        for i, name in enumerate(show):
            ax = fig.add_subplot(2, len(show), row * len(show) + i + 1, projection='3d')
            h = data[name]['height_m'][::stride, ::stride] / 1000
            zz, xx = _i0_np.mgrid[0:size:stride, 0:size:stride] * spacing / 1000
            ax.plot_surface(xx + origin[0] / 1000, zz + origin[1] / 1000, h, cmap='gray', vmin=LOW / 1000, vmax=HIGH / 1000, linewidth=0, rcount=h.shape[0], ccount=h.shape[1])
            ax.set_zlim(LOW / 1000, HIGH / 1000)
            ax.set_box_aspect((span / 1000, span / 1000, (HIGH - LOW) / 1000))
            ax.view_init(elev=30, azim=azimuth)
            ax.set_title(f'{name} | azimuth {azimuth}')
            ax.set_xlabel('X km')
            ax.set_ylabel('Z km')
            ax.set_zlabel('height km')
    fig.suptitle(f'Bare geometry | vertical exaggeration 1.00x | stride {stride} ({stride * spacing:g} m display samples)')
    fig.savefig(directory / f'{window}_bare_views.png', dpi=130)
    plt.close(fig)
    if window == 'main':
        peak = _i0_describe_skeleton(0, 0)
        world_x = origin[0] + _i0_np.arange(size) * spacing
        world_z = origin[1] + _i0_np.arange(size) * spacing
        ix = _i0_np.flatnonzero(_i0_np.abs(world_x - peak['peak_x_m']) <= 4500.0)
        iz = _i0_np.flatnonzero(_i0_np.abs(world_z - peak['peak_z_m']) <= 4500.0)
        if len(ix) > 1 and len(iz) > 1:
            fig = plt.figure(figsize=(5 * len(show), 9), constrained_layout=True)
            crop_stride = max(1, _i0_math.ceil(max(len(ix), len(iz)) / 100))
            ix, iz = (ix[::crop_stride], iz[::crop_stride])
            xx, zz = _i0_np.meshgrid(world_x[ix] / 1000, world_z[iz] / 1000)
            for i, name in enumerate(show):
                h = data[name]['skeleton_height_m'][_i0_np.ix_(iz, ix)]
                ax = fig.add_subplot(2, len(show), i + 1)
                ax.imshow(_i0_physical_hillshade(h, spacing * crop_stride), cmap='gray', vmin=0, vmax=1, extent=[world_x[ix[0]] / 1000, world_x[ix[-1]] / 1000, world_z[iz[-1]] / 1000, world_z[iz[0]] / 1000])
                ax.set_title(name + ' | no detail / Advanced')
                ax.set_xlabel('X km')
                ax.set_ylabel('Z km')
                ax = fig.add_subplot(2, len(show), len(show) + i + 1, projection='3d')
                ax.plot_surface(xx, zz, h / 1000, cmap='gray', vmin=LOW / 1000, vmax=HIGH / 1000, linewidth=0, rcount=h.shape[0], ccount=h.shape[1])
                ax.set_zlim(LOW / 1000, HIGH / 1000)
                ax.set_box_aspect(((world_x[ix[-1]] - world_x[ix[0]]) / 1000, (world_z[iz[-1]] - world_z[iz[0]]) / 1000, (HIGH - LOW) / 1000))
                ax.view_init(elev=24, azim=-60)
                ax.set_title(name)
                ax.set_xlabel('X km')
                ax.set_ylabel('Z km')
                ax.set_zlabel('height km')
            fig.suptitle(f'Shared peak crop +/-4.5 km | skeleton + common background only | 1.00x vertical | display step {crop_stride * spacing:g} m')
            fig.savefig(directory / 'main_peak_macro_views.png', dpi=130)
            plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 8), constrained_layout=True)
    h = data['mixed']['height_m']
    ax.imshow(_i0_physical_hillshade(h, spacing), cmap='gray', vmin=0, vmax=1, extent=extent)
    c = _i0_SkeletonMountainConfig()
    sources = []
    lo = _i0_np.floor(_i0_np.asarray(origin) / c.cell_size_m).astype(int) - 1
    hi = _i0_np.floor((_i0_np.asarray(origin) + span) / c.cell_size_m).astype(int) + 1
    for cz in range(lo[1], hi[1] + 1):
        for cx in range(lo[0], hi[0] + 1):
            source = _i0_describe_skeleton(cx, cz, c)
            sources.append(source)
            ax.scatter(source['peak_x_m'] / 1000, source['peak_z_m'] / 1000, marker='^', c='red', s=25)
            for curve in source['curves']:
                t = _i0_np.linspace(0, 1, 65)
                u, v = (t * curve['length_m'], curve['bend_m'] * _i0_np.sin(_i0_np.pi * t) ** 2)
                co, si = (_i0_math.cos(curve['angle_rad']), _i0_math.sin(curve['angle_rad']))
                x = curve['start_x_m'] + co * u - si * v
                z = curve['start_z_m'] + si * u + co * v
                ax.plot(x / 1000, z / 1000, color='orange' if curve['level'] == 1 else 'cyan', linewidth=1.2)
    ax.set_xlim(extent[:2])
    ax.set_ylim(extent[2:])
    ax.set_xlabel('X east (km)')
    ax.set_ylabel('Z south (km)')
    ax.set_title('Procedural skeleton: red peak, orange primary, cyan secondary (not rivers)')
    fig.savefig(directory / f'{window}_skeleton_overlay.png', dpi=140)
    plt.close(fig)
    (directory / f'{window}_skeleton.json').write_text(_i0_json.dumps(sources, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

# Source: tools.prepare_skeleton_mountains
def plot_sections(directory):
    import matplotlib.pyplot as plt
    source = _i0_describe_skeleton(0, 0)
    parent = source['curves'][0]
    co, si = (_i0_math.cos(parent['angle_rad']), _i0_math.sin(parent['angle_rad']))
    distance = _i0_np.linspace(-6000, 6000, 401)
    saved = {'distance_m': distance}
    fig, axes = plt.subplots(1, 2, figsize=(15, 5), constrained_layout=True)
    for ax, t, label in zip(axes, (0.0, 0.38), ('through primary peak', 'across primary shoulder')):
        u, v = (t * parent['length_m'], parent['bend_m'] * _i0_math.sin(_i0_np.pi * t) ** 2)
        px = parent['start_x_m'] + co * u - si * v
        pz = parent['start_z_m'] + si * u + co * v
        x, z = (px - si * distance, pz + co * distance)
        prefix = 'peak' if t == 0 else 'shoulder'
        saved[prefix + '_x_m'], saved[prefix + '_z_m'] = (x, z)
        for name, c in cases_skeleton():
            fields = sample_skeleton(c, x, z)
            for key in ('height_m', 'macro_height_m'):
                saved[f'{prefix}_{name}_{key}'] = fields[key]
            if name != 'skeleton_bare':
                ax.plot(distance / 1000, fields['height_m'], label=name, linewidth=1.2)
        ax.set_title(label + f' | centre ({px:.1f}, {pz:.1f}) m')
        ax.set_xlabel('nominal cross-ridge distance (km)')
        ax.set_ylabel('sampled height (m)')
        ax.set_ylim(LOW, HIGH)
        ax.grid(True)
        ax.legend()
    fig.suptitle('Exact world-coordinate sections; no interpolation from image pixels')
    fig.savefig(directory / 'main_peak_sections.png', dpi=140)
    plt.close(fig)
    _i0_np.savez_compressed(directory / 'sections.npz', **saved)

# Source: tools.prepare_skeleton_mountains
def generate_skeleton(output, size=121, spacing=200.0, benchmark=False):
    target = _i0_Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    if isinstance(size, bool) or not isinstance(size, int) or size < 2 or (size > 1024) or (not _i0_np.isfinite(spacing)) or (spacing <= 0):
        raise ValueError('invalid grid')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = _i0_Path(_i0_tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        sources = ['terrain_pipeline/skeleton_mountains.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/common_infra.py', 'diffusion/geographic_noise.py', 'terrain_pipeline/terrain_map_style.py', 'tools/prepare_mountain_forms.py', 'tools/prepare_mountain_forms.py', 'tools/prepare_mountain_forms.py']
        manifest = {'algorithm_id': _i0_ALGORITHM_ID, 'world_seed': _i0_WORLD_SEED, 'source_sha256': {p: digest(ROOT / p) for p in sources}, 'subseed_derivation': 'terrain_pipeline.world_seed.derive_subseed', 'subseeds': {p: _i0_derive_subseed(_i0_WORLD_SEED, p) for p in _i0_PURPOSES + ('product-ridge', 'product-warp', 'product-voronoi-sites', 'local-volume-sites', 'local-volume-selection')}, 'advanced_filter': {'algorithm_id': _i0_advanced.ADVANCED_ALGORITHM_ID, 'stable_seed': int.from_bytes(_i0_hashlib.sha256(f'advanced-terrain-filter-v1:{_i0_WORLD_SEED}:phacelle'.encode('ascii')).digest()[:8], 'little'), 'config': _i0_asdict(_i0_advanced.AdvancedFilterConfig(amplitude_m=150.0, wavelength_m=1800.0, octaves=3))}, 'mapping': {'minimum_m': LOW, 'maximum_m': HIGH, 'encoding': 'round(clip((h+500)/6500,0,1)*65535)'}, 'coordinate_convention': 'row Z south, column X east; origin + index * spacing; metres', 'dependencies': {'macro_neighbor_cells': '3x3', 'source_support_cells': _i0_SOURCE_SUPPORT_CELLS, 'hierarchy_levels': 2, 'curves_per_source': 6, 'curve_distance': 'analytic nominal-frame lateral offset; not exact Euclidean distance', 'sample_halo_m': _i0_HALO_M, 'cache_capacity_descriptors': _i0_CACHE_CAPACITY, 'cache_scope': 'per invocation, discarded'}, 'plot_geometry': {'stride': max(1, _i0_math.ceil(size / 140)), 'vertical_exaggeration': 1.0}, 'stages': {'base_height_m': 'product v2 macro, base=200 m / amplitude=600 m / alpha=.65; bare case uses flat 200 m', 'skeleton_height_m': 'base plus source/curve contraharmonic soft union; no detail or Advanced', 'macro_height_m': 'skeleton plus 45 m amplitude noise scaled by skeleton uplift/4700', 'final_delta_m': 'slope fade(.02,.08) * skeleton uplift fade(0,1000 m) * negative-only gain2.4', 'skeleton_bare': 'mixed geometry; base relief, detail and Advanced all off; not the previous baseline'}, 'environment': {'python': _i0_sys.version, 'numpy': _i0_np.__version__, 'platform': _i0_platform.platform(), 'processor': _i0_platform.processor()}, 'cases': [], 'benchmark': [], 'timings_seconds': {'generation': 0.0, 'save': 0.0, 'plot': 0.0}}
        for window, origin, choices in (('main', (0.0, 0.0), cases_skeleton()), ('negative', (-24000.0, -24000.0), [('mixed', _i0_SkeletonMountainConfig())])):
            x, z = _i0_np.meshgrid(origin[0] + _i0_np.arange(size) * spacing, origin[1] + _i0_np.arange(size) * spacing)
            data = {}
            for name, config in choices:
                begin = _i0_time.perf_counter()
                f = sample_skeleton(config, x, z)
                manifest['timings_seconds']['generation'] += _i0_time.perf_counter() - begin
                begin = _i0_time.perf_counter()
                npz = stage / f'{window}_{name}.npz'
                _i0_np.savez_compressed(npz, **f)
                item = {'name': f'{window}_{name}', 'algorithm_id': 'local-volume-mountains-v1' if name == 'previous' else _i0_ALGORITHM_ID, 'config': _i0_asdict(config), 'shape_zx': [size, size], 'spacing_m': spacing, 'origin_xz_m': list(origin), 'npz': npz.name, 'npz_sha256': digest(npz), 'height_images': {key: save_height(stage / f'{window}_{name}_{key}.png', f[key]) for key in ('macro_height_m', 'height_m')}, 'max_abs_detail_m': float(_i0_np.max(_i0_np.abs(f.get('detail_delta_m', _i0_np.zeros(1))))), 'final_delta_range_m': [float(f['final_delta_m'].min()), float(f['final_delta_m'].max())]}
                manifest['cases'].append(item)
                manifest['timings_seconds']['save'] += _i0_time.perf_counter() - begin
                data[name] = f
            begin = _i0_time.perf_counter()
            plot_results_skeleton(stage, window, data, spacing, origin)
            manifest['timings_seconds']['plot'] += _i0_time.perf_counter() - begin
        begin = _i0_time.perf_counter()
        plot_sections(stage)
        manifest['timings_seconds']['plot'] += _i0_time.perf_counter() - begin
        if benchmark:
            for location, origin in (('near', (0.0, 0.0)), ('far', (500000000.0, -500000000.0))):
                x, z = _i0_np.meshgrid(origin[0] + _i0_np.arange(512) * 60.0, origin[1] + _i0_np.arange(512) * 60.0)
                _, stats = measured(lambda: _i0_sample_skeleton_mountains(x, z))
                manifest['benchmark'].append({'location': location, 'origin_xz_m': list(origin), 'shape_zx': [512, 512], 'spacing_m': 60.0, **stats})
            manifest['benchmark_scope'] = 'wall time with tracemalloc; sampled whole-process RSS every 10ms can miss peaks; includes process baseline, excludes interpreter startup'
        manifest['files_sha256'] = {p.name: digest(p) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage / 'manifest.json').write_text(_i0_json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        _i0_os.rename(stage, target)
    except BaseException:
        if stage.parent != target.parent or not stage.name.startswith('.' + target.name + '-'):
            raise RuntimeError('unexpected staging path')
        _i0_shutil.rmtree(stage)
        raise
    return target

# Source: tools.prepare_skeleton_mountains
def _run_skeleton(args, parser):
    print(generate_skeleton(args.output, args.size, args.spacing, args.benchmark))

# Source: tools.prepare_product_mountains
_i2_sys.path.insert(0, str(ROOT))

# Source: tools.prepare_product_mountains
PREPARE_PRODUCT_MOUNTAINS_LOW, PREPARE_PRODUCT_MOUNTAINS_HIGH = (-500.0, 4500.0)

# Source: tools.prepare_product_mountains
WINDOWS = {'main': (0.0, 0.0), 'negative': (-24000.0, -24000.0)}

# Source: tools.prepare_product_mountains
def prepare_product_mountains_encode_height(height):
    height = _i2_np.asarray(height, dtype=_i2_np.float64)
    if not _i2_np.isfinite(height).all():
        raise ValueError('height must be finite')
    return _i2_np.rint(_i2_np.clip((height - PREPARE_PRODUCT_MOUNTAINS_LOW) / (PREPARE_PRODUCT_MOUNTAINS_HIGH - PREPARE_PRODUCT_MOUNTAINS_LOW), 0, 1) * 65535).astype(_i2_np.uint16)

# Source: tools.prepare_product_mountains
def prepare_product_mountains_decode_height(encoded):
    return PREPARE_PRODUCT_MOUNTAINS_LOW + _i2_np.asarray(encoded, dtype=_i2_np.float64) * ((PREPARE_PRODUCT_MOUNTAINS_HIGH - PREPARE_PRODUCT_MOUNTAINS_LOW) / 65535)

# Source: tools.prepare_product_mountains
def prepare_product_mountains_save_height(path, height):
    encoded = prepare_product_mountains_encode_height(height)
    _i2_Image.fromarray(encoded, mode='I;16').save(path)
    _i2_Image.fromarray(_i2_np.rint(encoded.astype(_i2_np.float64) / 257).astype(_i2_np.uint8), mode='L').save(path.with_name(path.stem + '_preview.png'))
    error = prepare_product_mountains_decode_height(encoded) - height
    return {'min_m': float(_i2_np.min(height)), 'max_m': float(_i2_np.max(height)), 'saturated_below_count': int(_i2_np.count_nonzero(height < PREPARE_PRODUCT_MOUNTAINS_LOW)), 'saturated_above_count': int(_i2_np.count_nonzero(height > PREPARE_PRODUCT_MOUNTAINS_HIGH)), 'max_abs_decode_error_m': float(_i2_np.max(_i2_np.abs(error))), 'sha256': digest(path), 'preview_sha256': digest(path.with_name(path.stem + '_preview.png'))}

# Source: tools.prepare_product_mountains
def render_product(path, cases, spacing):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(cases), 5, figsize=(16, 3.3 * len(cases)), squeeze=False, constrained_layout=True)
    for row, (name, fields) in enumerate(cases):
        for col, (key, label, lo, hi, cmap) in enumerate([('ridge', 'R [0,1]', 0, 1, 'gray'), ('volume', 'V [0,1]', 0, 1, 'gray'), ('macro_height_m', 'Macro (m)', PREPARE_PRODUCT_MOUNTAINS_LOW, PREPARE_PRODUCT_MOUNTAINS_HIGH, 'gray'), ('height_m', 'Advanced (m)', PREPARE_PRODUCT_MOUNTAINS_LOW, PREPARE_PRODUCT_MOUNTAINS_HIGH, 'gray'), ('delta_m', 'delta (m)', -262.5, 262.5, 'coolwarm')]):
            im = axes[row, col].imshow(fields[key], cmap=cmap, vmin=lo, vmax=hi)
            axes[row, col].set_title('alpha=' + name.split('_')[-1] + ' | ' + label, fontsize=9)
            axes[row, col].axis('off')
            fig.colorbar(im, ax=axes[row, col], shrink=0.7)
    span_km = (cases[0][1]['height_m'].shape[0] - 1) * spacing / 1000
    fig.suptitle(f'Product mountains | {span_km:g} x {span_km:g} km | X east, Z south | elevation -500 to 4500 m')
    fig.savefig(path, dpi=130)
    plt.close(fig)
    fig, axes = plt.subplots(2, len(cases), figsize=(4 * len(cases), 8), squeeze=False, constrained_layout=True)
    for col, (name, fields) in enumerate(cases):
        h = fields['height_m']
        axes[0, col].imshow(_i2_physical_hillshade(h, spacing), cmap='gray', vmin=0, vmax=1)
        axes[0, col].set_title('alpha=' + name.split('_')[-1] + ' hillshade')
        axes[0, col].axis('off')
        ax = fig.add_subplot(2, len(cases), len(cases) + col + 1, projection='3d')
        axes[1, col].remove()
        stride = max(1, int(_i2_np.ceil(h.shape[0] / 100)))
        zz, xx = _i2_np.mgrid[0:h.shape[0]:stride, 0:h.shape[1]:stride] * spacing / 1000
        sample = h[::stride, ::stride]
        ax.plot_surface(xx, zz, sample / 1000, cmap='gray', vmin=PREPARE_PRODUCT_MOUNTAINS_LOW / 1000, vmax=PREPARE_PRODUCT_MOUNTAINS_HIGH / 1000, linewidth=0, rcount=sample.shape[0], ccount=sample.shape[1])
        ax.set_zlim(PREPARE_PRODUCT_MOUNTAINS_LOW / 1000, PREPARE_PRODUCT_MOUNTAINS_HIGH / 1000)
        ax.set_box_aspect((1, 1, 0.35))
        ax.view_init(elev=25, azim=-60)
        ax.set_title('alpha=' + name.split('_')[-1] + ' bare terrain')
    exaggeration = 0.35 * span_km / ((PREPARE_PRODUCT_MOUNTAINS_HIGH - PREPARE_PRODUCT_MOUNTAINS_LOW) / 1000)
    fig.suptitle(f'Product mountains | {span_km:g} x {span_km:g} km | X east, Z south | vertical exaggeration {exaggeration:.2f}x')
    fig.savefig(path.with_name(path.stem + '_terrain.png'), dpi=130)
    plt.close(fig)

# Source: tools.prepare_product_mountains
def generate_product(output, size=121, spacing=200.0, benchmark=False):
    target = _i2_Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    if size < 2 or not _i2_np.isfinite(spacing) or spacing <= 0:
        raise ValueError('invalid grid')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = _i2_Path(_i2_tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        source_files = ['terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/terrain_map_style.py', 'diffusion/geographic_noise.py', 'terrain_pipeline/common_infra.py', 'tools/prepare_mountain_forms.py']
        manifest = {'algorithm_id': _i2_PRODUCT_ALGORITHM_ID, 'world_seed': 20260903, 'source_sha256': {p: digest(ROOT / p) for p in source_files}, 'subseeds': {purpose: _i2_derive_subseed(20260903, purpose) for purpose in ('product-ridge', 'product-warp', 'product-voronoi-sites')}, 'subseed_derivation': 'terrain_pipeline.world_seed.derive_subseed', 'advanced_filter': {'algorithm_id': _i2_ADVANCED_ID, 'config': _i2_asdict(_i2_AdvancedFilterConfig(amplitude_m=150.0, wavelength_m=1800.0, octaves=3)), 'stable_seed': int.from_bytes(_i2_hashlib.sha256(b'advanced-terrain-filter-v1:20260903:phacelle').digest()[:8], 'little'), 'stable_seed_derivation': 'SHA256 UTF-8 advanced-terrain-filter-v1:20260903:phacelle, first 8 bytes little-endian uint64'}, 'macro_formula': 'base_m + amplitude_m * ridge ** ridge_power * ((1-alpha) + alpha * volume)', 'ridge_formula': 'clip(1 - (sqrt(n*n + eps*eps) - eps) / (sqrt(1 + eps*eps) - eps), 0, 1); eps=ridge_smoothing', 'volume_formula': '1 - product(1 - exp(-2.2*d*d)*cutoff(d)) over 3x3 sites; cutoff=1-smoothstep(1,1.25,d)', 'coordinate_convention': 'row Z south, column X east; metres; samples at origin + index * spacing', 'mapping': {'minimum_m': PREPARE_PRODUCT_MOUNTAINS_LOW, 'maximum_m': PREPARE_PRODUCT_MOUNTAINS_HIGH, 'encode': 'round(clip((height_m+500)/5000,0,1)*65535)', 'decode': '-500 + code * 5000 / 65535', 'rounding': 'nearest, ties to even'}, 'plot_geometry': {'surface_stride': max(1, int(_i2_np.ceil(size / 100))), 'surface_vertical_exaggeration': 0.35 * ((size - 1) * spacing) / (PREPARE_PRODUCT_MOUNTAINS_HIGH - PREPARE_PRODUCT_MOUNTAINS_LOW), 'delta_color_limits_m': [-262.5, 262.5]}, 'cases': [], 'images': {}, 'benchmark': [], 'timings_seconds': {'generation': 0.0, 'save': 0.0, 'plot': 0.0}}
        for window, origin in WINDOWS.items():
            cases = []
            for alpha in (0.0, 0.65, 1.0) if window == 'main' else (0.65,):
                config = _i2_ProductMountainConfig(world_seed=20260903, alpha=alpha, advanced_enabled=True, batch_size=4096)
                x, z = _i2_np.meshgrid(origin[0] + _i2_np.arange(size) * spacing, origin[1] + _i2_np.arange(size) * spacing)
                start = _i2_time.perf_counter()
                fields = _i2_sample_product_mountains(x, z, config)
                manifest['timings_seconds']['generation'] += _i2_time.perf_counter() - start
                name = f'{window}_alpha_{alpha:g}'
                start = _i2_time.perf_counter()
                npz = stage / (name + '.npz')
                _i2_np.savez_compressed(npz, **{k: _i2_np.asarray(v, dtype=_i2_np.float64) for k, v in fields.items()})
                item = {'name': name, 'origin_xz_m': origin, 'shape_zx': [size, size], 'spacing_m': spacing, 'config': _i2_asdict(config), 'npz': npz.name, 'npz_sha256': digest(npz), 'height_images': {}}
                for key in ('macro_height_m', 'height_m'):
                    image_path = stage / (name + '_' + key + '.png')
                    item['height_images'][key] = {'file': image_path.name, **prepare_product_mountains_save_height(image_path, fields[key])}
                manifest['cases'].append(item)
                manifest['timings_seconds']['save'] += _i2_time.perf_counter() - start
                cases.append((name, fields))
            start = _i2_time.perf_counter()
            path = stage / (window + '_comparison.png')
            render_product(path, cases, spacing)
            manifest['timings_seconds']['plot'] += _i2_time.perf_counter() - start
            for p in (path, path.with_name(path.stem + '_terrain.png')):
                manifest['images'][p.name] = digest(p)
        if benchmark:
            for name, origin in [('near', (0.0, 0.0)), ('far', (500000000.0, -500000000.0))]:
                x, z = _i2_np.meshgrid(origin[0] + _i2_np.arange(512) * 60, origin[1] + _i2_np.arange(512) * 60)
                _, stats = measured(lambda: _i2_sample_product_mountains(x, z, _i2_ProductMountainConfig()))
                manifest['benchmark'].append({'location': name, 'origin_xz_m': origin, 'shape_zx': [512, 512], 'spacing_m': 60, **stats})
            manifest['benchmark_scope'] = 'measured helper: perf_counter wall time, tracemalloc and 10ms sampled whole-process RSS; samples may miss peaks'
        (stage / 'README.md').write_text(f'# 连续山脊与站点体量场\n\n来源：`{_i2_PRODUCT_ALGORITHM_ID}`，世界种子 20260903。源代码摘要、参数、计时和量化信息见 manifest.json。\n\n网格 {size} × {size}，间距 {spacing:g} 米；行 Z 向南，列 X 向东。主窗原点 (0, 0) 米，负窗原点 (-24000, -24000) 米。\n\nR 为平滑连续山脊场；V 由 Voronoi 同类站点的有限支持平滑核融合而成，不是严格 F1 最近点 Voronoi 距离。主窗展示 alpha=0、0.65、1，负窗展示 0.65。\n\n高程 PNG 是无阴影的 16 位单通道灰度，固定映射 -500 至 4500 米；`_preview.png` 为 8 位预览，NPZ 为 float64 米制高程或无量纲场。对照图单独标注 R/V，山体图仅作阴影可视化。Advanced 是外观滤波，非真实水沙侵蚀。\n', encoding='utf-8')
        (stage / 'manifest.json').write_text(_i2_json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        _i2_os.rename(stage, target)
    except BaseException:
        _i2_shutil.rmtree(stage, ignore_errors=True)
        raise
    return target

# Source: tools.prepare_product_mountains
def _run_product(args, parser):
    print(generate_product(args.output, args.size, args.spacing, args.benchmark))

# Source: tools.prepare_voronoi_mountains
_i4_sys.path.insert(0, str(ROOT))

# Source: tools.prepare_voronoi_mountains
PREPARE_VORONOI_MOUNTAINS_FAMILIES = ('cellular_massif', 'ridge_network', 'mixed')

# Source: tools.prepare_voronoi_mountains
KEYS = ('advanced_base_m', 'unprotected_height_m', 'height_m')

# Source: tools.prepare_voronoi_mountains
def routing(fields, origin, spacing, seed):
    shape = fields[KEYS[0]].shape
    kind = _i4_np.full(shape, 'interior', dtype='<U24')
    kind[[0, -1], :] = 'unknown_boundary'
    kind[:, [0, -1]] = 'unknown_boundary'
    boundary = _i4_BoundaryGrid(kind, _i4_np.zeros(shape, bool), 'unknown perimeter', _i4_hashlib.sha256(kind.tobytes()).hexdigest())
    graphs, records = ([], {})
    saved = {key: fields[key] for key in (*KEYS, 'protection_mask', 'structure_delta_m')}
    for key in KEYS:
        bed = fields[key]
        terrain = _i4_TerrainGrid(bed, _i4_np.ones(shape, bool), *origin, spacing, spacing, 'generated_terrain', 'voronoi_mountains', _i4_hashlib.sha256(bed.tobytes()).hexdigest(), generation_seed=seed)
        graph = _i4_route_diagnostic(terrain, boundary)
        flow = _i4_accumulate_local_discharge(graph, _i4_np.full(shape, 0.001))
        terminal = _i4_np.arange(bed.size, dtype=_i4_np.int64)
        for cell in graph.order_downstream_first:
            receiver = graph.receiver[cell]
            if receiver >= 0:
                terminal[cell] = terminal[receiver]
        graphs.append((graph, terminal))
        saved[key + '_receiver'] = graph.receiver
        saved[key + '_terminal'] = terminal
        saved[key + '_routed_q_m3_s'] = flow['routed_q_m3_s']
        records[key] = {'terminal_count': int(_i4_np.sum(graph.receiver < 0)), 'unknown_pending_m3_s': flow['unknown_pending_m3_s'], 'lake_retained_m3_s': flow['lake_retained_m3_s'], 'residual_m3_s': flow['residual_m3_s'], 'mean_edge_slope': float(graph.edge_slope.mean())}
    base, base_terminal = graphs[0]
    for key, (graph, terminal) in zip(KEYS[1:], graphs[1:]):
        records[key]['receiver_changed_fraction'] = float(_i4_np.mean(graph.receiver != base.receiver))
        records[key]['terminal_changed_fraction'] = float(_i4_np.mean(terminal != base_terminal))
        records[key]['mean_abs_edge_slope_change'] = float(_i4_np.mean(_i4_np.abs(graph.edge_slope - base.edge_slope)))
        records[key]['mean_abs_elevation_change_m'] = float(_i4_np.mean(_i4_np.abs(fields[key] - fields[KEYS[0]])))
    mask = fields['protection_mask']
    core = mask == 1
    outside = mask == 0
    delta = fields['height_m'] - fields['advanced_base_m']
    records['protection'] = {'core_fraction': float(core.mean()), 'transition_fraction': float(((mask > 0) & (mask < 1)).mean()), 'outside_fraction': float(outside.mean()), 'core_max_abs_error_m': float(_i4_np.max(_i4_np.abs(delta[core]))) if core.any() else None, 'outside_mean_abs_change_m': float(_i4_np.mean(_i4_np.abs(delta[outside]))) if outside.any() else None, 'mean_abs_slope_effect': float(_i4_np.mean(_i4_np.abs(graphs[2][0].edge_slope - graphs[1][0].edge_slope)))}
    transition = ((mask > 0) & (mask < 1)).ravel()
    core_flat = core.ravel()
    records['protection']['core_receiver_changed_fraction'] = float(_i4_np.mean((graphs[2][0].receiver != base.receiver)[core_flat])) if core.any() else None
    records['protection']['core_terminal_changed_fraction'] = float(_i4_np.mean((graphs[2][1] != base_terminal)[core_flat])) if core.any() else None
    for label, values in (('protected_slope', graphs[2][0].edge_slope), ('protection_slope_change', _i4_np.abs(graphs[2][0].edge_slope - graphs[1][0].edge_slope))):
        selected = values[transition]
        records['protection']['transition_' + label + '_p95'] = float(_i4_np.percentile(selected, 95)) if selected.size else None
        records['protection']['transition_' + label + '_max'] = float(_i4_np.max(selected)) if selected.size else None
    return (records, saved)

# Source: tools.prepare_voronoi_mountains
def render_voronoi(path, fields, origin, spacing):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    heights = [fields[k] for k in KEYS]
    low, high = (min((float(h.min()) for h in heights)), max((float(h.max()) for h in heights)))
    n = heights[0].shape[0]
    stride = max(1, int(_i4_np.ceil(n / 90)))
    xcoords = (origin[0] + _i4_np.arange(n) * spacing)[::stride] / 1000
    zcoords = (origin[1] + _i4_np.arange(n) * spacing)[::stride] / 1000
    x, z = _i4_np.meshgrid(xcoords, zcoords)
    extent = [origin[0] / 1000, (origin[0] + (n - 1) * spacing) / 1000, (origin[1] + (n - 1) * spacing) / 1000, origin[1] / 1000]
    fig = plt.figure(figsize=(15, 12), constrained_layout=True)
    for row, az in enumerate((-60, 120)):
        for col, h in enumerate(heights):
            ax = fig.add_subplot(4, 3, row * 3 + col + 1, projection='3d')
            sample = h[::stride, ::stride]
            shade = _i4_physical_hillshade(h, spacing)[::stride, ::stride]
            gray = _i4_np.repeat(_i4_np.clip(0.22 + 0.68 * shade, 0, 1)[..., None], 3, axis=2)
            ax.plot_surface(x, z, sample / 1000, facecolors=gray, shade=False, linewidth=0, antialiased=False, rcount=sample.shape[0], ccount=sample.shape[1])
            ax.set_zlim(low / 1000, high / 1000)
            ax.set_box_aspect((1, 1, 0.35))
            ax.view_init(elev=25, azim=az)
            ax.set_title(f'{KEYS[col]} az={az}°')
            ax.set_xlabel('X km')
            ax.set_ylabel('Z km')
    for col, h in enumerate(heights):
        ax = fig.add_subplot(4, 3, 7 + col)
        ax.imshow(_i4_physical_hillshade(h, spacing), cmap='gray', vmin=0, vmax=1, extent=extent)
        ax.set_xlabel('World X km')
        ax.set_ylabel('World Z km')
        ax.set_title(KEYS[col] + ' overhead')
    ax = fig.add_subplot(4, 3, 10)
    im = ax.imshow(fields['protection_mask'], vmin=0, vmax=1, cmap='viridis', extent=extent)
    fig.colorbar(im, ax=ax)
    ax.set_title('Protection mask')
    ax.set_xlabel('World X km')
    ax.set_ylabel('World Z km')
    ax = fig.add_subplot(4, 3, 11)
    effect = fields['height_m'] - fields['unprotected_height_m']
    lim = max(float(_i4_np.max(_i4_np.abs(effect))), 1e-09)
    im = ax.imshow(effect, cmap='coolwarm', vmin=-lim, vmax=lim, extent=extent)
    fig.colorbar(im, ax=ax, label='m')
    ax.set_title('Protection correction')
    ax.set_xlabel('World X km')
    ax.set_ylabel('World Z km')
    ax = fig.add_subplot(4, 3, 12)
    for key, h in zip(KEYS, heights):
        ax.plot((origin[0] + _i4_np.arange(n) * spacing) / 1000, h[n // 2], label=key)
    ax.set_ylim(low, high)
    ax.set_xlabel('X km')
    ax.set_ylabel('Elevation m')
    ax.legend(fontsize=6)
    ax.set_title('Central section')
    exaggeration = 0.35 * ((n - 1) * spacing) / (high - low)
    fig.suptitle(f'Origin {origin} m; common scale; vertical exaggeration {exaggeration:.2f}×')
    fig.savefig(path, dpi=110)
    plt.close(fig)
    fig = plt.figure(figsize=(7, 5), constrained_layout=True)
    ax = fig.add_subplot(111, projection='3d')
    sample = heights[2][::stride, ::stride]
    shade = _i4_physical_hillshade(heights[2], spacing)[::stride, ::stride]
    gray = _i4_np.repeat(_i4_np.clip(0.22 + 0.68 * shade, 0, 1)[..., None], 3, axis=2)
    ax.plot_surface(x, z, sample / 1000, facecolors=gray, shade=False, linewidth=0, rcount=sample.shape[0], ccount=sample.shape[1])
    ax.set_zlim(low / 1000, high / 1000)
    ax.set_box_aspect(((n - 1) * spacing, (n - 1) * spacing, high - low))
    ax.view_init(elev=25, azim=-60)
    ax.set_title('Protected terrain, physical aspect 1:1')
    ax.set_xlabel('X km')
    ax.set_ylabel('Z km')
    ax.set_zlabel('height km')
    physical_path = path.with_name(path.stem + '_1to1.png')
    fig.savefig(physical_path, dpi=110)
    plt.close(fig)
    if origin == (0.0, 0.0):
        lo, hi = (int(round(9000 / spacing)), int(round(15000 / spacing)))
        fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
        local_extent = [9, 15, 15, 9]
        for col, (key, h) in enumerate(zip(KEYS, heights)):
            axes[0, col].imshow(_i4_physical_hillshade(h, spacing)[lo:hi + 1, lo:hi + 1], cmap='gray', vmin=0, vmax=1, extent=local_extent)
            axes[0, col].set_title(key)
            axes[0, col].set_xlabel('World X km')
            axes[0, col].set_ylabel('World Z km')
            axes[1, col].plot((origin[0] + _i4_np.arange(lo, hi + 1) * spacing) / 1000, h[(lo + hi) // 2, lo:hi + 1])
            axes[1, col].set_ylim(low, high)
            axes[1, col].set_xlabel('World X km')
            axes[1, col].set_ylabel('Elevation m')
        fig.suptitle('Fixed central 9–15 km window; section at Z=12 km')
        detail_path = path.with_name(path.stem + '_central.png')
        fig.savefig(detail_path, dpi=110)
        plt.close(fig)
    with Image.open(path) as im:
        result = {'sha256': digest(path), 'width_px': im.width, 'height_px': im.height, 'stride': stride, 'vertical_exaggeration': exaggeration, 'physical_aspect_file': physical_path.name, 'physical_aspect_sha256': digest(physical_path)}
        if origin == (0.0, 0.0):
            result.update({'central_file': detail_path.name, 'central_sha256': digest(detail_path)})
        return result

# Source: tools.prepare_voronoi_mountains
def generate_voronoi(output, size=201, spacing=120.0, benchmark_sizes=(), windows=None, families=None):
    target = _i4_Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = _i4_Path(_i4_tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        sources = ['terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/mountain_forms.py', 'terrain_pipeline/drainage.py', 'terrain_pipeline/common_infra.py', 'terrain_pipeline/terrain_map_style.py', 'diffusion/geographic_noise.py', 'terrain_pipeline/common_infra.py', 'tools/prepare_mountain_forms.py', 'tools/prepare_mountain_forms.py', 'terrain_pipeline/drainage.py', 'terrain_pipeline/common_infra.py']
        hashes = {p: digest(ROOT / p) for p in sources}
        manifest = {'world_seed': 20260903, 'coordinates': 'X east, Z south, metres', 'source_hashes_sha256': hashes, 'window_selection': 'fixed before inspection', 'boundary': 'unknown perimeter; diagnostic topology, not preserved river network', 'rasters': [], 'images': {}, 'timings': {}, 'diagnostics': {}, 'benchmark': []}
        for window in windows or tuple(WINDOWS):
            origin = WINDOWS[window]
            for family in families or PREPARE_VORONOI_MOUNTAINS_FAMILIES:
                cfg = _i4_VoronoiConfig(world_seed=20260903, family=family)
                fields, stats = measured(lambda: _i4_rasterize(origin, (size, size), spacing, cfg))
                prefix = f'{window}_{family}'
                metadata = {'source_hashes_sha256': hashes, 'origin_m_xz': origin, 'spacing_m': spacing, 'shape_zx': [size, size], 'algorithm': fields['metadata']}
                path = stage / (prefix + '.npz')
                _i4_np.savez_compressed(path, **{k: fields[k] for k in (*KEYS, 'structure_delta_m', 'protection_mask')}, metadata_json=_i4_np.array(_i4_json.dumps(metadata, ensure_ascii=False, allow_nan=False)))
                manifest['rasters'].append({'file': path.name, 'sha256': digest(path), 'metadata': metadata})
                manifest['timings'][prefix + '_generation'] = stats
                render_start = _i4_time.perf_counter()
                image = render_voronoi(stage / (prefix + '.png'), fields, origin, spacing)
                render_stats = {'seconds': _i4_time.perf_counter() - render_start, 'memory': 'not sampled for rendering'}
                manifest['images'][prefix + '.png'] = image
                manifest['timings'][prefix + '_render'] = render_stats
                diag_fields = _i4_rasterize(origin, (65, 65), 375.0, cfg)
                (record, arrays), diag_stats = measured(lambda: routing(diag_fields, origin, 375.0, 20260903))
                diag_path = stage / (prefix + '_routing.npz')
                _i4_np.savez_compressed(diag_path, **arrays)
                manifest['diagnostics'][prefix] = {'results': record, 'file': diag_path.name, 'sha256': digest(diag_path), 'size_zx': [65, 65], 'spacing_m': 375.0, 'local_q_m3_s_per_cell': 0.001, 'timing': diag_stats}
        for n in benchmark_sizes:
            cfg = _i4_VoronoiConfig(world_seed=20260903, family='mixed')
            for origin in (WINDOWS['main'], (500000000.0, -500000000.0)):
                _, stats = measured(lambda: _i4_rasterize(origin, (n, n), 60.0, cfg))
                manifest['benchmark'].append({'size_zx': [n, n], 'origin_m_xz': origin, 'spacing_m': 60.0, **stats})
        cfg = _i4_VoronoiConfig(world_seed=20260903)
        coarse = _i4_rasterize((0.0, 0.0), (17, 17), 120.0, cfg)['height_m']
        fine = _i4_rasterize((0.0, 0.0), (33, 33), 60.0, cfg)['height_m']
        left = _i4_rasterize((0.0, 0.0), (17, 8), 120.0, cfg)['height_m']
        right = _i4_rasterize((960.0, 0.0), (17, 9), 120.0, cfg)['height_m']
        xx, zz = _i4_np.meshgrid(_i4_np.arange(17) * 120.0, _i4_np.arange(17) * 120.0)
        order = _i4_np.random.default_rng(17).permutation(xx.size)
        shuffled = _i4_sample_stages(xx.ravel()[order], zz.ravel()[order], cfg)['height_m']
        reordered = _i4_np.empty_like(shuffled)
        reordered[order] = shuffled
        manifest['sampling_consistency'] = {'coarse_fine_max_abs_m': float(_i4_np.max(_i4_np.abs(coarse - fine[::2, ::2]))), 'split_max_abs_m': float(_i4_np.max(_i4_np.abs(coarse - _i4_np.concatenate((left, right), axis=1)))), 'shuffled_max_abs_m': float(_i4_np.max(_i4_np.abs(coarse.ravel() - reordered)))}
        manifest['measurement_scope'] = 'wall seconds and tracemalloc peak; sampled whole-process RSS includes prior allocations and may miss peaks; rendering timed separately'
        (stage / 'manifest.json').write_text(_i4_json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        _i4_os.rename(stage, target)
    finally:
        if stage.exists():
            _i4_shutil.rmtree(stage)
    return target

# Source: tools.prepare_voronoi_mountains
def _run_voronoi(args, parser):
    print(generate_voronoi(args.output_dir, 401 if args.final else 201, 60.0 if args.final else 120.0, (128, 256, 512) if args.final else (), args.windows, args.families))


def main(argv=None):
    parser = _i0_argparse.ArgumentParser(description="Prepare reproducible mountain geometry and comparisons.")
    subparsers = parser.add_subparsers(dest="mechanism", required=True)
    mode_parser = subparsers.add_parser('skeleton')
    mode_parser.add_argument('output')
    mode_parser.add_argument('--size', type=int, default=121)
    mode_parser.add_argument('--spacing', type=float, default=200.0)
    mode_parser.add_argument('--benchmark', action='store_true')
    mode_parser.set_defaults(_handler=_run_skeleton, _parser=mode_parser)
    mode_parser = subparsers.add_parser('local-volume')
    mode_parser.add_argument('output')
    mode_parser.add_argument('--size', type=int, default=121)
    mode_parser.add_argument('--spacing', type=float, default=200.0)
    mode_parser.add_argument('--benchmark', action='store_true')
    mode_parser.set_defaults(_handler=_run_local_volume, _parser=mode_parser)
    mode_parser = subparsers.add_parser('product')
    mode_parser.add_argument('output')
    mode_parser.add_argument('--size', type=int, default=121)
    mode_parser.add_argument('--spacing', type=float, default=200.0)
    mode_parser.add_argument('--benchmark', action='store_true')
    mode_parser.set_defaults(_handler=_run_product, _parser=mode_parser)
    mode_parser = subparsers.add_parser('procedural')
    mode_parser.add_argument('--output-dir', type=_i3_Path, required=True)
    mode_parser.add_argument('--origin', nargs=2, type=float, default=(0.0, 0.0), metavar=('X_M', 'Z_M'))
    mode_parser.add_argument('--size', type=int, default=401, help='square raster side, 3 to 512')
    mode_parser.add_argument('--spacing', type=float, default=60.0, help='metres')
    mode_parser.add_argument('--world-seed', type=int, default=20260903)
    mode_parser.add_argument('--benchmark-sizes', nargs='+', type=int, default=[128, 256, 512])
    mode_parser.add_argument('--with-processes', action='store_true', help='add separate finite river, diffusion and glacier diagnostics')
    mode_parser.set_defaults(_handler=_run_procedural, _parser=mode_parser)
    mode_parser = subparsers.add_parser('voronoi')
    mode_parser.add_argument('--output-dir', type=_i4_Path, required=True)
    mode_parser.add_argument('--final', action='store_true', help='401² at 60 m and 128/256/512 benchmarks')
    mode_parser.add_argument('--windows', nargs='+', choices=tuple(WINDOWS), default=None)
    mode_parser.add_argument('--families', nargs='+', choices=PREPARE_VORONOI_MOUNTAINS_FAMILIES, default=None)
    mode_parser.set_defaults(_handler=_run_voronoi, _parser=mode_parser)
    args = parser.parse_args(argv)
    return args._handler(args, args._parser)

if __name__ == "__main__":
    main()
