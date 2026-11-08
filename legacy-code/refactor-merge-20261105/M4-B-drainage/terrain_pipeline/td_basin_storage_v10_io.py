"""Pure externally pinned v10 pages/checkpoints; never imports execution kernels."""

import math
import re
import numpy as np
from terrain_pipeline.common_infra import identity, load_bundle, save_bundle

PROFILE = 'v10-unified-infiltration-SSPRK2-hour-pages-v1'
STATES = ('depth_m', 'soil_mm', 'fast_mm', 'slow_mm')
ERRORS = ('error_depth', 'error_soil', 'error_fast', 'error_slow')
LEDGERS = ('rain_volume_m3', 'rain_infiltration_m3', 'surface_infiltration_m3',
    'rain_excess_m3', 'soil_et_m3', 'surface_et_m3', 'local_release_m3', 'percolation_m3',
    'internal_net_m3', 'boundary_outflow_m3', 'storage_change_m3', 'balance_residual_m3',
    'infiltration_capacity_m3')
FLUX = ('face_forward_m3', 'face_reverse_m3', 'active_forward_s', 'active_reverse_s',
        'routed_volume_m3', 'wet_duration_s')
STATIC = ('height_m', 'valid_mask', 'face_cells', 'receiver', 'boundary_cells', 'boundary_width_m')


def _metadata(result):
    arrays, metadata = result['arrays'], result['metadata']
    if result['identity_sha256'] != identity(arrays, metadata) or metadata.get('profile') != PROFILE:
        raise ValueError('v10 profile/identity mismatch')
    physical = metadata.get('parameters', {})
    if physical.get('runoff') != [15.,150.,.15,1.,3600.,259200.] or physical.get('face_conductance_m_s') != .6 or physical.get('surface_evaporation_mm_h') != .15 or physical.get('forcing_profile') != 'v10-unified-rain-surface-infiltration-experimental-v1':
        raise ValueError('v10 complete physical parameters mismatch')
    origin = metadata.get('origin_m_xz')
    if not isinstance(origin,list) or len(origin)!=2 or any(type(value) not in (int,float) or not math.isfinite(value) for value in origin):
        raise ValueError('v10 native origin invalid')
    for key in ('forcing_identity', 'hierarchy_identity'):
        if re.fullmatch('[0-9a-f]{64}', metadata.get(key, '')) is None:
            raise ValueError('v10 external identity syntax invalid')
    for key in ('cells', 'faces', 'substeps', 'forcing_hour_offset'):
        if type(metadata.get(key)) is not int or metadata[key] < 0:
            raise ValueError('v10 integer counts required')
    for key in ('dt_s', 'substep_s', 'spacing_m', 'start_s', 'end_s', 'positivity_cfl'):
        if type(metadata.get(key)) not in (int, float) or not math.isfinite(metadata[key]):
            raise ValueError('v10 finite time/CFL required')
    if (metadata['dt_s'] != 3600 or metadata['substep_s'] <= 0 or metadata['spacing_m'] <= 0
            or metadata['start_s'] != metadata['forcing_hour_offset'] * 3600
            or metadata['end_s'] != metadata['start_s'] + 3600):
        raise ValueError('v10 hourly time alignment invalid')
    count = math.ceil(3600 / metadata['parameters']['substep_s'])
    if metadata['substeps'] != count or metadata['substep_s'] != 3600 / count:
        raise ValueError('v10 derived step count mismatch')
    if not 1 <= metadata['cells'] <= 250000 or count * metadata['faces'] > 6000000000:
        raise ValueError('v10 chunk work budget exceeded')
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError('v10 nonfinite arrays')
    return arrays, metadata


