# 无限世界河网：动手前的设置核对（2026-10-20）

状态：**设计确认稿，未改动任何代码**。本文件只记录现状、实测与待拍板项。

---

## 0. 本轮问题

> 「先这样吧，检查一下河网部分，尝试生成无限时间。做之前先确认一下河网和群系、气候等元素应该怎么设置」

石柱群真三维线已收尾（落仓 + web 接入）。本轮转到河网线。用户明确要求**动手前先确认设置**，故本文件只做确认，不含实现。

---

## 1. 结论摘要

1. **「无限」目前只在上游成立。** TD 地形是真的无限（任意坐标取窗、确定性绝对坐标场）；**下游河网没有任何按需能力**，现有的六源主线写死 `0..5` 索引、整域一次算完。
2. **按需入口确实存在且能跑**，但**只有 66.1% 的宏观格能成功规划**，其余 33.9% 以同一个原因硬拒绝：`final published terrain drains outside its frozen domain`。
3. **跨窗口对不上，而且不是底层场的错。** 实测相邻两窗共享 12 513 格：原始条件场差 **0.0 m**（底层场是 `(seed, x, z)` 的纯函数），但发布后的 `height_m` 差 **144.9 m**、152 格流向不一致、**河网只重合 41.9%**。
4. **海洋掩码本身也是窗口依赖的**（2026-10-20 复核，更正下文 §2.2）：海洋由**窗口内洪泛**定义（`hydrology_planning.py:174-189`），窗口边界截断传播；多对相邻窗复核为 **13/36 对掩码不一致**（每对 1–13 格 / 12 513 格）。原 §2.2「海洋掩码完全一致」是**单对旧探针**的结论，**不成立**。

---

## 2. 实测（本轮新增，read-only 探针）

探针脚本在 `temp://scratch/river_on_demand_probe.py` / `_rate.py` / `river_cross_window.py`，未写入仓内任何文件。

### 2.1 按需接受率（11×11 宏观格，`-5..5`，seed=20261020）

```
  z=+5  ####...####   z= 0  ##....####.   z=-5  ##.##..#.##
  z=+4  ...#...####   z=-1  ####.###..#
  z=+3  .##########   z=-2  ###########
  z=+2  ##.#..####.   z=-3  ####.##..##
  z=+1  ##..#....##   z=-4  .##..#..##.
```

| 指标 | 值 |
|---|---|
| 接受 | **80 / 121 = 66.1%** |
| 拒绝原因 | **41/41 全部**是 `final published terrain drains outside its frozen domain` |
| 单次耗时 | 0.75–0.91 s（129×129 格，`macro_span_m=320_000`） |
| 确定性 | 同一格规划两次，`identity_sha256` **完全相同** |
| 产物状态 | `finite_canonical_support`，`budget.complete_world_coverage = False` |

拒绝来自 `hydrology_planning.py:295`：发布后的实际 D8 流向越过了冻结域边界（`:294` 的条件是「下游落在非海洋、且 owner 不同」）。同一函数里还有 `:299` 的对称门「unknown halo contributes inflow to frozen domain」。

> **2026-10-20 更正（诊断子代理逐格实验，待主线复核）**：本条上面的归因**不充分**。真机制是 `:290` `height = np.where(target | ocean, height, original)` 把已抬升的 halo **压回原值**，在发布面上**新造**了跨域最陡坡；而 `:291-295` 的门**在回退后的面上**校验。逐格实测：**每个被拒格在回退前违规数都是 0，回退后才 1–2**；保留填充 halo 的变体**同批格全部通过**。→ 拒绝是**实现层自伤**（门验的是被自己破坏过的面），**不是地理事实**。修法极小（不回退 halo / 门移到回退前），可能一举把接受率从 66% 拉到接近 100%。

### 2.2 跨窗口一致性（相邻两窗，共享 97×129 = 12 513 格）

