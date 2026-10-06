"""Pinned cold review of TD bundles, with solved water kept on its own bed."""

import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_source import load_td_source_bundle
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_storage_dispatch_io import load_storage as load_basin_storage
from terrain_pipeline.td_material_field import load_material_field
from terrain_pipeline.td_basin_morphology import load_morphology
from terrain_pipeline.td_basin_breach import load_saddle_breach


SCHEMA = "td-basin-review-v1"
ALGORITHM = "td-pinned-native-data-continuous-terrain-native-water-lod-v3"
LOADERS = {"source": load_td_source_bundle, "hierarchy": load_basin_hierarchy,
           "storage": load_basin_storage, "material": load_material_field,
           "morphology": load_morphology, "breach": load_saddle_breach}
MAX_REVIEW_BYTES = 256 * 1024 ** 2


def load_review_inputs(records):
    if not isinstance(records, dict) or not {"source", "hierarchy", "material"} <= set(records) or set(records) - set(LOADERS):
        raise ValueError("review needs pinned source/hierarchy/material and known optional roles")
    inputs = {}
    for role, record in records.items():
        if not isinstance(record, dict) or set(record) != {"path", "expected_sha256", "expected_identity"}:
            raise ValueError("each review input requires path and both external pins")
        for key in ("expected_sha256", "expected_identity"):
            value = record[key]
            if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("invalid review external pin")
        inputs[role] = LOADERS[role](record["path"], expected_sha256=record["expected_sha256"], expected_identity=record["expected_identity"])
    _validate_links(inputs)
    return inputs


