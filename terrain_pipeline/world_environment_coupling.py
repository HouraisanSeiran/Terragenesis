"""Global finite-account seasonal coupling; no block-local worlds or outlets."""
from dataclasses import asdict
import math
import time
import numpy as np
from numba import njit

from terrain_pipeline.common_infra import identity, json_sha256
from terrain_pipeline.climate_forcing import MONTH_DAYS
from terrain_pipeline.drainage import grid_mesh, accumulate_graph, valid_edge_mask
from terrain_pipeline.runoff import RunoffParameters
from terrain_pipeline.soil_water import SnowParameters, MAX_COLUMNS, advance as advance_weathering
from terrain_pipeline.environment_processes import (frozen_ground_step, advance_soil_chemistry,
    advance_succession, advance_habitat, SUCCESSION_PARAMETERS, volcanism_step)
from terrain_pipeline.world_environment_state import (ALGORITHM, binding, initialize,
    flatten_arrays, water_total)
from terrain_pipeline.world_environment_coupling_habitat import advance_global_habitat

DAY = 86400.
LATENT_ET = 2450000000.
STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8


def thermal_scenario_parameters(config):
    """One-layer engineering radiation and root-retention scenario, not weather."""
    thermal = dict(surface_emissivity=.97,sky_emissivity=.85)
    supplied = config.get('thermal_parameters',{})
    if set(supplied)-set(thermal):
        raise ValueError('unknown integrated thermal parameter')
    thermal.update(supplied)
    for name,value in thermal.items():
        if not np.isscalar(value) or not np.isfinite(value) or not 0<=value<=1:
            raise ValueError(name+' must be a finite emissivity in [0,1]')
    soil = dict(field_capacity_fraction=.6)
    supplied_soil = config.get('soil_water_parameters',{})
    if set(supplied_soil)-set(soil):
        raise ValueError('unknown integrated soil-water parameter')
    soil.update(supplied_soil)
    value = soil['field_capacity_fraction']
    if not np.isscalar(value) or not np.isfinite(value) or not 0<=value<=1:
        raise ValueError('field_capacity_fraction must be in [0,1]')
    return thermal,soil


def longwave_exchange(soil_temperature_c,air_temperature_c,parameters,land):
    """Grey surface/sky exchange in W/m2, temperature converted to kelvin.

    Fixed sky emissivity is declared, uncalibrated engineering forcing. It does
    not infer cloud/humidity from the saved climate or solve an atmosphere.
    """
    soil_k=soil_temperature_c+273.15
    air_k=air_temperature_c+273.15
    if np.any(soil_k<=0) or np.any(air_k<=0):
        raise ValueError('longwave exchange requires temperatures above absolute zero')
    surface=parameters['surface_emissivity']
    downward=surface*parameters['sky_emissivity']*STEFAN_BOLTZMANN_W_M2_K4*air_k**4*land
    upward=surface*STEFAN_BOLTZMANN_W_M2_K4*soil_k**4*land
    return downward,upward


def inventory_totals(state, area):
    w,t,c,e = (state[k] for k in ('water','thermal','chemistry','succession'))
    total = lambda record,names:sum(float(record[k].sum()) for k in names)
    liquid_m3 = area*total(w,('root_liquid_m','fast_surface_m'))+float(w['groundwater_m3'].sum())
    return dict(water_m3=water_total(state,area),
        salt_kg=total(c,('salt_dissolved_kg','salt_solid_kg'))+float(state['groundwater_solutes']['salt_kg'].sum()),
        carbon_kg=total(c,('organic_carbon_kg',))+total(e,('biomass_carbon_kg','dead_carbon_kg','char_carbon_kg'))+
            float(state['queues']['litter_carbon_kg'].sum()),
        nutrient_kg=total(c,('nutrient_kg','organic_nutrient_kg'))+float(e['plant_nutrient_kg'].sum())+
            float(state['groundwater_solutes']['nutrient_kg'].sum()+state['queues']['plant_nutrient_return_kg'].sum()+
                  state['queues']['plant_nutrient_uptake_kg'].sum()),
        energy_j=float(t['soil_temperature_c'].sum())*area*2000000.+liquid_m3*334000000.+
            float(state.get('volcanism',{}).get('lava_heat_j',np.array(0.)).sum()),
        population_individuals=float(state['habitat']['population_individuals'].sum()),
        routed_salt_kg=float(state['routed_exports']['salt_kg'].sum()),
        routed_nutrient_kg=float(state['routed_exports']['nutrient_kg'].sum()))


def combined_accounts(initial,final,ledgers,process_ledgers,native):
    rows = ledgers['spinup']+ledgers['output']
    summed = lambda records,key:sum(float(row.get(key,0.)) for row in records)
    account = lambda name,inputs,outputs:dict(initial=initial[name],external_input=inputs,
        external_output=outputs,final=final[name],residual=initial[name]+inputs-outputs-final[name])
    water_out = sum(summed(rows,k) for k in ('actual_et_m3','sublimation_m3','local_runoff_m3'))
    chemistry,ecology,habitat = (process_ledgers[k] for k in ('chemistry','ecology','habitat'))
    volcano = process_ledgers['volcanism']
    energy_in = (sum(summed(rows,k) for k in ('absorbed_shortwave_j','longwave_downward_j','geothermal_j','air_heat_j','sublimation_atmosphere_input_j'))+
        native['sensible_heat_j']+native['latent_heat_j']+(summed(rows,'precipitation_liquid_m3')+native['water_m3'])*334000000.+summed(volcano,'event_input_lava_heat_j'))
    energy_out = (sum(summed(rows,k) for k in ('longwave_upward_j','actual_et_vaporization_j','unused_et_energy_j','sublimation_vaporization_j'))+
        (summed(rows,'actual_et_m3')+summed(rows,'local_runoff_m3'))*334000000.)
    return dict(water=account('water_m3',summed(rows,'precipitation_m3')+native['water_m3'],water_out),
        salt=account('salt_kg',native['salt_kg'],final['routed_salt_kg']-initial['routed_salt_kg']),
        carbon=account('carbon_kg',native['organic_carbon_kg']+summed(ecology,'photosynthesis_carbon_kg'),
            summed(chemistry,'respired_carbon_kg')+summed(ecology,'fire_atmosphere_carbon_kg')),
        nutrient=account('nutrient_kg',native['nutrient_kg'],final['routed_nutrient_kg']-initial['routed_nutrient_kg']),
        energy=account('energy_j',energy_in,energy_out),
        population=account('population_individuals',summed(habitat,'births_individuals'),summed(habitat,'deaths_individuals')),
        semantics='routed salt/nutrient are outputs of seasonal domain and retained in explicit export witness arrays; energy reference is liquid enthalpy 334MJ/m3 at 0C plus soil sensible heat and finite lava heat')


@njit(cache=True)
def _shadow(height, sun, spacing, max_distance):
    nz, nx = height.shape
    result = np.zeros(height.shape, np.bool_)
    horizontal = math.hypot(sun[0], sun[2])
    for row in range(nz):
        for col in range(nx):
            if sun[1] <= 0:
                result[row,col] = True
            elif horizontal > 1e-10:
                for distance in range(1, max_distance + 1):
                    rr = int(round(row + distance * sun[2] / horizontal))
                    cc = int(round(col + distance * sun[0] / horizontal))
                    if 0 <= rr < nz and 0 <= cc < nx:
                        if height[rr,cc] > height[row,col] + distance * spacing * sun[1] / horizontal + 1e-9:
                            result[row,col] = True
                            break
    return result


