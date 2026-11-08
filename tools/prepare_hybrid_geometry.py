"""Consolidated prepare_hybrid_geometry implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i8_argparse
from importlib.metadata import version as _i8_version
import json as _i8_json
from pathlib import Path as _i8_Path
import time as _i8_time
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i8_MAX_BYTES
from terrain_pipeline.hybrid_geometry import guard as _i8_guard
from terrain_pipeline.hybrid_geometry import seal as _i8_seal
from terrain_pipeline.hybrid_geometry import HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256 as _i8_NUMERICAL_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import hybrid_river_faces_mechanism_2_build_faces as _i8_build_faces
from terrain_pipeline.hybrid_geometry import build_boolean_stage as _i8_build_boolean_stage
from terrain_pipeline.hybrid_geometry import resume_composition as _i8_resume_composition
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_PRISMS_POLICY as _i8_GEOMETRIC_POLICY
from terrain_pipeline.hybrid_geometry import identity as _i8_identity
import argparse as _i9_argparse
from dataclasses import asdict as _i9_asdict
import hashlib as _i9_hashlib
import json as _i9_json
from pathlib import Path as _i9_Path
import sys as _i9_sys
import time as _i9_time
from terrain_pipeline.hybrid_geometry import BedSampler as _i9_BedSampler
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i9_MAX_BYTES
from terrain_pipeline.hybrid_geometry import POLICY_SHA256 as _i9_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import Parameters as _i9_Parameters
from terrain_pipeline.hybrid_geometry import build_geometry as _i9_build_geometry
from terrain_pipeline.hybrid_geometry import hybrid_cave_geometry_guard as _i9_guard
from terrain_pipeline.hybrid_geometry import seal as _i9_seal
from terrain_pipeline.hybrid_geometry import FilePin as _i9_FilePin
from terrain_pipeline.hybrid_geometry import identity as _i9_identity
from terrain_pipeline.hybrid_geometry import load_graph as _i9_load_graph
from terrain_pipeline.hybrid_geometry import read_pinned as _i9_read_pinned
from terrain_pipeline.basin_topology import load_basin_hierarchy as _i9_load_basin_hierarchy
from terrain_pipeline import channel_geometry as _i9_source
import argparse as _i10_argparse
import hashlib as _i10_hashlib
import json as _i10_json
from pathlib import Path as _i10_Path
import sys as _i10_sys
import tempfile as _i10_tempfile
import time as _i10_time
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i10_MAX_BYTES
from terrain_pipeline.hybrid_geometry import MAX_RSS as _i10_MAX_RSS
from terrain_pipeline.hybrid_geometry import HYBRID_RIVER_FACES_POLICY_SHA256 as _i10_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import build_faces as _i10_build_faces
from terrain_pipeline.hybrid_geometry import guard as _i10_guard
from terrain_pipeline.hybrid_geometry import seal as _i10_seal
from terrain_pipeline.hybrid_geometry import identity as _i10_identity
from terrain_pipeline.hybrid_geometry import load_graph as _i10_load_graph
import argparse as _i11_argparse
import hashlib as _i11_hashlib
from importlib.metadata import version as _i11_version
import json as _i11_json
from pathlib import Path as _i11_Path
import sys as _i11_sys
import tempfile as _i11_tempfile
import time as _i11_time
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i11_MAX_BYTES
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_COMPOSITION_POLICY_SHA256 as _i11_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import build_composition as _i11_build_composition
from terrain_pipeline.hybrid_geometry import MAX_RSS as _i11_MAX_RSS
from terrain_pipeline.hybrid_geometry import guard as _i11_guard
from terrain_pipeline.hybrid_geometry import seal as _i11_seal
import argparse as _i12_argparse
from importlib.metadata import version as _i12_version
import json as _i12_json
from pathlib import Path as _i12_Path
import sys as _i12_sys
import tempfile as _i12_tempfile
import time as _i12_time
from terrain_pipeline.hybrid_geometry import NUMERICAL_POLICY as _i12_NUMERICAL_POLICY
from terrain_pipeline.hybrid_geometry import NUMERICAL_POLICY_SHA256 as _i12_NUMERICAL_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i12_MAX_BYTES
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY_SHA256 as _i12_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_COMPOSITION_MECHANISM_2_SCHEMA as _i12_SCHEMA
from terrain_pipeline.hybrid_geometry import hybrid_surface_composition_mechanism_2_build_composition as _i12_build_composition
from terrain_pipeline.hybrid_geometry import MAX_RSS as _i12_MAX_RSS
from terrain_pipeline.hybrid_geometry import guard as _i12_guard
from terrain_pipeline.hybrid_geometry import seal as _i12_seal
import argparse as _i13_argparse
from importlib.metadata import version as _i13_version
import json as _i13_json
from pathlib import Path as _i13_Path
import sys as _i13_sys
import tempfile as _i13_tempfile
import time as _i13_time
from terrain_pipeline.hybrid_geometry import HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY as _i13_NUMERICAL_POLICY
from terrain_pipeline.hybrid_geometry import HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256 as _i13_NUMERICAL_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY as _i13_POLICY
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY_SHA256 as _i13_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_COMPOSITION_MECHANISM_3_SCHEMA as _i13_SCHEMA
from terrain_pipeline.hybrid_geometry import resume_composition as _i13_resume_composition
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i13_MAX_BYTES
from terrain_pipeline.hybrid_geometry import MAX_RSS as _i13_MAX_RSS
from terrain_pipeline.hybrid_geometry import guard as _i13_guard
from terrain_pipeline.hybrid_geometry import seal as _i13_seal
from tools.hybrid_geometry_records import ROOT as _x17_ROOT
from tools.hybrid_geometry_records import GEOMETRY as _x18_GEOMETRY
from tools.hybrid_geometry_records import AUDIT as _x19_AUDIT
from tools.hybrid_geometry_records import GEOMETRY_SHA as _x20_GEOMETRY_SHA
from tools.hybrid_geometry_records import AUDIT_SHA as _x21_AUDIT_SHA
from tools.hybrid_geometry_records import file_sha as _x22_file_sha
from tools.hybrid_geometry_records import load_inputs as _x23_load_inputs
from tools.hybrid_geometry_records import read as _x24_read
from tools.hybrid_geometry_records import save as _x25_save
from tools.hybrid_geometry_records import CURRENT_GENERATOR_FILES as _x26_CURRENT_GENERATOR_FILES
CATEGORY = 'C'
SCHEMA = 'td-hybrid-current-composition-v1'
POLICY = {**_i8_GEOMETRIC_POLICY, 'version': 'original-Boolean-plus-rational-port-integration-v1', 'main_boolean': 'fresh-original-fixed-geometry-Boolean-stage-preserved-before-port-checks', 'numerical_slice': _i8_NUMERICAL_POLICY_SHA256, 'portal_boolean': 'original-bounded-collars-no-added-excavation', 'integration_only_no_new_physical_law': True}
POLICY_SHA256 = _i8_identity(POLICY)
CURRENT_FILES = _x26_CURRENT_GENERATOR_FILES

def prepare(output, geometry_pin=None, geometry_audit_pin=None, progress=print):
    from tools.audit_hybrid_geometry import audit_composition as audit_composition
    from tools.audit_hybrid_geometry import audit_faces as audit_faces
    if _i8_version('manifold3d') != '3.5.4':
        raise ValueError('fixed manifold3d 3.5.4 required')
    output = _i8_Path(output).resolve()
    if output.exists() or not output.is_relative_to(_x17_ROOT / '.scratch'):
        raise ValueError('new current integration output under workspace .scratch required')
    geometry_pin = geometry_pin or {'path': str(_x18_GEOMETRY), 'sha256': _x20_GEOMETRY_SHA}
    geometry_audit_pin = geometry_audit_pin or {'path': str(_x19_AUDIT), 'sha256': _x21_AUDIT_SHA}
    geometry, vdm, attachments, ports, original = _x23_load_inputs(geometry_pin, geometry_audit_pin)
    if len(vdm['stations']) != 17 or len(geometry['hydraulic_links']) != 18:
        raise ValueError('current geometry integration remains fixed 17 stations / 18 links')
    nodes = {kind: _x24_read(value['surface_node_pin']) for kind, value in attachments['attachments'].items()}
    sampling = _x24_read(geometry['source_sampling_pin'])
    inputs = {'geometry': geometry_pin, 'geometry_audit': geometry_audit_pin, 'graph': geometry['inputs']['graph'], 'mesh_pins': geometry['mesh_pins'], 'vdm': geometry['vdm_pin'], 'surface_attachments': geometry['surface_attachments_pin'], 'surface_nodes': {kind: value['surface_node_pin'] for kind, value in attachments['attachments'].items()}, 'original_source_sampling': geometry['source_sampling_pin']}
    code = {name: _x22_file_sha(_x17_ROOT / name) for name in CURRENT_FILES}
    output.mkdir(parents=True)
    started = _i8_time.monotonic()
    index = {'schema': 'td-hybrid-current-integration-index-v1', 'status': 'preparing', 'inputs': inputs, 'code_sha256': code, 'code_source_context': 'current', 'hydraulic_ready': False, 'publishable': False, 'stages_completed': []}

    def persist(name, record):
        return _x25_save(output / (name + '.json'), _i8_seal(record), output / (name + '.json'))
    try:
        progress('current: original main Boolean stage')
        stage, artifacts = _i8_build_boolean_stage(geometry, vdm, attachments, ports, original, nodes, sampling)
        main_pins = {name: persist(name, record) for name, record in artifacts.items()}
        checkpoint = persist('checkpoint_boolean', {'schema': 'td-hybrid-current-boolean-checkpoint-v1', 'status': 'boolean_stage_unverified', 'portal_checks_started': False, 'composition_stage': stage, 'inputs': inputs, 'artifacts': main_pins, 'code_sha256': code, 'code_source_context': 'current'})
        stage_index = persist('boolean-stage-index', {'schema': 'td-hybrid-current-boolean-index-v1', 'status': 'boolean_stage_unverified', 'inputs': inputs, 'artifacts': main_pins, 'checkpoint': checkpoint, 'code_sha256': code, 'code_source_context': 'current'})
        index.update(boolean_checkpoint=checkpoint, boolean_index=stage_index)
        index['stages_completed'].append('fresh-main-Boolean-saved')
        progress('current: latest rational portal integration')
        lineage = {'mode': 'fresh-original-boolean-then-rational-port', 'source_index_pin': stage_index, 'checkpoint_pin': checkpoint, 'main_boolean_recomputed': True}
        current_meshes = {name: record for name, record in artifacts.items() if name != 'surface_prisms'}
        current_meshes['original_cutter'] = original['cutter']
        composition, collars = _i8_resume_composition(stage, vdm, attachments, ports, current_meshes, artifacts['surface_prisms'], lineage)
        collar_pins = {name: persist(name, record) for name, record in collars.items()}
        original_pins = {'rock_before': geometry['mesh_pins']['rock_before'], **{'original_' + name: geometry['mesh_pins'][name] for name in ('cutter', 'rock_after', 'removed')}}
        composition.update(schema=SCHEMA, policy=POLICY, policy_identity_sha256=POLICY_SHA256, main_boolean_recomputed=True, boolean_stage_source_identity_sha256=stage['identity_sha256'], checkpoint_boolean_pin=checkpoint, inputs=inputs, code_sha256=code, code_source_context='current', mesh_pins={**original_pins, **{name: pin for name, pin in main_pins.items() if name != 'surface_prisms'}, **collar_pins}, surface_prisms_pin=main_pins['surface_prisms'], runtime={name: _i8_version(name) for name in ('manifold3d', 'numpy', 'shapely')}, integration_only_no_new_physical_law=True)
        composition_pin = persist('composition', composition)
        index['composition'] = composition_pin
        index['stages_completed'].append('rational-port-stage-saved')
        progress('current: independent composition cold audit')
        audited = audit_composition(composition_pin)
        audit_pin = persist('composition-audit', audited)
        index['composition_audit'] = audit_pin
        index['stages_completed'].append('composition-independent-audit')
        progress('current: latest actual face generation')
        faces_meshes = {name: _x24_read(composition['mesh_pins']['coupled_cutter' if name == 'cutter' else name]) for name in ('cutter', 'removed', 'rock_before', 'rock_after')}
        faces_meshes['original_cutter'] = original['cutter']
        faces = _i8_build_faces(geometry, vdm, attachments, ports, faces_meshes, composition, audited, artifacts['surface_prisms'], audit_pin)
        face_policy = {**faces['policy'], 'composition': 'independently-audited-current-fresh-Boolean-rational-integration'}
        faces.update(schema='td-hybrid-current-faces-v1', policy=face_policy, policy_identity_sha256=_i8_identity(face_policy), inputs={'geometry': geometry_pin, 'composition': composition_pin, 'composition_audit': audit_pin}, code_sha256=code, code_source_context='current')
        faces_pin = persist('faces', faces)
        index['faces'] = faces_pin
        progress('current: independent face cold audit')
        face_audit = audit_faces(faces_pin)
        index['faces_audit'] = persist('faces-audit', face_audit)
        index['stages_completed'].append('faces-independent-audit')
        index['status'] = 'candidate_integration_verified'
    except Exception as error:
        index.update(status='refused', errors=[type(error).__name__ + ': ' + str(error)], failure_kind='generation_or_validation_exception')
    index.update(elapsed_wall_s=_i8_time.monotonic() - started, actual_peak_rss_bytes=_i8_guard())
    if sum((path.stat().st_size for path in output.iterdir() if path.is_file())) > _i8_MAX_BYTES:
        index.update(status='refused', errors=['whole current integration package exceeds 64MiB'])
    persist('index', index)
    return index

def _entry_prepare_hybrid_geometry_current():
    parser = _i8_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=_i8_Path)
    arguments = parser.parse_args()
    result = prepare(arguments.output)
    print(_i8_json.dumps({'status': result['status'], 'stages_completed': result['stages_completed'], 'errors': result.get('errors', [])}))
    return 0 if result['status'] == 'candidate_integration_verified' else 2
ROOT = _i9_Path(__file__).resolve().parents[1]
_i9_sys.path.insert(0, str(ROOT))
CODE_FILES = ('terrain_pipeline/hybrid_geometry.py', 'tools/prepare_hybrid_geometry.py', 'tests/test_hybrid_geometry.py')
SURFACE_INDEX_SHA = 'd4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68'
SURFACE_AUDIT_SHA = '54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5'

def file_sha(path):
    digest = _i9_hashlib.sha256()
    with _i9_Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''):
            digest.update(chunk)
    return digest.hexdigest()

def read(record):
    return _i9_read_pinned(_i9_FilePin(record['path'], record['sha256']))

def checked_identity(record):
    unsigned = dict(record)
    expected = unsigned.pop('identity_sha256')
    if _i9_identity(unsigned) != expected:
        raise ValueError('saved content identity mismatch')

def load_inputs(graph_pin):
    record = _i9_read_pinned(graph_pin)
    graph = _i9_load_graph(record)
    inputs = {key: _i9_asdict(pin) for key, pin in graph.inputs}
    for pin in inputs.values():
        if file_sha(pin['path']) != pin['sha256']:
            raise ValueError('immutable graph parent pin changed: ' + pin['path'])
    if inputs['surface_index']['sha256'] != SURFACE_INDEX_SHA or inputs['surface_audit']['sha256'] != SURFACE_AUDIT_SHA:
        raise ValueError('only fixed actual task14 package authorized')
    fine_index, fine_audit = (read(inputs['fine_index']), read(inputs['fine_audit']))
    checked_identity(fine_index)
    if fine_index['schema'] != 'td-shared-channel-fine-preparation-v1' or fine_index['status'] != 'candidate_unverified' or fine_audit['status'] != 'passed' or fine_audit.get('errors') or (fine_audit['index_sha256'] != inputs['fine_index']['sha256']):
        raise ValueError('fine package requires genuine independent passed audit')
    if fine_index['channel']['index']['sha256'] != SURFACE_INDEX_SHA or fine_index['channel']['audit']['sha256'] != SURFACE_AUDIT_SHA:
        raise ValueError('fine parent is not fixed task14')
    for key in ('manifest', 'material', 'compact_fans'):
        if fine_index[key]['sha256'] != fine_audit[key + '_sha256'] or inputs['fine_' + key]['sha256'] != fine_index[key]['sha256']:
            raise ValueError('graph/fine actual artifact audit linkage mismatch')
    surface_index = read(inputs['surface_index'])
    for index in (fine_index, surface_index):
        for name, expected in index['code_sha256'].items():
            if file_sha(ROOT / name) != expected:
                raise ValueError('frozen parent implementation changed: ' + name)
    hierarchy_pin = inputs['original_hierarchy']
    original_hierarchy = surface_index['inputs']['hierarchy']
    if any((original_hierarchy[key] != hierarchy_pin[key] for key in ('path', 'sha256'))):
        raise ValueError('original hierarchy parent pin mismatch')
    hierarchy = _i9_load_basin_hierarchy(_i9_Path(hierarchy_pin['path']), expected_sha256=hierarchy_pin['sha256'], expected_identity=original_hierarchy['identity_sha256'])
    sections = read(inputs['original_06_sections'])
    protection = read(inputs['original_wet_protection_manifest'])['wet_protection']
    context = _i9_source._i46__context(hierarchy, sections['selected_leaf_ids'], protection)
    fans = read(fine_index['compact_fans'])
    checked_identity(fans)
    return (record, _i9_BedSampler(context, fans['fans']))

def save(path, record):
    size = 0
    digest = _i9_hashlib.sha256()
    with path.open('xb') as stream:
        try:
            for fragment in _i9_json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(',', ':')).iterencode(record):
                data = fragment.encode('utf-8')
                size += len(data)
                if size > _i9_MAX_BYTES:
                    raise ValueError('whole_geometry_file_budget_exceeded')
                digest.update(data)
                stream.write(data)
            _i9_guard()
        except (ValueError, MemoryError):
            stream.close()
            path.unlink()
            raise
    return {'path': str(path), 'sha256': digest.hexdigest(), 'bytes': size, 'identity_sha256': record['identity_sha256']}

def prepare_hybrid_cave_geometry_prepare(graph_pin, output, parameters):
    output = _i9_Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'verification'):
        raise ValueError('new verification output directory required')
    partial = output.with_name(output.name + '.partial')
    if partial.exists():
        raise ValueError('existing partial package must not be overwritten')
    started = _i9_time.perf_counter()
    graph_record, sampler = load_inputs(graph_pin)
    partial.mkdir(parents=True)
    pins = {}
    try:
        geometry, artifacts = _i9_build_geometry(graph_record, sampler, parameters)
        geometry['inputs']['graph'] = _i9_asdict(graph_pin)
        for key in list(artifacts):
            record = artifacts.pop(key)
            pin = save(partial / (key + '.json'), record)
            pin['path'] = str(output / (key + '.json'))
            pins[key] = pin
            del record
        geometry['mesh_pins'] = {key: pins[key] for key in ('rock_before', 'cutter', 'rock_after', 'removed')}
        geometry.update({key + '_pin': pins[key] for key in ('vdm', 'source_sampling', 'surface_attachments')})
        geometry['code_sha256'] = {name: file_sha(ROOT / name) for name in CODE_FILES}
        geometry['readonly_dependency_code_sha256'] = {str(_i9_Path(module.__file__).resolve().relative_to(ROOT)).replace('\\', '/'): file_sha(module.__file__) for name, module in list(_i9_sys.modules.items()) if name.startswith('terrain_pipeline.') and getattr(module, '__file__', None)}
        from importlib.metadata import version
        if version('manifold3d') != '3.5.4':
            raise ValueError('only_pinned_manifold3d_3.5.4_authorized')
        import manifold3d
        geometry['runtime'] = {'manifold3d': version('manifold3d'), 'manifold3d_binary_sha256': file_sha(manifold3d.__file__), 'numpy': version('numpy'), 'python': _i9_sys.version}
        geometry['resource'] = {'elapsed_s': _i9_time.perf_counter() - started, 'top_grid_count': sampler_grid_count(pins, partial), 'hard_grid_count': 300000, 'hard_rss_bytes': 1024 ** 3, 'hard_file_bytes': _i9_MAX_BYTES, 'actual_peak_rss_bytes': _i9_guard(), 'solver_calls': 0}
        _i9_seal(geometry)
        geometry_pin = save(partial / 'geometry.json', geometry)
        geometry_pin['path'] = str(output / 'geometry.json')
        index = {'schema': 'td-hybrid-cave-geometry-preparation-v1', 'status': 'candidate', 'rejection_reasons': [], 'geometry': geometry_pin, 'artifacts': pins, 'graph': _i9_asdict(graph_pin), 'graph_identity_sha256': graph_record['identity_sha256'], 'policy_identity_sha256': _i9_POLICY_SHA256, 'code_sha256': geometry['code_sha256'], 'independent_audit_passed': False, 'hydraulic_solved': False}
    except (ValueError, MemoryError) as error:
        index = {'schema': 'td-hybrid-cave-geometry-preparation-v1', 'status': 'refused', 'rejection_reasons': [str(error)], 'graph': _i9_asdict(graph_pin), 'graph_identity_sha256': graph_record['identity_sha256'], 'policy_identity_sha256': _i9_POLICY_SHA256, 'parameters': _i9_asdict(parameters), 'code_sha256': {name: file_sha(ROOT / name) for name in CODE_FILES}, 'partial_artifacts_not_accepted': pins, 'independent_audit_passed': False, 'hydraulic_solved': False}
    _i9_seal(index)
    save(partial / 'index.json', index)
    partial.rename(output)
    return index

def sampler_grid_count(pins, partial):
    record = _i9_json.loads((partial / 'source_sampling.json').read_bytes())
    return record['top_vertex_count']

def _entry_prepare_hybrid_cave_geometry():
    parser = _i9_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=_i9_Path, required=True)
    parser.add_argument('--graph-sha256', required=True)
    parser.add_argument('--output', type=_i9_Path, required=True)
    for name, default in _i9_asdict(_i9_Parameters()).items():
        parser.add_argument('--' + name.replace('_', '-'), type=int if name == 'stations' else float, default=default)
    args = parser.parse_args()
    parameters = _i9_Parameters(**{name: getattr(args, name) for name in _i9_asdict(_i9_Parameters())})
    index = prepare_hybrid_cave_geometry_prepare(_i9_FilePin(str(args.graph.resolve(strict=True)), args.graph_sha256), args.output, parameters)
    print(_i9_json.dumps({'status': index['status'], 'rejection_reasons': index['rejection_reasons'], 'output': str(args.output)}, ensure_ascii=False))
    return 0 if index['status'] == 'candidate' else 2
_i10_sys.path.insert(0, str(ROOT))
BASE = ROOT / 'verification/natural-river-network'
GEOMETRY = BASE / 'hybrid-cave-geometry-20261006-03/geometry.json'
AUDIT = GEOMETRY.parent / 'independent-audit-v2.json'
GEOMETRY_SHA = '3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593'
AUDIT_SHA = '703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364'
GRAPH_SHA = '279d632e6f471c2629a37d7d6954adbcb734be19278e009eb352c9852593846a'
PREPARE_HYBRID_RIVER_FACES_CODE_FILES = ('terrain_pipeline/hybrid_geometry.py', 'tools/prepare_hybrid_geometry.py', 'tests/test_hybrid_geometry.py')

def prepare_hybrid_river_faces_read(pin, *, check_identity=True):
    path = _i10_Path(pin['path']).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > _i10_MAX_BYTES or file_sha(path) != pin['sha256']:
        raise ValueError('fixed_input_path_bytes_or_SHA_mismatch:' + str(path))
    record = _i10_json.loads(path.read_bytes())
    if check_identity:
        unsigned = dict(record)
        expected = unsigned.pop('identity_sha256')
        if _i10_identity(unsigned) != expected or pin.get('identity_sha256', expected) != expected:
            raise ValueError('saved_input_identity_mismatch')
    return record

def prepare_hybrid_river_faces_load_inputs(geometry_pin, audit_pin):
    if geometry_pin['sha256'] != GEOMETRY_SHA or audit_pin['sha256'] != AUDIT_SHA:
        raise ValueError('only_fixed_independently_passed_geometry03_authorized')
    geometry, audit = (prepare_hybrid_river_faces_read(geometry_pin), prepare_hybrid_river_faces_read(audit_pin, check_identity=False))
    if geometry['schema'] != 'td-hybrid-river-geometry-v1' or geometry['status'] != 'candidate' or geometry['rejection_reasons'] or (audit['schema'] != 'td-hybrid-cave-geometry-independent-audit-v1') or (audit['status'] != 'passed') or audit['errors'] or (audit['geometry_sha256'] != GEOMETRY_SHA) or (not audit['actual_portal_connections_verified']) or (not audit['actual_hydraulic_sections_verified']) or (audit['graph_identity_sha256'] != geometry['graph_identity_sha256']) or (audit['mesh_pins'] != geometry['mesh_pins']) or (audit['inputs'] != geometry['inputs']) or (audit['vdm_pin'] != geometry['vdm_pin']):
        raise ValueError('fixed_geometry_audit_linkage_or_scope_invalid')
    graph_pin = geometry['inputs']['graph']
    if graph_pin['sha256'] != GRAPH_SHA:
        raise ValueError('wrong_fixed_actual_typed_graph')
    graph_record = prepare_hybrid_river_faces_read(graph_pin)
    graph = _i10_load_graph(graph_record)
    if graph_record['identity_sha256'] != geometry['graph_identity_sha256']:
        raise ValueError('typed_graph_geometry_identity_mismatch')
    for pin in geometry['inputs'].values():
        if not _i10_Path(pin['path']).resolve(strict=True).is_relative_to(ROOT) or file_sha(pin['path']) != pin['sha256']:
            raise ValueError('original_readonly_input_pin_changed')
    for group in ('code_sha256', 'readonly_dependency_code_sha256'):
        for name, sha in geometry[group].items():
            if file_sha(ROOT / name) != sha:
                raise ValueError('frozen_geometry_dependency_changed:' + name)
    ports = {}
    for kind in ('sink', 'spring'):
        node = next((node for node in graph.nodes if node.kind == kind))
        ports[kind] = _i10_json.loads(node.source_record_json)
        if geometry['portal_bindings'][kind]['port_identity_sha256'] != ports[kind]['identity_sha256']:
            raise ValueError('actual_canonical_port_binding_mismatch')
    meshes = {name: prepare_hybrid_river_faces_read(pin) for name, pin in geometry['mesh_pins'].items()}
    vdm, attachments = (prepare_hybrid_river_faces_read(geometry['vdm_pin']), prepare_hybrid_river_faces_read(geometry['surface_attachments_pin']))
    return (geometry, vdm, attachments, ports, meshes)

def prepare_hybrid_river_faces_save(path, record, final_path):
    payload = _i10_json.dumps(record, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > _i10_MAX_BYTES:
        raise ValueError('whole_face_saved_file_64MiB_budget_exceeded')
    _i10_guard()
    path.write_bytes(payload)
    return {'path': str(final_path), 'sha256': _i10_hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'identity_sha256': record['identity_sha256']}

def prepare_hybrid_river_faces_prepare(output, geometry_pin, audit_pin):
    import manifold3d
    from importlib.metadata import version
    if version('manifold3d') != '3.5.4':
        raise ValueError('fixed_Mesh64_manifold3d_3.5.4_required')
    output = _i10_Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / 'verification/hybrid-river-network').resolve()):
        raise ValueError('new_bounded_verification_package_required')
    started = _i10_time.monotonic()
    geometry, vdm, attachments, ports, meshes = prepare_hybrid_river_faces_load_inputs(geometry_pin, audit_pin)
    bindings = {'geometry': geometry_pin, 'geometry_audit': audit_pin, 'graph': geometry['inputs']['graph'], 'mesh_pins': geometry['mesh_pins'], 'vdm': geometry['vdm_pin'], 'surface_attachments': geometry['surface_attachments_pin']}
    code = {name: file_sha(ROOT / name) for name in PREPARE_HYBRID_RIVER_FACES_CODE_FILES}
    try:
        faces = _i10_build_faces(geometry, vdm, attachments, ports, meshes)
        faces.update(inputs=bindings, code_sha256=code, runtime={'manifold3d': version('manifold3d'), 'manifold3d_binary_sha256': file_sha(manifold3d.__file__), 'shapely': version('shapely')})
        _i10_seal(faces)
    except (ValueError, MemoryError) as error:
        faces = _i10_seal({'schema': 'td-hybrid-river-faces-v1', 'status': 'refused', 'rejection_reasons': [str(error)], 'inputs': bindings, 'faces': [], 'face_count': 0, 'policy_identity_sha256': _i10_POLICY_SHA256, 'code_sha256': code, 'unknown_geometry_not_zero_flow': True, 'independent_audit_passed': False, 'hydraulic_solved': False})
    output.parent.mkdir(parents=True, exist_ok=True)
    with _i10_tempfile.TemporaryDirectory(prefix='.actual-link-faces-', dir=output.parent) as temporary:
        staging = _i10_Path(temporary) / 'package'
        staging.mkdir()
        try:
            face_pin = prepare_hybrid_river_faces_save(staging / 'faces.json', faces, output / 'faces.json')
        except ValueError as error:
            faces = _i10_seal({'schema': 'td-hybrid-river-faces-v1', 'status': 'refused', 'rejection_reasons': [str(error)], 'inputs': bindings, 'faces': [], 'face_count': 0, 'code_sha256': code, 'policy_identity_sha256': _i10_POLICY_SHA256, 'whole_package_budget_refused_no_selected_subset': True, 'independent_audit_passed': False, 'hydraulic_solved': False})
            face_pin = prepare_hybrid_river_faces_save(staging / 'faces.json', faces, output / 'faces.json')
        index = _i10_seal({'schema': 'td-hybrid-river-faces-preparation-v1', 'status': faces['status'], 'rejection_reasons': faces['rejection_reasons'], 'faces': face_pin, 'inputs': bindings, 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': geometry['graph_identity_sha256'], 'policy_identity_sha256': _i10_POLICY_SHA256, 'code_sha256': code, 'independent_audit_passed': False, 'hydraulic_solved': False, 'resource': {'elapsed_wall_s': _i10_time.monotonic() - started, 'actual_peak_rss_bytes': _i10_guard(), 'max_rss_bytes': _i10_MAX_RSS, 'max_file_bytes': _i10_MAX_BYTES, 'solver_calls': 0, 'old_packages_changed': False}})
        prepare_hybrid_river_faces_save(staging / 'index.json', index, output / 'index.json')
        staging.rename(output)
    return index

def _entry_prepare_hybrid_river_faces():
    parser = _i10_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=_i10_Path, default=GEOMETRY)
    parser.add_argument('--geometry-sha256', default=GEOMETRY_SHA)
    parser.add_argument('--geometry-audit', type=_i10_Path, default=AUDIT)
    parser.add_argument('--geometry-audit-sha256', default=AUDIT_SHA)
    parser.add_argument('--output', type=_i10_Path, required=True)
    args = parser.parse_args()
    index = prepare_hybrid_river_faces_prepare(args.output, {'path': str(args.geometry.resolve(strict=True)), 'sha256': args.geometry_sha256}, {'path': str(args.geometry_audit.resolve(strict=True)), 'sha256': args.geometry_audit_sha256})
    print(_i10_json.dumps({'status': index['status'], 'rejection_reasons': index['rejection_reasons'], 'output': str(args.output)}))
    return 0 if index['status'] == 'candidate_unverified' else 2
_i11_sys.path.insert(0, str(ROOT))
PREPARE_HYBRID_SURFACE_COMPOSITION_CODE_FILES = ('terrain_pipeline/hybrid_geometry.py', 'tools/prepare_hybrid_geometry.py', 'tests/test_hybrid_geometry.py')
DEPENDENCIES = ('terrain_pipeline/hybrid_geometry.py', 'tools/prepare_hybrid_geometry.py')

def prepare_hybrid_surface_composition_save(path, record, final_path):
    payload = _i11_json.dumps(record, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > _i11_MAX_BYTES:
        raise ValueError('whole_surface_composition_file_64MiB_budget_exceeded')
    _i11_guard()
    path.write_bytes(payload)
    return {'path': str(final_path), 'sha256': _i11_hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'identity_sha256': record['identity_sha256']}

def prepare_hybrid_surface_composition_prepare(output, geometry_pin, audit_pin):
    import manifold3d
    if _i11_version('manifold3d') != '3.5.4':
        raise ValueError('fixed_manifold3d_3.5.4_required')
    output = _i11_Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / 'verification/hybrid-river-network').resolve()):
        raise ValueError('new_bounded_surface_composition_package_required')
    started = _i11_time.monotonic()
    geometry, vdm, attachments, ports, meshes = prepare_hybrid_river_faces_load_inputs(geometry_pin, audit_pin)
    node_pins = {kind: value['surface_node_pin'] for kind, value in attachments['attachments'].items()}
    nodes = {kind: prepare_hybrid_river_faces_read(pin) for kind, pin in node_pins.items()}
    sampling = prepare_hybrid_river_faces_read(geometry['source_sampling_pin'])
    inputs = {'geometry': geometry_pin, 'geometry_audit': audit_pin, 'graph': geometry['inputs']['graph'], 'mesh_pins': geometry['mesh_pins'], 'vdm': geometry['vdm_pin'], 'surface_attachments': geometry['surface_attachments_pin'], 'surface_nodes': node_pins, 'original_source_sampling': geometry['source_sampling_pin']}
    code = {name: file_sha(ROOT / name) for name in PREPARE_HYBRID_SURFACE_COMPOSITION_CODE_FILES}
    dependencies = {**geometry['code_sha256'], **geometry['readonly_dependency_code_sha256'], **{name: file_sha(ROOT / name) for name in DEPENDENCIES}}
    try:
        composition, artifacts = _i11_build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling)
    except (ValueError, MemoryError) as error:
        composition = _i11_seal({'schema': 'td-hybrid-surface-composition-v1', 'status': 'refused', 'rejection_reasons': [str(error)], 'policy_identity_sha256': _i11_POLICY_SHA256, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False})
        artifacts = {}
    composition.update(inputs=inputs, code_sha256=code, readonly_dependency_code_sha256=dependencies, runtime={'manifold3d': _i11_version('manifold3d'), 'manifold3d_binary_sha256': file_sha(manifold3d.__file__), 'shapely': _i11_version('shapely'), 'numpy': _i11_version('numpy')})
    output.parent.mkdir(parents=True, exist_ok=True)
    with _i11_tempfile.TemporaryDirectory(prefix='.surface-composition-', dir=output.parent) as temporary:
        staging = _i11_Path(temporary) / 'package'
        staging.mkdir()
        pins = {name: prepare_hybrid_surface_composition_save(staging / (name + '.json'), record, output / (name + '.json')) for name, record in artifacts.items()}
        composition['mesh_pins'] = {'rock_before': geometry['mesh_pins']['rock_before'], **{'original_' + name: geometry['mesh_pins'][name] for name in ('cutter', 'rock_after', 'removed')}, **{name: pin for name, pin in pins.items() if name != 'surface_prisms'}}
        if 'surface_prisms' in pins:
            composition['surface_prisms_pin'] = pins['surface_prisms']
        _i11_seal(composition)
        composition_pin = prepare_hybrid_surface_composition_save(staging / 'composition.json', composition, output / 'composition.json')
        index = _i11_seal({'schema': 'td-hybrid-surface-composition-preparation-v1', 'status': composition['status'], 'rejection_reasons': composition['rejection_reasons'], 'composition': composition_pin, 'artifacts': pins, 'inputs': inputs, 'code_sha256': code, 'readonly_dependency_code_sha256': dependencies, 'policy_identity_sha256': _i11_POLICY_SHA256, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False, 'resource': {'elapsed_wall_s': _i11_time.monotonic() - started, 'actual_peak_rss_bytes': _i11_guard(), 'max_rss_bytes': _i11_MAX_RSS, 'max_file_bytes': _i11_MAX_BYTES, 'solver_calls': 0, 'old_packages_changed': False}})
        prepare_hybrid_surface_composition_save(staging / 'index.json', index, output / 'index.json')
        if sum((path.stat().st_size for path in staging.iterdir())) > _i11_MAX_BYTES:
            raise ValueError('whole_composition_package_64MiB_budget_exceeded_no_publication')
        _i11_guard()
        staging.rename(output)
    return index

def _entry_prepare_hybrid_surface_composition():
    parser = _i11_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=_i11_Path, default=GEOMETRY)
    parser.add_argument('--geometry-sha256', default=GEOMETRY_SHA)
    parser.add_argument('--geometry-audit', type=_i11_Path, default=AUDIT)
    parser.add_argument('--geometry-audit-sha256', default=AUDIT_SHA)
    parser.add_argument('--output', type=_i11_Path, required=True)
    args = parser.parse_args()
    result = prepare_hybrid_surface_composition_prepare(args.output, {'path': str(args.geometry.resolve(strict=True)), 'sha256': args.geometry_sha256}, {'path': str(args.geometry_audit.resolve(strict=True)), 'sha256': args.geometry_audit_sha256})
    print(_i11_json.dumps({'status': result['status'], 'rejection_reasons': result['rejection_reasons'], 'output': str(args.output)}))
    return 0 if result['status'] == 'candidate_unverified' else 2
_i12_sys.path.insert(0, str(ROOT))
PREPARE_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_CODE_FILES = ('terrain_pipeline/hybrid_geometry.py', 'tools/prepare_hybrid_geometry.py', 'tests/test_hybrid_geometry.py')
FROZEN_V1_CODE = {'terrain_pipeline/hybrid_surface_composition.py': '0a9b424ca1994d150c8bf6c3cb90c2ce8c263cd5ca78cace24134242b02c5dd3', 'tools/prepare_hybrid_surface_composition.py': '93e50dec6ac93cbda8396fb2b344fd40204a1c72942c944a17e0ecd698bafff8', 'tests/test_hybrid_surface_composition.py': '5df84c0c6c5cfb17b83c1f25cfc3819ee7c221c9b850d5d62dfbcaf443bc0ae7'}

def refused_from_stage(staging, output, error):
    checkpoint_path = _i12_Path(staging) / 'checkpoint_boolean.json'
    if checkpoint_path.exists():
        checkpoint = _i12_json.loads(checkpoint_path.read_bytes())
        record = dict(checkpoint['composition_stage'])
        record['checkpoint_boolean_pin'] = {'path': str(_i12_Path(output) / 'checkpoint_boolean.json'), 'sha256': file_sha(checkpoint_path), 'bytes': checkpoint_path.stat().st_size, 'identity_sha256': checkpoint['identity_sha256']}
    else:
        record = {'schema': _i12_SCHEMA, 'policy_identity_sha256': _i12_POLICY_SHA256, 'numerical_slice_policy': _i12_NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': _i12_NUMERICAL_POLICY_SHA256, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False}
    record.update(status='refused', rejection_reasons=[type(error).__name__ + ':' + str(error)], boolean_stage_preserved=checkpoint_path.exists(), portal_connections={kind: {'status': 'not_verified', 'rejection_reasons': ['preparation_exception'], 'two_sided_complete_port_verified': False} for kind in ('sink', 'spring')}, preparation_exception={'type': type(error).__name__, 'message': str(error)})
    return _i12_seal(record)

def prepare_hybrid_surface_composition_mechanism_2_prepare(output, geometry_pin, audit_pin):
    import manifold3d
    if _i12_version('manifold3d') != '3.5.4':
        raise ValueError('fixed_manifold3d_3.5.4_required')
    output = _i12_Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / 'verification/hybrid-river-network').resolve()):
        raise ValueError('new_bounded_surface_composition_package_required')
    for name, expected in FROZEN_V1_CODE.items():
        if file_sha(ROOT / name) != expected:
            raise ValueError('frozen_v1_changed:' + name)
    started = _i12_time.monotonic()
    geometry, vdm, attachments, ports, meshes = prepare_hybrid_river_faces_load_inputs(geometry_pin, audit_pin)
    node_pins = {kind: value['surface_node_pin'] for kind, value in attachments['attachments'].items()}
    nodes = {kind: prepare_hybrid_river_faces_read(pin) for kind, pin in node_pins.items()}
    sampling = prepare_hybrid_river_faces_read(geometry['source_sampling_pin'])
    inputs = {'geometry': geometry_pin, 'geometry_audit': audit_pin, 'graph': geometry['inputs']['graph'], 'mesh_pins': geometry['mesh_pins'], 'vdm': geometry['vdm_pin'], 'surface_attachments': geometry['surface_attachments_pin'], 'surface_nodes': node_pins, 'original_source_sampling': geometry['source_sampling_pin']}
    code = {name: file_sha(ROOT / name) for name in PREPARE_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_CODE_FILES}
    dependencies = {**geometry['code_sha256'], **geometry['readonly_dependency_code_sha256'], **FROZEN_V1_CODE, **{name: file_sha(ROOT / name) for name in DEPENDENCIES}}
    runtime = {'manifold3d': _i12_version('manifold3d'), 'manifold3d_binary_sha256': file_sha(manifold3d.__file__), 'shapely': _i12_version('shapely'), 'numpy': _i12_version('numpy')}
    output.parent.mkdir(parents=True, exist_ok=True)
    with _i12_tempfile.TemporaryDirectory(prefix='.surface-composition-v2-', dir=output.parent) as temporary:
        staging = _i12_Path(temporary) / 'package'
        staging.mkdir()
        stage_pins = {}

        def persist_stage(record, artifacts):
            for name, artifact in artifacts.items():
                stage_pins[name] = prepare_hybrid_surface_composition_save(staging / (name + '.json'), artifact, output / (name + '.json'))
            checkpoint = _i12_seal({'schema': 'td-hybrid-surface-composition-boolean-checkpoint-v2', 'status': 'boolean_stage_unverified', 'composition_stage': record, 'artifacts': dict(stage_pins), 'inputs': inputs, 'code_sha256': code, 'readonly_dependency_code_sha256': dependencies, 'runtime': runtime, 'material': record['material'], 'portal_checks_started': False, 'numerical_slice_policy': _i12_NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': _i12_NUMERICAL_POLICY_SHA256})
            pin = prepare_hybrid_surface_composition_save(staging / 'checkpoint_boolean.json', checkpoint, output / 'checkpoint_boolean.json')
            if sum((path.stat().st_size for path in staging.iterdir())) > _i12_MAX_BYTES:
                raise ValueError('whole_stage_package_64MiB_budget_exceeded')
            return pin
        try:
            composition, artifacts = _i12_build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling, persist_stage)
        except (ValueError, AttributeError, TypeError, OverflowError) as error:
            composition = refused_from_stage(staging, output, error)
            artifacts = {}
        pins = dict(stage_pins)
        for name, artifact in artifacts.items():
            if name not in pins:
                try:
                    pins[name] = prepare_hybrid_surface_composition_save(staging / (name + '.json'), artifact, output / (name + '.json'))
                except (AttributeError, TypeError, OverflowError) as error:
                    composition = refused_from_stage(staging, output, error)
                    break

        def bind(record):
            record.update(inputs=inputs, code_sha256=code, readonly_dependency_code_sha256=dependencies, runtime=runtime, mesh_pins={'rock_before': geometry['mesh_pins']['rock_before'], **{'original_' + name: geometry['mesh_pins'][name] for name in ('cutter', 'rock_after', 'removed')}, **{name: pin for name, pin in pins.items() if name != 'surface_prisms'}})
            if 'surface_prisms' in pins:
                record['surface_prisms_pin'] = pins['surface_prisms']
            return _i12_seal(record)
        try:
            composition = bind(composition)
            composition_pin = prepare_hybrid_surface_composition_save(staging / 'composition.json', composition, output / 'composition.json')
        except (AttributeError, TypeError, OverflowError) as error:
            composition = bind(refused_from_stage(staging, output, error))
            composition_pin = prepare_hybrid_surface_composition_save(staging / 'composition.json', composition, output / 'composition.json')
        index = _i12_seal({'schema': 'td-hybrid-surface-composition-preparation-v2', 'status': composition['status'], 'rejection_reasons': composition['rejection_reasons'], 'composition': composition_pin, 'artifacts': pins, 'inputs': inputs, 'code_sha256': code, 'readonly_dependency_code_sha256': dependencies, 'policy_identity_sha256': _i12_POLICY_SHA256, 'numerical_slice_policy_identity_sha256': _i12_NUMERICAL_POLICY_SHA256, 'numerical_slice_policy': _i12_NUMERICAL_POLICY, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False, 'resource': {'elapsed_wall_s': _i12_time.monotonic() - started, 'actual_peak_rss_bytes': _i12_guard(), 'max_rss_bytes': _i12_MAX_RSS, 'max_file_bytes': _i12_MAX_BYTES, 'solver_calls': 0, 'old_packages_changed': False}})
        prepare_hybrid_surface_composition_save(staging / 'index.json', index, output / 'index.json')
        if sum((path.stat().st_size for path in staging.iterdir())) > _i12_MAX_BYTES:
            raise ValueError('whole_composition_package_64MiB_budget_exceeded_no_publication')
        _i12_guard()
        staging.rename(output)
    return index

def _entry_prepare_hybrid_surface_composition_v2():
    parser = _i12_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=_i12_Path, default=GEOMETRY)
    parser.add_argument('--geometry-sha256', default=GEOMETRY_SHA)
    parser.add_argument('--geometry-audit', type=_i12_Path, default=AUDIT)
    parser.add_argument('--geometry-audit-sha256', default=AUDIT_SHA)
    parser.add_argument('--output', type=_i12_Path, required=True)
    args = parser.parse_args()
    result = prepare_hybrid_surface_composition_mechanism_2_prepare(args.output, {'path': str(args.geometry.resolve(strict=True)), 'sha256': args.geometry_sha256}, {'path': str(args.geometry_audit.resolve(strict=True)), 'sha256': args.geometry_audit_sha256})
    print(_i12_json.dumps({'status': result['status'], 'rejection_reasons': result['rejection_reasons'], 'output': str(args.output)}))
    return 0 if result['status'] == 'candidate_unverified' else 2
_i13_sys.path.insert(0, str(ROOT))
SOURCE = BASE / 'hybrid-surface-composition-20261006-02/index.json'
SOURCE_SHA = '54f1fe63f8f8ff2b79e5bb7332c97fa76ec77b780abf772ad9245081b45af105'
PREPARE_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_CODE_FILES = ('terrain_pipeline/hybrid_geometry.py', 'tools/prepare_hybrid_geometry.py', 'tests/test_hybrid_geometry.py')
FROZEN_SOURCE_CODE = {'terrain_pipeline/hybrid_mesh_plane.py': 'ebe155432189c443e8bba0e0ef873873eeb7d4e65d46eaa7756c6877977e23f9', 'terrain_pipeline/hybrid_surface_composition_v2.py': '9ca048b281f6cbf3fa358d84bed4f9a9df97ebfe9e9b2ec2f66129311e0042bd', 'tools/prepare_hybrid_surface_composition_v2.py': 'c7d47d03afbd4c361d95a58c06468e8546a65ebfd7b2a96e19728907bb81509a', 'tests/test_hybrid_surface_composition_v2.py': '2e41c913fa454d64598664947dc0e9cc40cb3e95763ac30c7bc011f4bdd7c18c'}

def load_stage(index_pin):
    if index_pin['sha256'] != SOURCE_SHA:
        raise ValueError('only_fixed_composition02_saved_stage_authorized')
    index = prepare_hybrid_river_faces_read(index_pin)
    composition = prepare_hybrid_river_faces_read(index['composition'])
    checkpoint_pin = composition['checkpoint_boolean_pin']
    checkpoint = prepare_hybrid_river_faces_read(checkpoint_pin)
    stage = checkpoint['composition_stage']
    if index['schema'] != 'td-hybrid-surface-composition-preparation-v2' or composition['schema'] != 'td-hybrid-surface-composition-v2' or checkpoint['schema'] != 'td-hybrid-surface-composition-boolean-checkpoint-v2' or (checkpoint['portal_checks_started'] is not False) or (checkpoint['status'] != 'boolean_stage_unverified') or (stage['status'] != 'boolean_stage_unverified') or stage['rejection_reasons'] or (index['inputs'] != checkpoint['inputs']) or (composition['inputs'] != checkpoint['inputs']) or (index['code_sha256'] != FROZEN_SOURCE_CODE) or (checkpoint['code_sha256'] != FROZEN_SOURCE_CODE) or (composition['code_sha256'] != FROZEN_SOURCE_CODE) or (index['readonly_dependency_code_sha256'] != checkpoint['readonly_dependency_code_sha256']) or (composition['readonly_dependency_code_sha256'] != checkpoint['readonly_dependency_code_sha256']) or (checkpoint['material'] != stage['material']) or (composition['material'] != stage['material']):
        raise ValueError('saved_Boolean_stage_lineage_or_material_changed')
    for group in ('code_sha256', 'readonly_dependency_code_sha256'):
        for name, sha in checkpoint[group].items():
            if file_sha(ROOT / name) != sha:
                raise ValueError('frozen_saved_stage_source_code_changed:' + name)
    inputs = checkpoint['inputs']
    geometry, vdm, attachments, ports, original_meshes = prepare_hybrid_river_faces_load_inputs(inputs['geometry'], inputs['geometry_audit'])
    if stage['geometry_identity_sha256'] != geometry['identity_sha256'] or stage['graph_identity_sha256'] != geometry['graph_identity_sha256']:
        raise ValueError('stage_original_geometry_identity_changed')
    records = {name: prepare_hybrid_river_faces_read(pin) for name, pin in checkpoint['artifacts'].items()}
    for name, pin in checkpoint['artifacts'].items():
        if index['artifacts'][name] != pin or (name != 'surface_prisms' and composition['mesh_pins'][name] != pin):
            raise ValueError('stage_artifact_pin_changed:' + name)
    if composition['surface_prisms_pin'] != checkpoint['artifacts']['surface_prisms']:
        raise ValueError('immutable_stage_prism_pin_changed')
    reusable_pins = {name: pin for name, pin in index['artifacts'].items() if name.endswith('_collar')}
    reusable = {name: prepare_hybrid_river_faces_read(pin) for name, pin in reusable_pins.items()}
    lineage = {'source_index_pin': index_pin, 'source_composition_pin': index['composition'], 'checkpoint_pin': checkpoint_pin, 'boolean_artifact_pins': checkpoint['artifacts'], 'source_code_sha256': checkpoint['code_sha256'], 'source_readonly_dependency_code_sha256': checkpoint['readonly_dependency_code_sha256'], 'source_status': composition['status'], 'source_rejection_reasons': composition['rejection_reasons'], 'main_boolean_recomputed': False}
    meshes = {name: record for name, record in records.items() if name != 'surface_prisms'}
    meshes['original_cutter'] = original_meshes['cutter']
    return (stage, inputs, geometry, vdm, attachments, ports, meshes, records['surface_prisms'], lineage, reusable, reusable_pins)

def prepare_hybrid_surface_composition_mechanism_3_prepare(output, source_pin):
    import manifold3d
    if _i13_version('manifold3d') != '3.5.4':
        raise ValueError('fixed_manifold3d_3.5.4_required')
    output = _i13_Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / 'verification/hybrid-river-network').resolve()):
        raise ValueError('new_bounded_saved_stage_package_required')
    started = _i13_time.monotonic()
    stage, inputs, geometry, vdm, attachments, ports, meshes, prisms, lineage, reusable, inherited_collars = load_stage(source_pin)
    code = {name: file_sha(ROOT / name) for name in PREPARE_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_CODE_FILES}
    dependencies = {**lineage['source_code_sha256'], **lineage['source_readonly_dependency_code_sha256']}
    try:
        composition, artifacts = _i13_resume_composition(stage, vdm, attachments, ports, meshes, prisms, lineage, reusable)
    except (ValueError, AttributeError, TypeError, OverflowError) as error:
        composition = dict(stage)
        composition.update(schema=_i13_SCHEMA, status='refused', rejection_reasons=[type(error).__name__ + ':' + str(error)], policy=_i13_POLICY, policy_identity_sha256=_i13_POLICY_SHA256, numerical_slice_policy=_i13_NUMERICAL_POLICY, numerical_slice_policy_identity_sha256=_i13_NUMERICAL_POLICY_SHA256, stage_lineage=lineage, main_boolean_recomputed=False, material_inherited_unchanged=True, portal_connections={})
        artifacts = {}
    with _i13_tempfile.TemporaryDirectory(prefix='.surface-composition-v3-', dir=output.parent) as temporary:
        staging = _i13_Path(temporary) / 'package'
        staging.mkdir()
        new_pins = {name: prepare_hybrid_surface_composition_save(staging / (name + '.json'), record, output / (name + '.json')) for name, record in artifacts.items()}
        original = geometry['mesh_pins']
        pins = {'rock_before': original['rock_before'], **{'original_' + name: original[name] for name in ('cutter', 'rock_after', 'removed')}, **{name: pin for name, pin in lineage['boolean_artifact_pins'].items() if name != 'surface_prisms'}, **inherited_collars, **new_pins}
        composition.update(inputs=inputs, code_sha256=code, readonly_dependency_code_sha256=dependencies, mesh_pins=pins, surface_prisms_pin=lineage['boolean_artifact_pins']['surface_prisms'], checkpoint_boolean_pin=lineage['checkpoint_pin'], runtime={'manifold3d': _i13_version('manifold3d'), 'manifold3d_binary_sha256': file_sha(manifold3d.__file__), 'shapely': _i13_version('shapely'), 'numpy': _i13_version('numpy')})
        composition_pin = prepare_hybrid_surface_composition_save(staging / 'composition.json', _i13_seal(composition), output / 'composition.json')
        index = _i13_seal({'schema': 'td-hybrid-surface-composition-preparation-v3', 'status': composition['status'], 'rejection_reasons': composition['rejection_reasons'], 'composition': composition_pin, 'inputs': inputs, 'stage_lineage': lineage, 'artifacts': {**lineage['boolean_artifact_pins'], **inherited_collars, **new_pins}, 'code_sha256': code, 'readonly_dependency_code_sha256': dependencies, 'policy_identity_sha256': _i13_POLICY_SHA256, 'numerical_slice_policy': _i13_NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': _i13_NUMERICAL_POLICY_SHA256, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False, 'resource': {'elapsed_wall_s': _i13_time.monotonic() - started, 'actual_peak_rss_bytes': _i13_guard(), 'max_rss_bytes': _i13_MAX_RSS, 'max_file_bytes': _i13_MAX_BYTES, 'main_boolean_calls': 0, 'solver_calls': 0}})
        prepare_hybrid_surface_composition_save(staging / 'index.json', index, output / 'index.json')
        if sum((path.stat().st_size for path in staging.iterdir())) > _i13_MAX_BYTES:
            raise ValueError('whole_resume_package_64MiB_budget_exceeded_no_publication')
        _i13_guard()
        staging.rename(output)
    return index

def _entry_prepare_hybrid_surface_composition_v3():
    parser = _i13_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-index', type=_i13_Path, default=SOURCE)
    parser.add_argument('--source-index-sha256', default=SOURCE_SHA)
    parser.add_argument('--output', type=_i13_Path, required=True)
    args = parser.parse_args()
    result = prepare_hybrid_surface_composition_mechanism_3_prepare(args.output, {'path': str(args.source_index.resolve(strict=True)), 'sha256': args.source_index_sha256})
    print(_i13_json.dumps({'status': result['status'], 'rejection_reasons': result['rejection_reasons'], 'output': str(args.output)}))
    return 0 if result['status'] == 'candidate_unverified' else 2

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'current': '_entry_prepare_hybrid_geometry_current', 'cave': '_entry_prepare_hybrid_cave_geometry', 'faces': '_entry_prepare_hybrid_river_faces'}
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
