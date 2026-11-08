# Terrain Algorithm Layer

> 当前岛屿TD默认面积严格>100km²，峰海拔300–3000m、±10%波动；普通世界生成已接线。见[当前规则](../docs/island-mountains-current.md)。后文旧2000km²门槛属于历史记录。

这里是地形算法层的导航入口。当前为了保持既有验证器、前端和 Gradle 兼容，算法源文件仍保留在工作区根目录的既有路径；本目录先作为稳定的算法边界和迁移入口，不复制代码，也不创建第二份实现。

河流相关模块的统一分类入口为 [`river-system/`](../river-system/README.md)，登记表为 [`river-system/MODULES.md`](../river-system/MODULES.md)。当前只建立分类和迁移入口，运行源码暂不物理搬移，以保持现有导入、保存包和Claude在途写集稳定。

## 算法源

- `terrain_pipeline/`：米制地形、河网、盆地、动态水量、VDM、地理资料适配和只读 IO。
- `diffusion/`、`vdm_diffusion/`：Terrain Diffusion 与旧 VDM 相关运行支持。
- `tools/`：算法生成、导出、审计和验证命令；其中包含少量 Minecraft 构建兼容工具，迁移时必须按清单拆分。
- `tests/`：Python 算法测试。
- `verification/`：不可覆盖的实验、审计和验收产物。
- `research/`、`docs/`：研究资料、算法规格与契约。
- `web-preview/`：基于算法固定产物的只读审查前端。

## 当前原则

海洋地貌入口见 [板块岛屿与岛链](../docs/ocean-islands.md)：核心及世界层/局部条件采样归本工程，织梦导入调用；v3细化噪波及海底拼接已完成真实有限域核查。使用冻结板块来源，显式准备、自含保存与只读查询。[大型岛TD](../docs/island-mountains.md)按实际露海面积和连续腹地筛选，空计划不启动模型；当前真实来源无合格大岛。局部TD模型响应及无限上游来源另验。

2026-10-09：当前开发集中于独立地形/河网算法。Minecraft作为后续消费子项目，暂不开展新功能或迁移构建。

成熟库接入入口见 [pyflwdir图分析](../docs/reference-routing.md)：可选依赖 `requirements-reference.txt`，CLI为 `python -m tools.prepare_td_reference_routing`。直接复用已有TD图，计算汇水面积、贡献域和Strahler等级；来源与边界分类保留，历史默认产品身份不变。

算法层使用米制 XYZ、显式身份和版本化产物。算法不直接写 Minecraft 区块，也不把 Minecraft 的海平面、tick 或方块尺度反向写入物理模型。

后续物理拆分时，优先把 `terrain_pipeline/`、算法专用 `tools/`、Python `tests/` 和算法文档迁入独立包；`verification/` 保持由工作区统一管理，避免固定证据路径失效。
