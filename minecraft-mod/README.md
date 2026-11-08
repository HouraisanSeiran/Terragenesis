# Minecraft Mod Layer

> **状态：未完成，未启动。** 本层对应四阶段主线的第 4 阶段，在前三阶段（Python 河网 / 环境 / 三维地貌）成熟并通过验收之前不开始开发。仓库中的 Java 源码是历史兼容实现，不是当前算法主线，也不代表任何世界生成能力已达标。项目进度与算法主线不含本层内容，见 [README.md](../README.md) 与 [TODO.md](../TODO.md)。

这里是 Minecraft 适配层的导航入口。当前 Gradle 项目仍以工作区根目录为项目根，Java 源码保留在根目录 `src/`，以避免改变 Fabric、Gradle、验证器和历史构建产物的相对路径。

## Mod 源

- `src/main/java/`：Minecraft 世界生成、区块、河流、岩壁、VDM 体素化和消费接口。
- `src/main/resources/`：Fabric、world preset、biome、dimension 和资源配置。
- `src/test/java/`：Java/Minecraft 消费链验证。
- `build.gradle`、`settings.gradle`、`gradle.properties`：当前 Mod 构建入口。
- `dist/`、`preview/`：Mod 发布配置和历史游戏预览资料。

## 边界

Mod 只消费算法层发布的地形包、河网、地下结构、水体和材料数据，负责坐标映射、方块写入、世界预设和游戏内验证。完整河网拓扑、降雨产流、地下水和侵蚀计算不得隐藏在单个区块生成器中。

后续拆分 Mod 时，先建立独立 Gradle 子项目并完成双向构建，再移动 `src/` 和 Gradle 文件；在此之前不要直接移动目录或复制 Java 实现。
