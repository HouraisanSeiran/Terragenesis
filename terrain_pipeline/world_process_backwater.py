"""Bounded native 2D storage events; closed rims never become free outlets.

This adapter completes a declared short event, not a seasonal lake equilibrium
or a downstream continuation. Raw TD heights and the selected inlet are kept.
"""
from __future__ import annotations

import numpy as np

from terrain_pipeline.common_infra import identity


def _window(shape, row, col, side):
    r0 = min(max(0, row-side//2), max(0, shape[0]-side))
    c0 = min(max(0, col-side//2), max(0, shape[1]-side))
    return slice(r0, min(shape[0], r0+side)), slice(c0, min(shape[1], c0+side))


def _momentum(geometry, face_q):
    """Cell discharge density reconstructed from the actual D4 shared Q."""
    a = geometry['arrays']
    rows, cols = a['H0_m'].shape
    axis = np.r_[np.zeros(rows*(cols-1), int), np.ones((rows-1)*cols, int)]
    n = rows*cols
    result = np.zeros((n, 2))
    for dim in (0, 1):
        use = axis == dim
        nodes = np.r_[a['face_left'][use], a['face_right'][use]]
        count = np.bincount(nodes, minlength=n)
        total = np.bincount(nodes, weights=np.tile(face_q[use], 2), minlength=n)
        result[:, dim] = np.divide(total, count*geometry['metadata']['spacing_m'],
            out=np.zeros(n), where=count > 0)
    return result


def solve_native_backwater(product, region, terrain, *, config=None):
    """One finite closed-volume event with conservative signed 2D face replay."""
    from terrain_pipeline.world_process_detail import boundary_package, validate_boundary
    from terrain_pipeline.ocean_island_consumers import connected_ocean
    from terrain_pipeline.surface_hydraulics import (
        SurfaceBudget, prepare_surface_geometry, advance_inertial_surface)
    from terrain_pipeline.surface_rivers.metric_fv_bedload_v4 import transport_bedload
    from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig
    from terrain_pipeline.surface_rivers.metric_fv_suspended_supply import SuspendedConfig, advance_suspended

    cfg = dict(config or {})
    full = np.asarray(terrain['elevation_m'], np.float64)
    spacing = float(terrain['grid']['spacing_m'])
    if full.ndim != 2 or not np.isfinite(full).all() or spacing != 30.:
        raise ValueError('finite native TD at 30m required for storage event')
    first = terrain['grid']['first_sample_xz_m']
    x, z = region['location_xz_m']
    col, row = int(round((x-first[0])/spacing)), int(round((z-first[1])/spacing))
    if not 0 <= row < full.shape[0] or not 0 <= col < full.shape[1]:
        raise ValueError('selected location lies outside prepared native TD tile')
    max_cells = cfg.get('max_backwater_cells', cfg.get('max_estuary_cells', 65536))
    side = cfg.get('backwater_window_cells', 64)
    if type(max_cells) is not int or not 4 <= max_cells <= 65536:
        raise ValueError('backwater cell budget must be within 4..65536')
    if type(side) is not int or not 2 <= side <= 256 or side*side > max_cells:
        raise ValueError('backwater window exceeds declared cell budget')
    rows, cols = _window(full.shape, row, col, side)
    bed = full[rows, cols].copy()
    origin = [first[0]+cols.start*spacing, first[1]+rows.start*spacing]
    inlet = (row-rows.start)*bed.shape[1]+col-cols.start
    package = boundary_package(product, region, terrain['identity'],
        duration_s=cfg.get('detail_duration_s', 30.))
    validate_boundary(package, source_identity=product['metadata']['source_identity'], terrain_identity=terrain['identity'])
    if package['discharge_m3_s'] <= 0:
        raise ValueError('no water available in coarse boundary')
    duration = package['interval_end_s']-package['interval_start_s']
    interval_s = float(cfg.get('backwater_interval_s', .25))
    if not np.isfinite(interval_s) or interval_s <= 0:
        raise ValueError('positive finite backwater coupling interval required')
    intervals = int(np.ceil(duration/interval_s))
    if intervals > 4096:
        raise ValueError('backwater interval trace budget exceeded')
    interval_s = duration/intervals
    # Include signed-face, cell, bed/mobile traces and geometry in preflight;
    # the shared water budget does not account for adapter-owned replay arrays.
    trace_bytes = int((intervals*(20*bed.size+8*(2*bed.size+2*sum(bed.shape)))+64*bed.size)*8)
    if trace_bytes > 256*1024**2:
        raise ValueError('backwater replay memory budget exceeded')
    sea_full = connected_ocean(full)
    sea = sea_full[rows, cols]
    sea_inlet = bool(sea_full[row, col])
    # Sea connectivity classifies provenance only. This is a closed finite
    # initial stock, with no prescribed stage or ocean boundary import.
    initial_depth = np.where(sea, np.maximum(-bed, 0.), 0.) if sea_inlet else np.zeros_like(bed)
    initial_source = ('declared finite still-sea stock at 0m on full-native perimeter-connected cells; closed event, no sea stage supply'
        if sea_inlet else 'declared independently initially dry short event; no saved coarse lake water consumed')
    scenario = 'finite-initial-sea-stock' if sea_inlet else 'independent-initially-dry-storage-event'
    m, coarse = product['metadata'], product['arrays']
    cspacing = float(m['spacing_m'])
    zz, xx = np.indices(bed.shape)
    world_x, world_z = origin[0]+xx*spacing, origin[1]+zz*spacing
    cx = np.rint((world_x-m['first_xz_m'][0])/cspacing).astype(int)
    cz = np.rint((world_z-m['first_xz_m'][1])/cspacing).astype(int)
    shape = coarse['elevation_m'].shape
    if np.any((cx < 0)|(cx >= shape[1])|(cz < 0)|(cz >= shape[0])):
        raise ValueError('native storage support extends outside known coarse world')
    coarse_nodes = (cz*shape[1]+cx).ravel()
    support, counts = np.unique(coarse_nodes, return_counts=True)
    all_counts = np.bincount(coarse_nodes, minlength=coarse['elevation_m'].size)
    allocation = np.minimum(1., cspacing**2/(all_counts[coarse_nodes]*spacing**2))
    porosity = float(np.mean(np.asarray(coarse.get('porosity', np.full(shape, .35))).ravel()[support]))
    if not np.isfinite(porosity) or not 0 <= porosity < 1:
        raise ValueError('finite material porosity in [0,1) required')
    loose = np.asarray(coarse['loose_solid_m3']).ravel()[coarse_nodes]*allocation*spacing**2/cspacing**2
    if not np.isfinite(loose).all() or np.any(loose < 0):
        raise ValueError('nonnegative finite native loose stock required')
    removed_rock = np.asarray(coarse.get('rock_removed_m3', np.zeros(shape))).ravel()[coarse_nodes]
    remaining_rock = float(m['config']['rock_reserve_m'])*cspacing**2-removed_rock
    if not np.isfinite(remaining_rock).all() or np.any(remaining_rock < -1e-6):
        raise ValueError('coarse native support has invalid remaining finite rock reserve')
    native_rock_reserve = np.maximum(remaining_rock, 0.)*allocation*spacing**2/cspacing**2
    floor = bed-(loose/(spacing**2*(1.-porosity))).reshape(bed.shape)
    geometry = prepare_surface_geometry(bed, spacing_m=spacing,
        origin_m_xz=origin, source_identity=terrain['identity'])
    forcing = np.zeros_like(bed)
    forcing.ravel()[inlet] = package['water_m3']/duration
    initial_volume = float(initial_depth.sum()*spacing**2)
    max_depth = max(20., float(initial_depth.max())+package['water_m3']/spacing**2+1.)
    budget = SurfaceBudget(roughness_s_m_third=float(m['config']['roughness']),
        max_dt_s=min(.5, interval_s), max_cells=max_cells, max_substeps=100000,
        max_face_evaluations=100000000, max_bytes=256*1024**2,
        max_duration_s=300., max_wall_s=float(cfg.get('backwater_max_wall_s', 120.)),
        max_depth_m=max_depth, max_snapshots=4)
    max_change = float(cfg.get('backwater_max_bed_change_m', .05))
    bedload_cfg = BedloadConfig(porosity=porosity, manning_s_m_third=float(m['config']['roughness']),
        wave_height_m=0., max_bed_change_m=max_change)
    suspended_cfg = SuspendedConfig(porosity=porosity, max_bed_change_m=max_change)
    current_bed = bed.copy()
    suspended = np.zeros_like(bed)
    packets, sediment_steps = [], []
    bed_trace, mobile_trace = [bed.copy()], [suspended.copy()]
    erosion = np.zeros_like(bed)
    deposition = np.zeros_like(bed)
    solid_inputs, solid_exports, solid_faces = [], [], []

    def observe(packet):
        nonlocal current_bed, suspended
        # No ocean/stage driver is used. Cross velocity is reconstructed from
        # archived D4 Q; normal velocity uses the actual integrated shared flux.
        packet['momentum_before'] = _momentum(geometry, packet['internal_q_before_m3_s'])
        packet['momentum_after'] = _momentum(geometry, packet['internal_q_after_m3_s'])
        packet['tailwater_m'] = bed.ravel()[geometry['arrays']['boundary_cell']]
        before = current_bed.copy()
        moved = transport_bedload(current_bed, floor, geometry, packet, bedload_cfg)
        injected = package['solid_m3']*(packet['time_end_s']-packet['time_start_s'])/duration
        settled = advance_suspended(suspended, moved['bed_m'], geometry, packet,
            injected, np.array([inlet], int), suspended_cfg)
        current_bed = settled['bed_m']
        suspended = settled['suspended_solid_m3']
        erosion[:] += np.maximum(before-moved['bed_m'], 0.)*spacing**2
        deposition[:] += np.maximum(moved['bed_m']-before, 0.)*spacing**2
        deposition[:] += settled['deposited_solid_m3']/(1.-porosity)
        packets.append(packet)
        sediment_steps.append(dict(bedload=moved['ledger'], suspended=settled['ledger']))
        solid_inputs.append(injected)
        solid_exports.append(moved['boundary_export_solid_m3']+settled['boundary_export_solid_m3'])
        solid_faces.append(moved['internal_transfer_solid_m3']+settled['internal_transfer_solid_m3'])
        bed_trace.append(current_bed.copy())
        mobile_trace.append(suspended.copy())

    hydraulic = advance_inertial_surface(geometry, initial_depth_m=initial_depth,
        forcing_interval_s=interval_s, intervals=intervals, forcing_provider=lambda index: forcing,
        boundary_stage_provider=lambda index: bed.ravel()[geometry['arrays']['boundary_cell']],
        source_identity=terrain['identity'], forcing_identity=package['id'], budget=budget,
        snapshot_interval_s=duration, interval_observer=observe)
    if hydraulic['metadata']['status'] != 'completed' or len(packets) != intervals:
        raise ValueError('incomplete finite native storage event: '+str(hydraulic['metadata'].get('failure')))
    if np.max(np.abs(current_bed-bed)) > max_change*(1.+1e-12):
        raise ValueError('native storage total bed change exceeds frozen-water replay limit')
    hydraulic['metadata']['underlying_status'] = hydraulic['metadata']['status']
    hydraulic['metadata']['status'] = 'complete'
    hydraulic['metadata'].update(solver='surface_hydraulics.advance_inertial_surface',
        initial_water_source=initial_source, scenario=scenario, interval_s=interval_s,
        completed_scope='declared representative closed short event only',
        geometry_identity=identity(geometry['arrays'], geometry['metadata']))
    ha = hydraulic['arrays']
    for key in ('depth_before_m','depth_after_m','internal_transfer_m3','boundary_transfer_m3',
                'forcing_volume_m3','internal_q_before_m3_s','internal_q_after_m3_s'):
        ha['interval_'+key] = np.asarray([p[key] for p in packets])
    ha.update(face_left=geometry['arrays']['face_left'], face_right=geometry['arrays']['face_right'],
        boundary_cell=geometry['arrays']['boundary_cell'], boundary_kind=geometry['arrays']['boundary_kind'],
        interval_time_seconds=np.asarray([0.]+[p['time_end_s'] for p in packets]))
    final_loose = np.maximum(current_bed-floor, 0.).ravel()*spacing**2*(1.-porosity)
    delta = (current_bed-bed).ravel()
    event_fraction = min(1., duration/(m['config']['shaping_rounds']*m['config']['equivalent_exposure_seconds']))
    replacements = {key:[] for key in ('elevation_m','loose_solid_m3','rock_removed_m3',
        'mobile_solid_m3','erosion_m','deposition_m')}
    reversed_rock = reversed_loose = reversed_mobile = 0.
    initial_coarse = coarse.get('shaping_initial_elevation_m', coarse['initial_elevation_m'])
    initial_loose = coarse.get('shaping_initial_loose_solid_m3', coarse.get('initial_loose_solid_m3', coarse['loose_solid_m3']))
    initial_rock = coarse.get('shaping_initial_rock_removed_m3', np.zeros(shape))
    for node, count in zip(support, counts):
        use = coarse_nodes == node
        fraction = min(1., float(count*spacing**2/cspacing**2))
        f = fraction*event_fraction
        old_bed = float(coarse['elevation_m'].ravel()[node])
        replacements['elevation_m'].append(old_bed-(old_bed-initial_coarse.ravel()[node])*f+float(delta[use].sum()*spacing**2/cspacing**2))
        old_loose = float(coarse['loose_solid_m3'].ravel()[node])
        old_rock = float(np.asarray(coarse.get('rock_removed_m3', np.zeros(shape))).ravel()[node])
        old_mobile = float(np.asarray(coarse.get('mobile_solid_m3', np.zeros(shape))).ravel()[node])
        replacements['loose_solid_m3'].append(old_loose-(old_loose-initial_loose.ravel()[node])*f+float(final_loose[use].sum()-loose[use].sum()))
        replacements['rock_removed_m3'].append(old_rock-(old_rock-initial_rock.ravel()[node])*f)
        replacements['mobile_solid_m3'].append(old_mobile*(1-f)+float(suspended.ravel()[use].sum()))
        for name, fine in (('erosion_m', erosion), ('deposition_m', deposition)):
            previous = float(np.asarray(coarse.get(name, np.zeros(shape))).ravel()[node])
            replacements[name].append(previous*(1-f)+float(fine.ravel()[use].sum()/cspacing**2))
        reversed_rock += (old_rock-initial_rock.ravel()[node])*f
        reversed_loose += (old_loose-initial_loose.ravel()[node])*f
        reversed_mobile += old_mobile*f
    water_input = float(sum(p['forcing_volume_m3'].sum() for p in packets))
    water_export = float(sum(p['boundary_transfer_m3'].sum() for p in packets))
    final_volume = float(packets[-1]['depth_after_m'].sum()*spacing**2)
    solid_external = float(sum(solid_inputs))
    solid_export = float(np.asarray(solid_exports).sum())
    solid_initial = float(loose.sum())
    solid_final = float(final_loose.sum()+suspended.sum())
    sediment = dict(arrays=dict(initial_bed_m=bed, final_bed_m=current_bed, floor_m=floor,
        trace_bed_elevation_m=np.asarray(bed_trace), trace_mobile_solid_m3=np.asarray(mobile_trace),
        initial_alluvium_solid_m3=loose.reshape(bed.shape), final_alluvium_solid_m3=final_loose.reshape(bed.shape),
        interval_external_solid_m3=np.asarray(solid_inputs), interval_boundary_export_solid_m3=np.asarray(solid_exports),
        interval_internal_transfer_solid_m3=np.asarray(solid_faces),
        step_bulk_erosion_m3=erosion, step_bulk_deposition_m3=deposition),
        metadata=dict(status='complete', solver='metric_fv_bedload_v4 + metric_fv_suspended_supply',
            porosity=porosity, initial_rock_reserve_m3=float(native_rock_reserve.sum()),
            eroded_rock_m3=0., semantics='finite loose stock above source floor; no rock erosion; frozen water trace replay',
            final_rock_reserve_m3=float(native_rock_reserve.sum()),
            interval_ledgers=sediment_steps))
    native_row, native_col = np.indices(full.shape)
    return dict(status='complete', kind=region['kind'], region_id=region['id'], source_identity=m['source_identity'],
        terrain_identity=terrain['identity'], terrain_binding=terrain['binding'], boundary_package=package,
        downstream_boundary=dict(kind='finite-closed-control-volume', scenario=scenario,
            initial_water_source=initial_source, initial_water_m3=initial_volume, final_water_m3=final_volume,
            sea_connected_at_original_inlet=sea_inlet,
            coarse_lake_id=int(np.asarray(coarse.get('lake_id', np.zeros(shape))).ravel()[region['node']]),
            coarse_lake_water_consumed_m3=0., semantics='all cropped faces closed; stored water remains finite; no unknown land outlet'),
        replacement_accounting=dict(reversed_rock_removed_m3=reversed_rock,
            reversed_loose_change_solid_m3=reversed_loose, reversed_mobile_solid_m3=reversed_mobile,
            coarse_support_transfer_reversal_solid_m3=reversed_rock-reversed_loose-reversed_mobile,
            semantics='signed area/time coarse transfer reversal for the independent short event'),
        replaces_support_id=region['coarse_support_id'], consumed_package_id=package['id'],
        support_indices=support, replacement_arrays={key:np.asarray(value) for key,value in replacements.items()},
        native_arrays=dict(node=(native_row[rows,cols]*full.shape[1]+native_col[rows,cols]).ravel(),
            node_x_m=world_x.ravel(), node_z_m=world_z.ravel(), initial_bed_m=bed.ravel(),
            final_bed_m=current_bed.ravel(), area_m2=np.full(bed.size, spacing**2),
            initial_depth_m=initial_depth.ravel(), final_depth_m=packets[-1]['depth_after_m'],
            original_inlet_cell=np.array([inlet], np.int64), full_native_ocean_mask=sea.ravel(),
            initial_rock_reserve_m3=native_rock_reserve, final_rock_reserve_m3=native_rock_reserve.copy(),
            coarse_owner_node=coarse_nodes, coarse_stock_allocation=allocation),
        hydraulic=hydraulic, sediment=sediment,
        budgets=dict(boundary_water_m3=package['water_m3'], solver_water_input_m3=water_input,
            initial_water_m3=initial_volume, final_water_m3=final_volume,
            solver_water_export_m3=water_export, solver_water_storage_change_m3=final_volume-initial_volume,
            water_residual_m3=initial_volume+water_input-water_export-final_volume,
            boundary_solid_m3=package['solid_m3'], solver_external_solid_m3=solid_external,
            initial_alluvium_and_mobile_solid_m3=solid_initial, eroded_rock_m3=0.,
            final_alluvium_and_mobile_solid_m3=solid_final, exported_solid_m3=solid_export,
            solid_residual_m3=solid_initial+solid_external-solid_final-solid_export,
            coarse_equivalent_event_fraction=event_fraction),
        metadata=dict(completed_scope='declared representative short event only', scenario=scenario,
            window_origin_xz_m=origin, window_shape_zx=list(bed.shape), cells=int(bed.size),
            native_window_slices_zx=[[rows.start,rows.stop],[cols.start,cols.stop]],
            sampled_extent_xz_m=[origin,[float(world_x.max()),float(world_z.max())]],
            control_volume_extent_xz_m=[[origin[0]-spacing/2,origin[1]-spacing/2],
                [float(world_x.max()+spacing/2),float(world_z.max()+spacing/2)]],
            spacing_m=spacing, duration_s=duration, inlet_cell=int(inlet),
            inlet_xz_m=list(region['location_xz_m']),
            inlet_cell_center_xz_m=[float(world_x.ravel()[inlet]),float(world_z.ravel()[inlet])],
            inlet_point_to_cell_center_offset_xz_m=[float(world_x.ravel()[inlet]-x),float(world_z.ravel()[inlet]-z)],
            inlet_mapping='original point retained; source volume belongs to its containing native 30m finite-volume cell; no lower-bed or alternate candidate search',
            requested_location_xz_m=list(region['location_xz_m']),
            coarse_support_area_m2=[float(count*spacing**2) for count in counts],
            estimated_replay_bytes=trace_bytes, max_cells=max_cells,
            initial_water_source=initial_source, ocean_connectivity='full native source perimeter-connected D4 negatives before crop'),
        limitations=['complete only for the declared representative closed short event, not full downstream or seasonal lake equilibrium',
            'initially dry lake scenario consumes no saved coarse lake water; finite initial sea stock has no external stage replenishment',
            'raw native TD bed is retained; no excavation to remove adverse slopes',
            'local-inertia water omits advective momentum; sediment replays fixed water with reconstructed cell transverse velocity',
            'finite coarse loose stock only, no rock erosion; sediment bed changes require later hydraulic revalidation',
            'matching representative area/time coarse process fraction is replaced; no seasonal inventory handoff implied'])
