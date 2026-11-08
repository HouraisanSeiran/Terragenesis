# 河网中心线自然度根因审读（实测版）

日期：2026-10-18
状态：审读报告 + 可复现对照实验。本次审读本身未修改任何仓库源码；另有单独一轮 A-P0 实施（见 §7-P0）已完成，身份升 v7。

> **后续进展（2026-10-18，同日）**：本报告 §7 的 **P0 已实施**。
> 实施中发现两个与本报告建议不同的必要修正（声明上限不能是硬墙；上限只约束可移动节点），
> 落点、验收证据与回归结果见 `docs/river-algorithm-improvement-list-20261018.md` 的「A-P0 实施状态」、
> `docs/adr/0002-centerline-entry-independent-turn-ceiling.md` 与
> `verification/td-terrain-generated-rivers/CENTERLINE-V6-SUPERSEDED.md`。
> P1/P3/P4 与 A-P2 尚未实施。

---

## 0. 结论摘要

| # | 结论 | 证据强度 |
|---|---|---|
| 1 | **中心线改善的停止条件被锚定在“参考实际路径”上**，而不是物理或曲率目标。参考路径更差时，更优候选被拒绝，搜索提前结束。 | 代码硬读 + 台账实证（**确定**） |
| 2 | 转角上限用 `ordinary`/`junction` 的 **max 与 p95 四个数**做全局互斥。实测中它是**强约束**（占台账拒绝量的 10%，矩形 2:1 台阶上 146 次试错里 68 次被它否掉），但**不是分类式死锁**。 | 台账 + 对照实验（**确定**） |
| 2b | **被否定的假设**：“理想平滑候选必被转角纪律拒绝”。我专门检验了它，**假设不成立**——纯 2:1 台阶上直线化候选完全合法（§2.4）。原报告曾把此假设当结论，已撤回。 | 对照实验（**阴性结果**） |
| 3 | 起点选择（传不传 `reference_points`）能让同一目标停在两个不同状态：台阶起点下接受 6 步后最大转角仍 90.00°、能量一点不降；八遍初始化起点下降至 34.30°、能量降至 7.9%。 | 对照实验（**确定**） |
| 4 | **静默拒绝**：均值下降门槛与接受数不匹配，被丢弃的候选既不入 `refused_steps` 也不入 `accepted_steps`，台账低估真实试错量 2–3 倍。 | 运行时注入计数（**确定**） |
| 5 | 命名/报告口径错位：“转角不得超过参考实际路径”被读成自然度工程结论，实际是“不许比参考路径更差”。 | 代码 + 既有报告对照（**确定**） |
| 6 | **哪个预算在起作用是实例相关的**：真实路由算例里抬升预算是主约束（放宽到 6 m 使 max 71.29°→33.27°、能量 −91%）；但同一改动在平缓合成谷地里毫无效果，而**移除转角上限会变差**（能量 +37%）。两个门都是**相对基线设定的实例相关锥**，不是通用结构死锁。 | 对照实验（**确定**） |
| 7 | 三角洲候选分汊的单点干床归零、接受阈值写死、证据串写死 30 m 栅格——已在代码中确认。 | 代码硬读（**确定**，非本次实测） |

一句话：**当前形状搜索的问题不是某个阈值调得不对，而是“什么叫可接受”这件事完全由参考路径定义、而且部分候选悄悄消失。基线越好、门越紧、行为越难复现；而基线质量由“传没传 `reference_points`”决定。**

---

## 1. 实验装置（可复现）

全部探针已归档到工程内（会话临时目录会清空，报告要能自证）：

```
.scratch/centerline-naturalness-audit-20261018/
  analyze_centerline.py          解析单个策略台账（只读）
  analyze_ledgers.py             全仓台账聚合（扫 8068 个 json → ledger_aggregate.json）
  ledger_aggregate.json          139 份台账的拒绝原因/参考策略/试验预算汇总（后续 §2.3 引用的数据）
  probe_centerline_real.py       真实路由 + 真实 shape_centerline，四变体消融
  probe_acceptance.py            起点依赖对照 + 静默拒绝计数
  probe_p95_lock.py              自指上限的验证（§2.4，否定假设）
  probe_centerline_budget.py     抬升预算的无路由简化对照
  probe_centerline_ablation.py   首版消融探针（保留，见 §10 方法论）
  probe_v7_entry_independence.py  A-P0 实施后的入口无关验收（三入口同一可行集）
```

