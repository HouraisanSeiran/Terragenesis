"""Explicit-input dispatch of existing bounded environmental process kernels.

The caller owns stocks, geometry and interval forcing. Missing prerequisites
remain unprepared; the dispatcher never initializes an unspecified inventory
or manufactures an external driver. No terrain changes are applied twice.
"""
from __future__ import annotations

import copy
import numpy as np

from terrain_pipeline import environment_processes as kernels


# These fields intentionally include inputs for which historical kernels have
# convenient defaults. World generation requires an explicit physical source.
CONTRACTS = {
    'radiation': ('radiation', ('absorbed_energy_j_m2',), ('latitude_deg', 'longitude_deg', 'time_s', 'albedo')),
    'frozen_ground': ('frozen_ground', ('soil_temperature_c', 'liquid_water_m', 'ground_ice_m', 'snow_swe_m', 'thaw_time_s', 'frozen_time_s'),
                      ('air_temperature_c', 'ground_heat_w_m2', 'geothermal_heat_w_m2')),
    'aeolian': ('aeolian', ('loose_solid_m3', 'airborne_solid_m3'),
                ('wind_x_m_s', 'wind_z_m_s', 'water_saturation', 'vegetation_cover')),
    'groundwater': ('groundwater', ('groundwater_water_m3', 'surface_water_m3'),
                   ('specific_yield', 'aquifer_base_m', 'recharge_m3', 'lateral_conductance_m2_s', 'surface_stage_m', 'surface_conductance_m2_s')),
    'mass_wasting': ('mass', kernels.WEATHER_FIELDS + kernels.STOCKS + ('regolith_porosity',),
                     ('temperature_c', 'moisture', 'transport_fraction_per_s', 'repose_angle_deg', 'root_cohesion_pa')),
    'coastal_exchange': ('coastal_exchange', ('water_m3', 'salt_kg', 'bed_solid_m3', 'bed_m', 'time_s'),
                         ('mean_sea_level_m', 'tide_amplitude_m', 'tide_period_s', 'tide_phase_rad',
                          'wave_height_m', 'wave_direction_xz', 'ocean_salinity_kg_m3',
                          'mouth_mask', 'river_boundary_water_m3_s', 'river_boundary_solid_m3_s')),
    'volcanism': ('volcanism', ('mobile_lava_m3', 'lava_heat_j', 'airborne_ash_m3', 'deposited_lava_m3', 'deposited_ash_m3'),
                  ('lava_input_m3', 'ash_input_m3', 'wind_x_m_s', 'wind_z_m_s', 'geothermal_w_m2')),
    'soil_chemistry': ('soil_chemistry', ('water_m3','salt_dissolved_kg','salt_solid_kg','organic_carbon_kg','organic_nutrient_kg','nutrient_kg'),
                       ('water_input_m3_s','inflow_salinity_kg_m3','drainage_m3_s','evaporation_m3_s','litter_carbon_kg',
                        'nutrient_input_kg_s','litter_nutrient_kg','plant_nutrient_return_kg','plant_uptake_demand_kg')),
    'ecology': ('succession', ('biomass_carbon_kg','dead_carbon_kg','char_carbon_kg','plant_nutrient_kg','age_s','disturbance_fraction'),
                ('fire_hazard_s','disturbance_hazard_s','plant_stress_factor','water_available_fraction','temperature_c','plant_nutrient_uptake_kg')),
    'habitat': ('habitat', ('population_individuals','occupancy_s'),
                ('vegetation_cover_fraction','water_available_fraction','disturbance_fraction','water_temperature_c')),
}


