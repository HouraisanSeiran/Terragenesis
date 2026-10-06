import * as THREE from 'three';
import {OrbitControls} from './vendor/node_modules/three/examples/jsm/controls/OrbitControls.js';

const element=id=>document.getElementById(id);
const wrap=document.querySelector('.canvas-wrap');
const canvas=document.createElement('canvas');
canvas.id='faultSurface';canvas.className='saved-canvas hidden';
canvas.setAttribute('aria-label','断层局部真实三角网格');wrap.prepend(canvas);
const labels=document.createElement('div');labels.className='fault-labels hidden';
for(const text of ['平移前 · 已施加 VDM','平移后']){const label=document.createElement('span');label.textContent=text;labels.append(label)}
wrap.append(labels);
const scene=new THREE.Scene();scene.background=new THREE.Color('#101c1d');
scene.add(new THREE.HemisphereLight(0xe3edf3,0x55503e,2.2));
const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(80,180,-80);scene.add(light);
const camera=new THREE.PerspectiveCamera(45,1,.01,100000);
const mapCamera=new THREE.OrthographicCamera(-1,1,1,-1,.01,100000);
mapCamera.up.set(0,0,-1);
const before=new THREE.Group(),after=new THREE.Group();scene.add(before,after);
const layers={faultSeam:false,faultMoving:false,faultProtected:false};
let active=false,pending=false,payload=null,recipe=null,selected=null,origin=[0,0,0];
let renderer=null,controls=null,mapControls=null,lastView=null,lastAspect=null,pointerStart=null;
const mode=()=>element('faultMode').value;
const three=()=>window.surfaceRenderer.state.view==='3d';
const currentCamera=()=>three()?camera:mapCamera;
const currentControls=()=>three()?controls:mapControls;

