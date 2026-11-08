import * as THREE from 'three';
import {OrbitControls} from './vendor/node_modules/three/examples/jsm/controls/OrbitControls.js';
import {validate, validPoint} from './underground-contract.js';

const element=id=>document.getElementById(id);
const wrap=document.querySelector('.canvas-wrap');
const canvas=document.createElement('canvas');
canvas.id='undergroundSurface';
canvas.className='saved-canvas hidden';
canvas.setAttribute('aria-label','地下暗河局部 XYZ 米制几何');
wrap.prepend(canvas);
const scene=TerraView.createScene(THREE);
const group=new THREE.Group();
scene.add(group);
const {camera,mapCamera}=TerraView.createCameras(THREE);
const layers={rock:true,cutter:false,removed:false,reference:false,sections:false,centerline:false};
const scope='固定 125 m 山地样例 · 人工构造几何 · 非自然洞道发现';
const clipPlane=new THREE.Plane();
let renderer=null,controls=null,mapControls=null,payload=null,active=false,pending=false,selected=null,pointerStart=null;
const isThree=()=>window.surfaceRenderer.state.view==='3d';
const currentCamera=()=>isThree()?camera:mapCamera;
const currentControls=()=>isThree()?controls:mapControls;
function ensureRenderer(){
    if(renderer)return;
    renderer=TerraView.createRenderer(THREE,canvas);
    renderer.localClippingEnabled=true;
    controls=new OrbitControls(camera,canvas);
    mapControls=new OrbitControls(mapCamera,canvas);
    TerraView.configureControls(THREE,controls);
    TerraView.configureControls(THREE,mapControls,{map:true});
    for(const orbit of [controls,mapControls])orbit.addEventListener('change',render);
}
function clear(){
    payload=null;selected=null;
    while(group.children.length){
        const item=group.children[0];
        group.remove(item);item.geometry.dispose();item.material.dispose();
    }
    for(const id of ['stats','ledger','evidence','sourceRegistry','selection','coords'])element(id).textContent='';
    element('selectionTitle').textContent='尚未选取';
    element('undergroundStationLabel').textContent='—';
    if(active&&renderer)renderer.render(scene,currentCamera());
}
function mesh(name,points,triangles,color,opacity=1,wireframe=false){
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(points.flat(),3));
    geometry.setIndex(triangles.flat());
    geometry.computeVertexNormals();
    const material=new THREE.MeshStandardMaterial({color,side:THREE.DoubleSide,roughness:.78,transparent:opacity<1,opacity,depthWrite:opacity===1,wireframe});
    const item=new THREE.Mesh(geometry,material);
    item.name=name;group.add(item);
}
function line(name,points,color,segments=false){
    const geometry=new THREE.BufferGeometry().setFromPoints(points.map(point=>new THREE.Vector3(...point)));
    const material=new THREE.LineBasicMaterial({color,depthTest:false});
    const item=segments?new THREE.LineSegments(geometry,material):new THREE.Line(geometry,material);
    item.name=name;item.renderOrder=3;group.add(item);
}
function makeLayers(){
    element('layers').replaceChildren();
    for(const [name,label] of [['rock','岩体'],['cutter','cutter'],['removed','移除岩石'],['reference','VDM reference'],['sections','断面'],['centerline','中心线']]){
        const row=document.createElement('label'),input=document.createElement('input');
        input.type='checkbox';input.checked=layers[name];input.dataset.layer=name;
        input.onchange=()=>{layers[name]=input.checked;render()};
        row.append(input,label);element('layers').append(row);
    }
}
function sectionIndex(){return Math.max(0,Math.min(payload.stations.length-1,Number(element('undergroundStation').value)||0))}
function showStation(index){
    if(!payload)return;
    const station=payload.stations[index];
    selected={type:'underground-station',...station,crop_origin_xyz_m:[...payload.origin_xyz_m],station_world_xyz_m:station.origin_local_xyz_m.map((value,axis)=>value+payload.origin_xyz_m[axis]),parameters:payload.parameters,source_pins:payload.source_pins,identity_sha256:payload.identity_sha256,status:payload.status,scope,capabilities:payload.capabilities,water:null};
    element('selectionTitle').textContent=`断面 ${station.station_id}`;
    element('selection').textContent=JSON.stringify(selected,null,2);
    element('coords').textContent=`局部 XYZ m ${station.origin_local_xyz_m.map(value=>value.toFixed(2)).join(', ')}`;
}
function updateVisibility(){
    const mode=element('undergroundMode').value,index=sectionIndex();
    const clipping=element('undergroundClip').checked;
    const origin=new THREE.Vector3(...payload.stations[index].origin_local_xyz_m).applyMatrix4(group.matrixWorld);
    const previous=payload.stations[Math.max(0,index-1)].origin_local_xyz_m;
    const following=payload.stations[Math.min(payload.stations.length-1,index+1)].origin_local_xyz_m;
    const normal=new THREE.Vector3(...following).sub(new THREE.Vector3(...previous));
    normal.y/=group.scale.y;
    if(normal.lengthSq()===0)normal.set(1,0,0);
    clipPlane.setFromNormalAndCoplanarPoint(normal.normalize().negate(),origin);
    for(const item of group.children){
        if(item.name==='derived')item.visible=mode==='derived';
        else if(item.name==='rock_before'||item.name==='rock_after')item.visible=mode===item.name||(layers.rock&&item.name==='rock_after'&&mode!=='rock_before');
        else if(item.name.startsWith('section_'))item.visible=layers.sections||(clipping&&item.name===`section_${index}`);
        else item.visible=mode===item.name||!!layers[item.name];
        item.material.clippingPlanes=clipping&&!item.name.startsWith('section_')?[clipPlane]:[];
    }
    element('undergroundStationLabel').textContent=String(payload.stations[index].station_id);
}
function resetCamera(){
    if(!payload||!renderer)return;
    group.scale.y=Number(element('verticalScale').value);
    const box=new THREE.Box3();
    const mode=element('undergroundMode').value;
    const points=layers.rock||mode==='rock_before'||mode==='rock_after'
        ?payload.meshes.rock_before.vertices_local_xyz_m:payload.vdm.derived_local_xyz_m;
    for(const point of points)box.expandByPoint(new THREE.Vector3(point[0],point[1]*group.scale.y,point[2]));
    const ratio=Math.max(1,wrap.clientWidth)/Math.max(1,wrap.clientHeight);
    TerraView.frame(THREE,{box,camera,controls,aspect:ratio,direction:[.85,.65,.85],pad:1.15,farFactor:30});
    TerraView.frameMap(THREE,{box,mapCamera,mapControls,aspect:ratio,pad:1.15});
    render();
}
function render(){
    if(!active)return;
    canvas.classList.remove('hidden');element('surface').classList.add('hidden');
    if(!renderer)return;
    const width=Math.max(1,wrap.clientWidth),height=Math.max(1,wrap.clientHeight),ratio=width/height;
    renderer.setSize(width,height,false);
    controls.enabled=isThree()&&!pending;mapControls.enabled=!isThree()&&!pending;
    camera.aspect=ratio;camera.updateProjectionMatrix();
    mapCamera.left=-mapCamera.top*ratio;mapCamera.right=mapCamera.top*ratio;mapCamera.updateProjectionMatrix();
    group.scale.y=Number(element('verticalScale').value);group.updateMatrixWorld(true);
    if(payload)updateVisibility();
    renderer.render(scene,currentCamera());
    TerraView.hud.show('地下暗河 · 几何',isThree());
}
function load(next){
    validate(next);clear();ensureRenderer();payload=next;
    for(const [name,color,opacity] of [['rock_before',TerraView.material.rock,.18],['rock_after',TerraView.material.rock,.18],['cutter',TerraView.material.cutter,.45],['removed',TerraView.material.removed,.55]]){
        mesh(name,next.meshes[name].vertices_local_xyz_m,next.meshes[name].triangles,color,opacity);
    }
    mesh('derived',next.vdm.derived_local_xyz_m,next.vdm.triangles,TerraView.material.derived);
    mesh('reference',next.vdm.reference_local_xyz_m,next.vdm.triangles,TerraView.material.reference,.65,true);
    line('centerline',next.stations.map(station=>station.origin_local_xyz_m),TerraView.material.centerline);
    next.stations.forEach((station,index)=>line(`section_${index}`,[...station.ring_local_xyz_m,station.ring_local_xyz_m[0]],TerraView.material.section));
    const portalPoints=next.portals.flatMap(portal=>{
        const [east,height,north]=portal.position_local_xyz_m;
        return [[east-1,height,north],[east+1,height,north],[east,height-1,north],[east,height+1,north],[east,height,north-1],[east,height,north+1]];
    });
    line('centerline',portalPoints,TerraView.material.portal,true);
    element('undergroundStation').max=String(next.stations.length-1);element('undergroundStation').value='0';
    element('viewSubtitle').textContent=`局部 XYZ · m · ${next.status}`;
    const metrics=next.metrics;
    element('stats').textContent=`长度 ${Number(metrics.length_m).toFixed(1)} m · 开挖 ${Number(metrics.excavated_rock_m3).toFixed(2)} m³ · 残差 ${Number(metrics.material_residual_m3).toExponential(2)} m³ · 封闭核心 ${metrics.closed_core_count}`;
    element('ledger').textContent=JSON.stringify({schema:next.schema,identity_sha256:next.identity_sha256,origin_xyz_m:next.origin_xyz_m,parameters:next.parameters,metrics:next.metrics,portals:next.portals},null,2);
    element('evidence').textContent=`${scope}\ngeometry_checked · 仅几何检查，非自然度认证\n水力未求解 · 完整河网未验证 · 自然出口未认证\nwater: null`;
    element('sourceRegistry').textContent=JSON.stringify(next.source_pins,null,2);
    active=true;pending=false;makeLayers();resetCamera();
}
function pick(event){
    if(!active||pending||!payload||event.button!==0||!pointerStart||Math.hypot(event.clientX-pointerStart[0],event.clientY-pointerStart[1])>4)return;
    const rect=canvas.getBoundingClientRect();
    group.updateMatrixWorld(true);currentCamera().updateMatrixWorld(true);
    let nearest=-1,distance=18**2;
    payload.stations.forEach((station,index)=>{
        const world=new THREE.Vector3(...station.origin_local_xyz_m).applyMatrix4(group.matrixWorld);
        if(element('undergroundClip').checked&&clipPlane.distanceToPoint(world)<0)return;
        const point=world.project(currentCamera());
        if(point.z<-1||point.z>1)return;
        const squared=((point.x+1)*rect.width/2+rect.left-event.clientX)**2+((1-point.y)*rect.height/2+rect.top-event.clientY)**2;
        if(squared<distance){nearest=index;distance=squared}
    });
    if(nearest>=0){element('undergroundStation').value=String(nearest);showStation(nearest);render()}
}
canvas.addEventListener('pointerdown',event=>{pointerStart=[event.clientX,event.clientY]});
canvas.addEventListener('pointerup',pick);
canvas.addEventListener('pointercancel',()=>{pointerStart=null});
element('undergroundStation').addEventListener('input',()=>{if(payload){showStation(sectionIndex());render()}});
for(const id of ['undergroundClip','undergroundMode'])element(id).addEventListener('change',render);
new ResizeObserver(()=>{if(active&&payload)resetCamera();else render()}).observe(wrap);
function reviewRecord(){
    if(!payload||pending)return null;
    const meshCounts=Object.fromEntries(Object.entries(payload.meshes).map(([name,mesh])=>[name,{vertices:mesh.vertices_local_xyz_m.length,triangles:mesh.triangles.length}]));
    return {schema:'underground-surface-review-v1',category:'rivers',workspace:'underground',caseId:'underground',identity:payload.identity_sha256,identity_sha256:payload.identity_sha256,mesh_counts:meshCounts,vdm_counts:{vertices:payload.vdm.derived_local_xyz_m.length,triangles:payload.vdm.triangles.length},station_count:payload.stations.length,portal_count:payload.portals.length,origin_xyz_m:payload.origin_xyz_m,parameters:payload.parameters,source_pins:payload.source_pins,status:payload.status,scope,capabilities:payload.capabilities,metrics:payload.metrics,water:null,view:window.surfaceRenderer.state.view,mode:element('undergroundMode').value,layers:{...layers},clip:{enabled:element('undergroundClip').checked,stationIndex:sectionIndex()},camera:{position:currentCamera().position.toArray(),target:currentControls().target.toArray(),vertical:group.scale.y,zoom:currentCamera().zoom},selection:selected};
}
window.undergroundSurface=TerraView.register('undergroundSurface',{load,clear,render,resetCamera,reviewRecord,isLoading:()=>pending,isActive:()=>active,
    begin(){active=true;pending=true;ensureRenderer();clear();render()},
    finish(){pending=false;render()},
    close(){active=false;pending=false;clear();TerraView.hud.hide();canvas.classList.add('hidden');element('surface').classList.remove('hidden');if(controls)controls.enabled=false;if(mapControls)mapControls.enabled=false}
});
