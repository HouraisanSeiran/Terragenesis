"""Consolidated environment_product implementations; numeric expressions preserved."""
from __future__ import annotations
from copy import deepcopy as _i42_deepcopy
import math as _i42_math
import numpy as _i42_np
from pathlib import Path as _i40_Path
import json as _i40_json
import math as _i40_math
import numpy as _i40_np
from copy import deepcopy as _i39_deepcopy
import math as _i39_math
import numpy as _i39_np
from dataclasses import dataclass as _i41_dataclass
import hashlib as _i41_hashlib
import json as _i41_json
import math as _i41_math
import numpy as _i41_np
from dataclasses import asdict as _i43_asdict
import json as _i43_json
import os as _i43_os
from pathlib import Path as _i43_Path
import time as _i43_time
import numpy as _i43_np
from numba import njit as _i43_njit
from scipy.ndimage import map_coordinates as _i43_map_coordinates
from terrain_pipeline.environment_processes import radiation_initialize as _x115_radiation_initialize
from terrain_pipeline.environment_processes import frozen_ground_initialize as _x116_frozen_ground_initialize
from terrain_pipeline.environment_processes import volcanism_initialize as _x117_volcanism_initialize
from terrain_pipeline.environment_processes import aeolian_initialize as _x118_aeolian_initialize
from terrain_pipeline.environment_processes import initialize_soil_chemistry as _x119_initialize_soil_chemistry
from terrain_pipeline.environment_processes import initialize_succession as _x120_initialize_succession
from terrain_pipeline.environment_processes import initialize_coastal_exchange as _x121_initialize_coastal_exchange
from terrain_pipeline.environment_processes import initialize_habitat as _x122_initialize_habitat
CATEGORY = 'D'
STORAGE_SCHEMA = 'environment-process-product-v1'
STORAGE_ALGORITHM = 'finite-environment-process-coupling-v1'
EXPLICIT_V2_ALGORITHM = 'finite-environment-process-coupling-v2'
SEASONAL_ALGORITHM = 'finite-environment-seasonal-coupling-v1'
SEASONAL_V2_ALGORITHM = 'finite-environment-seasonal-coupling-v2'
STORAGE_MAX_CELLS = 4096
PACKETS = ('litter_carbon_kg', 'plant_nutrient_return_kg', 'soil_water_m3', 'soil_salt_kg', 'subsurface_salt_kg', 'subsurface_nutrient_kg')

def _pack(product, validate_product=None):
    if validate_product is None:
        validate_product = _validate_product
    from terrain_pipeline.common_infra import identity as _i42_identity
    validate_product(product)
    chunks, layout = ([], [])
    offset = 0

    def encode(value):
        nonlocal offset
        if isinstance(value, _i42_np.ndarray):
            data = _i42_np.ascontiguousarray(value)
            if data.dtype.kind not in 'biuf' or not _i42_np.isfinite(data).all():
                raise ValueError('finite numeric/bool arrays required')
            key = len(layout)
            raw = data.view(_i42_np.uint8).ravel()
            layout.append({'offset': offset, 'bytes': raw.size, 'shape': list(data.shape), 'dtype': data.dtype.str})
            chunks.append(raw)
            offset += raw.size
            return {'array_index': key}
        if isinstance(value, dict):
            return {str(key): encode(value[key]) for key in sorted(value)}
        if isinstance(value, (tuple, list)):
            return [encode(child) for child in value]
        if isinstance(value, _i42_np.generic):
            return value.item()
        return value
    tree = encode(product)
    payload = _i42_np.concatenate(chunks) if chunks else _i42_np.empty(0, _i42_np.uint8)
    if payload.nbytes > 64 * 1024 * 1024:
        raise ValueError('product payload exceeds bounded memory budget')
    metadata = {'schema': STORAGE_SCHEMA, 'algorithm': product['algorithm'], 'tree': tree, 'layout': layout}
    arrays = {'payload': payload}
    return {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i42_identity(arrays, metadata)}

def _validate_bundle(bundle, validate_product=None):
    if validate_product is None:
        validate_product = _validate_product
    from terrain_pipeline.common_infra import identity as _i42_identity
    metadata = bundle['metadata']
    if metadata.get('schema') != STORAGE_SCHEMA or metadata.get('algorithm') not in (STORAGE_ALGORITHM, EXPLICIT_V2_ALGORITHM, SEASONAL_ALGORITHM, SEASONAL_V2_ALGORITHM):
        raise ValueError('environment process schema mismatch')
    if _i42_identity(bundle['arrays'], metadata) != bundle['identity_sha256']:
        raise ValueError('environment process identity mismatch')
    payload = bundle['arrays']['payload']
    offset = 0
    for item in metadata['layout']:
        dtype = _i42_np.dtype(item['dtype'])
        if dtype.kind not in 'biuf' or any((not isinstance(n, int) or n < 0 for n in item['shape'])):
            raise ValueError('invalid packed dtype/shape')
        size = _i42_math.prod(item['shape']) * dtype.itemsize
        if item['offset'] != offset or item['bytes'] != size:
            raise ValueError('packed array layout mismatch')
        offset += size
    if payload.dtype != _i42_np.uint8 or payload.ndim != 1 or offset != payload.size:
        raise ValueError('packed payload length mismatch')
    product = _unpack(bundle)
    if product['algorithm'] != metadata['algorithm']:
        raise ValueError('environment process algorithm header/tree mismatch')
    validate_product(product)

def _unpack(bundle):
    payload = bundle['arrays']['payload']
    layout = bundle['metadata']['layout']

    def decode(value):
        if isinstance(value, dict) and set(value) == {'array_index'}:
            item = layout[value['array_index']]
            raw = payload[item['offset']:item['offset'] + item['bytes']]
            result = _i42_np.frombuffer(raw.tobytes(), dtype=item['dtype']).reshape(item['shape'])
            if not _i42_np.isfinite(result).all():
                raise ValueError('nonfinite process payload')
            return result
        if isinstance(value, dict):
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value
    return decode(bundle['metadata']['tree'])

def save_product(product, path, validate_product=None):
    if validate_product is None:
        validate_product = _validate_product
    from terrain_pipeline.common_infra import file_sha256 as _i42_file_sha256
    from terrain_pipeline.common_infra import save_bundle as _i42_save_bundle
    _i42_save_bundle(path, _pack(product, validate_product), validator=lambda bundle: _validate_bundle(bundle, validate_product))
    return _i42_file_sha256(path)

def product_identity(product, validate_product=None):
    if validate_product is None:
        validate_product = _validate_product
    return _pack(product, validate_product)['identity_sha256']

def load_product(path, *, expected_sha256, validate_product=None):
    if validate_product is None:
        validate_product = _validate_product
    from terrain_pipeline.common_infra import load_bundle as _i42_load_bundle
    bundle = _i42_load_bundle(path, expected_sha256=expected_sha256, validator=lambda bundle: _validate_bundle(bundle, validate_product))
    return _unpack(bundle)

def query_product(product, row, col):
    shape = product['context']['height_m'].shape
    if not 0 <= row < shape[0] or not 0 <= col < shape[1]:
        raise ValueError('query outside completed product')
    result = {'schema': STORAGE_SCHEMA, 'time_s': product['time_s'], 'row': int(row), 'col': int(col), 'world_x_m': float(product['context']['node_x_m'][row, col]), 'world_z_m': float(product['context']['node_z_m'][row, col]), 'derived_height_m': float(product['context']['height_m'][row, col]), 'receiver': int(product['context']['receiver'][row, col]), 'external_handoff': bool(product['context']['external_receiver_mask'][row, col]), 'ocean': bool(product['context']['ocean_mask'][row, col]), 'states': {name: {key: _i42_np.asarray(value)[row, col].item() for key, value in state.items()} for name, state in product['states'].items()}, 'last_budget': _i42_deepcopy(product['last_budget'])}
    if 'seasonal' in product:
        seasonal = product['seasonal']
        origin = product['context']['origin_native_xz']
        base = seasonal['climate_driver']['metadata']['origin_native_xz']
        sr, sc = (row + origin[1] - base[1], col + origin[0] - base[0])
        result['seasonal'] = {key: float(seasonal[key][row, col]) for key in ('snow_swe_mm', 'fast_mm', 'slow_mm')}
        result['seasonal'].update(vapour_kg=float(seasonal['climate_state']['arrays']['vapour_kg'][sr, sc]), pending_et_kg=float(seasonal['pending_et_kg'][sr, sc]), network_policy=seasonal['network_policy'], driver_identity_sha256=seasonal['climate_driver']['identity_sha256'], source_world_identity=product['sources']['source_world_identity'], initial_swe_source=seasonal['initial_swe_source'])
        from terrain_pipeline.geology import query_material_source as query_material_source
        result['seasonal']['material'] = query_material_source(seasonal['material_source'], row, col)
        if 'land_cover' in seasonal:
            from terrain_pipeline.soil_water import query as query_land_cover
            result['seasonal']['land_cover'] = query_land_cover(product, row, col)
    return result

