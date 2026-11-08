"""Sea-side connected prism validation on a saved annual delta bed.

The prescribed tide drives a reduced water/salt reservoir exchange, not a 2D
momentum solution or an along-creek velocity estimate. No river packet is replayed.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_propagation

from .complete_delta import load_run, sha256
from terrain_pipeline.environment_processes import _connected, initialize_coastal_exchange, advance_coastal_exchange

SCHEMA = 'complete-delta-tidal-validation-v1'
PERIOD_S = 44712.
AMPLITUDE_M = .65
VISIBLE_WATER_DEPTH_M = .01


def creek_coverage_checks(bed, core, reachable, snapshot_water_m3, spacing_m):
    """Require the complete negative-bed creek core, not one wet pixel."""
    negative_core = np.asarray(core, bool) & (bed < 0.)
    count = int(negative_core.sum())
    visible = np.asarray(snapshot_water_m3)/spacing_m**2 >= VISIBLE_WATER_DEPTH_M
    coverage = [dict(core_cells=count,
        connected_cells=int(np.count_nonzero(mask & negative_core)),
        connected_fraction=float(np.count_nonzero(mask & negative_core)/count) if count else 0.)
        for mask in reachable]
    checks = dict(negative_core_nonempty=count>0,
        mean_tide_entire_negative_core_connected=bool(count and np.all(reachable[1][negative_core])),
        high_tide_entire_negative_core_connected=bool(count and np.all(reachable[2][negative_core])),
        high_tide_entire_negative_core_visibly_wet=bool(count and np.all(visible[2][negative_core])),
        creek_visible_low_high_area_changes=bool(np.count_nonzero(visible[2] & core)>
            np.count_nonzero(visible[0] & core)))
    return checks, coverage, visible


def path_connection_coverage(scene, metadata, reachable):
    points, offsets = scene['tidal_creek_points_xz_m'], scene['tidal_creek_offsets']
    origin, spacing = np.asarray(metadata['origin_xz_m']), float(metadata['spacing_m'])
    records = []
    for index, (start, stop) in enumerate(zip(offsets[:-1], offsets[1:])):
        path = points[start:stop]
        dense = []
        for a,b in zip(path[:-1], path[1:]):
            dense.append(np.linspace(a,b,max(2,int(np.ceil(np.linalg.norm(b-a)/(spacing/4.)))+1)))
        samples = np.concatenate(dense) if dense else path
        ij = np.floor((samples-origin)/spacing+.5).astype(int)
        inside = (ij[:,0]>=0)&(ij[:,0]<reachable.shape[2])&(ij[:,1]>=0)&(ij[:,1]<reachable.shape[1])
        counts = [int(np.count_nonzero(mask[ij[inside,1],ij[inside,0]])) for mask in reachable]
        records.append(dict(path_index=index, sample_count=len(ij), outside_samples=int(np.count_nonzero(~inside)),
            connected_samples_low_mean_high=counts,
            connected_fraction_low_mean_high=[count/len(ij) if len(ij) else 0. for count in counts]))
    return records


def tidal_context(bed, scene, metadata):
    """Keep the original sea boundary as seed; protected river cannot bridge pools."""
    protected = scene['tidal_protected_river_mask'].astype(bool)
    valid = ~protected
    original = scene['tidal_original_marine_seed_mask'].astype(bool) & valid
    seeds = np.zeros_like(valid)
    seeds[[0, -1], :] = original[[0, -1], :]
    seeds[:, [0, -1]] = original[:, [0, -1]]
    seeds = binary_propagation(seeds, mask=original)
    if not seeds.any():
        raise ValueError('original marine seed has no external sea boundary connection')
    return dict(height_m=np.asarray(bed, float), spacing_m=float(metadata['spacing_m']),
        origin_native_xz=np.rint(metadata['origin_xz_m']).astype(np.int64),
        world_seed=int(metadata.get('world_seed', 20261020)), valid_mask=valid,
        protected_mask=protected, ocean_mask=seeds, river_mask=protected,
        receiver=np.full(bed.shape, -1, np.int64))


def scene_tide_forcing(metadata):
    """Read one complete design boundary; legacy scenes retain their old tide."""
    design = metadata.get('tidal_coast_construction', {})
    keys = ('design_low_stage_m', 'design_high_stage_m', 'design_period_s')
    present = [key in design for key in keys]
    if any(present) and not all(present):
        raise ValueError('scene tidal design requires low stage, high stage and period together')
    if not any(present):
        return dict(amplitude_m=AMPLITUDE_M, period_s=PERIOD_S,
            mean_sea_level_m=0., source='legacy default: scene has no tidal design boundary')
    low, high, period = (float(design[key]) for key in keys)
    if not np.isfinite([low, high, period]).all() or period <= 0. or low >= high:
        raise ValueError('scene tidal design requires finite ordered levels and positive period')
    if not np.isclose(low+high, 0., rtol=0., atol=1.e-12):
        raise ValueError('scene tidal design must be symmetric about zero sea level')
    return dict(amplitude_m=(high-low)/2., period_s=period,
        mean_sea_level_m=0., source='scene.metadata.tidal_coast_construction')


def simulate_tides(context, creek_mask, *, amplitude_m=AMPLITUDE_M,
                   period_s=PERIOD_S):
    """Run two complete physical periods, retaining second-period phase snapshots."""
    if not np.isfinite([amplitude_m, period_s]).all() or amplitude_m < 0. or period_s <= 0.:
        raise ValueError('finite nonnegative amplitude and positive tide period required')
    bed = context['height_m']
    area = context['spacing_m']**2
    state = initialize_coastal_exchange(context, mobile_thickness_m=0.)
    initial_water = float(state['water_m3'].sum())
    initial_salt = float(state['salt_kg'].sum())
    totals = dict(signed_ocean_water_m3=0., signed_ocean_salt_kg=0.,
        river_water_input_m3=0., river_solid_input_m3=0.,
        flood_water_m3=0., ebb_water_m3=0., creek_flood_water_m3=0., creek_ebb_water_m3=0.,
        flood_salt_kg=0., ebb_salt_kg=0., creek_flood_salt_kg=0., creek_ebb_salt_kg=0.,
        water_residual_m3=0., salt_residual_kg=0., solid_residual_m3=0.)
    snapshots = {}
    records = []
    forcing = dict(tide_amplitude_m=amplitude_m, tide_period_s=period_s,
        mean_sea_level_m=0., wave_height_m=0., river_boundary_water_m3_s=0.,
        river_boundary_solid_m3_s=0., ocean_salinity_kg_m3=35.)
    # 32 intervals per real period; the exchange kernel further bounds dt to 900 s.
    for index in range(64):
        result = advance_coastal_exchange(state, forcing, context, period_s/32.)
        state = result['state']
        flux, ledger = result['fluxes'], result['ledger']
        for key in ('signed_ocean_water_m3', 'signed_ocean_salt_kg',
                    'river_water_input_m3', 'river_solid_input_m3',
                    'water_residual_m3', 'salt_residual_kg', 'solid_residual_m3'):
            totals[key] += ledger[key]
        for key in ('flood_water_m3', 'ebb_water_m3'):
            totals[key] += float(flux[key].sum())
            totals['creek_'+key] += float(flux[key][creek_mask].sum())
        # The fixed 35 kg/m3 reservoir and initially uniform salt make each
        # signed exchange carry this concentration, including ebb.
        for direction in ('flood', 'ebb'):
            totals[direction+'_salt_kg'] += float(flux[direction+'_water_m3'].sum())*35.
            totals['creek_'+direction+'_salt_kg'] += float(flux[direction+'_water_m3'][creek_mask].sum())*35.
        records.append(dict(time_s=float(state['time_s'].flat[0]),
            tide_level_m=float(flux['tide_level_m'].flat[0]),
            flood_water_m3=float(flux['flood_water_m3'].sum()),
            ebb_water_m3=float(flux['ebb_water_m3'].sum()),
            creek_flood_water_m3=float(flux['flood_water_m3'][creek_mask].sum()),
            creek_ebb_water_m3=float(flux['ebb_water_m3'][creek_mask].sum())))
        # Mean rising, high, low, all from the second real period.
        if index+1 in (32, 40, 56):
            name = {32:'mean', 40:'high', 56:'low'}[index+1]
            snapshots[name] = dict(water_m3=state['water_m3'].copy(),
                stage_m=flux['water_stage_m'].copy(), time_s=records[-1]['time_s'])
    final_water = float(state['water_m3'].sum())
    final_salt = float(state['salt_kg'].sum())
    totals.update(initial_water_m3=initial_water, final_water_m3=final_water,
        initial_salt_kg=initial_salt, final_salt_kg=final_salt,
        total_water_balance_residual_m3=initial_water+totals['signed_ocean_water_m3']-final_water,
        total_salt_balance_residual_kg=initial_salt+totals['signed_ocean_salt_kg']-final_salt,
        bed_frozen_exact=bool(np.array_equal(state['bed_m'], bed)),
        mobile_solid_m3=float(state['bed_solid_m3'].sum()),
        protected_water_unchanged=bool(np.array_equal(state['water_m3'][context['protected_mask']],
            np.maximum(-bed[context['protected_mask']], 0.)*context['ocean_mask'][context['protected_mask']]*area)))
    return dict(ledger=totals, snapshots=snapshots, records=records)


def verify_saved_run(run_path, output):
    run_path, output = Path(run_path).resolve(), Path(output).resolve()
    if output == run_path or run_path in output.parents:
        raise ValueError('tidal output must be separate from source run')
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'output already populated: {output}')
    saved = load_run(run_path)
    with np.load(run_path/'scene.npz', allow_pickle=False) as data:
        scene = {key:data[key].copy() for key in data.files if key != 'metadata_json'}
        metadata = json.loads(data['metadata_json'].item())
    bed = saved['arrays']['final_bed_m']
    boundary = scene_tide_forcing(metadata)
    amplitude = boundary['amplitude_m']
    period = boundary['period_s']
    context = tidal_context(bed, scene, metadata)
    creek = scene['tidal_creek_footprint_mask'].astype(bool) & context['valid_mask']
    levels = np.asarray([-amplitude, 0., amplitude])
    reachable = np.asarray([_connected(bed, level, context['ocean_mask'], context['valid_mask'])
        for level in levels])
    tidal = simulate_tides(context, creek, amplitude_m=amplitude, period_s=period)
    control = simulate_tides(context, creek, amplitude_m=0., period_s=period)
    ledger = tidal['ledger']
    order = [tidal['snapshots'][name] for name in ('low', 'mean', 'high')]
    water_snapshots = np.asarray([v['water_m3'] for v in order])
    coverage_checks, core_coverage, visible = creek_coverage_checks(
        bed, scene['tidal_creek_mask'], reachable, water_snapshots, context['spacing_m'])
    checks = dict(bed_frozen_exact=ledger['bed_frozen_exact'],
        zero_river_inputs=ledger['river_water_input_m3']==ledger['river_solid_input_m3']==0.,
        zero_mobile_solid=ledger['mobile_solid_m3']==0.,
        water_conserved=abs(ledger['total_water_balance_residual_m3'])<.01,
        salt_conserved=abs(ledger['total_salt_balance_residual_kg'])<.1,
        creek_flood_and_ebb=ledger['creek_flood_water_m3']>0. and ledger['creek_ebb_water_m3']>0.,
        protected_river_excluded=not bool(np.any(reachable & context['protected_mask'])),
        zero_tide_no_exchange=control['ledger']['flood_water_m3']==control['ledger']['ebb_water_m3']==0.)
    # Intertidal banks may flood only partly; all constructed negative core must connect.
    checks.update(coverage_checks)
    checks['creek_visible_low_high_area_changes'] = bool(
        np.count_nonzero(visible[2] & creek)>np.count_nonzero(visible[0] & creek))
    if not all(checks.values()):
        raise ValueError('tidal validation failed: '+json.dumps(checks))
    output.mkdir(parents=True, exist_ok=True)
    arrays = dict(bed_m=bed, origin_xz_m=np.asarray(metadata['origin_xz_m']),
        spacing_m=np.asarray(metadata['spacing_m']), tide_levels_m=levels,
        bed_reachable_masks=reachable, ocean_seed_mask=context['ocean_mask'],
        tidal_valid_mask=context['valid_mask'], tidal_creek_footprint_mask=creek,
        tidal_intertidal_mask=scene['tidal_intertidal_mask'],
        snapshot_water_m3=water_snapshots,
        snapshot_stage_m=np.asarray([v['stage_m'] for v in order]),
        snapshot_time_s=np.asarray([v['time_s'] for v in order]))
    arrays['snapshot_wet_masks'] = visible
    arrays['snapshot_visible_depth_threshold_m'] = np.asarray(VISIBLE_WATER_DEPTH_M)
    np.savez_compressed(output/'tides.npz', **arrays)
    summary = dict(schema=SCHEMA, source_run=str(run_path),
        source_result_sha256=sha256(run_path/'result.npz'),
        source_scene_sha256=sha256(run_path/'scene.npz'),
        forcing=dict(period_s=period, amplitude_m=amplitude, mean_sea_level_m=0.,
            low_stage_m=-amplitude, high_stage_m=amplitude, source=boundary['source'], periods=2,
            elapsed_seconds=2*period, wave_height_m=0., river_water_m3=0., river_solid_m3=0.,
            semantics='prescribed engineering boundary; not climate generated'),
        domain=dict(shape=list(bed.shape), origin_xz_m=metadata['origin_xz_m'],
            spacing_m=metadata['spacing_m'], full_saved_grid=True,
            receiver='all -1 unused placeholder; no D8 operation executed',
            sea_seed='original marine support connected to external raster edge',
            river_policy='protected river excluded from sea connectivity and exchange'),
        phase_order=['low','mean','high'], tidal=tidal['ledger'],
        closure_absolute_tolerances=dict(water_m3=.01, salt_kg=.1),
        visible_water_depth_threshold_m=VISIBLE_WATER_DEPTH_M,
        snapshot_water_policy='Raw water inventories retained without clipping; display wet masks require at least 1 cm water depth to exclude exponential ebb films',
        negative_creek_core_connectivity=core_coverage,
        path_connection_coverage=path_connection_coverage(scene,metadata,reachable),
        zero_tide_control=control['ledger'], checks=checks,
        creek_connectivity=[dict(level_m=float(level), creek_cells=int(np.count_nonzero(mask & creek)),
            creek_area_m2=float(np.count_nonzero(mask & creek)*context['spacing_m']**2))
            for level,mask in zip(levels,reachable)],
        creek_actual_snapshots=[dict(phase=name, time_s=tidal['snapshots'][name]['time_s'],
            water_m3=float(tidal['snapshots'][name]['water_m3'][creek].sum()),
            wet_cells=int(np.count_nonzero(visible[index] & creek)),
            visible_wet_area_m2=float(np.count_nonzero(visible[index] & creek)*context['spacing_m']**2))
            for index,name in enumerate(('low','mean','high'))],
        records=tidal['records'],
        code_sha256={name:sha256(Path(__file__).resolve().parents[1]/name) for name in (
            'terrain_pipeline/delta_tidal_validation.py',
            'terrain_pipeline/environment_processes.py', 'tools/verify_delta_tides.py')},
        limitations='Reduced connected bed-based prism and water/salt exchange; no 2D momentum, finite-volume along-creek flow velocity, waves, bed evolution or repeated river forcing.',
        tides_sha256=sha256(output/'tides.npz'))
    (output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary
