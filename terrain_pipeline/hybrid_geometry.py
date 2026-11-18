"""Consolidated hybrid_geometry implementations; numeric expressions preserved."""
from __future__ import annotations

from dataclasses import asdict as _i7_asdict
from dataclasses import dataclass as _i7_dataclass
import hashlib as _i7_hashlib
import json as _i7_json
import math as _i7_math
from pathlib import Path as _i7_Path
import math as _i0_math
import numpy as _i0_np
import psutil as _i0_psutil
from shapely.geometry import LineString as _i0_LineString
from shapely.geometry import Polygon as _i0_Polygon
from dataclasses import asdict as _i1_asdict
from dataclasses import dataclass as _i1_dataclass
import json as _i1_json
import math as _i1_math
import numpy as _i1_np
import psutil as _i1_psutil
from terrain_pipeline import channel_geometry as _i1_source
from terrain_pipeline.td_shared_channel_fine import _center_cut as _i1__center_cut
from terrain_pipeline.td_shared_channel_fine import compact_node_fans as _i1_compact_node_fans
import numpy as _i2_np
from shapely.geometry import Polygon as _i2_Polygon
import math as _i5_math
import numpy as _i5_np
import psutil as _i5_psutil
from shapely.geometry import LineString as _i5_LineString
from shapely.geometry import Point as _i5_Point
from shapely.geometry import Polygon as _i5_Polygon
from shapely.ops import unary_union as _i5_unary_union
from collections import defaultdict as _i3_defaultdict
from fractions import Fraction as _i3_Fraction
import math as _i3_math
import numpy as _i3_np
from shapely.geometry import LineString as _i3_LineString
from shapely.geometry import Point as _i3_Point
from shapely.geometry import Polygon as _i3_Polygon
from shapely.ops import polygonize_full as _i3_polygonize_full
from shapely.ops import unary_union as _i3_unary_union
from collections import defaultdict as _i4_defaultdict
from fractions import Fraction as _i4_Fraction
import math as _i4_math
import numpy as _i4_np
from shapely.geometry import Polygon as _i4_Polygon
from shapely.geometry import box as _i4_box
from shapely.ops import unary_union as _i4_unary_union
from shapely.strtree import STRtree as _i4_STRtree
import math as _i6_math
import numpy as _i6_np
from shapely.geometry import LineString as _i6_LineString
from shapely.geometry import Point as _i6_Point
from shapely.geometry import Polygon as _i6_Polygon
from dataclasses import asdict as _i8_asdict
from dataclasses import dataclass as _i8_dataclass
import math as _i8_math
import numpy as _i8_np
from fractions import Fraction as _i15_Fraction
import math as _i15_math
import numpy as _i15_np
from shapely.geometry import LineString as _i15_LineString
from shapely.geometry import Polygon as _i15_Polygon
from shapely.ops import triangulate as _i15_triangulate
from shapely.ops import unary_union as _i15_unary_union
import numpy as _i14_np
import numpy as _i9_np
from fractions import Fraction as _i10_Fraction
import math as _i10_math
import numpy as _i10_np
from shapely.geometry import LineString as _i10_LineString
from shapely.geometry import Polygon as _i10_Polygon
from shapely.ops import triangulate as _i10_triangulate
from shapely.ops import unary_union as _i10_unary_union
import numpy as _i11_np
from shapely.geometry import Polygon as _i11_Polygon
import math as _i12_math
import numpy as _i12_np
from shapely.geometry import Polygon as _i12_Polygon

CATEGORY = 'C'

# Source: terrain_pipeline.hybrid_river_graph
HYBRID_RIVER_GRAPH_SCHEMA = 'td-hybrid-river-graph-v1'

# Source: terrain_pipeline.hybrid_river_graph
MAX_FILE_BYTES = 64 * 1024 * 1024

# Source: terrain_pipeline.hybrid_river_graph
MAX_SURFACE_NODES = 128

# Source: terrain_pipeline.hybrid_river_graph
def canonical_json(record):
    return _i7_json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False)

# Source: terrain_pipeline.hybrid_river_graph
def identity(record):
    return _i7_hashlib.sha256(canonical_json(record).encode('utf-8')).hexdigest()

# Source: terrain_pipeline.hybrid_river_graph
@_i7_dataclass(frozen=True)
class FilePin:
    path: str
    sha256: str

    def __post_init__(self):
        if not _i7_Path(self.path).is_absolute() or len(self.sha256) != 64:
            raise ValueError('pins require absolute paths and SHA256')
        int(self.sha256, 16)

# Source: terrain_pipeline.hybrid_river_graph
def read_pinned(pin: FilePin):
    path = _i7_Path(pin.path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('pinned JSON exceeds bounded file size')
    data = path.read_bytes()
    if _i7_hashlib.sha256(data).hexdigest() != pin.sha256:
        raise ValueError('pinned file SHA256 mismatch')
    return _i7_json.loads(data)

# Source: terrain_pipeline.hybrid_river_graph
@_i7_dataclass(frozen=True)
class RiverNode:
    node_id: str
    kind: str
    xyz_m: tuple[float, float, float]
    source_record_json: str
    port_arc_id: str | None = None
    source_xyz_m: tuple[float, float, float] | None = None
    bed_xyz_m: tuple[float, float, float] | None = None

    def __post_init__(self):
        if self.kind not in ('surface', 'sink', 'spring'):
            raise ValueError('unknown river node type')
        if not isinstance(self.xyz_m, tuple) or len(self.xyz_m) != 3:
            raise ValueError('XYZ must be an immutable three-tuple')
        if not all((_i7_math.isfinite(value) for value in self.xyz_m)):
            raise ValueError('nonfinite XYZ')
        for coordinates in (self.source_xyz_m, self.bed_xyz_m):
            if coordinates is not None and (not isinstance(coordinates, tuple) or len(coordinates) != 3 or (not all((_i7_math.isfinite(value) for value in coordinates)))):
                raise ValueError('source/bed coordinates must be finite immutable XYZ')
        if self.kind == 'surface' and (self.source_xyz_m != self.xyz_m or self.bed_xyz_m is None):
            raise ValueError('surface reference XYZ and actual derived bed XYZ must be distinct fields')
        if self.kind != 'surface' and self.bed_xyz_m != self.xyz_m:
            raise ValueError('route station XYZ must represent derived portal bed')

# Source: terrain_pipeline.hybrid_river_graph
@_i7_dataclass(frozen=True)
class RiverArc:
    arc_id: str
    kind: str
    node_ids: tuple[str, str]
    hydraulic_role: str
    source_record_json: str

    def __post_init__(self):
        if self.kind not in ('surface', 'underground', 'portal_attachment'):
            raise ValueError('unknown river arc type')
        if not isinstance(self.node_ids, tuple) or len(self.node_ids) != 2:
            raise ValueError('arc endpoints must be immutable')
        if self.hydraulic_role != ('context_only' if self.kind == 'surface' else 'sample_route'):
            raise ValueError('surface context cannot supply duplicate cumulative Q')

# Source: terrain_pipeline.hybrid_river_graph
@_i7_dataclass(frozen=True)
class HybridRiverGraph:
    nodes: tuple[RiverNode, ...]
    arcs: tuple[RiverArc, ...]
    inputs: tuple[tuple[str, FilePin], ...]
    bypass_arc_ids: tuple[str, ...]

    def __post_init__(self):
        if not all((isinstance(value, tuple) for value in (self.nodes, self.arcs, self.inputs, self.bypass_arc_ids))):
            raise ValueError('graph collections must be immutable tuples')
        node_ids = [node.node_id for node in self.nodes]
        arc_ids = [arc.arc_id for arc in self.arcs]
        if len(set(node_ids)) != len(node_ids) or len(set(arc_ids)) != len(arc_ids):
            raise ValueError('duplicate graph identities')
        if sum((node.kind == 'surface' for node in self.nodes)) > MAX_SURFACE_NODES:
            raise ValueError('surface node resource limit exceeded')
        if any((endpoint not in node_ids for arc in self.arcs for endpoint in arc.node_ids)):
            raise ValueError('dangling graph arc')
        if len([node for node in self.nodes if node.kind == 'sink']) != 1 or len([node for node in self.nodes if node.kind == 'spring']) != 1:
            raise ValueError('sample requires exactly one explicit sink/spring pair')
        underground = [arc for arc in self.arcs if arc.kind == 'underground']
        if len(underground) != 1:
            raise ValueError('sample requires one underground route')
        types = {node.node_id: node.kind for node in self.nodes}
        if tuple((types[key] for key in underground[0].node_ids)) != ('sink', 'spring'):
            raise ValueError('underground route must bind sink to spring')
        attachments = [arc for arc in self.arcs if arc.kind == 'portal_attachment']
        attachment_types = [tuple((types[key] for key in arc.node_ids)) for arc in attachments]
        if sorted(attachment_types) != sorted([('surface', 'sink'), ('spring', 'surface')]):
            raise ValueError('route requires explicit actual surface-to-portal half-arm attachments')
        if any((key not in arc_ids for key in self.bypass_arc_ids)):
            raise ValueError('bypass provenance is missing')

    def to_record(self):
        record = {'schema': HYBRID_RIVER_GRAPH_SCHEMA, 'coordinates': 'XYZ metres; Y elevation; XZ horizontal', 'nodes': [_i7_asdict(node) for node in self.nodes], 'arcs': [_i7_asdict(arc) for arc in self.arcs], 'inputs': {key: _i7_asdict(pin) for key, pin in self.inputs}, 'bypass_arc_ids': list(self.bypass_arc_ids), 'hydraulic_state_included': False, 'natural_outlet_certified': False, 'full_network_verified': False, 'surface_supply_active': False}
        record['identity_sha256'] = identity(record)
        return _i7_json.loads(canonical_json(record))

# Source: terrain_pipeline.hybrid_river_graph
def native_bed_pieces(port):
    pieces = []
    for segment in port['profile']['profile_segments']:
        for native in segment['native_pieces']:
            source = native['source']['source_coefficients_m_t012']
            cut = native['depth_coefficients_m_t01']
            if min(cut[0], cut[0] + cut[1]) < 0 or max(cut[0], cut[0] + cut[1]) > 4:
                raise ValueError('native profile violates strict cut limits')
            start, end = (native['start_xz_m'], native['end_xz_m'])
            pieces.append({'width_m': _i7_math.dist(start, end), 'bed_coefficients_m_t012': [source[0] - cut[0], source[1] - cut[1], source[2]]})
    if len(port['profile']['profile_segments']) != 3 or not pieces:
        raise ValueError('incomplete canonical native profile')
    return pieces

# Source: terrain_pipeline.hybrid_river_graph
def port_floor_xyz(port):
    segment = port['profile']['profile_segments'][1]
    for piece in segment['native_pieces']:
        lower, upper = piece['interval_t01']
        if lower <= 0.5 <= upper:
            fraction = (0.5 - lower) / (upper - lower)
            source = piece['source']['source_coefficients_m_t012']
            cut = piece['depth_coefficients_m_t01']
            bed = source[0] + source[1] * fraction + source[2] * fraction ** 2 - cut[0] - cut[1] * fraction
            return (port['midpoint_xz_m'][0], bed, port['midpoint_xz_m'][1])
    raise ValueError('port midpoint is unsupported')

# Source: terrain_pipeline.hybrid_river_graph
def attachment_evidence(saved_node, port, node_witness, port_witness):
    if saved_node['identity_sha256'] != node_witness['identity_sha256'] or saved_node['status'] != 'candidate':
        raise ValueError('attachment is not an audited accepted surface node')
    key = port['arc_id']
    arms = [arm for arm in saved_node['arms'] if arm['arc_id'] == key]
    proofs = [proof for proof in saved_node['port_proofs'] if proof.get('arc_id') == key]
    if len(arms) != 1 or len(proofs) != 1 or arms[0]['midpoint_port_identity_sha256'] != port['identity_sha256']:
        raise ValueError('attachment lacks a unique actual canonical half arm')
    proof = proofs[0]
    if proof['midpoint_port_identity_sha256'] != port['identity_sha256'] or sorted((segment['profile_segment_index'] for segment in proof['segments'])) != [0, 1, 2]:
        raise ValueError('attachment omitted full three-segment canonical boundary')
    geometry = saved_node['geometry']
    triangle_indices = [ordinal for ordinal, role in enumerate(geometry['triangle_roles']) if role.get('region') == 'half_arm' and role.get('arc_id') == key]
    ring_indices = [ordinal for ordinal, role in enumerate(geometry['triangle_roles']) if role.get('region') == 'node_ring']
    if not triangle_indices or not ring_indices or any((not segment['pieces'] for segment in proof['segments'])):
        raise ValueError('attachment has no actual half-arm triangle/native edge evidence')
    for segment in proof['segments']:
        for piece in segment['pieces']:
            if piece['side']['triangle_index'] not in triangle_indices:
                raise ValueError('canonical port side is not on the actual half arm')
    return canonical_json({'surface_node_pin': node_witness, 'canonical_port_pin': port_witness, 'half_arm_triangle_indices': triangle_indices, 'node_ring_triangle_indices': ring_indices, 'actual_complete_port_proof': proof, 'surface_node_record': saved_node, 'hydraulic_boundary_certified': False})

# Source: terrain_pipeline.hybrid_river_graph
def build_graph(surface_graph, manifest, topology, audit, ports, inputs, sink_arc_id, spring_arc_id, saved_nodes):
    if audit['status'] != 'passed' or not audit['complete_actual_reverse_midpoint_functions_verified']:
        raise ValueError('surface audit has not verified actual complete port functions')
    if sink_arc_id == spring_arc_id:
        raise ValueError('sink and spring cannot share one midpoint')
    selected = set(manifest['selected_node_ids'])
    joined = set(topology['joined_arc_ids'])
    if selected != set(audit['selected_node_ids']):
        raise ValueError('surface selection differs from passed audit')
    if any((key not in joined or key not in audit['ports'] for key in (sink_arc_id, spring_arc_id))):
        raise ValueError('sink/spring require audited actual joined midpoint ports')
    source_nodes = {node['node_id']: node for node in surface_graph['nodes']}
    source_arcs = {arc['arc_id']: arc for arc in surface_graph['arcs']}
    if not joined <= set(source_arcs) or not selected <= set(source_nodes):
        raise ValueError('accepted surface provenance missing')
    sink_arc, spring_arc = (source_arcs[sink_arc_id], source_arcs[spring_arc_id])
    outgoing = {}
    for key in joined:
        arc = source_arcs[key]
        if not set(arc['node_ids']) <= selected:
            raise ValueError('accepted arc references unselected node')
        outgoing.setdefault(arc['node_ids'][0], []).append(key)
    start, target = (sink_arc['node_ids'][1], spring_arc['node_ids'][0])
    queue = [(start, ())]
    visited = set()
    route = None
    while queue:
        current, path = queue.pop(0)
        if current == target:
            route = path
            break
        if current in visited:
            continue
        visited.add(current)
        for key in sorted(outgoing.get(current, ())):
            queue.append((source_arcs[key]['node_ids'][1], path + (key,)))
    if route is None:
        raise ValueError('ports do not lie on a directed accepted surface bypass')
    nodes = []
    for key in sorted(selected):
        original = source_nodes[key]
        saved = saved_nodes[key]
        if saved['identity_sha256'] != audit['nodes'][key]['identity_sha256']:
            raise ValueError('saved surface bed differs from actual audited node')
        source_xyz = tuple(saved['source_xyz_m'])
        if source_xyz != tuple(original['xyz_m']) or not 0 <= saved['center_depth_m'] <= 4:
            raise ValueError('surface source/derived bed coordinates differ from original evidence')
        bed_xyz = (source_xyz[0], source_xyz[1] - saved['center_depth_m'], source_xyz[2])
        nodes.append(RiverNode(key, 'surface', tuple(original['xyz_m']), canonical_json(original), source_xyz_m=source_xyz, bed_xyz_m=bed_xyz))
    for kind, key in (('sink', sink_arc_id), ('spring', spring_arc_id)):
        port = ports[key]
        witness = audit['ports'][key]
        if witness['identity_sha256'] != port['identity_sha256']:
            raise ValueError('canonical port identity differs from audit')
        if port.get('rejection_reasons') or port['upstream_parent_section'].get('anchor'):
            raise ValueError('rejected or anchor midpoint cannot be an engineered portal')
        native_bed_pieces(port)
        nodes.append(RiverNode('engineered:' + kind, kind, port_floor_xyz(port), canonical_json(port), key, bed_xyz_m=port_floor_xyz(port)))
    arcs = [RiverArc(key, 'surface', tuple(source_arcs[key]['node_ids']), 'context_only', canonical_json(source_arcs[key])) for key in sorted(joined)]
    arcs.append(RiverArc('engineered:underground', 'underground', ('engineered:sink', 'engineered:spring'), 'sample_route', canonical_json({'engineering_selection': True})))
    for kind, key, surface_node_id in (('sink', sink_arc_id, sink_arc['node_ids'][0]), ('spring', spring_arc_id, spring_arc['node_ids'][1])):
        evidence = attachment_evidence(saved_nodes[surface_node_id], ports[key], audit['nodes'][surface_node_id], audit['ports'][key])
        endpoints = (surface_node_id, 'engineered:sink') if kind == 'sink' else ('engineered:spring', surface_node_id)
        arcs.append(RiverArc('engineered:' + kind + ':half_arm_attachment', 'portal_attachment', endpoints, 'sample_route', evidence))
    return HybridRiverGraph(tuple(nodes), tuple(arcs), tuple(sorted(inputs.items())), (sink_arc_id,) + route + (spring_arc_id,))

# Source: terrain_pipeline.hybrid_river_graph
def load_graph(record):
    unsigned = dict(record)
    expected = unsigned.pop('identity_sha256')
    if record['schema'] != HYBRID_RIVER_GRAPH_SCHEMA or identity(unsigned) != expected:
        raise ValueError('hybrid graph schema/identity mismatch')
    nodes = tuple((RiverNode(**{**node, 'xyz_m': tuple(node['xyz_m']), 'source_xyz_m': tuple(node['source_xyz_m']) if node['source_xyz_m'] is not None else None, 'bed_xyz_m': tuple(node['bed_xyz_m']) if node['bed_xyz_m'] is not None else None}) for node in record['nodes']))
    arcs = tuple((RiverArc(**{**arc, 'node_ids': tuple(arc['node_ids'])}) for arc in record['arcs']))
    graph = HybridRiverGraph(nodes, arcs, tuple(sorted(((key, FilePin(**pin)) for key, pin in record['inputs'].items()))), tuple(record['bypass_arc_ids']))
    if graph.to_record() != record:
        raise ValueError('graph fields do not match immutable contract')
    return graph

# Source: terrain_pipeline.hybrid_geometry_common
MAX_BYTES = 64 * 1024 ** 2

# Source: terrain_pipeline.hybrid_geometry_common
MAX_RSS = 1024 ** 3

# Source: terrain_pipeline.hybrid_geometry_common
TOLERANCE_M = 1e-08

# Source: terrain_pipeline.hybrid_geometry_common
AREA_TOLERANCE_M2 = 1e-08

# Source: terrain_pipeline.hybrid_geometry_common
MAX_TRIANGLES = 200000

# Source: terrain_pipeline.hybrid_geometry_common
def seal(record):
    record.pop('identity_sha256', None)
    record['identity_sha256'] = identity(record)
    return record

# Source: terrain_pipeline.hybrid_geometry_common
def guard():
    memory = _i0_psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, 'peak_wset', 0))
    if peak > MAX_RSS:
        raise MemoryError('whole_face_package_1GiB_budget_exceeded')
    return peak

# Source: terrain_pipeline.hybrid_geometry_common
def plane_frame(origin_world, flow_xz, common_origin):
    origin_world, common_origin = (_i0_np.asarray(origin_world, float), _i0_np.asarray(common_origin, float))
    flow = _i0_np.asarray(flow_xz, float)
    if origin_world.shape != (3,) or common_origin.shape != (3,) or flow.shape != (2,) or (not all((_i0_np.isfinite(value).all() for value in (origin_world, common_origin, flow)))) or (_i0_np.linalg.norm(flow) <= TOLERANCE_M):
        raise ValueError('unknown_or_invalid_face_plane')
    flow /= _i0_np.linalg.norm(flow)
    normal = _i0_np.array([flow[0], 0.0, flow[1]])
    transverse = _i0_np.array([flow[1], 0.0, -flow[0]])
    return {'origin_world_xyz_m': origin_world.tolist(), 'origin_local_xyz_m': (origin_world - common_origin).tolist(), 'common_local_origin_xyz_m': common_origin.tolist(), 'normal_local_xyz': normal.tolist(), 'transverse_unit_xyz': transverse.tolist(), 'transverse_unit_xz': transverse[[0, 2]].tolist(), 'vertical_unit_xyz': [0.0, 1.0, 0.0], 'coordinate_convention': 'u_metres_Ylocal_metres_not_floor_relative', 'positive_normal': 'from_cell_to_cell_actual_horizontal_route'}

# Source: terrain_pipeline.hybrid_geometry_common
def project(vertices_local, frame):
    points = _i0_np.asarray(vertices_local, float)
    relative = points - _i0_np.array(frame['origin_local_xyz_m'])
    return _i0_np.column_stack((relative @ _i0_np.array(frame['transverse_unit_xyz']), points[:, 1]))

# Source: terrain_pipeline.hybrid_geometry_common
def unproject(points_uv, frame):
    points = _i0_np.asarray(points_uv, float)
    origin = _i0_np.array(frame['origin_local_xyz_m'])
    result = origin + points[:, :1] * _i0_np.array(frame['transverse_unit_xyz'])
    result[:, 1] = points[:, 1]
    return result

# Source: terrain_pipeline.hybrid_geometry_common
def solid_from_mesh(record, common_origin):
    import manifold3d as manifold
    points = _i0_np.array(record['vertices_local_xyz_m'], dtype=_i0_np.float64, order='C', copy=True)
    triangles = _i0_np.array(record['triangles'], dtype=_i0_np.uint64, order='C', copy=True)
    if points.ndim != 2 or points.shape[1] != 3 or (not _i0_np.isfinite(points).all()) or (triangles.ndim != 2) or (triangles.shape[1] != 3) or (not 0 < len(triangles) <= MAX_TRIANGLES) or (triangles.max() >= len(points)):
        raise ValueError('invalid_or_unbounded_saved_solid_mesh')
    origin = _i0_np.asarray(record['local_origin_xyz_m'], float)
    if origin.shape != (3,) or not _i0_np.isfinite(origin).all():
        raise ValueError('invalid_saved_solid_origin')
    points += origin - common_origin
    solid = manifold.Manifold(manifold.Mesh64(points, triangles))
    if solid.status() != manifold.Error.NoError or solid.is_empty() or solid.volume() <= 0:
        raise ValueError('saved_solid_not_positive_closed_manifold')
    return (solid, points, triangles)

# Source: terrain_pipeline.hybrid_geometry_common
def support_indices(line, slice_record):
    result = {item['triangle_index'] for item in slice_record['triangle_segments'] if _i0_LineString(item['points_uv_m']).distance(line) <= TOLERANCE_M and _i0_LineString(item['points_uv_m']).intersection(line.buffer(TOLERANCE_M)).length > TOLERANCE_M}
    result.update((item['triangle_index'] for item in slice_record['coplanar_triangle_supports'] if _i0_Polygon(item['polygon_uv_m']).distance(line) <= TOLERANCE_M))
    return sorted(result)

# Source: terrain_pipeline.hybrid_geometry_common
def canonical_floor(port, frame):
    floor = []
    if port['status'] != 'candidate' or port['rejection_reasons']:
        raise ValueError('unknown_refused_canonical_port')
    for segment in port['profile']['profile_segments']:
        for piece in segment['native_pieces']:
            coefficients = piece['source']['source_coefficients_m_t012']
            cut = piece['depth_coefficients_m_t01']
            if coefficients[2] != 0.0 or min(cut[0], cut[0] + cut[1]) < 0 or max(cut[0], cut[0] + cut[1]) > 4:
                raise ValueError('unknown_unsupported_canonical_native_function')
            for fraction, point in ((0.0, piece['start_xz_m']), (1.0, piece['end_xz_m'])):
                world = _i0_np.array([point[0], coefficients[0] + fraction * coefficients[1] - cut[0] - fraction * cut[1], point[1]])
                local = world - _i0_np.array(frame['common_local_origin_xyz_m'])
                if abs(float((local - frame['origin_local_xyz_m']) @ frame['normal_local_xyz'])) > TOLERANCE_M:
                    raise ValueError('canonical_floor_not_in_shared_plane')
                uv = project([local], frame)[0].tolist()
                if not floor or _i0_math.dist(uv, floor[-1]) > TOLERANCE_M:
                    floor.append(uv)
    floor.sort(key=lambda point: point[0])
    if len(floor) < 4:
        raise ValueError('incomplete_canonical_four_point_profile')
    return floor

# Source: terrain_pipeline.hybrid_cave_geometry
SCHEMA = 'td-hybrid-river-geometry-v1'

# Source: terrain_pipeline.hybrid_cave_geometry
MAX_GRID = 300000

# Source: terrain_pipeline.hybrid_cave_geometry
POLICY = {'version': 'local-rock-boolean-multichart-v1', 'terrain': 'original_native_bilinear_minus_independently_passed_saved_affine_cut_fans', 'solid': 'sampled_piecewise_planar_top_closed_sides_bottom_not_native_exact_not_fine_replacement', 'excavation': 'Mesh64_local_origin_closed_rock_minus_closed_derived_cutter_actual_volume', 'geology': 'generated_hermite_route_sine_squared_burial_not_surveyed', 'portals': 'immutable_complete_native_floor_with_engineered_ceiling_surface_ramp_openings', 'vdm': 'new_transverse_and_vertical_multichart_reference_plus_displacement_not_old_metric_vdm', 'water': 'not_generated_solid_banks_distinct_from_free_water', 'protection': 'unknown_protected_unselected_or_wet_native_support_refused_without_clamping', 'hydraulics': 'final_actual_ring_storage_sections_engineering_pressure_slot_no_solver'}

# Source: terrain_pipeline.hybrid_cave_geometry
POLICY_SHA256 = identity(POLICY)

