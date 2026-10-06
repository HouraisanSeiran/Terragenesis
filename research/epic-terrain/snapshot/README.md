# Epic-Terrain

高性能、写实的 Minecraft 地形重写数据包。厌倦了原版平坦乏味的地形？Epic-Terrain 重写了世界生成，带来山脉、阿尔卑斯式峰峦、大陆板块、侵蚀海岸线与全新的河流系统。

## 特性

- 平滑而真实的地表
- 壮观的阿尔卑斯式山峰
- 大陆板块式地形生成（海洋可绵延上万格）
- 全新海岸线：受侵蚀的峡湾、海、海峡、岛屿、半岛
- 新河流系统：大 / 小河、落差、源头

## 支持的 Minecraft 版本

| 数据包版本 | Minecraft 版本 | 说明 |
| --- | --- | --- |
| v0.2.5 (Beta) | 1.19.2 – 1.19.4 | 稳定 |
| v0.3.0 (Alpha) | 1.20 – 1.20.4 | 实验性 |
| v0.1.4 (Beta) | 1.20.5 – 1.21.4 | 稳定 |

> 1.19 理论上支持，但因 1.19 不支持自定义生物群系，作者不计划更新。

## 安装

1. 在 [Modrinth](https://modrinth.com/datapack/epicterrain) 下载对应你 MC 版本的数据包 `.zip`。
2. 放入存档目录 `saves/<世界>/datapacks/`，或客户端 `.minecraft/datapacks/`。
3. 进入世界后执行 `/reload`，或在创建世界时于「数据包」界面勾选启用。

## 兼容性

- 实验性产品，**默认不考虑兼容性**；相关兼容修复见 companion 包 *Epic Terrain Compatible*。
- **Terrablender 不可用**：会禁用地表功能（如河流）。
- 生物群系分布已重置，几乎**不兼容**增加生物群系的模组；修改原版的模组可用。
- **已知 Bug（1.21+）**：`minecraft:lake` 在 1.21 有问题，请用修复模组 [worldgenfeaturefix](https://modrinth.com/mod/worldgenfeaturefix)。
- 地图尺寸极大（海洋可达 10000 格），建议配合 [World Preview](https://modrinth.com/mod/world-preview) 预览。

## 仓库结构

源码按 Minecraft 版本分目录存放于 `versions/`：

```
versions/
├── 1.19.2-1.19.4/   # v0.2.5 Beta
├── 1.20-1.20.4/     # v0.3.0 Alpha
└── 1.20.5-1.21.4/   # v0.1.4 Beta
```

每个目录都是一个**完整可打包的数据包**（`pack.mcmeta` + `data/`）。将其压缩为 `.zip` 即可作为数据包分发。配置文档见 `docs/`。

## 许可

MIT —— 见 [LICENSE](LICENSE)。

## 反馈

- Bug 报告：<https://github.com/wonderfulaichen/Epic-Terrain/issues>（兼容性问题请打 `Epic Terrain Compatible` 标签）
- 源代码：<https://github.com/wonderfulaichen/Epic-Terrain>
