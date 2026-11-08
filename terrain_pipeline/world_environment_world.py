"""Single-use world inventory coupling for weathering, wind and slope transport.

These fixed representative generation events are separate from seasonal water
time. Spatial blocks own donors; their one-cell wind halos and explicit receiver
targets receive contributions exactly once, independent of block boundaries.
"""
from __future__ import annotations

from copy import deepcopy

import numpy as np

from terrain_pipeline import environment_processes as kernels
from terrain_pipeline.common_infra import identity, json_sha256
from terrain_pipeline.soil_water import normalize_parameters


def pack_state(record, arrays, prefix='environment_state'):
    """Preserve complete nested owners, arrays, clocks, events and packet IDs."""
    def encode(value, path):
        if isinstance(value, np.ndarray):
            name = prefix + '__' + '__'.join(path)
            if value.dtype.hasobject:
                raise ValueError('object state arrays cannot be published')
            arrays[name] = value
            return {'state_array': name}
        if isinstance(value, dict):
            return {key: encode(item, path+[key]) for key,item in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(item, path+[str(i)]) for i,item in enumerate(value)]
        return value.item() if isinstance(value,np.generic) else value
    return encode(record, [])


def unpack_state(record, arrays):
    def decode(value):
        if isinstance(value, dict):
            if set(value) == {'state_array'}:
                return np.asarray(arrays[value['state_array']]).copy()
            return {key:decode(item) for key,item in value.items()}
        if isinstance(value,list):
            return [decode(item) for item in value]
        return value
    return decode(record)


def persist_seasonal(seasonal):
    """Publish independently auditable final stocks and restart state together."""
    from terrain_pipeline.world_environment_state import flatten_arrays
    arrays,metadata,state = seasonal['arrays'],seasonal['metadata'],seasonal['state']
    arrays.update({'final_owner__'+key.replace('/','__'):value
                   for key,value in flatten_arrays(state['integrated']).items()})
    metadata['state_record'] = pack_state(state,arrays)
    return seasonal


def rebase_seasonal(seasonal, source, materials, climate, config):
    """Explicit terrain/forcing revision transaction; preserve every owner."""
    from terrain_pipeline.common_infra import array_sha256
    from terrain_pipeline.world_environment_state import binding
    state,metadata=seasonal['state'],seasonal['metadata']
    old=metadata['state_binding']
    if state['integrated']['binding']!=old:
        raise ValueError('saved seasonal state binding differs before rebase')
    cfg=deepcopy(config)
    cfg['environment']=dict(cfg.get('environment',{}),source_identity=source['source_identity'],
        terrain_revision=array_sha256(source['elevation_m']))
    new=binding(source['elevation_m'],np.asarray(source['ocean_mask'],bool),materials,
        climate.get('arrays',climate),cfg,source['world_seed'],source['first_xz_m'],source['spacing_m'])
    state['integrated']['binding']=new
    metadata['state_binding']=new
    metadata['state_rebase']=dict(parent_binding=old,binding=new,
        terrain_revision=cfg['environment']['terrain_revision'],ownership='all inventories, clocks, events and queues retained without initialization')
    metadata.setdefault('solver_identity_before_publication',metadata.pop('identity',None))
    persist_seasonal(seasonal)
    return seasonal


