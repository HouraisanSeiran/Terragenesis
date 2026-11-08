"""Independent geometry, wet support and local budgets of pinned fine runs."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ.setdefault(name, '1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import psutil
from terrain_pipeline.common_infra import checked_archive, file_sha256, identity, publish_bytes
from terrain_pipeline.runoff import _strict_json as _strict_json
from tools.audit_shallow_water import MODEL as SHALLOW_MODEL, MODEL_V2 as SHALLOW_MODEL_V2, MODEL_V3 as SHALLOW_MODEL_V3, MODEL_V7 as SHALLOW_MODEL_V7, audit_momentum

def read_json(record):
    path = Path(record['path'])
    if path.stat().st_size > 8 * 1024 ** 2 or file_sha256(path) != record['expected_sha256']:
        raise ValueError('independent JSON hash/size mismatch')
    return _strict_json(path.read_text(encoding='utf-8'))

def read_bundle(record):
    arrays = checked_archive(record['path'], expected_sha256=record['expected_sha256'], max_bytes=256 * 1024 ** 2)
    manifest = arrays.pop('manifest')
    decoded = _strict_json(manifest.tobytes().decode('utf-8'))
    if identity(arrays, decoded['metadata']) != decoded['identity_sha256']:
        raise ValueError('independent bundle identity mismatch')
    if record.get('expected_identity', decoded['identity_sha256']) != decoded['identity_sha256']:
        raise ValueError('independent external identity mismatch')
    return (arrays, decoded['metadata'], decoded['identity_sha256'])

def close(actual, expected, label, *, atol=1e-09, rtol=1e-11):
    if np.shape(actual) != np.shape(expected) or not np.isfinite(actual).all() or (not np.isfinite(expected).all()) or (not np.allclose(actual, expected, atol=atol, rtol=rtol)):
        raise ValueError('independent ' + label + ' mismatch')

def audit_code_records(index, stage_root, observed):
    if 'code_records' not in index:
        return False
    records = index['code_records']
    if set(records) != set(index['code_sha256']):
        raise ValueError('independent frozen source names mismatch')
    stage_root = stage_root.resolve(strict=True)
    snapshot = (stage_root / 'execution-code').resolve(strict=True)
    if not snapshot.is_relative_to(stage_root):
        raise ValueError('independent frozen source root escaped stage')
    for name, digest in index['code_sha256'].items():
        path = Path(records[name]['path']).resolve(strict=True)
        expected = (snapshot / name).resolve(strict=True)
        if not expected.is_relative_to(snapshot) or path != expected or records[name]['expected_sha256'] != digest or (file_sha256(path) != digest):
            raise ValueError('independent frozen source path/hash mismatch')
        observed.append(records[name])
    return True

def canonical_reference(arrays, metadata, source):
    """Independent physical recipe evaluation; never calls production builders."""
    x0, x1, z0, z1 = metadata['native_window']
    x, z = np.meshgrid(x0 + (np.arange((x1 - x0) * 30) + 0.5) / 30.0, z0 + (np.arange((z1 - z0) * 30) + 0.5) / 30.0)
    height = source['height_m']
    ix, iz = (np.floor(x).astype(int), np.floor(z).astype(int))
    jx, jz = (np.minimum(ix + 1, height.shape[1] - 1), np.minimum(iz + 1, height.shape[0] - 1))
    tx, tz = (x - ix, z - iz)
    native = (height[iz, ix] * (1 - tx) + height[iz, jx] * tx) * (1 - tz) + (height[jz, ix] * (1 - tx) + height[jz, jx] * tx) * tz
    cut = np.zeros_like(native)
    for a, b in arrays['selected_edge_cell_ids']:
        if source['receiver'][a] != b:
            raise ValueError('canonical receiver provenance mismatch')
        ax, az = (a % height.shape[1], a // height.shape[1])
        bx, bz = (b % height.shape[1], b // height.shape[1])
        fraction = np.clip(((x - ax) * (bx - ax) + (z - az) * (bz - az)) / ((bx - ax) ** 2 + (bz - az) ** 2), 0, 1)
        distance = 30 * np.hypot(x - ax - fraction * (bx - ax), z - az - fraction * (bz - az))
        cut = np.maximum(cut, np.where(distance < 4, 0.5 * (1 + np.cos(np.pi * np.minimum(distance / 4, 1))), 0))
    protected = source['protected_mask'][iz, ix] | source['protected_mask'][iz, jx] | source['protected_mask'][jz, ix] | source['protected_mask'][jz, jx]
    suppressed_cut = cut[protected].copy()
    cut[protected] = 0.0
    return (native - cut, protected, suppressed_cut)

def restrict_mean(values, factor):
    rows, columns = values.shape
    if type(factor) is not int or factor < 1 or rows % factor or columns % factor:
        raise ValueError('independent canonical restriction shape mismatch')
    return values.reshape(rows // factor, factor, columns // factor, factor).mean(axis=(1, 3))

def audit_initial_contract(depth, canonical_bed, *, lake_stage_m, spacing_m, initial_kind):
    expected = np.zeros(depth.shape) if initial_kind == 'rain' else restrict_mean(np.maximum(lake_stage_m - canonical_bed, 0.0), int(spacing_m))
    if expected.shape != depth.shape:
        raise ValueError('independent initial canonical footprint mismatch')
    difference = np.abs(depth - expected)
    return dict(maximum_depth_difference_m=float(difference.max(initial=0)), surface_volume_difference_m3=float((depth - expected).sum() * spacing_m ** 2), passed=bool(np.all(difference <= 1e-09)), semantics='dry zero or area restriction of max(shared physical lake stage minus protected canonical 1m bed,0)')

def audit_fan(geometry_arrays, water_arrays, spacing_m):
    """Integrate each wet fan from actual XYZ, without construction helpers."""
    bed = geometry_arrays['bed_vertices_xyz_m']
    vertices = water_arrays['water_vertices_xyz_m']
    triangles = water_arrays['water_triangles']
    wet = water_arrays['wet_cell_ids']
    depth = water_arrays['cell_depth_m']
    if not np.array_equal(wet, np.flatnonzero(depth.ravel() > 0)):
        raise ValueError('independent wet support omitted or duplicated')
    if vertices.shape != bed.shape or not np.array_equal(vertices[:, [0, 2]], bed[:, [0, 2]]):
        raise ValueError('independent water/bed footprint mismatch')
    if triangles.shape != (4 * wet.size, 3):
        raise ValueError('independent wet fan triangle count')
    if triangles.size and (triangles.min() < 0 or triangles.max() >= len(vertices)):
        raise ValueError('independent water triangle bounds')
    differences = vertices[:, 1] - bed[:, 1]
    if not np.isfinite(vertices).all() or np.any(differences < -1e-12):
        raise ValueError('independent negative/nonfinite reconstructed depth')
    positions = vertices[triangles]
    normals = np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0])
    if np.any(normals[:, 1] <= 0):
        raise ValueError('independent wet fan downward/degenerate triangles')
    areas = normals[:, 1] / 2
    volumes = (areas * differences[triangles].mean(axis=1)).reshape(-1, 4).sum(axis=1)
    expected = depth.ravel()[wet] * spacing_m ** 2
    close(areas.reshape(-1, 4).sum(axis=1), np.full(wet.size, spacing_m ** 2), 'wet projected area')
    close(volumes, expected, 'per-cell triangle volume', atol=1e-08, rtol=1e-10)
    corner = water_arrays['corner_depth_m']
    center = water_arrays['center_depth_m']
    if corner.shape != (depth.shape[0] + 1, depth.shape[1] + 1) or center.shape != depth.shape:
        raise ValueError('independent corner/center depth shapes')
    reconstructed = np.full(corner.shape, np.inf)
    for rows, columns in ((slice(None, -1), slice(None, -1)), (slice(None, -1), slice(1, None)), (slice(1, None), slice(1, None)), (slice(1, None), slice(None, -1))):
        reconstructed[rows, columns] = np.minimum(reconstructed[rows, columns], depth)
    if not np.array_equal(corner, reconstructed):
        raise ValueError('independent shared minimum corner depth')
    corner_sum = corner[:-1, :-1] + corner[:-1, 1:] + corner[1:, 1:] + corner[1:, :-1]
    close(center, 3 * depth - corner_sum / 2, 'conservative center reconstruction')
    return dict(wet_cells=int(wet.size), omitted_wet_cells=0, raster_volume_m3=float(expected.sum()), triangle_volume_m3=float(volumes.sum()), maximum_cell_volume_difference_m3=float(np.max(np.abs(volumes - expected), initial=0)), total_volume_difference_m3=float(volumes.sum() - expected.sum()), maximum_center_depth_m=float(center.max(initial=0)), maximum_cell_depth_m=float(depth.max(initial=0)))

def audit_interval(packet, surface_geometry, initial_depth, final_depth, forcing_volume, spacing_m):
    arrays = surface_geometry
    left, right = (arrays['face_left'], arrays['face_right'])
    boundary = arrays['boundary_cell']
    cells = initial_depth.size
    internal = packet['internal_transfer_m3']
    external = packet['boundary_transfer_m3']
    incidence = np.bincount(right, weights=internal, minlength=cells) - np.bincount(left, weights=internal, minlength=cells) - np.bincount(boundary, weights=external, minlength=cells)
    residual = spacing_m ** 2 * (final_depth.ravel() - initial_depth.ravel()) - forcing_volume.ravel() - incidence
    close(residual, np.zeros(cells), 'local surface balance', atol=2e-08)
    if np.any(external[arrays['boundary_kind'] == 0] != 0):
        raise ValueError('independent closed boundary exchange')
    return dict(max_cell_residual_m3=float(np.abs(residual).max(initial=0)), signed_boundary_export_m3=float(external.sum()), reverse_internal_transfer_faces=int(np.count_nonzero(internal < 0)))

def audit_bed(arrays, metadata, source):
    height = source['height_m']
    if any((not np.array_equal(source[key], arrays['native_' + key]) for key in ('height_m', 'receiver', 'valid_mask', 'protected_mask'))):
        raise ValueError('independent native source mismatch')
    x0, x1, z0, z1 = metadata['native_window']
    spacing = metadata['spacing_m']
    rows, columns = arrays['bed_center_m'].shape
    if rows * spacing != (z1 - z0) * 30 or columns * spacing != (x1 - x0) * 30:
        raise ValueError('independent entire finite window coverage')
    x, z = np.meshgrid(x0 + np.arange(columns + 1) * spacing / 30, z0 + np.arange(rows + 1) * spacing / 30)
    ix, iz = (np.floor(x).astype(int), np.floor(z).astype(int))
    jx, jz = (np.minimum(ix + 1, height.shape[1] - 1), np.minimum(iz + 1, height.shape[0] - 1))
    tx, tz = (x - ix, z - iz)
    native = (height[iz, ix] * (1 - tx) + height[iz, jx] * tx) * (1 - tz) + (height[jz, ix] * (1 - tx) + height[jz, jx] * tx) * tz
    close(arrays['native_bilinear_corner_m'], native, 'native bilinear bed')
    cut = np.zeros_like(native)
    edge_ids = arrays['selected_edge_cell_ids']
    for a, b in edge_ids:
        if source['receiver'][a] != b:
            raise ValueError('independent source receiver edge')
        ax, az = (a % height.shape[1], a // height.shape[1])
        bx, bz = (b % height.shape[1], b // height.shape[1])
        fraction = np.clip(((x - ax) * (bx - ax) + (z - az) * (bz - az)) / ((bx - ax) ** 2 + (bz - az) ** 2), 0, 1)
        distance = 30 * np.hypot(x - ax - fraction * (bx - ax), z - az - fraction * (bz - az))
        expected = np.where(distance < 4, 0.5 * (1 + np.cos(np.pi * np.minimum(distance / 4, 1))), 0)
        cut = np.maximum(cut, expected)
    protection = source['protected_mask'][iz, ix] | source['protected_mask'][iz, jx] | source['protected_mask'][jz, ix] | source['protected_mask'][jz, jx]
    cut[protection] = 0
    close(arrays['cut_corner_m'], cut, 'declared protected incision', atol=2e-10)
    close(arrays['bed_corner_m'], native - cut, 'derived bed')
    corner = arrays['bed_corner_m']
    mean = (corner[:-1, :-1] + corner[1:, :-1] + corner[1:, 1:] + corner[:-1, 1:]) / 4
    vertices = arrays['bed_vertices_xyz_m']
    triangles = arrays['bed_triangles']
    if len(triangles) != 4 * rows * columns or len(vertices) != (rows + 1) * (columns + 1) + rows * columns:
        raise ValueError('independent complete bed fan')
    positions = vertices[triangles]
    normals = np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0])
    if np.any(normals[:, 1] <= 0):
        raise ValueError('independent bed winding')
    areas = normals[:, 1] / 2
    close(areas.reshape(-1, 4).sum(axis=1), np.full(rows * columns, spacing ** 2), 'bed area')
    integrated = (areas * positions[:, :, 1].mean(axis=1)).reshape(-1, 4).sum(axis=1) / spacing ** 2
    solved_mean = arrays['bed_center_m'].ravel()
    mean_error = abs(integrated - solved_mean)
    canonical, protected, suppressed = canonical_reference(arrays, metadata, source)
    saved_canonical = arrays.get('canonical_bed_center_m')
    canonical_present = saved_canonical is not None
    canonical_error = float(abs(saved_canonical - canonical).max(initial=0)) if canonical_present else None
    restriction_error = float(abs(arrays['bed_center_m'] - restrict_mean(canonical, int(spacing))).max(initial=0))
    protected_error = float(abs(saved_canonical[protected] - canonical[protected]).max(initial=0)) if canonical_present else None
    incoming = np.bincount(edge_ids[:, 1], minlength=height.size)
    return dict(cells=rows * columns, bed_triangles=len(triangles), selected_edges=len(edge_ids), confluences=int(np.count_nonzero(incoming >= 2)), maximum_incision_m=float(cut.max(initial=0)), cut_volume_m3=float(((cut[:-1, :-1] + cut[1:, :-1] + cut[1:, 1:] + cut[:-1, 1:]) / 4).sum() * spacing ** 2), maximum_triangle_fv_bed_mean_difference_m=float(mean_error.max(initial=0)), triangle_fv_bed_mean_verified=bool(np.all(mean_error <= 1e-09)), canonical_present=canonical_present, maximum_canonical_difference_m=canonical_error, maximum_canonical_restriction_difference_m=restriction_error, protected_canonical_sample_count=int(protected.sum()), maximum_protected_canonical_difference_m=protected_error, suppressed_protected_recipe_cut_max_m=float(suppressed.max(initial=0)), canonical_contract_verified=canonical_present and canonical_error <= 1e-09 and (restriction_error <= 1e-09), limitations=['Bed mean checks integrate saved XYZ fan triangles; saved water volume conservation does not imply correct mean bed.'])

def audit_run(case, source, observed, *, lake_stage_m):
    bed, bed_meta, bed_id = read_bundle(case['bed'])
    bed_summary = audit_bed(bed, bed_meta, source)
    index = read_json(case['run'])
    audit_code_records(index, Path(case['run']['path']).resolve().parent.parent, observed)
    geometry, geometry_meta, geometry_id = read_bundle(index['geometry'])
    forcing, forcing_meta, forcing_id = read_bundle(index['forcing'])
    states, state_meta, state_id = read_bundle(index['states'])
    observed.extend([case['bed'], case['run'], index['geometry'], index['forcing'], index['states']])
    if state_meta['bed_identity'] != bed_id or geometry_meta['source_identity'] != bed_id or forcing_meta['bed_identity'] != bed_id or (state_meta['geometry_identity'] != geometry_id) or (state_meta['forcing_identity'] != forcing_id):
        raise ValueError('independent same-bed source identity chain')
    close(geometry['H2_m'], bed['bed_center_m'], 'original solved new bed')
    spacing = bed_meta['spacing_m']
    canonical, _, _ = canonical_reference(bed, bed_meta, source)
    initial_contract = audit_initial_contract(states['initial_depth_m'], canonical, lake_stage_m=lake_stage_m, spacing_m=spacing, initial_kind=case.get('initial_kind', 'lake'))
    dt = forcing_meta['dt_s']
    n = forcing_meta['steps']
    if len(index['intervals']) != n or ('frames' in case and len(case['frames']) != n + 1):
        raise ValueError('independent complete interval/frame coverage')
    subgrid = geometry_meta.get('hydraulic_model') == 'canonical-subcell-storage-segmented-face-local-inertia-v1'
    shallow = geometry_meta.get('hydraulic_model') in (SHALLOW_MODEL, SHALLOW_MODEL_V2, SHALLOW_MODEL_V3, SHALLOW_MODEL_V7)
    if geometry_meta.get('hydraulic_model') in (SHALLOW_MODEL_V3, SHALLOW_MODEL_V7):
        geometry['hydraulic_datum_m'] = geometry_meta['hydraulic_datum_m']
        for stage, depth in zip(states['stage_relative_m'], states['depth_m']):
            close(np.maximum(stage.ravel()[:, None] - geometry['subcell_bed_relative_m'], 0).mean(axis=1).reshape(depth.shape), depth, 'subgrid HLL V(stage)')
    physical = []
    if shallow and len(index['momenta']) != n:
        raise ValueError('independent shallow sampled momentum coverage')
    if subgrid:
        subbed = geometry['subcell_bed_relative_m']
        for stage, depth in zip(states['stage_relative_m'], states['depth_m']):
            close(np.maximum(stage.ravel()[:, None] - subbed, 0).mean(axis=1).reshape(depth.shape), depth, 'subgrid stored stage hypsometry')
        if len(index['momenta']) != n:
            raise ValueError('independent subgrid momentum coverage')
    close(states['time_s'], np.arange(n + 1) * dt, 'saved physical seconds')
    factor = spacing ** 2 / 1000
    rain = forcing['rain_mm_h'] * dt / 3600
    soil, fast, slow = (forcing[name] for name in ('soil_mm', 'fast_mm', 'slow_mm'))
    infil, et, perc, excess, release_fast, release_slow = (forcing[name] for name in ('infiltration_mm', 'actual_et_mm', 'percolation_mm', 'excess_mm', 'fast_release_mm', 'slow_release_mm'))
    close(np.diff(soil, axis=0), infil - et - perc, 'soil budget')
    close(excess, rain - infil, 'rain infiltration/excess')
    close(np.diff(fast, axis=0), excess - release_fast, 'fast reservoir budget')
    close(np.diff(slow, axis=0), perc - release_slow, 'slow reservoir budget')
    parameters = forcing_meta['runoff_metadata']['parameters']
    for values, incoming, released, tau in ((fast, excess, release_fast, parameters['fast_tau_s']), (slow, perc, release_slow, parameters['slow_tau_s'])):
        ratio = dt / tau
        fraction = -math.expm1(-ratio)
        incoming_fraction = ratio / 2 - ratio ** 2 / 6 + ratio ** 3 / 24 if ratio < 0.0001 else 1 - fraction / ratio
        close(released, values[:-1] * fraction + incoming * incoming_fraction, 'independent reservoir release law')
    close(forcing['outflow_volume_m3'], (release_fast + release_slow) * factor, 'single surface delivery')
    intervals = []
    import_lower_bound = 0.0
    for number, pin in enumerate(index['intervals']):
        packet, packet_meta, _ = read_bundle(pin)
        observed.append(pin)
        import_lower_bound += float(np.maximum(-packet['boundary_transfer_m3'], 0).sum())
        close(packet['depth_before_m'], states['depth_m'][number].ravel(), 'checkpoint before')
        close(packet['depth_after_m'], states['depth_m'][number + 1].ravel(), 'checkpoint after')
        close(packet['forcing_volume_m3'], forcing['outflow_volume_m3'][number], 'complete forcing')
        intervals.append(audit_interval(packet, geometry, states['depth_m'][number], states['depth_m'][number + 1], forcing['outflow_volume_m3'][number], spacing))
        if packet_meta['bed_identity'] != bed_id or packet_meta['forcing_identity'] != forcing_id:
            raise ValueError('independent interval identity binding')
        if shallow:
            for endpoint, position in (('before', number), ('after', number + 1)):
                expected = np.column_stack((states['momentum_x_m2_s'][position].ravel(), states['momentum_z_m2_s'][position].ravel()))
                close(packet['momentum_' + endpoint], expected, 'shallow snapshot momentum ' + endpoint)
            change = np.zeros((bed['bed_center_m'].size, 2))
            np.add.at(change, geometry['face_left'], -packet['internal_momentum_transfer'] / spacing ** 2)
            np.add.at(change, geometry['face_right'], packet['internal_momentum_transfer'] / spacing ** 2)
            np.add.at(change, geometry['boundary_cell'], -packet['boundary_momentum_transfer'] / spacing ** 2)
            change += packet['bed_momentum_change'] + packet['manning_momentum_change']
            close(packet['momentum_after'] - packet['momentum_before'], change, 'shallow interval momentum account')
            witness, witness_meta, _ = read_bundle(index['momenta'][number])
            observed.append(index['momenta'][number])
            if witness_meta.get('hydraulic_model') != geometry_meta['hydraulic_model'] or witness_meta['interval'] != number or witness_meta['bed_identity'] != bed_id or (witness_meta['geometry_identity'] != geometry_id) or (witness_meta['forcing_identity'] != forcing_id):
                raise ValueError('independent shallow witness model/source/time binding')
            close(witness_meta['time_start_s'], number * dt, 'shallow sampled time')
            close(witness['state_before'][:, 0], packet['depth_before_m'], 'shallow sampled initial depth')
            close(witness['state_before'][:, 1:], packet['momentum_before'], 'shallow sampled initial momentum')
            physical.append(audit_momentum(witness, witness_meta, geometry, spacing, state_meta['solver_metadata']['budget'], forcing['local_q_m3_s'][number], forcing['boundary_stage_m'][number]))
        if subgrid:
            for kind in ('internal', 'boundary'):
                close(packet[f'{kind}_segment_transfer_m3'].sum(axis=1), packet[f'{kind}_transfer_m3'], 'subgrid signed segment volumes')
                for endpoint in ('before', 'after'):
                    close(packet[f'{kind}_segment_q_{endpoint}_m3_s'].sum(axis=1), packet[f'{kind}_q_{endpoint}_m3_s'], 'subgrid segment total discharges')
            from terrain_pipeline.fine_subgrid import validate_fine_momentum
            witness, witness_meta, witness_id = read_bundle(index['momenta'][number])
            observed.append(index['momenta'][number])
            validate_fine_momentum(dict(arrays=witness, metadata=witness_meta, identity_sha256=witness_id), bed=dict(arrays=bed, metadata=bed_meta, identity_sha256=bed_id), geometry=dict(arrays=geometry, metadata=geometry_meta, identity_sha256=geometry_id), forcing=dict(arrays=forcing, metadata=forcing_meta, identity_sha256=forcing_id), states=dict(arrays=states, metadata=state_meta, identity_sha256=state_id), interval=number, interval_packet=dict(arrays=packet, metadata=packet_meta))
    total = (soil + fast + slow).sum(axis=1) * factor + states['depth_m'].sum(axis=(1, 2)) * spacing ** 2
    net_boundary = np.r_[0.0, np.cumsum([item['signed_boundary_export_m3'] for item in intervals])]
    expected_change = np.r_[0.0, np.cumsum(((rain - et) * factor).sum(axis=1))] - net_boundary
    close(total - total[0], expected_change, 'four compartments complete budget', atol=1e-07)
    frames = []
    for number, declaration in enumerate(case.get('frames', [])):
        water, water_meta, _ = read_bundle(declaration['frame'])
        observed.append(declaration['frame'])
        if water_meta['bed_identity'] != bed_id or water_meta['hydraulic_state_identity'] != state_id or water_meta['state_index'] != number:
            raise ValueError('independent frame exact source binding')
        close(water_meta['time_s'], states['time_s'][number], 'frame time')
        if not np.array_equal(water['cell_depth_m'], states['depth_m'][number]):
            raise ValueError('independent exact saved cell depths')
        frames.append(audit_fan(bed, water, spacing))
    return (dict(geometry=bed_summary, initial_contract=initial_contract, intervals=intervals, frames=frames, independent_shallow_physical_equations=physical, saved_boundary_input_m3=float(states['ledger'][-1, 1]), independently_integrated_import_lower_bound_m3=import_lower_bound, maximum_four_compartment_residual_m3=float(np.abs(total - total[0] - expected_change).max()), independent_fast_slow_release=True), states['depth_m'])

def audit(index_record, output):
    started = time.monotonic()
    index = read_json(index_record)
    if index.get('schema') == 'single-domain-fine-short-index-v1':
        return audit_short(index_record, index, output, started)
    observed = [index_record, index['source'], index['report'], index['resource'], index['predeclared'], index['boundary_declaration']]
    frozen_code_verified = audit_code_records(index, Path(index_record['path']).resolve().parent, observed)
    source, _, _ = read_bundle(index['source'])
    report = read_json(index['report'])
    declaration = read_json(index['predeclared'])
    boundary_declaration = read_json(index['boundary_declaration'])
    resource = read_json(index['resource'])
    if report['cases'] != index['cases'] or declaration['source'] != index['source']:
        raise ValueError('independent index/report/declaration binding')
    if declaration['gates']['max_saved_depth_difference_m'] != 0.01 or declaration['gates']['max_relative_surface_volume_difference'] != 0.01 or declaration['gates']['max_lake_depth_change_m'] != 1e-09:
        raise ValueError('independent fixed refinement/static gates changed')
    if resource.get('complete') is not True or resource.get('budgets') != declaration.get('budgets'):
        raise ValueError('independent complete execution resource binding')
    for flag in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'):
        if index.get(flag) is not False or report.get(flag) is not False:
            raise ValueError('independent unsupported certification flag')
    cases, depths = ({}, {})
    for name, case in index['cases'].items():
        print('independently auditing ' + name, flush=True)
        cases[name], depths[name] = audit_run(case, source, observed, lake_stage_m=boundary_declaration['initial_lake_stage_m'])
        memory = psutil.Process().memory_info()
        if max(getattr(memory, 'peak_wset', memory.rss), getattr(memory, 'peak_pagefile', 0)) > 1024 ** 3:
            raise MemoryError('independent fine audit exceeds 1GiB')
    comparisons = []
    for coarse, fine, factor in (('tailwater-rise-1m', 'tailwater-rise-1m-half-dt', 1), ('tailwater-rise-2m', 'tailwater-rise-1m-half-dt', 2), ('tailwater-rise-4m', 'tailwater-rise-2m', 2)):
        a, b = (depths[coarse], depths[fine])
        t, r, c = a.shape
        averaged = b.reshape(t, r, factor, c, factor).mean(axis=(2, 4))
        error = float(np.abs(a - averaged).max())
        relative = float((np.abs(a.sum(axis=(1, 2)) * factor ** 2 - b.sum(axis=(1, 2))) / np.maximum(b.sum(axis=(1, 2)), 1e-12)).max())
        comparisons.append(dict(coarse=coarse, fine=fine, depth_difference_m=error, relative_volume_difference=relative, passed=error <= declaration['gates']['max_saved_depth_difference_m'] and relative <= declaration['gates']['max_relative_surface_volume_difference']))
    first_case, index_case = (index['cases']['tailwater-rise-1m'], index['cases']['tailwater-rise-1m-half-dt'])
    temporal_changed = first_case['solver']['substeps'] != index_case['solver']['substeps'] and first_case['diagnostics']['maximum_dt_s'] > index_case['diagnostics']['maximum_dt_s']
    for name in ('tailwater-rise-1m', 'tailwater-rise-1m-half-dt'):
        case = index['cases'][name]
        if case['diagnostics']['maximum_dt_s'] > case['solver']['budget']['max_dt_s'] + 1e-12:
            raise ValueError('independent saved actual dt exceeds declared budget')
    comparisons[0]['temporal_resolution_changed'] = temporal_changed
    comparisons[0]['passed'] = comparisons[0]['passed'] and temporal_changed
    for position, item in enumerate(comparisons):
        close(item['depth_difference_m'], report['comparisons'][position]['maximum_saved_depth_difference_m'], 'reported depth refinement')
        close(item['relative_volume_difference'], report['comparisons'][position]['maximum_relative_surface_volume_difference'], 'reported volume refinement')
    lake = depths['lake-at-rest-1m']
    lake_error = float(abs(lake - lake[0]).max())
    response = depths['tailwater-rise-1m-half-dt'][-1] - depths['tailwater-baseline-1m'][-1]
    imported = cases['tailwater-rise-1m-half-dt']['saved_boundary_input_m3']
    actual_import = cases['tailwater-rise-1m-half-dt']['independently_integrated_import_lower_bound_m3']
    if imported + 1e-08 < actual_import:
        raise ValueError('independent claimed gross import below signed face import')
    scenario_gates = dict(lake_at_rest=dict(max_depth_change_m=lake_error, passed=lake_error <= declaration['gates']['max_lake_depth_change_m']), controlled_tailwater=dict(max_depth_increase_m=float(response.max()), positive_response_cells=int(np.count_nonzero(response > declaration['gates']['minimum_tailwater_response_m'])), imported_volume_m3=imported, passed=float(response.max()) > declaration['gates']['minimum_tailwater_response_m'] and actual_import > declaration['gates']['minimum_tailwater_import_m3']))
    for scenario, fields in scenario_gates.items():
        for name, value in fields.items():
            if name != 'passed':
                close(value, report['scenario_gates'][scenario][name], 'reported scenario ' + scenario + ' ' + name)
    upstream = response[:, :max(1, response.shape[1] // 2)]
    response_cells = np.argwhere(response > declaration['gates']['minimum_tailwater_response_m'])
    scenario_gates['controlled_tailwater'].update(independent_import_lower_bound_m3=actual_import, maximum_west_half_depth_increase_m=float(upstream.max()), positive_west_half_response_cells=int(np.count_nonzero(upstream > declaration['gates']['minimum_tailwater_response_m'])), farthest_response_from_prescribed_east_boundary_m=float((response.shape[1] - 0.5 - response_cells[:, 1]).max(initial=0)))
    for record in observed:
        if file_sha256(record['path']) != record['expected_sha256']:
            raise ValueError('independent observed source changed')
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    memory = psutil.Process().memory_info()
    code_matches = {name: file_sha256(ROOT / name) == digest for name, digest in index['code_sha256'].items()}
    geometry_passed = all((case['geometry']['triangle_fv_bed_mean_verified'] and case['geometry']['canonical_contract_verified'] for case in cases.values()))
    initial_passed = all((case['initial_contract']['passed'] for case in cases.values()))
    result = dict(schema='single-domain-fine-independent-audit-v2', index_record=index_record, cases=cases, comparisons=comparisons, all_refinement_gates_passed=all((item['passed'] for item in comparisons)), scenario_gates=scenario_gates, all_scenario_gates_passed=all((item['passed'] for item in scenario_gates.values())), all_predeclared_gates_passed=all((item['passed'] for item in comparisons)) and all((item['passed'] for item in scenario_gates.values())) and geometry_passed and initial_passed, temporal_resolution_changed=temporal_changed, all_geometry_gates_passed=geometry_passed, all_initial_contracts_passed=initial_passed, historical_code_matches_current=code_matches, all_historical_code_pins_match_current=all(code_matches.values()), saved_artifact_chain_authenticated=True, production_geometry_builders_called=False, immutable_execution_code_verified=frozen_code_verified, physical_sampled_hll_verified=all((bool(case['independent_shallow_physical_equations']) for case in cases.values())), independent_physical_code_sha256=file_sha256(ROOT / 'tools/audit_shallow_water.py'), current_audit_code_sha256=file_sha256(Path(__file__)), resource=dict(elapsed_s=time.monotonic() - started, peak_rss_bytes=int(getattr(memory, 'peak_wset', memory.rss)), peak_private_bytes=int(getattr(memory, 'peak_pagefile', memory.vms))), solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, official_frontend_integrated=False, limitations=report['limitations'] + ['Historical code pins are authenticated by the fixed index; current code matching is reported separately.', 'A v2 diagnostic audit does not accept failed bed means, canonical protection or refinement gates.'])
    target = output / 'report.json'
    publish_bytes(target, (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    pin = dict(path=str(target), expected_sha256=file_sha256(target))
    print(json.dumps(dict(report=pin, comparisons=comparisons)), flush=True)
    return result

def audit_short(index_record, index, output, started):
    declaration = read_json(index['predeclared'])
    if set(index['cases']) != {'1.0', '2.0', '4.0'} or declaration['source'] != index['source'] or index.get('stage_accepted') is not False or any((index.get(name) is not False for name in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'))):
        raise ValueError('independent short diagnostic declaration/flags mismatch')
    gates = declaration['gates']
    if gates['max_saved_depth_difference_m'] != 0.01 or gates['max_relative_surface_volume_difference'] != 0.01 or gates['max_lake_depth_change_m'] != 1e-09:
        raise ValueError('independent short strict gates changed')
    source, _, _ = read_bundle(index['source'])
    observed = [index_record, index['source'], index['predeclared']]
    frozen_code_verified = audit_code_records(index, Path(index_record['path']).resolve().parent, observed)
    cases, depths = ({}, {})
    for name, case in index['cases'].items():
        print('independently auditing short ' + name, flush=True)
        cases[name], depths[name] = audit_run(case, source, observed, lake_stage_m=index['initial_lake_stage_m'])
    comparisons = []
    for coarse, fine in (('2.0', '1.0'), ('4.0', '2.0')):
        a, b = (depths[coarse], depths[fine])
        t, r, c = a.shape
        error = float(abs(a - b.reshape(t, r, 2, c, 2).mean(axis=(2, 4))).max())
        relative = float((abs(a.sum(axis=(1, 2)) * 4 - b.sum(axis=(1, 2))) / np.maximum(b.sum(axis=(1, 2)), 1e-12)).max())
        comparisons.append(dict(coarse=coarse, fine=fine, depth_difference_m=error, relative_volume_difference=relative, passed=error <= 0.01 and relative <= 0.01))
    for calculated, saved in zip(comparisons, index['comparisons']):
        close(calculated['depth_difference_m'], saved['maximum_saved_depth_difference_m'], 'short reported depth error')
        close(calculated['relative_volume_difference'], saved['maximum_relative_surface_volume_difference'], 'short reported volume error')
    for pin in observed:
        if file_sha256(pin['path']) != pin['expected_sha256']:
            raise ValueError('independent short observed artifact changed')
    memory = psutil.Process().memory_info()
    rss, private = (int(getattr(memory, 'peak_wset', memory.rss)), int(getattr(memory, 'peak_pagefile', memory.vms)))
    elapsed = time.monotonic() - started
    if max(rss, private) > 1024 ** 3 or elapsed > 1800:
        raise RuntimeError('independent short audit resource budget exceeded')
    result = dict(schema='single-domain-fine-short-independent-audit-v1', index_record=index_record, cases=cases, comparisons=comparisons, all_refinement_gates_passed=all((item['passed'] for item in comparisons)), temporal_resolution_changed=False, stage_accepted=False, saved_artifact_chain_authenticated=True, immutable_execution_code_verified=frozen_code_verified, physical_sampled_hll_verified=all((bool(case['independent_shallow_physical_equations']) for case in cases.values())), all_geometry_gates_passed=all((case['geometry']['triangle_fv_bed_mean_verified'] and case['geometry']['canonical_contract_verified'] for case in cases.values())), all_initial_contracts_passed=all((case['initial_contract']['passed'] for case in cases.values())), resource=dict(elapsed_s=elapsed, peak_rss_bytes=rss, peak_private_bytes=private), current_audit_code_sha256=file_sha256(Path(__file__)), independent_physical_code_sha256=file_sha256(ROOT / 'tools/audit_shallow_water.py'), solver_advanced=False, production_shallow_water_helpers_called=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, limitations=index['limitations'] + ['Physical HLL audit verifies saved first-substep witnesses; integrated intervals retain independently checked mass/momentum accounts.', 'For v3, Manning verification establishes implementation of its legacy coarse mean-depth friction equation only; canonical subcell-integrated friction consistency is not verified and the half-wet closure differs.'])
    target_root = Path(output).resolve()
    target_root.relative_to(ROOT)
    target_root.mkdir(parents=True, exist_ok=False)
    target = target_root / 'report.json'
    publish_bytes(target, (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    print(json.dumps(dict(report=dict(path=str(target), expected_sha256=file_sha256(target)), comparisons=comparisons)), flush=True)
    return result
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--index-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    audit(dict(path=str(args.index.resolve()), expected_sha256=args.index_sha256), args.output)
