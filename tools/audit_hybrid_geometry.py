"""Consolidated audit_hybrid_geometry implementations; numeric expressions preserved."""
from __future__ import annotations
import numpy as _i15_np
from tools.hybrid_geometry_audit_base import EmptySolid as _i15_EmptySolid
from tools.hybrid_geometry_audit_base import audit_material_solids as _i15_audit_material_solids
from tools.hybrid_geometry_audit_base import audit_sampling_mismatches as _i15_audit_sampling_mismatches
from tools.hybrid_geometry_saved_checks import Solid as _i15_Solid
from tools.hybrid_geometry_saved_checks import audit_prisms as _i15_audit_prisms
from tools.hybrid_geometry_saved_checks import audit_port as _i15_audit_port
from tools.hybrid_geometry_saved_checks import NUMERICAL_POLICY_SHA256 as _i15_NUMERICAL_POLICY_SHA256
from tools.td_shared_channel_fine_saved_audit import check_identity as _i15_check_identity
from tools.td_shared_channel_fine_saved_audit import compare as _i15_compare
from tools.td_shared_channel_fine_saved_audit import read as _i15_read
from tools.td_shared_channel_fine_saved_audit import require as _i15_require
from tools.hybrid_surface_resume_saved_audit import load_native_bound as _i15_load_native_bound
from tools.hybrid_interval_winding_saved_audit import IntervalSolid as _i15_IntervalSolid
from tools.hybrid_interval_winding_saved_audit import runtime_identity as _i15_runtime_identity
import argparse as _i16_argparse
import json as _i16_json
import math as _i16_math
import os as _i16_os
from pathlib import Path as _i16_Path
import sys as _i16_sys
import tempfile as _i16_tempfile
import time as _i16_time
import numpy as _i16_np
from tools.hybrid_cave_saved_audit import MANIFOLD_DIRECTORY as _i16_MANIFOLD_DIRECTORY
from tools.hybrid_cave_saved_audit import MAX_BYTES as _i16_MAX_BYTES
from tools.hybrid_cave_saved_audit import MAX_RSS as _i16_MAX_RSS
from tools.hybrid_cave_saved_audit import IndependentBed as _i16_IndependentBed
from tools.hybrid_cave_saved_audit import Solid as _i16_Solid
from tools.hybrid_cave_saved_audit import audit_hydraulic_sections as _i16_audit_hydraulic_sections
from tools.hybrid_cave_saved_audit import audit_source_sampling as _i16_audit_source_sampling
from tools.hybrid_cave_saved_audit import audit_surface_attachments as _i16_audit_surface_attachments
from tools.hybrid_cave_saved_audit import audit_typed_graph as _i16_audit_typed_graph
from tools.hybrid_cave_saved_audit import audit_vdm as _i16_audit_vdm
from tools.hybrid_cave_saved_audit import boolean_evidence as _i16_boolean_evidence
from tools.hybrid_cave_saved_audit import check_memory as _i16_check_memory
from tools.hybrid_cave_saved_audit import checked_path as _i16_checked_path
from tools.hybrid_cave_saved_audit import compare as _i16_compare
from tools.hybrid_cave_saved_audit import digest as _i16_digest
from tools.hybrid_cave_saved_audit import file_sha256 as _i16_file_sha256
from tools.hybrid_cave_saved_audit import read as _i16_read
from tools.hybrid_cave_saved_audit import require as _i16_require
from tools.hybrid_cave_saved_audit import saved_air_route as _i16_saved_air_route
import argparse as _i17_argparse
import json as _i17_json
import math as _i17_math
import os as _i17_os
from pathlib import Path as _i17_Path
import sys as _i17_sys
import tempfile as _i17_tempfile
import time as _i17_time
import numpy as _i17_np
from tools.hybrid_cave_saved_audit import MANIFOLD_DIRECTORY as _i17_MANIFOLD_DIRECTORY
from tools.hybrid_cave_saved_audit import MAX_BYTES as _i17_MAX_BYTES
from tools.hybrid_cave_saved_audit import MAX_RSS as _i17_MAX_RSS
from tools.hybrid_cave_saved_audit import IndependentBed as _i17_IndependentBed
from tools.hybrid_cave_saved_audit import Solid as _i17_Solid
from tools.hybrid_cave_saved_audit import audit_hydraulic_sections as _i17_audit_hydraulic_sections
from tools.hybrid_cave_saved_audit import audit_source_sampling as _i17_audit_source_sampling
from tools.hybrid_cave_saved_audit import audit_surface_attachments as _i17_audit_surface_attachments
from tools.hybrid_cave_saved_audit import audit_typed_graph as _i17_audit_typed_graph
from tools.hybrid_cave_saved_audit import audit_vdm as _i17_audit_vdm
from tools.hybrid_cave_saved_audit import boolean_evidence as _i17_boolean_evidence
from tools.hybrid_cave_saved_audit import check_memory as _i17_check_memory
from tools.hybrid_cave_saved_audit import checked_path as _i17_checked_path
from tools.hybrid_cave_saved_audit import compare as _i17_compare
from tools.hybrid_cave_saved_audit import digest as _i17_digest
from tools.hybrid_cave_saved_audit import file_sha256 as _i17_file_sha256
from tools.hybrid_cave_saved_audit import read as _i17_read
from tools.hybrid_cave_saved_audit import require as _i17_require
from tools.hybrid_cave_saved_audit import saved_air_route as _i17_saved_air_route
import argparse as _i18_argparse
import json as _i18_json
import math as _i18_math
from pathlib import Path as _i18_Path
import sys as _i18_sys
import time as _i18_time
import numpy as _i18_np
from tools.hybrid_cave_saved_audit import Solid as _i18_Solid
from tools.hybrid_cave_saved_audit import manifold_library as _i18_manifold_library
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i18_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_identity as _i18_check_identity
from tools.td_shared_channel_fine_saved_audit import check_memory as _i18_check_memory
from tools.td_shared_channel_fine_saved_audit import checked_path as _i18_checked_path
from tools.td_shared_channel_fine_saved_audit import compare as _i18_compare
from tools.td_shared_channel_fine_saved_audit import digest as _i18_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i18_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i18_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i18_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i18_require
import argparse as _i20_argparse
from fractions import Fraction as _i20_Fraction
import json as _i20_json
import math as _i20_math
from pathlib import Path as _i20_Path
import sys as _i20_sys
import time as _i20_time
import numpy as _i20_np
from tools.hybrid_cave_saved_audit import Solid as _i20_Solid
from tools.hybrid_cave_saved_audit import manifold_library as _i20_manifold_library
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i20_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_identity as _i20_check_identity
from tools.td_shared_channel_fine_saved_audit import checked_path as _i20_checked_path
from tools.td_shared_channel_fine_saved_audit import check_memory as _i20_check_memory
from tools.td_shared_channel_fine_saved_audit import compare as _i20_compare
from tools.td_shared_channel_fine_saved_audit import digest as _i20_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i20_file_sha256
from tools.td_shared_channel_fine_saved_audit import load_native as _i20_load_native
from tools.td_shared_channel_fine_saved_audit import read as _i20_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i20_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i20_require
import argparse as _i21_argparse
from collections import Counter as _i21_Counter
from collections import defaultdict as _i21_defaultdict
from fractions import Fraction as _i21_Fraction
import json as _i21_json
import math as _i21_math
from pathlib import Path as _i21_Path
import sys as _i21_sys
import time as _i21_time
import numpy as _i21_np
from tools.hybrid_cave_saved_audit import Solid as _i21_Solid
from tools.hybrid_cave_saved_audit import manifold_library as _i21_manifold_library
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i21_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_identity as _i21_check_identity
from tools.td_shared_channel_fine_saved_audit import check_memory as _i21_check_memory
from tools.td_shared_channel_fine_saved_audit import compare as _i21_compare
from tools.td_shared_channel_fine_saved_audit import digest as _i21_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i21_file_sha256
from tools.td_shared_channel_fine_saved_audit import load_native as _i21_load_native
from tools.td_shared_channel_fine_saved_audit import read as _i21_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i21_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i21_require
import argparse as _i22_argparse
from collections import Counter as _i22_Counter
from collections import defaultdict as _i22_defaultdict
from fractions import Fraction as _i22_Fraction
import json as _i22_json
import math as _i22_math
from pathlib import Path as _i22_Path
import sys as _i22_sys
import time as _i22_time
import numpy as _i22_np
from tools.hybrid_cave_saved_audit import manifold_library as _i22_manifold_library
from tools.hybrid_exact_solid_saved_audit import ExactSolid as _i22_ExactSolid
from tools.hybrid_exact_solid_saved_audit import SOLID_POLICY as _i22_SOLID_POLICY
from tools.hybrid_exact_solid_saved_audit import SOLID_POLICY_SHA256 as _i22_SOLID_POLICY_SHA256
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i22_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_identity as _i22_check_identity
from tools.td_shared_channel_fine_saved_audit import check_memory as _i22_check_memory
from tools.td_shared_channel_fine_saved_audit import compare as _i22_compare
from tools.td_shared_channel_fine_saved_audit import digest as _i22_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i22_file_sha256
from tools.td_shared_channel_fine_saved_audit import load_native as _i22_load_native
from tools.td_shared_channel_fine_saved_audit import read as _i22_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i22_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i22_require
import argparse as _i19_argparse
import json as _i19_json
import math as _i19_math
from pathlib import Path as _i19_Path
import sys as _i19_sys
import time as _i19_time
import numpy as _i19_np
from shapely.geometry import LineString as _i19_LineString
from shapely.geometry import Polygon as _i19_Polygon
from shapely.ops import unary_union as _i19_unary_union
from tools.hybrid_exact_solid_saved_audit import ExactSolid as _i19_Solid
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i19_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_identity as _i19_check_identity
from tools.td_shared_channel_fine_saved_audit import check_memory as _i19_check_memory
from tools.td_shared_channel_fine_saved_audit import compare as _i19_compare
from tools.td_shared_channel_fine_saved_audit import digest as _i19_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i19_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i19_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i19_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i19_require
import argparse as _i23_argparse
import json as _i23_json
from pathlib import Path as _i23_Path
import sys as _i23_sys
import time as _i23_time
import traceback as _i23_traceback
import numpy as _i23_np
from tools.hybrid_surface_resume_saved_audit import ValidatedSolid as _i23_ValidatedSolid
from tools.hybrid_surface_resume_saved_audit import load_native_bound as _i23_load_native_bound
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i23_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_memory as _i23_check_memory
from tools.td_shared_channel_fine_saved_audit import compare as _i23_compare
from tools.td_shared_channel_fine_saved_audit import digest as _i23_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i23_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i23_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i23_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i23_require
import argparse as _i24_argparse
import copy as _i24_copy
import json as _i24_json
from pathlib import Path as _i24_Path
import sys as _i24_sys
import time as _i24_time
import numpy as _i24_np
from tools.hybrid_interval_winding_saved_audit import IntervalSolid as _i24_IntervalSolid
from tools.hybrid_interval_winding_saved_audit import POLICY as _i24_POLICY
from tools.hybrid_interval_winding_saved_audit import POLICY_SHA256 as _i24_POLICY_SHA256
from tools.hybrid_interval_winding_saved_audit import runtime_identity as _i24_runtime_identity
from tools.hybrid_surface_resume_saved_audit import ValidatedSolid as _i24_ValidatedSolid
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i24_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_memory as _i24_check_memory
from tools.td_shared_channel_fine_saved_audit import checked_path as _i24_checked_path
from tools.td_shared_channel_fine_saved_audit import digest as _i24_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i24_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i24_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i24_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i24_require
import argparse as _i25_argparse
import copy as _i25_copy
import json as _i25_json
from pathlib import Path as _i25_Path
import sys as _i25_sys
import time as _i25_time
import numpy as _i25_np
from tools.hybrid_interval_winding_saved_audit import IntervalSolid as _i25_IntervalSolid
from tools.hybrid_interval_winding_saved_audit import POLICY as _i25_POLICY
from tools.hybrid_interval_winding_saved_audit import POLICY_SHA256 as _i25_POLICY_SHA256
from tools.hybrid_interval_winding_saved_audit import runtime_identity as _i25_runtime_identity
from tools.hybrid_surface_resume_saved_audit import ValidatedSolid as _i25_ValidatedSolid
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i25_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_memory as _i25_check_memory
from tools.td_shared_channel_fine_saved_audit import checked_path as _i25_checked_path
from tools.td_shared_channel_fine_saved_audit import digest as _i25_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i25_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i25_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i25_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i25_require
from tools.hybrid_geometry_records import GEOMETRY_SHA as _x27_GEOMETRY_SHA
from tools.hybrid_geometry_records import read as _x28_read
from tools.hybrid_geometry_records import load_inputs as _x29_load_inputs
from tools.hybrid_geometry_records import verify_current_code as _x30_verify_current_code
from tools.hybrid_geometry_records import current_audit_code as _x31_current_audit_code
CATEGORY = 'C'
SCHEMA = 'td-hybrid-current-composition-audit-v1'

def load_native_for_geometry(geometry):
    sections_pin = geometry['inputs']['original_06_sections']
    sections = _x28_read(sections_pin)
    protection_pin = geometry['inputs']['original_wet_protection_manifest']
    protection = _x28_read(protection_pin)['wet_protection']
    native, binding = _i15_load_native_bound(geometry['inputs']['original_hierarchy'], sections['hierarchy_identity_sha256'], sections['selected_leaf_ids'], protection)
    return (native, {**binding, 'sections_pin': dict(sections_pin), 'sections_identity_field': 'hierarchy_identity_sha256', 'sections_record_identity_sha256': sections['identity_sha256'], 'wet_protection_pin': dict(protection_pin)})

def audit_composition(composition_pin):
    record = _x28_read(composition_pin)
    _x30_verify_current_code(record)
    _i15_require(record['schema'] == 'td-hybrid-current-composition-v1' and record['status'] == 'candidate_unverified' and (not record['rejection_reasons']), 'current composition is incomplete or refused')
    for name in ('independent_audit_passed', 'hydraulic_ready', 'hydraulic_solved', 'full_network_verified'):
        _i15_require(record[name] is False, 'premature current composition claim: ' + name)
    inputs = record['inputs']
    _i15_require(inputs['geometry']['sha256'] == _x27_GEOMETRY_SHA, 'current fixed source geometry differs')
    geometry, vdm, attachments, ports, original_meshes = _x29_load_inputs(inputs['geometry'], inputs['geometry_audit'])
    _i15_require(inputs['graph'] == geometry['inputs']['graph'] and inputs['mesh_pins'] == geometry['mesh_pins'] and (inputs['vdm'] == geometry['vdm_pin']) and (inputs['surface_attachments'] == geometry['surface_attachments_pin']) and (inputs['original_source_sampling'] == geometry['source_sampling_pin']), 'current original input registry differs')
    _i15_require(len(vdm['stations']) == 17 and len(geometry['hydraulic_links']) == 18, 'current integration scope is fixed 17 stations / 18 links')
    _i15_require(record['geometry_identity_sha256'] == geometry['identity_sha256'] and record['graph_identity_sha256'] == geometry['graph_identity_sha256'], 'current composition original graph or geometry differs')
    _i15_require(record['numerical_slice_policy_identity_sha256'] == _i15_NUMERICAL_POLICY_SHA256, 'current slice numerical identity differs')
    lineage = record['stage_lineage']
    stage_index = _x28_read(lineage['source_index_pin'])
    checkpoint = _x28_read(lineage['checkpoint_pin'])
    _i15_require(lineage['mode'] == 'fresh-original-boolean-then-rational-port' and stage_index['schema'] == 'td-hybrid-current-boolean-index-v1' and (checkpoint['schema'] == 'td-hybrid-current-boolean-checkpoint-v1') and (checkpoint['portal_checks_started'] is False) and (stage_index['inputs'] == checkpoint['inputs'] == inputs) and (stage_index['artifacts'] == checkpoint['artifacts']) and (record['main_boolean_recomputed'] is True), 'current fresh stage lineage is missing or mixed with historical fixed-v3')
    _x30_verify_current_code(stage_index)
    _x30_verify_current_code(checkpoint)
    _i15_require(stage_index['code_sha256'] == checkpoint['code_sha256'] == record['code_sha256'], 'current stage code map changed')
    stage = checkpoint['composition_stage']
    _i15_check_identity(stage)
    _i15_require(stage['schema'] == 'td-hybrid-surface-boolean-stage-current-v1' and stage['material'] == record['material'] and (record['boolean_stage_source_identity_sha256'] == stage['identity_sha256']), 'current stage material or identity changed during portal integration')
    for name, pin in checkpoint['artifacts'].items():
        actual = record['surface_prisms_pin'] if name == 'surface_prisms' else record['mesh_pins'][name]
        _i15_require(actual == pin, 'current main Boolean stage artifact replaced: ' + name)
    meshes = {}
    interval_queries = []
    origin = None
    for role, pin in record['mesh_pins'].items():
        mesh = _x28_read(pin)
        location = _i15_np.asarray(mesh['local_origin_xyz_m'], float)
        if origin is None:
            origin = location
        _i15_require(_i15_np.array_equal(location, origin), 'current solids do not share one local origin')
        if mesh['schema'] == 'td-hybrid-empty-solid-v1':
            _i15_require(role == 'extra_removed' and mesh['signed_volume_m3'] == 0.0 and (mesh['triangles'] == []) and (mesh['vertices_local_xyz_m'] == []), 'invalid current empty solid')
            meshes[role] = _i15_EmptySolid()
        else:
            validated = _i15_Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], role)
            meshes[role] = _i15_IntervalSolid(validated, pin, interval_queries)
            _i15_compare(mesh['signed_volume_m3'], meshes[role].signed_volume, 'current saved volume ' + role, atol=1e-07, rtol=1e-09)
    native, native_binding = load_native_for_geometry(geometry)
    prisms = _x28_read(record['surface_prisms_pin'])
    _, source_reports = _i15_audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    material = _i15_audit_material_solids(*(meshes[name] for name in ('rock_before', 'original_rock_after', 'original_removed', 'surface_cutter', 'coupled_cutter', 'rock_after', 'extra_removed', 'removed', 'original_cutter')))
    for name in ('original_removed_m3', 'extra_removed_m3', 'total_removed_m3'):
        _i15_compare(record['material'][name], material[name], 'current material ' + name, atol=1e-07, rtol=1e-09)
    sampling = _x28_read(inputs['original_source_sampling'])
    mismatch = _i15_audit_sampling_mismatches(record['original_source_sampling_cut_lookup_mismatches'], sampling, attachments)
    reports, evidence = ({}, {})
    for kind in ('sink', 'spring'):
        evidence[kind] = {}
        reports[kind] = _i15_audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, evidence[kind])
    return {'schema': SCHEMA, 'status': 'passed', 'errors': [], 'composition_pin': composition_pin, 'composition_identity_sha256': record['identity_sha256'], 'inputs': inputs, 'mesh_pins': record['mesh_pins'], 'surface_prisms_pin': record['surface_prisms_pin'], 'materials_verified': True, 'native_half_arm_sources_verified': True, 'two_sided_complete_port_verified': True, 'stage_lineage_verified': True, 'stage_lineage': lineage, 'material': material, 'portal_reports': reports, 'prism_source_reports': source_reports, 'sampling_mismatch_report': mismatch, 'native_identity_binding': native_binding, 'interval_winding_queries': interval_queries, 'interval_runtime': _i15_runtime_identity(), 'portal_evidence': evidence, 'hydraulic_ready': False, 'publishable': False, 'audit_code_sha256': _x31_current_audit_code()}

def audit_faces(pin):
    from shapely.geometry import LineString
    from tools.hybrid_geometry_audit_base import check_plane
    from tools.hybrid_geometry_audit_base import source_canonical_floor
    from tools.hybrid_geometry_audit_base import whole_line_supported
    from tools.hybrid_geometry_saved_checks import audit_exact_slice
    from tools.hybrid_geometry_saved_checks import NUMERICAL_POLICY
    from tools.hybrid_geometry_face_checks import audit_role_slice
    from tools.hybrid_geometry_face_checks import audit_boundary
    record = _x28_read(pin)
    _x30_verify_current_code(record)
    _i15_require(record['schema'] == 'td-hybrid-current-faces-v1', 'wrong current face schema')
    inputs = record['inputs']
    geometry = _x28_read(inputs['geometry'])
    composition = _x28_read(inputs['composition'])
    coupled_audit = _x28_read(inputs['composition_audit'])
    _x30_verify_current_code(composition)
    _i15_require(coupled_audit.get('audit_code_sha256') == _x31_current_audit_code(), 'current composition auditor source changed')
    _i15_require(composition['schema'] == 'td-hybrid-current-composition-v1' and composition['status'] == 'candidate_unverified' and (not composition['rejection_reasons']) and (coupled_audit['schema'] == SCHEMA) and (coupled_audit['status'] == 'passed') and (coupled_audit['errors'] == []) and (coupled_audit['composition_pin'] == inputs['composition']) and (coupled_audit['composition_identity_sha256'] == composition['identity_sha256']) and (coupled_audit['inputs'] == composition['inputs']) and (coupled_audit['mesh_pins'] == composition['mesh_pins']) and (coupled_audit['surface_prisms_pin'] == composition['surface_prisms_pin']) and (coupled_audit['materials_verified'] is True) and (coupled_audit['native_half_arm_sources_verified'] is True) and (coupled_audit['two_sided_complete_port_verified'] is True) and (coupled_audit['stage_lineage_verified'] is True) and (coupled_audit['stage_lineage'] == composition['stage_lineage']) and (record['stage_lineage'] == composition['stage_lineage']) and (record['composition_identity_sha256'] == composition['identity_sha256']), 'current faces do not bind the independently audited composition')
    _i15_require(record['numerical_slice_policy'] == composition['numerical_slice_policy'] == NUMERICAL_POLICY and record['numerical_slice_policy_identity_sha256'] == _i15_NUMERICAL_POLICY_SHA256 and (composition['numerical_slice_policy_identity_sha256'] == _i15_NUMERICAL_POLICY_SHA256), 'current faces have an unverified slice policy')
    _i15_require(inputs['geometry'] == composition['inputs']['geometry'] and inputs['geometry']['sha256'] == _x27_GEOMETRY_SHA and (geometry['identity_sha256'] == record['geometry_identity_sha256']) and (geometry['graph_identity_sha256'] == record['graph_identity_sha256']) and (record['face_count'] == len(record['faces']) == len(geometry['hydraulic_links']) == 18), 'current geometry/face census differs')
    for flag in ('independent_audit_passed', 'hydraulic_solved', 'water_discharge_computed', 'storage_geometry_changed', 'pressure_slot_enlarges_face', 'native_exact'):
        _i15_require(record[flag] is False, 'premature current face claim: ' + flag)
    vdm = _x28_read(composition['inputs']['vdm'])
    prisms = _x28_read(composition['surface_prisms_pin'])
    attachments = _x28_read(composition['inputs']['surface_attachments'])
    original_pin = composition['mesh_pins']['original_cutter']
    original = _x28_read(original_pin)
    pins = {role: composition['mesh_pins']['coupled_cutter' if role == 'cutter' else role] for role in ('cutter', 'rock_before', 'rock_after', 'removed')}
    meshes = {role: _x28_read(mesh_pin) for role, mesh_pin in pins.items()}
    common = _i15_np.asarray(meshes['cutter']['local_origin_xyz_m'])
    solids = {}
    interval_queries = []
    for role, mesh in meshes.items():
        _i15_require(_i15_np.array_equal(mesh['local_origin_xyz_m'], common), 'current face source frames differ')
        validated = _i15_Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], role)
        solids[role] = _i15_IntervalSolid(validated, pins[role], interval_queries)
    reports, errors = ([], [])
    cells = {cell['cell_id']: cell for cell in geometry['hydraulic_cells']}
    for ordinal, face in enumerate(record['faces']):
        try:
            _i15_check_identity(face)
            _i15_require(face['schema'] == 'td-hybrid-river-face-v2' and face['face_id'] == 'face:' + str(ordinal) and (face['status'] == 'candidate') and (not face['rejection_reasons']), 'unknown/refused current face')
            link = geometry['hydraulic_links'][ordinal]
            for key in ('link_id', 'from_cell_id', 'to_cell_id', 'length_m'):
                _i15_require(face[key] == link[key], 'original hydraulic link substituted')
            _i15_require(face['additional_step_loss'] is None and face['roughness_manning'] == 0.035 and (face['roughness_source_cell_ids'] == [link['from_cell_id'], link['to_cell_id']]) and all((cells[key]['roughness_manning'] == 0.035 for key in face['roughness_source_cell_ids'])), 'undeclared current resistance parameters')
            if ordinal in (0, 17):
                kind = 'sink' if ordinal == 0 else 'spring'
                port = _x28_read(attachments['attachments'][kind]['canonical_port_pin'])
                station = vdm['stations'][0 if ordinal == 0 else -1]
                portal_report = coupled_audit['portal_reports'][kind]
                _i15_require(portal_report['verified'] is True and portal_report['two_sided_complete_port_verified'] is True and (portal_report['port_identity_sha256'] == port['identity_sha256']) and (portal_report['canonical_port_pin'] == attachments['attachments'][kind]['canonical_port_pin']), 'current per-portal audit identity differs')
                check_plane(face['plane'], station['origin_xyz_m'], port['flow_unit_xz'], common)
                canonical = source_canonical_floor(port, face['plane'])
                binding = face['shared_port_binding']
                attachment = attachments['attachments'][kind]
                _i15_require(binding == {'kind': kind, 'canonical_port_pin': attachment['canonical_port_pin'], 'surface_node_pin': attachment['surface_node_pin'], 'port_identity_sha256': port['identity_sha256'], 'actual_complete_port_proof': attachment['actual_complete_port_proof'], 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'canonical_profile_uv_m': canonical, 'hydraulic_boundary_certified': False}, 'current whole canonical profile differs')
                evidence = face['aperture']['canonical_two_sided_evidence']
                _i15_require(evidence['composition_audit_pin'] == inputs['composition_audit'] and evidence['two_sided_complete_port_verified'] is True and (evidence['composition_portal_connection'] == composition['portal_connections'][kind]) and (evidence['no_endcap_deleted'] is True), 'current two-sided face evidence missing')
            else:
                first, second = vdm['stations'][ordinal - 1:ordinal + 1]
                _i15_require((link['from_cell_id'], link['to_cell_id']) == (first['station_id'], second['station_id']) and face['shared_port_binding'] is None and (face['aperture']['canonical_two_sided_evidence'] is None), 'current route binding differs')
                start, end = (_i15_np.asarray(first['origin_xyz_m']), _i15_np.asarray(second['origin_xyz_m']))
                check_plane(face['plane'], (start + end) / 2, (end - start)[[0, 2]], common)
                canonical = None
            _i15_require(set(face['solid_slices']) == set(solids), 'current slice census differs')
            shapes = {role: audit_exact_slice(face['solid_slices'][role], solid, face['plane'], pins[role])[0] for role, solid in solids.items()}
            role_lines = [audit_role_slice(source, face['plane'], original, original_pin, vdm, prisms, composition['surface_prisms_pin']) for source in face['source_role_slices']]
            if canonical is not None:
                _i15_require(whole_line_supported(LineString(canonical), shapes['cutter'].boundary), 'current canonical floor not an actual face boundary')
            boundary = audit_boundary(face['aperture'], shapes, face['solid_slices'], role_lines, face['plane'])
            reports.append({'face_id': face['face_id'], 'link_id': link['link_id'], 'aperture': boundary})
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append({'face_id': face.get('face_id'), 'error': str(error)})
    _i15_require(not errors and len(reports) == 18, 'current face audit failed: ' + str(errors))
    return {'schema': 'td-hybrid-current-face-audit-v1', 'status': 'passed', 'errors': [], 'faces_pin': pin, 'inputs': inputs, 'reports': reports, 'verified_face_count': len(reports), 'composition_identity_sha256': composition['identity_sha256'], 'actual_slice_sources_verified': True, 'two_sided_canonical_ports_verified': True, 'interval_winding_queries': interval_queries, 'interval_runtime': _i15_runtime_identity(), 'hydraulic_solved': False, 'publishable': False}
ROOT = _i16_Path(__file__).resolve().parents[1]
_i16_sys.path.insert(0, str(ROOT))
AUDIT_SCHEMA = 'td-hybrid-cave-geometry-independent-audit-v1'
FROZEN_CODE = {'terrain_pipeline/hybrid_cave_geometry.py': '44c978a841c7b3da3e0052e825e6ca641f8c36b746ddffac26be57076e91408c', 'tools/prepare_hybrid_cave_geometry.py': '104d525135e081d14c5d0c1728d70d47391bf4707375c6d14ca0928a75e8e6a9', 'tests/test_hybrid_cave_geometry.py': 'e1b5b3c7e48716cd31c45294dcca89cdb81bb852e21656c42812b6379b6bc68c'}
POLICY = {'version': 'local-rock-boolean-multichart-v1', 'terrain': 'original_native_bilinear_minus_independently_passed_saved_affine_cut_fans', 'solid': 'sampled_piecewise_planar_top_closed_sides_bottom_not_native_exact_not_fine_replacement', 'excavation': 'Mesh64_local_origin_closed_rock_minus_closed_derived_cutter_actual_volume', 'geology': 'generated_hermite_route_sine_squared_burial_not_surveyed', 'portals': 'immutable_complete_native_floor_with_engineered_ceiling_surface_ramp_openings', 'vdm': 'new_transverse_and_vertical_multichart_reference_plus_displacement_not_old_metric_vdm', 'water': 'not_generated_solid_banks_distinct_from_free_water', 'protection': 'unknown_protected_unselected_or_wet_native_support_refused_without_clamping', 'hydraulics': 'final_actual_ring_storage_sections_engineering_pressure_slot_no_solver'}