def sea_climate_preparation(source, bed, climate, config):
    """One finite prior sea scenario whose real temperature drives coastal air.

    This is a declared prior interval, with its own native water/energy stocks;
    it consumes no present seasonal runoff and changes no precipitation supply.
    """
    from scipy.ndimage import distance_transform_edt
    from terrain_pipeline import world_environment_native as native
    ca = climate.get('arrays', climate)
    base = dict(source,elevation_m=bed,parent_terrain_revision=identity({'bed_m':bed},{}),
                plate_identity=source.get('plate_identity',source['source_identity']))
    base.pop('climate',None)
    cfg = dict(config.get('native_environment',{}),max_glaciers=0,max_coasts=0)
    prepared = native.prepare(base,config=cfg)
    seconds = float(config.get('basin_preparation_seconds',86400.))
    quantum = prepared['metadata']['config']['time_quantum_s']
    if not np.isfinite(seconds) or seconds <= 0 or seconds % quantum:
        raise ValueError('finite canonical prior sea duration required')
    drivers = {}
    air = np.asarray(ca['monthly_temperature_c'])[:12].mean(axis=0)
    for region in prepared['plans']:
        nodes = region['coarse_nodes']
        wet = region['wet_mask']
        wx = np.asarray(ca.get('wind_x_m_s',np.zeros(bed.shape))).ravel()[nodes]
        wz = np.asarray(ca.get('wind_z_m_s',np.zeros(bed.shape))).ravel()[nodes]
        drivers[region['id']] = dict(wind_xz_m_s=[float(wx.mean()),float(wz.mean())],
            surface_heat_w_m2=8.*(air.ravel()[nodes].reshape(wet.shape)-cfg.get('initial_sea_temperature_c',10.)))
    result = native.advance(prepared,None,dict(regions=drivers),time_edges_s=[0.,seconds])
    temperature = np.full(bed.shape,np.nan)
    anomaly = np.zeros(bed.shape)
    for region in prepared['plans']:
        nodes = region['coarse_nodes']
        final = result['arrays'][region['id']]['sea_temperature_c']
        temperature.ravel()[nodes] = final.ravel()
        anomaly.ravel()[nodes] = np.where(region['wet_mask'],final-cfg.get('initial_sea_temperature_c',10.),0.).ravel()
    support = np.isfinite(temperature)
    feedback = np.zeros(bed.shape)
    if support.any():
        distance,indices = distance_transform_edt(~support,return_indices=True)
        feedback = anomaly[tuple(indices)]*np.exp(-distance*source['spacing_m']/32000.)
        feedback[distance*source['spacing_m'] > 64000.] = 0.
    adjusted = {key:np.asarray(value).copy() for key,value in ca.items() if isinstance(value,np.ndarray)}
    adjusted['monthly_temperature_c'] = adjusted['monthly_temperature_c'][:12]+feedback[None]
    adjusted['monthly_precipitation_mm'] = adjusted['monthly_precipitation_mm'][:12]
    result['metadata']['actual_consumer'] = dict(name='coastal annual air-temperature forcing',
        climate_feedback='prior sea temperature anomaly attenuates over 32km, truncated64km; precipitation unchanged',
        affected_cells=int(np.count_nonzero(feedback)),max_abs_temperature_change_c=float(np.max(abs(feedback))),
        prior_interval_s=seconds,heat_flux='declared bulk exchange8 W/m2/K using generated prior annual air temperature')
    return adjusted,result,temperature,feedback