def context_from_store(store, row, col, size=33):
    """Read and pin an existing source; never generate a TD page or river Q."""
    from terrain_pipeline.drainage import build_mesh as _i40_build_mesh
    from terrain_pipeline.common_infra import checked_archive as _i40_checked_archive
    from terrain_pipeline.common_infra import file_sha256 as _i40_file_sha256
    from terrain_pipeline.td_source import read_disk_manifest as _i40_read_manifest
    from terrain_pipeline.world_river_network_io import read_network as _i40_read_network
    from terrain_pipeline.drainage import segments_clear as _i40_segments_clear
    from terrain_pipeline.geology import sample_lithology_points as _x62_sample_lithology_points
    store = _i40_Path(store)
    registry_path = store / 'registry.json'
    registry = _i40_json.loads(registry_path.read_text(encoding='utf-8'))
    if len(registry['components']) != 1:
        raise ValueError('select a store with exactly one prepared component')
    root, manifest = _i40_read_manifest(store, registry['components'][0], registry['world_identity'])
    graph = _i40_read_network(root, manifest['network'])
    shape = tuple(map(int, graph['native_shape']))
    if min(row, col) < 0 or size < 2 or size * size > STORAGE_MAX_CELLS or (row + size > shape[0]) or (col + size > shape[1]):
        raise ValueError('bounded source window outside saved graph')
    rows, cols = _i40_np.indices((size, size))
    source_ids = (rows + row) * shape[1] + cols + col
    remap = _i40_np.full(_i40_math.prod(shape), -1, _i40_np.int64)
    remap[source_ids.ravel()] = _i40_np.arange(size * size)
    original_receiver = graph['receiver'][source_ids]
    receiver = _i40_np.full((size, size), -1, _i40_np.int64)
    linked = original_receiver >= 0
    receiver[linked] = remap[original_receiver[linked]]
    external = linked & (receiver < 0)
    spacing = float(graph['spacing_m'])
    seed = int(manifest['network']['metadata']['world_seed'])
    full_mesh = _i40_build_mesh(shape, origin_native_xz=tuple(map(int, graph['origin_native_xz'])), spacing_m=spacing, world_seed=seed)
    edge_source = _i40_np.repeat(_i40_np.arange(_i40_math.prod(shape)), _i40_np.diff(full_mesh.indptr))
    keep = (remap[edge_source] >= 0) & (remap[full_mesh.indices] >= 0)
    es, et = (remap[edge_source[keep]], remap[full_mesh.indices[keep]])
    origin = (int(graph['origin_native_xz'][0]) + col, int(graph['origin_native_xz'][1]) + row)
    source_flags = {}
    tile_sources = []
    for group, needed in (('water_tiles', ('ocean_mask', 'channel_mask', 'complete_mask', 'protected_shore_mask', 'pending_basin_mask', 'lake_mask', 'upstream_unknown_mask')), ('composition_tiles', ('valid_mask',))):
        fields = {name: _i40_np.zeros((size, size), bool) for name in needed}
        covered = _i40_np.zeros((size, size), bool)
        for tile in manifest[group]:
            tx, tz = tile['origin_native_xz']
            tr, tc = tile['shape_zx']
            left, right = (max(origin[0], tx), min(origin[0] + size, tx + tc))
            top, bottom = (max(origin[1], tz), min(origin[1] + size, tz + tr))
            if right <= left or bottom <= top:
                continue
            path = root / tile['file']
            data = _i40_checked_archive(path, expected_sha256=tile['sha256'])
            target = (slice(top - origin[1], bottom - origin[1]), slice(left - origin[0], right - origin[0]))
            src = (slice(top - tz, bottom - tz), slice(left - tx, right - tx))
            for name in needed:
                fields[name][target] = data[name][src]
            covered[target] = True
            tile_sources.append({'file': str(path.resolve()), 'sha256': tile['sha256']})
        if not covered.all():
            raise ValueError('source masks do not cover selected saved window')
        source_flags.update(fields)
    ocean = source_flags['ocean_mask']
    valid = source_flags['valid_mask'] & source_flags['complete_mask']
    donors = _i40_np.flatnonzero(receiver.ravel() >= 0)
    blocked = donors[~_i40_segments_clear(donors, receiver.ravel()[donors], valid)]
    unresolved = _i40_np.zeros((size, size), bool)
    unresolved.ravel()[blocked] = True
    receiver.ravel()[blocked] = -1
    receiver[~valid] = -1
    clear = _i40_segments_clear(es, et, valid)
    es, et = (es[clear], et[clear])
    river_nodes = _i40_np.zeros(_i40_math.prod(shape), bool)
    river_nodes[graph.get('reach_source_node', graph.get('reach_source'))] = True
    river_nodes[graph.get('reach_target_node', graph.get('reach_target'))] = True
    ctx = {'height_m': graph['node_raw_bed_m'][source_ids].copy(), 'spacing_m': spacing, 'source_height_m': graph['node_raw_bed_m'][source_ids].copy(), 'source_receiver_node': original_receiver.copy(), 'origin_native_xz': list(origin), 'world_seed': seed, 'receiver': receiver, 'river_mask': source_flags['channel_mask'], 'ocean_mask': ocean, 'valid_mask': valid, 'protected_mask': source_flags['protected_shore_mask'], 'pending_basin_mask': source_flags['pending_basin_mask'], 'lake_mask': source_flags['lake_mask'], 'source_complete_mask': source_flags['complete_mask'], 'source_upstream_unknown_mask': source_flags['upstream_unknown_mask'], 'unresolved_receiver_mask': unresolved, 'node_x_m': graph['node_x_m'][source_ids], 'node_z_m': graph['node_z_m'][source_ids], 'graph_edge_source': es, 'graph_edge_target': et, 'external_receiver_mask': external, 'external_receiver_source_node': _i40_np.where(external, original_receiver, -1), 'source_terminal_kind': graph['node_terminal_kind'][source_ids], 'source_terminal_mask': external | ocean | unresolved | ~valid, 'routing_policy': 'source_terminal_flood'}
    if not ctx['source_terminal_mask'].any():
        ctx['source_terminal_mask'] = receiver < 0
    lithology = _x62_sample_lithology_points((origin[0] + cols) * spacing, (origin[1] + rows) * spacing, world_seed=seed)
    ctx['bed_hardness'] = _i40_np.asarray(lithology['bed_hardness']).reshape(size, size)
    ctx['solubility'] = _i40_np.full((size, size), 0.2)
    sources = {'kind': 'saved_generated_TD_terrain_not_observation', 'registry_path': str(registry_path.resolve()), 'registry_sha256': _i40_file_sha256(registry_path), 'source_world_identity': registry['world_identity'], 'manifest_sha256': _i40_file_sha256(root / 'manifest.json'), 'network_sha256': manifest['network']['sha256'], 'source_pages': registry['pages'], 'mask_tiles': tile_sources, 'window_row_col_size': [int(row), int(col), int(size)], 'external_receiver_cells': int(external.sum()), 'ocean_identity': 'unchanged hash-verified saved water tile ocean_mask; no edge-to-ocean inference', 'mesh_policy': 'saved full-source irregular adjacency restricted to window; real saved node coordinates', 'routing_policy': 'source terminals include external handoff/ocean; no external regeneration', 'lithology': 'same-world sample_lithology_points at native account anchors, seed20261020; graph position offset retained separately', 'solubility': 'declared engineering fraction0.2; existing lithology API does not supply solubility', 'porosity': 'declared engineering regolith porosity0.35; not a sampled material property'}
    return (ctx, sources)
MODULES = {'radiation': _x115_radiation_initialize, 'frozen_ground': _x116_frozen_ground_initialize, 'volcanism': _x117_volcanism_initialize, 'aeolian': _x118_aeolian_initialize, 'soil_chemistry': _x119_initialize_soil_chemistry, 'succession': _x120_initialize_succession, 'coastal_exchange': _x121_initialize_coastal_exchange, 'habitat': _x122_initialize_habitat}
FORCING_KEYS = {'radiation': {'latitude_deg', 'longitude_deg', 'albedo', 'time_s'}, 'volcanism': {'lava_input_m3', 'ash_input_m3', 'geothermal_w_m2', 'wind_x_m_s', 'wind_z_m_s'}, 'frozen_ground': set(), 'aeolian': {'wind_x_m_s', 'wind_z_m_s'}, 'mass': {'weathering_parameters', 'soil_request_solid_m3', 'transport_fraction_per_s', 'repose_angle_deg'}, 'groundwater': {'specific_yield', 'aquifer_base_m', 'lateral_conductance_m2_s', 'surface_conductance_m2_s', 'surface_stage_m', 'pumping_request_m3'}, 'soil_chemistry': {'drainage_m3_s', 'nutrient_input_kg_s', 'litter_nutrient_kg'}, 'succession': {'fire_hazard_s', 'disturbance_hazard_s'}, 'coastal_exchange': {'tide_amplitude_m', 'tide_period_s', 'mean_sea_level_m', 'tide_phase_rad', 'wave_height_m', 'wave_direction_xz', 'ocean_salinity_kg_m3', 'soil_exchange_m3_s'}, 'habitat': set()}

def _land_context(context):
    result = dict(context)
    land = context['valid_mask'] & ~context['ocean_mask']
    result['valid_mask'] = land
    rec = context['receiver'].copy()
    donors = _i39_np.flatnonzero(rec.ravel() >= 0)
    rec.ravel()[donors[~land.ravel()[rec.ravel()[donors]]]] = -1
    rec[~land] = -1
    result['receiver'] = rec
    return result

def initialize(context, sources=None, initial=None, *, mode='explicit', climate_driver=None, climate_state=None, seasonal_parameters=None):
    from terrain_pipeline.environment_processes import mass_initial_state as _x123_mass_initial_state
    from terrain_pipeline.environment_processes import groundwater_initial_state as _x124_groundwater_initial_state
    from terrain_pipeline.environment_processes import network_transition_initial_state as _x125_network_transition_initial_state
    from terrain_pipeline.soil_water import initialize as _x126_initialize
    from terrain_pipeline.environment_processes import inventory_totals as _x59_inventory_totals
    from terrain_pipeline.environment_contract import array as _x60_array
    from terrain_pipeline.environment_contract import context_arrays as _x61_context_arrays
    if mode not in ('explicit', 'explicit-v2', 'seasonal', 'seasonal-v2'):
        raise ValueError('environment mode must be explicit, explicit-v2, seasonal or seasonal-v2')
    if mode in ('explicit', 'explicit-v2') and any((value is not None for value in (climate_driver, climate_state, seasonal_parameters))):
        raise ValueError('climate driver/state/config require seasonal mode')
    context = _i39_deepcopy(context)
    height, masks, mesh, _ = _x61_context_arrays(context, 1.0)
    if height.size > STORAGE_MAX_CELLS:
        raise ValueError('dynamic product exceeds finite cell budget')
    if 'node_x_m' not in context:
        context['node_x_m'] = mesh.node_x_m.reshape(height.shape).copy()
        context['node_z_m'] = mesh.node_z_m.reshape(height.shape).copy()
    context.setdefault('external_receiver_mask', _i39_np.zeros(height.shape, bool))
    context.setdefault('source_terminal_mask', context['receiver'] < 0)
    context.setdefault('routing_policy', 'source_terminal_flood')
    declarations = _i39_deepcopy(initial or {})
    material_source = None
    if mode in ('seasonal', 'seasonal-v2'):
        if {'bed_hardness', 'solubility'} & set(declarations.get('mass', {})):
            raise ValueError('seasonal G2 sampled bed_hardness/solubility cannot be overridden by initial.mass')
        from terrain_pipeline.geology import prepare_material_source as prepare_material_source
        from terrain_pipeline.geology import material_mass_inputs as material_mass_inputs
        material_source = prepare_material_source(context)
        context.update(material_mass_inputs(material_source, context))
        sources = _i39_deepcopy(sources or {'kind': 'explicit_synthetic_context'})
        sources['solubility'] = 'same-world G2 properties_at at native account anchors; original rock-table solubility'
        sources['porosity'] = 'regolith engineering porosity0.35; G2 bedrock_porosity is a separate read-only property'
    land_ctx = _land_context(context)
    land = land_ctx['valid_mask'] & ~land_ctx['protected_mask']
    mass_args = {'bed_hardness': context.get('bed_hardness', 0.5), 'solubility': context.get('solubility', 0.2)}
    mass_args.update(declarations.get('mass', {}))
    groundwater_args = {name: _x60_array(value, height.shape, name) * land for name, value in declarations.get('groundwater', {}).items()}
    states = {'mass': _x123_mass_initial_state(land_ctx, **mass_args), 'groundwater': _x124_groundwater_initial_state(land_ctx, **groundwater_args)}
    for name, module in MODULES.items():
        ctx = context if name in ('radiation', 'coastal_exchange', 'aeolian', 'habitat') else land_ctx
        args = _i39_deepcopy(declarations.get(name, {}))
        states[name] = module(ctx, **args)
        if name in ('frozen_ground', 'soil_chemistry', 'succession', 'habitat'):
            for key in states[name]:
                states[name][key] = _i39_np.where(land, states[name][key], 0.0)
    states['network_transition'] = _x125_network_transition_initial_state(context)
    product = {'schema': STORAGE_SCHEMA, 'algorithm': STORAGE_ALGORITHM, 'context': context, 'states': states, 'results': {}, 'sources': _i39_deepcopy(sources or {'kind': 'explicit_synthetic_context'}), 'initial_declarations': declarations, 'time_s': 0.0, 'step_index': 0, 'parameters': {'status': 'declared_engineering_scenario_uncalibrated', 'rain_partition': '0.2 frozen; infiltration_factor*(0.6 soil+0.2 aquifer); remainder runoff', 'surface_packet_speed_m_s': '.5*.025/manning_n; one delivered graph edge per step', 'aquifer_exchange_roughness': 'surface conductance multiplied by .025/manning_n', 'process_parameters': {}}, 'pending_packets': {key: _i39_np.zeros(height.shape) for key in PACKETS}, 'cumulative_ledger': {}, 'last_transfers': {}, 'last_budget': {}, 'last_energy_budget': {}, 'forcing_history': [], 'limitations': ['finite engineering mechanism coupling, not calibrated natural-process certification', 'saved representative Q is never used as local rain or reinjected water', 'land soil/frozen/GW reservoirs are separately declared control-volume stocks', 'leached salt/nutrient stay in explicit pending subsurface stores; aquifer solute transport not implemented', 'network_transition inventories are read-only native-cell accounting views, not additional stores']}
    if mode in ('seasonal', 'seasonal-v2'):
        if climate_driver is None:
            raise ValueError('seasonal mode requires a pinned climate driver')
        _x126_initialize(product, climate_driver, climate_state, seasonal_parameters, material_source=material_source, version=2 if mode == 'seasonal-v2' else 1)
    if mode == 'explicit-v2':
        product['algorithm'] = EXPLICIT_V2_ALGORITHM
    product['initial_inventory'] = _x59_inventory_totals(product)
    return product

