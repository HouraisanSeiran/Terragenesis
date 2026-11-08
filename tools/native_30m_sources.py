"""Pinned source-only requests, deliberately independent of old derived directories."""
import copy
import json
import math
import os
from pathlib import Path

from terrain_pipeline.common_infra import file_sha256

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'native-30m-source-request-v1'
STORM = [1, 2, 3, 4, 5, 6, 7, 8, 8, 7, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 2, 1, 1, 1] + [0]*48
PARAMETER_KEYS = {'world_seed', 'origin_native_xz', 'shape_zx', 'coupled_intervals',
                  'resample_stride', 'storm_rain_mm_h', 'dt_s', 'infiltration_capacity_mm_h'}


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_request(request):
    base_keys = {'schema', 'parameters', 'source_records', 'expected_numerical_identity_sha256'}
    if not isinstance(request, dict):
        raise ValueError('source_request_fields')
    if request.get('schema') == SCHEMA:
        if set(request) != base_keys:
            raise ValueError('source_request_fields')
    elif request.get('schema') == 'native-30m-source-request-v2':
        if set(request) != base_keys | {'source_kind'} or request['source_kind'] != 'saved_assembly':
            raise ValueError('source_request_kind')
    elif request.get('schema') in ('native-30m-source-request-v3', 'native-30m-source-request-v4'):
        if set(request) != base_keys | {'source_kind'} or request['source_kind'] not in ('td_pages', 'saved_assembly'):
            raise ValueError('source_request_kind')
    else:
        raise ValueError('source_request_schema')
    expected = request['expected_numerical_identity_sha256']
    if expected is not None and not _sha(expected):
        raise ValueError('source_request_expected_identity')
    p = request['parameters']
    custom = request['schema'] in ('native-30m-source-request-v3', 'native-30m-source-request-v4')
    allowed_parameter_keys = PARAMETER_KEYS | ({'runoff_parameters'} if custom else set())
    if request['schema'] == 'native-30m-source-request-v4':
        allowed_parameter_keys |= {'terminal_native_xz', 'selection_parameters'}
    if not isinstance(p, dict) or not PARAMETER_KEYS.issubset(p) or not set(p).issubset(allowed_parameter_keys):
        raise ValueError('source_request_parameter_fields')
    if type(p['world_seed']) is not int or p['world_seed'] != 20261020:
        raise ValueError('unsupported_scenario')
    origin, shape = p['origin_native_xz'], p['shape_zx']
    if not isinstance(origin, list) or len(origin) != 2 or any(type(v) is not int for v in origin):
        raise ValueError('source_request_origin')
    if (not isinstance(shape, list) or len(shape) != 2 or
            any(type(v) is not int or not 2 <= v <= 1337 for v in shape)):
        raise ValueError('budget_window_dimension')
    if type(p['coupled_intervals']) is not int or not 1 <= p['coupled_intervals'] <= 12:
        raise ValueError('budget_coupled_intervals')
    if type(p['resample_stride']) is not int or p['resample_stride'] < 1:
        raise ValueError('source_request_stride')
    if request['schema'] == 'native-30m-source-request-v4':
        from tools.native_30m_selection_contract import selection_arguments
        selection_arguments(p)
    if custom:
        from tools.native_30m_event_config import event_configuration
        rain, rp = event_configuration(p['storm_rain_mm_h'], p.get('runoff_parameters',
                                      {'infiltration_capacity_mm_h': p['infiltration_capacity_mm_h']}))
        if (type(p['dt_s']) not in (int, float) or p['dt_s'] != 3600. or
                type(p['infiltration_capacity_mm_h']) not in (int, float) or
                p['infiltration_capacity_mm_h'] != rp.infiltration_capacity_mm_h):
            raise ValueError('event_parameter_binding')
    else:
        for key, required in (('dt_s', 3600.0), ('infiltration_capacity_mm_h', 2.0)):
            value = p[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value != required:
                raise ValueError('unsupported_scenario:' + key)
        rain = p['storm_rain_mm_h']
        if (not isinstance(rain, list) or len(rain) != 72 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in rain) or rain != STORM):
            raise ValueError('unsupported_scenario:storm_rain_mm_h')
    records = request['source_records']
    if not isinstance(records, list) or not 1 <= len(records) <= 64:
        raise ValueError('budget_pages')
    if request.get('source_kind') == 'saved_assembly' and len(records) != 1:
        raise ValueError('saved_assembly_requires_one_source')
    paths = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {'path', 'sha256'}:
            raise ValueError('source_request_page_fields')
        path = record['path']
        if not isinstance(path, str) or not path or '\x00' in path or path in paths:
            raise ValueError('source_request_page_path')
        paths.add(path)
        if not _sha(record['sha256']):
            raise ValueError('source_request_page_pin')


