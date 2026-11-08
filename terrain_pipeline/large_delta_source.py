"""Whole-support known-local runoff under an explicitly full reservoir boundary."""
import csv
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_game_hydrology import IDENTITY, ROOT
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval

OUT = Path('.scratch/large-delta-20261101/source-steady-v1')
DT = 15 * 86400

def run():
    terrain = ROOT / 'terrain-v3'
    route = ROOT / 'native-final-routing-v1'
    event = ROOT / 'native-event-v3'
    base = ROOT / 'native-event-v1'
    meta = json.loads((event / 'manifest.json').read_text(encoding='utf8'))
    if meta['source_identity'] != IDENTITY:
        raise ValueError('source identity mismatch')
    OUT.mkdir(parents=True, exist_ok=True)
    load = lambda p: np.load(p, mmap_mode='r', allow_pickle=False)
    d = route / 'derived'
    order, receiver = (load(route / 'routing' / (x + '.npy')) for x in ('order', 'receiver'))
    labels, anchors, nodes, unknown = (load(d / (x + '.npy')) for x in ('pool_index', 'pool_anchor', 'mouth_source', 'total_water_unknown'))
    capacity = load(event / 'pool_capacity_m3.npy')
    local = load(base / 'local_contribution_m3.npy')
    state = np.array(capacity)
    flow, retained = route_pool_interval(local, order, receiver, labels, anchors, capacity, state)
    q = np.array(flow[nodes]) / DT
    valid, ocean, invalid = (load(terrain / (x + '.npy')).ravel() for x in ('valid_mask', 'ocean_mask', 'unknown_mask'))
    terminal = float(q.sum() * DT)
    for start in range(0, len(local), 262144):
        end = min(start + 262144, len(local))
        mask = (receiver[start:end] < 0) & valid[start:end] & ~ocean[start:end]
        terminal += float(flow[start:end][mask].sum())
    np.save(OUT / 'steady_node_volume_m3.npy', flow)
    del flow
    area = np.lib.format.open_memmap(OUT / 'local_land_area_m2.npy', mode='w+', dtype='f8', shape=local.shape)
    for start in range(0, len(local), 262144):
        end = min(start + 262144, len(local))
        area[start:end] = 900. * (valid[start:end] & ~ocean[start:end] & ~invalid[start:end])
    zero = np.zeros(len(capacity))
    accumulated, _ = route_pool_interval(area, order, receiver, labels, anchors, zero, zero.copy())
    mouth_area = np.array(accumulated[nodes])
    del accumulated, area
    previous = load(event / 'mouth_water_m3.npy')[1] / DT
    coords = np.column_stack((nodes % 4096 * 30 - 61440, nodes // 4096 * 30 - 61440))
    flags = np.asarray(unknown[nodes], dtype=bool)
    np.savez(OUT / 'mouths.npz', node=nodes, xz_m=coords, steady_known_local_q_m3_s=q, transient_15_30d_q_m3_s=previous, known_local_land_area_m2=mouth_area, total_unknown=flags)
    with (OUT / 'mouths.csv').open('w', newline='', encoding='utf8') as f:
        w = csv.writer(f); w.writerow(['mouth_index','node','x_m','z_m','steady_local_q_m3_s','transient_day15_30_q_m3_s','difference_m3_s','known_local_land_area_km2','total_unknown'])
        for i in range(len(nodes)):
            w.writerow([i,int(nodes[i]),*coords[i],q[i],previous[i],q[i]-previous[i],mouth_area[i]/1e6,int(flags[i])])
    record = dict(source_identity=IDENTITY, duration_seconds=DT, forcing=meta['forcing'], boundary='all corrected pools initially full; no evaporation; external inflow unknown', initial_storage_m3=float(capacity.sum()), final_storage_m3=float(state.sum()), local_m3=float(local.sum()), retained_m3=float(retained), terminal_m3=terminal, residual_m3=float(local.sum())-retained-terminal, mouth_count=len(nodes))
    (OUT / 'manifest.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    print(json.dumps(record, indent=2), flush=True)

if __name__ == '__main__':
    run()
