"""Static full-grid review export; no routing, weather or surface advancement."""

import json
import os
import shutil
import tempfile
from pathlib import Path
import numpy as np
from terrain_pipeline.runoff import _strict_json as _strict_json
from terrain_pipeline.regional_surface_source import validate_source
from terrain_pipeline.common_infra import publish_bytes, file_sha256


def read_bounded_json(path, *, expected_sha256, max_bytes=16 * 1024 * 1024):
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError('JSON byte budget exceeded before read')
    if file_sha256(path) != expected_sha256:
        raise ValueError('external JSON hash mismatch')
    return _strict_json(path.read_text(encoding='utf-8'))


def validate_snapshot_index(index, *, source_identity):
    if (not isinstance(index, dict) or set(index) != {'schema', 'source_identity', 'cases', 'fixture_only'} or
            index['schema'] != 'regional-saved-B-mesh-cases-v1' or index['source_identity'] != source_identity or
            type(index['fixture_only']) is not bool or not isinstance(index['cases'], list) or not 1 <= len(index['cases']) <= 8):
        raise ValueError('known bound snapshot index schema required')
    seen = set()
    paths = {}
    for case in index['cases']:
        case_keys = {'id', 'model', 'requested_time_s', 'committed_time_s', 'status', 'failure', 'snapshots', 'B_validation'}
        optional_case = {'boundary_description', 'water_summary', 'sampling', 'boundary_faces'}
        if not isinstance(case, dict) or not case_keys.issubset(case) or set(case) - case_keys - optional_case:
            raise ValueError('exact scenario fields required')
        if not isinstance(case['id'], str) or not case['id'] or case['id'] in seen:
            raise ValueError('unique scenario IDs required')
        seen.add(case['id'])
        requested, committed = case['requested_time_s'], case['committed_time_s']
        if (any(type(value) not in (int, float) or not np.isfinite(value) for value in (requested, committed)) or
                not 0 <= committed <= requested <= 259200):
            raise ValueError('finite requested/committed physical time required')
        if (case['status'] not in ('completed', 'refused') or
                (case['status'] == 'completed' and (committed != requested or case['failure'] is not None)) or
                (case['status'] == 'refused' and (committed >= requested or
                    not isinstance(case['failure'], (str, dict)) or not case['failure']))):
            raise ValueError('case status must agree with committed time and failure')
        if isinstance(case['failure'], dict):
            failure = case['failure']
            if (not isinstance(failure.get('reason'), str) or not failure['reason'] or
                    type(failure.get('time_s')) not in (int, float) or
                    not np.isfinite(failure['time_s']) or failure['time_s'] < committed or
                    failure['time_s'] > requested):
                raise ValueError('failure reason and physical failure time required')
        if 'water_summary' in case:
            if not isinstance(case['boundary_description'], str) or not case['boundary_description']:
                raise ValueError('explicit saved case boundary description required')
            summary = case['water_summary']
            allowed = {'initial_volume_m3', 'supplied_m3', 'boundary_input_m3', 'boundary_output_m3', 'final_volume_m3'}
            if (not isinstance(summary, dict) or set(summary) - allowed or
                    any(type(v) not in (int, float) or not np.isfinite(v) or v < 0 for v in summary.values())):
                raise ValueError('known finite nonnegative water summary required')
        if 'sampling' in case and (not isinstance(case['sampling'], str) or not case['sampling']):
            raise ValueError('explicit saved sampling description required')
        if 'boundary_faces' in case:
            faces = case['boundary_faces']
            if not isinstance(faces, list) or len(faces) > 1024:
                raise ValueError('bounded saved boundary annotations required')
            seen_faces = set()
            for face in faces:
                if (not isinstance(face, dict) or set(face) != {'face_id', 'cell_flat', 'kind'} or
                        type(face['face_id']) is not int or not 0 <= face['face_id'] < 1024 or
                        face['face_id'] in seen_faces or type(face['cell_flat']) is not int or
                        not 0 <= face['cell_flat'] < 65536 or face['kind'] != 2):
                    raise ValueError('valid unique prescribed-stage boundary annotations required')
                row, column = divmod(face['cell_flat'], 256)
                if row not in (0, 255) and column not in (0, 255):
                    raise ValueError('boundary annotation cannot be an interior cell')
                seen_faces.add(face['face_id'])
        if (not isinstance(case['B_validation'], str) or not case['B_validation'] or
                not isinstance(case['status'], str) or not case['status'] or
                not isinstance(case['model'], str) or not case['model']):
            raise ValueError('external B validation evidence and solver model required')
        snapshots = case['snapshots']
        if not isinstance(snapshots, list) or not 1 <= len(snapshots) <= 300:
            raise ValueError('bounded saved states required')
        previous = -1.
        for state in snapshots:
            state_keys = {'time_s', 'path', 'sha256', 'volume_m3'}
            if not isinstance(state, dict) or set(state) not in (state_keys | {'max_depth_m'}, state_keys | {'display_max_depth_m'}):
                raise ValueError('exact saved state fields required')
            depth_key = 'display_max_depth_m' if 'display_max_depth_m' in state else 'max_depth_m'
            for key in ('time_s', 'volume_m3', depth_key):
                value = state[key]
                if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
                    raise ValueError('finite nonnegative saved water/time required')
            if not previous < state['time_s'] <= committed:
                raise ValueError('strictly increasing saved time required')
            previous = state['time_s']
            name = state['path']
            if not isinstance(name, str) or Path(name).name != name or any(char in name for char in '/\\:') or not name.endswith('.json'):
                raise ValueError('mesh paths must be safe JSON basenames')
            digest = state['sha256']
            if not isinstance(digest, str) or len(digest) != 64 or any(letter not in '0123456789abcdef' for letter in digest):
                raise ValueError('external mesh SHA required')
            if name in paths and paths[name] != digest:
                raise ValueError('one mesh basename cannot have conflicting hashes')
            paths[name] = digest
        if snapshots[0]['time_s'] != 0 or snapshots[-1]['time_s'] != committed:
            raise ValueError('saved initial and committed final states required')
    return index


