# 全仓一方源码模块职责台账

此目录为自动生成的逐文件静态台账，不是各阶段已完成/已认证清单。

人工职责覆盖在 annotations.json 管理，生成器不改该文件。源码正文说明与人工审阅分开标记；缺少说明不按文件名猜测职责。

| 源码范围 | 文件数 | 分表 |
| --- | --- | --- |
| diffusion | 20 | [diffusion-01.md](diffusion-01.md) |
| root | 3 | [root-01.md](root-01.md) |
| src | 120 | [src-01.md](src-01.md) |
| src | 40 | [src-02.md](src-02.md) |
| terrain_pipeline | 120 | [terrain_pipeline-01.md](terrain_pipeline-01.md) |
| terrain_pipeline | 120 | [terrain_pipeline-02.md](terrain_pipeline-02.md) |
| terrain_pipeline | 120 | [terrain_pipeline-03.md](terrain_pipeline-03.md) |
| terrain_pipeline | 74 | [terrain_pipeline-04.md](terrain_pipeline-04.md) |
| tests | 120 | [tests-01.md](tests-01.md) |
| tests | 120 | [tests-02.md](tests-02.md) |
| tests | 120 | [tests-03.md](tests-03.md) |
| tests | 120 | [tests-04.md](tests-04.md) |
| tests | 86 | [tests-05.md](tests-05.md) |
| tools | 120 | [tools-01.md](tools-01.md) |
| tools | 120 | [tools-02.md](tools-02.md) |
| tools | 120 | [tools-03.md](tools-03.md) |
| tools | 120 | [tools-04.md](tools-04.md) |
| tools | 120 | [tools-05.md](tools-05.md) |
| tools | 61 | [tools-06.md](tools-06.md) |
| vdm_diffusion | 13 | [vdm_diffusion-01.md](vdm_diffusion-01.md) |
| web-preview | 25 | [web-preview-01.md](web-preview-01.md) |

共 **1882** 个文件；说明依据计数：`{'manual-reviewed': 172, 'source-comment': 4, 'source-docstring': 1171, 'unreviewed': 535}`。
解析/解码错误：0。人工标注未匹配路径：[]。

## 范围与排除

- 活跃一方源码逐文件覆盖：terrain_pipeline、diffusion、vdm_diffusion、tools、tests、web-preview、src，以及根构建/启动入口。tests和tools有独立角色，不当成生产算法。
- legacy-code：冻结历史复验源码，见[归档规范](../../../legacy-code/README.md)，不重复计入活跃模块。service-0.9.0、backups、.claude/worktrees：历史/副本，不作为当前调用者。
- vendor、runtime、node_modules、models：第三方源码/运行环境/权重；data、cache、build、dist、preview、verification、各run-*和deltaRCM_Output：数据/构建/结果/冻结证据；不作为一方活跃算法。
- docs、research、algorithm、river-system、minecraft-mod、bootstrap-assets、.scratch：文档、清单、实验和交付记录；按目录身份管理，不将内部实验脚本登记为默认生产模块。其余根临时数据/日志不归为模块。
- .git、.vantaloom等运行元数据不扫描；不读凭据、环境配置和数据内容。

## 维护

```powershell
runtime/venv/Scripts/python.exe -B tools/build_module_catalog.py --write
runtime/venv/Scripts/python.exe -B tools/build_module_catalog.py --check
```

新增/删除/移动源码或职责改变时，先更新 annotations.json（人工确认的用途/阶段），再重新生成。--check 对比文件覆盖、内容哈希和全部生成表，不会写入或替代测试。
自动说明只取模块docstring/首注释；source-comment可能只是版权/格式声明，需人工复核。shared-or-unmapped表示尚未完成阶段映射，不能解释为无用文件。静态无调用者也不能作为删除依据：动态导入、反射、命令行、HTTP/配置、外部消费者和源码pin须另审。

具体方法、现有入口与设计缺口见[工程实现说明](../implementation-guide.md)。
