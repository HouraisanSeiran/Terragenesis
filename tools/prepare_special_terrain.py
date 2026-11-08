"""Consolidated prepare_special_terrain implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i31_argparse
import json as _i31_json
from pathlib import Path as _i31_Path
import sys as _i31_sys
import numpy as _i31_np
from terrain_pipeline.special_terrain import KINDS as _i31_KINDS
from terrain_pipeline.special_terrain import METRIC_FORMS_SCHEMA as _i31_SCHEMA
from terrain_pipeline.special_terrain import METRIC_FORMS_ALGORITHM as _i31_ALGORITHM
from terrain_pipeline.special_terrain import analytic_base_chart as _i31_analytic_base_chart
from terrain_pipeline.special_terrain import build_special_form_vdm as _i31_build_special_form_vdm
from terrain_pipeline.special_terrain import form_preset as _i31_form_preset
from terrain_pipeline.special_terrain import save_special_form_vdm as _i31_save_special_form_vdm
from terrain_pipeline.common_infra import file_sha256 as _i31_file_sha256
import argparse as _i32_argparse
import json as _i32_json
from pathlib import Path as _i32_Path
import sys as _i32_sys
import numpy as _i32_np
from terrain_pipeline.special_terrain import KINDS as _i32_KINDS
from terrain_pipeline.special_terrain import load_special_form_vdm as _i32_load_special_form_vdm
from terrain_pipeline.special_terrain import METRIC_SURFACE_ALGORITHM as _i32_ALGORITHM
from terrain_pipeline.special_terrain import METRIC_SURFACE_SCHEMA as _i32_SCHEMA
from terrain_pipeline.special_terrain import SUPERSEDES_ALGORITHM as _i32_SUPERSEDES_ALGORITHM
from terrain_pipeline.special_terrain import build_special_form_surface as _i32_build_special_form_surface
from terrain_pipeline.special_terrain import save_special_form_surface as _i32_save_special_form_surface
from terrain_pipeline.special_terrain import surface_preset as _i32_surface_preset
from terrain_pipeline.common_infra import file_sha256 as _i32_file_sha256
CATEGORY = 'C'
ROOT = _i31_Path(__file__).resolve().parents[1]
_i31_sys.path.insert(0, str(ROOT))
DEFAULT_OUTPUT = _i31_Path('.scratch/special-terrain/bundles-20261019')
SOURCE_IDENTITY = 'synthetic-analytic-base-plane'
PROTECTION_IDENTITY = 'no-protected-cells'

def build_one(kind):
    recipe = _i31_form_preset(kind)
    chart = _i31_analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m, spacing_m=recipe.spacing_m)
    mask = _i31_np.zeros(chart.shape[:2], dtype=bool)
    return _i31_build_special_form_vdm(chart, recipe=recipe, protected_mask=mask, source_identity=SOURCE_IDENTITY, protection_identity=PROTECTION_IDENTITY)

def _entry_prepare_special_terrain_forms(argv=None):
    parser = _i31_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=_i31_Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--kinds', default=','.join(sorted(_i31_KINDS)))
    args = parser.parse_args(argv)
    requested = [value for value in args.kinds.split(',') if value]
    unknown = sorted(set(requested) - _i31_KINDS)
    if unknown:
        raise SystemExit(f'unknown kinds: {unknown}')
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'schema': _i31_SCHEMA, 'algorithm': _i31_ALGORITHM, 'base': 'synthetic_analytic', 'status': 'candidate', 'forms': {}}
    for kind in sorted(set(requested)):
        result = build_one(kind)
        path = args.output / f'{kind}.npz'
        _i31_save_special_form_vdm(path, result)
        recipe = _i31_form_preset(kind)
        report['forms'][kind] = {'file': path.name, 'sha256': _i31_file_sha256(path), 'identity_sha256': result['identity_sha256'], 'chart_rows': int(result['arrays']['reference_xyz_m'].shape[0]), 'chart_cols': int(result['arrays']['reference_xyz_m'].shape[1]), 'spacing_m': recipe.spacing_m, 'target_count': len(recipe.targets), 'max_relief_m': float(_i31_np.max(result['arrays']['displacement_xyz_m'][:, :, 1])), 'parameter_sources': result['metadata']['parameter_sources'][kind]}
        print(f"{kind}: {path.name} identity={result['identity_sha256']}")
    report_path = args.output / 'manifest-report.json'
    report_path.write_text(_i31_json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'report: {report_path}')
    return 0
_i32_sys.path.insert(0, str(ROOT))
DEFAULT_PARENTS = _i32_Path('.scratch/special-terrain/bundles-20261019')
PREPARE_SURFACE_DEFAULT_OUTPUT = _i32_Path('.scratch/special-terrain/surface-20261020')

def load_parent(parents, kind):
    manifest = _i32_json.loads((parents / 'manifest-report.json').read_text(encoding='utf-8'))
    entry = manifest['forms'][kind]
    parent = _i32_load_special_form_vdm(parents / entry['file'], expected_sha256=entry['sha256'], expected_identity=entry['identity_sha256'])
    return (parent, manifest, entry)

def _entry_prepare_special_terrain_surface(argv=None):
    parser = _i32_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parents', type=_i32_Path, default=DEFAULT_PARENTS)
    parser.add_argument('--output', type=_i32_Path, default=PREPARE_SURFACE_DEFAULT_OUTPUT)
    parser.add_argument('--kinds', default=','.join(sorted(_i32_KINDS)))
    args = parser.parse_args(argv)
    requested = [value for value in args.kinds.split(',') if value]
    unknown = sorted(set(requested) - _i32_KINDS)
    if unknown:
        raise SystemExit(f'unknown kinds: {unknown}')
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'schema': _i32_SCHEMA, 'algorithm': _i32_ALGORITHM, 'supersedes_algorithm': _i32_SUPERSEDES_ALGORITHM, 'parents': str(args.parents), 'status': 'candidate', 'forms': {}}
    for kind in sorted(set(requested)):
        parent, manifest, entry = load_parent(args.parents, kind)
        roughness, dissection = _i32_surface_preset(kind)
        result = _i32_build_special_form_surface(parent, roughness=roughness, dissection=dissection)
        path = args.output / f'{kind}.npz'
        _i32_save_special_form_surface(path, result)
        metadata, arrays = (result['metadata'], result['arrays'])
        change = arrays['erosion_change_m']
        spacing = float(arrays['reference_xyz_m'][0, 1, 0] - arrays['reference_xyz_m'][0, 0, 0])
        report['forms'][kind] = {'file': path.name, 'sha256': _i32_file_sha256(path), 'identity_sha256': result['identity_sha256'], 'parent_file': entry['file'], 'parent_sha256': entry['sha256'], 'parent_identity_sha256': metadata['parent_identity_sha256'], 'chart_rows': int(arrays['reference_xyz_m'].shape[0]), 'chart_cols': int(arrays['reference_xyz_m'].shape[1]), 'spacing_m': spacing, 'relief_reference_m': metadata['relief_reference_m'], 'roughened_relief_reference_m': metadata['roughened_relief_reference_m'], 'facet_recipe': metadata['facet_recipe'], 'facet_wavelengths_m': metadata['facet_wavelengths_m'], 'dissection_recipe': metadata['dissection_recipe'], 'kernel_revisions': metadata['kernel_revisions'], 'ledger': metadata['ledger'], 'net_change_m3_recomputed': float(_i32_np.sum(change) * spacing ** 2), 'target_count': len(metadata['targets'])}
        print(f"{kind}: {path.name} identity={result['identity_sha256'][:16]} relief={metadata['relief_reference_m']:.2f}->{metadata['roughened_relief_reference_m']:.2f} m incision_max={metadata['ledger']['maximum_incision_m']:.3f} m relax_converged={metadata['ledger']['relaxation_converged']}")
    report_path = args.output / 'manifest-report.json'
    report_path.write_text(_i32_json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'report: {report_path}')
    return 0

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'forms': '_entry_prepare_special_terrain_forms', 'surface': '_entry_prepare_special_terrain_surface'}
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
