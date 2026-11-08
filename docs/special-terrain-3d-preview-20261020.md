# 特殊地形 3D 审查工作区（2026-10-20）

用**已有** `web-preview/` 前端把四类特殊地形 bundle 以三维形式展示。这是用户明确要求——
「用已有的前端用 3D 的形式展示」——因此没有新起前端工程，也没有改任何算法。

## 0. 来龙去脉

此前特殊地形只有离线三栏 PNG 对照（`.scratch/special-terrain/surface-preview-20261020/`）。
用户希望能在工作台里转着看那一整片米制地形，于是本轮把保存网格接进既有的 Three.js 工作区。

四条纪律全程未破：产物 `status=candidate`、四个能力位全 False、被 pin 的
`metric_*` / `diffusion/*` **零改动**、不写 `verification/`。

## 1. 交付面

| 文件 | 性质 | 说明 |
|---|---|---|
| `web-preview/special_surface.py` | 新增 ~178 行 | 只读适配器：硬 pin 清单 + 四个 bundle，`catalog()` / `descriptor(kind)` / `binary(kind,name)` |
| `web-preview/special-surface.js` | 新增 ~237 行 | 三维工作区：Three.js 轨道相机 + 二维变化图 + 图层 + 点选 + 审查导出 |
| `tests/test_special_surface_preview.py` | 新增 ~159 行 | **11/11 OK**：适配器 6 项 + 真 HTTP 路由 5 项 |
| `tools/verify_special_surface_browser.mjs` | 新增 ~234 行 | CDP 真浏览器验收（**14/14**），不依赖 playwright |
| `web-preview/bridge.py` | 修改 | 三条 GET 路由 + 静态白名单加 `special-surface.js` |
| `web-preview/index.html` | 修改 | 面板 `#specialControls` + `script type="module"` |
| `web-preview/app.js` | 修改 | `reviewCategories` / `setWorkspace` / `reset` / `reviewRecord` / `getSelection` 五处挂接 |
| `web-preview/style.css` | 修改 | `.special-canvas`（一条） |

## 2. 后端契约

```
GET /api/special/catalog                    -> special-surface-catalog-v1
GET /api/special/frame/<kind>               -> special-surface-case-v1（JSON descriptor）
GET /api/special/array/<kind>/<name>        -> application/octet-stream
```

`<kind>` ∈ `inselberg` / `karst_tower_field` / `sandstone_pillar_field` / `volcanic_plug`；
`<name>` ∈ `surface_vertices` / `surface_triangles` / `reference_vertices` / `change` / `protected`。
三条路由都**拒绝任何 query 参数**（400）。未知 kind → 500（`unknown special-terrain form`），
不匹配的路径形状 → 404。

二进制体沿用 `saved_surface` 的范式：JSON descriptor 带
`arrays[name] = {dtype, shape, bytes, url}`，数组另走 octet-stream。顶点先减去自身 AABB 最小点
（`origin_xyz_m`），dtype 定死 `<f4` / `<u4` / `<u1`，前端直接组装 `THREE.BufferAttribute`。

**拓扑复用，不重建**：`surface_triangles` 就是存储的 `triangles`（`(2(r-1)(c-1), 3)`）。
这既省一次三角化，也让「显示的是保存几何」这句话在代码层面成立。

## 3. 溯源与拒读

- 清单本身被 SHA256 pin（`MANIFEST_SHA = d1f12249…`，59486 B），**元数据改动无法悄悄把某个
  kind 指向另一个归档**——加形态必须重新 pin 常量，是一次显式源码修改。这是
  `saved_surface.ACCEPTANCE_SHA` 的下一层。
- 每个 bundle 另按 manifest 里的 `sha256` + `identity_sha256` 双重校验；
  路径 `resolve()` 后必须仍在工程根内，大小 ≤ 256 MiB。
- `metadata.parent_identity_sha256` 必须与清单一致，否则拒绝——父图身份漂移不会被当作新形态放行。
- **收敛声明由本模块复算，不相信台账里的布尔**：`record_status()` 用
  `relaxation_maximum_excess_m <= relaxation_tolerance_m` 重新推导；与清单里的
  `relaxation_converged` 不一致就 `raise`（这正是 v2 验收器拦下的那类缺陷，
  在读取侧也必须堵住）。

## 4. 前端

- **三维**：`surface`（保存地表，实体）、`reference`（解析参考面，线框淡显）、
  `change`（侵蚀变化，顶点色发散色带，默认关——大面积覆盖会挡住地形）、
  `protected`（保护区点云，仅在 `protected_cells > 0` 时建）。
- **二维**：`#specialField` 在「侵蚀变化 · m」与「地表高程 · m」之间切换；变化图用同一套
  发散色带（切蚀偏锈红、淤积偏青），高程图用连续褐绿带。
- **点选**：三维用 `THREE.Raycaster`、二维用反投影，两者都换算成 `[row, col]` 并显示
  `elevation_m` / `erosion_change_m`。索引 = `row * cols + col`，与 `vertices_xyz_m` 的行主序一致。
- **相机**：沿用既有语义——左键旋转、右键平移、滚轮缩放；`重置视图` 走 `resetCamera()`。
  垂直倍率复用共用滑杆（仅显示比例，不回写高程）。