| 量 | 结果 |
|---|---|
| 原始条件场 `original_height_m` | **max\|diff\| = 0.000000 m** ✅ |
| 海洋掩码 `ocean_mask` | ⚠️ 单对旧探针报 0 格不一致；**多对复核为 13/36 对不一致**（见 §2.3）❌ |
| 发布后 `height_m` | **max\|diff\| = 144.92 m** ❌ |
| 流向 `receiver` | **152 格不一致** ❌ |
| 河网 `river_mask` | 左 72 / 右 60，共享 39，并集 93 → **重合率 0.4194** ❌ |
| 归属 `owner_domain_id` | **1805 格不同**（左 67 个域 / 右 82 个域）❌ |
| 底层场是否全局一致 | 同一世界坐标重复采样差 **0.0 m**；是 `(seed, x, z)` 的纯函数 ✅ |

**读法**：底层真无限且因果一致是对的；**不一致完全来自「每个窗口各自做局部修正」**——每个 support 独立抬高/降低地形、独立划分归尾，没有跨窗对齐机制。

### 2.3 多对复核（2026-10-20，验收器 `tools/audit_river_on_demand_consistency.py`）

上表 §2.2 是**单对**读数，会把「恰好一致」误当通则。验收器对**全部相邻 accepted 对**逐对复核（seed=20261020，半径 3），并把「比较器是否对齐」与「产品是否一致」分成两件事：

| 量 | 半径 3 实测（36 对可比） |
|---|---|
| 共享原始条件场 max\|diff\| | **0.0 m**（36/36）——比较器对齐的**指纹** |
| 海洋掩码不一致 | **13/36 对**，每对 1–13 格 |
| 发布高度有差异的对 | **36/36 对**，最差 **239.51 m** |
| 流向不一致 | 36/36 对，最差 220 格 |
| 归属 `owner_domain_id` 不一致 | 36/36 对，最差 2404 格（**注意：这是标签噪声，不是冲突**——见 §2.4） |
| 河网重合率 | min **0.0**、mean **0.137** |
| 加载顺序无关（打乱重算比 identity） | **0/31 不一致** ✅ |
| 确定性（同格重算） | 3/3 相同 ✅ |

**海洋掩码为什么是窗口依赖的**：`certified_sea = original < sea_level_m - 100` 只在**窗口内**采样，洪泛也只在窗口内进行 → 「与主洋连通、但通路在窗口外」的格子，一窗判海、另一窗不判。这是**结构性缺陷**，必须进 P2/P3 清单。`:197-198` 还会因窗口内没有 certified ocean 直接拒绝整个 support。

> 运维提醒：验收器把所有输出放在结尾，长跑务必用 `background` + `python -u`，否则进程被杀时（如误设 `timeoutMs`）stdout 缓冲里的东西会全部丢失，现场变成「exit 1 且无任何输出」。

### 2.4 主轴「出口点定域」判据（2026-10-20 决定性实验）

**先纠一个量测错误**：`owner_domain_id` 在 `general` 模式下是 `enumerate(sorted(selected_terminals))` 的**窗口内序号**（`hydrology_planning.py:283-284`），同一个物理域在每个窗口拿到不同整数。拿它做跨窗比较会报出上千格「不一致」（旧验收器报 2533/2404）——那是**标签噪声**。可比的量是**流域出口的世界坐标** `catchments[].terminal_world_xz_m`。

实验（目标格 `(0,0)`，自身窗口以 `final published terrain drains outside its frozen domain` 拒绝；逐个看它的邻居窗口对该格世界方格的归属）：

| 邻居窗口 | 覆盖该方格的格数 | 该方格上的出口 |
|---|---|---|
| `(0,1)` | 43 / 1681 | 5 个不同出口 |
| `(1,0)` | 43 / 1681 | 6 个不同出口 |
| `(1,1)` | **4** / 1681 | 1 个（`(360000, 340000)`） |
| `(-1,-1)` | **0** / 1681 | — |
| 其余四个邻居 | — | 同样拒绝 |

三个覆盖它的窗口两两相比，**在两窗都认领的格子上对物理出口的归属 4/4 完全一致**。

