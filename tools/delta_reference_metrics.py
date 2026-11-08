#!/usr/bin/env python
"""Dimensionless morphology metrics of delta reference images and of generated delta masks.

    runtime/venv/Scripts/python.exe -B tools/delta_reference_metrics.py [--v3 <dir>] [--out <dir>]

Segments reference/ref2-plain-network.png (dark channels vs. land) and reference/ref3-small-estuary.png
(turbid pale-yellow channels/sand, dark green vegetation, teal sea) into masks and computes metrics that
do not depend on pixel size or map scale (lengths are divided by sqrt(delta extent area) or by the trunk
channel width).  The same ``compute_metrics`` is used on generated deltas (see ``masks_from_product``).

Classes: chan (channel water), sand (pale sand/bar/intertidal flats that are not channel), veg (vegetated land),
sea (open water outside the delta).  extent = convex hull of (channel skeleton + sand) minus sea.
Only numpy/scipy/skimage/PIL (CPU).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull, cKDTree
from skimage.draw import polygon as _polygon
from skimage.morphology import disk, skeletonize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, '.scratch', 'delta-network-v1-20261105')
REF = os.path.join(SCRATCH, 'reference')
WORK = os.path.join(SCRATCH, 'work')

K8 = np.ones((3, 3), int)
LAB8 = np.ones((3, 3), int)


# ------------------------------------------------------------------ segmentation of the references
def _largest(mask):
    lab, n = ndi.label(mask, LAB8)
    if n == 0:
        return mask
    cnt = np.bincount(lab.ravel())
    cnt[0] = 0
    return lab == cnt.argmax()


def _remove_small(mask, min_px):
    lab, n = ndi.label(mask, LAB8)
    cnt = np.bincount(lab.ravel(), minlength=n + 1)
    keep = cnt >= min_px
    keep[0] = False
    return keep[lab]


def segment_ref3(path=None, open_r=12):
    im = np.asarray(Image.open(path or os.path.join(REF, 'ref3-small-estuary.png')).convert('RGB')).astype(float)
    sm = np.stack([ndi.uniform_filter(im[..., k], 5) for k in range(3)], -1)
    r, g, b = sm[..., 0], sm[..., 1], sm[..., 2]
    light = r > 125
    ratio = b / np.maximum(g, 1.0)
    veg = (~light) & ((ratio < 0.775) | (g < 88))
    veg = ndi.median_filter(veg.astype(np.uint8), 7) > 0
    water = (~light) & (~veg)
    sea = _largest(ndi.binary_opening(water, disk(3)))
    sea = ndi.binary_dilation(sea, disk(3)) & water
    veg = veg | (water & ~sea)                      # enclosed shaded patches are vegetation
    light = light & ~veg
    opened = ndi.binary_opening(light, disk(open_r))
    sandflat = ndi.binary_dilation(opened, disk(open_r)) & light
    chan = light & ~sandflat
    chan = _remove_small(chan, 30)
    sand = light & ~chan
    return dict(chan=chan, sand=sand, veg=veg & ~light, sea=sea & ~light, rgb=im.astype(np.uint8))


def segment_ref2(path=None, roi=(100, 700, 0, 440)):
    im = np.asarray(Image.open(path or os.path.join(REF, 'ref2-plain-network.png')).convert('RGB')).astype(float)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    water = (((b - r) > 25) & (r < 100)) | ((r + g + b) < 150)
    x0, x1, y0, y1 = roi
    inroi = np.zeros(water.shape, bool)
    inroi[y0:y1, x0:x1] = True
    sea = _largest(ndi.binary_opening(water, disk(12)))
    sea = ndi.binary_dilation(sea, disk(12)) & water
    chan = water & ~sea & inroi
    chan = _remove_small(chan, 12)
    land = inroi & ~water
    # fields with sea-like colour at the roi boundary are not delta: keep land only west of the sea shore
    return dict(chan=chan, sand=np.zeros_like(chan), veg=land, sea=sea & inroi, rgb=im.astype(np.uint8), roi=roi)


# ------------------------------------------------------------------ metric helpers
def _hull_mask(points, shape):
    if len(points) < 3:
        return np.zeros(shape, bool)
    h = ConvexHull(points)
    pts = points[h.vertices]
    rr, cc = _polygon(pts[:, 0], pts[:, 1], shape)
    m = np.zeros(shape, bool)
    m[rr, cc] = True
    return m


def _skeleton_graph(skel):
    nb = ndi.convolve(skel.astype(int), K8, mode='constant') - skel.astype(int)
    nb = nb * skel
    junction = skel & (nb >= 3)
    endpoint = skel & (nb == 1)
    jl, nj = ndi.label(ndi.binary_dilation(junction, K8.astype(bool)) & skel, LAB8)
    branches = skel & (jl == 0)
    bl, nbr = ndi.label(branches, LAB8)
    _, ncomp = ndi.label(skel, LAB8)
    ne = int(ndi.label(endpoint & (jl == 0), LAB8)[1])
    return dict(junction_label=jl, n_junctions=int(nj), n_endpoints=ne, branch_label=bl, n_branches=int(nbr),
                n_components=int(ncomp), skel_len=int(skel.sum()))


def _prune(skel, n):
    s = skel.copy()
    for _ in range(n):
        nb = (ndi.convolve(s.astype(int), K8, mode='constant') - s.astype(int)) * s
        s = s & ~(nb <= 1)
    # regrow the ends we cut from the real branch ends (conditional dilation of surviving endpoints)
    nb = (ndi.convolve(s.astype(int), K8, mode='constant') - s.astype(int)) * s
    ends = s & (nb == 1)
    grow = ends.copy()
    for _ in range(n):
        grow = ndi.binary_dilation(grow, K8.astype(bool)) & skel & ~s | grow
    return s | (grow & skel)


def _moments_axes(ii, jj):
    c = np.cov(np.stack([ii, jj]).astype(float))
    ev, evec = np.linalg.eigh(c)
    ev = np.maximum(ev, 1e-9)
    return math.sqrt(ev[1] / ev[0]), evec[:, 1]


def _pct(a, qs=(10, 50, 90)):
    a = np.asarray(a, float)
    if a.size == 0:
        return {('p%d' % q): None for q in qs}
    return {('p%d' % q): float(np.percentile(a, q)) for q in qs}


def compute_metrics(chan, sand, veg, sea, name='', prune_frac=0.012, skel_scale=1):
    """chan/sand/veg/sea: boolean arrays of one shape.  Returns a dict of dimensionless metrics."""
    shape = chan.shape
    sk = skeletonize(chan)
    ys, xs = np.nonzero(sk)
    pts = np.stack([ys, xs], 1)
    hull_src = pts
    if sand.any():
        sy, sx = np.nonzero(sand)
        sub = np.stack([sy, sx], 1)[::7]
        hull_src = np.concatenate([pts, sub])
    extent = _hull_mask(hull_src, shape) & ~sea
    A = float(extent.sum())
    L0 = math.sqrt(A)                                  # length unit of the delta extent
    n_prune = max(2, int(round(prune_frac * L0)))
    skp = _prune(sk, n_prune) & extent
    dist = ndi.distance_transform_edt(chan)
    width_at_skel = 2.0 * dist[skp]
    w_max = float(width_at_skel.max()) if width_at_skel.size else 1.0
    gr = _skeleton_graph(skp)
    n_nodes = gr['n_junctions'] + gr['n_endpoints']
    cycles = gr['n_branches'] - n_nodes + gr['n_components']
    out = dict(name=name, extent_area_px=A, L0_px=L0, trunk_width_px=w_max, trunk_width_over_L0=w_max / L0)
    out['water_fraction'] = float((chan & extent).sum() / A)
    out['skeleton_len_over_L0'] = gr['skel_len'] / L0
    out['junction_density_per_L0'] = gr['n_junctions'] / (gr['skel_len'] / L0)       # nodes per unit skeleton length
    out['n_junctions'] = gr['n_junctions']
    out['n_endpoints'] = gr['n_endpoints']
    out['n_loops'] = int(max(cycles, 0))
    out['loops_per_junction'] = float(max(cycles, 0) / max(gr['n_junctions'], 1))
    wn = width_at_skel / w_max
    out['width_norm'] = _pct(wn, (10, 50, 90))
    out['width_norm']['frac_ge_0p5'] = float((wn >= 0.5).mean()) if wn.size else 0.0
    mean_w = float(width_at_skel.mean()) if width_at_skel.size else 1.0

    # ---- land blocks (vegetated + sand-less) cut by channels
    land = (veg | sand) & extent & ~chan
    lab, n = ndi.label(land, LAB8)
    cnt = np.bincount(lab.ravel(), minlength=n + 1)
    cnt[0] = 0
    a_min = max(0.002 * A, 20.0)
    big = np.nonzero(cnt >= a_min)[0]
    tree = cKDTree(pts) if len(pts) else None
    out['land_fraction'] = float(land.sum() / A)
    if len(big):
        areas = cnt[big].astype(float)
        amax = areas.max()
        out['n_land_blocks'] = int(len(big))
        out['largest_block_share'] = float(amax / cnt.sum())
        out['block_area_norm'] = _pct(areas / amax, (10, 50, 90))
        asp, ang, fr = [], [], []
        objs = ndi.find_objects(lab)
        sea_d = ndi.binary_dilation(sea, disk(3))
        for k in big:
            sl = objs[k - 1]
            ii, jj = np.nonzero(lab[sl] == k)
            ii = ii + sl[0].start
            jj = jj + sl[1].start
            if len(ii) < 10:
                continue
            ratio, axis = _moments_axes(ii, jj)
            asp.append(ratio)
            cy, cx = ii.mean(), jj.mean()
            if tree is not None:
                R = 0.06 * L0
                idx = tree.query_ball_point([cy, cx], R)
                if len(idx) >= 5:
                    pp = pts[idx].astype(float)
                    _, tv = _moments_axes(pp[:, 0], pp[:, 1])
                    cosang = abs(float(axis @ tv))
                    ang.append(math.degrees(math.acos(min(cosang, 1.0))))
            fr.append(bool(sea_d[sl][lab[sl] == k].any()))
        asp = np.asarray(asp)
        out['block_aspect'] = _pct(asp, (10, 50, 90))
        out['block_aspect']['frac_ge_2'] = float((asp >= 2).mean())
        big_i = int(np.argmax(cnt[big]))
        front = np.asarray(fr, bool)
        not_main = np.ones(len(asp), bool)
        if len(asp) == len(big):
            not_main[big_i] = False
        sel = front & not_main if len(asp) == len(big) else front
        out['front_tongue_aspect'] = _pct(asp[sel], (50, 90)) if sel.any() else {'p50': None, 'p90': None}
        out['n_front_tongues'] = int(sel.sum())
        out['block_flow_angle_deg'] = _pct(ang, (25, 50, 75)) if ang else {}
        out['block_along_flow_frac_lt30'] = float((np.asarray(ang) < 30).mean()) if ang else None
    # ---- sand
    if sand.any():
        sd = sand & extent
        out['sand_fraction_of_extent'] = float(sd.sum() / A)
        sl_, sn = ndi.label(sd, LAB8)
        scnt = np.bincount(sl_.ravel(), minlength=sn + 1)
        scnt[0] = 0
        smin = max(0.002 * A, 25.0)
        sbig = np.nonzero(scnt >= smin)[0]
        out['n_sand_blocks'] = int(len(sbig))
        out['sand_block_mean_area_over_w2'] = float(scnt[sbig].mean() / mean_w ** 2) if len(sbig) else 0.0
        out['sand_largest_share'] = float(scnt.max() / max(scnt.sum(), 1))
        # which skeleton branches does each sand block touch?
        bl = gr['branch_label'] * skp
        touch = []
        for k in sbig:
            m = ndi.binary_dilation(sl_ == k, disk(3))
            ids = np.unique(bl[m])
            ids = ids[ids > 0]
            # branches shorter than a few widths are node artefacts; keep branches with >= 2*mean_w pixels
            ids = [i for i in ids if (bl == i).sum() >= 2 * mean_w]
            touch.append(len(ids))
        touch = np.asarray(touch)
        out['sand_block_touch_channels'] = dict(mean=float(touch.mean()) if touch.size else 0.0,
                                                max=int(touch.max()) if touch.size else 0)
        out['n_sand_cross_channel_ge2'] = int((touch >= 2).sum())
        out['n_sand_cross_channel_ge3'] = int((touch >= 3).sum())
        vsum = float((veg & extent).sum())
        out['sand_over_land'] = float(sd.sum() / max(sd.sum() + vsum, 1.0))
    out['_extent'] = extent
    out['_skel'] = skp
    return out


# ------------------------------------------------------------------ generated products
def masks_from_product(prod_dir, sand_z=(-0.5, 0.35)):
    """Masks from skeleton-v3/v4 npy products (channel_mask, water_mask, bed_dem_float64, tidal_mask)."""
    d = prod_dir
    chan = np.load(os.path.join(d, 'channel_mask.npy')).astype(bool)
    tid = np.load(os.path.join(d, 'tidal_mask.npy')).astype(bool)
    water = np.load(os.path.join(d, 'water_mask.npy')).astype(bool)
    bed = np.load(os.path.join(d, 'bed_dem_float64.npy'))
    main = chan & ~tid
    land = ~water
    return masks_from_arrays(main, tid, water, land, bed, sand_z)


def masks_from_arrays(main_chan, tidal, water, land, bed, sand_z=(-0.5, 0.35), u_min_cells=70, sand_mask=None):
    chan = main_chan
    sea = water & ~chan & ~tidal & (bed < sand_z[0])
    sea = sea | (water & ~chan & ~tidal & (bed >= sand_z[0]) & False)
    if sand_mask is None:
        sand = (~chan) & (bed >= sand_z[0]) & (bed < sand_z[1])
    else:
        sand = sand_mask & ~chan
    veg = land & ~chan & ~sand
    sea = ~(chan | sand | veg)
    # only the part belonging to the sea connected to the ocean row (largest sea component) is "outside";
    # enclosed water is treated as channel-like water (kept in sea so that it is not counted as land)
    sand[:u_min_cells] = False
    veg[:u_min_cells] = False
    chan = chan.copy()
    return dict(chan=chan, sand=sand, veg=veg, sea=sea)


# ------------------------------------------------------------------ pictures
def save_mask_png(m, path, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rgb = np.zeros(m['chan'].shape + (3,), float)
    rgb[m['sea']] = (0.35, 0.65, 0.9)
    rgb[m['veg']] = (0.15, 0.5, 0.2)
    rgb[m['sand']] = (0.97, 0.88, 0.55)
    rgb[m['chan']] = (0.05, 0.15, 0.55)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.imshow(rgb)
    ax.set_title(title)
    ax.axis('off')
    fig.savefig(path, dpi=80, bbox_inches='tight')
    plt.close(fig)


def _clean(d):
    return {k: v for k, v in d.items() if not k.startswith('_')}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--v3', default=os.path.join(SCRATCH, 'skeleton-v3', 'base'))
    ap.add_argument('--out', default=WORK)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    res = {}
    r3 = segment_ref3()
    res['ref3'] = _clean(compute_metrics(r3['chan'], r3['sand'], r3['veg'], r3['sea'], 'ref3'))
    save_mask_png(r3, os.path.join(a.out, 'ref3_mask.png'), 'ref3 mask')
    r2 = segment_ref2()
    res['ref2'] = _clean(compute_metrics(r2['chan'], r2['sand'], r2['veg'], r2['sea'], 'ref2'))
    save_mask_png(r2, os.path.join(a.out, 'ref2_mask.png'), 'ref2 mask')
    if os.path.isdir(a.v3):
        m = masks_from_product(a.v3)
        res['v3'] = _clean(compute_metrics(m['chan'], m['sand'], m['veg'], m['sea'], 'v3'))
    with open(os.path.join(a.out, 'reference_metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
