# Minecraft 导出预设 v1

`MinecraftExportPreset` 只作独立物理到游戏映射；不生成或修改物理地形，不改变 Java 或 TGMCMT01，不自动接入旧默认世界。

固定预设 `minecraft-y64-ceiling1024-v1`：海平面 Y64，排他上限 1024，安全地表顶 1022（其上留一个空气层），最低 Y-64。必须显式指定有限正值 `metres_per_block`。

公式 `continuous_y = 64 + elevation_m / metres_per_block`，再向下取整为地表 Y。物理海平面 0 米映射 Y64。垂直映射不隐含水平重采样；原生 30 米像素仍保持物理坐标，水平适配另行完成。

```python
from terrain_pipeline.minecraft_preset import MinecraftExportPreset

preset = MinecraftExportPreset(metres_per_block=20.0)
report = preset.dry_run(physical_elevation_m)
game_surface_y = preset.transform(physical_elevation_m)
```

`dry_run` 返回极值、越界数量与是否接受；`transform` 在整数化前拒绝任何连续 Y 超出 [-64,1022] 的输入。不静默裁剪，不逐窗口归一化，输入保持不变，拒绝空数组和非有限数据。

整个域的比例须同时满足正高程 `max_m / 958` 和负高程 `-min_m / 128` 要求。统一选择并记录比例，避免相邻窗口不同缩放。预设身份包含比例与固定几何，和物理生成身份独立。

CPU 验证器 `review.html` 与 `minecraft-dryrun.json` 展示条件场预检，标记 `conditioning_only`，不是实际 TD 导出。预设通过不代表游戏维度支持此范围，也不证明水体或世界验收成功。
