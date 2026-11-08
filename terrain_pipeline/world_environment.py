"""Explicit metric world adapter for climate, snow and seasonal soil-water kernels.

Monthly states are physical seasonal time, separate from equivalent generation
erosion rounds. Query functions consume these published arrays without stepping.
"""
from __future__ import annotations

from dataclasses import asdict
import math

import numpy as np
from numba import njit
from scipy.ndimage import map_coordinates

from terrain_pipeline.common_infra import identity
from terrain_pipeline.climate_forcing import MONTH_DAYS, RefinedClimateParameters, sample_climate_v2
from terrain_pipeline.drainage import accumulate_graph
from terrain_pipeline.runoff import RunoffParameters
from terrain_pipeline.soil_water import (SnowParameters, temperature_index_pet_rate_mm_h,
    MAX_COLUMNS, initial_state as weather_initial_state, advance as advance_weathering,
    normalize_parameters as weather_parameters, assess_land_cover)
from terrain_pipeline.world_environment_conditional import run_conditional_processes

ALGORITHM = 'world-seasonal-water-v1'


def _grid(elevation_m, first_xz_m, spacing_m, ocean_mask):
    height = np.asarray(elevation_m, np.float64)
    ocean = np.asarray(ocean_mask, bool)
    if height.ndim != 2 or not height.size or height.size > 25000000 or not np.isfinite(height).all() or ocean.shape != height.shape:
        raise ValueError('finite common world height/ocean grid required')
    if not np.isfinite(spacing_m) or spacing_m <= 0 or len(first_xz_m) != 2 or not np.isfinite(first_xz_m).all():
        raise ValueError('finite absolute metric grid required')
    return height, ocean


def climate_fields(elevation_m, *, world_seed, first_xz_m, spacing_m, ocean_mask, config=None):
    """Sample the existing v2 climate against this world's actual elevation.

    Finite world edges use clamped heights for the orographic stencil, explicitly
    reported below. No synthetic coarse condition sampler or zero halo is used.
    ``block_cells`` controls allocation only, not arithmetic or the world seed.
    """
    height, ocean = _grid(elevation_m, first_xz_m, spacing_m, ocean_mask)
    cfg = dict(config or {})
    block = cfg.get('block_cells', 32768)
    if type(block) is not int or not 2 <= block <= 262144:
        raise ValueError('block_cells must be within 2..262144')
    scale = cfg.get('precipitation_multiplier', 1.)
    if not np.isfinite(scale) or scale < 0 or scale > 10:
        raise ValueError('finite precipitation multiplier in 0..10 required')
    parameters = RefinedClimateParameters(**cfg.get('climate_parameters', {}))
    nz, nx = height.shape
    x = first_xz_m[0] + np.tile(np.arange(nx), nz) * spacing_m
    z = first_xz_m[1] + np.repeat(np.arange(nz), nx) * spacing_m
    def sampler(qx, qz):
        qx, qz = np.broadcast_arrays(qx, qz)
        return map_coordinates(height, [(qz - first_xz_m[1]) / spacing_m,
                                       (qx - first_xz_m[0]) / spacing_m], order=1, mode='nearest', prefilter=False)
    arrays = dict(monthly_temperature_c=np.empty((12, height.size)),
                  monthly_precipitation_mm=np.empty((12, height.size)),
                  wind_x_m_s=np.empty(height.size), wind_z_m_s=np.empty(height.size),
                  orographic_lift=np.empty(height.size), orographic_shelter=np.empty(height.size))
    for start in range(0, height.size, block):
        stop = min(start + block, height.size)
        result = sample_climate_v2(world_seed, x[start:stop], z[start:stop], height.ravel()[start:stop],
                                   parameters=parameters, elevation_sampler=sampler)
        arrays['monthly_temperature_c'][:,start:stop] = result['monthly_temperature_c']
        arrays['monthly_precipitation_mm'][:,start:stop] = result['monthly_precipitation_mm'] * scale
        arrays['wind_x_m_s'][start:stop] = result['wind_unit'][0] * 8.
        arrays['wind_z_m_s'][start:stop] = result['wind_unit'][1] * 8.
        for name in ('orographic_lift','orographic_shelter'):
            arrays[name][start:stop] = result[name]
    for name, value in arrays.items():
        arrays[name] = value.reshape(((12,) if value.ndim == 2 else ()) + height.shape)
    metadata = dict(algorithm='world-metric-climate-v1', world_seed=world_seed,
        first_xz_m=list(first_xz_m), spacing_m=float(spacing_m), shape_zx=list(height.shape),
        climate_parameter_identity=parameters.identity_sha256, precipitation_multiplier=float(scale),
        elevation_source='caller_world_elevation_m', orographic_boundary='finite edge-clamped bilinear elevation stencil',
        latitude='existing synthetic periodic latitude bands, not a spherical world latitude',
        wind='existing v2 bearing bands with declared constant speed 8 m/s', status='computed')
    metadata['identity'] = identity(arrays, metadata)
    return dict(arrays=arrays, metadata=metadata)