def _route_packet(stock, context, dt_s, manning_n):
    """Move each local packet at most one delivered receiver edge per step."""
    shape = stock.shape
    receiver = context['receiver'].ravel()
    donors = _i39_np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    x, z = (context['node_x_m'].ravel(), context['node_z_m'].ravel())
    length = _i39_np.hypot(x[donors] - x[targets], z[donors] - z[targets])
    fraction = _i39_np.minimum(1.0, 0.5 * 0.025 / manning_n.ravel()[donors] * dt_s / length)
    moved = stock.ravel()[donors] * fraction
    updated = stock.copy()
    updated.ravel()[donors] -= moved
    ocean = context['ocean_mask'].ravel()[targets]
    coast_packet = _i39_np.zeros(shape)
    _i39_np.add.at(coast_packet.ravel(), targets[ocean], moved[ocean])
    _i39_np.add.at(updated.ravel(), targets[~ocean], moved[~ocean])
    external = context['external_receiver_mask'] & (context['receiver'] < 0)
    exported = _i39_np.where(external, updated, 0.0)
    updated -= exported
    return (updated, coast_packet, exported)

def advance(product, forcing, dt_s):
    """Advance one physical interval; every cross-module packet is debited once."""
    from terrain_pipeline.environment_processes import network_transition_initial_state as _x125_network_transition_initial_state
    from terrain_pipeline.soil_water import is_seasonal as _x127_is_seasonal
    from terrain_pipeline.soil_water import ALGORITHM_V2 as _x128_ALGORITHM_V2
    from terrain_pipeline.soil_water import advance_driver as _x129_advance_driver
    from terrain_pipeline.environment_processes import volcanism_step as _x130_volcanism_step
    from terrain_pipeline.environment_processes import radiation_step as _x131_radiation_step
    from terrain_pipeline.environment_processes import frozen_ground_step as _x132_frozen_ground_step
    from terrain_pipeline.soil_water import snow_and_bucket as _x133_snow_and_bucket
    from terrain_pipeline.environment_processes import SUCCESSION_PARAMETERS as _x134_SUCCESSION_PARAMETERS
    from terrain_pipeline.environment_processes import advance_soil_chemistry as _x135_soil_chemistry_step
    from terrain_pipeline.soil_water import driver_slices as _x136_driver_slices
    from terrain_pipeline.environment_processes import advance_succession as _x137_succession_step
    from terrain_pipeline.environment_processes import mass_step as _x138_mass_step
    from terrain_pipeline.environment_processes import aeolian_step as _x139_aeolian_step
    from terrain_pipeline.environment_processes import groundwater_step as _x140_groundwater_step
    from terrain_pipeline.environment_processes import advance_coastal_exchange as _x141_coastal_exchange_step
    from terrain_pipeline.environment_processes import advance_habitat as _x142_habitat_step
    from terrain_pipeline.environment_processes import INVENTORIES as _x143_INVENTORIES
    from terrain_pipeline.soil_water import NETWORK_ALGORITHM as _x144_NETWORK_ALGORITHM
    from terrain_pipeline.environment_processes import network_transition_step as _x145_network_transition_step
    from terrain_pipeline.environment_processes import commit_transition as _x146_commit_transition
    from terrain_pipeline.soil_water import net_water as _x147_net_water
    from terrain_pipeline.environment_processes import inventory_totals as _x59_inventory_totals
    from terrain_pipeline.environment_contract import array as _x60_array
    if not _i39_np.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError('positive physical dt_s required')
    seasonal_mode = _x127_is_seasonal(product)
    land_cover_mode = product.get('algorithm') == _x128_ALGORITHM_V2
    handoff_mode = land_cover_mode or product.get('algorithm') == EXPLICIT_V2_ALGORITHM
    allowed = set(FORCING_KEYS) | {'rainfall_m_s', 'air_temperature_c', 'wind_x_m_s', 'wind_z_m_s'}
    if seasonal_mode:
        allowed.add('climate')
    if handoff_mode:
        allowed.add('hydraulic_handoff_mask')
    allowed |= {name + '_parameters' for name in ('radiation', 'frozen_ground', 'volcanism', 'aeolian')}
    if set(forcing) - allowed:
        raise ValueError('unsupported product forcing fields: ' + str(sorted(set(forcing) - allowed)))
    for name, keys in FORCING_KEYS.items():
        if name in forcing and (not isinstance(forcing[name], dict) or set(forcing[name]) - keys):
            raise ValueError('unsupported or internally coupled forcing fields for ' + name)
    handoff_mask = None
    if handoff_mode:
        handoff_mask = _i39_np.asarray(forcing.get('hydraulic_handoff_mask', _i39_np.zeros_like(product['context']['valid_mask'])))
        active = product['context']['valid_mask'] & ~product['context']['ocean_mask'] & ~product['context']['protected_mask']
        if handoff_mask.dtype != bool or handoff_mask.shape != active.shape or _i39_np.any(handoff_mask & ~active):
            raise ValueError('hydraulic_handoff_mask must be matching bool active-land support')
    out = _i39_deepcopy(product)
    ctx, s = (out['context'], out['states'])
    land_ctx = _land_context(ctx)
    shape = ctx['height_m'].shape
    area = float(ctx['spacing_m']) ** 2
    land = land_ctx['valid_mask'] & ~ctx['protected_mask']
    before = _x59_inventory_totals(out)
    old_mass = s['mass']
    results, transfers, entries = ({}, {}, {})
    f = _i39_deepcopy(forcing)
    if seasonal_mode:
        f, climate_driving, recycled_et_kg = _x129_advance_driver(out, forcing, dt_s)
        results['climate'] = {'fluxes': {key: climate_driving[key] for key in ('rainfall_m_s', 'air_temperature_c', 'precipitation_mm')}, 'ledger': climate_driving['ledger'], 'metadata': climate_driving['seasonal_source']}

    def driver(name):
        value = f.get(name, {})
        if not isinstance(value, dict):
            raise ValueError(name + ' forcing must be a mapping')
        return _i39_deepcopy(value)

    def run(name, module, driving, context, parameters=None):
        if parameters is None:
            result = module(s[name], driving, context, dt_s)
        else:
            result = module(s[name], driving, context, dt_s, parameters=parameters)
        s[name] = result['state']
        results[name] = {key: result[key] for key in ('fluxes', 'ledger', 'metadata')}
        return result
    wind = {'wind_x_m_s': f.get('wind_x_m_s', 0.0), 'wind_z_m_s': f.get('wind_z_m_s', 0.0)}
    vol = run('volcanism', _x130_volcanism_step, {**wind, **driver('volcanism')}, land_ctx, f.get('volcanism_parameters'))
    rad = run('radiation', _x131_radiation_step, {**driver('radiation'), 'time_s': out['time_s']}, ctx, f.get('radiation_parameters'))
    rad['metadata']['clock_policy'] = 'product physical time is authoritative; any declared radiation.time_s is recorded but overridden'
    rain = _x60_array(f.get('rainfall_m_s', 0.0), shape, 'rainfall_m_s') * area * dt_s * land
    infiltration = _i39_np.clip(_i39_np.divide(s['frozen_ground']['liquid_water_m'], s['frozen_ground']['liquid_water_m'] + s['frozen_ground']['ground_ice_m'], out=_i39_np.ones(shape), where=s['frozen_ground']['liquid_water_m'] + s['frozen_ground']['ground_ice_m'] > 0.0), 0.0, 1.0)
    if seasonal_mode:
        soil_rain, aquifer_rain, frozen_rain, runoff_rain = (_i39_np.zeros(shape) for _ in range(4))
    else:
        soil_rain = rain * 0.6 * infiltration
        aquifer_rain = rain * 0.2 * infiltration
        frozen_rain = rain * 0.2
        runoff_rain = rain - soil_rain - aquifer_rain - frozen_rain
    s['frozen_ground']['liquid_water_m'] += frozen_rain / area
    ice = run('frozen_ground', _x132_frozen_ground_step, {**driver('frozen_ground'), 'air_temperature_c': f.get('air_temperature_c', 10.0), 'ground_heat_w_m2': rad['fluxes']['net_ground_heat_w_m2'], 'geothermal_heat_w_m2': vol['fluxes']['geothermal_heat_w_m2']}, land_ctx, f.get('frozen_ground_parameters'))
    if seasonal_mode:
        snow, bucket = _x133_snow_and_bucket(out, f, dt_s, rad, ice['fluxes']['infiltration_factor'])
        results['seasonal_snow'] = snow
        soil_rain = bucket['infiltration_m3']
        runoff_rain = bucket['release_m3']
        results['seasonal_soil'] = {'fluxes': bucket, 'ledger': {key: float(value.sum()) for key, value in bucket.items()}, 'metadata': {'algorithm': 'existing-regional-soil-bucket-seasonal-adapter-v1', 'parameters': out['seasonal']['runoff_parameters'], 'phase_policy': 'G7 liquid consumed once; no second PET phase decision', 'infiltration_policy': 'G12 liquid/(liquid+ground ice) scales G5 infiltration capacity'}}
    packets = out['pending_packets']
    water_packet = soil_rain + packets['soil_water_m3']
    salt_concentration = _i39_np.divide(packets['soil_salt_kg'], water_packet, out=_i39_np.zeros(shape), where=water_packet > 0.0)
    soil_driver = driver('soil_chemistry')
    soil_et_m3 = rad['fluxes']['potential_evaporation_m'] * area
    if seasonal_mode:
        soil_driver['drainage_m3_s'] = bucket['percolation_m3'] / dt_s
        soil_et_m3 = bucket['actual_et_m3']
    demand = area * _x134_SUCCESSION_PARAMETERS['growth_carbon_kg_m2_s'] * dt_s * _x134_SUCCESSION_PARAMETERS['nutrient_kg_per_carbon_kg'] * land
    soil = run('soil_chemistry', _x135_soil_chemistry_step, {**soil_driver, 'water_input_m3_s': water_packet / dt_s, 'inflow_salinity_kg_m3': salt_concentration, 'evaporation_m3_s': soil_et_m3 / dt_s, 'litter_carbon_kg': packets['litter_carbon_kg'], 'plant_nutrient_return_kg': packets['plant_nutrient_return_kg'], 'plant_uptake_demand_kg': demand}, land_ctx)
    if seasonal_mode:
        if not _i39_np.allclose(s['soil_chemistry']['water_m3'], bucket['soil_end_m3'], rtol=1e-12, atol=1e-10):
            raise ValueError('G5 and sole chemistry soil-water owner diverged')
        window = _x136_driver_slices(ctx, out['seasonal']['climate_driver'])
        out['seasonal']['pending_et_kg'][window] = bucket['actual_et_m3'] * 1000.0
    packets.update({name: _i39_np.zeros(shape) for name in PACKETS[:4]})
    packets['subsurface_salt_kg'] += soil['fluxes']['salt_leached_kg']
    packets['subsurface_nutrient_kg'] += soil['fluxes']['nutrient_leached_kg']
    moisture = _i39_np.clip(s['soil_chemistry']['water_m3'] / (area * 0.2), 0.0, 1.0)
    plant_stress = soil['fluxes']['plant_stress_factor']
    if land_cover_mode:
        import terrain_pipeline.soil_water as land_cover
        consumed_land_cover = land_cover.assess(out)
        plant_stress = plant_stress * consumed_land_cover['growth_support_factor']
        results['land_cover'] = {'fluxes': {key: consumed_land_cover[key] for key in ('growth_support_factor', 'suitability', 'soil_thickness_bulk_m', 'land_cover_index')}, 'ledger': {}, 'metadata': consumed_land_cover['adapter']}
    plant = run('succession', _x137_succession_step, {**driver('succession'), 'plant_nutrient_uptake_kg': soil['fluxes']['plant_uptake_kg'], 'plant_stress_factor': plant_stress, 'water_available_fraction': moisture, 'temperature_c': f.get('air_temperature_c', 10.0)}, land_ctx)
    packets['litter_carbon_kg'] = plant['fluxes']['litter_carbon_kg'].copy()
    packets['plant_nutrient_return_kg'] = plant['fluxes']['plant_nutrient_return_kg'].copy()
    matter = run('mass', _x138_mass_step, {**driver('mass'), 'temperature_c': f.get('air_temperature_c', 10.0), 'moisture': moisture, 'bio_activity': plant['fluxes']['cover_fraction'], 'root_cohesion_pa': plant['fluxes']['root_cohesion_pa']}, land_ctx)
    sand = run('aeolian', _x139_aeolian_step, {**wind, **driver('aeolian'), 'water_saturation': moisture, 'vegetation_cover': plant['fluxes']['cover_fraction']}, ctx, f.get('aeolian_parameters'))
    gw = run('groundwater', _x140_groundwater_step, {**driver('groundwater'), 'recharge_m3': _i39_np.zeros(shape) if seasonal_mode else aquifer_rain + soil['fluxes']['drainage_m3'] + ice['fluxes']['snow_meltwater_m'] * area, 'surface_input_m3': runoff_rain, 'surface_conductance_m2_s': _x60_array(driver('groundwater').get('surface_conductance_m2_s', 0.001), shape, 'surface conductance') * 0.025 / plant['fluxes']['manning_n']}, land_ctx)
    if handoff_mode:
        hydraulic_water = _i39_np.where(handoff_mask, s['groundwater']['surface_water_m3'], 0.0)
        hydraulic_solid = _i39_np.where(handoff_mask, s['mass']['river_sediment_solid_m3'], 0.0)
        s['groundwater']['surface_water_m3'] -= hydraulic_water
        s['mass']['river_sediment_solid_m3'] -= hydraulic_solid
        s['mass']['downstream_delivered_solid_m3'] += hydraulic_solid
        transfers.update(external_hydraulic_water_m3=hydraulic_water, external_hydraulic_solid_m3=hydraulic_solid)
        entries.update(external_hydraulic_water_m3=float(hydraulic_water.sum()), external_hydraulic_solid_m3=float(hydraulic_solid.sum()))
    s['groundwater']['surface_water_m3'], coast_water, water_export = _route_packet(s['groundwater']['surface_water_m3'], ctx, dt_s, plant['fluxes']['manning_n'])
    s['mass']['river_sediment_solid_m3'], coast_solid, solid_export = _route_packet(s['mass']['river_sediment_solid_m3'], ctx, dt_s, plant['fluxes']['manning_n'])
    direct_ocean_solid = s['mass']['ocean_export_solid_m3'] - old_mass['ocean_export_solid_m3']
    coast_solid += direct_ocean_solid
    s['mass']['downstream_delivered_solid_m3'] += coast_solid - direct_ocean_solid + solid_export
    coastal = None
    if ctx['ocean_mask'].any():
        mouth = coast_water + coast_solid > 0.0
        coast_driver = driver('coastal_exchange')
        if 'soil_exchange_m3_s' in coast_driver:
            coast_driver['soil_exchange_m3_s'] = _x60_array(coast_driver['soil_exchange_m3_s'], shape, 'soil_exchange_m3_s') * land
        coastal = run('coastal_exchange', _x141_coastal_exchange_step, {**coast_driver, 'mouth_mask': mouth, 'river_boundary_water_m3_s': coast_water / dt_s, 'river_boundary_solid_m3_s': coast_solid / dt_s}, ctx)
        packets['soil_water_m3'] = coastal['fluxes']['soil_water_m3'].copy()
        packets['soil_salt_kg'] = coastal['fluxes']['soil_salt_kg'].copy()
    animal = run('habitat', _x142_habitat_step, {**driver('habitat'), 'vegetation_cover_fraction': plant['fluxes']['cover_fraction'], 'water_available_fraction': moisture, 'water_temperature_c': f.get('air_temperature_c', 10.0), 'disturbance_fraction': s['succession']['disturbance_fraction']}, ctx)
    mass_bulk_change = s['mass']['regolith_bulk_m3'] - old_mass['regolith_bulk_m3'] + (s['mass']['soil_solid_m3'] - old_mass['soil_solid_m3'] + s['mass']['hillslope_deposit_solid_m3'] - old_mass['hillslope_deposit_solid_m3']) / (1.0 - s['mass']['regolith_porosity']) - matter['fluxes']['weathered_solid_m3']
    bed_change = mass_bulk_change / area + ice['fluxes']['height_change_m'] + vol['fluxes']['height_change_m'] + sand['fluxes']['height_change_m']
    if coastal:
        bed_change += s['coastal_exchange']['bed_m'] - product['states']['coastal_exchange']['bed_m']
    bed_change[~ctx['valid_mask'] | ctx['protected_mask']] = 0.0
    s['network_transition'] = _x125_network_transition_initial_state(ctx, water_m3=s['groundwater']['surface_water_m3'], sediment_solid_m3=s['mass']['river_sediment_solid_m3'], floodplain_solid_m3=s['mass']['hillslope_deposit_solid_m3'])
    if seasonal_mode:
        results['network_transition'] = {'fluxes': {'diagnostic_bed_change_m': bed_change.copy()}, 'ledger': {name + '_residual': 0.0 for name in _x143_INVENTORIES}, 'metadata': {'algorithm': _x144_NETWORK_ALGORITHM, 'status': 'frozen_saved_network', 'dt_s': float(dt_s), 'parameters': {}, 'policy': 'keep saved receiver and water geometry; no natural capture advancement'}}
    else:
        proposed = _x145_network_transition_step(s['network_transition'], {'bed_change_m': bed_change}, ctx, dt_s)
        committed = _x146_commit_transition(s['network_transition'], proposed, ctx)
        s['network_transition'] = committed['state']
        results['network_transition'] = {key: committed[key] for key in ('fluxes', 'ledger', 'metadata')}
        ctx['height_m'] = committed['state']['height_m'].copy()
        ctx['receiver'] = committed['state']['receiver'].copy()
        if _i39_np.any(bed_change):
            ctx['active_routing_policy'] = ctx['routing_policy']
    s['coastal_exchange']['bed_m'] = ctx['height_m'].copy()
    if land_cover_mode:
        out['seasonal']['land_cover'] = land_cover.assess(out)
    transfers.update(rainfall_m3=rain, rain_to_soil_m3=soil_rain, rain_to_aquifer_m3=aquifer_rain, rain_to_frozen_m3=frozen_rain, rain_to_runoff_m3=runoff_rain, river_to_coast_water_m3=coast_water, river_to_coast_solid_m3=coast_solid, window_water_export_m3=water_export, window_solid_export_m3=solid_export, soil_nutrient_to_plant_kg=soil['fluxes']['plant_uptake_kg'], litter_to_pending_kg=packets['litter_carbon_kg'], soil_root_cohesion_pa=plant['fluxes']['root_cohesion_pa'], hydraulic_manning_n=plant['fluxes']['manning_n'], derived_bed_change_m=bed_change)
    entries.update(rainfall_m3=float(rain.sum()), evaporation_m3=soil['ledger']['evaporation_m3'], window_water_export_m3=float(water_export.sum()), pumping_m3=gw['ledger']['pumping_m3'], ocean_water_input_m3=coastal['ledger']['signed_ocean_water_m3'] if coastal else 0.0, eruption_solid_input_m3=vol['ledger']['event_input_solid_m3'], solid_boundary_export_m3=float(solid_export.sum()) + sand['ledger']['boundary_export_solid_m3'] + vol['ledger']['boundary_export_solid_m3'], dissolved_solid_export_m3=float((s['mass']['dissolved_solid_m3'] - old_mass['dissolved_solid_m3']).sum()), photosynthesis_carbon_kg=plant['ledger']['photosynthesis_carbon_kg'], atmosphere_carbon_export_kg=plant['ledger']['fire_atmosphere_carbon_kg'] + soil['ledger']['respired_carbon_kg'], salt_boundary_input_kg=coastal['ledger']['signed_ocean_salt_kg'] if coastal else 0.0, salt_boundary_export_kg=0.0, nutrient_boundary_input_kg=soil['ledger']['nutrient_input_kg'] + soil['ledger']['litter_nutrient_kg'], nutrient_boundary_export_kg=0.0)
    if seasonal_mode:
        snow_fluxes = snow['fluxes']
        transfers.update({'seasonal_' + key: value for key, value in snow_fluxes.items()})
        transfers.update(g5_infiltration_m3=bucket['infiltration_m3'], g5_percolation_m3=bucket['percolation_m3'], g5_et_m3=bucket['actual_et_m3'], g5_release_m3=bucket['release_m3'], g5_fast_release_m3=bucket['fast_release_m3'], g5_slow_release_m3=bucket['slow_release_m3'], seasonal_et_recycle_kg=recycled_et_kg)
        climate_ledger = climate_driving['ledger']
        entries.update(atmosphere_inflow_m3=float(climate_ledger['inflow_kg']) / 1000.0, atmosphere_outflow_m3=float(climate_ledger['outflow_kg']) / 1000.0, precipitation_unmodelled_export_m3=float(climate_ledger['precipitation_kg']) / 1000.0 - float(rain.sum()), sublimation_m3=float(snow_fluxes['sublimation_m3'].sum()), seasonal_et_recycle_kg=float(recycled_et_kg.sum()))
    after = _x59_inventory_totals(out)
    net = {'water_m3': entries['rainfall_m3'] + entries['ocean_water_input_m3'] - entries['evaporation_m3'] - entries['window_water_export_m3'] - entries['pumping_m3'], 'solid_m3': entries['eruption_solid_input_m3'] - entries['solid_boundary_export_m3'] - entries['dissolved_solid_export_m3'], 'carbon_kg': entries['photosynthesis_carbon_kg'] - entries['atmosphere_carbon_export_kg'], 'salt_kg': entries['salt_boundary_input_kg'] - entries['salt_boundary_export_kg'], 'nutrient_kg': entries['nutrient_boundary_input_kg'] - entries['nutrient_boundary_export_kg']}
    if seasonal_mode:
        net['water_m3'] = _x147_net_water(entries)
    if handoff_mode:
        net['solid_m3'] -= entries['external_hydraulic_solid_m3']
        if not seasonal_mode:
            net['water_m3'] -= entries['external_hydraulic_water_m3']
    budget = {name + '_residual': before[name] + net[name] - after[name] for name in before}
    for name, residual in budget.items():
        key = name.removesuffix('_residual')
        if abs(residual) > 1e-09 * max(1.0, abs(before[key]), abs(after[key])):
            raise ValueError('coupled product inventory does not close: ' + name)
    absorbed_j = rad['ledger']['absorbed_j']
    solar_ground_j = float(rad['fluxes']['net_ground_heat_w_m2'].sum() * area * dt_s)
    solar_to_frozen_j = float((rad['fluxes']['net_ground_heat_w_m2'] * land).sum() * area * dt_s)
    potential_et_j = float(rad['fluxes']['potential_evaporation_m'].sum() * area * 2450000000.0)
    actual_et_j = entries['evaporation_m3'] * 2450000000.0
    old_frozen = product['states']['frozen_ground']
    thermal_p = ice['metadata']['parameters']
    air = _x60_array(f.get('air_temperature_c', 10.0), shape, 'air_temperature_c', nonnegative=False)
    air_heat_j = float((thermal_p['air_exchange_w_m2_k'] * (air - old_frozen['soil_temperature_c']) / (1.0 + thermal_p['snow_insulation_per_m_swe'] * old_frozen['snow_swe_m']) * land).sum() * area * dt_s)
    geothermal_to_frozen_j = float((vol['fluxes']['geothermal_heat_w_m2'] * land).sum() * area * dt_s)
    energy_budget = {'solar_absorbed_j': absorbed_j, 'solar_to_frozen_j': solar_to_frozen_j, 'unused_ocean_or_inactive_ground_shortwave_j': solar_ground_j - solar_to_frozen_j, 'actual_evaporation_latent_j': actual_et_j, 'unused_potential_evaporation_j': max(potential_et_j - actual_et_j, 0.0), 'shortwave_partition_residual_j': absorbed_j - solar_ground_j - potential_et_j, 'geothermal_to_frozen_j': geothermal_to_frozen_j, 'air_to_frozen_j': air_heat_j, 'frozen_heat_supply_residual_j': ice['ledger']['heat_input_j'] - solar_to_frozen_j - geothermal_to_frozen_j - air_heat_j, 'frozen_enthalpy_residual_j': ice['ledger']['energy_residual_j'], 'volcanic_heat_residual_j': vol['ledger']['heat_residual_j']}
    for name in ('shortwave_partition_residual_j', 'frozen_heat_supply_residual_j', 'frozen_enthalpy_residual_j', 'volcanic_heat_residual_j'):
        if abs(energy_budget[name]) > 1e-09 * max(1.0, abs(absorbed_j), abs(ice['ledger']['heat_input_j']), abs(vol['ledger']['cooling_heat_j'])):
            raise ValueError('coupled product energy does not close: ' + name)
    entries.update({name: value for name, value in energy_budget.items() if 'residual' not in name})
    for name, amount in entries.items():
        out['cumulative_ledger'][name] = out['cumulative_ledger'].get(name, 0.0) + amount
    out.update(results=results, last_transfers=transfers, last_budget=budget, last_energy_budget=energy_budget, time_s=out['time_s'] + dt_s, step_index=out['step_index'] + 1)
    out['parameters']['process_parameters'] = {name: result['metadata'].get('parameters', result['metadata'].get('weathering_parameters', {})) for name, result in results.items()}
    out['forcing_history'].append({'start_time_s': product['time_s'], 'dt_s': float(dt_s), 'declaration': _i39_deepcopy(forcing)})
    return out

