"""Consolidated prepare_hybrid_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import replace
from dataclasses import asdict as _i0_asdict
import argparse as _i0_argparse
import hashlib as _i0_hashlib
import json as _i0_json
from pathlib import Path as _i0_Path
import tempfile as _i0_tempfile
from terrain_pipeline.hybrid_geometry import FilePin as _i0_FilePin
from terrain_pipeline.hybrid_geometry import MAX_FILE_BYTES as _i0_MAX_FILE_BYTES
from terrain_pipeline.hybrid_geometry import build_graph as _i0_build_graph
from terrain_pipeline.hybrid_geometry import canonical_json as _i0_canonical_json
from terrain_pipeline.hybrid_geometry import identity as _i0_identity
from terrain_pipeline.hybrid_geometry import load_graph as _i0_load_graph
from terrain_pipeline.hybrid_geometry import native_bed_pieces as _i0_native_bed_pieces
from terrain_pipeline.hybrid_geometry import read_pinned as _i0_read_pinned
from terrain_pipeline.hybrid_hydraulics import common_Experiment as _i0_Experiment
from dataclasses import asdict as _i1_asdict
import argparse as _i1_argparse
import json as _i1_json
from pathlib import Path as _i1_Path
import sys as _i1_sys
import time as _i1_time
from terrain_pipeline.hybrid_geometry import MAX_FILE_BYTES as _i1_MAX_FILE_BYTES
from terrain_pipeline.hybrid_geometry import identity as _i1_identity
from terrain_pipeline.hybrid_geometry import read_pinned as _i1_read_pinned
from terrain_pipeline.hybrid_hydraulics import common_Experiment as _i1_Experiment
from terrain_pipeline.hybrid_hydraulics import common_compare_refinement as _i1_compare_refinement
from terrain_pipeline.hybrid_hydraulics import LOCAL_FRAME_INTEGRATION as _i1_INTEGRATION
from terrain_pipeline.hybrid_hydraulics import MODEL_VERSION as _i1_MODEL_VERSION
from terrain_pipeline.hybrid_hydraulics import LOCAL_FRAME_NUMERICAL_VERSION as _i1_NUMERICAL_VERSION
from terrain_pipeline.hybrid_hydraulics import inventory_policy as _i1_inventory_policy
from terrain_pipeline.hybrid_hydraulics import jacobian_policy as _i1_jacobian_policy
from terrain_pipeline.hybrid_hydraulics import local_model as _i1_local_model
from terrain_pipeline.hybrid_hydraulics import numerical_frame as _i1_numerical_frame
from terrain_pipeline.hybrid_hydraulics import local_frame_run_experiment as _i1_run_experiment
from builtins import ValueError as _i1_HydraulicDiagnosticStop
from builtins import ValueError as _i1_HydraulicExecutionFailure
from terrain_pipeline.hybrid_hydraulics import HYBRID_RIVER_SECTIONS_MECHANISM_2_SCHEMA as _i1_SECTION_SCHEMA
from tools.hybrid_hydraulics_records import file_sha as _x0_file_sha
from tools.hybrid_hydraulics_records import pin as _x1_pin
from tools.hybrid_hydraulics_records import saved_pin as _x2_saved_pin
from tools.hybrid_hydraulics_records import check_original_pins as _x3_check_original_pins
from tools.hybrid_hydraulics_records import validate_geometry as _x4_validate_geometry
from tools.hybrid_hydraulics_records import file_sha as _x5_file_sha
from tools.hybrid_hydraulics_records import pin as _x6_pin
from tools.hybrid_hydraulics_records import validate_geometry as _x7_validate_geometry
from tools.hybrid_hydraulics_records import atomic_save as _x8_atomic_save
from tools.hybrid_hydraulics_records import meaningful_evidence as _x9_meaningful_evidence
from tools.hybrid_hydraulics_records import paired_refinement as _x10_paired_refinement
from tools.hybrid_hydraulics_records import physical_model_identity as _x11_physical_model_identity
from tools.hybrid_hydraulics_records import precision_experiments as _x12_precision_experiments
from tools.hybrid_hydraulics_records import accuracy_policy as _x13_accuracy_policy
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _x14_HydraulicsLegacyReplay
from tools.frozen_hybrid_hydraulics import SOURCE_ROOT as _x15_SOURCE_ROOT
CATEGORY = 'C'
ROOT = _i0_Path(__file__).resolve().parents[1]
SURFACE_INDEX_SHA = 'd4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68'
SURFACE_AUDIT_SHA = '54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5'
CODE_FILES = ('terrain_pipeline/hybrid_geometry.py', 'terrain_pipeline/hybrid_hydraulics.py', 'tools/prepare_hybrid_hydraulics.py', 'tests/test_hybrid_geometry.py')

def prepare_graph(args):
    index_pin, audit_pin = (_x1_pin(args.surface_index, args.surface_index_sha256), _x1_pin(args.surface_audit, args.surface_audit_sha256))
    if index_pin.sha256 != SURFACE_INDEX_SHA or audit_pin.sha256 != SURFACE_AUDIT_SHA:
        raise ValueError('only the frozen actual passed task14 package is authorized')
    index, audit = (_i0_read_pinned(index_pin), _i0_read_pinned(audit_pin))
    if audit['index_sha256'] != index_pin.sha256 or audit.get('errors') or audit['inputs'] != index['inputs']:
        raise ValueError('surface passed audit/index binding mismatch')
    artifacts, bindings = ({}, {'surface_index': index_pin, 'surface_audit': audit_pin})
    for key in ('graph', 'manifest', 'topology', 'selection', 'mesh'):
        artifact_pin = _x2_saved_pin(index[key])
        if audit[key + '_sha256'] != artifact_pin.sha256:
            raise ValueError('surface artifact audit binding mismatch')
        artifacts[key] = _i0_read_pinned(artifact_pin)
        bindings['surface_' + key] = artifact_pin
    _x3_check_original_pins(index['inputs'])
    bindings.update((('original_' + key, _x2_saved_pin(record)) for key, record in index['inputs'].items()))
    for name, sha in index['code_sha256'].items():
        if _x0_file_sha(ROOT / name) != sha:
            raise ValueError('frozen parent code changed: ' + name)
    fine_index_pin, fine_audit_pin = (_x1_pin(args.fine_index, args.fine_index_sha256), _x1_pin(args.fine_audit, args.fine_audit_sha256))
    fine_index, fine_audit = (_i0_read_pinned(fine_index_pin), _i0_read_pinned(fine_audit_pin))
    if fine_audit['status'] != 'passed' or fine_audit.get('errors') or fine_audit['index_sha256'] != fine_index_pin.sha256:
        raise ValueError('fine input is not independently passed and bound')
    channel = fine_index['channel']
    if fine_audit['channel'] != channel:
        raise ValueError('fine independent audit original channel bindings differ')
    if channel['index']['sha256'] != index_pin.sha256 or channel['audit']['sha256'] != audit_pin.sha256:
        raise ValueError('fine package belongs to another surface package')
    bindings.update(fine_index=fine_index_pin, fine_audit=fine_audit_pin)
    for key in ('manifest', 'compact_fans', 'material'):
        artifact_pin = _x2_saved_pin(fine_index[key])
        if fine_audit[key + '_sha256'] != artifact_pin.sha256:
            raise ValueError('fine artifact differs from passed audit')
        _i0_read_pinned(artifact_pin)
        bindings['fine_' + key] = artifact_pin
    ports = {}
    for row in artifacts['manifest']['ports']:
        if row['arc_id'] in (args.sink_arc, args.spring_arc):
            port_pin = _x2_saved_pin(row['pin'])
            witness = audit['ports'][row['arc_id']]
            if witness['sha256'] != port_pin.sha256 or witness['path'] != port_pin.path:
                raise ValueError('chosen canonical port file is not the audited witness')
            ports[row['arc_id']] = _i0_read_pinned(port_pin)
            bindings['portal_' + row['arc_id']] = port_pin
    saved_nodes = {}
    for row in artifacts['manifest']['nodes']:
        if row['node_id'] not in artifacts['manifest']['selected_node_ids']:
            continue
        node_pin = _x2_saved_pin(row['pin'])
        witness = audit['nodes'][row['node_id']]
        if witness['sha256'] != node_pin.sha256 or witness['path'] != node_pin.path:
            raise ValueError('surface half-arm/bed node is not the audited file')
        saved_nodes[row['node_id']] = _i0_read_pinned(node_pin)
        bindings['accepted_node_' + row['node_id']] = node_pin
    graph = _i0_build_graph(artifacts['graph'], artifacts['manifest'], artifacts['topology'], audit, ports, bindings, args.sink_arc, args.spring_arc, saved_nodes)
    return {'graph.json': graph.to_record()}

def prepare_experiments(args):
    graph_pin, geometry_pin, geometry_audit_pin = (_x1_pin(args.graph, args.graph_sha256), _x1_pin(args.geometry, args.geometry_sha256), _x1_pin(args.geometry_audit, args.geometry_audit_sha256))
    graph_record = _i0_read_pinned(graph_pin)
    model, geometry = _x4_validate_geometry(graph_record, geometry_pin, geometry_audit_pin)
    if not 0 < args.initial_depth_m <= 0.25 or not 0 < args.pulse_tailwater_depth_m <= 0.25 or args.observation_interval_s <= 0:
        raise ValueError('explicit bounded prewet depth/tailwater depth/observation interval required')
    heads = tuple((cell.section.floor_m + args.initial_depth_m for cell in model.cells))
    if any((cell.kind == 'underground' and head >= cell.section.crown_m for cell, head in zip(model.cells, heads))):
        raise ValueError('requested prewet depth exceeds an actual conduit crown')
    import numpy as np
    count = int(np.ceil(args.duration_s / args.observation_interval_s))
    if not 1 <= count <= 4095:
        raise ValueError('physical observations exceed bounded count')
    times = tuple((float(value) for value in np.linspace(0, args.duration_s, count + 1)))
    pulse = _i0_Experiment('pulse', args.duration_s, args.pulse_duration_s, args.pulse_q_m3_s, model.cells[-1].section.floor_m + args.pulse_tailwater_depth_m, heads, times, max_step_s=args.max_step_s)
    reverse = replace(pulse, scenario='reverse_tailwater', pulse_duration_s=0, pulse_q_m3_s=0, tailwater_head_m=args.reverse_tailwater_head_m)
    if reverse.tailwater_head_m <= max(heads):
        raise ValueError('reverse engineering head must exceed the complete route initial heads')
    pulse.validate(model)
    reverse.validate(model)
    configuration = {'schema': 'td-hybrid-river-engineering-experiments-v1', 'status': 'engineering_configuration_only_not_solver_result', 'inputs': {'graph': _i0_asdict(graph_pin), 'geometry': _i0_asdict(geometry_pin), 'geometry_audit': _i0_asdict(geometry_audit_pin)}, 'graph_identity_sha256': graph_record['identity_sha256'], 'geometry_identity_sha256': geometry['identity_sha256'], 'initial_water_semantics': 'explicit_untraced_engineering_prewet_not_hidden_source', 'scenarios': [_i0_asdict(pulse), _i0_asdict(reverse)], 'natural_outlet_certified': False, 'refinement_tolerances': {'volume_absolute_tolerance_m3': 0.0001, 'head_absolute_tolerance_m': 0.001, 'volume_relative_tolerance': 0.01}}
    configuration['identity_sha256'] = _i0_identity(configuration)
    return {'experiments.json': configuration, 'index.json': {'schema': 'td-hybrid-river-engineering-configuration-preparation-v1', 'status': 'engineering_configuration_only_not_solver_result'}}

def publish(output, records):
    output = _i0_Path(output).resolve()
    if output.exists():
        raise ValueError('new output directory required; no frozen output overwrite')
    if output.parent != ROOT / 'verification' / 'natural-river-network':
        raise ValueError('new top-level verification package required; frozen package subdirectories cannot be modified')
    output.parent.mkdir(parents=True, exist_ok=True)
    with _i0_tempfile.TemporaryDirectory(prefix='.hybrid-', dir=output.parent) as temporary:
        staging = _i0_Path(temporary) / 'publish'
        staging.mkdir()
        artifacts = {}
        for name, record in records.items():
            if name == 'index.json':
                continue
            payload = _i0_canonical_json(record).encode('utf-8')
            if len(payload) > _i0_MAX_FILE_BYTES:
                raise ValueError('bounded artifact file exceeded')
            (staging / name).write_bytes(payload)
            artifacts[name] = {'path': str(output / name), 'sha256': _i0_hashlib.sha256(payload).hexdigest(), 'identity_sha256': record['identity_sha256']}
        index = dict(records.get('index.json', {'schema': 'td-hybrid-river-graph-preparation-v1', 'status': 'candidate_geometry_pending', 'full_network_verified': False}))
        index['artifacts'] = artifacts
        index['code_sha256'] = {name: _x0_file_sha(ROOT / name) for name in CODE_FILES}
        index['identity_sha256'] = _i0_identity(index)
        payload = _i0_canonical_json(index).encode('utf-8')
        if len(payload) > _i0_MAX_FILE_BYTES:
            raise ValueError('bounded index file exceeded')
        (staging / 'index.json').write_bytes(payload)
        staging.rename(output)
    return index

def _entry_prepare_hybrid_river_hydraulics():
    parser = _i0_argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    graph_parser = subparsers.add_parser('graph', help='prepare immutable graph only; no solver')
    graph_parser.add_argument('--surface-index', required=True, type=_i0_Path)
    graph_parser.add_argument('--surface-index-sha256', default=SURFACE_INDEX_SHA)
    graph_parser.add_argument('--surface-audit', required=True, type=_i0_Path)
    graph_parser.add_argument('--surface-audit-sha256', default=SURFACE_AUDIT_SHA)
    for name in ('fine-index', 'fine-audit'):
        graph_parser.add_argument('--' + name, required=True, type=_i0_Path)
        graph_parser.add_argument('--' + name + '-sha256', required=True)
    graph_parser.add_argument('--sink-arc', required=True)
    graph_parser.add_argument('--spring-arc', required=True)
    experiment_parser = subparsers.add_parser('experiments', help='prepare engineering forcing from audited actual sections; no solver')
    for name in ('graph', 'geometry', 'geometry-audit'):
        experiment_parser.add_argument('--' + name, required=True, type=_i0_Path)
        experiment_parser.add_argument('--' + name + '-sha256', required=True)
    for name in ('duration-s', 'pulse-duration-s', 'pulse-q-m3-s', 'reverse-tailwater-head-m'):
        experiment_parser.add_argument('--' + name, required=True, type=float)
    experiment_parser.add_argument('--initial-depth-m', type=float, default=0.05)
    experiment_parser.add_argument('--pulse-tailwater-depth-m', type=float, default=0.03)
    experiment_parser.add_argument('--observation-interval-s', type=float, default=5)
    experiment_parser.add_argument('--max-step-s', type=float, default=2)
    for command in (graph_parser, experiment_parser):
        command.add_argument('--output', required=True, type=_i0_Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('new output directory required')
    records = {'graph': prepare_graph, 'experiments': prepare_experiments}[args.command](args)
    result = publish(args.output, records)
    print(_i0_json.dumps({'status': result['status'], 'identity_sha256': result['identity_sha256'], 'summary': result.get('summary')}))
DATA_ROOT = ROOT
SCHEMA = 'td-hybrid-river-hydraulics-preparation-v8'
NEW_CODE = ('terrain_pipeline/hybrid_geometry.py', 'terrain_pipeline/hybrid_hydraulics.py', 'tools/hybrid_hydraulics_records.py', 'tools/frozen_hybrid_hydraulics.py', 'tools/prepare_hybrid_hydraulics.py', 'tests/test_hybrid_hydraulics.py')

def source_identity():
    """Current executed sources and historical reference pins are different identities."""
    replay = _x14_HydraulicsLegacyReplay()
    historical = {name: record['sha256'] for name, record in replay.manifest['files'].items()}
    current = {name: _x5_file_sha(DATA_ROOT / name) for name in NEW_CODE}
    return (current, historical)

def accuracy_policy():
    return {**_x13_accuracy_policy(), 'schema': 'td-hybrid-river-accuracy-policy-v8', 'integration': _i1_INTEGRATION}

def prepare(args):
    code, historical_code = source_identity()
    pins = {name: _x6_pin(getattr(args, name), getattr(args, name + '_sha256')) for name in ('graph', 'geometry', 'geometry_audit', 'experiments')}
    inputs = {name: _i1_asdict(value) for name, value in pins.items()}
    graph = _i1_read_pinned(pins['graph'])
    model, geometry = _x7_validate_geometry(graph, pins['geometry'], pins['geometry_audit'])
    configuration = _i1_read_pinned(pins['experiments'])
    unsigned = dict(configuration)
    expected = unsigned.pop('identity_sha256')
    if configuration['schema'] != 'td-hybrid-river-engineering-experiments-v1' or _i1_identity(unsigned) != expected:
        raise ValueError('engineering configuration identity/schema mismatch')
    if configuration['graph_identity_sha256'] != graph['identity_sha256'] or configuration['geometry_identity_sha256'] != geometry['identity_sha256'] or configuration['inputs'] != {name: inputs[name] for name in ('graph', 'geometry', 'geometry_audit')}:
        raise ValueError('engineering configuration geometry/graph binding mismatch')
    scenarios = configuration['scenarios']
    if len(scenarios) != 2 or {item['scenario'] for item in scenarios} != {'pulse', 'reverse_tailwater'}:
        raise ValueError('exactly the original two events required')
    tolerances = configuration.get('refinement_tolerances', {})
    limits = {'volume_absolute_tolerance_m3': 0.0001, 'head_absolute_tolerance_m': 0.001, 'volume_relative_tolerance': 0.01}
    if any((tolerances.get(key, maximum) > maximum for key, maximum in limits.items())):
        raise ValueError('refinement gates cannot be relaxed')
    experiments, parameter_ids = ([], {})
    for item in scenarios:
        original = _i1_Experiment(**{**item, 'initial_heads_m': tuple(item['initial_heads_m']), 'saved_times_s': tuple(item['saved_times_s'])})
        original.validate(model)
        pair = _x12_precision_experiments(original)
        for experiment in pair:
            experiment.validate(model)
        experiments.append(pair)
        parameter_ids[original.scenario] = _i1_identity(_i1_asdict(original))
    from terrain_pipeline.hybrid_hydraulics import validate_transition
    validate_transition(args.crown_friction_transition_m)
    if args.crown_friction_transition_m <= 0:
        raise ValueError('v8 requires the explicitly pinned roof-friction model')
    frame = _i1_numerical_frame(model)
    model_record = {'schema': 'td-hybrid-river-hydraulic-model-parameters-v8', 'model_version': _i1_MODEL_VERSION, 'numerical_version': _i1_NUMERICAL_VERSION, 'integration': _i1_INTEGRATION, 'inventory_policy': _i1_inventory_policy(), 'accuracy_policy': accuracy_policy(), 'numerical_frame': frame, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'friction_policy': {'width_m': args.crown_friction_transition_m, 'transition_start': 'crown', 'transition_end': 'crown+width_m', 'actual_perimeter_unchanged': True, 'storage_area_unchanged': True, 'pressure_slot_width_unchanged': True, 'roof_length_source': 'sum_actual_polygon_edges_with_both_endpoints_at_crown', 'constitutive_kind': 'C1_effective_roof_contact_friction', 'contact_polynomial': 'u*u*(3-2*u)_for_0<=u<=1'}, 'jacobian_policy': _i1_jacobian_policy(_i1_local_model(model, frame), args.crown_friction_transition_m), 'forcing_configuration_pin': inputs['experiments'], 'code_sha256': code, 'graph_identity_sha256': graph['identity_sha256'], 'geometry_identity_sha256': geometry['identity_sha256']}
    model_record['source_layout'] = 'explicit_common_radau_v8_20261023'
    model_record['frozen_reference_code_sha256'] = historical_code
    model_record['physical_model_identity_sha256'] = _x11_physical_model_identity(model_record)
    output = args.output.resolve()
    if output.exists() or output.parent not in (ROOT / 'verification/natural-river-network', ROOT / 'verification/hybrid-river-network'):
        raise ValueError('new verification directory required; no resume/reuse')
    output.mkdir(parents=True)
    model_pin = _x8_atomic_save(output, 'hydraulic-model.json', model_record)
    started = _i1_time.monotonic()
    checkpoint = {'schema': SCHEMA, 'status': 'running_partial', 'inputs': inputs, 'code_sha256': code, 'model_version': _i1_MODEL_VERSION, 'numerical_version': _i1_NUMERICAL_VERSION, 'integration': _i1_INTEGRATION, 'numerical_frame': frame, 'accuracy_policy': accuracy_policy(), 'section_adapter_schema': _i1_SECTION_SCHEMA, 'hydraulic_model_parameters': model_pin, 'physical_model_identity_sha256': _x11_physical_model_identity(model_record), 'graph_identity_sha256': graph['identity_sha256'], 'geometry_identity_sha256': geometry['identity_sha256'], 'friction_policy': model_record['friction_policy'], 'jacobian_policy': model_record['jacobian_policy'], 'input_parameter_identities': parameter_ids, 'completed_cases': [], 'generated_cases': [], 'artifacts': {}, 'summary': [], 'reused_cases': {}, 'case_provenance': {}, 'diagnostic_stop_s': args.diagnostic_stop_s, 'diagnostic_artifacts': {}, 'independent_audit_passed': False, 'natural_outlet_certified': False, 'full_network_verified': False, 'three_dimensional_flow_solved': False, 'work': {'new_1d_rhs_evaluations': 0, 'new_1d_link_evaluations': 0, 'old_hll_face_work': 0, 'old_hll_face_budget_remaining_unchanged': 2949448968}, 'resource': {'max_json_bytes': _i1_MAX_FILE_BYTES, 'max_rss_bytes': 1024 ** 3, 'wall_guard_seconds_per_case_unchanged': 600, 'whole_event_not_split_or_restarted': False, 'one_complete_forcing_event_budget_no_work_or_wall_reset': True, 'observation_times_reinitialize_Radau': True, 'negative_inventory_rollback_reinitializes_Radau_with_same_event_budget': True}, 'checkpoint_semantics': 'each complete case atomic; failure never accepted; no automatic resume'}

    def save_checkpoint():
        checkpoint['resource']['elapsed_wall_seconds'] = _i1_time.monotonic() - started
        _x8_atomic_save(output, 'checkpoint.json', checkpoint)
        _x8_atomic_save(output, 'index.json', checkpoint)
    checkpoint['source_layout'] = model_record['source_layout']
    checkpoint['frozen_reference_code_sha256'] = historical_code
    active_case = None
    save_checkpoint()
    try:
        for pair in experiments:
            completed = []
            for label, parameters in zip(('base', 'refined'), pair):
                active_case = parameters.scenario + '-' + label
                print(_i1_json.dumps({'case': active_case, 'status': 'started'}), flush=True)
                result = _i1_run_experiment(model, parameters, args.crown_friction_transition_m, args.diagnostic_stop_s)
                result.update(inputs=inputs, parameters=_i1_asdict(parameters), parameters_identity_sha256=_i1_identity(_i1_asdict(parameters)), local_solver_parameters_identity_sha256=_i1_identity(result['local_solver_parameters']), graph_identity_sha256=graph['identity_sha256'], geometry_identity_sha256=geometry['identity_sha256'], code_sha256=code, section_adapter_schema=_i1_SECTION_SCHEMA, meaningful_evidence=_x9_meaningful_evidence(result), accuracy_policy=accuracy_policy(), accuracy_level=label, input_parameters_identity_sha256=parameter_ids[parameters.scenario], physical_model_identity_sha256=_x11_physical_model_identity(model_record), hydraulic_model_parameters=model_pin, hydraulic_model_parameters_identity_sha256=model_pin['identity_sha256'])
                name = active_case + '.json'
                result_pin = _x8_atomic_save(output, name, result)
                checkpoint['artifacts'][name] = result_pin
                checkpoint['completed_cases'].append(active_case)
                checkpoint['generated_cases'].append(active_case)
                checkpoint['case_provenance'][active_case] = {'source_result_pin': result_pin, 'source_model_pin': model_pin, 'code_sha256': code, 'numerical_version': _i1_NUMERICAL_VERSION, 'physical_model_identity_sha256': _x11_physical_model_identity(model_record), 'reused': False}
                for key, source in (('new_1d_rhs_evaluations', 'rhs_evaluations'), ('new_1d_link_evaluations', 'link_evaluations')):
                    checkpoint['work'][key] += result['work'][source]
                save_checkpoint()
                print(_i1_json.dumps({'case': active_case, 'status': 'checkpoint_saved', 'pin': result_pin}), flush=True)
                completed.append(result)
            comparison = _i1_compare_refinement(*completed, **tolerances)
            comparison['scope'] = 'Radau_solver_parameter_refinement_of_full_saved_inventory_and_flux_history_not_wave_speed'
            paired = _x10_paired_refinement(*completed)
            evidence = completed[1]['meaningful_evidence']
            status = 'diagnostic_accepted' if comparison['status'] == paired['status'] == 'passed' and evidence['passed'] else 'refused_diagnostic_evidence'
            checkpoint['summary'].append({'scenario': pair[0].scenario, 'status': status, 'refinement': comparison, 'paired_link_refinement': paired, 'meaningful_evidence': evidence})
            save_checkpoint()
        checkpoint['status'] = 'diagnostic_accepted' if all((item['status'] == 'diagnostic_accepted' for item in checkpoint['summary'])) else 'refused_diagnostic_evidence'
        save_checkpoint()
    except Exception as error:
        stopped = isinstance(error, _i1_HydraulicDiagnosticStop)
        checkpoint['status'] = 'diagnostic_stopped' if stopped else 'failed_partial'
        checkpoint['failure'] = {'case': active_case, 'exception_type': type(error).__name__, 'message': str(error), 'failed_case_not_saved': True}
        if isinstance(error, _i1_HydraulicExecutionFailure):
            checkpoint['failure']['progress'] = error.progress
            for key, source in (('new_1d_rhs_evaluations', 'rhs_evaluations'), ('new_1d_link_evaluations', 'link_evaluations')):
                checkpoint['work'][key] += error.progress['work'][source]
            checkpoint['resource']['actual_peak_rss_bytes'] = error.progress['actual_peak_rss_bytes']
        save_checkpoint()
        if not stopped:
            raise
    return checkpoint

def _entry_prepare_hybrid_river_hydraulics_v8():
    parser = _i1_argparse.ArgumentParser(description=__doc__)
    for name in ('graph', 'geometry', 'geometry-audit', 'experiments'):
        parser.add_argument('--' + name, required=True, type=_i1_Path)
        parser.add_argument('--' + name + '-sha256', required=True)
    parser.add_argument('--output', required=True, type=_i1_Path)
    parser.add_argument('--diagnostic-stop-s', type=float)
    parser.add_argument('--crown-friction-transition-m', type=float, default=0.02)
    result = prepare(parser.parse_args())
    print(_i1_json.dumps({'status': result['status'], 'completed_cases': result['completed_cases'], 'summary': result['summary']}))

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'graph': '_entry_prepare_hybrid_river_hydraulics', 'solve': '_entry_prepare_hybrid_river_hydraulics_v8', 'experiments': '_entry_prepare_hybrid_river_hydraulics'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('command', choices=tuple(commands))
        parsed, values = parser.parse_known_args(values)
        selected = parsed.command
    if selected in ('graph', 'experiments'):
        values.insert(0, selected)
    function = globals()[commands[selected]]
    previous = sys.argv
    try:
        sys.argv = [previous[0]] + values
        return function(values) if inspect.signature(function).parameters else function()
    finally:
        sys.argv = previous
if __name__ == '__main__':
    main()
