"""Consolidated audit_special_terrain implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i35_argparse
import json as _i35_json
from pathlib import Path as _i35_Path
import sys as _i35_sys
import numpy as _i35_np
from terrain_pipeline.common_infra import identity as _i35_identity
from terrain_pipeline.common_infra import load_bundle as _i35_load_bundle
import argparse as _i36_argparse
import hashlib as _i36_hashlib
import json as _i36_json
from pathlib import Path as _i36_Path
import sys as _i36_sys
import numpy as _i36_np
from terrain_pipeline.common_infra import identity as _i36_identity
from terrain_pipeline.common_infra import load_bundle as _i36_load_bundle
CATEGORY = 'C'
ROOT = _i35_Path(__file__).resolve().parents[1]
_i35_sys.path.insert(0, str(ROOT))
AUDIT_SCHEMA = 'special-terrain-forms-independent-audit-v1'
ARRAY_KEYS = {'reference_xyz_m', 'displacement_xyz_m', 'vertices_xyz_m', 'triangles', 'protected_mask'}
METADATA_KEYS = {'schema', 'algorithm', 'coordinates', 'base', 'recipe', 'parameter_sources', 'source_identity', 'protection_identity', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'}
RECIPE_KEYS = {'kind', 'size_x_m', 'size_z_m', 'spacing_m', 'collar_margin_m', 'targets', 'seed'}
TARGET_KEYS = {'target_id', 'center_x_m', 'center_z_m', 'base_elevation_m', 'height_m', 'radius_x_m', 'radius_z_m', 'source_grade', 'source_ref'}
FLAGS = ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified')
TOLERANCE = 1e-09

def require(condition, message):
    if not condition:
        raise ValueError(message)

def smoothstep(value):
    fraction = _i35_np.clip(value, 0.0, 1.0)
    return fraction * fraction * (3.0 - 2.0 * fraction)

def minimal_scope(result):
    """Scope check only; every geometric claim is re-derived below."""
    require(isinstance(result, dict) and set(result) == {'arrays', 'metadata', 'identity_sha256'}, 'unexpected bundle fields')
    require(set(result['arrays']) == ARRAY_KEYS, 'unexpected array keys')
    require(set(result['metadata']) == METADATA_KEYS, 'unexpected metadata keys')

def rebuild_analytic_chart(recipe):
    """Own reconstruction of the closed analytic bed: a plane on a uniform grid."""
    cols_exact = recipe['size_x_m'] / recipe['spacing_m']
    rows_exact = recipe['size_z_m'] / recipe['spacing_m']
    require(abs(cols_exact - round(cols_exact)) < TOLERANCE and abs(rows_exact - round(rows_exact)) < TOLERANCE, 'recipe does not tile an integer number of spacing steps')
    rows, cols = (int(round(rows_exact)) + 1, int(round(cols_exact)) + 1)
    x = (_i35_np.arange(cols) - 0.5 * (cols - 1)) * recipe['spacing_m']
    z = (_i35_np.arange(rows) - 0.5 * (rows - 1)) * recipe['spacing_m']
    reference = _i35_np.zeros((rows, cols, 3), dtype=_i35_np.float64)
    reference[:, :, 0] = x[None, :]
    reference[:, :, 2] = z[:, None]
    return reference

def rebuild_relief(reference, recipe, flat_top_fraction):
    """Own reconstruction of the absolute relief field, with the auditor's own smoothstep.

    Returns the elevation the landform would hold over the *rebuilt* bed, so the caller
    can difference it against the stored bed after allowing for the bed's constant shift.
    """
    band = 1.0 - flat_top_fraction
    require(band > 0.0, 'flat-top fraction leaves no wall band')
    x, z = (reference[:, :, 0], reference[:, :, 2])
    relief = _i35_np.full(reference.shape[:2], -_i35_np.inf, dtype=_i35_np.float64)
    for target in recipe['targets']:
        across = (x - target['center_x_m']) / target['radius_x_m']
        along = (z - target['center_z_m']) / target['radius_z_m']
        radial = _i35_np.sqrt(across * across + along * along)
        profile = smoothstep((1.0 - radial) / band)
        relief = _i35_np.maximum(relief, target['base_elevation_m'] + target['height_m'] * profile)
    require(bool(_i35_np.isfinite(relief).all()), 'nonfinite replayed relief')
    return relief

def rebuild_displacement(rebuilt_bed, relief, mask, shift_value):
    """Field displacement exactly as the module declares it: positive cut to the bed."""
    target_elevation = relief + shift_value
    displacement = _i35_np.zeros((relief.shape[0], relief.shape[1], 3), dtype=_i35_np.float64)
    displacement[:, :, 1] = _i35_np.where(target_elevation - rebuilt_bed[:, :, 1] > 0.0, target_elevation - rebuilt_bed[:, :, 1], 0.0)
    displacement[mask] = 0
    displacement[0] = displacement[-1] = 0
    displacement[:, 0] = displacement[:, -1] = 0
    return displacement

def audit_sampling_gate(reference, recipe, flat_top_fraction):
    """Re-derive the gate the generator claims to apply."""
    horizontal = reference[:, :, (0, 2)]
    adjacent = _i35_np.concatenate((_i35_np.linalg.norm(_i35_np.diff(horizontal, axis=0), axis=2).ravel(), _i35_np.linalg.norm(_i35_np.diff(horizontal, axis=1), axis=2).ravel()))
    require(bool(_i35_np.isfinite(adjacent).all()) and bool(_i35_np.all(adjacent > 0)), 'invalid adjacent spacing')
    spacing = float(adjacent.max())
    require(spacing - float(adjacent.min()) < TOLERANCE * spacing, 'chart is not a uniform grid')
    band = 1.0 - flat_top_fraction
    observed = []
    for target in recipe['targets']:
        wall_width = band * min(target['radius_x_m'], target['radius_z_m'])
        observed.append({'target_id': target['target_id'], 'wall_band_m': wall_width, 'passed': wall_width >= 4.0 * spacing})
    require(all((entry['passed'] for entry in observed)), 'wall band below the sampling limit')
    return {'spacing_m': spacing, 'targets': observed}

def audit_mesh(vertices, triangles):
    """Own non-degeneracy and orientation check; no generator mesh helper is reused."""
    points = vertices[triangles]
    first = points[:, 1] - points[:, 0]
    second = points[:, 2] - points[:, 0]
    cross = _i35_np.cross(first, second)
    scale = _i35_np.linalg.norm(first, axis=1) * _i35_np.linalg.norm(second, axis=1)
    require(bool(_i35_np.isfinite(points).all()) and bool(_i35_np.isfinite(cross).all()), 'nonfinite triangle')
    require(bool(_i35_np.all(scale > 0.0)), 'degenerate triangle edge')
    area = _i35_np.linalg.norm(cross, axis=1)
    require(bool(_i35_np.all(area > 1e-12 * scale)), 'degenerate triangle area')
    plan = _i35_np.abs(cross[:, 1]) / _i35_np.maximum(area, 1e-300)
    return {'triangles': int(triangles.shape[0]), 'min_area_ratio': float(_i35_np.min(area / scale)), 'min_plan_view_alignment': float(_i35_np.min(plan))}

def audit_bundle(path, *, expected_sha256):
    result = _i35_load_bundle(path, expected_sha256=expected_sha256, validator=minimal_scope)
    metadata = result['metadata']
    require(metadata['schema'] == 'metric-special-terrain-v1' and metadata['algorithm'] == 'special-terrain-field-forms-v1', 'unexpected special terrain identity')
    require(metadata['coordinates'] == 'xyz metres; chart [row,col]', 'unexpected coordinates')
    require(metadata['base'] == 'synthetic_analytic', 'audit expects the declared synthetic analytic base')
    for flag in FLAGS:
        require(metadata[flag] is False, f'bundle prematurely promoted capability: {flag}')
    recipe = metadata['recipe']
    require(isinstance(recipe, dict) and set(recipe) == RECIPE_KEYS, 'unexpected recipe keys')
    for target in recipe['targets']:
        require(isinstance(target, dict) and set(target) == TARGET_KEYS, 'unexpected target keys')
        require(target['source_grade'] in ('verified', 'secondary', 'assumed'), 'target grade outside the declared scale')
        require(isinstance(target['source_ref'], str) and target['source_ref'].strip(), 'target lacks a ledger reference')
    flat_top_fraction = metadata['parameter_sources'][recipe['kind']].get('flat_top_fraction')
    require(flat_top_fraction is None or isinstance(flat_top_fraction, list), 'unexpected flat-top provenance entry')
    stored_reference = result['arrays']['reference_xyz_m']
    rebuilt_reference = rebuild_analytic_chart(recipe)
    require(rebuilt_reference.shape == stored_reference.shape, 'rebuilt chart shape differs from the stored chart')
    shift = stored_reference[:, :, 1] - rebuilt_reference[:, :, 1]
    require(float(shift.max() - shift.min()) < TOLERANCE, 'stored bed is not the replayed plane')
    shift_value = float(shift[0, 0])
    require(abs(float(shift.mean()) - shift_value) < TOLERANCE, 'stored bed shift is not constant')
    require(bool(_i35_np.array_equal(stored_reference[:, :, 0], rebuilt_reference[:, :, 0])) and bool(_i35_np.array_equal(stored_reference[:, :, 2], rebuilt_reference[:, :, 2])), 'stored plan coordinates differ from the replayed chart')
    stored_displacement = result['arrays']['displacement_xyz_m']
    require(bool(_i35_np.all(stored_displacement[:, :, 0] == 0)) and bool(_i35_np.all(stored_displacement[:, :, 2] == 0)), 'displacement is not vertical only')
    mask = result['arrays']['protected_mask']
    relief = stored_displacement[:, :, 1]
    band_candidates = []
    for fraction in sorted({0.2754, 0.55, 0.72, 0.8}):
        candidate = rebuild_displacement(rebuilt_reference, rebuild_relief(rebuilt_reference, recipe, fraction), mask, shift_value)[:, :, 1]
        band_candidates.append((float(_i35_np.abs(candidate - relief).max()), fraction))
    minimum_difference, recovered_fraction = min(band_candidates)
    require(minimum_difference < TOLERANCE, f'no declared flat-top fraction replays the stored relief (best {minimum_difference:.3e})')
    recomputed = rebuild_displacement(rebuilt_reference, rebuild_relief(rebuilt_reference, recipe, recovered_fraction), mask, shift_value)
    require(bool(_i35_np.array_equal(recomputed, stored_displacement)), 'independently replayed displacement differs from the stored displacement')
    perimeter_zero = {'first_row': bool(_i35_np.all(stored_displacement[0] == 0)), 'last_row': bool(_i35_np.all(stored_displacement[-1] == 0)), 'first_column': bool(_i35_np.all(stored_displacement[:, 0] == 0)), 'last_column': bool(_i35_np.all(stored_displacement[:, -1] == 0))}
    require(all(perimeter_zero.values()), 'chart perimeter displacement is not zero')
    require(bool(_i35_np.all(stored_displacement[~mask] >= 0.0)), 'negative displacement outside protection')
    require(bool(_i35_np.all(stored_displacement[mask] == 0.0)), 'protected cell received displacement')
    vertices = result['arrays']['vertices_xyz_m']
    require(bool(_i35_np.array_equal(vertices, (stored_reference + stored_displacement).reshape(-1, 3))), 'stored vertices are not reference plus displacement')
    mesh = audit_mesh(vertices, result['arrays']['triangles'])
    recomputed_identity = _i35_identity(result['arrays'], metadata)
    require(recomputed_identity == result['identity_sha256'], 'identity does not replay')
    return {'kind': recipe['kind'], 'target_count': len(recipe['targets']), 'chart_shape': [int(stored_reference.shape[0]), int(stored_reference.shape[1])], 'cells': int(stored_reference.shape[0] * stored_reference.shape[1]), 'base_elevation_shift_m': shift_value, 'recovered_flat_top_fraction': recovered_fraction, 'max_replay_difference_m': minimum_difference, 'max_relief_m': float(relief.max()), 'sampling_gate': audit_sampling_gate(stored_reference, recipe, recovered_fraction), 'perimeter_zero': perimeter_zero, 'mesh': mesh, 'displacement_vertical_only': True, 'identity_sha256': result['identity_sha256'], 'status': 'candidate', 'flags': {flag: metadata[flag] for flag in FLAGS}, 'caveat': 'Vertical-only displacement preserves the plan-view triangulation, so the replayed mesh is non-degenerate, but full solid self-intersection and hydraulic legality are not certified and the flags remain false.'}

def _entry_audit_special_terrain_forms(argv=None):
    parser = _i35_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundles', type=_i35_Path, help='directory holding <kind>.npz and manifest-report.json')
    parser.add_argument('--output', type=_i35_Path, default=None)
    args = parser.parse_args(argv)
    report_path = args.bundles / 'manifest-report.json'
    manifest = _i35_json.loads(report_path.read_text(encoding='utf-8'))
    report = {'audit_schema': AUDIT_SCHEMA, 'generator_imported': False, 'bundle_directory': str(args.bundles), 'forms': {}, 'failures': {}}
    for kind, entry in sorted(manifest['forms'].items()):
        path = args.bundles / entry['file']
        try:
            audited = audit_bundle(path, expected_sha256=entry['sha256'])
            require(audited['identity_sha256'] == entry['identity_sha256'], 'audited identity differs from the manifest identity')
            report['forms'][kind] = audited
            print(f"{kind}: pass identity={audited['identity_sha256']} replay_delta={audited['max_replay_difference_m']:.3e}")
        except ValueError as error:
            report['failures'][kind] = str(error)
            print(f'{kind}: FAIL {error}')
    output = args.output or args.bundles / 'independent-audit.json'
    output.write_text(_i35_json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'audit: {output}')
    print(f"passed={len(report['forms'])} failed={len(report['failures'])}")
    return 1 if report['failures'] else 0
_i36_sys.path.insert(0, str(ROOT))
AUDIT_SURFACE_AUDIT_SCHEMA = 'special-terrain-surface-independent-audit-v1'
SURFACE_SCHEMA = 'metric-special-terrain-surface-v2'
SURFACE_ALGORITHM = 'special-terrain-facet-noise-hydraulic-dissection-v2'
SUPERSEDED = 'special-terrain-facet-noise-hydraulic-dissection-v1'
PARENT_SCHEMA = 'metric-special-terrain-v1'
PARENT_ARRAY_KEYS = {'reference_xyz_m', 'displacement_xyz_m', 'vertices_xyz_m', 'triangles', 'protected_mask'}
AUDIT_SURFACE_ARRAY_KEYS = PARENT_ARRAY_KEYS | {'surface_xyz_m', 'erosion_change_m'}
AUDIT_SURFACE_METADATA_KEYS = {'schema', 'algorithm', 'coordinates', 'base', 'supersedes_algorithm', 'recipe', 'parameter_sources', 'source_identity', 'protection_identity', 'parent_schema', 'parent_algorithm', 'parent_identity_sha256', 'parent_kind', 'facet_recipe', 'facet_source', 'facet_wavelengths_m', 'dissection_recipe', 'dissection_source', 'kernel_revisions', 'relief_reference_m', 'roughened_relief_reference_m', 'targets', 'ledger', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'}
FACET_KEYS = {'seed', 'scales', 'amplitude_fraction'}
DISSECTION_KEYS = {'repose_angle_deg', 'steps', 'detachment_per_step_m', 'maximum_cut_fraction', 'maximum_incision_fraction', 'mobile_fraction', 'mobile_minimum_m', 'deposition_fraction', 'tolerance_m', 'max_sweeps'}
RETIRED_RECIPE_FIELDS = ('immobile_rock_fraction',)
LEDGER_SCALARS = ('transport_coefficient', 'mobile_reference_m', 'rock_floor_depth_m', 'detachment_ledger_m3', 'transport_deposition_ledger_m3', 'relaxation_transferred_ledger_m3', 'maximum_incision_m', 'maximum_deposition_m', 'net_change_ledger_m3', 'relaxation_tolerance_m', 'relaxation_sweep_budget', 'relaxation_maximum_excess_m')
LEDGER_COUNTS = ('incised_cells', 'deposited_cells', 'relaxation_sweeps_max')
STEP_KEYS = ('step_index', 'routed_discharge_max_m3_s', 'edge_slope_max_m_per_m', 'detachment_volume_m3', 'detachment_depth_max_m', 'transport_deposition_volume_m3', 'transport_change_max_m', 'relaxation_transferred_volume_m3', 'relaxation_change_max_m', 'relaxation_raw_residual_bulk_m3', 'relaxation_sweeps', 'relaxation_converged', 'relaxation_maximum_excess_m', 'relaxation_immobile_excess_m', 'relaxation_stalled_at_float64_resolution', 'mobile_column_volume_m3')
PHASE_KEYS = ('step_index', 'phase', 'injected_bulk_m3', 'exported_bulk_m3', 'lost_bulk_m3', 'inlet_correction_bulk_m3', 'raw_residual_bulk_m3')
SHA256_LENGTH = 64

def mixture(value):
    """The auditor's own bit-mixing step, re-derived from the published constants."""
    value = _i36_np.asarray(value, dtype=_i36_np.uint64)
    value = value ^ value >> _i36_np.uint64(30)
    value = value * _i36_np.uint64(13787848793156543929)
    value = value ^ value >> _i36_np.uint64(27)
    value = value * _i36_np.uint64(10723151780598845931)
    return value ^ value >> _i36_np.uint64(31)

