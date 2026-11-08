"""Prepare and export a finite, source-bound coarse world mountain product."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import threading
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import terrain_map_style as style
from terrain_pipeline.tectonic import load_product as load_base
from terrain_pipeline.mountain_forms import WorldMountainConfig, load_belt_product, prepare_world_mountain_belts, save_belt_product
from terrain_pipeline.common_infra import WORLD_SEED

DEFAULT_SOURCE = ROOT / '.scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz'
DEFAULT_IDENTITY = 'b4c8bbdba29111b8c3ba3270e2f0d3a4fed3544655249fa07c506654b8ae6af9'
DEFAULT_SHA256 = '7f1fa9e6aa5fe327000f1e850ad24ddddf20ffb3bf20d996259ba183af2c3ed3'
LOW, HIGH = -5000., 12000.
LOCAL_EXTENT_M = (-750000., -150000., -570000., 30000.)
STAGES = (('raw_elevation_m', '原板块高程代理'),
          ('base_elevation_m', '降低代理峰后的大陆基底'),
          ('elevation_m', '大陆基底 + 世界粗山系'))
SOURCE_FILES = (
    'terrain_pipeline/world_mountain_belts.py', 'terrain_pipeline/tectonic_product.py',
    'terrain_pipeline/tectonic_evolution.py', 'terrain_pipeline/tectonic_formation.py',
    'terrain_pipeline/tectonic_shapes.py', 'terrain_pipeline/terrain_map_style.py',
    'terrain_pipeline/common_infra.py',
    'diffusion/geographic_noise.py', 'tools/prepare_world_mountain_belts.py',
)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def measured(call):
    import psutil
    process = psutil.Process()
    samples = [process.memory_info().rss]
    stop = threading.Event()

    def monitor():
        while not stop.wait(.01):
            samples.append(process.memory_info().rss)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    start = time.perf_counter()
    try:
        result = call()
    finally:
        seconds = time.perf_counter() - start
        samples.append(process.memory_info().rss)
        stop.set()
        thread.join()
    info = {'seconds': seconds, 'sampled_process_rss_peak_bytes': max(samples)}
    if hasattr(process.memory_info(), 'peak_wset'):
        info['process_lifetime_peak_working_set_bytes'] = process.memory_info().peak_wset
    return result, info


def encode_height(height):
    height = np.asarray(height, dtype=np.float64)
    if height.ndim != 2 or not np.isfinite(height).all():
        raise ValueError('finite two-dimensional height required')
    return np.rint(np.clip((height - LOW) / (HIGH - LOW), 0., 1.) * 65535).astype(np.uint16)


def decode_height(encoded):
    return LOW + np.asarray(encoded, dtype=np.float64) * ((HIGH - LOW) / 65535)


def export_height(path, height):
    path = Path(path)
    encoded = encode_height(height)
    Image.fromarray(encoded).save(path)
    preview_path = path.with_name(path.stem + '_preview.png')
    preview = np.rint(encoded.astype(np.float64) / 257).astype(np.uint8)
    Image.fromarray(preview).save(preview_path)
    with Image.open(path) as image:
        if image.mode not in ('I;16', 'I') or not np.array_equal(np.asarray(image), encoded):
            raise ValueError('16bit PNG readback mismatch')
    with Image.open(preview_path) as image:
        if image.mode != 'L' or not np.array_equal(np.asarray(image), preview):
            raise ValueError('preview PNG readback mismatch')
    return {'file': path.name, 'preview_file': preview_path.name,
            'sha256': digest(path), 'preview_sha256': digest(preview_path),
            'minimum_m': float(np.min(height)), 'maximum_m': float(np.max(height)),
            'saturated_below_count': int(np.count_nonzero(height < LOW)),
            'saturated_above_count': int(np.count_nonzero(height > HIGH)),
            'max_abs_decode_error_m': float(np.max(np.abs(decode_height(encoded) - height))),
            'png_readback_equal': True}


def grid_axes(grid):
    nz, nx = grid['shape']
    spacing = grid['spacing_m']
    return (grid['origin_x_m'] + (np.arange(nx) + .5) * spacing,
            grid['origin_z_m'] + (np.arange(nz) + .5) * spacing)


def grid_extent(grid):
    width, height = grid['extent_m']
    return (grid['origin_x_m'], grid['origin_x_m'] + width,
            grid['origin_z_m'], grid['origin_z_m'] + height)


def terrain_rgb(height, ocean, spacing):
    """Reuse repository palettes/shading, with declared deep-ocean world limits."""
    from matplotlib.colors import Normalize
    palette = style.band_colors()
    bands = np.asarray(style.LAND_BANDS_M)
    indices = np.clip(np.searchsorted(bands, height, side='right') - 1, 0, len(palette) - 1)
    rgb = palette[indices].copy()
    rgb[ocean] = style.ocean_colormap()(Normalize(0., 5000., clip=True)(np.maximum(-height[ocean], 0)))[..., :3]
    return style.apply_hillshade(rgb, height, spacing)


def furniture(ax, extent, title):
    ax.set_title(title, fontsize=11)
    ax.set_xlabel('X 向东 (km)')
    ax.set_ylabel('Z 向南 (km)')
    ax.set_xlim(extent[0] / 1000, extent[1] / 1000)
    ax.set_ylim(extent[3] / 1000, extent[2] / 1000)
    style.draw_scale_bar(ax, style.nice_scale_length_km((extent[1] - extent[0]) / 1000))
    style.draw_north_arrow(ax)


def plot_inventory(ax, inventory):
    from matplotlib.patches import Ellipse
    colors = {'main': '#ef5350', 'parallel': '#ffcc65', 'oblique_branch': '#61e3ef'}
    for ridge in inventory['ridges']:
        points = np.asarray(ridge['vertices_m']) / 1000
        role = ridge['role']
        ax.plot(points[:, 0], points[:, 1], color=colors.get(role, 'white'),
                linewidth=1.3 if role == 'main' else .75, alpha=.85)
    for basin in inventory['basins']:
        direction = np.asarray(basin['axis'])
        angle = np.degrees(np.arctan2(direction[1], direction[0]))
        ax.add_patch(Ellipse(np.asarray(basin['centre_m']) / 1000,
                            2 * basin['semi_length_m'] / 1000,
                            2 * basin['semi_width_m'] / 1000, angle=angle,
                            facecolor='none', edgecolor='#f3a5f7', linewidth=.8))


def profile_samples(product):
    """Along the longest saved main ridge; all sampling is saved-raster query."""
    inventory = product.manifest['source_inventory']
    mains = [r for r in inventory['ridges'] if r['role'] == 'main']
    if mains:
        ridge = max(mains, key=lambda r: np.linalg.norm(np.diff(np.asarray(r['vertices_m']), axis=0), axis=1).sum())
        points = np.asarray(ridge['vertices_m'], dtype=float)
        name = ridge['source_id']
    else:
        xmin, xmax, zmin, zmax = grid_extent(product.manifest['grid'])
        points = np.array([[xmin + .1 * (xmax - xmin), (zmin + zmax) / 2],
                           [xmax - .1 * (xmax - xmin), (zmin + zmax) / 2]])
        name = 'fallback-domain-transect'
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.r_[0., np.cumsum(lengths)]
    distance = np.linspace(0., cumulative[-1], 601)
    x = np.interp(distance, cumulative, points[:, 0])
    z = np.interp(distance, cumulative, points[:, 1])
    result = product.query(x, z)
    return {'distance_m': distance, 'x_m': x, 'z_m': z,
            **{key: result[key] for key, _ in STAGES}}, str(name)


def render_figures(product, stage):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.lines import Line2D
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    arrays = product.arrays
    manifest = product.manifest
    grid = manifest['grid']
    spacing = grid['spacing_m']
    extent = grid_extent(grid)
    image_extent = np.array([extent[0], extent[1], extent[3], extent[2]]) / 1000
    ocean = arrays['ocean_connected'].astype(bool)
    metadata = {}
    title = f'程序化世界粗地貌，非TD | {spacing / 1000:g} km格 | 基底种子20261020 + 形态种子{manifest["world_seed"]}'
    rgb = {key: terrain_rgb(arrays[key], ocean, spacing) for key, _ in STAGES}

    fig, axes = plt.subplots(1, 3, figsize=(18, 6.2), constrained_layout=True)
    for ax, (key, label) in zip(axes, STAGES):
        ax.imshow(rgb[key], origin='upper', extent=image_extent, interpolation='nearest')
        furniture(ax, extent, label)
    cmap = ListedColormap(style.BAND_COLORS)
    colorbar = fig.colorbar(plt.cm.ScalarMappable(norm=BoundaryNorm(style.LAND_BANDS_M, cmap.N), cmap=cmap),
                           ax=axes, shrink=.72, pad=.015, extend='max')
    colorbar.set_label('陆地高程 (m)；海深固定0–5000 m蓝色；仅地形配色，无覆盖分类')
    fig.suptitle(title, fontsize=13)
    fig.savefig(stage / 'world_comparison.png', dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(13, 10), constrained_layout=True)
    ax.imshow(rgb['elevation_m'], origin='upper', extent=image_extent, interpolation='nearest')
    furniture(ax, extent, '最终世界粗山系 · 同源俯视地形配色与真实坡度阴影')
    fig.suptitle(title, fontsize=12)
    fig.savefig(stage / 'world_terrain.png', dpi=160)
    plt.close(fig)

    x, z = grid_axes(grid)
    lx0, lx1, lz0, lz1 = LOCAL_EXTENT_M
    xi = np.flatnonzero((x >= lx0) & (x < lx1))
    zi = np.flatnonzero((z >= lz0) & (z < lz1))
    if len(xi) >= 2 and len(zi) >= 2:
        crop = np.ix_(zi, xi)
        actual = (x[xi[0]] - spacing / 2, x[xi[-1]] + spacing / 2,
                  z[zi[0]] - spacing / 2, z[zi[-1]] + spacing / 2)
        local_extent = np.array([actual[0], actual[1], actual[3], actual[2]]) / 1000
        fig, axes = plt.subplots(1, 3, figsize=(17, 6.3), constrained_layout=True)
        for ax, (key, label) in zip(axes, STAGES):
            ax.imshow(rgb[key][crop], origin='upper', extent=local_extent, interpolation='nearest')
            furniture(ax, actual, label)
        fig.suptitle(title + '\n固定600 km大陆局部；格距与全域一致', fontsize=12)
        fig.savefig(stage / 'continental_closeup.png', dpi=160)
        plt.close(fig)
        metadata['local_extent_m'] = list(actual)

    fig, axes = plt.subplots(1, 2, figsize=(17, 7), constrained_layout=True)
    im = axes[0].imshow(arrays['mountain_height_m'], origin='upper', extent=image_extent,
                        cmap='magma', vmin=0, vmax=4000, interpolation='nearest')
    furniture(axes[0], extent, '新增山带高度 (m)，固定0–4000 m色阶')
    fig.colorbar(im, ax=axes[0], shrink=.65, label='新增高度 (m)')
    axes[1].imshow(rgb['elevation_m'], origin='upper', extent=image_extent, interpolation='nearest')
    plot_inventory(axes[1], manifest['source_inventory'])
    furniture(axes[1], extent, '保存的山带/盆地清册；盆地不代表湖泊')
    axes[1].legend(handles=[Line2D([0], [0], color=c, label=t) for c, t in
                           [('#ef5350', '主带'), ('#ffcc65', '平行脊'), ('#61e3ef', '斜支脉'), ('#f3a5f7', '盆地范围')]], fontsize=8)
    fig.suptitle(title, fontsize=12)
    fig.savefig(stage / 'mountain_inventory.png', dpi=160)
    plt.close(fig)

    profile, profile_id = profile_samples(product)
    np.savez(stage / 'profile_samples.npz', **profile)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True, gridspec_kw={'width_ratios': [1, 1.8]})
    axes[0].imshow(rgb['elevation_m'], origin='upper', extent=image_extent, interpolation='nearest')
    axes[0].plot(profile['x_m'] / 1000, profile['z_m'] / 1000, color='#ed3434', linewidth=1.6)
    furniture(axes[0], extent, '剖面位置 · 沿最长保存主带')
    for (key, label), color in zip(STAGES, ('#777777', '#b8860b', '#273b8c')):
        axes[1].plot(profile['distance_m'] / 1000, profile[key], color=color, label=label)
    axes[1].set(xlabel='沿线距离 (km)', ylabel='高程 (m)', title='跨峰群与鞍部剖面 · 栅格插值，非更细精度')
    axes[1].grid(alpha=.25)
    axes[1].legend(fontsize=9)
    fig.suptitle(title, fontsize=12)
    fig.savefig(stage / 'ridge_profile.png', dpi=160)
    plt.close(fig)
    metadata['profile'] = {'source_id': profile_id, 'samples': len(profile['x_m']),
                           'sampling': 'read-only raster query; interpolated points do not increase physical resolution',
                           'length_m': float(profile['distance_m'][-1])}
    return metadata


def verify_png(path):
    with Image.open(path) as image:
        image.load()
        values = np.asarray(image)
        if min(image.size) < 2 or np.ptp(values.astype(np.float64)) == 0:
            raise ValueError('empty or constant PNG: ' + str(path))
        return {'sha256': digest(path), 'size_px': list(image.size), 'mode': image.mode,
                'coverage_status': 'complete_in_window', 'terrain_basis': 'frozen-tectonic-derived-coarse-morphology',
                'td_binding': None}


def copy_gallery(output, gallery):
    output, gallery = Path(output).resolve(), Path(gallery).resolve()
    if gallery.exists():
        raise FileExistsError(gallery)
    gallery.mkdir(parents=True)
    files = sorted(output.glob('*.png')) + [output / 'manifest.json', output / 'README.md', output / 'source_inventory.json']
    checks = {}
    for source in files:
        target = gallery / source.name
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise ValueError('gallery copy mismatch')
        checks[source.name] = digest(target)
    write_json(gallery / 'gallery-manifest.json', {'source_directory': str(output),
               'product_manifest_sha256': digest(output / 'manifest.json'), 'copies_sha256': checks,
               'copy_checks_passed': True, 'td_binding': None})
    return checks


def compare_resolution(product, reference_directory):
    directory = Path(reference_directory)
    record = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    reference = load_belt_product(directory / 'product.npz', expected_identity=record['identity'])
    for name in ('world_seed', 'base_source', 'source_inventory'):
        if product.manifest[name] != reference.manifest[name]:
            raise ValueError('resolution comparison has different source geometry: ' + name)
    xmin, xmax, zmin, zmax = grid_extent(product.manifest['grid'])
    x, z = np.meshgrid(np.linspace(xmin + .01 * (xmax - xmin), xmax - .01 * (xmax - xmin), 129),
                       np.linspace(zmin + .01 * (zmax - zmin), zmax - .01 * (zmax - zmin), 103))
    direct, previous_direct = product.evaluate_geometry(x, z), reference.evaluate_geometry(x, z)
    current, previous = product.query(x, z), reference.query(x, z)
    errors = {}
    for key, _ in STAGES:
        difference = current[key] - previous[key]
        errors[key] = {'geometry_max_abs_difference_m': float(np.max(np.abs(direct[key] - previous_direct[key]))),
                       'raster_query_max_abs_difference_m': float(np.max(np.abs(difference))),
                       'raster_query_rmse_m': float(np.sqrt(np.mean(difference ** 2))),
                       'current_raster_vs_geometry_max_abs_m': float(np.max(np.abs(current[key] - direct[key]))),
                       'reference_raster_vs_geometry_max_abs_m': float(np.max(np.abs(previous[key] - previous_direct[key])))}
    return {'reference_directory': str(directory.resolve()), 'reference_identity': reference.identity,
            'spacing_m': [reference.manifest['grid']['spacing_m'], product.manifest['grid']['spacing_m']],
            'common_points': int(x.size), 'inventory_equal': True, 'errors': errors,
            'scope': 'same continuous geometry; independently sampled DEM interpolation may differ'}


def generate(output, *, source=DEFAULT_SOURCE, expected_identity=DEFAULT_IDENTITY,
             expected_sha256=DEFAULT_SHA256, spacing_m=5000., world_seed=WORLD_SEED,
             flatten_base=True, amplitude_scale=1., gallery=None, reference_run=None):
    target = Path(output).resolve()
    source = Path(source).resolve()
    if target.exists():
        raise FileExistsError(target)
    if gallery is not None and Path(gallery).exists():
        raise FileExistsError(gallery)
    config = WorldMountainConfig(spacing_m=spacing_m, world_seed=world_seed,
                                 flatten_base=flatten_base, amplitude_scale=amplitude_scale)
    source_sha256 = digest(source)
    if expected_sha256 is not None and source_sha256 != expected_sha256:
        raise ValueError('base source SHA256 mismatch')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / ('.' + target.name + '-staging')
    stage.mkdir()
    source_snapshot = {}
    for relative in SOURCE_FILES:
        destination = stage / 'source_snapshot' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
        source_snapshot[relative] = digest(destination)
    timings = {}
    base, timings['source_load'] = measured(lambda: load_base(source, expected_identity=expected_identity))
    product, timings['prepare'] = measured(lambda: prepare_world_mountain_belts(base, config))
    _, timings['save_product'] = measured(lambda: save_belt_product(product, stage / 'product.npz'))
    cold, timings['cold_load'] = measured(lambda: load_belt_product(stage / 'product.npz', expected_identity=product.identity))
    for key in product.arrays:
        if not np.array_equal(product.arrays[key], cold.arrays[key]):
            raise ValueError('cold read array mismatch: ' + key)

    def export_arrays():
        records, heights = {}, {}
        for key, values in cold.arrays.items():
            path = stage / (key + '.npy')
            np.save(path, values, allow_pickle=False)
            loaded = np.load(path, allow_pickle=False)
            if loaded.dtype != values.dtype or not np.array_equal(loaded, values):
                raise ValueError('NPY readback mismatch')
            records[key] = {'file': path.name, 'sha256': digest(path), 'dtype': str(values.dtype),
                            'shape': list(values.shape), 'readback_equal': True}
        for key, _ in STAGES:
            heights[key] = export_height(stage / (key + '_16bit.png'), cold.arrays[key])
        return records, heights

    (array_records, heights), timings['array_png_export'] = measured(export_arrays)
    plot_info, timings['render'] = measured(lambda: render_figures(cold, stage))
    arrays = cold.arrays
    ocean = arrays['ocean_connected'].astype(bool)
    origin = cold.manifest['grid']
    x, z = grid_axes(origin)
    xx, zz = np.meshgrid(x, z)
    check, timings['query_all_centres'] = measured(lambda: cold.query(xx, zz))
    centre_errors = {key: float(np.max(np.abs(check[key].astype(float) - values.astype(float))))
                     for key, values in arrays.items()}
    images = {p.name: verify_png(p) for p in sorted(stage.glob('*.png'))}
    for relative in SOURCE_FILES:
        if digest(ROOT / relative) != source_snapshot[relative]:
            raise ValueError('code changed during preparation: ' + relative)
    if digest(source) != source_sha256:
        raise ValueError('source changed during preparation')
    comparison = None
    if reference_run is not None:
        comparison, timings['resolution_comparison'] = measured(lambda: compare_resolution(cold, reference_run))
    metadata = {'schema': 'world-mountain-belts-delivery-v1', 'identity': cold.identity,
                'terrain_basis': '程序化世界粗地貌，非TD', 'td_binding': None,
                'base_source': {'path': str(source), 'identity': base.identity, 'sha256': source_sha256,
                                'world_seed': base.manifest['config']['world_seed']},
                'world_seed': world_seed, 'base_world_seed': base.manifest['config']['world_seed'],
                'config': asdict(config), 'product_manifest': cold.manifest,
                'product_npz_sha256': digest(stage / 'product.npz'),
                'source_snapshot_sha256': source_snapshot, 'arrays': array_records, 'height_images': heights,
                'mapping': {'minimum_m': LOW, 'maximum_m': HIGH, 'code_max': 65535,
                            'encode': 'round(clip((height-min)/(max-min),0,1)*65535)',
                            'rounding': 'nearest ties to even', 'decode_quantum_m': (HIGH - LOW) / 65535},
                'render': {'palette': 'terrain_map_style LAND_BANDS_M/BAND_COLORS',
                           'land_band_edges_m': list(style.LAND_BANDS_M),
                           'ocean_depth_limits_m': [0, 5000], 'light': list(style.HILLSHADE_LIGHT),
                           'vertical_exaggeration': 1, 'display_interpolation': 'nearest',
                           'no_vegetation_snow_or_water_simulation': True, **plot_info},
                'images': images, 'timings': timings, 'resolution_comparison': comparison,
                'resource_measurement': 'perf_counter wall seconds; process RSS sampled every 10 ms, includes interpreter and imports; sampling can miss peaks; peak_wset is process lifetime when available',
                'environment': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
                                'numpy': np.__version__, 'cpu_count': os.cpu_count(),
                                'packages': {name: importlib.metadata.version(name) for name in
                                             ('numpy', 'scipy', 'Pillow', 'matplotlib', 'psutil')}},
                'checks': {'cold_arrays_equal': True, 'npy_readback_equal': True, 'png_readback_equal': True,
                           'query_grid_centres_max_abs_error': centre_errors,
                           'ocean_elevation_max_abs_change_m': float(np.max(np.abs(arrays['elevation_m'][ocean] - arrays['raw_elevation_m'][ocean]), initial=0)),
                           'raw_negative_non_ocean_cells': int(np.sum((arrays['raw_elevation_m'] < 0) & ~ocean)),
                           'negative_non_ocean_cells': int(np.sum((arrays['elevation_m'] < 0) & ~ocean)),
                           'negative_elevation_created_cells': int(np.sum((arrays['elevation_m'] < 0) & (arrays['raw_elevation_m'] >= 0))),
                           'negative_elevation_removed_cells': int(np.sum((arrays['elevation_m'] >= 0) & (arrays['raw_elevation_m'] < 0))),
                           'source_unchanged': True},
                'limitations': ['coarse morphology only; no new hydrology, lakes, climate, TD inference or Minecraft',
                                'finite source prepared as a whole; infinite incremental generation not validated',
                                'visual morphology requires human review; delivery checks do not certify naturalness']}
    write_json(stage / 'source_inventory.json', cold.manifest['source_inventory'])
    write_json(stage / 'manifest.json', metadata)
    (stage / 'README.md').write_text(
        '# 大陆基底与世界粗山系\n\n'
        f'程序化世界粗地貌，非TD。格距 {spacing_m:g} m；1600×1280 km真实冻结板块背景。'
        f'基底实际种子 {metadata["base_world_seed"]}，新形态种子 {world_seed}。\n\n'
        'world_comparison.png 为同色阶/光照的原代理、压低峰幅基底、最终地表；world_terrain.png 为最终同源俯视。'
        'continental_closeup.png 是固定600 km大陆局部；mountain_inventory.png 叠加真实保存清册；ridge_profile.png 沿最长主带查询。\n\n'
        '仅地形配色，无真实植被、积雪或材质分类；海洋读保存连通掩膜，负高程内陆洼地不绘作海洋或已验湖泊。'
        f'16bit灰度固定映射 {LOW:g} 至 {HIGH:g} m，8bit仅预览。NPY/NPZ保留米制数组；量化、读回、文件摘要见manifest.json。\n\n'
        '未重跑水文、GPU、局部TD或游戏。来源原件不可变；source_snapshot保存本次实际代码。\n', encoding='utf-8')
    stage.rename(target)
    if gallery is not None:
        copy_gallery(target, gallery)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--expected-identity', default=DEFAULT_IDENTITY)
    parser.add_argument('--expected-sha256', default=DEFAULT_SHA256)
    parser.add_argument('--spacing', type=float, default=5000.)
    parser.add_argument('--world-seed', type=int, default=WORLD_SEED)
    parser.add_argument('--keep-proxy-peaks', action='store_true')
    parser.add_argument('--amplitude-scale', type=float, default=1.)
    parser.add_argument('--gallery', type=Path)
    parser.add_argument('--reference-run', type=Path)
    args = parser.parse_args(argv)
    output = generate(args.output, source=args.source, expected_identity=args.expected_identity,
                      expected_sha256=args.expected_sha256, spacing_m=args.spacing, world_seed=args.world_seed,
                      flatten_base=not args.keep_proxy_peaks, amplitude_scale=args.amplitude_scale,
                      gallery=args.gallery, reference_run=args.reference_run)
    print(output)
    return output


if __name__ == '__main__':
    main()