def validate_saved_mesh(mesh, *, source_identity):
    simple_keys = {'source_identity', 'vertices_xyz_m', 'triangles'}
    display_keys = simple_keys | {'time_s', 'display_cell_ids', 'display_threshold_m', 'omitted_wet_cells',
        'omitted_volume_m3', 'solver_volume_m3', 'display_volume_m3', 'representation', 'physical_archive'}
    if not isinstance(mesh, dict) or set(mesh) not in (simple_keys, display_keys) or mesh['source_identity'] != source_identity:
        raise ValueError('known source-bound mesh schema required')
    if set(mesh) == display_keys:
        if not isinstance(mesh['vertices_xyz_m'], list) or not isinstance(mesh['triangles'], list):
            raise ValueError('display geometry lists required')
        for key in ('time_s', 'display_threshold_m', 'omitted_volume_m3', 'solver_volume_m3', 'display_volume_m3'):
            value = mesh[key]
            if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
                raise ValueError('finite nonnegative display water metadata required')
        ids = mesh['display_cell_ids']
        if (not isinstance(ids, list) or len(ids) > 65536 or
                any(type(cell) is not int or not 0 <= cell < 65536 for cell in ids) or
                len(set(ids)) != len(ids) or type(mesh['omitted_wet_cells']) is not int or
                not 0 <= mesh['omitted_wet_cells'] <= 65536 - len(ids) or
                len(mesh['vertices_xyz_m']) != 4 * len(ids) or len(mesh['triangles']) != 2 * len(ids)):
            raise ValueError('display support/quad counts invalid')
        if not np.isclose(mesh['display_volume_m3'] + mesh['omitted_volume_m3'], mesh['solver_volume_m3'], rtol=1e-12, atol=1e-8):
            raise ValueError('display plus omitted storage must match solver storage')
        if (mesh['representation'] != 'independent_flat_cell_top_quads_not_continuous_shared_stage_surface' or
                not isinstance(mesh['physical_archive'], str) or Path(mesh['physical_archive']).name != mesh['physical_archive'] or
                any(char in mesh['physical_archive'] for char in '/\\:') or not mesh['physical_archive'].endswith('.npz')):
            raise ValueError('known top-quad representation and physical archive basename required')
    if (not isinstance(mesh['vertices_xyz_m'], list) or len(mesh['vertices_xyz_m']) > 300000 or
            not isinstance(mesh['triangles'], list) or len(mesh['triangles']) > 400000):
        raise ValueError('mesh count budget exceeded before array allocation')
    vertices = np.asarray(mesh['vertices_xyz_m'], dtype=np.float64)
    triangles = np.asarray(mesh['triangles'])
    if vertices.size == 0:
        vertices = vertices.reshape(0, 3)
    if triangles.size == 0:
        triangles = triangles.astype(np.int64).reshape(0, 3)
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) > 300000 or not np.isfinite(vertices).all() or
            triangles.ndim != 2 or triangles.shape[1] != 3 or len(triangles) > 400000 or
            triangles.dtype.kind not in 'iu' or (triangles < 0).any() or (triangles >= len(vertices)).any()):
        raise ValueError('bounded finite mesh and legal triangle indices required')
    if set(mesh) == display_keys:
        expected = (np.array([[0, 2, 1], [0, 3, 2]])[None] +
            np.arange(len(mesh['display_cell_ids']))[:, None, None] * 4).reshape(-1, 3)
        if not np.array_equal(triangles, expected):
            raise ValueError('saved display requires exact independent top-quad topology')
    return mesh


