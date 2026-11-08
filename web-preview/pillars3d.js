import * as THREE from 'three';
import {OrbitControls} from './vendor/node_modules/three/examples/jsm/controls/OrbitControls.js';

// Read-only viewer for the pinned pillar-field true-3D solid. It draws the stored closed
// MESH64 mesh -- and, for comparison, the un-carved prisms the same joint cells produce --
// and nothing else: no hydrology is re-run, no Boolean is re-evaluated and no certificate
// is implied. The six capability flags ride along in the descriptor so an export cannot
// look like a result.

const element=id=>document.getElementById(id);
const wrap=document.querySelector('.canvas-wrap');
const map=document.createElement('canvas');
const display=document.createElement('canvas');
map.id='pillarsMap';display.id='pillarsSolid';
map.className=display.className='special-canvas hidden';
wrap.prepend(map,display);
let active=false,catalog=null,descriptor=null,arrays={},serial=0,pending=false,renderer=null,selected=null,renderAspect=null;
const scene=TerraView.createScene(THREE);
const camera=new THREE.PerspectiveCamera(45,1,.1,100000);
const group=new THREE.Group();scene.add(group);
let controls=null;
const mapView={zoom:1,panX:0,panY:0};
const shadeSelect=element('pillars3dShade');
const LOW=[0.35,0.71,0.66],HIGH=[0.91,0.78,0.53],DEEP=[0.81,0.42,0.29];

