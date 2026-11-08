"""Land building for the complex delta network v1 (P2).

Input: the channel graph from ``delta_network_skeleton`` plus the TD-derived
site surface from ``delta_network_site``.  Output: a float64 bed DEM (m above
sea level = 0), water mask, island labels and auxiliary masks on the local
grid (index [i_u, j_v], u seaward).

Order of construction
1. shoreline field S (m, >0 land): TD coast  (+)  analytic lobe outline, with a
   smooth noise term; old lobes get a rounded (blurred) lower shoreline.
2. plain surface z_p = z0 + slope*D (D = inland distance to the shore); inland
   strip blends to TD relief; old-lobe fronts are lowered.
3. sea bed: delta-front slope from the shore, capped by the declared shelf;
   plume fans/bars in front of every mouth (extent ~ sqrt(Q_mouth)) pulled
   towards sea level - the biggest mouths build emergent spits.
4. channels: every graph edge is stamped as a cross-section
   bed = wl - h*(1-(2d/w)^4) (floor 0.15 h), low natural levees beside it;
   each mouth is prolonged seaward as a tapering subaqueous channel; tidal
   creeks are cut into the old-lobe fronts (not part of the graph).
5. islands = connected land components not touching the inland edge.

All coefficients are declared scenario values (see ``TerrainParams``).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage as ndi
from scipy.ndimage import gaussian_filter, map_coordinates

from terrain_pipeline.delta_network_site import grid_centres, rng_for
from terrain_pipeline.delta_network_skeleton import edge_points, width_of


@dataclass(frozen=True)
class TerrainParams:
    z0_m: float = 0.4                 # plain height at the shore
    plain_slope: float = 1.0e-4       # declared
    freeboard_m: float = 0.8          # bank top above water level
    td_blend_u: tuple = (-1500.0, -3500.0)   # TD relief fully used beyond the second value
    coast_noise_m: float = 220.0
    coast_noise_corr_m: float = 1500.0
    old_round_cells: float = 18.0
    old_lower: float = 0.7
    old_lower_band_m: float = 4000.0
    front_d0_m: float = 0.3
    front_slope: float = 2.0e-3       # delta-front depth gradient (declared)
    stamp_step_m: float = 18.0
    levee_h_frac: float = 0.06
    levee_h_max_m: float = 0.6
    levee_lam_min_m: float = 60.0
    levee_lam_max_m: float = 150.0
    channel_floor: float = 0.15
    ext_len_m: float = 2600.0
    fan_len_m: float = 2000.0         # at Q = 1000 m3/s, scales with sqrt(Q)
    fan_emerge_share: float = 0.10    # mouths with >= this Q share build emergent spits
    fan_emerge_m: float = 0.25
    fan_sub_m: float = -0.45
    tidal_per_lobe: int = 14
    tidal_len_m: float = 3200.0
    tidal_w_m: float = 42.0
    tidal_h_m: float = 0.9
    micro_relief_m: float = 0.06

    def to_dict(self):
        return asdict(self)


def _smooth_noise(rng, shape, corr_cells, amp):
    f = gaussian_filter(rng.standard_normal(shape), corr_cells, mode='reflect')
    s = f.std()
    return f * (amp / s if s > 0 else 0.0)


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


class _Grid:
    def __init__(self, spec):
        self.spec = spec
        self.dx = spec.spacing_m
        self.u, self.v = grid_centres(spec)
        self.U, self.V = np.meshgrid(self.u, self.v, indexing='ij')
        self.shape = self.U.shape

    def sample(self, arr, pu, pv):
        iu = (np.asarray(pu, float) - self.spec.u0_m) / self.dx - 0.5
        iv = (np.asarray(pv, float) - self.spec.v0_m) / self.dx - 0.5
        shp = iu.shape
        out = map_coordinates(arr, [np.atleast_1d(iu).ravel(), np.atleast_1d(iv).ravel()],
                              order=1, mode='nearest')
        return out.reshape(shp) if shp else out[0]


class _Stamps:
    """Accumulates channel cross-sections on the grid."""

    def __init__(self, grid):
        self.g = grid
        self.bed = np.full(grid.shape, np.inf)
        self.chan = np.zeros(grid.shape, bool)
        self.lev = np.zeros(grid.shape)
        self.tidal = np.zeros(grid.shape, bool)

    def add(self, pu, pv, w, h, wl, hl, lam, floor, tidal=False):
        g, dx = self.g, self.g.dx
        nu, nv = g.shape
        u0, v0 = g.spec.u0_m, g.spec.v0_m
        for k in range(len(pu)):
            we = max(w[k], 1.5 * dx)
            rad = we / 2 + 4 * lam[k]
            cu = (pu[k] - u0) / dx - 0.5
            cv = (pv[k] - v0) / dx - 0.5
            r = int(math.ceil(rad / dx)) + 1
            i0, i1 = max(int(cu) - r, 0), min(int(cu) + r + 2, nu)
            j0, j1 = max(int(cv) - r, 0), min(int(cv) + r + 2, nv)
            if i0 >= i1 or j0 >= j1:
                continue
            d = np.hypot(g.U[i0:i1, j0:j1] - pu[k], g.V[i0:i1, j0:j1] - pv[k])
            inside = d < we / 2
            if inside.any():
                prof = np.maximum(1.0 - (2 * d / we) ** 4, floor)
                cb = wl[k] - h[k] * prof
                sub = self.bed[i0:i1, j0:j1]
                sub[inside] = np.minimum(sub[inside], cb[inside])
                self.chan[i0:i1, j0:j1] |= inside
                if tidal:
                    self.tidal[i0:i1, j0:j1] |= inside
            if hl[k] > 0:
                out = (~inside) & (d < we / 2 + 4 * lam[k])
                lv = np.where(out, hl[k] * np.exp(-(d - we / 2) / lam[k]), 0.0)
                self.lev[i0:i1, j0:j1] = np.maximum(self.lev[i0:i1, j0:j1], lv)


def _densify(P, step):
    """Resample a polyline at ~step spacing (includes both ends). Returns (n,2)."""
    seg = np.hypot(*np.diff(P, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(int(math.ceil(s[-1] / step)), 1)
    t = np.linspace(0.0, s[-1], n + 1)
    return np.stack([np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])], axis=1)


def _lobe_weights(model, U, V, apex_u):
    du = U - apex_u
    phi = np.arctan2(V, du)
    tot = np.zeros_like(U)
    old = np.zeros_like(U)
    for lb in model.lobes:
        c = lb['R'] * np.exp(-((phi - lb['theta']) / lb['sigma']) ** 2)
        tot += c
        if lb['rank'] >= 1:
            old += c
    return old / (tot + 1e-9)


def build_terrain(spec, g, td_bed, td_ocean, tp: TerrainParams | None = None):
    tp = tp or TerrainParams()
    p = g.params
    grid = _Grid(spec)
    dx = grid.dx
    U, V = grid.U, grid.V
    shape = grid.shape
    rng = rng_for('delta-network/terrain', p.variant)

    # ---- 1. shoreline field -------------------------------------------------
    land_td = ~td_ocean
    s_td = (ndi.distance_transform_edt(land_td) - ndi.distance_transform_edt(~land_td)) * dx
    s_td = gaussian_filter(s_td, 2.0)
    du = U - p.apex_u
    r = np.hypot(du, V)
    phi = np.arctan2(V, du)
    s_lobe = g.model.radius(phi) - r
    S = np.maximum(s_td, s_lobe)
    S = S + _smooth_noise(rng, shape, tp.coast_noise_corr_m / dx, tp.coast_noise_m)
    wo = _lobe_weights(g.model, U, V, p.apex_u)
    wo = gaussian_filter(wo, 6.0) * (S > -6000)
    S_blur = gaussian_filter(S, tp.old_round_cells)
    S = S + wo * (S_blur - S)
    land0 = S > 0

    # ---- 2. plain surface ----------------------------------------------------
    D = ndi.distance_transform_edt(land0) * dx
    z_p = tp.z0_m + tp.plain_slope * np.minimum(D, 50000.0)
    s_blend = _smoothstep((tp.td_blend_u[0] - U) / (tp.td_blend_u[0] - tp.td_blend_u[1]))
    z_td = np.maximum(td_bed, z_p)
    z_p = z_p + (z_td - z_p) * s_blend
    lower = 1.0 - tp.old_lower * wo * (1.0 - _smoothstep(D / tp.old_lower_band_m))
    z_p = z_p * lower
    micro = _smooth_noise(rng, shape, 400.0 / dx, tp.micro_relief_m)
    z_p = z_p + micro * (~(s_blend > 0.5))

    # ---- 3. sea bed + mouth fans ----------------------------------------------
    dist_sea = ndi.distance_transform_edt(~land0) * dx
    depth = np.minimum(tp.front_d0_m + tp.front_slope * dist_sea, spec.shelf_max_depth_m)
    shelf = np.where(td_ocean & (td_bed < 0), np.maximum(-td_bed, 0.0), 1e9)
    sea_bed = -np.minimum(depth, np.maximum(shelf, tp.front_d0_m))

    n_nodes = len(g.node_uv)
    in_edges = [[] for _ in range(n_nodes)]
    for i in range(len(g.edge_from)):
        in_edges[int(g.edge_to[i])].append(i)
    mouths = []
    for n in g.mouth_nodes:
        n = int(n)
        e = max(in_edges[n], key=lambda i: (g.edge_q[i], -i))
        P = edge_points(g, e)
        d = P[-1] - P[-2]
        d = d / np.hypot(*d)
        mouths.append(dict(node=n, pos=g.node_uv[n].copy(), dir=d, q=float(g.node_q[n]),
                           share=float(g.node_q[n] / p.q_total),
                           w=float(width_of(g.node_q[n], p)), h=float(p.depth_c * g.node_q[n] ** p.depth_f)))
    for m in mouths:
        ls = tp.fan_len_m * math.sqrt(m['q'] / 1000.0)
        wt = max(1.5 * m['w'], 0.35 * ls)
        rel_u = U - m['pos'][0]
        rel_v = V - m['pos'][1]
        s = rel_u * m['dir'][0] + rel_v * m['dir'][1]
        t = -rel_u * m['dir'][1] + rel_v * m['dir'][0]
        k = np.exp(-np.maximum(s, 0) / ls) * np.exp(-(t / (wt * (1 + 0.5 * np.maximum(s, 0) / ls))) ** 2)
        k = k * (s > -0.3 * ls) * (~land0)
        target = tp.fan_emerge_m if m['share'] >= tp.fan_emerge_share else tp.fan_sub_m
        up = np.maximum(target - sea_bed, 0.0) * k
        sea_bed = sea_bed + up
        m['fan_len_m'], m['fan_width_m'] = float(ls), float(wt)
    spit = (~land0) & (sea_bed > 0.02)
    is_land_env = land0 | spit
    D_env = ndi.distance_transform_edt(is_land_env) * dx

    # ---- 4. channels ----------------------------------------------------------
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
        n_ext = int(tp.ext_len_m / tp.stamp_step_m)
        s = np.arange(1, n_ext + 1) * tp.stamp_step_m
        pu = m['pos'][0] + s * m['dir'][0]
        pv = m['pos'][1] + s * m['dir'][1]
        taper = np.maximum(1.0 - s / tp.ext_len_m, 0.0) ** 1.5
        w = np.full(len(s), m['w'])
        h = m['h'] * (0.25 + 0.75 * taper)
        wl = water_level(pu, pv)
        st.add(pu, pv, w, h, wl, np.zeros(len(s)), np.full(len(s), 60.0), tp.channel_floor)

    # tidal creeks on old-lobe fronts
    dsm = gaussian_filter(D_env, 3.0)
    gu, gv = np.gradient(dsm, dx)
    coast = land0 & (D <= 1.6 * dx) & (wo > 0.55) & (U > 1500)
    ci = np.argwhere(coast)
    n_tidal_pts = 0
    if len(ci):
        lobe_of = np.zeros(shape, np.int16)
        best = np.full(shape, -1.0)
        for lb in g.lobes:
            c = lb['R'] * np.exp(-((phi - lb['theta']) / lb['sigma']) ** 2)
            upd = c > best
            lobe_of = np.where(upd, lb['id'], lobe_of)
            best = np.where(upd, c, best)
        for lb in g.lobes:
            if lb['rank'] < 1:
                continue
            sel = ci[lobe_of[ci[:, 0], ci[:, 1]] == lb['id']]
            if len(sel) == 0:
                continue
            sel = sel[np.lexsort((sel[:, 1], sel[:, 0]))]
            pick = rng.choice(len(sel), size=min(tp.tidal_per_lobe, len(sel)), replace=False)
            for idx in sorted(pick):
                pu = float(grid.u[sel[idx, 0]]); pv = float(grid.v[sel[idx, 1]])
                pts, ws = [], []
                walkers = [(pu, pv, tp.tidal_len_m, 1.0, 0)]
                while walkers:
                    cu_, cv_, remaining, wf, depth_lvl = walkers.pop()
                    gd = np.array([float(grid.sample(gu, cu_, cv_)), float(grid.sample(gv, cu_, cv_))])
                    nrm = np.hypot(*gd)
                    heading = gd / nrm if nrm > 1e-9 else np.array([-1.0, 0.0])
                    ang = math.atan2(heading[1], heading[0])
                    steps = int(remaining / 100.0)
                    for _ in range(steps):
                        ang += rng.normal(0, 0.35)
                        gd = np.array([float(grid.sample(gu, cu_, cv_)), float(grid.sample(gv, cu_, cv_))])
                        if np.hypot(*gd) > 1e-9:
                            a2 = math.atan2(gd[1], gd[0])
                            ang += 0.35 * ((a2 - ang + math.pi) % (2 * math.pi) - math.pi)
                        cu_ += 100.0 * math.cos(ang); cv_ += 100.0 * math.sin(ang)
                        pts.append((cu_, cv_)); ws.append(wf)
                        if depth_lvl < 2 and rng.random() < 0.06:
                            walkers.append((cu_, cv_, remaining * 0.45, wf * 0.75, depth_lvl + 1))
                        wf *= 0.985
                if pts:
                    pts = np.array(pts); ws = np.array(ws)
                    ok = (pts[:, 0] > spec.u0_m + 200) & (pts[:, 0] < spec.u0_m + spec.nu * dx - 200) & \
                         (np.abs(pts[:, 1]) < 23000)
                    pts, ws = pts[ok], ws[ok]
                    n_tidal_pts += len(pts)
                    w_ = np.maximum(tp.tidal_w_m * ws, 1.5 * dx)
                    h_ = tp.tidal_h_m * ws
                    st.add(pts[:, 0], pts[:, 1], w_, h_, np.zeros(len(pts)), np.zeros(len(pts)),
                           np.full(len(pts), 60.0), tp.channel_floor, tidal=True)

    # ---- 5. compose -----------------------------------------------------------
    z_land = np.maximum(z_p + st.lev, 0.03)
    bed = np.where(is_land_env, np.where(spit, sea_bed, z_land), sea_bed)
    chan_water = st.chan
    bed = np.where(chan_water, np.minimum(st.bed, np.where(is_land_env, z_land, sea_bed)), bed)
    water = (~is_land_env) | chan_water
    # land cells that remain above water but are not channel
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
                levee=st.lev)


def terrain_metrics(spec, g, T):
    grid = T['grid']
    dx = grid.dx
    p = g.params
    env = T['land_env']
    edge = env & ~ndi.binary_erosion(env, border_value=1)
    iu, iv = np.nonzero(edge)
    cu, cv = grid.u[iu], grid.v[iv]
    dist = np.hypot(cu - p.apex_u, cv)
    far = float(dist.max()) if len(dist) else 0.0
    sel = env & (grid.U >= 3000.0)
    if sel.any():
        vv = grid.V[sel]
        width3 = float(vv.max() - vv.min() + dx)
    else:
        width3 = 0.0
    sel0 = env & (grid.U >= 0.0) & ~T['spit']
    width0 = float(grid.V[sel0].max() - grid.V[sel0].min() + dx) if sel0.any() else 0.0
    # shoreline length / straight length (envelope ignoring channels), via marching squares
    from skimage import measure
    f = gaussian_filter(env.astype(float), 1.0)
    best = None
    for c in measure.find_contours(f, 0.5):
        if len(c) < 10:
            continue
        L = float(np.sum(np.hypot(*np.diff(c, axis=0).T))) * dx
        if best is None or L > best[0]:
            best = (L, float(np.hypot(*(c[0] - c[-1]))) * dx)
    isl = T['island_label']
    n_isl = int(isl.max())
    areas = np.bincount(isl.ravel())[1:] * dx * dx / 1e6 if n_isl else np.array([])
    big = areas[areas >= 0.05] if n_isl else areas

    def pct(a, q):
        return float(np.percentile(a, q)) if len(a) else 0.0
    return dict(
        apex_to_farthest_shore_km=far / 1000.0,
        alongshore_width_u_ge_3km_km=width3 / 1000.0,
        alongshore_width_u_ge_0_km=width0 / 1000.0,
        shoreline_length_km=(best[0] / 1000.0 if best else 0.0),
        shoreline_straight_km=(best[1] / 1000.0 if best else 0.0),
        shoreline_ratio=(best[0] / best[1] if best else 0.0),
        n_islands=n_isl, n_islands_ge_0p05km2=int(len(big)),
        island_area_km2=dict(total=float(areas.sum()) if n_isl else 0.0, median=pct(areas, 50),
                             p90=pct(areas, 90), max=float(areas.max()) if n_isl else 0.0),
        water_fraction_of_delta=float(T['water'][(grid.U > 0)].mean()),
        bed_min_m=float(T['bed'].min()), bed_max_m=float(T['bed'].max()),
        nan_count=int(np.isnan(T['bed']).sum()),
        n_mouths=len(T['mouths']), n_tidal_points=int(T['n_tidal_pts']),
    )
