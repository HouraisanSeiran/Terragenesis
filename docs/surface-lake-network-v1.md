# Surface lake network v1

本切片将有限时序单池湖泊的隐式步末出流，单向送入实际下游河网的独立工程情景。所有结果始终为 `diagnostic_not_publishable`；`transfer_feasible` 只表示指定有限情景、接缝和门禁可行，不授权任何发布。

## 输入接口

`evaluate_surface_lake_network` 接收完整 `lake_inputs` 字典，键与冻结的 `evaluate_lake_routing` 一致，其中 `recipe` 为 `LakeRoutingRecipe`。下游输入为原始 `plan_channel` 计划、coarse 域/保护、`FineGrid`、完整 coarse shape 的有限 `outlet_stage_m` 数组，以及全部 section/stage/inundation/budget/network/valley/reroute/recovery 配方。

`LakeRiverSeam` 显式给出 `lake_path_grid_zx`、`world_x_m/world_z_m`、`downstream_vertical_datum`、湖泊和下游的原始 `source_identity` 绑定。湖路径节点必须是湖外合法整数节点，不能是 spill；世界坐标须精确对应湖路径节点、下游 coarse 节点及 fine 节点。湖泊与下游 coarse spacing、接缝 terrain 高程及垂直基准须一致；来源字符串可不同，但分别匹配绑定，逐步计划来源链还绑定原计划和湖泊算法身份。

非法索引、对齐、来源、参数或超初始硬资源 bounds 抛出 `ValueError`，不会复制巨大输入或伪造包。物理、门禁或运行累计资源失败保存诊断与已提交前缀。

## 每步算法

1. 从显式输入计算全湖轨迹，逐步重放该湖前缀，核对水位/储量，取隐式步末 `Qout`。
2. 从原计划 `Q` 减去原 D8 donor 汇入量，得到非负原局部入流；只在接缝节点增加 `Qout`，沿原 D8 拓扑重新汇流。禁止在每个格的累计 Q 上直接增加流量。
3. 使用原 H0 和原 channel 配方重新 `plan_channel`，调用真实 `recover_surface_network`。床、水面、细网格、保护、域与预算均须通过原门禁；不降低起河阈值。
4. 正出流必须有活动路径，且实际 recovery 最终计划注入节点活动、fine 注入节点湿。实际 fine 水面达到/超过 spill 即拒绝单向假设：即使湖泊出流恰为零，只要原下游局部来流在此产生高尾水，也同样拒绝。
5. 当前湖泊真实 wet 单元水平 footprint 与下游 fine wet footprint 的正面积重叠拒绝；不只比较点中心。不生成 spill/drop 连接器水几何。

仅 `Qout == 0` 且原下游总局部入流为零、无活动河段时允许 `no_flow`，不虚构湿格，不用 epsilon 吞水量。正出流不足原阈值而缺少活动路径明确失败。

## 账本与前缀

每步独立可核：

```text
dV_lake = dt * (lake_in - lake_loss - Qout)
river_outlet_Q = original_downstream_local_total + Qout
dV_lake + dt * river_outlet_Q = dt * (lake_in - lake_loss + original_downstream_local_total)
```

只求明确出口的 Q，总局部来流不包含重复累计的每格 Q。`ledger` 含每步量、残差和容差；`summary` 含已提交前缀累计量及独立累计残差。下游每步是准稳态门禁情景，不计河道蓄量与传播时间；因此合并账本只适用于该近似，不表示动态湖河守恒观测。

`independent_lake_diagnostic` 可保留全湖独立诊断。若第 k 步下游失败，`committed_lake_arrays`、`summary` 与 `ledger` 只对应 k 之前提交的前缀；不使用全湖结尾几何冒充联合末态。失败步位于 `trace` 且 `committed=false`。

每步床/谷面从同一原 H0 独立准备，是 scenario sequence，不是逐秒重复侵蚀或演化同一河床。切割预算逐情景校验；不同情景切割量不求和为真实总施工量。

## 资源及持久化

`SurfaceLakeNetworkRecipe` 分别限制 steps、湖/coarse/fine cells、累计 attempts、fine work、湖重放 work 与 retained bytes，均有硬上限。每步先保守估算已有+下一候选保留字节，真实 recovery 后再核实，最终 freeze 前核实；保留预算上限为 256 MiB。保守字节核算按结构出现次数计数，可能早拒绝，不扩预算。

`save_surface_lake_network` / `load_surface_lake_network` 是独立自包含诊断接口：输入、全湖诊断、实际下游 recovery 结果和前缀水数组都入包；数组按内容哈希去重。保存重放并在压缩前检查去重 payload 总字节，fsync 后通过原子 hard link 提交，禁止覆盖，竞争只有一个完整文件获胜。

加载先限制 ZIP 压缩/展开字节、成员数、NPY header 数量/形状/dtype，再分配数组；JSON 拒绝重复键与非有限常量，要求精确引用数组集合、哈希与完整算法语义重放。重哈希篡改状态、Q、几何或账本不足以通过。返回数组基于不可写 bytes，不能通过 `setflags(write=True)` 重新开启写入。

## 验证

```text
python -B -m unittest tests.test_surface_lake_network -v
python -B -X utf8 tools/verify_surface_lake_network.py
```

固定验证写入 `verification/surface-lake-network/run-UTC/`，包含正反包与报告、逐步和累计独立复算及不同出流下细床/湿区变化证据。仅使用工程合成资料；不接真实资料、预算迁移、前端、Java、GPU、游戏或默认 consumer。真实高尾水反例保持下游原 H0 与预算：湖 spill=9.01m、路径末 terrain=9m，显式下游出口水位=9.02m；fine 末边整行标为调用方工程合法出口，不宣称自然海口认证。实际 recovery 先通过所有预算和 joint 门禁，再因注入 fine 水面 9.02m 高于 spill 被本单向切片拒绝；正 Qout 和零 Qout 两例均入固定包。受控 mock 门禁测试另列于测试，不伪装为可重放工程包。固定报告没有 mock 情景。
