"""Project the saved displayed receiver edges onto original control cells."""
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path.cwd()))
from terrain_pipeline.new_world_game_river_detail import local_path, required_cut

root = Path('.scratch/river-upgrade-20261101')
g, h, terrain = root/'game-grade-90m', root/'game-hydro-v1', root/'terrain-v3'
out = root/'game-river-detail-v1'
out.mkdir(exist_ok=True)
load = lambda p: np.load(p, mmap_mode='r')
old = np.load(root/'game-connectivity-v1/edges.npz')
source, target = old['source'], old['target']
bed = load(terrain/'bed_m.npy')
ocean = load(terrain/'ocean_mask.npy')
valid = load(terrain/'valid_mask.npy')
unknown_terrain = load(terrain/'unknown_mask.npy')
coarse = load(g/'bed_m.npy')
width = coarse.shape[1]
pool = load(h/'derived/pool_index.npy')
watershed = load(h/'derived/watershed_id.npy')
level = load(h/'pool_level_m.npy')
storage = load(h/'pool_storage_m3.npy')
anchors = load(h/'derived/pool_anchor.npy')
water = load(h/'node_water_m3.npy')
nodes = np.unique(np.concatenate((source, target)))
node_rc = np.column_stack((nodes // width * 3, nodes % width * 3)).astype(np.int32)
assert np.array_equal(np.asarray(coarse).ravel()[nodes], bed[node_rc[:, 0], node_rc[:, 1]])
control_rc = node_rc.copy()
positions = dict(zip(nodes.tolist(), map(tuple, node_rc.tolist())))
def basin_allowed(donor):
    basin = watershed[donor]
    def allowed(cell):
        row = min((cell[0] + 1) // 3, coarse.shape[0] - 1)
        col = min((cell[1] + 1) // 3, width - 1)
        return bool(valid[cell] and not unknown_terrain[cell] and watershed[row * width + col] == basin)
    return allowed
# Bind each ocean receiver once, shared by all displayed incoming mouth edges.
# A contact must be reachable from every displayed donor in a 360 m disk.
mouth_mask = old['mouth_90m']
for receiver in np.unique(target[mouth_mask]):
    donors = source[mouth_mask & (target == receiver)]
    anchor = positions[int(receiver)]
    candidates = []
    for dr in range(-12, 13):
        for dc in range(-12, 13):
            r, c = anchor[0] + dr, anchor[1] + dc
            if dr*dr + dc*dc <= 144 and 0 <= r < bed.shape[0] and 0 <= c < bed.shape[1] and ocean[r, c]:
                candidates.append((dr*dr + dc*dc, r, c))
    fallback = None
    for _, r, c in sorted(candidates):
        contact = (r, c)
        approaches = [local_path(bed, ocean, positions[int(donor)], contact, margin=3,
                                 allow_ocean_end=True, allowed=basin_allowed(donor)) for donor in donors]
        if any(path is None for path in approaches):
            continue
        if fallback is None:
            fallback = contact
        if all(np.max(required_cut([bed[cell] for cell in path])) <= 4 for path in approaches):
            fallback = contact
            break
    if fallback is not None:
        positions[int(receiver)] = fallback
node_rc = np.asarray([positions[int(node)] for node in nodes], np.int32)
paths, profiles, cuts, offsets = [], [], [], [0]
status = np.zeros(len(source), np.uint8)
wet = np.zeros(len(source), bool)
mouth_contact = np.zeros(len(source), bool)
max_cut = np.full(len(source), np.nan, np.float32)
cut_ends = np.full(len(source), np.nan, np.float32)
for i, (a, b) in enumerate(zip(source, target)):
    start, end = positions[int(a)], positions[int(b)]
    mouth = bool(old['mouth_90m'][i])
    path = local_path(bed, ocean, start, end, allow_ocean_end=mouth, allowed=basin_allowed(a))
    if path is None:
        status[i] = 3  # no path in local search corridor
        offsets.append(offsets[-1])
        continue
    rc = np.asarray(path, np.int32)
    values = np.asarray(bed[rc[:, 0], rc[:, 1]], np.float32)
    cut = required_cut(values).astype(np.float32)
    max_cut[i] = np.max(cut)
    mouth_contact[i] = mouth and bool(ocean[tuple(rc[-1])])
    pa, pb = int(pool[a]), int(pool[b])
    coarse_rows = np.minimum((rc[:, 0] + 1) // 3, coarse.shape[0] - 1)
    coarse_cols = np.minimum((rc[:, 1] + 1) // 3, width - 1)
    crosses_pool = np.any(pool[coarse_rows * width + coarse_cols] >= 0)
    if pa >= 0 or pb >= 0 or crosses_pool:
        status[i] = 2  # pool transitions/interior are never cut here
        if pa >= 0 and pa == pb and np.isfinite(level[-1, pa]):
            wet[i] = bool(storage[-1, pa] > 0 and np.all(values < level[-1, pa]))
        cut[:] = 0
    elif max_cut[i] <= 4.0:
        status[i] = 0  # bounded per-edge construction proposal
    else:
        status[i] = 1  # exceeds bound, retain unmodified profile
        cut[:] = 0
    cut_ends[i] = cut[-1]
    paths.append(rc)
    profiles.append(values)
    cuts.append(cut)
    offsets.append(offsets[-1] + len(rc))
np.savez_compressed(out/'refinement.npz', source=source, target=target, node_id=nodes,
    node_row_col=node_rc, control_row_col=control_rc, offsets=np.asarray(offsets, np.int64), row_col=np.concatenate(paths),
    original_bed_m=np.concatenate(profiles), proposed_cut_m=np.concatenate(cuts),
    status=status, max_required_cut_m=max_cut, actual_pool_surface_covers_path=wet,
    mouth_90m=old['mouth_90m'], mouth_contact=mouth_contact,
    pool_source=old['pool_source'], pool_target=old['pool_target'], q_m3_s=old['q_m3_s'],
    terminal_index=load(h/'derived/terminal_index.npy')[source],
    pool_id=load(h/'derived/pool_id.npy'))
incoming_cut_nodes = np.unique(target[(status == 0) & (cut_ends > 1e-5)])
shared_cut_nodes = np.intersect1d(incoming_cut_nodes, source[status == 0])
summary = dict(edges=len(source), nodes=len(nodes), status_counts={str(i): int((status == i).sum()) for i in range(4)},
    same_pool_actual_wet=int(wet.sum()), mouths=int(old['mouth_90m'].sum()),
    mouths_contact=int(mouth_contact.sum()), max_required_cut_m=float(np.nanmax(max_cut)),
    unresolved_source_ids=source[status != 0].tolist(),
    unresolved_mouth_source_ids=source[old['mouth_90m'] & ~mouth_contact].tolist(),
    same_pool_not_covered_source_ids=source[(old['pool_source'] >= 0) & (old['pool_source'] == old['pool_target']) & ~wet].tolist(),
    mouth_source_ids=source[mouth_mask].tolist(),
    mouth_status=status[mouth_mask].tolist(),
    before_rising_edges=int(np.count_nonzero(old['max_rise_m'] > 1e-5)),
    after_raw_rising_edges=int(np.count_nonzero(max_cut > 1e-5)),
    after_within_bound_edges=int(np.count_nonzero(max_cut <= 4)),
    moved_mouth_receiver_nodes=int(np.count_nonzero(np.any(node_rc != control_rc, axis=1))),
    old_source_sample_differs_from_control=int(np.count_nonzero(np.abs(old['endpoint_bed_m'][:, 0] - np.asarray(coarse).ravel()[source]) > 1e-5)),
    shared_nodes_with_incoming_cut_and_uncut_outgoing=int(len(shared_cut_nodes)),
    source_identity=json.loads((terrain/'manifest.json').read_text(encoding='utf8'))['identity'],
    algorithm='control-cell-local-path-v1', search_margin_cells=3, max_proposed_cut_m=4.0)
(out/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
print(json.dumps({k:v for k,v in summary.items() if not isinstance(v, list)}, indent=2))