def source_request_from_candidate(env):
    request = {'schema': SCHEMA, 'parameters': copy.deepcopy(env['manifest']['parameters']),
               'source_records': [{k: r[k] for k in ('path', 'sha256')}
                                  for r in env['manifest']['source_records']],
               'expected_numerical_identity_sha256': env['manifest']['identity_sha256']}
    records = env['manifest']['source_records']
    kind = ('saved_assembly' if len(records) == 1 and records[0].get('schema') == 'native-30m-saved-assembly-v1' else 'td_pages')
    from tools.native_30m_event_config import uses_custom_event
    if 'terminal_native_xz' in request['parameters'] or 'selection_parameters' in request['parameters']:
        request.update(schema='native-30m-source-request-v4', source_kind=kind)
    elif uses_custom_event(request['parameters']):
        request.update(schema='native-30m-source-request-v3', source_kind=kind)
    elif kind == 'saved_assembly':
        request.update(schema='native-30m-source-request-v2', source_kind='saved_assembly')
    validate_request(request)
    return request


def save_source_request(path, request):
    validate_request(request)
    payload = json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(payload) > 1048576:
        raise ValueError('source_request_bytes')
    with open(path, 'xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return file_sha256(path)


def load_source_request(path, *, expected_sha256):
    from tools.native_30m_bundle_reader import _jread, _checkpath
    path = Path(path).absolute()
    _checkpath(path)
    if not _sha(expected_sha256):
        raise ValueError('source_request_external_pin_required')
    if path.stat().st_size > 1048576:
        raise ValueError('source_request_bytes')
    if file_sha256(path) != expected_sha256:
        raise ValueError('source_request_pin_mismatch')
    request = _jread(path)
    validate_request(request)
    # Relative page paths retain their original spelling for deterministic source identity.
    # Their base is always the project root, never the directory of a former release.
    for record in request['source_records']:
        page = Path(record['path'])
        if not page.is_absolute():
            page = ROOT / page
        _checkpath(page)
        if file_sha256(page) != record['sha256']:
            raise ValueError('pin_mismatch:' + record['path'])
    return request


def compute_source_request(records, parameters, expected_identity=None):
    defaults = {'world_seed': 20261020, 'origin_native_xz': [42173, 42874], 'shape_zx': [1337, 1337],
                'coupled_intervals': 12, 'resample_stride': 3, 'storm_rain_mm_h': list(STORM),
                'dt_s': 3600., 'infiltration_capacity_mm_h': 2.}
    defaults.update(copy.deepcopy(parameters))
    defaults['origin_native_xz'] = list(defaults['origin_native_xz'])
    defaults['shape_zx'] = list(defaults['shape_zx'])
    request = {'schema': SCHEMA, 'parameters': defaults, 'source_records': copy.deepcopy(records),
               'expected_numerical_identity_sha256': expected_identity}
    from tools.native_30m_event_config import uses_custom_event
    if 'terminal_native_xz' in defaults or 'selection_parameters' in defaults:
        request.update(schema='native-30m-source-request-v4', source_kind='td_pages')
    elif uses_custom_event(defaults):
        request.update(schema='native-30m-source-request-v3', source_kind='td_pages')
    validate_request(request)
    return request