def radiation_month(height, spacing, month, land, *, phases=4, horizon_m=64000.):
    """Core solar/gradient/ray equations, bounded rays and declared quadrature.

    Four representative-day midpoint phases are weighted by actual month days.
    Unknown terrain beyond 64 km is not asserted to be unshadowed physically.
    """
    days = int(MONTH_DAYS[month])
    midpoint_day = float(sum(MONTH_DAYS[:month])) + days / 2
    dz = np.gradient(height, spacing, axis=0) if height.shape[0] > 1 else np.zeros_like(height)
    dx = np.gradient(height, spacing, axis=1) if height.shape[1] > 1 else np.zeros_like(height)
    absorbed = np.zeros_like(height)
    incident = np.zeros_like(height)
    for phase in range(phases):
        seconds = (math.floor(midpoint_day) + (phase + .5) / phases) * DAY
        declination = np.deg2rad(23.44) * np.sin(2 * np.pi * seconds / (DAY * 365))
        hour = 2 * np.pi * (seconds / DAY % 1 - .5)
        lat = np.deg2rad(35.)
        sun = np.array([-np.cos(declination)*np.sin(hour),
            np.sin(lat)*np.sin(declination)+np.cos(lat)*np.cos(declination)*np.cos(hour),
            np.cos(lat)*np.sin(declination)-np.sin(lat)*np.cos(declination)*np.cos(hour)])
        cosine = np.maximum(0.,(-dx*sun[0]+sun[1]-dz*sun[2])/np.sqrt(1+dx*dx+dz*dz))
        shadow = _shadow(height, sun, spacing, min(int(math.ceil(horizon_m/spacing)), int(math.ceil(math.hypot(*height.shape)))))
        flux = np.where(land & ~shadow,700.*cosine,0.) / phases
        incident += flux
        absorbed += flux * .8
    return dict(absorbed_shortwave_w_m2=absorbed, incident_w_m2=incident)


@njit(cache=True)
def _cap_face_roundoff(amounts, donors, available):
    """Commit precomputed face requests against a finite remaining donor.

    Input faces have canonical global mesh order. Ratio scaling establishes the
    simultaneous physical request; this final representable commit prevents a
    few-ulp overdraw without iterative tightening or post-hoc stock clipping.
    """
    remaining = available.copy()
    actual = amounts.copy()
    reduction = 0.
    for edge in range(amounts.size):
        donor = donors[edge]
        actual[edge] = min(amounts[edge],remaining[donor])
        remaining[donor] -= actual[edge]
        reduction += amounts[edge]-actual[edge]
    return actual,remaining,reduction


def global_groundwater(water, tracers, base, specific_yield, conductance, sources,
                       targets, area, dt_s, capacity, drainage_tau_s, face_metric=None):
    """Single shared-face request/donor-cap/scatter transaction, including tracers."""
    initial = water.copy()
    head = base.ravel() + water.ravel() / (area * specific_yield.ravel())
    difference = head[sources] - head[targets]
    donors = np.where(difference >= 0,sources,targets)
    receivers = np.where(difference >= 0,targets,sources)
    request = np.minimum(conductance.ravel()[donors],conductance.ravel()[receivers]) * np.abs(difference) * dt_s
    if face_metric is not None:
        request *= face_metric
    total = np.bincount(donors,weights=request,minlength=water.size)
    factor = np.minimum(1.,np.divide(water.ravel(),total,out=np.ones(water.size),where=total>0))
    moved = request * factor[donors]
    moved,remaining_water,roundoff_reduction = _cap_face_roundoff(moved,donors,water.ravel())
    donor_fraction = np.divide(moved,water.ravel()[donors],out=np.zeros_like(moved),where=water.ravel()[donors]>0)
    tracer_initial = {name:float(pool.sum()) for name,pool in tracers.items()}
    tracer_roundoff_reduction = {}
    for name,pool in tracers.items():
        transfer = pool.ravel()[donors] * donor_fraction
        transfer,remaining_tracer,reduction = _cap_face_roundoff(transfer,donors,pool.ravel())
        tracer_roundoff_reduction[name] = reduction
        pool[:] = (remaining_tracer+
            np.bincount(receivers,weights=transfer,minlength=water.size)).reshape(water.shape)
    water[:] = (remaining_water+
        np.bincount(receivers,weights=moved,minlength=water.size)).reshape(water.shape)
    # A declared finite aquifer-base drain, plus saturated springs; no lake
    # stage is supplied, so no fictitious bidirectional lake exchange occurs.
    spring = np.maximum(water-capacity,0.)
    baseflow = np.minimum(water,spring + (water-spring) * -np.expm1(-dt_s/drainage_tau_s))
    fraction = np.divide(baseflow,water,out=np.zeros_like(water),where=water>0)
    exports = {name:pool*fraction for name,pool in tracers.items()}
    for name,pool in tracers.items():
        pool -= exports[name]
    water -= baseflow
    return dict(baseflow_m3=baseflow, exports=exports,
        head_m=base+water/(area*specific_yield),
        water_residual_m3=float(initial.sum()-water.sum()-baseflow.sum()),
        donor_roundoff_transfer_reduction_m3=roundoff_reduction,
        tracer_roundoff_transfer_reduction_kg=tracer_roundoff_reduction,
        tracer_residual_kg={name:tracer_initial[name]-float(pool.sum())-float(exports[name].sum())
                           for name,pool in tracers.items()},
        lateral_gross_m3=float(moved.sum()))


def apply_native_packets(state, packets, expected, area, land, energy_input_map=None):
    """Consume the shared native-card schema at completed daily boundaries.

    Quantities are scalar packet totals distributed by normalized coarse mapping
    weights; repeated global IDs accumulate. Nonzero solids require a separate
    finite material owner and are rejected by this water/chemistry receiver.
    """
    totals = dict(water_m3=0.,salt_kg=0.,nutrient_kg=0.,organic_carbon_kg=0.,
                  sensible_heat_j=0.,latent_heat_j=0.)
    handoffs = state['handoffs']
    known = {p['id'] for p in handoffs['pending']} | set(handoffs['consumed_ids'])
    for packet in packets:
        if packet.get('schema')!='world-environment-exchange-v1' or packet.get('id')!=json_sha256({k:v for k,v in packet.items() if k!='id'}):
            raise ValueError('native packet identity mismatch')
        if packet.get('id') in known:
            continue
        debit = packet.get('source_debit',{})
        if (packet.get('source_identity')!=expected['source_identity'] or
            packet.get('parent_terrain_revision')!=expected['parent_terrain_revision'] or
            not packet.get('parent_state_identity') or packet.get('owner_to')!='seasonal-soil' or
            debit.get('status')!='debited' or not debit.get('account_id') or
            packet.get('status')!='in-flight' or packet.get('consumed_by') is not None):
            raise ValueError('native packet requires bound source/revision/owner and actual debit witness')
        begin,end = packet.get('interval_start_s'),packet.get('interval_end_s')
        if not np.isfinite([begin,end]).all() or begin<0 or end<begin or begin%DAY or end%DAY:
            raise ValueError('seasonal native exchange requires exact daily interval boundaries')
        quantities = packet.get('quantities',{})
        if set(quantities)-set(totals)-{'solid_m3'} or quantities.get('solid_m3',0.)!=0:
            raise ValueError('unsupported seasonal packet quantity or solid owner')
        for name,value in quantities.items():
            if not np.isscalar(value) or not np.isfinite(value) or (not name.endswith('heat_j') and value<0):
                raise ValueError('finite scalar native packet quantity required')
        ids = np.asarray(packet.get('support_global_ids'),np.int64)
        weights = np.asarray(packet.get('mapping_weights'),float)
        if (ids.ndim!=1 or np.any(ids<0) or np.any(ids>=land.size) or not np.all(land.ravel()[ids]) or
            weights.shape!=ids.shape or not np.isfinite(weights).all() or np.any(weights<0) or
            not np.isclose(weights.sum(),1.,rtol=0,atol=1e-12)):
            raise ValueError('native packet requires normalized explicit global land mapping')
        handoffs['pending'].append(dict(packet))
        known.add(packet['id'])
    pending = []
    for packet in handoffs['pending']:
        if packet['interval_end_s']>state['elapsed_s']:
            pending.append(packet)
            continue
        ids = np.asarray(packet['support_global_ids'],np.int64)
        weights = np.asarray(packet['mapping_weights'],float)
        for name in totals:
            amount = float(packet['quantities'].get(name,0.))
            values = amount*weights
            totals[name] += amount
            if energy_input_map is not None and (name=='water_m3' or name.endswith('heat_j')):
                np.add.at(energy_input_map.ravel(),ids,values*(334000000. if name=='water_m3' else 1.))
            if name=='water_m3':
                np.add.at(state['water']['fast_surface_m'].ravel(),ids,values/area)
            elif name=='salt_kg':
                np.add.at(state['chemistry']['salt_solid_kg'].ravel(),ids,values)
            elif name=='nutrient_kg':
                np.add.at(state['chemistry']['nutrient_kg'].ravel(),ids,values)
            elif name=='organic_carbon_kg':
                np.add.at(state['chemistry']['organic_carbon_kg'].ravel(),ids,values)
            elif name.endswith('heat_j'):
                # Signed sensible/latent energy enters the enthalpy account;
                # the next phase transaction restores equilibrium once.
                np.add.at(state['thermal']['soil_temperature_c'].ravel(),ids,values/(area*2000000.))
        handoffs['consumed_ids'].append(packet['id'])
    handoffs['pending'] = pending
    return totals


