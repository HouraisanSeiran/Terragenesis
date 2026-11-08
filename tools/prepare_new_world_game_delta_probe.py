"""Audit a short real mouth reach; this is not a completed delta product."""
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

from terrain_pipeline.common_infra import identity
from terrain_pipeline.new_world_game_delta import route_trace_sediment, section_stages
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters


ROOT = Path('.scratch/river-upgrade-20261101')
SOURCE_ID = 'c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'


def main():
    source, hydro, graph = ROOT / 'terrain-v3', ROOT / 'game-hydro-v1', ROOT / 'game-grade-90m'
    manifest = json.loads((hydro / 'manifest.json').read_text(encoding='utf8'))
    terrain = json.loads((source / 'manifest.json').read_text(encoding='utf8'))
    if manifest['source_identity'] != SOURCE_ID or terrain['identity'] != SOURCE_ID:
        raise ValueError('source identity mismatch')
    xy = np.load(hydro / 'mouth_world_xz_m.npy')
    water = np.load(hydro / 'mouth_water_m3.npy')
    unknown = np.load(hydro / 'mouth_unknown.npy')
    candidates = np.flatnonzero((xy[:, 0] >= -26170) & (xy[:, 0] <= 23830)
        & (xy[:, 1] >= -19990) & (xy[:, 1] <= 30010) & ~unknown)
    mouth = int(candidates[np.argmax(water[:, candidates].sum(axis=0))])
    mouth_node = int(np.load(hydro / 'derived/mouth_source.npy')[mouth])
    rec = np.load(graph / 'routing/receiver.npy', mmap_mode='r')
    area = np.load(graph / 'contributing_cells.npy', mmap_mode='r').ravel()
    pool = np.load(hydro / 'derived/pool_index.npy', mmap_mode='r')
    chain = [mouth_node]
    while len(chain) < 128:
        parents = np.flatnonzero(rec == chain[-1])
        if not len(parents): break
        parent = int(parents[np.argmax(area[parents])])
        if pool[parent] >= 0: break
        chain.append(parent)
    chain.reverse()
    ids = np.asarray(chain, dtype=np.int64)
    x = np.load(graph / 'graph/node_x_m.npy', mmap_mode='r')[ids] * 3 - 61440
    z = np.load(graph / 'graph/node_z_m.npy', mmap_mode='r')[ids] * 3 - 61440
    bed = np.load(source / 'bed_m.npy', mmap_mode='r')
    ocean = np.load(source / 'ocean_mask.npy', mmap_mode='r')
    nodes = np.column_stack([x, z])
    tangents = np.gradient(nodes, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    offsets = np.arange(-10, 11) * 30.
    section = nodes[:, None, :] + offsets[None, :, None] * np.stack([-tangents[:, 1], tangents[:, 0]], axis=1)[:, None, :]
    coords = [(section[:, :, 1]+61440)/30, (section[:, :, 0]+61440)/30]
    profiles = map_coordinates(bed, coords, order=1)
    center = map_coordinates(bed, [(z+61440)/30, (x+61440)/30], order=1).astype(float)
    distances = np.linalg.norm(np.diff(nodes, axis=0), axis=1)
    length = np.r_[distances, distances[-1]]
    # Local normal-flow approximation: a positive regression gradient, not a
    # claim that all sampled bed steps are downhill or that backwater is solved.
    gradient = (center[0] - center[-1]) / distances.sum()
    if gradient <= 0: raise ValueError('local physical reach lacks downhill mean bed')
    time = np.load(hydro / 'time_seconds.npy').astype(float)
    volume = np.asarray(np.load(hydro / 'node_water_m3.npy', mmap_mode='r')[:, ids], dtype=float)
    if not np.allclose(volume[:, -1], water[:, mouth]): raise ValueError('mouth water mismatch')
    stage, width = section_stages(profiles, 30., volume / np.diff(time)[:, None],
                                  np.full(len(ids), gradient), .035)
    depth = np.maximum(stage - profiles.min(axis=1), 0.)
    # Declared finite stocks, not construction spoil; the upstream boundary has
    # no supplied solid and therefore this is only a local minimum scenario.
    widths = np.maximum(width.max(axis=0), 1.)
    geom = identity({'node_ids': ids, 'sections_m': profiles, 'ocean_mask_at_sections':
        map_coordinates(ocean.astype(np.uint8), coords, order=0).astype(bool)},
        {'source_identity': SOURCE_ID, 'spacing_m': 30.})
    hydroid = identity({'time_seconds': time, 'routed_volume_m3': volume},
                       {'mouth_index': mouth, 'source_identity': SOURCE_ID})
    material = MaterialParameters(provenance='declared game scenario, uncalibrated')
    result = route_trace_sediment(receiver=np.r_[np.arange(1, len(ids)), -1].astype(np.int64),
        length_m=length, width_m=widths, bed_m=center, depth_m=depth,
        routed_water_m3=volume, slope=np.full(len(ids), gradient), time_seconds=time,
        rock_floor_m=center-1., alluvium_bulk_m3=widths*length*.25,
        hardness=np.full(len(ids), .5), material=material, geometry_identity=geom,
        hydraulic_identity=hydroid, provenance='declared 0.25 m alluvium, 1 m rock floor, hardness 0.5')
    out = ROOT / 'game-delta-local-probe'
    out.mkdir(exist_ok=True)
    np.savez_compressed(out / 'reach.npz', **result['arrays'], node_ids=ids, node_xz_m=nodes,
                        section_bed_m=profiles, section_stage_m=stage)
    report = {'source_identity': SOURCE_ID, 'mouth_index': mouth,
        'mouth_id': str(np.load(hydro / 'derived/mouth_id.npy')[mouth]),
        'mouth_water_m3': water[:, mouth].tolist(), 'node_ids': ids.tolist(),
        'gradient_approximation': gradient, 'geometry_identity': geom,
        'local_hydraulic_identity': hydroid, 'sediment_identity': result['identity_sha256'],
        'mouth_solid_m3': result['arrays']['exported_solid_m3'][:, -1].tolist(),
        'global_residual_m3': result['metadata']['global_residual'],
        'limitations': ['local short reach only; upstream sediment supply omitted',
            'section normal flow uses mean gradient, does not solve backwater or lake connection',
            'original 30 m sections are samples, no continuous wet connectivity certified',
            'no delta geometry or final map; not a game-delta-v1 product']}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