def advance_native_world(source, prepared, prior_sea, arrays, seasonal, config, *, continuation=False):
    """Debit actual parent stocks, advance an annual native stage, commit once."""
    from terrain_pipeline import world_environment_native as native
    from terrain_pipeline.world_environment_state import flatten_arrays
    area = source['spacing_m']**2
    elapsed = float(seasonal['state']['integrated']['elapsed_s'])
    duration = float(config['output_years']*365.*86400.)
    begin,end = elapsed-duration,elapsed
    packets=[]
    state=deepcopy(prepared['state'])
    source_identity=identity(flatten_arrays(seasonal['state']),dict(clock=elapsed))
    rec=np.asarray(arrays['receiver']).ravel()
    terminal=rec<0
    marine=terminal & (np.asarray(arrays['ocean_mask'])|np.asarray(arrays['lagoon_mask'])).ravel()
    routed=np.asarray(arrays['monthly_routed_volume_m3']).sum(axis=0).ravel()
    river_stock=np.where(marine,routed,0.)
    if continuation:
        river_stock += np.asarray(prepared.get('parent_owners',{}).get('routed_marine_water_remaining_m3',
            np.zeros(source['elevation_m'].shape))).ravel()
    initial_river=river_stock.copy()
    loose=np.asarray(arrays['loose_solid_m3']).copy().ravel()
    initial_loose=loose.copy()
    marine_solid=np.asarray(arrays['marine_received_solid_m3']).copy().ravel()
    initial_marine_solid=marine_solid.copy()
    snow = prepared.get('snow_history')
    snow_stock=(np.asarray(snow['snow_swe_mm'])*area/1000. if snow else np.zeros(source['elevation_m'].shape)).ravel().copy()
    if continuation:
        snow_stock=np.asarray(prepared['parent_owners']['preparation_snow_remaining_m3']).ravel().copy()
    initial_snow=snow_stock.copy()
    def make(region,process,quantity,amounts,account):
        total=float(np.sum(amounts))
        if total <= 0:
            return
        record=dict(schema=native.PACKET_SCHEMA,process=process,source_identity=source['source_identity'],
            parent_state_identity=source_identity,parent_terrain_revision=source['parent_terrain_revision'],
            support_global_ids=np.asarray(region['coarse_nodes']).ravel().tolist(),
            mapping_weights=(np.asarray(amounts).ravel()/total).tolist(),owner_from='world-'+account,
            owner_to=region['id'],interval_start_s=begin,interval_end_s=end,quantities={quantity:total},
            source_debit=dict(status='debited',account_id=account),status='in-flight',consumed_by=None)
        record['id']=json_sha256(record)
        packets.append(record)
    for region in prepared['plans']:
        rid=region['id']
        if not continuation and region['kind']=='basin' and rid in prior_sea['state']:
            # Promote the finite prior terminal stock; its saved initial snapshot
            # is a historical audit, never a second active sea owner.
            state[rid]=deepcopy(prior_sea['state'][rid])
            wet=region['wet_mask']
            state[rid]['volume_m3']=np.where(wet,state[rid]['volume_m3'],0.)
            state[rid]['sensible_heat_j']=np.where(wet,state[rid]['sensible_heat_j'],0.)
        if not continuation:
            state[rid]['physical_time_s']=begin
        elif state[rid]['physical_time_s']!=begin:
            raise ValueError('native and seasonal continuation clocks differ')
        if region['kind']=='coast' and not continuation:
            state[rid]['core']['time_s'][:]=begin
        nodes=np.asarray(region['coarse_nodes']).ravel()
        if region['kind']=='glacier' and (not continuation or state[rid]['core'] is None):
            requested=region['snow_transfer_request']['water_m3_by_cell']
            actual=np.zeros(nodes.size)
            for i,node in enumerate(nodes):
                actual[i]=min(float(requested[i]),snow_stock[node])
                snow_stock[node]-=actual[i]
            make(region,'snow_to_glacier','water_m3',actual,'historical-snow-preparation')
        elif region['kind']=='glacier':
            live=seasonal['state']['integrated']['water']['snow_swe_m'].ravel()
            actual=np.zeros(nodes.size)
            native_area=np.asarray(region['geometry']['cell_area_m2'])
            for i,node in enumerate(nodes):
                actual[i]=min(live[node]*native_area[i],live[node]*area)
                live[node]-=actual[i]/area
            make(region,'snow_to_glacier','water_m3',actual,'live-seasonal-snow')
            transferred=np.zeros(source['elevation_m'].size)
            np.add.at(transferred,nodes,actual)
            seasonal['arrays'].setdefault('cumulative_external__native_snow_transfer_m3',
                np.zeros(source['elevation_m'].shape))[:]+=transferred.reshape(source['elevation_m'].shape)
            seasonal['state']['snow_swe_mm'][:]=live.reshape(source['elevation_m'].shape)*1000.
            seasonal['arrays']['snow_swe_mm'][:]=seasonal['state']['snow_swe_mm']
            seasonal['arrays']['monthly_snow_swe_mm'][-1]=seasonal['state']['snow_swe_mm']
            account=seasonal['metadata']['independent_accounts']['water']
            account['final']-=float(actual.sum())
            account['external_output']+=float(actual.sum())
        elif region['kind']=='coast':
            context=region['context']
            active=~context['protected_mask'].ravel()
            allocation=np.zeros(nodes.size)
            coverage=np.asarray(region['mapping_weights']).ravel()
            for i,node in enumerate(nodes):
                if active[i] and (not continuation or state[rid].get('initial_stock_pending')):
                    allocation[i]=min(loose[node],initial_loose[node]*coverage[i])
                    loose[node]-=allocation[i]
            make(region,'coast_initial_solid','solid_m3',allocation,'loose-solid')
            node=int(region['node'])
            seen=set()
            while rec[node]>=0 and node not in seen:
                seen.add(node)
                node=int(rec[node])
            requested=float(routed[int(region['node'])])
            actual=min(requested,river_stock[node]) if marine[node] else 0.
            river_stock[node]-=actual
            local=np.zeros(nodes.size)
            mouth=context['river_mask'].ravel() & active
            if mouth.any():
                local[mouth]=actual/mouth.sum()
                make(region,'river_to_coast','water_m3',local,'routed-marine-water')
                delivered=marine_solid[node] if marine[node] else 0.
                marine_solid[node]-=delivered
                local_solid=np.zeros(nodes.size)
                local_solid[mouth]=delivered/mouth.sum()
                make(region,'river_to_coast','solid_m3',local_solid,'routed-marine-solid')
            elif actual:
                river_stock[node]+=actual
    before={rid:deepcopy(stock) for rid,stock in state.items() if rid!='_exchange'}
    drivers={}
    for region in prepared['plans']:
        nodes=np.asarray(region['coarse_nodes']).ravel()
        wind=[float(np.asarray(arrays.get(key,np.zeros(source['elevation_m'].shape))).ravel()[nodes].mean())
              for key in ('wind_x_m_s','wind_z_m_s')]
        drivers[region['id']]=dict(wind_xz_m_s=wind)
    result=native.advance(prepared,state,dict(packets=packets,regions=drivers),time_edges_s=[begin,end])
    for region in prepared['plans']:
        result['state'][region['id']].pop('initial_stock_pending',None)
    refused={row['id'] for row in result['refused_packets']}
    if refused:
        raise ValueError('publication native packets refused after preflight: '+str(result['refused_packets']))
    arrays['native_initial_routed_marine_water_m3']=initial_river.reshape(source['elevation_m'].shape)
    arrays['native_final_routed_marine_water_m3']=river_stock.reshape(source['elevation_m'].shape)
    arrays['native_initial_loose_owner_m3']=initial_loose.reshape(source['elevation_m'].shape)
    arrays['native_final_loose_owner_m3']=loose.reshape(source['elevation_m'].shape)
    arrays['native_initial_preparation_snow_m3']=initial_snow.reshape(source['elevation_m'].shape)
    arrays['native_final_preparation_snow_m3']=snow_stock.reshape(source['elevation_m'].shape)
    arrays['loose_solid_m3']=loose.reshape(source['elevation_m'].shape)
    arrays['native_initial_routed_marine_solid_m3']=initial_marine_solid.reshape(source['elevation_m'].shape)
    arrays['native_final_routed_marine_solid_m3']=marine_solid.reshape(source['elevation_m'].shape)
    arrays['marine_received_solid_m3']=marine_solid.reshape(source['elevation_m'].shape)
    bed_delta=np.zeros(source['elevation_m'].size)
    consumed=[]
    for commit in result['bed_commit']:
        if commit['parent_terrain_revision']!=source['parent_terrain_revision'] or commit['id'] in consumed:
            raise ValueError('bed parent revision or duplicate commit differs')
        np.add.at(bed_delta,np.asarray(commit['support_global_ids']),
                  np.asarray(commit['bed_change_m'])*np.asarray(commit['mapping_weights']))
        consumed.append(commit['id'])
    result['state']['_exchange']['pending_bed_commits']=[]
    result['state']['_exchange'].setdefault('consumed_bed_commit_ids',[]).extend(consumed)
    arrays['native_committed_bed_change_m']=bed_delta.reshape(source['elevation_m'].shape)
    arrays['elevation_m']=np.asarray(arrays['elevation_m'])+arrays['native_committed_bed_change_m']
    material_packets=[]
    glacier_runoff=np.zeros(source['elevation_m'].shape)
    for packet in result['packets_out']:
        if packet['owner_to']=='surface-route':
            local=np.zeros(source['elevation_m'].size)
            quantity='water_m3' if packet['process']=='glacier_melt_to_runoff' else 'solid_m3'
            np.add.at(local,np.asarray(packet['support_global_ids']),
                      packet['quantities'][quantity]*np.asarray(packet['mapping_weights']))
            if quantity=='water_m3':
                # Actual retained glacier liquid joins the final routed month,
                # not another synthetic discharge-times-duration source.
                arrays['monthly_runoff_m3'][-1]+=local.reshape(source['elevation_m'].shape)
                glacier_runoff+=local.reshape(source['elevation_m'].shape)
            else:
                arrays['mobile_solid_m3']+=local.reshape(source['elevation_m'].shape)
            material_packets.append(packet['id'])
    arrays['native_glacier_runoff_m3']=glacier_runoff
    for region in prepared['plans']:
        rid=region['id']
        stock=result['state'][rid]
        stock['pending_packets']=[packet for packet in stock['pending_packets'] if packet['id'] not in material_packets]
        stock.setdefault('consumed_outgoing_packet_ids',[]).extend(
            packet['id'] for packet in result['packets_out'] if packet['owner_from']==rid and packet['id'] in material_packets)
        if region['kind']=='glacier':
            removed=result['arrays'][rid]['eroded_rock_m3'].sum(axis=0)
            np.add.at(arrays['rock_removed_m3'].ravel(),np.asarray(region['coarse_nodes']),removed)
    prepared['parent_owners']=dict(preparation_snow_remaining_m3=snow_stock.reshape(source['elevation_m'].shape),
        routed_marine_water_remaining_m3=river_stock.reshape(source['elevation_m'].shape))
    prepared['state']=result['state']
    result['metadata']['publication']=dict(parent_revision=source['parent_terrain_revision'],
        consumed_bed_commit_ids=consumed,consumed_surface_route_packet_ids=material_packets,
        staged_interval=[begin,end],prior_sea_promotion='one finite prior terminal stock replaces fresh basin fill; snapshot remains historical only')
    for region in prepared['plans']:
        rid=region['id']
        for name,value in result['arrays'][rid].items():
            arrays['native__'+rid+'__'+name]=np.asarray(value).copy()
        for label,record in [('initial_owner',before[rid]),('final_owner',result['state'][rid])]:
            arrays.update({'native_'+label+'__'+rid+'__'+key.replace('/','__'):value.copy()
                for key,value in flatten_arrays(record).items()})
    glacier_regions=[region for region in prepared['plans'] if region['kind']=='glacier']
    if glacier_regions:
        volume=np.zeros(source['elevation_m'].size)
        coverage=np.zeros_like(volume)
        for region in glacier_regions:
            data=result['arrays'][region['id']]
            np.add.at(volume,region['coarse_nodes'],data['ice_final_volume_m3'])
            np.add.at(coverage,region['coarse_nodes'],region['geometry']['cell_area_m2']/area)
        arrays['glacier_ice_volume_m3']=volume.reshape(source['elevation_m'].shape)
        arrays['glacier_coverage_fraction']=coverage.reshape(source['elevation_m'].shape)
        arrays['glacier_ice_thickness_m']=(volume/area).reshape(source['elevation_m'].shape)
        arrays['glacier_ice_surface_m']=np.where(coverage.reshape(source['elevation_m'].shape)>0,
            arrays['elevation_m']+arrays['glacier_ice_thickness_m'],np.nan)
        result['metadata']['glacier_map_semantics']='coarse cell-area-averaged actual native ice volume; surface=committed coarse bed+effective thickness; native physical surface retained separately'
    coast_regions=[region for region in prepared['plans'] if region['kind']=='coast']
    if coast_regions:
        water=np.zeros(source['elevation_m'].size)
        salt=np.zeros_like(water)
        for region in coast_regions:
            core=result['state'][region['id']]['core']
            np.add.at(water,region['coarse_nodes'],core['water_m3'].ravel())
            np.add.at(salt,region['coarse_nodes'],core['salt_kg'].ravel())
        arrays['coastal_water_volume_m3']=water.reshape(source['elevation_m'].shape)
        arrays['coastal_salt_kg']=salt.reshape(source['elevation_m'].shape)
        arrays['coastal_salinity_kg_m3']=np.divide(salt,water,out=np.full_like(water,np.nan),where=water>0).reshape(source['elevation_m'].shape)
    return prepared,result,packets


