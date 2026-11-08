# 河流算法改进清单（按影响/成本排序）

日期：2026-10-18
状态：审读产物 + A-P0 实施记录。§1 的 A-P0 已于 2026-10-18 实施（身份 v6→v7），其余条目仍为审读建议、未改动源码。
配套证据：`docs/centerline-naturalness-audit-20261018.md`（含 7 个可复现探针，位于 `.scratch/centerline-naturalness-audit-20261018/`）。

---

## 0. 一句话

**当前中心线的「自然度不通过」不是阈值调得不对，而是「什么叫可接受」完全由参考路径定义（自指门），而且部分候选被静默丢弃。**先修这两件事，再谈任何数值。

但也要诚实地记住（全仓 139 份台账、17583 次拒绝的口径）：

| 拒绝原因 | 占比 | 性质 |
|---|---:|---|
| 走廊 / 有效性 | **63.1%** | 真实物理约束（抬升预算 / valid_mask / 原走廊） |
| 转角纪律（自指） | **36.4%** | **非物理，是相对基线的纪律，应降级为诊断字段** |
| 切深预算 | 0.5% | 真实几何约束 |

→ 转角纪律占了三分之一以上且形式不可协商，改它收益大；但走廊是最大头，不能只改转角就以为完工。

---

## 1. 算法层

### A-P0【结构必改，收益最大】取消「以基线为上限」的自指接受规则

**问题**：接受判据写成「不许比参考路径更差」，而不是物理或曲率目标。

```python
# metric_terrain_centerline.py:139-142
for kind in ("ordinary", "junction"):
    for metric in ("maximum_degrees", "p95_degrees"):
        if turns[kind][metric] > baseline_turn[kind][metric] + 1e-7:
            raise ValueError(kind + " " + metric + " exceeds reference actual path")
```

**为什么是结构问题而不是调参问题**（三条已实测证据）：
1. 上限是**自指**的（上限 = 基线自身），所以「基线质量」直接决定搜索空间；
2. 同一算法、同一参数，**只改起点**（传不传 `reference_points`），结果差 27 倍——转角能量 1.000 一动不动 vs 降至 0.037（§3 的 D1a/D1b）；
3. 它把「把 90° 台阶摊成两组 45°」这类**真实改善**判为回归（两段方向夹角仍约 90°，卡在上限刀锋上，余量仅 1e-7）。

**该规则在仓库里存在三份实现，必须同时改（漏一处等于没改）**：

| 位置 | 作用 |
|---|---|
| `terrain_pipeline/surface_rivers/metric_terrain_centerline.py:139-142` | 轮廓搜索期主门，用 `baseline_turn` |
| `terrain_pipeline/surface_rivers/metric_td_generated_rivers.py:670-674` | **横向切深预算修复阶段**的第二道门，用 `policy["baseline_turns"]` |
| `tools/diagnose_td_river_bottom_budget.py:145` | 诊断工具副本 |

**做法（两件必须同时做，只做一件会过拟合单个算例）**：
1. **起点归一**：无论是否传 `reference_points`，搜索起点一律先用八遍初始化得到干净 baseline；`reference_points` 只用于验收对齐，不充当搜索起点。
2. **上限归一**：以**分段单段解析上限**（如单段转角 ≤ 90°，或曲率半径 ≥ 走廊宽）作为硬约束；把「参考 max/p95 回归」**降级为诊断字段**。若仍需保留回归纪律，改用**总转角能量不上升**（`all_donor_turn_energy` 已是标量，天然避开 `maximum_degrees` 的全局互斥）。

**影响面（已核实）**：`shape_centerline` 的生产消费者只有 `metric_td_generated_rivers.py:653` 与 `tools/diagnose_td_river_bottom_budget.py:127`；`tests/test_metric_terrain_centerline.py` 9 处调用中 **3 处直接断言自指规则**（`test_all_junction_donors_are_counted_and_cannot_regress`、`test_curvature_hotspots_cover_remote_nodes_and_accept_multiple_per_round`、`test_rejected_high_turn_does_not_prevent_later_ordinary_candidates`）——须同步改测试。

**对既有证据的影响**：会改变 `ALGORITHM` 身份（`anchored-staged-…-sweep-v6` → v7）→ **旧证书不得继承**，符合 `CONTRIBUTING.md:31,37`，需显式声明。同时要把「v6 证书」标为 superseded 而非删除（失败证据保留纪律）。

**验收方式**：同一实例分别走「台阶起点」与「干净起点」两条入口，要求最终 max/转角能量落在同一区间（当前差距 27 倍）。

成本：中——三处代码 + 3 个测试 + 身份声明；风险：中（会改变已冻结的穴面几何，需重跑既有验收）。

#### A-P0 实施状态（2026-10-18，已实施）