- **导出**：`reviewRecord()` 带 `schema: special-surface-review-v1`，含 bundle/manifest 摘要、
  identity、父 identity、算法、`chart_shape`、`spacing_m`、relief/change 区间、净变化、
  保护区计数、收敛态、图层与相机；四个能力位**硬编码 false**。

## 5. 实测

```
catalog: 4 forms / status candidate / algorithm special-terrain-facet-noise-hydraulic-dissection-v2
inselberg             276×476 @ 8.0 m  起伏 0–369.06 m  变化 −20.56…+11.08 m  净 −2.751e6 m³  finite_stop
karst_tower_field     491×491 @ 1.0 m  起伏 0–208.39 m  变化 −10.61…+13.66 m  净 −9.532e3 m³  converged
sandstone_pillar_field 321×321 @ 0.5 m 起伏 0–158.57 m  变化 −11.40…+11.63 m  净 −6.119e2 m³  converged
volcanic_plug         411×411 @ 1.0 m  起伏 0–285.43 m  变化 −41.61…+6.05 m   净 −1.224e5 m³  finite_stop
```

每个 kind 的 5 个数组逐一对上声明字节数（如 karst 三角形 5 762 400 B / 480 200 面）。

**路由实测**（真 HTTP，非 mock）：`catalog` 200；四 kind 的 `frame` + 20 个数组 URL 全 200 且
`Content-Type: application/octet-stream`、长度与声明一致；带 query 的 frame → 400；
未知 kind → 500；`/api/special/frame`（形状不匹配）→ 404；`/special-surface.js` → 200，
`/special-surface-nope.js` → 403（白名单生效）。

**浏览器实测**（真浏览器，非静态检查）：本机没有 playwright，但 Edge/Chrome 的 headless 模式可用，于是用 **Chrome DevTools Protocol + node 内置 WebSocket**（node ≥ 22）写了一个自包含的验收器 [`tools/verify_special_surface_browser.mjs`](tools/verify_special_surface_browser.mjs)：自己起桥接与无头浏览器、开 `?workspace=special`，从页面内读回真实状态。它做的是截图做不到的事——直接 `readPixels` 数非空像素。

```
14/14 checks passed
ok  three-dimensional group rasterises: {width:871,height:896,hidden:false,lit:780416}
ok  flat map paints: {hidden:false,width:871,height:896,lit:140640}
ok  first form reads a pinned bundle: inselberg
ok  switching form reads a different bundle: sandstone_pillar_field
ok  three dimensions survive a form switch: {lit:780416}
ok  export is enabled and refuses to claim capability: bounded_relaxation_converged export=true
ok  page has no script errors
```

报告落在 `.scratch/special-surface-browser-report.json`（schema `special-surface-browser-verification-v1`）。

**一个真缺陷（浏览器实测才抓到）**：`view3d` 点击后 canvas 仍 `hidden`、非空像素 **0**——`saved-surface.js` 里的共享控件绑定（`:157` 的 `for(const id of ['view2d','view3d','verticalScale'])…`）我漏抄了，而 `app.js` 的 `renderWorkspace()` 只调 `surfaceRenderer.render()`、不驱动本模块；于是切三维时它自己的 canvas 从未显示。补上自我订阅后：`lit` 0 → **780416**。**教训：照抄模板时，“不显眼的那几行”往往就是接通的那一根线。**

**回归**：`test_underground_preview_bridge` + `test_fault_preview_bridge` +
`test_web_preview_river_results` + `test_special_terrain_l1_cave_bridge` **40/40 OK**，
既有工作区未受影响。`bridge.py` / `special_surface.py` `py_compile` 通过；
两个 JS `node --check` 通过；HTML id 无缺失、无重复。

## 6. 未做 / 未认证

- **手机像素与真机触控未验**：本机只有桌面 headless Edge；本仓库既有的 playwright 验收器（桌面/手机双档像素、触控、冷读身份）本机跑不了。本轮的 CDP 验收器只覆盖桌面一档。
- 点选（`Raycaster` / 二维反投影）与导出按钮的端到端行为未在验收器里逐项断言——验收器验的是渲染与非空像素、图幅切换、图层列表与导出记录字段。
- 工作区未登记进 `bridge.fixed_catalog()["workspaces"]`（那是展示登记，前端导航不读它）。
- **大 TD 底图（1280²@30 m，38 km）不是本工作区的对象**——本工作区只读四类特殊地形 bundle。

## 7. 纪律与参数性质

- 产物 `status=candidate`，`hydraulic_ready` / `natural_outlet_verified` / `publishable` /
  `self_intersection_verified` 四位全 False，前端与导出两处都写死。
- 面板与图注明写「合成分析图幅 · 非地理参照 · 非水力成果」；descriptor 里带同一句 `semantics`。
- `spacing_m`、`relief_reference_m`、变化区间等全部**继承自 bundle 声明**，本工作区不新造任何
  数量；发散色带的锚色与权重是**声明式显示选择**。
- 被 pin 的 `terrain_pipeline/metric_special_terrain_surface.py` 等内核**零改动**。