| 探针 | 对应章节 |
|---|---|
| `probe_centerline_real.py` | §5.1 |
| `probe_acceptance.py` | §3、§4 |
| `probe_p95_lock.py` | §2.4 |
| `probe_centerline_budget.py` | §5.2 |
| `analyze_centerline.py` | §2.3（单算例台账） |
| `analyze_ledgers.py` + `ledger_aggregate.json` | §2.3 的全仓补测 |

运行方式（工程自带解释器）：

```powershell
& runtime\venv\Scripts\python.exe <探针.py>
```

变体均通过**运行时读取源码文本 + 替换单点字符串 + `exec`**实现，仓库文件零改动；若替换串出现次数不为 1 立即断言失败，防止误伤。

---

## 2. 发现：停止条件锚定在参考路径上

### 2.1 代码

`terrain_pipeline/surface_rivers/metric_terrain_centerline.py:131-144`，`admissible()`：

```python
for kind in ("ordinary", "junction"):
    for metric in ("maximum_degrees", "p95_degrees"):
        if turns[kind][metric] > baseline_turn[kind][metric] + 1e-7:
            raise ValueError(kind + " " + metric + " exceeds reference actual path")
```

`baseline_turn = turn_summary(baseline, receiver)`（`:108`），而 baseline 来自 `:96-107`：

- `reference_points is not None` → **直接用参考路径**（`reference_policy: "saved baseline actual nodes"`）
- 否则 → 八遍初始化（`deterministic legacy eight-pass six-metre initialization`）

调用方 `metric_td_generated_rivers.py:645-657` 把 `reference_points` 一路传下来，默认不传。

### 2.2 后果一：锚比候选差时，改善被判为回归

仓库自己的台账 `verify_batched_small_bed.json`：

```
baseline_turns.ordinary = maximum 63.752  p95 62.567
```

台账里根本没有“junction”类别（max/p95 = 0），说明该算例**没有汇流三段转角**，ordinary 是唯一控制量。也就是说：**一个相对实例逐边改善的候选，只要其某条普通边的绝对转角超过 63.752°/62.567°，就被拒绝。**

这与“曲率连续”的工程目标是互相矛盾的——一个把 90° 台阶摊成两组 45° 的候选，其相对转角必然落在 90° 附近，越“抹平”越容易越界。

### 2.3 后果二：四个数全局互斥（强约束，但不是死锁）

`maximum_degrees` 是**全体节点上的最大值**（`metric_terrain_centerline.py:70-79`）。移动节点 i，可能把节点 j 的相对转角从 60° 抬到 64°，于是整批被否。台账实证（`diagnose_s0c24_overlap.json`）：

```
accepted_steps = {terrain: 24, smooth: 173, local: 197}
refused_steps  = 1214
   phase smooth   1177
   reason "source elevation or validity corridor"                1092
   reason "junction maximum_degrees exceeds reference actual path"  82
   reason "ordinary p95_degrees exceeds reference actual path"      36
   reason "ordinary maximum_degrees exceeds reference actual path"   4
final_turns.ordinary = maximum 39.599  p95 25.236   (基线 65.690 / 31.944)
```

即：**这一个算例的 1214 次拒绝里 122 次来自转角纪律（约 10%），1092 次来自高程走廊（约 90%）。**

> ⚠️ **单算例不可外推（2026-10-18 补测）。** 随后把**全仓所有台账**聚合重算（脚本 `analyze_centerline.py` 的聚合版，扫 8068 个 json、53 个文件、**139 份台账实例**）——这是本报告唯一一次跨算例统计，结论与上段**不同**：
>
> | 拒绝原因 | 次数 | 占比 |
> |---|---:|---:|
> | 走廊 / 有效性（`source elevation or validity corridor` 等） | 11088 | **63.1%** |
> | 转角纪律（`{ordinary,junction} {maximum,p95}_degrees exceeds reference actual path`） | 6403 | **36.4%** |
> | 切深预算（`... incision ... exceeds 4m budget`） | 92 | 0.5% |
> | 合计 | 17583 | 100% |
>
> 据此修正：
>
> - 走廊仍是**第一大**门（63%），把自然度全部归因于“转角上限卡死”仍**不成立**。
> - 但转角纪律**绝不是可忽略的 10%**——全仓口径 **36.4%**，且是**一票否决、不可协商**的形式（§2.2）。本报告初稿只引了对己有利的那一个算例，§10 的方法论教训在同一份报告里又出现了一次。
> - 139 份台账里 **127 份用八遍初始化**（未传 `reference_points`），仅 **6 份**用 `saved baseline actual nodes`。§3 的“起点决定终点”是**真实机制**，但它在已归档证据里是**少数入口**——不要把全部问题都归到 `reference_points`。
> - `smooth_candidate_trials == maximum_smooth_candidate_trials`（试错预算耗完）出现在 **8/139** 份。

