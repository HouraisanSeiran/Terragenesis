"""Explicit planning, preparation, resumption and read-only world process queries."""
from pathlib import Path
import hashlib
import json
import time
from types import SimpleNamespace
from dataclasses import asdict
from copy import deepcopy

import numpy as np
from scipy.ndimage import binary_dilation, binary_propagation

from terrain_pipeline import drainage
from terrain_pipeline.climate_forcing import MONTH_DAYS
from terrain_pipeline.common_infra import identity, array_sha256
from terrain_pipeline import world_process_hydrology as hydro
from terrain_pipeline.world_process_detail import select_regions


class _PauseAtRound(Exception):
    pass


def _content_metadata(record):
    """Separate measured execution costs from numerical content identity."""
    observed={}
    def clean(value,path):
        if isinstance(value,dict):
            result={}
            for key,item in value.items():
                if key in ('costs','cpu_seconds'):
                    observed['/'.join(path+[key])]=item
                else:
                    result[key]=clean(item,path+[key])
            return result
        if isinstance(value,list):
            return [clean(item,path+[str(i)]) for i,item in enumerate(value)]
        return value
    return clean(record,[]),observed

SCHEMA = 'terragenesis-world-process-v1'
ALGORITHM = 'world-generation-water-solid-closure-v2'
INTEGRATED_ALGORITHM = 'world-generation-integrated-environment-v3'
DEFAULTS = dict(shaping_rounds=16, equivalent_exposure_seconds=86400. * 365. * 100.,
                max_round_bed_change_m=2., initial_loose_thickness_m=1., rock_reserve_m=1000.,
                roughness=.04, chunk_cells=32768, max_cells=25_000_000,
                spinup_years=1, output_years=1, history_stages=50, history_span_ma=500.)


def _config(config):
    result = dict(DEFAULTS)
    result.update(config or {})
    if 'integrated_environment' in result and type(result['integrated_environment']) is not bool:
        raise ValueError('integrated_environment must be boolean')
    for name in ('shaping_rounds', 'chunk_cells', 'max_cells', 'history_stages'):
        if type(result[name]) is not int or result[name] < 1:
            raise ValueError(name + ' must be a positive integer')
    for name in ('equivalent_exposure_seconds', 'max_round_bed_change_m', 'roughness', 'rock_reserve_m'):
        if not np.isfinite(result[name]) or result[name] <= 0:
            raise ValueError(name + ' must be finite positive')
    if not np.isfinite(result['initial_loose_thickness_m']) or result['initial_loose_thickness_m'] < 0:
        raise ValueError('negative loose inventory')
    for name in ('pause_after_round',):
        if name in result and (type(result[name]) is not int or result[name] < 1):
            raise ValueError('positive pause round required')
    if 'wallclock_budget_seconds' in result and (not np.isfinite(result['wallclock_budget_seconds']) or result['wallclock_budget_seconds'] <= 0):
        raise ValueError('positive wallclock budget required')
    for name,upper in (('max_detail_nodes',2048),('max_estuary_cells',65536)):
        if name in result and (type(result[name]) is not int or not 1<=result[name]<=upper):
            raise ValueError(name+' exceeds bounded detailed work')
    return result


def _source(source, config):
    for name in ('elevation_m', 'ocean_mask', 'first_xz_m', 'spacing_m', 'world_seed', 'source_identity'):
        if name not in source:
            raise ValueError('missing explicit world source: ' + name)
    bed = np.asarray(source['elevation_m'], np.float64)
    if bed.ndim != 2 or min(bed.shape) < 2 or bed.size > config['max_cells'] or not np.isfinite(bed).all():
        raise ValueError('finite bounded two-dimensional world bed required')
    if np.asarray(source['ocean_mask']).shape != bed.shape:
        raise ValueError('ocean mask shape differs')
    if len(source['first_xz_m']) != 2 or not np.isfinite(source['first_xz_m']).all() or not np.isfinite(source['spacing_m']) or source['spacing_m'] <= 0:
        raise ValueError('explicit finite metric frame required')
    if not isinstance(source['source_identity'], str) or not source['source_identity']:
        raise ValueError('source identity required')
    if type(source['world_seed']) is not int or not 0<=source['world_seed']<2**64:
        raise ValueError('unsigned explicit world seed required')
    for name in ('ocean_mask', 'lagoon_mask', 'protected_mask', 'lake_id'):
        if name in source and np.asarray(source[name]).shape != bed.shape:
            raise ValueError(name + ' shape differs from world bed')
    return bed


def plan(source, config=None):
    cfg = _config(config)
    bed = _source(source, cfg)
    estimate = int(bed.size * 8 * 160 + bed.size * 12 * 4 * 10)
    if cfg.get('integrated_environment'):
        # Retained float64 owners, monthly diagnostics, climate and routing/
        # shaping workspace; publication aliases owners instead of copying them.
        estimate = max(estimate,int(bed.size*8*727+256*2**20))
    return dict(schema=SCHEMA, algorithm=INTEGRATED_ALGORITHM if cfg.get('integrated_environment') else ALGORITHM, source_identity=source['source_identity'],
                shape_zx=list(bed.shape), spacing_m=float(source['spacing_m']), world_seed=int(source['world_seed']),
                fixed_shaping_rounds=cfg['shaping_rounds'], estimated_memory_bytes=estimate,
                detailed_limits=dict(native_td_tiles=4, channel_nodes=2048, estuary_cells=65536),
                status='ready', config=cfg)


def _materials(source, bed, cfg):
    if source.get('materials') is not None:
        history = source.get('geology_history')
        if history is not None and 'layer_top_m' not in history.get('arrays', {}):
            history = None
        return source['materials'], history
    from terrain_pipeline import world_geology
    history = source.get('geology_history')
    if history is None and source.get('initial_fields') is not None:
        history = world_geology.build_history(source['initial_fields'], source['skeleton_fields'],
            world_seed=int(source['world_seed']), origin_xz_m=source.get('skeleton_origin_xz_m', source['first_xz_m']),
            spacing_m=source.get('skeleton_spacing_m', source['spacing_m']), stages=cfg['history_stages'], span_ma=cfg['history_span_ma'],
            initial_source_identity=source.get('initial_source_identity', source['source_identity'] + '/initial'),
            final_source_identity=source['source_identity'])
    if history is None:
        raise ValueError('world shaping requires declared materials or genuine initial geology history')
    # Exposure is sampled after the event bed and procedural column offset are
    # established, so uncorrected layout height cannot select a false horizon.
    return {}, history


def _geological_bed(source, bed, history, protected):
    """Apply geological events once, retaining procedural relief and coast."""
    if history is None:
        return bed.copy(), np.zeros_like(bed), np.zeros_like(bed), np.zeros_like(bed)
    a, m = history['arrays'], history['metadata']
    first, spacing = source['first_xz_m'], source['spacing_m']
    ix = np.floor((first[0] + np.arange(bed.shape[1])*spacing-m['origin_xz_m'][0])/m['spacing_m']).astype(int)
    iz = np.floor((first[1] + np.arange(bed.shape[0])*spacing-m['origin_xz_m'][1])/m['spacing_m']).astype(int)
    if np.any((ix < 0) | (ix >= m['shape_zx'][1])) or np.any((iz < 0) | (iz >= m['shape_zx'][0])):
        raise ValueError('world bed extends outside geological support')
    sample = np.ix_(iz, ix)
    geological = np.asarray(a['geological_surface_m'])[sample]
    layout = np.asarray(a['final_layout_elevation_m'])[sample]
    requested = geological-layout
    corrected = np.where(protected, 0., requested)
    # Coarse generation preserves declared land; any clipping is a separate
    # procedural adjustment, never an invented geological event.
    corrected = np.where(~protected, np.maximum(bed+corrected, .01)-bed, corrected)
    initial = bed+corrected
    return initial, initial-geological, corrected, corrected-requested


def _seasons(source, bed, route, lake_id, materials, cfg, climate=None, initial_state=None):
    from terrain_pipeline import world_environment
    if cfg.get('integrated_environment'):
        cfg = deepcopy(cfg)
        cfg['environment'] = dict(cfg.get('environment',{}), source_identity=source['source_identity'],
            terrain_revision=array_sha256(bed))
        if cfg['environment'].get('dated_events'):
            from terrain_pipeline.world_environment_state import binding
            climate=climate or source.get('climate') or world_environment.climate_fields(bed,
                world_seed=source['world_seed'],first_xz_m=source['first_xz_m'],spacing_m=source['spacing_m'],
                ocean_mask=source['ocean_mask'],config=cfg)
            target=binding(bed,np.asarray(source['ocean_mask'],bool),materials,climate.get('arrays',climate),cfg,
                source['world_seed'],source['first_xz_m'],source['spacing_m'])
            # Source events deliberately opt into this world binding. Explicit
            # foreign bindings still reject in the seasonal event owner.
            cfg['environment']['dated_events']=[dict(event,source_binding=target)
                if event.get('source_binding') in (None,'current-world') else event
                for event in cfg['environment']['dated_events']]
    return world_environment.run_seasons(bed, world_seed=int(source['world_seed']), first_xz_m=source['first_xz_m'],
        spacing_m=float(source['spacing_m']), ocean_mask=source['ocean_mask'], receiver=route.receiver, order=route.order,
        lake_id=lake_id, materials=materials, climate=climate or source.get('climate'), config=cfg, initial_state=initial_state)


def _lake_cell_storage(surface,bed,lake_id,storage,spacing):
    """Represent each actual pool stock on its wet cells without changing it."""
    cell=np.maximum(np.nan_to_num(surface.reshape(bed.shape)-bed,nan=0.),0.)*spacing**2
    labels=np.asarray(lake_id).ravel()-1
    present=np.unique(labels[labels>=0])
    for i,label in enumerate(present):
        support=labels==label
        total=float(cell.ravel()[support].sum())
        if total:
            cell.ravel()[support]*=storage[i]/total
    return cell


