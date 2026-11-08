# 山川形意 · 本地地形预览

## 界面视觉与 3D 查看器统一约定

界面采用「现代复古」风格：暖炭底色、旧纸色文字、琥珀（主强调）/青绿（水、保存）/赭红（侵蚀、警示）三个强调色；标题用衬线体，标签与数值用等宽体，面板用细线与硬阴影。样式只在 `style.css` 的 `:root` 变量里定义，改色请改变量，不要在组件里写色值。

2D 画布与全部 Three.js 查看器共用同一套调色板与相机语义，集中在 `renderer.js` 开头的两个全局对象，经典脚本，先于所有模块加载：

- `TerraTheme`：调色板、地形渐变 `relief(t)`、切深渐变 `cut(v)`、侵蚀／沉积发散色。2D 用 CSS 字符串，3D 用同一组 RGB 数值。
- `TerraView`：`createScene`（背景＋灯光）、`createRenderer`、`createCameras`、`configureControls`（左键旋转、右键平移、滚轮缩放、可绕到下方；地图相机左键平移）、`frame`／`frameMap`（取景）、`keepInView`、`material`（材质色表）、`linearColor`（sRGB→线性，顶点色必须经此上传）、`hud`（左下视图徽标与右上操作提示）。

每个 3D 查看器（`faultSurface`、`savedSurface`、`specialSurface`、`pillars3d`、`undergroundSurface`、`riverResultScene`）通过 `TerraView.register(name, api)` 注册，并满足同一接口：`render`、`resetCamera`、`reviewRecord`、`isLoading`、`isActive`、`close`。原有的 `window.xxx` 全局名与各自的专用方法（`open`、`load`、`begin`、`setTime` 等）保持不变。新增 3D 查看器时只需复用 `TerraView` 的构造函数并注册，不要再各写一份场景、灯光和相机代码。

本次改动只涉及显示：`style.css`、`index.html` 与上述前端脚本，不触及 `bridge.py`、任何算法、保存包或验收数据。

## 只读审查与失败清理

保存河槽、全域覆盖和保存水面帧的来源、算法身份、米制单位与保存时间沿用原产物；展示抽稀不改变账本或全域统计。读取开始即清空旧几何、选择、账本与可导出记录；HTTP 失败、异常包和 60 秒请求超时保持空结果。工作区切换沿用请求序号丢弃迟到响应，候选与诊断层不提升为认证河槽、水面或自然出口。

验收入口：`tools/verify_td_readonly_review.py --output <工作区报告目录>`，检查桌面/手机冷读身份、图层、选择与导出一致性，以及异常响应、超时、迟到请求和保存帧失败清理。六案例二维/三维回归入口仍为 `tools/verify_td_river_results_browser.py`。

## 全域谷地河槽覆盖审查

入口：`http://127.0.0.1:8765/?workspace=global`，或「河网算法 → 全域几何 · 覆盖与排除」。`GET /api/river-results/global` 读取固定网络计划、全域 tiled 失败前缀和 `td1024-20261011-01/scope-exclusion.json`；TD底图上绿色显示623条已接受边，红色显示本轮排除的50条 owner-divide 边。支持图层开关、逐条排除边选择与完整审查导出；侧栏提供覆盖、材料账、来源和排除证据，保持 `publishable=false`。

排除仅划分本轮交付范围；母集仍为673条，重路由尚未评估。旧诊断中的0.1是无量纲半径缩放系数，不是0.1米。前端使用来源元数据的米制坐标，TD底图每8格取样并保留末边界，仅用于显示。验证入口：`tools/verify_td_global_geometry_browser.py`。

默认入口仍是「河网成果验收 · 真实河槽与水沙」，包含六个 M5/M6/自然谷地案例。全域覆盖图展示边的位置与接受状态，不把网络计划折线称为新的已生成床面。

## 真实TD形态候选

阶段3–5固定审查通过 `data/natural-stage-review-v1/manifest.json` 绑定本轮六类原生保存候选、截弯材料与残留库存，以及阶段4证伪报告；仍使用原 `/api/morphology/case` 和形态工作区。各子包冷读与SHA复核通过后才整体显示；任意子包或父来源变化拒绝整个读取。

