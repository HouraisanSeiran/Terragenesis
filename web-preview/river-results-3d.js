import * as THREE from 'three';
import {OrbitControls} from '/vendor/node_modules/three/examples/jsm/controls/OrbitControls.js';

const parent=document.querySelector('.canvas-wrap');
const renderer=TerraView.createRenderer(THREE);
renderer.domElement.id='riverResult3d';renderer.domElement.style.cssText='position:absolute;inset:0;width:100%;height:100%;display:none';parent.append(renderer.domElement);
const scene=TerraView.createScene(THREE);
const camera=new THREE.PerspectiveCamera(42,1,.01,10000);
const controls=TerraView.configureControls(THREE,new OrbitControls(camera,renderer.domElement));controls.enableDamping=false;
let group=null,identity=null,layer=null,base=null,open=false;
function draw(){const width=parent.clientWidth,height=parent.clientHeight;renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();renderer.render(scene,camera);TerraView.hud.show('河槽成果 · 保存三角网',true)}
controls.addEventListener('change',draw);
function mesh(data,heights,context=false){
    const geometry=new THREE.BufferGeometry(),positions=new Float32Array(data.xz.length*3),colors=new Float32Array(data.xz.length*3);
    const range=heights.reduce((r,v)=>[Math.min(r[0],v),Math.max(r[1],v)],[Infinity,-Infinity]);
    const maximum=data.cut_m?data.cut_m.reduce((r,v)=>Math.max(r,v),0):0;
    for(let i=0;i<data.xz.length;i++){
        positions.set([data.xz[i][0]-base[0],heights[i]-base[1],data.xz[i][1]-base[2]],i*3);
        const t=(heights[i]-range[0])/(range[1]-range[0]||1),cut=data.cut_m?.[i]||0;
        // 与 2D 画布同一套渐变：地形用 relief，切深用 cut；顶点色按线性空间上传。
        let rgb=TerraTheme.reliefRgb(t*.8);
        if(!context&&layer!=='original')rgb=TerraTheme.cutRgb(cut/(maximum||1));
        colors.set(TerraView.linearColor(rgb),i*3);
    }
    geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));geometry.setIndex(data.triangles.flat());geometry.computeVertexNormals();
    return new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({vertexColors:true,roughness:1,side:THREE.DoubleSide}));
}
function clear(){if(group){scene.remove(group);group.traverse(o=>{o.geometry?.dispose();o.material?.dispose()});group=null}identity=null}
function reset(){if(!group)return;const box=new THREE.Box3().setFromObject(group),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3()),distance=Math.max(size.x,size.z,size.y)*1.2;camera.position.copy(center).add(new THREE.Vector3(distance*.6,distance*.7,distance*.8));controls.target.copy(center);camera.near=.01;camera.far=distance*50;camera.updateProjectionMatrix();controls.update();draw()}
function render(result,mode,vertical){
    open=true;
    renderer.domElement.style.display='block';document.querySelector('#surface').style.visibility='hidden';
    if(identity!==result.identity||layer!==mode){
        clear();identity=result.identity;layer=mode;
        const c=result.context,b=result.source.bounds_xz_m;base=[(b[0][0]+b[1][0])/2,c.original_m.reduce((s,v)=>s+v,0)/c.original_m.length,(b[0][1]+b[1][1])/2];
        group=new THREE.Group();group.add(mesh(c,c.original_m,true));group.add(mesh(result.mesh,mode==='original'?result.mesh.original_m:result.mesh.bed_m));scene.add(group);group.scale.y=vertical;reset();
    }else group.scale.y=vertical;
    draw();
}
function close(){if(open)TerraView.hud.hide();open=false;renderer.domElement.style.display='none';document.querySelector('#surface').style.visibility='visible'}
const reviewCamera=()=>({position:camera.position.toArray(),target:controls.target.toArray()});
// 旧名（render/close/reset/reviewCamera）被 app.js、renderer.js 与验收脚本使用，保持不变；
// 其余为与其他 3D 查看器一致的统一接口。
window.riverResultScene=TerraView.register('riverResultScene',{render,close,reset,reviewCamera,
    resetCamera:reset,reviewRecord:reviewCamera,isLoading:()=>false,isActive:()=>open});
