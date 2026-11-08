"""Land building for the complex delta network v3 (rework of v2 / ``delta_network_terrain``).

What changed against v2 (v3)
----------------------------
* Old lobes are built from their *historical* discharge (lobe share x q_total), not the
  current edge discharge: cone radius ~ old_body_k*sqrt(Q_hist), only partly shrinking at the
  front, so a retreated old lobe is a low, wide plain and not a few thin strips.
* Plume fans are cut at a finite length behind the mouth and every emergent block must be
  connected: a connected component of (land | spit) that does not touch the mainland row is
  deleted unless its nearest channel centreline is within ``conn_N`` x that channel's width
  (hard check, recomputed in ``terrain_metrics_v3``).
* Land between channels is continuous: bank radius has a floor proportional to the channel
  width, little radius noise, the shore is morphologically closed (``close_radius_m``), and
  sub-resolution fragments (< ``min_island_km2``) are drowned into shoals instead of being
  kept as dots.

What changed against v1 (inherited from v2)
-------------------------------------------
* The shoreline is **built by the channels**, not by the analytic lobe outline:
  every channel point deposits a floodplain "cone" (S = R - d); the land is the union
  of these cones.  R is large (``r_plain_m``) on the upper plain (islands/plain between
  channels stay land) and shrinks towards the front to ``r_front0 + k*w`` (so
  wide channels carry wider levees/banks); every mouth adds a mouth-lobe cone chain
  whose radius grows with sqrt(Q).  Protrusions of the coast therefore sit at the mouths.
* Real widths: w = a*Q^b from the graph; the last ~1.5 km of every mouth flares into a funnel.
* Mouth bar: a mouth with a large enough funnel splits into two branches around an
  emergent / near-sea-level bar (elongated along flow, blunt upstream end is the lobe tip).
* Old lobes: their land field is blurred (rounded) and pulled back (retreat), the surface is
  lowered, and a dendritic tidal-creek network (wide at the sea, narrowing and branching
  landward) is cut from the old-lobe shore; no parallel stripes.
* The global lobe envelope is not used at all here (only as growth guide in the skeleton).

All coefficients are declared scenario values (``TerrainParamsV3``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from scipy.ndimage import gaussian_filter

from terrain_pipeline.delta_network_site import rng_for
from terrain_pipeline.delta_network_skeleton_v3 import edge_points, width_of
from terrain_pipeline.delta_network_terrain import (
    TerrainParams, _Grid, _Stamps, _densify, _smooth_noise, _smoothstep, terrain_metrics)

__all__ = ['TerrainParamsV3', 'build_terrain_v3', 'terrain_metrics_v3']


@dataclass(frozen=True)
class TerrainParamsV3(TerrainParams):
    # floodplain cones
    r_plain_m: float = 1400.0
    r_front0_m: float = 250.0
    r_front_k: float = 3.5
    plain_f0: float = 0.30
    plain_f1: float = 0.55
    radius_noise: float = 0.10
    r_floor_k: float = 1.1             # bank radius floor = k*w + r_floor_m (continuous banks)
    r_floor_m: float = 150.0
    close_radius_m: float = 450.0      # shore closing: fills inlets narrower than 2x this
    min_island_km2: float = 0.05       # smaller non-mainland pieces are drowned into shoals
    conn_N: float = 8.0                # emergent block must be <= N x channel width from a channel
    fan_cut_ls: float = 2.5            # plume fan cut at 0.6 lobe_len + this x plume length
    old_body_k: float = 45.0           # old-lobe cone radius = k*sqrt(Q_hist [m3/s]) (m)
    old_front_frac: float = 0.55       # old-lobe front radius floor = frac x body radius
    cone_step_m: float = 80.0
    coast_noise_m: float = 120.0
    # mouth lobes / bars
    lobe_k_m: float = 55.0             # lobe radius = lobe_k * sqrt(Q)
    lobe_len_factor: float = 1.6
    lobe_exp: float = 0.6
    funnel_len_m: float = 1500.0
    funnel_gain: float = 1.8
    bar_min_wf_m: float = 100.0
    bar_len_factor: float = 1.7
    bar_halfwidth_frac: float = 0.24
    # old lobes
    old_reach: float = 0.8
    old_round_cells: float = 6.0
    old_retreat_m: float = 250.0
    old_lower: float = 0.7
    # fans
    fan_len_m: float = 1400.0
    fan_emerge_share: float = 0.12
    # tidal creeks (dendritic)
    creek_spacing_m: float = 1500.0
    creek_step_m: float = 80.0
    creek_len_m: float = 5000.0
    creek_branch_p: float = 0.07
    creek_w0_m: float = 90.0
    creek_h0_m: float = 1.2
    creek_max_depth: int = 3


def _cones(S, grid, pu, pv, r):
    dx = grid.dx
    nu, nv = grid.shape
    u0, v0 = grid.spec.u0_m, grid.spec.v0_m
    for k in range(len(pu)):
        rk = float(r[k])
        cu = (pu[k] - u0) / dx - 0.5
        cv = (pv[k] - v0) / dx - 0.5
        n = int(rk / dx) + 2
        i0, i1 = max(int(cu) - n, 0), min(int(cu) + n + 2, nu)
        j0, j1 = max(int(cv) - n, 0), min(int(cv) + n + 2, nv)
        if i0 >= i1 or j0 >= j1:
            continue
        d = np.hypot(grid.U[i0:i1, j0:j1] - pu[k], grid.V[i0:i1, j0:j1] - pv[k])
        sub = S[i0:i1, j0:j1]
        np.maximum(sub, rk - d, out=sub)


def _dense_w(P, W, step):
    seg = np.hypot(*np.diff(P, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(int(math.ceil(s[-1] / step)), 1)
    t = np.linspace(0.0, s[-1], n + 1)
    return np.stack([np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])], axis=1), np.interp(t, s, W)


def _edge_rank(g, i):
    lobe = int(g.edge_lobe[i])
    return 0 if lobe < 0 else int(g.lobes[lobe]['rank'])


def _env_connectivity(env, grid, pts, wts, N):
    """Components of ``env`` not touching the mainland row; bad = nearest channel farther than N x width."""
    from scipy.spatial import cKDTree
    lab, n = ndi.label(env)
    bad = np.zeros(env.shape, bool)
    rep = dict(n_components=int(n), n_mainland_components=0, n_detached=0, n_detached_near_channel=0,
               n_detached_removed=0, max_kept_ratio=0.0, N=float(N))
    if n == 0:
        return bad, rep
    top = np.unique(lab[0, :])
    top = top[top > 0]
    rep['n_mainland_components'] = int(len(top))
    main = np.zeros(n + 1, bool)
    main[top] = True
    cand = (lab > 0) & ~main[lab]
    ii, jj = np.nonzero(cand)
    if len(ii) == 0:
        return bad, rep
    d, idx = cKDTree(pts).query(np.stack([grid.U[ii, jj], grid.V[ii, jj]], axis=1))
    ratio = d / np.maximum(wts[idx], 1.0)
    ids = np.unique(lab[ii, jj])
    mn = np.asarray(ndi.minimum(ratio, lab[ii, jj], index=ids))
    lut = np.zeros(n + 1, bool)
    lut[ids[mn > N]] = True
    rep['n_detached'] = int(len(ids))
    rep['n_detached_removed'] = int((mn > N).sum())
    rep['n_detached_near_channel'] = int((mn <= N).sum())
    rep['max_kept_ratio'] = float(mn[mn <= N].max()) if (mn <= N).any() else 0.0
    bad = lut[lab]
    return bad, rep


def _channel_points(g, mouths, step=100.0):
    P, W = [], []
    for i in range(len(g.edge_from)):
        Q = _densify(edge_points(g, i), step)
        P.append(Q)
        W.append(np.full(len(Q), float(g.edge_w[i])))
    for m in mouths:
        s = np.arange(0.0, m['Le_m'] + step, step)
        P.append(np.stack([m['pos'][0] + s * m['dir'][0], m['pos'][1] + s * m['dir'][1]], axis=1))
        W.append(np.full(len(s), m['w'] * (1 + 1.8)))
    return np.concatenate(P), np.concatenate(W)


def build_terrain_v3(spec, g, td_bed, td_ocean, tp: TerrainParamsV3 | None = None):
    tp = tp or TerrainParamsV3()
    p = g.params
    grid = _Grid(spec)
    dx = grid.dx
    U, V = grid.U, grid.V
    shape = grid.shape
    rng = rng_for('delta-network-v3/terrain', p.variant, world_seed=getattr(p, 'algorithm_world_seed', 20261020))

    # ---- 1. shoreline = union of channel-built floodplain cones ----------------------
    land_td = ~td_ocean
    s_td = (ndi.distance_transform_edt(land_td) - ndi.distance_transform_edt(~land_td)) * dx
    s_td = gaussian_filter(s_td, 2.0)
    rnoise = _smooth_noise(rng, shape, 2000.0 / dx, 1.0)
    S_y = np.full(shape, -3000.0)
    S_o = np.full(shape, -3000.0)

    n_nodes = len(g.node_uv)
    in_edges = [[] for _ in range(n_nodes)]
    for i in range(len(g.edge_from)):
        in_edges[int(g.edge_to[i])].append(i)

    for i in range(len(g.edge_from)):
        P = _densify(edge_points(g, i), tp.cone_step_m)
        du = P[:, 0] - p.apex_u
        rr = np.hypot(du, P[:, 1])
        guide = g.model.radius(np.arctan2(P[:, 1], du))
        f = _smoothstep(((rr / guide) - tp.plain_f0) / (tp.plain_f1 - tp.plain_f0))
        R = (1 - f) * tp.r_plain_m + f * (tp.r_front0_m + tp.r_front_k * g.edge_w[i])
        rank = _edge_rank(g, i)
        if rank > 0:
            lb = g.lobes[int(g.edge_lobe[i])]
            Rh = tp.old_body_k * math.sqrt(max(lb['share'] * p.q_total, 1.0))   # historical discharge
            R = (1 - f) * np.maximum(tp.r_plain_m, Rh) + f * np.maximum(
                tp.r_front0_m + tp.r_front_k * g.edge_w[i], tp.old_front_frac * Rh)
        nz = np.clip(grid.sample(rnoise, P[:, 0], P[:, 1]), -2.0, 2.0)
        R = np.maximum(R * (1 + tp.radius_noise * nz), tp.r_floor_k * g.edge_w[i] + tp.r_floor_m)
        _cones(S_y if rank == 0 else S_o, grid, P[:, 0], P[:, 1], R)

    mouths = []
    for n in g.mouth_nodes:
        n = int(n)
        e = max(in_edges[n], key=lambda i: (g.edge_q[i], -i))
        P = edge_points(g, e)
        d = P[-1] - P[max(-4, -len(P))]
        d = d / np.hypot(*d)
        q = float(g.node_q[n])
        rank = _edge_rank(g, e)
        Rm = tp.lobe_k_m * math.sqrt(q) * (tp.old_reach if rank > 0 else 1.0)
        mouths.append(dict(node=n, pos=g.node_uv[n].copy(), dir=d, q=q, share=q / p.q_total, rank=rank,
                           w=float(width_of(q, p)), h=float(p.depth_c * q ** p.depth_f), Rm=float(Rm)))
    for m in mouths:
        ls = tp.lobe_len_factor * m['Rm']
        s = np.arange(0.0, ls, 60.0)
        pu = m['pos'][0] + s * m['dir'][0]
        pv = m['pos'][1] + s * m['dir'][1]
        r = m['Rm'] * (1 - s / ls) ** tp.lobe_exp
        _cones(S_y if m['rank'] == 0 else S_o, grid, pu, pv, r)
        m['lobe_len_m'] = float(ls)

    S_ob = gaussian_filter(S_o, tp.old_round_cells) - tp.old_retreat_m
    S_d = np.maximum(S_y, S_ob)
    S_d = S_d + _smooth_noise(rng, shape, 1500.0 / dx, tp.coast_noise_m)
    S = np.maximum(s_td, S_d)
    land0 = S > 0
    if tp.close_radius_m > 0:
        from skimage.morphology import disk
        rc = int(round(tp.close_radius_m / dx))
        cl = ndi.binary_closing(np.pad(land0, rc, mode='edge'), structure=disk(rc))[rc:-rc, rc:-rc]
        S = np.where(cl & ~land0, 1.0, S)
        land0 = S > 0
    old_dom = (S_ob > S_y) & land0 & (s_td < S_ob)
    wo = gaussian_filter(old_dom.astype(float), 6.0)

    # ---- 2. plain surface ------------------------------------------------------------
    D = ndi.distance_transform_edt(land0) * dx
    z_p = tp.z0_m + tp.plain_slope * np.minimum(D, 50000.0)
    s_blend = _smoothstep((tp.td_blend_u[0] - U) / (tp.td_blend_u[0] - tp.td_blend_u[1]))
    z_td = np.maximum(td_bed, z_p)
    z_p = z_p + (z_td - z_p) * s_blend
    lower = 1.0 - tp.old_lower * wo * (1.0 - _smoothstep(D / tp.old_lower_band_m))
    z_p = z_p * lower
    micro = _smooth_noise(rng, shape, 400.0 / dx, tp.micro_relief_m)
    z_p = z_p + micro * (~(s_blend > 0.5))

    # ---- 3. sea bed, plume fans, mouth bars -------------------------------------------
    dist_sea = ndi.distance_transform_edt(~land0) * dx
    depth = np.minimum(tp.front_d0_m + tp.front_slope * dist_sea, spec.shelf_max_depth_m)
    shelf = np.where(td_ocean & (td_bed < 0), np.maximum(-td_bed, 0.0), 1e9)
    sea_bed = -np.minimum(depth, np.maximum(shelf, tp.front_d0_m))

    for m in mouths:
        ls = tp.fan_len_m * math.sqrt(m['q'] / 1000.0) + m['lobe_len_m'] * 0.3
        ls0 = ls
        wt = max(1.5 * m['w'], 0.35 * ls)
        rel_u = U - m['pos'][0]
        rel_v = V - m['pos'][1]
        s = rel_u * m['dir'][0] + rel_v * m['dir'][1]
        t = -rel_u * m['dir'][1] + rel_v * m['dir'][0]
        k = np.exp(-np.maximum(s - 0.6 * m['lobe_len_m'], 0) / ls) * \
            np.exp(-(t / (wt * (1 + 0.5 * np.maximum(s, 0) / ls))) ** 2)
        k = k * (s > 0.2 * m['lobe_len_m']) * (s < 0.6 * m['lobe_len_m'] + tp.fan_cut_ls * ls) * (~land0)
        target = tp.fan_emerge_m if m['share'] >= tp.fan_emerge_share else tp.fan_sub_m
        sea_bed = sea_bed + np.maximum(target - sea_bed, 0.0) * k
        m['fan_len_m'], m['fan_width_m'] = float(ls0), float(wt)

    n_bars = 0
    for m in mouths:
        Le = 0.85 * m['lobe_len_m']
        Wf = m['w'] * (1 + tp.funnel_gain)
        m['Le_m'], m['Wf_m'] = float(Le), float(Wf)
        m['bar'] = None
        if Wf < tp.bar_min_wf_m:
            continue
        Lb = tp.bar_len_factor * Wf
        a = 0.5 * Lb
        b = tp.bar_halfwidth_frac * Wf
        sc = Le + 0.5 * a
        m['bar'] = dict(s_c=float(sc), a=float(a), b=float(b))
        rel_u = U - m['pos'][0]
        rel_v = V - m['pos'][1]
        s = rel_u * m['dir'][0] + rel_v * m['dir'][1]
        t = -rel_u * m['dir'][1] + rel_v * m['dir'][0]
        qd = ((s - sc) / a) ** 2 + (t / b) ** 2
        bar = (qd < 1.0) & (~land0)
        sea_bed = np.where(bar, np.maximum(sea_bed, 0.06 + 0.3 * (1 - qd)), sea_bed)
        n_bars += 1

    spit = (~land0) & (sea_bed > 0.02)
    ch_pts, ch_w = _channel_points(g, mouths)
    bad, conn_build = _env_connectivity(land0 | spit, grid, ch_pts, ch_w, tp.conn_N)
    land0 = land0 & ~bad
    spit = spit & ~bad
    is_land_env = land0 | spit
    D_env = ndi.distance_transform_edt(is_land_env) * dx

    # ---- 4. channels ---------------------------------------------------------------------
    st = _Stamps(grid)

    def water_level(pu, pv):
        zp = grid.sample(z_p, pu, pv)
        return np.maximum(0.0, zp - tp.freeboard_m)

    def lev_params(h, w):
        hl = np.minimum(tp.levee_h_frac * h, tp.levee_h_max_m)
        lam = np.clip(w, tp.levee_lam_min_m, tp.levee_lam_max_m)
        return hl, lam

    for i in range(len(g.edge_from)):
        P = _densify(edge_points(g, i), tp.stamp_step_m)
        w = np.full(len(P), g.edge_w[i])
        h = np.full(len(P), g.edge_h[i])
        wl = water_level(P[:, 0], P[:, 1])
        hl, lam = lev_params(h, w)
        st.add(P[:, 0], P[:, 1], w, h, wl, hl, lam, tp.channel_floor)

    for m in mouths:
        Le = m['Le_m']
        d = m['dir']
        nrm = np.array([-d[1], d[0]])
        n_ext = max(int(Le / tp.stamp_step_m), 2)
        s = np.arange(1, n_ext + 1) * tp.stamp_step_m
        Lf = min(tp.funnel_len_m, Le)
        w = m['w'] * (1 + tp.funnel_gain * _smoothstep((s - (Le - Lf)) / Lf))
        h = m['h'] * (1 - 0.5 * s / Le)
        pu = m['pos'][0] + s * d[0]
        pv = m['pos'][1] + s * d[1]
        wl = water_level(pu, pv)
        st.add(pu, pv, w, h, wl, np.zeros(len(s)), np.full(len(s), 60.0), tp.channel_floor)
        if m['bar'] is not None:
            bd = m['bar']
            Wf = m['Wf_m']
            s1 = bd['s_c'] + bd['a'] + 0.9 * 2 * bd['a']
            sb = np.arange(Le, s1, tp.stamp_step_m)
            x = (sb - Le) / max(s1 - Le, 1.0)
            for sign in (1.0, -1.0):
                tt = sign * (0.45 * Wf * _smoothstep((sb - Le) / (0.6 * bd['a'] + 1.0)) +
                             math.tan(math.radians(9.0)) * np.maximum(sb - bd['s_c'], 0.0))
                wb = 0.42 * Wf * (1 - 0.5 * x)
                hb = m['h'] * 0.5 * (1 - 0.7 * x)
                pu = m['pos'][0] + sb * d[0] + tt * nrm[0]
                pv = m['pos'][1] + sb * d[1] + tt * nrm[1]
                st.add(pu, pv, wb, hb, np.zeros(len(sb)), np.zeros(len(sb)), np.full(len(sb), 60.0),
                       tp.channel_floor)

    # ---- dendritic tidal creeks on old-lobe fronts ---------------------------------------
    dsm = gaussian_filter(D, 3.0)
    gu, gv = np.gradient(dsm, dx)
    coast = land0 & (D <= 1.6 * dx) & (wo > 0.5) & (U > 1500)
    ci = np.argwhere(coast)
    n_tidal_pts = 0
    n_creeks = 0
    if len(ci):
        ci = ci[np.lexsort((ci[:, 1], ci[:, 0]))]
        ncr = max(int(len(ci) / (tp.creek_spacing_m / dx)), 1)
        pick = np.sort(rng.choice(len(ci), size=min(ncr, len(ci)), replace=False))
        step = tp.creek_step_m
        for idx in pick:
            pu0 = float(grid.u[ci[idx, 0]])
            pv0 = float(grid.v[ci[idx, 1]])
            ang0 = math.atan2(float(grid.sample(gv, pu0, pv0)), float(grid.sample(gu, pu0, pv0)))
            stack = [(pu0, pv0, ang0, 0.0, 1.0, 0, [(pu0, pv0)], [1.0])]
            n_creeks += 1
            while stack:
                cu_, cv_, ang, trav, wf, lvl, pts, ws = stack.pop()
                rem = tp.creek_len_m * (0.65 ** lvl)
                while trav < rem:
                    g1 = np.array([float(grid.sample(gu, cu_, cv_)), float(grid.sample(gv, cu_, cv_))])
                    if np.hypot(*g1) > 1e-9:
                        a2 = math.atan2(g1[1], g1[0])
                        ang += 0.3 * ((a2 - ang + math.pi) % (2 * math.pi) - math.pi)
                    ang += rng.normal(0, 0.3)
                    cu_ += step * math.cos(ang)
                    cv_ += step * math.sin(ang)
                    trav += step
                    if not (spec.u0_m + 200 < cu_ < spec.u0_m + spec.nu * dx - 200 and abs(cv_) < 23000):
                        break
                    if float(grid.sample(D, cu_, cv_)) < 0.3 * dx and trav > 3 * step:
                        break
                    pts.append((cu_, cv_))
                    ws.append(wf * (1.0 - 0.6 * min(trav / tp.creek_len_m, 1.0)) if lvl == 0 else
                              wf * (1.0 - 0.5 * min(trav / rem, 1.0)))
                    if lvl < tp.creek_max_depth and trav > 300.0 and rng.random() < tp.creek_branch_p:
                        sgn = 1.0 if rng.random() < 0.5 else -1.0
                        ang_b = ang + sgn * float(rng.uniform(0.45, 0.9))
                        stack.append((cu_, cv_, ang_b, 0.0, wf * 0.7 * (1.0 - 0.3 * min(trav / tp.creek_len_m, 1.0)),
                                      lvl + 1, [(cu_, cv_)], [ws[-1] * 0.7]))
                if len(pts) >= 2:
                    Pd, Wd = _dense_w(np.array(pts), np.array(ws), 20.0)
                    w_ = np.maximum(tp.creek_w0_m * Wd, 1.5 * dx)
                    h_ = tp.creek_h0_m * Wd
                    ok = (Pd[:, 0] > spec.u0_m + 200) & (Pd[:, 0] < spec.u0_m + spec.nu * dx - 200) & \
                         (np.abs(Pd[:, 1]) < 23000)
                    Pd, w_, h_ = Pd[ok], w_[ok], h_[ok]
                    n_tidal_pts += len(Pd)
                    st.add(Pd[:, 0], Pd[:, 1], w_, h_, np.zeros(len(Pd)), np.zeros(len(Pd)),
                           np.full(len(Pd), 60.0), tp.channel_floor, tidal=True)

    # ---- 5. compose ---------------------------------------------------------------------
    chan_water = st.chan
    # drown sub-resolution fragments that are not part of the mainland (no dotted islands)
    ld0 = is_land_env & ~chan_water
    lab0, n0 = ndi.label(ld0)
    top0 = np.unique(lab0[0, :])
    top0 = top0[top0 > 0]
    ar0 = np.bincount(lab0.ravel(), minlength=n0 + 1) * dx * dx / 1e6
    small = ar0 < tp.min_island_km2
    small[0] = False
    small[top0] = False
    kill = small[lab0]
    n_drowned = int(small.sum())
    if kill.any():
        is_land_env = is_land_env & ~kill
        spit = spit & ~kill
        sea_bed = np.where(kill, np.minimum(sea_bed, -0.15), sea_bed)
    z_land = np.maximum(z_p + st.lev, 0.03)
    bed = np.where(is_land_env, np.where(spit, sea_bed, z_land), sea_bed)
    bed = np.where(chan_water, np.minimum(st.bed, np.where(is_land_env, z_land, sea_bed)), bed)
    water = (~is_land_env) | chan_water
    land_dry = is_land_env & ~chan_water

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

    return dict(grid=grid, bed=bed.astype(np.float64), water=water, land_env=is_land_env, land_dry=land_dry,
                chan=chan_water, tidal=st.tidal, spit=spit, island_label=island_label, mainland=mainland,
                S=S, D_env=D_env, old_weight=wo, z_plain=z_p, mouths=mouths, n_tidal_pts=n_tidal_pts,
                n_creeks=n_creeks, n_bars=n_bars, levee=st.lev, conn_build=conn_build, n_drowned=n_drowned)


def terrain_metrics_v3(spec, g, T):
    from skimage.morphology import disk
    m = terrain_metrics(spec, g, T)
    grid = T['grid']
    p = g.params
    st_ = disk(25)
    solid = T['land_dry'] | T['chan']
    pad = 30
    pm = np.pad(solid, pad, mode='edge')
    env = ndi.binary_erosion(ndi.binary_dilation(pm, structure=st_), structure=st_, border_value=1)
    env = env[pad:-pad, pad:-pad] & (grid.U >= 2000.0)
    r_apex = np.hypot(grid.U - p.apex_u, grid.V)
    mr = np.hypot(g.node_uv[g.mouth_nodes, 0] - p.apex_u, g.node_uv[g.mouth_nodes, 1])
    far_mouth = float(mr.max())
    front = env & (r_apex >= 0.55 * far_mouth)
    plain = env & (grid.U < 15000.0)
    chan_net = T['chan'] & ~T['tidal']

    def frac(mask, zone):
        return float(mask[zone].mean()) if zone.any() else 0.0
    m['channel_area_fraction_envelope'] = frac(T['chan'], env)
    m['channel_area_fraction_front'] = frac(T['chan'], front)
    m['channel_area_fraction_front_network_only'] = frac(chan_net, front)
    m['channel_area_fraction_plain_u_lt_15km'] = frac(T['chan'], plain)
    m['envelope_area_km2'] = float(env.sum() * grid.dx ** 2 / 1e6)
    m['n_tidal_creeks'] = int(T['n_creeks'])
    m['n_mouth_bars'] = int(T['n_bars'])
    m['farthest_mouth_from_apex_km'] = far_mouth / 1000.0
    isl = T['island_label']
    if isl.max() > 0:
        areas = np.bincount(isl.ravel())[1:] * grid.dx ** 2 / 1e6
        idx = np.arange(1, isl.max() + 1)
        # elongation of islands >= 0.05 km2 (major/minor axis from second moments)
        el = []
        for k in idx[areas >= 0.05]:
            ii, jj = np.nonzero(isl == k)
            if len(ii) < 10:
                continue
            c = np.cov(np.stack([ii, jj]))
            ev = np.sort(np.linalg.eigvalsh(c))
            el.append(math.sqrt(max(ev[1], 1e-9) / max(ev[0], 1e-9)))
        m['island_elongation'] = dict(n=len(el), median=float(np.median(el)) if el else 0.0,
                                      p90=float(np.percentile(el, 90)) if el else 0.0)
        m['island_area_hist_km2'] = {k: int(v) for k, v in zip(
            ['<0.05', '0.05-0.5', '0.5-5', '5-50', '>50'],
            [np.sum(areas < 0.05), np.sum((areas >= 0.05) & (areas < 0.5)), np.sum((areas >= 0.5) & (areas < 5)),
             np.sum((areas >= 5) & (areas < 50)), np.sum(areas >= 50)])}
    # ---- v3: connectivity of the emergent land (hard check) and land-block statistics
    tp_N = float(T['conn_build']['N'])
    pts_, w_ = _channel_points(g, T['mouths'])
    bad, crep = _env_connectivity(T['land_env'], grid, pts_, w_, tp_N)
    crep = dict(crep)
    crep['n_remaining_violations'] = int(ndi.label(bad)[1])
    crep['n_removed_during_build'] = int(T['conn_build']['n_detached_removed'])
    crep['ok'] = bool(crep['n_remaining_violations'] == 0)
    m['island_connectivity'] = crep
    m['n_drowned_fragments'] = int(T['n_drowned'])
    dry = T['land_dry']
    lab, n = ndi.label(dry)
    delta_zone = grid.U >= 2000.0
    cnt = np.bincount(lab[delta_zone].ravel(), minlength=n + 1)
    cnt[0] = 0
    tot = float(cnt.sum())
    m['land_blocks'] = dict(
        n_blocks=int((cnt > 0).sum()),
        n_blocks_ge_0p05km2=int((cnt * grid.dx ** 2 / 1e6 >= 0.05).sum()),
        n_blocks_lt_0p05km2=int(((cnt > 0) & (cnt * grid.dx ** 2 / 1e6 < 0.05)).sum()),
        largest_block_share=float(cnt.max() / tot) if tot > 0 else 0.0,
        delta_land_area_km2=float(tot * grid.dx ** 2 / 1e6))
    return m
