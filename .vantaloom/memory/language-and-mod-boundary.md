---
name: language-and-mod-boundary
description: Python 主语言、Java 仅作地形转换与 Minecraft 导入、排在算法成熟之后
scope: project
type: spec
paths: [terrain_pipeline/**, diffusion/**, src/main/java/**]
---
## 用户拍板的语言与分工边界（2026-10-21）
**Python 是主语言**，地形算法全部在 Python 侧实现与演进。

**Java 端职责被限定为：转换已完成的地形 + 导入群系等内容，作为 Mod 把结果变成 Minecraft 内的内容。**

**时序：Java 侧排在「地形算法成熟之后」才实现。**

推论（必须据此调整口径）：
- 现在不算「Java 默认世界没接线」为缺陷——那是**计划内的次序**，不是欠债。此前把它列为 limitation 的表述要改为「按用户决定的次序，Java 侧待算法成熟后实现」。
- Python 先行案例（如 p5 群系接气候）符合此方针，但**不必**再强调「Java 侧未接」是缺口。
- `build.gradle` / `src/main/java/**` / Mod 相关改动一律不在地形算法成熟前启动。
- 调研、契约、验收器、算法实现都留在 Python（`terrain_pipeline/**`、`diffusion/**`、`tools/**`、`tests/**`）。