def audit(geometry_pin):
    started = _i16_time.perf_counter()
    geometry = _i16_read(geometry_pin)
    _i16_require(geometry['schema'] == 'td-hybrid-river-geometry-v1' and geometry['status'] == 'candidate' and (geometry['rejection_reasons'] == []) and (geometry['sampled_not_native_exact'] is True) and (geometry['fine15_replaced'] is False), 'candidate local sampled geometry scope differs')
    _i16_require(geometry['policy'] == POLICY and geometry['policy_identity_sha256'] == _i16_digest(POLICY) and (geometry['parameters_identity_sha256'] == _i16_digest(geometry['parameters'])), 'geometry policy/parameters identity differs')
    for flag in ('independent_audit_passed', 'hydraulic_solved', 'hydraulic_ready', 'free_water_surface_generated', 'natural_outlet_certified', 'full_network_verified'):
        _i16_require(geometry[flag] is False, 'geometry prematurely promoted capability: ' + flag)
    for pin in geometry['inputs'].values():
        _i16_checked_path(pin)
    for code in (geometry['code_sha256'], geometry['readonly_dependency_code_sha256']):
        for name, sha in code.items():
            _i16_checked_path({'path': str(ROOT / name), 'sha256': sha})
    _i16_require(geometry['code_sha256'] == FROZEN_CODE, 'frozen actual geometry implementation differs')
    _i16_require(geometry['runtime']['manifold3d'] == '3.5.4', 'geometry not frozen Mesh64 runtime')
    parameters = geometry['parameters']
    _i16_require(0.175 <= parameters['rock_spacing_m'] <= 2.0 and type(parameters['stations']) is int and (9 <= parameters['stations'] <= 33) and all((_i16_math.isfinite(value) and value > 0 for value in parameters.values())), 'local engineering parameter bounds differ')
    graph = _i16_read(geometry['inputs']['graph'])
    _i16_require(graph['identity_sha256'] == geometry['graph_identity_sha256'] and all((geometry['inputs'].get(key) == pin for key, pin in graph['inputs'].items())), 'geometry graph parent binding differs')
    graph_result, portals, native = _i16_audit_typed_graph(graph)
    compact = _i16_read(graph['inputs']['fine_compact_fans'])
    bed = _i16_IndependentBed(native, compact)
    _i16_require(set(geometry['mesh_pins']) == {'rock_before', 'cutter', 'rock_after', 'removed'}, 'solid mesh pin census differs')
    records, solids = ({}, {})
    origin = None
    peak = _i16_check_memory()
    for name, pin in geometry['mesh_pins'].items():
        record = _i16_read(pin)
        _i16_require(record['schema'] == 'td-hybrid-local-solid-mesh-v1' and record['role'] == name and (record['sampled_not_native_exact'] is True), 'saved solid role/schema/scope differs')
        local_origin = _i16_np.asarray(record['local_origin_xyz_m'], float)
        _i16_require(local_origin.shape == (3,) and _i16_np.isfinite(local_origin).all(), 'invalid local origin')
        if origin is None:
            origin = local_origin
        _i16_require(_i16_np.array_equal(origin, local_origin), 'Boolean solid local origins differ')
        solid = _i16_Solid(record['vertices_local_xyz_m'], record['triangles'], name)
        _i16_compare(record['signed_volume_m3'], solid.signed_volume, 'saved signed solid volume', atol=1e-07, rtol=1e-09)
        records[name], solids[name] = (record, solid)
        peak = max(peak, _i16_check_memory())
    _i16_compare(origin, portals['sink']['node']['xyz_m'], 'fixed local origin at canonical sink')
    vdm = _i16_read(geometry['vdm_pin'])
    vdm_result = _i16_audit_vdm(vdm, solids['cutter'], origin, portals)
    _i16_require(len(vdm['stations']) == parameters['stations'], 'explicit station parameter differs')
    sampling = _i16_read(geometry['source_sampling_pin'])
    source_result = _i16_audit_source_sampling(sampling, solids['rock_before'], origin, bed, parameters['rock_spacing_m'])
    boolean = _i16_boolean_evidence(solids['rock_before'], solids['cutter'], solids['rock_after'], solids['removed'])
    actual_material = geometry['actual_solid_material']
    for key, value in (('rock_before_m3', boolean['rock_volume_m3']), ('rock_after_m3', boolean['actual_rock_volume_m3']), ('excavated_rock_m3', boolean['excavated_volume_m3']), ('exported_excavated_rock_m3', boolean['excavated_volume_m3']), ('signed_residual_m3', boolean['rock_volume_m3'] - boolean['actual_rock_volume_m3'] - boolean['excavated_volume_m3'])):
        _i16_compare(actual_material[key], value, 'actual rock material ' + key, atol=1e-07, rtol=1e-09)
    _i16_require(actual_material['fill_rock_m3'] == 0.0, 'actual rock adds fill')
    attachment_record = _i16_read(geometry['surface_attachments_pin'])
    attachments = _i16_audit_surface_attachments(attachment_record, geometry, portals, bed, compact)
    sections = _i16_audit_hydraulic_sections(geometry, vdm, solids['rock_before'], sampling, origin, bed)
    path = _i16_np.asarray(geometry['air_path_xyz_m'], float)
    _i16_require(path.shape == (len(vdm['stations']), 3), 'saved station air path census differs')
    for point, station in zip(path, vdm['stations']):
        station_origin = _i16_np.asarray(station['origin_xyz_m'])
        _i16_compare(point[[0, 2]], station_origin[[0, 2]], 'air route references actual VDM station horizontal position')
        floor = _i16_np.asarray(station['derived_ring_xyz_m'])[:station['floor_vertex_count']]
        offsets = (floor[:, [0, 2]] - station_origin[[0, 2]]) @ _i16_np.asarray(station['transverse_unit_xz'])
        _i16_require(_i16_np.all(_i16_np.diff(offsets) > 0.0), 'air station floor not ordered')
        _i16_require(_i16_np.interp(0.0, offsets, floor[:, 1]) < point[1] < min(_i16_np.asarray(station['derived_ring_xyz_m'])[-2:, 1]), 'saved air station not in actual profile interior')
    segments = geometry['air_path_segments']
    _i16_require(len(segments) == len(path) - 1, 'saved air route segments omitted')
    for ordinal, segment in enumerate(segments):
        _i16_compare(segment['from_xyz_m'], path[ordinal], 'air segment origin')
        _i16_compare(segment['to_xyz_m'], path[ordinal + 1], 'air segment target')
        _i16_require(segment['rock_after_hits'] == [], 'generator reported blocked air segment')
    openings = geometry['portal_opening_witnesses']
    _i16_require(set(openings) == {'sink', 'spring'}, 'portal aperture witness census differs')
    opening_segments = []
    station_ids = [station['station_id'] for station in vdm['stations']]
    for kind, endpoint in (('sink', 0), ('spring', -1)):
        portal_binding = geometry['portal_bindings'][kind]
        _i16_require(portal_binding['port_arc_id'] == portals[kind]['port']['arc_id'] and portal_binding['port_identity_sha256'] == portals[kind]['port']['identity_sha256'] and (portal_binding['immutable_station_id'] == vdm['stations'][endpoint]['station_id']) and (portal_binding['full_native_floor_preserved'] is True) and (portal_binding['hydraulic_boundary_certified'] is False), 'actual canonical portal binding differs')
        _i16_require(geometry['portal_sections'][kind]['pieces'] == portals[kind]['pieces'] and geometry['portal_sections'][kind]['canonical_profile'] == portals[kind]['port']['profile'], 'actual portal complete native function differs')
        witness = openings[kind]
        _i16_require(witness['station_id'] in station_ids and witness['opening_kind'] == 'actual_terrain_top_ramp_aperture_not_entire_planar_port_cap' and witness['rock_before_hits'] and (witness['rock_after_hits'] == []), 'actual ramp aperture incorrectly identified')
        index = station_ids.index(witness['station_id'])
        _i16_require(0 < index < len(station_ids) // 2 if kind == 'sink' else len(station_ids) // 2 < index < len(station_ids) - 1, 'aperture associated with wrong portal half')
        _i16_compare(witness['inside_xyz_m'], path[index], 'aperture joins saved station air route')
        point = _i16_np.asarray(witness['inside_xyz_m'])
        bed.verify(point[[0, 2]], witness['source_bed_witness'])
        _i16_require(witness['above_xyz_m'][0] == point[0] and witness['above_xyz_m'][2] == point[2] and (witness['above_xyz_m'][1] > witness['source_bed_witness']['derived_bed_m'] > point[1]), 'aperture exterior/source-bed ordering differs')
        opening_segments.append((_i16_np.asarray(witness['above_xyz_m']) - origin, point - origin))
    air = _i16_saved_air_route(solids['rock_before'], solids['cutter'], solids['rock_after'], path - origin, opening_segments)
    distances = _i16_np.linalg.norm(_i16_np.diff(_i16_np.asarray([station['origin_xyz_m'] for station in vdm['stations']]), axis=0), axis=1)
    _i16_compare(geometry['conduit_length_m'], _i16_math.fsum(distances.tolist()), 'saved conduit station length')
    resource = geometry['resource']
    _i16_require(resource['top_grid_count'] == sampling['top_vertex_count'] <= resource['hard_grid_count'] == 300000 and resource['hard_rss_bytes'] == _i16_MAX_RSS and (resource['hard_file_bytes'] == _i16_MAX_BYTES), 'explicit local geometry resources differ')
    result = {'schema': AUDIT_SCHEMA, 'status': 'passed', 'errors': [], 'geometry': geometry_pin, 'geometry_sha256': geometry_pin['sha256'], 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': graph['identity_sha256'], 'inputs': geometry['inputs'], 'mesh_pins': geometry['mesh_pins'], 'vdm_pin': geometry['vdm_pin'], 'source_sampling_pin': geometry['source_sampling_pin'], 'surface_attachments_pin': geometry['surface_attachments_pin'], 'policy_identity_sha256': geometry['policy_identity_sha256'], 'parameters_identity_sha256': geometry['parameters_identity_sha256'], 'typed_graph': graph_result, 'source_sampling': source_result, 'vdm': vdm_result, 'actual_boolean': boolean, 'surface_attachments': attachments, 'actual_air_route': air, 'actual_hydraulic_sections_verified': True, 'actual_portal_connections_verified': True, 'section_classification': sections, 'portal_scope': 'two actual terrain ramp apertures tied to immutable canonical floors, not complete planar cap/whole-bank opening certification', 'hydraulic_exchange_scope': 'actual open-ramp to covered-core transitions, not automatically the canonical midpoint portals', 'source_native_function_verified_at_saved_samples': True, 'sampled_top_not_native_exact': True, 'hydraulic_solved': False, 'three_dimensional_flow_solved': False, 'natural_outlet_certified': False, 'full_network_verified': False, 'fine15_replaced': False, 'free_water_surface_generated': False, 'scope': 'bounded sampled local rock Boolean, actual openings, saved VDM and explicit open/closed engineering sections only', 'runtime_pins': {str(path.resolve()): _i16_file_sha256(path) for path in _i16_MANIFOLD_DIRECTORY.glob('*.pyd')}, 'resource': {'actual_peak_audit_rss_bytes': max(peak, _i16_check_memory()), 'max_rss_bytes': _i16_MAX_RSS, 'max_file_bytes': _i16_MAX_BYTES, 'max_vertices_per_solid': 100000, 'max_faces_per_solid': 200000, 'solver_calls': 0, 'elapsed_s': _i16_time.perf_counter() - started}}
    return result

def _entry_audit_hybrid_cave_geometry():
    parser = _i16_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=_i16_Path, required=True)
    parser.add_argument('--geometry-sha256', required=True)
    parser.add_argument('--output', type=_i16_Path, required=True)
    parser.add_argument('--audit-schema', default=AUDIT_SCHEMA, choices=[AUDIT_SCHEMA])
    args = parser.parse_args()
    output = args.output.resolve()
    _i16_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    result = audit({'path': str(args.geometry.resolve()), 'sha256': args.geometry_sha256})
    result['audit_code_sha256'] = {name: _i16_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tools/hybrid_cave_saved_audit.py', 'tests/test_hybrid_geometry_saved_audit.py', 'tools/audit_td_shared_channel_fine.py', 'tools/td_shared_channel_fine_saved_audit.py')}
    result['identity_sha256'] = _i16_digest(result)
    payload = _i16_json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i16_require(len(payload) <= _i16_MAX_BYTES, 'audit exceeds 64MiB output budget')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with _i16_tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = _i16_Path(stream.name)
            stream.write(payload)
            stream.flush()
            _i16_os.fsync(stream.fileno())
        _i16_os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(_i16_json.dumps({'status': result['status'], 'actual_boolean': result['actual_boolean'], 'section_classification': result['section_classification']}))
_i17_sys.path.insert(0, str(ROOT))
AUDIT_HYBRID_CAVE_GEOMETRY_MECHANISM_2_FROZEN_CODE = {'terrain_pipeline/hybrid_cave_geometry.py': 'dd839163651239ba358b74b79e41acf6831487a6638e980483f9825243311b55', 'tools/prepare_hybrid_cave_geometry.py': '104d525135e081d14c5d0c1728d70d47391bf4707375c6d14ca0928a75e8e6a9', 'tests/test_hybrid_cave_geometry.py': '98c8c229432c0e5a4819d6d8ba482da722b45a825c3e43d73614e30b9f8d4b27'}

def audit_hybrid_cave_geometry_mechanism_2_audit(geometry_pin):
    started = _i17_time.perf_counter()
    geometry = _i17_read(geometry_pin)
    _i17_require(geometry['schema'] == 'td-hybrid-river-geometry-v1' and geometry['status'] == 'candidate' and (geometry['rejection_reasons'] == []) and (geometry['sampled_not_native_exact'] is True) and (geometry['fine15_replaced'] is False), 'candidate local sampled geometry scope differs')
    _i17_require(geometry['policy'] == POLICY and geometry['policy_identity_sha256'] == _i17_digest(POLICY) and (geometry['parameters_identity_sha256'] == _i17_digest(geometry['parameters'])), 'geometry policy/parameters identity differs')
    for flag in ('independent_audit_passed', 'hydraulic_solved', 'hydraulic_ready', 'free_water_surface_generated', 'natural_outlet_certified', 'full_network_verified'):
        _i17_require(geometry[flag] is False, 'geometry prematurely promoted capability: ' + flag)
    for pin in geometry['inputs'].values():
        _i17_checked_path(pin)
    for code in (geometry['code_sha256'], geometry['readonly_dependency_code_sha256']):
        for name, sha in code.items():
            _i17_checked_path({'path': str(ROOT / name), 'sha256': sha})
    _i17_require(geometry['code_sha256'] == AUDIT_HYBRID_CAVE_GEOMETRY_MECHANISM_2_FROZEN_CODE, 'frozen actual geometry implementation differs')
    _i17_require(geometry['runtime']['manifold3d'] == '3.5.4', 'geometry not frozen Mesh64 runtime')
    parameters = geometry['parameters']
    _i17_require(0.175 <= parameters['rock_spacing_m'] <= 2.0 and type(parameters['stations']) is int and (9 <= parameters['stations'] <= 33) and all((_i17_math.isfinite(value) and value > 0 for value in parameters.values())), 'local engineering parameter bounds differ')
    graph = _i17_read(geometry['inputs']['graph'])
    _i17_require(graph['identity_sha256'] == geometry['graph_identity_sha256'] and all((geometry['inputs'].get(key) == pin for key, pin in graph['inputs'].items())), 'geometry graph parent binding differs')
    graph_result, portals, native = _i17_audit_typed_graph(graph)
    compact = _i17_read(graph['inputs']['fine_compact_fans'])
    bed = _i17_IndependentBed(native, compact)
    _i17_require(set(geometry['mesh_pins']) == {'rock_before', 'cutter', 'rock_after', 'removed'}, 'solid mesh pin census differs')
    records, solids = ({}, {})
    origin = None
    peak = _i17_check_memory()
    for name, pin in geometry['mesh_pins'].items():
        record = _i17_read(pin)
        _i17_require(record['schema'] == 'td-hybrid-local-solid-mesh-v1' and record['role'] == name and (record['sampled_not_native_exact'] is True), 'saved solid role/schema/scope differs')
        local_origin = _i17_np.asarray(record['local_origin_xyz_m'], float)
        _i17_require(local_origin.shape == (3,) and _i17_np.isfinite(local_origin).all(), 'invalid local origin')
        if origin is None:
            origin = local_origin
        _i17_require(_i17_np.array_equal(origin, local_origin), 'Boolean solid local origins differ')
        solid = _i17_Solid(record['vertices_local_xyz_m'], record['triangles'], name)
        _i17_compare(record['signed_volume_m3'], solid.signed_volume, 'saved signed solid volume', atol=1e-07, rtol=1e-09)
        records[name], solids[name] = (record, solid)
        peak = max(peak, _i17_check_memory())
    _i17_compare(origin, portals['sink']['node']['xyz_m'], 'fixed local origin at canonical sink')
    vdm = _i17_read(geometry['vdm_pin'])
    vdm_result = _i17_audit_vdm(vdm, solids['cutter'], origin, portals)
    _i17_require(len(vdm['stations']) == parameters['stations'], 'explicit station parameter differs')
    sampling = _i17_read(geometry['source_sampling_pin'])
    source_result = _i17_audit_source_sampling(sampling, solids['rock_before'], origin, bed, parameters['rock_spacing_m'])
    boolean = _i17_boolean_evidence(solids['rock_before'], solids['cutter'], solids['rock_after'], solids['removed'])
    actual_material = geometry['actual_solid_material']
    for key, value in (('rock_before_m3', boolean['rock_volume_m3']), ('rock_after_m3', boolean['actual_rock_volume_m3']), ('excavated_rock_m3', boolean['excavated_volume_m3']), ('exported_excavated_rock_m3', boolean['excavated_volume_m3']), ('signed_residual_m3', boolean['rock_volume_m3'] - boolean['actual_rock_volume_m3'] - boolean['excavated_volume_m3'])):
        _i17_compare(actual_material[key], value, 'actual rock material ' + key, atol=1e-07, rtol=1e-09)
    _i17_require(actual_material['fill_rock_m3'] == 0.0, 'actual rock adds fill')
    attachment_record = _i17_read(geometry['surface_attachments_pin'])
    attachments = _i17_audit_surface_attachments(attachment_record, geometry, portals, bed, compact)
    sections = _i17_audit_hydraulic_sections(geometry, vdm, solids['rock_before'], sampling, origin, bed)
    path = _i17_np.asarray(geometry['air_path_xyz_m'], float)
    _i17_require(path.shape == (len(vdm['stations']), 3), 'saved station air path census differs')
    for point, station in zip(path, vdm['stations']):
        station_origin = _i17_np.asarray(station['origin_xyz_m'])
        _i17_compare(point[[0, 2]], station_origin[[0, 2]], 'air route references actual VDM station horizontal position')
        floor = _i17_np.asarray(station['derived_ring_xyz_m'])[:station['floor_vertex_count']]
        offsets = (floor[:, [0, 2]] - station_origin[[0, 2]]) @ _i17_np.asarray(station['transverse_unit_xz'])
        _i17_require(_i17_np.all(_i17_np.diff(offsets) > 0.0), 'air station floor not ordered')
        _i17_require(_i17_np.interp(0.0, offsets, floor[:, 1]) < point[1] < min(_i17_np.asarray(station['derived_ring_xyz_m'])[-2:, 1]), 'saved air station not in actual profile interior')
    segments = geometry['air_path_segments']
    _i17_require(len(segments) == len(path) - 1, 'saved air route segments omitted')
    for ordinal, segment in enumerate(segments):
        _i17_compare(segment['from_xyz_m'], path[ordinal], 'air segment origin')
        _i17_compare(segment['to_xyz_m'], path[ordinal + 1], 'air segment target')
        _i17_require(segment['rock_after_hits'] == [], 'generator reported blocked air segment')
    openings = geometry['portal_opening_witnesses']
    _i17_require(set(openings) == {'sink', 'spring'}, 'portal aperture witness census differs')
    opening_segments = []
    station_ids = [station['station_id'] for station in vdm['stations']]
    for kind, endpoint in (('sink', 0), ('spring', -1)):
        portal_binding = geometry['portal_bindings'][kind]
        _i17_require(portal_binding['port_arc_id'] == portals[kind]['port']['arc_id'] and portal_binding['port_identity_sha256'] == portals[kind]['port']['identity_sha256'] and (portal_binding['immutable_station_id'] == vdm['stations'][endpoint]['station_id']) and (portal_binding['full_native_floor_preserved'] is True) and (portal_binding['hydraulic_boundary_certified'] is False), 'actual canonical portal binding differs')
        _i17_require(geometry['portal_sections'][kind]['pieces'] == portals[kind]['pieces'] and geometry['portal_sections'][kind]['canonical_profile'] == portals[kind]['port']['profile'], 'actual portal complete native function differs')
        witness = openings[kind]
        _i17_require(witness['station_id'] in station_ids and witness['opening_kind'] == 'actual_terrain_top_ramp_aperture_not_entire_planar_port_cap' and witness['rock_before_hits'] and (witness['rock_after_hits'] == []), 'actual ramp aperture incorrectly identified')
        index = station_ids.index(witness['station_id'])
        _i17_require(0 < index < len(station_ids) // 2 if kind == 'sink' else len(station_ids) // 2 < index < len(station_ids) - 1, 'aperture associated with wrong portal half')
        _i17_compare(witness['inside_xyz_m'], path[index], 'aperture joins saved station air route')
        point = _i17_np.asarray(witness['inside_xyz_m'])
        bed.verify(point[[0, 2]], witness['source_bed_witness'])
        _i17_require(witness['above_xyz_m'][0] == point[0] and witness['above_xyz_m'][2] == point[2] and (witness['above_xyz_m'][1] > witness['source_bed_witness']['derived_bed_m'] > point[1]), 'aperture exterior/source-bed ordering differs')
        opening_segments.append((_i17_np.asarray(witness['above_xyz_m']) - origin, point - origin))
    air = _i17_saved_air_route(solids['rock_before'], solids['cutter'], solids['rock_after'], path - origin, opening_segments)
    distances = _i17_np.linalg.norm(_i17_np.diff(_i17_np.asarray([station['origin_xyz_m'] for station in vdm['stations']]), axis=0), axis=1)
    _i17_compare(geometry['conduit_length_m'], _i17_math.fsum(distances.tolist()), 'saved conduit station length')
    resource = geometry['resource']
    _i17_require(resource['top_grid_count'] == sampling['top_vertex_count'] <= resource['hard_grid_count'] == 300000 and resource['hard_rss_bytes'] == _i17_MAX_RSS and (resource['hard_file_bytes'] == _i17_MAX_BYTES), 'explicit local geometry resources differ')
    result = {'schema': AUDIT_SCHEMA, 'audit_implementation_version': 'generator-bool-boundary-v2', 'status': 'passed', 'errors': [], 'geometry': geometry_pin, 'geometry_sha256': geometry_pin['sha256'], 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': graph['identity_sha256'], 'inputs': geometry['inputs'], 'mesh_pins': geometry['mesh_pins'], 'vdm_pin': geometry['vdm_pin'], 'source_sampling_pin': geometry['source_sampling_pin'], 'surface_attachments_pin': geometry['surface_attachments_pin'], 'policy_identity_sha256': geometry['policy_identity_sha256'], 'parameters_identity_sha256': geometry['parameters_identity_sha256'], 'typed_graph': graph_result, 'source_sampling': source_result, 'vdm': vdm_result, 'actual_boolean': boolean, 'surface_attachments': attachments, 'actual_air_route': air, 'actual_hydraulic_sections_verified': True, 'actual_portal_connections_verified': True, 'section_classification': sections, 'portal_scope': 'two actual terrain ramp apertures tied to immutable canonical floors, not complete planar cap/whole-bank opening certification', 'hydraulic_exchange_scope': 'actual open-ramp to covered-core transitions, not automatically the canonical midpoint portals', 'source_native_function_verified_at_saved_samples': True, 'sampled_top_not_native_exact': True, 'hydraulic_solved': False, 'three_dimensional_flow_solved': False, 'natural_outlet_certified': False, 'full_network_verified': False, 'fine15_replaced': False, 'free_water_surface_generated': False, 'scope': 'bounded sampled local rock Boolean, actual openings, saved VDM and explicit open/closed engineering sections only', 'runtime_pins': {str(path.resolve()): _i17_file_sha256(path) for path in _i17_MANIFOLD_DIRECTORY.glob('*.pyd')}, 'resource': {'actual_peak_audit_rss_bytes': max(peak, _i17_check_memory()), 'max_rss_bytes': _i17_MAX_RSS, 'max_file_bytes': _i17_MAX_BYTES, 'max_vertices_per_solid': 100000, 'max_faces_per_solid': 200000, 'solver_calls': 0, 'elapsed_s': _i17_time.perf_counter() - started}}
    return result

def _entry_audit_hybrid_cave_geometry_v2():
    parser = _i17_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=_i17_Path, required=True)
    parser.add_argument('--geometry-sha256', required=True)
    parser.add_argument('--output', type=_i17_Path, required=True)
    parser.add_argument('--audit-schema', default=AUDIT_SCHEMA, choices=[AUDIT_SCHEMA])
    args = parser.parse_args()
    output = args.output.resolve()
    _i17_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    result = audit_hybrid_cave_geometry_mechanism_2_audit({'path': str(args.geometry.resolve()), 'sha256': args.geometry_sha256})
    result['audit_code_sha256'] = {name: _i17_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tools/hybrid_cave_saved_audit.py', 'tests/test_hybrid_geometry_saved_audit.py', 'tools/audit_td_shared_channel_fine.py', 'tools/td_shared_channel_fine_saved_audit.py')}
    result['identity_sha256'] = _i17_digest(result)
    payload = _i17_json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i17_require(len(payload) <= _i17_MAX_BYTES, 'audit exceeds 64MiB output budget')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with _i17_tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = _i17_Path(stream.name)
            stream.write(payload)
            stream.flush()
            _i17_os.fsync(stream.fileno())
        _i17_os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(_i17_json.dumps({'status': result['status'], 'actual_boolean': result['actual_boolean'], 'section_classification': result['section_classification']}))
_i18_sys.path.insert(0, str(ROOT))
AUDIT_HYBRID_RIVER_FACES_AUDIT_SCHEMA = 'td-hybrid-river-faces-independent-audit-v1'
PLANE_TOLERANCE_M = 1e-08
GEOMETRY_SHA256 = '3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593'
GEOMETRY_AUDIT_SHA256 = '703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364'
GRAPH_SHA256 = '279d632e6f471c2629a37d7d6954adbcb734be19278e009eb352c9852593846a'
FROZEN_FACE_CODE = {'terrain_pipeline/hybrid_river_faces.py': '73ae18fc30afabb70ed4b3d1c043606141e560c7d0d818f38053ac018b5acc8a', 'tools/prepare_hybrid_river_faces.py': 'e4c7051473aaaa5dbe79baa5314fc4fe52e68af7e9197a8871eb68272b82fb2e', 'tests/test_hybrid_river_faces.py': 'a329e3850f7e211dbf07c756263650d0f3d1b7b3848f1ee7a8c833fe52b290e6'}
AUDIT_HYBRID_RIVER_FACES_POLICY = {'version': 'actual_saved_solid_link_faces-v1', 'coordinates': 'common_local_XYZ_metres_Y_vertical_face_u_Ylocal', 'gallery_plane': 'adjacent_station_origin_midpoint_normal_actual_XZ_station_difference', 'attachment_plane': 'exact_immutable_canonical_gallery_0_16_with_complete_saved_half_arm_proof', 'geometry': 'actual_Mesh64_plane_slices_not_minimum_of_endpoint_sections', 'wall': 'actual_rock_after_boundary_separate_from_free_surface_engineering_wall_and_artificial_cutter_cap', 'open': 'saved_actual_cut_floor_with_explicit_engineering_vertical_extensions_not_a_closed_cutter_roof', 'slot': 'storage_only_never_enlarges_face', 'unknown': 'missing_geometry_or_multiple_disconnected_apertures_refused_never_zero_flow_closed_wall', 'flow': 'not_computed_no_step_loss_no_new_roughness_original_link_length'}

def triangle_plane_segments(vertices, triangles, origin, normal, transverse):
    vertices = _i18_np.asarray(vertices, dtype=float)
    triangles = _i18_np.asarray(triangles)
    origin, normal, transverse = (_i18_np.asarray(value, dtype=float) for value in (origin, normal, transverse))
    _i18_require(vertices.ndim == 2 and vertices.shape[1] == 3 and _i18_np.isfinite(vertices).all(), 'invalid source vertices')
    _i18_require(triangles.ndim == 2 and triangles.shape[1] == 3 and _i18_np.issubdtype(triangles.dtype, _i18_np.integer) and (triangles.min() >= 0) and (triangles.max() < len(vertices)), 'invalid source triangle references')
    _i18_require(all((value.shape == (3,) and _i18_np.isfinite(value).all() for value in (origin, normal, transverse))), 'invalid face plane frame')
    _i18_compare(_i18_np.linalg.norm(normal), 1.0, 'unit face normal')
    _i18_compare(_i18_np.linalg.norm(transverse), 1.0, 'unit transverse axis')
    _i18_compare(normal[1], 0.0, 'horizontal flow normal')
    _i18_compare(transverse[1], 0.0, 'horizontal transverse axis')
    _i18_compare(normal @ transverse, 0.0, 'orthogonal face axes')
    intersections, coplanar = ({}, [])
    for ordinal, indices in enumerate(triangles):
        points = vertices[indices]
        distances = (points - origin) @ normal
        if _i18_np.all(_i18_np.abs(distances) <= PLANE_TOLERANCE_M):
            coplanar.append(ordinal)
            continue
        if distances.min() > PLANE_TOLERANCE_M or distances.max() < -PLANE_TOLERANCE_M:
            continue
        crossings = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            if abs(distances[first]) <= PLANE_TOLERANCE_M:
                crossings.append(points[first])
            if distances[first] * distances[second] < 0:
                fraction = distances[first] / (distances[first] - distances[second])
                crossings.append(points[first] + fraction * (points[second] - points[first]))
        unique = []
        for point in crossings:
            if all((_i18_np.linalg.norm(point - previous) > PLANE_TOLERANCE_M for previous in unique)):
                unique.append(point)
        if len(unique) >= 2:
            pairs = [(_i18_np.linalg.norm(first - second), first, second) for offset, first in enumerate(unique) for second in unique[offset + 1:]]
            length, first, second = max(pairs, key=lambda item: item[0])
            if length > PLANE_TOLERANCE_M:
                intersections[ordinal] = _i18_np.asarray([[(point - origin) @ transverse, point[1]] for point in (first, second)])
    return (intersections, coplanar)

def polygons_geometry(contours):
    from shapely.geometry import GeometryCollection
    from shapely.geometry import Polygon
    result = GeometryCollection()
    for contour in contours:
        points = _i18_np.asarray(contour, dtype=float)
        _i18_require(points.ndim == 2 and points.shape[1] == 2 and (len(points) >= 3) and _i18_np.isfinite(points).all(), 'invalid saved slice contour')
        polygon = Polygon(points)
        _i18_require(polygon.is_valid and polygon.area > 0.0, 'invalid/self-intersecting saved slice polygon')
        result = result.symmetric_difference(polygon)
    return result

def independently_slice(solid, origin, normal, transverse):
    library = _i18_manifold_library()
    transform = _i18_np.asarray([_i18_np.append(transverse, -_i18_np.dot(transverse, origin)), [0.0, 1.0, 0.0, 0.0], _i18_np.append(normal, -_i18_np.dot(normal, origin))])
    result = polygons_geometry(solid.manifold(library).transform(transform).slice(0.0).to_polygons())
    from shapely.geometry import Polygon
    _, coplanar = triangle_plane_segments(solid.vertices, solid.triangles, origin, normal, transverse)
    for ordinal in coplanar:
        points = solid.points[ordinal]
        polygon = Polygon(_i18_np.column_stack(((points - origin) @ transverse, points[:, 1])))
        if polygon.area > 1e-08:
            result = result.union(polygon)
    return result

def saved_slice_geometry(record):
    from shapely.geometry import GeometryCollection
    from shapely.geometry import Polygon
    _i18_require(len(record['polygons_uv_m']) == len(record['holes_uv_m']), 'slice hole ownership mismatch')
    result = GeometryCollection()
    for exterior, holes in zip(record['polygons_uv_m'], record['holes_uv_m']):
        polygon = Polygon(exterior, holes)
        _i18_require(polygon.is_valid and polygon.area > 0.0, 'invalid saved slice with holes')
        _i18_require(result.intersection(polygon).area <= 1e-08, 'overlapping saved slice components')
        result = result.union(polygon)
    return result

def audit_slice(record, solid, frame, pin):
    from shapely.geometry import LineString
    from shapely.geometry import Polygon
    _i18_require(record['mesh_pin'] == pin and record['coordinate_convention'] == frame['coordinate_convention'], 'slice source/frame binding differs')
    origin, normal, transverse = [_i18_np.asarray(frame[key], float) for key in ('origin_local_xyz_m', 'normal_local_xyz', 'transverse_unit_xyz')]
    segments, coplanar = triangle_plane_segments(solid.vertices, solid.triangles, origin, normal, transverse)
    saved = record['triangle_segments']
    _i18_require(len({item['triangle_index'] for item in saved}) == len(saved) and {item['triangle_index'] for item in saved} == set(segments), 'incomplete/duplicate triangle-plane support')
    for item in saved:
        ordinal = item['triangle_index']
        _i18_require(type(ordinal) is int and item['vertex_indices'] == solid.triangles[ordinal].tolist(), 'triangle source references differ')
        expected = LineString(segments[ordinal])
        points = _i18_np.asarray(item['points_uv_m'], float)
        _i18_require(points.shape == (2, 2) and _i18_np.isfinite(points).all(), 'invalid saved plane segment')
        _i18_require(expected.hausdorff_distance(LineString(points)) <= PLANE_TOLERANCE_M, 'fabricated triangle-plane segment')
        xyz = origin + points[:, :1] * transverse
        xyz[:, 1] = points[:, 1]
        _i18_compare(item['points_local_xyz_m'], xyz, 'triangle segment inverse frame', atol=PLANE_TOLERANCE_M)
    expected_caps = {}
    for ordinal in coplanar:
        points = solid.points[ordinal]
        polygon = Polygon(_i18_np.column_stack(((points - origin) @ transverse, points[:, 1])))
        if polygon.area > 1e-08:
            expected_caps[ordinal] = polygon
    saved_caps = record['coplanar_triangle_supports']
    _i18_require(len({item['triangle_index'] for item in saved_caps}) == len(saved_caps) and {item['triangle_index'] for item in saved_caps} == set(expected_caps), 'coplanar support census differs')
    for item in saved_caps:
        ordinal = item['triangle_index']
        _i18_require(item['vertex_indices'] == solid.triangles[ordinal].tolist(), 'coplanar source references differ')
        _i18_require(Polygon(item['polygon_uv_m']).symmetric_difference(expected_caps[ordinal]).area <= 1e-08, 'fabricated coplanar triangle')
    expected_method = 'Mesh64_transform_slice_exact_plane' + ('_union_exact_saved_coplanar_triangles' if expected_caps else '')
    _i18_require(record['method'] == expected_method, 'undeclared slice/coplanar policy')
    actual = independently_slice(solid, origin, normal, transverse)
    supplied = saved_slice_geometry(record)
    difference = supplied.symmetric_difference(actual).area
    _i18_require(difference <= 1e-08, 'saved slice differs from independent source solid slice')
    _i18_compare(record['area_m2'], actual.area, 'actual slice area', atol=1e-08)
    return (actual, {'area_m2': actual.area, 'symmetric_difference_m2': difference, 'triangle_segments': len(segments), 'coplanar_triangles': len(expected_caps)})

def whole_line_supported(line, boundary):
    return line.difference(boundary.buffer(PLANE_TOLERANCE_M)).length <= PLANE_TOLERANCE_M

def verify_floor(points, aperture):
    from shapely.geometry import LineString
    floor = _i18_np.asarray(points, float)
    _i18_require(floor.ndim == 2 and floor.shape[1] == 2 and (len(floor) >= 2) and _i18_np.isfinite(floor).all() and _i18_np.all(_i18_np.diff(floor[:, 0]) > 0), 'invalid saved cut floor')
    line = LineString(floor)
    _i18_require(whole_line_supported(line, aperture.boundary), 'cut floor not actual source boundary')
    _i18_compare(floor[[0, -1], 0], [aperture.bounds[0], aperture.bounds[2]], 'whole aperture floor width', atol=1e-08)
    knots = sorted(set(floor[:, 0].tolist() + [point[0] for point in aperture.exterior.coords]))
    probes = knots + [(first + second) / 2 for first, second in zip(knots, knots[1:])]
    for offset in probes:
        vertical = LineString([(offset, aperture.bounds[1] - 1), (offset, aperture.bounds[3] + 1)])
        intersection = aperture.intersection(vertical)
        _i18_require(not intersection.is_empty, 'cut floor crosses missing aperture')
        _i18_compare(float(_i18_np.interp(offset, floor[:, 0], floor[:, 1])), intersection.bounds[1], 'saved floor is actual lower aperture envelope', atol=1e-08)
    return line

def audit_aperture(record, slices, shapes, frame, canonical=None):
    from shapely.geometry import LineString
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    cutter, before, after, removed = [shapes[key] for key in ('cutter', 'rock_before', 'rock_after', 'removed')]
    _i18_require(not cutter.is_empty and cutter.geom_type == 'Polygon' and (not cutter.interiors) and (removed.is_empty or (removed.geom_type == 'Polygon' and (not removed.interiors))), 'unknown/multiple/holed actual aperture cannot be accepted')
    _i18_require(not removed.is_empty or canonical is not None, 'unknown empty excavation without verified canonical whole port')
    _i18_require(record['pressure_slot_enlarges_face'] is False, 'storage slot fabricated a face aperture')
    polygon = Polygon(record['polygon_uv_m'])
    _i18_require(polygon.is_valid and polygon.symmetric_difference(cutter).area <= 1e-08, 'aperture not actual cutter domain')
    uv = _i18_np.asarray(record['polygon_uv_m'], float)
    xyz = _i18_np.asarray(frame['origin_local_xyz_m']) + uv[:, :1] * _i18_np.asarray(frame['transverse_unit_xyz'])
    xyz[:, 1] = uv[:, 1]
    _i18_compare(record['polygon_local_xyz_m'], xyz, 'aperture localXYZ', atol=1e-08)
    blocked = cutter.intersection(after).area
    replay = removed.symmetric_difference(cutter.intersection(before)).area
    outside = cutter.difference(before).area
    _i18_require(blocked <= 1e-08 and replay <= 1e-08, 'actual aperture blocked or removed/source intersection differs')
    for key, expected in (('blocked_area_m2', blocked), ('removed_replay_difference_area_m2', replay), ('actual_excavated_aperture_area_m2', removed.area), ('cutter_outside_original_rock_area_m2', outside), ('bounded_display_aperture_area_m2', cutter.area)):
        _i18_compare(record[key], expected, key, atol=1e-08)
    floor = verify_floor(record['cut_floor_uv_m'], cutter)
    pieces, wall_lengths, covered = (record['boundary_pieces'], [], [])
    _i18_require(pieces, 'missing aperture boundary census')
    for piece in pieces:
        points = _i18_np.asarray(piece['points_uv_m'], float)
        _i18_require(points.shape == (2, 2) and _i18_np.isfinite(points).all(), 'invalid boundary segment')
        line = LineString(points)
        _i18_require(line.length > PLANE_TOLERANCE_M and whole_line_supported(line, cutter.boundary), 'fabricated boundary piece')
        xyz = _i18_np.asarray(frame['origin_local_xyz_m']) + points[:, :1] * _i18_np.asarray(frame['transverse_unit_xyz'])
        xyz[:, 1] = points[:, 1]
        _i18_compare(piece['points_local_xyz_m'], xyz, 'boundary inverse frame', atol=1e-08)
        category = piece['category']
        actual_wall = whole_line_supported(line, after.boundary) and before.buffer(PLANE_TOLERANCE_M).covers(line)
        if actual_wall:
            _i18_require(category == 'actual_rock_wet_wall', 'actual rock wall misclassified')
            _i18_compare(piece['potential_wetted_length_m'], line.length, 'actual wet wall length', atol=1e-08)
            wall_lengths.append(line.length)
        else:
            _i18_require(not before.buffer(PLANE_TOLERANCE_M).covers(line), 'unknown in-rock edge without actual whole-wall support')
            _i18_require(category != 'actual_rock_wet_wall' and piece['potential_wetted_length_m'] is None, 'non-rock/artificial edge counted as real wetted wall')
            if whole_line_supported(line, floor):
                _i18_require(category == 'saved_cut_floor_open_air_side', 'open cut floor category differs')
            elif abs(points[0, 0] - points[1, 0]) <= PLANE_TOLERANCE_M:
                _i18_require(category == 'engineering_lateral_wall_above_terrain', 'engineering wall category differs')
            else:
                _i18_require(category == 'artificial_cutter_top_cap_not_wetted_wall', 'artificial cap category differs')
        for role, indices in piece['source_triangle_indices'].items():
            _i18_require(role in ('cutter', 'rock_after') and len(set(indices)) == len(indices) and all((type(index) is int for index in indices)), 'invalid wall source roles/references')
            support_lines = [LineString(item['points_uv_m']) for item in slices[role]['triangle_segments'] if item['triangle_index'] in indices]
            support_caps = [Polygon(item['polygon_uv_m']) for item in slices[role]['coplanar_triangle_supports'] if item['triangle_index'] in indices]
            available = {item['triangle_index'] for item in slices[role]['triangle_segments'] + slices[role]['coplanar_triangle_supports']}
            _i18_require(set(indices) <= available, 'wall references non-intersecting source triangles')
            if role == 'cutter' or actual_wall:
                _i18_require(indices and whole_line_supported(line, unary_union(support_lines + support_caps)), 'whole wall/edge lacks actual triangle support')
        _i18_require(set(piece['source_triangle_indices']) == {'cutter', 'rock_after'}, 'wall source census differs')
        covered.append(line)
    union = unary_union(covered)
    _i18_require(whole_line_supported(cutter.boundary, union) and abs(sum((line.length for line in covered)) - union.length) <= 1e-08, 'missing/overlapping aperture boundary pieces')
    closed = bool(outside <= 1e-08 and len(wall_lengths) == len(pieces) and (canonical is None))
    _i18_require(type(record['closed_boundary_certified']) is bool and record['closed_boundary_certified'] is closed and (record['kind'] == ('closed_polygon' if closed else 'open_cut_floor')), 'closed/open aperture classification differs')
    if canonical is not None:
        _i18_require(LineString(canonical).hausdorff_distance(floor) <= 1e-08, 'canonical whole floor missing from actual slice')
        _i18_compare(record['cut_floor_uv_m'], canonical, 'canonical full native knot function', atol=1e-08)
    extension = record['open_extension']
    if closed:
        _i18_require(extension is None, 'closed actual aperture given artificial extension')
    else:
        extensions = []
        for piece in pieces:
            if piece['category'] != 'artificial_cutter_top_cap_not_wetted_wall':
                continue
            points = piece['points_uv_m']
            first, second = sorted(points, key=lambda point: point[0])
            _i18_require(second[0] - first[0] > PLANE_TOLERANCE_M, 'zero-width free top interval')
            upper = max(cutter.bounds[3], before.bounds[3] if not before.is_empty else cutter.bounds[3], after.bounds[3] if not after.is_empty else cutter.bounds[3]) + 1
            column = Polygon([first, second, [second[0], upper], [first[0], upper]])
            _i18_require(column.intersection(before).area <= 1e-08 and column.intersection(after).area <= 1e-08 and (column.intersection(cutter).area <= 1e-08), 'free-top engineering extension penetrates actual rock roof or is not upper boundary')
            extensions.append({'u_interval_m': [first[0], second[0]], 'lower_boundary_uv_m': points, 'kind': 'above_saved_artificial_cap_only_not_above_actual_rock_roof'})
        _i18_require(extensions, 'unknown open face without supported artificial free-top interval')
        _i18_require(extension == {'kind': 'explicit_engineering_vertical', 'lateral_u_m': [floor.coords[0][0], floor.coords[-1][0]], 'unbounded_above_cut_floor': False, 'unbounded_only_over_supported_free_top_intervals': extensions, 'actual_rock_roof_segments_remain_bounded': True, 'artificial_cutter_roof_is_not_flow_ceiling': True, 'extension_is_engineering_not_whole_physical_path_certification': True, 'not_actual_terrain_floodplain': True}, 'undeclared engineering open extension')
    free_edges = []
    removed_points = list(removed.exterior.coords) if not removed.is_empty else []
    for first, second in zip(removed_points, removed_points[1:]):
        line = LineString([first, second])
        if line.length > PLANE_TOLERANCE_M and (not whole_line_supported(line, cutter.boundary)):
            free_edges.append(line)
    supplied_free = []
    for edge in record['terrain_opening_free_edges']:
        line = LineString(edge['points_uv_m'])
        _i18_require(edge['category'] == 'original_rock_top_opening_free_boundary_not_wall' and whole_line_supported(line, before.boundary), 'free opening edge not source rock boundary')
        refs = edge['rock_before_triangle_indices']
        lines = [LineString(item['points_uv_m']) for item in slices['rock_before']['triangle_segments'] if item['triangle_index'] in refs]
        caps = [Polygon(item['polygon_uv_m']) for item in slices['rock_before']['coplanar_triangle_supports'] if item['triangle_index'] in refs]
        _i18_require(refs and whole_line_supported(line, unary_union(lines + caps)), 'free opening lacks original source triangle support')
        supplied_free.append(line)
    expected_free, saved_free = (unary_union(free_edges), unary_union(supplied_free))
    _i18_require(whole_line_supported(expected_free, saved_free) and whole_line_supported(saved_free, expected_free), 'missing/fabricated original rock free-edge census')
    return {'kind': record['kind'], 'bounded_area_m2': cutter.area, 'actual_rock_wall_length_m': _i18_math.fsum(wall_lengths), 'boundary_piece_count': len(pieces), 'actual_excavated_area_m2': removed.area, 'engineering_open_extension_not_actual_rock_boundary': not closed, 'slot_excluded': True, 'free_surface_clip_not_counted_as_wall': True}

def check_plane(frame, world_origin, flow_xz, common_origin):
    world_origin, common_origin = (_i18_np.asarray(world_origin, float), _i18_np.asarray(common_origin, float))
    flow = _i18_np.asarray(flow_xz, float)
    _i18_require(flow.shape == (2,) and _i18_np.isfinite(flow).all() and (_i18_np.linalg.norm(flow) > 1e-08), 'unknown actual flow axis')
    flow = flow / _i18_np.linalg.norm(flow)
    normal, transverse = ([flow[0], 0.0, flow[1]], [flow[1], 0.0, -flow[0]])
    for key, expected in (('origin_world_xyz_m', world_origin), ('origin_local_xyz_m', world_origin - common_origin), ('common_local_origin_xyz_m', common_origin), ('normal_local_xyz', normal), ('transverse_unit_xyz', transverse), ('transverse_unit_xz', [flow[1], -flow[0]]), ('vertical_unit_xyz', [0.0, 1.0, 0.0])):
        _i18_compare(frame[key], expected, 'actual plane ' + key, atol=1e-08)
    _i18_require(frame['coordinate_convention'] == 'u_metres_Ylocal_metres_not_floor_relative' and frame['positive_normal'] == 'from_cell_to_cell_actual_horizontal_route', 'wrong face frame semantics')

def source_canonical_floor(port, frame):
    _i18_require(port['status'] == 'candidate' and (not port['rejection_reasons']), 'refused canonical source port')
    common = _i18_np.asarray(frame['common_local_origin_xyz_m'], float)
    origin = _i18_np.asarray(frame['origin_local_xyz_m'], float)
    normal, transverse = (_i18_np.asarray(frame['normal_local_xyz']), _i18_np.asarray(frame['transverse_unit_xyz']))
    floor = []
    for segment in port['profile']['profile_segments']:
        for piece in segment['native_pieces']:
            source, cut = (piece['source']['source_coefficients_m_t012'], piece['depth_coefficients_m_t01'])
            _i18_require(source[2] == 0 and 0 <= min(cut[0], sum(cut)) <= max(cut[0], sum(cut)) <= 4, 'unsupported/illegal canonical native floor')
            for fraction, xz in ((0.0, piece['start_xz_m']), (1.0, piece['end_xz_m'])):
                height = source[0] + source[1] * fraction - cut[0] - cut[1] * fraction
                point = _i18_np.asarray([xz[0], height, xz[1]]) - common
                _i18_require(abs((point - origin) @ normal) <= 1e-08, 'source canonical floor off actual face plane')
                uv = [float((point - origin) @ transverse), float(point[1])]
                if not floor or _i18_math.dist(uv, floor[-1]) > 1e-08:
                    floor.append(uv)
    floor.sort(key=lambda point: point[0])
    _i18_require(len(floor) >= 4 and all((second[0] > first[0] for first, second in zip(floor, floor[1:]))), 'canonical port whole floor/knot census invalid')
    return floor

def audit_face(face, ordinal, geometry, vdm, attachments, solids, common_origin):
    _i18_check_identity(face)
    link = geometry['hydraulic_links'][ordinal]
    _i18_require(face['schema'] == 'td-hybrid-river-face-v1' and face['face_id'] == 'face:' + str(ordinal) and (face['status'] == 'candidate') and (not face['rejection_reasons']), 'refused/unknown face cannot be promoted')
    for key in ('link_id', 'from_cell_id', 'to_cell_id', 'length_m'):
        _i18_require(face[key] == link[key], 'actual link binding differs: ' + key)
    cells = {cell['cell_id']: cell for cell in geometry['hydraulic_cells']}
    _i18_require(face['length_source'] == 'unchanged_geometry_hydraulic_link' and face['length_m'] > 0 and (face['roughness_manning'] == 0.035) and (face['roughness_source_cell_ids'] == [link['from_cell_id'], link['to_cell_id']]) and all((cells[key]['roughness_manning'] == 0.035 for key in face['roughness_source_cell_ids'])) and (face['additional_step_loss'] is None), 'undeclared n/length/step loss')
    stations = vdm['stations']
    canonical = None
    if ordinal in (0, 17):
        kind = 'sink' if ordinal == 0 else 'spring'
        attachment = attachments['attachments'][kind]
        port = _i18_read(attachment['canonical_port_pin'])
        source_node = _i18_read(attachment['surface_node_pin'])
        station = stations[0 if ordinal == 0 else -1]
        _i18_require(link['to_cell_id'] == station['station_id'] if ordinal == 0 else link['from_cell_id'] == station['station_id'], 'canonical attachment gallery endpoint differs')
        _i18_require(geometry['portal_bindings'][kind]['port_identity_sha256'] == port['identity_sha256'], 'canonical port differs from original geometry')
        check_plane(face['plane'], station['origin_xyz_m'], port['flow_unit_xz'], common_origin)
        _i18_require(face['orientation_witness'] == {'canonical_station_id': station['station_id'], 'actual_flow_unit_xz': port['flow_unit_xz'], 'actual_source_arc_xyz_m': port['source_arc_xyz_m'], 'not_oblique_endpoint_section_projection': True}, 'canonical face orientation source differs')
        canonical = source_canonical_floor(port, face['plane'])
        binding = face['shared_port_binding']
        expected = {'kind': kind, 'canonical_port_pin': attachment['canonical_port_pin'], 'surface_node_pin': attachment['surface_node_pin'], 'port_identity_sha256': port['identity_sha256'], 'actual_complete_port_proof': attachment['actual_complete_port_proof'], 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'canonical_floor_uv_m': canonical, 'hydraulic_boundary_certified': False, 'shared_whole_function_not_endpoint_minimum': True}
        _i18_require(binding == expected and face['plane_rule'] == 'actual_canonical_shared_port_plane', 'incomplete canonical attachment binding')
        proof = binding['actual_complete_port_proof']
        _i18_require(proof in source_node['port_proofs'] and proof['midpoint_port_identity_sha256'] == port['identity_sha256'] and (sorted((segment['profile_segment_index'] for segment in proof['segments'])) == [0, 1, 2]) and all((segment['pieces'] for segment in proof['segments'])), 'canonical whole profile not original complete proof')
        source_triangles = source_node['geometry']['triangles']
        _i18_require(binding['half_arm_triangle_indices'] and all((type(index) is int and 0 <= index < len(source_triangles) for index in binding['half_arm_triangle_indices'])), 'invalid actual half-arm triangle references')
    else:
        first, second = (stations[ordinal - 1], stations[ordinal])
        _i18_require((link['from_cell_id'], link['to_cell_id']) == (first['station_id'], second['station_id']) and face['shared_port_binding'] is None and (face['plane_rule'] == 'actual_adjacent_station_midpoint_XZ_flow_plane'), 'wrong gallery plane/link rule')
        start, end = (_i18_np.asarray(first['origin_xyz_m']), _i18_np.asarray(second['origin_xyz_m']))
        check_plane(face['plane'], (start + end) / 2, (end - start)[[0, 2]], common_origin)
        _i18_require(face['orientation_witness'] == {'station_ids': [first['station_id'], second['station_id']], 'station_origin_world_xyz_m': [start.tolist(), end.tolist()], 'normal_rule': 'unit_horizontal_discrete_centerline_segment_not_area_cosine_rescale'}, 'gallery face orientation witness differs')
    _i18_require(set(face['solid_slices']) == set(solids), 'four actual solid slice census differs')
    shapes, reports = ({}, {})
    for role, solid in solids.items():
        shapes[role], reports[role] = audit_slice(face['solid_slices'][role], solid, face['plane'], geometry['mesh_pins'][role])
        _i18_check_memory()
    return {'face_id': face['face_id'], 'link_id': link['link_id'], 'plane_verified': True, 'canonical_complete_floor_verified': canonical is not None, 'solid_slices': reports, 'aperture': audit_aperture(face['aperture'], face['solid_slices'], shapes, face['plane'], canonical)}

def audit_hybrid_river_faces_audit(face_pin):
    record = _i18_read(face_pin)
    _i18_require(record['schema'] == 'td-hybrid-river-faces-v1' and record['status'] in ('candidate_unverified', 'refused'), 'wrong saved face schema/status')
    _i18_require(record['code_sha256'] == FROZEN_FACE_CODE, 'frozen face implementation binding differs')
    inputs = record['inputs']
    _i18_require(inputs['geometry']['sha256'] == GEOMETRY_SHA256 and inputs['geometry_audit']['sha256'] == GEOMETRY_AUDIT_SHA256 and (inputs['graph']['sha256'] == GRAPH_SHA256), 'only fixed independently passed geometry03 parents supported')
    geometry = _i18_read(inputs['geometry'])
    geometry_audit = _i18_read_audit(inputs['geometry_audit'])
    graph = _i18_read(inputs['graph'])
    _i18_require(geometry_audit['status'] == 'passed' and (not geometry_audit['errors']) and (geometry_audit['geometry_sha256'] == GEOMETRY_SHA256) and (geometry_audit['geometry_identity_sha256'] == geometry['identity_sha256']) and (geometry_audit['actual_hydraulic_sections_verified'] is True) and (geometry_audit['actual_portal_connections_verified'] is True) and (geometry_audit['mesh_pins'] == geometry['mesh_pins']) and (geometry_audit['vdm_pin'] == geometry['vdm_pin']) and (geometry_audit['graph_identity_sha256'] == geometry['graph_identity_sha256']) and (geometry_audit['inputs'] == geometry['inputs']) and (inputs['graph'] == geometry['inputs']['graph']) and (graph['identity_sha256'] == geometry['graph_identity_sha256']), 'geometry/independent audit/graph linkage differs')
    _i18_require(inputs['mesh_pins'] == geometry['mesh_pins'] and inputs['vdm'] == geometry['vdm_pin'] and (inputs['surface_attachments'] == geometry['surface_attachments_pin']), 'actual face sources substituted')
    for parent in (record, geometry, geometry_audit):
        for group in ('code_sha256', 'readonly_dependency_code_sha256', 'audit_code_sha256'):
            for name, sha in parent.get(group, {}).items():
                _i18_require(_i18_file_sha256(ROOT / name) == sha, 'frozen source changed: ' + name)
    for parent in (geometry, graph):
        for pin in parent['inputs'].values():
            _i18_checked_path(pin)
    _i18_require(geometry['status'] == 'candidate' and (not geometry['rejection_reasons']) and (set(record['inputs']) == {'geometry', 'geometry_audit', 'graph', 'mesh_pins', 'vdm', 'surface_attachments'}), 'changed geometry/face input contract')
    _i18_require(record.get('policy') == AUDIT_HYBRID_RIVER_FACES_POLICY and record['policy_identity_sha256'] == _i18_digest(AUDIT_HYBRID_RIVER_FACES_POLICY), 'face policy differs')
    for flag in ('independent_audit_passed', 'hydraulic_solved', 'native_exact', 'water_discharge_computed', 'storage_geometry_changed', 'pressure_slot_enlarges_face'):
        _i18_require(record[flag] is False, 'face source prematurely promoted capability: ' + flag)
    _i18_require(record['geometry_identity_sha256'] == geometry['identity_sha256'] and record['graph_identity_sha256'] == graph['identity_sha256'] and (record['runtime']['manifold3d'] == '3.5.4'), 'face geometry identity/runtime differs')
    library = _i18_manifold_library()
    _i18_require(_i18_file_sha256(library.__file__) == record['runtime']['manifold3d_binary_sha256'], 'actual slice library binary changed')
    vdm, attachments = (_i18_read(inputs['vdm']), _i18_read(inputs['surface_attachments']))
    _i18_require(len(vdm['stations']) == 17 and len(geometry['hydraulic_links']) == 18 and (record['face_count'] == len(record['faces']) == 18), 'fixed 18-link face census incomplete')
    solids, common = ({}, None)
    for role, pin in geometry['mesh_pins'].items():
        mesh = _i18_read(pin)
        _i18_require(mesh['role'] == role and mesh['schema'] == 'td-hybrid-local-solid-mesh-v1', 'wrong actual mesh role')
        origin = _i18_np.asarray(mesh['local_origin_xyz_m'], float)
        if common is None:
            common = origin
        _i18_require(_i18_np.array_equal(common, origin), 'source solids not in common frame')
        solids[role] = _i18_Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], role)
    _i18_require(set(solids) == {'cutter', 'removed', 'rock_before', 'rock_after'}, 'actual solid census differs')
    reports, errors = ([], [])
    for ordinal, face in enumerate(record['faces']):
        try:
            reports.append(audit_face(face, ordinal, geometry, vdm, attachments, solids, common))
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append({'face_id': face.get('face_id'), 'error': str(error), 'saved_status': face.get('status'), 'saved_rejection_reasons': face.get('rejection_reasons')})
    refused = [face['face_id'] for face in record['faces'] if face['status'] != 'candidate']
    _i18_require(record['rejection_reasons'] == refused and record['status'] == ('refused' if refused else 'candidate_unverified'), 'saved whole-package refusal census differs')
    return {'schema': AUDIT_HYBRID_RIVER_FACES_AUDIT_SCHEMA, 'status': 'refused' if errors else 'passed', 'errors': errors, 'faces_pin': face_pin, 'inputs': inputs, 'geometry_sha256': GEOMETRY_SHA256, 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': graph['identity_sha256'], 'reports': reports, 'verified_face_count': len(reports), 'actual_slice_sources_verified': not errors, 'wet_wall_boundary_sources_verified': not errors, 'hydraulic_solved': False, 'n_and_length_provenance_only_not_physical_adoption': True, 'additional_step_loss_unknown_not_zero': True, 'hydraulic_constitutive_law_accepted': False, 'whole_link_step_support_certified': False, 'unbounded_engineering_extension_is_actual_rock_aperture': False, 'scope': '18_saved_local_transverse_faces_not_full_link_control_sill_or_dynamic_flow_certification', 'tolerances': {'plane_and_boundary_m': PLANE_TOLERANCE_M, 'slice_difference_m2': 1e-08}}

def _entry_audit_hybrid_river_faces():
    parser = _i18_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--faces', type=_i18_Path, required=True)
    parser.add_argument('--faces-sha256', required=True)
    parser.add_argument('--output', type=_i18_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i18_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    pin = {'path': str(args.faces.resolve()), 'sha256': args.faces_sha256}
    started = _i18_time.monotonic()
    try:
        report = audit_hybrid_river_faces_audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as error:
        report = {'schema': AUDIT_HYBRID_RIVER_FACES_AUDIT_SCHEMA, 'status': 'refused', 'errors': [str(error)], 'faces_pin': pin, 'hydraulic_solved': False, 'hydraulic_constitutive_law_accepted': False}
    report['resource'] = {'wall_seconds': _i18_time.monotonic() - started, 'actual_peak_rss_bytes': _i18_check_memory(), 'solver_calls': 0, 'source_artifacts_modified': False}
    report['code_sha256'] = {name: _i18_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tests/test_hybrid_geometry_saved_audit.py', 'tools/hybrid_cave_saved_audit.py', 'tools/td_shared_channel_fine_saved_audit.py')}
    report['identity_sha256'] = _i18_digest(report)
    payload = _i18_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i18_require(len(payload) <= _i18_MAX_BYTES, 'independent face audit exceeds 64MiB file budget')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i18_json.dumps({'status': report['status'], 'errors': report['errors'], 'output': str(output), 'sha256': _i18_file_sha256(output), 'verified_face_count': report.get('verified_face_count', 0)}))
    if report['status'] != 'passed':
        raise SystemExit(1)
_i20_sys.path.insert(0, str(ROOT))
AUDIT_HYBRID_SURFACE_COMPOSITION_AUDIT_SCHEMA = 'td-hybrid-surface-composition-independent-audit-v1'
FROZEN_COMPOSITION_CODE = {'terrain_pipeline/hybrid_surface_composition.py': '0a9b424ca1994d150c8bf6c3cb90c2ce8c263cd5ca78cace24134242b02c5dd3', 'tools/prepare_hybrid_surface_composition.py': '93e50dec6ac93cbda8396fb2b344fd40204a1c72942c944a17e0ecd698bafff8', 'tests/test_hybrid_surface_composition.py': '5df84c0c6c5cfb17b83c1f25cfc3819ee7c221c9b850d5d62dfbcaf443bc0ae7'}
AUDIT_HYBRID_SURFACE_COMPOSITION_POLICY = {'version': 'saved-native-halfarm-prism-composition-v1', 'operation': 'original_sampled_rock_minus_union_immutable_gallery_and_surface_prisms', 'floor': 'saved_native_patch_bilinear_minus_saved_affine_cut_at_vertices_piecewise_planar', 'entity_domain': 'original_saved_native_patch_polygon_authority_including_recorded_clip_roundoff_not_resnapped_fan', 'canonical': 'whole_original_native_piece_linear_boundary_match_not_four_point_only', 'approximation': 'not_native_exact_not_fine15_material_no_resampling_or_double_depth_cut', 'top': 'explicit_common_horizontal_cap_above_all_saved_rock_and_gallery_vertices', 'material': 'original_removed_plus_disjoint_extra_removed_equals_total_no_fill', 'portal': 'full_supported_shared_interface_and_exact_unblocked_polygon_offsets_diagnostic_only', 'hydraulics': 'not_solved_no_discharge_or_resistance_law_acceptance'}

class EmptySolid:

    def manifold(self, library):
        return library.Manifold()

def exact_fan_cut(fan, point):
    points = fan['vertices_xz_m']
    depths = fan['depth_at_vertices_m']
    _i20_require(len(points) == 3 and all((len(vertex) == 2 for vertex in points)) and (len(point) == 2) and (len(depths) == 3) and all((_i20_math.isfinite(value) for vertex in points for value in vertex)) and all((_i20_math.isfinite(value) for value in point)) and all((_i20_math.isfinite(value) and 0 <= value <= 4 for value in depths)), 'invalid saved fan inputs')
    exact_points = [[_i20_Fraction.from_float(float(value)) for value in vertex] for vertex in points]
    target = [_i20_Fraction.from_float(float(value)) for value in point]
    first = [exact_points[1][axis] - exact_points[0][axis] for axis in (0, 1)]
    second = [exact_points[2][axis] - exact_points[0][axis] for axis in (0, 1)]
    offset = [target[axis] - exact_points[0][axis] for axis in (0, 1)]
    determinant = first[0] * second[1] - first[1] * second[0]
    _i20_require(determinant != 0, 'degenerate saved fan domain')
    weight_first = (offset[0] * second[1] - offset[1] * second[0]) / determinant
    weight_second = (first[0] * offset[1] - first[1] * offset[0]) / determinant
    weights = [1 - weight_first - weight_second, weight_first, weight_second]
    if min(weights) < 0:
        return None
    value = sum((weight * _i20_Fraction.from_float(float(depth)) for weight, depth in zip(weights, depths)))
    _i20_require(0 <= value <= 4, 'strict exact fan cut depth invalid')
    return float(value)

def saved_patch_affine_depth(fan, point):
    _i20_require(all((_i20_math.isfinite(depth) and 0 <= depth <= 4 for depth in fan['depth_at_vertices_m'])), 'invalid original fan vertex depths')
    for vertex, depth in zip(fan['vertices_xz_m'], fan['depth_at_vertices_m']):
        if _i20_np.array_equal(vertex, point):
            return float(depth)
    coefficients = fan['depth_coefficients_m_1xz']
    offset = _i20_np.asarray(point, float) - _i20_np.asarray(fan['depth_origin_xz_m'], float)
    value = _i20_math.fsum((coefficients[0], coefficients[1] * offset[0], coefficients[2] * offset[1]))
    _i20_require(_i20_math.isfinite(value) and 0 <= value <= 4, 'strict original patch affine depth invalid; no clamp')
    return value

def volume_difference(first, second):
    return float((first - second).volume() + (second - first).volume())

def audit_material_solids(original_rock, old_after, old_removed, surface_cutter, combined_cutter, actual_after, extra_removed, total_removed, gallery_cutter):
    library = _i20_manifold_library()
    solids = [solid.manifold(library) for solid in (original_rock, old_after, old_removed, surface_cutter, combined_cutter, actual_after, extra_removed, total_removed, gallery_cutter)]
    rock, previous, previous_removed, surface, combined, actual, extra, total, gallery = solids
    tolerance = max(1e-07, rock.volume() * 1e-10)
    _i20_require(volume_difference(previous, rock - gallery) <= tolerance and volume_difference(previous_removed, rock ^ gallery) <= tolerance, 'original saved rock/cave material mismatch')
    _i20_require(volume_difference(combined, gallery + surface) <= tolerance, 'combined cutter not actual gallery/surface union')
    _i20_require(volume_difference(actual, rock - combined) <= tolerance, 'actual rock not original minus combined cutter')
    _i20_require(volume_difference(total, rock ^ combined) <= tolerance, 'total removed not actual original rock intersection')
    _i20_require(volume_difference(extra, previous - actual) <= tolerance and volume_difference(extra, previous ^ surface) <= tolerance, 'extra removed not newly cut old remaining rock')
    fill = float((actual - previous).volume())
    overlap = float((previous_removed ^ extra).volume())
    residual = float(total.volume() - previous_removed.volume() - extra.volume())
    _i20_require(fill <= tolerance and overlap <= tolerance and (abs(residual) <= tolerance) and (volume_difference(total, previous_removed + extra) <= tolerance), 'fill/overlapping extra/original-plus-extra material mismatch')
    _i20_check_memory()
    return {'original_removed_m3': previous_removed.volume(), 'extra_removed_m3': extra.volume(), 'total_removed_m3': total.volume(), 'signed_increment_residual_m3': residual, 'actual_added_rock_difference_m3': fill, 'old_extra_overlap_m3': overlap, 'independent_boolean_verified': True, 'comparison_tolerance_m3': tolerance}

def source_patch_height(patch, point, native):
    row, column = patch['patch_row_column']
    _i20_require(type(row) is int and type(column) is int and (0 <= row < native.height.shape[0] - 1) and (0 <= column < native.height.shape[1] - 1), 'invalid native source patch index')
    origin = native.origin + _i20_np.asarray([column, row]) * native.spacing
    heights = [float(native.height[row, column]), float(native.height[row, column + 1]), float(native.height[row + 1, column]), float(native.height[row + 1, column + 1])]
    coefficients = [heights[0], heights[1] - heights[0], heights[2] - heights[0], heights[3] - heights[1] - heights[2] + heights[0]]
    _i20_compare(patch['patch_origin_m_xz'], origin, 'original native patch origin', atol=1e-09)
    _i20_require(patch['native_spacing_m'] == native.spacing, 'native source spacing changed')
    _i20_compare(patch['native_height_m'], heights, 'native original patch heights', atol=0.0)
    _i20_compare(patch['bilinear_coefficients_m'], coefficients, 'native bilinear whole coefficients', atol=1e-12)
    columns = native.height.shape[1]
    _i20_require(patch['native_cell_ids'] == [row * columns + column, row * columns + column + 1, (row + 1) * columns + column, (row + 1) * columns + column + 1], 'native patch provenance differs')
    position = (_i20_np.asarray(point, float) - origin) / native.spacing
    _i20_require(_i20_np.all(position >= 0) and _i20_np.all(position <= 1), 'prism vertex outside saved native patch')
    sample = native.sample(point)
    _i20_require(not sample['rejection_reasons'] and (not sample['wet_source_support']) and (sample['height_m'] is not None), 'prism source wet/protected/unknown/unselected')
    return float(coefficients[0] + coefficients[1] * position[0] + coefficients[2] * position[1] + coefficients[3] * position[0] * position[1])

def audit_prisms(saved, attachments, vdm, native, origin, meshes):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    _i20_require(saved['schema'] == 'td-hybrid-surface-prisms-v1' and saved['native_exact'] is False and (saved['bottom_semantics'] == AUDIT_HYBRID_SURFACE_COMPOSITION_POLICY['floor']) and (set(saved['half_arms']) == {'sink', 'spring'}), 'changed prism source/approximation contract')
    _i20_compare(saved['common_local_origin_xyz_m'], origin, 'prism shared local origin', atol=0.0)
    expected_cap = max((float(meshes[role].vertices[:, 1].max() + origin[1]) for role in ('rock_before', 'original_cutter'))) + 10.0
    _i20_require(saved['cap_y_world_m'] == expected_cap and saved['cap_above_saved_rock_and_gallery_margin_m'] == 10.0, 'surface cutter cap not fixed above actual original solids')
    library = _i20_manifold_library()
    records, all_prisms, reports = ({}, [], {})
    expected_faces = {tuple(sorted(face)) for face in ((0, 2, 1), (3, 4, 5), (0, 1, 4), (0, 4, 3), (1, 2, 5), (1, 5, 4), (2, 0, 3), (2, 3, 5))}
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        half = saved['half_arms'][kind]
        attachment = attachments['attachments'][kind]
        node = _i20_read(attachment['surface_node_pin'])
        wanted = {'shared:' + node['node_id'] + ':' + str(index) for index in attachment['half_arm_triangle_indices']}
        functions = {item['triangle_id']: item for item in node['source_functions'] if item['triangle_id'] in wanted}
        _i20_require(set(functions) == wanted and node['status'] == 'candidate' and (not node['rejection_reasons']) and (half['node_id'] == node['node_id']) and (half['node_pin'] == attachment['surface_node_pin']) and (half['half_arm_triangle_indices'] == attachment['half_arm_triangle_indices']) and (half['immutable_gallery_station_index'] == ordinal) and (half['immutable_gallery_ring_xyz_m'] == vdm['stations'][ordinal]['derived_ring_xyz_m']), 'original whole half-arm/immutable gallery sources differ')
        expected = {}
        for function in functions.values():
            _i20_check_identity(function)
            _i20_require(function['status'] == 'candidate' and (not function['rejection_reasons']), 'refused original source function')
            for fan in function['fans']:
                _i20_require(fan['fan_id'] not in expected, 'duplicate original fan')
                compact = next((item for item in attachment['compact_native_fans'] if item['fan_key'] == fan['fan_id']), None)
                _i20_require(compact is not None and all((compact[key] == fan[key] for key in ('vertices_xz_m', 'depth_at_vertices_m', 'depth_coefficients_m_1xz', 'depth_origin_xz_m'))), 'original native/compact affine fan mismatch')
                domains = [Polygon(patch['polygon_xz_m']) for patch in fan['native_patches']]
                _i20_require(all((domain.is_valid and domain.area > 0 for domain in domains)) and Polygon(fan['vertices_xz_m']).symmetric_difference(unary_union(domains)).area <= 1e-08, 'original native patch coverage differs from fan domain')
                expected[fan['fan_id']] = (function, fan)
        coverage = {}
        own = []
        bottoms = half['bottom_triangles']
        _i20_require(bottoms and [item['bottom_triangle_id'] for item in bottoms] == list(range(len(bottoms))) and (len(bottoms) * 8 <= 200000), 'invalid bounded prism triangle census')
        maximum_approximation = 0.0
        maximum_bilinear_bound = 0.0
        outside_vertex_count = 0
        for item in bottoms:
            _i20_require(item['fan_key'] in expected, 'surface cutter uses non-half-arm source')
            function, fan = expected[item['fan_key']]
            _i20_require(item['triangle_id'] == function['triangle_id'] and item['source_function_identity_sha256'] == function['identity_sha256'] and (item['saved_affine_fan'] == fan) and (item['saved_native_patch'] in fan['native_patches']) and (item['bilinear_interior_is_planar_approximation'] is True), 'prism native/fan function substituted or approximation concealed')
            patch = item['saved_native_patch']
            patch_index = fan['native_patches'].index(patch)
            bottom = _i20_np.asarray(item['bottom_vertices_xyz_m'], float)
            _i20_require(bottom.shape == (3, 3) and _i20_np.isfinite(bottom).all(), 'invalid bottom triangle')
            polygon = Polygon(bottom[:, [0, 2]])
            domain = Polygon(patch['polygon_xz_m'])
            _i20_require(polygon.is_valid and polygon.area > 0 and (polygon.difference(domain).area <= 1e-10), 'bottom triangle outside original native patch')
            coverage.setdefault((item['fan_key'], patch_index), []).append(polygon)
            expected_depths = []
            domain_witnesses = []
            for point in bottom:
                horizontal = point[[0, 2]]
                _i20_require(any((_i20_np.array_equal(horizontal, vertex) for vertex in patch['polygon_xz_m'])), 'prism introduced or snapped a saved patch vertex')
                inside = exact_fan_cut(fan, horizontal) is not None
                outside_vertex_count += int(not inside)
                domain_witnesses.append({'point_xz_m': horizontal.tolist(), 'inside_original_fan_exact_domain': inside, 'entity_domain_authority': 'original_saved_native_patch_polygon', 'clip_point_not_snapped': True})
                depth = saved_patch_affine_depth(fan, horizontal)
                expected_depths.append(depth)
                _i20_compare(point[1], source_patch_height(patch, point[[0, 2]], native) - depth, 'prism bottom original native minus cut', atol=1e-09)
            _i20_compare(item['depth_at_vertices_m'], expected_depths, 'strict original affine depths', atol=1e-12)
            _i20_require(item['saved_patch_vertex_domain_witnesses'] == domain_witnesses, 'exact original fan domain/patch authority witnesses concealed')
            centroid = bottom.mean(axis=0)
            depth = saved_patch_affine_depth(fan, centroid[[0, 2]])
            deviation = source_patch_height(patch, centroid[[0, 2]], native) - depth - centroid[1]
            maximum_approximation = max(maximum_approximation, abs(deviation))
            bilinear_bound = abs(patch['bilinear_coefficients_m'][3]) * _i20_np.ptp(bottom[:, 0]) * _i20_np.ptp(bottom[:, 2]) / native.spacing ** 2
            _i20_compare(item['conservative_interior_height_error_bound_m'], bilinear_bound, 'saved bilinear planar approximation bound', atol=1e-12)
            maximum_bilinear_bound = max(maximum_bilinear_bound, float(bilinear_bound))
            prism = item['prism']
            _i20_check_identity(prism)
            _i20_require(prism['schema'] == 'td-hybrid-local-solid-mesh-v1' and prism['role'] == 'surface_half_arm_closed_triangular_prism' and (item['prism_triangle_roles'] == ['floor', 'artificial_top_cap'] + ['lateral'] * 6) and ({tuple(sorted(face)) for face in prism['triangles']} == expected_faces), 'prism closure/source roles differ')
            top = bottom.copy()
            top[:, 1] = expected_cap
            _i20_compare(prism['local_origin_xyz_m'], origin, 'prism origin', atol=0.0)
            _i20_compare(prism['vertices_local_xyz_m'], _i20_np.vstack((bottom, top)) - origin, 'prism actual vertices', atol=1e-09)
            solid = _i20_Solid(prism['vertices_local_xyz_m'], prism['triangles'], 'source prism')
            _i20_compare(prism['signed_volume_m3'], solid.signed_volume, 'saved source prism volume', atol=1e-07)
            own.append(solid)
            all_prisms.append(solid.manifold(library))
        for fan_key, (_, fan) in expected.items():
            for patch_index, patch in enumerate(fan['native_patches']):
                parts = coverage.get((fan_key, patch_index), [])
                domain = Polygon(patch['polygon_xz_m'])
                _i20_require(parts and domain.symmetric_difference(unary_union(parts)).area <= 1e-08 and (abs(sum((part.area for part in parts)) - domain.area) <= 1e-08), 'missing/overlapping whole native patch prism coverage')
        records[kind] = own
        reports[kind] = {'bottom_triangles': len(bottoms), 'original_half_arm_triangles': len(wanted), 'native_source_and_saved_patch_affine_function_verified': True, 'exact_original_fan_outside_vertex_occurrences': outside_vertex_count, 'entity_domain_authority': 'original_saved_native_patch_polygon', 'max_sampled_centroid_planar_native_difference_m': maximum_approximation, 'max_saved_bilinear_component_error_bound_m': maximum_bilinear_bound, 'centroid_probe_is_not_global_approximation_bound': True}
        _i20_check_memory()
    expected_surface = library.Manifold.batch_boolean(all_prisms, library.OpType.Add)
    tolerance = max(1e-07, expected_surface.volume() * 1e-10)
    _i20_require(volume_difference(expected_surface, meshes['surface_cutter'].manifold(library)) <= tolerance, 'saved surface cutter not union of source-bound closed prisms')
    extra = meshes['extra_removed'].manifold(library)
    _i20_require((extra - expected_surface).volume() <= tolerance, 'extra removed escapes source-supported prism volume')
    return (records, reports)

def audit_canonical_pieces(witnesses, proof, bottoms, flow, kind, station):
    expected_pieces = [piece for segment in proof['segments'] for piece in segment['pieces']]
    _i20_require([item['original_piece'] for item in witnesses] == expected_pieces and witnesses, 'canonical whole piece census differs')
    normal = _i20_np.asarray(flow, float)
    normal /= _i20_np.linalg.norm(normal)
    side = -1.0 if kind == 'sink' else 1.0
    origin = _i20_np.asarray(station['origin_xyz_m'])[[0, 2]]
    minimum_distance = _i20_math.inf
    for witness in witnesses:
        piece = witness['original_piece']
        start, end = (_i20_np.asarray(piece['start_xz_m']), _i20_np.asarray(piece['end_xz_m']))
        delta = end - start
        squared_length = float(delta @ delta)
        _i20_require(squared_length > 1e-16 and piece['bed_coefficients_m_t012'][2] == 0.0 and (witness['full_interval_t01'] == [0.0, 1.0]) and witness['supports'], 'unsupported canonical piece')
        length = _i20_math.sqrt(squared_length)
        intervals = []
        for support in witness['supports']:
            index = support['bottom_triangle_id']
            _i20_require(type(index) is int and 0 <= index < len(bottoms), 'canonical references unknown source bottom')
            bottom = bottoms[index]
            vertices = _i20_np.asarray(bottom['bottom_vertices_xyz_m'])
            edge = _i20_np.asarray(support['edge_xyz_m'], float)
            _i20_require(edge.shape == (2, 3) and support['fan_key'] == bottom['fan_key'] and any((_i20_np.array_equal(edge, _i20_np.asarray([vertices[offset], vertices[(offset + 1) % 3]])) for offset in range(3))), 'canonical edge not original saved prism bottom edge')
            fractions = (edge[:, [0, 2]] - start) @ delta / squared_length
            _i20_require(_i20_np.max(_i20_np.linalg.norm(edge[:, [0, 2]] - (start + fractions[:, None] * delta), axis=1)) <= 1e-08 and abs(fractions[1] - fractions[0]) * length > 1e-08, 'canonical support edge off whole source line')
            interval = [max(0.0, float(min(fractions))), min(1.0, float(max(fractions)))]
            _i20_require((interval[1] - interval[0]) * length > 1e-08, 'empty canonical support interval')
            _i20_compare(support['interval_t01'], interval, 'canonical whole interval', atol=1e-12)
            slope = (edge[1, 1] - edge[0, 1]) / (fractions[1] - fractions[0])
            intercept = edge[0, 1] - slope * fractions[0]
            expected = piece['bed_coefficients_m_t012']
            error = max(abs(intercept - expected[0]), abs(intercept + slope - expected[0] - expected[1]))
            _i20_require(error <= 1e-08, 'whole canonical bed coefficient mismatch')
            _i20_compare(support['actual_bed_coefficients_m_t012'], [intercept, slope, 0.0], 'saved canonical coefficients', atol=1e-09)
            _i20_compare(support['maximum_whole_linear_error_m'], error, 'saved whole coefficient error', atol=1e-12)
            distances = side * ((vertices[:, [0, 2]] - origin) @ normal)
            _i20_require(distances.min() >= -1e-08 and distances.max() > 1e-08, 'canonical support not exterior half-arm volume')
            _i20_compare(support['exterior_support_distance_m'], distances.max(), 'actual exterior prism support', atol=1e-08)
            minimum_distance = min(minimum_distance, float(distances.max()))
            intervals.append(interval)
        cursor = 0.0
        for lower, upper in sorted(intervals):
            _i20_require((lower - cursor) * length <= 1e-08, 'canonical full function gap')
            cursor = max(cursor, upper)
        _i20_require((1 - cursor) * length <= 1e-08, 'canonical whole function incomplete')
    return minimum_distance

def audit_connections(composition, saved, geometry, attachments, vdm, meshes, origin):
    from shapely.geometry import Polygon
    library = _i20_manifold_library()
    _i20_require(set(composition['portal_connections']) == {'sink', 'spring'}, 'missing two actual port connection records')
    reports = {}
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        connection = composition['portal_connections'][kind]
        attachment = attachments['attachments'][kind]
        port = _i20_read(attachment['canonical_port_pin'])
        station = vdm['stations'][ordinal]
        _i20_require(port['identity_sha256'] == geometry['portal_bindings'][kind]['port_identity_sha256'] and connection['original_complete_port_proof'] == attachment['actual_complete_port_proof'] and (connection['immutable_gallery_station_index'] == ordinal) and (connection['offset_traces_are_diagnostic_only'] is True) and (connection['hydraulic_boundary_certified'] is False) and (connection['full_shared_interface_supported'] is True) and (connection['canonical_whole_piece_witnesses'] == saved['half_arms'][kind]['canonical_whole_piece_witnesses']), 'canonical connection source/claim differs')
        minimum_distance = audit_canonical_pieces(connection['canonical_whole_piece_witnesses'], attachment['actual_complete_port_proof'], saved['half_arms'][kind]['bottom_triangles'], port['flow_unit_xz'], kind, station)
        frame = connection['plane']
        check_plane(frame, station['origin_xyz_m'], port['flow_unit_xz'], origin)
        ring = _i20_np.asarray(station['derived_ring_xyz_m'], float)
        uv = _i20_np.column_stack(((ring[:, [0, 2]] - _i20_np.asarray(station['origin_xyz_m'])[[0, 2]]) @ _i20_np.asarray(frame['transverse_unit_xz']), ring[:, 1] - origin[1]))
        aperture = Polygon(uv)
        _i20_require(aperture.is_valid and aperture.area > 0 and (not aperture.interiors), 'invalid immutable gallery port domain')
        _i20_compare(connection['gallery_aperture_uv_m'], uv, 'whole immutable gallery aperture', atol=1e-08)
        shapes = {}
        _i20_require(set(connection['exact_solid_slices']) == {'coupled_cutter', 'rock_after', 'removed'}, 'exact port slice census differs')
        for role, record in connection['exact_solid_slices'].items():
            shapes[role], _ = audit_slice(record, meshes[role], frame, {'artifact': role})
        blocked = aperture.intersection(shapes['rock_after']).area
        missing = aperture.difference(shapes['coupled_cutter']).area
        _i20_require(blocked <= 1e-08 and missing <= 1e-08, 'actual full port blocked or absent; no cap deletion permitted')
        _i20_compare(connection['exact_blocked_area_m2'], blocked, 'actual exact port blocked area', atol=1e-08)
        _i20_compare(connection['exact_missing_cutter_area_m2'], missing, 'actual exact port missing area', atol=1e-08)
        epsilon = min(0.001, minimum_distance / 16)
        _i20_require(connection['epsilon_rule'] == 'min_1mm_and_minimum_actual_exterior_support_distance_div16', 'changed bounded collar depth policy')
        bounds = aperture.bounds
        width, height = (bounds[2] - bounds[0], bounds[3] - bounds[1])
        basis = _i20_np.asarray([frame['transverse_unit_xyz'], frame['vertical_unit_xyz'], frame['normal_local_xyz']]).T
        center = _i20_np.asarray(frame['origin_local_xyz_m']) + _i20_np.asarray(frame['transverse_unit_xyz']) * ((bounds[0] + bounds[2]) / 2)
        center[1] = (bounds[1] + bounds[3]) / 2
        proof = connection['positive_volume_connection']
        _i20_require(set(proof['sides']) == {'surface', 'gallery'} and proof['constructed_by_intersecting_actual_cutters_not_new_excavation'] is True, 'whole two-sided positive-volume source proof missing')
        side_solids, side_reports = ([], {})
        surface_sign = -1.0 if kind == 'sink' else 1.0
        for side, sign, source in (('surface', surface_sign, 'surface_cutter'), ('gallery', -surface_sign, 'original_cutter')):
            side_proof = proof['sides'][side]
            role = kind + '_' + side + '_collar'
            _i20_require(side_proof['artifact'] == role and side_proof['source_solid'] == source and (side_proof['normal_side_sign'] == sign), 'two-sided source orientation differs')
            transform = _i20_np.column_stack((basis, center + sign * epsilon / 2 * _i20_np.asarray(frame['normal_local_xyz'])))
            _i20_compare(side_proof['slab_width_height_depth_m'], [width, height, epsilon], 'source collar slab dimensions', atol=1e-12)
            _i20_compare(side_proof['slab_transform_3x4'], transform, 'source collar frame/side', atol=1e-09)
            slab = library.Manifold.cube([width, height, epsilon], center=True).transform(transform)
            expected = meshes[source].manifold(library) ^ slab
            actual = meshes[role].manifold(library)
            _i20_require(not actual.is_empty() and actual.volume() > 0 and (len(actual.decompose()) == 1) and (volume_difference(expected, actual) <= 1e-07), 'collar not connected positive-volume actual source/slab intersection')
            _i20_compare(side_proof['positive_volume_m3'], actual.volume(), 'actual positive collar volume', atol=1e-07)
            domain, _ = audit_slice(side_proof['interface_solid_slice'], meshes[role], frame, {'artifact': role})
            gap = aperture.difference(domain).area
            _i20_require(gap <= 1e-08, 'two-sided collar does not cover complete immutable port')
            _i20_compare(side_proof['whole_aperture_uncovered_area_m2'], gap, 'whole port collar gap', atol=1e-08)
            side_solids.append(actual)
            side_reports[side] = {'mesh_pin': composition['mesh_pins'][role], 'volume_m3': actual.volume(), 'whole_port_gap_m2': gap, 'actual_source_solid': source}
        connected_role = kind + '_connected_collar'
        _i20_require(proof['connected_collar_artifact'] == connected_role, 'wrong saved connected collar')
        connected = meshes[connected_role].manifold(library)
        _i20_require(len(connected.decompose()) == proof['component_count'] == 1 and volume_difference(connected, side_solids[0] + side_solids[1]) <= 1e-07, 'two actual source collars not one connected saved volume')
        overlap = float((connected ^ meshes['rock_after'].manifold(library)).volume())
        _i20_require(overlap <= 1e-07, 'whole-port connection volume blocked by actual remaining rock')
        _i20_compare(proof['actual_rock_overlap_volume_m3'], overlap, 'saved connected collar actual rock overlap', atol=1e-07)
        _i20_require((connected - meshes['coupled_cutter'].manifold(library)).volume() <= 1e-07, 'connection proof adds fictitious excavation outside actual coupled cutter')
        traces = connection['one_sided_diagnostic_traces']
        _i20_require([trace['offset_m'] for trace in traces] == [-epsilon, -epsilon / 2, epsilon / 2, epsilon], 'offset diagnostics not bound to source-derived depth')
        for trace in traces:
            shifted = _i20_np.asarray(station['origin_xyz_m']) + trace['offset_m'] * _i20_np.asarray(frame['normal_local_xyz'])
            check_plane(trace['plane'], shifted, port['flow_unit_xz'], origin)
            _i20_require(set(trace['solid_slices']) == {'coupled_cutter', 'rock_after', 'removed'}, 'diagnostic trace census differs')
            for role, record in trace['solid_slices'].items():
                audit_slice(record, meshes[role], trace['plane'], {'artifact': role})
        reports[kind] = {'verified': True, 'port_identity_sha256': port['identity_sha256'], 'canonical_port_pin': attachment['canonical_port_pin'], 'two_sided_complete_port_verified': True, 'exact_blocked_area_m2': blocked, 'exact_missing_cutter_area_m2': missing, 'positive_volume_sides': side_reports, 'connected_collar_pin': composition['mesh_pins'][connected_role], 'actual_rock_overlap_volume_m3': overlap, 'offset_slices_not_acceptance_basis': True, 'scope': 'source_supported_full_canonical_port_local_positive_volume_join_not_whole_link_or_hydraulics'}
        _i20_check_memory()
    return reports

def audit_sampling_mismatches(saved, sampling, attachments):
    expected = []
    for kind in ('sink', 'spring'):
        attachment = attachments['attachments'][kind]
        node = _i20_read(attachment['surface_node_pin'])
        wanted = {'shared:' + node['node_id'] + ':' + str(index) for index in attachment['half_arm_triangle_indices']}
        fans = [fan for fan in attachment['compact_native_fans'] if fan['triangle_id'] in wanted]
        port = _i20_read(attachment['canonical_port_pin'])
        for sample in sampling['samples']:
            point = _i20_np.asarray(sample['xz_m'], float)
            if abs((point - port['midpoint_xz_m']) @ _i20_np.asarray(port['flow_unit_xz'])) > 1e-08:
                continue
            hits = []
            for fan in fans:
                vertices = _i20_np.asarray(fan['vertices_xz_m'])
                if _i20_np.any(point < vertices.min(axis=0)) or _i20_np.any(point > vertices.max(axis=0)):
                    continue
                depth = exact_fan_cut(fan, point)
                if depth is not None:
                    hits.append({'fan_key': fan['fan_key'], 'exact_domain_cut_depth_m': depth, 'saved_vertices_xz_m': fan['vertices_xz_m'], 'saved_vertex_depths_m': fan['depth_at_vertices_m']})
            if not hits:
                continue
            depths = [hit['exact_domain_cut_depth_m'] for hit in hits]
            _i20_require(max(depths) - min(depths) <= 1e-09, 'exact original shared fan depth mismatch')
            if abs(depths[0] - sample['cut_depth_m']) > 1e-09:
                expected.append({'kind': kind, 'source_sampling_row': sample['row'], 'source_sampling_column': sample['column'], 'point_xz_m': sample['xz_m'], 'saved_cut_depth_m': sample['cut_depth_m'], 'saved_fan_keys': sample['fan_keys'], 'saved_derived_bed_m': sample['derived_bed_m'], 'saved_original_source_sample': sample['source_sample'], 'exact_domain_supports': hits, 'expected_cut_depth_m': depths[0], 'sampled_top_excess_height_m': depths[0] - sample['cut_depth_m'], 'classification': 'saved_cut_lookup_mismatch_exact_domain_not_source_height_recalculation', 'scope': 'only_saved_port_plane_grid_samples_no_global_source_claim'})
    _i20_require(len(saved) == len(expected), 'original source sampling mismatch witness census differs')
    for actual, independent in zip(saved, expected):
        _i20_require(set(actual) == set(independent), 'source sampling mismatch fields differ')
        for field, value in independent.items():
            if field in ('expected_cut_depth_m', 'sampled_top_excess_height_m'):
                _i20_compare(actual[field], value, 'exact original source mismatch ' + field, atol=1e-12)
            elif field == 'exact_domain_supports':
                _i20_require(len(actual[field]) == len(value), 'source mismatch exact domain support census differs')
                for saved_hit, expected_hit in zip(actual[field], value):
                    for key in ('fan_key', 'saved_vertices_xz_m', 'saved_vertex_depths_m'):
                        _i20_require(saved_hit[key] == expected_hit[key], 'source mismatch support changed')
                    _i20_compare(saved_hit['exact_domain_cut_depth_m'], expected_hit['exact_domain_cut_depth_m'], 'source mismatch exact cut', atol=1e-12)
            else:
                _i20_require(actual[field] == value, 'source sampling mismatch source provenance differs: ' + field)
    return expected

def audit_hybrid_surface_composition_audit(composition_pin):
    record = _i20_read(composition_pin)
    _i20_require(record['schema'] == 'td-hybrid-surface-composition-v1' and record['status'] == 'candidate_unverified' and (not record['rejection_reasons']), 'refused/incomplete source composition cannot be accepted')
    inputs = record['inputs']
    _i20_require(set(inputs) == {'geometry', 'geometry_audit', 'graph', 'mesh_pins', 'vdm', 'surface_attachments', 'surface_nodes', 'original_source_sampling'} and inputs['geometry']['sha256'] == GEOMETRY_SHA256 and (inputs['geometry_audit']['sha256'] == GEOMETRY_AUDIT_SHA256), 'fixed geometry03 parents differ')
    geometry, old_audit, graph = (_i20_read(inputs['geometry']), _i20_read_audit(inputs['geometry_audit']), _i20_read(inputs['graph']))
    _i20_require(old_audit['status'] == 'passed' and (not old_audit['errors']) and (old_audit['geometry_sha256'] == GEOMETRY_SHA256) and (old_audit['geometry_identity_sha256'] == geometry['identity_sha256']) and (old_audit['mesh_pins'] == geometry['mesh_pins']) and (old_audit['inputs'] == geometry['inputs']) and (old_audit['actual_portal_connections_verified'] is True) and (old_audit['actual_hydraulic_sections_verified'] is True) and (graph['identity_sha256'] == geometry['graph_identity_sha256'] == record['graph_identity_sha256']) and (record['geometry_identity_sha256'] == geometry['identity_sha256']), 'original saved geometry parent chain differs')
    _i20_require(inputs['graph'] == geometry['inputs']['graph'] and inputs['mesh_pins'] == geometry['mesh_pins'] and (inputs['vdm'] == geometry['vdm_pin']) and (inputs['surface_attachments'] == geometry['surface_attachments_pin']) and (inputs['original_source_sampling'] == geometry['source_sampling_pin']), 'original saved sources changed')
    expected_code_names = {'terrain_pipeline/hybrid_surface_composition.py', 'tools/prepare_hybrid_surface_composition.py', 'tests/test_hybrid_surface_composition.py'}
    _i20_require(set(record['code_sha256']) == expected_code_names and record['code_sha256'] == FROZEN_COMPOSITION_CODE, 'composition frozen code identity differs')
    for parent in (record, geometry, old_audit):
        for group in ('code_sha256', 'readonly_dependency_code_sha256', 'audit_code_sha256'):
            for name, sha in parent.get(group, {}).items():
                _i20_require(_i20_file_sha256(ROOT / name) == sha, 'pinned implementation changed: ' + name)
    for parent in (geometry, graph):
        for pin in parent['inputs'].values():
            _i20_checked_path(pin)
    _i20_require(record['policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_POLICY and record['policy_identity_sha256'] == _i20_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_POLICY), 'unknown composition/source policy')
    for flag in ('vdm_moved', 'ports_moved', 'fill_generated', 'native_exact', 'fine15_replaced', 'independent_audit_passed', 'hydraulic_ready', 'hydraulic_solved', 'full_network_verified'):
        _i20_require(record[flag] is False, 'source composition prematurely promoted: ' + flag)
    _i20_require(record['original_sampled_rock_retained_cut_only_not_source_resampling'] is True, 'original source defects or repair semantics hidden')
    library = _i20_manifold_library()
    _i20_require(record['runtime']['manifold3d'] == '3.5.4' and record['runtime']['manifold3d_binary_sha256'] == _i20_file_sha256(library.__file__), 'composition Boolean runtime differs')
    attachments, vdm = (_i20_read(inputs['surface_attachments']), _i20_read(inputs['vdm']))
    sampling = _i20_read(inputs['original_source_sampling'])
    sampling_mismatches = audit_sampling_mismatches(record['original_source_sampling_cut_lookup_mismatches'], sampling, attachments)
    _i20_require(inputs['surface_nodes'] == {kind: attachment['surface_node_pin'] for kind, attachment in attachments['attachments'].items()} and set(inputs['surface_nodes']) == {'sink', 'spring'}, 'original half-arm node bindings differ')
    original_pins = {'rock_before': geometry['mesh_pins']['rock_before'], **{'original_' + role: geometry['mesh_pins'][role] for role in ('cutter', 'rock_after', 'removed')}}
    extra_roles = {kind + '_' + side + '_collar' for kind in ('sink', 'spring') for side in ('surface', 'gallery', 'connected')}
    expected_meshes = set(original_pins) | {'surface_cutter', 'coupled_cutter', 'rock_after', 'removed', 'extra_removed'} | extra_roles
    _i20_require(set(record['mesh_pins']) == expected_meshes and all((record['mesh_pins'][role] == pin for role, pin in original_pins.items())), 'original/new mesh identity or complete volume-proof census differs')
    meshes, origin = ({}, None)
    for role, pin in record['mesh_pins'].items():
        mesh = _i20_read(pin)
        local_origin = _i20_np.asarray(mesh['local_origin_xyz_m'], float)
        _i20_require(local_origin.shape == (3,) and _i20_np.isfinite(local_origin).all(), 'invalid common local mesh origin')
        if origin is None:
            origin = local_origin
        _i20_require(_i20_np.array_equal(origin, local_origin), 'composition solids not in common local frame')
        expected_role = role.removeprefix('original_')
        if role == 'removed':
            expected_role = 'total_removed'
        _i20_require(mesh['role'] == expected_role, 'saved mesh role substituted')
        if mesh['schema'] == 'td-hybrid-empty-solid-v1':
            _i20_require(role == 'extra_removed' and mesh['vertices_local_xyz_m'] == [] and (mesh['triangles'] == []) and (mesh['signed_volume_m3'] == 0.0), 'unknown/invalid empty material solid')
            meshes[role] = EmptySolid()
        else:
            _i20_require(mesh['schema'] == 'td-hybrid-local-solid-mesh-v1', 'unknown saved solid schema')
            meshes[role] = _i20_Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], role)
            _i20_compare(mesh['signed_volume_m3'], meshes[role].signed_volume, 'saved actual solid volume', atol=1e-07, rtol=1e-09)
    sections = _i20_read(geometry['inputs']['original_06_sections'])
    protection = _i20_read(geometry['inputs']['original_wet_protection_manifest'])['wet_protection']
    native = _i20_load_native(geometry['inputs']['original_hierarchy'], sections['selected_leaf_ids'], protection)
    prisms = _i20_read(record['surface_prisms_pin'])
    _, source_reports = audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    material = audit_material_solids(*(meshes[key] for key in ('rock_before', 'original_rock_after', 'original_removed', 'surface_cutter', 'coupled_cutter', 'rock_after', 'extra_removed', 'removed', 'original_cutter')))
    saved_material = record['material']
    for key, expected in (('original_rock_before_m3', meshes['rock_before'].signed_volume), ('original_removed_m3', material['original_removed_m3']), ('original_rock_after_m3', meshes['original_rock_after'].signed_volume), ('total_removed_m3', material['total_removed_m3']), ('extra_removed_m3', material['extra_removed_m3']), ('new_rock_after_m3', meshes['rock_after'].signed_volume)):
        _i20_compare(saved_material[key], expected, 'saved material ' + key, atol=1e-07, rtol=1e-09)
    residuals = [saved_material['original_rock_before_m3'] - saved_material['original_rock_after_m3'] - saved_material['original_removed_m3'], saved_material['original_rock_before_m3'] - saved_material['new_rock_after_m3'] - saved_material['total_removed_m3'], saved_material['total_removed_m3'] - saved_material['original_removed_m3'] - saved_material['extra_removed_m3']]
    _i20_compare(saved_material['signed_residuals_m3'], residuals, 'saved signed material residuals', atol=1e-07)
    _i20_require(saved_material['fill_m3'] == 0.0 and saved_material['fine15_material_replaced'] is False and (saved_material['sampled_solid_material_not_native_exact'] is True) and (abs(saved_material['residual_tolerance_m3'] - material['comparison_tolerance_m3']) <= 1e-12), 'fill or material accuracy policy changed')
    _i20_require(len(meshes['coupled_cutter'].manifold(library).decompose()) == record['coupled_cutter_component_count'] == 1, 'actual coupled cutter disconnected')
    errors = []
    portal_reports = {kind: {'verified': False, 'two_sided_complete_port_verified': False} for kind in ('sink', 'spring')}
    try:
        portal_reports = audit_connections(record, prisms, geometry, attachments, vdm, meshes, origin)
    except (ValueError, KeyError, TypeError, IndexError, RuntimeError) as error:
        errors.append('two-sided whole-port verification failed: ' + str(error))
    verified = not errors
    return {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_AUDIT_SCHEMA, 'status': 'passed' if verified else 'refused', 'errors': errors, 'composition_pin': composition_pin, 'composition_identity_sha256': record['identity_sha256'], 'inputs': inputs, 'mesh_pins': record['mesh_pins'], 'surface_prisms_pin': record['surface_prisms_pin'], 'geometry_sha256': GEOMETRY_SHA256, 'policy_identity_sha256': _i20_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_POLICY), 'native_half_arm_sources_verified': True, 'source_reports': source_reports, 'original_source_sampling_cut_lookup_mismatches': sampling_mismatches, 'materials_verified': True, 'material': material, 'portal_reports': portal_reports, 'two_sided_complete_port_verified': verified, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False, 'native_exact': False, 'fine15_replaced': False, 'original_sampling_defects_revalidated_as_correct': False, 'whole_link_control_sill_verified': False, 'scope': 'source_bound_piecewise_planar_surface_carve_increment_and_local_full_port_volume_connections', 'tolerances': {'canonical_boundary_m': 1e-08, 'whole_port_gap_area_m2': 1e-08, 'collar_boolean_difference_m3': 1e-07}}

def _entry_audit_hybrid_surface_composition():
    parser = _i20_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=_i20_Path, required=True)
    parser.add_argument('--composition-sha256', required=True)
    parser.add_argument('--output', type=_i20_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i20_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    pin = {'path': str(args.composition.resolve()), 'sha256': args.composition_sha256}
    started = _i20_time.monotonic()
    try:
        report = audit_hybrid_surface_composition_audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as error:
        report = {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_AUDIT_SCHEMA, 'status': 'refused', 'errors': [str(error)], 'composition_pin': pin, 'materials_verified': False, 'two_sided_complete_port_verified': False, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False}
    report['resource'] = {'wall_seconds': _i20_time.monotonic() - started, 'actual_peak_rss_bytes': _i20_check_memory(), 'solver_calls': 0, 'source_artifacts_modified': False}
    report['code_sha256'] = {name: _i20_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tests/test_hybrid_geometry_saved_audit.py', 'tools/audit_hybrid_geometry.py', 'tools/hybrid_cave_saved_audit.py', 'tools/td_shared_channel_fine_saved_audit.py')}
    report['identity_sha256'] = _i20_digest(report)
    payload = _i20_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i20_require(len(payload) <= _i20_MAX_BYTES, 'composition independent audit exceeds 64MiB file budget')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i20_json.dumps({'status': report['status'], 'errors': report['errors'], 'output': str(output), 'sha256': _i20_file_sha256(output), 'two_sided_complete_port_verified': report['two_sided_complete_port_verified']}))
    if report['status'] != 'passed':
        raise SystemExit(1)
_i21_sys.path.insert(0, str(ROOT))
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_AUDIT_SCHEMA = 'td-hybrid-surface-composition-independent-audit-v2'
SLICE_SCHEMA = 'td-hybrid-exact-mesh-plane-slice-v1'
NUMERICAL_POLICY = {'version': 'identity_cached_mesh_plane-v1', 'plane': 'exact_rational_sign_of_saved_binary64_coordinates_and_plane', 'intersection': 'one_exact_rational_intersection_per_original_unoriented_edge_then_binary64', 'identity': 'original_vertex_or_sorted_original_edge_ids_no_round_bucket_no_snap', 'regions': 'directed_identity_loops_polygonize_winding_holes_and_3D_occupancy_check', 'coplanar': 'oriented_original_facets_closed_trace_and_separate_positive_negative_interior_traces', 'geometry': 'unchanged_saved_Mesh64_no_CrossSection_grid', 'thresholds': 'no_area_or_distance_acceptance_threshold_relaxation'}
NUMERICAL_POLICY_SHA256 = _i21_digest(NUMERICAL_POLICY)
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY = {**AUDIT_HYBRID_SURFACE_COMPOSITION_POLICY, 'version': 'saved-native-halfarm-prism-composition-v2', 'numerical_slice': NUMERICAL_POLICY_SHA256, 'failure': 'saved_boolean_stage_and_material_before_port_checks_port_failure_preserves_artifacts'}
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_FROZEN_COMPOSITION_CODE = {'terrain_pipeline/hybrid_mesh_plane.py': 'ebe155432189c443e8bba0e0ef873873eeb7d4e65d46eaa7756c6877977e23f9', 'terrain_pipeline/hybrid_surface_composition_v2.py': '9ca048b281f6cbf3fa358d84bed4f9a9df97ebfe9e9b2ec2f66129311e0042bd', 'tools/prepare_hybrid_surface_composition_v2.py': 'c7d47d03afbd4c361d95a58c06468e8546a65ebfd7b2a96e19728907bb81509a', 'tests/test_hybrid_surface_composition_v2.py': '2e41c913fa454d64598664947dc0e9cc40cb3e95763ac30c7bc011f4bdd7c18c'}
FROZEN_HELPERS = {'tools/audit_hybrid_surface_composition.py': 'bb655a3a06ae410b22c72810d18a73a5c7b576b809a4ce9d0ef853255337b585'}
ERRORS = (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError)

def rational_vector(values):
    return [_i21_Fraction.from_float(float(value)) for value in values]

def dot(first, second):
    return sum((value * other for value, other in zip(first, second)))

def cross(first, second):
    return [first[1] * second[2] - first[2] * second[1], first[2] * second[0] - first[0] * second[2], first[0] * second[1] - first[1] * second[0]]

def independent_triangle_trace(solid, frame):
    origin, normal, transverse = [_i21_np.asarray(frame[key], float) for key in ('origin_local_xyz_m', 'normal_local_xyz', 'transverse_unit_xyz')]
    _i21_require(all((value.shape == (3,) and _i21_np.isfinite(value).all() for value in (origin, normal, transverse))), 'invalid exact plane frame')
    _i21_compare([_i21_np.linalg.norm(normal), _i21_np.linalg.norm(transverse), normal @ transverse], [1.0, 1.0, 0.0], 'exact plane orthonormal frame', atol=1e-12)
    _i21_require(normal[1] == transverse[1] == 0.0, 'exact plane must use horizontal normal/transverse')
    anchor, direction, lateral = map(rational_vector, (origin, normal, transverse))
    vertices = [rational_vector(point) for point in solid.vertices]
    distances = [dot([value - base for value, base in zip(point, anchor)], direction) for point in vertices]
    signs = [int(value > 0) - int(value < 0) for value in distances]
    nodes, segments, caps = ({}, {}, {})

    def vertex_node(index):
        return save_node('v:' + str(index), [index], vertices[index])

    def save_node(name, indices, point):
        uv = [float(dot([value - base for value, base in zip(point, anchor)], lateral)), float(point[1])]
        nodes[name] = {'node_id': name, 'vertex_indices': indices, 'point_local_xyz_m': list(map(float, point)), 'point_uv_m': uv}
        return name
    for ordinal, indices in enumerate(solid.triangles.tolist()):
        own_signs = [signs[index] for index in indices]
        if min(own_signs) > 0 or max(own_signs) < 0:
            continue
        points = [vertices[index] for index in indices]
        outward = cross([value - base for value, base in zip(points[1], points[0])], [value - base for value, base in zip(points[2], points[0])])
        if own_signs == [0, 0, 0]:
            ids = [vertex_node(index) for index in indices]
            orientation = dot(outward, direction)
            _i21_require(orientation != 0, 'degenerate coplanar original triangle')
            caps[ordinal] = {'triangle_index': ordinal, 'vertex_indices': indices, 'intersection_node_ids': ids, 'polygon_uv_m': [nodes[name]['point_uv_m'] for name in ids], 'normal_dot_plane': float(orientation), 'occupied_incident_side': 'negative' if orientation > 0 else 'positive'}
            continue
        ids = []
        exact_points = {}
        for first, second in zip(indices, indices[1:] + indices[:1]):
            if signs[first] == 0:
                name = vertex_node(first)
                ids.append(name)
                exact_points[name] = vertices[first]
            if signs[first] * signs[second] < 0:
                low, high = sorted((first, second))
                fraction = distances[low] / (distances[low] - distances[high])
                point = [base + fraction * (end - base) for base, end in zip(vertices[low], vertices[high])]
                name = save_node('e:' + str(low) + ':' + str(high), [low, high], point)
                ids.append(name)
                exact_points[name] = point
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2:
            continue
        _i21_require(len(ids) == 2, 'ambiguous original triangle intersection')
        orientation = dot([end - start for start, end in zip(exact_points[ids[0]], exact_points[ids[1]])], cross(direction, outward))
        _i21_require(orientation != 0, 'degenerate original slice segment')
        if orientation < 0:
            ids.reverse()
        incident = 'both' if min(own_signs) < 0 < max(own_signs) else 'positive' if max(own_signs) > 0 else 'negative'
        segments[ordinal] = {'triangle_index': ordinal, 'vertex_indices': indices, 'intersection_node_ids': ids, 'incident_halfspace': incident, 'points_local_xyz_m': [nodes[name]['point_local_xyz_m'] for name in ids], 'points_uv_m': [nodes[name]['point_uv_m'] for name in ids]}
    return (nodes, segments, caps, signs)

def check_census(saved, expected, key, label):
    _i21_require(isinstance(saved, list) and len(saved) == len(expected), label + ' census differs')
    actual = {}
    for item in saved:
        name = item[key]
        _i21_require(name not in actual and name in expected, label + ' duplicate/unknown reference')
        actual[name] = item
        _i21_require(item == expected[name], label + ' source value/reference differs')

def signed_area(points):
    offsets = _i21_np.asarray(points, float) - _i21_np.asarray(points[0], float)
    return _i21_math.fsum((float(first[0] * second[1] - first[1] * second[0]) for first, second in zip(offsets, _i21_np.roll(offsets, -1, axis=0)))) / 2.0

def audit_side_loops(loops, side, nodes, segments):
    from shapely.geometry import LineString
    from shapely.geometry import Polygon
    from shapely.ops import polygonize_full
    from shapely.ops import unary_union
    coefficients, supports = (_i21_Counter(), _i21_defaultdict(list))
    for ordinal, segment in segments.items():
        if segment['incident_halfspace'] in (side, 'both'):
            first, second = segment['intersection_node_ids']
            key = tuple(sorted((first, second)))
            coefficients[key] += 1 if key == (first, second) else -1
            supports[key].append(ordinal)
    expected = _i21_Counter()
    for key, count in coefficients.items():
        _i21_require(abs(count) <= 1, 'duplicate/nonmanifold exact identity edge')
        if count:
            expected[key if count > 0 else key[::-1]] += 1
    observed, loop_polygons = (_i21_Counter(), [])
    for loop in loops:
        if loop['side'] != side:
            continue
        ids = loop['node_ids']
        _i21_require(len(ids) >= 3 and len(set(ids)) == len(ids) and all((name in nodes for name in ids)), 'open/repeated/unknown exact loop node')
        edges = list(zip(ids, ids[1:] + ids[:1]))
        observed.update(edges)
        _i21_require(loop['triangle_supports'] == [supports[tuple(sorted(edge))] for edge in edges], 'loop original triangle support differs')
        points = [nodes[name]['point_uv_m'] for name in ids]
        area = signed_area(points)
        _i21_compare(loop['signed_area_m2'], area, 'loop signed area', atol=max(1e-14, abs(area) * 2e-15))
        polygon = Polygon(points)
        _i21_require(polygon.is_valid and polygon.area > 0 and (area != 0), 'invalid exact loop geometry')
        loop_polygons.append((polygon, 1 if area > 0 else -1))
    _i21_require(observed == expected, 'loop edges do not exhaust original oriented side trace')
    outgoing, incoming = (_i21_Counter((edge[0] for edge in expected)), _i21_Counter((edge[1] for edge in expected)))
    _i21_require(outgoing == incoming and all((count == 1 for count in outgoing.values())), 'branched/unclosed exact side trace')
    lines = [LineString([nodes[first]['point_uv_m'], nodes[second]['point_uv_m']]) for first, second in expected]
    if not lines:
        return Polygon()
    cells, cuts, dangles, invalid = polygonize_full(lines)
    _i21_require(cuts.is_empty and dangles.is_empty and invalid.is_empty, 'incomplete planar identity arrangement')
    retained = []
    for cell in cells.geoms:
        query = cell.representative_point()
        winding = sum((sign for polygon, sign in loop_polygons if polygon.covers(query)))
        _i21_require(winding in (0, 1), 'invalid oriented hole/component winding')
        if winding:
            retained.append(cell)
    return unary_union(retained)

def polygon_parts(shape):
    _i21_require(shape.is_empty or shape.geom_type in ('Polygon', 'MultiPolygon'), 'nonpolygon slice region')
    return [] if shape.is_empty else [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)

def domain_parts(shape):
    from shapely.geometry import GeometryCollection
    from shapely.ops import unary_union
    polygons, lines, points = ([], [], [])
    pending = [shape]
    while pending:
        item = pending.pop()
        if item.is_empty:
            continue
        if item.geom_type == 'Polygon':
            polygons.append(item)
        elif item.geom_type in ('LineString', 'LinearRing'):
            lines.append(item)
        elif item.geom_type == 'Point':
            points.append(tuple(item.coords[0]))
        elif item.geom_type in ('MultiPolygon', 'MultiLineString', 'MultiPoint', 'GeometryCollection'):
            pending.extend(item.geoms)
        else:
            raise ValueError('unknown saved contact domain dimension')
    return (unary_union(polygons), unary_union(lines) if lines else GeometryCollection(), set(points))

def check_shape(record, expected, label, require_contacts=False):
    from shapely.geometry import GeometryCollection
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    expected_area, expected_lines, expected_points = domain_parts(expected)
    supplied = saved_slice_geometry(record)
    difference = supplied.symmetric_difference(expected_area).area
    _i21_require(difference <= 1e-08, label + ' saved components/holes differ from identity trace')
    _i21_compare(record['area_m2'], expected_area.area, label + ' area', atol=1e-08)
    if require_contacts or 'contact_lines_uv_m' in record or 'contact_points_uv_m' in record:
        saved_lines = []
        for points in record['contact_lines_uv_m']:
            values = _i21_np.asarray(points, float)
            _i21_require(values.ndim == 2 and values.shape[1] == 2 and (len(values) >= 2) and _i21_np.isfinite(values).all(), label + ' invalid contact line')
            line = LineString(values)
            _i21_require(line.is_valid and line.length > 0, label + ' degenerate contact line')
            saved_lines.append(line)
        lines = unary_union(saved_lines) if saved_lines else GeometryCollection()
        _i21_require(lines.equals(expected_lines), label + ' contact lines differ from actual zero-area trace')
        saved_points = record['contact_points_uv_m']
        _i21_require(all((len(point) == 2 and all((_i21_math.isfinite(value) for value in point)) for point in saved_points)) and len(set(map(tuple, saved_points))) == len(saved_points) and (set(map(tuple, saved_points)) == expected_points), label + ' contact points differ from actual zero-area trace')
    else:
        _i21_require(expected_lines.is_empty and (not expected_points), label + ' missing explicit contact domain fields')
    return difference

def audit_exact_slice(record, solid, frame, pin):
    """Return independently verified closed-trace shape and compact source evidence."""
    from shapely.geometry import Point
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    _i21_check_identity(record)
    _i21_require(record['schema'] == SLICE_SCHEMA and record['mesh_pin'] == pin and (record['coordinate_convention'] == frame['coordinate_convention']) and (record['method'] == 'original_identity_cached_rational_mesh_plane_no_CrossSection') and (record['numerical_policy'] == NUMERICAL_POLICY) and (record['numerical_policy_identity_sha256'] == NUMERICAL_POLICY_SHA256), 'exact slice schema/source/numerical policy binding differs')
    nodes, segments, caps, signs = independent_triangle_trace(solid, frame)
    _i21_require(record['vertex_plane_classifications'] == [{'vertex_index': index, 'sign': sign, 'classification_method': 'exact_rational'} for index, sign in enumerate(signs)], 'saved exact vertex signs differ')
    check_census(record['intersection_nodes'], nodes, 'node_id', 'shared-edge intersection')
    check_census(record['triangle_segments'], segments, 'triangle_index', 'original segment')
    check_census(record['coplanar_triangle_supports'], caps, 'triangle_index', 'oriented coplanar facet')
    loops = record['identity_loops']
    _i21_require(all((loop['side'] in ('positive', 'negative') for loop in loops)), 'unknown loop incident side')
    sides = {side: audit_side_loops(loops, side, nodes, segments) for side in ('positive', 'negative')}
    _i21_require(set(record['one_sided_interior_traces']) == set(sides), 'one-sided slice census differs')
    for side, shape in sides.items():
        check_shape(record['one_sided_interior_traces'][side], shape, side + ' trace')
    cap_shape = unary_union([Polygon(item['polygon_uv_m']) for item in caps.values()])
    actual = unary_union([*sides.values(), cap_shape])
    _i21_require(actual.is_valid and record['coplanar_semantics'] == 'closed_trace_contains_actual_original_facets_side_occupation_recorded', 'invalid coplanar occupancy semantics')
    difference = check_shape(record, actual, 'closed exact slice')
    witnesses = record['occupancy_witnesses']
    parts = polygon_parts(actual)
    holes = [Polygon(hole).difference(actual) for polygon in parts for hole in polygon.interiors]
    holes = [hole for hole in holes if not hole.is_empty]
    _i21_require(len(witnesses) == len(parts) + len(holes), 'component/hole occupancy witness census differs')
    covered, covered_holes = (set(), set())
    for witness in witnesses:
        query = Point(witness['point_uv_m'])
        inside = witness['region'] == 'retained_polygon'
        _i21_require(inside or witness['region'] == 'excluded_hole', 'unknown occupancy witness region')
        candidates = [index for index, polygon in enumerate(parts if inside else holes) if polygon.contains(query)]
        visited = covered if inside else covered_holes
        _i21_require(len(candidates) == 1 and candidates[0] not in visited, 'duplicate/outside occupancy witness')
        visited.add(candidates[0])
        point = _i21_np.asarray(frame['origin_local_xyz_m']) + query.x * _i21_np.asarray(frame['transverse_unit_xyz'])
        point[1] = query.y
        _i21_compare(witness['point_local_xyz_m'], point, 'occupancy witness frame', atol=1e-12)
        if cap_shape.covers(query):
            _i21_require(inside and witness['classification'] == 'original_oriented_coplanar_boundary_facet' and (witness['coplanar_triangle_indices'] == [ordinal for ordinal, cap in caps.items() if Polygon(cap['polygon_uv_m']).covers(query)]), 'coplanar occupancy classified as free interior')
        else:
            classification = 'original_Mesh64_interior_two_ray_parities' if inside else 'original_Mesh64_void_two_ray_parities'
            expected = 1 if inside else 0
            _i21_require(witness['classification'] == classification and witness['ray_parities'] == [expected, expected], 'missing saved interior/void occupancy evidence')
            _i21_require(abs(solid.winding(point) - expected) <= 1e-07, 'independent original solid occupancy failed')
    hole_probes = 0
    for polygon in parts:
        for hole in polygon.interiors:
            region = Polygon(hole).difference(actual)
            for empty in polygon_parts(region):
                query = empty.representative_point()
                point = _i21_np.asarray(frame['origin_local_xyz_m']) + query.x * _i21_np.asarray(frame['transverse_unit_xyz'])
                point[1] = query.y
                _i21_require(not cap_shape.covers(query) and abs(solid.winding(point)) <= 1e-07, 'saved hole conceals occupied original solid')
                hole_probes += 1
    _i21_check_memory()
    return (actual, {'schema': 'td-hybrid-exact-slice-independent-evidence-v1', 'verified': True, 'mesh_pin': pin, 'slice_identity_sha256': record['identity_sha256'], 'numerical_policy_identity_sha256': NUMERICAL_POLICY_SHA256, 'area_m2': float(actual.area), 'symmetric_difference_m2': float(difference), 'triangle_segments': len(segments), 'coplanar_triangles': len(caps), 'shared_intersection_nodes': len(nodes), 'identity_loops': len(loops), 'component_occupancy_witnesses': len(witnesses), 'independent_hole_occupancy_probes': hole_probes, 'builder_or_slicer_called': False, 'coplanar_facets_removed': False})

def audit_port(kind, composition, prisms, geometry, attachments, vdm, meshes, origin, evidence):
    from shapely.geometry import Polygon
    library = _i21_manifold_library()
    ordinal = 0 if kind == 'sink' else len(vdm['stations']) - 1
    connection = composition['portal_connections'][kind]
    attachment = attachments['attachments'][kind]
    port = _i21_read(attachment['canonical_port_pin'])
    station = vdm['stations'][ordinal]
    _i21_require(port['identity_sha256'] == geometry['portal_bindings'][kind]['port_identity_sha256'] and connection['original_complete_port_proof'] == attachment['actual_complete_port_proof'] and (connection['immutable_gallery_station_index'] == ordinal) and (connection['offset_traces_are_diagnostic_only'] is True) and (connection['hydraulic_boundary_certified'] is False) and (connection['full_shared_interface_supported'] is True) and (connection['canonical_whole_piece_witnesses'] == prisms['half_arms'][kind]['canonical_whole_piece_witnesses']), 'canonical original source/whole-port claim differs')
    distance = audit_canonical_pieces(connection['canonical_whole_piece_witnesses'], attachment['actual_complete_port_proof'], prisms['half_arms'][kind]['bottom_triangles'], port['flow_unit_xz'], kind, station)
    frame = connection['plane']
    check_plane(frame, station['origin_xyz_m'], port['flow_unit_xz'], origin)
    ring = _i21_np.asarray(station['derived_ring_xyz_m'])
    uv = _i21_np.column_stack(((ring[:, [0, 2]] - _i21_np.asarray(station['origin_xyz_m'])[[0, 2]]) @ _i21_np.asarray(frame['transverse_unit_xz']), ring[:, 1] - origin[1]))
    aperture = Polygon(uv)
    _i21_require(aperture.is_valid and aperture.area > 0 and (not aperture.interiors), 'invalid immutable port')
    _i21_compare(connection['gallery_aperture_uv_m'], uv, 'immutable whole port', atol=1e-08)

    def checked_slice(record, role, plane, label):
        shape, report = audit_exact_slice(record, meshes[role], plane, {'artifact': role})
        report['source_mesh_pin'] = composition['mesh_pins'][role]
        evidence[label] = report
        return shape
    _i21_require(set(connection['exact_solid_slices']) == {'coupled_cutter', 'rock_after', 'removed'}, 'whole-port solid slice census differs')
    shapes = {role: checked_slice(record, role, frame, 'canonical:' + role) for role, record in connection['exact_solid_slices'].items()}
    blocked = aperture.intersection(shapes['rock_after'])
    missing = aperture.difference(shapes['coupled_cutter'])
    _i21_compare(connection['exact_blocked_area_m2'], blocked.area, 'actual whole-port blockage', atol=1e-08)
    _i21_compare(connection['exact_missing_cutter_area_m2'], missing.area, 'actual whole-port missing', atol=1e-08)
    check_shape(connection['blocked_domain'], blocked, 'blocked port', require_contacts=True)
    check_shape(connection['missing_domain'], missing, 'missing port', require_contacts=True)
    evidence['whole_port_metrics'] = {'exact_blocked_area_m2': float(blocked.area), 'exact_missing_cutter_area_m2': float(missing.area)}
    _i21_require(blocked.area <= 1e-08 and missing.area <= 1e-08, 'actual full port blocked or missing')
    epsilon = min(0.001, distance / 16)
    _i21_require(connection['epsilon_rule'] == 'min_1mm_and_minimum_actual_exterior_support_distance_div16', 'collar depth policy changed')
    bounds = aperture.bounds
    width, height = (bounds[2] - bounds[0], bounds[3] - bounds[1])
    basis = _i21_np.asarray([frame['transverse_unit_xyz'], frame['vertical_unit_xyz'], frame['normal_local_xyz']]).T
    center = _i21_np.asarray(frame['origin_local_xyz_m']) + _i21_np.asarray(frame['transverse_unit_xyz']) * ((bounds[0] + bounds[2]) / 2)
    center[1] = (bounds[1] + bounds[3]) / 2
    proof = connection['positive_volume_connection']
    _i21_require(set(proof['sides']) == {'surface', 'gallery'} and proof['constructed_by_intersecting_actual_cutters_not_new_excavation'] is True, 'missing two-sided actual source-volume proof')
    surface_sign = -1.0 if kind == 'sink' else 1.0
    side_solids, side_reports = ([], {})
    for side, sign, source in (('surface', surface_sign, 'surface_cutter'), ('gallery', -surface_sign, 'original_cutter')):
        saved = proof['sides'][side]
        role = kind + '_' + side + '_collar'
        _i21_require(saved['artifact'] == role and saved['source_solid'] == source and (saved['normal_side_sign'] == sign), 'collar source/orientation differs')
        transform = _i21_np.column_stack((basis, center + sign * epsilon / 2 * _i21_np.asarray(frame['normal_local_xyz'])))
        _i21_compare(saved['slab_width_height_depth_m'], [width, height, epsilon], 'collar dimensions', atol=1e-12)
        _i21_compare(saved['slab_transform_3x4'], transform, 'collar side frame', atol=1e-09)
        slab = library.Manifold.cube([width, height, epsilon], center=True).transform(transform)
        expected = meshes[source].manifold(library) ^ slab
        actual = meshes[role].manifold(library)
        _i21_require(actual.volume() > 0 and len(actual.decompose()) == saved['component_count'] == 1 and (volume_difference(expected, actual) <= 1e-07), 'collar not actual connected source/slab intersection')
        _i21_compare(saved['positive_volume_m3'], actual.volume(), 'collar volume', atol=1e-07)
        domain = checked_slice(saved['interface_solid_slice'], role, frame, 'collar:' + side)
        gap = aperture.difference(domain)
        _i21_compare(saved['whole_aperture_uncovered_area_m2'], gap.area, 'whole collar gap', atol=1e-08)
        check_shape(saved['uncovered_domain'], gap, 'collar uncovered domain', require_contacts=True)
        _i21_require(gap.area <= 1e-08, 'whole port not covered by both actual volume collars')
        side_solids.append(actual)
        side_reports[side] = {'mesh_pin': composition['mesh_pins'][role], 'volume_m3': float(actual.volume()), 'whole_port_gap_m2': float(gap.area), 'actual_source_solid': source}
    role = kind + '_connected_collar'
    connected = meshes[role].manifold(library)
    _i21_require(proof['connected_collar_artifact'] == role and len(connected.decompose()) == proof['component_count'] == 1 and (volume_difference(connected, side_solids[0] + side_solids[1]) <= 1e-07), 'source collars not one saved connected volume')
    overlap = float((connected ^ meshes['rock_after'].manifold(library)).volume())
    _i21_require(overlap <= 1e-07 and (connected - meshes['coupled_cutter'].manifold(library)).volume() <= 1e-07, 'collar blocked or outside actual cutter')
    _i21_compare(proof['actual_rock_overlap_volume_m3'], overlap, 'actual collar rock overlap', atol=1e-07)
    traces = connection['one_sided_diagnostic_traces']
    _i21_require([trace['offset_m'] for trace in traces] == [-epsilon, -epsilon / 2, epsilon / 2, epsilon], 'offset diagnostics not source-depth-bound')
    for index, trace in enumerate(traces):
        shifted = _i21_np.asarray(station['origin_xyz_m']) + trace['offset_m'] * _i21_np.asarray(frame['normal_local_xyz'])
        check_plane(trace['plane'], shifted, port['flow_unit_xz'], origin)
        _i21_require(set(trace['solid_slices']) == set(shapes), 'diagnostic solid slice census differs')
        for source, record in trace['solid_slices'].items():
            checked_slice(record, source, trace['plane'], 'offset:' + str(index) + ':' + source)
    _i21_require(connection['status'] == 'verified_geometry_unverified_audit' and connection['two_sided_complete_port_verified'] is True and (not connection['rejection_reasons']), 'producer whole-port status disagrees with evidence')
    return {'verified': True, 'port_identity_sha256': port['identity_sha256'], 'canonical_port_pin': attachment['canonical_port_pin'], 'two_sided_complete_port_verified': True, 'exact_blocked_area_m2': float(blocked.area), 'exact_missing_cutter_area_m2': float(missing.area), 'positive_volume_sides': side_reports, 'connected_collar_pin': composition['mesh_pins'][role], 'actual_rock_overlap_volume_m3': overlap, 'offset_slices_not_acceptance_basis': True, 'scope': 'local_source_supported_full_port_volume_join_not_whole_link_or_hydraulics'}

def check_code_pins(record):
    _i21_require(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_FROZEN_COMPOSITION_CODE and record['code_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_FROZEN_COMPOSITION_CODE, 'composition v2 frozen implementation identity differs')
    for name, sha in {**FROZEN_HELPERS, **FROZEN_COMPOSITION_CODE}.items():
        _i21_require(_i21_file_sha256(ROOT / name) == sha, 'frozen v1 dependency changed: ' + name)
    for group in ('code_sha256', 'readonly_dependency_code_sha256', 'audit_code_sha256'):
        for name, sha in record.get(group, {}).items():
            _i21_require(_i21_file_sha256(ROOT / name) == sha, 'pinned implementation changed: ' + name)

def audit_hybrid_surface_composition_mechanism_2_audit(composition_pin):
    record = _i21_read(composition_pin)
    _i21_require(record['schema'] == 'td-hybrid-surface-composition-v2' and record['status'] in ('candidate_unverified', 'refused') and (record['boolean_stage_preserved'] is True), 'unknown/incomplete composition v2 stage')
    check_code_pins(record)
    inputs = record['inputs']
    _i21_require(set(inputs) == {'geometry', 'geometry_audit', 'graph', 'mesh_pins', 'vdm', 'surface_attachments', 'surface_nodes', 'original_source_sampling'} and inputs['geometry']['sha256'] == GEOMETRY_SHA256 and (inputs['geometry_audit']['sha256'] == GEOMETRY_AUDIT_SHA256), 'fixed geometry03 pins differ')
    geometry, old_audit, graph = (_i21_read(inputs['geometry']), _i21_read_audit(inputs['geometry_audit']), _i21_read(inputs['graph']))
    for parent in (geometry, old_audit):
        for group in ('code_sha256', 'readonly_dependency_code_sha256', 'audit_code_sha256'):
            for name, sha in parent.get(group, {}).items():
                _i21_require(_i21_file_sha256(ROOT / name) == sha, 'geometry03 implementation changed: ' + name)
    _i21_require(old_audit['status'] == 'passed' and (not old_audit['errors']) and (old_audit['geometry_sha256'] == GEOMETRY_SHA256) and (old_audit['geometry_identity_sha256'] == geometry['identity_sha256']) and (old_audit['mesh_pins'] == geometry['mesh_pins']) and (old_audit['inputs'] == geometry['inputs']) and (old_audit['actual_portal_connections_verified'] is True) and (old_audit['actual_hydraulic_sections_verified'] is True) and (graph['identity_sha256'] == geometry['graph_identity_sha256'] == record['graph_identity_sha256']) and (record['geometry_identity_sha256'] == geometry['identity_sha256']), 'original accepted geometry chain differs')
    _i21_require(inputs['graph'] == geometry['inputs']['graph'] and inputs['mesh_pins'] == geometry['mesh_pins'] and (inputs['vdm'] == geometry['vdm_pin']) and (inputs['surface_attachments'] == geometry['surface_attachments_pin']) and (inputs['original_source_sampling'] == geometry['source_sampling_pin']), 'immutable sources changed')
    _i21_require(record['policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY and record['policy_identity_sha256'] == _i21_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY) and (record['numerical_slice_policy'] == NUMERICAL_POLICY) and (record['numerical_slice_policy_identity_sha256'] == NUMERICAL_POLICY_SHA256), 'unknown composition/slice policy')
    for flag in ('vdm_moved', 'ports_moved', 'fill_generated', 'native_exact', 'fine15_replaced', 'independent_audit_passed', 'hydraulic_ready', 'hydraulic_solved', 'full_network_verified'):
        _i21_require(record[flag] is False, 'prematurely promoted source composition: ' + flag)
    _i21_require(record['original_sampled_rock_retained_cut_only_not_source_resampling'] is True, 'original sampled-source repair semantics concealed')
    library = _i21_manifold_library()
    _i21_require(record['runtime']['manifold3d'] == '3.5.4' and record['runtime']['manifold3d_binary_sha256'] == _i21_file_sha256(library.__file__), 'Boolean runtime differs')
    attachments, vdm = (_i21_read(inputs['surface_attachments']), _i21_read(inputs['vdm']))
    _i21_require(inputs['surface_nodes'] == {kind: attachment['surface_node_pin'] for kind, attachment in attachments['attachments'].items()} and set(inputs['surface_nodes']) == {'sink', 'spring'}, 'original half-arm node bindings differ')
    sampling_mismatches = audit_sampling_mismatches(record['original_source_sampling_cut_lookup_mismatches'], _i21_read(inputs['original_source_sampling']), attachments)
    originals = {'rock_before': geometry['mesh_pins']['rock_before'], **{'original_' + role: geometry['mesh_pins'][role] for role in ('cutter', 'rock_after', 'removed')}}
    base_roles = set(originals) | {'surface_cutter', 'coupled_cutter', 'rock_after', 'removed', 'extra_removed'}
    collar_roles = {kind + '_' + side + '_collar' for kind in ('sink', 'spring') for side in ('surface', 'gallery', 'connected')}
    _i21_require(base_roles <= set(record['mesh_pins']) <= base_roles | collar_roles and all((record['mesh_pins'][role] == pin for role, pin in originals.items())), 'mesh census/source bindings differ')
    checkpoint = _i21_read(record['checkpoint_boolean_pin'])
    _i21_require(checkpoint['schema'] == 'td-hybrid-surface-composition-boolean-checkpoint-v2' and checkpoint['status'] == 'boolean_stage_unverified' and (checkpoint['portal_checks_started'] is False) and (checkpoint['inputs'] == inputs) and (checkpoint['code_sha256'] == record['code_sha256']) and (checkpoint['readonly_dependency_code_sha256'] == record['readonly_dependency_code_sha256']) and (checkpoint['runtime'] == record['runtime']) and (checkpoint['material'] == record['material']) and (checkpoint['numerical_slice_policy'] == NUMERICAL_POLICY) and (checkpoint['numerical_slice_policy_identity_sha256'] == NUMERICAL_POLICY_SHA256), 'Boolean checkpoint source/material/policy binding differs')
    stage = checkpoint['composition_stage']
    _i21_check_identity(stage)
    _i21_require(stage['schema'] == record['schema'] and stage['status'] == 'boolean_stage_unverified' and (not stage['rejection_reasons']), 'unknown Boolean composition stage')
    for field in ('policy', 'policy_identity_sha256', 'numerical_slice_policy', 'numerical_slice_policy_identity_sha256', 'geometry_identity_sha256', 'graph_identity_sha256', 'material', 'coupled_cutter_component_count', 'original_source_sampling_cut_lookup_mismatches'):
        _i21_require(stage[field] == record[field], 'Boolean/final composition field differs: ' + field)
    artifacts = checkpoint['artifacts']
    _i21_require(set(artifacts) == base_roles - set(originals) | {'surface_prisms'} and artifacts['surface_prisms'] == record['surface_prisms_pin'] and all((artifacts[role] == record['mesh_pins'][role] for role in base_roles - set(originals))), 'Boolean checkpoint artifact pins differ')
    meshes, origin = ({}, None)
    for role, pin in record['mesh_pins'].items():
        mesh = _i21_read(pin)
        current = _i21_np.asarray(mesh['local_origin_xyz_m'], float)
        _i21_require(current.shape == (3,) and _i21_np.isfinite(current).all(), 'invalid local solid origin')
        if origin is None:
            origin = current
        _i21_require(_i21_np.array_equal(current, origin), 'solids do not share original local origin')
        expected_role = role.removeprefix('original_')
        _i21_require(mesh['role'] == expected_role, 'saved solid role differs')
        if mesh['schema'] == 'td-hybrid-empty-solid-v1':
            _i21_require(role == 'extra_removed' and mesh['vertices_local_xyz_m'] == [] and (mesh['triangles'] == []) and (mesh['signed_volume_m3'] == 0.0), 'invalid empty solid')
            meshes[role] = EmptySolid()
        else:
            _i21_require(mesh['schema'] == 'td-hybrid-local-solid-mesh-v1', 'unknown solid schema')
            meshes[role] = _i21_Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], role)
            _i21_compare(mesh['signed_volume_m3'], meshes[role].signed_volume, 'saved actual solid volume', atol=1e-07, rtol=1e-09)
    sections = _i21_read(geometry['inputs']['original_06_sections'])
    protection = _i21_read(geometry['inputs']['original_wet_protection_manifest'])['wet_protection']
    native = _i21_load_native(geometry['inputs']['original_hierarchy'], sections['selected_leaf_ids'], protection)
    prisms = _i21_read(record['surface_prisms_pin'])
    _, source_reports = audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    material = audit_material_solids(*(meshes[key] for key in ('rock_before', 'original_rock_after', 'original_removed', 'surface_cutter', 'coupled_cutter', 'rock_after', 'extra_removed', 'removed', 'original_cutter')))
    saved = record['material']
    for key, expected in (('original_rock_before_m3', meshes['rock_before'].signed_volume), ('original_rock_after_m3', meshes['original_rock_after'].signed_volume), ('new_rock_after_m3', meshes['rock_after'].signed_volume), *((key, material[key]) for key in ('original_removed_m3', 'extra_removed_m3', 'total_removed_m3'))):
        _i21_compare(saved[key], expected, 'saved material ' + key, atol=1e-07, rtol=1e-09)
    residuals = [saved['original_rock_before_m3'] - saved['original_rock_after_m3'] - saved['original_removed_m3'], saved['original_rock_before_m3'] - saved['new_rock_after_m3'] - saved['total_removed_m3'], saved['total_removed_m3'] - saved['original_removed_m3'] - saved['extra_removed_m3']]
    _i21_compare(saved['signed_residuals_m3'], residuals, 'signed material residuals', atol=1e-07)
    _i21_require(saved['fill_m3'] == 0.0 and saved['fine15_material_replaced'] is False and (saved['sampled_solid_material_not_native_exact'] is True) and (abs(saved['residual_tolerance_m3'] - material['comparison_tolerance_m3']) <= 1e-12), 'material semantics or tolerance changed')
    errors, portal_reports, evidence = ([], {}, {})
    if len(meshes['coupled_cutter'].manifold(library).decompose()) != record['coupled_cutter_component_count'] or record['coupled_cutter_component_count'] != 1:
        errors.append('actual coupled cutter not one component')
    _i21_require(set(record['portal_connections']) == {'sink', 'spring'}, 'missing canonical ports')
    for kind in ('sink', 'spring'):
        evidence[kind] = {}
        try:
            portal_reports[kind] = audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, evidence[kind])
        except ERRORS as error:
            errors.append(kind + ': ' + str(error))
            portal_reports[kind] = {'verified': False, 'two_sided_complete_port_verified': False, 'errors': [str(error)]}
    if record['status'] != 'candidate_unverified' or record['rejection_reasons']:
        errors.append('producer refused composition: ' + '; '.join(record['rejection_reasons']))
    verified = not errors
    return {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_AUDIT_SCHEMA, 'status': 'passed' if verified else 'refused', 'errors': errors, 'composition_pin': composition_pin, 'composition_identity_sha256': record['identity_sha256'], 'inputs': inputs, 'mesh_pins': record['mesh_pins'], 'surface_prisms_pin': record['surface_prisms_pin'], 'checkpoint_boolean_pin': record['checkpoint_boolean_pin'], 'geometry_sha256': GEOMETRY_SHA256, 'policy_identity_sha256': _i21_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY), 'numerical_slice_policy': NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': NUMERICAL_POLICY_SHA256, 'native_half_arm_sources_verified': True, 'source_reports': source_reports, 'original_source_sampling_cut_lookup_mismatches': sampling_mismatches, 'materials_verified': True, 'material': material, 'portal_reports': portal_reports, 'exact_slice_reports': evidence, 'two_sided_complete_port_verified': verified, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False, 'native_exact': False, 'fine15_replaced': False, 'original_sampling_defects_revalidated_as_correct': False, 'whole_link_control_sill_verified': False, 'builder_or_slicer_called': False, 'scope': 'source_bound_piecewise_planar_carve_material_and_local_full_port_connections_only', 'tolerances': {'canonical_boundary_m': 1e-08, 'whole_port_gap_area_m2': 1e-08, 'collar_boolean_difference_m3': 1e-07}}

def _entry_audit_hybrid_surface_composition_v2():
    parser = _i21_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=_i21_Path, required=True)
    parser.add_argument('--composition-sha256', required=True)
    parser.add_argument('--output', type=_i21_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i21_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    pin = {'path': str(args.composition.resolve()), 'sha256': args.composition_sha256}
    started = _i21_time.monotonic()
    try:
        report = audit_hybrid_surface_composition_mechanism_2_audit(pin)
    except ERRORS as error:
        report = {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_AUDIT_SCHEMA, 'status': 'refused', 'errors': [str(error)], 'composition_pin': pin, 'materials_verified': False, 'native_half_arm_sources_verified': False, 'two_sided_complete_port_verified': False, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False}
    report['resource'] = {'wall_seconds': _i21_time.monotonic() - started, 'actual_peak_rss_bytes': _i21_check_memory(), 'solver_calls': 0, 'source_artifacts_modified': False}
    report['code_sha256'] = {name: _i21_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tests/test_hybrid_geometry_saved_audit.py', 'tools/audit_hybrid_geometry.py', 'tools/audit_hybrid_geometry.py', 'tools/hybrid_cave_saved_audit.py', 'tools/td_shared_channel_fine_saved_audit.py')}
    report['identity_sha256'] = _i21_digest(report)
    payload = _i21_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i21_require(len(payload) <= _i21_MAX_BYTES, 'audit report exceeds 64MiB')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i21_json.dumps({'status': report['status'], 'errors': report['errors'], 'output': str(output), 'sha256': _i21_file_sha256(output), 'two_sided_complete_port_verified': report['two_sided_complete_port_verified']}))
    if report['status'] != 'passed':
        raise SystemExit(1)
_i22_sys.path.insert(0, str(ROOT))
Solid = _i22_ExactSolid
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_AUDIT_SCHEMA = 'td-hybrid-surface-composition-independent-audit-v3'
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_SLICE_SCHEMA = 'td-hybrid-exact-mesh-plane-slice-v2'
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY = {'version': 'rational_topology_mesh_plane-v2', 'authority': 'saved_binary64_mesh_rational_XYZ_UV_nodes_and_exact_orientation', 'identity': 'original_vertex_and_unoriented_edge_ids_never_merged_or_snapped', 'display': 'consecutive_zero_length_display_edges_only_omitted_with_full_rational_witness', 'topology': 'exact_directed_loops_and_exact_containment_parents_equal_display_hierarchy_or_refused', 'certificate': 'original_1e-8m_distance_and_1e-8m2_area_limits_no_collapsed_positive_area_loop', 'projection_bound': 'exact_rational_L1_distance_and_display_perimeter_with_upward_binary64_ceiling', 'coplanar': 'original_oriented_facets_closed_trace_and_separate_incident_halfspaces', 'occupancy': 'original_Mesh64_two_ray_inside_and_hole_void_checks', 'geometry': 'saved_mesh_unchanged_no_CrossSection_grid'}
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256 = _i22_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY)
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY = {**AUDIT_HYBRID_SURFACE_COMPOSITION_POLICY, 'version': 'saved-stage-rational-surface-composition-v3', 'numerical_slice': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256, 'main_boolean': 'immutable_composition02_checkpoint_mesh_pins_material_and_extra_removed_not_recomputed', 'portal_boolean': 'bounded_collars_only_reuse_saved_collars_when_available', 'failure': 'saved_stage_lineage_material_and_partial_port_reports_preserved'}
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_FROZEN_COMPOSITION_CODE = {'terrain_pipeline/hybrid_mesh_plane_v2.py': 'c08f36980976193961c6869b6c07d2e3d44d313be1ecc7ef9e5fcdbed5ae788c', 'terrain_pipeline/hybrid_surface_composition_v3.py': '4be72eb2607d47c9d6260a826d3c04d3624c7e31679bc2aa73c086a83c8828ea', 'tools/prepare_hybrid_surface_composition_v3.py': '6aa37cf6341d078753421caeaee95480a9c335a7b0bb1e3412fd93937dd2cb38', 'tests/test_hybrid_surface_composition_v3.py': '2a6d40e57c115a74c758010d4c19a70c57d766dec1e8561908e3105e6ecd5a1a'}
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_FROZEN_HELPERS = {'tools/audit_hybrid_surface_composition.py': 'bb655a3a06ae410b22c72810d18a73a5c7b576b809a4ce9d0ef853255337b585', 'tools/audit_hybrid_surface_composition_v2.py': '814c87591f8a6adecc82fab4c170424fa14fc0624d885c28802a09fd091cdf75'}
SOURCE_INDEX_SHA256 = '54f1fe63f8f8ff2b79e5bb7332c97fa76ec77b780abf772ad9245081b45af105'
SOURCE_COMPOSITION_SHA256 = '4ef1ed45bf4bd9b819e267273e622ca6475c4271e6d89672be31396e485f1f1d'
SOURCE_CHECKPOINT_SHA256 = 'f84621ff8cecc5e7ef5e33f156c1d7329e998727a21d74d0823cb02207422394'
SOURCE_V2_CODE = {'terrain_pipeline/hybrid_geometry.py': 'ebe155432189c443e8bba0e0ef873873eeb7d4e65d46eaa7756c6877977e23f9', 'terrain_pipeline/hybrid_geometry.py': '9ca048b281f6cbf3fa358d84bed4f9a9df97ebfe9e9b2ec2f66129311e0042bd', 'tools/prepare_hybrid_geometry.py': 'c7d47d03afbd4c361d95a58c06468e8546a65ebfd7b2a96e19728907bb81509a', 'tests/test_hybrid_geometry.py': '2e41c913fa454d64598664947dc0e9cc40cb3e95763ac30c7bc011f4bdd7c18c'}

def audit_hybrid_surface_composition_mechanism_3_independent_triangle_trace(solid, frame):
    origin, normal, transverse = [_i22_np.asarray(frame[key], float) for key in ('origin_local_xyz_m', 'normal_local_xyz', 'transverse_unit_xyz')]
    _i22_require(all((value.shape == (3,) and _i22_np.isfinite(value).all() for value in (origin, normal, transverse))), 'invalid exact plane frame')
    _i22_compare([_i22_np.linalg.norm(normal), _i22_np.linalg.norm(transverse), normal @ transverse], [1.0, 1.0, 0.0], 'exact plane orthonormal frame', atol=1e-12)
    _i22_require(normal[1] == transverse[1] == 0.0, 'exact plane must use horizontal normal/transverse')
    anchor, direction, lateral = map(rational_vector, (origin, normal, transverse))
    vertices = [rational_vector(point) for point in solid.vertices]
    distances = [dot([value - base for value, base in zip(point, anchor)], direction) for point in vertices]
    signs = [int(value > 0) - int(value < 0) for value in distances]
    nodes, segments, caps = ({}, {}, {})

    def vertex_node(index):
        return save_node('v:' + str(index), [index], vertices[index])

    def save_node(name, indices, point):
        uv = [float(dot([value - base for value, base in zip(point, anchor)], lateral)), float(point[1])]
        nodes[name] = {'node_id': name, 'vertex_indices': indices, 'point_local_xyz_m': list(map(float, point)), 'point_uv_m': uv, 'rational_xyz_m': list(map(str, point)), 'rational_uv_m': [str(dot([value - base for value, base in zip(point, anchor)], lateral)), str(point[1])]}
        return name
    for ordinal, indices in enumerate(solid.triangles.tolist()):
        own_signs = [signs[index] for index in indices]
        if min(own_signs) > 0 or max(own_signs) < 0:
            continue
        points = [vertices[index] for index in indices]
        outward = cross([value - base for value, base in zip(points[1], points[0])], [value - base for value, base in zip(points[2], points[0])])
        if own_signs == [0, 0, 0]:
            ids = [vertex_node(index) for index in indices]
            orientation = dot(outward, direction)
            _i22_require(orientation != 0, 'degenerate coplanar original triangle')
            caps[ordinal] = {'triangle_index': ordinal, 'vertex_indices': indices, 'intersection_node_ids': ids, 'polygon_uv_m': [nodes[name]['point_uv_m'] for name in ids], 'normal_dot_plane': float(orientation), 'normal_dot_plane_rational': str(orientation), 'occupied_incident_side': 'negative' if orientation > 0 else 'positive'}
            continue
        ids = []
        exact_points = {}
        for first, second in zip(indices, indices[1:] + indices[:1]):
            if signs[first] == 0:
                name = vertex_node(first)
                ids.append(name)
                exact_points[name] = vertices[first]
            if signs[first] * signs[second] < 0:
                low, high = sorted((first, second))
                fraction = distances[low] / (distances[low] - distances[high])
                point = [base + fraction * (end - base) for base, end in zip(vertices[low], vertices[high])]
                name = save_node('e:' + str(low) + ':' + str(high), [low, high], point)
                ids.append(name)
                exact_points[name] = point
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2:
            continue
        _i22_require(len(ids) == 2, 'ambiguous original triangle intersection')
        orientation = dot([end - start for start, end in zip(exact_points[ids[0]], exact_points[ids[1]])], cross(direction, outward))
        _i22_require(orientation != 0, 'degenerate original slice segment')
        if orientation < 0:
            ids.reverse()
        incident = 'both' if min(own_signs) < 0 < max(own_signs) else 'positive' if max(own_signs) > 0 else 'negative'
        segments[ordinal] = {'triangle_index': ordinal, 'vertex_indices': indices, 'intersection_node_ids': ids, 'incident_halfspace': incident, 'points_local_xyz_m': [nodes[name]['point_local_xyz_m'] for name in ids], 'points_uv_m': [nodes[name]['point_uv_m'] for name in ids], 'orientation_rational': str(abs(orientation)), 'exact_orientation_sign': 1, 'orientation_before_reversal_rational': str(orientation), 'rational_points_xyz_m': [nodes[name]['rational_xyz_m'] for name in ids], 'rational_points_uv_m': [nodes[name]['rational_uv_m'] for name in ids]}
    return (nodes, segments, caps, signs)

def audit_hybrid_surface_composition_mechanism_3_audit_prisms(saved, attachments, vdm, native, origin, meshes):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    _i22_require(saved['schema'] == 'td-hybrid-surface-prisms-v1' and saved['native_exact'] is False and (saved['bottom_semantics'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY['floor']) and (set(saved['half_arms']) == {'sink', 'spring'}), 'changed prism source/approximation contract')
    _i22_compare(saved['common_local_origin_xyz_m'], origin, 'prism shared local origin', atol=0.0)
    expected_cap = max((float(meshes[role].vertices[:, 1].max() + origin[1]) for role in ('rock_before', 'original_cutter'))) + 10.0
    _i22_require(saved['cap_y_world_m'] == expected_cap and saved['cap_above_saved_rock_and_gallery_margin_m'] == 10.0, 'surface cutter cap not fixed above actual original solids')
    library = _i22_manifold_library()
    records, all_prisms, reports = ({}, [], {})
    expected_faces = {tuple(sorted(face)) for face in ((0, 2, 1), (3, 4, 5), (0, 1, 4), (0, 4, 3), (1, 2, 5), (1, 5, 4), (2, 0, 3), (2, 3, 5))}
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        half = saved['half_arms'][kind]
        attachment = attachments['attachments'][kind]
        node = _i22_read(attachment['surface_node_pin'])
        wanted = {'shared:' + node['node_id'] + ':' + str(index) for index in attachment['half_arm_triangle_indices']}
        functions = {item['triangle_id']: item for item in node['source_functions'] if item['triangle_id'] in wanted}
        _i22_require(set(functions) == wanted and node['status'] == 'candidate' and (not node['rejection_reasons']) and (half['node_id'] == node['node_id']) and (half['node_pin'] == attachment['surface_node_pin']) and (half['half_arm_triangle_indices'] == attachment['half_arm_triangle_indices']) and (half['immutable_gallery_station_index'] == ordinal) and (half['immutable_gallery_ring_xyz_m'] == vdm['stations'][ordinal]['derived_ring_xyz_m']), 'original whole half-arm/immutable gallery sources differ')
        expected = {}
        for function in functions.values():
            _i22_check_identity(function)
            _i22_require(function['status'] == 'candidate' and (not function['rejection_reasons']), 'refused original source function')
            for fan in function['fans']:
                _i22_require(fan['fan_id'] not in expected, 'duplicate original fan')
                compact = next((item for item in attachment['compact_native_fans'] if item['fan_key'] == fan['fan_id']), None)
                _i22_require(compact is not None and all((compact[key] == fan[key] for key in ('vertices_xz_m', 'depth_at_vertices_m', 'depth_coefficients_m_1xz', 'depth_origin_xz_m'))), 'original native/compact affine fan mismatch')
                domains = [Polygon(patch['polygon_xz_m']) for patch in fan['native_patches']]
                _i22_require(all((domain.is_valid and domain.area > 0 for domain in domains)) and Polygon(fan['vertices_xz_m']).symmetric_difference(unary_union(domains)).area <= 1e-08, 'original native patch coverage differs from fan domain')
                expected[fan['fan_id']] = (function, fan)
        coverage = {}
        own = []
        bottoms = half['bottom_triangles']
        _i22_require(bottoms and [item['bottom_triangle_id'] for item in bottoms] == list(range(len(bottoms))) and (len(bottoms) * 8 <= 200000), 'invalid bounded prism triangle census')
        maximum_approximation = 0.0
        maximum_bilinear_bound = 0.0
        outside_vertex_count = 0
        for item in bottoms:
            _i22_require(item['fan_key'] in expected, 'surface cutter uses non-half-arm source')
            function, fan = expected[item['fan_key']]
            _i22_require(item['triangle_id'] == function['triangle_id'] and item['source_function_identity_sha256'] == function['identity_sha256'] and (item['saved_affine_fan'] == fan) and (item['saved_native_patch'] in fan['native_patches']) and (item['bilinear_interior_is_planar_approximation'] is True), 'prism native/fan function substituted or approximation concealed')
            patch = item['saved_native_patch']
            patch_index = fan['native_patches'].index(patch)
            bottom = _i22_np.asarray(item['bottom_vertices_xyz_m'], float)
            _i22_require(bottom.shape == (3, 3) and _i22_np.isfinite(bottom).all(), 'invalid bottom triangle')
            polygon = Polygon(bottom[:, [0, 2]])
            domain = Polygon(patch['polygon_xz_m'])
            _i22_require(polygon.is_valid and polygon.area > 0 and (polygon.difference(domain).area <= 1e-10), 'bottom triangle outside original native patch')
            coverage.setdefault((item['fan_key'], patch_index), []).append(polygon)
            expected_depths = []
            domain_witnesses = []
            for point in bottom:
                horizontal = point[[0, 2]]
                _i22_require(any((_i22_np.array_equal(horizontal, vertex) for vertex in patch['polygon_xz_m'])), 'prism introduced or snapped a saved patch vertex')
                inside = exact_fan_cut(fan, horizontal) is not None
                outside_vertex_count += int(not inside)
                domain_witnesses.append({'point_xz_m': horizontal.tolist(), 'inside_original_fan_exact_domain': inside, 'entity_domain_authority': 'original_saved_native_patch_polygon', 'clip_point_not_snapped': True})
                depth = saved_patch_affine_depth(fan, horizontal)
                expected_depths.append(depth)
                _i22_compare(point[1], source_patch_height(patch, point[[0, 2]], native) - depth, 'prism bottom original native minus cut', atol=1e-09)
            _i22_compare(item['depth_at_vertices_m'], expected_depths, 'strict original affine depths', atol=1e-12)
            _i22_require(item['saved_patch_vertex_domain_witnesses'] == domain_witnesses, 'exact original fan domain/patch authority witnesses concealed')
            centroid = bottom.mean(axis=0)
            depth = saved_patch_affine_depth(fan, centroid[[0, 2]])
            deviation = source_patch_height(patch, centroid[[0, 2]], native) - depth - centroid[1]
            maximum_approximation = max(maximum_approximation, abs(deviation))
            bilinear_bound = abs(patch['bilinear_coefficients_m'][3]) * _i22_np.ptp(bottom[:, 0]) * _i22_np.ptp(bottom[:, 2]) / native.spacing ** 2
            _i22_compare(item['conservative_interior_height_error_bound_m'], bilinear_bound, 'saved bilinear planar approximation bound', atol=1e-12)
            maximum_bilinear_bound = max(maximum_bilinear_bound, float(bilinear_bound))
            prism = item['prism']
            _i22_check_identity(prism)
            _i22_require(prism['schema'] == 'td-hybrid-local-solid-mesh-v1' and prism['role'] == 'surface_half_arm_closed_triangular_prism' and (item['prism_triangle_roles'] == ['floor', 'artificial_top_cap'] + ['lateral'] * 6) and ({tuple(sorted(face)) for face in prism['triangles']} == expected_faces), 'prism closure/source roles differ')
            top = bottom.copy()
            top[:, 1] = expected_cap
            _i22_compare(prism['local_origin_xyz_m'], origin, 'prism origin', atol=0.0)
            _i22_compare(prism['vertices_local_xyz_m'], _i22_np.vstack((bottom, top)) - origin, 'prism actual vertices', atol=1e-09)
            solid = Solid(prism['vertices_local_xyz_m'], prism['triangles'], 'source prism')
            _i22_compare(prism['signed_volume_m3'], solid.signed_volume, 'saved source prism volume', atol=1e-07)
            own.append(solid)
            all_prisms.append(solid.manifold(library))
        for fan_key, (_, fan) in expected.items():
            for patch_index, patch in enumerate(fan['native_patches']):
                parts = coverage.get((fan_key, patch_index), [])
                domain = Polygon(patch['polygon_xz_m'])
                _i22_require(parts and domain.symmetric_difference(unary_union(parts)).area <= 1e-08 and (abs(sum((part.area for part in parts)) - domain.area) <= 1e-08), 'missing/overlapping whole native patch prism coverage')
        records[kind] = own
        reports[kind] = {'bottom_triangles': len(bottoms), 'original_half_arm_triangles': len(wanted), 'native_source_and_saved_patch_affine_function_verified': True, 'exact_original_fan_outside_vertex_occurrences': outside_vertex_count, 'entity_domain_authority': 'original_saved_native_patch_polygon', 'max_sampled_centroid_planar_native_difference_m': maximum_approximation, 'max_saved_bilinear_component_error_bound_m': maximum_bilinear_bound, 'centroid_probe_is_not_global_approximation_bound': True}
        _i22_check_memory()
    expected_surface = library.Manifold.batch_boolean(all_prisms, library.OpType.Add)
    tolerance = max(1e-07, expected_surface.volume() * 1e-10)
    _i22_require(volume_difference(expected_surface, meshes['surface_cutter'].manifold(library)) <= tolerance, 'saved surface cutter not union of source-bound closed prisms')
    extra = meshes['extra_removed'].manifold(library)
    _i22_require((extra - expected_surface).volume() <= tolerance, 'extra removed escapes source-supported prism volume')
    return (records, reports)

def rational_area(points):
    return sum((first[0] * second[1] - first[1] * second[0] for first, second in zip(points, points[1:] + points[:1]))) / 2

def ceil_fraction(value):
    rounded = float(value)
    _i22_require(_i22_math.isfinite(rounded), 'nonfinite rational certificate conversion')
    return _i22_math.nextafter(rounded, _i22_math.inf) if _i22_Fraction.from_float(rounded) < value else rounded

def projection_certificate(rational, display_points):
    displayed = [rational_vector(point) for point in display_points]
    _i22_require(len(rational) == len(displayed) and len(rational) >= 3, 'projection certificate vertex census differs')
    error = max((sum((abs(exact - shown) for exact, shown in zip(point, rounded))) for point, rounded in zip(rational, displayed)))
    perimeter = sum((sum((abs(end - start) for start, end in zip(first, second))) for first, second in zip(displayed, displayed[1:] + displayed[:1])))
    bound = 2 * error * perimeter + _i22_Fraction.from_float(_i22_math.nextafter(_i22_math.pi, _i22_math.inf)) * error ** 2
    return {'maximum_projection_distance_l1_rational': str(error), 'display_perimeter_l1_rational': str(perimeter), 'projection_area_bound_rational': str(bound), 'maximum_projection_distance_m': ceil_fraction(error), 'conservative_projection_area_bound_m2': ceil_fraction(bound), 'area_error_m2': ceil_fraction(abs(rational_area(rational) - rational_area(displayed)))}

def area_upper(area, bound):
    return _i22_math.nextafter(_i22_math.fsum((float(area), bound)), _i22_math.inf)

def planar_turn(first, second, third):
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])

def on_segment(point, first, second):
    return planar_turn(first, second, point) == 0 and all((min(start, end) <= value <= max(start, end) for value, start, end in zip(point, first, second)))

def segments_meet(first, second, other_first, other_second):
    if any((max(first[axis], second[axis]) < min(other_first[axis], other_second[axis]) or max(other_first[axis], other_second[axis]) < min(first[axis], second[axis]) for axis in (0, 1))):
        return False
    turns = [planar_turn(first, second, other_first), planar_turn(first, second, other_second), planar_turn(other_first, other_second, first), planar_turn(other_first, other_second, second)]
    return turns[0] * turns[1] < 0 and turns[2] * turns[3] < 0 or any((turns[0] == 0 and on_segment(other_first, first, second), turns[1] == 0 and on_segment(other_second, first, second), turns[2] == 0 and on_segment(first, other_first, other_second), turns[3] == 0 and on_segment(second, other_first, other_second)))

def rational_contains(point, ring):
    winding = 0
    for first, second in zip(ring, ring[1:] + ring[:1]):
        _i22_require(not on_segment(point, first, second), 'exact hierarchy query on original boundary')
        turn = planar_turn(first, second, point)
        if first[1] <= point[1] < second[1] and turn > 0:
            winding += 1
        elif second[1] <= point[1] < first[1] and turn < 0:
            winding -= 1
    _i22_require(winding in (-1, 0, 1), 'non-simple rational hierarchy winding')
    return winding != 0

def check_rational_boundaries(rings):
    for ordinal, ring in enumerate(rings):
        _i22_require(len(set(map(tuple, ring))) == len(ring), 'repeated rational loop coordinate')
        edges = list(zip(ring, ring[1:] + ring[:1]))
        for index, (first, second) in enumerate(edges):
            previous = ring[index - 1]
            if planar_turn(previous, first, second) == 0:
                _i22_require(dot([value - center for value, center in zip(previous, first)], [value - center for value, center in zip(second, first)]) < 0, 'backtracking rational loop boundary')
            for other_index in range(index + 1, len(edges)):
                if other_index == index + 1 or (index == 0 and other_index == len(edges) - 1):
                    continue
                _i22_require(not segments_meet(first, second, *edges[other_index]), 'self-intersecting exact rational loop')
        for other in rings[:ordinal]:
            _i22_require(not any((segments_meet(first, second, other_first, other_second) for first, second in edges for other_first, other_second in zip(other, other[1:] + other[:1]))), 'intersecting/touching exact rational loop hierarchy')

def certified_side(loops, side, nodes, segments):
    from shapely.geometry import Point
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    coefficients, supports = (_i22_Counter(), _i22_defaultdict(list))
    for ordinal, segment in segments.items():
        if segment['incident_halfspace'] in (side, 'both'):
            first, second = segment['intersection_node_ids']
            key = tuple(sorted((first, second)))
            coefficients[key] += 1 if key == (first, second) else -1
            supports[key].append(ordinal)
    expected = _i22_Counter()
    for key, count in coefficients.items():
        _i22_require(abs(count) <= 1, 'nonmanifold rational edge census')
        if count:
            expected[key if count > 0 else key[::-1]] += 1
    own_loops = [loop for loop in loops if loop['side'] == side]
    observed, rings, displays, areas, bounds = (_i22_Counter(), [], [], [], [])
    for loop in own_loops:
        ids = loop['node_ids']
        _i22_require(len(ids) >= 3 and len(set(ids)) == len(ids) and all((name in nodes for name in ids)), 'unknown/repeated rational loop identity')
        edges = list(zip(ids, ids[1:] + ids[:1]))
        observed.update(edges)
        _i22_require(loop['triangle_supports'] == [supports[tuple(sorted(edge))] for edge in edges], 'rational loop triangle support differs')
        ring = [list(map(_i22_Fraction, nodes[name]['rational_uv_m'])) for name in ids]
        area = rational_area(ring)
        _i22_require(area != 0 and loop['signed_area_m2_rational'] == str(area) and (loop['signed_area_m2'] == float(area)), 'rational loop area authority differs')
        display_ids = []
        for name in ids:
            if not display_ids or nodes[name]['point_uv_m'] != nodes[display_ids[-1]]['point_uv_m']:
                display_ids.append(name)
        if len(display_ids) > 1 and nodes[display_ids[-1]]['point_uv_m'] == nodes[display_ids[0]]['point_uv_m']:
            display_ids.pop()
        _i22_require(loop['display_loop_node_ids'] == display_ids and len(display_ids) >= 3, 'display omission is not consecutive duplicate-only or collapses positive-area loop')
        displayed = [rational_vector(nodes[name]['point_uv_m']) for name in display_ids]
        displayed_area = rational_area(displayed)
        polygon = Polygon([nodes[name]['point_uv_m'] for name in display_ids])
        _i22_require(polygon.is_valid and polygon.area > 0 and (area * displayed_area > 0), 'display loop changes orientation or validity')
        certificate = projection_certificate(ring, [nodes[name]['point_uv_m'] for name in ids])
        bound = _i22_Fraction(certificate['projection_area_bound_rational'])
        _i22_require(certificate['maximum_projection_distance_m'] <= 1e-08 and certificate['area_error_m2'] <= 1e-08 and (certificate['conservative_projection_area_bound_m2'] <= 1e-08), 'original projection distance/area gate exceeded')
        _i22_require(loop['display_signed_area_m2_rational'] == str(displayed_area), 'display rational area differs')
        _i22_require(all((loop[key] == value for key, value in certificate.items())), 'exact L1/upward projection certificate differs')
        rings.append(ring)
        displays.append(polygon)
        areas.append(area)
        bounds.append(bound)
    _i22_require(observed == expected, 'identity loops do not exhaust original rational directed edges')
    outgoing, incoming = (_i22_Counter((edge[0] for edge in expected)), _i22_Counter((edge[1] for edge in expected)))
    _i22_require(outgoing == incoming and all((count == 1 for count in outgoing.values())), 'open/branched original rational trace')
    check_rational_boundaries(rings)
    parents = []
    for ordinal, loop in enumerate(own_loops):
        query = list(map(_i22_Fraction, loop['containment_query_uv_rational']))
        point = Point(list(map(float, query)))
        _i22_require(displays[ordinal].contains(point) and rational_contains(query, rings[ordinal]), 'hierarchy query outside own rational/display loop')
        containers = []
        for other, polygon in enumerate(displays):
            if other == ordinal:
                continue
            _i22_require(not displays[ordinal].boundary.intersects(polygon.boundary), 'display hierarchy touching/crossing')
            if abs(areas[other]) > abs(areas[ordinal]):
                inside = rational_contains(query, rings[other])
                _i22_require(inside == polygon.contains(point), 'rational/display containment disagreement')
                if inside:
                    containers.append(other)
        parent = min(containers, key=lambda index: abs(areas[index])) if containers else None
        _i22_require(loop['exact_parent_loop_index'] == parent and loop['display_parent_loop_index'] == parent and (loop['hierarchy_certified'] is True), 'saved hierarchy certificate differs')
        _i22_require(parent is not None or areas[ordinal] > 0, 'root hole without occupied shell')
        if parent is not None:
            _i22_require((areas[parent] > 0) != (areas[ordinal] > 0), 'non-alternating exact hole hierarchy')
        parents.append(parent)
    polygons = []
    for ordinal, area in enumerate(areas):
        if area > 0:
            holes = [list(displays[index].exterior.coords) for index, parent in enumerate(parents) if parent == ordinal and areas[index] < 0]
            polygon = Polygon(displays[ordinal].exterior.coords, holes)
            _i22_require(polygon.is_valid, 'invalid certified occupied component/holes')
            polygons.append(polygon)
    return (unary_union(polygons), sum(bounds, _i22_Fraction(0)))

def audit_hybrid_surface_composition_mechanism_3_audit_exact_slice(record, solid, frame, pin):
    from shapely.geometry import Point
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    _i22_check_identity(record)
    _i22_require(record['schema'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_SLICE_SCHEMA and record['mesh_pin'] == pin and (record['coordinate_convention'] == frame['coordinate_convention']) and (record['method'] == 'rational_identity_topology_certified_binary64_display') and (record['numerical_policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY) and (record['numerical_policy_identity_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256), 'rational slice source/schema/policy differs')
    nodes, segments, caps, signs = audit_hybrid_surface_composition_mechanism_3_independent_triangle_trace(solid, frame)
    _i22_require(record['vertex_plane_classifications'] == [{'vertex_index': index, 'sign': sign, 'classification_method': 'exact_rational'} for index, sign in enumerate(signs)], 'rational vertex classification differs')
    check_census(record['intersection_nodes'], nodes, 'node_id', 'rational intersection authority')
    check_census(record['triangle_segments'], segments, 'triangle_index', 'rational original triangle segment')
    for cap in caps.values():
        rational = [list(map(_i22_Fraction, nodes[name]['rational_uv_m'])) for name in cap['intersection_node_ids']]
        cap['projection_certificate'] = {'signed_area_m2_rational': str(rational_area(rational)), **projection_certificate(rational, cap['polygon_uv_m'])}
    check_census(record['coplanar_triangle_supports'], caps, 'triangle_index', 'rational oriented original cap')
    collapses = {}
    for ordinal, segment in segments.items():
        if segment['points_uv_m'][0] == segment['points_uv_m'][1]:
            first, second = [list(map(_i22_Fraction, point)) for point in segment['rational_points_uv_m']]
            _i22_require(first != second, 'actual exact-zero segment cannot be display-omitted')
            collapses[ordinal] = {'triangle_index': ordinal, 'intersection_node_ids': segment['intersection_node_ids'], 'rational_delta_uv_m': [str(end - start) for start, end in zip(first, second)], 'display_point_uv_m': segment['points_uv_m'][0], 'display_omitted_zero_length_only': True, 'original_segment_and_node_identities_preserved': True}
    check_census(record['projection_collapse_witnesses'], collapses, 'triangle_index', 'display collapse witness')
    loops = record['identity_loops']
    _i22_require(all((loop['side'] in ('positive', 'negative') for loop in loops)), 'unknown rational loop side')
    sides, bounds = ({}, [])
    for side in ('positive', 'negative'):
        sides[side], bound = certified_side(loops, side, nodes, segments)
        bounds.append(bound)
        check_shape(record['one_sided_interior_traces'][side], sides[side], side + ' certified trace')
    _i22_require(set(record['one_sided_interior_traces']) == set(sides), 'rational incident-side census differs')
    cap_polygons, cap_bounds = ([], [])
    for cap in caps.values():
        rational = [list(map(_i22_Fraction, nodes[name]['rational_uv_m'])) for name in cap['intersection_node_ids']]
        display = Polygon(cap['polygon_uv_m'])
        shown = [rational_vector(point) for point in cap['polygon_uv_m']]
        certificate = cap['projection_certificate']
        _i22_require(display.is_valid and display.area > 0 and (rational_area(rational) * rational_area(shown) > 0) and (certificate['area_error_m2'] <= 1e-08) and (certificate['maximum_projection_distance_m'] <= 1e-08) and (certificate['conservative_projection_area_bound_m2'] <= 1e-08), 'actual coplanar facet projection cannot be certified')
        cap_polygons.append(display)
        cap_bounds.append(_i22_Fraction(certificate['projection_area_bound_rational']))
    rational_bound = sum([*bounds, *cap_bounds], _i22_Fraction(0))
    full_bound = ceil_fraction(rational_bound)
    _i22_require(record['display_projection_certified'] is True and full_bound <= 1e-08, 'whole slice projection certificate exceeds original gate')
    _i22_require(record['projection_area_error_bound_m2'] == full_bound and record['projection_area_error_bound_rational'] == str(rational_bound), 'whole rational L1/upward projection bound differs')
    cap_shape = unary_union(cap_polygons)
    actual = unary_union([*sides.values(), cap_shape])
    _i22_require(actual.is_valid and record['coplanar_semantics'] == 'closed_trace_retains_original_oriented_facets_no_cap_deletion', 'unknown rational cap semantics')
    difference = check_shape(record, actual, 'rational closed slice display')
    parts = polygon_parts(actual)
    holes = [Polygon(hole).difference(actual) for polygon in parts for hole in polygon.interiors]
    holes = [hole for hole in holes if not hole.is_empty]
    witnesses = record['occupancy_witnesses']
    _i22_require(len(witnesses) == len(parts) + len(holes), 'rational occupancy witness census differs')
    covered, covered_holes = (set(), set())
    for witness in witnesses:
        query = Point(witness['point_uv_m'])
        inside = witness['region'] == 'retained_polygon'
        _i22_require(inside or witness['region'] == 'excluded_hole', 'unknown rational occupancy region')
        candidates = [index for index, polygon in enumerate(parts if inside else holes) if polygon.contains(query)]
        visited = covered if inside else covered_holes
        _i22_require(len(candidates) == 1 and candidates[0] not in visited, 'duplicate/outside rational occupancy witness')
        visited.add(candidates[0])
        point = _i22_np.asarray(frame['origin_local_xyz_m']) + query.x * _i22_np.asarray(frame['transverse_unit_xyz'])
        point[1] = query.y
        _i22_compare(witness['point_local_xyz_m'], point, 'rational occupancy frame', atol=1e-12)
        if cap_shape.covers(query):
            _i22_require(inside and witness['classification'] == 'original_oriented_coplanar_boundary_facet' and (witness['coplanar_triangle_indices'] == [ordinal for ordinal, cap in caps.items() if Polygon(cap['polygon_uv_m']).covers(query)]), 'unbound coplanar occupancy witness')
        else:
            expected = int(inside)
            classification = 'original_Mesh64_interior_two_ray_parities' if inside else 'original_Mesh64_void_two_ray_parities'
            _i22_require(witness['classification'] == classification and witness['ray_parities'] == [expected, expected] and (abs(solid.winding(point) - expected) <= 1e-07), 'independent rational original solid occupancy failed')
    _i22_check_memory()
    return (actual, {'schema': 'td-hybrid-rational-slice-independent-evidence-v1', 'verified': True, 'mesh_pin': pin, 'slice_identity_sha256': record['identity_sha256'], 'numerical_policy_identity_sha256': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256, 'area_m2': float(actual.area), 'symmetric_difference_m2': float(difference), 'triangle_segments': len(segments), 'coplanar_triangles': len(caps), 'identity_loops': len(loops), 'projection_collapse_witnesses': len(collapses), 'projection_area_error_bound_m2': full_bound, 'full_rational_source_identity_and_hierarchy_verified': True, 'builder_or_slicer_called': False, 'coplanar_facets_removed': False})

def audit_hybrid_surface_composition_mechanism_3_audit_port(kind, composition, prisms, geometry, attachments, vdm, meshes, origin, evidence):
    from shapely.geometry import Polygon
    library = _i22_manifold_library()
    ordinal = 0 if kind == 'sink' else len(vdm['stations']) - 1
    connection = composition['portal_connections'][kind]
    attachment = attachments['attachments'][kind]
    port = _i22_read(attachment['canonical_port_pin'])
    station = vdm['stations'][ordinal]
    _i22_require(port['identity_sha256'] == geometry['portal_bindings'][kind]['port_identity_sha256'] and connection['original_complete_port_proof'] == attachment['actual_complete_port_proof'] and (connection['immutable_gallery_station_index'] == ordinal) and (connection['offset_traces_are_diagnostic_only'] is True) and (connection['hydraulic_boundary_certified'] is False) and (connection['full_shared_interface_supported'] is True) and (connection['canonical_whole_piece_witnesses'] == prisms['half_arms'][kind]['canonical_whole_piece_witnesses']), 'canonical original source/whole-port claim differs')
    distance = audit_canonical_pieces(connection['canonical_whole_piece_witnesses'], attachment['actual_complete_port_proof'], prisms['half_arms'][kind]['bottom_triangles'], port['flow_unit_xz'], kind, station)
    frame = connection['plane']
    check_plane(frame, station['origin_xyz_m'], port['flow_unit_xz'], origin)
    ring = _i22_np.asarray(station['derived_ring_xyz_m'])
    uv = _i22_np.column_stack(((ring[:, [0, 2]] - _i22_np.asarray(station['origin_xyz_m'])[[0, 2]]) @ _i22_np.asarray(frame['transverse_unit_xz']), ring[:, 1] - origin[1]))
    aperture = Polygon(uv)
    _i22_require(aperture.is_valid and aperture.area > 0 and (not aperture.interiors), 'invalid immutable port')
    _i22_compare(connection['gallery_aperture_uv_m'], uv, 'immutable whole port', atol=1e-08)

    def checked_slice(record, role, plane, label):
        source_record = _i22_read(composition['mesh_pins'][role])
        pin = {'artifact': role, 'identity_sha256': source_record['identity_sha256'], 'triangle_identity_authority': 'immutable_saved_record_arrays'}
        shape, report = audit_hybrid_surface_composition_mechanism_3_audit_exact_slice(record, meshes[role], plane, pin)
        report['source_mesh_pin'] = composition['mesh_pins'][role]
        evidence[label] = report
        return shape
    _i22_require(set(connection['exact_solid_slices']) == {'coupled_cutter', 'rock_after', 'removed'}, 'whole-port solid slice census differs')
    shapes = {role: checked_slice(record, role, frame, 'canonical:' + role) for role, record in connection['exact_solid_slices'].items()}
    blocked = aperture.intersection(shapes['rock_after'])
    missing = aperture.difference(shapes['coupled_cutter'])
    _i22_compare(connection['exact_blocked_area_m2'], blocked.area, 'actual whole-port blockage', atol=1e-08)
    _i22_compare(connection['exact_missing_cutter_area_m2'], missing.area, 'actual whole-port missing', atol=1e-08)
    check_shape(connection['blocked_domain'], blocked, 'blocked port', require_contacts=True)
    check_shape(connection['missing_domain'], missing, 'missing port', require_contacts=True)
    evidence['whole_port_metrics'] = {'exact_blocked_area_m2': float(blocked.area), 'exact_missing_cutter_area_m2': float(missing.area)}
    blocked_upper = area_upper(blocked.area, evidence['canonical:rock_after']['projection_area_error_bound_m2'])
    missing_upper = area_upper(missing.area, evidence['canonical:coupled_cutter']['projection_area_error_bound_m2'])
    _i22_require(connection['blocked_area_upper_bound_m2'] == blocked_upper and connection['missing_area_upper_bound_m2'] == missing_upper, 'saved port area upward bound differs')
    evidence['whole_port_metrics'].update(blocked_area_with_projection_bound_m2=blocked_upper, missing_area_with_projection_bound_m2=missing_upper)
    _i22_require(blocked_upper <= 1e-08 and missing_upper <= 1e-08, 'actual full port blocked/missing or projection uncertainty exceeds original gate')
    epsilon = min(0.001, distance / 16)
    _i22_require(connection['epsilon_rule'] == 'min_1mm_and_minimum_actual_exterior_support_distance_div16', 'collar depth policy changed')
    bounds = aperture.bounds
    width, height = (bounds[2] - bounds[0], bounds[3] - bounds[1])
    basis = _i22_np.asarray([frame['transverse_unit_xyz'], frame['vertical_unit_xyz'], frame['normal_local_xyz']]).T
    center = _i22_np.asarray(frame['origin_local_xyz_m']) + _i22_np.asarray(frame['transverse_unit_xyz']) * ((bounds[0] + bounds[2]) / 2)
    center[1] = (bounds[1] + bounds[3]) / 2
    proof = connection['positive_volume_connection']
    _i22_require(set(proof['sides']) == {'surface', 'gallery'} and proof['constructed_by_intersecting_actual_cutters_not_new_excavation'] is True, 'missing two-sided actual source-volume proof')
    surface_sign = -1.0 if kind == 'sink' else 1.0
    side_solids, side_reports = ([], {})
    for side, sign, source in (('surface', surface_sign, 'surface_cutter'), ('gallery', -surface_sign, 'original_cutter')):
        saved = proof['sides'][side]
        role = kind + '_' + side + '_collar'
        source_index = _i22_read(composition['stage_lineage']['source_index_pin'])
        inherited = role in source_index['artifacts']
        _i22_require(saved['inherited_saved_collar'] is inherited and (not inherited or source_index['artifacts'][role] == composition['mesh_pins'][role]), 'saved collar inheritance claim differs')
        _i22_require(saved['artifact'] == role and saved['source_solid'] == source and (saved['normal_side_sign'] == sign), 'collar source/orientation differs')
        transform = _i22_np.column_stack((basis, center + sign * epsilon / 2 * _i22_np.asarray(frame['normal_local_xyz'])))
        _i22_compare(saved['slab_width_height_depth_m'], [width, height, epsilon], 'collar dimensions', atol=1e-12)
        _i22_compare(saved['slab_transform_3x4'], transform, 'collar side frame', atol=1e-09)
        slab = library.Manifold.cube([width, height, epsilon], center=True).transform(transform)
        expected = meshes[source].manifold(library) ^ slab
        actual = meshes[role].manifold(library)
        _i22_require(actual.volume() > 0 and len(actual.decompose()) == saved['component_count'] == 1 and (volume_difference(expected, actual) <= 1e-07), 'collar not actual connected source/slab intersection')
        _i22_compare(saved['positive_volume_m3'], actual.volume(), 'collar volume', atol=1e-07)
        domain = checked_slice(saved['interface_solid_slice'], role, frame, 'collar:' + side)
        gap = aperture.difference(domain)
        _i22_compare(saved['whole_aperture_uncovered_area_m2'], gap.area, 'whole collar gap', atol=1e-08)
        gap_upper = area_upper(gap.area, evidence['collar:' + side]['projection_area_error_bound_m2'])
        _i22_require(saved['uncovered_area_upper_bound_m2'] == gap_upper, 'saved collar upward coverage bound differs')
        check_shape(saved['uncovered_domain'], gap, 'collar uncovered domain', require_contacts=True)
        _i22_require(gap_upper <= 1e-08, 'whole port collar gap/projection uncertainty exceeds original gate')
        side_solids.append(actual)
        side_reports[side] = {'mesh_pin': composition['mesh_pins'][role], 'volume_m3': float(actual.volume()), 'whole_port_gap_m2': float(gap.area), 'actual_source_solid': source}
    role = kind + '_connected_collar'
    connected = meshes[role].manifold(library)
    _i22_require(proof['connected_collar_artifact'] == role and len(connected.decompose()) == proof['component_count'] == 1 and (volume_difference(connected, side_solids[0] + side_solids[1]) <= 1e-07), 'source collars not one saved connected volume')
    overlap = float((connected ^ meshes['rock_after'].manifold(library)).volume())
    _i22_require(overlap <= 1e-07 and (connected - meshes['coupled_cutter'].manifold(library)).volume() <= 1e-07, 'collar blocked or outside actual cutter')
    _i22_compare(proof['actual_rock_overlap_volume_m3'], overlap, 'actual collar rock overlap', atol=1e-07)
    traces = connection['one_sided_diagnostic_traces']
    _i22_require(traces == [] and connection['offset_traces_not_recomputed'] is True, 'v3 diagnostic-offset reuse contract differs')
    for index, trace in enumerate(traces):
        shifted = _i22_np.asarray(station['origin_xyz_m']) + trace['offset_m'] * _i22_np.asarray(frame['normal_local_xyz'])
        check_plane(trace['plane'], shifted, port['flow_unit_xz'], origin)
        _i22_require(set(trace['solid_slices']) == set(shapes), 'diagnostic solid slice census differs')
        for source, record in trace['solid_slices'].items():
            checked_slice(record, source, trace['plane'], 'offset:' + str(index) + ':' + source)
    _i22_require(connection['status'] == 'verified_geometry_unverified_audit' and connection['two_sided_complete_port_verified'] is True and (not connection['rejection_reasons']), 'producer whole-port status disagrees with evidence')
    return {'verified': True, 'port_identity_sha256': port['identity_sha256'], 'canonical_port_pin': attachment['canonical_port_pin'], 'two_sided_complete_port_verified': True, 'exact_blocked_area_m2': float(blocked.area), 'exact_missing_cutter_area_m2': float(missing.area), 'positive_volume_sides': side_reports, 'connected_collar_pin': composition['mesh_pins'][role], 'actual_rock_overlap_volume_m3': overlap, 'offset_slices_not_acceptance_basis': True, 'scope': 'local_source_supported_full_port_volume_join_not_whole_link_or_hydraulics'}

def audit_hybrid_surface_composition_mechanism_3_check_code_pins(record):
    _i22_require(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_FROZEN_COMPOSITION_CODE and record['code_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_FROZEN_COMPOSITION_CODE, 'composition v2 frozen implementation identity differs')
    for name, sha in {**AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_FROZEN_HELPERS, **FROZEN_COMPOSITION_CODE}.items():
        _i22_require(_i22_file_sha256(ROOT / name) == sha, 'frozen v1 dependency changed: ' + name)
    for group in ('code_sha256', 'readonly_dependency_code_sha256', 'audit_code_sha256'):
        for name, sha in record.get(group, {}).items():
            _i22_require(_i22_file_sha256(ROOT / name) == sha, 'pinned implementation changed: ' + name)

def check_stage_lineage(record):
    lineage = record['stage_lineage']
    _i22_require(set(lineage) == {'source_index_pin', 'source_composition_pin', 'checkpoint_pin', 'boolean_artifact_pins', 'source_code_sha256', 'source_readonly_dependency_code_sha256', 'source_status', 'source_rejection_reasons', 'main_boolean_recomputed'} and lineage['main_boolean_recomputed'] is False, 'unknown stage replay lineage')
    _i22_require(lineage['source_index_pin']['sha256'] == SOURCE_INDEX_SHA256 and lineage['source_composition_pin']['sha256'] == SOURCE_COMPOSITION_SHA256 and (lineage['checkpoint_pin']['sha256'] == SOURCE_CHECKPOINT_SHA256), 'only fixed composition02 saved Boolean stage authorized')
    index = _i22_read(lineage['source_index_pin'])
    source = _i22_read(lineage['source_composition_pin'])
    checkpoint = _i22_read(lineage['checkpoint_pin'])
    _i22_require(index['schema'] == 'td-hybrid-surface-composition-preparation-v2' and source['schema'] == 'td-hybrid-surface-composition-v2' and (index['composition'] == lineage['source_composition_pin']) and (source['checkpoint_boolean_pin'] == lineage['checkpoint_pin'] == record['checkpoint_boolean_pin']) and (index['status'] == source['status'] == lineage['source_status']) and (index['rejection_reasons'] == source['rejection_reasons'] == lineage['source_rejection_reasons']) and (source['boolean_stage_preserved'] is True), 'source stage identity/status binding differs')
    _i22_require(checkpoint['schema'] == 'td-hybrid-surface-composition-boolean-checkpoint-v2' and checkpoint['status'] == 'boolean_stage_unverified' and (checkpoint['portal_checks_started'] is False) and (lineage['boolean_artifact_pins'] == checkpoint['artifacts']) and (index['inputs'] == source['inputs'] == checkpoint['inputs'] == record['inputs']) and (index['code_sha256'] == source['code_sha256'] == checkpoint['code_sha256'] == lineage['source_code_sha256'] == SOURCE_V2_CODE) and (index['readonly_dependency_code_sha256'] == source['readonly_dependency_code_sha256'] == checkpoint['readonly_dependency_code_sha256'] == lineage['source_readonly_dependency_code_sha256']), 'source Boolean checkpoint input/code/artifact binding differs')
    for name, sha in {**SOURCE_V2_CODE, **lineage['source_readonly_dependency_code_sha256']}.items():
        _i22_require(_i22_file_sha256(ROOT / name) == sha, 'source stage frozen implementation changed: ' + name)
    stage = checkpoint['composition_stage']
    _i22_check_identity(stage)
    _i22_require(stage['schema'] == source['schema'] and stage['status'] == 'boolean_stage_unverified' and (not stage['rejection_reasons']) and (checkpoint['runtime'] == source['runtime'] == record['runtime']), 'source Boolean stage/runtime contract differs')
    _i22_require(source['policy'] == stage['policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY and source['policy_identity_sha256'] == stage['policy_identity_sha256'] == index['policy_identity_sha256'] == _i22_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY) and (source['numerical_slice_policy'] == checkpoint['numerical_slice_policy'] == index['numerical_slice_policy'] == stage['numerical_slice_policy'] == NUMERICAL_POLICY) and (source['numerical_slice_policy_identity_sha256'] == checkpoint['numerical_slice_policy_identity_sha256'] == index['numerical_slice_policy_identity_sha256'] == stage['numerical_slice_policy_identity_sha256'] == _i22_digest(NUMERICAL_POLICY)), 'source stage numerical/geometric identity differs')
    for field in ('geometry_identity_sha256', 'graph_identity_sha256', 'material', 'coupled_cutter_component_count', 'original_source_sampling_cut_lookup_mismatches'):
        _i22_require(stage[field] == source[field] == record[field], 'unchanged source Boolean field differs: ' + field)
    _i22_require(checkpoint['material'] == record['material'] and checkpoint['artifacts']['surface_prisms'] == record['surface_prisms_pin'], 'replayed source prisms/material substituted')
    expected = {'surface_cutter', 'coupled_cutter', 'rock_after', 'removed', 'extra_removed', 'surface_prisms'}
    _i22_require(set(checkpoint['artifacts']) == expected, 'source Boolean artifact census differs')
    for role, pin in checkpoint['artifacts'].items():
        _i22_require(index['artifacts'][role] == pin and (source['surface_prisms_pin'] == pin if role == 'surface_prisms' else source['mesh_pins'][role] == record['mesh_pins'][role] == pin), 'unchanged Boolean artifact byte pin differs')
    return checkpoint

def audit_complete(composition_pin, progress):
    record = _i22_read(composition_pin)
    _i22_require(record['schema'] == 'td-hybrid-surface-composition-v3' and record['status'] in ('candidate_unverified', 'refused') and (record['boolean_stage_preserved'] is True), 'unknown/incomplete composition v2 stage')
    audit_hybrid_surface_composition_mechanism_3_check_code_pins(record)
    progress.update(composition_identity_sha256=record['identity_sha256'], inputs=record['inputs'], mesh_pins=record['mesh_pins'], surface_prisms_pin=record['surface_prisms_pin'], stage_lineage=record['stage_lineage'])
    inputs = record['inputs']
    _i22_require(set(inputs) == {'geometry', 'geometry_audit', 'graph', 'mesh_pins', 'vdm', 'surface_attachments', 'surface_nodes', 'original_source_sampling'} and inputs['geometry']['sha256'] == GEOMETRY_SHA256 and (inputs['geometry_audit']['sha256'] == GEOMETRY_AUDIT_SHA256), 'fixed geometry03 pins differ')
    geometry, old_audit, graph = (_i22_read(inputs['geometry']), _i22_read_audit(inputs['geometry_audit']), _i22_read(inputs['graph']))
    for parent in (geometry, old_audit):
        for group in ('code_sha256', 'readonly_dependency_code_sha256', 'audit_code_sha256'):
            for name, sha in parent.get(group, {}).items():
                _i22_require(_i22_file_sha256(ROOT / name) == sha, 'geometry03 implementation changed: ' + name)
    _i22_require(old_audit['status'] == 'passed' and (not old_audit['errors']) and (old_audit['geometry_sha256'] == GEOMETRY_SHA256) and (old_audit['geometry_identity_sha256'] == geometry['identity_sha256']) and (old_audit['mesh_pins'] == geometry['mesh_pins']) and (old_audit['inputs'] == geometry['inputs']) and (old_audit['actual_portal_connections_verified'] is True) and (old_audit['actual_hydraulic_sections_verified'] is True) and (graph['identity_sha256'] == geometry['graph_identity_sha256'] == record['graph_identity_sha256']) and (record['geometry_identity_sha256'] == geometry['identity_sha256']), 'original accepted geometry chain differs')
    _i22_require(inputs['graph'] == geometry['inputs']['graph'] and inputs['mesh_pins'] == geometry['mesh_pins'] and (inputs['vdm'] == geometry['vdm_pin']) and (inputs['surface_attachments'] == geometry['surface_attachments_pin']) and (inputs['original_source_sampling'] == geometry['source_sampling_pin']), 'immutable sources changed')
    _i22_require(record['policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY and record['policy_identity_sha256'] == _i22_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY) and (record['numerical_slice_policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY) and (record['numerical_slice_policy_identity_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256), 'unknown composition/slice policy')
    for flag in ('vdm_moved', 'ports_moved', 'fill_generated', 'native_exact', 'fine15_replaced', 'independent_audit_passed', 'hydraulic_ready', 'hydraulic_solved', 'full_network_verified'):
        _i22_require(record[flag] is False, 'prematurely promoted source composition: ' + flag)
    _i22_require(record['original_sampled_rock_retained_cut_only_not_source_resampling'] is True, 'original sampled-source repair semantics concealed')
    _i22_require(record['main_boolean_recomputed'] is False and record['material_inherited_unchanged'] is True, 'v3 replay changed original Boolean/material')
    library = _i22_manifold_library()
    _i22_require(record['runtime']['manifold3d'] == '3.5.4' and record['runtime']['manifold3d_binary_sha256'] == _i22_file_sha256(library.__file__), 'Boolean runtime differs')
    attachments, vdm = (_i22_read(inputs['surface_attachments']), _i22_read(inputs['vdm']))
    _i22_require(inputs['surface_nodes'] == {kind: attachment['surface_node_pin'] for kind, attachment in attachments['attachments'].items()} and set(inputs['surface_nodes']) == {'sink', 'spring'}, 'original half-arm node bindings differ')
    sampling_mismatches = audit_sampling_mismatches(record['original_source_sampling_cut_lookup_mismatches'], _i22_read(inputs['original_source_sampling']), attachments)
    originals = {'rock_before': geometry['mesh_pins']['rock_before'], **{'original_' + role: geometry['mesh_pins'][role] for role in ('cutter', 'rock_after', 'removed')}}
    base_roles = set(originals) | {'surface_cutter', 'coupled_cutter', 'rock_after', 'removed', 'extra_removed'}
    collar_roles = {kind + '_' + side + '_collar' for kind in ('sink', 'spring') for side in ('surface', 'gallery', 'connected')}
    _i22_require(base_roles <= set(record['mesh_pins']) <= base_roles | collar_roles and all((record['mesh_pins'][role] == pin for role, pin in originals.items())), 'mesh census/source bindings differ')
    checkpoint = check_stage_lineage(record)
    progress['stage_lineage_verified'] = True
    artifacts = checkpoint['artifacts']
    _i22_require(set(artifacts) == base_roles - set(originals) | {'surface_prisms'} and artifacts['surface_prisms'] == record['surface_prisms_pin'] and all((artifacts[role] == record['mesh_pins'][role] for role in base_roles - set(originals))), 'Boolean checkpoint artifact pins differ')
    meshes, origin = ({}, None)
    for role, pin in record['mesh_pins'].items():
        mesh = _i22_read(pin)
        current = _i22_np.asarray(mesh['local_origin_xyz_m'], float)
        _i22_require(current.shape == (3,) and _i22_np.isfinite(current).all(), 'invalid local solid origin')
        if origin is None:
            origin = current
        _i22_require(_i22_np.array_equal(current, origin), 'solids do not share original local origin')
        expected_role = role.removeprefix('original_')
        _i22_require(mesh['role'] == expected_role, 'saved solid role differs')
        if mesh['schema'] == 'td-hybrid-empty-solid-v1':
            _i22_require(role == 'extra_removed' and mesh['vertices_local_xyz_m'] == [] and (mesh['triangles'] == []) and (mesh['signed_volume_m3'] == 0.0), 'invalid empty solid')
            meshes[role] = EmptySolid()
        else:
            _i22_require(mesh['schema'] == 'td-hybrid-local-solid-mesh-v1', 'unknown solid schema')
            meshes[role] = Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], role)
            _i22_compare(mesh['signed_volume_m3'], meshes[role].signed_volume, 'saved actual solid volume', atol=1e-07, rtol=1e-09)
            progress.setdefault('mesh_validation_reports', {})[role] = meshes[role].validation_evidence
    sections = _i22_read(geometry['inputs']['original_06_sections'])
    protection = _i22_read(geometry['inputs']['original_wet_protection_manifest'])['wet_protection']
    native = _i22_load_native(geometry['inputs']['original_hierarchy'], sections['selected_leaf_ids'], protection)
    prisms = _i22_read(record['surface_prisms_pin'])
    _, source_reports = audit_hybrid_surface_composition_mechanism_3_audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    progress.update(native_half_arm_sources_verified=True, source_reports=source_reports, original_source_sampling_cut_lookup_mismatches=sampling_mismatches)
    material = audit_material_solids(*(meshes[key] for key in ('rock_before', 'original_rock_after', 'original_removed', 'surface_cutter', 'coupled_cutter', 'rock_after', 'extra_removed', 'removed', 'original_cutter')))
    progress['material_boolean_evidence'] = material
    saved = record['material']
    for key, expected in (('original_rock_before_m3', meshes['rock_before'].signed_volume), ('original_rock_after_m3', meshes['original_rock_after'].signed_volume), ('new_rock_after_m3', meshes['rock_after'].signed_volume), *((key, material[key]) for key in ('original_removed_m3', 'extra_removed_m3', 'total_removed_m3'))):
        _i22_compare(saved[key], expected, 'saved material ' + key, atol=1e-07, rtol=1e-09)
    residuals = [saved['original_rock_before_m3'] - saved['original_rock_after_m3'] - saved['original_removed_m3'], saved['original_rock_before_m3'] - saved['new_rock_after_m3'] - saved['total_removed_m3'], saved['total_removed_m3'] - saved['original_removed_m3'] - saved['extra_removed_m3']]
    _i22_compare(saved['signed_residuals_m3'], residuals, 'signed material residuals', atol=1e-07)
    _i22_require(saved['fill_m3'] == 0.0 and saved['fine15_material_replaced'] is False and (saved['sampled_solid_material_not_native_exact'] is True) and (abs(saved['residual_tolerance_m3'] - material['comparison_tolerance_m3']) <= 1e-12), 'material semantics or tolerance changed')
    progress.update(materials_verified=True, material=material)
    errors, portal_reports, evidence = ([], {}, {})
    if len(meshes['coupled_cutter'].manifold(library).decompose()) != record['coupled_cutter_component_count'] or record['coupled_cutter_component_count'] != 1:
        errors.append('actual coupled cutter not one component')
    _i22_require(set(record['portal_connections']) == {'sink', 'spring'}, 'missing canonical ports')
    for kind in ('sink', 'spring'):
        evidence[kind] = {}
        try:
            portal_reports[kind] = audit_hybrid_surface_composition_mechanism_3_audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, evidence[kind])
        except ERRORS as error:
            errors.append(kind + ': ' + str(error))
            portal_reports[kind] = {'verified': False, 'two_sided_complete_port_verified': False, 'errors': [str(error)]}
    if record['status'] != 'candidate_unverified' or record['rejection_reasons']:
        errors.append('producer refused composition: ' + '; '.join(record['rejection_reasons']))
    verified = not errors
    return {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_AUDIT_SCHEMA, 'status': 'passed' if verified else 'refused', 'errors': errors, 'composition_pin': composition_pin, 'composition_identity_sha256': record['identity_sha256'], 'inputs': inputs, 'mesh_pins': record['mesh_pins'], 'surface_prisms_pin': record['surface_prisms_pin'], 'checkpoint_boolean_pin': record['checkpoint_boolean_pin'], 'geometry_sha256': GEOMETRY_SHA256, 'stage_lineage': record['stage_lineage'], 'stage_lineage_verified': True, 'mesh_validation_reports': progress.get('mesh_validation_reports', {}), 'solid_validation_policy': _i22_SOLID_POLICY, 'solid_validation_policy_identity_sha256': _i22_SOLID_POLICY_SHA256, 'policy_identity_sha256': _i22_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY), 'numerical_slice_policy': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256, 'native_half_arm_sources_verified': True, 'source_reports': source_reports, 'original_source_sampling_cut_lookup_mismatches': sampling_mismatches, 'materials_verified': True, 'material': material, 'portal_reports': portal_reports, 'exact_slice_reports': evidence, 'two_sided_complete_port_verified': verified, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False, 'native_exact': False, 'fine15_replaced': False, 'original_sampling_defects_revalidated_as_correct': False, 'whole_link_control_sill_verified': False, 'builder_or_slicer_called': False, 'scope': 'source_bound_piecewise_planar_carve_material_and_local_full_port_connections_only', 'tolerances': {'canonical_boundary_m': 1e-08, 'whole_port_gap_area_m2': 1e-08, 'collar_boolean_difference_m3': 1e-07}}

def audit_hybrid_surface_composition_mechanism_3_audit(composition_pin):
    progress = {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_AUDIT_SCHEMA, 'status': 'refused', 'errors': [], 'composition_pin': composition_pin, 'native_half_arm_sources_verified': False, 'materials_verified': False, 'two_sided_complete_port_verified': False, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False, 'whole_link_control_sill_verified': False, 'numerical_slice_policy': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256, 'solid_validation_policy': _i22_SOLID_POLICY, 'solid_validation_policy_identity_sha256': _i22_SOLID_POLICY_SHA256}
    try:
        return audit_complete(composition_pin, progress)
    except ERRORS as error:
        progress['errors'].append(str(error))
        return progress

def _entry_audit_hybrid_surface_composition_v3():
    parser = _i22_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=_i22_Path, required=True)
    parser.add_argument('--composition-sha256', required=True)
    parser.add_argument('--output', type=_i22_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i22_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    pin = {'path': str(args.composition.resolve()), 'sha256': args.composition_sha256}
    started = _i22_time.monotonic()
    try:
        report = audit_hybrid_surface_composition_mechanism_3_audit(pin)
    except ERRORS as error:
        report = {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_AUDIT_SCHEMA, 'status': 'refused', 'errors': [str(error)], 'composition_pin': pin, 'materials_verified': False, 'native_half_arm_sources_verified': False, 'two_sided_complete_port_verified': False, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False}
    report['resource'] = {'wall_seconds': _i22_time.monotonic() - started, 'actual_peak_rss_bytes': _i22_check_memory(), 'solver_calls': 0, 'source_artifacts_modified': False}
    report['code_sha256'] = {name: _i22_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tests/test_hybrid_geometry_saved_audit.py', 'tools/audit_hybrid_geometry.py', 'tools/audit_hybrid_geometry.py', 'tools/hybrid_exact_solid_saved_audit.py', 'tools/hybrid_cave_saved_audit.py', 'tools/td_shared_channel_fine_saved_audit.py')}
    report['identity_sha256'] = _i22_digest(report)
    payload = _i22_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i22_require(len(payload) <= _i22_MAX_BYTES, 'audit report exceeds 64MiB')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i22_json.dumps({'status': report['status'], 'errors': report['errors'], 'output': str(output), 'sha256': _i22_file_sha256(output), 'two_sided_complete_port_verified': report['two_sided_complete_port_verified']}))
    if report['status'] != 'passed':
        raise SystemExit(1)
_i19_sys.path.insert(0, str(ROOT))
AUDIT_HYBRID_RIVER_FACES_MECHANISM_2_SCHEMA = 'td-hybrid-river-faces-independent-audit-v2'

def topology_roles(vdm, mesh):
    stations = vdm['stations']
    sizes = {len(item['derived_ring_xyz_m']) for item in stations}
    floors = {item['floor_vertex_count'] for item in stations}
    _i19_require(len(sizes) == len(floors) == 1 and len(stations) == 17, 'unsupported original chart topology')
    count, floor = (next(iter(sizes)), next(iter(floors)))
    _i19_require(count == floor + 2 and floor >= 2, 'unsupported floor/roof chart')
    points = _i19_np.asarray([item['derived_ring_xyz_m'] for item in stations], float).reshape(-1, 3)
    _i19_compare(mesh['vertices_local_xyz_m'], points - _i19_np.asarray(mesh['local_origin_xyz_m']), 'immutable VDM/cutter vertices', atol=0.0)
    _i19_require(mesh['triangles'] == vdm['triangles'], 'immutable VDM/cutter triangles')
    roles = []
    for ordinal, triangle in enumerate(mesh['triangles']):
        station_ids = sorted({vertex // count for vertex in triangle})
        offsets = {vertex % count for vertex in triangle}
        if len(station_ids) == 1:
            _i19_require(station_ids in ([0], [len(stations) - 1]), 'interior cap not supported')
            edge, role = (None, 'endcap')
        else:
            _i19_require(len(station_ids) == 2 and station_ids[1] == station_ids[0] + 1, 'nonadjacent source stations')
            edges = [edge for edge in range(count) if {(edge + 1) % count, edge} == offsets]
            _i19_require(len(edges) == 1, 'invalid ring edge topology')
            edge = edges[0]
            if edge < floor - 1:
                role = 'floor'
            elif edge == floor:
                role = 'roof'
            else:
                role = 'lateral'
        roles.append({'triangle_index': ordinal, 'source_role': role, 'ring_edge_index': edge, 'station_indices': station_ids, 'vertex_indices': triangle})
    return roles

def audit_role_slice(record, frame, original_mesh, original_pin, vdm, prisms, prism_pin):
    _i19_require(record['numerical_policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY and record['numerical_policy_identity_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256, 'role numerical policy substituted')
    if record['role_rule'] == 'station_major_floor_vertex_count_not_edge_slope':
        _i19_require(record['mesh_pin'] == original_pin, 'original role source substituted')
        mesh, roles = (original_mesh, topology_roles(vdm, original_mesh))
    else:
        _i19_require(record['role_rule'] == 'audited_saved_triangular_prism_topology' and record['mesh_pin'] == prism_pin, 'unsupported role source')
        witnesses = record['triangle_segments'] + record['coplanar_triangle_supports']
        _i19_require(witnesses, 'empty role slice')
        binding = witnesses[0]['role_provenance']
        kind, bottom_id = (binding['half_arm_kind'], binding['bottom_triangle_id'])
        _i19_require(kind in ('sink', 'spring'), 'unknown prism half-arm')
        candidates = [item for item in prisms['half_arms'][kind]['bottom_triangles'] if item['bottom_triangle_id'] == bottom_id]
        _i19_require(len(candidates) == 1, 'ambiguous prism source')
        bottom, roles = (candidates[0], [])
        mesh = bottom['prism']
        _i19_check_identity(mesh)
        _i19_require(len(mesh['triangles']) == 8 and bottom['prism_triangle_roles'] == ['floor', 'artificial_top_cap'] + ['lateral'] * 6, 'invalid saved prism topology')
        for ordinal, triangle in enumerate(mesh['triangles']):
            source_role = 'floor' if ordinal == 0 else 'roof' if ordinal == 1 else 'lateral'
            roles.append({'triangle_index': ordinal, 'source_role': source_role, 'original_prism_role': bottom['prism_triangle_roles'][ordinal], 'half_arm_kind': kind, 'bottom_triangle_id': bottom_id, 'fan_key': bottom['fan_key'], 'source_function_identity_sha256': bottom['source_function_identity_sha256'], 'prism_identity_sha256': mesh['identity_sha256'], 'vertex_indices': triangle})
    points = _i19_np.asarray(mesh['vertices_local_xyz_m']) + (_i19_np.asarray(mesh['local_origin_xyz_m']) - _i19_np.asarray(frame['common_local_origin_xyz_m']))
    origin, normal, transverse = [_i19_np.asarray(frame[key]) for key in ('origin_local_xyz_m', 'normal_local_xyz', 'transverse_unit_xyz')]
    role_solid = _i19_Solid(points, mesh['triangles'], 'saved topology role source')
    _, segments, coplanar, _ = audit_hybrid_surface_composition_mechanism_3_independent_triangle_trace(role_solid, frame)
    saved = record['triangle_segments']
    _i19_require(len(saved) == len(segments) and {item['triangle_index'] for item in saved} == set(segments), 'role line census differs')
    lines = {}
    for item in saved:
        ordinal = item['triangle_index']
        expected = segments[ordinal]
        _i19_require(item['vertex_indices'] == mesh['triangles'][ordinal] and item['role_provenance'] == roles[ordinal] and (item['source_role'] == roles[ordinal]['source_role']), 'fabricated topology role')
        _i19_require(set(item) == set(expected) | {'source_role', 'role_provenance'} and all((item[key] == value for key, value in expected.items())), 'role source intersection identity or incident side differs')
        line = _i19_LineString(item['points_uv_m'])
        _i19_require(line.hausdorff_distance(_i19_LineString(segments[ordinal]['points_uv_m'])) <= 1e-08, 'fabricated role support segment')
        uv = _i19_np.asarray(item['points_uv_m'])
        xyz = origin + uv[:, :1] * transverse
        xyz[:, 1] = uv[:, 1]
        _i19_compare(item['points_local_xyz_m'], xyz, 'role segment frame', atol=1e-08)
        lines[ordinal] = (line, roles[ordinal])
    expected_caps = {}
    for ordinal, item in coplanar.items():
        expected_caps[ordinal] = _i19_Polygon(item['polygon_uv_m'])
    saved_caps = record['coplanar_triangle_supports']
    _i19_require(len(saved_caps) == len(expected_caps) and {item['triangle_index'] for item in saved_caps} == set(expected_caps), 'role cap census differs')
    for item in saved_caps:
        ordinal = item['triangle_index']
        expected = coplanar[ordinal]
        _i19_require(item['role_provenance'] == roles[ordinal] and item['source_role'] == roles[ordinal]['source_role'] and (item['vertex_indices'] == mesh['triangles'][ordinal]) and (_i19_Polygon(item['polygon_uv_m']).symmetric_difference(expected_caps[ordinal]).area <= 1e-08), 'fabricated coplanar topology role')
        _i19_require(set(item) == set(expected) | {'source_role', 'role_provenance'} and all((item[key] == value for key, value in expected.items())), 'role source coplanar identity or occupied side differs')
    return lines

def audit_boundary(aperture, shapes, slices, role_lines, frame):
    cutter, before, after, removed = [shapes[key] for key in ('cutter', 'rock_before', 'rock_after', 'removed')]
    _i19_require(cutter.geom_type == 'Polygon' and (not cutter.is_empty) and (not cutter.interiors), 'unknown/multiple fluid aperture')
    polygon = _i19_Polygon(aperture['polygon_uv_m'])
    _i19_require(polygon.is_valid and polygon.symmetric_difference(cutter).area <= 1e-08 and (aperture['polygon_authoritative'] is True) and (aperture['floor_height_function_required'] is False), 'actual polygon replaced by height function')
    _i19_require(aperture['pressure_slot_enlarges_face'] is False and cutter.intersection(after).area <= 1e-08, 'actual rock blocks fluid aperture or storage slot enlarges face')
    replay = removed.symmetric_difference(cutter.intersection(before)).area
    _i19_require(replay <= 1e-08, 'removed material not actual Boolean slice')
    bounds = {role: record['projection_area_error_bound_m2'] for role, record in slices.items()}
    blocked_upper = _i19_math.nextafter(_i19_math.fsum((cutter.intersection(after).area, bounds['cutter'], bounds['rock_after'])), _i19_math.inf)
    replay_upper = _i19_math.nextafter(_i19_math.fsum((replay, bounds['removed'], bounds['cutter'], bounds['rock_before'])), _i19_math.inf)
    _i19_require(aperture['projection_area_error_bounds_m2'] == bounds and aperture['blocked_area_upper_bound_m2'] == blocked_upper and (aperture['removed_replay_difference_area_upper_bound_m2'] == replay_upper) and (blocked_upper <= 1e-08) and (replay_upper <= 1e-08), 'face projection error or conservative acceptance bound differs')
    for key, expected in (('blocked_area_m2', cutter.intersection(after).area), ('removed_replay_difference_area_m2', replay), ('bounded_display_aperture_area_m2', cutter.area), ('actual_excavated_aperture_area_m2', removed.area)):
        _i19_compare(aperture[key], expected, key, atol=1e-08)
    components = len(removed.geoms) if removed.geom_type == 'MultiPolygon' else int(not removed.is_empty)
    _i19_require(aperture['material_component_count'] == components and aperture['material_components_do_not_certify_fluid_connectivity'] is True, 'material components confused with fluid connectivity')
    origin, transverse = (_i19_np.asarray(frame['origin_local_xyz_m']), _i19_np.asarray(frame['transverse_unit_xyz']))
    uv = _i19_np.asarray(aperture['polygon_uv_m'])
    xyz = origin + uv[:, :1] * transverse
    xyz[:, 1] = uv[:, 1]
    _i19_compare(aperture['polygon_local_xyz_m'], xyz, 'polygon frame', atol=1e-08)
    lines, floors, tops, wet_lengths = ([], [], [], [])
    for piece in aperture['boundary_pieces']:
        line = _i19_LineString(piece['points_uv_m'])
        _i19_require(line.length > 1e-08 and whole_line_supported(line, cutter.boundary), 'fabricated aperture boundary')
        uv = _i19_np.asarray(piece['points_uv_m'])
        xyz = origin + uv[:, :1] * transverse
        xyz[:, 1] = uv[:, 1]
        _i19_compare(piece['points_local_xyz_m'], xyz, 'boundary frame', atol=1e-08)
        support = []
        for reference in piece['source_role_support']:
            source_index, ordinal = (reference['source_index'], reference['triangle_index'])
            _i19_require(type(source_index) is int and 0 <= source_index < len(role_lines) and (ordinal in role_lines[source_index]), 'unknown role support reference')
            source_line, source_role = role_lines[source_index][ordinal]
            _i19_require(reference == {'source_index': source_index, **source_role} and source_role['source_role'] != 'endcap', 'endcap/fabricated source counted as wall')
            support.append(source_line)
        _i19_require(support and whole_line_supported(line, _i19_unary_union(support)), 'whole boundary missing role support')
        roles = {reference['source_role'] for reference in piece['source_role_support']}
        _i19_require(roles == {piece['source_role']}, 'ambiguous source role')
        wall = before.buffer(1e-08).covers(line) and whole_line_supported(line, after.boundary)
        expected = 'actual_rock_wet_wall' if wall else {'floor': 'saved_cut_floor_open_air_side', 'lateral': 'engineering_lateral_wall_above_terrain', 'roof': 'artificial_cutter_top_cap_not_wetted_wall'}[piece['source_role']]
        _i19_require(wall or not before.buffer(1e-08).covers(line), 'inside-rock boundary missing actual wall')
        _i19_require(piece['physical_exposure'] == piece['category'] == expected, 'incorrect physical exposure')
        if wall:
            _i19_compare(piece['potential_wetted_length_m'], line.length, 'actual wet wall', atol=1e-08)
            wet_lengths.append(line.length)
        else:
            _i19_require(piece['potential_wetted_length_m'] is None, 'artificial/free edge counted as actual wet wall')
        for role in ('cutter', 'rock_after'):
            ids = piece['source_triangle_indices'][role]
            _i19_require(len(ids) == len(set(ids)), 'duplicate wall triangle refs')
            supports = [_i19_LineString(item['points_uv_m']) for item in slices[role]['triangle_segments'] if item['triangle_index'] in ids]
            supports.extend((_i19_Polygon(item['polygon_uv_m']) for item in slices[role]['coplanar_triangle_supports'] if item['triangle_index'] in ids))
            available = {item['triangle_index'] for item in slices[role]['triangle_segments'] + slices[role]['coplanar_triangle_supports']}
            _i19_require(set(ids) <= available, 'wall refs nonintersecting triangles')
            if role == 'cutter' or wall:
                _i19_require(supports and whole_line_supported(line, _i19_unary_union(supports)), 'whole wall lacks actual source triangles')
        lines.append(line)
        if piece['source_role'] == 'floor':
            floors.append(piece['points_uv_m'])
        if expected == 'artificial_cutter_top_cap_not_wetted_wall':
            tops.append({'points_uv_m': piece['points_uv_m'], 'u_interval_m': sorted((piece['points_uv_m'][0][0], piece['points_uv_m'][-1][0])), 'source_role_support': piece['source_role_support']})
    _i19_require(lines and whole_line_supported(cutter.boundary, _i19_unary_union(lines)) and (abs(_i19_math.fsum((line.length for line in lines)) - _i19_unary_union(lines).length) <= 1e-08), 'missing/duplicate aperture boundary')
    closed = len(wet_lengths) == len(lines)
    _i19_require(aperture['closed_boundary_certified'] is closed and aperture['kind'] == ('closed_polygon' if closed else 'open_actual_polygon') and (floors == aperture['floor_boundary_pieces_uv_m']) and floors, 'actual boundary classification differs')
    expected_extension = None if closed else {'kind': 'explicit_engineering_supported_top_intervals_only', 'unbounded_above_cut_floor': False, 'supported_free_top_intervals': tops, 'actual_rock_roof_segments_remain_bounded': True, 'extension_is_not_physical_path_certification': True}
    _i19_require(aperture['open_extension'] == expected_extension and (closed or tops), 'unsupported engineering extension')
    return {'kind': aperture['kind'], 'area_m2': cutter.area, 'actual_rock_wet_wall_length_m': _i19_math.fsum(wet_lengths), 'boundary_piece_count': len(lines), 'polygon_and_source_roles_verified': True}

def audit_hybrid_river_faces_mechanism_2_audit(pin):
    record = _i19_read(pin)
    _i19_require(record['schema'] == 'td-hybrid-river-faces-v2', 'wrong face schema')
    inputs = record['inputs']
    geometry, composition = (_i19_read(inputs['geometry']), _i19_read(inputs['composition']))
    coupled_audit = _i19_read_audit(inputs['composition_audit'])
    _i19_require(composition['schema'] == 'td-hybrid-surface-composition-v3' and composition['status'] == 'candidate_unverified' and (not composition['rejection_reasons']) and (coupled_audit['schema'] == 'td-hybrid-surface-composition-independent-audit-v4') and (coupled_audit['status'] == 'passed') and (not coupled_audit['errors']) and (coupled_audit['composition_pin']['sha256'] == inputs['composition']['sha256']) and (_i19_Path(coupled_audit['composition_pin']['path']).resolve() == _i19_Path(inputs['composition']['path']).resolve()) and (coupled_audit['composition_identity_sha256'] == composition['identity_sha256']) and (coupled_audit['inputs'] == composition['inputs']) and (coupled_audit['mesh_pins'] == composition['mesh_pins']) and (coupled_audit['surface_prisms_pin'] == composition['surface_prisms_pin']) and (coupled_audit['policy_identity_sha256'] == composition['policy_identity_sha256']) and (coupled_audit['materials_verified'] is True) and (coupled_audit['native_half_arm_sources_verified'] is True) and (coupled_audit['material']['independent_boolean_verified'] is True) and (coupled_audit['two_sided_complete_port_verified'] is True) and (coupled_audit['stage_lineage_verified'] is True) and (coupled_audit['stage_lineage'] == composition['stage_lineage']) and (record['stage_lineage'] == inputs['stage_lineage'] == composition['stage_lineage']) and (composition['main_boolean_recomputed'] is False) and (composition['material_inherited_unchanged'] is True) and (record['composition_identity_sha256'] == composition['identity_sha256']), 'coupled geometry not independently accepted')
    check_stage_lineage(composition)
    _i19_require(composition['numerical_slice_policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY and composition['numerical_slice_policy_identity_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256 and (record['numerical_slice_policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY) and (record['numerical_slice_policy_identity_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256), 'unverified quantized slice policy')
    _i19_require(inputs['geometry'] == composition['inputs']['geometry'] and inputs['geometry_audit'] == composition['inputs']['geometry_audit'] and (inputs['graph'] == composition['inputs']['graph']) and (inputs['vdm'] == composition['inputs']['vdm']) and (inputs['surface_attachments'] == composition['inputs']['surface_attachments']) and (inputs['surface_prisms'] == composition['surface_prisms_pin']) and (inputs['mesh_pins'] == composition['mesh_pins']) and (inputs['original_inputs'] == composition['inputs']) and (coupled_audit['geometry_sha256'] == inputs['geometry']['sha256']) and (inputs['geometry']['sha256'] == '3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593'), 'mixed geometry/source/mesh parents')
    composition_index = _i19_read(inputs['composition_index'])
    _i19_require(composition_index['schema'] == 'td-hybrid-surface-composition-preparation-v3' and composition_index['composition']['sha256'] == inputs['composition']['sha256'] and (_i19_Path(composition_index['composition']['path']).resolve() == _i19_Path(inputs['composition']['path']).resolve()) and (composition_index['inputs'] == composition['inputs']) and (composition_index['stage_lineage'] == composition['stage_lineage']) and (composition_index['code_sha256'] == composition['code_sha256']), 'composition index binding differs')
    for parent in (record, composition, coupled_audit):
        for group in ('code_sha256', 'readonly_dependency_code_sha256', 'audit_code_sha256'):
            for name, sha in parent.get(group, {}).items():
                _i19_require(_i19_file_sha256(ROOT / name) == sha, 'frozen source changed: ' + name)
    _i19_require(geometry['identity_sha256'] == record['geometry_identity_sha256'] and geometry['graph_identity_sha256'] == record['graph_identity_sha256'] and (record['face_count'] == len(record['faces']) == len(geometry['hydraulic_links']) == 18), 'geometry/face census differs')
    for flag in ('independent_audit_passed', 'hydraulic_solved', 'water_discharge_computed', 'storage_geometry_changed', 'pressure_slot_enlarges_face', 'native_exact'):
        _i19_require(record[flag] is False, 'premature hydraulic/geometry promotion')
    vdm = _i19_read(composition['inputs']['vdm'])
    prisms = _i19_read(composition['surface_prisms_pin'])
    attachments = _i19_read(composition['inputs']['surface_attachments'])
    original_pin = composition['mesh_pins']['original_cutter']
    original = _i19_read(original_pin)
    pins = {role: composition['mesh_pins']['coupled_cutter' if role == 'cutter' else role] for role in ('cutter', 'rock_before', 'rock_after', 'removed')}
    meshes = {role: _i19_read(mesh_pin) for role, mesh_pin in pins.items()}
    common = _i19_np.asarray(meshes['cutter']['local_origin_xyz_m'])
    solids = {}
    for role, mesh in meshes.items():
        _i19_require(_i19_np.array_equal(mesh['local_origin_xyz_m'], common), 'source solids not in common frame')
        solids[role] = _i19_Solid(mesh['vertices_local_xyz_m'], mesh['triangles'], role)
    reports, errors = ([], [])
    cells = {cell['cell_id']: cell for cell in geometry['hydraulic_cells']}
    for ordinal, face in enumerate(record['faces']):
        try:
            _i19_check_identity(face)
            _i19_require(face['schema'] == 'td-hybrid-river-face-v2' and face['face_id'] == 'face:' + str(ordinal) and (face['status'] == 'candidate') and (not face['rejection_reasons']), 'unknown/refused face')
            link = geometry['hydraulic_links'][ordinal]
            for key in ('link_id', 'from_cell_id', 'to_cell_id', 'length_m'):
                _i19_require(face[key] == link[key], 'original hydraulic link substituted')
            _i19_require(face['additional_step_loss'] is None and face['roughness_manning'] == 0.035 and (face['roughness_source_cell_ids'] == [link['from_cell_id'], link['to_cell_id']]) and all((cells[key]['roughness_manning'] == 0.035 for key in face['roughness_source_cell_ids'])), 'undeclared resistance parameters')
            if ordinal in (0, 17):
                kind = 'sink' if ordinal == 0 else 'spring'
                port = _i19_read(attachments['attachments'][kind]['canonical_port_pin'])
                station = vdm['stations'][0 if ordinal == 0 else -1]
                portal_report = coupled_audit['portal_reports'][kind]
                _i19_require(portal_report['verified'] is True and portal_report['two_sided_complete_port_verified'] is True and (portal_report['port_identity_sha256'] == port['identity_sha256']) and (portal_report['canonical_port_pin'] == attachments['attachments'][kind]['canonical_port_pin']), 'per-portal identity/verification differs')
                check_plane(face['plane'], station['origin_xyz_m'], port['flow_unit_xz'], common)
                canonical = source_canonical_floor(port, face['plane'])
                binding = face['shared_port_binding']
                attachment = attachments['attachments'][kind]
                _i19_require(binding == {'kind': kind, 'canonical_port_pin': attachment['canonical_port_pin'], 'surface_node_pin': attachment['surface_node_pin'], 'port_identity_sha256': port['identity_sha256'], 'actual_complete_port_proof': attachment['actual_complete_port_proof'], 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'canonical_profile_uv_m': canonical, 'hydraulic_boundary_certified': False}, 'whole native canonical profile differs')
                evidence = face['aperture']['canonical_two_sided_evidence']
                _i19_require(evidence['composition_audit_pin'] == inputs['composition_audit'] and evidence['two_sided_complete_port_verified'] is True and (evidence['composition_portal_connection'] == composition['portal_connections'][kind]) and (evidence['no_endcap_deleted'] is True), 'missing actual two-sided port proof')
            else:
                first, second = vdm['stations'][ordinal - 1:ordinal + 1]
                _i19_require((link['from_cell_id'], link['to_cell_id']) == (first['station_id'], second['station_id']) and face['shared_port_binding'] is None and (face['aperture']['canonical_two_sided_evidence'] is None), 'wrong route binding')
                start, end = (_i19_np.asarray(first['origin_xyz_m']), _i19_np.asarray(second['origin_xyz_m']))
                check_plane(face['plane'], (start + end) / 2, (end - start)[[0, 2]], common)
                canonical = None
            _i19_require(set(face['solid_slices']) == set(solids), 'actual solid slice census differs')
            shapes = {role: audit_hybrid_surface_composition_mechanism_3_audit_exact_slice(face['solid_slices'][role], solid, face['plane'], pins[role])[0] for role, solid in solids.items()}
            role_lines = [audit_role_slice(source, face['plane'], original, original_pin, vdm, prisms, composition['surface_prisms_pin']) for source in face['source_role_slices']]
            if canonical is not None:
                _i19_require(whole_line_supported(_i19_LineString(canonical), shapes['cutter'].boundary), 'canonical floor not actual face boundary')
            report = audit_boundary(face['aperture'], shapes, face['solid_slices'], role_lines, face['plane'])
            reports.append({'face_id': face['face_id'], 'link_id': link['link_id'], 'aperture': report})
            _i19_check_memory()
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append({'face_id': face.get('face_id'), 'error': str(error), 'saved_rejection_reasons': face.get('rejection_reasons')})
    refused = [item['face_id'] for item in record['faces'] if item['status'] != 'candidate']
    _i19_require(record['rejection_reasons'] == refused and record['status'] == ('refused' if refused else 'candidate_unverified'), 'refusal census differs')
    return {'schema': AUDIT_HYBRID_RIVER_FACES_MECHANISM_2_SCHEMA, 'status': 'refused' if errors else 'passed', 'errors': errors, 'faces_pin': pin, 'inputs': inputs, 'reports': reports, 'verified_face_count': len(reports), 'geometry_identity_sha256': geometry['identity_sha256'], 'composition_identity_sha256': composition['identity_sha256'], 'actual_slice_sources_verified': not errors, 'wet_wall_boundary_sources_verified': not errors, 'two_sided_canonical_ports_verified': not errors, 'hydraulic_solved': False, 'hydraulic_constitutive_law_accepted': False, 'whole_link_step_support_certified': False}

def _entry_audit_hybrid_river_faces_v2():
    parser = _i19_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--faces', type=_i19_Path, required=True)
    parser.add_argument('--faces-sha256', required=True)
    parser.add_argument('--output', type=_i19_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i19_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit required')
    pin = {'path': str(args.faces.resolve()), 'sha256': args.faces_sha256}
    started = _i19_time.monotonic()
    try:
        report = audit_hybrid_river_faces_mechanism_2_audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as error:
        report = {'schema': AUDIT_HYBRID_RIVER_FACES_MECHANISM_2_SCHEMA, 'status': 'refused', 'errors': [str(error)], 'faces_pin': pin, 'hydraulic_solved': False, 'hydraulic_constitutive_law_accepted': False}
    report['resource'] = {'wall_seconds': _i19_time.monotonic() - started, 'peak_rss_bytes': _i19_check_memory(), 'solver_calls': 0}
    report['code_sha256'] = {name: _i19_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tests/test_hybrid_geometry_saved_audit.py', 'tools/audit_hybrid_geometry.py', 'tools/hybrid_exact_solid_saved_audit.py', 'tools/audit_hybrid_geometry.py', 'tools/hybrid_cave_saved_audit.py', 'tools/td_shared_channel_fine_saved_audit.py')}
    report['identity_sha256'] = _i19_digest(report)
    payload = _i19_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i19_require(len(payload) <= _i19_MAX_BYTES, 'audit exceeds file budget')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i19_json.dumps({'status': report['status'], 'errors': report['errors'], 'verified_face_count': report.get('verified_face_count', 0), 'sha256': _i19_file_sha256(output)}))
    return 0 if report['status'] == 'passed' else 1
_i23_sys.path.insert(0, str(ROOT))
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_AUDIT_SCHEMA = 'td-hybrid-surface-composition-independent-audit-v4'
COMPOSITION_SHA256 = '88ed045a0589d130a2622cba3b4ace4a139b6513ebca2616a1bae67bdda0e4b6'
PREVIOUS_AUDIT_SHA256 = '4ea6f5700735395e3591a744a25d22ab520a6ae486d4c5c2d3a201c83d01a977'
BASE = ROOT / 'verification/natural-river-network/hybrid-surface-composition-20261006-03'
PREVIOUS_CODE = {'tests/test_hybrid_geometry_saved_audit.py': '5900221e64c864a909992daeb34c5aced97b5636d52fad137234d584d8f66924', 'tools/audit_hybrid_geometry.py': 'f16987cfbcef80977b96c948c125757d55002d0dbab9d6ae9d3eea80bde71ded', 'tools/audit_hybrid_geometry.py': 'bb655a3a06ae410b22c72810d18a73a5c7b576b809a4ce9d0ef853255337b585', 'tools/audit_hybrid_geometry.py': '6d1a59873b8543b25c532fdfbf4265fec2e93a9a394a0232242796926013cd3d', 'tools/hybrid_cave_saved_audit.py': '9fbdbb83b5b5ca54c3da815d1288d45ffd40fabad0bd12c2d22dd311d2b3474a', 'tools/hybrid_exact_solid_saved_audit.py': '0fc1adcfabd817aa13558ff2eaade19d8f150d8a2a1322cda2ef8582733f333f', 'tools/td_shared_channel_fine_saved_audit.py': 'f654e5a9730280e5fdd5e03206be1d3de8cb9b92852aeb047b86cee91655b0a9'}
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_ERRORS = ERRORS + (AttributeError, OverflowError, ZeroDivisionError)

def validate_resume_parent(composition_pin, previous_pin):
    _i23_require(composition_pin['sha256'] == COMPOSITION_SHA256 and previous_pin['sha256'] == PREVIOUS_AUDIT_SHA256, 'only fixed composition03/audit-v1 continuation authorized')
    record, parent = (_i23_read(composition_pin), _i23_read_audit(previous_pin))
    _i23_require(record['schema'] == 'td-hybrid-surface-composition-v3' and record['status'] == 'candidate_unverified' and (not record['rejection_reasons']) and (parent['schema'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_AUDIT_SCHEMA) and (parent['status'] == 'refused') and (parent['errors'] == ["'identity_sha256'"]) and (parent['composition_pin'] == composition_pin) and (parent['composition_identity_sha256'] == record['identity_sha256']), 'unknown continuation point or mismatched saved composition')
    _i23_require(parent['code_sha256'] == PREVIOUS_CODE, 'previous audit code registry differs')
    for name, sha in PREVIOUS_CODE.items():
        _i23_require(_i23_file_sha256(ROOT / name) == sha, 'previous audit frozen source changed: ' + name)
    audit_hybrid_surface_composition_mechanism_3_check_code_pins(record)
    _i23_require(parent['stage_lineage_verified'] is True and parent['stage_lineage'] == record['stage_lineage'] and (parent['inputs'] == record['inputs']) and (parent['mesh_pins'] == record['mesh_pins']) and (parent['surface_prisms_pin'] == record['surface_prisms_pin']) and (parent['native_half_arm_sources_verified'] is False) and (parent['materials_verified'] is False) and (parent['two_sided_complete_port_verified'] is False) and ('material_boolean_evidence' not in parent) and ('portal_reports' not in parent), 'incomplete/unknown inherited evidence boundaries')
    _i23_require(parent['numerical_slice_policy'] == record['numerical_slice_policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY and parent['numerical_slice_policy_identity_sha256'] == record['numerical_slice_policy_identity_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256 and (parent['solid_validation_policy'] == _i22_SOLID_POLICY) and (parent['solid_validation_policy_identity_sha256'] == _i22_SOLID_POLICY_SHA256) and (record['policy'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY) and (record['policy_identity_sha256'] == _i23_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY)), 'inherited numerical/solid/source policy differs')
    reports = parent['mesh_validation_reports']
    _i23_require(set(reports) == set(record['mesh_pins']) and len(reports) == 15, 'all fifteen completed mesh reports required')
    return (record, parent)

def validate_material_account(record, meshes, material):
    saved = record['material']
    for key, expected in (('original_rock_before_m3', meshes['rock_before'].signed_volume), ('original_rock_after_m3', meshes['original_rock_after'].signed_volume), ('new_rock_after_m3', meshes['rock_after'].signed_volume), *((key, material[key]) for key in ('original_removed_m3', 'extra_removed_m3', 'total_removed_m3'))):
        _i23_compare(saved[key], expected, 'saved material ' + key, atol=1e-07, rtol=1e-09)
    residuals = [saved['original_rock_before_m3'] - saved['original_rock_after_m3'] - saved['original_removed_m3'], saved['original_rock_before_m3'] - saved['new_rock_after_m3'] - saved['total_removed_m3'], saved['total_removed_m3'] - saved['original_removed_m3'] - saved['extra_removed_m3']]
    _i23_compare(saved['signed_residuals_m3'], residuals, 'saved signed material residuals', atol=1e-07)
    _i23_require(saved['fill_m3'] == 0.0 and saved['fine15_material_replaced'] is False and (saved['sampled_solid_material_not_native_exact'] is True) and (abs(saved['residual_tolerance_m3'] - material['comparison_tolerance_m3']) <= 1e-12), 'original material semantics or thresholds changed')

def record_failure(report, stage, error):
    message = stage + ': ' + type(error).__name__ + ': ' + str(error)
    report['errors'].append(message)
    frames = _i23_traceback.extract_tb(error.__traceback__)
    source = frames[-1] if frames else None
    report['failure_stage'] = stage
    report['failures'].append({'stage': stage, 'error_type': type(error).__name__, 'message': str(error), 'source_path': str(_i23_Path(source.filename).resolve()) if source else None, 'source_line': source.lineno if source else None, 'source_function': source.name if source else None})

def resume(composition_pin, previous_pin, report):
    report['current_stage'] = 'resume_parent_binding'
    record, parent = validate_resume_parent(composition_pin, previous_pin)
    report.update(composition_identity_sha256=record['identity_sha256'], inputs=record['inputs'], mesh_pins=record['mesh_pins'], surface_prisms_pin=record['surface_prisms_pin'], checkpoint_boolean_pin=record['checkpoint_boolean_pin'], stage_lineage=record['stage_lineage'], stage_lineage_verified=True, mesh_validation_reports=parent['mesh_validation_reports'], geometry_sha256=GEOMETRY_SHA256, policy_identity_sha256=_i23_digest(AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY), inherited_evidence={'audit_pin': previous_pin, 'audit_identity_sha256': parent['identity_sha256'], 'composition_pin': composition_pin, 'composition_identity_sha256': record['identity_sha256'], 'completed_stages': ['stage_lineage', 'mesh_validation'], 'mesh_roles': sorted(record['mesh_pins']), 'mesh_validation_inherited': True, 'exact_mesh_recomputed': False, 'source_material_ports_inherited': False, 'audit_code_sha256_matched': True, 'validated_mesh_roles': []})
    meshes, origin = ({}, None)
    for role, pin in record['mesh_pins'].items():
        report['current_stage'] = 'inherit_mesh:' + role
        mesh = _i23_read(pin)
        _i23_require(mesh['role'] == role.removeprefix('original_'), 'inherited mesh role differs')
        current = _i23_np.asarray(mesh['local_origin_xyz_m'], float)
        _i23_require(current.shape == (3,) and _i23_np.isfinite(current).all(), 'invalid inherited local origin')
        if origin is None:
            origin = current
        _i23_require(_i23_np.array_equal(origin, current), 'inherited meshes do not share local origin')
        meshes[role] = _i23_ValidatedSolid(mesh, parent['mesh_validation_reports'][role], role)
        report['inherited_evidence']['validated_mesh_roles'].append(role)
    report['current_stage'] = 'native_source_inputs'
    geometry = _i23_read(record['inputs']['geometry'])
    sections_pin = geometry['inputs']['original_06_sections']
    sections = _i23_read(sections_pin)
    protection_pin = geometry['inputs']['original_wet_protection_manifest']
    protection = _i23_read(protection_pin)['wet_protection']
    attachments, vdm = (_i23_read(record['inputs']['surface_attachments']), _i23_read(record['inputs']['vdm']))
    report['current_stage'] = 'native_manifest_binding'
    native, binding = _i23_load_native_bound(geometry['inputs']['original_hierarchy'], sections['hierarchy_identity_sha256'], sections['selected_leaf_ids'], protection)
    binding.update(sections_pin=sections_pin, wet_protection_pin=protection_pin)
    report['native_identity_binding'] = binding
    report['new_stages_completed'].append('native_binding')
    report['current_stage'] = 'native_half_arm_prisms'
    prisms = _i23_read(record['surface_prisms_pin'])
    _, sources = audit_hybrid_surface_composition_mechanism_3_audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    report.update(native_half_arm_sources_verified=True, source_reports=sources, original_source_sampling_cut_lookup_mismatches=record['original_source_sampling_cut_lookup_mismatches'])
    report['new_stages_completed'].append('native_prisms')
    report['current_stage'] = 'material_independent_boolean'
    material = audit_material_solids(*(meshes[key] for key in ('rock_before', 'original_rock_after', 'original_removed', 'surface_cutter', 'coupled_cutter', 'rock_after', 'extra_removed', 'removed', 'original_cutter')))
    report['material_boolean_evidence'] = material
    report['current_stage'] = 'material_saved_account'
    validate_material_account(record, meshes, material)
    report.update(materials_verified=True, material=material)
    report['new_stages_completed'].append('material')
    report['current_stage'] = 'coupled_cutter_components'
    library = _i22_manifold_library()
    _i23_require(len(meshes['coupled_cutter'].manifold(library).decompose()) == record['coupled_cutter_component_count'] == 1, 'actual coupled cutter disconnected')
    _i23_require(set(record['portal_connections']) == {'sink', 'spring'}, 'complete portal census required')
    for kind in ('sink', 'spring'):
        report['current_stage'] = 'port:' + kind
        report['exact_slice_reports'][kind] = {}
        try:
            report['portal_reports'][kind] = audit_hybrid_surface_composition_mechanism_3_audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, report['exact_slice_reports'][kind])
            report['new_stages_completed'].append('port:' + kind)
        except AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_ERRORS as error:
            record_failure(report, report['current_stage'], error)
            report['portal_reports'][kind] = {'verified': False, 'two_sided_complete_port_verified': False, 'errors': [report['errors'][-1]]}
    verified = not report['errors'] and all((report['portal_reports'].get(kind, {}).get('two_sided_complete_port_verified') is True for kind in ('sink', 'spring')))
    report.update(status='passed' if verified else 'refused', two_sided_complete_port_verified=verified, current_stage='complete')

def audit_hybrid_surface_composition_mechanism_4_audit(composition_pin, previous_pin):
    report = {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_AUDIT_SCHEMA, 'status': 'refused', 'errors': [], 'failures': [], 'failure_stage': None, 'composition_pin': composition_pin, 'native_half_arm_sources_verified': False, 'materials_verified': False, 'two_sided_complete_port_verified': False, 'portal_reports': {}, 'exact_slice_reports': {}, 'new_stages_completed': [], 'numerical_slice_policy': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_3_NUMERICAL_POLICY_SHA256, 'solid_validation_policy': _i22_SOLID_POLICY, 'solid_validation_policy_identity_sha256': _i22_SOLID_POLICY_SHA256, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False, 'native_exact': False, 'fine15_replaced': False, 'original_sampling_defects_revalidated_as_correct': False, 'whole_link_control_sill_verified': False, 'builder_or_slicer_called': False, 'scope': 'byte_bound_completed_mesh_evidence_and_new_native_material_full_port_cold_checks', 'tolerances': {'canonical_boundary_m': 1e-08, 'whole_port_gap_area_m2': 1e-08, 'collar_boolean_difference_m3': 1e-07}}
    try:
        resume(composition_pin, previous_pin, report)
    except AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_ERRORS as error:
        record_failure(report, report.get('current_stage', 'audit_entry'), error)
    return report

def _entry_audit_hybrid_surface_composition_v4():
    parser = _i23_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=_i23_Path, default=BASE / 'composition.json')
    parser.add_argument('--composition-sha256', default=COMPOSITION_SHA256)
    parser.add_argument('--previous-audit', type=_i23_Path, default=BASE / 'independent-audit-v1.json')
    parser.add_argument('--previous-audit-sha256', default=PREVIOUS_AUDIT_SHA256)
    parser.add_argument('--output', type=_i23_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i23_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    pin = {'path': str(args.composition.resolve()), 'sha256': args.composition_sha256}
    previous_pin = {'path': str(args.previous_audit.resolve()), 'sha256': args.previous_audit_sha256}
    started = _i23_time.monotonic()
    report = audit_hybrid_surface_composition_mechanism_4_audit(pin, previous_pin)
    report['resource'] = {'wall_seconds': _i23_time.monotonic() - started, 'actual_peak_rss_bytes': _i23_check_memory(), 'solver_calls': 0, 'source_artifacts_modified': False, 'exact_mesh_recomputations': 0, 'producer_stage_recomputations': 0}
    report['code_sha256'] = {**PREVIOUS_CODE, **{name: _i23_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tools/hybrid_surface_resume_saved_audit.py', 'tests/test_hybrid_geometry_saved_audit.py')}}
    report['identity_sha256'] = _i23_digest(report)
    payload = _i23_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i23_require(len(payload) <= _i23_MAX_BYTES, 'continuation audit exceeds 64MiB budget')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i23_json.dumps({'status': report['status'], 'errors': report['errors'], 'failure_stage': report['failure_stage'], 'output': str(output), 'sha256': _i23_file_sha256(output)}))
    if report['status'] != 'passed':
        raise SystemExit(1)
_i24_sys.path.insert(0, str(ROOT))
frozen = __import__('sys').modules[__name__]
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_AUDIT_SCHEMA = 'td-hybrid-surface-composition-independent-audit-v5'
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_AUDIT_SHA256 = '82aad9f51e59b4a9718b69d8c7a2b85e501e847d7f976cadadb1bb84ebdfb2a0'
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_CODE = {**PREVIOUS_CODE, 'tools/audit_hybrid_geometry.py': '9db6e56a046c4fb3fc4319add596c2e828a1763dabfffaf372f0a94c03b39396', 'tools/hybrid_surface_resume_saved_audit.py': 'd96494f0bf0467700e70dcf8ef2231d96002f2cf56572aeeb896a77f4c0844f5', 'tests/test_hybrid_geometry_saved_audit.py': 'c57b87e2efbd6225fd22db586ec7a2380ff9b5668ed6db0938a42e1c7924f2a6'}
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_ERRORS = AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_ERRORS + (ArithmeticError,)
INHERITED_FIELDS = ('composition_identity_sha256', 'inputs', 'mesh_pins', 'surface_prisms_pin', 'checkpoint_boolean_pin', 'stage_lineage', 'stage_lineage_verified', 'mesh_validation_reports', 'geometry_sha256', 'policy_identity_sha256', 'inherited_evidence', 'native_identity_binding', 'source_reports', 'original_source_sampling_cut_lookup_mismatches', 'native_half_arm_sources_verified', 'materials_verified', 'material_boolean_evidence', 'material', 'numerical_slice_policy', 'numerical_slice_policy_identity_sha256', 'solid_validation_policy', 'solid_validation_policy_identity_sha256', 'tolerances')

def validate_parent(composition_pin, parent_pin):
    _i24_require(composition_pin['sha256'] == COMPOSITION_SHA256 and parent_pin['sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_AUDIT_SHA256, 'only fixed composition03/v4 audit recovery authorized')
    record, parent = (_i24_read(composition_pin), _i24_read_audit(parent_pin))
    _i24_require(parent['schema'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_AUDIT_SCHEMA and parent['status'] == 'refused' and (parent['composition_pin'] == composition_pin) and (parent['composition_identity_sha256'] == record['identity_sha256']) and (parent['code_sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_CODE), 'v4 parent schema/identity/source registry differs')
    for name, sha in AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_CODE.items():
        _i24_require(_i24_file_sha256(ROOT / name) == sha, 'frozen parent source changed: ' + name)
    _, raw_mesh_parent = validate_resume_parent(composition_pin, parent['inherited_evidence']['audit_pin'])
    _i24_require(parent['errors'] == ['port:' + kind + ': ValueError: independent rational original solid occupancy failed' for kind in ('sink', 'spring')] and parent['new_stages_completed'] == ['native_binding', 'native_prisms', 'material'] and (parent['stage_lineage_verified'] is True) and (parent['native_half_arm_sources_verified'] is True) and (parent['materials_verified'] is True) and (parent['two_sided_complete_port_verified'] is False), 'unknown v4 completed-stage boundary')
    for name in ('inputs', 'mesh_pins', 'surface_prisms_pin', 'checkpoint_boolean_pin', 'stage_lineage'):
        _i24_require(parent[name] == record[name], 'inherited saved binding differs: ' + name)
    _i24_require(parent['mesh_validation_reports'] == raw_mesh_parent['mesh_validation_reports'] and set(parent['mesh_validation_reports']) == set(record['mesh_pins']) and (len(record['mesh_pins']) == 15) and (set(parent['inherited_evidence']['validated_mesh_roles']) == set(record['mesh_pins'])), 'complete original fifteen mesh evidence differs')
    for kind in ('sink', 'spring'):
        _i24_require(parent['portal_reports'][kind]['verified'] is False and parent['portal_reports'][kind]['two_sided_complete_port_verified'] is False, 'unverified parent port cannot be inherited')
    for pin in record['inputs'].values():
        _i24_checked_path(pin)
    for name in ('source_index_pin', 'source_composition_pin', 'checkpoint_pin'):
        _i24_checked_path(record['stage_lineage'][name])
    for pin in record['stage_lineage']['boolean_artifact_pins'].values():
        _i24_checked_path(pin)
    _i24_checked_path(record['checkpoint_boolean_pin'])
    geometry = _i24_read(record['inputs']['geometry'])
    binding = parent['native_identity_binding']
    sections_pin = geometry['inputs']['original_06_sections']
    sections = _i24_read(sections_pin)
    _i24_checked_path(geometry['inputs']['original_hierarchy'])
    _i24_checked_path(geometry['inputs']['original_wet_protection_manifest'])
    _i24_require(binding['verified'] is True and binding['original_inputs_or_pin_modified'] is False and (binding['archive_and_array_budgets_unchanged'] is True) and (binding['original_pin'] == geometry['inputs']['original_hierarchy']) and (binding['sections_pin'] == sections_pin) and (binding['wet_protection_pin'] == geometry['inputs']['original_wet_protection_manifest']) and (binding['expected_hierarchy_identity_sha256'] == binding['manifest_hierarchy_identity_sha256'] == sections['hierarchy_identity_sha256']), 'inherited rich native binding differs')
    _i24_require(parent['material_boolean_evidence'] == parent['material'] and parent['material']['independent_boolean_verified'] is True, 'incomplete inherited material proof')
    _i24_checked_path(record['surface_prisms_pin'])
    return (record, parent, geometry)

def audit_hybrid_surface_composition_mechanism_5_resume(composition_pin, parent_pin, report):
    report['current_stage'] = 'v4_parent_binding'
    record, parent, geometry = validate_parent(composition_pin, parent_pin)
    for name in INHERITED_FIELDS:
        report[name] = _i24_copy.deepcopy(parent[name])
    report['resumed_evidence'] = {'audit_pin': parent_pin, 'audit_identity_sha256': parent['identity_sha256'], 'composition_pin': composition_pin, 'composition_identity_sha256': record['identity_sha256'], 'completed_stages': ['native_binding', 'native_prisms', 'material'], 'native_prisms_material_inherited': True, 'source_material_recomputed': False, 'ports_inherited': False, 'audit_code_sha256_matched': True, 'validated_mesh_roles': []}
    report['current_stage'] = 'interval_runtime_binding'
    report['interval_winding']['runtime'] = _i24_runtime_identity()
    meshes, origin = ({}, None)
    for role, pin in record['mesh_pins'].items():
        report['current_stage'] = 'bind_original_mesh:' + role
        mesh = _i24_read(pin)
        _i24_require(mesh['role'] == role.removeprefix('original_'), 'original mesh role differs')
        own_origin = _i24_np.asarray(mesh['local_origin_xyz_m'], float)
        _i24_require(own_origin.shape == (3,) and _i24_np.isfinite(own_origin).all(), 'invalid original mesh origin')
        if origin is None:
            origin = own_origin
        _i24_require(_i24_np.array_equal(origin, own_origin), 'original mesh frames differ')
        solid = _i24_ValidatedSolid(mesh, parent['mesh_validation_reports'][role], role)
        meshes[role] = _i24_IntervalSolid(solid, pin, report['interval_winding']['queries'])
        report['resumed_evidence']['validated_mesh_roles'].append(role)
    report['current_stage'] = 'read_saved_port_inputs'
    prisms = _i24_read(record['surface_prisms_pin'])
    attachments, vdm = (_i24_read(record['inputs']['surface_attachments']), _i24_read(record['inputs']['vdm']))
    for kind in ('sink', 'spring'):
        report['current_stage'] = 'port:' + kind
        report['exact_slice_reports'][kind] = {}
        try:
            report['portal_reports'][kind] = frozen.audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, report['exact_slice_reports'][kind])
            report['new_stages_completed'].append('port:' + kind)
        except AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_ERRORS as error:
            record_failure(report, report['current_stage'], error)
            report['portal_reports'][kind] = {'verified': False, 'two_sided_complete_port_verified': False, 'errors': [report['errors'][-1]]}
    queries = report['interval_winding']['queries']
    certified = bool(queries) and all((query['verified'] is True for query in queries))
    report['interval_winding']['every_query_certified'] = certified
    verified = certified and (not report['errors']) and all((report['portal_reports'][kind].get('two_sided_complete_port_verified') is True for kind in ('sink', 'spring')))
    report.update(status='passed' if verified else 'refused', two_sided_complete_port_verified=verified, current_stage='complete')

def audit_hybrid_surface_composition_mechanism_5_audit(composition_pin, parent_pin):
    report = {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_AUDIT_SCHEMA, 'status': 'refused', 'errors': [], 'failures': [], 'failure_stage': None, 'composition_pin': composition_pin, 'new_stages_completed': [], 'portal_reports': {}, 'exact_slice_reports': {}, 'native_half_arm_sources_verified': False, 'materials_verified': False, 'two_sided_complete_port_verified': False, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False, 'native_exact': False, 'fine15_replaced': False, 'original_sampling_defects_revalidated_as_correct': False, 'whole_link_control_sill_verified': False, 'builder_or_slicer_called': False, 'scope': 'fixed_v4_completed_sources_material_meshes_inherited_only_unresolved_full_ports_rechecked', 'interval_winding': {'policy': _i24_POLICY, 'policy_identity_sha256': _i24_POLICY_SHA256, 'queries': [], 'every_query_certified': False}}
    try:
        audit_hybrid_surface_composition_mechanism_5_resume(composition_pin, parent_pin, report)
    except AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_ERRORS as error:
        record_failure(report, report.get('current_stage', 'audit_entry'), error)
    return report

def _entry_audit_hybrid_surface_composition_v5():
    parser = _i24_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=_i24_Path, default=BASE / 'composition.json')
    parser.add_argument('--composition-sha256', default=COMPOSITION_SHA256)
    parser.add_argument('--previous-audit', type=_i24_Path, default=BASE / 'independent-audit-v2.json')
    parser.add_argument('--previous-audit-sha256', default=AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_AUDIT_SHA256)
    parser.add_argument('--output', type=_i24_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i24_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    started = _i24_time.monotonic()
    report = audit_hybrid_surface_composition_mechanism_5_audit({'path': str(args.composition.resolve()), 'sha256': args.composition_sha256}, {'path': str(args.previous_audit.resolve()), 'sha256': args.previous_audit_sha256})
    report['resource'] = {'wall_seconds': _i24_time.monotonic() - started, 'actual_peak_rss_bytes': _i24_check_memory(), 'solver_calls': 0, 'source_artifacts_modified': False, 'exact_mesh_recomputations': 0, 'native_prism_material_recomputations': 0, 'producer_stage_recomputations': 0, 'interval_triangle_evaluations': sum((query.get('triangle_interval_evaluations', 0) for query in report['interval_winding']['queries']))}
    report['code_sha256'] = {**AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_CODE, **{name: _i24_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_geometry.py', 'tools/hybrid_interval_winding_saved_audit.py', 'tests/test_hybrid_geometry_saved_audit.py')}}
    report['identity_sha256'] = _i24_digest(report)
    payload = _i24_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i24_require(len(payload) <= _i24_MAX_BYTES, 'interval continuation report exceeds 64MiB')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i24_json.dumps({'status': report['status'], 'errors': report['errors'], 'failure_stage': report['failure_stage'], 'output': str(output), 'sha256': _i24_file_sha256(output)}))
    if report['status'] != 'passed':
        raise SystemExit(1)
_i25_sys.path.insert(0, str(ROOT))
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_AUDIT_SCHEMA = 'td-hybrid-surface-composition-independent-audit-v6'
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_COMPOSITION_SHA256 = COMPOSITION_SHA256
V5_AUDIT_SHA256 = 'ba3da3e65c41db558b52fd2fb046d89f571f06f4fd41cd572fcdeb309f80e245'
V4_AUDIT_SHA256 = '82aad9f51e59b4a9718b69d8c7a2b85e501e847d7f976cadadb1bb84ebdfb2a0'
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_BASE = BASE
V4_PATH = AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_BASE / 'independent-audit-v2.json'
V5_CODE = {**AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_PREVIOUS_CODE, 'tools/audit_hybrid_geometry.py': 'bb1500f24ebdc3702645ea7676de6a774556f8bdd79b479ab7600eac4783fb16', 'tools/hybrid_interval_winding_saved_audit.py': 'cc9fe11238bbdcd70ae14f32d73e83108c50c631515076412ed656715a563d81', 'tests/test_hybrid_geometry_saved_audit.py': '127a62a35c4b823e417f39bd3a70ef88a56a18aa468c863f684c306a6d0bed67'}
AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_ERRORS = AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_ERRORS

def iter_input_pins(record):
    inputs = record['inputs']
    for name in ('geometry', 'geometry_audit', 'graph', 'original_source_sampling', 'surface_attachments', 'vdm'):
        yield ('inputs.' + name, inputs[name])
    for name, pin in inputs['mesh_pins'].items():
        yield ('inputs.mesh_pins.' + name, pin)
    for name, pin in inputs['surface_nodes'].items():
        yield ('inputs.surface_nodes.' + name, pin)

def audit_hybrid_surface_composition_mechanism_6_validate_parent(composition_pin, v5_pin, v4_pin):
    _i25_require(composition_pin['sha256'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_COMPOSITION_SHA256 and v5_pin['sha256'] == V5_AUDIT_SHA256 and (v4_pin['sha256'] == V4_AUDIT_SHA256), 'only fixed composition03/v5/v4 continuation authorized')
    record, failed_v5 = (_i25_read(composition_pin), _i25_read_audit(v5_pin))
    _i25_require(failed_v5['schema'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_5_AUDIT_SCHEMA and failed_v5['status'] == 'refused' and (failed_v5['composition_pin'] == composition_pin) and (failed_v5['failure_stage'] == 'v4_parent_binding') and (failed_v5['errors'] == ["v4_parent_binding: KeyError: 'path'"]) and (failed_v5['code_sha256'] == V5_CODE), 'v5 failure report or code binding differs')
    for name, sha in V5_CODE.items():
        _i25_require(_i25_file_sha256(ROOT / name) == sha, 'fixed v5 source changed: ' + name)
    old_record, parent = (_i25_read(composition_pin), _i25_read_audit(v4_pin))
    _i25_require(parent['composition_pin'] == composition_pin and parent['schema'] == AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_4_AUDIT_SCHEMA and (parent['status'] == 'refused') and (parent['composition_identity_sha256'] == old_record['identity_sha256']) and (parent['code_sha256'] == {**PREVIOUS_CODE, 'tools/audit_hybrid_surface_composition_v4.py': '9db6e56a046c4fb3fc4319add596c2e828a1763dabfffaf372f0a94c03b39396', 'tools/hybrid_surface_resume_saved_audit.py': 'd96494f0bf0467700e70dcf8ef2231d96002f2cf56572aeeb896a77f4c0844f5', 'tests/test_hybrid_surface_composition_v4_saved_audit.py': 'c57b87e2efbd6225fd22db586ec7a2380ff9b5668ed6db0938a42e1c7924f2a6'}), 'fixed v4 parent binding differs')
    validate_resume_parent(composition_pin, parent['inherited_evidence']['audit_pin'])
    _i25_require(parent['new_stages_completed'] == ['native_binding', 'native_prisms', 'material'] and parent['native_half_arm_sources_verified'] is True and (parent['materials_verified'] is True) and (parent['two_sided_complete_port_verified'] is False), 'v4 completed evidence boundary differs')
    _i25_require(record['identity_sha256'] == old_record['identity_sha256'], 'composition identity changed')
    for label, pin in iter_input_pins(record):
        _i25_checked_path(pin)
    for name in ('source_index_pin', 'source_composition_pin', 'checkpoint_pin'):
        _i25_checked_path(record['stage_lineage'][name])
    for pin in record['stage_lineage']['boolean_artifact_pins'].values():
        _i25_checked_path(pin)
    _i25_checked_path(record['checkpoint_boolean_pin'])
    geometry = _i25_read(record['inputs']['geometry'])
    sections_pin = geometry['inputs']['original_06_sections']
    sections = _i25_read(sections_pin)
    _i25_checked_path(geometry['inputs']['original_hierarchy'])
    _i25_checked_path(geometry['inputs']['original_wet_protection_manifest'])
    binding = parent['native_identity_binding']
    _i25_require(binding['verified'] is True and binding['original_inputs_or_pin_modified'] is False and (binding['original_pin'] == geometry['inputs']['original_hierarchy']) and (binding['sections_pin'] == sections_pin) and (binding['expected_hierarchy_identity_sha256'] == binding['manifest_hierarchy_identity_sha256'] == sections['hierarchy_identity_sha256']), 'v4 native binding differs')
    _i25_require(parent['material_boolean_evidence'] == parent['material'] and parent['material']['independent_boolean_verified'] is True, 'v4 material evidence differs')
    return (record, parent, geometry)

def audit_hybrid_surface_composition_mechanism_6_resume(composition_pin, v5_pin, v4_pin, report):
    report['current_stage'] = 'v5_parent_binding'
    record, parent, geometry = audit_hybrid_surface_composition_mechanism_6_validate_parent(composition_pin, v5_pin, v4_pin)
    inherited_names = ('composition_identity_sha256', 'inputs', 'mesh_pins', 'surface_prisms_pin', 'checkpoint_boolean_pin', 'stage_lineage', 'stage_lineage_verified', 'mesh_validation_reports', 'geometry_sha256', 'policy_identity_sha256', 'inherited_evidence', 'native_identity_binding', 'source_reports', 'original_source_sampling_cut_lookup_mismatches', 'native_half_arm_sources_verified', 'materials_verified', 'material_boolean_evidence', 'material', 'numerical_slice_policy', 'numerical_slice_policy_identity_sha256', 'solid_validation_policy', 'solid_validation_policy_identity_sha256', 'tolerances')
    for name in inherited_names:
        report[name] = _i25_copy.deepcopy(parent[name])
    report['resumed_evidence'] = {'audit_pin': v4_pin, 'audit_identity_sha256': parent['identity_sha256'], 'failed_continuation_pin': v5_pin, 'failed_continuation_sha256': V5_AUDIT_SHA256, 'composition_pin': composition_pin, 'composition_identity_sha256': record['identity_sha256'], 'completed_stages': ['native_binding', 'native_prisms', 'material'], 'native_prisms_material_inherited': True, 'source_material_recomputed': False, 'ports_inherited': False, 'audit_code_sha256_matched': True, 'validated_mesh_roles': []}
    report['current_stage'] = 'interval_runtime_binding'
    report['interval_winding']['runtime'] = _i25_runtime_identity()
    meshes, origin = ({}, None)
    for role, pin in record['mesh_pins'].items():
        report['current_stage'] = 'bind_original_mesh:' + role
        mesh = _i25_read(pin)
        _i25_require(mesh['role'] == role.removeprefix('original_'), 'original mesh role differs')
        own_origin = _i25_np.asarray(mesh['local_origin_xyz_m'], float)
        _i25_require(own_origin.shape == (3,) and _i25_np.isfinite(own_origin).all(), 'invalid original mesh origin')
        if origin is None:
            origin = own_origin
        _i25_require(_i25_np.array_equal(origin, own_origin), 'original mesh frames differ')
        meshes[role] = _i25_IntervalSolid(_i25_ValidatedSolid(mesh, parent['mesh_validation_reports'][role], role), pin, report['interval_winding']['queries'])
        report['resumed_evidence']['validated_mesh_roles'].append(role)
    report['current_stage'] = 'read_saved_port_inputs'
    prisms = _i25_read(record['surface_prisms_pin'])
    attachments, vdm = (_i25_read(record['inputs']['surface_attachments']), _i25_read(record['inputs']['vdm']))
    for kind in ('sink', 'spring'):
        report['current_stage'] = 'port:' + kind
        report['exact_slice_reports'][kind] = {}
        try:
            report['portal_reports'][kind] = audit_hybrid_surface_composition_mechanism_3_audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, report['exact_slice_reports'][kind])
            report['new_stages_completed'].append('port:' + kind)
        except AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_ERRORS as error:
            record_failure(report, report['current_stage'], error)
            report['portal_reports'][kind] = {'verified': False, 'two_sided_complete_port_verified': False, 'errors': [report['errors'][-1]]}
    queries = report['interval_winding']['queries']
    certified = bool(queries) and all((query.get('verified') is True for query in queries))
    report['interval_winding']['every_query_certified'] = certified
    passed = certified and (not report['errors']) and all((report['portal_reports'][kind].get('two_sided_complete_port_verified') is True for kind in ('sink', 'spring')))
    report.update(status='passed' if passed else 'refused', two_sided_complete_port_verified=passed, current_stage='complete')

def audit_hybrid_surface_composition_mechanism_6_audit(composition_pin, v5_pin, v4_pin):
    report = {'schema': AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_AUDIT_SCHEMA, 'status': 'refused', 'errors': [], 'failures': [], 'failure_stage': None, 'composition_pin': composition_pin, 'new_stages_completed': [], 'portal_reports': {}, 'exact_slice_reports': {}, 'native_half_arm_sources_verified': False, 'materials_verified': False, 'two_sided_complete_port_verified': False, 'hydraulic_constitutive_law_accepted': False, 'hydraulic_solved': False, 'native_exact': False, 'fine15_replaced': False, 'original_sampling_defects_revalidated_as_correct': False, 'whole_link_control_sill_verified': False, 'builder_or_slicer_called': False, 'scope': 'fixed_v4_native_prisms_material_inherited_only_unresolved_full_ports_rechecked', 'interval_winding': {'policy': _i25_POLICY, 'policy_identity_sha256': _i25_POLICY_SHA256, 'queries': [], 'every_query_certified': False}}
    try:
        audit_hybrid_surface_composition_mechanism_6_resume(composition_pin, v5_pin, v4_pin, report)
    except AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_ERRORS as error:
        record_failure(report, report.get('current_stage', 'audit_entry'), error)
    return report

def _entry_audit_hybrid_surface_composition_v6():
    parser = _i25_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=_i25_Path, default=AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_BASE / 'composition.json')
    parser.add_argument('--composition-sha256', default=AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_COMPOSITION_SHA256)
    parser.add_argument('--previous-audit', type=_i25_Path, default=AUDIT_HYBRID_SURFACE_COMPOSITION_MECHANISM_6_BASE / 'independent-audit-v3.json')
    parser.add_argument('--previous-audit-sha256', default=V5_AUDIT_SHA256)
    parser.add_argument('--v4-audit', type=_i25_Path, default=V4_PATH)
    parser.add_argument('--v4-audit-sha256', default=V4_AUDIT_SHA256)
    parser.add_argument('--output', type=_i25_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i25_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit file required')
    started = _i25_time.monotonic()
    report = audit_hybrid_surface_composition_mechanism_6_audit({'path': str(args.composition.resolve()), 'sha256': args.composition_sha256}, {'path': str(args.previous_audit.resolve()), 'sha256': args.previous_audit_sha256}, {'path': str(args.v4_audit.resolve()), 'sha256': args.v4_audit_sha256})
    report['resource'] = {'wall_seconds': _i25_time.monotonic() - started, 'actual_peak_rss_bytes': _i25_check_memory(), 'solver_calls': 0, 'source_artifacts_modified': False, 'exact_mesh_recomputations': 0, 'native_prism_material_recomputations': 0, 'producer_stage_recomputations': 0, 'interval_triangle_evaluations': sum((q.get('triangle_interval_evaluations', 0) for q in report['interval_winding']['queries']))}
    report['code_sha256'] = {**V5_CODE, 'tools/audit_hybrid_geometry.py': _i25_file_sha256(ROOT / 'tools/audit_hybrid_geometry.py'), 'tests/test_hybrid_geometry_saved_audit.py': _i25_file_sha256(ROOT / 'tests/test_hybrid_geometry_saved_audit.py')}
    report['identity_sha256'] = _i25_digest(report)
    payload = _i25_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    _i25_require(len(payload) <= _i25_MAX_BYTES, 'continuation audit exceeds 64MiB')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i25_json.dumps({'status': report['status'], 'errors': report['errors'], 'failure_stage': report['failure_stage'], 'output': str(output), 'sha256': _i25_file_sha256(output)}))
    if report['status'] != 'passed':
        raise SystemExit(1)
