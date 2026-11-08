"""Read-only compact diagnostic charts from externally pinned saved summaries."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.regional_surface_review import read_bounded_json
from terrain_pipeline.common_infra import publish_bytes, file_sha256


def diagnostics(summary, forcing, *, case_metadata=None):
    if summary['source_identity'] != forcing['source_identity']:
        raise ValueError('summary/forcing source identity mismatch')
    frames = summary['frames']
    if not isinstance(frames, list) or not 1 <= len(frames) <= 300:
        raise ValueError('bounded saved summary frames required')
    previous = -1.
    for frame in frames:
        time = frame['time_s']
        if type(time) not in (int, float) or not np.isfinite(time) or not previous < time <= 259200:
            raise ValueError('finite increasing saved frame times required')
        previous = time
        volumes = [frame['total_volume_m3'], frame['partitions']['potential_lake']['volume_m3'],
            frame['partitions']['non_lake']['volume_m3']]
        if any(type(v) not in (int, float) or not np.isfinite(v) or v < 0 for v in volumes):
            raise ValueError('finite nonnegative partition storage required')
        if not np.isclose(volumes[0], volumes[1] + volumes[2], atol=1e-6, rtol=1e-12):
            raise ValueError('lake/nonlake partition storage does not sum to total')
        for key in ('preceding_saved_interval_external_outflow_mean_m3_s',
                'preceding_saved_interval_external_inflow_mean_m3_s'):
            value = frame[key]
            if value is None and time == 0:
                continue
            if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
                raise ValueError('finite saved-interval mean external rates required')
    if frames[0]['time_s'] != 0:
        raise ValueError('saved initial state required')
    dt, steps = forcing['dt_s'], forcing['steps']
    if type(dt) not in (int, float) or not np.isfinite(dt) or dt <= 0 or type(steps) is not int or not 1 <= steps <= 288:
        raise ValueError('finite positive forcing time grid required')
    ledger = forcing['ledger']
    for key in ('rain_m3', 'runoff_m3', 'et_m3'):
        values = ledger[key]
        if len(values) != steps or not np.isfinite(values).all() or min(values) < 0:
            raise ValueError('finite positive forcing ledger columns required')
    committed = frames[-1]['time_s']
    if committed > steps * dt:
        raise ValueError('summary time exceeds forcing physical domain')
    rates = [{'start_s': i * dt, 'end_s': min((i + 1) * dt, committed),
        'rain_mean_mm_h': ledger['rain_m3'][i] / 58982400. * 1000 * 3600 / dt,
        'runoff_mean_m3_s': ledger['runoff_m3'][i] / dt,
        'et_mean_m3_s': ledger['et_m3'][i] / dt}
        for i in range(steps) if i * dt < committed]
    outgoing = [{'start_s': frames[i - 1]['time_s'], 'end_s': frame['time_s'],
        'mean_m3_s': frame['preceding_saved_interval_external_outflow_mean_m3_s']}
        for i, frame in enumerate(frames) if i > 0]
    incoming = [{'start_s': frames[i - 1]['time_s'], 'end_s': frame['time_s'],
        'mean_m3_s': frame['preceding_saved_interval_external_inflow_mean_m3_s']}
        for i, frame in enumerate(frames) if i > 0]
    status = None
    if case_metadata is not None:
        if case_metadata['source_identity'] != summary['source_identity'] or case_metadata['committed_time_s'] != committed:
            raise ValueError('saved summary committed time/source differs from pinned case')
        status = {key: case_metadata[key] for key in ('status', 'failure', 'requested_time_s', 'committed_time_s')}
        if (status['status'] not in ('completed', 'refused') or not np.isfinite(status['requested_time_s']) or
                not committed <= status['requested_time_s'] <= 259200 or
                (status['status'] == 'completed' and (committed != status['requested_time_s'] or status['failure'] is not None)) or
                (status['status'] == 'refused' and (committed >= status['requested_time_s'] or not status['failure']))):
            raise ValueError('case completion/failure/time status inconsistent')
    return {'source_identity': summary['source_identity'], 'committed_time_s': committed, 'outgoing_intervals': outgoing,
        'incoming_intervals': incoming, 'case_status': status,
        'frames': frames, 'forcing_rates': rates, 'rain_soil_surface': summary['rain_soil_surface'],
        'non_DAG': summary['non_DAG'], 'scope': 'saved partition storage and preceding-saved-interval mean outlet rates; not instantaneous flood peaks'}


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>单区域水量诊断</title>
<style>body{font:16px sans-serif;background:#17212c;color:#eee;margin:24px}canvas{background:#f4f6f8;max-width:100%}pre{white-space:pre-wrap}</style>
<h1>单区域水量诊断</h1><p>只读保存数据。降雨和产流是forcing时段平均；出界率是相邻保存状态区间平均，不是瞬时洪峰。潜在湖标签分区不是统一湖水位；停止降雨不保证所有区域已退水。</p>
<select id="case"></select><p id="status"></p><div id="charts"></div><pre id="account"></pre>
<script>let data;function chart(title,series){const h=document.createElement('h2');h.textContent=title;const canvas=document.createElement('canvas');canvas.width=1100;canvas.height=280;document.getElementById('charts').append(h,canvas);const ctx=canvas.getContext('2d'),max=Math.max(1,...series.flatMap(s=>s.points.map(p=>p[1]))),end=Math.max(1,data.cases[+document.getElementById('case').value].committed_time_s);ctx.fillStyle='#222';ctx.fillText('0 → '+(end/3600).toFixed(3)+'h，最大刻度 '+max.toPrecision(6),50,20);ctx.strokeStyle='#ced5dd';for(let tick=0;tick<=4;tick++){const x=50+tick*250;ctx.beginPath();ctx.moveTo(x,40);ctx.lineTo(x,240);ctx.stroke();ctx.fillStyle='#222';ctx.fillText((end/3600*tick/4).toFixed(2)+'h',x-12,254)}for(let tick=0;tick<=2;tick++){const y=240-tick*97.5;ctx.beginPath();ctx.moveTo(50,y);ctx.lineTo(1050,y);ctx.stroke();ctx.fillStyle='#222';ctx.fillText((max*tick/2).toPrecision(5),2,y)}series.forEach((s,k)=>{ctx.strokeStyle=s.color;ctx.beginPath();s.points.forEach((p,j)=>{const x=50+p[0]/end*1000,y=240-p[1]/max*195;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.fillStyle=s.color;ctx.fillText(s.label,50+k*330,265)})}
function render(){const d=data.cases[+document.getElementById('case').value];document.getElementById('charts').replaceChildren();document.getElementById('status').textContent=d.id+' · '+d.case_status.status+' · 已提交 '+(d.committed_time_s/3600)+'h / 请求 '+(d.case_status.requested_time_s/3600)+'h'+(d.case_status.failure?' · 拒绝 '+JSON.stringify(d.case_status.failure):'');chart('降雨（mm/h）',[{label:'区域平均雨强',color:'#167eaa',points:d.forcing_rates.flatMap(r=>[[r.start_s,r.rain_mean_mm_h],[r.end_s,r.rain_mean_mm_h]])}]);chart('产流与出界率（m³/s）',[{label:'土库→surface产流',color:'#bf5f10',points:d.forcing_rates.flatMap(r=>[[r.start_s,r.runoff_mean_m3_s],[r.end_s,r.runoff_mean_m3_s]])},{label:'保存区间平均出界',color:'#166bad',points:d.outgoing_intervals.flatMap(r=>[[r.start_s,r.mean_m3_s],[r.end_s,r.mean_m3_s]])},{label:'保存区间平均入界（尾水）',color:'#8e389f',points:d.incoming_intervals.flatMap(r=>[[r.start_s,r.mean_m3_s],[r.end_s,r.mean_m3_s]])}]);chart('地表储水（m³）',[{label:'全域',color:'#182c43',points:d.frames.map(f=>[f.time_s,f.total_volume_m3])},{label:'潜在lake标签区',color:'#885299',points:d.frames.map(f=>[f.time_s,f.partitions.potential_lake.volume_m3])},{label:'nonlake区',color:'#1b916c',points:d.frames.map(f=>[f.time_s,f.partitions.non_lake.volume_m3])}]);document.getElementById('account').textContent=JSON.stringify({source_identity:d.source_identity,case_id:d.id,case_status:d.case_status,forcing_manifest_sha256:d.forcing_manifest_sha256,scope:d.scope,water_account:d.rain_soil_surface,non_DAG:d.non_DAG},null,2);window.diagnosticsReady=true}
fetch('diagnostics.json').then(r=>r.json()).then(d=>{data=d;d.cases.forEach((c,i)=>document.getElementById('case').add(new Option(c.id,i)));document.getElementById('case').onchange=render;render()});</script></html>'''


def browser_acceptance(directory, cases):
    from playwright.sync_api import sync_playwright
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    evidence = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True, args=['--disable-gpu'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1300})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/diagnostics.html', wait_until='networkidle')
            page.wait_for_function('window.diagnosticsReady===true')
            for number, case in enumerate(cases):
                page.select_option('#case', str(number))
                account = json.loads(page.locator('#account').inner_text())
                if account['case_id'] != case['id'] or account['case_status'] != case['case_status'] or page.locator('canvas').count() != 3:
                    raise ValueError('diagnostic case/time/chart data mismatch')
                page.screenshot(path=str(directory / ('case-%02d.png' % number)), full_page=True)
                evidence.append({'case_id': case['id'], 'committed_time_s': case['committed_time_s'],
                    'saved_frames': len(case['frames']), 'rain_intervals': len(case['forcing_rates'])})
            browser.close()
        if errors:
            raise ValueError('diagnostics browser errors: ' + repr(errors))
        return {'pageerrors': errors, 'cases': evidence, 'readonly': True}
    finally:
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-index', type=Path, required=True)
    parser.add_argument('--run-index-sha256', required=True)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    run = read_bounded_json(args.run_index, expected_sha256=args.run_index_sha256, max_bytes=262144)
    if set(run) != {'schema', 'cases'} or run['schema'] != 'regional-diagnostics-trusted-run-v1' or not 1 <= len(run['cases']) <= 8:
        raise ValueError('known pinned diagnostics run index required')
    cases = []
    seen = set()
    for case in run['cases']:
        if set(case) != {'id', 'summary_path', 'summary_sha256', 'forcing_manifest_path', 'forcing_manifest_sha256', 'case_manifest_path', 'case_manifest_sha256'}:
            raise ValueError('exact pinned diagnostics case required')
        if not isinstance(case['id'], str) or not case['id'] or case['id'] in seen:
            raise ValueError('unique diagnostics case ID required')
        seen.add(case['id'])
        paths = [(ROOT / case[key]).resolve() for key in ('summary_path', 'forcing_manifest_path', 'case_manifest_path')]
        if any(not path.is_relative_to(ROOT) for path in paths):
            raise ValueError('diagnostics paths escape workspace')
        summary = read_bounded_json(paths[0], expected_sha256=case['summary_sha256'])
        forcing = read_bounded_json(paths[1], expected_sha256=case['forcing_manifest_sha256'])
        case_manifest = read_bounded_json(paths[2], expected_sha256=case['case_manifest_sha256'])
        binding = read_bounded_json(paths[2].parent / 'binding.json',
            expected_sha256=case_manifest['artifacts']['binding.json'])
        metadata = read_bounded_json(paths[2].parent / 'states.json',
            expected_sha256=case_manifest['artifacts']['states.json'])['metadata']
        if (binding['forcing_manifest_sha256'] != case['forcing_manifest_sha256'] or
                metadata['forcing_identity'] != case['forcing_manifest_sha256']):
            raise ValueError('case/summary cannot use another forcing manifest with the same source')
        if summary['case_manifest_sha256'] != case['case_manifest_sha256']:
            raise ValueError('summary saved case manifest mismatch')
        cases.append({'id': case['id'], 'forcing_manifest_sha256': case['forcing_manifest_sha256'],
            **diagnostics(summary, forcing, case_metadata=metadata)})
    output = ROOT / 'verification/regional-review-diagnostics' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    publish_bytes(output / 'diagnostics.json', json.dumps({'cases': cases}, allow_nan=False).encode())
    publish_bytes(output / 'diagnostics.html', PAGE.encode('utf-8'))
    if args.browser:
        publish_bytes(output / 'browser.json', json.dumps(browser_acceptance(output, cases), allow_nan=False, indent=2).encode())
    publish_bytes(output / 'manifest.json', json.dumps({'external_run_index_sha256': args.run_index_sha256,
        'exporter_sha256': file_sha256(Path(__file__)), 'files_sha256': {p.name: file_sha256(p) for p in output.iterdir() if p.is_file()}}, indent=2).encode())
    print(output)


if __name__ == '__main__':
    main()
