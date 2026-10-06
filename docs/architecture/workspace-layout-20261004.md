# 工作区分层与迁移边界

日期：2026-10-04

## 当前结论

本工程是一个历史上逐步扩展的混合工作区，包含两类主要产物：

1. **Terrain Algorithm Layer**：米制地形、地表/地下河网、盆地水量、VDM 几何、侵蚀候选、固定验证和只读审查前端。
2. **Minecraft Mod Layer**：Fabric/Gradle Java 模组、世界预设、区块消费、VDM 体素化和游戏内验证。

两层现在共享根目录、`verification/` 和若干 `tools/`。大量 Python 模块使用 `Path(__file__).resolve().parents[1]`，Java 验证使用工作区相对输出，前端固定读取根目录下的 `verification/`。因此本轮采用逻辑分层，不直接移动源码、验证包或运行时目录，避免破坏固定身份和历史入口。

## 目录归属

| 层 | 当前路径 | 责任 |
| --- | --- | --- |
| 算法 | `terrain_pipeline/` | 真实地形、河网、地下水、盆地、VDM 与只读 IO |
| 算法 | `diffusion/`、`vdm_diffusion/` | Terrain Diffusion/VDM 算法支持 |
| 算法 | `tests/`、算法专用 `tools/` | Python 测试、导出、审计 |
| 算法 | `research/`、算法 `docs/` | 规格、研究与契约 |
| 算法审查 | `web-preview/` | 只读二维/三维前端和固定数据桥接 |
| 证据 | `verification/` | 版本化输入、结果、验收和失败证据；两层共享但不可覆盖 |
| Mod | `src/main/`、`src/test/` | Java/Fabric 消费链与游戏内验证 |
| Mod | `build.gradle`、`settings.gradle`、`gradle.properties` | Gradle 项目入口 |
| Mod | `dist/`、`preview/` | 发布配置与游戏预览资料 |

## 下一次物理拆分的安全顺序

1. 为算法层和 Mod 层建立各自的 manifest，列出文件、相对路径、所有者和调用方。
2. 将 `tools/` 按“算法工具 / Mod 构建工具 / 共享只读工具”拆分，并先保留兼容转发入口。
3. 将算法层变为独立 Python 包，使用显式配置传入 `workspace_root`、`verification_root` 和数据 manifest，消除隐式根目录推断。
4. 将 Mod 变为独立 Gradle 项目，以发布的算法地形包作为输入；先双构建、双验证，再移动 Java 源码。
5. 最后才考虑移动大型 `models/`、`runtime/`、`cache/` 和历史产物；这些目录不应复制。

## 当前不能做的整理

- 不能把 `terrain_pipeline/` 直接移动后再用一堆副本修路径。
- 不能移动或重命名 `verification/` 中被固定 SHA、报告和前端引用的目录。
- 不能把新的三维河网算法写入 Java 区块生成器以减少目录数量。
- 不能把 `web-preview/` 迁到另一个工程；它属于本工作区的算法审查前端。
