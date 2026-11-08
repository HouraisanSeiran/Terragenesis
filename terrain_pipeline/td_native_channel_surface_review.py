"""Export an offline, read-only review of a pinned saved channel bed mesh."""

import base64
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_native_channel_surface import load_channel_surface


def _encoded(values):
    return base64.b64encode(values.tobytes()).decode("ascii")


def export_surface_review(report_path, *, expected_report_sha256, output_path):
    if file_sha256(report_path) != expected_report_sha256:
        raise ValueError("surface report external SHA mismatch")
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if report.get("schema") != "td-native-channel-surface-prototype-v1":
        raise ValueError("surface report schema mismatch")
    surface_pin = report["surface"]
    surface = load_channel_surface(surface_pin["path"], expected_sha256=surface_pin["expected_sha256"],
                                   expected_identity=surface_pin["expected_identity"])
    if file_sha256(report_path) != expected_report_sha256:
        raise ValueError("surface report changed while reading")
    metadata = surface["metadata"]
    if metadata != report["metadata"] or surface["identity_sha256"] != surface_pin["expected_identity"]:
        raise ValueError("surface report metadata/identity mismatch")
    if (metadata["geometry_identity"] != report["geometry"]["expected_identity"] or
            metadata["candidate_tile_identities"] != sorted(tile["expected_identity"] for tile in report["tiles"])):
        raise ValueError("surface source pins mismatch")
    if any(report.get(flag) is not False for flag in
           ("water_generated", "hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("surface report scope flags invalid")
    geometry_report_path = Path(report["geometry"]["path"]).with_name("report.json")
    geometry_report_sha256 = file_sha256(geometry_report_path)
    geometry_report = json.loads(geometry_report_path.read_text(encoding="utf-8"))
    if geometry_report["geometry"] != report["geometry"]:
        raise ValueError("geometry report source mismatch")
    source_inputs = geometry_report["inputs"]
    for name, identity_name in (("hierarchy", "hierarchy_identity"), ("hour_page", "hour_page_identity")):
        if source_inputs[name]["expected_identity"] != metadata[identity_name]:
            raise ValueError("native source identity mismatch")
    if file_sha256(geometry_report_path) != geometry_report_sha256:
        raise ValueError("geometry report changed while reading")
    source_pins = [report["source_tile_report"], report["geometry"], *report["tiles"], report["obj"]]
    source_pins.extend(source_inputs.values())
    for pin in source_pins:
        if file_sha256(pin["path"]) != pin["expected_sha256"]:
            raise ValueError("surface source file SHA mismatch")
    arrays = surface["arrays"]
    vertices = arrays["vertices_xyz_m"]
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
    center[1] = float((vertices[:, 1].min() + vertices[:, 1].max() + arrays["candidate_cut_m"].max()) / 2)
    packed = np.column_stack((vertices - center, arrays["candidate_cut_m"])).astype("<f4")
    indices = np.asarray(arrays["triangles"], dtype="<u4")
    payload = {
        "vertices": _encoded(packed), "triangles": _encoded(indices),
        "count": int(len(vertices)), "triangle_count": int(len(indices)),
        "center_xyz_m": center.tolist(), "window": metadata["window"],
        "extent_m": [float(np.ptp(vertices[:, 0])), float(np.ptp(vertices[:, 1]) + arrays["candidate_cut_m"].max()),
                     float(np.ptp(vertices[:, 2]))],
        "cut_max_m": float(arrays["candidate_cut_m"].max()),
        "height_range_m": [float(vertices[:, 1].min() - center[1]),
                           float((vertices[:, 1] + arrays["candidate_cut_m"]).max() - center[1])],
        "pins": {"report": {"path": str(Path(report_path).resolve()), "expected_sha256": expected_report_sha256},
                 "source_tile_report": report["source_tile_report"], "geometry": report["geometry"],
                 "tiles": report["tiles"], "surface": surface_pin, "obj": report["obj"],
                 "geometry_report": {"path": str(geometry_report_path), "expected_sha256": geometry_report_sha256},
                 "hierarchy": source_inputs["hierarchy"], "hour_page": source_inputs["hour_page"],
                 "hierarchy_identity": metadata["hierarchy_identity"],
                 "hour_page_identity": metadata["hour_page_identity"],
                 "forcing_identity": metadata["forcing_identity"],
                 "source_code_sha256": report["code_sha256"]},
    }
    embedded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    page = _PAGE.replace("__DATA__", embedded)
    if file_sha256(report_path) != expected_report_sha256:
        raise ValueError("surface report changed while exporting")
    if file_sha256(geometry_report_path) != geometry_report_sha256:
        raise ValueError("geometry report changed while exporting")
    for pin in source_pins:
        if file_sha256(pin["path"]) != pin["expected_sha256"]:
            raise ValueError("surface source changed while exporting")
    if file_sha256(surface_pin["path"]) != surface_pin["expected_sha256"]:
        raise ValueError("surface mesh changed while exporting")
    publish_bytes(output_path, page.encode("utf-8"))
    return payload["pins"]


_PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TD native channel bed review</title></head>
<style>
body{margin:0;background:#10171c;color:#e3e9e9;font:14px system-ui,sans-serif}header{padding:12px 18px;background:#1b292e;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0 18px 0 0}button{background:#29444b;border:1px solid #678087;border-radius:5px;color:white;padding:7px 12px;cursor:pointer}button.active{background:#ad6435}
main{display:grid;grid-template-columns:minmax(0,1fr) 320px;height:calc(100vh - 64px)}canvas{width:100%;height:100%;display:block}aside{padding:18px;overflow:auto;background:#182228;line-height:1.45}
aside h2{font-size:14px;color:#e9b27f}pre{font:11px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}p{margin:8px 0;color:#b9c9c9}
@media(max-width:750px){main{display:block;height:auto}canvas{height:65vh}aside{max-height:none}}
</style>
<body><header><h1>Saved channel bed - diagnostic review</h1><button id="native">Original sampled bed</button><button id="candidate" class="active">Derived cut bed</button><button id="cut">Cut coloring: off</button><button id="reset">Reset view</button></header>
<main><canvas id="view" aria-label="Rotatable saved bed mesh"></canvas><aside><h2>Scope</h2><p id="scope"></p><p>Drag to rotate · wheel to zoom · reset restores view. Bed only; no water surface or hydraulic certification.</p><h2>Source pins</h2><pre id="pins"></pre></aside></main>
<script>
"use strict";
const data=__DATA__;
document.getElementById("scope").textContent=`${data.count} saved vertices; ${data.triangle_count} saved triangles; ${data.window.join(", ")} lattice window; original TD 30 m to derived 1 m sampling display only; no new source terrain detail.`;
document.getElementById("pins").textContent=JSON.stringify(data.pins,null,2);
const canvas=document.getElementById("view"), gl=canvas.getContext("webgl2",{antialias:true});
if(!gl){document.getElementById("scope").textContent+=" WebGL2 unavailable; open in a WebGL2-capable browser.";throw new Error("WebGL2 required");}
function binary(base64){const raw=atob(base64), bytes=new Uint8Array(raw.length);for(let index=0;index<raw.length;index++)bytes[index]=raw.charCodeAt(index);return bytes;}
function shader(type,source){const result=gl.createShader(type);gl.shaderSource(result,source);gl.compileShader(result);if(!gl.getShaderParameter(result,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(result));return result;}
const vertex=shader(gl.VERTEX_SHADER,`#version 300 es
in vec4 bedSample; uniform float yaw,pitch,zoom,aspect,nativeMode,heightScale; uniform vec3 extent;
out float cutAmount; out float elevation;
void main(){vec3 point=vec3(bedSample.x,bedSample.y+nativeMode*bedSample.w,bedSample.z);point.y*=heightScale;
float cy=cos(yaw),sy=sin(yaw),cp=cos(pitch),sp=sin(pitch);
vec3 rotated=vec3(cy*point.x+sy*point.z,point.y,-sy*point.x+cy*point.z);
rotated=vec3(rotated.x,cp*rotated.y-sp*rotated.z,sp*rotated.y+cp*rotated.z);
float span=max(extent.x,extent.z)*zoom;
gl_Position=vec4(rotated.x/span/max(aspect,1.0),rotated.y/span*min(aspect,1.0),-rotated.z/(span*3.0),1.0);
cutAmount=bedSample.w;elevation=bedSample.y+nativeMode*bedSample.w;
}`);
const fragment=shader(gl.FRAGMENT_SHADER,`#version 300 es
precision highp float; in float cutAmount,elevation; uniform float cutMode,cutMax,low,high; out vec4 color;
void main(){float height=clamp((elevation-low)/max(high-low,0.001),0.0,1.0);
vec3 earth=mix(vec3(0.17,0.28,0.24),vec3(0.75,0.69,0.51),height);
vec3 incision=mix(vec3(0.25,0.31,0.33),vec3(0.95,0.34,0.12),clamp(cutAmount/max(cutMax,0.001),0.0,1.0));
color=vec4(mix(earth,incision,cutMode),1.0);}`);
const program=gl.createProgram();gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);
if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);
const samples=binary(data.vertices),indices=binary(data.triangles),array=gl.createVertexArray();gl.bindVertexArray(array);
const vertexBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vertexBuffer);gl.bufferData(gl.ARRAY_BUFFER,samples,gl.STATIC_DRAW);
const vertexAttributeLocation=gl.getAttribLocation(program,"bedSample");gl.enableVertexAttribArray(vertexAttributeLocation);gl.vertexAttribPointer(vertexAttributeLocation,4,gl.FLOAT,false,16,0);
const indexBuffer=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indexBuffer);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);
const uniform=(name)=>gl.getUniformLocation(program,name);
gl.uniform3f(uniform("extent"),...data.extent_m);gl.uniform1f(uniform("cutMax"),data.cut_max_m);
gl.uniform1f(uniform("low"),data.height_range_m[0]);gl.uniform1f(uniform("high"),data.height_range_m[1]);
let yaw=-0.7,pitch=-0.65,zoom=1.25,nativeMode=0,cutMode=0,drag=false,lastX=0,lastY=0;
function draw(){const width=canvas.clientWidth,height=canvas.clientHeight,dpr=devicePixelRatio||1;canvas.width=Math.max(1,Math.round(width*dpr));canvas.height=Math.max(1,Math.round(height*dpr));gl.viewport(0,0,canvas.width,canvas.height);
gl.clearColor(0.07,0.1,0.12,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
gl.uniform1f(uniform("yaw"),yaw);gl.uniform1f(uniform("pitch"),pitch);gl.uniform1f(uniform("zoom"),zoom);gl.uniform1f(uniform("aspect"),width/Math.max(height,1));
gl.uniform1f(uniform("nativeMode"),nativeMode);gl.uniform1f(uniform("cutMode"),cutMode);gl.uniform1f(uniform("heightScale"),1);
gl.drawElements(gl.TRIANGLES,data.triangle_count*3,gl.UNSIGNED_INT,0);}
function update(){document.getElementById("native").classList.toggle("active",nativeMode===1);document.getElementById("candidate").classList.toggle("active",nativeMode===0);document.getElementById("cut").textContent=`Cut coloring: ${cutMode?"on":"off"}`;draw();}
document.getElementById("native").onclick=()=>{nativeMode=1;update()};document.getElementById("candidate").onclick=()=>{nativeMode=0;update()};
document.getElementById("cut").onclick=()=>{cutMode=1-cutMode;update()};document.getElementById("reset").onclick=()=>{yaw=-0.7;pitch=-0.65;zoom=1.25;update()};
canvas.onpointerdown=event=>{drag=true;lastX=event.clientX;lastY=event.clientY;canvas.setPointerCapture(event.pointerId)};
canvas.onpointerup=()=>drag=false;canvas.onpointermove=event=>{if(!drag)return;yaw+=(event.clientX-lastX)*0.008;pitch=Math.max(-1.5,Math.min(1.5,pitch+(event.clientY-lastY)*0.008));lastX=event.clientX;lastY=event.clientY;draw()};
canvas.onwheel=event=>{event.preventDefault();zoom=Math.max(0.3,Math.min(8,zoom*Math.exp(event.deltaY*0.001)));draw()};
new ResizeObserver(draw).observe(canvas);update();
</script></body></html>'''
