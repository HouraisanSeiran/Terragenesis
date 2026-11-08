# 石柱群：从二维高度场改为真三维程序化生成 + VDM 柱壁雕刻

Status: candidate（原型 → **已落仓** → **已接进 `web-preview`**）
日期：2026-10-20
上游：`docs/special-terrain-surface-20261020.md`（现高度场路线）、`.scratch/special-terrain/parameters-and-sources.md`（参数台账）
本文件**不改动任何已有身份的字节**：`metric-special-terrain-v1` / `metric-special-terrain-surface-v2` 的模块与证书一字未动。落仓版**新增**了一份针对 `sandstone_pillar_field` 旧几何值的 `SUPERSEDES` 作废声明（§8）——声明只出现在新模块自己的报告里，**不写 `verification/`**。

---

## 0. 来龙去脉

用户先问「石柱群底座应该是圆的吗」，再给出方向性指令：

> 石柱是需要程序化生成的，不应该是基于二维灰度图的，应该做成 3D 形式，用 vdm 在柱壁上雕刻

前半句是对现状的准确诊断。现在石柱群走**高度场**：`metric_special_terrain_forms.py` 给出一个位移场，`metric_special_terrain_surface.py` 把它抬升成规则网格（`surface_xyz_m`）。

高度场每个 (row, col) 只有**唯一一个 z**。后果是双重的：

1. **截面只可能是等高线**。现在代码里 `rx == rz`，每个 bump 就是一个圆盘——这正是用户看到的「圆形底座」。要改成多边形，高度场的等高线也不会是直边多边形，而是椭圆的变体。
2. **竖直柱壁、顶上外凸的铁帽、凹进去的壁龛，高度场根本表达不了**。壁只能靠位移快速变化来「隐喻」，而真壁是多值面。

所以不是「优化参数」的事，是**几何表示换人**。

---

## 1. 来龙去脉：资料说明（两条线）

### 1.1 地貌事实线（张家界石英砂岩峰林）

可用的硬事实（来源已逐项标等级，详见台账 §1/§2）：

| 事实 | 等级 |
|---|---|
| 岩性：中上泥盆统（云台观组 + 黄家墩组）**石英砂岩**，厚 >500 m，产状近水平，**非碳酸盐岩溶** | 已核实 |
| 机制：燕山运动形成**多组垂直节理**，流水沿节理强烈下切；重力崩塌 + 风化 | 已核实 |
| **垂直节理是必要条件**（地貌学上直接归因于节理控制） | 已核实 |
| 群体规模：3000+ 座石柱，景区 369 km² | 已核实 |
| 演化四阶段：平台/方山 → 峰墙 → 峰丛/峰林 → 残林 | 已核实 |
| 单体：高几十米至 400 m，超 200 m 的千余座 | 二手 |
| 顶部约 30 m 厚**铁质石英砂岩铁帽** | 二手 |
| 形态描述（二手、来自百科引景区解说）：金鞭岩「**四棱分明**，棱面布满节理横纹」；御笔峰「**方正如削**…**上细下粗**」；总体「**棱角平直**」「顶平壁陡」 | 二手 |

**“棱角平直的柱状形态 + 节理控制截面”是二手材料里反复出现的官方描述**，也是多边形棱柱而非圆盘的直接依据。

### 1.2 几何参照（不是张家界的实测，只是此类几何的既有先例）

- NPS《Columnar Jointing》标了魔鬼塔柱体**边数 3–7**（已核实，但那是响岩斑岩的柱状节理，**不是张家界**）。它说明「节理控制的岩石柱截面是多边形」这个**几何事实**成立；证明不了张家界的具体边数，本实现**没有**把 3–7 当约束。
- 仓内已有设计提案 `research/岩壁Voronoi与贴壁流水设计.md`（2026-09-27，未接入）：直接提出「Voronoi 岩块 / 节理 / 耐蚀度」与「把岩壁当斜面求解」，并给出沿面内法线的退缩式 `D_new = D_old − dt·E·n`。
- 仓内 `research/VDM岩壁形态资料-20261003.md` 提供与柱壁对应的 VDM 形态语汇：`layered_ledge` / `stepped_wall`（硬岩棚）、`fluted_wall`（沿裂隙的纵向浅槽）。