- 转角纪律**代价不成比例**：拥有“一票否决、不可协商”的权力（§2.2），而最终结果里 ordinary max 从 65.690° 降到 39.599° 主要靠 terrain 阶段那 24 步。

### 2.4 【重要】被否定的假设：理想候选并非必被拒绝

我最初推测“越平滑越容易越界，因此转角纪律是分类式死锁”。**专门检验后该假设不成立**（`probe_p95_lock.py`）：

纯 2:1 矩形台阶（80 节点，每节点转角恰好 90°）：

```
baseline ordinary: count 78  max 90.0000  p95 90.000000   能量 78.000000
ideal    ordinary: count 78  max  0.0000  p95  0.000000   能量  0.000000

admissible() 转角规则对 ideal 候选的判定：
   ordinary maximum_degrees   0.0000 <= 90.0000001   允许
   ordinary p95_degrees       0.0000 <= 90.0000001   允许
   junction maximum_degrees   0.0000 <=  0.0000001   允许
=> ideal 候选被出厂规则允许
```

真实搜索在同一算例上拿到 **78/78 节点全部接受**，max 21.40°/p95 15.93°、能量 0.0472（下降 99.94%），146 次试错中 68 次被转角纪律否掉。

**结论修正**：

1. 锚是**自指**的（上限 = 基线自身），所以理论上永远存在越来越好的候选；不存在“必然触发”的隐形天花板。
2. 但锚使**接受带变成不对称**：一个把 90° 台阶摊成 45°+45° 的候选，其**相对转角**约 90°（两段方向间的夹角），刚好卡在上限 90.0000001 的刀锋上，余量只有 1e-7 弧度级。
3. 于是结果取决于“基线里到底有没有超过 63.75° 的边”，而不是取决于目标曲率——**对于恰在刀锋上的台阶（>63.75° 基线 + 90° 级相对转角），纪律会持续否决真实改善**（§2.2）；对于纯 90° 基线（上限也是 90°），纪律反倒几乎不挡事。

也就是说：**风险集中在“基线本身已经很好”的算例上**——那里上限被压到 30–50° 级，任何把残余折角摊开的重采样都会越界。这正好与 §3 的起点依赖叠乘。

---

## 3. 发现：起点选择决定终点

同一地形、同一原始路径、同一 `corridor_m`，只改 `reference_points`：

| 变体 | 起点 | 接受步 | ordinary max / p95 | 转角能量 | 台账拒绝 |
|---|---|---:|---|---:|---:|
| D1a | 原始 D8 台阶（含 90° 折角） | `{terrain:1, smooth:2, local:3}` | **90.00 / 0.00 → 90.00 / 0.00** | **1.00000 → 1.00000** | 53 |
| D1b | 八遍初始化（`reference_points=None`） | `{terrain:0, smooth:2, local:2}` | 71.29 / 0.00 → **34.30 / 0.00** | 0.46159 → **0.03696** | 29 |

读法：

1. D1a 报了 6 次“接受”、平均转角从 1.14° 降到 1.15°，但**最大转角和转角能量一动不动**——接受的是装饰性位移。
2. D1b 的转角上限**更严**（71.29 而不是 90.00），结果却好得多。原因是锚同时决定起点：**锚松→起点脏→候选被锁死；锚紧→起点干净→搜索有改善余地。**
3. 因此“不许回归”这条纪律在起点差时会**主动中止**整个搜索，而调用方只记录 `reference_policy` 字符串，不记录它的数值后果。

工程含义：想让中心线变好，**先把起点弄干净**（或让上限与起点解耦），而不是去调 `iterations`、`corridor_m` 或上采样。

---

## 4. 发现：静默拒绝（账目失真）

`metric_terrain_centerline.py:245`：

```python
if float(np.mean(current_source - sampled)) <= 1e-10:
    continue
```

与相邻分支（`:241-243` 带 `refused.append`）不同，这里**直接丢弃**：既不进 `refused_steps`，也不进 `accepted_steps`。

运行时注入计数（探针 D2）：被该门槛吞掉的候选 **52 个**；同一算例台账里记录的拒绝只有 **29 个**。

