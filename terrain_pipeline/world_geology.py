"""Forward, event-driven geological columns for explicitly sourced world terrain.

This is a generation history, not a reconstruction of an observed geological past.
The offline tectonic endpoints supply an explicitly declared kinematic trend. Saved
operations can be replayed without noise, tectonic inference, or access to a model.
"""
from __future__ import annotations

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.geology import ROCK_ORDER, rock_table, rock_table_identity, _value_noise

ALGORITHM = 'world-event-geology-v1'
SCHEMA = 'world-event-geology-columns-v1'

# Explicit illustrative intrinsic permeability, m². These are declared material
# references, not estimates obtained by converting porosity to permeability.
PERMEABILITY_M2 = dict(granite=1e-17, basalt=1e-15, andesite=1e-16,
    rhyolite=1e-17, gabbro=1e-18, tuff=1e-13, limestone=1e-13,
    sandstone=1e-12, shale=1e-19, conglomerate=1e-11, mudstone=1e-18,
    dolomite=3e-14, schist=1e-17, gneiss=1e-18, marble=1e-18,
    quartzite=1e-18, slate=1e-19, hornfels=1e-19)


def _number(value, name, lower, upper):
    if isinstance(value, (bool, np.bool_)) or not np.isscalar(value) or not np.isfinite(value) or not lower <= value <= upper:
        raise ValueError(name + ' outside finite supported bounds')
    return float(value)


def _fields(fields):
    if fields is None:
        raise ValueError('actual initial tectonic fields required; final-only worlds cannot acquire a recovered history')
    result = {name: np.asarray(fields[name], np.float64) for name in ('elevation_m', 'continental_fraction', 'plate_id')}
    shape = result['elevation_m'].shape
    if len(shape) != 2 or min(shape) < 1 or np.prod(shape) > 262144:
        raise ValueError('geological skeleton must contain 1..262144 cells')
    if any(a.shape != shape or not np.isfinite(a).all() for a in result.values()):
        raise ValueError('finite common geological field shape required')
    if np.any((result['continental_fraction'] < 0) | (result['continental_fraction'] > 1)):
        raise ValueError('continental_fraction must be within 0..1')
    return result


