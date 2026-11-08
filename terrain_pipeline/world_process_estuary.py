"""Bounded native-TD estuary event using existing 2D FV water and bedload kernels.

Returns the same support/replacement/budget contract as solve_native_reach so
continue_details can publish one immutable product version. Missing ocean-edge
connectivity stays pending; still sea at 0 m is an explicit scenario when no
tide/wave driver is supplied.
"""
from __future__ import annotations

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.world_process_detail import boundary_package, validate_boundary


def _window(bed, first, spacing, location_xz_m, size):
    col = int(round((location_xz_m[0] - first[0]) / spacing))
    row = int(round((location_xz_m[1] - first[1]) / spacing))
    if not 0 <= row < bed.shape[0] or not 0 <= col < bed.shape[1]:
        raise ValueError('selected location lies outside prepared native TD tile')
    half = size // 2
    r0 = max(0, row - half)
    c0 = max(0, col - half)
    r1 = min(bed.shape[0], r0 + size)
    c1 = min(bed.shape[1], c0 + size)
    r0 = max(0, r1 - size)
    c0 = max(0, c1 - size)
    origin = [first[0] + c0 * spacing, first[1] + r0 * spacing]
    return slice(r0, r1), slice(c0, c1), origin, (row - r0, col - c0)


def _inlet_cell(bed, ocean, local_row, local_col):
    adjacent = np.zeros(bed.shape, bool)
    adjacent[1:] |= ocean[:-1]
    adjacent[:-1] |= ocean[1:]
    adjacent[:, 1:] |= ocean[:, :-1]
    adjacent[:, :-1] |= ocean[:, 1:]
    candidates = np.flatnonzero((bed >= 0.) & adjacent)
    if not candidates.size:
        raise ValueError('pending-estuary-driver: no land cell adjacent to sea-connected ocean in window')
    rows, cols = np.divmod(candidates, bed.shape[1])
    distance = abs(rows-local_row)+abs(cols-local_col)
    # Stable row-major tie breaking; one scan over the finite window.
    return int(candidates[np.argmin(distance)])


