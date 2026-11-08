# 特殊地形离线几何与预览 · 交付文档（2026-10-19）

本轮范围（用户 2026-10-19 16:05 拍板）：**只做离线几何 + 预览（Python 侧）**；允许局部体积表示（优先扩展现有
`hybrid_cave_geometry` 骨架）；新形态沿用 canyon 先例（新增版本化配方 + 独立预设，不动任何已有配方与世界）。
本轮**不**改 Java 消费端、**不**起新 snapshot format version、**不**动 `TGMCMT01`。

前置盘点：`docs/special-terrain-recon-20261019.md`（285 行，四份只读盘点合成）。
规格与任务：`.scratch/special-terrain/{spec.md,issues/01..11-*.md}`。
参数台账：`.scratch/special-terrain/parameters-and-sources.md`。

---

## 1. 交付清单（全部本轮新建，逐条可解释）

### 1.1 源码（`git status` 中均为 `??` 未跟踪；不修改任何既有 `metric_*` / `hybrid_*` 跟踪文件的语义）

| 文件 | 行数/字节 | 身份常量 |
|---|---|---|
| `terrain_pipeline/metric_special_terrain_forms.py` | 22 828 B | `SCHEMA=metric-special-terrain-v1` / `ALGORITHM=special-terrain-field-forms-v1` |
| `terrain_pipeline/td_special_terrain_adapter.py` | 17 803 B | `td-special-terrain-chart-v1` / `td-fine-bed-special-terrain-adapter-v1` |
| `terrain_pipeline/special_terrain_l1_sinkhole.py` | 586 行 | `td-special-terrain-l1-sinkhole-v1` / `sampled-rock-sinkhole-shaft-subsurface-river-skylight-v1` |
| `terrain_pipeline/special_terrain_l1_cave_bridge.py` | 33 819 B | `td-special-terrain-l1-cave-bridge-v1` / `sampled-rock-cave-tunnel-skylights-natural-bridge-v1` |
| `terrain_pipeline/special_terrain_l1_rock_eggs.py` | 503 行 | `td-special-terrain-l1-rock-eggs-v1` / `stacked-disconnected-rock-egg-bodies-with-genuine-voids-v1` |
| `terrain_pipeline/special_terrain_l1_uluru_flare.py` | 25 031 B | `td-special-terrain-l1-uluru-flare-v1` / `inselberg-with-flared-overhanging-base-v1` |

配套工具（`tools/`，均为 `??`）：`audit_special_terrain_forms.py`（L0 独立冷读校验器）、`prepare_special_terrain_forms.py`、
`preview_special_terrain_forms.py`、`preview_td_special_terrain.py`。

测试（`tests/`，均为 `??`）：`test_metric_special_terrain_forms.py`、`test_td_special_terrain_adapter.py`、
`test_special_terrain_l1_{sinkhole,cave_bridge,rock_eggs,uluru_flare}.py`。

`docs/special-terrain-recon-20261019.md` 为本轮盘点文档（`??`）。

### 1.2 产物（全部在 `.scratch/`，不进 `verification/`）

| 目录 | 内容 |
|---|---|
| `.scratch/special-terrain/bundles-20261019/` | L0 四类 bundle（`inselberg.npz` 等）+ `manifest-report.json` + `independent-audit.json` |
| `.scratch/special-terrain/preview-20261019/` | L0 四类各 3 图 + `six-category-contact-sheet.png` + `report.json`（含 `l1_placeholders`） |
| `.scratch/special-terrain/td-adapter-20261019/` | 真实 TD 1 m 床窗口上两例端到端（`volcanic_plug` / `karst_tower_field`）+ 各自 bundle 与 3 图 + `report.json` |
| `.scratch/special-terrain/l1-preview-20261019/{sinkhole,cave-bridge,rock-eggs,uluru-flare}/` | 每项 `report.json` + 3 PNG |

### 1.3 L0 四类实测尺度（`manifest-report.json`）

