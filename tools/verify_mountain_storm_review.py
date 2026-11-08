"""Export and browser-audit saved weather/water only; never generate or advance."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import checked_archive, file_sha256, publish_bytes
from terrain_pipeline.climate_forcing import storm_load_forcing as load_forcing
from tools.verify_mountain_source_adapter import write_json


SOURCE = ROOT / "verification/mountain-storm-forcing/run-20261001T071520828638Z"


def export_review(destination):
    if destination.exists():
        raise FileExistsError(destination)
    files = [path for path in SOURCE.iterdir() if path.is_file()]
    before = {path.name: file_sha256(path) for path in files}
    report = json.loads((SOURCE / "report.json").read_text(encoding="utf-8"))
    data = {"schema": "mountain-weather-spatial-readonly-review-v1", "cases": {},
        "source_identity": report["source_identity"], "selection_identity": report["selection_identity"],
        "geometry_identity": report["geometry_identity"], "source_directory": str(SOURCE),
        "dt_s": 900., "spacing_m": 30., "coordinates": "x east, z south; m; grid [z,x]",
        "rain_semantics": "saved HRU interval means, not freshly evaluated cell weather",
        "lake_rain_limitation": "300m mixed HRU mean applied to lake footprint; max error 5.16334110 mm/h",
        "alignment": "state k at k*dt; preceding rain/Q interval k-1; k=0 has no preceding flux"}
    geometry = None
    for name in ("eastward", "westward", "no_rain"):
        digest = report["no_rain_baseline"]["archive_sha256"] if name == "no_rain" else report["cases"][name]["coupling_sha256"]
        arrays = checked_archive(SOURCE / f"pressure_mountain-{name}-coupling.npz",
                                 expected_sha256=digest, max_bytes=768*1024*1024)
        manifest = json.loads(arrays.pop("manifest").tobytes().decode("utf-8"))
        from terrain_pipeline.lake import validate_coupling as validate_coupling

        validate_coupling(dict(manifest, arrays=arrays))
        if geometry is None:
            mask = arrays["hydrology_mask"]
            cells = np.flatnonzero(mask)
            rows, columns = np.unravel_index(cells, mask.shape)
            metadata = manifest["metadata"]["source_metadata"]
            origin = metadata["origin_m_xz"]
            node = arrays["anchor_node"].ravel()[cells]
            receiver = arrays["receiver"].ravel()[cells]
            lake_nodes = [index for index, kind in enumerate(manifest["metadata"]["node_kind"]) if kind == "lake"]
            geometry = {"grid_shape": list(mask.shape), "origin_m_xz": origin,
                "cell_flat": cells.tolist(), "east_m": (origin[0]+columns*30).tolist(),
                "south_m": (origin[1]+rows*30).tolist(), "HRU": arrays["cell_owner"].ravel()[cells].tolist(),
                "node": node.tolist(), "receiver_flat": receiver.tolist(),
                "lake_footprint": np.isin(node, lake_nodes).tolist(), "lake_nodes": lake_nodes,
                "node_kind": manifest["metadata"]["node_kind"],
                "node_downstream": arrays["node_downstream"].tolist(),
                "HRU_area_m2": arrays["area_m2"].tolist(),
                "HRU_absolute_300m_bins": json.loads((SOURCE / "pressure_mountain-eastward-weather-consumer.json").read_text(encoding="utf-8"))["HRU_bins_east_south"]}
        else:
            if not np.array_equal(arrays["cell_owner"].ravel()[cells], geometry["HRU"]):
                raise ValueError("paired HRU geometry mismatch")
        if name == "no_rain":
            rain = np.zeros((288, len(geometry["HRU_area_m2"])))
            parameters = None
        else:
            weather = load_forcing(SOURCE / f"{name}-weather.npz", expected_sha256=report["cases"][name]["weather_sha256"],
                cell_owner=arrays["cell_owner"], source_identity=report["source_identity"], selection_identity=report["selection_identity"])
            rain = weather["arrays"]["rain_mm_h"]
            parameters = weather["metadata"]["parameters"]
        data["cases"][name] = {"parameters": parameters, "coupling_sha256": digest,
            "weather_sha256": None if name == "no_rain" else report["cases"][name]["weather_sha256"],
            "rain_mm_h": rain.tolist(), "node_q_m3_s": (arrays["outflow_volume_m3"]/900).tolist(),
            "node_storage_m3": arrays["storage_m3"].tolist(),
            "outlet_q_m3_s": (arrays["total_boundary_volume_m3"]/900).tolist(),
            "lake_storage_m3": arrays["storage_m3"][:, geometry["lake_nodes"]].sum(axis=1).tolist(),
            "lake_stage_m": {str(node): arrays["lake_stage_m"][:, node].tolist() for node in geometry["lake_nodes"]},
            "soil_fast_slow_storage_m3": ((arrays["runoff_soil_mm"]+arrays["runoff_fast_mm"]+arrays["runoff_slow_mm"])*arrays["runoff_area_m2"]/1000).sum(axis=1).tolist()}
    data["geometry"] = geometry
    data["state_time_hours"] = (np.arange(289)*.25).tolist()
    data["interval_start_hours"] = (np.arange(288)*.25).tolist()
    write_json(destination / "weather-water-consumer.json", data)
    publish_bytes(destination / "review.html", PAGE.encode("utf-8"))
    after = {path.name: file_sha256(path) for path in files}
    if before != after:
        raise RuntimeError("frozen source artifacts changed during static export")
    write_json(destination / "report.json", {"status": "static_spatial_weather_water_export", "source_files_sha256": before,
        "source_unchanged": True, "consumer_sha256": file_sha256(destination / "weather-water-consumer.json"),
        "exporter_sha256": file_sha256(Path(__file__)), "html_sha256": file_sha256(destination / "review.html"),
        "no_weather_generation": True, "no_water_advancement": True, "gpu_inference_run": False})


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>移动天气空间回放</title>
<style>body{background:#17212c;color:#eee;font:16px sans-serif;margin:24px}canvas{background:#f5f7fa;border:1px solid #888;max-width:100%}.maps{display:flex;gap:16px;flex-wrap:wrap}pre{white-space:pre-wrap;word-break:break-all}label{margin:10px}</style>
<h1>pressure1378：保存雨强、河库Q与湖量同步回放</h1>
<p>参数化移动天气非预报；有限窗口外边界非天然海口。灰色/蓝色线为离散干格receiver传播，并非全部可见河道；无河道水位、回水或3D水面。青色框为30m湖footprint。</p>
<p>雨图仅绘制保存的15 HRU时段平均值：绝对300m分区，实际贡献格裁切。湖格使用混合HRU雨，最大聚合误差5.16334110mm/h，不是局地高精度湖雨；未重新生成天气。</p>
<select id="case"><option>eastward</option><option>westward</option><option>no_rain</option></select>
<input id="time" type="range" min="0" max="288" value="48" step="1"><span id="clock"></span>
<div class="maps"><div>空间时段平均雨强 mm/h（0–24）<br><canvas id="rain" width="620" height="480"></canvas></div><div>离散河库时段平均Q m³/s（共同色标）<br><canvas id="river" width="620" height="480"></canvas></div></div>
<p>同轴方向对照：东向蓝、西向红、同初始湿土无雨灰；竖线为所选状态时刻。k=0无前一时段雨/Q。</p>
<canvas id="hydro" width="1260" height="250"></canvas><canvas id="lake" width="1260" height="250"></canvas><pre id="detail"></pre>
<script>let data;const names=['eastward','westward','no_rain'],colors=['#1677cc','#cc3b24','#666'];
async function init(){data=await(await fetch('weather-water-consumer.json')).json();window.reviewReady=true;render()}
function render(){if(!data)return;const name=document.getElementById('case').value,k=+document.getElementById('time').value,interval=k? k-1:null,c=data.cases[name],g=data.geometry;
document.getElementById('clock').textContent=data.state_time_hours[k]+' h / 状态 '+k+' / 前一时段 '+(interval===null?'无':interval);
const east=g.east_m,south=g.south_m,minX=Math.min(...east)-15,maxX=Math.max(...east)+15,minZ=Math.min(...south)-15,maxZ=Math.max(...south)+15;
const qmax=Math.max(...names.map(n=>Math.max(...data.cases[n].outlet_q_m3_s)),1e-9);
function map(id,mode){const canvas=document.getElementById(id),ctx=canvas.getContext('2d');ctx.clearRect(0,0,620,480);const scale=Math.min(540/(maxX-minX),390/(maxZ-minZ)),point=(x,z)=>[55+(x-minX)*scale,30+(z-minZ)*scale],index=new Map(g.cell_flat.map((cell,i)=>[cell,i]));
g.cell_flat.forEach((cell,i)=>{const [x,y]=point(east[i]-15,south[i]-15);let value=interval===null?0:mode==='rain'?c.rain_mm_h[interval][g.HRU[i]]:c.node_q_m3_s[interval][g.node[i]],ratio=Math.min(1,value/(mode==='rain'?24:qmax));ctx.fillStyle=interval===null?'#ddd':mode==='rain'?`rgb(${Math.round(245-200*ratio)},${Math.round(250-120*ratio)},250)`:`rgb(${Math.round(240-220*ratio)},${Math.round(240-100*ratio)},${Math.round(240-20*ratio)})`;ctx.fillRect(x,y,30*scale,30*scale);
if(mode==='river'&&!g.lake_footprint[i]&&index.has(g.receiver_flat[i])){const j=index.get(g.receiver_flat[i]),a=point(east[i],south[i]),b=point(east[j],south[j]);ctx.strokeStyle='#506d8a';ctx.lineWidth=.6+2*ratio;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke()}
if(g.lake_footprint[i]){ctx.strokeStyle='#00bfc7';ctx.lineWidth=3;ctx.strokeRect(x,y,30*scale,30*scale)}});
ctx.fillStyle='#222';ctx.font='12px sans-serif';ctx.fillText('绝对东坐标 km: '+(minX/1000).toFixed(3)+' → '+(maxX/1000).toFixed(3),55,450);ctx.fillText('绝对南坐标 km: '+(minZ/1000).toFixed(3)+' → '+(maxZ/1000).toFixed(3),55,468);ctx.fillText(interval===null?'初始状态；无时段量':mode==='rain'?'雨强色标 0–24 mm/h':'Q色标 0–'+qmax.toFixed(3)+' m³/s',55,18);
if(mode==='rain'){ctx.strokeStyle='#d88600';ctx.lineWidth=.7;g.HRU_absolute_300m_bins.forEach(bin=>{let a=point(bin[0]*300,bin[1]*300);ctx.strokeRect(a[0],a[1],300*scale,300*scale)})}}
map('rain','rain');map('river','river');
function plot(id,key,label,states){const ctx=document.getElementById(id).getContext('2d');ctx.clearRect(0,0,1260,250);const maximum=Math.max(...names.map(n=>Math.max(...data.cases[n][key])),1e-9);names.forEach((n,index)=>{ctx.strokeStyle=colors[index];ctx.lineWidth=2;ctx.beginPath();data.cases[n][key].forEach((v,j)=>{const hour=(states?j:j+1)*.25,x=50+hour/72*1150,y=220-v/maximum*185;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.fillStyle=colors[index];ctx.fillText(n,800+index*130,18)});ctx.fillStyle='#222';ctx.fillText(label+'；0–72物理小时；上限 '+maximum.toFixed(3),50,18);ctx.strokeStyle='#111';ctx.beginPath();const x=50+data.state_time_hours[k]/72*1150;ctx.moveTo(x,25);ctx.lineTo(x,225);ctx.stroke()}
plot('hydro','outlet_q_m3_s','开放外边界Q m³/s',false);plot('lake','lake_storage_m3','四池总储水 m³',true);
const frame={case:name,state_index:k,physical_hour:data.state_time_hours[k],preceding_interval_index:interval,rain_HRU_mm_h:interval===null?null:c.rain_mm_h[interval],boundary_Q_m3_s:interval===null?null:c.outlet_q_m3_s[interval],lake_storage_m3:c.lake_storage_m3[k],lake_stage_m:Object.fromEntries(Object.entries(c.lake_stage_m).map(([node,values])=>[node,values[k]])),soil_fast_slow_storage_m3:c.soil_fast_slow_storage_m3[k],source_identity:data.source_identity,geometry_identity:data.geometry_identity,selection_identity:data.selection_identity,lake_rain_error:data.lake_rain_limitation};document.getElementById('detail').textContent=JSON.stringify(frame,null,2);window.currentReviewFrame=frame}
document.getElementById('case').onchange=render;document.getElementById('time').oninput=render;init();</script></html>'''


def browser_audit(directory):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1",0),partial(SimpleHTTPRequestHandler,directory=str(directory.resolve())))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    result = {"pageerrors":[],"cases":{},"html_sha256":file_sha256(directory/"review.html")}
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel="msedge",headless=True,args=["--disable-gpu"])
            page=browser.new_page(viewport={"width":1440,"height":1200})
            page.on("pageerror",lambda error:result["pageerrors"].append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/review.html",wait_until="networkidle")
            page.wait_for_function("window.reviewReady===true")
            for name in ("eastward","westward","no_rain"):
                page.select_option("#case",name)
                frames=[]
                for state in (0,24,48,56,96,288):
                    page.locator("#time").evaluate("(slider,k)=>{slider.value=k;slider.dispatchEvent(new Event('input'))}",state)
                    frame=page.evaluate("window.currentReviewFrame")
                    if frame["case"]!=name or frame["state_index"]!=state or frame["physical_hour"]!=state*.25:
                        raise ValueError("spatial browser frame mismatch")
                    if state==0 and frame["rain_HRU_mm_h"] is not None:
                        raise ValueError("initial state must not show interval rain")
                    frames.append({"state_index":state,"physical_hour":frame["physical_hour"],"Q":frame["boundary_Q_m3_s"]})
                result["cases"][name]=frames
            if result["pageerrors"]:
                raise ValueError("spatial browser errors")
            page.select_option("#case","eastward")
            page.locator("#time").evaluate("slider=>{slider.value=48;slider.dispatchEvent(new Event('input'))}")
            page.screenshot(path=str(directory/"browser-review.png"),full_page=True)
            browser.close()
        write_json(directory/"browser-review.json",result)
    finally:
        server.shutdown()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--browser-review",type=Path)
    args=parser.parse_args()
    if args.browser_review:
        browser_audit(args.browser_review)
        return
    destination=args.output or ROOT/"verification/mountain-storm-review"/("run-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    export_review(destination)
    browser_audit(destination)
    print(str(destination))


if __name__=="__main__":
    main()