> **未取得（仍是缺口）**：张家界**单柱底径 / 柱间距 / 垂直节理间距 / 高宽比分布**（台账 §3 硬缺口四项）。本次全部走**显式假设**。

---

## 2. 真三维表示：用仓内已有的闭合实体通路

**不新内核**。复用 `terrain_pipeline/hybrid_rock_boolean.py` + `hybrid_cave_geometry.py`（已被四个 L1 形态在用：天坑、溶洞-天生桥、岩石蛋、Uluru）：

| 仓内 API | 用途 |
|---|---|
| `polygon_prism_record(polygon_xz, bottom_y, top_y, origin, role)` | 任意简单多边形拉伸的**闭合竖直棱柱** |
| `combine(records, ...)` → `batch_boolean(OpType.Add)` | 并集，带分量普查 + 材料账本 |
| `save_manifold(solid, origin, role)` | 实体 → 三角网（走 pinned MESH64，保存体积由构造即等于实测量） |
| `mesh_record` 的反向二用流形门 | 水密性判定 |

**待验证的假设**：现有测试里的 `self_intersection_verified` 在仓内**一律硬写 False**，水密门不能代替自交检查。本原型没有做自交专项检查——只是保证了**每个水平截面都是简单多边形**（必要不充分）。

---

## 3. 多边形截面从哪来：节理网络 = 抖动栅格 Voronoi

1. 抖动栅格布种子（`PITCH_M=30`，一个方向拉伸 `STRIKE_STRETCH=1.6` 做出主导节理走向）；
2. Voronoi 胞 → 每个胞是一个**不规则凸多边形**；
3. 每胞**内缩** `0.5 × JOINT_GAP_M=3 m`（mitre）→ 产出真节理缝，柱与柱分开站；
4. 沿弧长重采样到 `1.5 m`，再做 **4 遍循环滑动平均**。

**第 4 步不是装饰，是前提**：mitre 角的**局部曲率半径几乎为零**，而雕刻就是向内偏移。偏移超过那个半径，截面就从里面穿过去了。实测：不平滑时 **15/16** 柱在离底 4–16 m 处就折；平滑后 **无**。同理，环顶点间距 ~12 m 而凹槽波长 11 m 会**混叠**，所以重采样到 1.5 m（呼应仓内 `SAMPLES_PER_FEATURE = 4`）。

---

## 4. VDM 在竖直柱壁上刻什么、怎么刻

每个柱的截面顶点，沿各自的**外法线**做横向位移。四项，全部用仓内已有词汇：

| 项 | 地质对应 | 实现 |
|---|---|---|
| `taper` | **上细下粗** | **绕自身质心的精确相似收缩** `1 − 0.10·(y/h)`；施加于位移**之前** |
| `striation`（两级） | **节理横纹**（金鞭岩「棱面布满节理横纹」） | 沿高度 `y` 两级正弦，幅 0.55/0.22 m，波长 24/14 m |
| `flute`（两级） | 纵向凹槽（`fluted_wall`） | 沿周长 `s` 两级正弦，幅 0.55/0.22 m，间距 16/7 m |
| `cap` | **铁帽**（顶部 ~30 m 铁质石英砂岩） | 顶部 30 m 内向外凸 1.1 m |

位移幅值限幅 `±2.0 m`。高度细分 `SUBSTEPS_M=3 m`，最细波长 `≥ 4 × 3 = 12 m`（`STRIATION_L_M` 最小 14 m）。

### 4.1 三个真实的踩坑（都是先出结论、被实验推翻）

这三条是本次最贵的代价，**改版时不要重犯**：

