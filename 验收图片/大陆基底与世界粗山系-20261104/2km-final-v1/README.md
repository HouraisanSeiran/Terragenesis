# 大陆基底与世界粗山系

程序化世界粗地貌，非TD。格距 2000 m；1600×1280 km真实冻结板块背景。基底实际种子 20261020，新形态种子 20260903。

world_comparison.png 为同色阶/光照的原代理、压低峰幅基底、最终地表；world_terrain.png 为最终同源俯视。continental_closeup.png 是固定600 km大陆局部；mountain_inventory.png 叠加真实保存清册；ridge_profile.png 沿最长主带查询。

仅地形配色，无真实植被、积雪或材质分类；海洋读保存连通掩膜，负高程内陆洼地不绘作海洋或已验湖泊。16bit灰度固定映射 -5000 至 12000 m，8bit仅预览。NPY/NPZ保留米制数组；量化、读回、文件摘要见manifest.json。

未重跑水文、GPU、局部TD或游戏。来源原件不可变；source_snapshot保存本次实际代码。