def adapt_B_index(path, *, expected_sha256, source_identity, case_metadata, case_id, trusted_height,
                  expected_case_manifest_sha256, origin_m_xz=None,
                  boundary_description='Engineering boundary; see pinned case geometry', representation_id=None,
                  boundary_faces=None):
    index = read_bounded_json(path, expected_sha256=expected_sha256, max_bytes=262144)
    if representation_id is not None:
        validate_snapshot_index(index, source_identity=source_identity)
        matches = [case for case in index['cases'] if case['id'] == representation_id]
        if len(matches) != 1 or index['fixture_only']:
            raise ValueError('one real saved representation ID required')
        representation = matches[0]
        snapshots = []
        threshold = None
        for state in representation['snapshots']:
            mesh = validate_saved_mesh(read_bounded_json(Path(path).parent / state['path'],
                expected_sha256=state['sha256']), source_identity=source_identity)
            if 'omitted_volume_m3' not in mesh:
                raise ValueError('real display representation must retain omitted storage statistics')
            if threshold is not None and threshold != mesh['display_threshold_m']:
                raise ValueError('one representation cannot mix display thresholds')
            threshold = mesh['display_threshold_m']
            if mesh['solver_volume_m3'] != state['volume_m3']:
                raise ValueError('representation index total volume mismatch')
            snapshots.append({'time_s': state['time_s'], 'path': state['path'], 'sha256': state['sha256'],
                'omitted_volume_m3': mesh['omitted_volume_m3'], 'solver_volume_m3': mesh['solver_volume_m3']})
        index = {'schema': 'regional-saved-B-mesh-index-v1', 'source_identity': source_identity,
            'status': 'B_static_validated_saved_mesh', 'source_case_manifest_sha256': expected_case_manifest_sha256,
            'source_case_directory': 'externally pinned by trusted run index', 'snapshots': snapshots,
            'display_threshold_m': threshold, 'sampling': 'B saved keyframes, not full trajectory',
            'representation': 'independent_flat_cell_top_quads_not_continuous_shared_stage_surface'}
    keys = {'schema', 'source_identity', 'status', 'source_case_manifest_sha256', 'source_case_directory',
        'snapshots', 'display_threshold_m', 'sampling', 'representation'}
    optional = {'display_refusals', 'representation_export_failures'}
    if (not isinstance(index, dict) or not keys.issubset(index) or set(index) - keys - optional or
            index['schema'] != 'regional-saved-B-mesh-index-v1' or index['source_identity'] != source_identity or
            index['status'] != 'B_static_validated_saved_mesh' or
            index['source_case_manifest_sha256'] != expected_case_manifest_sha256):
        raise ValueError('known B single-case saved index required')
    if (not isinstance(index['snapshots'], list) or not 1 <= len(index['snapshots']) <= 300 or
            type(index['display_threshold_m']) not in (int, float) or
            not np.isfinite(index['display_threshold_m']) or index['display_threshold_m'] < 0):
        raise ValueError('bounded B saved snapshots and finite display threshold required')
    if index.get('display_refusals'):
        raise ValueError('incomplete display export: preserve refusal evidence, do not invent missing states')
    if case_metadata['source_identity'] != source_identity:
        raise ValueError('B case metadata source mismatch')
    snapshots = []
    for state in index['snapshots']:
        if set(state) != {'time_s', 'path', 'sha256', 'omitted_volume_m3', 'solver_volume_m3'}:
            raise ValueError('exact B saved snapshot fields required')
        name = state['path']
        if not isinstance(name, str) or Path(name).name != name or any(char in name for char in '/\\:'):
            raise ValueError('safe B snapshot basename required')
        mesh = validate_saved_mesh(read_bounded_json(Path(path).parent / name, expected_sha256=state['sha256']),
            source_identity=source_identity)
        if (mesh.get('time_s') != state['time_s'] or mesh.get('omitted_volume_m3') != state['omitted_volume_m3'] or
                mesh.get('solver_volume_m3') != state['solver_volume_m3'] or
                mesh.get('display_threshold_m') != index['display_threshold_m']):
            raise ValueError('B mesh/index saved time and volume mismatch')
        ids = mesh['display_cell_ids']
        vertices = np.asarray(mesh['vertices_xyz_m'], dtype=np.float64).reshape(-1, 4, 3)
        depth = vertices[:, 0, 1] - trusted_height.ravel()[ids]
        if (depth < 0).any() or (vertices[:, :, 1] != vertices[:, :1, 1]).any():
            raise ValueError('display water stage below source H0')
        if origin_m_xz is not None:
            rows, columns = np.divmod(ids, 256)
            expected_x = origin_m_xz[0] + columns[:, None] * 30 + np.array([-15., 15., 15., -15.])
            expected_z = origin_m_xz[1] + rows[:, None] * 30 + np.array([-15., -15., 15., 15.])
            if not np.array_equal(vertices[:, :, 0], expected_x) or not np.array_equal(vertices[:, :, 2], expected_z):
                raise ValueError('display quad footprint differs from bound source grid')
        if not np.isclose(depth.sum() * 900., mesh['display_volume_m3'], rtol=1e-10, atol=1e-6):
            raise ValueError('display top stage volume disagrees with saved display storage')
        snapshots.append({'time_s': state['time_s'], 'path': name, 'sha256': state['sha256'],
            'volume_m3': state['solver_volume_m3'], 'display_max_depth_m': float(depth.max()) if len(depth) else 0.})
    case = {'id': case_id, 'model': case_metadata['schema'], 'requested_time_s': case_metadata['requested_time_s'],
        'committed_time_s': case_metadata['committed_time_s'], 'status': case_metadata['status'],
        'failure': case_metadata['failure'], 'snapshots': snapshots,
        'boundary_description': boundary_description,
        'boundary_faces': boundary_faces or [],
        'sampling': index['sampling'] + '; only saved keyframes, not complete time-step replay; flat-cell water tops',
        'water_summary': {key: case_metadata[key] for key in ('initial_volume_m3', 'supplied_m3',
            'boundary_input_m3', 'boundary_output_m3', 'final_volume_m3') if key in case_metadata},
        'B_validation': 'External saved-case manifest SHA ' + index['source_case_manifest_sha256'] +
            '; full source index SHA ' + expected_sha256 + '; display meshes retain omitted storage and physical archive references'}
    return validate_snapshot_index({'schema': 'regional-saved-B-mesh-cases-v1', 'source_identity': source_identity,
        'fixture_only': False, 'cases': [case]}, source_identity=source_identity)


