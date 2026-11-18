"""Consolidated environment_regional_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
from copy import deepcopy as _i48_deepcopy
from dataclasses import asdict as _i48_asdict
import hashlib as _i48_hashlib
import json as _i48_json
from pathlib import Path as _i48_Path
import numpy as _i48_np
from pathlib import Path as _i49_Path
import json as _i49_json
import math as _i49_math
import numpy as _i49_np
CATEGORY = 'D'
SCHEMA = 'environment-regional-hydraulics-v1'
MAX_STEPS = 64

def _digest(value):
    return _i48_hashlib.sha256(_i48_json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def _seal(region):
    from terrain_pipeline.common_infra import identity as _i48_identity
    region['identity_sha256'] = _i48_identity(region['arrays'], region['metadata'])
    return region

def validate_region(region):
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters as _i48_MaterialParameters
    from terrain_pipeline.common_infra import identity as _i48_identity
    a, m = (region['arrays'], region['metadata'])
    if m.get('schema') != SCHEMA or region['identity_sha256'] != _i48_identity(a, m):
        raise ValueError('regional schema/identity mismatch')
    if m['step'] > MAX_STEPS or not _i48_np.isfinite(m['time_s']) or m['time_s'] < 0.0:
        raise ValueError('regional time/step budget exceeded')
    count = len(m['source_nodes'])
    if not 1 <= count <= 16 or len(set(m['source_nodes'])) != count:
        raise ValueError('finite unique source reach required')
    for key, value in a.items():
        if value.shape != (count,) or value.dtype != _i48_np.float64 or (not _i48_np.isfinite(value).all()):
            raise ValueError('finite regional reach arrays required: ' + key)
    for key in ('water_m3', 'mobile_solid_m3', 'loose_solid_m3', 'rock_removed_m3'):
        if _i48_np.any(a[key] < 0.0):
            raise ValueError('negative regional inventory')
    if _i48_np.any(a['water_m3'] > m['width_m'] * _i48_np.asarray(m['length_m']) * m['max_depth_m']):
        raise ValueError('regional depth capacity exceeded')
    _i48_MaterialParameters(**m['material'])
    for packet in m['exports']:
        validate_packet(packet)
    for packet_id, receipt in m['receipts'].items():
        if packet_id != receipt['packet_id']:
            raise ValueError('receipt key mismatch')
        validate_packet(receipt)

def validate_packet(packet):
    body = {key: value for key, value in packet.items() if key != 'packet_id'}
    if _digest(body) != packet['packet_id']:
        raise ValueError('packet identity mismatch')
    for key in ('water_m3', 'solid_m3', 'time_start_s', 'time_end_s'):
        if not _i48_np.isfinite(packet[key]) or packet[key] < 0.0:
            raise ValueError('invalid physical port quantity')
    if packet['time_end_s'] <= packet['time_start_s']:
        raise ValueError('invalid port interval')

def select_pair(context):
    """Choose by immutable node order, before any hydraulic outcome is known."""
    rec = context['receiver'].ravel()
    bed = context['height_m'].ravel()
    active = (context['valid_mask'] & context['river_mask'] & ~context['protected_mask'] & ~context['ocean_mask']).ravel()
    for donor in _i48_np.flatnonzero(active & (rec >= 0)):
        target = int(rec[donor])
        end = int(rec[target])
        if active[target] and end >= 0 and (bed[donor] > bed[target] > bed[end]):
            return [int(donor), target]
    raise ValueError('no supported real downhill adjacent channel pair')

def select_reaches(context, nodes_per_region=2):
    """Select two consecutive original downhill reaches by immutable node order."""
    if type(nodes_per_region) is not int or not 1 <= nodes_per_region <= 16:
        raise ValueError('nodes_per_region must be 1..16')
    rec, bed = (context['receiver'].ravel(), context['height_m'].ravel())
    active = (context['valid_mask'] & context['river_mask'] & ~context['protected_mask'] & ~context['ocean_mask']).ravel()
    for start in _i48_np.flatnonzero(active):
        chain = [int(start)]
        while len(chain) < nodes_per_region * 2 + 1:
            target = int(rec[chain[-1]])
            if target < 0 or target in chain or (not active[target]) or (bed[chain[-1]] <= bed[target]):
                break
            chain.append(target)
        if len(chain) == nodes_per_region * 2 + 1:
            return [chain[:nodes_per_region], chain[nodes_per_region:nodes_per_region * 2]]
    raise ValueError('no supported real downhill two-reach chain')

def prepare_from_context(context, sources, source_node_ids, *, selected_nodes=None, initial_depth_m=0.2, initial_mobile_solid_m3=0.001, initial_alluvium_depth_m=0.002, width_m=3.0, material=None):
    """Prepare independent declared stocks on unchanged real source geometry.

    source_node_ids is a same-shape array of original global network node IDs.
    No process product stock is copied or withdrawn by this operation.
    """
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters as _i48_MaterialParameters
    if context['world_seed'] != 20261020 or context['spacing_m'] != 30.0:
        raise ValueError('fixed seed20261020/30m source required')
    ids = _i48_np.asarray(source_node_ids)
    if ids.shape != context['height_m'].shape or ids.dtype != _i48_np.int64 or _i48_np.unique(ids).size != ids.size:
        raise ValueError('unique original int64 source node IDs required')
    nodes = select_reaches(context) if selected_nodes is None else list(selected_nodes)
    groups = [[int(n)] for n in nodes] if all((isinstance(n, (int, _i48_np.integer)) for n in nodes)) else [list(g) for g in nodes]
    flat = [int(n) for group in groups for n in group]
    if len(groups) != 2 or any((not 1 <= len(g) <= 16 for g in groups)) or len(set(flat)) != len(flat):
        raise ValueError('two bounded disjoint real source reaches required')
    if any((int(context['receiver'].ravel()[a]) != b for a, b in zip(flat[:-1], flat[1:]))):
        raise ValueError('regional reaches must follow original receiver')
    material = _i48_MaterialParameters() if material is None else material
    quantities = (initial_depth_m, initial_mobile_solid_m3, initial_alluvium_depth_m, width_m)
    if not all((_i48_np.isfinite(v) and v >= 0.0 for v in quantities)) or width_m <= 0.0 or (not 0 <= initial_depth_m <= 5.0):
        raise ValueError('invalid declared initial channel inventories')
    regions = {}
    for local in flat:
        if not (context['valid_mask'].ravel()[local] and context['river_mask'].ravel()[local] and (not context['protected_mask'].ravel()[local]) and (not context['ocean_mask'].ravel()[local])):
            raise ValueError('regional owner must be supported unprotected land channel')
        receiver = int(context['receiver'].ravel()[local])
        if receiver < 0 or int(context['source_receiver_node'].ravel()[local]) != int(ids.ravel()[receiver]):
            raise ValueError('actual original receiver proof required for open port')
        bed = float(context['height_m'].ravel()[local])
        end_bed = float(context['height_m'].ravel()[receiver])
        x, z = (context['node_x_m'].ravel(), context['node_z_m'].ravel())
        distance = float(_i48_np.hypot(x[local] - x[receiver], z[local] - z[receiver]))
        if bed <= end_bed or distance <= 0.0:
            raise ValueError('unsupported non-downhill original source edge')
        name = 'node-' + str(int(ids.ravel()[local]))
        row, col = _i48_np.unravel_index(local, ids.shape)
        native = [int(context['origin_native_xz'][0]) + int(col), int(context['origin_native_xz'][1]) + int(row)]
        area = width_m * distance
        arrays = {'bed_m': _i48_np.array([bed]), 'water_m3': _i48_np.array([area * initial_depth_m]), 'stage_m': _i48_np.array([bed + initial_depth_m]), 'last_solved_outflow_q_m3_s': _i48_np.zeros(1), 'mobile_solid_m3': _i48_np.array([float(initial_mobile_solid_m3)]), 'loose_solid_m3': _i48_np.array([area * initial_alluvium_depth_m * (1.0 - material.porosity)]), 'rock_removed_m3': _i48_np.zeros(1)}
        meta = dict(schema=SCHEMA, algorithm='existing-manning-exner-regional-endpoint-handoff-v1', region_id=name, source_world_identity=sources['source_world_identity'], source_nodes=[int(ids.ravel()[local])], source_node=int(ids.ravel()[local]), target_node=int(ids.ravel()[receiver]), source_native_xz=native, target_native_xz=[int(context['origin_native_xz'][0]) + int(receiver % ids.shape[1]), int(context['origin_native_xz'][1]) + int(receiver // ids.shape[1])], source_xz_m=[float(x[local]), float(z[local])], original_bed_m=[bed], target_original_bed_m=end_bed, length_m=[distance], width_m=float(width_m), max_depth_m=5.0, roughness=0.035, rock_floor_m=[bed - 0.3 - initial_alluvium_depth_m], material=_i48_asdict(material), source_provenance=_i48_deepcopy(sources), world_seed=20261020, spacing_m=30.0, time_s=0.0, step=0, exports=[], receipts={}, initial_stocks={key: value.tolist() for key, value in arrays.items()}, initial_stock_provenance='independent declared engineering scenario; source process stocks neither copied nor debited', local_forcing='zero; old representative Q and old stocks never reinjected', hydraulic_observation='stage_m reflects current owned water and updated bed; last_solved_outflow_q_m3_s is the actual previous Manning endpoint before port credit, zero until first solve', handoff='synchronous interval-end credit; next interval hydraulic consumption', limitations=['finite reach owners; original receivers frozen; no capture', 'open boundary gradient from actual next receiver; no permanent watershed proof', 'rectangular channel/material areas and roughness are explicit engineering declarations', 'frozen-water sediment replay; updated nodal bed used by next hydraulic solve'], last_solver={})
        regions[name] = _seal(dict(arrays=arrays, metadata=meta))
    merged = {}
    for group in groups:
        members = [regions['node-' + str(int(ids.ravel()[local]))] for local in group]
        region = _i48_deepcopy(members[-1])
        region['arrays'] = {key: _i48_np.concatenate([r['arrays'][key] for r in members]) for key in region['arrays']}
        meta = region['metadata']
        meta['source_nodes'] = [r['metadata']['source_node'] for r in members]
        meta['region_id'] = 'reach-' + str(meta['source_nodes'][0]) + '-' + str(meta['source_nodes'][-1])
        for key in ('length_m', 'rock_floor_m', 'original_bed_m'):
            meta[key] = [r['metadata'][key][0] for r in members]
        meta['node_native_xz'] = [r['metadata']['source_native_xz'] for r in members]
        meta['initial_stocks'] = {key: value.tolist() for key, value in region['arrays'].items()}
        merged[meta['region_id']] = _seal(region)
    return merged

def prepare_process_handoff(product, source_node_ids, *, time_start_s, selected_nodes=None, material=None):
    """Consume a completed environment export into initially dry regional owners.

    The source product already debited these quantities and remains an immutable
    evidence record. Never call this again as fresh local Q: the packet IDs pin
    its exact source product identity and persisted receipts reject redelivery.
    """
    from terrain_pipeline.environment_product import product_identity as product_identity
    transfers = product['last_transfers']
    water = transfers['external_hydraulic_water_m3']
    solid = transfers['external_hydraulic_solid_m3']
    if not 0 <= time_start_s < product['time_s']:
        raise ValueError('actual completed source interval required')
    history = product['forcing_history'][-1]
    if time_start_s != history['start_time_s'] or time_start_s + history['dt_s'] != product['time_s']:
        raise ValueError('handoff time must match the saved source forcing interval')
    nodes = select_reaches(product['context']) if selected_nodes is None else selected_nodes
    flat = [int(n) for g in nodes for n in g] if isinstance(nodes[0], (list, tuple)) else list(nodes)
    support = _i48_np.zeros_like(water, bool)
    support.ravel()[flat] = True
    if _i48_np.any(water[~support] != 0.0) or _i48_np.any(solid[~support] != 0.0):
        raise ValueError('all source exports must have a prepared authoritative owner')
    regions = prepare_from_context(product['context'], product['sources'], source_node_ids, selected_nodes=nodes, initial_depth_m=0.0, initial_mobile_solid_m3=0.0, initial_alluvium_depth_m=0.0, material=material)
    source_id = product_identity(product)
    for region in regions.values():
        m = region['metadata']
        m['time_s'] = float(product['time_s'])
        m['source_process_identity'] = source_id
        m['initial_stock_provenance'] = 'dry/zero solid initial stock; actual debited completed environment external export received once'
        _seal(region)
    for local in flat:
        global_node = int(source_node_ids.ravel()[local])
        name = next((key for key, r in regions.items() if global_node in r['metadata']['source_nodes']))
        m = regions[name]['metadata']
        node_index = m['source_nodes'].index(global_node)
        native = m['node_native_xz'][node_index]
        packet = dict(source_world_identity=m['source_world_identity'], source_region='environment-process', source_node=global_node, target_node=global_node, source_native_xz=native, target_native_xz=native, time_start_s=float(time_start_s), time_end_s=float(product['time_s']), water_m3=float(water.ravel()[local]), solid_m3=float(solid.ravel()[local]), source_state_identity=source_id, ownership='source external export already debited; regional channel now sole water/solid owner')
        packet['packet_id'] = _digest(packet)
        regions[name] = deliver(regions[name], packet)
    return regions

def deliver(region, packet):
    """Credit an already-debited port once; an exact saved replay is a no-op."""
    validate_region(region)
    validate_packet(packet)
    m = region['metadata']
    if packet['source_world_identity'] != m['source_world_identity'] or packet['target_node'] not in m['source_nodes']:
        raise ValueError('port world/target ownership mismatch')
    if packet['packet_id'] in m['receipts']:
        if m['receipts'][packet['packet_id']] != packet:
            raise ValueError('receipt payload mismatch')
        return _i48_deepcopy(region)
    if packet['time_end_s'] != m['time_s']:
        raise ValueError('port must be delivered at shared physical interval endpoint')
    result = _i48_deepcopy(region)
    index = m['source_nodes'].index(packet['target_node'])
    result['arrays']['water_m3'] = result['arrays']['water_m3'].copy()
    result['arrays']['mobile_solid_m3'] = result['arrays']['mobile_solid_m3'].copy()
    result['arrays']['water_m3'][index] += packet['water_m3']
    result['arrays']['mobile_solid_m3'][index] += packet['solid_m3']
    area = _i48_np.asarray(m['length_m']) * m['width_m']
    result['arrays']['stage_m'] = result['arrays']['bed_m'] + result['arrays']['water_m3'] / area
    result['metadata']['receipts'][packet['packet_id']] = _i48_deepcopy(packet)
    _seal(result)
    validate_region(result)
    return result

def _solve(region, dt_s, target_bed):
    from terrain_pipeline.channel_geometry import ChannelConfig as _i48_ChannelConfig
    from terrain_pipeline.channel_geometry import ChannelForcing as _i48_ChannelForcing
    from terrain_pipeline.channel_geometry import ChannelNetwork as _i48_ChannelNetwork
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters as _i48_MaterialParameters
    from terrain_pipeline.surface_rivers.metric_sediment import SedimentConfig as _i48_SedimentConfig
    from terrain_pipeline.surface_rivers.metric_sediment import SedimentDomain as _i48_SedimentDomain
    from terrain_pipeline.surface_rivers.metric_sediment import SedimentForcing as _i48_SedimentForcing
    from terrain_pipeline.common_infra import identity as _i48_identity
    from terrain_pipeline.surface_hydraulics import solve_channel as _i48_solve_channel
    from terrain_pipeline.surface_rivers.metric_sediment import solve_sediment as _i48_solve_sediment
    a, m = (region['arrays'], region['metadata'])
    start, end = (m['time_s'], m['time_s'] + dt_s)
    bed = a['bed_m']
    if bed[-1] <= target_bed or _i48_np.any(_i48_np.diff(bed) >= 0.0):
        raise ValueError('updated regional bed reverses original receiver; capture paused')
    gid = region['identity_sha256']
    n = len(bed)
    ones = _i48_np.ones(n)
    lengths = _i48_np.asarray(m['length_m'])
    slope = (bed - _i48_np.r_[bed[1:], target_bed]) / lengths
    receiver = _i48_np.r_[_i48_np.arange(1, n), -1].astype(_i48_np.int64)
    kind = _i48_np.array(['interior'] * (n - 1) + ['open_outflow'])
    network = _i48_ChannelNetwork(receiver, lengths.copy(), ones * m['width_m'], a['bed_m'].copy(), slope, ones * m['roughness'], ones * m['max_depth_m'], kind, gid, 'actual saved nodal bed/receiver distance', 'declared Manning .035', _i48_np.r_[lengths[:-1], 0.0])
    forcing = _i48_ChannelForcing(_i48_np.array([start, end]), _i48_np.zeros((1, n)), gid)
    water = _i48_solve_channel(network, forcing, a['water_m3'].copy(), _i48_ChannelConfig(max_dt_seconds=0.25))
    if water['metadata']['status'] != 'complete':
        raise ValueError('regional water solver failed: ' + str(water['metadata']['failure_reason']))
    wa = water['arrays']
    hydraulic_id = _i48_identity(wa, water['metadata'])
    material = _i48_MaterialParameters(**m['material'])
    area = lengths * m['width_m']
    domain = _i48_SedimentDomain(receiver.copy(), area, ones * m['width_m'], a['bed_m'].copy(), _i48_np.asarray(m['rock_floor_m']), a['loose_solid_m3'] / (1.0 - material.porosity), _i48_np.zeros(n, bool), receiver < 0, gid, 'owned rectangular channel material area')
    drive = _i48_SedimentForcing(wa['time_seconds'].copy(), wa['volume_m3'][:-1].copy(), wa['depth_m'][:-1].copy(), wa['outflow_q_m3_s'].copy(), _i48_np.broadcast_to(slope, wa['outflow_q_m3_s'].shape).copy(), _i48_np.zeros_like(wa['outflow_q_m3_s']), hydraulic_id, gid, 'actual existing Manning trace')
    sediment = _i48_solve_sediment(domain, drive, material, a['mobile_solid_m3'].copy(), _i48_SedimentConfig(max_dt_seconds=0.1, max_bed_change_m=0.01))
    if sediment['metadata']['status'] != 'complete':
        raise ValueError('regional sediment solver failed: ' + str(sediment['metadata']['failure_reason']))
    sa = sediment['arrays']
    result = _i48_deepcopy(region)
    result['arrays'] = dict(bed_m=sa['trace_bed_elevation_m'][-1].copy(), stage_m=sa['trace_bed_elevation_m'][-1] + wa['depth_m'][-1], last_solved_outflow_q_m3_s=wa['outflow_end_q_m3_s'][-1].copy(), water_m3=wa['volume_m3'][-1].copy(), mobile_solid_m3=sa['trace_mobile_solid_m3'][-1].copy(), loose_solid_m3=sa['trace_bed_alluvium_solid_m3'][-1].copy(), rock_removed_m3=a['rock_removed_m3'] + sa['trace_rock_removed_m3'][-1])
    packet = dict(source_world_identity=m['source_world_identity'], source_region=m['region_id'], source_node=m['source_node'], target_node=m['target_node'], source_native_xz=m['source_native_xz'], target_native_xz=m['target_native_xz'], time_start_s=start, time_end_s=end, water_m3=float(wa['boundary_outflow_volume_m3'].sum()), solid_m3=float(sa['step_exported_solid_m3'].sum()), source_state_identity=gid, hydraulic_identity=hydraulic_id, sediment_identity=sediment['identity_sha256'])
    packet['packet_id'] = _digest(packet)
    result['metadata'].update(time_s=end, step=m['step'] + 1, last_solver=dict(water_algorithm=water['metadata']['algorithm'], sediment_algorithm=sediment['metadata']['algorithm'], water_residual_m3=float(_i48_np.max(_i48_np.abs(wa['balance_residual_m3']))), solid_residual_m3=float(_i48_np.max(_i48_np.abs(sa['step_balance_residual_m3']))), eroded_loose_solid_m3=float(sa['step_eroded_loose_solid_m3'].sum()), eroded_rock_m3=float(sa['step_eroded_rock_m3'].sum()), internal_water_transferred_m3=float((wa['outflow_q_m3_s'][:, :-1] * _i48_np.diff(wa['time_seconds'])[:, None]).sum()), internal_solid_transferred_m3=float(sa['step_outgoing_solid_m3'][:, :-1].sum()), water_internal_steps=len(wa['time_seconds']) - 1, sediment_internal_steps=len(sa['trace_time_seconds']) - 1))
    result['metadata']['exports'].append(packet)
    return (_seal(result), packet)

def advance(regions, dt_s, *, request_order=None):
    """Stage all owners before delivery; publish nothing on any solver failure."""
    if len(regions) != 2 or not _i48_np.isfinite(dt_s) or (not 0 < dt_s <= 60.0):
        raise ValueError('two bounded regions and 0<dt_s<=60 required')
    order = sorted(regions) if request_order is None else list(request_order)
    if len(order) != len(regions) or set(order) != set(regions):
        raise ValueError('request order must cover owners exactly once')
    for region in regions.values():
        validate_region(region)
    stamps = {(r['metadata']['source_world_identity'], r['metadata']['time_s'], r['metadata']['step']) for r in regions.values()}
    if len(stamps) != 1 or next(iter(stamps))[2] >= MAX_STEPS:
        raise ValueError('regional source/time synchronization or step budget mismatch')
    owners = {node: key for key, r in regions.items() for node in r['metadata']['source_nodes']}
    if len(owners) != sum((len(r['metadata']['source_nodes']) for r in regions.values())):
        raise ValueError('duplicate global node owner')
    staged, packets = ({}, [])
    for key in order:
        region = regions[key]
        m = region['metadata']
        target = owners.get(m['target_node'])
        target_bed = float(regions[target]['arrays']['bed_m'][regions[target]['metadata']['source_nodes'].index(m['target_node'])]) if target else m['target_original_bed_m']
        staged[key], packet = _solve(region, dt_s, target_bed)
        packets.append(packet)
    for packet in sorted(packets, key=lambda p: p['source_node']):
        target = owners.get(packet['target_node'])
        if target is not None:
            staged[target] = deliver(staged[target], packet)
    for region in staged.values():
        validate_region(region)
    return {key: staged[key] for key in sorted(staged)}

def save_checkpoint(path, regions):
    """Content-address region files first; manifest is the only commit point."""
    from terrain_pipeline.common_infra import file_sha256 as _i48_file_sha256
    from terrain_pipeline.common_infra import identity as _i48_identity
    from terrain_pipeline.common_infra import load_bundle as _i48_load_bundle
    from terrain_pipeline.common_infra import save_bundle as _i48_save_bundle
    path = _i48_Path(path)
    stamps = set()
    entries = {}
    for key, region in sorted(regions.items()):
        validate_region(region)
        stamps.add((region['metadata']['source_world_identity'], region['metadata']['time_s'], region['metadata']['step']))
        entries[key] = region['identity_sha256'] + '.npz'
    if len(stamps) != 1 or len(regions) != 2:
        raise ValueError('shared two-region checkpoint required')
    if path.exists():
        raise FileExistsError(path)
    files = {}
    for key, region in sorted(regions.items()):
        target = path.parent / entries[key]
        if target.exists():
            existing = _i48_load_bundle(target, expected_sha256=_i48_file_sha256(target), validator=validate_region)
            if existing['identity_sha256'] != region['identity_sha256']:
                raise ValueError('existing regional object differs')
        else:
            _i48_save_bundle(target, region, validator=validate_region)
        files[key] = dict(file=entries[key], sha256=_i48_file_sha256(target), identity=region['identity_sha256'])
    world, time_s, step = next(iter(stamps))
    meta = dict(schema=SCHEMA + '-checkpoint', source_world_identity=world, time_s=time_s, step=step, regions=files)
    record = dict(arrays={}, metadata=meta, identity_sha256=_i48_identity({}, meta))
    _i48_save_bundle(path, record, validator=_validate_checkpoint)
    return _i48_file_sha256(path)

def _validate_checkpoint(record):
    from terrain_pipeline.common_infra import identity as _i48_identity
    if record['metadata'].get('schema') != SCHEMA + '-checkpoint' or record['identity_sha256'] != _i48_identity(record['arrays'], record['metadata']):
        raise ValueError('checkpoint identity mismatch')

def load_checkpoint(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _i48_load_bundle
    path = _i48_Path(path)
    record = _i48_load_bundle(path, expected_sha256=expected_sha256, validator=_validate_checkpoint)
    m = record['metadata']
    result = {}
    for key, entry in m['regions'].items():
        if _i48_Path(entry['file']).name != entry['file']:
            raise ValueError('regional object must be adjacent to checkpoint')
        region = _i48_load_bundle(path.parent / entry['file'], expected_sha256=entry['sha256'], validator=validate_region)
        rm = region['metadata']
        if rm['region_id'] != key or region['identity_sha256'] != entry['identity'] or (rm['source_world_identity'], rm['time_s'], rm['step']) != (m['source_world_identity'], m['time_s'], m['step']):
            raise ValueError('regional object/checkpoint mismatch')
        result[key] = region
    if len(result) != 2:
        raise ValueError('two-region checkpoint required')
    return result

def query(regions):
    """Read only the already-completed saved state and port evidence."""
    return {key: dict(time_s=r['metadata']['time_s'], source_node=r['metadata']['source_node'], source_nodes=r['metadata']['source_nodes'], state={k: v.tolist() for k, v in r['arrays'].items()}, exports=_i48_deepcopy(r['metadata']['exports']), receipt_count=len(r['metadata']['receipts']), last_solver=_i48_deepcopy(r['metadata']['last_solver'])) for key, r in sorted(regions.items())}
DRIVER_SCHEMA = 'environment-climate-driver-v1'
STATE_SCHEMA = 'environment-climate-state-v1'
MAX_CELLS = 4096
MAX_SUBSTEPS = 100000
SPACING_M = 30.0
DRIVER_FIELDS = {'x_m', 'z_m', 'elevation_m', 'ridge_height_m', 'upwind_ridge_height_m', 'orographic_gradient', 'wind_bearing_x', 'wind_bearing_z', 'monthly_temperature_c'}

def _bundle(arrays, metadata):
    from terrain_pipeline.common_infra import identity as _i49_identity
    from terrain_pipeline.common_infra import readonly as _i49_readonly
    return {'arrays': {name: _i49_readonly(value) for name, value in arrays.items()}, 'metadata': metadata, 'identity_sha256': _i49_identity(arrays, metadata)}

def _shape(shape):
    if not isinstance(shape, (list, tuple)) or len(shape) != 2 or any((type(side) is not int or side < 1 for side in shape)) or (_i49_math.prod(shape) > MAX_CELLS):
        raise ValueError('climate domain must contain 1..4096 cells in a 2D grid')
    return tuple(shape)

def _mass(value, shape, name):
    value = _i49_np.broadcast_to(_i49_np.asarray(value, _i49_np.float64), shape).copy()
    if not _i49_np.isfinite(value).all() or _i49_np.any(value < 0.0):
        raise ValueError('finite nonnegative %s required' % name)
    return value

def _time(value):
    from terrain_pipeline.climate_forcing import MAX_TIME_S as _x78_MAX_TIME_S
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (not 0 <= value <= _x78_MAX_TIME_S):
        raise ValueError('bounded nonnegative physical time_s required')
    return float(value)

def _saved_terrain_support(store, bounds):
    """Read only saved TD tiles intersecting the exact original ridge support."""
    from terrain_pipeline.common_infra import checked_archive as _i49_checked_archive
    from terrain_pipeline.common_infra import file_sha256 as _i49_file_sha256
    from terrain_pipeline.common_infra import identity as _i49_identity
    store = _i49_Path(store)
    registry_path = store / 'registry.json'
    registry = _i49_json.loads(registry_path.read_text(encoding='utf-8'))
    if registry['world']['layout']['world_seed'] != 20261020:
        raise ValueError('fixed world seed20261020 required')
    left, top, right, bottom = bounds
    component = next((item for item in registry['components'] if item['bounds'][0] <= left and item['bounds'][1] <= top and (item['bounds'][2] >= right) and (item['bounds'][3] >= bottom)), None)
    if component is None:
        raise ValueError('actual saved terrain does not cover the original 15km ridge support')
    root = store / 'versions' / component['version']
    manifest_path = root / 'manifest.json'
    manifest = _i49_json.loads(manifest_path.read_text(encoding='utf-8'))
    expected = manifest.pop('identity_sha256')
    if expected != component['identity_sha256'] or _i49_identity({}, manifest) != expected or manifest['world_identity'] != registry['world_identity']:
        raise ValueError('saved terrain manifest identity mismatch')
    height = _i49_np.empty((bottom - top, right - left), _i49_np.float64)
    covered = _i49_np.zeros(height.shape, bool)
    records = []
    for tile in manifest['composition_tiles']:
        tx, tz = tile['origin_native_xz']
        rows, cols = tile['shape_zx']
        x0, z0, x1, z1 = (max(left, tx), max(top, tz), min(right, tx + cols), min(bottom, tz + rows))
        if x0 >= x1 or z0 >= z1:
            continue
        path = root / tile['file']
        data = _i49_checked_archive(path, expected_sha256=tile['sha256'])
        src = _i49_np.s_[z0 - tz:z1 - tz, x0 - tx:x1 - tx]
        dst = _i49_np.s_[z0 - top:z1 - top, x0 - left:x1 - left]
        if not data['valid_mask'][src].all():
            raise ValueError('unresolved saved TD ridge support')
        height[dst] = data['composed_elevation_m'][src]
        covered[dst] = True
        records.append({'path': str(path.resolve()), 'sha256': tile['sha256']})
    if not covered.all() or not _i49_np.isfinite(height).all():
        raise ValueError('actual saved TD ridge support has missing or nonfinite cells')
    source = {'registry_path': str(registry_path.resolve()), 'registry_sha256': _i49_file_sha256(registry_path), 'manifest_sha256': _i49_file_sha256(manifest_path), 'world_identity': registry['world_identity'], 'component_identity_sha256': expected, 'tiles': records, 'source_pages': registry['pages'], 'height_field': 'saved composed_elevation_m; generated TD-derived bed, equals network node_raw_bed_m', 'support_bounds_native_xz_exclusive': list(bounds)}

    def sample(x_m, z_m):
        x, z = _i49_np.broadcast_arrays(_i49_np.asarray(x_m, _i49_np.float64), _i49_np.asarray(z_m, _i49_np.float64))
        ix, iz = (x / SPACING_M, z / SPACING_M)
        if not _i49_np.isfinite(x).all() or not _i49_np.isfinite(z).all() or _i49_np.any(ix != _i49_np.rint(ix)) or _i49_np.any(iz != _i49_np.rint(iz)) or _i49_np.any(ix < left) or _i49_np.any(ix >= right) or _i49_np.any(iz < top) or _i49_np.any(iz >= bottom):
            raise ValueError('ridge query outside actual prepared TD support or off native grid')
        return height[iz.astype(_i49_np.int64) - top, ix.astype(_i49_np.int64) - left]
    return (sample, source)

def build_climate_driver(store, origin_native_xz=(43700, 42100), shape_zx=(64, 64)):
    """Pin real terrain once, using the unmodified 15 km / three-tap G3/G4 rules."""
    from terrain_pipeline.common_infra import file_sha256 as _i49_file_sha256
    from terrain_pipeline.climate_forcing import calendar as _x81_calendar
    from terrain_pipeline.climate_forcing import sample_seasonal_air as _x82_sample_seasonal_air
    from terrain_pipeline.climate_forcing import RefinedClimateParameters as _x83_RefinedClimateParameters
    from terrain_pipeline.climate_forcing import latitude_norm as _x84_latitude_norm
    from terrain_pipeline.climate_forcing import ridge_height as _x85_ridge_height
    from terrain_pipeline.climate_forcing import wind_unit as _x86_wind_unit
    shape = _shape(shape_zx)
    if len(origin_native_xz) != 2 or any((type(value) is not int for value in origin_native_xz)):
        raise ValueError('integer native origin pair required')
    cols, rows = _i49_np.meshgrid(_i49_np.arange(shape[1]), _i49_np.arange(shape[0]))
    x = (origin_native_xz[0] + cols) * SPACING_M
    z = (origin_native_xz[1] + rows) * SPACING_M
    parameters = _x83_RefinedClimateParameters()
    bearings = {_x86_wind_unit(float(value)) for value in _i49_np.asarray(_x84_latitude_norm(20261020, z)).ravel()}
    if len(bearings) != 1:
        raise ValueError('fixed climate domain crosses the original constant-wind band')
    wind = bearings.pop()
    taps = parameters.ridge_offsets_m
    scale = parameters.orographic_scale_m
    bounds = (int((x.min() + min(taps) + min(0.0, -wind[0] * scale)) / SPACING_M), int((z.min() + min(taps) + min(0.0, -wind[1] * scale)) / SPACING_M), int((x.max() + max(taps) + max(0.0, -wind[0] * scale)) / SPACING_M) + 1, int((z.max() + max(taps) + max(0.0, -wind[1] * scale)) / SPACING_M) + 1)
    sampler, source = _saved_terrain_support(store, bounds)
    elevation = sampler(x, z)
    air = _x82_sample_seasonal_air(20261020, x, z, elevation_m=elevation, elevation_sampler=sampler)
    here = _x85_ridge_height(20261020, x, z, parameters=parameters, elevation_sampler=sampler)
    upwind = _x85_ridge_height(20261020, x - wind[0] * scale, z - wind[1] * scale, parameters=parameters, elevation_sampler=sampler)
    arrays = {'x_m': x, 'z_m': z, 'elevation_m': elevation, 'ridge_height_m': here, 'upwind_ridge_height_m': upwind, 'orographic_gradient': (here - upwind) / scale, 'monthly_temperature_c': air['monthly_temperature_c'], 'wind_bearing_x': air['wind_bearing_x'], 'wind_bearing_z': air['wind_bearing_z']}
    metadata = {'schema': DRIVER_SCHEMA, 'world_seed': 20261020, 'origin_native_xz': list(origin_native_xz), 'shape_zx': list(shape), 'spacing_m': SPACING_M, 'source': source, 'calendar': _x81_calendar(), 'air_identity_sha256': air['identity']['identity_sha256'], 'air_code_identities': air['code_identities'], 'wind_bearing': list(wind), 'orographic_scale_m': scale, 'ridge_offsets_m': list(taps), 'parameter_identity_sha256': parameters.identity_sha256, 'random_streams': {'world_seed': 20261020, 'method': 'original geographic_noise.field(seed,salt); octave salt increment811', 'thermal_salt': 1401, 'moisture_salt': 1503, 'continentality_salt': 1607, 'seasonal_phase_salt': 1709, 'new_driver_random_process': False}, 'code_sha256': {name: _i49_file_sha256(_i49_Path(__file__).with_name(name)) for name in ('environment_regional_hydraulics.py', 'climate_forcing.py')}, 'wind_semantics': 'original G3 synthetic band axial direction; speed is separate declared m/s', 'boundary_semantics': 'fixed full-domain upstream external kg/s per face; open downstream export', 'recycle_semantics': 'caller owns previous-macrostep ET; supplied kg recycled once over next interval', 'precipitation_semantics': 'G4 finite vapour condensation, not the v2 climatological rain multiplier', 'time_semantics': 'physical seconds, G3 fixed365 monthly calendar; no Minecraft tick or wall clock'}
    result = _bundle(arrays, metadata)
    validate_climate_driver(result)
    return result

def validate_climate_driver(driver):
    from terrain_pipeline.common_infra import identity as _i49_identity
    from terrain_pipeline.climate_forcing import calendar as _x81_calendar
    arrays, metadata = (driver['arrays'], driver['metadata'])
    shape = _shape(metadata['shape_zx'])
    if metadata['schema'] != DRIVER_SCHEMA or metadata['world_seed'] != 20261020 or metadata['spacing_m'] != SPACING_M or (metadata['calendar'] != _x81_calendar()) or (metadata['orographic_scale_m'] != 15000.0) or (metadata['ridge_offsets_m'] != [-7500.0, 0.0, 7500.0]) or (set(arrays) != DRIVER_FIELDS):
        raise ValueError('climate driver schema or original climate parameters mismatch')
    for name, array in arrays.items():
        expected = (12,) + shape if name == 'monthly_temperature_c' else shape
        if array.shape != expected or array.dtype.kind not in 'fiu' or (not _i49_np.isfinite(array).all()):
            raise ValueError('invalid prepared climate field: ' + name)
    rows, cols = _i49_np.indices(shape)
    origin = metadata['origin_native_xz']
    if not _i49_np.array_equal(arrays['x_m'], (origin[0] + cols) * SPACING_M) or not _i49_np.array_equal(arrays['z_m'], (origin[1] + rows) * SPACING_M) or (not _i49_np.all(arrays['wind_bearing_x'] == metadata['wind_bearing'][0])) or (not _i49_np.all(arrays['wind_bearing_z'] == metadata['wind_bearing'][1])) or (tuple(metadata['wind_bearing']) not in ((-1, 0), (1, 0))) or (not _i49_np.array_equal(arrays['orographic_gradient'], (arrays['ridge_height_m'] - arrays['upwind_ridge_height_m']) / 15000.0)):
        raise ValueError('prepared climate geometry or original axial wind mismatch')
    if driver['identity_sha256'] != _i49_identity(arrays, metadata):
        raise ValueError('climate driver identity mismatch')
    return True

def initial_climate_state(driver, *, time_s=0.0, vapour_kg=0.0):
    validate_climate_driver(driver)
    return _bundle({'vapour_kg': _mass(vapour_kg, tuple(driver['metadata']['shape_zx']), 'vapour kg')}, {'schema': STATE_SCHEMA, 'driver_identity_sha256': driver['identity_sha256'], 'shape_zx': driver['metadata']['shape_zx'], 'time_s': _time(time_s)})

def validate_climate_state(state, driver=None):
    from terrain_pipeline.common_infra import identity as _i49_identity
    arrays, metadata = (state['arrays'], state['metadata'])
    shape = _shape(metadata['shape_zx'])
    if metadata['schema'] != STATE_SCHEMA or set(arrays) != {'vapour_kg'}:
        raise ValueError('climate state schema mismatch')
    _time(metadata['time_s'])
    if arrays['vapour_kg'].shape != shape or arrays['vapour_kg'].dtype != _i49_np.dtype('float64'):
        raise ValueError('climate state shape mismatch')
    _mass(arrays['vapour_kg'], shape, 'vapour kg')
    if state['identity_sha256'] != _i49_identity(arrays, metadata):
        raise ValueError('climate state identity mismatch')
    if driver is not None and (metadata['driver_identity_sha256'] != driver['identity_sha256'] or list(shape) != driver['metadata']['shape_zx']):
        raise ValueError('climate state belongs to another fixed driver')
    return True

def advance_climate_driver(driver, state, end_time_s, *, external_inflow_kg_per_s, wind_speed_m_s, uplift_gain, et_recycle_kg=None):
    """Advance persistent vapour with CFL substeps and explicit per-upstream-face kg/s.

    ET belongs to the caller's previous macrostep, supplied once as kg per cell.
    It is distributed uniformly over this interval; this driver has no pending ET.
    """
    from terrain_pipeline.climate_forcing import depth_mm as _x76_depth_mm
    from terrain_pipeline.climate_forcing import climate_transport_step as _x77_climate_transport_step
    from terrain_pipeline.climate_forcing import _interval_mean_monthly as _x79_interval_mean_monthly
    from terrain_pipeline.climate_forcing import _validate_time_edges as _x80_validate_time_edges
    validate_climate_driver(driver)
    validate_climate_state(state, driver)
    start, end = (state['metadata']['time_s'], _time(end_time_s))
    shape = tuple(driver['metadata']['shape_zx'])
    _x80_validate_time_edges([start, end], _i49_math.prod(shape))
    for name, value in (('wind_speed_m_s', wind_speed_m_s), ('uplift_gain', uplift_gain)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i49_math.isfinite(value)) or (value < 0):
            raise ValueError('finite nonnegative ' + name + ' required')
    duration = end - start
    substeps = max(1, _i49_math.ceil(wind_speed_m_s * duration / SPACING_M))
    if substeps > MAX_SUBSTEPS:
        raise ValueError('climate CFL substep budget exceeded')
    dt = duration / substeps
    wind = tuple(driver['metadata']['wind_bearing'])
    faces = shape[0] if wind[0] else shape[1]
    rate = _mass(external_inflow_kg_per_s, (faces,), 'upstream external kg/s per face')
    recycle = _mass(0.0 if et_recycle_kg is None else et_recycle_kg, shape, 'previous-step ET kg')
    vapour = state['arrays']['vapour_kg']
    precipitation = _i49_np.zeros(shape, _i49_np.float64)
    ledger = dict.fromkeys(('inflow_kg', 'recycle_kg', 'precipitation_kg', 'outflow_kg', 'nondepositing_kg'), 0.0)
    for _index in range(substeps):
        step = _x77_climate_transport_step(vapour, wind_bearing=wind, wind_speed_m_s=wind_speed_m_s, dt_s=dt, uplift_gain=uplift_gain, gradient=driver['arrays']['orographic_gradient'], inflow_kg=rate * dt, recycle_kg=recycle / substeps)
        if not step['ledger']['closure_ok'] or not step['boundary']['certified']:
            raise ValueError('uncertified climate substep')
        vapour = step['vapour_kg']
        precipitation += step['precipitation_kg']
        for name in ledger:
            ledger[name] += step['ledger'][name]
    ledger['storage_change_kg'] = float(vapour.sum() - state['arrays']['vapour_kg'].sum())
    ledger['closure_residual_kg'] = ledger['inflow_kg'] + ledger['recycle_kg'] - ledger['precipitation_kg'] - ledger['outflow_kg'] - ledger['nondepositing_kg'] - ledger['storage_change_kg']
    ledger['closure_tolerance_kg'] = 1e-09 * max(ledger['inflow_kg'] + ledger['recycle_kg'], ledger['precipitation_kg'], ledger['outflow_kg'], 1.0)
    ledger['closure_ok'] = abs(ledger['closure_residual_kg']) <= ledger['closure_tolerance_kg']
    if not ledger['closure_ok']:
        raise ValueError('aggregate climate moisture ledger does not close')
    ledger['substeps'] = substeps
    ledger['max_cfl'] = wind_speed_m_s * dt / SPACING_M
    temperature = _x79_interval_mean_monthly(driver['arrays']['monthly_temperature_c'].reshape(12, -1), start, end).reshape(shape)
    new_state = _bundle({'vapour_kg': vapour}, dict(state['metadata'], time_s=end))
    forcing = {'precipitation_mm': _x76_depth_mm(precipitation), 'rainfall_m_s': _x76_depth_mm(precipitation) / 1000.0 / duration, 'air_temperature_c': temperature, 'ledger': ledger, 'seasonal_source': {'driver_identity_sha256': driver['identity_sha256'], 'state_before_identity_sha256': state['identity_sha256'], 'state_after_identity_sha256': new_state['identity_sha256'], 'time_edges_s': [start, end], 'wind_bearing': list(wind), 'wind_speed_m_s': wind_speed_m_s, 'uplift_gain': uplift_gain, 'external_inflow_kg_per_s_per_face': rate.tolist(), 'recycle_semantics': driver['metadata']['recycle_semantics']}}
    return (new_state, forcing)

def crop_climate_result(forcing, *, row, col, shape_zx):
    """Query an already calculated fixed-domain result; preserve its full-domain ledger."""
    from terrain_pipeline.common_infra import readonly as _i49_readonly
    shape = _shape(shape_zx)
    full = forcing['precipitation_mm'].shape
    if type(row) is not int or type(col) is not int or min(row, col) < 0 or (row + shape[0] > full[0]) or (col + shape[1] > full[1]):
        raise ValueError('climate crop outside calculated fixed domain')
    result = dict(forcing)
    for name in ('precipitation_mm', 'rainfall_m_s', 'air_temperature_c'):
        result[name] = _i49_readonly(forcing[name][row:row + shape[0], col:col + shape[1]])
    result['query'] = {'row': row, 'col': col, 'shape_zx': list(shape), 'ledger_scope': 'unchanged full fixed calculation domain'}
    return result

def save_climate_driver(path, driver):
    from terrain_pipeline.common_infra import save_bundle as _i49_save_bundle
    _i49_save_bundle(path, driver, validator=validate_climate_driver)

def _driver_headers(headers):
    if set(headers) != DRIVER_FIELDS | {'manifest'}:
        raise ValueError('climate driver archive fields mismatch')
    shape = _shape(list(headers['elevation_m'][0]))
    for name in DRIVER_FIELDS:
        expected = (12,) + shape if name == 'monthly_temperature_c' else shape
        if headers[name][0] != expected or headers[name][1].kind not in 'fiu':
            raise ValueError('climate driver allocation shape/dtype mismatch')

def load_climate_driver(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _i49_load_bundle
    return _i49_load_bundle(path, expected_sha256=expected_sha256, validator=validate_climate_driver, header_validator=_driver_headers)

def save_climate_state(path, state):
    from terrain_pipeline.common_infra import save_bundle as _i49_save_bundle
    _i49_save_bundle(path, state, validator=validate_climate_state)

def load_climate_state(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _i49_load_bundle

    def headers(record):
        if set(record) != {'vapour_kg', 'manifest'}:
            raise ValueError('climate state archive fields mismatch')
        _shape(list(record['vapour_kg'][0]))
        if record['vapour_kg'][1] != _i49_np.dtype('float64'):
            raise ValueError('climate state allocation dtype mismatch')
    return _i49_load_bundle(path, expected_sha256=expected_sha256, validator=validate_climate_state, header_validator=headers)
