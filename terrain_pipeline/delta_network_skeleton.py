"""Procedural channel skeleton for the complex delta network v1 (P1).

Everything here lives in the local metric frame of ``delta_network_site``
(u seaward, v along shore, metres).  World coordinates are only produced at
export time.

Structure of the generated network
----------------------------------
* lobe level   - the river enters at the apex; 2-4 avulsion nodes close to the
  apex split off one distributary trunk per lobe.  Lobes have an age rank:
  the youngest carries the largest share and reaches farthest seaward, older
  lobes carry less and their coast has retreated (smaller radius).
* bifurcation level - every distributary splits repeatedly (mouth-bar
  bifurcations).  Spacing L_b = beta * w (beta: from memory, Edmonds &
  Slingerland 2007).  The discharge split is asymmetric (0.5-0.8), the larger
  child deflects little, the smaller one a lot.  Recursion stops at
  ``max_level`` or when a child would be narrower than 1.5 cells.
* confluences / lateral links - channels that run into a foreign channel
  with a legal merge angle join it (node with in-degree > 1); additional
  lateral connecting channels leave a big channel sideways and join a
  neighbour.  Together they close loops (graph is a DAG, not a tree).

Paths are grown step by step (``step_m``).  The heading follows persistent
noise (OU), a goal direction, the coast normal, the gradient of a synthetic
plain surface (declared: linear ramp to the coast plus smooth relief), and
repulsion from foreign channels.  Turn rule: every step is limited to
``max_turn_deg`` (<=45, no penalty) and every junction angle is checked with
``river_path_geometry.turn_allowed`` (<90 deg).

Flow: every node splits its through-flow over its out edges with fixed
fractions, evaluated in topological order, so conservation holds to rounding.
Width/depth follow w = a*Q^b, h = c*Q^f (exponents Leopold & Maddock 1953;
coefficients are declared scenario values, see ``DeltaParams``).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage as ndi
from scipy.ndimage import gaussian_filter

from terrain_pipeline.delta_network_site import derive_seed, rng_for
from terrain_pipeline.channel_geometry import turn_allowed, turn_penalty

NODE_KINDS = ('source', 'avulsion', 'bifurcation', 'confluence', 'link_start', 'mouth')
EDGE_KINDS = ('trunk', 'lobe', 'distributary', 'link')
WINDOW_U = (-4000.0, 44000.0)
WINDOW_V = (-24000.0, 24000.0)


@dataclass(frozen=True)
class DeltaParams:
    variant: str = 'base'
    q_total: float = 8000.0            # m3/s, declared scenario
    # lobes / coast
    n_lobes: int = 4
    apex_u: float = -600.0             # inlet position (u), v = 0
    base_coast_u: float = 0.0          # pre-delta TD coast
    r_young: float = 36000.0           # radius of the youngest lobe from apex
    r_decay: float = 0.80              # radius factor per age rank
    share_ratio: float = 0.55          # discharge share factor per age rank
    spread_deg: float = 36.0
    angle_jitter_deg: float = 8.0
    sigma_young_deg: float = 32.0
    sigma_old_deg: float = 27.0
    max_lateral_m: float = 21000.0     # R*sin(theta) clamp (window half width 24 km)
    coast_noise_amp: float = 0.05
    # hydraulic geometry (exponents: Leopold & Maddock 1953; coefficients declared)
    width_a: float = 3.5
    width_b: float = 0.5
    depth_c: float = 0.4
    depth_f: float = 0.4
    cell_m: float = 30.0
    # bifurcation
    beta: float = 6.0                  # L_b = beta*w (memory: Edmonds & Slingerland 2007)
    asym_lo: float = 0.5
    asym_hi: float = 0.8
    max_level: int = 6
    min_child_cells: float = 1.5
    major_defl_deg: tuple = (4.0, 16.0)
    minor_defl_deg: tuple = (22.0, 48.0)
    # path growth
    step_m: float = 240.0
    avul_first_m: float = 900.0
    avul_gap_m: float = 1100.0
    c_goal: float = 1.3
    c_fwd: float = 1.0
    c_terr: float = 0.25
    c_coast: float = 0.5
    coast_pull_m: float = 2000.0
    c_rep: float = 1.2
    rep_range_m: float = 1600.0
    noise_amp: float = 0.55
    noise_corr_m: float = 2500.0
    max_turn_deg: float = 15.0
    steer_gain: float = 0.6
    relief_amp_m: float = 0.4
    relief_corr_m: float = 6000.0
    plain_slope: float = 1.0e-4
    # loops
    link_prob: float = 0.6
    link_donor_q_min: float = 700.0
    link_frac: tuple = (0.08, 0.22)
    link_range_m: tuple = (1200.0, 5500.0)
    merge_max_deg: float = 80.0
    zone_m: float = 1500.0
    max_steps: int = 1500

    def to_dict(self):
        return asdict(self)


def width_of(q, p):
    return p.width_a * np.power(q, p.width_b)


def depth_of(q, p):
    return p.depth_c * np.power(q, p.depth_f)


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# --------------------------------------------------------------------------- coast model
class CoastModel:
    """Analytic delta outline: base coast plus lobes in polar form about the apex."""

    def __init__(self, p: DeltaParams, lobes, harmonics):
        self.apex_u = p.apex_u
        self.base_u = p.base_coast_u
        self.lobes = lobes
        self.harm = harmonics

    def radius(self, phi):
        phi = np.asarray(phi, float)
        R = np.zeros_like(phi)
        for lb in self.lobes:
            R = np.maximum(R, lb['R'] * np.exp(-((phi - lb['theta']) / lb['sigma']) ** 2))
        h = np.ones_like(phi)
        for a, m, ph in self.harm:
            h = h + a * np.cos(m * phi + ph)
        return R * h

    def land(self, u, v):
        u = np.asarray(u, float)
        v = np.asarray(v, float)
        du = u - self.apex_u
        r = np.hypot(du, v)
        phi = np.arctan2(v, du)
        return (u < self.base_u) | (r < self.radius(phi))

    def signed(self, u, v):
        """Pseudo signed distance (m, >0 on land) along the radial direction."""
        u = np.asarray(u, float)
        v = np.asarray(v, float)
        du = u - self.apex_u
        r = np.hypot(du, v)
        phi = np.arctan2(v, du)
        return np.maximum(self.radius(phi) - r, self.base_u - u)


def plan_lobes(p: DeltaParams, rng):
    n = p.n_lobes
    base = (np.arange(n) - (n - 1) / 2.0) * p.spread_deg
    ang = np.radians(base + rng.uniform(-p.angle_jitter_deg, p.angle_jitter_deg, n))
    order = np.argsort(ang)
    ang = ang[order]
    central = np.argsort(np.abs(ang))[:2 if n % 2 == 0 else 1]
    youngest = int(central[int(rng.integers(len(central)))])
    rank = np.zeros(n, int)
    others = [i for i in range(n) if i != youngest]
    perm = rng.permutation(len(others))
    for k, i in enumerate(others):
        rank[i] = 1 + int(perm[k])
    lobes = []
    shares = p.share_ratio ** rank
    shares = shares / shares.sum()
    for i in range(n):
        R = p.r_young * p.r_decay ** rank[i] * float(rng.uniform(0.95, 1.05))
        R = min(R, p.max_lateral_m / max(abs(math.sin(ang[i])), 0.3))
        sig = math.radians(p.sigma_young_deg if rank[i] == 0 else p.sigma_old_deg)
        lobes.append(dict(id=i, rank=int(rank[i]), theta=float(ang[i]), R=float(R),
                          sigma=float(sig), share=float(shares[i])))
    harm = []
    for j in range(4):
        harm.append((float(p.coast_noise_amp / math.sqrt(j + 1) * rng.uniform(0.5, 1.0)),
                     int(rng.integers(4, 14)), float(rng.uniform(0, 2 * math.pi))))
    return lobes, harm, youngest


# --------------------------------------------------------------------------- steering field
class _Field:
    """Coarse fields used for steering: inland depth D, plain-surface gradient, coast normal."""

    def __init__(self, p: DeltaParams, model: CoastModel, rng):
        dx = 120.0
        self.dx = dx
        window_u = getattr(p, 'window_u_m', WINDOW_U)
        window_v = getattr(p, 'window_v_m', WINDOW_V)
        self.u0, self.v0 = window_u[0], window_v[0]
        nu = int(round((window_u[1] - window_u[0]) / dx))
        nv = int(round((window_v[1] - window_v[0]) / dx))
        self.nu, self.nv = nu, nv
        uc = self.u0 + (np.arange(nu) + 0.5) * dx
        vc = self.v0 + (np.arange(nv) + 0.5) * dx
        U, V = np.meshgrid(uc, vc, indexing='ij')
        land = model.land(U, V)
        d_in = ndi.distance_transform_edt(land) * dx
        d_out = ndi.distance_transform_edt(~land) * dx
        D = np.where(land, d_in - 0.5 * dx, -(d_out - 0.5 * dx))
        Ds = gaussian_filter(D, 2.0, mode='nearest')
        noise = gaussian_filter(rng.standard_normal((nu, nv)), p.relief_corr_m / dx, mode='reflect')
        noise = noise / noise.std()
        z = p.plain_slope * Ds + p.relief_amp_m * noise
        gu, gv = np.gradient(z, dx)
        nu_, nv_ = np.gradient(Ds, dx)
        nrm = np.hypot(nu_, nv_) + 1e-12
        F = np.stack([D, -gu, -gv, -nu_ / nrm, -nv_ / nrm], axis=-1)
        self.F = F

    def sample(self, u, v):
        x = min(max((u - self.u0) / self.dx - 0.5, 0.0), self.nu - 1.001)
        y = min(max((v - self.v0) / self.dx - 0.5, 0.0), self.nv - 1.001)
        i, j = int(x), int(y)
        fx, fy = x - i, y - j
        F = self.F
        return (F[i, j] * (1 - fx) * (1 - fy) + F[i + 1, j] * fx * (1 - fy) +
                F[i, j + 1] * (1 - fx) * fy + F[i + 1, j + 1] * fx * fy)


# --------------------------------------------------------------------------- builder
class _Walker:
    __slots__ = ('pos', 'psi', 'goal', 'Q', 'level', 'lobe', 'kind', 'edge', 'n0', 'own',
                 'zone_edges', 'zone_pt', 's_total', 's_split', 's_birth', 'next_split',
                 'split_p', 'xi', 'steps', 'dead', 'avul', 'can_split', 'target', 'rep_on')


def _unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 0 else (1.0, 0.0)


class _Builder:
    CELL = 900.0

    def __init__(self, p, model, field, lobes, youngest, rng):
        self.p, self.model, self.field, self.lobes, self.rng = p, model, field, lobes, rng
        self.youngest = youngest
        self.node_pos, self.node_kind = [], []
        self.edges = []
        self.segs, self.seg_edge = [], []
        self.hash = {}
        self.walkers, self.open = [], {}
        self.q_min_child = (p.min_child_cells * p.cell_m / p.width_a) ** (1.0 / p.width_b)
        self.umax = WINDOW_U[1] - 500.0
        self.vmax = WINDOW_V[1] - 500.0

    # ----- graph primitives
    def add_node(self, pos, kind):
        self.node_pos.append((float(pos[0]), float(pos[1])))
        self.node_kind.append(kind)
        return len(self.node_pos) - 1

    def new_edge(self, frm, pos, kind, level, lobe, frac):
        self.edges.append(dict(frm=frm, to=None, pts=[(float(pos[0]), float(pos[1]))], segs=[],
                               kind=kind, level=level, lobe=lobe, frac=frac))
        return len(self.edges) - 1

    def _hash_seg(self, sid):
        a, b = self.segs[sid][:2], self.segs[sid][2:]
        c = self.CELL
        for i in range(int(math.floor(min(a[0], b[0]) / c)), int(math.floor(max(a[0], b[0]) / c)) + 1):
            for j in range(int(math.floor(min(a[1], b[1]) / c)), int(math.floor(max(a[1], b[1]) / c)) + 1):
                self.hash.setdefault((i, j), []).append(sid)

    def extend_edge(self, eid, pt):
        e = self.edges[eid]
        a = e['pts'][-1]
        pt = (float(pt[0]), float(pt[1]))
        self.segs.append((a[0], a[1], pt[0], pt[1]))
        self.seg_edge.append(eid)
        sid = len(self.segs) - 1
        e['segs'].append(sid)
        e['pts'].append(pt)
        self._hash_seg(sid)

    def split_edge(self, eid, k, s, kind):
        e = self.edges[eid]
        A, B = e['pts'][k], e['pts'][k + 1]
        m = (A[0] + s * (B[0] - A[0]), A[1] + s * (B[1] - A[1]))
        nid = self.add_node(m, kind)
        e2 = dict(frm=nid, to=e['to'], pts=[m] + e['pts'][k + 1:], segs=[],
                  kind=e['kind'], level=e['level'], lobe=e['lobe'], frac=1.0)
        self.segs[e['segs'][k]] = (A[0], A[1], m[0], m[1])
        self.segs.append((m[0], m[1], B[0], B[1]))
        self.seg_edge.append(len(self.edges))
        new_sid = len(self.segs) - 1
        e2['segs'] = [new_sid] + e['segs'][k + 1:]
        e['pts'] = e['pts'][:k + 1] + [m]
        e['segs'] = e['segs'][:k + 1]
        e['to'] = nid
        e2id = len(self.edges)
        self.edges.append(e2)
        for sid in e2['segs']:
            self.seg_edge[sid] = e2id
        self._hash_seg(new_sid)
        if eid in self.open:
            w = self.open.pop(eid)
            w.own.add(eid)
            w.edge = e2id
            self.open[e2id] = w
        return nid, e2id

    def reaches(self, start, goal):
        """True when node ``goal`` is reachable from node ``start`` over closed edges."""
        if start is None:
            return False
        if start == goal:
            return True
        out = {}
        for e in self.edges:
            if e['to'] is not None:
                out.setdefault(e['frm'], []).append(e['to'])
        seen, stack = {start}, [start]
        while stack:
            n = stack.pop()
            for m in out.get(n, ()):
                if m == goal:
                    return True
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        return False

    # ----- walkers
    def new_walker(self, node, pos, psi, goal, Q, level, lobe, kind, frac, parent_edges=(), avul=None):
        p = self.p
        w = _Walker()
        ekind = 'trunk' if kind == 'trunk' else ('link' if kind == 'link' else ('lobe' if level <= 1 else 'distributary'))
        w.edge = self.new_edge(node, pos, ekind, level, lobe, frac)
        w.n0, w.pos, w.psi, w.goal, w.Q = node, (float(pos[0]), float(pos[1])), psi, goal, Q
        w.level, w.lobe, w.kind = level, lobe, kind
        w.own = set()
        w.zone_edges = set(parent_edges)
        w.zone_pt = w.pos
        w.s_total = w.s_split = w.s_birth = 0.0
        w.xi = float(self.rng.standard_normal())
        w.steps = 0
        w.dead = False
        w.avul = avul or []
        w.target = None
        w.can_split = kind in ('lobe', 'distributary') and level < p.max_level
        w.rep_on = kind not in ('trunk', 'link')
        wd = float(width_of(Q, p))
        w.next_split = p.beta * wd * float(self.rng.uniform(0.8, 1.3))
        w.split_p = float(self.rng.uniform(p.asym_lo, p.asym_hi))
        self.walkers.append(w)
        self.open[w.edge] = w
        return w

    def finish(self, w, node):
        self.edges[w.edge]['to'] = node
        self.open.pop(w.edge, None)
        w.dead = True

    # ----- geometry queries
    def _cells(self, a, b, pad=0.0):
        c = self.CELL
        for i in range(int(math.floor((min(a[0], b[0]) - pad) / c)), int(math.floor((max(a[0], b[0]) + pad) / c)) + 1):
            for j in range(int(math.floor((min(a[1], b[1]) - pad) / c)), int(math.floor((max(a[1], b[1]) + pad) / c)) + 1):
                yield (i, j)

    def _skip_seg(self, w, sid):
        eid = self.seg_edge[sid]
        if eid == w.edge or eid in w.own:
            return True
        if eid in w.zone_edges and w.s_birth < 4.0 * self.p.zone_m:
            s = self.segs[sid]
            if math.hypot(0.5 * (s[0] + s[2]) - w.zone_pt[0], 0.5 * (s[1] + s[3]) - w.zone_pt[1]) < self.p.zone_m:
                return True
        return False

    def repulsion(self, w, P):
        R = self.p.rep_range_m
        rx = ry = 0.0
        seen = set()
        for cell in self._cells(P, P, R):
            for sid in self.hash.get(cell, ()):
                if sid in seen:
                    continue
                seen.add(sid)
                if self._skip_seg(w, sid):
                    continue
                s = self.segs[sid]
                dx, dy = P[0] - 0.5 * (s[0] + s[2]), P[1] - 0.5 * (s[1] + s[3])
                d = math.hypot(dx, dy)
                if 1e-6 < d < R:
                    k = (1 - d / R) ** 2 / d
                    rx += dx * k
                    ry += dy * k
        n = math.hypot(rx, ry)
        if n > 2.0:
            rx, ry = rx * 2.0 / n, ry * 2.0 / n
        return rx, ry

    def first_hit(self, w, P, Qp):
        ids = []
        seen = set()
        for cell in self._cells(P, Qp):
            for sid in self.hash.get(cell, ()):
                if sid not in seen:
                    seen.add(sid)
                    if not self._skip_seg(w, sid):
                        ids.append(sid)
        if not ids:
            return None
        S = np.array([self.segs[i] for i in ids])
        rx, ry = Qp[0] - P[0], Qp[1] - P[1]
        sx, sy = S[:, 2] - S[:, 0], S[:, 3] - S[:, 1]
        den = rx * sy - ry * sx
        apx, apy = S[:, 0] - P[0], S[:, 1] - P[1]
        with np.errstate(divide='ignore', invalid='ignore'):
            t = (apx * sy - apy * sx) / den
            s = (apx * ry - apy * rx) / den
        ok = (np.abs(den) > 1e-9) & (t > 1e-6) & (t <= 1.0) & (s >= 0.0) & (s <= 1.0)
        if not ok.any():
            return None
        idx = np.where(ok)[0]
        k = idx[np.argmin(t[idx])]
        return float(t[k]), ids[k], float(s[k])

    def coast_t(self, P, Qp):
        """Fraction along P->Qp where the shoreline is crossed (None if all land)."""
        def is_land(q):
            return bool(self.model.land(q[0], q[1])) and abs(q[1]) < self.vmax and q[0] < self.umax
        if is_land(Qp):
            return None
        lo, hi = 0.0, 1.0
        for _ in range(14):
            mid = 0.5 * (lo + hi)
            if is_land((P[0] + mid * (Qp[0] - P[0]), P[1] + mid * (Qp[1] - P[1]))):
                lo = mid
            else:
                hi = mid
        return max(lo, 1e-3)

    # ----- events
    def avulse(self, w):
        p = self.p
        _, lobe_i, f = w.avul[0]
        rest = w.avul[1:]
        lb = self.lobes[lobe_i]
        node = self.add_node(w.pos, 'avulsion')
        self.finish(w, node)
        sgn = 1.0 if lb['theta'] >= 0 else -1.0
        defl = sgn * min(abs(lb['theta']), math.radians(50.0)) * float(self.rng.uniform(0.75, 1.0))
        tgt = (p.apex_u + 0.75 * lb['R'] * math.cos(lb['theta']), 0.75 * lb['R'] * math.sin(lb['theta']))
        g = _unit(tgt[0] - w.pos[0], tgt[1] - w.pos[1])
        ed = {w.edge}
        self.new_walker(node, w.pos, w.psi + defl, g, f * w.Q, 1, lobe_i, 'lobe', f, ed)
        cont_lobe = rest[0][1] if rest else self.youngest
        clb = self.lobes[cont_lobe]
        ctgt = (p.apex_u + 0.75 * clb['R'] * math.cos(clb['theta']), 0.75 * clb['R'] * math.sin(clb['theta']))
        cg = _unit(ctgt[0] - w.pos[0], ctgt[1] - w.pos[1])
        if rest:
            self.new_walker(node, w.pos, w.psi - defl * 0.15, (1.0, 0.0), (1 - f) * w.Q, 0,
                            -1, 'trunk', 1 - f, ed, avul=list(rest))
        else:
            self.new_walker(node, w.pos, w.psi - defl * 0.15, cg, (1 - f) * w.Q, 1,
                            self.youngest, 'lobe', 1 - f, ed)

    def bifurcate(self, w):
        p = self.p
        rng = self.rng
        node = self.add_node(w.pos, 'bifurcation')
        pe = w.edge
        self.finish(w, node)
        pmain = max(w.split_p, 1 - w.split_p)
        qmin = 1 - pmain
        rx, ry = self.repulsion(w, w.pos) if w.rep_on else (0.0, 0.0)
        perp = (-math.sin(w.psi), math.cos(w.psi))
        lat = rx * perp[0] + ry * perp[1]
        # the minor child goes to the side with more room (away from neighbours)
        side = 1.0 if lat > 0.05 else (-1.0 if lat < -0.05 else (1.0 if rng.random() < 0.5 else -1.0))
        a_major = math.radians(float(rng.uniform(*p.major_defl_deg)))
        a_minor = math.radians(float(rng.uniform(*p.minor_defl_deg)))
        for _ in range(8):
            ok_pen = turn_penalty((math.cos(0), math.sin(0)), (math.cos(a_minor), math.sin(a_minor)), 1.0)
            if np.isfinite(ok_pen) and rng.random() < math.exp(-ok_pen):
                break
            a_minor = math.radians(float(rng.uniform(*p.minor_defl_deg)))
        ps_major = w.psi - side * a_major
        ps_minor = w.psi + side * a_minor
        gmaj = w.goal
        gmin = _unit(0.5 * w.goal[0] + 0.5 * math.cos(ps_minor), 0.5 * w.goal[1] + 0.5 * math.sin(ps_minor))
        ed = {pe}
        a = self.new_walker(node, w.pos, ps_major, gmaj, pmain * w.Q, w.level + 1, w.lobe, 'distributary', pmain, ed)
        b = self.new_walker(node, w.pos, ps_minor, gmin, qmin * w.Q, w.level + 1, w.lobe, 'distributary', qmin, ed)
        a.zone_edges.add(b.edge)
        b.zone_edges.add(a.edge)

    def _merge_ok(self, w, step_dir, sid):
        s = self.segs[sid]
        seg_dir = (s[2] - s[0], s[3] - s[1])
        if not turn_allowed(step_dir, seg_dir, self.p.merge_max_deg):
            return False, seg_dir
        te = self.edges[self.seg_edge[sid]]
        if self.reaches(te['to'], w.n0):
            return False, seg_dir
        return True, seg_dir

    def merge(self, w, P, Qp, hit):
        t, sid, s = hit
        s = min(max(s, 0.03), 0.97)
        eid = self.seg_edge[sid]
        e = self.edges[eid]
        k = e['segs'].index(sid)
        nid, _ = self.split_edge(eid, k, s, 'confluence')
        m = self.node_pos[nid]
        self.extend_edge(w.edge, m)
        self.finish(w, nid)

    def mouth(self, w, P, Qp, tc):
        c = (P[0] + tc * (Qp[0] - P[0]), P[1] + tc * (Qp[1] - P[1]))
        self.extend_edge(w.edge, c)
        node = self.add_node(c, 'mouth')
        self.finish(w, node)

    def advance(self, w):
        p = self.p
        w.steps += 1
        if w.steps > p.max_steps:
            raise RuntimeError('walker exceeded max_steps (kind=%s level=%d pos=%s)' % (w.kind, w.level, w.pos))
        P = w.pos
        if w.avul and w.s_total >= w.avul[0][0]:
            self.avulse(w)
            return
        f = self.field.sample(P[0], P[1])
        D = float(f[0])
        if w.can_split and w.s_split >= w.next_split:
            q = min(w.split_p, 1 - w.split_p)
            if q * w.Q >= self.q_min_child and D > 2.5 * p.step_m:
                self.bifurcate(w)
                return
            if q * w.Q < self.q_min_child:
                w.can_split = False
            else:
                w.next_split = w.s_split + p.step_m
        # steering
        h = (math.cos(w.psi), math.sin(w.psi))
        perp = (-h[1], h[0])
        rho = math.exp(-p.step_m / p.noise_corr_m)
        w.xi = rho * w.xi + math.sqrt(1 - rho * rho) * float(self.rng.standard_normal())
        goal = w.goal
        c_goal = p.c_goal
        if w.target is not None:
            tx, ty = w.target[0] - P[0], w.target[1] - P[1]
            if tx * h[0] + ty * h[1] > 0 and math.hypot(tx, ty) > 1.5 * p.step_m:
                goal = _unit(tx, ty)
                c_goal = 3.0
        tn = math.hypot(f[1], f[2]) / 1.0e-4
        tscale = min(1.5, tn) / (tn + 1e-12) / 1.0e-4
        wc = 0.0 if w.kind == 'trunk' else p.c_coast * math.exp(-max(D, 0.0) / p.coast_pull_m)
        dx = c_goal * goal[0] + p.c_fwd * h[0] + p.c_terr * f[1] * tscale + wc * f[3] + p.noise_amp * w.xi * perp[0]
        dy = c_goal * goal[1] + p.c_fwd * h[1] + p.c_terr * f[2] * tscale + wc * f[4] + p.noise_amp * w.xi * perp[1]
        if w.rep_on:
            ramp = min(1.0, w.s_birth / (2.0 * p.zone_m))
            rx, ry = self.repulsion(w, P)
            dx += p.c_rep * ramp * rx
            dy += p.c_rep * ramp * ry
        max_t = math.radians(p.max_turn_deg)
        dpsi = _wrap(math.atan2(dy, dx) - w.psi)
        dpsi = max(-max_t, min(max_t, p.steer_gain * dpsi))
        psi0 = w.psi
        psi = max(-1.48, min(1.48, w.psi + dpsi))
        rot_step = math.radians(15.0)
        for attempt in range(3):
            Qp = (P[0] + p.step_m * math.cos(psi), P[1] + p.step_m * math.sin(psi))
            hit = self.first_hit(w, P, Qp)
            tc = self.coast_t(P, Qp)
            if hit is not None and (tc is None or hit[0] < tc):
                step_dir = (Qp[0] - P[0], Qp[1] - P[1])
                ok, seg_dir = self._merge_ok(w, step_dir, hit[1])
                if ok:
                    self.merge(w, P, Qp, hit)
                    return
                # rotate toward the foreign flow direction and retry
                diff = _wrap(math.atan2(seg_dir[1], seg_dir[0]) - psi)
                if abs(_wrap(psi - psi0)) + rot_step > math.radians(max_t * 0 + 45):
                    break
                psi = psi + math.copysign(min(rot_step, abs(diff)), diff)
                continue
            if tc is not None:
                self.mouth(w, P, Qp, tc)
                return
            self._move(w, Qp, psi)
            return
        # could not merge legally: stop short of the foreign segment
        t = hit[0] if hit is not None else 1.0
        Qs = (P[0] + 0.45 * t * (Qp[0] - P[0]), P[1] + 0.45 * t * (Qp[1] - P[1]))
        self._move(w, Qs, psi, length=0.45 * t * p.step_m)

    def _move(self, w, Qp, psi, length=None):
        L = length if length is not None else self.p.step_m
        self.extend_edge(w.edge, Qp)
        w.pos = (float(Qp[0]), float(Qp[1]))
        w.psi = psi
        w.s_total += L
        w.s_split += L
        w.s_birth += L

    def run(self):
        i = 0
        while True:
            alive = [w for w in self.walkers if not w.dead]
            if not alive:
                break
            for w in alive:
                if not w.dead:
                    self.advance(w)
            i += 1
            if i > 20000:
                raise RuntimeError('growth did not terminate')

    # ----- lateral links
    def link_pass(self):
        p, rng = self.p, self.rng
        if p.link_prob <= 0:
            return
        node_q, edge_q = self._flow_planned()
        donors = [i for i, e in enumerate(self.edges)
                  if e['kind'] in ('lobe', 'distributary') and edge_q[i] >= p.link_donor_q_min]
        for d in donors:
            if rng.random() > p.link_prob:
                continue
            Q = self._flow_planned()[1]
            e = self.edges[d]
            lam = float(rng.uniform(*p.link_frac))
            if lam * Q[d] < self.q_min_child or len(e['segs']) < 4:
                continue
            frac_pos = float(rng.uniform(0.3, 0.7))
            k = min(int(frac_pos * len(e['segs'])), len(e['segs']) - 1)
            sfrac = float(rng.uniform(0.2, 0.8))
            A, B = e['pts'][k], e['pts'][k + 1]
            pos = (A[0] + sfrac * (B[0] - A[0]), A[1] + sfrac * (B[1] - A[1]))
            hd = _unit(B[0] - A[0], B[1] - A[1])
            tgt = self._pick_target(d, pos, hd)
            if tgt is None:
                continue
            tpt, = tgt
            vec = _unit(tpt[0] - pos[0], tpt[1] - pos[1])
            ang = _wrap(math.atan2(vec[1], vec[0]) - math.atan2(hd[1], hd[0]))
            psi0 = math.atan2(hd[1], hd[0]) + math.copysign(min(abs(ang), math.radians(65.0)), ang)
            nid, e2 = self.split_edge(d, k, sfrac, 'link_start')
            self.edges[e2]['frac'] = 1 - lam
            w = self.new_walker(nid, pos, psi0, vec, lam * Q[d], min(e['level'] + 1, p.max_level),
                                e['lobe'], 'link', lam, {d, e2})
            w.target = tpt
            w.can_split = False
            w.s_birth = 0.0
        self.run()

    def _pick_target(self, donor, pos, hd):
        p = self.p
        S = np.array(self.segs)
        eids = np.array(self.seg_edge)
        mids = 0.5 * (S[:, :2] + S[:, 2:])
        dirs = S[:, 2:] - S[:, :2]
        dn = np.linalg.norm(dirs, axis=1) + 1e-12
        vec = mids - np.array(pos)
        d = np.linalg.norm(vec, axis=1) + 1e-12
        cosd = (vec @ np.array(hd)) / d
        cost = np.einsum('ij,ij->i', vec, dirs) / (d * dn)
        lo, hi = p.link_range_m
        ok = ((d > lo) & (d < hi) & (cosd < math.cos(math.radians(25))) & (cosd > math.cos(math.radians(75))) &
              (cost > math.cos(math.radians(65))) & (eids != donor))
        a = self.edges[donor]['frm']
        for i in np.argsort(np.where(ok, d, np.inf), kind='stable')[:6]:
            if not ok[i]:
                break
            te = self.edges[int(eids[i])]
            if te['kind'] == 'link' and False:
                continue
            if te['to'] is None or self.reaches(te['to'], a) or te['frm'] == a and False:
                continue
            return ((float(mids[i, 0]), float(mids[i, 1])),)
        return None

    # ----- flow
    def _flow_planned(self):
        N = len(self.node_pos)
        frm = np.array([e['frm'] for e in self.edges])
        to = np.array([e['to'] if e['to'] is not None else -1 for e in self.edges])
        frac = np.array([e['frac'] for e in self.edges], float)
        return solve_flow(N, frm, to, frac, self.p.q_total, 0)[:2]


def solve_flow(n_nodes, frm, to, frac, q_total, source):
    """Topological propagation. Out fractions of every node are renormalised to sum to 1."""
    frm, to = np.asarray(frm), np.asarray(to)
    E = len(frm)
    fr = np.asarray(frac, float).copy()
    osum = np.zeros(n_nodes)
    np.add.at(osum, frm, fr)
    fr = fr / osum[frm]
    indeg = np.zeros(n_nodes, int)
    valid = to >= 0
    np.add.at(indeg, to[valid], 1)
    out = [[] for _ in range(n_nodes)]
    for i in range(E):
        out[frm[i]].append(i)
    qn = np.zeros(n_nodes)
    qn[source] = q_total
    qe = np.zeros(E)
    stack = [n for n in range(n_nodes) if indeg[n] == 0]
    order = []
    deg = indeg.copy()
    while stack:
        stack.sort(reverse=True)
        n = stack.pop()
        order.append(n)
        for i in out[n]:
            qe[i] = fr[i] * qn[n]
            if to[i] >= 0:
                qn[to[i]] += qe[i]
                deg[to[i]] -= 1
                if deg[to[i]] == 0:
                    stack.append(int(to[i]))
    if len(order) != n_nodes:
        raise RuntimeError('network contains a cycle')
    return qn, qe, fr, order


# --------------------------------------------------------------------------- result
class DeltaGraph:
    pass


def build_delta_network(params: DeltaParams | None = None):
    p = params or DeltaParams()
    seeds = {k: derive_seed('delta-network/' + k, p.variant)
             for k in ('lobes', 'relief', 'growth')}
    rng_lobes = rng_for('delta-network/lobes', p.variant)
    lobes, harm, youngest = plan_lobes(p, rng_lobes)
    model = CoastModel(p, lobes, harm)
    field = _Field(p, model, rng_for('delta-network/relief', p.variant))
    rng = rng_for('delta-network/growth', p.variant)
    b = _Builder(p, model, field, lobes, youngest, rng)
    # trunk and avulsion schedule
    others = sorted([lb for lb in lobes if lb['id'] != youngest], key=lambda lb: (-abs(lb['theta']), lb['id']))
    shares = [lb['share'] for lb in others] + [lobes[youngest]['share']]
    avul = []
    s = p.avul_first_m * float(rng.uniform(0.8, 1.2))
    for i, lb in enumerate(others):
        f = shares[i] / sum(shares[i:])
        avul.append((s, lb['id'], f))
        s += p.avul_gap_m * float(rng.uniform(0.8, 1.3))
    src = b.add_node((p.apex_u, 0.0), 'source')
    b.new_walker(src, (p.apex_u, 0.0), 0.0, (1.0, 0.0), p.q_total, 0, -1, 'trunk', 1.0, avul=avul)
    b.run()
    b.link_pass()
    return _finalize(b, p, model, lobes, youngest, seeds)


def _finalize(b, p, model, lobes, youngest, seeds):
    g = DeltaGraph()
    g.params, g.model, g.lobes, g.youngest, g.seeds = p, model, lobes, youngest, seeds
    N, E = len(b.node_pos), len(b.edges)
    for e in b.edges:
        if e['to'] is None:
            raise RuntimeError('unfinished edge')
    g.node_uv = np.array(b.node_pos, float)
    g.node_kind = np.array([NODE_KINDS.index(k) for k in b.node_kind], np.int8)
    g.edge_from = np.array([e['frm'] for e in b.edges], np.int64)
    g.edge_to = np.array([e['to'] for e in b.edges], np.int64)
    frac = np.array([e['frac'] for e in b.edges], float)
    qn, qe, fr, order = solve_flow(N, g.edge_from, g.edge_to, frac, p.q_total, 0)
    g.node_q, g.edge_q, g.edge_frac, g.topo = qn, qe, fr, np.array(order)
    g.edge_w = width_of(qe, p)
    g.edge_h = depth_of(qe, p)
    g.edge_level = np.array([e['level'] for e in b.edges], np.int16)
    g.edge_lobe = np.array([e['lobe'] for e in b.edges], np.int16)
    g.edge_kind = np.array([EDGE_KINDS.index(e['kind']) for e in b.edges], np.int8)
    off = [0]
    pts = []
    for e in b.edges:
        pts.extend(e['pts'])
        off.append(len(pts))
    g.pt_off = np.array(off, np.int64)
    g.pts_uv = np.array(pts, float)
    g.edge_len = np.array([float(np.sum(np.hypot(*np.diff(np.array(e['pts']), axis=0).T))) for e in b.edges])
    g.mouth_nodes = np.where(g.node_kind == NODE_KINDS.index('mouth'))[0]
    return g


def edge_points(g, i):
    return g.pts_uv[g.pt_off[i]:g.pt_off[i + 1]]


# --------------------------------------------------------------------------- validation / metrics
def _ang(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b) / (na * nb)))))


def validate_graph(g):
    """Hard-acceptance checks; returns a dict (``ok`` is True when all pass)."""
    N, E = len(g.node_uv), len(g.edge_from)
    rep = {}
    inflow = np.zeros(N)
    outflow = np.zeros(N)
    np.add.at(inflow, g.edge_to, g.edge_q)
    np.add.at(outflow, g.edge_from, g.edge_q)
    src = np.zeros(N)
    src[0] = g.params.q_total
    err = np.abs(inflow + src - outflow)
    err[g.mouth_nodes] = np.abs(inflow[g.mouth_nodes] - g.node_q[g.mouth_nodes])
    rep['max_node_conservation_error'] = float(err.max())
    rep['mouth_total_error'] = float(abs(g.node_q[g.mouth_nodes].sum() - g.params.q_total))
    # every edge reaches the sea (reverse BFS from mouths)
    rev = [[] for _ in range(N)]
    for i in range(E):
        rev[g.edge_to[i]].append(g.edge_from[i])
    seen = set(map(int, g.mouth_nodes))
    stack = list(seen)
    while stack:
        n = stack.pop()
        for m in rev[n]:
            if int(m) not in seen:
                seen.add(int(m))
                stack.append(int(m))
    rep['edges_without_path_to_sea'] = int(sum(1 for i in range(E) if int(g.edge_from[i]) not in seen))
    # turns
    max_turn = 0.0
    n_ge90 = 0
    n_disallowed = 0
    n_gt45 = 0
    first_dir, last_dir = [], []
    for i in range(E):
        P = edge_points(g, i)
        d = np.diff(P, axis=0)
        first_dir.append(d[0])
        last_dir.append(d[-1])
        for k in range(len(d) - 1):
            a = _ang(d[k], d[k + 1])
            max_turn = max(max_turn, a)
            n_gt45 += a > 45
            n_ge90 += a >= 90 - 1e-9
            n_disallowed += not turn_allowed(d[k], d[k + 1], 90.0)
    ins = [[] for _ in range(N)]
    outs = [[] for _ in range(N)]
    for i in range(E):
        ins[g.edge_to[i]].append(i)
        outs[g.edge_from[i]].append(i)
    for n in range(N):
        for i in ins[n]:
            for j in outs[n]:
                a = _ang(last_dir[i], first_dir[j])
                max_turn = max(max_turn, a)
                n_gt45 += a > 45
                n_ge90 += a >= 90 - 1e-9
                n_disallowed += not turn_allowed(last_dir[i], first_dir[j], 90.0)
    rep['max_turn_deg'] = float(max_turn)
    rep['turns_ge_90deg'] = int(n_ge90)
    rep['turns_not_allowed'] = int(n_disallowed)
    rep['turns_gt_45deg'] = int(n_gt45)
    rep['nan_count'] = int(np.isnan(g.pts_uv).sum() + np.isnan(g.edge_q).sum() + np.isnan(g.edge_w).sum())
    rep['dag'] = True
    rep['dead_end_nodes'] = int(sum(1 for n in range(N) if not outs[n] and n not in set(map(int, g.mouth_nodes))))
    rep['ok'] = bool(rep['max_node_conservation_error'] <= 1e-9 and rep['edges_without_path_to_sea'] == 0 and
                     rep['turns_ge_90deg'] == 0 and rep['turns_not_allowed'] == 0 and rep['nan_count'] == 0 and
                     rep['dead_end_nodes'] == 0)
    return rep


def skeleton_metrics(g):
    p = g.params
    N, E = len(g.node_uv), len(g.edge_from)
    # undirected components
    parent = list(range(N))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in zip(g.edge_from, g.edge_to):
        parent[find(int(a))] = find(int(b))
    comps = len({find(i) for i in range(N)})
    kinds = {NODE_KINDS[k]: int((g.node_kind == k).sum()) for k in range(len(NODE_KINDS))}
    levels = {int(l): int((g.edge_level == l).sum()) for l in np.unique(g.edge_level)}
    # bifurcation angles between sibling first segments
    angs = []
    outs = {}
    for i in range(E):
        outs.setdefault(int(g.edge_from[i]), []).append(i)
    for n, lst in outs.items():
        if len(lst) == 2:
            d0 = np.diff(edge_points(g, lst[0]), axis=0)[0]
            d1 = np.diff(edge_points(g, lst[1]), axis=0)[0]
            angs.append(_ang(d0, d1))
    # width-Q exponent from exported arrays
    m = g.edge_q > 0
    b_fit = float(np.polyfit(np.log(g.edge_q[m]), np.log(g.edge_w[m]), 1)[0])
    phi = np.linspace(-1.2, 1.2, 4801)
    R = g.model.radius(phi)
    ur = p.apex_u + R * np.cos(phi)
    vr = R * np.sin(phi)
    front = ur > p.base_coast_u + 3000.0
    width = float(vr[front].max() - vr[front].min()) if front.any() else 0.0
    return dict(
        n_nodes=N, n_edges=E, node_kinds=kinds, n_mouths=int(len(g.mouth_nodes)),
        edge_levels=levels, max_level=int(g.edge_level.max()), loops=int(E - N + comps), components=int(comps),
        bifurcation_angle_deg=dict(n=len(angs), mean=float(np.mean(angs)) if angs else 0.0,
                                   p10=float(np.percentile(angs, 10)) if angs else 0.0,
                                   p90=float(np.percentile(angs, 90)) if angs else 0.0),
        width_exponent_fit=b_fit, total_channel_length_km=float(g.edge_len.sum() / 1000.0),
        mouth_q_share=[float(x) for x in np.sort(g.node_q[g.mouth_nodes])[::-1][:12]],
        farthest_coast_from_apex_m=float(np.max(R)),
        model_front_width_m=width,
        lobes=[dict(id=l['id'], rank=l['rank'], theta_deg=math.degrees(l['theta']), R_m=l['R'], share=l['share'])
               for l in g.lobes])


# --------------------------------------------------------------------------- export
def export_graph(g, outdir, spec=None):
    """Write the channel graph (npz + json) in local and, when ``spec`` is given, world coordinates."""
    from terrain_pipeline.delta_network_site import local_to_world
    os.makedirs(outdir, exist_ok=True)
    arrays = dict(node_uv=g.node_uv, node_kind=g.node_kind, node_q=g.node_q,
                  edge_from=g.edge_from, edge_to=g.edge_to, edge_q=g.edge_q, edge_w=g.edge_w, edge_h=g.edge_h,
                  edge_level=g.edge_level, edge_lobe=g.edge_lobe, edge_kind=g.edge_kind, edge_frac=g.edge_frac,
                  edge_len=g.edge_len, pt_off=g.pt_off, pts_uv=g.pts_uv)
    if spec is not None:
        X, Z = local_to_world(spec, g.node_uv[:, 0], g.node_uv[:, 1])
        arrays['node_xz'] = np.stack([X, Z], axis=1)
        X, Z = local_to_world(spec, g.pts_uv[:, 0], g.pts_uv[:, 1])
        arrays['pts_xz'] = np.stack([X, Z], axis=1)
    np.savez(os.path.join(outdir, 'channel_graph.npz'), **arrays)
    meta = dict(node_kinds=NODE_KINDS, edge_kinds=EDGE_KINDS, lobes=g.lobes, youngest_lobe=g.youngest,
                params=g.params.to_dict(), seeds={k: str(v) for k, v in g.seeds.items()})
    with open(os.path.join(outdir, 'channel_graph_meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return arrays