async function json(path){const response=await fetch(path,{signal:AbortSignal.timeout(60000)});const body=await response.json();if(!response.ok)throw Error(body.error||response.status);return body}
function clearMeshes(){while(group.children.length){const item=group.children[0];group.remove(item);item.geometry?.dispose();item.material?.dispose()}}
function layerNames(){return ['carved','plain','footprint']}
function mix(first,second,weight){return first.map((value,index)=>value+(second[index]-value)*weight)}
function coloursForFootprints(){
    const foot=descriptor.pillar_footprints,shade=shadeSelect.value;
    const heights=foot.map(item=>item.height_m),scales=foot.map(item=>item.carve_scale);
    const low=Math.min(...heights),high=Math.max(...heights);
    const scaleLow=Math.min(...scales),scaleHigh=Math.max(...scales);
    return foot.map((item,index)=>{
        if(shade==='carve'){
            // A pillar that folded at a shallower depth is the one the geometry could not carve
            // fully: that reads as the hot end of the ramp.
            const span=(scaleHigh-scaleLow)||1;
            return mix(DEEP,LOW,Math.max(0,Math.min(1,(scaleHigh-item.carve_scale)/span)));
        }
        const span=(high-low)||1;
        return mix(LOW,HIGH,Math.max(0,Math.min(1,(item.height_m-low)/span)));
    });
}
function ringSegments(ring,y){
    const positions=[];
    for(let index=0;index<ring.length;index++){
        const next=(index+1)%ring.length;
        positions.push(ring[index][0],y,ring[index][1],ring[next][0],y,ring[next][1]);
    }
    return positions;
}
function footprintGeometry(){
    const positions=[],colours=[];
    const palette=coloursForFootprints();
    descriptor.pillar_footprints.forEach((item,index)=>{
        const y=item.height_m+2;
        const segments=ringSegments(item.ring_xz_m,y);
        for(let channel=0;channel<segments.length/3;channel++)colours.push(...TerraView.linearColor(palette[index].map(v=>v*255)));
        positions.push(...segments);
    });
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(positions),3));
    geometry.setAttribute('color',new THREE.BufferAttribute(new Float32Array(colours),3));
    return geometry;
}
function buildMeshes(){
    const carved=new THREE.BufferGeometry();
    carved.setAttribute('position',new THREE.BufferAttribute(arrays.solid_vertices,3));
    carved.setIndex(new THREE.BufferAttribute(arrays.solid_triangles,1));
    carved.computeVertexNormals();
    const solid=new THREE.Mesh(carved,new THREE.MeshStandardMaterial({color:TerraView.material.solid,side:THREE.DoubleSide,roughness:.92,metalness:0}));
    solid.name='carved';group.add(solid);
    const plain=new THREE.BufferGeometry();
    plain.setAttribute('position',new THREE.BufferAttribute(arrays.plain_vertices,3));
    plain.setIndex(new THREE.BufferAttribute(arrays.plain_triangles,1));
    const prisms=new THREE.Mesh(plain,new THREE.MeshStandardMaterial({color:TerraView.material.reference,side:THREE.DoubleSide,wireframe:true,transparent:true,opacity:.3,metalness:0}));
    prisms.name='plain';group.add(prisms);
    const ring=new THREE.LineSegments(footprintGeometry(),new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.95}));
    ring.name='footprint';group.add(ring);
}
function resetCamera(){
    if(!descriptor)return;
    const box=new THREE.Box3().setFromObject(group);
    TerraView.frame(THREE,{box,camera,controls,aspect:wrap.clientWidth/wrap.clientHeight,direction:[.8,.85,.95]});render();
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
    if(!three){drawMap();TerraView.hud.show('石柱群 · 真三维实体',false);return}
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
    for(const item of group.children){
        // A LineSegments has no `isMesh`, so the layer loop must not assume meshes only.
        item.visible=!!window.surfaceRenderer.state.layers[item.name];
    }
    renderer.render(scene,camera);
    TerraView.hud.show('石柱群 · 真三维实体',true);
}
function planBounds(){
    const points=[];
    for(const item of descriptor.pillar_footprints)points.push(...item.ring_xz_m);
    for(const point of descriptor.plateau.ring_xz_m)points.push(point);
    const xs=points.map(point=>point[0]),zs=points.map(point=>point[1]);
    return {minX:Math.min(...xs),maxX:Math.max(...xs),minZ:Math.min(...zs),maxZ:Math.max(...zs)};
}
function drawMap(){
    const bounds=planBounds(),ctx=map.getContext('2d');
    map.width=wrap.clientWidth*Math.min(devicePixelRatio,2);map.height=wrap.clientHeight*Math.min(devicePixelRatio,2);
    ctx.fillStyle=TerraTheme.colors.stage;ctx.fillRect(0,0,map.width,map.height);
    const spanX=(bounds.maxX-bounds.minX)||1,spanZ=(bounds.maxZ-bounds.minZ)||1;
    const scale=Math.min((map.width-50)/spanX,(map.height-50)/spanZ)*mapView.zoom;
    const factor=map.width/map.clientWidth;
    const left=(map.width-scale*spanX)/2+mapView.panX*factor,top=(map.height-scale*spanZ)/2+mapView.panY*factor;
    const project=point=>[left+(point[0]-bounds.minX)*scale,top+(point[1]-bounds.minZ)*scale];
    const palette=coloursForFootprints();
    ctx.beginPath();
    descriptor.plateau.ring_xz_m.forEach((point,index)=>{const [x,y]=project(point);index?ctx.lineTo(x,y):ctx.moveTo(x,y)});
    ctx.closePath();ctx.fillStyle='rgba(44,37,27,.88)';ctx.fill();
    ctx.strokeStyle='rgba(179,154,98,.75)';ctx.lineWidth=1;ctx.stroke();
    const carve=shadeSelect.value==='carve';
    descriptor.pillar_footprints.forEach((item,index)=>{
        ctx.beginPath();
        item.ring_xz_m.forEach((point,ordinal)=>{const [x,y]=project(point);ordinal?ctx.lineTo(x,y):ctx.moveTo(x,y)});
        ctx.closePath();
        const colour=palette[index].map(value=>Math.round(value*255));
        ctx.fillStyle=`rgba(${colour[0]},${colour[1]},${colour[2]},${carve&&item.carve_scale<1?.95:.85})`;
        ctx.fill();
        ctx.strokeStyle=`rgba(${colour[0]},${colour[1]},${colour[2]},1)`;ctx.lineWidth=selected&&selected.pillar_index===index?2.4:1.1;ctx.stroke();
        const [cx,cy]=project(item.centre_xz_m);
        ctx.fillStyle='#1a1409';ctx.font=`${Math.round(9*Math.min(devicePixelRatio,2))}px ui-monospace, monospace`;
        ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(index),cx,cy);
    });
    if(selected){
        const item=descriptor.pillar_footprints[selected.pillar_index];
        const [cx,cy]=project(item.centre_xz_m);
        ctx.strokeStyle='#e3a63c';ctx.lineWidth=2;ctx.beginPath();ctx.arc(cx,cy,scale*8,0,Math.PI*2);ctx.stroke();
    }
    ctx.fillStyle='#cfc3a8';ctx.font=`${Math.round(10*Math.min(devicePixelRatio,2))}px ui-monospace, monospace`;
    ctx.textAlign='left';ctx.textBaseline='bottom';
    ctx.fillText(`平面 · 节理胞轮廓 ${descriptor.pillar_count} 柱 · ${carve?'着色=雕刻深度 step':'着色=柱高'}`,12,map.height-10);
}
function makeLayers(){
    const root=element('layers');root.replaceChildren();
    for(const [name,label] of [['carved','雕刻后闭合实体'],['plain','未雕刻棱柱（对照）'],['footprint','柱顶节理胞轮廓']]){
        const wrapElement=document.createElement('label'),input=document.createElement('input');input.type='checkbox';
        input.checked=window.surfaceRenderer.state.layers[name]!==false;input.dataset.layer=name;
        input.onchange=()=>{window.surfaceRenderer.state.layers[name]=input.checked;render()};
        wrapElement.append(input,label);root.append(wrapElement);
    }
}
function inspect(){
    const frame=descriptor;
    element('viewTitle').textContent='地形输入 · 石柱群真三维闭合实体';
    element('viewSubtitle').textContent=`${frame.pillar_count} 柱 · ${frame.vertices} 顶点 / ${frame.triangles} 三角 · 闭合单连通`;
    element('pillars3dStatus').textContent=frame.every_section_simple
        ?'逐水平截面均简单 · 合成分析几何 · 非水力成果'
        :'存在非简单水平截面 · 合成分析几何 · 非水力成果';
    element('stats').textContent=`${frame.pillar_count} 柱 · 柱高 ${frame.height_m[0].toFixed(1)}–${frame.height_m[1].toFixed(1)} m · 体积 ${frame.assembled_volume_m3.toFixed(0)} m³ · 满深度 ${frame.full_depth_pillars}/${frame.pillar_count} · components ${frame.components}`;
    element('ledger').textContent=JSON.stringify({caseId:frame.caseId,identity:frame.identity,algorithm:frame.algorithm,report_sha256:frame.report_sha256,status:frame.status,pillar_count:frame.pillar_count,height_m:frame.height_m,carve_scales:frame.carve_scales,full_depth_pillars:frame.full_depth_pillars,assembled_volume_m3:frame.assembled_volume_m3,plateau_volume_m3:frame.plateau_volume_m3,volume_account:frame.volume_account,components:frame.components,every_section_simple:frame.every_section_simple,witnesses:frame.witnesses},null,2);
    element('evidence').textContent=`${frame.semantics}\nreport ${frame.report_sha256}\ncarved ${frame.carved_sha256}\nplain ${frame.plain_sha256}\nidentity ${frame.identity}\nsupersedes ${frame.supersedes.superseded_schema}\nhydraulic_ready=false · natural_outlet_verified=false · publishable=false · self_intersection_verified=false`;
    element('sourceRegistry').textContent=`固定报告 ${frame.report_sha256.slice(0,16)}…\n算法 ${frame.algorithm}`;
}
function selectPillar(index,point=null){
    const item=descriptor.pillar_footprints[index];
    if(!item)return;
    element('selectionTitle').textContent=`柱 ${index} · ${item.role}`;
    selected={pillar_index:index,role:item.role,height_m:item.height_m,carve_scale:item.carve_scale,ring_area_m2:item.ring_area_m2,signed_volume_m3:item.signed_volume_m3,centre_xz_m:item.centre_xz_m,origin_xyz_m:descriptor.origin_xyz_m,rendered_xyz_m:point};
    element('selection').textContent=JSON.stringify(selected,null,2);
    render();
}
function pillarAtXZ(x,z){
    let best=null;
    descriptor.pillar_footprints.forEach((item,index)=>{
        let inside=false;
        const ring=item.ring_xz_m;
        for(let first=0,second=ring.length-1;first<ring.length;second=first++){
            const [xi,zi]=ring[first],[xj,zj]=ring[second];
            if((zi>z)!==(zj>z)&&x<(xj-xi)*(z-zi)/(zj-zi)+xi)inside=!inside;
        }
        const distance=Math.hypot(x-item.centre_xz_m[0],z-item.centre_xz_m[1]);
        if(inside&&(!best||distance<best.distance))best={index,distance};
        else if(!best)best={index,distance,inside:false};
        else if(!best.inside&&distance<best.distance)best={index,distance,inside:false};
    });
    return best?best.index:null;
}
async function loadFrame(){
    const request=++serial;let loaded=false;pending=true;element('exportReview').disabled=true;element('loading').classList.remove('hidden');
    descriptor=null;arrays={};selected=null;clearMeshes();
    for(const name of ['ledger','stats','evidence','selection','selectionTitle'])element(name).textContent='';
    render();
    try{
        const next=await json('/api/pillars3d/frame'),nextArrays={};
        for(const [name,record] of Object.entries(next.arrays)){
            const response=await fetch(record.url,{signal:AbortSignal.timeout(60000)});if(!response.ok)throw Error(`读取 ${name} 失败`);
            const bytes=await response.arrayBuffer();if(bytes.byteLength!==record.bytes)throw Error('二进制数组长度不匹配');
            nextArrays[name]=record.dtype==='float32'?new Float32Array(bytes):record.dtype==='uint8'?new Uint8Array(bytes):new Uint32Array(bytes);
        }
        if(request!==serial||!active)return;
        descriptor=next;arrays=nextArrays;selected=null;
        element('selectionTitle').textContent='尚未选取';element('selection').textContent='在平面点选柱，或在三维实体上点选';
        if(!nextArrays.solid_vertices||!nextArrays.solid_triangles)throw Error('闭合实体网格缺失');
        if(nextArrays.solid_vertices.length!==next.vertices*3||nextArrays.solid_triangles.length!==next.triangles*3)throw Error('网格阵列与摘要计数不符');
        clearMeshes();buildMeshes();
        inspect();makeLayers();render();if(controls)resetCamera();loaded=true;
    }catch(error){if(request===serial&&active){descriptor=null;arrays={};selected=null;clearMeshes();render();throw error}}
    finally{if(request===serial){pending=false;element('exportReview').disabled=!loaded;element('loading').classList.add('hidden')}}
}
function reportError(error){if(!active)return;element('error').textContent=error.message;element('error').classList.remove('hidden')}
function reviewRecord(){
    if(!descriptor)return null;
    return {schema:'special-pillars3d-review-v1',workspace:'pillars3d',caseId:descriptor.caseId,
        source:{report_sha256:descriptor.report_sha256,carved_sha256:descriptor.carved_sha256,plain_sha256:descriptor.plain_sha256,identity:descriptor.identity,algorithm:descriptor.algorithm,report_schema:descriptor.report_schema},
        pillar_count:descriptor.pillar_count,height_m:descriptor.height_m,carve_scales:descriptor.carve_scales,full_depth_pillars:descriptor.full_depth_pillars,
        assembled_volume_m3:descriptor.assembled_volume_m3,plateau_volume_m3:descriptor.plateau_volume_m3,volume_account:descriptor.volume_account,
        components:descriptor.components,every_section_simple:descriptor.every_section_simple,witnesses:descriptor.witnesses,supersedes:descriptor.supersedes,
        shade:shadeSelect.value,view:window.surfaceRenderer.state.view,
        camera:controls?{position:camera.position.toArray(),target:controls.target.toArray(),vertical:group.scale.y}:null,
        layers:{...window.surfaceRenderer.state.layers},selection:selected,status:descriptor.status,semantics:descriptor.semantics,
        hydraulic_ready:false,natural_outlet_verified:false,publishable:false,self_intersection_verified:false};
}
shadeSelect.onchange=render;
// The shared view/scale controls drive surfaceRenderer, which knows nothing about this group,
// so the module subscribes to them itself -- same wiring saved-surface.js uses.
for(const id of ['view2d','view3d','verticalScale'])element(id).addEventListener(id==='verticalScale'?'input':'click',render);
new ResizeObserver(render).observe(wrap);
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
map.addEventListener('click',event=>{
    if(!descriptor||pending||mapDrag?.moved||event.button!==0)return;
    const bounds=planBounds(),spanX=(bounds.maxX-bounds.minX)||1,spanZ=(bounds.maxZ-bounds.minZ)||1;
    const scale=Math.min((map.width-50)/spanX,(map.height-50)/spanZ)*mapView.zoom,factor=map.width/map.clientWidth;
    const left=(map.width-scale*spanX)/2+mapView.panX*factor,top=(map.height-scale*spanZ)/2+mapView.panY*factor;
    const x=bounds.minX+(event.offsetX*factor-left)/scale,z=bounds.minZ+(event.offsetY*factor-top)/scale;
    const index=pillarAtXZ(x,z);if(index!==null)selectPillar(index);
});
let pointerStart=null,pointerMoved=false;
display.addEventListener('pointerdown',event=>{pointerStart=event.button===0?[event.clientX,event.clientY]:null;pointerMoved=false});
display.addEventListener('pointermove',event=>{if(pointerStart&&event.buttons===1)pointerMoved ||= Math.hypot(event.clientX-pointerStart[0],event.clientY-pointerStart[1])>4});
display.addEventListener('click',event=>{
    if(!descriptor||pending||!pointerStart||pointerMoved||event.button!==0)return;
    const rect=display.getBoundingClientRect(),ray=new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2),camera);
    const target=group.children.find(item=>item.isMesh&&item.name==='carved'&&item.visible);
    if(!target)return;
    const hit=ray.intersectObject(target)[0];
    if(!hit)return;
    const point=hit.point;
    const index=pillarAtXZ(point.x,point.z);
    if(index!==null)selectPillar(index,[point.x+descriptor.origin_xyz_m[0],point.y/group.scale.y+descriptor.origin_xyz_m[1],point.z+descriptor.origin_xyz_m[2]]);
});
window.pillars3d=TerraView.register('pillars3d',{async open(){
    active=true;element('surface').classList.add('hidden');const request=++serial;
    mapView.zoom=1;mapView.panX=0;mapView.panY=0;
    for(const name of layerNames())if(window.surfaceRenderer.state.layers[name]===undefined)window.surfaceRenderer.state.layers[name]=name!=='plain';
    try{
        catalog=await json('/api/pillars3d/catalog');if(!active||request!==serial)return;
        await loadFrame();
    }catch(error){if(active&&request===serial)throw error}
},close(){active=false;++serial;pending=false;TerraView.hud.hide();element('exportReview').disabled=false;element('loading').classList.add('hidden');map.classList.add('hidden');display.classList.add('hidden');element('surface').classList.remove('hidden');clearMeshes();descriptor=null;arrays={};selected=null},
    render,resetCamera,reviewRecord,isLoading:()=>pending,isActive:()=>active});