「原始／候选」消费真实保存before/after床面，点选原生格显示前后床高与截弯库存。账本保留事件、重验、失败例、能力和阶段4全部场景状态、离群统计、消融及资源；长数值序列仅摘录显示，导出保留完整报告。不同窗口的沉积／床变证据单独说明scope，不叠加到当前地形。静态库存情景不推进物理时间，残留level-pool并非认证水面，拓扑、水动力、自然出口和发布能力保持false。

固定pin准备入口：`tools/prepare_td_stage_review.py`；浏览器验收：`tools/verify_td_stage_review_browser.py`，包/身份回归：`tests/test_td_stage_review.py`。本轮新后端试用端口为8766。

最终功能证据：`verification/td-natural-river-stages/stage5-browser-20261011-02/report.json`；桌面/手机首屏、画布与三维旋转的最终布局证据：`verification/td-natural-river-stages/stage5-layout-20261011-01/report.json`。3项保存适配测试通过，24个阶段4场景均保留。01为验证器身份字段修正前失败诊断，03主动取消重复批次；这两份不计入完成证据。试用：`http://127.0.0.1:8766/?workspace=morphology`。

历史兼容入口：未配置阶段审查manifest时，形态工作区仍读取 `verification/td-morphology-candidates/td256-20261010-01/`，显示真实TD局部窗口的原始地形和六类候选：三角洲、截弯取直、外弯冲刷/内弯点坝、辫状分汊、冲积扇、洪泛平原。支持二维/三维、候选选择、原始/候选高程图层、父图身份、来源SHA和材料/储量摘要。

前端只读取已保存候选包；显式水陆解释、中心线和候选形态不会被界面升级为自然河口、真实水动力或已写回主RoutingGraph。水动力、自然出口和发布能力保持false。

## 地下暗河 V1

入口：`http://127.0.0.1:8765/?workspace=underground`，归入「河网算法」。默认读取固定真实山地的125.3m洞道新成果；透明岩体默认开启，中心线默认关闭。支持2D/3D、开挖前后岩体、VDM洞道、移除岩石、断面剖切与选择、参数生成和审查导出。

`GET /api/underground/case` 只读绑定来源的保存包；`POST /api/underground/generate` 只接受seed、侧向幅度、宽度倍率和洞顶变化四个字段。输入编辑不重算，点击生成才启动有界子进程，结果另存不可覆盖的独立包。新参数不会改变原始来源或默认保存包。

这是固定两端、有界窗口的构造洞道生成，非自动自然洞道发现。生成器几何检查通过不等于独立审计、完整接回认证或水力完成；水面为空，不提供假动画。算法契约、预算、实际数据和后续事项见 `docs/underground-river-v1.md`。

## 特殊地形 3D 工作区

入口：`http://127.0.0.1:8765/?workspace=special`，或「地形输入 → 特殊地形 · 合成图幅 3D」。这一项目展示 L0 四类特殊地形 v2 保存网格（inselberg / karst_tower_field / sandstone_pillar_field / volcanic_plug），全分辨率顶点与**存储的**三角形拓扑——不重建拓扑。

只读 API：`GET /api/special/catalog`、`GET /api/special/frame/<kind>`、`GET /api/special/array/<kind>/<name>`。三条路由都拒绝 query，`array` 走 `application/octet-stream`；清单本身被 SHA256 硬 pin，元数据改动无法悄悄换掉某个归档，收敛声明由读取端复算而非相信台账。

图层为「保存地表 / 解析参考面 / 侵蚀变化 · m / 保护区单元」；侵蚀变化默认关（大面积覆盖会挡住地形）。二维可在「侵蚀变化 · m」与「地表高程 · m」间切换；点选显示 `[row, col]`、高程与侵蚀变化。

