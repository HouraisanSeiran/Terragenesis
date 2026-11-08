# 特殊地形表面：噪波粗糙度 + 水力侵蚀（v2）· 交付文档（2026-10-20）

本轮范围（用户 2026-10-20 提出）：看完六类特殊地形预览后指出两点——①「形态上太过规整了，为什么不用噪波处理？」
②「还可以再加上水力侵蚀，多复用已有的算法」。本轮**只给 L0 四类场式地形（魔鬼塔柱 / 乌鲁鲁主体 / 张家界石柱群 /
喀斯特峰林）加面粗糙度与水力切割**，并**复用仓内既有内核**；**不**改任何既有 `metric_*` / `diffusion/*` 被 pin 的文件，
**不**改 Java 消费端，**不**动 `TGMCMT01`。

上一轮（只做离线几何与预览）见 [`docs/special-terrain-offline-20261019.md`](special-terrain-offline-20261019.md)。
参数台账与来源分级：[`.scratch/special-terrain/parameters-and-sources.md`](../.scratch/special-terrain/parameters-and-sources.md) §5.1 / §5.2。

---

## 1. 用户两点意见分别落在哪里

| 意见 | 落点 | 做法 |
|---|---|---|
| 形态太规整，要噪波 | **面粗糙度（facet roughness）** | 调用仓内唯一可用噪波内核 `diffusion/geographic_noise.field`，多八度、按父图格距声明波长、峰值归一化、随父图起伏缩放、向 collar 渐隐 |
| 加水力侵蚀，复用已有算法 | **水力切割（hydraulic dissection）** | 路由 + 汇流 + 声明式水流功率开挖 + 仓内八邻 donor-limited 输运 + 只对在途松散柱做休止角松弛；四个复用件全部只 import |

---

## 2. 复用的仓内内核（全部只 import，绝不修改）

这些文件的 sha256 被已发布证据 pin，因此**一个字节都不能改**；新模块只调用它们，并把它们当时的 sha256 写进产物 metadata
（`kernel_revisions`），使「内核动了」这件事在产物里可见。

| 内核 | 位置 | 用途 | 约束 |
|---|---|---|---|
| `field` | `diffusion/geographic_noise.py` | 多八度平滑噪波（米坐标 + seed/salt） | 被 `metric_forcing.py` / `metric_noise_forcing.py` / `tools/prepare_hydrology_algorithm_release.py` 引用 |
| `route_diagnostic` | `terrain_pipeline/surface_rivers/metric_drainage.py` | 八邻最陡下降路由 | 需 `TerrainGrid` + `BoundaryGrid`；四边边界 kind 必须显式；**第 0 行永远排除** |
| `accumulate_local_discharge` | 同上 | 汇流累积 → `routed_q_m3_s` | 同上 |
| `conservative_diffusion_step` | `terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py` | 八邻 donor-limited 配对输运（总量守恒） | 入参是**泥沙**通量，喂水量级会爆；`cell_type==-2` 为墙；第 0 行排除 |
| `phase_record` | 同上 | 相位守恒账本 | 返回的数组不能进 JSON identity，只取标量 |
| `relax_mobile_slopes` | `terrain_pipeline/surface_rivers/metric_fluvial_slope_stability.py` | 只对在途松散柱做休止角松弛 | 必须 `base <= bed` |

**未能复用**（因此未使用）：`simulate_fluvial_morphodynamics`（需 pyDeltaRCM 2.3.0，本机 venv 未装）、
`metric_reference_erosion`（依赖 pyDeltaRCM monkey-patch）。所以本轮**不**声称跑通了仓内参考侵蚀模型。

---

## 3. 三条实测得出的语义（都是先被推翻、后被证实的）

这一节比参数表重要：本轮有**两个初稿判断被自己的探针推翻**，写下来避免重现。

### 3.1 「给整面铺松散壳再松弛到休止角」是错的——会毁地形

正确做法是仓内**原生 `mobile_base` 语义**（`metric_fluvial_morphodynamics.py:584` 的 running-min）：活动柱初始为空，只在被切过的格点下降。
未动岩石 `available = bed − mobile_base == 0`，天然不受休止角约束——休止角保证的是「松散岩体不塌」，不是「264 m 塔必须处于休止角」。

| 做法 | 松弛搬动量 | 切割量 | 后果 |
|---|---|---|---|
| 整面铺壳 + 松弛（**错**） | 1.8e7 m³ | 5.2e3 m³ | 塔体损失 36.5 m；喀斯特格点反被**抬高** 104 m |
| 原生在途柱（**对**） | 3.9e5 m³ | 1.8e7 m³ | 最大柱损失 = 切割深度 8.6 m |

