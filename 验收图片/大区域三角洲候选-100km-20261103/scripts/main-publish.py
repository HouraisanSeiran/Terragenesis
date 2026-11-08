"""Freeze the actual regional candidate and evidence; no evolution or inference."""
from pathlib import Path
import hashlib
import json
import shutil
import numpy as np
from terrain_pipeline.coastal_delta_evolution import load
from terrain_pipeline.coastal_marine_sediment import classify_ocean

task = Path(__file__).resolve().parent
workspace = task.parents[1]
output = workspace / '验收图片/大区域三角洲候选-100km-20261103'
output.mkdir(exist_ok=False)


def copy(source, destination):
    target = output / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


for path in (task / 'main-event-preview').iterdir():
    if path.is_file():
        copy(path, Path('figures') / path.name)
for name in ('final-initial', 'final-formed', 'final-event'):
    for suffix in ('npz', 'json'):
        copy(task / f'{name}.{suffix}', Path('data') / f'{name}.{suffix}')
for name in ('manifest.json', 'source.npz', 'state.npz'):
    copy(task / 'case-source' / name, Path('source') / name)
for name in ('main-source-accept.json', 'main-case-accept.json', 'activation-probe-report.json',
             'candidate-survey.json', 'final-event-report.json', 'budget.json', 'final-check.json'):
    copy(task / name, Path('evidence') / name)
for name in ('run.py', 'continue_case.py', 'activation_probe.py', 'finalize_case.py',
             'render_v2.py', 'main-source-accept.py', 'main-case-accept.py', 'main-publish.py'):
    copy(task / name, Path('scripts') / name)
copy(task / 'report.md', '计算说明.md')
copy(task / 'main-review.md', '主端审查.md')

state, progress = load(task / 'final-event')
ocean, _ = classify_ocean(state, 0.)
with np.load(task / 'case-source/source.npz') as source:
    stage = np.full(state.bed_m.shape, np.nan)
    discharge = np.full(state.bed_m.shape, np.nan)
    for z, x, level, depth, q in progress['river_hydraulics']['nodes']:
        if depth > 0 and q > 0:
            stage[int(z), int(x)] = level
            discharge[int(z), int(x)] = q
    routes = progress['routes']
    offsets = np.cumsum([0] + [len(route) for route in routes])
    np.savez_compressed(output / 'data/final-product.npz',
        bed_m=state.bed_m, valid_mask=state.valid_mask, ocean_mask=ocean,
        source_ocean=source['source_ocean'], source_unknown_wet=source['unknown_wet'],
        water_stage_m=stage, discharge_m3_s=discharge,
        section_nodes_zx_bed_width_bank=np.asarray(progress['hydraulic_sections']['nodes']),
        hydraulic_nodes_zx_stage_depth_q=np.asarray(progress['river_hydraulics']['nodes']),
        route_cells_zx=np.asarray([cell for route in routes for cell in route], dtype=np.int32),
        route_offsets=offsets, route_q_m3_s=progress['river_hydraulics']['route_q_m3_s'],
        origin_xz_m=state.origin_xz_m, spacing_m=state.spacing_m,
        physical_time_s=state.time_s, equivalent_years=progress['years'], world_seed=20261020)

for name in ('regional', 'detail', 'comparison'):
    path = output / 'figures' / f'{name}.json'
    info = json.loads(path.read_text(encoding='utf-8'))
    info['coverage_notes'] = info['coverage_status']
    info['coverage_status'] = 'partial'
    info['rendered_stages'] = ['initial', 'final-event'] if name == 'comparison' else ['final-event']
    info['primary_is_post_event'] = True
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')

readme = '''# 100×100 km区域三角洲候选

区域样图已生成，供用户验收。**100 km是区域视域；主要连续沉积出露块约15×7 km，尚未达到成熟大型三角洲形态。** 三条实际通海水路仍有明显直角，形态未判通过。

- [100 km区域总图](figures/regional.png)
- [20 km本体放大图](figures/detail.png)
- [同源初末与床面变化](figures/comparison.png)
- [主端审查与边界](主端审查.md)
- [计算参数、时间和来源说明](计算说明.md)
- [独立连通与水沙核对](evidence/main-case-accept.json)

![本体与邻近海岸](figures/detail.png)

图为保存高程的地形配色与已算水路，非卫星观测。区域和本体图为25 h事件末态；对照左为初态、右为同一事件末态。原生TD30 m，区域计算200 m，历史种子20261020。蓝线仅正流量/正水深断面，显示线宽增强；灰虚线为历史细河槽几何，本轮未重算沿线水面。紫色是原未知水域分类，并非DEM无效。

复用已有历史沉积初态，再算2等效年河道/漫滩、显式低阈值情景启用两条候选，随后25 h潮浪。未完成连续两年海洋输运；不是标准阈值下自发生成大三角洲。历史库存、长期等效年和物理事件分账。末态三路Q约72.90、48.87、28.22 m³/s，25 h累计接收约881万m³水，其余待交付。

`data/final-product.npz`是事件末态DEM、实际子格断面/水面/流量和活动路线；水面及流量的NaN表示未在该格计算河道值，不能补零作未知上游来水。`source_ocean`保留原海洋证据，`ocean_mask`是事件末态连通海分类，二者不可混用。栅格床面与窄河槽断面分开表达，不应把200 m整格当作河宽。

`data/final-initial/formed/event`的NPZ+JSON为可加载续算检查点；`source/`保留源与迁移账；`scripts/`仅记录实际工作区过程，不是脱离工程的独立运行包。源TD页不复制，路径和摘要保留在来源清单。历史图集不覆盖，具体大小和文件摘要见manifest.json。
'''
(output / 'README.md').write_text(readme, encoding='utf-8')
files = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size,
          'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(output.rglob('*')) if p.is_file()]
manifest = {'schema': 'regional-delta-candidate-publication-v1',
    'status': 'technical_checks_passed; large_delta_morphology_not_passed',
    'source_identity': state.source_identity, 'world_seed': 20261020,
    'extent_km': [100, 100], 'sampling_m': 200., 'native_td_m': 30.,
    'data_time': {'equivalent_years': progress['years'], 'physical_time_s': state.time_s},
    'formed_primary_figures_show': 'post_25h_event',
    'files': files, 'payload_bytes': sum(f['bytes'] for f in files)}
(output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
assert all(hashlib.sha256((output / f['path']).read_bytes()).hexdigest() == f['sha256'] for f in files)
frozen, frozen_progress = load(output / 'data/final-event')
assert frozen.source_identity == state.source_identity
assert np.array_equal(frozen.bed_m, state.bed_m) and len(frozen_progress['routes']) == 3
print(json.dumps({'published': str(output), 'files': len(files) + 1,
                  'bytes': sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
                  'cold_load_routes': len(frozen_progress['routes'])}, ensure_ascii=False))