def advance_current_events(state, events, context, days):
    """Dated finite current-event supplies; historical age_ma>0 never replays."""
    shape = context['height_m'].shape
    fire,disturbance,heat,bed,lava_heat_input = (np.zeros(shape) for _ in range(5))
    ledgers = []
    occupied = np.zeros(shape,bool)
    scheduled = state['events'].setdefault('scheduled',{})
    event_ids = [e.get('id') for e in events]
    if len(event_ids)!=len(set(event_ids)):
        raise ValueError('dated event IDs must be unique')
    for event in events:
        if not event.get('id') or not np.isfinite(event.get('start_s',np.nan)):
            raise ValueError('dated event ID and physical start_s required')
        if event['start_s']<0 or event['start_s']%DAY:
            raise ValueError('dated event requires exact physical daily boundary')
        if event.get('source_binding')!=state['binding']:
            raise ValueError('current event source_binding must match integrated world')
        if event['id'] in scheduled and json_sha256(scheduled[event['id']])!=json_sha256(event):
            raise ValueError('dated event ID cannot change its finite supply or timing')
        scheduled[event['id']] = dict(event)
    for event in scheduled.values():
        if event.get('age_ma',0.)!=0 or event['start_s']>state['elapsed_s']:
            continue
        event_id = event['id']
        kind = event.get('kind')
        if kind not in ('volcanism','fire','disturbance'):
            raise ValueError('unsupported dated current event')
        ids = np.asarray(event.get('global_cell_ids',()),np.int64)
        if ids.ndim!=1 or np.unique(ids).size!=ids.size or np.any(ids<0) or np.any(ids>=np.prod(shape)):
            raise ValueError('current event requires unique global support')
        if kind!='volcanism':
            if event_id in state['events']['consumed_ids']:
                continue
            fraction = float(event.get('fraction',1.))
            if not 0<=fraction<1:
                raise ValueError('disturbance fraction must be in [0,1)')
            (fire if kind=='fire' else disturbance).ravel()[ids] += -np.log1p(-fraction)/(days*DAY)
            state['events']['consumed_ids'].append(event_id)
            continue
        if 'volcanism' not in state:
            state['volcanism'] = {name:np.zeros(shape) for name in
                ('mobile_lava_m3','lava_heat_j','airborne_ash_m3','deposited_lava_m3','deposited_ash_m3')}
        if not ids.size:
            continue
        # Bounded support is supplied explicitly; no independently initialized
        # tile world. Global event stocks are sliced and committed back once.
        rows,cols = np.divmod(ids,shape[1])
        r0,r1,c0,c1 = int(rows.min()),int(rows.max()+1),int(cols.min()),int(cols.max()+1)
        sub = (slice(r0,r1),slice(c0,c1))
        local_shape = (r1-r0,c1-c0)
        if np.prod(local_shape)>262144:
            raise ValueError('current volcanic support exceeds bounded kernel geometry')
        if occupied[sub].any():
            raise ValueError('overlapping volcanic support requires one aggregated dated event')
        occupied[sub] = True
        mapping = np.arange(np.prod(shape)).reshape(shape)[sub]
        reverse = {int(g):i for i,g in enumerate(mapping.ravel())}
        rec = np.asarray(context['receiver']).reshape(shape)[sub]
        local_receiver = np.array([reverse.get(int(v),-1) for v in rec.ravel()]).reshape(local_shape)
        local_context = dict(height_m=context['height_m'][sub],spacing_m=context['spacing_m'],
            receiver=local_receiver,ocean_mask=context['ocean_mask'][sub])
        forcing = dict(lava_input_m3=np.zeros(local_shape),ash_input_m3=np.zeros(local_shape))
        for name in ('wind_x_m_s','wind_z_m_s'):
            forcing[name] = np.broadcast_to(np.asarray(context.get(name,0.),float),shape)[sub]
        if event_id not in state['events']['consumed_ids']:
            for field in ('lava_input_m3','ash_input_m3'):
                value = np.broadcast_to(np.asarray(event.get(field,0.),float),ids.shape)
                if not np.isfinite(value).all() or np.any(value<0):
                    raise ValueError('finite nonnegative volcanic event inventory required')
                forcing[field].ravel()[[reverse[int(g)] for g in ids]] = value
            state['events']['consumed_ids'].append(event_id)
        old = {name:value[sub].copy() for name,value in state['volcanism'].items()}
        result = volcanism_step(old,forcing,local_context,days*DAY)
        result['ledger']['event_input_lava_heat_j'] = float(forcing['lava_input_m3'].sum())*2000000000.
        lava_heat_input[sub] += forcing['lava_input_m3']*2000000000.
        for name,value in result['state'].items():
            state['volcanism'][name][sub] = value
        heat[sub] += result['fluxes']['geothermal_heat_w_m2']
        bed[sub] += result['fluxes']['height_change_m']
        ledgers.append(result['ledger'])
    return dict(fire_hazard_s=fire,disturbance_hazard_s=disturbance,
        heat_w_m2=heat,height_change_m=bed,external_lava_heat_j=lava_heat_input,ledgers=ledgers)