def _seasonal_lake_routing(seasonal,route,lake_id,bed,ocean,lagoon,spacing,initial_cell_storage=None):
    """Warm lakes with actual spinup runoff, then account only output water."""
    monthly_local=np.asarray(seasonal['arrays']['monthly_runoff_m3'],np.float64)
    integrated='integrated' in seasonal.get('state',{})
    warmup=seasonal['arrays'].get('spinup_monthly_runoff_m3',np.empty((0,)+bed.shape))
    storage=None
    released=np.zeros(bed.shape)
    carried_total=0.
    if initial_cell_storage is not None:
        prior=np.asarray(initial_cell_storage,np.float64)
        if prior.shape!=bed.shape or not np.isfinite(prior).all() or np.any(prior<0):
            raise ValueError('finite matching previous lake cell stock required')
        carried_total=float(prior.sum())
        labels=np.asarray(lake_id).ravel()-1
        present=np.unique(labels[labels>=0])
        labels=np.where(labels>=0,np.searchsorted(present,labels),-1)
        wet=labels>=0
        capacity=np.bincount(labels[wet],weights=(np.maximum(route.filled.ravel()-bed.ravel(),0.)*spacing**2)[wet],minlength=present.size)
        totals=np.bincount(labels[wet],weights=prior.ravel()[wet],minlength=present.size)
        storage=np.minimum(totals,capacity).astype(np.float64)
        fractions=np.divide(storage,totals,out=np.zeros_like(storage),where=totals>0)
        released=prior.copy().ravel()
        released[wet]*=1.-fractions[labels[wet]]
        released=released.reshape(bed.shape)
    warmup_ledger=[]
    output_ledger=[]
    monthly_flow=[]
    terminal=route.receiver<0
    marine_terminal=terminal&(ocean|lagoon).ravel()
    external_terminal=terminal&~(ocean|lagoon).ravel()
    for phase,intervals in (('spinup',warmup),('output',monthly_local)):
        for index,local in enumerate(intervals):
            local=np.where(ocean|lagoon,0.,local)
            prior_release=float(released.sum()) if phase=='output' and index==0 else 0.
            if prior_release:
                local=local+released
            flow,surface,ledger=hydro.lake_balance(local,route.receiver,route.order,lake_id,bed,route.filled,
                spacing**2,storage,compute_surface=index==len(intervals)-1 and (phase=='output' or integrated))
            storage=ledger.pop('storage_by_pool_m3')
            ledger.update(local_runoff_m3=float(local.sum()),
                marine_export_m3=float(flow[marine_terminal].sum()),
                external_dependency_m3=float(flow[external_terminal].sum()))
            ledger['residual_m3']=(ledger['initial_storage_m3']+ledger['local_runoff_m3']-
                ledger['final_storage_m3']-ledger['marine_export_m3']-ledger['external_dependency_m3'])
            if phase=='spinup':
                warmup_ledger.append(ledger)
            else:
                if index==0 and initial_cell_storage is not None:
                    ledger['initial_storage_m3']+=prior_release
                    ledger['local_runoff_m3']-=prior_release
                output_ledger.append(ledger)
                monthly_flow.append(flow.reshape(bed.shape))
        if phase=='spinup':
            output_initial_storage=(carried_total if initial_cell_storage is not None else
                0. if storage is None else float(storage.sum()))
            if integrated:
                if initial_cell_storage is not None:
                    initial_cell=np.asarray(initial_cell_storage).copy()
                elif len(warmup):
                    initial_cell=_lake_cell_storage(surface,bed,lake_id,storage,spacing)
                else:
                    initial_cell=np.zeros(bed.shape)
    final_storage=float(storage.sum())
    water=dict(initial_storage_m3=output_initial_storage,final_storage_m3=final_storage,
        retained_m3=final_storage-output_initial_storage,monthly=output_ledger,
        local_runoff_m3=sum(row['local_runoff_m3'] for row in output_ledger),
        marine_export_m3=sum(row['marine_export_m3'] for row in output_ledger),
        external_dependency_m3=sum(row['external_dependency_m3'] for row in output_ledger),
        spinup=dict(status='computed' if len(warmup) else 'no-spinup-runoff',months_completed=len(warmup),
            initial_storage_m3=0.,final_storage_m3=output_initial_storage,monthly=warmup_ledger))
    water['residual_m3']=(water['initial_storage_m3']+water['local_runoff_m3']-
        water['final_storage_m3']-water['marine_export_m3']-water['external_dependency_m3'])
    if integrated:
        seasonal['arrays']['initial_lake_storage_m3']=initial_cell
        cell=_lake_cell_storage(surface,bed,lake_id,storage,spacing)
        seasonal['arrays']['final_lake_storage_m3']=cell
        routed=np.asarray(monthly_flow).sum(axis=0)
        seasonal['arrays'].update(lake_pre_native_initial_storage_m3=initial_cell,
            lake_pre_native_final_storage_m3=cell,
            lake_pre_native_local_runoff_m3=np.where(ocean|lagoon,0.,monthly_local.sum(axis=0)),
            lake_pre_native_marine_export_m3=np.where(marine_terminal.reshape(bed.shape),routed,0.),
            lake_pre_native_external_dependency_m3=np.where(external_terminal.reshape(bed.shape),routed,0.))
        water['lake_stock_remap']=dict(previous_storage_m3=carried_total,
            released_by_capacity_or_topology_m3=float(released.sum()),semantics='previous cell stocks remapped into actual new pools; finite overflow enters first routed interval once')
        water['routing_witness_semantics']='lake_pre_native_* and lake_post_native_* arrays are diagnostic stock/terminal snapshots at their actual stage topology, not additional inventory owners'
    return np.asarray(monthly_flow),surface,water


def _environment_stage(generation, seasonal):
    """Generation bed effects alone do not complete seasonal mechanisms."""
    if generation.get('status') != 'complete' or not seasonal.get('processes'):
        return 'partial-or-pending'
    completed = {'computed', 'complete', 'not-triggered'}
    for metadata in (generation, seasonal):
        if metadata.get('pending_processes'):
            return 'partial-or-pending'
        for process in metadata.get('processes', {}).values():
            if process.get('status') not in completed:
                return 'partial-or-pending'
    return 'complete'


def _post_native_lakes(seasonal,arrays,route,lakes,bed,ocean,lagoon,spacing,monthly,water):
    """Route only new native liquid and retained lake water after the bed commit.

    The annual runoff already routed before native debit is never replayed.
    Post-interval pool changes conservatively remap the actual retained stock.
    """
    initial=np.asarray(seasonal['arrays']['final_lake_storage_m3']).copy()
    tail=dict(arrays=dict(monthly_runoff_m3=np.asarray(arrays['native_glacier_runoff_m3'])[None]),
        state=dict(integrated={}))
    tail_flow,surface,tail_budget=_seasonal_lake_routing(tail,route,lakes,bed,ocean,lagoon,spacing,initial)
    result=np.asarray(monthly).copy()
    result[-1]+=tail_flow[0]
    final=dict(water)
    final['final_storage_m3']=tail_budget['final_storage_m3']
    final['retained_m3']=final['final_storage_m3']-final['initial_storage_m3']
    for key in ('local_runoff_m3','marine_export_m3','external_dependency_m3'):
        final[key]+=tail_budget[key]
    final['post_native_interval']=tail_budget
    final['residual_m3']=final['initial_storage_m3']+final['local_runoff_m3']-final['final_storage_m3']-final['marine_export_m3']-final['external_dependency_m3']
    seasonal['arrays']['final_lake_storage_m3']=tail['arrays']['final_lake_storage_m3']
    post=dict(lake_post_native_marine_export_m3=tail['arrays']['lake_pre_native_marine_export_m3'],
        lake_post_native_external_dependency_m3=tail['arrays']['lake_pre_native_external_dependency_m3'])
    seasonal['arrays'].update(post)
    arrays.update(post)
    final['routing_time_semantics']='annual water routed once before native stage; only new native liquid and finite lake remap routed on committed bed; next annual interval uses new topology'
    return result,surface,final