# Source: terrain_pipeline.hybrid_cave_geometry
@_i1_dataclass(frozen=True)
class Parameters:
    rock_spacing_m: float = 1.0
    stations: int = 17
    burial_m: float = 6.0
    ceiling_clearance_m: float = 2.0
    crop_margin_m: float = 8.0
    bottom_margin_m: float = 5.0
    vdm_amplitude_m: float = 0.12
    roughness_manning: float = 0.035
    pressure_slot_width_m: float = 0.02

    def __post_init__(self):
        if not all((_i1_math.isfinite(value) and value > 0 for key, value in _i1_asdict(self).items() if key != 'stations')):
            raise ValueError('positive finite explicit engineering parameters required')
        if not 0.175 <= self.rock_spacing_m <= 2.0 or type(self.stations) is not int or (not 9 <= self.stations <= 33):
            raise ValueError('bounded rock resolution/stations required')
        if self.burial_m > 30 or self.ceiling_clearance_m > 8 or self.crop_margin_m > 30:
            raise ValueError('local engineering geometry bounds exceeded')

# Source: terrain_pipeline.hybrid_cave_geometry
def hybrid_cave_geometry_guard():
    memory = _i1_psutil.Process().memory_info()
    if max(memory.rss, getattr(memory, 'peak_wset', 0)) > MAX_RSS:
        raise MemoryError('whole_geometry_1GiB_budget_exceeded')
    return max(memory.rss, getattr(memory, 'peak_wset', 0))

# Source: terrain_pipeline.hybrid_cave_geometry
class BedSampler:

    def __init__(self, context, fans):
        self.context = context
        self.fans = fans
        self.bins = {}
        for ordinal, fan in enumerate(fans):
            vertices = _i1_np.asarray(fan['vertices_xz_m'])
            low, high = (_i1_np.floor(vertices.min(axis=0) / 10).astype(int), _i1_np.floor(vertices.max(axis=0) / 10).astype(int))
            for column in range(low[0], high[0] + 1):
                for row in range(low[1], high[1] + 1):
                    self.bins.setdefault((column, row), []).append(ordinal)

    def __call__(self, point):
        point = _i1_np.asarray(point, float)
        sample = _i1_source._source_sample(self.context, *point)
        if sample['rejection_reasons'] or sample['height_m'] is None or sample['wet_source_support']:
            raise ValueError('source_gate:' + ','.join(sample['rejection_reasons'] or ['wet_native_support']) + ':' + str(point.tolist()))
        cuts, keys = ([], [])
        for ordinal in self.bins.get(tuple(_i1_np.floor(point / 10).astype(int)), []):
            fan = self.fans[ordinal]
            cut = _i1__center_cut(fan, point)
            if cut is not None:
                cuts.append(cut)
                keys.append(fan['fan_key'])
        if cuts and max(cuts) - min(cuts) > 1e-09:
            raise ValueError('saved_fan_shared_function_mismatch')
        cut = cuts[0] if cuts else 0.0
        return {'source_sample': sample, 'cut_depth_m': cut, 'fan_keys': keys, 'derived_bed_m': sample['height_m'] - cut}

# Source: terrain_pipeline.hybrid_cave_geometry
def portal_knots(port):
    if port['status'] != 'candidate' or port['rejection_reasons']:
        raise ValueError('refused actual canonical profile')
    native_bed_pieces(port)
    values = {0.0, 1.0, 2.0, 3.0}
    for ordinal, segment in enumerate(port['profile']['profile_segments']):
        for piece in segment['native_pieces']:
            if piece['source']['source_coefficients_m_t012'][2] != 0.0:
                raise ValueError('quadratic_portal_floor_requires_new_exact_interface')
            values.update((ordinal + bound for bound in piece['interval_t01']))
    return values

# Source: terrain_pipeline.hybrid_cave_geometry
def portal_point(port, parameter):
    original = port['profile']['profile_xyz_m']
    if parameter in (0.0, 1.0, 2.0, 3.0):
        return _i1_np.array(original[int(parameter)], float)
    ordinal = min(int(parameter), 2)
    fraction = parameter - ordinal
    segment = port['profile']['profile_segments'][ordinal]
    for piece in segment['native_pieces']:
        lower, upper = piece['interval_t01']
        if lower <= fraction <= upper:
            local = (fraction - lower) / (upper - lower)
            if fraction == lower:
                point = _i1_np.array(piece['start_xz_m'], float)
            elif fraction == upper:
                point = _i1_np.array(piece['end_xz_m'], float)
            else:
                point = (1.0 - local) * _i1_np.array(piece['start_xz_m']) + local * _i1_np.array(piece['end_xz_m'])
            coefficients = piece['source']['source_coefficients_m_t012']
            cut = piece['depth_coefficients_m_t01']
            depth = cut[0] if local == 0 else cut[0] + cut[1] if local == 1 else (1.0 - local) * cut[0] + local * (cut[0] + cut[1])
            if not 0 <= depth <= 4:
                raise ValueError('strict_negative_or_maxcut_portal_depth')
            height = coefficients[0] + coefficients[1] * local + coefficients[2] * local ** 2 - depth
            return _i1_np.array([point[0], height, point[1]])
    raise ValueError('canonical_native_profile_gap')

# Source: terrain_pipeline.hybrid_cave_geometry
def build_charts(sink, spring, sink_xyz, spring_xyz, parameters):
    knots = sorted(portal_knots(sink) | portal_knots(spring))
    floor_ends = [_i1_np.array([portal_point(port, value) for value in knots]) for port in (sink, spring)]
    origins = _i1_np.array([sink_xyz, spring_xyz], float)
    distance = float(_i1_np.linalg.norm((origins[1] - origins[0])[[0, 2]]))
    if not 30 <= distance <= 400:
        raise ValueError('explicit_pair_outside_bounded_route_length')
    directions = _i1_np.array([sink['flow_unit_xz'], spring['flow_unit_xz']])
    tangent_scale = min(distance * 0.6, 60.0)
    stations = []
    for ordinal, fraction in enumerate(_i1_np.linspace(0.0, 1.0, parameters.stations)):
        complement = 1.0 - fraction
        horizontal = (2 * fraction ** 3 - 3 * fraction ** 2 + 1) * origins[0, [0, 2]] + (-2 * fraction ** 3 + 3 * fraction ** 2) * origins[1, [0, 2]] + (fraction ** 3 - 2 * fraction ** 2 + fraction) * tangent_scale * directions[0] + (fraction ** 3 - fraction ** 2) * tangent_scale * directions[1]
        tangent = (6 * fraction ** 2 - 6 * fraction) * origins[0, [0, 2]] + (-6 * fraction ** 2 + 6 * fraction) * origins[1, [0, 2]] + (3 * fraction ** 2 - 4 * fraction + 1) * tangent_scale * directions[0] + (3 * fraction ** 2 - 2 * fraction) * tangent_scale * directions[1]
        tangent /= _i1_np.linalg.norm(tangent)
        transverse = _i1_np.array([-tangent[1], tangent[0]])
        burial = parameters.burial_m * _i1_math.sin(_i1_math.pi * fraction) ** 2 if ordinal not in (0, parameters.stations - 1) else 0.0
        origin = _i1_np.array([horizontal[0], complement * origins[0, 1] + fraction * origins[1, 1] - burial, horizontal[1]])
        floor = []
        for first, second in zip(*floor_ends):
            offset_first = (first[[0, 2]] - origins[0, [0, 2]]) @ _i1_np.array([-directions[0, 1], directions[0, 0]])
            offset_second = (second[[0, 2]] - origins[1, [0, 2]]) @ _i1_np.array([-directions[1, 1], directions[1, 0]])
            offset = complement * offset_first + fraction * offset_second
            point = _i1_np.array([horizontal[0] + offset * transverse[0], complement * first[1] + fraction * second[1] - burial, horizontal[1] + offset * transverse[1]])
            floor.append(point)
        floor = _i1_np.array(floor)
        if ordinal == 0:
            floor = floor_ends[0].copy()
            origin = origins[0].copy()
            transverse = _i1_np.array([-directions[0, 1], directions[0, 0]])
        elif ordinal == parameters.stations - 1:
            floor = floor_ends[1].copy()
            origin = origins[1].copy()
            transverse = _i1_np.array([-directions[1, 1], directions[1, 0]])
        roof_y = float(floor[:, 1].max() + parameters.ceiling_clearance_m)
        roof_first, roof_last = (floor[0].copy(), floor[-1].copy())
        roof_first[1] = roof_last[1] = roof_y
        reference = _i1_np.vstack((floor, roof_last, roof_first))
        displacement = _i1_np.zeros_like(reference)
        if ordinal not in (0, parameters.stations - 1):
            amplitude = parameters.vdm_amplitude_m * _i1_math.sin(_i1_math.pi * fraction) ** 2
            displacement[-2, [0, 2]] = amplitude * transverse
            displacement[-1, [0, 2]] = -amplitude * transverse
            displacement[-2:, 1] = amplitude * _i1_math.cos(4 * _i1_math.pi * fraction)
        derived = reference + displacement
        stations.append({'station_id': 'gallery:' + str(ordinal), 'fraction': float(fraction), 'origin_xyz_m': origin.tolist(), 'transverse_unit_xz': transverse.tolist(), 'reference_ring_xyz_m': reference.tolist(), 'displacement_ring_xyz_m': displacement.tolist(), 'derived_ring_xyz_m': derived.tolist(), 'floor_vertex_count': len(knots)})
    triangles = sweep_triangles(stations)
    horizontal_rings = [_i1_np.array(station['derived_ring_xyz_m'])[:, [0, 2]] for station in stations]
    swept_bounds = [(_i1_np.vstack((first, second)).min(axis=0), _i1_np.vstack((first, second)).max(axis=0)) for first, second in zip(horizontal_rings, horizontal_rings[1:])]
    for first_index, (first_low, first_high) in enumerate(swept_bounds):
        for second_low, second_high in swept_bounds[first_index + 2:]:
            if _i1_np.all(_i1_np.minimum(first_high, second_high) - _i1_np.maximum(first_low, second_low) > 1e-08):
                raise ValueError('nonadjacent_sweep_projection_overlap_not_certified')
    local_vertices = _i1_np.array([station['derived_ring_xyz_m'] for station in stations]).reshape(-1, 3) - origins[0]
    if signed_volume(local_vertices, triangles) < 0:
        triangles = [triangle[::-1] for triangle in triangles]
    return seal({'schema': 'td-hybrid-multichart-vdm-v1', 'stations': stations, 'triangles': triangles, 'profile_parameters': knots, 'immutable_portal_station_ids': [stations[0]['station_id'], stations[-1]['station_id']], 'old_fixed_chart_vdm_accepted': False, 'reference_rule': 'generated_baseline_conduit_chart_bound_to_original_port_profiles_not_original_TD_surface', 'displacement_rule': 'zero_floor_and_portals_variable_ceiling_transverse_and_vertical_sine'})

# Source: terrain_pipeline.hybrid_cave_geometry
def sweep_triangles(stations):
    import manifold3d as manifold
    count = len(stations[0]['derived_ring_xyz_m'])
    triangles = []
    for ordinal in range(len(stations) - 1):
        for offset in range(count):
            following = (offset + 1) % count
            first, second = (ordinal * count + offset, ordinal * count + following)
            third, fourth = (first + count, second + count)
            triangles.extend(([first, second, fourth], [first, fourth, third]))
    for ordinal, reverse in ((0, True), (len(stations) - 1, False)):
        station = stations[ordinal]
        vertices = _i1_np.asarray(station['derived_ring_xyz_m'])
        origin = _i1_np.asarray(station['origin_xyz_m'])
        transverse = _i1_np.asarray(station['transverse_unit_xz'])
        polygon = _i1_np.column_stack(((vertices[:, [0, 2]] - origin[[0, 2]]) @ transverse, vertices[:, 1] - origin[1]))
        for triangle in manifold.triangulate([polygon], allow_convex=False):
            indices = [int(value) + ordinal * count for value in triangle]
            triangles.append(indices[::-1] if reverse else indices)
    return triangles

# Source: terrain_pipeline.hybrid_cave_geometry
def signed_volume(vertices, triangles):
    points = _i1_np.asarray(vertices, float)[_i1_np.asarray(triangles, int)]
    return float(_i1_np.einsum('ij,ij->i', points[:, 0], _i1_np.cross(points[:, 1], points[:, 2])).sum() / 6.0)

# Source: terrain_pipeline.hybrid_cave_geometry
def mesh_record(vertices, triangles, origin, role):
    vertices = _i1_np.asarray(vertices, float)
    triangles = _i1_np.asarray(triangles, int)
    if not _i1_np.isfinite(vertices).all() or vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError('invalid solid vertices')
    if signed_volume(vertices, triangles) < 0:
        triangles = triangles[:, ::-1]
    uses = {}
    for triangle in triangles:
        if len(set(triangle)) != 3 or min(triangle) < 0 or max(triangle) >= len(vertices):
            raise ValueError('invalid_solid_triangle')
        for first, second in zip(triangle, _i1_np.roll(triangle, -1)):
            uses.setdefault(tuple(sorted((int(first), int(second)))), []).append((int(first), int(second)))
    if any((len(sides) != 2 or sides[0] != sides[1][::-1] for sides in uses.values())):
        raise ValueError('solid_is_not_closed_reverse_two_use_manifold')
    return seal({'schema': 'td-hybrid-local-solid-mesh-v1', 'role': role, 'local_origin_xyz_m': list(origin), 'vertices_local_xyz_m': vertices.tolist(), 'triangles': triangles.tolist(), 'signed_volume_m3': signed_volume(vertices, triangles), 'sampled_not_native_exact': True})

# Source: terrain_pipeline.hybrid_cave_geometry
def manifold_from_record(record):
    import manifold3d as manifold
    solid = manifold.Manifold(manifold.Mesh64(_i1_np.array(record['vertices_local_xyz_m'], dtype=_i1_np.float64, order='C', copy=True), _i1_np.array(record['triangles'], dtype=_i1_np.uint64, order='C', copy=True)))
    if solid.status() != manifold.Error.NoError or solid.is_empty():
        raise ValueError('invalid_closed_manifold:' + str(solid.status()))
    if solid.volume() <= 0:
        raise ValueError('nonpositive_solid_volume')
    return solid

# Source: terrain_pipeline.hybrid_cave_geometry
def save_manifold(solid, origin, role):
    mesh = solid.to_mesh64()
    return mesh_record(_i1_np.array(mesh.vert_properties[:, :3], copy=True), _i1_np.array(mesh.tri_verts, copy=True), origin, role)

# Source: terrain_pipeline.hybrid_cave_geometry
def build_rock(vdm, sampler, parameters, origin):
    rings = _i1_np.array([station['derived_ring_xyz_m'] for station in vdm['stations']])
    low = _i1_np.floor((rings[:, :, [0, 2]].min(axis=(0, 1)) - parameters.crop_margin_m) / parameters.rock_spacing_m) * parameters.rock_spacing_m
    high = _i1_np.ceil((rings[:, :, [0, 2]].max(axis=(0, 1)) + parameters.crop_margin_m) / parameters.rock_spacing_m) * parameters.rock_spacing_m
    counts = _i1_np.rint((high - low) / parameters.rock_spacing_m).astype(int) + 1
    columns, rows = map(int, counts)
    if columns * rows > MAX_GRID:
        raise ValueError('whole_rock_grid_budget_exceeded_no_crop_truncation')
    bottom = float(rings[:, :, 1].min() - parameters.bottom_margin_m)
    vertices, samples = ([], [])
    for row in range(rows):
        for column in range(columns):
            point = low + _i1_np.array([column, row]) * parameters.rock_spacing_m
            result = sampler(point)
            samples.append({'row': row, 'column': column, 'xz_m': point.tolist(), **result})
            if result['derived_bed_m'] <= bottom:
                raise ValueError('rock_bottom_above_sampled_top')
            vertices.append([point[0] - origin[0], result['derived_bed_m'] - origin[1], point[1] - origin[2]])
        if row % 16 == 0:
            hybrid_cave_geometry_guard()
    triangles = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            first = row * columns + column
            triangles.extend(([first, first + columns, first + columns + 1], [first, first + columns + 1, first + 1]))
    perimeter = list(range(columns)) + [row * columns + columns - 1 for row in range(1, rows)]
    perimeter += list(range((rows - 1) * columns + columns - 2, (rows - 1) * columns - 1, -1))
    perimeter += [row * columns for row in range(rows - 2, 0, -1)]
    bottom_ids = []
    for index in perimeter:
        bottom_ids.append(len(vertices))
        point = vertices[index]
        vertices.append([point[0], bottom - origin[1], point[2]])
    for ordinal in range(len(perimeter)):
        following = (ordinal + 1) % len(perimeter)
        first, second = (perimeter[ordinal], perimeter[following])
        third, fourth = (bottom_ids[ordinal], bottom_ids[following])
        triangles.extend(([first, second, fourth], [first, fourth, third]))
    center_id = len(vertices)
    vertices.append([(low[0] + high[0]) / 2 - origin[0], bottom - origin[1], (low[1] + high[1]) / 2 - origin[2]])
    for first, second in zip(bottom_ids, bottom_ids[1:] + bottom_ids[:1]):
        triangles.append([center_id, first, second])
    record = mesh_record(vertices, triangles, origin, 'rock_before')
    sampling = seal({'schema': 'td-hybrid-rock-source-sampling-v1', 'origin_xz_m': low.tolist(), 'spacing_m': parameters.rock_spacing_m, 'rows': rows, 'columns': columns, 'top_vertex_count': rows * columns, 'bottom_elevation_m': bottom, 'samples': samples, 'native_exact': False, 'fine15_replaced': False})
    return (record, sampling)

# Source: terrain_pipeline.hybrid_cave_geometry
def ray_hits(solid, first, second, origin):
    hits = solid.ray_cast(tuple(_i1_np.array(first) - origin), tuple(_i1_np.array(second) - origin))
    return [{'face_id': int(hit.face_id), 'distance': float(hit.distance), 'position_xyz_m': (_i1_np.array(hit.position) + origin).tolist()} for hit in hits]

# Source: terrain_pipeline.hybrid_cave_geometry
def closed_rock_section(containment):
    covered = all((item['actual_sampled_top_cover_m'] is not None and item['actual_sampled_top_cover_m'] > 0.0 for item in containment))
    roof_cover = min((item['actual_sampled_top_cover_m'] if item['actual_sampled_top_cover_m'] is not None else -_i1_math.inf for item in containment[-2:]))
    return bool(covered and roof_cover >= 0.5)