**已落地**，身份由 `…-ordinary-sweep-v6` 升为 `…-analytic-turn-bound-v7`（`SUPERSEDES_ALGORITHM` 常量同文件声明）。

| 落点 | 改动 |
|---|---|
| `terrain_pipeline/surface_rivers/metric_terrain_centerline.py` | 新增 `ANALYTIC_TURN_BOUND_DEGREES`、`node_turns`、`movable_turn_maxima`、`turn_ceiling`、`enforce_turn_ceiling`、`anchor_turn_exemption`；`admissible` 改调新门；取消 max/p95 四数互斥 |
| `terrain_pipeline/surface_rivers/metric_td_generated_rivers.py:673` | 第二道门改用 `policy["effective_turn_ceiling_degrees"]`，不再用 `policy["baseline_turns"]` |
| `tools/diagnose_td_river_bottom_budget.py:146` | 改用 `turn_ceiling(legacy, receiver)` |
| `tests/test_metric_terrain_centerline.py` | 改写 3 个直接断言自指规则的用例；新增 3 个断言新机制的用例 |
| `docs/adr/0002-centerline-entry-independent-turn-ceiling.md` | 决策记录 |
| `verification/td-terrain-generated-rivers/CENTERLINE-V6-SUPERSEDED.md` | v6 证书 supersession 声明（12 份，字节未改） |

**两处设计修正（与本文原建议不同，已由实测否决原方案）**：

1. **声明上限不能做成一次性硬墙**。原建议写「单段转角 ≤ 90° 作为硬约束」；实测把它直接当硬墙时，脏基线下整批候选被否、**接受 0 步**（搜索被堵死）。最终形式是
   `turn_ceiling(baseline) = max(声明上限, 基线自身 movable 转角最大值)`——声明上限是**严格程度的上限封顶**，既保证入口无关，又保证脏基线仍有单调下降余量。
2. **上限只作用于可移动节点**。源/汇流/终点锚点不可移动，其宽转角属不可变原始栅格；它改走 `anchor_turn_exemption` 诊断字段，不再毒化可行性。

**验收证据（可复现）**：`.scratch/centerline-naturalness-audit-20261018/probe_v7_entry_independence.py`（输出存 `.pytest_cache/ap0-entry-independence.txt`）。
同一实例三种入口（传原始台阶参考 / 不传参考 / 传**被扰动**的参考）
→ 最终路径**逐节点完全相同**（偏移 0.000e+00），`accepted_steps` 与有效上限也完全相同。
对照改动前：同算法同参数仅换入口，转角能量差 27 倍（本文 §3 D1a/D1b）。
**本文「验收方式」一条已满足。**

**回归**：24 个受影响模块，结果见 `.pytest_cache/ap0-regression-3.txt`——22 个 OK；
`test_metric_td_generated_rivers` 与 `test_audit_td_generated_rivers` 各 3 error，
与**改动前基线逐条一致**（`results3.txt` 同为 FAILED、同一条 `HiGHS Status 0: Not Set`、同为 3 error），
属 A-P2 已定因的既有技术债，非 A-P0 引入。


---

### A-P1【账目可修，不影响数值】补上三处静默拒绝的记录

`metric_terrain_centerline.py:245` 的均值门槛与相邻分支（`:241-243` 带 `refused.append`）不同，直接 `continue`：既不进 `refused_steps`，也不进 `accepted_steps`。

运行时注入计数（探针 D2）：被吞掉 **52 个**候选，而同一算例台账只记 **29 个** → **低估真实试错量 2–3 倍**。

同类静默早退无原因记录：
- `metric_terrain_centerline.py:27-51` 八遍初始化 `if not chosen: break`
- `metric_channel_geometry.py:598` 坐标下降 `if not changed and iteration >= 4: break`

**做法**：每处 `break`/`continue` 都追加 `refused_steps`（带 `silent=True` 与计数），并在 policy 输出 `status: converged | iteration_limit | no_improving_candidate`。

为何重要：本工程纪律是「失败证据必须保留」（`CONTRIBUTING.md:37`），但这里不是**隐藏失败**，而是**没有记录失败**——直接破坏自然度问题的可归因性。

成本：小。风险：无（不改数值结果）。

---

### A-P2【先建基线，再改算法】先修全量回归的“非绿基准”与依赖缺失

**这一项与算法无关但优先级很高**：当前工作区不具备「全绿基准」，任何改善自然度的改动都无法与干净基线对比。

**重要更正**：仓库里已有的全量回归结果（`.pytest_cache/fullrun/results.json`）**不可采信**——它的 PowerShell 脚本有 bug（`$ran.Trim()` 对数组报错），导致 **414 个测试模块只落盘了 310 个**，且把 104 个没跑到的模块记成假的 `IMPORT`。报告里「394 OK / 20 FAILED」这个数字实际只覆盖 310 个模块。