def compute(source, config=None, *, checkpoint_callback=None, _initial_state=None, _stop_after_round=None):
    started = time.perf_counter()
    cfg = _config(config)
    source_bed = _source(source, cfg)
    initial_bed = source_bed
    shape = initial_bed.shape
    ocean = np.asarray(source['ocean_mask'], bool)
    lagoon = np.asarray(source.get('lagoon_mask', np.zeros(shape, bool)), bool)
    protected = np.asarray(source.get('protected_mask', np.zeros(shape, bool)), bool) | ocean | lagoon
    protected |= binary_dilation(ocean | lagoon) & ~ocean
    mesh = source.get('mesh')
    if mesh is None:
        mesh = drainage.grid_mesh(shape, x0_m=source['first_xz_m'][0], z0_m=source['first_xz_m'][1], dx_m=source['spacing_m'], world_seed=int(source['world_seed']))
    materials, history = _materials(source, initial_bed, cfg)
    initial_bed, column_offset, geology_delta, geology_protection = _geological_bed(source, source_bed, history, protected)
    x, z = np.meshgrid(source['first_xz_m'][0] + np.arange(shape[1]) * source['spacing_m'],
                       source['first_xz_m'][1] + np.arange(shape[0]) * source['spacing_m'])
    if history is not None:
        from terrain_pipeline import world_geology
        exposed = world_geology.sample_materials(history,x,z,initial_bed-column_offset)
        materials = exposed.get('arrays',exposed)
    porosity = np.broadcast_to(np.asarray(materials.get('porosity', .35)), shape).ravel()
    if not np.isfinite(porosity).all() or np.any((porosity < 0) | (porosity >= 1)):
        raise ValueError('finite material porosity in [0,1) required')
    loose_depth = np.broadcast_to(np.asarray(source.get('initial_loose_thickness_m', cfg['initial_loose_thickness_m'])), shape)
    if not np.isfinite(loose_depth).all() or np.any(loose_depth < 0):
        raise ValueError('finite nonnegative loose material thickness required')
    initial_loose = np.where(ocean | lagoon, 0., loose_depth * source['spacing_m'] ** 2 * (1 - porosity.reshape(shape))).ravel()
    bed = initial_bed.copy()
    loose = initial_loose.copy()
    rock = np.zeros(bed.size)
    mobile = np.zeros(bed.size)
    marine = np.zeros(bed.size)
    external = np.zeros(bed.size)
    erosion = np.zeros(bed.size)
    deposition = np.zeros(bed.size)
    transported = np.zeros(bed.size)
    airborne = np.zeros(shape)
    dissolved = np.zeros(shape)
    environmental_arrays = {}
    generation_environment = dict(status='pending-input', reason='complete seasonal material and weathering fields required')
    initial_route = hydro.routing(initial_bed, ocean, lagoon, mesh)
    initial_labels, _ = drainage.pool_labels(initial_bed.ravel(), initial_route.filled.ravel(), mesh.indptr, mesh.indices)
    initial_lakes = np.where((ocean|lagoon).ravel(), 0, initial_labels+1).reshape(shape).astype(np.int32)
    seasonal = _seasons(source, initial_bed, initial_route, initial_lakes, materials, cfg)
    required_environment = ('temperature_c','soil_water_mm','cover_fraction','monthly_weathered_rock_m')
    if all(name in seasonal['arrays'] for name in required_environment):
        from terrain_pipeline.world_environment_world import generation_environment as prepare_environment
        environment_source = dict(source, elevation_m=initial_bed, loose_solid_m3=loose.reshape(shape),
            receiver=initial_route.receiver.reshape(shape), mesh=mesh, protected_mask=protected,
            rock_remaining_m3=np.full(shape,cfg['rock_reserve_m']*source['spacing_m']**2))
        generated = prepare_environment(environment_source, materials, seasonal, history, cfg)
        ga = generated['arrays']
        environmental_arrays = {'generation_environment_'+name:np.asarray(value)
            for name,value in ga.items() if isinstance(value,np.ndarray)}
        generation_environment = generated['metadata']
        loose = np.asarray(ga['loose_solid_m3']).ravel().copy()
        rock = np.asarray(ga['weathered_rock_m3']).ravel().copy()
        marine = np.asarray(ga['marine_received_solid_m3']).ravel().copy()
        external = np.asarray(ga['boundary_export_solid_m3']).ravel().copy()
        airborne = np.asarray(ga['airborne_solid_m3']).copy()
        dissolved = np.asarray(ga['dissolved_solid_m3']).copy()
        initial_bed = initial_bed + np.asarray(ga.get('volcanic_height_change_m', np.zeros(shape)))
        bed = initial_bed + (loose-initial_loose).reshape(shape)/(source['spacing_m']**2*(1-porosity.reshape(shape)))-rock.reshape(shape)/source['spacing_m']**2
    prepared_regions = []
    if source.get('environment_regions'):
        from terrain_pipeline.world_environment_regions import dispatch_prepared_regions
        if sum(row.get('kind')=='aeolian' for row in source['environment_regions'])>1:
            raise ValueError('one owner required for the full-world prepared wind accounts')
        bound_regions=[]
        for record in source['environment_regions']:
            record=deepcopy(record)
            if record.get('kind')=='aeolian':
                context=record.get('context',{})
                if (not np.array_equal(context.get('height_m'),bed) or
                        context.get('spacing_m')!=source['spacing_m'] or
                        not np.array_equal(context.get('ocean_mask'),ocean)):
                    raise ValueError('prepared environment must bind the current world bed and ocean')
                for name,value in (('loose_solid_m3',loose.reshape(shape)),('airborne_solid_m3',airborne)):
                    if not np.array_equal(record.get('state',{}).get(name),value):
                        raise ValueError('prepared environment initial inventory differs: '+name)
                for name,value in (('valid_mask',np.ones(shape,bool)),('protected_mask',protected)):
                    if name in context and not np.array_equal(context[name],value):
                        raise ValueError('prepared environment geometry differs: '+name)
                    context[name]=value
            bound_regions.append(record)
        prepared_regions = dispatch_prepared_regions(bound_regions,
            expected_source_identity=source['source_identity'])
        for index,row in enumerate(prepared_regions):
            if row.get('status') != 'computed':
                continue
            state = row.get('state', {})
            for name,value in state.items():
                if isinstance(value,np.ndarray) and not value.dtype.hasobject:
                    environmental_arrays['prepared_environment_%d_%s'%(index,name)]=value
            if row['kind']=='aeolian':
                loose = np.asarray(state['loose_solid_m3'], np.float64).ravel().copy()
                airborne = np.asarray(state['airborne_solid_m3'], np.float64).copy()
                for flux in row['fluxes']:
                    external+=np.asarray(flux['boundary_export_solid_m3']).ravel()
                bed=initial_bed+(loose-initial_loose).reshape(shape)/(source['spacing_m']**2*(1-porosity.reshape(shape)))-rock.reshape(shape)/source['spacing_m']**2
                row['publication']='matching full-world wind stocks replaced once; boundary export debited separately'
            else:
                row.update(status='pending-publication',
                    reason='regional proposal retained; no bound replacement of this mechanism world accounts')
        generation_environment = dict(generation_environment,
            prepared_regions=[{k: v for k, v in row.items() if k not in ('state','fluxes')} for row in prepared_regions],
            prepared_region_semantics='bound wind stocks replace matching accounts; other regional proposals remain separately persisted pending publication')
        if any(row.get('status') != 'computed' for row in prepared_regions):
            generation_environment = dict(generation_environment, status='partial-or-pending')
    shaping_initial_bed=bed.copy()
    shaping_initial_loose=loose.copy()
    shaping_initial_rock=rock.copy()
    start_round = 0
    if _initial_state is not None:
        state = _initial_state
        start_round = int(state['round'])
        bed, loose, rock, mobile, marine, external, erosion, deposition = (np.asarray(state[name]).copy() for name in ('bed', 'loose', 'rock', 'mobile', 'marine', 'external', 'erosion', 'deposition'))
        transported = np.asarray(state['transported']).copy()
    local_water = np.asarray(seasonal['arrays']['monthly_runoff_m3'], np.float64).sum(axis=0)
    if local_water.shape != shape or not np.isfinite(local_water).all() or np.any(local_water < 0):
        raise ValueError('monthly runoff must contain finite local volumes')
    local_water = np.where(ocean | lagoon, 0., local_water)
    route = initial_route
    shaping_water = ([] if _initial_state is None else
                     json.loads(str(_initial_state['shaping_water_json'])))
    for round_index in range(start_round, cfg['shaping_rounds']):
        if history is not None:
            from terrain_pipeline import world_geology
            exposed = world_geology.sample_materials(history, x, z, bed-column_offset)
            materials = exposed.get('arrays', exposed)
        route = hydro.routing(bed, ocean, lagoon, mesh)
        round_labels, _ = drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
        round_lakes = np.where((ocean|lagoon).ravel(),0,round_labels+1).reshape(shape).astype(np.int32)
        flow, _, round_water = hydro.lake_balance(local_water, route.receiver, route.order, round_lakes, bed, route.filled, source['spacing_m'] ** 2, compute_surface=False)
        round_water.pop('storage_by_pool_m3')
        terminal=route.receiver<0
        round_water.update(local_runoff_m3=float(local_water.sum()),
            marine_export_m3=float(flow[terminal&(ocean|lagoon).ravel()].sum()),
            external_dependency_m3=float(flow[terminal&~(ocean|lagoon).ravel()].sum()))
        round_water['residual_m3']=(round_water['local_runoff_m3']-round_water['marine_export_m3']-
            round_water['external_dependency_m3']-round_water['retained_m3'])
        shaping_water.append(round_water)
        q = flow.reshape(shape) / (365. * 86400. * cfg['output_years'])
        sediment_materials = dict(materials, porosity=porosity.reshape(shape))
        if cfg.get('integrated_environment') and 'manning_n' in seasonal['arrays']:
            sediment_materials['manning_n'] = seasonal['arrays']['manning_n']
        bed, loose, rock, mobile, ledger, hydraulic = hydro.shape_round(bed, initial_bed, initial_loose, loose, rock, mobile,
            route.receiver, route.order, q, mesh, ocean, lagoon, round_lakes, protected, sediment_materials, cfg)
        marine += ledger['marine_solid_m3']
        external += ledger['external_solid_m3']
        erosion += ledger['eroded_rock_m3'] + ledger['eroded_loose_solid_m3'] / (1 - porosity)
        deposition += ledger['deposited_solid_m3'] / (1 - porosity)
        transported += ledger['outgoing_solid_m3']
        state = dict(round=round_index + 1, bed=bed, loose=loose, rock=rock, mobile=mobile, marine=marine, external=external, erosion=erosion, deposition=deposition, transported=transported,
            shaping_water_json=np.array(json.dumps(shaping_water,sort_keys=True)))
        if checkpoint_callback is not None:
            checkpoint_callback(state)
        if _stop_after_round is not None and round_index + 1 >= _stop_after_round and round_index + 1 < cfg['shaping_rounds']:
            return dict(status='paused', state=state)
    route = hydro.routing(bed, ocean, lagoon, mesh)
    # Re-label actual final depressions on the existing irregular graph.
    labels, count = drainage.pool_labels(bed.ravel(), route.filled.ravel(), mesh.indptr, mesh.indices)
    final_lakes = np.where(ocean.ravel() | lagoon.ravel(), 0, labels + 1).reshape(shape).astype(np.int32)
    if history is not None:
        exposed = world_geology.sample_materials(history, x, z, bed-column_offset)
        materials = exposed.get('arrays',exposed)
    native_preparation = None
    final_climate = None
    if cfg.get('integrated_environment'):
        # No trial owner is retained alongside the authoritative final solve.
        del seasonal
        from terrain_pipeline.world_environment import climate_fields
        from terrain_pipeline.world_environment_world import sea_climate_preparation, persist_seasonal
        climate = source.get('climate') or climate_fields(bed,world_seed=source['world_seed'],
            first_xz_m=source['first_xz_m'],spacing_m=source['spacing_m'],ocean_mask=ocean,config=cfg)
        final_climate,native_preparation,sea_temperature,sea_feedback = sea_climate_preparation(source,bed,climate,cfg)
    final_seasonal = _seasons(source, bed, route, final_lakes, materials, cfg, final_climate)
    if cfg.get('integrated_environment'):
        # The generation trial supplied rates for equivalent shaping. It is not
        # a second retained ecological/water inventory. Only final state owns it.
        from terrain_pipeline.world_environment_world import pack_state
        weathered_final = np.asarray(final_seasonal['state']['weathered_rock_m'])*source['spacing_m']**2
        weathered_final = np.where(~protected,weathered_final,0.)
        weathered_final = np.minimum(weathered_final,np.maximum(cfg['rock_reserve_m']*source['spacing_m']**2-rock.reshape(shape),0.))
        from terrain_pipeline.soil_water import normalize_parameters
        dissolved_fraction = normalize_parameters(cfg.get('weathering_parameters'))['dissolved_fraction_of_solid']['value']
        final_regolith = weathered_final*(1.-dissolved_fraction)
        loose += final_regolith.ravel()
        rock += weathered_final.ravel()
        dissolved += weathered_final*dissolved_fraction
        bed += final_regolith/(source['spacing_m']**2*(1-porosity.reshape(shape)))-weathered_final/source['spacing_m']**2
        commit = final_seasonal['metadata']['environment_bed_commit']
        heave = np.asarray(final_seasonal['arrays']['environment_proposed_height_change_m'])
        bed += np.where(protected,0.,heave)
        commit.update(status='committed',committed_once=True,
            protected_adjustment_m3=float(heave[protected].sum()*source['spacing_m']**2),
            final_bed_revision=array_sha256(bed))
        final_seasonal['metadata']['generation_trial_semantics']='discarded diagnostic owners; its rates drive a separately debited equivalent generation event; only final seasonal owners retained'
        final_seasonal['arrays']['final_seasonal_weathered_rock_m3']=weathered_final
        final_seasonal['arrays']['final_seasonal_regolith_solid_m3']=final_regolith
        final_seasonal['arrays']['sea_temperature_c']=sea_temperature
        final_seasonal['arrays']['sea_air_temperature_feedback_c']=sea_feedback
        final_seasonal['metadata']['sea_preparation']=native_preparation['metadata']
        final_seasonal['metadata']['sea_preparation_ledger']=native_preparation['ledger']
        final_seasonal['metadata']['sea_preparation_state']=pack_state(native_preparation,
            final_seasonal['arrays'],'sea_preparation_state')
        persist_seasonal(final_seasonal)
        # Derivatives consume the committed bed; seasonal stocks are not rerun.
        route = hydro.routing(bed,ocean,lagoon,mesh)
        labels,count = drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
        final_lakes=np.where((ocean|lagoon).ravel(),0,labels+1).reshape(shape).astype(np.int32)
    monthly_flow,lake_surface,water=_seasonal_lake_routing(final_seasonal,route,final_lakes,bed,ocean,lagoon,float(source['spacing_m']))
    flow = monthly_flow.sum(axis=0).ravel()
    discharge = flow.reshape(shape) / (365. * 86400. * cfg['output_years'])
    solid = dict(initial_loose_solid_m3=float(initial_loose.sum()), final_loose_solid_m3=float(loose.sum()), initial_mobile_solid_m3=0., final_mobile_solid_m3=float(mobile.sum()), rock_removed_m3=float(rock.sum()), marine_received_solid_m3=float(marine.sum()), external_dependency_solid_m3=float(external.sum()))
    solid['initial_bedrock_reserve_m3']=float(cfg['rock_reserve_m']*initial_bed.size*source['spacing_m']**2)
    solid['final_bedrock_reserve_m3']=solid['initial_bedrock_reserve_m3']-solid['rock_removed_m3']
    solid['bedrock_residual_m3']=solid['initial_bedrock_reserve_m3']-solid['final_bedrock_reserve_m3']-solid['rock_removed_m3']
    solid['residual_m3'] = solid['initial_loose_solid_m3'] + solid['rock_removed_m3'] - solid['final_loose_solid_m3'] - solid['final_mobile_solid_m3'] - solid['marine_received_solid_m3'] - solid['external_dependency_solid_m3']
    solid.update(final_airborne_solid_m3=float(airborne.sum()), dissolved_solid_m3=float(dissolved.sum()))
    solid['residual_m3'] -= solid['final_airborne_solid_m3']+solid['dissolved_solid_m3']
    area = drainage.accumulate_graph(route.receiver, route.order, np.full(shape, source['spacing_m'] ** 2))
    arrays = dict(final_seasonal['arrays'])
    arrays.update(environmental_arrays)
    arrays.update(elevation_m=bed, receiver=route.receiver.reshape(shape), order=route.order,
        initial_elevation_m=initial_bed, ocean_mask=ocean, lagoon_mask=lagoon, protected_mask=protected,
        shaping_initial_elevation_m=shaping_initial_bed,shaping_initial_loose_solid_m3=shaping_initial_loose.reshape(shape),
        shaping_initial_rock_removed_m3=shaping_initial_rock.reshape(shape),
        layout_elevation_m=source_bed, geological_height_change_m=geology_delta,
        geological_protection_adjustment_m=geology_protection, geological_column_offset_m=column_offset,
        environment_airborne_solid_m3=airborne, environment_dissolved_solid_m3=dissolved,
        lake_id=final_lakes, drainage_area_m2=area, discharge_m3_s=discharge,
        water_surface_m=lake_surface.reshape(shape), erosion_m=erosion.reshape(shape) / source['spacing_m'] ** 2,
        deposition_m=deposition.reshape(shape) / source['spacing_m'] ** 2, loose_solid_m3=loose.reshape(shape),
        initial_loose_solid_m3=initial_loose.reshape(shape),
        rock_removed_m3=rock.reshape(shape), marine_received_solid_m3=marine.reshape(shape), external_dependency_solid_m3=external.reshape(shape))
    arrays['mobile_solid_m3'] = mobile.reshape(shape)
    arrays['monthly_routed_volume_m3'] = np.asarray(monthly_flow)
    monthly_seconds=np.tile(np.asarray(MONTH_DAYS,np.float64)*86400.,cfg['output_years'])
    arrays['monthly_discharge_m3_s']=monthly_flow/monthly_seconds[:,None,None]
    arrays['generation_transported_solid_m3'] = transported.reshape(shape)
    for name in ('node_x_m','node_z_m','indptr','indices','edge_length_m'):
        arrays['routing_mesh_'+name]=np.asarray(getattr(mesh,name))
    for name, value in materials.items():
        if isinstance(value, np.ndarray) and value.shape == shape:
            arrays[name] = value
    metadata = dict(schema=SCHEMA, algorithm=INTEGRATED_ALGORITHM if cfg.get('integrated_environment') else ALGORITHM, source_identity=source['source_identity'], world_seed=int(source['world_seed']),
        plate_identity=source.get('plate_identity',source['source_identity']),
        island_provenance=source.get('island_provenance'), generation_environment=generation_environment,
        first_xz_m=list(source['first_xz_m']), spacing_m=float(source['spacing_m']), config=cfg, status='complete',
        shaping=dict(rounds=cfg['shaping_rounds'], semantics='equivalent generation shaping; not continuous geological-time hydraulics',
                     channel_geometry_excavation_m3=0., old_unbudgeted_erosion_replaced=True),
        water_budget=water, shaping_water_budget=shaping_water, solid_budget=solid, environment=final_seasonal['metadata'],
        monthly_discharge_semantics='actual monthly lake-routed volume divided by its physical month duration; warmup excluded',
        geology=None if history is None else history['metadata'],
        stages=dict(coarse_water_sediment='complete', geology='declared-materials-only' if history is None else 'complete',
            environment=_environment_stage(generation_environment, final_seasonal['metadata']), detailed='pending-terrain'),
        sources=dict(routing='terrain_pipeline.drainage.route_graph', lake_storage='terrain_pipeline.drainage.route_pool_interval', hydraulics='surface_hydraulics._hydraulics rectangular Manning', sediment_rates='surface_rivers.metric_sediment._rates', bed_conversion='metric_bed_update.bed_from_inventory'),
        limits=['Finite-domain land rim is an external dependency, not an ocean mouth.',
                'Coarse shaping uses fixed equivalent exposure with conservative DAG transfer, not transient sediment CFL replay.',
                'Marine sediment is a receiving stock; coarse shoreline is protected.',
                'Depositional porosity remains the initial declared sediment porosity; exposed bedrock resistance is resampled each round.',
                'Final seasonal hydrology is independent of equivalent shaping rounds.'], cpu_seconds=time.perf_counter() - started)
    metadata['geological_bed_application'] = dict(sampling='nearest geological cell in absolute coordinates; local procedural relief retained as column offset',
        applied_displacement_m3=float(geology_delta.sum()*source['spacing_m']**2),
        protection_layout_adjustment_m3=float(geology_protection.sum()*source['spacing_m']**2))
    metadata['input_binding'] = dict(elevation_m=array_sha256(source_bed),ocean_mask=array_sha256(ocean),
        lagoon_mask=array_sha256(lagoon),protected_mask=array_sha256(protected),
        mesh=identity({name:np.asarray(getattr(mesh,name)) for name in
            ('node_x_m','node_z_m','indptr','indices','edge_length_m')},
            dict(shape=list(mesh.shape),spacing_m=float(mesh.spacing_m))),
        initial_loose_solid_m3=array_sha256(initial_loose),
        geology_identity=None if history is None else history['metadata'].get('identity'))
    details = select_regions(source, arrays, cfg)
    if cfg.get('integrated_environment'):
        from terrain_pipeline import world_environment_native
        from terrain_pipeline.world_environment_world import pack_state, advance_native_world
        native_source=dict(source,elevation_m=bed,parent_terrain_revision=array_sha256(bed),
            plate_identity=source.get('plate_identity',source['source_identity']),rock_reserve_m=np.maximum(
                cfg['rock_reserve_m']-rock.reshape(shape)/source['spacing_m']**2,0.),
            discharge_m3_s=discharge,protected_mask=protected,climate=dict(arrays=final_climate))
        native_plan=world_environment_native.plan(native_source,cfg.get('native_environment'))
        native_source['snow_history']=native_plan['history']
        native_source['authorized_river_detail_global_ids']=[candidate['node'] for candidate in native_plan['candidates']
            if candidate['kind']=='coast']
        prepared=world_environment_native.prepare(native_source,native_terrain=source.get('native_terrain',()),
            config=cfg.get('native_environment'))
        prepared['historical_climate']={key:final_climate[key] for key in
            ('monthly_temperature_c','monthly_precipitation_mm')}
        prepared,native_result,inbound=advance_native_world(native_source,prepared,native_preparation,arrays,final_seasonal,cfg)
        bed=np.asarray(arrays['elevation_m'])
        route=hydro.routing(bed,ocean,lagoon,mesh)
        labels,_=drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
        final_lakes=np.where((ocean|lagoon).ravel(),0,labels+1).reshape(shape).astype(np.int32)
        monthly_flow,lake_surface,water=_post_native_lakes(final_seasonal,arrays,route,final_lakes,bed,ocean,lagoon,
            float(source['spacing_m']),monthly_flow,water)
        flow=monthly_flow.sum(axis=0).ravel()
        arrays.update(receiver=route.receiver.reshape(shape),order=route.order,lake_id=final_lakes,
            water_surface_m=lake_surface.reshape(shape),monthly_routed_volume_m3=monthly_flow,
            monthly_discharge_m3_s=monthly_flow/monthly_seconds[:,None,None],
            discharge_m3_s=flow.reshape(shape)/(365.*86400.*cfg['output_years']),
            drainage_area_m2=drainage.accumulate_graph(route.receiver,route.order,np.full(shape,source['spacing_m']**2)))
        metadata['water_budget']=water
        metadata['native_environment']=dict(metadata=native_result['metadata'],statuses=native_result['statuses'],candidates=prepared['candidates'],
            inbound_packets=inbound,ledger=native_result['ledger'],
            result_record=pack_state(native_result,arrays,'native_result'),
            prepared_record=pack_state(prepared,arrays,'native_prepared'))
        metadata['environment']['processes'].update({key:native_result['statuses'][key] for key in ('glacier','coastal_exchange','basin_water_heat')})
        if native_result['statuses']['basin_water_heat']['status']=='computed':
            metadata['environment']['processes']['basin_water_heat']=dict(status='computed',
                scope='finite prior sea water/heat; actual temperature consumed by coastal air forcing',
                actual_consumer=native_preparation['metadata']['actual_consumer'])
        metadata['final_owner_semantics']='one retained final seasonal owner; native stocks separate; state arrays preserve clocks, packets and events'
        native_solid=sum(float(np.sum(stock['core']['bed_solid_m3'])) for rid,stock in prepared['state'].items()
            if rid!='_exchange' and isinstance(stock.get('core'),dict) and 'bed_solid_m3' in stock['core'])
        solid.update(final_native_coast_solid_m3=native_solid,final_loose_solid_m3=float(arrays['loose_solid_m3'].sum()),
            final_mobile_solid_m3=float(arrays['mobile_solid_m3'].sum()),rock_removed_m3=float(arrays['rock_removed_m3'].sum()),
            marine_received_solid_m3=float(arrays['marine_received_solid_m3'].sum()))
        solid['final_bedrock_reserve_m3']=solid['initial_bedrock_reserve_m3']-solid['rock_removed_m3']
        solid['residual_m3']=(solid['initial_loose_solid_m3']+solid['rock_removed_m3']-
            sum(solid.get(key,0.) for key in ('final_loose_solid_m3','final_mobile_solid_m3','marine_received_solid_m3',
                'external_dependency_solid_m3','final_airborne_solid_m3','dissolved_solid_m3','final_native_coast_solid_m3')))
        metadata['stages']['environment']=_environment_stage(generation_environment,metadata['environment'])
        details=select_regions(source,arrays,cfg)
        from terrain_pipeline.world_environment_world import rebase_seasonal
        rebase_seasonal(final_seasonal,dict(source,elevation_m=bed),materials,final_climate,cfg)
        # Arrays was constructed before rebase; refresh scalar descriptors and
        # shared state-array aliases without copying all owner arrays.
        arrays.update(final_seasonal['arrays'])
    if cfg.get('integrated_environment'):
        metadata,observed=_content_metadata(metadata)
        return dict(arrays=arrays,metadata=metadata,details=details,geology_history=history,
            performance=dict(observed_costs=observed))
    return dict(arrays=arrays, metadata=metadata, details=details, geology_history=history)


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            result.update(block)
    return result.hexdigest()