def _validate_product(product):
    """Static checks only: cold loading does not route, sample or advance."""
    from terrain_pipeline.soil_water import is_seasonal as _x127_is_seasonal
    from terrain_pipeline.soil_water import ALGORITHM_V2 as _x128_ALGORITHM_V2
    from terrain_pipeline.soil_water import net_water as _x147_net_water
    from terrain_pipeline.soil_water import ALGORITHMS as _x148_ALGORITHMS
    from terrain_pipeline.soil_water import seasonal_coupling_validate as _x149_seasonal_coupling_validate
    from terrain_pipeline.environment_processes import inventory_totals as _x59_inventory_totals
    if product.get('schema') != STORAGE_SCHEMA or product.get('algorithm') not in (STORAGE_ALGORITHM, EXPLICIT_V2_ALGORITHM) + _x148_ALGORITHMS:
        raise ValueError('invalid environment process product')
    ctx = product['context']
    shape = _i39_np.asarray(ctx['height_m']).shape
    if len(shape) != 2 or not 0 < _i39_math.prod(shape) <= STORAGE_MAX_CELLS:
        raise ValueError('invalid finite product shape')
    if set(product['states']) != set(MODULES) | {'mass', 'groundwater', 'network_transition'}:
        raise ValueError('incomplete process state')
    for name, state in product['states'].items():
        for field, value in state.items():
            data = _i39_np.asarray(value)
            if data.shape != shape or data.dtype.kind not in 'biuf' or (not _i39_np.isfinite(data).all()):
                raise ValueError('invalid persistent state array: ' + name + '.' + field)
    if not _i39_np.array_equal(product['states']['network_transition']['height_m'], ctx['height_m']):
        raise ValueError('committed height/context mismatch')
    if not _i39_np.array_equal(product['states']['network_transition']['receiver'], ctx['receiver']):
        raise ValueError('committed receiver/context mismatch')
    if not _i39_np.isfinite(product['time_s']) or product['time_s'] < 0.0 or product['step_index'] != len(product['forcing_history']):
        raise ValueError('invalid persistent physical time/history')
    ledger = product['cumulative_ledger']
    get = lambda name: float(ledger.get(name, 0.0))
    net = {'water_m3': get('rainfall_m3') + get('ocean_water_input_m3') - get('evaporation_m3') - get('window_water_export_m3') - get('pumping_m3'), 'solid_m3': get('eruption_solid_input_m3') - get('solid_boundary_export_m3') - get('dissolved_solid_export_m3'), 'carbon_kg': get('photosynthesis_carbon_kg') - get('atmosphere_carbon_export_kg'), 'salt_kg': get('salt_boundary_input_kg') - get('salt_boundary_export_kg'), 'nutrient_kg': get('nutrient_boundary_input_kg') - get('nutrient_boundary_export_kg')}
    if _x127_is_seasonal(product):
        _x149_seasonal_coupling_validate(product)
        net['water_m3'] = _x147_net_water(ledger)
        if product['algorithm'] == _x128_ALGORITHM_V2:
            net['solid_m3'] -= get('external_hydraulic_solid_m3')
    if product['algorithm'] == EXPLICIT_V2_ALGORITHM:
        net['water_m3'] -= get('external_hydraulic_water_m3')
        net['solid_m3'] -= get('external_hydraulic_solid_m3')
    current = _x59_inventory_totals(product)
    for name, amount in current.items():
        initial = float(product['initial_inventory'][name])
        if abs(initial + net[name] - amount) > 1e-09 * max(1.0, abs(initial), abs(amount)):
            raise ValueError('persistent coupled inventory mismatch: ' + name)
