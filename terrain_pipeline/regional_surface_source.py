"""Full real-TD regional source and saved static routing diagnostics."""
import numpy as np
from terrain_pipeline.common_infra import load_physical_source, identity, readonly, save_bundle, load_bundle
from terrain_pipeline.lake import load_mountain_geometry as load_mountain_geometry
RAW_SHA256 = 'e1dc646b990388af3bf284b614b10c2a834d0259429539d2a7d3d2cc844712ae'
SCHEMA = 'regional-surface-source-v1'
KEYS = {'height_m', 'receiver', 'downstream_first_order', 'outlet_owner', 'outlet_cells', 'contributing_area_m2', 'diagnostic_lake_id', 'boundary_mask', 'protected_mask', 'hydrology_mask', 'channel_mask'}

def build_source(raw_path, geometry_path, *, geometry_sha256, channel_area_m2=1000000.0):
    if not np.isfinite(channel_area_m2) or channel_area_m2 <= 0:
        raise ValueError('positive independent channel threshold required')
    source = load_physical_source(raw_path, expected_sha256=RAW_SHA256, boundary={'policy': 'all_edges_open', 'halo_cells': 0, 'upstream_contribution': 'excluded_finite_experiment'})
    from terrain_pipeline.common_infra import file_sha256
    if file_sha256(geometry_path) != geometry_sha256:
        raise ValueError('external geometry SHA mismatch')
    geometry = load_mountain_geometry(geometry_path, trusted_height=source['arrays']['height_m'], source_binding={'source_identity': source['identity_sha256']})
    old = geometry['arrays']
    arrays = {'height_m': old['H0_m'].copy(), 'receiver': old['receiver'].reshape(256, 256).copy(), 'downstream_first_order': old['order'].copy(), 'outlet_owner': old['outlet_owner'].copy(), 'outlet_cells': old['outlet_cells'].copy(), 'contributing_area_m2': old['contributing_area_m2'].copy(), 'diagnostic_lake_id': old['lake_id'].copy(), 'boundary_mask': old['boundary_mask'].copy(), 'protected_mask': old['protected_mask'].copy(), 'hydrology_mask': np.ones((256, 256), bool), 'channel_mask': old['contributing_area_m2'] >= channel_area_m2}
    meta = {'schema': SCHEMA, 'raw_sha256': RAW_SHA256, 'height_source_identity': source['identity_sha256'], 'geometry_sha256': geometry_sha256, 'shape': [256, 256], 'spacing_m': 30.0, 'origin_m_xz': source['metadata']['origin_m_xz'], 'area_m2': 58982400.0, 'channel_area_threshold_m2': float(channel_area_m2), 'boundary_condition': 'all_edges_free_engineering_drain', 'natural_outlet_certified': False, 'hydrological_planning_domain_closed': False, 'diagnostic_scope': 'D4 fullspill static routing/lake labels only; never uniform-stage dynamic pools', 'surface_evolution': 'static H0 input only; dynamic solver algorithm and flux law declared by downstream solver artifact'}
    result = {'arrays': arrays, 'metadata': meta, 'identity_sha256': identity(arrays, meta)}
    validate_source(result)
    result['arrays'] = {key: readonly(value) for key, value in arrays.items()}
    return result

def headers(values):
    if set(values) != KEYS | {'manifest'}:
        raise ValueError('regional source exact members required')
    for key in KEYS:
        shape, dtype = values[key]
        expected_shape = (65536,) if key == 'downstream_first_order' else (1020,) if key == 'outlet_cells' else (256, 256)
        expected_dtype = bool if key.endswith('mask') else np.int64 if key in {'receiver', 'downstream_first_order', 'outlet_owner', 'outlet_cells', 'diagnostic_lake_id'} else np.float64
        if shape != expected_shape or dtype != np.dtype(expected_dtype):
            raise ValueError('regional source typed allocation mismatch: ' + key)
    shape, dtype = values['manifest']
    if len(shape) != 1 or not 1 <= shape[0] <= 65536 or dtype != np.uint8:
        raise ValueError('bounded metadata required')

