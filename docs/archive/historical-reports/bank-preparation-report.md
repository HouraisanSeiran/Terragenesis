# 显式有限拓岸准备

`terrain_pipeline.coastal_delta_bank_formation.prepare_banks(state, progress, *, max_cut_m=0.5, min_wet_depth_m=0.05, subdivisions=None)` 返回 `(new_state, new_progress, report)`。距离单位为米、面积为平方米、固体库存为立方米；`subdivisions=None` 使用网络保存的采样细分数，缺省为 8。输入 progress 不原地修改。仅支持已有多单元节点库存、设计宽度和 irregular route geometry 的状态；无有效保存节点水位时该节点的请求被拒绝。

```python
from terrain_pipeline.coastal_delta_bank_formation import prepare_banks
from terrain_pipeline.coastal_delta_hydraulics import solve

state, progress, report = prepare_banks(state, progress, max_cut_m=0.5)
# 使用调用方的实际海平面和水力配置重新求解。
hydraulics = solve(state, progress, sea_level_m, hydraulic_config)
```

依据现有设计宽度对已保存路线采样，逐节点扣除已有占有，按每格剩余面积比例分配竞争；仅转移真实外部库存。外部床由外部固体库存、剩余面积、base 和孔隙率计算。新增部分仅在已有水位减最小湿深以下才接纳；必要切深受 max_cut、可蚀库存和原节点平均断面床高约束，切出固体进入 mobile。已占有部分不再转移。此处水位是保存的滞后水力结果，拓岸后必须由调用方重算水力；模块不接入默认世界，也不调用图求解器。

报告包含设计走廊采样面积 `design_area_m2`、拓岸前后占有面积、实际新增面积和切沙总量；`nodes` 按节点列出申请、新增、切沙及 `missing_stage`、`no_free_area`、`bank_above_wet_limit`、`competing_for_free_area` 拒绝面积。设计走廊面积与实际占有面积不一定互相包含：旧占有始终保留，竞争与高岸可限制新增。

针对现有合成 fixture（100 m 网格、细分 12、设计宽 350 m、保存水位 -2.2 m、默认限制）的测试：设计采样面积 748,541.67 m²，实际占有从 494,791.67 增至 748,541.67 m²，新增 253,750 m²，切出并转入 mobile 38,062.5 m³。这个数值仅说明该合成案例，不代表自然地貌验收。

验证：`python -m pytest tests/test_coastal_delta_bank_formation.py -q`（3 passed）；`python -m pytest tests/test_coastal_delta_multicell.py -q`（9 passed）。覆盖库存守恒、占有不超 1、原始基底和孔隙率及海洋种子不变、两节点竞争、无空闲面积、高岸、缺水位、重复调用与存档冷读。测试无 TD/GPU。