def _field(value, shape, name, *, fraction=False, signed=False):
    result = np.broadcast_to(np.asarray(value, np.float64), shape).copy()
    if not np.isfinite(result).all() or (not signed and np.any(result < 0)) or (fraction and np.any(result > 1)):
        raise ValueError('invalid finite world field: ' + name)
    return result


def _wind(bed, loose, wet, cover, wind_x, wind_z, active, ocean, spacing, seconds, rows):
    shape = bed.shape
    entrained = np.zeros(shape)
    deposited = np.zeros(shape)
    airborne = np.zeros(shape)
    exported = np.zeros(shape)
    for start in range(0, shape[0], rows):
        end = min(start + rows, shape[0])
        lo, hi = max(0, start-1), min(shape[0], end+1)
        section = np.s_[lo:hi, :]
        stock = np.zeros((hi-lo, shape[1]))
        stock[start-lo:end-lo] = loose[start:end]
        context = dict(height_m=bed[section], spacing_m=spacing,
                       valid_mask=np.ones(stock.shape, bool), protected_mask=~active[section], ocean_mask=ocean[section])
        result = kernels.aeolian_step(dict(loose_solid_m3=stock, airborne_solid_m3=np.zeros_like(stock)),
            dict(wind_x_m_s=wind_x[section], wind_z_m_s=wind_z[section],
                 water_saturation=wet[section], vegetation_cover=cover[section]), context, seconds)
        flux = result['fluxes']
        entrained[section] += flux['entrained_solid_m3']
        deposited[section] += flux['deposited_solid_m3']
        airborne[section] += result['state']['airborne_solid_m3']
        exported[section] += flux['boundary_export_solid_m3']
    return loose-entrained+deposited, airborne, exported, entrained, deposited


