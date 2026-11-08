# 离线地形图渲染器（遥感图 / 地形图两种版式）

**日期**：2026-10-20  
**状态**：`status=candidate`，仅作插图；四能力位全 False；不认证任何河道、海口或湖泊。  
**范围**：新增 3 个文件，不触碰任何被 pin 的 `metric_*` / `diffusion/*` 内核。

## 0. 来龙去脉

用户看完六类特殊地形预览后提出两点（噪波 + 水力侵蚀，见 [special-terrain-surface-20261020.md](special-terrain-surface-20261020.md)），
随后给出四条方向性意见，并拍板：**先把预览做到遥感图 / 地形图格式**（A 做），**实时无限预览作为可选开关、默认关**（B，性能开销大），
Python 侧体素器（C）与米制气候补纬度（D）本轮不做。

对标物是另一个工程产的四张 3600×3600 预览（Nacrea，非本仓代码）。取证结论：
**「遥感图」与「地形图」的要素本仓基本具备，真缺口在三处纯出图逻辑**。

## 1. 交付面

| 文件 | 行数 | 作用 |
|---|---|---|
| `terrain_pipeline/terrain_map_style.py` | 约 305 | 全仓唯一的离线地形图样式层 |
| `tools/render_terrain_map.py` | 约 470 | 两种版式的渲染器 |
| `tests/test_terrain_map_style.py` | 约 305 | 25 项合约测试 |

**为何要建样式层**：六段 relief 色带此前在 `tools/` 下有**三份逐字副本**，陆/海色带另有**九份副本**。
新建渲染器若再抄一份，就是第四份。

**故意不迁移的副本**：`tools/compare_hydrology_projection_naturalness.fixed_hillshade` 与 delta 工具里的内联色带
**保留字节不变**——它们的 PNG 在 `verification/` 里作为证据（哈希被引用）。迁移是另一次显式审查的变更。

## 2. 两种版式

### `remote`（遥感图式）
连续 hypsometric 色带 + 物理 hillshade + 水系叠加：常流**实线**、非常流**虚线**。
后者的语义不是新造的——仓内已有 `permanent_channel_mask` / `seasonal_channel_mask`，
参见 `tools/review_td_channel_geometry.py:210-214`。
**不画公里网格**：网格是印刷图版的要素，卫星合成影像上盖网格与「纯影像」的观感相冲突。

### `topo`（地形图式）
离散分级色带 + **每条带边一条等值线**（隔一条加粗）+ 公里网格 + 比例尺 + 指北针 + 分级图例。

配色为**声明式制图风格**，不测量任何东西：

- 六段 relief 色带 `RELIEF_COLORS`（逐字继承既有三份副本）
- 14 个分级边界 `LAND_BANDS_M`（0→8000 m）+ 13 色 `BAND_COLORS`
- 混合式 `HILLSHADE_BASE=0.55` / `HILLSHADE_WEIGHT=0.65`（逐位继承，使新旧图可比）

## 3. 三处缺口的补齐

### 3.1 分级等高色带——全仓此前**不存在**
此前所有高程一律连续 `Normalize`。`banded_relief_rgb` 用 `searchsorted(side="right")-1` 离散分级；
`validate_band_edges` 强制首边 = 海平面且严格递增；`band_colors` 强制**颜色数 == 边数-1**。
顶级采用开区间：≥ 最后一边者取最后一色（故 `LAND_BANDS_M` 比 `BAND_COLORS` 多一项）。

### 3.2 经纬网——全仓此前 **0 处**
**这是一个口径问题，不是实现问题。** 本工程地形在**无限张量/瓦片像素坐标**上，不在球面上。
`diffusion/geography*.py` 里那句 `latitude = 22 * np.sin(z / 96)`（如 `geography_v5.py:54`）是
**纯 Z 坐标的函数**、只是用来调制温度的名义值，**不是真实地理纬度**。

因此分成两层：

- **默认**：`draw_metre_graticule` 画**米制坐标框**（公里网格），返回实际画了几根线。这是诚实且立即可用的。
- **可选**：`draw_declared_graticule` 只在调用方**显式声明** deg/m 换算时画，
  并在产物里 stamp `declared_graticule_not_a_projection` + 图上绰经度标签标 `*` + 一行小字说明。
  **拒绝猜测换算**（缺任一项就 `ValueError`）。它返回 `kind="declared_graticule_not_a_projection"`。

