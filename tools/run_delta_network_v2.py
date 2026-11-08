#!/usr/bin/env python
"""Run the complex delta network v2 (site -> channel skeleton v2 -> channel-built land v2) and draw the figures.

    runtime/venv/Scripts/python.exe -B tools/run_delta_network_v2.py
    runtime/venv/Scripts/python.exe -B tools/run_delta_network_v2.py --variants base --no-figs --out <dir>

Products (per variant, under --out/<variant>/): bed_dem_float64.npy, water_mask.npy, island_labels.npy,
spit_mask.npy, channel_mask.npy, tidal_mask.npy, channel_graph.json, metrics.json, manifest.json,
sha256sums.json.  No wall-clock time, entropy or hash() is used: same parameters -> byte-identical outputs.
v1 products (skeleton-v1/) are never touched.
"""
from __future__ import annotations

import argparse
import dataclasses
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from terrain_pipeline import delta_network_site as site                 # noqa: E402
from terrain_pipeline import delta_network_skeleton_v2 as sk2           # noqa: E402
from terrain_pipeline import delta_network_terrain_v2 as ter2           # noqa: E402
import run_delta_network_v1 as r1                                       # noqa: E402

SCRATCH = os.path.join(ROOT, '.scratch', 'delta-network-v1-20261105')
DEFAULT_OUT = os.path.join(SCRATCH, 'skeleton-v2')
DEFAULT_FIGS = os.path.join(ROOT, '验收图片', '复杂三角洲水网v2-20261105')

VARIANTS = {
    'base': dict(),
    'few_loops': dict(link_prob=0.08, link_donor_q_min=2500.0, spacing_plain_m=3200.0, spacing_front_m=900.0,
                      split_gap_factor=1.8),
    'many_loops': dict(link_prob=0.95, link_donor_q_min=300.0, spacing_plain_m=1800.0, spacing_front_m=550.0,
                       split_gap_factor=1.25),
}
VARIANT_TITLE = {'base': '基准参数', 'few_loops': '环少(接近参考图3)', 'many_loops': '环多(接近参考图2)'}
U_EDGES = np.arange(500.0, 44000.0, 500.0)


def code_identity():
    out = {}
    for mod in (site, sk2, ter2):
        out[os.path.relpath(mod.__file__, ROOT).replace('\\', '/')] = r1.sha256_file(mod.__file__)
    for mod in (r1.sk, r1.ter):                      # shared v1 helpers imported by v2
        out[os.path.relpath(mod.__file__, ROOT).replace('\\', '/')] = r1.sha256_file(mod.__file__)
    out['tools/run_delta_network_v2.py'] = r1.sha256_file(os.path.abspath(__file__))
    return out