这些是**合成分析图幅**：非地理参照、非水力成果，`hydraulic_ready` / `natural_outlet_verified` / `publishable` / `self_intersection_verified` 全为 false。详情见 `docs/special-terrain-3d-preview-20261020.md`。契约测试 `tests/test_special_surface_preview.py`（**11/11 OK**）；真浏览器验收 `node tools/verify_special_surface_browser.mjs`（**CDP + node 内置 WebSocket，不依赖 playwright**，**14/14**），它直接 `readPixels` 数非空像素，能抓住「canvas 建了但从未显示」这类截图看不出的缺陷。手机档与真机触控本轮未验。

## 石柱群 · 真三维闭合实体

入口：`http://127.0.0.1:8765/?workspace=pillars3d`，或「地形输入 → 石柱群 · 真三维闭合实体」。这个工作区展示的是[石柱群真三维落仓产物](../docs/special-terrain-pillars-3d-20261020.md)：不是高度场网格，而是真实的**闭合实体**（节理控制的多边形棱柱 + VDM 雕刻柱壁），拓扑直接复用保存的三角形，不重建。

只读 API：`GET /api/pillars3d/catalog`、`GET /api/pillars3d/frame`、`GET /api/pillars3d/array/<name>`。三条路由都拒 query，`array` 走 `application/octet-stream`；报告按 **SHA256 + identity**、两份网格档案按 **digest** 共四重硬 pin，每次读取都复核——任何一处被改就拒读，而不是显示错的字节。

图层：`carved`（雕刻后闭合实体） / `plain`（未雕刻棱柱线框，作对照） / `footprint`（柱顶**节理胞轮廓线**）。平面图画的**是多边形节理胞而不是圆盘**（这是该项目最初的诊断所在）；着色可在「柱高」与「雕刻深度 step」之间切换，两根未刻到满深的柱会以锈色标出。

这仍是 **candidate 产物**：不是水力成果，六能力位（含 `self_intersection_verified`）全为 false；这里只保证**逐水平截面**是简单多边形（256 检查 / 0 折），**不保证整体三角网无自交**。契约测试 `tests/test_pillars3d_preview.py`（**15/15 OK**）；真浏览器验收 `node tools/verify_pillars3d_browser.mjs`（**CDP + node 内置 WebSocket，不依赖 playwright**，**17/17**）。对应地，`sandstone_pillar_field` 在「特殊地形 3D 工作区」（高度场那一版）里的几何值已被声明作废——作废声明只出现在新模块自己的报告里，旧模块与它的文件一字未动。

## 算法审查分类与相机

主导航统一为「地形输入」「VDM 算法」「河网算法」。地形输入按来源组织，当前包含 Terrain Diffusion 保存高度场、DEM 诊断与特殊地形合成图幅 3D；该类别不限定 TD，后续实际接入的新算法可加入输入项目。VDM 包含岩壁形态/参数变形与真实断层平移，河网包含最新 AMR、共享边界、原生降雨水量、盆地出口和历史工程案例。

默认打开河网真实成果验收；类别下的审查项目和案例分别筛选，历史 TD 样本可切换原始高度场/派生对照。来源、单位、保存 ledger、图层、选择和导出是共用面板；导出包含中性的类别身份 `terrain / vdm / rivers` 以及当前项目身份，不把 TD 当作整个地形输入类别。

三维交互采用相机绕地形，左键旋转、右键平移、滚轮缩放、单击点选。AMR 两轴方向已修正，其他三维视图使用相同角度方向和画布高度归一的灵敏度。允许绕到下方查看悬挑背面，竖直轴保持固定。原生小时页仍只支持二维，纯证据项目不显示虚假的三维能力。

VDM 的黄色连线表示参考面顶点到派生岩壁顶点的位移，不是拓扑方向或水流方向。「VDM 位移向量」作为独立图层默认关闭，可按需勾选；与河网边开关互不影响，审查导出保留该图层状态。黄色保护点仍由「保护／域边界」控制。

验证与决策见 `.scratch/frontend-review/spec.md`；导航、方向、下方观察、导出、手机像素检查使用 `tools/verify_review_navigation_camera.py`，全保存包检查使用 `tools/verify_saved_surface_frontend.py`，历史案例使用 `tests/test_surface_review_browser.py`。

