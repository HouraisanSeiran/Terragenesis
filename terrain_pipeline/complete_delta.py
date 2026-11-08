"""Independent engineered delta, finite monthly forcing and replayable state.

Coordinates are metres at raster cell centres. Construction bulk volumes and
natural sediment solid volumes have separate ledgers. Resume replays history
from the constructed bed; previously emitted outlet packets are never emitted
again. No upstream receiver or terrain generator is executed here.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from scipy.ndimage import label, binary_propagation

from terrain_pipeline.surface_rivers.metric_coast_bounded_delta import (
    construct_coast_bounded_scene, path_station, sample_path,
)
from terrain_pipeline.surface_rivers.metric_tidal_creek_construction import enrich_tidal_coast
from terrain_pipeline.surface_rivers.metric_integrated_delta import (
    IntegratedDeltaConfig, build_channel_tree, integrated_solid_ledger, run_integrated_delta,
)
from tools.run_integrated_delta import (
    load_scene, protect_scene_geometry, incoming_water, connected_water_diagnostics,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENE = ROOT / '.scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/scene.npz'
DEFAULT_FORCING = ROOT / 'verification/fluvial-delta/adaptive-tree-16km-20261018-02/result.npz'
WORLD_SEED = 20261020
SCHEMA = 'complete-engineered-delta-v1'
MONTHLY_SUBSTEPS = 4


def purpose_seed(purpose: str) -> int:
    return int.from_bytes(hashlib.sha256(f'{WORLD_SEED}:{purpose}'.encode('ascii')).digest()[:4], 'little')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def high_sediment_challenge_forcing():
    """One fixed non-leap engineering year, no claim of climate generation."""
    seconds = np.asarray([31,28,31,30,31,30,31,31,30,31,30,31], float)*86400.
    q = np.asarray([55,50,60,85,120,155,180,165,125,90,70,60], float)
    concentration = np.asarray([.10,.10,.12,.18,.25,.40,.60,.48,.30,.20,.14,.10])
    return validate_forcing(dict(month_seconds=seconds.tolist(), monthly_water_m3=(q*seconds).tolist(),
        monthly_solid_m3=(q*seconds*concentration/2650.).tolist(),
        description='Finite prescribed engineering monthly season; peak Q 180 m3/s; suspended solid concentration 0.10-0.60 kg/m3; density 2650 kg/m3. Not climate generated.',
        solid_density_kg_m3=2650., peak_solid_flux_upper_bound_m3_s=.8,
        record_ids=[f'engineering-year1-month{i+1:02d}' for i in range(12)]))


def historical_finite_forcing(path):
    """Replay existing finite monthly packets without rerouting their source."""
    path = Path(path).resolve()
    with np.load(path,allow_pickle=False) as data:
        forcing = {key:data[key].tolist() for key in ('month_seconds','monthly_water_m3','monthly_solid_m3')}
    forcing.update(record_ids=[f'historical-finite-year1-month{i+1:02d}' for i in range(len(forcing['month_seconds']))],
        description='Read-only replay of saved finite engineering boundary packets; upstream terrain, receiver and erosion are not rerun.',
        source_forcing_path=str(path),source_forcing_sha256=sha256(path))
    return validate_forcing(forcing)


def default_forcing():
    return historical_finite_forcing(DEFAULT_FORCING)


def validate_forcing(forcing):
    arrays = [np.asarray(forcing[k], float) for k in ('month_seconds','monthly_water_m3','monthly_solid_m3')]
    dt, water, solid = arrays
    if dt.ndim != 1 or not len(dt) or any(a.shape != dt.shape or not np.isfinite(a).all() for a in arrays):
        raise ValueError('forcing requires equal nonempty finite one-dimensional arrays')
    if np.any(dt <= 0) or np.any(water < 0) or np.any(solid < 0):
        raise ValueError('forcing requires positive durations and nonnegative volumes')
    result = dict(forcing)
    ids = result.get('record_ids')
    if not isinstance(ids, list) or len(ids) != len(dt) or any(not isinstance(v,str) or not v for v in ids) or len(set(ids)) != len(ids):
        raise ValueError('forcing requires one unique nonempty record_id per month')
    for key, value in zip(('month_seconds','monthly_water_m3','monthly_solid_m3'), arrays):
        result[key] = value.tolist()
    result['total_water_m3'] = float(water.sum())
    result['total_solid_m3'] = float(solid.sum())
    result['total_seconds'] = float(dt.sum())
    return result


def construct_scene(source_path, forcing, *, construction_mode='natural', world_seed=WORLD_SEED):
    source_path = Path(source_path).resolve()
    source_hash = sha256(source_path)
    with np.load(source_path, allow_pickle=False) as data:
        metadata = json.loads(data['metadata_json'].item())
        arrays = {key: data[key].copy() for key in data.files if key != 'metadata_json'}
    old_seed = metadata.get('seed')
    seed = int.from_bytes(hashlib.sha256(f'{int(world_seed)}:complete-delta/coastal-construction/v1'.encode('ascii')).digest()[:4], 'little')
    metadata['seed'] = seed
    arrays['incoming_q_m3_s'] = np.asarray(forcing['monthly_water_m3'])/np.asarray(forcing['month_seconds'])
    scene = construct_coast_bounded_scene(arrays, metadata, finite_solid_supply_m3=forcing['total_solid_m3'],
        construction_mode=construction_mode, world_seed=world_seed)
    if construction_mode == 'natural':
        coast_audit = scene['audit']
        coast_algorithm = scene['metadata']['algorithm']
        scene = enrich_tidal_coast(scene['arrays'], scene['metadata'], world_seed=world_seed)
        tidal_audit = scene['audit']
        delta = scene['arrays']['bed_m']-scene['arrays']['base_bed_m']
        area = float(scene['metadata']['spacing_m'])**2
        scene['audit'] = dict(coast_audit,
            cut_bulk_m3=float(np.maximum(-delta, 0.).sum()*area),
            fill_bulk_m3=float(np.maximum(delta, 0.).sum()*area),
            net_bulk_m3=float(delta.sum()*area),
            coast_construction=coast_audit, tidal_detail=tidal_audit)
        scene['metadata'].update(algorithm='complete-coast-and-tidal-island-construction-v2',
            construction_algorithms=dict(coast=coast_algorithm,
                tidal_detail=scene['metadata']['tidal_coast_construction']['algorithm']),
            geometry_limitations='Prescribed river tree, interdistributary relief and marine-rooted tidal creek excavation on inherited terrain; no avulsion, emergent tidal morphology, topology evolution or calibrated Wax Lake reconstruction')
    scene['metadata'].update(world_seed=int(world_seed), purpose_seeds={'coastal_construction': seed},
        seed_derivation='SHA256 ASCII world_seed:purpose, first four bytes little-endian uint32',
        seed_purpose='complete-delta/coastal-construction/v1',
        source_scene_path=str(source_path), source_scene_sha256=source_hash,
        inherited_source_seed=old_seed,
        source_terrain_identity='Inherited base_bed_m from source scene; original terrain is not regenerated by current world seed',
        coordinate_convention='origin_xz_m is centre of [row=0,col=0]; rows increase +z, columns +x; metres')
    if sha256(source_path) != source_hash:
        raise ValueError('source scene changed during construction')
    return scene


def geometry_for(scene):
    geometry = build_channel_tree(scene['bed_m'], scene['origin_xz_m'], scene['spacing_m'],
        scene['mouth_xz_m'], scene['fan_apex_xz_m'], scene['trunk_path_xz_m'],
        scene['branch_paths_xz_m'], scene['widths_m'],
        ocean_mask=scene.get('open_marine_mask', scene['connected_ocean_mask']),
        branch_parent_index=scene.get('terminal_parent_index'))
    protect_scene_geometry(geometry, scene)
    return geometry


def wet_diagnostics(scene, wet, *, include_incoming=True):
    result = connected_water_diagnostics(scene, wet)
    labels, _ = label(wet)
    origin, spacing = scene['origin_xz_m'], scene['spacing_m']
    def cells(path):
        station = path_station(path)
        dense = sample_path(path, station, np.linspace(0., station[-1], max(2, int(np.ceil(station[-1]/(spacing/4.)))+1)))
        ij = np.floor((dense-origin)/spacing+.5).astype(int)
        inside = (ij[:,0]>=0)&(ij[:,0]<wet.shape[1])&(ij[:,1]>=0)&(ij[:,1]<wet.shape[0])
        return ij[inside]
    apex = result['apex_component']
    checks = []
    for name, path in ([('incoming',scene['designed_incoming_path_xz_m'])] if include_incoming else []) + [('trunk',scene['trunk_path_xz_m']),
                        *[(f'branch{i}', p) for i,p in enumerate(scene['branch_paths_xz_m'])]]:
        ij = cells(path)
        values = labels[ij[:,1],ij[:,0]]
        checks.append(dict(name=name, samples=len(ij), dry_samples=int(np.count_nonzero(values==0)),
            all_samples_in_source_component=bool(apex and np.all(values==apex))))
    marine = scene.get('open_marine_mask', scene['connected_ocean_mask']) & wet
    seeds = np.zeros_like(wet)
    seeds[[0,-1],:] = marine[[0,-1],:]
    seeds[:,[0,-1]] = marine[:,[0,-1]]
    open_water = binary_propagation(seeds, mask=marine)
    ends = [cells(p)[-1] for p in scene['branch_paths_xz_m']]
    result.update(centerline_checks=checks, all_centerlines_wet=all(c['all_samples_in_source_component'] for c in checks),
        terminal_open_boundary_connected=[bool(open_water[c[1],c[0]]) for c in ends])
    return result


def simulate(scene, forcing, config=None):
    forcing = validate_forcing(forcing)
    config = config or IntegratedDeltaConfig()
    geometry = geometry_for(scene)
    substeps = MONTHLY_SUBSTEPS
    expanded = {key:np.repeat(np.asarray(forcing[key])/substeps,substeps)
        for key in ('monthly_water_m3','monthly_solid_m3','month_seconds')}
    result = run_integrated_delta(scene['bed_m'], geometry, expanded['monthly_water_m3'],
        expanded['monthly_solid_m3'], expanded['month_seconds'], config)
    subrecords = result['records']
    # The retained incoming bed is excluded from morphodynamics, including
    # stage raster projection. Join its unchanged cells with each step's own
    # solved source head and flow, just as for the final saved water surface.
    raw_snapshots=result['wet_timeseries'].copy()
    joined_snapshots=[]
    for record,head,wet in zip(subrecords,result['monthly_node_heads_m'],raw_snapshots):
        incoming_result=dict(stage_m=scene['bed_m'].copy(),final_bed_m=scene['bed_m'],
            depth_m=np.zeros_like(scene['bed_m']),records=[record],final_heads_m=head)
        _,_,incoming_wet=incoming_water(scene,incoming_result)
        joined_snapshots.append(wet | (incoming_wet & geometry.protected_mask & scene['main_section_mask']))
    result['raw_delta_only_substep_wet_snapshots']=raw_snapshots
    result['wet_timeseries']=np.asarray(joined_snapshots)
    monthly_records=[]
    terminal_q=np.asarray([r.terminal_q_m3_s for r in subrecords])
    result['substep_terminal_q_m3_s']=terminal_q
    result['substep_terminal_export_solid_m3']=result['monthly_terminal_export_solid_m3'].copy()
    result['substep_wet_hydraulic_snapshots']=result['wet_timeseries'].copy()
    result['monthly_last_substep_used_q_m3_s']=terminal_q[substeps-1::substeps]
    for month in range(len(forcing['month_seconds'])):
        group=subrecords[month*substeps:(month+1)*substeps]
        mean_q=np.mean(terminal_q[month*substeps:(month+1)*substeps],axis=0)
        padded=np.r_[mean_q[:3],np.zeros(max(0,3-len(mean_q)))]
        monthly_records.append(replace(group[-1],water_input_m3=forcing['monthly_water_m3'][month],
            solid_input_m3=forcing['monthly_solid_m3'][month],
            q_branch0_m3_s=padded[0],q_branch1_m3_s=padded[1],q_branch2_m3_s=padded[2],
            deposition_solid_m3=sum(r.deposition_solid_m3 for r in group),
            reentrainment_solid_m3=sum(r.reentrainment_solid_m3 for r in group),
            export_solid_m3=sum(r.export_solid_m3 for r in group),
            mass_error_m3=sum(r.mass_error_m3 for r in group),terminal_q_m3_s=tuple(mean_q),
            terminal_export_m3=tuple(np.sum([r.terminal_export_m3 for r in group],axis=0))))
    result['records']=monthly_records
    result['monthly_terminal_export_solid_m3']=result['monthly_terminal_export_solid_m3'].reshape(len(monthly_records),substeps,-1).sum(axis=1)
    result['wet_timeseries']=result['wet_timeseries'][::substeps]
    result['monthly_land_stored_solid_m3']=result['monthly_land_stored_solid_m3'][substeps-1::substeps]
    result['monthly_node_heads_m']=result['monthly_node_heads_m'][substeps-1::substeps]
    result['monthly_max_junction_q_residual_m3_s']=result['monthly_max_junction_q_residual_m3_s'].reshape(-1,substeps).max(axis=1)
    marine = scene.get('open_marine_mask', scene['connected_ocean_mask'])
    if not np.array_equal(result['final_bed_m'][marine], scene['bed_m'][marine]):
        raise ValueError('annual morphodynamics changed frozen marine bed')
    surface, depth, wet = incoming_water(scene, result)
    result.update(water_surface_m=surface, water_depth_m=depth, wet_mask=wet)
    return result




def save_run(output, scene_path, forcing, *, emitted_before=0, config=None, construction_ledger=None):
    output = Path(output)
    scene = load_scene(Path(scene_path))
    try:
        result = simulate(scene, forcing, config)
    except ValueError as error:
        if hasattr(error, 'hydraulic_diagnostics'):
            output.mkdir(parents=True, exist_ok=True)
            (output/'failed-hydraulics.json').write_text(json.dumps(error.hydraulic_diagnostics,
                default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v,indent=2),encoding='utf-8')
        raise
    monthly_connectivity = [wet_diagnostics(scene,wet,include_incoming=False) for wet in result['wet_timeseries']]
    substep_connectivity = [wet_diagnostics(scene,wet,include_incoming=False) for wet in result['substep_wet_hydraulic_snapshots']]
    substep_flowing=np.repeat(np.asarray(forcing['monthly_water_m3'])>0.,MONTHLY_SUBSTEPS)
    if np.any(result['substep_terminal_q_m3_s'][substep_flowing]<=0.):
        raise ValueError('positive source substep contains a dry terminal')
    connectivity = wet_diagnostics(scene, result['wet_mask'])
    if not (connectivity['all_centerlines_wet'] and all(connectivity['terminal_open_boundary_connected'])
            and connectivity['incoming_connected_to_apex'] and connectivity['apex_and_terminals_connected']):
        raise ValueError('complete delta wet connectivity failed: '+json.dumps(connectivity))
    if not all(c['all_centerlines_wet'] and all(c['terminal_open_boundary_connected']) for c in monthly_connectivity):
        raise ValueError('month-start hydraulic snapshot has a dry channel: '+json.dumps([
            dict(month_index=i,checks=c['centerline_checks'],outlets=c['terminal_open_boundary_connected'])
            for i,c in enumerate(monthly_connectivity) if not c['all_centerlines_wet']]))
    if not all(c['all_centerlines_wet'] and all(c['terminal_open_boundary_connected']) for c in substep_connectivity):
        raise ValueError('substep hydraulic snapshot has a dry channel')
    source_path = scene['metadata'].get('source_scene_path')
    if source_path and sha256(source_path) != scene['metadata']['source_scene_sha256']:
        raise ValueError('inherited source changed during simulation')
    forcing_source=forcing.get('source_forcing_path')
    if forcing_source and sha256(forcing_source) != forcing['source_forcing_sha256']:
        raise ValueError('archived forcing source changed during simulation')
    if construction_ledger is None:
        delta = scene['bed_m']-scene['base_bed_m']
        area = scene['spacing_m']**2
        construction_ledger=dict(cut_bulk_m3=float(np.maximum(-delta,0.).sum()*area),
            fill_bulk_m3=float(np.maximum(delta,0.).sum()*area),net_bulk_m3=float(delta.sum()*area))
    output.mkdir(parents=True, exist_ok=True)
    records = result['records']
    arrays = {k:v for k,v in result.items() if isinstance(v, np.ndarray)}
    arrays.update(origin_xz_m=scene['origin_xz_m'], spacing_m=np.asarray(scene['spacing_m']),
        month_seconds=np.asarray(forcing['month_seconds']), monthly_water_m3=np.asarray(forcing['monthly_water_m3']),
        monthly_solid_m3=np.asarray(forcing['monthly_solid_m3']),
        monthly_terminal_q_m3_s=np.asarray([r.terminal_q_m3_s for r in records]),
        monthly_escrow_solid_m3=np.asarray([r.escrow_solid_m3 for r in records]))
    flowing = np.asarray(forcing['monthly_water_m3'])>0.
    if np.any(arrays['monthly_terminal_q_m3_s'][flowing]<=0.):
        raise ValueError('positive source month contains a dry terminal')
    np.savez_compressed(output/'result.npz', **arrays)
    ledger = integrated_solid_ledger(result, np.asarray(forcing['monthly_solid_m3']))
    packets = []
    times = np.r_[0.,np.cumsum(forcing['month_seconds'])]
    for month in range(emitted_before,len(records)):
        for terminal, (q,solid) in enumerate(zip(arrays['monthly_terminal_q_m3_s'][month], arrays['monthly_terminal_export_solid_m3'][month])):
            packets.append(dict(packet_id=f'{sha256(scene_path)}:{forcing["record_ids"][month]}:terminal-{terminal}', month_index=month,
                terminal_index=terminal, outlet_xz_m=scene['branch_paths_xz_m'][terminal,-1].tolist(),
                start_seconds=float(times[month]), end_seconds=float(times[month+1]),
                water_m3=float(q*forcing['month_seconds'][month]), solid_m3=float(solid)))
    (output/'outlet-packets.json').write_text(json.dumps(packets,indent=2),encoding='utf-8')
    summary = dict(schema=SCHEMA, source=scene['metadata'], forcing=forcing,
        construction_ledger=construction_ledger, solid_ledger=ledger,
        solid_ledger_residual_m3=ledger['input_solid_m3']-ledger['retained_solid_m3']-ledger['exported_solid_m3']-ledger['escrow_solid_m3'],
        final_wet_connectivity=connectivity, terminal_count=len(scene['branch_paths_xz_m']),
        month_start_hydraulic_snapshots=[dict(month_index=i,**c) for i,c in enumerate(monthly_connectivity)],
        substep_hydraulic_checks=dict(snapshot_count=len(substep_connectivity),all_centerlines_wet=True,
            all_outlets_open_boundary_connected=True,
            upstream_incoming_checked='each substep joins frozen protected incoming bed using its own solved source head and Q; final actual water separately'),
        minimum_terminal_q_m3_s=float(arrays['monthly_terminal_q_m3_s'][flowing].min()) if np.any(flowing) else 0.,
        minimum_substep_terminal_q_m3_s=float(result['substep_terminal_q_m3_s'][substep_flowing].min()) if np.any(substep_flowing) else 0.,
        code_sha256={name:sha256(ROOT/name) for name in ('terrain_pipeline/complete_delta.py',
            'terrain_pipeline/surface_rivers/metric_coast_bounded_delta.py',
            'terrain_pipeline/surface_rivers/metric_tidal_creek_construction.py',
            'terrain_pipeline/surface_rivers/metric_tidal_island_geometry.py',
            'terrain_pipeline/channel_geometry.py','terrain_pipeline/surface_rivers/metric_integrated_delta.py')},
        secondary_count=int(np.count_nonzero(scene.get('terminal_level',[]))),
        emitted_packet_count=len(packets), replayed_month_count=emitted_before,
        continuation_policy='Full history replay from constructed bed; previously emitted packet IDs excluded',
        time_integration=dict(substeps_per_month=MONTHLY_SUBSTEPS,
            substep_seconds=(np.asarray(forcing['month_seconds'])/MONTHLY_SUBSTEPS).tolist(),
            terminal_q_semantics='monthly_terminal_q_m3_s is time-weighted throughput; monthly_last_substep_used_q_m3_s is last substep hydraulic Q before its bed update'),
        water_ledger=dict(input_water_m3=forcing['total_water_m3'],
            outlet_water_m3=float(np.sum(arrays['monthly_terminal_q_m3_s']*np.asarray(forcing['month_seconds'])[:,None])),
            residual_m3=float(forcing['total_water_m3']-np.sum(arrays['monthly_terminal_q_m3_s']*np.asarray(forcing['month_seconds'])[:,None])),
            policy='Quasi-steady monthly throughput; no transient water storage term'),
        config=asdict(result['config']), max_junction_q_residual_m3_s=float(result['monthly_max_junction_q_residual_m3_s'].max()),
        frozen_marine_bed_exact=bool(np.array_equal(result['final_bed_m'][scene.get('open_marine_mask', scene['connected_ocean_mask'])],
            scene['bed_m'][scene.get('open_marine_mask', scene['connected_ocean_mask'])])),
        retained_upstream_exact=bool(np.array_equal(result['final_bed_m'][scene['retained_upstream_raster_mask']], scene['bed_m'][scene['retained_upstream_raster_mask']])))
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    state=dict(schema=SCHEMA, scene_path=str(Path(scene_path).resolve()), scene_sha256=sha256(scene_path),
        forcing=forcing, emitted_month_count=len(records), config=summary['config'],construction_ledger=construction_ledger,
        substeps_per_month=MONTHLY_SUBSTEPS)
    (output/'state.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    manifest = {name:sha256(output/name) for name in ('scene.npz','result.npz','state.json','forcing.json','outlet-packets.json')}
    summary['file_sha256'] = manifest
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


def load_run(output):
    """Cold read a completed product, rejecting altered arrays or state."""
    output = Path(output)
    summary = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    if summary['schema'] != SCHEMA:
        raise ValueError('unsupported complete delta schema')
    required = {'scene.npz','result.npz','state.json','forcing.json','outlet-packets.json'}
    if set(summary['file_sha256']) != required:
        raise ValueError('incomplete saved product manifest')
    for name, expected in summary['file_sha256'].items():
        if sha256(output/name) != expected:
            raise ValueError('saved product identity mismatch: '+name)
    with np.load(output/'result.npz',allow_pickle=False) as data:
        arrays = {key:data[key].copy() for key in data.files}
    return dict(summary=summary, arrays=arrays)


def run(output, source_scene=DEFAULT_SCENE, forcing=None):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'output already populated: {output}')
    forcing = validate_forcing(forcing or default_forcing())
    constructed = construct_scene(source_scene, forcing)
    output.mkdir(parents=True,exist_ok=True)
    scene_path = output/'scene.npz'
    np.savez_compressed(scene_path, **constructed['arrays'], metadata_json=np.asarray(json.dumps(constructed['metadata'])))
    (output/'forcing.json').write_text(json.dumps(forcing,indent=2),encoding='utf-8')
    return save_run(output,scene_path,forcing,construction_ledger=constructed['audit'])


def resume(state_path, output, additional_forcing):
    load_run(Path(state_path).parent)
    state = json.loads(Path(state_path).read_text(encoding='utf-8'))
    if state['schema'] != SCHEMA or sha256(state['scene_path']) != state['scene_sha256']:
        raise ValueError('state schema or scene identity mismatch')
    if state['substeps_per_month'] != MONTHLY_SUBSTEPS:
        raise ValueError('continuation integration identity mismatch')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'output already populated: {output}')
    old, extra = state['forcing'], validate_forcing(additional_forcing)
    if state['emitted_month_count'] != len(old['month_seconds']):
        raise ValueError('state emitted count does not match complete history')
    if set(old['record_ids']) & set(extra['record_ids']):
        raise ValueError('additional forcing record_ids already consumed')
    merged = dict(old)
    for key in ('month_seconds','monthly_water_m3','monthly_solid_m3'):
        merged[key] = old[key]+extra[key]
    merged['record_ids'] = old['record_ids']+extra['record_ids']
    merged = validate_forcing(merged)
    output.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(state['scene_path'],output/'scene.npz')
    (output/'forcing.json').write_text(json.dumps(merged,indent=2),encoding='utf-8')
    return save_run(output,output/'scene.npz',merged,emitted_before=state['emitted_month_count'],
        config=IntegratedDeltaConfig(**state['config']),construction_ledger=state['construction_ledger'])