→ **台账反映的真实试错量被低估 2–3 倍。** 对“失败证据必须保留”的纪律（`CONTRIBUTING.md:37`）而言，这是一个可修的账目漏洞：不是隐藏失败，而是**没有记录失败**。

同类静默早退还有两处，均不写原因：

- `metric_terrain_centerline.py:27-51` 八遍初始化 `if not chosen: break`
- `metric_channel_geometry.py:563-600` 坐标下降 `if not changed and iteration >= 4: break`

---

## 5. 发现：两个预算的作用是实例相关的

这是本报告**修正最多**的一节。我先验怀疑“抬升 0.25 m 预算过紧”，也用两个算例分别检验了它，结果并不一致。

### 5.1 真实路由算例（基线 ordinary max 71.29° / p95 11.90°）

`SMOOTH_SOURCE_RISE_M = 0.25`（`metric_terrain_centerline.py:12`）与 `ceiling = np.minimum(original_source + 0.5, floor_source + SMOOTH_SOURCE_RISE_M)`（`:162`）的消融：

| 变体 | 接受步 | ordinary max | 转角能量 |
|---|---:|---:|---:|
| A 出厂设置 | `{terrain:2, smooth:11, local:13}` | 71.29 → 68.18 | 0.47506 → 0.39645（−16.5%） |
| B 仅抬升预算 → 6 m | `{terrain:2, smooth:16, local:18}` | 71.29 → **33.27** | 0.47506 → **0.04303（−90.9%）** |
| C 仅上限 → 解析 90° | `{terrain:10, smooth:27, local:35}` | 71.29 → **78.87（变差）** | 0.47506 → **0.65272（+37%）** |
| D 两者都改 | `{terrain:10, smooth:30, local:38}` | 71.29 → 33.37 | 0.47506 → 0.04139 |

**这个算例里真正的瓶颈是抬升预算（B），而转角上限是保护性的（C 移除后变差）。**

### 5.2 平缓合成谷地（基线 ordinary max 21.35°）

同一套消融在“谷底缓慢弯曲 + 起点已经基本顺滑”的算例上，A/B/C 三组输出**逐字相同**（max 21.35→9.41，能量 0.0289→0.0010）。

→ 该算例下**两个门都不约束**：起点已有足够余量，不存在“想移却移不动”的需求。

### 5.3 结论

| 算例 | 基线 max 转角 | 卡住的是谁 |
|---|---:|---|
| 平缓合成谷地 | 21.35° | 都不卡（无需求） |
| 真实路由谷地 | 71.29° | **抬升预算**（上限是保护） |
| 纯 2:1 台阶 | 90.00° | **都不卡**（上限自指地也等于 90°） |
| 台账 `verify_batched_small_bed` | 63.75° | 抬升预算 33/33（上限未触发） |
| 台账 `diagnose_s0c24_overlap` | 65.69° | **走廊 1092 / 转角 122** |

所以真正稳定的模式不是“某个数字太紧”，而是：

> **两个门都以基线为绝对参照系（上限=基线，抬升=基线+0.25m）。基线越好，两个门都越紧；而基线的质量本身由“传没传 `reference_points`”决定（§3）。于是同一个算法在不同入口下表现出完全不同的行为，工程上看到的就是“参数怎么调都不对”。**

→ 因此 §7 的 P0/P1 应合并：**先固定一个合格的、实例无关的参照系，再谈任何预算数值**。在此之前调 `SMOOTH_SOURCE_RISE_M` 或上限数值都是过拟合单个算例。

---

## 6. 发现：候选生成侧的硬台阶（代码确认，非本轮实测）

`metric_integrated_delta.py:374-375`：

```python
if np.any(~np.isfinite(depth)) or np.any(depth <= 1e-6):
    return 0.0, 0.0
```

沿程**任一点**干床 → 整段流量与水深归零。后果：残差面出现台阶，`least_squares` 在干床边界不连续；床面 1 mm 级变化可让某分汊从“有流量”跳到“零流量”。`docs/delta-integrated-completion-20261017.md:22` 自述的“干床零流量平台”就是它。建议改为有效过水断面（干段阻力贡献 0 或按临界水深处理），并把策略写进 `ALGORITHM` 身份。

同族问题：

- `metric_terrain_centerline.py:245` 的均值门槛（§4）
- `metric_integrated_delta.py:484-485` 终端分汊按 `widths / widths.sum()` 预分配，与 `docs/delta-integrated-completion-20261017.md:22` 声称的“替代固定份额”口径不一致
- `metric_river_release.py:234` 写死 `"spacing_m": 30.` 与 `"CRS unresolved"`，而 `TerrainGrid` 已带 `dx_m/dz_m/crs` 契约 → 非 30 m 来源会静默错位

