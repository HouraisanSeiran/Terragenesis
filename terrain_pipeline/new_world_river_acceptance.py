"""Source-bound, finite event river acceptance; no terrain construction."""
import json
from pathlib import Path

import numpy as np

from terrain_pipeline import new_world_native_water as water
from terrain_pipeline import new_world_river_scene as scene
from terrain_pipeline.new_world_rivers import solve_finite_hydraulics
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork


def run(water_path, *, expected_terrain_identity, expected_planner_identity,
        expected_water_identity, origin_native_xz, shape_zx, width_m, max_depth_m,
        roughness, downstream_stage_m, mouth_id=None):
    """Run the complete selected scene chain, or return an unresolved diagnostic.

    Width, storage depth, roughness and downstream stage are declared scenario
    inputs; they are not measurements inferred from terrain or annual discharge.
    """
    if not expected_water_identity:
        raise ValueError('pinned water identity required')
    if len(shape_zx) != 2 or any(type(n) is not int or n < 2 or n * 30 > 50000 for n in shape_zx):
        raise ValueError('display dimensions must be between 2 cells and 50 km')
    if any(not np.isfinite(x) or x <= 0 for x in (width_m, max_depth_m, roughness)) or not np.isfinite(downstream_stage_m):
        raise ValueError('finite positive section and roughness and finite downstream stage required')
    common = dict(expected_terrain_identity=expected_terrain_identity,
                  expected_planner_identity=expected_planner_identity,
                  expected_water_identity=expected_water_identity)
    product = water.read_product(water_path, **common)
    wm, event = product
    x0, z0 = origin_native_xz
    height, width = shape_zx
    candidates = []
    for row in event['outlets']:
        if row.get('kind') != 'marine':
            continue
        sx, sz = row['source_native_xz']
        tx, tz = row['target_native_xz']
        if not (x0 <= sx < x0 + width and z0 <= sz < z0 + height and
                x0 <= tx < x0 + width and z0 <= tz < z0 + height):
            continue
        volume = row.get('known_local_volume_m3')
        known = isinstance(volume, (int, float)) and np.isfinite(volume) and volume >= 0
        candidates.append(dict(mouth_id=row['mouth_id'], known_volume_m3=float(volume) if known else None,
                               total_water_unknown=bool(row['total_water_unknown']), available=bool(known)))
    candidates.sort(key=lambda c: int(c['mouth_id']))
    if not candidates:
        raise ValueError('no actual marine mouths in the display window')
    if mouth_id is None:
        eligible = [c for c in candidates if c['available']]
        if not eligible:
            raise ValueError('no mouth with known event volume in the display window')
        selected = min(eligible, key=lambda c: (-c['known_volume_m3'], int(c['mouth_id'])))
        reason = 'largest known event volume; numeric mouth ID breaks ties'
    else:
        selected = next((c for c in candidates if c['mouth_id'] == mouth_id), None)
        if selected is None:
            raise ValueError('requested mouth not in display window')
        reason = 'explicit mouth ID'
    sm, a = scene.extract(water_path, **common, mouth_id=selected['mouth_id'], interval=wm['interval'],
                          origin_native_xz=origin_native_xz, shape_zx=shape_zx)
    failures = []
    if selected['total_water_unknown'] or np.any(a['total_water_unknown']):
        failures.append('total water unknown')
    if np.any(a['pool_index'] >= 0):
        failures.append('lake crossing has no supported head or exchange')
    if any(b['known_volume_m3'] is None for b in sm['boundary_contributions']):
        failures.append('boundary trace unavailable')
    local = a['incremental_volume_m3']
    if not np.isfinite(local).all() or np.any(local < -1e-9):
        failures.append('invalid incremental routed volume')
    if len(local) < 2:
        failures.append('selected path has fewer than two nodes')
    report = dict(status='unresolved', candidates=candidates, selected_mouth_id=selected['mouth_id'],
                  selection_reason=reason, full_chosen_path_parent_indices=a['parent_index'].tolist(),
                  full_chosen_path_xz_m=a['node_xz_m'].tolist(), verified_subset_parent_indices=[],
                  failures=failures, scene=sm, event_forcing={'source': wm['source'],
                  'duration_s': wm['duration_s'], 'runoff_depth_m': wm['runoff_depth_m']},
                  whole_river_connectivity_certified=False,
                  section_policy={'width_m': width_m, 'max_storage_depth_m': max_depth_m,
                                  'manning_n': roughness, 'downstream_stage_m': downstream_stage_m})
    report['source_identities'] = dict(terrain=expected_terrain_identity, planner=expected_planner_identity, water=expected_water_identity, scene=scene._identity(sm))
    if failures:
        return report, None
    result = solve_finite_hydraulics(bed_m=a['bed_m'], valid_mask=a['valid_mask'] & ~a['unknown_mask'] & ~a['ocean_mask'],
        path_xz_m=a['node_xz_m'], width_m=np.full(len(local), width_m), max_depth_m=np.full(len(local), max_depth_m),
        origin_xz_m=sm['origin_xz_m'], spacing_m=sm['spacing_m'], source_identity_sha256=expected_water_identity,
        section_source='declared fixed rectangular scenario', roughness=roughness,
        roughness_source='declared scenario Manning n', time_seconds=np.array([0., wm['duration_s']]),
        local_volume_m3=np.maximum(local, 0)[None, :], initial_volume_m3=np.zeros(len(local)),
        downstream={'kind': 'open', 'stage_m': downstream_stage_m})
    if result['metadata']['status'] != 'complete':
        failures.append(result['metadata']['reason'])
        return report, result
    try:
        replay_inputs(result)
    except ValueError as error:
        failures.append('hydraulic replay verification: ' + str(error))
        return report, result
    report['status'] = 'physical_solve_complete_sampled_sections_only'
    report['verified_subset_parent_indices'] = a['parent_index'].tolist()
    report['hydraulic'] = result['metadata']
    return report, result


