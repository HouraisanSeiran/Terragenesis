"""Channel skeleton for the complex delta network v2 (rework of v1).

What changed against ``delta_network_skeleton`` (v1)
----------------------------------------------------
* No level cap.  Bifurcations happen along the *whole* length of every channel
  with probability ~ 1/(beta*w) per unit length (mouth-bar spacing L_b = beta*w),
  boosted towards the front.  A bifurcation is only allowed when the free lateral
  gap beside the channel is larger than ``split_gap_factor`` x the target
  spacing at that position; the target spacing shrinks from ``spacing_plain_m``
  (reticulate plain section) to ``spacing_front_m`` (front).
* Crowding is resolved by merging: when a neighbour is closer than
  ``merge_frac`` x target spacing, the smaller channel is attracted to it and
  joins it (confluence, in-degree > 1) - no channel is simply terminated for
  being narrow; children below 1.5 cells are just never created.
* The analytic lobe outline of v1 is only an *upper bound guide* here: every
  channel gets its own reach (``end_frac`` x guide radius) and ends in a mouth
  there.  The shoreline itself is built from the channels in the terrain module.
* Flow is re-evaluated from the planned graph every few sweeps so that widths
  used for bifurcation spacing include discharge gained by confluences.

Local metric frame: u seaward, v along shore (see ``delta_network_site``).
Turn rule: step turns <= ``max_turn_deg`` (<=45 deg, no penalty), junction
angles checked with ``river_path_geometry.turn_allowed`` (< 90 deg).
Hydraulic geometry: w = a*Q^b, h = c*Q^f (exponents Leopold & Maddock 1953;
coefficients are declared scenario values).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from terrain_pipeline.delta_network_site import derive_seed, rng_for
from terrain_pipeline.delta_network_skeleton import (
    EDGE_KINDS, NODE_KINDS, WINDOW_U, WINDOW_V, CoastModel, DeltaGraph, DeltaParams, _Field, _ang,
    _unit, _wrap, depth_of, edge_points, plan_lobes, skeleton_metrics, solve_flow, validate_graph,
    width_of)
from terrain_pipeline.channel_geometry import turn_allowed, turn_penalty

__all__ = ['DeltaParamsV3', 'build_delta_network_v3', 'validate_graph', 'edge_points', 'NODE_KINDS',
           'EDGE_KINDS', 'width_of', 'depth_of', 'skeleton_metrics_v3', 'activity_profile',
           'event_profile', 'solve_flow']


@dataclass(frozen=True)
class DeltaParamsV3(DeltaParams):
    variant: str = 'v3'
    algorithm_world_seed: int = 20261020
    # Finite planning support; default preserves the historical 48 km case.
    window_u_m: tuple = WINDOW_U
    window_v_m: tuple = WINDOW_V
    boundary_margin_m: float = 500.0
    # hydraulic geometry: trunk ~450 m wide, 50-300 m distributaries (declared)
    width_a: float = 6.5
    depth_c: float = 0.3
    beta: float = 6.0                  # L_b = beta*w (memory: Edmonds & Slingerland 2007)
    # steering
    c_goal: float = 1.1
    c_coast: float = 0.3
    noise_amp: float = 0.7
    zone_m: float = 1200.0
    max_steps: int = 3000
    link_prob: float = 0.9
    link_donor_q_min: float = 600.0
    # lobes (v2 overrides of v1 defaults: wider fan, longer reach)
    r_young: float = 49000.0
    r_decay: float = 0.88
    spread_deg: float = 60.0
    max_lateral_m: float = 21500.0
    sigma_young_deg: float = 40.0
    sigma_old_deg: float = 36.0
    # v2: spacing control / activity
    spacing_plain_m: float = 2200.0
    spacing_front_m: float = 600.0
    front_f0: float = 0.30
    front_f1: float = 0.85
    split_gap_factor: float = 1.4
    merge_frac: float = 0.5
    merge_min_len_factor: float = 2.0
    c_attr: float = 1.6
    rep_factor: float = 0.7
    front_boost: float = 2.0
    min_remaining_split_m: float = 900.0
    min_split_len_factor: float = 0.5
    end_frac_young: tuple = (0.92, 1.05)
    end_frac_old: tuple = (0.85, 1.0)
    refresh_every: int = 6
    lobe_room_sigma: float = 1.6
    # ---- v3: meanders, soft form limits (old PlanConfig numbers rescaled to local width), oblique links
    meander_lambda_k: float = 12.0        # wavelength = k*w (10-14 w; recalled, not re-verified)
    meander_lambda_min_m: float = 1100.0
    c_mea: float = 0.55                   # lateral steering amplitude of the meander (~16 deg heading swing)
    fan_half_deg: float = 65.0            # old PlanConfig.fan_half_angle_deg, now vs. the apex-radial direction
    detour_max: float = 1.6               # old max_detour_ratio, applied per walker (path/chord)
    detour_min_chord_m: float = 1500.0
    link_spacing_k: float = 10.0          # mean link spacing along a donor = k*w_donor
    link_len_k: float = 12.0              # median link length = k*w_donor
    link_len_sigma: float = 0.45          # lognormal sigma of link length
    link_len_min_m: float = 900.0
    link_len_max_m: float = 6500.0
    link_ang_deg: tuple = (20.0, 60.0)    # angle donor tangent -> link direction
    link_junc_deg: tuple = (20.0, 60.0)   # junction angle link -> target channel
    link_gap_k: float = 4.0               # min distance between link starts = k*w_donor
    link_forward_frac: float = 0.15       # link must advance seaward by >= frac*length
    forward_deg: float = 70.0             # max heading offset from the apex-radial direction
    link_slots_jitter: tuple = (0.6, 1.6)


class _Walker:
    __slots__ = ('pos', 'psi', 'goal', 'Q', 'level', 'lobe', 'kind', 'edge', 'n0', 'own',
                 'zone_edges', 'zone_pt', 's_total', 's_split', 's_birth', 'split_p', 'xi',
                 'steps', 'dead', 'avul', 'can_split', 'target', 'rep_on', 'end_frac', 'mph', 'bpos')


class _Builder:
    def __init__(self, p, model, field, lobes, youngest, rng, shore_test=None):
        self.p, self.model, self.field, self.lobes, self.rng = p, model, field, lobes, rng
        self.shore_test = shore_test
        self.youngest = youngest
        self.node_pos, self.node_kind = [], []
        self.edges = []
        self.segs, self.seg_edge = [], []
        self.cap = 4096
        self.S = np.zeros((self.cap, 4))
        self.M = np.zeros((self.cap, 2))
        self.SE = np.zeros(self.cap, np.int64)
        self.nseg = 0
        self.walkers, self.open = [], {}
        self.q_min_child = (p.min_child_cells * p.cell_m / p.width_a) ** (1.0 / p.width_b)
        self.umax = p.window_u_m[1] - p.boundary_margin_m
        self.vmin = p.window_v_m[0] + p.boundary_margin_m
        self.vmax = p.window_v_m[1] - p.boundary_margin_m
        self.n_stall = 0

    # ------------------------------------------------------------ segment storage
    def _add_seg(self, seg, eid):
        if self.nseg >= self.cap:
            self.cap *= 2
            for name in ('S', 'M'):
                a = getattr(self, name)
                b = np.zeros((self.cap,) + a.shape[1:])
                b[:len(a)] = a
                setattr(self, name, b)
            b = np.zeros(self.cap, np.int64)
            b[:len(self.SE)] = self.SE
            self.SE = b
        i = self.nseg
        self.segs.append(seg)
        self.seg_edge.append(eid)
        self.S[i] = seg
        self.M[i] = (0.5 * (seg[0] + seg[2]), 0.5 * (seg[1] + seg[3]))
        self.SE[i] = eid
        self.nseg += 1
        return i

    def _set_seg(self, sid, seg):
        self.segs[sid] = seg
        self.S[sid] = seg
        self.M[sid] = (0.5 * (seg[0] + seg[2]), 0.5 * (seg[1] + seg[3]))

    def _set_seg_edge(self, sid, eid):
        self.seg_edge[sid] = eid
        self.SE[sid] = eid

    # ------------------------------------------------------------ graph primitives
    def add_node(self, pos, kind):
        self.node_pos.append((float(pos[0]), float(pos[1])))
        self.node_kind.append(kind)
        return len(self.node_pos) - 1

    def new_edge(self, frm, pos, kind, level, lobe, frac, q):
        self.edges.append(dict(frm=frm, to=None, pts=[(float(pos[0]), float(pos[1]))], segs=[],
                               kind=kind, level=level, lobe=lobe, frac=frac, q=float(q)))
        return len(self.edges) - 1

    def extend_edge(self, eid, pt):
        e = self.edges[eid]
        a = e['pts'][-1]
        pt = (float(pt[0]), float(pt[1]))
        sid = self._add_seg((a[0], a[1], pt[0], pt[1]), eid)
        e['segs'].append(sid)
        e['pts'].append(pt)

    def split_edge(self, eid, k, s, kind):
        e = self.edges[eid]
        A, B = e['pts'][k], e['pts'][k + 1]
        m = (A[0] + s * (B[0] - A[0]), A[1] + s * (B[1] - A[1]))
        nid = self.add_node(m, kind)
        e2id = len(self.edges)
        e2 = dict(frm=nid, to=e['to'], pts=[m] + e['pts'][k + 1:], segs=[],
                  kind=e['kind'], level=e['level'], lobe=e['lobe'], frac=1.0, q=e['q'])
        self._set_seg(e['segs'][k], (A[0], A[1], m[0], m[1]))
        new_sid = self._add_seg((m[0], m[1], B[0], B[1]), e2id)
        e2['segs'] = [new_sid] + e['segs'][k + 1:]
        e['pts'] = e['pts'][:k + 1] + [m]
        e['segs'] = e['segs'][:k + 1]
        e['to'] = nid
        self.edges.append(e2)
        for sid in e2['segs']:
            self._set_seg_edge(sid, e2id)
        if eid in self.open:
            w = self.open.pop(eid)
            w.own.add(eid)
            w.edge = e2id
            self.open[e2id] = w
        return nid, e2id

    def reaches(self, start, goal):
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

    # ------------------------------------------------------------ walkers
    def new_walker(self, node, pos, psi, goal, Q, level, lobe, kind, frac, parent_edges=(), avul=None,
                   end_frac=1.0):
        p = self.p
        w = _Walker()
        ekind = 'trunk' if kind == 'trunk' else ('link' if kind == 'link' else ('lobe' if level <= 1 else 'distributary'))
        w.edge = self.new_edge(node, pos, ekind, level, lobe, frac, Q)
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
        w.can_split = kind in ('lobe', 'distributary')
        w.rep_on = kind not in ('trunk', 'link')
        w.split_p = float(self.rng.uniform(p.asym_lo, p.asym_hi))
        w.end_frac = float(end_frac)
        w.mph = float(self.rng.uniform(0.0, 2.0 * math.pi))
        w.bpos = w.pos
        self.walkers.append(w)
        self.open[w.edge] = w
        return w

    def finish(self, w, node):
        self.edges[w.edge]['to'] = node
        self.open.pop(w.edge, None)
        w.dead = True

    def _end_frac_for(self, lobe_id):
        p = self.p
        lo, hi = p.end_frac_young if self.lobes[lobe_id]['rank'] == 0 else p.end_frac_old
        return float(self.rng.uniform(lo, hi))

    # ------------------------------------------------------------ geometry queries
    def _filter(self, w, idx):
        """Boolean keep-mask over segment ids ``idx`` (drops own/zone segments)."""
        eids = self.SE[idx]
        keep = eids != w.edge
        if w.own:
            keep &= ~np.isin(eids, np.fromiter(w.own, np.int64))
        if w.zone_edges and w.s_birth < 4.0 * self.p.zone_m:
            zm = np.isin(eids, np.fromiter(w.zone_edges, np.int64))
            if zm.any():
                zx = self.M[idx, 0] - w.zone_pt[0]
                zy = self.M[idx, 1] - w.zone_pt[1]
                zm &= (zx * zx + zy * zy) < self.p.zone_m ** 2
                keep &= ~zm
        return keep

    def _scan(self, w, P, h, radius):
        n = self.nseg
        if n == 0:
            return None
        M = self.M[:n]
        dx = M[:, 0] - P[0]
        dy = M[:, 1] - P[1]
        d2 = dx * dx + dy * dy
        idx = np.nonzero(d2 < radius * radius)[0]
        if idx.size == 0:
            return None
        idx = idx[self._filter(w, idx)]
        if idx.size == 0:
            return None
        rx, ry = dx[idx], dy[idx]
        return dict(idx=idx, eid=self.SE[idx], rx=rx, ry=ry, along=rx * h[0] + ry * h[1],
                    lat=-rx * h[1] + ry * h[0], d=np.sqrt(d2[idx]))

    def first_hit(self, w, P, Qp):
        n = self.nseg
        if n == 0:
            return None
        M = self.M[:n]
        pad = 400.0
        x0, x1 = min(P[0], Qp[0]) - pad, max(P[0], Qp[0]) + pad
        y0, y1 = min(P[1], Qp[1]) - pad, max(P[1], Qp[1]) + pad
        idx = np.nonzero((M[:, 0] > x0) & (M[:, 0] < x1) & (M[:, 1] > y0) & (M[:, 1] < y1))[0]
        if idx.size == 0:
            return None
        idx = idx[self._filter(w, idx)]
        if idx.size == 0:
            return None
        S = self.S[idx]
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
        j = np.where(ok)[0]
        k = j[np.argmin(t[j])]
        return float(t[k]), int(idx[k]), float(s[k])

    def _out(self, q, w):
        if q[1] <= self.vmin or q[1] >= self.vmax or q[0] >= self.umax:
            return True
        if w.kind == 'trunk':
            return False
        du = q[0] - self.p.apex_u
        r = math.hypot(du, q[1])
        if r < 3000.0:
            return False
        if self.shore_test is not None:
            return bool(self.shore_test(float(q[0]), float(q[1])))
        return r >= float(self.model.radius(math.atan2(q[1], du))) * w.end_frac

    def reach_t(self, P, Qp, w):
        if not self._out(Qp, w):
            return None
        lo, hi = 0.0, 1.0
        for _ in range(14):
            mid = 0.5 * (lo + hi)
            if self._out((P[0] + mid * (Qp[0] - P[0]), P[1] + mid * (Qp[1] - P[1])), w):
                hi = mid
            else:
                lo = mid
        return max(hi, 1e-3)

    def spacing(self, fr):
        p = self.p
        t = min(max((fr - p.front_f0) / (p.front_f1 - p.front_f0), 0.0), 1.0)
        s = t * t * (3 - 2 * t)
        return p.spacing_plain_m + (p.spacing_front_m - p.spacing_plain_m) * s

    # ------------------------------------------------------------ events
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
        self.new_walker(node, w.pos, w.psi + defl, g, f * w.Q, 1, lobe_i, 'lobe', f, ed,
                        end_frac=self._end_frac_for(lobe_i))
        cont_lobe = rest[0][1] if rest else self.youngest
        clb = self.lobes[cont_lobe]
        ctgt = (p.apex_u + 0.75 * clb['R'] * math.cos(clb['theta']), 0.75 * clb['R'] * math.sin(clb['theta']))
        cg = _unit(ctgt[0] - w.pos[0], ctgt[1] - w.pos[1])
        if rest:
            self.new_walker(node, w.pos, w.psi - defl * 0.15, (1.0, 0.0), (1 - f) * w.Q, 0,
                            -1, 'trunk', 1 - f, ed, avul=list(rest))
        else:
            self.new_walker(node, w.pos, w.psi - defl * 0.15, cg, (1 - f) * w.Q, 1,
                            self.youngest, 'lobe', 1 - f, ed, end_frac=self._end_frac_for(self.youngest))

    def bifurcate(self, w, side):
        p = self.p
        rng = self.rng
        node = self.add_node(w.pos, 'bifurcation')
        pe = w.edge
        self.finish(w, node)
        pmain = max(w.split_p, 1 - w.split_p)
        qmin = 1 - pmain
        a_major = math.radians(float(rng.uniform(*p.major_defl_deg)))
        a_minor = math.radians(float(rng.uniform(*p.minor_defl_deg)))
        for _ in range(8):
            ok_pen = turn_penalty((1.0, 0.0), (math.cos(a_minor), math.sin(a_minor)), 1.0)
            if np.isfinite(ok_pen) and rng.random() < math.exp(-ok_pen):
                break
            a_minor = math.radians(float(rng.uniform(*p.minor_defl_deg)))
        ps_major = w.psi - side * a_major
        ps_minor = w.psi + side * a_minor
        ed = {pe}
        ef_major = min(1.0, max(0.55, w.end_frac * float(rng.uniform(0.94, 1.04))))
        ef_minor = min(1.0, max(0.55, w.end_frac * float(rng.uniform(0.85, 1.05))))
        a = self.new_walker(node, w.pos, ps_major, w.goal, pmain * w.Q, w.level + 1, w.lobe, 'distributary',
                            pmain, ed, end_frac=ef_major)
        b = self.new_walker(node, w.pos, ps_minor, w.goal, qmin * w.Q, w.level + 1, w.lobe, 'distributary',
                            qmin, ed, end_frac=ef_minor)
        a.zone_edges.add(b.edge)
        b.zone_edges.add(a.edge)

    def _merge_ok(self, w, step_dir, sid, P=None, sh=None):
        s = self.segs[sid]
        seg_dir = (s[2] - s[0], s[3] - s[1])
        if P is not None and sh is not None:
            # v3: the (clamped) junction point must lie ahead of the walker, never behind it
            sc = min(max(sh, 0.03), 0.97)
            jx, jy = s[0] + sc * seg_dir[0] - P[0], s[1] + sc * seg_dir[1] - P[1]
            jn = math.hypot(jx, jy)
            sn = math.hypot(step_dir[0], step_dir[1])
            # the final piece P->junction must be a real segment pointing along the step (<= 60 deg)
            if jn < 25.0 or (jx * step_dir[0] + jy * step_dir[1]) < 0.5 * jn * sn:
                return False, seg_dir
        if not turn_allowed(step_dir, seg_dir, self.p.merge_max_deg):
            return False, seg_dir
        te = self.edges[self.seg_edge[sid]]
        frm = self.edges[w.edge]['frm']
        if self.reaches(te['to'], frm) or te['frm'] == frm and te['to'] is None:
            return False, seg_dir
        return True, seg_dir

    def merge(self, w, P, Qp, hit):
        t, sid, s = hit
        s = min(max(s, 0.03), 0.97)
        eid = self.seg_edge[sid]
        e = self.edges[eid]
        k = e['segs'].index(sid)
        nid, _ = self.split_edge(eid, k, s, 'confluence')
        self.extend_edge(w.edge, self.node_pos[nid])
        self.finish(w, nid)

    def mouth(self, w, P, Qp, tc):
        c = (P[0] + tc * (Qp[0] - P[0]), P[1] + tc * (Qp[1] - P[1]))
        self.extend_edge(w.edge, c)
        node = self.add_node(c, 'mouth')
        self.finish(w, node)

    # ------------------------------------------------------------ one step of one walker
    def advance(self, w):
        p = self.p
        rng = self.rng
        w.steps += 1
        if w.steps > p.max_steps:
            raise RuntimeError('walker exceeded max_steps (kind=%s level=%d pos=%s)' % (w.kind, w.level, w.pos))
        P = w.pos
        if w.avul and w.s_total >= w.avul[0][0]:
            self.avulse(w)
            return
        f = self.field.sample(P[0], P[1])
        D = float(f[0])
        du = P[0] - p.apex_u
        r = math.hypot(du, P[1])
        phi = math.atan2(P[1], du)
        h = (math.cos(w.psi), math.sin(w.psi))
        perp = (-h[1], h[0])
        if w.kind == 'trunk':
            fr, st, rend = 0.0, p.spacing_plain_m, 1e9
        else:
            rend = float(self.model.radius(phi)) * w.end_frac
            fr = min(max(r / max(rend, 1.0), 0.0), 1.0)
            st = self.spacing(fr)
        cap = 2.2 * st
        sc = None
        gl = gr = cap
        if w.kind in ('lobe', 'distributary'):
            sc = self._scan(w, P, h, max(cap, 1.0))
            if sc is not None:
                m = (sc['along'] > -0.4 * cap) & (sc['along'] < 0.8 * cap)
                if m.any():
                    lat = sc['lat'][m]
                    if (lat > 0).any():
                        gl = min(cap, float(lat[lat > 0].min()))
                    if (lat < 0).any():
                        gr = min(cap, float(-lat[lat < 0].max()))
            if w.lobe >= 0:
                lb = self.lobes[w.lobe]
                dphi = _wrap(phi - lb['theta'])
                lim = p.lobe_room_sigma * lb['sigma']
                if dphi > lim:
                    gl = 0.0
                elif dphi < -lim:
                    gr = 0.0
        # ---- bifurcation along the whole length
        if w.can_split and w.s_split >= p.min_split_len_factor * p.beta * float(width_of(w.Q, p)):
            wd = float(width_of(w.Q, p))
            prob = min(1.0, p.step_m / (p.beta * wd)) * (1.0 + p.front_boost * fr)
            if rng.random() < prob and rend - r > p.min_remaining_split_m:
                q = min(w.split_p, 1 - w.split_p)
                if q * w.Q >= self.q_min_child and max(gl, gr) >= p.split_gap_factor * st:
                    if gl > gr:
                        side = 1.0
                    elif gr > gl:
                        side = -1.0
                    else:
                        side = 1.0 if rng.random() < 0.5 else -1.0
                    self.bifurcate(w, side)
                    return
        # ---- steering
        rho = math.exp(-p.step_m / p.noise_corr_m)
        w.xi = rho * w.xi + math.sqrt(1 - rho * rho) * float(rng.standard_normal())
        goal = w.goal
        c_goal = p.c_goal
        if w.kind in ('lobe', 'distributary') and r > 1.0:
            lb = self.lobes[w.lobe] if w.lobe >= 0 else None
            rot = 0.0
            if lb is not None:
                dphi = _wrap(phi - lb['theta'])
                rot = -math.copysign(min(0.5 * max(abs(dphi) / lb['sigma'] - 1.0, 0.0) * 1.5, 0.7), dphi)
            ca, sa = math.cos(rot), math.sin(rot)
            ux, uy = du / r, P[1] / r
            goal = (ux * ca - uy * sa, ux * sa + uy * ca)
        if w.target is not None:
            tx, ty = w.target[0] - P[0], w.target[1] - P[1]
            if tx * h[0] + ty * h[1] > 0 and math.hypot(tx, ty) > 1.5 * p.step_m:
                goal = _unit(tx, ty)
                c_goal = 3.0
        # v3 soft form limits (old PlanConfig.max_detour_ratio, rescaled): path/chord since birth
        if w.kind in ('lobe', 'distributary') and w.s_birth > p.detour_min_chord_m:
            chord = math.hypot(P[0] - w.bpos[0], P[1] - w.bpos[1])
            ratio = w.s_birth / max(chord, 1.0)
            if ratio > p.detour_max:
                c_goal *= 1.0 + 2.0 * min(3.0, ratio / p.detour_max - 1.0)
        tn = math.hypot(f[1], f[2]) / 1.0e-4
        tscale = min(1.5, tn) / (tn + 1e-12) / 1.0e-4
        wc = 0.0 if w.kind == 'trunk' else p.c_coast * math.exp(-max(D, 0.0) / p.coast_pull_m)
        dx = c_goal * goal[0] + p.c_fwd * h[0] + p.c_terr * f[1] * tscale + wc * f[3] + p.noise_amp * w.xi * perp[0]
        dy = c_goal * goal[1] + p.c_fwd * h[1] + p.c_terr * f[2] * tscale + wc * f[4] + p.noise_amp * w.xi * perp[1]
        if w.kind != 'link':
            # meander: lateral steering with wavelength = k*w (k ~ 10-14, recalled value)
            lam_m = max(p.meander_lambda_min_m, p.meander_lambda_k * float(width_of(w.Q, p)))
            mea = p.c_mea * math.sin(2.0 * math.pi * w.s_total / lam_m + w.mph)
            dx += mea * perp[0]
            dy += mea * perp[1]
        if w.kind != 'trunk' and r > 3000.0:
            # fan half angle (old fan_half_angle_deg), soft: pull back towards the axis
            over = abs(phi) - math.radians(p.fan_half_deg)
            if over > 0:
                dy -= math.copysign(c_goal * min(2.0, over / math.radians(10.0)), P[1])
        if w.rep_on and sc is not None:
            ax = ay = 0.0
            attracted = False
            if w.s_birth > p.merge_min_len_factor * st:
                gmin = min(gl, gr)
                if gmin < p.merge_frac * st:
                    cand = np.nonzero((np.abs(sc['lat']) < p.merge_frac * st) & (sc['along'] > 0) &
                                      (sc['along'] < 1.5 * st + 600.0))[0]
                    cand = cand[np.argsort(sc['d'][cand], kind='stable')]
                    for k in cand[:6]:
                        eid = int(sc['eid'][k])
                        qn = self.edges[eid]['q']
                        if qn > w.Q * 0.9 or (abs(qn - w.Q) <= 0.1 * w.Q and eid < w.edge):
                            ux, uy = _unit(float(sc['rx'][k]), float(sc['ry'][k]))
                            ax, ay = ux, uy
                            attracted = True
                            break
            if attracted:
                dx += p.c_attr * ax
                dy += p.c_attr * ay
            else:
                R = max(p.rep_factor * st, 300.0)
                d = sc['d']
                sel = (d > 1e-6) & (d < R)
                if sel.any():
                    k = (1 - d[sel] / R) ** 2 / d[sel]
                    rx = float(-(sc['rx'][sel] * k).sum())
                    ry = float(-(sc['ry'][sel] * k).sum())
                    n = math.hypot(rx, ry)
                    if n > 2.0:
                        rx, ry = rx * 2.0 / n, ry * 2.0 / n
                    ramp = min(1.0, w.s_birth / (2.0 * p.zone_m))
                    dx += p.c_rep * ramp * rx
                    dy += p.c_rep * ramp * ry
        max_t = math.radians(p.max_turn_deg)
        dpsi = _wrap(math.atan2(dy, dx) - w.psi)
        dpsi = max(-max_t, min(max_t, p.steer_gain * dpsi))
        psi0 = w.psi
        psi = max(-1.48, min(1.48, w.psi + dpsi))
        if w.kind in ('lobe', 'distributary') and r > 3000.0:
            # every step keeps a seaward component (old min_forward_m): heading within +-fwd of the radial
            fw = math.radians(p.forward_deg)
            psi = phi + max(-fw, min(fw, _wrap(psi - phi)))
        rot_step = math.radians(15.0)
        hit = None
        Qp = P
        for attempt in range(3):
            Qp = (P[0] + p.step_m * math.cos(psi), P[1] + p.step_m * math.sin(psi))
            hit = self.first_hit(w, P, Qp)
            tc = self.reach_t(P, Qp, w)
            if hit is not None and (tc is None or hit[0] < tc):
                step_dir = (Qp[0] - P[0], Qp[1] - P[1])
                ok, seg_dir = self._merge_ok(w, step_dir, hit[1], P, hit[2])
                if ok:
                    self.merge(w, P, Qp, hit)
                    return
                diff = _wrap(math.atan2(seg_dir[1], seg_dir[0]) - psi)
                if abs(_wrap(psi - psi0)) + rot_step > math.radians(45):
                    break
                psi = psi + math.copysign(min(rot_step, abs(diff)), diff)
                continue
            if tc is not None:
                self.mouth(w, P, Qp, tc)
                return
            self._move(w, Qp, psi)
            return
        t = hit[0] if hit is not None else 1.0
        Qs = (P[0] + 0.45 * t * (Qp[0] - P[0]), P[1] + 0.45 * t * (Qp[1] - P[1]))
        self.n_stall += 1
        self._move(w, Qs, psi, length=0.45 * t * p.step_m)

    def _move(self, w, Qp, psi, length=None):
        L = length if length is not None else self.p.step_m
        self.extend_edge(w.edge, Qp)
        w.pos = (float(Qp[0]), float(Qp[1]))
        w.psi = psi
        w.s_total += L
        w.s_split += L
        w.s_birth += L

    def refresh_q(self):
        _, edge_q = self._flow_planned()
        for i, e in enumerate(self.edges):
            e['q'] = float(edge_q[i])
        for eid, w in self.open.items():
            w.Q = float(edge_q[eid])

    def run(self):
        i = 0
        while True:
            alive = [w for w in self.walkers if not w.dead]
            if not alive:
                break
            if i % self.p.refresh_every == 0:
                self.refresh_q()
            for w in alive:
                if not w.dead:
                    self.advance(w)
            i += 1
            if i > 30000:
                raise RuntimeError('growth did not terminate')

    # ------------------------------------------------------------ lateral links (v3: oblique, random, width-scaled)
    def link_pass(self):
        """Lateral connecting channels.

        Per donor channel the link starts are laid out along its length with a mean
        spacing of ``link_spacing_k * w_donor`` (random jitter, never below
        ``link_gap_k * w_donor``); each slot becomes a link with probability ``link_prob``.
        A link leaves the donor at 20-60 deg, has a lognormal length scaled with the donor
        width and joins the target channel at 20-60 deg - so links are oblique, of very
        different length and their number follows the local channel width, not a fixed grid.
        Slots are processed from downstream to upstream so earlier point indices stay valid.
        """
        p, rng = self.p, self.rng
        if p.link_prob <= 0:
            return
        edge_q = self._flow_planned()[1]
        donors = [i for i, e in enumerate(self.edges)
                  if e['kind'] in ('lobe', 'distributary') and edge_q[i] >= p.link_donor_q_min]
        for d in donors:
            e = self.edges[d]
            pts = np.array(e['pts'], float)
            if len(pts) < 5:
                continue
            seg = np.hypot(*np.diff(pts, axis=0).T)
            cum = np.concatenate([[0.0], np.cumsum(seg)])
            L = float(cum[-1])
            wd = float(width_of(edge_q[d], p))
            spacing = p.link_spacing_k * wd
            gap = p.link_gap_k * wd
            s = float(rng.uniform(0.0, 1.0)) * spacing
            slots = []
            while s < 0.85 * L:
                if s > 0.15 * L:
                    slots.append(s)
                s += max(gap, spacing * float(rng.uniform(*p.link_slots_jitter)))
            for s in sorted(slots, reverse=True):
                if rng.random() > p.link_prob:
                    continue
                e = self.edges[d]
                if len(e['pts']) != len(pts) and s > cum[len(e['pts']) - 1]:
                    continue
                Q = self._flow_planned()[1]
                lam = float(rng.uniform(*p.link_frac))
                if lam * Q[d] < self.q_min_child:
                    continue
                k = int(min(np.searchsorted(cum, s, side='right') - 1, len(seg) - 1))
                if k >= len(e['segs']):
                    continue
                sfrac = float((s - cum[k]) / max(seg[k], 1e-9))
                sfrac = min(max(sfrac, 0.05), 0.95)
                A, B = e['pts'][k], e['pts'][k + 1]
                pos = (A[0] + sfrac * (B[0] - A[0]), A[1] + sfrac * (B[1] - A[1]))
                hd = _unit(B[0] - A[0], B[1] - A[1])
                Ldes = float(np.clip(p.link_len_k * wd * math.exp(p.link_len_sigma * rng.standard_normal()),
                                     p.link_len_min_m, p.link_len_max_m))
                tgt = self._pick_target(d, pos, hd, Ldes)
                if tgt is None:
                    continue
                tpt, = tgt
                vec = _unit(tpt[0] - pos[0], tpt[1] - pos[1])
                psi0 = math.atan2(vec[1], vec[0])
                nid, e2 = self.split_edge(d, k, sfrac, 'link_start')
                self.edges[e2]['frac'] = 1 - lam
                w = self.new_walker(nid, pos, psi0, vec, lam * Q[d], e['level'] + 1, e['lobe'], 'link', lam, {d, e2})
                w.target = tpt
                w.can_split = False
                w.s_birth = 0.0
        self.run()

    def _pick_target(self, donor, pos, hd, Ldes):
        p = self.p
        n = self.nseg
        S = self.S[:n]
        eids = self.SE[:n]
        mids = self.M[:n]
        dirs = S[:, 2:] - S[:, :2]
        dn = np.linalg.norm(dirs, axis=1) + 1e-12
        vec = mids - np.array(pos)
        d = np.linalg.norm(vec, axis=1) + 1e-12
        cosd = (vec @ np.array(hd)) / d                       # link direction vs donor tangent
        cost = np.einsum('ij,ij->i', vec, dirs) / (d * dn)    # link direction vs target tangent
        a0, a1 = p.link_ang_deg
        j0, j1 = p.link_junc_deg
        rad = np.array(_unit(pos[0] - p.apex_u, pos[1]))
        fwd = (vec @ rad) / d
        ok = ((d > 0.55 * Ldes) & (d < 1.7 * Ldes) &
              (cosd < math.cos(math.radians(a0))) & (cosd > math.cos(math.radians(a1))) &
              (cost < math.cos(math.radians(j0))) & (cost > math.cos(math.radians(j1))) &
              (fwd > p.link_forward_frac) & (eids != donor))
        a = self.edges[donor]['frm']
        score = np.where(ok, np.abs(np.log(d / Ldes)), np.inf)
        for i in np.argsort(score, kind='stable')[:8]:
            if not ok[i]:
                break
            te = self.edges[int(eids[i])]
            if te['to'] is None or self.reaches(te['to'], a):
                continue
            return ((float(mids[i, 0]), float(mids[i, 1])),)
        return None

    def _flow_planned(self):
        N = len(self.node_pos)
        frm = np.array([e['frm'] for e in self.edges])
        to = np.array([e['to'] if e['to'] is not None else -1 for e in self.edges])
        frac = np.array([e['frac'] for e in self.edges], float)
        return solve_flow(N, frm, to, frac, self.p.q_total, 0)[:2]


def build_delta_network_v3(params: DeltaParamsV3 | None = None, *, field_override=None, shore_test=None):
    """Grow the network with optional source-terrain steering and real shore.

    ``field_override.sample(u, v)`` supplies the existing five-component field.
    ``shore_test(u, v)`` replaces the analytic reach stop for non-trunk arms,
    after the first 3 km from the apex. Planning bounds remain independent.
    Omitting both hooks preserves the historical seeded construction.
    """
    p = params or DeltaParamsV3()
    for name in ('window_u_m', 'window_v_m'):
        bounds = np.asarray(getattr(p, name), dtype=float)
        if bounds.shape != (2,) or not np.isfinite(bounds).all() or bounds[1] - bounds[0] < 1200.:
            raise ValueError(name + ' must be finite increasing metre bounds spanning at least 1200 m')
    if not p.window_u_m[0] < p.apex_u < p.window_u_m[1] or not p.window_v_m[0] < 0. < p.window_v_m[1]:
        raise ValueError('planning window must contain the source apex')
    if not np.isfinite(p.boundary_margin_m) or p.boundary_margin_m < 0 or p.boundary_margin_m * 2 >= min(
            p.window_u_m[1] - p.window_u_m[0], p.window_v_m[1] - p.window_v_m[0]):
        raise ValueError('invalid finite planning boundary margin')
    purposes = ('lobes', 'relief', 'growth')
    seeds = {k: derive_seed('delta-network-v3/' + k, p.variant, world_seed=p.algorithm_world_seed) for k in purposes}
    lobes, harm, youngest = plan_lobes(p, rng_for('delta-network-v3/lobes', p.variant, world_seed=p.algorithm_world_seed))
    model = CoastModel(p, lobes, harm)
    field = field_override if field_override is not None else _Field(p, model,
        rng_for('delta-network-v3/relief', p.variant, world_seed=p.algorithm_world_seed))
    rng = rng_for('delta-network-v3/growth', p.variant, world_seed=p.algorithm_world_seed)
    b = _Builder(p, model, field, lobes, youngest, rng, shore_test=shore_test)
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
    g = _finalize(b, p, model, lobes, youngest, seeds)
    g.n_stall = b.n_stall
    return g


def _finalize(b, p, model, lobes, youngest, seeds):
    g = DeltaGraph()
    g.params, g.model, g.lobes, g.youngest, g.seeds = p, model, lobes, youngest, seeds
    N = len(b.node_pos)
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


# ----------------------------------------------------------------------------- diagnostics
def activity_profile(g, u_edges):
    """Number of channel crossings of each line u = const (active channels) and Q-weighted width."""
    out_n = np.zeros(len(u_edges), int)
    out_w = np.zeros(len(u_edges))
    for i in range(len(g.edge_from)):
        P = edge_points(g, i)
        u = P[:, 0]
        for k, uk in enumerate(u_edges):
            c = int(np.count_nonzero((u[:-1] - uk) * (u[1:] - uk) < 0))
            if c:
                out_n[k] += c
                out_w[k] += c * g.edge_w[i]
    return out_n, out_w


def event_profile(g):
    """u positions of splitting nodes (avulsion/bifurcation/link start) and of confluences."""
    kinds = g.node_kind
    ks = [NODE_KINDS.index(k) for k in ('avulsion', 'bifurcation', 'link_start')]
    kc = NODE_KINDS.index('confluence')
    split_u = g.node_uv[np.isin(kinds, ks), 0]
    conf_u = g.node_uv[kinds == kc, 0]
    return split_u, conf_u


def skeleton_metrics_v3(g):
    m = skeleton_metrics(g)
    m['guide_envelope_max_radius_m'] = m.pop('farthest_coast_from_apex_m')
    m['guide_envelope_width_m'] = m.pop('model_front_width_m')
    p = g.params
    mr = np.hypot(g.node_uv[g.mouth_nodes, 0] - p.apex_u, g.node_uv[g.mouth_nodes, 1])
    m['farthest_mouth_from_apex_m'] = float(mr.max())
    su, cu = event_profile(g)
    m['n_split_events'] = int(len(su))
    m['n_confluences'] = int(len(cu))
    m['split_u_km'] = dict(median=float(np.median(su) / 1000.0), p90=float(np.percentile(su, 90) / 1000.0))
    m['confluence_u_km'] = dict(median=float(np.median(cu) / 1000.0) if len(cu) else 0.0,
                                p90=float(np.percentile(cu, 90) / 1000.0) if len(cu) else 0.0)
    m['frac_splits_beyond_10km'] = float(np.mean(su > 10000.0))
    m['frac_confluences_beyond_10km'] = float(np.mean(cu > 10000.0)) if len(cu) else 0.0
    m['stall_steps'] = int(getattr(g, 'n_stall', 0))
    return m
