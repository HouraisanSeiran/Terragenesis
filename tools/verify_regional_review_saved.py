"""One read-only review entry for externally pinned B case/display exports."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import publish_bytes, file_sha256
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.regional_surface_review import read_bounded_json, adapt_B_index, export_review
from terrain_pipeline.regional_hydraulics_archive import read_arrays, GEOMETRY


def workspace_path(name):
    if not isinstance(name, str):
        raise ValueError('workspace relative path required')
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('path escapes workspace')
    return path


def browser_acceptance(directory):
    from playwright.sync_api import sync_playwright
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    evidence = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True, args=['--disable-gpu'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            page.on('pageerror', lambda error: errors.append(str(error)))
            for filename, case_control, slider_control, play_control, ready in (
                    ('review-3d.html', '#case', '#time', '#play', 'window.cameraReady'),
                    ('review.html', '#savedCase', '#savedTime', '#savedPlay', 'window.reviewReady')):
                page.goto(f'http://127.0.0.1:{server.server_port}/{filename}', wait_until='networkidle')
                page.wait_for_function(ready + '===true && window.loadedSnapshot?.time_s===0')
                index = json.loads((directory / 'saved-mesh-index.json').read_text())
                for number, case in enumerate(index['cases']):
                    before = page.evaluate('window.cameraState||null')
                    page.select_option(case_control, str(number))
                    page.wait_for_function('(id)=>window.loadedSnapshot?.case_id===id && window.loadedSnapshot.time_s===0', arg=case['id'])
                    if before is not None and page.evaluate('window.cameraState') != before:
                        raise ValueError('case switch reset camera')
                    state_metrics = []
                    for state_number, state in enumerate(case['snapshots']):
                        page.locator(slider_control).evaluate('(s,k)=>{s.value=k;s.dispatchEvent(new Event("input"))}', state_number)
                        page.wait_for_function('(s)=>window.loadedSnapshot?.case_id===s.id && window.loadedSnapshot.time_s===s.time',
                            arg={'id': case['id'], 'time': state['time_s']})
                        if filename == 'review-3d.html':
                            metrics = page.evaluate('()=>{const frames=[];for(let i=0;i<10;i++){const start=performance.now();render();if(window.finishGL)window.finishGL();frames.push(performance.now()-start)}return {frames_ms:frames,vertices:water.vertices_xyz_m.length,triangles:water.triangles.length,omitted_volume_m3:water.omitted_volume_m3??null,solver_volume_m3:water.solver_volume_m3??null,renderer:window.rendererBackend||"Canvas"}}')
                            p95 = sorted(metrics['frames_ms'])[8]
                            if p95 > 50:
                                raise ValueError('real saved mesh render exceeds predeclared p95 50ms')
                            if metrics['triangles'] and page.evaluate('!!window.blueWaterPixels'):
                                retained_camera = page.evaluate('window.cameraState')
                                page.uncheck('#terrainVisible')
                                exposed = page.evaluate('({pixels:window.blueWaterPixels(),triangles:window.GLwaterTriangles,loaded:window.loadedSnapshot})')
                                if (exposed['triangles'] != metrics['triangles'] or exposed['loaded']['time_s'] != state['time_s'] or
                                        page.evaluate('window.cameraState') != retained_camera or exposed['pixels'] <= 0):
                                    raise ValueError('hidden terrain changed saved water or camera')
                                metrics['hidden_terrain_same_state'] = exposed
                                page.screenshot(path=str(directory / (case['id'] + '-no-terrain.png')), full_page=True)
                                page.check('#terrainVisible')
                            state_metrics.append({'time_s': state['time_s'], 'p95_ms': p95, **metrics})
                    page.locator(slider_control).evaluate('(s)=>{s.value=0;s.dispatchEvent(new Event("input"))}')
                    page.click(play_control)
                    if len(case['snapshots']) > 1:
                        page.click(play_control)
                        if page.locator(play_control).inner_text() != '播放':
                            raise ValueError('pause did not stop saved playback')
                        page.click(play_control)
                    page.wait_for_function('(t)=>window.loadedSnapshot?.time_s===t', arg=case['committed_time_s'], timeout=180000)
                    if page.locator(play_control).inner_text() != '播放':
                        raise ValueError('saved playback did not stop at committed endpoint')
                    if before is not None and page.evaluate('window.cameraState') != before:
                        raise ValueError('saved time selection or playback reset camera')
                    if filename == 'review.html':
                        page.locator('#map').click(position={'x': 61.5, 'y': 51.5})
                        click = page.evaluate('window.clickedCell')
                        if click['cell_flat'] != 0 or click['saved_time_s'] != case['committed_time_s']:
                            raise ValueError('local cell click/time alignment failed')
                        evidence.append({'page': filename, 'case_id': case['id'], 'local_cell_click': click})
                    evidence.append({'page': filename, 'case_id': case['id'], 'saved_states_checked': len(case['snapshots']),
                        'play_pause_final_stop': True, 'physical_certification': False, 'state_render_metrics': state_metrics,
                        'performance_budget_p95_ms': 50})
                page.screenshot(path=str(directory / (filename + '.png')), full_page=True)
            browser.close()
        if errors:
            raise ValueError('saved review browser errors: ' + repr(errors))
        return {'pageerrors': errors, 'cases': evidence, 'scope': 'saved display playback only; not hydraulic acceptance'}
    finally:
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-index', type=Path, required=True)
    parser.add_argument('--run-index-sha256', required=True)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    run = read_bounded_json(args.run_index, expected_sha256=args.run_index_sha256, max_bytes=262144)
    if set(run) != {'schema', 'source_path', 'source_sha256', 'network_path', 'network_sha256', 'cases'} or run['schema'] != 'regional-review-trusted-run-v1':
        raise ValueError('known external trusted run index required')
    if not isinstance(run['cases'], list) or not 1 <= len(run['cases']) <= 8:
        raise ValueError('bounded cases required')
    source = load_source(workspace_path(run['source_path']), expected_sha256=run['source_sha256'])
    output = ROOT / 'verification/regional-review-saved' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    inputs = output / 'saved-input'
    cases = []
    prepared = []
    for case in run['cases']:
        case_keys = {'id', 'mesh_index_path', 'mesh_index_sha256', 'case_manifest_path', 'case_manifest_sha256'}
        if (not case_keys.issubset(case) or set(case) - case_keys - {'predeclared_sha256', 'representation_id'} or
                not isinstance(case['id'], str) or not case['id'] or
                any(not (letter.isalnum() or letter in '_-') for letter in case['id'])):
            raise ValueError('exact pinned case fields required')
        manifest_path = workspace_path(case['case_manifest_path'])
        manifest = read_bounded_json(manifest_path, expected_sha256=case['case_manifest_sha256'])
        metadata = read_bounded_json(manifest_path.parent / 'states.json',
            expected_sha256=manifest['artifacts']['states.json'])['metadata']
        read_bounded_json(manifest_path.parent / 'geometry.json',
            expected_sha256=manifest['artifacts']['geometry.json'])
        geometry_sha = manifest['artifacts']['geometry.npz']
        if file_sha256(manifest_path.parent / 'geometry.npz') != geometry_sha:
            raise ValueError('saved boundary geometry hash mismatch')
        geometry = read_arrays(manifest_path.parent / 'geometry.npz', GEOMETRY, expected_sha256=geometry_sha)
        kinds = geometry['boundary_kind']
        prescribed = int((kinds == 2).sum())
        drains = int((kinds == 1).sum())
        boundary_description = f'Engineering finite window: {drains} free-drain faces, {prescribed} prescribed-stage faces'
        boundary_faces = [{'face_id': int(face), 'cell_flat': int(geometry['boundary_cell'][face]),
            'kind': int(kinds[face])} for face in range(len(kinds)) if kinds[face] == 2]
        if prescribed:
            declaration = read_bounded_json(manifest_path.parent.parent / 'predeclared.json',
                expected_sha256=case['predeclared_sha256']) if 'predeclared_sha256' in case else None
            if declaration:
                boundary_description += '; tailwater event ' + json.dumps(declaration['tailwater'])
            else:
                boundary_description += '; event schedule not pinned in this review; not natural outlets'
        mesh_path = workspace_path(case['mesh_index_path'])
        adapted = adapt_B_index(mesh_path, expected_sha256=case['mesh_index_sha256'],
            source_identity=source['identity_sha256'], case_metadata=metadata, case_id=case['id'],
            trusted_height=source['arrays']['height_m'], expected_case_manifest_sha256=case['case_manifest_sha256'],
            origin_m_xz=source['metadata']['origin_m_xz'],
            boundary_description=boundary_description, representation_id=case.get('representation_id'))
        adapted['cases'][0]['boundary_faces'] = boundary_faces
        prepared.append((mesh_path, adapted['cases'][0]))
    inputs.mkdir(parents=True, exist_ok=False)
    for number, (mesh_path, case) in enumerate(prepared):
        for state in case['snapshots']:
            original = mesh_path.parent / state['path']
            name = 'case-%02d-' % number + state['path']
            shutil.copyfile(original, inputs / name)
            if file_sha256(inputs / name) != state['sha256']:
                raise ValueError('saved display changed during copy')
            state['path'] = name
        cases.append(case)
    index_path = inputs / 'index.json'
    publish_bytes(index_path, json.dumps({'schema': 'regional-saved-B-mesh-cases-v1',
        'source_identity': source['identity_sha256'], 'fixture_only': False, 'cases': cases}, allow_nan=False).encode())
    result = export_review(source, workspace_path(run['network_path']), output / 'review',
        network_sha256=run['network_sha256'], snapshot_index_path=index_path,
        snapshot_index_sha256=file_sha256(index_path))
    if args.browser:
        publish_bytes(output / 'browser.json', json.dumps(browser_acceptance(output / 'review'),
            allow_nan=False, indent=2).encode())
    publish_bytes(output / 'manifest.json', json.dumps({'review': result,
        'external_run_index_sha256': args.run_index_sha256, 'external_run_index_path': str(args.run_index.resolve()),
        'source_hashes': {name: file_sha256(ROOT / name) for name in (
            'terrain_pipeline/regional_surface_review.py', 'tools/verify_regional_review_saved.py')},
        'files_sha256': {str(path.relative_to(output)): file_sha256(path) for path in output.rglob('*') if path.is_file()}},
        allow_nan=False, indent=2).encode())
    print(output)


if __name__ == '__main__':
    main()