| kind | 格距 | 最大起伏 | 目标数 | identity_sha256（前 12） |
|---|---|---|---|---|
| `volcanic_plug`（魔鬼塔） | 1.0 m | 264.0 m | 1 | `e7872b3e2cd8` |
| `inselberg`（乌鲁鲁主体） | 8.0 m | 348.0 m | 1 | `c116d6a40fe4` |
| `sandstone_pillar_field`（张家界石柱群） | 0.5 m | 144.312421 m | 多 | `18fdd59cdb68` |
| `karst_tower_field`（喀斯特峰林） | 1.0 m | 196.963657 m | 多 | `2f4154a8f750` |

四类 `independent-audit.json`：`passed=4 failed=0`，各项 `max_replay_difference_m=0.0`、
`perimeter_zero` 四边全 true、`displacement_vertical_only=true`、`snap 0 m`、四状态位全 false。

### 1.4 L1 四项实测体积账（`report.json` 的 `solids`，均为 Mesh64 实测量）

| 形态 | solids 与体积 m³ | witnesses | report identity（前 12） |
|---|---|---|---|
| 天坑竖井+暗河+天窗 | `rock_before` 576000.0；5 cutter；`cutter_union` 37291.721260；`removed` 33759.838585；`rock_after` 542240.161416 | 31（全 true） | `0c1248f486c1` |
| 溶洞—天窗—天生桥 | `rock_before` 432000.0；4 cutter；`cutter_union` 13051.417619；`removed` 13051.417619；`rock_after` 418948.582381 | 15（全 true） | `70ce3a82d209` |
| 岩石蛋堆 | 8 蛋（20.374…111.965）；`rock_after` 386.088067 | 5（全 true） | `977f55a27dac` |
| Uluru flared slope | `flared_skirt` 626356.187368；`inselberg_body` 18930098.928350；并集 `uluru_flare` 19450711.378603（1 连通分量） | 6（全 true） | `c21d0edf2b5a` |

---

## 2. 参数来源分级与显式假设（三级台账纪律）

台账 `parameters-and-sources.md` 的三级：**已核实** / **二手** / **未取得 → 显式假设**。
逐形态来源回指落在 `metric_special_terrain_forms.PARAMETER_SOURCES` 与各 L1 模块的 `EXPLICIT_ASSUMPTIONS`。

### 2.1 已核实（可直接作生成器约束带）
- 魔鬼塔高 264 m + 岩性 phonolite porphyry（NPS）。
- 张家界 3000+ 柱、景区 369 km²（遗产地）。
- **魔鬼岩石蛋单体高至 6 m**（北领地官方旅游页）——L1 石蛋堆据此把半径上界钉在 3.0 m。

### 2.2 二手（可作默认值，须标二手）
- 小寨天坑口径 626 m / 垂深 666.2 m / 坑底直径 522 m / 容积约 1.19 亿 m³（多源一致，另有 622 m 版）。
- 乌鲁鲁：**348 m 与 335 m 两版冲突未解**（`uluru-flare` report 的 `height_conflict` 段写明 `resolution:"unresolved"`、`published_m:[348,335]`，选了公园管理方数字）。
- 乌鲁鲁长 3.6 km、周长 9.0…9.4 km → 半宽 ~1.0 km。
- Kata Tjuta 36 个圆顶岩体、最高相对平原约 546 m。

### 2.3 未取得（生成器一律走「显式假设」，机器可读、逐项带理由）
册列硬缺口：柱径/节理间距/层厚、峰林基座直径/峰间距/壁坡度、张家界单柱底径/柱间距、
乌鲁鲁 335/348 冲突与 flared slope 外扩幅度、石蛋直径/堆叠/群密度。

| 形态 | `explicit_assumptions` 条数 | 例（全部 `grade:"assumed"`，无一条当实测） |
|---|---|---|
| 天坑 | 26 | 斗壁坡度、阶地宽度粒度、暗河管径与顶穿位置 |
| 溶洞—天窗—天生桥 | 15 | 隧道直径/埋深、天窗半径、桥宽 |
| 岩石蛋堆 | 9 | 单体半径分布、堆叠数、群间距、悬空净空、外扩幅度 |
| Uluru flared slope | 5 | `total_height_m=348`、`overhang_amplitude_m=38`、`skirt_height_m=12`、两个坡度角 |
| L0 四类 | 逐参数 | 见 `metric_special_terrain_forms.PARAMETER_SOURCES` |