1. **taper 一开始用「到世界原点的距离」当径向** `-f·t·‖ring‖`。它沿周长任意变化、还随柱子在场地里的位置变，把壁面**整段拉折**。改为**绕质心的相似收缩**——正相似变换把简单多边形映成简单多边形，**可证不折**。效果：满深度柱 **8/16 → 14/16**。
2. **报 `no consistent winding found` 的其实是容差，不是绕向**。手搓 double 精度的体积与 MESH64 实测差 ~1.7e-6 相对量（MESH64 把近重合顶点重新焊接），而 `_volume_gate` 的 1e-9 是给 `to_mesh64()` 往返过的记录用的。修：干脆用 `save_manifold` 导出。
3. **`signed_volume` 为负不代表门会报错**。墙三角化按 CCW 环走 → 法线朝内，MESH64 的 `volume()` 是**带符号的**，`volume() > 0` 把合法盖组合漏掉了。修：盖的 4 种翻转**各配一次全局反转**，取 `status==NoError and volume()>0`。

---

## 5. 实测（candidate）

**落仓产物**在 `.scratch/special-terrain/l1-preview-20261020/pillars3d/`（`report.json` + `carved.npz` + `plain.npz` + 三张 PNG），由落仓模块自己的 CLI 生成：

```
.\runtime\venv\Scripts\python.exe -m terrain_pipeline.special_terrain_pillars3d
```

| 文件 | sha256 |
|---|---|
| `report.json`（8 432 751 B） | `e00b359f0490f20fcad7321bd59599e51e0ed2d2d186bb5bc4cbac4f08582269` |
| `carved.npz` | `2efaa0004d86b16b68e5bbf9e79a2fd341b2f400a9e3891b52f512c01fa8d2b0` |
| `plain.npz` | `51f2737b37d2e06f243975255a1ca33c8fe96583d29ff360b392474a085f5dd9` |

报告 `identity_sha256 = a44932dd5ba1fe83e66d352f84615632c14b74ae0352e7e30bd923cc6e365477`。

**归档原型**（只读留档）在 `.scratch/special-terrain/pillars3d-20261020/`：`pillar3d_proto.py`、诊断脚本 `diag_winding_and_folding.py`、作图脚本 `pillar3d_figs.py`、`arrays/`。三个脚本均已从归档位置**重跑验证过**（exit 0）。原型与落仓模块**共用同一几何算法**，落仓版只是把它重写为仓内体例（dataclass + `FLAGS` + `SUPERSEDES` + `write_report`），**两者实测数字逐位吻合**——这是本次落仓最有用的一条对照证据。

> 时间列为**指示性**：同一代码两次分别得 plain 0.38 / 0.27 s、carved 8.99 / 8.44 s（与机器负载相关），不作为性能验收。

| 口径 | pillars | 高带 (m) | 满深度 | union (s) | 顶点 | 三角 | 体积 (m³) | 分量 | 闭合实体门 | 每截面简单 |
|---|---|---|---|---|---|---|---|---|---|---|
| `plain_prisms` | 16 | 44.40–133.48 | — | 0.381 | 3 755 | 7 506 | 11 985 720.22 | 1 | passed | 是 |
| `vdm_carved_walls` | 16 | 44.40–133.48 | **14/16** | 8.99 | 97 981 | 195 958 | 11 378 293.13 | 1 | passed | 是 |

`carve_scales = [1, 1, .5, 1, 1, 1, 1, 1, .7, 1, 1, 1, 1, 1, 1, 1]` —— 未满深度的两根是**截面本身就小**的胞（备选面积 832 / 2 277 m²），2 m 级雕刻会把它们折掉；代码逐级退让而非默默接受折截面。

**对比图**：`.scratch/special-terrain/pillars3d-20261020/pillars3d-prototype.png`（1547×1706）
三面板：①平面截面（16 个胞 + 一个胞在底/中/顶的雕刻轮廓，直接回应「不该是圆的」）；②单柱壁剖面（锥度 alone vs 锥度+雕刻，可见顶部铁帽外凸）；③真三维闭合实体场。

作图脚本同目录（仅读原型数组，只写本目录）。

---

## 6. 参数性质（必须随产物披露）