def build_history(initial_fields, final_fields, *, world_seed, origin_xz_m,
                  spacing_m, stages=50, span_ma=500., initial_source_identity,
                  final_source_identity):
    """Generate columns forward from a declared initial state and save operations.

    ``origin_xz_m`` is the outer cell corner; samples are at half a cell.
    Optional final ``raw_elevation_m`` separates tectonic elevation from layout.
    Offline steps are mapped linearly onto event ages; no physical calibration
    or recovered migration trajectory is implied by the endpoint trend.
    """
    initial = _fields(initial_fields)
    final = _fields(final_fields)
    if initial['elevation_m'].shape != final['elevation_m'].shape:
        raise ValueError('initial/final geological grids differ')
    if type(stages) is not int or not 1 <= stages <= 60:
        raise ValueError('stages must be an integer in 1..60')
    span_ma = _number(span_ma, 'span_ma', 1., 4500.)
    spacing_m = _number(spacing_m, 'spacing_m', 1., 100000.)
    if type(world_seed) is not int or not 0 <= world_seed < 2**64:
        raise ValueError('unsigned world_seed required')
    if len(origin_xz_m) != 2 or not np.isfinite(origin_xz_m).all():
        raise ValueError('finite absolute origin required')
    if any(not isinstance(v, str) or not v for v in (initial_source_identity, final_source_identity)):
        raise ValueError('explicit initial and final source identities required')
    shape = initial['elevation_m'].shape
    zz, xx = np.indices(shape)
    x = origin_xz_m[0] + (xx + .5) * spacing_m
    z = origin_xz_m[1] + (zz + .5) * spacing_m
    patch = _value_noise(x, z, max(3 * spacing_m, 30000.), world_seed ^ 0x67656F)
    raw_final = np.asarray(final_fields.get('raw_elevation_m', final['elevation_m']), np.float64)
    if raw_final.shape != shape or not np.isfinite(raw_final).all():
        raise ValueError('finite raw final tectonic elevation required')
    trend = raw_final - initial['elevation_m']
    trajectory = initial_fields.get('stage_elevation_m', final_fields.get('history_elevation_m'))
    trajectory_source = 'linear offline-endpoint kinematic trend; intermediate states are generation assumptions'
    stage_displacements = np.broadcast_to(trend / stages,(stages,)+shape).copy()
    if trajectory is not None:
        trajectory = np.asarray(trajectory,np.float64)
        if trajectory.ndim != 3 or trajectory.shape[1:] != shape or not 2 <= len(trajectory) <= 1001 or not np.isfinite(trajectory).all():
            raise ValueError('finite ordered tectonic checkpoint elevations required')
        if not np.allclose(trajectory[0],initial['elevation_m'],rtol=0,atol=1e-6) or not np.allclose(trajectory[-1],raw_final,rtol=0,atol=1e-6):
            raise ValueError('tectonic trajectory must bind actual initial and raw final elevations')
        positions_in_trace = np.linspace(0,len(trajectory)-1,stages+1)
        lower = np.floor(positions_in_trace).astype(int)
        upper = np.minimum(lower+1,len(trajectory)-1)
        fraction = (positions_in_trace-lower)[:,None,None]
        mapped = trajectory[lower] * (1-fraction) + trajectory[upper] * fraction
        stage_displacements = np.diff(mapped,axis=0)
        trajectory_source = 'saved forward tectonic checkpoints linearly mapped from offline step index to declared geological ages; no physical time calibration'
    def map_trace(name, fallback):
        supplied = initial_fields.get('stage_' + name)
        if supplied is None:
            return np.broadcast_to(fallback, (stages + 1,) + shape)
        trace = np.asarray(supplied, np.float64)
        if trajectory is None or trace.shape != trajectory.shape or not np.isfinite(trace).all():
            raise ValueError('material/plate trace must match ordered elevation trajectory: ' + name)
        if not np.allclose(trace[0], initial[name], rtol=0, atol=1e-6) or not np.allclose(trace[-1], final[name], rtol=0, atol=1e-6):
            raise ValueError('material/plate trace endpoints differ: ' + name)
        if name == 'plate_id':
            return trace[np.floor(positions_in_trace).astype(int)]
        return trace[lower] * (1-fraction) + trace[upper] * fraction
    continental_trace = map_trace('continental_fraction', final['continental_fraction'])
    plate_trace = map_trace('plate_id', final['plate_id'])
    elevation_trace = (np.concatenate([initial['elevation_m'][None],
        initial['elevation_m'][None] + np.cumsum(stage_displacements, axis=0)], axis=0))
    operations = {}
    float_ops = ('tectonic_displacement_m', 'deposition_thickness_m', 'erosion_depth_m',
                 'fault_displacement_m', 'fold_displacement_m', 'volcanic_thickness_m')
    for name in float_ops:
        operations[name] = np.zeros((stages,) + shape, np.float64)
    for name in ('metamorphism_mask', 'intrusion_mask'):
        operations[name] = np.zeros((stages,) + shape, bool)
    operations['deposition_rock_index'] = np.zeros((stages,) + shape, np.uint8)
    positions = {name: i for i, name in enumerate(ROCK_ORDER)}
    stage_duration_scale = span_ma / stages / 10.
    events = []
    previous = None
    for step in range(stages):
        phase = (step + .5) / stages
        continental = continental_trace[step + 1]
        stage_elevation = elevation_trace[step + 1]
        ocean_crust = continental < .3
        # Settings follow the actual saved stage, rather than applying the
        # final plate layout to the entire declared geological past.
        uplift = stage_displacements[step] > 250. / stages
        basin = (stage_displacements[step] < -100. / stages) | ((stage_elevation < 200.) & ~ocean_crust)
        boundary = np.zeros(shape, bool)
        for axis in (0, 1):
            adjacent = np.diff(plate_trace[step + 1], axis=axis) != 0
            lo = [slice(None), slice(None)]
            hi = [slice(None), slice(None)]
            lo[axis] = slice(0, -1)
            hi[axis] = slice(1, None)
            boundary[tuple(lo)] |= adjacent
            boundary[tuple(hi)] |= adjacent
        arc = boundary & uplift & (continental < .8)
        operations['tectonic_displacement_m'][step] = stage_displacements[step]
        deposition = basin * (1. - phase * .4) * (2. + patch * 8.) * stage_duration_scale
        operations['deposition_thickness_m'][step] = deposition
        operations['erosion_depth_m'][step] = uplift * (1. + patch * 3.) * stage_duration_scale
        if step % 10 == 4:
            operations['fault_displacement_m'][step] = boundary * (patch - .5) * np.minimum(abs(trend) * .08, 120.)
        if step % 10 == 5:
            operations['fold_displacement_m'][step] = uplift * np.sin(x / max(8 * spacing_m, 80000.) + phase * 3.) * 12.
        operations['metamorphism_mask'][step] = uplift & (step >= stages // 3)
        operations['intrusion_mask'][step] = uplift & boundary & (patch > .62) & (step % 13 == 7)
        operations['volcanic_thickness_m'][step] = arc * (patch > .55) * (step % 9 == 3) * (25. + 30 * patch)
        # Basin facies alternate by age and position; noise modifies only a
        # tectonically admissible sedimentary environment.
        facies = np.where(patch < .35, positions['shale'], positions['sandstone'])
        if step % 4 == 2:
            facies = np.where(stage_elevation < 0., positions['limestone'], facies)
        operations['deposition_rock_index'][step] = facies
        kinds = [('tectonic', stage_displacements[step] != 0), ('deposition', deposition > 0),
                 ('erosion_unconformity', operations['erosion_depth_m'][step] > 0),
                 ('fault', operations['fault_displacement_m'][step] != 0),
                 ('fold', operations['fold_displacement_m'][step] != 0),
                 ('burial_metamorphism', operations['metamorphism_mask'][step]),
                 ('intrusion', operations['intrusion_mask'][step]),
                 ('volcanism', operations['volcanic_thickness_m'][step] > 0)]
        for kind, mask in kinds:
            if not mask.any():
                continue
            event_id = 'geology-%03d-%s' % (step, kind)
            points = np.argwhere(mask)
            field_by_kind = dict(tectonic='tectonic_displacement_m',deposition='deposition_thickness_m',
                erosion_unconformity='erosion_depth_m',fault='fault_displacement_m',fold='fold_displacement_m',
                burial_metamorphism='metamorphism_mask',intrusion='intrusion_mask',volcanism='volcanic_thickness_m')
            events.append(dict(id=event_id, stage=step, kind=kind,
                older_ma=span_ma * (1 - step / stages), younger_ma=span_ma * (1 - (step + 1) / stages),
                array_reference=field_by_kind[kind], array_stage=step,
                mask_rule=('nonzero' if kind not in ('deposition','erosion_unconformity','volcanism') else 'positive'),
                bounds_cells_zx=[points.min(axis=0).tolist(), (points.max(axis=0) + 1).tolist()],
                bounds_m=[float(origin_xz_m[0]+points[:,1].min()*spacing_m),
                          float(origin_xz_m[1]+points[:,0].min()*spacing_m),
                          float(origin_xz_m[0]+(points[:,1].max()+1)*spacing_m),
                          float(origin_xz_m[1]+(points[:,0].max()+1)*spacing_m)],
                affected_cells=int(mask.sum()), predecessor=previous,
                layer_change=('append chronological layer %d' % (step+1) if kind in ('deposition','volcanism') else
                    'truncate intersected older layers' if kind == 'erosion_unconformity' else
                    'replace buried material with metamorphic rock' if kind == 'burial_metamorphism' else
                    'replace buried material with granite' if kind == 'intrusion' else 'displace existing layer horizons'),
                material_source=('declared_magmatic_external' if kind in ('intrusion','volcanism') else
                                 'declared_basin_external_sediment' if kind == 'deposition' else 'existing_column')))
            previous = event_id
    initial_rock = np.where(initial['continental_fraction'] >= .5, positions['granite'], positions['gabbro']).astype(np.uint8)
    arrays = dict(initial_elevation_m=initial['elevation_m'].copy(), initial_basement_rock_index=initial_rock,
                  final_layout_elevation_m=final['elevation_m'].copy(), final_raw_tectonic_elevation_m=raw_final.copy(), **operations)
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, world_seed=world_seed,
        origin_xz_m=list(map(float, origin_xz_m)), spacing_m=spacing_m, shape_zx=list(shape),
        stages=stages, span_ma=span_ma, stage_duration_ma=span_ma / stages,
        initial_source_identity=initial_source_identity, final_source_identity=final_source_identity,
        time_mapping=trajectory_source,
        history_status='forward_generated_approximation_from_declared_initial_state',
        basement='declared prehistory: continental granite / oceanic gabbro; no claimed prior event record',
        events=events, rock_table_identity=rock_table_identity(),
        trajectory_identity=(None if trajectory is None else identity(
            dict(elevation_m=trajectory, continental_fraction=continental_trace, plate_id=plate_trace),
            dict(source=initial_source_identity, offline_samples=len(trajectory), mapped_stages=stages))),
        permeability=dict(values_m2=PERMEABILITY_M2, source='explicit illustrative intrinsic material references; uncalibrated; not derived from porosity'),
        limitations=['vertical columns with local horizon offsets; no lateral thrust duplication or overhangs',
                     'offline-step to geological-age mapping is a declared generation approximation',
                     'basin and magmatic supplies are generation exogenous terms, not conserved transfers from neighboring cells'])
    result = dict(arrays=arrays, metadata=metadata)
    columns = replay_history(result)
    arrays.update(columns['arrays'])
    metadata['budgets'] = columns['budgets']
    metadata['identity'] = identity(arrays, metadata)
    return result


