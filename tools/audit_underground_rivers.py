"""Consolidated audit_underground_rivers implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i44_argparse
import json as _i44_json
import math as _i44_math
from pathlib import Path as _i44_Path
import sys as _i44_sys
import time as _i44_time
import numpy as _i44_np
from terrain_pipeline.common_infra import publish_bytes as _i44_publish_bytes
from tools.hybrid_cave_saved_audit import Solid as _i44_Solid
from tools.hybrid_cave_saved_audit import boolean_evidence as _i44_boolean_evidence
from tools.hybrid_cave_saved_audit import check_memory as _i44_check_memory
from tools.hybrid_cave_saved_audit import checked_path as _i44_checked_path
from tools.hybrid_cave_saved_audit import compare as _i44_compare
from tools.hybrid_cave_saved_audit import digest as _i44_digest
from tools.hybrid_cave_saved_audit import file_sha256 as _i44_file_sha256
from tools.hybrid_cave_saved_audit import read as _i44_read
from tools.hybrid_cave_saved_audit import require as _i44_require
from tools.hybrid_cave_saved_audit import saved_air_route as _i44_saved_air_route
from tools.td_shared_channel_fine_saved_audit import check_identity as _i44_check_identity
CATEGORY = 'C'
ROOT = _i44_Path(__file__).resolve().parents[1]
_i44_sys.path.insert(0, str(ROOT))
SCHEMA = 'td-underground-preview-saved-evidence-audit-v1'
SOURCE_INDEX_SHA = 'd7b971d28f07ff457776e0ce65ff8d583a4d1f70e50cbb3bdaad8e4909679fd6'
SOURCE_AUDIT_SHA = '703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364'
FLAGS = ('hydraulic_solved', 'full_network_verified', 'natural_outlet_certified')

def check_capabilities(record):
    _i44_require(set(record['capabilities']) == set(FLAGS) and all((record['capabilities'][flag] is False for flag in FLAGS)), 'unverified capability promoted')

def check_saved_geometry(preview, rock, source_vdm):
    """Verify saved relationships before independently replaying bounded Boolean evidence."""
    _i44_check_identity(preview)
    _i44_require(preview['schema'] == 'td-underground-river-preview-v1' and preview['status'] == 'geometry_checked', 'preview schema/status differs')
    check_capabilities(preview)
    _i44_require(preview['water'] is None, 'unverified water supplied')
    checks = preview['geometry_checks']
    _i44_require(checks['independent_audit_passed'] is False and checks['complete_portal_certified'] is False, 'producer certification promoted')
    origin = _i44_np.asarray(preview['origin_xyz_m'], float)
    _i44_compare(origin, rock['local_origin_xyz_m'], 'source rock origin', atol=0.0)
    _i44_require(set(preview['meshes']) == {'rock_before', 'rock_after', 'removed', 'cutter'}, 'four saved solids required')
    for key in ('vertices_local_xyz_m', 'triangles'):
        _i44_require(preview['meshes']['rock_before'][key] == rock[key], 'source rock changed')
    stations = preview['stations']
    source_stations = source_vdm['stations']
    _i44_require(9 <= len(stations) == len(source_stations) <= 33, 'station census differs')
    _i44_require([s['station_id'] for s in stations] == [s['station_id'] for s in source_stations] and len({s['station_id'] for s in stations}) == len(stations), 'station IDs differ')
    vdm = preview['vdm']
    reference, displacement, derived = (_i44_np.asarray(vdm[key], float) for key in ('reference_local_xyz_m', 'displacement_xyz_m', 'derived_local_xyz_m'))
    expected_reference = _i44_np.concatenate([s['reference_ring_xyz_m'] for s in source_stations]) - origin
    _i44_compare(reference, expected_reference, 'source VDM reference', atol=1e-10)
    _i44_compare(reference + displacement, derived, 'VDM displacement', atol=1e-10)
    cutter = preview['meshes']['cutter']
    _i44_compare(derived, cutter['vertices_local_xyz_m'], 'VDM cutter vertices', atol=1e-10)
    _i44_require(vdm['triangles'] == cutter['triangles'] == source_vdm['triangles'], 'VDM sweep topology differs')
    rings = [_i44_np.asarray(s['ring_local_xyz_m'], float) for s in stations]
    for ring, source in zip(rings, source_stations):
        _i44_require(ring.shape == _i44_np.asarray(source['derived_ring_xyz_m']).shape, 'station ring shape differs')
    _i44_compare(_i44_np.concatenate(rings), derived, 'stations and VDM', atol=1e-10)
    for ordinal in (0, -1):
        _i44_compare(rings[ordinal], _i44_np.asarray(source_stations[ordinal]['derived_ring_xyz_m']) - origin, 'immutable portal ring', atol=1e-10)
        _i44_compare(stations[ordinal]['origin_local_xyz_m'], _i44_np.asarray(source_stations[ordinal]['origin_xyz_m']) - origin, 'immutable portal origin', atol=1e-10)
    _i44_require([p['kind'] for p in preview['portals']] == ['sink', 'spring'], 'portal census differs')
    for portal, ordinal in zip(preview['portals'], (0, -1)):
        _i44_compare(portal['position_local_xyz_m'], stations[ordinal]['origin_local_xyz_m'], 'portal station position', atol=0.0)
    centers = _i44_np.asarray([s['origin_local_xyz_m'] for s in stations], float)
    _i44_compare(preview['metrics']['length_m'], _i44_math.fsum(_i44_np.linalg.norm(_i44_np.diff(centers, axis=0), axis=1)), 'station length', atol=1e-08)
    path = _i44_np.asarray(checks['air_path_local_xyz_m'], float)
    _i44_require(path.shape == centers.shape, 'air path census differs')
    _i44_compare(checks['air_path_xyz_m'], path + origin, 'air path coordinate frame', atol=1e-10)
    _i44_compare(path[:, [0, 2]], centers[:, [0, 2]], 'air path station binding', atol=1e-10)
    for point, center, ring, source in zip(path, centers, rings, source_stations):
        floor = ring[:source['floor_vertex_count']]
        offsets = (floor[:, [0, 2]] - center[[0, 2]]) @ _i44_np.asarray(source['transverse_unit_xz'])
        _i44_require(_i44_np.all(_i44_np.diff(offsets) > 0.0) and offsets[0] <= 0.0 <= offsets[-1], 'unordered station floor')
        _i44_require(_i44_np.interp(0.0, offsets, floor[:, 1]) < point[1] < ring[-2:, 1].min(), 'air waypoint outside station interior')
    segments = checks['air_path_segments']
    _i44_require(len(segments) == checks['air_segment_count'] == len(path) - 1, 'air segment census differs')
    for ordinal, segment in enumerate(segments):
        _i44_compare(segment['from_xyz_m'], path[ordinal] + origin, 'air segment start', atol=1e-10)
        _i44_compare(segment['to_xyz_m'], path[ordinal + 1] + origin, 'air segment end', atol=1e-10)
        _i44_require(segment['rock_after_hits'] == [], 'saved blocked air route')
    openings = checks['portal_opening_witnesses']
    _i44_require(set(openings) == {'sink', 'spring'}, 'two opening witnesses required')
    ids = [s['station_id'] for s in stations]
    opening_segments = []
    for kind in ('sink', 'spring'):
        witness = openings[kind]
        ordinal = ids.index(witness['station_id'])
        _i44_require(0 < ordinal < len(ids) // 2 if kind == 'sink' else len(ids) // 2 < ordinal < len(ids) - 1, 'opening attached to wrong portal half')
        _i44_compare(witness['inside_xyz_m'], path[ordinal] + origin, 'opening air path binding', atol=1e-10)
        outside = _i44_np.asarray(witness['above_xyz_m'], float) - origin
        _i44_compare(outside[[0, 2]], path[ordinal, [0, 2]], 'opening vertical probe', atol=1e-10)
        _i44_require(outside[1] > path[ordinal, 1], 'opening probe not above interior')
        opening_segments.append((outside, path[ordinal]))
    solids = {name: _i44_Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], name) for name, mesh in preview['meshes'].items()}
    boolean = _i44_boolean_evidence(solids['rock_before'], solids['cutter'], solids['rock_after'], solids['removed'])
    _i44_compare(preview['metrics']['excavated_rock_m3'], boolean['excavated_volume_m3'], 'excavated material', atol=1e-07, rtol=1e-09)
    residual = boolean['rock_volume_m3'] - boolean['actual_rock_volume_m3'] - boolean['excavated_volume_m3']
    _i44_compare(preview['metrics']['material_residual_m3'], residual, 'material residual', atol=1e-07)
    air = _i44_saved_air_route(solids['rock_before'], solids['cutter'], solids['rock_after'], path, opening_segments)
    return {'actual_boolean': boolean, 'actual_air_route': air, 'source_rock_unchanged': True, 'immutable_endpoint_rings_verified': True, 'saved_vdm_station_cutter_binding_verified': True}

def audit(index_pin):
    started = _i44_time.perf_counter()
    index = _i44_read(index_pin)
    _i44_require(index['schema'] == 'td-underground-river-preparation-v1' and index['status'] == 'geometry_checked' and (index['rejection_reasons'] == []), 'successful preparation required')
    check_capabilities(index)
    preview = _i44_read(index['preview'])
    _i44_require(preview['parameters'] == index['parameters'] and preview['source_pins'] == index['parents'] and (preview['metrics'] == index['metrics']), 'index/preview linkage differs')
    parents = index['parents']
    _i44_require(parents['geometry03_index']['sha256'] == SOURCE_INDEX_SHA and parents['geometry03_audit']['sha256'] == SOURCE_AUDIT_SHA, 'fixed source pins differ')
    source_index, source_audit = (_i44_read(parents['geometry03_index']), _i44_read(parents['geometry03_audit']))
    _i44_require(source_audit['status'] == 'passed' and (not source_audit.get('errors')) and (source_audit['geometry_sha256'] == source_index['geometry']['sha256']), 'source audit linkage differs')
    _i44_require(parents['geometry03'] == source_index['geometry'] and parents['graph'] == source_index['graph'] and (parents['rock_before'] == source_index['artifacts']['rock_before']) and (parents['vdm'] == source_index['artifacts']['vdm']), 'source artifacts substituted')
    for pin in parents.values():
        _i44_checked_path(pin)
    evidence = check_saved_geometry(preview, _i44_read(parents['rock_before']), _i44_read(parents['vdm']))
    result = {'schema': SCHEMA, 'status': 'passed', 'index': index_pin, 'preview': index['preview'], 'parents': parents, 'evidence': evidence, 'capabilities': {key: False for key in FLAGS}, 'scope': 'saved solids, material, fixed endpoints, VDM binding and air polyline only', 'continuous_roof_cover_verified': False, 'complete_portal_certified': False, 'seed_recipe_replayed': False, 'water': None, 'resource': {'solver_calls': 0, 'producer_calls': 0, 'elapsed_s': _i44_time.perf_counter() - started, 'peak_rss_bytes': _i44_check_memory()}, 'audit_code_sha256': {name: _i44_file_sha256(ROOT / name) for name in ('tools/audit_underground_rivers.py', 'tools/hybrid_cave_saved_audit.py', 'tools/td_shared_channel_fine_saved_audit.py')}}
    result['identity_sha256'] = _i44_digest(result)
    return result

def _entry_audit_underground_river_preview():
    parser = _i44_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=_i44_Path, required=True)
    parser.add_argument('--index-sha256', required=True)
    parser.add_argument('--output', type=_i44_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i44_require(output.is_relative_to(ROOT / 'verification') and (not output.exists()), 'new verification file required')
    pin = {'path': str(args.index.resolve()), 'sha256': args.index_sha256}
    try:
        result = audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
        result = {'schema': SCHEMA, 'status': 'refused', 'index': pin, 'errors': [str(error)]}
        result['identity_sha256'] = _i44_digest(result)
    _i44_publish_bytes(output, _i44_json.dumps(result, sort_keys=True, indent=2, allow_nan=False).encode('utf-8'))
    print(_i44_json.dumps({'status': result['status'], 'output': str(output), 'errors': result.get('errors', [])}))
    return 0 if result['status'] == 'passed' else 2

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'audit-underground-river-preview': '_entry_audit_underground_river_preview'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('command', choices=tuple(commands))
        parsed, values = parser.parse_known_args(values)
        selected = parsed.command
    function = globals()[commands[selected]]
    previous = sys.argv
    try:
        sys.argv = [previous[0]] + values
        return function(values) if inspect.signature(function).parameters else function()
    finally:
        sys.argv = previous
if __name__ == '__main__':
    main()