def export_review(source, network_path, destination, *, network_sha256, snapshot_index_path=None,
                  snapshot_index_sha256=None, allow_fixture=False):
    validate_source(source)
    if Path(network_path).stat().st_size > 16 * 1024 * 1024:
        raise ValueError('network JSON exceeds16MiB before read')
    if file_sha256(network_path) != network_sha256:
        raise ValueError('external static network SHA mismatch')
    network = read_bounded_json(network_path, expected_sha256=network_sha256)
    if network['source_identity'] != source['identity_sha256']:
        raise ValueError('review/network source binding mismatch')
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = source['arrays']
    data = {'schema': 'regional-fullgrid-static-review-v1', 'source_identity': source['identity_sha256'],
        'raw_sha256': source['metadata']['raw_sha256'], 'origin_m_xz': source['metadata']['origin_m_xz'],
        'spacing_m': 30., 'shape': [256, 256], 'area_m2': 58982400.,
        'height_m': arrays['height_m'].ravel().tolist(),
        'potential_lake_id': arrays['diagnostic_lake_id'].ravel().tolist(),
        'contributing_area_m2': arrays['contributing_area_m2'].ravel().tolist(),
        'channel_mask': arrays['channel_mask'].ravel().tolist(),
        'network_sha256': network_sha256, 'network': network,
        'snapshot_contract': {'required_external_B_validator': True,
            'source_binding': 'same raw TD SHA, H0/grid/origin and boundary; no source identity substitution',
            'arrays': 'time_s[K]; depth_m[K,256,256]; B model metadata/ledger/requested+committed time',
            'stage': 'H0+saved_depth only; potential lake labels never create water',
            'consumer': 'saved snapshots only; no prepare/advance; no invented states between snapshots'}}
    mesh_files = {}
    if snapshot_index_path is None:
        index = {'schema':'regional-saved-B-mesh-index-v1', 'source_identity':source['identity_sha256'],
            'snapshots':[], 'status':'awaiting_B_saved_mesh'}
    else:
        index = validate_snapshot_index(read_bounded_json(snapshot_index_path,
            expected_sha256=snapshot_index_sha256, max_bytes=262144), source_identity=source['identity_sha256'])
        if index['fixture_only'] and not allow_fixture:
            raise ValueError('synthetic fixture must never enter formal source review')
        for case in index['cases']:
            for state in case['snapshots']:
                mesh_path = Path(snapshot_index_path).parent / state['path']
                validate_saved_mesh(read_bounded_json(mesh_path, expected_sha256=state['sha256']),
                    source_identity=source['identity_sha256'])
                mesh_files[state['path']] = (mesh_path, state['sha256'])
        if sum(path.stat().st_size for path, digest in mesh_files.values()) > 512 * 1024 * 1024:
            raise ValueError('review mesh total disk budget exceeded')
    cases = index.get('cases', [])
    case_status = [{'id': case['id'], 'status': case['status'], 'failure': case['failure'],
        'requested_time_s': case['requested_time_s'], 'committed_time_s': case['committed_time_s']}
        for case in cases]
    data['saved_dynamic_states_available'] = bool(cases)
    data['case_status'] = case_status
    data['fixture_only'] = index.get('fixture_only', False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.review-staging-', dir=destination.parent))
    try:
        publish_bytes(staging / 'consumer.json', json.dumps(data, allow_nan=False, separators=(',', ':')).encode())
        publish_bytes(staging / 'review.html', (PAGE + PLAN_PLAYBACK).encode('utf-8'))
        publish_bytes(staging / 'review-3d.html', CAMERA_PAGE.encode('utf-8'))
        for name, (path, digest) in mesh_files.items():
            shutil.copyfile(path, staging / name)
            if file_sha256(staging / name) != digest:
                raise ValueError('mesh changed during export')
        publish_bytes(staging / 'saved-mesh-index.json', json.dumps(index, allow_nan=False).encode())
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {'consumer_sha256': file_sha256(destination / 'consumer.json'),
        'html_sha256': file_sha256(destination / 'review.html'), 'cells': 65536,
        'saved_dynamic_states_available': bool(cases), 'case_status': case_status,
        'fixture_only': index.get('fixture_only', False),
        'snapshot_status': 'saved states available; physical acceptance remains external' if cases else
            'awaiting externally validated B frozen artifact'}


CAMERA_PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>单区域河网审查</title>
<style>body{background:#17212c;color:#eee;font:16px sans-serif;margin:24px}canvas{background:#dce5ed;touch-action:none;max-width:100%}pre{white-space:pre-wrap}</style>
<h1>单区域河网审查 · 三维</h1><a href="review.html">切换二维平面</a>
<p>Terrain Diffusion生成山地，非认证测绘DEM；有限计算区域，不是完整自然流域。模型局部惯性忽略动量平流，30m不解析细槽。</p>
<p>拖动旋转、滚轮缩放；竖直比例1×。蓝线为静态规划河段，红线为H0逆坡，均非已实现通水底床。</p>
<details><summary>审查范围与模型说明</summary><p>地表采样三角网不作体积认证，粗地表可能遮挡微水；不可凭蓝色像素估计储水。紫色标签是潜在洼地，不是初始水。动态蓝水只读取已保存水体mesh，不插值造水。边缘为工程排水边界，非天然海口。静态河段为前景审查叠加，不认证水下可见性或动态流向。</p><pre id="info"></pre></details>
<label><input id="channels" type="checkbox" checked>静态河段</label><label><input id="lakes" type="checkbox">潜在湖标签</label><select id="case" disabled></select>
<label><input id="terrainVisible" type="checkbox" checked>地形背景（可遮挡微水；关闭审查完整水面）</label>
<p id="waterLedger"></p>
<p id="samplingNote"></p>
<button id="reset">重置相机</button><button id="play" disabled>播放</button><input id="time" type="range" min="0" max="0" value="0" disabled><span id="clock">无已验收动态快照</span>
<canvas id="scene" width="1100" height="760"></canvas>
<script>let data,index,activeCase=null,water=null,ticket=0,timer=null,terrain=[],bounds,center,rotation;const canvas=document.getElementById('scene'),ctx=canvas.getContext('2d');let yaw=.6,pitch=.65,distance=15000,drag=null;
function caseLabel(c){const name=c.id.replace('wet_no_rain','湿土无雨').replace('uniform_heavy_tailwater','均匀暴雨·抬尾水').replace('uniform_heavy','均匀暴雨').replace('filtered_1mm','1毫米过滤（默认）').replace('full_top','全量微水膜').replace('dry','干初态');return name+' · '+(c.status==='completed'?'已完成':'已拒绝')}
function prepareTerrain(){let minimum=Infinity,maximum=-Infinity,sum=0;for(const h of data.height_m){minimum=Math.min(minimum,h);maximum=Math.max(maximum,h);sum+=h}bounds={minimum,maximum};center=[data.origin_m_xz[0]+127.5*30,sum/65536,data.origin_m_xz[1]+127.5*30];const vertex=(r,c)=>[data.origin_m_xz[0]+c*30,data.height_m[r*256+c],data.origin_m_xz[1]+r*30];for(let r=0;r<255;r+=4)for(let c=0;c<255;c+=4){const rr=Math.min(255,r+4),cc=Math.min(255,c+4),a=vertex(r,c),b=vertex(r,cc),d=vertex(rr,c),e=vertex(rr,cc),v=(a[1]-minimum)/Math.max(1,maximum-minimum),color=`rgb(${Math.round(80+170*v)},${Math.round(120+90*v)},100)`;terrain.push({vertices:[a,b,d],color},{vertices:[b,e,d],color})}}
function point(v){const x=v[0]-center[0],y=v[1]-center[1],z=v[2]-center[2],xx=rotation.cy*x-rotation.sy*z,zz=rotation.sy*x+rotation.cy*z,yy=rotation.cp*y-rotation.sp*zz,depth=distance+rotation.sp*y+rotation.cp*zz;return [550+xx*900/depth,380-yy*900/depth,depth]}
function triangle(vertices,color,faces){const p=vertices.map(point);if(p.some(v=>v[2]<=100))return;faces.push({p,color,depth:p.reduce((s,v)=>s+v[2],0)/3})}
function litColor(face){const [a,b,c]=face.vertices,u=b.map((v,i)=>v-a[i]),v=c.map((n,i)=>n-a[i]);let n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];if(n[1]<0)n=n.map(x=>-x);const length=Math.hypot(...n)||1,light=.4+.6*Math.max(0,(-.45*n[0]+.8*n[1]-.4*n[2])/length);return 'rgb('+face.color.match(/\\d+/g).map(x=>Math.round(Number(x)*light)).join(',')+')'}
function render(){if(!data)return;const started=performance.now();rotation={cy:Math.cos(yaw),sy:Math.sin(yaw),cp:Math.cos(pitch),sp:Math.sin(pitch)};ctx.clearRect(0,0,1100,760);const faces=[],{minimum,maximum}=bounds;
document.getElementById('samplingNote').textContent=activeCase?.sampling||'仅保存状态；未提供完整时间步回放。当前页面无60m尺度切换，60m只报告对照。';
document.getElementById('waterLedger').textContent='来源 '+data.source_identity.slice(0,12)+' · 30m / 65536格 / 58.9824km² · 边缘工程排水 · 模型 '+(activeCase?.model||'静态H0')+(water?.solver_volume_m3!==undefined?' · 物理总储水 '+water.solver_volume_m3.toFixed(3)+'m³ · 显示 '+water.display_volume_m3.toFixed(3)+'m³ · 遗漏 '+water.omitted_volume_m3.toFixed(3)+'m³ ('+(water.solver_volume_m3?100*water.omitted_volume_m3/water.solver_volume_m3:0).toFixed(2)+'%) · 显示阈值 '+water.display_threshold_m+'m':'');
if(window.drawGL){window.drawGL()}else{if(document.getElementById('terrainVisible').checked)terrain.forEach(face=>triangle(face.vertices,face.lit||(face.lit=litColor(face)),faces));if(water)water.triangles.forEach(ids=>triangle(ids.map(i=>water.vertices_xyz_m[i]),'#168fc5',faces));faces.sort((a,b)=>b.depth-a.depth);faces.forEach(f=>{ctx.fillStyle=f.color;ctx.beginPath();f.p.forEach((p,j)=>j?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fill()})}
if(document.getElementById('channels').checked)[false,true].forEach(uphill=>data.network.segments.filter(s=>!!s.H0_uphill_edges===uphill).forEach(s=>{ctx.strokeStyle=uphill?'#e42a20':'#1259df';ctx.lineWidth=uphill?2:1;ctx.beginPath();s.cell_flat.forEach((i,j)=>{const p=point([data.origin_m_xz[0]+i%256*30,data.height_m[i]+1,data.origin_m_xz[1]+Math.floor(i/256)*30]);j?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])});ctx.stroke()}));
if(document.getElementById('lakes').checked){ctx.fillStyle='#885299';const labels=new Set();data.potential_lake_id.forEach((id,i)=>{if(id<=0)return;const p=point([data.origin_m_xz[0]+i%256*30,data.height_m[i]+2,data.origin_m_xz[1]+Math.floor(i/256)*30]);ctx.fillRect(p[0]-1.5,p[1]-1.5,3,3);if(!labels.has(id)){labels.add(id);ctx.fillText('L'+id,p[0]+3,p[1])}})}
if(activeCase?.boundary_faces){ctx.fillStyle='#f28413';activeCase.boundary_faces.forEach(face=>{const i=face.cell_flat,p=point([data.origin_m_xz[0]+i%256*30,data.height_m[i]+2,data.origin_m_xz[1]+Math.floor(i/256)*30]);ctx.fillRect(p[0]-4,p[1]-4,8,8);ctx.fillText('stage '+face.face_id,p[0]+5,p[1])})}
ctx.fillStyle='#222';ctx.fillText('x east / z south metres; H0 '+minimum.toFixed(2)+'–'+maximum.toFixed(2)+'m; vertical1x',20,25);window.cameraState={yaw,pitch,distance};window.cameraReady=true;window.lastRenderMs=performance.now()-started;document.getElementById('info').textContent=JSON.stringify({source_identity:data.source_identity,fixture_only:index?.fixture_only||false,terrain_display_stride:4,terrain_display_not_volume_mesh:true,snapshot_count:activeCase?.snapshots.length||0,case_id:activeCase?.id,water_loaded:!!water,camera:window.cameraState,render_ms:window.lastRenderMs},null,2)}
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId)};canvas.onpointerup=()=>drag=null;canvas.onpointermove=e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.006;pitch=Math.max(-1.2,Math.min(1.2,pitch+(e.clientY-drag[1])*.006));drag=[e.clientX,e.clientY];render()};canvas.onwheel=e=>{e.preventDefault();distance=Math.max(6000,Math.min(50000,distance*Math.exp(e.deltaY*.001)));render()};document.getElementById('reset').onclick=()=>{yaw=.6;pitch=.65;distance=15000;render()};
async function selectSnapshot(){const request=++ticket,k=+document.getElementById('time').value,s=activeCase?.snapshots[k];if(!s)return;const response=await fetch(s.path);if(!response.ok)throw Error('mesh HTTP failure');const length=Number(response.headers.get('content-length'));if(length>16777216)throw Error('mesh exceeds16MiB');const bytes=await response.arrayBuffer();if(bytes.byteLength>16777216)throw Error('mesh exceeds16MiB');const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(v=>v.toString(16).padStart(2,'0')).join('');if(digest!==s.sha256)throw Error('mesh hash mismatch');const m=JSON.parse(new TextDecoder().decode(bytes));if(m.source_identity!==data.source_identity||!Array.isArray(m.vertices_xyz_m)||!Array.isArray(m.triangles)||m.vertices_xyz_m.length>300000||m.triangles.length>400000)throw Error('mesh binding/resource mismatch');if(!m.vertices_xyz_m.every(v=>v.length===3&&v.every(Number.isFinite))||!m.triangles.every(t=>t.length===3&&t.every(i=>Number.isInteger(i)&&i>=0&&i<m.vertices_xyz_m.length)))throw Error('mesh indices invalid');if(request!==ticket)return;water=m;window.loadedSnapshot={case_id:activeCase.id,time_s:s.time_s};document.getElementById('clock').textContent=(index.fixture_only?'合成界面测试 · ':'')+s.time_s/3600+'h / 已提交 '+activeCase.committed_time_s/3600+'h / 请求 '+activeCase.requested_time_s/3600+'h · V='+s.volume_m3+'m³';render()}
function selectCase(){pause();++ticket;water=null;activeCase=index.cases[+document.getElementById('case').value];const slider=document.getElementById('time');slider.value=0;slider.max=activeCase.snapshots.length-1;slider.disabled=false;document.getElementById('play').disabled=false;render();selectSnapshot()}
function pause(){if(timer!==null)clearInterval(timer);timer=null;document.getElementById('play').textContent='播放'}document.getElementById('time').oninput=()=>{pause();selectSnapshot()};document.getElementById('play').onclick=()=>{if(timer!==null){pause();return}const slider=document.getElementById('time');if(+slider.value>=+slider.max)slider.value=0;document.getElementById('play').textContent='暂停';selectSnapshot();timer=setInterval(()=>{slider.value=Math.min(+slider.max,+slider.value+1);selectSnapshot();if(+slider.value>=+slider.max)pause()},500)};
document.getElementById('channels').onchange=render;document.getElementById('lakes').onchange=render;document.getElementById('case').onchange=selectCase;
document.getElementById('terrainVisible').onchange=()=>render();
const playMany=document.getElementById('play').onclick;document.getElementById('play').onclick=()=>{if(activeCase?.snapshots.length===1){pause();selectSnapshot();return}playMany()};
const renderModel=render;render=function(){renderModel();if(!data)return;const ledger=document.getElementById('waterLedger');ledger.textContent=ledger.textContent.replace('边缘工程排水',activeCase?.boundary_description||'边缘工程排水');if(activeCase?.water_summary)ledger.textContent+=' · 全程水账 '+JSON.stringify(activeCase.water_summary);if(activeCase?.failure)ledger.textContent+=' · 拒绝 '+JSON.stringify(activeCase.failure)};
const renderSupport=render;render=function(){renderSupport();if(water?.omitted_wet_cells!==undefined)document.getElementById('waterLedger').textContent+=' · 显示湿格 '+water.display_cell_ids.length+' / 遗漏湿格 '+water.omitted_wet_cells};
function setupGL(){const wrapper=document.createElement('div');wrapper.style.cssText='position:relative;width:1100px;max-width:100%';canvas.before(wrapper);const layer=document.createElement('canvas');layer.width=1100;layer.height=760;layer.style.cssText='position:absolute;inset:0;width:100%;height:100%';wrapper.append(layer,canvas);canvas.style.cssText='position:relative;background:transparent;display:block';const gl=layer.getContext('webgl',{alpha:false,antialias:true});if(!gl){canvas.style.background='#dce5ed';return}window.rendererBackend='WebGL';window.finishGL=()=>gl.finish();
const vertexSource='attribute vec3 position;attribute vec3 color;varying vec3 shade;uniform vec4 rotation;uniform float distance;void main(){float xx=rotation.x*position.x-rotation.y*position.z;float zz=rotation.y*position.x+rotation.x*position.z;float yy=rotation.z*position.y-rotation.w*zz;float depth=distance+rotation.w*position.y+rotation.z*zz;gl_Position=vec4(xx*900.0/550.0,yy*900.0/380.0,1.002002*depth-200.2002,depth);shade=color;}';const fragmentSource='precision mediump float;varying vec3 shade;void main(){gl_FragColor=vec4(shade,1.0);}';
function shader(type,source){const result=gl.createShader(type);gl.shaderSource(result,source);gl.compileShader(result);if(!gl.getShaderParameter(result,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(result));return result}const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vertexSource));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragmentSource));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);const position=gl.getAttribLocation(program,'position'),color=gl.getAttribLocation(program,'color'),rotate=gl.getUniformLocation(program,'rotation'),dist=gl.getUniformLocation(program,'distance');let terrainBuffer=null,waterBuffer=null,waterReference=null;
function buffer(vertices,colors){const values=new Float32Array(vertices.length*6);vertices.forEach((v,i)=>{values.set(v.map((n,k)=>n-center[k]),i*6);values.set(colors[i],i*6+3)});const result=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,result);gl.bufferData(gl.ARRAY_BUFFER,values,gl.STATIC_DRAW);return {buffer:result,count:vertices.length}}
function draw(packet){if(!packet)return;gl.bindBuffer(gl.ARRAY_BUFFER,packet.buffer);gl.enableVertexAttribArray(position);gl.enableVertexAttribArray(color);gl.vertexAttribPointer(position,3,gl.FLOAT,false,24,0);gl.vertexAttribPointer(color,3,gl.FLOAT,false,24,12);gl.drawArrays(gl.TRIANGLES,0,packet.count)}
window.drawGL=()=>{if(!terrainBuffer){const vertices=[],colors=[];terrain.forEach(face=>{const rgb=litColor(face).match(/\\d+/g).map(v=>Number(v)/255);face.vertices.forEach(v=>{vertices.push(v);colors.push(rgb)})});terrainBuffer=buffer(vertices,colors)}if(waterReference!==water){if(waterBuffer)gl.deleteBuffer(waterBuffer.buffer);waterBuffer=null;waterReference=water;if(water){const vertices=[],colors=[];water.triangles.forEach(ids=>ids.forEach(i=>{vertices.push(water.vertices_xyz_m[i]);colors.push([.086,.561,.773])}));waterBuffer=buffer(vertices,colors)}}gl.viewport(0,0,1100,760);gl.clearColor(.863,.898,.929,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.uniform4f(rotate,rotation.cy,rotation.sy,rotation.cp,rotation.sp);gl.uniform1f(dist,distance);if(document.getElementById('terrainVisible').checked)draw(terrainBuffer);draw(waterBuffer);window.GLwaterTriangles=(waterBuffer?.count||0)/3};
window.blueWaterPixels=()=>{render();gl.finish();const pixels=new Uint8Array(1100*760*4);gl.readPixels(0,0,1100,760,gl.RGBA,gl.UNSIGNED_BYTE,pixels);let count=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]<60&&pixels[i+1]>100&&pixels[i+2]>150)count++;return count};
layer.addEventListener('webglcontextlost',e=>{e.preventDefault();window.drawGL=null;canvas.style.background='#dce5ed';window.rendererBackend='Canvas fallback';render()});}
setupGL();
Promise.all([fetch('consumer.json').then(r=>r.json()),fetch('saved-mesh-index.json').then(r=>r.json())]).then(([d,i])=>{data=d;index=i;prepareTerrain();if(i.source_identity!==d.source_identity)throw Error('snapshot index source mismatch');if(i.cases?.length){const selector=document.getElementById('case');i.cases.forEach((c,k)=>selector.add(new Option(caseLabel(c),k)));selector.disabled=false;selectCase()}render()});</script></html>'''


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>完整区域静态河网</title>
<style>body{background:#17212c;color:#eee;font:16px sans-serif;margin:24px}canvas{background:#eee;max-width:100%}pre{white-space:pre-wrap}label{margin:10px}</style>
<h1>单区域河网审查 · 二维</h1><a href="review-3d.html">进入三维与保存状态播放</a>
<p>Terrain Diffusion生成山地，非认证测绘DEM；有限计算区域，不是完整自然流域。30m不解析细槽，局部惯性不是完整浅水认证。</p>
<p>65536格；H0未切床。蓝色静态规划线非已实现通水河道，红色为原H0逆坡段；满盆fill/spill规划并非动态流向。潜在湖为几何范围，不是初始水。边缘free engineering drain，非天然海口。</p>
<p>30m格中心origin+index×30，footprint±15；子格细槽未解决。本页不准备、不求天气或水动力。B冻结快照未接入前，不显示虚构水位。</p>
<label><input id="channel" type="checkbox" checked>静态河段</label><label><input id="lake" type="checkbox">潜在洼地</label>
<p id="planLedger"></p><p id="planSampling"></p><p>点击二维格心查看H0/显示水位/显示体积；过滤遗漏格不能推断为干格。橙色方框为指定stage边界。无60m尺度切换。</p><pre id="cellDetail"></pre><canvas id="map" width="940" height="900"></canvas><pre id="detail"></pre>
<script>let data;function render(){if(!data)return;const c=document.getElementById('map'),ctx=c.getContext('2d');ctx.clearRect(0,0,940,900);const h=data.height_m,min=h.reduce((a,b)=>Math.min(a,b),Infinity),max=h.reduce((a,b)=>Math.max(a,b),-Infinity),scale=3,offset=60;
for(let i=0;i<65536;i++){const v=(h[i]-min)/(max-min),lake=document.getElementById('lake').checked&&data.potential_lake_id[i]>0;ctx.fillStyle=lake?'#a58aaf':`rgb(${Math.round(80+170*v)},${Math.round(120+105*v)},${Math.round(65+130*v)})`;ctx.fillRect(offset+i%256*scale,50+Math.floor(i/256)*scale,scale,scale)}
if(document.getElementById('channel').checked)[false,true].forEach(uphill=>data.network.segments.filter(s=>!!s.H0_uphill_edges===uphill).forEach(s=>{ctx.strokeStyle=uphill?'#e42a20':'#1259df';ctx.lineWidth=uphill?2.2:1.2;ctx.beginPath();s.cell_flat.forEach((i,j)=>{const x=offset+(i%256+.5)*scale,y=50+(Math.floor(i/256)+.5)*scale;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}));
ctx.strokeStyle='#222';ctx.strokeRect(offset,50,768,768);ctx.fillStyle='#222';ctx.font='14px sans-serif';ctx.fillText('绝对东km '+((data.origin_m_xz[0]-15)/1000).toFixed(3)+' → '+((data.origin_m_xz[0]+255*30+15)/1000).toFixed(3),60,845);ctx.fillText('绝对南km '+((data.origin_m_xz[1]-15)/1000).toFixed(3)+' → '+((data.origin_m_xz[1]+255*30+15)/1000).toFixed(3),60,866);
for(let j=0;j<200;j++){const v=j/199;ctx.fillStyle=`rgb(${Math.round(80+170*v)},${Math.round(120+105*v)},${Math.round(65+130*v)})`;ctx.fillRect(850,650-j*2,20,2)}ctx.fillStyle='#222';ctx.fillText(max.toFixed(2)+'m',845,240);ctx.fillText(min.toFixed(2)+'m',845,675);
document.getElementById('detail').textContent=JSON.stringify({source_identity:data.source_identity,raw_sha256:data.raw_sha256,cells:65536,area_m2:data.area_m2,channel_cells:data.network.channel_cells,segments:data.network.segments.length,uphill_edges:data.network.H0_uphill_channel_edges,max_uphill_m:data.network.max_H0_channel_uphill_m,saved_dynamic_states_available:data.saved_dynamic_states_available,case_status:data.case_status,fixture_only:data.fixture_only,snapshot_contract:data.snapshot_contract},null,2);window.reviewReady=true}
document.getElementById('channel').onchange=render;document.getElementById('lake').onchange=render;fetch('consumer.json').then(r=>r.json()).then(d=>{data=d;render()});</script></html>'''