def solve_native_estuary(product, region, terrain, *, config=None):
    """Solve one representative still-sea estuary event on a cropped native TD window."""
    from terrain_pipeline import environment_delta_fv as fv

    cfg = config or {}
    bed_full = np.asarray(terrain['elevation_m'], np.float64)
    first = terrain['grid']['first_sample_xz_m']
    spacing = float(terrain['grid']['spacing_m'])
    if bed_full.ndim != 2 or not np.isfinite(bed_full).all() or spacing != 30.:
        raise ValueError('finite native TD terrain at explicit 30m spacing required')
    max_cells = cfg.get('max_estuary_cells', 65536)
    if type(max_cells) is not int or not 4 <= max_cells <= 65536:
        raise ValueError('estuary cell budget must be an integer within 4..65536')
    size = cfg.get('estuary_window_cells', int(np.sqrt(max_cells)))
    if type(size) is not int or size < 2:
        raise ValueError('positive estuary window side of at least two cells required')
    size = max(8, min(size, 256, bed_full.shape[0], bed_full.shape[1], int(np.sqrt(max_cells))))
    if size * size > max_cells:
        size = int(np.sqrt(max_cells))
    rows, cols, origin, local = _window(bed_full, first, spacing, region['location_xz_m'], size)
    bed = bed_full[rows, cols].copy()
    if bed.size > max_cells:
        raise ValueError('estuary window exceeds declared cell budget')
    from terrain_pipeline.ocean_island_consumers import connected_ocean
    # Determine sea connectivity on the entire prepared native source before
    # cropping. A closed lake touching only a crop edge is not an ocean inlet.
    sea = connected_ocean(bed_full)[rows, cols]
    if not np.r_[sea[:, 0], sea[:, -1], sea[0], sea[-1]].any():
        raise ValueError('pending-estuary-driver: estuary window needs ocean connected to the domain edge')
    inlet = _inlet_cell(bed, sea, local[0], local[1])
    package = boundary_package(product, region, terrain['identity'], duration_s=cfg.get('detail_duration_s', 30.))
    validate_boundary(package, source_identity=product['metadata']['source_identity'], terrain_identity=terrain['identity'])
    if package['discharge_m3_s'] <= 0:
        raise ValueError('no water available in coarse boundary')
    duration = package['interval_end_s'] - package['interval_start_s']
    coarse = product['arrays']
    m = product['metadata']
    cspacing = float(m['spacing_m'])
    cfirst = m['first_xz_m']
    # Map every native cell to a coarse support cell for inventory and replacement.
    zz, xx = np.indices(bed.shape)
    world_x = origin[0] + xx * spacing
    world_z = origin[1] + zz * spacing
    cx = np.rint((world_x - cfirst[0]) / cspacing).astype(int)
    cz = np.rint((world_z - cfirst[1]) / cspacing).astype(int)
    if np.any((cx < 0) | (cx >= coarse['elevation_m'].shape[1]) | (cz < 0) | (cz >= coarse['elevation_m'].shape[0])):
        raise ValueError('native estuary support extends outside known coarse world')
    coarse_nodes = (cz * coarse['elevation_m'].shape[1] + cx).ravel()
    porosity = float(np.mean(np.asarray(coarse.get('porosity', np.full(coarse['elevation_m'].shape, .35))).ravel()[np.unique(coarse_nodes)]))
    loose_density = np.asarray(coarse['loose_solid_m3']).ravel()[coarse_nodes] / cspacing ** 2
    # Nearest-centre ownership at a 30m/2000m boundary can assign slightly more
    # than one coarse footprint. Its finite source stock is never overdrawn.
    counts = np.bincount(coarse_nodes, minlength=coarse['elevation_m'].size)
    allocation = np.minimum(1., cspacing**2/(counts[coarse_nodes]*spacing**2))
    cover = (loose_density*allocation).reshape(bed.shape) / (1. - porosity)
    floor = bed - cover
    # Explicit still-sea mean stage; missing tide/wave is not recorded as measured zero tide.
    from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig
    from terrain_pipeline.surface_rivers.metric_fv_suspended_supply import SuspendedConfig
    bedload = BedloadConfig(porosity=porosity, manning_s_m_third=float(m['config']['roughness']),
                            wave_height_m=0., max_bed_change_m=float(cfg.get('estuary_max_bed_change_m', .05)))
    suspended = SuspendedConfig(porosity=porosity, max_bed_change_m=bedload.max_bed_change_m)
    delta_cfg = fv.FVDeltaConfig(
        coupling_interval_s=min(duration, float(cfg.get('estuary_coupling_interval_s', duration))),
        max_hydro_dt_s=float(cfg.get('estuary_max_hydro_dt_s', .5)),
        tide_amplitude_m=0.,
        sea_mean_m=0.,
        max_wall_s=float(cfg.get('estuary_max_wall_s', 120.)),
        max_halvings=int(cfg.get('estuary_max_halvings', 8)),
        bedload=bedload,
        suspended=suspended,
    )
    delta_cfg.validate()
    state = fv.initialize(
        bed, sea, np.asarray([inlet], np.int64),
        origin_m_xz=origin, source_world_identity=m['source_identity'],
        source_identity=terrain['identity'], spacing_m=spacing, floor_m=floor,
        erodible_cover_m=0., config=delta_cfg)
    # The generic delta initializer declares water at sea stage over every low
    # cell. This adapter has no lake-water handoff, so only connected sea has an
    # initial water stock; closed below-sea land remains dry in this event.
    if np.any((bed < 0.) & ~sea):
        initial_arrays = {key: value.copy() for key, value in state['arrays'].items()}
        initial_arrays['depth_m'] = np.where(sea, np.maximum(-bed, 0.), 0.)
        initial_metadata = dict(state['metadata'])
        initial_metadata['initial_water_m3'] = float(initial_arrays['depth_m'].sum()*spacing**2)
        initial_metadata['initial_water_source'] = 'declared still sea at 0m only on source-edge-connected ocean; no initial closed-lake water supplied'
        state = dict(arrays=initial_arrays, metadata=initial_metadata,
                     identity_sha256=identity(initial_arrays, initial_metadata))
        fv.validate(state)
    forcing = dict(id=package['id'], source='coarse-world-boundary-package',
                   time_start_s=0., time_end_s=duration,
                   water_m3=package['water_m3'], solid_m3=package['solid_m3'])
    try:
        advanced = fv.advance(state, [forcing])
    except (ValueError, RuntimeError, MemoryError) as exc:
        raise ValueError('pending-estuary-driver: ' + str(exc)) from exc
    final_bed = np.asarray(advanced['arrays']['bed_m'], np.float64)
    delta = final_bed - bed
    support = np.unique(coarse_nodes)
    area = np.full(bed.size, spacing ** 2)
    event_fraction = min(1., duration / (m['config']['shaping_rounds'] * m['config']['equivalent_exposure_seconds']))
    replacement, loose_replacement, rock_replacement = [], [], []
    erosion_replacement, deposition_replacement, mobile_replacement = [], [], []
    reversed_rock = reversed_loose_change = reversed_mobile = 0.
    for coarse_node in support:
        use = coarse_nodes == coarse_node
        fraction = min(1., float(area[use].sum() / cspacing ** 2))
        coarse_change = (coarse['elevation_m'].ravel()[coarse_node]
                         - coarse.get('shaping_initial_elevation_m', coarse['initial_elevation_m']).ravel()[coarse_node]) * fraction * event_fraction
        detailed_change = float(np.sum(delta.ravel()[use] * area[use]) / cspacing ** 2)
        replacement.append(coarse['elevation_m'].ravel()[coarse_node] - coarse_change + detailed_change)
        coarse_erosion = float(np.asarray(coarse.get('erosion_m', np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        coarse_deposition = float(np.asarray(coarse.get('deposition_m', np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        fine_erosion = float(np.maximum(-delta.ravel()[use], 0.).sum() * spacing ** 2 / cspacing ** 2)
        fine_deposition = float(np.maximum(delta.ravel()[use], 0.).sum() * spacing ** 2 / cspacing ** 2)
        erosion_replacement.append(coarse_erosion * (1 - fraction * event_fraction) + fine_erosion)
        deposition_replacement.append(coarse_deposition * (1 - fraction * event_fraction) + fine_deposition)
        initial_native_loose = float(cover.ravel()[use].sum() * spacing ** 2 * (1. - porosity))
        final_native_loose = float(np.maximum(final_bed.ravel()[use] - floor.ravel()[use], 0.).sum() * spacing ** 2 * (1. - porosity))
        old_loose = float(coarse['loose_solid_m3'].ravel()[coarse_node])
        original_loose = float(np.asarray(coarse.get('shaping_initial_loose_solid_m3', coarse.get('initial_loose_solid_m3', coarse['loose_solid_m3']))).ravel()[coarse_node])
        loose_replacement.append(old_loose - (old_loose - original_loose) * fraction * event_fraction + final_native_loose - initial_native_loose)
        old_rock = float(np.asarray(coarse.get('rock_removed_m3', np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        original_rock = float(np.asarray(coarse.get('shaping_initial_rock_removed_m3', np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        rock_delta = float(np.maximum(floor.ravel()[use] - final_bed.ravel()[use], 0.).sum() * spacing ** 2)
        rock_replacement.append(old_rock - (old_rock - original_rock) * fraction * event_fraction + rock_delta)
        old_mobile = float(np.asarray(coarse.get('mobile_solid_m3', np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        suspended = float(np.asarray(advanced['arrays']['suspended_solid_m3']).ravel()[use].sum())
        mobile_replacement.append(old_mobile * (1 - fraction * event_fraction) + suspended)
        reversed_rock += (old_rock - original_rock) * fraction * event_fraction
        reversed_loose_change += (old_loose - original_loose) * fraction * event_fraction
        reversed_mobile += old_mobile * fraction * event_fraction
    ledger = advanced['metadata']['ledger']
    water_input = float(ledger['water_input_m3'])
    water_export = float(ledger['water_export_m3'])
    sea_import = float(ledger['sea_import_m3'])
    water_storage = float(advanced['arrays']['depth_m'].sum() * spacing ** 2 - advanced['metadata']['initial_water_m3'])
    solid_external = float(ledger['solid_input_m3'])
    solid_export = float(ledger['solid_export_m3'])
    solid_initial = float(advanced['metadata']['initial_bed_solid_m3'])
    solid_final = float(((final_bed - advanced['arrays']['floor_m']) * spacing ** 2 * (1. - porosity)).sum()
                        + advanced['arrays']['suspended_solid_m3'].sum())
    hydraulic = dict(arrays=dict(depth_m=np.asarray(advanced['arrays']['depth_m']),
                                 momentum_m2_s=np.asarray(advanced['arrays']['momentum_m2_s']),
                                 time_seconds=np.asarray([0., duration])),
                     metadata=dict(status='complete', solver='environment_delta_fv.advance_growth',
                                   underlying_solvers=advanced['metadata']['underlying_solvers'],
                                   sea_scenario='still-sea-mean-0m-no-tide-driver',
                                   sea_import_m3=sea_import, water_export_m3=water_export))
    sediment = dict(arrays=dict(final_bed_m=final_bed, initial_bed_m=bed, floor_m=np.asarray(advanced['arrays']['floor_m']),
                                external_solid_m3=np.asarray([solid_external]),
                                suspended_solid_m3=np.asarray(advanced['arrays']['suspended_solid_m3']),
                                exported_solid_m3=np.asarray([solid_export])),
                    metadata=dict(status='complete', solver='metric_fv_coastal bedload+suspended',
                                  solid_export_m3=solid_export))
    return dict(status='complete', kind=region['kind'], region_id=region['id'], source_identity=m['source_identity'],
        terrain_identity=terrain['identity'], terrain_binding=terrain['binding'], boundary_package=package,
        downstream_boundary=dict(kind='still-sea-edge', sea_mean_m=0., tide_amplitude_m=0.,
            semantics='fixed mean sea stage; missing tide/wave driver is still-sea, not measured zero tide'),
        replacement_accounting=dict(reversed_rock_removed_m3=reversed_rock,
            reversed_loose_change_solid_m3=reversed_loose_change, reversed_mobile_solid_m3=reversed_mobile,
            coarse_support_transfer_reversal_solid_m3=reversed_rock - reversed_loose_change - reversed_mobile,
            semantics='signed reversal of the coarse support transfer for the replaced area/time; geological and generation environment beds are retained'),
        replaces_support_id=region['coarse_support_id'], consumed_package_id=package['id'],
        support_indices=support,
        replacement_arrays=dict(elevation_m=np.asarray(replacement), loose_solid_m3=np.asarray(loose_replacement),
            rock_removed_m3=np.asarray(rock_replacement), mobile_solid_m3=np.asarray(mobile_replacement),
            erosion_m=np.asarray(erosion_replacement), deposition_m=np.asarray(deposition_replacement)),
        native_arrays=dict(node=np.arange(bed.size, dtype=np.int64), node_x_m=world_x.ravel(), node_z_m=world_z.ravel(),
            initial_bed_m=bed.ravel(), final_bed_m=final_bed.ravel(), area_m2=area,
            depth_m=np.asarray(advanced['arrays']['depth_m']).ravel(), inlet_cell=np.asarray([inlet]),
            initial_ocean_mask=sea.ravel()),
        hydraulic=hydraulic, sediment=sediment,
        budgets=dict(boundary_water_m3=package['water_m3'], solver_water_input_m3=water_input,
            solver_water_export_m3=water_export, solver_water_storage_change_m3=water_storage,
            sea_import_m3=sea_import,
            water_residual_m3=water_input + sea_import - water_export - water_storage,
            boundary_solid_m3=package['solid_m3'], solver_external_solid_m3=solid_external,
            initial_alluvium_and_mobile_solid_m3=solid_initial, eroded_rock_m3=0.,
            final_alluvium_and_mobile_solid_m3=solid_final, exported_solid_m3=solid_export,
            solid_residual_m3=solid_initial + solid_external - solid_final - solid_export,
            coarse_equivalent_event_fraction=event_fraction),
        metadata=dict(sea_scenario='still-sea-mean-0m-no-tide-driver', window_origin_xz_m=origin,
            window_shape_zx=list(bed.shape), inlet_cell=int(inlet),
            inlet_xz_m=[float(world_x.ravel()[inlet]), float(world_z.ravel()[inlet])],
            ocean_connectivity='negative cells connected to the full native TD source perimeter before cropping',
            fv_identity=advanced['identity_sha256']),
        limitations=['representative short still-sea event; not a full tidal estuary solve',
            'only the matching representative fraction of coarse equivalent process is replaced over actual rectangular support area',
            'finite loose cover from coarse inventory; sea is not an infinite sand source',
            'D4 FV faces only; no D8 drainage path is introduced'])
