"""Dispatch explicitly prepared environmental regions into existing kernels.

No inventories, boundary heads, tides or material species are manufactured here.
Regions retain independent accounts; their deltas are proposals for the world
replacement publisher, never implicitly added to an already processed coarse bed.
"""
from __future__ import annotations

import numpy as np

from terrain_pipeline import environment_processes as processes
from terrain_pipeline.common_infra import identity

CONTRACTS = {
    'aeolian': (processes.aeolian_step,('loose_solid_m3','airborne_solid_m3'),
        ('wind_x_m_s','wind_z_m_s','water_saturation','vegetation_cover'), ('height_m','spacing_m','ocean_mask')),
    'frozen_ground': (processes.frozen_ground_step,('liquid_water_m','ground_ice_m','soil_temperature_c','snow_swe_m','thaw_time_s','frozen_time_s'),
        ('air_temperature_c','ground_heat_w_m2','geothermal_heat_w_m2'),('height_m','spacing_m','ocean_mask')),
    'groundwater': (processes.groundwater_step,('groundwater_water_m3','surface_water_m3'),
        ('specific_yield','aquifer_base_m','recharge_m3','surface_input_m3','lateral_conductance_m2_s',
         'surface_stage_m','surface_conductance_m2_s','pumping_request_m3'),
        ('height_m','spacing_m','world_seed','origin_native_xz','valid_mask','protected_mask','ocean_mask','river_mask','receiver')),
    'mass_wasting': (processes.mass_step,(*processes.WEATHER_FIELDS,*processes.STOCKS,'regolith_porosity'),
        ('temperature_c','moisture','bio_activity','soil_request_solid_m3','transport_fraction_per_s','repose_angle_deg','root_cohesion_pa'),
        ('height_m','spacing_m','world_seed','origin_native_xz','valid_mask','protected_mask','ocean_mask','river_mask','receiver')),
    'coastal_exchange': (processes.advance_coastal_exchange,('water_m3','salt_kg','bed_solid_m3','bed_m','time_s'),
        ('sea_level_m','ocean_salinity_kg_m3','mouth_mask','river_water_m3_s','river_sediment_solid_m3_s','wave_exchange_fraction'),
        ('height_m','spacing_m','world_seed','origin_native_xz','valid_mask','protected_mask','ocean_mask','receiver')),
    'volcanism': (processes.volcanism_step,('mobile_lava_m3','lava_heat_j','airborne_ash_m3','deposited_lava_m3','deposited_ash_m3'),
        ('magma_input_m3_s','ash_input_m3_s','magma_temperature_c','wind_x_m_s','wind_z_m_s','geothermal_w_m2'),
        ('height_m','spacing_m','ocean_mask','receiver')),
    'soil_chemistry': (processes.advance_soil_chemistry,('water_m3','salt_dissolved_kg','salt_solid_kg','organic_carbon_kg','organic_nutrient_kg','nutrient_kg'),
        ('water_input_m3_s','inflow_salinity_kg_m3','water_output_m3_s','temperature_c'),
        ('height_m','spacing_m','world_seed','origin_native_xz','valid_mask','protected_mask','ocean_mask','receiver')),
    'ecology': (processes.advance_succession,('biomass_carbon_kg','dead_carbon_kg'),
        ('vegetation_suitability','water_stress','temperature_c','disturbance_fraction'),
        ('height_m','spacing_m','world_seed','origin_native_xz','valid_mask','protected_mask','ocean_mask','receiver')),
}


def dispatch_prepared_regions(regions, *, expected_source_identity=None):
    """Advance exact explicit intervals for supported, source-bound regions.

    A record has id, kind, source_identity, context, state, and intervals. Each
    interval has dt_s and forcing; callers must prepare all required fields.
    Repeated IDs are rejected before any solver executes. Region state/ledgers
    are returned separately so publication can replace matching coarse support.
    """
    records = list(regions or [])
    ids = [record.get('id') for record in records]
    if any(not isinstance(value,str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError('unique nonempty environmental region IDs required')
    prepared = []
    for record in sorted(records,key=lambda row:row['id']):
        kind = record.get('kind')
        if kind not in CONTRACTS:
            prepared.append(dict(id=record['id'],kind=kind,status='unsupported',reason='no general prepared-region adapter for this mechanism'))
            continue
        solver,state_fields,forcing_fields,context_fields = CONTRACTS[kind]
        source = record.get('source_identity')
        if not isinstance(source,str) or not source or (expected_source_identity is not None and source != expected_source_identity):
            raise ValueError('environment region source identity mismatch')
        state,context = record.get('state',{}),record.get('context',{})
        intervals = record.get('intervals',[])
        missing = ['state/'+name for name in state_fields if name not in state]
        missing += ['context/'+name for name in context_fields if name not in context]
        if not intervals:
            missing.append('intervals')
        for index,interval in enumerate(intervals):
            missing += ['interval/%d/forcing/%s'%(index,name) for name in forcing_fields if name not in interval.get('forcing',{})]
            dt = interval.get('dt_s')
            if isinstance(dt,bool) or not isinstance(dt,(int,float)) or not np.isfinite(dt) or dt <= 0:
                missing.append('interval/%d/positive_dt_s'%index)
        if kind == 'volcanism' and not record.get('geological_event_id'):
            missing.append('geological_event_id')
        if missing:
            prepared.append(dict(id=record['id'],kind=kind,status='pending-input',missing=missing))
            continue
        if np.asarray(context['height_m']).size > 262144:
            prepared.append(dict(id=record['id'],kind=kind,status='pending-resource',reason='existing environmental kernel maximum is 262144 cells'))
            continue
        prepared.append((record,solver))
    result = []
    for entry in prepared:
        if isinstance(entry,dict):
            result.append(entry)
            continue
        record,solver = entry
        state = {name:np.array(value,copy=True) for name,value in record['state'].items()}
        ledger = []
        fluxes = []
        for interval in record['intervals']:
            kwargs = {}
            if record['kind'] in ('aeolian','frozen_ground','volcanism'):
                kwargs['parameters'] = record.get('parameters')
            output = solver(state,interval['forcing'],record['context'],interval['dt_s'],**kwargs)
            state = output['state']
            ledger.append(output.get('ledger',{}))
            fluxes.append(output.get('fluxes',{}))
        arrays = {name:np.asarray(value) for name,value in state.items()}
        metadata = dict(id=record['id'],kind=record['kind'],status='computed',
            source_identity=record['source_identity'],intervals_completed=len(record['intervals']),
            physical_seconds=sum(float(row['dt_s']) for row in record['intervals']),
            ledger=ledger,solver=output.get('metadata',{}),
            replacement='unpublished regional proposal; replace matching coarse account on explicit publication, never additive replay')
        metadata['identity'] = identity(arrays,metadata)
        result.append(dict(**metadata,state=state,fluxes=fluxes))
    return result
