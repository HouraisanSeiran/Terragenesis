"""Saved-only whole-polynomial witnesses for source-bank boundary refusals."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from tools.audit_td_fine_bed_shards import read, check_memory
from tools.audit_saved_source_conforming_banks import native_edge_polynomial

def maximum_polynomial_error(coefficients):
    constant, linear, quadratic = coefficients
    parameters = [0.0, 1.0]
    if quadratic != 0:
        critical = -linear / (2 * quadratic)
        if 0 < critical < 1:
            parameters.append(float(critical))
    return max((abs(constant + linear * value + quadratic * value ** 2) for value in parameters))

def diagnose(index, audit=None):
    if audit is not None and (audit['status'] != 'passed' or audit['manifest_sha256'] != index['manifest']['sha256']):
        raise ValueError('matching saved source-bank audit required')
    manifest = read(index['manifest'])
    hierarchy_pin = index['inputs']['hierarchy']
    hierarchy = load_basin_hierarchy(hierarchy_pin['path'], expected_sha256=hierarchy_pin['sha256'], expected_identity=hierarchy_pin['identity_sha256'])
    selected = set(manifest['selected_leaf_ids'])
    component_by_triangle = {triangle: component['component_id'] for component in manifest['components'] for triangle in component['triangle_ids']}
    witnesses = {}
    for pin in index['chunks']['proofs']:
        chunk = read(pin)
        for proof in chunk['records']:
            if proof['kind'] != 'edge_function_proof' or proof['status'] != 'refused':
                continue
            components = {component_by_triangle[side['triangle_id']] for side in proof['sides'] if side['triangle_id'] in component_by_triangle}
            if components <= witnesses.keys():
                continue
            start, end = (np.asarray(proof['start_xz_m']), np.asarray(proof['end_xz_m']))
            source = native_edge_polynomial(hierarchy, selected, start, end)
            values = proof['side_depth_knots'][0]['depth_knots_m']
            if any((value is None for value in values)):
                continue
            cuts = np.array([values[0], values[1] - values[0]])
            bed = np.asarray(source['source_height_polynomial_m']).copy()
            bed[:2] -= cuts
            comparisons = []
            for side in proof['sides']:
                if not side['triangle_id'].startswith('legacy06:'):
                    continue
                points = np.asarray(side['points_xyz_m'])
                vector = points[1, [0, 2]] - points[0, [0, 2]]
                fraction = (np.array([start, end]) - points[0, [0, 2]]) @ vector / (vector @ vector)
                height = points[0, 1] + fraction * (points[1, 1] - points[0, 1])
                old = np.array([height[0], height[1] - height[0], 0.0])
                difference = bed - old
                comparisons.append(dict(legacy_triangle_id=side['triangle_id'], legacy_edge_index=side['edge_index'], legacy_absolute_bed_polynomial_m=old.tolist(), difference_polynomial_m=difference.tolist(), maximum_whole_segment_bed_mismatch_m=maximum_polynomial_error(difference)))
            if not comparisons and 'uncovered_boundary_has_nonzero_depth' not in proof['rejection_reasons']:
                continue
            witness = dict(segment_id=proof['segment_id'], start_xz_m=start.tolist(), end_xz_m=end.tolist(), source_polynomial_m=source['source_height_polynomial_m'], cut_depth_polynomial_m=cuts.tolist(), new_source_relative_bed_polynomial_m=bed.tolist(), maximum_cut_depth_m=max(values), sides=[dict(triangle_id=side['triangle_id'], edge_index=side['edge_index']) for side in proof['sides']], saved_rejection_reasons=proof['rejection_reasons'], legacy_comparisons=comparisons, proof_semantics='whole native segment polynomial including interior extrema, not a point-only continuity check')
            for component in components - witnesses.keys():
                witnesses[component] = witness
        del chunk
        check_memory()
    expected = {component['component_id'] for component in manifest['components'] if component['status'] == 'refused'}
    if set(witnesses) != expected:
        raise ValueError('not every refused component has an independently computed boundary witness')
    largest = max((comparison['maximum_whole_segment_bed_mismatch_m'] for witness in witnesses.values() for comparison in witness['legacy_comparisons']), default=0.0)
    return dict(schema='td-source-bank-boundary-diagnosis-v1', status='completed', witnesses=witnesses, refused_components_with_independent_witness=len(witnesses), largest_witness_bed_mismatch_m=largest, source_relative_components_accepted=manifest['summary']['candidate_components'], original_fill_refused_cells_remaining=manifest['summary']['original_fill_refused_cells'], source_bank_acceptance_audit_status='passed' if audit is not None else 'pending', solver_calls=0, bed_mutations=0, source_center_resamples=0, actual_peak_rss_bytes=check_memory(), next_action='include and replan the actual neighboring source-relative interface or explicit conservative closure; do not apply only the locally passing pieces')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--audit-sha256')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'verification/natural-river-network'):
        raise ValueError('new boundary diagnosis path required')
    index = read(dict(path=str(args.input.resolve()), sha256=args.sha256))
    if (args.audit is None) != (args.audit_sha256 is None):
        raise ValueError('audit path and SHA must be provided together')
    audit = read(dict(path=str(args.audit.resolve()), sha256=args.audit_sha256)) if args.audit is not None else None
    if audit is not None and audit['index_sha256'] != args.sha256:
        raise ValueError('boundary diagnosis audit does not bind actual index')
    result = diagnose(index, audit)
    result.update(index_sha256=args.sha256, independent_audit_sha256=args.audit_sha256, diagnosis_code_sha256=file_sha256(Path(__file__)))
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())
    print(json.dumps({name: value for name, value in result.items() if name != 'witnesses'}))
if __name__ == '__main__':
    main()
