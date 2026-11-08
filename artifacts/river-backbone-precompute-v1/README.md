# 河网预计算（river-backbone-precompute-v1）：正式候选包说明

本目录是一个**有限候选**产品：一个固定 TD 30 m 窗口上的完整河段网络 + 一个实际事件的水量 +
只读查询。它**不是**世界河网收官，**不**声称海口、水动力、LOD 表示或无限世界。
逐项口径与失败历史见本线交付说明 `.scratch/river-precompute-finalization/s1/DELIVERY.md`。

## 产品内容

```
manifest.json   元数据 + 每段记录 + 逐数组 sha256 + identity_sha256（唯一权威）
arrays.npz      33 个数组（receivers / 掩码 / 面积 / 每段的节点序列 / 本地输入 / 时间边）
```

| 项 | 值 |
|---|---|
| schema | `metric-river-backbone-v1` |
| logical_version | `backbone-or-a-qest-v1` |
| identity_sha256 | `e13280d9b1964f707d1e33cebddd66c19435af5a43636eb1b2e4ac291487e4f7` |
| 支持 | 385×385 = 148,225 格；origin native `[42173, 42874]`；`world_seed=20261020`；`spacing_m=30` |
| 河道 / 河段 / 节点 | 9,484 格 / 1,500 段 / 9,484 节点 |
| 面积 complete / pending | 143,953 / 4,272 |
| 门 | `a_min_cells=48` OR `q_min=1e-3 m³/s`（首版配置候选，已进每段身份） |
| 事件侧流支流 | 292 条，单一来源（`refined`），292 条均在 `audit.json` 里逐条复核 |
| 事件接收湖 | 1 个库（safe level 799.8836 m，safe volume 20,854.19 m³），2 条入湖河段引用 |
| 永久终点 | **全部 `pending`**，无海口/全球内流 |
| payload | 50,894,429 B（48.5 MiB） |
| display_line | **null**（不交付 LOD） |

## 坐标与时间约定

- 格 `(row, col)` 的世界参考点 = `origin_native + (col, row)`，单位 **原生 30 m 格**；
  米制 = 原生格 × 30，仅用于显示与长度。
- 数组一律 `[z, x]` 索引（行是 z，列是 x）；`origin_native_xz` 是**有符号** `(x, z)`。
- `time_edges_s` 25 个值 / 24 个区间；区间 `i` 拥有 `[edges[i], edges[i+1])` 的流量。

## 怎么读（只读，不重算）

```powershell
# 计数/门/可用性总览
runtime/venv/Scripts/python.exe -B tools/query_river_backbone.py --product <候选包根>/product --mode census

# 一个世界点（原生格坐标；落在域外或未解析格会被拒，不裁剪）
runtime/venv/Scripts/python.exe -B tools/query_river_backbone.py --product <候选包根>/product `
  --mode cell --point-native 42299 42874

# 一段河：有序原生 trace + 世界锚点 + 终点
runtime/venv/Scripts/python.exe -B tools/query_river_backbone.py --product <候选包根>/product `
  --mode reach --reach-id rb-ac659596dc3d77de84337abe79d73ad7b6ba5978a74bfb23533aba986f23151d
```

最小读例（需要自己写脚本时）：

```python
import json, numpy as np
from terrain_pipeline.surface_rivers.metric_backbone_product import load_backbone_product

product = load_backbone_product("<候选包根>/product")          # 冷读：校验字节/预算/头/身份/自洽；不重算
manifest = json.load(open("<候选包根>/product/manifest.json"))
row = manifest["reaches"][0]                          # reach_id / 世界锚点 / 终点 / terminal_reason
cells = product["arrays"]["reach_cells"][
    product["arrays"]["reach_ptr"][0]:product["arrays"]["reach_ptr"][1]]
q = product["arrays"]["node_q_source_model_scenario_m3_s"][:, 0]   # 该段 head 的 24 步 m³/s
area = product["arrays"]["node_area_cells"][0]        # 上游面积（格，不是流量）
```

## 必须分开读的量

- **面积**（`area_cells` / `area_m2`）：上游格数 / m²。**不是**流量，`pending` 表示只是下界。
- **`source_model_scenario`**（m³/s）：M2 finite-event 实际产流在本支持上重新累加，属**物理水量**，
  但仍**不是**水动力状态；未标定（`declared_uncalibrated`），只覆盖 3,951 个有输入的格。
- **`climatology_estimate`**：本产品**未声明**，不存在（S1 不内置气候估计器）。
- **水深 / 水位 / 水动力**：`unavailable_no_hydraulic_state`。
- 面积完整性与每个流量的完整性是**各自独立**的累计，互不代用。

## 拒绝而不是猜

域外坐标、未解析格、非河道格读流量、未声明量、永久终点、display line、水动力量，一律**按名拒绝**。
产品内不存在「补 0」或裁剪路径。

## 已验证 / 未验证

- **已验证**（真实数据，独立审计 `status=PASS`）：段内 receiver 链与锚点、覆盖、面积与完整性逐位一致、
  `source_model_scenario` 逐位一致（`max|gap|=0.0`）、292/292 支流单一来源且双加可检出、
  191 条结构终点全 `pending`、2 条河段引用同一事件湖。
- **未验证**：跨窗 72k 格全普查、父进程 RSS 停止门（审计子进程采样峰 190,697,472 B，`is_limit=false`）、
  display LOD 表示层门（R2 仍独立后续）、任意坐标/无限世界、水力与输沙。

## 复跑

```powershell
runtime/venv/Scripts/python.exe -B tools/prepare_river_backbone.py --mode prepare --plan p2 `
  --event-dir <finite-river-sample-v1>/event --event-receiver `
  --side-mode refined --max-branches 1024 --output <新的空目录>
```
新目录拒覆盖；审计不 PASS 则落 `*.rejected-*`，目标路径保持不存在。