def lattice(x, z, seed, salt):
    with _i36_np.errstate(over='ignore'):
        bits = _i36_np.asarray(x, dtype=_i36_np.int64).astype(_i36_np.uint64) * _i36_np.uint64(11400714785074694791)
        bits ^= _i36_np.asarray(z, dtype=_i36_np.int64).astype(_i36_np.uint64) * _i36_np.uint64(14029467366897019727)
        bits ^= _i36_np.uint64(seed & 18446744073709551615) + _i36_np.uint64(salt)
        return (mixture(bits) >> _i36_np.uint64(11)).astype(_i36_np.float64) / (1 << 53) * 2 - 1

def smooth_noise(x, z, spacing, seed, salt):
    gx, gz = (x / spacing, z / spacing)
    ix, iz = (_i36_np.floor(gx).astype(_i36_np.int64), _i36_np.floor(gz).astype(_i36_np.int64))
    fx, fz = (gx - ix, gz - iz)
    fx, fz = (fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz))
    a, b = (lattice(ix, iz, seed, salt), lattice(ix + 1, iz, seed, salt))
    c, d = (lattice(ix, iz + 1, seed, salt), lattice(ix + 1, iz + 1, seed, salt))
    return (a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz

def noise_field(x, z, seed, salt, scales):
    """Weighted octave sum, with the auditor's own salt progression and normaliser."""
    result, total = (_i36_np.zeros_like(x, dtype=_i36_np.float64), 0.0)
    for octave, (spacing, weight) in enumerate(scales):
        result += weight * smooth_noise(x, z, spacing, seed, salt + octave * 811)
        total += weight
    return result / total

def audit_surface_minimal_scope(result):
    require(isinstance(result, dict) and set(result) == {'arrays', 'metadata', 'identity_sha256'}, 'unexpected bundle fields')
    require(set(result['arrays']) == AUDIT_SURFACE_ARRAY_KEYS, 'unexpected surface array keys')
    require(set(result['metadata']) == AUDIT_SURFACE_METADATA_KEYS, 'unexpected surface metadata keys')

def surface_headers(headers):
    require(set(headers) == AUDIT_SURFACE_ARRAY_KEYS | {'manifest'}, 'unexpected surface archive members')
    require(headers['reference_xyz_m'][1] == _i36_np.dtype('float64'), 'surface reference is not float64')

def parent_scope(result):
    require(isinstance(result, dict) and set(result) == {'arrays', 'metadata', 'identity_sha256'}, 'unexpected parent bundle fields')
    require(set(result['arrays']) == PARENT_ARRAY_KEYS, 'unexpected parent array keys')

def uniform_spacing(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = _i36_np.concatenate((_i36_np.linalg.norm(_i36_np.diff(horizontal, axis=0), axis=2).ravel(), _i36_np.linalg.norm(_i36_np.diff(horizontal, axis=1), axis=2).ravel()))
    require(bool(_i36_np.isfinite(adjacent).all()) and bool(_i36_np.all(adjacent > 0.0)), 'invalid spacing')
    spacing = float(adjacent.max())
    require(spacing - float(adjacent.min()) < TOLERANCE * spacing, 'chart is not a uniform grid')
    return spacing

def rebuild_facet(reference, parent_displacement, facet_recipe, spacing):
    """Own reconstruction of the facet relief from the declared recipe alone."""
    require(set(facet_recipe) == FACET_KEYS, 'unexpected facet recipe keys')
    seed = facet_recipe['seed']
    require(type(seed) is int and 0 <= seed < 2 ** 64, 'facet seed is not uint64')
    scales = facet_recipe['scales']
    require(isinstance(scales, list) and 1 <= len(scales) <= 8, 'unexpected facet octave list')
    for pair in scales:
        require(isinstance(pair, list) and len(pair) == 2 and all((type(value) is float and _i36_np.isfinite(value) and (value > 0.0) for value in pair)), 'unexpected facet octave')
    amplitude = facet_recipe['amplitude_fraction']
    require(type(amplitude) is float and 0.0 < amplitude <= 0.5, 'facet amplitude outside range')
    top = parent_displacement[:, :, 1]
    peak = float(_i36_np.max(top))
    require(_i36_np.isfinite(peak) and peak > 0.0, 'parent chart carries no relief to roughen')
    metres = [(cells * spacing, weight) for cells, weight in scales]
    noise = noise_field(reference[:, :, 0], reference[:, :, 2], seed, 1901, metres)
    require(noise.shape == top.shape and bool(_i36_np.isfinite(noise).all()), 'nonfinite facet noise')
    noise = noise - float(_i36_np.mean(noise, dtype=_i36_np.float64))
    scale = float(_i36_np.max(_i36_np.abs(noise)))
    require(_i36_np.isfinite(scale) and scale > 0.0, 'degenerate facet noise field')
    taper = _i36_np.clip(top / peak, 0.0, 1.0)
    return noise / scale * taper * (amplitude * peak)

def audit_surface_audit_mesh(vertices, triangles):
    """Own non-degeneracy and orientation check; no generator mesh helper is reused."""
    points = vertices[triangles]
    first, second = (points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    cross = _i36_np.cross(first, second)
    scale = _i36_np.linalg.norm(first, axis=1) * _i36_np.linalg.norm(second, axis=1)
    require(bool(_i36_np.isfinite(points).all()) and bool(_i36_np.isfinite(cross).all()), 'nonfinite triangle')
    require(bool(_i36_np.all(scale > 0.0)), 'degenerate triangle edge')
    area = _i36_np.linalg.norm(cross, axis=1)
    require(bool(_i36_np.all(area > 1e-12 * scale)), 'degenerate triangle area')
    plan = _i36_np.abs(cross[:, 1]) / _i36_np.maximum(area, 1e-300)
    return {'triangles': int(triangles.shape[0]), 'min_area_ratio': float(_i36_np.min(area / scale)), 'min_plan_view_alignment': float(_i36_np.min(plan))}

def audit_targets(change, reference, parent_recipe):
    """Replay every declared target footprint and re-measure its incision."""
    x, z = (reference[:, :, 0], reference[:, :, 2])
    record = {}
    for target in parent_recipe['targets']:
        across = (x - target['center_x_m']) / target['radius_x_m']
        along = (z - target['center_z_m']) / target['radius_z_m']
        inside = _i36_np.sqrt(across * across + along * along) <= 1.0
        record[target['target_id']] = {'footprint_cells': int(inside.sum()), 'maximum_incision_m': float(_i36_np.max(-change[inside])) if inside.any() else 0.0, 'maximum_deposition_m': float(_i36_np.max(change[inside])) if inside.any() else 0.0}
    return record

def audit_surface_audit_bundle(path, *, expected_sha256, parents, parent_manifest):
    result = _i36_load_bundle(path, expected_sha256=expected_sha256, validator=audit_surface_minimal_scope, header_validator=surface_headers)
    metadata, arrays = (result['metadata'], result['arrays'])
    require(metadata['schema'] == SURFACE_SCHEMA and metadata['algorithm'] == SURFACE_ALGORITHM, 'unexpected surface identity')
    require(metadata['supersedes_algorithm'] == SUPERSEDED, 'missing superseded identity')
    require(metadata['parent_schema'] == PARENT_SCHEMA, 'unexpected parent schema')
    require(metadata['coordinates'] == 'xyz metres; chart [row,col]', 'unexpected coordinates')
    for flag in FLAGS:
        require(metadata[flag] is False, f'bundle prematurely promoted capability: {flag}')
    require(any((field in metadata['dissection_recipe'] for field in RETIRED_RECIPE_FIELDS)) is False, 'retired dissection recipe field is still present')
    require(set(metadata['dissection_recipe']) == DISSECTION_KEYS, 'unexpected dissection recipe keys')
    kind = metadata['parent_kind']
    require(kind in parent_manifest['forms'], 'parent kind is not in the parent manifest')
    entry = parent_manifest['forms'][kind]
    parent = _i36_load_bundle(parents / entry['file'], expected_sha256=entry['sha256'], validator=parent_scope)
    require(metadata['parent_identity_sha256'] == entry['identity_sha256'], 'declared parent identity differs from the parent manifest')
    require(metadata['parent_identity_sha256'] == parent['identity_sha256'], 'parent bundle on disk does not carry the declared identity')
    require(metadata['parent_algorithm'] == parent['metadata']['algorithm'], 'declared parent algorithm differs from the parent bundle')
    reference = arrays['reference_xyz_m']
    require(bool(_i36_np.array_equal(reference, parent['arrays']['reference_xyz_m'])), 'surface chart is not the parent chart')
    require(bool(_i36_np.array_equal(arrays['protected_mask'], parent['arrays']['protected_mask'])), 'surface protection differs from the parent')
    spacing = uniform_spacing(reference)
    parent_displacement = parent['arrays']['displacement_xyz_m']
    displacement = arrays['displacement_xyz_m']
    surface = arrays['surface_xyz_m']
    change = arrays['erosion_change_m']
    mask = arrays['protected_mask']
    facet = rebuild_facet(reference, parent_displacement, metadata['facet_recipe'], spacing)
    facet[mask] = 0.0
    require(bool(_i36_np.array_equal(displacement[:, :, 0], parent_displacement[:, :, 0])) and bool(_i36_np.array_equal(displacement[:, :, 2], parent_displacement[:, :, 2])), 'horizontal displacement changed')
    rebuilt_roughened = parent_displacement[:, :, 1] + facet
    maximum_difference = float(_i36_np.max(_i36_np.abs(rebuilt_roughened - displacement[:, :, 1])))
    require(maximum_difference < TOLERANCE, f'replayed facet relief differs from the stored displacement ({maximum_difference:.3e})')
    metres = [cells * spacing for cells, _ in metadata['facet_recipe']['scales']]
    require([pair[0] for pair in metadata['facet_wavelengths_m']] == metres, 'declared facet wavelengths disagree with the recipe')
    require(metadata['relief_reference_m'] == float(_i36_np.max(parent_displacement[:, :, 1])), 'declared parent relief disagrees with the parent chart')
    require(metadata['roughened_relief_reference_m'] == float(_i36_np.max(displacement[:, :, 1])) and metadata['roughened_relief_reference_m'] >= metadata['relief_reference_m'], 'declared roughened relief disagrees with the stored displacement')
    recipe = metadata['dissection_recipe']
    roughened = reference[:, :, 1] + displacement[:, :, 1]
    depth = recipe['maximum_incision_fraction'] * metadata['roughened_relief_reference_m']
    floor = _i36_np.minimum(_i36_np.maximum(roughened - depth, reference[:, :, 1]), roughened)
    final = surface[:, :, 1]
    worst = float(_i36_np.min(final - floor))
    require(worst >= -TOLERANCE, f'final bed crosses the recomputed rock floor by {-worst:.3e} m')
    require(float(_i36_np.max(_i36_np.abs(final - (roughened + change)))) < TOLERANCE, 'stored change does not close the roughened surface')
    ledger = metadata['ledger']
    require(all((name in ledger for name in LEDGER_SCALARS + LEDGER_COUNTS)), 'ledger is missing a declared scalar')
    require(float(_i36_np.sum(change) * spacing ** 2) == ledger['net_change_ledger_m3'], 'net change ledger disagrees with the stored change')
    require(int(_i36_np.sum(change < 0.0)) == ledger['incised_cells'] and int(_i36_np.sum(change > 0.0)) == ledger['deposited_cells'], 'incision cell counts disagree with the stored change')
    require(ledger['maximum_incision_m'] == float(_i36_np.max(-change)) and ledger['maximum_deposition_m'] == float(_i36_np.max(change)), 'incision extremes disagree with the stored change')
    require(all((ledger[name] >= 0.0 for name in ('detachment_ledger_m3', 'transport_deposition_ledger_m3', 'relaxation_transferred_ledger_m3', 'rock_floor_depth_m'))), 'a dissection ledger term is negative')
    require(ledger['rock_floor_depth_m'] == depth, 'declared rock floor depth is not the recipe depth')
    steps = ledger['steps']
    require(isinstance(steps, list) and len(steps) == recipe['steps'] and ([step['step_index'] for step in steps] == list(range(recipe['steps']))), 'step ledger does not match the declared dissection steps')
    for step in steps:
        require(set(step) == set(STEP_KEYS), 'unexpected dissection step keys')
    require(ledger['relaxation_tolerance_m'] == recipe['tolerance_m'] and ledger['relaxation_sweep_budget'] == recipe['max_sweeps'], 'relaxation budget does not match the declared dissection recipe')
    derived_converged = all((step['relaxation_maximum_excess_m'] <= recipe['tolerance_m'] for step in steps))
    require(all((bool(step['relaxation_converged']) == (step['relaxation_maximum_excess_m'] <= recipe['tolerance_m']) for step in steps)), "a step's convergence flag disagrees with its own recorded excess")
    require(ledger['relaxation_converged'] is derived_converged, 'relaxation summary flag disagrees with the per-step excess')
    require(ledger['relaxation_maximum_excess_m'] == max((step['relaxation_maximum_excess_m'] for step in steps)) and ledger['relaxation_sweeps_max'] == max((step['relaxation_sweeps'] for step in steps)), 'relaxation extremes disagree with the per-step records')
    for step in steps:
        unresolved = step['relaxation_maximum_excess_m'] > recipe['tolerance_m']
        require(step['relaxation_sweeps'] <= recipe['max_sweeps'], 'a relaxation step exceeded the declared sweep budget')
        require(not (unresolved and step['relaxation_stalled_at_float64_resolution']), 'a relaxation step stalled short of repose')
    require(ledger['phase_balance']['phase'] == 'hydraulic-dissection' and set(ledger['phase_balance']) == set(PHASE_KEYS), 'unexpected phase balance record')
    require(ledger['phase_balance']['exported_bulk_m3'] == -ledger['net_change_ledger_m3'], 'phase balance export term disagrees with the net change ledger')
    recomputed_targets = audit_targets(change, reference, parent['metadata']['recipe'])
    require(set(recomputed_targets) == set(metadata['targets']), 'target id set differs')
    for target_id, record in recomputed_targets.items():
        stored = metadata['targets'][target_id]
        require(stored['footprint_cells'] == record['footprint_cells'] and stored['maximum_incision_m'] == record['maximum_incision_m'] and (stored['maximum_deposition_m'] == record['maximum_deposition_m']), f'target {target_id} incision record does not replay')
    revisions = metadata['kernel_revisions']
    for name, digest in revisions.items():
        require(len(digest) == SHA256_LENGTH and _i36_hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, f'kernel revision mismatch for {name}')
    perimeter = {'first_row': bool(_i36_np.all(displacement[0] == 0) and _i36_np.all(change[0] == 0)), 'last_row': bool(_i36_np.all(displacement[-1] == 0) and _i36_np.all(change[-1] == 0)), 'first_column': bool(_i36_np.all(displacement[:, 0] == 0) and _i36_np.all(change[:, 0] == 0)), 'last_column': bool(_i36_np.all(displacement[:, -1] == 0) and _i36_np.all(change[:, -1] == 0))}
    require(all(perimeter.values()), 'chart perimeter carries displacement or change')
    require(bool(_i36_np.all(change[mask] == 0.0)), 'a protected cell was dissected')
    require(bool(_i36_np.array_equal(surface[0], reference[0])) and bool(_i36_np.array_equal(surface[-1], reference[-1])) and bool(_i36_np.array_equal(surface[:, 0], reference[:, 0])) and bool(_i36_np.array_equal(surface[:, -1], reference[:, -1])), 'surface no longer closes on its collar')
    vertices = arrays['vertices_xyz_m']
    require(bool(_i36_np.array_equal(vertices, surface.reshape(-1, 3))), 'stored vertices are not the stored surface')
    mesh = audit_surface_audit_mesh(vertices, arrays['triangles'])
    recomputed_identity = _i36_identity(arrays, metadata)
    require(recomputed_identity == result['identity_sha256'], 'identity does not replay')
    return {'kind': kind, 'parent_identity_sha256': metadata['parent_identity_sha256'], 'chart_shape': [int(reference.shape[0]), int(reference.shape[1])], 'spacing_m': spacing, 'relief_reference_m': metadata['relief_reference_m'], 'roughened_relief_reference_m': metadata['roughened_relief_reference_m'], 'max_facet_replay_difference_m': maximum_difference, 'rock_floor_depth_m': depth, 'min_bed_minus_floor_m': worst, 'maximum_incision_m': ledger['maximum_incision_m'], 'maximum_deposition_m': ledger['maximum_deposition_m'], 'incised_cells': ledger['incised_cells'], 'deposited_cells': ledger['deposited_cells'], 'net_change_m3': ledger['net_change_ledger_m3'], 'detachment_ledger_m3': ledger['detachment_ledger_m3'], 'transport_deposition_ledger_m3': ledger['transport_deposition_ledger_m3'], 'relaxation_transferred_ledger_m3': ledger['relaxation_transferred_ledger_m3'], 'relaxation_converged': ledger['relaxation_converged'], 'relaxation_tolerance_m': ledger['relaxation_tolerance_m'], 'relaxation_maximum_excess_m': ledger['relaxation_maximum_excess_m'], 'relaxation_sweeps_max': ledger['relaxation_sweeps_max'], 'targets': recomputed_targets, 'perimeter_zero': perimeter, 'mesh': mesh, 'identity_sha256': result['identity_sha256'], 'status': 'candidate', 'flags': {flag: metadata[flag] for flag in FLAGS}, 'caveat': 'Facet noise, rock floor, ledger scalars, target footprints, kernel pins and identity are all re-derived here from the stored arrays and the parent bundle; the transpose of the transport and repose kernels themselves is imported by the producer and is outside this audit, so hydraulic legality and solid self-intersection remain uncertified and every flag stays false.'}

def _entry_audit_special_terrain_surface(argv=None):
    parser = _i36_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundles', type=_i36_Path, help='directory holding the surface <kind>.npz and manifest-report.json')
    parser.add_argument('--parents', type=_i36_Path, required=True, help='directory holding the parent <kind>.npz and manifest-report.json')
    parser.add_argument('--output', type=_i36_Path, default=None)
    args = parser.parse_args(argv)
    manifest = _i36_json.loads((args.bundles / 'manifest-report.json').read_text(encoding='utf-8'))
    parent_manifest = _i36_json.loads((args.parents / 'manifest-report.json').read_text(encoding='utf-8'))
    report = {'audit_schema': AUDIT_SURFACE_AUDIT_SCHEMA, 'generator_imported': False, 'bundle_directory': str(args.bundles), 'parent_directory': str(args.parents), 'forms': {}, 'failures': {}}
    for kind, entry in sorted(manifest['forms'].items()):
        path = args.bundles / entry['file']
        try:
            audited = audit_surface_audit_bundle(path, expected_sha256=entry['sha256'], parents=args.parents, parent_manifest=parent_manifest)
            require(audited['identity_sha256'] == entry['identity_sha256'], 'audited identity differs from the manifest identity')
            report['forms'][kind] = audited
            print(f"{kind}: pass identity={audited['identity_sha256'][:16]} facet_delta={audited['max_facet_replay_difference_m']:.3e} bed_minus_floor={audited['min_bed_minus_floor_m']:.3e}")
        except ValueError as error:
            report['failures'][kind] = str(error)
            print(f'{kind}: FAIL {error}')
    output = args.output or args.bundles / 'independent-audit.json'
    output.write_text(_i36_json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'audit: {output}')
    print(f"passed={len(report['forms'])} failed={len(report['failures'])}")
    return 1 if report['failures'] else 0

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'forms': '_entry_audit_special_terrain_forms', 'surface': '_entry_audit_special_terrain_surface'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('command', choices=tuple(commands))
        parsed, values = parser.parse_known_args(values)
        selected = parsed.command
    function = globals()[commands[selected]]
    previous = sys.argv
    try:
        sys.argv = [previous[0]] + values
        return function(values) if inspect.signature(function).parameters else function()
    finally:
        sys.argv = previous
if __name__ == '__main__':
    main()