所有 L1 模块的 `synthetic_base = {"kind":"synthetic_analytic", "note":"not TD native terrain, not surveyed"}`，
且 `not_claimed` 明列 `real_devils_marbles_reproduction` / `self_intersection_verified` 等——**没有任何一项可引用为机构值或实测**。

---

## 3. 身份常量与状态位

- **新形态一律新 `SCHEMA`/`ALGORITHM`**（见 §1.1 表），沿用 canyon 先例的版本化配方 + 独立预设。
- **既有 `metric_*` 身份常量零改动**：本轮唯一触及的既有文件是 `terrain_pipeline/metric_vdm_forms.py`，只做 P1 护栏
  （`_shape` 的 `else` → 显式 `elif form.kind == "massive_overhang":` + 末尾 `raise ValueError`），逐字节等价、
  `identity_sha256 = identity(arrays, metadata)` 不含源码文本 → 既有产物身份不变。`git diff` 可见仅此一处 hunk。
- **冻结基线未变**：`hybrid_cave_geometry.py` = `DD839163651239BA358B74B79E41ACF6831487A6638E980483F9825243311B55`；
  `hybrid_rock_boolean.py` = `6A472225ADB2ABD114527B4431739F058665D37E6B3A55C594659F40EB87B7E0`。
- **状态位**：所有 L0/L1 产物 `status="candidate"`；能力位
  （`independent_audit_passed` / `hydraulic_ready` / `natural_outlet_certified` / `full_network_verified` /
  `self_intersection_verified` / `publishable`；L0 为四位的 `hydraulic_ready/natural_outlet_verified/publishable/self_intersection_verified`）
  **全部显式 False**，`report.json` 与内联 boolean 记录两处一致。

---

## 4. 独立冷读审计与验收（本轮实测）

### 4.1 L1 四项（P5.6，主代理侧，不复用任何生成器）
- `temp://scratch/audit_l1_all_cold_v2.py`：只读磁盘 `report.json`、用 `Manifold.Mesh64(float64, uint64)` 重建，
  复算 **29 条 record 的 `identity_sha256` 与体积门**、**全部 Mesh64_boolean 见证**（union / subtract，sub 用
  `rock ∧ cutter_union` 量真被挖掉的料）、**54 条探针**（绕数 + 射线，含嵌套复合见证）→ **全部通过**，
  顶层 identity 全 OK。
- `temp://scratch/check_l1_figures_v2.py`：figures sha256（两种 path 约定都能解析）、紧凑无换行、无 NaN/Infinity、
  假设全 `grade=assumed` 带 reason、顶层契约键齐备 → PASSED。
- 测试：`tests.test_special_terrain_l1_{sinkhole,cave_bridge,rock_eggs,uluru_flare}` 合计 **54 用例 OK**。
- 关键见证（实测数字）：
  - 天坑：同轴射线挖前 1 击 / 挖后 0 击；坑底首个命中 y=−36.0（= 声明河床）；collar 内 5 样本 0 击、collar 外 14 样本各 1 击且首击 y=0。
  - 桥：水平射线恰好 4 击（x=−29,−21,+21,+29），两井之间 42 m 与井到边墙 31 m 全实心；顶面全扫每 1 m 井内 0 击 / 井外恒 1 击。
  - 石蛋：分离对并集 = 各部分之和（rel 2.0e-15）；堆叠对并集 206.072930 < 213.103022；悬空中点绕数 2.209e-17、探针重叠恰 0.0、外部射线 0 击；净空 0.540251 > 解析间隙 0.539824。
  - Uluru：悬挑点绕数 1.48e-16（外）、探针交集 0.0；竖直射线 1 击于 y=10 塔底；并集 1 连通分量。