def _freeze_global(state, air, ground_heat, geothermal, context, block_cells):
    """Point-local kernel blocks share the authoritative global phase stocks."""
    shape = context['height_m'].shape
    water, thermal = state['water'],state['thermal']
    stocks = dict(liquid_water_m=water['root_liquid_m'],ground_ice_m=water['ground_ice_m'],
        snow_swe_m=water['snow_swe_m'],soil_temperature_c=thermal['soil_temperature_c'],
        thaw_time_s=thermal['thaw_time_s'],frozen_time_s=thermal['frozen_time_s'])
    flux = {k:np.zeros(shape) for k in ('snow_meltwater_m','infiltration_factor','height_change_m','heat_input_j_m2')}
    ledger = dict(heat_input_j=0.,snow_latent_j=0.,energy_residual_j=0.,water_residual_m3=0.)
    # Kernel air forcing currently requires nonnegative air; use an equivalent
    # explicit heat flux and air=temp=0 so negative climate remains supported.
    for start in range(0,air.size,block_cells):
        stop = min(start+block_cells,air.size)
        sl = slice(start,stop)
        old = {k:v.ravel()[sl].reshape(1,-1).copy() for k,v in stocks.items()}
        temp = old['soil_temperature_c'].copy()
        air_heat = 5.*(air.ravel()[sl].reshape(1,-1)-temp)/(1+50*old['snow_swe_m'])
        # Its bounded forcing helper rejects signed heat/air, so the adapter
        # evaluates the identical enthalpy equations with signed air exchange.
        heat = ground_heat.ravel()[sl].reshape(1,-1)+geothermal.ravel()[sl].reshape(1,-1)+air_heat
        active = ~context['ocean_mask'].ravel()[sl].reshape(1,-1)
        energy = np.where(active,heat*DAY,0.)
        flux['heat_input_j_m2'].ravel()[sl] = energy.ravel()
        latent = 334000000.
        snowmelt = np.minimum(old['snow_swe_m'],np.maximum(energy,0.)/latent)
        soil_energy = energy-snowmelt*latent
        mass = old['liquid_water_m']+old['ground_ice_m']
        before = temp*2000000.+old['liquid_water_m']*latent
        enthalpy = before+soil_energy
        liquid = np.clip(enthalpy/latent,0.,mass)
        ice = mass-liquid
        new_temp = np.where(enthalpy<0,enthalpy,np.maximum(enthalpy-mass*latent,0.))/2000000.
        updated = dict(liquid_water_m=liquid,ground_ice_m=ice,
            soil_temperature_c=new_temp,snow_swe_m=old['snow_swe_m']-snowmelt,
            thaw_time_s=np.where(ice>1e-10,0.,old['thaw_time_s']+DAY),
            frozen_time_s=np.where(ice>1e-10,old['frozen_time_s']+DAY,0.))
        for name,value in updated.items():
            stocks[name].ravel()[sl] = np.where(active,value,old[name]).ravel()
        flux['snow_meltwater_m'].ravel()[sl] = np.where(active,snowmelt,0.).ravel()
        flux['infiltration_factor'].ravel()[sl] = np.divide(liquid,mass,out=np.ones_like(mass),where=mass>0).ravel()
        flux['height_change_m'].ravel()[sl] = np.where(active,.09*(ice-old['ground_ice_m']),0.).ravel()
        area = context['spacing_m']**2
        ledger['heat_input_j'] += float(energy.sum()*area)
        ledger['snow_latent_j'] += float(snowmelt[active].sum()*latent*area)
        ledger['energy_residual_j'] += float(((new_temp*2000000.+liquid*latent-before-soil_energy)*active).sum()*area)
    return flux,ledger


def prepare_snow_history(temperature_c, precipitation_mm, *, spacing_m, ocean_mask,
                         support_ids=(), years=10, snow_parameters=None):
    """Stream global snow summaries; retain monthly history only for selected IDs.

    Native preparation owns candidate selection and can call twice: first with
    no supports, then with selected global cell IDs. No independent tile snow.
    This is a preparation scenario, not duplicated live seasonal snow inventory.
    """
    if type(years) is not int or not 10 <= years <= 100:
        raise ValueError('snow preparation requires 10..100 physical years')
    t,p = np.asarray(temperature_c,float),np.asarray(precipitation_mm,float)
    ocean = np.asarray(ocean_mask,bool)
    if t.shape != (12,)+ocean.shape or p.shape != t.shape or not np.isfinite(t).all() or not np.isfinite(p).all() or np.any(p<0):
        raise ValueError('finite monthly common climate required')
    ids = np.asarray(support_ids,dtype=np.int64)
    if ids.ndim != 1 or np.any(ids<0) or np.any(ids>=ocean.size) or np.unique(ids).size != ids.size:
        raise ValueError('unique global snow support IDs required')
    sp = SnowParameters(**(snow_parameters or {}))
    swe = np.zeros(ocean.shape)
    annual_min = np.full(ocean.shape,np.inf)
    history = {name:np.empty((years*12,ids.size)) for name in
        ('swe_mm','snowfall_mm','potential_ablation_mm','potential_sublimation_mm','snow_melt_mm','sublimation_mm')}
    years_perennial = np.zeros(ocean.shape,np.int64)
    annual = []
    for year in range(years):
        minimum = np.full(ocean.shape,np.inf)
        accumulation = np.zeros(ocean.shape)
        ablation = np.zeros(ocean.shape)
        for month,days in enumerate(MONTH_DAYS):
            solid = np.where((t[month]<sp.freezing_threshold_c)&~ocean,p[month],0.)
            available = swe+solid
            melt_demand = sp.degree_day_melt_mm_per_day_c*np.maximum(t[month]-sp.min_melt_temperature_c,0)*days
            sub_demand = np.full(ocean.shape,sp.sublimation_demand_mm_per_day*days)
            melt = np.minimum(available,melt_demand)
            sub = np.minimum(available-melt,sub_demand)
            swe = available-melt-sub
            minimum = np.minimum(minimum,swe)
            accumulation += solid
            ablation += melt+sub
            for name,value in zip(history,(swe,solid,melt_demand,sub_demand,melt,sub)):
                history[name][year*12+month] = value.ravel()[ids]
        years_perennial += minimum>0
        annual_min = np.minimum(annual_min,minimum) if year>=years-5 else annual_min
        annual.append(dict(year=year+1,accumulation_m3=float(accumulation.sum()*spacing_m**2/1000),
            ablation_m3=float(ablation.sum()*spacing_m**2/1000),storage_m3=float(swe.sum()*spacing_m**2/1000)))
    return dict(algorithm='world-sparse-ten-year-snow-preparation-v1',years=years,
        time_edges_s=np.r_[0.,np.cumsum(np.tile(MONTH_DAYS,years)*DAY)],
        climate_identity=identity(dict(temperature_c=t,precipitation_mm=p,ocean_mask=ocean),dict(spacing_m=float(spacing_m),snow_parameters=sp.identity())),
        min_perennial_swe_mm=annual_min.copy(),years_with_perennial_snow=years_perennial,
        net_accumulation_mm=swe.copy(),snow_swe_mm=swe.copy(),
        support_ids=ids.copy(),history=history,annual_summary=annual,
        terminal_swe_mm=swe,last_five_year_minimum_swe_mm=annual_min,
        ownership='preparation evidence only; native initial inventory must debit one accepted terminal stock')


