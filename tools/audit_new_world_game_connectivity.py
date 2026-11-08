import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path.cwd()))
from terrain_pipeline.new_world_game_connectivity import audit_edges

root = Path('.scratch/river-upgrade-20261101')
g = root/'game-grade-90m'; h = root/'game-hydro-v1'; d = h/'derived'; terrain = root/'terrain-v3'; low = root/'game-grade-lowland'
out = root/'game-connectivity-v1'; out.mkdir(exist_ok=True)
load = lambda p: np.load(p, mmap_mode='r')
manifest = json.loads((h/'manifest.json').read_text(encoding='utf8'))
assert json.loads((terrain/'manifest.json').read_text(encoding='utf8'))['identity'] == manifest['source_identity']
rec = load(g/'routing/receiver.npy'); channel = load(low/'channel_mask.npy').ravel()
x = load(g/'graph/node_x_m.npy')*3-61440; z = load(g/'graph/node_z_m.npy')*3-61440
bounds = [-26170,23830,-19990,30010]
ids = np.flatnonzero(channel & (rec >= 0) & (x >= bounds[0]) & (x <= bounds[1]) & (z >= bounds[2]) & (z <= bounds[3]))
target = rec[ids]
bed = load(terrain/'bed_m.npy'); ocean = load(terrain/'ocean_mask.npy')
r = audit_edges(bed, ocean, x, z, ids, target)
pool = load(d/'pool_index.npy'); pa, pb = pool[ids], pool[target]
level = load(h/'pool_level_m.npy'); anchor = load(d/'pool_anchor.npy'); spill = load(d/'pool_spill_m.npy')
unknown = load(d/'total_water_unknown.npy').ravel()[ids]
water = load(h/'node_water_m3.npy'); times = load(h/'time_seconds.npy')
q = np.asarray(water[:,ids]) / np.diff(times)[:,None]
inside = pa >= 0
q[:,inside & (ids != anchor[np.maximum(pa,0)])] = np.nan
mouth = load(g/'ocean_mask.npy').ravel()[target]
inlet = (pb >= 0) & (pa != pb); outlet = (pa >= 0) & (pa != pb)
levels = np.full((2,len(ids)), np.nan)
for j,p in enumerate((pa,pb)):
    m = p >= 0; levels[j,m] = level[-1,p[m]]
# Status is geometric only: 0 non-increasing, 1 rising; 2 source ocean mismatch.
same_pool = (pa >= 0) & (pa == pb)
pool_surface_covers_line = same_pool & np.isfinite(levels[0]) & (levels[0] > r['bed_max_m'])
inlet_target_wet = inlet & np.isfinite(levels[1]) & (levels[1] > r['endpoint_bed_m'][:,1])
outlet_source_wet = outlet & np.isfinite(levels[0]) & (levels[0] > r['endpoint_bed_m'][:,0])
status = (r['max_rise_m'] > 1e-5).astype(np.uint8)
status[mouth & ~r['ocean_crossing']] = 2
np.savez_compressed(out/'edges.npz', source=ids, target=target, source_xz_m=np.column_stack((x[ids],z[ids])), target_xz_m=np.column_stack((x[target],z[target])), status=status, unknown=unknown, q_m3_s=q, pool_source=pa, pool_target=pb, pool_level_day30_m=levels, pool_level_day15_m=np.stack((np.where(pa >= 0, level[1,np.maximum(pa,0)], np.nan), np.where(pb >= 0, level[1,np.maximum(pb,0)], np.nan))), pool_surface_covers_line=pool_surface_covers_line, inlet_target_wet=inlet_target_wet, outlet_source_wet=outlet_source_wet, inlet=inlet, outlet=outlet, mouth_90m=mouth, **r)
visible_pools = np.unique(np.concatenate((pa[pa>=0],pb[pb>=0])))
overflow = np.any(np.asarray(water[:,anchor[visible_pools]]) > 0,axis=0)
dry = ~np.isfinite(level[-1,visible_pools])
maxi = int(np.argmax(r['max_rise_m']))
summary = dict(source_identity=manifest['source_identity'], bounds_xz_m=bounds, edges=len(ids), rising_edges=int(np.count_nonzero(r['max_rise_m']>1e-5)), max_rise_m=float(r['max_rise_m'][maxi]), max_step_m=float(r['max_step_m'].max()), max_edge_source=int(ids[maxi]), max_blocker_row_col=r['blocker_row_col'][maxi].tolist(), max_blocker_entry_xz_m=r['blocker_entry_xz_m'][maxi].tolist(), unknown_edges=int(unknown.sum()), inlets=int(inlet.sum()), inlet_target_wet=int(inlet_target_wet.sum()), outlets=int(outlet.sum()), outlet_source_wet=int(outlet_source_wet.sum()), same_pool_edges=int(same_pool.sum()), same_pool_surface_covers_line=int(pool_surface_covers_line.sum()), visible_pools=len(visible_pools), dry_day30=int(dry.sum()), overflow_any_interval=int(overflow.sum()), mouths_90=int(mouth.sum()), mouths_without_30m_ocean_crossing=int((mouth & ~r['ocean_crossing']).sum()), mouths_target_not_30m_ocean=int((mouth & ~r['ocean_at_target']).sum()), nonmouth_30m_ocean_crossings=int((~mouth & r['ocean_crossing']).sum()))
(out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print(json.dumps(summary,indent=2))