### 4.2 L0 四类（P3/P4）
- `tools/audit_special_terrain_forms.py` 独立冷读：4/4 pass、`max_replay_difference_m=0.0`、perimeter 四边 0。
- 真实 TD 1 m 床端到端两例：`td-adapter-20261019/report.json` 记录 `lattice_vs_canonical_floor_difference_m=6.8e-13`、
  `chart_floor` 与 canonical 差 ≤1.46e-6 m 容差、`artificial_cut_maximum_m=0.0`、`protected_cells_chart=0`、
  四状态位 false，且带完整 `identity_chain`（fine_bed → chart source → chart protection → source hierarchy）。
- 测试：`test_metric_special_terrain_forms` + `test_td_special_terrain_adapter` + `test_metric_vdm_forms` 合计 **32 用例 OK**。

### 4.3 契约不一致（如实记录，未强行统一；不构成错误）
1. `figures[].path`：`rock-eggs`/`sinkhole` 存**纯文件名**，`cave-bridge`/`uluru-flare` 存**含目录的仓库相对路径**；
   两种都指向同一磁盘文件、sha256 均已核对一致。
2. `local_origin_xyz_m`：`cave-bridge` 缺该键（另有 `world_frame` 声明「零局部原点」）；`rock-eggs` `[0,0,0]`；
   `sinkhole` `[1200,480,-2500]`；`uluru-flare` `[120,40,-75]`。
3. 顶层键各有额外项（`world_frame` / `height_conflict` / `derived` / `source_grade` / `cold_read_contract` / `hydraulic_status` 等）。
4. L1 报告的 `identity_sha256` 由各模块在**构建时**自产（`figures:[]` 时 seal，figures 未参与身份），因此与 egg-pile 早前信件头部单独列出的值不同——不矛盾。

---

## 5. 未认证项（本轮明确不做，不得声称）

1. **Java 侧 9 步接入**未做：`SurfaceModifier` → 配方 → `TerrainModeRegistry` 三处 → 客户端枚举 → 独立 preset json →
   语言键 → 验证工具。米制路径当前无体积场/无洞穴/无材料/无水/无气候。
2. **`TGMCMT01` 新 format version** 未起：v1 载荷逐字节锁定，本轮一律走独立预设。
3. **天坑水文合法性**未解决：工程纪律是「不填洼、显式出口才合法」。L1 的
   `prerequisites_before_hydraulic_or_consumer_use` 明列三项前置——① 埋藏/闭端河段显式终点声明；
   ② 竖井/空腔体积的 lake-domain 记录；③ 闭端河段内流耗损契约（`metric_natural_lakes.py:225-237` 的 `closed` 通量恒 0 缺口）。
   本轮水文代码**一行未动**。
4. **自交与认证**：`self_intersection_verified` 等位保持 False；L1 的 30 m 主网格无法解析件级尺度的问题只由 P4 薄适配部分缓解。
5. 形态参数多数无来源（§2.3），因此只可用于离线几何/预览演示，**不是**真实地貌还原。

---

## 6. 后续阶段（登记，本轮不实施）

1. Java 9 步接入（照 0.8.0 canyon 范本，均不需要动 `TGMCMT01`）。
2. `TGMCMT01` 新 format version（体积通道 / 材料 / 水 / 气候）。
3. 天坑与消费端接入前的三项水文前置（§5.3）。
4. L1 真实 TD 基床落地（本轮 L1 均为 `synthetic_analytic` 解析块，未接真实床）。
5. 岩性—地层真空白、风化—侵蚀—输沙闭环、米制气候补纬度（见 `docs/expansion-assessment-20261019.md`）。

---

## 7. `git status` 逐条解释

- 本轮新增（`??`）：§1.1 的 6 个 `terrain_pipeline/*.py`、4 个 `tools/*.py`、6 个 `tests/*.py`、
  `docs/special-terrain-recon-20261019.md`、本文件、`.scratch/special-terrain/**`（规格/台账/bundle/预览/报告）。
- 本轮修改（`M`）：仅 `terrain_pipeline/metric_vdm_forms.py`（P1 护栏，§3）；`TODO.md` 追加本轮登记（§见 TODO 顶部）。
- 其余数百个 `M`/`??` 条目为本任务开始前既有的工作区状态（三角洲、A-P0 等），**非本轮改动**。
- `verification/` 本轮**零新增**（纪律：只放声明，不放扫描/临时产物）。