调用侧开关：`--declare-metres-per-degree-east/north` + `--declare-origin-degrees`（三个必须同给）。

### 3.3 比例尺——全仓此前只有 1 个脚本有
`nice_scale_length_km(span)` 取不超过图幅 1/4 的最大 1/2/5×10ⁿ；`format_scale_label` 小于 1 km 时用米。
白描边 + 端刻度，锚点用**有符号** y 跨度（见 §5）。

## 4. 两处被自己的实测拦下的真缺陷（**勿重犯**）

这两条都不是测试写错，而是第一版默认值本身是错的，且**报告会报出误导性的数字**。

### 4.1 `colour_range_m` 对大 TD 以外的数据源用错了参照系
第一版把 `FROZEN_ELEVATION_LIMITS_M = (0.609, 536.184)`（大 TD 图幅的冻结区间）当成**全局默认**。
后果：208 m 的喀斯特图被拉到 536 m 量程上，**实际起伏被压成 2.6 倍宽的色带**，塔林挤进一两个色阶；
而报告里的 `colour_range_m` 报的是 0.609..536.184，与 `plotted_max_m=208.386` 并列，读者会以为色带是对的。

**修正**：`resolve_elevation_limits` —— 调用方显式给就用；否则**默认取该图幅自身范围**；
**唯一例外**是 `DEFAULT_SOURCE`（默认大 TD 底图，比较性渲染），它仍保留冻结对，
以便新图能与 `verification/` 里的已有审阅图同尺并置。

### 4.2 `graticule_step_km=10.0` 在 0.16 km 的图上画不出任何线，报告却说画了
第一版默认步长写死 10 km。0.16 km 的特殊地形图上**零根线**，但报告里仍写 `"graticule": "planar_kilometre_grid"`。

**修正两条**：
1. `nice_graticule_step_km(span, divisions=6)` 按跨度推导（0.16→20 m、3.8→500 m、38.37→5 km）。
2. `draw_metre_graticule` 改为**返回实际画了多少根线**（`x_lines`/`y_lines`），
   报告改写这个记录而非重复请求值——**不再凭声明声称画了网格**。

同类问题也解释了为何 `large-td-lowland` 现在报 5 km（x8/y7）而不是 10 km：两个值都不算错，但前者才是图幅尺度的。

## 5. 倒置 y 轴的坑（`screen_frame`）

所有图幅用栅格约定：**z 向南增大**，图幅 y 轴倒置（`get_ylim()` 首值大于次值），屏幕上方是更小的 z。
`matplotlib` 的 *数据* 坐标里，把「底边」当成 `ymin` 是错的。
`screen_frame(axis)` 统一返回 `(xmin, xmax, ymin, ymax, signed_span = ymax - ymin)`；
`draw_scale_bar` / `draw_north_arrow` 都用**有符号**跨度，故同一套公式在两种朝向下都对。

因此**北箭头指向 z 减小方向**（图幅上方）——单测 `test_arrow_points_at_decreasing_z_on_an_inverted_axis` 钉死这一点。

### 5.1 测试取证上的一个坑
不能用 `FancyArrowPatch.get_path().vertices` 去验箭头方向：那个 path 在 patch 的**私有坐标系**里（实测跨度 1.07，而轴跨度 20）。
箭头两端挂在 `Annotation` 上：`xy` = 头、`xyann` / `get_position()` = 尾。

### 5.2 既有的饱和行为（如实记录，不掩盖）
`0.55 + 0.65·shade` 在满 shade 下 = 1.20 > 1.0，所以**亮度 > 0.975 的色带会饱和到纯白**（如 `#f4f3f0`）。
这是既有配方的固有行为，单测 `test_banded_relief_uses_the_declared_palette_and_blend` 把饱和作为断言记下。

## 6. 数据源与溯源

两种入口，都**强制溯源**：