def _slope(bed, loose, wet, cover, active, ocean, source, seconds, block, root_cohesion_pa=None):
    """Use unchanged mass kernel on disjoint donor/receiver account pairs.

    Virtual pair accounts retain actual metric endpoints and actual receivers.
    Only the donor contains stock. Receiver stocks are gathered globally once;
    this is one physical hop, not a new drainage or multi-hop routing method.
    """
    shape = bed.shape
    raw_receiver = np.asarray(source['receiver'])
    if raw_receiver.shape != shape or raw_receiver.dtype.kind not in 'iu':
        raise ValueError('matching integer world receiver required')
    rec = raw_receiver.ravel()
    mesh = source.get('mesh')
    if mesh is None:
        from terrain_pipeline.drainage import grid_mesh
        first = source['first_xz_m']
        mesh = grid_mesh(shape, x0_m=first[0], z0_m=first[1], dx_m=source['spacing_m'], world_seed=source['world_seed'])
    from terrain_pipeline.drainage import receiver_edges_valid, segments_clear
    if (tuple(mesh.shape) != shape or mesh.spacing_m != source['spacing_m'] or
            not receiver_edges_valid(rec, mesh)):
        raise ValueError('world receivers must follow the supplied actual metric mesh')
    donors = np.flatnonzero((rec >= 0) & active.ravel() & (loose.ravel() > 0))
    donors = donors[segments_clear(donors,rec[donors],active)]
    removed = np.zeros(bed.size)
    received = np.zeros(bed.size)
    marine = np.zeros(bed.size)
    for start in range(0, donors.size, block):
        cells = donors[start:start+block]
        targets = rec[cells]
        count = cells.size
        indices = np.r_[cells, targets]
        pair_shape = (2, count)
        context = dict(height_m=bed.ravel()[indices].reshape(pair_shape), spacing_m=source['spacing_m'],
            world_seed=source['world_seed'], origin_native_xz=(0,0),
            node_x_m=mesh.node_x_m[indices].reshape(pair_shape), node_z_m=mesh.node_z_m[indices].reshape(pair_shape),
            graph_edge_source=np.r_[np.arange(count), np.arange(count,2*count)],
            graph_edge_target=np.r_[np.arange(count,2*count), np.arange(count)],
            receiver=np.r_[np.arange(count,2*count),np.full(count,-1)].reshape(pair_shape),
            valid_mask=np.ones(pair_shape,bool), protected_mask=(~active.ravel()[indices]).reshape(pair_shape),
            ocean_mask=ocean.ravel()[indices].reshape(pair_shape), river_mask=np.zeros(pair_shape,bool))
        state = kernels.mass_initial_state(context, bedrock_thickness_m=0.,bed_hardness=1.,solubility=0.)
        stock = np.r_[loose.ravel()[cells],np.zeros(count)].reshape(pair_shape)
        state['hillslope_deposit_solid_m3'] = stock
        # The existing kernel's initial-total field is a ledger anchor. Here
        # its declared total is transported loose stock, never new bedrock.
        state['initial_bedrock_solid_m3'] = stock.copy()
        result = kernels.mass_step(state,dict(temperature_c=0.,moisture=wet.ravel()[indices].reshape(pair_shape),
            transport_fraction_per_s=1./86400.,repose_angle_deg=34.,
            root_cohesion_pa=(cover.ravel()[indices].reshape(pair_shape)*2000. if root_cohesion_pa is None
                else root_cohesion_pa.ravel()[indices].reshape(pair_shape))),context,seconds)
        moved = result['fluxes']['mobilized_solid_m3'].ravel()[:count]
        target_protected = ~active.ravel()[targets]
        moved[target_protected] = 0.
        removed[cells] += moved
        sea = ocean.ravel()[targets]
        np.add.at(received,targets[~sea],moved[~sea])
        np.add.at(marine,targets[sea],moved[sea])
    return (loose.ravel()-removed+received).reshape(shape),marine.reshape(shape),removed.reshape(shape)


