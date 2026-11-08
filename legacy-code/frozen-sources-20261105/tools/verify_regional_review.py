"""Read-only regional static export and actual Edge browser acceptance."""

import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.regional_surface_review import export_review
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.verify_mountain_source_adapter import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', type=Path, required=True)
    parser.add_argument('--network-directory', type=Path, required=True)
    parser.add_argument('--fixture-playback', action='store_true')
    parser.add_argument('--full-quad-fixture', action='store_true')
    args = parser.parse_args()
    if args.full_quad_fixture and not args.fixture_playback:
        raise ValueError('full quad fixture requires isolated fixture playback')
    source_meta = json.loads((args.source_directory / 'manifest.json').read_text(encoding='utf-8'))
    source = load_source(args.source_directory / 'source.npz', expected_sha256=source_meta['source_sha256'])
    network_meta = json.loads((args.network_directory / 'manifest.json').read_text(encoding='utf-8'))
    category = 'regional-review-fixture' if args.fixture_playback else 'regional-review'
    destination = ROOT / 'verification' / category / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    snapshot_args = {}
    if args.fixture_playback:
        fixture = destination.parent / (destination.name + '-input')
        fixture.mkdir(parents=True, exist_ok=False)
        cases = []
        x, z = source['metadata']['origin_m_xz']
        h = float(source['arrays']['height_m'][128, 128])
        for name, depths in [('synthetic_initial_peak_recession', (0., 2., .2)),
                ('synthetic_tailwater_UI_only', (0., .5, 1.)), ('synthetic_refused_t0', (0.,))]:
            states = []
            for step, depth in enumerate(depths):
                path = fixture / (name + '-' + str(step) + '.json')
                vertices = [[x + 3800, h + depth, z + 3800], [x + 3900, h + depth, z + 3800],
                    [x + 3900, h + depth, z + 3900], [x + 3800, h + depth, z + 3900]] if depth else []
                triangles = [[0, 1, 2], [0, 2, 3]] if depth else []
                if args.full_quad_fixture and depth:
                    vertices = []
                    triangles = []
                    for cell in range(65536):
                        row, column = divmod(cell, 256)
                        cx, cz = int(x + column * 30), int(z + row * 30)
                        stage = round(float(source['arrays']['height_m'][row, column]) + depth, 3)
                        offset = len(vertices)
                        vertices.extend([[cx - 15, stage, cz - 15], [cx + 15, stage, cz - 15],
                            [cx + 15, stage, cz + 15], [cx - 15, stage, cz + 15]])
                        triangles.extend([[offset, offset + 1, offset + 2], [offset, offset + 2, offset + 3]])
                publish_bytes(path, json.dumps({'source_identity': source['identity_sha256'], 'vertices_xyz_m': vertices,
                    'triangles': triangles}, allow_nan=False, separators=(',', ':')).encode())
                states.append({'time_s': step * 900., 'path': path.name, 'sha256': file_sha256(path),
                    'volume_m3': depth * (58982400 if args.full_quad_fixture else 10000), 'max_depth_m': depth})
            refused = len(depths) == 1
            cases.append({'id': name, 'model': 'synthetic UI fixture only', 'requested_time_s': 1800.,
                'committed_time_s': 0. if refused else 1800., 'status': 'refused' if refused else 'completed',
                'failure': {'reason': 'synthetic_t0_refusal', 'time_s': 0.} if refused else None,
                'B_validation': 'No physical acceptance: isolated synthetic playback fixture', 'snapshots': states})
        index_path = fixture / 'index.json'
        write_json(index_path, {'schema': 'regional-saved-B-mesh-cases-v1', 'source_identity': source['identity_sha256'],
            'fixture_only': True, 'cases': cases})
        snapshot_args = {'snapshot_index_path': index_path, 'snapshot_index_sha256': file_sha256(index_path), 'allow_fixture': True}
    result = export_review(source, args.network_directory / 'network.json', destination,
        network_sha256=network_meta['network_sha256'], **snapshot_args)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(destination)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True, args=['--disable-gpu'])
            page = browser.new_page(viewport={'width':1440, 'height':1100})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/review.html', wait_until='networkidle')
            page.wait_for_function('window.reviewReady===true')
            detail = json.loads(page.locator('#detail').inner_text())
            if detail['cells'] != 65536 or detail['channel_cells'] != 1583 or detail['uphill_edges'] != 520:
                raise ValueError('browser full-grid diagnostic mismatch')
            page.check('#lake')
            page.uncheck('#channel')
            page.check('#channel')
            red_pixels = page.evaluate("""()=>{const p=document.getElementById('map').getContext('2d').getImageData(0,0,940,900).data;let count=0;for(let i=0;i<p.length;i+=4)if(p[i]>190&&p[i+1]<90&&p[i+2]<90)count++;return count}""")
            if red_pixels < 100:
                raise ValueError('uphill red segments not visibly rendered')
            page.screenshot(path=str(destination / 'browser-2d.png'), full_page=True)
            page.goto(f'http://127.0.0.1:{server.server_port}/review-3d.html', wait_until='networkidle')
            page.wait_for_function('window.cameraReady===true')
            before = page.evaluate('window.cameraState')
            page.mouse.move(550, 380)
            page.mouse.down()
            page.mouse.move(650, 430, steps=5)
            page.mouse.up()
            page.mouse.wheel(0, -200)
            page.wait_for_timeout(200)
            after = page.evaluate('window.cameraState')
            render_costs = page.evaluate('()=>{const times=[];for(let j=0;j<20;j++){yaw+=.01;render();times.push(window.lastRenderMs)}return times}')
            if after['yaw'] == before['yaw'] or after['distance'] == before['distance']:
                raise ValueError('3D rotate/zoom did not change camera')
            playback = {}
            if args.fixture_playback:
                page.wait_for_function('window.loadedSnapshot?.time_s===0')
                retained = page.evaluate('window.cameraState')
                page.select_option('#case', '1')
                page.wait_for_function("window.loadedSnapshot?.case_id==='synthetic_tailwater_UI_only'")
                if page.evaluate('window.cameraState') != retained:
                    raise ValueError('scenario switch reset camera')
                page.click('#play')
                page.wait_for_function('window.loadedSnapshot?.time_s===1800')
                if args.full_quad_fixture:
                    page.wait_for_function("window.loadedSnapshot?.case_id==='synthetic_tailwater_UI_only' && window.loadedSnapshot.time_s===1800 && water?.triangles.length===131072 && water.vertices_xyz_m.length===262144 && window.GLwaterTriangles===131072")
                full_water_costs = page.evaluate('()=>{const times=[];for(let j=0;j<10;j++){if(window.loadedSnapshot.time_s!==1800)throw Error("timing state changed");const start=performance.now();yaw+=.01;render();if(window.finishGL)window.finishGL();times.push(performance.now()-start)}return times}')
                counted_state = page.evaluate('({loaded:window.loadedSnapshot,vertices:water.vertices_xyz_m.length,triangles:water.triangles.length,GLwaterTriangles:window.GLwaterTriangles,blue_pixels:window.blueWaterPixels?window.blueWaterPixels():null})')
                if args.full_quad_fixture and (counted_state['triangles'] != 131072 or counted_state['GLwaterTriangles'] != 131072 or counted_state['blue_pixels'] < 10000):
                    raise ValueError('full water was not rendered at the measured state')
                page.screenshot(path=str(destination / 'browser-full-water-3d.png'), full_page=True)
                if args.full_quad_fixture:
                    saved_camera = page.evaluate('window.cameraState')
                    page.uncheck('#terrainVisible')
                    unobscured = page.evaluate('({loaded:window.loadedSnapshot,triangles:water.triangles.length,blue_pixels:window.blueWaterPixels()})')
                    if unobscured['blue_pixels'] <= counted_state['blue_pixels'] or page.evaluate('window.cameraState') != saved_camera:
                        raise ValueError('terrain hide did not expose water without changing camera')
                    page.screenshot(path=str(destination / 'browser-full-water-no-terrain.png'), full_page=True)
                    page.check('#terrainVisible')
                else:
                    unobscured = None
                frame_p95 = sorted(full_water_costs)[int(.95 * (len(full_water_costs) - 1))]
                if args.full_quad_fixture and frame_p95 > 50:
                    raise ValueError('full-quad synchronized rendering p95 exceeds declared 50ms budget')
                if page.locator('#play').inner_text() != '播放':
                    raise ValueError('playback did not stop at final state')
                page.click('#play')
                page.click('#play')
                if page.locator('#play').inner_text() != '播放':
                    raise ValueError('pause control failed')
                page.select_option('#case', '0')
                page.select_option('#case', '1')
                page.wait_for_function("window.loadedSnapshot?.case_id==='synthetic_tailwater_UI_only' && window.loadedSnapshot.time_s===0")
                page.wait_for_timeout(500)
                if page.evaluate('window.loadedSnapshot.case_id') != 'synthetic_tailwater_UI_only':
                    raise ValueError('stale fetch replaced selected case')
                playback = {'case_switch_camera_preserved': True, 'play_pause_end_passed': True,
                    'case_fetch_race_guard_passed': True, 'scope': 'synthetic_UI_not_hydraulic_evidence',
                    'full_65536_quad_fixture': args.full_quad_fixture, 'loaded_water_10_frame_ms': full_water_costs,
                    'timing_includes_GL_finish': True, 'renderer': page.evaluate('window.rendererBackend||"Canvas"')}
                playback['performance_budget_p95_ms'] = 50
                playback['observed_frame_p95_ms'] = frame_p95
                playback['measured_and_screenshot_state'] = counted_state
                playback['hidden_terrain_same_water_state'] = unobscured
                page.select_option('#case', '2')
                page.wait_for_function("window.loadedSnapshot?.case_id==='synthetic_refused_t0'")
                page.click('#play')
                page.wait_for_timeout(600)
                if page.locator('#play').inner_text() != '播放' or page.evaluate('window.loadedSnapshot.time_s') != 0:
                    raise ValueError('single t0 refusal playback failed')
                playback['single_state_refusal_passed'] = True
                page.screenshot(path=str(destination / 'browser-fixture-3d.png'), full_page=True)
                page.goto(f'http://127.0.0.1:{server.server_port}/review.html', wait_until='networkidle')
                page.wait_for_function('window.loadedSnapshot?.time_s===0')
                page.select_option('#savedCase', '1')
                page.click('#savedPlay')
                page.wait_for_function('window.loadedSnapshot?.time_s===1800')
                if page.locator('#savedPlay').inner_text() != '播放':
                    raise ValueError('2D playback final stop failed')
                playback['2D_shared_case_time_passed'] = True
            if errors:
                raise ValueError('browser errors')
            page.screenshot(path=str(destination / 'browser-review.png'), full_page=True)
            browser.close()
        write_json(destination / 'browser-review.json', {'pageerrors':errors, 'full_cells':65536, 'layer_toggles_passed':True,
            '3D_rotate_zoom_passed':True, 'camera_before':before, 'camera_after':after, 'synthetic_water_in_formal_page':False,
            'fixture_only':args.fixture_playback, 'playback':playback,
            'static_3D_20_frame_ms':render_costs, 'red_segment_pixels':red_pixels, 'dynamic_large_mesh_performance_certified':False})
    finally:
        server.shutdown()
    write_json(destination / 'manifest.json', {**result, 'source_identity':source['identity_sha256'],
        'delivery_source_sha256':{name:file_sha256(ROOT / name) for name in ('terrain_pipeline/regional_surface_review.py', 'tools/verify_regional_review.py')},
        'files_sha256':{item.name:file_sha256(item) for item in destination.iterdir() if item.is_file()}})
    print(str(destination))


if __name__ == '__main__':
    main()