def validate_source(result):
    arrays, meta = (result['arrays'], result['metadata'])
    headers({**{key: (value.shape, value.dtype) for key, value in arrays.items()}, 'manifest': ((1,), np.dtype(np.uint8))})
    expected = {'schema', 'raw_sha256', 'height_source_identity', 'geometry_sha256', 'shape', 'spacing_m', 'origin_m_xz', 'area_m2', 'channel_area_threshold_m2', 'boundary_condition', 'natural_outlet_certified', 'hydrological_planning_domain_closed', 'diagnostic_scope', 'surface_evolution'}
    if set(meta) != expected or meta['schema'] != SCHEMA or meta['raw_sha256'] != RAW_SHA256 or (meta['shape'] != [256, 256]) or (meta['spacing_m'] != 30.0) or (meta['area_m2'] != 58982400.0) or (meta['boundary_condition'] != 'all_edges_free_engineering_drain') or (meta['natural_outlet_certified'] is not False) or (meta['hydrological_planning_domain_closed'] is not False) or (result['identity_sha256'] != identity(arrays, meta)):
        raise ValueError('regional source contract mismatch')
    if not arrays['hydrology_mask'].all() or not np.isfinite(arrays['height_m']).all():
        raise ValueError('full finite65536 grid required')
    if len(meta['origin_m_xz']) != 2 or not np.isfinite(meta['origin_m_xz']).all():
        raise ValueError('finite absolute origin required')
    if meta['origin_m_xz'] != [-184320.0, 61440.0]:
        raise ValueError('fixed actual source origin required')
    for key in ('height_source_identity', 'geometry_sha256'):
        token = meta[key]
        if not isinstance(token, str) or len(token) != 64 or any((letter not in '0123456789abcdef' for letter in token)):
            raise ValueError('source and geometry identities required')
    if (arrays['diagnostic_lake_id'] < 0).any() or not np.isfinite(arrays['contributing_area_m2']).all():
        raise ValueError('finite static diagnostic arrays required')
    threshold = meta['channel_area_threshold_m2']
    if not isinstance(threshold, (int, float)) or not np.isfinite(threshold) or threshold <= 0:
        raise ValueError('positive channel threshold required')
    boundary = np.zeros((256, 256), bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    receiver = arrays['receiver'].ravel()
    order = arrays['downstream_first_order']
    if not np.array_equal(boundary, arrays['boundary_mask']) or not np.array_equal(receiver == -1, boundary.ravel()):
        raise ValueError('engineering drain must be exactly all window edges')
    if (receiver < -1).any() or (receiver >= 65536).any() or (not np.array_equal(np.sort(order), np.arange(65536))):
        raise ValueError('bounded full static routing required')
    rank = np.empty(65536, np.int64)
    rank[order] = np.arange(65536)
    active = receiver >= 0
    donors = np.flatnonzero(active)
    targets = receiver[active]
    if not (rank[donors] > rank[targets]).all() or not (np.abs(donors // 256 - targets // 256) + np.abs(donors % 256 - targets % 256) == 1).all():
        raise ValueError('static D4 DAG required')
    outlets = arrays['outlet_cells']
    owner = arrays['outlet_owner'].ravel()
    if not np.array_equal(outlets, np.flatnonzero(boundary)) or (owner < 0).any() or (owner >= 1020).any():
        raise ValueError('complete outlet identifiers required')
    if not np.array_equal(owner[outlets], np.arange(1020)) or not np.array_equal(owner[donors], owner[targets]):
        raise ValueError('saved outlet owner recurrence fails')
    accumulation = arrays['contributing_area_m2'].ravel()
    expected_area = np.full(65536, 900.0)
    np.add.at(expected_area, targets, accumulation[donors])
    if not np.array_equal(accumulation, expected_area) or accumulation[outlets].sum() != 58982400.0:
        raise ValueError('full unique contributing area recurrence fails')
    if not np.array_equal(arrays['channel_mask'], arrays['contributing_area_m2'] >= threshold):
        raise ValueError('independent channel diagnostic mismatch')
    return {'cells': 65536, 'area_m2': 58982400.0, 'static_route_certified': True, 'dynamic_surface_solved': False}

def save_source(path, result):
    save_bundle(path, result, validator=validate_source)

def load_source(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, max_bytes=32 * 1024 * 1024, header_validator=headers, validator=validate_source)