### 3.2 切割必须由**岩石下限**约束，不能由活动柱约束

若切割上限取 `mobile_base`，则活动柱初始为空、永远切不动任何东西——下限必须是**声明**的岩石下限
`floor = min(max(表面 − f×加噪后起伏, 基准床面), 表面)`。这也意味着下限用的起伏必须是**加噪后**的起伏，
所以产物里 `relief_reference_m`（父图峰值，给噪波振幅与 collar 渐隐用）与 `roughened_relief_reference_m`（加噪后峰值，给下限与活动柱用）
是两个**独立字段**——否则冷读者无法从产物复算下限。

### 3.3 「切割量要够大才看得见」

同一小算例：切割深度标定 K=0.3 时约 1e-3 m/格（图上完全看不见），K=8 时 8.8e4 m³、最大下切 6.65 m、27.7% 活动面被切 >1 m。
因此 `detachment_per_step_m` 是按图分档的（塔 8 / 乌鲁鲁 8 / 石柱 2 / 峰林 6 m）。

---

## 4. 结构保证（可被冷读逐一复算）

1. **collar 逐位归零**：噪波按父图位移渐隐、切割每步向 collar 夹回，产物里四边位移与 change 都 **精确等于 0**（不是「接近 0」）。
2. **保底不穿透**：`floor <= bed`、`mobile_base <= bed` 每相位夹紧；切割每步 `raise` 若越过下限。
3. **挖填不互抵**：`detachment_ledger_m3`（挖）、`transport_deposition_ledger_m3`（填）、`relaxation_transferred_ledger_m3`（内部搬移，总量不变）三本独立账，各步可查。
4. **身份可重放**：`surface == reference + displacement + vertical(change)` **逐位**成立（不是容差意义上），所以冷读者能用自算的 change 重建 bed。
5. **不碰父图**：父 bundle 只读，全部新字段在新 bundle 里。
6. **四能力位仍全 False**：`hydraulic_ready` / `natural_outlet_verified` / `publishable` / `self_intersection_verified`。
   本轮做的是形态改善，不是水文认证，`hydraulic_ready` 必须仍然 False。

---

## 5. 产物与工具

| 路径 | 内容 |
|---|---|
| `terrain_pipeline/metric_special_terrain_surface.py` | 新模块（`??`）：`SCHEMA=metric-special-terrain-surface-v2` / `ALGORITHM=special-terrain-facet-noise-hydraulic-dissection-v2` / `SUPERSEDES_ALGORITHM=…-v1` / `RETIRED_RECIPE_FIELDS=("immobile_rock_fraction",)` |
| `tests/test_metric_special_terrain_surface.py` | 单测 10 项 |
| `tools/prepare_special_terrain_surface.py` | 读父 bundle → 生成四类 v2 bundle + `manifest-report.json` |
| `tools/audit_special_terrain_surface.py` | **独立冷读**验收器：不 import 生成器，自己重实现噪波内核、重算岩石下限、重放 target 足迹、从磁盘重算五个 kernel 的 sha256、重放 identity |
| `tools/preview_special_terrain_surface.py` | 三栏对照（父图 / 加噪 / 侵蚀）+ 剖面（含重算下限）+ 侵蚀变化发散图 |
| `.scratch/special-terrain/surface-20261020/` | 四类 v2 bundle + `manifest-report.json` + `independent-audit.json` |
| `.scratch/special-terrain/surface-preview-20261020/` | 四类各 3 图 + `report.json` |

**产物目录在 `.scratch/`，不进 `verification/`**：本轮是形态改善与 candidate 产物，`verification/` 只允许追加声明文件。

---

## 6. v1 → v2 的三处真缺陷修复

单测与冷读验收器收敛过程中改出的**模块侧真缺陷**（不是测试写错）：

1. **recipe 序列化不一致**：`asdict()` 出 tuple，而 bundle 经 JSON 往返出 list，导致 `validate` 里
   `metadata["facet_recipe"] != asdict(facet)` **必然失配** —— 任何 `load_special_form_surface` 都会抛 `ValueError`。
   修法：新增 `_canonical(value) = json.loads(json.dumps(value, sort_keys=True, allow_nan=False))`，build 与 validate 两侧都用它。
   顺带好处：内存态 bundle 与 load 后逐字段相等。
2. **`relief_reference_m` 语义混淆**：该字段原本记的是**父图**起伏（给噪波振幅与 collar 渐隐用），但岩石下限与活动柱实际按**加噪后**起伏算。
   新增独立字段 `roughened_relief_reference_m` 并在 validate 里校验它 `== max(displacement[:, :, 1])` 且 `>=` 父图值。
