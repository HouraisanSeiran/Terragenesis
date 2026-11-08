"""Consolidated export_hybrid_geometry_review implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i27_argparse
from io import BytesIO as _i27_BytesIO
import json as _i27_json
from pathlib import Path as _i27_Path
import sys as _i27_sys
import numpy as _i27_np
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i27_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import checked_path as _i27_checked_path
from tools.td_shared_channel_fine_saved_audit import check_memory as _i27_check_memory
from tools.td_shared_channel_fine_saved_audit import read as _i27_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i27_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i27_require
from tools.export_td_watershed_inspection import encoded as _i27_encoded
from tools.export_td_watershed_inspection import publish_directory as _i27_publish_directory
import argparse as _i28_argparse
import json as _i28_json
from pathlib import Path as _i28_Path
import sys as _i28_sys
import tempfile as _i28_tempfile
import time as _i28_time
import matplotlib as _i28_matplotlib
import matplotlib.pyplot as _i28_plt
from matplotlib.patches import Polygon as _i28_PolygonPatch
import numpy as _i28_np
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i28_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_memory as _i28_check_memory
from tools.td_shared_channel_fine_saved_audit import digest as _i28_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i28_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i28_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i28_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i28_require
CATEGORY = 'C'
ROOT = _i27_Path(__file__).resolve().parents[1]
_i27_sys.path.insert(0, str(ROOT))
SCHEMA = 'td-hybrid-cave-review-v1'
AUDIT_SCHEMA = 'td-hybrid-cave-geometry-independent-audit-v1'
MESH_NAMES = ('rock_before', 'cutter', 'rock_after', 'removed')

def load_review(geometry_path, geometry_sha256, audit_path=None, audit_sha256=None, audit_schema=AUDIT_SCHEMA):
    pin = {'path': str(_i27_Path(geometry_path).resolve()), 'sha256': geometry_sha256}
    geometry = _i27_read(pin)
    _i27_require(geometry['schema'] == 'td-hybrid-river-geometry-v1', 'unexpected saved geometry schema')
    graph = _i27_read(geometry['inputs']['graph'])
    _i27_require(graph['schema'] == 'td-hybrid-river-graph-v1' and graph['identity_sha256'] == geometry['graph_identity_sha256'], 'geometry graph identity differs')
    for source_pin in geometry['inputs'].values():
        _i27_checked_path(source_pin)
    _i27_require(all((geometry['inputs'].get(key) == value for key, value in graph['inputs'].items())), 'geometry omitted/altered typed graph parent')
    meshes = {}
    for name in MESH_NAMES:
        mesh = _i27_read(geometry['mesh_pins'][name])
        _i27_require(mesh['schema'] == 'td-hybrid-local-solid-mesh-v1', 'unexpected local solid schema')
        points = _i27_np.asarray(mesh['vertices_local_xyz_m'], float)
        faces = _i27_np.asarray(mesh['triangles'])
        origin = _i27_np.asarray(mesh['local_origin_xyz_m'], float)
        _i27_require(points.ndim == 2 and points.shape[1] == 3 and (len(points) <= 100000) and (origin.shape == (3,)) and _i27_np.isfinite(points).all() and _i27_np.isfinite(origin).all() and (faces.ndim == 2) and (faces.shape[1] == 3) and (0 < len(faces) <= 200000) and _i27_np.issubdtype(faces.dtype, _i27_np.integer) and (faces.min() >= 0) and (faces.max() < len(points)), 'invalid saved mesh references')
        meshes[name] = mesh
    vdm = _i27_read(geometry['vdm_pin'])
    _i27_require(vdm['schema'] == 'td-hybrid-multichart-vdm-v1', 'unexpected saved VDM schema')
    attachments = _i27_read(geometry['surface_attachments_pin'])
    native_pin = graph['inputs']['original_hierarchy']
    with _i27_np.load(_i27_checked_path(native_pin), allow_pickle=False) as archive:
        native_manifest = _i27_json.loads(bytes(archive['manifest']))
        height, valid = (archive['height_m'].copy(), archive['valid_mask'].copy())
    _i27_require(height.ndim == 2 and height.size <= 250000 and (valid.shape == height.shape) and _i27_np.isfinite(height).all(), 'invalid bounded native terrain')
    binding = {'binding_status': 'not_supplied', 'scope': 'reference to independent saved evidence only; exporter does not execute audit'}
    audit_pin = None
    if audit_path is not None or audit_sha256 is not None:
        _i27_require(audit_path is not None and audit_sha256 is not None, 'audit path and SHA required together')
        audit_pin = {'path': str(_i27_Path(audit_path).resolve()), 'sha256': audit_sha256}
        audit = _i27_read_audit(audit_pin)
        failures = []
        if audit.get('schema') != audit_schema:
            failures.append('schema')
        if audit.get('geometry_sha256') != geometry_sha256 or audit.get('graph_identity_sha256') != graph['identity_sha256']:
            failures.append('geometry_graph_binding')
        if audit.get('inputs') != geometry['inputs'] or audit.get('mesh_pins') != geometry['mesh_pins'] or audit.get('vdm_pin') != geometry['vdm_pin']:
            failures.append('source_mesh_vdm_binding')
        if audit.get('status') not in ('passed', 'failed') or not isinstance(audit.get('errors'), list):
            failures.append('status_errors')
        if audit.get('status') == 'passed' and (audit.get('errors') or audit.get('actual_hydraulic_sections_verified') is not True or audit.get('actual_portal_connections_verified') is not True):
            failures.append('passed_evidence')
        binding.update(binding_status='not_matched' if failures else 'matched', binding_failures=failures)
        if not failures:
            binding.update(referenced_status=audit['status'], errors=audit['errors'])
    portals = {node['kind']: node for node in graph['nodes'] if node['kind'] in ('sink', 'spring')}
    _i27_require(set(portals) == {'sink', 'spring'}, 'missing actual typed portals')
    origin = meshes['rock_after']['local_origin_xyz_m']
    review = {'schema': SCHEMA, 'geometry_identity_sha256': geometry['identity_sha256'], 'graph_identity_sha256': graph['identity_sha256'], 'pins': {'geometry': pin, 'graph': geometry['inputs']['graph'], 'inputs': geometry['inputs'], 'meshes': geometry['mesh_pins'], 'vdm': geometry['vdm_pin'], 'audit': audit_pin, 'source_sampling': geometry['source_sampling_pin'], 'surface_attachments': geometry['surface_attachments_pin']}, 'coordinates': {'convention': 'XYZ metres; Y elevation; XZ horizontal', 'plot_origin_xyz_m': origin, 'native_origin_m_xz': native_manifest['metadata']['origin_m_xz'], 'native_spacing_m': native_manifest['metadata']['spacing_m']}, 'meshes': meshes, 'stations': vdm['stations'], 'portals': portals, 'surface_attachments': attachments['attachments'], 'actual_closed_core_station_indices': geometry['actual_closed_core_station_indices'], 'hydraulic_cells': geometry['hydraulic_cells'], 'air_path_xyz_m': geometry['air_path_xyz_m'], 'independent_audit_reference': binding, 'native_terrain': {'height_m': height.tolist(), 'valid_mask': valid.tolist()}, 'limitations': ['Engineered local rock-minus-cave sample, not surveyed geology or full river.', 'Native terrain shown at original samples; local solid top is an explicitly sampled triangulation.', 'Remaining-rock transparency is display only, not evidence of a physical opening.', 'Removed solid and VDM outlines are geometry, not water.', 'Hydraulic sections alone do not certify hydraulic flow; no hydraulic state attached.', 'Frontend navigation pending; mesh artifact supplied without UI changes.'], 'hydraulic_solved': False, 'three_dimensional_flow_solved': False, 'full_network_verified': False, 'natural_outlet_certified': False}
    _i27_check_memory()
    return review

def caseartifact(review):
    saved = review['meshes']['rock_after']
    vertices = (_i27_np.asarray(saved['vertices_local_xyz_m']) + _i27_np.asarray(saved['local_origin_xyz_m'])).tolist()
    heights = [point[1] for point in vertices]
    return {'schema': 'td-hybrid-cave-mesh-case-v1', 'kind': 'mesh', 'caseId': 'hybrid-cave-' + review['geometry_identity_sha256'][:12], 'label': 'Saved actual remaining rock solid; engineered cave; no water', 'mesh': {'vertices': vertices, 'triangles': saved['triangles'], 'bed': heights, 'h0': heights, 'water': None, 'wet': [], 'wetCells': [], 'cells': [], 'hydrologicOwner': [], 'cellOwner': []}, 'geometry_layers': {name: review['meshes'][name] for name in MESH_NAMES}, 'stations': review['stations'], 'portals': review['portals'], 'pins': review['pins'], 'surface_attachments': review['surface_attachments'], 'actual_closed_core_station_indices': review['actual_closed_core_station_indices'], 'coordinates': review['coordinates'], 'independent_audit_reference': review['independent_audit_reference'], 'limitations': review['limitations'], 'hydraulic_solved': False, 'three_dimensional_flow_solved': False, 'full_network_verified': False, 'natural_outlet_certified': False}

def render_figures(review, vertical_exaggeration=1.0):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import LightSource
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    _i27_require(_i27_np.isfinite(vertical_exaggeration) and 0 < vertical_exaggeration <= 10, 'explicit display vertical multiplier must be in (0,10]')
    origin = _i27_np.asarray(review['coordinates']['plot_origin_xyz_m'])
    points = {name: _i27_np.asarray(mesh['vertices_local_xyz_m']) + _i27_np.asarray(mesh['local_origin_xyz_m']) - origin for name, mesh in review['meshes'].items()}
    faces = {name: _i27_np.asarray(mesh['triangles'], int) for name, mesh in review['meshes'].items()}
    native = _i27_np.asarray(review['native_terrain']['height_m'])
    valid = _i27_np.asarray(review['native_terrain']['valid_mask'], bool)
    spacing = review['coordinates']['native_spacing_m']
    native_origin = _i27_np.asarray(review['coordinates']['native_origin_m_xz']) - origin[[0, 2]]
    shade = LightSource(315, 45).hillshade(native, dx=spacing, dy=spacing)
    shade[~valid] = _i27_np.nan
    extent = [native_origin[0] - spacing / 2, native_origin[0] + (native.shape[1] - 0.5) * spacing, native_origin[1] + (native.shape[0] - 0.5) * spacing, native_origin[1] - spacing / 2]
    portals = {kind: _i27_np.asarray(node['xyz_m']) - origin for kind, node in review['portals'].items()}
    output = {}

    def finish(figure, name):
        stream = _i27_BytesIO()
        figure.savefig(stream, format='png', dpi=150, facecolor='white')
        plt.close(figure)
        _i27_require(stream.tell() <= _i27_MAX_BYTES, 'scientific PNG exceeds 64MiB')
        output[name] = stream.getvalue()
        _i27_check_memory()
    figure, axes = plt.subplots(1, 2, figsize=(14, 7), gridspec_kw={'width_ratios': [1, 1.5]})
    low, high = (points['rock_before'][:, [0, 2]].min(axis=0), points['rock_before'][:, [0, 2]].max(axis=0))
    for axis in axes:
        axis.imshow(shade, cmap='gray', extent=extent, interpolation='nearest')
        for kind, point in portals.items():
            axis.scatter(point[0], point[2], marker='v' if kind == 'sink' else '^', s=55, c='#a84635', zorder=5)
            axis.annotate(kind, point[[0, 2]], xytext=(6, 7), textcoords='offset points', fontsize=9)
        axis.set_aspect('equal')
        axis.xaxis.set_major_locator(MaxNLocator(4))
        axis.yaxis.set_major_locator(MaxNLocator(4))
        axis.ticklabel_format(style='plain', useOffset=False)
        axis.set_xlabel('Local X (m)')
        axis.set_ylabel('Local Z (m)')
    axes[0].add_patch(Rectangle(low, *high - low, facecolor='none', edgecolor='#a84635', linewidth=1.5))
    axes[0].set_title('Native mountain location')
    axes[1].add_collection(PolyCollection(points['removed'][:, [0, 2]][faces['removed']], facecolors='#a78342', edgecolors='none', alpha=0.65))
    margin = max(5.0, float(_i27_np.max(high - low)) * 0.08)
    axes[1].set_xlim(low[0] - margin, high[0] + margin)
    axes[1].set_ylim(low[1] - margin, high[1] + margin)
    axes[1].set_title('Saved excavated-solid projection; not water')
    figure.suptitle('Engineered local cave | native terrain and actual saved geometry', fontsize=14)
    figure.text(0.05, 0.03, 'Model origin XYZ (m): ' + str(origin.tolist()) + ' | Original native samples, no solver', fontsize=9)
    figure.subplots_adjust(bottom=0.15, top=0.86, wspace=0.3)
    finish(figure, 'overview.png')
    stations = review['stations']
    rings = [_i27_np.asarray(station['derived_ring_xyz_m']) - origin for station in stations]
    centers = _i27_np.asarray([_i27_np.asarray(station['origin_xyz_m']) - origin for station in stations])
    distance = _i27_np.r_[0.0, _i27_np.cumsum(_i27_np.linalg.norm(_i27_np.diff(centers, axis=0), axis=1))]
    figure, axis = plt.subplots(figsize=(13, 5))
    floor = [ring[:, 1].min() + origin[1] for ring in rings]
    roof = [ring[:, 1].max() + origin[1] for ring in rings]
    axis.plot(distance, floor, color='#825f2c', linewidth=2.0, label='Saved VDM ring minimum elevation')
    axis.plot(distance, roof, color='#696561', linewidth=1.0, linestyle=':', label='Cutter roof outline; not rock roof at open ramps')
    core = review['actual_closed_core_station_indices']
    if core:
        axis.plot(distance[core], _i27_np.asarray(roof)[core], color='#696561', linewidth=2.5, label='Saved roof outline within actual covered core')
    axis.fill_between(distance, floor, roof, color='#a78342', alpha=0.16, label='Section envelope only; not water')
    axis.set_xlabel('Saved station-origin path distance (m)')
    axis.set_ylabel('Model Y elevation (m)')
    axis.set_title('Final saved VDM sections | longitudinal elevation envelope')
    axis.grid(alpha=0.2)
    axis.legend(fontsize=9)
    axis.ticklabel_format(style='plain', useOffset=False)
    figure.tight_layout()
    finish(figure, 'profile.png')
    figure = plt.figure(figsize=(13, 9))
    axis = figure.add_subplot(111, projection='3d')
    for name, color, alpha in (('rock_after', '#787d77', 0.16), ('removed', '#b29155', 0.45)):
        plotted = points[name][:, [0, 2, 1]].copy()
        plotted[:, 2] *= vertical_exaggeration
        axis.add_collection3d(Poly3DCollection(plotted[faces[name]], facecolors=color, edgecolors='none', alpha=alpha, rasterized=True))
    for ring in rings:
        closed = _i27_np.vstack((ring, ring[0]))
        axis.plot(closed[:, 0], closed[:, 2], closed[:, 1] * vertical_exaggeration, color='#73552b', linewidth=0.65, alpha=0.8)
    for attachment in review['surface_attachments'].values():
        mesh = attachment['geometry']
        halfarm = _i27_np.asarray(mesh['vertices_xyz_m']) - origin
        halfarm = halfarm[:, [0, 2, 1]]
        halfarm[:, 2] *= vertical_exaggeration
        triangles = _i27_np.asarray(mesh['triangles'], int)[attachment['half_arm_triangle_indices']]
        axis.add_collection3d(Poly3DCollection(halfarm[triangles], facecolors='#527363', edgecolors='none', alpha=0.8))
    rows, columns = _i27_np.indices(native.shape)
    native_x = native_origin[0] + columns * spacing
    native_z = native_origin[1] + rows * spacing
    crop = valid & (native_x >= low[0]) & (native_x <= high[0]) & (native_z >= low[1]) & (native_z <= high[1])
    axis.scatter(native_x[crop], native_z[crop], (native[crop] - origin[1]) * vertical_exaggeration, s=2, c='#444844', alpha=0.35, depthshade=False)
    for kind, point in portals.items():
        axis.scatter(point[0], point[2], point[1] * vertical_exaggeration, c='#a84635', marker='v' if kind == 'sink' else '^', s=50)
        axis.text(point[0], point[2], point[1] * vertical_exaggeration, ' ' + kind, fontsize=9)
    bounds = points['rock_before'][:, [0, 2, 1]].copy()
    bounds[:, 2] *= vertical_exaggeration
    minimum, maximum = (bounds.min(axis=0), bounds.max(axis=0))
    span = _i27_np.maximum(maximum - minimum, 1.0)
    axis.set_xlim(minimum[0], maximum[0])
    axis.set_ylim(minimum[1], maximum[1])
    axis.set_zlim(minimum[2], maximum[2])
    axis.set_box_aspect(span)
    axis.view_init(elev=22, azim=-58)
    axis.set_xlabel('Local X (m)')
    axis.set_ylabel('Local Z (m)')
    axis.set_zlabel('Local Y (m)' if vertical_exaggeration == 1 else 'Local Y x ' + str(vertical_exaggeration))
    for coordinate_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
        coordinate_axis.set_major_locator(MaxNLocator(4))
    axis.set_title('Actual remaining-rock shell (transparent) + saved excavated solid + final VDM rings\nNative samples (dots), saved half-arms (green); no water; Y multiplier ' + str(vertical_exaggeration), fontsize=11)
    figure.text(0.08, 0.03, 'Local origin XYZ (m): ' + str(origin.tolist()) + ' | Transparency is inspection only; independent opening audit required', fontsize=9)
    finish(figure, 'oblique-3d.png')
    return output

def _entry_export_hybrid_cave_review():
    parser = _i27_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=_i27_Path, required=True)
    parser.add_argument('--geometry-sha256', required=True)
    parser.add_argument('--audit', type=_i27_Path)
    parser.add_argument('--audit-sha256')
    parser.add_argument('--audit-schema', default=AUDIT_SCHEMA, choices=[AUDIT_SCHEMA])
    parser.add_argument('--output', type=_i27_Path, required=True)
    parser.add_argument('--vertical-exaggeration', type=float, default=1.0)
    args = parser.parse_args()
    _i27_require(not args.output.exists(), 'new review output directory required')
    review = load_review(args.geometry, args.geometry_sha256, args.audit, args.audit_sha256, args.audit_schema)
    artifacts = {'review.json': _i27_encoded(review), 'caseartifact.json': _i27_encoded(caseartifact(review))}
    artifacts.update(render_figures(review, args.vertical_exaggeration))
    print(_i27_publish_directory(args.output, artifacts))
_i28_matplotlib.use('Agg')
_i28_sys.path.insert(0, str(ROOT))

def export(faces_pin, audit_pin, output):
    started = _i28_time.monotonic()
    faces, audit = (_i28_read(faces_pin), _i28_read_audit(audit_pin))
    _i28_require(faces['schema'] == 'td-hybrid-river-faces-v1' and audit['schema'] == 'td-hybrid-river-faces-independent-audit-v1' and (audit['faces_pin']['sha256'] == faces_pin['sha256']) and (_i28_Path(audit['faces_pin']['path']).resolve() == _i28_Path(faces_pin['path']).resolve()) and (audit['status'] in ('passed', 'refused')) and (len(faces['faces']) == faces['face_count'] == 18), 'wrong saved face/audit linkage or scope')
    accepted = {item['face_id'] for item in audit['reports']}
    _i28_require(len(accepted) == audit['verified_face_count'] and all((item['status'] == 'candidate' for item in faces['faces'] if item['face_id'] in accepted)), 'face acceptance census differs')
    output = _i28_Path(output).resolve()
    _i28_require(not output.exists() and output.parent == (ROOT / 'verification/natural-river-network').resolve(), 'new local face review package required')
    colors = {'rock_after': '#c1c4c8', 'removed': '#cc8850', 'cutter': '#1b8d91'}
    figure, axes = _i28_plt.subplots(3, 6, figsize=(22, 11), constrained_layout=True)
    summary = []
    for face, axis in zip(faces['faces'], axes.flat):
        slices = face.get('solid_slices', {})
        cutter = slices.get('cutter', {}).get('polygons_uv_m', [])
        _i28_require(cutter, 'saved refused face lacks diagnostic slice evidence')
        bounds = _i28_np.concatenate([_i28_np.asarray(loop, float) for loop in cutter])
        _i28_require(_i28_np.isfinite(bounds).all() and bounds.shape[1] == 2, 'invalid slice display coordinates')
        for role in ('rock_after', 'removed', 'cutter'):
            record = slices[role]
            for polygon, holes in zip(record['polygons_uv_m'], record['holes_uv_m']):
                axis.add_patch(_i28_PolygonPatch(polygon, closed=True, facecolor=colors[role] if role != 'cutter' else 'none', edgecolor=colors[role], linewidth=1.0, alpha=0.7))
                if role != 'cutter':
                    for hole in holes:
                        axis.add_patch(_i28_PolygonPatch(hole, closed=True, facecolor='white', edgecolor=colors[role], linewidth=0.5))
        for piece in face.get('aperture', {}).get('boundary_pieces', []):
            if piece['category'] == 'actual_rock_wet_wall':
                points = _i28_np.asarray(piece['points_uv_m'])
                axis.plot(points[:, 0], points[:, 1], color='#24272a', linewidth=2.0)
        passed = face['face_id'] in accepted
        axis.set_title(face['face_id'] + (' | geometry passed' if passed else ' | REFUSED'), fontsize=10, color='#146c55' if passed else '#b42428')
        axis.set_xlim(bounds[:, 0].min() - 0.5, bounds[:, 0].max() + 0.5)
        axis.set_ylim(bounds[:, 1].min() - 0.5, bounds[:, 1].max() + 0.5)
        axis.set_aspect('equal', adjustable='box')
        axis.grid(alpha=0.15)
        axis.set_xlabel('transverse u (m)', fontsize=8)
        axis.set_ylabel('common local Y (m)', fontsize=8)
        reasons = face['rejection_reasons'] if not passed else []
        summary.append({'face_id': face['face_id'], 'link_id': face['link_id'], 'geometry_passed': passed, 'rejection_reasons': reasons, 'plane': face['plane'], 'kind': face.get('aperture', {}).get('kind'), 'hydraulic_certified': False})
        _i28_check_memory()
    figure.suptitle('Saved actual link slices: grey remaining rock, orange removed rock, teal cutter, black verified wet wall\nLocal slice geometry only; refused faces retained; no water, discharge, or whole-link sill certification', fontsize=12)
    with _i28_tempfile.TemporaryDirectory(prefix='.face-review-', dir=output.parent) as temporary:
        staging = _i28_Path(temporary) / 'package'
        staging.mkdir()
        figure.savefig(staging / 'faces.png', dpi=130)
        _i28_plt.close(figure)
        _i28_require((staging / 'faces.png').stat().st_size <= _i28_MAX_BYTES, 'face image exceeds file budget')
        report = {'schema': 'td-hybrid-river-faces-review-v1', 'status': 'saved_geometry_review', 'inputs': {'faces': faces_pin, 'audit': audit_pin}, 'audit_status': audit['status'], 'verified_face_count': len(accepted), 'faces': summary, 'image': {'path': str(output / 'faces.png'), 'sha256': _i28_file_sha256(staging / 'faces.png')}, 'hydraulic_certified': False, 'integration_performed': False, 'water_mesh': None, 'whole_link_sill_verified': False, 'frontend_integrated': False, 'code_sha256': {'tools/export_hybrid_geometry_review.py': _i28_file_sha256(_i28_Path(__file__))}, 'resource': {'wall_seconds': _i28_time.monotonic() - started, 'peak_rss_bytes': _i28_check_memory(), 'solver_calls': 0}}
        report['identity_sha256'] = _i28_digest(report)
        payload = _i28_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        _i28_require(len(payload) <= _i28_MAX_BYTES, 'face review exceeds file budget')
        (staging / 'review.json').write_bytes(payload)
        staging.rename(output)
    return report

def _entry_export_hybrid_river_faces_review():
    parser = _i28_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--faces', required=True, type=_i28_Path)
    parser.add_argument('--faces-sha256', required=True)
    parser.add_argument('--audit', required=True, type=_i28_Path)
    parser.add_argument('--audit-sha256', required=True)
    parser.add_argument('--output', required=True, type=_i28_Path)
    args = parser.parse_args()
    report = export({'path': str(args.faces.resolve()), 'sha256': args.faces_sha256}, {'path': str(args.audit.resolve()), 'sha256': args.audit_sha256}, args.output)
    print(_i28_json.dumps({'status': report['status'], 'audit_status': report['audit_status'], 'verified_face_count': report['verified_face_count'], 'output': str(args.output)}))

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'cave': '_entry_export_hybrid_cave_review', 'faces': '_entry_export_hybrid_river_faces_review'}
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