def replay_history(history):
    """Replay the saved event program; all thicknesses are bulk rock metres."""
    a, m = history['arrays'], history['metadata']
    stages = m['stages']
    shape = a['initial_elevation_m'].shape
    base = np.zeros((stages + 1,) + shape, np.float64)
    top = np.zeros_like(base)
    rock = np.zeros(base.shape, np.uint8)
    surface = np.asarray(a['initial_elevation_m'], np.float64).copy()
    base[0] = surface - 30000.
    top[0] = surface
    rock[0] = a['initial_basement_rock_index']
    initial_bottom = base[0].copy()
    area = m['spacing_m'] ** 2
    ledger = dict(initial_rock_bulk_m3=float(30000. * surface.size * area),
                  sediment_external_bulk_m3=0., volcanic_external_bulk_m3=0.,
                  erosion_export_bulk_m3=0., tectonic_displacement_volume_m3=0.,
                  intrusion_replacement_bulk_m3=0., metamorphic_replacement_bulk_m3=0.)
    positions = {name: i for i, name in enumerate(ROCK_ORDER)}
    metamorphic = np.arange(len(ROCK_ORDER), dtype=np.uint8)
    for old, new in (('granite','gneiss'), ('gabbro','schist'), ('basalt','schist'),
                     ('sandstone','quartzite'), ('limestone','marble'), ('shale','slate')):
        metamorphic[positions[old]] = positions[new]
    for stage in range(stages):
        count = stage + 1
        displacement = (a['tectonic_displacement_m'][stage] + a['fault_displacement_m'][stage]
                        + a['fold_displacement_m'][stage])
        base[:count] += displacement
        top[:count] += displacement
        surface += displacement
        ledger['tectonic_displacement_volume_m3'] += float(displacement.sum() * area)
        thickness = np.maximum(top[:count] - base[:count], 0.)
        burial = surface - .5 * (base[:count] + top[:count])
        mask = a['metamorphism_mask'][stage][None] & (burial > 2000.) & (thickness > 0)
        converted = metamorphic[rock[:count]]
        ledger['metamorphic_replacement_bulk_m3'] += float(thickness[mask & (converted != rock[:count])].sum() * area)
        rock[:count] = np.where(mask, converted, rock[:count])
        intrusion = a['intrusion_mask'][stage][None] & (burial > 500.) & (thickness > 0)
        ledger['intrusion_replacement_bulk_m3'] += float(thickness[intrusion].sum() * area)
        rock[:count] = np.where(intrusion, positions['granite'], rock[:count])
        # Erosion truncates every intersected horizon, exposing the older layer.
        erosion = np.minimum(a['erosion_depth_m'][stage], np.maximum(surface - base[0], 0.))
        surface -= erosion
        top[:count] = np.maximum(base[:count], np.minimum(top[:count], surface))
        ledger['erosion_export_bulk_m3'] += float(erosion.sum() * area)
        sediment = a['deposition_thickness_m'][stage]
        volcanic = a['volcanic_thickness_m'][stage]
        # Volcanic cells and basin facies have distinct admissibility masks.
        thickness = sediment + volcanic
        base[count] = surface
        top[count] = surface + thickness
        rock[count] = np.where(volcanic > 0., positions['andesite'], a['deposition_rock_index'][stage])
        surface += thickness
        ledger['sediment_external_bulk_m3'] += float(sediment.sum() * area)
        ledger['volcanic_external_bulk_m3'] += float(volcanic.sum() * area)
    # Only the declared procedural layout displacement is a layout correction.
    # Do not force the geological surface back to the target after every event:
    # that would erase fault offsets, deposition and denudation from horizons.
    raw_final = a.get('final_raw_tectonic_elevation_m', a['initial_elevation_m'] + a['tectonic_displacement_m'].sum(axis=0))
    offset = a['final_layout_elevation_m'] - raw_final
    base += offset
    top += offset
    final_volume = float(np.maximum(top - base, 0.).sum() * area)
    ledger['final_rock_bulk_m3'] = final_volume
    ledger['rock_bulk_residual_m3'] = (ledger['initial_rock_bulk_m3'] + ledger['sediment_external_bulk_m3']
        + ledger['volcanic_external_bulk_m3'] - ledger['erosion_export_bulk_m3'] - final_volume)
    ledger['layout_vertical_displacement_m3'] = float(offset.sum() * area)
    return dict(arrays=dict(layer_bottom_m=base, layer_top_m=top, layer_rock_index=rock,
                           geological_surface_m=surface+offset, layout_correction_m=offset), budgets=ledger)


