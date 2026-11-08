"""Explicit initial tidal island, flat and channel excavation."""
from __future__ import annotations

import copy
import numpy as np
from scipy.ndimage import binary_propagation, distance_transform_edt
from scipy.spatial import cKDTree

from terrain_pipeline.channel_geometry import derived_seed
from .metric_tidal_island_geometry import (
    construct_island_channels, assign_tidal_storage, connected_tidal_exchange, DESIGN_LOW_STAGE_M,
    DESIGN_HIGH_STAGE_M, DESIGN_PERIOD_S,
)


def enrich_tidal_coast(source_arrays, source_metadata, *, world_seed=20261020):
    """Construct a prescribed initial coast; bulk cut is not sediment transport."""
    arrays = {key: value.copy() for key, value in source_arrays.items()}
    metadata = copy.deepcopy(source_metadata)
    original = np.asarray(arrays['bed_m'], float).copy()
    dx = float(metadata['spacing_m'])
    origin = np.asarray(metadata['origin_xz_m'], float)
    marine = np.asarray(arrays['open_marine_mask'], bool).copy()
    channel = np.asarray(arrays['channel_mask'], bool)
    retained = np.asarray(arrays['retained_upstream_raster_mask'], bool)
    river_buffer = max(30., 1.5*dx)
    river_distance = distance_transform_edt(~channel)*dx
    protected = (river_distance <= river_buffer) | retained
    fan = np.asarray(arrays.get('platform_weight', np.ones_like(original)))
    coast_distance = distance_transform_edt(~marine)*dx
    allowed = (~protected & (fan > .035) & (original < 4.) & (coast_distance < 2200.))
    seed = derived_seed(world_seed, 'delta/tidal-island-channel-geometry/v3')
    rng = np.random.default_rng(seed)
    river_direction = np.asarray(metadata.get('river_direction_xz', [1., 0.]), float)
    if 'river_direction_xz' not in metadata and 'trunk_path_xz_m' in arrays:
        trunk = arrays['trunk_path_xz_m']
        river_direction = trunk[-1]-trunk[max(0, len(trunk)-20)]
    river_direction = river_direction/np.linalg.norm(river_direction)
    bed, paths, parents, levels, through = construct_island_channels(
        original, marine, allowed, coast_distance, origin, dx, rng, river_direction)
    bank_weight = np.clip((river_distance-river_buffer)/220., 0., 1.)
    bank_weight = bank_weight**2*(3.-2.*bank_weight)
    bed = original+bank_weight*(bed-original)
    service, service_area, own_prism, cumulative_prism, sections = assign_tidal_storage(
        bed, allowed, marine, paths, parents, through, origin, dx, prospective=True)
    # Resolve only sections that the raster can represent. Their former
    # service cells are reassigned to retained channels, never double counted.
    keep = (sections[:, 2] >= max(2.5*dx, 35.)) | (np.asarray(parents) < 0)
    omitted_subresolution = int(np.count_nonzero(~keep))
    if omitted_subresolution:
        mapping = {}
        kept_ids = []
        remapped_parents = []
        for identity, parent in enumerate(parents):
            if keep[identity] and (parent < 0 or parent in mapping):
                mapping[identity] = len(kept_ids)
                kept_ids.append(identity)
                remapped_parents.append(-1 if parent < 0 else mapping[parent])
        paths = [paths[i] for i in kept_ids]
        levels = [levels[i] for i in kept_ids]
        parents = remapped_parents
        through = through[kept_ids]
        service, service_area, own_prism, cumulative_prism, sections = assign_tidal_storage(
            bed, allowed, marine, paths, parents, through, origin, dx, prospective=True)
    widths = sections[:, 0] if len(sections) else np.empty(0)
    depths = sections[:, 1] if len(sections) else np.empty(0)
    maximum_tidal_width = max(2.5*dx, .6*float(metadata.get('incoming_width_m', 200.)))
    widths = np.minimum(widths, maximum_tidal_width)
    # Subordinate tidal sections cannot replace the solved river geometry.
    # Preserve the requested section area where the declared depth cap allows.
    depths = np.minimum(3.8, sections[:, 4]/(.725*np.maximum(widths, 1.e-12)))
    depths = np.maximum(.45, depths)
    sections[:, 0] = widths
    sections[:, 1] = depths
    design_platform = bed.copy()
    design_exchange, design_connected = connected_tidal_exchange(
        bed, allowed, marine, paths, origin, dx, prospective=True)
    creek_ids = np.full(bed.shape, -1, np.int32)
    shore_footprint = (bed < original) & (coast_distance < 500.)
    for identity, (path, width, depth) in enumerate(zip(paths, widths, depths)):
        station = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        fraction = station/max(station[-1], 1.e-12)
        taper = (.6+.4*np.abs(2.*fraction-1.)**.8 if through[identity]
                 else .2+.8*(1.-fraction)**.8)
        minimum_width = max(2.5*dx, 35.)
        profile_width = minimum_width+max(0., width-minimum_width)*taper
        radius = .5*profile_width
        margin = max(width, minimum_width)+3.*dx
        lo = np.maximum(np.floor((path.min(axis=0)-margin-origin)/dx).astype(int), 0)
        hi = np.minimum(np.ceil((path.max(axis=0)+margin-origin)/dx).astype(int)+1, bed.shape[::-1])
        rows = slice(lo[1], hi[1])
        cols = slice(lo[0], hi[0])
        zz, xx = np.mgrid[lo[1]:hi[1], lo[0]:hi[0]]
        query = np.stack([origin[0]+xx*dx, origin[1]+zz*dx], axis=-1)
        distance, nearest = cKDTree(path).query(query.reshape(-1, 2), workers=1)
        distance = distance.reshape(xx.shape)
        nearest = nearest.reshape(xx.shape)
        ratio = distance/radius[nearest]
        active = (ratio < 2.1) & allowed[rows, cols] & ~marine[rows, cols]
        local_depth = depth*taper[nearest]**.5
        target = np.where(ratio <= 1., -local_depth*np.clip((1.-ratio)/.55, 0., 1.),
                          .55*np.clip((ratio-1.)/1.1, 0., 1.))
        weight = np.clip((2.1-ratio)/.55, 0., 1.)
        old = bed[rows, cols]
        proposal = old+weight*(target-old)
        changed = active & (proposal < old)
        old[changed] = proposal[changed]
        creek_ids[rows, cols][changed & (ratio <= 1.)] = identity
        if levels[identity] == 0:
            shore_footprint[rows, cols] |= changed & (fraction[nearest] < .35)
    footprint = bed < original
    new_marine = binary_propagation(marine, mask=(marine | footprint) & (bed < 0.))
    isolated_cut = footprint & (bed < 0.) & ~new_marine
    # Keep disconnected depressions as shallow positive tidal flats rather
    # than restoring abrupt patches of the inherited high platform.
    bed[isolated_cut] = np.minimum(original[isolated_cut], .08)
    footprint = bed < original
    shore_footprint &= footprint
    tidal_creek = new_marine & ~marine
    original_paths = paths
    kept, kept_parents, kept_levels, kept_widths, kept_depths, kept_through = [], [], [], [], [], []
    path_id_map = {}
    rejected_paths = truncated_paths = 0
    for old_id, (path, parent, level, width, depth) in enumerate(zip(paths, parents, levels, widths, depths)):
        if parent >= 0 and parent not in path_id_map:
            rejected_paths += 1
            continue
        cells = np.floor((path-origin)/dx+.5).astype(int)
        covered = new_marine[cells[:, 1], cells[:, 0]] & (bed[cells[:, 1], cells[:, 0]] < 0.)
        missing = np.flatnonzero(~covered)
        if len(missing):
            path = path[:missing[0]]
            truncated_paths += 1
        if len(path) < 14:
            rejected_paths += 1
            continue
        path_id_map[old_id] = len(kept)
        kept.append(path)
        kept_parents.append(-1 if parent < 0 else path_id_map[parent])
        kept_levels.append(level)
        kept_widths.append(width)
        kept_depths.append(depth)
        kept_through.append(bool(through[old_id] and not len(missing)))
    mapped_ids = np.full_like(creek_ids, -1)
    for old_id, new_id in path_id_map.items():
        mapped_ids[creek_ids == old_id] = new_id
    creek_ids = mapped_ids
    paths, parents, levels, widths = kept, kept_parents, kept_levels, kept_widths
    final_service, final_area, final_own_prism, final_prism, _ = assign_tidal_storage(
        bed, allowed, marine, paths, parents, np.asarray(kept_through), origin, dx)
    final_exchange, final_connected = connected_tidal_exchange(
        bed, allowed, marine, paths, origin, dx)
    adjacency = []
    wet_ids = np.where(new_marine, creek_ids, -1)
    for first, second in ((wet_ids[:-1], wet_ids[1:]), (wet_ids[:, :-1], wet_ids[:, 1:])):
        touching = (first >= 0) & (second >= 0) & (first != second)
        adjacency.append(np.sort(np.column_stack([first[touching], second[touching]]), axis=1))
    adjacency = np.unique(np.concatenate(adjacency), axis=0)
    cut = original-bed
    intertidal = footprint & (bed >= DESIGN_LOW_STAGE_M) & (bed < DESIGN_HIGH_STAGE_M)
    surface = np.asarray(arrays.get('water_surface_m', bed)).copy()
    surface[new_marine] = 0.
    wet = np.asarray(arrays.get('wet_mask', np.zeros_like(marine))).copy() | new_marine
    surface[~wet] = bed[~wet]
    offsets = np.r_[0, np.cumsum([len(path) for path in paths])].astype(np.int64)
    arrays.update(bed_m=bed, open_marine_mask=new_marine, connected_ocean_mask=new_marine.copy(),
        sea_seed_mask=new_marine.copy(), water_surface_m=surface,
        water_depth_m=np.where(wet, np.maximum(surface-bed, 0.), 0.), wet_mask=wet,
        construction_footprint_mask=arrays['construction_footprint_mask'] | footprint,
        tidal_creek_mask=tidal_creek, tidal_intertidal_mask=intertidal,
        tidal_shore_footprint_mask=shore_footprint, tidal_creek_footprint_mask=footprint,
        tidal_protected_river_mask=protected, tidal_detail_allowed_mask=allowed,
        tidal_original_marine_seed_mask=marine, tidal_initial_cut_depth_m=cut,
        tidal_creek_id=creek_ids, tidal_creek_offsets=offsets,
        tidal_creek_points_xz_m=np.concatenate(paths) if paths else np.empty((0, 2)),
        tidal_creek_parent_index=np.asarray(parents, np.int32),
        tidal_creek_join_index=np.full(len(paths), -1, np.int32),
        tidal_creek_wet_adjacency_pairs=adjacency,
        tidal_creek_level=np.asarray(levels, np.int8), tidal_creek_width_m=np.asarray(widths),
        tidal_creek_design_depth_m=np.asarray(kept_depths),
        tidal_creek_through_channel=np.asarray(kept_through),
        tidal_service_id=final_service, tidal_service_area_m2=final_area,
        tidal_service_exchange_volume_m3=final_own_prism,
        tidal_cumulative_exchange_volume_m3=final_prism,
        tidal_design_service_id=service,
        tidal_design_platform_bed_m=design_platform,
        tidal_design_exchange_depth_m=design_exchange,
        tidal_design_high_water_connected_mask=design_connected,
        tidal_final_exchange_depth_m=final_exchange,
        tidal_final_high_water_connected_mask=final_connected,
        tidal_design_path_saved_index=np.asarray([path_id_map.get(i, -1) for i in range(len(original_paths))], np.int32),
        tidal_design_service_area_m2=service_area,
        tidal_design_exchange_volume_m3=own_prism,
        tidal_design_cumulative_exchange_volume_m3=cumulative_prism,
        tidal_design_width_m=sections[:, 0] if len(sections) else np.empty(0),
        tidal_design_depth_m=sections[:, 1] if len(sections) else np.empty(0),
        tidal_design_unconstrained_width_m=sections[:, 2],
        tidal_design_unconstrained_depth_m=sections[:, 3],
        tidal_design_cross_section_m2=sections[:, 4],
        tidal_design_resolution_limited=sections[:, 2] < max(2.5*dx, 35.),
        tidal_design_actual_mouth_cross_section_m2=.725*sections[:, 0]*sections[:, 1],
        tidal_design_section_shortfall_m2=np.maximum(sections[:, 4]-.725*sections[:, 0]*sections[:, 1], 0.),
        tidal_design_implied_peak_velocity_m_s=.25*sections[:, 4]/np.maximum(.725*sections[:, 0]*sections[:, 1], 1.e-12),
        tidal_creek_connected_sample_fraction=np.ones(len(paths)),
        tidal_creek_disconnected_sample_count=np.zeros(len(paths), np.int32))
    if 'design_stage_m' in arrays:
        arrays['design_stage_m'][new_marine] = 0.
    audit = dict(cut_bulk_m3=float(cut.sum()*dx**2), fill_bulk_m3=0., net_bulk_m3=float(-cut.sum()*dx**2),
        creek_count=len(paths), root_count=int(np.count_nonzero(np.asarray(parents) == -1)),
        through_channel_count=int(np.count_nonzero(kept_through)),
        omitted_subresolution_branch_count=omitted_subresolution,
        section_capacity_limited_count=int(np.count_nonzero(sections[:, 4] > .725*sections[:, 0]*sections[:, 1]+1.e-8)),
        rejected_path_count=rejected_paths, truncated_path_count=truncated_paths,
        saved_path_minimum_connected_sample_fraction=1. if paths else 0.,
        saved_path_disconnected_sample_count=0, terminal_join_count=0,
        wet_raster_adjacency_count=int(len(adjacency)),
        restored_disconnected_excavation_area_m2=float(isolated_cut.sum()*dx**2),
        disconnected_negative_bed_raised_to_positive_flat=True,
        marine_added_area_m2=float(tidal_creek.sum()*dx**2), intertidal_area_m2=float(intertidal.sum()*dx**2),
        design_exchange_volume_m3=float(own_prism.sum()), final_exchange_volume_m3=float(final_own_prism.sum()),
        service_area_m2=float(final_area.sum()),
        protected_exact=bool(np.array_equal(bed[protected], original[protected])),
        all_negative_excavation_marine_connected=bool(not np.any((cut > 0.) & (bed < 0.) & ~new_marine)),
        original_marine_bed_exact=bool(np.array_equal(bed[marine], original[marine])))
    metadata['tidal_coast_construction'] = dict(algorithm='river-aligned-tidal-island-storage-initial-v5',
        world_seed=int(world_seed), purpose='delta/tidal-island-channel-geometry/v3', purpose_seed=int(seed),
        minimum_tip_width_m=max(2.5*dx, 35.), river_buffer_m=river_buffer,
        river_bank_transition_m=220., trapezoid_cross_section_area_factor=.725,
        bay_incision_correlation_reach_m=[80., 260.],
        bay_geometry_choice='Absolute-coordinate correlated bay intrusion length restricted to 80-260m to retain exposed interiors within this approximately kilometre-wide delta platform; geometric initialization parameter, not an erosion length inferred from tides',
        maximum_coast_distance_m=2200., audit=audit,
        design_low_stage_m=DESIGN_LOW_STAGE_M, design_high_stage_m=DESIGN_HIGH_STAGE_M,
        design_period_s=DESIGN_PERIOD_S,
        tidal_boundary_scenario='Prescribed symmetric 3m coastal spring tidal range inspired by Hiron Point, GBM delta; Hale et al. 2019 section 3.1 reports 3-3.5m. Idealized scenario, not site calibration.',
        design_velocity_m_s=.25, design_width_depth_ratio=70., maximum_width_m=maximum_tidal_width,
        inherited_river_direction_xz=river_direction.tolist(),
        channel_orientation='Through channels have strictly increasing inherited river-direction projection, endpoint longitudinal displacement >=0.65 chord length; blind tidal heads and tributaries grow inland against inherited river direction; widths capped at 0.6 incoming river width with depth adjusted up to 3.8m',
        design_method='Disjoint nearest-path service areas; storage=sum(max(high-bed,0)-max(low-bed,0))*cell_area on D4 high-stage sea-connected cells, proposed paths allowed as excavated during design; children accumulated upstream; two-mouth channels divide storage equally; Q_peak=pi*P/period, section=Q_peak/design_velocity, selected unconstrained width/depth ratio 70 and trapezoid area factor .725; branches below 2.5 cells omitted and service reassigned; surviving major sections may be raster limited; subordinate width capped at 0.6 incoming river width and centre depth adjusted up to 3.8m; section shortfall and implied peak velocity explicitly saved',
        semantics='Prescribed initial island/flat excavation and smooth channels, not emergent evolution or hydrodynamic calibration. Storage is a geometric proxy, not a simulated tidal prism. Original river and marine beds retained exactly; marine ownership only on D4-connected excavated negative beds.')
    return dict(arrays=arrays, metadata=metadata, audit=audit)
