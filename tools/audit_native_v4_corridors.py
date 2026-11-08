"""Read-only audit: v4 corridors re-evaluated with v3 pool levels, compared with v5 (event v3)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.new_world_native_network import section

ROOT = Path(__file__).resolve().parents[1] / '.scratch' / 'river-upgrade-20261101'
OUT = ROOT / 'native-v4-corridor-audit'
SECONDS = 1296000


def peak_and_volume(path, level, bed, q):
    cols = bed.shape[1]
    path = np.asarray(path)
    zz = path // cols
    xx = path % cols
    h = np.asarray(bed[zz, xx], dtype='f8')
    peak = max(0., float(np.max(h - level + .05)))
    length = 0.
    for a in range(len(path) - 1):
        dz = abs(int(zz[a + 1] - zz[a]))
        dx = abs(int(xx[a + 1] - xx[a]))
        length += 30 * (2 ** .5 if dz and dx else 1.)
        if not dz or not dx:
            mid = (h[a] + h[a + 1]) * .5
        else:
            mid = (h[a] + h[a + 1] + bed[zz[a], xx[a + 1]] + bed[zz[a + 1], xx[a]]) * .25
        peak = max(peak, float(mid - level + .05))
    width = float(section(np.array([q]))[0][0])
    return peak, max(0., peak) * width * length


def stats(values):
    v = np.asarray(values, dtype='f8')
    if not v.size:
        return {}
    return dict(n=int(v.size), min=float(v.min()), p50=float(np.percentile(v, 50)), p90=float(np.percentile(v, 90)), max=float(v.max()), sum=float(v.sum()))


def main():
    load = lambda p: np.load(p, mmap_mode='r')
    bed = load(ROOT / 'terrain-v3/bed_m.npy')
    d = ROOT / 'native-final-routing-v1/derived'
    anchors = load(d / 'pool_anchor.npy')
    lv2 = load(ROOT / 'native-event-v2/pool_level_m.npy')[2]
    lv3 = load(ROOT / 'native-event-v3/pool_level_m.npy')[2]
    f2 = load(ROOT / 'native-event-v2/node_water_m3.npy')[1]
    f3 = load(ROOT / 'native-event-v3/node_water_m3.npy')[1]
    result = {}
    for tag, work in (('v4', 'native-network-v4-work'), ('v5', 'native-network-v5-work')):
        w = ROOT / work
        off = load(w / 'corridor_offsets.npy')
        nodes = load(w / 'corridor_node_id.npy')
        eidx = load(w / 'corridor_edge_index.npy')
        pidx = load(w / 'corridor_pool_index.npy')
        stored_cut = load(w / 'corridor_cut_bound_m.npy')
        stored_cap = load(w / 'corridor_capacity_bound_m3.npy')
        fail = load(w / 'corridor_failure_edges.npy')
        rows = []
        for i in range(len(eidx)):
            pool = int(pidx[i])
            anchor = int(anchors[pool])
            path = nodes[off[i]:off[i + 1]]
            p2, c2 = peak_and_volume(path, float(lv2[pool]), bed, float(f2[anchor]) / SECONDS)
            p3, c3 = peak_and_volume(path, float(lv3[pool]), bed, float(f3[anchor]) / SECONDS)
            rows.append(dict(edge=int(eidx[i]), pool=pool, stored_cut=float(stored_cut[i]), cut_v2=p2, cut_v3=p3, cap_v2=c2, cap_v3=c3, stored_cap=float(stored_cap[i]), level_diff=float(lv3[pool] - lv2[pool]), flow_v3_m3=float(f3[anchor])))
        cut3 = np.array([r['cut_v3'] for r in rows])
        cut2 = np.array([r['cut_v2'] for r in rows])
        diff = np.array([r['level_diff'] for r in rows])
        result[tag] = dict(
            corridors=len(rows), failures=int(len(fail)),
            stored_cut_max=float(np.max(stored_cut)) if len(rows) else 0.,
            recomputed_v2_matches_stored=bool(np.allclose(cut2, np.array([r['stored_cut'] for r in rows]), atol=1e-9)) if rows else True,
            max_cut_v2=float(cut2.max()) if rows else 0., max_cut_v3=float(cut3.max()) if rows else 0.,
            over_4m_v3=int(np.count_nonzero(cut3 > 4.)), over_6m_v3=int(np.count_nonzero(cut3 > 6.)),
            over_4m_v2=int(np.count_nonzero(cut2 > 4.)),
            level_diff_v3_minus_v2=stats(diff),
            changed_level_edges=int(np.count_nonzero(np.abs(diff) > 1e-9)),
            cut_increase_edges=int(np.count_nonzero(cut3 > cut2 + 1e-9)),
            capacity_bound_stored=float(sum(r['stored_cap'] for r in rows)),
            capacity_bound_v3=float(sum(r['cap_v3'] for r in rows)),
            affected_flow_m3_over_4m=float(sum(r['flow_v3_m3'] for r, c in zip(rows, cut3) if c > 4.)),
            affected_flow_m3_level_changed=float(sum(r['flow_v3_m3'] for r in rows if abs(r['level_diff']) > 1e-9)),
            worst_edges=sorted(rows, key=lambda r: -r['cut_v3'])[:5])
    net = ROOT / 'native-network-v3'
    pools = load(net / 'inlet_pool_index.npy')
    status = load(net / 'edge_status.npy')
    eids = load(net / 'inlet_edge_index.npy')
    result['inlet_pools_negative_total'] = int(np.count_nonzero(pools < 0))
    result['inlet_pools_negative_status7'] = int(sum(1 for i, k in enumerate(eids) if status[k] == 7 and pools[i] < 0))
    v4f = load(ROOT / 'native-network-v4-work/corridor_failure_edges.npy')
    result['v4_failure_reasons'] = 'v4 stored no reasons; failures=%d' % len(v4f)
    OUT.mkdir(exist_ok=True)
    (OUT / 'audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items()}, indent=2, ensure_ascii=False)[:6000])


if __name__ == '__main__':
    main()