def run_variant(name, outroot, td_cache, tp=None):
    over = VARIANTS[name]
    p = dataclasses.replace(sk2.DeltaParamsV2(), variant=name, **over)
    tp = tp or ter2.TerrainParamsV2()
    spec, tdb, tdo = td_cache
    g = sk2.build_delta_network_v2(p)
    rep = sk2.validate_graph(g)
    skm = sk2.skeleton_metrics_v2(g)
    n_act, w_act = sk2.activity_profile(g, U_EDGES)
    su, cu = sk2.event_profile(g)
    skm['activity_profile'] = dict(u_km=(U_EDGES / 1000.0).tolist(), active_channels=n_act.tolist(),
                                   summed_width_m=w_act.tolist())
    T = ter2.build_terrain_v2(spec, g, tdb, tdo, tp)
    tm = ter2.terrain_metrics_v2(spec, g, T)
    od = os.path.join(outroot, name)
    os.makedirs(od, exist_ok=True)
    arrays = {
        'bed_dem_float64.npy': T['bed'].astype(np.float64),
        'water_mask.npy': T['water'].astype(np.uint8),
        'island_labels.npy': T['island_label'].astype(np.int32),
        'spit_mask.npy': T['spit'].astype(np.uint8),
        'channel_mask.npy': T['chan'].astype(np.uint8),
        'tidal_mask.npy': T['tidal'].astype(np.uint8),
    }
    for fn, a in arrays.items():
        np.save(os.path.join(od, fn), a)
    r1.write_json(os.path.join(od, 'channel_graph.json'), r1.graph_dict(g, spec))
    metrics = dict(validation=rep, skeleton=skm, terrain=tm, nan_in_bed=int(np.isnan(arrays['bed_dem_float64.npy']).sum()))
    r1.write_json(os.path.join(od, 'metrics.json'), metrics)
    window = dict(
        local_u_m=[spec.u0_m, spec.u0_m + spec.nu * spec.spacing_m],
        local_v_m=[spec.v0_m, spec.v0_m + spec.nv * spec.spacing_m],
        shape=[spec.nu, spec.nv], spacing_m=spec.spacing_m,
        index_order='[i_u, j_v]; cell centre u=u0+(i+.5)*dx, v=v0+(j+.5)*dx')
    manifest = dict(
        product='complex-delta-network-v2', producer='Terragenesis', variant=name,
        world_seed=site.WORLD_SEED,
        seed_derivation="sub_seed = first 8 bytes (big endian) of SHA256('world_seed|purpose|repr(extra)'); "
                        "rng = numpy.random.Generator(PCG64(sub_seed)); no hash(), clock or OS entropy; "
                        "ties are broken by absolute world coordinates / stable index order",
        derived_seeds={**{k: str(v) for k, v in g.seeds.items()},
                       'terrain': str(site.derive_seed('delta-network-v2/terrain', name))},
        site=spec.to_dict(), window=window, td_source=r1.td_cache_identity(),
        params=dict(delta=p.to_dict(), terrain=tp.to_dict()),
        code_sha256=code_identity(),
        declared='river discharge, a/c width-depth coefficients, spacing/gap/merge numbers, plain slope, shelf, '
                 'front slope, levee, mouth-lobe/bar/funnel and tidal-creek numbers are declared scenario values; '
                 'exponents b~0.5, f~0.4 from Leopold & Maddock 1953; beta (bifurcation spacing L_b = beta*w) is '
                 'recalled from Edmonds & Slingerland 2007, not re-verified',
        metrics=metrics)
    r1.write_json(os.path.join(od, 'manifest.json'), manifest)
    sums = {fn: r1.sha256_file(os.path.join(od, fn)) for fn in
            sorted(list(arrays) + ['channel_graph.json', 'metrics.json', 'manifest.json'])}
    r1.write_json(os.path.join(od, 'sha256sums.json'), sums)
    return dict(name=name, params=p, g=g, T=T, metrics=metrics, spec=spec, sums=sums, outdir=od,
                split_u=su, conf_u=cu, activity=n_act)


