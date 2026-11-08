"""Produce fixed-map grayscale evidence for continuous ridge × Voronoi mountains."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_forms import PRODUCT_ALGORITHM_ID, ProductMountainConfig, sample_product_mountains
from terrain_pipeline.mountain_forms import AdvancedFilterConfig, ADVANCED_ALGORITHM_ID as ADVANCED_ID
from terrain_pipeline.terrain_map_style import physical_hillshade
from terrain_pipeline.common_infra import derive_subseed
from tools.prepare_procedural_mountains import measured

LOW, HIGH = -500.0, 4500.0
WINDOWS = {'main': (0.0, 0.0), 'negative': (-24000.0, -24000.0)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode_height(height):
    height = np.asarray(height, dtype=np.float64)
    if not np.isfinite(height).all():
        raise ValueError('height must be finite')
    return np.rint(np.clip((height - LOW) / (HIGH - LOW), 0, 1) * 65535).astype(np.uint16)


def decode_height(encoded):
    return LOW + np.asarray(encoded, dtype=np.float64) * ((HIGH - LOW) / 65535)


def save_height(path, height):
    encoded = encode_height(height)
    Image.fromarray(encoded, mode='I;16').save(path)
    Image.fromarray(np.rint(encoded.astype(np.float64) / 257).astype(np.uint8), mode='L').save(path.with_name(path.stem + '_preview.png'))
    error = decode_height(encoded) - height
    return {'min_m': float(np.min(height)), 'max_m': float(np.max(height)),
            'saturated_below_count': int(np.count_nonzero(height < LOW)),
            'saturated_above_count': int(np.count_nonzero(height > HIGH)),
            'max_abs_decode_error_m': float(np.max(np.abs(error))),
            'sha256': digest(path), 'preview_sha256': digest(path.with_name(path.stem + '_preview.png'))}


def render(path, cases, spacing):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(cases), 5, figsize=(16, 3.3 * len(cases)), squeeze=False, constrained_layout=True)
    for row, (name, fields) in enumerate(cases):
        for col, (key, label, lo, hi, cmap) in enumerate([
            ('ridge', 'R [0,1]', 0, 1, 'gray'), ('volume', 'V [0,1]', 0, 1, 'gray'),
            ('macro_height_m', 'Macro (m)', LOW, HIGH, 'gray'),
            ('height_m', 'Advanced (m)', LOW, HIGH, 'gray'),
            ('delta_m', 'delta (m)', -262.5, 262.5, 'coolwarm')]):
            im = axes[row, col].imshow(fields[key], cmap=cmap, vmin=lo, vmax=hi)
            axes[row, col].set_title('alpha=' + name.split('_')[-1] + ' | ' + label, fontsize=9)
            axes[row, col].axis('off')
            fig.colorbar(im, ax=axes[row, col], shrink=.7)
    span_km = (cases[0][1]['height_m'].shape[0] - 1) * spacing / 1000
    fig.suptitle(f'Product mountains | {span_km:g} x {span_km:g} km | X east, Z south | elevation -500 to 4500 m')
    fig.savefig(path, dpi=130)
    plt.close(fig)
    fig, axes = plt.subplots(2, len(cases), figsize=(4 * len(cases), 8), squeeze=False, constrained_layout=True)
    for col, (name, fields) in enumerate(cases):
        h = fields['height_m']
        axes[0, col].imshow(physical_hillshade(h, spacing), cmap='gray', vmin=0, vmax=1)
        axes[0, col].set_title('alpha=' + name.split('_')[-1] + ' hillshade')
        axes[0, col].axis('off')
        ax = fig.add_subplot(2, len(cases), len(cases) + col + 1, projection='3d')
        axes[1, col].remove()
        stride = max(1, int(np.ceil(h.shape[0] / 100)))
        zz, xx = np.mgrid[0:h.shape[0]:stride, 0:h.shape[1]:stride] * spacing / 1000
        sample = h[::stride, ::stride]
        ax.plot_surface(xx, zz, sample / 1000, cmap='gray', vmin=LOW / 1000, vmax=HIGH / 1000, linewidth=0,
                        rcount=sample.shape[0], ccount=sample.shape[1])
        ax.set_zlim(LOW / 1000, HIGH / 1000)
        ax.set_box_aspect((1, 1, .35))
        ax.view_init(elev=25, azim=-60)
        ax.set_title('alpha=' + name.split('_')[-1] + ' bare terrain')
    exaggeration = .35 * span_km / ((HIGH - LOW) / 1000)
    fig.suptitle(f'Product mountains | {span_km:g} x {span_km:g} km | X east, Z south | vertical exaggeration {exaggeration:.2f}x')
    fig.savefig(path.with_name(path.stem + '_terrain.png'), dpi=130)
    plt.close(fig)


def generate(output, size=121, spacing=200., benchmark=False):
    target = Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    if size < 2 or not np.isfinite(spacing) or spacing <= 0:
        raise ValueError('invalid grid')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        source_files = ['terrain_pipeline/product_mountains.py', 'terrain_pipeline/advanced_terrain_filter.py',
                        'terrain_pipeline/voronoi_mountains.py', 'terrain_pipeline/procedural_mountains.py',
                        'terrain_pipeline/terrain_map_style.py', 'diffusion/geographic_noise.py',
                        'terrain_pipeline/common_infra.py', 'tools/prepare_product_mountains.py']
        manifest = {'algorithm_id': PRODUCT_ALGORITHM_ID, 'world_seed': 20260903,
                    'source_sha256': {p: digest(ROOT / p) for p in source_files},
                    'subseeds': {purpose: derive_subseed(20260903, purpose) for purpose in ('product-ridge', 'product-warp', 'product-voronoi-sites')},
                    'subseed_derivation': 'terrain_pipeline.world_seed.derive_subseed',
                    'advanced_filter': {'algorithm_id': ADVANCED_ID,
                        'config': asdict(AdvancedFilterConfig(amplitude_m=150., wavelength_m=1800., octaves=3)),
                        'stable_seed': int.from_bytes(hashlib.sha256(b'advanced-terrain-filter-v1:20260903:phacelle').digest()[:8], 'little'),
                        'stable_seed_derivation': 'SHA256 UTF-8 advanced-terrain-filter-v1:20260903:phacelle, first 8 bytes little-endian uint64'},
                    'macro_formula': 'base_m + amplitude_m * ridge ** ridge_power * ((1-alpha) + alpha * volume)',
                    'ridge_formula': 'clip(1 - (sqrt(n*n + eps*eps) - eps) / (sqrt(1 + eps*eps) - eps), 0, 1); eps=ridge_smoothing',
                    'volume_formula': '1 - product(1 - exp(-2.2*d*d)*cutoff(d)) over 3x3 sites; cutoff=1-smoothstep(1,1.25,d)',
                    'coordinate_convention': 'row Z south, column X east; metres; samples at origin + index * spacing',
                    'mapping': {'minimum_m': LOW, 'maximum_m': HIGH, 'encode': 'round(clip((height_m+500)/5000,0,1)*65535)',
                                'decode': '-500 + code * 5000 / 65535', 'rounding': 'nearest, ties to even'},
                    'plot_geometry': {'surface_stride': max(1, int(np.ceil(size / 100))),
                                      'surface_vertical_exaggeration': .35 * ((size - 1) * spacing) / (HIGH - LOW),
                                      'delta_color_limits_m': [-262.5, 262.5]},
                    'cases': [], 'images': {}, 'benchmark': [], 'timings_seconds': {'generation': 0., 'save': 0., 'plot': 0.}}
        for window, origin in WINDOWS.items():
            cases = []
            for alpha in ((0., .65, 1.) if window == 'main' else (.65,)):
                config = ProductMountainConfig(world_seed=20260903, alpha=alpha, advanced_enabled=True, batch_size=4096)
                x, z = np.meshgrid(origin[0] + np.arange(size) * spacing, origin[1] + np.arange(size) * spacing)
                start = time.perf_counter()
                fields = sample_product_mountains(x, z, config)
                manifest['timings_seconds']['generation'] += time.perf_counter() - start
                name = f'{window}_alpha_{alpha:g}'
                start = time.perf_counter()
                npz = stage / (name + '.npz')
                np.savez_compressed(npz, **{k: np.asarray(v, dtype=np.float64) for k, v in fields.items()})
                item = {'name': name, 'origin_xz_m': origin, 'shape_zx': [size, size], 'spacing_m': spacing,
                        'config': asdict(config), 'npz': npz.name, 'npz_sha256': digest(npz), 'height_images': {}}
                for key in ('macro_height_m', 'height_m'):
                    image_path = stage / (name + '_' + key + '.png')
                    item['height_images'][key] = {'file': image_path.name, **save_height(image_path, fields[key])}
                manifest['cases'].append(item)
                manifest['timings_seconds']['save'] += time.perf_counter() - start
                cases.append((name, fields))
            start = time.perf_counter()
            path = stage / (window + '_comparison.png')
            render(path, cases, spacing)
            manifest['timings_seconds']['plot'] += time.perf_counter() - start
            for p in (path, path.with_name(path.stem + '_terrain.png')):
                manifest['images'][p.name] = digest(p)
        if benchmark:
            for name, origin in [('near', (0., 0.)), ('far', (500000000., -500000000.))]:
                x, z = np.meshgrid(origin[0] + np.arange(512) * 60, origin[1] + np.arange(512) * 60)
                _, stats = measured(lambda: sample_product_mountains(x, z, ProductMountainConfig()))
                manifest['benchmark'].append({'location': name, 'origin_xz_m': origin, 'shape_zx': [512, 512], 'spacing_m': 60, **stats})
            manifest['benchmark_scope'] = 'measured helper: perf_counter wall time, tracemalloc and 10ms sampled whole-process RSS; samples may miss peaks'
        (stage / 'README.md').write_text(
            '# 连续山脊与站点体量场\n\n'
            f'来源：`{PRODUCT_ALGORITHM_ID}`，世界种子 20260903。源代码摘要、参数、计时和量化信息见 manifest.json。\n\n'
            f'网格 {size} × {size}，间距 {spacing:g} 米；行 Z 向南，列 X 向东。'
            '主窗原点 (0, 0) 米，负窗原点 (-24000, -24000) 米。\n\n'
            'R 为平滑连续山脊场；V 由 Voronoi 同类站点的有限支持平滑核融合而成，'
            '不是严格 F1 最近点 Voronoi 距离。主窗展示 alpha=0、0.65、1，负窗展示 0.65。\n\n'
            '高程 PNG 是无阴影的 16 位单通道灰度，固定映射 -500 至 4500 米；'
            '`_preview.png` 为 8 位预览，NPZ 为 float64 米制高程或无量纲场。'
            '对照图单独标注 R/V，山体图仅作阴影可视化。Advanced 是外观滤波，非真实水沙侵蚀。\n', encoding='utf-8')
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        os.rename(stage, target)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--size', type=int, default=121)
    parser.add_argument('--spacing', type=float, default=200.)
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    print(generate(args.output, args.size, args.spacing, args.benchmark))


if __name__ == '__main__':
    main()