本次已重跑（Python 版 runner：`.pytest_cache/fullrun/results3.json` + `results3.txt` + `logs2/`），并按失败原因分类：

| 分类 | 含义 | 处理 |
|---|---|---|
| `IMPORT` | **venv 缺依赖**，不是代码 bug | 装依赖即可，见下表 |
| `FAILED` | 真实失败（部分是已登记的技术债，部分是环境） | 逐个定因；明细见 `.pytest_cache/fullrun/results3.txt` |
| `OK` / `OK_NOOUTPUT` | 通过 | — |

**venv 缺失依赖（按引用次数）**：

| 包 | 引用处 | 备注 |
|---|---:|---|
| `psutil` | 86 | 资源审计类 |
| `shapely` | 55 | 地下河/几何 |
| `manifold3d` | 23 | 地下河几何 |
| `playwright` | 20 | 浏览器验收 |
| `pytest` | 14 | venv 里没有 pytest（测试靠 `unittest` 跑） |
| `pypdfium2`, `PyPDF2` | 2 | 证据提取 |

另有**未入库的本地包**：`vdm_diffusion`、`terrain_diffusion`、`sr_harness`、`agent_mcp`、`pyDeltaRCM`、`fault_preview`、`river_results`、`global_geometry`。

成本：小（装包）/ 中（本地包入库）。风险：低。

#### A-P2 补充： 20 个 FAILED 已全部定因（含一个新发现的一类）

完整证据：`.scratch/baseline-regression-20261018.md`（本轮新增）。**关键更正：20 个失败里没有一个是「代码写错」。**

| 类别 | 模块数 | 根因 |
|---|--:|---|
| 环境缺依赖 | 11 | `shapely`（8：hybrid_river_hydraulics 族 7 个 + sections_v2）、`pyDeltaRCM`（2）、`psutil`（1） |
| **台账做逐位精确比对 + numpy 2.4.6 改了求和顺序** | 6 | `surface_domain_mosaic.py:367`（详见下） |
| HiGHS 判不可行 | 2 | `metric_design_bed.py:971`（详见下） |
| 冻结 metadata 逐位比对 + 1 ULP 漂移 | 1 | `test_surface_river_diagnostics`（含 2 个失败用例） |
| **合计** | **20** | |

→ **只有 HiGHS 那 2 个是真正的几何/优化问题；其余 18 个都是环境或比对方式问题。**

**★ 新发现（本轮实测）：venv 的 numpy 2.4.6 让 6 个模块同时变红。**

- 6 个模块（`surface_domain_mosaic` / `domain_prepare` / `engineering_prepare` / `land_coverage` / `cross_domain` / `review_export`）全部停在**同一条断言**：
  `surface_domain_mosaic.py:367 raise ValueError("saved volume or Q ledger differs")`。
- 该行用 `fine_mosaic._identity(summary)` 对 `unique_cut_volume_m3` 做 **sha256 逐位**比对，
  而它是 `((h0-h2)[tri].mean(axis=1) * area/2).sum()` 的浮点累加。
- 对同一份冻结证据实测（`verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz`）：

| 解释器 | numpy | stored | recomputed | 相等 |
|---|---|---|---|---|
| runtime\venv | **2.4.6** | 576.8710544290027 | 576.8710544290026 | **False** |
| D:\anaconda | 2.2.6 | 576.8710544290027 | 576.8710544290027 | True |

  差 1 ULP（1.14e-13 m³）。其余五个字段（area/water/Q 三项）逐位相同。
- 推论：**「全绿基准」不是把包装上就有的**——这 6 个模块即使装齐依赖也仍然红。要么把台账比对从 sha256 降为带容差的规范化（不允许删 identity 机制），要么锁死 numpy 版本（`runtime/requirements-lock.txt: numpy==2.4.6` 与冻结证据生成时的环境不一致）。**两者都要做。**

**HiGHS 两个失败的定因边界**：已用 anaconda（scipy 1.16.3）复跑 `tests.test_metric_td_generated_rivers`，**同样 3 error、同一条 message** → **不是 scipy 版本问题**。
属 A8 同族（`docs/td-river-shape-repair-20261012.md:93` 已记 Status 8: Infeasible），新信息是 Status 0 出现在已有 `shape-path` 证据链的回归测试里。
另：`terrain_pipeline/surface_river_diagnostics.py` **在本工作区不存在**，但 `test_surface_river_diagnostics.py` 却站在它上面——是**测试与实现脱节**，不只是数值问题。


---

### A-P3【先诊断再决定】走廊主因专项（全仓 63.1%）

走廊 / 有效性是一等大门（11088/17583），大宽于转角纪律，但在现有台账里被压成**一个字符串**：`"source elevation or validity corridor"`。

