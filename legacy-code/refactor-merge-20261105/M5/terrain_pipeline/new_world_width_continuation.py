"""Conservative short continuation of a solver-backed native width reach."""
import numpy as np
from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork, ChannelForcing, ChannelConfig
from terrain_pipeline.surface_rivers.metric_channel_solver import solve_channel
from terrain_pipeline.surface_rivers.metric_sediment import (MaterialParameters, SedimentDomain,
    SedimentForcing, SedimentConfig, solve_sediment)


def continue_width_reach(a, geometry_identity_sha256, *, duration_s=60.):
    """Carry committed stocks and saved water volume into rectangular new section."""
    n = len(a['receiver'])
    kinds = np.full(n, 'interior', dtype='U24'); kinds[-1] = 'open_outflow'
    network = ChannelNetwork(receiver=a['receiver'], length_m=a['length_m'], width_m=a['width_m'],
        bed_elevation_m=a['bed_m'], bed_slope=a['bed_slope'], roughness=np.full(n, .035),
        max_depth_m=a['max_depth_m'], terminal_kind=kinds, source_identity_sha256=geometry_identity_sha256,
        section_source='rectangular formative section, committed prior sediment', roughness_source='scenario Manning n=.035',
        receiver_distance_m=np.r_[a['length_m'][:-1], 0.])
    t0 = float(a['time_seconds'][-1])
    forcing = ChannelForcing(np.array([t0, t0+duration_s]), a['water_inflow_m3_s'][None,:], geometry_identity_sha256)
    water = solve_channel(network, forcing, a['storage_m3'], ChannelConfig(max_dt_seconds=1.))
    if water['metadata']['status'] != 'complete':
        raise ValueError('water continuation failed: ' + str(water['metadata']['failure_reason']))
    h = water['arrays']
    hydraulic_id = identity(h, water['metadata'])
    material = MaterialParameters(sediment_erodibility_m_s_pa=1e-8, rock_erodibility_m_s_pa=1e-10,
        settling_velocity_m_s=.0001, provenance='declared homogeneous finite sediment scenario')
    loose = a['sediment_trace_loose_solid_m3'][-1]
    mobile = a['sediment_trace_mobile_solid_m3'][-1]
    domain = SedimentDomain(network.receiver, network.length_m*network.width_m, network.width_m,
        network.bed_elevation_m, a['sediment_rock_floor_m'], loose/(1-material.porosity),
        np.zeros(n, dtype=bool), np.arange(n)==n-1, geometry_identity_sha256,
        'prior committed mobile and alluvium stocks, finite rock floor')
    external = np.zeros_like(h['outflow_q_m3_s']); external[:,0] = .00001
    sediment_forcing = SedimentForcing(h['time_seconds'], h['volume_m3'][:-1], h['depth_m'][:-1],
        h['outflow_q_m3_s'], np.broadcast_to(network.bed_slope, external.shape).copy(), external,
        hydraulic_id, geometry_identity_sha256, 'actual new-section water continuation')
    sediment = solve_sediment(domain, sediment_forcing, material, mobile, SedimentConfig(max_dt_seconds=1.))
    if sediment['metadata']['status'] != 'complete':
        raise ValueError('sediment continuation failed: ' + str(sediment['metadata']['failure_reason']))
    return water, sediment
