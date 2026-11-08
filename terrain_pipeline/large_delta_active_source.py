"""Active 30-day sediment delivery from retained mouth-5879 formation stock."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from terrain_pipeline.new_world_game_hydrology import IDENTITY
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment

FORMATION = Path('.scratch/large-delta-20261101/source-formation-v2')
OUTPUT = Path('.scratch/large-delta-20261101/active-source-v1')
SECONDS_PER_DAY = 86400
DAYS = 30
POROSITY = 0.4


def calculate(network, formation_stock, source_identity=IDENTITY):
    """Route retained solid once, with no hillslope transfer or external inflow."""
    receiver = np.asarray(network['receiver'], dtype=np.int64)
    n = receiver.size
    initial = np.asarray(formation_stock['channel_final_solid_m3'], dtype=np.float64)
    hillslope = np.asarray(formation_stock['hillslope_remaining_solid_m3'], dtype=np.float64)
    if initial.shape != (n,) or hillslope.shape != (n,) or np.any(initial < 0) or np.any(hillslope < 0):
        raise ValueError('invalid formation stocks')
    length = np.asarray(network['length_m'], dtype=np.float64)
    width = np.asarray(network['width_m'], dtype=np.float64)
    area = length * width
    bed = np.asarray(network['bed_m'], dtype=np.float64) + formation_stock['channel_bed_delta_m']
    bulk = initial / (1.0 - POROSITY)
    # An explicitly exhausted rock reserve; hardness=1 independently forbids rock erosion.
    floor = bed - bulk / area - 1e-9
    q = np.asarray(network['accumulated_q_m3_s'], dtype=np.float64)
    depth = np.asarray(network['depth_m'], dtype=np.float64)
    slope = np.asarray(network['slope'], dtype=np.float64)
    material = MaterialParameters(porosity=POROSITY, provenance='formation-v2 default homogeneous material')
    result = route_daily_sediment(
        receiver=receiver, length_m=length, width_m=width, bed_elevation_m=bed,
        water_depth_m=np.tile(depth, (DAYS, 1)), water_q_m3_s=np.tile(q, (DAYS, 1)),
        friction_slope=np.tile(slope, (DAYS, 1)), time_seconds=np.arange(DAYS + 1, dtype=np.float64) * SECONDS_PER_DAY,
        rock_floor_m=floor, initial_alluvium_bulk_m3=bulk, hardness=np.ones(n), material=material,
        geometry_identity_sha256=source_identity, hydraulic_identity_sha256=source_identity,
        material_provenance='retained formation-v2 scenario-2 channel stock; no hillslope transfer')
    a = result['arrays']
    if np.any(a['eroded_rock_m3']) or np.any(a['external_solid_m3']):
        raise ValueError('unexpected rock or external input')
    return a


def run():
    source = json.loads((FORMATION / 'manifest.json').read_text(encoding='utf8'))
    if source['identity'] != IDENTITY or source['mouth'] != 5879:
        raise ValueError('formation source identity or mouth mismatch')
    with np.load(FORMATION / 'reduced-network.npz', allow_pickle=False) as net_file, np.load(FORMATION / 'scenario-2.npz', allow_pickle=False) as stock_file:
        network = dict(net_file)
        stock = dict(stock_file)
    initial = stock['channel_final_solid_m3']
    hillslope = stock['hillslope_remaining_solid_m3']
    if not np.isclose(initial.sum(), source['scenarios']['2']['channel_final_solid_m3'], rtol=1e-12):
        raise ValueError('formation channel stock mismatch')
    if not np.isclose(hillslope.sum(), source['scenarios']['2']['hillslope_remaining_m3'], rtol=1e-12):
        raise ValueError('formation hillslope stock mismatch')
    a = calculate(network, stock)
    outlet = np.flatnonzero(network['receiver'] == -1)
    if len(outlet) != 1:
        raise ValueError('expected one outlet')
    q = float(network['accumulated_q_m3_s'][outlet[0]])
    if not np.isclose(q, source['outlet_q_m3_s'], rtol=1e-12):
        raise ValueError('formation outlet water mismatch')
    delivery = a['exported_solid_m3'].sum(axis=1)
    final_channel = a['trace_loose_solid_m3'][-1]
    final_mobile = a['trace_mobile_solid_m3'][-1]
    residual = float(initial.sum() - final_channel.sum() - final_mobile.sum() - delivery.sum())
    if abs(residual) > 1e-9 * max(1., float(initial.sum())):
        raise ValueError('active sediment budget mismatch')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(OUTPUT / 'forcing.npz', time_seconds=a['time_seconds'],
        interval_water_q_m3_s=np.full(DAYS, q), interval_water_m3=np.full(DAYS, q * SECONDS_PER_DAY),
        interval_delivered_solid_m3=delivery, interval_delivered_solid_m3_s=delivery / SECONDS_PER_DAY,
        native_node=network['native_node'], receiver=network['receiver'], reach_water_q_m3_s=network['accumulated_q_m3_s'],
        initial_channel_solid_m3=initial, final_channel_solid_m3=final_channel,
        initial_mobile_solid_m3=a['trace_mobile_solid_m3'][0], final_mobile_solid_m3=final_mobile,
        initial_hillslope_solid_m3=hillslope, final_hillslope_solid_m3=hillslope.copy(),
        channel_erosion_solid_m3=a['eroded_loose_solid_m3'], channel_deposition_solid_m3=a['deposited_solid_m3'],
        initial_channel_bed_m=a['trace_bed_m'][0], final_channel_bed_m=a['trace_bed_m'][-1])
    record = dict(schema='active-source-v1', source_identity=IDENTITY, source_formation=str(FORMATION),
        source_scenario='2 m cover, formation-v2 retained channel stock', mouth_index=5879,
        duration_seconds=DAYS * SECONDS_PER_DAY, interval_seconds=SECONDS_PER_DAY,
        known_local_outlet_water_q_m3_s=q, known_local_water_volume_m3=q * DAYS * SECONDS_PER_DAY,
        water_scenario='constant full-reservoir known-local runoff, no acceleration; not a calendar climate simulation',
        external_water='unknown; not included in known-local scenario', external_sediment='unknown; not included in known-local scenario',
        hillslope_transfer_solid_m3=0.0, rock_erosion_solid_m3=0.0,
        initial_channel_solid_m3=float(initial.sum()), final_channel_solid_m3=float(final_channel.sum()),
        initial_mobile_solid_m3=float(a['trace_mobile_solid_m3'][0].sum()), final_mobile_solid_m3=float(final_mobile.sum()),
        initial_hillslope_solid_m3=float(hillslope.sum()), final_hillslope_solid_m3=float(hillslope.sum()),
        delivered_solid_m3=float(delivery.sum()), residual_solid_m3=residual,
        formation_export_reused_m3=0.0, forcing_npz='forcing.npz', porosity=POROSITY,
        limitations='frozen reduced-network hydraulics and default sediment parameters inherited from formation-v2; no separate lake trapping')
    (OUTPUT / 'manifest.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    print(json.dumps(record, indent=2))
    return record


if __name__ == '__main__':
    run()
