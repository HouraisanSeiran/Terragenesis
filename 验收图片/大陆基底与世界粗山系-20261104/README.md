# 大陆基底与世界粗山系 · 2026-11-04

当前看 [2 km最终候选](2km-final-v1/world_comparison.png)；低成本同源对照为 [5 km最终候选](5km-final-v1/world_comparison.png)。两份都采用 `curved-world-belts-3`，覆盖1600×1280 km同一冻结大陆，坐标X东/Z南、米制格心。

**程序化世界粗地貌，非TD。** 历史基底实际种子20261020，新形态种子20260903。原板块来源identity `b4c8bbdba29111b8c3ba3270e2f0d3a4fed3544655249fa07c506654b8ae6af9`；原始数据不改写。本图集无新河网、湖泊、水沙、气候、植被、积雪或材质模拟，不把盆地轮廓当作已验湖泊。

每个最终目录中的图：

- `world_comparison.png`：原板块高程代理、降低代理峰幅的大陆基底、最终粗山系，同范围、色阶与光照。
- `world_terrain.png`：最终同源俯视地形配色与真实坡度阴影。
- `continental_closeup.png`：固定600×600 km大陆局部，格距与全域一致。
- `mountain_inventory.png`：新增山带高度及已保存主带/平行脊/斜支脉/盆地清册叠图。
- `ridge_profile.png`：沿最长已保存主带约430 km的峰鞍剖面，查询插值不增加物理精度。
- `*_16bit.png` / `*_preview.png`：固定[-5000,12000] m米制高程的16bit灰度/8bit预览，前者最大量化误差≤0.129702 m，无饱和。

`manifest.json`是对应原始运行清单的逐字节副本，包含来源、双seed、参数、库存、计时、环境、源码摘要、数组与图片摘要。`gallery-manifest.json`记录原始运行目录和所有副本SHA检查。米制NPY/完整NPZ与源码快照保存在对应 `.scratch/world-mountain-belts-20261104/run-*-final-v1/` 中。

2/5 km共享保存几何，在13287个公共点上几何求值差0；栅格独立采样和插值存在误差：最终高程query最大差461.81 m、RMSE13.71 m。地图粗形态可比，不宣称栅格严格跨精度一致。

`5km-preview-v1/`、`5km-preview-v2/` 是修正连续性/海岸过渡/形态结构前的历史候选，保留用于追溯，不作为当前最终几何。图片检查通过仅证明保存与来源可追溯；形态自然度由主端和用户图审。