WORLD_ALGORITHM = 'environment-world-product-v1'
WORLD_SCHEMA = 'environment-world-product-v1'
STATUS_COMPUTED = 'computed'
STATUS_DECLARED = 'declared'
STATUS_PENDING = 'pending'
STATUS_NOT_AVAILABLE = 'not_available'
FIELD_STATUS = (STATUS_COMPUTED, STATUS_DECLARED, STATUS_PENDING, STATUS_NOT_AVAILABLE)
FIELD_SPECS = {'elevation_m': ('m', 'per_cell'), 'porosity': ('1', 'per_cell'), 'bed_hardness': ('1', 'per_cell'), 'solubility': ('1', 'per_cell'), 'parent_solid_m3': ('m3', 'per_cell'), 'parent_bulk_m3': ('m3', 'per_cell'), 'monthly_temperature_c': ('degC_monthly_mean', 'monthly'), 'annual_temperature_c': ('degC_annual_mean', 'per_cell'), 'water_state_mm': ('mm', 'state3'), 'water_state_total_mm': ('mm', 'per_cell'), 'soil_thickness_bulk_m': ('m_bulk', 'per_cell'), 'soil_water_capacity_mm': ('mm', 'per_cell'), 'suitability': ('1_normalised', 'per_cell'), 'land_cover_index': ('ordinal', 'per_cell'), 'snow_state': ('mm_equivalent_water', 'per_cell')}
WORLD_MAX_CELLS = 262144

def _canonical(payload):
    return _i41_json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)

def _digest(payload):
    return _i41_hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()

def _array_digest(array):
    values = _i41_np.ascontiguousarray(_i41_np.asarray(array))
    hasher = _i41_hashlib.sha256()
    hasher.update(str(values.shape).encode('ascii'))
    hasher.update(values.dtype.str.encode('ascii'))
    hasher.update(values.tobytes(order='C'))
    return hasher.hexdigest()

def _points_digest(x_m, z_m):
    """与点序无关的点集摘要（按 (x, z) 排序后取字节）。"""
    x = _i41_np.asarray(x_m, _i41_np.float64).reshape(-1)
    z = _i41_np.asarray(z_m, _i41_np.float64).reshape(-1)
    order = _i41_np.lexsort((z, x))
    return _array_digest(_i41_np.stack((x[order], z[order])))

def _point_order(x_m, z_m):
    x = _i41_np.asarray(x_m, _i41_np.float64).reshape(-1)
    z = _i41_np.asarray(z_m, _i41_np.float64).reshape(-1)
    return _i41_np.lexsort((z, x))

@_i41_dataclass(frozen=True)
class WorldProduct:
    """一组同坐标字段 + 四层身份 + 逐字段状态。不可变。"""
    arrays: dict
    status: dict
    units: dict
    world_identity: str
    source_identity: str
    model_identity: str
    time_identity: str
    record: dict

    def __post_init__(self):
        if not isinstance(self.arrays, dict) or not self.arrays:
            raise ValueError('arrays 必须是非空字典')
        cells = None
        for name, value in self.arrays.items():
            if name not in FIELD_SPECS:
                raise ValueError('未声明的字段：%r' % (name,))
            unit, kind = FIELD_SPECS[name]
            array = _i41_np.asarray(value)
            if kind == 'per_cell':
                if array.ndim != 1:
                    raise ValueError('%s 必须是 [N]' % (name,))
            elif kind == 'monthly':
                if array.ndim != 2 or array.shape[0] != 12:
                    raise ValueError('%s 必须是 [12, N]' % (name,))
            elif kind == 'state3':
                if array.ndim != 2 or array.shape[0] != 3:
                    raise ValueError('%s 必须是 [3, N]' % (name,))
            width = array.shape[-1]
            if cells is None:
                cells = width
            elif width != cells:
                raise ValueError('%s 的列数与其它字段不一致' % (name,))
            if name not in self.status:
                raise ValueError('字段 %r 缺少状态' % (name,))
            if self.status[name] not in FIELD_STATUS:
                raise ValueError('字段 %r 的状态 %r 不在允许集合内' % (name, self.status[name]))
        if not 1 <= cells <= WORLD_MAX_CELLS:
            raise ValueError('列数超出 1..%d' % (WORLD_MAX_CELLS,))
        for label in ('world_identity', 'source_identity', 'model_identity', 'time_identity'):
            value = getattr(self, label)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError('%s 必须是 64 位十六进制摘要' % (label,))

    @property
    def cells(self):
        return int(_i41_np.asarray(self.arrays['elevation_m']).size)

    def count_status(self, status):
        return sorted((name for name, value in self.status.items() if value == status))