PLAN_PLAYBACK = '''<script>
const controls=document.createElement('div');controls.innerHTML='<select id="savedCase" disabled></select><button id="savedPlay" disabled>播放</button><input id="savedTime" type="range" min="0" max="0" value="0" disabled><span id="savedClock">等待保存状态</span>';document.getElementById('map').before(controls);
let savedIndex,savedCase,savedWater=null,savedTicket=0,savedTimer=null;
function savedLabel(c){return c.id.replace('wet_no_rain','湿土无雨').replace('uniform_heavy_tailwater','均匀暴雨·抬尾水').replace('uniform_heavy','均匀暴雨').replace('filtered_1mm','1毫米过滤（默认）').replace('full_top','全量微水膜').replace('dry','干初态')+' · '+(c.status==='completed'?'已完成':'已拒绝')}
const staticRender=render;
render=function(){staticRender();if(!data||!savedWater)return;document.getElementById('planLedger').textContent='模型 '+savedCase.model+' · 边缘工程排水 · 30m / 65536格'+(savedWater.solver_volume_m3!==undefined?' · 物理总储水 '+savedWater.solver_volume_m3.toFixed(3)+'m³ · 显示 '+savedWater.display_volume_m3.toFixed(3)+'m³ · 遗漏 '+savedWater.omitted_volume_m3.toFixed(3)+'m³ ('+(savedWater.solver_volume_m3?100*savedWater.omitted_volume_m3/savedWater.solver_volume_m3:0).toFixed(2)+'%) · 阈值 '+savedWater.display_threshold_m+'m':'');const ctx=document.getElementById('map').getContext('2d');ctx.fillStyle='#168fc5';for(const ids of savedWater.triangles){ctx.beginPath();ids.forEach((id,j)=>{const v=savedWater.vertices_xyz_m[id],x=60+((v[0]-data.origin_m_xz[0])/30+.5)*3,y=50+((v[2]-data.origin_m_xz[1])/30+.5)*3;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.closePath();ctx.fill()}};
function stopSaved(){clearInterval(savedTimer);savedTimer=null;document.getElementById('savedPlay').textContent='播放'}
async function loadSaved(){const ticket=++savedTicket,s=savedCase.snapshots[+document.getElementById('savedTime').value];const response=await fetch(s.path);if(!response.ok)throw Error('saved mesh HTTP failure');if(Number(response.headers.get('content-length'))>16777216)throw Error('saved mesh size');const bytes=await response.arrayBuffer();if(bytes.byteLength>16777216)throw Error('saved mesh size');const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(v=>v.toString(16).padStart(2,'0')).join('');if(hash!==s.sha256)throw Error('saved mesh hash');const mesh=JSON.parse(new TextDecoder().decode(bytes));if(mesh.source_identity!==savedIndex.source_identity||!Array.isArray(mesh.vertices_xyz_m)||!Array.isArray(mesh.triangles)||mesh.vertices_xyz_m.length>300000||mesh.triangles.length>400000)throw Error('mesh schema/binding');if(!mesh.vertices_xyz_m.every(v=>v.length===3&&v.every(Number.isFinite))||!mesh.triangles.every(t=>t.length===3&&t.every(i=>Number.isInteger(i)&&i>=0&&i<mesh.vertices_xyz_m.length)))throw Error('invalid mesh');if(ticket!==savedTicket)return;savedWater=mesh;window.loadedSnapshot={case_id:savedCase.id,time_s:s.time_s};document.getElementById('savedClock').textContent=(savedIndex.fixture_only?'合成界面测试 · ':'')+s.time_s/3600+'h / 已提交 '+savedCase.committed_time_s/3600+'h / 请求 '+savedCase.requested_time_s/3600+'h · V='+s.volume_m3+'m³';render()}
function changeSavedCase(){stopSaved();++savedTicket;savedWater=null;savedCase=savedIndex.cases[+document.getElementById('savedCase').value];const slider=document.getElementById('savedTime');slider.max=savedCase.snapshots.length-1;slider.value=0;slider.disabled=false;document.getElementById('savedPlay').disabled=false;render();loadSaved()}
document.getElementById('savedCase').onchange=changeSavedCase;document.getElementById('savedTime').oninput=()=>{stopSaved();loadSaved()};document.getElementById('savedPlay').onclick=()=>{if(savedTimer!==null){stopSaved();return}const slider=document.getElementById('savedTime');if(+slider.value>=+slider.max)slider.value=0;loadSaved();document.getElementById('savedPlay').textContent='暂停';savedTimer=setInterval(()=>{slider.value=Math.min(+slider.max,+slider.value+1);loadSaved();if(+slider.value>=+slider.max)stopSaved()},500)};
const playSavedMany=document.getElementById('savedPlay').onclick;document.getElementById('savedPlay').onclick=()=>{if(savedCase?.snapshots.length===1){stopSaved();loadSaved();return}playSavedMany()};
const renderLedger=render;render=function(){renderLedger();if(!savedCase)return;const ledger=document.getElementById('planLedger');ledger.textContent=ledger.textContent.replace('边缘工程排水',savedCase.boundary_description||'边缘工程排水');if(savedCase.water_summary)ledger.textContent+=' · 全程水账 '+JSON.stringify(savedCase.water_summary);if(savedCase.failure)ledger.textContent+=' · 拒绝 '+JSON.stringify(savedCase.failure)};
const renderAnnotations=render;render=function(){renderAnnotations();if(!savedCase||!data)return;document.getElementById('planSampling').textContent=savedCase.sampling||'仅保存关键帧，不是完整时间步回放';const ctx=document.getElementById('map').getContext('2d');ctx.strokeStyle='#f28413';ctx.lineWidth=3;(savedCase.boundary_faces||[]).forEach(face=>{const i=face.cell_flat;ctx.strokeRect(60+i%256*3,50+Math.floor(i/256)*3,3,3)})};
const renderPlanSupport=render;render=function(){renderPlanSupport();if(savedWater?.omitted_wet_cells!==undefined)document.getElementById('planLedger').textContent+=' · 显示湿格 '+savedWater.display_cell_ids.length+' / 遗漏湿格 '+savedWater.omitted_wet_cells};
document.getElementById('map').onclick=e=>{if(!data)return;const rect=e.currentTarget.getBoundingClientRect(),column=Math.floor(((e.clientX-rect.left)*940/rect.width-60)/3),row=Math.floor(((e.clientY-rect.top)*900/rect.height-50)/3);if(row<0||row>=256||column<0||column>=256)return;const id=row*256+column,H0=data.height_m[id],mesh=savedWater,position=mesh?.display_cell_ids?.indexOf(id)??-1,eta=position>=0?mesh.vertices_xyz_m[position*4][1]:null;const record={cell_flat:id,row,column,x_m:data.origin_m_xz[0]+column*30,z_m:data.origin_m_xz[1]+row*30,H0_m:H0,potential_lake_id:data.potential_lake_id[id],saved_time_s:window.loadedSnapshot?.time_s??null,display_eta_m:eta,display_depth_m:eta===null?null:eta-H0,display_cell_volume_m3:eta===null?null:(eta-H0)*900,status:eta!==null?'saved_display_cell':mesh?.display_threshold_m===0?'dry_in_complete_saved_support':'not_shown_unknown_depth_not_certified_dry'};window.clickedCell=record;document.getElementById('cellDetail').textContent=JSON.stringify(record,null,2)};
fetch('saved-mesh-index.json').then(r=>r.json()).then(i=>{savedIndex=i;if(!i.cases?.length)return;const selector=document.getElementById('savedCase');i.cases.forEach((c,k)=>selector.add(new Option(savedLabel(c),k)));selector.disabled=false;changeSavedCase()});
</script>'''