**做法**：拆成三类分别计数：
1. 抬升 0.5 m 超限（`original_source + 0.5`）
2. `valid_mask` 越界
3. 原走廊（`corridor_m`）越界

**性质**：先诊断，后决定是否调参。不要直接改 `SMOOTH_SOURCE_RISE_M`（探针已证实它会过拟合单个算例：真实路由算例里它是主约束，平缓合成谷地里毫无效果）。

成本：小（改一行 raise 为带三类的 reason）。风险：无。

---

### A-P4【三角洲侧三项小修】

| # | 位置 | 问题 | 成本 |
|---|---|---|---|
| 1 | `metric_integrated_delta.py:389-390` | 沿程**任一点**干床就整段流量与水深归零，制造残差面台阶；床面 1 mm 级变化可让分汊从“有流量”跳到“零流量” | 中 |
| 2 | `metric_river_release.py:234` | 写死 `"spacing_m": 30.` 与 `"CRS unresolved"`，而 `TerrainGrid` 已带 `dx_m/dz_m/crs` 契约 → 非 30 m 来源会静默错位 | 小 |
| 3 | `metric_integrated_delta.py:499` | 终端分汊按 `widths / widths.sum()` 预分配，与 `docs/delta-integrated-completion-20261017.md:22` 声称的“替代固定份额”口径不一致 | 小–中 |

---

## 2. 工程层（架构债）

### C-1 中心线模块族职责重叠（7 个模块，1500+ 行）

| 模块 | 行数 | 被引用 |
|---|---:|---:|
| `channel_centerline.py` | 314 | 11 |
| `surface_centerline_prepare.py` | 396 | 5 |
| `metric_terrain_centerline.py` | 324 | 7 |
| `frozen_terrain_centerline.py` | 244 | 6 |
| `metric_local_budget_centerline.py` | 188 | 4 |
| `metric_valley_centerline.py` | 181 | 11 |
| `metric_budget_centerline.py` | 149 | 4 |

七个模块都叫 “centerline” 但职责不同（路由中心线 / TD 快照 / 几何搜索 / 预算 / 谷底）。当前无可执行的合并建议——存在版本族（v2..v10）是因为保留了证据链，**不能简单删**。建议只做一件事：在 `docs/architecture/river-module-classification-20261009.md` 里给每个模块写一行“职责 + 唯一消费者 + 可否退役”，先把重复性变成可审计的。

### C-2 两条互不相通的三角洲路径

`metric_delta.py`（候选/契约演示：折线分汊、权重只依赖几何、`hydraulic=False`）与 `metric_integrated_delta.py` / `metric_fluvial_morphodynamics.py`（生产：阻力求解）是两条路。报告里的数字容易被混记。建议把 `metric_delta` 的事件明确标为 `diagnostic_only`，并在 `EVENT_TYPES` 文档里写明“`delta_growth` 事件不代表生产运行结果”。成本小。

### C-3 两套泥沙范式的字段名相同而语义不同

- `metric_sediment.py` 冻结水力回放（`bounded-frozen-water-exner-v2`，强制 `publishable=False`）
- `metric_morphology_coupling.py` 交替耦合（`capacity_coefficient * q * dt * (v/v_ref)**2`）

两者都产出 `deposited_solid_m3 / reentrained_solid_m3 / unresolved_solid_m3`，但定义不同，跨报告比较会错。建议给每个 ledger 加 `ledger_semantics` 字段（如 `"exner_frozen_water_replay"` / `"capacity_settling_coupled"`），并让审计脚本拒绝跨语义直接比较。成本小。

---

## 3. 不建议现在做

- **放宽 `corridor_m`**：会把河道推到非谷底，与「原走廊」纪律冲突。
- **给端口加真回水/潮汐**：工程量大，且潮汐按用户要求需先讨论（`TODO.md:49`）。当前 `metric_lake_channel_coupling.py:3` 自述端口是 “reduced finite conductance weir, **not Saint-Venant backwater**”，措辞应在报告/前端统一改为“约化堰流端口”，禁止出现“回水”。成本小。
- **新增第四套洼地填充**：`docs/architecture/river-module-classification-20261009.md:32` 已禁止。
- **删版本族 v2..v10**：各有 test 消费者，是有意保留的证据链。

---

## 4. 建议执行顺序

1. **先做 A-P2**（装依赖 + 用 `results3.json` 建立可信的全绿/已知红基准）——否则后续任何改动都无法验收。
2. 再做 **A-P0**（三处自指规则 + 3 个测试 + 身份升 v7）——收益最大。
3. 同时做 **A-P1**（静默拒绝补账）与 **A-P3**（走廊拆三类）——都是小成本，且能把 P0 的效果说清楚。
4. **A-P4** 三项可穿插做。
5. **C-1/C-2/C-3** 文档性治理，与算法改动分开提交（`CONTRIBUTING.md:35`）。