---

## 7. 建议（按“收益/成本/风险”）

### P0 — 先固定参照系（上限与起点解耦，合并原 P0/P1）

> **状态（2026-10-18 同日实施）**：已实施完成，身份 v7。下文保留当时的设计依据与建议；
> 实际落地时对两条建议做了修正（见页首后续进展链接）。

§5.3 表明：**两个门都相对基线定标，而基线由入口决定**。所以第一步不是改数字，而是**取消“以基线为上限”这条自指规则**，让不同入口走同一条路径。

**该规则在仓库里存在三份实现，必须同时改（漏一处等于没改）：**

| 位置 | 作用 |
|---|---|
| `metric_terrain_centerline.py:139-142`（`admissible`） | 轮廓搜索期间的主门，用 `baseline_turn` |
| `metric_td_generated_rivers.py:670-674`（`validate`） | **横向切深预算修复阶段**的第二道门，用 `policy["baseline_turns"]`（本报告初稿遗漏） |
| `tools/diagnose_td_river_bottom_budget.py:145` | 诊断工具里的副本 |

**影响面（已核实）**：`shape_centerline` 的生产消费者只有 `metric_td_generated_rivers.py:653` 与 `tools/diagnose_td_river_bottom_budget.py:127`；`tests/test_metric_terrain_centerline.py` 有 9 处调用，**其中 3 处直接断言这条自指规则**（`test_all_junction_donors_are_counted_and_cannot_regress`、`test_curvature_hotspots_cover_remote_nodes_and_accept_multiple_per_round`、`test_rejected_high_turn_does_not_prevent_later_ordinary_candidates`）——改机制须同步改测试，符合 `CONTRIBUTING.md:31`（算法身份变更单独记录）与 `CONTRIBUTING.md:37`（失败证据不得隐去、`v5` 不得继承 `v4` 证书）。

- **落点**：`metric_terrain_centerline.py:131-144`（`admissible`）、`:96-107`（baseline 选择）；`metric_td_generated_rivers.py:645-657` 与 `:670-674`
- **做法**（两件必须同时做）：
  1. **起点归一**：无论是否传 `reference_points`，搜索起点一律先用八遍初始化得到干净 baseline；`reference_points` 只用于验收对齐，不充当搜索起点。
  2. **上限归一**：以**分段单段解析上限**（如单段转角 ≤ 90°、或曲率半径 ≥ 走廊宽）作为硬约束；把“参考 max/p95 回归”**降级为诊断字段**。若仍需保留回归纪律，改用**总转角能量不上升**（`all_donor_turn_energy` 已是标量，天然避开 max 的全局互斥）。
- **依据**：§3 的 D1a/D1b 分裂（同算法、同参数、仅入口不同 → 能量 1.000 vs 0.037）；§2.4 确认自指上限存在刀锋余量（仅 1e-7 弧度级）；§5.1 确认单改任一门都会过拟合单算例。
- **性质**：结构必改（不是调参）
- **对既有证据的影响**：会改变 `ALGORITHM` 身份 → **旧证书不得继承**（符合 `CONTRIBUTING.md:37`，需显式声明）
- **验收方式**：同一实例分别走“台阶起点”与“干净起点”两条入口，要求最终 max/能量落在同一区间（当前差距 27 倍）

### P2 — 补上三处静默拒绝的记录

- **落点**：`metric_terrain_centerline.py:245`、`:27-51`、`metric_channel_geometry.py:598`
- **做法**：每处 `break`/`continue` 都追加 `refused_steps`（带 `silent=True` 与计数），并在 policy 里输出 `status: converged | iteration_limit | no_improving_candidate`。
- **性质**：账目可修，**不影响数值结果**
- **价值**：让“自然度不通过”可归因；D2 显示低估 2–3 倍

### P2b — 修当前最脏的 20 个回归（新增，已实测）

后台跑完 414 个模块：**394 OK，20 FAILED**（结果在 `.pytest_cache/fullrun/results.json`）。非 OK 清单：

```
test_audit_td_generated_rivers            test_hybrid_river_hydraulics(_v3..v8)  (共7 个)
test_hybrid_river_sections_v2            test_metric_fluvial_morphodynamics
test_metric_fluvial_water_repair         test_metric_td_generated_rivers
test_single_domain_shallow_water_accelerated_v7  test_surface_cross_domain
test_surface_domain_mosaic               test_surface_domain_prepare
test_surface_engineering_prepare         test_surface_land_coverage
test_surface_review_export               test_surface_river_diagnostics
```

