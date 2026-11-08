"""Consolidated audit_vdm_fault implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i41_argparse
import json as _i41_json
from pathlib import Path as _i41_Path
import sys as _i41_sys
import numpy as _i41_np
from terrain_pipeline.vdm_cuts import load_fault as _i41_load_fault
from terrain_pipeline.common_infra import file_sha256 as _i41_file_sha256
CATEGORY = 'C'
ROOT = _i41_Path(__file__).resolve().parents[1]
_i41_sys.path.insert(0, str(ROOT))

def _json_value(value):
    if isinstance(value, _i41_np.generic):
        return value.item()
    if isinstance(value, _i41_np.ndarray):
        return {'shape': list(value.shape), 'dtype': str(value.dtype)}
    return value

def audit_fault(path, *, expected_sha256=None, expected_identity=None):
    path = _i41_Path(path)
    report = {'schema': 'metric-vdm-fault-audit-v2', 'path': str(path.resolve()), 'file_sha256': _i41_file_sha256(path), 'load': {'passed': False, 'error': None}, 'structure': {'passed': False, 'checks': {}}, 'identity': {'passed': False, 'stored': None, 'expected': expected_identity}, 'semantics': {'passed': False, 'checks': {}}}
    try:
        result = _i41_load_fault(path, expected_sha256=expected_sha256 or report['file_sha256'], expected_identity=expected_identity or '0' * 64)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['load']['error'] = str(error)
        return report
    arrays = result['arrays']
    metadata = result['metadata']
    report['load']['passed'] = True
    report['identity']['stored'] = result['identity_sha256']
    report['identity']['passed'] = expected_identity in (None, result['identity_sha256'])
    required = {'vertices_xyz_m', 'triangles', 'vertex_side', 'transition_weight', 'applied_displacement_xyz_m', 'vertex_source_index', 'triangle_source_index', 'seam_edges'}
    report['structure']['checks']['required_arrays'] = sorted(required - set(arrays)) == []
    if report['structure']['checks']['required_arrays']:
        vertices = arrays['vertices_xyz_m']
        triangles = arrays['triangles']
        sides = arrays['vertex_side']
        report['structure']['checks'].update({'vertices_3d': vertices.ndim == 2 and vertices.shape[1] == 3, 'triangles_3_indices': triangles.ndim == 2 and triangles.shape[1] == 3, 'triangle_indices_in_range': bool(_i41_np.all((triangles >= 0) & (triangles < len(vertices)))), 'side_length_matches_vertices': len(sides) == len(vertices), 'finite_geometry': bool(_i41_np.isfinite(vertices).all()), 'readonly_arrays': all((not value.flags.writeable for value in arrays.values() if isinstance(value, _i41_np.ndarray)))})
    report['structure']['passed'] = all(report['structure']['checks'].values())
    report['semantics']['checks']['open_surface'] = metadata.get('closed_surface') is False
    report['semantics']['checks']['horizontal_strike'] = metadata.get('slip_axis') == 'horizontal_strike'
    report['semantics']['checks']['source_identity_present'] = bool(metadata.get('source_identity'))
    report['semantics']['checks']['transition_width_positive'] = metadata.get('transition_width_m', 0) > 0
    if report['structure']['checks'].get('required_arrays'):
        triangle_sides = arrays['vertex_side'][arrays['triangles']]
        influenced = _i41_np.any(arrays['transition_weight'][arrays['triangles']] > 0.0, axis=1)
        report['semantics']['checks']['no_cross_seam_triangle'] = not bool(_i41_np.any(_i41_np.ptp(triangle_sides[influenced], axis=1) != 0))
        weights = arrays['transition_weight']
        report['semantics']['checks']['bounded_transition'] = bool(_i41_np.isfinite(weights).all() and _i41_np.all((weights >= 0) & (weights <= 1)))
        report['semantics']['checks']['seam_edges_present'] = arrays['seam_edges'].ndim == 2
    report['semantics']['passed'] = all(report['semantics']['checks'].values())
    report['passed'] = bool(report['load']['passed'] and report['identity']['passed'] and report['structure']['passed'] and report['semantics']['passed'])
    report['metadata'] = {key: _json_value(value) for key, value in metadata.items()}
    return report

def _entry_audit_metric_vdm_fault():
    parser = _i41_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=_i41_Path, help='saved fault NPZ')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-identity')
    parser.add_argument('--output', type=_i41_Path, help='write a new JSON report')
    parser.add_argument('--legacy-v1-replay', action='store_true', help='explicitly use the pinned historical v1 validator')
    args = parser.parse_args()
    if args.legacy_v1_replay:
        from tools.frozen_vdm_fault import audit_legacy_fault as audit_legacy_fault
        auditor = audit_legacy_fault
    else:
        auditor = audit_fault
    report = auditor(args.path, expected_sha256=args.expected_sha256, expected_identity=args.expected_identity)
    encoded = _i41_json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.write_text(encoded + '\n', encoding='utf-8')
    raise SystemExit(0 if report.get('passed') else 1)

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'audit-metric-vdm-fault': '_entry_audit_metric_vdm_fault'}
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
