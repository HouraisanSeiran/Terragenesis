# Terragenesis 河网系统

这是河流算法、湖泊、泥沙、河床几何、地下暗河候选、审计工具和前端消费的统一分类根目录。

当前运行中的 Python 源码仍保留在 `terrain_pipeline/`，因为现有测试、保存包和Claude在途代码使用这些导入路径。`river-system/` 目前提供职责分类和迁移入口，不复制算法实现。

## 目录

| 目录 | 内容 | 当前来源 |
| --- | --- | --- |
| `canonical/` | 当前TD河网主线 | `terrain_pipeline/surface_rivers/metric_*`、`terrain_pipeline/td_*` |
| `morphology/` | 三角洲、截弯、点坝、辫状、冲积扇、洪泛事件 | `terrain_pipeline/surface_rivers/metric_delta*`、`metric_cutoff.py`、`metric_bank_braiding.py`、`metric_fan_floodplain.py` |
| `hydrology/` | 来源、汇流、降雨、河道水量、湖泊和边界 | `terrain_pipeline/surface_rivers/metric_*`、`terrain_pipeline/rainfall_runoff.py` |
| `geometry/` | 河槽、连续床、细床、VDM和地下几何 | `terrain_pipeline/surface_rivers/metric_channel_geometry.py`、`terrain_pipeline/hybrid_*`、`terrain_pipeline/underground_*` |
| `legacy/` | 旧原型、兼容接口和历史实验 | 非`metric_*`的旧`surface_rivers`、`real_dem_*`、`mountain_*` |
| `adapters/` | 外部库、数据源、前端和Minecraft消费接口 | `metric_reference_routing.py`、`web-preview/`、`src/` |
| `validation/` | 生成后冷读、审计、测试和保存证据 | `tools/audit_*`、`tools/verify_*`、`tests/`、`verification/` |

## 迁移规则

- 新河网代码只进入 `terrain_pipeline/surface_rivers/metric_*`，稳定后迁入对应分类目录并保留兼容导入壳。
- 不复制第二份算法实现。
- 原始TD、保存包、失败证据和默认世界不移动、不覆盖。
- Minecraft是后续消费子项目，不进入当前河网核心。
- 分类完整登记见 `MODULES.md`。