def _validate_links(inputs):
    source = inputs["source"]
    hierarchy = inputs["hierarchy"]
    height = source["arrays"]["height_m"]
    shape = height.shape
    source_metadata = source["metadata"]
    if hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"]:
        raise ValueError("review source/hierarchy identity chain mismatch")
    for role, bundle in inputs.items():
        metadata = bundle["metadata"]
        if metadata["spacing_m"] != source_metadata["spacing_m"] or metadata["origin_m_xz"] != source_metadata["origin_m_xz"]:
            raise ValueError("review coordinate mismatch: " + role)
        arrays = bundle["arrays"]
        if role == "material":
            if arrays["erodibility"].shape != shape or not np.array_equal(arrays["protected_mask"], source["arrays"]["protected_mask"]):
                raise ValueError("review material coverage/protection mismatch")
        else:
            bed = arrays["original_height_m"] if role in ("morphology", "breach") else arrays["height_m"]
            if not np.array_equal(bed, height, equal_nan=True) or not np.array_equal(arrays["valid_mask"], source["arrays"]["valid_mask"]):
                raise ValueError("review original bed/coverage mismatch: " + role)
    if "storage" in inputs:
        storage = inputs["storage"]
        if storage["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or not np.array_equal(storage["arrays"]["face_cells"], hierarchy["arrays"]["face_cells"]):
            raise ValueError("review hydro/topology identity chain mismatch")
    if "morphology" in inputs and inputs["morphology"]["metadata"]["material_identity_sha256"] != inputs["material"]["identity_sha256"]:
        raise ValueError("review morphology material identity mismatch")
    if "breach" in inputs:
        metadata = inputs["breach"]["metadata"]
        if metadata["source_identity_sha256"] != source["identity_sha256"] or metadata["topology_identity_sha256"] != hierarchy["identity_sha256"] or metadata["material_identity_sha256"] != inputs["material"]["identity_sha256"]:
            raise ValueError("review breach source/topology/material chain mismatch")
        if "storage" not in inputs or metadata["hydro_identity_sha256"] != inputs["storage"]["identity_sha256"]:
            raise ValueError("review breach requires pinned matching hydro package")


def _plain(value):
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def make_basin_review(inputs):
    """Adapt complete frozen arrays only; never interpolate a hydraulic state."""
    _validate_links(inputs)
    source = inputs["source"]
    topology = inputs["hierarchy"]["arrays"]
    height = source["arrays"]["height_m"]
    material = inputs["material"]["arrays"]
    fields = {"H0_m": height, "valid_mask": source["arrays"]["valid_mask"],
              "protected_mask": source["arrays"]["protected_mask"], "basin_owner": topology["cell_owner"],
              "contribution_owner": topology["contribution_owner"],
              "erodibility": material["erodibility"], "erodible_thickness_m": material["erodible_thickness_m"],
              "weak_path_preference": material["weak_path_preference"]}
    candidates = {"baseline": {"height_m": height, "height_delta_m": np.zeros(height.shape),
                               "flags": {"status": "baseline", "hydrology_coupled_verified": False,
                                         "transient_converged": False, "morphology_flux_ready": False}}}
    for role in ("morphology", "breach"):
        if role in inputs:
            bundle = inputs[role]
            candidates[role] = {"height_m": bundle["arrays"]["height_m"],
                                "height_delta_m": bundle["arrays"]["height_delta_m"],
                                "flags": bundle["metadata"],
                                "material_ledger": bundle["metadata"]["ledger"],
                                "stored_solid_m3": bundle["arrays"]["stored_solid_m3"]}
            if role == "breach":
                candidates[role]["path_cell_ids"] = bundle["arrays"]["path_cell_ids"]
    water = None
    if "storage" in inputs:
        storage = inputs["storage"]
        depth = storage["arrays"]["depth_m"]
        if depth.ndim == 2:
            depth = depth.reshape((-1,) + height.shape)
        threshold = storage["metadata"]["parameters"]["wet_threshold_m"]
        water = {"time_s": np.arange(depth.shape[0]) * storage["metadata"]["dt_s"],
                 "cell_stores_mm": {name: storage["arrays"][name].reshape((-1,) + height.shape) for name in ("soil_mm", "fast_mm", "slow_mm")},
                 "depth_m": depth, "surface_formula": "H0_m + depth_m where valid and depth > wet_threshold_m; otherwise no water surface",
                 "bed_identity_sha256": source["identity_sha256"], "hydro_identity_sha256": storage["identity_sha256"],
                 "semantics": "solved cell water on original storage bed; never coupled to unverified candidate",
                 "ledger": {name: np.sum(values, axis=1) for name, values in storage["arrays"].items() if name.endswith("_m3") and values.ndim == 2 and values.shape[1] == height.size},
                 "flags": {**storage["metadata"], "transient_converged": storage["metadata"].get("transient_converged", False),
                           "morphology_flux_ready": storage["metadata"].get("morphology_flux_ready", False)}}
    stride = max(1, int(np.ceil(max(height.shape) / 64)))
    displayed = int(np.count_nonzero(source["arrays"]["valid_mask"][::stride, ::stride]))
    displayed_mask = np.zeros(height.shape, bool)
    displayed_mask[::stride, ::stride] = True
    omitted = source["arrays"]["valid_mask"] & ~displayed_mask
    omitted_ids = np.flatnonzero(omitted.ravel())
    review = {"schema": SCHEMA, "algorithm": ALGORITHM, "shape": list(height.shape), "spacing_m": source["metadata"]["spacing_m"],
              "origin_m_xz": source["metadata"]["origin_m_xz"], "coordinates": "X east; Z south; [z,x]; cell_id=z*nx+x; metres",
              "inputs": {role: bundle["identity_sha256"] for role, bundle in inputs.items()},
              "fields": fields, "candidates": candidates,
              "topology": {name: topology[name] for name in ("node_parent", "node_birth_m", "node_upper_m", "node_unknown_contact", "face_cells", "face_level_m", "face_merge_node")},
              "water": water, "sampling": {"stride": 1, "omitted_cells": 0, "omitted_water_volume_m3": 0},
              "render_lod": {"stride": stride, "displayed_points": displayed,
                             "terrain_interpolation": True, "water_interpolation": False,
                             "omitted_points": int(np.count_nonzero(omitted)),
                             "omitted_cell_ids": omitted_ids,
                             "omitted_footprint_area_m2": int(np.count_nonzero(omitted)) * source["metadata"]["spacing_m"] ** 2,
                             "footprint_policy": "terrain triangles interpolate sampled native centre heights for display only; water covers only sampled native footprints; no wetness interpolation",
                             "omitted_water_volume_m3_by_frame": None if water is None else np.sum(depth[:, omitted], axis=1) * source["metadata"]["spacing_m"] ** 2},
              "flags": {"readonly": True, "hydraulic_ready": False, "natural_outlet_verified": False,
                        "transient_converged": False, "morphology_flux_ready": False,
                        "water_available": water is not None, "water_on_candidate_verified": False},
              "limitations": "Finite generative prototype. Solved water belongs to baseline bed; derived geometry needs topology rebuild and separate coupled validation. 3D cell surfaces do not certify hydraulic connectivity."}
    return _plain(review)


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TD 盆地只读审查</title>
<style>body{font:14px system-ui;margin:16px;background:#142126;color:#dfebe9}select,input,button{margin:5px}canvas{display:block;width:100%;height:65vh;background:#0a151a}pre{white-space:pre-wrap;max-height:30vh;overflow:auto}.note{color:#f0c985}</style>
<h2>TD 盆地只读审查</h2><p class="note">生成启发原型；瞬态未认证，形态通量未就绪。地形连续LOD三角面是高度插值，仅供展示；水保持原生采样格片，不插值。水面只对应冻结求解状态。未解析米级河槽，不认证水力连通；水遗漏footprint和体积见详情。</p>
<label>候选<select id="candidate"></select></label><label>图层<select id="layer"><option value="bed">床面</option><option value="H0_m">原床</option><option value="delta">切填差</option><option value="erodibility">抗蚀倒数</option><option value="erodible_thickness_m">材料厚度</option><option value="weak_path_preference">弱路径偏好</option><option value="basin_owner">盆地归属</option></select></label>
<label>视图<select id="view"><option>2D</option><option>3D</option></select></label><label><input id="water" type="checkbox" checked>求解水面</label><label><input id="saddle" type="checkbox">跨归属鞍部面</label>
<label>水深展示阈值(m)<input id="waterThreshold" type="number" min="0" step="0.01" value="0.05"></label>
<label>时间<input id="time" type="range" min="0" max="0" value="0"><span id="stamp"></span></label><button id="play">播放</button><button id="fit">重置视角</button><span>拖动旋转 · 滚轮缩放 · 点击采样格读取</span><canvas id="canvas"></canvas><pre id="details"></pre>
<script>const data=__DATA__;const canvas=document.getElementById('canvas'),context=canvas.getContext('2d');const candidate=document.getElementById('candidate'),layer=document.getElementById('layer'),view=document.getElementById('view'),time=document.getElementById('time');let yaw=-.6,pitch=.7,last=null,zoom=1,playing=null,moved=false,pick=null,screenCells=[];
for(const name of Object.keys(data.candidates)){const option=document.createElement('option');option.value=name;option.textContent=name;candidate.append(option)}time.max=data.water?data.water.time_s.length-1:0;
view.value='3D';zoom=1.2;
function range(values){let low=Infinity,high=-Infinity;for(const row of values)for(const value of row)if(value!==null){low=Math.min(low,value);high=Math.max(high,value)}return[low,high]}
function draw(){canvas.width=canvas.clientWidth*devicePixelRatio;canvas.height=canvas.clientHeight*devicePixelRatio;context.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);const width=canvas.clientWidth,height=canvas.clientHeight,rows=data.shape[0],cols=data.shape[1],chosen=data.candidates[candidate.value];let values=layer.value==='bed'?chosen.height_m:layer.value==='delta'?chosen.height_delta_m:data.fields[layer.value];const[low,high]=range(values),[bedLow,bedHigh]=range(chosen.height_m);const scale=Math.min(width/(cols+rows*.35),height/(rows+cols*.25))*.8*zoom;context.clearRect(0,0,width,height);screenCells=[];
function project(col,row,elevation){if(view.value==='2D')return[width/2+(col-cols/2)*scale,height/2+(row-rows/2)*scale];const centerX=col-cols/2,centerZ=row-rows/2,rotX=centerX*Math.cos(yaw)-centerZ*Math.sin(yaw),rotZ=centerX*Math.sin(yaw)+centerZ*Math.cos(yaw),vertical=(elevation-bedLow)/data.spacing_m;return[width/2+rotX*scale,height*.7+(rotZ*Math.sin(pitch)-vertical*Math.cos(pitch))*scale]}
function quad(col,row,elevation,fill){const extent=1/data.render_lod.stride,points=[[col,row],[col+extent,row],[col+extent,row+extent],[col,row+extent]].map(point=>project(point[0],point[1],elevation));context.beginPath();points.forEach((point,index)=>index?context.lineTo(...point):context.moveTo(...point));context.closePath();context.fillStyle=fill;context.fill()}
function terrain(col,row,fill){if(row+1>=rows||col+1>=cols){quad(col,row,chosen.height_m[row][col],fill);return}const corners=[[row,col],[row,col+1],[row+1,col+1],[row+1,col]];if(corners.some(([cornerRow,cornerCol])=>!data.fields.valid_mask[cornerRow][cornerCol]))return;const points=corners.map(([cornerRow,cornerCol])=>project(cornerCol+.5/data.render_lod.stride,cornerRow+.5/data.render_lod.stride,chosen.height_m[cornerRow][cornerCol]));const slopeX=(chosen.height_m[row][col+1]-chosen.height_m[row][col])/data.spacing_m,slopeZ=(chosen.height_m[row+1][col]-chosen.height_m[row][col])/data.spacing_m;const shade=Math.max(.45,Math.min(1.15,.85+(-slopeX*.4+slopeZ*.3)/Math.sqrt(1+slopeX*slopeX+slopeZ*slopeZ)));for(const triangle of [[0,1,2],[0,2,3]]){context.beginPath();triangle.forEach((index,position)=>position?context.lineTo(...points[index]):context.moveTo(...points[index]));context.closePath();context.fillStyle=fill;context.fill();if(layer.value==='bed'||layer.value==='H0_m'){context.fillStyle=shade<1?`rgba(0,0,0,${1-shade})`:`rgba(255,255,255,${shade-1})`;context.fill()}}}
const cells=[];for(let row=0;row<rows;row++)for(let col=0;col<cols;col++)if(data.fields.valid_mask[row][col])cells.push([row,col]);if(view.value==='3D')cells.sort((first,second)=>((first[1]-second[1])*Math.sin(yaw)+(first[0]-second[0])*Math.cos(yaw)));
const frame=Number(time.value),showWater=data.water&&candidate.value==='baseline'&&document.getElementById('water').checked;
for(const[row,col]of cells){const value=values[row][col],fraction=(value-low)/(high-low||1);let fill=`rgb(${Math.round(35+150*fraction)},${Math.round(75+110*fraction)},${Math.round(70+80*fraction)})`;if(layer.value==='delta')fill=value<0?'#d99b60':value>0?'#88cbb4':'#32464c';if(data.fields.protected_mask[row][col])fill='#e784ad';terrain(col,row,fill);screenCells.push({row,col,point:project(col+.5/data.render_lod.stride,row+.5/data.render_lod.stride,chosen.height_m[row][col])})}
const displayThreshold=Math.max(0,Number(document.getElementById('waterThreshold').value)||0),sampleArea=(data.spacing_m/data.render_lod.stride)**2;let thresholdHiddenVolume=0;if(data.water)for(const[row,col]of cells){const depth=data.water.depth_m[frame][row][col];if(depth<=Math.max(displayThreshold,data.water.flags.parameters.wet_threshold_m))thresholdHiddenVolume+=depth*sampleArea;else if(showWater)quad(col,row,data.fields.H0_m[row][col]+depth,'#5aaee5aa')}data.display_omission={threshold_m:displayThreshold,threshold_hidden_sampled_water_m3:thresholdHiddenVolume,lod_omitted_water_m3:data.render_lod.omitted_water_volume_m3_by_frame?.[frame]||0,total_hidden_water_m3:thresholdHiddenVolume+(data.render_lod.omitted_water_volume_m3_by_frame?.[frame]||0),scope:'threshold acts only on rendered native samples; LOD omission separate; computational depth unchanged'};
if(pick){const pickedRow=pick.row/data.render_lod.stride,pickedCol=pick.col/data.render_lod.stride;pick.derived_m=chosen.height_m[pickedRow][pickedCol];pick.delta_m=chosen.height_delta_m[pickedRow][pickedCol];pick.erodible_thickness_m=data.fields.erodible_thickness_m[pickedRow][pickedCol];pick.weak_path_preference=data.fields.weak_path_preference[pickedRow][pickedCol];pick.water_depth_m=showWater?data.water?.depth_m[frame][pickedRow][pickedCol]:null;pick.water_scope=showWater?'matching baseline solved state':'no matching candidate solved state';pick.soil_mm=data.water?.cell_stores_mm.soil_mm[frame][pickedRow][pickedCol];pick.fast_mm=data.water?.cell_stores_mm.fast_mm[frame][pickedRow][pickedCol];pick.slow_mm=data.water?.cell_stores_mm.slow_mm[frame][pickedRow][pickedCol]}
data.render_lod.current_display_omission=data.display_omission;
if(document.getElementById('saddle').checked){context.strokeStyle='#ffd77e';context.lineWidth=1;for(const face of data.saddle_overlay){context.beginPath();context.moveTo(...project(face[0],face[1],face[4]));context.lineTo(...project(face[2],face[3],face[4]));context.stroke()}}
document.getElementById('stamp').textContent=data.water?`${data.water.time_s[frame]} s`:'无求解水帧';document.getElementById('details').textContent=JSON.stringify({global_flags:data.flags,water_flags:data.water?.flags,candidate_flags:chosen.flags,picked_cell:pick,material_ledger:chosen.material_ledger,inputs:data.inputs,raw_input_records:data.raw_input_records,sampling:data.sampling,render_lod:data.render_lod,water:showWater?'baseline solved cell surfaces':'hidden: no matching solved candidate state',limitations:data.limitations},null,2)}
for(const control of document.querySelectorAll('select,input'))control.addEventListener('input',draw);canvas.addEventListener('pointerdown',event=>{moved=false;last=[event.clientX,event.clientY];canvas.setPointerCapture(event.pointerId)});canvas.addEventListener('pointermove',event=>{if(last){const deltaX=event.clientX-last[0],deltaY=event.clientY-last[1];if(Math.abs(deltaX)+Math.abs(deltaY)>2)moved=true;yaw+=deltaX*.005;pitch=Math.max(.1,Math.min(1.5,pitch+deltaY*.005));last=[event.clientX,event.clientY];draw()}});canvas.addEventListener('pointerup',event=>{last=null;if(!moved){const rectangle=canvas.getBoundingClientRect(),point=[event.clientX-rectangle.left,event.clientY-rectangle.top];let nearest=null,distance=Infinity;for(const cell of screenCells){const squared=(cell.point[0]-point[0])**2+(cell.point[1]-point[1])**2;if(squared<distance){distance=squared;nearest=cell}}if(nearest&&distance<400){const {row,col}=nearest,frame=Number(time.value),nativeRow=row*data.render_lod.stride,nativeCol=col*data.render_lod.stride;pick={cell_id:nativeRow*data.native_shape[1]+nativeCol,row:nativeRow,col:nativeCol,H0_m:data.fields.H0_m[row][col],derived_m:data.candidates[candidate.value].height_m[row][col],delta_m:data.candidates[candidate.value].height_delta_m[row][col],erodibility:data.fields.erodibility[row][col],basin_owner:data.fields.basin_owner[row][col],water_depth_m:data.water?.depth_m[frame][row][col]}}draw()}});canvas.addEventListener('wheel',event=>{event.preventDefault();zoom=Math.max(.2,Math.min(10,zoom*Math.exp(-event.deltaY*.001)));draw()},{passive:false});document.getElementById('fit').onclick=()=>{yaw=-.6;pitch=.7;zoom=1;draw()};document.getElementById('play').onclick=()=>{if(playing){clearInterval(playing);playing=null;document.getElementById('play').textContent='播放'}else if(data.water){document.getElementById('play').textContent='暂停';playing=setInterval(()=>{time.value=(Number(time.value)+1)%(Number(time.max)+1);draw()},500)}};window.addEventListener('resize',draw);draw();</script></html>'''


def export_basin_review(records, output_dir):
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    inputs = load_review_inputs(records)
    review = make_basin_review(inputs)
    review["raw_input_records"] = {role: {**record, "path": str(Path(record["path"]).resolve())} for role, record in records.items()}
    payload = json.dumps(review, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_REVIEW_BYTES:
        raise ValueError("review byte budget exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".td-review-stage-", dir=output.parent))
    try:
        (temporary / "review.json").write_text(payload, encoding="utf-8")
        browser_review = dict(review)
        browser_review["fields"] = {name: np.asarray(values)[::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist() for name, values in review["fields"].items()}
        browser_review["candidates"] = {}
        for name, candidate in review["candidates"].items():
            browser_review["candidates"][name] = {key: value for key, value in candidate.items() if key not in ("height_m", "height_delta_m", "stored_solid_m3")}
            for key in ("height_m", "height_delta_m"):
                browser_review["candidates"][name][key] = np.asarray(candidate[key])[::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist()
        if review["water"] is not None:
            browser_review["water"] = {key: value for key, value in review["water"].items() if key not in ("depth_m", "surface_m", "cell_stores_mm")}
            browser_review["water"]["cell_stores_mm"] = {name: np.asarray(values)[:, ::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist() for name, values in review["water"]["cell_stores_mm"].items()}
            browser_review["water"]["depth_m"] = np.asarray(review["water"]["depth_m"])[:, ::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist()
        browser_review["native_shape"] = review["shape"]
        browser_review["shape"] = list(np.asarray(browser_review["fields"]["H0_m"]).shape)
        browser_review["spacing_m"] = review["spacing_m"] * review["render_lod"]["stride"]
        browser_review["topology"] = {"face_cells": [], "face_level_m": [], "face_merge_node": []}
        saddle_overlay = []
        native_cols = review["shape"][1]
        owners = np.asarray(review["fields"]["basin_owner"]).ravel()
        stride = review["render_lod"]["stride"]
        for face, level in zip(review["topology"]["face_cells"], review["topology"]["face_level_m"]):
            first, second = face
            if owners[first] == owners[second]:
                continue
            row, col = divmod(first, native_cols)
            target_row, target_col = divmod(second, native_cols)
            endpoints = [col + 1, row, col + 1, row + 1] if row == target_row else [col, row + 1, col + 1, row + 1]
            saddle_overlay.append([coordinate / stride for coordinate in endpoints] + [level])
        browser_review["saddle_overlay"] = saddle_overlay
        browser_review["render_lod"] = {key: value for key, value in review["render_lod"].items() if key != "omitted_cell_ids"}
        safe_payload = json.dumps(browser_review, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (temporary / "review.html").write_text(HTML.replace("__DATA__", safe_payload), encoding="utf-8")
        manifest = {"schema": SCHEMA, "algorithm": ALGORITHM,
                    "input_algorithms": {role: bundle["metadata"].get("algorithm", bundle["metadata"].get("schema")) for role, bundle in inputs.items()},
                    "flags": review["flags"],
                    "inputs": {role: {**record, "path": str(Path(record["path"]).resolve())} for role, record in records.items()},
                    "files": {name: file_sha256(temporary / name) for name in ("review.json", "review.html")},
                    "review_identity_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    "renderer": "offline canvas projected cell surfaces; no external dependencies", "source_unchanged": True}
        for record in records.values():
            if file_sha256(record["path"]) != record["expected_sha256"]:
                raise ValueError("review input changed during export")
        (temporary / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.rename(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def load_selection_proof(record, *, expected_candidate_records_sha256=None):
    """Load separately pinned evidence; never promote bundle flags from a scope claim."""
    if not isinstance(record, dict) or set(record) != {"path", "expected_sha256"}:
        raise ValueError("selection proof requires external path/SHA256")
    path = Path(record["path"])
    if path.stat().st_size > 4 * 1024 ** 2 or file_sha256(path) != record["expected_sha256"]:
        raise ValueError("selection proof hash/size mismatch")
    proof = json.loads(path.read_text(encoding="utf-8"))
    if proof.get("schema") != "td-basin-selection-proof-v1" or not isinstance(proof.get("scopes"), list):
        raise ValueError("unsupported selection proof schema")
    if expected_candidate_records_sha256 is not None and proof.get("candidate_records_sha256") != expected_candidate_records_sha256:
        raise ValueError("selection proof refers to another candidate index")
    scope_ids = set()
    allowed = {"representative_basin", "full_domain_baseline", "candidate_full_domain", "candidate_selection"}
    for scope in proof["scopes"]:
        if not isinstance(scope, dict) or scope.get("scope") not in allowed or not isinstance(scope.get("scope_id"), str) or scope["scope_id"] in scope_ids:
            raise ValueError("invalid proof scope")
        scope_ids.add(scope["scope_id"])
        if type(scope.get("passed")) is not bool or not isinstance(scope.get("artifacts"), list) or not scope["artifacts"]:
            raise ValueError("proof scope requires a boolean verdict and external artifacts")
        for artifact in scope["artifacts"]:
            if set(artifact) != {"path", "expected_sha256"} or file_sha256(artifact["path"]) != artifact["expected_sha256"]:
                raise ValueError("proof scope artifact external hash mismatch")
        if scope["scope"] in ("candidate_full_domain", "candidate_selection") and not isinstance(scope.get("candidate_id"), str):
            raise ValueError("candidate proof needs candidate_id")
        if not isinstance(scope.get("limitations"), str):
            raise ValueError("proof must describe scope limitations")
    return proof


def load_basin_review(directory, *, expected_manifest_sha256):
    directory = Path(directory)
    if file_sha256(directory / "manifest.json") != expected_manifest_sha256:
        raise ValueError("external review manifest hash mismatch")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema"] != SCHEMA or set(manifest["files"]) != {"review.json", "review.html"}:
        raise ValueError("unsupported review manifest")
    for name, expected in manifest["files"].items():
        if (directory / name).stat().st_size > MAX_REVIEW_BYTES * 2 or file_sha256(directory / name) != expected:
            raise ValueError("review file hash or size mismatch")
    payload = (directory / "review.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["review_identity_sha256"]:
        raise ValueError("review identity mismatch")
    return json.loads(payload)


def load_candidate_comparison(records_path, *, expected_sha256, baseline_records,
                              selection_proof=None):
    """Cold-load 55's fixed index, then check each candidate without retaining all water arrays."""
    records_path = Path(records_path).resolve()
    if records_path.stat().st_size > 4 * 1024 ** 2 or file_sha256(records_path) != expected_sha256:
        raise ValueError("external candidate records hash/size mismatch")
    index = json.loads(records_path.read_text(encoding="utf-8"))
    if index.get("schema") != "td-basin-candidate-records-v1":
        raise ValueError("unsupported candidate comparison schema")
    candidate_proof = None
    if selection_proof is not None:
        candidate_proof = load_selection_proof(selection_proof, expected_candidate_records_sha256=expected_sha256)
    if not isinstance(baseline_records, dict) or set(baseline_records) != {"source", "hierarchy", "material", "ordinary", "strong"}:
        raise ValueError("comparison requires exact baseline source/hierarchy/material/ordinary/strong pins")
    base = {role: baseline_records[role] for role in ("source", "hierarchy", "material")}
    original = None
    baseline_ids = {}
    algorithms = {}
    for scenario in ("ordinary", "strong"):
        inputs = load_review_inputs({**base, "storage": baseline_records[scenario]})
        original = inputs["source"]["arrays"]["height_m"].copy()
        baseline_ids[scenario] = inputs["storage"]["identity_sha256"]
        algorithms[scenario] = inputs["storage"]["metadata"]["algorithm"]
        del inputs
    candidates = index.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 11:
        raise ValueError("candidate count exceeds baseline + two morphology + eight saddle budget")
    ids = [record.get("candidate_id") for record in candidates]
    if any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids) or "baseline" not in ids or index.get("selected_candidate_id") not in ids:
        raise ValueError("invalid candidate IDs/selection")
    source_identity = baseline_records["source"]["expected_identity"]
    topology_identity = baseline_records["hierarchy"]["expected_identity"]
    summaries = []
    for record in candidates:
        candidate_id = record["candidate_id"]
        if candidate_id == "baseline":
            if record.get("source_identity_sha256") != source_identity or record.get("hierarchy_identity_sha256") != topology_identity:
                raise ValueError("candidate index baseline identity mismatch")
            if any(record.get(scenario + "_identity_sha256") != baseline_ids[scenario] for scenario in baseline_ids):
                raise ValueError("candidate index baseline hydro mismatch")
            summaries.append({"candidate_id": "baseline", "records": baseline_records, "flags": record})
            continue
        role = "breach" if candidate_id.startswith("saddle_breach") else "morphology"
        artifact = record.get("morphology")
        _candidate_artifact(artifact, records_path.parent)
        geometry_inputs = load_review_inputs({**base, "storage": baseline_records["ordinary"], role: artifact})
        geometry = geometry_inputs[role]
        derived = geometry["arrays"]["height_m"].copy()
        ledger = geometry["metadata"]["ledger"]
        if record.get("material_ledger") != ledger:
            raise ValueError("candidate summary ledger differs from pinned geometry")
        delta = derived - original
        if record.get("changed_cells") != int(np.count_nonzero(delta)) or not np.isclose(record.get("max_abs_delta_m"), float(np.max(np.abs(delta))), rtol=0, atol=1e-9):
            raise ValueError("candidate summary geometry differs from pinned geometry")
        del geometry_inputs, geometry
        coupled = {}
        if any(key in record for key in ("source", "hierarchy", "ordinary", "strong")):
            if not all(key in record for key in ("source", "hierarchy", "ordinary", "strong")):
                raise ValueError("partially published candidate coupled state")
            for key in ("source", "hierarchy", "ordinary", "strong"):
                _candidate_artifact(record[key], records_path.parent)
            for scenario in ("ordinary", "strong"):
                selected_records = {"source": record["source"], "hierarchy": record["hierarchy"],
                                    "material": base["material"], "storage": record[scenario]}
                inputs = load_review_inputs(selected_records)
                if not np.array_equal(inputs["source"]["arrays"]["height_m"], derived, equal_nan=True):
                    raise ValueError("candidate rebuilt source differs from pinned geometry")
                if inputs["storage"]["metadata"]["algorithm"] != algorithms[scenario]:
                    raise ValueError("candidate/baseline water algorithm differs")
                coupled[scenario] = {"records": selected_records, "algorithm": algorithms[scenario],
                                     "transient_converged": False, "morphology_flux_ready": False,
                                     "water_bed_identity_sha256": record["source"]["expected_identity"]}
                del inputs
        summaries.append({"candidate_id": candidate_id, "geometry_role": role, "geometry_record": artifact,
                          "original_source_record": base["source"], "flags": record,
                          "coupled_scenarios": coupled, "water_available": bool(coupled),
                          "material_ledger": ledger})
    if file_sha256(records_path) != expected_sha256:
        raise ValueError("candidate index changed during cold adaptation")
    return {"schema": "td-basin-candidate-review-v1", "algorithm": ALGORITHM,
            "records_path": str(records_path), "expected_sha256": expected_sha256,
            "selected_candidate_id": index["selected_candidate_id"], "candidates": summaries,
            "selection_proof": candidate_proof,
            "flags": {"transient_converged": False, "morphology_flux_ready": False, "publishable": False},
            "limitations": "Coupled water is bound to each rebuilt bed; selection/sensitivity evidence is reported separately and never inferred from a successful load."}


def _candidate_artifact(record, directory):
    if not isinstance(record, dict) or set(record) != {"path", "expected_sha256", "expected_identity"}:
        raise ValueError("candidate artifact requires both external pins")
    path = Path(record["path"]).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("candidate artifact escapes fixed candidate directory")


def export_comparison_navigation(comparison, page_links, output_path):
    """Publish actual page links and explicit selection scope, without inventing candidate water."""
    from terrain_pipeline.mountain_source_adapter import publish_bytes
    if set(page_links) - {candidate["candidate_id"] for candidate in comparison["candidates"]}:
        raise ValueError("navigation links name an unknown candidate")
    rows = []
    for candidate in comparison["candidates"]:
        candidate_id = candidate["candidate_id"]
        links = page_links.get(candidate_id, {})
        if set(links) - {"ordinary", "strong"}:
            raise ValueError("navigation scenario must be ordinary or strong")
        anchors = []
        for scenario in ("ordinary", "strong"):
            if scenario in links:
                target = Path(links[scenario]).resolve(strict=True)
                relative = os.path.relpath(target, Path(output_path).resolve().parent).replace("\\", "/")
                anchors.append('<a href="' + html.escape(relative, quote=True) + '">' + scenario + '</a>')
            else:
                anchors.append(scenario + '：无冻结审查页面')
        flags = candidate.get("flags", {})
        reasons = flags.get("rejection_reasons", [])
        rows.append('<tr><td>' + html.escape(candidate_id) + '</td><td>' + ' · '.join(anchors) + '</td><td>' + html.escape('; '.join(reasons) or '未记录拒绝') + '</td><td>' + html.escape(str(flags.get("selected", False))) + '</td></tr>')
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>TD 候选对照</title><h1>TD 候选只读对照</h1><p>选择范围：固定记录中的有限候选。数值敏感性、形态通量及发布门槛未认证；冷读成功不构成候选接受。没有匹配新床水文时不提供新水面。</p><p>记录选择：' + html.escape(comparison["selected_candidate_id"]) + '</p><table border="1"><tr><th>候选</th><th>两雨页面</th><th>拒绝原因</th><th>记录选中</th></tr>' + ''.join(rows) + '</table><pre>' + html.escape(json.dumps(comparison["flags"], ensure_ascii=False, indent=2)) + '</pre></html>'
    publish_bytes(output_path, page.encode("utf-8"))
    return Path(output_path)
