import * as THREE from 'three';
import {OrbitControls} from './vendor/node_modules/three/examples/jsm/controls/OrbitControls.js';

// Read-only viewer for the pinned special-terrain surface bundles. It draws the stored
// arrays -- full-resolution surface, analytic reference floor, per-cell erosion change --
// and nothing else: no hydrology is re-run and no certificate is implied. The four
// capability flags ride along in the descriptor so the export cannot look like a result.

const element=id=>document.getElementById(id);
const wrap=document.querySelector('.canvas-wrap');
const map=document.createElement('canvas');
const display=document.createElement('canvas');
map.id='specialMap';display.id='specialSurface';
map.className=display.className='special-canvas hidden';
wrap.prepend(map,display);
let active=false,catalog=null,descriptor=null,arrays={},elevation=null,serial=0,pending=false,renderer=null,selected=null,renderAspect=null;
const scene=TerraView.createScene(THREE);
const camera=new THREE.PerspectiveCamera(45,1,.1,100000);
const group=new THREE.Group();scene.add(group);
let controls=null;
const mapView={zoom:1,panX:0,panY:0};
const formSelect=element('specialForm');
const {neutral:NEUTRAL_RGB,incision:INCISION_RGB,deposition:DEPOSITION_RGB}=TerraTheme.diverge;
const NEUTRAL=NEUTRAL_RGB.map(v=>v/255),INCISION=INCISION_RGB.map(v=>v/255),DEPOSITION=DEPOSITION_RGB.map(v=>v/255);

