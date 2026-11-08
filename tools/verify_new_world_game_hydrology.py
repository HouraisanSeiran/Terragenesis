import hashlib, json, os, time
from pathlib import Path
import numpy as np
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval

root = Path('.scratch/river-upgrade-20261101')
out = root/'game-hydro-v1'
t = time.monotonic()
marker = root/'hydro-computing.pid'
marker.write_text(str(os.getpid()), encoding='ascii')
try:
    load = lambda path: np.load(path, mmap_mode='r', allow_pickle=False)
    terrain = root/'terrain-v3'
    manifest = json.loads((terrain/'manifest.json').read_text(encoding='utf8'))
    hashes = {}
    for name in ('bed_m', 'ocean_mask', 'valid_mask', 'unknown_mask', 'climate_base'):
        digest = hashlib.sha256()
        with (terrain/(name+'.npy')).open('rb') as f:
            for chunk in iter(lambda: f.read(8*1024*1024), b''):
                digest.update(chunk)
        hashes[name] = digest.hexdigest() == manifest['files'][name]
    r = root/'game-grade-90m'
    d = out/'derived'
    order, rec = [load(r/'routing'/(x+'.npy')) for x in ('order','receiver')]
    labels, anchors, capacity = [load(d/(x+'.npy')) for x in ('pool_index','pool_anchor','pool_capacity_m3')]
    valid, ocean, unknown = [load(r/(x+'.npy')) for x in ('valid_mask','ocean_mask','unknown_mask')]
    annual = np.asarray(load(terrain/'climate_base.npy')[2,::3,::3], dtype=np.float64).ravel()
    local = annual * (15/365) * .001 * .3 * 8100
    local[~(valid & ~ocean & ~unknown).ravel()] = 0
    saved = load(out/'pool_storage_m3.npy')
    state = np.array(saved[1])
    flow, _ = route_pool_interval(local, order, rec, labels, anchors, capacity, state)
    expected = load(out/'node_water_m3.npy')[1]
    sources = load(d/'mouth_source.npy')
    target = load(d/'mouth_ocean_receiver.npy')
    mouth = load(out/'mouth_water_m3.npy')
    levels = load(out/'pool_level_m.npy')
    result = dict(source_hashes_match=hashes, restarted_flow_max_abs_m3=float(np.max(np.abs(flow-expected))), restarted_storage_max_abs_m3=float(np.max(np.abs(state-saved[2]))), mouth_count=len(sources), mouth_edges_valid=bool(np.all(rec[sources] == target) and np.all(ocean.ravel()[target])), mouth_series_match=bool(np.array_equal(mouth[1], flow[sources])), positive_final_lakes=int(np.count_nonzero(saved[2]>0)), finite_levels_match_wet=bool(np.array_equal(np.isfinite(levels[2]), saved[2]>0)), unknown_mouths=int(load(out/'mouth_unknown.npy').sum()), seconds=time.monotonic()-t)
    (out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))
    assert all(hashes.values()) and result['restarted_flow_max_abs_m3'] == 0 and result['restarted_storage_max_abs_m3'] == 0 and result['mouth_edges_valid'] and result['mouth_series_match'] and result['finite_levels_match_wet']
finally:
    marker.unlink(missing_ok=True)