def _json(path, data):
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def _record_identity(record, excluded=('manifest_identity',)):
    payload = {k: v for k, v in record.items() if k not in excluded}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _bound_path(root, filename):
    path = (Path(root) / filename).resolve()
    if path.parent != Path(root).resolve():
        raise ValueError('product path escapes preparation directory')
    return path


def _write_checkpoint(root, record):
    record['checkpoint_identity'] = _record_identity(record, ('checkpoint_identity',))
    _json(root / 'checkpoint.json', record)


def _save_source(source, root):
    def encode(value, path):
        if isinstance(value, np.ndarray):
            filename = 'source_' + '__'.join(path) + '.npy'
            np.save(root / filename, value, allow_pickle=False)
            return dict(npy_file=filename)
        if isinstance(value, dict):
            if any(not isinstance(k,str) or not k or '/' in k or '\\' in k for k in value):
                raise ValueError('source keys must be safe field names')
            return {k: encode(v, path + [k]) for k, v in value.items()}
        if isinstance(value, tuple):
            return dict(tuple_values=[encode(v, path + [str(i)]) for i, v in enumerate(value)])
        if isinstance(value, list):
            return [encode(v, path + [str(i)]) for i, v in enumerate(value)]
        if isinstance(value, np.generic):
            return value.item()
        return value
    fields = dict(source)
    if fields.get('mesh') is not None:
        mesh = fields['mesh']
        fields['mesh'] = dict(mesh_fields=asdict(mesh) if hasattr(mesh, '__dataclass_fields__') else vars(mesh))
    return encode(fields, [])


