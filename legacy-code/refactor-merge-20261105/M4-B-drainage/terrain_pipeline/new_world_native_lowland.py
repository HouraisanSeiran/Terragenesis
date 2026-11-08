"""Native event channel evidence on the saved 30 m receiver graph."""
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from numba import njit
from terrain_pipeline.new_world_game_hydrology import ROOT, IDENTITY
from terrain_pipeline.surface_rivers.metric_lowland_runoff import LowlandRunoffConfig, lowland_geometry


@njit
def accumulate(order, receiver, area):
    for j in range(order.size - 1, -1, -1):
        i = order[j]
        target = receiver[i]
        if target >= 0:
            area[target] += area[i]


@njit
def channels_and_capture(order, receiver, labels, anchors, area, lowland, ocean, unknown, valid, flow, channel, capture):
    for j in range(order.size - 1, -1, -1):
        i = order[j]
        p = labels[i]
        eligible = valid[i] and not ocean[i] and not unknown[i] and flow[i] >= .015 * 1296000 and (p < 0 or anchors[p] == i)
        if eligible:
            threshold = 4000000 if lowland[i] else 810000
            if area[i] * 900 >= threshold:
                channel[i] = True
            if channel[i]:
                target = receiver[i]
                if target >= 0:
                    channel[target] = True
        else:
            channel[i] = False
    for j in range(order.size):
        i = order[j]
        if channel[i]:
            capture[i] = i
        elif receiver[i] >= 0:
            capture[i] = capture[receiver[i]]
        else:
            capture[i] = -1


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(*, root=ROOT, output=None):
    start = time.monotonic()
    root = Path(root)
    terrain = root / 'terrain-v3'; event = root / 'native-event-v1'; route = root / 'native-final-routing-v1'
    source = json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    water = json.loads((event / 'manifest.json').read_text(encoding='utf8'))
    if source['identity'] != IDENTITY or water['source_identity'] != IDENTITY or water['spacing_m'] != 30:
        raise ValueError('source binding mismatch')
    out = Path(output or root / 'native-lowland-v1')
    out.mkdir(exist_ok=False)
    load = lambda p: np.load(p, mmap_mode='r', allow_pickle=False)
    bed = load(terrain / 'bed_m.npy'); shape = bed.shape; n = bed.size
    ocean, unknown, valid = (load(terrain / (x + '.npy')).ravel() for x in ('ocean_mask','unknown_mask','valid_mask'))
    order, receiver = (load(route / 'routing' / (x+'.npy')) for x in ('order','receiver'))
    labels, anchors = (load(route / 'derived' / (x+'.npy')) for x in ('pool_index','pool_anchor'))
    flow = load(event / 'node_water_m3.npy')[1]
    lowland = np.lib.format.open_memmap(out/'lowland_mask.npy',mode='w+',dtype='?',shape=shape)
    config = LowlandRunoffConfig(upland_initiation_area_m2=810000.)
    halo = int(np.ceil(config.relief_radius_m / 30)) + 1
    for a in range(0,shape[0],128):
        b = min(a+128,shape[0]); lo = max(0,a-halo); hi = min(shape[0],b+halo)
        _, _, mask = lowland_geometry(np.asarray(bed[lo:hi]),30,config)
        lowland[a:b] = mask[a-lo:b-lo]
    lowland.flush()
    area = np.lib.format.open_memmap(out/'contributing_cells.npy',mode='w+',dtype='i4',shape=(n,))
    for a in range(0,n,262144):
        b = min(a+262144,n)
        area[a:b] = valid[a:b] & ~ocean[a:b] & ~unknown[a:b]
    accumulate(order,receiver,area); area.flush()
    channel = np.lib.format.open_memmap(out/'channel_mask.npy',mode='w+',dtype='?',shape=shape)
    capture = np.lib.format.open_memmap(out/'capture_index.npy',mode='w+',dtype='i4',shape=shape)
    channels_and_capture(order,receiver,labels,anchors,area,lowland.ravel(),ocean,unknown,valid,flow,channel.ravel(),capture.ravel())
    channel.flush(); capture.flush()
    # Fixed physical window uses inclusive control-cell centers.
    x0,x1,z0,z1 = 1176,2843,1382,3049
    sl = np.s_[z0:z1,x0:x1]
    land_count = 0; captured = 0; terminal_area = 0
    for a in range(0,n,262144):
        b=min(a+262144,n); land=valid[a:b] & ~ocean[a:b] & ~unknown[a:b]
        land_count += int(land.sum()); captured += int(np.count_nonzero(land & (capture.ravel()[a:b] >= 0)))
        dest=receiver[a:b]; target=np.maximum(dest,0); terminal=(dest<0) | ocean[target] | unknown[target] | ~valid[target]
        terminal_area += int(area[a:b][land & terminal].sum(dtype=np.int64))
    record = dict(schema='native-lowland-v1',source_identity=IDENTITY,terrain_manifest_sha256=digest(terrain/'manifest.json'),event_manifest_sha256=digest(event/'manifest.json'),routing_binding_sha256=digest(route/'binding.json'), source_paths=dict(terrain=str(terrain),event=str(event),routing=str(route)),shape_zx=list(shape),spacing_m=30,origin_center_m=[-61440,-61440],cell_area_m2=900,interval=1,config=dict(upland_initiation_area_m2=810000,lowland_initiation_area_m2=4000000,relief_radius_m=300,lowland_relief_m=20,lowland_slope=.025,q_threshold_m3_s=.015),window_bounds_xz_m=[-26170,23830,-19990,30010],window_counts=dict(channel_cells=int(channel[sl].sum()),lowland_cells=int(lowland[sl].sum()),lowland_land_cells=int(np.count_nonzero(lowland[sl] & valid.reshape(shape)[sl] & ~ocean.reshape(shape)[sl] & ~unknown.reshape(shape)[sl]))),counts=dict(channel_cells=int(channel.sum()),land_cells=land_count,captured_land_cells=captured,terminal_contributing_cells=terminal_area),budgets_unchanged=water['budgets'],algorithm='saved receiver area initiation and downstream closure gated by actual interval 2 flow; pool interiors excluded except overflow anchor',runtime_seconds=time.monotonic()-start)
    if terminal_area != land_count: raise ValueError('contributing area does not close')
    tmp=out/'manifest.tmp'; tmp.write_text(json.dumps(record,indent=2),encoding='utf8'); os.replace(tmp,out/'manifest.json')
    return record

