# Terragenesis（山川形意）

面向**无限世界**的地形生成算法系统。目标是在世界生成场景中**部分替代 World Machine / Gaea**：按需生成、有限依赖、确定性、可审计，而不是制作单张有限图幅。

> **状态：开发中，未发布。** 本文口径为 2026-11-08；逐日进展与历史记录在 [TODO.md](TODO.md)，文档索引在 [docs/README.md](docs/README.md)。所有算法产物标记 `status=candidate`，能力位（`hydraulic_ready` / `natural_outlet_verified` / `publishable`）保持 `false`，除非对应验收已经通过。

## 现行入口

| 文档 | 用途 |
| --- | --- |
| [docs/README.md](docs/README.md) | 现行文档入口（必读 / 架构 / 专题 / 归档分列） |
| [TODO.md](TODO.md) | 工程进度总览与逐日记录 |
| [无限世界地形生成评价标准.md](无限世界地形生成评价标准.md) | E1–E9 评价项与四档交付状态；算法选型与验收以此为准 |
| [CONTEXT.md](CONTEXT.md) | 领域词汇与系统语境 |
| [docs/architecture/routing-terminology.md](docs/architecture/routing-terminology.md) | 路由术语：图接收点 / 宏观格 D8 / D4 分组，以及 `strict-D8` 旧名的处理边界 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 编码规则、共用世界种子、版本管理、验收约定 |
| [docs/terrain-diffusion-four-stage-roadmap.md](docs/terrain-diffusion-four-stage-roadmap.md) | 四阶段主线、边界与未完成项 |
| [docs/architecture/world-generation-system/README.md](docs/architecture/world-generation-system/README.md) | 模块总览与四阶段分类（机生成台账） |

## 四阶段主线

| 阶段 | 范围 | 状态 |
| --- | --- | --- |
| **1. 无限世界河网** | 30 m 原生基底、汇流与盆地、河湖、河槽几何、水沙账本 | **进行中，端到端未完成**（拓扑与守恒可用；供水与输沙仍是情景参数） |
| **2. 地理环境 G1–G20** | 气候、土壤、水分、雪冰、风化成土、海岸 | **有限工程版，未整体完成**；参数未与文献量级标定 |
| **3. 非高度场三维地貌 V1–V8** | 洞穴、天坑、石柱、悬挑、岩壁 | **离线原型，未接入无限世界** |
| **4. Java / Minecraft 适配** | 把已验收产物转换为游戏世界 | **未启动，未完成**；只做转换与消费，不决定算法语义 |

阶段 1–3 全部为 Python 算法与产物；第 4 阶段在此前三阶段成熟前不开始。四阶段编号不代表完成度，也不能由测试数量折算。

## 当前能跑出什么（有限范围，均已保存证据）

- **三角洲 v5（2026-11-08）**：真实低地与有限地质库存构造连续平原，基准 267.03 km²，原口左右宽 7.15 / 3.25 km；同一算法在百公里内部跨度 100.3 km（口门跨度 24.57 km）。两例各 600 秒，固体账差 0，冷读续算逐位一致，65 项相关回归通过。**未通过/未接**：潮流反转、长期漫滩与迁汊、30 m 尺度的岸边切山与拓扑变化、多尺度一致性。
- **海洋岛屿与岛链 v3（2026-11-07）**：64 万格正式产品，交线坡跳 0.481184 → 0.000373 m/m，无新增陆桥，45.80 秒、采样 RSS ≈ 440 MiB。大型岛的 TD 资格条件（≥2000 km² 且 3 km 岸缓冲后内接圆 ≥20 km）尚未被真实主源触发。
- **火山岛 v5（2026-11-08）**：主工程 148 项、协作方 31 项检查通过，旧 v4 可精确回放。形态候选，不代表岩浆物理。
- **世界粗山系（2026-11-04）**：1600×1280 km 冻结大陆上的 5 km 预览与 2 km 正式产品，512000 格，核心生成 2.123 秒、RSS 158.24 MiB。**E4 未通过**：5/2 km 公共点最大差 461.81 m、RMSE 13.71 m，LOD 过渡未做。
- **42 km 跨区域水文交接（2026-10-30）**：196 万格，37 条河道边与 17 个盆地在磁盘模式跨原请求界，独立水量账与冷读通过，78.77 秒 / 600.91 MiB。
- **世界过程链路（2026-11-08）**：1600 km / 2 km 实跑 162.71 秒、CPU 142.64 秒、峰值 2.89 GB；同批次 attempt01 在计算前被内存门槛拒绝（可用 3.480 GB < 要求 3.955 GB），因此不沿用旧成绩。

