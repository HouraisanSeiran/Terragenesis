"""World-scale generation adapter over irregular routing and sediment rate kernels.

Equivalent shaping rounds are not a transient hydraulic simulation. All stocks
are solid m3; only the Exner conversion introduces depositional pore volume.
"""
from types import SimpleNamespace

import numpy as np
from numba import njit

from terrain_pipeline import drainage
from terrain_pipeline.surface_hydraulics import _hydraulics
from terrain_pipeline.surface_rivers.metric_bed_update import bed_from_inventory
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, _rates


def routing(bed, ocean, lagoon, mesh):
    outlets = np.asarray(ocean, bool) | np.asarray(lagoon, bool)
    outlets = outlets.copy()
    outlets[[0, -1], :] = True
    outlets[:, [0, -1]] = True
    return drainage.route_graph(np.asarray(bed, np.float64), outlets, mesh)


def lake_balance(local_m3, receiver, order, lake_id, bed, filled, cell_area_m2, initial_storage=None, *, compute_surface=True):
    """Reuse capacity-limited pool routing, with explicit empty initial lakes."""
    labels = np.asarray(lake_id, np.int64).ravel() - 1
    present = np.unique(labels[labels >= 0])
    if present.size:
        labels = np.where(labels >= 0, np.searchsorted(present, labels), -1).astype(np.int64)
    count = present.size
    capacity = np.bincount(labels[labels >= 0], weights=np.maximum(np.asarray(filled).ravel() - np.asarray(bed).ravel(), 0.)[labels >= 0] * cell_area_m2, minlength=count)
    rank = np.empty(labels.size, np.int64)
    rank[np.asarray(order)] = np.arange(labels.size)
    anchor_rank = np.full(count, labels.size, np.int64)
    np.minimum.at(anchor_rank, labels[labels >= 0], rank[labels >= 0])
    anchors = np.asarray(order)[anchor_rank]
    storage = np.zeros(count) if initial_storage is None else np.asarray(initial_storage, np.float64).copy()
    if storage.shape != capacity.shape or np.any((storage < 0) | (storage > capacity)):
        raise ValueError('lake initial storage differs from capacity')
    before = storage.copy()
    flow, retained = drainage.route_pool_interval(np.asarray(local_m3, np.float64).ravel(), np.asarray(order, np.int64), np.asarray(receiver, np.int64), labels, anchors, capacity, storage)
    surface = np.full(labels.size, np.nan)
    if not compute_surface:
        return flow, surface, dict(initial_storage_m3=float(before.sum()), final_storage_m3=float(storage.sum()), retained_m3=float(retained), capacity_m3=float(capacity.sum()), storage_by_pool_m3=storage)
    # A constant level is solved from actual capacity, never equated to spill level.
    lake_cells = np.flatnonzero(labels >= 0)
    grouped = lake_cells[np.argsort(labels[lake_cells], kind='stable')]
    edges = np.r_[0, np.cumsum(np.bincount(labels[lake_cells], minlength=count))]
    for label in range(count):
        if storage[label] <= 0.:
            continue
        cells = grouped[edges[label]:edges[label + 1]]
        heights = np.asarray(bed).ravel()[cells]
        low, high = float(heights.min()), float(np.asarray(filled).ravel()[cells].max())
        for _ in range(40):
            mid = (low + high) / 2
            if np.maximum(mid - heights, 0.).sum() * cell_area_m2 > storage[label]:
                high = mid
            else:
                low = mid
        wet = cells[heights < (low + high) / 2]
        surface[wet] = (low + high) / 2
    return flow, surface, dict(initial_storage_m3=float(before.sum()), final_storage_m3=float(storage.sum()), retained_m3=float(retained), capacity_m3=float(capacity.sum()), storage_by_pool_m3=storage)


def representative_hydraulics(bed, receiver, discharge, mesh, roughness=.04):
    """Invert the existing rectangular Manning kernel with fixed iterations."""
    bed = np.asarray(bed, np.float64).ravel()
    rec = np.asarray(receiver, np.int64).ravel()
    q = np.asarray(discharge, np.float64).ravel()
    distance = np.full(bed.size, float(mesh.spacing_m))
    edge = rec >= 0
    distance[edge] = np.hypot(mesh.node_x_m[edge] - mesh.node_x_m[rec[edge]], mesh.node_z_m[edge] - mesh.node_z_m[rec[edge]])
    slope = np.zeros(bed.size)
    slope[edge] = np.maximum(0., (bed[edge] - bed[rec[edge]]) / distance[edge])
    width = np.minimum(float(mesh.spacing_m), np.maximum(1., 4. * np.sqrt(q)))
    roughness_field = np.broadcast_to(np.asarray(roughness, np.float64).ravel(), (bed.size,)).copy()
    if not np.isfinite(roughness_field).all() or np.any(roughness_field <= 0):
        raise ValueError('positive finite actual Manning roughness required')
    network = SimpleNamespace(length_m=distance, width_m=width, bed_slope=slope, roughness=roughness_field, terminal_kind=np.full(bed.size, 'interior', dtype='U16'))
    low = np.zeros(bed.size)
    high = np.full(bed.size, 1000.)
    for _ in range(32):
        middle = (low + high) / 2
        volume = middle * width * distance
        solved_q = _hydraulics(network, volume)[2]
        below = solved_q < q
        low = np.where(below, middle, low)
        high = np.where(below, high, middle)
    depth = np.where((q > 0) & (slope > 0), (low + high) / 2, 0.)
    return dict(width_m=width, depth_m=depth, slope=slope, length_m=distance, volume_m3=depth * width * distance)


