# 工作区实验数据清理记录

2026-10-14 对本地工作区做了一次空间清理。清理前扫描到约99.94GB文件；初始扫描跳过4处跨盘junction及其他重解析点，不含它们的目标文件。逻辑文件大小与NTFS压缩后的实际占用不同。清理后 D 盘可用空间从约198.05GB增加到约223.60GB，本地文件约73.44GB（末次扫描不含.git，约9MB，随后删除约20.6MB的临时盘点清单）。GB均为十进制。空闲空间差值也可能受同时运行的其他进程影响。

## 已删除

- `verification/td-natural-river-stages/spatial-series-20261011-02.returning`：逐文件、逐SHA256证明与 `spatial-series-20261011-02` 完全相同，删除约6.21GB。
- `verification/td-natural-river-stages/spatial-series-20261011-02-original`：同样与当前保留副本完全相同，删除约6.21GB。
- `runtime/pip-cache`、`runtime/tmp`：可由 pip 和测试重新生成的下载、安装和编译临时文件。
- `verification/bootstrap-cold/Terragenesis/`：旧冷启动环境的完整副本，含重复的 Python/依赖、Terrain Diffusion 源码、模型和缓存；保留其外层 `install*.log`、`managed-service.json` 和 `service.log` 作为冷启动证据。删除前已确认当前入口使用 `runtime/venv`，工作区没有现行文档引用该副本路径。
- 工作区各处可再生的 `__pycache__`、`.pytest_cache`、`.mypy_cache` 和 `.ruff_cache`。

本轮D盘空闲空间增加约25.55GB。保留了主模型权重、主运行环境和当前源码；旧冷启动副本内的模型、环境及源码随该副本移除，不能再用旧路径启动该冷环境。逐文件重复证明保存在 `.scratch/storage-cleanup/duplicate-proof.json`。冷启动副本外层日志保留，但内部安装日志和旧环境不是完整归档。

## 保留

- 原始 TD 缓存、Terrain Diffusion 模型权重和当前 `runtime/venv`：它们是重新生成和复验的输入。
- `verification/hydrological-planning-domain/large-td-confluence-20261014-03`：修复方形截河后的原生TD河网基准。
- `verification/hydrological-planning-domain/large-td-lowland-20261014-01`：当前低地径流/季节性河道产品、图、冷读报告和身份摘要。
- `verification/td-terrain-generated-rivers/generated-20261011-04` 与 `shape-repair-20261013-37-resumed-all-six`：六源河槽基准和最近的形态修复证据。
- 阶段0–5、自然度失败、旧方形截河失败和规划域失败记录：这些是解释算法边界所需的失败证据，不可用“新结果通过”覆盖。
- `docs/`、`CONTEXT.md`、`TODO.md`、`.scratch/`任务记录和源码测试。

## 暂不删除

`verification/` 仍有大量历史批次，约66.3GB。4处跨盘证据链接在本次检查中目标不可达，对应的 `.returning` 文件夹均保留，不能按后缀当垃圾删掉。历史独立批次可以按批次归档，但当前没有逐目录建立“唯一保留版本”清册，因此本轮不凭文件名猜测删除。

按Git已跟踪及未忽略源码文件统计，排除依赖、构建及vendor，总计250,858物理行，包含注释和空行，1,424个文件，文本约14.95MB：`terrain_pipeline` 91,928行、`tools` 94,237行、`tests` 49,832行，其余为Java、前端和辅助源码。另把被忽略的历史 `verification` 与 `.scratch` 脚本也计入时达到约568,478行。这些不是单一河网算法的核心规模；工具/测试占比约57.4%，版本并存和逐轮验收脚本增加了维护负担。本轮没有删除源码。

清理后已读取当前低地存档，并重新计算当前低地存档和03来源存档SHA256，均与原验收报告一致；主Python与NumPy可用。没有重跑河网生成或把历史通过记录称为新的算法验收。

下一次清理应先生成每个实验批次的来源、状态、唯一产物和再生入口清册，再删除同一批次中间快照。删除源码工具前必须先确认没有被固定验收入口、历史报告或当前测试引用；这种整理主要改善维护性，释放空间很少。
