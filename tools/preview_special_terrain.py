"""Consolidated preview_special_terrain implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _landform_argparse
from terrain_pipeline.special_terrain import LEDGER as _landform_LEDGER
from terrain_pipeline.special_terrain import DEFAULT_OUTPUT as _landform_DEFAULT_OUTPUT, DEFAULT_PREVIEW as _landform_DEFAULT_PREVIEW, EGGS as _landform_EGGS, FIGURE_NAMES as _landform_FIGURE_NAMES, LOCAL_ORIGIN as _landform_LOCAL_ORIGIN, PLAN_SAMPLES as _landform_PLAN_SAMPLES, PROFILE_SAMPLES as _landform_PROFILE_SAMPLES, ROCK_EGGS_DEFAULT_OUTPUT as _landform_ROCK_EGGS_DEFAULT_OUTPUT, SOLID_ROLE as _landform_SOLID_ROLE, SinkholeParameters as _landform_SinkholeParameters, ULURU_FLARE_SOLID_ROLE as _landform_ULURU_FLARE_SOLID_ROLE, _i28_Path as _landform__i28_Path, _i28_hashlib as _landform__i28_hashlib, _i28_json as _landform__i28_json, _i28_math as _landform__i28_math, _i28_np as _landform__i28_np, _i28_sys as _landform__i28_sys, _i31_Path as _landform__i31_Path, _i31_json as _landform__i31_json, _i31_np as _landform__i31_np, _i32_Path as _landform__i32_Path, _i32_hashlib as _landform__i32_hashlib, _i32_json as _landform__i32_json, _i32_np as _landform__i32_np, _i33_Path as _landform__i33_Path, _i33_hashlib as _landform__i33_hashlib, _i33_json as _landform__i33_json, _i33_np as _landform__i33_np, _i33_sys as _landform__i33_sys, _i34_Path as _landform__i34_Path, _i34_hashlib as _landform__i34_hashlib, _i34_json as _landform__i34_json, _i34_np as _landform__i34_np, _i34_sys as _landform__i34_sys, _plane_segments as _landform__plane_segments, _top_surface_map as _landform__top_surface_map, _x16_ray_hits as _landform__x16_ray_hits, _x17_hybrid_cave_geometry_seal as _landform__x17_hybrid_cave_geometry_seal, _x25_solid_from_record as _landform__x25_solid_from_record, as_origin as _landform_as_origin, as_parameters as _landform_as_parameters, cave_bridge_write_report as _landform_cave_bridge_write_report, file_sha256 as _landform_file_sha256, parameters as _landform_parameters, perimeter_arc_length as _landform_perimeter_arc_length, report as _landform_report, rock_eggs_plane_section_segments as _landform_rock_eggs_plane_section_segments, rock_eggs_write_report as _landform_rock_eggs_write_report, save_arrays as _landform_save_arrays, sinkhole_build as _landform_sinkhole_build, uluru_flare_plane_section_segments as _landform_uluru_flare_plane_section_segments, uluru_flare_write_report as _landform_uluru_flare_write_report, wall_levels as _landform_wall_levels, wall_ring_at as _landform_wall_ring_at, write_report as _landform_write_report
import matplotlib as _i33_matplotlib
import matplotlib.pyplot as _i33_plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection as _i33_Poly3DCollection

def _save(figure, output_directory, name):
    path = _landform__i28_Path(output_directory) / name
    figure.savefig(path, dpi=120, metadata={'Software': 'special_terrain_pillars3d'})
    import matplotlib.pyplot as plt
    plt.close(figure)
    return {'name': name, 'path': path.as_posix(), 'sha256': _landform__i28_hashlib.sha256(path.read_bytes()).hexdigest()}

def render(geometry, output_directory):
    """Plan, wall profile and 3D views of the saved union. Display only, never evidence."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    matplotlib.rcParams['font.family'] = ['Microsoft YaHei', 'DejaVu Sans']
    matplotlib.rcParams['axes.unicode_minus'] = False
    _landform_parameters = geometry['parameters']
    polygons = geometry['polygons']
    heights = geometry['heights']
    origin = geometry['origin']
    output = _landform__i28_Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    union = geometry['solids'][_landform_SOLID_ROLE]
    vertices = _landform__i28_np.asarray(union['vertices_local_xyz_m'], float) + _landform__i28_np.asarray(origin, float)
    triangles = _landform__i28_np.asarray(union['triangles'], int)
    phases = _landform__i28_np.random.default_rng(_landform_parameters.seed + 7).uniform(0.0, 2.0 * _landform__i28_math.pi, size=len(polygons))
    panel = []
    figure, axes = plt.subplots(figsize=(8.4, 8.4))
    for ring in polygons:
        closed = _landform__i28_np.vstack((ring, ring[:1]))
        axes.plot(closed[:, 0], closed[:, 1], color='#7b5e2e', linewidth=0.9)
    axes.scatter(geometry['centres'][:, 0], geometry['centres'][:, 1], s=8.0, color='#c62828', zorder=5, label='节理种子点 (joint seeds)')
    ring = polygons[0]
    height = float(heights[0])
    perimeter_s = _landform_perimeter_arc_length(ring)
    for y, colour, label in ((0.0, '#2e7d32', '底 y = 0'), (height * 0.5, '#1565c0', '中 y = h/2'), (height, '#6a1b9a', '顶 y = h')):
        outline = _landform_wall_ring_at(ring, perimeter_s, y, height, float(phases[0]), True, _landform_parameters)
        closed = _landform__i28_np.vstack((outline, outline[:1]))
        axes.plot(closed[:, 0], closed[:, 1], color=colour, linewidth=1.4, label=label)
    axes.annotate('多边形棱柱截面 (polygonal prism section),\n不是高度场能给出的圆盘', xy=(float(polygons[0][:, 0].min()), float(polygons[0][:, 1].min())), xytext=(-_landform_parameters.footprint_half_extent_m * 0.95, -_landform_parameters.footprint_half_extent_m * 0.78), fontsize=8, arrowprops={'arrowstyle': '->', 'lw': 0.8})
    axes.set_aspect('equal')
    axes.set_xlabel('x (m)')
    axes.set_ylabel('z (m)')
    axes.set_title('%d 个节理胞：不规则多边形平面截面 (plan view, synthetic analytic, not TD)' % len(polygons))
    axes.legend(fontsize=7, loc='upper right')
    axes.grid(alpha=0.2)
    figure.tight_layout()
    panel.append(_save(figure, output, 'pillars3d-a-plan.png'))
    figure, axes = plt.subplots(figsize=(7.6, 7.0))
    centre = ring.mean(axis=0)
    radii = _landform__i28_np.linalg.norm(ring - centre, axis=1)
    levels = _landform_wall_levels(height, _landform_parameters.substep_m)
    for index, colour, label in ((int(_landform__i28_np.argmax(radii)), '#1565c0', '最远壁点 (farthest arris)'), (int(_landform__i28_np.argmin(radii)), '#2e7d32', '最近壁点 (nearest face)')):
        profile = [float(_landform__i28_np.linalg.norm(_landform_wall_ring_at(ring, perimeter_s, float(y), height, float(phases[0]), True, _landform_parameters)[index] - centre)) for y in levels]
        axes.plot(profile, levels, color=colour, linewidth=1.4, label=label)
    axes.axhline(height - _landform_parameters.cap_thickness_m, color='#6a1b9a', linestyle='--', linewidth=1.0, label='铁帽下界 (iron cap base, %.0f m)' % _landform_parameters.cap_thickness_m)
    axes.annotate('上细下粗 (taper %.0f%%)：绕自身质心的相似收缩' % (_landform_parameters.taper_fraction * 100.0), xy=(float(min(radii)) * 0.99, height * 0.55), xytext=(float(min(radii)) * 0.55, height * 0.82), fontsize=8, arrowprops={'arrowstyle': '->', 'lw': 0.8})
    axes.annotate('铁帽外凸 (cap bulge %.1f m)' % _landform_parameters.cap_bulge_m, xy=(float(max(radii)) * 1.02, height - _landform_parameters.cap_thickness_m * 0.5), xytext=(float(max(radii)) * 0.8, height * 0.18), fontsize=8, arrowprops={'arrowstyle': '->', 'lw': 0.8})
    axes.set_xlabel('距柱截面质心的径向距离 (m)')
    axes.set_ylabel('y elevation (m)')
    axes.set_title('单柱壁剖面：每条周边射线的半径随高程变化')
    axes.legend(fontsize=7, loc='upper left')
    axes.grid(alpha=0.2)
    figure.tight_layout()
    panel.append(_save(figure, output, 'pillars3d-b-wall-profile.png'))
    figure = plt.figure(figsize=(9.0, 7.4))
    axes = figure.add_subplot(111, projection='3d')
    faces = vertices[triangles][::max(1, len(triangles) // 6000)]
    axes.add_collection3d(Poly3DCollection(faces, facecolor='#c8853f', edgecolor='#6b4f1d', linewidths=0.05, alpha=0.95))
    low, high = (vertices.min(axis=0), vertices.max(axis=0))
    axes.set_xlim(low[0], high[0])
    axes.set_ylim(low[2], high[2])
    axes.set_zlim(low[1], high[1])
    axes.set_xlabel('x (m)')
    axes.set_ylabel('z (m)')
    axes.set_zlabel('y elevation (m)')
    axes.set_title('石柱群闭合 MESH64 实体：%d 面' % len(triangles))
    figure.tight_layout()
    panel.append(_save(figure, output, 'pillars3d-c-solid.png'))
    return panel

def main_landform(argv=None):
    parser = _landform_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=_landform__i28_Path)
    parser.add_argument('--output', type=_landform__i28_Path, default=_landform_DEFAULT_OUTPUT)
    arguments = parser.parse_args(argv)
    output = arguments.directory if arguments.directory is not None else arguments.output
    output.mkdir(parents=True, exist_ok=True)
    record, geometry = _landform_write_report(output / 'report.json', output_directory=output)
    arrays = _landform_save_arrays(output, geometry)
    print(_landform__i28_json.dumps({'status': record['status'], 'report': (output / 'report.json').as_posix(), 'union_volume_m3': record['volume_account']['assembled_volume_m3'], 'components': record['boolean']['census']['assembled_components'], 'pillars': record['volume_account']['pillar_count'], 'full_depth_pillars': record['volume_account']['full_depth_pillars'], 'carve_scales': record['volume_account']['carve_scales'], 'height_range_m': record['variants']['vdm_carved_walls']['height_range_m'], 'variants': record['variants'], 'witness_verdicts': {name: witness['verdict'] for name, witness in record['witnesses'].items()}, 'arrays': arrays, 'figures': record['figures'], 'identity_sha256': record['identity_sha256']}, ensure_ascii=False))
    return 0

def write_preview(directory, parameters=_landform_SinkholeParameters(), origin=_landform_LOCAL_ORIGIN, *, names=_landform_FIGURE_NAMES, report_name='report.json'):
    """Write the plan / profile / solid figures plus the contract ``report.json``."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory = _landform__i31_Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    record, solids = _landform_sinkhole_build(_landform_parameters, origin)
    _landform_parameters = _landform_as_parameters(_landform_parameters)
    origin = _landform_as_origin(origin)
    after = _landform__x25_solid_from_record(solids['rock_after'], 'rock_after')
    xs, grid = _landform__top_surface_map(after, origin, _landform_parameters.block_half_span_x_m, _landform_PLAN_SAMPLES)
    figure, axes = plt.subplots(figsize=(7.2, 6.4), dpi=140)
    image = axes.imshow(grid, origin='lower', extent=[xs[0], xs[-1], xs[0], xs[-1]], cmap='terrain', aspect='equal')
    axes.set_xlabel('x [m]')
    axes.set_ylabel('z [m]')
    axes.set_title('sinkhole plan view: first vertical-hit elevation [m]')
    axes.plot([0.0], [0.0], marker='x', color='black')
    axes.add_patch(plt.Circle((0.0, 0.0), _landform_parameters.shaft_radius_top_m, fill=False, color='black', linestyle=':'))
    axes.text(_landform_parameters.shaft_radius_top_m + 3.0, 0.0, 'shaft collar r = %.1f m' % _landform_parameters.shaft_radius_top_m)
    figure.colorbar(image, ax=axes, label='elevation [m]')
    figure.tight_layout()
    figure.savefig(directory / names[0])
    plt.close(figure)
    profile_z = 0.0
    centres = _landform__i31_np.linspace(-_landform_parameters.block_half_span_x_m, _landform_parameters.block_half_span_x_m, _landform_PROFILE_SAMPLES)
    columns = []
    for x in centres:
        hits = _landform__x16_ray_hits(after, [float(x), 20.0, profile_z], [float(x), -46.0, profile_z], origin)
        if len(hits) % 2:
            raise ValueError('profile column has an odd hit count; geometry not y-columnar here')
        heights = [hit['position_xyz_m'][1] for hit in hits]
        columns.append((float(x), [(heights[index], heights[index + 1]) for index in range(0, len(heights), 2)]))
    figure, axes = plt.subplots(figsize=(9.6, 4.6), dpi=140)
    for x, pairs in columns:
        for low, high in pairs:
            axes.plot([x, x], [low, high], color='#6b4f31', linewidth=2.2)
    axes.axhline(_landform_parameters.ground_surface_y_m, color='black', linewidth=1.0)
    axes.set_xlim(-_landform_parameters.block_half_span_x_m, _landform_parameters.block_half_span_x_m)
    axes.set_ylim(_landform_parameters.block_floor_y_m - 4.0, 12.0)
    axes.set_xlabel('x [m]')
    axes.set_ylabel('elevation [m]')
    axes.set_title('sinkhole section at z = 0 m: rock [brown] left by the Mesh64 subtraction')
    figure.tight_layout()
    figure.savefig(directory / names[1])
    plt.close(figure)
    vertices = _landform__i31_np.array(solids['rock_after']['vertices_local_xyz_m'], float) + origin
    triangles = _landform__i31_np.array(solids['rock_after']['triangles'], int)
    figure = plt.figure(figsize=(8.2, 6.4), dpi=140)
    axes = figure.add_subplot(projection='3d')
    step = max(1, len(triangles) // 1600)
    for triangle in triangles[::step]:
        loop = _landform__i31_np.vstack((vertices[triangle], vertices[triangle[0]]))
        axes.plot(loop[:, 0], loop[:, 2], loop[:, 1], color='#6b4f31', linewidth=0.35, alpha=0.5)
    axes.set_xlabel('x [m]')
    axes.set_ylabel('z [m]')
    axes.set_zlabel('elevation [m]')
    axes.set_title('sinkhole solid: rock_after wireframe (sampled triangles)')
    figure.tight_layout()
    figure.savefig(directory / names[2])
    plt.close(figure)
    _landform_report = {key: value for key, value in record.items() if key != 'identity_sha256'}
    _landform_report['figures'] = [{'name': name, 'path': name, 'sha256': _landform_file_sha256(directory / name)} for name in names]
    _landform__x17_hybrid_cave_geometry_seal(_landform_report)
    (directory / report_name).write_text(_landform__i31_json.dumps(_landform_report, sort_keys=True, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    return _landform_report

def sinkhole_main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=_landform__i31_Path, required=True)
    arguments = parser.parse_args()
    _landform_report = write_preview(arguments.output)
    print(_landform__i31_json.dumps({'status': _landform_report['status'], 'identity_sha256': _landform_report['identity_sha256'], 'figures': _landform_report['figures'], 'material': _landform_report['boolean']['material']}, ensure_ascii=False))
    return 0

def _cave_bridge_save(figure, output_directory, name):
    import matplotlib.pyplot as plt
    path = output_directory / name
    figure.savefig(path, dpi=110, metadata={'Software': None})
    plt.close(figure)
    return {'name': name, 'path': str(path), 'sha256': _landform__i32_hashlib.sha256(path.read_bytes()).hexdigest()}

def cave_bridge_render(output_directory, solids, parameters):
    """Three display figures (plan slice, through profile, void solid); never a certification."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output_directory = _landform__i32_Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    figures = []
    slice_y = (_landform_parameters.tunnel_floor_y_m + _landform_parameters.tunnel_roof_y_m) / 2.0
    figure, axes = plt.subplots(figsize=(6.4, 6.4))
    for role, colour, width in (('rock_after', '.55', 0.5), ('removed', '#c0392b', 0.9)):
        for first, second in _landform__plane_segments(solids[role], 1, slice_y):
            axes.plot([first[0], second[0]], [first[2], second[2]], color=colour, linewidth=width, zorder=2 if role == 'removed' else 1)
    for centre in _landform_parameters.skylight_x_m:
        axes.plot([centre], [0.0], marker='+', color='#2980b9', markersize=10, zorder=3)
    axes.set_aspect('equal')
    axes.set_title('plan slice at y=%.0f m: rock outline, gallery and both bores' % slice_y)
    axes.set_xlabel('x m')
    axes.set_ylabel('z m')
    figures.append(_cave_bridge_save(figure, output_directory, 'a-plan-slice.png'))
    figure, axes = plt.subplots(figsize=(8.4, 4.0))
    for role, colour, width in (('rock_after', '.55', 0.6), ('removed', '#c0392b', 0.9)):
        for first, second in _landform__plane_segments(solids[role], 2, 0.0):
            axes.plot([first[0], second[0]], [first[1], second[1]], color=colour, linewidth=width, zorder=2 if role == 'removed' else 1)
    axes.axhline(_landform_parameters.top_y_m, color='#2980b9', linewidth=0.7, linestyle=':')
    axes.set_title('profile through z=0: two bores, the rock between them, and the gallery')
    axes.set_xlabel('x m')
    axes.set_ylabel('y m')
    figures.append(_cave_bridge_save(figure, output_directory, 'b-profile-z0.png'))
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    figure = plt.figure(figsize=(7.2, 6.0))
    axes = figure.add_subplot(111, projection='3d')
    for role, colour, alpha in (('rock_after', '.45', 0.06), ('removed', '#c0392b', 0.55)):
        vertices = _landform__i32_np.asarray(solids[role]['vertices_local_xyz_m'], float)
        triangles = _landform__i32_np.asarray(solids[role]['triangles'], int)
        step = max(1, len(triangles) // 4000)
        axes.add_collection3d(Poly3DCollection(vertices[triangles[::step]], facecolor=colour, edgecolor='none', alpha=alpha))
    edges = _landform__i32_np.asarray(solids['rock_before']['vertices_local_xyz_m'], float)
    axes.set_xlim(edges[:, 0].min(), edges[:, 0].max())
    axes.set_ylim(edges[:, 2].min(), edges[:, 2].max())
    axes.set_zlim(edges[:, 1].min(), edges[:, 1].max())
    axes.set_xlabel('x m')
    axes.set_ylabel('z m')
    axes.set_zlabel('y m')
    axes.set_title('excavated gallery, branch and two bores inside the analytic block')
    figures.append(_cave_bridge_save(figure, output_directory, 'c-solid-3d.png'))
    return figures

def cave_bridge_main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=_landform__i32_Path, default=_landform__i32_Path('.scratch/special-terrain/l1-preview-20261019/cave-bridge'))
    args = parser.parse_args()
    path = args.output / 'report.json'
    record = _landform_cave_bridge_write_report(path, output_directory=args.output)
    print(_landform__i32_json.dumps({'status': record['status'], 'report': str(path), 'material': record['boolean']['material'], 'census': record['boolean']['census'], 'identity_sha256': record['identity_sha256']}, ensure_ascii=False))
    return 0
_i33_matplotlib.use('Agg')

def render_preview(record, output_directory, hover=None):
    """Plan view, true plane section (with the measured clearance) and a 3D solid view."""
    output = _landform__i33_Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    vertices = _landform__i33_np.asarray(record['vertices_local_xyz_m'], float)
    triangles = _landform__i33_np.asarray(record['triangles'], int)
    figures = []
    figure, axes = _i33_plt.subplots(figsize=(9.0, 9.0))
    for triangle in triangles:
        ring = vertices[triangle][:, [0, 2]]
        axes.plot(_landform__i33_np.append(ring[:, 0], ring[0, 0]), _landform__i33_np.append(ring[:, 1], ring[0, 1]), color='#8a6d3b', linewidth=0.2, alpha=0.3)
    for item in _landform_EGGS:
        axes.annotate(item.egg_id, (item.centre_xyz_m[0], item.centre_xyz_m[2]), fontsize=7, ha='center', color='#4a3010')
    axes.set_aspect('equal')
    axes.set_xlabel('x (m)')
    axes.set_ylabel('z (m)')
    axes.set_title('rock egg pile: plan view of the closed MESH64 union (synthetic analytic, not TD)')
    axes.grid(alpha=0.2)
    path = output / 'rock-eggs-a-plan.png'
    figure.tight_layout()
    figure.savefig(path, dpi=140, metadata={'Software': 'special_terrain_l1_rock_eggs'})
    _i33_plt.close(figure)
    figures.append({'name': 'a-plan', 'path': path.name, 'sha256': _landform__i33_hashlib.sha256(path.read_bytes()).hexdigest(), 'description': 'plan (x, z) wireframe of the union; the two separated eggs stand clear on the lower right'})
    figure, axes = _i33_plt.subplots(figsize=(9.0, 7.0))
    plane_value = float(hover['midpoint_xyz_m'][2]) if hover else 0.6
    segments = _landform_rock_eggs_plane_section_segments(record, 2, plane_value)
    if not segments:
        raise ValueError('plane section produced no segments')
    for first, second in segments:
        axes.plot([first[0], second[0]], [first[1], second[1]], color='#6b4f1d', linewidth=1.2)
    if hover:
        first = hover['facing_surface_hits'][0]['position_xyz_m']
        second = hover['facing_surface_hits'][1]['position_xyz_m']
        axes.plot([first[0], second[0]], [first[1], second[1]], color='#c0392b', linewidth=2.4, label='measured clearance %.3f m' % hover['measured_mesh_clearance_m'])
        axes.annotate('%s hovering above %s' % (hover['upper_egg_id'], hover['lower_egg_id']), (hover['midpoint_xyz_m'][0], hover['midpoint_xyz_m'][1]), fontsize=7, xytext=(14.0, 14.0), textcoords='offset points', color='#c0392b', arrowprops={'arrowstyle': '-', 'color': '#c0392b'})
        axes.legend(loc='upper left', fontsize=7)
    axes.set_aspect('equal')
    axes.set_xlabel('x (m)')
    axes.set_ylabel('y (m)')
    axes.set_title('rock egg pile: section at z = %.2f m (triangle/plane intersections)' % plane_value)
    axes.grid(alpha=0.2)
    path = output / 'rock-eggs-b-section.png'
    figure.tight_layout()
    figure.savefig(path, dpi=140, metadata={'Software': 'special_terrain_l1_rock_eggs'})
    _i33_plt.close(figure)
    figures.append({'name': 'b-section', 'path': path.name, 'sha256': _landform__i33_hashlib.sha256(path.read_bytes()).hexdigest(), 'description': 'true plane section through the hover pair; the red segment is the measured clearance', 'plane': 'z', 'value_m': plane_value, 'segment_count': len(segments)})
    figure = _i33_plt.figure(figsize=(10.0, 8.0))
    axes = figure.add_subplot(111, projection='3d')
    stride = max(1, len(triangles) // 8000)
    faces = vertices[triangles][::stride]
    axes.add_collection3d(_i33_Poly3DCollection(faces, facecolor='#c8a165', edgecolor='#6b4f1d', linewidths=0.1, alpha=0.95))
    low, high = (vertices.min(axis=0), vertices.max(axis=0))
    axes.set_xlim(low[0], high[0])
    axes.set_ylim(low[1], high[1])
    axes.set_zlim(low[2], high[2])
    axes.set_xlabel('x (m)')
    axes.set_ylabel('y (m)')
    axes.set_zlabel('z (m)')
    axes.set_title('rock egg pile: closed MESH64 union, %d triangles' % len(triangles))
    path = output / 'rock-eggs-c-solid.png'
    figure.tight_layout()
    figure.savefig(path, dpi=140, metadata={'Software': 'special_terrain_l1_rock_eggs'})
    _i33_plt.close(figure)
    figures.append({'name': 'c-solid', 'path': path.name, 'sha256': _landform__i33_hashlib.sha256(path.read_bytes()).hexdigest(), 'description': '3D view of the union; separated bodies and the hovering body are visible', 'faces_shown': len(faces), 'faces_total': len(triangles)})
    return figures

def rock_eggs_main(argv=None):
    parser = _landform_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=_landform__i33_Path)
    parser.add_argument('--output', type=_landform__i33_Path, default=_landform_ROCK_EGGS_DEFAULT_OUTPUT)
    parser.add_argument('--ledger', default=_landform_LEDGER)
    arguments = parser.parse_args(argv)
    output_directory = arguments.directory if arguments.directory is not None else arguments.output
    document, _artifacts, _landform_report = _landform_rock_eggs_write_report(output_directory, ledger=arguments.ledger)
    hover = document['witnesses']['hover_void_midpoint_is_outside']['observed']
    print(_landform__i33_json.dumps({'status': document['status'], 'connected_components': document['assembly']['connected_components'], 'union_volume_m3': document['assembly']['signed_volume_m3'], 'sum_of_parts_m3': document['assembly']['sum_of_parts_m3'], 'measured_hover_clearance_m': hover['measured_mesh_clearance_m'], 'witness_verdicts': {name: item['verdict'] for name, item in document['witnesses'].items()}, 'identity_sha256': document['identity_sha256'], 'report': str(_landform_report)}, ensure_ascii=False))
    return document

def _uluru_flare_save(figure, output_directory, name):
    path = _landform__i34_Path(output_directory) / name
    figure.savefig(path, dpi=120, metadata={'Software': 'special_terrain_l1_uluru_flare'})
    import matplotlib.pyplot as plt
    plt.close(figure)
    return {'name': name, 'path': path.as_posix(), 'sha256': _landform__i34_hashlib.sha256(path.read_bytes()).hexdigest()}

def uluru_flare_render(record, parameters, output_directory):
    """Plan, true section and 3D views of the saved union. Display only, never evidence."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    output = _landform__i34_Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    vertices = _landform__i34_np.asarray(record['vertices_local_xyz_m'], float) + _landform__i34_np.asarray(record['local_origin_xyz_m'], float)
    triangles = _landform__i34_np.asarray(record['triangles'], int)
    panel = []
    figure, axes = plt.subplots(figsize=(8.0, 8.0))
    axes.add_patch(Wedge((vertices[:, 0].mean(), vertices[:, 2].mean()), _landform_parameters.tower_base_radius_m, 0.0, 360.0, width=_landform_parameters.overhang_amplitude_m, facecolor='#f6d9a8', edgecolor='none', alpha=0.85, label='overhang annulus: %.0f m of open alcove' % _landform_parameters.overhang_amplitude_m))
    for triangle in triangles:
        ring = vertices[triangle][:, [0, 2]]
        closed = _landform__i34_np.vstack((ring, ring[:1]))
        axes.plot(closed[:, 0], closed[:, 1], color='#7b5e2e', linewidth=0.2, alpha=0.3)
    angles = _landform__i34_np.linspace(0.0, 2.0 * _landform__i34_np.pi, 361)
    for radius, colour in ((_landform_parameters.skirt_outer_radius_m, '#2e7d32'), (_landform_parameters.tower_base_radius_m, '#c62828')):
        axes.plot(radius * _landform__i34_np.cos(angles) + vertices[:, 0].mean(), radius * _landform__i34_np.sin(angles) + vertices[:, 2].mean(), color=colour, linewidth=1.1, linestyle='--', label='radius %.0f m' % radius)
    axes.set_aspect('equal')
    axes.set_xlabel('x (m)')
    axes.set_ylabel('z (m)')
    axes.set_title('uluru flared base: plan view (synthetic analytic, not TD)')
    axes.legend(fontsize=7, loc='upper right')
    axes.grid(alpha=0.2)
    figure.tight_layout()
    panel.append(_uluru_flare_save(figure, output, 'uluru-flare-a-plan.png'))
    figure, axes = plt.subplots(figsize=(7.5, 7.0))
    section_value = float(_landform__i34_np.mean(vertices[:, 2]))
    segments = _landform_uluru_flare_plane_section_segments(record, 2, section_value)
    if not segments:
        raise ValueError('plane section produced no segments')
    for first, second in segments:
        axes.plot([first[0], second[0]], [first[1], second[1]], color='#6b4f1d', linewidth=1.2)
    axes.annotate('open alcove under the overhang', xy=(vertices[:, 0].mean() + _landform_parameters.skirt_outer_radius_m + 10.0, _landform_parameters.skirt_top_elevation_m * 0.5), xytext=(vertices[:, 0].mean() + _landform_parameters.tower_base_radius_m + 20.0, 90.0), fontsize=7, arrowprops={'arrowstyle': '->', 'lw': 0.8})
    axes.set_aspect('equal')
    axes.set_xlabel('x (m)')
    axes.set_ylabel('y elevation (m)')
    axes.set_title('uluru flared base: section at z = %.2f m (triangle/plane crossings)' % section_value)
    axes.grid(alpha=0.2)
    figure.tight_layout()
    panel.append(_uluru_flare_save(figure, output, 'uluru-flare-b-section.png'))
    figure = plt.figure(figsize=(9.0, 7.0))
    axes = figure.add_subplot(111, projection='3d')
    faces = vertices[triangles][::max(1, len(triangles) // 6000)]
    axes.add_collection3d(Poly3DCollection(faces, facecolor='#c8853f', edgecolor='#6b4f1d', linewidths=0.1, alpha=0.95))
    low, high = (vertices.min(axis=0), vertices.max(axis=0))
    axes.set_xlim(low[0], high[0])
    axes.set_ylim(low[2], high[2])
    axes.set_zlim(low[1], high[1])
    axes.set_xlabel('x (m)')
    axes.set_ylabel('z (m)')
    axes.set_zlabel('y elevation (m)')
    axes.set_title('uluru flared base: closed MESH64 union, %d faces' % len(triangles))
    figure.tight_layout()
    panel.append(_uluru_flare_save(figure, output, 'uluru-flare-c-solid.png'))
    return panel

def uluru_flare_main(argv=None):
    parser = _landform_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=_landform__i34_Path)
    parser.add_argument('--output', type=_landform__i34_Path, default=_landform_DEFAULT_PREVIEW)
    arguments = parser.parse_args(argv)
    output = arguments.directory if arguments.directory is not None else arguments.output
    record = _landform_uluru_flare_write_report(output / 'report.json', output_directory=output)
    print(_landform__i34_json.dumps({'status': record['status'], 'report': (output / 'report.json').as_posix(), 'union_volume_m3': record['solids'][_landform_ULURU_FLARE_SOLID_ROLE]['signed_volume_m3'], 'components': record['boolean']['census']['assembled_components'], 'witness_verdicts': {name: witness['verdict'] for name, witness in record['witnesses'].items()}, 'identity_sha256': record['identity_sha256']}, ensure_ascii=False))
    return 0
import argparse as _i33_argparse
import hashlib as _i33_hashlib
import json as _i33_json
import math as _i33_math
from pathlib import Path as _i33_Path
import sys as _i33_sys
import matplotlib as _i33_matplotlib
import matplotlib.colors as _i33_mcolors
import matplotlib.pyplot as _i33_plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection as _i33_Poly3DCollection
import numpy as _i33_np
from terrain_pipeline.special_terrain import METRIC_FORMS_ALGORITHM as _i33_ALGORITHM
from terrain_pipeline.special_terrain import KINDS as _i33_KINDS
from terrain_pipeline.special_terrain import METRIC_FORMS_SCHEMA as _i33_SCHEMA
from terrain_pipeline.special_terrain import load_special_form_vdm as _i33_load_special_form_vdm
from terrain_pipeline.common_infra import identity as _i33_identity
import argparse as _i34_argparse
import json as _i34_json
import math as _i34_math
from pathlib import Path as _i34_Path
import sys as _i34_sys
import matplotlib as _i34_matplotlib
import numpy as _i34_np
from terrain_pipeline.special_terrain import METRIC_FORMS_ALGORITHM as _i34_ALGORITHM
from terrain_pipeline.special_terrain import FormTarget as _i34_FormTarget
from terrain_pipeline.special_terrain import METRIC_FORMS_SCHEMA as _i34_FORM_SCHEMA
from terrain_pipeline.special_terrain import SpecialFormRecipe as _i34_SpecialFormRecipe
from terrain_pipeline.special_terrain import build_special_form_vdm as _i34_build_special_form_vdm
from terrain_pipeline.special_terrain import form_preset as _i34_form_preset
from terrain_pipeline.special_terrain import save_special_form_vdm as _i34_save_special_form_vdm
from terrain_pipeline.special_terrain import validate_special_form_vdm as _i34_validate_special_form_vdm
from terrain_pipeline.common_infra import file_sha256 as _i34_file_sha256
from terrain_pipeline.common_infra import identity as _i34_identity
from terrain_pipeline.basin_topology import load_basin_hierarchy as _i34_load_basin_hierarchy
from terrain_pipeline.special_terrain import TD_ADAPTER_SCHEMA as _i34_ADAPTER_SCHEMA
from terrain_pipeline.special_terrain import build_td_form_chart as _i34_build_td_form_chart
from terrain_pipeline.special_terrain import select_native_window as _i34_select_native_window
CATEGORY = 'C'
_i33_matplotlib.use('Agg')
ROOT = _i33_Path(__file__).resolve().parents[1]
_i33_sys.path.insert(0, str(ROOT))
DEFAULT_BUNDLES = _i33_Path('.scratch/special-terrain/bundles-20261019')
DEFAULT_OUTPUT = _i33_Path('.scratch/special-terrain/preview-20261019')
SAMPLE_SEED = 20261019
MAX_FACES = 16000
PNG_META = {'Software': 'preview_special_terrain_forms'}
VERIFICATION_DIRECTORY = 'verification'
L1_PLACEHOLDERS = (('l1-sinkhole-shaft', 'Sinkhole shaft, subsurface river and skylight (tiankeng)'), ('l1-cave-skylight-bridge', 'Cave, skylight and natural bridge'), ('l1-rock-egg-pile', 'Devils Marbles, stacked rock eggs with voids between them'), ('l1-uluru-flared-slope', 'Uluru flared slope, overhanging base'))
SIX_CATEGORIES = (('1 Devils Tower plug', 'volcanic_plug'), ('2 Tiankeng sinkhole', 'l1-sinkhole-shaft'), ('3 Karst tower field', 'karst_tower_field'), ('4 Zhangjiajie sandstone pillars', 'sandstone_pillar_field'), ('5 Uluru inselberg', 'inselberg'), ('6 Devils Marbles rock eggs', 'l1-rock-egg-pile'))
CONTACT_SHEET = 'six-category-contact-sheet.png'
CONTACT_SLOTS = (('L0 field forms, vertical displacement only', 'L0', ('volcanic_plug', 'karst_tower_field', 'sandstone_pillar_field', 'inselberg')), ('L1 volume forms, sampled rock Boolean route, geometry pending in P5', 'L1', ('l1-sinkhole-shaft', 'l1-cave-skylight-bridge', 'l1-rock-egg-pile', 'l1-uluru-flared-slope')))
CATEGORY_LABELS = {'volcanic_plug': '1 Devils Tower volcanic plug', 'l1-sinkhole-shaft': '2 Tiankeng sinkhole shaft, river and skylight', 'karst_tower_field': '3 Karst tower field (Guilin)', 'sandstone_pillar_field': '4 Zhangjiajie sandstone pillar group', 'inselberg': '5 Uluru inselberg body', 'l1-uluru-flared-slope': '5 Uluru flared slope base', 'l1-rock-egg-pile': '6 Devils Marbles stacked rock eggs', 'l1-cave-skylight-bridge': '2/3 cave, skylight and natural bridge'}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha256_file(path):
    digest = _i33_hashlib.sha256()
    with _i33_Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''):
            digest.update(block)
    return digest.hexdigest()

def guard_output(output):
    """Refuse to write anywhere near a source cache or the verification tree."""
    parts = [part.lower() for part in _i33_Path(output).resolve().parts]
    require(VERIFICATION_DIRECTORY not in parts, f'refusing to write previews under {VERIFICATION_DIRECTORY}/: {output}')
    return _i33_Path(output)

def load_manifest(bundles):
    path = _i33_Path(bundles) / 'manifest-report.json'
    require(path.is_file(), f'missing bundle manifest: {path}')
    record = _i33_json.loads(path.read_text(encoding='utf-8'))
    require(record.get('schema') == _i33_SCHEMA, 'manifest schema mismatch')
    require(record.get('algorithm') == _i33_ALGORITHM, 'manifest algorithm mismatch')
    require(record.get('base') == 'synthetic_analytic', 'unexpected manifest base bed')
    require(record.get('status') == 'candidate', 'preview only accepts candidate bundles')
    return record

def measure(kind, result, entry, bundle_path):
    """Re-derive the geometry numbers and cross-check them against the manifest."""
    arrays = result['arrays']
    reference = arrays['reference_xyz_m']
    displacement = arrays['displacement_xyz_m']
    vertices = arrays['vertices_xyz_m']
    triangles = arrays['triangles']
    mask = arrays['protected_mask']
    rows, cols = reference.shape[:2]
    require(displacement.shape == reference.shape, f'{kind}: displacement shape mismatch')
    require(mask.shape == (rows, cols), f'{kind}: protected mask shape mismatch')
    require((rows, cols) == (int(entry['chart_rows']), int(entry['chart_cols'])), f'{kind}: chart shape {rows}x{cols} disagrees with the manifest')
    spacing_x = float(reference[0, 1, 0] - reference[0, 0, 0])
    spacing_z = float(reference[1, 0, 2] - reference[0, 0, 2])
    require(abs(spacing_x - spacing_z) <= 1e-09 * max(spacing_x, spacing_z), f'{kind}: non-uniform chart spacing')
    spacing_m = 0.5 * (spacing_x + spacing_z)
    declared_spacing = float(entry['spacing_m'])
    require(abs(spacing_m - declared_spacing) <= 1e-09 * max(1.0, declared_spacing), f'{kind}: spacing {spacing_m} disagrees with the manifest {declared_spacing}')
    relief = float(_i33_np.max(displacement[:, :, 1]))
    declared_relief = float(entry['max_relief_m'])
    require(abs(relief - declared_relief) <= 1e-09 * max(1.0, abs(declared_relief)), f'{kind}: max relief {relief} disagrees with the manifest {declared_relief}')
    collar = float(max(_i33_np.max(_i33_np.abs(displacement[0, :, 1])), _i33_np.max(_i33_np.abs(displacement[-1, :, 1])), _i33_np.max(_i33_np.abs(displacement[:, 0, 1])), _i33_np.max(_i33_np.abs(displacement[:, -1, 1]))))
    require(collar == 0.0, f'{kind}: chart collar displacement is {collar}, expected exactly 0')
    require(not _i33_np.any(displacement[:, :, 0] != 0) and (not _i33_np.any(displacement[:, :, 2] != 0)), f'{kind}: displacement must be vertical only')
    require(not _i33_np.any(displacement[mask] != 0), f'{kind}: a protected cell was displaced')
    require(not _i33_np.any(mask), f'{kind}: this bundle declares an empty protected mask')
    require(triangles.shape == (2 * (rows - 1) * (cols - 1), 3), f'{kind}: triangle count mismatch')
    require(_i33_np.array_equal(vertices, (reference + displacement).reshape(-1, 3)), f'{kind}: vertices are not reference plus displacement')
    digest = sha256_file(bundle_path)
    require(digest == entry['sha256'], f'{kind}: bundle bytes disagree with the manifest')
    local_identity = _i33_identity(arrays, result['metadata'])
    require(local_identity == result['identity_sha256'] == entry['identity_sha256'], f'{kind}: recomputed identity disagrees with the bundle or the manifest')
    require(result['metadata']['base'] == 'synthetic_analytic', f'{kind}: preview expects the synthetic analytic base bed')
    for flag in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'):
        require(result['metadata'][flag] is False, f'{kind}: status flag {flag} is not False')
    return {'kind': kind, 'file': _i33_Path(bundle_path).name, 'sha256': digest, 'identity_sha256': local_identity, 'chart_rows': rows, 'chart_cols': cols, 'spacing_m': spacing_m, 'max_relief_m': relief, 'collar_max_abs_m': collar, 'triangles': int(triangles.shape[0]), 'target_count': int(entry['target_count']), 'parameter_sources': entry['parameter_sources']}

def chart_extent(reference):
    """Physical metre extent derived from the array, not from a hand-written number."""
    return (float(reference[0, 0, 0]), float(reference[0, -1, 0]), float(reference[0, 0, 2]), float(reference[-1, 0, 2]))

def plot_plan(kind, reference, displacement, output, *, base_label='synthetic analytic base bed'):
    surface = reference[:, :, 1] + displacement[:, :, 1]
    rows, cols = surface.shape
    x0, x1, z0, z1 = chart_extent(reference)
    extent = (x0, x1, z0, z1)
    spacing_x = (x1 - x0) / (cols - 1)
    spacing_z = (z1 - z0) / (rows - 1)
    vmin = float(_i33_np.min(surface))
    vmax = float(_i33_np.max(surface))
    fig, ax = _i33_plt.subplots(figsize=(9, 7), dpi=140)
    image = ax.imshow(surface, origin='lower', extent=extent, cmap='terrain', vmin=vmin, vmax=vmax, aspect='equal')
    levels = _i33_np.linspace(vmin, vmax, 11)[1:-1]
    if levels.size:
        ax.contour(_i33_np.linspace(x0, x1, cols), _i33_np.linspace(z0, z1, rows), surface, levels=levels, colors='#101010', linewidths=0.4, alpha=0.65)
    bar = fig.colorbar(image, ax=ax, shrink=0.85)
    bar.set_label('elevation (m)')
    ax.set_xlabel('x (m)')
    ax.set_ylabel('z (m)')
    ax.set_title(f'{kind}: plan view over {base_label}')
    ax.text(0.01, 0.01, f'extent {x1 - x0:.1f} m x {z1 - z0:.1f} m  spacing {spacing_x:.3g} m', transform=ax.transAxes, fontsize=8, color='#202020')
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    _i33_plt.close(fig)
    return {'file': _i33_Path(output).name, 'sha256': sha256_file(output), 'extent_m': list(extent), 'spacing_x_m': spacing_x, 'spacing_z_m': spacing_z, 'colorbar_vmin_m': vmin, 'colorbar_vmax_m': vmax, 'surface_min_m': float(surface.min()), 'surface_max_m': float(surface.max()), 'contour_levels_m': [float(value) for value in levels]}

def plot_profile(kind, reference, displacement, output, *, base_label='synthetic analytic base bed'):
    relief_rows = _i33_np.max(displacement[:, :, 1], axis=1)
    row = int(_i33_np.argmax(relief_rows))
    x = reference[0, :, 0]
    base = reference[row, :, 1]
    final = base + displacement[row, :, 1]
    fig, ax = _i33_plt.subplots(figsize=(10, 5), dpi=140)
    ax.plot(x, base, color='#555555', lw=1.2, label=base_label)
    ax.fill_between(x, base, final, color='#c9a227', alpha=0.35, label='added field displacement')
    ax.plot(x, final, color='#7a4b00', lw=1.4, label='displaced surface')
    ax.set_xlabel('x (m)')
    ax.set_ylabel('elevation (m)')
    ax.set_title(f'{kind}: profile along z = {float(reference[row, 0, 2]):.1f} m (row of maximum relief)')
    ax.grid(alpha=0.25, lw=0.5)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    _i33_plt.close(fig)
    return {'file': _i33_Path(output).name, 'sha256': sha256_file(output), 'profile_row': row, 'profile_z_m': float(reference[row, 0, 2]), 'x_min_m': float(x.min()), 'x_max_m': float(x.max()), 'base_min_m': float(base.min()), 'base_max_m': float(base.max()), 'final_min_m': float(final.min()), 'final_max_m': float(final.max()), 'row_relief_max_m': float(relief_rows[row]), 'row_relief_sum_m': float(_i33_np.sum(displacement[row, :, 1]))}

def plot_solid(kind, reference, displacement, vertices, triangles, output):
    faces_total = int(triangles.shape[0])
    stride = max(1, int(_i33_math.ceil(faces_total / MAX_FACES)))
    faces = triangles[::stride]
    elevation = vertices[:, 1]
    vmin = float(elevation.min())
    vmax = float(elevation.max())
    cmap = _i33_matplotlib.colormaps['viridis']
    norm = _i33_mcolors.Normalize(vmin=vmin, vmax=vmax)
    points = vertices[faces]
    facecolors = cmap(norm(points[:, :, 1].mean(axis=1)))
    fig = _i33_plt.figure(figsize=(9, 7), dpi=140)
    ax = fig.add_subplot(projection='3d')
    ax.add_collection3d(_i33_Poly3DCollection(points, facecolors=facecolors, edgecolors='none', linewidths=0.0))
    x0, x1, z0, z1 = chart_extent(reference)
    ax.set_xlim(x0, x1)
    ax.set_ylim(z0, z1)
    ax.set_zlim(vmin, max(vmax, vmin + 1e-06))
    ax.set_box_aspect((max(x1 - x0, 1e-06), max(z1 - z0, 1e-06), max(vmax - vmin, 1e-06)))
    ax.view_init(elev=28, azim=-62)
    ax.set_xlabel('x (m)')
    ax.set_ylabel('z (m)')
    ax.set_zlabel('elevation (m)')
    ax.set_title(f'{kind}: displaced surface, every {stride}th triangle shaded')
    mappable = _i33_plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array(elevation)
    fig.colorbar(mappable, ax=ax, shrink=0.6, pad=0.12, label='elevation (m)')
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    _i33_plt.close(fig)
    return {'file': _i33_Path(output).name, 'sha256': sha256_file(output), 'faces_total': faces_total, 'face_stride': stride, 'faces_drawn': int(faces.shape[0]), 'elevation_min_m': vmin, 'elevation_max_m': vmax, 'x_range_m': [x0, x1], 'z_range_m': [z0, z1]}

def write_placeholder(name, label, output):
    fig, ax = _i33_plt.subplots(figsize=(8, 5), dpi=140)
    ax.axis('off')
    ax.text(0.5, 0.62, 'L1 volume path - preview pending (P5)', ha='center', va='center', fontsize=15, color='#333333')
    ax.text(0.5, 0.42, label, ha='center', va='center', fontsize=11, color='#444444')
    ax.text(0.5, 0.24, 'geometry not generated: needs the sampled rock Boolean route', ha='center', va='center', fontsize=9, color='#777777')
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    _i33_plt.close(fig)
    return {'file': _i33_Path(output).name, 'sha256': sha256_file(output), 'status': 'placeholder', 'label': label, 'geometry_verified': False, 'detail': 'L1 volume forms are implemented in P5; this panel only reserves the slot'}

def write_contact_sheet(records, placeholders, output):
    """One labelled slot per special-terrain category, embedding the plan panels.

    Every caption number is read from the geometry-derived record (never hand-written), and
    the sheet stores the sha256 of each embedded panel, so the composite is traceable back
    to the panels it embeds. A category that has no slot refuses the whole sheet.
    """
    slotted = {kind for _, _, kinds in CONTACT_SLOTS for kind in kinds}
    for label, kind in SIX_CATEGORIES:
        require(kind in slotted, f'category {label} has no contact-sheet slot')
    rows, columns = (len(CONTACT_SLOTS), max((len(slot[2]) for slot in CONTACT_SLOTS)))
    fig, axes = _i33_plt.subplots(rows, columns, figsize=(5.0 * columns, 4.6 * rows), dpi=140)
    entries = []
    for row_index, (row_label, grade, kinds) in enumerate(CONTACT_SLOTS):
        for column in range(columns):
            ax = axes[row_index, column]
            ax.axis('off')
            if column >= len(kinds):
                continue
            kind = kinds[column]
            if kind in records:
                record = records[kind]
                panel = record['panels']['plan']
                x0, x1, z0, z1 = panel['extent_m']
                require(abs(x1 - x0 - (record['chart_cols'] - 1) * record['spacing_m']) <= 1e-09 * max(1.0, x1 - x0), f'{kind}: contact-sheet extent disagrees with shape x spacing')
                caption = f"{CATEGORY_LABELS[kind]} [{grade}]\nextent {x1 - x0:.1f} x {z1 - z0:.1f} m | spacing {record['spacing_m']:.3g} m | relief {record['max_relief_m']:.6g} m"
                status, panel_sha, panel_file = ('geometry', panel['sha256'], panel['file'])
            else:
                placeholder = placeholders[kind]
                caption = f'{CATEGORY_LABELS[kind]} [{grade}]\nvolume geometry pending (P5): slot reserved only'
                status, panel_sha, panel_file = ('placeholder', placeholder['sha256'], placeholder['file'])
            image_path = _i33_Path(output) / panel_file
            digest = sha256_file(image_path)
            require(digest == panel_sha, f'{kind}: contact sheet would embed a changed panel {panel_file}')
            image = _i33_plt.imread(image_path)
            require(image.ndim == 3 and min(image.shape[:2]) >= 64, f'{kind}: unreadable panel image {panel_file}')
            ax.imshow(image, interpolation='nearest')
            ax.set_title(caption, fontsize=9)
            entries.append({'row': row_index, 'column': column, 'row_label': row_label, 'kind': kind, 'status': status, 'panel_file': panel_file, 'panel_sha256': digest, 'caption': caption})
    fig.suptitle('Six special-terrain categories: ' + '; '.join((label for label, _ in SIX_CATEGORIES)), fontsize=11)
    fig.tight_layout()
    sheet_path = _i33_Path(output) / CONTACT_SHEET
    fig.savefig(sheet_path, metadata=PNG_META)
    _i33_plt.close(fig)
    return {'file': CONTACT_SHEET, 'sha256': sha256_file(sheet_path), 'categories': [{'label': label, 'kind': kind} for label, kind in SIX_CATEGORIES], 'slots': entries, 'note': 'captions are formatted from the geometry-derived records; each slot records the sha256 of the panel it embeds'}

def preview_kind(kind, bundles, entries, output):
    entry = entries[kind]
    bundle_path = _i33_Path(bundles) / entry['file']
    result = _i33_load_special_form_vdm(bundle_path, expected_sha256=entry['sha256'], expected_identity=entry['identity_sha256'])
    record = measure(kind, result, entry, bundle_path)
    arrays = result['arrays']
    panels = {'plan': plot_plan(kind, arrays['reference_xyz_m'], arrays['displacement_xyz_m'], output / f'{kind}-a-plan.png'), 'profile': plot_profile(kind, arrays['reference_xyz_m'], arrays['displacement_xyz_m'], output / f'{kind}-b-profile.png'), 'solid': plot_solid(kind, arrays['reference_xyz_m'], arrays['displacement_xyz_m'], arrays['vertices_xyz_m'], arrays['triangles'], output / f'{kind}-c-solid.png')}
    x0, x1, z0, z1 = panels['plan']['extent_m']
    require(abs(x1 - x0 - (record['chart_cols'] - 1) * record['spacing_m']) <= 1e-09 * max(1.0, x1 - x0), f'{kind}: plan extent disagrees with shape x spacing')
    require(abs(z1 - z0 - (record['chart_rows'] - 1) * record['spacing_m']) <= 1e-09 * max(1.0, z1 - z0), f'{kind}: plan extent disagrees with shape x spacing')
    require(abs(panels['plan']['colorbar_vmax_m'] - record['max_relief_m']) <= 1e-09 * max(1.0, record['max_relief_m']), f'{kind}: colour range disagrees with the measured relief')
    require(abs(panels['profile']['row_relief_max_m'] - record['max_relief_m']) <= 1e-09 * max(1.0, record['max_relief_m']), f'{kind}: profile row does not carry the maximum relief')
    require(abs(panels['solid']['elevation_max_m'] - record['max_relief_m']) <= 1e-09 * max(1.0, record['max_relief_m']), f'{kind}: 3D colour range disagrees with the measured relief')
    record['panels'] = panels
    record['status'] = 'illustrated'
    record['base'] = result['metadata']['base']
    record['flags'] = {flag: result['metadata'][flag] for flag in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified')}
    return record

def _entry_preview_special_terrain_forms(argv=None):
    parser = _i33_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundles', type=_i33_Path, default=DEFAULT_BUNDLES)
    parser.add_argument('--output', type=_i33_Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--kinds', default=','.join(sorted(_i33_KINDS)))
    args = parser.parse_args(argv)
    requested = [value for value in args.kinds.split(',') if value]
    unknown = sorted(set(requested) - _i33_KINDS)
    if unknown:
        raise SystemExit(f'unknown kinds: {unknown}')
    output = guard_output(args.output)
    manifest = load_manifest(args.bundles)
    entries = manifest['forms']
    missing = sorted(set(requested) - set(entries))
    if missing:
        raise SystemExit(f'bundles missing from the manifest: {missing}')
    output.mkdir(parents=True, exist_ok=True)
    report = {'schema': _i33_SCHEMA, 'algorithm': _i33_ALGORITHM, 'base': 'synthetic_analytic', 'status': 'candidate', 'sample_seed': SAMPLE_SEED, 'paths_omitted': True, 'note': 'no timestamp and no directory path is recorded so two runs compare equal', 'claims': {'real_terrain_reconstruction': False, 'publishable': False, 'hydraulic_ready': False, 'natural_outlet_verified': False}, 'forms': {}, 'l1_placeholders': {}}
    for kind in sorted(set(requested)):
        record = preview_kind(kind, args.bundles, entries, output)
        report['forms'][kind] = record
        print(f"{kind}: {record['chart_rows']}x{record['chart_cols']} @ {record['spacing_m']:g} m relief {record['max_relief_m']:.6g} m collar {record['collar_max_abs_m']:.6g} m faces {record['panels']['solid']['faces_drawn']}/{record['panels']['solid']['faces_total']}")
    for name, label in L1_PLACEHOLDERS:
        report['l1_placeholders'][name] = write_placeholder(name, label, output / f'{name}.png')
        print(f'{name}: placeholder')
    report['contact_sheet'] = write_contact_sheet(report['forms'], report['l1_placeholders'], output)
    print(f"contact sheet: {CONTACT_SHEET} sha256 {report['contact_sheet']['sha256']} slots {len(report['contact_sheet']['slots'])}")
    report_path = output / 'report.json'
    report_path.write_text(_i33_json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'report: {report_path.name} sha256 {sha256_file(report_path)}')
    return 0
_i34_matplotlib.use('Agg')
_i34_sys.path.insert(0, str(ROOT))
SOURCE_PATH = 'verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz'
SOURCE = dict(path=str(ROOT / SOURCE_PATH), expected_sha256='36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422', expected_identity='cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998')
PREVIEW_TD_SPECIAL_TERRAIN_DEFAULT_OUTPUT = _i34_Path('.scratch/special-terrain/td-adapter-20261019')
ALL_FLAGS = ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified')
WINDOW_SIZE_M = 960.0
WINDOW_CENTER_M_XZ = [-177600.0, 67680.0]
POSITION_ASSUMPTION = 'target centres sit at the selected window centre; the adapter and this tool choose no real-world site and no site was surveyed'
CHANNEL_SELECTION = 'empty edge selection: the passive special-terrain bed is the plain native bilinear bed, so the adapter cuts no artificial channel through the landform; the separate shared-bed channel ladder in tools/diagnose_single_domain_fine.py is deliberately not reproduced here'
FOOT_ELEVATION_BASIS = 'minimum bed elevation over the selected window, declared by this caller; the pinned hierarchy carries no surveyed landform foot and the preset foot of 0 m is a synthetic base-bed value, so the foot is an assumption and not a measurement'
FILL_ONLY_SEMANTICS = 'the form fills terrain up to the declared absolute surface and never excavates (displacement = max(declared relief - bed, 0)); on a sloping real bed the emerged footprint is therefore asymmetric and can be smaller than the nominal ellipse'

def _finite_number(value, name):
    if type(value) not in (int, float) or not _i34_math.isfinite(value):
        raise ValueError(f'invalid {name}')

def preview_td_special_terrain_guard_output(output):
    parts = [part.lower() for part in _i34_Path(output).resolve().parts]
    require(VERIFICATION_DIRECTORY not in parts, f'refusing to write under {VERIFICATION_DIRECTORY}/: {output}')
    return _i34_Path(output)

def replace_target(target, center_x_m, center_z_m, base_elevation_m):
    return _i34_FormTarget(target.target_id, center_x_m, center_z_m, base_elevation_m, target.height_m, target.radius_x_m, target.radius_z_m, target.source_grade, target.source_ref)

def centred_recipe(kind, *, center_x_m, center_z_m, base_elevation_m, size_x_m, size_z_m, spacing_m, keep='all'):
    """The declared preset with its targets moved to the window centre and its foot set.

    Radii, heights, seed, collar margin and the target subset stay exactly the preset
    values; the chart extent and spacing are taken from the real chart being built instead,
    so the saved recipe describes the bed it was actually burned into rather than the
    synthetic preset bed. ``base_elevation_m`` must be the caller's declared absolute foot:
    a preset foot of 0 m would bury the whole form under the pinned bed and yield a silent
    all-zero displacement, which ``case_record`` would then have to report as a failed case.
    ``keep="tallest"`` takes a declared subset: the single tallest preset target, for
    windows too small to hold the whole field.
    """
    _finite_number(base_elevation_m, 'foot elevation')
    for name, value in (('chart size x', size_x_m), ('chart size z', size_z_m), ('chart spacing', spacing_m)):
        _finite_number(value, name)
        if value <= 0:
            raise ValueError(f'invalid {name}')
    preset = _i34_form_preset(kind)
    chosen = preset.targets
    subset = 'full preset'
    if keep == 'tallest':
        chosen = (max(preset.targets, key=lambda target: target.height_m),)
        subset = f'single tallest preset target of {len(preset.targets)}; the remaining field does not fit the window'
    elif keep != 'all':
        raise ValueError('invalid preset subset selector')
    targets = tuple((replace_target(target, center_x_m, center_z_m, base_elevation_m) for target in chosen))
    return (preset, _i34_SpecialFormRecipe(preset.kind, size_x_m, size_z_m, spacing_m, preset.collar_margin_m, targets, preset.seed), subset)

def chart_center_m_xz(reference):
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    return (0.5 * (float(x.min()) + float(x.max())), 0.5 * (float(z.min()) + float(z.max())))

def chart_size_m_xz(reference):
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    return (float(x.max()) - float(x.min()), float(z.max()) - float(z.min()))

def _footprint_bed_min(reference, recipe):
    """Lowest bed elevation inside every nominal target ellipse.

    Reported as the floor each declared foot was set against, per target. The emerged
    outline of a fill-only form is instead set by the *highest* bed under the ellipse, so
    this number is a declaration aid and not the extent of the result.
    """
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    bed = reference[:, :, 1]
    floors = []
    for target in recipe.targets:
        across = (x - target.center_x_m) / target.radius_x_m
        along = (z - target.center_z_m) / target.radius_z_m
        inside = _i34_np.sqrt(across * across + along * along) <= 1.0
        if not inside.any():
            raise ValueError(f'target {target.target_id} has no chart cell inside its footprint')
        floors.append(float(bed[inside].min()))
    return floors

def build_case(kind, hierarchy, *, spacing_m, requested_size_m, window_center_m_xz, keep='all'):
    native_shape = hierarchy['arrays']['height_m'].shape
    native_origin = hierarchy['metadata']['origin_m_xz']
    window = _i34_select_native_window(center_m_xz=window_center_m_xz, size_m_xz=[requested_size_m] * 2, spacing_m=spacing_m, native_shape=native_shape, native_origin_m_xz=native_origin)
    chart = _i34_build_td_form_chart(hierarchy, window=window, spacing_m=spacing_m, source_hierarchy_sha256=SOURCE['expected_sha256'], selected_edge_cell_ids=_i34_np.zeros((0, 2), dtype=_i34_np.int64), channel_policy='reject')
    reference = chart['chart_reference_xyz_m']
    center_x_m, center_z_m = chart_center_m_xz(reference)
    size_x_m, size_z_m = chart_size_m_xz(reference)
    foot_elevation_m = float(_i34_np.min(reference[:, :, 1]))
    preset, recipe, subset = centred_recipe(kind, center_x_m=center_x_m, center_z_m=center_z_m, base_elevation_m=foot_elevation_m, size_x_m=size_x_m, size_z_m=size_z_m, spacing_m=float(window['spacing_m']), keep=keep)
    result = _i34_build_special_form_vdm(reference, recipe=recipe, protected_mask=chart['protected_mask'], source_identity=chart['source_identity'], protection_identity=chart['protection_identity'], base_kind='td_fine_bed')
    require(result['metadata']['base'] == 'td_fine_bed', 'form did not record the TD bed base')
    require(_i34_validate_special_form_vdm(result), 'form bundle failed its own validator')
    placement = {'kind': kind, 'preset_kind': preset.kind, 'preset_subset': subset, 'target_count': len(recipe.targets), 'target_center_m_xz': [center_x_m, center_z_m], 'target_ids': [target.target_id for target in recipe.targets], 'preset_radius_x_m': [target.radius_x_m for target in recipe.targets], 'preset_height_m': [target.height_m for target in recipe.targets], 'declared_foot_elevation_m': foot_elevation_m, 'declared_foot_basis': FOOT_ELEVATION_BASIS, 'window_bed_min_m': foot_elevation_m, 'window_bed_max_m': float(_i34_np.max(reference[:, :, 1])), 'nominal_footprint_bed_min_m': _footprint_bed_min(reference, recipe), 'fill_only_semantics': FILL_ONLY_SEMANTICS, 'placement_semantics': POSITION_ASSUMPTION, 'parameter_sources': result['metadata']['parameter_sources'][kind]}
    return {'window': window, 'chart': chart, 'result': result, 'recipe': recipe, 'placement': placement}

def case_record(kind, case, bundle_path):
    result = case['result']
    arrays = result['arrays']
    reference = arrays['reference_xyz_m']
    displacement = arrays['displacement_xyz_m']
    chart_record = case['chart']['record']
    rows, cols = reference.shape[:2]
    relief = float(_i34_np.max(displacement[:, :, 1]))
    require(relief > 0.0, f'{kind}: form produced no relief')
    collar = float(max(_i34_np.max(_i34_np.abs(displacement[0, :, 1])), _i34_np.max(_i34_np.abs(displacement[-1, :, 1])), _i34_np.max(_i34_np.abs(displacement[:, 0, 1])), _i34_np.max(_i34_np.abs(displacement[:, -1, 1]))))
    require(collar == 0.0, f'{kind}: collar displacement is {collar}, expected exactly 0')
    require(_i34_np.array_equal(arrays['vertices_xyz_m'], (reference + displacement).reshape(-1, 3)), f'{kind}: vertices are not reference plus displacement')
    require(not _i34_np.any(displacement[cases_mask(case)] != 0), f'{kind}: a protected cell was displaced')
    require(_i34_np.array_equal(reference, case['chart']['chart_reference_xyz_m']), f'{kind}: form reference chart is not the adapter chart')
    require(_i34_np.array_equal(arrays['protected_mask'], case['chart']['protected_mask']), f'{kind}: form protected mask is not the adapter mask')
    metadata = result['metadata']
    for key in ('source_identity', 'protection_identity'):
        require(metadata[key] == case['chart'][key], f'{kind}: form {key} does not match the adapter chart')
    require(metadata['source_identity'] == chart_record['identity_chain']['chart_source_identity'], f'{kind}: chart source identity disagrees with its own chain record')
    require(metadata['protection_identity'] == chart_record['identity_chain']['chart_protection_identity'], f'{kind}: chart protection identity disagrees with its own chain record')
    require(result['identity_sha256'] == _i34_identity(arrays, metadata), f'{kind}: re-derived form identity disagrees with the declared identity')
    declared = {target.target_id: target for target in case['recipe'].targets}
    for entry in metadata['recipe']['targets']:
        target = declared[entry['target_id']]
        require(entry['base_elevation_m'] == target.base_elevation_m, f'{kind}: saved target foot disagrees with the declared recipe')
    require(float(_i34_np.min(reference[:, :, 1])) == float(case['placement']['declared_foot_elevation_m']), f'{kind}: declared foot is not the window bed minimum')
    require(relief <= max((float(value) for value in case['placement']['preset_height_m'])) + 1e-09, f'{kind}: relief exceeds the declared preset height')
    digest = _i34_file_sha256(bundle_path)
    return {'kind': kind, 'file': _i34_Path(bundle_path).name, 'sha256': digest, 'identity_sha256': result['identity_sha256'], 'form_schema': _i34_FORM_SCHEMA, 'form_algorithm': _i34_ALGORITHM, 'adapter_schema': _i34_ADAPTER_SCHEMA, 'chart_rows': rows, 'chart_cols': cols, 'spacing_m': float(case['window']['spacing_m']), 'max_relief_m': relief, 'collar_max_abs_m': collar, 'triangles': int(arrays['triangles'].shape[0]), 'target_count': len(case['recipe'].targets), 'declared_flags': {flag: result['metadata'][flag] for flag in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified')}, 'base': result['metadata']['base'], 'window': case['window'], 'chart_record': chart_record, 'placement': case['placement']}

def cases_mask(case):
    return case['chart']['protected_mask']

def _entry_preview_td_special_terrain(argv=None):
    parser = _i34_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=_i34_Path, default=PREVIEW_TD_SPECIAL_TERRAIN_DEFAULT_OUTPUT)
    parser.add_argument('--kinds', default='volcanic_plug,karst_tower_field')
    args = parser.parse_args(argv)
    output = preview_td_special_terrain_guard_output(args.output)
    hierarchy = _i34_load_basin_hierarchy(**SOURCE)
    require(_i34_file_sha256(SOURCE['path']) == SOURCE['expected_sha256'], 'pinned hierarchy changed on disk')
    require(hierarchy['identity_sha256'] == SOURCE['expected_identity'], 'pinned hierarchy identity changed')
    report = {'source': {'path': SOURCE_PATH, 'expected_sha256': SOURCE['expected_sha256'], 'expected_identity': SOURCE['expected_identity']}, 'adapter_schema': _i34_ADAPTER_SCHEMA, 'form_schema': _i34_FORM_SCHEMA, 'form_algorithm': _i34_ALGORITHM, 'sample_seed': SAMPLE_SEED, 'position_assumption': POSITION_ASSUMPTION, 'channel_selection': CHANNEL_SELECTION, 'foot_elevation_basis': FOOT_ELEVATION_BASIS, 'fill_only_semantics': FILL_ONLY_SEMANTICS, 'paths_omitted': True, 'note': 'no timestamp and no absolute path is recorded so two runs compare equal', 'claims': {'real_terrain_reconstruction': False, 'publishable': False, 'natural_outlet_certified': False, 'hydraulic_ready': False, 'foot_elevation_surveyed': False, 'preset_foot_is_synthetic': True, 'excavation_modelled': False, **{flag: False for flag in ALL_FLAGS}}, 'cases': {}}
    requested = [value for value in args.kinds.split(',') if value]
    output.mkdir(parents=True, exist_ok=True)
    for kind in requested:
        if kind == 'volcanic_plug':
            spacing_m, requested_size, keep = (4.0, WINDOW_SIZE_M, 'all')
        elif kind == 'karst_tower_field':
            spacing_m, requested_size, keep = (1.0, 240.0, 'tallest')
        else:
            raise SystemExit(f'no declared adapter ladder for kind {kind}')
        case = build_case(kind, hierarchy, spacing_m=spacing_m, requested_size_m=requested_size, window_center_m_xz=WINDOW_CENTER_M_XZ, keep=keep)
        bundle_path = output / f'{kind}-td-bundle.npz'
        if bundle_path.exists():
            bundle_path.unlink()
        _i34_save_special_form_vdm(bundle_path, case['result'])
        record = case_record(kind, case, bundle_path)
        arrays = case['result']['arrays']
        base_label = f"pinned TD {case['window']['spacing_m']:g} m fine bed {case['window']['fine_shape_zx'][1]}x{case['window']['fine_shape_zx'][0]}"
        panels = {'plan': plot_plan(kind, arrays['reference_xyz_m'], arrays['displacement_xyz_m'], output / f'{kind}-td-a-plan.png', base_label=base_label), 'profile': plot_profile(kind, arrays['reference_xyz_m'], arrays['displacement_xyz_m'], output / f'{kind}-td-b-profile.png', base_label=base_label), 'solid': plot_solid(kind, arrays['reference_xyz_m'], arrays['displacement_xyz_m'], arrays['vertices_xyz_m'], arrays['triangles'], output / f'{kind}-td-c-solid.png')}
        record['panels'] = panels
        surface = arrays['reference_xyz_m'][:, :, 1] + arrays['displacement_xyz_m'][:, :, 1]
        require(abs(panels['plan']['colorbar_vmin_m'] - float(surface.min())) <= 1e-09 * max(1.0, abs(float(surface.min()))), f'{kind}: plan colour floor disagrees with the plotted surface')
        require(abs(panels['plan']['colorbar_vmax_m'] - float(surface.max())) <= 1e-09 * max(1.0, abs(float(surface.max()))), f'{kind}: plan colour ceiling disagrees with the plotted surface')
        require(abs(panels['plan']['extent_m'][1] - panels['plan']['extent_m'][0] - (record['chart_cols'] - 1) * record['spacing_m']) <= 1e-09 * 960.0, f'{kind}: plan extent disagrees with shape x spacing')
        require(abs(panels['profile']['row_relief_max_m'] - record['max_relief_m']) <= 1e-09 * max(1.0, record['max_relief_m']), f'{kind}: profile row does not carry the maximum relief')
        require(abs(panels['solid']['elevation_max_m'] - float(surface.max())) <= 1e-09 * max(1.0, abs(float(surface.max()))), f'{kind}: 3D colour range disagrees with the plotted surface')
        report['cases'][kind] = record
        print(f"{kind}: {record['chart_rows']}x{record['chart_cols']} @ {record['spacing_m']:g} m relief {record['max_relief_m']:.6g} m collar {record['collar_max_abs_m']:.6g} m bed {case['window']['fine_shape_zx'][1]}x{case['window']['fine_shape_zx'][0]} snap {case['window']['maximum_snap_observed_m']:.6g} m")
    report_path = output / 'report.json'
    report_path.write_text(_i34_json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'report: {report_path.name} sha256 {sha256_file(report_path)}')
    return 0

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'forms': '_entry_preview_special_terrain_forms', 'td': '_entry_preview_td_special_terrain', 'pillars': 'main_landform', 'sinkhole': 'sinkhole_main', 'cave-bridge': 'cave_bridge_main', 'rock-eggs': 'rock_eggs_main', 'uluru-flare': 'uluru_flare_main'}
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