def validate_storage(result):
    arrays, metadata = _metadata(result)
    if metadata.get('schema') != 'td-v10-hour-page-v1' or set(arrays) != set(STATES + LEDGERS + FLUX + STATIC + ('rain_mm_h',)):
        raise ValueError('v10 page schema/arrays mismatch')
    cells, faces = metadata['cells'], metadata['faces']
    height = arrays['height_m']
    if height.ndim != 2 or height.size != cells or height.dtype != np.float64 or arrays['valid_mask'].shape != height.shape or arrays['valid_mask'].dtype != bool:
        raise ValueError('v10 grid/mask mismatch')
    valid = arrays['valid_mask'].ravel()
    links = arrays['face_cells']
    if links.shape != (faces, 2) or links.dtype != np.int64 or np.any((links < 0) | (links >= cells)):
        raise ValueError('v10 face indices invalid')
    rows, columns = np.divmod(links, height.shape[1])
    if np.any(abs(rows[:, 0]-rows[:, 1])+abs(columns[:, 0]-columns[:, 1]) != 1) or not valid[links].all():
        raise ValueError('v10 faces must be valid D4')
    boundary = arrays['boundary_cells']
    widths = arrays['boundary_width_m']
    if boundary.dtype != np.int64 or boundary.ndim != 1 or np.any((boundary < 0) | (boundary >= cells)) or widths.shape != boundary.shape or np.any(widths <= 0):
        raise ValueError('v10 boundary invalid')
    degree = np.bincount(links.ravel(), minlength=cells).astype(float)
    np.add.at(degree, boundary, widths/metadata['spacing_m'])
    cfl = float(degree.max(initial=0)) * .6 * metadata['substep_s'] / metadata['spacing_m']
    if cfl > 1 or cfl != metadata['positivity_cfl']:
        raise ValueError('v10 actual geometry CFL mismatch')
    for key in STATES:
        if arrays[key].shape != (2, cells) or np.any(arrays[key] < 0) or np.any(arrays[key][:, ~valid] != 0):
            raise ValueError('v10 state positivity/unknown invalid')
    for key in LEDGERS + ('rain_mm_h',):
        if arrays[key].shape != (1, cells) or np.any(arrays[key][:, ~valid] != 0):
            raise ValueError('v10 ledger/rain shape/unknown invalid')
        if key not in ('internal_net_m3', 'storage_change_m3', 'balance_residual_m3') and np.any(arrays[key] < 0):
            raise ValueError('v10 negative gross ledger')
    for key in FLUX:
        size = faces if key.startswith(('face_', 'active_')) else cells
        if arrays[key].shape != (size,) or np.any(arrays[key] < 0):
            raise ValueError('v10 flux shape/positivity invalid')
        if ('duration' in key or key.startswith('active_')) and np.any(arrays[key] > 3600 + 1e-8):
            raise ValueError('v10 activity exceeds page time')
    if arrays['receiver'].shape != (cells,) or arrays['receiver'].dtype != np.int64 or np.any((arrays['receiver'] < -1) | (arrays['receiver'] >= cells)):
        raise ValueError('v10 receiver invalid')
    rain = arrays['rain_volume_m3']
    if not np.allclose(rain, arrays['rain_infiltration_m3'] + arrays['rain_excess_m3'], rtol=1e-12, atol=1e-9):
        raise ValueError('v10 unique rain allocation failed')
    if np.any(arrays['rain_infiltration_m3'] + arrays['surface_infiltration_m3'] > arrays['infiltration_capacity_m3'] + 1e-8):
        raise ValueError('v10 infiltration capacity violated')
    signed = arrays['face_forward_m3'] - arrays['face_reverse_m3']
    net = np.bincount(links[:, 1], weights=signed, minlength=cells) - np.bincount(links[:, 0], weights=signed, minlength=cells)
    if not np.allclose(net, arrays['internal_net_m3'][0], rtol=1e-10, atol=1e-7):
        raise ValueError('v10 face divergence ledger mismatch')
    area = metadata['spacing_m']**2
    before = area*(arrays['depth_m'][0] + sum(arrays[key][0] for key in STATES[1:])/1000)
    after = area*(arrays['depth_m'][1] + sum(arrays[key][1] for key in STATES[1:])/1000)
    change = after-before
    residual = rain[0]+net-arrays['soil_et_m3'][0]-arrays['surface_et_m3'][0]-arrays['boundary_outflow_m3'][0]-change
    tolerance = 1e-6+1e-10*(abs(before)+abs(after)+rain[0])
    if np.any(abs(residual)>tolerance) or abs(float(residual.sum())) > 1e-6+1e-10*float(abs(change).sum()+rain.sum()):
        raise ValueError('v10 water ledger failed')
    if not np.allclose(change, arrays['storage_change_m3'][0], rtol=0, atol=1e-9) or not np.allclose(residual, arrays['balance_residual_m3'][0], rtol=0, atol=1e-7):
        raise ValueError('v10 saved balance mismatch')
    return True


def validate_checkpoint(result):
    arrays, metadata = _metadata(result)
    required = STATES + ERRORS + tuple('cumulative_'+key for key in FLUX)
    if metadata.get('schema') != 'td-v10-hour-checkpoint-v1' or set(arrays) != set(required):
        raise ValueError('v10 checkpoint arrays/schema mismatch')
    for key in STATES + ERRORS:
        if arrays[key].shape != (metadata['cells'],):
            raise ValueError('v10 checkpoint state shape mismatch')
        if key in STATES and np.any(arrays[key] < 0):
            raise ValueError('v10 checkpoint negative state')
    if np.any(arrays['soil_mm'] > 150):
        raise ValueError('v10 checkpoint soil capacity exceeded')
    for key in FLUX:
        values = arrays['cumulative_'+key]
        size = metadata['faces'] if key.startswith(('face_', 'active_')) else metadata['cells']
        if values.shape != (size,) or np.any(values < 0):
            raise ValueError('v10 checkpoint evidence invalid')
        if ('duration' in key or key.startswith('active_')) and np.any(values > metadata['end_s']+1e-8):
            raise ValueError('v10 cumulative duration invalid')
    if re.fullmatch('[0-9a-f]{64}', metadata.get('last_page_identity', '')) is None:
        raise ValueError('v10 checkpoint last-page identity invalid')
    return True


def _headers(headers):
    if 'manifest' not in headers or len(headers) > 64:
        raise ValueError('v10 archive headers invalid')
    for key, (shape, dtype) in headers.items():
        if key == 'manifest':
            if dtype != np.uint8 or len(shape) != 1 or math.prod(shape) > 1048576:
                raise ValueError('v10 manifest allocation invalid')
        elif dtype not in (np.dtype('float64'), np.dtype('int64'), np.dtype('bool')) or math.prod(shape) > 1000000:
            raise ValueError('v10 array allocation/type invalid')


def save_storage(path, result):
    save_bundle(path, result, validator=validate_storage)


def save_checkpoint(path, result):
    save_bundle(path, result, validator=validate_checkpoint)


def _load(path, expected_sha256, expected_identity, validator):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validator,
                         max_bytes=128*1024*1024, header_validator=_headers)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('v10 external identity mismatch')
    return result


def load_storage(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_storage)


def load_checkpoint(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_checkpoint)