| 参数 | 值 | 性质 |
|---|---|---|
| `HEIGHT_BAND_M` | 40–150 m | 来源支持（单体高几十米至 400 m） |
| 铁帽厚度 `CAP_THICKNESS_M` | 30 m | 二手 |
| 节理发育（多组垂直节理控制形态） | — | 已核实（机制） |
| **`PITCH_M`（节理间距 / 柱间距）** | 30 m | **显式假设**（台账 §3） |
| **`JOINT_GAP_M`** | 6 m | **显式假设** |
| **`STRIKE_STRETCH`** | 1.6 | **显式假设** |
| **`STRIATION_A_M` / `_L_M`** | 0.55/0.22 m，24/14 m | **显式假设** |
| **`FLUTE_A_M` / `_PITCH_M`** | 0.55/0.22 m，16/7 m | **显式假设** |
| **`TAPER_FRACTION`** | 0.10 | **显式假设** |
| **`INWARD/OUTWARD_LIMIT_M`** | 2.0 m | **显式假设** |
| **`SUBSTEPS_M` / `RING_SPACING_M`** | 3 / 1.5 m | **显式假设**（却受 `SAMPLES_PER_FEATURE=4` 约束） |
| 张家界**单柱底径 / 高宽比分布** | — | **未取得**（台账 §3） |

---

## 7. 验收与未认证

**已做**：两个建造分支均 `exit 0`；`combine` 的 `_component_gate` / `_volume_gate` 均通过；每个柱体通过 `save_manifold` 的**反向二用流形门**；每根柱**逐水平截面**用 shapely 判定简单多边形（不过即逐级退让深度）；`components == 1` 单连通；六能力位全 False。

**未做 / 未认证**（落仓后**未变**，必须如实说）：
- **自交专项检查仍然没做**（仓内 `self_intersection_verified` 历来硬写 False；落仓版**保持 False**）。这里只保证**逐水平截面**是简单多边形（落仓实测 **256 检查 / 0 折**），**不保证整体三角网无自交**——这是本路线最大的未认证项。
- **未做规模验收**（16 柱 / 312 m 场地；真实张家界是 3000+ 柱 / 369 km²）。
- **未做性能验收**（`combine` 约 9 s，随柱数增长未测）。
- **仍未接进生产管线**：新模块**不**被 `metric_special_terrain_forms.py` / `metric_special_terrain_surface.py` 调用，Java 侧与 `TGMCMT01` 未动，它也不是任何已有身份的输入。
- **没有做 Minecraft 导出**。
- 没有做尘埃/植被/水流在柱壁上的交互。

---

## 8. 落仓（用户批准后已执行）

落仓要走的那一步在用户答「可以」后已经做了。改几何表示 = 改 `ALGORITHM` / `SCHEMA` / `identity`，**旧证书不得继承**，所以四件事逐条落到：

1. **新身份**。`terrain_pipeline/special_terrain_pillars3d.py`（1127 行）：
   - `SCHEMA = td-special-terrain-l1-pillars3d-v1`、`REPORT_SCHEMA = td-special-terrain-l1-pillars3d-report-v1`；
   - `ALGORITHM = joint-controlled-sandstone-pillar-field-with-vdm-carved-vertical-walls-v1`；
   - `PARENT_ALGORITHM = hybrid_rock_boolean.ALGORITHM`（**父模块零改动**，只 import：`BooleanParameters` / `polygon_prism_record` / `combine` / `census` / `solid_from_record` / `FLAGS`，加 `hybrid_cave_geometry` 的 `save_manifold` / `signed_volume` / `ray_hits` / `seal`）；
   - `SOLID_ROLE = pillar_field_rock`、`PLATEAU_ROLE = plateau`、`PILLAR_ROLE_PREFIX = pillar-`、`DEFAULT_ORIGIN = (0, 0, 0)`、`DEFAULT_OUTPUT = .scratch/special-terrain/l1-preview-20261020/pillars3d`；
   - `PillarParameters` dataclass（每个字段带范围校验，非有限浮点直接拒），参数本身作为 `EXPLICIT_ASSUMPTIONS` **随产物披露等级**（26 条，每条带 `grade` 与理由）；
   - `status = candidate`、**六能力位全 False**（`full_network_verified` / `hydraulic_ready` / `independent_audit_passed` / `natural_outlet_certified` / `publishable` / `self_intersection_verified`）。
