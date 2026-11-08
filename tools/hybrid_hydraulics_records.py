"""Consolidated hybrid_hydraulics_records implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import asdict as _i2_asdict
from dataclasses import replace as _i2_replace
import hashlib as _i2_hashlib
import json as _i2_json
import os as _i2_os
from pathlib import Path as _i2_Path
import tempfile as _i2_tempfile
from terrain_pipeline.hybrid_geometry import FilePin as _i2_FilePin
from terrain_pipeline.hybrid_geometry import MAX_FILE_BYTES as _i2_MAX_FILE_BYTES
from terrain_pipeline.hybrid_geometry import canonical_json as _i2_canonical_json
from terrain_pipeline.hybrid_geometry import identity as _i2_identity
from terrain_pipeline.hybrid_geometry import load_graph as _i2_load_graph
from terrain_pipeline.hybrid_geometry import native_bed_pieces as _i2_native_bed_pieces
from terrain_pipeline.hybrid_geometry import read_pinned as _i2_read_pinned
from terrain_pipeline.hybrid_hydraulics import common_Model as _i2_Model
CATEGORY = 'C'

def file_sha(path):
    digest = _i2_hashlib.sha256()
    with _i2_Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def pin(path, sha=None):
    path = _i2_Path(path).resolve(strict=True)
    return _i2_FilePin(str(path), sha or file_sha(path))

def saved_pin(record):
    return _i2_FilePin(record['path'], record['sha256'])

def check_original_pins(inputs):
    for key, record in inputs.items():
        original = saved_pin(record)
        if file_sha(original.path) != original.sha256:
            raise ValueError('original input pin changed: ' + key)

def validate_geometry(graph_record, geometry_pin, geometry_audit_pin):
    graph = _i2_load_graph(graph_record)
    geometry, audit = (_i2_read_pinned(geometry_pin), _i2_read_pinned(geometry_audit_pin))
    if geometry['schema'] != 'td-hybrid-river-geometry-v1' or geometry['graph_identity_sha256'] != graph_record['identity_sha256']:
        raise ValueError('geometry belongs to a different typed graph')
    unsigned = dict(geometry)
    geometry_identity = unsigned.pop('identity_sha256')
    if _i2_identity(unsigned) != geometry_identity:
        raise ValueError('geometry identity mismatch')
    if audit['status'] != 'passed' or audit.get('errors') or audit['geometry_sha256'] != geometry_pin.sha256 or (audit['graph_identity_sha256'] != graph_record['identity_sha256']):
        raise ValueError('geometry independent audit binding mismatch')
    if audit['schema'] != 'td-hybrid-cave-geometry-independent-audit-v1':
        raise ValueError('wrong independent geometry audit schema')
    if not audit['actual_hydraulic_sections_verified'] or not audit['actual_portal_connections_verified']:
        raise ValueError('node adjacency is not actual hydraulic/void attachment evidence')
    for key, graph_pin in graph.inputs:
        if geometry['inputs'].get(key) != _i2_asdict(graph_pin):
            raise ValueError('geometry omitted immutable parent pin: ' + key)
        if file_sha(graph_pin.path) != graph_pin.sha256:
            raise ValueError('graph original pin changed: ' + key)
    check_original_pins(geometry['inputs'])
    for kind, ordinal in (('sink', 0), ('spring', -1)):
        node = next((node for node in graph.nodes if node.kind == kind))
        port = _i2_json.loads(node.source_record_json)
        binding = geometry['portal_bindings'][kind]
        if binding['port_arc_id'] != node.port_arc_id or binding['port_identity_sha256'] != port['identity_sha256']:
            raise ValueError('actual portal differs from selected audited midpoint')
        if geometry['portal_sections'][kind]['pieces'] != _i2_native_bed_pieces(port):
            raise ValueError('portal omitted/changed complete native function')
    active_arcs = {arc.arc_id: arc for arc in graph.arcs if arc.hydraulic_role == 'sample_route'}
    required_arcs = {'surface_in': 'engineered:sink:half_arm_attachment', 'underground': 'engineered:underground', 'surface_out': 'engineered:spring:half_arm_attachment'}
    station_ids = []
    regions = []
    for cell in geometry['hydraulic_cells']:
        region = cell['route_region']
        if region not in required_arcs or cell['graph_arc_id'] != required_arcs[region] or cell['graph_arc_id'] not in active_arcs:
            raise ValueError('actual section is not on the physical graph route')
        reference = cell['section_geometry_reference']
        station_ids.append(reference['station_id'])
        regions.append(region)
        ring = reference['derived_ring_xyz_m']
        origin = reference['origin_xyz_m']
        transverse = reference['transverse_unit_xz']
        import math
        if len(transverse) != 2 or abs(math.hypot(*transverse) - 1) > 1e-10:
            raise ValueError('section frame is not a unit transverse direction')
        section = cell['section']
        shape = section['polygon_transverse_elevation_m'] if section['kind'] == 'closed_polygon' else section['polyline_transverse_elevation_m']
        if len(ring) != len(shape):
            raise ValueError('storage shape differs from final derived ring')
        for point, projected in zip(ring, shape):
            if len(point) != 3 or not all((math.isfinite(value) for value in point)):
                raise ValueError('nonfinite actual section ring')
            delta_x, delta_z = (point[0] - origin[0], point[2] - origin[2])
            if abs(delta_x * transverse[0] + delta_z * transverse[1] - projected[0]) > 1e-08 or abs(point[1] - projected[1]) > 1e-08 or abs(delta_x * transverse[1] - delta_z * transverse[0]) > 1e-08:
                raise ValueError('section polygon is not the actual final VDM ring projection')
    if len(set(station_ids)) != len(station_ids) or set(regions) != set(required_arcs) or regions != sorted(regions, key=lambda region: list(required_arcs).index(region)):
        raise ValueError('missing/duplicated/out-of-order physical route stations')
    return (_i2_Model.from_geometry(geometry), geometry)

def atomic_save(output, name, record):
    sealed = dict(record)
    sealed.pop('identity_sha256', None)
    sealed['identity_sha256'] = _i2_identity(sealed)
    payload = _i2_canonical_json(sealed).encode('utf-8')
    if len(payload) > _i2_MAX_FILE_BYTES:
        raise ValueError('bounded checkpoint JSON exceeded')
    descriptor, temporary = _i2_tempfile.mkstemp(prefix='.checkpoint-', suffix='.tmp', dir=output)
    try:
        with _i2_os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            _i2_os.fsync(stream.fileno())
        _i2_os.replace(temporary, output / name)
    finally:
        if _i2_Path(temporary).exists():
            _i2_Path(temporary).unlink()
    return {'path': str(output / name), 'sha256': file_sha(output / name), 'identity_sha256': sealed['identity_sha256']}

def meaningful_evidence(result):
    if result['scenario'] == 'pulse':
        ordinal = result['ledger_columns'].index('source_tracer_out_m3')
        source_out = result['boundary_ledger_m3'][-1][ordinal]
        start = result['times_s'][-1] - 100.0
        observed = start in result['times_s']
        recent = source_out - result['boundary_ledger_m3'][result['times_s'].index(start)][ordinal] if observed else None
        return {'passed': bool(source_out >= 2.7 and observed and (recent >= 0.5)), 'source_tracer_out_m3': source_out, 'source_tracer_out_last_100s_m3': recent, 'last_100s_start_observed': observed, 'minimum_source_out_m3': 2.7, 'minimum_recent_source_out_m3': 0.5}
    returned = result['tailwater_tracer_mass_m3'][-1][0]
    return {'passed': bool(returned >= 1.0 and result['reverse_reached_sink']), 'tailwater_tracer_in_first_surface_cell_m3': returned, 'minimum_returned_tailwater_m3': 1.0}

def paired_refinement(base, refined):
    fields = ('paired_link_water_integral_m3', 'paired_link_source_integral_m3', 'paired_link_tailwater_integral_m3', 'paired_link_untraced_integral_m3', 'untraced_water_volume_m3')
    if base['times_s'] != refined['times_s'] or base['link_ids'] != refined['link_ids']:
        raise ValueError('paired-link refinement identities/times differ')
    differences = {}
    for key in fields:
        if len(base[key]) != len(refined[key]):
            raise ValueError('paired-link refinement shape differs')
        difference = 0.0
        for first, second in zip(base[key], refined[key]):
            if len(first) != len(second):
                raise ValueError('paired-link refinement shape differs')
            difference = max(difference, max((abs(left - right) for left, right in zip(first, second))))
        differences[key] = difference
    if len(base['outlet_untraced_out_m3']) != len(refined['outlet_untraced_out_m3']):
        raise ValueError('untraced outlet refinement shape differs')
    differences['outlet_untraced_out_m3'] = max((abs(first - second) for first, second in zip(base['outlet_untraced_out_m3'], refined['outlet_untraced_out_m3'])))
    return {'status': 'passed' if max(differences.values()) <= 0.0001 else 'refused', 'absolute_tolerance_m3': 0.0001, 'max_absolute_differences_m3': differences}

def physical_model_identity(record):
    return _i2_identity({key: record[key] for key in PHYSICAL_MODEL_FIELDS})

def accuracy_policy():
    return {'schema': 'td-hybrid-river-accuracy-policy-v7', 'integration': 'BDF', 'forcing_configuration_pin_unchanged': True, 'parameter_transform': {'base': {'relative_tolerance_divisor': 64, 'absolute_tolerance_divisor': 64, 'max_step_divisor': 4}, 'refined': {'relative_tolerance_divisor': 256, 'absolute_tolerance_divisor': 256, 'max_step_divisor': 8}}, 'unchanged_scope': 'all_other_pinned_Experiment_parameters_initial_geometry_slot_forcing_and_guards', 'comparison_gates_unchanged': {'volume_absolute_tolerance_m3': 0.0001, 'head_absolute_tolerance_m': 0.001, 'volume_relative_tolerance': 0.01, 'paired_and_origin_absolute_tolerance_m3': 0.0001}, 'reused_cases_allowed': False, 'precision_change_not_physical_change': True}

def precision_experiments(original):
    base = _i2_replace(original, relative_tolerance=original.relative_tolerance / 64, absolute_tolerance=original.absolute_tolerance / 64, max_step_s=original.max_step_s / 4)
    refined = _i2_replace(original, relative_tolerance=original.relative_tolerance / 256, absolute_tolerance=original.absolute_tolerance / 256, max_step_s=original.max_step_s / 8)
    return (base, refined)
PHYSICAL_MODEL_FIELDS = ('model_version', 'model_parameters', 'friction_policy', 'inventory_policy', 'forcing_configuration_pin', 'graph_identity_sha256', 'geometry_identity_sha256')