def _load_source(root, record):
    def decode(value):
        if isinstance(value, dict):
            if set(value) == {'npy_file'}:
                return np.load(_bound_path(root, value['npy_file']), mmap_mode='r', allow_pickle=False)
            if set(value) == {'tuple_values'}:
                return tuple(decode(v) for v in value['tuple_values'])
            if set(value) == {'mesh_fields'}:
                return SimpleNamespace(**decode(value['mesh_fields']))
            return {k: decode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [decode(v) for v in value]
        return value
    return decode(record)


def prepare(source, out_dir, config=None, *, resume=False):
    if resume:
        return globals()['resume'](Path(out_dir) / 'checkpoint.json', out_dir)
    cfg = _config(config)
    preparation_plan = plan(source, cfg)
    try:
        import psutil
        required = max(2 * 2 ** 30, preparation_plan['estimated_memory_bytes'])
        wait_s = float(cfg.get('memory_wait_s', 0.))
        poll_s = float(cfg.get('memory_poll_s', 5.))
        deadline = time.perf_counter() + max(0., wait_s)
        while True:
            available = psutil.virtual_memory().available
            if available >= required:
                break
            if wait_s <= 0 or time.perf_counter() >= deadline:
                raise MemoryError('world process preparation memory gate: need %d available bytes' % required)
            time.sleep(max(0.05, min(poll_s, deadline - time.perf_counter())))
    except ImportError:
        if source['elevation_m'].size > 65536:
            raise RuntimeError('psutil is required for large world process preparation')
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=False)
    source_record = _save_source(source, root)
    source_files = {p.name: _digest(p) for p in root.glob('source_*')}
    checkpoint = dict(schema=SCHEMA, source=source_record, source_files=source_files, config=cfg, round=0, state_file=None)
    _write_checkpoint(root, checkpoint)
    return _execute_saved(source, root, cfg, checkpoint, None)


def _execute_saved(source, root, cfg, checkpoint, state):
    started = time.perf_counter()
    def save_state(current):
        target = root / ('round-%02d.npz' % current['round'])
        np.savez(target, **current)
        checkpoint.update(round=current['round'], state_file=target.name, state_sha256=_digest(target))
        _write_checkpoint(root, checkpoint)
    stop_after = cfg.get('pause_after_round')
    def callback(current):
        save_state(current)
        budget = cfg.get('wallclock_budget_seconds')
        if budget is not None and time.perf_counter() - started >= budget and current['round'] < cfg['shaping_rounds']:
            raise _PauseAtRound()
    try:
        result = compute(source, cfg, checkpoint_callback=callback, _initial_state=state, _stop_after_round=stop_after)
    except _PauseAtRound:
        return dict(status='paused', checkpoint=str(root / 'checkpoint.json'), round=checkpoint['round'])
    if result.get('status') == 'paused':
        return dict(status='paused', checkpoint=str(root / 'checkpoint.json'), round=checkpoint['round'])
    return _publish_product(result, root, time.perf_counter() - started)