def generation_environment(source, materials, seasonal, geological_history=None, config=None):
    """Return one proposed bed delta and finite stocks, without mutating inputs.

    ``source.loose_solid_m3`` is required. The caller applies returned stocks
    and bed change once and records this generation event separately from its
    equivalent water/sediment shaping rounds and seasonal physical water time.
    """
    cfg = dict(config or {})
    bed = np.asarray(source['elevation_m'],np.float64)
    if bed.ndim != 2 or min(bed.shape) < 1 or not np.isfinite(bed).all():
        raise ValueError('finite world bed required')
    shape = bed.shape
    spacing = float(source['spacing_m'])
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError('positive metric spacing required')
    loose = _field(source['loose_solid_m3'],shape,'loose_solid_m3')
    initial = loose.copy()
    ocean = np.asarray(source['ocean_mask'],bool)
    protected = np.asarray(source.get('protected_mask',np.zeros(shape,bool)),bool)
    if ocean.shape != shape or protected.shape != shape:
        raise ValueError('common world masks required')
    active = ~protected
    area = spacing**2
    porosity = _field(materials.get('porosity',.35),shape,'porosity',fraction=True)
    if np.any(porosity >= 1):
        raise ValueError('porosity must be below one')
    a = seasonal['arrays']
    _field(a['temperature_c'],shape,'temperature_c',signed=True)
    capacity = seasonal.get('metadata',{}).get('runoff_parameters',{}).get('soil_capacity_mm',150.)
    if not np.isfinite(capacity) or capacity <= 0:
        raise ValueError('positive declared soil capacity required')
    wet = np.clip(_field(a['soil_water_mm'],shape,'soil_water_mm') / capacity,0.,1.)
    cover = _field(a['cover_fraction'],shape,'cover_fraction',fraction=True)
    weathered_months = np.asarray(a['monthly_weathered_rock_m'],np.float64)
    if weathered_months.ndim != 3 or weathered_months.shape[1:] != shape or not np.isfinite(weathered_months).all() or np.any(weathered_months < 0):
        raise ValueError('finite nonnegative monthly weathering depths required')
    weathered = weathered_months.sum(axis=0)*area
    weathered = np.where(active & ~ocean, weathered,0.)
    requested_weathered = weathered.copy()
    if 'rock_remaining_m3' in source:
        reserve = _field(source['rock_remaining_m3'],shape,'rock_remaining_m3')
        weathered = np.minimum(weathered,reserve)
    wp = normalize_parameters(cfg.get('weathering_parameters'))
    dissolved = weathered*wp['dissolved_fraction_of_solid']['value']
    regolith = weathered-dissolved
    loose += regolith
    seconds = float(cfg.get('generation_environment_seconds',600.))
    if not np.isfinite(seconds) or not 0 < seconds <= 86400.:
        raise ValueError('bounded generation environment interval required')
    rows = cfg.get('environment_block_rows',64)
    if type(rows) is not int or rows < 1:
        raise ValueError('positive integer environment block rows required')
    rows = min(rows,max(1,262144//shape[1]-2))
    if rows <= 0 or (min(shape[0],rows+2)*shape[1] > 262144):
        raise ValueError('world row width exceeds bounded wind kernel support')
    processes = dict(weathering=dict(status='computed',source='output-year existing seasonal weathering; spinup excluded'))
    if 'wind_x_m_s' in a and 'wind_z_m_s' in a:
        wx = _field(a['wind_x_m_s'],shape,'wind_x_m_s',signed=True)
        wz = _field(a['wind_z_m_s'],shape,'wind_z_m_s',signed=True)
        loose,airborne,exported,entrained,deposited = _wind(bed,loose,wet,cover,wx,wz,active,ocean,spacing,seconds,rows)
        marine = np.where(ocean,deposited,0.)
        loose -= marine
        processes['aeolian'] = dict(status='computed',source=kernels.AEOLIAN_ALGORITHM,
            grain_provenance='declared single sand-class fraction of finite world loose stock; uncalibrated')
    else:
        airborne,exported,entrained,deposited,marine=(np.zeros(shape) for _ in range(5))
        processes['aeolian'] = dict(status='pending-input',reason='actual world wind not supplied')
    pairs = cfg.get('environment_pair_block',8192)
    if type(pairs) is not int or not 1 <= pairs <= 32768:
        raise ValueError('bounded positive receiver-pair block required')
    roots = (_field(a['root_cohesion_pa'],shape,'root_cohesion_pa')
             if cfg.get('integrated_environment') and 'root_cohesion_pa' in a else None)
    loose,mass_marine,mass_moved = _slope(bed,loose,wet,cover,active,ocean,source,seconds,pairs,roots)
    marine += mass_marine
    processes['mass_wasting'] = dict(status='computed',source=kernels.MASS_ALGORITHM,
                                     criterion='actual receiver metric slope, moisture, root cohesion and finite loose stock')
    # Geological events already built the initial geological bed. Only a new
    # explicit current event can add volcanic supply; never replay ancient lava.
    processes['volcanism'] = dict(status='not-triggered',reason='no unconsumed current eruption event; historical lava is already in geological initial bed')
    volcanic_delta = np.zeros(shape)
    volcanic_ledger = None
    volcanic_state = {}
    if source.get('current_volcanic_event') is not None:
        event = source['current_volcanic_event']
        if not event.get('event_identity') or event.get('consumed',False):
            raise ValueError('unconsumed dated current volcanic event required')
        if event.get('age_ma') != 0.:
            raise ValueError('current eruption requires explicit age_ma=0; historical events are already applied')
        historical_events = (geological_history or {}).get('metadata',{}).get('events',[])
        if any(item['id'] == event['event_identity'] for item in historical_events):
            raise ValueError('already applied geological event cannot be replayed as a current eruption')
        # Bounded eruption contexts require explicitly prepared regional stocks
        # and forcing; dispatch them through the existing checked adapter.
        from terrain_pipeline.world_environment_conditional import run_conditional_processes
        context=dict(event['context'])
        if (not np.array_equal(context['height_m'],bed) or context['spacing_m'] != spacing or
                not np.array_equal(context['receiver'],source['receiver']) or
                not np.array_equal(context['valid_mask'],np.ones(shape,bool)) or
                not np.array_equal(context['protected_mask'],protected | ocean) or
                not np.array_equal(context['ocean_mask'],ocean)):
            raise ValueError('current eruption must bind the actual bed, spacing, receivers and protected coarse coast')
        if source.get('mesh') is not None:
            context['node_x_m']=source['mesh'].node_x_m.reshape(shape)
            context['node_z_m']=source['mesh'].node_z_m.reshape(shape)
        result=run_conditional_processes(context,dict(volcanism=event),dt_s=seconds)
        if result['processes']['volcanism']['status']!='computed':
            processes['volcanism']=result['processes']['volcanism']
        else:
            eruption=result['results']['volcanism']
            volcanic_delta=eruption['fluxes']['height_change_m']
            volcanic_ledger=eruption['ledger']
            volcanic_state=eruption['state']
            processes['volcanism']=result['processes']['volcanism']
            processes['volcanism'].update(age_ma=0.,consumed=True)
    delta = (loose-initial)/(area*(1.-porosity))-weathered/area+volcanic_delta
    # Ocean receiving solids are tracked without altering protected coarse coast.
    delta = np.where(active & ~ocean,delta,0.)
    ledger=dict(initial_loose_solid_m3=float(initial.sum()),weathered_rock_m3=float(weathered.sum()),
        dissolved_solid_m3=float(dissolved.sum()),final_loose_solid_m3=float(loose.sum()),
        final_airborne_solid_m3=float(airborne.sum()),boundary_export_solid_m3=float(exported.sum()),
        marine_received_solid_m3=float(marine.sum()))
    ledger['solid_residual_m3']=(ledger['initial_loose_solid_m3']+ledger['weathered_rock_m3']-
        sum(ledger[key] for key in ('dissolved_solid_m3','final_loose_solid_m3','final_airborne_solid_m3','boundary_export_solid_m3','marine_received_solid_m3')))
    arrays=dict(height_change_m=delta,volcanic_height_change_m=volcanic_delta,
        loose_solid_m3=loose,airborne_solid_m3=airborne,
        weathered_rock_m3=weathered,dissolved_solid_m3=dissolved,boundary_export_solid_m3=exported,
        marine_received_solid_m3=marine,aeolian_entrained_solid_m3=entrained,mass_mobilized_solid_m3=mass_moved)
    arrays.update({'volcanic_'+name:value for name,value in volcanic_state.items()})
    pending=[name for name,row in processes.items() if row.get('status')=='pending-input']
    status='partial-or-pending' if pending else 'complete'
    metadata=dict(algorithm='world-finite-environment-coupling-v1',source_identity=source['source_identity'],
        status=status,pending_processes=pending,interval_s=seconds,processes=processes,solid_budget=ledger,
        volcanic_budget=volcanic_ledger,
        weathering_supply=dict(requested_rock_m3=float(requested_weathered.sum()),
            debited_rock_m3=float(weathered.sum()),
            reserve_limited_cells=int(np.count_nonzero(weathered<requested_weathered))),
        semantics='one generation event; output-year weathering debited once; donor-owned wind and receiver-pair mass transfer',
        units='inventories m3 solid; weathered rock m3 rock; bed change metres bulk using local material porosity',
        limits=['single sand class, one transport hop and uncalibrated material fractions',
                'historical volcanic material is not injected again; regional current eruptions require prepared owner',
                'groundwater, glacier and coast require explicit external geometry/drivers in seasonal preparation'])
    metadata['identity']=identity(arrays,metadata)
    return dict(arrays=arrays,metadata=metadata)