# ----------------------------------------------------------------------------- figures
def fig_remote(res, path):
    plt = r1._setup_mpl()
    from matplotlib.patches import Patch
    spec = res['spec']
    rgb = r1.remote_rgb(res['T'], spec.spacing_m)
    fig, ax = plt.subplots(figsize=(11.5, 11))
    ax.imshow(rgb, extent=r1._extent_km(spec), origin='upper', interpolation='nearest')
    ax.plot([-22.5, -17.5], [41.0, 41.0], c='k', lw=4)
    ax.plot([-22.5, -17.5], [41.0, 41.0], c='w', lw=1.5)
    ax.text(-20, 42.2, '5 km', ha='center', va='bottom', color='w', fontsize=11,
            bbox=dict(fc='k', ec='none', alpha=.55, pad=1.5))
    m = res['metrics']
    t = m['terrain']
    ax.set_title('复杂三角洲水网v2 遥感配色平面图 — %s\n入海口 %d,环 %d,岛 %d(≥0.05 km² %d);顶点→最远岸线 %.1f km,沿岸宽(u≥3km) %.1f km;前缘水道面积占比 %.0f%%' % (
        VARIANT_TITLE[res['name']], m['skeleton']['n_mouths'], m['skeleton']['loops'], t['n_islands'],
        t['n_islands_ge_0p05km2'], t['apex_to_farthest_shore_km'], t['alongshore_width_u_ge_3km_km'],
        100 * t['channel_area_fraction_front']), fontsize=11.5)
    ax.legend(handles=[Patch(fc=np.array((10, 34, 86)) / 255, label='深水(>7 m)'),
                       Patch(fc=np.array((54, 112, 182)) / 255, label='中等水深'),
                       Patch(fc=np.array((160, 208, 232)) / 255, label='浅水(<1.2 m)'),
                       Patch(fc=np.array((228, 210, 160)) / 255, label='沙洲/沙嘴/口门沙坝/小岛'),
                       Patch(fc=np.array((96, 148, 76)) / 255, label='陆地(绿)')],
              loc='upper right', fontsize=9, framealpha=.9)
    r1._axes_labels(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return rgb


def fig_diag(res, path):
    plt = r1._setup_mpl()
    from matplotlib.lines import Line2D
    g, spec, T = res['g'], res['spec'], res['T']
    fig, ax = plt.subplots(figsize=(11.5, 11))
    bg = np.where(T['land_env'], 0.93, 1.0)
    ax.imshow(bg, extent=r1._extent_km(spec), origin='upper', cmap='gray', vmin=0, vmax=1, interpolation='nearest')
    rank_col = {0: '#d62728', 1: '#ff7f0e', 2: '#2ca02c', 3: '#1f77b4'}
    lobe_info = {lb['id']: lb for lb in g.lobes}
    qmax = float(g.edge_q.max())
    for i in np.argsort(g.edge_q)[::-1]:
        P = sk2.edge_points(g, i)
        lb = int(g.edge_lobe[i])
        c = '#555555' if lb < 0 else rank_col.get(lobe_info[lb]['rank'], '#9467bd')
        ax.plot(P[:, 1] / 1000, P[:, 0] / 1000, c=c, lw=0.5 + 7.0 * math.sqrt(g.edge_q[i] / qmax),
                solid_capstyle='round', alpha=.95, zorder=3)
    marks = {'avulsion': ('*', 'k', 12, '改道点'), 'bifurcation': ('o', 'k', 3.0, '分汊'),
             'confluence': ('s', '#7b3fa0', 3.8, '汇合'), 'mouth': ('v', '#e00000', 6, '入海口'),
             'link_start': ('D', '#008b8b', 4.0, '横向连接汊起点'), 'source': ('P', 'k', 10, '入口')}
    for kind, (mk, col, ms, lab) in marks.items():
        idx = np.where(g.node_kind == sk2.NODE_KINDS.index(kind))[0]
        if len(idx):
            ax.plot(g.node_uv[idx, 1] / 1000, g.node_uv[idx, 0] / 1000, mk, c=col, ms=ms, ls='none', label=lab, zorder=5)
    for r, c in rank_col.items():
        lbs = [lb for lb in g.lobes if lb['rank'] == r]
        if lbs:
            ax.plot([], [], c=c, lw=3, label='叶瓣#%d 年龄序%d(%s)份额%.0f%%' % (
                lbs[0]['id'], r, '最新' if r == 0 else '较老', 100 * lbs[0]['share']))
    ax.plot([], [], c='#555555', lw=5, label='主干')
    ax.legend(loc='upper right', fontsize=8.5, framealpha=.92, ncol=2)
    sm = res['metrics']['skeleton']
    ax.set_title('汊道诊断图 — %s:线宽∝√Q,颜色=叶瓣年龄(红=最新最大)\n边 %d,节点 %d,环数 E−V+C=%d,层级 0–%d(无层级上限)' % (
        VARIANT_TITLE[res['name']], len(g.edge_from), len(g.node_uv), sm['loops'], sm['max_level']), fontsize=12)
    ax.set_xlim(-24, 24)
    ax.set_ylim(44, -4)
    r1._axes_labels(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def fig_activity(results, path):
    plt = r1._setup_mpl()
    fig, ax = plt.subplots(figsize=(10, 6))
    cols = {'base': '#d62728', 'few_loops': '#1f77b4', 'many_loops': '#2ca02c'}
    for res in results:
        ax.plot(U_EDGES / 1000, res['activity'], c=cols.get(res['name'], 'k'), lw=2.2 if res['name'] == 'base' else 1.4,
                label=VARIANT_TITLE[res['name']])
    ax.set_xlabel('离海岸基线 u / km(自顶点向海,u 为局部坐标,顶点在 u=−0.6 km)')
    ax.set_ylabel('该 u 截面上穿过的活动汊道数')
    ax.set_title('活动汊道数随 u 的变化(v1 在顶点 10 km 内分汊后保持约 10 条平行线;v2 沿全程保持网状并在前缘增多)')
    ax.grid(alpha=.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def fig_events(results, path):
    plt = r1._setup_mpl()
    n = len(results)
    fig, axs = plt.subplots(1, n, figsize=(6 * n, 5), sharey=True)
    bins = np.arange(0, 44.1, 2.0)
    for ax, res in zip(np.atleast_1d(axs), results):
        ax.hist(res['split_u'] / 1000, bins=bins, alpha=.65, color='#1f77b4', label='分汊点(含改道/连接汊起点)')
        ax.hist(res['conf_u'] / 1000, bins=bins, alpha=.65, color='#7b3fa0', label='汇合点')
        sm = res['metrics']['skeleton']
        ax.set_title('%s\n分汊 %d、汇合 %d;>10 km 的分汊占 %.0f%%' % (
            VARIANT_TITLE[res['name']], sm['n_split_events'], sm['n_confluences'], 100 * sm['frac_splits_beyond_10km']),
            fontsize=11)
        ax.set_xlabel('u / km')
        ax.grid(alpha=.3)
    np.atleast_1d(axs)[0].set_ylabel('节点数 / 2 km')
    np.atleast_1d(axs)[0].legend(fontsize=9)
    fig.suptitle('分汊点与汇合点沿 u 方向的分布', fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def fig_compare(results, rgbs, path):
    plt = r1._setup_mpl()
    n = len(results)
    fig, axs = plt.subplots(1, n, figsize=(7.2 * n, 8.2))
    for ax, res, rgb in zip(np.atleast_1d(axs), results, rgbs):
        m = res['metrics']
        ax.imshow(rgb, extent=r1._extent_km(res['spec']), origin='upper', interpolation='nearest')
        ax.set_title('%s  (variant=%s)' % (VARIANT_TITLE[res['name']], res['name']), fontsize=12)
        ax.set_xlabel('环 %d | 入海口 %d | 层级 0–%d | 岛 %d(≥0.05km² %d)\n汊道总长 %.0f km | 顶点→最远岸 %.1f km | 沿岸宽 %.1f km' % (
            m['skeleton']['loops'], m['skeleton']['n_mouths'], m['skeleton']['max_level'], m['terrain']['n_islands'],
            m['terrain']['n_islands_ge_0p05km2'], m['skeleton']['total_channel_length_km'],
            m['terrain']['apex_to_farthest_shore_km'], m['terrain']['alongshore_width_u_ge_3km_km']), fontsize=10)
    fig.suptitle('v2 参数/种子对比:环少(接近参考图3) — 基准 — 环多(接近参考图2)', fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
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
    for nm in names:
        res = run_variant(nm, a.out, (spec, tdb, tdo))
        m = res['metrics']
        print('[%s] ok=%s mouths=%d loops=%d levels=%d islands=%d far=%.1fkm width=%.1fkm front_chan=%.0f%%' % (
            nm, m['validation']['ok'], m['skeleton']['n_mouths'], m['skeleton']['loops'], m['skeleton']['max_level'],
            m['terrain']['n_islands'], m['terrain']['apex_to_farthest_shore_km'],
            m['terrain']['alongshore_width_u_ge_3km_km'], 100 * m['terrain']['channel_area_fraction_front']), flush=True)
        top[nm] = res['sums']
        if not a.no_figs:
            os.makedirs(a.figs, exist_ok=True)
            rgb = fig_remote(res, os.path.join(a.figs, '1_遥感配色平面图_%s_v2.png' % nm))
            fig_diag(res, os.path.join(a.figs, '2_汊道诊断图_%s_v2.png' % nm))
            r1.VARIANT_TITLE.update(VARIANT_TITLE)
            r1.fig_dem(res, os.path.join(a.figs, '3_床面DEM与横剖面_%s_v2.png' % nm))
            rgbs.append(rgb[::2, ::2])
        res['T'] = None
        results.append(res)
    r1.write_json(os.path.join(a.out, 'sha256sums_all.json'), top)
    if not a.no_figs:
        os.makedirs(a.figs, exist_ok=True)
        fig_activity(results, os.path.join(a.figs, '5_活动汊道数随u变化_v2.png'))
        fig_events(results, os.path.join(a.figs, '6_分汊汇合点分布直方图_v2.png'))
        if len(results) > 1:
            fig_compare(results, rgbs, os.path.join(a.figs, '4_参数种子对比_v2.png'))
    return results


if __name__ == '__main__':
    main()