注意：**这 20 个失败里可能有一部分是我的探针之外的既有状态**（仓库工作区本身有大量未提交修改）。但这意味着：**当前工作区不具备“全绿基准”**，任何“改善自然度”的改动都无法与干净基线对比。**应先建基线，再改算法。**

### P3 — 走廊主因专项

- 台账里 **1092/1214** 的拒绝来自“source elevation or validity corridor”。这是 §2.3 的真实主因，值得单独一轮诊断：区分“抬升 0.5 m 超限”“valid_mask 越界”“原走廊越界”三类，各自计数。
- **性质**：先诊断，后决定是否调参

### P4 — 三角洲侧三项小修

- 单点干床（`metric_integrated_delta.py:374-375`）：中成本，影响可解性（残差连续性）
- 写死 30 m 栅格（`metric_river_release.py:234`）：小成本，消除静默错位
- 分汊份额口径（`:484-485`）：小-中成本，统一到阻力-连续性求解

### 不建议现在做

- 放宽 `corridor_m`（会把河道推到非谷底，与“原走廊”纪律冲突）
- 给端口加真回水/潮汐（工程量大，且潮汐按用户要求需先讨论）
- 新增第四套洼地填充（`docs/architecture/river-module-classification-20261009.md:32` 已禁止）

---

## 8. 与既有结论的关系

| 既有说法 | 本报告的态度 |
|---|---|
| “栅格折角/笔直路径是调参不可解的结构问题” | **同意，但要换机制**：不是“优化不够强”，而是**停止条件由参考路径定义**（§2、§3） |
| “转角上限卡死自然度” | **需要修正（且初稿引错了比例）**：单个算例里转角纪律只占 122/1214，但**全仓 139 份台账口径下占 6403/17583 = 36.4%**，是第二大门；主因仍是走廊（63.1%）。但转角纪律**一经触发即不可协商**，形式必须改（§7 P0）。 |
| “失败证据必须保留” | **一处漏洞**：§4 的三处静默拒绝没有留证 |
| “抬升 0.25 m 预算过紧” | **实测否定**：放宽到 6 m 只换来 1 个接受步；但**与上限形式替换耦合后仍有价值**（§5） |

---

## 9. 未验证 / 存疑（明确标注）

- 全部对照均在**合成谷地 + 真实路由**上完成，规模（60–120 节点）远小于生产算例（六源 4767 条超预算拒绝）。**结论是新声明的机制候选，不是生产验收证据。**
- “junction 类别是否存在实例”只从台账（`maximum_degrees = 0.0`）推断，未在真实六源输出上复核。
- §5 变体 C（解析 90° 上限）的**变差**结果只用了一个算例一次运行，未做多算例重复，方向可靠、幅度不可引用。
- §6 的干床、30 m 栅格、分汊份额均为代码硬读 + 既有报告交叉，未做本轮复现。
- 本次审读基于 2026-10-17 代码与报告；期间并行会话已推进三角洲任务 10（`docs/delta-adaptive-distributaries-20261018.md`）。若重心转向三角洲验收，本报告中心线结论**不受影响且优先级更高**——它是所有明渠几何的上游。

---

## 10. 附：本报告的方法论说明

本报告初稿中有 **两条结论被自己的实验推翻**，已在上文撤回并改写：

| 初稿结论 | 检验结果 | 现文位置 |
|---|---|---|
| “越平滑越容易越界，转角纪律是分类式死锁” | **不成立**：纯 2:1 台阶上直线化候选完全合法，78/78 节点全接受 | §2.4 |
| “抬升 0.25 m 预算不是瓶颈”（基于第一个算例） | **片面**：真实路由算例里它就是主约束（max 71.29°→33.27°） | §5 |

两次都是**先写结论、后做检验**，检验把它们否掉了。这两条保留在文里而不是删掉，因为本工程本身就有“保留失败证据”的纪律（`CONTRIBUTING.md:37`），而且它们的否定过程本身就是主要证据（§2.4/§5.3 的表格都直接来自这两次检验）。

## 11. 附：本报告未做的事

- 未修改 `terrain_pipeline/` 任何源码
- 已运行完整回归（414 模块：394 OK / 20 FAILED），结果存 `.pytest_cache/fullrun/results.json`
- 未删除、未覆盖任何 `verification/` 证据
- 未把探针写入工程目录，全部位于会话临时目录
