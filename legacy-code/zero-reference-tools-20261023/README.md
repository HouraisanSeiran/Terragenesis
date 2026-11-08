# 工具层零绑定文件归档（第 1 批，2026-10-23）

**范围**：只归档「活跃代码零引用 + 冻结证据零引用」的工具。
被 `verification/` 记录为审计者/执行者/生成者的工具**一律保留**，理由见下。

## 归档内容

| 原路径 | 字节 | SHA256 | 活跃代码引用 | 冻结证据引用 |
|---|---:|---|---:|---:|
| `tools/export_td_watershed_inspection_v2.py` | 25870 | `3d758302af049406f760a7cb19b9b5ac7df63f47785c200675526fa47fef1c9a` | 0 | 0 |
| `tools/prepare_hybrid_river_faces_v2.py` | 25805 | `3a2db8e7b2afe66c1611f85b0aa1ac8f9daf3b0f6b9d6c572cadfc531c2c5298` | 0 | 0 |

归档目录：`legacy-code/zero-reference-tools-20261023/`，保留原相对路径层级。
`manifest.json` 记录原路径、字节数、SHA256 与归档路径，SHA 固定写入代码/文档，供后续校验。

## 归档理由

这两份在**全部活跃 .py（1508 个）**中零引用，且在 `verification/`（7524 个 json/md）中零引用。
删掉不改变任何生产路径，也不会让任何冻结证据失去可复现的审计者。

## 明确「不归档」的工具及依据

初版清单里有 9 个，经核实后**只归档 2 个**。其余全部保留，因为它们是冻结证据指名道姓的记录对象：

| 工具 | 证据引用数 | 证据中的角色 | 实测 SHA 一致性 |
|---|---:|---|---|
| `verify_td_basin_storage_v4.py` | 8 | `execution-code.json` 等记录的执行者 | 待逐条核（记录在案） |
| `verify_td_basin_storage_v5.py` | 7 | 同上 | 待逐条核 |
| `verify_td_basin_storage_v6.py` | 7 | 同上 | 待逐条核 |
| `audit_hybrid_cave_geometry.py` | 2 | `independent-audit-v2.json` 审计链 | — |
| `audit_hybrid_cave_geometry_v2.py` | 2 | `audit_code_sha256` 登记的审计者 | **与记录完全一致** `fb35600b…` |
| `audit_td_ported_network_composition.py` | 2 | `independent-audit-v3.json` 审计链 | — |
| `export_hybrid_river_faces_review.py` | 1 | `code_sha256` 登记的审查者 | **与记录完全一致** `8aa5dbcf…` |
| `benchmark_height_budget_v5.py` | 1 | `saving_code` 登记的产物生成者 | **与记录完全一致** `cdf0edcd…` |
| `benchmark_height_budget.py` | 1（经 v5 族） | 与 v5 **职责不同**（v1 跑真实模型预算采样；v5 做输入压缩筛选），不是版本冗余 | — |

**关键判断**：这些工具"没人 import"不等于"没人需要"。`verification/` 里的
`audit_code_sha256` / `code_sha256` / `saving_code` 字段把它们的 SHA 当作证据的一部分。
删除会让那批冻结记录失去可复现的审计者——那是损坏证据，不是清理冗余。

## 一个反例：曾误判为重复的两个文件

`benchmark_height_budget.py`（v1）与 `benchmark_height_budget_v5.py` 名字像版本关系，
实测两者**并不同源**（182 行 vs 191 行，函数集完全不同）：
- v1：`_write_json/_sha256/_sample/_brief`，跑固定真实模型高度预算采样
- v5：`_range/_condition_probe/evaluate/_score`，做 v5 输入压缩筛选与留出种子

所以"同族"不等于"同功能"，更不等于"可以只留最新"。

## 未做

- 未修改任何生产代码、`verification/`、Java/Mod。
- 未处理带硬 pin 的族（浅水 v8、hydraulics、几何、basin codec），那些需要先迁 pin 再删。
- 归档文件**不加入** `sys.path`，不作为默认导入路径；需要时用显式路径引用。