本轮最终验证通过：`verification/frontend-review/navigation-camera-20261004-03/report.json` 与 `verification/frontend-review/categories-camera-20261004-02/report.json`。审查发现、修复和测试边界见 `.scratch/frontend-review/delivery-20261004.md`。直接打开地形输入：`http://127.0.0.1:8765/?workspace=terrain`。

## 真实断层局部审查

入口为 `http://127.0.0.1:8765/?workspace=fault`，或「VDM 算法 → 断层平移」。`GET /api/fault/case` 读取固定保存包；「生成断层预览」显式提交 `POST /api/fault/preview`，不写保存包、不推进水力。输入变化不会触发计算。预览失败或请求开始会清除旧几何并禁用导出；跨工作区及新请求用 `requestSerial` 丢弃过期响应。

POST body 只包含五个字段，不接受客户端来源路径：

```json
{"plane_origin_xz_m":[-183648.5,64591.5],"strike_degrees":18,"slip_m":4,"moving_side":"positive","transition_width_m":6}
```

滑移范围为 [-8, 8] m，过渡宽度为 [1, 30] m，走向范围为 [0, 360]°；切面原点限制在后端固定局部范围。固定选择为 row 2:17、col 72:87。返回 schema 为 `fault-case-v1` 或 `fault-preview-v1`，必需包含真实 `identity`、`source`、`metadata`、`geometry`、`report`、`defaults`、`selection` 及 mesh。前端使用返回的局部重编号三角形及 seamEdges，不插值、不补侧壁、不封实体。

`fault-surface.js` 复用本地 Three.js 0.180.0 和 OrbitControls，先减去相对原点再上传 Float32 XYZ。二维为同一真实 mesh 的正交俯视；三维为轨道相机。`before` 严格使用后端 `mesh.reference`（已施加 VDM、尚未断层平移），不是 TD/H0；`after` 使用 `mesh.vertices`；`compare` 分屏使用同一相机与原点。重置返回局部范围，不假造完整地形；完整 TD、VDM、河网仍可通过原导航审查。

画布为 `#faultSurface`；模式为 `#faultMode`（after/before/compare），操作为 `#faultSaved` 与 `#faultPreview`。参数 ID 为 `faultDirection`、`faultX`、`faultZ`、`faultSlip`、`faultTransition`、`faultSide`。图层 checkbox 的 `data-layer` 为 `faultSeam`、`faultMoving`、`faultProtected`，初始均关闭，且不改变旧 VDM 黄色位移图层默认值。点选显示原 source vertex/face ID；切缝新顶点保留后端 sourceVertexIndex（可能为 -1），不伪造原始 ID，同时显示 side、displacement、transitionWeight 和保护标记。

`window.faultSurface.reviewRecord()` / `isLoading()` 供浏览器验收调用。记录含 identity、source、metadata、geometry、report、已应用 recipe、mesh_counts、view、mode、camera position/target/relative_origin_xyz_m、layers、selection。参数编辑不会更改已应用 recipe。只有成功加载保存包或预览才返回 `geometry_generated: true`，加载中或失败返回 null。状态为 diagnostic，hydraulic_ready / natural_outlet_verified / publishable / self_intersections_verified 均为 false，不宣称 accepted。导出绑定当前真实结果而非尚未提交的表单。

协调代理已实际完成 `tools/verify_fault_preview_frontend.py` 的桌面/手机/宽屏像素、相机、前后对照、正负滑移、非法拒绝和导航验收，最终证据为 `verification/metric-vdm-fault/frontend-20261005-03/report.json`。正式 API 读取 `run-v2-20261005-02`，在已经 VDM 变形的岩壁上进行局部切割；旧 v1 切在原 chart 的问题不再进入预览。完整限制见 `.scratch/metric-vdm/fault-frontend-delivery-20261005.md`。

## 最新单域三维与共享边界审查

「单域三维 · AMR」读取第一阶段固定消费包；不用运行 `build_data.py`。只需运行下方 `serve.py`。新增本地 Three.js 三维全分辨率床/水、二维平均水深/床高/实际叶间距、两组域切线、保存时间播放、点选及来源身份导出。AMR 240²/1m canonical 的实际叶为 4/2/1m，原生为 256²/30m；uniform 包仍保留空间深差失败诊断。

