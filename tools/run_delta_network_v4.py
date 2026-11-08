#!/usr/bin/env python
"""Run the complex delta network v4 (site -> skeleton (= v3) -> channel-built land v3 -> v4 post-processing)
and draw the figures, including the comparison with the reference images (ref2, ref3).

    runtime/venv/Scripts/python.exe -B tools/run_delta_network_v4.py
    runtime/venv/Scripts/python.exe -B tools/run_delta_network_v4.py --variants base --no-figs --out <dir>

Products (per variant, under --out/<variant>/): bed_dem_float64.npy, water_mask.npy, island_labels.npy,
spit_mask.npy, channel_mask.npy, tidal_mask.npy, sand_mask.npy, channel_graph.json, metrics.json,
manifest.json, sha256sums.json.  CPU only (numpy/scipy/skimage); no clock, entropy or hash() is used.
v1-v3 products are never touched.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from terrain_pipeline import delta_network_site as site                 # noqa: E402
from terrain_pipeline import delta_network_skeleton_v3 as sk3           # noqa: E402
from terrain_pipeline import delta_network_skeleton_v4 as sk4           # noqa: E402
from terrain_pipeline import delta_network_terrain_v3 as ter3           # noqa: E402
from terrain_pipeline import delta_network_terrain_v4 as ter4           # noqa: E402
import run_delta_network_v1 as r1                                       # noqa: E402
import run_delta_network_v3 as r3                                       # noqa: E402
import delta_reference_metrics as drm                                   # noqa: E402

SCRATCH = os.path.join(ROOT, '.scratch', 'delta-network-v1-20261105')
DEFAULT_OUT = os.path.join(SCRATCH, 'skeleton-v4')
DEFAULT_FIGS = os.path.join(ROOT, '验收图片', '复杂三角洲水网v4-20261105')
REF_JSON = os.path.join(SCRATCH, 'work', 'reference_metrics.json')
REF_DIR = os.path.join(SCRATCH, 'reference')
VARIANTS = r3.VARIANTS
VARIANT_TITLE = r3.VARIANT_TITLE
U_EDGES = r3.U_EDGES

TABLE_KEYS = [
    ('trunk_width_over_L0', '干流宽 / √面积'),
    ('skeleton_len_over_L0', '汊道骨架长 / √面积'),
    ('junction_density_per_L0', '分汊+汇合点密度 / √面积'),
    ('loops_per_junction', '环数 / 节点数'),
    ('water_fraction', '水体面积比'),
    ('largest_block_share', '最大陆块占陆地比'),
    ('block_aspect.p50', '陆块长宽比中位'),
    ('front_tongue_aspect.p50', '前缘陆舌长宽比中位'),
    ('width_norm.p50', '汊宽中位 / 主干宽'),
    ('sand_fraction_of_extent', '沙洲占三角洲范围比'),
    ('sand_block_mean_area_over_w2', '沙洲平均面积 / 主干宽²'),
    ('sand_block_touch_channels.mean', '每块沙洲接触汊道数(均)'),
    ('n_sand_cross_channel_ge2', '跨汊(≥2)沙洲块数'),
    ('n_sand_blocks', '沙洲块数'),
]


def code_identity():
    out = {}
    for mod in (site, sk3, sk4, ter3, ter4, r1.sk, r1.ter, drm):
        out[os.path.relpath(mod.__file__, ROOT).replace('\\', '/')] = r1.sha256_file(mod.__file__)
    out['tools/run_delta_network_v4.py'] = r1.sha256_file(os.path.abspath(__file__))
    return out


def ref_masks_metrics(T):
    m = drm.masks_from_arrays(T['chan'] & ~T['tidal'], T['tidal'], T['water'], ~T['water'], T['bed'],
                              sand_mask=T['sand'])
    met = drm._clean(drm.compute_metrics(m['chan'], m['sand'], m['veg'], m['sea'], 'v4'))
    return m, met


def run_variant(name, outroot, td_cache, tp=None):
    over = VARIANTS[name]
    p = dataclasses.replace(sk4.DeltaParamsV4(), variant=name, **over)
    tp = tp or ter4.TerrainParamsV4()
    spec, tdb, tdo = td_cache
    g = sk4.build_delta_network_v4(p)
    rep = sk4.validate_graph(g)
    skm = sk4.skeleton_metrics_v4(g)
    n_act, w_act = sk4.activity_profile(g, U_EDGES)
    su, cu = sk4.event_profile(g)
    skm['activity_profile'] = dict(u_km=(U_EDGES / 1000.0).tolist(), active_channels=n_act.tolist(),
                                   summed_width_m=w_act.tolist())
    T = ter4.build_terrain_v4(spec, g, tdb, tdo, tp)
    tm = ter4.terrain_metrics_v4(spec, g, T)
    masks, refm = ref_masks_metrics(T)
    od = os.path.join(outroot, name)
    os.makedirs(od, exist_ok=True)
    arrays = {
        'bed_dem_float64.npy': T['bed'].astype(np.float64),
        'water_mask.npy': T['water'].astype(np.uint8),
        'island_labels.npy': T['island_label'].astype(np.int32),
        'spit_mask.npy': T['spit'].astype(np.uint8),
        'channel_mask.npy': T['chan'].astype(np.uint8),
        'tidal_mask.npy': T['tidal'].astype(np.uint8),
        'sand_mask.npy': T['sand'].astype(np.uint8),
    }
    for fn, a in arrays.items():
        np.save(os.path.join(od, fn), a)
    r1.write_json(os.path.join(od, 'channel_graph.json'), r1.graph_dict(g, spec))
    metrics = dict(validation=rep, skeleton=skm, terrain=tm, reference_style=refm,
                   nan_in_bed=int(np.isnan(arrays['bed_dem_float64.npy']).sum()))
    r1.write_json(os.path.join(od, 'metrics.json'), metrics)
    window = dict(
        local_u_m=[spec.u0_m, spec.u0_m + spec.nu * spec.spacing_m],
        local_v_m=[spec.v0_m, spec.v0_m + spec.nv * spec.spacing_m],
        shape=[spec.nu, spec.nv], spacing_m=spec.spacing_m,
        index_order='[i_u, j_v]; cell centre u=u0+(i+.5)*dx, v=v0+(j+.5)*dx')
    manifest = dict(
        product='complex-delta-network-v4', producer='Terragenesis', variant=name,
        world_seed=site.WORLD_SEED,
        seed_derivation="sub_seed = first 8 bytes (big endian) of SHA256('world_seed|purpose|repr(extra)'); "
                        "rng = numpy.random.Generator(PCG64(sub_seed)); no hash(), clock or OS entropy; "
                        "ties are broken by absolute world coordinates / stable index order",
        derived_seeds={**{k: str(v) for k, v in g.seeds.items()},
                       'terrain_v3': str(site.derive_seed('delta-network-v3/terrain', name)),
                       'terrain_v4': str(site.derive_seed('delta-network-v4/terrain', name))},
        site=spec.to_dict(), window=window, td_source=r1.td_cache_identity(),
        params=dict(delta=p.to_dict(), terrain=tp.to_dict()),
        code_sha256=code_identity(),
        compute='CPU only (numpy/scipy/skimage); no GPU, no Terrain Diffusion sampling; TD terrain read from saved npy',
        declared='sand/vegetation split, apron/bank/old-lobe sand widths, shoal gain/noise and all v3 scenario '
                 'numbers are declared scenario values calibrated against the reference-image segmentation '
                 '(tools/delta_reference_metrics.py), not measured geology',
        metrics=metrics)
    r1.write_json(os.path.join(od, 'manifest.json'), manifest)
    sums = {fn: r1.sha256_file(os.path.join(od, fn)) for fn in
            sorted(list(arrays) + ['channel_graph.json', 'metrics.json', 'manifest.json'])}
    r1.write_json(os.path.join(od, 'sha256sums.json'), sums)
    return dict(name=name, params=p, g=g, T=T, metrics=metrics, spec=spec, sums=sums, outdir=od,
                split_u=su, conf_u=cu, activity=n_act, masks=masks)


# ----------------------------------------------------------------------------- figures
def rgb_v4(T, dx):
    """Remote-sensing-like colours; sand uses the explicit sand mask."""
    from scipy import ndimage as ndi
    bed, water, chan = T['bed'], T['water'], T['chan']
    wlev = np.where(chan, np.maximum(0.0, T['z_plain'] - 0.8), 0.0)
    depth = np.where(chan, np.clip(wlev - bed, 0, None), np.clip(-bed, 0, None))
    stops = np.array([0.0, 1.2, 3.0, 7.0, 25.0])
    cols = np.array([(160, 208, 232), (112, 176, 222), (54, 112, 182), (22, 62, 130), (10, 34, 86)], float)
    rgb = np.zeros(bed.shape + (3,))
    for k in range(3):
        rgb[..., k] = np.interp(depth, stops, cols[:, k])
    z = np.clip(bed, 0, None)
    gcol = np.array([(128, 170, 98), (96, 148, 76), (84, 128, 64), (118, 124, 84)], float)
    gz = np.array([0.0, 1.0, 6.0, 25.0])
    land_rgb = np.zeros_like(rgb)
    for k in range(3):
        land_rgb[..., k] = np.interp(z, gz, gcol[:, k])
    sw = ndi.gaussian_filter(T['sand'].astype(float), 0.8)
    land_rgb = land_rgb * (1 - sw[..., None]) + np.array((228, 210, 160), float) * sw[..., None]
    rgb = np.where((~water)[..., None], land_rgb, rgb)
    return np.clip(rgb / 255.0, 0, 1)


def fig_remote(res, path):
    plt = r1._setup_mpl()
    from matplotlib.patches import Patch
    spec = res['spec']
    rgb = rgb_v4(res['T'], spec.spacing_m)
    fig, ax = plt.subplots(figsize=(11.5, 11))
    ax.imshow(rgb, extent=r1._extent_km(spec), origin='upper', interpolation='nearest')
    ax.plot([-22.5, -17.5], [41.0, 41.0], c='k', lw=4)
    ax.plot([-22.5, -17.5], [41.0, 41.0], c='w', lw=1.5)
    ax.text(-20, 42.2, '5 km', ha='center', va='bottom', color='w', fontsize=11,
            bbox=dict(fc='k', ec='none', alpha=.55, pad=1.5))
    m = res['metrics']
    t = m['terrain']
    rm = m['reference_style']
    ax.set_title('复杂三角洲水网v4 遥感配色平面图 — %s\n入海口 %d,环 %d;沙洲占范围 %.0f%%(参考图3:22%%),跨汊沙洲块 %d;顶点→最远岸线 %.1f km,沿岸宽 %.1f km' % (
        VARIANT_TITLE[res['name']], m['skeleton']['n_mouths'], m['skeleton']['loops'],
        100 * rm['sand_fraction_of_extent'], rm['n_sand_cross_channel_ge2'],
        t['apex_to_farthest_shore_km'], t['alongshore_width_u_ge_3km_km']), fontsize=11.5)
    ax.legend(handles=[Patch(fc=np.array((10, 34, 86)) / 255, label='深水(>7 m)'),
                       Patch(fc=np.array((54, 112, 182)) / 255, label='中等水深'),
                       Patch(fc=np.array((160, 208, 232)) / 255, label='浅水(<1.2 m)'),
                       Patch(fc=np.array((228, 210, 160)) / 255, label='沙洲/沙坪(显式 sand_mask)'),
                       Patch(fc=np.array((96, 148, 76)) / 255, label='植被陆地(绿)')],
              loc='upper right', fontsize=9, framealpha=.9)
    r1._axes_labels(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return rgb


def fig_compare(results, rgbs, path):
    plt = r1._setup_mpl()
    n = len(results)
    fig, axs = plt.subplots(1, n, figsize=(7.2 * n, 8.2))
    for ax, res, rgb in zip(np.atleast_1d(axs), results, rgbs):
        m = res['metrics']
        rm = m['reference_style']
        ax.imshow(rgb, extent=r1._extent_km(res['spec']), origin='upper', interpolation='nearest')
        ax.set_title('%s  (variant=%s)' % (VARIANT_TITLE[res['name']], res['name']), fontsize=12)
        ax.set_xlabel('环 %d | 入海口 %d | 沙洲占范围 %.0f%% | 跨汊沙洲 %d 块\n顶点→最远岸 %.1f km | 沿岸宽 %.1f km' % (
            m['skeleton']['loops'], m['skeleton']['n_mouths'], 100 * rm['sand_fraction_of_extent'],
            rm['n_sand_cross_channel_ge2'], m['terrain']['apex_to_farthest_shore_km'],
            m['terrain']['alongshore_width_u_ge_3km_km']), fontsize=10)
    fig.suptitle('v4 参数/种子对比:环少(接近参考图3) — 基准 — 环多(接近参考图2)', fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _mask_rgb(m):
    rgb = np.ones(m['chan'].shape + (3,), float)
    rgb[m['sea']] = (0.62, 0.78, 0.92)
    rgb[m['veg']] = (0.30, 0.58, 0.32)
    rgb[m['sand']] = (0.97, 0.88, 0.55)
    rgb[m['chan']] = (0.05, 0.15, 0.55)
    return rgb


def _get(d, key):
    for part in key.split('.'):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d if isinstance(d, (int, float)) else None


def _fmt(v):
    if v is None:
        return '—'
    return ('%.3f' % v) if abs(v) < 100 else ('%.0f' % v)


def fig_masks_table(base, path):
    plt = r1._setup_mpl()
    ref = json.load(open(REF_JSON, encoding='utf-8'))
    r2 = drm.segment_ref2()
    r3m = drm.segment_ref3()
    fig = plt.figure(figsize=(17, 13))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.85], hspace=0.12, wspace=0.05)
    for k, (m, ttl) in enumerate(((r2, '参考图2 掩码(深蓝=汊道,绿=植被陆地,浅蓝=海/水)'),
                                  (r3m, '参考图3 掩码(蓝=汊道,浅黄=沙洲,绿=植被,浅蓝=海)'),
                                  (base['masks'], 'v4 基准 掩码(同一分割口径)'))):
        ax = fig.add_subplot(gs[0, k])
        rgb = _mask_rgb(m)
        if k == 2:
            rgb = rgb[70:, :]
        ax.imshow(rgb, interpolation='nearest')
        ax.set_title(ttl, fontsize=11)
        ax.axis('off')
    ax = fig.add_subplot(gs[1, :])
    ax.axis('off')
    rm = base['metrics']['reference_style']
    rows = []
    for key, lab in TABLE_KEYS:
        rows.append([lab, _fmt(_get(ref['ref2'], key)), _fmt(_get(ref['ref3'], key)),
                     _fmt(_get(ref['v3'], key)), _fmt(_get(rm, key))])
    tb = ax.table(cellText=rows, colLabels=['指标(无量纲)', '参考图2', '参考图3', 'v3 基准', 'v4 基准'],
                  loc='center', cellLoc='center', colWidths=[0.34, 0.15, 0.15, 0.15, 0.15])
    tb.auto_set_font_size(False)
    tb.set_fontsize(11)
    tb.scale(1, 1.55)
    fig.suptitle('参考图掩码与指标对比(长度除以 √三角洲范围面积;宽度除以主干宽)', fontsize=14)
    fig.savefig(path, dpi=90, bbox_inches='tight')
    plt.close(fig)


def fig_side_by_side(base, rgb, path):
    from PIL import Image
    plt = r1._setup_mpl()
    spec = base['spec']
    im2 = np.asarray(Image.open(os.path.join(REF_DIR, 'ref2-plain-network.png')).convert('RGB'))
    im3 = np.asarray(Image.open(os.path.join(REF_DIR, 'ref3-small-estuary.png')).convert('RGB'))
    fig, axs = plt.subplots(1, 3, figsize=(21, 8.2), gridspec_kw=dict(width_ratios=[im2.shape[1] / im2.shape[0] * 0.9,
                                                                                   1.0, 1.0]))
    axs[0].imshow(im2)
    axs[0].set_title('参考图2(平原分汊网络)', fontsize=12)
    axs[1].imshow(rgb, extent=r1._extent_km(spec), origin='upper', interpolation='nearest')
    axs[1].set_title('v4 基准 遥感配色平面图', fontsize=12)
    axs[2].imshow(im3)
    axs[2].set_title('参考图3(小型河口:沙洲与前缘)', fontsize=12)
    axs[0].axis('off')
    axs[2].axis('off')
    r1._axes_labels(axs[1])
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--variants', default=','.join(VARIANTS))
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--figs', default=DEFAULT_FIGS)
    ap.add_argument('--no-figs', action='store_true')
    a = ap.parse_args(argv)
    names = [v for v in a.variants.split(',') if v]
    anchor = site.find_anchor(os.path.join(ROOT, site.TD_DIR), t=0.30)
    spec = site.SiteSpec(anchor_world_m=anchor)
    tdb, tdo, inside = site.sample_td(spec)
    assert inside.all(), 'window leaves the TD tile'
    results, rgbs = [], []
    os.makedirs(a.out, exist_ok=True)
    top = {}
    r1.VARIANT_TITLE.update(VARIANT_TITLE)
    r3.VARIANT_TITLE.update(VARIANT_TITLE)
    base_keep = None
    for nm in names:
        res = run_variant(nm, a.out, (spec, tdb, tdo))
        m = res['metrics']
        rm = m['reference_style']
        print('[%s] ok=%s mouths=%d loops=%d islands=%d far=%.1fkm width=%.1fkm sand=%.2f cross2=%d blocks=%d' % (
            nm, m['validation']['ok'], m['skeleton']['n_mouths'], m['skeleton']['loops'],
            m['terrain']['n_islands'], m['terrain']['apex_to_farthest_shore_km'],
            m['terrain']['alongshore_width_u_ge_3km_km'], rm['sand_fraction_of_extent'],
            rm['n_sand_cross_channel_ge2'], rm['n_land_blocks']), flush=True)
        top[nm] = res['sums']
        if not a.no_figs:
            os.makedirs(a.figs, exist_ok=True)
            rgb = fig_remote(res, os.path.join(a.figs, '1_遥感配色平面图_%s_v4.png' % nm))
            r3.fig_diag(res, os.path.join(a.figs, '2_汊道诊断图_%s_v4.png' % nm))
            r1.fig_dem(res, os.path.join(a.figs, '3_床面DEM与横剖面_%s_v4.png' % nm))
            rgbs.append(rgb[::2, ::2])
            if nm == 'base':
                base_keep = (res['masks'], rgb)
        base_res = res if nm == 'base' else None
        if base_res is not None and not a.no_figs:
            fig_masks_table(base_res, os.path.join(a.figs, '7_参考图掩码与指标对比_v4.png'))
            fig_side_by_side(base_res, base_keep[1], os.path.join(a.figs, '8_v4与参考图并排_v4.png'))
        res['T'] = None
        res['masks'] = None
        results.append(res)
    r1.write_json(os.path.join(a.out, 'sha256sums_all.json'), top)
    if not a.no_figs:
        r3.fig_activity(results, os.path.join(a.figs, '5_活动汊道数随u变化_v4.png'))
        r3.fig_events(results, os.path.join(a.figs, '6_分汊汇合点分布直方图_v4.png'))
        if len(results) > 1:
            fig_compare(results, rgbs, os.path.join(a.figs, '4_参数种子对比_v4.png'))
    return results


if __name__ == '__main__':
    main()
