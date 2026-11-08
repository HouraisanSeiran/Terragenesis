"""Build a bounded saved-native-reach width experiment from existing products.

The sediment solve uses the old section; its committed interval exchange updates
one subsequent section. Neither the original network nor its sediment is mutated.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_rivers.formative_section import formative_section, section_from_routed_budget
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment
from terrain_pipeline.geology import sample_lithology_points


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def select_saved_reach(edges, status, bed, q, *, minimum_nodes=60):
    """Choose the highest-Q upstream start with >= minimum bounded river nodes."""
    edges = np.asarray(edges)
    good = ((status == 0) & (bed[edges[:, 0]] > bed[edges[:, 1]] + 1e-8)
            & (q[edges[:, 0]] > 0) & (q[edges[:, 1]] >= q[edges[:, 0]]))
    receiver = {int(a): int(b) for a, b in edges[good]}
    best = None
    for start in receiver:
        path = []
        seen = set()
        node = start
        while node in receiver and node not in seen:
            path.append(node)
            seen.add(node)
            node = receiver[node]
        if node in seen:
            continue
        path.append(node)
        if len(path) >= minimum_nodes and (best is None or (q[start], len(path)) > (q[best[0]], len(best))):
            best = path
    if best is None:
        raise ValueError('no qualifying bounded native network reach')
    return np.asarray(best, dtype=np.int64)


def _normal_depth(q, width, slope, roughness):
    def discharge(depth):
        area = width * depth
        return area * (area / (width + 2 * depth)) ** (2 / 3) * slope ** .5 / roughness
    upper = 1.
    while discharge(upper) < q:
        upper *= 2.
    return brentq(lambda h: discharge(h) - q, 0., upper)


def construct_saved_width_reach(root, *, minimum_nodes=60):
    """Return arrays and metadata for a saved TD/native-event connected reach.

    Saved interval-2 Q is a fixed formative scenario, not historical bankfull.
    Homogeneous sediment stocks and inlet supply are explicit scenarios. The
    sediment replay uses baseline sections and frozen, normal-flow hydraulics.
    """
    root = Path(root)
    network_dir = root / 'native-network-v4'
    event_dir = root / 'native-event-v3'
    names = ('node_id', 'node_xz_m', 'node_bed_m', 'node_raw_bed_m', 'node_q_m3_s', 'edge_nodes', 'edge_status')
    data = {name: np.load(network_dir / (name + '.npy'), mmap_mode='r') for name in names}
    manifest = json.loads((network_dir / 'manifest.json').read_text(encoding='utf8'))
    event_manifest = json.loads((event_dir / 'manifest.json').read_text(encoding='utf8'))
    if manifest['source_identity'] != event_manifest['source_identity']:
        raise ValueError('terrain/event identities differ')
    selected = select_saved_reach(data['edge_nodes'], data['edge_status'], data['node_bed_m'], data['node_q_m3_s'], minimum_nodes=minimum_nodes)
    xz = np.asarray(data['node_xz_m'][selected], dtype=np.float64)
    bed = np.asarray(data['node_bed_m'][selected], dtype=np.float64)
    raw = np.asarray(data['node_raw_bed_m'][selected], dtype=np.float64)
    q = np.asarray(data['node_q_m3_s'][selected], dtype=np.float64)
    n = len(selected)
    distance = np.linalg.norm(np.diff(xz, axis=0), axis=1)
    length = np.r_[distance, distance[-1]]
    slope = np.r_[(bed[:-1] - bed[1:]) / distance, (bed[-2] - bed[-1]) / distance[-1]]
    receiver = np.r_[np.arange(1, n, dtype=np.int64), np.int64(-1)]
    lith = sample_lithology_points(xz[:, 0], xz[:, 1], world_seed=20261020)
    bh, bank = lith['bed_hardness'], lith['bank_hardness']
    # Fracture already contributed to the sampled resistance. Cohesion is an
    # explicit bank-material scenario, not an observed TD lithology property.
    baseline = formative_section(q, bh, bank, 0., .25, max_width_m=300.)
    roughness = .035
    old_depth = np.array([_normal_depth(qi, wi, si, roughness) for qi, wi, si in zip(q, baseline.width_m, slope)])
    time = np.asarray(np.load(root / 'native-event-v1' / 'time_seconds.npy'), dtype=np.float64)[1:3]
    event_flow = np.load(event_dir / 'node_water_m3.npy', mmap_mode='r')
    event_q = np.asarray(event_flow[1, data['node_id'][selected]], dtype=np.float64) / (time[1] - time[0])
    if not np.allclose(q, event_q, rtol=1e-12, atol=0.):
        raise ValueError('saved network Q differs from native event interval')
    scenario = dict(initial_alluvium_bulk_depth_m=.015, rock_reserve_depth_m=.5,
                    external_inlet_solid_m3_s=.00001, initial_mobile_solid_m3=0.,
                    bank_cohesion=.25, manning_n=roughness)
    alluvium = baseline.width_m * length * scenario['initial_alluvium_bulk_depth_m']
    rock_floor = bed - scenario['initial_alluvium_bulk_depth_m'] - scenario['rock_reserve_depth_m']
    external = np.zeros((1, n), dtype=np.float64)
    external[0, 0] = scenario['external_inlet_solid_m3_s']
    forcing_id = identity({'time_seconds': time, 'q_m3_s': q}, {'source': manifest['source_identity'], 'kind': 'saved-network-interval-2-formative-scenario'})
    geom_id = identity({'xz_m': xz, 'bed_m': bed, 'width_m': baseline.width_m}, {'source': manifest['source_identity']})
    material = MaterialParameters(sediment_erodibility_m_s_pa=1e-8, rock_erodibility_m_s_pa=1e-10,
        settling_velocity_m_s=.0001, provenance='declared homogeneous finite sediment scenario')
    routed = route_daily_sediment(receiver=receiver, length_m=length, width_m=baseline.width_m,
        bed_elevation_m=bed, water_depth_m=old_depth[None, :], water_q_m3_s=q[None, :],
        friction_slope=slope[None, :], time_seconds=time, rock_floor_m=rock_floor,
        initial_alluvium_bulk_m3=alluvium, hardness=bh, material=material,
        external_solid_m3_s=external, initial_mobile_solid_m3=np.zeros(n),
        geometry_identity_sha256=geom_id, hydraulic_identity_sha256=forcing_id,
        material_provenance=material.provenance)
    s = routed['arrays']
    section = section_from_routed_budget(q, bh, bank, 0., .25,
        incoming_solid_m3=s['incoming_solid_m3'][0], external_solid_m3=s['external_solid_m3'][0],
        capacity_solid_m3=s['capacity_solid_m3'][0], eroded_loose_solid_m3=s['eroded_loose_solid_m3'][0],
        eroded_rock_m3=s['eroded_rock_m3'][0], deposited_solid_m3=s['deposited_solid_m3'][0],
        initial_mobile_solid_m3=s['initial_mobile_solid_m3'], max_width_m=300.)
    final_bed = s['trace_bed_m'][-1].copy()
    final_slope = np.r_[(final_bed[:-1] - final_bed[1:]) / distance,
                        (final_bed[-2] - final_bed[-1]) / distance[-1]]
    if np.any(final_slope <= 0.) or np.any(final_bed > raw):
        raise ValueError('sediment replay requires a new bounded bed reconciliation')
    depth = np.array([_normal_depth(qi, wi, si, roughness) for qi, wi, si in zip(q, section.width_m, final_slope)])
    # Rectangular storage is the existing ChannelNetwork hydraulic approximation.
    # Its top width equals the analytic trapezoid incision top width.
    final_id = identity({'xz_m': xz, 'bed_m': final_bed, 'width_m': section.width_m}, {'source': manifest['source_identity'], 'sediment': routed['identity_sha256']})
    kinds = np.full(n, 'interior', dtype='U24'); kinds[-1] = 'open_outflow'
    channel = ChannelNetwork(receiver=receiver, length_m=length, width_m=np.asarray(section.width_m),
        bed_elevation_m=final_bed, bed_slope=final_slope, roughness=np.full(n, roughness),
        max_depth_m=np.maximum(depth * 2., 1.), terminal_kind=kinds,
        source_identity_sha256=final_id, section_source='lagged routed formative width',
        roughness_source='declared Manning scenario', receiver_distance_m=np.r_[distance, 0.])
    water_lateral = np.r_[q[0], np.diff(q)]
    arrays = dict(node_id=np.asarray(data['node_id'][selected]), network_index=selected, xz_m=xz,
        receiver=receiver, length_m=length, raw_td_m=raw, baseline_bed_m=bed, bed_m=final_bed, formative_q_m3_s=q,
        water_inflow_m3_s=water_lateral, bed_slope=final_slope, bed_resistance=bh, bank_resistance=bank,
        baseline_width_m=baseline.width_m, width_m=channel.width_m, baseline_depth_m=old_depth,
        water_depth_m=depth, storage_m3=channel.width_m * channel.length_m * depth,
        max_depth_m=channel.max_depth_m, time_seconds=time,
        **{'sediment_' + k: v for k, v in s.items()})
    sources = {name: file_sha256(network_dir / (name + '.npy')) for name in names}
    sources.update(network_manifest=file_sha256(network_dir / 'manifest.json'),
                   event_manifest=file_sha256(event_dir / 'manifest.json'),
                   event_water=file_sha256(event_dir / 'node_water_m3.npy'),
                   terrain_manifest=file_sha256(root / 'terrain-v3' / 'manifest.json'),
                   event_time=file_sha256(root / 'native-event-v1' / 'time_seconds.npy'))
    metadata = dict(schema='native-formative-width-reach-v1', terrain_identity=manifest['source_identity'],
        world_seed=20261020, source_file_sha256=sources, source_network=str(network_dir),
        source_event=str(event_dir), baseline_geometry_sha256=geom_id,
        formative_flow_sha256=forcing_id, sediment_sha256=routed['identity_sha256'],
        final_geometry_sha256=final_id, scenario=scenario, sediment_metadata=routed['metadata'],
        water_policy='saved interval-2 Q held as formative flow; incoming plus nonnegative incremental tributary flow equals node Q; outside headwater unknown, assigned scenario boundary',
        history='historical climate and bankfull recurrence unknown',
        sediment_policy='finite replay on baseline geometry; committed final bed and interval exchange update next geometry once',
        storage_policy='rectangular Manning storage; width equals incision top width; trapezoid incision is not the same cross-sectional area',
        depth_policy='normal depth from fixed Q, width, slope and scenario Manning n; not observed seasonal water level')
    return {'arrays': arrays, 'metadata': metadata, 'identity_sha256': identity(arrays, metadata)}

