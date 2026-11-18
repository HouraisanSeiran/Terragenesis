"""Owned global seasonal inventories and strict restart binding.

Depths are water equivalent metres; chemistry and ecology stocks are kilograms.
The chemistry water field is a transaction view, never a second water inventory.
"""
from copy import deepcopy
import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.environment_processes import initialize_succession, initialize_habitat

SCHEMA = 'world-environment-state-v1'
ALGORITHM = 'world-seasonal-integrated-environment-v3'


def flatten_arrays(record, prefix=''):
    result = {}
    for name, value in record.items():
        key = prefix + name
        if isinstance(value, np.ndarray):
            result[key] = value
        elif isinstance(value, dict):
            result.update(flatten_arrays(value, key + '/'))
    return result


def binding(height, ocean, materials, climate, cfg, world_seed, first_xz_m, spacing_m):
    # Run length is scheduling, not a physical parameter. A one-year continuation
    # must have the same binding as a two-year uninterrupted calculation.
    parameters = {k:v for k,v in cfg.items() if k not in
                  ('spinup_years', 'output_years', 'integrated_environment')}
    if 'environment' in parameters:
        parameters['environment'] = {k:v for k,v in parameters['environment'].items()
            if k not in ('native_exchange','dated_events','output_fields','block_cells')}
    arrays = dict(height_m=height, ocean_mask=ocean,
                  **{'material/' + k:np.asarray(v) for k,v in materials.items()
                     if isinstance(v, (np.ndarray, int, float))})
    arrays.update({'climate/' + k:np.asarray(v) for k,v in climate.items()
                   if isinstance(v, np.ndarray)})
    return identity(arrays, dict(algorithm=ALGORITHM, schema=SCHEMA,
        parameters=parameters, world_seed=world_seed, first_xz_m=list(first_xz_m),
        spacing_m=float(spacing_m)))


def initialize(context, params, scenario, state_binding, initial_state=None):
    shape = context['height_m'].shape
    land = ~context['ocean_mask']
    area = context['spacing_m'] ** 2
    if initial_state is not None:
        saved = initial_state.get('integrated', {})
        if saved.get('schema') != SCHEMA or saved.get('binding') != state_binding:
            raise ValueError('integrated restart schema/source/terrain/config binding mismatch')
        result = deepcopy(saved)
        for name, value in flatten_arrays(result).items():
            if value.shape != shape or not np.isfinite(value).all():
                raise ValueError('invalid integrated restart field: ' + name)
            if not name.endswith('soil_temperature_c') and np.any(value < 0):
                raise ValueError('negative integrated inventory: ' + name)
        return result

    def stock(name, default):
        value = np.broadcast_to(np.asarray(scenario.get(name, default), float), shape).copy()
        if not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError('finite nonnegative initial inventory required: ' + name)
        return value * land

    zeros = lambda: np.zeros(shape)
    water = dict(root_liquid_m=stock('root_liquid_m', params.initial_soil_mm / 1000),
        fast_surface_m=stock('fast_surface_m', params.initial_fast_mm / 1000),
        groundwater_m3=stock('groundwater_depth_m', params.initial_slow_mm / 1000) * area,
        ground_ice_m=zeros(), snow_swe_m=zeros())
    thermal = dict(soil_temperature_c=zeros(), thaw_time_s=zeros(), frozen_time_s=zeros(),
                   absorbed_energy_j_m2=zeros())
    chemistry = dict(salt_dissolved_kg=stock('soil_salinity_kg_m3', .05) * water['root_liquid_m'] * area,
        salt_solid_kg=zeros(), organic_carbon_kg=stock('organic_carbon_kg_m2', 1.) * area,
        organic_nutrient_kg=stock('organic_nutrient_kg_m2', .02) * area,
        nutrient_kg=stock('mineral_nutrient_kg_m2', .01) * area)
    ecology = initialize_succession(context, biomass_carbon_kg_m2=scenario.get('biomass_carbon_kg_m2', .1))
    habitat = initialize_habitat(context, population_individuals=stock('habitat_population_m2', .00001) * area)
    return dict(schema=SCHEMA, binding=state_binding, elapsed_s=0., months_completed=0,
        water=water, thermal=thermal, chemistry=chemistry, succession=ecology, habitat=habitat,
        groundwater_solutes=dict(salt_kg=zeros(), nutrient_kg=zeros()),
        routed_exports=dict(salt_kg=zeros(), nutrient_kg=zeros()),
        queues=dict(litter_carbon_kg=zeros(), plant_nutrient_return_kg=zeros(),plant_nutrient_uptake_kg=zeros()),
        events=dict(consumed_ids=[], active={}), handoffs=dict(pending=[], consumed_ids=[]))


def water_total(state, area):
    water = state['water']
    return float(sum(water[k].sum() * area for k in
        ('root_liquid_m', 'fast_surface_m', 'ground_ice_m', 'snow_swe_m')) +
        water['groundwater_m3'].sum())