2. **旧值作废声明**。报告顶层 `SUPERSEDES`（也导出为模块常量）指名 `kind = sandstone_pillar_field`、`superseded_schema = metric-special-terrain-v1`、`superseded_surface_schema = metric-special-terrain-surface-v2`，`replaced_by` 指向新 `ALGORITHM`，`not_a_certification = true`，并写明理由。**作废的是该 kind 的高度场几何值，不是那个模块或它的文件**——旧记录仍在盘上、仍可读，只是对这个地貌不再构成可接受的几何。
3. **产物** 仍在 `.scratch/` 下、仍带 `status = candidate`，`verification/` 一个字节没写；被 pin 的 `metric_*` / `diffusion/*` 零改动。
4. **原型重写为仓内模块**：几何算法搬运，外壳按 L1 范式重写，并**新增**报告顶层 `pillar_footprints`（16 项，含 `base_ring_xz_m` 节理胞环与 `ring_area_m2`）、`level_schedule`（层位表，本产物只记第 0 柱）、`plateau_ring_xz_m` / `plateau_bottom_y_m` / `plateau_top_y_m`——这三组是给预览与冷读用的，逐柱完整网格**不塞进报告**（体积太大，另存 `carved.npz` / `plain.npz`）。

### 8.1 落仓时新发现的两个真缺陷（勿重犯）

两个都是**先写结论、被实验推翻**那一类，价值比代码高：

1. **截面简单性门是假阴性，真因是容差不是几何**。该门用水平面切保存的三角网、把交点线缝回多边形。**共享竖边上的交点会被相邻两个三角各算一遍**，二者差 ~1e-11 m，而 shapely `polygonize` 要求端点**精确相等**——于是**笔直棱柱**也返回 0 个多边形，平铰数报成「折」。修法：缝合前把端点吸附到 **1e-6 m** 网格（`section_polygon_count`，吸附在 `np.round(..., 6)` 两行）；修后 plain 与 carved 都是 **256 检查 / 0 折**。容差随见证落盘（`section_endpoint_snap_m` + `method_note`），并已写进模块 docstring。
   > **教训**：门本身也要有假阴性告警意识。「几何不可能折」和「门判没折」是两件事，当门报大规模失败而几何上不该失败时，先怀疑门的数值前提。
2. **`overlap_removed_m3` 恰为 0 是对的，不是缺陷**（原型遗留的另一条错误断言）。节理缝让 16 柱互不相交，基座整体位于 `y < 0`（`-45 ≤ y ≤ 0`），声明的输入**互不重叠**，并集按定义**不减任何材料** → `overlap_removed_m3 = 0.0`、`overlap_removed_relative = 0.0`、`relative_residual = 1.64e-16`。「并集一定挖掉重叠体积」是个**默认假设**，在这个几何里不成立。真正可测的是 VDM 减掉了多少：`record["volume_account"]["carved_removed_m3"] = 607 427.0826254059 m³`。
   另：柱环面积比 **15.73**（角部 822.23 m² vs 内部 12 936.11 m²）是 **Voronoi 边界胞被 `box` 裁剪的真几何**，不是缺陷；初稿写的「< 12」阀值本身就是猜的。

---

## 9. 接进 `web-preview` 做真三维展示

第四项地形输入工作区「**石柱群 · 真三维闭合实体**」。**未新起前端工程、未改算法**，照 `special_surface` 的只读适配器范式：

