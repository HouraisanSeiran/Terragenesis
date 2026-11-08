"""Consolidated prepare_vdm_fault implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i38_argparse
import json as _i38_json
from pathlib import Path as _i38_Path
import sys as _i38_sys
import time as _i38_time
import numpy as _i38_np
from terrain_pipeline.vdm_cuts import load_formed_vdm as _i38_load_formed_vdm
from terrain_pipeline.vdm_cuts import FaultRecipe as _i38_FaultRecipe
from terrain_pipeline.vdm_cuts import apply_fault as _i38_apply_fault
from terrain_pipeline.vdm_cuts import load_fault as _i38_load_fault
from terrain_pipeline.vdm_cuts import save_fault as _i38_save_fault
from terrain_pipeline.common_infra import file_sha256 as _i38_file_sha256
from terrain_pipeline.common_infra import publish_bytes as _i38_publish_bytes
import argparse as _i37_argparse
from datetime import datetime as _i37_datetime
from datetime import timezone as _i37_timezone
import json as _i37_json
from pathlib import Path as _i37_Path
import sys as _i37_sys
from terrain_pipeline.common_infra import file_sha256 as _i37_file_sha256
CATEGORY = 'C'
PREPARE_METRIC_VDM_FAULT_MECHANISM_2_ROOT = _i38_Path(__file__).resolve().parents[1]
_i38_sys.path.insert(0, str(PREPARE_METRIC_VDM_FAULT_MECHANISM_2_ROOT))

def publish(path, value):
    _i38_publish_bytes(path, _i38_json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))

def prepare_metric_vdm_fault_mechanism_2_prepare(configuration, output):
    start = _i38_time.perf_counter()
    configuration = _i38_Path(configuration).resolve(strict=True)
    config_sha = _i38_file_sha256(configuration)
    config = _i38_json.loads(configuration.read_text(encoding='utf-8'))
    source = _i38_load_formed_vdm(**config['source'])
    chosen = config['selection']
    selection = _i38_np.zeros(source['arrays']['reference_xyz_m'].shape[:2], bool)
    selection[chosen['row_start']:chosen['row_stop'], chosen['column_start']:chosen['column_stop']] = True
    recipe = _i38_FaultRecipe(**{**config['fault'], 'plane_origin_xz_m': tuple(config['fault']['plane_origin_xz_m'])})
    result = _i38_apply_fault(source, recipe=recipe, selection_mask=selection)
    output = _i38_Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    _i38_save_fault(output / 'fault.npz', result)
    fault_sha = _i38_file_sha256(output / 'fault.npz')
    loaded = _i38_load_fault(output / 'fault.npz', expected_sha256=fault_sha, expected_identity=result['identity_sha256'])
    arrays = loaded['arrays']
    edge = arrays['vertex_source_edge']
    fraction = arrays['vertex_source_fraction'][:, None]
    baseline = source['arrays']['vertices_xyz_m']
    expected = baseline[edge[:, 0]] * (1.0 - fraction) + baseline[edge[:, 1]] * fraction
    before = arrays['vertices_xyz_m'] - arrays['applied_displacement_xyz_m']
    difference = float(_i38_np.max(_i38_np.abs(before - expected)))
    if difference > 1e-08:
        raise ValueError('independent VDM preservation audit failed')
    if _i38_file_sha256(configuration) != config_sha or _i38_file_sha256(config['source']['path']) != config['source']['expected_sha256']:
        raise ValueError('source changed during preparation')
    audit = {'schema': 'metric-vdm-fault-audit-v2', 'passed': True, 'file_sha256': fault_sha, 'identity': {'passed': True, 'stored': result['identity_sha256'], 'expected': result['identity_sha256']}, 'max_vdm_preservation_error_m': difference, 'source_vdm_identity': source['identity_sha256'], 'source_vdm_preserved': True, 'cold_read': True, 'self_intersection_verified': False}
    publish(output / 'audit.json', audit)
    geometry = {'vertices': len(arrays['vertices_xyz_m']), 'triangles': len(arrays['triangles']), 'seam_edges': len(arrays['seam_edges']), 'moved_vertices': int(_i38_np.count_nonzero(_i38_np.linalg.norm(arrays['applied_displacement_xyz_m'], axis=1) > 1e-12)), 'max_displacement_m': float(_i38_np.linalg.norm(arrays['applied_displacement_xyz_m'], axis=1).max())}
    flags = {'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False, 'solver_advanced': False}
    pin = {'path': str(output / 'fault.npz'), 'expected_sha256': fault_sha, 'expected_identity': result['identity_sha256']}
    report = {'schema': 'metric-vdm-fault-preparation-v2', 'fault': result['metadata'], 'fault_bundle': pin, 'selection': chosen, 'source': config['source'], 'geometry': geometry, 'source_vdm_preserved': True, 'elapsed_s': _i38_time.perf_counter() - start, **flags}
    publish(output / 'report.json', report)
    index = {'schema': 'metric-vdm-fault-delivery-v2', 'algorithm': result['metadata']['algorithm'], 'configuration': {'path': str(configuration), 'sha256': config_sha}, 'source': {'path': config['source']['path'], 'sha256': config['source']['expected_sha256'], 'identity_sha256': source['identity_sha256']}, 'fault': {'path': 'fault.npz', 'sha256': fault_sha, 'identity_sha256': result['identity_sha256']}, 'audit': {'path': 'audit.json', 'sha256': _i38_file_sha256(output / 'audit.json')}, 'report': {'path': 'report.json', 'sha256': _i38_file_sha256(output / 'report.json')}, 'geometry': geometry, 'status': 'diagnostic_not_publishable', **flags}
    publish(output / 'index.json', index)
    return {'index': str(output / 'index.json'), 'sha256': _i38_file_sha256(output / 'index.json'), 'geometry': geometry, 'audit': audit}
_i37_sys.path.insert(0, str(PREPARE_METRIC_VDM_FAULT_MECHANISM_2_ROOT))

def prepare(configuration, expected_sha256, output):
    """Keep the pinned configuration API, but generate only the current schema."""
    configuration = _i37_Path(configuration).resolve(strict=True)
    if _i37_file_sha256(configuration) != expected_sha256:
        raise ValueError('fault configuration SHA mismatch')
    return prepare_metric_vdm_fault_mechanism_2_prepare(configuration, output)

def _entry_prepare_metric_vdm_fault():
    parser = _i37_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', type=_i37_Path, required=True)
    parser.add_argument('--configuration-sha256', required=True)
    parser.add_argument('--output', type=_i37_Path, default=PREPARE_METRIC_VDM_FAULT_MECHANISM_2_ROOT / '.scratch/metric-vdm-fault' / _i37_datetime.now(_i37_timezone.utc).strftime('run-%Y%m%dT%H%M%S%fZ'))
    parser.add_argument('--legacy-v1-replay', action='store_true', help='explicitly replay the hash-pinned archived v1 algorithm')
    args = parser.parse_args()
    if args.legacy_v1_replay:
        from tools.frozen_vdm_fault import replay_legacy_preparation as replay_legacy_preparation
        result = replay_legacy_preparation(args.configuration, args.configuration_sha256, args.output)
    else:
        result = prepare(args.configuration, args.configuration_sha256, args.output)
    print(_i37_json.dumps(result, ensure_ascii=False))

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'prepare-metric-vdm-fault': '_entry_prepare_metric_vdm_fault'}
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
