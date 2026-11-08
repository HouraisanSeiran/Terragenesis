"""Reference-bound pre-event inputs for the large delta tidal alternative."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = 'c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'
FILES = {'terrain': 'terrain-product-v2/terrain.npz', 'terrain_manifest': 'terrain-product-v2/manifest.json',
         'network': 'active-network-v12/network.npz', 'network_metrics': 'active-network-v12/metrics.json',
         'forcing': 'active-source-v1/forcing.npz', 'forcing_manifest': 'active-source-v1/manifest.json'}
BASE = Path('.scratch/large-delta-20261101')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def active_layer(original, formed, deposit, initial, ocean, valid, thickness_m=.25):
    """Return disjoint assumed bulk thicknesses and an absolute protected floor."""
    arrays = [np.asarray(a) for a in (original, formed, deposit, initial, ocean, valid)]
    if any(a.shape != arrays[0].shape for a in arrays) or not np.isfinite(thickness_m) or thickness_m < 0:
        raise ValueError('matching shapes and finite nonnegative thickness required')
    original, formed, deposit, initial, ocean, valid = arrays
    if not all(np.isfinite(a).all() for a in (original, formed, deposit, initial)):
        raise ValueError('finite bed and deposit required')
    cover = np.minimum(np.maximum(np.minimum(initial - original, deposit), 0.), thickness_m)
    cover = np.where(valid, cover, 0.)
    cut = (initial < np.minimum(formed, original) - 1.e-8) & (original <= 4.)
    channel = np.where(valid & cut, thickness_m - cover, 0.)
    marine = np.where(valid & ocean & ~cut & (original <= 4.), thickness_m - cover, 0.)
    return {'formation_cover_m': cover, 'marine_assumed_m': marine,
            'channel_assumed_m': channel, 'floor_m': initial - cover - marine - channel}


def _patch(xz, radius_m, origin, spacing, shape):
    x, z = np.rint((np.asarray(xz) - origin) / spacing).astype(int)
    r = int(np.ceil(radius_m / spacing))
    return [int(v) for v in (max(0, z-r), min(shape[0], z+r+1), max(0, x-r), min(shape[1], x+r+1))]


def prepare_source(output_dir, root=ROOT):
    root, output = Path(root).resolve(), Path(output_dir).resolve()
    paths = {k: root / BASE / v for k, v in FILES.items()}
    metadata = {k: json.loads(paths[k].read_text(encoding='utf-8')) for k in ('terrain_manifest', 'network_metrics', 'forcing_manifest')}
    if any(v['source_identity'] != IDENTITY or v.get('world_seed', 20261020) != 20261020 for v in metadata.values()):
        raise ValueError('source identity or seed mismatch')
    with np.load(paths['terrain']) as terrain, np.load(paths['network']) as network, np.load(paths['forcing']) as forcing:
        origin, spacing, shape = terrain['origin_xz_m'], float(terrain['spacing_m']), terrain['valid'].shape
        if shape != (2000, 2000) or not np.array_equal(origin, [-12570, -59040]) or spacing != 30:
            raise ValueError('unexpected native grid')
        if not np.array_equal(network['time_seconds'], forcing['time_seconds']) or not np.array_equal(network['source_interval_solid_m3'], forcing['interval_delivered_solid_m3']) or not np.array_equal(network['source_interval_water_m3'], forcing['interval_water_m3']):
            raise ValueError('event forcing mismatch')
        anchors = metadata['network_metrics']['outlet_world_xz_m']
        mouth_patches = [_patch(a, 3000, origin, spacing, shape) for a in anchors]
        coast = [min(p[0] for p in mouth_patches), max(p[1] for p in mouth_patches), min(p[2] for p in mouth_patches), max(p[3] for p in mouth_patches)]
        patches = {'mouth_radius_m': 3000, 'mouths_z0_z1_x0_x1': mouth_patches, 'coastal_band_z0_z1_x0_x1': coast,
                   'coastal_band_shape_zx': [coast[1]-coast[0], coast[3]-coast[2]]}
    output.mkdir(parents=True, exist_ok=True)
    import os
    references = {k: {'path': Path(os.path.relpath(p, output)).as_posix(), 'sha256': digest(p)} for k, p in paths.items()}
    if references['terrain']['sha256'] != metadata['network_metrics']['terrain_sha256'] or references['forcing']['sha256'] != metadata['network_metrics']['forcing_sha256']:
        raise ValueError('network source digest mismatch')
    manifest = {'schema': 'delta-tides-source-v1', 'source_identity': IDENTITY, 'world_seed': 20261020,
                'references': references, 'patches': patches, 'active_layer_thickness_m': .25,
                'formation_solid_m3': {'source': metadata['terrain_manifest']['source_solid_m3'], 'placed': metadata['terrain_manifest']['placed_solid_m3'], 'unused': metadata['terrain_manifest']['unused_solid_m3']},
                'construction_excavation': {k: metadata['network_metrics'][k] for k in ('deposit_excavation_bulk_m3', 'deposit_excavation_solid_m3', 'original_excavation_bulk_m3', 'original_excavation_solid_m3')},
                'external_water': 'unknown', 'external_sediment': 'unknown', 'forcing_use': 'one 30-day pre-event alternative; do not repeat',
                'section_columns': ['branch', 'sequence', 'x_m', 'z_m', 'bed_m', 'stage_m', 'analytic_width_m', 'analytic_depth_m']}
    path = output / 'source-manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return path


def load_source(manifest_path):
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    if manifest['schema'] != 'delta-tides-source-v1' or manifest['source_identity'] != IDENTITY:
        raise ValueError('invalid source manifest')
    refs = {k: (path.parent / v['path']).resolve() for k, v in manifest['references'].items()}
    for k, p in refs.items():
        if digest(p) != manifest['references'][k]['sha256']:
            raise ValueError(f'source digest mismatch: {k}')
    with np.load(refs['terrain']) as t, np.load(refs['network']) as n, np.load(refs['forcing']) as f:
        result = {'originalbed': t['originalbed'], 'formedbed': t['derivedbed'], 'deposit': t['deposit'],
                  'source_ocean': t['original_ocean'], 'valid': t['valid'], 'initial_bed_m': n['initial_channel_bed_m'],
                  'sections': n['initial_centerline_sections'], 'parent': n['parent'], 'leaf_indices': n['leaf_indices'],
                  'inlet_xz_m': n['inlet_hook_xz_m'], 'forcing': {k: f[k] for k in f.files},
                  'network': {k: n[k] for k in ('branch_width_m', 'branch_length_m', 'branch_depth_m', 'branch_q_m3_s')},
                  'manifest': manifest, 'metadata': {k: json.loads(refs[k].read_text(encoding='utf-8')) for k in ('terrain_manifest', 'network_metrics', 'forcing_manifest')}}
        origin, spacing = t['origin_xz_m'], float(t['spacing_m'])
        result['x_m'] = origin[0] + np.arange(t['valid'].shape[1]) * spacing
        result['z_m'] = origin[1] + np.arange(t['valid'].shape[0]) * spacing
    result['sea_anchors_xz_m'] = np.asarray(result['metadata']['network_metrics']['outlet_world_xz_m'])
    result['reach_segments'] = [result['sections'][result['sections'][:, 0] == i] for i in range(len(result['parent']))]
    result['active_layer'] = active_layer(result['originalbed'], result['formedbed'], result['deposit'], result['initial_bed_m'], result['source_ocean'], result['valid'], manifest['active_layer_thickness_m'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output_dir')
    args = parser.parse_args()
    print(prepare_source(args.output_dir))




