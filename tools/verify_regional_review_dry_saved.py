"""Read-only real dry-state handoff; never advances surface or invents water."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.regional_surface_review import export_review, read_bounded_json
from terrain_pipeline.regional_hydraulics_mesh import water_columns, validate_water_columns


def write_json(path, value):
    publish_bytes(path, json.dumps(value, allow_nan=False, indent=2).encode('utf-8'))


def main():
    directory = ROOT / 'verification/regional-hydraulics/full-20261001T101153406000Z/dry'
    manifest_sha = file_sha256(directory / 'manifest.json')
    manifest = read_bounded_json(directory / 'manifest.json', expected_sha256=manifest_sha)
    for name in ('states.json', 'states.npz', 'binding.json'):
        if file_sha256(directory / name) != manifest['artifacts'][name]:
            raise ValueError('saved solver artifact hash mismatch')
    metadata = read_bounded_json(directory / 'states.json', expected_sha256=manifest['artifacts']['states.json'])['metadata']
    if metadata['status'] != 'completed' or metadata['committed_time_s'] != 259200 or metadata['failure'] is not None:
        raise ValueError('complete real 72-hour dry case required')
    source = load_source(ROOT / 'verification/regional-source/run-20261001T095258008789Z/source.npz',
        expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
    if source['identity_sha256'] != metadata['source_identity']:
        raise ValueError('saved source mismatch')
    output = ROOT / 'verification/regional-review-dry' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    inputs = output / 'saved-input'
    inputs.mkdir(parents=True, exist_ok=False)
    snapshots = []
    with np.load(directory / 'states.npz', allow_pickle=False) as saved:
        times, depths = saved['time_s'], saved['depth_m']
        if (times.ndim != 1 or len(times) > 50 or depths.shape != (len(times), 256, 256) or
                times[0] != 0 or times[-1] != 259200 or not (np.diff(times) > 0).all() or
                not np.isfinite(depths).all() or np.any(depths != 0)):
            raise ValueError('real saved dry states must be finite all-zero and time-bound')
        for step, time in enumerate(times):
            packet = water_columns(source['arrays']['height_m'], depths[step], spacing_m=30.,
                origin_m_xz=source['metadata']['origin_m_xz'], source_identity=source['identity_sha256'], time_s=float(time))
            proof = validate_water_columns(packet, trusted_height=source['arrays']['height_m'],
                saved_depth=depths[step], source_identity=source['identity_sha256'])
            path = inputs / ('dry-%03d.json' % step)
            write_json(path, {'source_identity': source['identity_sha256'], 'vertices_xyz_m': [], 'triangles': []})
            snapshots.append({'time_s': float(time), 'path': path.name, 'sha256': file_sha256(path),
                'volume_m3': proof['volume_m3'], 'max_depth_m': 0.})
    index = {'schema': 'regional-saved-B-mesh-cases-v1', 'source_identity': source['identity_sha256'],
        'fixture_only': False, 'cases': [{'id': 'dry', 'model': metadata['schema'],
            'requested_time_s': 259200., 'committed_time_s': 259200., 'status': 'completed', 'failure': None,
            'B_validation': 'Real saved zero depth + static water-column validation; dry only, not wet-flow acceptance',
            'snapshots': snapshots}]}
    write_json(inputs / 'index.json', index)
    network = ROOT / 'verification/regional-source-network/run-20261001T095553240102Z/network.json'
    result = export_review(source, network, output / 'review', network_sha256=file_sha256(network),
        snapshot_index_path=inputs / 'index.json', snapshot_index_sha256=file_sha256(inputs / 'index.json'))
    write_json(output / 'manifest.json', {'review': result, 'solver_manifest_sha256': manifest_sha,
        'solver_directory': str(directory.relative_to(ROOT)), 'states_sha256': manifest['artifacts']['states.npz'],
        'validation_scope': 'actual dry empty mesh only; no wet/tailwater physical acceptance',
        'source_sha256': {name: file_sha256(ROOT / name) for name in (
            'terrain_pipeline/regional_surface_review.py', 'terrain_pipeline/regional_hydraulics_mesh.py',
            'tools/verify_regional_review_dry_saved.py')},
        'files_sha256': {str(path.relative_to(output)): file_sha256(path) for path in output.rglob('*') if path.is_file()}})
    print(output)


if __name__ == '__main__':
    main()