**判定**：
1. **物理出口归属是全局良定义的** —— 两个窗口都认领同一格时说的是同一个出口。主轴方向**成立**。
2. **但「领属（哪块地属于哪个域）」是窗口相对的** —— 同一格被不同窗口认领 0 / 4 / 43 格。仅靠「出口点定域」**不够**。
3. → **P2 必须同时解决两件事**：① 用**全局出口**定域（已有主轴）；② 让 **eligibility（领土）也窗口无关**，否则「任意格都能出河网」仍不成立。
4. 该方格 **1337 / 1681 已被判海** → 海边附近被拒格大量是**真海洋**，「拒绝」大部分其实是「这里就是海」。**海岸线与海陆边界必须进 P2 范围。**

> 验收器已据此升级为 **schema v2**：新增物理出口字段（`outlet_disagreements` / `outlet_agreement` / `outlet_coverage_mismatch_pairs`），旧 `owner_disagreements` 改名 `owner_label_disagreements` 并标注为非冲突指标。

**规模确认（半径 5，**101 对**可比，v2 验收器 `temp://scratch/consistency-baseline-r5-v2.json`）**：

| 指标 | 值 | 读法 |
|---|---|---|
| `comparator_aligned` | **True** | 条件场摩擦指纹通过，下文跨窗数字均有效 |
| `outlet_disagreement_pairs` | **0 / 101** | 两窗都认领的格上物理出口**零冲突** |
| `min / mean outlet_agreement` | **1.0 / 1.0** | 出口归属**全局良定义**——主轴成立 |
| `outlet_coverage_mismatch_pairs` | **101 / 101** | 「领地覆盖量」**每对都不同**——eligibility 窗口相对 |
| `worst_owner_label_disagreements` | 2533 | **纯标签噪声**（已标注 informational） |
| `ocean_mismatch_pairs` | 25 / 101 | 海洋窗口依赖 |
| `conditions_conflict_pairs` | **0** | 底层场无冲突 |
| `worst_height_diff_m` | 239.51 | 局部修正窗口依赖（101/101 对有差） |
| `load_order.identity_mismatches` | **0 / 80** | 加载顺序无关 ✅ |
| 接受率 | **80 / 121 = 66.116%** | 拒绝 41/41 同因；`undocumented = 0` |

**结论（P1 定性口径）**：跨窗不一致**不是**底层的错（条件场 0、出口 0）；它集中在**三个窗口相关的局部量**：海洋掩码（25/101）、局部修正高度（101/101）、域领土覆盖（101/101）。

> **运维与量测教训（已写入验收器 docstring）**：① `owner_domain_id` 是窗口内 `enumerate` 序号，**永不可跨窗比较**——必须用 `catchments[].terminal_world_xz_m`；② 给「已知为真」的量（条件场）设**指纹门**，一旦它报出差异就说明**比较器错了**，而不是发现了冲突。

设计文件自己也承认这一点：`hydrology_planning.py:504-506`「Infinite-world ownership and adjacent canonical support reconciliation are **deliberately not certified** by this experimental pair planner」，`:377`「infinite coverage and adjacent canonical products not certified」。

---

## 3. 现状：三个元素各自是什么

### 3.1 河网

**主线链**（当前最完整）：TD 来源 → 噪波降雨 → 汇水路由 → 河网选择 → 实际河床 → 独立审计 → 静态图集。入口 `python -m tools.generate_td_terrain_rivers` + `audit_td_generated_rivers` + `render_td_generated_rivers`。

