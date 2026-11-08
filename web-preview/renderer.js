"use strict";
/* ---- Terragenesis 视觉语言 + 共享 3D 查看器工具包 -------------------------------------
 * 经典脚本，先于所有 ES 模块查看器加载（bridge 白名单里已有本文件，因此不新增文件）。
 *   TerraTheme  调色板、等高渐变、切深渐变：2D 画布与 3D 顶点色共用同一套数值。
 *   TerraView   场景/灯光/相机/控制器/取景的统一构造，以及查看器注册表与接口约定。
 * 只管显示，不读取也不改变任何算法结果。 */
(function installTerraKit(global) {
    const colors = {stage: '#16120d', panel: '#1d1812', line: '#5d4e37', paper: '#ece0c4', soft: '#cfc3a8', muted: '#a09479',
        amber: '#e3a63c', rust: '#cf6b4b', teal: '#58b4a8', olive: '#a3b36c', sand: '#d9c294'};
    const stops = [[0, [42, 72, 66]], [.22, [78, 110, 80]], [.48, [146, 146, 94]], [.74, [196, 146, 82]], [1, [232, 214, 172]]];
    const clamp01 = value => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
    const mixRgb = (first, second, weight) => first.map((value, index) => value + (second[index] - value) * weight);
    const css = rgb => `rgb(${rgb.map(Math.round).join(',')})`;
    function reliefRgb(t) {
        t = clamp01(t);
        for (let index = 1; index < stops.length; index++) {
            if (t <= stops[index][0]) {
                const [low, from] = stops[index - 1], [high, to] = stops[index];
                return mixRgb(from, to, (t - low) / ((high - low) || 1));
            }
        }
        return stops[stops.length - 1][1].slice();
    }
    const cutRgb = v => mixRgb([86, 128, 116], [232, 160, 60], clamp01(v));
    const diverge = {neutral: [168, 158, 133], incision: [207, 107, 75], deposition: [88, 180, 168]};
    const theme = {colors, diverge, mixRgb, clamp01, reliefRgb, cutRgb,
        relief: t => css(reliefRgb(t)), cut: v => css(cutRgb(v)), css,
        font: {ui: '"Segoe UI Variable Text","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif', mono: '"Cascadia Mono",Consolas,ui-monospace,monospace'}};

    // Three.js 材质色（0xRRGGBB，按 sRGB 解释）。所有查看器从这里取色，保证同一语义同一颜色。
    const material = {terrain: 0xa9a37c, water: 0x4aa3b0, reference: 0x8fb3a6, rock: 0xb3a98f, solid: 0xc09a63,
        cutter: 0xe3a63c, removed: 0xcf6b4b, derived: 0x6fc0b0, section: 0xf1d9a6, centerline: 0xb9d6dc,
        portal: 0xe98a6c, edge: 0xe3a63c, moving: 0x58b4a8, marker: 0xe3a63c};

    const lut = new Float32Array(256);
    for (let index = 0; index < 256; index++) { const s = index / 255; lut[index] = s <= .04045 ? s / 12.92 : Math.pow((s + .055) / 1.055, 2.4); }
    // 顶点色数组按线性空间解释；调色板数值是 sRGB 0..255，所以写进 BufferAttribute 前必须转换。
    const linearColor = rgb => rgb.map(value => lut[Math.max(0, Math.min(255, Math.round(value)))]);

    const contract = ['render', 'resetCamera', 'reviewRecord', 'isLoading', 'isActive', 'close'];
    const viewers = {};
    const view = {
        theme, material, contract, viewers, linearColor,
        direction: [.85, .9, .85],
        createRenderer(THREE, canvas) {
            const renderer = new THREE.WebGLRenderer(canvas ? {canvas, antialias: true, preserveDrawingBuffer: true} : {antialias: true, preserveDrawingBuffer: true});
            renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, 2));
            return renderer;
        },
        createScene(THREE) {
            const scene = new THREE.Scene();
            scene.background = new THREE.Color(colors.stage);
            scene.add(new THREE.HemisphereLight(0xf3e8d0, 0x4b402f, 2.1));
            const key = new THREE.DirectionalLight(0xffe7c0, 2.1); key.position.set(80, 180, -80); scene.add(key);
            const fill = new THREE.DirectionalLight(0x8fb9c4, .5); fill.position.set(-120, 60, 100); scene.add(fill);
            return scene;
        },
        createCameras(THREE) {
            const camera = new THREE.PerspectiveCamera(45, 1, .01, 100000);
            const mapCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, .01, 100000);
            mapCamera.up.set(0, 0, -1);
            return {camera, mapCamera};
        },
        // 左键旋转、右键平移、滚轮缩放；允许绕到下方；地图相机左键平移且不旋转。
        configureControls(THREE, controls, {map = false} = {}) {
            controls.rotateSpeed = -1; controls.minPolarAngle = .01; controls.maxPolarAngle = Math.PI - .01;
            controls.mouseButtons = {LEFT: map ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN};
            if (map) controls.enableRotate = false;
            return controls;
        },
        frame(THREE, {box, camera, controls, aspect, direction = view.direction, pad = 1.12, farFactor = 20}) {
            const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
            const extent = Math.max(size.x, size.y, size.z, 1), half = camera.fov * Math.PI / 360;
            const angle = Math.min(half, Math.atan(Math.tan(half) * aspect));
            const distance = box.getBoundingSphere(new THREE.Sphere()).radius / Math.sin(angle) * pad;
            camera.aspect = aspect; camera.near = Math.max(.01, extent / 10000); camera.far = Math.max(extent * farFactor, distance * 4);
            controls.target.copy(center);
            camera.position.copy(center).add(new THREE.Vector3(...direction).normalize().multiplyScalar(distance));
            camera.updateProjectionMatrix(); controls.update();
            return {center, size, extent, distance};
        },
        frameMap(THREE, {box, mapCamera, mapControls, aspect, pad = 1.12}) {
            const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
            const extent = Math.max(size.x, size.y, size.z, 1), half = Math.max(size.z / 2, size.x / (2 * aspect), 1) * pad;
            mapCamera.left = -half * aspect; mapCamera.right = half * aspect; mapCamera.top = half; mapCamera.bottom = -half;
            mapCamera.near = .01; mapCamera.far = extent * 30; mapCamera.zoom = 1;
            mapControls.target.copy(center); mapCamera.position.copy(center).add(new THREE.Vector3(0, extent * 8, 0));
            mapCamera.updateProjectionMatrix(); mapControls.update();
            return {center, size, extent};
        },
        // 窗口变化后若相机距离小于能容纳模型的最小距离，则拉远（原先在 saved/special/pillars 三处各写一份）。
        keepInView(THREE, {group, camera, controls, resized}) {
            const radius = new THREE.Box3().setFromObject(group).getBoundingSphere(new THREE.Sphere()).radius;
            const half = camera.fov * Math.PI / 360, angle = Math.min(half, Math.atan(Math.tan(half) * camera.aspect));
            const direction = camera.position.clone().sub(controls.target), minimum = radius / Math.sin(angle) * 1.05;
            if (resized && direction.length() < minimum) camera.position.copy(controls.target).add(direction.normalize().multiplyScalar(minimum));
        },
        // 统一提示层：左下角视图徽标 + 右上角操作提示，所有 3D 查看器共用同一对元素。
        hud: (() => {
            let badge = null, hint = null;
            const ensure = () => {
                if (badge) return true;
                const wrap = document.querySelector('.canvas-wrap');
                if (!wrap) return false;
                badge = document.createElement('div'); badge.className = 'tg-badge hidden'; badge.setAttribute('aria-hidden', 'true');
                hint = document.createElement('div'); hint.className = 'tg-hint hidden'; hint.setAttribute('aria-hidden', 'true');
                hint.textContent = '左键旋转 · 右键平移 · 滚轮缩放 · 单击点选';
                wrap.append(badge, hint);
                return true;
            };
            return {
                show(label, threeD) {
                    if (!ensure()) return;
                    badge.textContent = '';
                    const strong = document.createElement('b'); strong.textContent = threeD ? '3D' : '2D';
                    badge.append(strong, ` · ${label}`);
                    badge.classList.remove('hidden'); hint.classList.toggle('hidden', !threeD);
                },
                hide() { if (badge) { badge.classList.add('hidden'); hint.classList.add('hidden'); } }
            };
        })(),
        // 查看器注册：保持原有 window.xxx 全局不变，同时校验统一接口。
        register(name, api) {
            const missing = contract.filter(key => typeof api[key] !== 'function');
            if (missing.length) console.warn(`TerraView: ${name} 缺少接口 ${missing.join(', ')}`);
            viewers[name] = api;
            return api;
        },
        active() { return Object.values(viewers).find(item => { try { return item.isActive(); } catch (error) { return false; } }) || null; }
    };
    global.TerraTheme = theme;
    global.TerraView = view;
}(window));
const canvas=document.querySelector("#surface"),ctx=canvas.getContext("2d");
let state={view:"2d",case:null,caseId:"",yaw:-.55,pitch:.65,zoom:1,panX:0,panY:0,vertical:1,drag:false,moved:false,lastX:0,lastY:0,time:0,layers:{h0:false,bed:true,water:true,wet:true,domains:true,unknown:true,edges:true,footprint:true,displacement:false}};
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function resize(){syncCanvas();render()}
function syncCanvas(){const d=devicePixelRatio||1,w=Math.round(canvas.clientWidth*d),h=Math.round(canvas.clientHeight*d);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}ctx.setTransform(d,0,0,d,0,0)}
function range(values){let lo=Infinity,hi=-Infinity;for(const value of values){if(Number.isFinite(value)){lo=Math.min(lo,value);hi=Math.max(hi,value)}}return lo===Infinity?[0,1]:[lo,hi]}
function bounds(points){let xlo=Infinity,xhi=-Infinity,zlo=Infinity,zhi=-Infinity;for(const point of points){xlo=Math.min(xlo,point[0]);xhi=Math.max(xhi,point[0]);zlo=Math.min(zlo,point[2]);zhi=Math.max(zhi,point[2])}return [xlo,xhi,zlo,zhi]}
function fit(b,w,h,pad=30){return Math.min((w-pad*2)/(b[1]-b[0]||1),(h-pad*2)/(b[3]-b[2]||1))}
function project(p,b,w,h,s){return [w/2+state.panX+(p[0]-(b[0]+b[1])/2)*s*state.zoom,h/2+state.panY+(p[2]-(b[2]+b[3])/2)*s*state.zoom]}
function drawLine(points,color,width=1){if(!points.length)return;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke()}
function colorRamp(v,lo,hi){return TerraTheme.relief(clamp((v-lo)/(hi-lo||1),0,1))}
function drawTriangle(points,fill,stroke=null){ctx.beginPath();ctx.moveTo(...points[0]);points.slice(1).forEach(p=>ctx.lineTo(...p));ctx.closePath();ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.stroke()}}
function mesh2d(m,w,h){let b=bounds(m.vertices),s=fit(b,w,h),p=m.vertices.map(v=>project(v,b,w,h,s));const show=state.layers.h0?m.h0:m.bed,[lo,hi]=range(show);if(state.layers.h0||state.layers.bed)m.triangles.forEach(t=>drawTriangle(t.map(i=>p[i]),colorRamp(show[t[0]],lo,hi)));if(state.layers.water&&m.wetCells)m.triangles.forEach((t,index)=>{if(m.wetCells[Math.floor(index/2)])drawTriangle(t.map(i=>p[i]),"#4aa3b0aa")});drawMeshOverlays(m,p,v=>project(v,b,w,h,s));return {b,s,p,triangles:m.triangles}}
function drawMeshOverlays(m,p,projection){
    const perimeter=cell=>[...cell,cell[0]];
    if(state.layers.wet&&Array.isArray(m.wetCells)&&Array.isArray(m.cells))for(let index=0;index<m.wetCells.length;index++)if(m.wetCells[index]&&m.cells[index])drawLine(perimeter(m.cells[index]).map(node=>p[node]),"#7cd4d6",.7);
    if(state.layers.domains&&Array.isArray(m.hydrologicOwner)&&Array.isArray(m.cells)){const owners=m.hydrologicOwner.flat();for(let index=0;index<m.cells.length;index++){const cell=m.cells[index];drawLine(perimeter(cell).map(node=>p[node]),owners[index]===1?"#58b4a866":owners[index]===2?"#cf6b4b66":"#d9c29444",.6)}}
    if(state.layers.footprint){
        const overlay=state.case.overlay,show=state.layers.h0?m.h0:m.bed,vertex=index=>[m.vertices[index][0],show[index],m.vertices[index][2]],indices=m.vertices.map((_,index)=>index);
        if(overlay?.candidateFootprint){
            const [xmin,xmax,zmin,zmax]=overlay.candidateFootprint,b=bounds(m.vertices),onMesh=xmin===b[0]&&xmax===b[1]&&zmin===b[2]&&zmax===b[3];
            let outline;
            if(onMesh){const edge=(axis,value,sortAxis,reverse=false)=>indices.filter(index=>m.vertices[index][axis]===value).sort((left,right)=>(m.vertices[left][sortAxis]-m.vertices[right][sortAxis])*(reverse?-1:1));const perimeter=[...edge(2,zmin,0),...edge(0,xmax,2).slice(1),...edge(2,zmax,0,true).slice(1),...edge(0,xmin,2,true).slice(1)];outline=perimeter.map(index=>projection(vertex(index)))}
            else outline=[[xmin,0,zmin],[xmax,0,zmin],[xmax,0,zmax],[xmin,0,zmax],[xmin,0,zmin]].map(projection);
            ctx.setLineDash([7,5]);drawLine(outline,"#e3a63c",2);ctx.setLineDash([]);ctx.fillStyle="#e3a63c";ctx.font="11px sans-serif";ctx.fillText(onMesh?'Footprint: actual mesh boundary':'XZ footprint reference projection (Y=0; not terrain)',14,18);
        }
        if(overlay?.sharedBoundaryX!==undefined){const shared=indices.filter(index=>m.vertices[index][0]===overlay.sharedBoundaryX).sort((left,right)=>m.vertices[left][2]-m.vertices[right][2]);drawLine(shared.map(index=>projection(vertex(index))),"#f1c36a",2);state.sharedBoundaryNodeIds=shared;state.sharedBoundaryProjected=shared.map(index=>projection(vertex(index)))}
    }
}
function coast2d(m,w,h){let b=bounds(m.bedVertices),s=fit(b,w,h),bed=m.bedVertices.map(v=>project(v,b,w,h,s)),water=m.waterVertices.map(v=>project(v,b,w,h,s));let [lo,hi]=range(m.bedVertices.map(point=>point[1]));if(state.layers.bed)m.triangles.forEach(t=>drawTriangle(t.map(i=>bed[i]),colorRamp(m.bedVertices[t[0]][1],lo,hi)));if(state.layers.water)m.triangles.forEach(t=>drawTriangle(t.map(i=>water[i]),"#4aa3b0aa"));drawLine(m.centerline.map(v=>project(v,b,w,h,s)),"#f1c36a",2);return {b,s,p:state.layers.water?water:bed,triangles:m.triangles}}
function dem2d(d,w,h){let g=d.grid,disp=d.display,rows=disp.height.length,cols=disp.height[0].length,b=[g.origin_x_m,g.origin_x_m+g.spacing_x_m*(cols-1)*disp.stride,g.origin_z_m,g.origin_z_m+g.spacing_z_m*(rows-1)*disp.stride],s=fit(b,w,h),p=[];const [lo,hi]=range(disp.height.flat());for(let row=0;row<rows;row++)for(let col=0;col<cols;col++){const x=b[0]+col*g.spacing_x_m*disp.stride,z=b[2]+row*g.spacing_z_m*disp.stride,pt=project([x,0,z],b,w,h,s),dx=s*state.zoom*g.spacing_x_m*disp.stride,dz=s*state.zoom*g.spacing_z_m*disp.stride;p.push(pt);const unknown=disp.unknown[row][col]||!Number.isFinite(disp.height[row][col]);if(!unknown&&state.layers.bed){ctx.fillStyle=colorRamp(disp.height[row][col],lo,hi);ctx.fillRect(pt[0]-dx/2,pt[1]-dz/2,dx+1,dz+1)}else if(unknown&&state.layers.unknown){drawLine([[pt[0]-dx/2,pt[1]-dz/2],[pt[0]+dx/2,pt[1]+dz/2]],"#cf6b4b")}if(state.layers.footprint&&!disp.footprint[row][col]){ctx.strokeStyle="#e3a63c";ctx.strokeRect(pt[0]-dx/2,pt[1]-dz/2,dx,dz)}}return {b,s,p}}
function flowInterval(d=state.case){return d?window.riverRenderer?.flowInterval(d,state)||null:null}
function camera3d(vertices,heights,w,h){
    const b=bounds(vertices),s=fit(b,w,h,50)*state.zoom,[lo,hi]=range(heights),cy=Math.cos(state.yaw),sy=Math.sin(state.yaw),cp=Math.cos(state.pitch),sp=Math.sin(state.pitch),mx=(b[0]+b[1])/2,mz=(b[2]+b[3])/2,my=(lo+hi)/2;
    function projection(vertex){const x=(vertex[0]-mx)*cy-(vertex[2]-mz)*sy,z=(vertex[0]-mx)*sy+(vertex[2]-mz)*cy,y=(vertex[1]-my)*state.vertical;return [w/2+state.panX+x*s,h/2+state.panY+(z*sp-y*cp)*s,z*cp+y*sp]}
    return {b,s,projection};
}
function dynamic2d(d,w,h,baseCamera=null){
    if(!window.riverRenderer)throw Error('河网渲染模块尚未加载');
    return window.riverRenderer.render(d,w,h,baseCamera,{state,bounds,fit,project,camera3d,drawLine,drawTriangle,context:ctx});
}
function mesh3d(vertices,triangles,heights,w,h,water=null,wet=null,h0=null,baseCamera=null,defer=false,wetCells=null){
    const show=h0&&state.layers.h0?h0:heights,[lo,hi]=range(show),camera=baseCamera||camera3d(vertices,show,w,h),p=vertices.map((vertex,index)=>Number.isFinite(show[index])?camera.projection([vertex[0],show[index],vertex[2]]):null),wp=water?vertices.map((vertex,index)=>Number.isFinite(water[index])?camera.projection([vertex[0],water[index],vertex[2]]):null):null,faces=[];
    let waterFaceCount=0;for(let triangleIndex=0;triangleIndex<triangles.length;triangleIndex++){const triangle=triangles[triangleIndex];if((state.layers.bed||state.layers.h0)&&triangle.every(index=>p[index]))faces.push({points:triangle.map(index=>p[index]),fill:colorRamp((show[triangle[0]]+show[triangle[1]]+show[triangle[2]])/3,lo,hi)});if(wp&&state.layers.water&&(wetCells?wetCells[Math.floor(triangleIndex/2)]:triangle.every(index=>wp[index]&&(!wet||wet[index])))){faces.push({points:triangle.map(index=>wp[index]),fill:"#4aa3b08c"});waterFaceCount++}}
    for(const face of faces)face.depth=(face.points[0][2]+face.points[1][2]+face.points[2][2])/3;
    if(!defer)drawFaces(faces);
    return {b:camera.b,s:camera.s,p:state.case.kind==='coast'&&state.layers.water?wp:p,bed:p,water:wp,camera,triangles,faces,waterFaceCount};
}
function drawFaces(faces){faces.sort((left,right)=>right.depth-left.depth);for(const face of faces)drawTriangle(face.points,face.fill)}
const demCache=new WeakMap();
function dem3d(d,w,h){
    let geometry=demCache.get(d);
    if(!geometry){const g=d.grid,display=d.display,rows=display.height.length,cols=display.height[0].length,vertices=[],heights=[],triangles=[];for(let row=0;row<rows;row++)for(let col=0;col<cols;col++){vertices.push([g.origin_x_m+col*g.spacing_x_m*display.stride,display.height[row][col],g.origin_z_m+row*g.spacing_z_m*display.stride]);heights.push(display.unknown[row][col]?null:display.height[row][col])}for(let row=0;row<rows-1;row++)for(let col=0;col<cols-1;col++){const ids=[row*cols+col,row*cols+col+1,(row+1)*cols+col+1,(row+1)*cols+col];if(ids.every(index=>Number.isFinite(heights[index])))triangles.push([ids[0],ids[1],ids[2]],[ids[0],ids[2],ids[3]])}geometry={vertices,heights,triangles};demCache.set(d,geometry)}
    const oldH0=state.layers.h0;state.layers.h0=false;const plot=mesh3d(geometry.vertices,geometry.triangles,geometry.heights,w,h);state.layers.h0=oldH0;plot.unknownPickPlane="minimum finite DEM height, marker only (not terrain)";
    if(state.layers.unknown||state.layers.footprint){const minimum=range(geometry.heights)[0],cols=d.display.height[0].length;for(let index=0;index<plot.p.length;index++){const row=Math.floor(index/cols),col=index%cols;if(!plot.p[index]){const vertex=geometry.vertices[index];plot.p[index]=plot.camera.projection([vertex[0],minimum,vertex[2]]);if(state.layers.unknown)drawLine([[plot.p[index][0]-2,plot.p[index][1]-2],[plot.p[index][0]+2,plot.p[index][1]+2]],"#cf6b4b")}if(state.layers.footprint&&!d.display.footprint[row][col]){ctx.strokeStyle="#e3a63c";ctx.strokeRect(plot.p[index][0]-2,plot.p[index][1]-2,4,4)}}}
    return plot;
}
function legacy2d(d,w,h){let b=[d.origin[0],d.origin[0]+(d.width-1)*d.spacing,d.origin[1],d.origin[1]+(d.height-1)*d.spacing],s=fit(b,w,h),p=[],data=d.legacyMode==='raw'||state.layers.legacyRaw&&!state.layers.legacyProcessed?d.raw:d.processed,lo=d.report.raw_height_range[0],hi=d.report.raw_height_range[1];for(let z=0;z<d.height;z++)for(let x=0;x<d.width;x++){let i=z*d.width+x,pt=project([d.origin[0]+x*d.spacing,0,d.origin[1]+z*d.spacing],b,w,h,s);p.push(pt);ctx.fillStyle=colorRamp(data[i],lo,hi);ctx.fillRect(pt[0],pt[1],Math.ceil(s*state.zoom*d.spacing+1),Math.ceil(s*state.zoom*d.spacing+1))}return {b,s,p}}
function legacy3d(d,w,h){let data=d.legacyMode==='raw'||state.layers.legacyRaw&&!state.layers.legacyProcessed?d.raw:d.processed,v=[],t=[];for(let z=0;z<d.height;z++)for(let x=0;x<d.width;x++)v.push([d.origin[0]+x*d.spacing,data[z*d.width+x],d.origin[1]+z*d.spacing]);for(let z=0;z<d.height-1;z++)for(let x=0;x<d.width-1;x++){let i=z*d.width+x;t.push([i,i+1,i+d.width+1],[i,i+d.width+1,i+d.width])}return mesh3d(v,t,data,w,h)}
function td2d(d,w,h){const page=d.page,grid=page.display,height=grid.height_m,valid=grid.valid_mask,mode=document.querySelector('#tdLayer')?.value||'depth',values=mode==='rain'?grid.rain_mm_h:mode==='bed'?height:state.time===0?grid.start_depth_m:grid.end_depth_m,rows=values.length,cols=values[0].length,points=[],b=[page.metadata.origin_m_xz[0],page.metadata.origin_m_xz[0]+(cols-1)*grid.spacing_m,page.metadata.origin_m_xz[1],page.metadata.origin_m_xz[1]+(rows-1)*grid.spacing_m],s=fit(b,w,h,25),finite=values.flat().filter(Number.isFinite),[lo,hi]=range(finite),size=s*state.zoom*grid.spacing_m;for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){const pt=project([b[0]+c*grid.spacing_m,0,b[2]+r*grid.spacing_m],b,w,h,s),v=values[r][c],ok=valid[r][c]&&Number.isFinite(v);points.push(ok?pt:null);if(!ok)continue;ctx.fillStyle=mode==='depth'&&v<grid.threshold_m?'#2b2519':colorRamp(v,lo,hi);ctx.fillRect(pt[0]-size/2,pt[1]-size/2,size+1,size+1)}ctx.fillStyle='#e6dbc0';ctx.font='11px sans-serif';ctx.fillText(`${mode==='rain'?'rain mm/h':mode==='bed'?'native bed m':'saved depth m'} · display stride ${grid.stride} · missing cells not dry`,14,20);return {b,s,p:points,tdSample:true}}
function morphologySelection(){return document.querySelector('#morphologyFeature')?.value||'all'}
function morphologyValues(c){const values=c.mesh.bed.slice(),layer=document.querySelector('#morphologyLayer')?.value||'original',name=morphologySelection(),item=c.morphology.candidates[name];if(layer==='candidate'&&item?.after_bed_m)return item.after_bed_m.flat();if(layer==='candidate'&&item?.height_delta_m){const delta=item.height_delta_m.flat();for(let index=0;index<values.length;index++)values[index]+=Number(delta[index]||0)}return values}
function morphologyMask(c,mask,b,s,color){if(!Array.isArray(mask))return;const rows=mask.length,columns=mask[0]?.length||0,size=s*c.morphology.terrain.spacing_m*state.zoom;for(let row=0;row<rows;row++)for(let column=0;column<columns;column++)if(mask[row][column]){const point=project([c.morphology.terrain.origin_x_m+column*c.morphology.terrain.spacing_m,0,c.morphology.terrain.origin_z_m+row*c.morphology.terrain.spacing_m],b,canvas.clientWidth,canvas.clientHeight,s);ctx.fillStyle=color;ctx.fillRect(point[0]-size/2,point[1]-size/2,size+1,size+1)}}
function morphology2d(c,w,h){const values=morphologyValues(c),b=bounds(c.mesh.vertices),s=fit(b,w,h,28),p=c.mesh.vertices.map(v=>project(v,b,w,h,s)),[lo,hi]=range(values),size=s*c.morphology.terrain.spacing_m*state.zoom;for(let index=0;index<p.length;index++)if(c.morphology.terrain.valid_mask.flat()[index]&&state.layers.bed){ctx.fillStyle=colorRamp(values[index],lo,hi);ctx.fillRect(p[index][0]-size/2,p[index][1]-size/2,size+1,size+1)}const name=morphologySelection(),item=c.morphology.candidates[name];if(item){morphologyMask(c,item.deposit_mask||item.bar_mask||item.footprint||item.inundation_mask,b,s,name==='floodplain'?'#63b7d377':name==='bank'?'#d76f6f99':'#e6b85e99');if(item.erosion_mask)morphologyMask(c,item.erosion_mask,b,s,'#d76f6f99');if(item.shortcut_xz_m)drawLine(item.shortcut_xz_m.map(point=>project([point[0],0,point[1]],b,w,h,s)),'#b7e4bb',3);if(item.loop_xz_m)drawLine(item.loop_xz_m.map(point=>project([point[0],0,point[1]],b,w,h,s)),'#d67c6d',2);if(item.distributary_candidates)for(const path of item.distributary_candidates)drawLine(path.polyline.map(cell=>project([c.morphology.terrain.origin_x_m+cell[1]*c.morphology.terrain.spacing_m,0,c.morphology.terrain.origin_z_m+cell[0]*c.morphology.terrain.spacing_m],b,w,h,s)),'#f0cf83',2)}ctx.fillStyle='#e6dbc0';ctx.font='11px sans-serif';ctx.fillText(`真实TD局部候选 · ${name==='all'?'全部形态':name} · 原始来源不变`,14,20);return {b,s,p,bed:p,morphology:true}}
function morphology3d(c,w,h){const plot=mesh3d(c.mesh.vertices,c.mesh.triangles,morphologyValues(c),w,h),name=morphologySelection(),item=c.morphology.candidates[name],drawPoints=points=>{if(Array.isArray(points))drawLine(points.map(point=>plot.camera.projection([point[0],morphologyLineHeight(c,point),point[1]])),'#f0cf83',2)};if(item?.shortcut_xz_m)drawPoints(item.shortcut_xz_m);if(item?.loop_xz_m)drawPoints(item.loop_xz_m);if(item?.distributary_candidates)for(const path of item.distributary_candidates)drawPoints(path.polyline.map(cell=>[c.morphology.terrain.origin_x_m+cell[1]*c.morphology.terrain.spacing_m,c.morphology.terrain.origin_z_m+cell[0]*c.morphology.terrain.spacing_m]));ctx.fillStyle='#e6dbc0';ctx.font='11px sans-serif';ctx.fillText(`真实TD局部候选 · ${name==='all'?'全部形态':name} · 未写回主河网`,14,20);return plot}
function morphologyLineHeight(c,point){
    if(!c.morphology.stage_review)return 0;
    const terrain=c.morphology.terrain,rows=terrain.height_m.length,columns=terrain.height_m[0].length;
    const row=clamp(Math.round((point[1]-terrain.origin_z_m)/terrain.spacing_m),0,rows-1);
    const column=clamp(Math.round((point[0]-terrain.origin_x_m)/terrain.spacing_m),0,columns-1);
    return morphologyValues(c)[row*columns+column];
}
function globalGeometry2d(c,w,h){
    const g=c.global.global_geometry,accepted=g.accepted_edge_points_xz_m,refused=g.refused_edge_points_xz_m,t=c.global.terrain;
    const b=[t.x_m[0],t.x_m.at(-1),t.z_m[0],t.z_m.at(-1)],s=fit(b,w,h,24),[lo,hi]=range(t.height_m.flat());
    const projection=p=>project([p[0],0,p[1]],b,w,h,s);
    for(let row=0;row<t.z_m.length-1;row++)for(let col=0;col<t.x_m.length-1;col++){
        if(!t.valid_mask[row][col])continue;
        const a=projection([t.x_m[col],t.z_m[row]]),z=projection([t.x_m[col+1],t.z_m[row+1]]);
        ctx.fillStyle=colorRamp(t.height_m[row][col],lo,hi);ctx.fillRect(a[0],a[1],z[0]-a[0]+.5,z[1]-a[1]+.5);
    }
    if(document.querySelector('#globalAccepted').checked)accepted.forEach(edge=>drawLine(edge.map(projection),'#a3b36c',1.8));
    if(document.querySelector('#globalExcluded').checked)refused.forEach(edge=>drawLine(edge.map(projection),'#e0574a',3));
    const selected=document.querySelector('#globalEdge').value;
    if(selected!==''){
        const edge=refused[Number(selected)].map(projection);
        drawLine(edge,'#ffffff',4);ctx.strokeStyle='#ffffff';ctx.lineWidth=2;ctx.beginPath();ctx.arc(edge[0][0],edge[0][1],9,0,Math.PI*2);ctx.stroke();
    }
    return {b,s,p:[],globalGeometry:true};
}
function render(){
    if(state.case?.kind==='river-result'&&state.view==='3d'&&window.riverResultScene){window.riverResultScene.render(state.case.results,window.riverResults.mode(),state.vertical);return}
    window.riverResultScene?.close();
    if(window.faultSurface?.isActive()){window.faultSurface.render();return}
    if(!canvas.clientWidth||!canvas.clientHeight)return;
    if(!state.case){syncCanvas();ctx.fillStyle=TerraTheme.colors.stage;ctx.fillRect(0,0,canvas.clientWidth,canvas.clientHeight);state.plot=null;return}
    const started=performance.now();syncCanvas();let w=canvas.clientWidth,h=canvas.clientHeight;ctx.fillStyle=TerraTheme.colors.stage;ctx.fillRect(0,0,w,h);let c=state.case,plot;
    if(c.kind==='river-result')plot=window.riverResults.render(c,w,h,{context:ctx,state,camera3d,drawTriangle});
    else if(c.kind==='td')plot=td2d(c,w,h);
    else if(c.kind==='morphology')plot=state.view==='3d'?morphology3d(c,w,h):morphology2d(c,w,h);
    else if(c.kind==='global-geometry')plot=globalGeometry2d(c,w,h);
    else if(c.kind==='mesh'&&c.mesh.reference){
        const m=c.mesh,show=state.layers.h0?m.reference:m.vertices,values=show.map(v=>v[1]);
        plot=state.view==='3d'?mesh3d(show,m.triangles,values,w,h):mesh2d({...m,vertices:show,bed:values,h0:values},w,h);
        const projected=plot.p;if(state.layers.domains&&m.protected?.length){ctx.fillStyle='#e3a63caa';for(let i=0;i<m.protected.length;i++)if(m.protected[i]&&projected[i]){const p=projected[i];ctx.fillRect(p[0]-1.3,p[1]-1.3,2.6,2.6)}}
        if(state.layers.displacement&&m.displacement?.length){ctx.strokeStyle='#f1d9a6';ctx.lineWidth=1;for(let i=0;i<m.displacement.length;i+=Math.max(1,Math.ceil(m.displacement.length/380))){const v=m.displacement[i];if(!v||Math.hypot(...v)<.05)continue;const start=plot.camera?plot.camera.projection(m.reference[i]):projected[i],end=plot.camera?plot.camera.projection(m.vertices[i]):projected[i];if(start&&end){ctx.beginPath();ctx.moveTo(start[0],start[1]);ctx.lineTo(end[0],end[1]);ctx.stroke()}}}
    }
    else if(c.kind==='mesh'){
        plot=state.view==='3d'?mesh3d(c.mesh.vertices,c.mesh.triangles,c.mesh.bed,w,h,c.mesh.water,c.mesh.wet,c.mesh.h0):mesh2d(c.mesh,w,h);
        if(state.view==='3d')drawMeshOverlays(c.mesh,plot.p,plot.camera.projection);
    }else if(c.kind==='engineering'){
        const vertices=[...c.mesh.vertices,...c.outlets.flatMap(outlet=>outlet.mesh.bedVertices)],heights=[...c.mesh.bed,...c.outlets.flatMap(outlet=>outlet.mesh.bedVertices.map(point=>point[1]))],b=bounds(vertices),s=fit(b,w,h,50),camera=state.view==='3d'?camera3d(vertices,heights,w,h):{b,s,projection:point=>project(point,b,w,h,s)};
        if(state.view==='3d'){
            plot=mesh3d(c.mesh.vertices,c.mesh.triangles,c.mesh.bed,w,h,c.mesh.water,c.mesh.wet,c.mesh.h0,camera,true,c.mesh.wetCells);
            for(const outlet of c.outlets){const mesh=outlet.mesh,strip=mesh3d(mesh.bedVertices,mesh.triangles,mesh.bedVertices.map(point=>point[1]),w,h,mesh.waterVertices.map(point=>point[1]),null,null,camera,true);plot.faces.push(...strip.faces);plot.waterFaceCount+=strip.waterFaceCount}
            drawFaces(plot.faces);
        }else{
            const p=c.mesh.vertices.map(camera.projection),show=state.layers.h0?c.mesh.h0:c.mesh.bed,[lo,hi]=range(show);if(state.layers.h0||state.layers.bed)for(const triangle of c.mesh.triangles)drawTriangle(triangle.map(index=>p[index]),colorRamp(show[triangle[0]],lo,hi));if(state.layers.water)for(let index=0;index<c.mesh.triangles.length;index++){const triangle=c.mesh.triangles[index];if(c.mesh.wetCells[Math.floor(index/2)])drawTriangle(triangle.map(index=>p[index]),"#4aa3b08c")}plot={b,s,p,camera,triangles:c.mesh.triangles};
            for(const outlet of c.outlets){const mesh=outlet.mesh,bed=mesh.bedVertices.map(camera.projection),water=mesh.waterVertices.map(camera.projection);for(const triangle of mesh.triangles){if(state.layers.bed)drawTriangle(triangle.map(index=>bed[index]),"#b08a5c");if(state.layers.water)drawTriangle(triangle.map(index=>water[index]),"#4aa3b08c")}}
        }
        drawMeshOverlays(c.mesh,plot.p,camera.projection);plot.outletPlots=c.outlets.map(outlet=>({p:(state.layers.water?outlet.mesh.waterVertices:outlet.mesh.bedVertices).map(camera.projection)}));for(const outlet of c.outlets)drawLine(outlet.mesh.centerline.map(camera.projection),"#f1c36a",2);
        const oldWater=state.layers.water;state.layers.water=state.layers.graphStage!==false;plot.graphPlot=dynamic2d(c,w,h,camera);state.layers.water=oldWater;plot.graphOverlaySemantics="diagnostic graph annotation; does not represent a fine-grid instantaneous water surface";
    }else if(c.kind==='coast'){plot=state.view==='3d'?mesh3d(c.mesh.bedVertices,c.mesh.triangles,c.mesh.bedVertices.map(v=>v[1]),w,h,c.mesh.waterVertices.map(v=>v[1])):coast2d(c.mesh,w,h);if(state.view==='3d')drawLine(c.mesh.centerline.map(plot.camera.projection),"#f1c36a",2)}
    else if(c.kind==='dem')plot=state.view==='3d'?dem3d(c,w,h):dem2d(c,w,h);
    else if(c.kind==='legacy')plot=state.view==='3d'?legacy3d(c,w,h):legacy2d(c,w,h);
    else plot=dynamic2d(c,w,h);
    state.plot=plot;ctx.fillStyle="#cfc3a8";ctx.font="11px sans-serif";ctx.fillText(state.view==='3d'?`${c.kind==='legacy'?'历史方块坐标':'XYZ m'} · ${state.vertical.toFixed(2)}x`:'XZ',14,h-16);state.lastRenderMs=performance.now()-started;
}
canvas.addEventListener('contextmenu',event=>event.preventDefault());
canvas.addEventListener('pointerdown',event=>{
    if(event.button!==0&&event.button!==2)return;
    state.drag=true;state.moved=false;state.dragButton=event.button;
    state.startX=state.lastX=event.offsetX;state.startY=state.lastY=event.offsetY;
    canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointerup',()=>state.drag=false);
canvas.addEventListener('pointercancel',()=>state.drag=false);
canvas.addEventListener('pointermove',event=>{
    if(!state.drag)return;
    const dx=event.offsetX-state.lastX,dy=event.offsetY-state.lastY;
    state.moved=state.moved||Math.hypot(event.offsetX-state.startX,event.offsetY-state.startY)>4;
    if(state.view==='3d'&&state.dragButton===0){
        const radiansPerPixel=2*Math.PI/Math.max(canvas.clientHeight,1);
        state.yaw+=dx*radiansPerPixel;state.pitch=clamp(state.pitch-dy*radiansPerPixel,-Math.PI/2+.01,Math.PI/2-.01);
    }
    else{state.panX+=dx;state.panY+=dy}
    state.lastX=event.offsetX;state.lastY=event.offsetY;render();
});
canvas.addEventListener('wheel',event=>{event.preventDefault();state.zoom=clamp(state.zoom*Math.exp(-event.deltaY*.001),.2,8);render()},{passive:false});
window.surfaceRenderer={state,resize,render,flowInterval,range,resetCamera(){if(window.faultSurface?.isActive()){window.faultSurface.resetCamera();return}state.yaw=-.55;state.pitch=.65;state.zoom=1;state.panX=0;state.panY=0;render()}};
new ResizeObserver(resize).observe(canvas);
resize();
