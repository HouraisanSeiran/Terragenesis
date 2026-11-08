# 图水力、连续分合与显式有限拓岸集成

2026-11-04。实现使用用户授权的 GPT-6.1 Sol 后备模型。仅显式实验入口启用；没有切换默认世界，没有调用 TD/GPU 或前端。原始 TD 来源和旧结果未改动。

## API

```python
from terrain_pipeline.coastal_delta_branching import _record, _update_activity
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_delta_morphology import (
    prepare_morphology, capture_formative_discharge,
)
from terrain_pipeline.coastal_delta_evolution import save

config = HydraulicConfig(upstream_stage_limit_m=stage_limit_m)
progress['hydraulics_backend'] = 'physical_edge_graph'
_update_activity(state, progress, actual_sea_level_m, 'explicit-graph', config)
state = _record(state, progress)

# 显式形态边界：使用现有 design_width_m，请求有限岸边面积；切床进入 mobile。
state, progress, report = prepare_morphology(
    state, progress, sea_level_m=actual_sea_level_m, hydraulic_config=config,
    max_cut_m=.5, min_wet_depth_m=.05, subdivisions=None,
    capture_formative=True, reference_sea_level_m=mean_sea_level_m,
)
save(new_checkpoint_prefix, state, progress)

# 也可独立捕获代表性成形 Q，不改变当前保存水力的海位。
state, progress = capture_formative_discharge(
    state, progress, hydraulic_config=config,
    reference_sea_level_m=mean_sea_level_m,
)
```

`prepare_morphology(...) -> (state, progress, report)` 先按实际海位求解并记录，再调用已交付的 `prepare_banks`，最后在新增面积和切床后的同态库存上重算水力、activity、segments 并记录。它不另造河宽公式，也不在每个物理子步自动拓岸。`report` 保留 bank 模块面积、切沙和逐节点拒绝项，并将 `hydraulics_recompute_required` 置 false，记录 `recomputed_sea_level_m`。使用新的返回 state/progress 保存和续算；直接在冷读后的 progress 上修改元数据时，也必须 `_record` 后再保存，不能绕过 `_validate`。

`capture_formative_discharge(...) -> (state, progress)` 只允许 graph 模式，将参考海位解的唯一实际节点 Q 存在 `progress['formative_discharge']['nodes']`，行格式 `[z,x,q_m3_s]`；小于总流量 1e-7 的零流/数值尾部不会抹除历史正 Q。`node_reference_sea_level_m` 逐节点保存该正 Q 的来源参考海位；顶层 `reference_sea_level_m` 是最近尝试的海位，干解后可能与历史节点来源不同。`source`、`parameters`、`algorithm` 和 `reference_semantics` 说明取值身份。这是显式代表性边界条件，不是气候统计。graph 模式下 `_width_feedback` 只使用已捕获的实际 Q，未捕获节点保留设计宽并报告 unavailable，不再将设计分配当成实际 Q。旧模式保留旧设计 Q 契约。

## 流量与拓扑契约

`solve_sections` 在 `hydraulics_backend == 'physical_edge_graph'` 时调用现有 `solve_graph`，其他值保持原路径；缺少显式断面时该后端报错。图算法的数值方程未更改，仍是非负单向 DAG 的准稳态矩形 Manning 近似，不包含反向潮河、惯性、临界流或科研浅水。

`edge_q_m3_s` 每行 `[az,ax,bz,bx,q]` 和 `mouth_q_m3_s` 每行 `[z,x,q]` 是实际唯一物理流。`segment_fluxes`、`_event_edges`、multicell 事件/年度共用的 `_edges` 和 `_mouth_forcing` 直接消费它们；旧单格年度边构造也优先消费该结果。河口方向按唯一流入边实际 Q 加权真实不规则坐标单位方向，且按 distinct end 只附加一次外部交换边；宽度取实际有效断面。

`route_q_m3_s` 仍将每个独立嘴流量分给首次出现该嘴的 cover，其他同嘴 cover 为 0。它不表示路径流量；`actual_shares = route_q / requested_q` 只作兼容汇总，不能据此重建物理边。`active` 表示此 cover 上所有实际边及嘴 Q 均大于总 Q 的 1e-7，与独立供水分配无关。

graph attachment 允许从共享主干再分出一臂；每次只追加父前缀、新臂、既有重汇后缀的必要 cover，不展开全部路径组合。几何相交、真实 mesh 邻接、库存唯一和 DAG 检查保留；层级深度及侧支上限仍约束父分支，嘴数量使用 distinct ends。multicell 自动口门延长对所有同嘴 cover 共享同一段新增几何/库存，只延长一次；avulsion 的嘴数和共享干流候选兼容 graph 模式。真实事件、有限拓岸、连续 attachment 的验收范围是具有不规则几何和 node_footprints 的 multicell 链；旧单格年度消费者已接实际边，但单格自动形态 graph 模式没有专项验收。

