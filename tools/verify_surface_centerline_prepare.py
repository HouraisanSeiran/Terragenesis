"""Fixed CPU-only implementation verification; not independent acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.channel_geometry import SmoothingRecipe, build_centerline
from terrain_pipeline.channel_geometry import ChannelRecipe, plan_channel
from terrain_pipeline.surface_domain import load_surface_centerline, save_surface_centerline, slice_surface_centerline
from terrain_pipeline.surface_domain import SurfaceNetworkBudget
from tests.test_surface_domain import bent_plan, prepare_case, rehash_result, write_package

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def check_readonly(arrays):
    for array in arrays.values():
        try:
            array.setflags(write=True)
        except ValueError:
            continue
        raise AssertionError('array allows write flag restoration')

def record_case(destination, name, result, expected_status):
    require(result['status'] == expected_status, name + ': unexpected status')
    diagnostic = expected_status != 'prepared'
    path = destination / (name + '.npz')
    save_surface_centerline(result, path, allow_diagnostic=diagnostic)
    loaded = load_surface_centerline(path, allow_diagnostic=diagnostic)
    require(loaded['identity_sha256'] == result['identity_sha256'], name + ': changed identity')
    require(loaded['summary'] == result['summary'], name + ': changed summary')
    for field in result['arrays']:
        np.testing.assert_array_equal(loaded['arrays'][field], result['arrays'][field])
    check_readonly(loaded['arrays'])
    if diagnostic:
        try:
            load_surface_centerline(path)
        except ValueError:
            pass
        else:
            raise AssertionError('default load accepted a diagnostic')
    else:
        first = slice_surface_centerline(loaded, slice(0, 40), slice(0, 40))
        second = slice_surface_centerline(loaded, slice(20, 61), slice(20, 61))
        for field in first['arrays']:
            np.testing.assert_array_equal(first['arrays'][field][20:40, 20:40], second['arrays'][field][:20, :20])
        check_readonly(first['arrays'])
        np.savez_compressed(destination / (name + '-window.npz'), **first['arrays'])
    return {'status': loaded['status'], 'identity_sha256': loaded['identity_sha256'], 'package': path.name, 'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'save_reload_equal': True, 'hard_readonly': True, 'summary': loaded['summary']}

def rebuild_plan(plan, discharge=None, height=None, source='verification-failure'):
    arrays = plan['arrays']
    params = plan['identity']['parameters']
    recipe = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
    return plan_channel(arrays['source_height_m'] if height is None else height, arrays['receiver'], arrays['order'], arrays['outlet_mask'], arrays['discharge_m3_s'] if discharge is None else discharge, 10.0, 10.0, 0.0, 0.0, 0.0, source, recipe)

def run(destination):
    plan = bent_plan()
    source_height = plan['arrays']['source_height_m'].copy()
    source_discharge = plan['arrays']['discharge_m3_s'].copy()
    centerline = build_centerline(plan, SmoothingRecipe(max_offset_m=10.0))
    zero = build_centerline(plan, SmoothingRecipe(strength=0.0, max_offset_m=10.0))
    smooth = prepare_case(plan, centerline)
    unmoved = prepare_case(plan, zero)
    require(smooth['summary']['moved_nodes'] > 0, 'positive has no moved nodes')
    cases = {'bent-confluence': record_case(destination, 'bent-confluence', smooth, 'prepared'), 'zero-strength': record_case(destination, 'zero-strength', unmoved, 'prepared')}
    cut = smooth['arrays']['section__actual_cut_m']
    reference_cut = unmoved['arrays']['section__actual_cut_m']
    cut_difference = cut - reference_cut
    require(np.any(cut_difference != 0), 'moved geometry has no actual fine-bed change')
    weights = np.ones(cut.shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    measured_volume = float(np.sum(cut * weights))
    measured_area = float(np.sum((cut > 1e-09) * weights))
    require(abs(measured_volume - smooth['summary']['cut_volume_m3']) < 1e-09, 'volume disagrees')
    require(measured_area == smooth['summary']['area_m2'], 'area disagrees')
    discharge = plan['arrays']['discharge_m3_s'].ravel()
    incoming = np.zeros(discharge.size)
    receiver = plan['arrays']['receiver']
    for donor, target in enumerate(receiver):
        if target >= 0:
            incoming[target] += discharge[donor]
    require(np.all(discharge - incoming >= 0), 'negative local discharge')
    require(discharge[9] == 0.1 and discharge[11] == 0.1 and (discharge[17] == 0.2), 'wrong confluence fixture flow')
    geometry = centerline['arrays']
    anchors = geometry['anchor_mask']
    np.testing.assert_array_equal(geometry['node_world_xz_m'][anchors], geometry['original_world_xz_m'][anchors])
    np.savez_compressed(destination / 'moved-fine-bed-comparison.npz', node_flat_index=geometry['node_flat_index'], original_world_xz_m=geometry['original_world_xz_m'], moved_world_xz_m=geometry['node_world_xz_m'], anchor_mask=anchors, discharge_m3_s=discharge, incoming_discharge_m3_s=incoming, local_discharge_m3_s=discharge - incoming, moved_surface_m=smooth['arrays']['section__bounded_surface_m'], zero_strength_surface_m=unmoved['arrays']['section__bounded_surface_m'], cut_difference_m=cut_difference, integration_weights=weights)
    domain = np.ones((61, 61), bool)
    domain[11, 21] = False
    protected = np.zeros((61, 61), bool)
    protected[11, 21] = True
    failures = {'domain-support': prepare_case(plan, centerline, domain=domain), 'protected-support': prepare_case(plan, centerline, protected=protected), 'no-legal-outlet': prepare_case(plan, centerline, legal=np.zeros((61, 61), bool)), 'bed-budget': prepare_case(plan, centerline, budget=SurfaceNetworkBudget(0.1, 5000.0, 5000.0)), 'area-budget': prepare_case(plan, centerline, budget=SurfaceNetworkBudget(4.0, 1.0, 5000.0)), 'volume-budget': prepare_case(plan, centerline, budget=SurfaceNetworkBudget(4.0, 5000.0, 1.0)), 'coarse-resolution': prepare_case(plan, centerline, spacing=2.0)}
    flat_height = source_height.copy()
    flat_height[1:6, 2:5] = 5.0
    failures['centerline-slope'] = prepare_case(rebuild_plan(plan, height=flat_height))
    require(failures['coarse-resolution']['summary']['needs_finer_grid'], 'missing refinement diagnostic')
    for name, result in failures.items():
        cases[name] = record_case(destination, name, result, 'diagnostic_not_publishable')
    rejection_report = {}
    bad_discharge = source_discharge.copy()
    bad_discharge.flat[[9, 11]] = 0.2
    bad_plan = rebuild_plan(plan, discharge=bad_discharge, source='nonconservative-two-sources')
    np.savez_compressed(destination / 'nonconservative-input.npz', **bad_plan['arrays'])
    try:
        prepare_case(bad_plan)
    except ValueError as error:
        rejection_report['nonconservative-discharge'] = str(error)
    else:
        raise AssertionError('nonconservative Q accepted')
    for name, mutation in (('rehashed-bed', 'bed'), ('rehashed-summary', 'summary')):
        result = deepcopy(smooth)
        if mutation == 'bed':
            result['arrays']['section__bounded_surface_m'][30, 38] += 0.1
        else:
            result['summary']['area_m2'] += 1.0
        rehash_result(result)
        path = destination / (name + '-rejected.npz')
        write_package(result, path)
        try:
            load_surface_centerline(path)
        except ValueError as error:
            rejection_report[name] = str(error)
        else:
            raise AssertionError('rehashed inconsistent payload accepted')
    np.testing.assert_array_equal(source_height, plan['arrays']['source_height_m'])
    np.testing.assert_array_equal(source_discharge, plan['arrays']['discharge_m3_s'])
    return {'verification_kind': 'implementation_verification_not_independent_acceptance', 'cases': cases, 'rejections': rejection_report, 'direct_checks': {'source_preserved': True, 'source_flow_m3_s': [float(discharge[9]), float(discharge[11])], 'confluence_flow_m3_s': float(discharge[17]), 'anchors_preserved': True, 'moved_nodes': smooth['summary']['moved_nodes'], 'changed_fine_nodes_vs_zero_strength': int(np.count_nonzero(cut_difference)), 'max_abs_cut_difference_m': float(np.max(np.abs(cut_difference))), 'weighted_area_m2': measured_area, 'weighted_cut_volume_m3': measured_volume}, 'limits': 'synthetic fixed geometry, static stage, same fine-grid slices; no naturalness/game acceptance'}

def main():
    utc = datetime.now(timezone.utc)
    destination = ROOT / 'verification/surface-centerline-prepare' / utc.strftime('run-%Y%m%dT%H%M%S%fZ')
    destination.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': utc.isoformat(), 'output_directory': str(destination), 'status': 'failed'}
    try:
        report.update(run(destination))
        report['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / 'terrain_pipeline/surface_domain.py', ROOT / 'tests/test_surface_domain.py', Path(__file__))}
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (destination / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps({'status': report['status'], 'output_directory': str(destination)}, ensure_ascii=False))
if __name__ == '__main__':
    main()