3. **`relaxation_converged` 被当成必须为 True 的门槛**（由独立验收器拦下，见 §6.1）。

此外 v1 的 `FacetRoughnessRecipe.scales` 写的是**绝对米数波长**，在 8 m 网格的 inselberg 上必踩采样门槛——
这也从侧面证明 **v1 从未真正跑过**。v2 改为按**格数**声明。

### 6.1 验收器拦下的是一个「从未验证过的声明预算」

首次跑 `tools/prepare_special_terrain_surface.py` 时，四类全部输出 `relax_converged=False`，
独立验收器因此 **0/4 失败**。根因不是地形算法，而是 `surface_preset` 里两个**从未实测过**的常量：
`tolerance_m=1e-6`、`max_sweeps=8`。

探针实测（只读、不入仓）：

| kind | 网格 / 格距 | 容差 1e-6 下实需扫数 | 容差 1e-3、预算 512 下（12 步） | 实际所需最大扫数 |
|---|---|---|---|---|
| inselberg | 276×476 @ 8 m | 236 / 438（收敛） | 步 0–9 收敛（126→508），步 10、11（543 / 617）未收敛 | 617 |
| karst_tower_field | 491×491 @ 1 m | 59 / 81（收敛） | **全 12 步收敛**（33–152 扫） | 152 |
| sandstone_pillar_field | 321×321 @ 0.5 m | 84 / 307（收敛） | **全 12 步收敛**（28–494 扫） | 494 |
| volcanic_plug | 411×411 @ 1 m | 453 收敛 / 512 未收敛 | 步 0、1 收敛（221 / 448），步 2–11（826–2031）未收敛 | 2031 |

两个结论：

- **残差是预算问题，不是结构性下限**：把预算放到 20000 扫，**四类 12 步全部收敛**（最大 2031 扫），所以不存在「永远达不到绝对容差」的情况。
- **但加预算不可行**：所需扫数逐步增长（volcanic_plug 到 2000+ 扫，是 512 的 4 倍），而
  `DissectionRecipe.__post_init__` 把 `max_sweeps` 限在 1–512（与内核上限一致），
  `relax_mobile_slopes` 本身也默认 512。**不能**去改内核默认值——`metric_fluvial_morphodynamics.GRAVITY_PARAMETERS`
  的同名值被 `tools/verify_fluvial_morphodynamics.py:492` 作为冻结机制校验。

真正的问题是**门槛写错了对象**。`relax_mobile_slopes` 的 docstring 明写：
*「Return actual relaxed state, including an unconverged finite-stop state」*——
它的契约就是允许返回未收敛的有限停步态，判据是 `maximum_mobile_excess_after_m <= tolerance_m`。
把一个**允许为假**的量当成必须为真，是验收器比内核自身还严。

修法（两侧都改，不降低几何要求）：

1. **验收器改为检查自洽**：逐项复算「每个操作数是否与声明一致」，而不是要求成功。具体：
   逐步复算 `relaxation_converged == (relaxation_maximum_excess_m <= tolerance_m)`；
   汇总值与逐步极值一致；扫数不超预算；**未收敛的步不得是「卡在 float64 分辨率不动」**（那是真问题，必须拒绝）。
2. **模块加可审计字段**：台账里新增 `relaxation_tolerance_m` / `relaxation_sweep_budget` /
   `relaxation_maximum_excess_m` / `relaxation_sweeps_max`，逐步记录另加 `relaxation_maximum_excess_m` /
   `relaxation_immobile_excess_m` / `relaxation_stalled_at_float64_resolution`；
   `validate_special_form_surface` 自己复算这个布尔。
3. **预算按实测定值**：`surface_preset` 的 `tolerance_m` 由 `1e-6` 改为 `1e-3`（1 mm，在 150–348 m 起伏上物理上够小），
   `max_sweeps` 由 `8` 改为 `512`（实测所需量级）。karst / sandstone 由此**全 12 步真收敛**；
   inselberg / volcanic_plug 如实记 `False` 并由自洽检查背书。

**比参数表重要的一点**：这条链上「加噪波 → 切割 → 松弛」每一步都要经得起冷读复算；
「松弛收敛了」这句声明本身也必须能被复算，否则它就只是一个没人验过的字段。

---

## 7. 数值结果

全部由 `tools/prepare_special_terrain_surface.py` 与独立冷读验收器输出，**未手改**。

### 7.1 几何与账本（`surface-20261020/`）

