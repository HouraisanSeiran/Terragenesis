import * as THREE from 'three';
import {OrbitControls} from './vendor/node_modules/three/examples/jsm/controls/OrbitControls.js';

const element=id=>document.getElementById(id);
const wrap=document.querySelector('.canvas-wrap');
const map=document.createElement('canvas');
const display=document.createElement('canvas');
map.id='savedMap';display.id='savedSurface';
map.className=display.className='saved-canvas hidden';
wrap.prepend(map,display);
let active=false, catalog=null, descriptor=null, arrays={}, serial=0, pending=false, renderer=null, selected=null, renderAspect=null;
const scene=new THREE.Scene();scene.background=new THREE.Color('#101c1d');
const camera=new THREE.PerspectiveCamera(45,1,.1,100000);
const group=new THREE.Group();scene.add(group);
scene.add(new THREE.HemisphereLight(0xe3edf3,0x55503e,2.2));
const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(80,180,-80);scene.add(light);
let controls=null;
const mapView={zoom:1,panX:0,panY:0};
const packageSelect=element('savedPackage'),scenarioSelect=element('savedScenario');

async function json(path){const response=await fetch(path);const body=await response.json();if(!response.ok)throw Error(body.error||response.status);return body}
function clearMeshes(){while(group.children.length){const item=group.children[0];group.remove(item);item.geometry?.dispose();item.material?.dispose()}}
function createMesh(name,color,opacity){
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(arrays[name+'_vertices'],3));
    geometry.setIndex(new THREE.BufferAttribute(arrays[name+'_triangles'],1));
    geometry.computeVertexNormals();
    const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color,side:THREE.DoubleSide,transparent:opacity<1,opacity,roughness:.86,depthWrite:true,polygonOffset:name==='water',polygonOffsetFactor:-1}));
    mesh.name=name;group.add(mesh);
}
function resetCamera(){
    if(!descriptor)return;
    const box=new THREE.Box3().setFromObject(group),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
    const extent=Math.max(size.x,size.y,size.z,1);
    camera.aspect=wrap.clientWidth/wrap.clientHeight;
    const angle=Math.min(camera.fov*Math.PI/360,Math.atan(Math.tan(camera.fov*Math.PI/360)*camera.aspect));
    const distance=box.getBoundingSphere(new THREE.Sphere()).radius/Math.sin(angle)*1.12;
    controls.target.copy(center);camera.near=Math.max(.01,extent/10000);camera.far=extent*20;
    camera.position.copy(center).add(new THREE.Vector3(.85,.9,.85).normalize().multiplyScalar(distance));camera.updateProjectionMatrix();controls.update();render();
}
function render(){
    if(!active||!descriptor)return;
    const three=window.surfaceRenderer.state.view==='3d';
    display.classList.toggle('hidden',!three);map.classList.toggle('hidden',three);
    if(!three){drawMap();return}
    if(!renderer){
        renderer=new THREE.WebGLRenderer({canvas:display,antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
        controls=new OrbitControls(camera,display);controls.rotateSpeed=-1;
        controls.minPolarAngle=.01;controls.maxPolarAngle=Math.PI-.01;
        controls.mouseButtons={LEFT:THREE.MOUSE.ROTATE,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.PAN};
        controls.addEventListener('change',render);resetCamera();
    }
    const width=wrap.clientWidth,height=wrap.clientHeight;
    renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();
    const resized=renderAspect!==camera.aspect;renderAspect=camera.aspect;
    group.scale.y=Number(element('verticalScale').value);
    const radius=new THREE.Box3().setFromObject(group).getBoundingSphere(new THREE.Sphere()).radius;
    const angle=Math.min(camera.fov*Math.PI/360,Math.atan(Math.tan(camera.fov*Math.PI/360)*camera.aspect));
    const direction=camera.position.clone().sub(controls.target),minimum=radius/Math.sin(angle)*1.05;
    if(resized&&direction.length()<minimum)camera.position.copy(controls.target).add(direction.normalize().multiplyScalar(minimum));
    for(const item of group.children)item.visible=item.name.startsWith('domain_')?!!window.surfaceRenderer.state.layers.domains&&item.name==='domain_'+element('savedPartition').value:!!window.surfaceRenderer.state.layers[item.name];
    renderer.render(scene,camera);
}
function drawMap(){
    const [rows,cols]=descriptor.depth_shape,ctx=map.getContext('2d'),field=element('savedField').value;
    map.width=wrap.clientWidth*Math.min(devicePixelRatio,2);map.height=wrap.clientHeight*Math.min(devicePixelRatio,2);
    ctx.fillStyle='#101c1d';ctx.fillRect(0,0,map.width,map.height);
    const pixels=document.createElement('canvas');pixels.width=cols;pixels.height=rows;
    const pixelContext=pixels.getContext('2d'),image=pixelContext.createImageData(cols,rows),values=new Float32Array(rows*cols);
    if(field==='leaf'){
        values.fill(descriptor.spacing_m);
        if(arrays.leaf_row)for(let index=0;index<arrays.leaf_row.length;index++){
            const row=arrays.leaf_row[index],col=arrays.leaf_column[index],size=arrays.leaf_spacing_m[index];
            for(let dz=0;dz<size;dz++)for(let dx=0;dx<size;dx++)values[(row+dz)*cols+col+dx]=size;
        }
    }else if(field==='bed')values.set(arrays.bed_height);
    else values.set(arrays.depth);
    let maximum=0,minimum=Infinity;for(const value of values){maximum=Math.max(maximum,value);minimum=Math.min(minimum,value)}
    for(let index=0;index<values.length;index++){
        const value=values[index],ratio=(value-minimum)/(maximum-minimum||1),offset=index*4;
        const color=field==='leaf'?(value===1?[66,157,129]:value===2?[224,181,78]:[143,148,163]):field==='bed'?[75+ratio*132,93+ratio*101,66+ratio*94]:value>0?[38,102+ratio*105,143+ratio*104]:[30,46,42];
        image.data.set([...color,255],offset);
    }
    pixelContext.putImageData(image,0,0);
    const scale=Math.min((map.width-40)/cols,(map.height-40)/rows)*mapView.zoom,width=scale*cols,height=scale*rows;
    const factor=map.width/map.clientWidth,left=(map.width-width)/2+mapView.panX*factor,top=(map.height-height)/2+mapView.panY*factor;
    ctx.imageSmoothingEnabled=false;ctx.drawImage(pixels,left,top,width,height);
    const partition=descriptor.domain_partitions[element('savedPartition').value];
    if(partition&&window.surfaceRenderer.state.layers.domains){
        ctx.strokeStyle='#f6c968';ctx.lineWidth=2;ctx.beginPath();
        ctx.moveTo(left+partition.column_cut*scale,top);ctx.lineTo(left+partition.column_cut*scale,top+height);
        ctx.moveTo(left,top+partition.row_cut*scale);ctx.lineTo(left+width,top+partition.row_cut*scale);ctx.stroke();
    }
}
function makeLayers(){
    const root=element('layers');root.replaceChildren();
    for(const [name,label] of [['bed','保存床面'],['water','保存水面'],['edges','静态 receiver 骨架'],...(descriptor.package==='amr'?[['domains','域间共享边界']]:[])]){
        const wrap=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=window.surfaceRenderer.state.layers[name];input.dataset.layer=name;
        input.onchange=()=>{window.surfaceRenderer.state.layers[name]=input.checked;render()};wrap.append(input,label);root.append(wrap);
    }
}
function inspect(){
    const frame=descriptor;
    element('viewTitle').textContent=element('reviewProject').value==='mosaic'?'河网算法 · 共享边界与跨精度':'河网算法 · 单域三维';element('viewSubtitle').textContent=`${frame.scenario} · ${frame.time_s} s`;
    element('savedStatus').textContent=frame.status==='diagnostic_uniform_spatial_failure'?'诊断：uniform 空间深差未通过':'有限工程保存链已验收';
    element('stats').textContent=`${frame.depth_shape.join('×')} · ${frame.spacing_m} m · ${frame.wet_cells} 湿格 · ${frame.volume_m3.toFixed(3)} m³`;
    element('ledger').textContent=JSON.stringify({time_s:frame.time_s,volume_m3:frame.volume_m3,leaf_counts:frame.leaf_counts,columns:['supplied_m3','boundary_input_m3','boundary_output_m3','storage_m3','residual_m3'],ledger:frame.ledger},null,2);
    element('evidence').textContent=`${frame.representation}\nmanifest ${frame.manifest_sha256}\nframe ${frame.identity}\n天然海口未认证 · hydraulic_ready=false · publishable=false`;
    element('sourceRegistry').textContent=`阶段验收 ${catalog.acceptance_sha256}\n保存包 ${frame.manifest_sha256}`;
}
async function loadFrame(index,reset=false){
    const packageName=packageSelect.value,scenario=scenarioSelect.value;
    const times=catalog.packages[packageName].scenarios[scenario].times_s;
    index=Math.max(0,Math.min(times.length-1,index));
    const request=++serial;let loaded=false;pending=true;element('exportReview').disabled=true;element('loading').classList.remove('hidden');
    try{
        const next=await json(`/api/saved/frame/${packageName}/${scenario}/${index}`),nextArrays={};
        for(const [name,record] of Object.entries(next.arrays)){
            const response=await fetch(record.url);if(!response.ok)throw Error(`读取 ${name} 失败`);
            const bytes=await response.arrayBuffer();if(bytes.byteLength!==record.bytes)throw Error('二进制数组长度不匹配');
            nextArrays[name]=record.dtype==='float32'?new Float32Array(bytes):new Uint32Array(bytes);
        }
        if(request!==serial||!active)return;
        descriptor=next;arrays=nextArrays;selected=null;element('selectionTitle').textContent='尚未选取';element('selection').textContent='';clearMeshes();createMesh('bed',0x9eac8b,1);createMesh('water',0x2998c5,.86);
        const positions=new Float32Array(arrays.edges.length*3);for(let index=0;index<arrays.edges.length;index++)positions.set(arrays.nodes.subarray(arrays.edges[index]*3,arrays.edges[index]*3+3),index*3);
        const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
        const graph=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:0xf6c968,depthTest:false}));graph.name='edges';group.add(graph);
        for(const name of ['domain_central','domain_mixed'])if(arrays[name]){
            const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(arrays[name],3));
            const lines=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:0xf4bd55,depthTest:false}));lines.name=name;group.add(lines);
        }
        element('savedPartition').disabled=next.package!=='amr';
        window.surfaceRenderer.state.time=index;element('timeRange').max=times.length-1;element('timeRange').value=index;
        element('timeStep').textContent=`${index} / ${times.length-1}`;element('timeSeconds').textContent=`t = ${times[index]} s`;
        inspect();makeLayers();render();if(reset&&controls)resetCamera();loaded=true;
    }catch(error){if(request===serial&&active)throw error}
    finally{if(request===serial){pending=false;element('exportReview').disabled=!loaded;element('loading').classList.add('hidden')}}
}
async function selectPackage(){
    scenarioSelect.replaceChildren();
    for(const name of Object.keys(catalog.packages[packageSelect.value].scenarios)){const option=document.createElement('option');option.value=name;option.textContent=name;scenarioSelect.append(option)}
    if(packageSelect.value==='amr')scenarioSelect.value='tailwater-rise-root4';
    await loadFrame(0,true);
}
packageSelect.onchange=()=>selectPackage().catch(reportError);
scenarioSelect.onchange=()=>loadFrame(0,true).catch(reportError);
element('savedField').onchange=render;
element('savedPartition').onchange=render;
for(const id of ['view2d','view3d','verticalScale'])element(id).addEventListener(id==='verticalScale'?'input':'click',render);
element('reset').addEventListener('click',()=>{if(active){mapView.zoom=1;mapView.panX=0;mapView.panY=0;if(controls)resetCamera();render()}});
new ResizeObserver(render).observe(wrap);
function reportError(error){if(!active)return;element('error').textContent=error.message;element('error').classList.remove('hidden')}
function selectCell(row,col,point=null){
    const [rows,cols]=descriptor.depth_shape;
    if(row<0||col<0||row>=rows||col>=cols)return;
    element('selectionTitle').textContent=`canonical [${row}, ${col}]`;
    selected={row,col,time_s:descriptor.time_s,mean_depth_m:arrays.depth[row*cols+col],bed_height_m:arrays.bed_height[row*cols+col],origin_xyz_m:descriptor.origin_xyz_m,spacing_m:descriptor.spacing_m,rendered_xyz_m:point};
    element('selection').textContent=JSON.stringify(selected,null,2);
}
map.addEventListener('click',event=>{
    if(!descriptor||pending||mapDrag?.moved||event.button!==0)return;
    const [rows,cols]=descriptor.depth_shape,scale=Math.min((map.width-40)/cols,(map.height-40)/rows)*mapView.zoom,factor=map.width/map.clientWidth;
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
    const hit=ray.intersectObjects(group.children.filter(item=>item.isMesh&&item.visible))[0];
    if(!hit)return;
    const point=hit.point;
    selectCell(Math.floor(point.z/descriptor.spacing_m),Math.floor(point.x/descriptor.spacing_m),[point.x+descriptor.origin_xyz_m[0],point.y/group.scale.y+descriptor.origin_xyz_m[1],point.z+descriptor.origin_xyz_m[2]]);
});
function reviewRecord(){return descriptor?{schema:'saved-surface-review-v1',workspace:'saved',caseId:`${descriptor.package}-${descriptor.scenario}`,source:{manifest_sha256:descriptor.manifest_sha256,frame_identity:descriptor.identity,bed_identity:descriptor.bed_identity,acceptance_sha256:catalog.acceptance_sha256},timeIndex:descriptor.index,timeSeconds:descriptor.time_s,view:window.surfaceRenderer.state.view,camera:controls?{position:camera.position.toArray(),target:controls.target.toArray(),vertical:group.scale.y}:null,layers:{...window.surfaceRenderer.state.layers},selection:selected,status:descriptor.status,hydraulic_ready:false,natural_outlet_verified:false,publishable:false}:null}
window.savedSurface={async open({mosaic=false}={}){
    active=true;element('surface').classList.add('hidden');const request=++serial;
    mapView.zoom=1;mapView.panX=0;mapView.panY=0;
    if(mosaic){packageSelect.value='amr';element('savedPartition').value='mixed';element('savedField').value='leaf';window.surfaceRenderer.state.layers.domains=true}
    try{catalog=await json('/api/saved/catalog');if(active&&request===serial)await selectPackage()}
    catch(error){if(active&&request===serial)throw error}
},close(){active=false;++serial;pending=false;element('exportReview').disabled=false;element('loading').classList.add('hidden');element('chartSection').classList.remove('hidden');map.classList.add('hidden');display.classList.add('hidden');element('surface').classList.remove('hidden');clearMeshes();descriptor=null;arrays={};selected=null},async setTime(index){if(!pending)await loadFrame(index)},render,reviewRecord,isLoading:()=>pending};
window.surfaceReview.ready.then(()=>{
    const requested=new URLSearchParams(location.search).get('workspace')||'saved';
    const known=Object.values(window.surfaceReview.categories).some(category=>category.projects.some(project=>project.id===requested));
    window.surfaceReview.navigate(known?requested:'saved');
});