@njit(cache=True)
def _constant_month_bucket(liquid, states, pet, hours, infiltration_capacity, soil_capacity, percolation_rate, fast_tau, slow_tau):
    """Same hourly advance_soil equations; exact constant-soil reservoir tail.

    This adapter operates on depth, with no historical 30m area assumption.
    Once the soil fixed point is reached, reservoirs use their geometric-series
    recurrence; the water account computes total release without cancellation
    at each hourly step. Soil/PET forcing remains the full physical month.
    """
    runoff = np.zeros(liquid.size)
    evap = np.zeros(liquid.size)
    fast_a = math.exp(-3600. / fast_tau)
    slow_a = math.exp(-3600. / slow_tau)
    fast_b = -math.expm1(-3600. / fast_tau) / (3600. / fast_tau)
    slow_b = -math.expm1(-3600. / slow_tau) / (3600. / slow_tau)
    for cell in range(liquid.size):
        rain = liquid[cell] / hours
        soil, fast, slow = states[0,cell], states[1,cell], states[2,cell]
        before = soil + fast + slow
        total_et = 0.
        for hour in range(hours):
            infiltration = min(rain, infiltration_capacity, max(soil_capacity - soil, 0.))
            wet_soil = soil + infiltration
            et = min(wet_soil, pet[cell])
            wet_soil -= et
            percolation = min(wet_soil, percolation_rate)
            new_soil = wet_soil - percolation
            fast = fast_a * fast + fast_b * (rain - infiltration)
            slow = slow_a * slow + slow_b * percolation
            total_et += et
            if new_soil == soil:
                remaining = hours - hour - 1
                if remaining:
                    fast_eq = fast_b * (rain - infiltration) / (1 - fast_a)
                    slow_eq = slow_b * percolation / (1 - slow_a)
                    fast = fast_eq + (fast - fast_eq) * fast_a ** remaining
                    slow = slow_eq + (slow - slow_eq) * slow_a ** remaining
                    total_et += remaining * et
                soil = new_soil
                break
            soil = new_soil
        states[0,cell], states[1,cell], states[2,cell] = soil, fast, slow
        evap[cell] = total_et
        runoff[cell] = max(0., liquid[cell] - total_et + before - soil - fast - slow)
    return runoff, evap


def _material(materials, name, shape, default=None):
    if name not in materials:
        if default is None:
            return None
        return np.full(shape, default, np.float64)
    value = np.broadcast_to(np.asarray(materials[name], np.float64), shape).copy()
    if not np.isfinite(value).all():
        raise ValueError('finite material field required: ' + name)
    return value


