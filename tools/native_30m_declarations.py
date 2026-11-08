"""Declarations derived from saved values, not an independent numerical audit."""
import numpy as np


def release_declarations(env):
    a, j = env['arrays'], env['json_records']
    event = a['event.npz']
    ej = j['event.json']
    dyn = env['dynamics']
    t = env['manifest']['parameters']['coupled_intervals']
    edges = event['time_edges_s']
    counts = a['reach_context.npz']['lateral_cell_counts']
    supply = event['local_q_m3_s'][:t, :1] * counts[None, :]
    forcing_window = [float(edges[0]), float(edges[-1])]
    coupled_window = [float(edges[0]), float(edges[t])]
    stage_scopes = {
        'terrain_surface': ('resolved original TD nodes only', 'source file/coordinate binding'),
        'd8_topology': ('complete upstream saved graph only', 'strict topology recomputation and propagated unknown'),
        'local_runoff': ('declared catchment and event only', 'active cells, bucket budget and event array identity'),
        'diagnostic_discharge': ('one declared interval, complete requested cells only', 'frozen product recomputation plus event binding'),
        'design_discharge': ('sampled section nodes; routed storm peak only', 'event routed peak and section Q binding'),
        'channel_section': ('sampled nodes; source-bed normal-depth approximation', 'section coordinate and geometry binding'),
        'hydraulics': ('bounded Manning at saved times, not backwater', 'child trace/state/forcing binding; independent saved-state audit'),
        'solid_inventory': ('sampled nodes at saved times; solid volume', 'inventory parent/child binding and independent three ledgers'),
        'bed_change': ('nodal bed only, PL mesh unchanged', 'parent/child binding and independent pointwise Exner'),
        'water_ledger': ('audit endpoint, not a spatial raster', 'independent raw trace water inventory and export'),
        'solid_ledger': ('audit endpoint, not a spatial raster', 'independent mobile/loose/rock ledgers'),
    }
    scopes = {key: {'status': 'computed_and_gated', 'range': limits, 'basis': basis}
              for key, (limits, basis) in stage_scopes.items()}
    for key in ('lake', 'backwater', 'floodplain_2d', 'natural_outlet', 'infinite_world'):
        scopes[key] = {'status': 'not_implemented', 'reason_code': 'stage_not_implemented'}
    params = ej['runoff_parameters']
    material = dyn['metadata']['material']
    sec = j['section.json']
    return {
        'schema': 'native-30m-finite-declarations-v1',
        'role': 'native_30m_diagnostic_bundle_unvalidated',
        'profile': 'full_finite_chain',
        'coordinates': {'array_order': '[z,x]', 'origin_order': '[x,z]', 'spacing_m': 30.0,
                        'world_meter_query_sampling': 'floor to native 30m node; not interpolated'},
        'time_binding': {'schema': 'nested-time-binding-v1', 'all_stages_share_one_window': False,
                         'forcing_window_seconds': forcing_window, 'runoff_window_seconds': forcing_window,
                         'design_q_window_seconds': forcing_window, 'coupled_window_seconds': coupled_window,
                         'coupled_covers_fraction_of_forcing': (edges[t]-edges[0])/(edges[-1]-edges[0]),
                         'unexecuted_remaining_coupled_seconds': float(edges[-1]-edges[t])},
        'design_q': {'semantics': 'declared_storm_event_reach_routed_peak',
                     'is_bankfull': False, 'used_for_dynamic_injection': False,
                     'value_m3_s': ej['design_q_m3_s'], 'interval_index': ej['design_q_interval_index'],
                     'instantaneous_event_peak_m3_s': float(event['instantaneous_terminal_q_m3_s'].max()),
                     'routed_event_peak_m3_s': float(event['routed_terminal_q_m3_s'].max()),
                     'peak_lag_seconds': float((event['routed_terminal_q_m3_s'].argmax()-
                                               event['instantaneous_terminal_q_m3_s'].argmax()) *
                                              env['manifest']['parameters']['dt_s'])},
        'nodal_local_supply': {'source': 'original_soil_bucket_local_q', 'unit': 'm3/s',
                               'time_edges_seconds': edges[:t+1].tolist(),
                               'q_m3_s': supply.tolist(),
                               'volumes_m3': (supply*np.diff(edges[:t+1])[:, None]).tolist(),
                               'event_identity_sha256': ej['event_identity'],
                               'attribution': 'uniform per-cell runoff times topology-verified exclusive lateral counts'},
        'geometry': {'normal_depth_slope_state': 'source_bed',
                     'dynamic_hydraulics_slope_state': 'interval_start_updated_nodal_bed; terminal slope held initial',
                     'hydraulic_depth_is_uniform_flow_approximation': True,
                     'depth_is_hydraulic_not_geometric': True, 'dynamic_PL_mesh_updated': False,
                     'resample_stride': sec['actual_stride'],
                     'carved_length_m': sec['sampled_stem_length_m'], 'full_stem_length_m': sec['full_stem_length_m'],
                     'length_difference_is_sampled_chord_not_missing_river': True},
        'declared_defaults': {'calibration_status': 'declared_uncalibrated',
                              'computation': env['manifest']['parameters'], 'runoff': params,
                              'section': sec['actual_parameters'], 'material': material,
                              'initial_alluvium_depth_m_by_node':
                                  (a['reach_context.npz']['initial_alluvium_bulk_m3']/dyn['arrays']['material_area_m2']).tolist(),
                              'dynamic_channel': dyn['metadata']['water_0']['metadata']['config'],
                              'dynamic_sediment': dyn['metadata']['sediment_0']['metadata']['config']},
        'bed_change_magnitude_validated': False,
        'capability_scopes': scopes,
        'certification': {
            'hydraulic_ready': {'value': False, 'reason': 'bounded Manning ran; no backwater/floodplain or magnitude certification'},
            'natural_outlet_verified': {'value': False, 'reason': 'declared interior downstream model boundary is not a natural outlet'},
            'publishable': {'value': False, 'reason': 'finite experimental algorithm product; not certified default infinite-world content'}},
    }