def run_conditional_processes(context, inputs, *, dt_s, initial_state=None):
    """Run supported prepared processes using fixed physical interval work.

    ``inputs[name]`` contains ``state`` (or persisted ``initial_state[name]``),
    ``forcing``, ``source_identity`` and optional ``parameters``. A dated
    geological ``event_identity`` is additionally mandatory for volcanism.
    Results return each stock, flux, budget and kernel identity unmodified.
    ``height_change_m`` is a proposed single-use contribution, never silently
    added to the supplied context. Detailed preparation owns its replacement.
    """
    if not np.isfinite(dt_s) or dt_s <= 0:
        raise ValueError('positive finite physical conditional interval required')
    unknown = set(inputs or {}) - set(CONTRACTS) - {'glacier'}
    if unknown:
        raise ValueError('unknown conditional processes: ' + ', '.join(sorted(unknown)))
    results, statuses, states = {}, {}, {}
    previous = initial_state or {}
    for name, (registry_name, stock_names, forcing_names) in CONTRACTS.items():
        supplied = (inputs or {}).get(name)
        if supplied is None:
            statuses[name] = dict(status='pending-input', reason='prepared stock, forcing and source binding not supplied')
            continue
        if not isinstance(supplied, dict):
            raise ValueError('conditional input must be a mapping: ' + name)
        if supplied.get('status') == 'not-triggered':
            if not supplied.get('reason'):
                raise ValueError('untriggered process requires a causal reason')
            statuses[name] = dict(status='not-triggered', reason=supplied['reason'])
            continue
        state = previous.get(name, supplied.get('state'))
        forcing = supplied.get('forcing')
        missing = []
        if state is None:
            missing.append('finite initial stock')
        elif any(key not in state for key in stock_names):
            missing.extend('state.' + key for key in stock_names if key not in state)
        if forcing is None:
            missing.append('physical forcing')
        elif any(key not in forcing for key in forcing_names):
            missing.extend('forcing.' + key for key in forcing_names if key not in forcing)
        if not supplied.get('source_identity'):
            missing.append('source_identity')
        if name == 'volcanism' and not supplied.get('event_identity'):
            missing.append('dated geological event_identity')
        if name == 'groundwater' and not supplied.get('permeability_source'):
            missing.append('explicit permeability_source')
        if name == 'aeolian' and not supplied.get('grain_provenance'):
            missing.append('explicit mobile grain_provenance')
        if name in ('soil_chemistry', 'ecology', 'habitat') and not supplied.get('inventory_provenance'):
            missing.append('chemical/biological inventory_provenance')
        if missing:
            statuses[name] = dict(status='pending-input', reason='missing ' + ', '.join(missing))
            continue
        # Never let a kernel partially mutate a caller's stored accounts when
        # a later input validation fails.
        _, advance, accepts_parameters = kernels._PROCESS_FUNCTIONS[registry_name]
        arguments = (copy.deepcopy(state), forcing, context, dt_s)
        if accepts_parameters:
            result = advance(*arguments, parameters=supplied.get('parameters'))
        else:
            if supplied.get('parameters'):
                raise ValueError('this kernel accepts parameters in its explicit forcing: ' + name)
            result = advance(*arguments)
        results[name] = result
        states[name] = result['state']
        statuses[name] = dict(status='computed', source_identity=supplied['source_identity'],
                              event_identity=supplied.get('event_identity'), metadata=result['metadata'])
    if (inputs or {}).get('glacier') is not None:
        glacier_input = dict(inputs['glacier'])
        glacier_input.update(previous.get('glacier',{}))
        glacier = advance_native_glacier(glacier_input)
        statuses['glacier'] = glacier['process']
        if glacier.get('result') is not None:
            results['glacier'] = glacier['result']
            states['glacier'] = dict(thickness_start_m=glacier['result']['arrays']['thickness_edge_m'][-1].copy())
    return dict(results=results, state=states, processes=statuses,
                semantics='stocks and fluxes already balanced by each existing kernel; terrain proposals require one explicit owner')


def advance_native_glacier(supplied):
    """Bind the unchanged bounded ice core to its actual native support.

    Its historical cell account is 900 m². Explicitly reject a world-scale
    flowline instead of treating those native volumes as 2 km volumes.
    """
    required = ('source_identity','thickness_start_m','bed_m','accumulation_mm',
                'ablation_mm','time_edges_s','x_m','width_m','bedrock_erodible_m3','land_port_mask')
    missing = [name for name in required if name not in supplied]
    if missing:
        return dict(process=dict(status='pending-input',reason='missing ' + ', '.join(missing)))
    x = np.asarray(supplied['x_m'],np.float64)
    if x.ndim != 1 or not 3 <= x.size <= 9 or not np.allclose(np.diff(x),30.,rtol=0,atol=1e-9) or supplied['width_m'] != 30.:
        return dict(process=dict(status='unsupported-scale',
            reason='existing glacier core requires a 3..9 cell native 30m by 30m flowline; world coarse geometry cannot reuse its fixed 900m2 inventory'))
    accumulation = np.asarray(supplied['accumulation_mm'],np.float64)
    if not np.isfinite(accumulation).all() or np.any(accumulation < 0):
        raise ValueError('finite nonnegative glacier accumulation required')
    if not np.any(accumulation > 0) and not np.any(np.asarray(supplied['thickness_start_m']) > 0):
        return dict(process=dict(status='not-triggered',reason='no accumulation or initial ice stock'))
    kwargs = {key:supplied[key] for key in required if key != 'source_identity'}
    if 'parameters' in supplied:
        kwargs['parameters'] = kernels.GlacierParameters(**supplied['parameters'])
    result = kernels.advance_glacier(**kwargs)
    return dict(result=result,process=dict(status='computed',source_identity=supplied['source_identity'],
        algorithm=result['metadata']['algorithm'],semantics='native ice/water/rock stocks separate; erosion is an explicitly declared finite proxy'))
