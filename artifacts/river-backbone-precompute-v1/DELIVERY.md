# S1 河网预计算：首版有限候选交付

Date: 2026-10-29 · 状态：**P2 支持上的 prepare + 独立审计 + 只读 query 已在真实数据上通过**
范围：有限候选。**不是**世界河网收官，不推 R2 门完成，不改原 TD / M1–M4 / 旧产物。

---

## 1. 支持范围（一句话）

一个 **385×385 = 148,225 格** 的固定窗口（`p2`：origin native `[42173, 42874]`，`world_seed=20261020`，
`spacing_m=30`），从 4 张 pinned TD 页读取；B1 父级**重算**并核对 identity `9caa2919…342b`。
超出该窗口的任何坐标一律拒绝，不裁剪、不外推。

## 2. 交付了什么

| 项 | 值 |
|---|---|
| 产品 schema | `metric-river-backbone-v1`（`logical_version = backbone-or-a-qest-v1`） |
| 产品 identity | `e13280d9b1964f707d1e33cebddd66c19435af5a43636eb1b2e4ac291487e4f7` |
| 有效格 / 河道格 | 148,225 / **9,484** |
| 河段（reaches） / 节点 | **1,500** / 9,484 |
| 面积完整 / 下界 pending | 143,953 / **4,272** |
| 门（首版配置候选，进身份） | `a_min_cells=48` OR `q_min=1e-3 m³/s` |
| 侧流（支流） | **292** 条，`mode=refined`，单槽替换 |
| 事件接收湖 | **1 个**库、**2 条**入湖河段共同引用 |
| payload | 50,894,429 B（48.5 MiB），33 个数组 |
| 墙钟 | prepare 8.969 s（审计子步 5.813 s），总 16.492 s |

## 3. 两个流量口径（必须分开读）

- **`source_model_scenario`（实际事件，物理水量，不是水动力状态）**：M2 交付的 finite-event soil
  产流（3,951 个有输入的格、24×900 s），在**本支持**上重新沿 receiver 累加。
  24 步末最大节点流量 `0.0451 m³/s`，末步非零节点 271 个。
  标定状态 `declared_uncalibrated`。
- **`climatology_estimate`**：**本产品没有**。S1 不内置气候估计器，只接受调用方声明的显式输入；
  本产品未声明，故该量不存在（面积与拓扑照常成立）。
- **`water_depth_m` / `stage_m` / 水动力**：`unavailable_no_hydraulic_state`，本层从不产出。

流量完整性是**每量自己的**累计：`source_model_scenario` complete 3,951 / pending 144,274（缺输入的格
不被当 0，向下游传播）。面积完整性是另一次独立累计，两者不互相代用。

## 4. 终点：全部 `pending`（诚实口径）

- 191 条河段落在**结构终点**（`retained`/`unknown_boundary`），`terminal_reason=structural_terminal`；
  每条都发布 `permanent_terminal = {kind: "pending", reason:
  "no_trusted_land_sea_or_world_basin_evidence", is_permanent_terminal: false}`。
- **没有**发布任何海口或全球内流终点。
- 2 条河段引用**同一个** M1–M4 事件接收湖：`kind=finite_event_lake_storage`，
  `safe_level=799.8836 m`、`safe_volume=20,854.19 m³`、25 个时间边、24 边有实际蓄水，
  证据指向 `artifacts/finite-river-sample-v1`（product identity `226cd4f6…`）。
  这是**有限事件接收**，`is_permanent_terminal=false`，超出该安全水位/库容即拒。
- gate 选中但不可路由的终点另有 156 格，单独存为 `gate_terminal_mask`，不进河段、不丢。

## 5. 原生 30 m trace 与表示

- 每段保存**有序原生格 trace**（`reach_cells` 按 `reach_ptr` 分段，世界坐标 =
  `origin_native + index`，米制仅用于显示）。`world_path_sha256` 对有序序列取摘要，
  `reach_id = rb-…` 由世界锚点（root 世界点 + 有序路径摘要 + 门 + 种子 + 间距）派生，
  **不含** support origin/shape、flat 索引或 segment 序号。
- **`display_line = null`**：本版**不交付** LOD/简化折线。简线永远不能用于挖槽、路由或物理。
- 河形生产保真（R2 的表示层门）**仍独立后续**，本版通过不把它标 done。

## 6. 命令（真实跑过的）

```powershell
# prepare（新建目录；PASS 前不落正式路径）
runtime/venv/Scripts/python.exe -B tools/prepare_river_backbone.py --mode prepare --plan p2 `
  --event-dir artifacts/finite-river-sample-v1/event `
  --event-receiver --side-mode refined --max-branches 1024 `
  --output .scratch/river-precompute-finalization/s1/staging/p2-event-refined-v4

