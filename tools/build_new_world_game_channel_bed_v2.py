"""Build sparse shared-bed profiles from the saved 30 m refinement, without replay."""
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path.cwd()))
from terrain_pipeline.channel_geometry import solve_shared_bed_scc

root = Path('.scratch/river-upgrade-20261101')
a = np.load(root / 'game-river-detail-v1/refinement.npz')
out = root / 'game-river-bed-v2'
out.mkdir(exist_ok=True)
off = a['offsets']; rc = a['row_col']; original = a['original_bed_m']
selected = np.flatnonzero(a['status'] != 2)
selected = selected[a['status'][selected] != 3]
# A raster sample is a single physical vertex even where separate paths cross.
indices = np.concatenate([np.arange(off[i], off[i+1]) for i in selected])
cells, inverse = np.unique(rc[indices], axis=0, return_inverse=True)
heights = np.full(len(cells), np.nan)
heights[inverse] = original[indices]
assert np.allclose(heights[inverse], original[indices], atol=1e-5)
arcs = []; cursor = 0; edge_vertices = {}
for i in selected:
    n = off[i+1] - off[i]; vertices = inverse[cursor:cursor+n]; cursor += n
    edge_vertices[int(i)] = vertices
    arcs.extend(zip(vertices[:-1], vertices[1:]))
bed, component, strong, bad = solve_shared_bed_scc(heights, arcs)
# Flow ownership is inherited from the saved graph, not from SCC connectivity.
# Cross-basin shared-cell SCCs require a corridor reroute, not flattening.
watershed = np.load(root/'game-hydro-v1/derived/watershed_id.npy', mmap_mode='r')
edge_owner = np.asarray(watershed[a['source']])
scc_sizes = np.bincount(strong)
scc_owners = {}
for i, vertices in edge_vertices.items():
    for group in np.unique(strong[vertices]):
        if scc_sizes[group] > 1:
            scc_owners.setdefault(int(group), set()).add(int(edge_owner[i]))
cross_basin_scc = [group for group, owners in scc_owners.items() if len(owners) > 1]
for group in cross_basin_scc:
    cid = component[np.flatnonzero(strong == group)[0]]
    bad[cid] = True
    bed[component == cid] = np.nan
reasons = ['downstream_cut_cap' if x else 'accepted' for x in bad]
accepted = np.zeros(len(a['source']), bool)
profile = np.full(len(rc), np.nan, dtype=np.float32)
for i, vertices in edge_vertices.items():
    assert len(set(component[vertices])) == 1
    if reasons[component[vertices[0]]] == 'accepted':
        accepted[i] = True
        profile[off[i]:off[i+1]] = bed[vertices]
        assert np.all(np.diff(bed[vertices]) <= 1e-8)
        assert np.max(heights[vertices] - bed[vertices]) <= 4.000001
# Sections use the existing default empirical Q scaling. Width and initial
# design incision are separate from the continuity cut and from water depth.
q = a['q_m3_s']; exposure = 1 - np.exp(-3.)
q30 = q[-1]; active = np.isfinite(q30) & (q30 > 0)
width = np.zeros(len(q30)); depth = np.zeros(len(q30))
width[active] = np.minimum(120, 4 * q30[active]**.45 * 1.75 * 1.25) * exposure
depth[active] = np.minimum(4, .6 * q30[active]**.3) * exposure
# Represented section uses actual closure cut, with a 0.6 bottom/top ratio.
# Its integral is a non-overlap estimate, not a terrain raster excavation.
volume = np.zeros(len(q30))
for i in np.flatnonzero(accepted & active):
    p = profile[off[i]:off[i+1]].astype(float)
    cut = original[off[i]:off[i+1]] - p
    xy = rc[off[i]:off[i+1]]
    length = np.linalg.norm(np.diff(xy, axis=0), axis=1) * 30
    volume[i] = np.sum((cut[:-1] + cut[1:]) * .5 * .8 * width[i] * length)
np.savez_compressed(out / 'shared-bed.npz', source=a['source'], target=a['target'], offsets=off,
    row_col=rc, original_bed_m=original, bed_m=profile, accepted=accepted,
    q_day15_day30_m3_s=q, active_day30=active, top_width_m=width,
    bottom_width_m=.6*width, initial_design_incision_m=depth,
    construction_bulk_nonoverlap_estimate_m3=volume,
    shared_cell_row_col=cells, shared_cell_source_m=heights, shared_cell_bed_m=bed,
    shared_cell_component=component, geometry_scc=strong)
failed = selected[~accepted[selected]]
summary = {'geometry_multi_cell_scc':int(np.count_nonzero(scc_sizes > 1)), 'cross_basin_scc_rejected':cross_basin_scc, 'selected_nonpool_edges':len(selected), 'accepted_edges':int(accepted.sum()),
 'rejected_edges':len(failed), 'rejected_source_ids':a['source'][failed].tolist(),
 'rejected_source_ids_by_reason':{reason:[int(a['source'][i]) for i in failed if reasons[component[edge_vertices[int(i)][0]]] == reason] for reason in ('directed_cycle','downstream_cut_cap')},
 'pool_touching_source_ids':a['source'][a['status']==2].tolist(),
 'rejected_component_reasons':{reason:reasons.count(reason) for reason in sorted(set(reasons))},
 'pool_touching_edges':int(np.count_nonzero(a['status']==2)),
 'accepted_active_day30_edges':int(np.count_nonzero(accepted & active)),
 'nonpool_inactive_or_unknown_day30_edges':int(np.count_nonzero(~active[selected])),
 'accepted_mouth_source_ids':a['source'][accepted & a['mouth_90m']].tolist(),
 'unaccepted_mouth_source_ids':a['source'][~accepted & a['mouth_90m']].tolist(),
 'accepted_max_cut_m':float(np.nanmax(heights-bed)) if np.isfinite(bed).any() else None,
 'bulk_nonoverlap_estimate_m3':float(volume.sum()),
 'source_identity':json.loads((root/'game-river-detail-v1/summary.json').read_text(encoding='utf8'))['source_identity']}
(out/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
print(json.dumps({k:v for k,v in summary.items() if not isinstance(v,(list,dict))}, indent=2))
