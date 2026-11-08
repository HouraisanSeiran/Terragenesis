from pathlib import Path
import hashlib, json, shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from terrain_pipeline.coastal_delta_product import load_checkpoint
from terrain_pipeline.coastal_marine_sediment import load_state
from tools.render_remote_sensing import surface_rgb

p = Path('.scratch/coast-marine-reorganization-20261102')
out = Path('验收图片/海岸三角洲河口推进-20261102')
out.mkdir(parents=True, exist_ok=False)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
# Preserve existing event bytes and recover metadata from its unchanged formation progress.
large_event = p/'growth-v3-large-event'
shutil.copyfile(p/'growth-v2-large-event.npz', large_event.with_suffix('.npz'))
large_progress = json.loads((p/'growth-v2-large-20.json').read_text(encoding='utf8'))
large_progress['state_sha256'] = sha(large_event.with_suffix('.npz'))
large_event.with_suffix('.json').write_text(json.dumps(large_progress, indent=2), encoding='utf8')
shutil.copyfile(p/'growth-v2-large-event.json', p/'growth-v3-large-event-stats.json')
source, _ = load_checkpoint(p/'delta-v7-moderate')
small, sp = load_checkpoint(p/'growth-v3-stage10')
small_event, _ = load_checkpoint(p/'growth-v3-event')
large, lp = load_checkpoint(p/'growth-v2-large-20')
large_event_state, _ = load_checkpoint(large_event)
r0,r1,c0,c1=185,240,385,455
x=(source.origin_xz_m[0]+np.arange(c0,c1)*source.spacing_m)/1000
z=(source.origin_xz_m[1]+np.arange(r0,r1)*source.spacing_m)/1000
half=source.spacing_m/2000
extent=[x[0]-half,x[-1]+half,z[0]-half,z[-1]+half]
def plot(states, titles, name):
 fig,axes=plt.subplots(1,3,figsize=(18,5.4),layout='constrained')
 for ax,s,title in zip(axes,states,titles):
  bed=s.bed_m[r0:r1,c0:c1]; valid=s.valid_mask[r0:r1,c0:c1]
  rgb=surface_rgb(bed, s.spacing_m)
  depth=np.clip(-bed/15,0,1)[...,None]
  water=np.array([.24,.56,.62])*(1-depth)+np.array([.06,.20,.34])*depth
  rgb=np.where((bed<0)[...,None],water,rgb)
  rgb=np.where(valid[...,None],rgb,1.)
  ax.imshow(rgb,origin='lower',extent=extent,interpolation='nearest')
  ax.contour(x,z,np.ma.masked_where(~valid,bed),levels=[0],colors='black',linewidths=.7)
  ax.set(xlim=(extent[0],extent[1]),ylim=(extent[3],extent[2]),aspect='equal',xlabel='World x (km)',ylabel='World z (km)',title=title)
 fig.suptitle('Engineering initial edition | TD-derived DEM | 600 m cells | black: DEM 0 m shoreline')
 fig.savefig(out/name,dpi=180); plt.close(fig)
plot([source,small,small_event],['Inherited v7: 400 equivalent years','Growth: +200 equivalent years','Then 25-hour tide / wave event'],'small-200y.png')
plot([source,large,large_event_state],['Inherited v7: 400 equivalent years','Growth: +600 equivalent years','Then 25-hour tide / wave event'],'large-600y.png')
files=[p/'base-product-v2/manifest.json',p/'base-product-v2/final_bed.npy',p/'sediment-v3-state.npz',p/'delta-v7-moderate.npz',p/'delta-v7-moderate.json',p/'growth-v3-stage10.npz',p/'growth-v3-stage10.json',p/'growth-v3-event.npz',p/'growth-v3-event.json',p/'growth-v2-large-20.npz',p/'growth-v2-large-20.json',large_event.with_suffix('.npz'),large_event.with_suffix('.json'),Path('terrain_pipeline/coastal_delta_growth.py'),Path('terrain_pipeline/coastal_delta_product.py'),Path('terrain_pipeline/coastal_marine_sediment.py'),Path('tools/render_remote_sensing.py'),Path(__file__)]
source_dir=Path('.scratch/delta-scale-suite-20261102/source-case300')
files.extend(f for f in source_dir.iterdir() if f.is_file())
snapshot=out/'implementation-snapshot';snapshot.mkdir()
for f in files[13:18]: shutil.copyfile(f,snapshot/f.name)
base=json.loads((p/'base-product-v2/manifest.json').read_text(encoding='utf8'))
manifest={'edition':'工程初版','source_chain':['source-case300','base-product-v2','sediment-v3','delta-v7-moderate','growth'], 'source_identity':source.source_identity,'world_seed':20261020,'origin_xz_m':list(source.origin_xz_m),'shape_zx':list(source.bed_m.shape),'spacing_m':source.spacing_m,'coordinates':'cell centres; x east, z south; array [z,x]; DEM image pixel edges and 0 m contours share absolute x/z coordinates; z increases downward','render':'tools.render_remote_sensing.surface_rgb; elevation colours and shaded relief, synthetic depth tint; no actual land cover','algorithm':'coast-following-v2 base; v7 formation; shoreline-triggered D4 single-cell finite-stock growth','formation_scenario':{'inherited_years':400,'small_additional_years':200,'large_additional_years':600,'event_seconds':90000,'discharge_m3_s':150,'solid_rate_m3_s':0.08,'delivery_leak_multiplier':0.25,'growth_interval_years':20,'sea_level_m':0,'notes':'equivalent formation years are distinct from event seconds; forcing assumed, not measured; 600 m cells, channel widths subgrid; large uses saved v2 states and historical sidecar, not retroactively regenerated history'},'base_manifest_source_files_sha256':base['source_files_sha256'],'sha256':{str(f):sha(f) for f in files},'images':{n:sha(out/n) for n in ['small-200y.png','large-600y.png']}}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
(out/'README.md').write_text('''# 海岸三角洲河口推进｜工程初版\n\n同源 TD 地形、陆架与有限供沙结果：左为继承的 400 等效年，中为再推进，右为 25 小时潮浪事件。黑线是同一 DEM 的 0 m 等高线；横轴 x 向东，纵轴 z 向南。600 m 为栅格间距，绘图不是河宽；色彩为地形示意，不是真实地表覆盖。\n\n小例口门推进约 4.33 km，接陆 43.56 km²；净增厚至少 0.1 m 的连续沉积体跨度 20.303 km，包含水下。大例接陆 55.44 km²、沉积体跨度 20.957 km，同样包含水下。均为假定供流供沙的有限工程情景，不代表完整多叶瓣或百公里三角洲。\n\n来源、参数、坐标、文件哈希和实现快照见 manifest.json 与 implementation-snapshot。大例图只读旧计算，事件 checkpoint 元数据根据保存的形成进度及事件文件哈希恢复；旧阶段历史见工作区 growth-v2-large-history.json。\n''',encoding='utf8')
print('atlas',out, 'large checkpoint',load_checkpoint(large_event)[1]['years_delivered'])
