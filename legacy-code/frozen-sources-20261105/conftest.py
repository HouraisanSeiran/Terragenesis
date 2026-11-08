"""冻结副本目录：禁止 pytest 收集，并从 sys.path 里摸掉自己。

这里的文件是证据复验用的原始字节副本（见 manifest.json），不是活跃测试或模块；
目录结构与仓库根相同，直接收集会与真实测试同名、并因缺少同级模块而报错。

除了忽略收集，还要把本目录从 sys.path 中摸除：pytest 的 prepend 导入模式在加载本
conftest 时会把本目录插到 sys.path 前面，于是 `terrain_pipeline`、`tools` 等包会
错指向冻结副本、遮蔽仓库根下的真实实现。
"""
import os
import sys

collect_ignore_glob = ["*"]

_HERE = os.path.dirname(os.path.abspath(__file__))


def _drop_self_from_sys_path():
    kept = []
    for entry in sys.path:
        try:
            resolved = os.path.abspath(entry or os.getcwd())
        except (OSError, ValueError):
            kept.append(entry)
            continue
        if resolved != _HERE:
            kept.append(entry)
    sys.path[:] = kept


_drop_self_from_sys_path()
