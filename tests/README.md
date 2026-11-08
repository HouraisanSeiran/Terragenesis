# Python 测试

在工程根目录使用项目虚拟环境：

```powershell
runtime/venv/Scripts/python.exe -m pip install -r requirements-test.txt
runtime/venv/Scripts/python.exe -B -X utf8 -m pytest --collect-only -q
runtime/venv/Scripts/python.exe -B -X utf8 -m pytest tests/test_underground_rivers.py -q
```

默认 pytest 收集入口是根目录 `tests/`。历史备份、归档和验收快照保持原样；复验时显式指定历史测试路径，并使用对应的历史实现环境。Java/Fabric 测试使用 Gradle。

浏览器测试需要 Playwright Python 包及本机 Microsoft Edge（`msedge` 渠道）；当前使用系统已安装的 Edge，无需执行 `playwright install`。仅做 `--collect-only` 不启动浏览器。完整浏览器验收还须按对应测试准备服务与输入产物。