def world_assemble(*, city_name, world_seed, spacing_m, x_m, z_m, fields, statuses, source_identities, model_parameters, time_record=None):
    """把各生产者**在同一组坐标上**的结果装配成产品。

    不计算任何物理量：``fields`` 里的每个数组必须由调用方从已有生产者拿到。

    参数
    ----
    x_m, z_m : [N] 绝对世界米坐标（30 m 格）。**不吸附**：非格心坐标必须由调用方
        事先显式处理并在 ``source_identities`` 里记录接受偏移；本函数只校验有限性。
    fields : {字段名: 数组}，名必须属于 :data:`FIELD_SPECS`。
    statuses : {字段名: 状态}，每个字段必须有状态。
    source_identities : 各输入源的身份字典（distinct 名字 → identity 或记录）。
    model_parameters : 模型参数（含 G6 参数身份）。
    time_record : 可选，时变字段的时间声明。
    """
    if not isinstance(world_seed, int) or isinstance(world_seed, bool) or world_seed < 0:
        raise ValueError('world_seed 必须是非负整数')
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or (not _i41_math.isfinite(spacing_m)) or (spacing_m <= 0):
        raise ValueError('spacing_m 必须是有限正数')
    x = _i41_np.asarray(x_m, _i41_np.float64).reshape(-1)
    z = _i41_np.asarray(z_m, _i41_np.float64).reshape(-1)
    if x.size != z.size or x.size == 0:
        raise ValueError('x_m/z_m 必须等长且非空')
    if not _i41_np.isfinite(x).all() or not _i41_np.isfinite(z).all():
        raise ValueError('坐标必须有限')
    if max(float(_i41_np.max(_i41_np.abs(x))), float(_i41_np.max(_i41_np.abs(z)))) > 1000000000000.0:
        raise ValueError('坐标超出支持范围')
    cells = int(x.size)
    if cells > WORLD_MAX_CELLS:
        raise ValueError('列数超出 %d' % (WORLD_MAX_CELLS,))
    for name in fields:
        if name not in FIELD_SPECS:
            raise ValueError('未声明的字段：%r' % (name,))
    if set(fields) != set(statuses):
        raise ValueError('fields 与 statuses 的字段集必须一致')
    required = ('elevation_m', 'annual_temperature_c', 'water_state_mm')
    missing = [name for name in required if name not in fields]
    if missing:
        raise ValueError('联合产品缺必要同坐标字段：%r' % (missing,))
    arrays = {}
    units = {}
    for name, value in fields.items():
        unit, _kind = FIELD_SPECS[name]
        arrays[name] = _i41_np.asarray(value, _i41_np.float64)
        units[name] = unit
    record = {'city_name': city_name, 'world_seed': int(world_seed), 'spacing_m': float(spacing_m), 'cells': cells, 'coordinate_semantics': '绝对世界米；调用方提供的坐标原样进入身份，本模块从不吸附或移动', 'fields': sorted(fields), 'status_counts': {status: sorted((n for n, s in statuses.items() if s == status)) for status in FIELD_STATUS if any((s == status for s in statuses.values()))}}
    world_identity = _digest({'schema': WORLD_SCHEMA, 'world_seed': int(world_seed), 'spacing_m': float(spacing_m), 'points_sha256': _points_digest(x, z)})
    source_identity = _digest({'schema': WORLD_SCHEMA, 'sources': source_identities})
    model_identity = _digest({'schema': WORLD_SCHEMA, 'parameters': model_parameters, 'fields': sorted(fields)})
    time_identity = _digest({'schema': WORLD_SCHEMA, 'time': time_record if time_record is not None else None})
    return WorldProduct(arrays=arrays, status=dict(statuses), units=units, world_identity=world_identity, source_identity=source_identity, model_identity=model_identity, time_identity=time_identity, record={**record, 'x_m': x, 'z_m': z})

def world_save(product, arrays_path, record_path):
    """保存为 ``.npz``（数组）+ ``.json``（元数据）。**不覆盖**已有文件。"""
    if not isinstance(product, WorldProduct):
        raise ValueError('WorldProduct required')
    import os
    for path in (arrays_path, record_path):
        if os.path.exists(path):
            raise FileExistsError(path)
    payload = dict(product.arrays)
    payload['x_m'] = _i41_np.asarray(product.record['x_m'], _i41_np.float64)
    payload['z_m'] = _i41_np.asarray(product.record['z_m'], _i41_np.float64)
    meta = {'schema': WORLD_SCHEMA, 'algorithm': WORLD_ALGORITHM, 'record': {k: v for k, v in product.record.items() if k not in ('x_m', 'z_m')}, 'status': product.status, 'units': product.units, 'world_identity': product.world_identity, 'source_identity': product.source_identity, 'model_identity': product.model_identity, 'time_identity': product.time_identity}
    _i41_np.savez_compressed(arrays_path, **payload)
    with open(record_path, 'w', encoding='utf-8') as stream:
        _i41_json.dump(meta, stream, ensure_ascii=False, indent=1, allow_nan=False, sort_keys=True)
    return meta

def world_load(arrays_path, record_path, *, expected_world_identity=None):
    """读回产品。只做一致性校验，不重算物理量。"""
    with open(record_path, 'r', encoding='utf-8') as stream:
        meta = _i41_json.load(stream)
    if meta.get('schema') != WORLD_SCHEMA:
        raise ValueError('未知的 schema：%r' % (meta.get('schema'),))
    if expected_world_identity is not None and meta.get('world_identity') != expected_world_identity:
        raise ValueError('world_identity 与期望不符（产品属于另一套坐标）')
    with _i41_np.load(arrays_path, allow_pickle=False) as archive:
        stored = {name: _i41_np.asarray(archive[name], _i41_np.float64) for name in archive.files}
    for key in ('x_m', 'z_m'):
        if key not in stored:
            raise ValueError('产品缺少坐标数组：%r' % (key,))
    arrays = {name: value for name, value in stored.items() if name not in ('x_m', 'z_m')}
    record = dict(meta['record'])
    record['x_m'] = stored['x_m']
    record['z_m'] = stored['z_m']
    return WorldProduct(arrays=arrays, status=dict(meta['status']), units=dict(meta['units']), world_identity=meta['world_identity'], source_identity=meta['source_identity'], model_identity=meta['model_identity'], time_identity=meta['time_identity'], record=record)

def world_query(product, x_query_m, z_query_m, *, accept_offset_m=None):
    """在同坐标产品上**只读**取字段。

    不生成、不推进、不改写产品。请求点必须**恰好**落在产品格点上；若不完全重合，
    需要调用方显式传入 ``accept_offset_m`` 接受实测偏移——本函数**从不吸附**。
    """
    if not isinstance(product, WorldProduct):
        raise ValueError('WorldProduct required')
    qx = _i41_np.asarray(x_query_m, _i41_np.float64).reshape(-1)
    qz = _i41_np.asarray(z_query_m, _i41_np.float64).reshape(-1)
    if qx.size != qz.size or qx.size == 0:
        raise ValueError('查询坐标必须等长且非空')
    if not _i41_np.isfinite(qx).all() or not _i41_np.isfinite(qz).all():
        raise ValueError('查询坐标必须有限')
    px = _i41_np.asarray(product.record['x_m'], _i41_np.float64)
    pz = _i41_np.asarray(product.record['z_m'], _i41_np.float64)
    index = _i41_np.full(qx.size, -1, _i41_np.int64)
    offset = _i41_np.full(qx.size, _i41_np.inf, _i41_np.float64)
    for cell in range(px.size):
        distance = _i41_np.hypot(qx - px[cell], qz - pz[cell])
        better = distance < offset
        offset = _i41_np.where(better, distance, offset)
        index = _i41_np.where(better, cell, index)
    if accept_offset_m is None:
        if _i41_np.any(offset > 1e-09):
            raise ValueError('查询点不在产品格点上：实测最大偏移 %.6f m。需要时显式传 accept_offset_m；本接口从不吸附坐标' % (float(_i41_np.max(offset)),))
    else:
        limit = float(accept_offset_m)
        if not _i41_math.isfinite(limit) or limit < 0:
            raise ValueError('accept_offset_m 必须是非负有限值')
        if float(_i41_np.max(offset)) > limit + 1e-09:
            raise ValueError('实测偏移 %.6f m 超过允许的 %.6f m' % (float(_i41_np.max(offset)), limit))
    result = {'cell_index': index, 'offset_m': offset, 'snapped': False, 'cells': int(qx.size)}
    for name, array in product.arrays.items():
        _kind = FIELD_SPECS[name][1]
        if _kind == 'per_cell':
            result[name] = _i41_np.asarray(array)[index]
        else:
            result[name] = _i41_np.asarray(array)[:, index]
    result['status'] = {name: product.status[name] for name in product.arrays}
    result['world_identity'] = product.world_identity
    return result

def world_describe():
    """静态声明，供审查与下游引用（无数值影响）。"""
    return {'schema': WORLD_SCHEMA, 'algorithm': WORLD_ALGORITHM, 'field_specs': {name: {'units': unit, 'shape': kind} for name, (unit, kind) in FIELD_SPECS.items()}, 'required_fields': ['elevation_m', 'annual_temperature_c', 'water_state_mm'], 'max_cells': WORLD_MAX_CELLS, 'statuses': list(FIELD_STATUS), 'identities': ['world_identity', 'source_identity', 'model_identity', 'time_identity'], 'separations': {'assemble': '组合，不算物理量', 'query': '只读，不生成不推进不改写', 'load': '只读回内存，不重算'}, 'never': ['把缺来源的字段当零', '吸附或移动调用方坐标', '把库存量与水深/mm 互相派生', '把宏观网格插值成 30 m 原生格', '用一个总哈希代替四层身份']}

def atomic_npz(path, **arrays):
    path = _i43_Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('wb') as stream:
        _i43_np.savez(stream, **arrays)
    _i43_os.replace(temporary, path)