async function json(path){const response=await fetch(path,{signal:AbortSignal.timeout(60000)});const body=await response.json();if(!response.ok)throw Error(body.error||response.status);return body}
function clearMeshes(){while(group.children.length){const item=group.children[0];group.remove(item);item.geometry?.dispose();item.material?.dispose()}}
function layerNames(){return ['surface','reference','change','protected']}
// A diverging ramp: incision (stored negative change) reads rust, deposition reads teal.
function changeColours(values,limit){
    const colours=new Float32Array(values.length*3);
    for(let index=0;index<values.length;index++){
        const ratio=Math.max(-1,Math.min(1,values[index]/(limit||1)));
        const target=ratio<0?INCISION:ratio>0?DEPOSITION:NEUTRAL,weight=Math.abs(ratio);
        for(let channel=0;channel<3;channel++)colours[index*3+channel]=NEUTRAL[channel]+(target[channel]-NEUTRAL[channel])*weight;
    }
    return colours;
}
// 顶点色属性按线性空间解释；changeColours 给的是 sRGB(0..1)，上传 GPU 前要转换，否则 3D 比 2D 偏亮。
function linearise(colours){
    const out=new Float32Array(colours.length);
    for(let index=0;index<colours.length;index++){const s=colours[index];out[index]=s<=.04045?s/12.92:Math.pow((s+.055)/1.055,2.4)}
    return out;
}
function surfaceGeometry(){
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(arrays.surface_vertices,3));
    geometry.setIndex(new THREE.BufferAttribute(arrays.surface_triangles,1));
    geometry.computeVertexNormals();
    return geometry;
}
function buildMeshes(){
    const geometry=surfaceGeometry();
    const surface=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:TerraView.material.terrain,side:THREE.DoubleSide,roughness:.9,metalness:0}));
    surface.name='surface';group.add(surface);
    const reference=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:TerraView.material.reference,side:THREE.DoubleSide,wireframe:true,transparent:true,opacity:.34,metalness:0}));
    reference.name='reference';group.add(reference);
    const limit=Math.max(Math.abs(descriptor.change_m[0]),Math.abs(descriptor.change_m[1]));
    const colours=changeColours(arrays.change,limit);
    const colourGeometry=new THREE.BufferGeometry();
    colourGeometry.setAttribute('position',new THREE.BufferAttribute(arrays.surface_vertices,3));
    colourGeometry.setIndex(new THREE.BufferAttribute(arrays.surface_triangles,1));
    colourGeometry.setAttribute('color',new THREE.BufferAttribute(linearise(colours),3));
    const change=new THREE.Mesh(colourGeometry,new THREE.MeshStandardMaterial({vertexColors:true,side:THREE.DoubleSide,transparent:true,opacity:.62,roughness:.9,metalness:0,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-2}));
    change.name='change';group.add(change);
    if(descriptor.protected_cells>0){
        const positions=[];
        for(let index=0;index<arrays.protected.length;index++)if(arrays.protected[index])positions.push(arrays.surface_vertices[index*3],arrays.surface_vertices[index*3+1]+1,arrays.surface_vertices[index*3+2]);
        const pointGeometry=new THREE.BufferGeometry();
        pointGeometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(positions),3));
        const points=new THREE.Points(pointGeometry,new THREE.PointsMaterial({color:TerraView.material.marker,size:Math.max(descriptor.spacing_m,1),sizeAttenuation:true}));
        points.name='protected';group.add(points);
    }
}
function resetCamera(){
    if(!descriptor)return;
    const box=new THREE.Box3().setFromObject(group);
    TerraView.frame(THREE,{box,camera,controls,aspect:wrap.clientWidth/wrap.clientHeight});render();
}
function render(){
    if(!active)return;
    if(!descriptor){
        map.getContext('2d').clearRect(0,0,map.width,map.height);
        renderer?.clear();
        return;
    }
    const three=window.surfaceRenderer.state.view==='3d';
    display.classList.toggle('hidden',!three);map.classList.toggle('hidden',three);
    if(!three){drawMap();TerraView.hud.show(`特殊地形 · ${descriptor.label}`,false);return}
    if(!renderer){
        renderer=TerraView.createRenderer(THREE,display);
        controls=TerraView.configureControls(THREE,new OrbitControls(camera,display));
        controls.addEventListener('change',render);resetCamera();
    }
    const width=wrap.clientWidth,height=wrap.clientHeight;
    renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();
    const resized=renderAspect!==camera.aspect;renderAspect=camera.aspect;
    group.scale.y=Number(element('verticalScale').value);
    TerraView.keepInView(THREE,{group,camera,controls,resized});
    for(const item of group.children)item.visible=!!window.surfaceRenderer.state.layers[item.name];
    renderer.render(scene,camera);
    TerraView.hud.show(`特殊地形 · ${descriptor.label}`,true);
}
function fieldValues(){
    const [rows,cols]=descriptor.chart_shape,values=new Float32Array(rows*cols);
    if(element('specialField').value==='elevation')values.set(elevation);else values.set(arrays.change);
    return values;
}
function drawMap(){
    const [rows,cols]=descriptor.chart_shape,ctx=map.getContext('2d'),field=element('specialField').value;
    map.width=wrap.clientWidth*Math.min(devicePixelRatio,2);map.height=wrap.clientHeight*Math.min(devicePixelRatio,2);
    ctx.fillStyle=TerraTheme.colors.stage;ctx.fillRect(0,0,map.width,map.height);
    const values=fieldValues();
    let maximum=-Infinity,minimum=Infinity;for(const value of values){maximum=Math.max(maximum,value);minimum=Math.min(minimum,value)}
    const change=field!=='elevation',limit=Math.max(Math.abs(minimum),Math.abs(maximum))||1,ramp=change?changeColours(values,limit):null;
    const pixels=document.createElement('canvas');pixels.width=cols;pixels.height=rows;
    const pixelContext=pixels.getContext('2d'),image=pixelContext.createImageData(cols,rows);
    for(let index=0;index<values.length;index++){
        const ratio=(values[index]-minimum)/((maximum-minimum)||1),offset=index*4;
        if(change)image.data.set([ramp[index*3]*255,ramp[index*3+1]*255,ramp[index*3+2]*255,255],offset);
        else image.data.set([...TerraTheme.reliefRgb(ratio),255],offset);
    }
    pixelContext.putImageData(image,0,0);
    const scale=Math.min((map.width-40)/cols,(map.height-40)/rows)*mapView.zoom,width=scale*cols,height=scale*rows;
    const factor=map.width/map.clientWidth,left=(map.width-width)/2+mapView.panX*factor,top=(map.height-height)/2+mapView.panY*factor;
    ctx.imageSmoothingEnabled=false;ctx.drawImage(pixels,left,top,width,height);
}
function makeLayers(){
    const root=element('layers');root.replaceChildren();
    for(const [name,label] of [['surface','保存地表'],['reference','解析参考面'],['change','侵蚀变化 · m'],...(descriptor.protected_cells>0?[['protected','保护区单元']]:[])]){
        const wrap=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=window.surfaceRenderer.state.layers[name]!==false;input.dataset.layer=name;
        input.onchange=()=>{window.surfaceRenderer.state.layers[name]=input.checked;render()};wrap.append(input,label);root.append(wrap);
    }
}
function inspect(){
    const frame=descriptor;
    element('viewTitle').textContent='地形输入 · 特殊地形合成图幅';element('viewSubtitle').textContent=`${frame.label} · ${frame.chart_shape.join('×')} @ ${frame.spacing_m} m`;
    element('specialStatus').textContent=frame.status==='bounded_relaxation_converged'?'有界松弛收敛 · 合成分析图幅':'有界松弛有限步停止 · 合成分析图幅';
    element('stats').textContent=`${frame.chart_shape.join('×')} · ${frame.spacing_m} m · 起伏 ${frame.relief_m[0].toFixed(2)}–${frame.relief_m[1].toFixed(2)} m · 变化 ${frame.change_m[0].toFixed(2)}–${frame.change_m[1].toFixed(2)} m`;
    element('ledger').textContent=JSON.stringify({kind:frame.kind,identity:frame.identity,parent_identity:frame.parent_identity,algorithm:frame.algorithm,spacing_m:frame.spacing_m,chart_shape:frame.chart_shape,relief_m:frame.relief_m,relief_reference_m:frame.relief_reference_m,change_m:frame.change_m,net_change_m3:frame.net_change_m3,protected_cells:frame.protected_cells,target_count:frame.target_count,relaxation_converged:frame.relaxation_converged},null,2);
    element('evidence').textContent=`${frame.semantics}\nbundle ${frame.bundle_sha256}\nmanifest ${frame.manifest_sha256}\nidentity ${frame.identity}\nhydraulic_ready=false · natural_outlet_verified=false · publishable=false`;
    element('sourceRegistry').textContent=`固定清单 ${catalog.manifest_sha256}\n算法 ${catalog.algorithm}`;
}
async function loadFrame(reset=false){
    const kind=formSelect.value;
    const request=++serial;let loaded=false;pending=true;element('exportReview').disabled=true;element('loading').classList.remove('hidden');
    descriptor=null;arrays={};elevation=null;selected=null;clearMeshes();
    for(const name of ['ledger','stats','evidence','selection','selectionTitle'])element(name).textContent='';
    render();
    try{
        const next=await json(`/api/special/frame/${kind}`),nextArrays={};
        for(const [name,record] of Object.entries(next.arrays)){
            const response=await fetch(record.url,{signal:AbortSignal.timeout(60000)});if(!response.ok)throw Error(`读取 ${name} 失败`);
            const bytes=await response.arrayBuffer();if(bytes.byteLength!==record.bytes)throw Error('二进制数组长度不匹配');
            nextArrays[name]=record.dtype==='float32'?new Float32Array(bytes):record.dtype==='uint8'?new Uint8Array(bytes):new Uint32Array(bytes);
        }
        if(request!==serial||!active)return;
        descriptor=next;arrays=nextArrays;selected=null;element('selectionTitle').textContent='尚未选取';element('selection').textContent='在地图或三维表面点选单元';
        const [rows,cols]=next.chart_shape,total=rows*cols;
        if(nextArrays.change.length!==total||nextArrays.surface_vertices.length!==total*3)throw Error('阵列形状与 chart_shape 不符');
        elevation=new Float32Array(total);
        for(let index=0;index<total;index++)elevation[index]=nextArrays.surface_vertices[index*3+1]+next.origin_xyz_m[1];
        clearMeshes();buildMeshes();
        inspect();makeLayers();render();if(reset&&controls)resetCamera();loaded=true;
    }catch(error){if(request===serial&&active){descriptor=null;arrays={};elevation=null;selected=null;clearMeshes();render();throw error}}
    finally{if(request===serial){pending=false;element('exportReview').disabled=!loaded;element('loading').classList.add('hidden')}}
}
function populateForms(){
    formSelect.replaceChildren();
    for(const [kind,entry] of Object.entries(catalog.forms)){const option=document.createElement('option');option.value=kind;option.textContent=`${entry.label} · ${entry.chart_shape.join('×')} @ ${entry.spacing_m} m`;formSelect.append(option)}
}
function reportError(error){if(!active)return;element('error').textContent=error.message;element('error').classList.remove('hidden')}
function selectCell(row,col,point=null){
    const [rows,cols]=descriptor.chart_shape;
    if(row<0||col<0||row>=rows||col>=cols)return;
    const index=row*cols+col;
    element('selectionTitle').textContent=`单元 [${row}, ${col}]`;
    selected={row,col,elevation_m:elevation[index],erosion_change_m:arrays.change[index],origin_xyz_m:descriptor.origin_xyz_m,spacing_m:descriptor.spacing_m,rendered_xyz_m:point};
    element('selection').textContent=JSON.stringify(selected,null,2);
}
formSelect.onchange=()=>loadFrame(true).catch(reportError);
element('specialField').onchange=render;
// The shared view/scale controls drive surfaceRenderer, which knows nothing about this group,
// so the module subscribes to them itself -- same wiring saved-surface.js uses.
for(const id of ['view2d','view3d','verticalScale'])element(id).addEventListener(id==='verticalScale'?'input':'click',render);
new ResizeObserver(render).observe(wrap);
map.addEventListener('click',event=>{
    if(!descriptor||pending||mapDrag?.moved||event.button!==0)return;
    const [rows,cols]=descriptor.chart_shape,scale=Math.min((map.width-40)/cols,(map.height-40)/rows)*mapView.zoom,factor=map.width/map.clientWidth;
    const col=Math.floor((event.offsetX*factor-(map.width-scale*cols)/2-mapView.panX*factor)/scale),row=Math.floor((event.offsetY*factor-(map.height-scale*rows)/2-mapView.panY*factor)/scale);
    selectCell(row,col);
});
let mapDrag=null;
map.addEventListener('contextmenu',event=>event.preventDefault());
map.addEventListener('pointerdown',event=>{
    if(event.button!==0&&event.button!==2)return;
    mapDrag={startX:event.clientX,startY:event.clientY,lastX:event.clientX,lastY:event.clientY,moved:false,active:true};
    map.setPointerCapture(event.pointerId);
});
map.addEventListener('pointermove',event=>{
    if(!mapDrag?.active)return;
    mapDrag.moved ||= Math.hypot(event.clientX-mapDrag.startX,event.clientY-mapDrag.startY)>4;
    mapView.panX+=event.clientX-mapDrag.lastX;mapView.panY+=event.clientY-mapDrag.lastY;
    mapDrag.lastX=event.clientX;mapDrag.lastY=event.clientY;render();
});
for(const name of ['pointerup','pointercancel'])map.addEventListener(name,()=>{if(mapDrag)mapDrag.active=false});
map.addEventListener('wheel',event=>{event.preventDefault();mapView.zoom=Math.max(.2,Math.min(20,mapView.zoom*Math.exp(-event.deltaY*.001)));render()},{passive:false});
let pointerStart=null,pointerMoved=false;
display.addEventListener('pointerdown',event=>{pointerStart=event.button===0?[event.clientX,event.clientY]:null;pointerMoved=false});
display.addEventListener('pointermove',event=>{if(pointerStart&&event.buttons===1)pointerMoved ||= Math.hypot(event.clientX-pointerStart[0],event.clientY-pointerStart[1])>4});
display.addEventListener('click',event=>{
    if(!descriptor||pending||!pointerStart||pointerMoved||event.button!==0)return;
    const rect=display.getBoundingClientRect(),ray=new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2),camera);
    const hit=ray.intersectObjects(group.children.filter(item=>item.isMesh&&item.name==='surface'&&item.visible))[0];
    if(!hit)return;
    const point=hit.point;
    selectCell(Math.floor(point.z/descriptor.spacing_m),Math.floor(point.x/descriptor.spacing_m),[point.x+descriptor.origin_xyz_m[0],point.y/group.scale.y+descriptor.origin_xyz_m[1],point.z+descriptor.origin_xyz_m[2]]);
});
function reviewRecord(){
    if(!descriptor)return null;
    return {schema:'special-surface-review-v1',workspace:'special',caseId:descriptor.kind,source:{manifest_sha256:descriptor.manifest_sha256,bundle_sha256:descriptor.bundle_sha256,identity:descriptor.identity,parent_identity:descriptor.parent_identity,algorithm:descriptor.algorithm},
        chart_shape:descriptor.chart_shape,spacing_m:descriptor.spacing_m,relief_m:descriptor.relief_m,relief_reference_m:descriptor.relief_reference_m,change_m:descriptor.change_m,net_change_m3:descriptor.net_change_m3,protected_cells:descriptor.protected_cells,relaxation_converged:descriptor.relaxation_converged,
        field:element('specialField').value,view:window.surfaceRenderer.state.view,camera:controls?{position:camera.position.toArray(),target:controls.target.toArray(),vertical:group.scale.y}:null,layers:{...window.surfaceRenderer.state.layers},selection:selected,status:descriptor.status,
        semantics:descriptor.semantics,hydraulic_ready:false,natural_outlet_verified:false,publishable:false,self_intersection_verified:false};
}
window.specialSurface=TerraView.register('specialSurface',{async open(){
    active=true;element('surface').classList.add('hidden');const request=++serial;
    mapView.zoom=1;mapView.panX=0;mapView.panY=0;
    for(const name of layerNames())if(window.surfaceRenderer.state.layers[name]===undefined)window.surfaceRenderer.state.layers[name]=name!=='change';
    try{
        catalog=await json('/api/special/catalog');if(!active||request!==serial)return;
        populateForms();await loadFrame(true);
    }catch(error){if(active&&request===serial)throw error}
},close(){active=false;++serial;pending=false;TerraView.hud.hide();element('exportReview').disabled=false;element('loading').classList.add('hidden');map.classList.add('hidden');display.classList.add('hidden');element('surface').classList.remove('hidden');clearMeshes();descriptor=null;arrays={};elevation=null;selected=null},
    render,resetCamera,reviewRecord,isLoading:()=>pending,isActive:()=>active});