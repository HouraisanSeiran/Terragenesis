# 源码交付与运行范围

仓库为 https://github.com/HouraisanSeiran/Terragenesis 。算法与Mod目前按导航/职责分层，保留既有源码路径，避免固定验证器与Gradle入口失效；没有复制第二套算法。

## 上传内容

上传算法、验证/导出工具、测试、Mod Java及资源、只读网页源码、项目文档和依赖清单。保留远端已有提交历史。代码及固定成果使用原始文件字节SHA256绑定，`.gitattributes`保持字节不被Git自动改换行；已有冻结代码不为发布重新格式化。

模型、运行环境、缓存、游戏存档、训练权重和大型验证数据在工作区本地保存，不进入普通Git提交。`.scratch/`为本地任务系统；公开交付摘要放在`docs/`。读取实际验证包的工具需要相应文件及正确SHA，源码克隆本身不包含这些输入，也不会自动用合成地形替代。

研究摘要及上游许可保留；下载的网页原文、图片和PDF不进入源码发布。未配置个人Git作者时，本轮提交明确署名`Terragenesis Automation <automation@terragenesis.invalid>`，不推断或冒用维护者姓名邮箱。

## 算法依赖

建议使用Python3.11的独立环境，在仓库根目录安装：

```shell
python -m pip install -r algorithm/requirements.txt
```

基础算法无需启动Minecraft或模型服务。模型训练/推理的额外依赖见`bootstrap-assets/requirements-lock.txt`与`vdm_diffusion/requirements.txt`，并自行准备模型；不需要为审查已保存几何下载所有模型。

## 网页与Mod依赖

网页Three.js依赖清单与lock保留，`web-preview/vendor/node_modules`不上传。在该目录执行`npm ci --ignore-scripts --no-audit --no-fund`恢复依赖。启动`python web-preview/serve.py`仍需要其明确绑定的本地审查数据；只有网页源码并不等于已具备所有审查成果。

Gradle当前读取固定Terrain Diffusion上游源码；版本和许可见`bootstrap-assets/upstream-manifest.json`。发布仅包含构建所需的清单文件、源码与原许可，不包含模型/缓存；构建Mod需要其既有Java/Fabric工具链。此轮不构建或替换JAR，不改变默认世界。

JAR产物与本地工具链不上传；克隆后需外部Gradle或按对应官方版本恢复wrapper bootstrap JAR，不能假定本机缓存已随源码提供。新水系科学成果仍为模型米制，不自动进入Mod默认世界。
