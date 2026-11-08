"""Land building for the complex delta network v4 (post-processing of ``build_terrain_v3``).

Why v4 (user: "按参考图的形态作为基准")
----------------------------------------
v3 problems found by review, and what v4 does about each (all CPU, numpy/scipy only):

1. *Round/elliptic ponds inside the delta* = enclosed, non-TD water bodies left between the cones
   of the floodplain construction.  v4 fills every enclosed pond (not connected to the sea, not TD
   ocean) with low marsh/flat land.  No pond is kept.
2. *Fingered, thin front* -> a **sand apron**: every mouth deposits a Gaussian "supply" blob
   (sigma = ap_sigma_k * sqrt(Q), centred near the lobe tip); the blobs of neighbouring mouths add up,
   so adjacent mouths share one continuous intertidal sand flat (the cross-channel sand plain of
   reference 3).  The apron raises the sea bed to 0.06-0.32 m (emergent/intertidal), channels are
   carved through it by tails that run until the apron ends.
3. *Large sand area* -> besides the apron, bank sand (width ~ bank_k x channel width, only in the front
   half) and the fringe of the low old lobes are classed as sand; the explicit boolean mask ``sand``
   is a product (``sand_mask.npy``), vegetated land is the rest of the dry land.
4. *Uniform shoal outline* -> the shallow-water slope is multiplied by a supply-dependent factor
   (wide shoals in front of big mouths, narrow ones in embayments) and a log-normal noise.
5. *Detached blue line above the inlet* = random tidal creeks that wandered up into the TD plain
   plus a trunk that starts bluntly at the apex.  v4 deletes every channel cell above the apex
   that is not the trunk and stamps the trunk up to the window edge (monotone water level).
6. *Old lobes* get a continuous low sand/mud fringe (``old_sand_band_m``) instead of fragments.

All numbers are declared scenario values (``TerrainParamsV4``); randomness only through
``rng_for('delta-network-v4/terrain', variant)`` (SHA256-derived, no clock / entropy / hash()).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from skimage.morphology import disk

from terrain_pipeline.delta_network_site import rng_for
from terrain_pipeline import delta_network_terrain_v3 as t3
from terrain_pipeline.delta_network_terrain import _Grid, _Stamps, _smooth_noise, _smoothstep

__all__ = ['TerrainParamsV4', 'build_terrain_v4', 'postprocess_v4', 'terrain_metrics_v4']


@dataclass(frozen=True)
class TerrainParamsV4(t3.TerrainParamsV3):
    creek_spacing_m: float = 3200.0      # fewer tidal creeks on old lobes
    # ponds
    pond_tdo_frac: float = 0.3           # a water body with more TD-ocean cells than this is sea, not a pond
    pond_z_m: float = 0.38
    # sand apron
    ap_sigma_k: float = 100.0            # supply blob sigma = k*sqrt(Q) [m]
    ap_sigma_min_m: float = 520.0
    ap_shift: float = 0.9                # centre = mouth + dir * shift * Le
    ap_thr: float = 0.50
    ap_noise: float = 0.22
    ap_noise_corr_m: float = 900.0
    apron_z0_m: float = 0.06
    apron_z1_m: float = 0.30
    sand_z_max_m: float = 0.32
    tail_max_m: float = 6000.0
    tail_w_frac: float = 0.8
    tail_h_frac: float = 0.4
    # bank sand
    bank_k: float = 1.6                  # sand band half-width = k * channel width (front zone only)
    bank_max_m: float = 520.0
    bank_f0: float = 0.30
    bank_f1: float = 0.60
    # old lobes
    old_sand_band_m: float = 900.0
    # sand cleaning
    min_sand_km2: float = 0.06
    min_veg_in_sand_km2: float = 0.08
    # shoal
    shoal_gain: float = 1.5
    shoal_supply_sigma_m: float = 2400.0
    shoal_noise: float = 0.35
    shoal_noise_corr_m: float = 1800.0
    # upstream trunk
    tail_meander_gain: float = 0.5
    src_amp_m: float = 140.0


def _remove_small(mask, min_px):
    lab, n = ndi.label(mask)
    cnt = np.bincount(lab.ravel(), minlength=n + 1)
    keep = cnt >= min_px
    keep[0] = False
    return keep[lab]


def _enclosed_ponds(land_env, td_ocean, frac):
    """Water bodies (outside land_env) that touch no window border and are not TD ocean."""
    wat = ~land_env
    lab, n = ndi.label(wat)
    if n == 0:
        return np.zeros_like(wat)
    border = np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))
    cnt = np.bincount(lab.ravel(), minlength=n + 1).astype(float)
    tdo = np.bincount(lab[td_ocean].ravel(), minlength=n + 1).astype(float)
    pond = (tdo / np.maximum(cnt, 1.0)) < frac
    pond[0] = False
    pond[border] = False
    return pond[lab]


def postprocess_v4(spec, g, T, td_bed, td_ocean, tp: TerrainParamsV4 | None = None):
    tp = tp or TerrainParamsV4()
    p = g.params
    grid = T['grid']
    dx = grid.dx
    U, V = grid.U, grid.V
    shape = grid.shape
    rng = rng_for('delta-network-v4/terrain', p.variant, world_seed=getattr(p, 'algorithm_world_seed', 20261020))
    mouths = T['mouths']
    noise_a = _smooth_noise(rng, shape, tp.ap_noise_corr_m / dx, 1.0)
    noise_b = _smooth_noise(rng, shape, 600.0 / dx, 1.0)
    noise_s = _smooth_noise(rng, shape, tp.shoal_noise_corr_m / dx, 1.0)
    noise_c = _smooth_noise(rng, shape, 450.0 / dx, 1.0)

    bed = T['bed'].copy()
    chan = T['chan'].copy()
    tidal = T['tidal'].copy()
    land_env = T['land_env'].copy()
    spit = T['spit'].copy()
    z_plain = T['z_plain']
    z_land = np.maximum(z_plain + T['levee'], 0.03)

    # ---- 1. channel cells above the apex are random tidal creeks: delete; trunk goes to the window edge
    above = chan & (U < p.apex_u - 60.0)
    n_creek_cells_removed = int(above.sum())
    chan &= ~above
    tidal &= ~above
    bed = np.where(above & land_env, z_land, bed)
    st_src = _Stamps(grid)
    u_edge = spec.u0_m + 0.5 * dx
    su = np.arange(u_edge, p.apex_u + 1.0, 30.0)
    fade = _smoothstep((p.apex_u - su) / 1500.0)
    sv = tp.src_amp_m * fade * np.sin(2 * math.pi * (su - p.apex_u) / 4200.0)
    w_src = float(g.edge_w[0])
    h_src = float(g.edge_h[0])
    wl = np.maximum(0.0, grid.sample(z_plain, su, sv) - tp.freeboard_m)
    wl = np.minimum.accumulate(wl)
    hl = np.minimum(tp.levee_h_frac * h_src, tp.levee_h_max_m)
    st_src.add(su, sv, np.full(len(su), w_src), np.full(len(su), h_src), wl, np.full(len(su), hl),
               np.full(len(su), float(np.clip(w_src, tp.levee_lam_min_m, tp.levee_lam_max_m))), tp.channel_floor)
    new_src = st_src.chan & ~chan
    chan |= st_src.chan
    bed = np.where(st_src.chan, np.minimum(bed, st_src.bed), bed)
    land_env |= st_src.chan & (U < p.apex_u)

    # ---- 2. fill enclosed ponds (round basins between the floodplain cones)
    pond = _enclosed_ponds(land_env, td_ocean, tp.pond_tdo_frac)
    n_pond_cells = int(pond.sum())
    n_ponds = int(ndi.label(pond)[1])
    land_env |= pond
    bed = np.where(pond & ~chan, tp.pond_z_m + 0.06 * noise_b, bed)

    # ---- 3. sand apron from the mouth supply blobs
    F = np.zeros(shape)
    for m in mouths:
        sig = max(tp.ap_sigma_min_m, tp.ap_sigma_k * math.sqrt(m['q']))
        cu = m['pos'][0] + m['dir'][0] * tp.ap_shift * m['Le_m']
        cv = m['pos'][1] + m['dir'][1] * tp.ap_shift * m['Le_m']
        iu = int((cu - spec.u0_m) / dx)
        iv = int((cv - spec.v0_m) / dx)
        r = int(2.6 * sig / dx) + 2
        i0, i1 = max(iu - r, 0), min(iu + r + 1, shape[0])
        j0, j1 = max(iv - r, 0), min(iv + r + 1, shape[1])
        d2 = (U[i0:i1, j0:j1] - cu) ** 2 + (V[i0:i1, j0:j1] - cv) ** 2
        F[i0:i1, j0:j1] += np.exp(-d2 / sig ** 2)
    apron = (F + tp.ap_noise * noise_a) > tp.ap_thr
    apron &= (U > 500.0)
    apron_sea = apron & ~land_env
    # keep only apron pieces that touch land or a mouth funnel (no floating discs)
    lab_a, na = ndi.label(apron_sea | land_env)
    ref_ids = np.unique(np.concatenate([lab_a[0, :][lab_a[0, :] > 0], lab_a[chan & (U > 0)]]))
    ref_ids = ref_ids[ref_ids > 0]
    keep_a = np.zeros(na + 1, bool)
    keep_a[ref_ids] = True
    apron_sea &= keep_a[lab_a]
    # exclude cells that are TD ocean on the left/right of the delta (only the delta front is built)
    land_env_new = land_env | apron_sea
    # water pockets enclosed by the apron (round blue spots in the first v4 trial) are tidal flat, not ponds
    pond2 = _enclosed_ponds(land_env_new, td_ocean, 9.0)   # any water body that no longer touches the window border
    n_ponds += int(ndi.label(pond2)[1])
    n_pond_cells += int(pond2.sum())
    apron_sea |= pond2
    land_env_new |= pond2
    z_ap = tp.apron_z0_m + (tp.apron_z1_m - tp.apron_z0_m) * np.clip(0.5 + 0.5 * noise_b, 0.0, 1.0)
    bed = np.where(apron_sea & ~chan, z_ap, bed)
    spit = spit | apron_sea

    # ---- 4. tails: carve every mouth channel through the apron to open water
    st_tail = _Stamps(grid)
    apron_f = (apron_sea | (apron & land_env)).astype(float)
    tail_pts, tail_w = [], []
    graph_extensions = {}
    n_tails = 0
    for m in mouths:
        s = m['Le_m']
        end = None
        while s < m['Le_m'] + tp.tail_max_m:
            s += 30.0
            pu_ = m['pos'][0] + s * m['dir'][0]
            pv_ = m['pos'][1] + s * m['dir'][1]
            if float(grid.sample(apron_f, pu_, pv_)) < 0.5 and float(grid.sample(land_env_new.astype(float), pu_, pv_)) < 0.5:
                end = s + 60.0
                break
        if end is None:
            end = s
        graph_extensions[int(m['node'])] = dict(end_m=float(max(end, m['Le_m'])), direction=m['dir'].tolist())
        if end - m['Le_m'] < 150.0:
            continue
        ss = np.arange(m['Le_m'], end, 30.0)
        x = (ss - m['Le_m']) / max(end - m['Le_m'], 1.0)
        nrm = np.array([-m['dir'][1], m['dir'][0]])
        off = tp.tail_meander_gain * m['w'] * np.sin(2 * math.pi * (ss - m['Le_m']) / max(1500.0, 12 * m['w'])) * (1 - x)
        pu = m['pos'][0] + ss * m['dir'][0] + off * nrm[0]
        pv = m['pos'][1] + ss * m['dir'][1] + off * nrm[1]
        w0 = m['w'] * (1 + tp.funnel_gain) * tp.tail_w_frac
        w_ = w0 * (1 - 0.45 * x)
        h_ = np.maximum(m['h'] * tp.tail_h_frac * (1 - 0.5 * x), 0.5)
        st_tail.add(pu, pv, w_, h_, np.zeros(len(ss)), np.zeros(len(ss)), np.full(len(ss), 60.0), tp.channel_floor)
        tail_pts.append(np.stack([pu, pv], 1))
        tail_w.append(w_)
        n_tails += 1
    chan |= st_tail.chan
    bed = np.where(st_tail.chan, np.minimum(bed, st_tail.bed), bed)

    # ---- 5. channel points for the width-aware bank band and the connectivity check
    ch_pts, ch_w = t3._channel_points(g, mouths, step=40.0)
    if tail_pts:
        ch_pts = np.concatenate([ch_pts] + tail_pts)
        ch_w = np.concatenate([ch_w] + tail_w)
    far_mouth = float(np.hypot(g.node_uv[g.mouth_nodes, 0] - p.apex_u, g.node_uv[g.mouth_nodes, 1]).max())
    r_apex = np.hypot(U - p.apex_u, V)
    fz = _smoothstep((r_apex / far_mouth - tp.bank_f0) / (tp.bank_f1 - tp.bank_f0))
    chan_main = chan & ~tidal
    dch = ndi.distance_transform_edt(~chan_main) * dx
    cand = (dch <= tp.bank_max_m) & (fz > 0.02) & land_env_new & ~chan
    bank = np.zeros(shape, bool)
    ii, jj = np.nonzero(cand)
    if len(ii):
        d, idx = cKDTree(ch_pts).query(np.stack([U[ii, jj], V[ii, jj]], 1))
        ratio = d / np.maximum(ch_w[idx], 1.0)
        nz = np.clip(0.5 + 0.5 * noise_c[ii, jj], 0.0, 1.0)
        bank[ii, jj] = ratio < tp.bank_k * fz[ii, jj] * (0.55 + 0.9 * nz)

    # ---- 6. old-lobe fringe
    D_new = ndi.distance_transform_edt(land_env_new) * dx
    wo = T['old_weight']
    old_f = (wo > 0.5) & land_env_new & ~chan & (D_new <= tp.old_sand_band_m * (0.6 + 0.8 * np.clip(0.5 + 0.5 * noise_a, 0, 1)))

    # ---- 7. sand mask (explicit class) and cleaning
    sand = (apron & land_env_new) | bank | old_f      # filled ponds stay vegetated marsh (no round sand discs)
    sand &= ~chan
    sand = ndi.binary_closing(sand, structure=disk(2)) & land_env_new & ~chan
    sand = ndi.binary_opening(sand, structure=disk(1))
    min_px = int(round(tp.min_sand_km2 * 1e6 / dx ** 2))
    sand = _remove_small(sand, min_px)
    veg = land_env_new & ~sand & ~chan
    small_veg = veg & ~_remove_small(veg, int(round(tp.min_veg_in_sand_km2 * 1e6 / dx ** 2)))
    top = np.zeros(shape, bool)
    top[0, :] = True
    lab_v, nv = ndi.label(veg)
    top_ids = np.unique(lab_v[0, :])
    small_veg &= ~np.isin(lab_v, top_ids[top_ids > 0])
    sand |= small_veg
    sand &= ~chan
    # sand surface is intertidal; vegetated land stays at plain height
    bed = np.where(sand & ~apron_sea & ~chan, np.minimum(bed, tp.sand_z_max_m + 0.03 * noise_b), bed)
    bed = np.where(sand & ~chan, np.clip(bed, 0.03, tp.sand_z_max_m + 0.05), bed)

    # ---- 8. connectivity of emergent blocks (hard check, same rule as v3)
    bad, conn_build = t3._env_connectivity(land_env_new, grid, ch_pts, ch_w, tp.conn_N)
    land_env_new &= ~bad
    spit &= ~bad
    sand &= ~bad

    # ---- 8b. slivers of non-channel water enclosed by land and channel cells (1-55 px holes along channel margins)
    holes = _enclosed_ponds(land_env_new | chan, np.zeros(shape, bool), 9.0) & ~chan
    n_holes_filled = int(ndi.label(holes)[1])
    land_env_new |= holes
    bed = np.where(holes, tp.pond_z_m * 0.5 + 0.06 * noise_b, bed)

    # ---- 9. sea bed with supply-dependent shoal width, irregular outline
    Fs = gaussian_filter(F, tp.shoal_supply_sigma_m / dx)
    ref_v = np.percentile(Fs[Fs > 0.02], 90) if (Fs > 0.02).any() else 1.0
    sn = np.clip(Fs / max(ref_v, 1e-6), 0.0, 1.6)
    mult = np.exp(-tp.shoal_gain * (sn - 0.5)) * np.exp(tp.shoal_noise * noise_s)
    dist_sea = ndi.distance_transform_edt(~land_env_new) * dx
    depth = np.minimum(tp.front_d0_m + tp.front_slope * dist_sea * mult, spec.shelf_max_depth_m)
    shelf = np.where(td_ocean & (td_bed < 0), np.maximum(-td_bed, 0.0), 1e9)
    sea_bed = -np.minimum(depth, np.maximum(shelf, tp.front_d0_m))
    keep_chan_bed = chan
    bed = np.where(land_env_new, bed, sea_bed)
    bed = np.where(keep_chan_bed, bed if True else bed, bed)
    # channel cells over open water keep their carved profile (st / T bed already merged into ``bed`` earlier)
    chan_bed = np.where(T['chan'], T['bed'], np.inf)
    chan_bed = np.where(st_tail.chan, np.minimum(chan_bed, st_tail.bed), chan_bed)
    chan_bed = np.where(st_src.chan, np.minimum(chan_bed, st_src.bed), chan_bed)
    chan_bed = np.where(above, np.inf, chan_bed)
    bed = np.where(chan & np.isfinite(chan_bed), np.minimum(chan_bed, np.where(land_env_new, z_land, sea_bed)), bed)
    water = (~land_env_new) | chan

    # ---- 10. drown tiny non-mainland fragments, islands, labels
    ld0 = land_env_new & ~chan
    lab0, n0 = ndi.label(ld0)
    top0 = np.unique(lab0[0, :])
    top0 = top0[top0 > 0]
    ar0 = np.bincount(lab0.ravel(), minlength=n0 + 1) * dx * dx / 1e6
    small = ar0 < tp.min_island_km2
    small[0] = False
    small[top0] = False
    kill = small[lab0]
    n_drowned = int(small.sum()) + int(T['n_drowned'])
    if kill.any():
        land_env_new &= ~kill
        spit &= ~kill
        sand &= ~kill
        bed = np.where(kill, np.minimum(sea_bed, -0.15), bed)
        water = (~land_env_new) | chan
    land_dry = land_env_new & ~chan
    lab, n = ndi.label(land_dry)
    inland = np.unique(lab[0, :])
    inland = inland[inland > 0]
    mainland = np.isin(lab, inland)
    island_label = np.zeros(shape, np.int32)
    isl = (lab > 0) & ~mainland
    if isl.any():
        old_ids = np.unique(lab[isl])
        remap = np.zeros(n + 1, np.int32)
        remap[old_ids] = np.arange(1, len(old_ids) + 1, dtype=np.int32)
        island_label = remap[lab]
        island_label[~isl] = 0

    T4 = dict(T)
    T4.update(bed=bed.astype(np.float64), water=water, land_env=land_env_new, land_dry=land_dry, chan=chan,
              tidal=tidal, spit=spit, sand=sand & land_dry, island_label=island_label, mainland=mainland,
              graph_extensions=graph_extensions, source_path_uv_m=np.stack([su, sv], 1),
              conn_build=conn_build, n_drowned=n_drowned, supply=F, shoal_mult=mult,
              v4=dict(n_creek_cells_removed_above_apex=n_creek_cells_removed, n_ponds_filled=n_ponds,
                      pond_area_km2=float(n_pond_cells * dx * dx / 1e6), n_margin_holes_filled=n_holes_filled, n_tails=n_tails,
                      src_stub_cells_added=int(new_src.sum()), apron_sea_area_km2=float(apron_sea.sum() * dx * dx / 1e6),
                      shoal_mult_p5_p95=[float(np.percentile(mult[~land_env_new], 5)),
                                         float(np.percentile(mult[~land_env_new], 95))]))
    return T4


def build_terrain_v4(spec, g, td_bed, td_ocean, tp: TerrainParamsV4 | None = None, base=None):
    tp = tp or TerrainParamsV4()
    T = base if base is not None else t3.build_terrain_v3(spec, g, td_bed, td_ocean, tp)
    return postprocess_v4(spec, g, T, td_bed, td_ocean, tp)


def terrain_metrics_v4(spec, g, T):
    m = t3.terrain_metrics_v3(spec, g, T)
    m['v4'] = dict(T['v4'])
    grid = T['grid']
    dx = grid.dx
    m['sand_area_km2'] = float(T['sand'].sum() * dx * dx / 1e6)
    # a pond = enclosed water that is not a channel (channel water inside land_env is not a pond)
    env_or_chan = T['land_env'] | T['chan']
    pond_left = _enclosed_ponds(env_or_chan, np.zeros_like(env_or_chan), 2.0)
    # sub-0.05 km2 enclosed water cells are slivers between adjacent channels (drowned scraps, bed = front_d0),
    # reported separately; a "pond" must be at least min_island_km2 (same size rule as islands)
    lab_p, n_p = ndi.label(pond_left)
    area_p = np.bincount(lab_p.ravel(), minlength=n_p + 1)[1:] * dx * dx / 1e6
    big = area_p >= 0.05
    m['pond_check'] = dict(n_enclosed_ponds_left=int(big.sum()),
                           enclosed_pond_area_km2=float(area_p[big].sum()),
                           n_channel_slivers_lt_0p05km2=int((~big).sum()),
                           channel_sliver_area_km2=float(area_p[~big].sum()),
                           max_sliver_km2=float(area_p.max()) if n_p else 0.0)
    above = T['chan'] & (grid.U < g.params.apex_u - 60.0)
    comp, nc = ndi.label(T['chan'][:int((g.params.apex_u - grid.spec.u0_m) / dx) + 8])
    m['upstream_check'] = dict(n_chan_cells_above_apex_not_trunk=int(
        (above & ~(np.abs(grid.V) < 1200.0)).sum()), n_components_u_lt_apex=int(nc))
    return m