def prepare_world_acceptance_processes(terrain_path, output_dir, *, spinup_years=1, river_display_q_m3_s=2.0, resume=False):
    """Produce final-year seasonal fields and route that year's runoff from dry lakes."""
    from terrain_pipeline.channel_geometry import DischargeGeometryConfig as _i43_DischargeGeometryConfig
    from terrain_pipeline.drainage import accumulate_graph as _i43_accumulate_graph
    from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry as _i43_build_irregular_channel_geometry
    from terrain_pipeline.drainage import build_mesh as _i43_build_mesh
    from terrain_pipeline.common_infra import file_sha256 as _i43_file_sha256
    from terrain_pipeline.drainage import route_graph as _i43_route_graph
    from terrain_pipeline.soil_water import initial_state as _x150_initial_state
    from terrain_pipeline.soil_water import advance as _x151_advance
    from terrain_pipeline.climate_forcing import couple_td_climate as _x159_couple_td_climate
    from terrain_pipeline.climate_forcing import native_climate_sampler as _x160_native_climate_sampler
    from terrain_pipeline.climate_forcing import boundary_influence_mask as _x161_boundary_influence_mask
    from terrain_pipeline.climate_forcing import TD_CLIMATE_CHANNELS as _x162_TD_CLIMATE_CHANNELS
    from terrain_pipeline.soil_water import advance_cover_carbon as _x163_advance_cover_carbon
    from terrain_pipeline.soil_water import constant_month_soil as _x164_constant_month_soil
    from terrain_pipeline.drainage import pool_labels as _x165_pool_labels
    from terrain_pipeline.drainage import route_pool_interval as _x166_route_pool_interval
    from terrain_pipeline.basin_storage import PoolStorage as _x167_PoolStorage
    from terrain_pipeline.soil_water import advance_snow_ice as _x64_advance_snow_ice
    from terrain_pipeline.soil_water import SnowParameters as _x65_SnowParameters
    from terrain_pipeline.climate_forcing import sample_climate_v2 as _x66_sample_climate_v2
    from terrain_pipeline.climate_forcing import RefinedClimateParameters as _x67_RefinedClimateParameters
    from terrain_pipeline.climate_forcing import MONTH_DAYS as _x68_MONTH_DAYS
    from terrain_pipeline.climate_forcing import YEAR_S as _x69_YEAR_S
    from terrain_pipeline.geology import sample_lithology_points as _x71_sample_lithology_points
    from terrain_pipeline.geology import rock_table as _x72_rock_table
    from terrain_pipeline.soil_water import assess_land_cover as _x73_assess_land_cover
    started = _i43_time.perf_counter()
    output = _i43_Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_sha256 = _i43_file_sha256(terrain_path)
    with _i43_np.load(terrain_path, allow_pickle=False) as source:
        elevation = _i43_np.asarray(source['elevation_m'], _i43_np.float64)
        ocean = _i43_np.asarray(source['ocean_mask'], bool)
        td_climate = _i43_np.asarray(source['climate_base'], _i43_np.float64)
        raw_td = _i43_np.asarray(source['raw_td_m'], _i43_np.float64)
        metadata = _i43_json.loads(str(source['metadata_json'].item()))
    spacing = float(metadata['spacing_m'])
    origin = _i43_np.asarray(metadata['origin_xz_m'], _i43_np.float64)
    seed = int(metadata.get('world_seed', 20261020))
    if spacing != 90.0 or elevation.ndim != 2 or ocean.shape != elevation.shape or (not _i43_np.isfinite(elevation).all()) or (origin.shape != (2,)) or (not _i43_np.isfinite(origin).all()) or (seed != 20261020) or (type(spinup_years) is not int) or (not 0 <= spinup_years <= 5) or (not _i43_np.isfinite(river_display_q_m3_s)) or (river_display_q_m3_s <= 0):
        raise ValueError('finite same-source 90 m terrain, fixed seed and bounded spinup required')
    shape, count, area = (elevation.shape, elevation.size, spacing ** 2)
    flat = _i43_np.arange(count)
    x = origin[0] + flat % shape[1] * spacing
    z = origin[1] + flat // shape[1] * spacing
    land = ~ocean.ravel()
    sampler, climate_support = _x160_native_climate_sampler(metadata)
    climate_parameters = _x67_RefinedClimateParameters()
    radius = climate_parameters.orographic_scale_m + max((abs(v) for v in climate_parameters.ridge_offsets_m))
    sampler(_i43_np.array([x.min() - radius, x.max() + radius]), _i43_np.array([z.min() - radius, z.max() + radius]))
    monthly_temperature = _i43_np.empty((12, count), _i43_np.float64)
    monthly_precipitation = _i43_np.empty_like(monthly_temperature)
    cv_fallback = _i43_np.zeros(count, bool)
    if td_climate.shape != (5, *shape) or raw_td.shape != shape:
        raise ValueError('Same-source terrain must include actual five-channel TD climate_base and raw_td_m')
    td_flat = td_climate.reshape(5, count)
    cache_path = output / 'climate-cache.npz'
    checkpoint_path = output / 'monthly-checkpoint.npz'
    if resume and cache_path.exists():
        with _i43_np.load(cache_path, allow_pickle=False) as cache:
            if str(cache['source_sha256'].item()) != source_sha256:
                raise ValueError('Climate cache terrain SHA does not match')
            monthly_temperature[:] = cache['monthly_temperature']
            monthly_precipitation[:] = cache['monthly_precipitation']
            cv_fallback[:] = cache['cv_fallback']
            climate_identity = str(cache['climate_identity'].item())
    else:
        for start in range(0, count, 16384):
            stop = min(start + 16384, count)
            climate = _x66_sample_climate_v2(seed, x[start:stop], z[start:stop], elevation.ravel()[start:stop], elevation_sampler=sampler)
            coupled = _x159_couple_td_climate(td_flat[:, start:stop], raw_td.ravel()[start:stop], elevation.ravel()[start:stop], climate)
            monthly_temperature[:, start:stop] = coupled['monthly_temperature_c']
            monthly_precipitation[:, start:stop] = coupled['monthly_precipitation_mm']
            cv_fallback[start:stop] = coupled['precipitation_cv_fallback']
        climate_identity = climate['parameter_identity_sha256']
        atomic_npz(cache_path, monthly_temperature=monthly_temperature, monthly_precipitation=monthly_precipitation, cv_fallback=cv_fallback, source_sha256=_i43_np.array(source_sha256), climate_identity=_i43_np.array(climate_identity))
    lithology = _x71_sample_lithology_points(x, z, world_seed=seed)
    records = _x72_rock_table()
    for name in ('porosity', 'solubility'):
        lithology[name] = _i43_np.array([record[name] for record in records])[lithology['rock_index']]
    states = _i43_np.zeros((3, count), _i43_np.float64)
    swe = _i43_np.zeros(count)
    monthly_runoff = _i43_np.zeros((12, count), _i43_np.float64)
    monthly_snow = _i43_np.zeros((12, count), _i43_np.float32)
    monthly_soil = _i43_np.zeros((12, count), _i43_np.float32)
    monthly_root_water = _i43_np.zeros((12, count), _i43_np.float32)
    ledger = []
    final_start_storage = None
    completed_months = 0
    if resume and checkpoint_path.exists():
        with _i43_np.load(checkpoint_path, allow_pickle=False) as checkpoint:
            checkpoint_metadata = _i43_json.loads(str(checkpoint['metadata_json'].item()))
            if checkpoint_metadata['source_sha256'] != source_sha256 or checkpoint_metadata['spinup_years'] != spinup_years:
                raise ValueError('Monthly checkpoint source or spinup does not match')
            completed_months = checkpoint_metadata['completed_months']
            ledger = checkpoint_metadata['ledger']
            final_start_storage = checkpoint_metadata['final_start_storage']
            states[:] = checkpoint['states']
            swe[:] = checkpoint['swe']
            monthly_runoff[:] = checkpoint['monthly_runoff']
            monthly_snow[:] = checkpoint['monthly_snow']
            monthly_soil[:] = checkpoint['monthly_soil']
            monthly_root_water[:] = checkpoint['monthly_root_water']
        print(f'Resuming after {completed_months} completed months', flush=True)
    for year in range(spinup_years + 1):
        if year == spinup_years and completed_months <= year * 12:
            final_start_storage = float((states[:, land].sum() + swe[land].sum()) * area / 1000.0)
        for month, days in enumerate(_x68_MONTH_DAYS):
            if year * 12 + month < completed_months:
                continue
            liquid = _i43_np.zeros(count)
            sublimation = 0.0
            for start in range(0, count, 16384):
                stop = min(start + 16384, count)
                section = slice(start, stop)
                snow = _x64_advance_snow_ice(swe_start_mm=swe[section], temperature_c=monthly_temperature[month:month + 1, section], precip_mm=monthly_precipitation[month:month + 1, section] * land[section], time_edges_s=_i43_np.array([0.0, float(days * 86400.0)]), x_m=x[section], z_m=z[section], temperature_source='declared_interval', parameters=_x65_SnowParameters(max_swe_mm=100000.0))
                swe[section] = snow['arrays']['swe_edge_mm'][-1]
                liquid[section] = snow['arrays']['liquid_to_land_mm'][0]
                sublimation += float(snow['arrays']['sublimation_mm'][0][land[section]].sum())
            release, et = _x164_constant_month_soil(liquid, states, monthly_temperature[month], days, failure_path=output / f'failed-soil-year{year + 1}-month{month + 1}.npz', frame_metadata=dict(year=year + 1, month=month + 1, source_sha256=source_sha256))
            if year == spinup_years:
                monthly_runoff[month] = release * land * area / 1000.0
                monthly_snow[month] = swe
                monthly_soil[month] = states[0]
                monthly_root_water[month] = states.sum(axis=0)
                ledger.append(dict(month=month + 1, precipitation_m3=float(monthly_precipitation[month, land].sum() * area / 1000.0), et_m3=float(et[land].sum() * area / 1000.0), sublimation_m3=sublimation * area / 1000.0, runoff_m3=float(monthly_runoff[month].sum())))
            atomic_npz(checkpoint_path, states=states, swe=swe, monthly_runoff=monthly_runoff, monthly_snow=monthly_snow, monthly_soil=monthly_soil, monthly_root_water=monthly_root_water, metadata_json=_i43_np.array(_i43_json.dumps(dict(source_sha256=source_sha256, spinup_years=spinup_years, completed_months=year * 12 + month + 1, final_start_storage=final_start_storage, ledger=ledger))))
            print(f'seasonal year {year + 1}/{spinup_years + 1} month {month + 1}/12', flush=True)
    native_origin = tuple(_i43_np.floor(origin / spacing).astype(int))
    mesh = _i43_build_mesh(shape, native_origin, spacing, seed)
    offset = origin - _i43_np.asarray(native_origin) * spacing
    boundary = _i43_np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    unknown_boundary = boundary & ~ocean
    routing = _i43_route_graph(elevation, ocean | unknown_boundary, mesh)
    labels, pool_count = _x165_pool_labels(elevation.ravel(), routing.filled.ravel(), mesh.indptr, mesh.indices)
    anchors = _i43_np.full(pool_count, -1, _i43_np.int64)
    groups = _i43_np.argsort(labels, kind='stable')
    starts = _i43_np.searchsorted(labels[groups], _i43_np.arange(pool_count))
    stops = _i43_np.searchsorted(labels[groups], _i43_np.arange(pool_count), side='right')
    stores, capacities = ([], _i43_np.empty(pool_count))
    for label in range(pool_count):
        ids = groups[starts[label]:stops[label]]
        anchor = ids[_i43_np.argmin(routing.rank[ids])]
        anchors[label] = anchor
        store = _x167_PoolStorage(ids, elevation.ravel(), routing.filled.ravel()[anchor], area)
        stores.append(store)
        capacities[label] = store.capacity_m3
    storage = _i43_np.zeros(pool_count)
    discharge = _i43_np.zeros(count)
    routing_ledger = []
    for month, days in enumerate(_x68_MONTH_DAYS):
        flow, retained = _x166_route_pool_interval(monthly_runoff[month], routing.order, routing.receiver, labels, anchors, capacities, storage)
        discharge += flow / _x69_YEAR_S
        ocean_out = float(flow[ocean.ravel()].sum())
        boundary_out = float(flow[unknown_boundary.ravel()].sum())
        incoming = float(monthly_runoff[month].sum())
        routing_ledger.append(dict(month=month + 1, input_runoff_m3=incoming, ocean_export_m3=ocean_out, cropped_land_export_m3=boundary_out, lake_storage_change_m3=float(retained), residual_m3=incoming - ocean_out - boundary_out - retained))
    lake_depth = _i43_np.zeros(count)
    pool_records = []
    for label, store in enumerate(stores):
        ids = groups[starts[label]:stops[label]]
        stage = store.stage_at_volume(storage[label])
        lake_depth[ids] = _i43_np.maximum(stage - elevation.ravel()[ids], 0.0)
        target = int(routing.receiver[anchors[label]])
        pool_records.append(dict(pool_id=label, cells=int(ids.size), capacity_m3=float(capacities[label]), stored_m3=float(storage[label]), stage_m=float(stage), spill_stage_m=float(store.maximum), spill_source_node=int(anchors[label]), spill_receiver_node=target, downstream_pool_id=int(labels[target]) if target >= 0 else -1))
    lake = lake_depth.reshape(shape) > 1e-06
    influence = _x161_boundary_influence_mask(shape, ocean)
    unknown = _i43_accumulate_graph(routing.receiver, routing.order, influence.astype(float)).ravel() > 0
    river = (discharge.reshape(shape) >= river_display_q_m3_s) & ~ocean & ~lake
    geometry = _i43_build_irregular_channel_geometry(elevation, discharge.reshape(shape), river, mesh, routing.receiver, bed_hardness=lithology['bed_hardness'].reshape(shape), bank_hardness=lithology['bank_hardness'].reshape(shape), lake_mask=lake, ocean_mask=ocean, config=_i43_DischargeGeometryConfig())
    annual_temperature = monthly_temperature.mean(axis=0)
    soil_depth = _i43_np.zeros(count)
    vegetation = _i43_np.zeros(count)
    cover_class = _i43_np.zeros(count, _i43_np.uint8)
    weathered_m3, dissolved_m3 = (0.0, 0.0)
    for start in range(0, count, 4096):
        stop = min(start + 4096, count)
        section = slice(start, stop)
        size = stop - start
        section_land = land[section]
        state = _x150_initial_state(bedrock_thickness_m=10.0 * section_land, area_m2=area, bed_hardness=lithology['bed_hardness'][section], solubility=lithology['solubility'][section])
        moisture = _i43_np.clip(monthly_soil[:, section].mean(axis=0) / 150.0, 0.0, 1.0)
        state, flux = _x151_advance(state, dt_s=float(_x69_YEAR_S), temperature_c=annual_temperature[section], moisture=moisture)
        pore = _i43_np.minimum(lithology['porosity'][section], 0.8)
        initial_solid = 0.45 * (1.0 - pore) * area * section_land
        cover = _x73_assess_land_cover(parent_solid_m3=initial_solid + state['parent_solid_m3'], porosity=pore, horizontal_area_m2=area, family_temperature_c=annual_temperature[section], water_state_mm=monthly_soil[:, section].mean(axis=0), water_capacity_reference_mm=_i43_np.full(size, 150.0))
        soil_depth[section] = cover['soil_thickness_bulk_m']
        vegetation[section] = cover['suitability']
        cover_class[section] = cover['land_cover_index']
        weathered_m3 += float(flux['weathered_solid_m3'].sum())
        dissolved_m3 += float(flux['dissolved_solid_m3'].sum())
    suitability = vegetation.copy()
    suitability[~land | lake.ravel()] = 0.0
    cover_class[~land | lake.ravel()] = 0
    vegetation, biomass_carbon, succession = _x163_advance_cover_carbon(elevation, ocean, lake, river, routing.receiver, native_origin, monthly_temperature, monthly_root_water, seed)
    soil_depth[~land] = 0.0
    sources = _i43_np.flatnonzero((routing.receiver >= 0) & land)
    mouth_ids = sources[ocean.ravel()[routing.receiver[sources]]]
    mouths = []
    node_x, node_z = (mesh.node_x_m + offset[0], mesh.node_z_m + offset[1])
    for cell in sorted(mouth_ids, key=lambda i: -discharge[i])[:20]:
        target = int(routing.receiver[cell])
        direction = _i43_np.array([node_x[cell] - node_x[target], node_z[cell] - node_z[target]])
        direction /= _i43_np.linalg.norm(direction)
        mouths.append(dict(source_node=int(cell), ocean_receiver_node=target, source_xz_m=[float(node_x[cell]), float(node_z[cell])], ocean_xz_m=[float(node_x[target]), float(node_z[target])], inward_unit_xz=direction.tolist(), q_m3_s=float(discharge[cell]), annual_volume_m3=float(discharge[cell] * _x69_YEAR_S), unknown_external_inflow=bool(unknown[cell])))
    final_storage = float((states[:, land].sum() + swe[land].sum()) * area / 1000.0)
    balance = sum((item['precipitation_m3'] - item['et_m3'] - item['sublimation_m3'] - item['runoff_m3'] for item in ledger)) - final_storage + final_start_storage
    seasonal_scale = max(sum((item['precipitation_m3'] for item in ledger)), 1.0)
    routing_scale = max(float(monthly_runoff.sum()), 1.0)
    checks = dict(seasonal_water_closes=abs(balance) <= seasonal_scale * 1e-10, routed_water_closes=all((abs(item['residual_m3']) <= routing_scale * 1e-10 for item in routing_ledger)), lake_prisms_match_storage=abs(float(lake_depth.sum() * area) - float(storage.sum())) <= max(float(storage.sum()), 1.0) * 1e-10, no_lakes_in_ocean=not bool(_i43_np.any(lake & ocean)), incision_bounded=bool(_i43_np.max(elevation - geometry['arrays']['bed_elevation_m']) <= 4.0 + 1e-09))
    if not all(checks.values()):
        raise RuntimeError(f'Acceptance aggregate checks failed: {checks}')
    report = dict(schema='world-acceptance-processes-v1', source_terrain=metadata, origin_xz_m=origin.tolist(), spacing_m=spacing, cell_area_m2=area, shape=list(shape), world_seed=seed, climate_parameter_identity=climate_identity, climate_terrain_support=climate_support, td_climate_coupling=dict(algorithm='conditioned-TD-means-existing-phase-orography-v1', authoritative_channel_definition=_x162_TD_CLIMATE_CHANNELS, upstream_source='WorldPipeline._compute_climate actual returned five-channel tensor', input_channel_metadata_disagrees=metadata.get('climate_base_channels') != _x162_TD_CLIMATE_CHANNELS, temperature_mean='TD temp + TD beta * (max(composed,0)-max(rawTD,0)); no independent-noise mean', temperature_variability='existing monthly anomalies centered and normalized to TD std/100; BIO mean/std use 12 unweighted months', precipitation_mean='clip(TD annualP * existing terrain precipitation_multiplier,100,3200) mm/year', precipitation_variability='existing monthly anomaly scaled to TD CV/100 when all months remain nonnegative; otherwise existing positive seasonal shape retained', precipitation_cv_fallback_cells=int(cv_fallback.sum()), precipitation_cv_fallback_fraction=float(cv_fallback.mean()), independent_noise_role='deterministic monthly phase only; annual climate means come from TD conditions'), algorithms=['sample_climate_v2', 'couple_td_climate', 'advance_snow_ice:depth-only adapter', 'temperature_index_pet_rate_mm_h', 'advance_soil', 'build_mesh', 'route_graph', 'LakeStorage', 'weathering_soil_inventory.advance', 'assess_land_cover', 'build_irregular_channel_geometry', 'initialize_succession', 'advance_succession'], time=dict(calendar='365 day', spinup_years=spinup_years, final_year=spinup_years + 1, assimilation_epoch='declared synthetic year 1 start at physical t=0 seconds; not a civil date', final_year_start_s=float(spinup_years * _x69_YEAR_S), final_year_end_s=float((spinup_years + 1) * _x69_YEAR_S), snow_interval_clock='each call uses relative 0..month-duration seconds under declared_interval temperatures; no calendar lookup; physical month follows chronological loop', soil_timestep_s=3600, snow_timestep='monthly distributed mean', lake_timestep='final-year monthly runoff volumes', equilibrium_claim=False, instantaneous_fields='snow_swe_mm, soil_water_mm, lake_depth_m, vegetation_fraction, biomass_carbon_kg_m2: final year end', annual_fields='temperature and cover_suitability: TD-conditioned 12-month unweighted BIO mean; Q: final-year volume / 31536000 seconds', monthly_fields='monthly snow/soil are month-end stores; rain/runoff are interval totals'), assumptions=dict(initial_soil_fast_slow_snow_mm=0.0, initial_lake_storage_m3=0.0, initial_soil_bulk_depth_m=0.45, weatherable_bedrock_m=10.0, pet_temperature_bin_c=0.25, climate_halo='genuine composed30m native source; checked filter-valid support; no clamping', lake_evaporation='not modelled; lakes receive terrestrial runoff only', lake_scope='final-year filling from dry; no external inflow supplied', vegetation_fraction='existing succession live carbon / declared carrying carbon; actual final-year-end cover', snow_adapter='only returned mm stores used; native30m metadata/volumes not used'), boundaries=dict(actual_ocean_cells=int(ocean.sum()), cropped_land_outlet_cells=int(unknown_boundary.sum()), unknown_influence_band_cells=int(influence.sum()), unknown_influence_band_width_cells=8, affected_downstream_cells=int(unknown.sum()), external_inflow_m3=None, external_inflow_status='unknown; eight-cell land-boundary influence propagated on receiver DAG; imposed exports are separate'), seasonal_water_ledger=ledger, routing_water_ledger=routing_ledger, seasonal_storage_start_m3=final_start_storage, seasonal_storage_end_m3=final_storage, seasonal_balance_residual_m3=float(balance), pools=pool_records, major_ocean_mouths=mouths, aggregate_checks=checks, units=dict(elevation_m='metres above declared datum', bed_m='metres above declared datum', node_x_m='world metres', node_z_m='world metres', discharge_m3_s='final-year volume / year seconds', soil_depth_m='bulk metres', vegetation_fraction='actual succession cover_fraction [0,1]', cover_suitability_fraction='computed environment_land_cover suitability [0,1]', biomass_carbon_kg_m2='live plant carbon kg C per m2', snow_swe_mm='mm water equivalent', soil_water_mm='mm water depth', annual_precipitation_mm='mm per declared 365-day year', annual_temperature_c='degree Celsius', monthly_runoff_volume_m3='m3 per cell per calendar month', receiver='row-major cell account ID; -1 explicit outlet'), river_display_q_m3_s=float(river_display_q_m3_s), geometry=geometry['metadata'], weathering=dict(weathered_solid_m3=weathered_m3, dissolved_solid_m3=dissolved_m3, domain='terrestrial land only; ocean weatherable bedrock and initial mantle are zero'), succession=succession, runtime_seconds=float(_i43_time.perf_counter() - started), limitations=['synthetic climate and declared uncalibrated coefficients', 'cropped land boundary exports and missing inflow remain explicit', 'generation incision is bounded geometry; no hydraulic erosion or calibrated ecology'])
    output = _i43_Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    arrays = dict(elevation_m=elevation, bed_m=geometry['arrays']['bed_elevation_m'], ocean_mask=ocean, lake_mask=lake, lake_depth_m=lake_depth.reshape(shape), river_mask=river, receiver=routing.receiver, discharge_m3_s=discharge.reshape(shape), node_x_m=node_x, node_z_m=node_z, annual_precipitation_mm=monthly_precipitation.sum(axis=0).reshape(shape), annual_temperature_c=annual_temperature.reshape(shape), vegetation_fraction=vegetation.reshape(shape), td_climate_precipitation_cv_fallback_mask=cv_fallback.reshape(shape), cover_suitability_fraction=suitability.reshape(shape), biomass_carbon_kg_m2=biomass_carbon, soil_depth_m=soil_depth.reshape(shape), snow_swe_mm=swe.reshape(shape), soil_water_mm=states[0].reshape(shape), land_cover_index=cover_class.reshape(shape), unknown_external_inflow_mask=unknown.reshape(shape), unknown_external_inflow_source_mask=influence, monthly_temperature_c=monthly_temperature.reshape((12, *shape)), monthly_precipitation_mm=monthly_precipitation.reshape((12, *shape)), monthly_runoff_volume_m3=monthly_runoff.reshape((12, *shape)), monthly_snow_swe_mm=monthly_snow.reshape((12, *shape)), monthly_soil_water_mm=monthly_soil.reshape((12, *shape)), pool_id=labels.reshape(shape), metadata_json=_i43_np.array(_i43_json.dumps(report, ensure_ascii=True)))
    _i43_np.savez_compressed(output / 'product.npz', **arrays)
    graph = geometry['graph']
    graph['node_x_m'] = node_x
    graph['node_z_m'] = node_z
    for name in ('reach_min_x_m', 'reach_max_x_m'):
        graph[name] += offset[0]
    for name in ('reach_min_z_m', 'reach_max_z_m'):
        graph[name] += offset[1]
    _i43_np.savez_compressed(output / 'river_graph.npz', **graph)
    (output / 'report.json').write_text(_i43_json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report
