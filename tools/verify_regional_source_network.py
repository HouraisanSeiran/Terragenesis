"""Stable full-region static channel polylines; not dynamic surface fluxes."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.common_infra import file_sha256
from tools.verify_mountain_source_adapter import write_json


def export_network(source):
    arrays = source['arrays']
    receiver = arrays['receiver'].ravel()
    channel = arrays['channel_mask'].ravel()
    lakes = arrays['diagnostic_lake_id'].ravel()
    height = arrays['height_m'].ravel()
    cells = np.flatnonzero(channel)
    incoming = np.zeros(65536, np.int64)
    donors = cells[receiver[cells] >= 0]
    np.add.at(incoming, receiver[donors], 1)
    origins = source['metadata']['origin_m_xz']
    digest = source['identity_sha256']
    node_cells = set()
    for cell in cells:
        target = int(receiver[cell])
        if incoming[cell] != 1 or target < 0 or lakes[cell] > 0:
            node_cells.add(int(cell))
        if target >= 0 and lakes[cell] != lakes[target]:
            node_cells.add(int(cell))
            node_cells.add(target)
    segments = []
    covered = set()
    for start in sorted(node_cells):
        target = int(receiver[start])
        if target < 0 or not channel[start]:
            continue
        path = [start, target]
        while path[-1] not in node_cells and receiver[path[-1]] >= 0:
            path.append(int(receiver[path[-1]]))
        for donor, successor in zip(path, path[1:]):
            if successor != receiver[donor] or donor in covered:
                raise ValueError('static channel edge repeated or not receiver')
            covered.add(donor)
        elevations = height[path]
        uphill = np.diff(elevations) > 1e-9
        coordinates = [[float(origins[0] + cell % 256 * 30), float(height[cell]),
                        float(origins[1] + cell // 256 * 30)] for cell in path]
        segments.append({'id': f'{digest}:reach:{start}:{path[-1]}', 'start_cell': start,
            'end_cell': path[-1], 'cell_flat': path, 'coordinates_xyz_m': coordinates,
            'length_m': (len(path) - 1) * 30., 'H0_uphill_edges': int(uphill.sum()),
            'max_H0_uphill_m': float(np.maximum(np.diff(elevations), 0).max()),
            'crosses_static_lake': bool((lakes[path] > 0).any()),
            'static_lake_ids': np.unique(lakes[path][lakes[path] > 0]).tolist(),
            'bed_modified': False,
            'hydraulic_connectivity_certified': False,
            'route_status': 'uphill_H0_fillspill_planning_only' if uphill.any() else 'H0_nonuphill_static_plan_not_dynamic_certification'})
    expected = set(int(cell) for cell in donors)
    if covered != expected:
        raise ValueError('all selected channel receiver edges must be covered exactly once')
    nodes = []
    for cell in sorted(node_cells):
        flags = []
        if incoming[cell] == 0:
            flags.append('source')
        if incoming[cell] > 1:
            flags.append('confluence')
        if receiver[cell] < 0:
            flags.append('engineering_boundary_outlet')
        if lakes[cell] > 0:
            flags.append('static_depression_connection')
        nodes.append({'id': f'{digest}:node:{cell}', 'cell_flat': cell, 'flags': flags,
            'coordinates_xyz_m': [float(origins[0] + cell % 256 * 30), float(height[cell]),
                                  float(origins[1] + cell // 256 * 30)]})
    return {'schema': 'regional-static-channel-network-v1', 'source_identity': digest,
        'channel_area_threshold_m2': source['metadata']['channel_area_threshold_m2'],
        'channel_cells': len(cells), 'covered_channel_edges': len(covered), 'nodes': nodes, 'segments': segments,
        'H0_uphill_channel_edges': sum(segment['H0_uphill_edges'] for segment in segments),
        'max_H0_channel_uphill_m': max((segment['max_H0_uphill_m'] for segment in segments), default=0.),
        'lake_label_semantics': '0 non-lake; positive IDs are potential fullspill components, not actual initial water',
        'scope': 'full65536 regional diagnostic overlay; static D4 fullspill receiver is not dynamic flow direction',
        'unresolved': ['no accepted subcell fine channel sections', 'H0 uphill edges retained, not silently carved',
                       'static depression routing not unified initial lake stage', 'dynamic reverse flow declared by B surface artifact']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', required=True, type=Path)
    args = parser.parse_args()
    meta = json.loads((args.source_directory / 'manifest.json').read_text(encoding='utf-8'))
    source = load_source(args.source_directory / 'source.npz', expected_sha256=meta['source_sha256'])
    result = export_network(source)
    destination = ROOT / 'verification/regional-source-network' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    write_json(destination / 'network.json', result)
    write_json(destination / 'manifest.json', {'network_sha256': file_sha256(destination / 'network.json'),
        'source_manifest_sha256': file_sha256(args.source_directory / 'manifest.json'),
        'source_identity': source['identity_sha256'], 'exporter_sha256': file_sha256(Path(__file__))})
    print(json.dumps({'directory': str(destination), 'channel_cells': result['channel_cells'],
                      'nodes': len(result['nodes']), 'segments': len(result['segments'])}))


if __name__ == '__main__':
    main()