只读 API：`GET /api/saved/catalog`、`GET /api/saved/frame/<amr|native|uniform>/<scenario>/<index>`、`GET /api/saved/array/<package>/<scenario>/<index>/<name>`。只读桥接逐请求复核 SHA，缓存上限一帧，使用已有 consumer 加载器绑定保存来源；不推进水力。fan 中心水深可能是平均水深三倍，静态 receiver 骨架不是瞬时流向。

本地依赖在 `vendor/`，锁定 Three.js 0.180.0；若依赖缺失，在该目录执行 `npm ci --ignore-scripts --no-audit --no-fund`。浏览器无需 CDN。实际桌面/手机、canvas 像素、轨道缩放/点选、播放、末帧、来源导出和返回 VDM 的验证见 `verification/fine-domain-mosaic/frontend-20261004-04/report.json`；第二阶段范围与剩余工作见 `.scratch/fine-domain-mosaic/delivery-20261004.md`。

以下为原前端交付时的历史说明，不能据此把新固定包标成前端未接入。

在工程根目录执行：

```powershell
python web-preview/build_data.py
D:/anaconda/python.exe -X utf8 web-preview/serve.py
```

导出需要 NumPy；网页服务使用 Python 标准库，并通过 `bridge.py` 提供固定来源目录、TD 逐页读取和受保护的 VDM 局部预览接口。打开 `http://127.0.0.1:8765/`。服务只绑定本机，按 Ctrl+C 停止；不会启动模型推理、重新求解水文或写入游戏世界。

工作台保留 `web-preview/data/surface-review-v1/manifest.json` 的 13 个米制审查案例和 `data/manifest.json` 的旧 diffusion 样本。地表案例支持二维/三维、图层、选择、时间序列和审查记录导出。旧 diffusion 样本明确标为方块坐标历史资料，不能与 TD/VDM 的米制 XYZ 结果混称。

VDM 工作区读取固定六形态 gallery，并提供保存形态读取和显式 `POST /api/vdm/preview` 局部预览。`surface_curvature_m`、`end_elevation_difference_m`、`extension_direction_degrees` 保持独立语义，单位为米或度；源码不静默缩小超限参数。保存网格以 XYZ 和三角拓扑呈现，保护区与位移向量作为几何证据显示。它不是自然出口认证、地下洞穴或水力结果。

TD 工作区通过固定的 temporal refinement execution index 按需读取 eastward / westward 每方向 24 个小时页，加一个初始状态，共 25 个状态。原生页为 256×256、30 m 网格；绘图使用 4 格抽稀，但全域水量统计使用有效原生网格。水深是 m，soil/fast/slow 是 mm，降雨是 mm/h；`face_forward_m3` 与 `face_reverse_m3` 是小时累计体积，不是瞬时流量，界面另给出该页净小时平均值。旧原生水面和受限河谷路径保留为独立诊断来源，不自动贴合到 TD 细步页。

盆地工作区展示保留蓄水、有限切穿、有限填洼三种候选比较；当前均为 diagnostic，且自然海口、细槽水力、跨精度耦合和 publishable 状态未认证。断层工作区读取真实开放切割网格并提供显式预览，不移动水面或河道。

桥接接口包括：`GET /api/catalog`、`GET /api/vdm/gallery`、`GET /api/vdm/case/<kind>`、`GET /api/td/catalog`、`GET /api/td/page/<eastward|westward>/<hour>`、`GET /api/basin/comparison`、`POST /api/vdm/preview`、`GET /api/fault/case`、`POST /api/fault/preview` 和客户端导出用的 `POST /api/export`。旧 `/api/fault/draft` 不再由前端调用。固定 JSON、NPZ 和 manifest 读取均经过显式路径、schema、SHA256 或 identity 检查；静态文件服务也按 manifest 白名单限制。

本次断层 UI 写集为 `web-preview/index.html`、`app.js`、`renderer.js`、`style.css`、`README.md` 和新增 `fault-surface.js`。没有修改 `bridge.py`、`fault_preview.py`、算法或冻结验证包；后端由独立代理维护。