def replay_inputs(result):
    """Reconstruct immutable fixed-section solver inputs from the solved trace."""
    if result is None or result['metadata']['status'] != 'complete':
        raise ValueError('complete hydraulic result required')
    a, m = result['arrays'], result['metadata']
    points, bed = a['station_xz_m'], a['bed_elevation_m']
    edges = np.linalg.norm(np.diff(points, axis=0), axis=1)
    n = len(points)
    receiver = np.r_[np.arange(1, n, dtype=np.int64), np.int64(-1)]
    slope = np.r_[-np.diff(bed) / edges, (bed[-2] - bed[-1]) / edges[-1]]
    kind = np.full(n, 'interior', dtype='U24'); kind[-1] = 'open_outflow'
    network = ChannelNetwork(receiver, a['storage_length_m'].copy(), a['width_m'].copy(), bed.copy(), slope,
        np.full(n, m['roughness']), a['max_depth_m'].copy(), kind, m['source_identity_sha256'],
        m['section_source'], m['roughness_source'], np.r_[edges, 0.])
    time = a['input_time_seconds'].copy()
    q = np.zeros((len(time)-1, n)); q[:, a['original_station_index']] = a['input_volume_m3'] / np.diff(time)[:, None]
    initial = np.zeros(n); initial[a['original_station_index']] = a['input_initial_volume_m3']
    forcing = ChannelForcing(time, q, m['source_identity_sha256'])
    config = ChannelConfig(**m['solver_config'])
    replay = solve_channel(network, forcing, initial, config)
    if replay['metadata']['status'] != 'complete' or any(not np.array_equal(v, a[k]) for k, v in replay['arrays'].items()):
        raise ValueError('hydraulic replay differs from saved trace')
    return network, forcing, initial, config


def save(report, result, output):
    """Save diagnostics and, when available, the physical inputs and trace."""
    output = Path(output)
    output.mkdir(exist_ok=False)
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf8')
    if result is not None:
        with (output / 'hydraulic.npz').open('xb') as f:
            np.savez_compressed(f, metadata_json=np.array(json.dumps(result['metadata'], allow_nan=False)), **result['arrays'])


SUPPLY_INPUT_SCHEMA = 'river-acceptance-supply-input-v1'


