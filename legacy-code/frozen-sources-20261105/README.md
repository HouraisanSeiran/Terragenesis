# 冻结源文件快照（2026-11-05）

本目录是**证据复验用的冻结副本**，不是代码，也不是活跃模块。

## 为什么存在

`verification/` 里的历史证据用 SHA256 点名了具体源文件（硬 pin），另有一批源文件的哈希被写在
`tools/prepare_hybrid_river_hydraulics_v*.py` 的 `FROZEN_CODE`、`legacy-code/*/manifest.json`、
`legacy-code/hybrid-hydraulics-before-20261023/validation-source-freeze.json` 和
`diffusion/config.py` 的源文件身份列表里（隐形 pin）。

之后的重构会大量合并、改写、归档源码。为了让这些旧证据仍能逐字节复验，在重构动手之前把被点名的
源文件按原相对路径原样复制一份存在这里。

## 用户决定（2026-11-05）

- **旧产物原样保留**，不因为重构而废弃；
- **活跃源码不再负责复现旧产物**：重构以「一个功能一个内核、模块越少越好」为准，不要求重构后的代码
  仍能产出与 `verification/` 下完全一致的旧结果；
- 因此旧证据的复验依据就是本目录的字节副本 + `manifest.json` 里的 SHA256。

## 规矩

1. **不得被活跃代码导入。** 这里没有任何 `__init__.py` 的包语义，目录也不是 import 路径；
   `terrain_pipeline/`、`tools/`、`tests/`、`diffusion/` 下的新代码都不许 `import` 本目录里的模块。
   需要旧实现时用本目录**只读参照**（对照行为、搬运函数体），不要让运行时代码依赖它。
2. **不得修改。** 副本是原字节的复制品，`manifest.json` 记录了每一条的 SHA256；改一个字节就不再是证据。
   要修旧实现，改活跃源码，不要改这里。
3. **不得被 pytest 收集。** 目录结构与仓库根相同，`tests/` 下是历史测试副本；`conftest.py` 里的
   `collect_ignore_glob = ["*"]` 保证 `pytest` 不会把它们当成活跃测试（它们依赖历史模块关系，
   在副本里本来也无法独立运行）。

## 内容

- `manifest.json`：每个文件一条 `source_path` / `sha256`（原始字节）/ `bytes` / `pin_kind`
  （`hard` = 只被 `verification/` 点名；`implicit` = 只被工具或冻结清单以哈希引用；`both` = 两者）/ 
  `evidence_refs`（硬 pin 列出前 20 个证据文件与总数，隐形 pin 列出引用它的来源文件）。
  顶层还有生成时间、总数与快照 `dist/Terragenesis-algorithms-20261105.zip` 的 SHA256。
- `conftest.py`：禁止 pytest 收集。
- 其余文件按原相对路径存放，例如 `terrain_pipeline/rainfall_runoff.py`。

## 怎么校验

```powershell
runtime/venv/Scripts/python.exe -B tools/verify_frozen_sources.py            # 逐个核对副本 SHA256
runtime/venv/Scripts/python.exe -B tools/verify_frozen_sources.py --evidence  # 再核对硬 pin 哈希仍在证据文件里
```

退出码 0 = 全部通过。
