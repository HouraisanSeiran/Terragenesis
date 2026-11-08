"""Diagnostic-only declared rain conversion, explicitly not a river-chain product."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from terrain_pipeline.artifacts.contracts import digest
from terrain_pipeline.common_infra import checked_archive, file_sha256


def build_diagnostic_candidate(records, parameters, destination, *, source_kind, rain_mm_h):
    from tools.native_30m_resources import observed_call, active_budget
    from tools.native_30m_sources import validate_request, compute_source_request
    from terrain_pipeline.surface_rivers.native_30m_source import load_native_window, build_strict_topology
    from terrain_pipeline.surface_rivers.metric_network_discharge_product import build_discharge_product, save_discharge_product
    if type(rain_mm_h) not in (int, float) or not math.isfinite(rain_mm_h) or rain_mm_h < 0:
        raise ValueError('diagnostic_rain_rate')
    active_budget().check_window(records, parameters['shape_zx'], 1)
    if source_kind == 'td_pages':
        source = observed_call('native_source', load_native_window, records,
            origin_native_xz=parameters['origin_native_xz'], shape_zx=parameters['shape_zx'], world_seed=20261020)
    elif source_kind == 'saved_assembly' and len(records) == 1:
        from tools.native_30m_saved_source import load_saved_assembly
        source = observed_call('saved_assembly_source', load_saved_assembly, records[0], parameters)
    else:
        raise ValueError('source_kind_not_supported')
    top = observed_call('strict_topology', build_strict_topology, source['field'], source['resolved_mask'],
        origin_native_xz=parameters['origin_native_xz'], world_seed=20261020)
    local = np.where(top['valid_mask'], rain_mm_h / 1000. / 3600. * 30.**2, 0.).astype(np.float64)
    product = observed_call('diagnostic_discharge', build_discharge_product, top['receiver'], local,
        top['valid_mask'], top['terminal_kind'], top['upstream_unknown_mask'],
        origin_native_cells=parameters['origin_native_xz'], world_seed=20261020, interval_seconds=[0., 3600.],
        source_sha256=source['assembly_digest'], forcing_semantics='declared rain conversion only; no soil bucket, ET or storage')
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir()
    with (destination/'source.npz').open('xb') as stream:
        np.savez(stream, field=source['field'], resolved_mask=source['resolved_mask'],
                 origin_native_xz=np.asarray(parameters['origin_native_xz'], np.int64))
        stream.flush()
        os.fsync(stream.fileno())
    save_discharge_product(destination/'data', product)
    body = {'schema': 'native-30m-diagnostic-only-v1', 'profile': 'diagnostic-only', 'is_product': False,
            'role': 'native_30m_diagnostic_only_unvalidated', 'rain_semantics': 'declared_conversion',
            'parameters': {'world_seed': 20261020, 'spacing_m': 30.,
                'origin_native_xz': list(parameters['origin_native_xz']), 'shape_zx': list(parameters['shape_zx']),
                'rain_mm_h': rain_mm_h, 'interval_seconds': [0., 3600.]},
            'source_kind': source_kind, 'source_records': source['source_records'],
            'assembly_identity_sha256': source['assembly_digest'],
            'diagnostic_identity_sha256': product['identity_sha256'],
            'not_computed': ['soil_bucket', 'design_q', 'channel_section', 'hydraulics', 'sediment', 'bed'],
            'files': {name: file_sha256(destination/name) for name in
                      ('source.npz', 'data/manifest.json', 'data/arrays.npz')}}
    from tools.publish_native_30m_bundle import _write_json_synced, _code_pins
    body['source_code_identity'] = _code_pins()
    record = dict(body, identity_sha256=digest(body))
    _write_json_synced(destination/'diagnostic.json', record)
    load_diagnostic(destination)
    return record


def load_diagnostic(directory):
    from tools.native_30m_bundle_reader import _jread, _checkpath
    from terrain_pipeline.surface_rivers.metric_network_discharge_product import load_discharge_product
    root = Path(directory).absolute()
    _checkpath(root, isdir_ok=True)
    if {p.name for p in root.iterdir()} != {'diagnostic.json', 'source.npz', 'data'}:
        raise ValueError('diagnostic_only_entries')
    for name in ('diagnostic.json', 'source.npz'):
        _checkpath(root/name)
    _checkpath(root/'data', isdir_ok=True)
    record = _jread(root/'diagnostic.json')
    body = {k: v for k, v in record.items() if k != 'identity_sha256'}
    if (record.get('schema') != 'native-30m-diagnostic-only-v1' or record.get('profile') != 'diagnostic-only' or
            record.get('is_product') is not False or record.get('rain_semantics') != 'declared_conversion' or
            record.get('role') != 'native_30m_diagnostic_only_unvalidated' or
            record.get('source_kind') not in ('td_pages', 'saved_assembly') or
            record.get('not_computed') != ['soil_bucket', 'design_q', 'channel_section', 'hydraulics', 'sediment', 'bed'] or
            digest(body) != record.get('identity_sha256')):
        raise ValueError('diagnostic_only_identity_or_semantics')
    if set(record['files']) != {'source.npz', 'data/manifest.json', 'data/arrays.npz'}:
        raise ValueError('diagnostic_only_file_whitelist')
    for name, sha in record['files'].items():
        if file_sha256(root/name) != sha:
            raise ValueError('diagnostic_only_file_pin')
    p = record['parameters']
    shape = p['shape_zx']
    origin = p['origin_native_xz']
    if (not isinstance(shape, list) or len(shape) != 2 or any(type(v) is not int or not 2 <= v <= 1337 for v in shape) or
            not isinstance(origin, list) or len(origin) != 2 or any(type(v) is not int for v in origin) or
            type(p['world_seed']) is not int or p['world_seed'] != 20261020):
        raise ValueError('diagnostic_only_parameter_budget')
    child_manifest = _jread(root/'data/manifest.json')
    if child_manifest['metadata']['shape_zx'] != shape:
        raise ValueError('diagnostic_only_child_shape_budget')
    product = load_discharge_product(root/'data')
    if product['identity_sha256'] != record['diagnostic_identity_sha256']:
        raise ValueError('diagnostic_only_child_identity')
    source = checked_archive(root/'source.npz', expected_sha256=record['files']['source.npz'], max_bytes=512*1024**2)
    p, meta = record['parameters'], product['metadata']
    if (p['world_seed'] != 20261020 or p['spacing_m'] != 30. or p['interval_seconds'] != [0., 3600.] or
            meta['origin_native_cells'] != p['origin_native_xz'] or meta['shape_zx'] != p['shape_zx'] or
            meta['world_seed'] != p['world_seed'] or meta['spacing_m'] != p['spacing_m'] or
            meta['source_sha256'] != record['assembly_identity_sha256'] or
            meta['interval_seconds'] != p['interval_seconds']):
        raise ValueError('diagnostic_only_source_binding')
    rain = p['rain_mm_h']
    if type(rain) not in (int, float) or not math.isfinite(rain) or rain < 0:
        raise ValueError('diagnostic_rain_rate')
    shape = tuple(p['shape_zx'])
    if (set(source) != {'field', 'resolved_mask', 'origin_native_xz'} or
            source['field'].dtype != np.float64 or source['field'].shape != shape or
            source['resolved_mask'].dtype != np.bool_ or source['resolved_mask'].shape != shape or
            source['origin_native_xz'].dtype != np.int64 or source['origin_native_xz'].shape != (2,) or
            not np.array_equal(source['origin_native_xz'], p['origin_native_xz']) or
            not np.isfinite(source['field'][source['resolved_mask']]).all() or np.isinf(source['field']).any()):
        raise ValueError('diagnostic_source_array')
    top = product['arrays']
    expected = np.where(source['resolved_mask'], rain/1000./3600.*900., 0.)
    if not np.array_equal(top['valid_mask'], source['resolved_mask']) or not np.array_equal(top['local_q_m3_s'], expected):
        raise ValueError('diagnostic_declared_conversion_binding')
    from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
    derived = build_strict_topology(source['field'], source['resolved_mask'],
        origin_native_xz=tuple(int(v) for v in source['origin_native_xz']))
    for key in ('receiver', 'terminal_kind', 'upstream_unknown_mask'):
        if not np.array_equal(derived[key], top[key]):
            raise ValueError('diagnostic_source_topology_binding')
    return {'manifest': record, 'arrays': {'source.npz': source, 'topology.npz': dict(top)},
            'diagnostic': product, 'directory': root}


def publish_diagnostic(candidate, destination):
    from tools.native_30m_bundle_reader import _checkpath
    source = load_diagnostic(candidate)
    target = Path(destination).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.'+target.name+'-', dir=target.parent))
    try:
        for entry in source['directory'].iterdir():
            if entry.is_dir():
                shutil.copytree(entry, staging/entry.name)
            else:
                shutil.copyfile(entry, staging/entry.name)
        verified = load_diagnostic(staging)
        for path in staging.rglob('*'):
            if path.is_file():
                with path.open('rb+') as stream:
                    os.fsync(stream.fileno())
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)
        os.rename(staging, target)
        return dict(verified['manifest'], cold_read_verified_now=True)
    except Exception as exc:
        from tools.publish_native_30m_bundle import _write_json_synced
        _write_json_synced(staging/'failure.json', {'success': False, 'error': str(exc)})
        raise
