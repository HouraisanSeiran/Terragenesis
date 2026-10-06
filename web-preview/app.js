"use strict";
const $=id=>document.getElementById(id);
const ui=Object.fromEntries(['caseSelect','verticalScale','verticalLabel','caseStatus','caseScope','layers','timeSection','timeRange','timeStep','timeSeconds','view2d','view3d','reset','play','stepBack','stepForward','viewTitle','viewSubtitle','coords','stats','evidence','sourceRegistry','selectionTitle','selection','chart','chartSection','notes','exportReview','chartMetric','pickMode','ledger','error','loading','bridgeStatus','vdmControls','vdmForm','vdmSaved','vdmAmplitude','vdmWavelength','vdmCurvature','vdmEndDifference','vdmDirection','vdmSeed','vdmPreview','vdmStatus','faultControls','faultDirection','faultX','faultSlip','faultTransition','faultSide','faultDraft','faultStatus','tdSummary','tdCatalogText','tdStats','tdScenario','tdLayer','tdMetrics','basinControls','basinCandidates','basinLimitations'].map(id=>[id,$(id)]));
let manifest=null, catalog=null, current=null, currentEntry=null, workspace='saved', timer=null, requestSerial=0, selection=null, basinComparison=null, tdPage=null, tdDirection='eastward';
const reviewCategories={
    terrain:{label:'地形输入',projects:[{id:'terrain',label:'Terrain Diffusion · 保存高度场'},{id:'dem',label:'DEM 来源与范围 · 诊断对照'}]},
    vdm:{label:'VDM 算法',projects:[{id:'vdm',label:'岩壁形态与参数变形'},{id:'fault',label:'断层平移'}]},
    rivers:{label:'河网算法',projects:[{id:'saved',label:'单域 AMR / 原生 / uniform 对照'},{id:'mosaic',label:'共享边界与跨精度 · 保存审查'},{id:'td',label:'降雨与动态水量 · 原生小时页'},{id:'basin',label:'盆地与出口 · diagnostic 候选'},{id:'surface',label:'历史工程案例 · 有限范围'}]},
};
const rememberedProjects={terrain:'terrain',vdm:'vdm',rivers:'saved'};
function isSavedWorkspace(){return workspace==='saved'||workspace==='mosaic'}
function syncNavigation(project){
    const category=Object.keys(reviewCategories).find(key=>reviewCategories[key].projects.some(item=>item.id===project));
    if(!category)throw Error('未知审查项目');
    rememberedProjects[category]=project;
    document.querySelectorAll('[data-category]').forEach(tab=>tab.classList.toggle('active',tab.dataset.category===category));
    const select=$('reviewProject');select.replaceChildren();
    for(const item of reviewCategories[category].projects){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;select.append(option)}
    select.value=project;
}
const entries=new Map();
const bridge=location.protocol==='file:'?'http://127.0.0.1:8765':'';
const api=path=>`${bridge}${path}`;
const dynamic=c=>c&&(c.kind==='dynamic'||c.kind==='engineering');
async function json(url, options){const response=await fetch(api(url),options);const body=await response.json().catch(()=>({}));if(!response.ok)throw Error(body.error||`HTTP ${response.status}`);return body}
async function caseArtifact(url){
    const response=await fetch(api(url));if(!response.ok)throw Error(`HTTP ${response.status}`);
    const bytes=await response.arrayBuffer(),digest=await crypto.subtle.digest('SHA-256',bytes);
    const sha256=Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');
    return {body:JSON.parse(new TextDecoder().decode(bytes)),record:{path:'web-preview'+url,sha256,bytes:bytes.byteLength}};
}
function showError(error){ui.error.textContent=error?.message||String(error);ui.error.classList.remove('hidden');stop()}
function clearError(){ui.error.textContent='';ui.error.classList.add('hidden')}
function stop(){if(timer!==null)clearInterval(timer);timer=null;if(ui.play)ui.play.textContent='播放'}
function clearSelection(){selection=null;ui.selectionTitle.textContent='尚未选取';ui.selection.textContent='在地图点选节点、网格或动态边';ui.coords.textContent='未选取';if(ui.chart){ui.chart.getContext('2d').clearRect(0,0,ui.chart.width,ui.chart.height)}}
function statusLabel(status){const value=String(status||'pending');if(value.startsWith('accepted'))return 'accepted 有界证据';if(value.startsWith('diagnostic'))return 'diagnostic 候选';if(value.includes('not_implemented')||value.includes('backend-pending'))return 'not_implemented 尚未实现';if(value.includes('draft'))return 'draft 草案';return 'pending / 未验收'}
function sourceEntry(source){if(!source)return null;return typeof source==='string'?{path:source}:source}
function renderSourceRegistry(){if(!ui.sourceRegistry)return;ui.sourceRegistry.replaceChildren();const groups=[['VDM 形态 gallery',catalog?.generatedFrom?.[1]],['TD 固定时间页',catalog?.td?.sources?.[1]],['原生水面快照',catalog?.td?.sources?.[2]],['河谷路径候选',catalog?.td?.sources?.[3]],['盆地候选对比',catalog?.basin?.source]];groups.forEach(([label,source])=>{const entry=sourceEntry(source);if(entry)textLine(ui.sourceRegistry,label,`${entry.path||'—'} · ${(entry.sha256||'').slice(0,12)}…`)})}
function renderBasinComparison(){if(!ui.basinCandidates)return;ui.basinCandidates.replaceChildren();const comparison=basinComparison?.comparison||{},treatments=comparison.treatments||[];treatments.forEach(item=>{const row=document.createElement('div');row.className='candidate-row';const title=document.createElement('strong');title.textContent=item.label||item.candidate_id;const meta=document.createElement('span');meta.textContent=`${statusLabel(item.publishable?'accepted':'diagnostic_candidate')} · Δ ${Number(item.max_abs_delta_m||0).toFixed(4)} m · disturbance ${Number(item.disturbance_m3||0).toFixed(0)} m³`;row.append(title,meta);const reason=(item.rejection_reasons||[]).join('；');if(reason){const detail=document.createElement('small');detail.textContent=`未通过：${reason}`;row.append(detail)}ui.basinCandidates.append(row)});ui.basinLimitations.textContent=(comparison.limitations||[]).concat(comparison.decision?.reason||[]).join(' · ')||'自然海口未认证；水力耦合未完成'}
function textLine(parent,label,value){const line=document.createElement('div');line.textContent=`${label}：${value??'—'}`;parent.append(line)}
function evidence(c){ui.evidence.replaceChildren();const e=c?.evidence||c?.source||{};textLine(ui.evidence,'状态',statusLabel(e.status||c?.status));textLine(ui.evidence,'范围',e.scope||c?.metadata?.algorithm||'保存数据／显式局部预览');if(e.source)textLine(ui.evidence,'源',e.source.path||e.source.storage?.path);if(e.sha256||e.source?.sha256||e.source?.storage?.sha256)textLine(ui.evidence,'SHA256',e.sha256||e.source.sha256||e.source.storage.sha256);if(c?.identity)textLine(ui.evidence,'identity',c.identity);(e.limitations||catalog?.limitations||[]).slice(0,6).forEach((x,i)=>textLine(ui.evidence,i?'限制':'边界',x))}
function layerControls(c){ui.layers.replaceChildren();const names=c?.kind==='mesh'?[['h0','参考面 H0'],['bed','VDM 床面'],['water','水面（若保存）'],['wet','湿润单元'],['domains','保护／域边界'],['footprint','来源 footprint']]:[['bed','床面'],['water','水面'],['wet','湿润层'],['edges','河网边'],['unknown','unknown／孔洞'],['footprint','来源 footprint']];if(c?.mesh?.reference)names.push(['displacement','VDM 位移向量']);for(const [key,label] of names){const wrap=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.dataset.layer=key;input.checked=!!surfaceRenderer.state.layers[key];input.onchange=()=>{surfaceRenderer.state.layers[key]=input.checked;surfaceRenderer.render()};wrap.append(input,label);ui.layers.append(wrap)}}
function normalizeMeshCase(payload){const m=payload.mesh||{},vertices=m.vertices||[],reference=m.reference||vertices,delta=m.displacement||vertices.map(()=>[0,0,0]);return {kind:'mesh',caseId:`vdm-${payload.kind||payload.form?.kind||'preview'}`,label:payload.label||payload.form?.kind||'VDM preview',mesh:{vertices,reference,displacement:delta,protected:m.protected||[],sourceChart:m.sourceChart||{},triangles:m.triangles||[],bed:vertices.map(v=>Number(v[1])),h0:reference.map(v=>Number(v[1])),wetCells:[],cellOwner:[],hydrologicOwner:[],cells:[],columns:0,water:[],wet:[]},evidence:{status:payload.schema==='vdm-case-v1'?'diagnostic_saved_geometry':'pending_geometry_preview',scope:'XYZ metric VDM; contiguous local chart for display; source topology remapped without interpolation; no generated water',source:payload.source,limitations:payload.report?.limitations||catalog?.limitations||[]},identity:payload.identity,variant:payload.variant,metadata:payload.metadata,report:payload.report}}
function populateSelect(){
    ui.caseSelect.replaceChildren();
    if(workspace==='terrain'){
        for(const entry of window._legacyManifest||[]){const option=document.createElement('option');option.value='legacy:'+entry.file;option.textContent=entry.name;ui.caseSelect.append(option)}
    }else{
        for(const entry of manifest?.cases||[]){
            entries.set(entry.file,entry);
            if((entry.caseId==='dem-candidate')!==(workspace==='dem'))continue;
            const option=document.createElement('option');option.value=entry.file;
            option.textContent=`${entry.label||entry.caseId} · ${statusLabel(entry.status)}`;ui.caseSelect.append(option);
        }
    }
}
function setWorkspace(next){
    syncNavigation(next);
    ++requestSerial;stop();window.savedSurface?.close();window.faultSurface?.close();workspace=next;
    ui.exportReview.disabled=true;
    clearSelection();clearError();current=null;currentEntry=null;surfaceRenderer.state.case=null;surfaceRenderer.state.time=0;
    ui.stats.textContent='';ui.ledger.textContent='';ui.evidence.replaceChildren();ui.layers.replaceChildren();renderSourceRegistry();
    ui.loading.classList.add('hidden');surfaceRenderer.render();
    ui.vdmControls.classList.toggle('hidden',next!=='vdm');ui.faultControls.classList.toggle('hidden',next!=='fault');
    ui.tdSummary.classList.toggle('hidden',next!=='td');ui.basinControls.classList.toggle('hidden',next!=='basin');
    const cases=next==='surface'||next==='terrain'||next==='dem';
    document.querySelector('.surface-controls').classList.toggle('hidden',!cases);
    $('terrainVariantControls').classList.toggle('hidden',next!=='terrain');
    $('savedControls').classList.toggle('hidden',!isSavedWorkspace());
    ui.timeSection.classList.toggle('hidden',next!=='td'&&!isSavedWorkspace());
    ui.chartSection.classList.toggle('hidden',next!=='surface');
    const empty=next==='basin';
    ui.view3d.disabled=next==='td'||empty;ui.view2d.disabled=empty;ui.reset.disabled=empty;ui.pickMode.disabled=empty||isSavedWorkspace();
    ui.verticalScale.disabled=empty||next==='td';
    if(next==='td'&&surfaceRenderer.state.view==='3d')ui.view2d.click();
    if(isSavedWorkspace()){
        if(!window.savedSurface){showError(Error('三维查看器尚未就绪'));return}
        window.savedSurface.open({mosaic:next==='mosaic'}).catch(showError);
    }else if(next==='vdm'){
        ui.viewTitle.textContent='VDM 算法 · 岩壁';ui.viewSubtitle.textContent='保存形态与参数变形';
        loadVdmGallery().then(()=>{if(workspace==='vdm')return loadVdmCase()}).catch(showError);
    }else if(next==='td'){
        ui.viewTitle.textContent='河网算法 · 降雨与动态水量';ui.viewSubtitle.textContent='固定 v10 保存时间页';
        showTdSummary();ui.timeRange.max='24';loadTdPage(0);
    }else if(next==='basin'){
        ui.viewTitle.textContent='河网算法 · 盆地与出口';ui.viewSubtitle.textContent='diagnostic · 自然海口未认证';
        renderBasinComparison();
        if(basinComparison?.source){
            current={caseId:'basin-treatment-comparison',kind:'evidence-only',evidence:{status:'diagnostic_candidate',source:basinComparison.source},comparison:basinComparison.comparison};
            evidence(current);ui.exportReview.disabled=false;
        }
        ui.ledger.textContent=JSON.stringify(basinComparison?.comparison||{},null,2);
    }else if(next==='fault'){
        ui.viewTitle.textContent='VDM 算法 · 断层平移';ui.viewSubtitle.textContent='读取真实断层局部网格';
        ui.pickMode.disabled=true;
        loadFaultCase();
    }else{
        ui.viewTitle.textContent=next==='terrain'?'地形输入 · Terrain Diffusion':next==='dem'?'地形输入 · DEM 诊断':'河网算法 · 历史工程案例';
        populateSelect();if(ui.caseSelect.value)loadCase(ui.caseSelect.value);else showError(Error('当前分类没有保存案例'));
    }
}
async function loadVdmGallery(){if(ui.vdmForm.options.length)return;const gallery=catalog?.vdm?.forms;if(!gallery)return;for(const item of gallery.variants||[]){const option=document.createElement('option');option.value=item.kind;option.textContent=item.label||item.kind;ui.vdmForm.append(option)}}
async function loadVdmCase(){const serial=++requestSerial;clearError();ui.exportReview.disabled=true;try{const payload=await json(`/api/vdm/case/${encodeURIComponent(ui.vdmForm.value||'layered_ledge')}`);if(serial!==requestSerial||workspace!=='vdm')return;current=normalizeMeshCase(payload);currentEntry=null;surfaceRenderer.state.case=current;surfaceRenderer.state.caseId=current.caseId;surfaceRenderer.state.time=0;clearSelection();layerControls(current);evidence(current);ui.viewTitle.textContent='VDM 算法 · 岩壁';ui.viewSubtitle.textContent=`${current.label} · 固定保存网格`;ui.stats.textContent=`${current.mesh.vertices.length} vertices · ${current.mesh.triangles.length} triangles · protected ${current.mesh.protected.filter(Boolean).length}`;ui.vdmStatus.textContent=`已读取固定形态 · identity ${String(payload.identity||'').slice(0,16)}…`;ui.exportReview.disabled=false;surfaceRenderer.resetCamera?.();surfaceRenderer.render()}catch(error){if(serial!==requestSerial)return;ui.vdmStatus.textContent='保存形态读取失败；没有回退到假资料';showError(error)}}
async function loadBasinComparison(){try{basinComparison=await json('/api/basin/comparison');renderBasinComparison()}catch(error){ui.basinLimitations.textContent=`固定盆地证据读取失败：${error.message}`}}
async function previewVdm(){clearError();const serial=++requestSerial;ui.exportReview.disabled=true;ui.vdmStatus.textContent='正在请求显式局部几何预览…';try{const form={kind:ui.vdmForm.value||'layered_ledge',amplitude_m:Number(ui.vdmAmplitude.value),wavelength_m:Number(ui.vdmWavelength.value),surface_curvature_m:Number(ui.vdmCurvature.value),end_elevation_difference_m:Number(ui.vdmEndDifference.value),seed:Number(ui.vdmSeed.value)};if(ui.vdmDirection.value.trim()!=='')form.extension_direction_degrees=Number(ui.vdmDirection.value);const payload=await json('/api/vdm/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({form})});if(serial!==requestSerial||workspace!=='vdm')return;current=normalizeMeshCase(payload);currentEntry=null;surfaceRenderer.state.case=current;surfaceRenderer.state.caseId=current.caseId;surfaceRenderer.state.time=0;clearSelection();layerControls(current);evidence(current);ui.vdmStatus.textContent=`预览完成 · identity ${String(payload.identity||'').slice(0,16)}…`;ui.stats.textContent=`${current.mesh.vertices.length} vertices · ${current.mesh.triangles.length} triangles`;ui.exportReview.disabled=false;surfaceRenderer.resetCamera?.();surfaceRenderer.render()}catch(error){if(serial!==requestSerial||workspace!=='vdm')return;ui.vdmStatus.textContent='预览失败；没有回退到假资料';showError(error)}}
async function loadCase(file){
    const serial=++requestSerial;stop();clearSelection();clearError();ui.exportReview.disabled=true;ui.loading.classList.remove('hidden');
    try{
        let candidate,artifact;
        if(file.startsWith('legacy:')){
            artifact=await caseArtifact('/data/'+file.slice(7));candidate=artifact.body;candidate.kind='legacy';candidate.legacyMode=$('terrainVariant').value;
            candidate.caseId='legacy-'+candidate.name;
            candidate.evidence={status:'legacy_saved_sample',scope:'原始 TD 高度场 / 历史派生对照；方块坐标',source:{...artifact.record,scope:'saved_preview_only'},limitations:['历史显示抽样，不是现实 DEM 认证','与米制 VDM / 动态水力包独立']};
        }else{
            artifact=await caseArtifact('/data/surface-review-v1/'+file);candidate=artifact.body;
            const expected=entries.get(file)?.sha256;if(expected&&artifact.record.sha256!==expected)throw Error('审查案例 SHA256 与 manifest 不匹配');
        }
        if(serial!==requestSerial)return;
        current=candidate;current.renderArtifact=artifact.record;currentEntry=entries.get(file);surfaceRenderer.state.case=current;surfaceRenderer.state.caseId=current.caseId;surfaceRenderer.state.time=0;
        layerControls(current);evidence(current);ui.caseStatus.textContent=statusLabel(current.evidence?.status||currentEntry?.status);
        ui.caseScope.textContent=current.evidence?.scope||'';ui.viewSubtitle.textContent=current.label||current.caseId;
        ui.timeSection.classList.toggle('hidden',!dynamic(current));
        if(dynamic(current)){
            const count=Math.max(0,(current.timeseries?.timeSeconds||[]).length-1);ui.timeRange.max=String(count);ui.timeRange.value='0';
            ui.timeStep.textContent=`0 / ${count}`;ui.timeSeconds.textContent=`t = ${current.timeseries?.timeSeconds?.[0]??0} s`;
            ui.ledger.textContent=JSON.stringify(current.ledger||current.timeseries?.ledger||{},null,2);
        }else ui.ledger.textContent=JSON.stringify(current.metadata||current.report||{},null,2);
        ui.exportReview.disabled=false;surfaceRenderer.resetCamera?.();surfaceRenderer.render();drawChart();
    }catch(error){if(serial===requestSerial)showError(error)}finally{if(serial===requestSerial)ui.loading.classList.add('hidden')}
}
function drawChart(){const ctx=ui.chart?.getContext('2d');if(!ctx)return;ctx.clearRect(0,0,ui.chart.width,ui.chart.height);if(!current)return;const ts=current.timeseries;if(!ts)return;const metric=ui.chartMetric.value;let values=metric==='storage'?ts.storages:metric==='q'?ts.signedEdgeQ?.map(row=>row.reduce((a,b)=>a+b,0)):ts.stages?.map(row=>row[0]);if(!values?.length)return;const flat=values.map(v=>Array.isArray(v)?v.reduce((a,b)=>a+b,0):Number(v));const lo=Math.min(...flat),hi=Math.max(...flat),pad=18;ctx.strokeStyle='#89caa0';ctx.lineWidth=2;ctx.beginPath();flat.forEach((v,i)=>{const x=pad+(ui.chart.width-pad*2)*i/Math.max(1,flat.length-1),y=ui.chart.height-pad-(ui.chart.height-pad*2)*(v-lo)/(hi-lo||1);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.fillStyle='#9ab7a2';ctx.font='10px sans-serif';ctx.fillText(`${metric}  ${lo.toFixed(3)} … ${hi.toFixed(3)}`,pad,12)}
function chartSeries(c){
 if(!c||c.kind!=='engineering'||!selection||selection.type!=='outletNode')return {x:[],y:[]};
 const points=c.outlets[selection.outletIndex]?.mesh?.centerline||[];
 const origin=points[0]?.[2]??0;
 return {x:points.map(point=>point[2]-origin),y:points.map(point=>point[1])};
}
function setTime(index){if(isSavedWorkspace()){window.savedSurface?.setTime(index).catch(showError);return}if(workspace==='td'){loadTdPage(index);return}if(!dynamic(current))return;const max=Number(ui.timeRange.max);const i=Math.max(0,Math.min(max,index));surfaceRenderer.state.time=i;ui.timeRange.value=String(i);ui.timeStep.textContent=`${i} / ${max}`;ui.timeSeconds.textContent=`t = ${current.timeseries.timeSeconds?.[i]??'—'} s`;surfaceRenderer.render();drawChart()}
function reviewSource(){
    if(!current)return null;
    const sources=current.evidence?.source||current.source||{};
    const primary=sources.path?sources:sources.vdm||sources.storage||sources;
    return {...primary,identity:current.identity||sources.identity||current.evidence?.artifactIdentity||null,
        dependencies:sources,render_artifact:current.renderArtifact||null};
}
function exportReview(){
    if(ui.exportReview.disabled)return;
    const loaded=reviewRecord();if(!loaded?.caseId){showError(Error('没有可导出的当前审查结果'));return}
    const record={...loaded,notes:ui.notes.value,exportedAt:new Date().toISOString()};
    const blob=new Blob([JSON.stringify(record,null,2)],{type:'application/json'}),link=document.createElement('a');
    link.href=URL.createObjectURL(blob);link.download=`${record.caseId}-review.json`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),500);
}
function faultParameters(){return {plane_origin_xz_m:[Number(ui.faultX.value),Number($('faultZ').value)],strike_degrees:Number(ui.faultDirection.value),slip_m:Number(ui.faultSlip.value),moving_side:ui.faultSide.value,transition_width_m:Number(ui.faultTransition.value)}}
function applyFaultDefaults(defaults){
    ui.faultX.value=defaults.plane_origin_xz_m[0];$('faultZ').value=defaults.plane_origin_xz_m[1];
    ui.faultDirection.value=defaults.strike_degrees;ui.faultSlip.value=defaults.slip_m;
    ui.faultSide.value=defaults.moving_side;ui.faultTransition.value=defaults.transition_width_m;
}
async function loadFaultCase(preview=false){
    if(workspace!=='fault')return;
    const serial=++requestSerial;clearError();clearSelection();current=null;ui.exportReview.disabled=true;
    ui.faultStatus.textContent=preview?'正在生成显式预览；旧结果未应用':'正在读取保存断层…';
    ui.loading.classList.remove('hidden');window.faultSurface?.clear();
    try{
        await import('./fault-surface.js');
        if(serial!==requestSerial||workspace!=='fault')return;
        window.faultSurface.begin();
        let recipe;
        if(preview){
            for(const id of ['faultX','faultZ','faultDirection','faultSlip','faultTransition']){
                if(!$(id).checkValidity())throw Error(`断层参数无效：${$(id).parentElement.textContent.trim()}`);
            }
            recipe=faultParameters();
        }
        const payload=await json(preview?'/api/fault/preview':'/api/fault/case',preview?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(recipe)}:undefined);
        if(serial!==requestSerial||workspace!=='fault')return;
        window.faultSurface.load(payload,recipe||payload.defaults);
        if(!preview)applyFaultDefaults(payload.defaults);
        current={caseId:'strike-slip-fault',identity:payload.identity,source:payload.source,metadata:payload.metadata};
        ui.faultStatus.textContent=`${preview?'预览已生成（未保存）':'保存断层已读取'} · identity ${payload.identity}`;
        ui.exportReview.disabled=false;
    }catch(error){
        if(serial!==requestSerial||workspace!=='fault')return;
        window.faultSurface?.clear();ui.faultStatus.textContent='断层读取／预览失败；旧结果未应用，当前无可导出几何';showError(error);
    }finally{if(serial===requestSerial&&workspace==='fault'){window.faultSurface?.finish();ui.loading.classList.add('hidden')}}
}
async function draftFault(){return loadFaultCase(true)}
function showTdSummary(){const td=catalog?.td;ui.tdCatalogText.textContent=td?`固定来源：${td.directions.join(' / ')}；${td.nativeGrid.rows}×${td.nativeGrid.columns}，${td.nativeGrid.spacing_m}m 原生网格；每方向 ${td.statesPerDirection} 个保存状态。`:'';ui.tdStats.innerHTML='';if(td){textLine(ui.tdStats,'数据状态',td.status);textLine(ui.tdStats,'雨量语义',td.semantics?.rainfall);textLine(ui.tdStats,'蓄量语义',td.semantics?.storage);textLine(ui.tdStats,'流量语义',td.semantics?.signedEdgeQ);textLine(ui.tdStats,'水面高程',td.semantics?.stage);td.sources.forEach((s,i)=>textLine(ui.tdStats,`来源 ${i+1}`,`${s.path} · ${s.sha256.slice(0,12)}…`))}ui.tdMetrics.textContent='当前显示为固定 v10 时间页；不重跑求解器，页内流量是小时累计体积的语义。'}
function tdColorMatrix(){if(!tdPage)return null;const key=ui.tdLayer.value;if(key==='rain')return tdPage.display.rain_mm_h;if(key==='bed')return tdPage.display.height_m;return surfaceRenderer.state.time===0?tdPage.display.start_depth_m:tdPage.display.end_depth_m}
function renderTdPage(){if(!tdPage)return;current={kind:'td',caseId:`td-${tdDirection}-${surfaceRenderer.state.time}`,label:`${tdDirection} · state ${surfaceRenderer.state.time}`,page:tdPage,evidence:{status:'accepted_bounded_scope',scope:'TD v10 native page; sampled every fourth cell for display; totals cover all valid cells',source:tdPage.source,limitations:[tdPage.status,tdPage.flux.semantics]},identity:tdPage.source.identity};currentEntry=null;surfaceRenderer.state.case=current;layerControls(current);evidence(current);ui.viewSubtitle.textContent=current.label;ui.stats.textContent=`${tdPage.metadata.grid_shape.join('×')} · ${tdPage.metadata.spacing_m}m · wet ≥1mm: ${tdPage.totals.native_wet_cells} cells`;ui.tdMetrics.textContent=`${tdPage.metadata.start_s}–${tdPage.metadata.end_s} s ｜ 末态水 ${tdPage.totals.surface_water_m3.toFixed(1)} m³ ｜ 土壤 ${tdPage.totals.soil_water_m3.toFixed(1)} m³ ｜ 快库 ${tdPage.totals.fast_water_m3.toFixed(1)} m³ ｜ 慢库 ${tdPage.totals.slow_water_m3.toFixed(1)} m³ ｜ 雨量 ${tdPage.totals.rain_volume_m3.toFixed(1)} m³ ｜ 正向 ${tdPage.totals.forward_m3.toFixed(1)} m³ ｜ 反向 ${tdPage.totals.reverse_m3.toFixed(1)} m³ ｜ 净小时平均 ${tdPage.totals.net_hourly_mean_q_m3_s.toFixed(3)} m³/s`;ui.ledger.textContent=JSON.stringify({source:tdPage.source,totals:tdPage.totals,flux:tdPage.flux},null,2);surfaceRenderer.render();drawChart()}
async function loadTdPage(index){const i=Math.max(0,Math.min(24,Number(index)||0)),serial=++requestSerial,direction=tdDirection;clearError();ui.exportReview.disabled=true;ui.loading.classList.remove('hidden');try{const page=await json(`/api/td/page/${direction}/${i===0?0:i-1}`);if(serial!==requestSerial||workspace!=='td')return;tdPage=page;surfaceRenderer.state.time=i;ui.timeRange.value=String(i);ui.timeStep.textContent=`${i} / 24`;ui.timeSeconds.textContent=`t = ${i*3600} s`;clearSelection();renderTdPage();ui.exportReview.disabled=false}catch(error){if(serial===requestSerial)showError(error)}finally{if(serial===requestSerial)ui.loading.classList.add('hidden')}}
function tdPageIndex(){return surfaceRenderer.state.time===0?0:surfaceRenderer.state.time-1}
function publishSelection(value){selection=value;ui.selectionTitle.textContent=`${value.type} ${value.index??''}`;ui.selection.textContent=JSON.stringify(value,null,2);const point=value.sourceCoordinates||value.xyz||value.coordinates;ui.coords.textContent=point?`原坐标 ${JSON.stringify(point)}`:'已选取'}
function nearestPoint(points,x,y){let best=-1,dist=Infinity;points.forEach((point,index)=>{if(!point)return;const d=(point[0]-x)**2+(point[1]-y)**2;if(d<dist){dist=d;best=index}});return [best,dist]}
function selectAt(event){
 if(!current||surfaceRenderer.state.drag||surfaceRenderer.state.moved)return;
 const plot=surfaceRenderer.state.plot;if(!plot)return;const x=event.offsetX,y=event.offsetY,mode=ui.pickMode?.value||'node';
 if((mode==='graph'||mode==='edge')&&(plot.graphPlot||current.kind==='dynamic')){const graph= current.graph, graphPlot=plot.graphPlot||plot, points=graphPlot.p;
  if(mode==='graph'){const [index,dist]=nearestPoint(points,x,y);if(index<0||dist>24**2)return;const time=surfaceRenderer.state.time,interval=surfaceRenderer.flowInterval(current);return publishSelection({type:'graphNode',index,domain:graph.nodeKeys[index][0],nodeKey:graph.nodeKeys[index],xyz:[graph.coords[index][0],graph.bed[index],graph.coords[index][1]],bedM:graph.bed[index],stageM:current.timeseries.stages[time][index],storageM3:current.timeseries.storages[time][index],boundary:graph.boundary[index],timeSeconds:current.timeseries.timeSeconds[time],signedQ:interval?.row||null})}
  let best=-1,dist=Infinity;graph.edges.forEach((edge,index)=>{const a=points[edge[0]],b=points[edge[1]];if(!a||!b)return;const dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy||1))),d=(a[0]+t*dx-x)**2+(a[1]+t*dy-y)**2;if(d<dist){dist=d;best=index}});if(best<0||dist>30**2)return;const interval=surfaceRenderer.flowInterval(current);return publishSelection({type:'edge',index:best,endpoints:graph.edges[best],qM3S:interval?.row?.[best]??null,savedInterval:interval?[interval.start,interval.end]:null,orientation:'positive endpoint 0 -> 1'});
 }
 if(current.kind==='engineering'&&mode==='node'&&plot.outletPlots){for(let outletIndex=0;outletIndex<plot.outletPlots.length;outletIndex++){const [index,dist]=nearestPoint(plot.outletPlots[outletIndex].p,x,y);if(index>=0&&dist<24**2){const outlet=current.outlets[outletIndex],bed=outlet.mesh.bedVertices[index],water=outlet.mesh.waterVertices[index];return publishSelection({type:'outletNode',index,outletIndex,outletIdentity:outlet.identity,domain:outlet.domain??outlet.attachment?.domain_id,attachment:{domain:outlet.domain,sourceIdentity:outlet.identity,sharedLandNodeIds:outlet.sharedLandNodeIds??[],terminalQM3S:outlet.attachment?.terminal_q_m3_s??null},xyz:bed,h0M:outlet.mesh.h0[index],bedM:bed[1],waterM:water[1],depthM:water[1]-bed[1],cutM:outlet.mesh.h0[index]-bed[1]})}}}
 if(current.kind==='dem'&&mode==='node'){const [index,dist]=nearestPoint(plot.p||[],x,y);if(index>=0&&dist<24**2){const columns=current.display.height[0].length,row=Math.floor(index/columns),column=index%columns,display=current.display,grid=current.grid;return publishSelection({type:'demPoint',index,displayRow:row,displayCol:column,savedCandidateRow:row*display.stride,savedCandidateCol:column*display.stride,rowColMeaning:'saved DEM candidate grid, not original TIFF pixel',xM:grid.origin_x_m+column*display.stride*grid.spacing_x_m,zM:grid.origin_z_m+row*display.stride*grid.spacing_z_m,heightM:display.height[row][column],unknown:display.unknown[row][column],core:display.core[row][column],footprint:display.footprint[row][column],valid:display.valid[row][column],unknownRendering:'empty map cell / marker, no zero terrain'})}}
 if(mode==='cell'&&current.mesh?.cells){let best=-1,dist=Infinity;current.mesh.cells.forEach((cell,index)=>{const center=cell.reduce((sum,node)=>[sum[0]+plot.p[node][0]/cell.length,sum[1]+plot.p[node][1]/cell.length],[0,0]),d=(center[0]-x)**2+(center[1]-y)**2;if(d<dist){dist=d;best=index}});if(best>=0&&dist<36**2){const cell=current.mesh.cells[best],contributors=current.mesh.contributors;return publishSelection({type:'cell',index:best,cells:[best],nodes:cell,sourceContributors:[contributors?{indices:contributors.indices[best],weights:contributors.weights[best]}:null],wetCells:[current.mesh.wetCells?.[best]??false]})}}
 const [best,dist]=nearestPoint(plot.p||[],x,y);if(best<0||dist>24**2)return;const point=current.mesh?.vertices?.[best]||current.graph?.coords?.[best]||null;let sourceAudit=null;if(current.mesh?.sourceAudit){const audit=current.mesh.sourceAudit,at=(key)=>audit[key]?.[best]??null;sourceAudit=[{node:best,clampedXZ:at('clamped_xz_m'),indices:at('indices'),weights:at('weights'),positiveMask:at('positive_mask'),validLandSupport:at('valid_land_support'),protectedSupport:at('protected_support'),engineeringStripDomain:at('engineering_strip_domain'),dryCutBank:at('dry_cut_bank_mask')}]}return publishSelection({type:'mesh-node',index:best,sourceCoordinates:point,sourceAudit});
}
function pick(event){if(event.button===0)selectAt(event)}
function init(){
    document.querySelectorAll('[data-category]').forEach(tab=>tab.onclick=()=>setWorkspace(rememberedProjects[tab.dataset.category]));
    $('reviewProject').onchange=()=>setWorkspace($('reviewProject').value);syncNavigation(workspace);
    $('terrainVariant').onchange=()=>{if(workspace==='terrain')loadCase(ui.caseSelect.value)};
    ui.caseSelect.onchange=()=>loadCase(ui.caseSelect.value);ui.tdScenario.onchange=()=>{tdDirection=ui.tdScenario.value;setWorkspace('td')};
    ui.tdLayer.onchange=()=>surfaceRenderer.render();ui.vdmForm.onchange=()=>{if(workspace==='vdm')loadVdmCase()};ui.vdmSaved.onclick=loadVdmCase;
    ui.view2d.onclick=()=>{surfaceRenderer.state.view='2d';ui.view2d.classList.add('active');ui.view3d.classList.remove('active');surfaceRenderer.render()};
    ui.view3d.onclick=()=>{surfaceRenderer.state.view='3d';ui.view3d.classList.add('active');ui.view2d.classList.remove('active');surfaceRenderer.render()};
    ui.verticalScale.oninput=()=>{surfaceRenderer.state.vertical=Number(ui.verticalScale.value);ui.verticalLabel.textContent=`${surfaceRenderer.state.vertical.toFixed(2)}×`;surfaceRenderer.render()};
    ui.reset.onclick=()=>{if(!isSavedWorkspace())surfaceRenderer.resetCamera?.()};
    ui.timeRange.oninput=()=>setTime(Number(ui.timeRange.value));ui.stepBack.onclick=()=>setTime(surfaceRenderer.state.time-1);ui.stepForward.onclick=()=>setTime(surfaceRenderer.state.time+1);
    ui.play.onclick=()=>{if(timer!==null){stop();return}timer=setInterval(()=>{const next=surfaceRenderer.state.time+1;if(next>Number(ui.timeRange.max)){stop();return}setTime(next)},1200);ui.play.textContent='暂停'};
    ui.chartMetric.onchange=drawChart;ui.exportReview.onclick=exportReview;ui.vdmPreview.onclick=previewVdm;$('faultPreview').onclick=draftFault;$('faultSaved').onclick=()=>loadFaultCase();
    for(const id of ['faultDirection','faultX','faultZ','faultSlip','faultTransition','faultSide'])$(id).addEventListener('change',()=>{if(workspace==='fault')ui.faultStatus.textContent='参数已修改，未应用；当前几何仍绑定上次结果与 recipe'});
    document.querySelector('#surface').addEventListener('click',pick);window.addEventListener('resize',surfaceRenderer.resize);
}
const reviewReady=(async()=>{
    try{
        const [cat,main,legacy]=await Promise.all([json('/api/catalog'),json('/data/surface-review-v1/manifest.json'),json('/data/manifest.json')]);
        catalog=cat;manifest=main;window._legacyManifest=legacy;ui.bridgeStatus.textContent='本机桥接在线 · 固定来源已登记';
        await loadVdmGallery();await loadBasinComparison();
    }catch(error){ui.bridgeStatus.textContent='桥接读取失败';showError(error)}
})();
function reviewRecord(){
    const category=Object.keys(reviewCategories).find(key=>reviewCategories[key].projects.some(item=>item.id===workspace));
    if(workspace==='fault')return window.faultSurface?.isLoading()?null:window.faultSurface?.reviewRecord();
    if(isSavedWorkspace()&&(!window.savedSurface.reviewRecord()||window.savedSurface.isLoading()))return null;
    if(!isSavedWorkspace()&&!current)return null;
    const record=isSavedWorkspace()?window.savedSurface.reviewRecord():{schema:'surface-review-record-v2',caseId:current.caseId,source:reviewSource(),
        timeIndex:surfaceRenderer.state.time,timeSeconds:workspace==='td'?surfaceRenderer.state.time*3600:current.timeseries?.timeSeconds?.[surfaceRenderer.state.time],
        camera:{yaw:surfaceRenderer.state.yaw,pitch:surfaceRenderer.state.pitch,zoom:surfaceRenderer.state.zoom,vertical:surfaceRenderer.state.vertical,panX:surfaceRenderer.state.panX,panY:surfaceRenderer.state.panY},
        selection,layers:{...surfaceRenderer.state.layers},view:surfaceRenderer.state.view,status:current?.evidence?.status||'pending',
        terrainVariant:current.kind==='legacy'?current.legacyMode:undefined,
        evidence:current.evidence||null};
    return {...record,category,workspace};
}
init();
window.surfaceReview={load:loadCase,getSelection:()=>workspace==='fault'?window.faultSurface?.reviewRecord()?.selection:isSavedWorkspace()?window.savedSurface.reviewRecord()?.selection:selection,isPlaying:()=>timer!==null,selectAt,reviewRecord,navigate:setWorkspace,categories:reviewCategories,ready:reviewReady};