def sample_materials(history, x_m, z_m, elevation_m):
    """Sample the material actually intersected at an absolute metric height.

    Sampling above a column returns its exposed uppermost material, while query
    below the declared 30km basement or outside the finite source is rejected.
    """
    a, m = history['arrays'], history['metadata']
    x, z, h = np.broadcast_arrays(np.asarray(x_m, np.float64), np.asarray(z_m, np.float64), np.asarray(elevation_m, np.float64))
    if not all(np.isfinite(v).all() for v in (x,z,h)):
        raise ValueError('finite absolute material coordinates required')
    ix = np.floor((x - m['origin_xz_m'][0]) / m['spacing_m']).astype(np.int64)
    iz = np.floor((z - m['origin_xz_m'][1]) / m['spacing_m']).astype(np.int64)
    nz, nx = m['shape_zx']
    if np.any((ix < 0) | (ix >= nx) | (iz < 0) | (iz >= nz)):
        raise ValueError('material query outside geological support')
    index = np.zeros(x.shape, np.uint8)
    layer_index = np.zeros(x.shape, np.uint8)
    floor = a['layer_bottom_m'][0, iz, ix]
    if np.any(h < floor):
        raise ValueError('material query below declared basement support')
    for layer in range(a['layer_top_m'].shape[0]):
        bottom = a['layer_bottom_m'][layer, iz, ix]
        top = a['layer_top_m'][layer, iz, ix]
        selected = (top > bottom) & (h >= bottom)
        index = np.where(selected, a['layer_rock_index'][layer, iz, ix], index)
        layer_index = np.where(selected, layer, layer_index)
    table = rock_table()
    result = dict(rock_index=index, layer_index=layer_index)
    for output, key in (('bed_hardness','bed_hardness'), ('bank_hardness','bank_hardness'),
                        ('porosity','porosity'), ('erodibility','erodibility_index'),
                        ('solubility','solubility'), ('fracture_density','fracture_density')):
        result[output] = np.asarray([record[key] for record in table], np.float64)[index]
    result['permeability_m2'] = np.asarray([PERMEABILITY_M2[name] for name in ROCK_ORDER])[index]
    result['soil_thickness_m'] = .2 + result['erodibility'] * .8
    result['source_identity'] = m['identity'] if 'identity' in m else identity(a,m)
    result['provenance'] = dict(algorithm=ALGORITHM, rock_table_identity=m['rock_table_identity'],
        permeability=m['permeability'], exposure='actual query elevation intersects displaced, truncated chronological columns')
    return result