# Source: terrain_pipeline.hybrid_cave_geometry
def void_witnesses(before, after, removed, vdm, origin, sampler):
    stations = vdm['stations']
    path = []
    for station in stations:
        ring = _i1_np.asarray(station['derived_ring_xyz_m'])
        count = station['floor_vertex_count']
        transverse = _i1_np.array(station['transverse_unit_xz'])
        point = _i1_np.array(station['origin_xyz_m'])
        floor = ring[:count]
        offsets = (floor[:, [0, 2]] - point[[0, 2]]) @ transverse
        point[1] = float(_i1_np.interp(0.0, offsets, floor[:, 1]) + 0.35)
        if point[1] >= ring[-2:, 1].min():
            raise ValueError('no_positive_portal_air_clearance')
        path.append(point.tolist())
    segments = []
    for first, second in zip(path, path[1:]):
        hits = ray_hits(after, first, second, origin)
        if hits:
            raise ValueError('actual_rock_blocks_continuous_air_path')
        segments.append({'from_xyz_m': first, 'to_xyz_m': second, 'rock_after_hits': hits})
    openings = {}
    for kind, indices in (('sink', range(1, len(path) // 2)), ('spring', range(len(path) - 2, len(path) // 2, -1))):
        witness = None
        for ordinal in indices:
            inside = path[ordinal]
            terrain = sampler(_i1_np.array(inside)[[0, 2]])
            if inside[1] >= terrain['derived_bed_m'] - 0.05:
                continue
            above = [inside[0], terrain['derived_bed_m'] + 3.0, inside[2]]
            old_hits = ray_hits(before, above, inside, origin)
            new_hits = ray_hits(after, above, inside, origin)
            if old_hits and (not new_hits):
                witness = {'station_id': stations[ordinal]['station_id'], 'above_xyz_m': above, 'inside_xyz_m': inside, 'rock_before_hits': old_hits, 'rock_after_hits': new_hits, 'source_bed_witness': terrain, 'opening_kind': 'actual_terrain_top_ramp_aperture_not_entire_planar_port_cap'}
                break
        if witness is None:
            raise ValueError('actual_' + kind + '_terrain_opening_not_verified')
        openings[kind] = witness
    if len(removed.decompose()) != 1:
        raise ValueError('excavated_cavity_not_one_connected_solid')
    return (path, segments, openings)

# Source: terrain_pipeline.hybrid_cave_geometry
def cell_record(station, region, arc_id, length, parameters, reference, *, closed_rock=False):
    ring = _i1_np.array(station['derived_ring_xyz_m'])
    if region == 'underground' and (not closed_rock):
        ring = ring[:station['floor_vertex_count']]
    origin = _i1_np.array(station['origin_xyz_m'])
    transverse = _i1_np.array(station['transverse_unit_xz'])
    shape = _i1_np.column_stack(((ring[:, [0, 2]] - origin[[0, 2]]) @ transverse, ring[:, 1])).tolist()
    underground = region == 'underground' and closed_rock
    section = {'kind': 'closed_polygon', 'polygon_transverse_elevation_m': shape, 'pressure_slot_width_m': parameters.pressure_slot_width_m} if underground else {'kind': 'open_polyline', 'polyline_transverse_elevation_m': shape, 'sidewall_extension': 'explicit_engineering_vertical'}
    return {'cell_id': station['station_id'], 'kind': 'underground' if underground else 'surface', 'route_region': region, 'graph_arc_id': arc_id, 'length_m': length, 'roughness_manning': parameters.roughness_manning, 'physical_section_scope': 'actual_rock_enclosed_cutter_ring' if underground else 'actual_open_floor_engineered_vertical_overflow_walls', 'section': section, 'section_geometry_reference': {'station_id': station['station_id'], 'derived_ring_xyz_m': ring.tolist(), 'origin_xyz_m': origin.tolist(), 'transverse_unit_xz': transverse.tolist(), **reference}}

# Source: terrain_pipeline.hybrid_cave_geometry
def surface_cell(attachment, port, sampler, region, parameters):
    record = attachment['surface_node_record']
    arm = next((arm for arm in record['arms'] if arm['arc_id'] == port['arc_id']))
    vertices = _i1_np.asarray(record['geometry']['vertices_xyz_m'])
    inner = vertices[arm['inner_vertex_ids']]
    midpoint = _i1_np.array(port['midpoint_xz_m'])
    origin_xz = (inner[1, [0, 2]] + inner[2, [0, 2]]) / 2.0
    transverse = _i1_np.array([-port['flow_unit_xz'][1], port['flow_unit_xz'][0]])
    order = _i1_np.argsort((inner[:, [0, 2]] - origin_xz) @ transverse)
    inner = inner[order].copy()
    own_fans = _i1_compact_node_fans(record)
    half_arm_ids = {'shared:' + record['node_id'] + ':' + str(ordinal) for ordinal in attachment['half_arm_triangle_indices']}
    lower, upper = (inner[0, [0, 2]], inner[-1, [0, 2]])
    vector = upper - lower
    denominator = float(vector @ vector)
    points = {tuple(point[[0, 2]]) for point in inner}
    for fan in own_fans:
        if fan['triangle_id'] not in half_arm_ids:
            continue
        for vertex in fan['vertices_xz_m']:
            delta = _i1_np.array(vertex) - lower
            fraction = float(delta @ vector / denominator)
            distance = abs(float(delta[0] * vector[1] - delta[1] * vector[0])) / _i1_math.sqrt(denominator)
            if distance <= 1e-08 and 0.0 < fraction < 1.0 and all((_i1_math.dist(vertex, point) > 1e-08 for point in points)):
                points.add(tuple(vertex))
    horizontal = sorted(points, key=lambda point: float((_i1_np.array(point) - lower) @ vector))
    inner = _i1_np.array([[point[0], 0.0, point[1]] for point in horizontal])
    witnesses = []
    for point in inner:
        result = sampler(point[[0, 2]])
        point[1] = result['derived_bed_m']
        witnesses.append(result)
    origin = [origin_xz[0], float(inner[:, 1].min()), origin_xz[1]]
    length = float(_i1_np.linalg.norm(origin_xz - midpoint))
    if length <= 0:
        raise ValueError('zero_actual_surface_half_arm_length')
    station = {'station_id': region + ':half_arm', 'derived_ring_xyz_m': inner.tolist(), 'origin_xyz_m': origin, 'transverse_unit_xz': transverse.tolist()}
    saved = {'surface_node_pin': attachment['surface_node_pin'], 'canonical_port_pin': attachment['canonical_port_pin'], 'actual_complete_port_proof': attachment['actual_complete_port_proof'], 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'geometry': record['geometry'], 'compact_native_fans': own_fans, 'inner_vertex_ids': arm['inner_vertex_ids'], 'inner_source_witnesses': witnesses, 'hydraulic_inner_ring_xyz_m': inner.tolist(), 'hydraulic_station_id': station['station_id'], 'midpoint_geometry_only_not_hydraulic_bc': True}
    return (cell_record(station, region, 'engineered:sink:half_arm_attachment' if region == 'surface_in' else 'engineered:spring:half_arm_attachment', length, parameters, {'actual_half_arm_triangle_indices': attachment['half_arm_triangle_indices']}), saved)

# Source: terrain_pipeline.hybrid_cave_geometry
def build_geometry(graph_record, sampler, parameters=Parameters()):
    graph = load_graph(graph_record)
    portals = {kind: next((node for node in graph.nodes if node.kind == kind)) for kind in ('sink', 'spring')}
    ports = {kind: _i1_json.loads(node.source_record_json) for kind, node in portals.items()}
    for kind, port in ports.items():
        for value in sorted(portal_knots(port)):
            point = portal_point(port, value)
            result = sampler(point[[0, 2]])
            if abs(result['derived_bed_m'] - point[1]) > 1e-08:
                raise ValueError('actual_canonical_port_differs_from_saved_fan_bed:' + kind)
    vdm = build_charts(ports['sink'], ports['spring'], portals['sink'].xyz_m, portals['spring'].xyz_m, parameters)
    cover_witnesses = []
    for station in vdm['stations']:
        ring = _i1_np.array(station['derived_ring_xyz_m'])
        witnesses = [sampler(point[[0, 2]]) for point in ring]
        roof_cover = min((witness['derived_bed_m'] - point[1] for point, witness in zip(ring[-2:], witnesses[-2:])))
        if 0.25 <= station['fraction'] <= 0.75 and roof_cover < 0.5:
            raise ValueError('generated_route_has_insufficient_actual_roof_cover:' + station['station_id'])
        source_reference = [[point[0], witness['source_sample']['height_m'], point[2]] for point, witness in zip(ring, witnesses)]
        cover_witnesses.append({'station_id': station['station_id'], 'ring_source_witnesses': witnesses, 'minimum_roof_cover_m': roof_cover, 'original_source_reference_ring_xyz_m': source_reference, 'source_to_derived_displacement_ring_xyz_m': (ring - _i1_np.array(source_reference)).tolist(), 'separate_from_conduit_chart_VDM_displacement': True})
    origin = _i1_np.array(portals['sink'].xyz_m)
    rock_record, sampling = build_rock(vdm, sampler, parameters, origin)
    before = manifold_from_record(rock_record)
    above_y = max((sample['derived_bed_m'] for sample in sampling['samples'])) + 10.0
    closed_sections = []
    for station, witness in zip(vdm['stations'], cover_witnesses):
        ring = _i1_np.array(station['derived_ring_xyz_m'])
        containment = []
        for point in ring:
            hits = ray_hits(before, [point[0], above_y, point[2]], point.tolist(), origin)
            actual_cover = min((hit['position_xyz_m'][1] - point[1] for hit in hits), default=-_i1_math.inf)
            containment.append({'point_xyz_m': point.tolist(), 'rock_before_vertical_hits': hits, 'actual_sampled_top_cover_m': actual_cover if _i1_math.isfinite(actual_cover) else None})
        closed = closed_rock_section(containment)
        closed_sections.append(closed)
        witness.update(actual_ring_containment=containment, physical_closed_rock_section=closed)
    core_ids = [ordinal for ordinal, closed in enumerate(closed_sections) if closed]
    if not core_ids or core_ids != list(range(core_ids[0], core_ids[-1] + 1)):
        raise ValueError('actual_covered_core_missing_or_not_contiguous')
    vertices = _i1_np.array([station['derived_ring_xyz_m'] for station in vdm['stations']]).reshape(-1, 3) - origin
    cutter_record = mesh_record(vertices, vdm['triangles'], origin, 'cutter')
    cutter = manifold_from_record(cutter_record)
    after, removed = (before - cutter, before ^ cutter)
    import manifold3d as manifold
    if any((solid.status() != manifold.Error.NoError or solid.is_empty() for solid in (after, removed))):
        raise ValueError('actual_rock_boolean_failed_or_empty')
    if abs(before.volume() - after.volume() - removed.volume()) > max(1e-07, before.volume() * 1e-10):
        raise ValueError('signed_actual_solid_material_balance_failed')
    path, segments, openings = void_witnesses(before, after, removed, vdm, origin, sampler)
    attachments = {}
    cells = []
    for region, kind in (('surface_in', 'sink'), ('surface_out', 'spring')):
        arc = next((arc for arc in graph.arcs if arc.kind == 'portal_attachment' and portals[kind].node_id in arc.node_ids))
        evidence = _i1_json.loads(arc.source_record_json)
        cell, attachment = surface_cell(evidence, ports[kind], sampler, region, parameters)
        cells.append(cell)
        attachments[kind] = attachment
    stations = vdm['stations']
    distances = [_i1_math.dist(first['origin_xyz_m'], second['origin_xyz_m']) for first, second in zip(stations, stations[1:])]
    if min(distances) <= 0:
        raise ValueError('degenerate_conduit_station')
    gallery = [cell_record(station, 'underground', 'engineered:underground', (distances[ordinal - 1] if ordinal else 0.0) / 2 + (distances[ordinal] if ordinal < len(distances) else 0.0) / 2, parameters, {'vdm_station_index': ordinal, 'vdm_floor_vertex_indices': list(range(station['floor_vertex_count'])), 'cutter_ring_vertex_indices': list(range(ordinal * len(station['derived_ring_xyz_m']), ordinal * len(station['derived_ring_xyz_m']) + (len(station['derived_ring_xyz_m']) if closed_sections[ordinal] else station['floor_vertex_count'])))}, closed_rock=closed_sections[ordinal]) for ordinal, station in enumerate(stations)]
    cells = [cells[0], *gallery, cells[1]]
    links = []
    for ordinal, (first, second) in enumerate(zip(cells, cells[1:])):
        kind = {('surface', 'surface'): 'surface_half_arm', ('surface', 'underground'): 'sink_exchange', ('underground', 'surface'): 'spring_exchange', ('underground', 'underground'): 'conduit'}[first['kind'], second['kind']]
        links.append({'link_id': 'physical:' + str(ordinal), 'from_cell_id': first['cell_id'], 'to_cell_id': second['cell_id'], 'kind': kind, 'length_m': (first['length_m'] + second['length_m']) / 2, 'physical_attachment_reference': {'vdm_station_ids': [first['cell_id'], second['cell_id']], 'shared_native_port': ordinal in (0, len(cells) - 2)}})
    binding = {kind: {'port_arc_id': node.port_arc_id, 'port_identity_sha256': ports[kind]['identity_sha256'], 'immutable_station_id': stations[0 if kind == 'sink' else -1]['station_id'], 'full_native_floor_preserved': True, 'hydraulic_boundary_certified': False} for kind, node in portals.items()}
    beds = [min((point[1] for point in station['derived_ring_xyz_m'][:station['floor_vertex_count']])) for station in stations]
    geometry = {'schema': SCHEMA, 'status': 'candidate', 'rejection_reasons': [], 'graph_identity_sha256': graph_record['identity_sha256'], 'inputs': {key: _i1_asdict(pin) for key, pin in graph.inputs}, 'policy': POLICY, 'policy_identity_sha256': POLICY_SHA256, 'parameters': _i1_asdict(parameters), 'parameters_identity_sha256': identity(_i1_asdict(parameters)), 'portal_bindings': binding, 'portal_sections': {kind: {'pieces': native_bed_pieces(port), 'canonical_profile': port['profile'], 'geometry_port_only': True} for kind, port in ports.items()}, 'hydraulic_cells': cells, 'hydraulic_links': links, 'surface_attachment_route': 'actual_saved_half_arm_to_immutable_midpoint_floor', 'hydraulic_section_classification': 'physical_kind_surface_for_open_gallery_ramps_closed_underground_only_actual_rock_enclosed_core_route_region_unchanged', 'actual_closed_core_station_indices': core_ids, 'hydraulic_contract_identity_sha256': identity({'contract': 'actual-open-ramp-v2', 'physical_kind_independent_of_graph_route_region': True}), 'air_path_xyz_m': path, 'air_path_segments': segments, 'portal_opening_witnesses': openings, 'station_source_cover_witnesses': cover_witnesses, 'actual_solid_material': {'rock_before_m3': before.volume(), 'rock_after_m3': after.volume(), 'excavated_rock_m3': removed.volume(), 'exported_excavated_rock_m3': removed.volume(), 'fill_rock_m3': 0.0, 'signed_residual_m3': before.volume() - after.volume() - removed.volume()}, 'bed_slope_diagnostic': {'station_floor_elevation_m': beds, 'adverse_segments': [ordinal for ordinal in range(len(beds) - 1) if beds[ordinal + 1] > beds[ordinal]], 'not_adjusted_for_hydraulic_convenience': True}, 'conduit_length_m': _i1_math.fsum(distances), 'sampled_not_native_exact': True, 'fine15_replaced': False, 'independent_audit_passed': False, 'hydraulic_solved': False, 'hydraulic_ready': False, 'free_water_surface_generated': False, 'natural_outlet_certified': False, 'full_network_verified': False}
    hybrid_cave_geometry_guard()
    return (geometry, {'rock_before': rock_record, 'cutter': cutter_record, 'rock_after': save_manifold(after, origin, 'rock_after'), 'removed': save_manifold(removed, origin, 'removed'), 'vdm': vdm, 'source_sampling': sampling, 'surface_attachments': seal({'schema': 'td-hybrid-surface-attachments-v1', 'attachments': attachments})})

# Source: terrain_pipeline.hybrid_mesh_occupancy
def _polygons(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == 'Polygon':
        return [shape]
    if shape.geom_type == 'MultiPolygon':
        return list(shape.geoms)
    raise ValueError('unknown_nonpolygon_exact_slice_domain')

# Source: terrain_pipeline.hybrid_mesh_occupancy
def _occupancy(solid, shape, cap_shape, frame, points, coplanar):
    witnesses = []
    extent = float(_i2_np.linalg.norm(_i2_np.ptp(points, axis=0))) * 4.0 + 1.0
    queries = [(polygon.representative_point(), 1, 'retained_polygon') for polygon in _polygons(shape)]
    for polygon in _polygons(shape):
        for hole in polygon.interiors:
            void = _i2_Polygon(hole).difference(shape)
            if not void.is_empty:
                queries.append((void.representative_point(), 0, 'excluded_hole'))
    for query, expected, region in queries:
        uv = [query.x, query.y]
        local = _i2_np.asarray(frame['origin_local_xyz_m']) + query.x * _i2_np.asarray(frame['transverse_unit_xyz'])
        local[1] = query.y
        if cap_shape.covers(query):
            if not expected:
                raise ValueError('coplanar_facet_in_declared_slice_hole')
            witnesses.append({'point_uv_m': uv, 'point_local_xyz_m': local.tolist(), 'classification': 'original_oriented_coplanar_boundary_facet', 'region': region, 'coplanar_triangle_indices': [item['triangle_index'] for item in coplanar if _i2_Polygon(item['polygon_uv_m']).covers(query)]})
            continue
        parities = []
        for direction in ([1.0, 0.3713906763541037, 0.5291502622129182], [0.239, 1.0, 0.617]):
            vector = _i2_np.asarray(direction)
            vector /= _i2_np.linalg.norm(vector)
            hits = solid.ray_cast(local.tolist(), (local + extent * vector).tolist())
            distances = sorted(set((float(hit.distance) for hit in hits if hit.distance > 0.0)))
            parities.append(len(distances) % 2)
        if parities != [expected, expected]:
            raise ValueError('exact_slice_3D_occupancy_not_certified')
        witnesses.append({'point_uv_m': uv, 'point_local_xyz_m': local.tolist(), 'classification': 'original_Mesh64_interior_two_ray_parities' if expected else 'original_Mesh64_void_two_ray_parities', 'region': region, 'ray_parities': parities})
    return witnesses

# Source: terrain_pipeline.hybrid_river_faces
HYBRID_RIVER_FACES_SCHEMA = 'td-hybrid-river-faces-v1'

# Source: terrain_pipeline.hybrid_river_faces
FACE_SCHEMA = 'td-hybrid-river-face-v1'

# Source: terrain_pipeline.hybrid_river_faces
HYBRID_RIVER_FACES_POLICY = {'version': 'actual_saved_solid_link_faces-v1', 'coordinates': 'common_local_XYZ_metres_Y_vertical_face_u_Ylocal', 'gallery_plane': 'adjacent_station_origin_midpoint_normal_actual_XZ_station_difference', 'attachment_plane': 'exact_immutable_canonical_gallery_0_16_with_complete_saved_half_arm_proof', 'geometry': 'actual_Mesh64_plane_slices_not_minimum_of_endpoint_sections', 'wall': 'actual_rock_after_boundary_separate_from_free_surface_engineering_wall_and_artificial_cutter_cap', 'open': 'saved_actual_cut_floor_with_explicit_engineering_vertical_extensions_not_a_closed_cutter_roof', 'slot': 'storage_only_never_enlarges_face', 'unknown': 'missing_geometry_or_multiple_disconnected_apertures_refused_never_zero_flow_closed_wall', 'flow': 'not_computed_no_step_loss_no_new_roughness_original_link_length'}

# Source: terrain_pipeline.hybrid_river_faces
HYBRID_RIVER_FACES_POLICY_SHA256 = identity(HYBRID_RIVER_FACES_POLICY)

# Source: terrain_pipeline.hybrid_river_faces
def hybrid_river_faces_triangle_supports(points, triangles, frame):
    origin, normal = (_i5_np.array(frame['origin_local_xyz_m']), _i5_np.array(frame['normal_local_xyz']))
    distances = (points - origin) @ normal
    triangle_distances = distances[triangles]
    indices = _i5_np.flatnonzero((triangle_distances.min(axis=1) <= TOLERANCE_M) & (triangle_distances.max(axis=1) >= -TOLERANCE_M))
    segments, coplanar = ([], [])
    for ordinal in indices:
        ids = triangles[ordinal]
        vertices, values = (points[ids], distances[ids])
        if _i5_np.max(_i5_np.abs(values)) <= TOLERANCE_M:
            uv = project(vertices, frame)
            polygon = _i5_Polygon(uv)
            if polygon.area > AREA_TOLERANCE_M2:
                coplanar.append({'triangle_index': int(ordinal), 'vertex_indices': ids.tolist(), 'polygon_uv_m': uv.tolist()})
            continue
        intersections = []
        for first in range(3):
            following = (first + 1) % 3
            if abs(values[first]) <= TOLERANCE_M:
                intersections.append(vertices[first])
            if values[first] * values[following] < 0.0:
                fraction = values[first] / (values[first] - values[following])
                intersections.append((1.0 - fraction) * vertices[first] + fraction * vertices[following])
        distinct = []
        for point in intersections:
            if all((_i5_np.linalg.norm(point - other) > TOLERANCE_M for other in distinct)):
                distinct.append(point)
        if len(distinct) < 2:
            continue
        if len(distinct) > 2:
            pair = max(((first, second) for first in distinct for second in distinct), key=lambda pair: _i5_np.linalg.norm(pair[1] - pair[0]))
            distinct = list(pair)
        segments.append({'triangle_index': int(ordinal), 'vertex_indices': ids.tolist(), 'points_local_xyz_m': _i5_np.asarray(distinct).tolist(), 'points_uv_m': project(distinct, frame).tolist()})
    return (segments, coplanar)

# Source: terrain_pipeline.hybrid_river_faces
def polygon_from_loops(loops):
    polygons, holes = ([], [])
    for loop in loops:
        points = _i5_np.asarray(loop, float)
        area = float(_i5_np.sum(points[:, 0] * _i5_np.roll(points[:, 1], -1) - points[:, 1] * _i5_np.roll(points[:, 0], -1)) / 2.0)
        polygon = _i5_Polygon(points)
        if not polygon.is_valid or polygon.area <= AREA_TOLERANCE_M2:
            raise ValueError('invalid_actual_slice_polygon')
        (polygons if area > 0 else holes).append(polygon)
    result = _i5_unary_union(polygons)
    if holes:
        result = result.difference(_i5_unary_union(holes))
    return result

# Source: terrain_pipeline.hybrid_river_faces
def hybrid_river_faces_slice_solid(solid_data, frame, pin):
    solid, points, triangles = solid_data
    origin = _i5_np.array(frame['origin_local_xyz_m'])
    normal, transverse = (_i5_np.array(frame['normal_local_xyz']), _i5_np.array(frame['transverse_unit_xyz']))
    transform = _i5_np.vstack((_i5_np.r_[transverse, -float(transverse @ origin)], [0.0, 1.0, 0.0, 0.0], _i5_np.r_[normal, -float(normal @ origin)]))
    loops = [_i5_np.array(loop, dtype=float).tolist() for loop in solid.transform(transform.tolist()).slice(0.0).to_polygons()]
    segments, coplanar = hybrid_river_faces_triangle_supports(points, triangles, frame)
    shape = polygon_from_loops(loops) if loops else _i5_Polygon()
    method = 'Mesh64_transform_slice_exact_plane'
    if coplanar:
        caps = _i5_unary_union([_i5_Polygon(item['polygon_uv_m']) for item in coplanar])
        shape = shape.union(caps)
        method += '_union_exact_saved_coplanar_triangles'
    if not shape.is_valid:
        raise ValueError('actual_slice_boolean_invalid')
    polygons = [shape] if shape.geom_type == 'Polygon' and (not shape.is_empty) else list(shape.geoms) if shape.geom_type == 'MultiPolygon' else []
    record = {'mesh_pin': pin, 'method': method, 'polygons_uv_m': [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons], 'holes_uv_m': [[list(map(list, ring.coords))[:-1] for ring in polygon.interiors] for polygon in polygons], 'area_m2': float(shape.area), 'triangle_segments': segments, 'coplanar_triangle_supports': coplanar, 'coordinate_convention': frame['coordinate_convention']}
    return (record, shape)

# Source: terrain_pipeline.hybrid_river_faces
def lower_floor(polygon):
    coordinates = _i5_np.array(polygon.exterior.coords[:-1])
    values = sorted(set((float(point[0]) for point in coordinates)))
    floor = []
    for value in values:
        candidates = [point[1] for point in coordinates if point[0] == value]
        for first, second in zip(coordinates, _i5_np.roll(coordinates, -1, axis=0)):
            if min(first[0], second[0]) < value < max(first[0], second[0]):
                fraction = (value - first[0]) / (second[0] - first[0])
                candidates.append(float((1.0 - fraction) * first[1] + fraction * second[1]))
        floor.append([value, min(candidates)])
    if len(floor) < 2 or any((second[0] - first[0] <= 0 for first, second in zip(floor, floor[1:]))):
        raise ValueError('unknown_open_cut_floor')
    line = _i5_LineString(floor)
    if line.difference(polygon.boundary.buffer(TOLERANCE_M)).length > TOLERANCE_M:
        raise ValueError('cut_floor_not_actual_cutter_boundary')
    return floor

# Source: terrain_pipeline.hybrid_river_faces
def boundary_pieces(aperture, before, after, records, frame):
    floor = _i5_LineString(lower_floor(aperture))
    coordinates = list(aperture.exterior.coords)
    pieces = []
    for first, second in zip(coordinates, coordinates[1:]):
        line = _i5_LineString([first, second])
        if line.length <= TOLERANCE_M:
            continue
        points = []
        pending = [line.intersection(before.boundary), line.intersection(after.boundary)]
        while pending:
            intersection = pending.pop()
            if intersection.is_empty:
                continue
            if intersection.geom_type == 'Point':
                points.append(intersection)
            elif intersection.geom_type == 'LineString':
                points.extend((_i5_Point(point) for point in intersection.coords))
            elif hasattr(intersection, 'geoms'):
                pending.extend(intersection.geoms)
        fractions = sorted({0.0, 1.0, *(float(line.project(point, normalized=True)) for point in points)})
        for lower, upper in zip(fractions, fractions[1:]):
            part = _i5_LineString([line.interpolate(lower, normalized=True), line.interpolate(upper, normalized=True)])
            if part.length <= TOLERANCE_M:
                continue
            on_floor = part.difference(floor.buffer(TOLERANCE_M)).length <= TOLERANCE_M
            inside_before = before.buffer(TOLERANCE_M).covers(part)
            actual_wall = inside_before and part.difference(after.boundary.buffer(TOLERANCE_M)).length <= TOLERANCE_M
            if actual_wall:
                category = 'actual_rock_wet_wall'
            elif inside_before:
                raise ValueError('unknown_inside_rock_boundary_without_whole_rock_after_wall_support')
            elif on_floor:
                category = 'saved_cut_floor_open_air_side'
            elif abs(part.coords[0][0] - part.coords[-1][0]) <= TOLERANCE_M:
                category = 'engineering_lateral_wall_above_terrain'
            else:
                category = 'artificial_cutter_top_cap_not_wetted_wall'
            support = support_indices(part, records['cutter'])
            if not support:
                raise ValueError('missing_actual_cutter_triangle_boundary_support')
            rock_support = support_indices(part, records['rock_after'])
            if category == 'actual_rock_wet_wall' and (not rock_support):
                raise ValueError('unknown_actual_wall_without_saved_rock_triangle_support')
            uv = list(map(list, part.coords))
            pieces.append({'points_uv_m': uv, 'points_local_xyz_m': unproject(uv, frame).tolist(), 'category': category, 'potential_wetted_length_m': float(part.length) if category == 'actual_rock_wet_wall' else None, 'source_triangle_indices': {'cutter': support, 'rock_after': rock_support}})
    return pieces

# Source: terrain_pipeline.hybrid_river_faces
def classify_aperture(records, shapes, frame, *, canonical_floor=None):
    cutter, before, after, removed = (shapes[name] for name in ('cutter', 'rock_before', 'rock_after', 'removed'))
    if cutter.is_empty:
        raise ValueError('unknown_no_saved_cutter_aperture')
    if cutter.geom_type != 'Polygon' or cutter.interiors:
        raise ValueError('multiple_or_holed_void_aperture_not_certified')
    if removed.geom_type not in ('Polygon',) or removed.interiors:
        raise ValueError('missing_or_multiple_actual_excavation_slice')
    if removed.is_empty and canonical_floor is None:
        raise ValueError('unknown_open_floor_without_actual_excavation_or_canonical_port')
    blocked = float(cutter.intersection(after).area)
    if blocked > AREA_TOLERANCE_M2:
        raise ValueError('actual_rock_after_blocks_face_aperture')
    mismatch = float(removed.symmetric_difference(cutter.intersection(before)).area)
    if mismatch > AREA_TOLERANCE_M2:
        raise ValueError('actual_removed_slice_differs_from_rock_before_cut')
    outside = float(cutter.difference(before).area)
    pieces = boundary_pieces(cutter, before, after, records, frame)
    closed = bool(outside <= AREA_TOLERANCE_M2 and all((piece['category'] == 'actual_rock_wet_wall' for piece in pieces)))
    floor = lower_floor(cutter)
    if canonical_floor is not None:
        canonical = _i5_LineString(canonical_floor)
        if canonical.hausdorff_distance(_i5_LineString(floor)) > TOLERANCE_M:
            raise ValueError('canonical_complete_native_floor_not_actual_slice_floor')
        floor = canonical_floor
        closed = False
    if not closed and (not floor):
        raise ValueError('unknown_open_aperture_no_floor')
    free_edges = []
    for polygon in [removed] if not removed.is_empty else []:
        coordinates = list(polygon.exterior.coords)
        for first, second in zip(coordinates, coordinates[1:]):
            edge = _i5_LineString([first, second])
            if edge.length > TOLERANCE_M and edge.difference(cutter.boundary.buffer(TOLERANCE_M)).length > TOLERANCE_M:
                free_edges.append({'points_uv_m': [list(first), list(second)], 'category': 'original_rock_top_opening_free_boundary_not_wall', 'rock_before_triangle_indices': support_indices(edge, records['rock_before'])})
    polygon_uv = list(map(list, cutter.exterior.coords))[:-1]
    extensions = [{'u_interval_m': sorted([piece['points_uv_m'][0][0], piece['points_uv_m'][-1][0]]), 'lower_boundary_uv_m': piece['points_uv_m'], 'kind': 'above_saved_artificial_cap_only_not_above_actual_rock_roof'} for piece in pieces if piece['category'] == 'artificial_cutter_top_cap_not_wetted_wall']
    if not closed and (not extensions):
        raise ValueError('unknown_open_face_without_supported_free_top_interval')
    return {'kind': 'closed_polygon' if closed else 'open_cut_floor', 'polygon_uv_m': polygon_uv, 'polygon_local_xyz_m': unproject(polygon_uv, frame).tolist(), 'cut_floor_uv_m': floor, 'boundary_pieces': pieces, 'terrain_opening_free_edges': free_edges, 'blocked_area_m2': blocked, 'removed_replay_difference_area_m2': mismatch, 'actual_excavated_aperture_area_m2': float(removed.area), 'cutter_outside_original_rock_area_m2': outside, 'bounded_display_aperture_area_m2': float(cutter.area), 'pressure_slot_enlarges_face': False, 'open_extension': None if closed else {'kind': 'explicit_engineering_vertical', 'lateral_u_m': [floor[0][0], floor[-1][0]], 'unbounded_above_cut_floor': False, 'unbounded_only_over_supported_free_top_intervals': extensions, 'actual_rock_roof_segments_remain_bounded': True, 'artificial_cutter_roof_is_not_flow_ceiling': True, 'extension_is_engineering_not_whole_physical_path_certification': True, 'not_actual_terrain_floodplain': True}, 'closed_boundary_certified': closed}

# Source: terrain_pipeline.hybrid_river_faces
def build_faces(geometry, vdm, attachments, ports, meshes):
    common = _i5_np.array(meshes['cutter']['local_origin_xyz_m'], float)
    solids = {name: solid_from_mesh(record, common) for name, record in meshes.items()}
    stations = vdm['stations']
    cells = {cell['cell_id']: cell for cell in geometry['hydraulic_cells']}
    faces = []
    links = geometry['hydraulic_links']
    if len(stations) != 17 or len(links) != 18:
        raise ValueError('fixed_geometry03_requires_17_stations_18_links')
    for ordinal, link in enumerate(links):
        binding, canonical = (None, None)
        if ordinal in (0, 17):
            kind = 'sink' if ordinal == 0 else 'spring'
            station = stations[0 if kind == 'sink' else -1]
            port = ports[kind]
            frame = plane_frame(station['origin_xyz_m'], port['flow_unit_xz'], common)
            evidence = attachments['attachments'][kind]
            proof = evidence['actual_complete_port_proof']
            if proof['midpoint_port_identity_sha256'] != port['identity_sha256'] or sorted((segment['profile_segment_index'] for segment in proof['segments'])) != [0, 1, 2] or (not evidence['half_arm_triangle_indices']) or any((not segment['pieces'] for segment in proof['segments'])):
                raise ValueError('unknown_incomplete_saved_surface_attachment')
            canonical = canonical_floor(port, frame)
            binding = {'kind': kind, 'canonical_port_pin': evidence['canonical_port_pin'], 'surface_node_pin': evidence['surface_node_pin'], 'port_identity_sha256': port['identity_sha256'], 'actual_complete_port_proof': proof, 'half_arm_triangle_indices': evidence['half_arm_triangle_indices'], 'canonical_floor_uv_m': canonical, 'hydraulic_boundary_certified': False, 'shared_whole_function_not_endpoint_minimum': True}
            orientation_witness = {'canonical_station_id': station['station_id'], 'actual_flow_unit_xz': port['flow_unit_xz'], 'actual_source_arc_xyz_m': port['source_arc_xyz_m'], 'not_oblique_endpoint_section_projection': True}
            rule = 'actual_canonical_shared_port_plane'
        else:
            first, second = (stations[ordinal - 1], stations[ordinal])
            if (link['from_cell_id'], link['to_cell_id']) != (first['station_id'], second['station_id']):
                raise ValueError('link_station_order_mismatch')
            first_point, second_point = (_i5_np.array(first['origin_xyz_m']), _i5_np.array(second['origin_xyz_m']))
            frame = plane_frame((first_point + second_point) / 2.0, (second_point - first_point)[[0, 2]], common)
            orientation_witness = {'station_ids': [first['station_id'], second['station_id']], 'station_origin_world_xyz_m': [first_point.tolist(), second_point.tolist()], 'normal_rule': 'unit_horizontal_discrete_centerline_segment_not_area_cosine_rescale'}
            rule = 'actual_adjacent_station_midpoint_XZ_flow_plane'
        roughness = [cells[key]['roughness_manning'] for key in (link['from_cell_id'], link['to_cell_id'])]
        if roughness != [0.035, 0.035] or not _i5_math.isfinite(link['length_m']) or link['length_m'] <= 0:
            raise ValueError('unknown_roughness_or_invalid_original_link_length')
        record = {'schema': FACE_SCHEMA, 'face_id': 'face:' + str(ordinal), 'link_id': link['link_id'], 'from_cell_id': link['from_cell_id'], 'to_cell_id': link['to_cell_id'], 'plane': frame, 'plane_rule': rule, 'orientation_witness': orientation_witness, 'length_m': link['length_m'], 'length_source': 'unchanged_geometry_hydraulic_link', 'roughness_manning': 0.035, 'roughness_source_cell_ids': [link['from_cell_id'], link['to_cell_id']], 'roughness_binding_only_not_new_face_friction_certification': True, 'length_binding_only_not_resistance_length_certification': True, 'additional_step_loss': None, 'shared_port_binding': binding, 'status': 'candidate', 'rejection_reasons': []}
        record['hydraulic_use'] = {'status': 'needs_info', 'discharge_computed': False, 'required': ['independent_actual_face_geometry_passed', 'explicit_face_roughness_adoption', 'explicit_quasi_steady_resistance_length_policy', 'explicit_step_contraction_expansion_loss_policy'], 'unknown_loss_is_not_zero': True, 'unknown_geometry_is_not_closed_zero_flow': True}
        try:
            slices, shapes = ({}, {})
            for name in ('cutter', 'removed', 'rock_before', 'rock_after'):
                slices[name], shapes[name] = hybrid_river_faces_slice_solid(solids[name], frame, geometry['mesh_pins'][name])
            record['solid_slices'] = slices
            record['aperture'] = classify_aperture(slices, shapes, frame, canonical_floor=canonical)
        except ValueError as error:
            record.update(status='refused', rejection_reasons=[str(error)], unknown_geometry_not_zero_flow=True)
        faces.append(seal(record))
        guard()
    refused = [face['face_id'] for face in faces if face['status'] != 'candidate']
    return seal({'schema': HYBRID_RIVER_FACES_SCHEMA, 'status': 'refused' if refused else 'candidate_unverified', 'rejection_reasons': refused, 'faces': faces, 'face_count': len(faces), 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': geometry['graph_identity_sha256'], 'policy': HYBRID_RIVER_FACES_POLICY, 'policy_identity_sha256': HYBRID_RIVER_FACES_POLICY_SHA256, 'independent_audit_passed': False, 'hydraulic_solved': False, 'native_exact': False, 'water_discharge_computed': False, 'storage_geometry_changed': False, 'pressure_slot_enlarges_face': False, 'actual_peak_rss_bytes': guard()})

# Source: terrain_pipeline.hybrid_mesh_plane
NUMERICAL_POLICY = {'version': 'identity_cached_mesh_plane-v1', 'plane': 'exact_rational_sign_of_saved_binary64_coordinates_and_plane', 'intersection': 'one_exact_rational_intersection_per_original_unoriented_edge_then_binary64', 'identity': 'original_vertex_or_sorted_original_edge_ids_no_round_bucket_no_snap', 'regions': 'directed_identity_loops_polygonize_winding_holes_and_3D_occupancy_check', 'coplanar': 'oriented_original_facets_closed_trace_and_separate_positive_negative_interior_traces', 'geometry': 'unchanged_saved_Mesh64_no_CrossSection_grid', 'thresholds': 'no_area_or_distance_acceptance_threshold_relaxation'}

# Source: terrain_pipeline.hybrid_mesh_plane
NUMERICAL_POLICY_SHA256 = identity(NUMERICAL_POLICY)

# Source: terrain_pipeline.hybrid_mesh_plane
def _fraction(value):
    return _i3_Fraction(float(value))

# Source: terrain_pipeline.hybrid_mesh_plane
def _intersection_data(points, triangles, frame):
    points, triangles = (_i3_np.asarray(points, float), _i3_np.asarray(triangles, int))
    if points.ndim != 2 or points.shape[1] != 3 or (not _i3_np.isfinite(points).all()) or (triangles.ndim != 2) or (triangles.shape[1] != 3) or (len(triangles) > 200000) or (len(triangles) and (triangles.min() < 0 or triangles.max() >= len(points))):
        raise ValueError('invalid_exact_slice_mesh')
    origin = list(map(_fraction, frame['origin_local_xyz_m']))
    normal = list(map(_fraction, frame['normal_local_xyz']))
    transverse = list(map(_fraction, frame['transverse_unit_xyz']))
    active_axes = [axis for axis, value in enumerate(normal) if value]
    distances = [sum((normal[axis] * (_fraction(point[axis]) - origin[axis]) for axis in active_axes)) for point in points]
    signs = [int(value > 0) - int(value < 0) for value in distances]
    nodes, segments, coplanar = ({}, [], [])

    def node(vertex=None, edge=None):
        node_id = 'v:' + str(vertex) if vertex is not None else 'e:' + ':'.join(map(str, edge))
        if node_id not in nodes:
            if vertex is not None:
                rational = list(map(_fraction, points[vertex]))
                references = [vertex]
            else:
                first, second = edge
                fraction = distances[first] / (distances[first] - distances[second])
                rational = [_fraction(points[first, axis]) + fraction * (_fraction(points[second, axis]) - _fraction(points[first, axis])) for axis in range(3)]
                references = list(edge)
            uv = [float(sum((transverse[axis] * (rational[axis] - origin[axis]) for axis in range(3)))), float(rational[1])]
            nodes[node_id] = {'node_id': node_id, 'vertex_indices': references, 'point_local_xyz_m': list(map(float, rational)), 'point_uv_m': uv}
        return node_id
    for ordinal, triangle in enumerate(triangles):
        values = [signs[index] for index in triangle]
        if min(values) > 0 or max(values) < 0:
            continue
        vertices = points[triangle]
        outward = _i3_np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
        if _i3_np.linalg.norm(outward) == 0:
            raise ValueError('degenerate_exact_slice_triangle')
        if not any(values):
            ids = [node(vertex=int(index)) for index in triangle]
            uv = [nodes[index]['point_uv_m'] for index in ids]
            rational_edges = [[_fraction(vertices[index, axis]) - _fraction(vertices[0, axis]) for axis in range(3)] for index in (1, 2)]
            first, second = rational_edges
            rational_outward = [first[1] * second[2] - first[2] * second[1], first[2] * second[0] - first[0] * second[2], first[0] * second[1] - first[1] * second[0]]
            dot = sum((value * direction for value, direction in zip(rational_outward, normal)))
            if dot == 0:
                raise ValueError('degenerate_coplanar_facet_orientation')
            coplanar.append({'triangle_index': ordinal, 'vertex_indices': triangle.tolist(), 'intersection_node_ids': ids, 'polygon_uv_m': uv, 'normal_dot_plane': float(dot), 'occupied_incident_side': 'negative' if dot > 0 else 'positive'})
            continue
        ids = []
        for first, second in zip(triangle, _i3_np.roll(triangle, -1)):
            if signs[first] == 0:
                ids.append(node(vertex=int(first)))
            if signs[first] * signs[second] < 0:
                ids.append(node(edge=tuple(sorted((int(first), int(second))))))
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2:
            continue
        if len(ids) != 2:
            raise ValueError('ambiguous_exact_triangle_plane_intersection')
        tangent = _i3_np.cross(_i3_np.asarray(frame['normal_local_xyz']), outward)
        delta = _i3_np.asarray(nodes[ids[1]]['point_local_xyz_m']) - nodes[ids[0]]['point_local_xyz_m']
        orientation = float(delta @ tangent)
        if orientation == 0:
            raise ValueError('degenerate_projected_exact_segment')
        if orientation < 0:
            ids.reverse()
        incident = 'both' if min(values) < 0 < max(values) else 'positive' if max(values) > 0 else 'negative'
        segments.append({'triangle_index': ordinal, 'vertex_indices': triangle.tolist(), 'intersection_node_ids': ids, 'incident_halfspace': incident, 'points_local_xyz_m': [nodes[index]['point_local_xyz_m'] for index in ids], 'points_uv_m': [nodes[index]['point_uv_m'] for index in ids]})
    return (nodes, segments, coplanar, signs)

# Source: terrain_pipeline.hybrid_mesh_plane
def triangle_supports(points, triangles, frame):
    _, segments, coplanar, _ = _intersection_data(points, triangles, frame)
    return (segments, coplanar)

# Source: terrain_pipeline.hybrid_mesh_plane
def _side_region(nodes, segments, side):
    edges, supports = ({}, _i3_defaultdict(list))
    for segment in segments:
        if segment['incident_halfspace'] not in (side, 'both'):
            continue
        first, second = segment['intersection_node_ids']
        key = tuple(sorted((first, second)))
        direction = 1 if key == (first, second) else -1
        edges[key] = edges.get(key, 0) + direction
        supports[key].append(segment['triangle_index'])
    active = []
    for key, count in edges.items():
        if abs(count) > 1:
            raise ValueError('nonmanifold_duplicate_exact_slice_edge')
        if count:
            active.append(key if count > 0 else key[::-1])
    outgoing, incoming = ({}, _i3_defaultdict(int))
    for first, second in active:
        if first in outgoing:
            raise ValueError('branched_exact_slice_identity_graph')
        outgoing[first] = second
        incoming[second] += 1
    if set(outgoing) != set(incoming) or any((count != 1 for count in incoming.values())):
        raise ValueError('open_or_nonmanifold_exact_slice_identity_graph')
    pending, loops = (set(outgoing), [])
    while pending:
        start = min(pending)
        current, ids = (start, [])
        while current in pending:
            pending.remove(current)
            ids.append(current)
            current = outgoing[current]
        if current != start or len(ids) < 3:
            raise ValueError('invalid_exact_identity_loop')
        uv = [nodes[index]['point_uv_m'] for index in ids]
        anchor = _i3_np.asarray(uv[0])
        local = _i3_np.asarray(uv) - anchor
        area = float(sum((first[0] * second[1] - first[1] * second[0] for first, second in zip(local, _i3_np.roll(local, -1, axis=0)))) / 2.0)
        if area == 0 or not _i3_Polygon(uv).is_valid:
            raise ValueError('degenerate_or_self_crossing_exact_identity_loop')
        loops.append({'side': side, 'node_ids': ids, 'signed_area_m2': area, 'triangle_supports': [supports[tuple(sorted((first, second)))] for first, second in zip(ids, ids[1:] + ids[:1])]})
    lines = [_i3_LineString([nodes[first]['point_uv_m'], nodes[second]['point_uv_m']]) for first, second in active]
    if not lines:
        return (_i3_Polygon(), loops)
    cells, cuts, dangles, invalid = _i3_polygonize_full(lines)
    if not cuts.is_empty or not dangles.is_empty or (not invalid.is_empty):
        raise ValueError('exact_polygonize_incomplete_identity_graph')
    retained = []
    for cell in cells.geoms:
        representative = cell.representative_point()
        winding = sum((1 if loop['signed_area_m2'] > 0 else -1 for loop in loops if _i3_Polygon([nodes[index]['point_uv_m'] for index in loop['node_ids']]).covers(representative)))
        if winding not in (0, 1):
            raise ValueError('ambiguous_exact_slice_winding')
        if winding:
            retained.append(cell)
    return (_i3_unary_union(retained), loops)

# Source: terrain_pipeline.hybrid_mesh_plane
def slice_solid(solid_data, frame, pin):
    solid, points, triangles = solid_data
    points = _i3_np.asarray(points, float)
    nodes, segments, coplanar, signs = _intersection_data(points, triangles, frame)
    positive, positive_loops = _side_region(nodes, segments, 'positive')
    negative, negative_loops = _side_region(nodes, segments, 'negative')
    cap_shape = _i3_unary_union([_i3_Polygon(item['polygon_uv_m']) for item in coplanar])
    shape = _i3_unary_union([positive, negative, cap_shape])
    if not shape.is_valid:
        raise ValueError('invalid_exact_mesh_plane_region')
    polygons = _polygons(shape)
    occupancy = _occupancy(solid, shape, cap_shape, frame, points, coplanar)
    record = seal({'schema': 'td-hybrid-exact-mesh-plane-slice-v1', 'mesh_pin': pin, 'method': 'original_identity_cached_rational_mesh_plane_no_CrossSection', 'numerical_policy': NUMERICAL_POLICY, 'numerical_policy_identity_sha256': NUMERICAL_POLICY_SHA256, 'polygons_uv_m': [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons], 'holes_uv_m': [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in polygons], 'area_m2': float(shape.area), 'triangle_segments': segments, 'coplanar_triangle_supports': coplanar, 'intersection_nodes': list(nodes.values()), 'identity_loops': positive_loops + negative_loops, 'vertex_plane_classifications': [{'vertex_index': ordinal, 'sign': sign, 'classification_method': 'exact_rational'} for ordinal, sign in enumerate(signs)], 'one_sided_interior_traces': {side: {'polygons_uv_m': [list(map(list, polygon.exterior.coords))[:-1] for polygon in _polygons(domain)], 'holes_uv_m': [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in _polygons(domain)], 'area_m2': float(domain.area)} for side, domain in (('positive', positive), ('negative', negative))}, 'occupancy_witnesses': occupancy, 'coplanar_semantics': 'closed_trace_contains_actual_original_facets_side_occupation_recorded', 'coordinate_convention': frame['coordinate_convention']})
    guard()
    return (record, shape)

# Source: terrain_pipeline.hybrid_mesh_plane_v2
HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY = {'version': 'rational_topology_mesh_plane-v2', 'authority': 'saved_binary64_mesh_rational_XYZ_UV_nodes_and_exact_orientation', 'identity': 'original_vertex_and_unoriented_edge_ids_never_merged_or_snapped', 'display': 'consecutive_zero_length_display_edges_only_omitted_with_full_rational_witness', 'topology': 'exact_directed_loops_and_exact_containment_parents_equal_display_hierarchy_or_refused', 'certificate': 'original_1e-8m_distance_and_1e-8m2_area_limits_no_collapsed_positive_area_loop', 'projection_bound': 'exact_rational_L1_distance_and_display_perimeter_with_upward_binary64_ceiling', 'coplanar': 'original_oriented_facets_closed_trace_and_separate_incident_halfspaces', 'occupancy': 'original_Mesh64_two_ray_inside_and_hole_void_checks', 'geometry': 'saved_mesh_unchanged_no_CrossSection_grid'}

# Source: terrain_pipeline.hybrid_mesh_plane_v2
HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256 = identity(HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY)

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _sub(first, second):
    return [left - right for left, right in zip(first, second)]

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _cross(first, second):
    return [first[1] * second[2] - first[2] * second[1], first[2] * second[0] - first[0] * second[2], first[0] * second[1] - first[1] * second[0]]

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _dot(first, second):
    return sum((left * right for left, right in zip(first, second)))

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _trace(points, triangles, frame):
    points, triangles = (_i4_np.asarray(points, float), _i4_np.asarray(triangles, int))
    if points.ndim != 2 or points.shape[1] != 3 or (not _i4_np.isfinite(points).all()) or (triangles.ndim != 2) or (triangles.shape[1] != 3) or (len(triangles) > 200000) or (len(triangles) and (triangles.min() < 0 or triangles.max() >= len(points))):
        raise ValueError('invalid_rational_slice_mesh')
    rational_points = [list(map(_i4_Fraction, point)) for point in points]
    origin, normal, transverse = [list(map(_i4_Fraction, frame[name])) for name in ('origin_local_xyz_m', 'normal_local_xyz', 'transverse_unit_xyz')]
    distances = [_dot(normal, _sub(point, origin)) for point in rational_points]
    signs = [int(value > 0) - int(value < 0) for value in distances]
    nodes, segments, caps, collapses = ({}, [], [], [])

    def node(vertex=None, edge=None):
        node_id = 'v:' + str(vertex) if vertex is not None else 'e:' + ':'.join(map(str, edge))
        if node_id not in nodes:
            if vertex is not None:
                rational = rational_points[vertex]
                references = [vertex]
            else:
                first, second = edge
                fraction = distances[first] / (distances[first] - distances[second])
                rational = [left + fraction * (right - left) for left, right in zip(rational_points[first], rational_points[second])]
                references = list(edge)
            uv = [_dot(transverse, _sub(rational, origin)), rational[1]]
            nodes[node_id] = {'node_id': node_id, 'vertex_indices': references, 'point_local_xyz_m': list(map(float, rational)), 'point_uv_m': list(map(float, uv)), 'rational_xyz_m': list(map(str, rational)), 'rational_uv_m': list(map(str, uv))}
        return node_id
    for ordinal, triangle in enumerate(triangles):
        values = [signs[index] for index in triangle]
        if min(values) > 0 or max(values) < 0:
            continue
        vertices = [rational_points[index] for index in triangle]
        outward = _cross(_sub(vertices[1], vertices[0]), _sub(vertices[2], vertices[0]))
        if not any(outward):
            raise ValueError('exact_zero_source_triangle')
        if not any(values):
            ids = [node(vertex=int(index)) for index in triangle]
            orientation = _dot(outward, normal)
            if not orientation:
                raise ValueError('exact_zero_coplanar_orientation')
            caps.append({'triangle_index': ordinal, 'vertex_indices': triangle.tolist(), 'intersection_node_ids': ids, 'polygon_uv_m': [nodes[index]['point_uv_m'] for index in ids], 'normal_dot_plane': float(orientation), 'normal_dot_plane_rational': str(orientation), 'occupied_incident_side': 'negative' if orientation > 0 else 'positive'})
            continue
        ids = []
        for first, second in zip(triangle, _i4_np.roll(triangle, -1)):
            if signs[first] == 0:
                ids.append(node(vertex=int(first)))
            if signs[first] * signs[second] < 0:
                ids.append(node(edge=tuple(sorted((int(first), int(second))))))
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2:
            continue
        if len(ids) != 2:
            raise ValueError('ambiguous_rational_triangle_plane_intersection')
        first, second = [list(map(_i4_Fraction, nodes[index]['rational_xyz_m'])) for index in ids]
        orientation = _dot(_sub(second, first), _cross(normal, outward))
        if not orientation:
            raise ValueError('exact_zero_projected_segment')
        if orientation < 0:
            ids.reverse()
        incident = 'both' if min(values) < 0 < max(values) else 'positive' if max(values) > 0 else 'negative'
        segment = {'triangle_index': ordinal, 'vertex_indices': triangle.tolist(), 'intersection_node_ids': ids, 'incident_halfspace': incident, 'points_local_xyz_m': [nodes[index]['point_local_xyz_m'] for index in ids], 'points_uv_m': [nodes[index]['point_uv_m'] for index in ids], 'orientation_rational': str(orientation), 'exact_orientation_sign': int(orientation > 0) - int(orientation < 0), 'orientation_before_reversal_rational': str(orientation), 'rational_points_xyz_m': [nodes[index]['rational_xyz_m'] for index in ids], 'rational_points_uv_m': [nodes[index]['rational_uv_m'] for index in ids]}
        segment['orientation_rational'] = str(abs(orientation))
        segment['exact_orientation_sign'] = 1
        segments.append(segment)
        if segment['points_uv_m'][0] == segment['points_uv_m'][1]:
            rational_uv = [list(map(_i4_Fraction, nodes[index]['rational_uv_m'])) for index in ids]
            collapses.append({'triangle_index': ordinal, 'intersection_node_ids': ids, 'rational_delta_uv_m': list(map(str, _sub(rational_uv[1], rational_uv[0]))), 'display_point_uv_m': segment['points_uv_m'][0], 'display_omitted_zero_length_only': True, 'original_segment_and_node_identities_preserved': True})
    return (nodes, segments, caps, signs, collapses)

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def hybrid_mesh_plane_mechanism_2_triangle_supports(points, triangles, frame):
    _, segments, caps, _, _ = _trace(points, triangles, frame)
    return (segments, caps)

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _area(uv):
    return sum((first[0] * second[1] - first[1] * second[0] for first, second in zip(uv, uv[1:] + uv[:1]))) / 2

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def ceil_fraction(value):
    rounded = float(value)
    return _i4_math.nextafter(rounded, _i4_math.inf) if _i4_Fraction(rounded) < value else rounded

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _projection_certificate(rational, displayed):
    displayed = [list(map(_i4_Fraction, point)) for point in displayed]
    error = max((sum((abs(left - right) for left, right in zip(exact, display))) for exact, display in zip(rational, displayed)))
    perimeter = sum((sum((abs(left - right) for left, right in zip(first, second))) for first, second in zip(displayed, displayed[1:] + displayed[:1])))
    bound = 2 * error * perimeter + _i4_Fraction(_i4_math.nextafter(_i4_math.pi, _i4_math.inf)) * error ** 2
    return {'maximum_projection_distance_l1_rational': str(error), 'display_perimeter_l1_rational': str(perimeter), 'projection_area_bound_rational': str(bound), 'maximum_projection_distance_m': ceil_fraction(error), 'conservative_projection_area_bound_m2': ceil_fraction(bound), 'area_error_m2': ceil_fraction(abs(_area(rational) - _area(displayed)))}

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _inside(query, ring):
    winding = 0
    for first, second in zip(ring, ring[1:] + ring[:1]):
        orientation = (second[0] - first[0]) * (query[1] - first[1]) - (second[1] - first[1]) * (query[0] - first[0])
        if not orientation and min(first[0], second[0]) <= query[0] <= max(first[0], second[0]) and (min(first[1], second[1]) <= query[1] <= max(first[1], second[1])):
            raise ValueError('ambiguous_exact_hierarchy_boundary_query')
        if first[1] <= query[1] < second[1] and orientation > 0:
            winding += 1
        elif second[1] <= query[1] < first[1] and orientation < 0:
            winding -= 1
    return winding != 0

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _simple_rings(rings):
    edges, bounds = ([], [])
    for ring_index, ring in enumerate(rings):
        for ordinal, (first, second) in enumerate(zip(ring, ring[1:] + ring[:1])):
            low = [_i4_np.nextafter(float(min(first[axis], second[axis])), -_i4_np.inf) for axis in range(2)]
            high = [_i4_np.nextafter(float(max(first[axis], second[axis])), _i4_np.inf) for axis in range(2)]
            edges.append((ring_index, ordinal, first, second))
            bounds.append(_i4_box(low[0], low[1], high[0], high[1]))
    if not bounds:
        return
    tree = _i4_STRtree(bounds)
    comparisons = 0
    for index, (ring_index, ordinal, first, second) in enumerate(edges):
        for candidate in tree.query(bounds[index]):
            candidate = int(candidate)
            if candidate <= index:
                continue
            other_ring, other_ordinal, third, fourth = edges[candidate]
            if any((max(min(first[axis], second[axis]), min(third[axis], fourth[axis])) > min(max(first[axis], second[axis]), max(third[axis], fourth[axis])) for axis in range(2))):
                continue
            comparisons += 1
            if comparisons > 2000000:
                raise ValueError('whole_rational_intersection_budget_exceeded')
            adjacent = ring_index == other_ring and (ordinal - other_ordinal) % len(rings[ring_index]) in (1, len(rings[ring_index]) - 1)
            if adjacent:
                shared = next((point for point in (first, second) if point in (third, fourth)), None)
                if shared is None:
                    raise ValueError('adjacent_rational_edges_not_shared')
                left = second if first == shared else first
                right = fourth if third == shared else third
                vector_first, vector_second = (_sub(left, shared), _sub(right, shared))
                cross = vector_first[0] * vector_second[1] - vector_first[1] * vector_second[0]
                if not cross and _dot(vector_first, vector_second) > 0:
                    raise ValueError('overlapping_adjacent_rational_edges')
                continue

            def orientation(start, end, query):
                return (end[0] - start[0]) * (query[1] - start[1]) - (end[1] - start[1]) * (query[0] - start[0])
            if orientation(first, second, third) * orientation(first, second, fourth) <= 0 and orientation(third, fourth, first) * orientation(third, fourth, second) <= 0:
                raise ValueError('self_crossing_or_touching_rational_loops')

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def _side(nodes, segments, side):
    edges, supports = (_i4_defaultdict(int), _i4_defaultdict(list))
    for segment in segments:
        if segment['incident_halfspace'] not in (side, 'both'):
            continue
        first, second = segment['intersection_node_ids']
        key = tuple(sorted((first, second)))
        edges[key] += 1 if key == (first, second) else -1
        supports[key].append(segment['triangle_index'])
    active = []
    for key, count in edges.items():
        if abs(count) > 1:
            raise ValueError('nonmanifold_rational_slice_edge')
        if count:
            active.append(key if count > 0 else key[::-1])
    outgoing, incoming = ({}, _i4_defaultdict(int))
    for first, second in active:
        if first in outgoing:
            raise ValueError('branched_rational_identity_loop')
        outgoing[first] = second
        incoming[second] += 1
    if set(outgoing) != set(incoming) or any((count != 1 for count in incoming.values())):
        raise ValueError('open_rational_identity_loop')
    pending, loops, rings, displays = (set(outgoing), [], [], [])
    while pending:
        start, ids = (min(pending), [])
        current = start
        while current in pending:
            pending.remove(current)
            ids.append(current)
            current = outgoing[current]
        if current != start or len(ids) < 3:
            raise ValueError('invalid_rational_identity_loop')
        rational = [list(map(_i4_Fraction, nodes[index]['rational_uv_m'])) for index in ids]
        area = _area(rational)
        if not area:
            raise ValueError('exact_zero_loop_area')
        display_ids = []
        for index in ids:
            if not display_ids or nodes[index]['point_uv_m'] != nodes[display_ids[-1]]['point_uv_m']:
                display_ids.append(index)
        if len(display_ids) > 1 and nodes[display_ids[-1]]['point_uv_m'] == nodes[display_ids[0]]['point_uv_m']:
            display_ids.pop()
        display = _i4_Polygon([nodes[index]['point_uv_m'] for index in display_ids]) if len(display_ids) >= 3 else _i4_Polygon()
        displayed = [list(map(_i4_Fraction, nodes[index]['point_uv_m'])) for index in display_ids]
        display_area = _area(displayed) if displayed else _i4_Fraction(0)
        certificate = _projection_certificate(rational, [nodes[index]['point_uv_m'] for index in ids])
        error = certificate['maximum_projection_distance_m']
        area_bound = certificate['conservative_projection_area_bound_m2']
        if not display.is_valid or display.is_empty or display.area == 0 or (area * display_area <= 0) or (error > 1e-08) or (certificate['area_error_m2'] > 1e-08) or (area_bound > 1e-08):
            raise ValueError('display_loop_projection_not_certified')
        rings.append(rational)
        displays.append(display)
        loops.append({'side': side, 'node_ids': ids, 'display_loop_node_ids': display_ids, 'signed_area_m2': float(area), 'signed_area_m2_rational': str(area), 'display_signed_area_m2_rational': str(display_area), **certificate, 'triangle_supports': [supports[tuple(sorted((first, second)))] for first, second in zip(ids, ids[1:] + ids[:1])]})
    _simple_rings(rings)
    parents = []
    for ordinal, (ring, display) in enumerate(zip(rings, displays)):
        point = display.representative_point()
        query = [_i4_Fraction(point.x), _i4_Fraction(point.y)]
        if not _inside(query, ring):
            raise ValueError('display_representative_outside_exact_loop')
        containers = []
        for other, (other_ring, other_display) in enumerate(zip(rings, displays)):
            if other == ordinal:
                continue
            if display.boundary.intersects(other_display.boundary):
                raise ValueError('touching_display_loop_hierarchy_not_certified')
            if abs(_area(other_ring)) <= abs(_area(ring)):
                continue
            exact_inside = _inside(query, other_ring)
            if exact_inside != other_display.contains(point):
                raise ValueError('display_exact_loop_hierarchy_mismatch')
            if exact_inside:
                containers.append(other)
        parent = min(containers, key=lambda index: abs(_area(rings[index]))) if containers else None
        parents.append(parent)
        loops[ordinal].update(containment_query_uv_rational=list(map(str, query)), exact_parent_loop_index=parent, display_parent_loop_index=parent, hierarchy_certified=True)
    polygons = []
    for ordinal, loop in enumerate(loops):
        positive = _i4_Fraction(loop['signed_area_m2_rational']) > 0
        parent = parents[ordinal]
        if parent is None and (not positive) or (parent is not None and positive == (_i4_Fraction(loops[parent]['signed_area_m2_rational']) > 0)):
            raise ValueError('invalid_exact_loop_winding_hierarchy')
        if positive:
            holes = [list(displays[index].exterior.coords) for index, value in enumerate(parents) if value == ordinal and _i4_Fraction(loops[index]['signed_area_m2_rational']) < 0]
            polygon = _i4_Polygon(displays[ordinal].exterior.coords, holes)
            if not polygon.is_valid:
                raise ValueError('invalid_certified_display_polygon')
            polygons.append(polygon)
    return (_i4_unary_union(polygons), loops)

# Source: terrain_pipeline.hybrid_mesh_plane_v2
def hybrid_mesh_plane_mechanism_2_slice_solid(solid_data, frame, pin):
    solid, points, triangles = solid_data
    nodes, segments, caps, signs, collapses = _trace(points, triangles, frame)
    positive, positive_loops = _side(nodes, segments, 'positive')
    negative, negative_loops = _side(nodes, segments, 'negative')
    cap_polygons = []
    cap_bound = _i4_Fraction(0)
    for cap in caps:
        rational = [list(map(_i4_Fraction, nodes[index]['rational_uv_m'])) for index in cap['intersection_node_ids']]
        display = _i4_Polygon(cap['polygon_uv_m'])
        certificate = _projection_certificate(rational, cap['polygon_uv_m'])
        if not display.is_valid or display.area == 0 or certificate['maximum_projection_distance_m'] > 1e-08 or (certificate['conservative_projection_area_bound_m2'] > 1e-08) or (certificate['area_error_m2'] > 1e-08):
            raise ValueError('coplanar_projection_not_certified')
        cap['projection_certificate'] = {'signed_area_m2_rational': str(_area(rational)), **certificate}
        cap_bound += _i4_Fraction(certificate['projection_area_bound_rational'])
        cap_polygons.append(display)
    cap_shape = _i4_unary_union(cap_polygons)
    shape = _i4_unary_union([positive, negative, cap_shape])
    if not shape.is_valid:
        raise ValueError('invalid_rational_closed_trace_display')
    loops = positive_loops + negative_loops
    rational_bound = sum((_i4_Fraction(loop['projection_area_bound_rational']) for loop in loops)) + cap_bound
    bound = ceil_fraction(rational_bound)
    if bound > 1e-08:
        raise ValueError('whole_slice_projection_error_bound_exceeded')
    polygons = _polygons(shape)
    record = seal({'schema': 'td-hybrid-exact-mesh-plane-slice-v2', 'mesh_pin': pin, 'method': 'rational_identity_topology_certified_binary64_display', 'numerical_policy': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY, 'numerical_policy_identity_sha256': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256, 'polygons_uv_m': [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons], 'holes_uv_m': [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in polygons], 'area_m2': float(shape.area), 'triangle_segments': segments, 'coplanar_triangle_supports': caps, 'intersection_nodes': list(nodes.values()), 'identity_loops': loops, 'projection_collapse_witnesses': collapses, 'projection_area_error_bound_m2': bound, 'projection_area_error_bound_rational': str(rational_bound), 'display_projection_certified': True, 'vertex_plane_classifications': [{'vertex_index': ordinal, 'sign': sign, 'classification_method': 'exact_rational'} for ordinal, sign in enumerate(signs)], 'one_sided_interior_traces': {side: {'polygons_uv_m': [list(map(list, polygon.exterior.coords))[:-1] for polygon in _polygons(domain)], 'holes_uv_m': [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in _polygons(domain)], 'area_m2': float(domain.area)} for side, domain in (('positive', positive), ('negative', negative))}, 'occupancy_witnesses': _occupancy(solid, shape, cap_shape, frame, _i4_np.asarray(points), caps), 'coplanar_semantics': 'closed_trace_retains_original_oriented_facets_no_cap_deletion', 'coordinate_convention': frame['coordinate_convention']})
    guard()
    return (record, shape)

# Source: terrain_pipeline.hybrid_river_faces_v2
HYBRID_RIVER_FACES_MECHANISM_2_SCHEMA = 'td-hybrid-river-faces-v2'

# Source: terrain_pipeline.hybrid_river_faces_v2
HYBRID_RIVER_FACES_MECHANISM_2_FACE_SCHEMA = 'td-hybrid-river-face-v2'

# Source: terrain_pipeline.hybrid_river_faces_v2
ROLES = frozenset(('floor', 'lateral', 'roof', 'endcap'))

# Source: terrain_pipeline.hybrid_river_faces_v2
HYBRID_RIVER_FACES_MECHANISM_2_POLICY = {'version': 'actual_polygon_topology_coupled_link_faces-v2', 'geometry': 'actual_coupled_saved_solid_slices_polygon_authoritative_no_height_function', 'numerical_slice': 'td-hybrid-exact-mesh-plane-slice-v2_rational_loops_explicit_projection_collapse_no_CrossSection', 'coordinates': 'common_local_XYZ_metres_face_u_Ylocal', 'source_role': 'original_station_major_VDM_triangle_or_audited_surface_prism_triangle', 'physical_exposure': 'actual_rock_wall_or_saved_open_boundary_separate_from_source_role', 'canonical': 'independent_composition_complete_two_sided_port_proof_required_no_cap_deletion', 'composition': 'independently_audited_v3_saved_stage_replay_original_geometry_and_main_mesh_pins_unchanged', 'removed': 'multiple_material_components_allowed_only_with_exact_boolean_replay_not_fluid_connectivity', 'unknown': 'refused_not_zero_flow', 'slot': 'storage_only_never_enlarges_face', 'hydraulics': 'needs_info_no_law_no_solver_no_Q'}

# Source: terrain_pipeline.hybrid_river_faces_v2
HYBRID_RIVER_FACES_MECHANISM_2_POLICY_SHA256 = identity(HYBRID_RIVER_FACES_MECHANISM_2_POLICY)

# Source: terrain_pipeline.hybrid_river_faces_v2
def vdm_role_source(vdm, mesh, common_origin, mesh_pin):
    stations = vdm['stations']
    if len(stations) < 2:
        raise ValueError('unknown_incomplete_station_major_VDM')
    counts = {len(station['derived_ring_xyz_m']) for station in stations}
    floors = {station['floor_vertex_count'] for station in stations}
    if len(counts) != 1 or len(floors) != 1:
        raise ValueError('unknown_variable_ring_topology')
    count, floor_count = (counts.pop(), floors.pop())
    if floor_count < 2 or count != floor_count + 2:
        raise ValueError('unknown_ring_floor_lateral_roof_topology')
    points = _i6_np.asarray([station['derived_ring_xyz_m'] for station in stations], float).reshape(-1, 3)
    saved = _i6_np.asarray(mesh['vertices_local_xyz_m'], float)
    triangles = _i6_np.asarray(mesh['triangles'], int)
    if points.shape != saved.shape or not _i6_np.array_equal(points - _i6_np.asarray(mesh['local_origin_xyz_m'], float), saved) or triangles.shape != _i6_np.asarray(vdm['triangles']).shape or (not _i6_np.array_equal(triangles, vdm['triangles'])):
        raise ValueError('original_cutter_not_immutable_station_major_VDM')
    roles = []
    for ordinal, triangle in enumerate(triangles):
        station_ids = set((int(vertex) // count for vertex in triangle))
        offsets = set((int(vertex) % count for vertex in triangle))
        if len(station_ids) == 1:
            if station_ids not in ({0}, {len(stations) - 1}):
                raise ValueError('unknown_interior_station_cap')
            role = 'endcap'
            ring_edge = None
        else:
            if len(station_ids) != 2 or max(station_ids) - min(station_ids) != 1:
                raise ValueError('nonadjacent_station_triangle_not_supported')
            edges = [edge for edge in range(count) if offsets == {edge, (edge + 1) % count}]
            if len(edges) != 1:
                raise ValueError('unknown_triangle_ring_edge')
            ring_edge = edges[0]
            role = 'floor' if ring_edge < floor_count - 1 else 'roof' if ring_edge == floor_count else 'lateral'
        roles.append({'triangle_index': ordinal, 'source_role': role, 'ring_edge_index': ring_edge, 'station_indices': sorted(station_ids), 'vertex_indices': triangle.tolist()})
    return {'mesh_pin': mesh_pin, 'points_local_xyz_m': points - _i6_np.asarray(common_origin), 'triangles': triangles, 'triangle_roles': roles, 'role_rule': 'station_major_floor_vertex_count_not_edge_slope'}

# Source: terrain_pipeline.hybrid_river_faces_v2
def surface_role_sources(prisms, common_origin, prism_pin):
    sources = []
    triangle_count = 0
    for kind in ('sink', 'spring'):
        for bottom in prisms['half_arms'][kind]['bottom_triangles']:
            mesh = bottom['prism']
            points = _i6_np.asarray(mesh['vertices_local_xyz_m'], float)
            triangles = _i6_np.asarray(mesh['triangles'], int)
            roles = bottom['prism_triangle_roles']
            if points.shape != (6, 3) or triangles.shape != (8, 3) or roles != ['floor', 'artificial_top_cap'] + ['lateral'] * 6 or (not _i6_np.isfinite(points).all()):
                raise ValueError('unknown_surface_prism_role_topology')
            world_bottom = _i6_np.asarray(bottom['bottom_vertices_xyz_m'], float)
            if not _i6_np.array_equal(world_bottom - _i6_np.asarray(mesh['local_origin_xyz_m']), points[:3]):
                raise ValueError('surface_role_floor_not_actual_saved_bottom')
            sources.append({'mesh_pin': prism_pin, 'points_local_xyz_m': points + (_i6_np.asarray(mesh['local_origin_xyz_m']) - _i6_np.asarray(common_origin)), 'triangles': triangles, 'role_rule': 'audited_saved_triangular_prism_topology', 'triangle_roles': [{'triangle_index': ordinal, 'source_role': 'roof' if role == 'artificial_top_cap' else role, 'original_prism_role': role, 'half_arm_kind': kind, 'bottom_triangle_id': bottom['bottom_triangle_id'], 'fan_key': bottom['fan_key'], 'source_function_identity_sha256': bottom['source_function_identity_sha256'], 'prism_identity_sha256': mesh['identity_sha256'], 'vertex_indices': triangles[ordinal].tolist()} for ordinal, role in enumerate(roles)]})
            triangle_count += len(triangles)
            if triangle_count > 200000:
                raise ValueError('whole_surface_role_triangle_budget_exceeded')
    return sources

# Source: terrain_pipeline.hybrid_river_faces_v2
def role_slice(source, frame):
    segments, coplanar = hybrid_mesh_plane_mechanism_2_triangle_supports(source['points_local_xyz_m'], source['triangles'], frame)
    roles = {item['triangle_index']: item for item in source['triangle_roles']}
    if set(roles) != set(range(len(source['triangles']))):
        raise ValueError('unknown_incomplete_source_triangle_roles')
    for collection in (segments, coplanar):
        for item in collection:
            role = roles[item['triangle_index']]
            if role['source_role'] not in ROLES:
                raise ValueError('unsupported_saved_source_role')
            item['source_role'] = role['source_role']
            item['role_provenance'] = role
    return {'mesh_pin': source['mesh_pin'], 'role_rule': source['role_rule'], 'numerical_policy': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY, 'numerical_policy_identity_sha256': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256, 'triangle_segments': segments, 'coplanar_triangle_supports': coplanar}

# Source: terrain_pipeline.hybrid_river_faces_v2
def boundary_parts(polygon, before, after, slices, role_slices, frame):
    sources = [(source_index, item) for source_index, record in enumerate(role_slices) for item in record['triangle_segments'] if item['source_role'] != 'endcap']
    pieces = []
    coordinates = list(polygon.exterior.coords)
    for first, second in zip(coordinates, coordinates[1:]):
        line = _i6_LineString((first, second))
        if line.length <= TOLERANCE_M:
            continue
        points = []
        pending = [line.intersection(before.boundary), line.intersection(after.boundary)]
        for source_index, item in sources:
            source_line = _i6_LineString(item['points_uv_m'])
            if line.distance(source_line) <= TOLERANCE_M:
                points.extend((_i6_Point(point) for point in source_line.coords if line.distance(_i6_Point(point)) <= TOLERANCE_M))
        while pending:
            intersection = pending.pop()
            if intersection.is_empty:
                continue
            if intersection.geom_type == 'Point':
                points.append(intersection)
            elif intersection.geom_type == 'LineString':
                points.extend((_i6_Point(point) for point in intersection.coords))
            elif hasattr(intersection, 'geoms'):
                pending.extend(intersection.geoms)
        fractions = sorted({0.0, 1.0, *(float(line.project(point, normalized=True)) for point in points)})
        for lower, upper in zip(fractions, fractions[1:]):
            part = _i6_LineString((line.interpolate(lower, normalized=True), line.interpolate(upper, normalized=True)))
            if part.length <= TOLERANCE_M:
                continue
            support = [(source_index, item) for source_index, item in sources if part.difference(_i6_LineString(item['points_uv_m']).buffer(TOLERANCE_M)).length <= TOLERANCE_M]
            roles = {item['source_role'] for source_index, item in support}
            if len(roles) != 1:
                raise ValueError('unknown_or_ambiguous_actual_boundary_source_role')
            role = roles.pop()
            inside = before.buffer(TOLERANCE_M).covers(part)
            wall = inside and part.difference(after.boundary.buffer(TOLERANCE_M)).length <= TOLERANCE_M
            if wall:
                category = 'actual_rock_wet_wall'
            elif inside:
                raise ValueError('unknown_inside_rock_boundary_without_after_wall')
            else:
                category = {'floor': 'saved_cut_floor_open_air_side', 'lateral': 'engineering_lateral_wall_above_terrain', 'roof': 'artificial_cutter_top_cap_not_wetted_wall'}[role]
            cutter_support = support_indices(part, slices['cutter'])
            rock_support = support_indices(part, slices['rock_after'])
            if not cutter_support or (wall and (not rock_support)):
                raise ValueError('actual_polygon_boundary_missing_saved_triangle_support')
            uv = list(map(list, part.coords))
            pieces.append({'points_uv_m': uv, 'points_local_xyz_m': unproject(uv, frame).tolist(), 'source_role': role, 'physical_exposure': category, 'category': category, 'source_role_support': [{'source_index': source_index, **item['role_provenance']} for source_index, item in support], 'source_triangle_indices': {'cutter': cutter_support, 'rock_after': rock_support}, 'potential_wetted_length_m': float(part.length) if wall else None})
    if not pieces:
        raise ValueError('unknown_empty_actual_polygon_boundary')
    return pieces

# Source: terrain_pipeline.hybrid_river_faces_v2
def hybrid_river_faces_mechanism_2_classify_aperture(slices, shapes, role_slices, frame, canonical_profile=None, port_evidence=None):
    cutter, before, after, removed = (shapes[name] for name in ('cutter', 'rock_before', 'rock_after', 'removed'))
    if cutter.is_empty or cutter.geom_type != 'Polygon' or cutter.interiors or (not cutter.is_valid):
        raise ValueError('unknown_or_multiple_or_holed_actual_fluid_domain')
    if removed.geom_type not in ('Polygon', 'MultiPolygon') and (not removed.is_empty):
        raise ValueError('unknown_nonpolygon_material_slice')
    blocked = float(cutter.intersection(after).area)
    mismatch = float(removed.symmetric_difference(cutter.intersection(before)).area)
    projection_bounds = {name: record['projection_area_error_bound_m2'] for name, record in slices.items()}
    if any((not _i6_math.isfinite(value) or not 0 <= value <= AREA_TOLERANCE_M2 for value in projection_bounds.values())):
        raise ValueError('actual_slice_projection_error_bound_invalid')
    blocked_upper = _i6_math.nextafter(_i6_math.fsum((blocked, projection_bounds['cutter'], projection_bounds['rock_after'])), _i6_math.inf)
    mismatch_upper = _i6_math.nextafter(_i6_math.fsum((mismatch, *(projection_bounds[name] for name in ('removed', 'cutter', 'rock_before')))), _i6_math.inf)
    if blocked_upper > AREA_TOLERANCE_M2:
        raise ValueError('actual_rock_after_blocks_face_no_cap_deletion')
    if mismatch_upper > AREA_TOLERANCE_M2:
        raise ValueError('actual_total_removed_slice_boolean_mismatch')
    if canonical_profile is not None:
        if not port_evidence or not port_evidence.get('two_sided_complete_port_verified'):
            raise ValueError('unknown_canonical_two_sided_complete_port')
        if _i6_LineString(canonical_profile).difference(cutter.boundary.buffer(TOLERANCE_M)).length > TOLERANCE_M:
            raise ValueError('canonical_native_profile_not_actual_polygon_boundary')
    pieces = boundary_parts(cutter, before, after, slices, role_slices, frame)
    closed = all((piece['physical_exposure'] == 'actual_rock_wet_wall' for piece in pieces))
    extensions = [{'points_uv_m': piece['points_uv_m'], 'u_interval_m': sorted((piece['points_uv_m'][0][0], piece['points_uv_m'][-1][0])), 'source_role_support': piece['source_role_support']} for piece in pieces if piece['physical_exposure'] == 'artificial_cutter_top_cap_not_wetted_wall']
    if not closed and (not extensions):
        raise ValueError('unknown_open_face_without_topology_supported_free_top_interval')
    floor_pieces = [piece['points_uv_m'] for piece in pieces if piece['source_role'] == 'floor']
    if not floor_pieces:
        raise ValueError('unknown_missing_actual_topological_floor')
    return {'kind': 'closed_polygon' if closed else 'open_actual_polygon', 'polygon_uv_m': list(map(list, cutter.exterior.coords))[:-1], 'polygon_local_xyz_m': unproject(list(cutter.exterior.coords)[:-1], frame).tolist(), 'boundary_pieces': pieces, 'floor_boundary_pieces_uv_m': floor_pieces, 'polygon_authoritative': True, 'floor_height_function_required': False, 'blocked_area_m2': blocked, 'removed_replay_difference_area_m2': mismatch, 'blocked_area_upper_bound_m2': blocked_upper, 'removed_replay_difference_area_upper_bound_m2': mismatch_upper, 'projection_area_error_bounds_m2': projection_bounds, 'material_component_count': len(removed.geoms) if removed.geom_type == 'MultiPolygon' else int(not removed.is_empty), 'material_components_do_not_certify_fluid_connectivity': True, 'bounded_display_aperture_area_m2': float(cutter.area), 'actual_excavated_aperture_area_m2': float(removed.area), 'pressure_slot_enlarges_face': False, 'closed_boundary_certified': closed, 'canonical_two_sided_evidence': port_evidence, 'open_extension': None if closed else {'kind': 'explicit_engineering_supported_top_intervals_only', 'unbounded_above_cut_floor': False, 'supported_free_top_intervals': extensions, 'actual_rock_roof_segments_remain_bounded': True, 'extension_is_not_physical_path_certification': True}}

# Source: terrain_pipeline.hybrid_river_faces_v2
def hybrid_river_faces_mechanism_2_build_faces(geometry, vdm, attachments, ports, meshes, composition, composition_audit, prisms, audit_pin):
    common = _i6_np.asarray(meshes['cutter']['local_origin_xyz_m'], float)
    solids = {name: solid_from_mesh(meshes[name], common) for name in ('cutter', 'removed', 'rock_before', 'rock_after')}
    role_sources = [vdm_role_source(vdm, meshes['original_cutter'], common, composition['mesh_pins']['original_cutter'])]
    role_sources.extend(surface_role_sources(prisms, common, composition['surface_prisms_pin']))
    stations = vdm['stations']
    links = geometry['hydraulic_links']
    cells = {cell['cell_id']: cell for cell in geometry['hydraulic_cells']}
    if len(stations) != 17 or len(links) != 18:
        raise ValueError('fixed_original_route_requires_17_stations_18_links')
    pins = {name: composition['mesh_pins']['coupled_cutter' if name == 'cutter' else name] for name in ('cutter', 'removed', 'rock_before', 'rock_after')}
    faces = []
    for ordinal, link in enumerate(links):
        canonical, binding, evidence = (None, None, None)
        if ordinal in (0, 17):
            kind = 'sink' if ordinal == 0 else 'spring'
            station = stations[0 if kind == 'sink' else -1]
            port = ports[kind]
            frame = plane_frame(station['origin_xyz_m'], port['flow_unit_xz'], common)
            attachment = attachments['attachments'][kind]
            proof = attachment['actual_complete_port_proof']
            if proof['midpoint_port_identity_sha256'] != port['identity_sha256'] or sorted((segment['profile_segment_index'] for segment in proof['segments'])) != [0, 1, 2] or (not attachment['half_arm_triangle_indices']) or any((not segment['pieces'] for segment in proof['segments'])):
                raise ValueError('unknown_incomplete_original_canonical_attachment')
            canonical = canonical_floor(port, frame)
            binding = {'kind': kind, 'canonical_port_pin': attachment['canonical_port_pin'], 'surface_node_pin': attachment['surface_node_pin'], 'port_identity_sha256': port['identity_sha256'], 'actual_complete_port_proof': proof, 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'canonical_profile_uv_m': canonical, 'hydraulic_boundary_certified': False}
            evidence = {'composition_audit_pin': audit_pin, 'kind': kind, 'two_sided_complete_port_verified': bool(composition_audit.get('two_sided_complete_port_verified', False) and composition_audit.get('portal_reports', {}).get(kind, {}).get('verified', False) and composition_audit.get('portal_reports', {}).get(kind, {}).get('two_sided_complete_port_verified', False)), 'independent_port_report': composition_audit.get('portal_reports', {}).get(kind), 'composition_portal_connection': composition['portal_connections'].get(kind), 'no_endcap_deleted': True, 'offset_traces_are_diagnostic_only': True}
            orientation = {'canonical_station_id': station['station_id'], 'flow_unit_xz': port['flow_unit_xz']}
            rule = 'immutable_canonical_shared_port_with_audited_actual_two_sided_volume'
        else:
            first, second = (stations[ordinal - 1], stations[ordinal])
            if (link['from_cell_id'], link['to_cell_id']) != (first['station_id'], second['station_id']):
                raise ValueError('original_link_station_order_mismatch')
            first_point, second_point = (_i6_np.asarray(first['origin_xyz_m']), _i6_np.asarray(second['origin_xyz_m']))
            frame = plane_frame((first_point + second_point) / 2, (second_point - first_point)[[0, 2]], common)
            orientation = {'station_ids': [first['station_id'], second['station_id']], 'station_origin_world_xyz_m': [first_point.tolist(), second_point.tolist()]}
            rule = 'actual_adjacent_station_midpoint_XZ_flow_plane'
        if [cells[key]['roughness_manning'] for key in (link['from_cell_id'], link['to_cell_id'])] != [0.035, 0.035] or not _i6_math.isfinite(link['length_m']) or link['length_m'] <= 0:
            raise ValueError('unknown_original_roughness_or_link_length')
        record = {'schema': HYBRID_RIVER_FACES_MECHANISM_2_FACE_SCHEMA, 'face_id': 'face:' + str(ordinal), 'link_id': link['link_id'], 'from_cell_id': link['from_cell_id'], 'to_cell_id': link['to_cell_id'], 'plane': frame, 'plane_rule': rule, 'orientation_witness': orientation, 'roughness_manning': 0.035, 'roughness_source_cell_ids': [link['from_cell_id'], link['to_cell_id']], 'length_m': link['length_m'], 'length_source': 'unchanged_original_geometry_hydraulic_link', 'roughness_binding_only_not_new_face_friction_certification': True, 'length_binding_only_not_resistance_length_certification': True, 'numerical_slice_policy': composition['numerical_slice_policy'], 'numerical_slice_policy_identity_sha256': composition['numerical_slice_policy_identity_sha256'], 'additional_step_loss': None, 'shared_port_binding': binding, 'status': 'candidate', 'rejection_reasons': [], 'hydraulic_use': {'status': 'needs_info', 'discharge_computed': False, 'unknown_loss_is_not_zero': True, 'unknown_geometry_is_not_closed_zero_flow': True, 'required': ['independent_actual_face_geometry_passed', 'explicit_face_roughness_adoption', 'explicit_quasi_steady_resistance_length_policy', 'explicit_step_contraction_expansion_loss_policy']}}
        try:
            slices, shapes = ({}, {})
            for name, solid in solids.items():
                slices[name], shapes[name] = hybrid_mesh_plane_mechanism_2_slice_solid(solid, frame, pins[name])
                if slices[name]['schema'] != 'td-hybrid-exact-mesh-plane-slice-v2' or slices[name]['numerical_policy'] != composition['numerical_slice_policy'] or slices[name]['numerical_policy_identity_sha256'] != HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256 or (slices[name]['display_projection_certified'] is not True) or (not _i6_math.isfinite(slices[name]['projection_area_error_bound_m2'])) or (not 0 <= slices[name]['projection_area_error_bound_m2'] <= AREA_TOLERANCE_M2):
                    raise ValueError('actual_slice_numerical_policy_differs_from_audited_composition')
            record['solid_slices'] = slices
            roles = [role_slice(source, frame) for source in role_sources]
            roles = [source for source in roles if source['triangle_segments'] or source['coplanar_triangle_supports']]
            if any((source['numerical_policy_identity_sha256'] != composition['numerical_slice_policy_identity_sha256'] for source in roles)):
                raise ValueError('source_role_exact_slice_policy_differs_from_composition')
            record['source_role_slices'] = roles
            record['aperture'] = hybrid_river_faces_mechanism_2_classify_aperture(slices, shapes, roles, frame, canonical, evidence)
        except ValueError as error:
            record.update(status='refused', rejection_reasons=[str(error)], unknown_geometry_not_zero_flow=True)
        faces.append(seal(record))
        guard()
    refused = [face['face_id'] for face in faces if face['status'] != 'candidate']
    return seal({'schema': HYBRID_RIVER_FACES_MECHANISM_2_SCHEMA, 'status': 'refused' if refused else 'candidate_unverified', 'faces': faces, 'face_count': len(faces), 'rejection_reasons': refused, 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': geometry['graph_identity_sha256'], 'composition_identity_sha256': composition['identity_sha256'], 'policy': HYBRID_RIVER_FACES_MECHANISM_2_POLICY, 'policy_identity_sha256': HYBRID_RIVER_FACES_MECHANISM_2_POLICY_SHA256, 'stage_lineage': composition['stage_lineage'], 'numerical_slice_policy': composition['numerical_slice_policy'], 'numerical_slice_policy_identity_sha256': composition['numerical_slice_policy_identity_sha256'], 'independent_audit_passed': False, 'hydraulic_solved': False, 'water_discharge_computed': False, 'storage_geometry_changed': False, 'pressure_slot_enlarges_face': False, 'native_exact': False, 'actual_peak_rss_bytes': guard()})

# Source: terrain_pipeline.hybrid_rock_boolean
HYBRID_ROCK_BOOLEAN_SCHEMA = 'td-hybrid-rock-boolean-v1'

# Source: terrain_pipeline.hybrid_rock_boolean
RESULT_SCHEMA = 'td-hybrid-rock-boolean-result-v1'

# Source: terrain_pipeline.hybrid_rock_boolean
ALGORITHM = 'arbitrary-closed-rock-minus-closed-cutter-set-v1'

# Source: terrain_pipeline.hybrid_rock_boolean
RELATION = 'generalises_the_excavation_step_of_td-hybrid-river-geometry-v1_without_replacing_recomputing_or_editing_it'

# Source: terrain_pipeline.hybrid_rock_boolean
SOLID_SCHEMA = 'td-hybrid-local-solid-mesh-v1'

# Source: terrain_pipeline.hybrid_rock_boolean
MAX_COMPONENTS = 1024

# Source: terrain_pipeline.hybrid_rock_boolean
FLAGS = ('independent_audit_passed', 'hydraulic_ready', 'natural_outlet_certified', 'full_network_verified', 'self_intersection_verified', 'publishable')

# Source: terrain_pipeline.hybrid_rock_boolean
HYBRID_ROCK_BOOLEAN_POLICY = {'version': 'local-arbitrary-rock-boolean-v1', 'rock': 'caller_supplied_closed_solid_sampled_or_analytic_never_native_exact', 'cutters': 'caller_supplied_closed_solid_set_united_then_subtracted_actual_volume', 'assembly': 'caller_supplied_closed_solid_union_disconnected_components_allowed', 'excavation': 'Mesh64_local_origin_closed_rock_minus_closed_union_actual_volume', 'water': 'not_generated_solid_banks_distinct_from_free_water', 'protection': 'no_clamping_no_implicit_fill_no_hidden_truncation_refusal_only', 'conduit_scope': 'untouched_not_recomputed_and_not_reidentified_here', 'certification': 'candidate_only_every_capability_flag_written_false'}

# Source: terrain_pipeline.hybrid_rock_boolean
HYBRID_ROCK_BOOLEAN_POLICY_SHA256 = identity(HYBRID_ROCK_BOOLEAN_POLICY)

# Source: terrain_pipeline.hybrid_rock_boolean
CONDUIT_POLICY_SHA256 = '10287323bb7fbb835d2e8de6c6e03720454b2c1538e606e09764c872ca67604b'

# Source: terrain_pipeline.hybrid_rock_boolean
@_i8_dataclass(frozen=True)
class BooleanParameters:
    """Bounded explicit parameters; no default is a measurement or a certification."""
    solids_spacing_m: float = 1.0
    component_limit: int = 64
    balance_relative_tolerance: float = 1e-10

    def __post_init__(self):
        if type(self.solids_spacing_m) is not float or not _i8_math.isfinite(self.solids_spacing_m) or (not 0.05 <= self.solids_spacing_m <= 8.0):
            raise ValueError('bounded positive solid sampling spacing required')
        if type(self.component_limit) is not int or not 1 <= self.component_limit <= MAX_COMPONENTS:
            raise ValueError('bounded integer component limit required')
        if type(self.balance_relative_tolerance) is not float or not _i8_math.isfinite(self.balance_relative_tolerance) or (not 1e-15 <= self.balance_relative_tolerance <= 1e-06):
            raise ValueError('bounded relative balance tolerance required')

# Source: terrain_pipeline.hybrid_rock_boolean
class _Library:
    """Lazy pinned manifold3d accessor; the module imports no Boolean engine at import time."""

    @staticmethod
    def get():
        import manifold3d as manifold
        return manifold

# Source: terrain_pipeline.hybrid_rock_boolean
MANIFOLD = _Library

# Source: terrain_pipeline.hybrid_rock_boolean
def _origin(origin):
    origin = _i8_np.asarray(origin, float)
    if origin.shape != (3,) or not _i8_np.isfinite(origin).all():
        raise ValueError('finite three-component local origin required')
    return origin

# Source: terrain_pipeline.hybrid_rock_boolean
def _parameters(parameters):
    if not isinstance(parameters, BooleanParameters):
        raise ValueError('explicit BooleanParameters required')
    return parameters

# Source: terrain_pipeline.hybrid_rock_boolean
def positive_int(value, label):
    if type(value) is not int or not 1 <= value <= MAX_COMPONENTS:
        raise ValueError('bounded integer ' + label + ' required')
    return value

# Source: terrain_pipeline.hybrid_rock_boolean
def solid_from_record(record, label):
    """Validate one saved closed-solid record and return its pinned MESH64 solid.

    Every input is also volume-checked against the saved ``signed_volume_m3``: a record
    whose JSON volume disagrees with the reconstructed closed mesh is refused rather than
    quietly used as a Boolean operand.
    """
    if not isinstance(record, dict) or record.get('schema') != SOLID_SCHEMA or record.get('sampled_not_native_exact') is not True:
        raise ValueError('saved closed solid mesh record required for ' + label)
    if not isinstance(record.get('role'), str) or not record['role']:
        raise ValueError('explicit solid role required for ' + label)
    if len(record.get('vertices_local_xyz_m', [])) < 4 or len(record.get('triangles', [])) < 4:
        raise ValueError('degenerate closed solid record for ' + label)
    solid = manifold_from_record(record)
    if 'signed_volume_m3' not in record:
        raise ValueError('saved signed solid volume required for ' + label)
    _volume_gate(record, solid, label)
    return solid

# Source: terrain_pipeline.hybrid_rock_boolean
def census(solid):
    return len(solid.decompose())

# Source: terrain_pipeline.hybrid_rock_boolean
def _status_gate(solid, label):
    library = _Library.get()
    if solid.status() != library.Error.NoError or solid.is_empty():
        raise ValueError('closed solid ' + label + ' failed or is empty')

# Source: terrain_pipeline.hybrid_rock_boolean
def _volume_gate(record, solid, label):
    saved, actual = (float(record['signed_volume_m3']), float(solid.volume()))
    if not _i8_math.isfinite(saved) or not _i8_math.isfinite(actual) or saved <= 0.0:
        raise ValueError('nonpositive saved volume for ' + label)
    if abs(saved - actual) > max(1e-07, actual * 1e-09):
        raise ValueError('saved mesh volume disagrees with MESH64 volume for ' + label)

# Source: terrain_pipeline.hybrid_rock_boolean
def _component_gate(count, minimum, maximum, label):
    if count < minimum:
        raise ValueError(label + ' has fewer connected components than declared')
    if count > maximum:
        raise ValueError(label + ' exceeds the explicit component limit')
    return count

# Source: terrain_pipeline.hybrid_rock_boolean
def _pin(record):
    return {'role': record['role'], 'identity_sha256': record['identity_sha256'], 'signed_volume_m3': record['signed_volume_m3']}

# Source: terrain_pipeline.hybrid_rock_boolean
def _common(parameters, origin, operation):
    record = {'schema': RESULT_SCHEMA, 'status': 'candidate', 'rejection_reasons': [], 'algorithm': ALGORITHM, 'relation': RELATION, 'operation': operation, 'policy': HYBRID_ROCK_BOOLEAN_POLICY, 'policy_identity_sha256': HYBRID_ROCK_BOOLEAN_POLICY_SHA256, 'parameters': _i8_asdict(parameters), 'parameters_identity_sha256': identity(_i8_asdict(parameters)), 'local_origin_xyz_m': origin.tolist(), 'conduit_policy_identity_sha256': CONDUIT_POLICY_SHA256, 'parent_algorithm': 'td-hybrid-river-geometry-v1_conduit_step_untouched_not_recomputed', 'sampled_not_native_exact': True, 'fine15_replaced': False, 'water_generated': False, 'fill_rock_m3': 0.0}
    for flag in FLAGS:
        record[flag] = False
    return record

# Source: terrain_pipeline.hybrid_rock_boolean
def combine(records, origin, role, parameters, *, minimum_components=1):
    """Union caller-supplied closed solids into one closed record (gaps stay outside).

    ``minimum_components`` is the caller's own claim about the result (for example a rock
    egg pile must stay disconnected); it is refused rather than adjusted when unmet.
    """
    origin = _origin(origin)
    parameters = _parameters(parameters)
    positive_int(minimum_components, 'minimum component count')
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError('at least one closed input solid required')
    if not isinstance(role, str) or not role:
        raise ValueError('explicit result role required')
    library = _Library.get()
    solids = [solid_from_record(record, 'input ' + str(ordinal)) for ordinal, record in enumerate(records)]
    for ordinal, solid in enumerate(solids):
        _status_gate(solid, 'input ' + str(ordinal))
    union = library.Manifold.batch_boolean(solids, library.OpType.Add)
    _status_gate(union, 'assembled union')
    fence = _component_gate(census(union), minimum_components, parameters.component_limit, 'assembled union')
    assembly = save_manifold(union, origin, role)
    _volume_gate(assembly, union, 'assembled union')
    result = _common(parameters, origin, 'closed_solid_union_no_cutter')
    result.update({'inputs': {'solids': [_pin(record) for record in records]}, 'census': {'input_solids': len(records), 'assembled_components': fence, 'component_limit': parameters.component_limit, 'minimum_components_declared': minimum_components}, 'material': {'assembled_volume_m3': union.volume(), 'excavated_rock_m3': 0.0, 'exported_excavated_rock_m3': 0.0, 'signed_residual_m3': 0.0}, 'mesh_pins': {role: {'identity_sha256': assembly['identity_sha256'], 'signed_volume_m3': assembly['signed_volume_m3']}}, 'gates': {'each_input_closed_two_use_manifold': True, 'each_input_saved_volume_matches_mesh': True, 'assembled_closed_two_use_manifold': True, 'mesh_volume_matches_manifold_volume': True, 'component_census_within_limit': True, 'no_cutter_applied': True, 'no_clamping_no_implicit_fill': True}, 'refusals': 'open_or_degenerate_inputs_declared_component_shortfall_and_component_limit_excess_are_refused'})
    seal(result)
    hybrid_cave_geometry_guard()
    return (result, {role: assembly})

# Source: terrain_pipeline.hybrid_rock_boolean
def excavate(rock_record, cutter_records, parameters, origin, *, minimum_removed_components=1, minimum_rock_after_components=1):
    """Subtract an explicit closed cutter set from one closed rock body.

    Both the unified cutter set and the excavated void are saved as closed solid records,
    so tunnel/void volume is independently re-checkable. Disjoint cutters are allowed; the
    void may legitimately consist of several separated cavities.
    """
    origin = _origin(origin)
    parameters = _parameters(parameters)
    positive_int(minimum_removed_components, 'minimum removed component count')
    positive_int(minimum_rock_after_components, 'minimum remaining rock component count')
    if not isinstance(cutter_records, (list, tuple)) or not cutter_records:
        raise ValueError('explicit closed cutter set required; use combine for a cutter-free union')
    library = _Library.get()
    rock = solid_from_record(rock_record, 'rock')
    _status_gate(rock, 'rock')
    cutters = [solid_from_record(record, 'cutter ' + str(ordinal)) for ordinal, record in enumerate(cutter_records)]
    for ordinal, cutter in enumerate(cutters):
        _status_gate(cutter, 'cutter ' + str(ordinal))
    union = library.Manifold.batch_boolean(cutters, library.OpType.Add)
    _status_gate(union, 'unified cutter set')
    cutter_census = _component_gate(census(union), 1, parameters.component_limit, 'unified cutter set')
    after = rock - union
    removed = rock ^ union
    _status_gate(after, 'remaining rock')
    _status_gate(removed, 'excavated void')
    if after.volume() <= 0.0 or removed.volume() <= 0.0:
        raise ValueError('excavation refused: no positive remaining rock and excavated void volume')
    residual = rock.volume() - after.volume() - removed.volume()
    budget = max(1e-07, rock.volume() * parameters.balance_relative_tolerance)
    if abs(residual) > budget:
        raise ValueError('actual closed solid material balance failed')
    floor = _component_gate(census(after), minimum_rock_after_components, parameters.component_limit, 'remaining rock')
    void = _component_gate(census(removed), minimum_removed_components, parameters.component_limit, 'excavated void')
    rock_after = save_manifold(after, origin, 'rock_after')
    removed_record = save_manifold(removed, origin, 'removed')
    union_record = save_manifold(union, origin, 'cutter_union')
    for record, solid, label in ((rock_after, after, 'remaining rock'), (removed_record, removed, 'excavated void'), (union_record, union, 'unified cutter set')):
        _volume_gate(record, solid, label)
    result = _common(parameters, origin, 'rock_minus_closed_cutter_union')
    result.update({'inputs': {'rock': _pin(rock_record), 'cutters': [_pin(record) for record in cutter_records]}, 'census': {'rock_before_components': census(rock), 'cutter_union_components': cutter_census, 'rock_after_components': floor, 'removed_components': void, 'cutter_count': len(cutters), 'component_limit': parameters.component_limit, 'minimum_removed_components_declared': minimum_removed_components, 'minimum_rock_after_components_declared': minimum_rock_after_components}, 'material': {'rock_before_m3': rock.volume(), 'rock_after_m3': after.volume(), 'excavated_rock_m3': removed.volume(), 'exported_excavated_rock_m3': removed.volume(), 'fill_rock_m3': 0.0, 'signed_residual_m3': residual, 'balance_budget_m3': budget}, 'mesh_pins': {name: {'identity_sha256': record['identity_sha256'], 'signed_volume_m3': record['signed_volume_m3']} for name, record in (('rock_after', rock_after), ('removed', removed_record), ('cutter_union', union_record))}, 'gates': {'input_closed_two_use_manifold': True, 'input_saved_volume_matches_mesh': True, 'unified_cutter_closed_two_use_manifold': True, 'remaining_and_void_closed_two_use_manifold': True, 'mesh_volume_matches_manifold_volume': True, 'actual_volume_balance': True, 'positive_remaining_and_void_volume': True, 'component_census_within_limit': True, 'no_clamping_no_implicit_fill': True, 'no_silent_truncation': True}, 'refusals': 'open_or_degenerate_inputs_disjoint_or_empty_cutters_consumed_rock_and_declared_component_shortfall_are_refused'})
    seal(result)
    hybrid_cave_geometry_guard()
    return (result, {'rock_after': rock_after, 'removed': removed_record, 'cutter_union': union_record})

# Source: terrain_pipeline.hybrid_rock_boolean
def octagon_ring(centre_xz, radius_x_m, radius_z_m, segments):
    """Deterministic regular ring for prisms/frusta; counter-clockwise in the (x, z) plane."""
    centre_xz = _i8_np.asarray(centre_xz, float)
    if centre_xz.shape != (2,) or not _i8_np.isfinite(centre_xz).all():
        raise ValueError('finite ring centre required')
    if type(segments) is not int or not 3 <= segments <= 4096:
        raise ValueError('bounded integer ring segment count required')
    for value in (radius_x_m, radius_z_m):
        if type(value) is not float or not _i8_math.isfinite(value) or value <= 0.0:
            raise ValueError('bounded positive ring radii required')
    angles = _i8_np.arange(segments) * (2.0 * _i8_math.pi / segments)
    return centre_xz + _i8_np.column_stack((radius_x_m * _i8_np.cos(angles), radius_z_m * _i8_np.sin(angles)))

# Source: terrain_pipeline.hybrid_rock_boolean
def _ring(polygon_xz, label):
    ring = _i8_np.asarray(polygon_xz, float)
    if ring.ndim != 2 or ring.shape[1] != 2 or len(ring) < 3 or (not _i8_np.isfinite(ring).all()):
        raise ValueError('finite closed polygon with at least three points required for ' + label)
    if len(_i8_np.unique(ring, axis=0)) != len(ring):
        raise ValueError('repeated polygon point refused for ' + label)
    area = float(_i8_np.sum(ring[:, 0] * _i8_np.roll(ring[:, 1], -1) - _i8_np.roll(ring[:, 0], -1) * ring[:, 1]) / 2.0)
    if abs(area) < 1e-12:
        raise ValueError('degenerate polygon area refused for ' + label)
    return ring if area > 0.0 else ring[::-1]

# Source: terrain_pipeline.hybrid_rock_boolean
def polygon_prism_record(polygon_xz, bottom_y_m, top_y_m, origin, role, *, maximum_vertices=200000):
    """Closed vertical prism over an explicit simple polygon (shaft walls, terraces, tunnels).

    The ring is normalised counter-clockwise and the caps are triangulated by the pinned
    MESH64 triangulator, so the closed two-use manifold gate is decided by geometry rather
    than by hand-chosen winding.
    """
    origin = _origin(origin)
    ring = _ring(polygon_xz, 'prism')
    bottom, top = (float(bottom_y_m), float(top_y_m))
    if not (_i8_math.isfinite(bottom) and _i8_math.isfinite(top)) or top - bottom <= 0.0:
        raise ValueError('strict positive prism height required')
    library = _Library.get()
    count = len(ring)
    if 2 * count > maximum_vertices:
        raise ValueError('prism vertex budget exceeded before triangulation')
    vertices = [[point[0] - origin[0], bottom - origin[1], point[1] - origin[2]] for point in ring]
    vertices += [[point[0] - origin[0], top - origin[1], point[1] - origin[2]] for point in ring]
    triangles = []
    for ordinal in range(count):
        following = (ordinal + 1) % count
        triangles.extend(([ordinal, following, count + following], [ordinal, count + following, count + ordinal]))
    for triangle in library.triangulate([ring], allow_convex=False):
        first, second, third = (int(index) for index in triangle)
        triangles.append([count + first, count + second, count + third])
        triangles.append([third, second, first])
    if len(vertices) > maximum_vertices:
        raise ValueError('prism vertex budget exceeded')
    return mesh_record(vertices, triangles, origin, role)

# Source: terrain_pipeline.hybrid_rock_boolean
def frustum_record(bottom_centre_xz, top_centre_xz, bottom_y_m, top_y_m, radius_bottom_m, radius_top_m, origin, role, *, segments=64, maximum_vertices=200000):
    """Closed circular frustum between two explicit centres (funnel walls, flared bases)."""
    origin = _origin(origin)
    bottom_ring = _ring(octagon_ring(bottom_centre_xz, radius_bottom_m, radius_bottom_m, segments), 'frustum base')
    top_ring = _ring(octagon_ring(top_centre_xz, radius_top_m, radius_top_m, segments), 'frustum top')
    bottom, top = (float(bottom_y_m), float(top_y_m))
    if not (_i8_math.isfinite(bottom) and _i8_math.isfinite(top)) or top - bottom <= 0.0:
        raise ValueError('strict positive frustum height required')
    count = segments
    if 2 * count + 2 > maximum_vertices:
        raise ValueError('frustum vertex budget exceeded')
    vertices = [[point[0] - origin[0], bottom - origin[1], point[1] - origin[2]] for point in bottom_ring]
    vertices += [[point[0] - origin[0], top - origin[1], point[1] - origin[2]] for point in top_ring]
    base_centre = len(vertices)
    vertices.append([bottom_centre_xz[0] - origin[0], bottom - origin[1], bottom_centre_xz[1] - origin[2]])
    top_centre = len(vertices)
    vertices.append([top_centre_xz[0] - origin[0], top - origin[1], top_centre_xz[1] - origin[2]])
    triangles = []
    for ordinal in range(count):
        following = (ordinal + 1) % count
        triangles.extend(([ordinal, following, count + following], [ordinal, count + following, count + ordinal]))
        triangles.append([top_centre, count + ordinal, count + following])
        triangles.append([base_centre, following, ordinal])
    return mesh_record(vertices, triangles, origin, role)

# Source: terrain_pipeline.hybrid_rock_boolean
def sphere_record(centre_xyz_m, radius_m, origin, role, *, circular_segments=48):
    """Closed geodesic sphere (stacked egg bodies); the pinned engine owns the mesh."""
    origin = _origin(origin)
    centre = _i8_np.asarray(centre_xyz_m, float)
    if centre.shape != (3,) or not _i8_np.isfinite(centre).all():
        raise ValueError('finite sphere centre required')
    if type(radius_m) is not float or not _i8_math.isfinite(radius_m) or radius_m <= 0.0:
        raise ValueError('bounded positive sphere radius required')
    if type(circular_segments) is not int or not 4 <= circular_segments <= 512:
        raise ValueError('bounded integer sphere segment count required')
    library = _Library.get()
    solid = library.Manifold.sphere(radius_m, circular_segments).translate(tuple(centre - origin))
    _status_gate(solid, 'sphere')
    return save_manifold(solid, origin, role)

# Source: terrain_pipeline.hybrid_surface_prisms
HYBRID_SURFACE_PRISMS_POLICY = {'version': 'saved-native-halfarm-prism-composition-v1', 'operation': 'original_sampled_rock_minus_union_immutable_gallery_and_surface_prisms', 'floor': 'saved_native_patch_bilinear_minus_saved_affine_cut_at_vertices_piecewise_planar', 'entity_domain': 'original_saved_native_patch_polygon_authority_including_recorded_clip_roundoff_not_resnapped_fan', 'canonical': 'whole_original_native_piece_linear_boundary_match_not_four_point_only', 'approximation': 'not_native_exact_not_fine15_material_no_resampling_or_double_depth_cut', 'top': 'explicit_common_horizontal_cap_above_all_saved_rock_and_gallery_vertices', 'material': 'original_removed_plus_disjoint_extra_removed_equals_total_no_fill', 'portal': 'full_supported_shared_interface_and_exact_unblocked_polygon_offsets_diagnostic_only', 'hydraulics': 'not_solved_no_discharge_or_resistance_law_acceptance'}

# Source: terrain_pipeline.hybrid_surface_prisms
def hybrid_surface_prisms_exact_depth(fan, point):
    vertices = fan['vertices_xz_m']
    if any((not _i15_math.isfinite(depth) or not 0.0 <= depth <= 4.0 for depth in fan['depth_at_vertices_m'])):
        raise ValueError('strict_invalid_saved_vertex_depth')
    for vertex, depth in zip(vertices, fan['depth_at_vertices_m']):
        if list(point) == vertex:
            if not 0.0 <= depth <= 4.0:
                raise ValueError('strict_invalid_saved_vertex_depth')
            return float(depth)
    coordinates = [[_i15_Fraction(float(value)) for value in vertex] for vertex in vertices]
    query = [_i15_Fraction(float(value)) for value in point]
    first = [coordinates[1][axis] - coordinates[0][axis] for axis in range(2)]
    second = [coordinates[2][axis] - coordinates[0][axis] for axis in range(2)]
    relative = [query[axis] - coordinates[0][axis] for axis in range(2)]
    determinant = first[0] * second[1] - first[1] * second[0]
    if determinant == 0:
        raise ValueError('degenerate_saved_native_fan')
    weight_first = (relative[0] * second[1] - relative[1] * second[0]) / determinant
    weight_second = (first[0] * relative[1] - first[1] * relative[0]) / determinant
    weights = [1 - weight_first - weight_second, weight_first, weight_second]
    if min(weights) < 0:
        raise ValueError('point_outside_exact_saved_fan')
    depth = _i15_math.fsum((float(weight) * value for weight, value in zip(weights, fan['depth_at_vertices_m'])))
    if not 0.0 <= depth <= 4.0:
        raise ValueError('strict_negative_or_maxcut_depth_no_clamp')
    return depth

# Source: terrain_pipeline.hybrid_surface_prisms
def hybrid_surface_prisms_native_height(patch, point):
    origin = patch['patch_origin_m_xz']
    spacing = patch['native_spacing_m']
    if not _i15_math.isfinite(spacing) or spacing <= 0:
        raise ValueError('invalid_native_patch_spacing')
    local = (_i15_np.asarray(point) - origin) / spacing
    coefficients = patch['bilinear_coefficients_m']
    return float(coefficients[0] + coefficients[1] * local[0] + coefficients[2] * local[1] + coefficients[3] * local[0] * local[1])

# Source: terrain_pipeline.hybrid_surface_prisms
def hybrid_surface_prisms_saved_patch_depth(fan, point):
    if any((not _i15_math.isfinite(depth) or not 0.0 <= depth <= 4.0 for depth in fan['depth_at_vertices_m'])):
        raise ValueError('strict_invalid_saved_vertex_depth')
    for vertex, depth in zip(fan['vertices_xz_m'], fan['depth_at_vertices_m']):
        if list(point) == vertex:
            return float(depth)
    coefficients = fan['depth_coefficients_m_1xz']
    relative = _i15_np.asarray(point) - fan['depth_origin_xz_m']
    depth = _i15_math.fsum([coefficients[0], coefficients[1] * relative[0], coefficients[2] * relative[1]])
    if not _i15_math.isfinite(depth) or not 0.0 <= depth <= 4.0:
        raise ValueError('strict_saved_patch_affine_depth_no_clamp')
    return float(depth)

# Source: terrain_pipeline.hybrid_surface_prisms
def hybrid_surface_prisms_triangular_prism(bottom_xyz, cap_y, origin):
    bottom = _i15_np.asarray(bottom_xyz, dtype=float)
    if bottom.shape != (3, 3) or not _i15_np.isfinite(bottom).all() or cap_y <= bottom[:, 1].max():
        raise ValueError('invalid_surface_prism_floor_or_cap')
    if _i15_Polygon(bottom[:, [0, 2]]).area <= 0:
        raise ValueError('degenerate_surface_prism_projection')
    top = bottom.copy()
    top[:, 1] = cap_y
    vertices = _i15_np.vstack((bottom, top)) - origin
    triangles = [[0, 2, 1], [3, 4, 5], [0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4], [2, 0, 3], [2, 3, 5]]
    return mesh_record(vertices, triangles, origin, 'surface_half_arm_closed_triangular_prism')

# Source: terrain_pipeline.hybrid_surface_prisms
def hybrid_surface_prisms_half_arm_prisms(node, attachment, cap_y, origin):
    if node['status'] != 'candidate' or node['rejection_reasons']:
        raise ValueError('original_surface_node_not_accepted_candidate')
    ids = attachment['half_arm_triangle_indices']
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('missing_or_duplicate_original_half_arm_triangles')
    wanted = {'shared:' + node['node_id'] + ':' + str(ordinal) for ordinal in ids}
    for ordinal in ids:
        if not isinstance(ordinal, int) or not 0 <= ordinal < len(node['geometry']['triangles']):
            raise ValueError('invalid_original_half_arm_triangle_reference')
        role = node['geometry']['triangle_roles'][ordinal]
        if role['region'] != 'half_arm' or role['arc_id'] != attachment['actual_complete_port_proof']['arc_id']:
            raise ValueError('half_arm_source_role_or_actual_arc_mismatch')
    compact = {fan['fan_key']: fan for fan in attachment['compact_native_fans']}
    functions = [function for function in node['source_functions'] if function['triangle_id'] in wanted]
    if {function['triangle_id'] for function in functions} != wanted:
        raise ValueError('incomplete_original_half_arm_function_sources')
    bottoms, solids = ([], [])
    for function in functions:
        if function['status'] != 'candidate' or function['rejection_reasons']:
            raise ValueError('refused_original_half_arm_function')
        for source_fan in function['fans']:
            fan = compact.get(source_fan['fan_id'])
            if fan is None or any((fan[key] != source_fan[key] for key in ('vertices_xz_m', 'depth_at_vertices_m', 'depth_coefficients_m_1xz', 'depth_origin_xz_m'))):
                raise ValueError('compact_and_original_native_fan_mismatch')
            polygon = _i15_Polygon(fan['vertices_xz_m'])
            patches = source_fan['native_patches']
            domains = [_i15_Polygon(patch['polygon_xz_m']) for patch in patches]
            if not polygon.is_valid or any((not domain.is_valid for domain in domains)) or polygon.symmetric_difference(_i15_unary_union(domains)).area > 1e-08 or (abs(sum((domain.area for domain in domains)) - polygon.area) > 1e-08):
                raise ValueError('native_patch_domain_gap_or_overlap')
            for patch, domain in zip(patches, domains):
                triangles = [triangle for triangle in _i15_triangulate(domain) if domain.covers(triangle)]
                if abs(sum((triangle.area for triangle in triangles)) - domain.area) > 1e-08:
                    raise ValueError('whole_native_patch_triangulation_gap')
                for triangle in triangles:
                    horizontal = [list(point) for point in list(triangle.exterior.coords)[:3]]
                    depths = [hybrid_surface_prisms_saved_patch_depth(fan, point) for point in horizontal]
                    domain_witnesses = []
                    for point in horizontal:
                        try:
                            hybrid_surface_prisms_exact_depth(fan, point)
                            inside = True
                        except ValueError as error:
                            if str(error) != 'point_outside_exact_saved_fan':
                                raise
                            inside = False
                        domain_witnesses.append({'point_xz_m': point, 'inside_original_fan_exact_domain': inside, 'entity_domain_authority': 'original_saved_native_patch_polygon', 'clip_point_not_snapped': True})
                    bottom = [[point[0], hybrid_surface_prisms_native_height(patch, point) - depth, point[1]] for point, depth in zip(horizontal, depths)]
                    prism = hybrid_surface_prisms_triangular_prism(bottom, cap_y, origin)
                    solids.append(manifold_from_record(prism))
                    bottoms.append({'bottom_triangle_id': len(bottoms), 'triangle_id': function['triangle_id'], 'fan_key': fan['fan_key'], 'source_function_identity_sha256': function['identity_sha256'], 'bottom_vertices_xyz_m': bottom, 'depth_at_vertices_m': depths, 'saved_native_patch': patch, 'saved_affine_fan': source_fan, 'saved_patch_vertex_domain_witnesses': domain_witnesses, 'prism': prism, 'prism_triangle_roles': ['floor', 'artificial_top_cap'] + ['lateral'] * 6, 'bilinear_interior_is_planar_approximation': True, 'conservative_interior_height_error_bound_m': float(abs(patch['bilinear_coefficients_m'][3]) * _i15_np.ptp(_i15_np.asarray(horizontal)[:, 0]) * _i15_np.ptp(_i15_np.asarray(horizontal)[:, 1]) / patch['native_spacing_m'] ** 2)})
    if not bottoms or sum((len(item['prism']['triangles']) for item in bottoms)) > MAX_TRIANGLES:
        raise ValueError('whole_surface_prism_budget_or_missing_sources')
    guard()
    return (bottoms, solids)

# Source: terrain_pipeline.hybrid_surface_prisms
def hybrid_surface_prisms_canonical_boundary_witness(attachment, bottoms, ring, flow, kind):
    proof = attachment['actual_complete_port_proof']
    if not proof['segments'] or not attachment['half_arm_triangle_indices']:
        raise ValueError('missing_complete_original_port_proof')
    origin = _i15_np.asarray(ring[0], dtype=float)[[0, 2]]
    normal = _i15_np.asarray(flow, dtype=float)
    normal /= _i15_np.linalg.norm(normal)
    side = -1.0 if kind == 'sink' else 1.0
    witnesses = []
    for segment in proof['segments']:
        for piece in segment['pieces']:
            expected = piece['bed_coefficients_m_t012']
            if expected[2] != 0.0:
                raise ValueError('quadratic_canonical_requires_exact_new_geometry')
            start, end = (_i15_np.asarray(piece['start_xz_m']), _i15_np.asarray(piece['end_xz_m']))
            vector = end - start
            length = float(_i15_np.linalg.norm(vector))
            if length <= TOLERANCE_M:
                raise ValueError('degenerate_canonical_piece')
            intervals = []
            for bottom in bottoms:
                vertices = _i15_np.asarray(bottom['bottom_vertices_xyz_m'])
                for first, second in zip(vertices, _i15_np.roll(vertices, -1, axis=0)):
                    horizontal = _i15_np.array([first[[0, 2]], second[[0, 2]]])
                    fractions = (horizontal - start) @ vector / (length * length)
                    distances = _i15_np.linalg.norm(horizontal - (start + fractions[:, None] * vector), axis=1)
                    if max(distances) > TOLERANCE_M or abs(fractions[1] - fractions[0]) * length <= TOLERANCE_M:
                        continue
                    lower, upper = (max(0.0, float(min(fractions))), min(1.0, float(max(fractions))))
                    if (upper - lower) * length <= TOLERANCE_M:
                        continue
                    slope = float((second[1] - first[1]) / (fractions[1] - fractions[0]))
                    intercept = float(first[1] - slope * fractions[0])
                    error = max(abs(intercept - expected[0]), abs(intercept + slope - expected[0] - expected[1]))
                    if error > TOLERANCE_M:
                        raise ValueError('whole_canonical_piece_floor_mismatch')
                    signed = side * ((vertices[:, [0, 2]] - origin) @ normal)
                    if min(signed) < -TOLERANCE_M or max(signed) <= TOLERANCE_M:
                        raise ValueError('surface_port_support_not_actual_exterior_half_arm')
                    intervals.append({'interval_t01': [lower, upper], 'bottom_triangle_id': bottom['bottom_triangle_id'], 'fan_key': bottom['fan_key'], 'edge_xyz_m': [first.tolist(), second.tolist()], 'actual_bed_coefficients_m_t012': [intercept, slope, 0.0], 'maximum_whole_linear_error_m': error, 'exterior_support_distance_m': float(max(signed))})
            cursor = 0.0
            for item in sorted(intervals, key=lambda value: value['interval_t01']):
                lower, upper = item['interval_t01']
                if (lower - cursor) * length > TOLERANCE_M:
                    raise ValueError('canonical_whole_piece_boundary_gap')
                cursor = max(cursor, upper)
            if (1.0 - cursor) * length > TOLERANCE_M:
                raise ValueError('canonical_whole_piece_boundary_missing')
            witnesses.append({'original_piece': piece, 'full_interval_t01': [0.0, 1.0], 'supports': intervals})
    floor = _i15_LineString([_i15_np.asarray(point)[[0, 2]] for point in ring])
    original = _i15_LineString([_i15_np.asarray(point)[[0, 2]] for point in proof['original_profile_xyz_m']])
    if floor.hausdorff_distance(original) > TOLERANCE_M:
        raise ValueError('immutable_gallery_floor_horizontal_port_mismatch')
    return witnesses

# Source: terrain_pipeline.hybrid_surface_material
def hybrid_surface_material_volume_ledger(before, old_after, old_removed, after, removed, extra):
    values = {'original_rock_before_m3': float(before.volume()), 'original_removed_m3': float(old_removed.volume()), 'original_rock_after_m3': float(old_after.volume()), 'total_removed_m3': float(removed.volume()), 'extra_removed_m3': float(extra.volume()), 'new_rock_after_m3': float(after.volume()), 'fill_m3': 0.0}
    residuals = [values['original_rock_before_m3'] - values['original_rock_after_m3'] - values['original_removed_m3'], values['original_rock_before_m3'] - values['new_rock_after_m3'] - values['total_removed_m3'], values['total_removed_m3'] - values['original_removed_m3'] - values['extra_removed_m3']]
    tolerance = max(1e-07, values['original_rock_before_m3'] * 1e-10)
    if max(map(abs, residuals)) > tolerance:
        raise ValueError('signed_original_total_extra_material_balance_failed')
    values.update(signed_residuals_m3=residuals, residual_tolerance_m3=tolerance, fine15_material_replaced=False, sampled_solid_material_not_native_exact=True)
    return values

# Source: terrain_pipeline.hybrid_surface_material
def hybrid_surface_material_saved_sampling_mismatch_witnesses(sampling, attachments, ports):
    witnesses = []
    for kind in ('sink', 'spring'):
        attachment = attachments['attachments'][kind]
        triangle_ids = {'shared:' + fan['node_id'] + ':' + str(ordinal) for fan in attachment['compact_native_fans'][:1] for ordinal in attachment['half_arm_triangle_indices']}
        fans = [fan for fan in attachment['compact_native_fans'] if fan['triangle_id'] in triangle_ids]
        midpoint = _i14_np.asarray(ports[kind]['midpoint_xz_m'])
        flow = _i14_np.asarray(ports[kind]['flow_unit_xz'])
        for sample in sampling['samples']:
            point = sample['xz_m']
            if abs(float((_i14_np.asarray(point) - midpoint) @ flow)) > TOLERANCE_M:
                continue
            hits = []
            for fan in fans:
                vertices = _i14_np.asarray(fan['vertices_xz_m'])
                if _i14_np.any(_i14_np.asarray(point) < vertices.min(axis=0)) or _i14_np.any(_i14_np.asarray(point) > vertices.max(axis=0)):
                    continue
                try:
                    depth = hybrid_surface_prisms_exact_depth(fan, point)
                except ValueError as error:
                    if str(error) == 'point_outside_exact_saved_fan':
                        continue
                    raise
                hits.append({'fan_key': fan['fan_key'], 'exact_domain_cut_depth_m': depth, 'saved_vertices_xz_m': fan['vertices_xz_m'], 'saved_vertex_depths_m': fan['depth_at_vertices_m']})
            if not hits:
                continue
            depths = [hit['exact_domain_cut_depth_m'] for hit in hits]
            if max(depths) - min(depths) > 1e-09:
                raise ValueError('independent_exact_saved_fan_shared_depth_mismatch')
            if abs(depths[0] - sample['cut_depth_m']) > 1e-09:
                witnesses.append({'kind': kind, 'source_sampling_row': sample['row'], 'source_sampling_column': sample['column'], 'point_xz_m': point, 'saved_cut_depth_m': sample['cut_depth_m'], 'saved_fan_keys': sample['fan_keys'], 'saved_derived_bed_m': sample['derived_bed_m'], 'saved_original_source_sample': sample['source_sample'], 'exact_domain_supports': hits, 'expected_cut_depth_m': depths[0], 'sampled_top_excess_height_m': depths[0] - sample['cut_depth_m'], 'classification': 'saved_cut_lookup_mismatch_exact_domain_not_source_height_recalculation', 'scope': 'only_saved_port_plane_grid_samples_no_global_source_claim'})
    return witnesses

# Source: terrain_pipeline.hybrid_surface_boolean_stage
HYBRID_SURFACE_BOOLEAN_STAGE_SCHEMA = 'td-hybrid-surface-boolean-stage-current-v1'

# Source: terrain_pipeline.hybrid_surface_boolean_stage
HYBRID_SURFACE_BOOLEAN_STAGE_POLICY = {**HYBRID_SURFACE_PRISMS_POLICY, 'version': 'original-main-boolean-stage-current-v1', 'numerical_slice': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256, 'failure': 'Boolean-stage-preserved-before-any-rational-portal-check'}

# Source: terrain_pipeline.hybrid_surface_boolean_stage
HYBRID_SURFACE_BOOLEAN_STAGE_POLICY_SHA256 = identity(HYBRID_SURFACE_BOOLEAN_STAGE_POLICY)

# Source: terrain_pipeline.hybrid_surface_boolean_stage
def build_boolean_stage(geometry, vdm, attachments, ports, meshes, nodes, sampling):
    import manifold3d as manifold
    origin = _i9_np.asarray(meshes['rock_before']['local_origin_xyz_m'])
    if any((record['local_origin_xyz_m'] != origin.tolist() for record in meshes.values())):
        raise ValueError('saved_mesh_common_local_origin_mismatch')
    vertices = _i9_np.array([station['derived_ring_xyz_m'] for station in vdm['stations']]).reshape(-1, 3) - origin
    if not _i9_np.array_equal(vertices, meshes['cutter']['vertices_local_xyz_m']) or vdm['triangles'] != meshes['cutter']['triangles']:
        raise ValueError('immutable_vdm_original_cutter_array_mismatch')
    cap_y = max((max((point[1] for point in meshes[name]['vertices_local_xyz_m'])) + origin[1] for name in ('rock_before', 'cutter'))) + 10.0
    surface_solids, surface_records, connections = ([], {}, {})
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        attachment = attachments['attachments'][kind]
        bottoms, parts = hybrid_surface_prisms_half_arm_prisms(nodes[kind], attachment, cap_y, origin)
        station = vdm['stations'][ordinal]
        witnesses = hybrid_surface_prisms_canonical_boundary_witness(attachment, bottoms, station['derived_ring_xyz_m'][:station['floor_vertex_count']], ports[kind]['flow_unit_xz'], kind)
        surface_solids.extend(parts)
        surface_records[kind] = {'node_id': nodes[kind]['node_id'], 'node_pin': attachment['surface_node_pin'], 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'bottom_triangles': bottoms, 'immutable_gallery_station_index': ordinal, 'immutable_gallery_ring_xyz_m': station['derived_ring_xyz_m'], 'canonical_whole_piece_witnesses': witnesses}
        connections[kind] = {'canonical_whole_piece_witnesses': witnesses, 'immutable_gallery_station_index': ordinal, 'original_complete_port_proof': attachment['actual_complete_port_proof'], 'full_shared_interface_supported': True, 'offset_traces_are_diagnostic_only': True}
    surface = manifold.Manifold.batch_boolean(surface_solids, manifold.OpType.Add)
    before, cutter, old_after, old_removed = (manifold_from_record(meshes[name]) for name in ('rock_before', 'cutter', 'rock_after', 'removed'))
    coupled = cutter + surface
    after, removed, extra = (before - coupled, before ^ coupled, old_after ^ surface)
    if any((solid.status() != manifold.Error.NoError for solid in (surface, coupled, after, removed, extra))):
        raise ValueError('surface_composition_boolean_failed')
    if any((solid.is_empty() for solid in (surface, coupled, after, removed))):
        raise ValueError('missing_surface_composition_solid')
    artifacts = {name: save_manifold(solid, origin, name) for name, solid in (('surface_cutter', surface), ('coupled_cutter', coupled), ('rock_after', after), ('removed', removed))}
    artifacts['extra_removed'] = save_manifold(extra, origin, 'extra_removed') if not extra.is_empty() else seal({'schema': 'td-hybrid-empty-solid-v1', 'role': 'extra_removed', 'local_origin_xyz_m': origin.tolist(), 'vertices_local_xyz_m': [], 'triangles': [], 'signed_volume_m3': 0.0})
    artifacts['surface_prisms'] = seal({'schema': 'td-hybrid-surface-prisms-v1', 'common_local_origin_xyz_m': origin.tolist(), 'cap_y_world_m': cap_y, 'cap_above_saved_rock_and_gallery_margin_m': 10.0, 'half_arms': surface_records, 'bottom_semantics': HYBRID_SURFACE_PRISMS_POLICY['floor'], 'native_exact': False})
    result = {'schema': HYBRID_SURFACE_BOOLEAN_STAGE_SCHEMA, 'status': 'boolean_stage_unverified', 'rejection_reasons': [], 'policy': HYBRID_SURFACE_BOOLEAN_STAGE_POLICY, 'policy_identity_sha256': HYBRID_SURFACE_BOOLEAN_STAGE_POLICY_SHA256, 'numerical_slice_policy': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256, 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': geometry['graph_identity_sha256'], 'material': hybrid_surface_material_volume_ledger(before, old_after, old_removed, after, removed, extra), 'coupled_cutter_component_count': len(coupled.decompose()), 'original_source_sampling_cut_lookup_mismatches': hybrid_surface_material_saved_sampling_mismatch_witnesses(sampling, attachments, ports), 'original_sampled_rock_retained_cut_only_not_source_resampling': True, 'vdm_moved': False, 'ports_moved': False, 'fill_generated': False, 'native_exact': False, 'fine15_replaced': False, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False, 'full_network_verified': False}
    for name, record in artifacts.items():
        if name != 'surface_prisms' and len(record['triangles']) > MAX_TRIANGLES:
            raise ValueError('whole_composition_triangle_budget_exceeded')
    return (seal(result), artifacts)

# Source: terrain_pipeline.hybrid_surface_composition
HYBRID_SURFACE_COMPOSITION_SCHEMA = 'td-hybrid-surface-composition-v1'

# Source: terrain_pipeline.hybrid_surface_composition
HYBRID_SURFACE_COMPOSITION_POLICY_SHA256 = identity(HYBRID_SURFACE_PRISMS_POLICY)

# Source: terrain_pipeline.hybrid_surface_composition
def build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling):
    import manifold3d as manifold
    origin = _i10_np.asarray(meshes['rock_before']['local_origin_xyz_m'], dtype=float)
    if any((record['local_origin_xyz_m'] != origin.tolist() for record in meshes.values())):
        raise ValueError('saved_mesh_common_local_origin_mismatch')
    immutable_vertices = _i10_np.array([station['derived_ring_xyz_m'] for station in vdm['stations']]).reshape(-1, 3) - origin
    if not _i10_np.array_equal(immutable_vertices, _i10_np.asarray(meshes['cutter']['vertices_local_xyz_m'])) or vdm['triangles'] != meshes['cutter']['triangles']:
        raise ValueError('immutable_vdm_original_cutter_array_mismatch')
    cap_y = max((max((point[1] for point in meshes[name]['vertices_local_xyz_m'])) + origin[1] for name in ('rock_before', 'cutter'))) + 10.0
    surface_solids, surface_records, connections = ([], {}, {})
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        attachment = attachments['attachments'][kind]
        bottoms, solids = hybrid_surface_prisms_half_arm_prisms(nodes[kind], attachment, cap_y, origin)
        station = vdm['stations'][ordinal]
        floor_ring = station['derived_ring_xyz_m'][:station['floor_vertex_count']]
        witnesses = hybrid_surface_prisms_canonical_boundary_witness(attachment, bottoms, floor_ring, ports[kind]['flow_unit_xz'], kind)
        surface_records[kind] = {'node_id': nodes[kind]['node_id'], 'node_pin': attachment['surface_node_pin'], 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'bottom_triangles': bottoms, 'immutable_gallery_station_index': ordinal, 'immutable_gallery_ring_xyz_m': station['derived_ring_xyz_m'], 'canonical_whole_piece_witnesses': witnesses}
        surface_solids.extend(solids)
        connections[kind] = {'canonical_whole_piece_witnesses': witnesses, 'immutable_gallery_station_index': ordinal, 'original_complete_port_proof': attachment['actual_complete_port_proof'], 'full_shared_interface_supported': True, 'offset_traces_are_diagnostic_only': True}
    surface = manifold.Manifold.batch_boolean(surface_solids, manifold.OpType.Add)
    before, cutter, old_after, old_removed = (manifold_from_record(meshes[name]) for name in ('rock_before', 'cutter', 'rock_after', 'removed'))
    coupled = cutter + surface
    after, removed, extra = (before - coupled, before ^ coupled, old_after ^ surface)
    for solid in (surface, coupled, after, removed, extra):
        if solid.status() != manifold.Error.NoError:
            raise ValueError('surface_composition_boolean_failed')
    if any((solid.is_empty() for solid in (surface, coupled, after, removed))):
        raise ValueError('missing_surface_composition_solid')
    component_count = len(coupled.decompose())
    if component_count != 1:
        raise ValueError('surface_gallery_coupled_cutter_not_one_component')
    artifacts = {'surface_cutter': save_manifold(surface, origin, 'surface_cutter'), 'coupled_cutter': save_manifold(coupled, origin, 'coupled_cutter'), 'rock_after': save_manifold(after, origin, 'rock_after'), 'removed': save_manifold(removed, origin, 'total_removed')}
    if extra.is_empty():
        artifacts['extra_removed'] = seal({'schema': 'td-hybrid-empty-solid-v1', 'role': 'extra_removed', 'local_origin_xyz_m': origin.tolist(), 'vertices_local_xyz_m': [], 'triangles': [], 'signed_volume_m3': 0.0})
    else:
        artifacts['extra_removed'] = save_manifold(extra, origin, 'extra_removed')
    for name, record in artifacts.items():
        if len(record['triangles']) > MAX_TRIANGLES:
            raise ValueError('whole_composition_triangle_budget_exceeded')
    solids = {'coupled_cutter': coupled, 'rock_after': after, 'removed': removed}
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        station = vdm['stations'][ordinal]
        normal = ports[kind]['flow_unit_xz']
        frame = plane_frame(station['origin_xyz_m'], normal, origin)
        diagnostics, shapes = ({}, {})
        for name, solid in solids.items():
            mesh = solid.to_mesh64()
            record, shape = hybrid_river_faces_slice_solid((solid, _i10_np.array(mesh.vert_properties[:, :3]), _i10_np.array(mesh.tri_verts)), frame, {'artifact': name})
            diagnostics[name], shapes[name] = (record, shape)
        gallery_ring = _i10_np.asarray(station['derived_ring_xyz_m'])
        horizontal = (gallery_ring[:, [0, 2]] - _i10_np.asarray(station['origin_xyz_m'])[[0, 2]]) @ _i10_np.asarray(frame['transverse_unit_xz'])
        aperture = _i10_Polygon(_i10_np.column_stack((horizontal, gallery_ring[:, 1] - origin[1])))
        blocked = float(aperture.intersection(shapes['rock_after']).area)
        missing = float(aperture.difference(shapes['coupled_cutter']).area)
        if not aperture.is_valid or blocked > 1e-08 or missing > 1e-08:
            raise ValueError('actual_full_canonical_port_blocked_or_missing:' + kind)
        epsilon = min(0.001, min((item['exterior_support_distance_m'] for witness in connections[kind]['canonical_whole_piece_witnesses'] for item in witness['supports'])) / 16.0)
        basis = _i10_np.array([frame['transverse_unit_xyz'], frame['vertical_unit_xyz'], frame['normal_local_xyz']]).T
        bounds = aperture.bounds
        width, height = (bounds[2] - bounds[0], bounds[3] - bounds[1])
        center = _i10_np.array(frame['origin_local_xyz_m']) + _i10_np.array(frame['transverse_unit_xyz']) * ((bounds[0] + bounds[2]) / 2.0)
        center[1] = (bounds[1] + bounds[3]) / 2.0
        half_collars, collar_proofs = ([], {})
        surface_sign = -1.0 if kind == 'sink' else 1.0
        for side_name, side_solid, sign in (('surface', surface, surface_sign), ('gallery', cutter, -surface_sign)):
            slab_center = center + sign * epsilon / 2.0 * _i10_np.array(frame['normal_local_xyz'])
            slab = manifold.Manifold.cube([width, height, epsilon], center=True).transform(_i10_np.column_stack((basis, slab_center)).tolist())
            collar = side_solid ^ slab
            if collar.is_empty() or collar.volume() <= 0 or len(collar.decompose()) != 1:
                raise ValueError('missing_positive_volume_full_port_collar:' + kind + ':' + side_name)
            mesh = collar.to_mesh64()
            collar_slice, collar_domain = hybrid_river_faces_slice_solid((collar, _i10_np.array(mesh.vert_properties[:, :3]), _i10_np.array(mesh.tri_verts)), frame, {'artifact': kind + '_' + side_name + '_collar'})
            uncovered = float(aperture.difference(collar_domain).area)
            if uncovered > 1e-08:
                raise ValueError('whole_port_not_covered_by_both_volume_collars:' + kind + ':' + side_name)
            name = kind + '_' + side_name + '_collar'
            artifacts[name] = save_manifold(collar, origin, name)
            collar_proofs[side_name] = {'artifact': name, 'positive_volume_m3': float(collar.volume()), 'whole_aperture_uncovered_area_m2': uncovered, 'interface_solid_slice': collar_slice, 'source_solid': 'surface_cutter' if side_name == 'surface' else 'original_cutter', 'normal_side_sign': sign, 'slab_width_height_depth_m': [width, height, epsilon], 'slab_transform_3x4': _i10_np.column_stack((basis, slab_center)).tolist()}
            half_collars.append(collar)
        connected_collar = half_collars[0] + half_collars[1]
        rock_overlap = float((connected_collar ^ after).volume())
        if len(connected_collar.decompose()) != 1 or rock_overlap > 1e-07:
            raise ValueError('actual_full_port_volume_collar_disconnected_or_blocked:' + kind)
        artifacts[kind + '_connected_collar'] = save_manifold(connected_collar, origin, kind + '_connected_collar')
        traces = []
        for offset in (-epsilon, -epsilon / 2.0, epsilon / 2.0, epsilon):
            displaced = _i10_np.asarray(station['origin_xyz_m']) + offset * _i10_np.asarray(frame['normal_local_xyz'])
            shifted_frame = plane_frame(displaced, normal, origin)
            trace = {'offset_m': offset, 'plane': shifted_frame, 'solid_slices': {}}
            for name, solid in solids.items():
                mesh = solid.to_mesh64()
                record, _ = hybrid_river_faces_slice_solid((solid, _i10_np.array(mesh.vert_properties[:, :3]), _i10_np.array(mesh.tri_verts)), shifted_frame, {'artifact': name})
                trace['solid_slices'][name] = record
            traces.append(trace)
        connections[kind].update(plane=frame, exact_solid_slices=diagnostics, one_sided_diagnostic_traces=traces, epsilon_rule='min_1mm_and_minimum_actual_exterior_support_distance_div16', gallery_aperture_uv_m=list(map(list, aperture.exterior.coords))[:-1], exact_blocked_area_m2=blocked, exact_missing_cutter_area_m2=missing, positive_volume_connection={'sides': collar_proofs, 'connected_collar_artifact': kind + '_connected_collar', 'component_count': 1, 'actual_rock_overlap_volume_m3': rock_overlap, 'constructed_by_intersecting_actual_cutters_not_new_excavation': True}, hydraulic_boundary_certified=False)
    artifacts['surface_prisms'] = seal({'schema': 'td-hybrid-surface-prisms-v1', 'common_local_origin_xyz_m': origin.tolist(), 'cap_y_world_m': cap_y, 'cap_above_saved_rock_and_gallery_margin_m': 10.0, 'half_arms': surface_records, 'bottom_semantics': HYBRID_SURFACE_PRISMS_POLICY['floor'], 'native_exact': False})
    result = seal({'schema': HYBRID_SURFACE_COMPOSITION_SCHEMA, 'status': 'candidate_unverified', 'rejection_reasons': [], 'policy': HYBRID_SURFACE_PRISMS_POLICY, 'policy_identity_sha256': HYBRID_SURFACE_COMPOSITION_POLICY_SHA256, 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': geometry['graph_identity_sha256'], 'portal_connections': connections, 'coupled_cutter_component_count': component_count, 'material': hybrid_surface_material_volume_ledger(before, old_after, old_removed, after, removed, extra), 'original_source_sampling_cut_lookup_mismatches': hybrid_surface_material_saved_sampling_mismatch_witnesses(sampling, attachments, ports), 'original_sampled_rock_retained_cut_only_not_source_resampling': True, 'vdm_moved': False, 'ports_moved': False, 'fill_generated': False, 'native_exact': False, 'fine15_replaced': False, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False, 'full_network_verified': False, 'actual_peak_rss_bytes': guard()})
    return (result, artifacts)

# Source: terrain_pipeline.hybrid_surface_composition_v2
HYBRID_SURFACE_COMPOSITION_MECHANISM_2_SCHEMA = 'td-hybrid-surface-composition-v2'

# Source: terrain_pipeline.hybrid_surface_composition_v2
HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY = {**HYBRID_SURFACE_PRISMS_POLICY, 'version': 'saved-native-halfarm-prism-composition-v2', 'numerical_slice': NUMERICAL_POLICY_SHA256, 'failure': 'saved_boolean_stage_and_material_before_port_checks_port_failure_preserves_artifacts'}

# Source: terrain_pipeline.hybrid_surface_composition_v2
HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY_SHA256 = identity(HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY)

# Source: terrain_pipeline.hybrid_surface_composition_v2
def _solid_slice(solid, frame, name):
    mesh = solid.to_mesh64()
    data = (solid, _i11_np.array(mesh.vert_properties[:, :3]), _i11_np.array(mesh.tri_verts))
    record, shape = slice_solid(data, frame, {'artifact': name})
    return (data, record, shape)

# Source: terrain_pipeline.hybrid_surface_composition_v2
def _domain(shape):
    polygons, lines, points = ([], [], [])
    pending = [shape]
    while pending:
        item = pending.pop()
        if item.is_empty:
            continue
        if item.geom_type == 'Polygon':
            polygons.append(item)
        elif item.geom_type in ('LineString', 'LinearRing'):
            lines.append(list(map(list, item.coords)))
        elif item.geom_type == 'Point':
            points.append(list(item.coords[0]))
        elif item.geom_type in ('MultiPolygon', 'MultiLineString', 'MultiPoint', 'GeometryCollection'):
            pending.extend(reversed(list(item.geoms)))
        else:
            raise ValueError('unsupported_port_domain_geometry:' + item.geom_type)
    return {'polygons_uv_m': [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons], 'holes_uv_m': [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in polygons], 'contact_lines_uv_m': lines, 'contact_points_uv_m': points, 'area_m2': float(shape.area)}

# Source: terrain_pipeline.hybrid_surface_composition_v2
def _portal(kind, station, port, connection, solids, surface, cutter, after, origin, artifacts):
    import manifold3d as manifold
    frame = plane_frame(station['origin_xyz_m'], port['flow_unit_xz'], origin)
    ring = _i11_np.asarray(station['derived_ring_xyz_m'])
    horizontal = (ring[:, [0, 2]] - _i11_np.asarray(station['origin_xyz_m'])[[0, 2]]) @ _i11_np.asarray(frame['transverse_unit_xz'])
    aperture = _i11_Polygon(_i11_np.column_stack((horizontal, ring[:, 1] - origin[1])))
    connection.update(plane=frame, gallery_aperture_uv_m=list(map(list, aperture.exterior.coords))[:-1], exact_solid_slices={}, legacy_quantization_diagnostics={}, hydraulic_boundary_certified=False, two_sided_complete_port_verified=False)
    if not aperture.is_valid:
        raise ValueError('invalid_immutable_port_aperture')
    shapes = {}
    for name, solid in solids.items():
        data, record, shapes[name] = _solid_slice(solid, frame, name)
        connection['exact_solid_slices'][name] = record
        try:
            old_record, old_shape = hybrid_river_faces_slice_solid(data, frame, {'artifact': name})
            connection['legacy_quantization_diagnostics'][name] = {'legacy_method': old_record['method'], 'legacy_domain': _domain(old_shape), 'legacy_vs_exact_symmetric_difference_area_m2': float(old_shape.symmetric_difference(shapes[name]).area), 'legacy_blocked_or_missing_area_m2': float(aperture.intersection(old_shape).area if name == 'rock_after' else aperture.difference(old_shape).area), 'acceptance_use': False}
        except ValueError as error:
            connection['legacy_quantization_diagnostics'][name] = {'diagnostic_error': str(error), 'acceptance_use': False}
    blocked = aperture.intersection(shapes['rock_after'])
    missing = aperture.difference(shapes['coupled_cutter'])
    connection.update(exact_blocked_area_m2=float(blocked.area), exact_missing_cutter_area_m2=float(missing.area), blocked_domain=_domain(blocked), missing_domain=_domain(missing))
    if blocked.area > 1e-08 or missing.area > 1e-08:
        raise ValueError('actual_full_canonical_port_blocked_or_missing:' + kind)
    epsilon = min(0.001, min((item['exterior_support_distance_m'] for witness in connection['canonical_whole_piece_witnesses'] for item in witness['supports'])) / 16.0)
    connection['epsilon_rule'] = 'min_1mm_and_minimum_actual_exterior_support_distance_div16'
    basis = _i11_np.array([frame['transverse_unit_xyz'], frame['vertical_unit_xyz'], frame['normal_local_xyz']]).T
    bounds = aperture.bounds
    width, height = (bounds[2] - bounds[0], bounds[3] - bounds[1])
    center = _i11_np.array(frame['origin_local_xyz_m']) + _i11_np.array(frame['transverse_unit_xyz']) * ((bounds[0] + bounds[2]) / 2.0)
    center[1] = (bounds[1] + bounds[3]) / 2.0
    half_collars = []
    proof = {'sides': {}, 'constructed_by_intersecting_actual_cutters_not_new_excavation': True}
    connection['positive_volume_connection'] = proof
    surface_sign = -1.0 if kind == 'sink' else 1.0
    for side_name, side_solid, sign in (('surface', surface, surface_sign), ('gallery', cutter, -surface_sign)):
        name = kind + '_' + side_name + '_collar'
        slab_center = center + sign * epsilon / 2.0 * _i11_np.array(frame['normal_local_xyz'])
        transform = _i11_np.column_stack((basis, slab_center)).tolist()
        slab = manifold.Manifold.cube([width, height, epsilon], center=True).transform(transform)
        collar = side_solid ^ slab
        side = {'artifact': name, 'positive_volume_m3': float(collar.volume()), 'source_solid': 'surface_cutter' if side_name == 'surface' else 'original_cutter', 'normal_side_sign': sign, 'slab_width_height_depth_m': [width, height, epsilon], 'slab_transform_3x4': transform, 'component_count': len(collar.decompose())}
        proof['sides'][side_name] = side
        if not collar.is_empty():
            artifacts[name] = save_manifold(collar, origin, name)
        if collar.is_empty() or collar.volume() <= 0 or side['component_count'] != 1:
            raise ValueError('missing_positive_volume_full_port_collar:' + kind + ':' + side_name)
        _, record, domain = _solid_slice(collar, frame, name)
        gap = aperture.difference(domain)
        side.update(interface_solid_slice=record, whole_aperture_uncovered_area_m2=float(gap.area), uncovered_domain=_domain(gap))
        if gap.area > 1e-08:
            raise ValueError('whole_port_not_covered_by_both_volume_collars:' + kind + ':' + side_name)
        half_collars.append(collar)
    connected = half_collars[0] + half_collars[1]
    name = kind + '_connected_collar'
    artifacts[name] = save_manifold(connected, origin, name)
    overlap = float((connected ^ after).volume())
    proof.update(connected_collar_artifact=name, component_count=len(connected.decompose()), actual_rock_overlap_volume_m3=overlap)
    if proof['component_count'] != 1 or overlap > 1e-07:
        raise ValueError('actual_full_port_volume_collar_disconnected_or_blocked:' + kind)
    connection['one_sided_diagnostic_traces'] = []
    for offset in (-epsilon, -epsilon / 2.0, epsilon / 2.0, epsilon):
        displaced = _i11_np.asarray(station['origin_xyz_m']) + offset * _i11_np.asarray(frame['normal_local_xyz'])
        shifted = plane_frame(displaced, port['flow_unit_xz'], origin)
        trace = {'offset_m': offset, 'plane': shifted, 'solid_slices': {}}
        connection['one_sided_diagnostic_traces'].append(trace)
        for name, solid in solids.items():
            _, record, _ = _solid_slice(solid, shifted, name)
            trace['solid_slices'][name] = record
    connection['two_sided_complete_port_verified'] = True

# Source: terrain_pipeline.hybrid_surface_composition_v2
def hybrid_surface_composition_mechanism_2_build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling, save_stage=None):
    import manifold3d as manifold
    origin = _i11_np.asarray(meshes['rock_before']['local_origin_xyz_m'])
    if any((record['local_origin_xyz_m'] != origin.tolist() for record in meshes.values())):
        raise ValueError('saved_mesh_common_local_origin_mismatch')
    vertices = _i11_np.array([station['derived_ring_xyz_m'] for station in vdm['stations']]).reshape(-1, 3) - origin
    if not _i11_np.array_equal(vertices, meshes['cutter']['vertices_local_xyz_m']) or vdm['triangles'] != meshes['cutter']['triangles']:
        raise ValueError('immutable_vdm_original_cutter_array_mismatch')
    cap_y = max((max((point[1] for point in meshes[name]['vertices_local_xyz_m'])) + origin[1] for name in ('rock_before', 'cutter'))) + 10.0
    surface_solids, surface_records, connections = ([], {}, {})
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        attachment = attachments['attachments'][kind]
        bottoms, parts = hybrid_surface_prisms_half_arm_prisms(nodes[kind], attachment, cap_y, origin)
        station = vdm['stations'][ordinal]
        witnesses = hybrid_surface_prisms_canonical_boundary_witness(attachment, bottoms, station['derived_ring_xyz_m'][:station['floor_vertex_count']], ports[kind]['flow_unit_xz'], kind)
        surface_solids.extend(parts)
        surface_records[kind] = {'node_id': nodes[kind]['node_id'], 'node_pin': attachment['surface_node_pin'], 'half_arm_triangle_indices': attachment['half_arm_triangle_indices'], 'bottom_triangles': bottoms, 'immutable_gallery_station_index': ordinal, 'immutable_gallery_ring_xyz_m': station['derived_ring_xyz_m'], 'canonical_whole_piece_witnesses': witnesses}
        connections[kind] = {'canonical_whole_piece_witnesses': witnesses, 'immutable_gallery_station_index': ordinal, 'original_complete_port_proof': attachment['actual_complete_port_proof'], 'full_shared_interface_supported': True, 'offset_traces_are_diagnostic_only': True}
    surface = manifold.Manifold.batch_boolean(surface_solids, manifold.OpType.Add)
    before, cutter, old_after, old_removed = (manifold_from_record(meshes[name]) for name in ('rock_before', 'cutter', 'rock_after', 'removed'))
    coupled = cutter + surface
    after, removed, extra = (before - coupled, before ^ coupled, old_after ^ surface)
    if any((solid.status() != manifold.Error.NoError for solid in (surface, coupled, after, removed, extra))):
        raise ValueError('surface_composition_boolean_failed')
    if any((solid.is_empty() for solid in (surface, coupled, after, removed))):
        raise ValueError('missing_surface_composition_solid')
    artifacts = {name: save_manifold(solid, origin, name) for name, solid in (('surface_cutter', surface), ('coupled_cutter', coupled), ('rock_after', after), ('removed', removed))}
    artifacts['extra_removed'] = save_manifold(extra, origin, 'extra_removed') if not extra.is_empty() else seal({'schema': 'td-hybrid-empty-solid-v1', 'role': 'extra_removed', 'local_origin_xyz_m': origin.tolist(), 'vertices_local_xyz_m': [], 'triangles': [], 'signed_volume_m3': 0.0})
    artifacts['surface_prisms'] = seal({'schema': 'td-hybrid-surface-prisms-v1', 'common_local_origin_xyz_m': origin.tolist(), 'cap_y_world_m': cap_y, 'cap_above_saved_rock_and_gallery_margin_m': 10.0, 'half_arms': surface_records, 'bottom_semantics': HYBRID_SURFACE_PRISMS_POLICY['floor'], 'native_exact': False})
    result = {'schema': HYBRID_SURFACE_COMPOSITION_MECHANISM_2_SCHEMA, 'status': 'boolean_stage_unverified', 'rejection_reasons': [], 'policy': HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY, 'policy_identity_sha256': HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY_SHA256, 'numerical_slice_policy': NUMERICAL_POLICY, 'numerical_slice_policy_identity_sha256': NUMERICAL_POLICY_SHA256, 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': geometry['graph_identity_sha256'], 'material': hybrid_surface_material_volume_ledger(before, old_after, old_removed, after, removed, extra), 'coupled_cutter_component_count': len(coupled.decompose()), 'original_source_sampling_cut_lookup_mismatches': hybrid_surface_material_saved_sampling_mismatch_witnesses(sampling, attachments, ports), 'original_sampled_rock_retained_cut_only_not_source_resampling': True, 'vdm_moved': False, 'ports_moved': False, 'fill_generated': False, 'native_exact': False, 'fine15_replaced': False, 'independent_audit_passed': False, 'hydraulic_ready': False, 'hydraulic_solved': False, 'full_network_verified': False}
    for name, record in artifacts.items():
        if name != 'surface_prisms' and len(record['triangles']) > MAX_TRIANGLES:
            raise ValueError('whole_composition_triangle_budget_exceeded')
    if save_stage is not None:
        result['checkpoint_boolean_pin'] = save_stage(seal(dict(result)), artifacts)
    if result['coupled_cutter_component_count'] != 1:
        result['rejection_reasons'].append('surface_gallery_coupled_cutter_not_one_component')
    solids = {'coupled_cutter': coupled, 'rock_after': after, 'removed': removed}
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        connection = connections[kind]
        try:
            _portal(kind, vdm['stations'][ordinal], ports[kind], connection, solids, surface, cutter, after, origin, artifacts)
            connection.update(status='verified_geometry_unverified_audit', rejection_reasons=[])
        except ValueError as error:
            connection.update(status='refused', rejection_reasons=[str(error)], two_sided_complete_port_verified=False)
            result['rejection_reasons'].append(kind + ':' + str(error))
    result.update(portal_connections=connections, status='refused' if result['rejection_reasons'] else 'candidate_unverified', actual_peak_rss_bytes=guard(), boolean_stage_preserved=True)
    return (seal(result), artifacts)

# Source: terrain_pipeline.hybrid_surface_composition_v3
HYBRID_SURFACE_COMPOSITION_MECHANISM_3_SCHEMA = 'td-hybrid-surface-composition-v3'

# Source: terrain_pipeline.hybrid_surface_composition_v3
HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY = {**HYBRID_SURFACE_PRISMS_POLICY, 'version': 'saved-stage-rational-surface-composition-v3', 'numerical_slice': HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256, 'main_boolean': 'immutable_composition02_checkpoint_mesh_pins_material_and_extra_removed_not_recomputed', 'portal_boolean': 'bounded_collars_only_reuse_saved_collars_when_available', 'failure': 'saved_stage_lineage_material_and_partial_port_reports_preserved'}

# Source: terrain_pipeline.hybrid_surface_composition_v3
HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY_SHA256 = identity(HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY)

# Source: terrain_pipeline.hybrid_surface_composition_v3
def _slice(solid, record, frame, name):
    return hybrid_mesh_plane_mechanism_2_slice_solid((solid, _i12_np.asarray(record['vertices_local_xyz_m']), _i12_np.asarray(record['triangles'])), frame, {'artifact': name, 'identity_sha256': record['identity_sha256'], 'triangle_identity_authority': 'immutable_saved_record_arrays'})

# Source: terrain_pipeline.hybrid_surface_composition_v3
def _area_upper(area, bound):
    return _i12_math.nextafter(_i12_math.fsum((float(area), bound)), _i12_math.inf)

# Source: terrain_pipeline.hybrid_surface_composition_v3
def _hybrid_surface_composition_mechanism_3_portal(kind, station, port, connection, solids, meshes, origin, artifacts, reusable):
    import manifold3d as manifold
    frame = plane_frame(station['origin_xyz_m'], port['flow_unit_xz'], origin)
    ring = _i12_np.asarray(station['derived_ring_xyz_m'])
    horizontal = (ring[:, [0, 2]] - _i12_np.asarray(station['origin_xyz_m'])[[0, 2]]) @ _i12_np.asarray(frame['transverse_unit_xz'])
    aperture = _i12_Polygon(_i12_np.column_stack((horizontal, ring[:, 1] - origin[1])))
    connection.update(plane=frame, gallery_aperture_uv_m=list(map(list, aperture.exterior.coords))[:-1], exact_solid_slices={}, hydraulic_boundary_certified=False, two_sided_complete_port_verified=False)
    if not aperture.is_valid:
        raise ValueError('invalid_original_canonical_aperture')
    shapes = {}
    for name in ('coupled_cutter', 'rock_after', 'removed'):
        record, shapes[name] = _slice(solids[name], meshes[name], frame, name)
        connection['exact_solid_slices'][name] = record
    blocked, missing = (aperture.intersection(shapes['rock_after']), aperture.difference(shapes['coupled_cutter']))
    blocked_bound = connection['exact_solid_slices']['rock_after']['projection_area_error_bound_m2']
    missing_bound = connection['exact_solid_slices']['coupled_cutter']['projection_area_error_bound_m2']
    connection.update(exact_blocked_area_m2=float(blocked.area), exact_missing_cutter_area_m2=float(missing.area), blocked_domain=_domain(blocked), missing_domain=_domain(missing), blocked_area_upper_bound_m2=_area_upper(blocked.area, blocked_bound), missing_area_upper_bound_m2=_area_upper(missing.area, missing_bound))
    if connection['blocked_area_upper_bound_m2'] > 1e-08 or connection['missing_area_upper_bound_m2'] > 1e-08:
        raise ValueError('actual_full_canonical_port_blocked_or_missing:' + kind)
    depth = min(0.001, min((item['exterior_support_distance_m'] for witness in connection['canonical_whole_piece_witnesses'] for item in witness['supports'])) / 16.0)
    connection['epsilon_rule'] = 'min_1mm_and_minimum_actual_exterior_support_distance_div16'
    basis = _i12_np.array([frame['transverse_unit_xyz'], frame['vertical_unit_xyz'], frame['normal_local_xyz']]).T
    bounds = aperture.bounds
    width, height = (bounds[2] - bounds[0], bounds[3] - bounds[1])
    center = _i12_np.array(frame['origin_local_xyz_m']) + _i12_np.array(frame['transverse_unit_xyz']) * ((bounds[0] + bounds[2]) / 2.0)
    center[1] = (bounds[1] + bounds[3]) / 2.0
    collars = []
    proof = {'sides': {}, 'constructed_by_intersecting_actual_cutters_not_new_excavation': True}
    connection['positive_volume_connection'] = proof
    surface_sign = -1.0 if kind == 'sink' else 1.0
    for side_name, source, sign in (('surface', 'surface_cutter', surface_sign), ('gallery', 'original_cutter', -surface_sign)):
        name = kind + '_' + side_name + '_collar'
        slab_center = center + sign * depth / 2.0 * _i12_np.array(frame['normal_local_xyz'])
        transform = _i12_np.column_stack((basis, slab_center)).tolist()
        if name in reusable:
            collar = manifold_from_record(reusable[name])
            inherited = True
        else:
            slab = manifold.Manifold.cube([width, height, depth], center=True).transform(transform)
            collar = solids[source] ^ slab
            inherited = False
        side = {'artifact': name, 'positive_volume_m3': float(collar.volume()), 'source_solid': source, 'normal_side_sign': sign, 'slab_width_height_depth_m': [width, height, depth], 'slab_transform_3x4': transform, 'component_count': len(collar.decompose()), 'inherited_saved_collar': inherited}
        proof['sides'][side_name] = side
        if not collar.is_empty() and (not inherited):
            artifacts[name] = save_manifold(collar, origin, name)
        if collar.is_empty() or collar.volume() <= 0 or side['component_count'] != 1:
            raise ValueError('missing_positive_volume_collar:' + kind + ':' + side_name)
        record, shape = _slice(collar, reusable[name] if inherited else artifacts[name], frame, name)
        gap = aperture.difference(shape)
        bound = record['projection_area_error_bound_m2']
        side.update(interface_solid_slice=record, whole_aperture_uncovered_area_m2=float(gap.area), uncovered_area_upper_bound_m2=_area_upper(gap.area, bound), uncovered_domain=_domain(gap))
        if side['uncovered_area_upper_bound_m2'] > 1e-08:
            raise ValueError('whole_port_collar_coverage_failed:' + kind + ':' + side_name)
        collars.append(collar)
    name = kind + '_connected_collar'
    connected = manifold_from_record(reusable[name]) if name in reusable else collars[0] + collars[1]
    if name not in reusable:
        artifacts[name] = save_manifold(connected, origin, name)
    overlap = float((connected ^ solids['rock_after']).volume())
    proof.update(connected_collar_artifact=name, component_count=len(connected.decompose()), actual_rock_overlap_volume_m3=overlap)
    if proof['component_count'] != 1 or overlap > 1e-07:
        raise ValueError('whole_port_volume_disconnected_or_blocked:' + kind)
    connection.update(one_sided_diagnostic_traces=[], offset_traces_not_recomputed=True, two_sided_complete_port_verified=True)

# Source: terrain_pipeline.hybrid_surface_composition_v3
def resume_composition(stage, vdm, attachments, ports, meshes, prisms, lineage, reusable=None):
    origin = _i12_np.asarray(meshes['rock_after']['local_origin_xyz_m'])
    if any((record['local_origin_xyz_m'] != origin.tolist() for record in meshes.values())):
        raise ValueError('saved_stage_local_frame_changed')
    solids = {name: manifold_from_record(meshes[name]) for name in ('surface_cutter', 'coupled_cutter', 'rock_after', 'removed', 'original_cutter')}
    result = dict(stage)
    result.pop('identity_sha256', None)
    result.update(schema=HYBRID_SURFACE_COMPOSITION_MECHANISM_3_SCHEMA, policy=HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY, policy_identity_sha256=HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY_SHA256, numerical_slice_policy=HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY, numerical_slice_policy_identity_sha256=HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256, stage_lineage=lineage, main_boolean_recomputed=False, material_inherited_unchanged=True, portal_connections={}, rejection_reasons=[], boolean_stage_preserved=True)
    if stage['coupled_cutter_component_count'] != 1:
        result['rejection_reasons'].append('source_coupled_cutter_not_one_component')
    artifacts = {}
    for kind, ordinal in (('sink', 0), ('spring', len(vdm['stations']) - 1)):
        connection = {'canonical_whole_piece_witnesses': prisms['half_arms'][kind]['canonical_whole_piece_witnesses'], 'immutable_gallery_station_index': ordinal, 'original_complete_port_proof': attachments['attachments'][kind]['actual_complete_port_proof'], 'full_shared_interface_supported': True, 'offset_traces_are_diagnostic_only': True}
        result['portal_connections'][kind] = connection
        try:
            _hybrid_surface_composition_mechanism_3_portal(kind, vdm['stations'][ordinal], ports[kind], connection, solids, meshes, origin, artifacts, reusable or {})
            connection.update(status='verified_geometry_unverified_audit', rejection_reasons=[])
        except (ValueError, AttributeError, TypeError, OverflowError) as error:
            connection.update(status='refused', rejection_reasons=[type(error).__name__ + ':' + str(error)], two_sided_complete_port_verified=False)
            result['rejection_reasons'].append(kind + ':' + type(error).__name__ + ':' + str(error))
    result.update(status='refused' if result['rejection_reasons'] else 'candidate_unverified', actual_peak_rss_bytes=guard())
    return (seal(result), artifacts)