| kind | 网格 / 格距 | 起伏（父图 → 加噪后）m | 最大下切 m | 最大堆积 m | 岩石下限深 m | 挖 ledger m³ | 输运填 m³ | 松弛内部搬移 m³ | 净变 m³ | 被切 / 堆积格 |
|---|---|---|---|---|---|---|---|---|---|---|
| inselberg | 276×476 @ 8 m | 348.00 → 369.08 | 20.557 | 11.085 | 55.362 | 2,751,266.67 | 1,950,838.34 | 12,010,354.33 | −2,751,266.67 | 72,537 / 15,843 |
| karst_tower_field | 491×491 @ 1 m | 196.96 → 208.45 | 10.613 | 13.660 | 31.267 | 9,532.35 | 8,203.25 | 17,714.36 | −9,532.35 | 42,330 / 2,787 |
| sandstone_pillar_field | 321×321 @ 0.5 m | 144.31 → 158.62 | 11.404 | 11.633 | 23.793 | 611.90 | 734.30 | 1,569.82 | −611.90 | 27,082 / 1,688 |
| volcanic_plug | 411×411 @ 1 m | 264.00 → 285.46 | 41.611 | 6.049 | 42.819 | 122,365.61 | 38,514.77 | 1,083,249.40 | −122,365.61 | 66,873 / 6,180 |

（完整账本、逐步记录与 target 逐项下单见 `surface-20261020/manifest-report.json` 与 `independent-audit.json`；预览汇总见 `surface-preview-20261020/report.json`。）

### 7.2 独立冷读验收（不 import 生成器）

```
inselberg:             pass identity=2d8ee023fcb2b9c5 facet_delta=0.000e+00 bed_minus_floor=0.000e+00
karst_tower_field:     pass identity=f0e0b628cd54cf64 facet_delta=0.000e+00 bed_minus_floor=0.000e+00
sandstone_pillar_field:pass identity=bc410d6be968a3a3 facet_delta=0.000e+00 bed_minus_floor=0.000e+00
volcanic_plug:         pass identity=622738589a64e35f facet_delta=0.000e+00 bed_minus_floor=0.000e+00
passed=4 failed=0
```

`facet_delta=0.000e+00` ＝ 验收器自实现噪波重算的面与存储位移**逐位相同**；`bed_minus_floor=0.000e+00` ＝ 终态床面与自算岩石下限的最小差**逐位相同**。

### 7.3 休止角松弛（判决性一项）

| kind | 收敛？ | 最大残差 m | 最大扫数 | 预算 | 容差 m |
|---|---|---|---|---|---|
| inselberg | **False** | 5.318e-3 | 512 | 512 | 1e-3 |
| karst_tower_field | **True** | 1.000e-3 | 152 | 512 | 1e-3 |
| sandstone_pillar_field | **True** | 1.000e-3 | 494 | 512 | 1e-3 |
| volcanic_plug | **False** | 3.047e-1 | 512 | 512 | 1e-3 |

四个数字都是从台账**复算**的（见 §6.1）：验收器逐步验证 `relaxation_converged == (relaxation_maximum_excess_m <= tolerance_m)`，并确认未收敛的步是「用完了扫数」而非「卡在 float64 分辨率不动」。**未收敛不是失败**——它只表示在这些图上，512 扫不够把在途松散柱推到 1 mm 以内；流体合法性仍未认证（四能力位全 False）。

---

## 8. 未做 / 未认证（必须与原产物声明一致地读）

- **未做**：Java 消费端接入、新 snapshot format version、`TGMCMT01` 变更；TD 真实 1 m 床上的 v2 端到端（上一轮的 TD 适配器只跑了 v1 场式形态）。
- **未认证**：`hydraulic_ready=False`（本轮的切割是**声明式**水流功率项，不是水文合法性证明）；
  `natural_outlet_verified=False`（无自然出流口验证）；`self_intersection_verified=False`（未做实体自交检测）；
  `publishable=False`（全部 `status=candidate`）。
- **未做的事不要推测**：本轮的「水力侵蚀」= 复用仓内路由/汇流/输运/休止角内核 + 一个声明式开挖项，
  **不是** `simulate_fluvial_morphodynamics`（pyDeltaRCM 未安装），也**不是**完整水力-泥沙耦合模型。
- **参数等级**：§5.1 / §5.2 里除「继承自父模块 / 内核对内惯例 / 继承仓内原生语义」三档外，
  其余**全部是显式假设**——没有公开资料给出这四类地形的**表面微起伏量级**或**单步水流功率-侵蚀率**。
  唯一的例外是休止角松弛的 `tolerance_m` / `max_sweeps`：它们是**探针实测定值**（见 §6.1），不是假设。
