/* Saved geometry only. Cut colours are metres; M6 millimetres are charted separately. */
(function () {
    const $ = id => document.getElementById(id);
    let result = null, mode = 'cut', section = 1, time = 0, loadSerial = 0;
    const sedimentCanvas=document.createElement('canvas');sedimentCanvas.id='sedimentChart';sedimentCanvas.className='hidden';sedimentCanvas.style.width='100%';$('chartSection').append(sedimentCanvas);
    const caption=document.createElement('p');caption.id='resultCaption';caption.className='muted hidden';caption.style.cssText='margin:0;padding:8px 20px';document.querySelector('.stage-head').after(caption);
    const extrema = a => a.reduce((r, v) => [Math.min(r[0], v), Math.max(r[1], v)], [Infinity, -Infinity]);
    function line(ctx, values, color, box, limits) {
        const [x,y,w,h] = box, [lo,hi] = limits;
        ctx.beginPath(); values.forEach((v,i) => {const p=[x+i/(values.length-1)*w,y+h-(v-lo)/(hi-lo||1)*h];i?ctx.lineTo(...p):ctx.moveTo(...p)});
        ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();
    }
    function chart() {
        if (!result) return;
        const canvas=$('chart'),ctx=canvas.getContext('2d');canvas.width=Math.max(240,canvas.clientWidth);canvas.height=230;
        ctx.clearRect(0,0,canvas.width,canvas.height);ctx.font='11px sans-serif';ctx.fillStyle='#cfc3a8';
        const s=result.sections[Math.min(section,result.sections.length-1)];
        const datum=s.original_m[Math.floor(s.original_m.length/2)], original=s.original_m.map(v=>v-datum),bed=s.bed_m.map(v=>v-datum);
        const limits=extrema(original.concat(bed));limits[0]-=.035;limits[1]+=.035;
        line(ctx,original,'#d9c294',[26,32,canvas.width-48,118],limits);line(ctx,bed,'#58b4a8',[26,32,canvas.width-48,118],limits);
        ctx.fillText(`${s.label} · 相对中心原床 ${datum.toFixed(3)} m`,8,16);
        ctx.fillText(`${limits[1].toFixed(3)} m`,0,31);ctx.fillText(`${limits[0].toFixed(3)} m`,0,164);
        ctx.fillText(`横向 ${s.offset_m[0].toFixed(2)} 至 ${s.offset_m.at(-1).toFixed(2)} m`,24,182);
        ctx.fillStyle='#d9c294';ctx.fillText('原床',24,207);ctx.fillStyle='#58b4a8';ctx.fillText('加工床 · 真实三角网插值',78,207);
        $('selectionTitle').textContent=s.label;
        $('selection').textContent=`切深最大 ${Math.max(...s.original_m.map((v,i)=>v-s.bed_m[i])).toFixed(4)} m\n断面中心 X/Z ${s.center_xz_m.map(v=>v.toFixed(2)).join(' / ')} m\n原床与加工床使用相同基准；无纵向去趋势。`;
        if(result.sediment) {
            const s=result.sediment;
            const delta=s.bed_delta_mm[time];
            $('resultTimeLabel').textContent=`t = ${s.time_seconds[time]} s · 床变 ${delta.map(v=>v.toFixed(6)).join(' / ')} mm`;
            $('ledger').textContent=`物理时间 ${s.time_seconds[time]} s\n床变 ${delta.map(v=>v.toFixed(6)).join(' / ')} mm\n累计侵蚀松散固体 ${s.eroded_solid_m3[time].toFixed(9)} m³\n累计侵蚀岩石 ${s.eroded_rock_m3[time].toFixed(9)} m³\n过程累计沉积固体 ${s.deposited_solid_m3[time].toFixed(9)} m³\n累计出口固体 ${s.exported_solid_m3[time].toFixed(9)} m³\n累计沉积含再搬运，并非净增床。`;
            const c=$('sedimentChart'),cx=c.getContext('2d');c.width=Math.max(240,c.clientWidth);c.height=150;cx.clearRect(0,0,c.width,c.height);cx.fillStyle='#cfc3a8';cx.font='11px sans-serif';
            cx.fillText('保存节点床变 · mm（独立纵轴，未放大网格）',5,14);
            const limits=extrema(s.bed_delta_mm.flat());limits[0]=Math.min(0,limits[0]);limits[1]=Math.max(.000001,limits[1]);
            ['#58b4a8','#e3a63c','#cf6b4b','#a3b36c'].forEach((color,i)=>line(cx,s.bed_delta_mm.map(v=>v[i]),color,[25,26,c.width-50,89],limits));
            cx.fillText(`${limits[0].toFixed(6)} … ${limits[1].toFixed(6)} mm / 0–${s.time_seconds.at(-1)} s`,5,140);
        }
    }
    function render(c,w,h,helpers) {
        const {context:ctx,state,camera3d,drawTriangle}=helpers,m=c.results.mesh;
        const heights=mode==='original'?m.original_m:m.bed_m;
        const vertices=m.xz.map((p,i)=>[p[0],heights[i],p[1]]);
        const b=c.results.source.bounds_xz_m, center=[(b[0][0]+b[1][0])/2,(b[0][1]+b[1][1])/2],longZ=b[1][1]-b[0][1]>=b[1][0]-b[0][0];
        // Rotate the narrow reach along the wide canvas without stretching horizontal units.
        const context=c.results.context,contextVertices=context.xz.map((p,i)=>[p[0],context.original_m[i],p[1]]);
        const projection=state.view==='3d'?camera3d(contextVertices,context.original_m,w,h).projection:p=>{
            const scale=Math.min((w-90)/(longZ?b[1][1]-b[0][1]:b[1][0]-b[0][0]),(h-120)/(longZ?b[1][0]-b[0][0]:b[1][1]-b[0][1]))*state.zoom;
            return [w/2+(longZ?p[2]-center[1]:p[0]-center[0])*scale+state.panX,h/2+(longZ?p[0]-center[0]:p[2]-center[1])*scale+state.panY,0];
        };
        const points=vertices.map(projection),cutMax=extrema(m.cut_m)[1],heightRange=extrema(heights);
        const faces=m.triangles.map(t=>({t,depth:t.reduce((s,i)=>s+points[i][2],0)}));
        if(state.view==='3d'){
            const cp=contextVertices.map(projection),range=extrema(context.original_m);
            for(const t of context.triangles){const v=(t.reduce((s,i)=>s+context.original_m[i],0)/3-range[0])/(range[1]-range[0]||1);faces.push({contextPoints:t.map(i=>cp[i]),depth:t.reduce((s,i)=>s+cp[i][2],0),color:TerraTheme.relief(v*.8)})}
        }
        faces.sort((a,b)=>b.depth-a.depth);
        for(const {t,contextPoints,color:contextColor} of faces) {
            if(contextPoints){drawTriangle(contextPoints,contextColor);continue}
            const cut=t.reduce((s,i)=>s+m.cut_m[i],0)/3,tone=(t.reduce((s,i)=>s+heights[i],0)/3-heightRange[0])/(heightRange[1]-heightRange[0]||1);
            let color=TerraTheme.relief(tone*.8);
            if(mode==='cut'||(mode==='bed'&&cut>0)) {color=TerraTheme.cut(cut/(cutMax||1))}
            drawTriangle(t.map(i=>points[i]),color);
        }
        if(state.view==='2d'){
            const s=c.results.sections[Math.min(section,c.results.sections.length-1)];
            ctx.beginPath();s.endpoints_xz_m.forEach((p,i)=>{const q=projection([p[0],0,p[1]]);i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1])});ctx.strokeStyle='#ece0c4';ctx.lineWidth=2;ctx.stroke();
            if(c.results.comparison){
                for(const [nodes,color] of [[c.results.original_nodes_xz_m,'#cf6b4b'],[c.results.nodes_xz_m,'#a3b36c']])for(let i=0;i<nodes.length;i++){const target=c.results.receiver[i];if(target<0)continue;ctx.beginPath();[nodes[i],nodes[target]].forEach((p,j)=>{const q=projection([p[0],0,p[1]]);j?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1])});ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke()}
            }
        }
        const canvasText=w>500;
        if(canvasText){ctx.fillStyle='#ece0c4';ctx.font='13px sans-serif';ctx.fillText(`${c.results.label} · ${mode==='original'?'原始 TD 床面':mode==='cut'?'实际切深配色':'加工床面 / 切深配色'}`,24,28);ctx.fillStyle='#e3a63c';ctx.fillText(`切深 0–${cutMax.toFixed(3)} m · X/Z 同尺度 · 无生成水面`,24,51)}
        return {p:points,triangles:m.triangles};
    }
    async function open() {
        const serial=++loadSerial;
        clear();
        let catalog;
        try { catalog=await json('/api/river-results/catalog'); }
        catch(error){if(serial===loadSerial&&document.body.dataset.workspace==='release')showError(error);return}
        if(serial!==loadSerial||document.body.dataset.workspace!=='release')return;
        $('resultCase').replaceChildren(...catalog.cases.map(item=>{const o=document.createElement('option');o.value=item.id;o.textContent=item.label;return o}));
        if(catalog.cases.some(item=>item.id==='valley-4'))$('resultCase').value='valley-4';
        await load($('resultCase').value);
    }
    async function load(id) {
        if(document.body.dataset.workspace!=='release')return;
        const serial=++loadSerial;
        clear();
        try {
        const body=await json(`/api/river-results/case/${encodeURIComponent(id)}`);
        await import('./river-results-3d.js');
        if(serial!==loadSerial||document.body.dataset.workspace!=='release')return;
        if(!body.id||!body.identity||!body.source||!body.metadata||!body.mesh?.triangles?.length||!body.sections?.length)throw Error('保存河槽包缺少身份或几何');
        result=body;mode=$('resultLayer').value;section=Math.min(1,result.sections.length-1);time=0;
        $('resultSection').replaceChildren(...result.sections.map((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=s.label;return o}));$('resultSection').value=section;
        $('resultTimePanel').classList.toggle('hidden',!result.sediment);$('sedimentChart').classList.toggle('hidden',!result.sediment);
        $('resultTime').max=result.sediment?result.sediment.time_seconds.length-1:0;$('resultTime').value=0;
        const c={kind:'river-result',caseId:`river-result-${id}`,results:result,evidence:{status:'accepted_bounded_geometry',source:result.source,scope:'TD1024 真实米制局部河槽；保存成果只读展示'},identity:result.identity};
        window.setRiverResult(c);
        $('riverTerrainInput').value='Terrain Diffusion · 1024×1024 原始高度场';
        $('riverTerrainStatus').textContent=`局部范围 ${JSON.stringify(result.source.bounds_xz_m)} m`;
        $('resultCaption').textContent=result.comparison?'红：原路径 / 绿：加工路径。有界组件成果，全域仍623/673边。':result.sediment?'M6床变见独立mm曲线；三角网保持已验收M5几何。':'实际米制原床与加工河槽，无生成水面。';
        $('evidence').replaceChildren();
        const scope=document.createElement('p');scope.textContent='有界几何 / 冻结水量水沙回放。自然出口、水力耦合及全域发布未认证。';
        const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='查看来源、哈希与算法身份';pre.textContent=JSON.stringify({geometry:result.source,algorithm:result.metadata.algorithm,sediment:result.sediment?.source},null,2);details.append(summary,pre);$('evidence').append(scope,details);
        $('ledger').textContent=`最大切深 ${extrema(result.mesh.cut_m)[1].toFixed(4)} m\n切岩体积 ${result.metadata.cut_volume_m3.toFixed(3)} m³`+(result.comparison?`\n最大转角 ${result.comparison.before.max_turn_degrees.toFixed(3)} → ${result.comparison.after.max_turn_degrees.toFixed(3)}°\n移动节点 ${result.comparison.moved_nodes} · 最大位移 ${result.comparison.max_offset_m.toFixed(3)} m\n锚点固定 · 实际床单调\n仅本组件，全域仍623/673边`:'');
        $('stats').textContent=`${result.mesh.xz.length} 实际顶点 · ${result.mesh.triangles.length} 三角形`;
        surfaceRenderer.state.yaw=1.15;surfaceRenderer.resetCamera();surfaceRenderer.state.yaw=1.15;surfaceRenderer.render();chart();
        }catch(error){if(serial===loadSerial&&document.body.dataset.workspace==='release'){clear();showError(error)}}
    }
    function clear() {
        result=null;
        window.riverResultScene?.close();
        beginReviewRead();
        $('resultCaption').textContent='';
        $('resultTimeLabel').textContent='';
        const canvas=$('sedimentChart');
        canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);
    }
    $('resultCase').onchange=()=>{const pending=load($('resultCase').value),serial=loadSerial;pending.catch(e=>{if(serial===loadSerial&&document.body.dataset.workspace==='release')showError(e)})};
    $('resultLayer').onchange=()=>{mode=$('resultLayer').value;surfaceRenderer.render()};
    $('resultSection').onchange=()=>{section=Number($('resultSection').value);chart();surfaceRenderer.render()};
    $('resultTime').oninput=()=>{time=Number($('resultTime').value);chart()};
    window.riverResults={open,render,mode:()=>mode,close:()=>{++loadSerial;result=null;window.riverResultScene?.close()},reviewRecord:()=>result?({caseId:result.id,source:result.source,identity:result.identity,status:'saved_bounded_review',metadata:result.metadata,release:result.release,layer:mode,section,timeIndex:time,timeSeconds:result.sediment?.time_seconds[time],bedDeltaMm:result.sediment?.bed_delta_mm[time],sedimentSource:result.sediment?.source,camera:window.riverResultScene?.reviewCamera()}):null};
})();
