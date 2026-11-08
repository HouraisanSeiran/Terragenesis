#!/usr/bin/env python
"""Run the complex delta network v1 (site -> channel skeleton -> land) and draw the figures.

    runtime/venv/Scripts/python.exe -B tools/run_delta_network_v1.py
    runtime/venv/Scripts/python.exe -B tools/run_delta_network_v1.py --variants base --no-figs --out <dir>

Products (per variant, under --out/<variant>/): bed_dem_float64.npy, water_mask.npy,
island_labels.npy, spit_mask.npy, channel_mask.npy, tidal_mask.npy, channel_graph.json,
metrics.json, manifest.json, sha256sums.json.  No wall-clock time, entropy or hash() is used:
same parameters -> byte-identical outputs.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from terrain_pipeline import delta_network_site as site            # noqa: E402
from terrain_pipeline import delta_network_skeleton as sk          # noqa: E402
from terrain_pipeline import delta_network_terrain as ter          # noqa: E402

SCRATCH = os.path.join(ROOT, '.scratch', 'delta-network-v1-20261105')
DEFAULT_OUT = os.path.join(SCRATCH, 'skeleton-v1')
DEFAULT_FIGS = os.path.join(ROOT, '验收图片', '复杂三角洲水网v1-20261105')

VARIANTS = {
    'base': dict(),
    'few_loops': dict(n_lobes=3, link_prob=0.08, link_donor_q_min=2500.0, max_level=4),
    'many_loops': dict(link_prob=0.95, link_donor_q_min=300.0, max_level=6, beta=5.0),
}
VARIANT_TITLE = {'base': '基准参数', 'few_loops': '环少(接近参考图3)', 'many_loops': '环多(接近参考图2)'}


# ----------------------------------------------------------------------------- helpers
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 22), b''):
            h.update(blk)
    return h.hexdigest()


def _j(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(type(o))


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=True, default=_j)
        fh.write('\n')


def graph_dict(g, spec):
    X, Z = site.local_to_world(spec, g.node_uv[:, 0], g.node_uv[:, 1])
    nodes = [dict(id=i, kind=sk.NODE_KINDS[int(g.node_kind[i])], u_m=float(g.node_uv[i, 0]), v_m=float(g.node_uv[i, 1]),
                  world_X_m=float(X[i]), world_Z_m=float(Z[i]), Q_m3s=float(g.node_q[i]))
             for i in range(len(g.node_uv))]
    edges = []
    for i in range(len(g.edge_from)):
        P = sk.edge_points(g, i)
        PX, PZ = site.local_to_world(spec, P[:, 0], P[:, 1])
        edges.append(dict(id=i, **{'from': int(g.edge_from[i]), 'to': int(g.edge_to[i])},
                          Q_m3s=float(g.edge_q[i]), width_m=float(g.edge_w[i]), depth_m=float(g.edge_h[i]),
                          level=int(g.edge_level[i]), lobe=int(g.edge_lobe[i]), kind=sk.EDGE_KINDS[int(g.edge_kind[i])],
                          length_m=float(g.edge_len[i]),
                          path_uv_m=[[float(a), float(b)] for a, b in P],
                          path_world_XZ_m=[[float(a), float(b)] for a, b in zip(PX, PZ)]))
    return dict(coordinate_note='u seaward, v along shore (local metres); world X east, Z south (metres)',
                node_kinds=sk.NODE_KINDS, edge_kinds=sk.EDGE_KINDS, lobes=g.lobes, youngest_lobe=g.youngest,
                nodes=nodes, edges=edges)


def td_identity():
    d = os.path.join(ROOT, site.TD_DIR)
    out = {}
    for name in ('bed_m.npy', 'ocean_mask.npy'):
        p = os.path.join(d, name)
        out[name] = dict(path=os.path.relpath(p, ROOT).replace('\\', '/'), bytes=os.path.getsize(p), sha256=sha256_file(p))
    out['origin_center_m'] = site.TD_ORIGIN_CENTER_M
    out['spacing_m'] = site.TD_SPACING_M
    return out


def code_identity():
    out = {}
    for mod in (site, sk, ter):
        p = mod.__file__
        out[os.path.relpath(p, ROOT).replace('\\', '/')] = sha256_file(p)
    out['tools/run_delta_network_v1.py'] = sha256_file(os.path.abspath(__file__))
    return out


# ----------------------------------------------------------------------------- one variant
def run_variant(name, outroot, td_cache, tp=None):
    over = VARIANTS[name]
    p = dataclasses.replace(sk.DeltaParams(), variant=name, **over)
    tp = tp or ter.TerrainParams()
    spec, tdb, tdo = td_cache
    g = sk.build_delta_network(p)
    rep = sk.validate_graph(g)
    skm = sk.skeleton_metrics(g)
    T = ter.build_terrain(spec, g, tdb, tdo, tp)
    tm = ter.terrain_metrics(spec, g, T)
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
    write_json(os.path.join(od, 'channel_graph.json'), graph_dict(g, spec))
    metrics = dict(validation=rep, skeleton=skm, terrain=tm, nan_in_bed=int(np.isnan(arrays['bed_dem_float64.npy']).sum()))
    write_json(os.path.join(od, 'metrics.json'), metrics)
    window = dict(
        local_u_m=[spec.u0_m, spec.u0_m + spec.nu * spec.spacing_m],
        local_v_m=[spec.v0_m, spec.v0_m + spec.nv * spec.spacing_m],
        shape=[spec.nu, spec.nv], spacing_m=spec.spacing_m,
        index_order='[i_u, j_v]; cell centre u=u0+(i+.5)*dx, v=v0+(j+.5)*dx',
        corners_world_XZ_m=[[float(a), float(b)] for a, b in zip(*[np.ravel(c) for c in site.local_to_world(
            spec, np.array([spec.u0_m, spec.u0_m, spec.u0_m + spec.nu * spec.spacing_m, spec.u0_m + spec.nu * spec.spacing_m]),
            np.array([spec.v0_m, spec.v0_m + spec.nv * spec.spacing_m, spec.v0_m + spec.nv * spec.spacing_m, spec.v0_m]))])])
    manifest = dict(
        product='complex-delta-network-v1', variant=name,
        world_seed=site.WORLD_SEED,
        seed_derivation="sub_seed = first 8 bytes (big endian) of SHA256('world_seed|purpose|repr(extra)'); "
                        "rng = numpy.random.Generator(PCG64(sub_seed)); no hash(), clock or OS entropy; "
                        "ties are broken by absolute world coordinates / stable index order",
        derived_seeds={**{k: str(v) for k, v in g.seeds.items()},
                       'terrain': str(site.derive_seed('delta-network/terrain', name))},
        site=spec.to_dict(), window=window, td_source=td_cache_identity(),
        params=dict(delta=p.to_dict(), terrain=tp.to_dict()),
        code_sha256=code_identity(),
        declared='river discharge, a/c width-depth coefficients, plain slope, shelf, front slope, levee, fan and '
                 'tidal-creek numbers are declared scenario values; exponents b~0.5, f~0.4 from Leopold & Maddock 1953; '
                 'beta (bifurcation spacing L_b = beta*w) is recalled from Edmonds & Slingerland 2007, not re-verified',
        metrics=metrics)
    write_json(os.path.join(od, 'manifest.json'), manifest)
    sums = {fn: sha256_file(os.path.join(od, fn)) for fn in
            sorted(list(arrays) + ['channel_graph.json', 'metrics.json', 'manifest.json'])}
    write_json(os.path.join(od, 'sha256sums.json'), sums)
    return dict(name=name, params=p, g=g, T=T, metrics=metrics, spec=spec, sums=sums, outdir=od)


_TD_ID = {}


def td_cache_identity():
    if not _TD_ID:
        _TD_ID.update(td_identity())
    return _TD_ID


# ----------------------------------------------------------------------------- figures
def _setup_mpl():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'Noto Sans SC', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    return plt


def remote_rgb(T, dx):
    """Remote-sensing-like colours: deep/shallow water, sand bars, green land."""
    from scipy import ndimage as ndi
    bed, water, chan = T['bed'], T['water'], T['chan']
    wlev = np.where(chan, np.maximum(0.0, T['z_plain'] - 0.8), 0.0)
    depth = np.clip(wlev - bed, 0, None)
    stops = np.array([0.0, 1.2, 3.0, 7.0, 25.0])
    cols = np.array([(160, 208, 232), (112, 176, 222), (54, 112, 182), (22, 62, 130), (10, 34, 86)], float)
    rgb = np.zeros(bed.shape + (3,))
    for k in range(3):
        rgb[..., k] = np.interp(depth, stops, cols[:, k])
    land = ~water
    z = np.clip(bed, 0, None)
    gcol = np.array([(128, 170, 98), (96, 148, 76), (84, 128, 64), (118, 124, 84)], float)
    gz = np.array([0.0, 1.0, 6.0, 25.0])
    land_rgb = np.zeros_like(rgb)
    for k in range(3):
        land_rgb[..., k] = np.interp(z, gz, gcol[:, k])
    isl = T['island_label']
    n_isl = int(isl.max())
    area = np.bincount(isl.ravel(), minlength=n_isl + 1) * dx * dx / 1e6
    small = np.zeros(bed.shape, bool)
    if n_isl:
        small = (isl > 0) & (area[isl] < 0.35)
    dw = ndi.distance_transform_edt(~water) * dx
    sand_w = np.clip(1.0 - (dw - 30.0) / 150.0, 0, 1) * (z < 0.6)
    sand_w = np.maximum(sand_w, (T['spit'] | small).astype(float))
    sand_w = ndi.gaussian_filter(sand_w, 0.8)
    sand = np.array((228, 210, 160), float)
    land_rgb = land_rgb * (1 - sand_w[..., None]) + sand * sand_w[..., None]
    rgb = np.where(land[..., None], land_rgb, rgb)
    return np.clip(rgb / 255.0, 0, 1)


def _extent_km(spec):
    return [spec.v0_m / 1000, (spec.v0_m + spec.nv * spec.spacing_m) / 1000,
            (spec.u0_m + spec.nu * spec.spacing_m) / 1000, spec.u0_m / 1000]


def _axes_labels(ax):
    ax.set_xlabel('沿岸方向 v / km(向右=东北)')
    ax.set_ylabel('垂直岸线方向 u / km(向下=外海,东南)')


def fig_remote(res, path, rgb=None):
    plt = _setup_mpl()
    spec = res['spec']
    rgb = remote_rgb(res['T'], spec.spacing_m) if rgb is None else rgb
    fig, ax = plt.subplots(figsize=(11.5, 11))
    ax.imshow(rgb, extent=_extent_km(spec), origin='upper', interpolation='nearest')
    ax.plot([-22.5, -17.5], [41.0, 41.0], c='k', lw=4)
    ax.plot([-22.5, -17.5], [41.0, 41.0], c='w', lw=1.5)
    ax.text(-20, 42.2, '5 km', ha='center', va='bottom', color='w', fontsize=11,
            bbox=dict(fc='k', ec='none', alpha=.55, pad=1.5))
    m = res['metrics']
    t = m['terrain']
    ax.set_title('复杂三角洲水网v1 遥感配色平面图 — %s\n入海口 %d,环 %d,岛 %d(≥0.05 km² %d);顶点→最远岸线 %.1f km,沿岸宽(u≥3km) %.1f km' % (
        VARIANT_TITLE[res['name']], m['skeleton']['n_mouths'], m['skeleton']['loops'], t['n_islands'],
        t['n_islands_ge_0p05km2'], t['apex_to_farthest_shore_km'], t['alongshore_width_u_ge_3km_km']), fontsize=12)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(fc=np.array((10, 34, 86)) / 255, label='深水(>7 m)'),
                       Patch(fc=np.array((54, 112, 182)) / 255, label='中等水深'),
                       Patch(fc=np.array((160, 208, 232)) / 255, label='浅水(<1.2 m)'),
                       Patch(fc=np.array((228, 210, 160)) / 255, label='沙洲/沙嘴/潮滩'),
                       Patch(fc=np.array((96, 148, 76)) / 255, label='陆地(绿)')],
              loc='upper right', fontsize=9, framealpha=.9)
    _axes_labels(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return rgb


def fig_diag(res, path):
    plt = _setup_mpl()
    g, spec, T = res['g'], res['spec'], res['T']
    fig, ax = plt.subplots(figsize=(11.5, 11))
    bg = np.where(T['land_env'], 0.93, 1.0)
    ax.imshow(bg, extent=_extent_km(spec), origin='upper', cmap='gray', vmin=0, vmax=1, interpolation='nearest')
    rank_col = {0: '#d62728', 1: '#ff7f0e', 2: '#2ca02c', 3: '#1f77b4'}
    lobe_info = {lb['id']: lb for lb in g.lobes}
    qmax = float(g.edge_q.max())
    order = np.argsort(g.edge_q)[::-1]
    for i in order:
        P = sk.edge_points(g, i)
        lb = int(g.edge_lobe[i])
        c = '#555555' if lb < 0 else rank_col.get(lobe_info[lb]['rank'], '#9467bd')
        ax.plot(P[:, 1] / 1000, P[:, 0] / 1000, c=c, lw=0.5 + 7.0 * math.sqrt(g.edge_q[i] / qmax),
                solid_capstyle='round', alpha=.95, zorder=3)
    marks = {'avulsion': ('*', 'k', 12, '改道点'), 'bifurcation': ('o', 'k', 3.5, '分汊'),
             'confluence': ('s', '#7b3fa0', 4.5, '汇合'), 'mouth': ('v', '#e00000', 7, '入海口'),
             'link_start': ('D', '#008b8b', 4.5, '横向连接汊起点'), 'source': ('P', 'k', 10, '入口')}
    for kind, (mk, col, ms, lab) in marks.items():
        idx = np.where(g.node_kind == sk.NODE_KINDS.index(kind))[0]
        if len(idx):
            ax.plot(g.node_uv[idx, 1] / 1000, g.node_uv[idx, 0] / 1000, mk, c=col, ms=ms, ls='none', label=lab, zorder=5)
    from matplotlib.lines import Line2D
    for r, c in rank_col.items():
        lbs = [lb for lb in g.lobes if lb['rank'] == r]
        if lbs:
            ax.plot([], [], c=c, lw=3, label='叶瓣#%d 年龄序%d(%s)份额%.0f%%' % (
                lbs[0]['id'], r, '最新' if r == 0 else '较老', 100 * lbs[0]['share']))
    ax.plot([], [], c='#555555', lw=5, label='主干')
    ax.legend(loc='upper right', fontsize=8.5, framealpha=.92, ncol=2)
    ax.set_title('汊道诊断图 — %s:线宽∝√Q,颜色=叶瓣年龄(红=最新最大)\n边 %d,节点 %d,环数 E−V+C=%d,层级 0–%d' % (
        VARIANT_TITLE[res['name']], len(g.edge_from), len(g.node_uv), res['metrics']['skeleton']['loops'],
        res['metrics']['skeleton']['max_level']), fontsize=12)
    ax.set_xlim(-24, 24)
    ax.set_ylim(44, -4)
    _axes_labels(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def fig_dem(res, path):
    from scipy.ndimage import map_coordinates
    plt = _setup_mpl()
    g, spec, T = res['g'], res['spec'], res['T']
    bed = T['bed']
    dx = spec.spacing_m
    fig = plt.figure(figsize=(16, 9.5))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.05, 1], hspace=.32, wspace=.2)
    ax = fig.add_subplot(gs[:, 0])
    ax.imshow(bed, extent=_extent_km(spec), origin='upper', cmap='gray', vmin=-6, vmax=3, interpolation='nearest')
    uA = 10000.0
    lb = g.lobes[g.youngest]
    p = res['params']
    sB = np.linspace(0, min(lb['R'], 34000.0), 800)
    pB = (p.apex_u + sB * math.cos(lb['theta']), sB * math.sin(lb['theta']))
    vA = np.linspace(-23500, 23500, 1600)
    ax.plot(vA / 1000, np.full_like(vA, uA) / 1000, c='#ff3030', lw=1.8)
    ax.plot(np.array(pB[1]) / 1000, np.array(pB[0]) / 1000, c='#ffb000', lw=1.8)
    ax.text(-23, uA / 1000 - .6, 'A', color='#ff3030', fontsize=14, weight='bold')
    ax.text(pB[1][-1] / 1000, pB[0][-1] / 1000 + 1.2, 'B', color='#ffb000', fontsize=14, weight='bold')
    ax.set_title('床面 DEM(灰度:−6 m 黑 → +3 m 白;高程 0=海平面)— %s' % VARIANT_TITLE[res['name']])
    _axes_labels(ax)

    def prof(ax2, s, pu, pv, title, xlab):
        iu = (pu - spec.u0_m) / dx - .5
        iv = (pv - spec.v0_m) / dx - .5
        z = map_coordinates(bed, [iu, iv], order=1, mode='nearest')
        ax2.fill_between(s / 1000, -8, np.minimum(z, 0), color='#9ec5e6', step=None)
        ax2.fill_between(s / 1000, -8, z, where=z >= 0, color='#7aa05c')
        ax2.plot(s / 1000, z, c='k', lw=.7)
        ax2.axhline(0, c='#2060c0', lw=.8, ls='--')
        ax2.set_ylim(-8, 4)
        ax2.set_title(title, fontsize=11)
        ax2.set_xlabel(xlab)
        ax2.set_ylabel('床面高程 / m(垂向夸大)')
        ax2.grid(alpha=.3)
    prof(fig.add_subplot(gs[0, 1]), vA - vA[0], np.full_like(vA, uA), vA,
         '剖面A:沿岸 u=%.0f km,穿过各分流汊道与岛(蓝=水,绿=陆)' % (uA / 1000), '沿剖面距离 / km(自 v=−23.5 km)')
    prof(fig.add_subplot(gs[1, 1]), sB, pB[0], pB[1],
         '剖面B:自顶点沿最新叶瓣轴向(θ=%.0f°)向海,含河口外水下扇' % math.degrees(lb['theta']), '距顶点距离 / km')
    fig.savefig(path, dpi=100)
    plt.close(fig)


def fig_compare(results, rgbs, path):
    plt = _setup_mpl()
    n = len(results)
    fig, axs = plt.subplots(1, n, figsize=(7.2 * n, 8.2))
    for ax, res, rgb in zip(np.atleast_1d(axs), results, rgbs):
        m = res['metrics']
        ax.imshow(rgb, extent=_extent_km(res['spec']), origin='upper', interpolation='nearest')
        ax.set_title('%s  (variant=%s)' % (VARIANT_TITLE[res['name']], res['name']), fontsize=12)
        txt = '环 %d | 入海口 %d | 层级 0–%d | 岛 %d(≥0.05km² %d)\n汊道总长 %.0f km | 顶点→最远岸 %.1f km | 沿岸宽 %.1f km' % (
            m['skeleton']['loops'], m['skeleton']['n_mouths'], m['skeleton']['max_level'], m['terrain']['n_islands'],
            m['terrain']['n_islands_ge_0p05km2'], m['skeleton']['total_channel_length_km'],
            m['terrain']['apex_to_farthest_shore_km'], m['terrain']['alongshore_width_u_ge_3km_km'])
        ax.set_xlabel(txt, fontsize=10)
    fig.suptitle('参数/种子对比:环少(参考图3类型)— 基准 — 环多(参考图2类型);同一 world_seed,不同 variant 派生子种子', fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


# ----------------------------------------------------------------------------- main
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
        print('[%s] ok=%s mouths=%d loops=%d levels=%d islands=%d far=%.1fkm width=%.1fkm' % (
            nm, m['validation']['ok'], m['skeleton']['n_mouths'], m['skeleton']['loops'], m['skeleton']['max_level'],
            m['terrain']['n_islands'], m['terrain']['apex_to_farthest_shore_km'],
            m['terrain']['alongshore_width_u_ge_3km_km']))
        top[nm] = res['sums']
        if not a.no_figs:
            os.makedirs(a.figs, exist_ok=True)
            rgb = fig_remote(res, os.path.join(a.figs, '1_遥感配色平面图_%s.png' % nm))
            fig_diag(res, os.path.join(a.figs, '2_汊道诊断图_%s.png' % nm))
            fig_dem(res, os.path.join(a.figs, '3_床面DEM与横剖面_%s.png' % nm))
            rgbs.append(rgb[::2, ::2])
        res['T'] = None
        results.append(res)
    write_json(os.path.join(a.out, 'sha256sums_all.json'), top)
    if not a.no_figs and len(results) > 1:
        fig_compare(results, rgbs, os.path.join(a.figs, '4_参数种子对比.png'))
    return results


if __name__ == '__main__':
    main()
