"""Generate reproducible local-volume mountain comparison evidence."""
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
from terrain_pipeline.mountain_forms import LOCAL_VOLUME_ALGORITHM_ID, LocalVolumeConfig, sample_local_volume_mountains
from terrain_pipeline.mountain_forms import PRODUCT_ALGORITHM_ID as ORIGINAL_ID
from terrain_pipeline.mountain_forms import AdvancedFilterConfig, ADVANCED_ALGORITHM_ID as ADVANCED_ID
from terrain_pipeline.terrain_map_style import physical_hillshade
from terrain_pipeline.common_infra import derive_subseed
from tools.prepare_procedural_mountains import measured

LOW, HIGH = -500.0, 6000.0
CASES = [('control', 0., 1.), ('deep_only', 0., 2.4), ('local_only', .35, 1.), ('combined', .35, 2.4)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode_height(height):
    height = np.asarray(height, dtype=np.float64)
    if not np.isfinite(height).all():
        raise ValueError('height must be finite')
    return np.rint(np.clip((height - LOW) / (HIGH - LOW), 0, 1) * 65535).astype(np.uint16)


def decode_height(code):
    return LOW + np.asarray(code, dtype=np.float64) * (HIGH - LOW) / 65535


def save_height(path, height):
    code = encode_height(height)
    Image.fromarray(code, mode='I;16').save(path)
    preview = path.with_name(path.stem + '_preview.png')
    Image.fromarray(np.rint(code.astype(np.float64) / 257).astype(np.uint8), mode='L').save(preview)
    with Image.open(path) as image:
        actual = np.asarray(image)
    return {'file': path.name, 'sha256': digest(path), 'preview_sha256': digest(preview),
            'min_m': float(np.min(height)), 'max_m': float(np.max(height)),
            'saturated_below_count': int(np.count_nonzero(height < LOW)),
            'saturated_above_count': int(np.count_nonzero(height > HIGH)),
            'png_matches_encoded': bool(np.array_equal(actual, code)),
            'max_abs_decode_error_m': float(np.max(np.abs(decode_height(actual) - height)))}


def render(path, cases, spacing, origin):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    span = (cases[0][1]['height_m'].shape[0] - 1) * spacing / 1000
    extent = [origin[0]/1000, (origin[0]+span*1000)/1000, (origin[1]+span*1000)/1000, origin[1]/1000]
    fig, axes = plt.subplots(1, len(cases), figsize=(4*len(cases), 4), squeeze=False, constrained_layout=True)
    for ax, (name, f) in zip(axes[0], cases):
        ax.imshow(f['height_m'], cmap='gray', vmin=LOW, vmax=HIGH, extent=extent)
        ax.set_title(name + ' | elevation (m)')
        ax.set_xlabel('X east (km)'); ax.set_ylabel('Z south (km)')
    fig.suptitle('Fixed elevation mapping: -500 to 6000 m')
    fig.savefig(path, dpi=140); plt.close(fig)
    fig = plt.figure(figsize=(4*len(cases), 8), constrained_layout=True)
    stride = max(1, int(np.ceil(cases[0][1]['height_m'].shape[0] / 100)))
    for i, (name, f) in enumerate(cases):
        h = f['height_m']
        ax = fig.add_subplot(2, len(cases), i+1)
        ax.imshow(physical_hillshade(h, spacing), cmap='gray', vmin=0, vmax=1, extent=extent)
        ax.set_title(name + ' | hillshade'); ax.set_xlabel('X east (km)'); ax.set_ylabel('Z south (km)')
        ax = fig.add_subplot(2, len(cases), len(cases)+i+1, projection='3d')
        sample = h[::stride, ::stride]
        zz, xx = np.mgrid[0:h.shape[0]:stride, 0:h.shape[1]:stride] * spacing / 1000
        ax.plot_surface(xx+origin[0]/1000, zz+origin[1]/1000, sample/1000, cmap='gray', vmin=LOW/1000, vmax=HIGH/1000, linewidth=0, rcount=sample.shape[0], ccount=sample.shape[1])
        ax.set_zlim(LOW/1000, HIGH/1000); ax.set_box_aspect((1, 1, .35)); ax.view_init(elev=25, azim=-60)
        ax.set_title(name + ' | bare surface'); ax.set_xlabel('X km'); ax.set_ylabel('Z km'); ax.set_zlabel('height km')
    fig.suptitle(f'Hillshade and bare surface | stride {stride} | vertical exaggeration {.35 * span / ((HIGH-LOW)/1000):.2f}x')
    fig.savefig(path.with_name(path.stem + '_terrain.png'), dpi=140); plt.close(fig)
    if len(cases) != 4:
        return
    data = dict(cases)
    diffs = [('deep − control', data['deep_only']['height_m']-data['control']['height_m']),
             ('local − control', data['local_only']['height_m']-data['control']['height_m']),
             ('combined − control', data['combined']['height_m']-data['control']['height_m'])]
    limit = max(1., max(float(np.max(np.abs(d))) for _, d in diffs))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
    for ax, (name, d) in zip(axes, diffs):
        im = ax.imshow(d, cmap='coolwarm', vmin=-limit, vmax=limit, extent=extent)
        ax.set_title(name + ' | actual height difference (m)'); ax.set_xlabel('X east (km)'); ax.set_ylabel('Z south (km)')
        fig.colorbar(im, ax=ax, shrink=.8)
    fig.savefig(path.with_name(path.stem + '_differences.png'), dpi=140); plt.close(fig)
    indices = np.arange(cases[0][1]['height_m'].shape[0]) * spacing
    selected = (indices >= 9000) & (indices <= 15000)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), constrained_layout=True)
    for i, (name, f) in enumerate(cases):
        local = f['height_m'][np.ix_(selected, selected)]
        axes[0, i].imshow(local, cmap='gray', vmin=LOW, vmax=HIGH, extent=[9, 15, 15, 9])
        axes[0, i].set_title(name + ' | 9–15 km'); axes[0, i].set_xlabel('X km'); axes[0, i].set_ylabel('Z km')
        axes[1, i].plot(indices[selected]/1000, f['height_m'][np.argmin(abs(indices-12000)), selected])
        axes[1, i].set_title(name + ' | Z = 12 km'); axes[1, i].set_xlabel('X km'); axes[1, i].set_ylabel('height m')
        axes[1, i].set_ylim(LOW, HIGH); axes[1, i].grid(True)
    fig.savefig(path.with_name(path.stem + '_local_profiles.png'), dpi=140); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4), constrained_layout=True)
    row = np.argmin(abs(indices-12000))
    for label, changed, baseline in [('deep − control', 'deep_only', 'control'), ('combined − local', 'combined', 'local_only')]:
        difference = data[changed]['height_m'][row, selected] - data[baseline]['height_m'][row, selected]
        ax.plot(indices[selected]/1000, difference, label=label)
    ax.axhline(0, color='black', linewidth=.7)
    ax.set_title('Actual depth-gain difference | Z = 12 km'); ax.set_xlabel('X east (km)'); ax.set_ylabel('height difference (m)')
    ax.grid(True); ax.legend()
    fig.savefig(path.with_name(path.stem + '_depth_profile.png'), dpi=140); plt.close(fig)


