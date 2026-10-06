# 地表審查工作臺

## 2026-10-01 有界升级与复跑

保留 Sonnet 原有页面、旧扩散案例和已保存来源。当前 manifest 包含 13 个
保存案例：原五类、31 的 baseline/pulse/tailwater/failed/cancelled、32 统一
两出口工程、兼容 1m/2m wet seam、33 的 land-footprint-engineering。
accepted 标签只表示对应独立 review 的有界数据验收，不代表页面或自然性认证。

导出：`python -X utf8 web-preview/build_surface_review_data.py`。可用
`--output <directory>` 做隔离复跑。每次写独立 version 目录，固定来源 SHA256
在读取前、缓存命中时及发布前重核；bundle identity 与 verifier/report/review
绑定检查。缺独立 review 标 pending，失败 verifier 或身份/哈希不一致拒绝。
manifest 最后 fsync + atomic replace；失败保留旧 manifest，既有源和版本不覆盖。

浏览器：`python -X utf8 tools/verify_surface_review_browser.py`，只使用现有
Playwright 与已安装 Edge，不下载浏览器、不加依赖。工具自启本地临时 HTTP
服务，结束即关闭，证据写新的 `verification/surface-review-browser/run-UTC/`。
测试：`python -X utf8 -m unittest tests.test_surface_review_export
tests.test_surface_review_browser -v`。截图只用于查看，验收依赖具体数据/交互断言。

首次 canvas 按 CSS client size 与 DPR 同步；二维拖动/缩放，三维旋转/缩放。
XYZ 水平/垂直使用同一米制缩放，vertical 仅改变显示。每帧有限高程范围在三角
循环外计算；DEM 不使用巨大 spread，unknown 为 null 孔洞，三维 unknown 的
最低有限高程标记仅为拾取参考平面，不是零地形。床/静态水共用投影与深度排序。
工程 camera 包含全部陆地与海口，graph 是明确的可选注释 overlay，不假称遮挡
正确的动态 fine 水面。H0/H2 互斥显示；water、wet、hydrologic owner、footprint
各层真实生效，geometry owner 与水文 owner 分开说明。
积水面严格按保存 fully-wet cell mask 取每 cell 两三角，不以三顶点 wet
替代四顶点 cell 契约；33 显示1412陆地水面三角和180 outside三角。

拾取模式可选 mesh node/cell、graph node/edge；DEM 显示点映射原 source
row/col（stride 2，指保存候选网格，不是原 TIFF 行列），保留 unknown/core/footprint；mesh 提供 cut/depth/protected/
wet、真实 contributor indices/weights；33 另提供 clamp/source-support audit。
两工程海口支持实际节点拾取、outlet identity、床/水/attachment 和中心线曲线。
graph 支持 stage/storage/Q 时间曲线、31 保存 V(h) knots 与 source-bed 范围，
边界 storage 排除，V(h) 不能解释为边界记账储量。海口 profile 来自真实保存
centerline，不硬编码 4.2 到零。每域/全局 ledger 显示保存列含义及 m³ 单位。

state n 的 Q 取保存前一 interval `[t[n-1],t[n]]`；初始 state 取下一保存
interval 并明确标签；取消零步无 Q。不给最后 state 虚构新 Q。切换案例停止
timer、清选择与图；过期 async 请求不能覆盖新案例，错误在 UI 可见。下载审查
JSON 包含结构化 selection、完整 source hash/identity、time/interval 和含 vertical/
pan 的 camera，不修改 verification。

33 为 9800 m² 原 pixel footprint 的 clamped 半像素工程解释，非观测细 DEM；
只渲染 z75..90 的两条 outside 裁接，绝不重复32全 strip。动态 boundary 仍 z70，
静态 geometry coast z75；V(h) 仍原676 wet cells，不包括出口动态 storage。32
7800 m² 案例仍显示缺2000 m²；1m/2m seam 仅有界兼容切片，不称一般跨精度。

本頁面展示固定驗收包中的已保存地表、工程海口、動態 graph state 與真實 DEM 候選。瀏覽器只讀 `web-preview/data/surface-review-v1/` 的派生 JSON，不直接解析 NPZ，也不執行 prepare、recovery、mesh sampling 或時間求解。

## 啟動

在工程根目錄執行：

```powershell
D:/anaconda/python.exe -X utf8 web-preview/build_surface_review_data.py
D:/anaconda/python.exe -X utf8 web-preview/serve.py --port 8765
```

開啟 `http://127.0.0.1:8765/`。若 8765 已被占用，可指定其他本機埠。匯出命令只接受程式內固定 allowlist，會先使用各來源的靜態 loader，並將來源路徑、SHA256、artifact identity、座標軸、scope 與限制寫入每個案例。

## 案例

預設案例是雙域 fine 地表：7991 nodes、7800 cells、15600 triangles，其中 600 cells 是原 H0 不變的乾燥補帶。工作臺可顯示 H0、H2、靜態水面參考、wet、domain/source owner、共享 x=75 m 邊界，以及 synthetic 候選 footprint 與目前 mosaic 外緣缺口。`physical_footprint_complete` 與 `natural_outlets_certified` 保持來源的 false，不由頁面推論。

動態 pulse 與 domain2 尾水上升分開顯示，使用 16 nodes、14 edges、80 個已保存 committed steps。stage 是 lumped graph state；箭頭表達 signed Q，不是流速。尾水案例的 domain2 負 Q 可在時間軸和節點曲線中查看，兩個 domain component 不會被前端硬連成跨域河。

domain1 海口展示已保存的 84 nodes、120 triangles 與中心線 4.2 m 到 0 m 的靜態工程幾何。海側是 synthetic，固定水面參考不會因動態案例自動生成新的海口 mesh。

DEM 候選使用 `load_dem_candidate(..., verify_source=False)` 做離線結構檢查，顯示 642×460 source grid 的 stride-2 視圖。unknown 與 core unknown 以孔洞／警示色和 mask 保留，NaN 轉成 JSON null；不填 0、不鋪跨 unknown 的連通三角，也不與 synthetic 工程場景拼接。

舊的三個 Terrain Diffusion 預覽仍使用原本的 `web-preview/data/manifest.json`，沒有覆蓋或改寫。

## 審查記錄

右側備註只存在頁面記憶體。按「匯出審查記錄」會產生 JSON，包含 case/source hash、view、layer、timeSeconds、相機參數、選中內容與使用者備註；評論不會寫回任何 verification 包。

## 已知限制

本轮 exporter 的冷缓存测试禁止 prepare/recovery/advance、`_fine_source` 采样
及 mosaic/工程/land 的生成入口。B 修复保存 support 的静态校验路径后，
五项 exporter 聚焦测试全部通过；保留完整 proof/config 校验，不绕过 load。
旧失败证据保留，后端修复另存 supplemental evidence，原来源包身份不变。

三維視圖是已保存的地表三角面渲染，不是地下或多層三維河網。水面顯示是靜態參考 geometry；動態顯示只使用保存的節點 stage/storage/Q。DEM 未認證真實河口、垂直 datum、完整覆蓋與授權，不能作為自然地理認證。頁面不啟動遊戲、模型、GPU 計算，也不重新生成河網。

## 測試

只跑本次 exporter 的聚焦測試：

```powershell
D:/anaconda/python.exe -X utf8 -m unittest tests.test_surface_review_export -v
```

測試涵蓋固定 allowlist、source identity、三角索引數量、axes、unknown mask/null、signed Q、committed prefix、海口 XYZ 與禁止呼叫 prepare/advance。