| 能力 | 现状 | 位置 |
|---|---|---|
| 上游 TD 地形 | ✅ **真无限**（任意坐标、确定性） | `diffusion/backend.py:60-73`；上限 `\|tx\|, \|tz\| ≤ 1e6`（`diffusion/service.py:42`） |
| 下游河网 | ❌ **全有限** | 六源写死 `0 <= sample_index < 6`、强制 (513,513) float32（`metric_td_generated_source.py:28,41-42,59`）；生成器整域一次算完，四边当出口 + 强制 `valid_mask.all()`（`metric_td_generated_rivers.py:107-120`） |
| 最接近按需 | ⚠️ 按宏观格规划，但**每格独立** | `hydrology_planning.py:383-390` `plan_canonical_support(seed, cell_x, cell_z)`；`macro_span_m=320_000`（`:29-39`） |
| Python↔Java 衔接 | ⚠️ **loopback HTTP 不含河网** | `DiffusionClient.java:8,25-32`；Python 侧只有 `/health` 与 `/tile`（`diffusion/service.py:33-49`）；河网产物走文件 |
| Java 默认世界 | ⚠️ **是有限的** | `TerrainModeRegistry.java:19` + `LandformMode.java:12,32` → `metric_processed_readonly_v1`；越界即抛（`MetricProcessedTerrainSource.java:141-146`）。真无限的 `live_diffusion_global` **只给地形、不给河网** |

设计基线：`CONTEXT.md:71-88`（世界无限、**每个独立水文域与其水系必须有限**）、`:109`（「水文规划域层、相邻域验证及**无限按需调度尚未完成**」）、`:127`（九层基准）；`river-module-classification-20261009.md:60`（「尚未形成统一的无限世界运行链」）；`river-engineering-map.md:29-31`（无限世界列【长期目标】，待验证：窗口外延续 / 加载顺序 / 跨窗口一致性）。

### 3.2 气候

**两套并存，行为完全不同：**

| | TD 输出 5 通道 | 噪波气候 `metric_noise_forcing.py` |
|---|---|---|
| 内容 | 气温°C / 温度SD°C / 年降水mm / 降水CV% / **局地递减率 β** | 三强度场 + 12 月月温/月降水 + BIO1/4/12/15 |
| 身份 | 模型输出（「合成条件输出，不是实测气候」） | `metric-noise-climate-v1` |
| **β 通道** | **被本项目在边界丢弃**（只留 BIO1/4/12/15） | 有显式 `lapse_rate_c_per_m=-0.0065`（强制 −0.012≤·≤0） |
| **纬度** | —（不是场，是模型条件） | ❌ **完全没有**（`_coordinates` 只有 x/z + seed） |
| **迎风/背风** | — | ❌ **没有**；`elevation` 只进温度递减、**不进降水** |
| 谁在用 | TD 条件输入（`geographic_v1`）；Java 实时扩散路线重标定 | **河网产流 / 季节水账**（`metric_td_generated_rivers.py:211-222`、`hydrology_seasonal.py:17,70-77`） |
| 群系是否用 | ❌ 不用 | ❌ 不用 |

被丢弃的 β 通道：`diffusion/backend.py:70-71` 逐字「Upstream additionally returns temperature lapse rate; the public tile contract keeps BIO1/4/12/15」+ `climate=output['climate'][:4]`。

**唯一实现过迎风背风的是旧路线**：`diffusion/geography_v5.py:61-66`（`windward=clip((mountain-west)*800,0,350)`、`lee=...`，降水含 `+windward-lee`）；`:54` 的 `latitude = 22*np.sin(z/96)` 是**伪纬度**（条件格坐标的周期正弦），**不是米制纬度**。米制主线**一处也没有**。

### 3.3 群系（Minecraft 侧）

**决策链**（`TerrainBiomeSource.java:29-35`）：

```
生物群系坐标×4 → worldX/worldZ → Terrain.sample().base()
  → palette.get(地貌序数*4 + climate().variant())      # :34
```