def generate(output, size=121, spacing=200., benchmark=False):
    target = Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    if size < 2 or not np.isfinite(spacing) or spacing <= 0:
        raise ValueError('invalid grid')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        sources = ['terrain_pipeline/local_volume_mountains.py', 'terrain_pipeline/product_mountains.py', 'terrain_pipeline/advanced_terrain_filter.py', 'terrain_pipeline/common_infra.py', 'diffusion/geographic_noise.py', 'terrain_pipeline/terrain_map_style.py', 'tools/prepare_local_volume_mountains.py']
        manifest = {'algorithm_id': LOCAL_VOLUME_ALGORITHM_ID, 'original_algorithm_id': ORIGINAL_ID, 'world_seed': 20260903,
                    'source_sha256': {p: digest(ROOT / p) for p in sources},
                    'subseed_derivation': 'terrain_pipeline.world_seed.derive_subseed',
                    'subseeds': {purpose: derive_subseed(20260903, purpose) for purpose in ('product-ridge', 'product-warp', 'product-voronoi-sites', 'local-volume-sites', 'local-volume-selection')},
                    'advanced_filter': {'algorithm_id': ADVANCED_ID, 'config': asdict(AdvancedFilterConfig(amplitude_m=150., wavelength_m=1800., octaves=3)), 'stable_seed': int.from_bytes(hashlib.sha256(b'advanced-terrain-filter-v1:20260903:phacelle').digest()[:8], 'little')},
                    'coordinate_convention': 'row Z south, column X east; origin + index * spacing, metres',
                    'mapping': {'minimum_m': LOW, 'maximum_m': HIGH, 'encoding': 'round(clip((height+500)/6500,0,1)*65535)', 'legacy_mapping': 'previous product images use -500 to 4500 m'},
                    'formulas': {'original_macro': 'product-mountains-v2-smooth-mass, default alpha=0.65, Advanced disabled', 'local_macro': 'H0 + k * P * max(H0 - 200 m, 0)', 'fade': 'smoothstep(0.02, 0.08, hypot(slope_x, slope_z))', 'actual_advanced_delta': 'fade * (raw_delta * depth_gain if raw_delta < 0 else raw_delta)', 'control': 'k=0, gain=1, with slope fade; not the old un-faded product baseline', 'boundary': 'P=0 guarantees macro equality only; Advanced neighborhood up to 600 m can change final heights near patch edges'},
                    'plot_geometry': {'surface_stride': max(1, int(np.ceil(size/100))), 'surface_rcount_ccount': 'actual strided array dimensions', 'vertical_exaggeration': .35*(size-1)*spacing/(HIGH-LOW)},
                    'cases': [], 'images': {}, 'benchmark': [], 'timings_seconds': {'generation': 0., 'save': 0., 'plot': 0.}}
        for window, origin, choices in [('main', (0., 0.), CASES), ('negative', (-24000., -24000.), [CASES[-1]])]:
            cases = []
            x, z = np.meshgrid(origin[0] + np.arange(size)*spacing, origin[1] + np.arange(size)*spacing)
            for name, k, gain in choices:
                config = LocalVolumeConfig(k=k, depth_gain=gain)
                start = time.perf_counter(); fields = sample_local_volume_mountains(x, z, config)
                manifest['timings_seconds']['generation'] += time.perf_counter()-start
                start = time.perf_counter()
                npz = stage / f'{window}_{name}.npz'
                np.savez_compressed(npz, **{key: np.asarray(value, dtype=np.float64) for key, value in fields.items()})
                outside = fields['selection_w'] == 0
                item = {'name': f'{window}_{name}', 'origin_xz_m': origin, 'shape_zx': [size, size], 'spacing_m': spacing, 'config': asdict(config), 'npz': npz.name, 'npz_sha256': digest(npz),
                        'selection_support_fraction': float(np.mean(~outside)), 'p_support_fraction': float(np.mean(fields['p'] > 0)),
                        'outside_selection_macro_max_abs_error_m': float(np.max(np.abs(fields['macro_height_m'][outside]-fields['h0_m'][outside]))) if np.any(outside) else None,
                        'outside_patch_macro_max_abs_error_m': float(np.max(np.abs(fields['macro_height_m'][fields['p'] == 0]-fields['h0_m'][fields['p'] == 0]))) if np.any(fields['p'] == 0) else None,
                        'max_volume_lift_m': float(np.max(fields['volume_delta_m'])), 'raw_delta_min_m': float(np.min(fields['raw_advanced_delta_m'])), 'raw_delta_max_m': float(np.max(fields['raw_advanced_delta_m'])),
                        'final_delta_min_m': float(np.min(fields['final_delta_m'])), 'final_delta_max_m': float(np.max(fields['final_delta_m'])),
                        'height_images': {key: save_height(stage / f'{window}_{name}_{key}.png', fields[key]) for key in ('macro_height_m', 'height_m')}}
                manifest['cases'].append(item); manifest['timings_seconds']['save'] += time.perf_counter()-start
                cases.append((name, fields))
            start = time.perf_counter(); path = stage / f'{window}_comparison.png'; render(path, cases, spacing, origin)
            manifest['timings_seconds']['plot'] += time.perf_counter()-start
            for p in stage.glob(f'{window}_comparison*.png'):
                manifest['images'][p.name] = digest(p)
        if benchmark:
            for name, origin in [('near', (0., 0.)), ('far', (500000000., -500000000.))]:
                x, z = np.meshgrid(origin[0]+np.arange(512)*60, origin[1]+np.arange(512)*60)
                _, stats = measured(lambda: sample_local_volume_mountains(x, z, LocalVolumeConfig()))
                manifest['benchmark'].append({'location': name, 'origin_xz_m': origin, 'shape_zx': [512, 512], 'spacing_m': 60, **stats})
            manifest['benchmark_scope'] = 'measured: wall time, tracemalloc and sampled whole-process RSS; peaks may be missed'
        (stage/'README.md').write_text(f'# 局部站点体量与深沟壑\n\n来源 `{LOCAL_VOLUME_ALGORITHM_ID}`，原宏观 `{ORIGINAL_ID}`（默认 alpha=0.65，关闭 Advanced）；世界种子 20260903。详细来源、参数、子种子、量化和计时见 manifest.json。control 已使用坡度淡入，不能视为上一轮未淡入的基准。\n\n网格 {size} × {size}，间距 {spacing:g} 米。行 Z 向南、列 X 向东；主窗原点 (0,0)，负窗原点 (-24000,-24000) 米。P=0 的体量区外宏观不变，但 Advanced 使用 600 米邻域，区外边缘的最终高程仍可能改变。\n\n16 位单通道原始高程及 8 位预览统一固定 -500 至 6000 米、黑低白高，与旧图的 -500 至 4500 米映射不同。NPZ 字段为 float64。阴影及裸山图仅用于观察；Advanced 是外观雕刻，不是水沙侵蚀。\n', encoding='utf-8')
        (stage/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        os.rename(stage, target)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output'); parser.add_argument('--size', type=int, default=121); parser.add_argument('--spacing', type=float, default=200.); parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args(); print(generate(args.output, args.size, args.spacing, args.benchmark))


if __name__ == '__main__':
    main()