function clearGeometry(){
    for(const group of [before,after]){
        while(group.children.length){const item=group.children[0];group.remove(item);item.geometry.dispose();item.material.dispose()}
    }
}
function clear(){
    payload=null;recipe=null;selected=null;clearGeometry();
    element('stats').textContent='';element('ledger').textContent='';element('evidence').textContent='';
    labels.classList.add('hidden');if(active&&renderer)renderer.clear();
}
function ensureRenderer(){
    if(renderer)return;
    renderer=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    controls=new OrbitControls(camera,canvas);mapControls=new OrbitControls(mapCamera,canvas);
    for(const orbit of [controls,mapControls]){
        orbit.rotateSpeed=-1;orbit.minPolarAngle=.01;orbit.maxPolarAngle=Math.PI-.01;
        orbit.mouseButtons={LEFT:THREE.MOUSE.ROTATE,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.PAN};
        orbit.addEventListener('change',render);
    }
    mapControls.enableRotate=false;mapControls.mouseButtons.LEFT=THREE.MOUSE.PAN;
    mapControls.enabled=false;
}
function validate(next){
    if(!['fault-case-v1','fault-preview-v1'].includes(next.schema)||!next.identity)throw Error('断层 schema／identity 无效');
    const mesh=next.mesh;
    if(!mesh?.vertices?.length||!mesh.triangles?.length)throw Error('断层真实网格为空');
    const count=mesh.vertices.length;
    for(const key of ['vertices','reference','displacement']){
        if(mesh[key]?.length!==count||mesh[key].some(point=>!Array.isArray(point)||point.length!==3||!point.every(Number.isFinite)))throw Error(`断层 ${key} XYZ 无效`);
    }
    for(const key of ['protected','vertexSide','transitionWeight','sourceVertexIndex']){
        if(mesh[key]?.length!==count)throw Error(`断层 ${key} 长度不匹配`);
    }
    if(mesh.sourceTriangleIndex?.length!==mesh.triangles.length)throw Error('断层 sourceTriangleIndex 长度不匹配');
    const validIndex=index=>Number.isInteger(index)&&index>=0&&index<count;
    if(mesh.triangles.some(face=>face.length!==3||!face.every(validIndex)))throw Error('断层三角拓扑无效');
    if(!Array.isArray(mesh.seamEdges)||mesh.seamEdges.some(edge=>edge.length!==2||!edge.every(validIndex)))throw Error('断层 seamEdges 无效');
    if(!next.defaults?.plane_origin_xz_m)throw Error('断层 defaults 缺失');
}
function positions(points){return new Float32Array(points.flatMap(point=>point.map((value,axis)=>value-origin[axis])))}
function build(group,points){
    const mesh=payload.mesh,geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(positions(points),3));
    geometry.setIndex(mesh.triangles.flat());geometry.computeVertexNormals();
    const surface=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:0xffffff,vertexColors:true,side:THREE.DoubleSide,roughness:.86}));
    surface.name='surface';group.add(surface);
    const seamGeometry=new THREE.BufferGeometry();
    seamGeometry.setAttribute('position',new THREE.BufferAttribute(positions(mesh.seamEdges.flatMap(edge=>edge.map(index=>points[index]))),3));
    const seam=new THREE.LineSegments(seamGeometry,new THREE.LineBasicMaterial({color:0xe8b75c,depthTest:false}));
    seam.name='faultSeam';seam.renderOrder=2;group.add(seam);
}
function updateColors(){
    if(!payload)return;
    const mesh=payload.mesh;
    for(const group of [before,after]){
        const colors=new Float32Array(mesh.vertices.length*3);
        for(let index=0;index<mesh.vertices.length;index++){
            const moving=recipe.moving_side==='positive'?mesh.vertexSide[index]>0:mesh.vertexSide[index]<0;
            const color=new THREE.Color(layers.faultProtected&&mesh.protected[index]?0xe8b75c:layers.faultMoving&&moving?0x72b6c9:0x9eac8b);
            color.toArray(colors,index*3);
        }
        group.children[0].geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
    }
}
function makeLayers(){
    const root=element('layers');root.replaceChildren();
    for(const [name,label] of [['faultSeam','切缝边'],['faultMoving','移动侧'],['faultProtected','保护顶点']]){
        const row=document.createElement('label'),input=document.createElement('input');
        input.type='checkbox';input.dataset.layer=name;input.checked=layers[name];
        input.onchange=()=>{layers[name]=input.checked;updateColors();render()};
        row.append(input,label);root.append(row);
    }
}
function localBox(){
    const box=new THREE.Box3();
    for(const group of [before,after])box.union(new THREE.Box3().setFromObject(group));
    return box;
}
function aspect(){return Math.max(1,wrap.clientWidth)/(Math.max(1,wrap.clientHeight)*(mode()==='compare'?2:1))}
function resetCamera(){
    if(!payload||!renderer)return;
    const box=localBox(),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
    const extent=Math.max(size.x,size.y,size.z,1),ratio=aspect();
    camera.aspect=ratio;
    const angle=Math.min(camera.fov*Math.PI/360,Math.atan(Math.tan(camera.fov*Math.PI/360)*ratio));
    const distance=box.getBoundingSphere(new THREE.Sphere()).radius/Math.sin(angle)*1.12;
    controls.target.copy(center);camera.near=Math.max(.01,extent/10000);camera.far=Math.max(extent*20,distance*4);
    camera.position.copy(center).add(new THREE.Vector3(.85,.9,.85).normalize().multiplyScalar(distance));camera.updateProjectionMatrix();
    const halfHeight=Math.max(size.z/2,size.x/(2*ratio),1)*1.12;
    mapCamera.left=-halfHeight*ratio;mapCamera.right=halfHeight*ratio;mapCamera.top=halfHeight;mapCamera.bottom=-halfHeight;
    mapCamera.near=.01;mapCamera.far=extent*20;mapCamera.zoom=1;
    mapControls.target.copy(center);mapCamera.position.copy(center).add(new THREE.Vector3(0,extent*4,0));mapCamera.updateProjectionMatrix();
    controls.update();mapControls.update();lastAspect=ratio;render();
}
function render(){
    if(!active)return;
    canvas.classList.remove('hidden');element('surface').classList.add('hidden');
    if(!renderer||!payload)return;
    const width=Math.max(1,wrap.clientWidth),height=Math.max(1,wrap.clientHeight),ratio=aspect();
    controls.enabled=three();mapControls.enabled=!three();
    renderer.setSize(width,height,false);
    for(const group of [before,after]){
        group.scale.y=Number(element('verticalScale').value);
        group.children[1].visible=layers.faultSeam;
    }
    camera.aspect=ratio;camera.updateProjectionMatrix();
    const halfHeight=mapCamera.top;mapCamera.left=-halfHeight*ratio;mapCamera.right=halfHeight*ratio;mapCamera.updateProjectionMatrix();
    if(lastView!==three()||lastAspect!==ratio){lastView=three();lastAspect=ratio;resetCamera();return}
    const compare=mode()==='compare';labels.classList.toggle('hidden',!compare);
    renderer.setScissorTest(true);
    const panes=compare?[before,after]:[mode()==='before'?before:after];
    panes.forEach((group,index)=>{
        before.visible=group===before;after.visible=group===after;
        const left=compare?Math.floor(index*width/2):0,paneWidth=compare?(index===0?Math.floor(width/2):width-Math.floor(width/2)):width;
        renderer.setViewport(left,0,paneWidth,height);renderer.setScissor(left,0,paneWidth,height);renderer.render(scene,currentCamera());
    });
    renderer.setScissorTest(false);
}
function load(next,appliedRecipe){
    validate(next);clear();ensureRenderer();payload=next;recipe=structuredClone(appliedRecipe);
    const box=new THREE.Box3();
    for(const point of [...next.mesh.vertices,...next.mesh.reference])box.expandByPoint(new THREE.Vector3(...point));
    origin=box.getCenter(new THREE.Vector3()).toArray();
    build(before,next.mesh.reference);build(after,next.mesh.vertices);updateColors();makeLayers();
    const selection=next.selection;
    element('viewSubtitle').textContent=`${next.schema==='fault-case-v1'?'保存断层':'显式预览'} · 局部 row ${selection.row_start}:${selection.row_stop} / col ${selection.column_start}:${selection.column_stop}`;
    element('stats').textContent=`${next.mesh.vertices.length} vertices · ${next.mesh.triangles.length} triangles · ${next.mesh.seamEdges.length} seam edges`;
    element('ledger').textContent=JSON.stringify({schema:next.schema,identity:next.identity,recipe,metadata:next.metadata,geometry:next.geometry,report:next.report,selection:next.selection},null,2);
    element('evidence').textContent='diagnostic 几何候选\n开放切割表面；无岩壁侧壁／封闭实体\n水力未就绪 · 自然度未认证 · 不可发布 · 自交尚未验证';
    element('sourceRegistry').textContent=JSON.stringify(next.source,null,2);
    if(next.schema==='fault-case-v1'){
        const bounds=next.plane_origin_bounds_xz_m;
        for(const [id,axis] of [['faultX',0],['faultZ',1]]){
            if(bounds){element(id).min=bounds[0][axis];element(id).max=bounds[1][axis]}
            else{element(id).removeAttribute('min');element(id).removeAttribute('max')}
        }
    }
    active=true;pending=false;render();resetCamera();
}
function pick(event){
    if(!active||!payload||pending||!pointerStart||event.button!==0||Math.hypot(event.clientX-pointerStart[0],event.clientY-pointerStart[1])>4)return;
    const rect=canvas.getBoundingClientRect(),compare=mode()==='compare',right=compare&&event.clientX-rect.left>=rect.width/2;
    const paneWidth=compare?rect.width/2:rect.width,paneLeft=rect.left+(right?paneWidth:0);
    const group=compare?(right?after:before):mode()==='before'?before:after;
    group.updateMatrixWorld(true);
    const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((event.clientX-paneLeft)/paneWidth*2-1,-(event.clientY-rect.top)/rect.height*2+1),currentCamera());
    const hit=ray.intersectObject(group.children[0])[0];if(!hit)return;
    const mesh=payload.mesh,face=mesh.triangles[hit.faceIndex],points=group===before?mesh.reference:mesh.vertices;
    let vertex=face[0],minimum=Infinity;
    for(const index of face){
        const point=new THREE.Vector3(...points[index].map((value,axis)=>value-origin[axis])).applyMatrix4(group.matrixWorld);
        const distance=point.distanceToSquared(hit.point);if(distance<minimum){minimum=distance;vertex=index}
    }
    selected={type:'fault-vertex-face',mode:group===before?'before':'after',index:vertex,faceIndex:hit.faceIndex,sourceVertexIndex:mesh.sourceVertexIndex[vertex],sourceTriangleIndex:mesh.sourceTriangleIndex[hit.faceIndex],sourceFaceVertices:face.map(index=>mesh.sourceVertexIndex[index]),xyz:points[vertex],reference:mesh.reference[vertex],after:mesh.vertices[vertex],side:mesh.vertexSide[vertex],displacement:mesh.displacement[vertex],transitionWeight:mesh.transitionWeight[vertex],protected:mesh.protected[vertex],identity:payload.identity};
    element('selectionTitle').textContent=`vertex ${selected.sourceVertexIndex} · face ${selected.sourceTriangleIndex}`;
    element('selection').textContent=JSON.stringify(selected,null,2);element('coords').textContent=`XYZ m ${JSON.stringify(selected.xyz)}`;
}
canvas.addEventListener('pointerdown',event=>{pointerStart=[event.clientX,event.clientY]});
canvas.addEventListener('pointerup',pick);canvas.addEventListener('pointercancel',()=>{pointerStart=null});
element('faultMode').addEventListener('change',()=>{selected=null;element('selection').textContent='';element('selectionTitle').textContent='尚未选取';element('coords').textContent='未选取';render()});
new ResizeObserver(render).observe(wrap);
function reviewRecord(){
    if(!payload||pending)return null;
    return {schema:'fault-surface-review-v1',category:'vdm',workspace:'fault',caseId:'strike-slip-fault',identity:payload.identity,source:payload.source,metadata:payload.metadata,geometry:payload.geometry,report:payload.report,recipe:structuredClone(recipe),mesh:{vertices:payload.mesh.vertices.length,triangles:payload.mesh.triangles.length,seamEdges:payload.mesh.seamEdges.length},mesh_counts:{vertices:payload.mesh.vertices.length,triangles:payload.mesh.triangles.length,seamEdges:payload.mesh.seamEdges.length},payloadSchema:payload.schema,geometry_generated:true,status:payload.schema==='fault-case-v1'?'diagnostic_saved_geometry':'diagnostic_geometry_preview',hydraulic_ready:false,natural_outlet_verified:false,publishable:false,self_intersections_verified:false,view:window.surfaceRenderer.state.view,mode:mode(),camera:{position:currentCamera().position.toArray(),target:currentControls().target.toArray(),relative_origin_xyz_m:[...origin],vertical:after.scale.y,zoom:currentCamera().zoom},layers:{...layers},selection:selected};
}
window.faultSurface={load,clear,render,resetCamera,reviewRecord,isLoading:()=>pending,isActive:()=>active,
    begin(){active=true;pending=true;ensureRenderer();clear();render()},finish(){pending=false},
    close(){active=false;pending=false;clear();canvas.classList.add('hidden');labels.classList.add('hidden');element('surface').classList.remove('hidden');if(controls)controls.enabled=false;if(mapControls)mapControls.enabled=false}
};