## 验证与成本

所有命令使用 PowerShell `login:false`、`D:/anaconda/python.exe`、`PYTHONPATH=.;tests`、OMP/MKL/OPENBLAS 单线程、UTF-8。

- `pytest tests/test_coastal_delta_graph_integration.py -q`：3 passed，最终运行 9.12 s。连续两组真实 irregular mesh split/rejoin attachment，4 条必要 cover、2 个嘴；4 s/2 s 子步真实水沙事件约 0.32 s。添加缺省跨组合并重排 cover 后，事件床沙/mobile/stranded 库存按相对 1e-4 等价，共享主干和嘴只消费一次，存档冷读后第二个 2 s 事件按位一致。
- 同一集成测试覆盖拓岸新增实际面积、固体守恒和 immutable base、拓岸后保存 stage 与重新 solve 一致、参考 Q 零流保留及原海位 provenance；实际年度预算与 width feedback 使用所捕获 node Q 一致。
- 同一集成测试将真实断面与库存中的一条臂抬到 4 m 坎，实际可用旁路仍接受总 Q=100 m³/s，高坎边 Q<0.001 m³/s，2 s 事件传入 200 m³ 水并守恒；不是仅伪造 shares 的测试。
- `pytest tests/test_coastal_delta_graph_hydraulics.py tests/test_coastal_delta_branch_attachment.py tests/test_coastal_delta_bank_formation.py -q`：11 passed，22.43 s。
- `pytest tests/test_coastal_delta_multicell.py tests/test_coastal_delta_irregular_consumers.py tests/test_coastal_delta_mouth_extension.py tests/test_coastal_delta_multicell_avulsion.py tests/test_coastal_delta_branch_attachment.py tests/test_coastal_delta_hydraulics.py tests/test_coastal_delta_evolution.py -q`：56 passed，33.59 s。
- 补齐单格年度实际结果传递及规则坐标 fallback 后，`pytest tests/test_coastal_delta_graph_integration.py tests/test_coastal_delta_evolution.py -q`：22 passed，9.40 s。随后只增加成形 Q 逐节点参考海位元数据，再运行集成 3 passed。

以上计数有交集，不累加为独立测试总数。唯一 warning 为环境 anyio pytest 插件的 CallSpec2 弃用提示。没有引入 warm start 或稀疏 Jacobian；当前窄接线不改变已验证图解方程。长事件仍每 marine 子步求解，成本取决于图规模、岸床状态和步长，应按实际保存 TD 图测量。主端独立运行同源 100 m TD 10 s event 成功，约 2.63 s；其验收产物及更长时间结果由 reference-case-v7 runner/renderer 单独记录，不以本合成 fixture 代替 TD 验收。

冷读年度入口曾报 `formation progress does not match state`。最小复现显示 load 后立即 `_validate` 通过；run.py 在冷读后增加 `scenario_mean_sea_level_m`、未 `_record`，再保存才失败。runner 作者已补 `_record`，其同源 load→metadata→record→save→冷读烟测通过，床沙数组不变。生产一致性校验不放宽。

## 本次变更源码 SHA-256

```text
terrain_pipeline/coastal_delta_hydraulics.py 1c61a29eebea1726be267cf5990efed448eacb7378d15e993e362f01f712f91c
terrain_pipeline/coastal_delta_graph_hydraulics.py 58e75ecb1bddfbe46f461d6440e3d39a7f23d8108c93267eb17d0d308bde8707
terrain_pipeline/coastal_delta_branching.py 94ae3aaa142c6aeb72a338babbb485a2bffd99dc04febe748832c1730788f36f
terrain_pipeline/coastal_delta_branch_attachment.py 8d9b79ac53a989f6fe3d484c7583dc15b295e1b7cfd7c0147dbdeafa2b9545b5
terrain_pipeline/coastal_delta_morphology.py c9243c7431c35f786aa163c09fbdb6deb062f82c4e7ebc735b758ea678e7e7c9
terrain_pipeline/coastal_delta_multicell.py b3c8afbfef809b58396600fa4778f5593cb66e22f63a1e95f06b40eea5d0af34
terrain_pipeline/coastal_delta_mouth_extension.py f2a07ee8c0945a3dba759a5b5f93e87bb0c27e79f872663d39af9c278aa1c16e
terrain_pipeline/coastal_delta_multicell_avulsion.py 1158cdaed1b7f11508f04c25326bf2a1cd9c055923e9c82ae42acac6c42408ba
terrain_pipeline/coastal_delta_evolution.py ab50368ffebf4d4950c5bd0685d3a0a1cab2204a67055ed3689ac58aa508005a
tests/test_coastal_delta_graph_integration.py cc5e4d38f4e224ef11453decdc212e76d18ff8d766ce58c52fe80bfd218bfc7d
```