## 明确未完成 / 不予宣称

- 无限世界的**端到端**按需生成与增量调度；世界级稳定水文域、永久归属与跨请求一致性。
- **动态水动力**：回水、洪泛、二维双向浅水尚未实现；现有为有界 Manning 储量与湖河共步。
- **供水与输沙的物理标定**：产流径流系数、泥沙供给、海岸沉积系数仍为声明常数（量级核对见 [1–3 阶段科学评估](Terragenesis-1-3阶段科学评估与开源对照-20261104.md) §5）。
- **山体自然度（E5）**：连续多轮形态试验均"自然度未通过"，当前主线改为大陆基底 → 世界粗山系 → TD 局部细化。
- **多尺度一致（E4）**、**可控编辑与有限重算（E7）**。
- **第 4 阶段**：Java/Minecraft 适配未启动。

## 目录结构

| 路径 | 职责 |
| --- | --- |
| `terrain_pipeline/` | 米制算法主体：河网、河湖、三角洲、环境、三维地貌、岩性 |
| `diffusion/` | Terrain Diffusion 推理、条件场与后端接口 |
| `tools/` | 可执行入口：`prepare_*`（准备）、`audit_*`（独立审计）、`verify_*`（验收）、`render_*`（出图） |
| `tests/` | Python 测试；入口与约定见 [tests/README.md](tests/README.md) |
| `docs/` | 现行文档；`docs/archive/` 为过时报告 |
| `research/` | 文献与方法筛选 |
| `legacy-code/` | 冻结历史源码，按批次保存，供显式复验 |
| `third_party/` | 第三方参考实现 |
| `验收图片/` | 图集与图片清单（见 [目录.md](验收图片/目录.md)） |
| `src/`、`build.gradle` | 第 4 阶段预留，当前未启动，不参与算法 |

`terrain_pipeline/`、`tools/`、`tests/` 之外的目录默认不入库：`verification/`、`.scratch/`、`preview/`、`runtime/`、`models/`、`vendor/` 与图集二进制留在工作区，边界见 [docs/source-publication.md](docs/source-publication.md)。

## 环境与运行

```powershell
# Python 3.11（项目自带虚拟环境）
runtime/venv/Scripts/python.exe -V

# 测试依赖（pytest 等）
runtime/venv/Scripts/python.exe -m pip install -r requirements-test.txt

# 跑单个测试文件（推荐；完整套件较慢）
runtime/venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_bounded_glacier.py -q
```

- 测试按文件独立运行；部分模块导入会触发 numba 首次编译，冷启动可能需要数分钟，这不是回归失败。
- 共用世界种子为 `WORLD_SEED = 20260903`，定义见 [CONTRIBUTING.md](CONTRIBUTING.md#共用世界种子用户更新2026-11-03)；子种子由用途名确定性派生。
- 坐标统一为米制、明确海面基准与有效范围；模型米制坐标与任何方块坐标的换算必须显式声明。

## 版本与证据

- 基线标签 `baseline-20261108`（2026-11-08 工作树收口）；此后按 [CONTRIBUTING.md](CONTRIBUTING.md#版本管理2026-11-08-收口) 提交。
- 验收证据保存在 `verification/` 与 `验收图片/`，图集索引入库、图与数组不入库。
- 模块版本不使用 `*_vN` 文件名；历史实现移入 `legacy-code/<批次>/`，复验用 `git show <tag>:<path>`。