- `--source`：路由地形归档（`original_td_m` + `receiver` + 可选两个河道掩膜）。
  校验：2-D、有限、spacing > 0、常流与非常流掩膜**不重叠**；有掩膜就必须有 receiver。
- `--bundle`：特殊地形表面 bundle，走 `load_special_form_surface(expected_sha256, expected_identity)`。
  **两者缺一就拒绝读取**，这是 bundle 契约的全部意义。
  `resolve_bundle_provenance` 从显式 flag 或同级 `manifest-report.json` 的 `forms` 段取，
  **绝不用待读文件自己的摘要糊弄**；取不到就 `SystemExit`。
- `--expected-source-sha256`：可选，提供则校验。

**输出护栏**：`guard_output` 拒绝写 `verification/`。

## 7. 实测结果（五组场景 + 一个经纬网变体）

**网格只进 `topo`**（见下表中的「网格步长 / 线数」一列，`remote` 一律不画）。

| 场景 | 图幅 | 跨度 | 色带（自身） | 网格步长 / 线数（仅 topo） | 等值线 |
|---|---|---|---|---|---|
| large-td-lowland | 1280² @30 m | 38.37 km | 0.609..536.184 m（冻结对） | 5 km / x8·y7 | 5 |
| volcanic_plug | 411² @1 m | 0.41 km | 0..285.427 m | 50 m / x9·y9 | 3 |
| inselberg | 276×476 @8 m | 3.80 km | 0..369.063 m | 500 m / x7·y5 | 4 |
| sandstone_pillar_field | 321² @0.5 m | 0.16 km | 0..158.573 m | 20 m / x9·y9 | 2 |
| karst_tower_field | 491² @1 m | 0.49 km | 0..208.386 m | 50 m / x9·y9 | 3 |
| large-td-lowland-geo | 同上 | 同上 | 同上 | **声明式经纬网变体**（绰经度标 `*`） | 5 |

四类特殊地形 bundle 带 `caveats`：**合成解析图幅、非真实 TD 细节；图上无路由，故不画河网**。
大 TD 底图带的是：平面像素网格非地理投影；河线显示**存储路由**，不是已认证床面。

真实底图口径（与既有审阅图逐位一致）：`origin_xz_m=[353280, -1443840]`，spacing 30 m，
常流 22856 / 非常流 7942 链接，源 sha256 `e7a3a7b2…`，高程域与冻结 `ELEVATION_LIMITS` 逐位相符。

## 8. 验收

- `tests/test_terrain_map_style.py` **25/25 OK**（判成功看输出里的 `OK`；PowerShell 下 Python stderr 被当 NativeCommandError，exitCode 恒 1）。
- 渲染器 6 次调用全 exit 0，产物 PNG + `report.json` 齐备，每个 `report.json` 的 `sha256` 与磁盘文件重算一致。
- **两条拒绝路径实测触发**：无溯源 bundle、篡改 sha256。
- **输出护栏**：写 `verification/` 被拒。

## 9. 未做 / 未认证

- **B（实时无限预览）**：用户定为**可选开关、默认关**，本轮**未开工**。
- **群系图**：参考图里那 8 类群系是**纬度带驱动**的，而米制气候**没有纬度**；Java 侧有 16 个 biome json 但接不出来。
- **尺度的量级差**：参考图约 500 km，本仓最大单幅 38.4 km（差约 13 倍线性 / 170 倍格数）。
  上游本身是无限张量（`diffusion/backend.py:60-73` 可按任意世界坐标取窗口），**缺的是多分辨率金字塔，不是新算法**。
- **高程/海深数据域**：米制主线海深上限仅 40 m，参考图要 −6000..8000 m，需**扩容数据域**。
- 未改任何被 pin 的 `metric_*` / `diffusion/*`；未改 Java 消费端；未动 `TGMCMT01`。

## 10. 参数性质说明

除「继承既有副本 / 内核对内惯例」外，本文档涉及的**色带断点、颜色、hillshade 权重、分级边界均属声明式风格（显式假设）**，
没有公开资料给出这几类地形图应用什么色带。`FROZEN_ELEVATION_LIMITS_M` 是从既有大 TD 审阅工具抄来的**已有声明**，不是推得的值。
