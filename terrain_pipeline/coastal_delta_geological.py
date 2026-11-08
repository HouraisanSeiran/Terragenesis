"""Finite-volume, coarse geological sediment spreading on a MarineState.

Transport sweeps are numerical redistribution iterations, not physical seconds.
The inundation and deposition levels represent a prescribed formative flood
stage; they are not a hydraulic solution or a generated river network.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import math
import numpy as np

from .coastal_delta_product import load_checkpoint, save_checkpoint

SECONDS_PER_YEAR = 365.25 * 86400.


@dataclass(frozen=True)
class GeologicalConfig:
    inlet_zx: tuple
    water_stage_m: float = 2.
    deposit_ceiling_m: float = 1.
    settling_fraction: float = .01
    mobility_fraction: float = .8
    solid_rate_m3_s: float = 20.
    water_rate_m3_s: float = 15000.
    ceiling_slope_m_per_m: float = 0.
    minimum_ceiling_m: float = 0.


def _mask_identity(mask):
    return hashlib.sha256(np.ascontiguousarray(mask, dtype=np.uint8).tobytes()).hexdigest()


def start(state, config, *, ocean_mask):
    """Start an explicitly assumed boundary on an existing marine inventory."""
    c = config
    nums = (c.water_stage_m, c.deposit_ceiling_m, c.settling_fraction,
            c.mobility_fraction, c.solid_rate_m3_s, c.water_rate_m3_s,
            c.ceiling_slope_m_per_m, c.minimum_ceiling_m)
    if (not all(math.isfinite(x) for x in nums) or c.water_stage_m <= c.deposit_ceiling_m
            or not 0 <= c.settling_fraction <= 1 or not 0 < c.mobility_fraction <= 1
            or c.solid_rate_m3_s < 0 or c.water_rate_m3_s <= 0
            or c.ceiling_slope_m_per_m < 0 or c.minimum_ceiling_m > c.deposit_ceiling_m):
        raise ValueError('invalid geological forcing')
    r, col = c.inlet_zx
    if not (0 <= r < state.bed_m.shape[0] and 0 <= col < state.bed_m.shape[1]) or not state.valid_mask[r, col]:
        raise ValueError('invalid inlet')
    ocean_mask = np.asarray(ocean_mask, bool)
    if ocean_mask.shape != state.base_bed_m.shape or not ocean_mask[r, col]:
        raise ValueError('invalid source ocean')
    config_data = asdict(c)
    config_data['inlet_zx'] = list(c.inlet_zx)
    return {'algorithm': 'connected-formative-irregular-distance-v2', 'source_identity': state.source_identity,
            'ocean_mask_sha256': _mask_identity(ocean_mask),
            'config': config_data, 'years': 0., 'supply_solid_m3': 0., 'inputs': []}


def advance(state, progress, years, *, input_id, ocean_mask, sweeps):
    """Add finite external supply and move it through connected inundated cells.

    Original ocean cells are the only deposition/transport domain: unknown and
    pre-existing land are not filled. Every sweep first deposits a fraction up
    to local accommodation, then shares mobile stock with wet face neighbours.
    No stock leaves the domain in this closed-boundary approximation. Previously
    mobile sediment participates; the geological clock is separate from time_s.
    """
    if (progress.get('algorithm') != 'connected-formative-irregular-distance-v2'
            or progress.get('event_finalized') or any(p.get('record_kind') == 'geological_event_finalization' for p in state.consumed_packets)
            or progress['source_identity'] != state.source_identity or not input_id
            or input_id in progress['inputs'] or any(p['input_id'] == input_id for p in state.consumed_packets)
            or not math.isfinite(years) or years <= 0 or not isinstance(sweeps, int) or sweeps < 1):
        raise ValueError('invalid or duplicate geological input')
    c = GeologicalConfig(**progress['config'])
    ocean_mask = np.asarray(ocean_mask, bool)
    if _mask_identity(ocean_mask) != progress['ocean_mask_sha256']:
        raise ValueError('source ocean identity mismatch')
    domain = ocean_mask & state.valid_mask
    if domain.shape != state.base_bed_m.shape or not domain[tuple(c.inlet_zx)]:
        raise ValueError('inlet must be in the source ocean')
    stock = state.bed_solid_m3.copy()
    mobile = state.mobile_solid_m3.copy()
    area = state.spacing_m ** 2 * (1 - state.porosity)
    total_supply = c.solid_rate_m3_s * years * SECONDS_PER_YEAR
    # Shortest connected marine-face distance fixes the formative surface; it
    # affects height, never the set of cells eligible for sediment transport.
    if c.ceiling_slope_m_per_m:
        distance = _marine_graph_distance(state, domain, c.inlet_zx)
        ceiling = np.maximum(c.minimum_ceiling_m,
                             c.deposit_ceiling_m - c.ceiling_slope_m_per_m * distance)
    else:
        ceiling = c.deposit_ceiling_m
    water_stage = ceiling + (c.water_stage_m - c.deposit_ceiling_m)
    # Equal wet-neighbour weights avoid favouring deep water by assumption.
    for _ in range(sweeps):
        mobile[tuple(c.inlet_zx)] += total_supply / sweeps
        bed = state.base_bed_m + stock / area
        depth = np.where(domain, np.maximum(water_stage - bed, 0.), 0.)
        room = np.where(domain, np.maximum(ceiling - bed, 0.) * area, 0.)
        deposited = np.minimum(mobile * c.settling_fraction, room)
        stock += deposited
        mobile -= deposited
        weights = (depth > 0).astype(float)
        neighbours = np.zeros_like(mobile)
        neighbours[1:] += weights[:-1]
        neighbours[:-1] += weights[1:]
        neighbours[:, 1:] += weights[:, :-1]
        neighbours[:, :-1] += weights[:, 1:]
        outgoing = np.divide(mobile * c.mobility_fraction, neighbours,
                             out=np.zeros_like(mobile), where=(neighbours > 0) & (depth > 0))
        moved = outgoing * neighbours
        mobile -= moved
        mobile[1:] += outgoing[:-1] * weights[1:]
        mobile[:-1] += outgoing[1:] * weights[:-1]
        mobile[:, 1:] += outgoing[:, :-1] * weights[:, 1:]
        mobile[:, :-1] += outgoing[:, 1:] * weights[:, :-1]
    record = {'input_id': input_id, 'source_id': state.source_identity,
              'record_kind': 'geological_formative_input', 'known': True,
              'start_s': state.time_s, 'end_s': state.time_s,
              'row': c.inlet_zx[0], 'col': c.inlet_zx[1],
              'water_m3': 0., 'solid_m3': 0.,
              'direction_xz': [1., 0.], 'width_m': 1., 'depth_m': 1.,
              'delivered_water_m3': 0., 'delivered_solid_m3': 0., 'pending_solid_m3': 0.,
              'equivalent_water_m3': c.water_rate_m3_s * years * SECONDS_PER_YEAR,
              'geological_solid_m3': total_supply, 'equivalent_years': years,
              'water_interpretation': 'declared boundary, not hydraulically solved'}
    result = replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile,
                     consumed_packets=state.consumed_packets + (record,))
    p = dict(progress)
    p['inputs'] = [*progress['inputs'], input_id]
    p['years'] = progress['years'] + years
    p['supply_solid_m3'] = progress['supply_solid_m3'] + total_supply
    return result, p


def _marine_graph_distance(state, domain, inlet_zx):
    """Single-source metric distance with conservative barriers on mesh edges."""
    from scipy.sparse.csgraph import dijkstra
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    from terrain_pipeline.channel_geometry import _actual_segments_clear

    mesh = grid_mesh(domain.shape, x0_m=state.origin_xz_m[0],
                     z0_m=state.origin_xz_m[1], dx_m=state.spacing_m,
                     world_seed=20261020)
    mesh = masked_mesh(mesh, domain)
    sources = np.repeat(np.arange(domain.size), np.diff(mesh.indptr))
    points = np.column_stack((mesh.node_x_m, mesh.node_z_m))
    keep = _actual_segments_clear(sources, mesh.indices, points,
                                  state.origin_xz_m, state.spacing_m, domain)
    from scipy.sparse import coo_matrix
    graph = coo_matrix((mesh.edge_length_m[keep], (sources[keep], mesh.indices[keep])),
                       shape=(domain.size, domain.size)).tocsr()
    distance = dijkstra(graph, directed=False, indices=np.ravel_multi_index(tuple(inlet_zx), domain.shape))
    return distance.reshape(domain.shape)


def finalize_for_event(state, progress, *, ocean_mask, concentration_limit, sea_level_m=0., input_id):
    """Split numerical in-transit stock into bounded physical mobile and unresolved reserve."""
    from .coastal_marine_sediment import classify_ocean
    if (progress.get('algorithm') != 'connected-formative-irregular-distance-v2'
            or progress.get('event_finalized') or progress['source_identity'] != state.source_identity
            or not input_id or any(p.get('record_kind') == 'geological_event_finalization'
                                   or p.get('input_id') == input_id for p in state.consumed_packets)
            or not math.isfinite(concentration_limit) or not 0 <= concentration_limit <= 1
            or not math.isfinite(sea_level_m)):
        raise ValueError('invalid or already finalized event conversion')
    mask = np.asarray(ocean_mask, bool)
    if mask.shape != state.base_bed_m.shape or _mask_identity(mask) != progress['ocean_mask_sha256']:
        raise ValueError('source ocean identity mismatch')
    connected, _ = classify_ocean(state, sea_level_m)
    wet = connected & mask & state.valid_mask
    volume = np.where(wet, np.maximum(sea_level_m - state.bed_m, 0.) * state.spacing_m ** 2, 0.)
    mobile = np.minimum(state.mobile_solid_m3, concentration_limit * volume)
    removed = float(np.sum(state.mobile_solid_m3 - mobile, dtype=np.float64))
    record = {'record_kind': 'geological_event_finalization', 'input_id': input_id,
              'source_id': state.source_identity, 'known': False, 'start_s': state.time_s,
              'end_s': state.time_s, 'row': progress['config']['inlet_zx'][0],
              'col': progress['config']['inlet_zx'][1], 'direction_xz': [1., 0.],
              'width_m': 1., 'depth_m': 1., 'water_m3': None, 'solid_m3': None,
              'concentration_limit': concentration_limit, 'sea_level_m': sea_level_m,
              'retained_mobile_m3': float(mobile.sum(dtype=np.float64)),
              'transferred_unresolved_m3': removed}
    result = replace(state, mobile_solid_m3=mobile,
                     unresolved_solid_m3=state.unresolved_solid_m3 + removed,
                     consumed_packets=state.consumed_packets + (record,))
    p = dict(progress)
    p['event_finalized'] = record.copy()
    return result, p


def save(prefix, state, progress):
    save_checkpoint(prefix, state, progress)


def load(prefix):
    state, progress = load_checkpoint(prefix)
    if state.source_identity != progress['source_identity']:
        raise ValueError('checkpoint source identity mismatch')
    return state, progress