# 独立审计（另一次冷读；不重算 D8，不 import 生产者）
runtime/venv/Scripts/python.exe -B tools/audit_river_backbone.py `
  --product .scratch/river-precompute-finalization/s1/staging/p2-event-refined-v4/product `
  --parent-reference .scratch/river-precompute-finalization/s1/staging/p2-event-refined-v4/parent-reference.json `
  --report <新报告路径>.json

# 只读 query（不累计、不重算）
runtime/venv/Scripts/python.exe -B tools/query_river_backbone.py `
  --product .scratch/river-precompute-finalization/s1/staging/p2-event-refined-v4/product --mode census
```

预算：单算 process 60 s 墙钟、树 RSS 512 MiB、输出 payload 128 MiB —— 本次实测审计子进程 tree RSS
采样峰 **190,697,472 B（≈181.9 MiB）**，`is_limit=false`；**prepare 父进程（页读取 + build）峰值仍未测**，
故 `memory_budget_status = sampled_observation_only`，**不自报 512 MiB 门已过**。

产品目录内容（供主端 copy 到 `artifacts/river-backbone-precompute-v1/`）：
```
p2-event-refined-v4/
  product/manifest.json   2,214,490 B  元数据 + 1,500 条每段记录 + 逐数组 sha + identity
  product/arrays.npz     50,903,201 B  33 个数组
  parent-reference.json       2,395 B  B1 父级身份 + 来源 pin + assembly digest
  audit.json                179,798 B  独立审计完整报告（PASS）
  prepare-record.json         1,776 B  门/侧流计数/审计子步记录与 RSS 采样
```
copy 时请**整目录**复制（`product/` 与三个 JSON 同属一份证据）；只 copy `product/` 会丢失审计与父级绑定依据。

## 7. 独立审计实际通过的内容

`status=PASS, reasons=[]`，五项：
- `walk`：1,500 段 / 9,484 覆盖格 / 0 问题（段内 receiver 链连续、锚点、handoff、terminal edge 全部复核）
- `area`：与独立累加**逐位相同**；`area_complete` 与独立传播逐位相同（143,953 / 4,272）
- `quantities`：`source_model_scenario` 逐位相同，`max|gap| = 0.0`；完整性同理；`area_completeness_used=False`
- `terminals`：191 条全 `pending`，无永久终点；2 条引用同一库
- `side_inputs`：**292/292** 支流 `chosen.from` 单一来源、双加可检出、交付=成员供给、声明序列与入口交付一致

## 8. 失败历史（全部保留，未覆盖）

| 版本 | 失败点 | 处置 |
|---|---|---|
| v1 | 入口：`support_plan` 拒 `source_records` 必须精确 `{path, sha256}` | 工具侧 `_pin_records` 抽取；未改旧 strict 门 |
| v2 | 292 支流超 256 硬门 | 经用户放宽后按实重估计数上限 1024（并修掉两处真成本：分支只分配自己成员、side-input 每量只累加一次） |
| v2 复跑 | 建网→validate 拒「at most one reach may carry an event receiver」 | 改为按**湖身份**判唯一：同库多引用允许，不同库/矛盾证据仍拒 |
| v3 | 独立审计误报 `receiver graph contains a cycle` | 审计 Kahn 起点误取终端；只修 auditor，只读验证面积/完整性逐位一致 |
| v3 复跑 | `array not broadcastable to correct shape` | 审计死代码一维 scatter 配 24×148225 值；删死代码 + 加形状断言 |
| v3 复跑（同轮） | side-input 280/292 误判不等 | 审计把成员路由流量求和当独立答案（重复计数）；改为入口格交付 vs 成员本地供给 |
| v4 | — | **PASS** |

## 9. 明确不宣称

- 世界完成 / 任意坐标 / 无限世界：**false**。
- 海口、全球内流、永久终点：**pending**，一条都没有。
- Q-only 通道格数：**实测 0**（`q_gate_only_cells=0`）。48 格面积门单独主导了本窗河道；
  真实数据下 Q-only 为 0 就如实报 0，未调参凑非空。
- display LOD、水力/水深/水位、回水洪泛、输沙、湖库容动态：**不提供**。
- 跨窗 72k 格全普查（`independent_window_comparison`）**未跑**，本版不声称跨窗一致。
- 父进程 RSS 停止门：**未认证**。
- 40 km / 1 m 保真、R2 表示层门：**未完成**。

## 10. 已知未闭合项（不阻碍本版有限候选）

- 40 个事件输入格无河道下游（`no_channel_downstream`，未进入任何支流）；它们仍是 recorded
  `unassigned`，不被当 0 也不被丢弃。
- 4,272 格面积为 `lower_bound_pending`（窗口切边），原样入账。
- 产品只在 `.scratch/river-precompute-finalization/s1/staging/p2-event-refined-v4/` 下；
  正式路径 `artifacts/river-backbone-precompute-v1/` 由主端 copy，本线不写。