def run_integrated_seasons(elevation_m, *, world_seed, first_xz_m, spacing_m,
        ocean_mask, receiver, order, lake_id, materials, climate, config, initial_state):
    from terrain_pipeline.world_environment import _grid, climate_fields, _material, _weathering_states
    started = time.perf_counter()
    cpu_started = time.process_time()
    height,ocean = _grid(elevation_m,first_xz_m,spacing_m,ocean_mask)
    cfg = dict(config or {})
    env = dict(cfg.get('environment',{}))
    thermal_parameters,soil_water_parameters = thermal_scenario_parameters(env)
    warmup,output = cfg.get('spinup_years',1),cfg.get('output_years',1)
    if type(warmup) is not int or type(output) is not int or not 0<=warmup<=10 or not 1<=output<=5:
        raise ValueError('bounded integer spinup/output years required')
    if height.size>1000000:
        raise ValueError('integrated environment supports at most one million global cells')
    if np.asarray(lake_id).shape!=height.shape:
        raise ValueError('same-shape lake labels required')
    block = env.get('block_cells',32768)
    if type(block) is not int or not 1<=block<=262144:
        raise ValueError('environment block_cells must be 1..262144')
    climate = climate or climate_fields(height,world_seed=world_seed,first_xz_m=first_xz_m,
        spacing_m=spacing_m,ocean_mask=ocean,config=cfg)
    ca = climate.get('arrays',climate)
    temperature = np.asarray(ca['monthly_temperature_c'],float)
    precipitation = np.asarray(ca['monthly_precipitation_mm'],float)
    if temperature.shape!=(12,)+height.shape or precipitation.shape!=temperature.shape or not np.isfinite(temperature).all() or not np.isfinite(precipitation).all() or np.any(precipitation<0):
        raise ValueError('12 finite common climate fields and nonnegative precipitation required')
    if len(first_xz_m)!=2 or any(float(v)!=int(v) for v in first_xz_m):
        raise ValueError('integrated global mesh requires integer metric origin')
    land = ~ocean
    area = float(spacing_m)**2
    n = height.size
    params = RunoffParameters(**cfg.get('runoff_parameters',{}))
    snow = SnowParameters(**cfg.get('snow_parameters',{}))
    context = dict(height_m=height,spacing_m=float(spacing_m),world_seed=int(world_seed),
        origin_native_xz=tuple(map(int,first_xz_m)),receiver=np.asarray(receiver).reshape(height.shape),
        ocean_mask=ocean,valid_mask=np.ones(height.shape,bool),protected_mask=np.zeros(height.shape,bool),
        river_mask=np.asarray(lake_id).reshape(height.shape)>=0)
    for name in ('wind_x_m_s','wind_z_m_s'):
        context[name] = np.asarray(ca.get(name,np.zeros(height.shape)),float)
    mesh = grid_mesh(height.shape,x0_m=first_xz_m[0],z0_m=first_xz_m[1],dx_m=float(spacing_m),world_seed=int(world_seed))
    context['origin_native_xz'] = mesh.origin_native_xz
    source = np.repeat(np.arange(n),np.diff(mesh.indptr))
    target = mesh.indices
    # Supply exactly this shared graph to habitat; blocks never cut graph edges.
    context.update(graph_edge_source=source,graph_edge_target=target,
        node_x_m=mesh.node_x_m.reshape(height.shape),node_z_m=mesh.node_z_m.reshape(height.shape))
    context['_habitat_edges_valid'] = valid_edge_mask(mesh,land)
    keep = (source<target)&land.ravel()[source]&land.ravel()[target]
    sources,targets = source[keep],target[keep]
    face_metric = float(spacing_m)/mesh.edge_length_m[keep]
    state_binding = binding(height,ocean,materials,ca,cfg,world_seed,first_xz_m,spacing_m)
    integrated = initialize(context,params,env.get('initial_inventory_scenario',{}),state_binding,initial_state)
    if any(e.get('kind')=='volcanism' and e.get('age_ma',0.)==0 for e in env.get('dated_events',())) and 'volcanism' not in integrated:
        integrated['volcanism'] = {name:np.zeros(height.shape) for name in
            ('mobile_lava_m3','lava_heat_j','airborne_ash_m3','deposited_lava_m3','deposited_ash_m3')}
    initial_inventory = flatten_arrays(integrated)
    initial_inventory = {k:v.copy() for k,v in initial_inventory.items()}
    water,thermal,chem,eco = (integrated[k] for k in ('water','thermal','chemistry','succession'))
    soil_depth = (_material(materials,'soil_thickness_m',height.shape,.3) if initial_state is None else np.asarray(initial_state['soil_thickness_m'],float).copy())
    weathered = np.zeros(height.shape) if initial_state is None else np.asarray(initial_state['weathered_rock_m'],float).copy()
    weather_states = _weathering_states(materials,height.shape,area,land,initial_state)
    porosity = _material(materials,'porosity',height.shape,.35)
    if np.any((porosity<0)|(porosity>=1)):
        raise ValueError('material porosity must be in [0,1)')
    aquifer = env.get('aquifer_parameters',{})
    def parameter(name,default,minimum=0.,maximum=None):
        value = np.broadcast_to(np.asarray(aquifer.get(name,default),float),height.shape).copy()
        if not np.isfinite(value).all() or np.any(value<minimum) or (maximum is not None and np.any(value>maximum)):
            raise ValueError('invalid aquifer parameter: '+name)
        return value
    sy = parameter('specific_yield',.2,1e-12,1.)
    thickness = parameter('thickness_m',10.,1e-12)
    base = height-thickness
    capacity = thickness*area*sy*land
    # Hydraulic conductivity from actual material permeability and water
    # mobility; finite engineering default is declared when material lacks it.
    permeability = _material(materials,'permeability_m2',height.shape,1e-13)
    if np.any(permeability<0):
        raise ValueError('nonnegative permeability required')
    conductance = permeability*9.81e6*thickness*land
    tau = parameter('baseflow_timescale_s',90*DAY,1e-12)
    geothermal = _material(materials,'geothermal_heat_w_m2',height.shape,.06)*land
    if np.any(geothermal<0):
        raise ValueError('nonnegative geothermal heat required')
    field_capacity_m = params.soil_capacity_mm/1000*soil_water_parameters['field_capacity_fraction']
    names = ('monthly_runoff_m3','monthly_discharge_m3_s','monthly_soil_water_mm',
        'monthly_snow_swe_mm','monthly_actual_et_mm','monthly_cover_fraction','monthly_snow_melt_mm',
        'monthly_soil_thickness_m','monthly_weathered_rock_m','monthly_groundwater_storage_m3',
        'monthly_groundwater_head_m','monthly_groundwater_baseflow_m3','monthly_groundwater_recharge_m3',
        'monthly_ground_ice_m','monthly_soil_temperature_c','monthly_infiltration_factor',
        'monthly_absorbed_shortwave_j_m2','monthly_geothermal_input_j_m2','monthly_actual_et_energy_j_m2',
        'monthly_biomass_carbon_kg','monthly_soil_organic_carbon_kg','monthly_soil_salt_kg',
        'monthly_soil_nutrient_kg','monthly_plant_nutrient_kg','monthly_disturbance_fraction',
        'monthly_root_cohesion_pa','monthly_manning_n','monthly_plant_stress_factor','monthly_habitat_population_individuals')
    selected = env.get('output_fields', ())
    if selected == 'all':
        selected = names
    if isinstance(selected,str) or not set(selected).issubset(names):
        raise ValueError('environment output_fields must name supported monthly diagnostics, or all')
    required_names = names[:9]
    arrays = {name:np.empty((output*12,)+height.shape) for name in names if name in required_names or name in selected}
    arrays['spinup_monthly_runoff_m3'] = np.empty((warmup*12,)+height.shape)
    arrays.update(monthly_temperature_c=np.tile(temperature,(output,1,1)),
        monthly_precipitation_mm=np.tile(precipitation,(output,1,1)))
    for name in ('wind_x_m_s','wind_z_m_s'):
        if name in ca:
            arrays[name] = np.asarray(ca[name],float).copy()
    ledgers = dict(spinup=[],output=[])
    process_ledgers = dict(thermal=[],chemistry=[],ecology=[],habitat=[],volcanism=[])
    radiation = [radiation_month(height,spacing_m,m,land) for m in range(12)]
    proposed_heave = np.zeros(height.shape)
    external_maps = {name:np.zeros(height.shape) for name in
        ('photosynthesis_carbon_kg','respired_carbon_kg','fire_atmosphere_carbon_kg','births_individuals','deaths_individuals',
         'actual_et_m3','sublimation_m3','local_runoff_m3','energy_input_j','energy_output_j')}
    output_index = 0
    external = dict(water_m3=0.,salt_kg=0.,nutrient_kg=0.,organic_carbon_kg=0.,sensible_heat_j=0.,latent_heat_j=0.)
    packet_binding = dict(source_identity=env.get('source_identity',state_binding),parent_terrain_revision=env.get('terrain_revision'))
    initial_totals = inventory_totals(integrated,area)
    for run_month in range((warmup+output)*12):
        month = int(integrated['months_completed'])%12
        days = int(MONTH_DAYS[month])
        t = temperature[month]
        rain = precipitation[month]/days/1000*land
        absorbed = radiation[month]['absorbed_shortwave_w_m2']
        before = water_total(integrated,area)
        incoming_packets = apply_native_packets(integrated,env.get('native_exchange',()),packet_binding,area,land,external_maps['energy_input_j'])
        for name,value in incoming_packets.items():
            external[name] += value
        fire_hazard,disturbance_hazard = np.zeros(height.shape),np.zeros(height.shape)
        volcanic_heat_j = 0.
        longwave_down_j = 0.
        longwave_up_j = 0.
        local,et,melt_sum,recharge_sum,baseflow_sum,wet_sum,stress_sum = (np.zeros(height.shape) for _ in range(7))
        chemistry_month = {}
        thermal_month = {}
        groundwater_numerics = dict(water_residual_m3=0.,donor_roundoff_transfer_reduction_m3=0.,
            salt_residual_kg=0.,nutrient_residual_kg=0.,salt_roundoff_transfer_reduction_kg=0.,nutrient_roundoff_transfer_reduction_kg=0.)
        for day in range(days):
            packets_today = apply_native_packets(integrated,(),packet_binding,area,land,external_maps['energy_input_j'])
            for name,value in packets_today.items():
                external[name] += value
                incoming_packets[name] += value
            events = advance_current_events(integrated,env.get('dated_events',()),context,1)
            process_ledgers['volcanism'].extend(events['ledgers'])
            proposed_heave += events['height_change_m']
            fire_hazard += events['fire_hazard_s']/days
            disturbance_hazard += events['disturbance_hazard_s']/days
            volcanic_heat_j += float(events['heat_w_m2'].sum()*DAY*area)
            solid = np.where(t<snow.freezing_threshold_c,rain,0.)
            water['snow_swe_m'] += solid
            liquid_rain = rain-solid
            # Snow phase has one owner. The enthalpy kernel melts snow; ordinary
            # degree-day melt is suppressed in this integrated branch.
            longwave_down,longwave_up = longwave_exchange(thermal['soil_temperature_c'],t,thermal_parameters,land)
            net_longwave = longwave_down-longwave_up
            longwave_down_j += float(longwave_down.sum()*DAY*area)
            longwave_up_j += float(longwave_up.sum()*DAY*area)
            ff,fl = _freeze_global(integrated,t,absorbed*.7+net_longwave,geothermal+events['heat_w_m2'],context,block)
            melt = ff['snow_meltwater_m']
            melt_sum += melt
            proposed_heave += ff['height_change_m']
            sublimation = np.minimum(water['snow_swe_m'],snow.sublimation_demand_mm_per_day/1000*land)
            water['snow_swe_m'] -= sublimation
            external_maps['sublimation_m3'] += sublimation*area
            external_maps['energy_input_j'] += ((ff['heat_input_j_m2']+longwave_up*DAY+absorbed*.3*DAY-
                events['heat_w_m2']*DAY)*area+events['external_lava_heat_j']+
                liquid_rain*area*334000000.+sublimation*area*2834000000.)
            incoming = liquid_rain+melt
            infiltration = np.minimum(incoming,np.minimum(params.infiltration_capacity_mm_h*24/1000*ff['infiltration_factor'],
                np.maximum(params.soil_capacity_mm/1000-water['root_liquid_m']-water['ground_ice_m'],0.)))
            water['root_liquid_m'] += infiltration
            water['fast_surface_m'] += incoming-infiltration
            cover = np.clip(eco['biomass_carbon_kg']/(8.*area),0.,1.)
            # Bare-soil evaporation remains; actual live carbon changes canopy
            # transpiration demand and therefore root storage/recharge/runoff.
            actual_et = np.minimum(water['root_liquid_m'],absorbed*.3*DAY/LATENT_ET*(.5+.5*cover))
            water['root_liquid_m'] -= actual_et
            wet_sum += np.clip(water['root_liquid_m']/(params.soil_capacity_mm/1000),0.,1.)
            exposure_water = water['root_liquid_m']*area
            exposure_salinity = np.divide(chem['salt_dissolved_kg'],exposure_water,
                out=np.zeros(height.shape),where=exposure_water>0)
            stress_sum += np.where(exposure_water>0,1/(1+exposure_salinity/4),0.)
            # Gravity drainage owns only water above retained field capacity;
            # frozen pore water counts toward that finite root-zone occupancy.
            retained_liquid = np.maximum(field_capacity_m-water['ground_ice_m'],0.)
            drainable_liquid = np.maximum(water['root_liquid_m']-retained_liquid,0.)
            percolation = np.minimum(drainable_liquid,params.percolation_mm_h*24/1000*ff['infiltration_factor'])
            water['root_liquid_m'] -= percolation
            recharge = percolation*area
            water['groundwater_m3'] += recharge
            release = water['fast_surface_m']*-np.expm1(-DAY/params.fast_tau_s)
            water['fast_surface_m'] -= release
            # Chemistry sees the exact water transaction: drainage precedes ET
            # in its core. Pre-drain ET is already debited here; its water view
            # therefore starts after actual ET and before percolation.
            chem_view = dict(chem,water_m3=(water['root_liquid_m']+percolation)*area)
            daily_demand = area*SUCCESSION_PARAMETERS['growth_carbon_kg_m2_s']*DAY*SUCCESSION_PARAMETERS['nutrient_kg_per_carbon_kg']*land
            daily_demand *= np.clip(water['root_liquid_m']+percolation,0.,1.)>0
            cr = advance_soil_chemistry(chem_view,dict(plant_uptake_demand_kg=daily_demand,
                litter_carbon_kg=integrated['queues']['litter_carbon_kg'],
                plant_nutrient_return_kg=integrated['queues']['plant_nutrient_return_kg']),context,DAY)
            # Split the transaction: roots take finite nutrient while liquid is
            # present; the actual subsequent percolation leaches the remainder.
            drainage_fraction = np.divide(recharge,chem_view['water_m3'],out=np.zeros(height.shape),where=chem_view['water_m3']>0)
            for pool_name,flux_name in (('salt_dissolved_kg','salt_leached_kg'),('nutrient_kg','nutrient_leached_kg')):
                leached = cr['state'][pool_name]*drainage_fraction
                cr['state'][pool_name] -= leached
                cr['fluxes'][flux_name] = leached
                cr['ledger'][flux_name] = float(leached.sum())
            cr['state']['water_m3'] -= recharge
            cr['fluxes']['salinity_kg_m3'] = np.divide(cr['state']['salt_dissolved_kg'],cr['state']['water_m3'],
                out=np.zeros(height.shape),where=cr['state']['water_m3']>0)
            cr['fluxes']['drainage_m3'] = recharge.copy()
            cr['ledger']['drainage_m3'] = float(recharge.sum())
            integrated['queues']['plant_nutrient_uptake_kg'] += cr['fluxes']['plant_uptake_kg']
            chem.clear()
            chem.update({k:v for k,v in cr['state'].items() if k!='water_m3'})
            external_maps['respired_carbon_kg'] += cr['fluxes']['respired_carbon_kg']
            integrated['queues']['litter_carbon_kg'].fill(0.)
            integrated['queues']['plant_nutrient_return_kg'].fill(0.)
            integrated['groundwater_solutes']['salt_kg'] += cr['fluxes']['salt_leached_kg']
            integrated['groundwater_solutes']['nutrient_kg'] += cr['fluxes']['nutrient_leached_kg']
            gw = global_groundwater(water['groundwater_m3'],integrated['groundwater_solutes'],base,sy,
                conductance,sources,targets,area,DAY,capacity,tau,face_metric)
            for name in ('water_residual_m3','donor_roundoff_transfer_reduction_m3'):
                groundwater_numerics[name] += gw[name]
            for name in ('salt','nutrient'):
                groundwater_numerics[name+'_residual_kg'] += gw['tracer_residual_kg'][name+'_kg']
                groundwater_numerics[name+'_roundoff_transfer_reduction_kg'] += gw['tracer_roundoff_transfer_reduction_kg'][name+'_kg']
            for name,value in gw['exports'].items():
                integrated['routed_exports'][name] += value
            local += release*area+gw['baseflow_m3']
            external_maps['energy_output_j'] += ((longwave_up+absorbed*.3)*DAY*area+
                (actual_et*area+release*area+gw['baseflow_m3'])*334000000.+sublimation*area*2834000000.)
            et += actual_et
            recharge_sum += recharge
            baseflow_sum += gw['baseflow_m3']
            for destination,record in ((chemistry_month,cr['ledger']),(thermal_month,fl)):
                for name,value in record.items():
                    destination[name] = destination.get(name,0.)+value
            # Water account accumulates actual atmosphere loss once.
            chemistry_month['sublimation_m3'] = chemistry_month.get('sublimation_m3',0.)+float(sublimation.sum()*area)
            integrated['elapsed_s'] += DAY
        wet = wet_sum/days
        plant_stress = stress_sum/days
        # Uptake is debited from chemistry once, then handed to succession.
        uptake = integrated['queues']['plant_nutrient_uptake_kg'].copy()
        integrated['queues']['plant_nutrient_uptake_kg'].fill(0.)
        ecology = advance_succession(eco,dict(temperature_c=t,water_available_fraction=wet,
            plant_stress_factor=plant_stress,plant_nutrient_uptake_kg=uptake,
            fire_hazard_s=fire_hazard+env.get('ecology_parameters',{}).get('fire_hazard_s',0.),
            disturbance_hazard_s=disturbance_hazard+env.get('ecology_parameters',{}).get('disturbance_hazard_s',0.)),context,days*DAY)
        eco.clear()
        eco.update(ecology['state'])
        integrated['queues']['litter_carbon_kg'] = ecology['fluxes']['litter_carbon_kg'].copy()
        integrated['queues']['plant_nutrient_return_kg'] = ecology['fluxes']['plant_nutrient_return_kg'].copy()
        habitat = advance_global_habitat(integrated['habitat'],dict(vegetation_cover_fraction=ecology['fluxes']['cover_fraction'],
            water_available_fraction=wet,disturbance_fraction=eco['disturbance_fraction'],water_temperature_c=t),context,mesh,days*DAY)
        integrated['habitat'] = habitat['state']
        for name in ('photosynthesis_carbon_kg','fire_atmosphere_carbon_kg'):
            external_maps[name] += ecology['fluxes'][name]
        for name in ('births_individuals','deaths_individuals'):
            external_maps[name] += habitat['fluxes'][name]
        weather = np.zeros(n)
        parent = np.zeros(n)
        dissolved = 0.
        for index,start in enumerate(range(0,n,MAX_COLUMNS)):
            stop = min(start+MAX_COLUMNS,n)
            ws,flux = advance_weathering(weather_states[index],dt_s=days*DAY,
                temperature_c=t.ravel()[start:stop],moisture=wet.ravel()[start:stop],
                bio_activity=ecology['fluxes']['cover_fraction'].ravel()[start:stop],parameters=cfg.get('weathering_parameters'))
            weather_states[index] = ws
            weather[start:stop] = flux['weathered_depth_m']
            parent[start:stop] = flux['regolith_solid_m3']
            dissolved += float(flux['dissolved_solid_m3'].sum())
        weather = weather.reshape(height.shape)
        soil_depth += parent.reshape(height.shape)/area/(1-porosity)
        weathered += weather
        thermal['absorbed_energy_j_m2'] += absorbed*days*DAY
        after = water_total(integrated,area)
        external_maps['actual_et_m3'] += et*area
        external_maps['local_runoff_m3'] += local
        ledger = dict(month=month+1,physical_start_s=integrated['elapsed_s']-days*DAY,
            precipitation_m3=float((rain*days).sum()*area),actual_et_m3=float(et.sum()*area),
            sublimation_m3=chemistry_month['sublimation_m3'],local_runoff_m3=float(local.sum()),
            initial_storage_m3=before,final_storage_m3=after,
            native_water_input_m3=incoming_packets['water_m3'],
            groundwater_baseflow_m3=float(baseflow_sum.sum()),groundwater_recharge_m3=float(recharge_sum.sum()),
            weathered_rock_bulk_m3=float(weather.sum()*area),soil_regolith_solid_added_m3=float(parent.sum()),dissolved_rock_solid_m3=dissolved)
        ledger['water_residual_m3'] = before+ledger['precipitation_m3']+ledger['native_water_input_m3']-after-ledger['actual_et_m3']-ledger['sublimation_m3']-ledger['local_runoff_m3']
        ledger['groundwater_numerics'] = groundwater_numerics
        ledger['precipitation_liquid_m3'] = float(np.where(t>=snow.freezing_threshold_c,precipitation[month]/1000*land,0.).sum()*area)
        ledger['absorbed_shortwave_j'] = float(absorbed.sum()*days*DAY*area)
        ledger['geothermal_j'] = float(geothermal.sum()*days*DAY*area)
        ledger['longwave_downward_j'] = longwave_down_j
        ledger['longwave_upward_j'] = longwave_up_j
        ledger['air_heat_j'] = (thermal_month['heat_input_j']-float(((absorbed*.7+geothermal)*days*DAY).sum()*area)-
            volcanic_heat_j-longwave_down_j+longwave_up_j)
        ledger['actual_et_vaporization_j'] = float(et.sum()*area*LATENT_ET)
        ledger['unused_et_energy_j'] = float(absorbed.sum()*.3*days*DAY*area)-ledger['actual_et_vaporization_j']
        # Declared atmospheric demand supplies its own ice->vapour latent heat;
        # it is not silently taken from shortwave already partitioned above.
        ledger['sublimation_atmosphere_input_j'] = ledger['sublimation_m3']*2834000000.
        ledger['sublimation_vaporization_j'] = ledger['sublimation_atmosphere_input_j']
        is_spinup = run_month<warmup*12
        ledgers['spinup' if is_spinup else 'output'].append(ledger)
        process_ledgers['chemistry'].append(chemistry_month)
        process_ledgers['thermal'].append(thermal_month)
        process_ledgers['ecology'].append(ecology['ledger'])
        process_ledgers['habitat'].append(habitat['ledger'])
        integrated['months_completed'] += 1
        if is_spinup:
            arrays['spinup_monthly_runoff_m3'][run_month] = local
        else:
            values = (local,accumulate_graph(receiver,order,local)/(days*DAY),water['root_liquid_m']*1000,
                water['snow_swe_m']*1000,et*1000,ecology['fluxes']['cover_fraction'],melt_sum*1000,
                soil_depth,weather,water['groundwater_m3'],gw['head_m'],baseflow_sum,recharge_sum,
                water['ground_ice_m'],thermal['soil_temperature_c'],ff['infiltration_factor'],
                absorbed*days*DAY,geothermal*days*DAY,et*LATENT_ET,eco['biomass_carbon_kg'],
                chem['organic_carbon_kg'],chem['salt_dissolved_kg']+chem['salt_solid_kg'],
                chem['nutrient_kg'],eco['plant_nutrient_kg'],eco['disturbance_fraction'],
                ecology['fluxes']['root_cohesion_pa'],ecology['fluxes']['manning_n'],
                plant_stress,habitat['state']['population_individuals'])
            final_fields = dict(zip(names,values))
            for name,value in final_fields.items():
                if name in arrays:
                    arrays[name][output_index] = value
            output_index += 1
    arrays.update(temperature_c=temperature.mean(axis=0),precipitation_mm_yr=precipitation.sum(axis=0),
        geothermal_heat_w_m2=geothermal.copy(),soil_salinity_kg_m3=cr['fluxes']['salinity_kg_m3'].copy(),
        habitat_suitability=habitat['fluxes']['suitability'].copy(),
        environment_proposed_height_change_m=proposed_heave.copy())
    for alias,monthly in dict(soil_water_mm='soil_water_mm',snow_swe_mm='snow_swe_mm',cover_fraction='cover_fraction',
        root_cohesion_pa='root_cohesion_pa',manning_n='manning_n',groundwater_head_m='groundwater_head_m',
        soil_temperature_c='soil_temperature_c',plant_stress_factor='plant_stress_factor',
        habitat_population_individuals='habitat_population_individuals').items():
        arrays[alias] = final_fields['monthly_'+monthly].copy()
    for name,value in final_fields.items():
        if name not in required_names:
            arrays.setdefault(name.removeprefix('monthly_'),value.copy())
    # Flat numeric snapshots are directly serializable by the existing product
    # array writer. No compatibility views duplicate the owned water account.
    arrays.update({'initial_owner__'+k.replace('/','__'):v for k,v in initial_inventory.items()})
    arrays.update({'cumulative_external__'+k:v for k,v in external_maps.items()})
    arrays['land_cover_index'] = np.where(arrays['cover_fraction']>.2,2,np.where(arrays['cover_fraction']>0,1,0)).astype(np.uint8)
    stocks = ('bedrock_solid_m3','regolith_solid_m3','regolith_bulk_m3','parent_solid_m3','dissolved_solid_m3',
        'delivered_regolith_solid_m3','delivered_parent_solid_m3','weatherable_thickness_m','area_m2',
        'bed_hardness','solubility','initial_bedrock_solid_m3')
    state = dict(integrated=integrated,soil_fast_slow_mm=np.stack((water['root_liquid_m']*1000,
        water['fast_surface_m']*1000,np.zeros(height.shape))),snow_swe_mm=water['snow_swe_m'].copy()*1000,
        soil_thickness_m=soil_depth.copy(),weathered_rock_m=weathered.copy(),
        weathering={k:np.concatenate([ws[k] for ws in weather_states]) for k in stocks})
    bed_commit = dict(status='uncommitted',source_binding=state_binding,
        terrain_revision=env.get('terrain_revision'),components=['frost_heave'],
        id=identity(dict(height_change_m=proposed_heave),dict(binding=state_binding,elapsed_s=integrated['elapsed_s'])))
    processes = {name:dict(status='computed',scope=scope) for name,scope in dict(
        snow='one owned snow inventory; enthalpy melt and sublimation',groundwater='finite shared-face aquifer and debited local baseflow; no lake stage exchange',
        frozen_ground='signed-air one-layer enthalpy adapter; actual infiltration factor',radiation='64km bounded shadows, four representative-day phases, fictional latitude35 longitude0',
        soil_chemistry='finite soil/GW/export salt and nutrient stocks',ecology='carbon/nutrient succession with queued litter/returns',
        disturbance='declared hazard scenario, not dated historical-event replay',habitat='global shared graph functional population',
        weathering='finite existing weathering core with actual biomass feedback').items()}
    processes['volcanism'] = dict(status='computed' if process_ledgers['volcanism'] else 'not-triggered',
        reason='accepted age_ma=0 finite dated event supply' if process_ledgers['volcanism'] else 'no accepted current event intersects physical interval')
    scheduled_events = integrated['events'].get('scheduled',{}).values()
    triggered_disturbance = any(e.get('kind') in ('fire','disturbance') and e['id'] in integrated['events']['consumed_ids']
        for e in scheduled_events)
    background_hazard = any(np.any(np.asarray(env.get('ecology_parameters',{}).get(k,0.))>0)
        for k in ('fire_hazard_s','disturbance_hazard_s'))
    processes['disturbance'] = dict(status='computed' if triggered_disturbance or background_hazard else 'not-triggered',
        reason='dated event consumed or explicit nonzero background hazard' if triggered_disturbance or background_hazard else 'no dated disturbance intersects the interval and background hazards are zero',
        background_hazard_scenario=env.get('ecology_parameters',{}),
        waiting_event_ids=[e['id'] for e in scheduled_events if e.get('kind') in ('fire','disturbance') and e['id'] not in integrated['events']['consumed_ids']])
    final_totals = inventory_totals(integrated,area)
    accounts = combined_accounts(initial_totals,final_totals,ledgers,process_ledgers,external)
    metadata = dict(algorithm=ALGORITHM,world_seed=world_seed,first_xz_m=list(first_xz_m),spacing_m=float(spacing_m),
        shape_zx=list(height.shape),spinup_years=warmup,output_years=output,months_completed=integrated['months_completed'],
        climate_identity=climate.get('metadata',{}).get('identity'),runoff_parameters=asdict(params),snow_parameters=snow.identity(),
        water_budget=ledgers,process_budgets=process_ledgers,independent_accounts=accounts,processes=processes,
        environment_bed_commit=bed_commit,state_binding=state_binding,
        integrated_control=dict(schema=integrated['schema'],elapsed_s=integrated['elapsed_s'],
            months_completed=integrated['months_completed'],events=integrated['events'],handoffs=integrated['handoffs']),
        storage_semantics='root liquid/fast/GW/ground ice/snow unique owners; compatibility slow row is zero; chemistry water is a view',
        runoff_semantics='local interval volume including once-debited groundwater baseflow; downstream routing owns lakes',
        radiation_approximation=dict(algorithm='bounded-fictional-sun-v1',horizon_m=64000,phases=4,latitude_deg=35.,longitude_deg=0.,unknown_beyond_horizon=True),
        thermal_scenario=dict(algorithm='grey-surface-sky-longwave-v1',parameters=thermal_parameters,
            stefan_boltzmann_w_m2_k4=STEFAN_BOLTZMANN_W_M2_K4,temperature_units='kelvin internally; Celsius inputs',
            forcing_status='declared uncalibrated grey sky; no measured humidity/cloud or atmosphere solver'),
        soil_water_scenario=dict(parameters=soil_water_parameters,field_capacity_m=field_capacity_m,
            semantics='finite total root liquid+ice retention; only excess liquid drains at existing rate and frozen factor'),
        thermal_soil_parameter_identity=identity({},dict(thermal=thermal_parameters,soil_water=soil_water_parameters,
            stefan_boltzmann_w_m2_k4=STEFAN_BOLTZMANN_W_M2_K4,soil_capacity_mm=params.soil_capacity_mm)),
        initial_inventory_scenario=env.get('initial_inventory_scenario',{}),
        engineering_defaults=dict(permeability_m2=1e-13,aquifer_thickness_m=10,specific_yield=.2,baseflow_days=90,geothermal_w_m2=.06),
        costs=dict(wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu_started,
            state_array_bytes=sum(v.nbytes for v in flatten_arrays(state).values()),output_array_bytes=sum(v.nbytes for v in arrays.values())),
        limitations=['finite engineering accounts, uncalibrated defaults; no permanent infinite-world hydrology certification',
            'prescribed snow sublimation demand has explicit equal atmospheric energy supply and vapour energy output, no resolved atmosphere',
            'one-layer grey-sky longwave exchange with declared fixed emissivity; no cloud/humidity transport or multilayer snow/soil certification',
            'habitat uses functional expected individuals, no food web'])
    # Timing is observational and deliberately excluded from content identity.
    identity_metadata = {k:v for k,v in metadata.items() if k!='costs'}
    metadata['identity'] = identity(dict(arrays,**{'state/'+k:v for k,v in flatten_arrays(state).items()}),identity_metadata)
    return dict(arrays=arrays,state=state,metadata=metadata,conditional=None,
        initial_integrated_arrays=initial_inventory)