| 文件 | 作用 |
|---|---|
| [`web-preview/pillars3d.py`](../web-preview/pillars3d.py) | 只读适配器。`REPORT_SHA256` / `REPORT_IDENTITY` / `CARVED_SHA256` / `PLAIN_SHA256` **四重硬 pin**，每次读取都重算并复核；任何一处被改就 `raise`，**拒显示而不是显示错的**。`catalog()` / `frame()` / `binary(name)`；`SOURCE_SCHEMA = td-special-terrain-l1-pillars3d-report-v1`。四个数组：`solid_vertices` / `solid_triangles` / `plain_vertices` / `plain_triangles` |
| [`web-preview/pillars3d.js`](../web-preview/pillars3d.js) | 三层：`carved`（雕刻后闭合实体）、`plain`（未雕刻棱柱线框，作对照）、`footprint`（柱顶**节理胞轮廓线**）。平面图画的**是多边形节理胞而不是圆盘**（直接回应最初的诊断）；着色可在「柱高 / 雕刻深度 step」之间切，两根未满深柱以锈色跳出 |
| [`web-preview/bridge.py`](../web-preview/bridge.py) | 新增三条只读路由：`/api/pillars3d/catalog`、`/api/pillars3d/frame`、`/api/pillars3d/array/<name>`（后者 `application/octet-stream`）；均为拒 query；`pillars3d.js` 加入静态白名单（**不入白名单就是 403**，这是本仓的一个真坑） |
| [`web-preview/index.html`](../web-preview/index.html) / [`web-preview/app.js`](../web-preview/app.js) | 面板 `#pillars3dControls`（含着色选单与状态行）+ `script`；`reviewCategories` 归入「地形输入」、`setWorkspace` 分支、`reset`、`reviewRecord`、`getSelection` 五处挂接 |

入口：`http://127.0.0.1:8765/?workspace=pillars3d`

**拓扑复用不重建**：数组就是保存的 `vertices_local_xyz_m` 与 `triangles`，前端直接交 `THREE.BufferAttribute`——既省一次三角化，也让「屏幕上的是保存几何」在代码层成立。

### 9.1 验收

- 契约单测 [`tests/test_pillars3d_preview.py`](../tests/test_pillars3d_preview.py)：**15/15 OK**。含「pin 与磁盘一致」「pin 被动过就拒读（两个方向各一条）」「catalog 不带任何能力位」「声明字节数与二进制体逐一相符」「拓扑复用」「`pillar_footprints` 描述节理胞」「体积账自洽」；另五条走真 HTTP，覆盖 400 / 404 / 白名单 403 / 页面注册工作区。
- 真浏览器验收 [`tools/verify_pillars3d_browser.mjs`](../tools/verify_pillars3d_browser.mjs)：**17/17**。本机无 playwright，所以照既有的 `verify_special_surface_browser.mjs` 用 **CDP + node 内置 WebSocket** 自起桥接与无头 Edge，从页面内部 `readPixels` 数非空像素。报告在 `.scratch/special-terrain/l1-preview-20261020/pillars3d/browser-verification.json`。

**为什么必须用真浏览器**：截图看不出「canvas 其实一直是 `hidden`」。本次特意查了 **隐藏另两层、只留 `carved`** 时仍能绘制（lit 仍 823095）——上一轮高度场工作区就是在这里翻车的（`saved-surface.js` 的共享控件自我订阅漏抄，三维从未显示，而二维一直在画、截图看着「有东西」）。同样的反直觉调用也在这里存在，所以 lint 和截图都不算数。

实测：三维 lit = **823 095**、仅 `carved` 层 lit = **823 095**、平面图 lit = **208 942**、切「雕刻深度」后锈色像素 **172 995**、导出能力位全 `false`、报告仍 `candidate`。

---

## 10. 下一步可选方向

本路线在 candidate 阶段已经完整（落仓 + 展示 + 验收）。要往下走，按性价比排：

1. **自交专项检查**——本路线最大的未认证项。只需在保存的三角网上跑一套通用自交检测，与现有「逐水平截面简单」是两回事。
2. **规模与性能**——16 柱 → 数百柱；`combine` 目前约 9 s，未测随柱数的增长曲线。这是它作为真实地貌候选的前提。
3. **接回生产管线**——目前它是个孤立产物：要真上天，得让上游按节理网布置供输入（不是自己起种子），并决定它进不进 Minecraft 导出。
4. **参数台账 §3 四个硬缺口**（单柱底径 / 柱间距 / 节理间距 / 高宽比分布）——现在全部是显式假设，有资料就能把最重的四个从「assumed」提到「secondary」。