def _weathering_states(materials, shape, area, land, initial_state):
    """Bound calls to the unchanged 4096-column weathering kernel."""
    hardness = _material(materials,'bed_hardness',shape,.5).ravel()
    solubility = _material(materials,'solubility',shape,.2).ravel()
    stocks = []
    saved = (initial_state or {}).get('weathering')
    for start in range(0,land.size,MAX_COLUMNS):
        stop = min(start+MAX_COLUMNS,land.size)
        if saved is None:
            state = weather_initial_state(bedrock_thickness_m=land.ravel()[start:stop].astype(float),
                area_m2=area,bed_hardness=hardness[start:stop],solubility=solubility[start:stop])
        else:
            state = {name: value[start:stop].copy() for name,value in saved.items()}
            state.update(parameters=weather_parameters(),density_kg_m3=None,
                         status=np.where(state['bedrock_solid_m3']>0,'active','exhausted'))
        stocks.append(state)
    return stocks


def run_seasons(elevation_m, *, world_seed, first_xz_m, spacing_m, ocean_mask,
                receiver, order, lake_id, materials, climate=None, config=None,
                initial_state=None):
    """Run fixed monthly work with separate spin-up/output and local water input.

    Runoff is a cell-local interval volume; ``monthly_discharge_m3_s`` is its
    once-only graph accumulation. Optional mechanisms report pending inputs.
    A world terrain-shaping caller must not apply diagnostic frozen-ground heave
    as a second erosion/deposition volume.
    """
    if (config or {}).get('integrated_environment', False):
        from terrain_pipeline.world_environment_coupling import run_integrated_seasons
        return run_integrated_seasons(elevation_m, world_seed=world_seed,
            first_xz_m=first_xz_m, spacing_m=spacing_m, ocean_mask=ocean_mask,
            receiver=receiver, order=order, lake_id=lake_id, materials=materials,
            climate=climate, config=config, initial_state=initial_state)
    height, ocean = _grid(elevation_m, first_xz_m, spacing_m, ocean_mask)
    cfg = dict(config or {})
    warmup, output = cfg.get('spinup_years',1), cfg.get('output_years',1)
    if type(warmup) is not int or type(output) is not int or not 0 <= warmup <= 10 or not 1 <= output <= 5:
        raise ValueError('bounded integer spinup/output years required')
    climate = climate or climate_fields(height, world_seed=world_seed, first_xz_m=first_xz_m,
        spacing_m=spacing_m, ocean_mask=ocean, config=cfg)
    ca = climate.get('arrays',climate)
    temperature = np.asarray(ca['monthly_temperature_c'],np.float64)
    precipitation = np.asarray(ca['monthly_precipitation_mm'],np.float64)
    if temperature.shape != (12,) + height.shape or precipitation.shape != temperature.shape or not np.isfinite(temperature).all() or not np.isfinite(precipitation).all() or np.any(precipitation < 0):
        raise ValueError('12 finite common climate fields and nonnegative precipitation required')
    if np.asarray(lake_id).shape != height.shape:
        raise ValueError('same-shape lake labels required')
    params = RunoffParameters(**cfg.get('runoff_parameters',{}))
    snow_params = SnowParameters(**cfg.get('snow_parameters',{}))
    land = ~ocean
    n = height.size
    area = float(spacing_m) ** 2
    if initial_state is None:
        soil = np.zeros((3,n),np.float64)
        soil[0,land.ravel()] = params.initial_soil_mm
        soil[1,land.ravel()] = params.initial_fast_mm
        soil[2,land.ravel()] = params.initial_slow_mm
        swe = np.zeros(n)
        soil_depth = _material(materials, 'soil_thickness_m',height.shape,.3).ravel()
        weathered = np.zeros(n)
    else:
        soil = np.asarray(initial_state['soil_fast_slow_mm'],np.float64).reshape(3,n).copy()
        swe = np.asarray(initial_state['snow_swe_mm'],np.float64).reshape(n).copy()
        soil_depth = np.asarray(initial_state['soil_thickness_m'],np.float64).reshape(n).copy()
        weathered = np.asarray(initial_state.get('weathered_rock_m',np.zeros(n)),np.float64).reshape(n).copy()
    if not np.isfinite(soil).all() or not np.isfinite(swe).all() or np.any(soil < 0) or np.any(swe < 0) or np.any(soil[0] > params.soil_capacity_mm):
        raise ValueError('valid finite seasonal initial inventories required')
    erodibility = _material(materials, 'erodibility',height.shape,.5).ravel()
    porosity = _material(materials, 'porosity',height.shape,.35).ravel()
    if np.any((porosity < 0) | (porosity >= 1)) or np.any((erodibility < 0) | (erodibility > 1)):
        raise ValueError('material porosity/erodibility outside supported fractions')
    names = ('monthly_runoff_m3','monthly_discharge_m3_s','monthly_soil_water_mm',
             'monthly_snow_swe_mm','monthly_actual_et_mm','monthly_cover_fraction',
             'monthly_snow_melt_mm','monthly_soil_thickness_m','monthly_weathered_rock_m')
    arrays = {name:np.empty((output*12,) + height.shape) for name in names}
    arrays['spinup_monthly_runoff_m3']=np.empty((warmup*12,)+height.shape)
    arrays.update(monthly_temperature_c=np.tile(temperature,(output,1,1)),
                  monthly_precipitation_mm=np.tile(precipitation,(output,1,1)))
    for name in ('wind_x_m_s','wind_z_m_s'):
        if name in ca:
            arrays[name] = np.asarray(ca[name],np.float64).copy()
    ledgers = dict(spinup=[],output=[])
    weather_states = _weathering_states(materials,height.shape,area,land,initial_state)
    snow_max = np.zeros(n)
    snow_min_last = np.full(n,np.inf)
    output_index = 0
    for year in range(warmup + output):
        for month in range(12):
            before = float((soil.sum() + swe.sum()) * area / 1000.)
            days = int(MONTH_DAYS[month])
            t = temperature[month].ravel()
            rain = np.where(land.ravel(),precipitation[month].ravel(),0.)
            solid = np.where(t < snow_params.freezing_threshold_c,rain,0.)
            liquid_rain = rain - solid
            snow_available = swe + solid
            # Unit-depth adaptation of advance_snow_ice's melt-then-sublimation
            # equations; historical 900m² native reporting is not imported.
            melt = np.minimum(snow_available,snow_params.degree_day_melt_mm_per_day_c *
                              np.maximum(t - snow_params.min_melt_temperature_c,0.) * days)
            sublimation = np.minimum(snow_available - melt,snow_params.sublimation_demand_mm_per_day * days)
            swe = snow_available - melt - sublimation
            pet = temperature_index_pet_rate_mm_h(t)
            runoff_mm, et_mm = _constant_month_bucket(liquid_rain + melt,soil,pet,days*24,
                params.infiltration_capacity_mm_h,params.soil_capacity_mm,params.percolation_mm_h,
                params.fast_tau_s,params.slow_tau_s)
            local = runoff_mm.reshape(height.shape) * area / 1000.
            discharge = accumulate_graph(receiver,order,local) / (days * 86400.)
            wet = soil[0] / params.soil_capacity_mm
            # Existing weathering core debits finite bedrock and separately
            # credits dissolved and regolith solids. Parent is a subset of
            # regolith and is never counted again as another stock.
            weather = np.zeros(n)
            parent_solid = np.zeros(n)
            dissolved = 0.
            for block_index,start in enumerate(range(0,n,MAX_COLUMNS)):
                stop = min(start+MAX_COLUMNS,n)
                ws,flux = advance_weathering(weather_states[block_index],dt_s=days*86400.,
                    temperature_c=t[start:stop],moisture=wet[start:stop],bio_activity=0.,
                    parameters=cfg.get('weathering_parameters'))
                weather_states[block_index] = ws
                weather[start:stop] = flux['weathered_depth_m']
                parent_solid[start:stop] = flux['regolith_solid_m3']
                dissolved += float(flux['dissolved_solid_m3'].sum())
            weathered += weather
            soil_depth += parent_solid / area / (1. - porosity)
            cover = np.zeros(n)
            cover_class = np.zeros(n,np.uint8)
            for start in range(0,n,MAX_COLUMNS):
                stop = min(start+MAX_COLUMNS,n)
                suitability = assess_land_cover(parent_solid_m3=soil_depth[start:stop]*area*(1.-porosity[start:stop]),
                    porosity=porosity[start:stop],horizontal_area_m2=area,family_temperature_c=t[start:stop],
                    water_state_mm=soil[0,start:stop],water_capacity_reference_mm=np.full(stop-start,params.soil_capacity_mm),
                    hard_substrate=~land.ravel()[start:stop],status=dict(material='computed',water_state='computed',family_temperature='computed'))
                cover[start:stop] = suitability['suitability'] * land.ravel()[start:stop]
                cover_class[start:stop] = suitability['land_cover_index']
            after = float((soil.sum() + swe.sum()) * area / 1000.)
            ledger = dict(year=year,month=month+1,precipitation_m3=float(rain.sum()*area/1000.),
                actual_et_m3=float(et_mm.sum()*area/1000.),sublimation_m3=float(sublimation.sum()*area/1000.),
                local_runoff_m3=float(local.sum()),initial_storage_m3=before,final_storage_m3=after,
                weathered_rock_bulk_m3=float(weather.sum()*area),
                soil_regolith_solid_added_m3=float(parent_solid.sum()),dissolved_rock_solid_m3=dissolved)
            ledger['water_residual_m3'] = (ledger['precipitation_m3'] - ledger['actual_et_m3'] -
                ledger['sublimation_m3'] - ledger['local_runoff_m3'] + before - after)
            ledgers['spinup' if year < warmup else 'output'].append(ledger)
            if year<warmup:
                arrays['spinup_monthly_runoff_m3'][year*12+month]=local
            snow_max = np.maximum(snow_max,swe)
            if year >= warmup:
                snow_min_last = np.minimum(snow_min_last,swe)
                values = (local,discharge,soil[0],swe,et_mm,cover,melt,soil_depth,weather)
                for name,value in zip(names,values):
                    arrays[name][output_index] = np.asarray(value).reshape(height.shape)
                output_index += 1
    conditions = dict(
        snow=dict(status='computed',cells_accumulating=int((snow_max>0).sum()),
                  source='advance_snow_ice unit-depth equations; melt then sublimation'),
        weathering=dict(status='computed',source='terrain_pipeline.soil_water.advance; finite 1m weatherable bedrock, explicit dissolved/regolith split'),
        land_cover=dict(status='computed',source='terrain_pipeline.soil_water.assess_land_cover monthly suitability; not full ecosystem succession'),
        glacier=dict(status='pending-preparation' if np.any(snow_min_last>0) else 'not-triggered',
                     reason='persistent snow requires a supported flowline and ice geometry' if np.any(snow_min_last>0) else 'no persistent annual snow accumulation'),
        frozen_ground=dict(status='pending-preparation' if np.any(temperature[:,land]<0) else 'not-triggered',
                           reason='enthalpy column initial equilibrium and geothermal forcing required' if np.any(temperature[:,land]<0) else 'all land monthly air temperatures are above freezing'),
        aeolian=dict(status='pending-input',reason='finite mobile sand inventory and grain properties not supplied'),
        groundwater=dict(status='pending-input',reason=('explicit permeability available; aquifer thickness, head and boundary conditions required' if 'permeability_m2' in materials else 'explicit permeability, aquifer geometry and boundary heads required')),
        mass_wasting=dict(status='pending-input',reason='finite mobile regolith and slope stability inventory required'),
        coastal_exchange=dict(status='pending-input',reason='tidal/wave driver and coastal control volume required'),
        volcanism=dict(status='pending-geological-event',reason='seasonal magma supply must be handed over from a dated geological event'),
        disturbance=dict(status='pending-input',reason='dated disturbance driver not supplied'),
        soil_chemistry=dict(status='pending-input',reason='chemical species inventories and reactive boundary conditions required'),
        ecology=dict(status='pending-input',reason='suitability computed; ecological population/carbon inventories not supplied'))
    state = dict(soil_fast_slow_mm=soil.reshape((3,)+height.shape),snow_swe_mm=swe.reshape(height.shape),
                 soil_thickness_m=soil_depth.reshape(height.shape),weathered_rock_m=weathered.reshape(height.shape))
    weather_stock_names = ('bedrock_solid_m3','regolith_solid_m3','regolith_bulk_m3','parent_solid_m3',
        'dissolved_solid_m3','delivered_regolith_solid_m3','delivered_parent_solid_m3',
        'weatherable_thickness_m','area_m2','bed_hardness','solubility','initial_bedrock_solid_m3')
    state['weathering'] = {name:np.concatenate([ws[name] for ws in weather_states]) for name in weather_stock_names}
    arrays['land_cover_index'] = cover_class.reshape(height.shape)
    arrays.update(temperature_c=temperature.mean(axis=0), precipitation_mm_yr=precipitation.sum(axis=0),
                  soil_water_mm=arrays['monthly_soil_water_mm'][-1].copy(),
                  snow_swe_mm=arrays['monthly_snow_swe_mm'][-1].copy(),
                  cover_fraction=arrays['monthly_cover_fraction'][-1].copy())
    conditional = None
    if cfg.get('conditional_inputs') is not None:
        context = cfg.get('conditional_context')
        if context is None:
            raise ValueError('conditional process inputs require explicit bound world geometry')
        interval = cfg.get('conditional_dt_s')
        if interval is None:
            raise ValueError('conditional processes require their own explicit physical interval')
        conditional = run_conditional_processes(context,cfg['conditional_inputs'],dt_s=interval,
            initial_state=(initial_state or {}).get('conditional'))
        state['conditional'] = conditional['state']
        conditions.update(conditional['processes'])
    metadata = dict(algorithm=ALGORITHM,world_seed=world_seed,first_xz_m=list(first_xz_m),
        spacing_m=float(spacing_m),shape_zx=list(height.shape),spinup_years=warmup,output_years=output,
        months_completed=(warmup+output)*12,runoff_parameters=asdict(params),snow_parameters=snow_params.identity(),
        climate_identity=climate.get('metadata',{}).get('identity'),water_budget=ledgers,processes=conditions,
        runoff_semantics='local interval volume m3; discharge is one graph accumulation divided by physical month seconds',
        storage_semantics='soil/fast/slow plus snow water equivalent; output account excludes spinup',
        generation_time='not included: seasonal time is independent of equivalent shaping rounds',
        limitations=['channel/lake travel and storage are owned by water-process routing, not by the local soil bucket',
                     'conditional pending mechanisms have not modified terrain or silently supplied zeros',
                     'cover is climate/material suitability; no full ecological species simulation'])
    if conditional is not None:
        metadata['conditional_budgets'] = {name:result['ledger'] for name,result in conditional['results'].items()}
        metadata['conditional_interval_s'] = float(interval)
    identity_arrays = {**arrays,**{name:value for name,value in state.items() if name != 'weathering'}}
    identity_arrays.update({'weathering_'+name:value for name,value in state['weathering'].items()})
    identity_arrays.pop('conditional',None)
    if conditional is not None:
        for process, stocks in conditional['state'].items():
            for name,value in stocks.items():
                if isinstance(value,np.ndarray):
                    identity_arrays['conditional_'+process+'_'+name] = value
    metadata['identity'] = identity(identity_arrays,metadata)
    return dict(arrays=arrays,state=state,metadata=metadata,conditional=conditional)