def save_product(result, out_dir):
    """Publish an already computed result once; never repeat shaping or seasons."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=False)
    try:
        return _publish_product(result, root, result['metadata'].get('cpu_seconds', 0.))
    except Exception:
        # No manifest means an incomplete product, which query always rejects.
        # Keep diagnostic files rather than deleting a user's output directory.
        raise


def _publish_product(result, root, seconds):
    if (root / 'manifest.json').exists():
        raise FileExistsError('published world process products are immutable')
    arrays = result['arrays']
    files = {}
    for name, value in arrays.items():
        if not isinstance(value, np.ndarray) or value.dtype.hasobject:
            raise ValueError('typed non-object output arrays required: ' + name)
        if not isinstance(name,str) or not name or '/' in name or '\\' in name:
            raise ValueError('output layer name must be a simple field name')
        path = root / (name + '.npy')
        _bound_path(root, name+'.npy')
        np.save(path, value, allow_pickle=False)
        files[name] = dict(file=path.name, sha256=_digest(path), dtype=str(value.dtype), shape=list(value.shape))
    metadata = deepcopy(result['metadata'])
    metadata.pop('cpu_seconds', None)
    metadata['config'] = {k: v for k, v in metadata['config'].items() if k not in ('pause_after_round', 'wallclock_budget_seconds')}
    history_files = {}
    history = result.get('geology_history')
    if history is not None:
        history_path = root / 'geology-history.npz'
        np.savez(history_path, **history['arrays'])
        _json(root / 'geology-history.json', history['metadata'])
        history_files = {name: _digest(root / name) for name in ('geology-history.npz', 'geology-history.json')}
    manifest = dict(metadata=metadata, arrays=files, details=result['details'], status='published-coarse',
                    history_files=history_files,
                    identity=identity(arrays, metadata), performance=dict(cpu_seconds=float(seconds),
                    output_bytes=sum(p.stat().st_size for p in root.iterdir() if p.is_file())))
    manifest['performance'].update(result.get('performance',{}))
    manifest['detail_files']={p.relative_to(root).as_posix():_digest(p) for p in root.glob('detail-*/*') if p.is_file()}
    manifest['manifest_identity'] = _record_identity(manifest)
    _json(root / 'manifest.json', manifest)
    return manifest


def resume(checkpoint, out_dir=None, *, config=None):
    path = Path(checkpoint)
    root = path.parent
    if out_dir is not None and Path(out_dir).resolve() != root.resolve():
        raise ValueError('resume must continue the original preparation directory')
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('schema') != SCHEMA or record.get('checkpoint_identity') != _record_identity(record, ('checkpoint_identity',)):
        raise ValueError('checkpoint identity or schema mismatch')
    for file, digest in record['source_files'].items():
        if _digest(_bound_path(root, file)) != digest:
            raise ValueError('source changed after checkpoint')
    cfg = dict(record['config'])
    cfg.pop('pause_after_round', None)
    if config:
        operational = {'pause_after_round', 'wallclock_budget_seconds'}
        if set(config) - operational:
            raise ValueError('resume cannot change numerical configuration')
        cfg.update(config)
    state = None
    if record['state_file']:
        if _digest(_bound_path(root, record['state_file'])) != record['state_sha256']:
            raise ValueError('checkpoint state changed')
        with np.load(root / record['state_file'], allow_pickle=False) as bundle:
            state = {k: bundle[k] for k in bundle.files}
    return _execute_saved(_load_source(root, record['source']), root, cfg, record, state)


def query(product, fields=None, *, window=None, verify=True, expected_identity=None, expected_manifest_identity=None):
    """Read a published product only. Never compute or prepare missing data."""
    root = Path(product)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('manifest_identity') != _record_identity(manifest):
        raise ValueError('published manifest identity mismatch')
    if expected_identity is not None and manifest.get('identity') != expected_identity:
        raise ValueError('published product differs from expected identity')
    if expected_manifest_identity is not None and manifest['manifest_identity']!=expected_manifest_identity:
        raise ValueError('published manifest differs from expected identity')
    if verify:
        for filename,digest in {**manifest.get('history_files',{}),**manifest.get('detail_files',{})}.items():
            path=(root/filename).resolve()
            if not path.is_relative_to(root.resolve()) or _digest(path)!=digest:
                raise ValueError('published history/detail file SHA mismatch')
    requested = manifest['arrays'] if fields is None else fields
    arrays = {}
    for name in requested:
        spec = manifest['arrays'][name]
        path = _bound_path(root, spec['file'])
        if verify and _digest(path) != spec['sha256']:
            raise ValueError('published layer path or SHA mismatch')
        value = np.load(path, mmap_mode='r', allow_pickle=False)
        if list(value.shape) != spec['shape'] or str(value.dtype) != spec['dtype']:
            raise ValueError('published array header differs from manifest')
        if window is not None:
            z0, x0, z1, x1 = window
            value = value[..., z0:z1, x0:x1]
        arrays[name] = value
    return dict(arrays=arrays, metadata=manifest['metadata'], details=manifest['details'], identity=manifest['identity'])


def continue_details(product, out_dir, *, terrain_entries=(), config=None, plate_identity=None):
    """Run prepared native tasks serially and publish an immutable new version.

    Missing TD stays pending; this function never starts GPU inference. An author
    orchestrator may explicitly prepare the missing tiles and call it again.
    Preview and raw TD are retained. A completed boundary is consumed once in
    this version chain; reusing it for an overlapping support is rejected.
    `plate_identity` binds native TD to the plate/skeleton when the coarse product
    only recorded a process-local source identity.
    """
    from terrain_pipeline.world_process_detail import load_native_terrain, solve_native_reach, apply_replacements
    root = Path(product)
    previous = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    current = query(root)
    if current['metadata']['config'].get('integrated_environment'):
        return continue_environment(product,out_dir,terrain_entries=terrain_entries,config=config)
    cfg = dict(config or {})
    if len(terrain_entries)>4:
        raise ValueError('first detailed batch may use at most four native TD tiles')
    terrains=[]
    for entry in terrain_entries:
        m=current['metadata']
        plate=plate_identity or m.get('plate_identity') or m['source_identity']
        terrains.append(load_native_terrain(entry,source_identity=plate,
            world_seed=m['world_seed'],island_provenance=m.get('island_provenance')))
    output=Path(out_dir)
    output.mkdir(parents=True,exist_ok=False)
    details=[]
    completed=[]
    consumed=list(previous.get('consumed_package_ids',()))
    occupied=set(previous.get('replaced_support_indices',()))
    for candidate in current['details']:
        candidate=dict(candidate)
        if candidate.get('status')=='complete':
            if 'result_file' in candidate:
                candidate['result_reference']=dict(product=str(root.resolve()),
                    manifest_identity=previous['manifest_identity'],file=candidate.pop('result_file'))
            details.append(candidate)
            continue
        x,z=candidate['location_xz_m']
        available=[]
        for terrain in terrains:
            first=terrain['grid']['first_sample_xz_m'];spacing=terrain['grid']['spacing_m'];shape=terrain['grid']['shape_zx']
            if first[0]<=x<=first[0]+(shape[1]-1)*spacing and first[1]<=z<=first[1]+(shape[0]-1)*spacing:
                available.append(terrain)
        if not available:
            candidate.update(status='pending-terrain',reason='same-source verified native TD tile not prepared')
            details.append(candidate)
            continue
        terrain=sorted(available,key=lambda value:value['identity'])[0]
        try:
            if candidate['kind']=='river_mouth':
                from terrain_pipeline.world_process_estuary import solve_native_estuary
                detail=solve_native_estuary(current,candidate,terrain,config=cfg)
            else:
                detail=solve_native_reach(current,candidate,terrain,config=cfg)
        except (ValueError,MemoryError,ImportError,ModuleNotFoundError) as exc:
            reason=str(exc)
            status='unresolved'
            if candidate['kind']=='river_mouth' and 'pending-estuary' in reason:
                status='unresolved'
            candidate.update(status=status,reason=reason)
            details.append(candidate)
            continue
        if detail['consumed_package_id'] in consumed:
            raise ValueError('boundary package already consumed by an earlier detailed version')
        if occupied.intersection(detail['support_indices'].tolist()):
            candidate.update(status='unresolved-overlap',reason='native support overlaps an already replaced region; shared solver domain required')
            details.append(candidate)
            continue
        occupied.update(detail['support_indices'].tolist())
        directory=output/('detail-'+candidate['id'])
        directory.mkdir()
        native=detail.pop('native_arrays')
        hydraulic=detail.pop('hydraulic');sediment=detail.pop('sediment')
        for name,bundle in (('native',dict(arrays=native,metadata={})),('hydraulic',hydraulic),('sediment',sediment)):
            np.savez(directory/(name+'.npz'),**bundle['arrays'])
            _json(directory/(name+'.json'),bundle['metadata'])
        detail['support_indices']=detail['support_indices'].tolist()
        detail['replacement_arrays']={key:value.tolist() for key,value in detail['replacement_arrays'].items()}
        _json(directory/'result.json',detail)
        completed.append(detail)
        candidate.update(status='complete',reason='native TD detailed water/sediment event solved',
            terrain_identity=terrain['identity'],boundary_package_id=detail['consumed_package_id'],
            result_file=directory.name+'/result.json',budgets=detail['budgets'])
        if detail.get('metadata', {}).get('completed_scope'):
            candidate['completed_scope'] = detail['metadata']['completed_scope']
            candidate['reason'] = 'declared representative closed short event complete; full downstream and seasonal lake equilibrium unresolved'
        details.append(candidate)
    arrays,consumed=apply_replacements(current['arrays'],completed,consumed_package_ids=consumed)
    metadata=deepcopy(current['metadata'])
    history=None
    if previous.get('history_files'):
        with np.load(root/'geology-history.npz',allow_pickle=False) as saved:
            history=dict(arrays={name:saved[name] for name in saved.files},
                metadata=json.loads((root/'geology-history.json').read_text(encoding='utf-8')))
    if completed:
        _refresh_detail_world(arrays,metadata,history,current['arrays'])
        _replace_solid_budget(arrays,metadata,completed)
    metadata['parent_product_identity']=current['identity']
    metadata['stages']['detailed']='complete' if all(row['status']=='complete' for row in details) else 'partial-or-pending'
    metadata['detail_semantics']='native representative events replace matching time/area support; final topology and seasonal water rerouted; generation and detailed-event inventories reported separately'
    metadata['detailed_event_budgets']=list(metadata.get('detailed_event_budgets',[]))+[dict(region_id=row['region_id'],**row['budgets']) for row in completed]
    manifest=_publish_product(dict(arrays=arrays,metadata=metadata,details=details,geology_history=history),output,0.)
    manifest.update(parent_product_identity=current['identity'],consumed_package_ids=consumed,
        replaced_support_indices=sorted(occupied),
        detailed_regions=[row['id'] for row in details if row['status']=='complete'],
        pending_regions=[row['id'] for row in details if row['status']!='complete'])
    manifest['manifest_identity']=_record_identity(manifest)
    _json(output/'manifest.json',manifest)
    return manifest


def continue_environment(product, out_dir, *, terrain_entries=(), config=None):
    """Advance one real annual interval from the complete published owners.

    Bed/forcing rebases are explicit and retain all arrays and scalar controls.
    Previous native soil exports are consumed at this next real daily interval.
    No geological shaping, historical snow preparation or initial stock repeats.
    """
    from terrain_pipeline import world_environment_native as native
    from terrain_pipeline.world_environment_world import (
        unpack_state, pack_state, rebase_seasonal, advance_native_world)
    from terrain_pipeline.common_infra import json_sha256
    current=query(product)
    metadata=deepcopy(current['metadata'])
    if not metadata['config'].get('integrated_environment'):
        raise ValueError('legacy products retain the legacy continuation path')
    cfg=dict(metadata['config'])
    if config:
        if set(config)-{'output_years'}:
            raise ValueError('annual continuation cannot change physical configuration')
        cfg.update(config)
    cfg['spinup_years']=0
    arrays=dict(current['arrays'])
    shape=np.asarray(arrays['elevation_m']).shape
    bed=np.asarray(arrays['elevation_m']).copy()
    ocean=np.asarray(arrays['ocean_mask'],bool)
    lagoon=np.asarray(arrays['lagoon_mask'],bool)
    protected=np.asarray(arrays['protected_mask'],bool)
    mesh=SimpleNamespace(**{name:np.asarray(arrays['routing_mesh_'+name]) for name in
        ('node_x_m','node_z_m','indptr','indices','edge_length_m')},shape=shape,spacing_m=metadata['spacing_m'])
    route=hydro.routing(bed,ocean,lagoon,mesh)
    lakes=np.asarray(arrays['lake_id'])
    materials={name:np.asarray(arrays[name]) for name in ('porosity','erodibility','permeability_m2','bed_hardness',
        'bank_hardness','soil_thickness_m','solubility','fracture_density','rock_index') if name in arrays}
    climate={name:np.asarray(arrays[name])[:12].copy() if name.startswith('monthly_') else np.asarray(arrays[name]).copy()
        for name in ('monthly_temperature_c','monthly_precipitation_mm','wind_x_m_s','wind_z_m_s','orographic_lift','orographic_shelter') if name in arrays}
    source=dict(metadata,elevation_m=bed,ocean_mask=ocean,lagoon_mask=lagoon,protected_mask=protected,
        parent_terrain_revision=array_sha256(bed),rock_reserve_m=np.maximum(
            cfg['rock_reserve_m']-np.asarray(arrays['rock_removed_m3'])/metadata['spacing_m']**2,0.))
    previous_lakes=np.asarray(arrays['final_lake_storage_m3']).copy()
    prepared=unpack_state(metadata['native_environment']['prepared_record'],arrays)
    if terrain_entries:
        source['authorized_river_detail_global_ids']=[candidate['node'] for candidate in prepared['candidates']
            if candidate['kind']=='coast']
        from terrain_pipeline.world_process_detail import load_native_terrain
        terrains=[load_native_terrain(entry,source_identity=metadata['plate_identity'],world_seed=metadata['world_seed'],
            island_provenance=metadata.get('island_provenance')) for entry in terrain_entries]
        if any(terrain['manifest'].get('generator',{}).get('kind')!='terragenesis-gpu' for terrain in terrains):
            raise ValueError('native continuation requires exact same-source model TD')
        by_id={region['id'] for region in prepared['plans']}
        # Admission resolves only the saved candidate list. It does not reselect
        # easier terrain or create another historical snow preparation owner.
        for candidate in prepared['candidates']:
            if candidate['id'] in by_id:
                continue
            terrain=native._native_for(candidate,terrains)
            if terrain is None:
                continue
            region=native._native_region(source,candidate,terrain,prepared['metadata']['config'])
            nodes=np.asarray(region['coarse_nodes'])
            if region['kind']=='glacier':
                area_native=region['geometry']['cell_area_m2']
                region['snow_transfer_request']=dict(water_m3_by_cell=np.asarray(prepared['snow_history']['snow_swe_mm']).ravel()[nodes]*area_native/1000.)
                from terrain_pipeline.world_environment_coupling import prepare_snow_history
                historical=prepared['historical_climate']
                unique,inverse=np.unique(nodes,return_inverse=True)
                replay=prepare_snow_history(np.asarray(historical['monthly_temperature_c']).reshape(12,-1)[:,unique][:,None,:],
                    np.asarray(historical['monthly_precipitation_mm']).reshape(12,-1)[:,unique][:,None,:],
                    spacing_m=metadata['spacing_m'],ocean_mask=np.zeros((1,len(unique)),bool),
                    support_ids=np.arange(len(unique)),years=prepared['snow_history']['years'])
                region['snow_history']=dict(time_edges_s=replay['time_edges_s'],
                    climate_identity=prepared['snow_history']['climate_identity'],
                    **{name:value[:,inverse] for name,value in replay['history'].items()})
                core=None
            else:
                from terrain_pipeline.environment_processes import initialize_coastal_exchange
                core=initialize_coastal_exchange(region['context'],mobile_thickness_m=0.,
                    sea_level_m=prepared['metadata']['config']['mean_sea_level_m'],
                    ocean_salinity_kg_m3=prepared['metadata']['config']['ocean_salinity_kg_m3'])
            clock=float(metadata['environment']['integrated_control']['elapsed_s'])
            prepared['plans'].append(region)
            prepared['state'][region['id']]=dict(core=core,physical_time_s=clock,consumed_packet_ids=[],
                accepted_packet_ids=[],refused_packets=[],pending_packets=[],initial_stock_pending=True)
            if core is not None:
                core['time_s'][:]=clock
            prepared['statuses'][region['id']]=dict(status='prepared',kind=region['kind'],candidate_plan='saved frozen plan')
    state=unpack_state(metadata['environment']['state_record'],arrays)
    seasonal=dict(arrays={},state=state,metadata=deepcopy(metadata['environment']))
    old_binding=seasonal['metadata']['state_binding']
    # Actual native terminal sea temperature changes the next coastal forcing.
    from scipy.ndimage import distance_transform_edt
    sea=np.full(shape,np.nan)
    anomaly=np.zeros(shape)
    for region in prepared['plans']:
        if region['kind']!='basin':
            continue
        stock=prepared['state'][region['id']]
        volume=stock['volume_m3']
        temperature=np.divide(stock['sensible_heat_j'],4e6*volume,out=np.full_like(volume,np.nan),where=volume>0)
        nodes=region['coarse_nodes']
        sea.ravel()[nodes]=temperature.ravel()
        anomaly.ravel()[nodes]=np.nan_to_num(temperature-prepared['metadata']['config']['initial_sea_temperature_c']).ravel()
    feedback=np.zeros(shape)
    if np.isfinite(sea).any():
        distance,indices=distance_transform_edt(~np.isfinite(sea),return_indices=True)
        feedback=anomaly[tuple(indices)]*np.exp(-distance*metadata['spacing_m']/32000.)
        feedback[distance*metadata['spacing_m']>64000.]=0.
    climate['monthly_temperature_c']+=feedback[None]-np.asarray(arrays.get('sea_air_temperature_feedback_c',np.zeros(shape)))[None]
    incoming=[]
    target_revision=array_sha256(bed)
    for region in prepared['plans']:
        stock=prepared['state'][region['id']]
        retained=[]
        for original in stock.get('pending_packets',[]):
            if original['owner_to']!='seasonal-soil':
                retained.append(original)
                continue
            if original['source_identity']!=source['source_identity']:
                raise ValueError('native return source identity differs')
            packet=deepcopy(original)
            packet.pop('id')
            packet.update(parent_terrain_revision=target_revision,
                parent_packet_id=original['id'],source_debit=dict(status='debited',account_id='native-return/'+original['id']))
            packet['id']=json_sha256(packet)
            incoming.append(packet)
            stock.setdefault('transferred_soil_packet_ids',[]).append(original['id'])
        stock['pending_packets']=retained
    cfg=deepcopy(cfg)
    cfg['environment']=dict(cfg.get('environment',{}),native_exchange=incoming)
    # Previously scheduled events remain in state. Re-supplying old manifests
    # with a new world binding would incorrectly mutate their identities.
    cfg['environment'].pop('dated_events',None)
    rebase_seasonal(seasonal,source,materials,climate,cfg)
    seasonal=_seasons(source,bed,route,lakes,materials,cfg,climate,seasonal['state'])
    arrays.update(seasonal['arrays'])
    arrays['sea_temperature_c']=sea
    arrays['sea_air_temperature_feedback_c']=feedback
    # Apply only this invocation's actual weathering and heave once.
    weather=np.asarray(arrays['monthly_weathered_rock_m']).sum(axis=0)*metadata['spacing_m']**2
    weather=np.where(protected,0.,np.minimum(weather,source['rock_reserve_m']*metadata['spacing_m']**2))
    from terrain_pipeline.soil_water import normalize_parameters
    fraction=normalize_parameters(cfg.get('weathering_parameters'))['dissolved_fraction_of_solid']['value']
    regolith=weather*(1.-fraction)
    arrays['loose_solid_m3']=np.asarray(arrays['loose_solid_m3']).copy()+regolith
    arrays['rock_removed_m3']=np.asarray(arrays['rock_removed_m3']).copy()+weather
    arrays['environment_dissolved_solid_m3']=np.asarray(arrays['environment_dissolved_solid_m3']).copy()+weather*fraction
    arrays['mobile_solid_m3']=np.asarray(arrays['mobile_solid_m3']).copy()
    porosity=np.asarray(arrays.get('porosity',np.full(shape,.35)))
    bed+=regolith/(metadata['spacing_m']**2*(1-porosity))-weather/metadata['spacing_m']**2
    bed+=np.where(protected,0.,arrays['environment_proposed_height_change_m'])
    arrays['elevation_m']=bed
    seasonal['metadata']['environment_bed_commit'].update(status='committed',committed_once=True)
    route=hydro.routing(bed,ocean,lagoon,mesh)
    labels,_=drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
    lakes=np.where((ocean|lagoon).ravel(),0,labels+1).reshape(shape).astype(np.int32)
    monthly,surface,water=_seasonal_lake_routing(
        seasonal,route,lakes,bed,ocean,lagoon,metadata['spacing_m'],previous_lakes)
    arrays.update(receiver=route.receiver.reshape(shape),order=route.order,lake_id=lakes,
        monthly_routed_volume_m3=monthly,water_surface_m=surface.reshape(shape))
    prepared['metadata']['parent_terrain_revision']=array_sha256(bed)
    source.update(elevation_m=bed,parent_terrain_revision=array_sha256(bed))
    prepared,native_result,inbound=advance_native_world(source,prepared,{'state':{}},arrays,seasonal,cfg,continuation=True)
    bed=np.asarray(arrays['elevation_m'])
    source['elevation_m']=bed
    rebase_seasonal(seasonal,source,materials,climate,cfg)
    arrays.update(seasonal['arrays'])
    route=hydro.routing(bed,ocean,lagoon,mesh)
    labels,_=drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
    lakes=np.where((ocean|lagoon).ravel(),0,labels+1).reshape(shape).astype(np.int32)
    monthly,surface,water=_post_native_lakes(
        seasonal,arrays,route,lakes,bed,ocean,lagoon,metadata['spacing_m'],monthly,water)
    seconds=np.tile(np.asarray(MONTH_DAYS)*86400.,cfg['output_years'])
    arrays.update(receiver=route.receiver.reshape(shape),order=route.order,lake_id=lakes,monthly_routed_volume_m3=monthly,
        monthly_discharge_m3_s=monthly/seconds[:,None,None],water_surface_m=surface.reshape(shape),
        discharge_m3_s=monthly.sum(axis=0)/(365.*86400.*cfg['output_years']),
        drainage_area_m2=drainage.accumulate_graph(route.receiver,route.order,np.full(shape,metadata['spacing_m']**2)))
    arrays['final_lake_storage_m3']=seasonal['arrays']['final_lake_storage_m3']
    arrays['initial_lake_storage_m3']=seasonal['arrays']['initial_lake_storage_m3']
    metadata.update(environment=seasonal['metadata'],water_budget=water,parent_product_identity=current['identity'],
        continuation=dict(kind='annual-integrated-environment',parent_binding=old_binding,
            next_binding=seasonal['metadata']['state_binding'],incoming_native_packet_ids=[packet['id'] for packet in incoming],
            interval_end_s=seasonal['state']['integrated']['elapsed_s']),config=cfg)
    metadata['native_environment']=dict(metadata=native_result['metadata'],statuses=native_result['statuses'],
        candidates=prepared['candidates'],inbound_packets=inbound,ledger=native_result['ledger'],
        result_record=pack_state(native_result,arrays,'native_result'),prepared_record=pack_state(prepared,arrays,'native_prepared'))
    metadata['environment']['processes'].update({key:native_result['statuses'][key] for key in ('glacier','coastal_exchange','basin_water_heat')})
    if native_result['statuses']['basin_water_heat']['status']=='computed':
        metadata['environment']['processes']['basin_water_heat']=dict(status='computed',actual_consumer='next annual coastal air-temperature forcing',prior_or_previous_interval=True)
    metadata['stages']['environment']=_environment_stage(metadata['generation_environment'],metadata['environment'])
    metadata['stages']['detailed']='partial-or-pending'
    solid=metadata['solid_budget']
    solid.update(final_loose_solid_m3=float(arrays['loose_solid_m3'].sum()),rock_removed_m3=float(arrays['rock_removed_m3'].sum()),
        dissolved_solid_m3=float(arrays['environment_dissolved_solid_m3'].sum()),final_mobile_solid_m3=float(arrays['mobile_solid_m3'].sum()),
        marine_received_solid_m3=float(arrays['marine_received_solid_m3'].sum()))
    solid['final_native_coast_solid_m3']=sum(float(np.sum(stock['core']['bed_solid_m3'])) for rid,stock in prepared['state'].items()
        if rid!='_exchange' and isinstance(stock.get('core'),dict) and 'bed_solid_m3' in stock['core'])
    solid['final_bedrock_reserve_m3']=solid['initial_bedrock_reserve_m3']-solid['rock_removed_m3']
    solid['residual_m3']=solid['initial_loose_solid_m3']+solid['rock_removed_m3']-sum(solid.get(key,0.) for key in
        ('final_loose_solid_m3','final_mobile_solid_m3','marine_received_solid_m3','external_dependency_solid_m3',
         'final_airborne_solid_m3','dissolved_solid_m3','final_native_coast_solid_m3'))
    metadata,observed=_content_metadata(metadata)
    details=deepcopy(current['details'])
    result=dict(arrays=arrays,metadata=metadata,details=details,performance=dict(observed_costs=observed))
    root=Path(product)
    if (root/'geology-history.npz').exists():
        with np.load(root/'geology-history.npz',allow_pickle=False) as bundle:
            result['geology_history']=dict(arrays={name:bundle[name] for name in bundle.files},
                metadata=json.loads((root/'geology-history.json').read_text(encoding='utf8')))
    manifest=save_product(result,out_dir)
    manifest['parent_product_identity']=current['identity']
    manifest['manifest_identity']=_record_identity(manifest)
    _json(Path(out_dir)/'manifest.json',manifest)
    return manifest


def _refresh_detail_world(arrays, metadata, history, previous_arrays):
    """Rebuild published derived fields after replacement, without new shaping."""
    bed=np.asarray(arrays['elevation_m'])
    shape=bed.shape
    spacing=float(metadata['spacing_m'])
    old_ocean=np.asarray(arrays.get('ocean_mask',bed<0),bool)
    lagoon=np.asarray(arrays.get('lagoon_mask',np.zeros(shape,bool)),bool)
    # Estuary morphology can change coast only on the replaced support. Retain
    # declared submerged islands/lagoon semantics elsewhere.
    wet=(bed<0)&~lagoon
    ocean_seeds=np.zeros(shape,bool)
    ocean_seeds[[0,-1],:]=wet[[0,-1],:]
    ocean_seeds[:,[0,-1]]=wet[:,[0,-1]]
    ocean=binary_propagation(ocean_seeds,mask=wet)
    mesh_names=('node_x_m','node_z_m','indptr','indices','edge_length_m')
    if all('routing_mesh_'+name in arrays for name in mesh_names):
        mesh=SimpleNamespace(**{name:np.asarray(arrays['routing_mesh_'+name]) for name in mesh_names},shape=shape,spacing_m=spacing)
    else:
        mesh=drainage.grid_mesh(shape,x0_m=metadata['first_xz_m'][0],z0_m=metadata['first_xz_m'][1],dx_m=spacing,world_seed=int(metadata['world_seed']))
    route=hydro.routing(bed,ocean,lagoon,mesh)
    labels,_=drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
    lakes=np.where((ocean|lagoon).ravel(),0,labels+1).reshape(shape).astype(np.int32)
    materials={name:np.asarray(arrays[name]) for name in ('porosity','erodibility','permeability_m2','bed_hardness','bank_hardness','soil_thickness_m','solubility','fracture_density') if name in arrays}
    if history is not None:
        from terrain_pipeline.world_geology import sample_materials
        x,z=np.meshgrid(metadata['first_xz_m'][0]+np.arange(shape[1])*spacing,metadata['first_xz_m'][1]+np.arange(shape[0])*spacing)
        materials=sample_materials(history,x,z,bed-np.asarray(arrays.get('geological_column_offset_m',np.zeros(shape))))
    source=dict(metadata,elevation_m=bed,ocean_mask=ocean)
    cfg=_config(metadata['config'])
    climate=None
    if 'monthly_temperature_c' in arrays and 'monthly_precipitation_mm' in arrays:
        climate={name:np.asarray(arrays[name])[:12] for name in ('monthly_temperature_c','monthly_precipitation_mm')}
        climate.update({name:np.asarray(arrays[name]) for name in ('wind_x_m_s','wind_z_m_s') if name in arrays})
    seasonal=_seasons(source,bed,route,lakes,materials,cfg,climate)
    arrays.update(seasonal['arrays'])
    monthly,surface,water=_seasonal_lake_routing(seasonal,route,lakes,bed,ocean,lagoon,spacing)
    flow=monthly.sum(axis=0).ravel()
    arrays.update(receiver=route.receiver.reshape(shape),order=route.order,lake_id=lakes,ocean_mask=ocean,
        drainage_area_m2=drainage.accumulate_graph(route.receiver,route.order,np.full(shape,spacing**2)),
        monthly_routed_volume_m3=np.asarray(monthly),discharge_m3_s=flow.reshape(shape)/(365.*86400.*cfg['output_years']),water_surface_m=surface.reshape(shape))
    monthly_seconds=np.tile(np.asarray(MONTH_DAYS,np.float64)*86400.,cfg['output_years'])
    arrays['monthly_discharge_m3_s']=monthly/monthly_seconds[:,None,None]
    for name,value in materials.items():
        if isinstance(value,np.ndarray) and value.shape==shape:
            arrays[name]=value
    metadata.setdefault('coarse_preview_water_budget',metadata.get('water_budget'))
    metadata['water_budget']=water
    metadata['environment']=seasonal['metadata']
    metadata.setdefault('stages', {})['environment'] = _environment_stage(
        metadata.get('generation_environment', {}), seasonal['metadata'])
    metadata['topology_refresh']=dict(status='complete',source='replaced final bed; existing irregular graph routing',
        land_area_m2=float((~ocean).sum()*spacing**2),ocean_area_m2=float(ocean.sum()*spacing**2),
        changed_land_cells=int(np.count_nonzero(ocean!=old_ocean)),
        seasonal_semantics='output rerun after bed replacement; diagnostic weathering is not applied again')
    metadata['published_solid_inventory']={name:float(np.asarray(arrays[name]).sum()) for name in
        ('loose_solid_m3','mobile_solid_m3','rock_removed_m3','marine_received_solid_m3','external_dependency_solid_m3') if name in arrays}
    metadata['replacement_inventory_change']={name:float(np.asarray(arrays[name]).sum()-np.asarray(previous_arrays[name]).sum()) for name in
        ('loose_solid_m3','mobile_solid_m3','rock_removed_m3','marine_received_solid_m3','external_dependency_solid_m3') if name in arrays and name in previous_arrays}


def _replace_solid_budget(arrays,metadata,completed):
    """Reverse coarse support transfers, then account each detailed event once."""
    old=metadata.get('solid_budget')
    if old is None:
        metadata['detailed_solid_budget_status']='no declared coarse initial ledger; event budgets only'
        return
    metadata.setdefault('coarse_preview_solid_budget',deepcopy(old))
    solid=deepcopy(old)
    fields=dict(final_loose_solid_m3='loose_solid_m3',final_mobile_solid_m3='mobile_solid_m3',
        rock_removed_m3='rock_removed_m3',marine_received_solid_m3='marine_received_solid_m3',
        external_dependency_solid_m3='external_dependency_solid_m3')
    for key,name in fields.items():
        if name in arrays:
            solid[key]=float(np.asarray(arrays[name]).sum())
    input_solid=solid.get('detailed_boundary_input_solid_m3',0.)
    output_solid=solid.get('detailed_boundary_output_solid_m3',0.)
    reversal=solid.get('coarse_support_transfer_reversal_solid_m3',0.)
    for detail in completed:
        accounting=detail.get('replacement_accounting')
        if accounting is None:
            raise ValueError('detailed replacement requires explicit coarse transfer reversal accounting')
        reversal+=accounting['coarse_support_transfer_reversal_solid_m3']
        input_solid+=detail['budgets']['solver_external_solid_m3']
        output_solid+=detail['budgets']['exported_solid_m3']
    solid.update(detailed_boundary_input_solid_m3=input_solid,detailed_boundary_output_solid_m3=output_solid,
        coarse_support_transfer_reversal_solid_m3=reversal,
        replacement_semantics='separate representative intervals; signed coarse support transfer reversed; detail boundary input/output never relabelled as ocean export')
    solid['residual_m3']=(solid['initial_loose_solid_m3']+solid['rock_removed_m3']+input_solid+reversal-
        sum(solid.get(name,0.) for name in ('final_loose_solid_m3','final_mobile_solid_m3','marine_received_solid_m3',
            'external_dependency_solid_m3','final_airborne_solid_m3','dissolved_solid_m3'))-output_solid)
    if 'initial_bedrock_reserve_m3' in solid:
        solid['final_bedrock_reserve_m3']=solid['initial_bedrock_reserve_m3']-solid['rock_removed_m3']
    metadata['solid_budget']=solid
