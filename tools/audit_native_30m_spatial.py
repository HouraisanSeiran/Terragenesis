"""Independent raw-array graph and normal-depth audit; no tested graph/water kernels."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.common_infra import checked_archive, file_sha256
from terrain_pipeline.runoff import _strict_json as _strict_json
from tools.native_30m_graph_reference import independent_accumulation
from tools.native_30m_section_reference import normal_depth_reference
from tools.native_30m_hydraulic_reference import manning_trace_reference

BANNED = ('native_30m_source', 'native_30m_runoff', 'native_30m_reach_selection',
          'native_30m_section', 'native_30m_reach_chain', 'publish_native_30m_bundle',
          'metric_network_accumulation', 'metric_channel_solver', 'metric_sediment',
          'metric_morphology_coupling', 'world_channel_dynamics')


def read_json(path):
    with open(path, 'rb') as stream:
        raw = stream.read(1048577)
    if len(raw) > 1048576:
        raise ValueError('metadata bytes')
    return _strict_json(raw.decode('utf-8'))


def audit_raw(directory, expected_identity):
    if any(name.rsplit('.', 1)[-1] in BANNED for name in sys.modules):
        raise ValueError('independent process required')
    root = Path(directory).absolute()
    record = read_json(root / 'bundle.json')
    from terrain_pipeline.artifacts.contracts import digest
    core = {key: record[key] for key in ('schema', 'parameters', 'source_records',
                                        'stage_identities', 'files', 'capabilities')}
    if digest(core) != expected_identity or record['identity_sha256'] != expected_identity:
        raise ValueError('externally pinned numerical identity mismatch')
    allowed = {'source.npz', 'source.json', 'topology.npz', 'topology.json',
               'selection.npz', 'selection.json', 'event.npz', 'event.json', 'section.npz', 'section.json',
               'geometry.npz', 'reach_context.npz', 'reach_context.json', 'dynamics.npz',
               'discharge-diagnostic/manifest.json', 'discharge-diagnostic/arrays.npz'}
    if set(record['files']) != allowed:
        raise ValueError('file whitelist')
    for name, sha in record['files'].items():
        if file_sha256(root / name) != sha:
            raise ValueError('raw file pin mismatch:' + name)
    def load(name):
        return checked_archive(root / name, expected_sha256=record['files'][name], max_bytes=512*1024**2)
    top, sel, sec, rc = (load(key+'.npz') for key in ('topology', 'selection', 'section', 'reach_context'))
    counts, complete, processed = independent_accumulation(top['receiver'], top['valid_mask'].astype(np.float64),
                                                         top['valid_mask'], top['upstream_unknown_mask'])
    nodes = sec['node_cell_ids']
    if nodes.dtype != np.int64 or nodes.ndim != 1 or not 2 <= nodes.size <= 128 or np.any((nodes < 0) | (nodes >= counts.size)):
        raise ValueError('independent section node indices')
    for key in ('design_q_m3_s', 'width_m', 'source_slope_per_m', 'normal_depth_m'):
        value = sec[key]
        if value.dtype != np.float64 or value.shape != (nodes.size,) or not np.isfinite(value).all() or np.any(value <= 0):
            raise ValueError('independent section shape/finite:' + key)
    if sel['catchment_mask'].dtype != np.bool_ or sel['catchment_mask'].shape != counts.shape:
        raise ValueError('independent catchment mask shape')
    expected_lateral = np.r_[counts.ravel()[nodes[0]], np.diff(counts.ravel()[nodes])]
    if not np.array_equal(rc['lateral_cell_counts'], expected_lateral):
        raise ValueError('independent node attribution mismatch')
    if not complete[sel['catchment_mask']].all():
        raise ValueError('independent catchment incomplete')
    dj = read_json(root / 'discharge-diagnostic/manifest.json')
    diagnostic = load('discharge-diagnostic/arrays.npz')
    q, dc, dp = independent_accumulation(diagnostic['receiver'], diagnostic['local_q_m3_s'],
                                       diagnostic['valid_mask'], diagnostic['upstream_unknown_mask'])
    actual = diagnostic['known_routed_q_m3_s']
    if actual.dtype != np.float64 or actual.shape != q.shape or not np.isfinite(actual).all():
        raise ValueError('independent diagnostic output shape/finite')
    error = np.abs(q-actual)
    tolerance = 1e-12 + 1e-10*np.maximum(np.abs(q), np.abs(actual))
    if np.any(error > tolerance) or not np.array_equal(dc, diagnostic['complete_mask']):
        raise ValueError('independent diagnostic accumulation mismatch')
    sj = read_json(root / 'section.json')
    terminal = diagnostic['valid_mask'] & (diagnostic['receiver'] < 0)
    ledger = {'input_total_m3_s': float(diagnostic['local_q_m3_s'].sum())}
    for kind, name in (('retained', 'retained_m3_s'), ('open_outflow', 'open_outflow_m3_s'),
                       ('unknown_boundary', 'unknown_pending_m3_s')):
        ledger[name] = float(q[terminal & (diagnostic['terminal_kind'] == kind)].sum())
    ledger['residual_m3_s'] = (ledger['input_total_m3_s']-ledger['retained_m3_s']-
                              ledger['open_outflow_m3_s']-ledger['unknown_pending_m3_s'])
    ledger_tolerance = 1e-12 + 1e-10*max(abs(value) for value in ledger.values())
    if abs(ledger['residual_m3_s']) > ledger_tolerance:
        raise ValueError('independent diagnostic ledger does not close')
    for name, value in ledger.items():
        saved_value = dj['metadata']['ledger'][name]
        if type(saved_value) not in (int, float) or not np.isfinite(saved_value) or abs(saved_value-value) > ledger_tolerance:
            raise ValueError('independent diagnostic ledger mismatch:' + name)
    roughness = float(sj['actual_parameters']['manning_n'])
    depths = np.array([normal_depth_reference(float(q), float(w), float(s), roughness)
                       for q, w, s in zip(sec['design_q_m3_s'], sec['width_m'], sec['source_slope_per_m'])])
    area = sec['width_m']*sec['normal_depth_m']
    check = manning_trace_reference(area[None, :], np.ones(nodes.size), sec['width_m'],
                                    np.full(nodes.size, roughness), sec['source_slope_per_m'], np.zeros(nodes.size))
    relative = np.abs(check['outflow_q_m3_s'][0]-sec['design_q_m3_s'])/sec['design_q_m3_s']
    if relative.max() > 1e-12 or not np.allclose(depths, sec['normal_depth_m'], rtol=1e-10, atol=1e-12):
        raise ValueError('independent section conveyance mismatch')
    return {'passed': True, 'numerical_identity_sha256': expected_identity,
            'independence': {'tested_kernels_imported': False, 'banned_tokens': list(BANNED)},
            'topology_count_cells_independently_traversed': processed,
            'diagnostic_cells_independently_traversed': dp,
            'diagnostic_max_abs_error_m3_s': float(error.max()),
            'known_diagnostic_ledger_m3_s': ledger,
            'ledger_note': 'known local supply only; balance does not certify missing external upstream water',
            'diagnostic_max_error_over_tolerance': float((error/tolerance).max()),
            'section_nodes_checked': int(nodes.size),
            'normal_depth_max_abs_difference_m': float(np.max(np.abs(depths-sec['normal_depth_m']))),
            'section_conveyance_max_relative_residual': float(relative.max()),
            'scope': 'entire saved finite graph and sampled source-bed normal-depth section; not natural outlet or magnitude certification'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if Path(args.output).exists():
        raise FileExistsError(args.output)
    report = audit_raw(args.data, args.identity)
    with open(args.output, 'x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