def build_supply_inputs(report, result, *, active_layer_bulk_thickness_m, rock_depth_m,
                        initial_mobile_solid_m3_per_node, material):
    """Build a finite, declared scenario from a verified selected-chain run.

    Rock depth is below the initial bed surface, including the active layer.
    Material is a MaterialParameters instance; stocks are not excavation.
    """
    from dataclasses import asdict
    from terrain_pipeline.common_infra import identity
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
    if report.get('status') != 'physical_solve_complete_sampled_sections_only' or report.get('failures'):
        raise ValueError('complete supported selected chain required')
    if not isinstance(material, MaterialParameters):
        raise ValueError('explicit material parameters required')
    vals = (active_layer_bulk_thickness_m, rock_depth_m, initial_mobile_solid_m3_per_node)
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not np.isfinite(v) or v < 0 for v in vals) or rock_depth_m < active_layer_bulk_thickness_m:
        raise ValueError('invalid finite stock policy')
    network, forcing, initial, config = replay_inputs(result)
    sources = report['source_identities']
    sm = report['scene']
    if (sources != dict(terrain=sm['terrain_identity'], planner=sm['planner_identity'], water=sm['water_identity'], scene=scene._identity(sm))
            or network.source_identity_sha256 != sources['water']):
        raise ValueError('source identities inconsistent')
    mouth = report['selected_mouth_id']
    selected = next(c for c in report['candidates'] if c['mouth_id'] == mouth)
    native = selected['known_volume_m3']
    input_volume = float((forcing.local_q_m3_s * np.diff(forcing.time_seconds)[:, None]).sum())
    if (selected['total_water_unknown'] or sm['mouth_total_water_unknown'] or sm['mouth_id'] != mouth
            or native is None or native != sm['known_mouth_volume_m3']
            or not np.isclose(input_volume, native, rtol=1e-10, atol=1e-8)):
        raise ValueError('native mouth allocation does not match input')
    ledger = result['metadata']['water_ledger']
    if not np.isclose(ledger['initial_m3'] + input_volume, ledger['final_storage_m3'] + ledger['outflow_m3'], rtol=1e-9, atol=1e-8):
        raise ValueError('water ledger does not close')
    arrays = {'trace__' + k: v.copy() for k, v in result['arrays'].items()}
    for name in ('receiver', 'length_m', 'width_m', 'bed_elevation_m', 'bed_slope', 'roughness', 'max_depth_m', 'terminal_kind', 'receiver_distance_m'):
        arrays['network__' + name] = getattr(network, name).copy()
    arrays.update(time_seconds=forcing.time_seconds.copy(), local_q_m3_s=forcing.local_q_m3_s.copy(), initial_water_m3=initial.copy(),
                  rock_floor_m=network.bed_elevation_m - rock_depth_m,
                  initial_alluvium_bulk_m3=network.length_m * network.width_m * active_layer_bulk_thickness_m,
                  initial_mobile_solid_m3=np.full(initial.shape, initial_mobile_solid_m3_per_node), is_lake=np.zeros(initial.shape, dtype=bool))
    metadata = dict(schema=SUPPLY_INPUT_SCHEMA, report=report, hydraulic_metadata=result['metadata'],
        policy=dict(name='declared finite homogeneous engineering scenario', active_layer_bulk_thickness_m=active_layer_bulk_thickness_m,
                    rock_depth_below_bed_m=rock_depth_m, initial_mobile_solid_m3_per_node=initial_mobile_solid_m3_per_node,
                    material=asdict(material), units={'length':'m', 'bulk_and_solid_volume':'m3', 'critical_shear':'Pa',
                    'erodibility':'m/(s Pa)', 'settling_velocity':'m/s', 'porosity':'dimensionless',
                    'transport_coefficient':'kernel scenario coefficient'},
                    provenance='declared engineering scenario; not calibrated tectonic lithology; construction excavation excluded'),
        water_ledger=dict(input_m3=input_volume, channel_initial_storage_m3=ledger['initial_m3'],
            channel_final_storage_m3=ledger['final_storage_m3'], physical_mouth_delivered_m3=ledger['outflow_m3'],
            native_instantaneous_mouth_allocation_reference_m3=native),
        scope='selected chain, fixed rectangular sections; dynamic width unsupported; no whole-network certification')
    return dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))


def _validate_supply_inputs(bundle):
    from terrain_pipeline.common_infra import identity
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
    a, m = bundle['arrays'], bundle['metadata']
    if m.get('schema') != SUPPLY_INPUT_SCHEMA or identity(a, m) != bundle['identity_sha256']:
        raise ValueError('invalid supply input identity or schema')
    result = dict(metadata=m['hydraulic_metadata'], arrays={k[7:]: v for k, v in a.items() if k.startswith('trace__')})
    p = m['policy']
    expected = build_supply_inputs(m['report'], result, active_layer_bulk_thickness_m=p['active_layer_bulk_thickness_m'],
        rock_depth_m=p['rock_depth_below_bed_m'], initial_mobile_solid_m3_per_node=p['initial_mobile_solid_m3_per_node'],
        material=MaterialParameters(**p['material']))
    if m != expected['metadata'] or set(a) != set(expected['arrays']) or any(not np.array_equal(a[k], expected['arrays'][k]) for k in a):
        raise ValueError('supply input differs from verified replay or declared policy')


def save_supply_inputs(path, bundle):
    """Publish once and return the external file SHA-256 to pin subsequent reads."""
    from terrain_pipeline.common_infra import save_bundle, file_sha256
    save_bundle(path, bundle, validator=_validate_supply_inputs)
    return file_sha256(path)


def read_supply_inputs(path, *, expected_sha256, expected_terrain_identity, expected_planner_identity, expected_water_identity, expected_scene_identity, expected_mouth_id):
    """Read a pinned bundle and return keyword arguments for produce_supply."""
    from terrain_pipeline.common_infra import load_bundle
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
    bundle = load_bundle(path, expected_sha256=expected_sha256, validator=_validate_supply_inputs)
    a, m = bundle['arrays'], bundle['metadata']
    expected = dict(terrain=expected_terrain_identity, planner=expected_planner_identity, water=expected_water_identity, scene=expected_scene_identity)
    if m['report']['source_identities'] != expected or m['report']['selected_mouth_id'] != expected_mouth_id:
        raise ValueError('expected source or mouth identity mismatch')
    result = dict(metadata=m['hydraulic_metadata'], arrays={k[7:]: v for k, v in a.items() if k.startswith('trace__')})
    network, forcing, initial, config = replay_inputs(result)
    provenance = m['policy']['provenance']
    return dict(network=network, water_forcing=forcing, terrain_identity=expected_terrain_identity,
        mouth_nodes={expected_mouth_id: len(network.receiver)-1}, rock_floor_m=a['rock_floor_m'],
        initial_alluvium_bulk_m3=a['initial_alluvium_bulk_m3'], initial_mobile_solid_m3=a['initial_mobile_solid_m3'],
        is_lake=a['is_lake'], material=MaterialParameters(**m['policy']['material']),
        bed_material_provenance=provenance, bank_material_provenance=provenance, initial_water_m3=initial, hydraulic_config=config)
