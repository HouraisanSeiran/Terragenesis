# FV历史增长源码隔离归档

本目录保留用户A方案要求的完整历史执行/恢复，而不是当前默认后端。

## 信任根与范围

- 原A0 `manifest.json` SHA256固定为 `f76ddcec2d4523ae9ef31f5da7ae03c1eb5e4aaa267797b590310940c739da70`，包括50份原源码与3份真实summary参数模板；从原任务延续，未因本次恢复实施改写。
- 原CP既有的11/15/19键implementation签名仍按原集合精确验证；50份闭包只表示迁移前快照，不追溯声称旧CP当年签名全部间接helper。
- 恢复时另发现历史诊断工具 `tools/diagnose_fv_mpm_rejection.py` 调用旧v3。其11877字节原文单独放在 `supplemental/`，SHA `c87c6880f0f8a5bd4600603218edd56e8c548678cce838e3a740923a713802d4`；补清单 `supplemental-manifest.json` SHA固定为 `01d9f6d904cd71d65674d1a6d476ce437527aa9089efa0855ee3108b3f64c3dd`。不修改A0清单或旧CP签名来把它伪装为旧签名成员。该工具递归41个本地源码依赖均在A0/补充闭包，没有缺项。
- Python、NumPy、Numba等运行库未完整封存；旧源码复验不等于任意环境逐位再现保证。

## 默认与显式历史路径

当前默认为 `tools/run_natural_fv_growth.py` 或 `tools/run_natural_fv_growth_v4.py`，装配显式公共growth_core、current interval/scheduler/codec。它不导入此归档，不使用FunctionType或临时v3 schema。默认仍要求完整current-v4 checkpoint，不自动bootstrap、不自动升级v2/v3。

完整历史恢复通过：

```text
runtime/venv/Scripts/python.exe -B tools/replay_natural_fv_growth_legacy.py
  --legacy-runner v4 --resume <original.npz> --resume-sha256 <original SHA>
  --parameters <pinned-summary-or-complete-template.json> --parameters-sha256 <template SHA>
  --output <new directory> --duration-s <explicit finite window>
```

支持明确的v1/v2/v3/v4历史执行；checkpoint schema必须与所选runner匹配。PRE_CAP_V2原runner字节尚未取得，只保留原loader允许的受限状态迁移，不能声称精确PRE_CAP调度器本体复验。历史恢复必须给完整参数模板，不能猜缺失的潮汐、波浪、浓度、压缩及调度参数；不得自动重发模板的append_source。

`tools.natural_fv_growth_state_io.migrate_legacy_checkpoint(...)`是显式冷迁移，需CP外部SHA、参数模板及SHA、新输出路径。旧v4→current-v4保持状态逐位，产物记录真实新source closure；v1/v2/v3→v4需显式`upgrade_physics=True`，它是物理规则升级，不能说后续数值与旧算法等价。所有历史源码签名和原CP SHA作为来源保留。

旧MPM诊断命令必须加 `--legacy-v3-replay`、CP/参数外部SHA，`--captured-input`若提供也需SHA；无该显式选择则拒绝。旧v3前缀恢复同样要求 `--legacy-v3-replay` 与选定末CP/参数模板外部SHA。只读旧运行审计需 `inspect_natural_fv_growth.py --legacy-replay`，当前结果审计不自动fallback到归档。

## 隔离与拒绝

显式历史数值执行使用独立worker；本地源码只从可信清单加载到私有命名空间，不将归档加入sys.path或绑定裸旧模块名。源码/manifest联合篡改、缺签名、错template、错carrier合同均拒绝。数据根与原源码标签分开，原verification/及旧CP不改。每次载入先复核归档，不能缓存后跳过篡改检查。

本轮只迁移FV增长族及直接工具/测试，水动力v7、exchange-v3、bedload-v4、suspended和coastal MPM等不同职责仍为当前必要内核，不能按文件号一并删除。
