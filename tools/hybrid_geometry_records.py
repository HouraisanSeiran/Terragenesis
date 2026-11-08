"""Consolidated hybrid_geometry_records implementations; numeric expressions preserved."""
from __future__ import annotations
import hashlib as _i14_hashlib
import json as _i14_json
from pathlib import Path as _i14_Path
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i14_MAX_BYTES
from terrain_pipeline.hybrid_geometry import MAX_RSS as _i14_MAX_RSS
from terrain_pipeline.hybrid_geometry import guard as _i14_guard
from terrain_pipeline.hybrid_geometry import seal as _i14_seal
from terrain_pipeline.hybrid_geometry import identity as _i14_identity
from terrain_pipeline.hybrid_geometry import load_graph as _i14_load_graph
CATEGORY = 'C'
ROOT = _i14_Path(__file__).resolve().parents[1]
BASE = ROOT / 'verification/natural-river-network'
GEOMETRY = BASE / 'hybrid-cave-geometry-20261006-03/geometry.json'
AUDIT = GEOMETRY.parent / 'independent-audit-v2.json'
GEOMETRY_SHA = '3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593'
AUDIT_SHA = '703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364'
GRAPH_SHA = '279d632e6f471c2629a37d7d6954adbcb734be19278e009eb352c9852593846a'

def file_sha(path):
    digest = _i14_hashlib.sha256()
    with _i14_Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''):
            digest.update(chunk)
    return digest.hexdigest()

def read(pin, *, check_identity=True):
    path = _i14_Path(pin['path']).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > _i14_MAX_BYTES or file_sha(path) != pin['sha256']:
        raise ValueError('fixed_input_path_bytes_or_SHA_mismatch:' + str(path))
    record = _i14_json.loads(path.read_bytes())
    if check_identity:
        unsigned = dict(record)
        expected = unsigned.pop('identity_sha256')
        if _i14_identity(unsigned) != expected or pin.get('identity_sha256', expected) != expected:
            raise ValueError('saved_input_identity_mismatch')
    return record

def load_inputs(geometry_pin, audit_pin):
    if geometry_pin['sha256'] != GEOMETRY_SHA or audit_pin['sha256'] != AUDIT_SHA:
        raise ValueError('only_fixed_independently_passed_geometry03_authorized')
    geometry, audit = (read(geometry_pin), read(audit_pin, check_identity=False))
    if geometry['schema'] != 'td-hybrid-river-geometry-v1' or geometry['status'] != 'candidate' or geometry['rejection_reasons'] or (audit['schema'] != 'td-hybrid-cave-geometry-independent-audit-v1') or (audit['status'] != 'passed') or audit['errors'] or (audit['geometry_sha256'] != GEOMETRY_SHA) or (not audit['actual_portal_connections_verified']) or (not audit['actual_hydraulic_sections_verified']) or (audit['graph_identity_sha256'] != geometry['graph_identity_sha256']) or (audit['mesh_pins'] != geometry['mesh_pins']) or (audit['inputs'] != geometry['inputs']) or (audit['vdm_pin'] != geometry['vdm_pin']):
        raise ValueError('fixed_geometry_audit_linkage_or_scope_invalid')
    graph_pin = geometry['inputs']['graph']
    if graph_pin['sha256'] != GRAPH_SHA:
        raise ValueError('wrong_fixed_actual_typed_graph')
    graph_record = read(graph_pin)
    graph = _i14_load_graph(graph_record)
    if graph_record['identity_sha256'] != geometry['graph_identity_sha256']:
        raise ValueError('typed_graph_geometry_identity_mismatch')
    for pin in geometry['inputs'].values():
        if not _i14_Path(pin['path']).resolve(strict=True).is_relative_to(ROOT) or file_sha(pin['path']) != pin['sha256']:
            raise ValueError('original_readonly_input_pin_changed')
    for group in ('code_sha256', 'readonly_dependency_code_sha256'):
        for name, sha in geometry[group].items():
            if file_sha(ROOT / name) != sha:
                raise ValueError('frozen_geometry_dependency_changed:' + name)
    ports = {}
    for kind in ('sink', 'spring'):
        node = next((node for node in graph.nodes if node.kind == kind))
        ports[kind] = _i14_json.loads(node.source_record_json)
        if geometry['portal_bindings'][kind]['port_identity_sha256'] != ports[kind]['identity_sha256']:
            raise ValueError('actual_canonical_port_binding_mismatch')
    meshes = {name: read(pin) for name, pin in geometry['mesh_pins'].items()}
    vdm, attachments = (read(geometry['vdm_pin']), read(geometry['surface_attachments_pin']))
    return (geometry, vdm, attachments, ports, meshes)

def save(path, record, final_path):
    payload = _i14_json.dumps(record, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > _i14_MAX_BYTES:
        raise ValueError('whole_face_saved_file_64MiB_budget_exceeded')
    _i14_guard()
    path.write_bytes(payload)
    return {'path': str(final_path), 'sha256': _i14_hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'identity_sha256': record['identity_sha256']}
CURRENT_GENERATOR_FILES = ('terrain_pipeline/hybrid_geometry.py', 'tools/hybrid_geometry_records.py', 'tools/prepare_hybrid_geometry.py')
CURRENT_AUDIT_FILES = ('tools/audit_hybrid_geometry.py', 'tools/hybrid_geometry_audit_base.py', 'tools/hybrid_geometry_saved_checks.py', 'tools/hybrid_geometry_face_checks.py', 'tools/hybrid_cave_saved_audit.py', 'tools/hybrid_exact_solid_saved_audit.py', 'tools/hybrid_surface_resume_saved_audit.py', 'tools/hybrid_interval_winding_saved_audit.py', 'tools/td_shared_channel_fine_saved_audit.py', 'tools/hybrid_geometry_records.py')

def verify_current_code(record, expected_names=CURRENT_GENERATOR_FILES):
    if record.get('code_source_context') != 'current' or set(record.get('code_sha256', {})) != set(expected_names):
        raise ValueError('current source context or complete code registry differs')
    for name, expected in record['code_sha256'].items():
        if file_sha(ROOT / name) != expected:
            raise ValueError('current source sha256 mismatch: ' + name)

def current_audit_code():
    return {name: file_sha(ROOT / name) for name in CURRENT_AUDIT_FILES}