- 断言 16 项：`:20`（`"Expected 16 climate/landform biomes"`）、`RemoteGenerator.java:56`。
- 地貌序数：`core/Landform.java:3-9`（0 INSELBERG / 1 RIFT / 2 KARST / 3 PILLARS）。
- **当前默认世界的气候是硬编码常量**：`MetricProcessedTerrainSource.java:22` `ADAPTER_CLIMATE = new Landscape.Climate(0.5, 0.5)` → `variant()==2` → **米制世界只会出 4 个 `<地貌>_temperate`**。源码 `:131` 与 `docs/metric-minecraft-consumer.md:30-35` 都逐字承认「来源里没有气候字段」「这是显式适配器策略」。
- 16 份 biome json：`src/main/resources/data/remotemountains/worldgen/biome/`，**从原版逐字拷贝**（`tools/create_resources.py:19,26-31`：snowy←snowy_plains / arid←desert / temperate←plains / humid←forest）。
- **分档规则**（`core/Landscape.java:7-9`）：
  ```java
  public int variant(){return temperature<.28?0:rain<.34?1:rain>.64?3:2;}
  ```
  0 冷 / 1 旱 / 2 温 / 3 湿。**三个阈值全仓只此一处，无 Köppen/Holdridge 之类资料出处 = 纯工程假设。** 顺序陷阱：温度档优先，且 `rain<.34` 判在 `rain>.64` 之前 →「低温+高湿」落冷档。
- 纪律：`CONTEXT.md:31-32` 强调「地貌群系**不等同于** Minecraft biome」；`expansion-assessment-20261019.md:95` 建议「**复用已冻结的 `variant()` 4 档语义与 16 群系资源，不新增群系定义**」。

---

## 4. 待拍板项

### D1（**最高优先，决定后续全部工作**）：「无限时间」指哪一种？

| 选项 | 含义 | 代价 |
|---|---|---|
| **D1a** 无限世界按需生成 | 任意坐标都能按需出该处河网，且**窗口外延续、加载顺序无关、跨窗一致** | 要解决本文件 §2.2 的不一致；对应 `CONTEXT.md:71-88` 的规划域路线 |
| **D1b** 有限域拉长时间轴 | 在现有有限域上跑更多月份/更长水账与演进 | 不碰空间一致性；`hydrology_seasonal.py` 已是 12 月周期，拉长要先定「演进」含义 |
| **D1c** 两者都要 | 先按需空间、再加时间 | 最大工程量 |

### D2：气候以哪一套为准？

- **D2a** 噪波气候为产流真源，**先补缺口**（纬度 + 迎风背风）
- **D2b** TD 5 通道为准，**接回被丢弃的 β 通道**
- **D2c** 维持分工（噪波管降雨产流，TD 只作模型条件输入，不追求统一）
- **D2d** 本轮不碰气候

### D3：Minecraft 群系要不要真接上气候？

- **D3a** 维持现状（承认是适配器占位，只出 4 个温带）
- **D3b** 把气候归一化后喂进 `Climate.variant()`，让 16 档活起来
- **D3c** 重做映射（**与 `expansion-assessment:95` 的建议冲突**）
- **D3d** 本轮不碰群系

### D4：按需生成的单元与衔接走哪条路？

- **D4a** 沿用现有宏观格（320 km）+ **离线文件**交付
- **D4b** **把河网加进 loopback HTTP**，让 Minecraft 端按需请求
- **D4c** 先只做「可重复的按需离线生成」，衔接之后再定

---

## 5. 已知硬约束（不属拍板项，实现时必须遵守）

- 新河网算法只进 `terrain_pipeline/surface_rivers/metric_*`；**不动 Java/Mod/默认世界**；不在旧 `surface_rivers/*.py`、`rainfall_runoff.py`、`real_dem_rainfall_routing.py`、`mountain_lake_coupling.py` 上扩第二条主线；**不写 `verification/`**。
- 域外半格余量、六源冻结计划顺序、`valid_mask` 全覆盖等既有契约不得静默放宽。
- `docs/metric-minecraft-consumer.md` 是 Java 默认指向的**最新**说明；`README.md` / `IMPLEMENTATION_STATUS.md` 对它的描述已过时（待另案修正）。

---

## 6. 本轮未做

- 未改任何代码；未新增 `metric_*` 模块；未写 `verification/`。
- 未做规模/性能验收。
- 未处理 `README.md` / `IMPLEMENTATION_STATUS.md` 的时点过时（已登记为另案）。