@njit(cache=True)
def _transport(receiver, order, capacity, loose_limit, rock_limit, loose, ocean, lagoon, lakes, protected, mobile_initial):
    mobile = mobile_initial.copy()
    deposited = np.zeros(loose.size)
    loose_erosion = np.zeros(loose.size)
    rock_erosion = np.zeros(loose.size)
    marine = np.zeros(loose.size)
    external = np.zeros(loose.size)
    outgoing = np.zeros(loose.size)
    for index in range(order.size - 1, -1, -1):
        cell = order[index]
        if ocean[cell] or lagoon[cell]:
            marine[cell] += mobile[cell]
            mobile[cell] = 0.
            continue
        target = receiver[cell]
        if target < 0:
            external[cell] += mobile[cell]
            mobile[cell] = 0.
            continue
        if lakes[cell]:
            deposited[cell] += mobile[cell]
            mobile[cell] = 0.
        elif not protected[cell]:
            deficit = max(0., capacity[cell] - mobile[cell])
            eroded = min(loose[cell], loose_limit[cell], deficit)
            loose_erosion[cell] = eroded
            mobile[cell] += eroded
            # Bedrock is exposed only once the finite loose cover is exhausted.
            if loose[cell] - eroded <= 1e-12:
                eroded_rock = min(rock_limit[cell], max(0., capacity[cell] - mobile[cell]))
                rock_erosion[cell] = eroded_rock
                mobile[cell] += eroded_rock
            excess = max(0., mobile[cell] - capacity[cell])
            deposited[cell] += excess
            mobile[cell] -= excess
        outgoing[cell] = mobile[cell]
        mobile[target] += mobile[cell]
        mobile[cell] = 0.
    return deposited, loose_erosion, rock_erosion, marine, external, mobile, outgoing


def shape_round(bed, initial_bed, initial_loose, loose, rock_removed, mobile, receiver, order, discharge, mesh, ocean, lagoon, lake_id, protected, materials, config):
    roughness = materials.get('manning_n', config['roughness'])
    hydraulic = representative_hydraulics(bed, receiver, discharge, mesh, roughness=roughness)
    count = np.asarray(bed).size
    porosity = np.broadcast_to(np.asarray(materials.get('porosity', .35)), np.asarray(bed).shape).ravel()
    erodibility = np.broadcast_to(np.asarray(materials.get('erodibility', materials.get('erodibility_index', .5))), np.asarray(bed).shape).ravel()
    domain = SimpleNamespace(width_m=hydraulic['width_m'], bed_area_m2=np.full(count, mesh.spacing_m ** 2), is_lake=np.asarray(lake_id).ravel() > 0)
    forcing = SimpleNamespace(water_volume_m3=hydraulic['volume_m3'][None], water_depth_m=hydraulic['depth_m'][None], water_outflow_m3_s=np.asarray(discharge).reshape(1, -1), friction_slope=hydraulic['slope'][None])
    material = MaterialParameters()
    tau, capacity, _, _, loose_rate, rock_rate = _rates(domain, forcing, material, 0, np.asarray(mobile), np.asarray(loose), np.asarray(rock_removed))
    exposure = float(config['equivalent_exposure_seconds'])
    maximum = float(config['max_round_bed_change_m']) * mesh.spacing_m ** 2
    loose_limit = np.minimum(loose_rate * exposure * erodibility, maximum * (1 - porosity))
    rock_limit = np.minimum(rock_rate * exposure * erodibility, maximum)
    rock_limit = np.minimum(rock_limit, np.maximum(0., float(config['rock_reserve_m']) * mesh.spacing_m ** 2 - rock_removed))
    available_bulk = np.minimum(maximum, np.maximum(0., np.asarray(bed).ravel() - .01) * mesh.spacing_m ** 2)
    loose_limit = np.minimum(loose_limit, available_bulk * (1 - porosity))
    rock_limit = np.minimum(rock_limit, np.maximum(0., available_bulk - loose_limit / (1 - porosity)))
    dep, le, re, sea, ext, moving, outgoing = _transport(np.asarray(receiver, np.int64), np.asarray(order, np.int64), capacity * exposure, loose_limit, rock_limit, loose, np.asarray(ocean).ravel(), np.asarray(lagoon).ravel(), domain.is_lake, np.asarray(protected).ravel(), mobile)
    next_loose = loose - le + dep
    next_rock = rock_removed + re
    next_bed = bed_from_inventory(np.asarray(initial_bed).ravel(), initial_loose, next_loose, next_rock, mesh.spacing_m ** 2, porosity).reshape(np.asarray(bed).shape)
    # Coast protection is enforced through stock placement, not a post-hoc bed clamp.
    return next_bed, next_loose, next_rock, moving, dict(deposited_solid_m3=dep, eroded_loose_solid_m3=le, eroded_rock_m3=re, marine_solid_m3=sea, external_solid_m3=ext, outgoing_solid_m3=outgoing, shear_pa=tau), hydraulic
